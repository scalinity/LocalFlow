# MERGED_CROSS_AUDIT_CASE_MAP — summary

Read-only analysis of three declarative corpora for the LocalFlow cross-milestone remediation. All three corpora were audited at `340c566686c7123bfcf721e16160aacabbe0b97d`, and every declaration and merged case is `NOT_RUN`. The machine-readable map is `casemap.json` (same folder). Each `merged_case_id` is numbered within its kind: `XM-C###` for scenario and finding cases, `XM-MH##` for multi-hop, `XM-R##` for race and stateful, `XM-MR##` for metamorphic and `XM-MU##` for mutations.

**Which repository state this reflects.** The branch `xm-local-remediation-20260928` moved from `a613818` to `63f9ef2` while this map was being built. The three new commits edited `test_xm_remediation.py`, `test_xm_store_families.py`, `localflow/app.py`, `localflow/v2/store.py` and `localflow/v2/ui/hub.py`. The witness names, the `covered_by` claims and the producer/consumer callables were all re-verified at `63f9ef2`.

## Totals

| | declarations |
|---|---|
| Audit A | 180 (116 cases, 16 multi-hop, 18 race probes, 14 metamorphic, 16 mutations) |
| Audit C | 155 (125 cases = 87 base + 8 finding repros F001–F008 + 15 multi-hop + 15 stateful; 12 metamorphic; 18 mutations) |
| Audit B | 176 (116 scenario, 15 multi_hop, 15 stateful_race, 12 metamorphic, 18 mutation) |
| **Total source declarations** | **511** |
| Placed in the merged map | **511** (each exactly once; no duplicates, none unplaced) |

| merged kind | count |
|---|---|
| scenario_or_finding (XM-C) | 197 |
| multi_hop (XM-MH) | 32 |
| race_or_stateful (XM-R) | 24 |
| metamorphic (XM-MR) | 21 |
| mutation (XM-MU) | 35 |
| **total merged cases** | **309** |

- **Platform:** 156 portable, 148 appkit_headless (Hub, AppDelegate or InsertionService under `tests/v2/context/run_isolated.py`), 3 native_owned_window, 2 model_backed and 0 human.
- **Execution:** 201 `once` and 108 `distinct`. `distinct` means one invariant and one oracle, but the case needs several runs: both race orderings plus a no-race control, one store copy per dropped table, paired metamorphic worlds, per-variant fixtures, or one run per mutant.
- **Callables:** 311 distinct `exact_producer`/`exact_consumer` callables are named. Every one was verified at `63f9ef2`: 68 are module-level `def`s, and 243 are methods confirmed to sit inside the named class. Only document-only cases use `UNBOUND:<reason>`. Those are the STATUS, VERIFICATION, registry and M15-readiness cases, plus the evidence-hygiene scan.

## Per-driver-group counts

| driver_group | merged | platform | kinds | covered_by existing witness |
|---|---|---|---|---|
| G1_store_schema_migration | 22 | portable=22 | scenario=19, mutation=2, metamorphic=1 | 5 |
| G2_capture_retry_history | 33 | appkit_headless=32, portable=1 | scenario=21, mutation=4, race=3, multi=3, metamorphic=2 | 1 |
| G3_normalization_cleanup_evidence | 42 | appkit_headless=24, portable=18 | scenario=30, metamorphic=5, mutation=3, race=2, multi=2 | 2 |
| G4_transforms | 21 | appkit_headless=12, portable=9 | scenario=14, mutation=3, metamorphic=2, race=1, multi=1 | 3 |
| G5_notes_scratchpad_history_actions | 35 | appkit_headless=34, portable=1 | scenario=22, multi=5, race=4, mutation=4 | 3 |
| G6_learning_review_labels | 42 | portable=27, appkit_headless=14, native_owned_window=1 | scenario=25, multi=9, race=3, mutation=3, metamorphic=2 | 2 |
| G7_splits_export_validator | 29 | portable=29 | scenario=16, metamorphic=4, race=3, multi=3, mutation=3 | 1 |
| G8_profile_usage_analytics | 30 | portable=18, appkit_headless=12 | scenario=11, multi=7, mutation=7, race=3, metamorphic=2 | 2 |
| G9_privacy_deletion_retention | 16 | portable=14, appkit_headless=2 | scenario=13, race=1, metamorphic=1, mutation=1 | 0 |
| G10_hub_publication_ui | 20 | appkit_headless=18, portable=2 | scenario=9, race=4, mutation=4, metamorphic=2, multi=1 | 2 |
| G11_docs_status_runbook | 9 | portable=9 | scenario=9 | 2 |
| G12_native_model_human | 10 | portable=6, model_backed=2, native_owned_window=2 | scenario=8, multi=1, mutation=1 | 0 |

