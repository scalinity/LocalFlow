# Cross-milestone three-audit remediation (340c566)

State: **CROSS_MILESTONE_REMEDIATION_COMPLETE_PENDING_MANUAL_MODEL_VERIFICATION** — branch `xm-local-remediation-20260928`, merged onto `main`. Final production commit `a33f681` (`d6a555d` closed the 17 merged findings; `6a4dcfc` and `cabc756` repair the seven GATE-G06 defects; `a33f681` implements the final owner decisions); commits after it change tests and documents only. The source remediation is complete; native, manual, model and human qualification remain pending and are never implied passed (`remediation/gates/qualification_ledger.md`).

Three read-only GPT-6 audits of M01–M14 at `340c566686c7123bfcf721e16160aacabbe0b97d` (A: 8 findings, C: 8 findings + 10 test gaps + 5 design concerns, B: 11 findings + 5 test gaps + 2 design concerns) were merged by root cause into 17 findings (7 high, 9 medium, 1 low), ten proof gates and four policies. The originals are frozen byte-identical under `docs/v2/acceptance/cross-milestone/audits/` (`artifact_map.json` maps every supplied copy and duplicate); the merged ledger is `merged_ledger.json`.

## What was done

- **Reproduction first.** Every merged finding was reproduced on the audited base by a fail-first witness that crosses the real interface (`remediation/regressions_base_340c566.json`, `families_base_340c566.json`, `matrix_base_340c566.json`). All 17 reproduced; three local findings surfaced while reproducing (LOCAL-XM-01 the Transforms editor's instruction, LOCAL-XM-02/03 controls unreachable at the minimum window).
- **Repairs**, one decision each in `remediation/decisions.json` (xm-policy-r1 D01–D16): Store family integrity, guarded Recovery copy, one-op transform revisions and a changed-field editor, cleanup input provenance, History's current attempt, one Your Voice contribution per logical capture, truthful unknown outcomes for Transforms, Save to Scratchpad and History transfers, applied-spelling technical terms, Export Validate off the UI thread with a result bound to its folder, export publication intent and crash reconciliation, Undo Approval in the Hub, STATUS current state, and M07 runbook ownership. Per-finding detail: `remediation/adjudications.json`.
- **GATE-G06 drivers** reproduced seven more defects, each repaired (below).
- **Final owner decisions** (2026-09-28), implemented in `a33f681`:
  - **Retry authority (XM-C042).** A retry keeps its original capture's provenance — job, family, capture instant, destination identity — but inserts only into a destination its own action captured (`hubRetryJob(job_id, target_snapshot)`), revalidated by M08. Without one the result is kept as `saved_not_inserted`: nothing is inserted into whatever has focus and nothing is copied.
  - **History Paste Again (POLICY-D03)** uses explicit one-shot destination acquisition. Invoking the command does not authorize incidental foreground focus. LocalFlow steps aside, waits for a deliberate user destination selection, captures a fresh M08 target authority from that selection, revalidates source and destination, and inserts through the canonical M08 service. The click counts only if the app whose window was clicked is the app in front; Esc, a 30-second timeout, quit, deleting the source, reopening the Hub or a newer Paste Again end the pick with nothing pasted, and the Hub never comes forward while a dictation is in flight. The Recovery menu's Paste Last Result Again and normal push-to-talk are unchanged.
  - **Interface union.** `store.write_failed` carries the exception type only; the Dictionary panel, the JSON import, the Hub's collection setting and the consent menu toggles read an admitted store timeout as outcome unknown, never as failed.
  - **GATE-G02.** The missing automatable parts were closed: microphone selection and the silence warnings (LF-R04), a no-network-client import guard (LF-R25), handoff and STATUS freshness (LF-R28).
- **Independent review.** Ten fresh-context rounds (14, 10, 7, 9, 5, 6, 0, 3, 1, 0 allegations). Every allegation was reproduced by an independently written fail-first witness before any change. Rounds 8 and 9 reviewed the final decisions and found four defects in the Paste Again pick (a destination taken from any click, a reopened or superseded pick, a busy source check, a self-ended pick reopening the Hub mid-dictation), all repaired; round 10 converged under the bar "no correctness, data-loss or privacy defect reachable in single-user use". Lesser notes are residuals in `adjudications.json`.
- **Mutation.** `scripts/v2/xm_mutation_check.py`: 88 mutations (60 for the merged findings, XM-MU66–MU74 for the G06 repairs, XM-MU75–MU93 for the final decisions and review repairs), each an exact edit with a reach marker; all 88 killed with a green control.

## Evidence on the final tree

| Check | Result | Record |
|---|---|---|
| Cross-milestone regressions | 86/86 | `remediation/final/regressions.json` |
| Store family witnesses and controls | 27/27 | `remediation/final/families.json` |
| GATE-G06 drivers and controls, with the XM-C042 regressions | 93/93 | `remediation/final/g06_a.json` .. `g06_d.json` |
| POLICY-D03 Paste Again | 15/15 | `remediation/final/paste_again.json` |
| Mutations | 88/88 killed, control green | `remediation/final/mutation.json` |
| Owned native Hub suite (passive tier) | 6/6, never frontmost | `remediation/final/native_xm_hub.json` |
| Broad sweep (109 files, model-backed excluded) | 107 exit 0; `test_native_ax` and `test_native_insertion` exit 2 as on the audited base (native tier) | `remediation/final/sweep.json` |
| Compatibility corpora M05, M08, M09, M10, M12, M13, M14 | all 1,563 case, probe and relation results identical to the previous final records; M09's one ERROR is the record-graded C121; NOT_RUN are native/benchmark cases run without their records | `remediation/final/corpus_m*.json`, `m09_bench_mutation.json` |

The corpora, native suite, sweep and benchmarks ran on `a33f681`; the regressions, Paste Again suite and mutation gate on `00e8cad` (tests only after `a33f681`); the production tree was unmodified in every run. Milestone suites and corpus drivers whose expectations encoded the two replaced behaviours were adapted to the owner decisions without weakening their oracles: a retry is given an explicit target where one delivery must stay observable, and a Paste Again is followed by the user's click (`m08_world.pick_destination`).

The sweep flagged two files as changing the real clipboard. Run alone and measured directly (general pasteboard change count 852 → 852 for `test_m03_review_round.py` and `test_structure.py`), neither does: the changes came from activity outside the tests during that window.

## Performance (POLICY-D01, GATE-G08) — measured after correctness

`docs/v2/benchmarks/20260928-230400-xm-remediation-final-decisions/` on this Mac (Apple M5 Pro, macOS 27.0), both work-valid, on `a33f681`:

- **Dictation-shaped writer wait** beside each background job (M14 benchmark, full scale): profile compute p50 2.23 / p95 72.77 / p99 154.30 / max 161.18 ms (n 92); export p50 0.52 / p95 1.10 / p99 165.08 / max 171.25 ms (n 133); observation mining max 2.07 ms (n 142). The historical ~205/174 ms waits were observations on older code and fixtures.
- **Hub** (M09 benchmark, timing-qualified): construction p95 16.21 ms, first usable result p95 17.16 ms, full pass p95 270.60 ms (budget 1000 ms), History search p95 3.5–50.1 ms across its six query shapes (budget 200 ms) with validated work.
- **Not measured:** human-speaker end-to-end dictation (pending before M15; no synthetic figure stands in for it).

## Gates

| Gate | State |
|---|---|
| G01, G03, G04, G05, G09 | closed |
| G02 requirement binding | closed: 25 bound, 4 bound with later qualification (LF-R04 human, LF-R25 native, LF-R27 and LF-R29 model), 4 future, none partial (`gates/binding_summary.md`) |
| Interface union | 77 bound, 1 bound with later qualification (XM-IF-077, the M15 gate), none partial or unbound (`gates/ifunion_summary.md`) |
| G06 merged corpus | closed: 309 cases — 97 executed, 159 covered, 13 deferred, 1 not applicable, 39 future hardening specs, DRIVER_REQUIRED 0 (`gates/g06_summary.md`) |
| G07 native Hub | closed for the source remediation, with remaining native qualification |
| G08 end-to-end / contention | closed for the source remediation, with remaining human / M15 performance qualification |
| G10 | pending manual / model qualification |

### GATE-G06 — exhaustive semantic accounting

The merged corpus is a declarative semantic specification, not a list of programs to write: its 309 cases (511 source declarations) overlap other audit generations, the accepted milestone suites, the cross-milestone regressions, native/model/human qualification and M15. Every case is dispositioned. A new driver is required only when a case asserts a unique invariant whose truth this remediation may have materially changed and no current executable evidence proves it; merely traversing changed code is not enough. `FUTURE_HARDENING_SPEC` keeps a fully specified driver — invariant, proposed driver, why it is not required here, owning future phase — that is valuable but not needed to close this campaign.

| Disposition | Cases |
|---|---|
| EXECUTED_PASS | 97 — 59 by G06 drivers (including the XM-C042 regressions), 38 by existing cross-milestone witnesses |
| COVERED_BY_CURRENT_ACCEPTED_SUITE | 159 |
| DEFERRED_NATIVE / MODEL / HUMAN / M15 | 3 / 1 / 1 / 8 |
| NOT_APPLICABLE_WITH_REASON | 1 (XM-MU22: the mutant's target guard does not exist in `_worker`; the invariant is proven at the real guards) |
| FUTURE_HARDENING_SPEC | 39 |
| DRIVER_REQUIRED, ALIAS_OF_EXECUTED_CASE, EXECUTED_FAIL | 0 |

Defects the G06 drivers reproduced, each repaired and witnessed by a mutant:

- **XM-C137** History served an artifact of the wrong role as the job's final (`history_queries._job_artifacts`).
- **XM-C016** the artifact purge unlinked, and payload reads opened, corrupt locators outside the managed root (`store.py`).
- **XM-C005** a lost jobs or artifacts table was recreated empty while referrers survived (`_CORE_DEPENDENTS`).
- **XM-C106** History Copy and Paste Again could publish a final purged after its detail rendered (`hub.py`).
- **XM-C108** Replay reported `no_audio_artifact` for purged audio instead of the detail's reason (`hub.py`).
- **XM-R18** a retry committing attempt 2 while History read attempt 1 left the Hub on attempt 1 (`HubState.job_changed`).
- **XM-C020** push-to-talk minted the capture instant three times, so the usage fact trailed History's capture time by the mic-open latency (`startDictation`).

## Pending qualification (never implied passed)

`remediation/gates/qualification_ledger.md` holds each obligation with its case ids and owner:

- **Native:** G07's active tier (real keyboard and focus, Insights, Review / A-B, Your Voice, active deletion), the real-click Paste Again pick, XM-C196, XM-C121, XM-C197.
- **Manual:** the runbook checks in `docs/v2/VERIFICATION.html`, including M03-V006 (real microphones).
- **Model:** M07-V001; M07-V002 (blocked until the private legacy-transcript review tool exists); M11's integrated record (one misdirected review, fourteen output-limit fallbacks; GATE-G10); ASR language coverage (LF-R27) and a qualified decoder adapter (LF-R29).
- **Human / M15:** human-speaker end-to-end dictation timing (XM-C191, XM-C192, XM-C194, XM-C195, XM-MH32) and M15's own qualification.
- **Policies:** POLICY-D02 (AI-powered Your Voice) not implemented; POLICY-D04 holds as threat-model policy.

## Next, as separate work

- **Legacy-transcript review tool** (a pre-M15 qualification-support workstream, after this remediation is on `main`): local-only with no network, API or provider; reads the original retained examples read-only and never mutates evidence by reviewing it; shows source/raw beside cleaned/result with a keyboard-first Accept / Incorrect / Ambiguous / Skip flow and an optional error category; resumable and safe to interrupt, with explicit reviewed/unreviewed counts; exports the judgments and provenance M07 qualification needs; no transcript content is committed to Git. M07-V002 stays blocked until the tool exists and the review is done.

## Do not

- Do not mark any runbook check, deferred native case or pending qualification passed; every runbook check is Not run as committed.
- Do not start M15, M16, Quiet Editorial, AI-powered Your Voice interpretation or an installed-app rollout.
- Do not read the historical M14 benchmark figures in `STATUS.json` (`historical_implementation`) as current performance.
