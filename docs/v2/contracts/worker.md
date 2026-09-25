# Contract: Model worker process and supervision

**Spec:** S06, S09 · **Owner:** M03 · **Suites:** EV-04, EV-05

Model inference (ASR and cleanup) runs in a **fresh subprocess** — spawned
via `subprocess` (`python -m localflow.v2.worker --audio-root <dir>`),
never a fork of initialized Metal state. The parent process holds no MLX
state and alone owns capture, targets and insertion authority.

## Protocol (version 1)

Length-framed JSON on inherited pipes: each message is a 4-byte big-endian
length + UTF-8 JSON, and carries `v: 1`. Parent→worker ops: `load`,
`transcribe`, `clean`, `shutdown`. Worker→parent ops: `hello`, `engine`,
`result`, `fault`, `diag`.

**There is no insertion op.** The worker cannot request an insertion; the
supervisor ignores any unknown worker→parent message
(`reason_code: unknown_op`). Only the parent's coordinator ever calls the
insertion path.

**Audio is referenced, not shipped:** `transcribe` names a parent-created
file under the root fixed at spawn. The worker accepts only single-segment
names matching `^[A-Za-z0-9._-]+$`, resolves them against that root and
refuses anything that escapes it.

## Identity and staleness (M03-AC02)

- `generation` increments on every worker (re)spawn; each request is
  stamped with the current generation and the job's `attempt`.
- A result resolves its pending request only when its `req_id` is live and
  its generation matches the stamp. Late/unknown results are discarded with
  a `worker.stale_result_discarded` event; a stale-generation echo resolves
  as a fault.
- A retry of the same audio increments `attempt` and keeps the `job_id`
  (contracts/jobs.md). The supervisor's automatic retry does exactly one
  such increment; the store mirrors it via `bump_job_attempt`.

## Fault policy (M03-AC01)

A faulted stage (structured fault, pipe death, timeout) kills the damaged
worker, spawns a fresh one, waits for the needed engine and retries the
stage **once** with `attempt + 1`. A second fault raises `WorkerFailure`;
the caller records `failed_recoverable` with the audio preserved and
offers retry/raw-export actions — no loop. A circuit breaker trips after 3
consecutive worker deaths with zero successful stages: further automatic
work fails fast (`supervisor_breaker_tripped`) until a **manual**
`restart()` re-arms it. An engine that fails to load (e.g. cache miss —
the worker always runs with `HF_HUB_OFFLINE=1`, so nothing downloads
mid-dictation) fails requests without respawning.

## Engine lifecycle (S09)

Per-engine states reported by the worker: `loading`, `warming`, `ready`,
`failed` (plus supervisor-level `not_started`/`restarting`/degraded). ASR
and cleanup are displayed separately. A failed cleanup engine is degraded,
not dead: the worker answers in basic mode and labels it
(`path: "basic"`, `fallback_reason: cleanup_engine_failed`); the parent's
`cleanup_not_ready_policy` (`basic`|`wait`) decides whether a job runs the
fallback now or holds until the engine resolves. The recorded path is
always the path that produced the text (M03-AC04).

## Serialization and timing

One model request is in flight at a time (`_gpu_lock`); queued dictations
wait in the parent's FIFO. Workers report their own monotonic stage
durations as elapsed-ms; absolute monotonic values are never compared
across processes (S07). Worker stderr is drained into a bounded tail used
only for fault diagnostics; event `detail` carries a size-capped, sanitized
excerpt — transcripts never appear there.

## M03 remediation (2026-09-25; protocol version unchanged)

- **Generation-owned requests.** A pending request records its immutable
  expected identity: generation, `job_id`, `attempt` and result kind
  (`transcribe→asr`, `clean→clean`, `transform→transform`). A frame
  resolves it only when it comes from, and echoes, that generation and
  matches the rest; a live `req_id` with the wrong job/attempt/kind is a
  worker protocol violation and resolves as a fatal fault
  (`result_identity_mismatch`). A reader — including its `finally` —
  resolves only the requests of its own process; a request registered for
  a generation whose reader already finished resolves at once. Framing
  failures (bad length, EOF mid-frame → `truncated_frame`) end only their
  own generation; an unparsable body with a trustworthy length is skipped;
  non-object frames are ignored.
- **One lifecycle authority.** Spawn, the automatic retry's kill+respawn,
  manual restart, generation retirement and shutdown hold one re-entrant
  lifecycle lock (order: lifecycle → state; never the reverse). A request
  is registered and written under it, so it is stamped with — and sent
  to — one process. `shutdown()` closes admission permanently first:
  waiting requests resolve as `supervisor_closed` (non-fatal), a spawn
  waiting for `hello` is woken and kills its own child, and every later
  request, `ensure_running` or `restart` raises `supervisor_closed`. A
  spawn clears its `hello`/engine events under the same state lock as its
  closed-check, so shutdown's wake-up can never be erased (review R6); an
  `engine` frame from a generation other than the current one is ignored.
