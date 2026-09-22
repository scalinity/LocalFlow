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
