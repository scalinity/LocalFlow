# Worker footprint reduction

October 27, 2026. State: `WORKER_FOOTPRINT_COMPLETE_PENDING_LOCAL_VERIFICATION`.
The work is on branch `perf/worker-footprint` and is **not merged to `main`**.
The installed app and its idle worker were not changed.

**Goal:** lower the dictation worker's memory with the same two models, the
same output text and the same speed.
**Result:** the worker's launch peak is lower by 717 to 819 MiB. Its idle
footprint after the first dictation is unchanged, so the idle gain at launch
does not last. The other levers closed without code.
**Base commit:** `14a009a4f3d7d64a6419c12638af65bc6ed9b2a8` (`main`).
**Integration head:** `4eff5a3e98e3c396e06212f8aa2429c39ce3da67` on
`perf/worker-footprint`; `localflow/` tree SHA-256
`400fa463b31eeaca24b5c1ea5322a1ceb8cfae0c2506dc5e0a9e5d8bca6627b4`.
**This record:** this file, `STATUS.json` (`current_state.worker_footprint`)
and the pending runbook entry M03-V009 land in one commit on
`perf/04-verify-and-record`, cut from the integration head. The commit
changes no code.

**Files.** Production: `localflow/v2/worker.py` (the allocator release and
the optional memory frames), `localflow/v2/cleanup/model.py`
(`ModelRunner.load` takes an optional `on_phase` callback, fired once the
weights are loaded and before the warmup generation). Contract:
`docs/v2/contracts/worker.md`, sections *Memory diagnostics* and *Allocator
release at load*. Rig: `scripts/v2/footprint_rig.py`. Tests:
`tests/v2/lifecycle/{test_footprint_rig,test_footprint_rig_session,test_worker_cache_release,test_worker_memory_diag}.py`
and the shim options added to `tests/v2/lifecycle/prod_worker_harness.py`.
Records: this file, `docs/v2/STATUS.json`, `docs/v2/VERIFICATION.html`.

## What the worker does now

Once an engine's load and warmup finish, and before its `ready` frame, the
worker hands the allocator's unused cached memory back once, on the GPU
thread. It runs after the ASR warmup and after the cleanup warmup, never
between requests or between the chunks of one recording, and it adds no
frame and no engine state. With `LOCALFLOW_WORKER_MEMORY_DIAG=1` the worker
also writes content-free memory counters at six labels as `diag` frames;
with the variable unset the frame stream is unchanged. The contract holds
the exact rules and is not repeated here.

## Before and after

Side A is the baseline: the `localflow/` tree of commit `45bf38d` (the rig
and the inert diagnostics, no release), SHA-256
`e8c71fe828a7f2fcd39d8ad3296697d0cad1228d5a1cd78f2fdcf9d8bbae6797`, frozen as
an export. Side B is the candidate: the integration tree above. Runs are in
the private evidence root `~/Library/Application Support/LocalFlow/v2-evidence/footprint/`
and are never copied into the repository:

| Run | What it holds |
|---|---|
| `perf02-shipping-3` (A/B, pinned to the A/A `baseline-aa-shipping-3`) | footprint, bursts, resident latency bands, back-to-back gap, identity; 7:58 PM to 9:28 PM EDT, October 27 |
| `perf02-first-1` (A/B, pinned to the A/A `baseline-aa-first-1`) | the two first-request rows; 9:48 PM to 9:53 PM EDT, October 27 |
| `ticket05-gate` | the idle-unload gate (ticket 05) |

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
long clip. The prefix-cache parity test with the production cleanup
identifier (`tests/v2/cleanup/test_prompt_cache_parity.py`, prompt tokens
2,389, 4,575 and 558) and `tests/v2/cleanup/test_prompt_cache.py` (5 tests)
pass. No fault frame appeared, the worker generation stayed 1, no engine
loaded twice and the rig did not stop either run.

The lever lowers the spike paid at launch, not the peak once dictations run:
the first dictation refills the 173 MiB the release returned.

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
  allocator cache to 173 MiB after every result. Not a lever: the 173 MiB
  block is also present at idle after warmup, so a trim would lower idle by
  at most that much while the pool refills at the next dictation.
- **04, verify and record: this record.** It records the outcome and the
  numbers above; no production code changes in it.
- **05, gated idle unload: closed on a failed Residency gate, no code.** The
  worker's own cleanup load path, warmup included, timed in a disposable
  in-process script outside the repository on the integration tree
  (weights 2,258 MiB): page-cache-warm 1.679 to 1.723 s (median 1.699 s,
  10 repetitions), cold-ish 1.830 to 1.935 s (median 1.854 s, 10
  repetitions, weights' page-cache residency under 0.05%). Worst reload
  1.935 s. Usage records (dictation facts of October 19 to 27, capture
  duration and activity time only): 78 rows, 64 with a usable capture
  duration; capture duration minimum 0.35 s, median 37.9 s, 95th percentile
  172.6 s. 59 of 64 dictations (92.2%) last at least the worst reload
  against the 99% required; the largest shortfall is 1.585 s and 4 of the 5
  short dictations exceed the 300 ms added-wait limit. Both clauses fail.
- **Loader (ticket 02's second form): not built.** The Loader gate trips
  numerically (candidate launch peak 1,857 MiB above its idle, gate 1 GB),
  but the allocator peak (5,250 MiB) is set in the cleanup warmup on both
  sides, and the candidate's ASR phase peaks at 2,365 MiB (baseline 2,349)
  with 0 MiB cached after the ASR warmup. A bounded ASR loader acts only on
  that earlier phase, so it cannot lower the launch peak and cannot meet its
  own ship condition.

## Where measurement overrode the spec's defaults

- **Launch peak is the only claim.** The idle gain at launch (174 MiB) is
  refilled by the first dictation, so idle is not claimed.
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

## Pending owner decisions

1. **Install a new build.** The worker change reaches the installed app only
   after a reinstall of a build that contains it; the branch is not merged to
   `main`. The installed app and its idle worker were left untouched. A
   qualification build of the integration head goes to a new absolute path
   with `scripts/build_app.sh --output`, never over `/Applications/LocalFlow.app`.
2. **Run M03-V009**, the key release to inserted text check in the real app on
   the reference condition, repeated on one synthetic job. It is appended to
   the runbook as pending local verification and is not run.
3. **Reopen ticket 03 for a cache limit or a trim after an ASR result?** It
   matters only for ASR requests with no cleanup request after them (see
   *Limits*).
4. **Delete the earlier evidence runs and the baseline export** under
   `~/Library/Application Support/LocalFlow/v2-evidence/footprint/` and the
   git-ignored `.scratch/worker-footprint/`. The final runs
   (`perf02-shipping-3`, `perf02-first-1` and their A/A runs) are the record
   behind this file; the baseline export can be recreated from commit
   `45bf38d` with `git archive` and identified by its tree digest.

## Re-running the measurement

`.venv/bin/python scripts/v2/footprint_rig.py --code-root-a <baseline export> --code-root-b <candidate checkout> --mode shipping`,
pinning a finished A/A run with `--aa-report`. One run at a time; AC power; no
dictation during the run; run suites with `LOCALFLOW_DATA_HOME` set to a
scratch directory. Pin only an A/A run made by the rig at or after `fdc4e2f`.
