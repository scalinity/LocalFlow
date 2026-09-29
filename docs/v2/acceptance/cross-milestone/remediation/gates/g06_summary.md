# GATE-G06 — merged corpus disposition

The merged corpus (`gates/casemap.json`) is a declarative semantic specification: 511 source declarations from the three audits' corpora, merged into 309 cases. Much of it overlaps other audit generations, accepted milestone suites, the cross-milestone regressions, native/model/human qualification and M15. **309 declarative cases do not mean 309 bespoke executable drivers.**

Closure rule (owner decision, 2026-09-28): Every merged corpus case is explicitly dispositioned. Every unique automatable obligation that touches changed production code or a materially affected producer-to-consumer seam has executable evidence. Duplicate aliases, invariants already proven by a current accepted production-path suite, and explicitly later native/model/human/M15 obligations need no new bespoke driver, but name their exact owner and evidence.

Mandatory drivers: A DRIVER_REQUIRED case is mandatory before merge when (a) its exact producer or consumer runs through one of the 69 functions the remediation changed (340c566..d6a555d), or (b) its oracle reads behaviour a GATE-G06 repair changed (d6a555d..cabc756, each listed with that behaviour). Both lists: gates/g06_changed_functions.txt. Rule (b) is semantic because the G06 repairs sit on paths nearly every dictation runs (startDictation, _worker); a repair's own reproducing driver and mutant witness it. Mandatory cases carry an executed driver in tests/v2/crossmilestone/test_xm_g06_*.py; the others stay DRIVER_REQUIRED with their driver specification.

Machine-readable manifest: `gates/g06_disposition.json` (every case, its category, reason, bindings, producer/consumer, oracle argument, owner gate or driver specification). Code: `cabc756`.

## Totals

| Category | Cases |
|---|---|
| COVERED_BY_CURRENT_ACCEPTED_SUITE | 159 |
| DEFERRED_M15 | 8 |
| DEFERRED_MODEL | 2 |
| DEFERRED_NATIVE | 3 |
| DRIVER_REQUIRED | 40 |
| EXECUTED_PASS | 96 |
| NOT_APPLICABLE_WITH_REASON | 1 |
| ALIAS_OF_EXECUTED_CASE | 0 — duplicates were merged into their case by the case map; each case's source declarations are its `aliases` in the case map |
| DEFERRED_HUMAN / EXECUTED_FAIL | 0 |
| **Total** | 309 |

## Executed by a G06 driver (58 cases, all PASS on the final tree)

| Case | Driver | Note |
|---|---|---|
| XM-C001 | `test_xm_g06_a.py::g06_xm_c001_older_stores_keep_domain_rows` |  |
| XM-C002 | `test_xm_g06_a.py::g06_xm_c002_failed_backup_refuses_untouched` |  |
| XM-C003 | `test_xm_g06_a.py::g06_xm_c003_entrypoints_back_up_and_validator_opens_no_db` |  |
| XM-C004 | `test_xm_g06_a.py::g06_xm_c004_killed_migration_reopens_and_upgrades` |  |
| XM-C005 | `test_xm_g06_a.py::g06_xm_c005_lost_core_table_is_refused` | Driver reproduced a defect (a lost jobs/artifacts table was recreated empty while referrers survived); repaired with new _CORE_DEPENDENTS probes. |
| XM-C016 | `test_xm_g06_a.py::g06_xm_c016_corrupt_locator_never_touches_outside` | Driver reproduced a defect (artifact purge and payload reads followed corrupt locators outside the managed root); repaired in store.py (confined no-follow unlink and read). |
| XM-C018 | `test_xm_g06_a.py::g06_xm_c018_nonregular_nodes_refused_without_blocking` |  |
| XM-C020 | `test_xm_g06_c2.py::g06_xm_c020_mh06_retry_is_one_logical_dictation`, `test_xm_g06_c2.py::g06_xm_c020_mh06_control_clean_capture` | Driver reproduced a defect (push-to-talk minted the capture instant three times, the in-memory one after the mic opened, so the usage fact trailed jobs.captured_at_utc and a retry moved it); repaired in AppDelegate.st... |
| XM-C032 | `test_xm_g06_a.py::g06_xm_c032_worker_death_keeps_audio_never_a_transcript` |  |
| XM-C033 | `test_xm_g06_a.py::g06_xm_c033_unverified_is_never_confirmed` |  |
| XM-C034 | `test_xm_g06_a.py::g06_xm_c034_refused_target_is_saved_not_failed` |  |
| XM-C040 | `test_xm_g06_a.py::g06_xm_c040_revoked_lease_grants_no_authority` |  |
| XM-C193 | `test_xm_g06_a.py::g06_xm_c193_noop_and_wrong_cohort_are_invalid` |  |
| XM-MH06 | `test_xm_g06_c2.py::g06_xm_c020_mh06_retry_is_one_logical_dictation`, `test_xm_g06_c2.py::g06_xm_c020_mh06_control_clean_capture` |  |
| XM-MH17 | `test_xm_g06_a.py::g06_xm_mh17_one_dictation_one_identity_everywhere` |  |
| XM-MU15 | `test_xm_g06_a.py::g06_xm_mu15_export_confines_its_own_open` |  |
| XM-C043 | `test_xm_g06_b.py::g06_xm_c043_raw_route_never_claims_cleanup` |  |
| XM-C066 | `test_xm_g06_b.py::g06_xm_c066_identical_text_keeps_ownership` |  |
| XM-C067 | `test_xm_g06_b.py::g06_xm_c067_cleanup_fault_is_reason_coded` |  |
| XM-C070 | `test_xm_g06_b.py::g06_xm_c070_collection_off_invents_nothing` |  |
| XM-C076 | `test_xm_g06_b.py::g06_xm_c076_race_then_export_carries_executed_definition` |  |
| XM-R07 | `test_xm_g06_b.py::g06_xm_r07_history_action_during_load_refuses` |  |
| XM-MH18 | `test_xm_g06_b.py::g06_xm_mh18_transform_mode_end_to_end` |  |
| XM-MH20 | `test_xm_g06_b.py::g06_xm_mh20_failed_retention_never_exports_raw_as_input` |  |
| XM-R21 | `test_xm_g06_b.py::g06_xm_r21_edit_after_snapshot_keeps_frozen_task` |  |
| XM-MR19 | `test_xm_g06_b.py::g06_xm_mr19_normalization_provenance_relation` |  |
| XM-MU12 | `test_xm_g06_b.py::g06_xm_mu12_approve_unknown_then_retry_is_one` |  |
| XM-C094 | `test_xm_g06_c1.py::g06_xm_c094_note_delivery_receipt_is_labeled_note` |  |
| XM-MH22 | `test_xm_g06_c1.py::g06_xm_mh22_delayed_move_never_resurrects_source_in_profile` |  |
| XM-MH23 | `test_xm_g06_c1.py::g06_xm_mh23_unknown_save_opens_its_one_note` |  |
| XM-MH29 | `test_xm_g06_c1.py::g06_xm_mh29_copy_callers_respect_pending_and_outcome_is_honest` |  |
| XM-R05 | `test_xm_g06_c1.py::g06_xm_r05_reordered_history_never_redirects_actions` |  |
| XM-R06 | `test_xm_g06_c1.py::g06_xm_r06_teach_after_real_retry_is_stale` |  |
| XM-C104 | `test_xm_g06_c1.py::g06_xm_c104_applied_transform_is_the_delivered_final` |  |
| XM-C106 | `test_xm_g06_c1.py::g06_xm_c106_purge_after_render_revokes_content_actions` | Driver reproduced a defect (Copy/Paste Again could publish a final purged after the detail rendered); repaired with the Hub live-final check. |
| XM-C107 | `test_xm_g06_c1.py::g06_xm_c107_old_attempt_search_opens_current_final` |  |
| XM-C108 | `test_xm_g06_c1.py::g06_xm_c108_unavailable_replay_stops_and_reports_reason` | Driver reproduced a defect (Replay reported no_audio_artifact for purged audio); repaired: the detail reason is shown. |
| XM-C109 | `test_xm_g06_c1.py::g06_xm_c109_transform_of_moved_note_never_revives_job` |  |
| XM-MH13 | `test_xm_g06_c2.py::g06_xm_mh13_transformed_final_teach_refused`, `test_xm_g06_c2.py::g06_xm_mh13_cleaned_render_then_transform_commits` |  |
| XM-R18 | `test_xm_g06_c2.py::g06_xm_r18_retry_commits_while_history_read_is_held` | Driver reproduced a defect (a retry commit left the Hub on the earlier attempt); repaired: the commit reloads History (HubState.job_changed). |
| XM-C110 | `test_xm_g06_c2.py::g06_xm_c110_collection_off_hub_teach` |  |
| XM-C116 | `test_xm_g06_c2.py::g06_xm_c116_mr08_unapproved_evidence_never_changes_output` |  |
| XM-MH09 | `test_xm_g06_c2.py::g06_xm_mh09_certified_edit_to_scoped_next_job` |  |
| XM-MH14 | `test_xm_g06_c2.py::g06_xm_mh14_mid_flight_approval_applies_from_next_job` |  |
| XM-MH24 | `test_xm_g06_c2.py::g06_xm_mh24_collection_off_teach_approved_in_scope` |  |
| XM-MR08 | `test_xm_g06_c2.py::g06_xm_c116_mr08_unapproved_evidence_never_changes_output` |  |
| XM-C123 | `test_xm_g06_c2.py::g06_xm_c123_typed_only_note_contributes_nothing` |  |
| XM-C125 | `test_xm_g06_c2.py::g06_xm_c125_span_corrections_never_whole_gold` |  |
| XM-MH11 | `test_xm_g06_c2.py::g06_xm_mh11_mixed_note_mines_only_the_dictated_pair` |  |
| XM-C137 | `test_xm_g06_d.py::g06_xm_c137_wrong_role_never_history_final` | Driver reproduced a defect (History served a wrong-role manifest artifact as the final); repaired in history_queries._job_artifacts (role must match its slot; corrupt data fails closed, POLICY-D04). |
| XM-C144 | `test_xm_g06_d.py::g06_xm_c144_exclusion_reason_parity` |  |
| XM-C145 | `test_xm_g06_d.py::g06_xm_c145_late_family_is_reason_coded` |  |
| XM-MH01 | `test_xm_g06_d.py::g06_xm_mh01_c146_exposure_forward_old_package_historical` |  |
| XM-C146 | `test_xm_g06_d.py::g06_xm_mh01_c146_exposure_forward_old_package_historical` |  |
| XM-MH05 | `test_xm_g06_d.py::g06_xm_mh05_older_generation_never_republishes_excluded` |  |
| XM-C154 | `test_xm_g06_d.py::g06_xm_c154_speech_measures_exclude_typed_and_snippet_words` |  |
| XM-MH10 | `test_xm_g06_d.py::g06_xm_mh10_note_capture_counts_dictated_words_only` |  |
| XM-MH12 | `test_xm_g06_d.py::g06_xm_mh12_retry_agrees_across_consumers` |  |

