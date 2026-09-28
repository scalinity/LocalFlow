# Claude Code LOCAL / Opus 5.5 — Final Cross-Milestone Remediation Handoff

**Repository:** `scalinity/LocalFlow`  
**GPT audited canonical main:** `340c566686c7123bfcf721e16160aacabbe0b97d`  
**Scope:** M01–M14 composition repair and qualification only.  
**GPT target execution:** `NOT_RUN`. All findings below are source-derived allegations to adjudicate locally.

> This is a LOCAL remediation on Daniel's Mac against canonical main after all M01–M14 milestone remediations. Do not reopen milestones wholesale. Reproduce each cross-milestone allegation, repair the narrow owning seam, and preserve all accepted milestone behavior.

Do not perform Quiet Editorial, start M15/M16, inspect Daniel’s live content, or complete his human checks. A later model/native measurement needed to verify a repaired seam is a bounded compatibility check, not permission to launch the M15 campaign. Do not introduce an API provider requirement for the currently deterministic Your Voice feature.

Read the companion audit, interface matrix and declarative corpus before editing. When a companion is unavailable locally, use the embedded allegations and recreate its bindings from the pinned source; do not fabricate a prior test result. Requesting/locating an absent artifact is not permission to widen to private data. Every case has to be bound to a real production seam.

## 1. Safe startup and exact baseline

Run read-only diagnostics first:

```sh
pwd
git status --short --branch
git branch --show-current
git rev-parse HEAD
git remote -v
git worktree list
```

Read current `CLAUDE.md` and any relevant repository instructions. There are historical audit/reviewer worktrees: preserve them. Never automatically reset, clean, stash, discard, force checkout, remove worktrees or overwrite work. If proceeding would overwrite work, STOP and report the exact conflict. Do not reuse an unrelated dirty worktree.

Then:

```sh
git fetch --all --prune --tags
git rev-parse origin/main
```

Compare the exact remote SHA against the audited SHA above. If main has moved, record every intervening commit and determine which allegations/evidence paths changed. Do not silently transplant a reproduction to a different base or claim the old audit covers new production.

Only when safe under worktree/dirty-state rules:

```sh
git switch main
git merge --ff-only origin/main
```

Create a dedicated cross-milestone remediation branch with a unique descriptive name. Freeze the audited failing-base snapshot and record local pre-sync, remote-at-sync and post-sync SHAs. Do not change production until the interface inventory and fail-first plan exist.

## 2. Source and evidence inventory BEFORE edits

Read current README, START_HERE, STATUS, ORCHESTRATION, spec, implementation/evaluation plan, milestones, contract index, registry, all M01–M14 handoffs and their remediation addenda, acceptance receipts and VERIFICATION. Separate historical measurements from current campaign state. Resolve the M11 replay lineage correctly; the canonical accepted production is `9a049b3`, not the older cloud-only branch SHA.

Build a tracked-file caller ledger first. Use `git grep` and/or `rg` scoped to actual tracked files. A safe inventory pattern is:

```sh
git ls-files -z | xargs -0 rg -n --no-heading   'job_id|attempt|artifact_id|final_text|context_snapshot|destination|usage_facts|learning_candidates|profile_snapshots|split_assignments|outcome_unknown|expected_revision'
```

Also search `role`, `mode`, `scope`, `insert`, `clipboard`, `note`, `export`, `generation`, `revision`, every actual service class, and every symbol implicated by a finding. Enumerate Store.submit wrappers, callback main-thread owners, direct SQL readers/writers, file reads/unlinks, event/exception emits, config exports and all live-store-opening tools. Do not let untracked fixtures substitute for real callers. Avoid dumping private filesystem contents into evidence.

The ledger must record producer -> consumer -> identity/revision -> operation admission -> deletion/liveness -> owning tests. Resolve **every one of the 33 requirement IDs and 22 suite IDs** to current test files/functions, production calls and qualification state. The existing registry is a catalog, not proof those test paths exist or run. No connector search miss is evidence of absence.

Independently enumerate actual VERIFICATION check elements and stable IDs—not raw HTML string counts. Validate duplicates, per-milestone counts, `data-rev`, `data-code`, localStorage schema and changed-instruction behavior. The audit did not complete the full DOM census and did not receive Daniel’s browser-local state. Do not invent his results.

## 3. Environment and isolation

Record OS/hardware/RAM, Python/virtualenv, source and model revisions, cleanup template/config, available native bindings, microphone/AX permissions and test entrypoints without exposing private paths. Use synthetic stores and owned windows only. Never migrate, clean, copy-export or benchmark Daniel’s live store as a substitute for synthetic fixtures.

The repository’s documented tests are standalone `.venv/bin/python` entrypoints; do not assume pytest is installed or that a planned test command exists. Inspect each current entrypoint. A fake worker/generator is appropriate for deterministic seam reproduction but is not model-quality evidence. A native shell smoke test is not an interaction test.

