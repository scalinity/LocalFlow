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
import errno
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


# M14 (Spec S22/S29.7-S29.13, contracts/learning.md + dataset_exports.md):
# correction-learning candidates, versioned correction labels, sampling
# decisions, family split assignments (versioned, exposure-tracked) with
# tags kept separate from partitions, profile snapshots with deletable
# evidence links, and export manifests. Rows carry ids/hashes/counts
# only — before/after texts and graft payloads live in lease-governed
# artifacts written inside the same writer op. Additive only; no frozen
# identity changes.
_MIGRATIONS[10] = [
    """CREATE TABLE IF NOT EXISTS learning_candidates(
         candidate_id TEXT PRIMARY KEY,
         example_id TEXT,
         job_id TEXT NOT NULL,
         source TEXT NOT NULL,
         observation_id TEXT,
         before_artifact_id TEXT,
         after_artifact_id TEXT,
         changed_spans_json TEXT NOT NULL DEFAULT '[]',
         proposed_alias TEXT,
         proposed_canonical TEXT,
         proposed_scope_kind TEXT NOT NULL DEFAULT 'global',
         proposed_scope_value TEXT,
         status TEXT NOT NULL DEFAULT 'pending',
         decided_at_utc TEXT,
         rejection_reason TEXT,
         vocabulary_entry_id TEXT,
         vocabulary_action TEXT,
         counterexample_json TEXT,
         classification_json TEXT NOT NULL DEFAULT '{}',
         created_at_utc TEXT NOT NULL,
         updated_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_learning_candidates_job
         ON learning_candidates(job_id)""",
    """CREATE INDEX IF NOT EXISTS idx_learning_candidates_status
         ON learning_candidates(status)""",
    """CREATE TABLE IF NOT EXISTS correction_labels(
         label_id TEXT PRIMARY KEY,
         example_id TEXT NOT NULL,
         candidate_id TEXT,
         revision INTEGER NOT NULL,
         origin_stages_json TEXT NOT NULL DEFAULT '[]',
         edit_kind TEXT NOT NULL,
         domains_json TEXT NOT NULL DEFAULT '[]',
         pipeline_effect TEXT NOT NULL DEFAULT 'unknown',
         evidence_status TEXT NOT NULL,
         reviewer TEXT NOT NULL,
         abstained INTEGER NOT NULL DEFAULT 0,
         graft_artifact_id TEXT,
         notes TEXT,
         created_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_correction_labels_example
         ON correction_labels(example_id)""",
    """CREATE TABLE IF NOT EXISTS sampling_decisions(
         decision_id TEXT PRIMARY KEY,
         policy TEXT NOT NULL,
         seed TEXT NOT NULL,
         example_id TEXT NOT NULL,
         job_id TEXT,
         stratum TEXT NOT NULL,
         inclusion_reason TEXT NOT NULL,
         inclusion_probability REAL,
         population_hash TEXT,
         event_seq INTEGER,
         created_at_utc TEXT NOT NULL)""",
    """CREATE INDEX IF NOT EXISTS idx_sampling_decisions_example
         ON sampling_decisions(example_id)""",
    """CREATE TABLE IF NOT EXISTS split_assignments(
         assignment_version INTEGER PRIMARY KEY,
         policy TEXT NOT NULL,
         seed TEXT NOT NULL,
         family_count INTEGER NOT NULL,
         created_at_utc TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS training_memberships(
         example_id TEXT NOT NULL,
         family_id TEXT NOT NULL,
         assignment_version INTEGER NOT NULL,
         partition TEXT NOT NULL,
         exposed INTEGER NOT NULL DEFAULT 0,
         exposed_reason TEXT,
         created_at_utc TEXT NOT NULL,
         PRIMARY KEY(example_id, assignment_version))""",
    """CREATE INDEX IF NOT EXISTS idx_training_memberships_family
         ON training_memberships(family_id, assignment_version)""",
    """CREATE TABLE IF NOT EXISTS example_tags(
         example_id TEXT NOT NULL,
         tag TEXT NOT NULL,
         created_at_utc TEXT NOT NULL,
         PRIMARY KEY(example_id, tag))""",
    """CREATE TABLE IF NOT EXISTS profile_snapshots(
         snapshot_id TEXT PRIMARY KEY,
         algorithm_version INTEGER NOT NULL,
         computed_at_utc TEXT NOT NULL,
         eligible_words INTEGER NOT NULL,
         measured_json TEXT NOT NULL,
         cards_json TEXT NOT NULL,
         state TEXT NOT NULL DEFAULT 'current',
         invalidated_reason TEXT,
         source_example_count INTEGER NOT NULL,
         coverage_from_utc TEXT,
         coverage_to_utc TEXT)""",
    """CREATE TABLE IF NOT EXISTS profile_evidence(
         snapshot_id TEXT NOT NULL,
         example_id TEXT NOT NULL,
         card_id TEXT NOT NULL,
         role TEXT NOT NULL,
         included INTEGER NOT NULL DEFAULT 1,
         excluded_at_utc TEXT,
         PRIMARY KEY(snapshot_id, example_id, card_id))""",
    """CREATE TABLE IF NOT EXISTS export_manifests(
         export_id TEXT PRIMARY KEY,
         state TEXT NOT NULL,
         task_views_json TEXT NOT NULL,
         manifest_json TEXT,
         destination TEXT,
         fingerprint TEXT,
         examples_count INTEGER,
         excluded_count INTEGER,
         error TEXT,
         created_at_utc TEXT NOT NULL,
         finalized_at_utc TEXT)""",
]


# M02 remediation (M02-AUDIT-01/02/04): a durable, content-free job
# deletion barrier and durable payload-purge intents. Additive only.
# ``job_deletions`` is checked inside every evidence publication op, so a
# producer that resumes after delete-everywhere cannot recreate content;
# ``purge_intents`` records every payload file a committed purge still
# has to remove — the unlink happens only AFTER the SQL commit and the
# intent stays pending (retried on reconcile and at every open) until the
# file is actually gone. SQL cannot roll back an unlink, so the file is
# never touched before the row change is durable.
_MIGRATIONS[11] = [
    """CREATE TABLE IF NOT EXISTS job_deletions(
         job_id TEXT PRIMARY KEY,
         reason TEXT NOT NULL,
         deleted_at_utc TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS purge_intents(
         intent_id TEXT PRIMARY KEY,
         artifact_id TEXT,
         job_id TEXT,
         root TEXT NOT NULL,
         path TEXT NOT NULL,
         reason TEXT NOT NULL,
         created_at_utc TEXT NOT NULL,
         attempts INTEGER NOT NULL DEFAULT 0,
         last_error TEXT,
         completed_at_utc TEXT)""",
    """CREATE INDEX IF NOT EXISTS idx_purge_intents_open
         ON purge_intents(completed_at_utc)""",
    # Backfill the barrier for deletions made before v11 (idempotent, so
    # the repair path can re-run it): jobs whose examples were deleted
    # everywhere, and jobs whose artifacts carry a deletion tombstone
    # (retention never writes artifact tombstones).
    """INSERT OR IGNORE INTO job_deletions(job_id, reason, deleted_at_utc)
         SELECT job_id, 'pre_v11_deletion', MIN(updated_at_utc)
         FROM training_examples WHERE state='deleted' GROUP BY job_id""",
    """INSERT OR IGNORE INTO job_deletions(job_id, reason, deleted_at_utc)
         SELECT a.job_id, 'pre_v11_deletion', MIN(t.created_at_utc)
         FROM deletion_tombstones t JOIN artifacts a
           ON a.artifact_id = t.target_id
         WHERE t.target_kind='artifact' AND a.job_id IS NOT NULL
         GROUP BY a.job_id""",
]