## Executed by an existing cross-milestone witness (38 cases)

- XM-C007: `test_xm_store_families.py::x01a_lost_memberships_never_return_exposed_family_to_holdout`, `test_xm_store_families.py::x01b_lost_profile_evidence_never_keeps_dead_private_text`, `test_xm_store_families.py::x01c_lost_deltas_never_let_undo_destroy_a_user_edit`, `test_xm_store_families.py::x01d_lost_usage_facts_never_keep_deleted_usage_in_aggregates`, `test_xm_store_families.py::x01e_lost_candidates_never_forget_a_permanent_rejection`, `test_xm_store_families.py::x01f_lost_labels_never_readmit_background_speech`, `test_xm_store_families.py::c_torn_dictionary_stays_detectable_after_repair`, `test_xm_remediation.py::c_app_refuses_a_torn_dictionary`, `test_xm_store_families.py::x01h_lost_transform_rows_never_drop_a_user_definition`, `test_xm_store_families.py::x01h2_lost_revisions_never_present_history_as_none`, `test_xm_store_families.py::x01h3_lost_transform_registry_revision_never_restarts`, `test_xm_store_families.py::x01h4_lost_candidates_never_orphan_recorded_judgments`, `test_xm_store_families.py::x01i_lost_snippets_are_not_an_empty_registry`, `test_xm_store_families.py::x01i2_lost_style_rules_are_not_an_empty_registry`, `test_xm_store_families.py::x01i3_lost_profile_registry_revision_never_restarts`, `test_xm_store_families.py::x01j_lost_assignments_keep_the_assignment_history`, `test_xm_store_families.py::x01d2_lost_aggregates_never_hide_recorded_usage`, `test_xm_store_families.py::c_lost_judgments_only_shrink_exports`, `test_xm_store_families.py::c_lost_sampling_decisions_redraw_identically`, `test_xm_store_families.py::c_fresh_store_opens_empty`, `test_xm_store_families.py::c_intact_current_store_reopens_without_repair`
- XM-C008: `test_xm_store_families.py::x01a_lost_memberships_never_return_exposed_family_to_holdout`
- XM-C009: `test_xm_store_families.py::x01b_lost_profile_evidence_never_keeps_dead_private_text`
- XM-C010: `test_xm_store_families.py::x01c_lost_deltas_never_let_undo_destroy_a_user_edit`
- XM-C011: `test_xm_store_families.py::x01d_lost_usage_facts_never_keep_deleted_usage_in_aggregates`, `test_xm_store_families.py::x01d2_lost_aggregates_never_hide_recorded_usage`, `test_xm_store_families.py::x01i_lost_snippets_are_not_an_empty_registry`, `test_xm_store_families.py::x01i2_lost_style_rules_are_not_an_empty_registry`, `test_xm_store_families.py::x01i3_lost_profile_registry_revision_never_restarts`
- XM-C012: `test_xm_store_families.py::x01a_lost_memberships_never_return_exposed_family_to_holdout`, `test_xm_store_families.py::x01c_lost_deltas_never_let_undo_destroy_a_user_edit`
- XM-C024: `test_xm_remediation.py::x06_history_resolves_the_current_attempt_after_collection_off_retry`, `test_xm_remediation.py::c_collection_on_retry_resolves_the_new_manifest`
- XM-C182: `test_xm_remediation.py::x16_status_separates_current_state_from_historical_record`
- XM-C185: `test_xm_remediation.py::x17_m07_obligations_have_stable_runbook_ownership`
- XM-MR01: `test_xm_remediation.py::x07_retries_never_manufacture_dictations_or_words`, `test_xm_remediation.py::c_ten_independent_captures_reach_the_floor`
- XM-MU16: `test_xm_remediation.py::x06_history_resolves_the_current_attempt_after_collection_off_retry`
- XM-MU19: `test_xm_store_families.py::x01b_lost_profile_evidence_never_keeps_dead_private_text`
- XM-C071: `test_xm_remediation.py::x05_failed_normalized_retention_is_never_a_complete_task`
- XM-C072: `test_xm_remediation.py::c_unchanged_normalization_keeps_raw_input_complete`, `test_xm_remediation.py::c_ledger_failure_with_unchanged_text_keeps_raw_input`
- XM-C075: `test_xm_remediation.py::x03_interleaved_updates_preserve_the_committed_definition`, `test_xm_remediation.py::c_sequential_updates_each_preserve_their_definition`
- XM-C077: `test_xm_remediation.py::x04_stale_form_never_reverses_a_newer_opt_out`, `test_xm_remediation.py::x04_unknown_update_then_stale_refill_never_reenables_auto`, `test_xm_remediation.py::local01_selected_transform_fills_its_own_instruction`, `test_xm_remediation.py::c_fresh_form_update_changes_only_the_edited_field`
- XM-C078: `test_xm_remediation.py::x08_admitted_add_timeout_is_unknown_and_one_transform_results`, `test_xm_remediation.py::c_refused_add_saves_nothing_and_a_fixed_form_adds_once`
- XM-C176: `test_xm_remediation.py::x12_older_refresh_never_repaints_over_a_validate_result`, `test_xm_remediation.py::x12_validate_result_binds_to_its_destination_across_pane_switch`
- XM-C177: `test_xm_remediation.py::x13_validate_never_runs_filesystem_work_on_the_ui_thread`
- XM-MU20: `test_xm_remediation.py::x03_interleaved_updates_preserve_the_committed_definition`
- XM-MU21: `test_xm_remediation.py::x12_older_refresh_never_repaints_over_a_validate_result`
- XM-MU24: `test_xm_remediation.py::x04_stale_form_never_reverses_a_newer_opt_out`, `test_xm_remediation.py::x04_unknown_update_then_stale_refill_never_reenables_auto`
- XM-MU25: `test_xm_remediation.py::x08_admitted_add_timeout_is_unknown_and_one_transform_results`
- XM-MU28: `test_xm_remediation.py::x05_failed_normalized_retention_is_never_a_complete_task`
- XM-C088: `test_xm_remediation.py::x02_recovery_copy_never_replaces_a_pending_payload`, `test_xm_remediation.py::c_recovery_copy_publishes_when_nothing_is_pending`
- XM-C091: `test_xm_remediation.py::x09_admitted_save_timeout_then_retry_makes_one_note`, `test_xm_remediation.py::c_distinct_saves_make_distinct_notes`
- XM-C092: `test_xm_remediation.py::x10_unknown_source_deletion_is_reported_and_retry_settles`, `test_xm_remediation.py::c_unknown_create_never_deletes_the_source`
- XM-MU23: `test_xm_remediation.py::x02_recovery_copy_never_replaces_a_pending_payload`
- XM-MU26: `test_xm_remediation.py::x09_admitted_save_timeout_then_retry_makes_one_note`
- XM-MU27: `test_xm_remediation.py::x10_unknown_source_deletion_is_reported_and_retry_settles`
- XM-C118: `test_xm_remediation.py::c_service_undo_reverses_exactly_and_keeps_user_edits`, `test_xm_remediation.py::x15_hub_undo_refuses_after_a_user_edit`
- XM-C119: `test_xm_remediation.py::x15_hub_offers_undo_approval_for_the_rendered_candidate`, `test_xm_remediation.py::x15_hub_undo_unknown_outcome_then_retry_is_one_undo`, `test_xm_remediation.py::x15_hub_undo_refuses_after_a_user_edit`, `test_native_xm_hub.py::undo_approval_button_undoes_the_chosen_rule`
- XM-C021: `test_xm_remediation.py::x07_retries_never_manufacture_dictations_or_words`, `test_xm_remediation.py::c_ten_independent_captures_reach_the_floor`
- XM-R10: `test_xm_remediation.py::x14_post_rename_crash_is_recognized_not_lost_or_relabeled`, `test_xm_remediation.py::c_crash_before_rename_restores_and_the_retry_completes`
- XM-C152: `test_xm_remediation.py::x11_renamed_entry_never_relabels_historical_speech`, `test_xm_remediation.py::x11_missing_frozen_record_is_unrecorded_never_relabeled`, `test_xm_remediation.py::c_disabled_rule_no_longer_counts`, `test_xm_remediation.py::c_unrenamed_entry_cites_its_applied_term`
- XM-MU17: `test_xm_remediation.py::x07_retries_never_manufacture_dictations_or_words`, `test_xm_remediation.py::x07_excluded_latest_attempt_never_falls_back_to_an_older_one`
- XM-MU18: `test_xm_remediation.py::x11_renamed_entry_never_relabels_historical_speech`
- XM-MU34: `test_xm_remediation.py::x07_retries_never_manufacture_dictations_or_words`, `m13_drivers.py::d_retry_provenance`, `m13_drivers.py::d_retry_provenance`, `m13_drivers.py::d_worker_retry`

