# LocalFlow V2 — M02 Read-Only Deep Audit

**Repository:** `scalinity/LocalFlow`  
**Canonical branch inspected:** `main`  
**Audited commit:** `3ae0070d84730f8d750440f51097c4a53ff8bf02`  
**Audit date:** September 24, 2026 (America/New_York)  
**Method:** Source inspection, contract tracing, adversarial interleaving analysis, and test-oracle review. Reproduction scenarios below were **designed, not executed** in this audit.  
**Verdict:** **C — Significant persistence/evidence weaknesses.**

## Executive Assessment

M02 has a useful architecture and several real safeguards, but it is not yet a trustworthy boundary for all of the evidence and privacy guarantees that its downstream consumers assume.

The most consequential weaknesses are not model-quality problems. They concern **when an operation becomes durable, when an example becomes visible, what deletion prevents, and whether a retained artifact really belongs to the recorded attempt**. A serial SQLite writer prevents simultaneous SQL execution; it does not make a sequence of separately submitted operations atomic, and it cannot roll back an already-unlinked audio file.

This audit records **20 findings: 3 Critical, 14 High, and 3 Medium**, using the requested severity rubric. These are source-supported failure mechanisms and contract inconsistencies, not a claim that twenty failures have been observed on Daniel's Mac. Confidence and the reproduction boundary are stated per finding.

The priorities are: prevent post-deletion publication; make deletion completion honest; publish known-sensitive examples only in quarantine; bind permission and attempt identity correctly; acknowledge committed evidence rather than queued work; repair retention and revision transactions; then strengthen import, verification, event retention, shutdown, and benchmark evidence.

The accepted M01 repair is inherited. Its exact-text preservation and all-verified-prefix reconciliation must **not** be undone to simplify M02 repairs. M07 and M11 were not re-audited. The limited downstream inspection establishes interfaces and existing safeguards, not a new audit of those milestones.

## Audit Boundary

> This audit covers committed GitHub state at `3ae0070d84730f8d750440f51097c4a53ff8bf02`. Any uncommitted local state is outside the audit boundary.

The connected GitHub reader was used to resolve `main`, inspect ancestry, and retrieve commit-pinned files. No GitHub writes, branch creation, commits, issues, pull requests, or implementation were performed. Repository source, tests, and documentation were not edited.

Read scope included README; START_HERE; STATUS; M02 and relevant foundational milestone requirements; the relevant specification and evaluation sections; job/event/artifact/store/training/reference/preference/target/export contracts; M01 and M02 handoff and acceptance records; the four core M02 modules; M02 app, cleanup, audio and configuration hooks; import/event-view/benchmark scripts; the five requested M02 suites; M01 import-boundary regressions; and limited newer training/export service and test interfaces.

**Execution boundary:** No repository test suite or proposed reproduction was run in this audit. Historical results were read as historical evidence. No claim is made about the installed application, actual private database, microphone, AppKit/PyObjC, Accessibility, TCC, MLX/Metal, actual model execution, APFS behavior, sleep/wake, or reference-Mac performance. Native checks remain `PENDING_LOCAL_VERIFICATION` where necessary.

Source links below are pinned to the audited commit. Code locations use actual file and function names rather than pretending that connector response line numbers are repository line numbers.

## M01-Remediated Main Baseline

The baseline gate **passes**:

| Item | Verified committed state |
|---|---|
| Current `main` | `3ae0070d84730f8d750440f51097c4a53ff8bf02` |
| Accepted final M01 head | Exactly the same commit as audited `main` |
| Accepted M01 production repair | `3db74061f23001b9cce3d4fe029e0b30cbc295d6`, the direct parent of audited `main` |
| Pre-repair parent | `dbc8fe27fdf89720ff32ee65c27bc4e6220d4556` |
| Audited tree | `da5f3ae1ed130b6c222d9cb177e3a7aa4e366197` |

The tree contains the M01 producer scripts, remediation tests and evidence, current M01 handoff/acceptance addenda, and `docs/v2/VERIFICATION.html`. The current importer and its M01 boundary tests preserve exact payload text, defer newly encountered incomplete tails, inspect all verified historical prefixes, and link a later completion to a previously imported partial record without modifying the old payload. The six boundary tests use hand-written expected payloads and explicitly preserve distinct identities for repeated identical utterances. Their presence and assertions were inspected; they were not rerun here. [M01 handoff] [M01 acceptance] [M01 boundary tests]

The new finding about interruption plus source growth does **not** refute those accepted M01 changes: it concerns the absence of durable prefix/run metadata when an import is interrupted before its final run record is written.

## M02 Responsibilities

M02 is responsible for dated structured events, durable job and artifact identity, SQLite migrations and import bookkeeping, actual live training-evidence collection, consent records, independent retention interests, deletion, quarantine, and trustworthy missing/provenance information. Its outputs are consumed as facts by later job recovery, insertion attribution, analytics, curation/export, and qualification work. [Milestones] [Specification] [Training contract]

Three distinctions are essential throughout this report: **operational history is not training consent; a queued write is not a committed write; and a logical deletion marker is not proof that every managed content copy has been removed.**

## Current Architecture

```text
Capture / app coordinator / model observations
                |
                +--> EventWriter queue --> dated JSONL files
                |
                +--> EvidenceCollector --> separately queued store operations
                                           |
                                           v
                                   single SQLite writer
                                   jobs / artifacts / revisions /
                                   consent / leases / import metadata
                                           |
                            filesystem audio payloads outside SQL

Later consumers read the store and payload graph;
some add stronger checks than Store.verify().
```

The single-writer service and connection-level composite `Store.submit(...)` entry point are valuable foundations. However, the collector frequently uses multiple asynchronous calls instead of one logical publication transaction. Audio creation happens outside SQL; audio unlinking happens inside a callback whose surrounding transaction has not yet committed. Event emission is a separate channel with separate failure and retention behavior. [Store] [Collector] [Event writer]

## Historical Review Findings Considered

The historical M02 review reported cross-thread observation attribution, a dead history-persistence branch, and retention deleting legacy imports. Current source contains the relevant intended repairs: observation binding is on the coordinator that processes the job, the non-collection history path persists transcripts when enabled, and generic retention excludes legacy artifacts. This audit does not refile those repaired cases merely because they once existed. [M02 handoff] [App] [Store]

The September 22 human acceptance records remain meaningful for the code and instructions they actually exercised. They do not establish mid-flight consent semantics, crash consistency, failed-unlink behavior, or safe handling of unknown future event fields. Changing an implicated path should stale only the relevant historical check, preserving its result history. [M02 acceptance]

## Job State-Machine Assessment

The job contract names the progression `capturing → queued → transcribing → normalizing → cleaning → validating → ready_to_insert → insertion_posted → insertion_confirmed`, with `transforming` before insertion for auto-transforms, `insertion_unverified` for posted-but-unobservable insertion, and alternatives `saved_not_inserted`, `cancelled`, `failed_recoverable`, and `failed_unrecoverable`. Job identity stays stable across retries while `attempt` increments. [Jobs contract]

`Store.update_job_state` serializes transitions and protects terminal states against ordinary regression. Explicit `failed_recoverable → queued` retry is intentional; it is not itself an erroneous resurrection. Nevertheless, its rank-based check is not a complete legal-edge validator, and its API does not require the expected attempt/generation. Attempt increments and reopening are separate operations. The app also does not use the transition's Boolean result to guarantee exactly one corresponding event. [Store] [App]

