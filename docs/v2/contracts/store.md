# Contract: Persistent store

**Spec:** S08, S29.3–S29.4 · **Owner:** M02 · **Suites:** EV-03, EV-19

One SQLite database at `~/Library/Application Support/LocalFlow/v2.db`
(schema versions tracked in `schema_meta`; M02 ships v1 + v2-indexes,
`training_schema_version` 1) with artifact payloads under
`~/Library/Application Support/LocalFlow/v2-artifacts/` (0700/0600).
The legacy `stats.db` is an import source, never mutated; rows are copied
verbatim into `legacy_dictations` with original UTC instants, and a
`dictations` compatibility view exposes the original column names.

## Writer discipline

`localflow.v2.store.Store` is the single application writer: every read
and mutation is funneled through one FIFO writer thread; each op is one
transaction (commit on success, rollback on failure). Callers never touch
the connection. Pre-migration backups (SQLite backup API) go to
`v2-evidence/backups/`. A malformed core table blocks loudly instead of
being migrated over; missing tables at the recorded version are repaired
by idempotent DDL.

## Identities (frozen; producers add fields, never repurpose)

- Live jobs/artifacts: `job-`/`fam-`/`art-`/`ex-`/`rev-`/`consent-`/
  `lease-`/`tomb-` + uuid hex (Spec S06 example shapes).
- Legacy imports: `legacy:<source-sha>:<line-range>` with
  `time_quality: "unknown"`; stats rows keep their original `id` and
  Unix `ts` verbatim.
- Import bookkeeping: `imports(source_kind, source_sha256, locator)` is
  the idempotence key; `import_runs` records byte lengths so an appended
  log reconciles by verified byte prefix. Legacy log pairs, dictionary
  terms and transform definitions import through atomic
  artifact+bookkeeping ops (`import_legacy_pair`/`import_legacy_text`) —
  a crash can never leave one without the other.

## Retention and leases

`retention_class` ∈ {`history`, `training`, `legacy`, `recovery`}.
**`legacy` is never pruned** — only delete-everywhere removes imported
legacy content. `artifact_leases` (holder ∈ {`history`, `recovery`,
`training`}, expiry or pinned-null) gate `prune`/`prune_training`: expiry
of one interest never deletes content another live lease pins
(M02-AC06). The 30-day unreviewed training buffer evicts unpinned
examples; pinned ones survive. Purge marks the row first, then unlinks
the payload; leftover files become sweepable orphans (1 h in-flight
grace, quarantined not deleted).

## Deletion precedence

`delete_everywhere` revokes every lease, purges payloads and revision
rows, marks examples `deleted`, and leaves only content-free
`deletion_tombstones`. Ordinary revision immutability never justifies
retaining deleted payloads (S29.14).

## Events ↔ store

The event writer's unresolved-job callback is `Store.unresolved_job_ids`
— event retention keeps files mentioning unresolved jobs (S07). Envelope
`artifact_ids` must resolve to artifact rows or carry a
`missing_reasons` entry; `Store.verify()` enforces this and reports
orphan payload files.

## M03 additions (fields only; no frozen identity changed)

- `write_audio_artifact(dtype="pcm16")` writes a quantized derivative
  that **requires `parent_artifact_id`** and is marked `lossless: false`,
  `quantized_from_dtype: float32` (S29.5: quantization is never labeled
  lossless; kind `audio_wav_pcm16` vs `audio_wav_f32`).
- `bump_job_attempt(job_id)` increments a job's attempt for a retry that
  keeps the `job_id` (contracts/jobs.md).
- `update_job_state(..., retry=True)` allows exactly one terminal-state
  re-open — `failed_recoverable` → `queued` — for the deliberate recovery
  retry; every other transition out of a terminal state stays discarded
  (E12: exactly one logical terminal outcome per stale-result race).
- Recovery audio under the journal root (`v2-journal/job-<id>.wav`) is a
  parent-owned file, not a store artifact; it is not lease-governed and
  expires by mtime with the audio-failed retention knob (contracts/
  capture.md).

## M05 additions (schema v3; no frozen identity changed)

- Migration v3 adds the vocabulary tables (entries, aliases,
  append-only `vocabulary_history`, `vocabulary_meta` state counter,
  plus a case-insensitive one-canonical-per-scope unique index) —
  additive DDL only, safe on the live v2 database; see
  `contracts/vocabulary.md` for semantics.