Corpus `origin: synthetic` describes the audit fixture provenance. Profile witnesses must nevertheless use the real collector in an isolated simulated live-capture workflow, letting it set its legitimate envelope origin. Do not hand-forge eligible database rows and then claim a supported producer path, and do not pass envelope origin=synthetic and mistake its deliberate exclusion for a tested retry seam.

## 4. Allegation adjudication rules

For each CROSS-AUDIT ID, choose exactly one initial disposition: reproduced, refuted, narrowed, already fixed, test-gap only, design-only, or native/manual/model unresolved. Freeze fail-first evidence before the first repair. Record the relevant branch reached, independent expected-state ledger, exact state/identity before and after, and the concrete assertion failure. Static allegations are not automatically true.

A reproduction must cross the actual producer/consumer boundary. Unit-testing only a helper cannot prove or repair an integration defect requiring a collector, Store and profile, or a Hub form, Store and export. Preserve a successful sequential/control case so a harness that merely breaks setup cannot look convincing.

The eight allegations below are complete enough to start binding; all predictions are NOT_RUN in the GPT audit.

### CROSS-AUDIT-01 — Current-version repair does not protect the later relational families

**Severity:** HIGH · **Confidence:** High static confidence; target reproduction NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M02. **Compatibility consumers:** M10, M13, M14.

**Producer → consumer:** Store schema repair at schema 13 → Split exposure, profile support and reversible learning.

**Canonical requirement:** LF-R03/R25/R30/R32; loss of an authority table must not be mistaken for a clean empty feature.

**Source locations:** [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [localflow/v2/curation/splits.py · historical exposure and assignment](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/splits.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py).

**Current behavior:** The current-schema repair path knows the later table names, but _CORE_DEPENDENTS stops at the older core families plus notes. training_memberships, profile_evidence, usage_facts and learning_vocabulary_deltas are not in that dependent-loss refusal map.

**Composition failure mechanism:** A missing table is recreated with CREATE TABLE IF NOT EXISTS even when a surviving later feature depends on its lost history. Exposure is recovered only from surviving membership rows; profile scrubbing walks surviving support links. Recreating either table empty removes the evidence needed to detect that loss. This is a torn/corrupt-store recovery path, not a claim that arbitrary SQL must be impossible.

**Minimal deterministic reproduction:**

1. Create a synthetic current-version store through supported services; create at least 10 families, mark a chosen family exposed, and keep the assignment rows.

2. Close cleanly, copy the store, drop only training_memberships in the copy, then reopen through the normal migration/backup route.

3. Assign again with a fixed seed that would put the selected family into frozen_test if its exposure history were absent; inspect the resulting qualification.

4. In separate copies, drop profile_evidence while retaining a current supported snapshot. For learning_vocabulary_deltas, first approve a created entry and then user-edit its canonical name without changing the single approved alias; drop the delta table, reopen and invoke undo.

**Expected:** Fail closed with a recoverable corruption report and untouched backup, or reconstruct the entire lost authority from an independently sufficient canonical source. Never silently call the relational family intact.

**Likely actual / verification boundary:** Static repair permits the tables to be recreated empty. Exposure can then be forgotten, missing support links defeat link-driven invalidation, and undo with no delta falls back to revision_after_approval=None. For a created rule whose alias/enabled fields still match, that fallback can disable the later user-edited entry. All local witnesses remain NOT_RUN.

**Existing milestone coverage:** M02 repair tests and the M12 LOCAL-M12-02 repair regression are reported in their handoffs; M13/M14 report isolated passing suites.

**Why that coverage does not prove composition:** Those reports do not prove the new dependency-family loss cases, and an additive-migration success test is not a current-version corruption test.

**Regression recommendation:** A table-family matrix must cross Store.open -> feature read/write -> qualification, with backed-up preimage and sibling-table preservation assertions.

**Narrow repair direction:** Add a version-aware, authoritative family-integrity manifest. Distinguish a legitimate pre-feature upgrade from table loss at or after that feature version. Do not simply refuse every absent future table in an older valid store.

**M15 impact:** Block trust in repaired-store datasets/profiles until reproduced and repaired or conclusively refuted. Include usage/config families in the same inventory; their exact effects require separate witnesses.

**Corpus binding:** LF-CROSS-F001; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

### CROSS-AUDIT-02 — Transform revision numbers can name a history payload different from the live definition

**Severity:** HIGH · **Confidence:** High for the source-level interleaving mechanism; production caller concurrency must be established locally; NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M11. **Compatibility consumers:** M09, M10, M14.

**Producer → consumer:** TransformStore.update_transform → Frozen transform selection and M14 offline task-definition lineage.

**Canonical requirement:** LF-R17/R30/R32; a revision must identify the exact committed definition, not merely a monotonic counter.

**Source locations:** [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py); [docs/v2/contracts/transforms.md · Definitions and revisions; preserved exact definition; task identity](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/transforms.md); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py).