**Exactly-one assessment:** the row-level safeguard is transactional application logic, not an independent database constraint proving exactly one terminal outcome per attempt. Exactly one durable terminal **event**, agreement between events and SQL, and rejection of stale-attempt state updates are not established by the M02 boundary. The sequential state tests do not settle cancellation/completion or retry/late-result races. This report does not claim that the M03 supervisor actually accepts stale worker messages; that is a separate boundary with its own protections. [Store tests]

For durable workflow state, the store is the practical authority used by application consumers. The event log is not a transactional replica. A missing event therefore cannot safely mean “the transition did not occur,” and an emitted success cannot prove the corresponding write committed. Repairs should make this authority explicit and provide a small recoverable transition/publication record where the contract requires durable event correspondence.

## Store / Transaction / Crash-Consistency Assessment

The core single-writer discipline is sound for operations executed on that writer, and explicit connection-level composite operations are the right repair mechanism. The most important gaps are split publication transactions, pre-commit filesystem effects, caller-visible success before durable acknowledgment, lifecycle admission during shutdown, and incomplete integrity verification. [Store]

The principal crash boundaries are:

| Boundary | Current risk | Required convergence |
|---|---|---|
| Audio file written, artifact insert not committed | Unindexed private payload | Identifiable staging/orphan state, never falsely complete evidence |
| Artifact/lease/example/revision submitted separately | Partial evidence graph | Atomic logical publication or explicit incomplete state |
| Example/revision committed, quarantine state not committed | Known-sensitive example has wrong lifecycle state | Ineligible from the first visible state |
| Audio unlinked, enclosing SQL transaction fails | Live database row points to missing file | Durable purge intent and restart-safe reconciliation |
| Pair committed, import run metadata not recorded | Later append defeats known-prefix deduplication | Durable source lineage for every committed pair |
| State committed, event not persisted | State/event disagreement | Documented authority and an honest missing-event record |

No enterprise storage redesign is required. A few well-defined transactional service operations plus a small durable payload-deletion/staging protocol address the root causes more directly than adding exception suppression.

Migration and repair need a stricter distinction between a recognized additive upgrade and corruption recovery. The code has actual migration transactions and SQLite backup support, but current-version repair can recreate a missing core table without proving preservation of the lost relationships. Actual journal/synchronous/foreign-key settings should be recorded by portable verification rather than assumed from an unstated SQLite default. [Store]

## Event Logging Assessment

The writer supplies structured UTC instants, timezone/offset context, writer-assigned sequence and event identity, and monotonic timing support. Existing tests positively inspect thousands of concurrent events and simulate disk failure followed by recovery; these are stronger than empty-population or merely-no-exception checks. [Event writer] [Event tests]

The remaining risks are significant: size-roll eviction bypasses unresolved-job retention; normal-priority terminal records are not made durable merely because the associated SQL state is durable; shutdown can strand accepted work; and redacted export copies unknown fields rather than failing closed. Parent/causal-link and revision fields also need explicit contract-conformance coverage rather than assuming that a timestamp and UUID are a sufficient envelope. [Event viewer] [Events contract]

## Importer Assessment

Current M01 prefix verification hashes actual source bytes and does not trust size alone. Exact text, unknown dates, old partial immutability, completed-tail linkage, and repeated-identical-utterance identity are intentional and must survive remediation. [Importer] [M01 boundary tests]

The uncovered cases are composite ones: an interrupted import followed by growth before rerun, and stats imports whose source-scoped bookkeeping is inconsistent with a globally keyed legacy row. Same-source rerun coverage does not establish convergence for either case. Dictionary and transform import use stronger composite operations and should not be weakened to match the stats path. [Importer] [Import tests] [Store]

## Consent / Training Evidence Assessment

Default-off collection and separate operational-history behavior are present. The collector captures actual rendered prompt/proposal artifacts without initiating additional model calls; it distinguishes proposed output, applied output, and fallback metadata. The current coordinator binding addresses the historical observation attribution case. [Collector] [Cleanup hook]

However, the app creates the collector context after capture finishes, while the contract defines its consent revision as capture-time permission. Permission state and revision are also read separately. Evidence context attempt metadata is not updated alongside the app's retry counter. Publication, quarantine, leases, and revisions cross separate transaction boundaries. These are evidence-attribution and consent defects even when the displayed transcript looks correct. [Training contract] [App] [Store]

The phrase “paused means no training payload” needs an exact policy for already-authorized in-flight captures. The existing frozen-context behavior and capture-time contract should not be silently replaced by arbitrary last-second sampling. The definite defect here is that a later consent revision can be represented as the permission for an earlier capture. Any immediate-pause/revocation guarantee must additionally be enforced at publication and payload boundaries.

## Retention / Deletion Assessment

Generic artifact pruning does account for live leases and legacy exemptions. Training expiry, however, revokes all leases on the example's job artifacts, breaking independence when history outlives the training buffer. The legacy “mark correct” control also fails to give the example the retained reviewed lifecycle/provenance used by newer consumers. [Store] [Collector] [Training inspector]

Delete-everywhere has useful descendant cleanup hooks, including derived learning/profile state, but it does not establish a durable job-level write barrier. It also reports completion after suppressed unlink errors and does not cover the app's separately managed debug audio directory. Deleting current rows is therefore not equivalent to deleting the content everywhere and preventing recreation. [Store] [App]

## Privacy / Quarantine Assessment

This is not a request for perfect secret detection. The confirmed design issue starts **after a secret is suspected**: the code publishes an ordinary example and revision before separately changing the example index to quarantine. Detection correctness cannot make that publication sequence atomic. [Collector]

Private-file permissions and filesystem confinement deserve focused native checks where changed code relies on APFS behavior. The M02 artifact directory is not the complete inventory of app-managed audio: the log-transcript debug path writes a separate PCM16 copy. Tombstone tests should also inspect residual metadata, caller-supplied reason strings, and content-derived identifiers rather than checking only that `content_text` became null. This report does not assert that every retained hash is prohibited or that an actual secret was leaked from Daniel's machine.

## Test-Oracle Assessment

| Suite | Positive evidence in the source | What its current oracle does not establish |
|---|---|---|
| `logging/test_event_writer.py` | Populated concurrent output, unique sequence/event IDs, rotation and disk-recovery cases | Unresolved protection through the roll-count cap; unknown nested-field redaction; accepted work at close |
| `storage/test_store.py` | Concurrent population, pure-SQL rollback, leases, deletion and schema repair | Filesystem rollback; deletion plus late callbacks; reverse lease expiry; populated missing-core-table repair; payload hash/ownership integrity |
| `storage/test_import.py` | Same-source idempotency, append reconciliation, interrupted same-source rerun | Interruption **combined with** source growth; conflicting stats row identity; failed row followed by successful bookkeeping |
| `training/test_collector.py` | Default-off and enabled populations, exact prompt capture, final quarantine/control states | Real concurrent publication/edit/delete interleavings; capture-boundary consent changes; quarantine visibility before final state; review retention/export provenance |
| `training/test_live_pipeline.py` | Explicit native/model prerequisites; real prompt capture assertions when run | Portable cloud certification, broad speech accuracy, or new execution in this audit |
| M01 boundary regressions | Hand-written exact payloads, old partial/completion identity and multiple prefixes | Durable lineage for a run that never reached its final metadata write |
| Newer export safety tests inspected | Deliberately damaged audio is refused by the exporter | Integrity of all earlier M02 records or correctness of `Store.verify()` |

