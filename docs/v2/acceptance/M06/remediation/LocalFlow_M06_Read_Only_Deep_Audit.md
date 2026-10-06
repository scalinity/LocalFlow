# LocalFlow V2 — M06 Read-Only Deep Audit
## Local Context Snapshots and Destination Awareness

**Repository:** `scalinity/LocalFlow`  
**Audited canonical main:** `6a083bd70011988314836164e7d3016da3968490`  
**Audit type:** read-only, source-derived retrospective review  
**Readiness verdict:** **C. Significant context/privacy/lifecycle weaknesses**  
**Repository writes / production tests / native trials / model inference performed by this audit:** **none**  
**Delivered adversarial corpus:** **101 cases, all NOT_RUN**

Companion deliverables: `LocalFlow_M06_Adversarial_Corpus.json` and `LocalFlow_M06_Claude_Code_LOCAL_Remediation_Handoff.md`. The appendix links every repository source to the audited SHA. Finding reproductions are designed counterexamples and local verification obligations, not executed results.


## Executive Assessment

The accepted M01–M05 foundation is present and the final main recheck is unchanged. M06 nevertheless needs substantive, bounded repairs before its current privacy, identity and deadline claims can be accepted. The principal problem is not missing functionality: it is that the collection’s authority can outlive or differ from the actual focused AX objects being read. A captured allowed app can authorize another destination’s reads after focus changes, and separately re-fetched field/window/origin objects can form a hybrid snapshot. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py)

The other major concerns are equal-title cache reuse, missing/conflicting identity accepted as equality, shallow immutability, revocable provider ownership, unbounded selected-text retention, and unmeasured synchronous release work. Several native AX bridge assumptions remain unqualified. There are **25 findings: 1 Critical, 8 High, 7 Medium, 5 Test Gaps and 4 Design Concerns; no Low findings**. Design concerns are decisions to adjudicate, not instructions to patch blindly. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

Important protections must survive remediation: stable secure-field classify-before-read; explicit denied-provider gates and composition hard-null; target-ID refusal against a foreign active collection; own-handle downstream lookup; current frozen-entry M05 scope rebuilding; content-free normal context envelopes/events; independent retention-off behavior; and the accepted M02 deleted-job publication barrier. These are source-supported strengths, not a statement that all adversarial schedules pass. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S07](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py)

**This audit did not execute the repository tests, benchmark, native APIs, corpus, mutations or Daniel’s local verification.** Static counterexamples are identified as such; current reference-Mac performance remains unknown. The local handoff starts with safe synchronization, reproduces allegations on the inherited base, and requires an independent review of a frozen first pass.


## Audit Boundary

> This audit covers committed GitHub state at `6a083bd70011988314836164e7d3016da3968490`. Any uncommitted local state is outside the GPT-6 audit boundary.

GitHub was read only. No branch, commit, issue, pull request, source modification or remediation was made. The report and corpus are newly authored conversation artifacts, not repository edits. M01–M05 and previously audited M07/M11 were not re-audited; later systems were read only at M06-owned input/identity/evidence seams. M15 was not begun.

The attached audit brief supplied the scope and local-era requirements. Current repository files, not historical acceptance alone, supplied implementation facts. Evidence classes throughout this report are **source-established behavior**, **static counterexample**, **historical recorded result**, **test gap**, **design decision**, and **native/runtime NOT_RUN**. A static counterexample is not a measured incident in Daniel’s usage.

Known current app, collector, provider, snapshot, insertion-validation, evidence and capability paths were inspected directly. GitHub code search for an M06 identifier returned `incomplete_results: true` with no indexed hits. Therefore an exhaustive repository-wide caller inventory is **not certified**; local `rg` is explicitly required before edits. A zero-result incomplete index was never treated as proof of absence. Native permissions, actual app surfaces, process incarnation, model caches, current installed app and local dirty state are outside this audit.


## M01–M05 Remediated Main Baseline

Current remote `main` was resolved before substantive review and rechecked at the end: `6a083bd70011988314836164e7d3016da3968490` both times. Recent ancestry and the accepted remediation markers were inspected through GitHub. The foundation gate passes.

| Accepted component | Commit inherited by audited main |
|---|---|
| M01 final production repair | `3db74061f23001b9cce3d4fe029e0b30cbc295d6` |
| M02 final production repair | `bfbc63c35efa6273cc13242d54d3e5bbe264b21e` |
| M03 final production repair | `3e0d1ab972b866b4acbda622984bce04e8f95093` |
| M04 final production repair | `4ef219c52598e92a9857e9e0dec13ca7143f56dc` |
| M05 final production repair | `01a1f3c07ed3270aa1e7b3da39d89c453c84c1e8` |
| M05 final tests | `4adda7ddff8acd2510bb6057c1df4d466d3cbf81` |
| M05 evidence/documentation; audited main | `6a083bd70011988314836164e7d3016da3968490` |

The ancestry is consistent with the actual remediation addenda, and `docs/v2/VERIFICATION.html` contains M01–M05 sections. Their historical/pending local checks were not reclassified as passed. M05’s production SHA and later test/documentation heads are kept distinct. [S32](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M01.md) [S33](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M02.md) [S34](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M03.md) [S35](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M04.md) [S36](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M05.md) [S37](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/VERIFICATION.html)

Branch evidence: [pinned audited commit](https://github.com/scalinity/LocalFlow/commit/6a083bd70011988314836164e7d3016da3968490); [M01-to-audited-main comparison](https://github.com/scalinity/LocalFlow/compare/3db74061f23001b9cce3d4fe029e0b30cbc295d6...6a083bd70011988314836164e7d3016da3968490). These links are reference points, not instructions to move the local checkout destructively.


## M06 Responsibilities

M06 owns inexpensive PTT-time app identity, asynchronous local field/origin/workspace collection, bounded release finalization, destination-derived M05/M04 inputs, pre-decode context identity, distinct late context and governed retention. Its own code must not crawl the filesystem, interpret context as executable instructions, or qualify unsupported ASR biasing. Downstream insertion/cleanup/learning mechanics remain owned by their respective milestones. [S01](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/context.md) [S15](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_MILESTONES.md) [S16](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_SPEC.md) [S42](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/__init__.py)

Core invariants: classify and deny before content access; bind every accepted value to the destination/job that owns it; keep pre-decode bytes stable; make provider lifecycle, absence and deadline truthful; bound total release contribution; preserve captured dictionary/rule state while gaining destination scope; and make deletion/retention authoritative at every publication. These invariants are the basis of the findings, not an expansion into another milestone.


## Current Context Architecture

```text
PTT-down main-thread capture setup
  → visible overlay
  → NSWorkspace target identity (no M06 AX call)
  → begin() stores global _active and returns job.context_coll
  → background collection:
       one frontmost drift check
       focused field → separate focused window/title lookup
       → cached/live origin → workspace
release path, before ASR queue
  → finalize() chooses _active; optional target-ID refusal
  → compose pre_decode snapshot
  → M10 captured-rule re-resolution
  → M05 scope rebuild FROM CAPTURED ENTRIES, policy/context/hints
  → M10 authorized workspace/skill/file-resolution finalization
  → pre-decode hint/context/profile evidence packaging
  → released_mono assigned HERE (too late)
  → ASR queue / normalization / current permitted cleanup context
  → one app-level take_downstream(job.context_coll) pickup
  → separately recorded downstream evidence
```

This is the inspected production path, not the cleaner historical “all context is future work” description. The collection handle routes late results by job, but finalize still selects global `_active`. There are no futures in this implementation: `_Collection` owns a daemon thread, dictionaries, a completion Event and a lock. [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

Known interface graph: `TargetSnapshot.to_scope_context` → M05 app-only scope; finalized `ContextSnapshot.to_scope_context` → M05 and M10; `to_engine_context` → M04 identifiers/path flags; `context_snapshot_id` → qualified ASR request extension and evidence; `same_destination` → M08 validation; `on_context_snapshot` → M02 governed storage → M09/M14 evidence consumers. The current app’s other constructors/selection paths must appear in the local complete symbol inventory; this report does not claim that the incomplete GitHub index enumerated all of them. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S20](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/validation.py) [S26](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/capabilities.py)


## Historical M06 Review Findings Considered

The denied-browser repair is still present: all provider entry points receive a denied gate, and composition hard-nulls denied values. The residual issue is **when and to which object** that captured gate applies: focus can change after the one initial check (AUDIT-01). The historical fix must be preserved, not reverted or described as absent. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S13](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M06.md) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json)

The historical global late-context bug was partly repaired: job handles exist, downstream lookup takes that handle, target-ID mismatch refuses foreign active finalization, and failed-identity startup calls abandon. Residuals are finalize’s global selection/concurrent idempotence, non-revoking abandon and a downstream buffer that can refill after pickup (AUDIT-06/11/12). [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

Other historical improvements also remain: separate provider exception/deadline tokens, frozen-entry scope upgrades, HTTP-versus-file workspace gating, lowercase filename/version title negatives and changed-title cache invalidation. Their limits are examined rather than assumed fixed universally. The old “no context reaches any model prompt today” sentence is historical: current M07 intentionally accepts narrow permitted vocabulary/profile inputs. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S13](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M06.md) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json) [S23](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/cleanup.md)


## Target Identity Assessment

The PTT snapshot has an opaque target UUID, app bundle/name/PID, category, denied flag and capture time. It has no native window/field/process-incarnation token; the later snapshot supplies a window **title**, not a unique object identity. Necessary app identity for a denied-app decision is not a privacy violation. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py)

`same_destination` accepts equal PIDs before checking a contradictory bundle and falls back to bundle equality, including absent/absent identity. This is AUDIT-03. Same-title windows, same-role fields and browser tabs remain a separate authority-granularity decision (AUDIT-25); a moved caret is deliberately allowed by current insertion policy. Random `tgt`/`ctx` UUIDs are observation IDs, not content hashes. Different equivalent captures having different UUIDs is not a hashing defect. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S19](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/insertion.md) [S20](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/validation.py)

No M06 AX work precedes the overlay in the inspected path. However a blanket claim that the whole hotkey path has no pre-overlay I/O would be inaccurate: existing capture/job/journal setup is outside the M06 hook. Post-overlay M05/M10 work should be measured as needed, not relabeled invisible-feedback purity or used to reopen M03. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)


## Sensitive-Field / Denied-App Privacy Assessment

For a stable field, `read_field` queries role/subrole and returns for secure or non-text classifications before placeholder, selection, range, document and nearby reads. Denied providers return before AX access, including the browser-origin provider. This is an important verified ordering strength. The critical gap is the captured decision’s ownership across later system-focused lookups, not an allegation that the normal secure branch first reads AXValue and then discards it. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py)

Unknown/missing role and failed subrole need explicit distinction. `SystemAXHost.attribute` erases native error codes into None; a supported text role with an unreadable subrole can look like an ordinary field with no subrole. Real custom-password/control behavior is not certified here. Secure/unclassifiable **field content** and independent window/origin metadata are not interchangeable policy categories; current tests allow some metadata. AUDIT-22 requires adjudication rather than a blanket new privacy rule. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

Normal envelopes include IDs, counts, flags and controlled provider/omission fields rather than raw text/origin/path/title. Normal M06 failure events use exception type names, not exception messages. Full snapshot JSON is content-bearing and belongs only in a governed artifact. Nested mutability can weaken those assumptions, so value-object/allowlist tests remain necessary. Selected-text retention has no explicit cap (AUDIT-09); credentials in URL userinfo are not stripped by origin construction (AUDIT-14). [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py)


## Provider / Collector Lifecycle Assessment