**Current behavior:** update_transform reads and merges the definition before its writer operation. Inside the operation it reads only the current revision number. SQL updates just requested columns, but the appended definition JSON is built from the earlier full merged object.

**Composition failure mechanism:** Two interleaved supported updates can preserve both changes in the live row while appending a stale full definition at the same new revision. M14 transform_target_in resolves that revision from transform_revisions, so downstream offline reconstruction can inherit the wrong instruction set.

**Minimal deterministic reproduction:**

1. Seed transform T revision 1 with prompt P1 and enabled=True.

2. Use barriers after the initial definition reads so operations A and B both read revision 1. A changes prompt to P2; B changes only enabled to False.

3. Let A commit, then let B commit. Read the complete live definition and the preserved history row for its current revision.

4. Freeze/use that revision through the real transform snapshot path, and inspect the definition a real candidate/export qualification resolves.

**Expected:** Live definition and preserved definition at one revision are identical. A stale expected revision either refuses explicitly or is merged entirely inside one writer operation.

**Likely actual / verification boundary:** The live row can be P2/disabled at revision 3 while the revision-3 JSON is P1/disabled. This prediction follows the SQL and outer merged object; no target execution was performed.

**Existing milestone coverage:** M11 reports versioned definitions and same-task tests; M10 reports boolean/built-in-mode compatibility checks.

**Why that coverage does not prove composition:** Unique revision numbering is not equality of revision content. Existing reported tests do not establish the two-reader/two-writer manifest witness. The local inventory must establish a real supported concurrent definition-writer schedule; a unit-level interleaving alone does not prove ordinary single-threaded Hub reachability.

**Regression recommendation:** Cross TransformStore -> frozen definition/candidate -> evidence/export resolution. Independently compare all semantic fields, not just the revision integer.

**Narrow repair direction:** Read, validate, merge, mutate and serialize the complete writer-current definition in one transaction. Add expected_revision admission for editor actions. Keep legacy immutability, built-in mode binding and no-op behavior.

**M15 impact:** Block transform-task lineage qualification until fixed/refuted; rerun affected M11/M14 compatibility. No wholesale transform-engine rewrite is indicated.

**Corpus binding:** LF-CROSS-F002; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

### CROSS-AUDIT-03 — Retry examples can inflate Your Voice’s logical-dictation count and interpretation floor

**Severity:** HIGH · **Confidence:** High static confidence; target reproduction NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M14. **Compatibility consumers:** M02, M03, M13.

**Producer → consumer:** Retry collector creates a new training example for the same job → ProfileService._eligible/_compute_once.

**Canonical requirement:** Central logical-job invariant; LF-R20/R21/R30; a retry is not another spoken capture.

**Source locations:** [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md).

**Current behavior:** A retry starts a fresh capture context and can publish a new example ID under the same logical job/family. Profile eligibility selects latest revisions per example and deduplicates identical text; the floor counts len(eligible), and phrase support is also per example.

**Composition failure mechanism:** A retained raw-bearing failed attempt and a successful retry with non-identical raw text can both count as separate dictations. M13 correctly replaces one usage fact, while M14 describes multiple examples as multiple dictations. Exact-text deduplication is not logical-capture deduplication.

**Minimal deterministic reproduction:**

1. Create five synthetic captures with collection enabled. For each, publish a raw-bearing attempt that fails after ASR, then invoke the actual retry coordinator for the same job.

2. Use controlled ASR outputs that differ slightly between attempts so text deduplication cannot hide the seam; retain enough words for the default 2,000-word floor.

3. Settle the successful retry, compute usage and Your Voice, and inspect eligible IDs, dictation counts, phrase support and interpretation eligibility.

**Expected:** Usage and speech-derived denominators agree on the five logical captures. Define explicitly which attempt contributes profile speech; keep legitimate per-attempt training evidence without counting it as independent capture support.

**Likely actual / verification boundary:** Ten distinct eligible examples can satisfy the ten-dictation floor even though only five logical captures occurred. Qualification depends on those attempts meeting the existing eligibility predicate; the local test must demonstrate the complete supported producer path.

**Existing milestone coverage:** M13 reports retry exactly-once tests; M14 reports profile eligibility, exact-input fences and threshold tests.

**Why that coverage does not prove composition:** One tests usage rows and another supplies profile examples. Neither reported result proves the real retry collector -> profile denominator seam.

**Regression recommendation:** Use the real collector and coordinator with controlled worker replies; compare against an independently maintained set of original capture IDs and original capture durations.

**Narrow repair direction:** Canonicalize speech-profile support by logical capture/job with an explicit attempt-selection policy. Do not impose a global unique job constraint on training_examples or discard useful historical attempts.

