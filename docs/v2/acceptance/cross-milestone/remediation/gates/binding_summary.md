# GATE-G02: requirement -> test -> production branch binding

Repository: `<repo>`. Branch: `xm-local-remediation-20260928`. Head: `a613818` at the start, `684303c` at the end (concurrent commits).

This was a read-only pass: nothing was run, and nothing in the repository was edited. Every binding in `binding.json` comes from these sources:

- `docs/v2/registry.json` (33 LF-R / 22 EV)
- the E08 suite rows
- each tracked `test_*.py`: its docstring, case names (`def test_*` / `@case` / `CHECKS` / `VARIANTS`) and `localflow` imports
- production definitions, confirmed with `git grep`
- the sweep's own rules: `scripts/v2/m09_test_sweep.py` and `acceptance/M14/remediation/sweep_final_3ede837.json`

A suite name in a docstring was never counted as coverage.

## Counts

| | bound | bound with later qualification | partial | unbound | future |
|---|---|---|---|---|---|
| Requirements (33) | 25 (24 + LF-R28) | 4 | 0 | 0 | 4 |
| Suites (22) | 17 | 2 (EV-04 human, EV-18 model) | 0 | 0 | 3 |

- 19 suites have at least one tracked test file. Three have none: EV-16, EV-17 and EV-22.
- The 188 binding rows break down as: 144 portable_automated, 8 native_owned_window, 8 model_backed, 20 human and 12 unbound.

## Future (M15/M16), never counted as covered

- **LF-R23:** qualified model adapters (EV-16, EV-22). The precursors are capability-manifest honesty and identity-bound qualification.
- **LF-R24:** end-to-end performance (EV-16, EV-22). The per-milestone `benchmark_m*.py` scripts are stage benchmarks, not EV-16.
- **LF-R26:** packaging, upgrade and final acceptance (EV-17). Sleep/wake and store upgrades are tested only under EV-04 and EV-03.
- **LF-R33:** comparator and challenge evaluation (EV-22). `test_short_command_scoring.py` is text-only.

## Final dispositions of the five requirements that were partly bound

Every automatable source-path gap was closed with a test on the real production path; what remains is named with its later gate. Full records: `binding.json` → each requirement's `g02_final`.

| Requirement | Disposition | Owner / suite | Current tests (added here in bold) | Production path | Remaining |
|---|---|---|---|---|---|
| LF-R04 capture, hotkeys, mic switching, crash recovery | BOUND_WITH_LATER_HUMAN_QUALIFICATION | M03 / EV-04 | **`test_xm_remediation.py::r04_mic_switch_opens_the_configured_input`**, **`r04_silence_warnings_are_reported`**; lifecycle, journal and stuck-overlay suites | `audio.py Recorder._resolve_device → Recorder.start`; `app.py AppDelegate._finishCapture` (near-silence / dead-tail warnings) | real microphones and device switching: M03-V006 |
| LF-R25 offline operation, private storage, deletion | BOUND_WITH_LATER_NATIVE_QUALIFICATION | M02 / EV-03, EV-19, EV-21; EV-17 | store, collector, export, validator and privacy suites; **`r25_no_network_client_imports`** | `store.py Store`; `training.py EvidenceCollector`; `curation/export.py`; no network client import anywhere under `localflow/` | whole-app offline operation at runtime: EV-17 (M16) |
| LF-R27 existing behaviour and language coverage | BOUND_WITH_LATER_MODEL_QUALIFICATION | M03/M04; EV-04, EV-17 | `test_stuck_overlay.py`, `test_m04_review_round.py::test_R13_spanish_accented_numbers`, `test_cleanup.py` (model-backed) | `app.py` watchdog, `hotkey.py`, `cleanup.py`, `v2/normalize` | ASR language coverage needs the real model: M15; EV-17 (M16) |
| LF-R28 contracts, handoffs, traceable verification | FULLY_BOUND | EV-01 | `test_registry.py`, `test_xm_runbook.py`, `x16`, `x17`, **`r28_handoff_and_status_are_fresh`** (the STATUS production commit is in HEAD; the handoff names the same state and commit) | `build_registry.py`; `STATUS.json current_state`; `handoffs/CROSS-MILESTONE.md`; `VERIFICATION.html` | none here; the M16 sign-off is its own later requirement |
| LF-R29 pre-decode hint capabilities, one selector | BOUND_WITH_LATER_MODEL_QUALIFICATION | M05 / EV-18 | `test_hint_selection.py`, `test_audio_fidelity.py`, `test_vocabulary_pipeline.py`, `test_context_pipeline.py` | `vocabulary.py RelevantVocabularySelector/HintSet`; `capabilities.py`; app hint freeze | a qualified decoder adapter and acoustic strata: M15 |

## Harness-only, fake, static, dead or mislabelled tests

- **Harness-only cases.** These assert on test oracles or documents, not production:
  - `test_transform_remediation.py` `f05_oracle_*` (3 cases), which check `test_prompt_engineer_cases.judge`
  - `test_m04_remediation.py::test_18_oracle_mutations_are_caught`
  - `test_m04_review_round.py::test_R20_corpus_component_oracle_is_exact`
  - `test_baseline_manifest.py::test_historical_manifest_record_is_frozen`
  - all of `test_xm_runbook.py`
  - `test_xm_remediation.py` `x16`/`x17`
