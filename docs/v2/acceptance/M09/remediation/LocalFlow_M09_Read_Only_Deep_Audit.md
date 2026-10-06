# LocalFlow V2 — M09 Read-Only Deep Audit

**Repository:** `scalinity/LocalFlow`  
**Audited canonical main:** `7cd1111f0499e14bf110d2089c69fe4fa4075507`  
**Audit date:** September 26, 2026  
**Method:** committed-source/contract/test-oracle inspection through the connected GitHub repository. No repository modification, code execution, runtime reproduction, native trial or benchmark execution.

## Executive Assessment

### C. Significant Hub/query/evidence weaknesses

The canonical prerequisite passes: current `main` includes accepted M08 head `145488c` and final production `ea83bc1`, together with the accepted earlier foundations. The M09 audit is therefore not blocked on a missing M08 merge.

The current Hub is materially larger than its original five-view acceptance run. Its shared foundation has source-supported weaknesses in action identity, revocation, generation publication and evidence lifecycle. The most urgent paths are **a newly selected item paired with an old actionable detail/editor**, and **deleted private content remaining in existing Hub caches**. These are not cosmetic defects and are not a reason to redo the accepted M02/M03/M08 implementations.

This docket contains **2 Critical, 7 High and 14 Medium finding families**, plus **3 Test Gaps and 3 Design Concerns**. Severities are judgments about source-supported mechanisms, not claims of reproduced runtime incidents. Some related manifestations are deliberately consolidated. No Low finding is forced into the report merely to fill a heading.

The historical per-example listen gate, actual Retry button wiring and exclusive retry protections remain present. The M14 off-main abort is attributable to its **inline test dispatcher** in the inspected harness; a production off-main AppKit bug has **not** been established. Those distinctions must survive remediation.

The separate corpus contains **135 cases, all NOT_RUN**, including the twenty required stateful probes, seven proposed manual cases, 14 metamorphic relations and 28 mutation specifications. It is a normative corpus, not an executed harness or results report.

## Audit Boundary

> This audit covers committed GitHub state at `7cd1111f0499e14bf110d2089c69fe4fa4075507`. Any uncommitted local state is outside the GPT-6 audit boundary.

M09 owns the Hub shell/state/query/coordinator guarantees, History, Diagnostics, replay and inspection/annotation controls. M10–M14 are examined only where their current views consume those guarantees. This report does not judge style quality, transform semantics, Scratchpad storage algorithms, analytics arithmetic, learning classification, profile inference or dataset contents.

No tests were run. Native AppKit behavior, sound output, focus behavior, real memory/latency, live TCC state and subjective UI quality are unverified here. Existing results are described as historical records, never rerun evidence. The generated JSON files were checked only for document integrity and internal references; that is not product testing.

**Coverage limitation:** GitHub code search returned incomplete results, including an incomplete zero-result response for a known symbol. It was not treated as exhaustive. Directory/source inspection identified the callers listed below, but a full local `rg` inventory is mandatory before changing shared helpers. Large documents were inspected in relevant sections, and source scopes are recorded in the source index rather than falsely asserting every line was reviewed. This limitation is carried as M09-AUDIT-26; it does not erase the concrete paths already identified.

## Canonical Foundation

| Foundation | Accepted anchor checked | Ancestry observation |
|---|---|---|
| M01 | `3db7406` | Base equals merge base in comparison to audited main |
| M02 | `bfbc63c` | Audited main ahead 57, behind 0; base is merge base |
| M03 | `3e0d1ab` | Ancestor of M04, then M05→M06→R4→M11→audited main |
| M04 | `4ef219c` | Ancestor of M05 in direct comparison |
| M05 | `01a1f3c` | Ancestor of M06 in direct comparison |
| M06 | `4388b52` | Ancestor of R4 in direct comparison |
| M06 R4 | `46ecd5b` | Ancestor of reconciled M11 production `9a049b3` |
| M07 | `52edc47` | Ancestor of M01 anchor `3db7406`, hence audited main |
| M11 replay | `1545de9` | Ancestor of pre-M08 canonical `180278e` |
| M11 production | `9a049b3` | Audited main ahead 26, behind 0; base is merge base |
| Pre-M08 canonical | `180278ee8a157e7372ba187cfb0106556114293f` | Audited main ahead 21, behind 0; base is merge base |
| M08 production | `ea83bc198567d001e3d770ae5103ca369701825d` | Audited main ahead 9, behind 0; base is merge base |
| M08 accepted head | `145488c8962eb061b122c9ce9f3240bf730acef8` | Audited main ahead 2, behind 0; base is merge base |

These are ancestry checks, not claims that all inherited tests passed in this session. The M11 cloud heads `aa03af7`/`1be42ee` are not required ancestors: accepted remediation was replayed/reconciled, as the current handoff explains. [D13, D14]

The two commits after accepted M08 head are guidance/documentation changes: `2a28675fbc210b08c7e2e813b0839f4891207145` adds the auto-merge instruction to `CLAUDE.md`; `7cd1111f0499e14bf110d2089c69fe4fa4075507` records the M08 merge in orchestration/handoff. The comparison changes CLAUDE.md, ORCHESTRATION.html and the M08 handoff, not M09-facing production code. Accepted M08 tests, native/corpus/review evidence, benchmark records and runbook are present in the canonical diff; their contents are inherited evidence, not newly executed proof.

**Instruction conflict:** repository guidance now says to auto-merge a completed remediation. This task explicitly says not to merge to main and that Daniel merges later. The attached task takes precedence. The local handoff requires a dedicated branch push and **STOP, no self-merge**.

## Current M09 Architecture

The runtime shape is `AppDelegate → one HubController → pure-Python HubState → services → single FIFO Store writer`. The main window hosts Home, History, Styles, Snippets, Transforms, Scratchpad, Insights, Diagnostics, Models and Settings. Models includes Training Evidence/Review/Splits/Export; Insights includes Usage/Your Voice. App construction supplies the current services, not only the historical five-view dependencies. [S01, S02, S07, C01]

Queries materialize plain data off the AppKit thread and notify the shell. `_state_updated` dispatches `_refresh` using `AppHelper.callAfter`. Long actions likewise use a background worker followed by a main-thread completion. This is a good boundary, but shared dictionaries, selection state and action authority are not immutable snapshots; a correct dispatch call does not make their contents current. [S01, S02]

Read-only queries still use the one writer queue; “background” does not mean a separate unconstrained SQLite connection or zero interference. Training mutations generally create their artifact/lease/revision/state in one writer op. Schema is **v11**, not the historical M09 v5 or the older M14 closeout’s v10. No migration rollback is warranted. [S08, C02]

### Observed caller map and ownership

| Public/shared surface | Observed consumers | Audit treatment |
|---|---|---|
| HubController / HubState | AppDelegate, native Hub tests, M09 benchmark, later-view adapters | M09 shell and dispatch |
| HistoryQueryService | HubState, History tests, M09 benchmark | M09 query/read authority |
| TrainingDataService | Hub actions/state, tests/benchmark | M09 annotations/lifecycle |
| `_conn_*` annotation helpers | `training.py` note-evidence producer; downstream helper consumers must be enumerated locally | Preserve writer-only helper contract |
| ReplayService | History and Training buttons, tests, app Hub spec | M09 buffer/listening authority |
| `hubRetryJob` | Actual History Retry button and tests | M09 trigger; M03 remains retry authority |
| `hubPasteText` | Actual History Paste Again button and tests | M09 stable payload/identity; M08 remains effect authority |
| `_state_updated`, `_in_background` | All current shared view refresh and long-action adapters | Thread affinity plus generation/action ownership |
| deletion listener / retention pass | Store→AppDelegate pipeline/insertion revocation | Missing Hub cache/replay subscription is M09 boundary work |

This table is a source-derived inventory, not a substitute for the full local caller scan.

## Historical M09 Findings Revisited

**H1 — global listen gate:** the original global boolean has not returned. `listened_for` is tied to the example and cleared on selection change; successful playback initiation and selected/detail identity are checked before granting it. The current failure risks are stale editor/action identity, lifecycle restrictions and deletion of a previously prepared/active replay—not the original simple Replay A→save B bypass. Re-run both refusal and B-positive control through the current M14 tabs. [S02, S05, T01]

**H2 — dead Retry button:** the detail contains a job identity and the actual button keys off `job_id`; the old `kind`-only dead path is closed. The button can nevertheless resolve a stale A detail while B is selected, and it ignores some structured refusal outcomes. “The button fires” is weaker than “the button targets the right job and reports what happened.” [S02, S07, T01]

**H3 — double requeue:** active-job/nonretryable/deleted checks and the shared exclusive retry claim remain. The retained-job retry creates the accepted unscoped retry context. No duplicate-retry production defect is asserted solely from rereading these guards. Actual double-click/deletion/attempt interleavings remain corpus controls to preserve these repairs. [S07, D11]

## Modern Hub / Downstream View Integration

All ten view constructors and relevant adapters were inspected at the shared shell boundary. Later domain services are not re-audited. The strongest shared issue is that a displayed row/editor and the live backing dictionary can identify different objects during async refresh. M14 candidate Approve/Reject must use a rendered stable candidate identity, not a current first-row fallback; M10/M11 editor updates need the same identity discipline. [S01, S02, C09, C10]

Mine, Export and Your Voice have the correct background→main dispatch shape, but their completions lack an action/view generation. Mine’s unconditional return to Review is a concrete stale-navigation manifestation. Errors must follow the same ownership rule. These are M09 shell guarantees consumed by M14, not reasons to rewrite mining, classification, dataset export or profile computation. [S02, T05]

## Main-Thread and Query-Concurrency Assessment

**No production off-main AppKit mutation is proven by this audit.** Production `_state_updated` and the long-action helper use `callAfter`; state itself is Python and is intentionally touched by calling/query contexts. That does not excuse unsynchronized publication. Native mutation thread identity must be measured independently at success, refusal and error paths, including coordinator callbacks and close/reopen. [S01, S02, C01]

The test/benchmark inline dispatcher is not production behavior. Separate the pure-state oracle, a dispatch-contract oracle and native AppKit mutation assertions. A queued test helper must drain on main and track all query tails. An intentionally inline negative control should be intercepted before unsafe native mutation, not deliberately crash AppKit to prove a point. [T01, T05, T06, S12]

Every `_spawn` starts another daemon query; superseded workers are not joined as a group. The one-thread wording in the historical contract does not describe current admission behavior. Count actual work/threads under the 100-search probe and measure writer interference; hard SQL cancellation is not required unless necessary. [S01]

## Generation / Selection / Detail Race Assessment

There are two independent defects. First, selecting B does not revoke A’s already-loaded actionable detail/editor. Second, a generation comparison outside the mutation cannot prevent a later stale publication, and exception paths do not consistently compare generations at all. Fixing only the second leaves the first intact. [S01, S02]

The correct invariant is stronger than “the final pane looks right”: at every action boundary, selected ID, rendered detail ID, editor source revision and action ID must agree. At every publication boundary, generation, view/selection and revocation authority must be checked with the state change. Notify observers outside locks. Global versus per-view generations is an implementation choice; it is not a defect merely to intentionally cancel work in another view. [C01; findings 01–03]

## Focus-Steal Guard Assessment

Current `_hub_blocks_show` checks recording, `_injecting` and `InsertionService.busy`. M08 busy covers executing work, not queued admission or a pending clipboard payload. A missing state in that boolean is a **native/policy proof obligation**, not automatic proof of wrong insertion: M08 still validates the target at effects. [S07, S09]

A concrete liveness issue exists independently: deferred show depends on a transaction callback which M08 legitimately does not send for a reconciliation-only no-op, and callback delivery can occur before busy is decremented. Use a distinct true-idle notification or bounded recheck. Do not redefine no-op as insertion or make the Hub busy forever while a clipboard payload waits for a later publication. [C03; finding 11]