The six G12 portable cases are performance-validity and timing work: the benchmark no-op control, the 10k cohort, the long-note cost, pairwise writer pressure and the mixed-scale workload. Their correctness gates are portable, but their timings only mean something on the reference Mac.

## Unplaceable source declarations

**None.** All 511 were placed. Five placements are judgement calls where one source straddles two merged cases. Each was aliased to the merged case whose distinctive claim it carries, and the overlap is recorded in that case's `note`:
- `LF-CROSS-C017` covers both site and workspace exactness. It is aliased to the workspace case (with CM-C023); its site half overlaps the CM-C022 case.
- `LF-CROSS-C044` and `XF-CASE-086` also touch autosave counting (CM-C044) and repaste activity (CM-C059). Both are aliased to the transform-activity case with CM-C058.
- `XF-CASE-088` does two steps: delete content, then delete usage. It is aliased to CM-C061, and its second step overlaps the usage-deletion multi-hop XM-MH04.
- `LF-CROSS-C060` (support expiry with no publication race) is aliased to CM-H010. `LF-CROSS-H010` is a different case: expiry after the snapshot but before publication, kept separately as XM-MH03.
- `LF-CROSS-MU11` lists transform-Add killers but describes a generic change. It is merged with CM-MU011 (the M09/M14 usage and approval callers). `XF-MUT-005`, which names `_transform_write` specifically, stays a separate mutation.

## Merge decisions that reduce B's own count

B was used as the structural base, and 176 B declarations became 164 merged cases. Some B declarations collapsed together because one driver with one oracle satisfies both. The merged kind is the stronger one, because a race driver also exercises the single ordering its scenario twin asserts:
- CM-C001 and CM-C057 (retry leaves one usage fact) → XM-C020.
- CM-C080 and CM-C099 (profile_evidence lost) → XM-C009.
- Scenario into race: C025→R002, C026→R003, C045→R009, C046→R013, C056→R005, C078→R006, C090→R014.
- Scenario into multi-hop: C052→H012, C062→H009, C089→H013.

B's parallel structure with C held throughout: H001–H015 correspond to LF-CROSS-H001–H015, R001–R015 to S001–S015, and MR/MU 001–012/018 to C's MR/MU pairs. There are three exceptions:
- `LF-CROSS-H009` (delete usage *during* compute) belongs with R006, not with B's H009.
- `LF-CROSS-H010` stays separate.
- `LF-CROSS-MU07` is a different production edit from CM-MU007, as explained below.

## Audit A cases retained without a B alias (125 merged cases), and why B did not replace them

**Finding witnesses preserved as required.** B has no corpus case for any of them. B's CROSS-AUDIT-04 finding has no case, and B has no finding for X03, X04, X05, X08, X09 or X10.