**M15 impact:** Block claims based on current profile dictation/support counts until adjudicated. This finding does not allege that M13 currently double-counts usage.

**Corpus binding:** LF-CROSS-F003; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

### CROSS-AUDIT-04 — Speech-derived technical terms are renamed through current vocabulary state

**Severity:** MEDIUM · **Confidence:** High static confidence; target reproduction NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M14. **Compatibility consumers:** M05, M02.

**Producer → consumer:** Frozen applied-rule IDs and applied-rules artifact → Your Voice technical-term labels and citations.

**Canonical requirement:** LF-R21/R30; a current dictionary edit cannot rewrite what a past utterance evidenced.

**Source locations:** [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/v2/vocabulary_store.py · writer-authoritative update and revision history](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py).

**Current behavior:** Profile gathers applied_rule_ids from eligible envelopes, then resolves the term by the current enabled/approved vocabulary_entries canonical value. The collector already records the frozen applied-rules artifact.

**Composition failure mechanism:** An entry ID is stable across canonical-name revisions. Renaming an entry therefore relabels historical speech support without new speech, bypassing the stronger frozen manifest the producer supplied.

**Minimal deterministic reproduction:**

1. Use approved vocabulary entry E, canonical Orion SDK, in retained eligible dictations through the real normalization collector.

2. Change E canonical to Lyra SDK through VocabularyStore with expected_revision; do not dictate again.

3. Compute a new profile and inspect the technical term and its cited examples. Compare with the frozen applied-rules payload from those examples.

**Expected:** The speech-derived term remains the term actually applied at capture, or is explicitly unavailable. A separate current-dictionary summary may show Lyra SDK with its own source label.

**Likely actual / verification boundary:** The technical term can become Lyra SDK while keeping citations to the older Orion SDK dictations.

**Existing milestone coverage:** M05 reports revision-history correctness; M14 reports that technical terms must have eligible speech support.

**Why that coverage does not prove composition:** Existence of a cited example and a current entry ID does not prove the cited term occurred under that entry revision.

**Regression recommendation:** Cross M05 normalization -> collector manifest -> vocabulary rename -> profile; include rename, disable, deletion and frozen-manifest purge controls.

**Narrow repair direction:** Resolve speech terms from the owner/role/digest-qualified frozen applied-rules artifact. Keep dictionary-wide usage counters and current names distinctly labeled.

**M15 impact:** Repair before treating technical-term profile cards as reliable product evidence; does not require an LLM or new profile architecture.

**Corpus binding:** LF-CROSS-F004; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

### CROSS-AUDIT-05 — Transforms Update submits a stale full form without revision admission

**Severity:** MEDIUM · **Confidence:** High for full-form/no-CAS behavior; supported stale-form writer schedule requires local/native proof; NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M11. **Compatibility consumers:** M09, M10.

**Producer → consumer:** Transforms editor rendered form → TransformStore.update_transform.

**Canonical requirement:** LF-R13/R17; edits must be bound to the rendered revision and may not silently overwrite unseen fields.

**Source locations:** [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py).

**Current behavior:** The Transforms pane has no counterpart to the Styles/Snippets bound editor baseline and expected revision. Update sends name, mode, prompt, targets, shortcut and auto-apply from the whole form.

**Composition failure mechanism:** If a supported service update changes the definition after the form was filled, a later unrelated form edit can overwrite that unseen change. Ordinary table selection itself fills the form synchronously, so a click-to-wrong-row race is not asserted here.

**Minimal deterministic reproduction:**

1. Render transform T revision 1 in the real Hub controller.

2. Through TransformStore, change T prompt or auto-apply at revision 2 while the original form remains displayed.

3. Change only the name field in the old form and invoke Update. Observe the current definition, history and next job snapshot.

**Expected:** Refuse a stale revision or merge only intentionally edited fields under an explicit, writer-authoritative policy. Do not silently reverse an unseen auto-apply or instruction edit.

**Likely actual / verification boundary:** The old full form is submitted without expected_revision and can overwrite the newer prompt/auto-apply value.

**Existing milestone coverage:** M09 rendered-row discipline and M10 Styles/Snippets editor repairs are reported; Transforms CRUD uses a separate older path.

**Why that coverage does not prove composition:** Selection uses stable IDs, but stable row identity is not a stable content revision or an edited-field mask. Establish the supported writer that can change the row while the editor remains open; do not invent a second production caller.

**Regression recommendation:** An actual Hub form -> TransformStore -> next frozen job test; preserve a normal sequential-edit positive control.

**Narrow repair direction:** Use a transform editor binding of ID, revision and baseline form. Share the M10 discipline where appropriate, without coupling domain models or redesigning the UI.

**M15 impact:** Functional repair before product-surface handoff; native editor accessibility still needs its own qualification.