# Tables whose loss at the current schema version is corruption, not a
# torn additive migration, whenever rows that depend on them survive
# (M02-AUDIT-18). Each maps to queries that detect such surviving
# dependents; the queries only touch tables that must then exist.
_CORE_DEPENDENTS = {
    "jobs": ("SELECT 1 FROM artifacts WHERE job_id LIKE 'job-%' LIMIT 1",
             "SELECT 1 FROM training_examples LIMIT 1"),
    "artifacts": ("SELECT 1 FROM artifact_leases LIMIT 1",
                  "SELECT 1 FROM training_revisions LIMIT 1",
                  "SELECT 1 FROM imports LIMIT 1"),
    "training_examples": ("SELECT 1 FROM training_revisions LIMIT 1",),
    "training_revisions": ("SELECT 1 FROM training_examples WHERE"
                           " latest_revision_id IS NOT NULL LIMIT 1",),
    "artifact_leases": ("SELECT 1 FROM artifacts WHERE purged=0 AND"
                        " retention_class='training' LIMIT 1",),
    "consent_revisions": ("SELECT 1 FROM training_examples WHERE"
                          " consent_revision_id IS NOT NULL LIMIT 1",),
    "imports": ("SELECT 1 FROM artifacts WHERE retention_class='legacy'"
                " LIMIT 1", "SELECT 1 FROM legacy_dictations LIMIT 1"),
    "import_runs": ("SELECT 1 FROM imports WHERE source_kind='legacy_log'"
                    " LIMIT 1",),
    "legacy_dictations": ("SELECT 1 FROM imports WHERE"
                          " source_kind='stats_db' LIMIT 1",),
    "deletion_tombstones": ("SELECT 1 FROM training_examples WHERE"
                            " state='deleted' LIMIT 1",),
    # job_deletions is rebuilt from the tombstones by the v11 backfill
    # (re-applied by the repair path); a lost purge_intents table loses
    # only unfinished unlinks, which the orphan sweep still surfaces —
    # neither is refused.
}


class JobDeletedError(RuntimeError):
    """An evidence write for a job (or example) that delete-everywhere
    already removed. Content-free by construction: the message names no
    id, so it is safe in last_errors and store.write_failed events."""


_REASON_TOKEN = __import__("re").compile(r"^[a-z0-9_]{1,64}$")


def safe_reason(reason) -> str:
    """Tombstone/deletion reasons are codes, never caller free text."""
    return reason if isinstance(reason, str) and _REASON_TOKEN.match(
        reason) else "unspecified"


def conn_job_deleted(conn, job_id) -> bool:
    if not job_id:
        return False
    return conn.execute("SELECT 1 FROM job_deletions WHERE job_id=?",
                        (job_id,)).fetchone() is not None


def conn_assert_job_writable(conn, job_id):
    """The deletion barrier (M02-AUDIT-01): raise inside the writer op, so
    the whole op rolls back and nothing is recreated for a deleted job."""
    if conn_job_deleted(conn, job_id):
        raise JobDeletedError("evidence write refused: job was deleted")


def conn_assert_example_writable(conn, example_id):
    row = conn.execute(
        "SELECT job_id, state FROM training_examples WHERE example_id=?",
        (example_id,)).fetchone()
    if row is None:
        raise LookupError("evidence write refused: example not found")
    if row[1] == "deleted":
        raise JobDeletedError("evidence write refused: example was deleted")
    conn_assert_job_writable(conn, row[0])
    return row[0]


_ARTIFACT_ID = __import__("re").compile(r"^art-[0-9a-f]{32}$")