The collector uses one daemon thread per begin; providers execute sequentially. Per-call native timeout does not cancel a thread, cap outstanding collections or bound the aggregate sequence. `abandon` drops `_active` only. No M06 per-handle cancellation/closed admission is wired into the inspected app cancellation/deletion/quit paths. A retained handle can still accept/read late results (AUDIT-06). [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

Finalize first checks its snapshot under the collection lock, waits outside it, then composes under the lock without repeating the snapshot check. Two callers can publish distinct IDs; a new begin changes which global handle an older finalize can reach (AUDIT-11). Current UI serialization narrows live reachability and is not ignored in severity. `take_downstream` clears, rather than seals, the late buffer (AUDIT-12). [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

**Lock-order inspection:** `_active_lock` protects pointer/cache access; collection `lock` protects result routing/composition; host `_system_lock` protects lazy AX-system-element construction. Most AX content calls occur outside collector locks. No definite current lock-order cycle was established. External emission while holding `_active_lock`, future cancellation hooks, and composition work inside the collection lock are boundaries to test. The repair must not add store calls or waits under deletion-listener/collector locks. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S07](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py)

Native timeout clarification: Apple documents that setting the timeout on a system-wide AX element sets the process-wide default. Therefore the absence of a separate setter on every returned window object does **not** prove those calls are unbounded. The actual gaps are unchecked configuration results, native error fidelity and total lifetime/budget—not a fabricated timeout-inheritance bug. [Apple AXUIElementSetMessagingTimeout](https://developer.apple.com/documentation/applicationservices/1459345-axuielementsetmessagingtimeout).


## Deadline / Release-Path Assessment

Three distinct quantities must remain separate: (1) provider wait requested at finalize, (2) complete collector finalize including locks/composition/cache/event work, and (3) additional post-release context/scope/policy/packaging cost before ASR, plus the full release-to-insertion measurement. A 75 ms Event wait does not establish the third. The M06 milestone’s additional post-release target must not be silently redefined as provider waiting only. [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S15](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_MILESTONES.md) [S17](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md)

The synchronous path can rebuild a 10k-entry scoped vocabulary, select hints and serialize them after release. M10 adds its own authorized destination-dependent work. The parent `released_mono` timestamp is written after this work, so an end-to-end metric based on it excludes that contribution. AUDIT-07 is both a performance risk and a definite observational-boundary defect. Real Mac magnitude remains NOT_RUN. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S11](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m05.py) [S12](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M05/remediation/benchmark_cloud_01a1f3c.json)

A safe fix can precompute immutable projections during recording or cache by captured state plus valid destination identity; it cannot read a changed live dictionary to save work or silently omit required output/validation. Any safe scope downgrade must be explicit and coherent. The benchmark must demonstrate the injected-delay conservation relation before its numbers govern acceptance.


## Cache / Destination-Drift Assessment

The cache is a single metadata slot, not an unbounded map. Its `(PID, title, role)` key has no TTL, document locator, actual window/field token, tab generation or sensitivity state. A current field with the same tuple can be paired with a stale origin/workspace. When native title lookup is unavailable, a shared None makes the cache particularly weak. Changed-title tests do not prove equal-title or absent-title safety. [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

A cache hit also reconstructs a ProviderResult without preserving omission status. A previously absent/deadline/permission value can become `status=ok` while remaining None. The direct deny gate prevents a captured-denied snapshot from taking the cache; this is not a generalized claim that denied snapshots already reuse cached content. Secure transitions and mid-provider drift require their own ownership/privacy tests. [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py)

There is one initial drift check and it proceeds when live identity is unavailable. Window and origin stages re-fetch focused objects independently. Validate ownership at each content source and cache use, not just at the beginning or final artifact write. Cache refresh from an old handle must also respect current ownership and revocation. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py)


## Browser-Origin / Workspace Assessment

Direct origin construction strips path/query/fragment but reconstructs scheme plus `netloc`, which can retain userinfo and invalid/non-web authority forms. Title inference rejects familiar lowercase filenames and numeric versions, but an uppercase extension bypass and email-substring match remain. Direct localhost/IP origins and title guesses are different cases; no public-suffix lookup or external navigation should be introduced into this local collector merely to strengthen a heuristic. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

Workspace inference only accepts `file://` or scheme-less absolute paths before deriving a directory display name; HTTP URLs are not treated as local workspaces. M06 uses strings and contains no filesystem crawler in the inspected package. Percent-encoding, remote-authority file URLs and equal directory names at different paths need explicit opaque-name policy, not accidental normalization. M10’s separately authorized manifest/listing behavior means the **connected app** is not globally filesystem-free. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md) [S30](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/config.py)

Provenance marks `ax_url`, `document` or `window_title`, but conversion to ScopeContext drops source quality. Whether heuristic/display-name observations can grant site/workspace rules is AUDIT-23. M05’s repaired comparison canonicalization must be preserved rather than compensated for with unrelated M06 value rewriting. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md)


## M05 Scope-Upgrade Compatibility

The main positive seam is intact: `_finalize_job_context` rebuilds `VocabularySnapshot` from **the job’s captured entries**, not a fresh store snapshot. The repaired selector can fail independently: successful effective-scope upgrade remains, and the stale narrower hint set is cleared rather than reused. M05 canonicalizes site comparisons and compares bundle IDs case-insensitively while M06 retains exact values/provenance. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md) [S36](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M05.md)

Weaknesses are destination authenticity/cache freshness before scope formation, synchronous cold rebuilding, and partly transactional failure handling. M06 field/identifier attachment returns early if vocabulary is absent, despite those fields being independently available. Assignments occur before some upgrade failures; the later M10 finalizer can narrow the ultimate effect, so both must be included in the reproduction. Do not turn a helper-only observation into an unverified whole-pipeline failure. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

Tests must use real competing approved rules and distinct captured/future entries. Merely asserting that an object exists, that a scope string changed, or that a dictionary remained nonempty is not proof of effective membership or frozen state. The current M05 10k packaging cohort is directly relevant to M06 and should be remeasured on the Mac; unrelated M05 native backlog remains untouched. [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S11](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m05.py) [S12](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M05/remediation/benchmark_cloud_01a1f3c.json)


## M07 Permitted-Context Boundary

The inspected current app does not directly pass raw nearby text, selected text, origin, document or workspace into cleanup prompts. It does pass the normalized transcript, protections, a bounded approved-vocabulary list and destination/profile information under the current M07 contract; alias pairs are validator-only rather than model instructions. M06 can therefore steer output indirectly through normalization and approved scope even without raw neighboring text in a prompt. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S23](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/cleanup.md)

The historical hostile test’s transcript comparison is useful but insufficient for the modern full request. AUDIT-19 requires a request-shape/canary oracle with positive permitted terms/profile, not a prohibition on all context. No semantic-fidelity re-audit or model prompt-injection success is claimed. Late-only context must remain distinct from original hint evidence; current inspected code uses the pre-decode ID for the qualified request extension. [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S23](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/cleanup.md) [S26](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/capabilities.py)


## M08 same_destination Boundary

M08 is not relying on the name `same_destination` to imply a unique field. Its contract explicitly adds conditional window-title equality, role comparison and exact **nonempty** selection matching to the PID/bundle identity row. Missing field data can degrade to identity-only checks; moving a caret is deliberately not a target change. This narrows, but does not eliminate, same-title/same-role collisions. [S19](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/insertion.md) [S20](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/validation.py)

AUDIT-03 addresses objectively missing or contradictory identity accepted by the M06 hook. AUDIT-25 asks what stronger destination distinctions the product must enforce. Native range/window provenance from M06 also affects that consumer. Repairs should change only M06 identity and necessary consumer expectations; clipboard mechanics, insertion transactions and unrelated M08 behavior are outside scope. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S20](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/validation.py) [S21](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/hosts.py)


## Pre-Decode / Downstream Revision Assessment

The ordinary collector creates a distinct context ID for a late snapshot and does not append late provider data into the original object. Original and downstream occupy separate evidence fields. These are genuine strengths. However nested dictionaries remain mutable under the original ID, and concurrent finalize can create multiple original snapshots (AUDIT-05/11). [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py)

A downstream snapshot is a late-provider delta, not a merged complete destination. Nonmembers are `not_in_revision`; linkage currently depends on the shared target/job envelope rather than an explicit parent-context field. Clear-then-refill permits multiple pickups, while the production app’s one pickup can miss providers that finish later. Late field dependencies read the pre-decode bucket and can lose the late document’s workspace contribution (AUDIT-12/24). [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

The current production ASR manifest remains unqualified for contextual biasing. `asr_hint_request_fields` returns None unless exact adapter/checkpoint/runtime qualification is demonstrated; the context ID used at that seam is the pre-decode snapshot, not a late revision. No acoustic qualification or model-backed result was attempted. [S26](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/capabilities.py) [S27](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/asr_hints.md)


## Evidence / Retention / Deletion Assessment

`training_retain_context=false` independently suppresses both original and downstream M06 context payloads, while permitted in-memory use can continue. It does not mean every other dictionary/profile/evidence family is globally disabled. The content-free destination block marks non-retention and missing payloads. The old outer `consent_disabled` mapping alongside a precise destination-level reason is a compatibility choice that can be confusing, not itself a new leak. [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S25](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md) [S30](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/config.py)

The frozen envelope vocabulary already includes **`retention_write_failed`** from M04 remediation. Do not propose “adding a seventh reason” as though it had not happened. Historical six-value comments and current producer-specific meaning should be reconciled additively rather than casually replacing all reasons. Context artifact/lease write acknowledgment still needs the precise AUDIT-15 consistency test. [S25](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md) [S28](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/artifacts.md) [S29](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/normalization.md)

Accepted M02 publication checks traverse nested artifact references, refuse deleted jobs and null references to uncommitted artifacts; deletion overrides leases/immutability. Thus a broad allegation of late context resurrecting a deleted job is **not established**. M06 must still revoke its in-memory handle and prove its producer sequence against that barrier. Optimistic `retained=true` can be inconsistent with later reference sanitization even when the barrier correctly protects durable state. [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S07](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py) [S33](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M02.md)

Automatic worker retry keeps the current job’s captured state; explicit retained-audio/recovery retry uses the accepted unscoped default rather than silently attaching today’s destination as original. M14 does not gain permission to regenerate original context after an answer or later correction. Full current retry/profile matrices remain NOT_RUN under AUDIT-20. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S25](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md) [S35](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M04.md) [S36](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M05.md)


## Test-Oracle Assessment

The two M06 test files were read for what they assert. Historical counts (27 snapshot tests and 12 pipeline tests in the September 22 record) are not reported as executed here. They contain real protections: stable zero-read secure/denied tests, target-change-before-collection refusal, ordinary late non-growth, retention round-trip/off, frozen-entry scope and honest unqualified ASR fields. [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json)

Their gaps are independent AX-object ownership between providers; equal/null-title cache keys; every prohibited attribute; real AXValue and UTF-16 handling; per-handle cancellation; concurrent finalize; late completion between pickups; writer/lease failure paired with retained flags; M10’s second finalizer; and whole-request permitted-context inspection. Several schedules use sleeps instead of forcing the exact interleaving, and positive provider/scope populations are not always strong enough to exclude no-op work. [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py)

The corpus and mutation plan are **test specifications**, not an executed runner or a passing report. Local results must report control passes, mutant kills, invalid harness runs, skipped/native-manual cases and family-level outcomes separately. An invalid/no-op control makes a mutant “kill” uninformative. Native success cannot be established through declared non-native shims.


## Performance / Benchmark Assessment

| Evidence | Boundary / workload | Reported number | Valid interpretation |
|---|---|---:|---|
| Historical M06, Sept 22 | Synthetic fast collector finalize | p95 0.303 ms | Old code/fixtures, not current native AX performance |
| Historical M06, Sept 22 | Synthetic slow-provider cutoff | max 80.399 ms | Requested 75 ms plus observed scheduling/composition; not total release budget |
| Historical M06, Sept 22 | Old cold 10k scope workload | 62.193 ms | Different earlier implementation/workload |
| Historical M06, Sept 22 | Its pipeline delta | 0.424 ms | Cannot certify current incremental release cost; harness boundary/control defects |
| Final M05 production, cloud Linux x86_64 | 10k captured-entry rebuild + selection + disposition/request + JSON packaging | p50 351.994; p95/p99 363.568 ms | Relevant current algorithmic contribution, **not reference-Mac latency** |
| Current M06 on Daniel’s Mac | Actual release → context/scope → ASR handoff | **NOT_RUN** | Required local measurement |

Sources for every recorded figure: [S12](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M05/remediation/benchmark_cloud_01a1f3c.json) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json)

M05’s report transparently marks the 75 ms comparison `within_bound=false`, `gated=false`; its overall pass refers to its separately gated 25 ms cohorts. It is not a false claim that this scope cohort passed 75 ms. Its observed fresh selection p95 19.372 ms, fresh scoped selection 13.292 ms and positive normalization 12.746 ms do not replace the combined 363.568 ms cost. [S11](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m05.py) [S12](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M05/remediation/benchmark_cloud_01a1f3c.json)

M06’s harness has a stronger validity problem: the off arm installs an enabled collector, its timed pipeline starts after `press_release`, its “warm scope” measurement compares tuples, and its global-only entries do not prove changed scope eligibility. Correct that before accepting any new latency claim. Positive work validity and exit-driving bounds are separate gates. The Mac run must be isolated from concurrent sweeps and state SHA, machine, interpreter, provider/entry populations, warm/cold state, p50/p95/p99 and exact timer boundaries. [S10](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m06.py) [S11](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m05.py) [S17](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md)