**Corpus binding:** LF-CROSS-F005; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

### CROSS-AUDIT-06 — Transforms Add reports an admitted timeout as not saved and retries with a new identity

**Severity:** MEDIUM · **Confidence:** High static confidence; target reproduction NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M11. **Compatibility consumers:** M02, M09, M10.

**Producer → consumer:** Hub Transforms Add → Store admission and TransformStore.add_transform.

**Canonical requirement:** Unknown-outcome invariant; LF-R13/R17; an admitted timeout is not proof of noncommit.

**Source locations:** [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py).

**Current behavior:** The generic exception handler displays not saved: TimeoutError. add_transform generates a fresh transform ID unless supplied one; this Hub caller supplies neither a stable ID nor a durable operation identity.

**Composition failure mechanism:** After a writer-admitted timeout, the first Add may commit. A retry of the same form creates a second logical definition. M10 pending-add identities and M14 receipt handling do not automatically protect this M11 path.

**Minimal deterministic reproduction:**

1. Fill a custom transform form with no shortcut, so no shortcut collision masks duplicate creation.

2. Hold the admitted insert operation behind a deterministic writer barrier and inject/expire the caller wait without cancelling the queued operation.

3. Record the visible not-saved message, release the writer, and retry the unchanged form after commit.

4. Inspect definitions, revisions and next-job registry choices.

**Expected:** Unknown/pending is shown after admission; the same operation identity reconciles to one definition. A known pre-admission failure permits a fresh retry.

**Likely actual / verification boundary:** Two different IDs can be created for one intended Add, after the UI described the first operation as not saved.

**Existing milestone coverage:** M02 documents timeout admission; M10/M13/M14 report explicit unknown outcomes. This handler still catches all other exceptions as failure.

**Why that coverage does not prove composition:** A service-level timeout test or a different pane’s receipt test does not exercise this Add caller.

**Regression recommendation:** Real Hub Add -> real TransformStore/Store admission, with independent definition-count and ID assertions and a not-started control.

**Narrow repair direction:** Preallocate a stable ID/operation key for the form attempt, implement writer-idempotent reconciliation, and display not_started/failed/outcome_unknown distinctly.

**M15 impact:** Fix before a Hub handoff can claim consistent mutation semantics. Do not globally replace every exception with unknown.

**Corpus binding:** LF-CROSS-F006; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

### CROSS-AUDIT-07 — A training refresh can erase the completed Export Validate result

**Severity:** MEDIUM · **Confidence:** High static confidence; target reproduction NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M14. **Compatibility consumers:** M09.

**Producer → consumer:** Export Validate action → Training-data refresh and export-pane renderer.

**Canonical requirement:** LF-R13/R32; an older asynchronous read cannot overwrite a newer user-visible validation result.

**Source locations:** [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py).

**Current behavior:** exportValidate_ synchronously writes a report directly into export_text. It neither stores that report in the pane model nor advances the training-query/action generation. _refresh_export_pane later rewrites the same widget from last_export or the no-export instructions.

**Composition failure mechanism:** A pre-validation refresh remains a valid generation in HubState and can repaint over the newer action result. ExportRun has an action token, but Validate is outside that state model. This is pane-specific integration, not proof that the shared query engine is broken.

**Minimal deterministic reproduction:**

1. Start a real training/export refresh and hold its main-thread publication after its result has been obtained.

2. Validate a synthetic dataset with a known issue and observe the completed invalid report.

3. Release the held refresh and drain only that publication. Inspect the rendered report and destination identity.

**Expected:** The validation result remains visible, bound to the validated destination/fingerprint, until superseded by a newer explicit action or clearly invalidated.

**Likely actual / verification boundary:** The widget is replaced by old export status or generic instructions. Exported bytes need not change for the feedback to become misleading.

**Existing milestone coverage:** M09 generation tests and M14 export/native checks are reported; M14 already lists this residual.

**Why that coverage does not prove composition:** A query-to-query stale test does not cover a direct widget action followed by a still-current query result.

**Regression recommendation:** Native/headless MainQueue barrier test across Validate and training refresh, including pane switch and two destinations.

**Narrow repair direction:** Represent validation in the pane state with destination identity and an action generation; fence older refresh publication. Consider async validation separately for main-thread responsiveness.

**M15 impact:** Close before functional UI qualification. Narrow repair; no Quiet Editorial work.

**Corpus binding:** LF-CROSS-F007; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

### CROSS-AUDIT-08 — STATUS mixes implementation-era details with current campaign state

**Severity:** LOW · **Confidence:** High static confidence; target reproduction NOT_RUN · **Execution:** NOT_RUN

**Primary owner:** M14. **Compatibility consumers:** M01, M13.

**Producer → consumer:** STATUS.json retained implementation record → Human/agent readiness interpretation.