def iter_artifact_refs(obj, path="", _ref_slot=False, _keys=()):
    """Every artifact id an envelope references, with its JSON path —
    top-level artifact_ids and nested prompt/proposal/audio-preparation
    references alike (M02-AUDIT-05/14). A reference is any string in an
    ``*artifact_id`` slot or an ``*artifact_ids`` mapping/list, plus any
    string shaped exactly like a minted artifact id. ``missing_reasons``
    and ``completeness`` hold reasons and paths, never references.
    Yields (display_path, artifact_id, key_tuple); walk back with the
    key tuple (keys may themselves contain '.' or '[')."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not _keys and k in ("completeness", "missing_reasons"):
                continue
            slot = isinstance(k, str) and (k.endswith("artifact_id")
                                           or k.endswith("artifact_ids"))
            yield from iter_artifact_refs(
                v, f"{path}.{k}" if path else str(k), _ref_slot or slot,
                _keys + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_artifact_refs(v, f"{path}[{i}]", _ref_slot,
                                          _keys + (i,))
    elif isinstance(obj, str) and obj and (
            _ref_slot or _ARTIFACT_ID.match(obj)):
        yield path, obj, _keys


def _set_path(obj, keys, value):
    """Replace one reference found by iter_artifact_refs (key tuple)."""
    cur = obj
    for k in keys[:-1]:
        cur = cur[k]
    cur[keys[-1]] = value


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
        # M02-AUDIT-15: explicit lifecycle. Admission closes at the START
        # of close() ("closing"); accepted work drains; the connection is
        # closed only once the writer thread has actually exited.
        self.lifecycle = "open"
        self._executing = False
        self.close_status = None
        # M02-AUDIT-02/04: set by an op that recorded purge intents; the
        # writer drains them only after that op's commit.
        self._purge_pending = False
        # Job-scoped payload directories outside the artifacts dir (the
        # app's transcript-logging debug copies, recovery journal) that
        # delete-everywhere must also clear: (directory, job_id -> glob).
        self._job_payload_dirs = []
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.artifacts_dir, 0o700)
            os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            self._migrate()
        except Exception:
            self._db.close()
            raise
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass
        # A crash between a purge commit and its unlink leaves the intent
        # pending; finish that deletion work before anything else runs.
        self._drain_purge_intents()
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
                self._executing = True
            try:
                self._purge_pending = False
                try:
                    out = fn()
                    err = None
                    # One commit per operation keeps multi-statement ops
                    # (prune, delete-everywhere, migration-style batches)
                    # atomic.
                    self._db.commit()
                except Exception as e:  # surfaced, never crashes
                    out, err = None, f"{type(e).__name__}: {e}"
                    self.last_errors.append(err)
                    try:
                        self._db.rollback()
                    except sqlite3.DatabaseError:
                        pass
                    # The op's purge intents rolled back with it: their
                    # files are still referenced by live rows, untouched.
                    self._purge_pending = False
                    self.emit("store.write_failed", level="ERROR",
                              reason_code="store_error", detail=err[:200])
                if self._purge_pending:
                    # Only now is the purge durable; remove the files.
                    self._purge_pending = False
                    self._drain_purge_intents()
                if isinstance(out, dict) and "_purge_intents" in out:
                    # Report what is still on disk from HERE (no second
                    # submission that a concurrent close could refuse).
                    out["pending_purges"] = self._count_pending(
                        out.pop("_purge_intents"))
                if result_q is not None:
                    result_q.put((out, err))
            finally:
                with self._cond:
                    self._executing = False
                    self._cond.notify_all()

    def _submit(self, fn, wait=False, timeout=15.0):
        """Queue one op. ``timeout`` bounds only the CALLER's wait: a
        TimeoutError does not cancel the op, which stays queued and may
        still commit later (M02-AUDIT-15/05) — callers that need to know
        pre-allocate their ids and re-read."""
        result_q = queue.Queue(maxsize=1) if wait else None
        with self._cond:
            if self.lifecycle != "open":
                # Admission is closed from the first moment of close():
                # nothing is accepted that the drain might not cover.
                raise RuntimeError(f"store is {self.lifecycle}")
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
        """Barrier: all previously queued mutations have been EXECUTED.
        A barrier does not report whether an earlier fire-and-forget op
        failed — evidence completeness is established by the publishing
        op itself (``publish_example``), never by sync() returning."""
        self._submit(lambda: None, wait=True, timeout=timeout)

    def submit(self, fn, wait=True, timeout=15.0):
        """Run ``fn(connection)`` on the writer thread — the sanctioned
        entry point for same-package domain layers (M05
        vocabulary_store) so they honor the single-writer discipline
        while the connection itself stays private to this module."""
        return self._submit(lambda: fn(self._db), wait=wait,
                            timeout=timeout)

    def close(self, timeout=5.0) -> dict:
        """Close admission, drain accepted work, then stop. Returns an
        honest status: ``drained`` is False (with the count of accepted
        ops still pending) when the writer did not finish within
        ``timeout`` — the connection is then left open for the live
        writer instead of being closed under it (M02-AUDIT-15)."""
        deadline = time.monotonic() + timeout
        with self._cond:
            if self.lifecycle == "closed":
                return self.close_status
            self.lifecycle = "closing"
            while (self._queue or self._executing) \
                    and time.monotonic() < deadline:
                self._cond.wait(max(0.01, deadline - time.monotonic()))
            pending = len(self._queue) + (1 if self._executing else 0)
            self._stop = True
            self._cond.notify_all()
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        alive = self._thread.is_alive()
        if not alive:
            try:
                self._db.close()
            except sqlite3.DatabaseError:
                pass
        self.lifecycle = "closed"
        self.close_status = {"drained": pending == 0 and not alive,
                             "pending_ops": pending,
                             "writer_alive": alive}
        return self.close_status

    # ---- migration -------------------------------------------------------

    def _migrate(self):
        version = self._schema_version()
        target = max(_MIGRATIONS)
        if version > target:
            # A newer build wrote this store: its tables may carry
            # meanings this code cannot honor. Refuse, untouched
            # (M02-AUDIT-18).
            raise RuntimeError(
                f"store schema v{version} is newer than this build"
                f" supports (v{target}); refusing to open it")
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
        # (all DDL is IF NOT EXISTS / idempotent) when tables or indexes
        # are missing — but only when that repair is SAFE. A missing core
        # table whose dependent rows survive is corruption: recreating it
        # empty would present the lost relationships as a healthy empty
        # store (M02-AUDIT-18). That case is backed up and refused.
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
                    "usage_facts", "daily_aggregates",
                    "learning_candidates", "correction_labels",
                    "sampling_decisions", "split_assignments",
                    "training_memberships", "example_tags",
                    "profile_snapshots", "profile_evidence",
                    "export_manifests", "job_deletions", "purge_intents"}
        have = {r[0] for r in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        expected_idx = {m.group(1) for stmts in _MIGRATIONS.values()
                        for s in stmts for m in [__import__("re").search(
                            r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)",
                            s)] if m}
        have_idx = {r[0] for r in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        missing_tables = expected - have
        missing_idx = expected_idx - have_idx
        if version >= target and (missing_tables or missing_idx):
            corrupt = []
            for table in sorted(missing_tables & set(_CORE_DEPENDENTS)):
                for probe in _CORE_DEPENDENTS[table]:
                    try:
                        if self._db.execute(probe).fetchone():
                            corrupt.append(table)
                            break
                    except sqlite3.DatabaseError:
                        continue  # the dependent table is gone too
            if self.backup_dir is not None:
                self._backup(label="pre-repair")
            if corrupt:
                self.emit("store.schema_corrupt", level="ERROR",
                          reason_code="missing_core_table_with_dependents",
                          detail=",".join(corrupt))
                raise RuntimeError(
                    "store schema corrupt: core table(s) "
                    f"{', '.join(corrupt)} missing while dependent rows"
                    " remain; refusing to recreate them empty — restore"
                    " from backup")
            for v_repair in range(1, target + 1):
                for stmt in _MIGRATIONS[v_repair]:
                    self._db.execute(stmt)
            self._db.commit()
            self.emit("store.schema_repaired", level="WARNING",
                      reason_code=("missing_tables" if missing_tables
                                   else "missing_indexes"),
                      detail=f"tables={len(missing_tables)}"
                             f" indexes={len(missing_idx)}")

    def _schema_version(self) -> int:
        try:
            row = self._db.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.DatabaseError:
            return 0

    def _backup(self, label="pre-migrate"):
        stamp = ids.now_utc_iso(self.now_fn()).replace(":", "")
        dst = self.backup_dir / f"v2-{label}-{stamp}.db"
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

    def update_job_state(self, job_id, state, reason=None, *, retry=False,
                         expected_attempt=None):
        """Idempotent transition; stale/regressing states are discarded.
        A terminal state is final for stale-result purposes — the one
        deliberate exception is an explicit retry re-opening a
        ``failed_recoverable`` job to ``queued`` (contracts/jobs.md: a retry
        increments the attempt and keeps the job_id), which must be passed
        explicitly. ``expected_attempt`` (optional) fences the transition:
        a writer that still believes in an older attempt is discarded
        instead of settling the re-opened job (M02-AUDIT-09)."""
        now = ids.now_utc_iso(self.now_fn())

        def op():
            row = self._db.execute(
                "SELECT state, attempt FROM jobs WHERE job_id=?",
                (job_id,)).fetchone()
            if row is None:
                return False
            current = row[0]
            if expected_attempt is not None \
                    and int(row[1]) != int(expected_attempt):
                return False  # stale attempt: never settles a newer one
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
            if conn_job_deleted(self._db, job_id):
                # The staged file is referenced by no row: removing it is
                # safe whether or not anything commits.
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise JobDeletedError(
                    "evidence write refused: job was deleted")
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

    def artifact_payload(self, artifact_id, verify=False):
        """Read back retained content: text str, audio ndarray, or None.
        ``verify=True`` checks the payload bytes against the recorded
        sha256 first and raises ValueError on a mismatch (M02-AUDIT-14);
        the default keeps the historical read-only behavior."""
        art = self.artifact(artifact_id)
        if art is None or art["purged"]:
            return None
        if art["content_path"]:
            path = self.artifacts_dir / art["content_path"]
            if verify and ids.sha256_bytes(path.read_bytes()) \
                    != art["sha256"]:
                raise ValueError("artifact payload hash mismatch")
            arr, _rate = read_wav(path)
            return arr
        if verify and art["content_text"] is not None \
                and ids.sha256_text(art["content_text"]) != art["sha256"]:
            raise ValueError("artifact payload hash mismatch")
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

    def start_import_run(self, kind, sha, source_bytes, source_path):
        """Durably record a run's source snapshot (hash + byte length)
        BEFORE any of its records commit (M02-AUDIT-10). A run interrupted
        after committing some pairs then still identifies its bytes as a
        verified prefix of a later, grown source; ``finish_import_run``
        fills in the counts. An unfinished run keeps note
        ``status=started``."""
        run_id = ids.new_id("import")

        def op():
            self._db.execute(
                "INSERT INTO import_runs(run_id, source_kind, source_sha256,"
                " source_bytes, source_path, imported_records, skipped_records,"
                " imported_at_utc, note) VALUES(?,?,?,?,?,0,0,?,?)",
                (run_id, kind, sha, source_bytes, str(source_path),
                 ids.now_utc_iso(self.now_fn()), "status=started"))
        self._submit(op, wait=True)
        return run_id

    def finish_import_run(self, run_id, imported, skipped, note=None):
        def op():
            self._db.execute(
                "UPDATE import_runs SET imported_records=?, skipped_records=?,"
                " imported_at_utc=?, note=? WHERE run_id=?",
                (imported, skipped, ids.now_utc_iso(self.now_fn()),
                 "status=completed" + (f"; {note}" if note else ""), run_id))
        self._submit(op, wait=True)
        return run_id

    def import_legacy_stats_row(self, row, source_sha, locator):
        """Atomically import ONE legacy stats row plus its bookkeeping
        (M02-AUDIT-11). ``legacy_dictations.id`` is the original
        producer's id, global across sources, so a second source reusing
        an id is reconciled explicitly, never ``INSERT OR IGNORE``d:

        - same id, identical content → the same entity; bookkeeping points
          at the existing row (``duplicate_identical``);
        - same id, different content → a conflict: the source row is kept
          losslessly as a ``legacy`` conflict artifact (outside the dated
          legacy totals) and reported (``conflict``);
        - otherwise the row is inserted (``imported``).

        Bookkeeping commits only together with its data. Returns the
        outcome string, or ``skipped`` when this locator was imported."""
        ts = float(row["ts"])
        captured = ids.now_utc_iso(ts)
        cols = ("id", "ts", "duration_sec", "raw_text", "cleaned_text",
                "raw_words", "cleaned_words", "fixed_words", "wpm",
                "app_name", "app_bundle", "kind")
        values = tuple(ts if c == "ts" else row[c] for c in cols)
        now = ids.now_utc_iso(self.now_fn())

        def op():
            if self._db.execute(
                    "SELECT 1 FROM imports WHERE source_kind='stats_db' AND"
                    " source_sha256=? AND source_locator=?",
                    (source_sha, locator)).fetchone():
                return "skipped"
            existing = self._db.execute(
                f"SELECT {', '.join(cols)} FROM legacy_dictations WHERE id=?",
                (row["id"],)).fetchone()
            if existing is None:
                self._db.execute(
                    "INSERT INTO legacy_dictations(id, ts,"
                    " captured_at_utc, duration_sec, raw_text, cleaned_text,"
                    " raw_words, cleaned_words, fixed_words, wpm, app_name,"
                    " app_bundle, kind, imported_from_sha256)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (row["id"], ts, captured, *values[2:], source_sha))
                outcome, imported_id = "imported", \
                    f"legacy_dictations:{row['id']}"
            elif tuple(existing) == values:
                outcome, imported_id = "duplicate_identical", \
                    f"legacy_dictations:{row['id']}"
            else:
                artifact_id = ids.new_id("art")
                payload = json.dumps(dict(zip(cols, values)),
                                     ensure_ascii=False, sort_keys=True)
                self._db.execute(
                    "INSERT INTO artifacts(artifact_id, job_id, stage,"
                    " parent_artifact_id, kind, role, content_path,"
                    " content_text, sha256, bytes, meta_json,"
                    " retention_class, purged, created_at_utc)"
                    " VALUES(?,NULL,'import',NULL,?,?,NULL,?,?,?,?,"
                    "'legacy',0,?)",
                    (artifact_id, "legacy_stats_row_conflict",
                     "legacy_stats_row_conflict", payload,
                     ids.sha256_text(payload),
                     len(payload.encode("utf-8")),
                     json.dumps({"conflicts_with_legacy_id": row["id"],
                                 "source_sha256": source_sha,
                                 "time_quality": "known"}), now))
                outcome, imported_id = "conflict", artifact_id
            self._db.execute(
                "INSERT INTO imports(source_kind, source_sha256,"
                " source_locator, imported_id, imported_at_utc, time_quality)"
                " VALUES('stats_db',?,?,?,?,'known')",
                (source_sha, locator, imported_id, now))
            return outcome
        return self._submit(op, wait=True)

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
            conn_assert_job_writable(self._db, job_id)
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
        # 'deleted' is final: no later state change resurrects a
        # delete-everywhere tombstone (M02-AUDIT-01).
        def op():
            self._db.execute(
                "UPDATE training_examples SET state=?, updated_at_utc=?"
                " WHERE example_id=? AND state != 'deleted'",
                (state, ids.now_utc_iso(self.now_fn()), example_id))
        self._submit(op)

    def publish_example(self, *, job_id, family_id, envelope,
                        consent_revision_id=None, collection_policy=None,
                        quarantined=False, example_id=None, timeout=15.0):
        """ONE writer op publishing a live example: the example row in its
        FINAL initial state (``quarantined_sensitive`` from the first
        visible moment when the scanner flagged it — M02-AUDIT-03), its
        revision 1 and the latest pointer, after the deletion barrier and
        a check that every artifact the envelope references actually
        committed for this job (M02-AUDIT-05). An uncommitted reference
        is nulled with ``not_captured_at_stage`` and listed in the
        envelope's content-free ``completeness`` block — evidence is
        never called complete because ids were allocated. Waits for the
        commit; a TimeoutError does not cancel the op (the pre-allocated
        ``example_id`` identifies it if it commits later). Returns
        {example_id, revision_id, state, complete, uncommitted}."""
        example_id = example_id or ids.new_id("ex")
        revision_id = ids.new_id("rev")
        now = ids.now_utc_iso(self.now_fn())
        state = "quarantined_sensitive" if quarantined \
            else "captured_unreviewed"

        def op():
            conn_assert_job_writable(self._db, job_id)
            env = json.loads(json.dumps(envelope, default=str))
            env["example_id"] = example_id
            env["revision_id"] = revision_id
            env["parent_revision_id"] = None
            env["state"] = state
            missing = dict(env.get("missing_reasons") or {})
            uncommitted = []
            for path, aid, keys in list(iter_artifact_refs(env)):
                row = self._db.execute(
                    "SELECT job_id, purged FROM artifacts WHERE"
                    " artifact_id=?", (aid,)).fetchone()
                if row is not None and row[0] == job_id and not row[1]:
                    continue
                _set_path(env, keys, None)
                uncommitted.append(path)
                key = path[len("artifact_ids."):] \
                    if path.startswith("artifact_ids.") else path
                missing.setdefault(key, "not_captured_at_stage")
            env["missing_reasons"] = missing
            env["completeness"] = {"complete": not uncommitted,
                                   "uncommitted_references": uncommitted}
            self._db.execute(
                "INSERT INTO training_examples(example_id, job_id,"
                " family_id, consent_revision_id, collection_policy, state,"
                " created_at_utc, updated_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                (example_id, job_id, family_id, consent_revision_id,
                 collection_policy, state, now, now))
            conn_append_revision(self._db, example_id, env, None,
                                 revision_id=revision_id, now=now)
            return {"example_id": example_id, "revision_id": revision_id,
                    "state": state, "complete": not uncommitted,
                    "uncommitted": uncommitted}
        return self._submit(op, wait=True, timeout=timeout)

    def update_latest_revision(self, example_id, mutate, timeout=15.0):
        """Read the CURRENT latest revision, apply ``mutate(envelope) ->
        envelope`` and append the result as its child — all inside one
        writer op, so an annotation or observation that lands meanwhile
        is never overwritten by a stale snapshot and the parent is the
        revision actually extended (M02-AUDIT-08). ``mutate`` runs on the
        writer thread and must not call the store. Deleted examples are
        refused. Returns the new revision id (None when mutate declines)."""
        def op():
            conn_assert_example_writable(self._db, example_id)
            row = self._db.execute(
                "SELECT envelope_json, revision_id FROM training_revisions"
                " WHERE example_id=? ORDER BY rowid DESC LIMIT 1",
                (example_id,)).fetchone()
            if row is None:
                raise LookupError("example has no revision to extend")
            env = mutate(json.loads(row[0]))
            if env is None:
                return None
            return conn_append_revision(self._db, example_id, env, row[1])
        return self._submit(op, wait=True, timeout=timeout)

    def append_revision(self, example_id, envelope: dict, parent_revision_id=None):
        revision_id = envelope.get("revision_id") or ids.new_id("rev")
        envelope = dict(envelope)
        envelope["revision_id"] = revision_id
        envelope["parent_revision_id"] = parent_revision_id
        payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        now = ids.now_utc_iso(self.now_fn())

        def op():
            conn_assert_example_writable(self._db, example_id)
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

    def consent_snapshot(self):
        """(state, consent_revision_id) from ONE read of the latest
        revision — never a state from one revision paired with the id of
        another (M02-AUDIT-06). No revision reads as disabled."""
        return self._submit(lambda: tuple(self._db.execute(
            "SELECT state, consent_revision_id FROM consent_revisions"
            " ORDER BY rowid DESC LIMIT 1").fetchone()
            or ("disabled", None)), wait=True)

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
            # S29.14: reviewed examples are retained until explicitly
            # removed — their evidence is not aged out with the
            # unreviewed buffer (M02-AUDIT-16). Exclusion, expiry and
            # deletion leave REVIEWED_RETAINED_STATES and release this.
            marks = ",".join("?" * len(REVIEWED_RETAINED_STATES))
            reviewed = set(r[0] for r in self._db.execute(
                "SELECT job_id FROM training_examples WHERE state IN"
                f" ({marks})", REVIEWED_RETAINED_STATES))
            purged = 0
            kept_by_lease = 0
            kept_reviewed = 0
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
                if job_id and job_id in reviewed:
                    kept_reviewed += 1
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
                if self._purge_artifact(artifact_id, reason="retention"):
                    purged += 1
            self.emit("store.prune", level="INFO",
                      reason_code="retention_pass",
                      detail=f"purged={purged} kept_by_lease={kept_by_lease}"
                             f" kept_reviewed={kept_reviewed}")
            return {"purged": purged, "kept_by_lease": kept_by_lease,
                    "kept_reviewed": kept_reviewed}
        return self._submit(op, wait=True)

    def prune_training(self, now=None):
        """Expire the 30-day unreviewed evidence buffer (S29.14); pinned
        examples (a training lease with no expiry) are never evicted."""
        now = now if now is not None else self.now_fn()

        def op():
            now_iso = ids.now_utc_iso(now)
            expired = 0
            kept_other = 0
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
                # M02-AUDIT-07: only the TRAINING interest expires here.
                # A history/recovery lease (or a pin) on the same artifact
                # is an independent interest: the payload survives until
                # the shared live-lease predicate says no interest is
                # left. Non-training-class artifacts stay with the
                # generic history policy (prune).
                for (aid, rclass) in self._db.execute(
                        "SELECT artifact_id, retention_class FROM artifacts"
                        " WHERE job_id=? AND purged=0",
                        (job_id,)).fetchall():
                    self._db.execute(
                        "UPDATE artifact_leases SET revoked_at_utc=? WHERE"
                        " artifact_id=? AND holder='training' AND"
                        " revoked_at_utc IS NULL AND expires_at_utc IS NOT"
                        " NULL", (now_iso, aid))
                    if rclass != "training":
                        continue
                    if self._live_lease_count(aid, now_iso):
                        kept_other += 1
                        continue
                    self._purge_artifact(aid, reason="training_expiry")
                self._db.execute(
                    "UPDATE training_examples SET state='expired',"
                    " updated_at_utc=? WHERE example_id=?", (now_iso, ex_id))
                # M14: expiry propagates like deletion — no open
                # suggestion or label outlives the evidence it came from.
                self._stale_candidates(job_id, now_iso)
                self._db.execute(
                    "DELETE FROM correction_labels WHERE example_id=?",
                    (ex_id,))
                self._db.execute(
                    "INSERT INTO deletion_tombstones(tombstone_id, target_kind,"
                    " target_id, reason, created_at_utc) VALUES(?,?,?,?,?)",
                    (ids.new_id("tomb"), "example", ex_id,
                     "training_buffer_expired", now_iso))
                expired += 1
            return {"expired": expired,
                    "kept_by_other_interest": kept_other}
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
            live_example_states = LIVE_EXAMPLE_STATES
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
        target_kind ∈ {'example', 'job'}.

        M02 remediation: the job is recorded in ``job_deletions`` inside
        the same op — a durable barrier every later evidence write checks
        (M02-AUDIT-01); payload files (the artifacts plus any registered
        job-scoped copies: the transcript-logging debug WAV, recovery
        journal audio) become durable purge intents removed only after
        the commit (M02-AUDIT-02/04). The result says honestly whether
        every file is gone: ``complete`` is False while any intent is
        still pending (it is retried by ``reconcile_purges`` and at
        every open)."""
        reason = safe_reason(reason)

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
            intents = []
            if job_id:
                self._db.execute(
                    "INSERT OR IGNORE INTO job_deletions(job_id, reason,"
                    " deleted_at_utc) VALUES(?,?,?)",
                    (job_id, reason, now_iso))
                for (aid,) in self._db.execute(
                        "SELECT artifact_id FROM artifacts WHERE job_id=?",
                        (job_id,)).fetchall():
                    self._revoke_leases(aid)
                    if self._purge_artifact(aid, reason="deleted",
                                            intents=intents):
                        purged_artifacts.append(aid)
                for directory, pattern in self._job_payload_dirs:
                    try:
                        found = sorted(pathlib.Path(directory).glob(
                            pattern(job_id)))
                    except OSError:
                        found = []
                    for p in found:
                        intents.append(self._record_purge_intent(
                            None, job_id, "abs", str(p), "deleted"))
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
                    # M14 (S29.14/S22): derived labels go with the
                    # content they describe.
                    self._db.execute(
                        "DELETE FROM correction_labels WHERE example_id=?",
                        (ex_id,))
                    # Every snapshot that drew on the example loses its
                    # text-bearing content (phrases, cards), not only
                    # the current one: deletion overrides the
                    # snapshot-as-record rule (S29.14).
                    self._db.execute(
                        "UPDATE profile_snapshots SET"
                        " state='invalidated',"
                        " invalidated_reason='source_deleted',"
                        " measured_json='{}', cards_json='[]' WHERE"
                        " snapshot_id IN (SELECT snapshot_id FROM"
                        " profile_evidence WHERE example_id=?)",
                        (ex_id,))
                    self._db.execute(
                        "DELETE FROM profile_evidence WHERE example_id=?",
                        (ex_id,))
                # Candidates are keyed by JOB: a teach with collection
                # off has no example row, and its payload artifact was
                # purged with the job's artifacts above.
                self._stale_candidates(job_id, now_iso)
            for aid in purged_artifacts:
                self._db.execute(
                    "INSERT INTO deletion_tombstones(tombstone_id, target_kind,"
                    " target_id, reason, created_at_utc) VALUES(?,?,?,?,?)",
                    (ids.new_id("tomb"), "artifact", aid, reason, now_iso))
            return {"job_id": job_id,
                    "purged_artifacts": len(purged_artifacts),
                    "payload_files": len(intents),
                    "_purge_intents": intents}
        out = self._submit(op, wait=True)
        # The writer drained the intents right after the commit and
        # counted what is actually still on disk — never the plan.
        pending = out["pending_purges"]
        out["complete"] = pending == 0
        self.emit("training.deleted_everywhere", level="INFO",
                  reason_code=reason, job_id=out.pop("job_id"),
                  outcome="complete" if pending == 0 else "purge_pending",
                  detail=f"files={out['payload_files']} pending={pending}")
        return out

    def job_deleted(self, job_id) -> bool:
        """Whether delete-everywhere has barred this job (a check for
        producers writing job-scoped copies OUTSIDE the store)."""
        if not job_id:
            return False
        return self._submit(lambda: conn_job_deleted(self._db, job_id),
                            wait=True)

    def register_job_payload_dir(self, directory, pattern):
        """Declare a directory holding JOB-SCOPED payload copies the store
        does not index (``pattern(job_id)`` → glob, which must match only
        that job's files). delete-everywhere then removes them through the
        same durable purge intents (M02-AUDIT-02). Ownership is by name
        pattern, never guessed from content or age."""
        self._job_payload_dirs.append((pathlib.Path(directory), pattern))

    def _record_purge_intent(self, artifact_id, job_id, root, path, reason):
        intent_id = ids.new_id("purge")
        self._db.execute(
            "INSERT INTO purge_intents(intent_id, artifact_id, job_id, root,"
            " path, reason, created_at_utc) VALUES(?,?,?,?,?,?,?)",
            (intent_id, artifact_id, job_id, root, path, reason,
             ids.now_utc_iso(self.now_fn())))
        self._purge_pending = True
        return intent_id

    def _intent_paths(self, root, path):
        if root == "artifacts":
            # A payload the pre-remediation sweep moved to orphans/ is
            # the same managed file under the same unique name.
            return [self.artifacts_dir / path,
                    self.artifacts_dir / "orphans" / path]
        return [pathlib.Path(path)]

    def _drain_purge_intents(self):
        """Writer-thread (or pre-thread) only: attempt every pending purge
        intent. A removed or already-absent file completes its intent; a
        failure keeps it pending with an errno code (content-free) and an
        attempt count. Never raises."""
        try:
            rows = self._db.execute(
                "SELECT intent_id, root, path FROM purge_intents WHERE"
                " completed_at_utc IS NULL").fetchall()
        except sqlite3.DatabaseError:
            return
        if not rows:
            return
        now_iso = ids.now_utc_iso(self.now_fn())
        failed = 0
        try:
            for intent_id, root, path in rows:
                err = None
                for p in self._intent_paths(root, path):
                    try:
                        p.unlink(missing_ok=True)
                    except OSError as e:
                        err = errno.errorcode.get(e.errno, "OSError") \
                            if e.errno else type(e).__name__
                if err is None:
                    self._db.execute(
                        "UPDATE purge_intents SET completed_at_utc=?,"
                        " attempts=attempts+1, last_error=NULL WHERE"
                        " intent_id=?", (now_iso, intent_id))
                else:
                    failed += 1
                    self._db.execute(
                        "UPDATE purge_intents SET attempts=attempts+1,"
                        " last_error=? WHERE intent_id=?", (err, intent_id))
            self._db.commit()
        except sqlite3.DatabaseError:
            try:
                self._db.rollback()
            except sqlite3.DatabaseError:
                pass
            return
        if failed:
            self.emit("store.purge_pending", level="ERROR",
                      reason_code="payload_unlink_failed",
                      detail=f"pending={failed}")

    def _count_pending(self, intent_ids) -> int:
        """Writer-thread only."""
        if not intent_ids:
            return 0
        marks = ",".join("?" * len(intent_ids))
        return self._db.execute(
            "SELECT COUNT(*) FROM purge_intents WHERE completed_at_utc IS"
            f" NULL AND intent_id IN ({marks})",
            tuple(intent_ids)).fetchone()[0]

    def reconcile_purges(self) -> int:
        """Retry every pending purge intent now; returns how many remain."""
        self._submit(self._drain_purge_intents, wait=True)
        return self.pending_purges()

    def pending_purges(self, intent_ids=None) -> int:
        def op():
            if intent_ids is None:
                return self._db.execute(
                    "SELECT COUNT(*) FROM purge_intents WHERE"
                    " completed_at_utc IS NULL").fetchone()[0]
            marks = ",".join("?" * len(intent_ids))
            return self._db.execute(
                "SELECT COUNT(*) FROM purge_intents WHERE completed_at_utc"
                f" IS NULL AND intent_id IN ({marks})",
                tuple(intent_ids)).fetchone()[0]
        return self._submit(op, wait=True)

    def _stale_candidates(self, job_id, now_iso):
        """M14 (S29.14, M14-AC03): a job's evidence died (deleted or
        expired) — its open learning candidates go stale (never
        approvable) and lose their rule terms and spans. Rejected rows
        keep their rule terms: a rejection is the user's own decision
        that the pair must never be suggested again (S11); approved
        rows keep theirs — the rule already lives in the dictionary."""
        self._db.execute(
            "UPDATE learning_candidates SET status='stale',"
            " proposed_alias=NULL, proposed_canonical=NULL,"
            " changed_spans_json='[]', updated_at_utc=? WHERE job_id=?"
            " AND status IN ('pending','suppressed','dismissed','stale')",
            (now_iso, job_id))
        self._db.execute(
            "UPDATE learning_candidates SET changed_spans_json='[]',"
            " updated_at_utc=? WHERE job_id=? AND status IN"
            " ('approved','rejected')", (now_iso, job_id))

    def _revoke_leases(self, artifact_id):
        self._db.execute(
            "UPDATE artifact_leases SET revoked_at_utc=? WHERE artifact_id=?"
            " AND revoked_at_utc IS NULL",
            (ids.now_utc_iso(self.now_fn()), artifact_id))

    def _purge_artifact(self, artifact_id, reason="purge",
                        intents=None) -> bool:
        row = self._db.execute(
            "SELECT content_path, job_id FROM artifacts WHERE artifact_id=?"
            " AND purged=0", (artifact_id,)).fetchone()
        if row is None:
            return False
        # M02-AUDIT-04: the file is NOT touched here. The row change and a
        # durable purge intent commit together; the writer unlinks only
        # after that commit and keeps the intent pending until the file
        # is really gone (M02-AUDIT-02). A rollback therefore leaves a
        # live row with its payload intact, and a crash after the commit
        # leaves a pending intent that the next open finishes.
        self._db.execute(
            "UPDATE artifacts SET content_text=NULL, content_path=NULL,"
            " purged=1 WHERE artifact_id=?", (artifact_id,))
        if row[0]:
            intent = self._record_purge_intent(
                artifact_id, row[1], "artifacts", row[0], reason)
            if intents is not None:
                intents.append(intent)
        return True

    def tombstones(self):
        return self._submit(lambda: self._db.execute(
            "SELECT tombstone_id, target_kind, target_id, reason,"
            " created_at_utc FROM deletion_tombstones ORDER BY"
            " created_at_utc").fetchall(), wait=True)

    # ---- consistency -----------------------------------------------------

    def verify(self, deep=False):
        """Content-free consistency report over jobs/artifacts/evidence.

        Structural checks (always): core tables; live examples have a
        revision (a delete-everywhere tombstone legitimately has none);
        the latest pointer names the example's newest revision and every
        parent is a revision of the same example; EVERY artifact an
        envelope references — top-level and nested (prompt/proposal,
        audio preparation, stage blocks) — exists, belongs to the
        envelope's job, unless a missing-reason covers it (a purged row
        is a legitimate retention outcome, not corruption); leases name
        existing artifacts; unfinished purge intents are reported.

        ``deep=True`` additionally re-reads every live payload: a file
        must exist with the recorded size and sha256, inline text must
        match its sha256 (M02-AUDIT-14). Reports, never repairs."""

        def op():
            issues = []
            expected_tables = {"schema_meta", "jobs", "artifacts", "imports",
                               "training_examples", "training_revisions",
                               "artifact_leases"}
            have = {r[0] for r in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not expected_tables <= have:
                issues.append("missing core tables")
            examples = {r[0]: (r[1], r[2], r[3]) for r in self._db.execute(
                "SELECT example_id, job_id, state, latest_revision_id FROM"
                " training_examples").fetchall()}
            revs_by_ex = {}
            for ex_id, rev_id, parent in self._db.execute(
                    "SELECT example_id, revision_id, parent_revision_id FROM"
                    " training_revisions ORDER BY rowid").fetchall():
                revs_by_ex.setdefault(ex_id, []).append((rev_id, parent))
            for ex_id, (job_id, state, latest) in examples.items():
                revs = revs_by_ex.get(ex_id, [])
                if not revs:
                    if state != "deleted":
                        issues.append(f"example {ex_id} has no revision")
                    continue
                if latest != revs[-1][0]:
                    issues.append(f"example {ex_id} latest pointer is not"
                                  " its newest revision")
                own = {r for r, _p in revs}
                for rev_id, parent in revs[1:]:
                    if parent is not None and parent not in own:
                        issues.append(f"revision {rev_id} parent is not a"
                                      " revision of its example")
            for ex_id in revs_by_ex:
                if ex_id not in examples:
                    issues.append(f"revisions for unknown example {ex_id}")
            for (rev_id, ex_id, payload) in self._db.execute(
                    "SELECT revision_id, example_id, envelope_json FROM"
                    " training_revisions").fetchall():
                try:
                    env = json.loads(payload)
                except json.JSONDecodeError:
                    issues.append(f"revision {rev_id} envelope unparsable")
                    continue
                reasons = env.get("missing_reasons") or {}
                ex = examples.get(ex_id)
                job_id = env.get("job_id") or (ex[0] if ex else None)
                for path, aid, _keys in iter_artifact_refs(env):
                    key = path[len("artifact_ids."):] \
                        if path.startswith("artifact_ids.") else path
                    if key in reasons:
                        continue
                    row = self._db.execute(
                        "SELECT job_id, purged FROM artifacts WHERE"
                        " artifact_id=?", (aid,)).fetchone()
                    if row is None:
                        issues.append(
                            f"revision {rev_id} references missing artifact"
                            f" {aid} without a missing-reason")
                    elif job_id and row[0] and row[0] != job_id:
                        issues.append(
                            f"revision {rev_id} references artifact {aid}"
                            " owned by another job")
                    # A PURGED referenced artifact is not an issue: the
                    # content-free row stays, and retention legitimately
                    # removes payloads under live examples (E19.5's
                    # audio-deleted text-only case, which the exporter
                    # handles by eligibility).
                prep = env.get("audio_preparation") or {}
                if prep and not prep.get("artifact_id"):
                    if "audio_preparation" not in reasons and \
                            "audio_preparation.artifact_id" not in reasons:
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
            pending = self._db.execute(
                "SELECT COUNT(*) FROM purge_intents WHERE completed_at_utc"
                " IS NULL").fetchone()[0]
            if pending:
                issues.append(f"{pending} payload purge(s) still pending")
            payload_issues = []
            if deep:
                for aid, path, text, sha, size in self._db.execute(
                        "SELECT artifact_id, content_path, content_text,"
                        " sha256, bytes FROM artifacts WHERE purged=0"
                        ).fetchall():
                    if path:
                        p = self.artifacts_dir / path
                        try:
                            data = p.read_bytes()
                        except OSError:
                            payload_issues.append(
                                f"artifact {aid} payload file missing")
                            continue
                        if size is not None and len(data) != size:
                            payload_issues.append(
                                f"artifact {aid} payload size mismatch")
                        elif ids.sha256_bytes(data) != sha:
                            payload_issues.append(
                                f"artifact {aid} payload hash mismatch")
                    elif text is not None and ids.sha256_text(text) != sha:
                        payload_issues.append(
                            f"artifact {aid} text hash mismatch")
                issues.extend(payload_issues)
            orphan_files = self._orphan_files()
            return {"ok": not issues and not orphan_files,
                    "issues": issues, "orphan_files": orphan_files,
                    "pending_purges": pending, "deep": bool(deep)}
        return self._submit(op, wait=True, timeout=120.0 if deep else 15.0)

    def _managed_payload_names(self):
        """Names of files the store still owns: live payloads plus files a
        pending purge intent has yet to remove (never orphans)."""
        known = {r[0] for r in self._db.execute(
            "SELECT content_path FROM artifacts WHERE content_path"
            " IS NOT NULL")}
        known |= {r[0] for r in self._db.execute(
            "SELECT path FROM purge_intents WHERE root='artifacts' AND"
            " completed_at_utc IS NULL")}
        return known

    def _orphan_files(self):
        known = self._managed_payload_names()
        return [p.name for p in self.artifacts_dir.glob("*.wav")
                if p.name not in known]

    def sweep_orphans(self, grace_sec=3600):
        """Crash between payload write and record commit (E19.2): files with
        no database row move to orphans/ once past the in-flight grace
        period instead of being silently deleted. A file with a pending
        purge intent is NOT an orphan — it is deletion work, retried here
        first and never parked in orphans/ (M02-AUDIT-02)."""

        def op():
            self._drain_purge_intents()
            now = self.now_fn()
            moved = []
            known = self._managed_payload_names()
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

# Training-example states (S29.3). LIVE: the example exists and its
# evidence is retained. TRAINABLE: live and not quarantined — suspected
# secrets are excluded from training, export and derived statistics
# (S29.14) while staying reviewable so the deletion choice can be made.
LIVE_EXAMPLE_STATES = ("captured_unreviewed", "review_candidate",
                       "annotated", "ambiguous", "quarantined_sensitive")
TRAINABLE_STATES = ("captured_unreviewed", "review_candidate",
                    "annotated", "ambiguous")
# Reviewed examples retained until explicitly removed (S29.14): their job
# artifacts are exempt from age-based pruning while the example stays in
# one of these states (M02-AUDIT-16). Exclusion/expiry/deletion leave it.
REVIEWED_RETAINED_STATES = ("annotated",)


def conn_append_revision(conn, example_id, env, parent_revision_id, *,
                         revision_id=None, now=None):
    """The one writer-thread revision append: refuses deleted examples/
    jobs (M02-AUDIT-01), stores the envelope with its real parent and
    moves the latest pointer in the same transaction."""
    conn_assert_example_writable(conn, example_id)
    revision_id = revision_id or ids.new_id("rev")
    env = dict(env)
    env["revision_id"] = revision_id
    env["parent_revision_id"] = parent_revision_id
    payload = json.dumps(env, ensure_ascii=False, sort_keys=True)
    now = now or ids.now_utc_iso()
    conn.execute(
        "INSERT INTO training_revisions(revision_id, example_id,"
        " parent_revision_id, created_at_utc, envelope_json,"
        " content_sha256) VALUES(?,?,?,?,?,?)",
        (revision_id, example_id, parent_revision_id, now, payload,
         ids.sha256_text(payload)))
    conn.execute(
        "UPDATE training_examples SET latest_revision_id=?,"
        " updated_at_utc=? WHERE example_id=?",
        (revision_id, now, example_id))
    return revision_id


def conn_artifact_text(conn, artifact_id):
    """A text artifact's content inside a writer op, or None when absent
    or purged."""
    if not artifact_id:
        return None
    row = conn.execute(
        "SELECT content_text, purged FROM artifacts WHERE artifact_id=?",
        (artifact_id,)).fetchone()
    if row is None or row[1] or row[0] is None:
        return None
    return row[0]


def insert_text_artifact_row(conn, *, artifact_id, job_id, stage, role, text,
                             kind="text", retention_class="history",
                             meta=None, parent_artifact_id=None,
                             created_at_utc):
    conn_assert_job_writable(conn, job_id)  # M02-AUDIT-01 barrier
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
    # A lease names a retained payload: none on an artifact that never
    # committed (its async insert failed — M02-AUDIT-05), was purged, or
    # belongs to a deleted job (M02-AUDIT-01).
    art = conn.execute("SELECT job_id, purged FROM artifacts WHERE"
                       " artifact_id=?", (artifact_id,)).fetchone()
    if art is None:
        raise LookupError("lease refused: artifact not committed")
    if art[1]:
        raise JobDeletedError("lease refused: artifact already purged")
    conn_assert_job_writable(conn, art[0])
    conn.execute(
        "INSERT INTO artifact_leases(lease_id, artifact_id, holder,"
        " granted_at_utc, expires_at_utc) VALUES(?,?,?,?,?)",
        (lease_id or ids.new_id("lease"), artifact_id, holder,
         ids.now_utc_iso(granted_at_epoch),
         ids.now_utc_iso(granted_at_epoch + days * 86400)
         if days is not None else None))
