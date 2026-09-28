# LocalFlow V2 — Final M01–M14 Cross-Milestone Read-Only Audit

**Repository:** `scalinity/LocalFlow`  
**Audit date:** 28 September 2026  
**Pinned main:** `340c566686c7123bfcf721e16160aacabbe0b97d`  
**Target execution:** `NOT_RUN`  
**Disposition:** **B — Proceed after targeted cross-milestone repairs.**

## Executive Assessment

The accepted milestones have a substantial coherent foundation, but they do not yet compose cleanly at every inspected seam. This review identifies **3 HIGH, 4 MEDIUM and 1 LOW source-supported findings**, with **no confirmed CRITICAL finding**. The findings are static allegations with deterministic reproduction specifications, not executed failure results. The most consequential seams are later-table corruption repair, transform revision-manifest identity, and retry examples counted as independent speech-profile observations. Details and exact owning seams follow below. [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py)

The recommended next step is a bounded local reproduction/remediation campaign—not reopening M01–M14 wholesale. Preserve the repaired insertion, scoped-vocabulary, note provenance, usage-deletion and export-qualification boundaries. The attached corpus specifies **125 cases across 29 categories**, including 15 multi-hop scenarios and 15 stateful schedules, plus 12 metamorphic relations and 18 mutations. Every target case, relation and mutation remains **NOT_RUN**.

**M15 is not authorized.** In addition to the cross-milestone seams, the current M11 handoff records an actual unsuccessful model-backed run, not just missing execution: 40 cases include one misdirected review and 14 output-limit fallbacks. The handoff explicitly keeps M15 gated. Native fixture passes and an accepted lexical gate cannot erase that result. [docs/v2/handoffs/M11.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md)

This is a substantive source-based audit, **not an exhaustive all-files/all-callers proof**. The full current test-entrypoint census, complete 80-check DOM/ID reconciliation, every live-store-opening tool, and exhaustive event/file-reader inventories are not independently closed here. Those are named coverage obligations, not implied passes. Verdict B directs repairs and closure work; it does not certify every uninspected path clean.

## Audit Boundary

> This audit covers committed GitHub state at 340c566686c7123bfcf721e16160aacabbe0b97d. Any uncommitted local state is outside the GPT-6 audit boundary.

Read-only GitHub API/connector inspection established the pinned main, production ancestry, source interfaces and relevant contract/handoff evidence. No repository file was edited, no branch/commit was created, no test or application target was run, and no installed app or private live store was inspected. The deliverables are newly authored audit artifacts, not repository modifications.

Evidence classes used here are **source-traced**, **handoff-reported historical execution**, **proposed reproduction (NOT_RUN)**, and **unclosed coverage**. A historical suite exit code is not a new current-main pass. A static path prediction is not a reproduced native failure. File links below are pinned to this audit SHA; source functions are named where a stable function reference is more useful than an arbitrary excerpt.

The supplied audit instructions are the task authority. Required concerns are covered by named report sections, findings or explicit test gaps. Some long source/document fetches were bounded or truncated; their unseen portions are not treated as inspected. The report does not claim that reading a handoff substitutes for reading every production caller or every test body.

## Canonical Main / Lineage

Remote `main` equals the supplied merged docs/main head. The accepted M14 production is followed only by evidence, tooling/test-driver and documentation changes in the inspected comparison; no later `localflow/` production change was present. The evidence-tree anchor is `0e5cdcc8287c51ee5218eaef25a119d1fdb6d494`; the parent of the audited docs head is that evidence-tree commit. The root tree is `596a7cc0d812cffb0a0c319a3cccc910cc6c4eb2`.