## History Query / Search / Grouping Assessment

Parameterized LIKE escaping and the subquery form avoid wildcard injection and a materialized-match parameter cliff. Unknown legacy dates are represented as Undated, and the final merged list is capped once for ordinary positive limits. These are useful retained strengths, not proof of correct chronology. [S03, T02]

The final sort discards within-day time by sorting date plus ID. Default local timezone resolution freezes the current offset rather than historical DST. The service exposes app/mode filters, but the actual History state/action calls only text search. Legacy database row detail is misrouted, and legacy pair identity changes with the matching half. Malformed metadata/future mode handling needs a safe, explicit policy; unsupported timestamp formats must not be silently “repaired” into invented dates. [S01–S03; findings 12–16]

Text lookup checks retained/unpurged role artifacts. A training interest expiring does not necessarily purge a legitimate independent History lease: remediation must enforce actual surface authority and payload lifecycle, not incorrectly erase all history whenever training expires. Deleted/purged payload must not survive in caches or become a stale search hit. [C02, S08; finding 02]

## Lineage Assessment

The four stages remain distinct, and genuine missing artifacts have explicit reasons instead of simple text substitution. But choosing the first artifact per role does not identify the current retry attempt or a coherent parent chain. Do not fix this by independently picking the newest row per role either; resolve an authoritative lineage/manifest. [S03, C06; finding 09]

M11 now retains output and decision artifacts even for fallback/review paths. History must surface the recorded `path`, `reason` and `applied` status rather than treat `transform_output` existence as proof it was inserted. This audit does not judge transform quality. Equal texts can legitimately have distinct stage identities; absent/purged stages cannot borrow prior-stage text. [S10, C14; finding 17]

## Replay / Listening Provenance Assessment

Original float32 audio is read without in-place modification, and replay constructs a PCM16 derivative in memory. Successful sound initiation—not a click alone—opens the current per-example gate. Initiation does **not** prove the entire recording was heard; the present contract is not silently strengthened to require completion. [S05, S02, C01]

Deletion does not currently revoke active/prepared sound buffers, and unavailable replacement requests can return before stopping previous playback. A real/native trial is required for audible behavior and memory/long-audio costs; source alone establishes the missing revocation seam, not an empirical memory leak. [S05, S07; finding 07]

## Retry / Paste Again Assessment

Retry reaches the shared coordinator and M03 authority. Preserve its active claim, state, deletion, strict recovery-audio and unscoped-context rules. The M09 defects are stable selected-item binding and visible handling of returned outcomes. Direct `_retry_job` tests alone do not qualify the button. [S07, T01]

Paste Again carries the V2 job ID, while legacy rows must remain honestly jobless. Current M08 gives each deliberate repaste a new operation identity and reconciles/deletes safely. Do not collapse all repastes by job ID in the name of duplicate prevention. The same captured action should not be delivered twice; two distinct explicit user actions are not automatically the same intent. The local native test must also establish how the real Hub action chooses/returns to its intended external destination—this audit does not certify that experience from a direct coordinator call. [S02, S07, S09, C03]

## Training Data Annotation Assessment

The one-writer-op artifact/lease/revision/state pattern is structurally good. Verbatim and intended-writing are separate objects; partial spans remain partial and do not set whole-example correctness. These strengths need independent failpoint and real-action tests, not replacement with a new annotation model. [S04, T03]

The concrete weaknesses are excluded-state reactivation and unbound reviewed-stage identity. Re-reading latest text and validating length does not prove the user saw it. Carry the immutable reviewed artifact/hash (and an appropriate revision token) into the transaction, while allowing an unrelated newer revision to survive if the exact reviewed stage is unchanged. [S04; findings 05–06]

## Pin / Exclude / Delete Assessment

User pins and annotation-review leases are explicitly separated in both pin directions. Preserve that behavior and the independent interests recognized by M02 retention. [S04, S08, T03]

Exclude→restore can erase quarantine/expiry, and annotation saves can implicitly restore excluded evidence. Delete delegates to M02’s durable barrier/purge authority; the observed M09 failure is cache/replay revocation, not absence of the durable barrier. Job targets remain until metadata pruning, so their post-delete visibility requires an explicit privacy/label policy separate from M13 usage retention. [S04, S08; findings 02, 04–07, 29]

## Diagnostics / Redacted Export Assessment

The most consequential diagnostics defect is the Hub’s obsolete drop-detail-only export, despite M02’s accepted typed allowlist. Reuse the accepted helper rather than maintaining two privacy policies. Event file ordering likewise needs the accepted stream-aware ordering. [S06, S13, C07]

The actual export button reparses retained logs on main; last=500 bounds results but not input work. It queries a new set rather than exporting the displayed snapshot. Level All cannot clear the current filter under the existing sentinel handling, and valid non-object JSON can evade malformed-line handling. Timeline UTC policy must match the control. [S01, S02, S06; findings 18–20]

## Store / Writer-Thread Assessment

Queries use the sanctioned single writer queue, and results are materialized plain data. Annotation writes do not visibly nest Store.submit inside their own writer op. Current deletion admission and rollback machinery are present. Full transactional and nested-submit failpoints remain NOT_RUN. [S03, S04, S08]

A 15-second caller timeout is not cancellation. A UI “not saved” message must not become false certainty when the queued operation can later commit. Synchronous CRUD is explicitly admitted by the current Hub contract, so classify its measured impact and late-commit UX before redesigning it. Background queries can still contend with dictation through the shared writer, which is why the 100-search/stall probes measure both main-thread responsiveness and worker progress separately. [C01, C02; findings 10, 24, 27]

## M14 Hub Race Ownership Assessment

**Adjudication: A — a test-harness-induced off-main race in the inspected M14 helper.** `run_background` replaces `AppHelper.callAfter` globally with direct invocation while Hub query workers can still complete. The M06 record’s `-[NSView _setHidden:]` assertion on `localflow-hub-query` is consistent with that exact path. The M09 benchmark repeats the same unsafe harness idea. [T05, S12, D12]

This does not prove B, a production dispatcher failure, or C, a production M14 caller misusing the real dispatcher. The broader source weaknesses in state mutation and result identity are independently real concerns and must not be confused with an off-main AppKit claim. Fix the test helper, then obtain an independent native thread-identity record across real dispatch success/error paths. Passing the flaky test alone is not an acceptable closure oracle. [S01, S02; finding 25]

## M12 Race Boundary Assessment

The current Scratchpad Hub test uses a main-drained callback queue, not M14’s inline dispatcher. Its note-transform acceptance path polls transform completion, accepts, and inspects a note/revision immediately; the historical intermittent revision-write timing issue does not thereby become an M09 query bug. Instrument note commit and Hub publication as separate barriers before assigning ownership. [T06, C13, D14]

M09’s shared stale selection/publication repair must be compatibility-tested against Scratchpad, but must not opportunistically rewrite autosave, note revision storage or transform acceptance. A separate observed History→Scratchpad adapter spelling inconsistency is a **M12-owned lead**, not an authorized M09 domain repair; verify it locally through its real button and report ownership if encountered. Neither lead is counted as a proven M09 production finding.

## Privacy Assessment

The local Hub may legitimately display retained text and app metadata; that does not permit them into support exports, operational events or committed test evidence. The audit uses only repository source and synthetic planned canaries, not Daniel’s live History, audio or app-use data. [C07, C08, C11]

Highest-risk boundaries: cached content after deletion, prepared/active replay after revocation, dropped exclusion/quarantine restrictions, and Hub redaction policy drift. A metadata-only record requires honest retained-field labeling. A live History lease is not the same as training eligibility. Managed payload deletion is not a promise of forensic erasure or deletion of independently permitted usage aggregates. [C02, C08; findings 02, 04–08, 29]

## Test-Oracle Assessment

Existing suites contain useful positive controls, but many assertions stop at service correctness after all work has settled. They miss actual action reachability, selection→detail intervals, lifecycle composition, stale error publication and current-view benchmark work. [T01–T05]

Specific weak oracles: generation count instead of final authorized state under forced ordering; legacy DB list membership instead of list→detail→action; terminal restore directly rather than terminal→exclude→restore; fresh storage query after deletion instead of old UI cache; canary only in `detail`; one artifact per role; single-file diagnostics; latest-thread join instead of all-work drain. Some standalone suites have explicitly enumerated main runners, so adding a function without registering it can silently omit it. The local inventory must record discovered test functions and actual executed case counts. [T01–T04]

Mutation errors are not kills. A control must pass, the mutation must demonstrably apply, and the intended independent oracle must fail for the intended reason. Empty-work benchmark mutants must fail validity even when elapsed time is excellent.

## Native / Manual Verification Assessment

Automatable locally: real AppKit construction and dispatch identity; deterministic query/action barriers; controlled show/hide and helper-window focus; NSSound initiation/stop with synthetic audio; frame bounds; real coordinator button paths; resource counts. These are not automatable in this read-only GitHub session. [C01, T01, T05]

Proposed manual runbook: M09-V001 full current layout, V002 real keyboard/focus/text scale, V003 replay/recovery experience, V004 actual History Paste Again, V005 move/resize/relaunch, V006 understandable Training provenance, V007 Diagnostics/export experience. Reuse existing stable IDs if already assigned locally and carry `native-m09-hub-trial` forward as an instruction revision. Only Daniel records subjective/manual results. Do not clear earlier milestones’ unrelated manual backlog.

## Performance / Benchmark Assessment

The historical September 22 record reports approximately 42.6 ms warm text-hit p95, 66.7 ms interactive shell p95, 28.2 MB UI memory delta and a 1k inspector cohort. These are accurately identified as **historical**, not current measurements or comparable proof for the expanded Hub. [D09]

The current benchmark still iterates five indexes and omits later services; those indexes now stop before Scratchpad, Insights, Diagnostics, Models and Settings. The inspector/memory populations are not an adequate all-current-view workload. Inline `callAfter`, newest-only waits and insufficient work assertions further invalidate its use as a current gate. [S12; finding 23]

Local qualification must first prove 50,000 real History jobs and known hit/miss work, all ten populated views and required subtabs, nonempty Training list/detail, real Diagnostics window processing, correct completion IDs, bounded rapid-search work and actual rendered settlement. Then record n/p50/p95/p99, view-switch latency, query-thread/queue peaks and a defined memory method on Daniel’s Mac without a competing large sweep. Retain ≤200 ms warm History p95 and ≤1000 ms shell p95 on the proper cohorts; do not invent budgets for previously ungated metrics. [D05, D07]

## Critical Findings

### M09-AUDIT-01 — Selection changes leave old detail/editor authority live

**Severity:** CRITICAL · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** stable selection / wrong-record action

**Canonical requirement:** S19; M09-AC02/05/06; the action must target the exact item visibly selected and reviewed.

**Code location:** state.py: select_history_row, select_training_example and detail loaders; hub.py: History Retry/Replay/Paste, training annotation/pin/exclude/delete, table delegate paths.

**Current behavior:** A selection change immediately replaces selected_id but does not clear the previous detail. History actions resolve job/audio/text from detail; Training actions combine selected_id with the old pane or editor. Several later tables resolve row indexes against worker-replaced state.

**Failure mechanism:** There is an action-authority interval even when generation cancellation works: B is selected, A is still the loaded detail. A delayed refresh can also make an index name a different row from the one rendered.

**Minimal reproduction:**
1. Load A completely with a distinguishable job/example and text.
2. Select B; hold B’s detail query before it returns.
3. Invoke the actual History Retry/Paste or Training intended/span action. Capture the coordinator/service target and rendered identity.
4. For a destructive modal, change the state during the modal and compare the confirmed identity with the committed target.

**Expected behavior:** Clear/disable stale detail actions or require an immutable rendered action context whose selected ID, detail ID and revision all agree; a stale invocation must refuse without a write.

