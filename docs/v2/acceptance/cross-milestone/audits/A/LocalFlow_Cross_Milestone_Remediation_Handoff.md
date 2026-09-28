# LocalFlow — Cross-Milestone Remediation Handoff

**Base reviewed:** `340c566686c7123bfcf721e16160aacabbe0b97d`  
**Repository:** `scalinity/LocalFlow`  
**Prepared:** 2026-09-28

This is a proposed local implementation-session handoff. The audit itself performed no repository writes or test/model/native execution. Begin with identity and scope verification; do not assume the local checkout or installed app matches GitHub main.

## Copy-ready session instruction

You are the local remediation implementer for LocalFlow's cross-milestone M01–M14 review. Read the supplied audit, interface matrix, corpus and this handoff. Work spec-first, preserve accepted behavior, and use synthetic stores/fixtures. Do not start M15 model qualification, training, recording, external insertion or live-data migration as a side effect of these repairs.

### 1. Establish and freeze identity

Inspect the actual branch, HEAD, worktree changes and ancestry against `340c566686c7123bfcf721e16160aacabbe0b97d`. Preserve all user changes. Do not reset, force-push, rewrite history or silently fold unrelated work into this remediation. If current source has changed, separate already-fixed, still-present and newly-conflicting allegations with exact source references before implementing anything.

Record the current production, evidence-producing and installed-build identities separately. A GitHub head check is not proof of an installed `.app` or running process. Use only explicitly authorized temporary stores; never mine, migrate or copy the user's live training/notes/audio data just to make a reproduction convenient.

### 2. Finish bounded static gaps before claiming complete closure

The audit contains real defects but does not claim an exhaustive full-tree sweep. Enumerate all production clipboard writers and all callers of the relevant Store/NoteStore/transform mutation APIs. Trace their outcome and identity handling to the UI. Read the complete current canonical S29/E19/M15 acceptance sections and the relevant owner contracts.

Enumerate stable human verification ids from the actual current VERIFICATION/ORCHESTRATION/STATUS files; record instruction revisions, total/pending/complete counts and browser storage namespace/reset policy. Do not copy totals from an older handoff. Preserve existing historical outcomes; do not mark human checks passed by editing JSON or browser state.

This static completion work is not permission to expand into an unsolicited architecture rewrite. Record unrelated findings separately with source/reproduction evidence.

### 3. Reproduce and repair in this order

#### 1. XF-AUDIT-01 — Recovery Copy Last Raw bypasses the clipboard-ownership guard

**Reproduction:** Keep dictation A's payload pending after a posted, unverified transaction. Make a different failed dictation B's raw text available in _last_failed. Invoke Copy Last Raw before A's delayed consumer reads the pasteboard. The caller has no ownership refusal before replacing A's bytes.

**Use:** `XF-CASE-045` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Route this action through the shared guarded-copy command; preserve its refusal reason in the Recovery surface. Inventory every production pasteboard writer, including legacy helpers, rather than changing M08's core protocol.

**Acceptance:** Use the real AppDelegate action with a pending ownership ticket and a distinct raw canary. Assert pasteboard generation and payload are unchanged and refusal is visible; release ownership and assert a subsequent copy succeeds.

**Preserve:** New cross-caller composition defect; no allegation that M08's core ownership repair failed.

