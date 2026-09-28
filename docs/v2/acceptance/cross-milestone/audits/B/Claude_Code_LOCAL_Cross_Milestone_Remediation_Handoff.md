# Claude Code LOCAL / Opus 5.5 — Final Cross-Milestone Remediation Handoff

**Repository:** `scalinity/LocalFlow`  
**GPT audited main:** `340c566686c7123bfcf721e16160aacabbe0b97d`  
**Date of read-only audit:** 2026-09-28  
**GPT target execution:** `NOT_RUN` for every case; no local/native/model/human result was produced.

> This is a LOCAL remediation on Daniel's Mac against canonical main after all M01–M14 milestone remediations. Do not reopen milestones wholesale. Reproduce each cross-milestone allegation, repair the narrow owning seam, and preserve all accepted milestone behavior.

## 1. Mission and non-negotiable boundary

Use the attached audit, `LocalFlow_M01_M14_Cross_Milestone_Adversarial_Corpus.json`, and `LocalFlow_M01_M14_Interface_Matrix.md` as source-backed allegations and a declarative test specification—not as already executed evidence. Read this entire handoff before editing. All GPT corpus cases start NOT_RUN/NOT_BOUND. Bind them to actual local production services through the inventory below.

Your task is bounded cross-milestone correctness remediation and its evidence. It is not another wholesale M01–M14 audit, not a new product architecture, not model training, and not the Quiet Editorial redesign. Do not start M15 or M16. Do not perform or mark Daniel's outstanding human checks, including the copy-of-his-real-store M14-V001. Do not access his live transcripts, notes, apps, profiles or exported data for fixtures. Native automation uses owned synthetic windows and disposable stores only.

The top-level invariant is one logical dictation with one coherent identity, frozen intent, capture provenance, governed content lineage and truthful outcome. No consumer may strengthen authority upstream did not prove. Deletion, expiry, exclusion, exposure and unknown outcomes propagate monotonically. Reuse stronger canonical authority instead of reimplementing weaker checks.

## 2. Safe startup — inspect first, never destroy local work

Run and record privately:

```sh
pwd
git status --short --branch
git branch --show-current
git rev-parse HEAD
git remote -v
git worktree list
```

Verify the repository is LocalFlow and the remote really identifies `scalinity/LocalFlow`. LocalFlow has historical audit/reviewer worktrees: do not automatically remove, repurpose or clean them. Do not automatically reset, clean, stash, discard, force-checkout, delete a branch or remove a worktree. If changing branches or syncing would overwrite work, STOP and report the exact conflict without attempting a workaround that loses data.

Read current `CLAUDE.md`, project instructions, START_HERE, STATUS, ORCHESTRATION, the contracts index, all relevant handoffs and remediation addenda. Current CLAUDE.md forbids co-author/attribution trailers and requires a **completed**, pushed remediation to merge onto main in the same session. It forbids incomplete merges and force-push. Pending human checks alone do not block the completed-remediation merge; they remain checks against main.

Then:

```sh
git fetch --all --prune --tags
git rev-parse origin/main
git log --oneline --decorate -20 origin/main
git merge-base --is-ancestor 340c566686c7123bfcf721e16160aacabbe0b97d origin/main
```

Record audited SHA, local pre-sync SHA and remote main at sync. If origin/main differs from the audit, inspect the complete intervening delta and rebind every affected finding/test. Do not claim the old audit covers new code. Non-descendant/unexpected history, conflicting local work or uncertain ownership requires STOP, not a guessed merge.

When demonstrably safe:

```sh
git switch main
git merge --ff-only origin/main
git rev-parse HEAD
git switch -c cross-milestone-remediation-20260928
```

Use another descriptive unique branch name only when that name already exists; never replace an existing branch. Record local main after sync, branch and environment. Freeze the actual audited/reproduction base before changes. Preserve the fourteen accepted anchors listed in the audit; M12 `b17aa2b`, M13 `36e03a2` and M14 `9d0cfdf` must remain inherited.

## 3. Environment and evidence boundary

Record Mac model/chip, RAM, OS/build, interpreter and dependency versions, model IDs/quantization/cache provenance, app launch mode, commit/dirty state and relevant adapter identity. Do not claim the installed bundle equals source HEAD without evidence. Keep personal paths out of committed evidence.

Follow the repository's existing acceptance/remediation evidence layout; inspect it before creating records. Do not create a parallel undocumented evidence system. Use disposable synthetic HOME/Application Support, stores, artifact roots, journals, notes, managed attachments, destination windows and datasets. No real-data migration or automated human check is authorized by this handoff.

