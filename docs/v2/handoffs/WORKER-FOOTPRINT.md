# Worker footprint reduction

October 28, 2026. State: `WORKER_FOOTPRINT_COMPLETE_PENDING_LOCAL_VERIFICATION`
(M03-V009 and M03-V010 are not run). The work is merged into `main`
(fast-forward on October 28; `main` and `origin/main` at
`7304b0edf49a86c29e1067048e3d5aed12cf919a`) and installed: `/Applications/LocalFlow.app`
was rebuilt from a clean worktree of `main` at that commit at 2:06 AM EDT on
October 28 (its `BUILD.json` reads `source_revision` `7304b0e…`, `dirty`
false). The working branches `perf/worker-footprint` and `perf/05-idle-unload`
are merged and deleted.

**Goal:** lower the dictation worker's memory with the same two models and the
same output text. Speed is unchanged except for a dictation that starts right
after an idle unload of the cleanup model, the trade accepted in ADR-0003.
**Result:** two levers ship. The allocator release lowers the launch peak by
717 to 819 MiB; its idle gain at launch does not last, because the first
dictation refills it. The idle unload returns the cleanup model's memory after
ten idle minutes (the worker's footprint drops by a median of 2,653 MiB) at
the price of a wait on short dictations that start right after an unload. The
steady-state cache and the loader closed without code.
**Base commit:** `14a009a4f3d7d64a6419c12638af65bc6ed9b2a8` (`main`).
**Last code commit:** `7d523d88bd41ebf39adc58225066012574b82464`;
`localflow/` tree SHA-256
`6f1762f7e6878f84c2e455fd4c459108e6c316f2f119918fa4de2ec44d1af768`. The
commits after it on `main`, up to `7304b0e`, change only the records, so
`localflow/` at `7304b0e` is byte-identical.
**Measured heads.** The launch-peak and latency numbers were measured on
`4eff5a3e98e3c396e06212f8aa2429c39ce3da67` (`localflow/` tree
`400fa463b31eeaca24b5c1ea5322a1ceb8cfae0c2506dc5e0a9e5d8bca6627b4`); the
idle-unload numbers on `09a86457d2260ff93dc676e16e7bf67679751f5e` (tree
`901804ef5044c83718160b8827dc928c294457ee1eff1d52720c9c324de73aa0`). The
last code commit differs from `09a8645` only in the supervisor's single-writer
bound on the press-time ask (`localflow/v2/supervisor.py`); the worker the
rig drives is byte-identical.
**Final tree A/B:** run `final-ab-1`, a full shipping A/B of the baseline
export (`localflow/` tree `e8c71fe8…`) against the last code commit `7d523d8`
(tree `6f1762f7e687…`), pinned to the A/A `baseline-aa-shipping-3`, 12:25 AM
to 1:59 AM EDT on October 28 (unloading is switched off in every phase of this
run, as in the rig's other phases). All ten latency bands pass (paired medians
-13.3 to +2.9 ms, every paired p95 inside its effective limit), the back-to-back
gap is -0.0 ms, identity passes for every cleanup case, both speech clips
and the first-request outputs, no fault frame appeared and the generation
stayed 1. Footprint (MiB, 12 spawns per side): idle at ready 4,153 to 3,981
cold-ish and 4,155 to 3,982 warm; launch peak 6,554 to 5,837 cold-ish and
7,066 to 5,837 warm (the baseline's warm launch peaks range from 6,554 to
7,578, so its warm median moves between runs); idle 2 s after a 20-dictation
burst 4,168 to 4,170 (median of six bursts per side, unchanged); lifetime peak
after the burst 7,373 on both sides.
**Install.** The new launcher is byte-identical to the previous install's, so
the macOS Accessibility and Input Monitoring grants carry over. The previous
app was quit with the ordered quit (`worker.shutdown` reaped the worker,
`app.shutdown` drained the store) and the new app started a fresh worker whose
two engines reached ready with no fault. Read with the footprint tool right
after launch, that worker shows a footprint of 3,981 MiB at ready and a
lifetime peak of 5,865 MiB (the rig measured 3,981 and 5,837 for this code, and
4,153 and 6,554 cold-ish for the baseline side). Each app's `BUILD.json`
manifest of 169 bundled `localflow/` files matches its source commit
byte for byte: the installed app matches `7304b0e` and the rollback copy
matches `14a009a`. The only shipped-code differences between those two
commits are the files of this work.
**Rollback copy.** The previous installed app (built from `main` at `14a009a`;
its `BUILD.json` reads `dirty` true, from files outside the bundled code; 972
MB) is kept at
`~/Library/Application Support/LocalFlow/v2-evidence/footprint/installed-app-before-20261028/LocalFlow.app`.
It is private and not in the repository, and it is the build without the
changes that M03-V009 compares against.
**Live unload:** LIVE-UNLOAD-PENDING: the installed worker's first idle unload (due about 2:17 AM EDT on October 28) is not recorded here yet.
**This record:** this file, `STATUS.json` (`current_state.worker_footprint`)
and the pending runbook entries M03-V009 and M03-V010. No commit of the
record changes code.

**Files.** Production: `localflow/v2/worker.py` (the allocator release, the
optional memory frames, the idle unload and `ensure_cleanup`),
`localflow/v2/cleanup/model.py` (`ModelRunner.load` takes an optional
`on_phase` callback, fired once the weights are loaded and before the warmup
generation), `localflow/v2/supervisor.py` (the `unloaded` state,
`prepare_cleanup`, the wait for a resting model), `localflow/app.py` (the
press-time ask and the menu-bar label), `localflow/v2/ui/companion/controller.py`
(the Hub re-reads the engine on a cleanup state change),
`frontend/src/app/Sidebar.svelte` and `frontend/src/routes/models/Engines.svelte`
with the rebuilt tracked bundle under `localflow/v2/ui/companion/web/`
(`BUILD.json`, `index.html`, `assets/`). Contract: `docs/v2/contracts/worker.md`,
sections *Memory diagnostics*, *Allocator release at load* and *Idle unload of
the cleanup model*. Decision: `docs/v2/decisions/ADR-0003-idle-unload-of-the-cleanup-model.md`.
Rig: `scripts/v2/footprint_rig.py` (with its `idle` phase). Tests:
`tests/v2/lifecycle/{test_footprint_rig,test_footprint_rig_session,test_worker_cache_release,test_worker_memory_diag,test_worker_idle_unload,test_idle_unload_supervisor,test_idle_unload_app}.py`,
`tests/v2/ui/test_idle_unload_display.py`, `frontend/tests/owner-polish.test.mjs`
and the shim options in `tests/v2/lifecycle/prod_worker_harness.py` and
`tests/v2/lifecycle/fake_worker.py`. Records: this file,
`docs/v2/STATUS.json`, `docs/v2/VERIFICATION.html`.

## What the worker does now

Once an engine's load and warmup finish, and before its `ready` frame, the
worker hands the allocator's unused cached memory back once, on the GPU
thread. It runs after the ASR warmup and after the cleanup warmup, as the
last step of that engine's load: never while a request runs and never between
the chunks of one recording. A cleanup load that waits for a request (a
deferred load, or one queued behind requests that arrived first) can run,
release included, between two requests. The release adds no frame and no
engine state. With `LOCALFLOW_WORKER_MEMORY_DIAG=1` the worker
also writes content-free memory counters at six labels as `diag` frames;
with the variable unset the frame stream is unchanged.

After an idle period of 600 seconds with nothing queued or running, the worker
also drops the cleanup model, runs the allocator release and writes one
`unloaded` cleanup engine frame (`CLEANUP_IDLE_UNLOAD_S`; the environment
variable `LOCALFLOW_WORKER_IDLE_UNLOAD_S` is a test and measurement seam, not
a setting). The speech engine never unloads, and neither does a `v1` cleanup
or a mode other than `llm`. The model comes back through the load's own
`loading` and `ready` frames when a hotkey press sends `ensure_cleanup` (the
app writes it from a short-lived daemon thread right after the recorder
starts, so the reload overlaps the recording) or when a `clean` finds the
engine unloaded. A `clean` that arrives during an unload or reload waits and
gets the real answer (path `llm`), never the not-ready answer; the first load
at worker start keeps today's behaviour. An unload or reload writes no fault,
keeps the generation, never restarts the worker and does not count toward the
breaker. The supervisor, the menu-bar line (`Cleanup: resting`), the Hub's
sidebar and Models page handle the state. The contract and ADR-0003 hold the
exact rules and are not repeated here.

## Before and after

Side A is the baseline: the `localflow/` tree of commit `45bf38d` (the rig
and the inert diagnostics, no release), SHA-256
`e8c71fe828a7f2fcd39d8ad3296697d0cad1228d5a1cd78f2fdcf9d8bbae6797`, frozen as
an export. Side B is the candidate: the `4eff5a3` tree above. Runs are in
the private evidence root `~/Library/Application Support/LocalFlow/v2-evidence/footprint/`
and are never copied into the repository:

| Run | What it holds |
|---|---|
| `perf02-shipping-3` (A/B, pinned to the A/A `baseline-aa-shipping-3`) | footprint, bursts, resident latency bands, back-to-back gap, identity; 7:58 PM to 9:28 PM EDT, October 27 |
| `perf02-first-1` (A/B, pinned to the A/A `baseline-aa-first-1`) | the two first-request rows; 9:48 PM to 9:53 PM EDT, October 27 |
| `ticket05-gate` | the Residency gate: reload time and capture durations (ticket 05) |
| `perf05-idle-1` (idle phase, one tree on both sides) | the idle unload: footprint drop, reload time, release-to-result per capture length, never-degraded and second-dictation checks; 12:11 AM to 12:23 AM EDT, October 28 |

Both models are those the installed configuration names: ASR
`mlx-community/parakeet-tdt-0.6b-v3` at revision
`ed2b7e8c15f9aaa0b5772e2efb986255eaef7e15`, cleanup
`local/LocalFlow-Cleanup-M2-Qwen3.5-4B-4bit`. The machine was an Apple M5 Pro
with 48 GB on AC power, no thermal warning before or after each run;
macOS 27.2, Python 3.14.9, mlx 0.31.2, mlx-lm 0.31.3, parakeet-mlx 0.5.2.
Sizes are MiB as the footprint tool reports them.

| Row | A baseline | B candidate | Limit (Gate table) | Verdict |
|---|---|---|---|---|
| Idle at ready, total | 4,154 | 3,980 | Idle floor 100 | 174 lower, **not lasting** (next row) |
| Idle at ready, GPU line | 3,782 | 3,609 | | 173 lower |
| Idle 2 s after a 20-dictation burst, total (median of six bursts per side) | 4,168.5 | 4,168 | Idle floor 100 | unchanged |
| Launch peak, cold-ish (5 spawns per side) | 6,554 | 5,837 | Peak floor 500 | 717 lower, pass |
| Launch peak, page-cache-warm (7 spawns per side) | 6,656 | 5,837 | Peak floor 500 | 819 lower, pass |
| Lifetime peak after the burst | 7,373 | 7,373 | | unchanged |
| Back-to-back gap (30 pairs) | | -0.0 ms (max 0.1) | under 50 ms | pass |
| Identity: every cleanup case and both speech clips | | match | any mismatch fails | pass |
| Latency, eight resident bands | | paired median -5.1 to +0.7 ms, paired p95 2.8 to 34.7 ms | Latency rule | pass |
| Latency, first request after ready | | ASR 0.6 ms median, 5.3 ms p95; cleanup -4.3 ms median, 17.1 ms p95 | Latency rule | pass |

Identity compares the SHA-256 of every output text, the recorded decode
ranges and the per-pass output token counts; the 60 second chunker ran on the
long clip. The rig also compares the first-request outputs A against B
within each pair (ASR text and decode-range digests, cleanup text digest and
per-pass token counts) as part of Identity. The two final runs
(`perf02-shipping-3`, 10 pairs, and `perf02-first-1`, 30 pairs) predate that
comparison, so those outputs were compared from their reports afterwards:
equal in all 40 pairs. The prefix-cache parity test with the production cleanup
identifier (`tests/v2/cleanup/test_prompt_cache_parity.py`, prompt tokens
2,389, 4,575 and 558) and `tests/v2/cleanup/test_prompt_cache.py` (5 tests)
pass. No fault frame appeared, the worker generation stayed 1, no engine
loaded twice and the rig did not stop either run.

The lever lowers the spike paid at launch, not the peak once dictations run:
the first dictation refills the 173 MiB the release returned. The footprint
of a worker that has been idle for ten minutes is the unload's, below.

### Latency by band

Paired, interleaved (A,B,B,A) round-trip times, `perf02-shipping-3`. The
effective limit is max(spec limit, the A/A run's own value of the same
statistic), so no limit is tighter than the instrument.

| Band | Pairs | Baseline median / p95 ms | Paired median / p95 ms | Effective limits ms |
|---|---|---|---|---|
| cleanup 1 to 20 words | 150 | 458.9 / 763.7 | -2.1 / 14.5 | 50.0 / 76.4 |
| cleanup 21 to 50 | 65 | 624.2 / 1,033.0 | -1.7 / 18.4 | 50.0 / 103.3 |
| cleanup 51 to 100 | 30 | 1,437.0 / 1,952.5 | -2.6 / 20.8 | 71.8 / 195.3 |
| cleanup 101 to 200 | 15 | 2,165.6 / 2,260.4 | -5.1 / 34.7 | 108.3 / 226.0 |
| ASR under 10 s | 150 | 77.8 / 86.6 | -0.2 / 2.8 | 50.0 / 8.7 |
| ASR 10 to 30 s | 150 | 201.0 / 252.4 | -0.1 / 4.4 | 50.0 / 25.2 |
| ASR 30 to 90 s | 150 | 552.8 / 767.6 | 0.7 / 7.6 | 50.0 / 76.8 |
| ASR over 90 s | 150 | 1,317.3 / 1,466.4 | 0.7 / 8.6 | 65.9 / 146.6 |
| first request, ASR (`perf02-first-1`) | 15 | 212.8 / 215.0 | 0.6 / 5.3 | 50.0 / 21.5 |
| first request, cleanup (`perf02-first-1`) | 15 | 932.2 / 942.2 | -4.3 / 17.1 | 50.0 / 94.2 |

Negative means the candidate is faster. The A/A runs on identical code read
the first-request rows at 0.7 / 6.5 ms (ASR) and -2.7 / 18.5 ms (cleanup).
`perf02-shipping-3` reads FAIL on one row, the first-request ASR paired p95
(27.8 ms against an effective limit of 26.9 ms) under the per-pair
statistic; the row is judged on the block statistic below, which passes. The
frozen length bands hold 94, 13, 6 and 3 cleanup cases and 30 ASR clips per
band; the three upper cleanup bands are short of the Gate table's 30 cases
(they ran all five repeats), because the corpus has no more cases in those
bands.

## Idle unload of the cleanup model

The Residency gate failed on both clauses (numbers under *Ticket records*).
The owner chose to build the unload anyway and accepted a wait on short
dictations that start right after an unload; ADR-0003 records the decision.

### Measured: `perf05-idle-1`

The rig's idle phase, one tree (head `09a8645`) on both sides. Side B's worker
unloads the cleanup model after 6 idle seconds (`LOCALFLOW_WORKER_IDLE_UNLOAD_S`);
side A's never unloads. For each capture length the rig waits for side B's
unload, reads its footprint, then runs one simulated dictation per side (side
B gets the `ensure_cleanup` ask at the press) and judges the release-to-result
times on ABBA blocks of two pairs: 5 blocks per length, 40 unloads in all. No
A/A report is pinned, so the spec limits apply; the rig records these bands as
measured and none changes its exit status. AC power, no thermal warning before
or after; the installed idle worker's CPU time rose 0.07 s over the run.

| Row | Result |
|---|---|
| Footprint 2 s after ready against 2 s after the unload (40 unloads) | drops by a median of 2,653 MiB (range 2,373 to 2,655), 117% of the cleanup weights (2,258 MiB) |
| Reload, press to the cleanup `ready` frame (40 dictations) | 1,720 ms minimum, 1,760 ms median, 1,900 ms maximum |
| Cleanup requests during an unload or reload | all 60 on side B came back path `llm`; none was degraded |
| Idle outputs, A against B | identical |
| Second dictation started during the reload | both cleanups path `llm` and equal to side A's; exactly one reload; last result at 3,997 ms against 2,565 ms on side A (median over pairs) |

Release-to-result by capture length, paired, interleaved (A,B,B,A); positive
means side B is slower. The reload remainder is the reload time minus the
capture length, never below zero.

| Capture | Blocks | Baseline median / p95 ms | Paired median / p95 ms | Spec limits ms | Verdict | Median reload remainder ms |
|---|---|---|---|---|---|---|
| 0.5 s | 5 | 1,143.9 / 1,156.1 | +1,227.2 / +1,250.4 | 57.2 / 115.6 | fails, accepted | 1,263 |
| 1 s | 5 | 1,147.4 / 1,150.8 | +739.1 / +794.9 | 57.4 / 115.1 | fails, accepted | 770 |
| 2 s | 5 | 1,136.9 / 1,150.8 | -17.5 / -7.6 | 56.8 / 115.1 | pass | 0 |
| 5 s | 5 | 1,143.1 / 1,153.1 | -2.0 / +3.2 | 57.2 / 115.3 | pass | 0 |

### What waits and what never changes

- **What waits.** Cleanup, for a dictation shorter than the reload that began
  after an idle unload. In the recorded history that is about 6% of the
  after-idle dictations (2 of the 32 measurable ones, the largest shortfall
  1.435 s). A `transcribe` that reaches the worker while a reload runs waits
  for it too.
- **Transcription cannot hide a reload.** The Gate table assumed that
  transcription time also overlaps the reload; it does not, because the
  reload and the transcription share the worker's one GPU thread. A reload
  still running when the recording ends delays the transcription by its
  remainder. When the reload starts with the recording, the added wait is
  about the reload time minus the recording length, never below zero: up to
  about 1.9 s for a very short dictation (1.935 s measured worst at the gate).
  The reload can start slightly after the recording does, when the worker's
  GPU thread is free.
- **What never changes.** The cleaned text (idle outputs are identical to the
  side that never unloads), the speech recognizer (always resident, its
  latency unchanged outside a reload), the generation numbers, the fault
  policy, the breaker, and the lifecycle; the first load at worker start.
- **A very long recording.** The press-time ask restarts the idle clock once.
  A recording longer than the idle period can meet an unloaded model when it
  ends, and its cleanup then waits for a full reload after the transcription.
  Such recordings are rare (the longest in the recorded history is under four
  minutes) and the reload is small beside their transcription time, so no
  timer keeps the model loaded during a recording.

## Ticket records

- **01, rig and baseline: closed, done.** `scripts/v2/footprint_rig.py` spawns
  the real worker, loads both models and measures from outside, writing a
  content-free report under the private evidence root. It takes an exclusive
  lock so one measurement runs at a time, and stops itself above 16 GiB of
  footprint or 2 GiB of swap growth. The A/A run passes Rig validity.
  `baseline-aa-shipping-2` is superseded as a latency noise floor (see
  *Where measurement overrode the spec's defaults*); its footprint and burst
  numbers stand.
- **02, launch peak: closed, done, shipped.** The lever is one allocator
  release after each engine's load and warmup (`85a05f1`, `localflow/v2/worker.py`).
  Results are in the table above. The loader form was not built (below).
- **03, steady-state cache: closed on its stop rule, no code.** In the 12
  burst spawns of `baseline-aa-shipping-2`, the footprint 2 s after a
  20-dictation burst is 13 to 17 MiB above the same spawn's idle (median 15)
  against the Idle floor of 100 MB; the cleanup library already returns the
  allocator cache to 173 to 266 MiB after every result. Not a lever: the
  173 MiB block is also present at idle after warmup, so a trim would lower
  idle by at most that much while the pool refills at the next dictation.
- **04, verify and record: this record.** It records the outcome and the
  numbers above; no production code changes in it.
- **05, idle unload: the Residency gate failed; built on the owner's
  decision (ADR-0003), shipped on `main`.** The gate: the
  worker's own cleanup load path, warmup included, timed in a disposable
  in-process script outside the repository on the `4eff5a3` tree
  (weights 2,258 MiB): page-cache-warm 1.679 to 1.723 s (median 1.699 s,
  10 repetitions), cold-ish 1.830 to 1.935 s (median 1.854 s, 10
  repetitions, weights' page-cache residency under 0.05%). Worst reload
  1.935 s. Usage records (dictation facts of October 19 to 27, capture
  duration and activity time only): 78 rows, 64 with a usable capture
  duration; capture duration minimum 0.35 s, median 37.9 s, 95th percentile
  172.6 s. 59 of 64 dictations (92.2%) last at least the worst reload
  against the 99% required; the largest shortfall is 1.585 s and 4 of the 5
  short dictations exceed the 300 ms added-wait limit. Both clauses fail.
  The owner accepted the wait on short dictations and the unload was built
  (what it does: *What the worker does now*; results and what waits:
  *Idle unload of the cleanup model*).
- **Loader (ticket 02's second form): not built.** The Loader gate trips
  numerically (candidate launch peak 1,857 MiB above its idle, gate 1 GB),
  but the allocator peak (5,250 MiB) is set in the cleanup warmup on both
  sides, and the candidate's ASR phase peaks at 2,365 MiB (baseline 2,349)
  with 0 MiB cached after the ASR warmup. A bounded ASR loader acts only on
  that earlier phase, so it cannot lower the launch peak and cannot meet its
  own ship condition.

## Where measurement overrode the spec's defaults

- **The allocator release claims launch peak only.** Its idle gain at launch
  (174 MiB) is refilled by the first dictation, so idle is not claimed for it;
  the idle footprint gain belongs to the unload.
- **The Residency gate failed and the unload was built on the owner's
  decision.** The Gate table says a lever that misses its gate is closed with
  a note; the owner accepted the wait on short dictations instead (ADR-0003),
  so the Latency rule fails for the 0.5 s and 1 s captures of an after-idle
  dictation by design, and passes at 2 s and 5 s.
- **Transcription does not overlap the reload.** The Gate table assumed
  transcription time also overlaps the reload, making capture duration a
  conservative budget. The reload and the transcription share the worker's one
  GPU thread, so capture duration alone is the budget: the added wait is about
  the reload time minus the recording length.
- **Ticket 03 closed on its comparison rule** (growth over the same spawn's
  idle). The Gate table's Idle floor alone would not have stopped a trim of
  the 173 MiB block, which the observation above explains.
- **The Loader gate tripped but the loader was not built**, for the reason
  recorded under *Loader*.
- **Noise-floor rule.** Every Latency limit is max(spec limit, the A/A run's
  value of the same statistic), so a limit is never tighter than what the
  rig measures on identical code.
- **ASR latency bands interleave one unmeasured cleanup request after each
  ASR request.** ASR-only streams of different-length clips grow the worker's
  allocator cache about 1.1 to 1.5 GB per request, and only a cleanup request
  clears it; a real dictation ends in cleanup. The extra request is part of
  no verdict, digest, pair or request count.
- **First-request rows are judged on ABBA blocks of two spawn pairs** (an AB
  pair, then a BA pair; difference is the mean of the two B-minus-A values,
  baseline the mean of the two A values; 30 pairs, 15 blocks). The process
  that asks first is about 25 ms slower in the A/A as much as in the A/B, so
  the orders cancel it in a block but not in a single pair's p95. The rule was
  fixed before the re-run.

## Limits of this evidence

- **The Gate table's 30-case shipping claim is not met in three bands.** The
  cleanup bands of 21 to 50, 51 to 100 and 101 to 200 words hold 13, 6 and 3
  committed cases, a spec requirement this evidence does not meet. Every
  committed case in them ran all 5 repeats (65, 30 and 15 measured blocks)
  and the corpus has no more cases in those bands, so the verdict for those
  bands rests on all available cases, not on the claimed count.
- The worker protocol seam does not see the interval from releasing the key
  to the text appearing in an app. That check is M03-V009 in
  `VERIFICATION.html`, **Not run**.
- ASR-only request streams still grow the allocator cache about 1.1 to 1.5 GB
  per request with active memory flat at 3,607 MiB (cached reached 18,528 MiB
  after 15 requests, identical on baseline and candidate). It matters only
  when ASR runs without a cleanup request after it (cleanup off or basic, or
  a caller that sends ASR alone); that case was not audited.
- Latency was measured at the worker protocol on synthetic fixtures and
  speech generated with the system synthesizer, never on the owner's audio.
- The idle measurement (`perf05-idle-1`) uses those synthetic clips on the same
  code on both sides, with unloading off on side A. Its idle period is 6 s,
  set through the test seam; the production period is 600 s. The period sets
  when the unload fires, not what it does, but a reload after a real ten idle
  minutes can start from colder page cache and take as long as the gate's
  cold-ish worst of 1.935 s.
- The rig drives the worker directly. The supervisor, app, menu-bar, Hub and
  frontend changes of the unload have no model-backed measurement; tests with
  fake workers cover them. The owner's real hotkey path after a real idle
  period is M03-V010 in `VERIFICATION.html`, **Not run**.

## Pending owner decisions

1. **Run the runbook checks M03-V009 and M03-V010.** V009 is the key release
   to inserted text check in the real app on the reference condition,
   repeated on one synthetic job: the rollback copy (the build without the
   changes) against the installed app (the build with them). V010 is the idle
   unload in the installed app after real idle periods: footprint, cleanup
   states, the menu-bar line, a six-second dictation and a one-second
   dictation. Both are in the runbook as pending local verification and are
   not run. The two apps share one bundle identifier, so each check quits one
   before it opens the other.
2. **Reopen ticket 03 for a cache limit or a trim after an ASR result?** It
   matters only for ASR requests with no cleanup request after them (see
   *Limits*).
3. **Delete the earlier evidence runs, the baseline export and the rollback
   copy of the previous install.** The evidence runs and the baseline export
   are under `~/Library/Application Support/LocalFlow/v2-evidence/footprint/`
   and the git-ignored `.scratch/worker-footprint/`. The final runs
   (`perf02-shipping-3`, `perf02-first-1` and their A/A runs, `perf05-idle-1`
   and `final-ab-1`) are the record behind this file, with `ticket05-gate`
   for the gate numbers; the baseline export can be recreated from commit
   `45bf38d` with `git archive` and identified by its tree digest. The
   rollback copy is the build M03-V009 needs, so it stays until that check
   has run or been dropped.

## Re-running the measurement

`.venv/bin/python scripts/v2/footprint_rig.py --code-root-a <baseline export> --code-root-b <candidate checkout> --mode shipping`,
pinning a finished A/A run with `--aa-report`. The idle phase is named in
`--phases` and is never part of a default run (`--phases idle`; side B unloads
after `--idle-unload-s` seconds, 6 by default, and side A never does). One run
at a time; AC power; no
dictation during the run; run suites with `LOCALFLOW_DATA_HOME` set to a
scratch directory. Pin only an A/A run made by the rig at or after `fdc4e2f`.
The rig refuses a pinned report unless it is complete and not aborted, was an
A/A (both sides one tree), passed Rig validity and Identity where it states
them, and froze the same bands and ran the same baseline tree as this run.