| A witness | merged case | why B does not replace it |
|---|---|---|
| XF-CASE-045 + XF-RACE-003 | XM-C088 (MERGED-X02) | CM-C032 governs target-lease metadata, not pasteboard ownership. |
| XF-CASE-048 | XM-C089 (X02 control) | This is the existing guarded caller, needed as the control. |
| XF-CASE-041 + XF-RACE-001 (+ LF-CROSS-F002) | XM-C075 (MERGED-X03) | CM-R004 is a job snapshot vs a definition edit, which is a different consumer. |
| XF-CASE-078 | XM-C076 (X03 export hop) | The exporter is the consumer; no B case exports after the race. |
| XF-CASE-042 + XF-RACE-002 (+ LF-CROSS-F005) | XM-C077 (MERGED-X04) | B has no stale-form case. |
| XF-CASE-077 | XM-C071 (MERGED-X05) | CM-C086 checks tier agreement, not retention failure. |
| XF-CASE-113 / XF-CASE-102 | XM-C072 / XM-C073 (X05 controls) | These are the negative and positive controls. |
| XF-CASE-105 + XF-RACE-004 (+ LF-CROSS-C010, F006) | XM-C078 (MERGED-X08) | CM-C013 is the M10 snippet/style Add, a different producer from TransformStore. |
| XF-CASE-049 + XF-RACE-005 | XM-C091 (MERGED-X09) | B has no Save Transform case. |
| XF-CASE-050 + XF-RACE-006 | XM-C092 (MERGED-X10) | B has no History Move case. |
| XF-CASE-100 | XM-C183 (STATUS control, MERGED-X16) | This is the historical-benchmark control. XF-CASE-092 itself merges with CM-C101, LF-CROSS-C076 and F008 into XM-C182. |

**Other A-retained cases, grouped by the reason B does not cover them:**
- *No B declaration on the path.*
  - Duplicate terminal callback (XF-001).
  - Old-attempt completion (XF-002 + LF-C005) and old worker generation (XF-007/RACE-012).
  - ASR worker death (XF-005).
  - Cancel before and after the irreversible post (XF-009/RACE-013 and XF-010/RACE-014). CM-C011 cancels at generation instead.
  - Quit lifecycle (XF-011, XF-012/RACE-018, MH-015).
  - Insertion return shape (XF-099) and clipboard restore over an external owner (XF-047).
  - Collector attribution under interleaving (XF-003) and cleanup-only fault (XF-006).
  - Consent timing (XF-013, XF-014, and XF-015 + LF-C004).
  - Mode override (XF-027, XF-028).
  - Context degradation (XF-029, XF-031, XF-032). CM-C024 and CM-C027 use different consumers or single-capture setups.
  - Precedence masking (XF-035), snippet placeholder and collision (XF-038, XF-039), and real-model Clean (XF-026).
  - Definition identity collision (XF-004) and stale panel completion (XF-044).
  - Whole-note transform (XF-052), selection-before-paint (XF-054/RACE-016), search policy (XF-055) and replay (XF-056).
  - Teach with collection off (XF-016 + XF-059), delete during review (XF-018), unchanged correction (XF-060), dictionary composition and rejection (XF-061, XF-062), and counterexample scope (XF-063 + LF-C063).
  - Labeling gates (XF-066, XF-067, XF-068), preferences (XF-069, XF-070, XF-071, XF-072) and candidate popup (XF-090).
  - Split floor and family (XF-073, XF-075), forward-only exposure on a *new assignment* (XF-074), and late family (XF-076 + LF-C065).
  - Destination preservation (XF-080 + LF-C057), provenance downgrade (XF-103 + LF-C066), evidence-store failure (XF-104), legacy import (XF-097), not-started vs unknown (XF-106) and operation-id target reuse (XF-107).
  - Profile origin, signature, fence and time (XF-081, XF-083, XF-084/RACE-009, XF-087).
  - Collector tombstone (XF-017/RACE-007), note-candidate invalidation (XF-019), pending unlink (XF-022) and pure-typed note (XF-115).
  - Diagnostics (XF-093, XF-094, XF-096), error-after-success (XF-089/RACE-017), main-thread dispatch (XF-108), and autosave vs arrival interleaving (XF-RACE-015).
  - Performance (XF-110, XF-111), native layout (XF-091) and late native consumption (XF-046).