Sources: [Event tests] [Store tests] [Import tests] [Collector tests] [Live tests] [M01 boundary tests] [Export tests].

The named collector “simultaneous jobs” helper exercises sequential complete captures; it is not evidence of a thread race. The separate binding/interleaving coverage is valuable for the coordinator's actual ownership model. The benchmark population issue in M02-AUDIT-17 is a concrete false-green path, not merely a recommendation to add more tests.

## Critical Findings

### M02-AUDIT-01 — Deletion does not prevent late evidence publication or recreation

**Severity:** Critical. **Confidence:** High, source-demonstrated; runtime reproduction not executed. **Category:** Privacy, lifecycle, transactional integrity.

**Canonical requirement:** S29.14 and the training/store contracts: delete-everywhere overrides leases and no descendant may recreate deleted content.

**Code location / implementation:** `Store.delete_everywhere`, `write_text_artifact`, `write_audio_artifact`, `upsert_example`, `append_revision`; collector stage/finalization/outcome callbacks. Deletion enumerates current job artifacts and examples. It writes artifact/example tombstones but no durable job-level prohibition against future evidence writes. Writers do not validate a deletion epoch or equivalent liveness token. Collector callbacks rely on `ctx.collecting` and existing context IDs. [Store] [Collector]

**Failure mechanism:** A callback delayed until after deletion can create new artifact IDs or a new example for the same job. A delayed outcome callback can also append a revision to an already-deleted example. Serialization only orders these operations; it does not reject the late one.

**Minimal reproduction:** Begin a collected job; retain its context. Delete the job before finalization. Resume audio/text/finalize callbacks. Separately finalize an example, delete it, then invoke an outcome/observation callback with the old context.

**Expected:** No new content, leases, or usable revision graph for the deleted logical job; explicit rejection/invalidation. **Likely:** New payload/example or late revision is accepted because the storage mutation has no deletion guard. Runtime verification required.

**Existing coverage / regression:** Current deletion coverage inspects a completed graph, not a resumed producer. Add barrier-controlled tests for both orderings, including deletion before an example exists, after payload staging, and between revision read and append. Inspect content bytes and all related rows, not just `state='deleted'`.

**Narrow repair / downstream impact:** Persist a content-free job tombstone/deletion epoch and validate it inside every evidence publication transaction; invalidate in-flight producer authority. M03 retry/recovery, M08 delayed observations, M14 deletion and M15 provenance all depend on this.

### M02-AUDIT-02 — Delete-everywhere can report success while managed audio remains

**Severity:** Critical. **Confidence:** High for both concrete paths; native filesystem reproduction pending. **Category:** Privacy, deletion completeness.

**Canonical requirement:** S29.14; delete-everywhere removes managed content copies and reports failures honestly.

**Code location / implementation:** `Store._purge_artifact` nulls the path and marks a row purged, suppressing unlink `OSError`; `sweep_orphans` moves unknown WAVs into an orphan directory rather than completing deletion. Separately, the app's `_dump_audio` path writes transcript-logging PCM16 WAVs under `~/Library/Logs/LocalFlow-audio` and keeps the latest five without registering them in the store's job/artifact graph. [Store] [App]

**Failure mechanism:** After a failed unlink, the database no longer retains the normal retry path, yet deletion reports the artifact purged. Moving that leftover into quarantine is not deletion. The separate debug copy is outside the enumeration entirely.

**Minimal reproduction:** Inject an unlink permission error for one registered audio artifact, call delete-everywhere, then retry and sweep. Independently create a dictation with transcript logging enabled, identify its debug WAV, and delete its store job.

**Expected:** All managed copies removed, or a durable pending-purge/error state naming the remaining managed work without exposing content. **Likely:** A purge count/success event despite residual audio; the debug copy survives until unrelated rotation. Runtime verification required.

**Existing coverage / regression:** Existing completed-delete tests do not fault unlink or inventory the debug directory. Add failed-unlink/restart/retry tests and a temporary-directory app-audio inventory test. Assert the file bytes are gone, not just the SQL content pointer.

**Narrow repair / downstream impact:** Keep durable purge work until deletion is acknowledged; register the debug copy with job-scoped deletion or remove the redundant managed copy. Do not delete unrelated user files or immutable legacy sources by guessing ownership. M14 and M15 must not interpret a premature deletion event as complete privacy enforcement.

### M02-AUDIT-03 — Known-sensitive evidence is published before quarantine becomes durable

**Severity:** Critical. **Confidence:** High, source-demonstrated transaction split. **Category:** Quarantine, evidence eligibility.

**Canonical requirement:** S29.14: suspected-sensitive evidence must be excluded from training/export handling; audit behavior after detection, not detector perfection.

**Code location / implementation:** `EvidenceCollector.finalize` submits `upsert_example`, `append_revision`, and only afterward `set_example_state(..., 'quarantined_sensitive')`. The ordinary example state and initial revision can therefore commit first. [Collector] [Store]

**Failure mechanism:** A process exit or failed state update between these operations leaves a known-sensitive example indexed as an ordinary captured example. Another consumer can observe the intermediate state. This does not prove that a supervised export would automatically pass its independent review gates.

**Minimal reproduction:** Use a synthetic credential marker that the existing scanner detects. Stop or fault the quarantine-state operation after example and revision publication; reopen and inspect the index and graph. Also interleave a reader between publication and quarantine.

**Expected:** The first durable visible state is quarantined/ineligible, or no example is published. **Likely:** Ordinary lifecycle state survives without the required quarantine transition. Runtime verification required.

**Existing coverage / regression:** The secret test checks the final settled state and absence of secret text in events. Add fault points and visibility checks at each publication boundary, with positive proof that the scanner detected the marker.

**Narrow repair / downstream impact:** Determine quarantine before publication and commit example state, initial revision, and required relationships atomically. Keep sensitive content policy separate from event redaction. M14 sampling/review/export and M15 retained evidence depend on the index being truthful from first visibility.

## High Findings

### M02-AUDIT-04 — Filesystem unlink occurs before the surrounding SQL commit

**Severity:** High. **Confidence:** High. **Category:** Crash consistency, durable data loss.

**Canonical requirement:** Store transaction and artifact availability guarantees; a rollback must not leave a live row pointing to a deleted payload.

**Code location / implementation:** `_purge_artifact` updates the row and immediately unlinks. The writer commits only after the enclosing callback returns. Its comment claims “commit first; unlink afterwards,” but the implementation does not establish that order. [Store]

**Failure mechanism:** A later SQL exception, commit failure, or process exit after unlink can restore/retain the pre-transaction live row while the file is permanently absent.

**Minimal reproduction:** Create retained audio. Inside a writer transaction perform the purge, then deliberately raise before commit. Reopen and inspect row liveness, path and file bytes.

**Expected:** Either the live payload survives rollback or a committed purge intent makes deletion explicit and recoverable. **Likely:** Live SQL row, missing WAV. Runtime verification required.

**Existing coverage / regression:** Pure-SQL rollback tests cannot expose this. Add payload-aware rollback and subprocess crash tests at before/after-unlink and before/after-commit boundaries.