**Likely actual behavior / verification boundary:** History can act on A while B is selected; Training can attach a judgment based on A’s visible text to B. The per-example verbatim gate prevents some, not all, annotation variants.

**Existing coverage:** History Retry button and per-example listen tests act only after wait_for_queries; M14 tests use settled/single-row data.

**Why the oracle misses it:** No oracle observes the selection→detail interval, captures rendered row identity, or checks both selected and acted-on IDs.

**Regression recommendation:** Drive actual buttons with A/B barriers, table reorder before reload, modal reentrancy, and a B-positive control. Assert zero wrong-record calls, not just the final pane text.

**Narrow repair direction:** Introduce one stable rendered selection/action token; clear or disable stale detail and bind input buffers/toggles to the same token. Keep domain operations in existing services/coordinator.

**Downstream impact:** M03 retry, M08 Paste Again, M10/M11 editors and M12/M14 shared selectors consume this authority. Repair shared adapters without re-auditing their domain algorithms.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S02] `localflow/v2/ui/hub.py`, [T01] `tests/v2/ui/test_hub_shell.py`, [T05] `tests/v2/ui/test_training_review_hub.py`, [C01] `docs/v2/contracts/hub.md`, [D05] `docs/v2/LOCALFLOW_V2_MILESTONES.md`.

### M09-AUDIT-02 — Delete-everywhere does not revoke cached Hub plaintext

**Severity:** CRITICAL · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** privacy / deletion monotonicity

**Canonical requirement:** S25/S29.14; M09-AC06; deletion must remove renderable private payload, including cached UI state and late results.

**Code location:** hub.py: _delete_example and Models/History refresh; app.py: _on_job_deleted, _retention_pass; state.py: cached detail/data and publication.

**Current behavior:** The Training delete path clears selected_id but leaves detail and editor content; refresh can render that detail. The app’s deletion listener revokes pipeline/insertion authority but never invalidates Hub state. Retention does not notify the Hub either.

**Failure mechanism:** Storage deletion is not UI invalidation. Cached copies remain reachable independently of purged artifacts, and a read completed before deletion may publish after it.

**Minimal reproduction:**
1. Load synthetic A’s transcript, annotation editor, History preview and detail.
2. Delete A through the real Hub command; inspect immediately and after reload/close/reopen.
3. Separately hold an A detail result after its store read, delete A, then release publication.

**Expected behavior:** Deleted payload disappears from every affected cache/editor and cannot be republished; metadata-only displays may survive only under an explicit policy and honest absence labels.

**Likely actual behavior / verification boundary:** A’s old Training detail/editor can remain visible or be rendered again. A late read has no deletion epoch/token fence at publication.

**Existing coverage:** Deletion tests query the service again and see purged storage; they do not retain an already-open Hub pane.

**Why the oracle misses it:** A fresh storage read cannot detect a stale in-memory copy or a pre-deletion query result.

**Regression recommendation:** Use independent canaries across History, Training, Review and Your Voice caches; assert absence after deletion and after every delayed callback. Include retained-by-an-independent-History-lease expiry control.

**Narrow repair direction:** Subscribe the shared UI state to revocation without calling Store from the writer listener; flag/increment a revocation epoch there, dispatch cache clearing on main, and fence late publications. Do not purge valid independent retention interests.

**Downstream impact:** Preserve M02 durable deletion, M03 listener and M08 operation revocation. M14 invalidated snapshot data must not be resurrected by M09 caches; M15 cannot accept deleted evidence.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S02] `localflow/v2/ui/hub.py`, [S07] `localflow/app.py`, [S08] `localflow/v2/store.py`, [C02] `docs/v2/contracts/store.md`, [C11] `docs/v2/contracts/profile.md`, [T03] `tests/v2/ui/test_training_data.py`.

## High Findings

### M09-AUDIT-03 — Generation checks are not atomic with publication; errors bypass them

**Severity:** HIGH · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** query concurrency / stale publication

**Canonical requirement:** S19 cancellation; newer query/selection must win for data, detail, loading and errors.

**Code location:** state.py: _load_history, _load_history_detail, Models/downstream loaders, _publish_locked, _spawn.

**Current behavior:** Success paths check generation and later mutate shared dictionaries without the same lock; exception paths publish without a generation check. _publish_locked is not itself locked.

**Failure mechanism:** An old worker can pass its check, be paused, let a newer generation publish, and then overwrite it. An old exception can overwrite a new success without even that narrow interval.

**Minimal reproduction:**
1. Hold query A after work finishes but before its publication.
2. Start and finish B; release A.
3. Repeat with A raising after B succeeds, and A succeeding after B errors.
4. Repeat across History→Training and within A→B detail selection.

**Expected behavior:** Validation of generation, view/selection token and publication is indivisible; all success/error/loading/clear operations follow it.

**Likely actual behavior / verification boundary:** Stale data/detail or error can overwrite newer state; a later detail success can also leave an earlier error visible.

**Existing coverage:** The existing search-generation test checks an increment and the search string, not forced out-of-order outcomes.

**Why the oracle misses it:** Sequential waits and a final-state-only assertion never exercise the check→publish gap or stale exceptions.

**Regression recommendation:** Barrier-controlled success/error permutations with an independent expected state log; assert complete state snapshots and callback order.

**Narrow repair direction:** Centralize guarded publication with immutable request snapshots; lock validation+mutation or publish on one owning thread. Notify outside locks. A per-view generation is optional, not mandated solely by taste.

**Downstream impact:** All M10–M14 shared loaders depend on this mechanism. No domain service rewrite is required.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [T01] `tests/v2/ui/test_hub_shell.py`, [C01] `docs/v2/contracts/hub.md`.

### M09-AUDIT-04 — Exclude→restore launders quarantined or expired state

**Severity:** HIGH · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** lifecycle / evidence eligibility

**Canonical requirement:** S29.14 and Training contract: restore must not resurrect terminal/non-reviewable states.

**Code location:** training_data.py: exclude.

**Current behavior:** exclude(True) protects deleted but replaces expired or quarantined_sensitive with excluded. A subsequent exclude(False) sees only excluded and restores a live state.

**Failure mechanism:** The original lifecycle restriction is overwritten rather than preserved as an independent state or refusal.

**Minimal reproduction:**
1. Create a quarantined_sensitive example with a valid revision.
2. Call exclude(True), then exclude(False) through the Hub/service.
3. Repeat with expired; include deleted and ordinary active/excluded controls.

**Expected behavior:** Quarantine/expiry survives both transitions; ordinary user exclusion remains reversible without erasing another restriction.

**Likely actual behavior / verification boundary:** The example becomes annotated or captured_unreviewed, allowing downstream consumers to treat formerly restricted evidence as live.

**Existing coverage:** test_exclude_restore_refuses_terminal_states tests restore directly on a terminal state.

**Why the oracle misses it:** It never inserts exclude(True) before the restore, which is the state-laundering step.

**Regression recommendation:** Transition-table tests over every state and both operations, plus M14 review/profile eligibility checks at the seam.

**Narrow repair direction:** Reject exclusion changes on terminal/non-reviewable states or preserve exclusion as an orthogonal flag with an authoritative original lifecycle. Do not change M14 classifiers.

**Downstream impact:** M02 quarantine, M14 review/profile/export and M15 evidence eligibility.

**Pinned evidence:** [S04] `localflow/v2/training_data.py`, [T03] `tests/v2/ui/test_training_data.py`, [C05] `docs/v2/contracts/training_evidence.md`, [C09] `docs/v2/contracts/learning.md`, [C11] `docs/v2/contracts/profile.md`.

### M09-AUDIT-05 — Verbatim/span annotation silently re-includes excluded evidence

**Severity:** HIGH · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** lifecycle / annotation authority

**Canonical requirement:** S29.14; explicit exclusion is not undone by an annotation; non-reviewable state must be checked inside the write.

**Code location:** training_data.py: set_verbatim, add_span_correction state update; contrast mark_intended.

**Current behavior:** Both annotation paths update state to annotated with NOT IN ('deleted','expired','quarantined_sensitive'), omitting excluded. mark_intended has the stronger state guard.

**Failure mechanism:** An annotation write can change training eligibility even though the user requested a label, not Restore.

**Minimal reproduction:**
1. Exclude a synthetic example with retained stage/audio.
2. Invoke span save, or a verbatim save with a legitimate existing listening token.
3. Inspect example state and downstream eligibility; contrast intended-writing refusal.

**Expected behavior:** Refuse the review on excluded evidence or preserve exclusion explicitly; no implicit re-inclusion.

**Likely actual behavior / verification boundary:** The annotation commits and state becomes annotated.

**Existing coverage:** Happy-path annotation tests and a separate exclusion test do not combine these operations.

**Why the oracle misses it:** They test correctness of the new annotation object but not preservation of the pre-existing lifecycle restriction.

**Regression recommendation:** Cover each annotation API against every non-reviewable state with row/revision/artifact/lease counts and an ordinary active positive control.

**Narrow repair direction:** Apply a shared writer-time reviewability predicate before any artifact/lease/revision creation; retain intended/verbatim distinctions.

**Downstream impact:** M14 review/export/profile gates must not receive evidence reactivated by M09.

**Pinned evidence:** [S04] `localflow/v2/training_data.py`, [T03] `tests/v2/ui/test_training_data.py`, [C09] `docs/v2/contracts/learning.md`, [C12] `docs/v2/contracts/dataset_exports.md`.

### M09-AUDIT-06 — Span offsets are rebound to the latest stage, not the reviewed stage

**Severity:** HIGH · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** provenance / immutable revision binding

**Canonical requirement:** S29.4/S29.6; M09-AC05: code-point offsets name the exact immutable stage/version reviewed.

**Code location:** training_data.py: add_span_correction; hub.py: Training span action.

**Current behavior:** The API accepts example_id, stage, offsets and replacement only. It reads a stage once and re-reads the latest revision in its writer op; no reviewed artifact/revision/hash is supplied.

**Failure mechanism:** Bounds checking against the latest text is not identity checking. A same-length R2 satisfies R1 offsets while naming different words.

**Minimal reproduction:**
1. Display stage R1 containing "alpha beta" and select code-point span [0,5).
2. Advance the example to a different immutable stage R2 containing "gamma beta".
3. Save the original correction without reloading, including an R2 transition between preliminary read and write.

**Expected behavior:** Either bind the annotation explicitly to R1 with a truthful preserved parent, or refuse as stale and require review; never silently reinterpret it as an R2 correction.

**Likely actual behavior / verification boundary:** The correction is parented to R2 and records R2’s original substring despite the user having reviewed R1.

**Existing coverage:** Current tests check range validity, Unicode/partial behavior and parent linkage on a single unchanged stage.

**Why the oracle misses it:** A valid parent at commit time does not prove that it is the parent the user saw.

**Regression recommendation:** Same-length replacement, emoji before span, changed/removed stage and revision-only-change controls; independent expected original substring/hash.

**Narrow repair direction:** Carry reviewed artifact identity and text hash (and an appropriate revision token) through the action; compare inside the one writer op. Avoid rejecting harmless unrelated revisions when the exact stage is unchanged.

**Downstream impact:** M02 immutable envelopes, M14 labels/grafts/exports and M15 training correctness.

**Pinned evidence:** [S04] `localflow/v2/training_data.py`, [S02] `localflow/v2/ui/hub.py`, [C06] `docs/v2/contracts/artifacts.md`, [T03] `tests/v2/ui/test_training_data.py`.

### M09-AUDIT-07 — Replay has no deletion/retention revocation for an active or prepared buffer

**Severity:** HIGH · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** replay / private audio lifecycle

**Canonical requirement:** S08/S29.14: no replay after purge/delete; one playback authority; original float32 must stay untouched.

