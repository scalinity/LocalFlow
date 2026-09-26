# M08 remediation benchmark — 2026-09-26 (reference Mac)

Work-valid insertion timings (benchmark schema 2) for the M08 remediation.
The historical fixture benchmark of 2026-09-22
(`../20260922-131238-m08/m08.json`) is unchanged and describes other code.

## Provenance

- Code: `git archive a50032c` (production `846fd2c`) in a disposable copy,
  with `scripts/v2/benchmark_m08.py` overlaid from the working tree
  (sha256 `19541c2c…a6f608`, recorded in both JSON files). No other file
  differed from the archived commit.
- Mac: Apple M5 Pro (Mac17,8), 18 CPUs, 48 GiB, macOS 27.0 (26A428), arm64,
  AC power; Python 3.14.7, PyObjC 12.2.1; load average 2.0/3.2/3.5 (another
  session was active on the machine).
- Desktop isolation: every portable cohort ran under
  `tests/v2/context/run_isolated.py` (0 Accessibility calls blocked, 0 events,
  the general pasteboard redirected to a private one). The native cohort
  ran natively and reached only its own helper process by pid; no key event
  was posted and only a private named pasteboard existed on that path.

## Files

- `m08.json` — cohorts, per-cohort validity, budgets and verdicts (exit 0).
- `benchmark_mutation.json` — BMUT-01..06 against the same SHA and benchmark
  bytes (control green, 6/6 killed).
- `native_cohort_at_4260fe3.json` — the native cohort run on `4260fe3`
  (production `b2cb243`, before `846fd2c`): every sample invalid —
  `SystemInsertionHost.is_settable` answered False for a settable text view,
  so the AX method was never chosen and the transaction tried to post a key
  event (refused by the cohort). Evidence that the native witness rejects.

## Rerun

    # portable + native (native spawned outside isolation, own helper only)
    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/benchmark_m08.py <outdir> --native \
        [--code-rev <sha> --overlay scripts/v2/benchmark_m08.py]
    # benchmark-work mutants (disposable copies, never the live checkout)
    .venv/bin/python scripts/v2/m08_benchmark_mutation_check.py \
        --rev <sha> --output <file> --scale 0.25 [--benchmark-from-worktree]

Exit codes: 0 valid and every declared gate met; 1 valid, a gate failed;
2 WORK INVALID (a sample lacks its witness; no speed verdict); 3 harness
error. The mutation checker counts only 2 (or 1 with valid work) as a kill.

## Validity (checked per sample before any verdict)

Witnesses come from the synthetic world's own logs
(`tests/v2/insertion/m08_world.py`) and the helper's AppKit state, never from
a result object alone: unique field contents and payloads per sample; the
exact physical effect on the bound field (count and bytes); the validation of
the ACTUAL bound element and owner pid inside the transaction; pre-read and
readback both on the destination; publish → post → consume ordering and the
restored generation (or, on contending samples, the user copy surviving);
the queue thread; the operation id; no Accessibility call on the calling
thread for UI entry points. Injected delays were conserved: 200 ms per AX
content read appears in every UI `to_effect`/`to_worker_end` clock and in no
callback clock; the delayed consumer appears in the readback clock and not in
the enqueue clock.

## Results (ms; n, p50 / p95 / p99 / max)

