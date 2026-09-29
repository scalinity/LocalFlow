# Cross-milestone three-audit remediation (340c566)

State: **CROSS_MILESTONE_REMEDIATION_INCOMPLETE** — branch `xm-local-remediation-20260928`, not pushed and not merged onto `main`. Final production commit `cabc756` (`d6a555d` closed the 17 merged findings; `6a4dcfc` and `cabc756` repair the seven GATE-G06 defects); commits after it change tests and documents only.

Three read-only GPT-6 audits of M01–M14 at `340c566686c7123bfcf721e16160aacabbe0b97d` (A: 8 findings, C: 8 findings + 10 test gaps + 5 design concerns, B: 11 findings + 5 test gaps + 2 design concerns) were merged by root cause into 17 findings (7 high, 9 medium, 1 low), ten proof gates and four policies. The originals are frozen byte-identical under `docs/v2/acceptance/cross-milestone/audits/` (`artifact_map.json` maps every supplied copy and duplicate); the merged ledger is `merged_ledger.json`.

## What was done

- **Reproduction first.** Every merged finding was reproduced on the audited base by a fail-first witness that crosses the real interface (`remediation/regressions_base_340c566.json`, `families_base_340c566.json`, `matrix_base_340c566.json`). All 17 reproduced; three local findings surfaced while reproducing (LOCAL-XM-01 the Transforms editor's instruction, LOCAL-XM-02/03 controls unreachable at the minimum window).
- **Repairs**, one decision each in `remediation/decisions.json` (xm-policy-r1 D01–D16): Store family integrity (refusal with backup; derivable tables rebuilt; a store that lost its version stamp checked against the schema its tables show), guarded Recovery copy, one-op transform revisions and a changed-field editor, cleanup input provenance, History's current attempt, one Your Voice contribution per logical capture, truthful unknown outcomes for Transforms, Save to Scratchpad and History transfers, applied-spelling technical terms, Export Validate off the UI thread with a result bound to its folder, export publication intent and crash reconciliation (including cleanup of exports LocalFlow quit or crashed during, so no copy of recordings outlives them), Undo Approval in the Hub, STATUS current state, and M07 runbook ownership. Per-finding detail: `remediation/adjudications.json`.
- **Independent review.** Seven fresh-context rounds (14, 10, 7, 9, 5, 6, 0 allegations). Every allegation was reproduced by an independently written fail-first witness before any change; the fourth round replaced accreted guards with simpler rules. The seventh round converged under the bar "no correctness, data-loss or privacy defect reachable in single-user use"; its lesser notes are recorded as residuals in `adjudications.json`.
- **Mutation.** `scripts/v2/xm_mutation_check.py`: 69 mutations (60 for the merged findings, XM-MU66–XM-MU74 for the G06 repairs), each an exact edit with a reach marker; all 69 killed on the final tree with a green control (`remediation/final/mutation.json`).

## Evidence on the final tree

| Check | Result | Record |
|---|---|---|
| Cross-milestone regressions | 79/79 | `remediation/final/regressions.json` |
| Store family witnesses and controls | 27/27 | `remediation/final/families.json` |
| GATE-G06 drivers and controls | 89/89 | `remediation/final/g06_a.json` .. `g06_d.json` |
| Mutations | 69/69 killed, control green | `remediation/final/mutation.json` |
| Owned native Hub suite (passive tier) | 6/6, never frontmost | `remediation/final/native_xm_hub.json` |
| Broad sweep (108 files, model-backed excluded) | 105 exit 0, no clipboard change; `test_native_ax` and `test_native_insertion` exit 2 as on the audited base (native tier); `test_m02_remediation_store` injected its unlink fault at `Path.unlink`, which the XM-C016 confined helper no longer calls — moved to `os.unlink` (`26f8afe`, assertions unchanged), 19/19 | `remediation/final/sweep.json`, `recheck_test_m02_remediation_store.json` |
| Compatibility corpora M05, M08, M09, M10, M12, M13, M14 | every case, probe and relation identical to the previous final records except LF-M14-S009, now PASS (its seam fix, `5176133`); M09's one ERROR is the record-graded C121 as before; NOT_RUN are native/benchmark cases run without their records | `remediation/final/corpus_m*.json`, `m09_bench_mutation.json` |

Every record above ran on `cabc756` with the production tree unmodified.

## Performance (POLICY-D01, GATE-G08) — measured after correctness

`docs/v2/benchmarks/20260928-203300-xm-remediation-g06/` on this Mac (Apple M5 Pro, macOS 27.0), both work-valid, on `cabc756`:

- **Dictation-shaped writer wait** beside each background job (M14 benchmark, full scale): profile compute p50 2.37 / p95 76.34 / p99 159.92 / max 160.99 ms (n 93); export p50 0.52 / p95 0.96 / p99 171.58 / max 172.53 ms (n 137); observation mining max 37.23 ms (n 141). The historical ~205/174 ms waits were observations on older code and fixtures.
- **Hub** (M09 benchmark, timing-qualified): construction p95 16.96 ms, first usable result p95 17.94 ms, full pass p95 289.51 ms (budget 1000 ms), History search p95 3.6–52.1 ms across its six query shapes (budget 200 ms) with validated work.
- **Not measured:** dictation end-to-end (needs a human speaker).

## GATE-G06 — re-scoped and closed

The merged corpus is a declarative semantic specification, not a list of programs to write: its 309 cases (511 source declarations) overlap other audit generations, the accepted milestone suites, the cross-milestone regressions, native/model/human qualification and M15. Under the owner's closure rule (2026-09-28) every case is dispositioned, and every unique automatable obligation that touches changed production code or a materially affected seam has executable evidence; aliases, invariants proven by a current accepted production-path suite, and later native/model/M15 obligations name their owner and evidence instead of receiving a bespoke driver.

| Disposition | Cases |
|---|---|
| EXECUTED_PASS | 96 — 58 by G06 drivers, 38 by existing cross-milestone witnesses |
| COVERED_BY_CURRENT_ACCEPTED_SUITE | 159 |
| DEFERRED_NATIVE / MODEL / M15 | 3 / 2 / 8 |
| NOT_APPLICABLE_WITH_REASON | 1 (XM-MU22: the mutant's target guard does not exist in `_worker`; the invariant is proven at the real guards) |
| DRIVER_REQUIRED, not mandatory | 40 |
| ALIAS_OF_EXECUTED_CASE, DEFERRED_HUMAN, EXECUTED_FAIL | 0 |

A DRIVER_REQUIRED case is mandatory before merge when its path runs through one of the 69 functions the remediation changed, or its oracle reads behaviour a G06 repair changed; none of the 40 remaining ones does. Manifest, rule and per-case bindings: `remediation/gates/g06_disposition.json`, `g06_summary.md`, `g06_changed_functions.txt`.

The 58 mandatory drivers (`tests/v2/crossmilestone/test_xm_g06_{a,b,c1,c2,d}.py`, with controls: 89 cases — A 18, B 20, C1 20, C2 21, D 10 — all PASS on cabc756) reproduced seven defects, each repaired and witnessed by a mutant:

- **XM-C137** History served an artifact of the wrong role as the job's final (`history_queries._job_artifacts`).
- **XM-C016** the artifact purge unlinked, and payload reads opened, corrupt locators outside the managed root (`store.py`).
- **XM-C005** a lost jobs or artifacts table was recreated empty while referrers survived (`_CORE_DEPENDENTS`).
- **XM-C106** History Copy and Paste Again could publish a final purged after its detail rendered (`hub.py`).
- **XM-C108** Replay reported `no_audio_artifact` for purged audio instead of the detail's reason (`hub.py`).
- **XM-R18** a retry committing attempt 2 while History read attempt 1 left the Hub on attempt 1 (`HubState.job_changed`).
- **XM-C020** push-to-talk minted the capture instant three times, so the usage fact trailed History's capture time by the mic-open latency (`startDictation`).

Open product question from the corpus: **XM-C042** — a retry carries no target and inserts at the current focus (posted_unverified), which conflicts with that case's "no write into another app" oracle. It stays DRIVER_REQUIRED until the owner decides whether a retry may insert at the current focus (related to POLICY-D03).

## Open — why the campaign is incomplete

- **GATE-G02:** 33 requirements — 24 bound to tests and production branches, 5 partial, 4 future (`gates/binding_summary.md`).
- **Interface union:** 78 rows from A ∪ C ∪ B (119 source rows) — 70 bound, 5 partial, 3 unbound (`gates/ifunion_summary.md`).
- **GATE-G07:** the native Hub suite's active tier, real keyboard and focus are not run.
- **GATE-G08:** dictation end-to-end not measured.
- **GATE-G10 (separately owned):** M11's integrated record is not all-green (one misdirected review, fourteen output-limit fallbacks); M07's long-prompt trial and real-text stratum are pending as M07-V001/V002 — V002 is blocked because no private tool yet presents the 749 legacy candidates for review.
- **Legacy-transcript review tool (a separate pre-M15 qualification-support workstream):** approved to build after this remediation merges and before M15 qualification, never on this branch. It is local-only with no network, API or provider; it reads the original retained examples read-only and never mutates evidence by reviewing it; it shows source/raw beside cleaned/result with a keyboard-first Accept / Incorrect / Ambiguous / Skip flow and an optional error category; progress is resumable and safe to interrupt, with explicit reviewed/unreviewed counts; it exports the judgments and provenance M07 qualification needs; no transcript content is committed to Git. M07-V002 stays blocked until the tool exists and the review is done.
- **Policies:** POLICY-D02 (AI-powered Your Voice) not implemented; POLICY-D03 (History Paste Again destination) is an open product decision; POLICY-D04 holds as threat-model policy.

## Do not

- Do not push or merge this branch while the campaign is incomplete.
- Do not build the legacy-transcript review tool on this branch.
- Do not mark any runbook check passed; every check is Not run as committed.
- Do not start M15, M16, Quiet Editorial or AI-powered Your Voice interpretation.
- Do not read the historical M14 benchmark figures in `STATUS.json` (`historical_implementation`) as current performance.