- *A-only chains.* XF-MULTIHOP-001 to 016. MH-001 merges LF-C001, and MH-009 merges XF-034. B's multi-hops cover different hop sequences.
- *A-only metamorphic relations.* XF-META-002, 003, 004, 005, 006, 009, 010, 012 and 013. B's MR set has no equivalent perturbation. META-001, 007, 008, 011 and 014 did merge into B relations.
- *A-only mutations.* XF-MUT-001, 002, 004–012, 014, 015 and 016 each describe a production edit that no B mutation names. XF-MUT-003 merged with LF-MU15, and XF-MUT-013 with LF-MU07.

## Audit C cases retained without a B alias (32 merged cases), and why

- **LF-CROSS-F001 (XM-C007) is kept as its own umbrella finding case covering four families: training_memberships, profile_evidence, learning_vocabulary_deltas and usage_facts.** It is deliberately not collapsed into B's profile_evidence-only witness, CM-C080/C099 → XM-C009. Its sub-witnesses LF-C069, C073 and C075 are separate merged cases: XM-C008, XM-C010 and XM-C011.
- LF-CROSS-F002, F005 and F006 merge with A only (XM-C075, XM-C077 and XM-C078), because B has no case for them.
- Other C-specific cases:
  - A late retry cannot resurrect a deleted job (C006).
  - All definition families change after freeze (C020). B covers vocabulary and transform only, separately.
  - A private file re-read after freeze (C021).
  - Missing ownership, and strict accept never downgrading (C023).
  - Capture-app provenance across a retry (C024).
  - Protection mapping through chunked cleanup (C027).
  - Auto-apply is not a human preference (C030).
  - Transform digest or task mismatch (C054). B's C072 is about managed-file digests.
  - Purge-after-render revocation (C036). B's C048 is about deletion.
  - Sampling does not grant a review lease (C050). B's C066 is about mined candidates.
  - Content vs usage retention passes (C051).
  - Five-view readiness/export parity (C064). B's C085 and C086 are single-view.
  - Collection off still runs normally (C083).
  - Deletion with queued private actions (C084).
  - Expiry before publication (H010).
  - Mutation MU07 + XF-MUT-013, "typed ownership stored as dictated", is a different edit from CM-MU007's whole-note-diff bypass.
  - MU15 + XF-MUT-003 and MU18 have no B mutation.

## Merged findings → merged cases