**Canonical requirement:** LF-R28; distinguish historical provenance, current state and verified evidence.

**Source locations:** [docs/v2/STATUS.json · implementation-era status and benchmark fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/STATUS.json); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [ORCHESTRATION.html · campaign state and M15 dependency eligibility](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/ORCHESTRATION.html).

**Current behavior:** Current STATUS text still describes the older store/benchmark implementation, while Store is schema 13 and the current M14 handoff reports the stronger remediation and higher writer-wait measurements.

**Composition failure mechanism:** Consumers can mistake historical implementation-era details for current qualification. The STATUS document schema_version=1 is its own JSON format, not the database version; a historical source_commit is not inherently wrong.

**Minimal deterministic reproduction:**

1. Compare STATUS descriptions and benchmark labels against Store schema 13 and the M13/M14 remediation addenda.

2. Classify each discrepancy as historical provenance, stale current assertion or ambiguous ownership; preserve historical fields rather than rewriting them as new measurements.

**Expected:** One unambiguous current campaign state with explicit links to historical implementation and final remediation evidence.

**Likely actual / verification boundary:** Current and historical meanings are not consistently separated in STATUS. This does not negate the accepted production lineage.

**Existing milestone coverage:** Registry and orchestration validation are reported, but the registry catalog has no benchmark/source freshness assertion.

**Why that coverage does not prove composition:** A valid JSON document and complete requirement catalog do not prove semantic freshness.

**Regression recommendation:** Document-state checker with independently derived current DB version and explicit historical/current tags; preserve intentional provenance.

**Narrow repair direction:** Add or clarify current-remediation fields and evidence links; retain old measured results as historical, and keep M11 gating explicit.

**M15 impact:** Documentation closure required before M15 authorization; no production behavior change by itself.

**Corpus binding:** LF-CROSS-F008; independently classify reproduced/refuted/narrowed/already-fixed/test-gap/design/native-unresolved before editing.

## 5. Additional coverage and residual decisions

**Preserve already strong seams.** History Teach carries the rendered final artifact/hash into the writer. M14 approval uses M05 canonical scope and writer methods. Note mining uses M12 occurrence-safe rebasing and drops typed-only changes. Usage deletion redacts usage-derived profile copies without deleting speech. Readiness and export share owner/role/task predicates. Strict replacement never silently becomes ordinary dictation.

**Normalize ordering.** The coordinator consumes one M04/M05/M10 normalization result, including snippet and file-reference edits, then maps protected output spans before M07. Inventory the actual internal proposal/conflict order; do not assume milestone order. Raw bypasses this stage. A permitted retry with no old policy may use an explicitly labeled new policy, but must not rewrite original capture provenance or borrow another job’s context.

**Final text is purpose-specific.** Delivered/display final, eligible raw speech, cleanup-supervised pair, transform task and acoustic reference are different authorities. Do not replace them with a universal latest-text fallback. Missing required final/source means unavailable or a named weaker qualification tier, not invented raw truth.

**Native functional probes.** Exercise real custom transform prompt typing/focus, the NSTextView/control methods used by the form, stale editor admission, Validate repaint, active deletion, Insights, Review/A-B and Your Voice. Reproduce the inherited minimum-width Apply Retention geometry lead. Do not mark an AppKit interaction passed from fake widget objects alone.

**Export publication crash.** Hook after staging-to-destination rename and before Store commit; kill only an owned child; reopen the synthetic store; inspect destination validity, receipt absence and moved-aside files. Retry the same ID with and without later consent/content changes. Choose a bounded conservative reconciliation/journal or explicit orphan/quarantine policy. Never invent a committed receipt or new current consent. A missing receipt is not proof a valid published package does not exist.

**Direct-SQL pair forgery.** Keep supported producer admission and export requalification. Treat database-forgery cases as corruption defense in depth, not a mandate for impossible SQL-proof service security. Prove all supported producers before accepting that threat-model boundary.

**Undo approval.** Separate service reversibility, missing visible Hub control and the later product phase. Record an explicit functional obligation/decision; do not claim a hidden API is an already usable control. Preserve later user edits. For a lost delta table, test a created learned entry whose canonical name was edited later while its single approved alias remained unchanged; the legacy fallback must not silently disable that edited entry after v13 repair.

**Your Voice remains local/deterministic.** No API key/network/provider redesign. Correct logical-capture counting and historical term provenance without discarding valid per-attempt training evidence.

**Privacy inventory.** Inspect every generic event and exception path with separate synthetic canaries for transcript, note, corrected text, filename/path, app/workspace/profile names, vocabulary/derived phrases and dataset text. Governed artifacts may contain their authorized content; generic diagnostic envelopes may not silently inherit it.