## Covered by a current accepted suite (159 cases)

Each names its exact test, current evidence, producer and consumer and why its oracle proves the invariant (manifest fields `bindings`, `evidence`, `producer`, `consumer`, `oracle_argument`).

| Case | Bound to |
|---|---|
| XM-C006 | `test_m12_remediation.py::l02_populated_m12_table_loss_is_refused` |
| XM-C013 | `test_legacy_import_boundary.py::test_incomplete_tail_then_completion_imports_once`, `test_legacy_import_boundary.py::test_pre_remediation_partial_tail_is_completed_not_lost`, `test_import.py::test_appended_log_prefix_reconciliation`, `test_import.py::test_log_identity_and_unknown_dates` |
| XM-C014 | `test_m02_remediation_store.py::test_close_admission_and_drain`, `test_m02_remediation_store.py::test_caller_timeout_is_not_cancellation` |
| XM-C015 | `test_m14_remediation.py::ir05_operation_id_reused_on_another_target_refuses` |
| XM-C017 | `test_m10_remediation.py::r01_link_swap_after_listing_not_followed`, `test_xm_privacy.py::session`, `test_m12_remediation.py::r01b_read_refuses_absolute_and_dir_symlink_and_final_symlink` |
| XM-C019 | `test_m10_remediation.py::r01_child_directory_symlink_not_followed`, `test_m10_remediation.py::r01_link_swap_after_listing_not_followed`, `m10_drivers_c.py::no_fallback_scan`, `m10_drivers_c.py::display_name_not_path` |
| XM-C025 | `test_m03_remediation_app.py::test_09_t0_rate_and_gaps_survive_a_t1_retry`, `m13_drivers.py::d_clock`, `m13_drivers.py::d_retry_provenance` |
| XM-C028 | `test_m03_review_round.py::test_R4_scan_and_retry_claim_exclusively` |
| XM-C030 | `test_m03_remediation_supervisor.py::test_13_expected_identity_matrix`, `test_m03_remediation_supervisor.py::test_03_old_finalizer_cannot_fail_new_request`, `m13_drivers.py::d_stale_attempt`, `m08_corpus_runner.py::f01_c05` |
| XM-R01 | `test_worker_protocol.py::test_stale_generation_echo_resolves_as_fault`, `test_worker_protocol.py::test_stale_generation_result_discarded`, `test_m03_remediation_supervisor.py::test_13_expected_identity_matrix`, `test_m03_remediation_supervisor.py::test_03_old_finalizer_cannot_fail_new_request` |
| XM-C035 | `test_lifecycle.py::test_cancel_during_processing_blocks_late_insert` |
| XM-R02 | `test_m08_remediation.py::test_a15_cancel_after_publish_prevents_post`, `test_m08_remediation.py::test_a15_cancel_after_validation_prevents_ax_write`, `m08_corpus_runner.py::f14_c03` |
| XM-R03 | `m08_corpus_runner.py::f14_c04`, `m08_corpus_runner.py::f14_c05` |
| XM-C036 | `m13_drivers.py::d_repaste_policy`, `m13_drivers.py::d_repaste_policy`, `m13_drivers.py::d_repaste_policy`, `m13_drivers.py::d_repaste_counted`, `m13_drivers.py::d_repaste_counted`, `m13_drivers.py::d_repaste_counted` |
| XM-C037 | `m08_corpus_runner.py::f01_c02` |
| XM-C038 | `test_transform_remediation_native.py::f06_same_app_other_document_not_replaced`, `test_selection_capture_m06_seam.py::test_seam_other_window_with_equal_title_refuses_strict_accept` |
| XM-C041 | `test_m08_remediation.py::test_a04_strict_needs_native_window_element`, `test_m08_remediation.py::test_a04_strict_needs_recorded_surroundings`, `test_transform_remediation.py::f06_plain_dictation_contract_unchanged`, `test_transform_remediation_native.py::f06_unreadable_selection_is_not_replacement_proof` |
| XM-C184 | `test_xm_runbook.py::g03_ids_well_formed_unique_and_in_their_section`, `test_xm_runbook.py::g03_numbering_is_stable_per_milestone`, `test_xm_runbook.py::g03_storage_namespace_and_stale_rule` |
| XM-MR06 | `test_m03_remediation_app.py::test_09_t0_rate_and_gaps_survive_a_t1_retry`, `m13_drivers.py::d_retry_provenance`, `m13_drivers.py::d_retry_provenance` |
| XM-MR18 | `test_m14_remediation.py::f17_approval_retry_after_unknown_outcome_reconciles`, `test_m14_remediation.py::f17_label_retry_with_one_operation_is_one_revision`, `test_m14_remediation.py::f17_split_retry_with_one_operation_is_one_version`, `test_m14_remediation.py::ir05_operation_id_reused_on_another_target_refuses` |
| XM-MU06 | `test_m03_remediation_app.py::test_09_t0_rate_and_gaps_survive_a_t1_retry`, `m13_drivers.py::d_retry_provenance` |
| XM-MU10 | `test_m08_remediation.py::test_a01_clipboard_post_bound_to_validated_field`, `test_m08_remediation.py::test_a01_write_after_validation_goes_only_to_validated_field`, `test_m08_remediation.py::test_a01_same_app_other_window_after_validation` |
| XM-MU35 | `test_m14_remediation.py::f28_benchmark_rejects_a_noop_component` |
| XM-C044 | `m10_drivers.py::canonical_equivalents`, `m10_drivers.py::canonical_equivalents`, `m14_drivers_c.py::c078_equivalent_scope` |
| XM-C047 | `test_context_snapshot.py::test_scope_context_drives_vocabulary_snapshot`, `m05_corpus_runner.py::h_text`, `m05_corpus_runner.py::h_text`, `m05_corpus_runner.py::h_text`, `m05_corpus_runner.py::h_text`, `m05_corpus_runner.py::h_text`, `m10_drivers.py::missing_site` |
| XM-C049 | `test_context_pipeline.py::test_secure_field_pipeline_retains_no_content`, `test_context_snapshot.py::test_ac01_secure_field_retains_no_content`, `test_context_snapshot.py::test_denied_app_never_read`, `test_transform_remediation_native.py::f06_secure_field_classified_before_any_content_read` |
| XM-C052 | `test_m06_remediation.py::test_a12_downstream_sealed_with_parent_link`, `test_context_pipeline.py::test_ac05_late_context_downstream_not_predecode`, `test_m06_remediation.py::test_a05_snapshot_transitively_immutable` |
| XM-C053 | `test_m06_review_round.py::test_r3_deferred_widening_keeps_the_captured_profile`, `test_m10_remediation.py::r12_deferred_widening_adds_no_workspace_registry`, `test_m10_remediation.py::r12_builder_failure_leaves_no_half_tuple`, `m10_drivers.py::failed_widening_tuple` |
| XM-C054 | `m10_drivers_c.py::style_in_flight`, `m10_drivers_c.py::snippet_in_flight`, `m10_drivers_c.py::m11_between_jobs`, `test_vocabulary_pipeline.py::test_ac03_live_midflight_edit`, `test_m06_remediation.py::test_a07_projection_uses_captured_entries_only`, `test_m10_remediation.py::r11_manifest_edit_after_freeze_never_reaches_the_job` |
| XM-C055 | `test_m10_remediation.py::r11_manifest_edit_after_freeze_never_reaches_the_job`, `test_m10_remediation.py::r01_link_swap_after_listing_not_followed`, `m10_drivers_c.py::cache_deletion` |
| XM-C056 | `m10_drivers.py::override_once`, `test_m10_remediation.py::c13_healthy_override_consumed_once`, `m10_drivers.py::cancelled_capture`, `m10_drivers.py::short_capture` |
| XM-C057 | `test_transform_pipeline.py::test_auto_apply_disabled_runs_clean_with_reason`, `m10_drivers_c.py::m11_optin`, `m10_drivers_c.py::m11_optin`, `m10_drivers_c.py::m11_optin`, `m10_drivers_c.py::m11_unbound` |
| XM-C058 | `m05_corpus_runner.py::h_text`, `m05_corpus_runner.py::h_text`, `m05_corpus_runner.py::h_text`, `test_m05_review_round.py::test_Q5_scope_values_have_one_canonical_form` |
| XM-C059 | `m10_drivers_b.py::captured_rewrite`, `m10_drivers_c.py::terminal_separator`, `m10_drivers_b.py::cleanup_failure_keeps_expansion`, `test_cleanup_remediation.py::test_05_protection_exact_and_multiplicity` |
| XM-C060 | `test_m04_remediation.py::test_10_literal_escape_scope`, `test_normalize_syntax.py::test_literal_and_noncommand_stay_unconverted`, `test_cleanup_engine.py::test_protected_span_mapping_never_drops`, `m10_drivers_b.py::trigger_literal` |
| XM-C061 | `test_cleanup_remediation.py::test_02_typed_numbers`, `test_cleanup_remediation.py::test_r7_comma_grouping_is_checked`, `test_m04_remediation.py::test_05_signed_typed_values_and_port_domain`, `test_m04_remediation.py::test_03_scaled_decimal_exact`, `test_m04_remediation.py::test_04_malformed_and_quantified_scales_whole_literal`, `test_m04_remediation.py::test_08_structured_chains_owned_whole` |
| XM-C062 | `test_cleanup_remediation.py::test_05_occurrence_mapping_uses_ledger`, `test_cleanup_remediation.py::test_r4_protected_occurrence_not_merely_text`, `test_cleanup_engine.py::test_protected_span_mapping_never_drops`, `test_cleanup_engine.py::test_multi_window_with_protected_span` |
| XM-C063 | `m10_drivers_b.py::slot_policy`, `m10_drivers_b.py::slot_policy`, `m10_drivers_b.py::slot_policy`, `m10_drivers_b.py::missing_snapshot_protects` |
| XM-C064 | `m10_drivers_b.py::snippet_beats_term`, `m05_corpus_runner.py::h_same_span`, `test_m10_remediation.py::c31_coordinator_runs_one_normalization_pass` |
| XM-C068 | `test_m02_remediation_collector.py::test_consent_is_decided_at_capture_start` |
| XM-C069 | `test_m02_remediation_collector.py::test_consent_is_decided_at_capture_start`, `test_collector.py::test_pause_creates_no_new_payload`, `test_transform_remediation_native.py::f08_dictation_candidate_follows_captured_consent` |
| XM-C073 | `m14_drivers_b.py::c060_same_job_wrong_stage`, `m14_drivers_b.py::c063_deleted_artifact_row` |
| XM-C074 | `test_m02_remediation_collector.py::test_uncommitted_artifact_is_reported_not_claimed`, `test_xm_remediation.py::x05_failed_normalized_retention_is_never_a_complete_task`, `m05_corpus_runner.py::h_hint_failure` |
| XM-C079 | `test_transform_pipeline.py::test_uncertain_coverage_falls_back_to_clean`, `test_transform_remediation.py::f01_unrepresented_requirements_not_applied`, `test_transform_remediation.py::f03_real_worker_round_trip_nonempty_coverage` |
| XM-C080 | `m12_drivers_c.py::s005`, `m12_drivers_b.py::c065`, `test_transform_remediation_native.py::f07_accept_checks_the_captured_note_identity`, `test_transform_remediation_native.py::f07_chained_transform_keeps_destination_authority` |
| XM-C081 | `m14_drivers_d.py::c113_cross_task`, `test_transform_engine.py::test_task_identity_and_retry_semantics`, `test_transform_pipeline.py::test_preference_same_task_invariants` |
| XM-C082 | `test_transform_engine.py::test_task_identity_and_retry_semantics`, `m14_drivers_d.py::c113_cross_task` |
| XM-C083 | `test_transform_engine.py::test_exact_carry_guards_every_mode`, `test_transform_remediation.py::f01_unrepresented_requirements_not_applied`, `test_transform_remediation.py::f01_same_losses_under_polish_and_concise` |
| XM-C084 | `test_transform_remediation.py::f04_technical_tokens_carry_verbatim`, `test_transform_remediation.py::f04_case_distinct_literals_stay_distinct`, `test_transform_pipeline.py::test_uncertain_coverage_falls_back_to_clean` |
| XM-C087 | `m14_drivers_d.py::c116_task_key_corruption`, `m14_drivers_b.py::c061_foreign_transform` |
| XM-C135 | `m10_drivers_c.py::hub_add_timeout_snippet`, `m10_drivers_c.py::hub_add_timeout_style`, `test_m10_remediation.py::r21_admitted_add_timeout_is_unknown_and_retry_is_idempotent` |
| XM-C178 | `m13_drivers_b.py::d_rapid_filters`, `m09_drivers.py::c001_history_late_completion`, `m09_drivers.py::c029_request_inputs_captured_at_admission`, `test_m09_remediation.py::test_a03_old_error_after_new_success` |
| XM-R15 | `test_m09_remediation.py::test_a02_late_detail_publication_after_delete`, `test_m09_remediation.py::test_r02_readmitted_detail_never_overrides_newer_selection`, `m09_drivers.py::c090_cross_view_payload_and_profile_revoked` |
| XM-R16 | `test_m09_remediation.py::test_a03_old_error_after_new_success`, `test_m09_remediation.py::test_a03_publication_check_and_mutation_atomic` |
| XM-R17 | `test_m03_remediation_app.py::test_04_quit_is_ordered`, `m09_drivers.py::c036_quit_cancels_deferred_show`, `m09_drivers.py::c038_shutdown_accounts_for_every_query_tail` |
| XM-C180 | `test_m09_remediation.py::test_r04_export_is_the_rendered_window_not_newer_state`, `test_m09_remediation.py::test_a20_export_is_the_displayed_snapshot_and_parses_off_main` |
| XM-C181 | `test_m09_remediation.py::test_a25_refresh_and_completions_run_on_main`, `test_m09_remediation.py::test_a21_mine_completion_never_forces_review_tab`, `test_m09_remediation.py::test_a21_older_export_cannot_overwrite_newer_status` |
| XM-R20 | `test_vocabulary_pipeline.py::test_ac03_live_midflight_edit`, `test_m06_remediation.py::test_a07_projection_uses_captured_entries_only`, `m05_corpus_runner.py::h_midflight` |
| XM-MR04 | `m14_drivers_c.py::c078_equivalent_scope`, `m05_corpus_runner.py::h_text`, `m14_drivers_c.py::c091_scope_app_site`, `m14_drivers_c.py::c092_scope_workspace_profile` |
| XM-MR10 | `test_m09_remediation.py::test_a03_old_success_after_new_error`, `test_m09_remediation.py::test_a03_old_error_after_new_success`, `m09_drivers.py::c001_history_late_completion`, `m13_drivers_b.py::d_rapid_filters` |
| XM-MR14 | `m12_drivers_c.py::s005`, `test_transform_remediation.py::f07_note_destination_identity_and_region` |
| XM-MR15 | `test_transform_engine.py::test_task_identity_and_retry_semantics`, `test_transform_pipeline.py::test_preference_same_task_invariants`, `test_transform_remediation.py::f10_retry_lineage_recorded_on_the_new_candidate` |
| XM-MR16 | `test_m09_remediation.py::test_a01_training_table_click_uses_rendered_row`, `m10_drivers_c.py::hub_reorder` |
| XM-MR21 | `m05_corpus_runner.py::h_text`, `m05_corpus_runner.py::h_text`, `m14_drivers_c.py::c073_positive_new_entry` |
| XM-MU03 | `test_m10_remediation.py::r02_app_bundle_case`, `test_m10_remediation.py::r02_site_host_case_and_trailing_slash`, `test_m10_remediation.py::c02_non_equivalent_identities_stay_distinct` |
| XM-MU13 | `m13_drivers_b.py::d_hub_delete_all`, `m13_drivers_b.py::d_hub_delete_one`, `m13_drivers_b.py::d_rapid_filters` |
| XM-C096 | `m12_drivers_b.py::c053`, `m12_drivers_c.py::s020` |
| XM-C097 | `m12_drivers_c.py::s004`, `m12_drivers_c.py::s003`, `m12_drivers_b.py::c055` |
| XM-C098 | `m12_drivers_c.py::s020`, `m12_drivers_c.py::s021`, `test_m12_remediation.py::r04_typed_prefix_never_gets_dictated_provenance` |
| XM-C100 | `test_m12_remediation.py::r13_whole_note_accept_refuses_after_growth`, `m12_drivers_b.py::c059`, `m12_drivers_c.py::s005` |
| XM-C101 | `test_m09_remediation.py::test_r08_teach_refuses_when_the_final_text_is_a_transform`, `m09_drivers.py::test_r08_teach_refuses_when_the_final_text_is_a_transform`, `m14_drivers_a.py::c007_transformed_final_guard` |
| XM-C102 | `m09_drivers.py::c128_invalidated_action_buffers`, `test_m09_remediation.py::test_a02_late_detail_publication_after_delete`, `m09_drivers.py::test_a02_late_detail_publication_after_delete` |
| XM-C103 | `test_m09_remediation.py::test_r09_final_text_is_never_the_source_transcript`, `m09_drivers.py::test_r09_final_text_is_never_the_source_transcript`, `test_m12_remediation.py::r14b_missing_final_is_refused_not_substituted`, `m12_drivers_b.py::c100` |
| XM-C105 | `test_transform_pipeline.py::test_uncertain_coverage_falls_back_to_clean`, `test_m09_remediation.py::test_a17_transform_decision_is_displayed_and_final_text_authorized`, `m09_drivers.py::test_a17_transform_decision_is_displayed_and_final_text_authorized` |
| XM-MU05 | `test_m14_remediation.py::f11_teach_refuses_a_final_newer_than_the_rendered_one`, `test_m14_remediation.py::f11_history_teach_passes_the_rendered_final_identity`, `m14_drivers_a.py::c005_stale_final` |
| XM-C111 | `test_native_m14_training.py::c213`, `m14_drivers_c.py::c079_s029_revocation_between_phases` |
| XM-C112 | `m14_drivers_a.py::c004_identical`, `test_learning.py::test_teach_refusals_and_deletion_propagation` |
| XM-C113 | `test_learning.py::test_approval_composes_with_existing_entries_and_undo`, `m14_drivers_c.py::c075_existing_user_entry`, `m14_drivers_c.py::c083_alias_added_then_user_alias`, `m14_drivers_c.py::c085_preexisting_approved_alias` |
| XM-C114 | `test_m14_remediation.py::ir02_rejection_suppresses_pending_siblings`, `m14_drivers_c.py::c096_same_exact_pair`, `m14_drivers_c.py::c097_case_equivalent`, `test_learning.py::test_unapproved_rejected_never_change_output` |
| XM-C115 | `m14_drivers_c.py::c088_positive_actual_flip`, `m14_drivers_c.py::c091_scope_app_site`, `m14_drivers_c.py::c092_scope_workspace_profile`, `m14_drivers_c.py::c090_empty`, `m14_drivers_c.py::c077_disabled_entry`, `m14_drivers_c.py::c087_manual_disable_before_reapprove`, `test_m14_remediation.py::d06_approval_without_counterexamples_is_recorded_untested` |
| XM-C117 | `m14_drivers_c.py::c078_equivalent_scope`, `m14_drivers_c.py::c073_positive_new_entry`, `m14_drivers_c.py::mr013_canonical_scope_equivalence`, `test_m14_remediation.py::f22_equivalent_app_scope_composes_with_existing_entry` |
| XM-C133 | `test_native_m14_training.py::c212`, `test_m14_remediation.py::f18_job_only_teach_is_actionable_in_review` |
| XM-MH07 | `m10_drivers.py::canonical_equivalents`, `m10_drivers.py::canonical_equivalents`, `m10_drivers.py::canonical_equivalents`, `m10_drivers.py::canonical_equivalents`, `m10_drivers.py::canonical_equivalents`, `m10_drivers.py::canonical_profile`, `m10_drivers.py::non_equivalent`, `m10_drivers.py::non_equivalent`, `m10_drivers.py::non_equivalent`, `m14_drivers_c.py::c078_equivalent_scope`, `m14_drivers_c.py::mr013_canonical_scope_equivalence`, `m14_drivers_c.py::c074_preapproval_control`, `m14_drivers_c.py::c082_s007_created_then_user_edit`, `m14_drivers_c.py::c083_alias_added_then_user_alias`, `m14_drivers_c.py::c084_s031_concurrent_alias_during_undo` |
| XM-MH16 | `test_native_m14_training.py::c219`, `m14_drivers_c.py::c080_s006_unknown_after_effect`, `m14_drivers_c.py::c080_s006_unknown_after_effect` |
| XM-MH25 | `test_m14_remediation.py::ir01_reapproval_plans_against_the_candidates_identity`, `m14_drivers_c.py::c082_s007_created_then_user_edit`, `m14_drivers_c.py::c083_alias_added_then_user_alias`, `m14_drivers_c.py::c086_undo_reapprove`, `m14_drivers_c.py::mr002_undo_and_reapproval` |
| XM-R23 | `m14_drivers_c.py::s005_approval_against_existing_user_entry`, `test_m14_remediation.py::f10_concurrent_user_alias_survives_alias_undo`, `m14_drivers_c.py::c079_s029_revocation_between_phases` |
| XM-C120 | `m12_drivers_c.py::s021`, `m12_drivers.py::c043`, `test_m12_remediation.py::r17_surviving_typed_echo_is_not_dictated`, `m14_drivers_a.py::c022_repeated_words` |
| XM-C122 | `m14_drivers_a.py::c020_typed_plus_dictated`, `m14_drivers_a.py::c024_typed_transform_only`, `m14_drivers_a.py::c017_edit_first_of_two`, `m14_drivers_a.py::c018_edit_second_of_two`, `m12_drivers_b.py::c122`, `test_m14_remediation.py::f13_typed_only_region_is_not_dictation_evidence` |
| XM-C124 | `m14_drivers_a.py::c030_pending_note_delete`, `m12_drivers_b.py::c124` |
| XM-C126 | `test_m09_remediation.py::test_a07_listen_gate_is_per_example_through_current_hub`, `m09_drivers.py::test_a07_listen_gate_is_per_example_through_current_hub` |
| XM-C128 | `test_m09_remediation.py::test_a06_span_after_same_length_stage_replacement`, `test_m09_remediation.py::test_r05_span_fields_clear_when_the_stage_under_them_changes`, `test_m09_remediation.py::test_a06_unrelated_revision_keeps_same_reviewed_artifact`, `test_m09_remediation.py::test_r05_span_fields_survive_an_unrelated_revision`, `m09_drivers.py::test_a06_span_after_same_length_stage_replacement`, `m09_drivers.py::test_a06_unrelated_revision_keeps_same_reviewed_artifact` |
| XM-C129 | `m14_drivers_b.py::c046_explicit_then_abstain`, `m14_drivers_b.py::c045_abstain_then_explicit`, `test_m14_remediation.py::f14_readiness_matches_export_membership`, `test_m14_remediation.py::f19_later_abstention_returns_item_to_unresolved` |
| XM-C130 | `m14_drivers_d.py::c113_cross_task`, `m14_drivers_d.py::c116_task_key_corruption` |
| XM-C131 | `m14_drivers_d.py::s015_display_swapped_after_render`, `m14_drivers_d.py::c112_swapped_display`, `test_m14_remediation.py::f16_pair_judgment_binds_to_the_rendered_pair` |
| XM-C132 | `m14_drivers_d.py::c114_latest_sequence`, `m14_drivers_d.py::s016_latest_changes` |
| XM-MH15 | `m14_drivers_a.py::c025_deleted_note`, `m14_drivers_a.py::c030_pending_note_delete`, `m14_drivers_g.py::c222_delete_derived`, `m12_drivers_b.py::c125`, `m12_drivers_b.py::c117`, `m12_drivers_c.py::s026`, `test_note_evidence.py::test_deletion_propagates_to_evidence` |
| XM-MH27 | `m14_drivers_d.py::s015_display_swapped_after_render`, `m14_drivers_d.py::c112_swapped_display`, `m14_drivers_d.py::mr011_display_permutation`, `m14_drivers_d.py::c114_latest_sequence`, `m14_drivers_d.py::s016_latest_changes`, `test_m14_remediation.py::f16_pair_judgment_binds_to_the_rendered_pair` |
| XM-R22 | `m14_drivers_a.py::c025_deleted_note`, `m14_drivers_a.py::c030_pending_note_delete`, `m12_drivers_b.py::c124` |
| XM-MR17 | `test_m09_remediation.py::test_a06_unrelated_revision_keeps_same_reviewed_artifact`, `test_m09_remediation.py::test_r05_span_fields_survive_an_unrelated_revision`, `test_m09_remediation.py::test_a06_emoji_code_point_offsets`, `m09_drivers.py::test_a06_unrelated_revision_keeps_same_reviewed_artifact`, `m09_drivers.py::test_a06_emoji_code_point_offsets` |
| XM-MU07 | `test_m14_remediation.py::f13_typed_only_region_is_not_dictation_evidence`, `m14_drivers_a.py::c020_typed_plus_dictated`, `m12_drivers_b.py::c122` |
| XM-MU08 | `test_note_editor.py::test_debounce_and_autosave` |
| XM-MU33 | `test_m14_remediation.py::f16_pair_judgment_binds_to_the_rendered_pair`, `m14_drivers_d.py::s015_display_swapped_after_render` |
| XM-C022 | `m13_drivers.py::d_identity`, `m14_drivers_f.py::c181_repeat_variants` |
| XM-C136 | `m14_drivers_b.py::c058_foreign_raw`, `m14_drivers_a.py::c013_foreign_payload`, `m14_drivers_b.py::c053_foreign_audio`, `m14_drivers_f.py::c168_foreign_audio` |
| XM-C138 | `m14_drivers_a.py::c006_missing_applied`, `m14_drivers_b.py::c051_audio_missing_purged`, `test_m14_remediation.py::f03_purge_after_publication_invalidates_current`, `test_history_queries.py::test_audio_and_purged_reasons` |
| XM-C139 | `test_dataset_export.py::test_export_safety_and_semantics`, `m14_drivers_e.py::c147_outside_audio_path` |
| XM-C140 | `m14_drivers_e.py::c136_cleanup_missing_prompt` |
| XM-C141 | `m14_drivers_e.py::c143_nonempty_destination`, `m14_drivers_e.py::c142_empty_destination`, `m14_drivers_e.py::c144_unowned_staging_directory`, `test_xm_validator.py::main` |
| XM-C142 | `m14_drivers_b.py::c051_audio_missing_purged` |
| XM-C143 | `m14_drivers_f.py::c167_positive_parity` |
| XM-R08 | `test_m14_remediation.py::ir09_exposure_between_snapshot_and_fence_refuses` |
| XM-C148 | `test_splits.py::test_exposure_moves_forward_only`, `m14_drivers_d.py::c127_next_version`, `m14_drivers_d.py::c128_absent_version`, `m14_drivers_d.py::mr007_exposure_forward_only` |
| XM-C149 | `m14_drivers_d.py::c119_nine_floor`, `m14_drivers_d.py::s017_nine_versus_ten`, `test_splits.py::test_minimum_family_floor_and_late_hints` |
| XM-C150 | `m14_drivers_d.py::c121_related_variants` |
| XM-C151 | `m14_drivers_d.py::c115_source_output_purge` |
| XM-R09 | `m14_drivers_e.py::c153_s030_purge_after_fence`, `m14_drivers_e.py::c153_s030_purge_after_fence`, `m14_drivers_e.py::c151_s019_selected_purge_before_fence`, `m14_drivers_e.py::c151_s019_selected_purge_before_fence`, `m14_drivers_e.py::c152_s020_unrelated_delete`, `m14_drivers_e.py::c152_s020_unrelated_delete` |
| XM-C153 | `m14_drivers_f.py::c177_below_words`, `m14_drivers_f.py::c176_positive_floor`, `m14_drivers_f.py::c178_below_dictations`, `m14_drivers_g.py::mr008_profile_floor` |
| XM-MH02 | `test_m14_remediation.py::f03_purge_after_publication_invalidates_current`, `m14_drivers_e.py::c140_restricted_all_views`, `m14_drivers_f.py::c179_restricted` |
| XM-MH03 | `m14_drivers_g.py::c192_purge_mid_compute`, `m14_drivers_g.py::c192_purge_mid_compute`, `m14_drivers_e.py::c151_s019_selected_purge_before_fence` |
| XM-MH04 | `m13_drivers_b.py::d_profile_copies`, `m13_drivers_b.py::d_profile_copies`, `m13_drivers_b.py::d_profile_copies`, `m14_drivers_g.py::c198_delete_all_redacts_in_one_op` |
| XM-R11 | `m13_drivers_b.py::d_delete_during_profile`, `m14_drivers_g.py::s025_usage_deletion_with_profile` |
| XM-R12 | `m14_drivers_g.py::c192_purge_mid_compute`, `m14_drivers_g.py::c192_purge_mid_compute` |
| XM-R13 | `m14_drivers_g.py::c191_delete_mid_compute`, `m14_drivers_g.py::c191_delete_mid_compute` |
| XM-C155 | `m14_drivers_f.py::c183_owning_input_changes`, `m14_drivers_g.py::c196_secondary_signature_cannot_absorb`, `m14_drivers_g.py::c206_unchanged_idle_no_reads` |
| XM-C156 | `test_usage_store.py::test_unknown_dates_never_enter_dated_views`, `test_usage_store.py::test_dst_day_boundaries`, `m13_drivers.py::d_dst`, `m13_drivers.py::d_dst`, `m13_drivers.py::d_dst`, `m13_drivers.py::d_dst`, `m13_drivers.py::d_dst`, `m13_drivers.py::d_dst`, `m13_drivers.py::d_dst`, `m13_drivers.py::d_dst`, `m13_drivers_b.py::d_undated`, `m13_drivers_b.py::d_undated`, `m13_drivers_b.py::d_undated`, `m13_drivers_b.py::d_undated`, `test_m09_remediation.py::test_a13_default_zone_honors_historical_dst`, `m09_drivers.py::c042_unknown_times_stay_undated` |
| XM-C157 | `m13_drivers.py::d_wpm`, `m13_drivers.py::d_wpm`, `m13_drivers.py::d_wpm` |
| XM-C158 | `m13_drivers.py::d_words`, `m13_drivers.py::d_explicit_transform`, `m13_drivers.py::d_explicit_transform`, `m13_drivers.py::d_explicit_transform`, `m13_drivers.py::d_explicit_transform`, `m13_drivers.py::d_explicit_transform`, `m13_drivers.py::d_auto_transform_deletion`, `m13_drivers.py::d_repaste_counted`, `m13_drivers.py::d_repaste_counted`, `m13_drivers.py::d_repaste_counted`, `m14_drivers_g.py::c203_transform_counts` |
| XM-C159 | `m13_drivers.py::d_repaste_counted`, `m13_drivers.py::d_repaste_counted`, `m13_drivers.py::d_repaste_counted`, `m13_drivers.py::d_repaste_policy`, `m13_drivers.py::d_repaste_policy`, `m13_drivers.py::d_repaste_policy`, `m13_drivers.py::d_repaste_policy`, `m13_drivers.py::d_repaste_policy` |
| XM-C160 | `m13_drivers_b.py::d_delete_one_timeout`, `m13_drivers_b.py::d_profile_copies`, `m14_drivers_g.py::c222_delete_derived` |
| XM-C161 | `m14_drivers_g.py::c222_delete_derived`, `m14_drivers_g.py::c187_delete_one_support` |
| XM-C162 | `m14_drivers_a.py::c015_deleted_job`, `m14_drivers_g.py::c191_delete_mid_compute`, `m14_drivers_e.py::c151_s019_selected_purge_before_fence`, `m14_drivers_e.py::c153_s030_purge_after_fence` |
| XM-R14 | `test_m02_remediation_collector.py::test_delete_before_finalize_blocks_late_producer`, `test_m09_remediation.py::test_a02_late_detail_publication_after_delete` |
| XM-C163 | `test_m02_remediation_store.py::test_failed_unlink_stays_pending_then_retries` |
| XM-C164 | `m14_drivers_a.py::c032_reviewed_vs_user_pin`, `m14_drivers_a.py::s033_reviewed_artifact_unpinned`, `m09_drivers.py::c015_unpin_keeps_annotation_retention` |
| XM-C165 | `m14_drivers_a.py::c026_positive_live_pending`, `m14_drivers_a.py::c027_pending_expiry`, `m14_drivers_f.py::c179_restricted`, `m14_drivers_e.py::c140_restricted_all_views` |
| XM-C166 | `test_m02_remediation_store.py::test_training_expiry_respects_other_interests`, `test_store.py::test_history_expiry_respects_training_lease`, `test_m09_remediation.py::test_a02_independent_history_lease_survives_training_expiry` |
| XM-C167 | `m13_drivers_b.py::d_pruning`, `m13_drivers_b.py::d_pruning` |
| XM-C169 | `m13_drivers_b.py::d_retention_independence`, `m13_drivers_b.py::d_retention_independence`, `m14_drivers_g.py::c199_expiry`, `test_usage_store.py::test_text_prune_does_not_empty_usage_and_expiry_does` |
| XM-C170 | `m09_drivers.py::c072_late_deletion_revokes_queued_paste`, `m09_drivers.py::c128_invalidated_action_buffers`, `m09_drivers.py::c090_cross_view_payload_and_profile_revoked` |
| XM-C171 | `test_xm_privacy.py::session`, `test_m09_remediation.py::test_a08_hub_export_uses_typed_allowlist`, `m09_drivers.py::c101_known_field_wrong_type`, `m14_drivers_g.py::c220_content_free_events` |
| XM-C172 | `test_xm_privacy.py::session`, `m13_drivers_b.py::d_privacy`, `m13_drivers_b.py::d_privacy`, `m13_drivers_b.py::d_privacy`, `m13_drivers_b.py::d_privacy`, `m13_drivers_b.py::d_privacy`, `m13_drivers_b.py::d_privacy`, `m13_drivers_b.py::d_privacy`, `m13_drivers_b.py::d_privacy` |
| XM-MH26 | `m14_drivers_f.py::c162_semantic_consistent_tamper`, `m14_drivers_d.py::c121_related_variants`, `m14_drivers_d.py::c122_family_corruption`, `m14_drivers_d.py::c127_next_version`, `m14_drivers_d.py::c128_absent_version`, `m14_drivers_f.py::c171_blocked_asr`, `test_xm_validator.py::main` |
| XM-MH28 | `m14_drivers_g.py::c222_delete_derived`, `m14_drivers_g.py::c191_delete_mid_compute`, `m13_drivers_b.py::d_delete_during_profile` |
| XM-MH30 | `m14_drivers_e.py::c151_s019_selected_purge_before_fence`, `m14_drivers_e.py::c152_s020_unrelated_delete`, `test_m14_remediation.py::ir09_exposure_between_snapshot_and_fence_refuses` |
| XM-MR02 | `m14_drivers_b.py::c060_same_job_wrong_stage`, `m14_drivers_b.py::c058_foreign_raw`, `m14_drivers_b.py::c059_transform_as_raw`, `m14_drivers_b.py::c062_wrong_verbatim_role` |
| XM-MR03 | `m14_drivers_g.py::c191_delete_mid_compute`, `m14_drivers_e.py::c153_s030_purge_after_fence`, `m14_drivers_g.py::mr004_deletion_monotonicity` |
| XM-MR07 | `m13_drivers_b.py::d_delete_all_independent`, `m13_drivers_b.py::d_delete_after_content`, `m14_drivers_g.py::c222_delete_derived`, `m14_drivers_g.py::mr009_usage_redaction_monotone` |
| XM-MR09 | `m14_drivers_d.py::c129_old_version_export` |
| XM-MR11 | `m14_drivers_g.py::c187_delete_one_support` |
| XM-MR12 | `m14_drivers_e.py::c152_s020_unrelated_delete`, `m14_drivers_e.py::c152_s020_unrelated_delete`, `m14_drivers_e.py::c151_s019_selected_purge_before_fence`, `m14_drivers_e.py::mr010_export_dependency_locality` |
| XM-MR20 | `m14_drivers_d.py::c120_permutation`, `m14_drivers_d.py::c120_permutation` |
| XM-MU01 | `m12_drivers_b.py::c120`, `m13_drivers_b.py::d_note_revisions` |
| XM-MU02 | `m14_drivers_b.py::c059_transform_as_raw`, `m14_drivers_b.py::c058_foreign_raw` |
| XM-MU09 | `m13_drivers_b.py::d_profile_copies`, `m13_drivers_b.py::d_profile_copies` |
| XM-MU11 | `m14_drivers_g.py::c187_delete_one_support`, `m14_drivers_g.py::c184_cards_follow_live_support`, `m14_drivers_g.py::c185_arbitrary_citation_fails_oracle` |
| XM-MU14 | `m14_drivers_d.py::c128_absent_version`, `test_splits.py::test_exposure_moves_forward_only` |
| XM-MU29 | `test_m02_remediation_collector.py::test_delete_before_finalize_blocks_late_producer` |
| XM-MU31 | `m14_drivers_g.py::c191_delete_mid_compute` |
| XM-MU32 | `test_m14_remediation.py::ir09_exposure_between_snapshot_and_fence_refuses`, `m14_drivers_e.py::c151_s019_selected_purge_before_fence`, `m14_drivers_e.py::c153_s030_purge_after_fence` |

