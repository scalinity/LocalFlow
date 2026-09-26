# M09 remediation benchmark, final code — 2026-09-26 (reference Mac)

The work-valid M09 benchmark at full size on the final remediation code,
after the independent review round. The failing first-pass run is
`../20260926-112149-m09-remediation/`.

## Provenance

- Code: the committed checkout at `dbeee1c` (production `caec491`), no
  tracked file modified. Benchmark script sha256 `024f4118aec01cec…`.
- Mac: Apple M5 Pro (Mac17,8), 18 CPUs, macOS 27.0, Python 3.14.7.
  Load average 7.88 / 7.84 / 7.80 at start: other sessions were active
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
(`acceptance/M09/remediation/benchmark_mutation_final_dbeee1c.json`: 8
of 8 killed; an injected 50 ms delay moved every search p50 by
52.5–57.7 ms).

## Results (ms)

`work_valid: true`, `timing_qualified: true` (exit 0).

| Cohort (clock) | first pass p95 | after `0083466` p95 | final p50 / p95 / p99 / max | Budget | Verdict |
|---|---|---|---|---|---|
| History text hit (search call → rows) | 38.3 | 27.0 | 28.1 / 32.6 / 33.2 / 33.2 | 200 | pass |
| History text miss | 31.9 | 26.0 | 27.2 / 30.1 / 31.6 / 31.6 | 200 | pass |
| History app filter | 27.6 | 25.5 | 27.1 / 29.8 / 31.1 / 31.1 | 200 | pass |
| History mode filter | 42.0 | 44.6 | 44.0 / 49.5 / 52.0 / 52.0 | 200 | pass |
| History browse, mixed sources | 1500.7 | 58.8 | 53.7 / 57.1 / 61.6 / 61.6 | 200 | pass |
| History legacy mode | 1350.9 | 4.9 | 3.7 / 4.6 / 4.9 / 4.9 | 200 | pass |
| Shell full pass (init → every view/tab rendered on main) | 1633.4 | 302.7 | 319.1 / 327.0 / 327.0 / 327.0 | 1000 | pass |
| Training list (1,000) / detail / readiness | 3.7 / 0.1 / 11.5 | 5.8 / 0.2 / 12.6 | p95 4.9 / 0.1 / 13.1 | — | reported |
| Diagnostics window (last 500) / redacted export (500) | 26.7 / 6.0 | 26.2 / 6.0 | p95 27.1 / 6.3 | — | reported |

Search cohorts n = 50; shell n = 10; Training and Diagnostics n = 20.

**Rapid search.** 100 search changes while a real dictation runs:
admission 0.37 ms on main in total, drained in 39 ms, one query thread,
99 requests superseded before they started, one store search; the
dictation took 42.0 ms against 13.3 ms idle.

**Memory.** Python heap 1.3 MB with the Hub built and after shutdown
(peak 12.8 MB); process RSS 135.9 → 167.1 MB with every view visited.