**Code location:** replay.py: play_artifact/play/stop; hub.py: Training delete; app.py: deletion listener.

**Current behavior:** Audio is resolved/read/converted into memory and NSSound is retained without a job/artifact revocation subscription. Delete does not stop it. A missing new request returns before stopping the old sound.

**Failure mechanism:** A buffer is a private copy outside the Store’s purge path. Availability at resolution does not authorize playback after a later deletion.

**Minimal reproduction:**
1. Start synthetic A replay; delete A through the Hub and observe stop/release.
2. Hold after reading A bytes but before sound creation/play; delete then release.
3. Play A then request missing B; inspect the advertised current replay and actual sound.

**Expected behavior:** Delete revokes prepared/active playback and discards retained buffer references; late starts refuse. Switching to unavailable B must not misleadingly leave A presented as B playback.

**Likely actual behavior / verification boundary:** Active A continues and a prepared A may start after deletion. Missing B can leave A playing. Real NSSound behavior remains a local/native verification item.

**Existing coverage:** Tests prove a successful second play stops the first and that a fresh purged-artifact lookup refuses.

**Why the oracle misses it:** They do not delete after buffer creation or test an unavailable replacement while sound is active.

**Regression recommendation:** Synthetic sound call log plus a separate real NSSound initiation/stop test; deletion barrier on both sides of read/start; no original-WAV hash changes.

**Narrow repair direction:** Track job/artifact plus revocation generation for each replay and prepared buffer; revoke/stop on main as required, clear references, and check authority at start. Do not claim full listening from successful initiation.

**Downstream impact:** M02 audio deletion, M09 listening provenance and M14 ASR-review workflow.

**Pinned evidence:** [S05] `localflow/v2/ui/replay.py`, [S02] `localflow/v2/ui/hub.py`, [S07] `localflow/app.py`, [T03] `tests/v2/ui/test_training_data.py`, [C02] `docs/v2/contracts/store.md`.

### M09-AUDIT-08 — Hub redacted export bypasses the accepted typed allowlist

**Severity:** HIGH · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** privacy / diagnostics export

**Canonical requirement:** Current events contract and accepted M02 remediation: export only versioned, typed, content-free allowed fields.

**Code location:** diagnostics.py: redacted_export; hub.py: diagnosticsExport_; scripts/v2/view_events.py: redact/REDACTION_ALLOWLIST.

**Current behavior:** Hub export copies event fields except detail. The accepted CLI viewer uses typed validation, omission counts and a redaction version.

**Failure mechanism:** Dropping one known sensitive field is not a content boundary. Unknown top-level fields, nested values or wrong-type allowlisted fields survive the Hub path.

**Minimal reproduction:**
1. Write a synthetic event with an ordinary valid envelope plus private_text, nested payload and a secret-like wrong-type field; put a separate canary in detail.
2. Export through the actual Hub action.
3. Compare output against the accepted typed policy, not against a second copy of the Hub implementation.

**Expected behavior:** Only accepted typed fields survive; unknown/private/nested fields are omitted and omission/version metadata is honest.

**Likely actual behavior / verification boundary:** The detail canary is removed but other payload canaries survive.

**Existing coverage:** Diagnostics redaction test places private content only in detail.

**Why the oracle misses it:** Its oracle is the old implementation’s single-field rule, not the post-M02 contract.

**Regression recommendation:** Canaries in every field shape; benign valid control; future/unknown fields; wrong types; nested strings; actual export-button path.

**Narrow repair direction:** Share the accepted M02 pure redaction helper between CLI and Hub (move to a package module if necessary); do not fork a second allowlist or broaden fields.

**Downstream impact:** Preserve M02 policy; prevents private transcript/app metadata leaking through M09 support exports.

**Pinned evidence:** [S06] `localflow/v2/diagnostics.py`, [S13] `scripts/v2/view_events.py`, [C07] `docs/v2/contracts/events.md`, [T04] `tests/v2/ui/test_diagnostics.py`.

### M09-AUDIT-09 — History chooses the earliest artifact per role across repeated stages

**Severity:** HIGH · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** lineage / attempt identity

**Canonical requirement:** M09-AC01 and reconciled M03/M11 identities: stage text must belong to the represented attempt/lineage, not an arbitrary same-role row.

**Code location:** history_queries.py: _job_artifacts and job_detail; training.py stage producers; app.py retained-job retry.

**Current behavior:** Artifacts are traversed in ascending rowid and the first per role is retained. A retry preserves job identity and may append later stage artifacts.

**Failure mechanism:** The job’s current attempt/outcome can be displayed alongside an earlier attempt’s raw/normalized/applied/transform text; independently selecting a first row per role also permits mixed chains.

**Minimal reproduction:**
1. Use a real retained-job retry producer path, or an explicitly documented same-job immutable-stage fixture, to create distinguishable attempt-1 and attempt-2 artifacts.
2. Load History detail and preview after attempt 2.
3. Purge the earlier stage and check whether it shadows the retained authoritative stage.

**Expected behavior:** Resolve the intended attempt/manifest and exact parent-linked stages; unavailable current evidence must be labeled, not silently replaced by an older attempt.

**Likely actual behavior / verification boundary:** Earlier role artifacts win even when later authoritative artifacts exist; current status and text can disagree.

**Existing coverage:** Current lineage tests create one artifact per role.

**Why the oracle misses it:** They cannot distinguish first-row convenience from authoritative lineage selection.

**Regression recommendation:** Two-attempt and multiple-artifact fixtures with exact identity/parent assertions; real retry integration to confirm reachable producer shape.

**Narrow repair direction:** Use explicit current attempt/stage references or an authoritative manifest. Do not merely switch ASC to DESC independently for each role; that can still mix chains.

**Downstream impact:** M03 retry, M07 applied text, M08 Paste Again and reconciled M11 transformed stage; preserve historical evidence rather than rewriting it.

**Pinned evidence:** [S03] `localflow/v2/history_queries.py`, [S07] `localflow/app.py`, [S10] `localflow/v2/training.py`, [T02] `tests/v2/ui/test_history_queries.py`, [C06] `docs/v2/contracts/artifacts.md`.

## Medium Findings

### M09-AUDIT-10 — Rapid queries create unbounded daemon workers and wait only for the newest

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** query resource discipline

**Canonical requirement:** Hub contract’s query discipline, responsive dictation and bounded companion-UI work.

**Code location:** state.py: _spawn, _query_thread, wait_for_queries; Store’s shared FIFO writer.

**Current behavior:** Each request starts another daemon thread; only the latest thread is stored/joined. Superseded work may still be queued/executing on the single writer.

**Failure mechanism:** Generation cancellation suppresses publication, not work. A slow writer plus rapid input accumulates threads and pending reads; waiting for the latest thread is not a drain oracle.

**Minimal reproduction:**
1. Hold the writer/query service at a barrier.
2. Issue 100 distinct search changes through the same public state surface.
3. Measure admitted/running threads and queued work; release and drain every admitted request.

**Expected behavior:** Bound/coalesce superseded work and provide truthful drain/shutdown accounting; normal search still performs real work.

**Likely actual behavior / verification boundary:** Up to one new daemon per request is admitted. Exact peak count, queue delay and dictation impact require measurement.

**Existing coverage:** The generation test and benchmark wait on only the newest query.

**Why the oracle misses it:** Neither measures outstanding old work or shared-writer contention.

**Regression recommendation:** 100-search barrier probe with peak counts and a concurrent dictation-store heartbeat; assertions based on an explicit chosen bound, not a fragile sleep.

**Narrow repair direction:** Use a bounded query executor/latest-request coalescing and track all admitted work. Do not require hard SQLite cancellation unless measured need establishes it.

**Downstream impact:** M03/M08 shared writer latency and all M10–M14 query consumers; no worker-engine change.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S08] `localflow/v2/store.py`, [S12] `scripts/v2/benchmark_m09.py`, [T01] `tests/v2/ui/test_hub_shell.py`.

### M09-AUDIT-11 — Deferred Hub show can lose its only completion wake-up

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** focus / deferred intent liveness

**Canonical requirement:** M09 deferred Open Hub must eventually execute exactly once after the unsafe interval ends.

**Code location:** app.py: _flush_pending_hub_show and hubPasteText._repaste_done; insertion/service.py: _run completion/finally ordering.

**Current behavior:** M09 flushes deferred show from the repaste transaction callback. M08 correctly does not invoke that callback for a reconciliation-only no-op; callback invocation also precedes busy decrement.

**Failure mechanism:** An Open Hub deferred during a no-op reconciliation receives no wake-up. A main-thread flush that runs before busy clears can return with the pending flag still set and no later retry.

**Minimal reproduction:**
1. Hold a repaste while busy; request Open Hub twice.
2. Make reconciliation return already-present/no transaction, then release.
3. Separately force the main callback to run before worker finally decrements busy.

**Expected behavior:** One pending intent is delivered after actual quiescence, including no-op, refusal and exception paths, unless quitting/cancelled.

**Likely actual behavior / verification boundary:** The intent can remain pending until an unrelated event happens to flush it.

**Existing coverage:** Busy tests check refusal/deferral; successful transaction paths exercise the callback but not reconciliation-only completion.

**Why the oracle misses it:** They assume transaction completion and service-idle notification are equivalent.

**Regression recommendation:** Deterministic queued/busy/no-op/error/success schedules and exactly-once show log, plus quit-cancellation control.

**Narrow repair direction:** Add/use a distinct service-idle/operation-settled notification after state transition, or a bounded coordinator recheck. Do not change M08’s accepted transaction-callback meaning or count a no-op as an insertion.

**Downstream impact:** M08 repaste semantics and M12 deferred quick-open intent share the seam.

**Pinned evidence:** [S07] `localflow/app.py`, [S09] `localflow/v2/insertion/service.py`, [C03] `docs/v2/contracts/insertion.md`, [T01] `tests/v2/ui/test_hub_shell.py`.

### M09-AUDIT-12 — Merged History is ordered by day and ID, not actual capture instant

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** History ordering / global limit

**Canonical requirement:** S19 newest-first History with deterministic ties and an exact merged limit.

**Code location:** history_queries.py: _search_op final dated_rows.sort.

**Current behavior:** Per-source SQL sorts by instant, but the final merged sort uses (date, str(id)) in reverse order.

**Failure mechanism:** All captures on one local day lose their time ordering. The final limit can retain older same-day rows and discard newer ones.

**Minimal reproduction:**
1. Seed two same-day jobs whose ID lexical order is opposite their capture times and one dated legacy row between them.
2. Search with a small merged limit, then repeat with equal timestamps.

**Expected behavior:** Sort by parsed capture instant across sources, with a documented stable source-qualified tie-break; Undated remains last.

**Likely actual behavior / verification boundary:** Within-day order follows IDs rather than time.

**Existing coverage:** Grouping tests use different days; limit test checks cardinality, not membership across sources.

**Why the oracle misses it:** Correct group labels and row count do not prove newest-first selection.

**Regression recommendation:** Exact ordered-ID assertions for mixed sources, same-day captures, ties and limits 0/1/N with documented zero semantics.

**Narrow repair direction:** Retain a sortable canonical instant and stable source-qualified identity through the merge; apply the final limit once.

**Downstream impact:** M09 navigation/actions; no M13 analytics arithmetic change.

**Pinned evidence:** [S03] `localflow/v2/history_queries.py`, [T02] `tests/v2/ui/test_history_queries.py`, [D06] `docs/v2/LOCALFLOW_V2_SPEC.md`.

### M09-AUDIT-13 — Default History timezone freezes the current offset

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** History date provenance / DST

**Canonical requirement:** S08/S21 local-date grouping must honor the actual zone at each historical instant; unknown time stays Undated.

**Code location:** history_queries.py: __init__, _local_date and local-day Home boundaries.