- `Store.submit(fn, wait=True)` runs ``fn(connection)`` on the writer
  thread — the sanctioned entry point for same-package domain layers
  (`vocabulary_store`) so they honor the single-writer discipline while
  the connection itself stays private to this module. The torn-write
  repair path now covers the v3 vocabulary tables (all migration DDL
  re-applies idempotently).

## M09 additions (schema v5; no frozen identity changed)

- Migration v5 adds `job_targets(job_id PK, app_name, app_bundle,
  recorded_at_utc)` — the dictation's destination app, Spec S08's jobs
  "target" field, recorded once at PTT start via
  `Store.set_job_target` — plus `idx_jobs_captured` for History's
  date-grouped listing. A side table rather than an ALTER keeps every
  migration statement idempotent (the torn-write repair re-applies
  them all); see `contracts/hub.md`. The module-level
  `insert_text_artifact_row`/`grant_lease_row` are the canonical
  writer-thread INSERTs domain layers compose inside one op.

## M10 additions (schema v6; no frozen identity changed)

- Migration v6 adds the M10 configuration tables (see
  `contracts/profiles.md`): `style_rules` + `snippets` (versioned rows,
  a NOCASE unique trigger index) and `profiles_meta` (two monotonic
  state counters for snapshot invalidation — the M05 vocabulary-meta
  pattern). All M10 access goes through `StyleRuleStore` /
  `SnippetStore` over `Store.submit`; usage hits never bump the state
  counters. The torn-write repair path covers the v6 tables.

## M11 additions (schema v7; no frozen identity changed)

- Migration v7 adds the transform tables (see
  `contracts/transforms.md`): `transforms` (versioned rows) +
  `transform_revisions` (append-only preserved revisions — an old
  definition is never erased) + `transform_meta` (the state-counter
  pattern) + `transform_candidates`/`preference_observations` (S29.10;
  rows content-free, texts in lease-governed artifacts written inside
  the same op; the same-task invariant enforced at write time). All
  access through `TransformStore` over `Store.submit`; the torn-write
  repair path covers the v7 tables.

## M13 additions (schema v9; no frozen identity changed)

- Migration v9 adds the usage analytics tables (see
  `contracts/analytics.md`): `usage_facts` (one dictation row per
  logical job under a partial unique index — a retry reaching a
  terminal outcome REPLACES it; separate `transform`/`repaste`
  activity rows) + `daily_aggregates` (versioned, always recomputed
  from the facts inside the same writer op as the fact write) + day/
  activity indexes. The torn-write repair path covers the v9 tables.
  The `retention_days` map gains the independent `usage` knob.
- `prune_metadata` enforces the M02 `metadata` knob (deferred to M13
  by hub.md): terminal job rows delete once every content retention
  has expired past the window and no live training example pins them —
  `job_targets`/`insertions`/`insertion_observations` go with the row;
  usage facts never do (M13-AC03).

## M12 additions (schema v8; no frozen identity changed)

- Migration v8 adds the Scratchpad tables (see
  `contracts/scratchpad.md`): `notes` (mutable header: derived title,
  pin, current revision pointer, the unsaved-tail-risk marker) +
  `note_revisions` (append-only parent-linked; origin/trigger,
  dictation/transform attribution, word-origin spans) +
  `note_attachments` (managed image payloads under `v2-notes/`) +
  `note_evidence_links` (note↔training-example references with closure
  state — note deletion closes them). All access through `NoteStore`
  over `Store.submit`; the torn-write repair path covers the v8
  tables. Post-close submits now fail fast (`store is closed`)
  instead of hanging on the dead writer.

## M14 additions (schema v10; no frozen identity changed)

- Migration v10 adds the curation and personalization tables (see
  `contracts/learning.md`, `contracts/profile.md`,
  `contracts/dataset_exports.md`): `learning_candidates` (with the
  `vocabulary_action` an approval took) + `correction_labels`
  (append-only per-example revisions, graft artifact ids) +
  `sampling_decisions` + `split_assignments`/`training_memberships`
  (versioned, exposure-tracked) + `example_tags` + `profile_snapshots`/
  `profile_evidence` + `export_manifests`, with their indexes. Rows are
  ids/hashes/counts/offsets (a candidate row also names its proposed
  rule terms); observed words and graft payloads live only in
  lease-governed artifacts written inside the same writer op. New id
  prefixes: `cand-`, `lbl-`, `smp-`, `prof-`, `export-`. The torn-write
  repair path covers the v10 tables.
