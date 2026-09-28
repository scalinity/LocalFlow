# LocalFlow M01–M14 — Producer → Consumer Interface Matrix

**Audited commit:** `340c566686c7123bfcf721e16160aacabbe0b97d` · **Target execution:** `NOT_RUN`

This is the source-review interface inventory, not an exhaustive local `rg` caller census. A cited handoff reports earlier execution; it is not an independently rerun result. “Owning tests” names the owning suite or a source-reported entrypoint, not a newly verified passing test. Each proposed local regression must cross the actual edge.

## Architecture boundary

The coordinator orchestrates the worker and domain services over a single-writer store. M04, M05 and M10 contribute to one normalization result; they must not be modeled as three unrelated text mutators. M06 pre-decode and late downstream snapshots remain separately identified. A retry preserves original capture provenance but may explicitly use a new attempt policy where its contract permits it.

## Interface index

| ID | Producer → consumer | Object | Principal risk |
|---|---|---|---|
| IF-01 | M01 → M02/M03 | Baseline/config/model provenance | Provenance drift remains an explicit gate |
| IF-02 | M02 → M03 | Logical job and managed audio | Do not confuse retry attempt with another capture |
| IF-03 | M03 → M07 | Worker reply and attempt | Native worker restart composition needs a bound local regression |
| IF-04 | M04/M05/M10 → M07 | One deterministic normalization result | Internal normalize rule ordering not independently exhaustively re-enumerated |
| IF-05 | M05 → M10/M14 | Canonical scoped vocabulary identity | Preserve actual M05 authority; do not invent M14 SQL shortcuts |
| IF-06 | M06 → M07/M10/M11 | Job-scoped context collection | Native AX/browser guarantees still require owned probes |
| IF-07 | M10 → M11 | Frozen styles/snippets/file/skill authority | No downstream bypass of path/skill admission may be assumed absent without local inventory |
| IF-08 | M11 → M14 | Transform definition history | CROSS-AUDIT-02, -05, -06 |
| IF-09 | M07 → M11 | Cleanup result and transform input | Real-model correctness remains unresolved; gate existence is not semantic proof |
| IF-10 | M11 → M08 | Gated transform candidate and accept | Current Mac/real-model end-to-end verification remains pending |
| IF-11 | M08 → M09/M13 | External insertion outcome | No later producer currently upgrades posted-unverified to confirmed |
| IF-12 | M12 → M03/M13 | Internal note delivery receipt | Keep internal confirmation distinct from AX insertion |
| IF-13 | M02/M07/M11 → M09 | Current History lineage | Purpose-specific final selection; profile raw speech is not this display final |
| IF-14 | M09 → M14 | History Teach admission | Strong seam retained; transformed unsupported teaching must refuse honestly |
| IF-15 | M09 → M12 | History Save/Move transfer | Native cross-pane transfer/retry/expiry witness still required |
| IF-16 | M08 → M14 | Certified edit observation | No claim that any external edit is acoustic ground truth |
| IF-17 | M12 → M14 | Note revision provenance | Typed-only and ambiguous repeated regions abstain; crash evidence gaps remain |
| IF-18 | M03/M08/M11/M12 → M13 | Usage terminal producers | No new execution here; independent cross-producer reduction required |
| IF-19 | M02/M03 → M14 | Training examples into speech profile | CROSS-AUDIT-03 |
| IF-20 | M05/M02 → M14 | Frozen applied vocabulary into technical terms | CROSS-AUDIT-04 |
| IF-21 | M13 → M14/M09 | Usage deletion and profile copies | Strong source separation; full active-pane canary run remains NOT_RUN |
| IF-22 | M14 → M05 | Approval and undo delta | Service reversibility does not establish visible Undo control |
| IF-23 | M14 → M13 readiness / M14 export | Shared task qualification | Match partitions/assignment when comparing membership, not global counts blindly |
| IF-24 | M14 splits → M14 export / M15 | Family and exposure history | CROSS-AUDIT-01 covers lost membership authority |
| IF-25 | M02 → M14 export | Managed artifact files | Ancestor-symlink and all downstream-reader equivalence need local probes |
| IF-26 | M14 export → Filesystem / Store / Hub | Dataset publication | DESIGN-02: conservative recovery, not a claim of cross-filesystem transaction atomicity |
| IF-27 | M14 Validate → M09 Hub state | Validation result | CROSS-AUDIT-07 |
| IF-28 | M02 → All later domains | Schema/version and repair authority | CROSS-AUDIT-01; live-opening CLI inventory not exhaustive in this audit |
| IF-29 | M01/M09/M14 docs → M15 authorization | Registry/runbook/current-state evidence | CROSS-AUDIT-08 and coverage gaps |