## Critical Findings

### M06-AUDIT-01 — The captured allow/deny decision is not bound to the AX objects subsequently read

**Severity:** CRITICAL · **Confidence:** High — static control-flow counterexample; no native reproduction claimed  
**Category:** Privacy / destination ownership · **Execution:** NOT_RUN

**Canonical requirement.** S12 classify/deny before content read; M06-AC01/AC03; the captured destination must own every content-bearing result.

**Code location.** collector.py: ContextCollector._collect and _destination_changed; providers.py: read_field and read_site_origin.

**Current behavior.** The collector checks frontmost identity once, then read_field obtains the system focused element. Window/title collection obtains it again, and the origin provider obtains it yet again. The deny decision remains the original TargetSnapshot.denied boolean. An unavailable frontmost result explicitly permits collection to proceed.

**Failure mechanism.** Focus can change after the initial comparison and before any later lookup. An allowed target A can therefore authorize reads from denied app B; later stages can also combine A field text with B title/origin. No AX-object PID or per-destination generation binds these reads. A post-read discard would not satisfy the privacy requirement.

**Minimal reproduction (NOT_RUN).** Use a latch after _destination_changed returns false. Capture allowed A, then switch the scripted frontmost and AX focus to denied B containing CANARY_DENIED_B. Release the latch. A second variant switches from A to B after the field provider, before window/origin collection. Assert all reads and the assembled fields, not only final output.

**Expected behavior.** No B content attribute is fetched under A authority. Unverifiable ownership yields a content-free omission. A snapshot cannot silently mix independently focused destinations.

**Likely actual behavior / verification boundary.** Statically, read_field receives denied=False and fetches B content while the snapshot retains target A. The mid-provider variant can carry A field data plus B origin/title. Exact macOS scheduling/exposure remains a local-native check.

**Existing coverage.** Denied-browser tests cover a destination denied at capture; the drift test changes destination before collection starts.

**Why the oracle misses it.** There is no barrier between the initial identity check and a focused-element lookup, and no mixed-provider ownership oracle.

**Regression recommendation.** Instrument every prohibited attribute, tag every AX object with an owning app/window/field generation, and run switches at each read boundary. Add a scope contender so wrong origin demonstrably chooses the wrong approved rule, using a scripted ASR result.

**Narrow repair direction.** Collect from a job-owned, identity-validated AX target rather than repeated global focus lookups. Check deny/sensitivity before content access, refuse missing/conflicting ownership, and revalidate before accepting provider values. Document the limits of non-atomic external AX state; do not claim a post-read scrub prevents a read.

**Downstream impact.** M05 wrong scope and M10 wrong style can steer normalization and M07 permitted context; M08 and M14 receive falsely attributed destination evidence. This is an M06 repair, not a new M07/M08 audit.

**Pinned evidence.** [S01](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/context.md) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

**Corpus mapping.** `LF-M06-C001`, `LF-M06-C002`, `LF-M06-C003`, `LF-M06-C004`, `LF-M06-C005`, `LF-M06-C006`, `LF-M06-D001`, `LF-M06-D002`, `LF-M06-D003`, `LF-M06-D004`, `LF-M06-D005`, `LF-M06-S001`, `LF-M06-S006`, `LF-M06-N005`


## High Findings

### M06-AUDIT-02 — The metadata cache cannot distinguish equal-title windows, tabs or documents

**Severity:** HIGH · **Confidence:** High — exact key and reuse path inspected  
**Category:** Cache coherence / scope authority · **Execution:** NOT_RUN

**Canonical requirement.** S12 cache invalidation on focus changes; M06-AC03; destination-specific metadata must belong to the current destination.

**Code location.** collector.py: _collect signature, origin_step, workspace_step, _remember.

**Current behavior.** The cache key is (PID, window title, field role). There is one cache entry, no TTL, and no window/field token, document locator, tab/origin change signal or sensitivity state in the key.

**Failure mechanism.** Different destinations regularly satisfy the same tuple. The current field is freshly read while origin/workspace can come from a prior snapshot. Missing native window titles make the key still less discriminating. The cache is bounded in size; its defect is ownership/freshness, not an unbounded map.

**Minimal reproduction (NOT_RUN).** Prime a browser snapshot for https://alpha.example with title Compose, PID 101 and AXTextArea. Change only tab URL/text to https://beta.example with the same title and role. Start another capture. For workspace, change file:///Synthetic/alpha/a.py to file:///Synthetic/beta/b.py with equal title and role.

**Expected behavior.** Invalidate and resolve the new destination, or omit metadata with an honest reason. The B snapshot must not contain A site/workspace.

**Likely actual behavior / verification boundary.** The matching tuple permits the old origin/workspace to be returned without re-reading their underlying source.

**Existing coverage.** Same-PID invalidation tests change the title. Browser-site distinction tests instantiate separate collectors.

**Why the oracle misses it.** The changed-title signal makes the test pass without distinguishing equal-title tabs or unreadable titles.

**Regression recommendation.** Keep one collector alive across captures. Test same title, missing title, same-origin new page, same document title, focus-field change, secure transition and PID reuse. Assert new origin/workspace and exact scoped-rule membership.

**Narrow repair direction.** Bind cached metadata to validated destination identity and explicit freshness. Do not use a title as an identity token. Disable reuse when required identity signals are unavailable; keep cache size bounded.

**Downstream impact.** M05 site/workspace rules, M10 profiles and developer paths, M07 context selection, and M14 replay provenance.

**Pinned evidence.** [S01](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/context.md) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md)

**Corpus mapping.** `LF-M06-S006`, `LF-M06-S007`, `LF-M06-S013`, `LF-M06-E003`

### M06-AUDIT-03 — same_destination can report a match when identity is absent or contradictory

**Severity:** HIGH · **Confidence:** High — direct expression evaluation  
**Category:** Target identity / downstream authority · **Execution:** NOT_RUN

**Canonical requirement.** Targets contract and M06-AC03: missing identity is not evidence of equality; M08 relies on M06 for its identity row.

**Code location.** snapshot.py: ContextSnapshot.same_destination; insertion/validation.py: validate_target identity row.

**Current behavior.** With both PIDs present, equality of PID wins without checking a conflicting bundle. Otherwise bundle equality is used, including None == None. No process incarnation is recorded.

**Failure mechanism.** A truthy frontmost dictionary lacking PID/bundle can match a target with missing identity. A recycled PID with a different bundle also matches. These are incorrect affirmative identity claims even under M08’s deliberately coarse documented policy.

**Minimal reproduction (NOT_RUN).** Construct a target with app_pid=None and app_bundle=None; call same_destination({"name":"Synthetic B"}). Separately use target PID 101/bundle synthetic.a and live PID 101/bundle synthetic.b. Inspect the identity row of validate_target.

**Expected behavior.** Absent or contradictory identity must never yield an affirmative match. A fallback requires an actual non-empty authoritative identity.

**Likely actual behavior / verification boundary.** The first comparison returns True through None == None; the second returns True through PID equality.

**Existing coverage.** Existing identity tests distinguish ordinary app/PID changes and scope keys.

**Why the oracle misses it.** They do not assert unknown-vs-unknown or same-PID/conflicting-bundle behavior.

**Regression recommendation.** Add a complete missing/empty/invalid PID/bundle matrix and a recycled-PID simulation. Keep a positive control for a genuine same destination.

**Narrow repair direction.** Require usable identity and reject contradictions. Define an opaque process/destination identity without reading content on the visible-feedback path. Preserve M08’s explicit caret and plain-dictation policy unless separately adjudicated.

**Downstream impact.** M08’s identity decision; same-title/cross-field granularity is additionally a design concern in AUDIT-25, not an assertion that M08 has no other checks.

**Pinned evidence.** [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S18](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/targets.md) [S19](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/insertion.md) [S20](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/validation.py)

**Corpus mapping.** `LF-M06-S015`, `LF-M06-I004`, `LF-M06-I005`, `LF-M06-I006`

### M06-AUDIT-04 — The native AX boundary is masked by tuple/window test doubles

**Severity:** HIGH · **Confidence:** Medium for native failure manifestation; high for missing conversion and lookup paths  
**Category:** Native ABI / range coordinates / target fidelity · **Execution:** NOT_RUN

**Canonical requirement.** S12 bounded selected/nearby context; S29.4 and artifacts.md require explicit native UTF-16 to Unicode-code-point conversion.

**Code location.** providers.py: SystemAXHost.string_for_range, focused_window, _as_range and read_field; insertion/hosts.py: focused_window_title comparison.

**Current behavior.** The range request passes a raw CoreFoundation.CFRange as the CFTypeRef parameter; _as_range tries tuple/attributes/dictionary/string-description parsing rather than AXValue decoding. Selected ranges are serialized without an explicit coordinate system/conversion. focused_window queries AXFocusedWindow on the focused field, with no application-element fallback (which the M08 host already has).

**Failure mechanism.** Native AXValue-wrapped ranges need a real bridge, not a fake tuple. Non-BMP strings expose the code-unit/code-point distinction. Application-owned focused-window attributes can be absent on fields, degrading identity/cache and title fallback. Test doubles return Python tuples and a window regardless of which object was queried.

**Minimal reproduction (NOT_RUN).** On the local Mac, create and decode a real AXValue CFRange, then use a synthetic native editable field with text A😀B and known selection/caret. Exercise the real SystemAXHost, including a field lacking AXFocusedWindow while its application exposes it. Record native error codes and types without focused private content.

**Expected behavior.** Real AXValue boxing/unboxing, declared native units, tested conversion before generic text-range serialization, and application-owned window lookup. Unsupported surfaces omit honestly without full-field fallback.

**Likely actual behavior / verification boundary.** Runtime/native verification required. The missing bridge/conversion/application lookup is visible statically; this audit does not claim an executed PyObjC failure or a measured rate of missing windows.

**Existing coverage.** FakeAXHost uses ordinary tuples, Python string slicing and a permissive focused_window method; historical native destination trials are pending.

**Why the oracle misses it.** The fake bypasses the representation and ownership boundary that needs qualification.

**Regression recommendation.** Add non-shim native tests for AXValue, ASCII/non-BMP/combining text, zero-length and nonempty selection, and application window lookup. Keep native-offset handling distinct from retained code-point offsets.

**Narrow repair direction.** Implement a small typed native adapter and expose its omission/error states. Use the existing application-window pattern only after confirming actual target ownership. Avoid expanding into general M08 insertion repairs.

**Downstream impact.** M04 identifiers, M05 workspace/site context, M08 selection/target inputs, and M14 offset/replay fidelity.

**Pinned evidence.** [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json) [S21](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/hosts.py) [S28](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/artifacts.md) [S16](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_SPEC.md)

**Corpus mapping.** `LF-M06-B004`, `LF-M06-B005`, `LF-M06-N001`, `LF-M06-N002`, `LF-M06-N003`

### M06-AUDIT-05 — Frozen dataclasses leave mutable data beneath a fixed context ID

**Severity:** HIGH · **Confidence:** High — object construction and serialization inspected  
**Category:** Immutability / evidence identity · **Execution:** NOT_RUN

**Canonical requirement.** M06-AC05 pre-decode immutability; S29 immutable stage inputs; behavior/serialized bytes must not change under a frozen identity.

**Code location.** snapshot.py: ContextSnapshot fields, from_json, to_json and to_envelope_block.

**Current behavior.** ContextSnapshot is frozen at the attribute level but identifiers is a dict and providers/omissions contain dicts. from_json can retain caller-owned nested objects. A caller can also construct FieldContext with mutable range data despite the annotation.

**Failure mechanism.** An owner or consumer mutates a nested object after ID assignment; serialization changes while context_snapshot_id stays fixed. A later M04 engine copy may be protected, but that does not protect the original context artifact/envelope or another serialization.

**Minimal reproduction (NOT_RUN).** Create a snapshot from a dictionary with identifiers={"user id":"userId"}. Save JSON and ID; mutate the original dictionary, a provider row and an omission row, then serialize again. Also attempt snap.identifiers mutation directly.

**Expected behavior.** Deep ownership and immutability, or explicit new-revision construction for changes. Caller-owned mutation must not change the snapshot.

**Likely actual behavior / verification boundary.** Nested dictionaries remain mutable and can change the bytes under the same ID. Assignment to the top-level frozen attribute alone would fail, which is not sufficient.

**Existing coverage.** Tests assert late results do not grow a finalized object, but do not mutate caller-owned nested collections.

**Why the oracle misses it.** They test the collector’s behavior, not the value object’s transitive immutability.