- **Fault classes.** Worker faults carry `fault_class`: `input`, `engine`,
  `protocol` (and parent-side `closed`, `revoked`) are refusals — no kill,
  no retry, no death counted; anything else (`runtime`, or a frame without
  a class) is fatal and gets the one automatic retry. Reason codes are
  controlled tokens (`[a-z0-9_.:-]`); exception text never crosses the
  pipe (`error_type` is the class name only). The parent re-validates
  every code it forwards.
- **Executed identity.** `WorkerFailure.attempt/generation` name the last
  execution actually admitted to a worker (None when nothing was sent);
  `retried` says an automatic retry was admitted; `fatal` says a
  generation was retired. A retry that never reached a worker leaves the
  first attempt as the executed one.
- **Retirement.** A second fatal failure retires its generation even
  below the breaker threshold. A result with `retire_generation` (an
  exception escaping the cleanup engine, answered with the unchanged
  normalized input — or, on V1, a generation exception answered with the
  basic pass) is returned to the caller with `retired_generation: true`,
  counted as a death (never a healthy success), and the process is killed;
  the next request spawns fresh. A semantic rejection inside the engine
  is not a runtime failure.
- **Revocation.** `revoke_job(job_id)` (user cancel, delete-everywhere)
  forbids the automatic retry for that job; the damaged generation is
  still retired.
- **Retry honesty (review R10).** `worker.restarting` (`retry_once`) is
  emitted only when the retry actually proceeds. A fatal failure whose
  retry is refused — `request_revoked`, `supervisor_closed`,
  `supervisor_breaker_tripped` — emits `worker.retry_skipped` with that
  reason and raises `WorkerFailure(<reason>, fatal=True)` carrying the
  first (executed) attempt; `retried` stays false.
- **Scheduling.** The worker has a control thread (always reading) and one
  GPU thread (loads and model requests, strictly one at a time). A
  `clean` while the cleanup model is not usable is answered NOW on the
  control thread — V2: the unchanged normalized input,
  `path: llm_fallback_normalized`, `fallback_reason: cleanup_not_ready`;
  V1: the basic pass, `path: basic` — and a failed engine keeps its
  existing degraded answers. A spawn made for a waiting request sends
  `defer_cleanup_until_request`, so that request runs before the long
  cleanup load. An ASR request arriving while a cleanup load is already
  running waits for that load (one GPU owner) — the parent reports it as
  `worker.request_queued_behind_load`; the request timeout still bounds
  it. A transform waits for the cleanup load; a failed load refuses it
  (`cleanup_engine_not_ready`, non-fatal). When the ASR load fails, the
  cleanup load never starts: the worker reports cleanup `failed`
  (`cleanup_not_loaded_asr_failed`; V2 marks its load failed, V1 keeps a
  basic-only cleaner) — or `ready` with `not_llm_mode` when no model was
  configured — so a later `clean` gets the engine's normal degraded
  answer, never an exception (review R7).
- **Input boundary.** The worker opens the named file under its root with
  `O_NOFOLLOW|O_NONBLOCK`, requires a regular file and reads that one
  descriptor (symlinks, FIFOs and directories are refused without
  blocking); the WAV is parsed strictly (a truncated payload is
  `audio_incomplete`, never a shorter "complete" input); a declared rate
  that differs from the file's, or a file rate the loaded model does not
  take, is refused (`audio_rate_mismatch` / `audio_unsupported_rate`) —
  never relabeled or resampled implicitly.
- **Framing.** Both directions cap frames at 64 MiB; the worker writes
  whole frames (write-all under a lock shared by its two threads) and
  refuses an oversized response before writing a byte; a malformed or
  wrong-version request is refused as a `protocol` fault and the next
  request is still served.
- **Diagnostics.** Each generation has its own byte-bounded (16 KiB)
  stderr tail, drained in chunks (a newline-free stream cannot grow it);
  an old generation's drainer never writes into a newer tail; the digest
  (`stderr_lines`, `bytes~`, `traceback`) never raises and never changes a
  request's disposition.
- **Retry budget (design).** One automatic retry per stage request (ASR
  and cleanup each), not per dictation: a dictation whose ASR and cleanup
  both fault once executes attempts 1, 2, 2, 3 — still one logical job,
  one usage fact.