## IF-01 — M01 → M02/M03: Baseline/config/model provenance

**Authoritative object/fields:** Commit/config/model hashes and installed-build identity.
**Frozen versus mutable:** Pinned source is immutable; installed process and effective configuration are separate observations.
**Expected revision/identity:** Exact source/config/model revision, never a branch name alone.
**Deletion behavior:** No private baseline copied into generic events.
**Timeout behavior:** Startup failure is not evidence that an installed process matches Git.
**Owning tests / evidence:** EV-01; M01 handoff; current installed parity remains human/native.
**Cross-milestone risk:** Provenance drift remains an explicit gate.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py).

## IF-02 — M02 → M03: Logical job and managed audio

**Authoritative object/fields:** job_id, original capture instant, family, attempt, registered audio.
**Frozen versus mutable:** Capture provenance immutable; attempt/state mutable under lifecycle admission.
**Expected revision/identity:** Expected attempt and managed audio name/digest.
**Deletion behavior:** Job tombstone prevents resurrection; journal and artifact copies share deletion authority.
**Timeout behavior:** Admitted writer timeout is unknown, not cancellation.
**Owning tests / evidence:** EV-03/04/05/19; M02/M03 reported regressions.
**Cross-milestone risk:** Do not confuse retry attempt with another capture.
**Source:** [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py).

## IF-03 — M03 → M07: Worker reply and attempt

**Authoritative object/fields:** job_id, attempt, worker generation, raw text and stage duration.
**Frozen versus mutable:** Each reply belongs to its requested attempt; stage output becomes governed artifact.
**Expected revision/identity:** Match job/attempt; do not settle a stale worker reply.
**Deletion behavior:** Deleted/cancelled job cannot be republished by a late result.
**Timeout behavior:** Worker failure and Store admission timeout are different dimensions.
**Owning tests / evidence:** EV-05/09; app coordinator source traced.
**Cross-milestone risk:** Native worker restart composition needs a bound local regression.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py).

## IF-04 — M04/M05/M10 → M07: One deterministic normalization result

**Authoritative object/fields:** Policy/context snapshots, ledger edits, protected spans, approved rules/snippets/file references.
**Frozen versus mutable:** Per-job snapshots fixed; runtime registry may change for later jobs.
**Expected revision/identity:** Rule IDs plus frozen revision/manifests and exact output coordinates.
**Deletion behavior:** Unavailable protection must not be silently discarded.
**Timeout behavior:** Normalization exception is explicitly recorded raw passthrough; unprotected cleanup abstains.
**Owning tests / evidence:** EV-06/07/12/09; test_cleanup_remediation.py is reported.
**Cross-milestone risk:** Internal normalize rule ordering not independently exhaustively re-enumerated.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py).

## IF-05 — M05 → M10/M14: Canonical scoped vocabulary identity

**Authoritative object/fields:** entry ID, canonical scope, aliases, enabled/approved, revision/history.
**Frozen versus mutable:** Definitions mutable with canonical identity and revision; frozen job snapshot immutable.
**Expected revision/identity:** Expected revision and canonical_scope_value, not raw string comparison.
**Deletion behavior:** User deletion/disable cannot be undone by a stale learned rule.
**Timeout behavior:** M14 approval receipt protects one transaction; other callers require inventory.
**Owning tests / evidence:** EV-07/12/20; M05/M10 handoffs and LearningService traced.
**Cross-milestone risk:** Preserve actual M05 authority; do not invent M14 SQL shortcuts.
**Source:** [localflow/v2/vocabulary_store.py · writer-authoritative update and revision history](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py).