**Regression recommendation.** Independently mutate every nested container before and after serialization; assert stable bytes, scope, engine context and envelope. Verify detached mutable JSON output cannot mutate the source object.

**Narrow repair direction.** Deep-copy and recursively freeze internal state; serialize fresh ordinary JSON containers. Preserve existing public representations and historical IDs without retroactive rewrites.

**Downstream impact.** M05/M07 request identity, M08 snapshot authority, M14 reconstruction and any consumers retaining object references.

**Pinned evidence.** [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S28](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/artifacts.md) [S29](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/normalization.md)

**Corpus mapping.** `LF-M06-I001`, `LF-M06-I002`, `LF-M06-I003`

### M06-AUDIT-06 — Abandon, cancellation, deletion and shutdown do not revoke provider handles

**Severity:** HIGH · **Confidence:** High — lifecycle wiring inspected  
**Category:** Provider lifecycle / cancellation / resource bounds · **Execution:** NOT_RUN

**Canonical requirement.** M06 per-job lifecycle; late providers must not publish for abandoned work; M02 delete-everywhere remains the durable authority.

**Code location.** collector.py: _Collection._run, begin, abandon, route, take_downstream; app.py: cancelDictation, _on_job_deleted, applicationWillTerminate_.

**Current behavior.** Each begin creates a daemon thread. abandon clears only the global active pointer; a retained handle remains usable and the provider keeps running. The app’s cancellation/deletion/shutdown paths do not revoke the context handle or close context admission.

**Failure mechanism.** In-flight work can retain AX references, read further destination data, populate late results or emit after its job is cancelled. There is no total collection-age limit or admission bound. The native per-call timeout is not a whole-provider lifetime bound.

**Minimal reproduction (NOT_RUN).** Block a provider with an Event, cancel/abandon/delete its job or shut down, then release it. Call take_downstream on the original handle and inspect subsequent reads/cache/events. Repeat boundedly with several blocked jobs and count admitted active providers.

**Expected behavior.** Revoked handles cannot accept/publish further results; no new work after shutdown; bounded outstanding work and a defined drain/drop policy. Durable deletion must remain enforced by the store.

**Likely actual behavior / verification boundary.** The thread/handle is not revoked by abandon and remains capable of delivering late data. M02/M03 barriers still prevent durable deleted-job publication; this finding does not claim a verified resurrection.

**Existing coverage.** Abandon tests prove global finalize returns None after a failed identity. M02 tests prove store deletion, not M06 thread revocation.

**Why the oracle misses it.** No pending provider is resumed after cancellation while a retained handle is inspected.

**Regression recommendation.** Latch provider completion against each lifecycle transition. Assert no late artifact, no new context reference, no cache repopulation, no continuing content reads after a cooperative revocation check, and bounded provider admission.

**Narrow repair direction.** Add a per-handle lifecycle/cancellation state, bounded admission/age and collector shutdown. Integrate flag-only revocation with deletion without store calls under collector locks. Do not force-kill Python threads or block the UI waiting for them.

**Downstream impact.** M02 deletion seam, M03 shutdown, M09 History deletion, M14 retained evidence. No changes to accepted durable deletion semantics are required.

**Pinned evidence.** [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S07](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py) [S33](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M02.md) [S34](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M03.md)

**Corpus mapping.** `LF-M06-S005`, `LF-M06-S011`, `LF-M06-S012`, `LF-M06-N006`

### M06-AUDIT-07 — The 75 ms provider wait is not the release-path budget, and the release clock starts too late

**Severity:** HIGH · **Confidence:** High for synchronous path and timer placement; current-Mac latency unknown  
**Category:** Deadline / observability / M05 seam · **Execution:** NOT_RUN

**Canonical requirement.** M06 milestone: P95 additional post-release context delay ≤75 ms; E11 parent monotonic end-to-end timing; S24/S29.16 remain separate budgets.

**Code location.** app.py: _finalize_job_context and _finishCapture; collector.py: finalize; benchmark_m05.py: upgrade.

**Current behavior.** After waiting on providers, release synchronously rebuilds VocabularySnapshot from captured entries, resolves profile-dependent policy/skills, selects hints and packages evidence. M10 may perform its authorized workspace discovery. released_mono is assigned only after these steps.

**Failure mechanism.** The wait cutoff does not bound the combined work. Current final-M05 cloud evidence reports scope_upgrade_and_packaging P95 363.568 ms for 10k entries. The late timer omits the very work that needs measuring from reported release-to-insertion time.

**Minimal reproduction (NOT_RUN).** Instrument actual release callback entry, provider finalize, vocabulary rebuild, policy/profile work, hint selection/serialization, ASR enqueue/start and insertion end. Run a 10k mixed-scope fixture with a real eligibility change, plus a delayed scope-builder control that must visibly increase end-to-end latency.

**Expected behavior.** Budget the additional M06-triggered path from actual release; record every component and keep the end-to-end clock anchored before it. A missed Mac gate must be explicit, not hidden by a later clock.

**Likely actual behavior / verification boundary.** Synchronous work and timer exclusion are established from source. 363.568 ms is current-production-code cloud evidence, not a measurement on Daniel’s Mac and not an exact whole-app release time. Current reference-Mac verdict is NOT_RUN.

**Existing coverage.** Fast/slow collector tests measure waiting. Historical M06 and current M05 benchmarks use different workloads/boundaries.

**Why the oracle misses it.** A provider-only test can pass while scope rebuilding dominates. The app/benchmark clock placement hides post-release work.

**Regression recommendation.** Run isolated reference-Mac cold/warm cohorts with p50/p95/p99, positive population assertions and a real release timestamp. Demonstrate the injected delay is included. Distinguish provider cutoff, total context increment and full release-to-ASR/insertion.

**Narrow repair direction.** Move the observational release timestamp to the actual boundary; optimize/precompute or cache immutable scoped projections without rereading the live dictionary, or use an explicit safe downgrade when the remaining budget is exhausted. Do not silently change the 75 ms acceptance target.

**Downstream impact.** M05’s directly relevant M05-V003 residual; M10 scoped work; M13 latency validity; M15 acceptance. Do not rerun unrelated M01–M05 backlog.

**Pinned evidence.** [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S10](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m06.py) [S11](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m05.py) [S12](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M05/remediation/benchmark_cloud_01a1f3c.json) [S15](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_MILESTONES.md) [S17](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md)

**Corpus mapping.** `LF-M06-S016`, `LF-M06-N006`

### M06-AUDIT-08 — benchmark_m06.py can be green while its named work is absent or untimed

**Severity:** HIGH · **Confidence:** High — benchmark branches and clock inspected  
**Category:** Benchmark validity / false green · **Execution:** NOT_RUN

**Canonical requirement.** M06-AC06 and E11 require coverage, scoped work and release cost to be actually measured; validity precedes timing.

**Code location.** benchmark_m06.py: pipeline_delta, scope-upgrade cohort, fast/slow cohorts and final verdict.

**Current behavior.** The pipeline helper installs an enabled collector in both context-on and context-off arms. It calls press_release before starting its pipeline timer. The alleged warm scope-cache measurement is tuple equality, not a production cache call; the scope workload uses global entries. Slow partial status and fast timing have weak population checks, and the combined scope cost is not an exit gate.

**Failure mechanism.** An enabled-vs-enabled comparison after the expensive boundary cannot establish the incremental release cost. A no-op or failed provider can satisfy weak partial/latency conditions; unchanged effective membership can masquerade as a scope upgrade.

**Minimal reproduction (NOT_RUN).** Inspect the two installed collector.enabled flags and spy on actual content reads. Insert a deterministic delay inside release finalization. Replace provider work with an omitted result and replace scope upgrade with a no-op. Require invalid-work exit status before interpreting timings.

**Expected behavior.** Off really has zero AX reads; clocks include release work; an actual mixed-scope contender changes the eligible set; missing work fails independently of timing; advertised budget verdict affects exit code.

**Likely actual behavior / verification boundary.** The current source sets both collectors enabled and excludes press_release from its timed region; the warm cohort does not call a cache. No executable mutation was run in this audit.

**Existing coverage.** M06 historical acceptance cites the benchmark output; the benchmark itself lacks the independent oracles needed for these substitutions.

**Why the oracle misses it.** Timing and nonempty row counts are accepted without proving named work or off/on separation.

**Regression recommendation.** Port the M05 authored-membership style of oracle, not its output values. Add mutants for enabled-off, no-op provider, no-op upgrade, omitted packaging and timer-after-work. Require positive controls and truthful p95 gates.

**Narrow repair direction.** Repair the harness before using it to approve performance repairs. Preserve historical JSON as historical and produce new schema/versioned reports with invalid-work/budget-failed/pass exits.

**Downstream impact.** M06/M05 reference-Mac decisions, M13 reported latency and M15 performance gate.

**Pinned evidence.** [S10](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m06.py) [S11](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m05.py) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json) [S17](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md)

**Corpus mapping.** `LF-M06-S016`, `LF-M06-M005`

### M06-AUDIT-09 — Selection retention has no cap; the identifier count is not a total payload bound

**Severity:** HIGH · **Confidence:** High — read/scan ordering inspected  
**Category:** Privacy minimization / payload and compute bounds · **Execution:** NOT_RUN

**Canonical requirement.** S12 bounded text context; M06 latency/memory discipline; selected text follows the same privacy and ownership constraints as nearby text.

**Code location.** providers.py: read_field, extract_identifiers; snapshot.py: FieldContext.nearby_text.

**Current behavior.** AXSelectedText is read before the selected range and is retained without a length cap. The 600 limit applies separately to preceding and following slices, not selection. extract_identifiers calls regex.findall on the combined string before stopping at 64 identifiers. Placeholder/document/title strings also lack explicit payload limits.

**Failure mechanism.** A very large selection can be copied, serialized and retained despite small nearby/identifier counts. Selection is NOT fed to extract_identifiers: normal conforming flank reads cap that scanner’s input at about 1200 characters. Its findall-then-count pattern becomes an unbounded-work issue only if the host returns oversized nearby strings, which are not post-validated. Out-of-range or inconsistent range/total values are also not validated coherently.

**Minimal reproduction (NOT_RUN).** Provide a synthetic multi-megabyte AXSelectedText and inspect retained byte limits. Separately make AXStringForRange return more characters than requested, with many identifier matches. Add negative/oversized selected ranges. Do not use giant selection as evidence of giant identifier-scanner input.

**Expected behavior.** Explicit per-field and total budgets, honest oversize/truncation reasons, and range-based bounded reads when supported. No AXValue full-field fallback to compensate for missing range support.

**Likely actual behavior / verification boundary.** Selected text is retained in full. Identifier extraction scans preceding/following text, not selected text; ordinary 600-per-flank reads bound its input. An oversized host return can bypass that input bound before findall. Exact time/memory impact requires local measurement.

**Existing coverage.** Tests cover short selections and 600-character flanks; they do not supply a giant selected text value or maliciously oversized range response.

**Why the oracle misses it.** Assertions about flank lengths and identifier count do not establish total payload/read/work bounds.

**Regression recommendation.** Add selection-at-limit/over-limit, huge plain selection, huge identifier, oversized host response, invalid/stale range, combining characters and newline cases. Check read volume, serialized size and allocation-friendly scanning, not only result count.

**Narrow repair direction.** Define selection semantics before truncating replacement evidence; read ranges first where safe, use bounded parameterized reads and streaming iteration, validate lengths, and mark incomplete selection as unavailable for exact replacement authority.

**Downstream impact.** M04 identifier cost, M08 exact-selection evidence, M14 artifact size and privacy, M15 latency. Do not silently truncate text and call it a complete selection.

