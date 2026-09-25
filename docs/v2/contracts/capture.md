# Contract: Durable capture journal

**Spec:** S06, S09 · **Owner:** M03 · **Suites:** EV-04, EV-19 (producer)

Each dictation journals its audio blocks off the real-time callback so a
crash mid-recording loses only the torn tail (M03-AC03).

## Discipline

- The audio callback **only enqueues** (bounded, non-blocking; queue bound
  256 blocks ≈ 12.8 s of headroom). One writer thread owns all disk work;
  the journal file is created lazily by that thread, so the hotkey/UI path
  does no disk work (S24).
- Under writer stalls or disk-full, blocks drop from the *journal only* —
  counted (`queue_dropped`), reported (`capture.journal_degraded`), and
  the recorder's in-memory buffer still feeds the live dictation. A full
  disk never discards an active recording's live path.
- `capture_journal: false` (config) selects memory-only capture; crash
  recovery is then honestly disabled for those dictations, not secretly
  persisted.

## File format (journal_version 1)

`<root>/job-<job_id>.blk` (root 0700, file 0600):

- line 1: header JSON (job/family identity, sample rate, channels, dtype)
- records: `b"BLK"` + `<u32 seq> <u32 frames> <u32 byte_len>` + float32
  payload
- clean close: a finalize JSON line (`blocks`, `samples`, `sha256`)

`<root>/job-<job_id>.wav` is the parent-created float32 WAV handed to the
worker (Spec S06 audio-by-reference) and kept for retry.

## Recovery

At startup, every `.blk` is reconstructed: complete records become samples
verbatim (bit-exact float32), the first record failing its magic/length
checks ends recovery and is reported as the **incomplete tail**
(`torn_bytes`, never guessed past). The reconstruction is written to the
job's `.wav`, the job is marked `failed_recoverable`
(`app_crash_during_capture`), the item enters the Recovery menu, and the
`.blk` is removed. Unresolved jobs that already hold a `.wav` (crash after
release) are re-opened the same way. Journal files for resolved jobs are
deleted eagerly; unresolved ones expire with the audio-failed retention
knob by mtime.

Sleep/lock mid-recording abandons capture into the same recoverable state;
wake never reopens the microphone (M03-AC04). A dead stream or vanished
input device instead *finishes* the dictation with the speech captured so
far, recording the discontinuity (`capture.device_discontinuity`) that the
evidence envelope surfaces under `audio_preparation.discontinuities`
(M03-AC05).

## M03 remediation (2026-09-25; journal_version 2)

- **Format v2** (v1 still read). Header adds `boot_id`. Each record is
  `b"BLK"` + `<u32 seq> <u32 frames> <u32 record_bytes>` +
  `<u64 start_sample> <u32 crc32(payload)>` + payload, with
  `record_bytes = 12 + 4·frames` (so the record stays self-delimiting by
  the same length field). `seq` numbers persisted records 1, 2, 3 … with
  no holes; `start_sample` is the block's position in the capture
  timeline, which counts every OFFERED block — a queue drop becomes a
  positioned gap. The finalize line adds `offered_samples`,
  `dropped_blocks`, `dropped_samples`.
- **Reconstruction statuses.** `finalized_verified` (footer blocks,
  samples and SHA-256 all match), `unfinalized` (clean EOF at a record
  boundary: whether capture continued is UNKNOWN, never assumed),
  `torn_tail` (EOF inside a record), `torn_footer` (EOF inside the
  finalize line — a lone `{` included), `corrupt` (`sequence_break`,
  `crc_mismatch`, `record_invalid`, `position_overlap`,
  `footer_mismatch`, `footer_unparsable`, `bytes_after_footer`,
  `header_invalid`), `no_header`. Recovery keeps only the verified prefix
  and never resynchronizes past a bad record. v2 reports each gap as
  `{at_sample, missing_samples, recovered_offset}` (interior and, from the
  footer, trailing); v1 positions are unknown and an unfinalized v1
  journal's integrity is `unverified`.
- **Ownership.** The writer holds an exclusive `flock` on its file while it
  may append (`capture_journal.is_live`). The app holds `.owner.lock` on
  the journal root for its lifetime; a process that cannot take it claims
  nothing at startup (`capture.recovery_skipped`
  `journal_root_owned_elsewhere`). The scan also skips live writers, jobs
  this process holds, rows of the current boot, deleted jobs (their
  residue is removed) and resolved jobs (consumed residue removed; a
  resolved job is never re-offered).
- **Creation authority.** File creation goes through the store's deletion
  arbitration (`Store.run_unless_deleted`); a discard (`close_discard`)
  revokes creation, and a writer that was already creating the file
  removes it itself — a cancelled or deleted journal cannot reappear.
- **Source selection.** A complete worker WAV (the full in-memory capture
  written at release) is kept untouched when it is at least as long as
  the journal reconstruction; otherwise the reconstruction is published
  atomically; a truncated WAV longer than any journal is republished as
  its complete-sample prefix and labeled truncated. Nothing replaces
  better audio.
- **Capture provenance.** `job-<id>.capture.json` (version 1,
  content-free) travels with the recovery audio: original
  `captured_at_utc`/`time_quality`/zone, actual `sample_rate` and
  `sample_count`, `source` (`live_memory`, `journal_reconstruction`,
  `worker_wav`, `worker_wav_prefix`), `complete` (true/false/null =
  unknown), journal status/gaps, WAV declared/available counts, device
  and teardown diagnostics, `capture_journal` enabled/disabled, and
  `recovered_at_utc` (a separate event, never the capture time). A
  recovery retry takes capture time from the job row (durable truth),
  then the sidecar; an absent instant stays absent (`time_quality:
  unknown`); the rate is the retained bytes' own.
- **Live vs recovered.** A live capture's evidence is the complete
  in-memory buffer: journal drops/degradation are recorded as
  `crash_journal` diagnostics, not audio discontinuities. Recovered audio
  reports its real ones (`incomplete_tail`, positioned `journal_gap`,
  `timeline_unverified` for v1, `capture_end_unknown`, `truncated_wav`).
- **Worker WAV.** Written to a `.part-` staging name in the journal root
  and published by atomic rename under the deletion barrier; the reader
  is strict (a truncated or over-long payload raises). Staged leftovers
  expire after an hour.
- **Stream teardown.** `Recorder.start` owns a stream only once it has
  started (a failed start closes it and leaves no stale reference);
  `Recorder.stop` survives stop/close exceptions, always returns the
  buffered speech, finalizes the journal and records
  `stream_teardown_error` (class name only).
- **Memory-only setting (design).** `capture_journal: false` disables the
  incremental journal only. Inference still hands the worker a WAV, and a
  failed or crashed job's WAV stays retryable (its provenance says
  `capture_journal: disabled`); the setting is not a "never store" mode.
- **Durability (design).** Blocks are handed to the OS with `os.write`:
  process-crash persistence, not a per-block power-loss guarantee (no
  fsync per block); completeness of captured speech, file integrity and
  physical durability are reported separately.