| Cohort | Clock | n | p50 | p95 | p99 | max | Verdict |
|---|---|---|---|---|---|---|---|
| ui_finish_with_text | `_finishWithText_` callback | 20 | 0.005 | 0.012 | 0.015 | 0.015 | pass (S24 ≤ 50) |
| ui_recovery_paste_again | `pasteLastResultAgain_` callback | 20 | 0.033 | 0.078 | 0.079 | 0.079 | pass (S24) |
| ui_history_paste_text | `hubPasteText` callback | 20 | 0.057 | 0.103 | 0.103 | 0.103 | pass (S24) |
| ui_undo_last_insertion | `undoLastInsertion_` callback | 20 | 0.021 | 0.029 | 0.029 | 0.029 | pass (S24) |
| ui_recovery_paste_again | call → witnessed effect (delay injected) | 20 | 614.4 | 618.1 | 618.7 | 618.7 | reported |
| ui_finish_with_text | call → worker end (queued behind earlier calls) | 20 | 6129.8 | 11647.7 | 12262.2 | 12262.2 | reported |
| ui_insertion_done_callback | `_insertionDone_` on the main thread | 20 | 0.943 | 1.451 | 2.147 | 2.147 | reported (not an S24 path) |
| ax_transaction | enqueue (submit) | 60 | 0.002 | 0.003 | 0.005 | 0.005 | pass (S24) |
| ax_transaction | queue wait | 60 | 0.003 | 0.006 | 0.009 | 0.009 | reported |
| ax_transaction | worker execution | 60 | 0.318 | 0.386 | 0.432 | 0.432 | reported |
| ax_transaction | validation (inside) | 60 | 0.014 | 0.025 | 0.034 | 0.034 | reported |
| clipboard_transaction | worker execution | 60 | 0.323 | 0.370 | 0.387 | 0.387 | reported |
| clipboard_transaction | snapshot / publish / post / readback / restore p95 | 60 | — | 0.005 / 0.002 / 0.005 / 0.006 / 0.002 | — | — | reported |
| clipboard_settle_inside | readback (consumer at 120 ms) | 10 | 161.8 | 165.2 | 165.2 | 165.2 | reported |
| clipboard_settle_beyond | readback = deliberate settle (250 ms bound) | 10 | 270.4 | 273.9 | 273.9 | 273.9 | reported |
| observer_tick | one full tick | 246 | 0.067 | 0.134 | 0.179 | 0.195 | reported |
| observer_reanchor_tick | tick with one bounded window read | 24 | 0.086 | 0.133 | 0.138 | 0.138 | reported |
| observer_stop | edit → recorded bounded edit → close | 6 | 2.823 | 5.275 | 5.275 | 5.275 | reported |
| undo | on the queue thread | 20 | 0.017 | 0.031 | 0.034 | 0.034 | reported |
| repaste_absent | reconcile + transaction on the queue | 20 | 1.032 | 1.245 | 1.504 | 1.504 | reported |
| repaste_present | reconcile, no effect | 20 | 0.072 | 0.101 | 0.113 | 0.113 | reported |
| cold_process | import + setup (fresh process) | 12 | 45.9 | 48.9 | 48.9 | 48.9 | reported |
| cold_process | first AX / clipboard transaction | 12 | 0.474 / 0.432 | 0.535 / 0.761 | — | — | reported |
| native_ax (warm) | validation → AX write → AX readback | 29 | 0.783 | 1.855 | 3.953 | 3.953 | pass (PROPOSED-M08-B1 ≤ 150) |
| native_ax_cold | first transaction, fresh process + helper | 6 | 32.4 | 38.1 | 38.1 | 38.1 | pass (PROPOSED-M08-B1) |

All 29 warm native samples were `confirmed` (10 with astral text; owned range
exact in UTF-16 units; the helper's own `NSTextView` text equal to the
expected bytes). In the cold native samples, validation dominates (p50
22.9 ms: the first Accessibility round trips to a fresh process).

## Budgets

Only S24's UI acknowledgment p95 ≤ 50 ms ("no model or disk work on UI
callback") is canonical. PROPOSED-M08-B1 (native validation → write →
readback p95 ≤ 150 ms, a share of S24's 0.75 s p50 end-to-end target for
short dictations) is a proposal, not a specification figure. Timings of the
world double's internals measure M08's own code over a Python host and carry
no budget.

## Benchmark-work mutants (`benchmark_mutation.json`, scale 0.25)

Control (unmutated copy, same benchmark bytes): exit 0, work valid, imports
from the copy. Each mutant applied (anchor matched once, file hash changed),
imported from its copy, and was rejected with exit 2 (work invalid):

| Mutant | First witness that rejected it |
|---|---|
| BMUT-01 remove target validation | validation of the actual target not witnessed |
| BMUT-02 no-op insertion | result posted_unverified; no effect |
| BMUT-03 skip clipboard publication | the late paste did not land the right text |
| BMUT-04 skip destination readback | pre-read and readback not both witnessed |
| BMUT-05 bypass the queue (inline on the caller) | transaction ran on MainThread; AX calls on the calling thread |
| BMUT-06 remove the restore ownership check | the contending user copy was restored over |

## Limits

- `n = 20` cohorts report p99 = max. The observer cadence is compressed
  (10 ms sleeps instead of 500 ms); the work per tick is unchanged.
- The UI cohorts drive the real AppDelegate methods on the calling thread
  with `AppHelper.callAfter` deferred and flushed on that thread; no
  NSApplication run loop runs.
- The native cohort covers the AX path into an owned NSTextView only. The
  clipboard paste path on a real destination needs a synthetic ⌘V to the
  desktop and stays in the manual runbook; no real application is measured.