**Repair/backup inventory.** Build current-version relational-family loss probes, clean historical upgrade fixtures and interrupted migration fixtures. Inventory app, export CLI, offline validator and all dev/benchmark live-store openers. Prove backups before any synthetic migration that requires them. Never report absent-table recreation as healthy without the domain’s independent integrity assertions.

## 6. Ordered execution and evidence

Follow this order; do not skip failing-base evidence or independent review:

1. Safe sync and exact SHA comparison.
2. Environment and native/model boundary inventory.
3. Complete tracked caller/interface, main-thread, event/file and test/backup inventories.
4. Freeze the audited failing base and source hashes.
5. Bind the declarative corpus to real production seams.
6. Reproduce material allegations and preserve failing-base receipts.
7. Adjudicate design concerns and threat-model boundaries explicitly.
8. Add fail-first cross-interface regressions with independent oracles.
9. Make narrow owning fixes, preserving neighboring contracts.
10. Run portable corpus cases.
11. Run deterministic stateful schedules with barriers, not sleeps.
12. Run metamorphic checks, including reduced-authority monotonicity.
13. Run mutations and adjudicate invalid/equivalent/surviving cases honestly.
14. Run affected M01–M14 compatibility and a broad final portable sweep.
15. Run owned native functional checks for implicated surfaces.
16. Run bounded current model-backed compatibility where needed and feasible; do not start the M15 campaign or invent human judgments.
17. Validate benchmark work/denominators with no-op/delay controls.
18. Run isolated reference-Mac performance and pairwise contention.
19. Freeze first-pass production SHA.
20. Obtain a fresh-context independent review in a separate read-only worktree.
21. Independently reproduce every reviewer allegation in the main remediation session.
22. Repair only confirmed review findings and keep adjudications for refuted/narrowed ones.
23. Rerun all affected/final evidence after the last production change.
24. Reconcile docs/current state/registry after code and evidence converge.
25. Store cross-milestone receipts in the repository’s existing evidence conventions.
26. Update verification instructions only when their behavior or supersession truly changed; never mark human checks yourself.
27. Realign orchestration while retaining the M11/M15 qualification gate.
28. Commit/push/merge only complete work under current repository rules.
29. STOP. Do not start Quiet Editorial, M15 or M16.

Every test exclusion needs its exact reason: native unavailable, model unavailable, unrelated to changed seam, or explicitly pending human action. NOT_RUN is never PASS. Do not blindly run giant unrelated model suites, but do not excuse affected compatibility simply because earlier milestones passed in isolation.

## 7. Stateful, metamorphic and mutation requirements

Use the companion corpus’s 15 stateful schedules and 15 multi-hop scenarios. In particular bind retry -> cleanup -> insertion -> usage, scoped approval/undo -> next normalization, frozen destination -> transform -> insertion, note provenance -> mining -> qualification, Delete Usage -> profile redaction, artifact expiry -> profile/export, exposure -> older split export, and unknown action -> Hub retry -> one effect.

The export-after-recheck race has a precise linearization rule: a deletion can queue after the recheck but cannot commit inside the still-running single-writer publish operation. Do not deadlock your harness waiting for that impossible commit. Test both legal operation orders and the separate rename-before-DB-commit crash.

A mutation is KILLED only if the intended production branch was reached AND an independent semantic assertion failed. Import errors, setup exceptions, unrelated crashes and a driver that never exercised the branch are INVALID. Report these counts separately. Include mutations that restore each repaired seam, not only generic preexisting mutants.

Use the 12 metamorphic relations, especially: adding attempts does not add captures; deleting support removes capability; narrowing scope cannot broaden effects; post-freeze context changes cannot rewrite the job; pending/rejected learning does not change output; exposure never becomes newly blind; older publications cannot win; and deletion of an unrelated source does not invalidate an otherwise unaffected export.

## 8. Performance qualification after correctness

Use the current reference Mac and pinned cached model revisions. Do not run compatibility tests or other heavy workloads concurrently unless the experiment explicitly measures contention. Collect a fresh real-pipeline baseline; never add historical component medians and call the sum E2E.

Report separately:

- Release-to-terminal dictation p50/p95/p99 by length and outcome, plus retry-start-to-terminal where applicable.
- Background operation wall time, with real-work counts and fingerprints.
- Store-writer wait p50/p95/p99 and worst observed wait.
- Main-thread heartbeat/interaction stall p50/p95/p99 and worst observed stall.
- Controlled pairwise contention: dictation plus exactly one of profile, export, mining, Insights, Scratchpad autosave or Hub search.

Preserve original capture/release clock semantics. Report fixture/sample counts, warmup/cold/warm distinctions, model/config/template revisions, fallback strata and actual destination receipt. Do not present failed/fallback-rescued work as successful model-path work. The historical M14 205/174 ms writer maxima are comparison leads, not fresh results or permission to weaken validation.

## 9. Mandatory independent review