## 4. Exhaustive tracked-file caller inventory BEFORE production edits

Run a tracked-file inventory, not connector search. Use `git ls-files` to constrain `rg` and preserve an interface ledger. At minimum search the following tokens and their actual aliases/callers:

```text
job_id attempt retry source_job_id artifact_id role stage final_text mode
scope canonical_scope_value destination context_snapshot context_snapshot_id
insert clipboard copy_text pasteboard note revision expected_revision
usage_facts learning_candidates profile_snapshots profile_evidence
split_assignments training_memberships export outcome_unknown generation
operation_id receipts Store submit backup_dir
```

Also inventory every M01–M14 service class and every Store-opening CLI/dev/benchmark path. Trace every direct clipboard write—not just insertion service methods. For each finding identify the real producer, all consumers, state/receipt identity, deletion listeners, source role, callable UI thread, failure/timeout path and owning tests. Do not edit until this ledger explains the failing seam.

For registry coverage map each of the 33 LF-R entries through its EV suite to a tracked current file, executable case and production branch. A directory or test name alone is not proof. Inspect tests that compare two outputs after both were produced under the same allegedly interfering state; require a real controlled before/after witness.

## 5. Findings to adjudicate, not blindly accept

| ID | Severity | Primary owner | Allegation / narrow seam |
| --- | --- | --- | --- |
| CROSS-AUDIT-01 | HIGH | M09 | History can prefer an old training manifest over a newer collection-off retry |
| CROSS-AUDIT-02 | HIGH | M14 | Your Voice can count multiple transcriptions of one capture as multiple dictations |
| CROSS-AUDIT-03 | MEDIUM | M14 | Historical dictionary use is rendered using the entry’s current spelling |
| CROSS-AUDIT-04 | HIGH | M08 | Recovery Copy Last Raw bypasses pending clipboard-paste ownership |
| CROSS-AUDIT-05 | HIGH | M02 | Torn-schema repair can erase governance links while leaving a current private profile |
| CROSS-AUDIT-06 | MEDIUM | M14 | A late Export refresh can overwrite a completed Validate result |
| CROSS-AUDIT-07 | MEDIUM | M14 | Export Validate runs potentially large filesystem work on the Hub callback |
| CROSS-AUDIT-08 | MEDIUM | M14 | Export rename and database completion commit need crash reconciliation |
| CROSS-AUDIT-09 | MEDIUM | M14 | Approved learning rules have service Undo but no Hub Undo Approval control |
| CROSS-AUDIT-10 | LOW | M14 documentation | Current STATUS fields still describe implementation-era M14 behavior and timings |
| CROSS-AUDIT-11 | LOW | M07 documentation | The central verification runbook has no M07 checks despite carried qualification work |


The source-backed audit contains full source locations, expected/likely actual behavior and minimal reproductions. Independently classify **every** record as `reproduced`, `refuted`, `narrowed`, `already_fixed`, `test_gap_only`, `design_only`, or `native_manual_model_unresolved`. Record evidence and the exact base SHA. Refuting an allegation with a production-path witness is a valid outcome; merely asserting the old owning suite is green is not.

Material reproduction priorities:

- **05:** populate a real synthetic current profile; close Store; corrupt only `profile_evidence`; reopen through actual migration/repair; delete source through supported API; call `current()`. Do not substitute an ordinary intact-link deletion test. A genuinely old empty schema is a separate control.
- **04:** keep a failed OLD_RAW; admit another delayed clipboard paste of NEW_FINAL; hold target consumption; invoke the real Recovery Copy Last Raw callback; release target. The claim concerns an internal LocalFlow copy, not the user's independently initiated clipboard change.
- **01:** ASR succeeds and cleanup fails while collecting, leaving an attempt-1 partial manifest; pause collection but keep transcript logging; retry same job successfully with attempt-2 output; read actual History/action authority. Do not “fix” this by deleting all old evidence.
- **02:** same capture/job, distinct retry examples with different ASR text. Use controlled adapter outputs to expose logical identity without requiring a probabilistic model outcome. Prove at least two-attempt inflation before the ten-dictation/2,000-word floor test. Independent captures are controls.
- **03:** apply vocabulary E revision1, then edit the SAME entry's canonical through M05; regenerate profile with no new dictation. Historical speech labels must not borrow current spelling.
- **06/07:** hold an older Models/Export refresh publication, complete Validate, release refresh; separately hold validator file work and measure UI acknowledgement. Result lifetime and main-thread blocking have independent assertions.
- **08:** stop a disposable export process after rename and before the SQLite completion commit. Restart and independently validate the package with no DB. Establish truthful recovery and same-operation retry, not just a vague crash-possible warning.
- **09:** establish service Undo as a positive control and inventory user-facing reachability. Add a bounded control through the existing safe delta service, or record an explicit accepted product deferral. No visual redesign.
- **10/11:** separate stale current fields from intentional historical provenance; reconcile M07's explicit pending long-prompt/real-text obligations with its empty central runbook section. Preserve old results and IDs.