**Current behavior:** The default zone comes from datetime.now().astimezone().tzinfo, which supplies a fixed current offset in this usage; parsing accepts only the canonical fractional-Z form.

**Failure mechanism:** A historical instant in the other daylight-saving season is converted with today’s offset, potentially moving it across midnight. Offset-form valid timestamps also become Undated under the strict parser.

**Minimal reproduction:**
1. Run/default-resolve an Eastern summer offset, then group 2026-01-15T04:30:00.000Z; compare with America/New_York.
2. Repeat with winter default and a summer boundary; include malformed, absent, canonical UTC and explicit-offset timestamps.

**Expected behavior:** Use the intended real local/IANA zone with its historical transitions. Preserve unknown dates; decide supported noncanonical valid timestamp forms explicitly.

**Likely actual behavior / verification boundary:** The winter example may be grouped January 15 instead of January 14. Noncanonical-format support needs contract adjudication; it is not permission to invent dates.

**Existing coverage:** Tests inject UTC or fixed timezones and do not exercise the production default across seasons.

**Why the oracle misses it:** A fixed-zone fixture masks the default-zone defect.

**Regression recommendation:** ZoneInfo-based independent expected dates, both seasons, DST repeated hour and near-midnight cases; distinguish malformed from valid-but-unsupported forms.

**Narrow repair direction:** Resolve a real local timezone or reuse an appropriate existing zone resolver without silently imposing the analytics reporting zone on History.

**Downstream impact:** M09 History/Home; preserve M13’s separate reporting-zone policy.

**Pinned evidence:** [S03] `localflow/v2/history_queries.py`, [T02] `tests/v2/ui/test_history_queries.py`, [D06] `docs/v2/LOCALFLOW_V2_SPEC.md`, [S11] `localflow/config.py`.

### M09-AUDIT-14 — Imported legacy database rows have no matching detail route

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** History source identity / action reachability

**Canonical requirement:** S19 supports V2 jobs, dated legacy analytics and undated legacy pairs with honest source-specific capabilities.

**Code location:** state.py: _load_history_detail; history_queries.py: legacy_db list rows and legacy_detail.

**Current behavior:** legacy_db rows use legacy-db:<id>, but every non-job detail request is sent to the artifact-based legacy_detail reader.

**Failure mechanism:** The source-qualified row identity is not dispatched to its source. A legacy database key is not an artifact ID.

**Minimal reproduction:**
1. Import a synthetic legacy_dictations row.
2. Select its visible History row and invoke detail, Copy and jobless Paste Again through the real Hub.

**Expected behavior:** Read the matching legacy database row; show retained raw/cleaned text, no fabricated audio/job ID, and enable only supported actions.

**Likely actual behavior / verification boundary:** Detail is missing/unavailable despite a real searchable legacy record; text actions cannot use the retained row correctly.

**Existing coverage:** The legacy database test asserts list inclusion; the legacy detail test covers log-pair artifacts.

**Why the oracle misses it:** No test joins the database list row to its actual detail/action path.

**Regression recommendation:** Source-by-source list→select→detail→Copy/Paste tests with exact IDs and absence reasons.

**Narrow repair direction:** Dispatch by explicit source kind and add a typed database detail adapter; keep legacy rows jobless.

**Downstream impact:** M08 attribution must remain intentionally absent for jobless legacy rows; M12 History copy may benefit from the same corrected detail.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S03] `localflow/v2/history_queries.py`, [T02] `tests/v2/ui/test_history_queries.py`, [T01] `tests/v2/ui/test_hub_shell.py`.

### M09-AUDIT-15 — Legacy-pair search changes row identity and loses the unmatched half

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** History search / stable identity

**Canonical requirement:** Search must not change the identity of one imported utterance or flatten its paired stages.

**Code location:** history_queries.py: legacy_log SQL/pair assembly and legacy_detail.

**Current behavior:** Text filtering happens before raw/cleaned halves are paired; the row ID prefers whichever cleaned half survived, otherwise the raw artifact.

**Failure mechanism:** A raw-only match and a cleaned-only match produce different IDs for the same pair. Raw-ID detail does not recover the cleaned child in the same way as cleaned-ID detail.

**Minimal reproduction:**
1. Create a pair with raw-only canary R and cleaned-only canary C.
2. Search R, then C, then no text; compare logical identity and both detail stages.

**Expected behavior:** One stable pair key regardless of the matching stage; select the matching pair first, then hydrate retained halves.

**Likely actual behavior / verification boundary:** The pair changes selection identity and can lose cleaned detail under raw-only search.

**Existing coverage:** Tests inspect an unfiltered pair or its cleaned-ID detail.

**Why the oracle misses it:** No metamorphic relation asserts identity invariance under a change of matching half.

**Regression recommendation:** Raw-only/cleaned-only/both/no-match fixtures, purged-half controls, and preserved selection across query edits.

**Narrow repair direction:** Use the immutable pair/root identity and source-aware hydration after matching; never synthesize the missing half.

**Downstream impact:** M01/M02 lossless legacy import identity stays intact; M09 alone needs a correct query adapter.

**Pinned evidence:** [S03] `localflow/v2/history_queries.py`, [T02] `tests/v2/ui/test_history_queries.py`, [C06] `docs/v2/contracts/artifacts.md`.

### M09-AUDIT-16 — History app/mode filters are implemented in the service but unreachable in the Hub

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** History functionality / UI integration

**Canonical requirement:** S19 and M09 task/acceptance description explicitly require History text, app and mode filtering.

**Code location:** hub.py: _build_history_view/history search action; state.py: _load_history; HistoryQueryService.search.

**Current behavior:** The view exposes text search only and _load_history passes text alone. The backend supports app and mode.

**Failure mechanism:** Backend-only tests certify a capability the actual History surface cannot invoke.

**Minimal reproduction:**
1. Construct the current History pane and inventory actual filter controls/actions.
2. Attempt app-name/bundle and supported mode filters without calling the query service directly.

**Expected behavior:** Reachable, labeled controls pass stable filter state to background queries and can clear each filter.

**Likely actual behavior / verification boundary:** No actual History app/mode control path exists.

**Existing coverage:** History query tests call search(app=..., mode=...) directly.

**Why the oracle misses it:** Service functionality is mistaken for product reachability.

**Regression recommendation:** Native/state adapter tests drive each real control and inspect rendered result IDs; unknown/missing targets remain honest.

**Narrow repair direction:** Add the missing controls and request fields using the existing service API; do not replace History with the separate Insights cohort filters.

**Downstream impact:** M09 only; private app metadata remains local and must not enter exported diagnostics.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S02] `localflow/v2/ui/hub.py`, [S03] `localflow/v2/history_queries.py`, [T02] `tests/v2/ui/test_history_queries.py`, [D05] `docs/v2/LOCALFLOW_V2_MILESTONES.md`.

### M09-AUDIT-17 — Transform artifacts are displayed without their applied/fallback decision

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** lineage / reconciled M11 compatibility

**Canonical requirement:** M09-AC01; reconciled M11: fallback_original/needs_review must not be represented as an applied transform.

**Code location:** history_queries.py: transformed lineage slot; training.py: on_transform_result; hub.py: stage renderer.

**Current behavior:** The collector retains transform_output even when not applied and separately records path, reason, applied and decision artifact. History selects the role without carrying that distinction into its displayed stage.

**Failure mechanism:** Artifact existence is treated as sufficient evidence of a transformed result; a retained fallback/proposal is not necessarily what was inserted.

**Minimal reproduction:**
1. Create real collector results for applied, fallback_original and needs_review with distinct Clean/proposal text.
2. Render current History lineage and final-text actions; compare against the recorded decision and actual inserted text.

**Expected behavior:** Expose true output/proposal and decision honestly; mark unapplied/fallback absence or status explicitly; final actions must use the authorized final text.

**Likely actual behavior / verification boundary:** Fallback/proposal output can appear under an undifferentiated transformed heading.

**Existing coverage:** Original M09 tests expected the transform stage not yet implemented; the modern test fixtures do not cover all M11 result paths.

**Why the oracle misses it:** A four-slot array does not prove truthful stage status.

**Regression recommendation:** Applied/fallback/review/not-requested/purged-decision controls with exact artifact, path and applied assertions.

**Narrow repair direction:** Consume the existing reconciled M11 manifest/decision identities; do not modify transform semantics or model quality.

**Downstream impact:** M11 compatibility and M15 training provenance; independent of the earlier-artifact selection defect in finding 09.

**Pinned evidence:** [S03] `localflow/v2/history_queries.py`, [S10] `localflow/v2/training.py`, [S02] `localflow/v2/ui/hub.py`, [C14] `docs/v2/contracts/transforms.md`, [T02] `tests/v2/ui/test_history_queries.py`.

### M09-AUDIT-18 — Diagnostics uses obsolete filename/global-sequence ordering

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** diagnostics chronology / bounded window

**Canonical requirement:** Accepted M02 events contract: per-stream sequence, cross-stream UTC merge, filter and last-N after ordering.

**Code location:** diagnostics.py: load_events and job_timeline; scripts/v2/view_events.py: order_records.

**Current behavior:** Hub diagnostics walks filename order and uses a global sequence sort for timelines rather than the accepted stream-aware algorithm.

**Failure mechanism:** Rotation, multiple writer streams and restarted sequence numbers can change the displayed last-N set or chronology.

**Minimal reproduction:**
1. Create two synthetic streams with reset/overlapping seq values and UTC interleaving; rotate filenames into the opposite order.
2. Load last N and a job timeline, then rename rotation files without changing event contents.

**Expected behavior:** Same records and chronology under filename changes; per-stream causal sequence remains authoritative.

**Likely actual behavior / verification boundary:** The retained display window/timeline can change with filenames or conflate independent sequence domains.

**Existing coverage:** Diagnostics tests use a simple single-file/single-stream sequence.

**Why the oracle misses it:** That fixture makes obsolete and accepted ordering coincide.

**Regression recommendation:** Compare against independently specified expected event IDs and accepted CLI policy, including clock rollback and filter-before-last semantics.

**Narrow repair direction:** Reuse the accepted pure event ordering helper; keep the legacy historical record unchanged.

**Downstream impact:** M02 support diagnostics and M09 user-visible timeline/export selection.

**Pinned evidence:** [S06] `localflow/v2/diagnostics.py`, [S13] `scripts/v2/view_events.py`, [C07] `docs/v2/contracts/events.md`, [T04] `tests/v2/ui/test_diagnostics.py`.

### M09-AUDIT-19 — Diagnostics filter/reset and malformed-record paths are incomplete

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** diagnostics reliability / error state

**Canonical requirement:** S19: filters/UTC controls work; malformed logs degrade safely without private payload warnings.

**Code location:** state.py: set_diagnostics_filter/_load_diagnostics; diagnostics.py: event parsing; hub.py: filter controls.

**Current behavior:** None means “do not update” for level_filter, so choosing All cannot clear an existing level. Valid JSON scalars/lists are not rejected before dict access. Timeline formatting does not consistently honor the UTC selection.

**Failure mechanism:** Control sentinel and actual cleared value are conflated; syntax-valid non-event JSON escapes the parser’s JSONDecodeError handler.

**Minimal reproduction:**
1. Choose ERROR then All and compare the visible IDs.
2. Place null, a number, a list and malformed JSON between valid events.
3. Toggle UTC while a job timeline is selected.

**Expected behavior:** All clears the filter, bad shapes produce a content-free warning/skip without losing valid events, and time display follows the selected policy.

**Likely actual behavior / verification boundary:** The level remains filtered; a non-object record can raise; timeline/display UTC can disagree.

**Existing coverage:** Tests cover direct filtered queries and malformed JSON syntax, not UI clear or valid non-object JSON.

**Why the oracle misses it:** They do not exercise the actual control sentinel or schema-shape boundary.

**Regression recommendation:** Real popup/reset tests, malformed-object corpus and known UTC/local timeline values; no private string in warning output.

