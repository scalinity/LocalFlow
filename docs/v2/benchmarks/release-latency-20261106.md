# Release latency qualification — 2026-11-06

The release path returns complete in-memory audio without joining the crash
journal writer. The writer still drains and finalizes asynchronously. Recovery
and deletion retain their existing ownership of the journal.

Cleanup keeps the same model, instructions, greedy sampling and validation.
It caches the complete static instruction prefix for both cleanup and
corrections. Each request receives a private copy. During cleanup, transcript
tokens supply short proposals that the model verifies in a batch. A rejected
proposal restores a private checkpoint and replays the accepted prefix; this
is required for recurrent caches. Three unhelpful rounds resume the ordinary
asynchronous decoder. Corrections and transforms use ordinary decoding.

The dedicated worker inference thread requests macOS user-initiated scheduling
before model loading. The request affects that thread and native threads that
inherit its scheduling; it changes no process-wide priority. A refused or
unavailable scheduling API leaves inference usable with inherited scheduling.

Insertion skips a redundant selection read when the destination's character
count is already unavailable. This preserves the existing unavailable pre-state
and can avoid an extra synchronous Accessibility call before posting text.
Native latency savings for this small change are unmeasured.

## Qualification

Model: `local/LocalFlow-Cleanup-M2-Qwen3.5-4B-4bit`, snapshot
`8bdf91843d892f6c88b681ba750b64eb0c012ef4`. Runtime: MLX 0.31.2,
MLX-LM 0.31.3, Python 3.14.10, macOS on Apple silicon.

| Check | Result |
| --- | --- |
| Cleanup suite | PASS: 319 passed, two opt-in model checks skipped |
| Full-engine original/candidate comparison | PASS: all 60 fidelity fixtures plus long, Unicode and list cases; complete token sequences and engine decisions identical |
| Prefix cache alone | PASS: original block cache and complete-prefix cache, lookup disabled, cold and warm, short cleanup, long cleanup and corrections; identical uncached token sequences |
| Updated coverage gates | PASS: 15 full-engine cases; accepted proposals, rejection/replay, full acceptance, ordinary-decoder fallback, cleanup cache hits and corrections cache hits all exercised |
| Output limits | PASS: real-model limits 1, 2 and 7; matching text, tokens and termination |
| Recurrent state and stream adapter | PASS: default suite includes actual tiny Qwen3.5 recurrent/attention caches, rollback, fallback, EOS, Unicode and length boundaries |
| Capture journal | PASS: eight cases, including blocked writer, complete audio and release followed by discard |
| Application lifecycle | PASS: 14 cases |
| Worker idle unload | PASS: 16 cases, including reload ordering and releasing the real engine/cache |
| Thread scheduling | PASS: three cases; native child-thread QoS, unchanged calling-thread QoS, denied request and unavailable API |
| Insertion races | PASS: 13 cases, including unreadable destinations, delayed consumption, selection changes, clipboard ownership and queued results |
| Native insertion cohort | NOT RUN: the launching terminal lacks Accessibility permission |
| Physical Fn release to visible text | NOT RUN |

Model-backed checks are opt-in:

```sh
LOCALFLOW_PREFIX_CACHE_PARITY=1 LOCALFLOW_PARITY_MODEL=/absolute/model/snapshot \
  .venv/bin/python -B -m unittest tests.v2.cleanup.test_prompt_cache_parity
LOCALFLOW_LOOKUP_PARITY=1 LOCALFLOW_LOOKUP_REPORT=/absolute/ignored/report.json \
  .venv/bin/python -B -m unittest tests.v2.cleanup.test_lookup_parity
```

Batch and singleton arithmetic can differ near numerical ties. These results
qualify the named model/runtime; the proposal algorithm alone does not prove
token identity for a different model or runtime.

## Timing

The baseline uses original block-aligned caching and ordinary decoding. The
candidate uses complete-prefix caching and transcript proposals. The worker
comparison also includes the thread scheduling change. Each mode owns separate
caches; comparison order alternates. No personal audio or dictation text is
used. Approximate p95 is sorted index `int((n - 1) * .95)`.

| Cohort | Baseline median / p95 | Candidate median / p95 |
| --- | --- | --- |
| 63 full-engine cases, changing ambient load | 1,792.6 / 5,758.6 ms | 1,645.6 / 4,423.6 ms |
| 15 final coverage cases, changing ambient load | 771.3 / 1,323.6 ms | 537.2 / 1,134.4 ms |
| Real worker: full ASR then cleanup, controlled CPU load, 12 samples per mode | 818.9 / 959.7 ms | 554.3 / 820.3 ms |

The real-worker cohort uses the existing synthetic 5.364-second speech clip
`clip-under-10s-00.wav`. Four fresh worker sessions run in baseline/candidate,
then candidate/baseline order; each session warms both stages, then processes
six full recordings while an owned 16-thread CPU load runs. All 24 samples
produce identical ASR text, cleaned text and cleanup path. The load remains
alive for every sample and is stopped/reaped by the probe. Median cleanup
request time falls from 685.0 to 415.6 ms. The largest total sample is
1,122.9 ms for baseline and 1,188.5 ms for candidate; the candidate does not
improve every observation.

Worker allocator samples retain about 16 MiB more active state with the
candidate (3,622.6 versus 3,606.6 MiB after requests). Cached allocator memory
also varies and is not a measurement of physical process footprint.

These timings end at the worker result. They omit recorder shutdown, parent
normalization/context work, insertion scheduling, keyboard delivery and the
destination application's response. They establish a useful reduction in
model work, not near-instant visible insertion under arbitrary system load.
Moving useful cleanup work into capture remains a separate incomplete step;
it needs final full-recording ASR, exact final cleanup-input matching and
cancellation that cannot delay final work behind a stale candidate.

## Review and project state

Two Claude Sonnet review phases found no critical issue. Findings F001–F013
were resolved through the cache, stream and qualification checks above. The
additional scheduling review was not admitted because NativePeers capacity
was full; its native behavior and failure paths were checked locally.

`ORCHESTRATION.html` already has unrelated uncommitted edits and is left with
its owner. This qualification changes no milestone completion or dependency;
the page would gain this latency follow-up and retain physical insertion as
unverified. Private raw reports, review packets and package/rollback copies
remain in the ignored `build/dictation-latency/` directory.