**Source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L5830-L6005); [localflow/inject.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/inject.py#L1-L150); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235); [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/insertion/service.py#L1-L250).

#### 2. XF-AUDIT-02 — Concurrent transform updates can give one revision two different definitions

**Reproduction:** Start r1={name:N0,prompt:P0}. Pause A after reading r1 for a rename to N1. Let B update prompt to P1 and commit r2. Resume A. The live row becomes {N1,P1,r3}; the preserved r3 can be {N1,P0,r3}. A candidate executed from live r3 can subsequently export the preserved P0 definition.

**Use:** `XF-CASE-041` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Read the authoritative row, merge and validate the requested delta, perform the update, and serialize exactly that committed definition within one writer op. Preserve revision numbering and append-only history.

**Acceptance:** Latch two real update_transform calls at the pre-read boundary. After each commit, compare all canonical definition fields in the live row and matching transform_revisions row. Execute/export a synthetic candidate from the affected revision and independently compare its task definition.

**Preserve:** New M11 storage→M14 export seam; preserve the accepted Prompt Engineer and fidelity gates.

**Source:** [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py#L200-L335); [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285); [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py#L335-L475).

#### 3. XF-AUDIT-03 — The transform editor can overwrite a later opt-out with an unchanged stale checkbox

**Reproduction:** Render a custom transform with auto_apply=True. Disable auto_apply through another admitted control/service call. Change only the name in the still-edited form and press Update. Its unchanged True checkbox is sent again and can reverse the disable.

**Use:** `XF-CASE-042` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Give transform editing the same rendered-id/revision/form binding and delta semantics used by the repaired M10 editors. Refuse conflicts without destroying the user's unsaved form.

**Acceptance:** Render, mutate the authoritative row elsewhere, edit one unrelated field, and press the actual Update action. Verify the concurrent opt-out survives or a stale/conflict outcome is shown. Add a fresh-form positive control.

**Preserve:** New consumer inconsistency relative to the established M09/M10 editor contract, not a request for a new editor architecture.

**Source:** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py#L1820-L2050); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py#L200-L335); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md).

#### 4. XF-AUDIT-04 — Missing normalized-input retention can be exported as a complete model task

**Reproduction:** Synthetic raw text is "ship to cloud"; deterministic normalization produces "ship to Claude". Inject failure only in retaining the normalization evidence, not in executing normalization or retaining the later cleanup prompt. Complete cleanup and mark the applied output intended-correct. The qualifier can export the raw phrase as input with model_task_complete.

**Use:** `XF-CASE-077` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Distinguish not-run/unchanged normalization from failed retention using the recorded producer outcome. Refuse the complete tier or downgrade to a truthful text-pair tier when exact input cannot be established. Do not infer exact input from the existence of a rendered prompt alone.

**Acceptance:** Drive the real collector through changed normalization with an injected retention failure, then real qualification/export. Independently record the actual cleanup input; assert it is either exported exactly with complete provenance or the record is refused/downgraded. Keep unchanged-normalization and bad-existing-reference controls.

**Preserve:** New M04/M07 producer-failure→M14 consumer mismatch; accepted cleanup semantics stay unchanged.

**Source:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py#L660-L830); [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285); [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py#L335-L475); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md#L45-L145).

#### 5. XF-AUDIT-05 — Transform CRUD reports admitted timeouts as not_saved and Add can duplicate

**Reproduction:** Hold the writer past the submit wait after Add has been admitted. Observe the UI timeout, then release the writer so the first transform commits. Repeat the same Add fields. The caller has no retained operation identity linking the second request to the first.

**Use:** `XF-CASE-105` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Return/render not_started, refused/failed, and outcome_unknown distinctly. Keep a preallocated identity or receipt for a logical Add until its outcome is known, and reconcile before another creation.

**Acceptance:** Latch real Store admission and commit, trigger Add through the real Hub action, then repeat with the same logical operation. Assert one transform, one initial preserved revision, truthful unknown status, and eventual reconciliation.

**Preserve:** An older CRUD caller did not inherit M02's outcome semantics; the underlying Store timeout behavior is intentional.

**Source:** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py#L1820-L2050); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py#L200-L335); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py#L1240-L1415).

#### 6. XF-AUDIT-06 — Save Transform to Scratchpad discards the note service's unknown-outcome identity

**Reproduction:** Keep a valid transform result on screen. Stall its note creation after admission, let the caller return from the timeout, then let the original op commit. Invoke Save again. The caller does not reconcile the first note identity.

**Use:** `XF-CASE-049` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Preserve the note id and a typed pending result across this caller; repeat/reconcile the same operation. Keep the panel result available until settlement and do not label admitted uncertainty as failure.

**Acceptance:** Invoke the real tfSaveToScratchpad with a synthetic result and latched Store. Verify one note after timeout/retry, a stable id throughout, and correct origin=transform. Run a refusal-before-admission control.

**Preserve:** New caller gap composed across M11 and the repaired M12 note API.

**Source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/notes.py#L285-L640); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py#L1240-L1415).

#### 7. XF-AUDIT-07 — History Move reports source deletion failed when its outcome is still unknown

**Reproduction:** Complete the note creation phase of Move. Hold only the source delete op after admission past its wait. Observe the returned status, then release the delete. The source can disappear after the caller reported the deletion phase as failed.

**Use:** `XF-CASE-050` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Represent the two phases separately and preserve a move/deletion identity until reconciliation. Retrying must reuse the existing destination note and settle the source phase only.

**Acceptance:** Latch the source-delete phase of real hubSaveHistoryRow(move=True). Assert one destination note, truthful source-deletion-unknown status, eventual reconciliation, and no second copy on retry. Preserve the existing create_unknown positive control.

**Preserve:** Narrow cross-phase gap in an otherwise guarded M12 History transfer.

**Source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/notes.py#L285-L640); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py#L1240-L1415).

#### 8. XF-AUDIT-08 — STATUS.json presents historical M14 details as current state

**Reproduction:** A fresh session reads STATUS first as START_HERE directs. It can plan a v9→v10 migration or use old 54/50.3 ms writer-wait figures even though the current addendum describes schema13 and maxima205/174 ms.

**Use:** `XF-CASE-092` and the related race/control entries in the corpus. Drive the actual production caller/producer; assert that the intended hook is reached. Do not grade a handwritten expected label as a test result.

**Smallest repair:** Add/update an explicitly current remediation projection with full code/evidence refs and current schema. Keep the original source_commit and benchmarks as labeled historical entries, not overwritten history. Reconcile runbook counts from the actual stable-id set.

**Acceptance:** Statically validate that current schema/production/evidence pointers agree with the addendum and that old records remain byte-identical. Independently enumerate runbook ids and distinguish pending records by their instruction revision.

**Preserve:** Partially refreshed current projection, not a request to rewrite accepted historical evidence.

**Source:** [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/STATUS.json); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

### 4. Mandatory implementation constraints

Keep M07 faithful cleanup and M11 Prompt Engineer requirement/literal policies unchanged. Do not suppress a test by weakening an invariant, dropping its independent oracle, or excluding an otherwise valid workload.

For transform updates, the authoritative read, merged validation, live update and immutable preserved definition must agree within the same writer transaction. Editor revision/delta binding is a separate layer: solving Store atomicity alone does not prevent a full stale form from reversing an opt-out.

For normalization/export, represent not-run, unchanged and failed-retention distinctly. A bad existing reference already refuses. The missing-reference failure branch needs its own proof. Healthy unchanged normalization with a valid ledger must remain eligible when actual input and required provenance are complete.

For timeouts, keep not_started/refused/failed/outcome_unknown/settled distinct. Store timeout is not cancellation. Reuse an id for the same logical operation, bind it to the same target/payload, and reject incompatible id reuse. History Move must retain destination-created and source-deletion states separately; a retry must not make another destination note.

For clipboard behavior, adopt the existing guarded authority from the Recovery caller. Do not invent a parallel pasteboard broker or silently treat user Copy as permission to corrupt another pending transaction.

For docs, preserve old evidence bytes and ids. Update the current projection with exact final code/evidence references, truthful current schema and pending native/manual state. Never fill in an anticipated commit hash, invented test count or guessed runbook total.

### 5. Test sequence and evidence discipline

Use deterministic latches/barriers, not sleeps, to establish races. Each failing baseline or passing repair must invoke the real producer/caller and observe actual persisted state, output bytes, ids, side effects and visible outcome. Platform adapters may be controlled for portable tests, but authority code and the user-command path must remain real. Native focus, clipboard consumption and keyboard/layout claims require native evidence.

Start with finding-specific reproductions and positive controls. Then run the sixteen multi-hop scenarios, relevant existing regressions, current full acceptance sweeps, and reachable mutation tests. Use temporary source copies for mutation; report applied/reached/killed/survived/invalid separately. A mutant that did not apply or failed during setup is not a killed mutant.

Performance work must validate actual useful work first: expected eligible populations, records, audio bytes, lineage and independent outputs. No-op/empty components make the fixture INVALID. Record continuous writer-wait p50/p95/p99/max and sample count separately from component throughput and later native end-to-end latency.

Never write PASS into the provided corpus merely because the expected result is known. Preserve the original design artifact; create a separate execution record containing case id, exact source/fixture/environment, real hook, observation, result and evidence pointer. Unexecuted items remain NOT_RUN; blocked items explain the actual missing capability.

### 6. Required remediation return

Return the exact starting/current/final source identity and a narrow changed-file summary. For every XF-AUDIT id, give reproduced/refuted/repaired/pending state, reached baseline evidence, implementation rationale, regression/control result and residual risk. A refutation must show the actual branch and countervailing source or reached test; “could not reproduce” without reaching the stated interleaving is not closure.

Return the complete production caller inventory for the repaired interfaces, the current runbook/browser-state reconciliation, acceptance artifact hashes, tests actually run with actual outcomes, and native/manual/model work still NOT_RUN. Explain whether any historical artifact was changed; normally historical evidence should be byte-identical.

The completion state must distinguish LOCAL_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION from final product acceptance. M15 planning can continue, but decision-grade qualification remains gated on truthful task evidence, settled authority/outcome protocols, complete canonical contract reconciliation and explicit current manual state.

## Acceptance gate checklist

| Gate | Required observation |
|---|---|
| Clipboard caller closure | No production in-app copy bypasses pending insertion ownership without an explicit documented override protocol |
| Transform revision integrity | Live/preserved/executed/exported canonical definition equality under the disjoint-update race |
| Stale transform editor | Name-only stale edit cannot reverse a later opt-out; unsaved user text is retained on conflict |
| Cleanup completeness | Changed-normalization retention failure cannot produce a false complete task; healthy unchanged control remains valid |
| Transform Add retry | One transform for one logical create across admitted timeout and reconciliation |
| Transform Save retry | One note and stable pending identity; no false ordinary create failure |
| History Move phases | One note; explicit source-delete-unknown; eventual source settlement without duplicate copy |
| Current docs | Schema/code/evidence/runbook projections agree without altering historical records or inventing human passes |
| Broader closure | Real caller census and full S29/E19/M15/runbook reconciliation completed, with remaining gaps explicit |
| M15 | No qualified-ready claim based on incorrect task lineage, unrun models or stale acceptance records |

## Starting status

All new corpus cases, multi-hop scenarios, races, metamorphic relations and mutations are **NOT_RUN**. The audit found source-supported allegations; it did not execute a failing baseline, repair code or certify a native build. Keep that boundary intact when creating the local execution record.