**Narrow repair / downstream impact:** Use durable purge intent followed by idempotent filesystem deletion and completion marking. Simply moving unlink after commit without a retry record would trade this failure for M02-AUDIT-02. Affects M03 recovery, M14 replay/export and M15 artifact availability.

### M02-AUDIT-05 — Queued writes are represented as saved, complete evidence

**Severity:** High. **Confidence:** High. **Category:** Persistence acknowledgment, evidence integrity.

**Canonical requirement:** M02/E19 completeness must describe retained artifacts, not merely allocated IDs; failure isolation must not manufacture complete evidence.

**Code location / implementation:** Multiple artifact, lease, example and revision APIs queue work asynchronously and return IDs. `sync()` waits for a barrier but does not propagate earlier asynchronous failures. Collector finalization emits `training.revision_saved` with `capture_complete` before those writes are acknowledged. [Store] [Collector]

**Failure mechanism:** An artifact insert can fail while later example/revision operations succeed. Caller `try/except` cannot catch the earlier writer-thread failure, and the in-memory context still supplies the failed artifact's ID. A saved/completed event is not proof of a committed graph.

**Minimal reproduction:** Fault the raw artifact insert only, allow later operations, finalize and sync, then inspect the revision, artifact table, lease table, error diagnostics and emitted completion event.

**Expected:** Ordinary dictation continues, but evidence is either atomically published or explicitly incomplete with the failed stage identified. **Likely:** Completion is announced despite missing durable pieces. Runtime verification required.

**Existing coverage / regression:** Row-count and final `verify()` checks do not prove correct acknowledgment. Add per-operation failure injection and a successful ordinary-text outcome alongside an honest evidence-failure outcome.

**Narrow repair / downstream impact:** Return bounded acknowledgments/futures or introduce composite publication operations. Emit saved events only after commit. Do not block microphone callbacks or require synchronous persistence of every optional diagnostic. Affects all downstream evidence consumers.

### M02-AUDIT-06 — Consent revision is sampled after capture, not at the recorded capture boundary

**Severity:** High. **Confidence:** High for timing/provenance mismatch; exact in-flight pause policy needs explicit confirmation. **Category:** Consent, temporal attribution.

**Canonical requirement:** `training_evidence.md` defines `consent_revision_id` as collection consent **at capture time**; default-off collection must not be retroactively authorized without an explicit policy.

**Code location / implementation:** The app starts recording and creates the job first, but invokes `collector.job_started` when finishing capture. That helper reads consent state and revision separately and freezes them into the context used by later payload writes. [App] [Collector] [Training contract]

**Failure mechanism:** Start disabled, enable before release: the later enabled revision is attached to earlier audio. Conversely, a context sampled enabled continues writing after a later pause. The latter is only acceptable under a clearly documented capture-snapshot policy, not under an immediate no-new-payload promise.

**Minimal reproduction:** Barrier-control microphone-start and capture-finish; toggle consent between them in both directions. Also interleave a consent write between state and revision reads.

**Expected:** One coherent capture-bound permission decision and matching revision; unambiguous treatment of already-in-flight captures. **Likely:** Later permission is presented as capture-time permission; state/revision can be sampled inconsistently. Runtime verification required.

**Existing coverage / regression:** Pause tests toggle between complete captures. Add boundary and queued-job cases, checking all payload files and rows, not only training-example count.

**Narrow repair / downstream impact:** Read state/revision atomically at the actual capture boundary, carry an explicit permission token, and enforce any revocation/deletion policy at publication. M14 eligibility and M15 provenance require the recorded permission to mean what the contract says.

### M02-AUDIT-07 — Training expiry revokes independent history/recovery retention interests

**Severity:** High. **Confidence:** High. **Category:** Retention, data loss.

**Canonical requirement:** S29 and artifact/store contracts separate history, recovery and training leases. Expiry of one interest must not override another live interest.

**Code location / implementation:** `Store.prune_training` enumerates the expired example's job artifacts, revokes their leases without holder scoping, and purges them. Its indefinite-training-lease protection is not a general live-lease check. [Store]

**Failure mechanism:** With history retained for 90 days and an unreviewed training buffer of 30 days, day-31 training expiry can remove content that history still promises to retain.

**Minimal reproduction:** One shared artifact with a 90-day history lease and 30-day training lease; advance the injected clock past 30 days and run training pruning.

**Expected:** Training interest expires; content survives for history/recovery until all applicable interests expire. **Likely:** Both interests are revoked and content purged. Runtime verification required.

**Existing coverage / regression:** Existing coverage demonstrates the reverse order—history expires first while training protects the artifact. Add the full lease-precedence matrix, including recovery, user pins and delete-everywhere override.

**Narrow repair / downstream impact:** Expire only the relevant holder's interest, then use one shared live-lease predicate to decide payload removal. Preserve deliberate deletion precedence. M03 recovery, M09 history/replay, M14 curation and M15 retained evidence are affected.

### M02-AUDIT-08 — Revision read/modify/append can lose newer annotations and record the wrong parent

**Severity:** High. **Confidence:** High. **Category:** Concurrency, revision provenance.

**Canonical requirement:** Append-only revisions must preserve the actual observation chain and must not silently overwrite newer evidence through a stale snapshot.

**Code location / implementation:** Collector insertion and observation callbacks read `latest_revision` outside the eventual append operation and append using `parent_revision_id=ctx.revision_1`, even after intermediate revisions. `Store.append_revision` does not compare against an expected current parent. [Collector] [Store]

**Failure mechanism:** Callback A reads revision 1; a human annotation creates revision 2; callback A publishes its stale full envelope as revision 3, omitting the new annotation while pointing at revision 1. Serial SQL execution does not serialize the complete read/modify/write operation.

**Minimal reproduction:** Pause an observation callback after its read, submit a marked-correct annotation, resume the callback, then inspect latest content and parent chain.

**Expected:** New observation extends the current revision without dropping unrelated annotations, or receives an explicit conflict. **Likely:** The latest envelope loses the intervening change and/or has a stale parent. Runtime verification required.

**Existing coverage / regression:** Sequential outcome assertions are insufficient. Add barriers and independent assertions for parent identity, annotation preservation and deletion interleavings.

**Narrow repair / downstream impact:** Read, modify, append and update the latest pointer in one writer operation, or use parent compare-and-swap with a defined retry. The newer inspector's connection-level helper illustrates the available pattern. Affects M08 observations, M14 labels and M15 lineage.

### M02-AUDIT-09 — Retry identity changes without updating the evidence context

**Severity:** High. **Confidence:** High for collector/app mismatch; stale-worker acceptance is not asserted. **Category:** Attempt/generation attribution.

**Canonical requirement:** Jobs and training contracts bind evidence to `job_id / attempt / worker_generation`; retries keep the family/job but increment attempt.

**Code location / implementation:** App retry handling bumps the app/store job attempt while the existing evidence context retains its earlier `attempt`. The envelope reads `ctx.attempt`; generation metadata is supplied through stage-specific paths and must also be checked after cleanup-worker retry. Store transitions do not require an expected-attempt token. [App] [Collector] [Store]

**Failure mechanism:** A retried result can be recorded under attempt 1 while the durable job and stage events describe attempt 2. This is misleading evidence even when the worker supervisor correctly rejected all stale messages.