## IF-06 — M06 → M07/M10/M11: Job-scoped context collection

**Authoritative object/fields:** Context snapshot/handle, destination identity, category and permitted context.
**Frozen versus mutable:** Pre-decode snapshot fixed; separately labeled late downstream revision tied to same collection.
**Expected revision/identity:** Collection identity and frozen request, never the newest foreground cache.
**Deletion behavior:** Sensitive/denied/missing proof only reduces capability.
**Timeout behavior:** Late provider response cannot retroactively become pre-decode evidence.
**Owning tests / evidence:** EV-08/09/12/13; coordinator take_downstream traced.
**Cross-milestone risk:** Native AX/browser guarantees still require owned probes.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py).

## IF-07 — M10 → M11: Frozen styles/snippets/file/skill authority

**Authoritative object/fields:** Effective mode/category, rule manifests and confined reference listing.
**Frozen versus mutable:** Current job uses frozen allowed references; next job may see edits.
**Expected revision/identity:** Definition/manifest revision and partial-listing status.
**Deletion behavior:** Revoked or missing source cannot trigger unchecked filesystem resolution.
**Timeout behavior:** Typed config mutation versus file effect must be separately reconciled.
**Owning tests / evidence:** EV-12/13; M10 remediation handoff.
**Cross-milestone risk:** No downstream bypass of path/skill admission may be assumed absent without local inventory.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py).

## IF-08 — M11 → M14: Transform definition history

**Authoritative object/fields:** transform_id, revision, prompt revision, definition JSON.
**Frozen versus mutable:** Definitions mutate; each historical revision must remain exact and immutable.
**Expected revision/identity:** Same revision must mean identical semantic definition across live/history/export.
**Deletion behavior:** Missing definition reduces task qualification.
**Timeout behavior:** Transform CRUD does not yet inherit all M10/M14 unknown protections.
**Owning tests / evidence:** EV-13/20/21; source traced through transform_target_in.
**Cross-milestone risk:** CROSS-AUDIT-02, -05, -06.
**Source:** [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py).

## IF-09 — M07 → M11: Cleanup result and transform input

**Authoritative object/fields:** Cleaned applied artifact, exact text/hash, requirement atoms.
**Frozen versus mutable:** Candidate output is distinct from accepted/applied output.
**Expected revision/identity:** Source hash, transform revision, task key and gate decision.
**Deletion behavior:** Source loss/staleness refuses later application.
**Timeout behavior:** Generation timeout is not a user approval or external delivery.
**Owning tests / evidence:** EV-09/13; M11 reported portable/native gates.
**Cross-milestone risk:** Real-model correctness remains unresolved; gate existence is not semantic proof.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py).

## IF-10 — M11 → M08: Gated transform candidate and accept

**Authoritative object/fields:** Candidate/task identity, approved disposition, captured target selection.
**Frozen versus mutable:** Candidate fixed to source; accept must revalidate destination.
**Expected revision/identity:** Exact target/selection identity and source revision; strict replacement stays strict.
**Deletion behavior:** Loss of proof refuses rather than downgrades to ordinary paste.
**Timeout behavior:** Posted-unverified is not confirmed; unknown external effects are not safe retries.
**Owning tests / evidence:** EV-10/13; M08/M11 handoffs.
**Cross-milestone risk:** Current Mac/real-model end-to-end verification remains pending.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py).

## IF-11 — M08 → M09/M13: External insertion outcome

**Authoritative object/fields:** Transaction identity and confirmed/posted_unverified/saved status.
**Frozen versus mutable:** Transaction receipt is observation; History/usage translate explicitly.
**Expected revision/identity:** One coordinator terminal completion per attempt.
**Deletion behavior:** Content deletion revokes replay/action payload; allowed usage may remain.
**Timeout behavior:** Unknown write admission distinct from external insertion uncertainty.
**Owning tests / evidence:** EV-10/11/15; completion and analytics contract traced.
**Cross-milestone risk:** No later producer currently upgrades posted-unverified to confirmed.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md).

## IF-12 — M12 → M03/M13: Internal note delivery receipt