The reviewer gets a fresh context and a separate read-only worktree at the frozen first-pass production SHA. Provide the audit, original failing-base receipts, change diff, corpus, interface inventory and first-pass evidence. Do not tell the reviewer to confirm your conclusions.

Reviewer focus: job versus attempt versus evidence identity; definition and rendered-revision authority; scope/context freeze; unknown writes/idempotency; deletion/expiry across derived copies; note provenance; schema-family integrity and backup entrypoints; event/private-content leakage; readiness/export agreement; exposure monotonicity; current profile support; real-work benchmark validity; stale Hub publications; and documentation-state drift.

The main session independently reproduces every allegation before accepting it. Freeze final production only after confirmed review defects are repaired. Rerun final affected evidence after the last production edit; a review of an earlier SHA is not a review of the final code.

## 10. Manual/model gate handling and documentation

Do not perform or mark Daniel’s human checks. Preserve M12-V001–V005, M13-V001–V005, M14-V001–V007 and M11-V001–V006, plus the genuinely pending earlier checks. Validate actual current instruction revisions/code refs from the runbook; do not infer completion from historical handoff text or browser storage that was never supplied.

The M11 current handoff records the actual 40-case model run with one misdirected review, 14 output-limit fallbacks and exit 1. Its formerly blind cases are now exposed. Portable/native success does not close that gate; neither does calling it NOT_RUN. Track remaining model/human prerequisites separately from repaired composition. Do not begin M15 to hide unresolved composition work.

A new owned native test may supersede the mechanical part of a human check only under explicit runbook policy, with a cited new receipt and preserved history. Human product-quality judgment is not automatically superseded.

After final code/evidence converges, reconcile STATUS, ORCHESTRATION, all affected handoffs, acceptance receipts, registry and VERIFICATION. Distinguish historical implementation provenance, historical results and current campaign state. Keep STATUS document schema_version separate from DB schema. Do not rewrite old measurements as if rerun today.

## 11. Evidence privacy and Git rules

Use existing repository evidence conventions; do not create a parallel untracked truth. Store audited/source SHAs, caller inventory, adjudications, corpus/stateful/metamorphic/mutation execution, compatibility, native/model boundaries, benchmark validity, independent review and final disposition.

Before EVERY evidence/docs commit, scan added content for `/Users/`, `scratchpad/`, session UUID/path fragments, temporary worktree paths, live app names, live transcripts/notes, personal profile terms and exported synthetic absolute paths. Truncated tracebacks may leak a path suffix without its `/Users/` prefix. Sanitize with meaning-preserving opaque IDs and retain hashes/relative fixture identities.

Read and follow current CLAUDE.md. No force push. No Co-Authored-By/attribution lines unless current explicit repository instructions actually require them; the audited rule prohibits them. Preserve accepted milestone history. Never reset/clean/stash/delete historical worktrees automatically. Completed remediation may be pushed/merged under current rules; incomplete work must not be merged. Resolve a moving main or conflict deliberately rather than guessing.

A complete automatable campaign with manual checks outstanding may use `CROSS_MILESTONE_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION` or the repository’s truthful equivalent. Do not use that state if required automated/native/review/performance gates did not converge. In all cases keep M15-gating model/human limitations explicit.

## 12. Required final report

1. GPT audited SHA.
2. Local pre-sync SHA.
3. Remote main at sync.
4. Local main after sync.
5. Remediation branch.
6. Environment.
7. Interface/caller inventory totals and unresolved mappings.
8. First-pass production SHA.
9. Final production SHA.
10. Final evidence/docs SHA.
11. Files changed.
12. Finding dispositions with failing-base evidence.
13. Corpus totals.
14. Stateful totals.
15. Metamorphic totals.
16. Mutation totals by killed/survived/equivalent/invalid/not-run.
17. Independent-review findings and main-session reproduction.
18. Portable compatibility sweep.
19. Owned native functional matrix.
20. Job/attempt identity result.
21. Final-text/mode result.
22. Scope/context result.
23. Insertion/Scratchpad result.
24. History/Hub identity result.
25. Analytics exactly-once result.
26. Deletion/retention result.
27. Artifact/path authority result.
28. Schema/migration/backup result.
29. Learning/vocabulary result.
30. Readiness/export/offline closure result.
31. Your Voice/profile result.
32. Family/exposure result.
33. Documentation/state/registry/verification reconciliation.
34. Performance with separate denominators.
35. M15 readiness matrix.
36. Manual/native/model checks remaining.
37. Residual risks and explicit design decisions.
38. Push/merge state.
39. Truthful completion state.

Then STOP.

The subsequent sequence is cross-milestone correctness closure -> dedicated Quiet Editorial desktop-companion redesign -> independent UI/product-quality review -> M15 qualification -> M16 final integration/acceptance. This handoff does not authorize those later phases or a change to domain contracts for visual redesign.
