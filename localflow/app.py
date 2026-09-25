"""LocalFlow app shell: menu bar item, state machine, and wiring.

M03: model inference (ASR + cleanup) moved into a fresh subprocess owned by
``localflow.v2.supervisor`` (Spec S06/S09). This parent process holds no
MLX/Metal state; it alone owns capture, targets and insertion authority.
Capture blocks journal to disk off the audio callback
(``localflow.v2.capture_journal``) so a crash mid-dictation recovers every
complete block with an honest incomplete-tail flag.
"""

import dataclasses
import json
import os
import pathlib
import queue
import signal
import threading
import time

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
from .v2 import context as v2_context
from .v2 import profiles as v2_profiles
from .v2 import profiles_store as v2_profiles_store
from .v2 import snippets_store as v2_snippets_store
from .v2 import transforms as v2_transforms
from .v2 import transforms_store as v2_transforms_store
from .v2 import notes as v2_notes
from .v2 import note_export as v2_note_export
from .v2 import snippets as v2_snippets
from .v2.developer import file_tags as v2_file_tags
from .v2.developer import skills as v2_skills
from .audio import Recorder
from .hotkey import DISPLAY_NAMES, HotkeyListener, MouseTriggerListener
from .inject import copy_text
from .overlay import MODE_FAILED, MODE_PROCESSING, MODE_RECORDING, \
    MODE_TRANSFORMING, Overlay
from .permissions import ensure_permissions
from .v2 import capture_journal
from .v2 import debug_audio as v2_debug_audio
from .v2 import cleanup as v2_cleanup
from .v2 import insertion as v2_insertion
from .v2 import normalize as v2_normalize
from .v2.insertion import hosts as v2_insertion_hosts
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

# M03 remediation: the capture-provenance sidecar written next to a job's
# recovery audio (content-free: timing, rate, sample counts, completeness).
PROVENANCE_VERSION = 1
PROVENANCE_SUFFIX = ".capture.json"
_TERMINAL = {"insertion_confirmed", "insertion_unverified",
             "saved_not_inserted", "cancelled", "failed_recoverable",
             "failed_unrecoverable"}
# Resolved states whose leftover journal was already consumed or
# abandoned by the user: the residue is removed, never re-offered.
_CONSUMED = {"insertion_confirmed", "insertion_unverified", "cancelled"}