## Deferred (13 cases)

| Case | Category | Owner |
|---|---|---|
| XM-C065 | DEFERRED_MODEL | tests/v2/fidelity/test_fidelity.py (model-backed EV-09) + VERIFICATION.html M07-V001 + M15-AC02 |
| XM-C187 | DEFERRED_M15 | M15 preconditions (LOCALFLOW_V2_MILESTONES.md M15) + GATE-G10 (M11 integrated record, M07-V001/V002) |
| XM-C188 | DEFERRED_M15 | M15 completion report (M15-AC01..AC08 evidence mapping) |
| XM-C189 | DEFERRED_M15 | M15-AC05, M15-AC08 |
| XM-C190 | DEFERRED_M15 | M15-AC06, M15-AC07 |
| XM-C191 | DEFERRED_MODEL | GATE-G08 (human-speaker end-to-end timing) + M15-AC04 |
| XM-C192 | DEFERRED_M15 | GATE-G08 + M15-AC03/AC04 (reference-condition budgets) |
| XM-C194 | DEFERRED_M15 | M15-AC03/AC04 (reference Mac) + GATE-G08 |
| XM-C195 | DEFERRED_M15 | M15-AC03/AC04 |
| XM-C196 | DEFERRED_NATIVE | GATE-G07 active tier + VERIFICATION.html M09-V001 (larger text, light/dark) and M09-V002 (keyboard only) |
| XM-C197 | DEFERRED_NATIVE | tests/v2/insertion/test_native_insertion.py native tier + VERIFICATION.html M08-V002 (your copy survives, clipboard comes back) |
| XM-MH32 | DEFERRED_M15 | GATE-G08 + M15-AC04 |
| XM-C121 | DEFERRED_NATIVE | GATE-G07 active tier (owned native Hub; adjudications.json GATE-G07 partial) together with M12 native qualification LF-M12-N002/N004/N006 (NOT_RUN in final/corpus_m*.json) |