| Milestone | Production anchor | Ancestor of audited main | Commits from anchor to audited main |
|---|---|---|---:|
| M01 | [`3db74061f23001b9cce3d4fe029e0b30cbc295d6`](https://github.com/scalinity/LocalFlow/commit/3db74061f23001b9cce3d4fe029e0b30cbc295d6) | Yes; GitHub comparison merge-base equals anchor | 158 |
| M02 | [`bfbc63c35efa6273cc13242d54d3e5bbe264b21e`](https://github.com/scalinity/LocalFlow/commit/bfbc63c35efa6273cc13242d54d3e5bbe264b21e) | Yes; GitHub comparison merge-base equals anchor | 154 |
| M03 | [`3e0d1ab972b866b4acbda622984bce04e8f95093`](https://github.com/scalinity/LocalFlow/commit/3e0d1ab972b866b4acbda622984bce04e8f95093) | Yes; GitHub comparison merge-base equals anchor | 150 |
| M04 | [`4ef219c52598e92a9857e9e0dec13ca7143f56dc`](https://github.com/scalinity/LocalFlow/commit/4ef219c52598e92a9857e9e0dec13ca7143f56dc) | Yes; GitHub comparison merge-base equals anchor | 145 |
| M05 | [`01a1f3c07ed3270aa1e7b3da39d89c453c84c1e8`](https://github.com/scalinity/LocalFlow/commit/01a1f3c07ed3270aa1e7b3da39d89c453c84c1e8) | Yes; GitHub comparison merge-base equals anchor | 139 |
| M06 | [`4388b521cedfebe5a16dc8c485d25275f0b342f0`](https://github.com/scalinity/LocalFlow/commit/4388b521cedfebe5a16dc8c485d25275f0b342f0) | Yes; GitHub comparison merge-base equals anchor | 132 |
| M07 | [`52edc4753df9be17d9119e95d760c4086c5649cd`](https://github.com/scalinity/LocalFlow/commit/52edc4753df9be17d9119e95d760c4086c5649cd) | Yes; GitHub comparison merge-base equals anchor | 170 |
| M08 | [`ea83bc198567d001e3d770ae5103ca369701825d`](https://github.com/scalinity/LocalFlow/commit/ea83bc198567d001e3d770ae5103ca369701825d) | Yes; GitHub comparison merge-base equals anchor | 106 |
| M09 | [`a304d48c3adf0ef7639fe66986d8affe41a2264a`](https://github.com/scalinity/LocalFlow/commit/a304d48c3adf0ef7639fe66986d8affe41a2264a) | Yes; GitHub comparison merge-base equals anchor | 71 |
| M10 | [`ed5e20631529e063564b151555215485ec316a53`](https://github.com/scalinity/LocalFlow/commit/ed5e20631529e063564b151555215485ec316a53) | Yes; GitHub comparison merge-base equals anchor | 55 |
| M11 | [`9a049b341d315201ba7d8019585fd7e71370af31`](https://github.com/scalinity/LocalFlow/commit/9a049b341d315201ba7d8019585fd7e71370af31) | Yes; GitHub comparison merge-base equals anchor | 123 |
| M12 | [`b17aa2bee82c46ef9f01d680e1b1031629744835`](https://github.com/scalinity/LocalFlow/commit/b17aa2bee82c46ef9f01d680e1b1031629744835) | Yes; GitHub comparison merge-base equals anchor | 39 |
| M13 | [`36e03a2a30e380729ceb56d3f1f41bea751bbb4f`](https://github.com/scalinity/LocalFlow/commit/36e03a2a30e380729ceb56d3f1f41bea751bbb4f) | Yes; GitHub comparison merge-base equals anchor | 19 |
| M14 | [`9d0cfdf85f459149b5382f432f7663cda5b16446`](https://github.com/scalinity/LocalFlow/commit/9d0cfdf85f459149b5382f432f7663cda5b16446) | Yes; GitHub comparison merge-base equals anchor | 6 |

These are independently verified ancestor relationships, not claims that every later edit preserved all behavior. M07’s remediation anchor was additionally located through the pinned cleanup-engine history. Milestone numbering is not chronological commit order.
M11 is an important exception to a naive branch-SHA check: its older cloud remediation was replayed onto the accepted lineage. The canonical final production anchor is `9a049b341d315201ba7d8019585fd7e71370af31`; the current handoff distinguishes the replay (`1545de9`) and later authority/callback repairs from the older cloud branch. Absence of that older cloud SHA as an ancestor is not, by itself, a missing repair. [docs/v2/handoffs/M11.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md)

## Current System Architecture

```text
M01 source/config/evaluation provenance
  -> M02 Store + jobs + immutable artifacts + consent + events
  -> M03 capture/FIFO coordinator + supervised ASR worker + attempts
  -> deterministic normalization result (M04 syntax + M05 vocabulary + M10 references/snippets)
  -> M07 faithful cleanup with mapped protected spans
  -> optional M11 gated transform
  -> M08 external target transaction OR M12 bound note-delivery receipt
  -> M09 History / Hub actions
  -> M13 exactly-once usage and distinct activity facts
  -> M14 correction/review/profile/qualification/export
```

M06 supplies job-scoped context and destination proof before these consumers run. A late downstream context result is taken from that job’s collection handle and labeled separately; it is not retroactive pre-decode evidence. M10 supplies effective writing mode/category and frozen reference/definition context. M12 note versions and M14 task evidence are domain objects over the shared Store, not interchangeable delivery receipts. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

The system’s central invariant is therefore purpose-aware: one logical capture retains its job/family/original provenance, while it may legitimately acquire multiple attempts, artifacts, note revisions or training examples. Each consumer must preserve the distinction between **capture identity**, **content revision**, **destination authority**, **user judgment** and **execution outcome**. The three HIGH findings arise from conflating one of those distinctions downstream.

## Producer → Consumer Interface Map

The companion **LocalFlow_M01_M14_Interface_Matrix.md** inventories **29 important interfaces**. Each records producer/consumer, authoritative object, mutable/frozen fields, revision admission, deletion, timeout, owning evidence and the residual risk. It also inventories 13 functional product surfaces to preserve during the later redesign.

The most important compositions are: M03 retries into M13/M14 counts; M04/M05/M10 ledger into M07 protection; M06/M11 into M08 strict destination ownership; M12 canonical span rebasing into M14 mining; M14 approval into M05 writer-authoritative vocabulary; and M02 repair/retention into M14 profile/export trust. The inspected implementation often shares canonical helpers correctly, but sharing a Store alone does not prove a multi-operation transaction. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

## Job / Attempt Identity

### Full-path state table

| Path | Authoritative identity | Content/fallback | Outcome authority | Downstream effect |
|---|---|---|---|---|
| A. Confirmed external insertion | job + attempt + final artifact + transaction | Final transformed/clean/Raw stage explicitly selected | External confirmation only from M08 evidence | One M13 dictation fact; no automatic human correctness label |
| B. Saved not inserted | same job/attempt and retained final | Final exists but destination proof or delivery failed | No external confirmation | Usage distinguishes saved; History/recovery can expose retained content |
| C. Posted unverified | same job/attempt + posted transaction | Final is known; external delivery remains unverified | Posting is not confirmation | Not automatic success truth or model-training approval |
| D. Failed | same job/attempt; any retained earlier stages | Missing final stays missing | Pipeline failure distinct from failed paste of saved text | M13 final_words unknown/null, not a fabricated successful zero |
| E. Cancelled | same job/attempt and cancellation state | Late worker results cannot republish | No external success inferred | Pre-release cancellation has no release-to-terminal latency |
| F. Retry | same original job/family/time; incremented attempt | New current-attempt artifacts; original capture provenance remains | New attempt may explicitly use a newly identified policy where allowed | M13 replaces one job fact; M14 capture denominator is finding -03 |
| G. Scratchpad delivery | job + bound note + arrival/revision receipt | Exact note-bound final, not currently selected note | Confirmed only after immutable note revision commits | One dictation fact; note autosaves are not new dictations |
| H. Transformed result | source hash + transform/task/candidate/revision + final | Applied transform wins for delivered/display final | Candidate/generation is not application/acceptance | Auto-apply is not human preference; task-specific export remains distinct |
| I. Raw mode | job + attempt + effective Raw mode | Original ASR result under Raw transport rules | Normalization/model cleanup skipped | No fake cleanup model pass; final result still explicitly stored |
| J. Collection off | job delivery/History/usage identities without trainable capture entitlement | Permitted local operation and ordinary retention continue | No evidence authority fabricated from usage | Explicit Teach may use retained History final under its own action policy; dataset export requires current consent |

For all paths, governed content deletion is enforced by job/artifact/note ownership, not by erasing independent permitted usage. Downstream profile/export eligibility must be requalified after content loss. An immutable artifact ID must still match its expected owner/role and current retention state. [localflow/v2/history_queries.py · current-attempt lineage and final-text resolution](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py)
CROSS-AUDIT-03 is a concrete split in logical-job interpretation: retained retry examples can inflate the profile denominator while usage correctly keeps one capture. Do not repair it by destroying legitimate per-attempt evidence.

## Terminal Outcome Semantics

The system needs two axes, not one overloaded success flag. **Pipeline/delivery** distinguishes confirmed, posted_unverified, saved_not_inserted, failed and cancelled. **Command admission/completion** distinguishes not_started, committed/deleted, rolled-back failed and outcome_unknown. A timeout after Store admission belongs to the second axis; it is not proof of a failed insertion or cancelled write. [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py)

External `confirmed` and internal note `confirmed` can share the usage-level terminal abstraction only while their destination/receipt types remain explicit. A committed note revision is not an AX confirmation. Conversely, a target refusal after successful text generation is saved-not-inserted, not necessarily a failed text pipeline. Posted-unverified must not become a positive training label. The inspected M13 contract is explicit about these translations; the corpus requires the independent cross-producer witness. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md)

## Unknown Outcome / Idempotency

M13 usage deletion has typed outcomes and durable completion markers; M14 uses operation receipts for repeat-sensitive actions such as Teach and approval. Export publication deliberately leaves staging under ownership of a writer-admitted operation after a caller timeout. Those are strong, distinct implementations of the same admission rule. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

Transforms Add/Update is not automatically protected by those later patterns. CROSS-AUDIT-06 demonstrates the Add risk: a fresh ID per retry plus “not saved” after an admitted timeout can create duplicate definitions. Updates also need a truthful unknown result even when their eventual logical effect is idempotent. Stable operation IDs must bind action and target; a reused key for another target is not a valid retry. [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py)

The local caller inventory must cover vocabulary, configuration, transforms, notes, labels, splits, approval, profile actions, exports and Hub CRUD. No blanket statement that every Store.submit caller has been audited is made here. Inventory and test branch admission before labeling a timeout failure or unknown.

## Final Text / Mode Authority

For a **delivered/displayed job final**, the inspected History lineage chooses an actually applied transformed result when present, otherwise the job’s current cleaned/applied result; Raw has its own explicit result. Missing expected final authority is unavailable, not silent fallback to raw ASR or a previous attempt. History actions must bind that rendered final and its revision/hash. The repaired Teach path checks the expected artifact and digest inside the same writer operation that mints the candidate. [localflow/v2/history_queries.py · current-attempt lineage and final-text resolution](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py); [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py)

Not every consumer should use this display-final selector. **Your Voice speech analysis intentionally uses retained eligible raw speech**, to avoid attributing a model’s writing style to Daniel. **Cleanup-supervised export** needs the exact cleanup input/output and intended-writing judgment; **transform-supervised export** needs its own task input, definition and explicit accept. Replacing all these purposes with one “latest text” helper would destroy task authority. Share canonical resolution by purpose, not by indiscriminate latest-artifact fallback. [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

Requested mode, effective mode, actual execution path and fallback reason remain separate fields. Raw, Clean, Polish, Concise, Prompt Engineer, custom transforms and Next Dictation Mode must retain that distinction through History/notes/usage/learning. The coordinator visibly skips normalization and model cleanup for effective Raw, and records normalization fallback explicitly. Exact all-mode UI-to-export composition remains part of the corpus rather than a current model-quality claim. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py)

## Scope / Context Composition

M14 approval calls M05’s canonical scope and writer-authoritative entry methods inside the approval transaction. Counterexamples run through the effective post-approval M05 snapshot in the rule’s own scope. Disabled/unapproved user entries are not silently reactivated; later user edits have their own revision authority. This is a genuine shared boundary, not an independent M14 scope implementation. [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/vocabulary_store.py · writer-authoritative update and revision history](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py)

M06 context is per-job. The coordinator uses that job’s frozen policy/context and collection handle; its late downstream snapshot is explicitly separate. A retry without a retained policy may use a clearly identified new default snapshot where the contract permits it. That does not authorize rewriting the original capture time/app/family or borrowing the previous live job’s scope. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py)

The local multi-hop tests must challenge bundle/site normalization, slash/whitespace/casing, exact workspace/profile names and global/null semantics across M05, M10 and M14. M10 path/skill confinement and partial-listing semantics are reported repaired; exhaustive downstream file/skill caller equivalence is not independently closed by this review. [docs/v2/handoffs/M10.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M10.md)

## Normalization / Protection Composition

The actual coordinator calls a **single deterministic normalization entrypoint** between ASR and cleanup; its result contains vocabulary, skill, snippet and file-reference edits. It records current-attempt hit sets and maps protections through the edit ledger. Snippet and resolved-filename output spans are added as exact generated protection. If protection cannot be constructed, the job abstains from model cleanup rather than proceeding unprotected. Raw mode bypasses this normalization stage. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py)

This is not evidence that the internal normalizer’s every precedence branch has been re-audited. The corpus targets protected repeated occurrences, literals containing command words, numeric identities, generated multi-line snippets, technical names and paths. The local inventory must enumerate the actual normalizer proposal/overlap-resolution order, rather than assume milestone number is execution order. M07’s existing remediation specifically addressed occurrence mapping, chunk seams, typed values and false-green fallback fixtures. [docs/v2/handoffs/M07.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M07.md)

## Transform Composition

The inspected coordinator retains a distinction between automatic generation/application and explicit user preference. M14’s supervised transform qualifier requires a current explicit accept and reconstructable task input/definition; auto-apply by itself is not an accept. Candidate identity must include task/source hash and frozen definition revision, while strict selected-text application still requires target proof. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py)

CROSS-AUDIT-02 exposes a lower-level problem that a correct transform gate cannot repair: one revision number may carry a stale history payload after interleaved definition edits. CROSS-AUDIT-05 and -06 expose weaker UI revision/timeout admission than Styles/Snippets. Repair those seams without weakening requirement preservation or rewriting the transform engine wholesale.

The M11 model-backed result remains a real qualification failure: 10 applied, 0 applied semantic failures, 1 review addressing a loss, **1 misdirected review**, 14 review-with-no-loss, 14 output-limit fallbacks, and exit status 1 over 40 cases. The exposed ten-case blind stratum cannot become a fresh blind holdout after tuning. The exact gate to close is trustworthy model behavior under the current contract, not merely adding more lexical assertions. [docs/v2/handoffs/M11.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md)

## External Insertion vs Scratchpad

External insertion settles through M08’s target/clipboard transaction. Scratchpad delivery settles through M12’s bound arrival and committed immutable revision. Buffer acceptance is not durable delivery. Both can feed one logical-dictation usage abstraction, but the receipt kind and destination must stay explicit. The reviewed coordinator and M13 contract preserve this separation. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md)

M12’s repaired arrival identity, immutable queued revisions and canonical note provenance are valuable upstream authority. Do not bypass them when adding note mining or profile features. Pending human/native trials still include switching notes during arrival, emoji/codepoint boundaries and crash/reopen behavior; optional evidence publication remains distinct from core note durability. [docs/v2/handoffs/M12.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M12.md)

## History / Hub Action Identity

History’s repaired Teach path carries the rendered final artifact/hash to writer admission; a changed final refuses rather than teaching against unseen content. The controller uses rendered row identity, not a bare mutable row index, and the shared state layer fences asynchronous requests. These protections are meaningful and should be preserved. [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/ui/state.py · per-key requests, epoch revocation and guarded publication](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/state.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py)

Transforms is not equivalent merely because it also selects a stable transform ID. Its Update path lacks a rendered revision/baseline and submits the whole form. An unseen service edit can be overwritten by an unrelated visible edit. Ordinary transform selection synchronously fills the selected form, so this audit does **not** promote an unproven click race to a wrong-item finding. Native custom-prompt editability and selector behavior remain a separate test obligation. [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py)

M09’s old Move-to-Scratchpad and Teach leads are reported resolved by M12/M14, respectively; do not reopen those original findings without a new reproduction. Copy, Paste Again, Save/Move, Retry and diagnostics still need the current cross-action expiry and generation witnesses. [docs/v2/handoffs/M09.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M09.md) [docs/v2/handoffs/M12.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M12.md)

## Hub Query Generation / Stale Publication

HubState’s query discipline uses bounded request execution, per-key generations and revocation epochs with guarded publication. A late query must not repaint after filter changes, deletion or close. Later pane actions must participate in that same state discipline; directly writing a widget is not itself a new query generation. [localflow/v2/ui/state.py · per-key requests, epoch revocation and guarded publication](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/state.py); [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py)

CROSS-AUDIT-07 is the concrete seam: Validate writes export_text directly, while a previously admitted training refresh can later write the same widget from old export state. The appropriate owner is M14’s Export pane, with M09 compatibility—not a claim that all query generations are broken. Preserve the validation report with destination/fingerprint identity and fence older publication.

The local native matrix must cover filter changes, note switches, usage deletion, profile exclusion, export validation, pane switches and app close. It must observe actual main-queue publication, not only a helper returning false for a stale integer token.

## Note Provenance → Learning

The M14 note miner calls M12’s occurrence-safe rebase to identify ambiguity, then attributes changed regions to dictated spans. A typed-only region is dropped; a boundary-crossing or multiply attributable region abstains. The retained note-correction payload is limited to changed regions rather than copying the whole typed note into an acoustic correction. This directly respects stronger upstream provenance. [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py)

Remaining composition tests are multi-dictation notes, simultaneous typed and dictated changes, repeated words, Unicode boundaries, deletion before the miner’s writer operation, and autosave/mining revision races. A note link or stable job ID must not silently retarget a historical edit to a newer attempt’s stage evidence. The reviewed selection of latest example by job deserves that bound retry witness, but no supported wrong-attempt note-mining failure was proved here; it is not promoted to an additional material finding. [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py)

## Analytics Exactly-Once Composition

M13 defines one dictation fact per logical job and replaces it on terminal retry while preserving original capture time/zone/app. Explicit transforms and repastes are separate activity kinds, and dictation-path auto-transforms ride the job fact. Note revisions/autosaves are not speech captures. Retry has no fresh release clock: end-to-end latency is null with an explicit reason, while retry-start-to-terminal is separate. [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py)

The invariant must be checked against an independent activity ledger spanning normal insertion, Scratchpad commit, failed/cancelled attempts, retries, History repaste and Recovery repaste. Do not infer “exactly once across the whole system” from the partial unique index alone: the profile denominator currently differs, and a no-transaction repaste must not be counted as an executed activity. CROSS-AUDIT-03 is downstream identity inflation, not a finding that the inspected M13 fact replacement is wrong.

## Privacy / Event Envelope

| Data class | Examples | Permitted treatment |
|---|---|---|
| Content-free operational metadata | Opaque job/attempt IDs, durations, counts, enumerated reason/status codes | Generic event envelope, subject to the canonical allowlist |
| Private metadata | App/site/workspace names, filenames/paths, named profiles, time-of-day usage | Local governed store/UI; not automatically safe in generic logs |
| Governed private content | Audio, transcripts, notes, corrected spans, prompts, vocabulary terms, derived phrases | Owner-bound artifacts/domain storage, explicit retention and deletion |
| Explicit export content | Selected audio/text/references/task definitions and lineage | Only in the explicitly requested governed export; not generic diagnostics |

Collector and learning code generally emit counts/IDs/reasons while storing exact text in governed artifacts. M13 explicitly classifies app names as private usage metadata; M14 candidate/counterexample payloads use governed artifacts. That is a source-supported design boundary, **not a completed every-emit/every-exception canary proof**. [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md)

The local campaign must inventory all emit/log sites and inject distinct canaries for transcript, corrected text, note text, filename, path, app, vocabulary/profile term and exported content. Inspect refusal and exception paths as well as success; truncated stack traces can hide private path prefixes. No privacy pass is claimed from a connector search miss or from the absence of a canary in an unexecuted test.

## Deletion / Expiry / Retention Propagation

Deletion has multiple authorities that must remain intentionally independent: job/content deletion, note deletion, artifact expiry, usage deletion/expiry, profile exclusion and current export consent. Monotonicity means removing governing evidence cannot create new eligibility, re-create content or leave an unsupported current interpretation. It does **not** mean every deletion should erase every independent domain. [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

The M13 contract deletes usage-derived fields from all Your Voice snapshots in the same removal transaction while leaving speech-derived fields and retained speech intact. Profile generation checks its raw inputs/labels/exclusions at final publication and reads usage at the committed writer boundary. Those seams are strong in the reviewed source. CROSS-AUDIT-01 shows why they also depend on repair preserving the support/authority tables. [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

Lease ownership must distinguish a user pin, review protection, unreviewed training buffer and note-linked evidence. The earlier Unpin/review seam is reported repaired; do not reclassify a lease solely by an incomplete artifact-role blacklist. All active panes must reconcile after expiry or deletion, including hidden cached payloads. Published standalone datasets are explicit copies: post-publication deletion policy must not be misrepresented as magically recalling every external file. [docs/v2/handoffs/M14.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md)

## Artifact / Filesystem Authority

The shared M14 qualifier requires an expected owner and checks artifact existence, purge state, semantic role, payload availability and text digest when recorded. Transform slots additionally bind task identity and source hash. Export streams audio through the managed-file helper and verifies the copied bytes against the capture digest. Readiness and export share task predicates rather than merely checking an ID exists. [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

The managed Store helper admits a plain filename through a directory descriptor, no-follow open and regular-file check; it uses nonblocking open to avoid a FIFO stall. The exporter refuses destinations inside its managed data and refuses replacing a non-owned populated destination. These are strong inspected controls, but not proof of equivalent confinement in every M10 reference and M12 attachment consumer or under every ancestor-symlink configuration. [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

A final dependency recheck can legitimately rely on immutable supported artifact writers after initial owner/role qualification. Direct SQL mutation of an immutable record is a corruption threat model, not automatically a supported race. Test it separately; do not demand impossible resistance to arbitrary database rewriting or conflate a same-ID corruption probe with a normal service update.

## Schema / Migration / Repair Composition

Current Store schema is **13**. Additive migrations include M10 configuration/definitions, M12 note families, M13 usage/zone metadata, and M14 learning/review/profile/split data plus operation receipts and vocabulary deltas. The old core loss detector was extended for notes, but not equivalently for the later dependency families. CROSS-AUDIT-01 is the resulting repair seam. [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

The exact current refusal-map keys inspected are: jobs, artifacts, training_examples, training_revisions, artifact_leases, consent_revisions, imports, import_runs, legacy_dictations, deletion_tombstones, notes, note_revisions, note_attachments and note_evidence_links. The code separately documents backfill/orphan behavior for job_deletions and purge_intents. Absence from this map is not by itself proof that every table needs identical treatment; each missing-family test must establish a surviving dependent and the real loss of authority. [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

Synthetic historical stores should span versions 1, 5–13, clean upgrades, interrupted additions and current-version loss. Never use Daniel’s live store. Inventory every app/CLI/dev/benchmark path that can open a live path with migration enabled, and prove backup hooks on synthetic copies. This audit read startup and Store migration behavior but did not complete the exhaustive tool-entrypoint inventory; backup compliance across every CLI remains TEST GAP, not asserted failure.

## Learning / Vocabulary Composition

Only explicit approval changes the normalization dictionary. Mining, sampling, labels, profile cards and rejection do not automatically alter output. In the inspected approval implementation, pending/live evidence checks, canonical scope, adverse counterexamples, the M05 vocabulary mutation, reversible delta and candidate decision occur in one writer operation. Counterexamples with no supplied phrases are “untested,” not “safe.” Existing disabled/unapproved entries are not casually reactivated. [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/vocabulary_store.py · writer-authoritative update and revision history](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py)

M14’s current handoff reports reversible undo against later user edits. The source inspected here establishes the approval-side delta and revision authority; the inspected undo path uses M05 writer methods and protects ordinary created-entry revisions. Its missing-delta legacy fallback, however, lacks that exact revision and can disable a later user-edited entry after a v13 table-loss repair. That is part of -01, not a claim that ordinary intact-delta undo is broken. The full caller/native surface was not reexecuted. The Hub’s missing Undo approval control is separated below as a product-surface concern. [docs/v2/handoffs/M14.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md)

## Readiness / Dataset Export Composition

Shared predicates distinguish ASR supervised, weak span graft, intended-writing cleanup, explicitly accepted transforms and same-input preference pairs. Cleanup has `model_task_complete` versus `text_pair_only` tiers; losing exact model prompts may reduce the tier rather than manufacture a full model-task record. An applied/posted result is not a human reference. [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md)

Parity must compare **the same task view, selection, assignment version and partitions**. Global readiness can legitimately include an eligible example captured after an older split assignment; the exporter names `not_in_assignment_version`. That is a disclosed selection difference, not proof that the shared eligibility predicates disagree. New unknown-count output is not allowed to masquerade as qualified readiness. [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md)

Offline graph writing includes task input/output, definition, human judgment, lineage, schema/algorithm versions, partition/exposure metadata and relative audio copies with checksums. This is source-supported closure design. The standalone validator’s entire rejection matrix and every live-producer-to-offline round trip were not independently re-audited/executed, so offline closure remains a local qualification obligation, especially after fixing transform revision manifests. [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py)

Publication rechecks selected dependencies and performs rename inside one Store writer operation; a queued deletion cannot commit between that check and rename. However, SQLite commits only after the callback returns. A crash after rename but before DB commit can leave a valid package without a completion row. The deterministic witness and recovery policy are recorded under DESIGN-02 rather than a vague “crashes happen” finding. [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

## Your Voice / Usage / Evidence Composition

Your Voice is currently a **local deterministic ProfileService**, not an external API/LLM feature. Its measured fields, phrases, technical-term support, reviewed labels and interpretation floor derive from retained source/domain data. No API key should be introduced as a prerequisite for this current feature. A future optional interpretive model is a separate design decision, not part of this audit. [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [docs/v2/contracts/profile.md · speech evidence, interpretation floor and liveness](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profile.md)

The exact-input writer fence is good: it rechecks example liveness, revision, qualified raw artifact, labels and exclusions before publishing. Usage metadata is read under current committed authority and can be redacted independently. The interpretation condition includes the word floor and at least ten eligible examples. The weakness is the unit of those examples across retries (CROSS-AUDIT-03), and current-name resolution for historical applied rules (CROSS-AUDIT-04). A live citation ID is necessary but not sufficient proof that a displayed term came from that revision. [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py)

Below the interpretation floor, measured statistics may still be useful. They must not become unsupported interpretive cards. Boundary tests must include 1,999/2,000 words and nine/ten **logical captures**, not just fixture rows, plus support removal after the snapshot is already visible.

## Family / Exposure Integrity

The inspected split/export paths consult exposure across assignment versions. New export through an older version still refuses a family currently known exposed in frozen_test. Task-keyed transform/preference rows are explicitly unpartitioned and not holdout-qualified; including train is a declared selection rule, not a fabricated family. [localflow/v2/curation/splits.py · historical exposure and assignment](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/splits.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

CROSS-AUDIT-01 breaks this otherwise strong rule only when repair discards the membership history that carries exposure. That condition must be tested without pretending arbitrary direct SQL writes are supported service admission. Ordinary exposure edits and export publication use deterministic barriers; a previously exposed model-debugging case cannot be relabeled fresh blind. Historical packages may stay immutable while future qualification changes.

## Performance Composition

Three quantities must stay separate: **main-thread stall**, **dictation writer wait**, and **background operation wall time**. The M14 final handoff reports approximately 205 ms worst observed dictation-writer wait during profile computation and 174 ms during export. The same handoff reports approximately 560 ms profile p95 wall time and 509 ms export p95 wall time for its recorded workloads. These are historical measurements from its named final benchmark, not measurements made by this audit and not an end-to-end dictation latency. [docs/v2/handoffs/M14.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md)

Those waits are a plausible M15 latency risk and a real correctness/performance trade-off after stronger authority checks. This review has not established a current numerical requirement violation by equating a writer maximum with a main-thread budget or by adding independent medians. M09/M13 query budgets and M12 arrival/commit figures are different workloads. M12’s low-latency core receipt benchmark also excludes optional collector evidence; that work must be visible in composition measurement. [docs/v2/handoffs/M09.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M09.md) [docs/v2/handoffs/M12.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M12.md) [docs/v2/handoffs/M13.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M13.md)

Synchronous Hub paths inspected include Transforms CRUD and Export Validate; other configuration/note/review controls require the complete main-thread caller census. Validate can read a package without blocking the Store but still block the UI. Profile/export final writer checks can contend with dictation even when their overall work is on a background thread. Do not solve either problem by weakening authority checks. [localflow/v2/ui/hub.py · tableViewSelectionDidChange_, _transform_write, exportValidate_, _refresh_export_pane](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py); [localflow/v2/transforms_store.py · add_transform, update_transform, _append_revision](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

Local qualification must first establish a fresh isolated current-pipeline E2E baseline on the reference Mac with cached models and real terminal receipts. Then run controlled **pairwise** contention: dictation plus one of profile, export, learning mining, Insights, autosave or Hub search at a time. Report p50/p95/p99, sample counts, maximum writer wait, maximum main-thread stall, background wall time, warmups, model/config revisions and missing/fallback strata. Run no test sweep concurrently and use no-op/delay controls to establish that benchmarks reach their intended work.

## Documentation / Registry / Verification State

The fully inspected registry contains 33 LF-R requirement IDs and 22 EV suite IDs, with no requirement lacking a catalog mapping. It does **not** contain a current executable test-file/production-call mapping. Therefore the orchestration claim “every requirement is covered by a suite” can be true as a catalog statement without proving each test exists, reaches production or currently passes. M15/M16-owned future suites must remain qualification obligations, not fake current greens. [docs/v2/registry.json · 33 requirements and 22 suite identifiers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/registry.json); [docs/v2/LOCALFLOW_V2_MILESTONES.md · M14/M15 prerequisites and acceptance criteria](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md)

CROSS-AUDIT-08 separates stale current STATUS assertions from intentional historical provenance. The JSON document’s schema_version=1 is not a database-version contradiction. A historical source_commit/benchmark should remain historical while current campaign state points to final production/evidence and the actual M11 gate. Do not destroy useful history merely to make STATUS and ORCHESTRATION look identical. [docs/v2/STATUS.json · implementation-era status and benchmark fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/STATUS.json); [ORCHESTRATION.html · campaign state and M15 dependency eligibility](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/ORCHESTRATION.html); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

VERIFICATION uses stable check IDs, instruction revisions, code refs and browser-local state under `localflow.v2.verification/state@1`. The inspected authoring rules mark older instruction results stale and retain their history. This audit did not receive Daniel’s browser-local export and does not infer his results from committed HTML. The orchestration/handoff total is 80 checks; the complete independent unique-ID/count/JS reconciliation is **not closed** here. A partial search match count is explicitly not used as proof of 80 unique checks. [docs/v2/VERIFICATION.html · stable check IDs, instruction revisions and browser-local results](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/VERIFICATION.html)

M01-V011 is explicitly superseded by the M15 latency gate. Some older checks name earlier schema/code baselines; a local reconciliation must decide whether their instructions remain valid, need a revision, or are superseded by newer native automation. Neither a new native pass nor a changed source SHA automatically marks a human check complete.

## Historical Residual-Risk Ledger

This ledger consolidates material residuals located in the reviewed handoff sections. It is not a claim to have independently reexecuted every historical case or enumerated every sentence in all appendices.

| Owner | Residual / compatibility lead | Current applicability | Accepted / superseded distinction | M15 relevance |
|---|---|---|---|---|
| M01 | Installed/source/config/model identity and historical latency pilot | Still applies to installed-build claims; source ancestry is now verified | V011 explicitly superseded by M15 latency qualification; preserve historical evidence | Current installed identity before a meaningful native/model qualification · [docs/v2/handoffs/M01.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M01.md) |
| M02 | Capture consent, retention/deletion, store repair and backup parity | Core contracts remain; later-family repair gap is new -01 | Old M02 isolated repair success does not cover later table families | Yes for repaired-store/data qualification; native/private checks remain separately owned · [docs/v2/handoffs/M02.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M02.md) |
| M03 | Microphone/hotkey/sleep/restart and retained-audio recovery | Still applies to actual hardware and runtime | Portable lifecycle logic is not hardware evidence | Before corresponding M15 reliability claims; do not fake human completion · [docs/v2/handoffs/M03.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M03.md) |
| M04 | Grammar edge cases, literals and numeric normalization under real dictation | Still applies; retain explicitly bounded grammar | No justification for redesigning grammar during seam repair | Model/native language-quality checks remain required for covered claims · [docs/v2/handoffs/M04.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M04.md) |
| M05 | Scoped vocabulary and dictionary native workflow; qualification source honesty | Canonical approval composition is source-supported | Previous raw-scope/dictionary corruption issues reported repaired | New -04 term-provenance witness; native dictionary workflow remains human · [docs/v2/handoffs/M05.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M05.md) |
| M06 | Native destination/AX/browser identity and permission conditions | Still applies; late context is explicitly job-bound | Older strict-selection leads subsequently repaired with M08/M11 where documented | Required before actual destination-safety qualification; not an audit-start blocker · [docs/v2/handoffs/M06.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M06.md) |
| M07 | Long-prompt human trial; lexical validator and model near-tie limitations | Still applies; model assertions are not complete human-semantic proof | Protected mapping/chunk/fallback-false-green issues reported repaired | Current model compatibility and semantic qualification remain required · [docs/v2/handoffs/M07.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M07.md) |
| M08 | External owned-target, clipboard-late-consumer and undo boundary | Bounded transaction policy remains intentional | Do not reopen repaired selection/target authority without a new witness | Owned native qualification before affected release claims · [docs/v2/handoffs/M08.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M08.md) |
| M09 | Synchronous CRUD, Hub foreground Paste Again policy, manual accessibility | Still applies; old Move/Teach defects have later owners | Move repaired by M12; rendered Teach repaired by M14 | -05/-06/-07 functional seams; unresolved main-thread/cross-pane checks · [docs/v2/handoffs/M09.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M09.md) |
| M10 | Real style/snippet/file/skill workflow and partial-listing semantics | Still applies; no file-chip surface is claimed | Spoken inline syntax limits may be intentional; no global re-scope | Native functional checks and current downstream confinement corpus · [docs/v2/handoffs/M10.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M10.md) |
| M11 | Real-model exit 1, misdirected review, output-limit fallbacks, benchmark/model gaps | Explicitly still gates M15 | Cloud remediation replay is inherited; old blind cases now exposed | YES: model gate remains; plus transform revision/editor/unknown repairs · [docs/v2/handoffs/M11.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md) |
| M12 | Core note receipt vs optional evidence crash gap; bounded dedup history | Intentional separate guarantees, not false durable-evidence promise | Old M09 transfer and note revision races reported repaired | Require note->learning/export witness; manual V001–V005 unchanged · [docs/v2/handoffs/M12.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M12.md) |
| M13 | Native Insights/usage checks; Apply Retention at minimum width; no later unverified upgrade | Manual checks and UI lead remain; no automatic late confirmation is policy | Readiness owner/role weakness subsequently repaired by M14 | UI lead must be reproduced/closed; content/usage independence must remain · [docs/v2/handoffs/M13.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M13.md) |
| M14 | Publish rename before completion commit; Validate repaint; no Hub Undo; direct-SQL pair forgery; writer waits | Individually adjudicated below, not bundled as one failure | Validate is -07; SQL-forgery boundary bounded; service reversibility preserved | Code findings plus explicit policy/native/performance closure before next phase · [docs/v2/handoffs/M14.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md) |

## Manual / Native / Model Verification Ledger

**No human check was performed or marked complete.** “Pending” means the committed evidence/runbook leaves it unresolved; this audit cannot see private browser-local results. Historical native fixture passes are evidence for those exact fixtures and SHAs, not substitutes for the checks below.

| Owner | Stable identifiers / provenance | Remaining verification | Disposition |
|---|---|---|---|
| M01/M02 | M01 verification baseline; M02-V001–V009 in inspected runbook | Native identity/config/models, copied-store backup/migration, capture consent, delete-everywhere, shutdown | Only current receipts can establish prerequisite environment; M01-V011 superseded; no browser-local completion inferred |
| M03–M06 | Earlier owned checks remain in their handoffs/runbook; exact full ID census not completed | Hardware capture/lifecycle, numeric/dictionary/destination/permission behavior | May run beside remediation where unchanged; target-safety/permission evidence required before qualification |
| M07 | native-m07-long-prompt-cleanup-trial | Long AI prompts, constraints, corrections, protected literals and undo-cleanup recovery | Human/model semantic quality is not superseded by static lexical gates |
| M08/M09 | M08 owned-target checks; M09-V001–V007 | Target/clipboard/undo plus appearances, keyboard, recovery/History, foreground paste policy and diagnostics | Run affected native regressions during remediation; human judgment stays pending |
| M10 | M10-V001–V004 | Real styles/one-shot modes/snippets, chosen skills, resolved-file text, terminal multiline behavior | Reported native pane passes do not close these human workflows |
| M11 | M11-V001–V006, r1, code 9a049b3; model receipt at f8bf7e5 | Strict selection/password denial, Prompt Engineer/retry/chaining/undo, note Unicode, custom/legacy modes and window size | Explicit M15 blocker: actual model failure plus unclosed native/human/model qualification; exposed cases cannot be fresh holdout |
| M12 | M12-V001–V005, r1, code b17aa2b | Dictation/typing/switching/emoji, crash/reopen, attachments/export, note transforms/refusals, restore/History transfer | Pending human checks; native automation may cover portions only with documented supersession |
| M13 | M13-V001–V005, r1, code 36e03a2 | Counts, filters, real retry exactly once, Delete Usage while content remains, minimum-width/keyboard/larger text | Pending human; inherited Apply Retention geometry lead must not disappear in redesign |
| M14 | M14-V001–V007, r1, code 9d0cfdf | Copied-store v13, Teach/approve, labels, same-input A/B, split/offline export, Your Voice/exclusion/deletion, keyboard/larger text | Pending human; fix affecting seams first, then preserve or version the instructions |

The M11 40-case receipt is **historical execution with an unresolved negative result**, not NOT_RUN. In contrast, this audit’s proposed cross-system targets are all NOT_RUN. Keeping those two meanings separate is essential. [docs/v2/handoffs/M11.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md)
No old human check is silently superseded by new automation. The local agent must identify the exact invariant that a native test now proves, preserve the historical check, and follow runbook policy for instruction/status reconciliation.

## M15 Readiness Matrix

This matrix separates what exists in source, what prior execution reports establish, and what remains to be qualified. M15 itself was not started. The dependency list alone is not authorization. [docs/v2/LOCALFLOW_V2_MILESTONES.md · M14/M15 prerequisites and acceptance criteria](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md) [docs/v2/handoffs/M11.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md)

| Prerequisite / acceptance obligation | Classification | Current evidence / blocker | Required next evidence |
|---|---|---|---|
| Canonical main and accepted production ancestry | Satisfied by current static evidence | All M01–M14 production anchors are ancestors of the audited head | Revalidate on local sync; inspect intervening commits |
| M03 job/attempt and worker/capture reliability | Source-supported plus historical automated evidence; fresh native verification pending | Coordinator/attempt paths inspected; no current target execution here | Run affected lifecycle integration and owned native probes |
| M07 faithful cleanup and protection | Historical automated/model evidence exists; current real-model/human compatibility pending | Protected occurrence/chunk safety reported repaired; static gate not semantic oracle | Rerun only affected compatibility, then M15 semantic/reference criteria |
| M08 external target/clipboard/undo correctness | Historical native evidence; pending affected native and human checks | Accepted strict ownership preserved in source/handoffs | Owned fixtures only; no live user apps/data |
| M11 transform definition/source authority | Blocked by cross-milestone findings | -02 definition/history identity; -05 stale editor; -06 unknown Add | Reproduce and narrowly repair; compatible transform/export tests |
| M11 requirement-preserving model behavior | Pending real-model verification with an existing unresolved failure | One misdirected review and 14 output-limit fallbacks in reported 40-case run; benchmark also unclosed | Close actual model gate with valid references and exposed/new holdout distinction |
| M13 exactly-once usage and independent retention | Source-supported and historical automated evidence; cross-producer/native proof pending | One logical job fact and usage redaction boundary inspected | Independent full-producer reduction and active UI deletion tests |
| M14 speech profile and evidence liveness | Blocked by cross-milestone findings | -03 capture denominator, -04 historical term provenance, -01 support-table repair | Repair then threshold/support/usage-redaction corpus |
| M14 family-safe readiness/export and offline closure | Shared predicates source-supported; blocked upstream lineage/repair; fresh round trip pending | -01 lost exposure history, -02 frozen definition; known publication residual | Requalify same cohorts/partitions, offline validator and crash-recovery decision |
| M15-AC01 model adapters/offline operation | M15 qualification not run; static/current implementation only | Pinned default models are not a qualification result | Later M15 after authorization; no provider key prerequisite for local use |
| M15-AC02 critical meaning / prompt preservation | Pending real-model and human-reference qualification | Zero applied semantic failures in one old stratum is not complete release evidence | Current referenced corpus and honest critical-error analysis |
| M15-AC03 performance and S24 budgets | Pending reference-Mac measurement | Historical M14 writer waits do not prove E2E pass or fail | Fresh isolated E2E plus controlled pairwise contention |
| M15-AC04 failure, timeout, fallback, memory and actual delivery | Pending native/system/model qualification; -06 relevant | No complete current composite measurement was run | Fault probes with independent real terminal outcome |
| M15-AC05 optional comparator | Not applicable when deliberately skipped with disclosure | Optional cloud access is not a local product prerequisite | Record skipped; never fabricate comparator scores |
| M15-AC06 challenge counts/references | Pending model/human dataset qualification | Required 140 speech clips plus 20 negatives; not created or reviewed in this audit | Verify exact counts, categories and separate reference authority |
| M15-AC07 portable/live evidence closure | Pending automated/offline and human evidence | 25-case portable pack and at least 10 live reviewed jobs are later qualification obligations | Synthetic cross-audit corpus does not substitute for reviewed real evidence |
| M15-AC08 missing comparator credentials | Pending later automated qualification; intended behavior explicit | No optional credentials should break ordinary local operation | Negative credential fixture, offline baseline intact |
| Documentation and registry/test/verification chain | Partially source-verified; -08 plus inventory gaps | Catalog 33/22 established; complete testpath/DOM/current-status mapping not closed | Reconcile after code/evidence, preserve history |
| Quiet Editorial / product-quality phase | Not started; outside audit implementation scope | Functional surfaces are inventoried, not redesigned | Only after cross-milestone repair closure; independent UI review before M15 |
| Daniel’s outstanding human checks | Pending human verification, not automatically all audit blockers | Some prerequisite evidence matters for later authorization; others can run in parallel | No automatic completion or silent supersession |

## Critical Findings

No CRITICAL finding is confirmed by this review. The missing membership-table repair witness has a potentially serious exposure consequence, but it requires explicit current-store corruption/repair and is classified HIGH rather than inflated into a proven ordinary-path blind-evaluation contamination event. No native wrong-target action or private user-data loss was executed or observed.

## High Findings

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

## Medium Findings

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

## Low Findings

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

## Test Gaps

### TEST-GAP-01 — Exhaustive local caller and service inventory

Resolve all tracked callers of the authority-bearing symbols/services before edits. Connector search misses and selected excerpts cannot prove absence.

**Impact:** All repaired seams; prerequisite to narrowing repair ownership.

### TEST-GAP-02 — Registry -> current test -> production branch

33/22 catalog mapping is verified, not executable coverage. Inventory existing test files, functions and actual production calls; mark future EV-16/17/22 obligations honestly.

**Impact:** M15 evidence traceability; no fake green from dead or renamed paths.

### TEST-GAP-03 — Complete verification DOM/ID and browser-state reconciliation

Enumerate actual check articles, unique IDs, per-milestone counts, revisions, code SHAs and localStorage schema. Do not use raw HTML token counts. Private browser statuses are unavailable here.

**Impact:** Preserve manual ownership and historical instructions.

### TEST-GAP-04 — Every live-store opener and backup route

App startup was inspected, not every CLI/dev/benchmark entrypoint. Bind each possible migration path to synthetic old-store fixtures and backup observers.

**Impact:** Migration/data safety before release qualification.

### TEST-GAP-05 — Exhaustive event and managed-file authority census

Inventory all emit/exception/file-read/unlink paths; prove content canary absence and confinement with synthetic sentinels, symlink/FIFO/ancestor cases.

**Impact:** Privacy and all downstream reader equivalence.

### TEST-GAP-06 — Actual current-main cross-service execution

All 125 declarative cases, 12 relations and 18 mutations are NOT_RUN; prior isolated suites cannot fill those result cells.

**Impact:** Required reproduction and regression evidence, not universal preexisting failure.

### TEST-GAP-07 — Owned native Hub functional matrix

Transforms prompt editability/selector support, actual editor revision binding, Validate publication, Settings Apply Retention geometry, keyboard/focus and active deletion all need owned native probes.

**Impact:** Functional quality, not visual redesign.

### TEST-GAP-08 — Current reference-Mac E2E and contention

No summed medians, no background wall time passed off as writer wait, no all-heavy-workload attribution. Verify samples/branch work with negative controls.

**Impact:** S24/M15 performance qualification.

### TEST-GAP-09 — Offline package validator and recovery closure

Shared qualifier/build graph are inspected; every validator tamper case and crash-recovery route was not executed or fully inventoried.

**Impact:** Preserve model-task lineage after -02 repair; resolve publish/receipt residual.

### TEST-GAP-10 — Current model/human semantics

M11 historical failure remains open; M07 long-prompt trial and native/manual gates are not fulfilled by static analysis.

**Impact:** Do not claim product/M15-ready after only portable fixes.

## Design Concerns

### DESIGN-01 — Service undo versus promised user-visible reversibility

M14’s service-side undo is reported implemented and revision-aware, while the Hub has no Undo approval control. The product promise of user-controlled reversible personalization is not satisfied merely by a hidden API, but this is not evidence that the underlying undo transaction is wrong. Record the missing visible action as a functional product-surface obligation for the subsequent authorized phase; decide explicitly whether a minimal control must precede it. A visual redesign is not required to add a correct control. Preserve later user edits and exact owned deltas. [docs/v2/handoffs/M14.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md) [docs/v2/LOCALFLOW_V2_MILESTONES.md · M14/M15 prerequisites and acceptance criteria](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py)

### DESIGN-02 — Valid published package without a committed completion receipt

The exporter writes the completion row inside publish_op, renames staging to destination, then Store commits when the callback returns. A deterministic crash hook **after successful rename and before Store commit** leaves a complete standalone package but no committed completion row. The same export ID’s normal receipt lookup cannot establish completion from a missing row. Source existence is not proof the DB commit happened. [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py); [localflow/v2/store.py · _MIGRATIONS[13], _CORE_DEPENDENTS, Store._migrate, submit](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py)

**Witness:** create a synthetic export and prior destination; pause immediately after rename; terminate only the owned child process; reopen the copied synthetic Store; validate the destination offline; inspect the absent receipt and any moved-aside directory; retry the same export ID both before and after consent/source changes. Record all filesystem names and DB state, not just process exit.

**Adjudication:** a recoverable Store/filesystem reconciliation concern, not a demonstrated corrupt dataset. Do not invent a committed receipt or delete a valid orphan package. Prefer an explicit publication journal/intent plus conservative recovery that recognizes the package identity and records the historical publication without granting new current evidence/consent. A simpler accepted policy may quarantine/report the orphan for explicit recovery. This is not intrinsically a blocker to doing other M15 science, but recovery must be adjudicated and tested before a release claim or any assumption that a missing receipt authorizes a fresh blind/consented export.

### DESIGN-03 — Direct-SQL pair forgery

The known pair-writer residual is bounded if every supported producer binds task/source authority and export requalifies the full pair. Arbitrary SQL can bypass service admission by definition. Maintain corruption tests and fail-closed export, but do not require impossible protection against rewriting the entire database as a prerequisite to ordinary supported behavior. The reviewed shared pair qualifier checks same task/input hashes, retained source/output and definition references. [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py) [docs/v2/handoffs/M14.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md)

### DESIGN-04 — Writer-time correctness cost

Approximately 205/174 ms worst observed writer waits deserve fresh pairwise latency measurement, not immediate removal of requalification. Moving expensive computation off the writer is useful only if the immutable snapshot/final fence is preserved. Keep main-thread async work, writer critical-section duration and background wall time separate. No existing end-to-end budget violation is established merely by comparing these maxima with unrelated medians. [docs/v2/handoffs/M14.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md)

### DESIGN-05 — Optional AI interpretation and Paste Again destination policy

Your Voice remains deterministic and local. An optional future AI interpretation layer may be considered after correctness and privacy semantics stabilize, but no provider/key/network dependency belongs in this remediation. Separately, History Paste Again invoked from a foreground Hub needs an explicit user-facing destination workflow; the existing M09 residual is a product policy question, not proof of unauthorized insertion. Native qualification must test the declared destination, not assume focus magically returned to the prior external app. [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py) [docs/v2/handoffs/M09.md · current remediation addendum; historical text is not a current run](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M09.md)

## Areas Verified Strong

The following are **source-supported boundaries**, not a blanket runtime certification:

- **Canonical lineage:** all accepted production anchors M01–M14 are ancestors of pinned main, including the actual M11 replay/final repair rather than the old cloud branch SHA.
- **Current-purpose final text:** History resolves current final lineage; Teach carries rendered artifact/hash and checks it inside the minting operation. [localflow/v2/history_queries.py · current-attempt lineage and final-text resolution](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py); [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py)
- **Frozen context/protection:** the coordinator uses job-scoped context and explicit downstream revisions, maps protected spans through normalization, and abstains from unsafe unprotected cleanup. [localflow/app.py · _retry_job, _m11_apply_transform, completion and usage producers](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py · job_started, retry_snapshot, _publish, on_failure, on_normalization_result](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py)
- **Canonical learning authority:** approval uses M05 scope and writer mutation, with pending/live evidence checks, counterexamples and a reversible delta in one operation. [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py); [localflow/v2/vocabulary_store.py · writer-authoritative update and revision history](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py)
- **Note-region provenance:** M14 consumes canonical occurrence-safe rebasing and keeps only attributable dictated changes; typed-only text and ambiguity are not automatically acoustic evidence. [localflow/v2/learning.py · teach_correction, _mine_note_candidates, approve, _plan_in, undo_approval, _undo_fields](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py)
- **Shared task evidence:** owner/role/task/payload/digest qualification and explicit human judgment are shared by readiness/export; auto-apply is not accept. [localflow/v2/curation/evidence.py · qualify, cleanup_qualification_in, transform_target_in, preference_pair_in](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)
- **Usage/content separation:** M13’s contract preserves one logical dictation fact and independently redacts usage-derived profile copies; profile final publication reads current usage authority. [docs/v2/contracts/analytics.md · one logical dictation, terminal outcomes, D11/D13](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/v2/profile.py · _eligible, _compute_once, _scrub_dead_evidence](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py)
- **Exposure and publication fences:** current exposure across assignment versions is checked at new export, and selected-dependency recheck plus rename is serialized against supported Store deletions. The repair/crash qualifications above remain essential. [localflow/v2/curation/splits.py · historical exposure and assignment](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/splits.py); [localflow/v2/curation/export.py · _select, _dependencies_hold, build/publish_op, _write_graph](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py)

## Cross-Milestone Adversarial Corpus Summary

The separate JSON is a **declarative specification**, not a runnable test suite or evidence of target execution. It contains:

| Component | Count | Execution |
|---|---:|---|
| Category-specific base cases | 87 | NOT_RUN |
| Finding-specific fail-first reproductions | 8 | NOT_RUN |
| Required multi-hop scenarios | 15 | NOT_RUN |
| Deterministic stateful schedules | 15 | NOT_RUN |
| **Total target cases** | **125** | **NOT_RUN** |
| Metamorphic relations | 12 | NOT_RUN |
| Mutation specifications | 18 | NOT_RUN |
| Required category coverage | 29 / 29 | Specification coverage only |

All fixtures are synthetic. Each case has a semantic oracle and a source/service binding obligation. A control must demonstrate the intended branch is reached; an import error or unused fixture is not a useful finding reproduction. Declarative names describing seams are not claims those driver APIs already exist.

## Stateful / Metamorphic / Mutation Plan

Use named barriers, events or condition variables—not sleeps. The 15 schedules cover retry/query publication, live focus after freeze, vocabulary/definition revisions, note/usage/artifact deletion during mining/computation, export recheck/rename, row reorder, approval/user edits, note autosave, Teach/retry, exposure/build and rename-before-commit crash.

The export recheck/deletion schedule must respect single-writer ordering: after the recheck, a competing deletion may be **queued**, but it cannot commit until the publication callback finishes. A harness that waits for that queued deletion to commit while holding the writer would deadlock and prove nothing. Test both legal serial orders independently.

Metamorphic relations state that reducing authority cannot increase capability; retries cannot create additional captures; scope narrowing cannot broaden matching; deleted usage/content cannot recreate the other domain; unapproved learning cannot alter output; exposure is monotonic; old generations cannot overwrite new state; unsupported cards disappear; and unrelated deletion does not unnecessarily invalidate an export.

A mutation is **KILLED only if its intended production branch was reached and an independent semantic assertion failed**. Import/setup errors, unrelated crashes and wrong-driver failures are INVALID. Equivalent/surviving mutants require adjudication, not relabeling. All mutation outcomes in this audit remain null/NOT_RUN. No target mutation was applied here.

## Recommended Repair Order

1. Freeze the exact audited base, safely sync the local worktree, and complete the tracked caller/interface/test/backup/verification inventories. Do not delete historical worktrees or overwrite local work.
2. Reproduce -01, -02 and -03 first with fail-first cross-service tests. Preserve the failing-base evidence and independently classify any refutation or narrower precondition.
3. Repair Store family integrity, transform writer/revision serialization, and profile logical-capture identity. Preserve existing per-attempt evidence and canonical domain authority.
4. Repair -04 historical technical-term provenance; repair -05/-06 transform editor revision/operation identity; repair -07 pane validation state. Native accessibility probes are functional, not redesign work.
5. Execute the relevant portable, stateful, metamorphic and mutation corpus, then broad affected M01–M14 compatibility. Adjudicate export crash recovery and Undo product obligations explicitly.
6. Run owned native probes and isolated current-reference-Mac performance after correctness converges. Preserve real-model qualification as a distinct gate; do not retune exposed cases and claim blind success.
7. Freeze first-pass production, obtain a fresh-context independent read-only review, independently reproduce reviewer allegations, repair confirmed issues, and rerun final evidence.
8. Reconcile STATUS, ORCHESTRATION, handoffs, acceptance records, registry and VERIFICATION after final code/evidence. Preserve historical results and Daniel’s manual ownership. Follow current CLAUDE.md for complete-work commit/push/merge; then STOP.

## Cross-Milestone Readiness Verdict

**B — Proceed after targeted cross-milestone repairs.**

The inspected system has enough shared canonical authority to justify narrow repairs rather than a wholesale redesign. It also has specific composition defects that isolated milestone acceptance did not cover. Three HIGH findings and four MEDIUM findings require local adjudication and, where reproduced, regression-protected repair. The LOW current-state documentation seam should close after code/evidence converge.

This verdict is **not** “all remaining paths verified,” “M15 ready,” or permission to skip the named coverage gaps. The local campaign must close its actual inventory/execution obligations and keep the failed M11 model gate visible. Daniel’s human checks remain untouched. Quiet Editorial remains a separate later phase, followed by independent product-quality review, then M15 and M16 only under their respective authorization.

**Audit target execution: NOT_RUN. No GitHub mutation or remediation performed.**

