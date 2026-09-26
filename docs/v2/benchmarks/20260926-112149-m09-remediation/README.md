# M09 remediation benchmark, first pass — 2026-09-26 (reference Mac)

The rewritten, work-valid M09 benchmark (`scripts/v2/benchmark_m09.py`)
at full size on the frozen first pass. It is kept because it failed:
every cohort's work was valid, but three timing budgets were exceeded,
which led to the History pair fix in `0083466`. The final run is
`../20260926-120724-m09-remediation-final/`; the historical fixture runs
(`../20260922-*-m09/`) describe the pre-remediation code.

## Provenance

- Code: the committed checkout at `4166806` (production identical to
  `272f3d9`), no tracked file modified.
- Mac: Apple M5 Pro (Mac17,8), macOS 27.0, Python 3.14.7. Load average
  at start 3.49 / 3.61 / 4.48: the independent reviewer and other
  sessions were running on the machine.
- Under `tests/v2/context/run_isolated.py` (no Accessibility, key events
  or general pasteboard).
- Population: 50,000 synthetic jobs (516 carry the hit token), 5,000
  legacy analytics rows, 1,000 legacy log pairs, 1,000 Training
  examples, 2,000 events.

## Result

`work_valid: true`, `timing_qualified: false` (exit 1).

| Cohort | p95 (ms) | Budget | Verdict |
|---|---|---|---|
| History text hit / miss / app / mode | 38.3 / 31.9 / 27.6 / 42.0 | 200 | pass |
| History browse (no filter, mixed sources) | 1500.7 | 200 | **fail** |
| History legacy mode | 1350.9 | 200 | **fail** |
| Shell full pass (all ten views) | 1633.4 | 1000 | **fail** |

Cause: each returned legacy log pair was hydrated by its own lookup on
`artifacts.parent_artifact_id`, which has no index, so every pair
scanned the artifacts table; and Undated pairs — which sort after every
dated row — were fetched even when dated rows already filled the limit.
The quick (5k) run had hidden it (browse 64 ms).