**Authoritative object/fields:** note ID, exact arrival/revision identity, source job, bound caret.
**Frozen versus mutable:** Arrival capture immutable; buffer ACK not equivalent to durable note commit.
**Expected revision/identity:** Exact note/revision/arrival, not currently selected note.
**Deletion behavior:** Deleted/revised destination refuses or preserves a truthful saved outcome.
**Timeout behavior:** Admitted note mutation may be unknown; never label it proven failed.
**Owning tests / evidence:** EV-14/15/19; M12/M13 reported native regressions.
**Cross-milestone risk:** Keep internal confirmation distinct from AX insertion.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md).

## IF-13 — M02/M07/M11 → M09: Current History lineage

**Authoritative object/fields:** job_id, attempt, stage artifacts, current transformed/clean final.
**Frozen versus mutable:** Artifacts immutable; current attempt/final selector changes under explicit lifecycle.
**Expected revision/identity:** Rendered final artifact/hash plus generation.
**Deletion behavior:** Missing expected final means unavailable, not fallback to prior/raw.
**Timeout behavior:** Historical action must not infer success from query completion.
**Owning tests / evidence:** EV-11/13/19; HistoryQueryService source traced.
**Cross-milestone risk:** Purpose-specific final selection; profile raw speech is not this display final.
**Source:** [localflow/v2/history_queries.py · current-attempt lineage and final-text resolution](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py); [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py).

## IF-14 — M09 → M14: History Teach admission

**Authoritative object/fields:** Rendered applied artifact ID/hash and corrected text.
**Frozen versus mutable:** User buffer belongs to exact rendered final.
**Expected revision/identity:** Expected final ID/hash checked inside minting writer operation.
**Deletion behavior:** Deleted/purged/stale final refuses.
**Timeout behavior:** Stable operation receipt reconciles the same teaching action.
**Owning tests / evidence:** EV-11/20; teach_correction source traced.
**Cross-milestone risk:** Strong seam retained; transformed unsupported teaching must refuse honestly.
**Source:** [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py).

## IF-15 — M09 → M12: History Save/Move transfer

**Authoritative object/fields:** Rendered job/final and note target identity.
**Frozen versus mutable:** Source text/revision fixed at admission; new note identity explicit.
**Expected revision/identity:** Transfer bound to visible source, not writer-current raw fallback.
**Deletion behavior:** Move may delete source only under its explicit supported contract.
**Timeout behavior:** Multi-operation outcome must distinguish saved note from source deletion.
**Owning tests / evidence:** EV-11/14; M09 residual superseded in M12 handoff.
**Cross-milestone risk:** Native cross-pane transfer/retry/expiry witness still required.
**Source:** [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/history_queries.py · current-attempt lineage and final-text resolution](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py).

## IF-16 — M08 → M14: Certified edit observation

**Authoritative object/fields:** Job-owned before/after observation artifacts and stop reason.
**Frozen versus mutable:** Immutable bounded observation; classifier cannot strengthen attribution.
**Expected revision/identity:** Owner + observation role + retained digest + reliable stop reason.
**Deletion behavior:** Deleted job or unretained observation cannot mint candidate.
**Timeout behavior:** Mining each observed edit is idempotent by observation identity.
**Owning tests / evidence:** EV-10/20; _mine_one and ev.qualify traced.
**Cross-milestone risk:** No claim that any external edit is acoustic ground truth.
**Source:** [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py).

## IF-17 — M12 → M14: Note revision provenance

**Authoritative object/fields:** Before/after note revisions, dictated spans, evidence links, job IDs.
**Frozen versus mutable:** Append-only revisions; typed text and dictated spans have distinct provenance.
**Expected revision/identity:** Canonical occurrence-safe rebase plus one-job changed-region attribution.
**Deletion behavior:** Deleted note/source must close links and revoke derived support.
**Timeout behavior:** Mining must recheck inside writer after queued wait.
**Owning tests / evidence:** EV-14/20; _mine_note_candidates traced.
**Cross-milestone risk:** Typed-only and ambiguous repeated regions abstain; crash evidence gaps remain.
**Source:** [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py).

## IF-18 — M03/M08/M11/M12 → M13: Usage terminal producers