**Narrow repair direction:** Use an explicit unchanged sentinel, validate record shape, and pass one display-time policy through the timeline.

**Downstream impact:** M09 diagnostics only; preserve M02 event schema and writer behavior.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S02] `localflow/v2/ui/hub.py`, [S06] `localflow/v2/diagnostics.py`, [T04] `tests/v2/ui/test_diagnostics.py`.

### M09-AUDIT-20 — Redacted Export re-reads full logs on the AppKit thread and is not the displayed snapshot

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** diagnostics UI responsiveness / export TOCTOU

**Canonical requirement:** Current Hub contract: background queries; export bounded to the displayed filtered window and labeled honestly.

**Code location:** hub.py: diagnosticsExport_; diagnostics.py: load_events.

**Current behavior:** The button calls load_events synchronously before the save panel/exception wrapper. last=500 limits the result, not full-file parsing. It re-queries rather than exporting the already-displayed event set.

**Failure mechanism:** A large log causes main-thread work; appends or pending filter changes between display and click change the exported set.

**Minimal reproduction:**
1. Display S1, hold/append events or change a filter without completing its reload.
2. Click the real export button while recording thread identities and an AppKit heartbeat.
3. Compare exported event identities/filter metadata against S1; inject a parse/read failure.

**Expected behavior:** No full-log parse on main. Export the frozen displayed set as contracted, or explicitly label a newly queried snapshot with its actual filters/time after an approved contract change.

**Likely actual behavior / verification boundary:** The main callback parses retained logs; output may be S2 while the user was shown S1, and an early read error may escape the pane’s error handling.

**Existing coverage:** Historical repair bounded output count; tests call the export function directly.

**Why the oracle misses it:** A bounded returned list does not prove bounded input work or main-thread safety, and direct function tests omit the button’s re-query.

**Regression recommendation:** Actual action with append/filter barriers, input-work counter, heartbeat and safe error oracle; zero-record positive control must still be honest.

**Narrow repair direction:** Capture the immutable displayed event snapshot/token on main, redact/write off-main, return a generation-bound safe status; keep native save-panel interaction on main.

**Downstream impact:** M02 export policy and M09 responsiveness; no M14 dataset-export algorithm audit.

**Pinned evidence:** [S02] `localflow/v2/ui/hub.py`, [S06] `localflow/v2/diagnostics.py`, [D09] `docs/v2/acceptance/M09/results.json`, [T04] `tests/v2/ui/test_diagnostics.py`.

### M09-AUDIT-21 — Long-action completions are not bound to the initiating view/action generation

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** downstream shared shell / stale completion

**Canonical requirement:** M09 shared-shell guarantee: async results/errors belong to stable action/item identity and may not override newer navigation.

**Code location:** hub.py: _in_background and Mine Candidates, Export, Your Voice completion adapters.

**Current behavior:** Callbacks correctly hop through callAfter, but they lack action-generation/selection/lifecycle checks. Mine completion unconditionally selects the Review tab.

**Failure mechanism:** Correct thread affinity does not prevent A’s result changing B’s current view or an older action overwriting newer action status.

**Minimal reproduction:**
1. Start Mine in Review; switch to Export or another view before completion; release success/error.
2. Run two same-type actions and complete the older last.
3. Close/reopen while an action finishes.

**Expected behavior:** Result recorded against its initiating token; no forced tab switch or incorrect status on a newer selection/action; safe persisted notification if appropriate.

**Likely actual behavior / verification boundary:** Mine can force Review selection after the user moved away; status fields can represent an older request as current.

**Existing coverage:** M14 tests wait for background work before changing navigation.

**Why the oracle misses it:** They prove task completion but not result ownership.

**Regression recommendation:** Event-controlled out-of-order completions for success/refusal/error across all long-action adapters; actual main-thread identity recorded separately.

**Narrow repair direction:** Add action IDs/generations and target identity at the shared completion adapter; do not change mining/profile/export internals.

**Downstream impact:** M14 callers with an M09 shell ownership fix; M12 completion issues only if the same root is demonstrated.

**Pinned evidence:** [S02] `localflow/v2/ui/hub.py`, [T05] `tests/v2/ui/test_training_review_hub.py`, [C01] `docs/v2/contracts/hub.md`, [C11] `docs/v2/contracts/profile.md`, [C12] `docs/v2/contracts/dataset_exports.md`.

### M09-AUDIT-22 — Refusals, loading and some query/action failures are not truthfully surfaced

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** UI state / error handling

**Canonical requirement:** S19 distinct loading/empty/error states; M09-AC02 action refusals and current Hub error-surfacing contract.

**Code location:** state.py: loading lifecycle and detail error handling; hub.py: History Retry/Paste handlers, Models refresh and some Settings actions.

**Current behavior:** Views initialize loading=False without consistently setting it on dispatch. Retry/Paste discard structured coordinator outcomes. Models rendering can retain old data without showing view.error; several synchronous coordinator errors lack a pane-level handler.

**Failure mechanism:** A refused action appears inert, a failing query looks like stale success, and a real load is not distinguishable from no data.

**Minimal reproduction:**
1. Invoke Retry on a non-retryable/missing-audio job and Paste while recording/busy.
2. Inject Models query failure with previous data present.
3. Hold an initial query and observe loading; make a Settings coordinator call fail.

**Expected behavior:** Safe, item-bound messages for refusal/failure; loading reflects admitted work; retained stale data is clearly labeled or cleared.

**Likely actual behavior / verification boundary:** No useful user-visible result on several paths; old content can remain presented as current.

**Existing coverage:** Tests assert coordinator return dictionaries directly or eventual service data, not actual rendered action/error text.

**Why the oracle misses it:** A correct service outcome does not certify that the user sees it.

**Regression recommendation:** Button-level outcome-to-pane assertions with private exception canaries and stale-error schedules; verify operational logs remain content-free.

**Narrow repair direction:** Normalize action/result handling and query states at the shared shell; retain safe local details only under contract and never log raw exceptions containing payload.

**Downstream impact:** M09 and M10–M14 shared adapters; preserve M03/M08 structured outcomes.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S02] `localflow/v2/ui/hub.py`, [S07] `localflow/app.py`, [T01] `tests/v2/ui/test_hub_shell.py`, [T05] `tests/v2/ui/test_training_review_hub.py`.

### M09-AUDIT-23 — M09 benchmark can qualify an incomplete current Hub and invalid dispatch harness

**Severity:** MEDIUM · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** benchmark validity / false green

**Canonical requirement:** M09 ≤200 ms warm 50k search, ≤1000 ms shell, current inspector/memory; non-no-op work validity must precede timing.

**Code location:** scripts/v2/benchmark_m09.py: bench_search, bench_shell, bench_training_inspector, bench_memory, main.

**Current behavior:** Shell/memory iterate range(5) although VIEWS has ten entries; later services are omitted. AppHelper.callAfter is replaced inline. Search/inspector timing lacks robust per-run work/population assertions; newest-thread-only waits do not drain all work.

**Failure mechanism:** Fast unavailable/omitted views or empty query work may pass timing. Inline dispatch can mutate AppKit on a query thread; historical five-view figures are not current-Hub certification.

**Minimal reproduction:**
1. Inventory constructed and populated views/tabs/services for each timed iteration.
2. Replace search with an empty result, remove examples, skip a current view, or suppress publication.
3. Check that validity fails before timing is judged.

**Expected behavior:** All required current views/subtabs and real service work are asserted; genuine main-thread dispatch; explicit dataset/result populations and safe drain; current Mac statistics.

**Likely actual behavior / verification boundary:** Several no-op/partial-work mutants can remain timing-green; no current measurements were obtained in this audit.

**Existing coverage:** Historical benchmark has a budget exit code, but no adequate work-validity mutation suite.

**Why the oracle misses it:** It treats elapsed time as evidence of completed required work.

**Regression recommendation:** Benchmark mutants for empty hit query, missing view/service, zero examples, stale drop, inline dispatch and wrong timed boundary; control must execute real work.

**Narrow repair direction:** Repair benchmark harness first, use a real/pumped main run loop, populate all ten views and current subtabs, assert results/work each run, then measure in isolation.

**Downstream impact:** Current M10–M14 shell population and M15 readiness evidence; historical September 22 record stays unchanged.

**Pinned evidence:** [S12] `scripts/v2/benchmark_m09.py`, [S01] `localflow/v2/ui/state.py`, [T01] `tests/v2/ui/test_hub_shell.py`, [D09] `docs/v2/acceptance/M09/results.json`, [D05] `docs/v2/LOCALFLOW_V2_MILESTONES.md`.

## Low Findings

No separate Low finding is asserted. Documentation drift is described where it affects a concrete gate or policy.

## Test Gaps

### M09-AUDIT-24 — Atomic annotation and timeout behavior lack independent failure evidence

**Severity:** TEST GAP · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** writer transaction / late commit proof

**Canonical requirement:** S29.6 annotation artifact+lease+revision+state atomic; single writer, no nested submit; timeout is not cancellation.

**Code location:** training_data.py writer helpers and annotation APIs; store.py _submit/commit/rollback.

**Current behavior:** The write grouping is structurally sound and direct, but tests do not inject failure after each logical stage. A 15-second caller timeout may leave its queued mutation alive.

**Failure mechanism:** A happy-path transaction cannot prove rollback/lease cleanup or truthful late-commit UI behavior; an indiscriminate async rewrite can introduce nested submit deadlocks.

**Minimal reproduction:**
1. Inject after artifact, lease, revision and state update, then inspect all four tables and pointers.
2. Delay the writer past the caller timeout, allow the operation to commit, and observe retry/status behavior.

**Expected behavior:** No half-annotation or orphan lease; no nested submit; late/unknown outcome reconciled by stable operation identity rather than reported as definitely not saved.

**Likely actual behavior / verification boundary:** Runtime/failpoint verification required; no deterministic rollback defect is asserted from the current grouping alone.

**Existing coverage:** Happy-path partial/verbatim/pin tests.

**Why the oracle misses it:** No independent before/after transaction snapshot or late-commit schedule.

**Regression recommendation:** Failpoint matrix, writer-thread submit assertion, immutable snapshot comparisons and retry-after-timeout idempotence adjudication.

**Narrow repair direction:** Add proof first; repair only reproduced behavior. Do not dismantle the existing one-writer-op design.

**Downstream impact:** M02 writer authority and M14 callers importing the shared helpers.

**Pinned evidence:** [S04] `localflow/v2/training_data.py`, [S08] `localflow/v2/store.py`, [T03] `tests/v2/ui/test_training_data.py`, [C02] `docs/v2/contracts/store.md`.

### M09-AUDIT-25 — Production main-thread safety lacks an independent native oracle; M14 shim is invalid

**Severity:** TEST GAP · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** thread identity / test ownership

**Canonical requirement:** No production AppKit mutation off main; a fake inline dispatcher cannot certify or refute production affinity.

**Code location:** hub.py: _state_updated/_in_background; test_training_review_hub.py: run_background; benchmark_m09.py inline replacement.

**Current behavior:** Production callbacks use AppHelper.callAfter. M14 run_background replaces it globally with direct invocation while query threads can still complete; the recorded M06 abort is consistent with that shim.

**Failure mechanism:** The test removes the main-thread hop and then exercises native views; the assertion is a harness-induced off-main mutation. It is not evidence that real callAfter violates its contract.

**Minimal reproduction:**
1. Use a main-drained queue/pumped run loop and record thread IDs for _refresh, setHidden and action error/success callbacks.
2. Keep an intentionally inline negative control isolated; do not run unsafe AppKit off-main in the ordinary suite.

**Expected behavior:** Native UI mutations always execute on main with the real dispatch path; the negative control is rejected before unsafe native mutation.

