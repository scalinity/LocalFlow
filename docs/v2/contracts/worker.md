# Contract: Model worker process and supervision

**Spec:** S06, S09 · **Owner:** M03 · **Suites:** EV-04, EV-05

Model inference (ASR and cleanup) runs in a **fresh subprocess** — spawned
via `subprocess` (`python -m localflow.v2.worker --audio-root <dir>`),
never a fork of initialized Metal state. The parent process holds no MLX
state and alone owns capture, targets and insertion authority.

## Protocol (version 1)

Length-framed JSON on inherited pipes: each message is a 4-byte big-endian
length + UTF-8 JSON, and carries `v: 1`. Parent→worker ops: `load`,
`transcribe`, `clean`, `ensure_cleanup`, `shutdown`. Worker→parent ops:
`hello`, `engine`, `result`, `fault`, `diag`.

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
`failed`, and `unloaded` for the cleanup engine only (plus supervisor-level
`not_started`/`restarting`/degraded). ASR and cleanup are displayed
separately. A failed cleanup engine is degraded,
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

## Memory diagnostics (off by default)

With `LOCALFLOW_WORKER_MEMORY_DIAG=1` in the worker's environment (read once
at start) the worker writes `diag` frames of `kind: "memory"` carrying a
`label` and the MLX allocator's `active`, `cached` and `peak` byte counts,
and nothing else. The labels are `asr_loaded` (weights loaded, before the
silence warmup), `asr_warmed`, `cleanup_loaded` (weights loaded, before the
warmup generation), `cleanup_warmed`, `asr_result` and `cleanup_result`
(after the result frame is written). Sampling runs on the GPU thread and only
reads the counters. With the variable unset the frame stream is unchanged.

## Allocator release at load

Once an engine's load and warmup finish, and before that engine's `ready`
frame is written, the worker calls `mx.clear_cache()` on the GPU thread,
so the cached blocks one load leaves behind are not held while the next
engine loads. It runs once after the ASR warmup and once after each cleanup
warmup (a reload after an idle unload is another cleanup load), as the last
step of that engine's load: never while a request runs
and never between the chunks of one recording. A cleanup load that waits for
a request (a deferred load, or one queued behind requests that arrived first)
can run, release included, between two requests. The release writes no frame
and changes no engine state. It frees no live array, and a failing call is
ignored rather than failing the engine. It does not depend
on `LOCALFLOW_WORKER_MEMORY_DIAG`; the `asr_warmed` and `cleanup_warmed`
samples are read after it.

The release runs only after a successful load and warmup: after the ASR
engine's and after the v2 cleanup engine's. It does not run after a failed
load, and the v1 cleanup path (`cleanup_implementation` other than `v2`) never
releases, so the launch-peak reduction does not apply there.

## Idle unload of the cleanup model

A worker that has been idle for the **idle period** hands the cleanup model
back to the system; the next dictation loads it again. It exists only for
the cleanup engine when `cleanup_mode` is `llm` and `cleanup_implementation`
is `v2`. The speech engine never unloads, and neither does a `v1` cleanup or
a cleanup mode other than `llm`.

**State and frame.** `unloaded` is a cleanup engine state. The worker writes
one `{"op": "engine", "engine": "cleanup", "state": "unloaded", "model_id":
<cleanup model id>}` frame, after the model is released and the allocator
cache cleared. A reload then writes the load's own frames, `loading` and
`ready` (or `failed`, carrying the same reason code as any cleanup load
failure). A failed reload leaves the engine `failed`, which answers as
described under Engine lifecycle; the worker does not try again.

**Idle period.** `CLEANUP_IDLE_UNLOAD_S`, 600 seconds. The environment
variable `LOCALFLOW_WORKER_IDLE_UNLOAD_S`, read once at start like the memory
switch, replaces it with a positive number of seconds; unset keeps 600, and
any other value (zero, negative, not a number) turns unloading off. It is a
test and measurement seam, not a setting.

**When it unloads.** Only on the GPU thread's scheduling step, and only when
all of these hold at once, decided under the lock that also guards request
routing: the worker is not stopping, the cleanup engine is `ready` on the
`v2` `llm` path with an engine object present, no task is queued, no load is
pending, and the idle clock reads at least the idle period. The idle clock
restarts at every received `transcribe`, `clean` and `ensure_cleanup`, at the
end of every GPU task and at the end of a cleanup load. The state becomes
`unloaded` at that decision, before the model is released. The GPU thread
then drops the engine (and with it the model and its prefix cache), runs
`gc.collect()`, releases the allocator cache as at load, and writes the
frame. The unload adds no memory diagnostic label.

**`ensure_cleanup`.** A request that needs no field beyond `v` and `op`:
no `req_id`, no `generation`. It never produces a result frame and never a
fault, in any state. It restarts the idle clock; when the cleanup engine is
`unloaded` it queues one reload on the GPU thread, however many arrive
before that reload finishes. In every other state, and for a cleanup path
that cannot unload, it does nothing more. The parent sends it when a
dictation starts, so the reload overlaps the recording.

**Waiting rule for `clean`.** A `clean` that arrives while the cleanup
engine is `unloaded`, or while a reload is queued or running, waits for the
reload and gets the engine's real answer (`path: llm`), never
`cleanup_not_ready`. A `clean` that finds the engine `unloaded` queues the
reload itself, so the parent need not have sent `ensure_cleanup` first. If
the reload fails, the clean gets the failed-engine answer. This is the one
exception to the rule that a `clean` is answered at once while the engine is
not usable: the first load at worker start keeps that rule, so a `clean`
before the first `ready` is answered degraded as before.

**Order on the GPU thread.** Requests run in arrival order, one at a time.
A `transcribe` queued ahead of a `clean` runs before the reload; the reload
runs before a `clean` at the head of the queue. A `transcribe` that arrives
during a reload waits for it (one GPU owner). A `transcribe` while the
engine is `unloaded` is served at once and does not start a reload, and the
speech engine's state does not change.

**What never changes.** An unload or reload does not change the generation,
write a `fault` frame, restart the worker or count toward the circuit
breaker, and result frames echo their request's identity unchanged. A worker
that restarts, for any reason, starts as a fresh process that loads both
engines as at first start. With unloading off, or before the idle period has
passed, the frame stream is exactly the one without this section.

## M03 remediation (2026-09-25; protocol version unchanged)

- **Generation-owned requests.** A pending request records its immutable
  expected identity: generation, `job_id`, `attempt` and result kind
  (`transcribe→asr`, `clean→clean`). A frame
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
  existing degraded answers. The one exception is the reload after an
  idle unload (Idle unload of the cleanup model): that `clean` waits for
  the reload. A spawn made for a waiting request sends
  `defer_cleanup_until_request`, so that request runs before the long
  cleanup load. An ASR request arriving while a cleanup load is already
  running waits for that load (one GPU owner) — the parent reports it as
  `worker.request_queued_behind_load`; the request timeout still bounds
  it. Transforms are not worker requests (ADR-0002). When the ASR load
  fails, the cleanup load never starts: the worker reports cleanup `failed`
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