- `delete_everywhere` propagates in the same op: the JOB's open
  learning candidates go `stale` with rule terms and spans cleared
  (candidates are job-keyed — a teach with collection off has no
  example; payloads are job artifacts and are purged with them), the
  example's correction labels are deleted, and every profile snapshot
  that drew on it is invalidated with its measured JSON and cards
  cleared; its evidence links go. `prune_training` expiry propagates
  to candidates and labels the same way. A mined candidate's payload
  lease follows the unreviewed buffer, so it never pins a job; a
  taught candidate's (reviewed) payload is retained until removed.
- M14 services use `Store.submit` with connection-level helpers inside
  ops (`review.verified_asr_eligible_in`, the split version read, the
  exporter's inline consent read) — a nested `Store` call inside an op
  would deadlock the writer. A refusal found inside an op returns as
  data and is raised after the op (an in-op raise surfaces wrapped as
  `RuntimeError`).

## M02 remediation (schema v11; no frozen identity changed)

Owner M02; findings M02-AUDIT-01…20 (`docs/v2/acceptance/M02/remediation/`).

- **Deletion barrier.** Migration v11 adds `job_deletions(job_id PK,
  reason, deleted_at_utc)` — content-free. `delete_everywhere` records
  the job in the same op; every evidence write (`insert_text_artifact_row`,
  `write_audio_artifact`, `grant_lease_row`, `upsert_example`,
  `publish_example`, `append_revision`, `update_latest_revision`,
  `conn_append_revision`) raises `JobDeletedError` inside its op, so a
  late producer can never recreate deleted content. A `deleted` example
  state is final (`set_example_state` never leaves it). Deletion/tombstone
  reasons are codes (`[a-z0-9_]{1,64}`), never caller free text.
- **Durable purge intents.** `purge_intents` (v11) records every payload
  file a committed purge must remove. `_purge_artifact` never unlinks:
  the row change + intent commit together, the writer unlinks only
  after that commit, and an intent stays pending (attempts + errno code)
  until the file is gone — retried by `reconcile_purges()`, by
  `sweep_orphans()` and at every `Store` open. A rollback therefore
  leaves a live row with intact bytes; a crash after commit is finished
  at the next open. The sweep never moves pending deletion work into
  `orphans/`; an intent also removes the same managed name from
  `orphans/` (files a pre-remediation sweep parked there).
- **Job-scoped payload copies.** `register_job_payload_dir(dir,
  pattern)` declares copies the store does not index; the app registers
  the transcript-logging debug directory (`dictation-<stamp>-<seq>-<job
  id>.wav`, `localflow/v2/debug_audio.py`) and the recovery journal
  (`job-<job id>.*`). Ownership is by name pattern only — legacy
  timestamp-only debug files have no known owner and are left to their
  unchanged rotation.
- **Honest deletion result.** `delete_everywhere` returns
  `{purged_artifacts, payload_files, pending_purges, complete}` and emits
  `training.deleted_everywhere` with outcome `complete`/`purge_pending`
  AFTER the commit and the unlink attempt.
- **Atomic publication.** `publish_example` is one op: deletion barrier,
  a check that every artifact the envelope references (top-level and
  nested) committed for this job, the example row in its FINAL initial
  state (`quarantined_sensitive` when the scanner flagged it), revision 1
  and the latest pointer. Uncommitted references are nulled with
  `not_captured_at_stage` and listed in the envelope's content-free
  `completeness` block. `update_latest_revision(example_id, mutate)`
  reads the current latest, mutates and appends with the real parent in
  one op (no stale snapshot can drop an intervening annotation).
- **Acknowledgment and timeouts.** `sync()` is an execution barrier, not
  proof that earlier fire-and-forget ops succeeded; completeness comes
  from `publish_example`. A waited call's `TimeoutError` does NOT cancel
  the op — it may still commit; callers pre-allocate ids to find it.
- **Leases.** `grant_lease_row` refuses an artifact that never
  committed, was purged, or belongs to a deleted job. `prune_training`
  expires only the TRAINING interest (training leases with an expiry);
  a history/recovery lease or a pin keeps the payload until the shared
  live-lease predicate says no interest remains; non-training-class
  artifacts stay with `prune`. `prune` keeps the job artifacts of
  examples in `REVIEWED_RETAINED_STATES` (`annotated`) — reviewed
  evidence is retained until removed (S29.14); exclusion, expiry and
  deletion release it.
- **Attempt fence.** `update_job_state(..., expected_attempt=N)` discards
  a transition from a writer still on another attempt (unfenced calls
  are unchanged). It is an API for callers that hold an authoritative
  attempt; the app does NOT pass it on its worker transitions: the
  app's attempt is synchronized with the store only by an unacknowledged
  bump, a mismatch would strand the job unresolved, and the single FIFO
  coordinator plus the M03 supervisor's stale-message rejection leave no
  confirmed stale writer to fence.
- **Consumers across the barrier.** Note mining skips a deleted job
  (one deleted job never fails the whole pass); a transform of text
  whose originating job was deleted records its candidate with artifacts
  detached from that job (`job_id` NULL); `TrainingDataService.exclude`
  leaves a `deleted` example deleted; `Store.job_deleted(job_id)` lets
  producers of copies outside the store (the debug WAV) check the
  barrier first. v11 backfills `job_deletions` for pre-v11 deletions
  (examples in state `deleted`, jobs whose artifacts carry deletion
  tombstones), idempotently — the repair path rebuilds a lost barrier
  table the same way; a lost `purge_intents` table is repaired empty.
- **Verification.** `verify()` checks every referenced artifact (nested
  included) exists and belongs to the envelope's job, revision
  parent/pointer consistency, pending purges, and accepts valid
  delete-everywhere tombstones. `verify(deep=True)` also re-reads every
  live payload (existence, size, sha256). `artifact_payload(...,
  verify=True)` refuses a hash mismatch. Downstream exporter checks stay
  independent and stronger for their own purpose.
- **Lifecycle.** `lifecycle` ∈ open/closing/closed; admission closes at
  the start of `close()`, accepted ops drain, and `close()` returns
  `{drained, pending_ops, writer_alive}` — a stalled writer is reported,
  never closed underneath. The app drains the store then the event
  writer on quit.
- **Schema repair.** A newer schema version is refused untouched. At the
  current version, a missing table whose dependents survive (see
  `_CORE_DEPENDENTS`) is corruption: a `v2-pre-repair-*.db` backup is
  taken and the open is refused; additive tables without dependents and
  missing indexes are re-created (idempotent DDL, `store.schema_repaired`).
  `job_deletions`/`purge_intents` are additive (rebuilt, never refused).
- **Imports.** `start_import_run`/`finish_import_run` record a log run's
  byte snapshot BEFORE its first pair commits (`note` `status=started`
  until completed), so an interrupted run still reconciles as a verified
  prefix. `import_legacy_stats_row` couples a stats row and its
  bookkeeping in one op; a reused legacy id with identical content is the
  same entity, with different content a `legacy_stats_row_conflict`
  artifact preserves it losslessly and the import reports it.
- **Retention knobs.** `localflow.config.retention_policy` validates the
  day knobs (integral, 1…36500); an invalid value falls back to its
  default and is reported (`config.retention_invalid`), never a crash or
  a zero/negative window.

## M03 remediation (schema unchanged, v11)

- **Deletion arbitration for payloads outside the store.**
  `run_unless_deleted(job_id, fn)` runs a short `fn` on the writer thread
  only if the job is not barred; `publish_job_file(job_id, staged, final)`
  atomically renames a staged file into place the same way and returns
  `published`/`deleted`/`failed` (a staged file that was not published is
  removed). Because delete-everywhere enumerates and purges a job's
  registered payload files in its own writer op, an M03 file (worker WAV,
  recovery WAV, capture-provenance sidecar, journal creation, debug copy)
  either exists before that enumeration and is purged with the job, or is
  never created. Staging names keep the final name as their prefix
  (`<name>.part-<pid>-<rand>`), so the job's glob owns them.
- **Deletion listeners.** `add_job_deletion_listener(fn)` runs `fn(job_id)`
  inside the delete op (writer thread) before the barrier commits; the app
  uses it only to revoke in-memory authority (queued work, cached
  delivery, recovery items, automatic retries) — flags, no store calls.
- **WAV helpers.** `_write_wav` stages and renames (no final-path prefix
  after an interruption). `read_wav_f32`/`read_wav` are strict: a
  truncated payload raises `WavIncompleteError` (declared/available
  sample counts), bytes beyond the declared payload raise
  `WavFormatError`; both subclass `ValueError`.
  `read_wav_f32_prefix` returns the complete-sample prefix with honest
  counts, for recovery classification only.
- **Attempts.** `bump_job_attempt(job_id, at_least=N, wait=True)` raises
  the attempt to an execution known to have run (never lowers it) and can
  return the committed value; the recovery retry uses the committed row
  as the attempt authority. The `expected_attempt` fence stays unwired
  app-wide (no stale writer was established; M03-AUDIT-03/05 were repaired
  at their concrete mechanisms).
