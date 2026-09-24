"""Persistent V2 store: SQLite jobs/artifacts/imports + training namespace.

One database (default ``~/Library/Application Support/LocalFlow/v2.db``)
owned by a single writer thread — every mutation and every read is funneled
through it, so there is exactly one application writer (Spec S06/S08). Text
artifacts are stored inline; audio artifacts are written as IEEE-float32
WAV files under a 0700 artifacts directory and referenced by relative path
+ sha256.

The training namespace (Spec S29.3) lives in the same database with its own
``training_schema_version``. Shared artifacts carry independent
history/recovery/training leases; expiry of one interest never deletes
content another live lease pins, and delete-everywhere overrides ordinary
immutability, purges payloads and leaves only content-free tombstones.
"""

import collections
import datetime as dt
import json
import os
import pathlib
import queue
import sqlite3
import struct
import threading
import time

import numpy as np

from . import ids

TERMINAL_STATES = {
    "insertion_confirmed", "insertion_unverified", "saved_not_inserted",
    "cancelled", "failed_recoverable", "failed_unrecoverable",
}

# Rank guards the happy-path order so a stale result can never move a job
# backwards (contracts/jobs.md invariant 1).
_STATE_ORDER = {
    "capturing": 0, "queued": 1, "transcribing": 2, "normalizing": 3,
    "cleaning": 4, "validating": 5, "transforming": 6,
    "ready_to_insert": 7, "insertion_posted": 8,
}
for _s in TERMINAL_STATES:
    _STATE_ORDER[_s] = 100

RETENTION_DAYS_DEFAULTS = {
    "transcript": 30, "audio_success": 7, "audio_failed": 30,
    "metadata": 14, "training_buffer": 30, "usage": 365,
}

_MIGRATIONS: dict[int, list[str]] = {
    1: [
        """CREATE TABLE IF NOT EXISTS schema_meta(
             key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS jobs(
             job_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
             family_id TEXT NOT NULL, session_id TEXT, boot_id TEXT,
             attempt INTEGER NOT NULL DEFAULT 1,
             captured_at_utc TEXT, released_at_utc TEXT,
             time_quality TEXT NOT NULL DEFAULT 'known',
             timezone TEXT, utc_offset_minutes INTEGER,
             state TEXT NOT NULL, state_reason TEXT,
             audio_artifact_id TEXT,
             source_revision TEXT, pipeline_revision TEXT,
             created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS artifacts(
             artifact_id TEXT PRIMARY KEY, job_id TEXT, stage TEXT NOT NULL,
             parent_artifact_id TEXT, kind TEXT NOT NULL, role TEXT,
             content_path TEXT, content_text TEXT, sha256 TEXT NOT NULL,
             bytes INTEGER, meta_json TEXT NOT NULL DEFAULT '{}',
             retention_class TEXT NOT NULL DEFAULT 'history',
             purged INTEGER NOT NULL DEFAULT 0,
             created_at_utc TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS imports(
             source_kind TEXT NOT NULL, source_sha256 TEXT NOT NULL,
             source_locator TEXT NOT NULL, imported_id TEXT NOT NULL,
             imported_at_utc TEXT NOT NULL, time_quality TEXT,
             PRIMARY KEY(source_kind, source_sha256, source_locator))""",
        """CREATE TABLE IF NOT EXISTS import_runs(
             run_id TEXT PRIMARY KEY, source_kind TEXT NOT NULL,
             source_sha256 TEXT NOT NULL, source_bytes INTEGER NOT NULL,
             source_path TEXT, imported_records INTEGER NOT NULL,
             skipped_records INTEGER NOT NULL,
             imported_at_utc TEXT NOT NULL, note TEXT)""",
        """CREATE TABLE IF NOT EXISTS legacy_dictations(
             id INTEGER PRIMARY KEY, ts REAL NOT NULL,
             captured_at_utc TEXT NOT NULL, duration_sec REAL,
             raw_text TEXT, cleaned_text TEXT,
             raw_words INTEGER, cleaned_words INTEGER, fixed_words INTEGER,
             wpm REAL, app_name TEXT, app_bundle TEXT, kind TEXT,
             imported_from_sha256 TEXT NOT NULL)""",
        # Compatibility view over the copied legacy rows using the original
        # producer's table/column names (Spec S08 migration contract).
        """CREATE VIEW IF NOT EXISTS dictations AS
             SELECT id, ts, duration_sec, raw_text, cleaned_text, raw_words,
                    cleaned_words, fixed_words, wpm, app_name, app_bundle, kind
             FROM legacy_dictations""",
        # --- training namespace (training_schema_version 1, Spec S29.3) ---
        """CREATE TABLE IF NOT EXISTS training_examples(
             example_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
             family_id TEXT NOT NULL, consent_revision_id TEXT,
             collection_policy TEXT,
             state TEXT NOT NULL DEFAULT 'captured_unreviewed',
             latest_revision_id TEXT,
             created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS training_revisions(
             revision_id TEXT PRIMARY KEY, example_id TEXT NOT NULL,
             parent_revision_id TEXT, created_at_utc TEXT NOT NULL,
             envelope_json TEXT NOT NULL, content_sha256 TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS consent_revisions(
             consent_revision_id TEXT PRIMARY KEY, state TEXT NOT NULL,
             policy_json TEXT NOT NULL, created_at_utc TEXT NOT NULL,
             note TEXT)""",
        """CREATE TABLE IF NOT EXISTS artifact_leases(
             lease_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL,
             holder TEXT NOT NULL, granted_at_utc TEXT NOT NULL,
             expires_at_utc TEXT, revoked_at_utc TEXT)""",
        """CREATE TABLE IF NOT EXISTS deletion_tombstones(
             tombstone_id TEXT PRIMARY KEY, target_kind TEXT NOT NULL,
             target_id TEXT NOT NULL, reason TEXT NOT NULL,
             created_at_utc TEXT NOT NULL)""",
    ],
}

TRAINING_SCHEMA_VERSION = 1
_ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"

_MIGRATIONS[2] = [
    # Hot-path indexes for lease checks, per-job artifact lookups and
    # revision chains (the daily prune and verify walk these).
    """CREATE INDEX IF NOT EXISTS idx_artifact_leases_artifact
         ON artifact_leases(artifact_id)""",
    """CREATE INDEX IF NOT EXISTS idx_artifacts_job
         ON artifacts(job_id)""",
    """CREATE INDEX IF NOT EXISTS idx_training_revisions_example
         ON training_revisions(example_id)""",
    """CREATE INDEX IF NOT EXISTS idx_imports_kind
         ON imports(source_kind)""",
]

