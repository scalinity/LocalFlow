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
