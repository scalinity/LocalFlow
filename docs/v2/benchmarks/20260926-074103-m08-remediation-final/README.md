# M08 remediation benchmark, final code — 2026-09-26 (reference Mac)

The work-valid benchmark (schema 2) rerun on the final remediation code,
after the independent review round. The first-pass run
(`../20260926-062315-m08-remediation/`, production `846fd2c`) and the
historical fixture run (`../20260922-131238-m08/`) are unchanged and
describe other code.

## Provenance

- Code: the committed checkout at `9483d1b` (production `ea83bc1`), no
  tracked file modified; `localflow` imported from that root. Benchmark
  script unchanged since the first pass (sha256 `19541c2c…a6f608`).
- Mac: Apple M5 Pro (Mac17,8), 18 CPUs, 48 GiB, macOS 27.0 (26A428),
  arm64; Python 3.14.7, PyObjC 12.2.1. **Battery power** (the first pass
  ran on AC) and load average 3.45/3.03/2.93: other sessions were active
  on the machine. Read the absolute timings with both in mind.
- Desktop isolation as in the first pass: portable cohorts under
  `tests/v2/context/run_isolated.py`; the native cohort reached only its
  own helper by pid; no key event posted.

## Files

- `m08.json` — cohorts, per-cohort validity, budgets and verdicts (exit 0,
  `work_valid: true`, 0 invalid samples).
- The benchmark-work mutants for this code are recorded in
  `acceptance/M08/remediation/benchmark_mutation_final_9483d1b.json`.

## Results (ms; p95 unless noted; first pass → final)

| Cohort / clock | n | first pass | final (p50 / p95 / p99 / max) | Verdict |
|---|---|---|---|---|
| `_finishWithText_` callback | 20 | 0.012 | 0.005 / 0.010 / 0.014 / 0.014 | pass (S24 ≤ 50) |
| `pasteLastResultAgain_` callback | 20 | 0.078 | 0.043 / 0.104 / 0.117 / 0.117 | pass (S24) |
| `hubPasteText` callback | 20 | 0.103 | 0.085 / 0.111 / 0.199 / 0.199 | pass (S24) |
| `undoLastInsertion_` callback | 20 | 0.029 | 0.039 / 0.045 / 0.051 / 0.051 | pass (S24) |
| undo call → effect (200 ms injected per content read) | 20 | 209.7 | 411.5 / 415.7 / 416.3 / 416.3 | reported |
| `_insertionDone_` on the main thread | 20 | 1.451 | 0.720 / 1.876 / 1.978 / 1.978 | reported |
| AX transaction: enqueue | 60 | 0.003 | 0.002 / 0.003 / 0.006 / 0.006 | pass (S24) |
| AX transaction: worker execution | 60 | 0.386 | 0.313 / 0.397 / 0.503 / 0.503 | reported |
| clipboard transaction: worker execution | 60 | 0.370 | 0.324 / 0.368 / 0.407 / 0.407 | reported |
| settle inside (consumer at 120 ms): readback | 10 | 165.2 | 165.3 / 173.9 / 173.9 / 173.9 | reported |
| settle beyond (250 ms bound): readback | 10 | 273.9 | 267.2 / 298.1 / 298.1 / 298.1 | reported |
| observer: one full tick | 246 | 0.134 | 0.115 / 0.191 / 0.245 / 0.470 | reported |
| observer: re-anchor tick | 24 | 0.133 | 0.144 / 0.253 / 0.366 / 0.366 | reported |
| observer: edit → recorded edit → close | 6 | 5.275 | 6.225 / 7.787 / 7.787 / 7.787 | reported |
| repaste, absent: reconcile + transaction | 20 | 1.245 | 1.582 / 1.942 / 2.040 / 2.040 | reported |
| native AX (warm): validation → write → readback | 29 | 1.855 | 0.634 / 1.111 / 1.534 / 1.534 | pass (PROPOSED-M08-B1 ≤ 150) |
| native AX (cold): first transaction | 6 | 38.06 | 33.52 / 42.61 / 42.61 / 42.61 | pass (PROPOSED-M08-B1) |

All 29 warm native samples were `confirmed` (10 with astral text).

**The one moved clock.** The undo effect clock rose by one injected
delay (≈200 ms): the benchmark sleeps 200 ms in every
`number_of_characters` and `string_for_range` call on the UI cohorts,
and undo now reads the field length once before its write (the proof
that `undone` means the field shrank, review R5). On the native cohort
that read costs about 0.05 ms. The callback clock, the only one with a
canonical budget, is unchanged. Everything else moved within noise; the
observer and repaste clocks sit higher by 0.05–0.7 ms at p95, in line
with battery power and load.

## Budgets

Only S24's UI acknowledgment p95 ≤ 50 ms is canonical. PROPOSED-M08-B1
(native validation → write → readback p95 ≤ 150 ms) is a proposal, not a
specification figure.

## Limits

As in the first-pass README: `n = 20` cohorts report p99 = max; the
observer cadence is compressed (10 ms sleeps); the UI cohorts run the
real AppDelegate methods with `AppHelper.callAfter` deferred and flushed
on the calling thread; the native cohort covers the AX path into an owned
NSTextView only; no real application is measured.