## Not applicable

- XM-MU22: The mutant's target does not exist. AppDelegate._worker (app.py:4031-4640) has no attempt or generation discard guard: it takes whatever supervisor.transcribe/clean returns and only copies res['attempt'] (app.py:4096-4102). Stale old-generation and old-attempt completions are rejected upstream in WorkerSupervisor._handle_message (supervisor.py:470-500), and at insertion by the stale_attempt gate (service.py:520). The equivalent invariant at those real guards is covered: test_worker_protocol.py::test_stale_generation_echo_resolves_as_fault and test_stale_generation_result_discarded, test_m03_remediation_supervisor.py::test_13_expected_identity_matrix (sweep exit=0), and LF-M08-F01-C05 (pass). Retries cannot overlap a live attempt (M13-C006 PASS).

## DRIVER_REQUIRED, not mandatory before merge (40 cases)

A unique automatable obligation no current suite proves, whose path runs through none of the remediation's changed functions and whose oracle reads no behaviour a G06 repair changed. Each keeps its driver specification in the manifest. XM-C042 carries an open product question: a retry has no target and inserts at the current focus (validate_target's target-less branch), which conflicts with the case's "0 writes into another app" oracle.

| Case | Invariant |
|---|---|
| XM-C023 | Autosaving and restoring a note that received dictation J creates no new capture, job or dictation count. |
| XM-C026 | A retry publishes its example under the original capture's consent revision and family, publishes nothing after a later revocation, never mints a new family, and increments jobs.attempt exactly once. |
| XM-C027 | Retrying an old job never consumes a queued one-shot Next Mode override; the next new capture receives it. |
| XM-C029 | Delivering the same successful terminal _finishWithText_ callback twice yields one terminal outcome, one dictation fact and one insertion submission. |
| XM-C031 | A retry result released after delete-everywhere recreates no governed content, learning or profile eligibility. |
| XM-C039 | Moving the selection to another occurrence of identical text needs proof of the original region; text equality never retargets a strict replacement. |
| XM-C042 (flagged) | A retry while another app is focused keeps the original capture app in its usage metadata and applies current insertion safety independently. |
| XM-C183 | Pre-remediation benchmark results stay dated and source-bound, are never relabeled current and are never overwritten by a rerun. |
| XM-C186 | Every registry requirement and suite entry resolves to a git-tracked current test entrypoint that imports and calls production code; dead or unbound nodes are reported as gaps, and future (M15/M16) suites are labeled ... |
| XM-MH19 | After ASR failure and worker restart, a retry keeps job, family and capture identity, rejects an old-generation response, cannot reuse stale insertion permission, and leaves one usage fact. |
| XM-C045 | Only documented canonical site-origin equivalents match; port and www variants never alias. |
| XM-C046 | Workspace/profile scopes are exact opaque identities after trimming across matching, approval and undo. |
| XM-C048 | When field context cannot be read, the finalized snapshot invents no site, workspace or selection authority. |
| XM-C050 | A late context delta stays attached to its own capture handle and parent revision and never replaces another capture's scope. |
| XM-C051 | A job with no usable workspace freezes no skill or file-tag authority cached from a prior workspace. |
| XM-C085 | An auto-applied transform never synthesizes a user accept or preference, and the auto path stays distinct in transform-supervised readiness. |
| XM-C086 | A held transform completion for source A released after the panel moved to B cannot replace B's display, destination or acceptance authority. |
| XM-C174 (flagged) | Unavailable source-revision or time-quality fields stay null-with-reason in rendered diagnostics and redacted exports. |
| XM-C175 | Under a low-priority flood the bounded queue counts loss and coalescing and marks terminal degradation explicitly. |
| XM-C179 | A query in flight when its pane or the Hub closes, including one whose source is deleted, never publishes, caches or resurrects focus or actions after reopen. |
| XM-MH08 | A job frozen in A generates its auto-transform from A's frozen policy after focus moves to B, is never pasted into B, and reports an honest saved disposition. |
| XM-MH31 | Quitting while an insertion, a note arrival and a review mutation settle causes no premature resource release, stale UI reopen, duplicate effect or false completion claim. |
| XM-R19 | A foreground change after context freeze never rereads B or pulls B's content or rules into A's job, and insertion revalidation refuses the unrelated target. |
| XM-MR05 | Changing live foreground context after freeze never alters the frozen job's policy or pulls unrelated content, apart from an independently checked insertion refusal. |
| XM-MR13 | Re-saving settings with identical values leaves effective output, task input and scope equal; any new revision is labeled without changed semantics. |
| XM-MU04 | Changing unrelated foreground context after freeze does not change the transform task's inputs. |
| XM-MU30 | A result read before deletion never repaints after revoke_job. |
| XM-C089 | History Copy refuses (outcome clipboard_busy, board untouched) while the M08 service owns the pasteboard, and after release copies exactly once. |
| XM-C090 | A reconcile of a pending clipboard payload never restores the obsolete prior clipboard over a newer external owner. |
| XM-C093 | A note arrival is reported delivered only after its revision commits; an admitted-but-timed-out arrival commit retried by the editor yields exactly one revision and one usage fact. |
| XM-R04 | An autosave pending while a dictation arrival commits never overwrites the typed tail or duplicates the arrival, in either release order. |
| XM-C095 | An owned external insertion writes no note revision and records exactly one external dictation fact. |
| XM-C099 | Quitting with an admitted but unacknowledged note arrival drains it or preserves recovery authority, and never claims saved/confirmed merely on enqueue. |
| XM-MH21 | Dictation into a note being edited keeps typed bytes typed, counts the arrival only when durable, and stops correction ownership at ambiguity. |
| XM-C134 | An operation id recorded for one action refuses when reused for a different action (kind) on the same target, leaving state unchanged. |
| XM-C127 | A span correction or intended-writing mark prepared in the Hub on a reviewable example that became quarantined_sensitive or expired before Save is refused and never overwrites the restriction. |
| XM-R24 | Mining interleaved with autosave binds each mined change to one exact (previous, current) revision pair and one job, and never promotes typed-region words from a stale diff. |
| XM-C147 | Deleting the example through which a family was exposed never washes the family's exposure. |
| XM-C168 | Being sampled never grants an unreviewed candidate indefinite human-review retention. |
| XM-C173 | Planned evidence artifacts and docs carry no user path, session id or live content, including truncated fragments without a /Users/ prefix. |