**Minimal reproduction:** Use a synthetic response marked retried with a new generation, follow the app's retry handling, finalize evidence and compare job attempt, events, stage manifest and envelope.

**Expected:** Coherent actual attempt identity, with stage-specific generations represented honestly. **Likely:** Attempt disagreement; generation consistency requires targeted runtime verification.

**Existing coverage / regression:** Add an app-interface test rather than a collector test that manually supplies already-correct metadata. Test two terminal updates racing and a late old-attempt update after explicit reopening.

**Narrow repair / downstream impact:** Establish one retry/attempt transition object and propagate it to job, context and events. Fence storage transitions by expected attempt where needed. Do not relabel earlier stage evidence as if produced by the latest worker. Affects M03, M08, M13, M14 and M15.

### M02-AUDIT-10 — Interrupted log import followed by source growth duplicates committed pairs

**Severity:** High. **Confidence:** High. **Category:** Import idempotency, crash recovery.

**Canonical requirement:** Lossless import must converge after interruption and append without duplicating logical source records, while preserving M01 physical identities and immutable partials.

**Code location / implementation:** `LegacyImporter.import_log` commits individual pairs through `Store.import_legacy_pair`, but `record_import_run` is submitted only after processing the run. Prefix reconciliation relies on those recorded runs. [Importer] [Store]

**Failure mechanism:** A committed pair can exist without durable metadata establishing its source as a verified prefix. If the source grows before retry, the new whole-file hash produces a different pair identity and the missing run record prevents recognition of the old committed pair.

**Minimal reproduction:** Import a log containing multiple closed pairs; interrupt after the first pair commits but before final run bookkeeping. Append another closed record, then rerun.

**Expected:** Previously committed logical pair skipped/reconciled, remaining pairs imported once. **Likely:** The first pair is imported again under the new source hash. Runtime verification required.

**Existing coverage / regression:** Current tests separately cover completed-run append and interrupted same-bytes retry. Combine them, with real committed rows, old partials and multiple verified prefixes. Assert pair identities and exact payloads, not just counts.

**Narrow repair / downstream impact:** Persist sufficient source snapshot/prefix lineage before or atomically with committed pair bookkeeping; distinguish started/completed runs. Do not deduplicate equal text, since distinct utterances may legitimately match. Affects M13 historical counts, M14 lineage and M15 source provenance.

### M02-AUDIT-11 — Stats import identity and acknowledgment can silently skip distinct source data

**Severity:** High. **Confidence:** High for key/transaction mismatch. **Category:** Import persistence, evidence accounting.

**Canonical requirement:** Lossless stats import must reconcile conflicts explicitly and mark an item imported only when its intended durable representation exists.

**Code location / implementation:** Stats import bookkeeping is source-hash/locator scoped, while `insert_legacy_dictation` uses `INSERT OR IGNORE` against a global legacy integer ID. Row insertion and import bookkeeping are separately queued. [Importer] [Store]

**Failure mechanism:** A second source with the same integer ID but different contents is silently ignored while its own bookkeeping can be recorded as imported. A failed asynchronous row insert followed by successful bookkeeping can similarly suppress repair on rerun.

**Minimal reproduction:** Import two small stats snapshots with the same row ID and distinct values; inspect stored values, reports and source bookkeeping. Separately fault only the row insert.

**Expected:** Explicit same-entity reconciliation/conflict or independently preserved source identity; no successful bookkeeping for absent data. **Likely:** One row retained, the distinct source marked handled, or a failed row permanently skipped. Runtime verification required.

**Existing coverage / regression:** Same-source idempotency and total comparisons do not cover cross-source ID collisions. Add deliberate conflicts and row/bookkeeping fault injection.

**Narrow repair / downstream impact:** Atomically couple data and bookkeeping, define source-versus-legacy identity, and report conflicts rather than silently replacing or ignoring content. Preserve existing immutable history. Direct effect on M13 totals and M15 evidence integrity.

### M02-AUDIT-12 — Redacted event export fails open for unknown and nested fields

**Severity:** High. **Confidence:** High. **Category:** Privacy, export schema.

**Canonical requirement:** Redacted diagnostics must not export private content; new event fields must default safe.

**Code location / implementation:** `scripts/v2/view_events.py` builds redacted output by excluding `detail` while copying other keys and values unchanged. [Event viewer]

**Failure mechanism:** A future `context`, `error`, `candidate`, nested object, or arbitrary value in another string field bypasses redaction. The exporter treats “not named detail” as evidence of safety.

**Minimal reproduction:** Write a valid JSONL event with a synthetic private marker under an unknown top-level field and a nested list/object; export redacted output and inspect bytes.

**Expected:** Only explicitly approved, type-validated content-free fields survive; unknown content is omitted or represented by a safe omission marker. **Likely:** Markers appear verbatim. Runtime verification required.

**Existing coverage / regression:** The current redaction test puts secret-like text only in `detail`, the exact field the exporter removes. Add unknown-key, nested-value and malformed-type cases plus a positive assertion that useful safe identifiers remain.

**Narrow repair / downstream impact:** Versioned typed allowlist, including field-specific constraints where strings are not inherently content-free. Do not simply expand a denylist of known private names. Affects shared diagnostics and M15 qualification exports; no actual disclosure is claimed here.

### M02-AUDIT-13 — Size-roll eviction bypasses unresolved-job evidence protection

**Severity:** High. **Confidence:** High. **Category:** Event retention, durable diagnostics.

**Canonical requirement:** Unresolved-job evidence must survive retention policies intended to remove disposable logs.

**Code location / implementation:** Event writer size rotation deletes excess rolls beyond `KEEP_ROLLS` directly. The unresolved-job protection applied in the general retention path is not applied to that eviction path. [Event writer]

**Failure mechanism:** Enough log volume on the same day removes an old roll containing the only relevant unresolved-job event, regardless of whether the age/cap retention callback would have protected it.

**Minimal reproduction:** Set a small roll size, emit a marker for a job reported unresolved, then generate more than eight rolls and inspect retained records.

**Expected:** Protected evidence survives or is safely compacted into a durable protected record. **Likely:** The roll cap deletes it. Runtime verification required.

**Existing coverage / regression:** Tests cover roll-count pruning and unresolved age retention separately. Add their combination, including active-file and process-prefixed files.

**Narrow repair / downstream impact:** Apply a shared protection-aware deletion policy to every removal path and define what happens if protection exceeds the normal cap. Affects M03 failure diagnosis, M13 activity reconstruction and M15 evidence.

### M02-AUDIT-14 — Store verification can approve missing or wrong payloads and incomplete relationships

**Severity:** High. **Confidence:** High. **Category:** Integrity verification, false-green evidence.

**Canonical requirement:** Artifact availability, ownership, hashes and revision relationships must be verifiable; repair must not hide corruption.

**Code location / implementation:** `Store.verify` checks selected tables, revision presence, top-level artifact-ID existence and lease references. It does not verify every live file's existence/hash/size, artifact job ownership, nested prompt/proposal references, or revision-parent consistency. `artifact_payload` also does not independently verify file bytes. Valid deleted examples are additionally flagged as having no revision. [Store]

**Failure mechanism:** A damaged or removed known WAV is not an unknown orphan, so the verifier can report `ok` despite a false availability claim. Wrong-job references can look structurally present.

**Minimal reproduction:** Create a valid graph, then independently remove or mutate its audio payload without editing the row; replace a nested prompt reference or point an artifact ID at another job. Separately verify a correctly deleted example.

