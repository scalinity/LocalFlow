# Contract: Dated events

**Spec:** S07 · **Shape owner:** M01 · **Live owner:** M02 · **Suites:** EV-02, EV-19

Operational log records are JSON Lines with escaped newlines; a transcript
can never break a record or impersonate an event prefix.

## Envelope (schema_version 2)

Required field families: `schema_version`, `event_id` (globally unique,
deduplicable), `timestamp_utc` (RFC 3339 ms), `timezone`,
`utc_offset_minutes`, `boot_id`/`session_id`/`process_id`/
`worker_generation`, `sequence` (monotonic, parent-assigned), `job_id`/
`attempt`/`stage` where applicable, `event`/`level`/`outcome`/
`reason_code` (stable names; machine-readable), `duration_ms`/
`queue_wait_ms` (monotonic, in-process), and reproducibility fields
`source_revision`, `pipeline_revision`, `model_id`, `model_revision`,
`config_hash`, `prompt_hash`, `artifact_ids`.

## Invariants

1. Dates belong to the event, not the filename. Legacy import keeps missing
   event times unknown (`time_quality: "unknown"`).
2. Operational events carry metadata, sizes, timings, sanitized reason codes
   — never raw/cleaned text, audio, credentials, environment variables or
   model hidden reasoning. Content lives in private artifacts.
3. Wall-clock corrections, DST and timezone travel must not produce negative
   durations; never compare absolute monotonic values across processes.
4. Training-related operational events (collection enabled/paused/excluded,
   evidence revision saved, annotation recorded, export started/completed,
   comparator approved/failed) are content-free: IDs and reason codes only.
5. The legacy undated log (`~/Library/Logs/LocalFlow.log`) is an import
   source with physical-line provenance, parsed by
   `scripts/v2/parse_legacy_log.py` under the E02 protocol.

## M02 remediation (export, ordering, retention, shutdown)

- **Redacted export is a versioned typed allowlist**
  (`scripts/v2/view_events.py::REDACTION_ALLOWLIST`, `redaction_version`
  1): only listed envelope fields survive, each only when its value
  passes that field's type/shape check (minted-id shapes, code tokens,
  numbers, UTC instants); `detail`, unknown/future fields, nested
  values, wrong types and secret-scanner hits are omitted and counted in
  `omitted_fields`. A new field is exported only after it is added to
  the allowlist with its check.
- **View order.** A stream is one writer instance (boot_id, session_id,
  process_id). Within a stream the writer `sequence` is authoritative;
  across streams, records merge by UTC instant; file names (active,
  `.2`, `.10`, pid-prefixed) never decide order. A wall-clock rollback
  inside a stream is shown in sequence order and reported as ambiguous
  for cross-stream placement. `--last N` is the last N of that order.
- **Every removal path is protection-aware.** The size-roll cap
  (`KEEP_ROLLS`) applies the same unresolved-job predicate as age/size
  retention; a protected roll is kept past the cap
  (`stats()["protected_rolls_kept"]`) until its jobs resolve. When the
  unresolved set cannot be read, nothing is removed.
- **Shutdown.** `close()` closes admission first (a later `emit` returns
  False and counts `dropped_after_close`), drains accepted events and
  returns `{drained, pending}`. The store is the durable authority for
  job state; an event is a diagnostic record of it, not a transactional
  replica.
