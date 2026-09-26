# M09 remediation benchmark, final code — 2026-09-26 (reference Mac)

The work-valid M09 benchmark at full size on the final remediation code,
after the independent review round. The failing first-pass run is
`../20260926-112149-m09-remediation/`.

## Provenance

- Code: the committed checkout at `18ff4f5` (production `a304d48`), no
  tracked file modified. Benchmark script sha256 `024f4118aec01cec…`
  (unchanged since the first pass).
- Mac: Apple M5 Pro (Mac17,8), 18 CPUs, macOS 27.0, Python 3.14.7.
  Load average 9.36 / 9.17 / 9.53 at start: other sessions were active
  on the machine. Read absolute timings with that in mind.
- Under `tests/v2/context/run_isolated.py` (no Accessibility, key events
  or general pasteboard).
- Population: 50,000 synthetic jobs (516 carry the hit token), 5,000
  legacy analytics rows, 1,000 legacy log pairs, 1,000 Training
  examples, 2,000 events, 5 styles, 5 snippets, 5 notes, 5 real
  dictations through the Harness coordinator.

## Validity before timing

A cohort's timing counts only when its work checked out: each search
returns exactly the expected ids (e.g. text hit: 200 of the 516 seeded
hits, newest first; the mixed browse includes both job and legacy
rows), the shell pass renders every view and subtab from its own
service, every admitted query is accounted for and drained, the
Training cohort lists 1,000 examples, and the dispatch runs through the
real main-thread queue. `m09_benchmark_mutation_check.py` shows each of
those checks rejecting a weakened benchmark
(`acceptance/M09/remediation/benchmark_mutation_final_18ff4f5.json`: 8
of 8 killed; an injected 50 ms delay moved every search p50 by
50.7–51.2 ms).

## Results (ms)

`work_valid: true`, `timing_qualified: true` (exit 0).

| Cohort (clock) | first pass p95 | final p50 / p95 / p99 / max | Budget | Verdict |
|---|---|---|---|---|
| History text hit (search call → rows) | 38.3 | 31.0 / 33.9 / 34.3 / 34.3 | 200 | pass |
| History text miss | 31.9 | 29.8 / 32.7 / 34.3 / 34.3 | 200 | pass |
| History app filter | 27.6 | 29.5 / 33.1 / 35.0 / 35.0 | 200 | pass |
| History mode filter | 42.0 | 47.5 / 51.0 / 52.1 / 52.1 | 200 | pass |
| History browse, mixed sources | 1500.7 | 58.3 / 60.7 / 62.5 / 62.5 | 200 | pass |
| History legacy mode | 1350.9 | 4.1 / 4.8 / 5.1 / 5.1 | 200 | pass |
| Shell full pass (init → every view/tab rendered on main) | 1633.4 | 315.3 / 325.3 / 325.3 / 325.3 | 1000 | pass |
| Training list (1,000) / detail / readiness | 3.7 / 0.1 / 11.5 | p95 5.6 / 0.2 / 15.0 | — | reported |
| Diagnostics window (last 500) / redacted export (500) | 26.7 / 6.0 | p95 27.2 / 6.2 | — | reported |

Search cohorts n = 50; shell n = 10; Training and Diagnostics n = 20.
The first-pass browse and legacy-mode figures are the per-pair
hydration defect fixed in `0083466`; the other differences are within
the load noise of a shared machine.

**Rapid search.** 100 search changes while a real dictation runs:
admission 0.39 ms on main in total, drained in 42 ms, one query thread,
99 requests superseded before they started, one store search; the
dictation took 46.4 ms against 13.8 ms idle.

**Memory.** Python heap 1.3 MB after shutdown (peak 12.8 MB); process
RSS 134.6 → 165.3 MB with every view visited (tracemalloc for the
Python heap, `ps` for resident memory — not an isolated allocation
count).