Test gaps12–16 require actual caller/registry/relational-family/native publication/performance closure, not a global checkbox. Design17 asks for explicit contention-budget adjudication; design18 is a future optional Your Voice product note only—no LLM/API layer implementation now.

## 6. Freeze failing-base evidence and write cross-interface regressions

Before a fix, save the minimal failing witness, source/environment identity and independent semantic assertion. The failing witness must cross the interface alleged to fail. A unit test of `canonical_scope_value` cannot prove approval→vocabulary→runtime scope behavior. A test of ProfileService alone that creates every example under a new job cannot prove retry identity. A mock returning the expected answer cannot qualify a production path.

Record failure mode without private payloads: synthetic IDs, attempt numbers, artifact roles/hashes, state/receipt transitions, counts, barrier arrivals and semantic assertion results. Runtime/native/model allegations remain unresolved until their correct environment is exercised. A failing setup/import or wrong API binding is INVALID, not reproduced.

Do not change production until the caller inventory and failing base are frozen. Use the existing project editing conventions; do not bypass any repository rule for decision/evidence editing.

## 7. Corpus binding and execution

Bind the supplied **176 declarations**: 116 category scenarios, 15 required multi-hop scenarios, 15 stateful races, 12 metamorphic relations and 18 proposed mutations. Keep their original IDs. Add precise adapter bindings, fixture lineage and owning test nodes without rewriting assertions to match the current implementation.

If a case cannot bind, record NOT_BOUND/BLOCKED or a justified NOT_APPLICABLE; it is not a pass. Synthetic fixture construction may use direct SQL only for explicit corruption tests or a sanctioned fixture helper. Supported-producer tests must use actual production producers; do not fabricate admitted “gold” evidence to bypass their checks.

Every target result is separate from the GPT declaration's NOT_RUN status. Preserve the input corpus as the specification and write execution results in the established evidence layout. Report attempted, passed, failed, blocked, invalid and not-run totals independently.

## 8. Mandatory deterministic races and metamorphic relations

Use explicit event/condition barriers and controlled executors/clocks, never sleeps as race proof. Cover: retry during History query; changed target; vocabulary and transform edits after freeze; note deletion during mining; usage deletion and artifact purge during profile compute; deletion around export publication; row reorder; query-after-delete; approval versus user edit; autosave versus mining; retry while Teach is open; exposure during export preparation; rename followed by completion failure.

Respect real serialization. A competing writer operation cannot commit in the middle of another Store callback. Show which side linearizes first and test both reachable orders. An invented impossible interleaving is INVALID, not a product defect.

Metamorphic projections enforce: one capture despite retries; removing proof cannot grant authority; deleting source cannot create derived truth; narrowing scope cannot widen effects; live focus does not alter frozen context; original capture provenance survives retry; usage and content deletion remain separate; unapproved learning cannot alter output; exposure never resets; old query results cannot overwrite new actions; removing support suppresses unsupported profile claims; export removal is dependency-local.

## 9. Mutation evidence

Freeze passing-base witnesses first, then use a dedicated disposable mutation worktree. Preserve historical worktrees. For each mutation record intended branch, reached-branch evidence and independent semantic assertion.

A mutant is **KILLED only if the intended branch is reached AND an independent semantic assertion fails**. Import errors, syntax/setup errors, unrelated exceptions or an unreachable branch are INVALID. Record surviving mutants honestly and improve the witness rather than hiding them. Never count no-op/wrong-work benchmark controls as ordinary green performance results.

## 10. Narrow repairs and preservation constraints

Prefer canonical helpers and exact source authority. Repair current-attempt History selection without deleting legitimate historical examples; repair logical profile counting without erasing retry evidence; consume frozen vocabulary revisions rather than current config; route all internal copies through M08; distinguish corrupted current relational families from legitimate older schemas.

