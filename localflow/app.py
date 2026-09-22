"""LocalFlow app shell: menu bar item, state machine, and wiring.

M03: model inference (ASR + cleanup) moved into a fresh subprocess owned by
``localflow.v2.supervisor`` (Spec S06/S09). This parent process holds no
MLX/Metal state; it alone owns capture, targets and insertion authority.
Capture blocks journal to disk off the audio callback
(``localflow.v2.capture_journal``) so a crash mid-dictation recovers every
complete block with an honest incomplete-tail flag.
"""

import json
import os
import pathlib
import queue
import signal
import threading
import time

import numpy as np
import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSSquareStatusItemLength,
    NSStatusBar,
    NSWorkspace,
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from . import config as config_mod
from . import v2
from .audio import Recorder
from .hotkey import DISPLAY_NAMES, HotkeyListener, MouseTriggerListener
from .inject import copy_text, paste_text
from .overlay import MODE_FAILED, MODE_PROCESSING, MODE_RECORDING, Overlay
from .permissions import ensure_permissions
from .v2 import capture_journal
from .v2 import normalize as v2_normalize
from .v2.supervisor import WorkerFailure, WorkerSupervisor

STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"

# Audio of the last few dictations, kept for replay when a transcript
# comes out wrong (local only, pruned to the newest AUDIO_DEBUG_KEEP)
AUDIO_DEBUG_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow-audio"
AUDIO_DEBUG_KEEP = 5

APP_SUPPORT = pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow"
V2_DB = APP_SUPPORT / "v2.db"
V2_ARTIFACTS = APP_SUPPORT / "v2-artifacts"
V2_BACKUPS = APP_SUPPORT / "v2-evidence" / "backups"
V2_JOURNAL = APP_SUPPORT / "v2-journal"
V2_EVENTS_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow"

# Hands-free (M03, Spec S09): a release shorter than min_duration_sec (a
# tap) followed by a new press within DOUBLE_TAP_SEC starts continuous
# capture; the next tap ends it.
DOUBLE_TAP_SEC = 0.4

FAILED_PILL_SEC = 1.8


class _JobCancelled(Exception):
    """Internal: the user cancelled while this job was in the pipeline."""


def pretty_model_name(model_id: str) -> str:
    last = model_id.split("/")[-1]
    low = last.lower()
    if "parakeet" in low:
        for v in ("v3", "v2", "v1"):
            if v in low:
                return f"Parakeet {v.upper()}"
        return "Parakeet"
    return last


