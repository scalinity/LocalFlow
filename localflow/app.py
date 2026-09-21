"""LocalFlow app shell: menu bar item, state machine, and wiring."""

import os
import pathlib
import queue
import signal
import threading
import time
import wave

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
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from . import config as config_mod
from . import v2
from .audio import Recorder
from .cleanup import TranscriptCleaner
from .hotkey import DISPLAY_NAMES, HotkeyListener
from .inject import paste_text
from .overlay import MODE_PROCESSING, MODE_RECORDING, Overlay
from .permissions import ensure_permissions
from .stt import Transcriber

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
V2_EVENTS_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow"


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
        self.transcriber = Transcriber(cfg["model"])
        self._asr_revision = v2.ids.resolve_model_revision(cfg["model"])[0]
        self.cleaner = TranscriptCleaner(
            cfg["cleanup"], cfg["cleanup_model"],
            notifier=lambda msg, level="INFO": self.v2log.emit(
                f"cleanup.{msg}", level=level),
            observer=self.collector.on_cleaner_observation)
        self.overlay = None
        self.hotkey = None
        self.status_item = None
        self.model_menu_item = None
        self._training_items = {}
        self._max_timer = None
        # Transcription runs on one FIFO worker so a new recording can
        # start while the previous dictation is still processing, and
        # pastes still land in dictation order.
        self._jobs = queue.Queue()
        self._pending = 0  # jobs enqueued but not yet pasted (main thread)
        self._injecting = False  # our own synthetic ⌘V is in flight
        self._dump_seq = 0
        # Current dictation job (minted at hotkey-down per contracts/jobs.md)
        self._job = None
        # Lost-release watchdog: armed per recording only if the press was
        # visible in the session key state, so hardware that doesn't report
        # fn there can never trigger a false recovery.
        self._watchdog_armed = False
        self._lost_ticks = 0

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

        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

        self.hotkey = HotkeyListener(
            self.cfg["hotkey"],
            on_press=self.startDictation,
            on_release=self.finishDictation,
            on_other_key=self.cancelDictation,
        )
        self.hotkey.start()

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

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            3.0, self, "statusDebug:", None, False
        )

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
        except Exception as e:
            self.v2log.emit("store.retention_failed", level="ERROR",
                            reason_code=type(e).__name__)

    def statusDebug_(self, timer):
        item = self.status_item
        w = item.button().window() if item.button() else None
        self.v2log.emit(
            "app.status_item", level="DEBUG",
            detail=f"visible={bool(item.isVisible())} "
                   f"windowNumber={w.windowNumber() if w else None} "
                   f"screen={'yes' if (w and w.screen()) else 'no'}"
        )

    def watchdog_(self, timer):
        # macOS sometimes never delivers the hotkey release flagsChanged
        # (seen when fn is tapped while a transcription is finishing).
        # Without recovery that traps the state machine in RECORDING —
        # _settle_state no-ops forever and the overlay never hides. Check
        # the real key state and finish the dictation ourselves. Only
        # armed when the press itself was visible in the session state,
        # so hardware where fn never reports there is unaffected.
        if self.state == STATE_RECORDING:
            if self._watchdog_armed and not self.hotkey.physically_down():
                self._lost_ticks += 1
                if self._lost_ticks >= 2:
                    self.v2log.emit(
                        "hotkey.release_lost", level="WARNING",
                        job_id=self._job["job_id"] if self._job else None,
                        reason_code="recovered_from_key_state")
                    self._lost_ticks = 0
                    self.hotkey.held = False
                    self.finishDictation()
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
            f"Model: {pretty_model_name(self.cfg['model'])} (loading…)", None, ""
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
                title, action, "")
            item.setTarget_(self)
            training.addItem_(item)
            self._training_items[action.rstrip(":")] = item
        training_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Training", None, "")
        training_item.setSubmenu_(training)
        menu.addItem_(training_item)
        self._refresh_training_menu()

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

    def _load_model(self):
        from .stt import _model_cached

        # Go fully offline when everything needed is already on disk.
        # Must happen before huggingface_hub gets imported by the loaders.
        needed = [self.cfg["model"]]
        if self.cfg["cleanup"] == "llm":
            needed.append(self.cfg["cleanup_model"])
        if all(_model_cached(m) for m in needed):
            os.environ.setdefault("HF_HUB_OFFLINE", "1")

        try:
            with v2.eventlog.capture_stderr(self.v2log):
                self.transcriber.load()
            status = "ready"
        except Exception as e:
            status = f"FAILED: {e}"
        AppHelper.callAfter(self._setModelStatus_, status)
        with v2.eventlog.capture_stderr(self.v2log):
            self.cleaner.load()

    def _setModelStatus_(self, status):
        name = pretty_model_name(self.cfg["model"])
        if status == "ready":
            self.model_menu_item.setTitle_(f"Model: {name}")
            self.v2log.emit("model.loaded", level="INFO",
                            model_id=self.cfg["model"])
        else:
            self.model_menu_item.setTitle_(f"Model: {name} ({status})")
            self.v2log.emit("model.load_failed", level="ERROR",
                            model_id=self.cfg["model"], outcome=status,
                            reason_code="asr_load_error")

    # ---- dictation state machine (all on main thread) ------------------

    def startDictation(self):
        self._watchdog_armed = self.hotkey.physically_down()
        self._lost_ticks = 0
        if self.state == STATE_RECORDING:
            return
        try:
            self.recorder.start()
        except Exception as e:
            self.v2log.emit("capture.mic_open_failed", level="ERROR",
                            reason_code=type(e).__name__)
            return
        job_id, family_id = self.store.create_job(
            kind="dictation", session_id=self.v2log.session_id,
            boot_id=self.v2log.boot_id,
            captured_at_utc=v2.ids.now_utc_iso(), time_quality="known",
            timezone=v2.ids.local_zone_name(),
            utc_offset_minutes=v2.ids.utc_offset_minutes(),
            state="capturing", source_revision=v2.ids.source_revision(),
            pipeline_revision=v2.ids.PIPELINE_REVISION)
        self._job = {
            "job_id": job_id, "family_id": family_id,
            "captured_at_utc": v2.ids.now_utc_iso(),
            "timezone": v2.ids.local_zone_name(),
            "utc_offset_minutes": v2.ids.utc_offset_minutes(),
        }
        self.v2log.emit("capture.started", level="INFO", job_id=job_id)
        self.state = STATE_RECORDING
        self.overlay.showWithMode_(MODE_RECORDING)
        if float(self.cfg["max_duration_sec"]) > 0:
            self._max_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                float(self.cfg["max_duration_sec"]), self, "maxDurationHit:", None, False
            )

    def maxDurationHit_(self, timer):
        if self.state == STATE_RECORDING:
            self.finishDictation()

    def _clear_max_timer(self):
        if self._max_timer is not None:
            self._max_timer.invalidate()
            self._max_timer = None

    def cancelDictation(self):
        if self._injecting:
            return  # keydown was our own synthetic ⌘V, not a user shortcut
        if self.state != STATE_RECORDING:
            return
        self._clear_max_timer()
        job, self._job = self._job, None
        self.recorder.stop()
        if job:
            self._job_state(job["job_id"], "cancelled",
                            reason="user_cancelled")
            self.v2log.emit("capture.cancelled", level="INFO",
                            job_id=job["job_id"], reason_code="user_cancelled")
        self.state = STATE_IDLE
        self._settle_state()

    def finishDictation(self):
        if self.state != STATE_RECORDING:
            return
        self._clear_max_timer()
        audio = self.recorder.stop()
        duration = len(audio) / float(self.cfg["sample_rate"])
        job, self._job = self._job, None
        if duration < float(self.cfg["min_duration_sec"]):
            if job:
                self._job_state(job["job_id"], "cancelled",
                                reason="below_min_duration")
                self.v2log.emit("capture.discarded", level="INFO",
                                job_id=job["job_id"],
                                reason_code="below_min_duration",
                                duration_ms=round(duration * 1000, 1))
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
            job.update({"audio": audio, "stats": s, "ctx": ctx, "failed": False})
            self._job_state(job["job_id"], "queued")
            try:
                self.store.set_job_released(job["job_id"])
            except Exception as e:
                self.v2log.emit("store.state_write_failed", level="WARNING",
                                job_id=job["job_id"],
                                reason_code=type(e).__name__)
        else:
            job = {"audio": audio, "stats": s, "ctx": None, "failed": False,
                   "job_id": None, "family_id": None}
        self._pending += 1
        self._jobs.put(job)
        self.state = STATE_PROCESSING
        self.overlay.setMode_(MODE_PROCESSING)

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

    @objc.python_method
    def _worker(self):
        while True:
            job = self._jobs.get()
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
                        # Task 7: the audio artifact is attached to the job
                        # before model execution.
                        self.collector.on_audio(
                            ctx, audio, self.cfg["sample_rate"], job["stats"])
                        self.store.sync()
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
                t0 = time.monotonic()
                raw = self.transcriber.transcribe(audio)
                t1 = time.monotonic()
                asr_ms = round((t1 - t0) * 1000, 1)
                self.v2log.emit(
                    "stage.completed", level="INFO", job_id=job_id,
                    stage="transcribing", duration_ms=asr_ms,
                    model_id=self.cfg["model"],
                    model_revision=self._asr_revision,
                    artifact_ids=([ctx.audio_artifact]
                                  if ctx is not None and ctx.audio_artifact
                                  else None))
                try:
                    if ctx is not None:
                        self.collector.on_asr_result(
                            ctx, raw, model_id=self.cfg["model"],
                            model_revision=self._asr_revision,
                            stage_duration_ms=asr_ms)
                        self._job_state(job_id, "cleaning")
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
                text = self.cleaner.clean(raw) if raw else raw
                t2 = time.monotonic()
                self.v2log.emit(
                    "stage.completed", level="INFO", job_id=job_id,
                    stage="cleaning", duration_ms=round((t2 - t1) * 1000, 1),
                    model_id=(self.cfg["cleanup_model"]
                              if self.cfg["cleanup"] == "llm" else None))
                try:
                    collecting = ctx is not None and ctx.collecting
                    if ctx is not None:
                        self.collector.on_cleanup_result(ctx, text)
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
                                retention_class="history")
                    self._job_state(job_id, "ready_to_insert")
                    self.store.sync()
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
            except Exception as e:
                job["failed"] = True
                self.v2log.emit("stage.failed", level="ERROR", job_id=job_id,
                                stage="pipeline", reason_code=type(e).__name__)
                self._job_state(job_id, "failed_recoverable",
                                reason="worker_exception")
                try:
                    if ctx is not None:
                        self.collector.on_failure(ctx, type(e).__name__)
                except Exception:
                    pass
                text = ""
            finally:
                self.collector.clear_current()
            AppHelper.callAfter(self._finishWithText_, text, job)

    @objc.python_method
    def _job_state(self, job_id, state, reason=None):
        """Persist a job transition without letting a store stall eat the
        dictation (the transition is idempotent, so a skipped write here is
        recorded in events and retried by the next one)."""
        if not job_id:
            return
        try:
            self.store.update_job_state(job_id, state, reason=reason)
        except Exception as e:
            self.v2log.emit("store.state_write_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)

    @objc.python_method
    def _dump_audio(self, audio):
        try:
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
        job_id, ctx = job["job_id"], job["ctx"]
        if job.get("failed"):
            pass  # failure already emitted and state recorded in the worker
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
                                job_id=job_id, reason_code="empty_transcription")
                self._job_state(job_id, "saved_not_inserted",
                                reason="empty_transcription")
            if ctx is not None:
                try:
                    self.collector.on_insertion(ctx, False, 0)
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
        self._settle_state()

    def clearInjecting_(self, timer):
        self._injecting = False


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