**Likely actual behavior / verification boundary:** M14 test-shim defect is source-supported; production off-main defect is not established. Native verification required.

**Existing coverage:** Historical isolated passes and intermittent abort; no authoritative thread-ID oracle across all adapters.

**Why the oracle misses it:** Passing alone is timing luck when an inline dispatcher and unjoined query tails coexist.

**Regression recommendation:** Separate pure-state tests, dispatcher-contract tests and native UI thread-identity tests; include exceptions, close/reopen and later-view actions.

**Narrow repair direction:** Repair M14’s test helper and M09 benchmark harness; add a shared safe test dispatcher. Only patch production if the real-path oracle proves a vulnerability.

**Downstream impact:** Ownership A: M14 test shim; M09 benchmark has the analogous harness bug. M09 production contract remains an independent proof obligation, not an automatic Critical.

**Pinned evidence:** [S02] `localflow/v2/ui/hub.py`, [T05] `tests/v2/ui/test_training_review_hub.py`, [S12] `scripts/v2/benchmark_m09.py`, [D12] `docs/v2/handoffs/M06.md`, [T06] `tests/v2/notes/test_scratchpad_hub.py`.

### M09-AUDIT-26 — Current native focus/lifecycle and full caller/resource coverage remain unqualified

**Severity:** TEST GAP · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** native boundary / query lifecycle / focus admission

**Canonical requirement:** M09-AC03/04 and current M08 compatibility: exact-one Hub, safe focus, close/reopen, lifecycle and dictation isolation.

**Code location:** HubController lifecycle, app.py focus/coordinator calls, state.py wait_for_queries, later view callbacks; complete local caller inventory.

**Current behavior:** Source supports one persistent controller and hide-on-close. busy covers executing insertion, not queued admission or pending clipboard lifetime. Connector code search returned incomplete results, so it cannot establish exhaustive callers.

**Failure mechanism:** A source-level guard/daemon declaration does not prove native focus, shutdown, window restoration or bounded contention. Queue admission can precede busy without proving an unsafe external effect by itself.

**Minimal reproduction:**
1. Use real native helper windows to probe queued-before-busy, executing, no-op and pending-payload states.
2. Close/reopen with all query/action tails tracked, then quit with callbacks queued.
3. Run local rg across every public M09 surface and actual AppKit mutation path; measure dictation under slow queries.

**Expected behavior:** No unsafe activation/effect or callback into invalid UI; exactly one controller; complete local caller inventory and bounded resources with truthful native/manual split.

**Likely actual behavior / verification boundary:** Runtime/native/manual verification required. Do not infer wrong insertion solely because busy is false for a queued or clipboard-only state.

**Existing coverage:** Basic close/reopen, single-instance and busy tests; no current all-view full-lifecycle oracle.

**Why the oracle misses it:** App single-instance is not window singleton proof, newest-thread join is not a drain, state keyboard tests are not actual keyboard usability.

**Regression recommendation:** Current ten-view/subtab thread and lifecycle registry, native helper trials, 100-search counts, memory and isolated benchmarks; retain subjective checks for Daniel.

**Narrow repair direction:** Close proof gaps first; add bounded lifecycle hooks only where reproduced. Do not broadly refactor M12/M14 services.

**Downstream impact:** M03 shutdown/dictation, M08 focus/repaste, M10–M14 shell and M15 gate.

**Pinned evidence:** [S01] `localflow/v2/ui/state.py`, [S02] `localflow/v2/ui/hub.py`, [S07] `localflow/app.py`, [S09] `localflow/v2/insertion/service.py`, [T01] `tests/v2/ui/test_hub_shell.py`, [T05] `tests/v2/ui/test_training_review_hub.py`.

## Design Concerns

### M09-AUDIT-27 — Synchronous CRUD waits are documented, but timeout UX needs explicit policy

**Severity:** DESIGN CONCERN · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** UI responsiveness / accepted limitation

**Canonical requirement:** Current hub.md explicitly permits synchronous CRUD/annotation waits up to Store’s 15-second timeout.

**Code location:** Hub annotation/pin/exclude/Settings and later adapter mutations; Store.submit.

**Current behavior:** Several main-thread actions wait synchronously on the single writer. This is admitted by the current contract.

**Failure mechanism:** A slow writer may freeze the Hub; main-thread hotkey handling may also wait even if the worker thread remains independent. A timed-out operation can still commit later.

**Minimal reproduction:**
1. Inject a slow writer and separately observe AppKit heartbeat, hotkey acknowledgment, active worker completion and mutation commit.

**Expected behavior:** Adjudicated, measured UX policy and truthful pending/unknown outcome. Do not automatically call an admitted limitation a Critical defect.

**Likely actual behavior / verification boundary:** Runtime measurements required; source establishes the possibility of blocking, not its typical duration or full dictation impact.

**Existing coverage:** Historical personal-scale timings, no explicit slow-writer UI/worker dual oracle.

**Why the oracle misses it:** A fast synthetic store never exercises the documented maximum wait.

**Regression recommendation:** Two-observer stall probe and timeout/reconciliation test; record real duration and any acceptance deviation.

**Narrow repair direction:** Prefer narrowly async mutations only where measured/approved; preserve one writer transaction and main-thread result publication.

**Downstream impact:** M09 plus M10–M14 mutations; do not impose an unrequested universal async redesign.

**Pinned evidence:** [C01] `docs/v2/contracts/hub.md`, [C02] `docs/v2/contracts/store.md`, [S02] `localflow/v2/ui/hub.py`, [S08] `localflow/v2/store.py`.

### M09-AUDIT-28 — Queued work, pending clipboard lifetime and user repaste intent need distinct focus policy

**Severity:** DESIGN CONCERN · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** M08 API consumption / policy

**Canonical requirement:** Accepted M08 operation identity and lapsed-paste semantics must be preserved while M09 avoids unsafe focus changes.

**Code location:** app.py: _hub_blocks_show/hubPasteText; insertion/service.py busy/paste_text and pending payload.

**Current behavior:** busy means executing work; a pending clipboard payload may remain until later reconciliation, not a timer. Each deliberate Paste Again creates a fresh operation identity.

**Failure mechanism:** Treating every pending clipboard as busy can block the Hub indefinitely; deduplicating all repastes by job ID would reject legitimate fresh user intent.

**Minimal reproduction:**
1. Probe the states separately with a pending payload before/after five seconds, a queued reconciliation, and fresh deliberate Paste Again actions.

**Expected behavior:** Define safe activation/admission and exactly-once handling per action without rewriting M08’s identity or pending-payload policy.

**Likely actual behavior / verification boundary:** Policy/native adjudication required; neither permanent busy nor global job-ID dedup is justified.

**Existing coverage:** M08 owns detailed service behavior; M09 tests only the old busy shape.

**Why the oracle misses it:** One boolean does not describe all modern states, and a second deliberate user action is not automatically an accidental duplicate.

**Regression recommendation:** Controls separating duplicate delivery of one action from two independent explicit actions; focus-change/target-refusal logs at the native seam.

**Narrow repair direction:** Consume a narrow authoritative quiescence/admission API if needed; do not expose private payloads or weaken target validation.

**Downstream impact:** Preserve accepted M08; M12 quick-open shares focus intent but not insertion semantics.

**Pinned evidence:** [S07] `localflow/app.py`, [S09] `localflow/v2/insertion/service.py`, [C03] `docs/v2/contracts/insertion.md`, [D13] `docs/v2/handoffs/M08.md`.

### M09-AUDIT-29 — Post-delete job/app metadata remains queryable until separate metadata pruning

**Severity:** DESIGN CONCERN · **Runtime status:** NOT_RUN · **Disposition:** pending local adjudication

**Confidence:** HIGH — source-supported; not runtime-reproduced

**Category:** privacy labeling / metadata retention

**Canonical requirement:** S29.14 delete wording versus S08/S21 separate operational/usage retention; app names are private local metadata, not automatically content-free.

**Code location:** store.py: delete_everywhere/prune_metadata; history_queries.py: jobs LEFT JOIN job_targets and app filters.

**Current behavior:** delete_everywhere purges payload/derived evidence but leaves job/job_targets rows. prune_metadata later deletes targets with eligible jobs. History’s app query can still discover that metadata.

**Failure mechanism:** The UI can promise deletion more broadly than the actual metadata lifecycle. Preserving M13 usage facts is independently permitted and must not be confused with retaining a searchable job target.

**Minimal reproduction:**
1. Create a synthetic job target, delete its evidence, query by app and job, then advance to legitimate metadata pruning.
2. Verify independent usage facts are not deleted by a content-only control.

**Expected behavior:** Explicit, consistent policy: suppress disallowed metadata immediately or clearly label the retained metadata-only record and its retention; never fabricate a destination/date.

**Likely actual behavior / verification boundary:** Metadata remains discoverable before pruning. Whether that violates an accepted retention exception needs explicit adjudication, not an invented policy.

**Existing coverage:** Target creation and content purge tests, not a post-delete app-discovery contract test.

**Why the oracle misses it:** They check payload absence but not private usage metadata discoverability.

**Regression recommendation:** Job-target create/delete/prune/orphan scenarios with exact allowed fields and independent usage-retention control.

**Narrow repair direction:** Resolve the contract/UI/query boundary narrowly; do not opportunistically rewrite M13 pruning or delete analytics.

**Downstream impact:** M02 deletion wording, M09 History filtering, M13 independent usage retention and privacy exports.

**Pinned evidence:** [S03] `localflow/v2/history_queries.py`, [S08] `localflow/v2/store.py`, [C02] `docs/v2/contracts/store.md`, [C08] `docs/v2/contracts/analytics.md`, [D06] `docs/v2/LOCALFLOW_V2_SPEC.md`.

## Areas Verified Strong

“Verified” here means inspected in the pinned source, not executed on macOS.

The shell/state split remains real. Query results are materialized through the sanctioned Store writer. Production query/long-action refresh callbacks use `callAfter`. Window close is hide rather than quitting the service. The app holds one Hub controller reference. History has escaped parameterized search and source-aware absence labels; unknown dates are not fabricated. [S01–S03, S07]

The historical per-example listen gate and actual Retry button fix remain. M03 retry claims and unscoped context survive. Paste Again threads a real V2 job identity; jobless legacy behavior is intentionally separate. M08 owns operation identity/revocation rather than the Hub inventing a second insertion engine. [S02, S05, S07, S09]

Training keeps intended/verbatim separate, partial spans partial, append-only revisions and review leases distinct from user pins. M02 deletion admission and payload purge are present in schema v11, and metadata pruning deletes eligible job-target rows without deleting independent usage facts. These strengths constrain the repair; they do not cancel the lifecycle/cache findings. [S04, S08]

## Adversarial Corpus Summary

File: `LocalFlow_M09_Adversarial_Corpus.json`.

| Item | Authored | Executed here |
|---|---:|---:|
| Cases | 135 | 0 |
| Required stateful probes | 20, mapped to C001–C020 | 0 |
| Manual-only proposed trials | 7, C129–C135 | 0 |
| Metamorphic relations | 14 | 0 |
| Mutation specifications | 28 | 0 |

Every case/relation/mutation is `NOT_RUN`; there are no claimed passes or failures. The corpus includes preservation controls for accepted behavior, not just predicted regressions. It specifies synthetic fixtures, schedule barriers, independent oracles, native boundaries and evidence fields. A local runner must be implemented/adapted; the JSON is not falsely presented as executable automation.

## Stateful / Metamorphic / Mutation Plan

C001–C020 directly map the required twenty stateful probes. Remaining cases extend errors, check→publish races, table/confirmation identity, queue/clipboard states, all History source classes, DST, lineage decisions, replay deletion, lifecycle composition, diagnostics policy and current benchmark populations.