class AppDelegate(NSObject):
    @objc.python_method
    def configure(self, cfg):
        self.cfg = cfg
        self.state = STATE_IDLE
        # V2 observability + store (Spec S07/S08). The event writer and the
        # single-writer store own their own background threads; nothing here
        # touches the audio callback.
        self.v2log = v2.eventlog.EventWriter(
            V2_EVENTS_DIR,
            retention_days=int(cfg.get("events_retention_days", 14)),
            cap_bytes=int(cfg.get("events_cap_mib", 100)) * 1024 * 1024)
        self.store = v2.store.Store(
            V2_DB, artifacts_dir=V2_ARTIFACTS, backup_dir=V2_BACKUPS,
            emit=self.v2log.emit)
        self.store.retention_days = {
            "transcript": int(cfg.get("retention_transcript_days", 30)),
            "audio_success": int(cfg.get("retention_audio_success_days", 7)),
            "audio_failed": int(cfg.get("retention_audio_failed_days", 30)),
            "metadata": int(cfg.get("retention_metadata_days", 14)),
            "training_buffer": int(cfg.get("training_buffer_days", 30)),
        }
        self.v2log.unresolved_jobs_fn = self.store.unresolved_job_ids
        self.consent = v2.training.ConsentManager(self.store, self.v2log.emit)
        self.collector = v2.training.EvidenceCollector(
            self.store, self.v2log.emit, self.consent,
            pipeline_info=lambda: self._pipeline_info())
        self.recorder = Recorder(
            sample_rate=cfg["sample_rate"], input_device=cfg["input_device"],
            notifier=lambda msg: self.v2log.emit(
                "capture.device_fallback", level="WARNING",
                reason_code="input_device_not_found"),
        )
        # M03: the models live in a fresh subprocess, never in this parent
        # (Spec S06). The supervisor spawns/restarts workers and reports
        # engine readiness; it is started lazily so construction alone (as
        # in tests) spawns nothing.
        self.supervisor = WorkerSupervisor(
            audio_root=V2_JOURNAL, asr_model=cfg["model"],
            cleanup_mode=cfg["cleanup"], cleanup_model=cfg["cleanup_model"],
            emit=self.v2log.emit,
            on_engine=lambda engine, state, info:
                AppHelper.callAfter(self._setEngineStatus_, (engine, state)),
        )
        self._asr_revision = v2.ids.resolve_model_revision(cfg["model"])[0]
        self._capability_manifest = v2.capabilities.asr_capability_manifest(
            cfg["model"], model_revision=self._asr_revision,
            runtime=v2.training.runtime_versions())
        # M04 (Spec S10): typed normalization runs in THIS parent process
        # on the coordinator thread — it is deterministic, model-free
        # code, so the worker subprocess (whose whole point is isolating
        # Metal/MLX faults, Spec S06) gains no new protocol op for it.
        # A bad knob or unreadable policy file degrades to stage-off with
        # an event — never a startup crash, never silent re-direction.
        self._norm_policy = None
        try:
            self._norm_policy = v2_normalize.NormalizationPolicy.from_config(
                cfg)
        except Exception as e:
            self.v2log.emit("normalization.policy_invalid", level="WARNING",
                            reason_code=type(e).__name__,
                            outcome="stage_disabled")
        # M05 (Spec S11/S30.1): the scoped dictionary and the Relevant
        # Vocabulary Selector. Legacy terms are adopted and the Claude
        # coding suggestions seeded once (both idempotent). A store
        # failure degrades to vocabulary-off with an event — never a
        # startup crash, never a dropped dictation.
        self._vocab = None
        self._vocab_state_rev = -1
        self._vocab_snapshot = None
        self._hint_selector = None
        self._dict_panel = None
        try:
            self._vocab = v2.vocabulary_store.VocabularyStore(self.store)
            self._vocab.seed_from_legacy_artifacts()
            self._vocab.seed_suggested_coding_terms()
            self._hint_selector = v2.vocabulary.RelevantVocabularySelector(
                max_terms=int(cfg.get("hint_term_limit", 100)))
        except Exception as e:
            self._vocab = None
            self.v2log.emit("vocabulary.store_unavailable", level="WARNING",
                            reason_code=type(e).__name__,
                            outcome="vocabulary_off")
        self._norm_context = None  # per-job vocabulary context (M06 adds
        #                            destination/path fields)
        self.overlay = None
        self.hotkey = None
        self.mouse_trigger = None
        self.status_item = None
        self.model_menu_item = None
        self._training_items = {}
        self._recovery_items = {}
        self._max_timer = None
        # Transcription requests run through the supervisor's serialized
        # GPU queue on one FIFO thread so a new recording can start while
        # the previous dictation is still processing, and pastes still land
        # in dictation order.
        self._jobs = queue.Queue()
        self._active_jobs = []  # queued-but-unfinished, in dictation order
        self._pending = 0  # jobs enqueued but not yet pasted (main thread)
        self._injecting = False  # our own synthetic ⌘V is in flight
        self._dump_seq = 0
        # Current dictation job (minted at hotkey-down per contracts/jobs.md)
        self._job = None
        # Last failed/recoverable dictation for the retry/raw-export menu
        self._last_failed = None
        self._recoverable = []  # crash-recovered items waiting for retry
        # Hands-free double-tap state (off unless cfg hands_free enables it)
        self._hands_free_active = False
        self._tap_pending = None  # {"job": …, "journal": …, "timer": …}
        # Lost-release watchdog: armed per recording only if the press was
        # visible in the session key state, so hardware that doesn't report
        # fn there can never trigger a false recovery.
        self._watchdog_armed = False
        self._lost_ticks = 0
        self._failed_pill_timer = None

    @objc.python_method
    def _vocab_job_state(self):
        """M05: the (policy, context, hint_set) trio a job captures at
        hotkey-down. The snapshot + policy rebuild only when the store's
        revision counter changed; in-flight jobs hold the objects they
        captured, so a rule edit mid-flight changes only future jobs and
        the job keeps its vocabulary revision (AC03). The hint set is
        selected fresh per job from the cached snapshot — frozen before
        decoding, never rebuilt from the answer (S30.1)."""
        policy, context = self._norm_policy, self._norm_context
        hint_set = None
        if self._vocab is not None and policy is not None \
                and policy.profile != "off":
            try:
                rev = self._vocab.revision()
                if rev != self._vocab_state_rev:
                    snapshot = self._vocab.snapshot(None)  # M06 feeds scope
                    self._norm_policy = v2_normalize.NormalizationPolicy(
                        locale=policy.locale, profile=policy.profile,
                        registered_skills=dict(snapshot.skills))
                    self._norm_context = v2_normalize.ContextSnapshot(
                        vocabulary=snapshot, source="m05_vocabulary")
                    self._vocab_snapshot = snapshot
                    self._vocab_state_rev = rev
                policy, context = self._norm_policy, self._norm_context
                if self._hint_selector is not None \
                        and self._vocab_snapshot is not None:
                    hint_set = self._hint_selector.select(
                        self._vocab_snapshot)
            except Exception as e:
                # A vocabulary failure must never disable normalization:
                # keep the last good state and say so.
                self.v2log.emit("vocabulary.refresh_failed", level="WARNING",
                                reason_code=type(e).__name__,
                                outcome="last_good_state")
        return policy, context, hint_set

    @objc.python_method
    def _pipeline_info(self):
        asr_rev, _ = v2.ids.resolve_model_revision(self.cfg["model"])
        clean_rev, _ = v2.ids.resolve_model_revision(self.cfg["cleanup_model"])
        return {
            "source_revision": v2.ids.source_revision(),
            "pipeline_revision": v2.ids.PIPELINE_REVISION,
            "config_hash": v2.ids.config_hash(self.cfg),
            "models": {"asr": self.cfg["model"], "asr_revision": asr_rev,
                       "cleanup": self.cfg["cleanup_model"],
                       "cleanup_revision": clean_rev},
            "runtime": v2.training.runtime_versions(),
            # M04: the normalization policy revision that produced each
            # example's typed edits (S29.4 normalization field family).
            # Absent when the policy failed to load (stage off).
            **({"normalization_policy_revision":
                self._norm_policy.policy_revision}
               if self._norm_policy is not None else {}),
        }

    # ---- lifecycle ----------------------------------------------------

    def applicationDidFinishLaunching_(self, note):
        perms = ensure_permissions(prompt=not os.environ.get("LOCALFLOW_NO_PROMPT"))
        if not perms["accessibility"]:
            self.v2log.emit(
                "app.permissions", level="WARNING",
                reason_code="accessibility_not_trusted",
                detail="the hotkey and paste will not work until enabled in"
                       " System Settings → Privacy & Security → Accessibility")

        self._setup_status_item()

        self.overlay = Overlay.alloc().init()
        self.overlay.setLevelSource_(lambda: self.recorder.level)

        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._start_worker, daemon=True).start()
        threading.Thread(target=self._recover_journals, daemon=True).start()

        self.hotkey = HotkeyListener(
            self.cfg["hotkey"],
            on_press=self.startDictation,
            on_release=self.finishDictation,
            on_other_key=self.cancelDictation,
        )
        self.hotkey.start()
        if self.cfg.get("mouse_trigger"):
            self.mouse_trigger = MouseTriggerListener(
                self.cfg["mouse_trigger"],
                on_press=lambda: self.startDictation(source="mouse"),
                on_release=lambda: self.finishDictation(source="mouse"))
            self.mouse_trigger.start()

        # Sleep/lock end capture with a recoverable item; wake never
        # reopens the microphone by itself (Spec S09).
        ws = NSWorkspace.sharedWorkspace().notificationCenter()
        ws.addObserver_selector_name_object_(
            self, "willSleep:", "NSWorkspaceWillSleepNotification", None)
        ws.addObserver_selector_name_object_(
            self, "didWake:", "NSWorkspaceDidWakeNotification", None)
        ws.addObserver_selector_name_object_(
            self, "sessionResigned:",
            "NSWorkspaceSessionDidResignActiveNotification", None)

        # Periodic wakeup so Python-level signal handlers (Ctrl+C) run,
        # and watchdog against lost hotkey release events
        self._keepalive = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "watchdog:", None, True
        )

        # Retention pass shortly after launch, then daily (Spec S25). The
        # event writer applies its own age/cap pruning on rotation.
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            30.0, self, "retentionPass:", None, False
        )
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            86400.0, self, "retentionPass:", None, True
        )

        key = DISPLAY_NAMES[self.cfg["hotkey"]]
        self.v2log.emit(
            "app.ready", level="INFO", reason_code="shell_interactive",
            config_hash=v2.ids.config_hash(self.cfg),
            detail=f"hold {key} to dictate, release to insert text")

    @objc.python_method
    def _start_worker(self):
        try:
            self.supervisor.ensure_running()
        except WorkerFailure as e:
            self.v2log.emit("worker.start_failed", level="ERROR",
                            reason_code=e.reason_code)

    def applicationWillTerminate_(self, note):
        try:
            self.supervisor.shutdown(timeout=2.0)
        except Exception:
            pass

    def retentionPass_(self, timer):
        # Retention queries can be slow with a large store; never let them
        # stall the main thread (the store serializes them on its writer).
        threading.Thread(target=self._retention_pass, daemon=True).start()

    @objc.python_method
    def _retention_pass(self):
        try:
            self.store.sweep_orphans()
            self.store.prune()
            self.store.prune_training()
            self._sweep_journal_root()
        except Exception as e:
            self.v2log.emit("store.retention_failed", level="ERROR",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _sweep_journal_root(self):
        """Failed/recoverable journal files expire with the audio-failed
        retention knob; resolved jobs already deleted theirs eagerly."""
        days = self.store.retention_days["audio_failed"]
        cutoff = time.time() - days * 86400
        for pattern in ("job-*.blk", "job-*.wav"):
            for p in V2_JOURNAL.glob(pattern):
                try:
                    if p.stat().st_mtime < cutoff:
                        p.unlink()
                except OSError:
                    continue

    # ---- crash recovery (M03-AC03) --------------------------------------

    @objc.python_method
    def _recover_journals(self):
        """Startup scan: unfinished journals become recoverable items with
        every complete block recovered and an honest incomplete-tail flag."""
        found = 0
        for blk in capture_journal.unfinished_journals(V2_JOURNAL):
            try:
                rec = capture_journal.reconstruct(blk)
            except Exception as e:
                self.v2log.emit("capture.recovery_failed", level="ERROR",
                                reason_code=type(e).__name__,
                                detail=blk.name)
                continue
            header = rec.header or {}
            job_id = header.get("job_id") or blk.stem[len("job-"):]
            family_id = header.get("family_id") or v2.ids.new_id("fam")
            stats = rec.stats()
            existing = self.store.job(job_id)
            if existing is None:
                self.store.create_job(
                    job_id=job_id, family_id=family_id,
                    session_id=self.v2log.session_id,
                    boot_id=v2.ids.new_id("boot"),
                    captured_at_utc=header.get("captured_at_utc"),
                    time_quality=header.get("time_quality", "unknown"),
                    state="failed_recoverable",
                    source_revision=v2.ids.source_revision(),
                    pipeline_revision=v2.ids.PIPELINE_REVISION)
            wav = V2_JOURNAL / f"job-{job_id}.wav"
            min_sec = float(self.cfg["min_duration_sec"])
            rate = int(header.get("sample_rate")
                       or self.cfg["sample_rate"])
            recoverable = (rec.samples.size
                           and rec.samples.size / rate >= min_sec)
            if recoverable:
                v2.store.write_wav_f32(wav, rec.samples, rate)
                self._recoverable.append({
                    "job_id": job_id, "family_id": family_id,
                    "wav": str(wav), "raw": None,
                    "attempt": (existing or {}).get("attempt", 1) or 1})
                found += 1
            try:
                blk.unlink()
            except OSError:
                pass
            self._job_state(job_id, "failed_recoverable"
                            if recoverable else "cancelled",
                            reason="app_crash_during_capture"
                            if recoverable else
                            ("crash_below_min_duration" if rec.samples.size
                             else "crash_no_audio_recovered"))
            self.v2log.emit(
                "capture.recovered_after_crash", level="WARNING",
                job_id=job_id, reason_code="journal_reconstruction",
                outcome=("incomplete_tail" if rec.incomplete_tail
                         else "complete") if recoverable
                else "below_min_duration",
                detail=f"blocks={stats['complete_blocks']}"
                       f" samples={stats['sample_count']}"
                       f" torn_bytes={stats['torn_bytes']}")
        # Jobs that finished capture but died before resolution (wav kept,
        # blk already finalized or swept). Only residue from previous boots:
        # a job minted by this live session is mid-flight, not crashed, and
        # must never be terminal-corrupted by this scan.
        for job_id in list(self.store.unresolved_job_ids()):
            row = self.store.job(job_id) or {}
            if row.get("boot_id") == self.v2log.boot_id:
                continue
            wav = V2_JOURNAL / f"job-{job_id}.wav"
            if not wav.exists():
                self._job_state(job_id, "failed_recoverable",
                                reason="app_crash_audio_lost")
                continue
            self._job_state(job_id, "failed_recoverable",
                            reason="app_crash_before_resolution")
            self._recoverable.append({
                "job_id": job_id, "family_id": row.get("family_id"),
                "wav": str(wav), "raw": None,
                "attempt": row.get("attempt", 1) or 1})
            found += 1
        if found:
            AppHelper.callAfter(self._refresh_recovery_menu)

    # ---- engine status ---------------------------------------------------

    def _setEngineStatus_(self, engines):
        _engine, _state = engines
        states = dict(self.supervisor.engine_state)
        self.model_menu_item.setTitle_(
            f"ASR: {states.get('asr', 'not_started')}"
            f" · Cleanup: {states.get('cleanup', 'not_started')}")

    # ---- dictation state machine (all on main thread) ------------------

    def startDictation(self, source="hotkey"):
        if self._hands_free_active:
            # A tap while hands-free ends continuous capture (Spec S09).
            self._hands_free_active = False
            self._finishCapture()
            return
        hands_free = False
        if self._tap_pending is not None:
            # Second tap inside the double-tap window: the short first tap
            # is discarded and continuous capture begins (when enabled).
            pending, self._tap_pending = self._tap_pending, None
            pending["timer"].invalidate()
            self._discard_short(pending["job"])
            if self.cfg.get("hands_free") == "double_tap":
                hands_free = True
        if self.state == STATE_RECORDING:
            return
        # The watchdog polls the trigger that actually started this
        # capture; a mouse-started dictation must not be finished by an
        # idle fn key state (and vice versa). Set only on the press that
        # starts the capture — a cross-trigger press during an active
        # capture returns above and touches nothing.
        self._capture_source = source
        listener = self.mouse_trigger if source == "mouse" else self.hotkey
        self._watchdog_armed = (
            listener is not None and listener.physically_down())
        self._lost_ticks = 0
        # Job first, then capture (Spec S06 ordering): the journal file and
        # every recovery record then carry the minted job identity.
        job_id, family_id = self.store.create_job(
            kind="dictation", session_id=self.v2log.session_id,
            boot_id=self.v2log.boot_id,
            captured_at_utc=v2.ids.now_utc_iso(), time_quality="known",
            timezone=v2.ids.local_zone_name(),
            utc_offset_minutes=v2.ids.utc_offset_minutes(),
            state="capturing", source_revision=v2.ids.source_revision(),
            pipeline_revision=v2.ids.PIPELINE_REVISION)
        journal = None
        try:
            if self.cfg.get("capture_journal", True):
                journal = capture_journal.CaptureJournal(
                    V2_JOURNAL, job_id=job_id, family_id=family_id,
                    sample_rate=self.cfg["sample_rate"],
                    emit=self.v2log.emit,
                    meta={"captured_at_utc": v2.ids.now_utc_iso(),
                          "time_quality": "known"})
                self.recorder.journal = journal
            self.recorder.start()
        except Exception as e:
            self.recorder.journal = None
            if journal is not None:
                journal.close_discard()
            self.v2log.emit("capture.mic_open_failed", level="ERROR",
                            job_id=job_id, reason_code=type(e).__name__)
            self._job_state(job_id, "failed_recoverable",
                            reason="mic_open_failed")
            return
        self._job = {
            "job_id": job_id, "family_id": family_id,
            "captured_at_utc": v2.ids.now_utc_iso(),
            "timezone": v2.ids.local_zone_name(),
            "utc_offset_minutes": v2.ids.utc_offset_minutes(),
            "journal": journal,
            "hands_free": hands_free,
        }
        if hands_free:
            # Releases no longer finish this capture; only a new tap, a
            # cancel, or the duration cap does (Spec S09).
            self._hands_free_active = True
        self.v2log.emit("capture.started", level="INFO", job_id=job_id,
                        outcome="hands_free" if hands_free else None)
        self.state = STATE_RECORDING
        self.overlay.showWithMode_(MODE_RECORDING)
        # M05: freeze the vocabulary policy/context/hint set into the job
        # (pre-decode; edits after this point affect only future jobs,
        # AC03). Runs AFTER the overlay so selector/snapshot work never
        # delays the hotkey-down visible feedback (S06/S24).
        try:
            self._job.update(dict(
                zip(("norm_policy", "norm_context", "hint_set"),
                    self._vocab_job_state())))
        except Exception as e:
            self.v2log.emit("vocabulary.refresh_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)
        if hands_free or float(self.cfg["max_duration_sec"]) > 0:
            cap = (float(self.cfg["max_duration_sec"])
                   if float(self.cfg["max_duration_sec"]) > 0 else 3600.0)
            self._max_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                cap, self, "maxDurationHit:", None, False
            )

    def maxDurationHit_(self, timer):
        if self.state == STATE_RECORDING:
            self._finishCapture()

    def _clear_max_timer(self):
        if self._max_timer is not None:
            self._max_timer.invalidate()
            self._max_timer = None

    def cancelDictation(self):
        if self._injecting:
            return  # keydown was our own synthetic ⌘V, not a user shortcut
        if self.state == STATE_RECORDING:
            self._clear_max_timer()
            self._hands_free_active = False
            job, self._job = self._job, None
            self.recorder.stop()
            if job:
                journal = job.get("journal")
                if journal is not None:
                    journal.close_discard()
                self._job_state(job["job_id"], "cancelled",
                                reason="user_cancelled")
                self.v2log.emit("capture.cancelled", level="INFO",
                                job_id=job["job_id"],
                                reason_code="user_cancelled")
                self._delete_journal_files(job["job_id"])
            self.state = STATE_IDLE
            self._settle_state()
        elif self.state == STATE_PROCESSING and self._active_jobs:
            # Cancel the in-flight dictation: insertion authority is
            # removed immediately; a late worker result is discarded
            # (contracts/jobs.md invariant 3, M03-AC02). The journal files
            # are deleted only after the coordinator finishes with them —
            # unlinking the wav under a live worker would fault a healthy
            # process and burn its one retry.
            job = self._active_jobs[0]
            if not job.get("cancelled"):
                job["cancelled"] = True
                self._job_state(job["job_id"], "cancelled",
                                reason="user_cancelled")
                self.v2log.emit("capture.cancelled", level="INFO",
                                job_id=job["job_id"],
                                reason_code="user_cancelled_while_processing")

    def finishDictation(self, source="hotkey"):
        if self.state != STATE_RECORDING:
            return
        if source != getattr(self, "_capture_source", "hotkey"):
            return  # cross-talk: a release from a trigger that didn't start
            # this capture (fn held while middle-clicking elsewhere, etc.)
        if self._hands_free_active:
            # Releasing the key during hands-free does not stop capture;
            # only a new tap, a cancel, or the duration cap ends it.
            return
        self._finishCapture()

    @objc.python_method
    def _finishCapture(self):
        if self.state != STATE_RECORDING:
            return
        self._clear_max_timer()
        audio = self.recorder.stop()
        duration = len(audio) / float(self.cfg["sample_rate"])
        job, self._job = self._job, None
        if duration < float(self.cfg["min_duration_sec"]):
            if (job is not None and job.get("hands_free") is False
                    and self.cfg.get("hands_free") == "double_tap"
                    and not job.get("from_retry")):
                # Might be the first tap of a double-tap: defer the discard
                # briefly instead of settling immediately.
                self._defer_short_discard(job)
                return
            if job:
                self._discard_short(job)
            else:
                self.state = STATE_IDLE
                self._settle_state()
            return
        s = self.recorder.stats
        if job:
            self.v2log.emit(
                "capture.completed", level="INFO", job_id=job["job_id"],
                duration_ms=round(s["duration_sec"] * 1000, 1),
                detail=f"voiced {s['voiced_pct']:.0f}%, trailing silence "
                       f"{s['trailing_silence_sec']:.1f}s, overflows "
                       f"{s['overflow_blocks']}")
            if s["overflow_blocks"]:
                self.v2log.emit(
                    "capture.overflow", level="WARNING", job_id=job["job_id"],
                    reason_code="input_overflow",
                    detail=f"{s['overflow_blocks']} audio blocks dropped")
            if s["duration_sec"] >= 2 and s["voiced_pct"] < 5:
                self.v2log.emit(
                    "capture.near_silence", level="WARNING",
                    job_id=job["job_id"], reason_code="nearly_silent_recording")
            elif s["duration_sec"] >= 10 and s["trailing_silence_sec"] >= 5:
                self.v2log.emit(
                    "capture.dead_tail", level="WARNING", job_id=job["job_id"],
                    reason_code="no_speech_in_final_seconds",
                    detail=f"last {s['trailing_silence_sec']:.0f}s silent")
            try:
                ctx = self.collector.job_started(
                    job["job_id"], job["family_id"],
                    captured_at_utc=job["captured_at_utc"],
                    timezone=job["timezone"],
                    utc_offset_minutes=job["utc_offset_minutes"])
            except Exception as e:
                self.v2log.emit("training.capture_failed", level="ERROR",
                                job_id=job["job_id"],
                                reason_code=type(e).__name__)
                ctx = None
            # M05 (S30.1): the hint set was frozen at hotkey-down; store
            # it with its disposition BEFORE recognition so the retained
            # set is what was actually offered pre-decode.
            if ctx is not None and job.get("hint_set") is not None:
                job["hint_disposition"] = v2.capabilities.hint_disposition(
                    self._capability_manifest, job["hint_set"])
                try:
                    self.collector.on_hint_set(
                        ctx, job["hint_set"], job["hint_disposition"])
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job["job_id"],
                                    reason_code=type(e).__name__)
            job.update({"audio": audio, "stats": s, "ctx": ctx,
                        "failed": False, "cancelled": False, "attempt": 1,
                        "raw": None, "wav": None})
            self._job_state(job["job_id"], "queued")
            try:
                self.store.set_job_released(job["job_id"])
            except Exception as e:
                self.v2log.emit("store.state_write_failed", level="WARNING",
                                job_id=job["job_id"],
                                reason_code=type(e).__name__)
        else:
            job = {"audio": audio, "stats": s, "ctx": None, "failed": False,
                   "cancelled": False, "attempt": 1, "raw": None, "wav": None,
                   "job_id": None, "family_id": None, "journal": None}
        self._pending += 1
        self._active_jobs.append(job)
        self._jobs.put(job)
        self.state = STATE_PROCESSING
        self.overlay.setMode_(MODE_PROCESSING)

    @objc.python_method
    def _defer_short_discard(self, job):
        job["discard_audio"] = True
        timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            DOUBLE_TAP_SEC, self, "tapWindowExpired:", None, False
        )
        self._tap_pending = {"job": job, "timer": timer}
        self.state = STATE_IDLE
        self.overlay.hide()

    def tapWindowExpired_(self, timer):
        pending, self._tap_pending = self._tap_pending, None
        if pending is not None:
            self._discard_short(pending["job"])

    @objc.python_method
    def _discard_short(self, job):
        """Below-minimum-duration capture: cancelled, journal deleted."""
        if job is None:
            return
        if job.get("job_id"):
            self._job_state(job["job_id"], "cancelled",
                            reason="below_min_duration")
            self.v2log.emit("capture.discarded", level="INFO",
                            job_id=job["job_id"],
                            reason_code="below_min_duration")
        journal = job.get("journal")
        if journal is not None:
            journal.close_discard()
        self.state = STATE_IDLE
        self._settle_state()

    # ---- sleep / lock / device loss ---------------------------------------

    def willSleep_(self, note):
        self._abandon_capture_for_system("system_sleep")

    def sessionResigned_(self, note):
        self._abandon_capture_for_system("session_locked_or_switched")

    def didWake_(self, note):
        # The microphone stays off after wake until the user asks for it
        # (Spec S09): nothing here starts a capture.
        self.v2log.emit(
            "app.woke", level="INFO",
            outcome="mic_off" if not self.recorder.recording else "mic_on",
            reason_code="wake_no_auto_reopen")

    @objc.python_method
    def _abandon_capture_for_system(self, reason):
        """Sleep/lock mid-recording: end capture with a recoverable item —
        the audio is preserved for retry; nothing auto-inserts."""
        if self.state != STATE_RECORDING:
            return
        self._clear_max_timer()
        self._hands_free_active = False
        audio = self.recorder.stop()
        job, self._job = self._job, None
        duration = len(audio) / float(self.cfg["sample_rate"])
        if job is None:
            self.state = STATE_IDLE
            self.overlay.hide()
            return
        if duration < float(self.cfg["min_duration_sec"]):
            self._discard_short(job)
            return
        try:
            wav = self._worker_wav_path(job)
            v2.store.write_wav_f32(pathlib.Path(wav), audio,
                                   int(self.cfg["sample_rate"]))
        except Exception as e:
            self.v2log.emit("capture.recovery_write_failed", level="ERROR",
                            job_id=job["job_id"],
                            reason_code=type(e).__name__)
            wav = None
        self._job_state(job["job_id"], "failed_recoverable", reason=reason)
        self.v2log.emit("capture.system_interrupted", level="WARNING",
                        job_id=job["job_id"], reason_code=reason,
                        outcome="recoverable_item" if wav else "audio_only")
        if wav:
            self._last_failed = {"job_id": job["job_id"],
                                 "family_id": job["family_id"],
                                 "wav": wav, "raw": None,
                                 "attempt": 1}
        self.state = STATE_IDLE
        self.overlay.hide()
        self._refresh_recovery_menu()

    @objc.python_method
    def _worker_wav_path(self, job) -> str:
        if job.get("wav"):
            return job["wav"]
        job_id = job.get("job_id") or v2.ids.new_id("job")
        return str(V2_JOURNAL / f"job-{job_id}.wav")

    # ---- watchdog ---------------------------------------------------------

    def watchdog_(self, timer):
        if self.state == STATE_RECORDING:
            listener = (self.mouse_trigger
                        if getattr(self, "_capture_source", "hotkey")
                        == "mouse" else self.hotkey)
            # Device loss / dead stream: preserve the speech captured so
            # far and finish the dictation with a warning (Spec S09).
            health_fn = getattr(self.recorder, "capture_health", None)
            if health_fn is not None:
                health = health_fn()
                if health.get("ok") is False:
                    # stop() folds this into the capture stats (it rebuilds
                    # them), so stash it on the recorder, not in stats.
                    self.recorder.discontinuity = {
                        "kind": "device_loss",
                        "callback_error": health.get("callback_error"),
                        "device_gone": health.get("device_gone"),
                        "device": health.get("device"),
                    }
                    self.v2log.emit(
                        "capture.device_loss", level="WARNING",
                        job_id=self._job["job_id"] if self._job else None,
                        reason_code=str(health.get("callback_error")
                                        or "device_gone"),
                        outcome="finishing_with_captured_speech")
                    self._finishCapture()
                    return
            if (self._watchdog_armed and not self._hands_free_active
                    and listener is not None
                    and not listener.physically_down()):
                self._lost_ticks += 1
                if self._lost_ticks >= 2:
                    self.v2log.emit(
                        "hotkey.release_lost", level="WARNING",
                        job_id=self._job["job_id"] if self._job else None,
                        reason_code="recovered_from_key_state")
                    self._lost_ticks = 0
                    listener.held = False
                    self._finishCapture()
            else:
                self._lost_ticks = 0
        else:
            self._lost_ticks = 0
            if (
                self._watchdog_armed
                and self.hotkey.held
                and not self.hotkey.physically_down()
            ):
                # A lost release outside RECORDING leaves `held` stuck
                # True, which would eat the next press.
                self.hotkey.held = False

    # ---- inference coordinator (FIFO thread) ------------------------------

    @objc.python_method
    def _worker(self):
        while True:
            job = self._jobs.get()
            if job.get("cancelled"):
                AppHelper.callAfter(self._finishWithText_, "", job)
                continue
            audio, ctx, job_id = job["audio"], job["ctx"], job["job_id"]
            # Observations during this job's cleanup attach to it even if
            # the main thread starts a newer dictation meanwhile.
            if ctx is not None:
                self.collector.bind_current(ctx)
            text = ""
            try:
                if self.cfg["log_transcripts"]:
                    self._dump_audio(audio)
                self._job_state(job_id, "transcribing")
                # Evidence/store work is guarded separately: a capture or
                # disk problem must never fail an otherwise successful
                # dictation (the pipeline stages below have their own try).
                try:
                    if ctx is not None:
                        self.collector.attach_capture_meta(
                            ctx, job["stats"], self.cfg["sample_rate"])
                        # The audio artifact is attached to the job before
                        # model execution.
                        self.collector.on_audio(
                            ctx, audio, self.cfg["sample_rate"], job["stats"])
                        self.store.sync()
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
                # Parent-created audio reference for the worker (Spec S06):
                # a float32 WAV under the parent-owned journal root.
                try:
                    wav = self._worker_wav_path(job)
                    if not job.get("wav"):
                        v2.store.write_wav_f32(
                            pathlib.Path(wav), audio,
                            int(self.cfg["sample_rate"]))
                        job["wav"] = wav
                except Exception as e:
                    self.v2log.emit("capture.worker_audio_failed",
                                    level="ERROR", job_id=job_id,
                                    reason_code=type(e).__name__)
                    raise
                t0 = time.monotonic()
                res = self.supervisor.transcribe(
                    job_id=job_id, attempt=job["attempt"],
                    audio_name=pathlib.Path(wav).name,
                    sample_rate=int(self.cfg["sample_rate"]))
                if res.get("retried") and job_id:
                    self._bump_attempt(job, job_id)
                job["attempt"] = res.get("attempt", job["attempt"])
                if job.get("cancelled"):
                    raise _JobCancelled()
                raw = res.get("text") or ""
                job["raw"] = raw
                asr_ms = res.get("duration_ms")
                self.v2log.emit(
                    "stage.completed", level="INFO", job_id=job_id,
                    attempt=job["attempt"], stage="transcribing",
                    duration_ms=asr_ms, model_id=self.cfg["model"],
                    model_revision=self._asr_revision,
                    worker_generation=res.get("generation"),
                    artifact_ids=([ctx.audio_artifact]
                                  if ctx is not None and ctx.audio_artifact
                                  else None))
                try:
                    if ctx is not None:
                        self.collector.on_asr_result(
                            ctx, raw, model_id=self.cfg["model"],
                            model_revision=self._asr_revision,
                            stage_duration_ms=asr_ms,
                            worker_generation=res.get("generation"),
                            decode_ranges=res.get("decode_ranges"),
                            capabilities=self._capability_manifest[
                                "capabilities"],
                            hint_disposition=job.get("hint_disposition")
                            or v2.capabilities.hint_disposition(
                                self._capability_manifest,
                                job.get("hint_set")))
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
                # M04 (Spec S10): typed normalization between ASR and
                # cleanup, in this process (deterministic, model-free).
                # A normalization bug must never drop a dictation: any
                # exception passes the raw transcript through. The job's
                # own captured policy/context are used (M05 AC03: an
                # in-flight job keeps its vocabulary revision).
                norm_policy = job.get("norm_policy") or self._norm_policy
                norm_context = job.get("norm_context") or self._norm_context
                norm_text = raw
                norm_result = None
                if raw and norm_policy is not None \
                        and norm_policy.profile != "off":
                    self._job_state(job_id, "normalizing")
                    tn = time.monotonic()
                    try:
                        norm_result = v2_normalize.normalize(
                            raw, norm_policy, norm_context)
                        norm_text = norm_result.text
                    except Exception as e:
                        self.v2log.emit(
                            "normalization.failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__,
                            outcome="raw_passthrough")
                    self.v2log.emit(
                        "stage.completed", level="INFO", job_id=job_id,
                        attempt=job["attempt"], stage="normalizing",
                        duration_ms=round(
                            (time.monotonic() - tn) * 1000, 2),
                        outcome=(None if norm_result is None else
                                 f"edits:{len(norm_result.edits)}"
                                 f"/rejected:{len(norm_result.rejected)}"),
                        detail=(None if norm_result is None else
                                norm_result.policy_revision))
                    try:
                        if ctx is not None and norm_result is not None:
                            self.collector.on_normalization_result(
                                ctx, norm_result, source_text=raw,
                                policy=norm_policy,
                                context=norm_context)
                    except Exception as e:
                        self.v2log.emit("training.capture_failed",
                                        level="ERROR", job_id=job_id,
                                        reason_code=type(e).__name__)
                    # M05 (task 5): only applied approved matches count as
                    # usage hits; suggestions never reached the engine.
                    vocab_rules = [e.rule_id for e in norm_result.edits
                                   if e.cls == "vocabulary" and e.rule_id] \
                        if norm_result is not None else []
                    if vocab_rules and self._vocab is not None:
                        try:
                            self._vocab.record_hits(vocab_rules)
                        except Exception as e:
                            self.v2log.emit(
                                "vocabulary.hit_write_failed",
                                level="WARNING", job_id=job_id,
                                reason_code=type(e).__name__)
                job["normalized"] = norm_text
                self._job_state(job_id, "cleaning")
                if raw:
                    if (self.cfg["cleanup"] == "llm"
                            and self.cfg.get("cleanup_not_ready_policy")
                            == "wait"):
                        # Hold the saved job until cleanup is ready/failed
                        # (Spec S09) — the recorded path stays honest either
                        # way (M03-AC04).
                        self.supervisor.wait_engine(
                            "cleanup",
                            float(self.cfg.get("cleanup_wait_timeout_sec",
                                               120)))
                    res2 = self.supervisor.clean(
                        job_id=job_id, attempt=job["attempt"],
                        raw_text=norm_text)
                    if res2.get("retried") and job_id:
                        self._bump_attempt(job, job_id)
                    job["attempt"] = res2.get("attempt", job["attempt"])
                    if job.get("cancelled"):
                        raise _JobCancelled()
                    text = res2.get("text") or ""
                    cleanup_path = res2.get("path")
                    self.v2log.emit(
                        "stage.completed", level="INFO", job_id=job_id,
                        attempt=job["attempt"], stage="cleaning",
                        duration_ms=res2.get("duration_ms"),
                        outcome=cleanup_path,
                        reason_code=res2.get("fallback_reason"),
                        model_id=(self.cfg["cleanup_model"]
                                  if cleanup_path == "llm" else None),
                        worker_generation=res2.get("generation"))
                    try:
                        if ctx is not None:
                            for obs in (res2.get("observations") or []):
                                self.collector.on_cleaner_observation(obs)
                    except Exception as e:
                        self.v2log.emit("training.capture_failed",
                                        level="ERROR", job_id=job_id,
                                        reason_code=type(e).__name__)
                else:
                    text = raw
                    cleanup_path = "raw" if self.cfg["cleanup"] == "off" \
                        else "basic_empty_input"
                try:
                    collecting = ctx is not None and ctx.collecting
                    if ctx is not None:
                        self.collector.on_cleanup_result(
                            ctx, text, path=cleanup_path,
                            fallback_reason=(
                                res2.get("fallback_reason")
                                if raw else None))
                        self.collector.finalize(ctx)
                    if raw and self.cfg["log_transcripts"] and not collecting:
                        # Collection disabled: the user's existing transcript
                        # logging choice still keeps text in the private
                        # store under a history lease (Spec S07).
                        self.store.write_text_artifact(
                            job_id=job_id, stage="asr", role="raw_transcript",
                            text=raw, retention_class="history")
                        if text is not None:
                            self.store.write_text_artifact(
                                job_id=job_id, stage="cleanup",
                                role="applied_output", text=text,
                                retention_class="history",
                                meta={"cleanup_path": cleanup_path})
                    self._job_state(job_id, "ready_to_insert")
                    self.store.sync()
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
            except _JobCancelled:
                job["failed"] = False
                text = ""
                self._note_cancelled_evidence(ctx)
            except WorkerFailure as e:
                if job.get("cancelled"):
                    # The user cancelled while the fault/retry was in
                    # flight: the failure is theirs, not a recoverable item.
                    job["failed"] = False
                    text = ""
                    self._note_cancelled_evidence(ctx)
                else:
                    job["failed"] = True
                    self.v2log.emit("stage.failed", level="ERROR",
                                    job_id=job_id,
                                    attempt=job.get("attempt"),
                                    stage=e.stage or "pipeline",
                                    reason_code=e.reason_code,
                                    outcome="recoverable_item"
                                    if job.get("wav")
                                    else "audio_unrecoverable")
                    self._job_state(
                        job_id,
                        "failed_recoverable" if job.get("wav")
                        else "failed_unrecoverable",
                        reason=f"worker_fault:{e.reason_code}")
                    self._note_failure_evidence(ctx, e.reason_code)
                    self._register_recoverable(job)
                    text = ""
            except Exception as e:
                if job.get("cancelled"):
                    job["failed"] = False
                    text = ""
                    self._note_cancelled_evidence(ctx)
                else:
                    job["failed"] = True
                    self.v2log.emit("stage.failed", level="ERROR",
                                    job_id=job_id,
                                    stage="pipeline",
                                    reason_code=type(e).__name__)
                    self._job_state(
                        job_id,
                        "failed_recoverable" if job.get("wav")
                        else "failed_unrecoverable",
                        reason="worker_exception")
                    self._note_failure_evidence(ctx, type(e).__name__)
                    self._register_recoverable(job)
                    text = ""
            finally:
                self.collector.clear_current()
            AppHelper.callAfter(self._finishWithText_, text, job)

    @objc.python_method
    def _bump_attempt(self, job, job_id):
        job["attempt"] = int(job.get("attempt", 1)) + 1
        try:
            self.store.bump_job_attempt(job_id)
        except Exception as e:
            self.v2log.emit("store.state_write_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)

    @objc.python_method
    def _note_cancelled_evidence(self, ctx):
        try:
            if ctx is not None:
                self.collector.on_failure(ctx, "user_cancelled")
        except Exception:
            pass

    @objc.python_method
    def _note_failure_evidence(self, ctx, error_kind):
        try:
            if ctx is not None:
                self.collector.on_failure(ctx, error_kind)
        except Exception:
            pass

    @objc.python_method
    def _register_recoverable(self, job):
        if not job.get("wav"):
            return
        self._last_failed = {
            "job_id": job.get("job_id"), "family_id": job.get("family_id"),
            "wav": job["wav"], "raw": job.get("raw"),
            "attempt": int(job.get("attempt", 1) or 1)}
        AppHelper.callAfter(self._refresh_recovery_menu)

    @objc.python_method
    def _delete_journal_files(self, job_id):
        if not job_id:
            return
        def _rm():
            for suffix in (".blk", ".wav"):
                try:
                    (V2_JOURNAL / f"job-{job_id}{suffix}").unlink(
                        missing_ok=True)
                except OSError:
                    pass
        threading.Thread(target=_rm, daemon=True).start()

    @objc.python_method
    def _job_state(self, job_id, state, reason=None, retry=False):
        """Persist a job transition without letting a store stall eat the
        dictation (the transition is idempotent, so a skipped write here is
        recorded in events and retried by the next one)."""
        if not job_id:
            return
        try:
            self.store.update_job_state(job_id, state, reason=reason,
                                        retry=retry)
        except Exception as e:
            self.v2log.emit("store.state_write_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)

    @objc.python_method
    def _dump_audio(self, audio):
        try:
            import wave
            AUDIO_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            self._dump_seq += 1
            stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{self._dump_seq:03d}"
            with wave.open(str(AUDIO_DEBUG_DIR / f"dictation-{stamp}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(self.cfg["sample_rate"]))
                w.writeframes(
                    (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
                )
            for old in sorted(AUDIO_DEBUG_DIR.glob("dictation-*.wav"))[:-AUDIO_DEBUG_KEEP]:
                old.unlink()
        except Exception as e:
            self.v2log.emit("capture.debug_audio_failed", level="WARNING",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _finishWithText_(self, text, job):
        self._pending -= 1
        if job in self._active_jobs:
            self._active_jobs.remove(job)
        job_id, ctx = job["job_id"], job["ctx"]
        if job.get("cancelled"):
            # Cancelled mid-processing: whatever the worker returned, it
            # lost insertion authority the moment the user cancelled. The
            # coordinator is done with the wav by now, so the journal files
            # can finally go.
            if job_id:
                self.v2log.emit("insertion.skipped", level="INFO",
                                job_id=job_id,
                                reason_code="user_cancelled")
            self._delete_journal_files(job_id)
            self._settle_state()
            return
        if job.get("failed"):
            self._show_failed_pill()
        elif text:
            if self.cfg["append_space"] and not text.endswith(("\n", " ")):
                text += " "
            # The synthetic ⌘V must not cancel a recording already in
            # progress; the flag is cleared shortly after the event lands.
            self._injecting = True
            try:
                if paste_text(text, restore_clipboard=self.cfg["restore_clipboard"]):
                    # V1 posts Cmd+V and cannot observe the target, so the
                    # outcome is posted_unverified (contracts/targets.md).
                    if job_id:
                        self.v2log.emit(
                            "insertion.posted", level="INFO", job_id=job_id,
                            outcome="posted_unverified",
                            reason_code="v1_target_unobservable",
                            detail=f"{len(text)} chars")
                        self._job_state(job_id, "insertion_posted")
                        self._job_state(job_id, "insertion_unverified",
                                        reason="v1_target_unobservable")
                    if ctx is not None:
                        self.collector.on_insertion(ctx, True, len(text))
                    self._delete_journal_files(job_id)
                else:
                    if job_id:
                        self.v2log.emit(
                            "insertion.saved_not_inserted", level="WARNING",
                            job_id=job_id, outcome="saved_not_inserted",
                            reason_code="accessibility_not_trusted",
                            detail="transcript left on the clipboard for a"
                                   " manual ⌘V")
                        self._job_state(job_id, "saved_not_inserted",
                                        reason="accessibility_not_trusted")
                    if ctx is not None:
                        self.collector.on_insertion(ctx, False, 0)
            finally:
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    0.25, self, "clearInjecting:", None, False
                )
        else:
            if job_id:
                self.v2log.emit("insertion.skipped", level="INFO",
                                job_id=job_id,
                                reason_code=(
                                    "cleanup_emptied_output"
                                    if job.get("raw")
                                    else "empty_transcription"))
                self._job_state(job_id, "saved_not_inserted",
                                reason="cleanup_emptied_output"
                                if job.get("raw")
                                else "empty_transcription")
            if ctx is not None:
                try:
                    self.collector.on_insertion(ctx, False, 0)
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
            self._delete_journal_files(job_id)
        if job.get("failed"):
            # The failed pill stays up briefly; its timer settles the state
            # machine so the failure is actually visible.
            return
        self._settle_state()

    def _show_failed_pill(self):
        try:
            self.overlay.setMode_(MODE_FAILED)
            self._failed_pill_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                FAILED_PILL_SEC, self, "failedPillDone:", None, False
            )
        except Exception:
            pass

    def failedPillDone_(self, timer):
        self._settle_state()

    def _settle_state(self):
        """After a recording or paste ends, fall back to the right state."""
        if self.state == STATE_RECORDING:
            return
        if self._pending > 0:
            self.state = STATE_PROCESSING
            self.overlay.showWithMode_(MODE_PROCESSING)
        else:
            self.state = STATE_IDLE
            self.overlay.hide()

    def clearInjecting_(self, timer):
        self._injecting = False

    # ---- menu ------------------------------------------------------------

    def _setup_status_item(self):
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSSquareStatusItemLength
        )
        button = self.status_item.button()
        icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "waveform", "LocalFlow"
        )
        if icon is not None:
            icon.setTemplate_(True)
            icon.setSize_((18.0, 18.0))
            button.setImage_(icon)
        else:
            button.setTitle_("〜")
        self.status_item.setVisible_(True)

        menu = NSMenu.alloc().init()
        key = DISPLAY_NAMES[self.cfg["hotkey"]]
        title_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"LocalFlow — hold {key} to dictate", None, ""
        )
        title_item.setEnabled_(False)
        menu.addItem_(title_item)

        self.model_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "ASR: not_started · Cleanup: not_started", None, ""
        )
        self.model_menu_item.setEnabled_(False)
        menu.addItem_(self.model_menu_item)

        # Minimal training-evidence controls (Spec S29.2, M02): collection
        # is opt-in, one persistent choice; nothing is collected until the
        # user turns it on here.
        training = NSMenu.alloc().init()
        for title, action in (
            ("Collect Training Evidence", "toggleTrainingCollection:"),
            ("Pause Collection", "toggleTrainingPause:"),
            ("Exclude Last Dictation", "excludeLastDictation:"),
            ("Mark Last Dictation Correct", "markLastCorrect:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, ""
            )
            item.setTarget_(self)
            training.addItem_(item)
            self._training_items[action.rstrip(":")] = item
        training_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Training", None, ""
        )
        training_item.setSubmenu_(training)
        menu.addItem_(training_item)

        # Recovery actions (Spec S09 / M03): after a fault exhausted its
        # automatic retry, the job is preserved here for a manual retry or
        # a raw export — never an infinite restart loop.
        recovery = NSMenu.alloc().init()
        for title, action in (
            ("Retry Last Failed Dictation", "retryLastFailed:"),
            ("Copy Raw Transcript of Last Failure", "copyLastRaw:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, ""
            )
            item.setTarget_(self)
            recovery.addItem_(item)
            self._recovery_items[action.rstrip(":")] = item
        recovery_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Recovery", None, ""
        )
        recovery_item.setSubmenu_(recovery)
        menu.addItem_(recovery_item)
        self._refresh_recovery_menu()

        # Dictionary management (Spec S11, M05): the management panel
        # (search, aliases, scopes, approval, conflict preview, phrase
        # sandbox) plus bulk JSON import/export.
        dictionary = NSMenu.alloc().init()
        for title, action in (
            ("Dictionary…", "openDictionaryPanel:"),
            ("Import Dictionary JSON…", "importDictionaryJSON:"),
            ("Export Dictionary JSON…", "exportDictionaryJSON:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, ""
            )
            item.setTarget_(self)
            dictionary.addItem_(item)
        dictionary_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Dictionary", None, ""
        )
        dictionary_item.setSubmenu_(dictionary)
        menu.addItem_(dictionary_item)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit LocalFlow", "terminate:", "q"
        )
        menu.addItem_(quit_item)
        self.status_item.setMenu_(menu)

    @objc.python_method
    def _refresh_training_menu(self):
        state = self.consent.state()
        collect = self._training_items.get("toggleTrainingCollection")
        pause = self._training_items.get("toggleTrainingPause")
        if collect is not None:
            collect.setTitle_("Collect Training Evidence"
                              + ("  ✓" if state == "enabled" else ""))
        if pause is not None:
            pause.setTitle_("Pause Collection" + ("  ✓" if state == "paused" else ""))
            pause.setEnabled_(state != "disabled")

    def toggleTrainingCollection_(self, sender):
        new = "disabled" if self.consent.state() == "enabled" else "enabled"
        self.consent.set(new, note="menu toggle")
        self._refresh_training_menu()

    def toggleTrainingPause_(self, sender):
        state = self.consent.state()
        new = "paused" if state == "enabled" else (
            "enabled" if state == "paused" else state)
        if new != state:
            self.consent.set(new, note="menu toggle")
        self._refresh_training_menu()

    def excludeLastDictation_(self, sender):
        self.collector.exclude_last()

    def markLastCorrect_(self, sender):
        self.collector.mark_last_correct()

    # ---- Dictionary management (Spec S11, M05) ---------------------------

    def openDictionaryPanel_(self, sender):
        if self._vocab is None:
            return
        try:
            if self._dict_panel is None:
                from .v2 import dictionary_panel
                self._dict_panel = \
                    dictionary_panel.DictionaryPanelController.alloc(
                    ).initWithVocabularyStore_(self._vocab)
            self._dict_panel.showWindow_(sender)
        except Exception as e:
            self.v2log.emit("vocabulary.panel_failed", level="WARNING",
                            reason_code=type(e).__name__)

    def importDictionaryJSON_(self, sender):
        if self._vocab is None:
            return
        from AppKit import NSOpenPanel
        panel = NSOpenPanel.openPanel()
        panel.setAllowedFileTypes_(["json"])
        panel.setCanChooseDirectories_(False)
        if panel.runModal() != 1 or panel.URLs() is None or not panel.URLs():
            return
        path = panel.URLs()[0].path()
        try:
            result = self._vocab.import_json(path)
            self.v2log.emit(
                "vocabulary.imported", level="INFO",
                detail=f"created {result['created']}, updated"
                       f" {result['updated']}, unchanged"
                       f" {result['unchanged']}")
        except Exception as e:
            self.v2log.emit("vocabulary.import_failed", level="WARNING",
                            reason_code=type(e).__name__)

    def exportDictionaryJSON_(self, sender):
        if self._vocab is None:
            return
        from AppKit import NSSavePanel
        panel = NSSavePanel.savePanel()
        panel.setAllowedFileTypes_(["json"])
        if panel.runModal() != 1 or panel.URL() is None:
            return
        path = panel.URL().path()
        try:
            doc = self._vocab.export_json()
            pathlib.Path(path).write_text(
                json.dumps(doc, ensure_ascii=False, indent=1),
                encoding="utf-8")
            self.v2log.emit(
                "vocabulary.exported", level="INFO",
                detail=f"{len(doc['entries'])} entries")
        except Exception as e:
            self.v2log.emit("vocabulary.export_failed", level="WARNING",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _refresh_recovery_menu(self):
        item = self._recovery_items.get("retryLastFailed")
        raw_item = self._recovery_items.get("copyLastRaw")
        has = self._last_failed is not None or bool(self._recoverable)
        if item is not None:
            item.setEnabled_(has)
        if raw_item is not None:
            raw_item.setEnabled_(
                bool(self._last_failed and self._last_failed.get("raw")))

    def retryLastFailed_(self, sender):
        if self.state == STATE_RECORDING:
            return  # never clobber an active capture from the menu
        info = self._last_failed
        if info is None and self._recoverable:
            info = self._recoverable[-1]
        if info is None:
            return
        if self.supervisor.supervisor_state == "failed":
            # An explicit user action re-arms the breaker (M03-AC01: the
            # automatic loop stops; recovery is manual from here).
            try:
                self.supervisor.restart()
            except WorkerFailure as e:
                self.v2log.emit("worker.manual_restart_failed", level="ERROR",
                                reason_code=e.reason_code)
                return
        try:
            _arr, _rate = v2.store.read_wav_f32(pathlib.Path(info["wav"]))
        except Exception as e:
            self.v2log.emit("dictation.retry_failed", level="ERROR",
                            job_id=info.get("job_id"),
                            reason_code=type(e).__name__)
            return
        attempt = int(info.get("attempt", 1) or 1) + 1
        job_id = info.get("job_id")
        family_id = info.get("family_id")
        if job_id:
            self.store.bump_job_attempt(job_id)
            self._job_state(job_id, "queued", reason="user_retry",
                            retry=True)
        try:
            ctx = self.collector.job_started(
                job_id, family_id,
                captured_at_utc=v2.ids.now_utc_iso(),
                timezone=v2.ids.local_zone_name(),
                utc_offset_minutes=v2.ids.utc_offset_minutes(),
                attempt=attempt)
        except Exception:
            ctx = None
        job = {"job_id": job_id, "family_id": family_id, "ctx": ctx,
               "failed": False, "cancelled": False, "attempt": attempt,
               "raw": None, "wav": info["wav"], "journal": None,
               "from_retry": True,
               "audio": _arr,
               "stats": {"device": "recovered", "duration_sec":
                         len(_arr) / float(self.cfg["sample_rate"]),
                         "voiced_pct": None, "trailing_silence_sec": None,
                         "overflow_blocks": None}}
        self.v2log.emit("dictation.retry_started", level="INFO",
                        job_id=job_id, attempt=attempt,
                        reason_code="user_retry")
        if info in self._recoverable:
            self._recoverable.remove(info)
        else:
            self._last_failed = None
        self._refresh_recovery_menu()
        self._pending += 1
        self._active_jobs.append(job)
        self._jobs.put(job)
        self.state = STATE_PROCESSING
        self.overlay.showWithMode_(MODE_PROCESSING)

    def copyLastRaw_(self, sender):
        info = self._last_failed
        if info is None or not info.get("raw"):
            return
        copy_text(info["raw"])
        self.v2log.emit("dictation.raw_exported", level="INFO",
                        job_id=info.get("job_id"),
                        reason_code="user_action",
                        detail=f"{len(info['raw'])} chars")


def main():
    cfg = config_mod.load()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    delegate = AppDelegate.alloc().init()
    delegate.configure(cfg)
    app.setDelegate_(delegate)

    signal.signal(signal.SIGINT, lambda *_: AppHelper.callAfter(app.terminate_, None))
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