def _acquire_root_lock(root):
    """Process-level ownership of the journal root (M03-AUDIT-01): only
    the process holding it may treat files there as another boot's crash
    residue. Returns the held descriptor, or None when another live
    process owns the root (its lock dies with it)."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover
        return None
    try:
        root = pathlib.Path(root)
        root.mkdir(parents=True, exist_ok=True)
        fd = os.open(root / ".owner.lock", os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


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
        # M02-AUDIT-19: retention knobs pass one validation layer — an
        # invalid value falls back to its default and is reported, never
        # a startup crash or a destructive (zero/negative) window.
        event_policy, event_problems = config_mod.event_retention_policy(cfg)
        self.v2log = v2.eventlog.EventWriter(
            V2_EVENTS_DIR,
            retention_days=event_policy["events_retention_days"],
            cap_bytes=event_policy["events_cap_mib"] * 1024 * 1024)
        self.store = v2.store.Store(
            V2_DB, artifacts_dir=V2_ARTIFACTS, backup_dir=V2_BACKUPS,
            emit=self.v2log.emit)
        retention, problems = config_mod.retention_policy(cfg)
        self.store.retention_days = retention
        for key, reason in event_problems + problems:
            self.v2log.emit("config.retention_invalid", level="WARNING",
                            reason_code=reason, outcome="default_used",
                            detail=key)
        # M02-AUDIT-02: job-scoped payload copies outside v2-artifacts
        # that delete-everywhere must also remove — the transcript-
        # logging debug WAV (named by job) and the recovery journal.
        self.store.register_job_payload_dir(
            AUDIO_DEBUG_DIR, v2_debug_audio.job_pattern)
        self.store.register_job_payload_dir(
            V2_JOURNAL, lambda job_id: f"job-{job_id}.*")
        # M03-AUDIT-02: delete-everywhere revokes this process's in-memory
        # authority (queued work, cached output, recovery items) inside the
        # same serialized store op that creates the barrier.
        self._deleted_jobs = set()
        self.store.add_job_deletion_listener(self._on_job_deleted)
        # M03-AUDIT-04: app admission (capture, retry, recovery) closes
        # once at quit; M03-AUDIT-01: journal-root ownership.
        self._closing = False
        self._coordinator_thread = None
        self._journal_root_lock = _acquire_root_lock(V2_JOURNAL)
        # M13 (Spec S08/S21, contracts/analytics.md): usage analytics —
        # dated facts over the single-writer store, independent of
        # training consent (usage metadata, not evidence). Guarded like
        # every other service: an analytics failure never touches the
        # dictation path.
        self._analytics = None
        self._insights = None
        try:
            self._analytics = v2.analytics.AnalyticsStore(
                self.store, emit=self.v2log.emit,
                reporting_timezone=v2.analytics.resolve_reporting_zone(
                    cfg.get("analytics_timezone") or None))
            self._insights = v2.analytics.InsightsQueryService(
                self.store, self._analytics)
        except Exception as e:
            self.v2log.emit("analytics.store_unavailable", level="WARNING",
                            reason_code=type(e).__name__,
                            outcome="analytics_off")
        try:
            # A changed analytics_timezone (or an aggregate table left
            # at an older algorithm version) re-buckets every fact's
            # day and rebuilds the aggregates at launch (versioned
            # recomputation) — day boundaries follow the selected
            # reporting zone (S21), and the table holds exactly one
            # zone/version's arithmetic.
            if self._analytics is not None:
                stored_zone, stored_version = self.store.submit(
                    lambda db: (
                        db.execute("SELECT DISTINCT reporting_timezone"
                                   " FROM usage_facts LIMIT 1").fetchone(),
                        db.execute("SELECT MAX(algorithm_version) FROM"
                                   " daily_aggregates").fetchone()))
                if (stored_zone and stored_zone[0] !=
                        self._analytics.reporting_timezone) or \
                        (stored_version and stored_version[0] !=
                            v2.analytics.ALGORITHM_VERSION):
                    self._analytics.rebuild_aggregates()
        except Exception as e:
            self.v2log.emit("analytics.zone_rebuild_failed",
                            level="WARNING", reason_code=type(e).__name__)
        self.v2log.unresolved_jobs_fn = self.store.unresolved_job_ids
        self.consent = v2.training.ConsentManager(self.store, self.v2log.emit)
        try:
            # Prime the capture-boundary snapshot once, off the hotkey path.
            self.consent.snapshot_now(point="startup")
        except Exception as e:
            self.v2log.emit("training.consent_snapshot_failed",
                            level="WARNING", reason_code=type(e).__name__)
        self.collector = v2.training.EvidenceCollector(
            self.store, self.v2log.emit, self.consent,
            pipeline_info=lambda: self._pipeline_info(),
            retain_context=bool(cfg.get("training_retain_context", True)))
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
            cleanup_implementation=cfg.get("cleanup_implementation", "v2"),
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
        self._vocab_state_key = None
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
        # M10 (Spec S15/S17): destination style rules, snippets and the
        # developer registries. Store failures degrade to M10-off with
        # an event — dictation never depends on these services (the
        # writing profile then resolves against zero rules: Clean, the
        # shipped default).
        self._styles = None
        self._style_rules = []
        self._style_state_key = None
        self._snip_store = None
        self._snippet_snapshot = None
        self._snippet_state_key = None
        self._skill_manifest_paths = tuple(
            cfg.get("skill_manifest_paths") or ())
        self._workspace_skill_dirs = tuple(
            cfg.get("workspace_skill_dirs") or ())
        self._dev_listing = bool(
            cfg.get("developer_workspace_listing", True))
        self._skill_records = []
        self._skill_cache_key = None
        self._last_file_resolver = None
        self._last_wp = None       # last resolved profile (Hub panel)
        self._last_skill_workspace = None  # stale-workspace provenance
        self._last_ws_skills = False    # last finalized set had ws skills
        self._next_job_mode = None  # the S15 one-job override
        # M11 (Spec S16): transform definitions and executors. The
        # store seeds the built-ins and materializes the legacy V1
        # definitions as preserved revisions once; failures degrade to
        # transforms-off with an event — dictation never depends on
        # this service (transform-backed modes then resolve with the
        # honest auto-apply-disabled fallback: Clean).
        self._tf_store = None
        self._tf_snapshot = None
        self._tf_state_key = None
        self._tf_panel = None       # the M11 transform preview panel
        self._tf_active = None      # in-flight selection transform state
        try:
            self._tf_store = v2_transforms_store.TransformStore(self.store)
            self._tf_store.seed_built_ins()
            self._tf_store.materialize_legacy()
        except Exception as e:
            self._tf_store = None
            self.v2log.emit("transforms.store_unavailable",
                            level="WARNING", reason_code=type(e).__name__,
                            outcome="transforms_off")
        # M12 (Spec S20): the Scratchpad note workspace. A note-store
        # failure degrades to the Scratchpad view reporting
        # notes_unavailable — dictation never depends on it.
        self._notes_store = None
        try:
            self._notes_store = v2_notes.NoteStore(
                self.store,
                on_evidence=self.collector.on_note_revision)
        except Exception as e:
            self._notes_store = None
            self.v2log.emit("notes.store_unavailable", level="WARNING",
                            reason_code=type(e).__name__,
                            outcome="scratchpad_off")
        # M14 (Spec S22/S29.7–S29.13): correction learning, curation and
        # the Your Voice profile. All store-backed services degrade to
        # None with an event — dictation never depends on any of them,
        # and nothing here runs on the dictation path (mining, sampling,
        # splits, export and profile generation are on-demand/idle).
        self._learning = None
        self._review = None
        self._sampling = None
        self._splits = None
        self._profile = None
        self._exporter = None
        try:
            from localflow.v2 import learning as v2_learning
            from localflow.v2 import profile as v2_profile
            from localflow.v2.curation import export as v2_export
            from localflow.v2.curation import review as v2_review
            from localflow.v2.curation import sampling as v2_sampling
            from localflow.v2.curation import splits as v2_splits
            self._learning = v2_learning.LearningService(
                self.store, emit=self.v2log.emit,
                vocabulary=self._vocab)
            self._review = v2_review.ReviewService(
                self.store, emit=self.v2log.emit)
            self._sampling = v2_sampling.SamplingService(
                self.store, emit=self.v2log.emit,
                percent=float(cfg.get("review_sample_percent", 10)))
            self._splits = v2_splits.SplitService(
                self.store, emit=self.v2log.emit)
            self._profile = v2_profile.ProfileService(
                self.store, emit=self.v2log.emit,
                min_words=int(cfg.get("profile_min_words", 2000)))
            self._exporter = v2_export.DatasetExporter(
                self.store, emit=self.v2log.emit)
            self._profile_idle_minutes = int(
                cfg.get("profile_idle_minutes", 30))
        except Exception as e:
            self._learning = self._review = self._sampling = None
            self._splits = self._profile = self._exporter = None
            self._profile_idle_minutes = 0
            self.v2log.emit("learning.services_unavailable",
                            level="WARNING", reason_code=type(e).__name__,
                            outcome="m14_curation_off")
        try:
            self._styles = v2_profiles_store.StyleRuleStore(self.store)
            self._snip_store = v2_snippets_store.SnippetStore(self.store)
        except Exception as e:
            self._styles = None
            self._snip_store = None
            self.v2log.emit("profiles.store_unavailable", level="WARNING",
                            reason_code=type(e).__name__,
                            outcome="styles_snippets_off")
        self._norm_context = None  # per-job vocabulary context (M06 adds
        #                            destination/path fields)
        # M06 (Spec S12): destination-aware context. Identity is read
        # cheaply at PTT start (after the overlay), providers collect
        # asynchronously during recording, and the finalize at release is
        # bounded by the S12 deadline. A construction failure disables
        # context with an event — dictation never depends on it.
        self._context = None
        try:
            self._context = v2_context.ContextCollector(
                enabled=bool(cfg.get("context_enabled", True)),
                deadline_ms=float(cfg.get("context_deadline_ms", 75)),
                denied_apps=cfg.get("context_denied_apps") or (),
                emit=self.v2log.emit)
        except Exception as e:
            self._context = None
            self.v2log.emit("context.collector_unavailable",
                            level="WARNING", reason_code=type(e).__name__,
                            outcome="context_off")
        # M08 (Spec S18): safe insertion. One serialized transaction
        # queue owns revalidation, the clipboard ownership protocol and
        # undo; the UI callback only ever enqueues. A construction
        # failure degrades to copy-only with an event — dictation
        # itself never depends on this service.
        self._insertion = None
        self._observers = []
        self._starting_observation = None
        try:
            self._insertion = v2_insertion.InsertionService(
                host=v2_insertion_hosts.SystemInsertionHost(),
                pasteboard=v2_insertion_hosts.SystemPasteboard(),
                keyboard=v2_insertion_hosts.SystemKeyboard(),
                store=self.store, emit=self.v2log.emit,
                restore_clipboard=bool(cfg.get("restore_clipboard", True)),
                observation_window_sec=float(
                    cfg.get("outcome_observation_sec", 30)),
                on_post_begin=lambda: setattr(self, "_injecting", True),
                on_post_end=lambda: AppHelper.callAfter(
                    self._armInjectingClear_))
        except Exception as e:
            self._insertion = None
            self.v2log.emit("insertion.service_unavailable",
                            level="WARNING", reason_code=type(e).__name__,
                            outcome="copy_only")
        # M09 (Spec S19): the native Hub. Constructed lazily on first
        # Open Hub; one controller for the process lifetime (closing
        # only orders the window out — the menu-bar service stays).
        self._hub = None
        self._hub_show_pending = False
        self._hub_pending_action = None
        self.overlay = None
        self.hotkey = None
        self.mouse_trigger = None
        self.status_item = None
        self.model_menu_item = None
        self.mode_menu_item = None  # M10: the effective mode/profile line
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
        self._mouse_lost_ticks = 0
        self._failed_pill_timer = None

    @objc.python_method
    def _vocab_job_state(self, scope_ctx=None, m10=None):
        """M05/M06/M10: the (policy, context, hint_set) trio a job
        captures at hotkey-down, scoped by the destination identity M06
        read just before (S12). The snapshot + policy rebuild only when
        the store's revision counter, the destination scope, the M10
        developer-skill revision or the style-derived normalization
        profile changed; in-flight jobs hold the objects they captured,
        so a rule edit mid-flight changes only future jobs and the job
        keeps its vocabulary revision (AC03). The hint set is selected
        fresh per job from the cached snapshot — frozen before
        decoding, never rebuilt from the answer (S30.1)."""
        policy, context = self._norm_policy, self._norm_context
        hint_set = None
        scope_key = None if scope_ctx is None else (
            scope_ctx.app_bundle, scope_ctx.site_origin,
            scope_ctx.workspace, scope_ctx.profile)
        m10_profile = (m10 or {}).get("norm_profile")
        m10_skills_rev = (m10 or {}).get("skill_records_rev")
        norm_profile = m10_profile or (
            policy.profile if policy is not None else None)
        if self._vocab is not None and policy is not None \
                and norm_profile != "off":
            try:
                rev = self._vocab.revision()
                key = (rev, scope_key, m10_skills_rev, norm_profile)
                if key != self._vocab_state_key:
                    snapshot = self._vocab.snapshot(scope_ctx)
                    # M10: the developer registry merges manifest
                    # skills with dictionary skills (same layer 3; a
                    # collision masks the alias — never insertion
                    # order). One merged map feeds the policy.
                    skills = dict(snapshot.skills)
                    if m10 is not None:
                        skills = dict(
                            self._m10_registry(m10, snapshot).policy_skills)
                    self._norm_policy = v2_normalize.NormalizationPolicy(
                        locale=policy.locale, profile=norm_profile,
                        registered_skills=skills)
                    self._norm_context = v2_normalize.ContextSnapshot(
                        vocabulary=snapshot, source="m05_vocabulary")
                    self._vocab_snapshot = snapshot
                    self._vocab_state_key = key
                elif m10 is not None and self._vocab_snapshot is not None:
                    # Cache hit: this job still needs ITS registry under
                    # this scope's snapshot (per-job object).
                    self._m10_registry(m10, self._vocab_snapshot)
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
        elif m10 is not None and m10_skills_rev and policy is not None \
                and norm_profile != "off":
            # Vocabulary store failed but manifest skills exist: the
            # registry still feeds layer 3 (degraded, per-job rebuild).
            try:
                self._norm_policy = v2_normalize.NormalizationPolicy(
                    locale=policy.locale, profile=norm_profile,
                    registered_skills=dict(
                        self._m10_registry(m10, None).policy_skills))
                self._norm_context = v2_normalize.ContextSnapshot(
                    source="m10_skills_only")
                policy, context = self._norm_policy, self._norm_context
            except Exception as e:
                self.v2log.emit("profiles.refresh_failed", level="WARNING",
                                reason_code=type(e).__name__,
                                outcome="skills_dropped")
        return policy, context, hint_set

    # ---- M10: styles, snippets, developer registries -------------------

    @objc.python_method
    def _m10_skill_records(self, workspace_dirs=(), workspace_name=None):
        """Configured-manifest discovery (S17): reads only the
        configured paths (+ the job's workspace dirs), frontmatter
        identity only, nothing executed. Cached by (path, mtime) so an
        unchanged manifest set never re-reads on the dictation path."""
        paths = list(self._skill_manifest_paths) + list(workspace_dirs)

        def stat_key(p):
            try:
                return (str(p), pathlib.Path(p).expanduser().stat()
                        .st_mtime_ns)
            except OSError:
                return (str(p), None)
        key = (tuple(stat_key(p) for p in paths), workspace_name)
        if key != self._skill_cache_key:
            self._skill_records = v2_skills.discover(
                self._skill_manifest_paths, workspace_dirs,
                workspace_name)
            self._skill_cache_key = key
        return self._skill_records

    @objc.python_method
    def _m10_registry(self, m10, vocab_snapshot):
        """The frozen layer-3 skill registry for one job: manifest
        records merged with the dictionary's scoped skills. Built once
        per job (the caller may rebuild after a workspace upgrade)."""
        if "skills" not in m10:
            m10["skills"] = v2_skills.SkillRegistry(
                m10["skill_records"],
                dict(vocab_snapshot.skills)
                if vocab_snapshot is not None else None)
        return m10["skills"]

    @objc.python_method
    def _transforms_snapshot(self):
        """The frozen transform registry for one job (the M10
        snippet-snapshot pattern): cached on the store's state counter
        so a mid-flight edit changes only future jobs. None when the
        transform store is unavailable."""
        if self._tf_store is None:
            return None
        rev = self._tf_store.revision()
        if rev != self._tf_state_key:
            self._tf_snapshot = v2_transforms.TransformSnapshot(
                self._tf_store.definitions())
            self._tf_state_key = rev
        return self._tf_snapshot

    @objc.python_method
    def _m10_freeze(self, dest):
        """Freeze the M10 per-job state at hotkey-down: the style rule
        set, the resolved writing profile (S15 precedence), the snippet
        registry and the manifest skill records. Everything here rides
        the job frozen — a mid-flight edit changes only future jobs."""
        m10 = {"override": self._next_job_mode, "file_resolver": None}
        self._next_job_mode = None  # a one-job override is consumed
        rules = []
        if self._styles is not None:
            try:
                rev = self._styles.revision()
                if rev != self._style_state_key:
                    self._style_rules = self._styles.rules()
                    self._style_state_key = rev
                rules = list(self._style_rules)
            except Exception as e:
                self.v2log.emit("profiles.refresh_failed", level="WARNING",
                                reason_code=type(e).__name__,
                                outcome="last_good_state")
                rules = list(self._style_rules)
        m10["rules"] = rules
        m10["transforms"] = self._transforms_snapshot()
        m10["wp"] = v2_profiles.resolve(m10["override"], rules, dest,
                                        transforms=m10["transforms"])
        if self._snip_store is not None:
            try:
                rev = self._snip_store.revision()
                if rev != self._snippet_state_key:
                    self._snippet_snapshot = v2_snippets.SnippetSnapshot(
                        self._snip_store.snippets())
                    self._snippet_state_key = rev
            except Exception as e:
                self.v2log.emit("profiles.refresh_failed", level="WARNING",
                                reason_code=type(e).__name__,
                                outcome="snippets_last_good_state")
        m10["snippet_snapshot"] = self._snippet_snapshot
        records = self._m10_skill_records()
        m10["skill_records"] = records
        m10["skill_records_rev"] = v2_skills.records_revision(records)
        wp = m10["wp"]
        m10["norm_profile"] = (
            wp.number_policy if wp.number_policy != "inherit" else None)
        return m10

    @objc.python_method
    def _m10_workspace_sources(self, snap):
        """(workspace skill dirs, listing root) for a finalized context:
        resolved from the active document's directory only when the
        locator is a real filesystem path (S12 — a URL locator yields
        nothing; no path is ever guessed)."""
        if snap is None or snap.field is None:
            return (), None
        url = snap.field.document_url
        if not url:
            return (), None
        raw = url[7:] if url.startswith("file://") else url
        if url.startswith("file://") is False and not raw.startswith("/"):
            return (), None  # an http locator is a recorded string only
        doc_dir = pathlib.Path(raw).expanduser().parent
        if not doc_dir.is_dir():
            return (), None
        ws_dirs = [doc_dir / name for name in self._workspace_skill_dirs]
        return tuple(ws_dirs), doc_dir

    @objc.python_method
    def _m10_re_resolve(self, job, snap):
        """M10 (S15): re-resolve the writing profile under the finalized
        destination (origin/workspace/the writing category the widened
        context implies) and refresh the style-derived normalization
        profile. Runs inside the finalize, BEFORE the M05 scope upgrade,
        so the widened vocabulary scope carries the resolved profile
        name and the upgraded policy already uses the final number
        policy (review: rules that only match at finalize must reach
        the job's normalization, not just its envelope)."""
        m10 = job.get("m10")
        if m10 is None or snap is None or snap.target is None:
            return
        dest = v2_profiles.Destination(
            app_bundle=snap.target.app_bundle,
            site_origin=snap.site_origin,
            workspace=snap.workspace,
            category=v2_profiles.derive_category(
                snap.target.category, snap.target.app_bundle,
                snap.site_origin))
        m10["wp"] = v2_profiles.resolve(m10["override"], m10["rules"],
                                        dest,
                                        transforms=m10.get("transforms"))
        m10["norm_profile"] = (
            m10["wp"].number_policy
            if m10["wp"].number_policy != "inherit" else None)

    @objc.python_method
    def _finalized_policy(self, base_policy, m10, vocab_snapshot,
                          *, stale_workspace: bool = False):
        """The finalized normalization policy for a job: the M05/M06
        scope-upgraded snapshot's dictionary skills MERGED with the
        job's frozen manifest skills (one SkillRegistry — collisions
        masked), under the style-derived profile. Single owner of the
        upgraded policy's skill set so no path can silently drop the
        manifest half (review C2)."""
        profile = (m10 or {}).get("norm_profile") or base_policy.profile
        skills = dict(vocab_snapshot.skills) if vocab_snapshot is not None \
            else dict(base_policy.registered_skills or {})
        if m10 is not None:
            registry = v2_skills.SkillRegistry(
                m10["skill_records"],
                dict(vocab_snapshot.skills)
                if vocab_snapshot is not None else None,
                stale_workspace=stale_workspace)
            m10["skills"] = registry
            skills = dict(registry.policy_skills)
        return v2_normalize.NormalizationPolicy(
            locale=base_policy.locale, profile=profile,
            registered_skills=skills)

    @objc.python_method
    def _m10_finalize_upgrade(self, job):
        """M10 finalize: workspace-scoped skill manifests (a changed
        workspace invalidates the stale records — the flag travels in
        the evidence), the file-tag resolver, and the engine-context
        attach. The profile re-resolution already ran inside
        _finalize_job_context (_m10_re_resolve); this pass catches the
        cases the M06 scope upgrade did not cover (no scope widening,
        or skill records that changed) so the job's policy always
        matches its frozen registries and style. Strictly pre-decode."""
        m10 = job.get("m10")
        if m10 is None:
            return
        snap = job.get("context_snapshot")
        if snap is not None:
            ws_dirs, doc_dir = self._m10_workspace_sources(snap)
            workspace = snap.workspace
            # Stale-workspace provenance: the PREVIOUS job's finalized
            # registry carried workspace-scoped skills from a DIFFERENT
            # workspace — this job's rebuild invalidates them (the
            # freeze-time records are global-only by construction, so
            # the signal is tracked against the last finalized set).
            stale = (workspace is not None
                     and self._last_skill_workspace is not None
                     and workspace != self._last_skill_workspace
                     and self._last_ws_skills)
            records = self._m10_skill_records(ws_dirs, workspace)
            rev = v2_skills.records_revision(records)
            base = job.get("norm_policy") or self._norm_policy
            job_vocab = getattr(job.get("norm_context"), "vocabulary",
                                None)
            if rev != m10["skill_records_rev"]:
                m10["skill_records"] = records
                m10["skill_records_rev"] = rev
                if base is not None and base.profile != "off":
                    try:
                        job["norm_policy"] = self._finalized_policy(
                            base, m10, job_vocab,
                            stale_workspace=stale)
                    except Exception as e:
                        self.v2log.emit(
                            "profiles.refresh_failed", level="WARNING",
                            job_id=job.get("job_id"),
                            reason_code=type(e).__name__,
                            outcome="hotkey_down_policy_kept")
            elif base is not None and base.profile != "off" \
                    and m10.get("norm_profile") \
                    and base.profile != m10["norm_profile"]:
                # A rule that only matched at finalize (site/category
                # widened): the number policy must reach the pipeline,
                # not only the envelope.
                try:
                    job["norm_policy"] = self._finalized_policy(
                        base, m10, job_vocab)
                except Exception as e:
                    self.v2log.emit(
                        "profiles.refresh_failed", level="WARNING",
                        job_id=job.get("job_id"),
                        reason_code=type(e).__name__,
                        outcome="hotkey_down_policy_kept")
            self._last_skill_workspace = workspace
            self._last_ws_skills = any(
                r.scope != "global" for r in m10["skill_records"])
            # The file-tag resolver: the open document plus the bounded
            # name-only listing of its directory (config-gated).
            known = ()
            if self._dev_listing and doc_dir is not None:
                known = v2_file_tags.list_workspace_files(doc_dir)
            doc_name = None
            if snap.field is not None and snap.field.document_url:
                doc_name = pathlib.Path(
                    snap.field.document_url).name
            m10["file_resolver"] = v2_file_tags.FileTagResolver(
                known, document_name=doc_name)
            self._last_file_resolver = m10["file_resolver"]
        # Attach the frozen registries to the job's engine context
        # (layer-3 snippet intent + file-tag resolution).
        ctx = job.get("norm_context") or self._norm_context
        if ctx is not None:
            try:
                job["norm_context"] = dataclasses.replace(
                    ctx, snippets=m10.get("snippet_snapshot"),
                    file_resolver=m10.get("file_resolver"))
            except TypeError:
                pass  # a test double without the M10 fields: skip attach
        self._last_wp = m10["wp"]
        self._set_mode_menu(m10["wp"])

    # ---- M11: transforms (Spec S16) --------------------------------------

    @objc.python_method
    def _m11_run_transform(self, defn, source, *, source_kind,
                           parent_job_id=None, attempt=1,
                           selection=None):
        """Run one transform on the worker's cleanup model and rebuild
        the ``TransformResult`` parent-side. TOTAL: a failed request —
        including an oversized source refused at job construction —
        returns the honest fallback-original result, never a raised
        exception into the dictation or selection paths (an exception
        escaping the selection work() would wedge ``_tf_active``
        forever)."""
        try:
            job = v2_transforms.job_for_definition(
                defn, source, source_kind=source_kind,
                parent_job_id=parent_job_id, selection=selection,
                locale=self.cfg.get("normalization_locale", "en-US"))
            res = self.supervisor.transform(
                job_id=parent_job_id, attempt=attempt,
                transform_id=job.transform_id,
                transform_revision=job.transform_revision,
                prompt_revision=job.prompt_revision, mode=job.mode,
                source=job.source, source_kind=source_kind,
                instructions=job.instructions,
                examples_revision=job.examples_revision,
                examples=job.examples,
                locale=self.cfg.get("normalization_locale", "en-US"))
        except ValueError as e:
            # The honest oversized-source refusal (S16), surfaced
            # through the same fallback channel as a worker fault.
            return v2_transforms.TransformResult(
                job=None, output=source,
                path=v2_transforms.PATH_FALLBACK_ORIGINAL,
                reason=f"transform_refused:{str(e)[:60]}")
        except Exception as e:
            reason = getattr(e, "reason_code", None) or type(e).__name__
            return v2_transforms.TransformResult(
                job=None, output=source,
                path=v2_transforms.PATH_FALLBACK_ORIGINAL,
                reason=f"transform_request_failed:{reason}")
        if res.get("refused"):
            return v2_transforms.TransformResult(
                job=None, output=source,
                path=v2_transforms.PATH_FALLBACK_ORIGINAL,
                reason=f"transform_refused:{res['refused'][:60]}")
        return self._m11_result_from_message(job, res)

    @staticmethod
    @objc.python_method
    def _m11_result_from_message(job, res):
        """Rebuild the worker's TransformResult from its message."""
        from .v2.transforms import atoms as tf_atoms
        from .v2.transforms import engine as tf_engine
        coverage = tuple(
            tf_atoms.Coverage(
                atom=tf_atoms.Atom(
                    kind=c.get("kind", ""),
                    excerpt=c.get("kept_excerpt", ""),
                    anchors=tuple(c.get("anchors", ())),
                    start=c.get("source_start", 0),
                    end=c.get("source_end", 0)),
                status=c.get("status", "missing"),
                output_start=c.get("output_start"),
                output_end=c.get("output_end"),
                evidence=c.get("evidence", ""))
            for c in res.get("coverage") or [])
        meta = res.get("result") or {}
        return tf_engine.TransformResult(
            job=job, output=res.get("output") or job.source,
            path=meta.get("path", tf_engine.PATH_FALLBACK_ORIGINAL),
            reason=meta.get("reason"),
            coverage=coverage,
            coverage_summary=meta.get("coverage"),
            diff_stats=meta.get("diff"),
            review_excerpts=tuple(res.get("review_excerpts") or ()),
            output_tokens=meta.get("output_tokens", 0),
            limit_hit=bool(meta.get("limit_hit")),
            duration_ms=meta.get("duration_ms", 0.0),
            prompt=res.get("prompt") or "")

    @objc.python_method
    def _m11_apply_transform(self, job, clean_text, ctx):
        """The dictation-path executor (worker thread): transform the
        CLEAN artifact before insertion when the resolved mode's bound
        definition opted in. The Clean text stays the cleanup family's
        applied output; the transform writes its own stage artifacts
        through the evidence collector. Returns the text to insert —
        TOTAL: any unexpected failure returns the Clean text with the
        recorded reason, so finalize and the history writes for the
        Clean artifact can never be skipped by a transform fault."""
        job_id = job.get("job_id")
        m10 = job.get("m10") or {}
        wp, snapshot = m10.get("wp"), m10.get("transforms")
        if wp is None or snapshot is None:
            return clean_text
        defn, reason = snapshot.auto_apply_decision(
            wp.mode, wp.profile_name, wp.category)
        if reason is not None:
            job["transform_note"] = reason
            if ctx is not None:
                self.collector.note_transform_gate(ctx, reason)
            self.v2log.emit("transforms.not_applied", level="INFO",
                            job_id=job_id, reason_code=reason)
            return clean_text
        try:
            result = self._m11_run_transform(
                defn, clean_text, source_kind="dictation",
                parent_job_id=job_id, attempt=job.get("attempt", 1))
        except Exception as e:
            # _m11_run_transform is total; this guards the impossible.
            result = None
            reason = f"transform_executor_error:{type(e).__name__}"
            job["transform_note"] = reason
            if ctx is not None:
                self.collector.note_transform_gate(ctx, reason)
            self.v2log.emit("transforms.request_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)
            return clean_text
        job["transform_result"] = result
        applied = result.path == v2_transforms.PATH_APPLIED
        try:
            if ctx is not None and result.job is not None:
                self.collector.on_transform_result(ctx, result,
                                                   applied=applied)
        except Exception as e:
            self.v2log.emit("training.capture_failed", level="ERROR",
                            job_id=job_id, reason_code=type(e).__name__)
        if result.job is not None:
            try:
                if self._tf_store is not None:
                    # Dictation-path candidates reference no payload
                    # artifacts here: the collector retains the exact
                    # texts lease-governed (below), so the rows stay
                    # id/hash-only by design.
                    self._tf_store.record_candidate(
                        result, task_kind="dictation_auto_apply",
                        model_id=self.cfg.get("cleanup_model"))
                    if applied:
                        self._tf_store.record_hits([defn.transform_id])
            except Exception as e:
                self.v2log.emit("transforms.record_failed",
                                level="WARNING", job_id=job_id,
                                reason_code=type(e).__name__)
        self.v2log.emit(
            "stage.completed", level="INFO", job_id=job_id,
            attempt=job.get("attempt", 1), stage="transforming",
            duration_ms=result.duration_ms, outcome=result.path,
            reason_code=result.reason,
            model_id=self.cfg.get("cleanup_model"))
        if not applied:
            # Uncertain coverage or a failed generation: the Clean
            # artifact inserts; the transform proposal stays recorded
            # for review — never silently dropped constraints.
            job["transform_note"] = result.reason
            if ctx is not None:
                self.collector.note_transform_gate(ctx, result.reason)
            return clean_text
        return result.output

    @objc.python_method
    def _m11_capture_selection(self):
        """Capture the focused selection for a selected-text transform
        (S16): source selection, range and a snapshot-shaped target
        identity the M08 revalidation consumes at accept time. Runs on
        the transform thread — bounded AX reads never touch the UI
        callback."""
        if self._insertion is None:
            return None, "insertion_service_unavailable"
        host = self._insertion.host
        fm = host.frontmost()
        if not fm:
            return None, "no_frontmost_application"
        bundle = fm.get("bundle")
        if bundle and bundle in (self.cfg.get("context_denied_apps")
                                 or ()):
            return None, "app_denied"
        el = host.focused_element()
        if el is None:
            return None, "no_focused_element"
        rng = None
        raw_range = host.attribute(el, "AXSelectedTextRange")
        try:
            if isinstance(raw_range, tuple):
                # The repo convention (providers._as_range): a plain
                # tuple is (location, length), never (start, end).
                rng = (int(raw_range[0]),
                       int(raw_range[0]) + int(raw_range[1]))
            elif raw_range is not None:
                rng = (int(raw_range.location),
                       int(raw_range.location) + int(raw_range.length))
        except (AttributeError, TypeError, ValueError):
            rng = None
        text = None
        if rng is not None and rng[1] > rng[0]:
            text = host.string_for_range(
                el, rng[0], rng[1] - rng[0])
        if not text or not text.strip():
            return None, "no_selection"
        role = host.attribute(el, "AXRole")
        from .v2 import ids as v2_ids_m11
        from .v2.context.snapshot import (ContextSnapshot, FieldContext,
                                          TargetSnapshot)
        from .v2.context.providers import categorize
        target = TargetSnapshot(
            target_snapshot_id=v2_ids_m11.new_id("tgt"),
            app_bundle=bundle, app_name=fm.get("name"),
            app_pid=fm.get("pid"),
            category=categorize(bundle) if bundle else "unknown",
            captured_at_utc=v2_ids_m11.now_utc_iso())
        field = FieldContext(
            role=str(role) if role else None,
            classification="text", selected_text=text,
            selected_range=tuple(rng))
        snap = ContextSnapshot(
            context_snapshot_id=v2_ids_m11.new_id("ctx"),
            stage="transform_selection", target=target, field=field,
            captured_at_utc=v2_ids_m11.now_utc_iso())
        return {"source": text, "range": tuple(rng), "snapshot": snap,
                "target": target}, None

    def runTransform_(self, sender):
        """Status-menu action: transform the current selection with the
        chosen definition. The pill acknowledges immediately (S24);
        capture + generation run off the UI callback."""
        transform_id = sender.representedObject()
        if self._tf_pipeline_busy():
            self.v2log.emit("transforms.busy", level="INFO",
                            reason_code="pipeline_active")
            return
        snapshot = self._transforms_snapshot()
        defn = snapshot.by_id(transform_id) if snapshot is not None else None
        if defn is None:
            self.v2log.emit("transforms.unavailable", level="WARNING",
                            reason_code="definition_missing")
            return
        self._tf_active = {"transform_id": transform_id}
        self.overlay.showWithMode_(MODE_TRANSFORMING)

        def work():
            capture, reason = self._m11_capture_selection()
            result = None
            if capture is None:
                self.v2log.emit("transforms.selection_unavailable",
                                level="INFO", reason_code=reason)
            else:
                result = self._m11_run_transform(
                    defn, capture["source"], source_kind="selection",
                    selection=capture["range"])
            AppHelper.callAfter(
                self._tfShowResult_, result, capture, defn)
        self._tf_spawn(work)

    @objc.python_method
    def _tf_pipeline_busy(self):
        """The one guard every transform entry shares: never while a
        dictation records/processes, another transform runs, or an
        insertion transaction is in flight (the pill belongs to the
        pipeline)."""
        return self.state != STATE_IDLE or self._tf_active is not None \
            or (self._insertion is not None and self._insertion.busy)

    @objc.python_method
    def _tf_spawn(self, work):
        """Run one transform work() on its daemon thread. The wrapper
        is total: whatever escapes, ``_tfShowResult_`` still runs on
        the main thread and clears ``_tf_active`` (an unguarded death
        would wedge every future transform until restart)."""
        def guarded():
            try:
                work()
            except Exception as e:
                self.v2log.emit("transforms.request_failed",
                                level="WARNING",
                                reason_code=type(e).__name__)
                AppHelper.callAfter(self._tfShowResult_, None, None, None)
        threading.Thread(target=guarded, daemon=True,
                         name="localflow-transform").start()

    @objc.python_method
    def _tfShowResult_(self, result, capture, defn):
        """Main thread: the transform finished — record the candidate
        and open the preview panel (or clear the pill honestly)."""
        self._tf_active = None
        if result is None or capture is None or defn is None:
            self._settle_state()
            return
        # M13 usage fact: an explicit (selection/note-scope) transform
        # run is its own activity kind — never a dictation word. The
        # dictation auto-apply path does not pass through here; its
        # transform rides the dictation's own fact. A refusal
        # (job is None) never ran a generation and records nothing.
        if self._analytics is not None and result.job is not None:
            try:
                self._analytics.record_transform_fact(
                    transform_id=result.job.transform_id,
                    task_key=result.job.task_key(),
                    path=result.path,
                    source_kind=("note"
                                 if (capture or {}).get("note") is not None
                                 else "selection"),
                    source_words=v2.analytics.word_count(
                        capture.get("source")),
                    output_words=v2.analytics.word_count(result.output),
                    duration_ms=result.duration_ms)
            except Exception as e:
                self.v2log.emit("usage.record_failed", level="WARNING",
                                reason_code=type(e).__name__)
        candidate_id = None
        if result.job is not None:
            try:
                if self._tf_store is not None:
                    # Display order ranks candidates WITHIN the task
                    # (S29.10), not results across the process. A note-
                    # scope capture is its own task kind (truthful
                    # provenance, never labeled a selection transform).
                    order = len(self._tf_store.candidates_for_task(
                        result.job.task_key())) + 1
                    candidate_id = self._tf_store.record_candidate(
                        result, task_kind=(
                            "transform_note"
                            if (capture or {}).get("note") is not None
                            else "transform_selection"),
                        source_artifact_text=capture["source"],
                        output_artifact_text=result.output,
                        model_id=self.cfg.get("cleanup_model"),
                        display_order=order)
            except Exception as e:
                self.v2log.emit("transforms.record_failed",
                                level="WARNING",
                                reason_code=type(e).__name__)
        self._settle_state()
        try:
            if self._tf_panel is None:
                from .v2.ui.transforms_panel import TransformPreviewPanel
                self._tf_panel = TransformPreviewPanel.alloc()\
                    .init_panel(self)
            self._tf_panel.show(result, capture, defn, candidate_id)
        except Exception as e:
            self.v2log.emit("transforms.panel_failed", level="WARNING",
                            reason_code=type(e).__name__)

    # Panel actions (called by the preview panel on the main thread).

    @objc.python_method
    def tfAcceptTransform(self, result, capture, candidate_id):
        """Accept: replace the captured selection through the M08
        queue — revalidation first (a changed selection is never
        overwritten, M11-AC03; target_changed routes to the copy
        offer). The explicit accept is the preference observation. A
        NOTE-scope capture (M12) applies in the Scratchpad editor
        instead — the external queue is never involved."""
        if candidate_id and result.job is not None \
                and self._tf_store is not None:
            try:
                self._tf_store.record_observation(
                    task_key=result.job.task_key(),
                    candidate_id=candidate_id, judgment="accept",
                    provenance="user_action",
                    source_event_id="transforms.accept")
            except Exception as e:
                self.v2log.emit("transforms.record_failed",
                                level="WARNING",
                                reason_code=type(e).__name__)
        if capture.get("note") is not None:
            self.tfApplyNoteTransform(result, capture)
            return
        self._insertion.submit(
            result.output,
            {"job_id": None, "attempt": 1,
             "context_snapshot": capture["snapshot"]},
            on_done=lambda r, j=None: AppHelper.callAfter(
                self._tfInsertDone_, r))
        self.v2log.emit("transforms.accepted", level="INFO",
                        outcome=result.path)

    @objc.python_method
    def _tfInsertDone_(self, insertion_result):
        state = getattr(insertion_result, "state", None) or \
            insertion_result.get("state")
        reason = getattr(insertion_result, "reason_code", None) or \
            insertion_result.get("reason_code")
        self.v2log.emit("transforms.insertion_done", level="INFO",
                        outcome=state, reason_code=reason)
        self._settle_state()

    @objc.python_method
    def tfCopyTransform(self, result):
        copy_text(result.output)
        self.v2log.emit("transforms.copied", level="INFO")

    @objc.python_method
    def tfRetryOriginal(self, result, capture, defn, candidate_id):
        """Retry-original: the SAME task, fresh attempt (S16 task 7) —
        the new candidate joins the task key and may be compared."""
        if result.job is None:
            return  # a refused job has no task to retry
        if self._tf_pipeline_busy():
            self.v2log.emit("transforms.busy", level="INFO",
                            reason_code="pipeline_active")
            return
        if candidate_id and self._tf_store is not None:
            try:
                self._tf_store.record_observation(
                    task_key=result.job.task_key(),
                    candidate_id=candidate_id, judgment="reject",
                    provenance="user_action",
                    reason_code="retry_original",
                    source_event_id="transforms.retry")
            except Exception as e:
                self.v2log.emit("transforms.record_failed",
                                level="WARNING",
                                reason_code=type(e).__name__)
        self._tf_active = {"transform_id": defn.transform_id}
        self.overlay.showWithMode_(MODE_TRANSFORMING)
        job = v2_transforms.retry_original(result.job)

        def work():
            res = self._m11_run_job(job)
            AppHelper.callAfter(self._tfShowResult_, res, capture, defn)
        self._tf_spawn(work)

    @objc.python_method
    def tfApplyAnother(self, result, capture, defn, other_id):
        """Apply-another-transform: transforms the SOURCE again under a
        different definition (a new task when the mode/instruction
        differs — never a same-input pair by construction)."""
        if self._tf_pipeline_busy():
            self.v2log.emit("transforms.busy", level="INFO",
                            reason_code="pipeline_active")
            return
        snapshot = self._transforms_snapshot()
        other = snapshot.by_id(other_id) if snapshot is not None else None
        if other is None:
            return
        self._tf_active = {"transform_id": other_id}
        self.overlay.showWithMode_(MODE_TRANSFORMING)

        def work():
            res = self._m11_run_transform(
                other, capture["source"], source_kind="selection",
                selection=capture["range"])
            AppHelper.callAfter(self._tfShowResult_, res, capture, other)
        self._tf_spawn(work)

    @objc.python_method
    def tfTransformOfResult(self, result, capture, defn_id):
        """Transform-the-result: the previous output becomes the source
        (a different task, never a preference pair with the original)."""
        if self._tf_pipeline_busy():
            self.v2log.emit("transforms.busy", level="INFO",
                            reason_code="pipeline_active")
            return
        snapshot = self._transforms_snapshot()
        defn = snapshot.by_id(defn_id) if snapshot is not None else None
        if defn is None:
            return
        self._tf_active = {"transform_id": defn_id}
        self.overlay.showWithMode_(MODE_TRANSFORMING)
        new_capture = dict(capture)
        new_capture["source"] = result.output
        new_capture["range"] = None

        def work():
            res = self._m11_run_transform(
                defn, result.output, source_kind="result")
            AppHelper.callAfter(self._tfShowResult_, res, new_capture,
                                defn)
        self._tf_spawn(work)

    @objc.python_method
    def _m11_run_job(self, job):
        """Re-run an existing TransformJob (retry-original path). TOTAL:
        a worker fault degrades to the honest fallback result, never an
        exception into the transform thread."""
        try:
            res = self.supervisor.transform(
                job_id=job.parent_job_id, attempt=1,
                transform_id=job.transform_id,
                transform_revision=job.transform_revision,
                prompt_revision=job.prompt_revision, mode=job.mode,
                source=job.source, source_kind=job.source_kind,
                instructions=job.instructions,
                examples_revision=job.examples_revision,
                examples=job.examples, locale=job.locale)
        except Exception as e:
            reason = getattr(e, "reason_code", None) or type(e).__name__
            return v2_transforms.TransformResult(
                job=job, output=job.source,
                path=v2_transforms.PATH_FALLBACK_ORIGINAL,
                reason=f"transform_request_failed:{reason}")
        if res.get("refused"):
            return v2_transforms.TransformResult(
                job=job, output=job.source,
                path=v2_transforms.PATH_FALLBACK_ORIGINAL,
                reason=f"transform_refused:{res['refused'][:60]}")
        return self._m11_result_from_message(job, res)

    # ---- M12: the Scratchpad coordinator commands (Spec S20) -----------

    @objc.python_method
    def tfRunNoteTransform(self, transform_id, source, range_, note):
        """Note-scope transform (S20): the note's selection — or the
        whole note when nothing is selected — under the M11 engine,
        with visible scope. The capture is note-bound; accept applies
        in the editor and the M08 external queue is never involved (a
        note transform never overwrites an external target)."""
        if self._tf_pipeline_busy():
            self.v2log.emit("transforms.busy", level="INFO",
                            reason_code="pipeline_active")
            return
        snapshot = self._transforms_snapshot()
        defn = snapshot.by_id(transform_id) if snapshot is not None else None
        if defn is None:
            self.v2log.emit("transforms.unavailable", level="WARNING",
                            reason_code="definition_missing")
            return
        if not source or not source.strip():
            self.v2log.emit("transforms.selection_unavailable",
                            level="INFO", reason_code="empty_note")
            return
        self._tf_active = {"transform_id": transform_id, "note": note}
        self.overlay.showWithMode_(MODE_TRANSFORMING)
        # No range = the whole note: accept REPLACES the note's full
        # content (an insertion at the caret would leave the original
        # beside its own transformation — S20's whole-note scope).
        rng = tuple(range_) if range_ else (0, len(source))
        capture = {"source": source, "range": rng,
                   "snapshot": None, "note": note}

        def work():
            result = self._m11_run_transform(
                defn, source, source_kind="note", selection=capture["range"])
            AppHelper.callAfter(self._tfShowResult_, result, capture, defn)
        self._tf_spawn(work)

    @objc.python_method
    def tfApplyNoteTransform(self, result, capture):
        """Note-scope accept: replace the captured range in the
        Scratchpad editor; the revision records the M11 task identity
        (origin=transform). Revalidation first — the captured source
        must still match at the range, else the copy offer (a changed
        note region is never blindly overwritten, the M08 discipline
        applied to the internal destination)."""
        applied = False
        reason = None
        try:
            if self._hub is not None:
                applied, reason = \
                    self._hub.scratchpad_apply_transform(result, capture)
        except Exception as e:
            reason = type(e).__name__
        if applied:
            self.v2log.emit("notes.transform_applied", level="INFO",
                            outcome=result.path,
                            detail=f"{len(result.output)} chars")
        else:
            copy_text(result.output)
            self.v2log.emit("notes.transform_target_lost", level="INFO",
                            reason_code=reason or "note_range_changed",
                            outcome="copy_offered")
        self._settle_state()

    @objc.python_method
    def tfSaveToScratchpad(self, result, defn):
        """The M11 preview panel's Save-to-Scratchpad, live in M12: the
        transform output becomes a NEW note whose first revision
        carries the task identity (origin=transform)."""
        if self._notes_store is None:
            self.v2log.emit("notes.store_unavailable", level="WARNING",
                            reason_code="scratchpad_off")
            return
        job = result.job
        try:
            out = self._notes_store.create_note(
                result.output, origin=v2_notes.ORIGIN_TRANSFORM,
                source_job_id=job.parent_job_id if job is not None else None,
                task_key=job.task_key() if job is not None else None,
                transform_id=job.transform_id if job is not None else None,
                transform_revision=(job.transform_revision
                                    if job is not None else None),
                title=defn.name)
        except Exception as e:
            self.v2log.emit("notes.note_create_failed", level="WARNING",
                            reason_code=type(e).__name__)
            return
        self.v2log.emit(
            "notes.note_created", level="INFO",
            detail=f"note={out['note_id']} origin=transform"
                   f" {len(result.output)} chars")
        if self._hub is not None:
            try:
                self._hub.scratchpad_note_created(out["note_id"])
            except Exception:
                pass

    @objc.python_method
    def hubNoteDeleted(self, payload):
        """Deletion propagates to evidence references: the collector
        closes the linked examples' note observations (S29.14,
        M12-AC05)."""
        try:
            self.collector.on_note_deleted(payload)
        except Exception as e:
            self.v2log.emit("training.note_capture_failed",
                            level="WARNING", reason_code=type(e).__name__)
        self.v2log.emit(
            "notes.deleted", level="INFO",
            detail=f"note={(payload or {}).get('note_id')}"
                   f" attachments="
                   f"{(payload or {}).get('purged_attachments', 0)}")

    @objc.python_method
    def hubExportNote(self, note_id, path, fmt):
        """Export one note (Markdown/plain). A failed export retains
        the source note untouched — export is a read-only projection."""
        if self._notes_store is None:
            return {"ok": False, "reason": "notes_unavailable",
                    "unsupported": []}
        if fmt not in v2_note_export.FORMATS:
            return {"ok": False, "reason": "unknown_format",
                    "unsupported": []}
        note = self._notes_store.open_note(note_id)
        if note is None:
            return {"ok": False, "reason": "note_missing",
                    "unsupported": []}
        report = v2_note_export.write_export(
            path, note, self._notes_store, fmt)
        self.v2log.emit(
            "notes.export_done" if report.get("ok")
            else "notes.export_failed",
            level="INFO" if report.get("ok") else "WARNING",
            reason_code=report.get("reason"),
            detail=f"note={note_id} fmt={fmt}"
                   f" bytes={report.get('bytes', 0)}"
                   f" unsupported={len(report.get('unsupported') or [])}")
        return report

    @objc.python_method
    def hubSaveHistoryRow(self, kind, row_id, move=False):
        """Explicit copy/move from History into the Scratchpad (S20).
        Copy creates a note from the row's retained final text (origin
        dictated, source job attributed when a V2 example exists).
        Move additionally applies the explicit deletion contract to the
        V2 job (delete-everywhere). Legacy rows have no deletion
        target — a move degrades honestly to copy (legacy history is
        lossless by contract)."""
        if self._notes_store is None:
            return {"outcome": "notes_unavailable"}
        text = None
        source_job = None
        if kind == "job":
            def read(db):
                # The retained FINAL text: applied output first, then
                # the cleaned/raw artifacts (a saved_not_inserted job
                # keeps its text there — exactly what a user rescues
                # into a note).
                for role in ("applied_output", "cleaned_transcript",
                             "raw_transcript"):
                    row = db.execute(
                        "SELECT content_text FROM artifacts WHERE job_id=?"
                        " AND role=? AND purged=0"
                        " ORDER BY rowid DESC LIMIT 1",
                        (row_id, role)).fetchone()
                    if row is not None:
                        return row
                return None
            row = self.store.submit(read)
            text = row[0] if row else None
            source_job = row_id if text else None
        else:
            def read_legacy(db):
                return db.execute(
                    "SELECT COALESCE(cleaned_text, raw_text) FROM"
                    " legacy_dictations WHERE id=?",
                    (int(row_id),)).fetchone()
            row = self.store.submit(read_legacy)
            text = row[0] if row else None
        if not text:
            return {"outcome": "no_retained_text"}
        try:
            out = self._notes_store.create_note(
                text,
                origin=(v2_notes.ORIGIN_DICTATED if kind == "job"
                        else v2_notes.ORIGIN_TYPED),
                source_job_id=source_job)
        except Exception as e:
            self.v2log.emit("notes.note_create_failed", level="WARNING",
                            reason_code=type(e).__name__)
            return {"outcome": "create_failed"}
        outcome = "copied"
        if move:
            if kind == "job":
                try:
                    self.store.delete_everywhere(
                        "job", row_id, reason="moved_to_scratchpad")
                    outcome = "moved"
                except Exception as e:
                    self.v2log.emit("notes.move_failed", level="WARNING",
                                    reason_code=type(e).__name__)
                    outcome = "move_failed_note_copied"
            else:
                outcome = "move_degrades_to_copy_legacy"
        self.v2log.emit("notes.note_created", level="INFO",
                        detail=f"note={out['note_id']}"
                               f" from_history={kind} {outcome}")
        if self._hub is not None:
            try:
                self._hub.scratchpad_note_created(out["note_id"])
            except Exception:
                pass
        return {"outcome": outcome, "note_id": out["note_id"]}

    def quickOpenScratchpad_(self, sender):
        """Quick-open (S20): Hub + Scratchpad view + a fresh note in one
        action, deferred by the focus-steal guard exactly like Open Hub
        — quick-open must never steal the external insertion target
        (M12 regression requirement)."""
        if self._hub_blocks_show():
            self._hub_show_pending = True
            self._hub_pending_action = "scratchpad"
            self.v2log.emit("hub.show_deferred", level="INFO",
                            reason_code="insertion_in_flight")
            return
        self.openHub_(None)
        if self._hub is not None:
            try:
                self._hub.scratchpad_quick_open()
            except Exception as e:
                self.v2log.emit("notes.quick_open_failed", level="WARNING",
                                reason_code=type(e).__name__)

    @objc.python_method
    def _set_mode_menu(self, wp):
        """The S15 quick-menu exposure: the effective mode/profile for
        the most recent destination (a fallback mode says so — never a
        silent Clean)."""
        if self.mode_menu_item is None or wp is None:
            return
        mode = {"raw": "Raw", "clean": "Clean"}.get(
            wp.effective_mode, wp.effective_mode)
        if wp.mode != wp.effective_mode:
            reason = (wp.fallback_reason or "").split(":", 1)
            why = {"transform_auto_apply_disabled":
                   "auto-apply off", "transform_not_bound":
                   "no bound transform"}.get(
                reason[0] if reason else "", "not applied")
            mode += f" (asked {wp.mode}, {why})"
        profile = wp.profile_name or "default"
        source = wp.source.replace("rule:", "rule: ")
        self.mode_menu_item.setTitle_(
            f"Mode: {mode} · profile {profile} · {source}")

    @objc.python_method
    def _finalize_job_context(self, job):
        """M06 (S12): bounded context finalize at release — before the
        job is enqueued for ASR, so everything here is pre-decode. The
        finalized origin/workspace can widen the hotkey-down app-only
        scope; the trio upgrade rebuilds from the job's FROZEN entry set
        (never the store), so a mid-flight edit cannot leak into an
        in-flight job (AC03). Failures degrade to the hotkey-down trio
        with an event — never a dropped dictation."""
        if self._context is None:
            return
        target = job.get("target")
        try:
            snap = self._context.finalize(
                job_id=job.get("job_id"),
                target_snapshot_id=target.target_snapshot_id
                if target is not None else None)
        except Exception as e:
            self.v2log.emit("context.finalize_failed", level="WARNING",
                            job_id=job.get("job_id"),
                            reason_code=type(e).__name__,
                            outcome="hotkey_down_scope_kept")
            return
        if snap is None:
            return
        job["context_snapshot"] = snap
        job["target"] = snap.target
        # M10: re-resolve the writing profile under the finalized
        # destination FIRST — the widened scope below carries the
        # resolved profile name (profile-scoped vocabulary) and the
        # upgraded policy uses the final style-derived number policy.
        try:
            self._m10_re_resolve(job, snap)
        except Exception as e:
            self.v2log.emit("profiles.finalize_failed", level="WARNING",
                            job_id=job.get("job_id"),
                            reason_code=type(e).__name__,
                            outcome="hotkey_down_profile_kept")
        vocab_snapshot = getattr(job.get("norm_context"), "vocabulary",
                                 None)
        if vocab_snapshot is None:
            return
        # One snapshot, three consumers (contracts/context.md): the M04
        # engine context gains the destination/path/identifier fields.
        job["norm_context"] = snap.to_engine_context(vocab_snapshot)
        if job.get("hint_set") is None \
                or self._hint_selector is None:
            return
        m10 = job.get("m10")
        full = snap.to_scope_context()
        if m10 is not None and m10["wp"].profile_name is not None:
            from .v2.vocabulary import ScopeContext
            full = ScopeContext(app_bundle=full.app_bundle,
                                site_origin=full.site_origin,
                                workspace=full.workspace,
                                profile=m10["wp"].profile_name)
        if full == snap.target.to_scope_context() and not (
                m10 is not None and full.profile is not None):
            return  # origin/workspace never resolved: scope unchanged
        upgraded = v2.vocabulary.VocabularySnapshot(
            vocab_snapshot.entries, full)
        base_policy = job.get("norm_policy") or self._norm_policy
        if base_policy is None:
            return
        # Build every upgraded value first: an exception anywhere must
        # leave the job on its hotkey-down trio, not a half-upgraded
        # mix (review fix). The M10 skills merge through the single
        # owner (_finalized_policy) so the scope upgrade can never drop
        # the manifest skills the job froze at hotkey-down.
        try:
            upgraded_policy = self._finalized_policy(
                base_policy, m10, upgraded)
            upgraded_context = snap.to_engine_context(upgraded)
            upgraded_set = self._hint_selector.select(upgraded)
        except Exception as e:
            self.v2log.emit("vocabulary.refresh_failed", level="WARNING",
                            job_id=job.get("job_id"),
                            reason_code=type(e).__name__,
                            outcome="hotkey_down_trio_kept")
            return
        job["norm_policy"] = upgraded_policy
        job["norm_context"] = upgraded_context
        job["hint_set"] = upgraded_set
        job["scope_upgraded"] = True

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

        self._coordinator_thread = threading.Thread(
            target=self._worker, daemon=True, name="localflow-coordinator")
        self._coordinator_thread.start()
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

        # M14 (Spec S22): idle profile regeneration — on demand/idle
        # only, always yielding to dictation. The timer checks the
        # pipeline state before every run; a recording, an in-flight
        # job or an insertion transaction defers to the next tick.
        # profile_idle_minutes = 0 disables idle generation entirely
        # (the Hub's Generate button still works on demand).
        if getattr(self, "_profile_idle_minutes", 0) > 0:
            interval = self._profile_idle_minutes * 60.0
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                interval, self, "profileIdlePass:", None, True
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
        """M03-AUDIT-04: one ordered quit. (1) app admission closes — no
        new capture, retry or recovery; (2) an active capture stops and
        its audio is kept as a recoverable item; (3) the worker's admission
        closes permanently — the request in flight resolves as
        ``supervisor_closed`` and nothing respawns; (4) the coordinator
        settles what it holds (queued jobs fail fast with their audio
        published as recovery items) and exits, bounded; (5) only then do
        the store and event writer close admission and drain. Nothing here
        waits for a main-thread callback."""
        self._closing = True
        try:
            if self.state == STATE_RECORDING:
                self._abandon_capture_for_system("app_quit")
        except Exception as e:
            self.v2log.emit("app.shutdown_capture_failed", level="ERROR",
                            reason_code=type(e).__name__)
        try:
            self.supervisor.shutdown(timeout=2.0)
        except Exception:
            pass
        coord = getattr(self, "_coordinator_thread", None)
        settled = True
        if coord is not None and coord.is_alive():
            self._jobs.put(None)  # sentinel after every queued job
            coord.join(timeout=4.0)
            settled = not coord.is_alive()
        if not settled:
            self.v2log.emit("app.shutdown_incomplete", level="ERROR",
                            reason_code="coordinator_busy",
                            outcome="store_closes_with_producer_alive")
        self._shutdown_persistence()
        fd = getattr(self, "_journal_root_lock", None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            self._journal_root_lock = None

    @objc.python_method
    def _shutdown_persistence(self, timeout=3.0):
        """M02-AUDIT-15: orderly quit for the M02 writers. Producers are
        already stopped (``_shutdown_app`` above); the store then closes
        admission and drains its accepted ops, the outcome is recorded as
        an event, and only then does the event writer close (its own
        admission first, then its drain). Bounded: a stalled writer is
        reported (pending count), never closed underneath."""
        status = None
        try:
            status = self.store.close(timeout=timeout)
        except Exception as e:
            self.v2log.emit("store.close_failed", level="ERROR",
                            reason_code=type(e).__name__)
        if status is not None:
            self.v2log.emit(
                "app.shutdown", level="INFO" if status.get("drained")
                else "ERROR",
                outcome="drained" if status.get("drained")
                else "store_drain_incomplete",
                reason_code="application_will_terminate",
                detail=f"pending_ops={status.get('pending_ops')}")
        try:
            self.v2log.close(timeout=timeout)
        except Exception:
            pass

    def retentionPass_(self, timer):
        # Retention queries can be slow with a large store; never let them
        # stall the main thread (the store serializes them on its writer).
        threading.Thread(target=self._retention_pass, daemon=True).start()

    def profileIdlePass_(self, timer):
        """M14 (S22): the idle profile tick. Yield-first: any pipeline
        activity (recording, an unfinished job, an insertion/undo in
        flight) skips this tick — profile work never delays dictation.
        The compute itself runs on a daemon thread (it is one bounded
        store op)."""
        try:
            if self.state == STATE_RECORDING or self._pending > 0 \
                    or self._injecting or (
                        self._insertion is not None
                        and bool(getattr(self._insertion, "busy", False))):
                return
            if self._profile is None:
                return
            threading.Thread(target=self._profile_idle_compute,
                             daemon=True,
                             name="localflow-profile-idle").start()
        except Exception as e:
            self.v2log.emit("profile.idle_failed", level="WARNING",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _profile_idle_compute(self):
        try:
            # Snapshots are records: an idle tick over unchanged
            # evidence adds none.
            self._profile.compute(only_if_changed=True)
        except Exception as e:
            self.v2log.emit("profile.idle_failed", level="WARNING",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _retention_pass(self):
        try:
            self.store.sweep_orphans()
            self.store.prune()
            self.store.prune_training()
            # M13: the usage knob's own expiry (facts and aggregates,
            # independent of text retention) and the M02 metadata knob's
            # job-row pruning, deferred to this milestone (hub.md).
            if self._analytics is not None:
                self._analytics.expire_usage()
            self.store.prune_metadata()
            self._sweep_journal_root()
        except Exception as e:
            self.v2log.emit("store.retention_failed", level="ERROR",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _sweep_journal_root(self):
        """Failed/recoverable journal files expire with the audio-failed
        retention knob; resolved jobs already deleted theirs eagerly.
        Staged ``.part-`` files are transient: any left by a crash go
        after an hour."""
        days = self.store.retention_days["audio_failed"]
        now = time.time()
        for pattern, cutoff in (("job-*.blk", now - days * 86400),
                                ("job-*.wav", now - days * 86400),
                                ("job-*" + PROVENANCE_SUFFIX,
                                 now - days * 86400),
                                ("job-*.part-*", now - 3600)):
            for p in V2_JOURNAL.glob(pattern):
                try:
                    if p.stat().st_mtime < cutoff:
                        p.unlink()
                except OSError:
                    continue

    # ---- job-file ownership (M03-AUDIT-01/02) ------------------------------

    @objc.python_method
    def _on_job_deleted(self, job_id):
        """Store deletion listener (writer thread, inside the delete op):
        revoke every in-memory authority this process holds for the job.
        Flags only — no store calls, no main-thread work."""
        self._deleted_jobs.add(job_id)
        tap = self._tap_pending or {}
        for job in [self._job, tap.get("job")] + list(self._active_jobs):
            if job and job.get("job_id") == job_id:
                job["deleted"] = True
                job["cancelled"] = True
        revoke = getattr(self.supervisor, "revoke_job", None)
        if revoke is not None:
            try:
                revoke(job_id)
            except Exception:
                pass

    @objc.python_method
    def _job_is_deleted(self, job_id) -> bool:
        if not job_id:
            return False
        if job_id in self._deleted_jobs:
            return True
        try:
            return bool(self.store.job_deleted(job_id))
        except Exception:
            return False

    @objc.python_method
    def _journal_open_gate(self, job_id):
        """The capture journal creates its file only through the store's
        deletion arbitration (M03-AUDIT-02)."""
        store = self.store

        def gate(opener):
            return store.run_unless_deleted(job_id, opener)
        return gate

    @objc.python_method
    def _live_job_ids(self) -> set:
        """Jobs this process is working on right now (capture, queue,
        coordinator, insertion) — never crash residue."""
        live = set()
        for job in [self._job, (self._tap_pending or {}).get("job")] \
                + list(self._active_jobs):
            if job and job.get("job_id"):
                live.add(job["job_id"])
        return live

    @objc.python_method
    def _publish_job_audio(self, job_id, path, samples, rate) -> str:
        """Stage a complete float32 WAV, then publish it atomically under
        the deletion barrier (M03-AUDIT-02/10). Returns the store's
        outcome: published / deleted / failed."""
        path = pathlib.Path(path)
        if not job_id:
            v2.store.write_wav_f32(path, samples, int(rate))
            return "published"
        staged = v2.store.stage_wav_f32(path, samples, int(rate))
        return self.store.publish_job_file(job_id, staged, path)

    @objc.python_method
    def _write_provenance(self, job_id, prov) -> str:
        """Publish the job's capture-provenance sidecar next to its audio
        (same arbitration as the audio; deleted with the job)."""
        if not job_id:
            return "failed"
        final = V2_JOURNAL / f"job-{job_id}{PROVENANCE_SUFFIX}"
        try:
            final.parent.mkdir(parents=True, exist_ok=True)
            staged = v2.store.stage_path(final)
            fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(prov, f, sort_keys=True)
        except Exception as e:
            self.v2log.emit("capture.provenance_write_failed",
                            level="WARNING", job_id=job_id,
                            reason_code=type(e).__name__)
            return "failed"
        return self.store.publish_job_file(job_id, staged, final)

    @objc.python_method
    def _read_provenance(self, job_id):
        path = V2_JOURNAL / f"job-{job_id}{PROVENANCE_SUFFIX}"
        try:
            prov = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(prov, dict) \
                or prov.get("capture_provenance_version") \
                != PROVENANCE_VERSION or prov.get("job_id") != job_id:
            return None
        return prov

    @objc.python_method
    def _live_provenance(self, job, stats, sample_count, rate):
        cap = job.get("captured_at_utc")
        return {
            "capture_provenance_version": PROVENANCE_VERSION,
            "job_id": job.get("job_id"), "family_id": job.get("family_id"),
            "captured_at_utc": cap,
            "time_quality": job.get("time_quality", "known") if cap
            else "unknown",
            "timezone": job.get("timezone"),
            "utc_offset_minutes": job.get("utc_offset_minutes"),
            "sample_rate": int(rate), "sample_count": int(sample_count),
            "channels": 1,
            # The live capture is the in-memory buffer: complete up to the
            # device (input overflows never reach memory or the journal).
            "source": "live_memory", "complete": True,
            "capture_journal": "enabled" if job.get("journal") is not None
            else "disabled",
            "device": stats.get("device"),
            "voiced_pct": stats.get("voiced_pct"),
            "trailing_silence_sec": stats.get("trailing_silence_sec"),
            "overflow_blocks": stats.get("overflow_blocks"),
            "device_discontinuity": stats.get("device_discontinuity"),
            "stream_teardown_error": stats.get("stream_teardown_error"),
        }

    @objc.python_method
    def _inspect_wav(self, path):
        """(samples, rate, info) for a recovery WAV — a truncated file
        yields its complete-sample prefix with honest counts — or None."""
        try:
            return v2.store.read_wav_f32_prefix(path)
        except (OSError, ValueError):
            return None

    # ---- crash recovery (M03-AC03) --------------------------------------

    @objc.python_method
    def _recover_journals(self):
        """Startup scan: crash residue from an EARLIER process becomes
        recoverable items (M03-AC03). Ownership first (M03-AUDIT-01):
        nothing is claimed unless this process owns the journal root, no
        live writer holds the file, the job is not this session's own work,
        and the job is neither deleted nor already resolved. Source
        selection never replaces better audio: a complete worker WAV (the
        full in-memory capture) beats a journal reconstruction, which beats
        a truncated WAV's prefix; every choice is recorded in the job's
        capture-provenance sidecar with the original capture instant."""
        if getattr(self, "_journal_root_lock", None) is None:
            self.v2log.emit("capture.recovery_skipped", level="WARNING",
                            reason_code="journal_root_owned_elsewhere",
                            outcome="nothing_claimed")
            return
        found = 0
        handled = set()
        min_sec = float(self.cfg["min_duration_sec"])
        for blk in capture_journal.unfinished_journals(V2_JOURNAL):
            if self._closing:
                return
            job_id = blk.stem[len("job-"):]
            handled.add(job_id)
            outcome = self._recover_one(job_id, blk, min_sec)
            if outcome == "recoverable":
                found += 1
        # Jobs that finished capture but died before resolution (wav kept,
        # blk already finalized or swept). Only residue from previous boots
        # and never work this process holds.
        for job_id in list(self.store.unresolved_job_ids()):
            if self._closing:
                return
            if job_id in handled:
                continue
            outcome = self._recover_one(job_id, None, min_sec)
            if outcome == "recoverable":
                found += 1
        if found:
            AppHelper.callAfter(self._refresh_recovery_menu)

    @objc.python_method
    def _recover_one(self, job_id, blk, min_sec):
        wav = V2_JOURNAL / f"job-{job_id}.wav"
        if job_id in self._live_job_ids():
            return "live_in_process"
        if blk is not None and capture_journal.is_live(blk):
            self.v2log.emit("capture.recovery_skipped", level="INFO",
                            job_id=job_id, reason_code="journal_writer_live")
            return "live_writer"
        row = self.store.job(job_id)
        if row and row.get("boot_id") == self.v2log.boot_id:
            return "current_session"
        if self._job_is_deleted(job_id):
            # Deleted work is never resurrected; residue is removed.
            self._delete_journal_files(job_id)
            self.v2log.emit("capture.recovery_skipped", level="INFO",
                            job_id=job_id, reason_code="job_deleted",
                            outcome="residue_removed")
            return "deleted"
        state = (row or {}).get("state")
        if state in _TERMINAL and state != "failed_recoverable":
            if state in _CONSUMED and blk is not None:
                try:
                    blk.unlink()
                except OSError:
                    pass
            self.v2log.emit("capture.recovery_skipped", level="INFO",
                            job_id=job_id, reason_code="job_already_resolved",
                            outcome=state)
            return "resolved"
        rec = None
        if blk is not None:
            try:
                rec = capture_journal.reconstruct(blk)
            except Exception as e:
                self.v2log.emit("capture.recovery_failed", level="ERROR",
                                reason_code=type(e).__name__)
                rec = None
            if rec is not None and rec.header.get("job_id") not in (
                    None, job_id):
                self.v2log.emit("capture.recovery_failed", level="ERROR",
                                job_id=job_id,
                                reason_code="journal_job_mismatch")
                return "mismatch"
        existing = self._inspect_wav(wav) if wav.exists() else None
        header = (rec.header if rec is not None else {}) or {}
        meta = header.get("meta") or {}
        if row is None:
            family_id = header.get("family_id") or v2.ids.new_id("fam")
            cap = meta.get("captured_at_utc")
            self.store.create_job(
                job_id=job_id, family_id=family_id,
                session_id=self.v2log.session_id,
                boot_id=header.get("boot_id") or "unknown_previous_boot",
                captured_at_utc=cap,
                time_quality=meta.get("time_quality", "known") if cap
                else "unknown",
                state="capturing",
                source_revision=v2.ids.source_revision(),
                pipeline_revision=v2.ids.PIPELINE_REVISION)
            row = self.store.job(job_id) or {}
        family_id = row.get("family_id") or header.get("family_id")
        # ---- source selection ------------------------------------------
        source, samples, rate, info = None, None, None, {}
        j_samples = rec.samples if rec is not None else None
        j_rate = header.get("sample_rate")
        if existing is not None and existing[2]["complete"] and (
                j_samples is None or existing[0].size >= j_samples.size):
            source, samples, rate = "worker_wav", existing[0], existing[1]
            info = existing[2]
        elif j_samples is not None and j_samples.size and j_rate and (
                existing is None or j_samples.size >= existing[0].size):
            source, samples, rate = "journal_reconstruction", j_samples, \
                j_rate
        elif existing is not None and existing[0].size:
            source, samples, rate = "worker_wav_prefix", existing[0], \
                existing[1]
            info = existing[2]
        prov = self._read_provenance(job_id) or {}
        if source is not None and source != "worker_wav" \
                and samples.size / float(rate) >= min_sec:
            published = self._publish_job_audio(job_id, wav, samples, rate)
            if published != "published":
                return "publish_" + published
        recoverable = source is not None and \
            samples.size / float(rate) >= min_sec
        # ---- provenance: the ORIGINAL capture, not this scan ----------
        cap = row.get("captured_at_utc") or prov.get("captured_at_utc") \
            or meta.get("captured_at_utc")
        new_prov = dict(prov)
        new_prov.update({
            "capture_provenance_version": PROVENANCE_VERSION,
            "job_id": job_id, "family_id": family_id,
            "captured_at_utc": cap,
            "time_quality": (row.get("time_quality") or prov.get(
                "time_quality") or meta.get("time_quality") or "known")
            if cap else "unknown",
            "timezone": row.get("timezone") or prov.get("timezone"),
            "utc_offset_minutes": row.get("utc_offset_minutes")
            if row.get("utc_offset_minutes") is not None
            else prov.get("utc_offset_minutes"),
            "recovered": True,
            "recovered_at_utc": v2.ids.now_utc_iso(),
        })
        if source is not None:
            new_prov.update({"source": source, "sample_rate": int(rate),
                             "sample_count": int(samples.size),
                             "channels": 1})
        if source == "journal_reconstruction":
            # Verified footer and no gap: complete. A clean record-boundary
            # EOF without footer: the capture's end is UNKNOWN (None), not
            # assumed. Anything torn, corrupt or gapped: incomplete.
            if rec.gaps or rec.status not in (
                    capture_journal.STATUS_VERIFIED,
                    capture_journal.STATUS_UNFINALIZED):
                new_prov["complete"] = False
            elif rec.status == capture_journal.STATUS_VERIFIED:
                new_prov["complete"] = True
            else:
                new_prov["complete"] = None
        elif source == "worker_wav":
            # The complete release-time WAV is the full memory capture.
            new_prov["complete"] = prov.get("complete", True)
        elif source == "worker_wav_prefix":
            new_prov["complete"] = False
        if source in ("worker_wav", "worker_wav_prefix"):
            new_prov["wav"] = {
                "declared_samples": info.get("declared_samples"),
                "available_samples": info.get("available_samples")}
        if rec is not None:
            new_prov["journal"] = {
                "status": rec.status, "version": rec.version,
                "integrity": rec.integrity,
                "corrupt_reason": rec.corrupt_reason,
                "torn_bytes": rec.torn_bytes,
                "positions_known": rec.positions_known,
                "gaps": list(rec.gaps or []),
                "dropped_blocks": (rec.footer or {}).get("dropped_blocks"),
                "used": source == "journal_reconstruction"}
        if recoverable:
            self._write_provenance(job_id, new_prov)
        if blk is not None:
            try:
                blk.unlink()
            except OSError:
                pass
        if state == "insertion_posted":
            reason = "app_crash_after_insertion_posted"
        elif blk is not None and source == "journal_reconstruction":
            reason = "app_crash_during_capture"
        elif source == "worker_wav_prefix":
            reason = "app_crash_audio_truncated"
        elif source == "worker_wav":
            reason = "app_crash_before_resolution"
        else:
            reason = None
        if recoverable:
            self._job_state(job_id, "failed_recoverable", reason=reason)
            self._recoverable.append({
                "job_id": job_id, "family_id": family_id,
                "wav": str(wav), "raw": None,
                "attempt": int(row.get("attempt") or 1)})
        elif blk is not None:
            self._job_state(
                job_id, "cancelled",
                reason="crash_below_min_duration" if source is not None
                else "crash_no_audio_recovered")
        else:
            self._job_state(job_id, "failed_recoverable",
                            reason="app_crash_audio_lost")
        self.v2log.emit(
            "capture.recovered_after_crash", level="WARNING",
            job_id=job_id, reason_code="journal_reconstruction"
            if source == "journal_reconstruction" else (source or "none"),
            outcome=("recoverable" if recoverable else
                     "below_min_duration" if source is not None
                     else "audio_lost"),
            detail=(f"journal={rec.status} blocks={rec.complete_blocks}"
                    f" samples={rec.samples.size}"
                    f" torn_bytes={rec.torn_bytes}"
                    f" gaps={len(rec.gaps or [])}" if rec is not None
                    else "journal=none")
            + (f" wav={'complete' if info.get('complete') else 'partial'}"
               if info else ""))
        return "recoverable" if recoverable else "not_recoverable"

    # ---- engine status ---------------------------------------------------

    def _setEngineStatus_(self, engines):
        _engine, _state = engines
        states = dict(self.supervisor.engine_state)
        self.model_menu_item.setTitle_(
            f"ASR: {states.get('asr', 'not_started')}"
            f" · Cleanup: {states.get('cleanup', 'not_started')}")

    # ---- dictation state machine (all on main thread) ------------------

    def startDictation(self, source="hotkey"):
        if getattr(self, "_closing", False):
            return  # quitting: app admission is closed (M03-AUDIT-04)
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
        if self._insertion is not None:
            # S29.8 stop condition: a new dictation ends any live
            # outcome-observation window.
            self._insertion.note_new_dictation()
        job_id, family_id = self.store.create_job(
            kind="dictation", session_id=self.v2log.session_id,
            boot_id=self.v2log.boot_id,
            captured_at_utc=v2.ids.now_utc_iso(), time_quality="known",
            timezone=v2.ids.local_zone_name(),
            utc_offset_minutes=v2.ids.utc_offset_minutes(),
            state="capturing", source_revision=v2.ids.source_revision(),
            pipeline_revision=v2.ids.PIPELINE_REVISION)
        # M02-AUDIT-06: the collection-consent decision is taken HERE, at
        # push-to-talk down — the capture boundary consent_revision_id is
        # defined against — as one coherent (state, revision) pair. A
        # consent change during the capture neither adds nor removes
        # this job's evidence (capture-snapshot policy).
        try:
            consent_snapshot = self.consent.capture_snapshot()
        except Exception as e:
            consent_snapshot = v2.training.ConsentSnapshot(
                "disabled", None, "ptt_down_unavailable")
            self.v2log.emit("training.consent_snapshot_failed",
                            level="WARNING", job_id=job_id,
                            reason_code=type(e).__name__,
                            outcome="not_collected")
        journal = None
        try:
            if self.cfg.get("capture_journal", True):
                journal = capture_journal.CaptureJournal(
                    V2_JOURNAL, job_id=job_id, family_id=family_id,
                    sample_rate=self.cfg["sample_rate"],
                    emit=self.v2log.emit,
                    meta={"captured_at_utc": v2.ids.now_utc_iso(),
                          "time_quality": "known"},
                    boot_id=self.v2log.boot_id,
                    open_gate=self._journal_open_gate(job_id))
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
            "consent": consent_snapshot,
            "sample_rate": int(self.cfg["sample_rate"]),
            "time_quality": "known",
        }
        # M12 (Spec S20): a dictation started with the Scratchpad
        # editor focused is NOTE-BOUND — an internal destination. The
        # insertion point is captured here, at PTT start, exactly as
        # the M08 discipline captures a selection at request time; the
        # anchor promised at hotkey-down is the anchor that receives.
        if self._hub is not None:
            try:
                if self._hub.scratchpad_editor_active():
                    self._job["note_target"] = {
                        "note_id": self._hub.editor.note_id,
                        "insertion_point":
                            self._hub.editor.insertion_point()}
                    self.v2log.emit(
                        "notes.dictation_bound", level="INFO",
                        job_id=job_id,
                        detail=f"note={self._job['note_target']['note_id']}")
            except Exception:
                pass  # a Hub probe failure must never touch capture
        if hands_free:
            # Releases no longer finish this capture; only a new tap, a
            # cancel, or the duration cap does (Spec S09).
            self._hands_free_active = True
        self.v2log.emit("capture.started", level="INFO", job_id=job_id,
                        outcome="hands_free" if hands_free else None)
        self.state = STATE_RECORDING
        self.overlay.showWithMode_(MODE_RECORDING)
        # M06 (Spec S12): cheap destination identity at PTT start —
        # AFTER the overlay (no Accessibility read ever delays visible
        # feedback) and BEFORE the trio, so the pre-decode hint set is
        # scoped by the real destination; the bounded provider
        # collection then runs asynchronously while recording.
        identity = None
        if self._context is not None:
            try:
                identity = self._context.capture_identity()
                if identity is not None:
                    # The per-job collection handle travels with the job;
                    # its downstream revision is composed from this handle
                    # only (never from whatever a newer dictation started).
                    self._job["context_coll"] = self._context.begin(identity)
                    # M13: the usage fact's own app copy (facts survive
                    # job-row pruning — AC03).
                    self._job["app_name"] = identity.app_name
                    self._job["app_bundle"] = identity.app_bundle
                    # M09: History's app filter needs the destination on
                    # the job row (Spec S08 jobs "target"); a store stall
                    # here never touches the dictation.
                    try:
                        self.store.set_job_target(
                            job_id, identity.app_name, identity.app_bundle)
                    except Exception as e:
                        self.v2log.emit("store.state_write_failed",
                                        level="WARNING", job_id=job_id,
                                        reason_code=type(e).__name__)
                else:
                    # A failed identity capture must never leave the
                    # PREVIOUS job's collection active — its finalize
                    # could hand the old snapshot to this job.
                    self._context.abandon()
            except Exception as e:
                identity = None
                self._context.abandon()
                self.v2log.emit("context.capture_failed", level="WARNING",
                                job_id=job_id, reason_code=type(e).__name__,
                                outcome="context_skipped")
        # M05/M10: freeze the vocabulary policy/context/hint set and the
        # style/snippet/developer registries into the job (pre-decode;
        # edits after this point affect only future jobs, AC03). Runs
        # AFTER the overlay so selector/snapshot work never delays the
        # hotkey-down visible feedback (S06/S24). The M10 profile
        # resolves first — its writing-profile name widens the M05
        # scope (profile-scoped vocabulary entries apply in their
        # destinations now, closing the M05 limitation).
        try:
            m10 = self._m10_freeze(v2_profiles.Destination(
                app_bundle=identity.app_bundle if identity is not None
                else None,
                # The PTT identity's app category derives the writing
                # category at hotkey-down already (IDE/terminal/mail
                # destinations resolve their rules and profile-scoped
                # vocabulary immediately; a browser's ai_prompt category
                # still waits for the finalized origin).
                category=v2_profiles.derive_category(
                    identity.category if identity is not None else None,
                    identity.app_bundle if identity is not None
                    else None)))
            self._job["m10"] = m10
            scope_ctx = None
            if identity is not None:
                from .v2.vocabulary import ScopeContext
                scope_ctx = ScopeContext(
                    app_bundle=identity.app_bundle,
                    profile=m10["wp"].profile_name)
            self._job.update(dict(
                zip(("norm_policy", "norm_context", "hint_set"),
                    self._vocab_job_state(scope_ctx, m10=m10))))
            if identity is not None:
                self._job["target"] = identity
            self._set_mode_menu(m10["wp"])
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
                # M13: this branch terminates the job without ever
                # reaching _finishWithText_ — the fact is written here
                # (capture duration unknown at this seam: no stats yet,
                # so duration_sec stays null, never invented).
                self._record_dictation_usage(job, "cancelled")
                self._delete_journal_files(job["job_id"], job)
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
                revoke = getattr(self.supervisor, "revoke_job", None)
                if revoke is not None and job.get("job_id"):
                    revoke(job["job_id"])
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
        # M03-AUDIT-15: every capture end — release, tap, duration cap,
        # device loss — clears the hands-free latch, so the next press
        # starts a capture instead of "ending" one that is gone.
        self._hands_free_active = False
        self._lost_ticks = 0
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
            # M06 (S12): bounded finalize + pre-decode scope upgrade
            # BEFORE the hint set is stored — the retained set is what
            # was actually offered pre-decode (late context is a
            # separate downstream revision, never merged here).
            try:
                self._finalize_job_context(job)
            except Exception as e:
                self.v2log.emit("context.finalize_failed", level="WARNING",
                                job_id=job["job_id"],
                                reason_code=type(e).__name__,
                                outcome="hotkey_down_scope_kept")
            # M10 (S15/S17): re-resolve under the finalized destination
            # (workspace manifests, file resolver, profile upgrade) —
            # still strictly pre-decode, before job_started/on_hint_set.
            try:
                self._m10_finalize_upgrade(job)
            except Exception as e:
                self.v2log.emit("profiles.finalize_failed", level="WARNING",
                                job_id=job["job_id"],
                                reason_code=type(e).__name__,
                                outcome="hotkey_down_state_kept")
            try:
                ctx = self.collector.job_started(
                    job["job_id"], job["family_id"],
                    captured_at_utc=job["captured_at_utc"],
                    timezone=job["timezone"],
                    utc_offset_minutes=job["utc_offset_minutes"],
                    consent_snapshot=job.get("consent"))
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
            # M06 (S30.1): the extension point is called for real on the
            # dictation path — None under the unqualified adapter (the
            # disposition above is the honest record), the dict with the
            # context_snapshot_id the day an adapter qualifies.
            if job.get("hint_set") is not None:
                job["hint_request_fields"] = \
                    v2.capabilities.asr_hint_request_fields(
                        job["hint_set"], self._capability_manifest,
                        context_snapshot_id=(
                            job["context_snapshot"].context_snapshot_id
                            if job.get("context_snapshot") is not None
                            else None))
            # M06 (S29.4 context family): the bounded destination
            # snapshot, retained pre-decode under its own lease when
            # training-context retention is on.
            if ctx is not None and job.get("context_snapshot") is not None:
                try:
                    self.collector.on_context_snapshot(
                        ctx, job["context_snapshot"])
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job["job_id"],
                                    reason_code=type(e).__name__)
            # M10 (S15/S17/S29.4): the resolved writing profile and the
            # frozen skill registry, retained pre-decode — the exact
            # mode/style/skill provenance this job ran under.
            if ctx is not None and job.get("m10") is not None:
                try:
                    m10 = job["m10"]
                    self.collector.on_writing_profile(
                        ctx, m10["wp"].to_json(),
                        skill_registry=m10.get("skills"))
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job["job_id"],
                                    reason_code=type(e).__name__)
            job.update({"audio": audio, "stats": s, "ctx": ctx,
                        "failed": False,
                        # A job deleted while it was still capturing keeps
                        # its revoked authority (M03-AUDIT-02).
                        "cancelled": bool(job.get("deleted")),
                        "attempt": 1, "raw": None, "wav": None})
            job["capture_provenance"] = self._live_provenance(
                job, s, len(audio), job.get("sample_rate")
                or self.cfg["sample_rate"])
            # M13 (E06 end-to-end latency): the parent's monotonic
            # release instant — end_to_end_ms is measured against this
            # when the terminal insertion outcome lands (PTT release to
            # target-confirmed text, never a cross-process clock).
            job["released_mono"] = time.monotonic()
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
        if self._insertion is not None:
            self._insertion.note_session_locked()

    def sessionResigned_(self, note):
        self._abandon_capture_for_system("session_locked_or_switched")
        if self._insertion is not None:
            self._insertion.note_session_locked()

    def didWake_(self, note):
        # The microphone stays off after wake until the user asks for it
        # (Spec S09): nothing here starts a capture. Observation,
        # however, re-arms — a lock is a state, not a one-way event.
        if self._insertion is not None:
            self._insertion.note_session_unlocked()
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
        rate = int(job.get("sample_rate") or self.cfg["sample_rate"])
        try:
            wav = self._worker_wav_path(job)
            outcome = self._publish_job_audio(job["job_id"], wav, audio,
                                              rate)
            if outcome != "published":
                wav = None
                self.v2log.emit("capture.recovery_write_failed",
                                level="WARNING", job_id=job["job_id"],
                                reason_code=f"publish_{outcome}")
            else:
                prov = self._live_provenance(job, self.recorder.stats,
                                             len(audio), rate)
                prov["interrupted_by"] = reason
                self._write_provenance(job["job_id"], prov)
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
            # M03-AUDIT-15: the same repair for the mouse trigger (its
            # button state is always observable). Two idle ticks, so a
            # press being delivered right now is never undone; idle means
            # there is no capture another trigger could be releasing.
            mt = self.mouse_trigger
            if mt is not None and mt.held and not mt.physically_down():
                self._mouse_lost_ticks += 1
                if self._mouse_lost_ticks >= 2:
                    mt.held = False
                    self._mouse_lost_ticks = 0
                    self.v2log.emit("hotkey.release_lost", level="INFO",
                                    reason_code="mouse_state_reconciled")
            else:
                self._mouse_lost_ticks = 0

    # ---- inference coordinator (FIFO thread) ------------------------------

    @objc.python_method
    def _worker(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return  # shutdown sentinel: every earlier job was settled
            if job.get("cancelled"):
                AppHelper.callAfter(self._finishWithText_, "", job)
                continue
            audio, ctx, job_id = job["audio"], job["ctx"], job["job_id"]
            rate = int(job.get("sample_rate") or self.cfg["sample_rate"])
            # Observations during this job's cleanup attach to it even if
            # the main thread starts a newer dictation meanwhile.
            if ctx is not None:
                self.collector.bind_current(ctx)
            text = ""
            try:
                if self.cfg["log_transcripts"]:
                    self._dump_audio(audio, job_id, rate)
                self._job_state(job_id, "transcribing")
                # Evidence/store work is guarded separately: a capture or
                # disk problem must never fail an otherwise successful
                # dictation (the pipeline stages below have their own try).
                try:
                    if ctx is not None:
                        self.collector.attach_capture_meta(
                            ctx, job["stats"], rate)
                        # The audio artifact is attached to the job before
                        # model execution.
                        self.collector.on_audio(
                            ctx, audio, rate, job["stats"])
                        self.store.sync()
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
                # Parent-created audio reference for the worker (Spec S06):
                # a float32 WAV under the parent-owned journal root.
                # M03-AUDIT-02/10: staged, then published atomically
                # under the deletion barrier — a deleted job's audio is
                # never recreated, and the worker never sees a
                # half-written file.
                try:
                    wav = self._worker_wav_path(job)
                    if not job.get("wav"):
                        if job.get("capture_provenance") and job_id:
                            self._write_provenance(
                                job_id, job["capture_provenance"])
                        outcome = self._publish_job_audio(
                            job_id, wav, audio, rate)
                        if outcome == "deleted":
                            job["deleted"] = job["cancelled"] = True
                            raise _JobCancelled()
                        if outcome != "published":
                            raise RuntimeError("worker audio not published")
                        job["wav"] = wav
                except _JobCancelled:
                    raise
                except Exception as e:
                    self.v2log.emit("capture.worker_audio_failed",
                                    level="ERROR", job_id=job_id,
                                    reason_code=type(e).__name__)
                    raise
                if job.get("cancelled"):
                    raise _JobCancelled()
                t0 = time.monotonic()
                res = self.supervisor.transcribe(
                    job_id=job_id, attempt=job["attempt"],
                    audio_name=pathlib.Path(wav).name,
                    sample_rate=rate)
                if res.get("retried") and job_id:
                    self._bump_attempt(job, job_id)
                job["attempt"] = res.get("attempt", job["attempt"])
                # M02-AUDIT-09: the evidence context follows the job's
                # actual attempt; the ASR worker generation is recorded
                # for the ASR stage only.
                self.collector.note_attempt(
                    ctx, job["attempt"], stage="asr",
                    worker_generation=res.get("generation"))
                if job.get("cancelled"):
                    raise _JobCancelled()
                raw = res.get("text") or ""
                job["raw"] = raw
                asr_ms = res.get("duration_ms")
                job["asr_ms"] = asr_ms  # M13 usage fact stage timing
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
                # M04/M10 (Spec S10/S15): typed normalization between ASR
                # and cleanup, in this process (deterministic, model-free).
                # A normalization bug must never drop a dictation: any
                # exception passes the raw transcript through. The job's
                # own captured policy/context are used (M05 AC03: an
                # in-flight job keeps its vocabulary revision). Raw mode
                # (S15) skips the stage entirely — original ASR text,
                # no normalization beyond transport.
                m10 = job.get("m10") or {}
                wp = m10.get("wp")
                mode_is_raw = wp is not None and wp.effective_mode == "raw"
                norm_policy = job.get("norm_policy") or self._norm_policy
                norm_context = job.get("norm_context") or self._norm_context
                norm_text = raw
                norm_result = None
                if raw and not mode_is_raw \
                        and norm_policy is not None \
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
                    job["vocab_hits"] = len(vocab_rules)  # M13 usage fact
                    if vocab_rules and self._vocab is not None:
                        try:
                            self._vocab.record_hits(vocab_rules)
                        except Exception as e:
                            self.v2log.emit(
                                "vocabulary.hit_write_failed",
                                level="WARNING", job_id=job_id,
                                reason_code=type(e).__name__)
                    # M10: applied snippet expansions count as usage
                    # (statistics, never matching state).
                    snippet_rules = [e.rule_id for e in norm_result.edits
                                     if e.cls == "snippet" and e.rule_id] \
                        if norm_result is not None else []
                    job["snippet_hits"] = len(snippet_rules)  # M13 fact
                    if snippet_rules and self._snip_store is not None:
                        try:
                            self._snip_store.record_hits(snippet_rules)
                        except Exception as e:
                            self.v2log.emit(
                                "profiles.hit_write_failed",
                                level="WARNING", job_id=job_id,
                                reason_code=type(e).__name__)
                job["normalized"] = norm_text
                # M06 (S12): late provider results become a separately
                # identified downstream revision — composed from THIS
                # job's collection handle (a newer dictation's late
                # context can never be attributed to this job) and
                # recorded as such, never relabeled pre-decode
                # (M06-AC05).
                if ctx is not None and self._context is not None:
                    try:
                        late = self._context.take_downstream(
                            job.get("context_coll"))
                        if late is not None:
                            self.collector.on_context_snapshot(
                                ctx, late, downstream=True)
                    except Exception as e:
                        self.v2log.emit("training.capture_failed",
                                        level="ERROR", job_id=job_id,
                                        reason_code=type(e).__name__)
                if raw and not mode_is_raw:
                    self._job_state(job_id, "cleaning")
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
                    # M07/M10 (S13 permitted context): protected spans in
                    # normalized-text coordinates, the job's frozen
                    # scoped vocabulary and the destination profile.
                    # Nearby text never enters (contracts/context.md).
                    # M10 adds the GENERATED spans (snippet expansions
                    # and resolved filenames) — output-coordinate spans
                    # the cleanup must keep verbatim (S17 protection).
                    # Spans are (start, end, kind): dictated literals map
                    # through the normalization ledger; generated spans
                    # are exact ("generated"). Protection that cannot be
                    # built means cleanup would run unprotected — the job
                    # abstains from model cleanup instead.
                    prot_spans = []
                    protection_failed = False
                    try:
                        prot_spans = v2_cleanup.protected_spans_for_cleanup(
                            raw, norm_text,
                            norm_result.protected
                            if norm_result is not None else [],
                            norm_result.edits
                            if norm_result is not None else [])
                        if norm_result is not None:
                            prot_spans.extend(
                                (s, e, "generated") for s, e in
                                v2_snippets.protected_output_spans(
                                    norm_result,
                                    m10.get("snippet_snapshot")))
                    except Exception as e:
                        protection_failed = True
                        self.v2log.emit(
                            "cleanup.context_build_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)
                    vocab_snapshot = getattr(
                        job.get("norm_context"), "vocabulary", None)
                    vocab_pairs = []
                    try:
                        vocab_pairs = [
                            (alias, t.canonical)
                            for alias, t in vocab_snapshot.match_items()
                        ][:40] if vocab_snapshot is not None else []
                    except Exception as e:
                        self.v2log.emit(
                            "cleanup.context_build_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)
                    hint_set = job.get("hint_set")
                    relevant_vocab = [
                        t.canonical for t in hint_set.terms[:40]
                    ] if hint_set is not None else sorted(
                        {c for _, c in vocab_pairs})
                    # M10 (S15): the destination profile is the RESOLVED
                    # writing category (ai_prompt/coding/terminal/…)
                    # when the profile resolution ran; the raw M06
                    # category is the pre-M10 fallback.
                    dest_profile = None
                    if wp is not None and wp.category:
                        dest_profile = v2_profiles.hint_key(wp.category)
                    if dest_profile is None:
                        snap = job.get("context_snapshot")
                        if snap is not None and snap.target is not None:
                            dest_profile = snap.target.category or None
                    # The exact permitted-context payload for the S29.4
                    # cleanup family — retained as a lease-governed
                    # artifact (never envelope content).
                    job["cleanup_context_payload"] = {
                        "mode": "clean",
                        "locale": self.cfg.get("normalization_locale",
                                               "en-US"),
                        "destination_profile": dest_profile,
                        "relevant_vocabulary": relevant_vocab,
                        "vocabulary_pairs": vocab_pairs,
                        "structure_hints": v2_cleanup.prompts.structure_hints(
                            dest_profile),
                        "protected_span_texts": [
                            norm_text[s:e] for s, e, _k in prot_spans],
                        "protected_span_kinds": [
                            k for _s, _e, k in prot_spans],
                    }
                    if protection_failed:
                        res2 = {
                            "attempt": job["attempt"], "text": norm_text,
                            "path": "llm_fallback_normalized",
                            "fallback_reason": "protection_unmapped",
                            "duration_ms": 0.0, "observations": [],
                            "v2": {"stage": "normalized",
                                   "incomplete": False,
                                   "termination": {
                                       "kind": "protection_unmapped"}}}
                    else:
                        res2 = self.supervisor.clean(
                            job_id=job_id, attempt=job["attempt"],
                            raw_text=norm_text,
                            protected_spans=prot_spans or None,
                            relevant_vocabulary=relevant_vocab or None,
                            vocabulary_pairs=vocab_pairs or None,
                            destination_profile=dest_profile,
                            locale=self.cfg.get("normalization_locale",
                                                "en-US"))
                    if res2.get("retried") and job_id:
                        self._bump_attempt(job, job_id)
                    job["attempt"] = res2.get("attempt", job["attempt"])
                    self.collector.note_attempt(
                        ctx, job["attempt"], stage="cleanup",
                        worker_generation=res2.get("generation"))
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
                    # Raw mode (S15) and cleanup-off both insert the
                    # original text; the recorded path stays honest
                    # about which one produced it.
                    cleanup_path = "raw" if (
                        self.cfg["cleanup"] == "off" or mode_is_raw) \
                        else "basic_empty_input"
                    res2 = {}  # no cleanup pass ran; nothing to report
                # M13 usage facts: the pipeline's own stage observations
                # ride the job dict to the terminal-state writer.
                job["cleanup_ms"] = res2.get("duration_ms")
                job["cleanup_path"] = cleanup_path
                job["fallback_reason"] = res2.get("fallback_reason")
                try:
                    collecting = ctx is not None and ctx.collecting
                    if ctx is not None:
                        self.collector.on_cleanup_result(
                            ctx, text, path=cleanup_path,
                            fallback_reason=(
                                res2.get("fallback_reason")
                                if raw else None),
                            v2=(res2.get("v2") if raw else None),
                            cleanup_context=(
                                job.get("cleanup_context_payload")
                                if raw else None))
                    # M11 (S16): the transform executor — the CLEAN
                    # artifact is already recorded above (retained,
                    # AC04); the transform runs before insertion and
                    # before finalize so its evidence rides the same
                    # revision. The insert text becomes the transform
                    # output only when validated (path applied).
                    clean_text = text
                    if wp is not None and wp.mode not in ("raw", "clean"):
                        if self.cfg["cleanup"] == "llm":
                            text = self._m11_apply_transform(
                                job, clean_text, ctx)
                        else:
                            # No LLM cleanup pass, no Clean intermediate
                            # to retain (S16) — the transform is honestly
                            # not run rather than rewriting an
                            # unretained base.
                            job["transform_note"] = \
                                "transform_requires_cleanup"
                            if ctx is not None:
                                self.collector.note_transform_gate(
                                    ctx, "transform_requires_cleanup")
                            self.v2log.emit(
                                "transforms.not_applied", level="INFO",
                                job_id=job_id,
                                reason_code="transform_requires_cleanup")
                    if ctx is not None:
                        self.collector.finalize(ctx)
                    if raw and self.cfg["log_transcripts"] and not collecting:
                        # Collection disabled: the user's existing transcript
                        # logging choice still keeps text in the private
                        # store under a history lease (Spec S07). The
                        # cleanup stage's applied output is the CLEAN
                        # text even when a transform follows.
                        self.store.write_text_artifact(
                            job_id=job_id, stage="asr", role="raw_transcript",
                            text=raw, retention_class="history")
                        if clean_text is not None:
                            self.store.write_text_artifact(
                                job_id=job_id, stage="cleanup",
                                role="applied_output", text=clean_text,
                                retention_class="history",
                                meta={"cleanup_path": cleanup_path})
                    # M11: a dictation transform applied pre-insertion
                    # keeps its own History stage artifact (the Clean
                    # output above stays the cleanup stage's output).
                    tf_result = job.get("transform_result")
                    if tf_result is not None \
                            and tf_result.path == v2_transforms.PATH_APPLIED \
                            and not collecting \
                            and self.cfg["log_transcripts"]:
                        self.store.write_text_artifact(
                            job_id=job_id, stage="transform",
                            role="transform_output",
                            text=tf_result.output,
                            retention_class="history",
                            meta={"transform_id":
                                  tf_result.job.transform_id,
                                  "transform_revision":
                                  tf_result.job.transform_revision})
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
                # M03-AUDIT-05: the attempt that actually executed — even
                # one that produced no result — is acknowledged before any
                # failure evidence, recovery item or usage fact is written.
                self._acknowledge_executed_attempt(job, ctx, e)
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
    def _acknowledge_executed_attempt(self, job, ctx, err):
        executed = getattr(err, "attempt", None)
        if not isinstance(executed, int) or isinstance(executed, bool):
            return
        job_id = job.get("job_id")
        if executed > int(job.get("attempt") or 1):
            job["attempt"] = executed
            if job_id:
                try:
                    self.store.bump_job_attempt(job_id, at_least=executed)
                except Exception as e:
                    self.v2log.emit("store.state_write_failed",
                                    level="WARNING", job_id=job_id,
                                    reason_code=type(e).__name__)
        stage = {"transcribe": "asr", "clean": "cleanup"}.get(err.stage)
        try:
            self.collector.note_attempt(
                ctx, job["attempt"], stage=stage,
                worker_generation=getattr(err, "generation", None))
        except Exception:
            pass

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
        if not job.get("wav") or job.get("deleted"):
            return
        self._last_failed = {
            "job_id": job.get("job_id"), "family_id": job.get("family_id"),
            "wav": job["wav"], "raw": job.get("raw"),
            "attempt": int(job.get("attempt", 1) or 1)}
        AppHelper.callAfter(self._refresh_recovery_menu)

    @objc.python_method
    def _delete_journal_files(self, job_id, job=None):
        """A resolved job's journal files go eagerly. The job's journal
        writer (if any) loses creation authority first, so a writer that
        finishes late can never recreate the ``.blk`` (M03-AUDIT-01/02)."""
        if not job_id:
            return
        journal = (job or {}).get("journal")
        if journal is not None:
            try:
                journal.close_discard(join_timeout=0)
            except Exception:
                pass

        def _rm():
            for p in V2_JOURNAL.glob(f"job-{job_id}.*"):
                try:
                    p.unlink(missing_ok=True)
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
    def _dump_audio(self, audio, job_id=None, rate=None):
        # M02-AUDIT-02: the debug copy is named by its job so
        # delete-everywhere (registered in configure) removes it too.
        # M03-AUDIT-02: written INSIDE the store's deletion arbitration —
        # a check-then-write could still lose to a delete in between.
        try:
            if job_id and self.store.job_deleted(job_id):
                return  # never recreate a deleted job's audio copy
            self._dump_seq += 1
            seq = self._dump_seq
            rate = int(rate or self.cfg["sample_rate"])

            def write():
                v2_debug_audio.write_debug_copy(
                    AUDIO_DEBUG_DIR, job_id, audio, rate,
                    keep=AUDIO_DEBUG_KEEP, seq=seq)
            if job_id:
                self.store.run_unless_deleted(job_id, write)
            else:
                write()
        except Exception as e:
            self.v2log.emit("capture.debug_audio_failed", level="WARNING",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _finishWithText_(self, text, job):
        job_id, ctx = job["job_id"], job["ctx"]
        if job.get("cancelled"):
            # Cancelled mid-processing: whatever the worker returned, it
            # lost insertion authority the moment the user cancelled. The
            # coordinator is done with the wav by now, so the journal files
            # can finally go.
            self._retire_active_job(job)
            if job_id:
                self.v2log.emit("insertion.skipped", level="INFO",
                                job_id=job_id,
                                reason_code="job_deleted"
                                if job.get("deleted") else "user_cancelled")
            if not job.get("deleted"):
                # A deleted job gets no new usage fact (M03-AUDIT-02).
                self._record_dictation_usage(job, "cancelled")
            self._delete_journal_files(job_id, job)
            self._settle_state()
            return
        if job.get("failed"):
            self._retire_active_job(job)
            self._record_dictation_usage(job, "failed")
            self._show_failed_pill()
        elif text:
            if self.cfg["append_space"] and not text.endswith(("\n", " ")):
                text += " "
            job["final_text"] = text  # the usage fact's final words
            # M12 (Spec S20): a note-bound dictation delivers into the
            # Scratchpad editor — an internal destination. The M08
            # external queue is never involved, so a note dictation can
            # never overwrite an external target; if the note closed
            # mid-dictation the text routes to the clipboard offer,
            # never a paste into whatever app is now focused.
            note_target = job.get("note_target")
            if note_target is not None:
                delivered = False
                try:
                    delivered = (
                        self._hub is not None
                        and self._hub.scratchpad_receive(text, job))
                except Exception as e:
                    self.v2log.emit("notes.receive_failed",
                                    level="WARNING", job_id=job_id,
                                    reason_code=type(e).__name__)
                self._retire_active_job(job)
                if delivered:
                    if job_id:
                        self.v2log.emit(
                            "notes.dictation_inserted", level="INFO",
                            job_id=job_id,
                            detail=f"note={note_target['note_id']}"
                                   f" {len(text)} chars")
                        self._job_state(job_id, "insertion_posted")
                        self._job_state(job_id, "insertion_confirmed",
                                        reason="scratchpad_note")
                    # The internal destination is still ONE logical
                    # dictation (M13-AC02): one fact, outcome confirmed.
                    self._record_dictation_usage(
                        job, "confirmed", text, end_to_end=True,
                        meta={"destination": "scratchpad_note"})
                    if ctx is not None:
                        try:
                            self.collector.on_insertion(ctx, True,
                                                        len(text))
                        except Exception as e:
                            self.v2log.emit(
                                "training.capture_failed", level="ERROR",
                                job_id=job_id,
                                reason_code=type(e).__name__)
                else:
                    copy_text(text)
                    if job_id:
                        self.v2log.emit(
                            "insertion.saved_not_inserted", level="WARNING",
                            job_id=job_id, outcome="saved_not_inserted",
                            reason_code="note_closed_during_dictation",
                            detail="transcript left on the clipboard for"
                                   " a manual ⌘V")
                        self._job_state(job_id, "saved_not_inserted",
                                        reason="note_closed_during_dictation")
                    self._record_dictation_usage(
                        job, "saved_not_inserted", text,
                        meta={"reason": "note_closed_during_dictation"})
                    if ctx is not None:
                        try:
                            self.collector.on_insertion(ctx, False, 0)
                        except Exception as e:
                            self.v2log.emit(
                                "training.capture_failed", level="ERROR",
                                job_id=job_id,
                                reason_code=type(e).__name__)
                self._delete_journal_files(job_id, job)
                self._settle_state()
                return
            # M08 (S18): the text branch hands off to the serialized
            # insertion queue — the job stays active (cancel authority
            # holds until the transaction starts) and settles in
            # _insertionDone_ on the main thread. No AX call, pasteboard
            # write or settle sleep ever runs on this UI callback.
            if self._insertion is None:
                copy_text(text)
                if job_id:
                    self.v2log.emit(
                        "insertion.saved_not_inserted", level="WARNING",
                        job_id=job_id, outcome="saved_not_inserted",
                        reason_code="insertion_service_unavailable",
                        detail="transcript left on the clipboard for a"
                               " manual ⌘V")
                    self._job_state(job_id, "saved_not_inserted",
                                    reason="insertion_service_unavailable")
                self._record_dictation_usage(
                    job, "saved_not_inserted", text,
                    meta={"reason": "insertion_service_unavailable"})
                if ctx is not None:
                    self.collector.on_insertion(ctx, False, 0)
                # M03-AUDIT-17: no insertion callback will ever arrive for
                # this synchronous fallback — it retires its own job. The
                # recovery audio stays (saved-not-inserted policy).
                self._retire_active_job(job)
                self._settle_state()
                return
            self._insertion.submit(
                text, job,
                on_done=lambda result, j=job: AppHelper.callAfter(
                    self._insertionDone_, result, j),
                on_observation=lambda info, j=job: AppHelper.callAfter(
                    self._observationStarted_, info, j))
            return
        else:
            self._retire_active_job(job)
            if job_id:
                reason = ("cleanup_emptied_output"
                          if job.get("raw") else "empty_transcription")
                self.v2log.emit("insertion.skipped", level="INFO",
                                job_id=job_id,
                                reason_code=reason)
                self._job_state(job_id, "saved_not_inserted",
                                reason=reason)
                # An empty transcription is an honest zero-word fact —
                # it still counts as one logical dictation attempt.
                self._record_dictation_usage(
                    job, "saved_not_inserted", text or "",
                    meta={"reason": reason})
            if ctx is not None:
                try:
                    self.collector.on_insertion(ctx, False, 0)
                except Exception as e:
                    self.v2log.emit("training.capture_failed", level="ERROR",
                                    job_id=job_id,
                                    reason_code=type(e).__name__)
            self._delete_journal_files(job_id, job)
        if job.get("failed"):
            # The failed pill stays up briefly; its timer settles the state
            # machine so the failure is actually visible.
            return
        self._settle_state()

    @objc.python_method
    def _record_dictation_usage(self, job, outcome, final_text=None,
                                *, meta=None, end_to_end=False):
        """M13: write the job's usage fact at its terminal outcome
        (Spec S08/S21, contracts/analytics.md). One fact per logical
        dictation — the store upserts on job_id, so a retry reaching a
        terminal outcome again REPLACES the row (M13-AC02: retries and
        replays never increment dictated words twice). Guarded: an
        analytics failure never disturbs the dictation path."""
        if self._analytics is None:
            return
        job_id = job.get("job_id")
        if not job_id:
            return
        try:
            m10 = job.get("m10") or {}
            wp = m10.get("wp")
            tf = job.get("transform_result")
            tf_job = getattr(tf, "job", None) if tf is not None else None
            released = job.get("released_mono")
            e2e = None
            if end_to_end and released is not None:
                # Parent-monotonic PTT release → terminal outcome (E06:
                # end-to-end; stage timings stay separate).
                e2e = round((time.monotonic() - released) * 1000.0, 1)
            stats = job.get("stats") or {}
            captured = job.get("captured_at_utc")
            raw = job.get("raw")
            # Words: the acoustic original and what actually shipped.
            # Cancelled/failed jobs keep final None — unknown, never 0.
            final_words = None
            if outcome in ("confirmed", "posted_unverified",
                           "saved_not_inserted"):
                final_words = v2.analytics.word_count(final_text)
            # No instant fallback: a job without a capture instant is
            # refused by the store (never parked on a fabricated today).
            self._analytics.record_dictation_fact(
                job_id=job_id,
                activity_at_utc=captured,
                timezone=job.get("timezone"),
                utc_offset_minutes=job.get("utc_offset_minutes"),
                time_quality="known" if captured else "unknown",
                duration_sec=stats.get("duration_sec"),
                raw_words=v2.analytics.word_count(raw),
                final_words=final_words,
                cleanup_path=job.get("cleanup_path"),
                fallback_reason=job.get("fallback_reason"),
                mode=(wp.effective_mode if wp is not None else "clean"),
                profile_name=(wp.profile_name if wp is not None else None),
                app_name=job.get("app_name"),
                app_bundle=job.get("app_bundle"),
                insertion_outcome=outcome,
                asr_ms=job.get("asr_ms"),
                cleanup_ms=job.get("cleanup_ms"),
                transform_ms=(getattr(tf, "duration_ms", None)
                              if tf is not None else None),
                end_to_end_ms=e2e,
                dictionary_hits=job.get("vocab_hits") or 0,
                snippet_hits=job.get("snippet_hits") or 0,
                transform_id=(getattr(tf_job, "transform_id", None)
                              if tf_job is not None else None),
                task_key=(tf_job.task_key() if tf_job is not None
                          and hasattr(tf_job, "task_key") else None),
                transform_path=(getattr(tf, "path", None)
                                if tf is not None else None),
                attempt=job.get("attempt", 1),
                meta=meta)
        except Exception as e:
            self.v2log.emit("usage.record_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)

    @objc.python_method
    def _retire_active_job(self, job):
        """One job leaves the active set exactly once, in whichever
        branch terminates it (the text branch defers this to
        _insertionDone_ so cancel authority holds until the insertion
        transaction starts)."""
        self._pending -= 1
        if job in self._active_jobs:
            self._active_jobs.remove(job)

    @objc.python_method
    def _insertionDone_(self, result, job):
        """The insertion transaction finished (main thread): record the
        honest outcome state, evidence and journal policy. Confirmed and
        posted results consumed the artifact; every other terminal state
        keeps the recovery audio for retry."""
        self._retire_active_job(job)
        job_id, ctx = job["job_id"], job["ctx"]
        if job.get("cancelled"):
            # Cancel landed between coordinator finish and transaction
            # start: the service refused it; authority was already gone.
            if result.reason_code == "user_cancelled":
                if job_id:
                    self.v2log.emit("insertion.skipped", level="INFO",
                                    job_id=job_id,
                                    reason_code="user_cancelled")
                if not job.get("deleted"):
                    self._record_dictation_usage(job, "cancelled")
                self._delete_journal_files(job_id, job)
                self._settle_state()
                return
            # Cancel landed MID-transaction: the insert physically ran
            # (possibly confirmed) — record it honestly instead of
            # discarding the evidence; the job's cancelled state stands.
            if job_id:
                self.v2log.emit(
                    "insertion.cancelled_after_insert", level="WARNING",
                    job_id=job_id, outcome=result.state,
                    reason_code="user_cancelled_mid_transaction")
                self._record_dictation_usage(
                    job, "cancelled",
                    meta={"after_insert_state": result.state})
            if ctx is not None:
                try:
                    self.collector.on_insertion_result(ctx, result)
                except Exception as e:
                    self.v2log.emit("training.capture_failed",
                                    level="ERROR", job_id=job_id,
                                    reason_code=type(e).__name__)
            self._settle_state()
            return
        state = result.state
        if state == "confirmed":
            if job_id:
                self.v2log.emit("insertion.confirmed", level="INFO",
                                job_id=job_id, outcome="confirmed",
                                detail=f"{result.inserted_chars} chars,"
                                       f" method {result.method}")
                self._job_state(job_id, "insertion_posted")
                self._job_state(job_id, "insertion_confirmed")
            self._record_dictation_usage(
                job, "confirmed", job.get("final_text"),
                end_to_end=True,
                meta={"method": result.method})
        elif state == "posted_unverified":
            if job_id:
                self.v2log.emit(
                    "insertion.posted", level="INFO", job_id=job_id,
                    outcome="posted_unverified",
                    reason_code=result.reason_code
                    or "readback_unavailable",
                    detail=f"{result.inserted_chars} chars,"
                           f" method {result.method}")
                self._job_state(job_id, "insertion_posted")
                self._job_state(job_id, "insertion_unverified",
                                reason=result.reason_code
                                or "readback_unavailable")
            # Posted but unverified: the end-to-end clock stops at the
            # terminal outcome, with the unverified reason in meta —
            # never presented as target-confirmed latency (E06).
            self._record_dictation_usage(
                job, "posted_unverified", job.get("final_text"),
                end_to_end=True,
                meta={"reason": result.reason_code
                      or "readback_unavailable"})
        else:
            reason = result.reason_code or state
            if job_id:
                event = {"target_changed": "insertion.target_changed",
                         "saved_not_inserted": "insertion.saved_not_inserted",
                         "failed": "insertion.failed"}[state]
                self.v2log.emit(
                    event, level="WARNING" if state != "target_changed"
                    else "INFO", job_id=job_id, outcome=state,
                    reason_code=reason)
                self._job_state(job_id, "saved_not_inserted", reason=reason)
            self._record_dictation_usage(
                job, "saved_not_inserted", job.get("final_text"),
                meta={"insertion_state": state, "reason": reason})
        if ctx is not None:
            # Evidence outcome revision: posted/confirmed/unknown stay
            # independent of correctness labels (S29.8). The
            # observation-start callback is dispatched before this one
            # (the service fires it inside the transaction), so a
            # started window rides the same revision; its close
            # appends the final observation block.
            try:
                self.collector.on_insertion_result(
                    ctx, result,
                    observation=({"observer": self._starting_observation}
                                 if self._starting_observation else None))
            except Exception as e:
                self.v2log.emit("training.capture_failed", level="ERROR",
                                job_id=job_id,
                                reason_code=type(e).__name__)
        self._starting_observation = None
        if state in ("confirmed", "posted_unverified"):
            self._delete_journal_files(job_id, job)
        self._settle_state()

    @objc.python_method
    def _observationStarted_(self, info, job):
        """S29.8 window opened on a certified surface: keep the observer
        referenced (the insert-time evidence revision picks it up) and
        wire its close back to the evidence collector."""
        obs = info.get("observer")
        if obs is None:
            return
        self._observers.append(obs)
        self._starting_observation = obs
        ctx = job.get("ctx")
        result = info.get("insertion")
        if obs.stop_reason is not None:
            # The window already closed before this callback ran (e.g.
            # an instant focus loss): finish it here so the final
            # revision is not lost to the race.
            self._observationFinished_(obs, result, job, ctx)
            return
        obs.on_closed = lambda: AppHelper.callAfter(
            self._observationFinished_, obs, result, job, ctx)

    @objc.python_method
    def _observationFinished_(self, obs, result, job, ctx):
        if obs in self._observers:
            self._observers.remove(obs)
        if ctx is None:
            return
        try:
            self.collector.on_observation_closed(ctx, result, obs)
        except Exception as e:
            self.v2log.emit("training.capture_failed", level="ERROR",
                            job_id=job.get("job_id"),
                            reason_code=type(e).__name__)

    @objc.python_method
    def _armInjectingClear_(self):
        # The synthetic ⌘V events were posted from the insertion thread;
        # clear the guard shortly after they land (same timing as the
        # pre-M08 inline paste).
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.25, self, "clearInjecting:", None, False)

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
        # A Hub open request that arrived mid-transaction runs now that
        # the pipeline has settled (no focus steal during insertion);
        # every _insertionDone_ branch lands here.
        self._flush_pending_hub_show()

    def clearInjecting_(self, timer):
        self._injecting = False
        self._flush_pending_hub_show()

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

        # M10 (Spec S15): the effective mode/profile exposure — the
        # quick-menu half of "always expose the effective mode/profile
        # in the pill or quick menu". The line updates per dictation
        # (_set_mode_menu); the override submenu is the S15 one-job
        # override ("Next dictation: …"), consumed by the next capture.
        self.mode_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Mode: Clean · profile default · global_default", None, ""
        )
        self.mode_menu_item.setEnabled_(False)
        menu.addItem_(self.mode_menu_item)
        mode_menu = NSMenu.alloc().init()
        for title, mode in (
                ("Default (rules apply)", None),
                ("Raw", "raw"),
                ("Clean", "clean")):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "setNextJobMode:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(mode)
            mode_menu.addItem_(item)
        mode_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Next Dictation Mode", None, ""
        )
        mode_item.setSubmenu_(mode_menu)
        menu.addItem_(mode_item)

        # The Hub (Spec S19, M09): history, diagnostics, models/training
        # data and settings in one native window; closing it never quits
        # the menu-bar service.
        hub_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Hub…", "openHub:", "l"
        )
        hub_item.setTarget_(self)
        menu.addItem_(hub_item)

        # M12 (Spec S20): quick-open — Hub + Scratchpad + a fresh note
        # in one action, behind the same focus-steal guard as Open Hub
        # (a quick-open must never steal the external insertion
        # target). The key equivalent is the menu's own; a global
        # hotkey grab stays out (the S16 binding discipline).
        scratchpad_item = NSMenuItem.alloc()\
            .initWithTitle_action_keyEquivalent_(
                "Quick Open Scratchpad", "quickOpenScratchpad_", "n")
        scratchpad_item.setTarget_(self)
        menu.addItem_(scratchpad_item)

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
            ("Undo Last Insertion", "undoLastInsertion:"),
            ("Paste Last Result Again", "pasteLastResultAgain:"),
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

        # M11 (Spec S16): explicit selected-text transforms. The
        # submenu rebuilds on open (menuNeedsUpdate_) so store edits in
        # the Hub surface without a restart; key equivalents are the
        # definitions' registered single-char shortcuts (collision-
        # checked at write time; the legacy keys 1/2 are never bound).
        self.transforms_menu = NSMenu.alloc().init()
        self.transforms_menu.setDelegate_(self)
        transforms_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Transforms", None, "")
        transforms_item.setSubmenu_(self.transforms_menu)
        menu.addItem_(transforms_item)

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

    def setNextJobMode_(self, sender):
        """The S15 one-job override: the next dictation runs in the
        chosen mode regardless of rules; consumed by that one job."""
        self._next_job_mode = sender.representedObject() or None
        self.v2log.emit("profiles.override_set", level="INFO",
                        reason_code="menu_action",
                        outcome=self._next_job_mode or "default")

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

    # ---- Hub (Spec S19, M09) ----------------------------------------------

    def openHub_(self, sender):
        """Single-instance Hub activation. Deferred, never denied, while
        an insertion transaction is in flight: activating a window mid-
        transaction would flip the frontmost app under the paste (the
        M09 regression requirement — window actions do not steal focus
        during insertion)."""
        if self._hub_blocks_show():
            self._hub_show_pending = True
            self.v2log.emit("hub.show_deferred", level="INFO",
                            reason_code="insertion_in_flight")
            return
        try:
            if self._hub is None:
                from .v2 import ui as v2_ui
                from .v2 import history_queries, training_data
                self._hub = v2_ui.HubController.alloc().initWithSpec_({
                    "store": self.store,
                    "history_service": history_queries.HistoryQueryService(
                        self.store),
                    "training_service": training_data.TrainingDataService(
                        self.store, emit=self.v2log.emit),
                    "styles_service": self._styles,
                    "snippets_service": self._snip_store,
                    "transforms_service": self._tf_store,
                    "notes_service": self._notes_store,
                    "insights_service": self._insights,
                    "learning_service": self._learning,
                    "review_service": self._review,
                    "sampling_service": self._sampling,
                    "splits_service": self._splits,
                    "profile_service": self._profile,
                    "export_service": self._exporter,
                    "transforms_store": self._tf_store,
                    "diagnostics_provider": self._hub_diagnostics_spec,
                    "coordinator": self,
                    "replay": v2_ui.ReplayService(),
                    "capabilities": self._capability_manifest,
                })
            self._hub.showWindow_(sender)
        except Exception as e:
            self.v2log.emit("hub.open_failed", level="WARNING",
                            reason_code=type(e).__name__)

    @objc.python_method
    def _hub_diagnostics_spec(self):
        return {"events_dir": V2_EVENTS_DIR,
                "pipeline_info": self._pipeline_info(),
                "engine_states": dict(self.supervisor.engine_state),
                "last": 500}

    @objc.python_method
    def _hub_blocks_show(self) -> bool:
        # getattr keeps the shared test harnesses' insertion stubs valid.
        # Recording is included: activating the Hub mid-capture would
        # flip the destination under the release-time insert.
        return self.state == STATE_RECORDING or self._injecting or (
            self._insertion is not None
            and bool(getattr(self._insertion, "busy", False)))

    @objc.python_method
    def _flush_pending_hub_show(self):
        if self._hub_show_pending and not self._hub_blocks_show():
            self._hub_show_pending = False
            action = self._hub_pending_action
            self._hub_pending_action = None
            self.openHub_(None)
            if action == "scratchpad" and self._hub is not None:
                try:
                    self._hub.scratchpad_quick_open()
                except Exception as e:
                    self.v2log.emit("notes.quick_open_failed",
                                    level="WARNING",
                                    reason_code=type(e).__name__)

    # Coordinator command surface the Hub calls (contract hub.md): the
    # shell owns no data logic and never writes into target apps.

    @objc.python_method
    def hubEngineStates(self):
        return dict(self.supervisor.engine_state)

    @objc.python_method
    def hubRecoveryInfo(self):
        return {"last_failed": self._last_failed is not None,
                "recoverable": len(self._recoverable)}

    @objc.python_method
    def collection_state(self):
        return self.consent.state()

    @objc.python_method
    def hubRetentionDays(self):
        return dict(self.store.retention_days)

    @objc.python_method
    def hubCopyText(self, text):
        copy_text(text)
        self.v2log.emit("hub.text_copied", level="INFO",
                        reason_code="history_action",
                        detail=f"{len(text)} chars")

    @objc.python_method
    def hubPasteText(self, text, job_id=None):
        """History's Paste Again: the M08 reconcile-then-submit engine
        under explicit user intent. Refused while recording or mid-
        transaction (never steals focus from an insert in flight). The
        selected row's job id rides along so the insertion row and any
        observation stay attributed (contracts/insertion.md)."""
        if self.state == STATE_RECORDING:
            return {"outcome": "recording"}
        if self._hub_blocks_show():
            return {"outcome": "insertion_in_flight"}
        if self._insertion is None:
            self.hubCopyText(text)
            return {"outcome": "copy_only_no_service"}
        paste = getattr(self._insertion, "paste_text", None)
        if paste is None:
            # The shared test harnesses stub _insertion without the M09
            # entry point; production always has it.
            self.hubCopyText(text)
            return {"outcome": "copy_only"}
        # The AX path fires no ⌘V guard timer, so the deferred-Hub-show
        # flush rides the transaction's completion instead.
        def _repaste_done(r, _job_id=job_id):
            # M13: a re-paste is its own activity row — never a second
            # dictation word count (M13-AC02). Guarded like every
            # analytics write.
            if self._analytics is not None:
                try:
                    self._analytics.record_repaste_fact(
                        job_id=_job_id,
                        meta={"state": getattr(r, "state", None)})
                except Exception as e:
                    self.v2log.emit("usage.record_failed",
                                    level="WARNING",
                                    reason_code=type(e).__name__)
            AppHelper.callAfter(self._flush_pending_hub_show)
        return paste(text, job_id=job_id, on_done=_repaste_done)

    @objc.python_method
    def hubRetryJob(self, job_id):
        """Retry one failed job from its History row, through the same
        coordinator path the Recovery menu uses. Only ``failed_
        recoverable`` jobs with live recovery audio retry — anything
        else reports why instead of requeueing (a double click must
        never insert the same dictation twice)."""
        if self.state == STATE_RECORDING:
            return {"outcome": "recording"}
        if any(j.get("job_id") == job_id for j in self._active_jobs):
            return {"outcome": "already_retrying"}
        if self._job_is_deleted(job_id):
            return {"outcome": "not_retryable", "reason": "deleted"}
        row = self.store.job(job_id) or {}
        if row.get("state") != "failed_recoverable":
            return {"outcome": "not_retryable",
                    "reason": row.get("state") or "unknown_job"}
        for info in ([self._last_failed] if self._last_failed else []) \
                + list(self._recoverable):
            if info and info.get("job_id") == job_id:
                wav = pathlib.Path(info.get("wav") or "")
                if not wav.exists():
                    return {"outcome": "audio_unavailable",
                            "reason": "recovery audio expired"}
                return self._retry_job(info)
        # Not the in-memory last-failed set: only retryable if recovery
        # audio still exists under the journal root (contracts/store.md
        # — it expires by mtime, and missing audio is labeled
        # unavailable, never fabricated).
        wav = V2_JOURNAL / f"job-{job_id}.wav"
        if wav.exists():
            return self._retry_job({
                "job_id": job_id, "family_id": row.get("family_id"),
                "wav": str(wav), "raw": None,
                "attempt": row.get("attempt", 1) or 1})
        return {"outcome": "audio_unavailable",
                "reason": "no recovery audio for job"}

    @objc.python_method
    def hubSetCollection(self, new_state):
        self.consent.set(new_state, note="hub settings")
        self._refresh_training_menu()

    @objc.python_method
    def hubEffectiveProfile(self):
        """M10 (S15): the Styles view's live panel — the last resolved
        writing profile plus the store/service availability behind it.
        Honest about services being off (a store failure is a reason,
        not a hidden default)."""
        wp = None
        if getattr(self, "_job", None) is not None \
                and isinstance(self._job, dict):
            wp = (self._job.get("m10") or {}).get("wp")
        if wp is None:
            wp = getattr(self, "_last_wp", None)  # survives job end
        return {
            "profile": wp.to_json() if wp is not None else None,
            "styles_available": self._styles is not None,
            "snippets_available": self._snip_store is not None,
            "next_job_mode": self._next_job_mode,
            "categories": list(v2_profiles.CATEGORIES),
            "modes": list(v2_profiles.MODES),
            "executable_modes": list(v2_profiles.EXECUTABLE_MODES),
        }

    @objc.python_method
    def hubSetNextJobMode(self, mode):
        if mode not in (None, *v2_profiles.MODES):
            return {"outcome": "unknown_mode"}
        self._next_job_mode = mode
        return {"outcome": "set"}

    @objc.python_method
    def hubPreviewPhrase(self, text):
        """M10 Styles/Snippets sandbox: what the CURRENT frozen
        registries and the resolved style's normalization policy would
        do to a phrase — pure local computation, no pipeline touch, no
        hit recording (the M05 sandbox_pattern, now style- and
        snippet-aware)."""
        if not text:
            return {"input": "", "output": "", "changed": False,
                    "edits": [], "rejected": []}
        base = self._norm_policy
        m10_policy, m10_context = base, self._norm_context
        try:
            wp = (self._norm_preview_profile() or {}).get("wp")
            if wp is not None and wp.number_policy != "inherit" \
                    and base is not None:
                m10_policy = v2_normalize.NormalizationPolicy(
                    locale=base.locale, profile=wp.number_policy,
                    registered_skills=dict(base.registered_skills))
            if m10_context is not None:
                m10_context = dataclasses.replace(
                    m10_context,
                    snippets=self._snippet_snapshot,
                    file_resolver=getattr(self, "_last_file_resolver",
                                          None))
        except Exception:
            m10_policy, m10_context = base, self._norm_context
        try:
            res = v2_normalize.normalize(text, m10_policy, m10_context)
        except Exception as e:
            return {"input": text, "error": type(e).__name__}
        return {
            "input": text, "output": res.text,
            "changed": res.text != text,
            "policy_revision": res.policy_revision,
            "edits": [
                {"before": e.input_text, "after": e.output_text,
                 "cls": e.cls, "rule_id": e.rule_id}
                for e in res.edits],
            "rejected": [
                {"before": r.input_text, "cls": r.cls,
                 "reason": r.reason}
                for r in res.rejected],
        }

    @objc.python_method
    def _norm_preview_profile(self):
        """The last job's frozen m10 state, if one is still around (the
        preview explains the policy a real destination resolved)."""
        job = getattr(self, "_job", None)
        if isinstance(job, dict) and job.get("m10") is not None:
            return job["m10"]
        return None

    @objc.python_method
    def hubSnippetCollisionPreview(self, trigger):
        """S17 collision preview for a trigger against dictionary
        aliases and the currently registered skills — before the edit
        lands. Pure computation over live state."""
        try:
            candidate = v2_snippets.Snippet(
                snippet_id="preview", trigger=trigger,
                name="preview", content="")
        except ValueError as e:
            return [{"kind": "invalid_trigger", "trigger": trigger,
                     "detail": str(e)}]
        entries = []
        if self._vocab is not None:
            try:
                entries = self._vocab.entries()
            except Exception:
                entries = []
        skills = dict(self._norm_policy.registered_skills) \
            if self._norm_policy is not None else {}
        stored = []
        if self._snip_store is not None:
            try:
                stored = self._snip_store.snippets()
            except Exception:
                stored = []
        return v2_snippets.preview_conflicts(
            candidate, stored, entries, skills)

    @objc.python_method
    def hubApplyRetention(self, values):
        """Apply the five store retention knobs now and persist them to
        the user config override. Only these five keys are written into
        the override (merged over its existing content) — a full-config
        freeze would silently pin values inherited from env/config
        files on later launches."""
        keys = ("transcript", "audio_success", "audio_failed",
                "metadata", "training_buffer")
        cfg_keys = ("retention_transcript_days",
                    "retention_audio_success_days",
                    "retention_audio_failed_days",
                    "retention_metadata_days", "training_buffer_days")
        # M02-AUDIT-19: the same validation as startup; an invalid knob
        # changes nothing (no destructive zero/negative window).
        checked = [config_mod.validate_retention_value(k, v)
                   for k, v in zip(cfg_keys, values)]
        if any(v is None for v in checked):
            self.v2log.emit("hub.retention_rejected", level="WARNING",
                            reason_code="out_of_range_or_not_integer")
            return {"outcome": "invalid"}
        values = checked
        for key, cfg_key, value in zip(keys, cfg_keys, values):
            self.store.retention_days[key] = int(value)
            self.cfg[cfg_key] = int(value)
        try:
            override = {}
            path = config_mod.user_override_path()
            try:
                override = json.loads(path.read_text())
            except (OSError, ValueError):
                override = {}
            for cfg_key, value in zip(cfg_keys, values):
                override[cfg_key] = int(value)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(override, ensure_ascii=False,
                                       indent=1), encoding="utf-8")
        except Exception as e:
            self.v2log.emit("hub.settings_write_failed", level="WARNING",
                            reason_code=type(e).__name__)
            return {"outcome": "not_persisted"}
        self.v2log.emit("hub.retention_applied", level="INFO",
                        reason_code="settings",
                        detail="/".join(str(v) for v in values))
        return {"outcome": "applied"}

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

    def menuNeedsUpdate_(self, menu):
        """Rebuild the Transforms submenu on open so Hub edits surface
        without a restart (definitions, enabled state, shortcuts)."""
        if menu is not self.transforms_menu:
            return
        menu.removeAllItems()
        snapshot = self._transforms_snapshot()
        defs = list(snapshot.definitions) if snapshot is not None else []
        if not defs:
            hint = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "No transforms configured (Hub → Transforms)", None, "")
            hint.setEnabled_(False)
            menu.addItem_(hint)
            return
        for d in defs:
            title = f"{d.name} ({d.mode})"
            if d.origin == "legacy":
                title += " — legacy"
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "runTransform:", d.shortcut or "")
            item.setTarget_(self)
            item.setRepresentedObject_(d.transform_id)
            menu.addItem_(item)

    def retryLastFailed_(self, sender):
        if self.state == STATE_RECORDING:
            return  # never clobber an active capture from the menu
        info = self._last_failed
        if info is None and self._recoverable:
            info = self._recoverable[-1]
        if info is None:
            return
        self._retry_job(info)

    @objc.python_method
    def _retry_job(self, info):
        """The one retry path (menu and the Hub's History row share it):
        re-arm the breaker, re-read the recovery audio, re-open the
        failed job with the next attempt and requeue it through the
        coordinator. The retry re-processes the ORIGINAL capture
        (M03-AUDIT-09): its capture instant, actual sample rate and known
        discontinuities come from the job row and the capture-provenance
        sidecar — never from the retry's clock or today's config."""
        job_id = info.get("job_id")
        family_id = info.get("family_id")
        if getattr(self, "_closing", False):
            return {"outcome": "closing"}
        if self._job_is_deleted(job_id):
            # Deleted work is never re-run or re-delivered (M03-AUDIT-02).
            self._drop_recovery_item(job_id)
            return {"outcome": "not_retryable", "reason": "deleted"}
        row = (self.store.job(job_id) or {}) if job_id else {}
        if job_id and row and row.get("state") != "failed_recoverable":
            # Only a failed_recoverable job re-opens; a resolved job's
            # leftover audio is never re-run from the menu either.
            self._drop_recovery_item(job_id)
            return {"outcome": "not_retryable",
                    "reason": row.get("state") or "unknown_job"}
        if self.supervisor.supervisor_state == "failed":
            # An explicit user action re-arms the breaker (M03-AC01: the
            # automatic loop stops; recovery is manual from here).
            try:
                self.supervisor.restart()
            except WorkerFailure as e:
                self.v2log.emit("worker.manual_restart_failed", level="ERROR",
                                reason_code=e.reason_code)
                return {"outcome": "restart_failed"}
        try:
            # Strict read: a truncated file is refused, never re-run as a
            # shorter "complete" capture (M03-AUDIT-10).
            _arr, _rate = v2.store.read_wav_f32(pathlib.Path(info["wav"]))
        except Exception as e:
            self.v2log.emit("dictation.retry_failed", level="ERROR",
                            job_id=job_id,
                            reason_code=type(e).__name__)
            return {"outcome": "audio_unavailable"}
        prov = (self._read_provenance(job_id) if job_id else None) or {}
        attempt = int(info.get("attempt", 1) or 1) + 1
        if job_id:
            try:
                # The durable row is the attempt authority: the retry is
                # the next attempt after the last one that EXECUTED.
                attempt = int(self.store.bump_job_attempt(
                    job_id, wait=True) or attempt)
            except Exception as e:
                self.v2log.emit("store.state_write_failed",
                                level="WARNING", job_id=job_id,
                                reason_code=type(e).__name__)
            self._job_state(job_id, "queued", reason="user_retry",
                            retry=True)
        # The original capture's instant and zone: store row first (the
        # durable truth), then the sidecar; absent stays absent — never
        # the retry's 'now' (the refusal rule).
        captured = row.get("captured_at_utc") or prov.get("captured_at_utc")
        time_quality = (row.get("time_quality") or prov.get("time_quality")
                        or "known") if captured else "unknown"
        zone = row.get("timezone") or prov.get("timezone")
        offset = row.get("utc_offset_minutes") \
            if row.get("utc_offset_minutes") is not None \
            else prov.get("utc_offset_minutes")
        try:
            # M02-AUDIT-06: a retry re-processes an OLD capture — it uses
            # that capture's permission (and only while collection is
            # enabled now), never today's consent attached retroactively.
            ctx = self.collector.job_started(
                job_id, family_id,
                captured_at_utc=captured, timezone=zone,
                utc_offset_minutes=offset, attempt=attempt,
                consent_snapshot=self.collector.retry_snapshot(job_id),
                time_quality=time_quality)
        except Exception:
            ctx = None
        job = {"job_id": job_id, "family_id": family_id, "ctx": ctx,
               "failed": False, "cancelled": False, "attempt": attempt,
               "raw": None, "wav": info["wav"], "journal": None,
               "from_retry": True,
               "audio": _arr,
               # The retained bytes' own rate — never relabeled to the
               # current configuration.
               "sample_rate": int(_rate),
               "stats": self._stats_from_provenance(prov, _arr.size,
                                                    int(_rate)),
               "captured_at_utc": captured, "time_quality": time_quality,
               "timezone": zone, "utc_offset_minutes": offset}
        # M13: the retry is the SAME logical dictation — its usage fact
        # keeps the ORIGINAL capture instant, observed zone and
        # destination app from the store rows (a retry completing on
        # another day must not move the dictation there, and an absent
        # instant stays absent — the refusal rule, never a fabricated
        # 'now').
        try:
            tgt = self.store.submit(lambda db: db.execute(
                "SELECT app_name, app_bundle FROM job_targets WHERE"
                " job_id=?", (job_id,)).fetchone()) or (None, None)
            job.update({"app_name": tgt[0], "app_bundle": tgt[1]})
        except Exception as e:
            self.v2log.emit("usage.retry_provenance_unavailable",
                            level="WARNING", job_id=job_id,
                            reason_code=type(e).__name__)
        self.v2log.emit("dictation.retry_started", level="INFO",
                        job_id=job_id, attempt=attempt,
                        reason_code="user_retry")
        if info in self._recoverable:
            self._recoverable.remove(info)
        elif (self._last_failed is not None
              and self._last_failed.get("job_id") == info.get("job_id")):
            # Only clear when this retry IS the last failure — retrying
            # an older History row must not strand a different failure's
            # recovery menu entry.
            self._last_failed = None
        self._refresh_recovery_menu()
        self._pending += 1
        self._active_jobs.append(job)
        self._jobs.put(job)
        self.state = STATE_PROCESSING
        self.overlay.showWithMode_(MODE_PROCESSING)
        return {"outcome": "requeued", "job_id": job_id}

    @objc.python_method
    def _drop_recovery_item(self, job_id):
        self._recoverable[:] = [i for i in self._recoverable
                                if i.get("job_id") != job_id]
        if self._last_failed is not None \
                and self._last_failed.get("job_id") == job_id:
            self._last_failed = None
        self._refresh_recovery_menu()

    @objc.python_method
    def _stats_from_provenance(self, prov, sample_count, rate) -> dict:
        """Capture diagnostics for a retried recovered capture: what is
        known about the ORIGINAL capture, honest None where unknown."""
        journal = prov.get("journal") or {}
        used_journal = prov.get("source") == "journal_reconstruction"
        wav = prov.get("wav") or {}
        stats = {
            "device": prov.get("device") or "unknown",
            "duration_sec": sample_count / float(rate),
            "voiced_pct": prov.get("voiced_pct"),
            "trailing_silence_sec": prov.get("trailing_silence_sec"),
            "overflow_blocks": prov.get("overflow_blocks"),
            "device_discontinuity": prov.get("device_discontinuity"),
            "stream_teardown_error": prov.get("stream_teardown_error"),
            "audio_source": prov.get("source") or "unknown",
            "recovered": bool(prov.get("recovered")),
            "capture_complete": prov.get("complete"),
            "capture_journal": prov.get("capture_journal"),
        }
        if used_journal:
            stats.update({
                "journal_status": journal.get("status"),
                "journal_version": journal.get("version"),
                "journal_integrity": journal.get("integrity"),
                "journal_gaps": journal.get("gaps") or None,
                "positions_known": journal.get("positions_known"),
                "journal_torn_bytes": journal.get("torn_bytes"),
                "journal_dropped_blocks": journal.get("dropped_blocks"),
                "incomplete_tail": journal.get("status") in (
                    capture_journal.STATUS_TORN_TAIL,
                    capture_journal.STATUS_CORRUPT,
                    capture_journal.STATUS_NO_HEADER),
            })
        if wav:
            stats["wav_declared_samples"] = wav.get("declared_samples")
            stats["wav_available_samples"] = wav.get("available_samples")
        return stats

    def copyLastRaw_(self, sender):
        if self._last_failed is None or not self._last_failed.get("raw"):
            return
        copy_text(self._last_failed["raw"])
        self.v2log.emit("dictation.raw_exported", level="INFO",
                        job_id=self._last_failed.get("job_id"),
                        reason_code="user_action",
                        detail=f"{len(self._last_failed['raw'])} chars")

    def undoLastResultAction_(self, outcome):
        self.v2log.emit(
            "insertion.undo", level="INFO", reason_code="menu_action",
            outcome=outcome.get("outcome"))

    def undoLastInsertion_(self, sender):
        """Target-bound undo of LocalFlow's own last insertion (S18);
        never deletes newer user edits — a stale range offers the
        previous text on the clipboard instead. The bounded AX work
        runs on the insertion queue thread; the menu action never
        blocks on it."""
        if self.state == STATE_RECORDING or self._insertion is None:
            return
        self._insertion.undo_last(
            on_done=lambda outcome: AppHelper.callAfter(
                self.undoLastResultAction_, outcome))

    def pasteLastResultAgain_(self, sender):
        """Explicit user intent (S18): reconcile the accessible text
        first (bounded reads); only a fresh queued transaction follows
        when the previous result is not already present."""
        if self.state == STATE_RECORDING or self._insertion is None:
            return
        self._insertion.paste_again()

    # ---- M13 usage analytics commands (Hub coordinator surface) -----------

    @objc.python_method
    def hubUsageInfo(self):
        """The Settings/Insights usage block: retention knob value and
        the active reporting timezone (S21)."""
        return {
            "usage_retention_days": self.store.retention_days.get(
                "usage", 365),
            "reporting_timezone": (self._analytics.reporting_timezone
                                   if self._analytics else None),
            "available": self._analytics is not None,
        }

    @objc.python_method
    def hubApplyUsageRetention(self, days):
        """Apply the usage retention knob now and persist it to the user
        override (the single-key discipline of hubApplyRetention)."""
        days = config_mod.validate_retention_value(
            "retention_usage_days", days)  # M02-AUDIT-19 bounds
        if days is None:
            return {"outcome": "invalid_days"}
        self.store.retention_days["usage"] = days
        self.cfg["retention_usage_days"] = days
        try:
            override = {}
            path = config_mod.user_override_path()
            try:
                override = json.loads(path.read_text())
            except (OSError, ValueError):
                override = {}
            override["retention_usage_days"] = days
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(override, ensure_ascii=False,
                                       indent=1), encoding="utf-8")
        except Exception as e:
            self.v2log.emit("hub.settings_write_failed", level="WARNING",
                            reason_code=type(e).__name__)
            return {"outcome": "not_persisted"}
        self.v2log.emit("hub.usage_retention_applied", level="INFO",
                        reason_code="settings", detail=f"{days}d")
        return {"outcome": "applied", "days": days}

    @objc.python_method
    def hubDeleteAllUsage(self):
        """The explicit 'delete all usage data' control (S21): facts and
        aggregates only — transcripts, audio, jobs and training
        evidence are untouched (delete-content vs delete-usage)."""
        if self._analytics is None:
            return {"outcome": "unavailable"}
        try:
            return {"outcome": "deleted",
                    **self._analytics.delete_all_usage()}
        except Exception as e:
            self.v2log.emit("usage.delete_failed", level="WARNING",
                            reason_code=type(e).__name__)
            return {"outcome": "failed"}

    @objc.python_method
    def hubDeleteUsageForJob(self, job_id):
        """The explicit 'delete associated usage' action for one job.
        Legacy imported rows are the lossless history contract — they
        carry no deletable usage facts and refuse honestly."""
        if not job_id or not str(job_id).startswith("job-"):
            return {"outcome": "not_a_v2_job",
                    "reason": "legacy_rows_have_no_deletable_usage"}
        if self._analytics is None:
            return {"outcome": "unavailable"}
        try:
            return {"outcome": "deleted",
                    **self._analytics.delete_usage_for_job(job_id)}
        except Exception as e:
            self.v2log.emit("usage.delete_failed", level="WARNING",
                            job_id=job_id, reason_code=type(e).__name__)
            return {"outcome": "failed"}


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