**Authoritative object/fields:** One logical job fact, attempt, original app/time; separate repaste/transform activity.
**Frozen versus mutable:** Latest terminal fact replaces same job; original provenance remains.
**Expected revision/identity:** Partial uniqueness for dictation; actual transaction identity for activity.
**Deletion behavior:** Content expiry does not delete independent permitted usage.
**Timeout behavior:** Typed deletion receipts/reconciliation; ordinary producer failures reported.
**Owning tests / evidence:** EV-15; M13 handoff and analytics contract.
**Cross-milestone risk:** No new execution here; independent cross-producer reduction required.
**Source:** [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md).

## IF-19 — M02/M03 → M14: Training examples into speech profile

**Authoritative object/fields:** Example/revision/raw artifact linked to logical job and attempt.
**Frozen versus mutable:** Per-attempt examples legitimate; speech denominator must be capture-based.
**Expected revision/identity:** Example ID is not a distinct-capture proof.
**Deletion behavior:** Dead raw evidence invalidates support; per-example exclusion has explicit scope.
**Timeout behavior:** Final profile writer checks exact read inputs and retries changes.
**Owning tests / evidence:** EV-19/15; ProfileService source traced.
**Cross-milestone risk:** CROSS-AUDIT-03.
**Source:** [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py).

## IF-20 — M05/M02 → M14: Frozen applied vocabulary into technical terms

**Authoritative object/fields:** Applied IDs plus vocabulary_applied_rules manifest.
**Frozen versus mutable:** Historical term meaning fixed; current entry canonical may change.
**Expected revision/identity:** Frozen applied rule revision/payload, not entry ID alone.
**Deletion behavior:** Missing proof cannot be replaced with current dictionary text.
**Timeout behavior:** Profile publication fence currently does not fix historical-name substitution.
**Owning tests / evidence:** EV-07/19/15; collector and profile source traced.
**Cross-milestone risk:** CROSS-AUDIT-04.
**Source:** [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/v2/vocabulary_store.py · writer-authoritative update and revision history](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py).

## IF-21 — M13 → M14/M09: Usage deletion and profile copies

**Authoritative object/fields:** Usage revision and app/hour/mode-derived snapshot fields.
**Frozen versus mutable:** Usage facts mutable independently of retained speech.
**Expected revision/identity:** Read committed usage revision in final writer; revoke Hub epoch.
**Deletion behavior:** Redact usage-derived snapshot copies in same deletion transaction.
**Timeout behavior:** Outcome_unknown reconciles via completion marker.
**Owning tests / evidence:** EV-15; analytics contract and coordinator source traced.
**Cross-milestone risk:** Strong source separation; full active-pane canary run remains NOT_RUN.
**Source:** [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py).

## IF-22 — M14 → M05: Approval and undo delta

**Authoritative object/fields:** Pending candidate, current live payload, canonical scoped entry and delta.
**Frozen versus mutable:** Approval mutates vocabulary only once; later user edits own new revision.
**Expected revision/identity:** Same writer M05 methods, expected revision, operation receipt.
**Deletion behavior:** Stale source cannot grant new approval; later user edits protected on undo.
**Timeout behavior:** Same operation receipt returns prior effect, not second mutation.
**Owning tests / evidence:** EV-07/20; approve/_plan_in traced; undo behavior additionally handoff-reported.
**Cross-milestone risk:** Service reversibility does not establish visible Undo control.
**Source:** [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/vocabulary_store.py · writer-authoritative update and revision history](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py).

## IF-23 — M14 → M13 readiness / M14 export: Shared task qualification

**Authoritative object/fields:** Example/task, current explicit judgments, artifacts, definitions and tiers.
**Frozen versus mutable:** Current qualification can reduce as content/judgment changes.
**Expected revision/identity:** Own job/task, role, retained bytes, digest and current decision.
**Deletion behavior:** Deletion only removes eligibility; cleanup tier may explicitly reduce.
**Timeout behavior:** Readiness is read-only; export has separate publication/reconciliation.
**Owning tests / evidence:** EV-19/20/21; shared qualifier and exporter traced.
**Cross-milestone risk:** Match partitions/assignment when comparing membership, not global counts blindly.
**Source:** [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md).