**Pinned evidence.** [S01](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/context.md) [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

**Corpus mapping.** `LF-M06-B001`, `LF-M06-B002`, `LF-M06-B003`, `LF-M06-B004`, `LF-M06-B005`, `LF-M06-B006`, `LF-M06-B007`, `LF-M06-B008`


## Medium Findings

### M06-AUDIT-10 — Privacy configuration coercion can turn malformed “off” or deny settings into collection

**Severity:** MEDIUM · **Confidence:** High for Python coercion; configuration validity assumptions explicit  
**Category:** Configuration / fail-closed controls · **Execution:** NOT_RUN

**Canonical requirement.** context_enabled=false means no context reads; training_retain_context=false means no M06 payload; context_denied_apps must be meaningful before access.

**Code location.** collector.py: __init__; app.py: context/evidence configuration; config.py: M06 defaults and load.

**Current behavior.** Boolean controls are converted with bool(); denied_apps is converted directly to frozenset; deadline_ms uses float without a finite safe-range check. The configuration loader accepts arbitrary JSON value types.

**Failure mechanism.** A string "false" is truthy; a deny-list supplied as one string becomes a set of characters instead of bundle IDs. An extreme deadline can exceed the intended bounded wait. These are malformed inputs, not a failure of literal JSON false.

**Minimal reproduction (NOT_RUN).** Use separate synthetic configurations with context_enabled="false", training_retain_context="false", context_denied_apps="com.google.Chrome", and a very large/nonfinite deadline. Observe validation disposition before any read or artifact write.

**Expected behavior.** Reject malformed privacy controls or fail to a documented safe state with content-free diagnostics. Never silently interpret a malformed disable/deny request as permission to read/retain.

**Likely actual behavior / verification boundary.** The coercions are visible in source. Genuine JSON false and proper arrays are handled as intended; no normal-config failure is alleged.

**Existing coverage.** Context tests use valid booleans/list settings; M02 numeric retention validation does not validate M06 context controls.

**Why the oracle misses it.** Input shape is assumed at the privacy boundary.

**Regression recommendation.** Type matrix including strings, numbers, booleans, null, arrays, objects, empty/duplicate/invalid bundle entries, and finite/nonfinite deadline values. Valid controls remain positive tests.

**Narrow repair direction.** Add narrow M06 config validation. Record capture-time versus runtime-toggle policy rather than inventing hot reload. Preserve configured limits only inside a documented safe range.

**Downstream impact.** M06 reads, context evidence retention and release reliability; no general configuration-system rewrite.

**Pinned evidence.** [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S30](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/config.py)

**Corpus mapping.** `LF-M06-S013`, `LF-M06-Q001`, `LF-M06-Q002`, `LF-M06-Q003`, `LF-M06-Q004`

### M06-AUDIT-11 — Finalize is still globally selected and is not concurrently idempotent

**Severity:** MEDIUM · **Confidence:** High — interleavings follow lock boundaries; live scheduling reachability narrowed  
**Category:** Handle ownership / concurrency · **Execution:** NOT_RUN

**Canonical requirement.** Per-job collection ownership and idempotent finalize; a foreign handle must never be substituted.

**Code location.** collector.py: begin, finalize and _active; app.py: _finalize_job_context.

**Current behavior.** Jobs retain context_coll for downstream only. finalize selects _active and optionally checks target_snapshot_id; job_id is only used for the event. The first snapshot check occurs under a lock, but composition after the wait does not re-check.

**Failure mechanism.** A begins, B begins, then A’s guarded finalize cannot retrieve A and returns None. Two callers that both pass the initial snapshot check can each compose a different pre-decode ID. A caller omitting the target ID has no job ownership guard.

**Minimal reproduction (NOT_RUN).** Use barriers for finalize(A) versus begin(B), and for two finalizers of the same handle passing the initial snapshot check before either composes. Add omitted-target-ID with mismatched job_id as an API contract probe.

**Expected behavior.** Finalize the explicitly supplied job-owned handle; validate ownership; publish exactly one immutable pre-decode result. Foreign/abandoned refusal is explicit and content-free.

**Likely actual behavior / verification boundary.** The guarded A call refuses the now-active B rather than reading A; the concurrent schedule can produce two IDs. The ordinary UI serializes capture callbacks, so this is not claimed as a reproduced live wrong-job incident.

**Existing coverage.** Serial finalize idempotence, foreign-target refusal and own-handle downstream tests exist.

**Why the oracle misses it.** They do not hold two finalizers at the same pre-composition boundary or finalize the older handle after a new begin.

**Regression recommendation.** Latch-based API tests plus a real app-method test checking which handle is passed. Assert one finalize event/artifact/ID and preserve A/B isolation.

**Narrow repair direction.** Use explicit handle/job ownership in finalize; re-check publication state under the final composition lock. Avoid a global lock held across AX work or deadline waiting.

**Downstream impact.** M05 hint context IDs, M14 pre-decode evidence, M03 queue integration. Preserve the successful historical guard against returning a foreign target.

**Pinned evidence.** [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

**Corpus mapping.** `LF-M06-S003`, `LF-M06-S004`, `LF-M06-F001`

### M06-AUDIT-12 — Downstream “one-shot” is a clearing operation, and late dependencies read the wrong stage bucket

**Severity:** MEDIUM · **Confidence:** High — state transitions inspected  
**Category:** Late provider revisions / lifecycle · **Execution:** NOT_RUN

**Canonical requirement.** M06-AC05: a separately identified downstream revision, one-shot retrieval and immutable pre-decode evidence.

**Code location.** collector.py: take_downstream, route, _collect field/doc_url lookup.

**Current behavior.** take_downstream clears coll.late but never marks the handle consumed. Providers still running can refill it. Workspace derivation and the signature read focused_field only from coll.results, so a field routed into coll.late is unavailable to those subsequent steps.

**Failure mechanism.** Partial completion followed by retrieval and further completion yields a second downstream snapshot. Conversely the app’s single pickup can miss providers completing later. A late field’s document can be omitted from workspace derivation even though that document was collected.

**Minimal reproduction (NOT_RUN).** Cut finalization while focused_field is blocked. Release it, hold the origin step, take_downstream once, then release the remaining providers and take_downstream again. Use a late field with file:///Synthetic/alpha/a.py and no IDE-title fallback.

**Expected behavior.** Declared one-shot finalization/close behavior, no additional revisions after consumption, and dependency computation from the collection’s validated data independently of its publication bucket.

**Likely actual behavior / verification boundary.** A second nonempty late batch can yield another ID. The late field is absent from coll.results and its document does not feed workspace derivation.

**Existing coverage.** The late test waits until providers have finished before its first pickup, then calls again immediately.

**Why the oracle misses it.** No provider completes between pickups; dependency staging is not asserted.

**Regression recommendation.** Use independent latches for all three providers, test each completion order and assert exact provider membership, source linkage and one-shot semantics.

**Narrow repair direction.** Choose and implement a sealed downstream lifecycle; separate provider data/dependencies from pre-decode versus downstream publication routing. Keep pre-decode bytes fixed. AUDIT-24 covers delta/full-view policy.

**Downstream impact.** M09 evidence completeness and M14 provenance; current app does not intentionally feed a late revision into original ASR hints.

**Pinned evidence.** [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py)

**Corpus mapping.** `LF-M06-S005`, `LF-M06-S010`, `LF-M06-F002`, `LF-M06-F003`

### M06-AUDIT-13 — Provider status can claim success for cached absence or failure for already retained data

**Severity:** MEDIUM · **Confidence:** High — status construction inspected  
**Category:** Provenance / coverage truth · **Execution:** NOT_RUN

**Canonical requirement.** M06 provider coverage and omission reasons must distinguish resolution, legitimate absence, failure and deadline.

**Code location.** collector.py: _remember, origin_step/workspace_step, _Collection._run and _compose; providers.py: SystemAXHost.attribute.

**Current behavior.** _remember caches None values but not their omission reason. A cache hit reconstructs ProviderResult with reason=None, hence status=ok. A window/title exception outside guarded providers marks every provider failed, including an already populated field. Native attribute errors are flattened to None.

**Failure mechanism.** An omitted/permission/deadline result can later look resolved without a successful read. A retained field can coexist with a provider_failed status. Native error codes that could distinguish unavailable/failed/classification uncertainty are lost.

**Minimal reproduction (NOT_RUN).** Prime a matching cache with an omitted origin/workspace, then repeat the capture and compare exact rows. Separately let field collection succeed and make focused_window raise. Inject native-style error codes versus genuine not-exposed attributes.

**Expected behavior.** Carry actual status/provenance with cached values, or do not cache negative/degraded results. A later window failure must not relabel an already successful independent provider.

**Likely actual behavior / verification boundary.** Cached None returns an ok row; the outer exception path labels all providers failed while existing results remain available for composition.

**Existing coverage.** Immediate read_field exceptions are checked against deadline; negative-cache and window-stage exceptions are not.

**Why the oracle misses it.** Tests assert broad partial outcomes rather than the exact value/status pair across repeated captures.

**Regression recommendation.** Assert provider row, omission, partial flag and value together; repeat across cache reuse and inject failures at window lookup, title lookup and each native attribute.

**Narrow repair direction.** Preserve structured provider outcomes and native error classes; guard window metadata as its own explicit stage or associate its error only with dependent providers. Keep exception text out of events.

**Downstream impact.** M13 coverage/diagnostics and M14 completeness; classification uncertainty also needs the policy adjudication in AUDIT-22.

**Pinned evidence.** [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

**Corpus mapping.** `LF-M06-S007`, `LF-M06-E001`, `LF-M06-E002`, `LF-M06-E003`

### M06-AUDIT-14 — Origin parsing retains userinfo, and title inference has avoidable false positives

**Severity:** MEDIUM · **Confidence:** High — parser branches inspected  
**Category:** Origin minimization / scope provenance · **Execution:** NOT_RUN

**Canonical requirement.** S12 browser origin rather than full URL; conservative, provenance-marked title fallback; no filenames/version titles misrepresented as sites.

**Code location.** providers.py: _url_origin, _TITLE_DOMAIN_RE, _plausible_host and read_site_origin.

**Current behavior.** _url_origin concatenates scheme and netloc, retaining userinfo and accepting non-web schemes/unchecked port text. Title matching searches a domain-looking substring; the file-extension deny set is lowercase but the candidate TLD is not normalized before comparison.

**Failure mechanism.** https://synthetic-user:CANARY_URL_CRED@alpha.example/path becomes an origin containing credentials. foo.com.TXT can pass the extension guard while foo.com.txt is rejected. An email-like title can supply a domain that is not evidence of the current site.

**Minimal reproduction (NOT_RUN).** Feed the credential URL, foo.com.TXT, a title author@alpha.example, Version 3.14 and a valid alpha.example title as independent controls. Assert exact origin, source provenance and permitted scope authority.

**Expected behavior.** No userinfo in an origin; supported scheme/host/port validation; case-insensitive filename rejection; non-site title content must not silently establish trusted destination identity.

**Likely actual behavior / verification boundary.** Userinfo survives netloc concatenation. The uppercase extension bypass follows from the case-sensitive set check. Title-only authority requires the separate policy decision in AUDIT-23.

**Existing coverage.** Query/fragment stripping and lowercase filename/version controls are covered.

**Why the oracle misses it.** No credential netloc, uppercase extension or email-title negative is supplied.

**Regression recommendation.** Add exact outputs for casing, ports, trailing slash, query/fragment, malformed URL, file URL, localhost/IP, userinfo, Unicode/IDNA policy and non-browser controls. Preserve original allowed representation where M05 comparison canonicalization already owns equivalence.

**Narrow repair direction.** Parse and reconstruct an allowed origin from validated host/scheme/port without userinfo; repair heuristic negatives narrowly. Do not normalize workspace/profile strings or rewrite M05 comparison rules.

**Downstream impact.** M05 site scope, M10 category/profile, retained context privacy. No claim that a credential-bearing URL was observed in Daniel’s usage.

**Pinned evidence.** [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md)

**Corpus mapping.** `LF-M06-U001`, `LF-M06-U002`, `LF-M06-U003`, `LF-M06-U004`, `LF-M06-U005`, `LF-M06-U006`, `LF-M06-U007`, `LF-M06-U008`, `LF-M06-U009`, `LF-M06-U010`, `LF-M06-U011`, `LF-M06-U012`, `LF-M06-U013`, `LF-M06-U014`, `LF-M06-U015`, `LF-M06-U016`, `LF-M06-U017`, `LF-M06-U018`, `LF-M06-U019`, `LF-M06-U020`

### M06-AUDIT-15 — Context retention metadata is optimistic before artifact/lease acknowledgment

**Severity:** MEDIUM · **Confidence:** High for queued publication path; final envelope consistency needs targeted reproduction  
**Category:** Evidence publication · **Execution:** NOT_RUN

**Canonical requirement.** M02 acknowledged publication semantics; M06 retained=true must mean a committed, governed payload exists.

**Code location.**  training.py: EvidenceCollector.on_context_snapshot; store.py: write_text_artifact, grant_lease, publish_example.

**Current behavior.** on_context_snapshot records retained=true and an allocated artifact ID after calls that can enqueue work rather than acknowledge its commit. A later writer failure is not caught by its local try block. M02 publish_example checks references and removes uncommitted ones before publication.

**Failure mechanism.** The M02 guard prevents the broad dangling-reference claim, but can leave an internal retained=true flag inconsistent with a nulled reference/completeness failure. A refused lease also needs distinct handling rather than treating an allocated ID as governed retention.

**Minimal reproduction (NOT_RUN).** Inject a writer-side context-artifact insert failure, then a lease failure, independently for pre-decode/downstream. Complete evidence publication and inspect the final stored envelope, retained flag, missing reason, actual artifact and lease, and capture event.

**Expected behavior.** No affirmative retention claim without acknowledged payload and lease. A known snapshot whose retention fails keeps content-free identity with an accurate retention_write_failed or established publication-incomplete reason.

**Likely actual behavior / verification boundary.** Optimistic in-memory flags are visible in source. M02 sanitizes uncommitted references, so durable resurrection/dangling references are not established. Run the exact final-envelope counterexample locally before choosing the repair.

**Existing coverage.** M06 tests cover retention on/off and successful round-trip; M02 covers generic uncommitted-reference sanitization.

**Why the oracle misses it.** The cross-family invariant retained flag ↔ acknowledged governed artifact is not asserted by M06.

**Regression recommendation.** Test asynchronous writer failure, lease refusal, publication timeout, delete-before-write and delete-before-publish. Assert every nested reference and truthful completeness, not only row count.

**Narrow repair direction.** Use acknowledged context publication or reconcile context retention flags in the existing acknowledged publication boundary. Keep dictation independent of evidence failures and preserve M02 deletion/timeout semantics.

**Downstream impact.** M09 diagnostics and M14 replay/readiness; do not modify M02 broadly or misreport its existing deletion protection.

**Pinned evidence.** [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S07](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py) [S25](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md) [S33](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M02.md)

**Corpus mapping.** `LF-M06-S010`, `LF-M06-S011`, `LF-M06-R001`, `LF-M06-R002`, `LF-M06-R003`, `LF-M06-Q004`

### M06-AUDIT-16 — The M06 engine-context seam is coupled to vocabulary availability and only partly transactional

**Severity:** MEDIUM · **Confidence:** High for helper behavior; whole-app disposition requires failpoint tests  
**Category:** M04/M05/M10 composition failure · **Execution:** NOT_RUN

**Canonical requirement.** One finalized M06 context feeds destination/identifiers independently of optional hints; failure must not silently mix authorities or reuse previous-job state.

**Code location.** app.py: _finalize_job_context and subsequent _m10_finalize_upgrade.

**Current behavior.** When norm_context has no vocabulary, the helper returns before attaching the new M04 destination/identifier context. Otherwise it updates context_snapshot, target, profile and an engine context with old vocabulary before building the upgraded snapshot/policy. Some failures are later labeled hotkey_down_trio_kept.

**Failure mechanism.** An unavailable vocabulary subsystem suppresses independently available identifiers. A later construction/policy failure can leave final destination/profile beside older scoped vocabulary/hints, without a precise effective-scope disposition. The retained entries are not reread from the store, which is a strength.

**Minimal reproduction (NOT_RUN).** Finalize a valid identifier-bearing snapshot while vocabulary is absent. Then inject failure into VocabularySnapshot construction and _finalized_policy, first at the helper and then through the complete release path including _m10_finalize_upgrade. Compare effective context, profile, vocabulary, hint and evidence identities.

**Expected behavior.** Attach permitted M06 engine fields even without vocabulary. Commit a coherent effective tuple or explicitly report which captured narrower scope was retained; no stale previous-job fallback.

**Likely actual behavior / verification boundary.** The early return definitely skips M06 engine fields. Partial assignments exist before the failed upgrade. The later M10 step can narrow the whole-app impact and must be included before accepting a stronger mismatch allegation.

**Existing coverage.** Positive frozen-entry/scope tests and repaired M05 selector failure tests exist.

**Why the oracle misses it.** No independent assertion covers missing vocabulary plus valid identifiers or every failure boundary across both finalizers.

**Regression recommendation.** Use a real scoped contender and captured rules; test store/selector/policy/profile errors separately. Preserve the accepted behavior that successful vocabulary upgrade with failed optional selection yields no hint set.

**Narrow repair direction.** Decouple M06 field attachment from vocabulary availability. Build the complete effective tuple in locals or record an explicit downgrade; keep M05 captured-entry immutability and M10 captured-rule policy.

**Downstream impact.** M04 identifier normalization, M05 effective scope, M07 permitted context and M10 profile evidence. No broad M05 re-audit.

**Pinned evidence.** [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md) [S29](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/normalization.md) [S36](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M05.md)

**Corpus mapping.** `LF-M06-S008`, `LF-M06-S009`, `LF-M06-M003`, `LF-M06-M004`


## Low Findings

None raised. Minor documentation corrections are included with their owning finding rather than inflated into separate defects.


## Test Gaps

### M06-AUDIT-17 — Privacy tests do not independently enumerate every prohibited read and destination-derived surface

**Severity:** TEST GAP · **Confidence:** High — inspected test oracles  
**Category:** Privacy proof completeness · **Execution:** NOT_RUN

**Canonical requirement.** S12 classify-before-read, denied-app absolute and M06-AC01.

**Code location.** test_context_snapshot.py: FakeAXHost and privacy cases; test_context_pipeline.py: secure/retention cases.

**Current behavior.** Existing canary cases prove important stable-field behavior, but the prohibited-read instrument is narrower than the full provider surface. A single field-value canary does not independently cover selection, document, URL, title, cache and exception payloads.

**Failure mechanism.** A new provider or metadata path can read a prohibited attribute while a test checks only the value canary or final snapshot. Conversely, necessary NSWorkspace identity must not be counted as prohibited content.

**Minimal reproduction (NOT_RUN).** Give each synthetic attribute a distinct canary; maintain an independently authored forbidden-call set for denied, secure and unclassifiable outcomes. Exercise all provider paths and both retained revisions.

**Expected behavior.** Attribute-level zero-read proof where forbidden, plus serialization/event/cache non-retention. Explicitly distinguish allowed identity from policy-dependent metadata.

**Likely actual behavior / verification boundary.** No new leak is claimed from the coverage gap alone. AUDIT-01 supplies the concrete destination-drift counterexample.

**Existing coverage.** Stable secure/denied cases and round-trip canary assertions already exist.

**Why the oracle misses it.** The field-focused oracle can miss a newly added independent read; metadata policy is not fully adjudicated.

**Regression recommendation.** Fail tests on an unexpected content-bearing call even when its return is discarded; require normal-field positive controls to prove the host is exercised.

**Narrow repair direction.** Expand independent instrumentation and policy matrices before touching production gates. Do not turn every allowed identity lookup into a false privacy finding.

**Downstream impact.** M06 privacy certification and M14 evidence boundaries.

**Pinned evidence.** [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S31](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/fixtures_context_targets.json)

**Corpus mapping.** `LF-M06-P001`, `LF-M06-P002`, `LF-M06-P003`, `LF-M06-P004`, `LF-M06-P005`, `LF-M06-P006`, `LF-M06-C001`, `LF-M06-C002`, `LF-M06-C003`, `LF-M06-C004`, `LF-M06-C005`, `LF-M06-C006`, `LF-M06-D001`, `LF-M06-D002`, `LF-M06-D003`, `LF-M06-D004`, `LF-M06-D005`, `LF-M06-S001`, `LF-M06-S002`, `LF-M06-S014`, `LF-M06-E001`

### M06-AUDIT-18 — Lifecycle and deletion seams lack deterministic, population-positive race evidence

**Severity:** TEST GAP · **Confidence:** High — inspected M06 suites  
**Category:** Concurrency / deletion proof · **Execution:** NOT_RUN

**Canonical requirement.** M06-AC02/AC05, M02 deletion authority and the requested stateful audit.

**Code location.** test_context_snapshot.py and test_context_pipeline.py; app._on_job_deleted; store.publish_example.

**Current behavior.** Existing M06 late-provider tests predominantly arrange timing with sleeps. They do not independently force every handle-finalize, delete-publication, cache-refresh or shutdown interleaving.

**Failure mechanism.** A test may pass without a genuinely late provider, successful initial artifact or competing job. Existing M02 barriers are meaningful but not a substitute for the full current M06 producer sequence.

**Minimal reproduction (NOT_RUN).** Latch an actual provider after its first positive read; delete the job while it is pending; release it through the production evidence path. Repeat delete before write, between artifact and lease, and before example publication.

**Expected behavior.** Exact ownership and no durable re-creation after deletion, with positive populations proving a real pending producer and real publication attempt.

**Likely actual behavior / verification boundary.** NOT_RUN. This is a missing independent proof, not a finding that the accepted deletion barrier is broken.

**Existing coverage.** M02 has targeted deletion/publication tests; M06 has basic late ownership and retention tests.

**Why the oracle misses it.** Cross-component operation ordering and actual produced populations are not all asserted in the M06 suites.

**Regression recommendation.** Use Events/Barriers and writer-operation hooks, not sleep duration as synchronization. Assert one snapshot/event and no references/artifacts for deleted jobs.

**Narrow repair direction.** Add seam tests around the existing authority; preserve flag-only deletion listeners and avoid lock inversion.

**Downstream impact.** M02/M03 compatibility, M09 deletion and M14 evidence readiness.

**Pinned evidence.** [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S07](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S33](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M02.md) [S34](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M03.md)

**Corpus mapping.** `LF-M06-S003`, `LF-M06-S004`, `LF-M06-S005`, `LF-M06-S010`, `LF-M06-S011`, `LF-M06-S012`, `LF-M06-R003`

### M06-AUDIT-19 — The hostile-context oracle needs to inspect the current full cleanup request

**Severity:** TEST GAP · **Confidence:** High — current consumer and historical test compared  
**Category:** M07 permitted-context seam · **Execution:** NOT_RUN

**Canonical requirement.** Current cleanup.md permitted-context contract; M06-AC04; no raw surrounding text in cleanup prompts.

**Code location.** app.py cleanup request construction; test_context_pipeline.py hostile-nearby test; contracts/cleanup.md.

**Current behavior.** Current cleanup intentionally receives selected approved vocabulary and a destination profile. The historical test compares recorded transcript inputs, while the old acceptance text says no context reaches any prompt.

**Failure mechanism.** Checking only the transcript argument does not prove that another request field carries no nearby text, origin, document or selected-text canary. It also cannot establish that permitted scoped vocabulary still arrives.

**Minimal reproduction (NOT_RUN).** Spy on the entire current cleanup request using a normal field containing distinct hostile canaries and an approved scoped vocabulary contender. Assert the exact allowed request shape, permitted positive terms/profile, and forbidden raw fields.

**Expected behavior.** Allowed vocabulary/category data is present; raw destination content is absent; alias pairs stay validator-only; late-only context never claims pre-decode origin.

**Likely actual behavior / verification boundary.** Current inspected source maintains a narrow permitted surface. This is a test/documentation gap, not a reproduced prompt injection.

**Existing coverage.** M07 contract and cleanup tests plus M06 transcript-equivalence test.

**Why the oracle misses it.** The historical assertion observes too narrow an interface and the historical architectural sentence is stale.

**Regression recommendation.** Capture complete supervisor arguments and rendered prompt data at the seam without re-auditing semantic validation. Include raw/clean/default styles.

**Narrow repair direction.** Update the interface oracle and historical-current distinction; do not remove legitimate M07 context or expand its prompt surface.

**Downstream impact.** M05/M06/M07/M10 compatibility and M14 reconstruction.

**Pinned evidence.** [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json) [S23](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/cleanup.md) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md)

**Corpus mapping.** `LF-M06-P001`, `LF-M06-P002`, `LF-M06-P003`, `LF-M06-P004`, `LF-M06-P005`, `LF-M06-P006`, `LF-M06-M001`

### M06-AUDIT-20 — Profile, disabled-context and retry matrices need current end-to-end identity assertions

**Severity:** TEST GAP · **Confidence:** Medium-high — relevant callers and contracts inspected  
**Category:** Cross-milestone capture policy · **Execution:** NOT_RUN

**Canonical requirement.** M05 frozen entries, M10 captured rule policy, M04 retry_unscoped_default and M06 disabled-context semantics.

**Code location.** app.py: _m10_freeze, _m10_re_resolve, _finalize_job_context, _m10_finalize_upgrade and _retry_norm_state.

**Current behavior.** Captured rules are re-resolved with finalized destination; retries use an explicitly unscoped default rather than current focus. M06 tests do not cover all profile A/B/no-profile transitions or supported disabled-state transitions with a primed cache.

**Failure mechanism.** A helper-only failure test can miss a later M10 repair or a new mismatch. Recovered audio must not acquire today’s context and be represented as the original snapshot.

**Minimal reproduction (NOT_RUN).** Capture rules and entries, change live stores during recording, then finalize. Repeat with profile failure, no vocabulary, context disabled, automatic retry, History retry and recovered audio. Compare complete effective identities.

**Expected behavior.** Current job obeys captured-entry/captured-rule policy; a retry remains explicitly new/unscoped; disabled context does not reuse a prior snapshot.

**Likely actual behavior / verification boundary.** NOT_RUN. The accepted unscoped retry path is a strength; no retroactive-context defect is asserted without a failing seam test.

**Existing coverage.** M05/M04 remediation and M06 positive frozen-entry tests cover subsets.

**Why the oracle misses it.** The full policy/context/profile/hint/evidence tuple and all current app paths are not asserted together.

**Regression recommendation.** Use two genuinely different profiles and scoped contenders, not equal defaults; require positive changes only on the next intended job.

**Narrow repair direction.** Add exact integration oracles and document whether any mid-capture feature change is supported; do not invent hot reload or change M02 capture-time consent semantics.

**Downstream impact.** M04/M05/M10/M14 provenance; no broad retry/profile audit.

**Pinned evidence.** [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S09](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md) [S25](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md) [S35](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M04.md) [S36](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M05.md)

**Corpus mapping.** `LF-M06-S008`, `LF-M06-S009`, `LF-M06-S013`, `LF-M06-M002`, `LF-M06-M003`

### M06-AUDIT-21 — Native recovery and repository-wide consumer coverage remain explicitly unqualified

**Severity:** TEST GAP · **Confidence:** High about audit boundary; native outcomes unknown  
**Category:** Native qualification / audit coverage · **Execution:** NOT_RUN

**Canonical requirement.** EV-08/EV-18/EV-19 require native interface evidence and current consumer tracing.

**Code location.** SystemAXHost lifecycle; all consumers of M06 public types/IDs; local reference-Mac test inventory.

**Current behavior.** Historical live AX access failed in its hosting terminal and human destination trials remained pending. This audit inspected the known full app and explicit provider/insertion/evidence interfaces; repository code search returned incomplete_results=true, not an exhaustive symbol inventory.

**Failure mechanism.** Fake AX success cannot certify permission revocation, stale system elements, process death or native representations. An incomplete search cannot prove there are no additional callers.

**Minimal reproduction (NOT_RUN).** Locally run rg for the public M06 symbols/IDs and classify every caller. Run synthetic-native permission/error/restart checks that are safe to automate; leave real GUI/TCC actions manual.

**Expected behavior.** Complete local caller inventory and actual native evidence, or precise remaining NOT_RUN checks. No inferred behavior from a missing search result.

**Likely actual behavior / verification boundary.** Runtime/native verification required; this coverage limit does not invalidate the specific source-backed counterexamples elsewhere.

**Existing coverage.** Known callers and contracts were manually traced; historical native limitations are declared.

**Why the oracle misses it.** The existing fake host does not model all native errors/ownership; GitHub indexing is not a proof of repository-wide absence.

**Regression recommendation.** Bind native tests to machine, interpreter and SHA; model error outcomes without private text; enumerate call sites with local source search.

**Narrow repair direction.** Close evidence gaps in the local session, refreshing a stale cached AX element only if the native result supports that repair. Do not invent a current native failure.

**Downstream impact.** All M06 consumers; this is not permission to audit another milestone.

**Pinned evidence.** [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S14](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json) [S17](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md) [S42](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/__init__.py)

**Corpus mapping.** `LF-M06-S012`, `LF-M06-S014`, `LF-M06-W001`, `LF-M06-W002`, `LF-M06-W003`, `LF-M06-W004`, `LF-M06-W005`, `LF-M06-W006`, `LF-M06-W007`, `LF-M06-W008`, `LF-M06-W009`, `LF-M06-W010`, `LF-M06-N001`, `LF-M06-N002`, `LF-M06-N003`, `LF-M06-N004`, `LF-M06-N005`, `LF-M06-N006`


## Design Concerns

### M06-AUDIT-22 — Secure and unclassifiable metadata policy must be distinguished from field content

**Severity:** DESIGN CONCERN · **Confidence:** High — distinction visible in contract and tests  
**Category:** Privacy policy adjudication · **Execution:** NOT_RUN

**Canonical requirement.** S12 prohibits secure/unclassifiable field content and denied-app reads; necessary identity and metadata need explicit scope.

**Code location.** providers.read_field; collector window/origin/workspace stages; secure-browser tests; context.md.

**Current behavior.** The field reader returns before secure/unclassifiable content. Other metadata stages can still query window/title/origin for a non-denied destination; tests allow a secure browser’s origin. A failed subrole read is flattened to None, which is also a legitimate absent subrole.

**Failure mechanism.** “No secure field content” and “no destination metadata at all” are different policies. Treating all metadata as automatically allowed or all identity as prohibited would silently rewrite the contract.

**Minimal reproduction (NOT_RUN).** Adjudicate a matrix of secure, unknown-role, missing-subrole, failed-subrole and denied destinations versus identity/title/origin/document/selection/nearby attributes. Distinguish real absence from failed classification.

**Expected behavior.** Field content remains fail-closed. Every metadata allowance is explicit, ownership-bound, minimized and tested. An unknown classification must not be promoted by an error masquerading as absence.

**Likely actual behavior / verification boundary.** Policy decision required for metadata. No stable secure AXValue/selected-text read was found in the inspected field provider; drift remains AUDIT-01.

**Existing coverage.** Stable secure tests support zero field-content reads and allow some metadata.

**Why the oracle misses it.** They do not settle the policy for every error/custom web control or metadata source.

**Regression recommendation.** Policy-driven attribute matrix with separate identity/content canaries and native subrole-error tests.

**Narrow repair direction.** Write the policy before widening a deny gate. Preserve plain dictation and do not broaden M08 insertion mechanics within this audit.

**Downstream impact.** M05/M10 scope allowance in sensitive destinations and M14 retention disclosure.

**Pinned evidence.** [S01](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/context.md) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S08](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py) [S16](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_SPEC.md)

**Corpus mapping.** `LF-M06-C001`, `LF-M06-C002`, `LF-M06-C003`, `LF-M06-C004`, `LF-M06-C005`, `LF-M06-C006`, `LF-M06-S002`, `LF-M06-N004`

### M06-AUDIT-23 — Heuristic origins/workspace names become scope authority without carrying source quality

**Severity:** DESIGN CONCERN · **Confidence:** High — representation seam inspected  
**Category:** Scope authority / identifier semantics · **Execution:** NOT_RUN

**Canonical requirement.** S12 provenance; M05 exact ScopeContext values and approved scope filtering.

**Code location.** providers.read_site_origin/read_workspace; ContextSnapshot.to_scope_context; app._m10_re_resolve.

**Current behavior.** Title-derived origins and directory/title-derived workspace display names have provenance in M06, but ScopeContext carries only values. Two distinct paths with the same containing-directory name also share that workspace value.

**Failure mechanism.** A weak title observation can trigger the same site rule as a direct URL, and a display-name scope may intentionally or accidentally cover more than one project. Merely labeling provenance in an artifact does not qualify authorization.

**Minimal reproduction (NOT_RUN).** Compare AXURL origin versus identical title-inferred origin with an approved site rule; compare /Synthetic/teamA/project/a.py and /Synthetic/teamB/project/a.py with a project scope. Record desired scope membership before implementation.

**Expected behavior.** An explicit decision on whether heuristic/display-name matches can grant scope; evidence must reveal that condition. Strong identity and display labels should not be conflated.

**Likely actual behavior / verification boundary.** Design-only until scope policy is adjudicated. Current value matching is not itself a new M05 comparison defect.

**Existing coverage.** Provenance strings and site/workspace positive cases exist.

**Why the oracle misses it.** The tests assume a value establishes eligibility and do not challenge evidence quality or display-name collisions.

**Regression recommendation.** Paired positive/negative controls for direct versus heuristic sources and equal labels at different destinations.

**Narrow repair direction.** Choose conservative omission, explicit opt-in or a typed authority-quality input. Preserve M05 case-insensitive bundle/canonical-site comparisons and existing opaque workspace/profile semantics.

**Downstream impact.** M05 and M10 rule authority, M07 permitted vocabulary, M14 provenance.

**Pinned evidence.** [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md)

**Corpus mapping.** `LF-M06-U001`, `LF-M06-U002`, `LF-M06-U003`, `LF-M06-U004`, `LF-M06-U005`, `LF-M06-U006`, `LF-M06-U007`, `LF-M06-U008`, `LF-M06-U009`, `LF-M06-U010`, `LF-M06-U011`, `LF-M06-U012`, `LF-M06-U013`, `LF-M06-U014`, `LF-M06-U015`, `LF-M06-U016`, `LF-M06-U017`, `LF-M06-U018`, `LF-M06-U019`, `LF-M06-U020`, `LF-M06-W001`, `LF-M06-W002`, `LF-M06-W003`, `LF-M06-W004`, `LF-M06-W005`, `LF-M06-W006`, `LF-M06-W007`, `LF-M06-W008`, `LF-M06-W009`, `LF-M06-W010`, `LF-M06-B007`

### M06-AUDIT-24 — Downstream revisions need a declared delta/full-view and parent-link policy

**Severity:** DESIGN CONCERN · **Confidence:** High — serialized shape inspected  
**Category:** Revision semantics · **Execution:** NOT_RUN

**Canonical requirement.** M06-AC05 separate late context; S29 original pre-decode inputs must remain identifiable.

**Code location.** ContextCollector.take_downstream/_compose; ContextSnapshot.to_json; training.on_context_snapshot.

**Current behavior.** A downstream snapshot contains only the late provider batch, a new UUID and stage=downstream. It shares the target and job envelope but has no explicit parent_context_snapshot_id. Providers outside the batch are not_in_revision.

**Failure mechanism.** A consumer can mistake a delta for a full replacement or cannot link a detached artifact to the exact pre-decode snapshot without its envelope. Independent UUIDs are not a content hash and are not themselves a collision defect.

**Minimal reproduction (NOT_RUN).** Finalize a partial original, capture one late batch, detach both artifacts from their envelope and reconstruct provider membership/parentage under the proposed contract. Test repeated pickup policy separately under AUDIT-12.

**Expected behavior.** A versioned description of delta versus full snapshot, original-context linkage, provider membership and terminal pickup semantics; original bytes never change.

**Likely actual behavior / verification boundary.** Design-only: current envelope/job linkage is real and must not be described as absent lineage everywhere.

**Existing coverage.** Tests check distinct IDs/stages and original non-growth.

**Why the oracle misses it.** They do not assert an explicit parent token or the semantics expected by a detached downstream consumer.

**Regression recommendation.** Test reconstruction from retained artifacts plus declared manifest, including missing original payload and retention off.

**Narrow repair direction.** Add compatible source linkage and stage/membership semantics only after deciding the representation; do not relabel late data as original or bulk-rewrite historical artifacts.

**Downstream impact.** M09 retained context and M14 replay/export.

**Pinned evidence.** [S01](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/context.md) [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S25](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md)

**Corpus mapping.** `LF-M06-F002`

### M06-AUDIT-25 — The product must state which destination distinctions can actually authorize insertion

**Severity:** DESIGN CONCERN · **Confidence:** High — M06/M08 contract comparison  
**Category:** Target granularity · **Execution:** NOT_RUN

**Canonical requirement.** S12/S18 intended destination versus the current M08 identity/window/field matrix.

**Code location.** TargetSnapshot, ContextSnapshot.same_destination; insertion.validate_target; contracts/targets.md and insertion.md.

**Current behavior.** M06’s hook is app identity only. M08 knowingly adds conditional title/role checks and exact nonempty-selection checks; a moved caret is explicitly allowed, and identity-only fallback exists when field data is unavailable.

**Failure mechanism.** Two same-title windows or same-role controls without a recorded nonempty selection can satisfy that matrix. Adding only a stronger-sounding method name does not distinguish them, while treating every caret movement as foreign would break declared behavior.

**Minimal reproduction (NOT_RUN).** Use one app with two equal-title windows and two same-role fields, identical or empty selection. Compare against a same-field caret movement. Define which should retain authority and which should save rather than insert.

**Expected behavior.** An explicit conservative authority model with opaque destination tokens where supported, honest unavailable distinctions and preserved deliberate caret semantics.

**Likely actual behavior / verification boundary.** Design concern for broader granularity; AUDIT-03 separately covers unambiguously absent/contradictory identity. No full M08 insertion audit or native wrong-window incident is claimed.

**Existing coverage.** M08’s documented extra checks are present; M06 app-change tests do not establish stronger identity.

**Why the oracle misses it.** Title/role equality can be mistaken for object identity; coarse fallback policy is not a native field-identity guarantee.

**Regression recommendation.** Targeted seam tests, including a positive same-field moved-caret control, equal-title windows, same-origin tab changes and unknown live role.

**Narrow repair direction.** Coordinate the M06 identity hook and only its M08 consumer. Do not add AX to visible-feedback startup, claim a title is unique, or rewrite insertion transactions.

**Downstream impact.** M08 insertion authority and M14 outcome attribution; M15 should not inherit an overstated safety claim.

**Pinned evidence.** [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S18](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/targets.md) [S19](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/insertion.md) [S20](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/validation.py) [S21](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/hosts.py)

**Corpus mapping.** `LF-M06-S015`


## Areas Verified Strong

**Stable-field privacy gates:** role/subrole precede content reads; known secure/unclassifiable fields return early; denied field/origin/workspace entry points refuse before querying; composition hard-nulls captured-denied values. These do not solve the intervening-focus ownership gap. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py)