# M05 (Spec S08 vocabulary table, S11): versioned canonical/alias records.
# Additive only — no existing table or frozen identity changes; the
# legacy dictionary artifacts imported by M02 stay untouched and seed
# these rows (vocabulary_store.seed_legacy_terms).
_MIGRATIONS[3] = [
    """CREATE TABLE IF NOT EXISTS vocabulary_entries(
         entry_id TEXT PRIMARY KEY,
         canonical TEXT NOT NULL,
         language TEXT,
         kind TEXT NOT NULL DEFAULT 'term',
         matching_mode TEXT NOT NULL DEFAULT 'phrase',
         scope_kind TEXT NOT NULL DEFAULT 'global',
         scope_value TEXT,
         priority INTEGER NOT NULL DEFAULT 0,
         pinned INTEGER NOT NULL DEFAULT 0,
         usage_count INTEGER NOT NULL DEFAULT 0,
         last_used_utc TEXT,
         origin TEXT NOT NULL DEFAULT 'user',
         enabled INTEGER NOT NULL DEFAULT 1,
         approved INTEGER NOT NULL DEFAULT 0,
         verification TEXT NOT NULL DEFAULT 'suggested',
         revision INTEGER NOT NULL DEFAULT 1,
         created_at_utc TEXT NOT NULL,
         updated_at_utc TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS vocabulary_aliases(
         entry_id TEXT NOT NULL,
         alias TEXT NOT NULL,
         language TEXT,
         approved INTEGER NOT NULL DEFAULT 1,
         PRIMARY KEY(entry_id, alias))""",
    """CREATE TABLE IF NOT EXISTS vocabulary_history(
         history_id INTEGER PRIMARY KEY AUTOINCREMENT,
         entry_id TEXT NOT NULL,
         revision INTEGER NOT NULL,
         action TEXT NOT NULL,
         change_json TEXT NOT NULL,
         created_at_utc TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS vocabulary_meta(
         key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_vocabulary_aliases_entry
         ON vocabulary_aliases(entry_id)""",
    # One canonical spelling per scope, case-insensitively — "Servo"
    # and "servo" in the same scope would otherwise coexist as rows and
    # mask each other's lowered alias keys in every snapshot.
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_vocabulary_canonical_scope
         ON vocabulary_entries(canonical COLLATE NOCASE, scope_kind,
                                IFNULL(scope_value, ''))""",
]


# M08 (Spec S18, S29.8): insertion transactions and bounded outcome
# observations. Additive only — attribution joins through job_id; the
# jobs table itself stays unchanged (the M06 decision: snapshot ids live
# with the consumers that need them, here on the insertion rows).
_MIGRATIONS[4] = [
    """CREATE TABLE IF NOT EXISTS insertions(
         insertion_id TEXT PRIMARY KEY,
         job_id TEXT NOT NULL,
         attempt INTEGER NOT NULL,
         target_snapshot_id TEXT,
         context_snapshot_id TEXT,
         method TEXT NOT NULL,
         state TEXT NOT NULL,
         reason_code TEXT,
         verification_json TEXT NOT NULL,
         owned_start INTEGER,
         owned_end INTEGER,
         inserted_chars INTEGER NOT NULL DEFAULT 0,
         clipboard_json TEXT,
         created_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_insertions_job
         ON insertions(job_id)""",
    """CREATE TABLE IF NOT EXISTS insertion_observations(
         observation_id TEXT PRIMARY KEY,
         insertion_id TEXT NOT NULL,
         job_id TEXT NOT NULL,
         started_at_utc TEXT NOT NULL,
         stopped_at_utc TEXT,
         stop_reason TEXT,
         edited INTEGER,
         reanchors INTEGER NOT NULL DEFAULT 0,
         ticks INTEGER NOT NULL DEFAULT 0,
         before_artifact_id TEXT,
         after_artifact_id TEXT,
         meta_json TEXT)""",
    """CREATE INDEX IF NOT EXISTS idx_insertion_observations_insertion
         ON insertion_observations(insertion_id)""",
]


# M09 (Spec S08 jobs "target" field / S19 History app filter): the
# destination app a dictation targeted, recorded at PTT start when the
# M06 identity read succeeded. A side table rather than an ALTER on
# jobs — plain CREATE TABLE keeps every migration statement idempotent
# (the torn-write repair path re-applies them all) and the jobs table
# untouched (the M06 decision: consumers own what they need).
# App names are private usage metadata (S21); they follow the job rows.
_MIGRATIONS[5] = [
    """CREATE TABLE IF NOT EXISTS job_targets(
         job_id TEXT PRIMARY KEY,
         app_name TEXT, app_bundle TEXT,
         recorded_at_utc TEXT NOT NULL)""",
    # History date grouping/sort walks captured time in every query.
    """CREATE INDEX IF NOT EXISTS idx_jobs_captured
         ON jobs(captured_at_utc)""",
]


# M10 (Spec S15/S17, contracts/profiles.md): destination style rules
# and versioned snippets — user-configured rows the Hub edits through
# the single writer (the M05 vocabulary pattern: versioned rows plus a
# monotonic state counter for snapshot invalidation; no ALTERs).
# Trigger/scope columns are configuration content, not usage data.
_MIGRATIONS[6] = [
    """CREATE TABLE IF NOT EXISTS style_rules(
         rule_id TEXT PRIMARY KEY,
         name TEXT NOT NULL,
         scope_kind TEXT NOT NULL,
         scope_value TEXT,
         mode TEXT NOT NULL,
         number_policy TEXT NOT NULL DEFAULT 'inherit',
         profile_name TEXT,
         enabled INTEGER NOT NULL DEFAULT 1,
         revision INTEGER NOT NULL DEFAULT 1,
         created_at_utc TEXT NOT NULL,
         updated_at_utc TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS snippets(
         snippet_id TEXT PRIMARY KEY,
         trigger TEXT NOT NULL,
         name TEXT NOT NULL,
         kind TEXT NOT NULL DEFAULT 'plain',
         content TEXT NOT NULL,
         content_rtf TEXT,
         allow_rewrite INTEGER NOT NULL DEFAULT 0,
         enabled INTEGER NOT NULL DEFAULT 1,
         revision INTEGER NOT NULL DEFAULT 1,
         usage_count INTEGER NOT NULL DEFAULT 0,
         last_used_utc TEXT,
         created_at_utc TEXT NOT NULL,
         updated_at_utc TEXT NOT NULL)""",
    # One-canonical-trigger: two enabled snippets sharing a trigger
    # would be ambiguous at match time (the snapshot masks both); the
    # unique index keeps the stored set unambiguous at the source.
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_snippets_trigger
         ON snippets(trigger COLLATE NOCASE)""",
    """CREATE TABLE IF NOT EXISTS profiles_meta(
         key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
]


# M11 (Spec S16/S29.10, contracts/transforms.md): transform
# definitions with append-only revisions (an old definition is never
# erased), same-task candidates and explicit preference observations.
# Rows carry hashes/ids/counts only — source and output texts live in
# lease-governed artifacts written inside the same writer op.
_MIGRATIONS[7] = [
    """CREATE TABLE IF NOT EXISTS transforms(
         transform_id TEXT PRIMARY KEY,
         name TEXT NOT NULL,
         mode TEXT NOT NULL,
         origin TEXT NOT NULL DEFAULT 'user',
         description TEXT NOT NULL DEFAULT '',
         prompt TEXT NOT NULL DEFAULT '',
         edit_types_json TEXT NOT NULL DEFAULT '[]',
         examples_json TEXT NOT NULL DEFAULT '[]',
         shortcut TEXT,
         target_profiles_json TEXT NOT NULL DEFAULT '[]',
         auto_apply INTEGER NOT NULL DEFAULT 0,
         enabled INTEGER NOT NULL DEFAULT 1,
         revision INTEGER NOT NULL DEFAULT 1,
         usage_count INTEGER NOT NULL DEFAULT 0,
         source_locator TEXT,
         legacy_key TEXT,
         created_at_utc TEXT NOT NULL,
         updated_at_utc TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS transform_revisions(
         transform_id TEXT NOT NULL,
         revision INTEGER NOT NULL,
         definition_json TEXT NOT NULL,
         created_at_utc TEXT NOT NULL,
         PRIMARY KEY(transform_id, revision))""",
    """CREATE TABLE IF NOT EXISTS transform_meta(
         key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS transform_candidates(
         candidate_id TEXT PRIMARY KEY,
         task_key TEXT NOT NULL,
         task_kind TEXT NOT NULL,
         transform_id TEXT NOT NULL,
         transform_revision INTEGER NOT NULL,
         prompt_revision TEXT NOT NULL,
         source_sha256 TEXT NOT NULL,
         instructions_sha256 TEXT NOT NULL,
         examples_revision TEXT,
         source_artifact_id TEXT,
         output_artifact_id TEXT,
         path TEXT NOT NULL,
         display_order INTEGER NOT NULL DEFAULT 0,
         model_id TEXT,
         created_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_transform_candidates_task
         ON transform_candidates(task_key)""",
    """CREATE TABLE IF NOT EXISTS preference_observations(
         observation_id TEXT PRIMARY KEY,
         task_key TEXT NOT NULL,
         candidate_id TEXT NOT NULL,
         candidate_b_id TEXT,
         judgment TEXT NOT NULL,
         provenance TEXT NOT NULL,
         reason_code TEXT,
         source_event_id TEXT,
         created_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_preference_observations_task
         ON preference_observations(task_key)""",
]


# M12 (Spec S20/S08, contracts/scratchpad.md): the Scratchpad note
# workspace. Notes point at an append-only, parent-linked revision chain
# (a transform creates a version, never an untracked overwrite);
# attachments are local image files under a managed 0700 directory;
# note_evidence_links track which training examples a note's revisions
# have been observed against so note deletion can close those
# references (S29.8/S29.14). Additive only, no frozen identity changes.
_MIGRATIONS[8] = [
    """CREATE TABLE IF NOT EXISTS notes(
         note_id TEXT PRIMARY KEY,
         title TEXT NOT NULL DEFAULT '',
         pinned INTEGER NOT NULL DEFAULT 0,
         current_revision_id TEXT,
         dirty_at_utc TEXT,
         created_at_utc TEXT NOT NULL,
         updated_at_utc TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS note_revisions(
         revision_id TEXT PRIMARY KEY,
         note_id TEXT NOT NULL,
         parent_revision_id TEXT,
         origin TEXT NOT NULL,
         trigger_kind TEXT NOT NULL DEFAULT 'explicit',
         content_text TEXT NOT NULL,
         content_sha256 TEXT NOT NULL,
         word_count INTEGER NOT NULL DEFAULT 0,
         source_job_id TEXT,
         task_key TEXT,
         transform_id TEXT,
         transform_revision INTEGER,
         restore_of TEXT,
         spans_json TEXT NOT NULL DEFAULT '[]',
         meta_json TEXT NOT NULL DEFAULT '{}',
         purged INTEGER NOT NULL DEFAULT 0,
         created_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_note_revisions_note
         ON note_revisions(note_id)""",
    """CREATE TABLE IF NOT EXISTS note_attachments(
         attachment_id TEXT PRIMARY KEY,
         note_id TEXT NOT NULL,
         kind TEXT NOT NULL DEFAULT 'image',
         mime TEXT,
         filename TEXT,
         bytes INTEGER NOT NULL DEFAULT 0,
         sha256 TEXT NOT NULL,
         content_path TEXT,
         purged INTEGER NOT NULL DEFAULT 0,
         created_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_note_attachments_note
         ON note_attachments(note_id)""",
    """CREATE TABLE IF NOT EXISTS note_evidence_links(
         note_id TEXT NOT NULL,
         example_id TEXT NOT NULL,
         job_id TEXT,
         first_seen_utc TEXT NOT NULL,
         closed_utc TEXT,
         close_reason TEXT,
         PRIMARY KEY(note_id, example_id))""",
]

# M13 (Spec S08 usage_facts/daily_aggregates, S21, contracts/analytics.md):
# dated usage facts — one row per logical dictation job (a retry replaces,
# never duplicates) plus separate transform/repaste activity rows — and
# versioned daily aggregates recomputed from those facts. The rows carry
# their own copies of app/duration/word facts so usage survives job-row
# metadata pruning and transcript expiry (M13-AC03: aggregate retention
# is independent of text retention). App names are private usage
# metadata (S21): store-side only, never in committed artifacts.
_MIGRATIONS[9] = [
    """CREATE TABLE IF NOT EXISTS usage_facts(
         fact_id TEXT PRIMARY KEY,
         kind TEXT NOT NULL,
         job_id TEXT,
         activity_at_utc TEXT NOT NULL,
         time_quality TEXT NOT NULL DEFAULT 'known',
         timezone TEXT, utc_offset_minutes INTEGER,
         day_local TEXT NOT NULL,
         reporting_timezone TEXT NOT NULL,
         algorithm_version INTEGER NOT NULL,
         duration_sec REAL,
         raw_words INTEGER, final_words INTEGER,
         cleanup_path TEXT, fallback_reason TEXT,
         mode TEXT, profile_name TEXT,
         app_name TEXT, app_bundle TEXT,
         insertion_outcome TEXT,
         asr_ms REAL, cleanup_ms REAL, transform_ms REAL,
         end_to_end_ms REAL,
         dictionary_hits INTEGER NOT NULL DEFAULT 0,
         snippet_hits INTEGER NOT NULL DEFAULT 0,
         transform_id TEXT, task_key TEXT, transform_path TEXT,
         source_kind TEXT, source_words INTEGER, output_words INTEGER,
         attempt INTEGER,
         word_count_version TEXT,
         meta_json TEXT NOT NULL DEFAULT '{}',
         created_at_utc TEXT NOT NULL)""",
    # One fact per logical dictation: a retry that reaches a terminal
    # state again REPLACES the row (ON CONFLICT DO UPDATE) instead of
    # adding a second one (M13-AC02).
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_facts_job
         ON usage_facts(job_id) WHERE kind='dictation'""",
    """CREATE INDEX IF NOT EXISTS idx_usage_facts_day
         ON usage_facts(day_local, kind)""",
    """CREATE INDEX IF NOT EXISTS idx_usage_facts_activity
         ON usage_facts(activity_at_utc)""",
    """CREATE TABLE IF NOT EXISTS daily_aggregates(
         day_local TEXT NOT NULL,
         reporting_timezone TEXT NOT NULL,
         algorithm_version INTEGER NOT NULL,
         dictations INTEGER NOT NULL DEFAULT 0,
         dictations_with_text INTEGER NOT NULL DEFAULT 0,
         insertion_confirmed INTEGER NOT NULL DEFAULT 0,
         insertion_unverified INTEGER NOT NULL DEFAULT 0,
         saved_not_inserted INTEGER NOT NULL DEFAULT 0,
         cancelled INTEGER NOT NULL DEFAULT 0,
         failed INTEGER NOT NULL DEFAULT 0,
         raw_words INTEGER NOT NULL DEFAULT 0,
         final_words INTEGER NOT NULL DEFAULT 0,
         capture_seconds REAL NOT NULL DEFAULT 0,
         fallback_jobs INTEGER NOT NULL DEFAULT 0,
         dictionary_hits INTEGER NOT NULL DEFAULT 0,
         snippet_hits INTEGER NOT NULL DEFAULT 0,
         transforms INTEGER NOT NULL DEFAULT 0,
         transform_words INTEGER NOT NULL DEFAULT 0,
         repastes INTEGER NOT NULL DEFAULT 0,
         computed_at_utc TEXT NOT NULL,
         PRIMARY KEY(day_local, reporting_timezone,
                     algorithm_version))""",
]


# ---- IEEE float32 WAV (Spec S29.5: the original capture artifact) -------

def write_wav_f32(path: pathlib.Path, samples: np.ndarray, sample_rate: int):
    """Lossless float-preserving WAV for the capture path's float32 buffer."""
    data = np.ascontiguousarray(samples, dtype="<f4").tobytes()
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 3, 1, int(sample_rate),
        int(sample_rate) * 4, 4, 32,
        b"data", len(data),
    )
    _write_wav(path, header, data)


def write_wav_pcm16(path: pathlib.Path, samples: np.ndarray, sample_rate: int):
    """Quantized PCM16 WAV — a derivative export, never lossless (S29.5)."""
    data = (np.clip(np.asarray(samples), -1.0, 1.0) * 32767).astype(
        "<i2").tobytes()
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 1, 1, int(sample_rate),
        int(sample_rate) * 2, 2, 16,
        b"data", len(data),
    )
    _write_wav(path, header, data)


def _write_wav(path: pathlib.Path, header: bytes, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(header)
        f.write(data)
    os.chmod(path, 0o600)


_WAV_HEADER = struct.Struct("<4sI4s4sIHHIIHH4sI")


def read_wav_f32(path: pathlib.Path) -> tuple[np.ndarray, int]:
    with open(path, "rb") as f:
        raw = f.read()
    (riff, _size, wave, fmt, _fmt_size, audio_format, channels, rate,
     _byte_rate, _block_align, bits, _mark, data_size) = _WAV_HEADER.unpack(
        raw[:44])
    if (riff, wave, fmt, audio_format, channels, bits) != (
            b"RIFF", b"WAVE", b"fmt ", 3, 1, 32):
        raise ValueError("not a mono float32 WAV")
    return (np.frombuffer(raw[44:44 + data_size], dtype="<f4").copy(), rate)


def read_wav(path: pathlib.Path) -> tuple[np.ndarray, int]:
    """Read either stored WAV flavor: float32 originals or PCM16 derivatives
    (returned as float32 in [-1, 1] — the quantization is already baked in
    and is recorded on the artifact, not hidden by re-expanding bits)."""
    with open(path, "rb") as f:
        raw = f.read()
    (riff, _size, wave, fmt, _fmt_size, audio_format, channels, rate,
     _byte_rate, _block_align, bits, _mark, data_size) = _WAV_HEADER.unpack(
        raw[:44])
    if (riff, wave, fmt, channels) != (b"RIFF", b"WAVE", b"fmt ", 1):
        raise ValueError("not a mono WAV")
    if audio_format == 3 and bits == 32:
        return (np.frombuffer(raw[44:44 + data_size], dtype="<f4").copy(),
                rate)
    if audio_format == 1 and bits == 16:
        # Scale by the same 32767 the writer used, so a derivative reads
        # back as exactly its quantized self (no phantom rescale).
        return (np.frombuffer(raw[44:44 + data_size], dtype="<i2").astype(
            np.float32) / 32767.0, rate)
    raise ValueError(f"unsupported WAV flavor: format={audio_format}"
                     f" bits={bits}")


def _iso_to_epoch(iso: str) -> float | None:
    try:
        return dt.datetime.strptime(iso, _ISO_FMT).replace(
            tzinfo=dt.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


class Store:
    """Single-writer SQLite store for jobs, artifacts and training evidence."""

    def __init__(self, db_path, *, artifacts_dir=None, backup_dir=None,
                 now_fn=time.time, emit=None):
        self.db_path = pathlib.Path(db_path)
        self.artifacts_dir = (pathlib.Path(artifacts_dir)
                              if artifacts_dir is not None
                              else self.db_path.parent / "v2-artifacts")
        self.backup_dir = pathlib.Path(backup_dir) if backup_dir else None
        self.now_fn = now_fn
        self.emit = emit or (lambda *a, **k: None)
        self.retention_days = dict(RETENTION_DAYS_DEFAULTS)
        self.last_errors = collections.deque(maxlen=50)
        self._queue: collections.deque = collections.deque()
        self._cond = threading.Condition()
        self._stop = False
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.artifacts_dir, 0o700)
            os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._migrate()
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass
        self._thread = threading.Thread(
            target=self._run, name="localflow-v2-store", daemon=True)
        self._thread.start()

    # ---- writer loop ---------------------------------------------------

    def _run(self):
        while True:
            with self._cond:
                while not self._queue and not self._stop:
                    self._cond.wait(0.5)
                if self._stop and not self._queue:
                    return
                fn, result_q = self._queue.popleft()
            try:
                out = fn()
                err = None
                # One commit per operation keeps multi-statement ops (prune,
                # delete-everywhere, migration-style batches) atomic.
                self._db.commit()
            except Exception as e:  # surfaced via last_errors, never crashes
                out, err = None, f"{type(e).__name__}: {e}"
                self.last_errors.append(err)
                try:
                    self._db.rollback()
                except sqlite3.DatabaseError:
                    pass
                self.emit("store.write_failed", level="ERROR",
                          reason_code="store_error", detail=err[:200])
            if result_q is not None:
                result_q.put((out, err))

    def _submit(self, fn, wait=False, timeout=15.0):
        if self._stop and not self._thread.is_alive():
            # The writer is gone (close completed); waiting would hang
            # for the full timeout on a queue nobody drains — fail
            # fast with the honest error instead.
            raise RuntimeError("store is closed")
        result_q = queue.Queue(maxsize=1) if wait else None
        with self._cond:
            self._queue.append((fn, result_q))
            self._cond.notify()
        if not wait:
            return None
        try:
            out, err = result_q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("store writer did not respond")
        if err:
            raise RuntimeError(err)
        return out

    def sync(self, timeout=15.0):
        """Barrier: all previously queued mutations have committed."""
        self._submit(lambda: None, wait=True, timeout=timeout)

    def submit(self, fn, wait=True, timeout=15.0):
        """Run ``fn(connection)`` on the writer thread — the sanctioned
        entry point for same-package domain layers (M05
        vocabulary_store) so they honor the single-writer discipline
        while the connection itself stays private to this module."""
        return self._submit(lambda: fn(self._db), wait=wait,
                            timeout=timeout)

    def close(self, timeout=5.0):
        try:
            self.sync(timeout)
        except (TimeoutError, RuntimeError):
            pass
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        self._thread.join(timeout=timeout)
        try:
            self._db.close()
        except sqlite3.DatabaseError:
            pass  # a writer op still finishing after a join timeout

    # ---- migration -------------------------------------------------------

    def _migrate(self):
        version = self._schema_version()
        target = max(_MIGRATIONS)
        # A present-but-malformed core table is corruption, not a torn
        # migration: checked FIRST, because later migrations (indexes)
        # reference these tables and would crash opaquely. Idempotent DDL
        # cannot fix a wrong-shaped table, and dropping user data silently
        # is forbidden (M02 stop conditions) — block loudly.
        for table, required_cols in (
                ("jobs", ("job_id", "family_id", "state")),
                ("artifacts", ("artifact_id", "sha256", "retention_class")),
                ("training_revisions", ("revision_id", "envelope_json"))):
            cols = {r[1] for r in self._db.execute(
                f"PRAGMA table_info({table})")}
            if cols and not set(required_cols) <= cols:
                raise RuntimeError(
                    f"store schema corrupt: table {table} is missing required"
                    f" columns {sorted(set(required_cols) - cols)}; refusing"
                    " to migrate over it — restore from backup or remove"
                    " v2.db manually")
        if 0 < version < target and self.backup_dir is not None:
            self._backup()
        elif 0 < version < target:
            # Constructed without a backup_dir but with a real upgrade
            # pending: proceed (additive DDL), but never silently —
            # an unbacked migration of live data must be visible.
            self.emit("store.migration_backup_skipped", level="WARNING",
                      reason_code="no_backup_dir",
                      detail=f"v{version}->v{target} without pre-migration"
                             " backup")
        for v in range(version + 1, target + 1):
            try:
                self._db.execute("BEGIN")
                for stmt in _MIGRATIONS[v]:
                    self._db.execute(stmt)
                self._db.execute(
                    "INSERT OR REPLACE INTO schema_meta VALUES('schema_version', ?)",
                    (str(v),))
                self._db.execute(
                    "INSERT OR REPLACE INTO schema_meta VALUES"
                    "('training_schema_version', ?)", (str(TRAINING_SCHEMA_VERSION),))
                self._db.commit()
            except sqlite3.DatabaseError:
                self._db.rollback()
                raise
            self.emit("store.migrated", level="INFO",
                      reason_code=f"store_schema_v{v}")
        # Repair path for a torn external write: re-apply every statement
        # (all DDL is IF NOT EXISTS / idempotent) when tables are missing.
        expected = {"schema_meta", "jobs", "artifacts", "imports", "import_runs",
                    "legacy_dictations", "training_examples", "training_revisions",
                    "consent_revisions", "artifact_leases", "deletion_tombstones",
                    "vocabulary_entries", "vocabulary_aliases",
                    "vocabulary_history", "vocabulary_meta",
                    "insertions", "insertion_observations",
                    "job_targets", "style_rules", "snippets",
                    "profiles_meta", "transforms", "transform_revisions",
                    "transform_meta", "transform_candidates",
                    "preference_observations", "notes", "note_revisions",
                    "note_attachments", "note_evidence_links",
                    "usage_facts", "daily_aggregates"}
        have = {r[0] for r in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if version >= target and not expected <= have:
            for v_repair in range(1, target + 1):
                for stmt in _MIGRATIONS[v_repair]:
                    self._db.execute(stmt)
            self._db.commit()
            self.emit("store.schema_repaired", level="WARNING",
                      reason_code="missing_tables")

    def _schema_version(self) -> int:
        try:
            row = self._db.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.DatabaseError:
            return 0

    def _backup(self):
        stamp = ids.now_utc_iso(self.now_fn()).replace(":", "")
        dst = self.backup_dir / f"v2-pre-migrate-{stamp}.db"
        dst.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(dst)
        try:
            self._db.backup(target)
        finally:
            target.close()
        self.emit("store.backup_taken", level="INFO",
                  reason_code="pre_migration_backup")

    # ---- jobs ------------------------------------------------------------

    def create_job(self, *, job_id=None, kind="dictation", family_id=None,
                   session_id=None, boot_id=None, attempt=1,
                   captured_at_utc=None, released_at_utc=None,
                   time_quality="known", timezone=None, utc_offset_minutes=None,
                   state="capturing", source_revision=None,
                   pipeline_revision=None):
        job_id = job_id or ids.new_id("job")
        family_id = family_id or ids.new_id("fam")
        now = ids.now_utc_iso(self.now_fn())

        def op():
            self._db.execute(
                "INSERT INTO jobs(job_id, kind, family_id, session_id, boot_id,"
                " attempt, captured_at_utc, released_at_utc, time_quality,"
                " timezone, utc_offset_minutes, state, source_revision,"
                " pipeline_revision, created_at_utc, updated_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, kind, family_id, session_id, boot_id, attempt,
                 captured_at_utc, released_at_utc, time_quality, timezone,
                 utc_offset_minutes, state, source_revision, pipeline_revision,
                 now, now))
            return job_id
        self._submit(op)
        return job_id, family_id

    def update_job_state(self, job_id, state, reason=None, *, retry=False):
        """Idempotent transition; stale/regressing states are discarded.
        A terminal state is final for stale-result purposes — the one
        deliberate exception is an explicit retry re-opening a
        ``failed_recoverable`` job to ``queued`` (contracts/jobs.md: a retry
        increments the attempt and keeps the job_id), which must be passed
        explicitly."""
        now = ids.now_utc_iso(self.now_fn())

        def op():
            row = self._db.execute(
                "SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return False
            current = row[0]
            if current == state:
                return True
            if current in TERMINAL_STATES:
                if retry and current == "failed_recoverable" \
                        and state == "queued":
                    pass  # the deliberate retry re-open (contracts/jobs.md)
                else:
                    return False  # exactly one logical terminal outcome (E12)
            elif _STATE_ORDER.get(state, 100) < _STATE_ORDER.get(current, 100):
                return False  # stale result discarded, never appended
            self._db.execute(
                "UPDATE jobs SET state=?, state_reason=?, updated_at_utc=?"
                " WHERE job_id=?", (state, reason, now, job_id))
            return True
        return bool(self._submit(op, wait=True))

    def bump_job_attempt(self, job_id):
        """A retry of the same audio increments the attempt, keeping the
        job_id (contracts/jobs.md)."""
        def op():
            self._db.execute(
                "UPDATE jobs SET attempt=attempt+1, updated_at_utc=?"
                " WHERE job_id=?",
                (ids.now_utc_iso(self.now_fn()), job_id))
        self._submit(op)

    def set_job_audio(self, job_id, artifact_id):
        def op():
            self._db.execute(
                "UPDATE jobs SET audio_artifact_id=?, updated_at_utc=?"
                " WHERE job_id=?",
                (artifact_id, ids.now_utc_iso(self.now_fn()), job_id))
        self._submit(op)

    def set_job_released(self, job_id, released_at_utc=None):
        def op():
            self._db.execute(
                "UPDATE jobs SET released_at_utc=?, updated_at_utc=?"
                " WHERE job_id=?",
                (released_at_utc or ids.now_utc_iso(self.now_fn()),
                 ids.now_utc_iso(self.now_fn()), job_id))
        self._submit(op)

    def set_job_target(self, job_id, app_name, app_bundle):
        """M09: record the dictation's destination app (History's app
        filter/display). Written once at PTT start from the M06 identity;
        a job with no identity read keeps no row — History then shows an
        honest unknown rather than a guess."""
        def op():
            self._db.execute(
                "INSERT OR REPLACE INTO job_targets(job_id, app_name,"
                " app_bundle, recorded_at_utc) VALUES(?,?,?,?)",
                (job_id, app_name, app_bundle,
                 ids.now_utc_iso(self.now_fn())))
        self._submit(op)

    def job(self, job_id):
        def op():
            cur = self._db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,))
            row = cur.fetchone()
            return _row_to_dict(row, [c[0] for c in cur.description])
        return self._submit(op, wait=True)

    def unresolved_job_ids(self):
        placeholders = ",".join("?" * len(TERMINAL_STATES))

        def op():
            return set(r[0] for r in self._db.execute(
                f"SELECT job_id FROM jobs WHERE state NOT IN ({placeholders})",
                tuple(TERMINAL_STATES)))
        return self._submit(op, wait=True)

    # ---- artifacts ---------------------------------------------------------

    def write_text_artifact(self, *, job_id, stage, role, text, kind="text",
                            retention_class="history", meta=None,
                            parent_artifact_id=None):
        artifact_id = ids.new_id("art")
        now = ids.now_utc_iso(self.now_fn())

        def op():
            return insert_text_artifact_row(
                self._db, artifact_id=artifact_id, job_id=job_id,
                stage=stage, role=role, text=text, kind=kind,
                retention_class=retention_class, meta=meta,
                parent_artifact_id=parent_artifact_id, created_at_utc=now)
        self._submit(op)
        return artifact_id

    def write_audio_artifact(self, *, job_id, stage, samples, sample_rate,
                             role="original_audio", retention_class="training",
                             meta=None, parent_artifact_id=None,
                             dtype="float32"):
        """Persist audio losslessly as float32 (S29.5) — or, when
        dtype="pcm16", as an explicitly-labeled quantized DERIVATIVE which
        must name its parent. Runs on the inference worker thread after
        capture completes — never on the audio callback."""
        if dtype not in ("float32", "pcm16"):
            raise ValueError(f"unknown audio dtype {dtype!r}")
        if dtype == "pcm16" and not parent_artifact_id:
            raise ValueError("pcm16 audio is a derivative and requires"
                             " parent_artifact_id (S29.5: quantization must"
                             " not be labeled lossless)")
        artifact_id = ids.new_id("art")
        rel = f"{artifact_id}.wav"
        path = self.artifacts_dir / rel
        if dtype == "float32":
            write_wav_f32(path, samples, sample_rate)
        else:
            write_wav_pcm16(path, samples, sample_rate)
        data_hash = ids.sha256_bytes(path.read_bytes())
        meta = dict(meta or {})
        sample_count = int(np.asarray(samples).size)
        meta.update({
            "format": ("wav_ieee_float32" if dtype == "float32"
                       else "wav_pcm16"),
            "dtype": dtype,
            "sample_rate": int(sample_rate), "channels": 1,
            "sample_count": sample_count,
            "duration_sec": sample_count / float(sample_rate),
            "lossless": dtype == "float32",
        })
        if dtype == "pcm16":
            meta["quantized_from_dtype"] = "float32"
        now = ids.now_utc_iso(self.now_fn())

        def op():
            self._db.execute(
                "INSERT INTO artifacts(artifact_id, job_id, stage,"
                " parent_artifact_id, kind, role, content_path, content_text,"
                " sha256, bytes, meta_json, retention_class, purged,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,0,?)",
                (artifact_id, job_id, stage, parent_artifact_id,
                 "audio_wav_f32" if dtype == "float32" else "audio_wav_pcm16",
                 role, rel, data_hash, path.stat().st_size,
                 json.dumps(meta, ensure_ascii=False), retention_class, now))
            return artifact_id
        self._submit(op)
        return artifact_id

    def artifact(self, artifact_id):
        def op():
            cur = self._db.execute(
                "SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,))
            row = cur.fetchone()
            return _row_to_dict(row, [c[0] for c in cur.description])
        return self._submit(op, wait=True)

    def artifact_payload(self, artifact_id):
        """Read back retained content: text str, audio ndarray, or None."""
        art = self.artifact(artifact_id)
        if art is None or art["purged"]:
            return None
        if art["content_path"]:
            arr, _rate = read_wav(self.artifacts_dir / art["content_path"])
            return arr
        return art["content_text"]

    def artifact_count(self):
        return self._submit(
            lambda: self._db.execute(
                "SELECT COUNT(*) FROM artifacts").fetchone()[0], wait=True)

    # ---- imports -----------------------------------------------------------

    def has_import(self, kind, sha, locator) -> bool:
        return self._submit(lambda: self._db.execute(
            "SELECT 1 FROM imports WHERE source_kind=? AND source_sha256=?"
            " AND source_locator=?", (kind, sha, locator)).fetchone()
            is not None, wait=True)

    def record_import(self, kind, sha, locator, imported_id, time_quality=None):
        def op():
            self._db.execute(
                "INSERT OR IGNORE INTO imports(source_kind, source_sha256,"
                " source_locator, imported_id, imported_at_utc, time_quality)"
                " VALUES(?,?,?,?,?,?)",
                (kind, sha, locator, imported_id,
                 ids.now_utc_iso(self.now_fn()), time_quality))
        self._submit(op)

    def import_legacy_text(self, *, text, role, kind, retention_class,
                           meta, source_kind, source_sha, locator,
                           time_quality=None):
        """Atomically create ONE legacy import artifact plus its bookkeeping
        row. A crash can never leave the artifact without bookkeeping (or
        vice versa), so re-import always converges. Returns the artifact id,
        or None when this locator was already imported."""
        artifact_id = ids.new_id("art")
        now = ids.now_utc_iso(self.now_fn())

        def op():
            exists = self._db.execute(
                "SELECT 1 FROM imports WHERE source_kind=? AND"
                " source_sha256=? AND source_locator=?",
                (source_kind, source_sha, locator)).fetchone()
            if exists:
                return None
            self._db.execute(
                "INSERT INTO artifacts(artifact_id, job_id, stage,"
                " parent_artifact_id, kind, role, content_path, content_text,"
                " sha256, bytes, meta_json, retention_class, purged,"
                " created_at_utc) VALUES(?,?,?,NULL,?,?,NULL,?,?,?,?,?,0,?)",
                (artifact_id, None, "import", kind, role, text,
                 ids.sha256_text(text), len(text.encode("utf-8")),
                 json.dumps(meta or {}, ensure_ascii=False),
                 retention_class, now))
            self._db.execute(
                "INSERT INTO imports(source_kind, source_sha256,"
                " source_locator, imported_id, imported_at_utc, time_quality)"
                " VALUES(?,?,?,?,?,?)",
                (source_kind, source_sha, locator, artifact_id, now,
                 time_quality))
            return artifact_id
        return self._submit(op, wait=True)

    def import_legacy_pair(self, *, raw_text, cleaned_text, raw_meta,
                           cleaned_meta, source_kind, source_sha, locator):
        """Atomically create a legacy raw/cleaned artifact pair (cleaned
        parented to raw) plus one bookkeeping row. Same convergence
        guarantee as import_legacy_text. Returns (raw_id, cleaned_id) or
        None when already imported."""
        raw_id = ids.new_id("art")
        cleaned_id = ids.new_id("art")
        now = ids.now_utc_iso(self.now_fn())

        def op():
            exists = self._db.execute(
                "SELECT 1 FROM imports WHERE source_kind=? AND"
                " source_sha256=? AND source_locator=?",
                (source_kind, source_sha, locator)).fetchone()
            if exists:
                return None
            for artifact_id, role, text, meta in (
                    (raw_id, "raw_transcript", raw_text, raw_meta),
                    (cleaned_id, "cleaned_transcript", cleaned_text,
                     cleaned_meta)):
                self._db.execute(
                    "INSERT INTO artifacts(artifact_id, job_id, stage,"
                    " parent_artifact_id, kind, role, content_path,"
                    " content_text, sha256, bytes, meta_json,"
                    " retention_class, purged, created_at_utc)"
                    " VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?,0,?)",
                    (artifact_id, None, "legacy_log",
                     raw_id if role == "cleaned_transcript" else None,
                     "legacy_text", role, text, ids.sha256_text(text),
                     len(text.encode("utf-8")),
                     json.dumps(meta, ensure_ascii=False), "legacy", now))
            self._db.execute(
                "INSERT INTO imports(source_kind, source_sha256,"
                " source_locator, imported_id, imported_at_utc, time_quality)"
                " VALUES(?,?,?,?,?,?)",
                (source_kind, source_sha, locator, cleaned_id, now,
                 "unknown"))
            return (raw_id, cleaned_id)
        return self._submit(op, wait=True)

    def record_import_run(self, kind, sha, source_bytes, source_path,
                          imported, skipped, note=None):
        run_id = ids.new_id("import")

        def op():
            self._db.execute(
                "INSERT INTO import_runs(run_id, source_kind, source_sha256,"
                " source_bytes, source_path, imported_records, skipped_records,"
                " imported_at_utc, note) VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, kind, sha, source_bytes, str(source_path), imported,
                 skipped, ids.now_utc_iso(self.now_fn()), note))
        self._submit(op)
        return run_id

    def import_run_bytes(self, kind) -> dict:
        """Map each imported source hash to its byte length (for prefix
        reconciliation of append-only sources like the legacy log)."""
        return self._submit(lambda: {
            r[0]: r[1] for r in self._db.execute(
                "SELECT source_sha256, source_bytes FROM import_runs"
                " WHERE source_kind=? ORDER BY rowid", (kind,))},
            wait=True)

    def insert_legacy_dictation(self, row, source_sha):
        """Insert one verbatim legacy analytics row (identity = source id)."""
        ts = float(row["ts"])
        captured = ids.now_utc_iso(ts)

        def op():
            self._db.execute(
                "INSERT OR IGNORE INTO legacy_dictations(id, ts,"
                " captured_at_utc, duration_sec, raw_text, cleaned_text,"
                " raw_words, cleaned_words, fixed_words, wpm, app_name,"
                " app_bundle, kind, imported_from_sha256)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["id"], ts, captured, row["duration_sec"], row["raw_text"],
                 row["cleaned_text"], row["raw_words"], row["cleaned_words"],
                 row["fixed_words"], row["wpm"], row["app_name"],
                 row["app_bundle"], row["kind"], source_sha))
        self._submit(op)

    def legacy_totals(self):
        return self._submit(lambda: self._db.execute(
            "SELECT COUNT(*), SUM(raw_words), SUM(cleaned_words),"
            " ROUND(SUM(duration_sec),1), SUM(fixed_words), MIN(captured_at_utc),"
            " MAX(captured_at_utc) FROM legacy_dictations").fetchone(), wait=True)

    def dated_analytics_rows(self):
        """Rows eligible for dated analytics: legacy rows carry known UTC
        instants; unknown-date log imports never appear here (S21)."""
        return self._submit(lambda: self._db.execute(
            "SELECT COUNT(*) FROM legacy_dictations WHERE captured_at_utc"
            " IS NOT NULL").fetchone()[0], wait=True)

    # ---- training namespace -------------------------------------------------

    def upsert_example(self, *, job_id, family_id, consent_revision_id=None,
                       collection_policy=None, example_id=None):
        example_id = example_id or ids.new_id("ex")
        now = ids.now_utc_iso(self.now_fn())

        def op():
            self._db.execute(
                "INSERT OR IGNORE INTO training_examples(example_id, job_id,"
                " family_id, consent_revision_id, collection_policy, state,"
                " created_at_utc, updated_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                (example_id, job_id, family_id, consent_revision_id,
                 collection_policy, "captured_unreviewed", now, now))
            return example_id
        self._submit(op)
        return example_id

    def set_example_state(self, example_id, state):
        def op():
            self._db.execute(
                "UPDATE training_examples SET state=?, updated_at_utc=?"
                " WHERE example_id=?",
                (state, ids.now_utc_iso(self.now_fn()), example_id))
        self._submit(op)

    def append_revision(self, example_id, envelope: dict, parent_revision_id=None):
        revision_id = envelope.get("revision_id") or ids.new_id("rev")
        envelope = dict(envelope)
        envelope["revision_id"] = revision_id
        envelope["parent_revision_id"] = parent_revision_id
        payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        now = ids.now_utc_iso(self.now_fn())

        def op():
            self._db.execute(
                "INSERT INTO training_revisions(revision_id, example_id,"
                " parent_revision_id, created_at_utc, envelope_json,"
                " content_sha256) VALUES(?,?,?,?,?,?)",
                (revision_id, example_id, parent_revision_id, now, payload,
                 ids.sha256_text(payload)))
            self._db.execute(
                "UPDATE training_examples SET latest_revision_id=?,"
                " updated_at_utc=? WHERE example_id=?",
                (revision_id, now, example_id))
            return revision_id
        self._submit(op)
        return revision_id

    def latest_revision(self, example_id):
        def op():
            # rowid = monotonic insert order; ISO-ms timestamps can tie.
            row = self._db.execute(
                "SELECT envelope_json FROM training_revisions WHERE example_id=?"
                " ORDER BY rowid DESC LIMIT 1",
                (example_id,)).fetchone()
            return json.loads(row[0]) if row else None
        return self._submit(op, wait=True)

    def example_for_job(self, job_id):
        return self._submit(lambda: self._db.execute(
            "SELECT example_id, state FROM training_examples WHERE job_id=?"
            " ORDER BY rowid DESC LIMIT 1", (job_id,)).fetchone(),
            wait=True)

    def latest_example(self):
        """Most recent example row: (example_id, job_id, state) or None."""
        return self._submit(lambda: self._db.execute(
            "SELECT example_id, job_id, state FROM training_examples"
            " ORDER BY rowid DESC LIMIT 1"
        ).fetchone(), wait=True)

    def append_consent(self, state, policy=None, note=None):
        consent_id = ids.new_id("consent")

        def op():
            self._db.execute(
                "INSERT INTO consent_revisions(consent_revision_id, state,"
                " policy_json, created_at_utc, note) VALUES(?,?,?,?,?)",
                (consent_id, state, json.dumps(policy or {}),
                 ids.now_utc_iso(self.now_fn()), note))
        self._submit(op)
        return consent_id

    def consent_state(self):
        return self._submit(lambda: (self._db.execute(
            "SELECT state FROM consent_revisions ORDER BY rowid DESC"
        ).fetchone() or ("disabled",))[0], wait=True)

    def current_consent_id(self):
        return self._submit(lambda: (self._db.execute(
            "SELECT consent_revision_id FROM consent_revisions"
            " ORDER BY rowid DESC"
        ).fetchone() or (None,))[0], wait=True)

    # ---- leases, retention, deletion ------------------------------------------

    def grant_lease(self, artifact_id, holder, days=None):
        """holder ∈ {history, recovery, training}; days=None pins (S29.14)."""
        lease_id = ids.new_id("lease")
        now = self.now_fn()

        def op():
            grant_lease_row(self._db, artifact_id, holder, days=days,
                            granted_at_epoch=now, lease_id=lease_id)
        self._submit(op)
        return lease_id

    def _live_lease_count(self, artifact_id, now_iso):
        return len(self._db.execute(
            "SELECT lease_id FROM artifact_leases WHERE artifact_id=? AND"
            " revoked_at_utc IS NULL AND (expires_at_utc IS NULL OR"
            " expires_at_utc > ?)", (artifact_id, now_iso)).fetchall())

    def prune(self, now=None):
        """Apply history retention. Never touches artifacts of unresolved
        jobs or content a live lease pins (M02-AC06). Runs on the writer
        thread; returns {purged, kept_by_lease}."""
        now = now if now is not None else self.now_fn()

        def op():
            now_iso = ids.now_utc_iso(now)
            placeholders = ",".join("?" * len(TERMINAL_STATES))
            unresolved = set(r[0] for r in self._db.execute(
                f"SELECT job_id FROM jobs WHERE state NOT IN ({placeholders})",
                tuple(TERMINAL_STATES)))
            purged = 0
            kept_by_lease = 0
            for (artifact_id, job_id, rclass, content_path, created) in \
                    self._db.execute(
                        "SELECT artifact_id, job_id, retention_class,"
                        " content_path, created_at_utc FROM artifacts"
                        " WHERE purged=0").fetchall():
                if rclass == "legacy":
                    # Imported legacy history is lossless by contract
                    # (Spec S08 / M02-AC02): only delete-everywhere removes
                    # it. Re-import cannot restore purged content because
                    # the imports bookkeeping survives pruning.
                    continue
                if job_id and job_id in unresolved:
                    continue
                if self._live_lease_count(artifact_id, now_iso):
                    kept_by_lease += 1
                    continue
                if rclass == "training":
                    days = self.retention_days["training_buffer"]
                elif content_path:  # audio payload
                    job = self._db.execute(
                        "SELECT state FROM jobs WHERE job_id=?",
                        (job_id,)).fetchone() if job_id else None
                    failed = bool(job and job[0] in
                                  ("failed_recoverable", "failed_unrecoverable"))
                    days = self.retention_days[
                        "audio_failed" if failed else "audio_success"]
                else:
                    days = self.retention_days["transcript"]
                created_t = _iso_to_epoch(created)
                if created_t is None or (now - created_t) < days * 86400:
                    continue
                if self._purge_artifact(artifact_id):
                    purged += 1
            self.emit("store.prune", level="INFO",
                      reason_code="retention_pass",
                      detail=f"purged={purged} kept_by_lease={kept_by_lease}")
            return {"purged": purged, "kept_by_lease": kept_by_lease}
        return self._submit(op, wait=True)

    def prune_training(self, now=None):
        """Expire the 30-day unreviewed evidence buffer (S29.14); pinned
        examples (a training lease with no expiry) are never evicted."""
        now = now if now is not None else self.now_fn()

        def op():
            now_iso = ids.now_utc_iso(now)
            expired = 0
            rows = self._db.execute(
                "SELECT example_id, job_id, created_at_utc FROM"
                " training_examples WHERE state IN ('captured_unreviewed',"
                " 'review_candidate')").fetchall()
            for ex_id, job_id, created in rows:
                created_t = _iso_to_epoch(created)
                if created_t is None or \
                        (now - created_t) < self.retention_days["training_buffer"] * 86400:
                    continue
                pinned = self._db.execute(
                    "SELECT 1 FROM artifact_leases l JOIN artifacts a ON"
                    " a.artifact_id = l.artifact_id WHERE a.job_id=? AND"
                    " l.holder='training' AND l.revoked_at_utc IS NULL AND"
                    " l.expires_at_utc IS NULL", (job_id,)).fetchone()
                if pinned:
                    continue
                for (aid,) in self._db.execute(
                        "SELECT artifact_id FROM artifacts WHERE job_id=?",
                        (job_id,)).fetchall():
                    self._revoke_leases(aid)
                    self._purge_artifact(aid)
                self._db.execute(
                    "UPDATE training_examples SET state='expired',"
                    " updated_at_utc=? WHERE example_id=?", (now_iso, ex_id))
                self._db.execute(
                    "INSERT INTO deletion_tombstones(tombstone_id, target_kind,"
                    " target_id, reason, created_at_utc) VALUES(?,?,?,?,?)",
                    (ids.new_id("tomb"), "example", ex_id,
                     "training_buffer_expired", now_iso))
                expired += 1
            return {"expired": expired}
        return self._submit(op, wait=True)

    def prune_metadata(self, now=None):
        """Job-row metadata pruning (the M02 ``metadata`` knob, enforced
        from M13): delete terminal jobs past the metadata window whose
        content is already gone (no unpurged artifact, no live training
        example). Usage facts are NOT deleted — aggregate retention is
        independent of text and job-row retention (S21, M13-AC03), which
        is why usage_facts carries its own app/duration/word copies.
        Effective pruning therefore starts once every content retention
        (transcript/audio) has expired past the metadata window, not
        before."""
        now = now if now is not None else self.now_fn()

        def op():
            now_iso = ids.now_utc_iso(now)
            placeholders = ",".join("?" * len(TERMINAL_STATES))
            live_example_states = ("captured_unreviewed",
                                   "review_candidate", "annotated",
                                   "ambiguous", "quarantined_sensitive")
            deleted = 0
            rows = self._db.execute(
                f"SELECT job_id, updated_at_utc FROM jobs WHERE state IN"
                f" ({placeholders})",
                tuple(TERMINAL_STATES)).fetchall()
            for job_id, updated in rows:
                updated_t = _iso_to_epoch(updated)
                if updated_t is None or (now - updated_t) < \
                        self.retention_days["metadata"] * 86400:
                    continue
                if self._db.execute(
                        "SELECT 1 FROM artifacts WHERE job_id=? AND purged=0"
                        " LIMIT 1", (job_id,)).fetchone():
                    continue  # content still retained — the row stays
                if self._db.execute(
                    "SELECT 1 FROM training_examples WHERE job_id=? AND"
                    " state IN (?,?,?,?,?) LIMIT 1",
                        (job_id, *live_example_states)).fetchone():
                    continue  # a live example still references the job
                self._db.execute(
                    "DELETE FROM insertion_observations WHERE job_id=?",
                    (job_id,))
                self._db.execute(
                    "DELETE FROM insertions WHERE job_id=?", (job_id,))
                self._db.execute(
                    "DELETE FROM job_targets WHERE job_id=?", (job_id,))
                self._db.execute(
                    "DELETE FROM jobs WHERE job_id=?", (job_id,))
                deleted += 1
            if deleted:
                self.emit("store.metadata_pruned", level="INFO",
                          reason_code="retention_pass",
                          detail=f"jobs={deleted}")
            return {"jobs_deleted": deleted}
        return self._submit(op, wait=True)

    def delete_everywhere(self, target_kind, target_id, reason="user_request"):
        """Revoke every lease, purge every managed payload and derived record,
        leave only content-free tombstones (S29.14). Overrides immutability.
        target_kind ∈ {'example', 'job'}."""

        def op():
            now_iso = ids.now_utc_iso(self.now_fn())
            if target_kind == "example":
                row = self._db.execute(
                    "SELECT job_id FROM training_examples WHERE example_id=?",
                    (target_id,)).fetchone()
                job_id = row[0] if row else None
            else:
                job_id = target_id
            purged_artifacts = []
            if job_id:
                for (aid,) in self._db.execute(
                        "SELECT artifact_id FROM artifacts WHERE job_id=?",
                        (job_id,)).fetchall():
                    self._revoke_leases(aid)
                    if self._purge_artifact(aid):
                        purged_artifacts.append(aid)
                for (ex_id,) in self._db.execute(
                        "SELECT example_id FROM training_examples WHERE"
                        " job_id=?", (job_id,)).fetchall():
                    self._db.execute(
                        "DELETE FROM training_revisions WHERE example_id=?",
                        (ex_id,))
                    self._db.execute(
                        "UPDATE training_examples SET state='deleted',"
                        " latest_revision_id=NULL, updated_at_utc=? WHERE"
                        " example_id=?", (now_iso, ex_id))
                    self._db.execute(
                        "INSERT INTO deletion_tombstones(tombstone_id,"
                        " target_kind, target_id, reason, created_at_utc)"
                        " VALUES(?,?,?,?,?)",
                        (ids.new_id("tomb"), "example", ex_id, reason, now_iso))
            for aid in purged_artifacts:
                self._db.execute(
                    "INSERT INTO deletion_tombstones(tombstone_id, target_kind,"
                    " target_id, reason, created_at_utc) VALUES(?,?,?,?,?)",
                    (ids.new_id("tomb"), "artifact", aid, reason, now_iso))
            self.emit("training.deleted_everywhere", level="INFO",
                      reason_code=reason, job_id=job_id)
            return {"purged_artifacts": len(purged_artifacts)}
        return self._submit(op, wait=True)

    def _revoke_leases(self, artifact_id):
        self._db.execute(
            "UPDATE artifact_leases SET revoked_at_utc=? WHERE artifact_id=?"
            " AND revoked_at_utc IS NULL",
            (ids.now_utc_iso(self.now_fn()), artifact_id))

    def _purge_artifact(self, artifact_id) -> bool:
        row = self._db.execute(
            "SELECT content_path FROM artifacts WHERE artifact_id=? AND"
            " purged=0", (artifact_id,)).fetchone()
        if row is None:
            return False
        # Commit the row change first; unlink afterwards. If the op fails
        # between the two, the database consistently says purged and the
        # leftover file becomes an orphan the sweep quarantines — never a
        # live row pointing at a deleted file.
        self._db.execute(
            "UPDATE artifacts SET content_text=NULL, content_path=NULL,"
            " purged=1 WHERE artifact_id=?", (artifact_id,))
        if row[0]:
            try:
                (self.artifacts_dir / row[0]).unlink(missing_ok=True)
            except OSError:
                pass
        return True

    def tombstones(self):
        return self._submit(lambda: self._db.execute(
            "SELECT tombstone_id, target_kind, target_id, reason,"
            " created_at_utc FROM deletion_tombstones ORDER BY"
            " created_at_utc").fetchall(), wait=True)

    # ---- consistency -----------------------------------------------------

    def verify(self):
        """Content-free consistency report over jobs/artifacts/evidence."""

        def op():
            issues = []
            expected_tables = {"schema_meta", "jobs", "artifacts", "imports",
                               "training_examples", "training_revisions",
                               "artifact_leases"}
            have = {r[0] for r in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not expected_tables <= have:
                issues.append("missing core tables")
            for (ex_id,) in self._db.execute(
                    "SELECT example_id FROM training_examples").fetchall():
                n = self._db.execute(
                    "SELECT COUNT(*) FROM training_revisions WHERE example_id=?",
                    (ex_id,)).fetchone()[0]
                if n == 0:
                    issues.append(f"example {ex_id} has no revision")
            for (rev_id, payload) in self._db.execute(
                    "SELECT revision_id, envelope_json FROM"
                    " training_revisions").fetchall():
                try:
                    env = json.loads(payload)
                except json.JSONDecodeError:
                    issues.append(f"revision {rev_id} envelope unparsable")
                    continue
                for key, aid in (env.get("artifact_ids") or {}).items():
                    if aid is None:
                        continue
                    if not self._db.execute(
                            "SELECT 1 FROM artifacts WHERE artifact_id=?",
                            (aid,)).fetchone():
                        reasons = env.get("missing_reasons") or {}
                        if key not in reasons:
                            issues.append(
                                f"revision {rev_id} references missing artifact"
                                f" {aid} without a missing-reason")
                prep = env.get("audio_preparation") or {}
                if prep and not prep.get("artifact_id"):
                    reasons = env.get("missing_reasons") or {}
                    if "audio_preparation" not in reasons:
                        issues.append(
                            f"revision {rev_id} has decode ranges with no"
                            " parent audio artifact and no missing-reason")
            for (lease_id, aid) in self._db.execute(
                    "SELECT lease_id, artifact_id FROM"
                    " artifact_leases").fetchall():
                if not self._db.execute(
                        "SELECT 1 FROM artifacts WHERE artifact_id=?",
                        (aid,)).fetchone():
                    issues.append(f"lease {lease_id} on missing artifact {aid}")
            orphan_files = self._orphan_files()
            return {"ok": not issues and not orphan_files,
                    "issues": issues, "orphan_files": orphan_files}
        return self._submit(op, wait=True)

    def _orphan_files(self):
        known = {r[0] for r in self._db.execute(
            "SELECT content_path FROM artifacts WHERE content_path IS NOT NULL")}
        return [p.name for p in self.artifacts_dir.glob("*.wav")
                if p.name not in known]

    def sweep_orphans(self, grace_sec=3600):
        """Crash between payload write and record commit (E19.2): files with
        no database row move to orphans/ once past the in-flight grace
        period instead of being silently deleted."""

        def op():
            now = self.now_fn()
            moved = []
            known = {r[0] for r in self._db.execute(
                "SELECT content_path FROM artifacts WHERE content_path"
                " IS NOT NULL")}
            for p in self.artifacts_dir.glob("*.wav"):
                if p.name in known:
                    continue
                try:
                    if now - p.stat().st_mtime < grace_sec:
                        continue
                    dest = self.artifacts_dir / "orphans"
                    dest.mkdir(exist_ok=True)
                    p.rename(dest / p.name)
                    moved.append(p.name)
                except OSError:
                    continue
            if moved:
                self.emit("store.orphan_files_swept", level="WARNING",
                          reason_code="orphan_payloads",
                          detail=f"n={len(moved)}")
            return moved
        return self._submit(op, wait=True)


def _row_to_dict(row, cols):
    if row is None:
        return None
    return dict(zip(cols, row))


# ---- shared writer-thread SQL (module-level so same-package domain
# layers compose them INSIDE one Store.submit op without duplicating
# the INSERT statements — the drift risk of parallel copies outlives
# any single milestone; M10's transform artifacts will reuse these) ----

def insert_text_artifact_row(conn, *, artifact_id, job_id, stage, role, text,
                             kind="text", retention_class="history",
                             meta=None, parent_artifact_id=None,
                             created_at_utc):
    payload = text if isinstance(text, str) else json.dumps(
        text, ensure_ascii=False, indent=1)
    conn.execute(
        "INSERT INTO artifacts(artifact_id, job_id, stage,"
        " parent_artifact_id, kind, role, content_path, content_text,"
        " sha256, bytes, meta_json, retention_class, purged,"
        " created_at_utc) VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?,0,?)",
        (artifact_id, job_id, stage, parent_artifact_id, kind, role,
         payload, ids.sha256_text(payload), len(payload.encode("utf-8")),
         json.dumps(meta or {}, ensure_ascii=False), retention_class,
         created_at_utc))
    return artifact_id


def grant_lease_row(conn, artifact_id, holder, *, days=None,
                    granted_at_epoch, lease_id=None):
    conn.execute(
        "INSERT INTO artifact_leases(lease_id, artifact_id, holder,"
        " granted_at_utc, expires_at_utc) VALUES(?,?,?,?,?)",
        (lease_id or ids.new_id("lease"), artifact_id, holder,
         ids.now_utc_iso(granted_at_epoch),
         ids.now_utc_iso(granted_at_epoch + days * 86400)
         if days is not None else None))