**Expected:** Precise content-free integrity errors, with legitimate tombstones recognized as valid. **Likely:** Some damaged graphs remain green; legitimate deletion produces a false error. Runtime verification required.

**Existing coverage / regression:** Add external byte-level mutations and independent relationship queries. The newer exporter already has a test refusing damaged audio; preserve that stronger guard rather than assuming it exists at the store boundary. [Export tests]

**Narrow repair / downstream impact:** Offer shallow/structural and deep/payload verification explicitly; validate full referenced graphs and lifecycle exceptions. Report, do not fabricate repairs. M03 recovery, M14 replay/export preparation and M15 benchmark acceptance depend on honest verification.

### M02-AUDIT-15 — App shutdown does not drain M02 writers; close APIs have admission races

**Severity:** High. **Confidence:** High for app wiring and admission conditions; timing-dependent failures need reproduction. **Category:** Shutdown, persistence reliability.

**Canonical requirement:** Orderly shutdown must account for accepted evidence/state/event work and must not leave callers waiting or report successful admission after closure.

**Code location / implementation:** App `applicationWillTerminate_` shuts down the model supervisor but does not drain/close the store and event writer. Their workers are daemon threads. Store admission rejects only after stop plus a dead thread, not at the start of closing; event emission lacks an equivalent closed admission guard. Timed close paths can proceed while a worker remains alive. [App] [Store] [Event writer]

**Failure mechanism:** Ordinary quit can terminate accepted queued operations. Racing producers may enqueue after draining begins, or an event may be accepted after closure with no consumer.

**Minimal reproduction:** Hold a writer operation behind a barrier, queue a revision/terminal event, invoke shutdown and attempt one more submission. Exercise emit-after-close and store-close-with-a-stalled-operation separately.

**Expected:** Producers quiesce, admission closes, accepted work is acknowledged or explicitly reported incomplete, then resources close; rejected callers get bounded failure. **Likely:** Lost accepted work, misleading acceptance, or resource closure while work remains. Runtime verification required.

**Existing coverage / regression:** Calling `close()` at the end of successful tests does not cover app termination or racing admission. Add deterministic shutdown protocol tests and a focused native app quit/reopen check.

**Narrow repair / downstream impact:** Explicit open/closing/closed lifecycle, producer shutdown order, bounded drain status and safe unresolved-work recording. Do not close a live worker's database connection. Affects M03 recovery and all durable M02 evidence consumers.

### M02-AUDIT-16 — Legacy “Mark Last Dictation Correct” does not produce retained reviewed evidence

**Severity:** High. **Confidence:** High. **Category:** Retention and downstream semantic compatibility.

**Canonical requirement:** Reviewed/pinned examples are retained until removed; explicit intended-writing judgments have consistent provenance and task meaning.

**Code location / implementation:** Collector `mark_last_correct` writes correctness/provenance but does not transition the example into the retained reviewed lifecycle. It uses `user_explicit`; newer `TrainingDataService.mark_intended` uses `user_explicit_intended_writing`, which the cleanup export consumer explicitly requires. [Collector] [Training inspector] [Exporter]

**Failure mechanism:** A user-marked correct example remains eligible for unreviewed-buffer expiry. It also does not satisfy the same intended-writing provenance predicate as the newer equivalent UI action.

**Minimal reproduction:** Mark via the legacy menu/service, advance beyond the unreviewed period and prune. Compare lifecycle/retention and cleanup-task eligibility with the newer intended-writing action on otherwise equivalent examples.

**Expected:** The explicit action has one documented reviewed meaning and retention behavior, without being mislabeled acoustic truth. **Likely:** Old-menu evidence expires or fails the intended-writing gate despite the visible correct mark. Runtime verification required.

**Existing coverage / regression:** The collector control test checks the immediate correctness value, not later retention or consumer eligibility. Add those assertions with positive comparable examples.

**Narrow repair / downstream impact:** Route both controls through one transactional intended-writing annotation service and reviewed-retention policy. Treat historical provenance conservatively; do not bulk-upgrade ambiguous old labels without evidence. Directly affects M14 curated cleanup data and M15 retained evaluation evidence.

### M02-AUDIT-17 — Collection benchmarks omit observation capture while reporting collection overhead

**Severity:** High. **Confidence:** High. **Category:** Benchmark/test-oracle integrity.

**Canonical requirement:** M02/E19 overhead evidence must exercise the claimed enabled path and positively verify captured inputs/outputs.

**Code location / implementation:** In `scripts/v2/benchmark_m02.py`, collection benchmark contexts are created but not bound through `collector.bind_current(ctx)` before observation callbacks. The observation sink therefore has no current job and ignores prompt/proposal records. The optional real-cleanup timing also does not cover the full final persistence path. [Benchmark] [Collector]

**Failure mechanism:** A run can produce an example with audio/raw/applied pieces, omit the intended model-observation work, and still pass shallow verification while advertising collection cost. No new timing number is asserted here.

**Minimal reproduction:** Run the synthetic benchmark fixture while independently counting prompt/proposal/decision records. Compare a correctly bound positive-control fixture. Inspect the timed region around finalization.

**Expected:** A benchmark refuses to certify the path unless every expected stage population exists, and its timing scope matches its label. **Likely:** Missing prompt/proposal population with a successful report. Runtime verification required.

**Existing coverage / regression:** `verify().ok` cannot replace expected stage-population assertions. Add a test that deliberately disables binding and proves the benchmark fails; count measured operations and distinguish enqueue latency from committed end-to-end cost.

**Narrow repair / downstream impact:** Bind/clear the real context correctly, assert stage populations, state timing scope, and mark affected historical performance claims stale rather than replacing them with fabricated cloud or Mac values. Critical to M15 model/overhead qualification.

## Medium Findings

### M02-AUDIT-18 — Current-version schema repair can conceal missing core relationships

**Severity:** Medium. **Confidence:** High for repair scope; consequences depend on the damaged schema. **Category:** Migration, corruption handling.

**Canonical requirement:** Backup-before-migration and truthful repair; incompatible core data must not be silently reinterpreted as a healthy empty table.

**Code location / implementation:** `_migrate` can reapply `CREATE TABLE IF NOT EXISTS` when an expected table is missing at the current schema version. Core shape validation covers limited columns; current-version repair does not establish complete relationship preservation, full index validation, or an explicit future-version refusal. [Store]

**Failure mechanism:** A populated database that has lost a core table can reopen with an empty replacement while related rows remain. This is concealment of an existing corruption class, not a claim that `CREATE TABLE` itself deleted populated data.

**Minimal reproduction:** Populate examples/revisions/artifacts; remove one core table in a disposable copy while retaining the schema version; reopen. Separately test a missing required index, malformed shape and unsupported newer version.

**Expected:** Backed-up, explicitly diagnosed repair/refusal with no false all-clear. **Likely:** Some cases are repaired structurally without sufficient semantic validation. Runtime verification required.

**Existing coverage / regression:** The empty-database missing-table test cannot prove preservation. Add populated fixtures and verify all relationships independently.

**Narrow repair / downstream impact:** Classify safe additive repairs separately from missing-core corruption; reject unsupported newer schemas; inventory required constraints/indexes. Preserve the original copy. Affects M03 startup and M14/M15 data trust.