**Ordinary stage and job separation:** a job keeps its own late handle; target-ID mismatch refuses a foreign active finalize; ordinary late data receives a separate stage and ID; pre-decode assembly does not deliberately grow from late callbacks. Deep immutability, concurrent finalize and terminal pickup remain repair items. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

**Captured M05 authority:** widened vocabulary is built from frozen entries, not a changed live dictionary; optional hint selection can fail without undoing a successful scope upgrade, and stale narrower hints are cleared. Current exact-identity qualification keeps unsupported ASR requests empty rather than fabricating biasing. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md) [S26](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/capabilities.py)

**Governed evidence:** normal context envelopes/events are content-free; independent retention-off applies to downstream too; M02’s committed-reference and deleted-job barriers remain present. A queued context producer’s optimistic flag must be repaired without weakening these protections. [S02](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py) [S04](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py) [S06](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py) [S07](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py)

**Bounded normal nearby access / no M06 filesystem crawler:** the provider requests 600 characters on each side using a range API and does not add an AXValue whole-field fallback. Identifier input is normally those flanks, not the selected text. M06 infers path/workspace from strings without opening files; M10’s explicitly authorized discovery is separate. The native range bridge and unbounded selection still need repair/qualification. [S03](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md)

**Not verified strong:** the current M06 benchmark, native field/window equivalence, revocation after cancel/quit, equal-title cache validity, total 75 ms release compliance and transitive snapshot immutability. No test count or historical acceptance sentence is substituted for those proofs.


