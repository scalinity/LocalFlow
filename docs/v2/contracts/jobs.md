# Contract: Dictation jobs

**Spec:** S06 · **Shape owner:** M01 · **Live owner:** M02 · **Suites:** EV-01, EV-03

A job is one logical dictation attempt from hotkey-down to terminal state.

## Identity

- `job_id`: UUID, minted at capture start, stable across retries.
- `attempt`: 1-based; a retry of the same audio increments it and keeps the
  `job_id`.
- `session_id` / `boot_id`: process lifecycle identity (M02).
- `family_id`: groups retries, shared audio, near-duplicate scripted
  recordings and crops for split hygiene (see `dataset_exports.md`).

## Time

- `captured_at_utc`: RFC 3339 with milliseconds, or `null` with
  `time_quality` of `unknown` for imported legacy records. Never assign the
  import day as the usage day.
- `timezone` / `utc_offset_minutes`: observed values, never assumed.

## States

`capturing → queued → transcribing → normalizing → cleaning → validating →
ready_to_insert → insertion_posted → insertion_confirmed`

Terminal alternatives: `saved_not_inserted`, `cancelled`,
`failed_recoverable`, `failed_unrecoverable`. `insertion_unverified` marks a
posted-but-unobservable event. Auto-transform inserts `transforming` before
`ready_to_insert`.

## Invariants

1. Transitions are idempotent; a stale result carrying an old `attempt` or a
   cancelled `job_id` is discarded from insertion, never appended.
2. Every state change emits one event (see `events.md`) with the job ID.
3. Cancellation removes insertion authority immediately, even if a GPU call
   finishes later.
4. Historical imported pairs (M01 reconciliation) are records of the legacy
   pipeline, not job-conformant objects; their identity is
   `legacy:<source-sha>:<physical-line-range>`.
   (M01 remediation, additive:) pairs imported after the remediation store
   the exact payload (`payload_derivation: "e02-exact-payload-v2"` in their
   meta; earlier imports without the field used the stripped-lines view and
   stay immutable). A pair a later record has not closed (an end-of-file
   tail) is not imported until it is complete; a completion of a tail that
   a pre-remediation import stored truncated records
   `completes_prior_partial_identity` instead of replacing it.