- MERGED-X01: XM-C007 (umbrella, F001), XM-C008, XM-C009 (B's profile_evidence witness), XM-C010, XM-C011, XM-C012 and XM-MU19
- MERGED-X02: XM-C088, XM-C089, XM-MH29 and XM-MU23
- MERGED-X03: XM-C075, XM-C076, XM-MH18 and XM-MU20
- MERGED-X04: XM-C077 and XM-MU24
- MERGED-X05: XM-C071, XM-C072, XM-C073, XM-MH20, XM-MR19 and XM-MU28
- MERGED-X06: XM-C024 and XM-MU16
- MERGED-X07: XM-C021, XM-MH12 and XM-MU17
- MERGED-X08: XM-C078 and XM-MU25
- MERGED-X09: XM-C091, XM-MH23 and XM-MU26
- MERGED-X10: XM-C092, XM-MH22 and XM-MU27
- MERGED-X11: XM-C152 and XM-MU18
- MERGED-X12: XM-C176 and XM-MU21
- MERGED-X13: XM-C177
- MERGED-X14: XM-R10
- MERGED-X15: XM-C119
- MERGED-X16: XM-C182 and XM-C183
- MERGED-X17: XM-C185

## Merged cases already covered by existing fail-first witnesses

These are the witnesses in `tests/v2/crossmilestone/test_xm_remediation.py` and `tests/v2/crossmilestone/test_xm_store_families.py` at `63f9ef2`. All 64 `@case` functions in the two files are referenced in the map.

**Covered (23):**

| merged case | finding | witnesses |
|---|---|---|
| XM-C007 | X01 umbrella | x01a–x01f, x01h–x01j, x01d2 and the siblings. The vocabulary family is governed by M05-AUDIT-18, so its witnesses are now `c_torn_dictionary_stays_detectable_after_repair` and `c_app_refuses_a_torn_dictionary`; the earlier x01g* witnesses were removed at `63f9ef2`. |
| XM-C008 / C009 / C010 / C011 | X01 sub-witnesses A/B/C/D | x01a / x01b / x01c / x01d, plus x01d2 and x01i* for the family |
| XM-C021 | X07 | x07_retries_never_manufacture_dictations_or_words, x07_excluded_latest_attempt_never_falls_back_to_an_older_one, c_ten_independent_captures_reach_the_floor |
| XM-C024 | X06 | x06_history_resolves_the_current_attempt_after_collection_off_retry, c_collection_on_retry_resolves_the_new_manifest |
| XM-C071, XM-C072 | X05 and its negative control | x05 and the four c_* normalization controls |
| XM-C075 | X03 | x03_interleaved_updates_preserve_the_committed_definition, c_sequential_updates… |
| XM-C077 | X04 | x04 ×2, c_fresh_form_update…, local01_selected_transform_fills_its_own_instruction |
| XM-C078 | X08 | x08 Add, x08 toggle sibling, c_refused_add… |
| XM-C088 | X02 | x02_recovery_copy_never_replaces_a_pending_payload, c_recovery_copy_publishes… |
| XM-C091 | X09 | x09_admitted_save_timeout_then_retry_makes_one_note, c_distinct_saves… |
| XM-C092 | X10 | x10 delete phase, x10 copy census, c_unknown_create_never_deletes_the_source |
| XM-C118 | undo keeps user edit | c_service_undo_reverses_exactly_and_keeps_user_edits, x15_hub_undo_refuses_after_a_user_edit |
| XM-C119 | X15 | x15 ×3 |
| XM-R10 | X14 | x14_post_rename_crash…, c_crash_before_rename… |
| XM-C152 | X11 | x11 ×2 plus two controls |
| XM-C176 | X12 | x12 ×2 |
| XM-C177 | X13 | x13_validate_never_runs_filesystem_work_on_the_ui_thread. The reference-Mac timing budget is still open. |
| XM-C182 | X16 | x16_status_separates_current_state_from_historical_record |
| XM-C185 | X17 | x17_m07_obligations_have_stable_runbook_ownership |

**Partially covered only (10).** A witness checks part of the invariant or one hop. The note on each case says what is missing.
- XM-C001: historical schema upgrades. Only jobs rows are checked.
- XM-C012: M14 relations. Receipts are not covered.
- XM-C020: retry leaves one usage fact. Outcome and original instant are not checked.
- XM-C076: the X03 export hop.
- XM-MH12: History retry → profile.
- XM-MH20: the X05 chain to export.
- XM-MH22, XM-MH23 and XM-MH29: the X10, X09 and X02 chains.
- XM-MR19: the normalization-provenance relation.

**Mutations with an existing candidate killer (13).** XM-MU16–MU21 and XM-MU23–MU28 are killed by the X06/X07/X11/X01b/X03/X12 and X02/X04/X08/X09/X10/X05 witnesses. XM-MU34 (XF-MUT-015) is killed by the x07 fact-count assertion.

## Not evaluated here

The branch now also carries `test_xm_privacy.py`, `test_xm_validator.py`, `test_xm_runbook.py` and `test_native_xm_hub.py`, plus `scripts/v2/xm_mutation_check.py`. They are outside the two witness files this map was asked to read, so no case is recorded as covered by them. They plausibly bear on XM-C171/C172 (privacy), XM-C141 (validator), XM-C184 (runbook ids) and the native-window cases. Reading them is the next step if those coverage claims matter.