Keep the following accepted behaviors intact: M06 explicit late delta and whole-tuple fallback; M05 canonical scopes; opaque workspace/profile policy; once-per-job normalization; snippet output-coordinate protection; M07 source fallback; mode-specific M11 gates; transformed-final Teach refusal; strict selection/target binding; independent note authority after a durable move; one-job M13 usage; source/usage deletion independence; latest labels; review leases distinct from user pins; explicit approval only; exact delta undo; current exposure across old split versions; shared readiness/export qualification; offline closure.

Do not weaken checks to improve an old benchmark. Do not introduce an optional network/API dependency into deterministic Your Voice. No new training/promotional claims from synthetic fixtures. Direct SQL pair forgery alone is not a supported producer bypass; preserve export requalification and adjudicate threat model proportionately.

## 11. Required local execution order

1. Safe sync and verify lineage/drift.
2. Inventory environment, source and configured adapters.
3. Complete tracked caller/interface/openers inventory.
4. Freeze audited/reproduction base.
5. Bind the cross-milestone corpus.
6. Reproduce/adjudicate every material finding.
7. Adjudicate design/residual policies explicitly.
8. Freeze fail-first cross-interface regressions.
9. Apply narrow owning fixes.
10. Run portable bound corpus.
11. Run deterministic stateful probes.
12. Run metamorphic relations.
13. Run valid mutation checks.
14. Run affected M01–M14 owning-suite compatibility and broad final sweep.
15. Run owned synthetic native functional checks.
16. Run current touched-model compatibility where feasible; distinguish inherited M07/M11 prerequisites from this repair's regressions.
17. Validate benchmarks actually perform the declared work.
18. Run isolated reference-Mac performance and controlled pairwise contention, not concurrently with tests.
19. Freeze first-pass production SHA.
20. Obtain fresh-context independent review of that SHA in a separate read-only worktree.
21. Independently reproduce every reviewer allegation in the main remediation session.
22. Repair confirmed reviewer findings narrowly.
23. Rerun the required complete evidence after final production changes.
24. Reconcile docs/current state/registry without erasing history.
25. Write cross-milestone evidence and final dispositions.
26. Update runbook only under stable-ID/instruction-revision policy.
27. Realign orchestration to the actual next authorized phase.
28. Commit/push/merge completed remediation under current CLAUDE.md; no incomplete merge.
29. STOP. Do not start Quiet Editorial, M15 or M16.

## 12. Compatibility sweep and native matrix

Run every materially affected milestone-owned suite and a broad final sweep after correctness convergence. Do not blindly run giant unrelated model suites merely to produce a bigger total, but do not omit affected production pathways. For each file/node record passed/failed/blocked/not-run and exact reason for exclusion. A native suite excluded on a cloud interpreter is not passed; a later owned Mac run must have its own record.

Native checks use the actual coordinator and owned synthetic windows for implicated History/Recovery actions, note delivery, Styles/Snippets/Transforms, Insights, Review/A-B, Your Voice and Export Validate. Verify focus and keyboard reachability of any added Undo control without restyling the shell. Record current visible identity, action receipt, generation and closure behavior. Do not operate Daniel's real apps/data to make a native test easier.

## 13. Performance and model qualification boundaries

After correctness and review converge, measure the current reference Mac in isolation. Report separately:

A. Dictation critical-path p50/p95/p99 and maxima, with release timestamp and actual terminal/visible event definitions.
B. Background operation wall time and declared workload identity.
C. Dictation Store writer wait p50/p95/p99/max.
D. Main-thread stall/acknowledgement p50/p95/p99/max.
E. Controlled pairwise contention against idle baselines.

Use current cached models and real pipeline execution for model-dependent paths, with synthetic referenced fixtures where appropriate. Keep output-limit/fallback/error/timed-out attempts in the report. A posted-unverified transaction is not verified-visible insertion latency. No summing unrelated medians, no simultaneous giant test sweep, no attribution from all-heavy-workloads-at-once.

The historical M14 max waits of approximately 205 ms/174 ms must not be called current UI stall measurements. Establish actual tradeoffs while preserving correctness. An explicit approved requirement revision, if needed, is a policy decision with evidence—not silent threshold relaxation.

M11's integrated 40-case record is not all green: one misdirected review and fourteen output-limit fallbacks remain in its history. M07 explicitly retains its long-prompt trial and real-text stratum. Requalify touched seams without pretending this is M15 launch or calling exposed fixtures newly blind. If a prerequisite remains outside the narrow repair, retain it as an explicit M15 blocker; if your changes introduce/leave an unmet required repair gate, remediation is incomplete.