### M02-AUDIT-19 — Retention configuration lacks a safe, explicit validation boundary

**Severity:** Medium. **Confidence:** High. **Category:** Reliability, retention policy.

**Canonical requirement:** Retention controls must have explicit interpretation and invalid values must not silently purge data or break ordinary app startup.

**Code location / implementation:** Configuration loading shallow-merges JSON values without validating the retention fields. App construction converts values with `int(...)`; downstream policies use them arithmetically. [Configuration] [App] [Store]

**Failure mechanism:** Null or malformed strings can fail during setup; negatives can make time-based retention immediately eligible; extremely large values can overflow date arithmetic. These are narrower configuration cases, not a claim that default values cause data loss.

**Minimal reproduction:** Temporary configurations with zero, negative, null, malformed-string and very large retention values; inspect load/startup and prune behavior without real user data.

**Expected:** Validated documented semantics, safe rejection or bounded fallback, and an observable policy error. **Likely:** Exceptions or unintended policy behavior. Runtime verification required.

**Existing coverage / regression:** Add table-driven configuration tests and assert no destructive pruning occurs for rejected policy inputs.

**Narrow repair / downstream impact:** One validation/normalization layer, explicit bounds and zero semantics, immutable effective policy revision. Keep persistence failures isolated from dictation where policy permits; do not silently ignore genuine core corruption. Affects M03 availability and M14/M15 retention interpretation.

### M02-AUDIT-20 — Event viewer file ordering does not establish chronological “last N”

**Severity:** Medium. **Confidence:** High for ordering mechanism. **Category:** Diagnostics accuracy.

**Canonical requirement:** Dated event views and “last” selection must faithfully identify recent activity, including rotated files and multiple process streams.

**Code location / implementation:** `scripts/v2/view_events.py` traverses lexically sorted filenames and derives the final selection from that traversal rather than an explicit event-order policy. Numeric suffixes and the active file do not necessarily sort in chronological order. [Event viewer]

**Failure mechanism:** A current active file may be traversed before older rolled files; `.10` and `.2` lexical order is not numeric. “Last N” can display older activity and omit newer events.

**Minimal reproduction:** Create synthetic active and rolled files with hand-written UTC instants/stream identities/sequences, then request the final few events. Include two process streams and a wall-clock rollback case.

**Expected:** A documented ordering policy distinguishing within-stream sequence from cross-stream wall-clock display, with honest ambiguity across clock rollback. **Likely:** Selection follows filename layout rather than actual recency. Runtime verification required.

**Existing coverage / regression:** Human timestamp-format tests do not test merged-view ordering. Add independent expected sequences and non-empty populations.

**Narrow repair / downstream impact:** Parse roll metadata and explicitly order records; do not use a process-local sequence as a global clock. Affects M03 debugging, M13 interpretation and M15 forensic review.

## Low Findings

No separate Low-severity finding is prioritized. Minor formatting or naming issues should not distract from the durability and privacy repairs above.

## Test Gaps

**Race oracles:** Add deterministic barriers for cancellation/completion, retry/late completion, consent transition/publication, annotation/outcome revision, delete/finalize, close/submit, and retention/payload read. Assert the final graph, permitted side effects and rejected operations for both interleavings. Avoid timing-only sleeps as the sole mechanism.

**Crash and disk faults:** Exercise failure before/after payload write, SQL commit, quarantine publication, unlink, import lineage and event emission. Use subprocess termination where a rollback simulation would miss process-exit behavior. No failure may be converted into complete evidence by a blanket exception handler.

**Integrity and privacy:** Independently mutate bytes, hashes, job ownership, parents and nested references; validate physical payload disappearance after deletion; cover unfamiliar event fields; inspect content-free tombstones and retained metadata. WAV checks should include an independent decoder/header/sample-count oracle, not only matching a writer with its paired reader.

**Positive populations:** Every enabled-collection benchmark and acceptance fixture should assert expected audio/raw/prompt/proposal/applied/revision populations. Every disabled-collection fixture should check files as well as rows. Model prerequisites must be explicit skips/pending states, never zero-work passes.

**Native-only checks:** APFS/path/mode behavior, real app shutdown/reopen, precise capture-time consent UI behavior, actual model observation attribution if changed, and physical sleep/wake remain local verification. Preserve already valid historical human checks when the relevant behavior is unchanged.

These gaps are derived from the inspected test bodies and the mechanisms above, not from the absence of a filename in an unreliable search result. [Store tests] [Collector tests] [Event tests] [Import tests] [Live tests]

## Design Concerns

**Pause and revoke semantics:** Decide explicitly whether pause blocks only future captures or all future training writes from in-flight captures. The capture-time revision must remain historically truthful either way. Delete-everywhere requires a stronger no-recreation barrier regardless of pause policy.

**Single writer scope:** A single `Store` instance serializes its own requests. That alone does not prove system-wide single ownership when the running app and an import/verification CLI open the same database. Portable multi-process behavior, migration coordination and timeout semantics need measurement and documentation; no enterprise broker is called for.

**Durability and cancellation:** Record effective journal mode, synchronous setting, foreign-key enforcement and busy timeout. A waited call timing out is not equivalent to cancelling its queued mutation. Specify whether late completion is allowed and how the caller discovers it, particularly for privacy actions.

**Orphan policy:** A wall-clock grace period is not an ownership token. Slow staged writes, clock changes and processes reopening the same artifact directory deserve targeted tests. Quarantine is an inspection/recovery policy; it cannot substitute for a required deletion.

**Unresolved meaning:** Confirm how `failed_recoverable` interacts with unresolved-job retention. Being a terminal attempt outcome does not necessarily mean the user's recoverable writing is disposable. This report does not independently re-audit M03 recovery.

**Required metadata:** Audit event parent linkage and missing source/model/config revision fields against the declared schema with explicit null/reason rules. Do not backfill missing historical values by guessing a current build or current model.

These are bounded follow-up questions for the M02 remediation and compatibility checks. They are not automatic mandates to change unrelated milestones.

## Areas Verified Strong

“Verified” here means supported by the inspected implementation and/or independent test assertions, **not rerun on the reference Mac**.

1. **M01 ancestry and import semantics:** accepted repaired main is the foundation; exact-text and all-prefix/old-partial behavior has dedicated hand-written regression oracles. [M01 boundary tests]
2. **Connection-level composite operations:** the store already offers the mechanism needed for narrow atomic repairs, and several domain operations use it rather than nesting writer requests. [Store] [Training inspector]
3. **Default-off collection:** absent consent does not silently opt the user in; ordinary history and training collection have distinct branches. [Collector] [App]
4. **Observation ownership in the current coordinator:** bind/clear behavior addresses the historical cross-job observer case; `_current` is not automatically a new cross-job defect merely because it is an attribute. [App] [Collector tests]
5. **Actual input capture and honest outcomes:** rendered prompt/proposal artifacts, separate applied output, fallback lineage and posted-versus-confirmed outcome distinctions are present. [Collector] [Cleanup hook]
6. **Original microphone representation:** the recorder uses mono float32 and sample-derived duration; M02 should preserve this without claiming that its PCM16 debug copy is the original evidence. [Audio hook]
7. **Logging positive oracles:** the concurrent emitter test asserts a real event population and unique ordered sequence/IDs; disk-recovery testing checks that an actual critical marker survives after recovery. [Event tests]
8. **Independent downstream guard:** the inspected export safety test corrupts audio bytes and expects export refusal. M02's weaker verifier should not be confused with an absence of all downstream integrity protection. [Export tests]

