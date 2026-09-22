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