## 14. Independent review — mandatory

Use a fresh context, a separate read-only worktree and a frozen first-pass production SHA. The reviewer must inspect source independently, not merely restate your passing summary. Focus on identity handoffs, rendered actions, unknown outcomes, deletion/retention, weaker downstream reimplementations, schema repair families, private derived copies, readiness/export equivalence, exposure, performance false greens and documentation drift.

The main session independently reproduces every allegation and records reproduced/refuted/narrowed dispositions. Do not merge unreviewed last-minute production changes. After repairs, rerun the affected and required global evidence. Keep first-pass/final-production/evidence-docs SHAs distinct.

## 15. Evidence, privacy and documentation reconciliation

Create records in existing repository conventions for audited/base SHA, interface inventory, finding adjudications, corpus execution, stateful execution, metamorphic execution, mutations, compatibility, native matrix, benchmark validity/results, independent review and final disposition.

Before each evidence/docs commit, scan for `/Users/`, scratchpad paths, session UUID/path fragments, temporary worktree paths, live app names, live transcripts/notes, personal profile terms and exported path leaks. Truncated stack traces can omit `/Users/`; inspect fragments too. Store private detailed evidence outside commits as policy requires. Synthetic names/paths should still be normalized in published records.

Only after final code/evidence converges reconcile STATUS.json, ORCHESTRATION.html, handoffs, acceptance records, registry and VERIFICATION.html. Separate implementation provenance, current campaign state and historical result. Preserve useful historical benchmarks and failed runs; point current state to their superseding evidence.

Runbook IDs never renumber/reuse; count actual article IDs, not HTML examples. Preserve prior sections except authorized changes. Material instruction changes bump the relevant instruction revision; stale saved browser results remain history. Do not mark human checks passed. M01-V011 is explicitly superseded by M15, not passed; M07 has no current check articles despite pending obligations and needs an owned mapping. Verify localStorage/schema/import behavior separately if modifying it.

## 16. Completion, Git rules and merge

Use a truthful completion state such as `CROSS_MILESTONE_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION` only when all confirmed automatable repair defects, required native/compatibility/review/performance gates and assigned requirements have converged. Preserve separately named M15 model/human prerequisites. Do not imply M15 readiness from a completed remediation merge.

If a required repair gate remains unmet, report `CROSS_MILESTONE_REMEDIATION_INCOMPLETE` with exact blockers and do not merge. Follow current CLAUDE.md. No force-push. No Co-Authored-By trailer or co-author section. Do not remove accepted history. Completed pushed remediation merges onto main in this session: fast-forward when safe, otherwise an ordinary merge only when conflict-free and understood. Never guess a conflict resolution; STOP and report paths. Push main after the authorized complete merge. Record any main movement and rerun affected evidence as needed.

## 17. Final report — all 39 fields

1. GPT audited SHA
2. Local pre-sync SHA
3. Remote main at sync
4. Local main after sync
5. Remediation branch
6. Environment and configured model/adapter identity
7. Interface/caller inventory totals and unbound items
8. First-pass production SHA
9. Final production SHA
10. Final evidence/docs SHA
11. Files changed
12. Every finding disposition with failing/refuting evidence
13. Corpus totals by status and category
14. Stateful totals and reachable barrier evidence
15. Metamorphic totals
16. Mutation totals: killed/survived/invalid/not-run
17. Independent-review findings and main-session adjudications
18. Portable/broad compatibility sweep and exclusions
19. Owned-native functional matrix
20. Job/attempt identity result
21. Final-text/mode authority result
22. Scope/context result
23. External insertion versus Scratchpad result
24. History/Hub rendered identity and publication result
25. Analytics exactly-once result
26. Deletion/retention/usage independence result
27. Artifact/path authority result
28. Schema/migration/backup/repair-family result
29. Learning/vocabulary approval/undo result
30. Readiness/export/offline closure result
31. Your Voice/profile cohort/provenance/redaction result
32. Family/exposure result
33. Docs/state/registry/runbook reconciliation
34. Performance and benchmark validity, separately measured
35. M15 readiness matrix with exact classifications
36. Manual/native/model checks remaining, with owners/IDs
37. Residual risks and accepted policy decisions
38. Branch/main push and merge state
39. Truthful completion state and explicit STOP

Then STOP. The next authorized product sequence is cross-milestone correctness complete → separate Quiet Editorial redesign → independent UI/product-quality review → M15 qualification → M16 final acceptance. Do not begin any of those later phases here.