## IF-24 — M14 splits → M14 export / M15: Family and exposure history

**Authoritative object/fields:** Family, assignment version, memberships, ever-exposed flag.
**Frozen versus mutable:** Old manifests immutable; future exposure only grows.
**Expected revision/identity:** All assignment versions contribute current exposure knowledge.
**Deletion behavior:** Do not erase exposure when examples expire or table repair occurs.
**Timeout behavior:** Assign/expose receipts must reconcile duplicate commands.
**Owning tests / evidence:** EV-21; SplitService and exporter traced.
**Cross-milestone risk:** CROSS-AUDIT-01 covers lost membership authority.
**Source:** [localflow/v2/curation/splits.py · historical exposure and assignment](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/splits.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py).

## IF-25 — M02 → M14 export: Managed artifact files

**Authoritative object/fields:** Plain managed filename, artifact ID, capture digest and file descriptor.
**Frozen versus mutable:** Content immutable; retention may purge source.
**Expected revision/identity:** Confinement + no-follow + regular file + streamed hash comparison.
**Deletion behavior:** Purged/missing selected input aborts before publication.
**Timeout behavior:** File publication cannot be made atomic with SQLite merely by serializing writes.
**Owning tests / evidence:** EV-03/19/21; managed helper and exporter traced.
**Cross-milestone risk:** Ancestor-symlink and all downstream-reader equivalence need local probes.
**Source:** [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py).

## IF-26 — M14 export → Filesystem / Store / Hub: Dataset publication

**Authoritative object/fields:** Export ID, staged package, semantic fingerprint, completion row.
**Frozen versus mutable:** Package immutable after publication; completion receipt is a separate durable fact.
**Expected revision/identity:** Selected dependency recheck and rename in one writer op, commit afterwards.
**Deletion behavior:** Delete queued before publish aborts; published offline copies need explicit policy.
**Timeout behavior:** Timed-out publish leaves staging for admitted operation; rename-before-commit crash remains.
**Owning tests / evidence:** EV-21; build/publish_op traced.
**Cross-milestone risk:** DESIGN-02: conservative recovery, not a claim of cross-filesystem transaction atomicity.
**Source:** [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py).

## IF-27 — M14 Validate → M09 Hub state: Validation result

**Authoritative object/fields:** Destination/fingerprint, validation issues, action generation.
**Frozen versus mutable:** Result fixed for exact package validated; later edit invalidates it.
**Expected revision/identity:** Not currently stored/fenced like ExportRun result.
**Deletion behavior:** Old query cannot make a newer invalid report disappear.
**Timeout behavior:** Synchronous call can stall main thread; do not conflate with writer wait.
**Owning tests / evidence:** EV-11/21; handlers traced.
**Cross-milestone risk:** CROSS-AUDIT-07.
**Source:** [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/ui/state.py · per-key requests, epoch revocation and guarded publication](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/state.py).

## IF-28 — M02 → All later domains: Schema/version and repair authority

**Authoritative object/fields:** Schema version, table families, dependent rows and preimage backup.
**Frozen versus mutable:** Version advances on valid migration; missing history must not masquerade as empty.
**Expected revision/identity:** Version-aware relational-family integrity.
**Deletion behavior:** Repair must preserve deletion/exposure/revocation semantics.
**Timeout behavior:** Failure must leave a usable preimage and no false clean opening.
**Owning tests / evidence:** EV-03/14/15/21; migration source traced.
**Cross-milestone risk:** CROSS-AUDIT-01; live-opening CLI inventory not exhaustive in this audit.
**Source:** [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py).

## IF-29 — M01/M09/M14 docs → M15 authorization: Registry/runbook/current-state evidence