- **Harness-weak:** `test_profile.py::test_no_profile_injection`. It runs `normalize()` twice, both after `compute()`, with context `None`, and never reaches cleanup. The real-coordinator proof is `test_m14_remediation.py::f27_profile_never_reaches_the_real_coordinator_pipeline`.
- **Fake counterpart:** `test_worker_protocol.py` pairs the real supervisor with `fake_worker.py`. Its "Metal" faults are string tokens, and no real Metal fault is ever produced.
- **Static only:** `test_m02_app_wiring.py` is an AST call-site check of `app.py`.
- **Fake I/O:** `test_baseline_probe.py` injects fake ASR and cleanup objects. Real inference is M01-V008.
- **Vacuous-pass risk:** in `test_xm_privacy.py` (committed 3d824ac during this pass), `step()` swallows exceptions. PASS needs only "no leak and no session error", and there is no floor on `records_scanned`.
- **Dead reference:** `acceptance/M01/results.json:31` cites `test_no_private_files_in_repo_docs_or_tests`. The case is now `test_no_private_files_in_repository`.
- **Mislabels:**
  - `test_insights_service.py` calls itself "EV-13", but it covers analytics, which is EV-15.
  - `test_sampling.py` calls itself "EV-19.4", but it covers sampling, which is EV-20.

## Qualification problems

- **Model-backed suites inside the portable sweep.** `test_structure.py` and `test_literal.py` load Qwen3-4B with no skip, but they are missing from the sweep's `MODEL_BACKED` tuple. In the M14 sweep they ran as "portable" (51.7 s and 13.5 s, 0 ok-lines).
- **Tracking moved during the analysis.** At the start (`a613818`), `test_xm_privacy.py`, `test_xm_runbook.py` and `test_xm_validator.py` were untracked, so the sweep (which uses `git ls-files`) would have skipped them. A concurrent session then committed them in `3d824ac` (head now `684303c`), so the sweep now picks them up. That session also left `tests/v2/crossmilestone/test_native_xm_hub.py` untracked and `localflow/v2/store.py` modified; neither was analysed here.
- **Corpus runners never run in the sweep.** The corpus runners and drivers (M05–M14) are tracked but are not `test_*.py` files. Their evidence exists only as recorded JSON.
- **`test_cleanup.py` excluded whole.** The sweep excludes it entirely, including its portable `--basic` tier.

## Model-, native- and human-gated requirements

- **Model-backed.** The tracked list is `test_cleanup.py`, `test_worker_live.py`, `test_live_pipeline.py`, `test_prompt_engineer_cases.py` and `test_fidelity.py`; `test_structure.py` and `test_literal.py` also load a model.
  - LF-R05 (worker live)
  - LF-R10/R11 (fidelity, literal, structure)
  - LF-R18 (Prompt Engineer semantics)
  - LF-R27 (V1 cleanup control)
  - LF-R30 (live pipeline)
- **Native, owned window.**
  - LF-R09 (`test_native_ax.py`, needs an AX grant, exits 2 without one)
  - LF-R12 (`test_native_insertion.py`, same)
  - LF-R13/R19/R20/R21/R22 (passive owned Hub windows in the M12/M13/M14 native suites)
  - LF-R14/R15 (`test_native_m10_panes.py`)
  - The ACTIVE tier needs the owner's go-ahead.
- **Human.** These are attributed by milestone ownership; the subject of each individual check was not reviewed.

  | Requirement(s) | Human checks |
  |---|---|
  | LF-R01 | M01-V001..V011 |
  | LF-R02, R03, R30 | M02-V001..V009 |
  | LF-R04 | M03-V004..V008 |
  | LF-R05 | M03-V002, V003 |
  | LF-R06, R07 | M04-V001..V003 |
  | LF-R08, R29 | M05-V001..V003 |
  | LF-R09 | M06-V001..V004 |
  | LF-R12 | M08-V001..V008 |
  | LF-R13 | M09-V001..V007 |
  | LF-R14, R15, R16 | M10-V001..V004 |
  | LF-R17, R18 | M11-V001..V006 |
  | LF-R19 | M12-V001..V005 |
  | LF-R20 | M13-V001..V005 |
  | LF-R21 | M14-V006 |
  | LF-R22 | M14-V002 |
  | LF-R31 | M14-V003, V004 |
  | LF-R32 | M14-V005 |

  LF-R10/R11 have **no** human id. The M07 runbook section is empty while `native-m07-long-prompt-cleanup-trial` is pending and M07-AC04 is `partial_automated` (MERGED-X17).

## Cross-milestone suites and the requirements they touch

| Suite | Status | Requirements |
|---|---|---|
| `test_xm_remediation.py` | tracked | R08, R12, R13, R17, R19, R20, R21, R22, R28 (docs only), R30, R32 |
| `test_xm_store_families.py` | committed 3d824ac | R03, R08, R14, R15, R17, R20, R21, R22, R31, R32 |
| `test_xm_privacy.py` | committed 3d824ac | R02, R25, R30 |
| `test_xm_runbook.py` | committed 3d824ac, document-only | R28 |
| `test_xm_validator.py` | committed 3d824ac | R25, R32 |
