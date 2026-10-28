# ADR-0003: The cleanup model unloads after ten idle minutes

**Status:** accepted · **Trade-off against:** the worker-footprint work's
Residency gate (a dictation never waits on a reload). The owner accepted the
trade-off recorded here.

## Context

The worker keeps two models resident: the speech recognizer and the cleanup
model. The cleanup model's weights are 2,258 MiB, and an idle worker holds
them for as long as it runs. Unloading them after the 10-minute idle
period returns that memory to the system, and the next dictation then has to
load the model again.

The reload is the worker's own cleanup load path, warmup included, followed
by the allocator release it runs after every successful load. Measured in a
disposable in-process script on the cleanup model
`local/LocalFlow-Cleanup-M2-Qwen3.5-4B-4bit` (10 repetitions each, AC power,
no thermal warning):

- page-cache warm: 1.679 to 1.723 s, median 1.699 s;
- cold-ish (the weights' page-cache residency under 0.05%): 1.830 to
  1.935 s, median 1.854 s.

The Residency gate asked that the reload hide behind the dictation that
causes it: at least 99% of recorded dictations must last at least the worst
reload, and no dictation may wait more than 300 ms for cleanup because of
one. The reload starts when the hotkey is pressed, so it overlaps the
recording, and the cleanup request waits for it.

Against the recorded dictations (64 with a usable capture duration; capture
duration only, never text or audio) the gate fails on both clauses:

- 59 of 64 (92.2%) last at least the worst measured reload, 1.935 s, against
  the 99% required.
- The other 5 fall short; the largest shortfall is 1.585 s against 300 ms
  allowed, and 4 of the 5 exceed 300 ms.
- On the after-idle dictations alone, 2 of the 32 measurable ones are
  shorter than the reload, the largest shortfall 1.435 s.

Capture duration is the right budget for the reload wait. The reload and the
transcription share the worker's one GPU thread, so transcription cannot hide
a reload: a reload still running when the recording ends delays the
transcription by its remainder, and when the reload starts with the
recording the added wait is about the reload time minus the recording
length, never below zero. The measurements are kept in the
private evidence folder; this record carries aggregate numbers only.

## Decision

Build the unload anyway. A dictation that starts after an idle unload and
ends before the reload finishes waits for cleanup. When the reload starts with
the recording, the wait is about the reload time minus the recording length:
at most about the reload time for a very short dictation (about 1.9 s;
1.935 s measured worst). The press-time request is written from the app's
press handler and the worker starts the load when its GPU thread is free, so
a reload can start slightly after the recording does. In the recorded history
the largest shortfall is 1.585 s over all dictations and 1.435 s over the
after-idle dictations, the ones that can meet an unload. The owner accepts
that wait on short dictations in exchange for the memory.

Everything else stays as it was: the cleaned text, the worker's lifecycle,
generation numbers and the fault policy. The speech recognizer stays resident
and its own latency is unchanged; a transcription that reaches the worker
while a reload runs waits for it, because the worker has one GPU thread (see
Consequences).

The design is in `contracts/worker.md` (Idle unload of the cleanup model).
In short: after the idle period, with nothing queued or running, the worker
drops the cleanup engine, clears the allocator cache and reports the engine
`unloaded`; `ensure_cleanup`, sent at every hotkey press, and a `clean` that
finds the engine unloaded each queue exactly one reload; a `clean` that
arrives during the reload waits for it and gets the engine's real answer,
never the not-ready answer.

## Consequences

- **What waits.** Cleanup, for a dictation shorter than the reload that began
  after an idle unload; in the recorded history that was about 6% of
  after-idle dictations. A `transcribe` that reaches the worker while the
  reload runs also waits for it, because the worker has one GPU thread. The
  first load at worker start is unchanged: a `clean` before the first
  `ready` is answered at once with the unchanged text.
- **A very long recording.** The press-time request restarts the idle clock
  once. A recording longer than the idle period can therefore find the model
  unloaded when it ends, and its cleanup then waits for a full reload after
  the transcription. Recordings that long are rare (the longest in the
  recorded history is under four minutes) and the reload is small beside
  their transcription time, so no timer keeps the model loaded during a
  recording.
- **What never changes.** An unload or reload writes no fault, keeps the
  generation, never restarts the worker and does not count toward the
  breaker. A failed reload ends in the existing failed-engine behaviour:
  `failed`, and the degraded answer for the requests that follow. The
  speech recognizer never unloads.
- **Measured separately.** How much the idle footprint drops after an
  unload; the first dictation after an unload and a second one that starts
  during the reload, against the footprint work's latency rule; and the
  model-backed runs of the footprint rig. This change is covered at the
  protocol seam with shimmed loaders, which proves when the worker unloads
  and what it writes, not how much memory returns or how long a real reload
  takes.
- **The seam.** `LOCALFLOW_WORKER_IDLE_UNLOAD_S` sets the idle period in
  seconds, or turns unloading off. It exists for tests and measurement, not
  as a setting.

## Alternatives considered

- **A shorter idle period:** unloads follow shorter pauses, so more
  dictations start on a reload. Each extra unload adds waits for a memory
  gain that lasts only until the next dictation.
- **A longer idle period:** fewer waits, but the weights stay held for the
  extra minutes, and the recorded history was evaluated at ten.
- **Unloading the speech recognizer too (or instead):** its reload would
  delay the transcription of every dictation after an idle period, not only
  its cleanup, and transcription latency is the one number every dictation
  shows. It stays resident.
- **Answering at once with the unchanged text instead of holding the
  insertion for the reload:** this is what a not-ready cleanup engine does,
  and it would put an uncleaned transcript in the document for the first
  dictation after every idle period. A wait on a short dictation is the
  smaller cost.