## Adversarial Corpus Summary

`LocalFlow_M06_Adversarial_Corpus.json` contains **101 synthetic cases in 50 families**, including all **16 required stateful probes**, **10 metamorphic relations**, and **18 mutation definitions**. Every case, relation and mutation is **NOT_RUN**; observed results are null. Role counts are recorded in the JSON and distinguish controls, adversarial, stateful, native and design probes.

The corpus includes field classifications, denied app classes, focus/handle interleavings, origin/title/locator edge cases, bounds and Unicode, missing/conflicting identity, mutable snapshots, negative-cache statuses, evidence writer/lease/deletion failures, valid/malformed controls, profile/retry seams and work-valid benchmarks. It uses invented text, paths and credentials; real bundle IDs are classification keys only. No private local evidence is included.

Some requested behaviors need policy adjudication, and their records explicitly say so rather than inventing a current provider/envelope reason. The JSON is a declarative machine-readable specification, not a self-executing test harness. The local session must implement independent adapters/oracles and publish base/first-pass/final outcomes separately without replacing the delivered NOT_RUN baseline.


## Stateful / Metamorphic / Mutation Test Plan

Run deterministic ownership/lifecycle cases first: barriers at the post-identity check, field completion, window/origin lookup, pre-finalize composition, late-result routing, cache refresh and writer publication. Prove that providers and artifacts genuinely exist before testing their absence after revocation/deletion. No sleep-only test establishes a specific interleaving.