Fourteen relations capture newer-wins, selection authority, delete monotonicity, listening isolation, retry idempotence, repaste intent identity, retention/lineage absence, main-thread affinity, pin separation, legacy identity, filename-independent diagnostics, redaction extension safety, lifecycle monotonicity and benchmark work sensitivity. Twenty-eight mutants challenge those relations and benchmark validity. Never mutate accepted source in place for mutation tests; use disposable isolated copies and prove the exact mutation applied.

## Downstream Impact

| Milestone | Required seam protection | Not authorized here |
|---|---|---|
| M02 | Durable deletion, quarantine, leases, writer transactions, typed event export | Re-audit/rewrite the storage campaign |
| M03 | Exclusive retry claims, attempts, unscoped recovery, dictation under Store stalls | Worker/journal redesign |
| M08 | Stable job/action identity, revocation, true-idle notification, focus/queued admission policy | New insertion engine, weaker target validation, blanket job-ID dedup |
| M10 | Stable editor/table selection and current shell construction | Style/snippet semantics |
| M11 | Authoritative lineage and applied/fallback identity; retained R4 | Prompt Engineer quality or re-tuning |
| M12 | Shared selection/dispatch and controlled query/commit race isolation | Autosave/revision/attachment cleanup |
| M13 | Honest app metadata and separate usage retention; current Insights shell | Analytics arithmetic/prune algorithm redesign |
| M14 | Main-thread test harness, stable candidate IDs, action-bound completion, revoked cached profile/evidence | Learning/profile/export business logic |
| M15 | No final consistency/readiness green until M09 and other campaign gates are real | Start M15 or clear prior model/manual gates |

Current M11 handoff still records separate model-backed/native readiness concerns. This M09 audit neither resolves them nor reclassifies them as M09 defects. [D14]

## Recommended Repair Order

1. Freeze the current local/canonical baseline, complete caller inventory and reproduce each allegation independently. Preserve this corpus unchanged and record a separate base results file.
2. Repair shared selection/action binding and atomic generation/revocation publication first (01–03). Build real-button and late-error regressions before editing related adapters.
3. Close lifecycle and replay authority holes (04–07), then reuse accepted typed redaction (08). Confirm deletion stops cached/replayed/copyable payload without destroying legitimate independent interests.
4. Resolve authoritative lineage, History sources/order/filter controls and diagnostics chronology/window behavior (09, 12–20). Preserve M11 result decisions and legacy identity.
5. Bound query work, deliver deferred intent after true idle, and bind long-action/error states (10–11, 21–22). Adjudicate queued/clipboard focus, metadata and synchronous waits explicitly (27–29).
6. Repair the M14/M09 harnesses and benchmark validity (23–26), run native/compatibility evidence on an isolated Mac, then perform the mandatory independent first-pass review and fail-first/pass-final checks.
7. Update only the authorized M09 runbook/contracts/results and orchestration state, push the dedicated branch, and stop without merging.

## M09 Readiness Verdict

### C. Significant Hub/query/evidence weaknesses

M09 is not ready to be treated as a fully reliable foundation for final cross-milestone qualification. The source-supported critical/high paths involve wrong-record authority, deleted private caches, lifecycle reactivation, stale spans/replay and privacy export—not merely missing visual polish. At the same time, the accepted M02/M03/M08/M11 protections are substantially present and should be preserved through narrow M09 repairs.

This is a completed **read-only source audit with explicit runtime/native/caller proof gaps**, not a remediation completion claim. Every allegation must be reproduced, refuted, narrowed, already-fixed, classified test/design-only, or left explicitly native/manual unresolved by the local session. No product test, manual verification or performance result has been fabricated.

## Evidence and Reading Ledger

The user’s attached M09 brief defines the requested scope and no-self-merge rule. Repository evidence is pinned to `7cd1111f0499e14bf110d2089c69fe4fa4075507`. Source IDs below identify the inspected scopes; finding locations use named functions/paths so they remain traceable without inventing source line numbers. Connector responses wrap code in one JSON content line, so source-file line numbers were not inferred from response line numbers.

### S01 — `localflow/v2/ui/state.py`

History, Models/Training, downstream loaders, generation/publication, wait/lifecycle.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/ui/state.py`

### S02 — `localflow/v2/ui/hub.py`

Shell, datasource/delegate, actions, all ten view adapters, background completions and settings.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/ui/hub.py`

### S03 — `localflow/v2/history_queries.py`

Search, source merging, grouping, role selection, detail, lineage, audio, Home.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/history_queries.py`

### S04 — `localflow/v2/training_data.py`

Inspection, annotation helpers, verbatim/intended/spans, pin/exclude/delete; readiness only at M09 boundary.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/training_data.py`

### S05 — `localflow/v2/ui/replay.py`

Entire replay service.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/ui/replay.py`

### S06 — `localflow/v2/diagnostics.py`

Entire diagnostics query/export module.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/diagnostics.py`

### S07 — `localflow/app.py`

Hub construction/coordinator, focus/deferred intent, retry, deletion listener, retention, shutdown and relevant downstream callbacks.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/app.py`

### S08 — `localflow/v2/store.py`

Schema v11, writer/commit/rollback, artifact and revision helpers, deletion barrier/listeners/purge, metadata pruning; not a new M02 audit.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/store.py`

### S09 — `localflow/v2/insertion/service.py`

Admission, busy, queued repaste, completion ordering, reconciliation and revocation; not M08 insertion algorithm requalification.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/insertion/service.py`

### S10 — `localflow/v2/training.py`

Transform artifact/decision production and latest-revision outcome/note callers of shared annotation helpers.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/v2/training.py`

### S11 — `localflow/config.py`

Defaults and validated retention bounds; current Hub-related configuration.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/localflow/config.py`

### S12 — `scripts/v2/benchmark_m09.py`

Search, shell, inspector, memory, main and budget verdict.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/scripts/v2/benchmark_m09.py`

### S13 — `scripts/v2/view_events.py`

Accepted M02 ordering and typed redaction implementation.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/scripts/v2/view_events.py`

### T01 — `tests/v2/ui/test_hub_shell.py`

Entire current standalone suite and inline dispatcher shim.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/tests/v2/ui/test_hub_shell.py`

### T02 — `tests/v2/ui/test_history_queries.py`

Current list/detail/lineage/filter tests.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/tests/v2/ui/test_history_queries.py`

### T03 — `tests/v2/ui/test_training_data.py`

Current annotation/retention/replay tests and standalone entry point.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/tests/v2/ui/test_training_data.py`

### T04 — `tests/v2/ui/test_diagnostics.py`

Current three diagnostics tests.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/tests/v2/ui/test_diagnostics.py`

### T05 — `tests/v2/ui/test_training_review_hub.py`

M14 make_hub/run_background shim and shell/action tests, scoped review.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/tests/v2/ui/test_training_review_hub.py`

### T06 — `tests/v2/notes/test_scratchpad_hub.py`

MainThreadAfter, actual note-transform button path, immediate revision assertions; scoped review.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/tests/v2/notes/test_scratchpad_hub.py`

### C01 — `docs/v2/contracts/hub.md`

Current complete shared Hub contract.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/hub.md`

### C02 — `docs/v2/contracts/store.md`

Current writer, retention, deletion and accepted remediation addenda.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/store.md`

### C03 — `docs/v2/contracts/insertion.md`

Current accepted M08 operation, queue, pending-payload, callback and revocation semantics.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/insertion.md`

### C04 — `docs/v2/contracts/context.md`

Current accepted M06 identity, permission, retention and retry seams.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/context.md`

### C05 — `docs/v2/contracts/training_evidence.md`

Relevant audio/reference/stage identities, accepted producer addenda and M09-facing provenance.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/training_evidence.md`

### C06 — `docs/v2/contracts/artifacts.md`

Immutable stages, parent identities, offsets and leases.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/artifacts.md`

### C07 — `docs/v2/contracts/events.md`

Accepted M02 typed redaction and stream/time ordering.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/events.md`

### C08 — `docs/v2/contracts/analytics.md`

M09 Insights adapter, private app metadata, independent usage retention; no arithmetic audit.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/analytics.md`

### C09 — `docs/v2/contracts/learning.md`

M14 review/candidate identities and non-reviewable lifecycle states; no classifier audit.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/learning.md`

### C10 — `docs/v2/contracts/preferences.md`

Exact candidate/task identities and explicit judgments.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/preferences.md`

### C11 — `docs/v2/contracts/profile.md`

Your Voice shell, async generation, invalidated display and privacy boundary.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/profile.md`

### C12 — `docs/v2/contracts/dataset_exports.md`

M09 shell integration, exact inputs, background action/finalization and ownership; no export-content audit.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/dataset_exports.md`

### C13 — `docs/v2/contracts/scratchpad.md`

M09 shared shell, editor/destination ownership and callback discipline.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/scratchpad.md`

### C14 — `docs/v2/contracts/transforms.md`

Reconciled M11 identities, applied/fallback distinction and M09 surface.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/transforms.md`

### C15 — `docs/v2/contracts/INDEX.md`

Owners, suite mapping and accepted addenda.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/contracts/INDEX.md`

### D01 — `README.md`

Current project orientation.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/README.md`

### D02 — `docs/v2/START_HERE.md`

Current startup/testing and source precedence.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/START_HERE.md`

### D03 — `docs/v2/STATUS.json`

Current committed historical milestone state; not runtime proof.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/STATUS.json`

### D04 — `ORCHESTRATION.html`

Current campaign/Now and historical context; not a visual/layout review.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/ORCHESTRATION.html`

### D05 — `docs/v2/LOCALFLOW_V2_MILESTONES.md`

P01–P04 and M09 scope, budgets, AC01–AC06.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/LOCALFLOW_V2_MILESTONES.md`

### D06 — `docs/v2/LOCALFLOW_V2_SPEC.md`

S08, S19, S21, relevant S25 retention/privacy, S29.4/.6/.14/.15.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/LOCALFLOW_V2_SPEC.md`

### D07 — `docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md`

EV-11, EV-19, EV-20, E14 and relevant E19 evidence/coverage gates.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md`

### D08 — `docs/v2/handoffs/M09.md`

Historical original findings, implementation and limitations.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/handoffs/M09.md`

### D09 — `docs/v2/acceptance/M09/results.json`

Historical AC results, human trial, tests, benchmark and review-loop evidence; not rerun.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/acceptance/M09/results.json`

### D10 — `docs/v2/handoffs/M02.md`

Accepted remediation/review addendum, deletion/redaction seam and limits.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/handoffs/M02.md`

### D11 — `docs/v2/handoffs/M03.md`

Accepted retry/claim/deletion/store-stall remediation addendum.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/handoffs/M03.md`

### D12 — `docs/v2/handoffs/M06.md`

Accepted main-thread lead, R4 integration and local verification boundaries.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/handoffs/M06.md`

### D13 — `docs/v2/handoffs/M08.md`

Accepted production/head, evidence/runbook and canonical merge.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/handoffs/M08.md`

### D14 — `docs/v2/handoffs/M11.md`

Reconciliation/replay, R4, final production, M12 race and outstanding M15 gates.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/docs/v2/handoffs/M11.md`

### D15 — `CLAUDE.md`

Instruction addition inspected through commit 2a28675: repository auto-merge conflicts with this task’s explicit no-self-merge.

Pinned source: `https://github.com/scalinity/LocalFlow/blob/7cd1111f0499e14bf110d2089c69fe4fa4075507/CLAUDE.md`

## Delivery Integrity

The package also contains the findings docket and source index as JSON, the complete local Claude handoff, and a SHA-256 manifest. Document validation checks schema shape, unique IDs, cross-references, required probes and all-NOT_RUN status only. It does not execute LocalFlow or establish product correctness.

Final canonical recheck: `main` remained `7cd1111f0499e14bf110d2089c69fe4fa4075507` at delivery. See `LocalFlow_M09_Canonical_Baseline.json` for the observed gate and drift record.