## Adversarial Reproduction Plan

All fixtures must use synthetic content, temporary directories and a disposable database. No source-data mutation, live Application Support import, user-file deletion or actual secret is required.

| Priority | Corpus / fault | Findings | Independent assertion |
|---|---|---|---|
| P0 | Delete before first example, during staging, before late outcome | 01 | No new live payload/example/revision after the tombstone boundary |
| P0 | Unlink failure + restart + debug-copy inventory | 02 | Remaining bytes explicitly pending, then physically absent after retry |
| P0 | Known-secret finalize with a fault before state change | 03 | No visible ordinary-state publication |
| P0 | Purge followed by transaction rollback / process exit | 04 | No live row pointing at a silently removed file |
| P0 | Artifact insert failure with later writes allowed | 05 | Ordinary text succeeds; evidence is not marked complete |
| P0 | Capture-time consent toggles and state/revision interleave | 06 | Permission and provenance match the actual capture boundary |
| P1 | History 90d / training 30d, pins, recovery, delete override | 07, 16 | Each independent retention interest obeyed |
| P1 | Outcome read → human annotation → outcome append | 08 | Latest annotation retained; actual parent preserved |
| P1 | Automatic retry and late old-attempt result | 09 | Coherent stage/job/context identity; stale update rejected |
| P1 | Pair commit → interruption → append → rerun | 10 | One logical pair per source occurrence, exact text retained |
| P1 | Stats ID conflict and failed insert / successful bookkeeping | 11 | No silent source loss and no false imported marker |
| P1 | Unknown/nested private event values | 12 | Marker absent; safe useful fields remain |
| P1 | Unresolved marker + more than eight size rolls | 13 | Protected evidence remains reachable |
| P1 | Missing/mutated WAV, wrong-job reference, valid tombstone | 14 | Honest deep verification; legitimate deletion accepted |
| P1 | Quit/close under backlog and concurrent submission | 15 | Every accepted operation accounted for; late admission refused |
| P1 | Deliberately unbound benchmark observer | 17 | Benchmark fails instead of issuing a valid overhead report |
| P2 | Populated schema corruption / missing index / newer version | 18 | Backup and explicit repair/refusal, no false healthy empty core |
| P2 | Invalid retention values | 19 | No destructive or startup-surprising interpretation |
| P2 | Active/rolled/process streams with independent timestamps | 20 | Correct declared view ordering |

Portable tests should capture command, interpreter, code SHA, exit code, expected/actual populations and content-free diagnostics. A failure to reproduce must result in a refuted or narrowed disposition, not a repair justified solely by this report.

## Downstream Impact

| Consumer | M02 boundary it relies on | Compatibility focus—not a new audit |
|---|---|---|
| M03 | Job attempt transitions, durable artifacts, shutdown/recovery truth | Retry identity; pending deletion; missing payload; old/new boot distinction |
| M08 | Outcome revisions and delayed observations | Correct parent; preserved annotation; no writes after deletion; terminal-event correspondence |
| M13 | Stable activity/import identity and dated events | No duplicate interrupted imports; truthful stats conflicts; ordering and clock semantics |
| M14 | Consent, lifecycle, annotations, retention and deletion | Quarantine from first visibility; reviewed retention; independent leases; delete barrier; preserved exporter integrity checks |
| M15 | Provenance, retained dataset and performance evidence | Committed completeness; exact attempt/model inputs; repaired benchmark population/timing oracles |

There is no recommendation to restart M03, redo M07/M11, change model choice, or broaden the scope into a full M14 audit.

## Recommended Repair Order

**First: privacy and publication invariants.** Reproduce 01–06. Establish the job deletion/permission boundary, durable purge intent, and atomic example publication with first-visible quarantine state. Agree on operation acknowledgment before layering more callbacks onto it.

**Second: lifecycle and lineage.** Repair 07–09, 15 and 16. Centralize retention-interest evaluation, transactional revision updates and retry identity; give shutdown a bounded admission/drain protocol.

**Third: durable import and verifier truth.** Repair 10–11, 14 and 18, preserving all accepted M01 behavior. Use populated damaged fixtures and interrupted growing sources.

**Fourth: diagnostic privacy and evidence quality.** Repair 12–13, 17, 19–20. Fix export allowlisting, protection-aware roll retention, benchmark population/timing scope and explicit configuration/view semantics. A cheap redaction fix may be committed earlier, but it does not resolve the deeper publication defects.

Run affected M01 compatibility tests throughout, then all portable M02 tests and targeted downstream interface tests. Keep production fixes, evidence updates and human verification statuses distinguishable.

## M02 Readiness Verdict

**C — Significant persistence/evidence weaknesses.**

M02 is not a failed architecture, and the evidence does not justify rewriting the product. It needs targeted foundational repairs because some operations can look successful while violating the promised durable graph, consent provenance, retention interest or deletion boundary.

The strongest basis for this verdict is the directly visible transaction/lifecycle behavior: no job-level post-deletion guard, suppressed physical-delete failure, pre-commit unlink, split quarantine publication, asynchronous saved signaling, and unconditional cross-holder lease revocation. The benchmark's missing observer binding also weakens the existing performance evidence independently of native model quality.

This is an actionable static verdict, not native certification. The cloud session must reproduce or refute each finding, repair confirmed defects narrowly, preserve historical human evidence honestly, and append only justified local checks to the existing verification runbook. Pending native checks do not by themselves block the next read-only milestone audit unless they make its inherited static foundation invalid.

---

## Commit-pinned source references

All links below refer to the audited commit, not a moving branch. Ancestry was checked through the connected GitHub branch/commit/tree responses.

[Milestones]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/LOCALFLOW_V2_MILESTONES.md
[Specification]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/LOCALFLOW_V2_SPEC.md
[Training contract]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/contracts/training_evidence.md
[Jobs contract]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/contracts/jobs.md
[Events contract]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/contracts/events.md
[M01 handoff]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/handoffs/M01.md
[M01 acceptance]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/acceptance/M01/results.json
[M02 handoff]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/handoffs/M02.md
[M02 acceptance]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/docs/v2/acceptance/M02/results.json
[M01 boundary tests]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/tests/v2/test_legacy_import_boundary.py
[Store]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/v2/store.py
[Collector]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/v2/training.py
[Event writer]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/v2/eventlog.py
[Importer]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/v2/importer.py
[App]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/app.py
[Cleanup hook]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/cleanup.py
[Audio hook]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/audio.py
[Configuration]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/config.py
[Event viewer]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/scripts/v2/view_events.py
[Benchmark]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/scripts/v2/benchmark_m02.py
[Training inspector]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/v2/training_data.py
[Exporter]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/localflow/v2/curation/export.py
[Store tests]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/tests/v2/storage/test_store.py
[Event tests]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/tests/v2/logging/test_event_writer.py
[Import tests]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/tests/v2/storage/test_import.py
[Collector tests]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/tests/v2/training/test_collector.py
[Live tests]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/tests/v2/training/test_live_pipeline.py
[Export tests]: https://github.com/scalinity/LocalFlow/blob/3ae0070d84730f8d750440f51097c4a53ff8bf02/tests/v2/training/test_dataset_export.py