**Authoritative object/fields:** Requirement/suite IDs, actual test entrypoint, check revision/code SHA/status.
**Frozen versus mutable:** Catalog and historical results immutable by role; current readiness explicit.
**Expected revision/identity:** Do not reuse stale instruction results or treat catalog mapping as execution.
**Deletion behavior:** Retain history while marking superseded/invalidated evidence.
**Timeout behavior:** Missing/native/model evidence stays pending, never PASS.
**Owning tests / evidence:** EV-01/17; registry inspected; full DOM/testpath census not closed.
**Cross-milestone risk:** CROSS-AUDIT-08 and coverage gaps.
**Source:** [docs/v2/registry.json · 33 requirements and 22 suite identifiers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/registry.json); [docs/v2/VERIFICATION.html · stable check IDs, instruction revisions and browser-local results](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/VERIFICATION.html); [docs/v2/STATUS.json · implementation-era status and benchmark fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/STATUS.json); [docs/v2/LOCALFLOW_V2_MILESTONES.md · M14/M15 prerequisites and acceptance criteria](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md).

## Functional surfaces the later redesign must preserve

| Surface | Data source | Key actions | Stable identity / async ownership | Qualification |
|---|---|---|---|---|
| Home | Coordinator readiness/recovery summary | Open/retry/recover under job identity | Status revision and current job; no focus-stealing during insertion | Native readiness product check remains open |
| History | HistoryQueryService + HubState | Copy, Paste Again, Retry, Save/Move, Teach, Delete Usage, diagnostics | Rendered row/detail ID, final artifact/hash, query generation and deletion epoch | M09 manual V001–V007; latest content still must be qualified |
| Styles | Profile/style service | Add/update/enable/import as supported | Bound rule ID/revision/baseline form; canonical scope | M10 native evidence reported; V001–V004 remain human |
| Snippets | Snippet service and frozen expansion registry | Add/update/enable/preview as supported | Bound snippet ID/revision and exact generated span | M10 native evidence reported; active-target use remains human |
| Transforms | TransformStore + execution coordinator | Add/update/toggle, choose mode/shortcut, generate/review/accept/undo | Definition ID+revision, candidate/task/target; editor baseline currently weaker | Findings -02/-05/-06; custom prompt editability/selector behavior needs native proof |
| Scratchpad | Note service, editor model and immutable revisions | New, pin, snapshot, attachment, transform, restore, export, delete | Rendered note/revision/caret/arrival; codepoint and UTF-16 boundaries explicit | M12 V001–V005 pending; reported native fixtures are not these human checks |
| Insights | One-snapshot analytics report | Range/app/mode filters, reload, usage controls | Report usage revision plus query generation/epoch | M13 V001–V005 pending |
| Training / Review | TrainingDataService, review/learning/sampling services | Teach/review labels, approve/reject, pair judgment, splits | Example/revision/candidate ID, pair task and both rendered candidate IDs | M14 manual plus required cross-interface regressions; no Hub Undo approval control reported |
| Your Voice | Local deterministic ProfileService | Generate, inspect citations, exclude evidence | Snapshot ID/input revision and source-linked support; usage sources separate | Findings -03/-04; M14 V006 and active expiry checks pending |
| Export | DatasetExporter + offline validator | Select views/destination, build, validate | Export ID and package fingerprint; validation action state currently incomplete | Finding -07; M14 V005 and crash-recovery policy pending |
| Diagnostics | Redacted store/event queries and coordinator | Inspect, export redacted diagnostic evidence | Query generation plus purpose-specific content-free schema | No exhaustive event-canary sweep executed; M09 manual diagnostics pending |
| Models | Engine status and Training subview | Inspect model/readiness and switch supported subviews | Model revision, current process readiness; training identity separate | M11 model gate unresolved; do not infer installed app from main |
| Settings | Config/Store retention and Analytics commands | Apply content/usage retention, delete all usage, supported preferences | Validated policy revision and typed mutation outcomes | M13 native coverage reported; inherited minimum-width Apply Retention defect not independently closed |

## Test binding and release discipline

Before editing, inventory tracked callers and resolve every EV suite to current files, symbols and production-path assertions. Record unresolved mappings rather than manufacturing test names. The companion corpus provides independent semantic oracles and deterministic schedules; every one is NOT_RUN in this review.
No interface is cleared for M15 merely because its owning milestone reported a green isolated suite. Keep static proof, inherited automated evidence, fresh native execution, real-model quality and human product judgment as separate columns.