Metamorphic checks cover privacy/deny monotonicity, A/B isolation, late-stage isolation, cache invalidation, captured-entry scope widening, independent retention, representation equivalence, failure-status honesty and injected-delay conservation. Variants in one family are related evidence, not new independent samples.

Only after controls pass, introduce the declared mutations in disposable local copies: denied gate removed; exception mislabeled deadline; global handle substitution; skipped identity check; original object grown by late data; downstream retention bypass; coarse cache; live dictionary reread; old-job fallback; deleted-job publication bypass; refilled downstream; absent identity equality; native range bridge removed; cached absence promoted; clock after work; no-op scope/packaging; truthiness-enabled privacy; optimistic retention. Report control validity and every mutant’s disposition. No mutations were run by this audit.


## Downstream Impact

| Consumer | M06-owned consequence / narrow compatibility obligation |
|---|---|
| M05 | Authentic current scope; frozen entries and repaired comparison rules preserved; optional hint failure stays isolated; current 10k contribution measured |
| M07 | Only permitted complete request data; no raw nearby/selected/origin/path leakage; wrong scope can still select wrong approved terms |
| M08 | Honest missing/conflicting identity, native selection units and explicit field/window granularity; do not rewrite insertion transactions |
| M09 | Correct retained/absent context and deleted-job behavior; no phantom late references |
| M10 | Re-resolve captured rules under valid scope; coherent tuple on error; authorized filesystem work separately accounted |
| M13 | Release clock includes M06 contribution; provider coverage reflects actual successes, not cached None |
| M14 | Original context remains immutable and pre-decode; late lineage explicit; deletion/completeness and retry provenance trustworthy |
| M15 | Do not inherit old “pass” claims for current native, privacy, identity or latency gates; do not begin M15 during remediation |

This table scopes interfaces, not new audits of those milestones. [S05](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py) [S19](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/insertion.md) [S22](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md) [S23](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/cleanup.md) [S24](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md) [S25](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md)


## Recommended Repair Order

1. **Safely synchronize the local foundation, inventory actual capabilities, and freeze base reproductions.** Reclassify each allegation before patching; close the local caller-inventory gap.
2. **Adjudicate privacy/authority/native-coordinate contracts needed by the repairs.** Preserve required identity and legitimate plain dictation; do not introduce broad metadata bans or new insertion semantics implicitly.
3. **Repair read ownership, identity and cache authority together.** Focus transitions, denied gates, absent/conflicting identity and freshness share one boundary. Add native range/window qualification and bounded selected-text handling.
4. **Make snapshot and handle lifecycles explicit.** Deep immutability, explicit job finalization, one original publication, revocation/closed admission and sealed late revision semantics; preserve deletion barriers.
5. **Repair status/publication/composition truth and configuration validation.** Positive values must match provider status, retained must match governed publication, and the effective profile/scope/hint tuple must be coherent.
6. **Repair the benchmark oracle and release clock before optimizing performance.** Then remeasure cold/warm current M05 scope plus actual M06 release contribution on the Mac without competing sweeps.
7. **Run corpus, seam/native tests and mutations; freeze first-pass SHA; obtain independent read-only review; reproduce review allegations before fixes; rerun final evidence and update only M06’s runbook.** Push the dedicated branch and stop, without merging or beginning another milestone.


## M06 Readiness Verdict

### C. Significant context/privacy/lifecycle weaknesses

This is not a stale-foundation or “audit inconclusive” result. The inherited main is verified, and the critical read-authority counterexample plus independent cache/lifecycle/immutability/deadline defects follow from the inspected source. Conversely, it is not a claim of observed secret capture, a measured native wrong-window insertion, broken M02 deletion, or current Mac performance failure. Those distinctions are preserved in every finding.

M06 should proceed to the **LOCAL remediation handoff**, not acceptance as-is. Accept only reproduced/narrowed defects with independent fail-first/pass-final evidence; refute unsupported allegations explicitly; adjudicate design questions before code changes. Automated/local-native completion may still leave human TCC/destination checks pending. The correct local-era completion label must reflect that boundary, not reuse the old cloud label.

**Stop boundary:** this report, the NOT_RUN corpus and the complete local handoff finish the GPT audit. No repository remediation or Daniel-local verification was performed.


## Pinned Source Inventory

**S01 — Context contract.** [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/context.md)

**S02 — Snapshot value objects and identity.** [localflow/v2/context/snapshot.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/snapshot.py)

**S03 — Accessibility providers.** [localflow/v2/context/providers.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/providers.py)

**S04 — Collector, handles, cache and revisions.** [localflow/v2/context/collector.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/collector.py)

**S05 — Production app integration.** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/app.py)

**S06 — Training evidence producer.** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/training.py)

**S07 — Store publication and deletion authority.** [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/store.py)

**S08 — Snapshot tests and fake AX host.** [tests/v2/context/test_context_snapshot.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_snapshot.py)

**S09 — Pipeline tests.** [tests/v2/context/test_context_pipeline.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/test_context_pipeline.py)

**S10 — M06 benchmark.** [scripts/v2/benchmark_m06.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m06.py)

**S11 — Current M05 benchmark.** [scripts/v2/benchmark_m05.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/scripts/v2/benchmark_m05.py)

**S12 — Final M05 cloud benchmark evidence.** [docs/v2/acceptance/M05/remediation/benchmark_cloud_01a1f3c.json](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M05/remediation/benchmark_cloud_01a1f3c.json)

**S13 — M06 historical handoff.** [docs/v2/handoffs/M06.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M06.md)

**S14 — M06 historical acceptance.** [docs/v2/acceptance/M06/results.json](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/acceptance/M06/results.json)

**S15 — Milestone obligations.** [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_MILESTONES.md)

**S16 — Specification S12, S29, S30.1.** [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_SPEC.md)

**S17 — Evaluation E10, E11, E18, E19.** [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md)

**S18 — Target contract.** [docs/v2/contracts/targets.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/targets.md)

**S19 — Insertion contract.** [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/insertion.md)

**S20 — Insertion identity consumer.** [localflow/v2/insertion/validation.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/validation.py)

**S21 — Insertion native host.** [localflow/v2/insertion/hosts.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/insertion/hosts.py)

**S22 — Vocabulary contract and remediation.** [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/vocabulary.md)

**S23 — Cleanup permitted context.** [docs/v2/contracts/cleanup.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/cleanup.md)

**S24 — Profiles and authorized developer context.** [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/profiles.md)

**S25 — Training-evidence contract and addenda.** [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/training_evidence.md)

**S26 — ASR qualification implementation.** [localflow/v2/capabilities.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/capabilities.py)

**S27 — ASR hint contract.** [docs/v2/contracts/asr_hints.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/asr_hints.md)

**S28 — Artifact and offset contract.** [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/artifacts.md)

**S29 — Normalization contract.** [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/normalization.md)

**S30 — Configuration.** [localflow/config.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/config.py)

**S31 — M06 synthetic destinations and adversarial trees.** [tests/v2/context/fixtures_context_targets.json](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/tests/v2/context/fixtures_context_targets.json)

**S32 — Accepted M01 addendum.** [docs/v2/handoffs/M01.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M01.md)

**S33 — Accepted M02 addendum.** [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M02.md)

**S34 — Accepted M03 addendum.** [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M03.md)

**S35 — Accepted M04 addendum.** [docs/v2/handoffs/M04.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M04.md)

**S36 — Accepted M05 addendum.** [docs/v2/handoffs/M05.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/handoffs/M05.md)

**S37 — Verification runbook.** [docs/v2/VERIFICATION.html](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/VERIFICATION.html)

**S38 — Current status.** [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/STATUS.json)

**S39 — Starting instructions.** [docs/v2/START_HERE.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/START_HERE.md)

**S40 — Repository overview.** [README.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/README.md)

**S41 — Contract registry.** [docs/v2/contracts/INDEX.md](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/docs/v2/contracts/INDEX.md)

**S42 — Context package exports.** [localflow/v2/context/__init__.py](https://github.com/scalinity/LocalFlow/blob/6a083bd70011988314836164e7d3016da3968490/localflow/v2/context/__init__.py)

**Native primary reference:** Apple’s AXUIElementSetMessagingTimeout documentation establishes process-default behavior for the system-wide element. AXValueCreate documents boxing supported structures into AXValue objects; exact project PyObjC behavior remains a native test. These references do not certify LocalFlow’s current Mac runtime.

- [Apple AXUIElementSetMessagingTimeout](https://developer.apple.com/documentation/applicationservices/1459345-axuielementsetmessagingtimeout)
- [Apple AXValueCreate](https://developer.apple.com/documentation/applicationservices/1459351-axvaluecreate)
