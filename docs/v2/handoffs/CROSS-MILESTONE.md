# Cross-milestone three-audit remediation (340c566)

State: **CROSS_MILESTONE_REMEDIATION_INCOMPLETE** — branch `xm-local-remediation-20260928`, not merged onto `main`. Final production commit `d6a555d`; commits after it change tests, the mutation catalog and documents only.

Three read-only GPT-6 audits of M01–M14 at `340c566686c7123bfcf721e16160aacabbe0b97d` (A: 8 findings, C: 8 findings + 10 test gaps + 5 design concerns, B: 11 findings + 5 test gaps + 2 design concerns) were merged by root cause into 17 findings (7 high, 9 medium, 1 low), ten proof gates and four policies. The originals are frozen byte-identical under `docs/v2/acceptance/cross-milestone/audits/` (`artifact_map.json` maps every supplied copy and duplicate); the merged ledger is `merged_ledger.json`.

## What was done

- **Reproduction first.** Every merged finding was reproduced on the audited base by a fail-first witness that crosses the real interface (`remediation/regressions_base_340c566.json`, `families_base_340c566.json`, `matrix_base_340c566.json`). All 17 reproduced; three local findings surfaced while reproducing (LOCAL-XM-01 the Transforms editor's instruction, LOCAL-XM-02/03 controls unreachable at the minimum window).
- **Repairs**, one decision each in `remediation/decisions.json` (xm-policy-r1 D01–D16): Store family integrity (refusal with backup; derivable tables rebuilt; a store that lost its version stamp checked against the schema its tables show), guarded Recovery copy, one-op transform revisions and a changed-field editor, cleanup input provenance, History's current attempt, one Your Voice contribution per logical capture, truthful unknown outcomes for Transforms, Save to Scratchpad and History transfers, applied-spelling technical terms, Export Validate off the UI thread with a result bound to its folder, export publication intent and crash reconciliation (including cleanup of exports LocalFlow quit or crashed during, so no copy of recordings outlives them), Undo Approval in the Hub, STATUS current state, and M07 runbook ownership. Per-finding detail: `remediation/adjudications.json`.
- **Independent review.** Seven fresh-context rounds (14, 10, 7, 9, 5, 6, 0 allegations). Every allegation was reproduced by an independently written fail-first witness before any change; the fourth round replaced accreted guards with simpler rules. The seventh round converged under the bar "no correctness, data-loss or privacy defect reachable in single-user use"; its lesser notes are recorded as residuals in `adjudications.json`.
- **Mutation.** `scripts/v2/xm_mutation_check.py`: 60 mutations, each an exact edit with a reach marker; all 60 killed on the final tree with a green control (`remediation/final/mutation.json`).

## Evidence on the final tree

| Check | Result | Record |
|---|---|---|
| Cross-milestone regressions | all pass | `remediation/final/regressions.json` |
| Store family witnesses and controls | all pass | `remediation/final/families.json` |
| Mutations | 60/60 killed | `remediation/final/mutation.json` |
| Owned native Hub suite (passive tier) | 6/6, never frontmost | `remediation/final/native_xm_hub.json` |
| Broad sweep (103 files, model-backed excluded) | 99 exit 0; `test_native_ax` and `test_native_insertion` exit 2 as on the audited base (native tier); `test_xm_remediation` failed only on the pending STATUS check; `test_native_xm_hub` failed inside the sweep and passes alone | `remediation/final/sweep.json`, `recheck_*.json` |
| Compatibility corpora M05, M08, M09, M10, M12, M13, M14 | every portable, stateful and metamorphic case as in each milestone's final record; deltas are record-graded native/benchmark cases run without their records (NOT_RUN); M14 C063/C158 drivers follow D13 (commit b296408) | `remediation/final/corpus_m*.json`, `m09_bench_mutation.json` |

The sweep flagged five files as changing the real clipboard. Rerun alone, and measured directly before and after each (general pasteboard change count 800 → 800 for `test_structure.py`, `test_m12_remediation.py` and `test_xm_remediation.py`), none does: the changes came from activity outside the tests during that window.

## Performance (POLICY-D01, GATE-G08) — measured after correctness

`docs/v2/benchmarks/20260928-180600-xm-remediation-final/` on this Mac (Apple M5 Pro, macOS 27.0), both work-valid:

- **Dictation-shaped writer wait** beside each background job (M14 benchmark, full scale): profile compute p50 2.16 / p95 61.46 / p99 141.65 / max 159.19 ms (n 92); export p50 0.54 / p95 1.25 / p99 157.53 / max 161.63 ms (n 131); observation mining max 33.49 ms (n 141). The historical ~205/174 ms waits were observations on older code and fixtures.
- **Hub** (M09 benchmark, timing-qualified): construction p95 21.49 ms, first usable result p95 22.44 ms, full pass p95 277.04 ms (budget 1000 ms), History search p95 23–38 ms with validated work.
- **Not measured:** dictation end-to-end (needs a human speaker).

## Open — why the campaign is incomplete

- **GATE-G06:** the merged corpus `remediation/gates/casemap.json` places all 511 source declarations of the three corpora into 309 merged cases; the committed witnesses execute the finding reproductions and their controls, and the other merged cases have no driver yet.
- **GATE-G02:** 33 requirements — 24 bound to tests and production branches, 5 partial, 4 future (`gates/binding_summary.md`).
- **Interface union:** 78 rows from A ∪ C ∪ B (119 source rows) — 70 bound, 5 partial, 3 unbound (`gates/ifunion_summary.md`).
- **GATE-G07:** the native Hub suite's active tier, real keyboard and focus are not run.
- **GATE-G08:** dictation end-to-end not measured.
- **GATE-G10 (separately owned):** M11's integrated record is not all-green (one misdirected review, fourteen output-limit fallbacks); M07's long-prompt trial and real-text stratum are pending as M07-V001/V002 — V002 is blocked because no private tool yet presents the 749 legacy candidates for review.
- **Policies:** POLICY-D02 (AI-powered Your Voice) not implemented; POLICY-D03 (History Paste Again destination) is an open product decision; POLICY-D04 holds as threat-model policy.

## Do not

- Do not merge this branch onto `main` while the campaign is incomplete.
- Do not mark any runbook check passed; every check is Not run as committed.
- Do not start M15, M16, Quiet Editorial or AI-powered Your Voice interpretation.
- Do not read the historical M14 benchmark figures in `STATUS.json` (`historical_implementation`) as current performance.
