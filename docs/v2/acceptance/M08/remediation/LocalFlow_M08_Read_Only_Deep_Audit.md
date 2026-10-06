# LocalFlow V2 — M08 Read-Only Deep Audit

**Date:** September 26, 2026  
**Repository:** `scalinity/LocalFlow`  
**Canonical audited SHA:** `180278ee8a157e7372ba187cfb0106556114293f`  
**Mode:** Read-only source audit; all proposed probes NOT_RUN

## Executive Assessment

**Verdict: C — significant authority remediation required before M08 can be treated as qualified.** The present code has a useful architecture and several correctly preserved repairs, but it does not consistently carry the authority that was checked into the field that is later written, read back, undone or observed. The most consequential problems are not cosmetic UI defects: they can cause a wrong-destination write, incorrect clipboard consumption, unrelated-field observation, or recovery after deletion. [S-SERVICE] [S-VALIDATION] [S-LEASE] [S-OBSERVER] [S-APP]

This report contains **19 source-backed defect findings: four Critical, twelve High and three Medium**, plus **two separate test/benchmark proof gaps**. Severity describes the consequence of the supplied interleaving, not a measured incident frequency. Every reproduction in this report and the companion corpus is **NOT_RUN**. Native adapter behavior, real application compatibility, current latency and live-data incidence have not been measured by this audit.

The central repair is a small, explicit authority model at the insertion boundary—not a rewrite of LocalFlow. A request must distinguish permission to insert, permission to replace selected text, permission to read a destination, permission to undo, permission to observe, and permission to retain training evidence. Those permissions must not be inferred from one app-identity match or from a later substring match. They must preserve accepted M06 ordinary-caret behavior and M02 capture-time consent semantics. [S-C-INSERT] [S-C-CONTEXT] [S-C-TRAIN] [S-H-M02]

**What is already strong:** the ordinary insertion entry queues work; clipboard restoration checks its owned generation; the context-absent terminal guard is present; wake re-arms observation; the clipboard full-identical-text ambiguity guard is present; the shared M06 identity rule rejects contradictions and absent identity; M11’s normalized deny gate is integrated; M02’s durable deleted-job artifact barrier remains intact. These are mandatory preservation controls, not findings to “fix” by removing functionality. [S-SERVICE] [S-CLIPBOARD] [S-VALIDATION] [S-SEAM] [S-STORE] [S-H-M06] [S-H-M11]

**Recommended next unit:** one local-only M08 reproduction/remediation branch on Daniel’s Mac, followed by a frozen first-pass independent review, owned-native-helper qualification, honest reference-Mac benchmarks and an M08-only runbook update. Push the branch without merging. M09, M12 and M15 do not start as part of that unit.

## Audit Boundary

This audit covers committed GitHub state at `180278ee8a157e7372ba187cfb0106556114293f`. Any uncommitted local state is outside the GPT-6 audit boundary.

Repository: `scalinity/LocalFlow`. Audited branch: canonical `main`. The GitHub branch read returned the expected full SHA; the integration and selected ancestry comparisons were read through the authenticated connector. Files used for conclusions were pinned to that SHA, not fetched from an unpinned moving branch.

The audit performed **source and committed-evidence inspection only**. It did not run LocalFlow, its tests, its corpus, its benchmark, MLX, PyObjC, macOS Accessibility or a native helper. No GitHub file, branch, issue or PR was changed. Local output generation and JSON/cross-reference validation validate this handoff package, **not the repository implementation**. The package contains no live clipboard, transcript, audio, database, screenshot or user-field sample.

The remote code-search endpoint returned incomplete results. Accordingly, this is a substantial, path-based consumer trace—not a claim that remote search proved every caller absent or present. The local handoff requires an exhaustive `rg` inventory before patching. The app review covered the relevant startup, M11 capture/accept, deletion, insertion completion, observer subscription, Hub/Recovery and lock/wake ranges; it was not a new full audit of every subsystem in `app.py`.

Evidence classes are kept distinct:

| Class | Meaning in this report |
|---|---|
| Static source counterexample | A concrete schedule follows from inspected branches; not executed here. |
| Historical committed result | A prior session’s dated, SHA-bound record; quoted as history, not rerun. |
| Portable production-consumer test | Required local test of actual Python consumers with independent synthetic hosts; currently NOT_RUN. |
| Real-framework / fixture-target test | Real AppKit/PyObjC construction with fake destination effects; not a real Accessibility write. |
| Owned native helper | Real host API against only a synthetic target owned by the test; required locally, NOT_RUN here. |
| Manual arbitrary-app qualification | Human-controlled TextEdit/browser/editor/terminal behavior; remains unverified until explicitly recorded. |

References `[S-…]` resolve to immutable commit-pinned repository files in the source register at the end. The file/symbol locators on each finding are the operative code references; no guessed source line numbers are used.

## Canonical Foundation

The branch read identified `main` at `180278ee8a157e7372ba187cfb0106556114293f`, commit message **“Realign orchestration overview after the pre-M08 integration”**, dated September 26, 2026. Its parent is `1c074ce0ff3ef25da79e13600be38cfa4fcf843a`. The current NOW panel explicitly makes M08’s read-only audit the next campaign unit and says M15 is dependency-eligible but gated. `STATUS.json` still describes the historical M14 implementation state; it is not clearance to skip this campaign. [S-ORCHESTRATION] [S-STATUS]

| Foundation | Provenance available to this audit | Consequence |
|---|---|---|
| Accepted M01–M05 remediation | The M06 synchronization addendum records accepted M01–M05 commits verified as ancestors at `6a083bd`; current contract/store/collector and M02/M03 review changes are present in the pinned tree. These earlier milestones are inherited, not independently re-certified here. | Preserve v11 tombstones, consent snapshots, exact stage lineage, normalization and vocabulary contracts. |
| M06 local remediation | Direct comparison of `cb05ca9571e5662ec1275530a892b4c1c604a130` to audited main returned ahead 8, behind 0, with that base as merge base. M06 final production is recorded as `4388b52`. | Use the repaired shared identity and typed native boundary, not a historical variant. |
| Accepted M07 remediation | Direct comparison from `52edc4753df9be17d9119e95d760c4086c5649cd` returned ahead 52, behind 0, with that base as merge base. | Preserve final Clean/normalized fallback bytes and all source-coordinate guarantees. |
| Integrated M11 production | Direct comparison from `9a049b341d315201ba7d8019585fd7e71370af31` returned ahead 5, behind 0; the later changes in that comparison are evidence/tests/docs/probe work, not another production rewrite. | Review current strict selection/accept paths. |
| Historical M11 cloud source | `aa03af7` / `1be42ee` were semantically replayed as `1545de9`; the final integrated production follows `46ecd5b` and `9a049b3`. They need not be ancestors of main. | Never treat a missing cloud-head ancestry relation as missing M11 remediation. |

The integrated handoff explicitly records both M06 R4’s closure and the accepted-selection callback fix. It also records the M08 historical baseline suites as green on the integrated tree. Those results are useful prior evidence, not proof that the adversarial schedules below were tested. [S-H-M02] [S-H-M03] [S-H-M06] [S-H-M07] [S-H-M11]

**Unchanged other-owner work:** M06 R5 remains under M06-V001; M11’s one misdirected model review and output-limit fallbacks remain M11/M15 work; M12 Scratchpad and M14 Hub harness races stay with those owners. None is inflated into a newly discovered M08 production defect. [S-H-M06] [S-H-M11]

## Current M08 Architecture

The production path is: coordinator result → `InsertionService.submit` → single worker queue → terminal/trust checks → target validation → AXSelectedText or clipboard method → destination readback → `InsertionResult`/insertion record → coordinator completion → optional observation → final observation/evidence revision. A parallel Recovery path offers queued undo; Paste Again currently performs reconciliation before queue admission. A selected-text M11 transform captures a destination, then accepts through the same queue with strict replacement. Internal Scratchpad accepts bypass the external queue by design. [S-SERVICE] [S-APP] [S-C-INSERT] [S-C-TRANSFORM] [S-C-NOTE]

The package is split reasonably: `hosts` isolates native calls; `validation` interprets the snapshot; `target_lease` represents granted authority; `clipboard` owns generations and supported flavors; `result` and `record` separate outward state from persistence; `observation` produces bounded post-insertion signals. The problem is that the lease is substantially weaker than the later consumers need: it contains app/range/classification metadata but no stable native field/window capability and no consumed/revoked operation identity. [S-HOSTS] [S-VALIDATION] [S-LEASE] [S-CLIPBOARD] [S-RESULT] [S-RECORD] [S-OBSERVER]

Authority currently dissipates at several seams: authorization before selection capture does not own the captured element; validation before write does not own the newly selected write element; confirmation does not by itself prove the observer’s next focused element is the same one; and durable deletion does not reach the service’s recovery cache. These are distinct seams and require effect-level tests even when a shared identity predicate is correct.

## Historical M08 Findings Revisited

The original handoff recorded three Critical findings, ten warnings and seventeen suggestions. Its three named Critical repairs are still visible. The review should not erase or rewrite that historical result. [S-H-M08] [S-A-M08]

| Historical item | Current static disposition | New boundary, if any |
|---|---|---|
| CA1: no-context multiline terminal bypass | **Repair present:** live bundle classification protects the snapshot-absent path; certified bracketed surfaces remain empty. | Late target changes and control-character variants need new qualification; they are not proof CA1 returned. |
| Lock signal was one-way | **Repair present:** wake re-arms the signal; timestamped new-dictation stop remains. | New observer ownership and deletion tests must preserve this control. |
| DB1: identical preexisting clipboard text confirmed | **Repair present for full-text clipboard equality.** | AX/missing-pre-read confirmation is AUDIT-06; unchanged partial prefix is AUDIT-07. |
| Cancellation after physical insertion | **Truth-preserving completion is present.** | AUDIT-15 concerns cancellation before an avoidable effect, not undoing recorded reality. |
| Early observer close reconciliation | **Early-close branch is present.** | A narrower subscribe/close TOCTOU remains, AUDIT-18. |
| Undo/Paste Again off-main claim | Undo queue dispatch is present; the current Recovery/History call graph still performs repaste reconciliation synchronously. | AUDIT-17 narrows the broad historical claim; no unverified regression-origin commit is assigned. |
| AXFocusedWindow on application; unreadable role fallback | Native application-window title helper and plain unavailable-role handling are present. | They do not prove element ownership or strict missing-proof completeness. |
| Deadline-bounded re-anchor | A bound exists. | AUDIT-11 questions the result of ambiguous/failed search and after-range provenance, not absence of a deadline. |
| Named constants, decorator/dead-code/import/style changes | No new correctness finding is raised from these maintenance items. | No claim of fresh historical diff verification beyond the inspected current paths. |
| Migration backup skip warning | Historical exception and warning were documented; current store contract is v11. | Do not use M08’s old schema-v4 record as current store authority. |
| User-copy test hook | Hook-based coverage exists. | It does not cover every capture/post/restore interleaving or real native acknowledgment. |
| Multi-item flattening, substring reconciliation, observer approximation, failed-job state collapse | Deliberate limitations remain disclosed. | Keep them explicit; a limitation is not an automatic production bug. Benchmark scope and substring authority cannot be overstated. |

The recorded M08 suite counts—13 race, 10 attribution and 5 pipeline cases—are historical execution evidence. This audit read their current implementations but ran none of them. The proposed corpus deliberately challenges dimensions those tests do not represent. [S-RACES] [S-ATTRIBUTION] [S-PIPELINE] [S-FIXTURE] [S-H-M11]

## Post-M06 Identity and Native Boundary

The shared `identity_matches`/`same_destination` rule is a real improvement: a usable pid is compared when both exist, bundle identity is the fallback where appropriate, two known conflicting bundles reject even with equal pids, and missing identity never matches itself. Current validation and the lease use this rule. Preserve it. [S-C-CONTEXT] [S-C-TARGET] [S-VALIDATION] [S-LEASE]

M06 also introduced owner-bound reads, AXValue decoding/boxing, UTF-16 native ranges, exact-only code-point projection, native window identity in addition to title, and revocable context handles. M08 consumes pieces of that repair, but the service’s write/undo/observer paths are not a complete end-to-end consumer of it. Reusing `ax_range` in validation is insufficient if `_current_range` still assumes a fixture object or an owned end is calculated with `len(text)` in the wrong unit. [S-H-M06] [S-C-CONTEXT] [S-NATIVE] [S-SERVICE]

Do not over-tighten the accepted destination policy: a moved empty caret—and a same-role field move in the same window before ordinary validation—can be allowed for plain dictation. The field chosen for that operation must then be bound to its write. That permissiveness is not authority for strict selected replacement, subsequent undo, or observation to follow focus indefinitely.

## Post-M11 Selection Boundary

The integrated M11 code supplies a selected-text capture, host-unit range, native window element and strict-replacement flag. It preserves source/task identity across Retry Original and Transform Output, records accepted insertion under a retained transform-candidate id, and fixes the successful-accept callback. These are inherited protections. [S-H-M11] [S-C-TRANSFORM] [S-C-PREF] [S-SEAM] [S-APP]

M08’s remaining responsibilities are narrower: prove the capture actually belongs to the app authorized to read; positively revalidate every required strict proof; bind the effect to that destination; retain previous text for safe undo where permitted; and report actual insertion rather than transformation quality. The model’s output-limit incidence or lexical requirement judgments are not insertion defects. Note-scope transformations keep their internal destination and code-point conversion; they must not accidentally be routed through the external queue during repair. [S-SELECTION] [S-VALIDATION] [S-SERVICE] [S-C-NOTE]

## M11 AX-Element Ownership Lead

**Lead A is substantiated as M08-AUDIT-02.** `capture_selection` applies a decision about NSWorkspace’s frontmost app, then obtains a system-wide focused element without checking its owning process. An allowed A→denied B schedule can therefore read B under A’s earlier decision. The integrated seam suite correctly tests normalized denial of A itself, but does not make authorization identity and returned element owner independent variables. [S-SELECTION] [S-HOSTS] [S-SEAM] [S-H-M11]

The narrow remedy is shared owner-bound capture, not another deny-list parser and not a new transform engine. The local proof must show zero forbidden B reads, including discarded returns, while an authorized A selection still works. It must test drift before capture and between selection/flank acquisition. Reading first and discarding later does not satisfy S12.

## Deny-Policy / M08 Reader Policy Assessment

**Lead B is substantiated for destination-content acquisition, with a deliberately narrower conclusion than “deny all operations.”** S12 says never read denied apps and says unclassifiable fields must retain plain dictation without nearby-text reading. The current M08 service does not consistently pass that read restriction to validation, readback, undo, reconciliation and observation. There is no need to infer a new policy to identify denied-field content reads as contrary to the present wording. [S-SPEC] [S-C-CONTEXT] [S-SERVICE] [S-OBSERVER]

| Operation | Minimal applicable permission | Current code / required disposition |
|---|---|---|
| M06 context collection | Owned target + normalized allow decision + positive content classification | Repaired; preserve zero-content-read behavior when denied/secure/unclassifiable. |
| Explicit M11 external selection capture | Explicit transform intent plus owned, allowed, classified field | Normalized deny check present; owner binding missing (AUDIT-02). Context-off alone is not a universal ban. |
| Plain insertion | User insertion intent, live destination authority and method safety | May remain usable without content collection; forbidden reads cannot be justified by the need to confirm. |
| Target validation | Minimal owner/window/classification metadata; selection text only when read-authorized | Identity-only degradation must not silently grant destructive replacement or content-reading capability. |
| Destination readback | Authorized bounded content read at the actual effect target | If unavailable or forbidden, retain honest unverified state rather than bypass policy. |
| Undo verification | Original destination/range authority plus current permitted bounded read | App identity/substring alone is insufficient; refuse safely when proof cannot be obtained. |
| Paste Again reconciliation | Explicit new intent plus a permitted bounded read at its chosen destination | Current whole-field substring read needs authorization and serialization; no arbitrary denied-field scan. |
| Outcome observation | Same confirmed destination + read capability + capture-bound collection permission | All three are required; confirmation does not confer perpetual read permission. |
| Internal Scratchpad | LocalFlow-owned note/document permission | Not an external AX deny-list reader; keep its independent authority model. |

A user policy change during a transaction should have a documented admission/revocation boundary. This report does not invent retrospective cancellation of every previously permitted operation. The unconditional rules are simpler: no operation starts prohibited destination-content acquisition, and delete-everywhere immediately removes the deleted job’s future read/replay/publication authority. [S-H-M02] [S-C-TRAIN] [S-STORE]

## Target Authority Assessment

Three facts must be distinguishable: **the destination promised at request time, the live target allowed by the operation’s policy, and the actual element receiving the effect.** Current app identity and title checks address only part of that relationship. Reacquiring global focus can make those three facts refer to different objects. [S-VALIDATION] [S-LEASE] [S-SERVICE]

A narrow replacement design would carry an opaque, in-memory destination capability: app identity, verified owner pid, native window/field handles where available, method permissions, typed range evidence, operation id and revocation state. Persistent rows should contain opaque identifiers/disclosures, not native object serialization or field content. Plain snapshot-less explicit repaste may choose a fresh destination, but that is a new user operation, not inherited authority from an old insertion. Strict selection, undo and observation must retain stronger original-destination proof.

This is a repair direction, not an instruction to copy the report’s names into an existing API. The local agent must use the current interfaces, minimize schema changes, and expose uncertainty on unqualified surfaces instead of silently blessing them.

## Selection / Native Range Assessment

Current M06/M11 selection capture distinguishes native host units from code points where exact conversion is possible. Current M08 validation decodes native AXValue ranges. The gaps arise later: service-local range extraction, length arithmetic, undo boxing and observer ranges do not uniformly preserve that distinction (AUDIT-05). [S-SEAM] [S-NATIVE] [S-VALIDATION] [S-SERVICE] [S-OBSERVER]

Replacement proof needs an explicit absence lattice. “Known equal,” “known different,” “not captured,” “forbidden to read,” and “temporarily unavailable” are not interchangeable. Plain no-context caret insertion can degrade gracefully; a non-empty destructive replacement cannot simply retain authority because a live check was unavailable. Strict mode must not collapse window-title and native-window identity into one success bit or silently omit both unavailable flanks (AUDIT-04).

Required native coverage includes real AXValueRef decoding, AXValue boxing for setter calls, astral prefixes, astral inserted text, combining marks, ZWJ sequences, nonzero range offsets, long prefixes where code-point mapping is unavailable, and round-trip undo. An ASCII fixture pass is not evidence for those cases. [S-C-ARTIFACT] [S-C-CONTEXT] [S-NATIVE]

## Queue / Cancellation / Duplicate Assessment

The single queue is a useful ordering boundary. It prevents normal publish/restore transactions from interleaving and keeps normal insertion work off the initiating UI callback. But FIFO ordering does not provide exactly-once effects, cancellation revocation, or reconciliation against an unresolved previous paste. [S-SERVICE] [S-RACES] [S-PIPELINE]

AUDIT-14 concerns operation identity at the final side-effect boundary and idempotent completion. It does not assert that M03’s production worker normally emits duplicate accepted results; the M03 generation and stale-message protections are retained. It also does not demand enabling the store attempt fence that M02 explicitly left unwired. A local operation id can protect effects without changing that accepted store protocol. [S-H-M02] [S-H-M03] [S-C-JOB]

AUDIT-15 requires a defined cancellation linearization point. Admission at transaction entry cannot excuse an avoidable write after revocation became visible during validation. Conversely, a cancel after post/effect cannot convert reality to “nothing inserted.” AUDIT-16 extends the same monotonic-facts principle to exceptions. The public result should remember publish/post/write/readback phases even when later persistence or restoration fails.

## AX Insertion Assessment

The direct AX method is valuable because it avoids the clipboard’s shared-payload window. Its ordinary successful path should remain available and receive its own positive controls. It still needs owner-bound target acquisition, native-range correctness, and a qualified confirmation predicate. A true return from a generic setter is not by itself a complete account of what changed or where. [S-SERVICE] [S-HOSTS]

The local adapter tests should force: unavailable settable attribute, capability changing before the setter, setter failure without effect, setter partial effect followed by failure, success-with-no-effect, exception after real effect, and a successful exact replacement. Unsupported/no-op branches must not be “fixed” by returning confirmed to preserve a benchmark. Confirmation and performance grading must observe actual helper destination bytes.

## Clipboard Transaction Assessment

Generation-owned restore, supported-flavor disclosure and no synthetic Return/Backspace are strong existing controls. Current supported flavors are plain text, RTF, HTML, PDF, PNG and TIFF; flattening into one item and unsupported file promises are disclosed limitations rather than evidence of full multi-item fidelity. [S-CLIPBOARD] [S-HOSTS] [S-C-INSERT]

The highest-priority clipboard defect is AUDIT-07: an unchanged pre-existing proper prefix is treated as a consumed partial paste. The proof obligation is not “the result looks like a prefix,” but “this transaction’s destination consumed its payload and produced this partial change.” The historical full-identical guard does not establish that property.

There is a second queue-level design obligation: retaining the first unresolved payload until a late consumer reads it cannot be claimed safe if a second queued transaction is allowed to replace that payload first. The local remediation must choose a documented pending-consumption policy—hold, quarantine/offer, or another method-specific safe refusal—rather than claiming global clipboard ownership lasts forever. This case is in the corpus even though no universal clipboard protocol is prescribed here.

AUDIT-19 addresses avoidable snapshot and acknowledgment gaps. The report deliberately does **not** claim a generation check plus native write is an atomic compare-and-swap. The publish→target-read and restore-check→write micro-windows require honest residual disclosure and manual qualification, not fabricated guarantees. [S-C-INSERT] [S-H-M08]

## Readback / Confirmation Assessment

A defensible confirmation requires the correct target, the correct owned range, a valid coordinate convention, a meaningful pre-state and a method-qualified post-state. Reading LocalFlow’s own clipboard is never destination confirmation. Current clipboard full-preexisting ambiguity is correctly conservative; current AX and missing-pre-read/no-snapshot paths are not uniformly conservative (AUDIT-06). [S-SERVICE] [S-VALIDATION] [S-RESULT]

Partial readback must remain unverified. A changed partial prefix may prove some consumption; an unchanged pre-existing prefix does not. Missing readback cannot improve a result. A no-snapshot insertion cannot become certified merely because later text happens to match while the validation path explicitly recorded no destination proof.

Confirmation certifies neither semantic correctness nor acoustic fidelity. A successful exact insertion of an erroneous transcript is still just successful insertion. `no_edit_observed`, `undo_candidate`, confirmed and posted states must remain separate from M14 correctness labels and preferences. [S-C-TRAIN] [S-C-PREF] [S-TRAINING]

## Terminal Multiline Assessment

The historical no-context terminal bypass is repaired. The service classifies the live frontmost bundle when no usable snapshot category exists, and an uncertified multiline terminal request is offered without posting. The certified bracketed-paste set is empty; the package contains no synthetic Return. These are preservation controls, not new defects. [S-SERVICE] [S-RACES] [S-C-INSERT]

Qualification still needs target drift after the guard, single-line inert input, literal commands without implicit execution, and explicit adjudication of CR-only/CRLF/Unicode separators and control characters. Those variants are **design/native probes**, not claims that a particular current terminal executes them. Test automation must use a non-executing owned helper; the real-terminal trial uses Daniel-controlled inert text and remains manual. Do not add a terminal to the certified set solely from a generic fixture pass.

## Undo / Paste Again Assessment

Undo has two distinct defects: destination ownership (AUDIT-08) and lost previous selection text on clipboard replacements (AUDIT-09). Matching inserted bytes at old offsets in a new document does not grant permission to replace that document. An unrelated edit must never be overwritten. Empty previous text is correct for caret insertion, not for an authorized replacement that overwrote a selection. [S-SERVICE] [S-LEASE] [S-ATTRIBUTION]

Paste Again has explicit user intent, but its reconcile/read/choose-target/write sequence must be one serialized operation. The current synchronous whole-field substring scan raises both policy and responsiveness concerns (AUDIT-03/17), and two pre-queue scans can both observe absence (AUDIT-14). The substring heuristic itself is already documented as approximate: this report does not reinterpret an incidental matching substring as a proven duplicate or require a new semantic classifier.

Deletion and bounded recovery lifetime apply to cached text as well as store artifacts (AUDIT-13). Keep the fixed M03 Copy Last Raw behavior and add equivalent revocation to M08’s separate cache, without deleting other users’ clipboard contents or arbitrary historical data. [S-APP] [S-H-M03] [S-H-M02]

## Observation / Attribution Assessment

Observation is the most consequential evidence seam. Current code can follow same-app, same-role focus to another field (AUDIT-10); accept ambiguous re-anchors or mis-bound after-text (AUDIT-11); start without capture consent (AUDIT-12); outlive deletion (AUDIT-13); or miss final notification in a close/subscription gap (AUDIT-18). Each requires a different invariant and a distinct regression. [S-OBSERVER] [S-SERVICE] [S-APP]

The observer’s **ability** to read a surface is not permission to read it. Nor is readback equality a durable guarantee that the next focused element is the same target. Field/window/owner identity, classification, exact range provenance, active lifecycle and collection permission all remain necessary at their respective boundaries.

M14’s `mine_observation_candidates` consumes edited observations under the premise that M08 certified their source region. That makes producer provenance a prerequisite; downstream classification cannot reconstruct an owner or span that was never reliably recorded. This is not a claim that passive observation automatically approves vocabulary changes: explicit learning approval, label and preference gates remain separate. [S-LEARNING] [S-C-TRAIN] [S-C-PREF]

## Evidence / Retention / Deletion Assessment

The current store is **schema v11**, not the schema-v4 stage described in the historical M08 handoff. M02’s durable job-deletion barrier, purge intents, lease precedence and write-time checks are accepted foundations. A raw `Store.submit` call serializes SQL but does not automatically authorize its job reference; M08’s direct insertion/observation writers must explicitly follow the store contract where necessary. [S-C-STORE] [S-STORE] [S-RECORD] [S-H-M02]

The important distinction is **continued authority versus durable resurrection**. The source shows M08 recovery caches and observers not revoked by the app’s deletion listener. The source also shows the store refusing late deleted-job content artifact writes. Therefore AUDIT-13 does not claim those artifacts are currently recreated after deletion. It calls for stopping unauthorized reads/replay and adjudicating any late content-free status rows, while preserving the barrier that already prevents resurrection.

Capture-time consent is also binding. An off-at-capture job cannot acquire passive training observation permission merely because collection is later enabled. A pause after an authorized capture started does not revoke that capture under the accepted M02 policy. Delete-everywhere is the immediate overriding operation. Preview transforms use their separately documented consent gate; explicit teaching is not blanket passive-observation consent. [S-H-M02] [S-C-TRAIN] [S-H-M11]

Content-bearing before/after values belong only in lease-governed artifacts. Rows, events and envelope blocks stay content-free; reference types, missing reasons, stage roles and previous immutable revisions must not be relabeled to make a failed observation look valid.

## Privacy Assessment

The audit corpus uses only synthetic app ids, fields, clipboard flavors and canaries. No arbitrary desktop content, private clipboard state, user database, transcript or audio was inspected. All future native tests must use an owned helper or a deliberately controlled manual surface. The existing isolation runner keeps real frameworks while blocking live-desktop AX/event calls; a pass under it is not proof that real Accessibility insertion worked. [S-ISOLATION] [S-H-M06]

Privacy tests must count acquisition, not only retention: canaries must be checked in every content read, discarded result, snapshot, artifact, envelope, diagnostic event, candidate, profile and export boundary. A later redact/discard does not repair reading a denied or secure field. Conversely, permitted minimal metadata, explicit insertion intent and collection permission must not be conflated into one global “privacy on/off” bit.

Sensitive-field transitions require native role/subrole tests. A helper can prove the code refused before a read; it does not certify every password implementation in third-party applications. Never intentionally collect real passwords to demonstrate a bug.

## Test-Oracle Assessment

The principal test fixture is coherent and useful for its intended narrow cases, but it is not an independent native authority model. It exposes one field, Python-like ranges, simplified pasteboard behavior and favorable capability responses. Real M06 native tests close some API gaps; the M08 bridge coverage does not execute native insertion/undo/observation end to end. [S-FIXTURE] [S-NATIVE] [S-SEAM]

The expanded oracle should own its own world state: independent app identity and element-owner pid; distinct windows/fields even with equal title/text; host UTF-16 ranges separate from code-point spans; an independently recorded destination revision; clipboard generations and per-flavor acknowledgment; and explicit read/effect logs. It should derive expected transitions without calling the production confirmation, range or re-anchor algorithm as its oracle.

Use Events/Barriers and completion acknowledgments to force races. Sleep may simulate a native delay, but should not decide whether the decisive interleaving occurred. Tests must drive `capture_selection`, `validate_target`, real service queue/undo/repaste, actual coordinator callbacks and real store writes. A reimplementation of the bug in a test cannot prove the repair.

Preservation controls matter: stable permitted insertion, same-field caret move, allowed selected capture, direct AX’s zero-clipboard path, user-copy restore skip, full-preexisting ambiguity, wake re-arm, deletion barrier and no implicit correctness labels must stay green. This prevents “safe because everything now refuses” false success.

## Native Verification Assessment

**No native verification ran in this audit.** Current committed native evidence is inherited and narrower than the end-to-end claims now at issue. The local agent must use Daniel’s actual `.venv`, PyObjC/ApplicationServices and Accessibility-capable owned helpers, not a cloud shim as a substitute. [S-NATIVE] [S-H-M06] [S-H-M11]

| Local qualification | Required independent witness |
|---|---|
| AXValue/UTF-16 service path | Real native range object, exact write/readback/undo bytes and typed offsets. |
| Owner/window/field binding | Two owned processes or independent owned targets; real owner pid and native element identity, equal-title/equal-text negatives. |
| Secure/unclassifiable refusal | Native role/subrole classification before every content acquisition. |
| Clipboard flavors/generations | Controlled board/helper with exact supported flavor bytes and acknowledged publication/restoration; no sampling of arbitrary user clipboard. |
| Actual UI callback | Main-thread/run-loop witness; all potentially slow AX/clipboard/store work attributed to the correct measured stage. |
| Observation and deletion | Real service/observer/store with deterministic lifecycle barriers and synthetic payloads. |

The historical M08 runbook slot is currently a placeholder beginning at M08-V001. The original human trial is recorded in M08’s handoff/results and must be carried forward into that section. Preserve M06-V003’s target-switch coverage as a cross-reference, not by marking it passed or duplicating conflicting instructions. [S-RUNBOOK] [S-H-M08]

## Performance / Benchmark Assessment

No new latency number is reported. The historical M08 figures came from a fixture benchmark; they cannot be transplanted onto current real-native behavior. The source benchmark’s separate validation timing, repeated simple insertions, submit timing and approximate observer cost do not prove every timed sample performed the safety work (AUDIT-20). The observer approximation is already disclosed; the problem is relying on it for broader qualification. [S-BENCH] [S-H-M08]

The replacement report must separate: UI enqueue/callback duration; queue wait; target validation; AX write; clipboard snapshot/publication/post; destination readback; deliberate settle wait; restore; full observer tick/re-anchor/stop; undo; and Recovery/History repaste. A long worker settle is not automatically a UI stall. A cheap submit call is not evidence that synchronous reconciliation elsewhere is cheap.

Every arm needs a validity gate before a speed verdict: exact SHA/tree/import path; interpreter/OS/framework/native permission state; process-cold versus warm labeling; sample count and denominator; p50/p95/p99 and max; exact effect/method/read/ownership evidence per sample; declared applicable budget; controlled delay conservation; and independent positive controls. Existing canonical budgets must be cited. Any additional M08 budget proposed by remediation must be labeled and justified, not retroactively attributed to the spec. [S-EVAL] [S-MILESTONES]

Six mandatory benchmark-work mutants remove validation, make insertion a no-op, skip publication, skip readback, bypass the queue, and remove ownership checks. The benchmark must become invalid or fail its declared gate, not merely become faster. Some current state assertions may already kill a no-op mutant; this audit does not falsely claim every mutant survives.

## Critical Findings

### M08-AUDIT-01 — Validation does not bind the element used for the write

**Severity:** CRITICAL · **Confidence:** High for source-level counterexample; native schedule not executed · **Category:** Destination authority / time-of-check-to-use · **Probe status:** NOT_RUN

**Canonical requirement:** S18; M08-AC01; targets invariant 1; M06 owned-element rule.

**Exact code path/symbol:** `validation._validate; validation._surroundings_verdict; InsertionService._transaction, _clipboard_insert, _await_readback; SystemInsertionHost.focused_element`. [S-SERVICE] [S-VALIDATION] [S-HOSTS] [S-LEASE] [S-C-TARGET] [S-C-CONTEXT]

**Current behavior:** Validation resolves frontmost identity and a system-focused element. The service then obtains another focused element for method selection; clipboard pre-read and the readback phase obtain focused elements again. TargetLease retains app identity, not the validated field/window handle.

**Failure mechanism:** A field from app B or another window can become the write/readback element after app A passed validation. The direct AX path can therefore write B while the result carries A’s verification. Clipboard post is also globally focused and must not inherit an old validation as current authority.

**Minimal reproduction:** Use two owned synthetic apps A/B. Validate A/W1/F1; hold at a barrier immediately after validate_target returns. Move focus to B/W2/F2, where AXSelectedText is settable, then release. Record the exact element passed to set_attribute and every readback.

**Expected:** No write to B. Refuse as target_changed, or revalidate the still-authorized destination under an explicitly defined transaction policy. A reread alone must not silently transfer authority.

**Likely actual / verification boundary:** The direct-AX branch selects F2 and calls its setter under the lease for A. This is derived from the current call sequence, not a native reproduction.

**Existing coverage:** Historical changed-app tests change the target before validation; M06 tests prove the identity helper, not this write boundary.

**Why the oracle misses it:** The principal fixture exposes one field and no independent owner PID. Passing the identity predicate is not an effect-level assertion about the later setter.

**Regression:** Barrier-driven A→B and same-app W1→W2 cases; an unchanged A/W1/F1 positive control; assert setter owner/window, paste-post target and source-bound evidence, not only result.state.

**Narrow repair:** Carry a validated, owner-checked destination object through the transaction. Recheck cancellation/authority at the last defensible effect boundary; never substitute an unchecked global element. Keep the irreducible global-keystroke focus race explicitly unqualified on unsupported surfaces.

**Downstream impact:** M06 helper stays authoritative; M11 strict accepts and M09 recovery use this service. M14 must not trust an A-attributed result produced by a write to B. M15 qualification remains blocked for affected paths.

### M08-AUDIT-07 — An unchanged pre-existing prefix is mistaken for a consumed partial paste

**Severity:** CRITICAL · **Confidence:** High for deterministic source counterexample; probe NOT_RUN · **Category:** Delayed clipboard consumption / premature restoration · **Probe status:** NOT_RUN

**Canonical requirement:** S18 clipboard correctness; M08-AC01/02/03; delayed-paste contract.

**Exact code path/symbol:** `InsertionService._clipboard_insert, _await_readback, _readback`. [S-SERVICE] [S-CLIPBOARD] [S-RACES] [S-FIXTURE] [S-C-INSERT]

**Current behavior:** _readback labels any nonempty proper prefix of the requested text as partial. _clipboard_insert restores on partial, assuming the destination consumed the paste. Unlike full-text ambiguity, partial classification does not check whether the prefix was already present before posting.

**Failure mechanism:** An observable field can remain unchanged throughout the settle window yet trigger restoration. A delayed target then consumes the restored user clipboard instead of LocalFlow’s text.

**Minimal reproduction:** Field="hel", caret=0, request="hello", old clipboard="CANARY_OLD_CLIPBOARD". Hold paste consumption beyond settle. The pre-read returns "hel"; no write occurs before the deadline. Resume target consumption only after the restore decision.

**Expected:** Unchanged prefix is ambiguous/pending, not proof of consumption. Never restore on that observation alone; the destination must not receive the old clipboard as the dictation.

**Likely actual / verification boundary:** At deadline current code returns partial, restores the old clipboard, and the delayed target can paste CANARY_OLD_CLIPBOARD. This is a predicted deterministic interleaving, not an executed result.

**Existing coverage:** Historical tests cover full identical text and a genuine truncated paste, but not a pre-existing partial prefix.

**Why the oracle misses it:** The partial fixture actually changes the field, so it validates the inference only in a favorable world.

**Regression:** Use explicit barriers for post, deadline and target consumption. Add unchanged-prefix versus genuinely changed-partial positive controls with exact destination and clipboard assertions.

**Narrow repair:** Require positive attributable change before treating partial as consumed; preserve before/after evidence and ambiguity. Retaining ownership also needs a policy for the next queued transaction while a paste is still unresolved.

**Downstream impact:** M09 retry must not double an unresolved paste. M11 clipboard replacements and M14 observer admission inherit the outcome semantics.

### M08-AUDIT-08 — Undo can replace equal text in a different field or window

**Severity:** CRITICAL · **Confidence:** High for source-level counterexample; native write requires qualification · **Category:** Destructive undo authority · **Probe status:** NOT_RUN

**Canonical requirement:** S18 target-bound undo; M08-AC04; targets invariant 4.

**Exact code path/symbol:** `InsertionService._undo_now; TargetLease`. [S-SERVICE] [S-LEASE] [S-ATTRIBUTION] [S-C-INSERT] [S-C-TARGET]

**Current behavior:** Undo verifies app identity, then selects the current focused element. It checks that the old owned offsets contain the inserted string, but does not prove the original field or window owns those offsets.

**Failure mechanism:** A different document in the same app can coincidentally hold the same text at the same offsets; equality is mistaken for ownership and newer/unrelated content is replaced.

**Minimal reproduction:** Insert "red" in A/W1/F1. Move focus to A/W2/F2 that independently contains "red" at the same range. Invoke real undo on the queue and inspect the setter’s element.

**Expected:** No write to F2. Refuse stale/no-authority undo and use a non-destructive recovery offer where appropriate.

**Likely actual / verification boundary:** Current identity and substring checks permit writing F2. The native CFRange defect may mask this path on some hosts; fixing native writes must not expose an untested authority defect.

**Existing coverage:** Existing undo tests protect changed text in the same fixture field and unsupported setters.

**Why the oracle misses it:** One-field fixtures cannot distinguish equal content from the original destination.

**Regression:** Two fields and two windows with equal text/ranges, same-role controls, unrelated edit, changed app, and valid original-field undo. Assert forbidden setters remain untouched.

**Narrow repair:** Bind undo to the exact insertion destination and an owned revision/range, not app+substring. Revoke the record on deletion and consumed undo; never use synthetic Backspace.

**Downstream impact:** M11 accepts share Recovery undo; M09 UI can trigger it. M06 same-window caret permissiveness for plain insertion does not authorize cross-field undo.

### M08-AUDIT-10 — Observation can read another field and attribute its edits to the insertion

**Severity:** CRITICAL · **Confidence:** High for missing identity/subrole checks; controlled native proof NOT_RUN · **Category:** Outcome attribution / sensitive-field transition · **Probe status:** NOT_RUN

**Canonical requirement:** S29.8 exact target/job/region; M08-AC05; secure-field stop rule.

**Exact code path/symbol:** `OutcomeObserver tick/target checks; TargetLease; SystemInsertionHost`. [S-OBSERVER] [S-LEASE] [S-HOSTS] [S-ATTRIBUTION] [S-LEARNING] [S-C-TRAIN]

**Current behavior:** Each observation tick obtains the current focused element after checking app identity and role. The lease has no original field/window identity. The secure check inspects role text rather than the full M06 role/subrole classification.

**Failure mechanism:** Same-app, same-role field changes can remain eligible and be read/retained as the original insertion. A native AXTextField with secure subrole is not safely covered by a role-only check.

**Minimal reproduction:** Confirm a synthetic insertion in A/W1/F1, then focus A/W2/F2 with the same role and a canary at the owned range. Tick explicitly. Separately transition to AXRole=AXTextField, AXSubrole=AXSecureTextField before a tick.

**Expected:** Stop before content read on owner/window/field loss or secure/unclassifiable transition. No F2 canary may enter observation artifacts, envelopes, candidates or logs.

**Likely actual / verification boundary:** The same-role foreign field can be read and an owned_range_edited record can be created. Whether a real secure control returns content is not assumed; attempting the prohibited read is itself testable.

**Existing coverage:** Historical observation tests change app/role, use a Secure role string, and test same-field edits.

**Why the oracle misses it:** The fixture does not model independent element identity/window/subrole transitions.

**Regression:** Identity-rich two-field observer tests and native role/subrole helper controls. Run the real observer producer through the real store and inspect before/after artifacts, not just stop_reason.

**Narrow repair:** Bind observer reads to the confirmed destination capability, require current classification before each content read, and stop with explicit unavailable/lost-authority reasons. Confirmation alone is not permanent field certification.

**Downstream impact:** M14 currently assumes owned_range_edited observations have trustworthy target attribution. This does not imply automatic dictionary approval, which remains separate.

## High Findings

### M08-AUDIT-02 — M11 capture authorizes app A but can read app B’s element

**Severity:** HIGH · **Confidence:** High for missing owner check; native interleaving not executed · **Category:** Lead A / pre-transform privacy and selection authority · **Probe status:** NOT_RUN

**Canonical requirement:** S12; M11-AC03 at the M08 boundary; M06 ownership contract.

**Exact code path/symbol:** `insertion.selection.capture_selection; AppDelegate._m11_capture_selection; SystemInsertionHost.focused_element`. [S-SELECTION] [S-HOSTS] [S-SEAM] [S-APP] [S-C-CONTEXT] [S-C-TRANSFORM]

**Current behavior:** The repaired capture applies the shared normalized app-deny decision to the frontmost app, then requests the system-focused element without verifying its owning process.

**Failure mechanism:** A focus change after authorizing A can expose B’s selected text and flanks under A’s metadata. B may be a denied app even though its field is not a password field. Checking B’s role/subrole does not prove B was authorized.

**Minimal reproduction:** Authorize allowed A, pause before focused_element, switch to denied B with a synthetic selection CANARY_B_SELECTION, return B’s element, resume. Capture all content-bearing AX calls and any created snapshot.

**Expected:** Zero B content reads; owner mismatch refuses or restarts a newly authorized capture before content acquisition. Do not merely discard B’s text after reading it.

**Likely actual / verification boundary:** The current reader reaches B’s selection/flanks while the earlier app decision remains A’s. Runtime/native verification is required for the real adapter.

**Existing coverage:** test_selection_capture_m06_seam checks normalized deny, invalid configuration, astral ranges and strict native-window mismatch.

**Why the oracle misses it:** The seam host does not model app identity and focused-element owner as independently changing facts.

**Regression:** An owner-PID drift barrier plus allowed-A positive control, denied-A zero-read control, and a switch between selection and flank reads.

**Narrow repair:** Reuse M06’s app-owned element acquisition and AXUIElementGetPid verification through the shared insertion host. Freeze one authorized element; preserve the repaired normalized deny logic.

**Downstream impact:** M11 semantic gate, retry/task identity and model quality are not reopened. M08 only owns the capture/destination boundary that consumes their result.

### M08-AUDIT-03 — M08 destination-content readers lack the applicable deny and sensitive-field gate

**Severity:** HIGH · **Confidence:** High for read paths and canonical prohibition; precise metadata policy must remain explicit · **Category:** Lead B / operation-specific privacy authorization · **Probe status:** NOT_RUN

**Canonical requirement:** S12 “Never read … denied apps”; training_evidence consent; M06 secure/unclassifiable metadata policy.

**Exact code path/symbol:** `validation._validate; InsertionService._clipboard_insert, _reconciled_repaste, _undo_now; OutcomeObserver; SystemInsertionHost`. [S-SPEC] [S-C-CONTEXT] [S-C-TRAIN] [S-VALIDATION] [S-SERVICE] [S-OBSERVER] [S-CONFIG]

**Current behavior:** These readers do not receive/use the normalized deny decision as a content-read permission. Paste Again reads up to 200,000 characters before queueing. Validation may proceed with no field context; readback and later observation then still read content.

**Failure mechanism:** Context denial is treated as missing context, rather than as a prohibition on destination-content reads. Explicit intent to paste does not inherently authorize reading unrelated field content. Secure classification is also not consistently applied before these reads.

**Minimal reproduction:** Use a denied app with an ordinary text field containing CANARY_DENIED; provide a PTT identity-only snapshot. Drive validation, readback, undo and Paste Again separately. Count every string/range/value read even when its return is later discarded.

**Expected:** No destination-content read in a denied app under the current S12 wording. Plain insertion/copy may remain available without nearby-text reads and must stay unverified where proof is prohibited. Metadata needed to decide ownership/classification is a separately documented minimum.

**Likely actual / verification boundary:** Content reads occur in the current operations. This is not an assertion that context_enabled=false must disable explicit transforms, or that denial must prohibit all writes.

**Existing coverage:** M06 and the integrated M11 deny tests protect their collectors; M08 fixture tests mainly omit the deny policy.

**Why the oracle misses it:** No operation-by-operation oracle spans all M08 read entry points; lack of retained content is weaker than zero prohibited acquisition.

**Regression:** Freeze the reader-policy matrix in this report; test denied/unclassifiable/secure/ordinary fields independently across each operation, plus context-off and explicit-selection positive controls.

**Narrow repair:** Introduce an explicit read capability separate from insertion capability, sourced from the shared normalized policy. Gate content before acquisition; retain truthful unverified/copy-only fallbacks. Do not invent a broader ban on permitted metadata or explicit writes.

**Downstream impact:** M06 and M11 must share one normalization policy. M09 recovery and M14 observation must not bypass it. M02 collection permission remains a different axis.

### M08-AUDIT-04 — Missing replacement proof can still grant destructive selection authority

**Severity:** HIGH · **Confidence:** High for consumer branches; producer-dependent reachability is stated · **Category:** Selection authority / strict proof completeness · **Probe status:** NOT_RUN

**Canonical requirement:** S12 selection invalidation; S18; M08-AC04; current strict-replacement contract.

**Exact code path/symbol:** `validation._validate and validate_target; _surroundings_verdict`. [S-VALIDATION] [S-C-INSERT] [S-C-CONTEXT] [S-SEAM] [S-H-M06]

**Current behavior:** Plain replacement can retain replace_selection when the live selected range/text is unavailable. Strict validation requires one combined window=pass flag: a matching title can satisfy it when a native window is missing. If both captured flanks are None, the strict surroundings check is skipped.

**Failure mechanism:** A missing observation is treated as a weaker successful check rather than loss of destructive authority. Distinct proof obligations—native window and title—are collapsed into one flag.

**Minimal reproduction:** Case A: a recorded non-empty selection, then make live range/text unavailable and inspect the lease. Case B: a strict snapshot with matching title/role/range/text but missing live AXWindow or both missing flanks. Keep an intact strict-capture control.

**Expected:** Preserve the accepted plain moved-caret behavior, but do not authorize destructive replacement from missing required proof. Strict replacement must positively satisfy each documented requirement or offer the result for manual use.

**Likely actual / verification boundary:** Current plain code can return a replacement lease with selection=unavailable; strict code can report strict=pass without every independent proof. Native impact requires the local host tests.

**Existing coverage:** M06 repaired the producer that retained an over-budget unkept selection; this report does not reopen that producer bug. M11 tests cover a positive native-window mismatch, not each missing-proof arm.

**Why the oracle misses it:** Tests cover mismatches more often than missing facts. Combined verification fields hide which window fact was actually proved.

**Regression:** Remove one proof at a time from a valid snapshot; assert authority cannot increase. Exercise the actual public validation consumer, not a hand-copied predicate.

**Narrow repair:** Separate write modes and proof fields (caret insertion versus replacement; window handle versus title; selection and surroundings). Preserve the M06 policy that a same-field caret move remains allowed.

**Downstream impact:** M11 selected-text accept must fail closed; plain M06/M08 behavior must not be tightened indiscriminately. M09 retry has a distinct explicit-intent contract.

### M08-AUDIT-05 — Native AX range handling is repaired at validation, not end to end

**Severity:** HIGH · **Confidence:** High for code mismatch; real native effects NOT_RUN · **Category:** AXValue boxing / UTF-16 versus code-point coordinates · **Probe status:** NOT_RUN

**Canonical requirement:** artifacts text-offset contract; S29.4; M06 D8; S18 owned-range safety.

**Exact code path/symbol:** `InsertionService._current_range, _ax_insert, _await_readback, _readback, _undo_now; OutcomeObserver; SystemInsertionHost.set_attribute`. [S-SERVICE] [S-HOSTS] [S-OBSERVER] [S-VALIDATION] [S-NATIVE] [S-FIXTURE] [S-C-ARTIFACT] [S-C-NOTE]

**Current behavior:** Validation uses ax_range, but _current_range reads .location/.length directly. Owned ends combine a host-native start with Python len(text). Undo sends a bare CFRange through the generic native setter. Observation uses the resulting bounds.

**Failure mechanism:** A real AXValueRef is not the fixture’s Python range. Astral characters make host UTF-16 lengths differ from code-point lengths. The range can be unreadable, truncated, shifted or incorrectly labeled; unboxed native range writes may fail.

**Minimal reproduction:** In an owned native helper, place A😀B before the caret and insert X😀Y; repeat selection replacement and undo, then a combining/ZWJ string. Inspect actual native ranges, destination bytes and exported coordinate metadata.

**Expected:** Use typed host-native ranges for AX calls; convert to code points only when exact and label both conventions. Decode and box real AXValue ranges through the accepted M06 adapter. Unsupported conversion must not create a guessed range or confirmation.

**Likely actual / verification boundary:** Fixture success can conceal failed native _current_range/undo and wrong length calculations. Runtime/native verification required; this audit does not claim a measured macOS failure.

**Existing coverage:** test_native_ax qualifies M06 and selected M08 validation/string-for-range bridges, not native service insertion, undo and observer end to end.

**Why the oracle misses it:** fixture_target uses Python offsets and a location/length object; ASCII-only bridges have no unit discrepancy.

**Regression:** Native service-level tests must assert exact field bytes, host ranges, exported code-point ranges, method and real setter effects for ASCII, BMP, astral, combining and ZWJ cases.

**Narrow repair:** Keep one typed range adapter; never add a second incompatible conversion. Separate host ranges from artifact offsets in names/types, and preserve honest null-with-reason when an exact conversion is unavailable.

**Downstream impact:** M06 native helpers are reused, not replaced. M11 external selections and M14 observation regions depend on this; internal Scratchpad code-point handling stays separate.

### M08-AUDIT-06 — Post-write text equality can overstate insertion confirmation

**Severity:** HIGH · **Confidence:** High for source-level proof gap; native no-op behavior requires qualification · **Category:** Confirmation provenance · **Probe status:** NOT_RUN

**Canonical requirement:** S18; M08-AC03; pre-write consistency requirement; validation’s no-snapshot downgrade.

**Exact code path/symbol:** `InsertionService._ax_insert, _clipboard_insert, _await_readback; validation._validate`. [S-SERVICE] [S-VALIDATION] [S-RACES] [S-C-INSERT] [S-RESULT]

**Current behavior:** AX precheck is merely an available range, not pre-write content consistency. Clipboard pre_content=None does not prevent a later match from confirming. No-snapshot validation says posted_unverified in its contract/comment, but the service may promote a matching readback to confirmed and start observation.

**Failure mechanism:** Matching bytes alone do not prove that this transaction produced them at the intended region. Missing authority or an absent pre-read can be obscured by a later equal read.

**Minimal reproduction:** Use a helper whose setter reports success but performs no write over an already matching substring; separately return None for the pre-read and matching bytes later; separately submit without a target snapshot. Record true effect count independently of result.state.

**Expected:** Confirmation must satisfy the documented authority and pre/post consistency predicates. An indistinguishable no-op remains ambiguous unless a separately qualified method-specific acknowledgment supplies equivalent proof.

**Likely actual / verification boundary:** Current AX and missing-pre-read branches can report confirmed in these controlled worlds. A native setter no-op is a proposed qualification case, not an observed platform incident.

**Existing coverage:** The historical identical-preexisting fix applies to clipboard full-text equality and is still present.

**Why the oracle misses it:** The AX branch and missing-pre-read/no-target variants are not covered by that clipboard-only test.

**Regression:** Cross method × pre-read available/unavailable × identical/prefix/different × actual effect/no-op. Assert actual bytes and effect logs; keep a genuine successful AX replacement control.

**Narrow repair:** Centralize a method-qualified confirmation predicate that consumes authority, coordinate certainty, pre-read and post-read evidence. Preserve posted_unverified rather than fabricating proof.

**Downstream impact:** M14 cannot treat false confirmation as field certification. M09 status and retry reconciliation must retain unknown physical outcomes.

### M08-AUDIT-09 — Clipboard-path selection replacement loses the overwritten text needed by undo

**Severity:** HIGH · **Confidence:** High for unconditional before_text value · **Category:** Undo recovery fidelity · **Probe status:** NOT_RUN

**Canonical requirement:** S18 recovery undo; M08-AC04; preserve selected-text replacement history.

**Exact code path/symbol:** `InsertionService._clipboard_insert and _remember_undo`. [S-SERVICE] [S-ATTRIBUTION] [S-C-INSERT]

**Current behavior:** AX replacement captures previous selected text before writing. Clipboard insertion always stores before_text="", even when the lease represents a non-empty replacement.

**Failure mechanism:** A later supported undo removes the inserted text but cannot restore the replaced selection; an unsupported undo also has no previous text to offer.

**Minimal reproduction:** Select "old wording", make AXSelectedText temporarily non-settable so insertion uses clipboard, paste "new wording". Then make the owned helper support range/text setters and invoke undo; also test the unsupported recovery offer.

**Expected:** Undo restores exactly "old wording" in the still-owned region or offers that retained text non-destructively. Caret insertion legitimately has empty before_text.

**Likely actual / verification boundary:** Current clipboard undo record contains empty previous text. Native capability changes are a test setup, not a claim that every external app changes capability this way.

**Existing coverage:** Existing replacement/undo tests exercise the AX path or caret insertion.

**Why the oracle misses it:** The clipboard method’s history field is not asserted for selection replacement.

**Regression:** Parameterize replacement/caret × AX/clipboard × later undo supported/unsupported; assert exact previous text and ownership.

**Narrow repair:** Capture the authorized overwritten selection before clipboard publication and retain it under a bounded recovery lifetime; refuse to fabricate an undo record if capture is forbidden or uncertain.

**Downstream impact:** M11 selected transforms frequently need this recovery behavior. M02 deletion must revoke the cached text, not just durable artifacts.

### M08-AUDIT-11 — Re-anchoring and changed-length edits can manufacture an owned edit

**Severity:** HIGH · **Confidence:** High for conflated branches; exact runtime examples require local probes · **Category:** Observation range provenance / ambiguity · **Probe status:** NOT_RUN

**Canonical requirement:** S29.8 bounded exact region; M08-AC05; unavailable must not become attribution.

**Exact code path/symbol:** `OutcomeObserver range read, re-anchor search and close`. [S-OBSERVER] [S-ATTRIBUTION] [S-C-TRAIN] [S-LEARNING]

**Current behavior:** Re-anchoring accepts the first nearby matching text occurrence. Search failure/read failure/deadline exhaustion are not an ownership proof. Changed-length edits are inspected with old bounds; when the field shrinks, a whole remaining-field fallback is possible.

**Failure mechanism:** Repeated text can move the owned region to a different occurrence. An unsuccessful or incomplete search can be treated as an edit rather than unknown. Fixed old length can truncate a longer correction or include adjacent non-owned text after a shorter one.

**Minimal reproduction:** Create two equal occurrences near the insertion; remove the true owned occurrence while leaving the other. Separately inject range-read failure or exhaust the re-anchor deadline; separately replace an owned word with a longer/shorter word beside a canary suffix.

**Expected:** Only unambiguous, bounded, same-field provenance may re-anchor. Read failure, multiple candidate matches and exhausted search stop as unavailable/ambiguous. After-text excludes unrelated suffix/prefix content.

**Likely actual / verification boundary:** Current branches can choose the first equal occurrence or close as owned_range_edited without exact after-region proof. Runtime verification required for each branch; no empirical false-label count is claimed.

**Existing coverage:** Tests include benign outside-prefix movement, equal-length edits, unreadable surfaces and a re-anchor time bound.

**Why the oracle misses it:** They do not supply adversarial duplicate occurrences, independently bounded after-region truth and read-failure versus edit oracles.

**Regression:** Independent span/revision model, duplicate-occurrence negative controls, inserted-text length ladder and failures at every read. Deadline exhaustion must never count as edit evidence.

**Narrow repair:** Represent re-anchor results as matched_unique/ambiguous/unavailable/deadline, not one bool. Require boundary evidence for changed-length edits; abstain rather than retain the remaining document.

**Downstream impact:** M14 classification cannot recover lost target provenance. M02 lease hygiene alone does not make a wrong region valid evidence.

### M08-AUDIT-12 — Outcome observation writes training artifacts without capture consent

**Severity:** HIGH · **Confidence:** High for admission path and independent writes · **Category:** Opt-in collection boundary · **Probe status:** NOT_RUN

**Canonical requirement:** S29.2; training_evidence opt-in; M02 capture-time consent adjudication.

**Exact code path/symbol:** `InsertionService._observe; OutcomeObserver.begin/close; AppDelegate observation callbacks`. [S-SERVICE] [S-OBSERVER] [S-TRAINING] [S-C-TRAIN] [S-H-M02] [S-CONFIG]

**Current behavior:** _observe starts for a confirmed result and a positive observation window. It does not require the capture’s training permission. The observer writes training-class before/after artifacts and leases itself; the later collector’s ctx/consent guard cannot undo those earlier writes.

**Failure mechanism:** A job captured while collection is disabled can still produce durable training observation content. A null collector context is not the same as preventing the independent observer producer.

**Minimal reproduction:** Create an ordinary job with capture-time consent=false and the default positive observation window. Confirm insertion through the real service, then edit the owned region. Query observation rows, training artifacts and leases.

**Expected:** No training-content observation for this capture. An insertion result may still be recorded as operational metadata. Preserve M02’s rule that a pause after an already-consented capture starts is not retroactive revocation; deletion is the immediate barrier.

**Likely actual / verification boundary:** Current observer admission and direct writes allow content retention for the opt-out capture. This is a source-derived path, not a claim about Daniel’s live consent or stored data.

**Existing coverage:** Collector consent tests do not exercise the independently writing M08 observer with capture permission off.

**Why the oracle misses it:** Tests infer no collection from a missing training revision while the observer may already have created artifacts.

**Regression:** Off-at-capture, on-at-capture, enable-after-capture, pause-after-authorized-capture, retry with original-and-current permission and deletion controls; inspect all artifact/lease/observation surfaces.

**Narrow repair:** Pass a capture-bound observation permission into the insertion request and gate before the first observation content read/write. Reuse the established consent revision semantics; do not replace them with a simplistic current-global-flag check.

**Downstream impact:** M02 semantics must remain unchanged. M11 candidate consent and explicit teaching are separate authorization paths, not blanket permission for passive observation.

### M08-AUDIT-13 — Deletion does not revoke M08’s cached undo/repaste and active observer authority

**Severity:** HIGH · **Confidence:** High for missing M08 listener integration; durable artifact guard is intact · **Category:** Deletion / recovery-cache lifecycle · **Probe status:** NOT_RUN

**Canonical requirement:** S29.14 delete-everywhere; M03 cache revocation boundary; M08 recovery authority.

**Exact code path/symbol:** `AppDelegate._on_job_deleted; InsertionService._undo_record/_last_text; OutcomeObserver; insertion.record`. [S-APP] [S-SERVICE] [S-OBSERVER] [S-RECORD] [S-STORE] [S-H-M02] [S-H-M03]

**Current behavior:** The app deletion listener revokes active jobs, context and worker/recovery caches, but does not revoke M08’s remembered insertion text or active observers. M08 raw metadata writers also do not consult the job-deletion helper.

**Failure mechanism:** After deletion, Recovery Paste Again can still use the service’s cached text; the observer can continue reading even though its eventual artifact write is barred. Late content-free metadata may still be written. These are not evidence that M02’s text-artifact tombstone barrier is broken.

**Minimal reproduction:** Insert a synthetic job, delete_everywhere(job), then invoke service.paste_again and tick its observer. Assert read/write/cache effects. Separately hold a publication before and after the store’s deletion op.

**Expected:** Deleted jobs lose future M08 replay/read authority and cached payloads. Durable content must not resurrect; the existing M02 barrier must continue refusing it. Content-free tombstones/status records need an explicit, non-resurrecting policy.

**Likely actual / verification boundary:** Current service cache remains usable and observer admission/lifetime is not deletion-aware. Store artifact writes for the deleted job are expected to be refused by the existing M02 barrier.

**Existing coverage:** M03 tests cover Copy Last Raw and recovery caches; M02 tests cover durable late evidence.

**Why the oracle misses it:** Neither proves revocation of the separate M08 _last_text/undo_record and observer instances.

**Regression:** Real Store.delete_everywhere through the registered listener; then all M08 public recovery/read APIs. Test delete-before-insert, after-insert, during-observer publication and after retirement.

**Narrow repair:** Add a flag-only M08 revoke_job hook to the existing deletion listener without nested writer waits. Clear matching caches, fence queued work and stop observers. Use writer-side tombstone checks for new durable M08 records where required.

**Downstream impact:** Preserve M02’s schema-v11 authority and M03’s deletion arbitration. M09 recovery and M14 mining must see revoked M08 state, not retained replay authority.

### M08-AUDIT-14 — The insertion boundary lacks operation identity for duplicate delivery and queued repaste reconciliation

**Severity:** HIGH · **Confidence:** High for service behavior; upstream normal-delivery protections acknowledged · **Category:** Exactly-once effects / operation identity · **Probe status:** NOT_RUN

**Canonical requirement:** jobs idempotent transitions and stale attempts; M08-AC01; S18 retry reconciliation.

**Exact code path/symbol:** `InsertionService.submit/_run/_reconciled_repaste; AppDelegate._insertionDone_/_retire_active_job`. [S-SERVICE] [S-APP] [S-C-JOB] [S-PIPELINE] [S-RACES] [S-H-M02] [S-H-M03]

**Current behavior:** Each submit creates a new transaction without a consumed-operation fence. Paste Again reconciles before joining the queue. Completion retirement decrements pending on each delivery rather than proving first completion.

**Failure mechanism:** Two deliveries of the same insertion intent can cause two writes. Two repaste checks can both see absence before either queued write occurs. A duplicate completion can retire/decrement twice. The upstream M03 supervisor already rejects stale worker messages; this finding is the missing final effect boundary, not a claim that normal worker delivery is known duplicated.

**Minimal reproduction:** Call submit twice with the same explicit test operation id/job/attempt and use barriers before consumption; separately invoke two reconciliation requests while holding the queue. Deliver the same completed result twice to the coordinator and observe pending/job state.

**Expected:** One effect and one retirement per operation. A deliberate new user repaste receives a distinct intent id and is not globally prohibited merely because job_id matches.

**Likely actual / verification boundary:** The service has no operation id/consumed ledger; repeated submissions are independent writes. Controlled duplicate delivery remains to be run through actual callers.

**Existing coverage:** Existing two-job tests prove serialization/order, not idempotency of one intent; M03’s stale-frame rejection remains valuable.

**Why the oracle misses it:** A queue orders work but does not deduplicate it; a store transition being idempotent does not undo a second physical paste.

**Regression:** Duplicate submit/callback, stale attempt, retired generation, two explicit intents and original-paste-still-pending matrix; assert effect counts and pending exactly once.

**Narrow repair:** Add an operation-level identity/fence at the parent’s side-effect boundary and idempotent completion. Run repaste reconciliation and destination binding on the queue. Preserve explicit new-intent semantics and M02’s adjudicated store attempt policy.

**Downstream impact:** M03 supervisor logic is not broadly rewritten. M09 repaste and M11 accepts need compatible intent identity; M13 usage totals must not hide doubled physical effects.

### M08-AUDIT-15 — Cancellation can arrive after the only check but before an avoidable write

**Severity:** HIGH · **Confidence:** High for check placement; product linearization must be explicit · **Category:** Cancellation / effect-boundary revocation · **Probe status:** NOT_RUN

**Canonical requirement:** jobs invariant 3; M08 architecture: old result has no insertion authority after cancellation.

**Exact code path/symbol:** `InsertionService._transaction/_ax_insert/_clipboard_insert; AppDelegate cancellation and completion`. [S-SERVICE] [S-APP] [S-PIPELINE] [S-C-JOB] [S-MILESTONES]

**Current behavior:** The service checks job.cancelled at transaction entry, then performs validation and potentially several reads before writing/publishing/posting. No later admission check fences a cancellation that occurs during those steps.

**Failure mechanism:** A cancellation observed before the irreversible effect may still be ignored because the transaction was admitted earlier. This is distinct from cancellation after an actual insertion, which must keep the real physical outcome.

**Minimal reproduction:** Hold after validation but before AXSelectedText write; cancel the same mutable job, then release. Repeat after clipboard publication but before post, and after an independently witnessed physical insertion.

**Expected:** Before-effect cancellation prevents further avoidable effects. After-effect cancellation preserves posted/confirmed/unknown facts and never retroactively reports zero insertion. Specify the linearization point and residual native race.

**Likely actual / verification boundary:** Current early-only check permits the pre-write schedule to proceed. The coordinator’s existing cancelled_after_insert reporting is a strength to preserve.

**Existing coverage:** The pipeline cancel-after-insert test constructs a result rather than forcing the real service schedule; pre-cancelled admission is tested.

**Why the oracle misses it:** The decisive interleaving between validation and physical effect is not forced by a barrier.

**Regression:** Cancellation before validation, before publish/write, before post, after post and after effect; audit both destination and clipboard ownership under each schedule.

**Narrow repair:** Use a revocable operation capability checked at effect admission; never hold broad locks across slow AX/store calls. Define recovery for published-but-unposted text without overwriting a user copy.

**Downstream impact:** M03 cancellation semantics and M02 durable state remain authoritative. M09 status must not erase late physical effects or offer blind retry.

### M08-AUDIT-16 — A late exception can erase known physical effects and method provenance

**Severity:** HIGH · **Confidence:** High for exception fallback; injected failure NOT_RUN · **Category:** Failure-state truth / unsafe retry risk · **Probe status:** NOT_RUN

**Canonical requirement:** S18 honest outcomes; M08-AC03; event/evidence lineage.

**Exact code path/symbol:** `InsertionService._run and _clipboard_insert/_ax_insert/_finish`. [S-SERVICE] [S-RESULT] [S-RECORD] [S-APP] [S-RACES]

**Current behavior:** The outer catch constructs a fresh failed result with method=none and a new insertion id. It has no phase ledger showing whether a publish, post or write already occurred; this fallback does not follow the usual persisted _finish path.

**Failure mechanism:** A readback/restore/helper exception after a real write can be reported like a pre-write failure. A user may retry text already inserted, while evidence loses the original method and transaction identity.

**Minimal reproduction:** Use a controlled host that performs the AX write, then raises on readback; separately post/consume clipboard paste, then raise during restore. Inspect returned result, event and insertion row.

**Expected:** Keep the original insertion id and all known phases. Unknown confirmation after a known post is posted_unverified with a reason, not evidence of no effect; a persistence failure is separate from physical failure.

**Likely actual / verification boundary:** Current outer fallback returns failed/method none without the known physical-phase record. Runtime fault-injection required.

**Existing coverage:** Historical failed-paste tests cover a reported post failure, not arbitrary exceptions after an independently observed effect.

**Why the oracle misses it:** The oracle primarily checks result states in successful paths and does not reconcile effects with failure records.

**Regression:** Fault at every phase boundary plus after-effect controls; assert no loss of known effects, no duplicate retry and content-free diagnostics.

**Narrow repair:** Track a stable transaction object and monotonic phase facts. Finalize one truthful result on every path; isolate evidence persistence from actual destination outcomes.

**Downstream impact:** M02 outcomes and M09 retry decisions require this distinction; M14 must never infer absence/success from a catch-all state.

## Medium Findings

### M08-AUDIT-17 — Recovery Paste Again performs AX reads on the UI caller and outside queue serialization

**Severity:** MEDIUM · **Confidence:** High for call graph; measured UI cost unavailable · **Category:** UI responsiveness / timing-boundary gap · **Probe status:** NOT_RUN

**Canonical requirement:** S24 UI-thread rule; insertion contract queue ownership; M08 benchmark requirement.

**Exact code path/symbol:** `AppDelegate.pasteAgain_/hubPasteText; InsertionService._reconciled_repaste; benchmark_m08`. [S-APP] [S-SERVICE] [S-PIPELINE] [S-BENCH]

**Current behavior:** Ordinary _finishWithText_ queues insertion promptly. However, the Recovery/History repaste APIs call _reconciled_repaste synchronously, where field length and up to 200,000 characters are read before submit. Completion/fallback persistence also needs its own measured boundary.

**Failure mechanism:** The nominally asynchronous operation can block the real UI callback on AX reads. The existing benchmark times submit, not these entry points; its enqueue figure cannot establish menu latency.

**Minimal reproduction:** Invoke actual Recovery and History entry methods on the main thread with a controlled delayed AX reader and a busy insertion queue. Record thread identities and callback duration; keep ordinary submit as a positive control.

**Expected:** UI callback only schedules bounded work; reconciliation and ownership checks execute on the serialized worker. Distinguish enqueue, queue wait and execution cost.

**Likely actual / verification boundary:** Synchronous reader calls run in the caller. The duration on Daniel’s Mac is NOT_RUN, and no 0.6-second UI stall is asserted.

**Existing coverage:** Queue tests and the submit microbenchmark prove the normal service entry, not menu/hub repaste callbacks.

**Why the oracle misses it:** Inline callAfter shims and direct service tests erase actual thread identity and run-loop behavior.

**Regression:** Real coordinator entry-point tests with named-thread assertions and delay conservation; measure callback/queue/AX separately.

**Narrow repair:** Move the complete reconcile-and-submit operation into the queue and deliver its outcome asynchronously; benchmark actual UI entry points without running arbitrary desktop reads.

**Downstream impact:** M09 recovery/focus guard is the direct consumer. Do not rewrite unrelated Hub or M14 test races.

### M08-AUDIT-18 — Observation close can fall between the early-close check and callback installation

**Severity:** MEDIUM · **Confidence:** High for deterministic check/assignment race · **Category:** Final evidence publication / callback lifecycle · **Probe status:** NOT_RUN

**Canonical requirement:** S29.8 final stop reason; M08 outcome-envelope completion.

**Exact code path/symbol:** `AppDelegate._observationStarted_ and _observationFinished_; OutcomeObserver close/on_closed`. [S-APP] [S-OBSERVER] [S-PIPELINE] [S-C-TRAIN]

**Current behavior:** The app correctly handles an observer already closed before _observationStarted_. It then checks stop_reason and, if still open, assigns on_closed in a separate operation.

**Failure mechanism:** Close can occur after the None check but before callback installation. The observer closes without the handler; the newly assigned handler is not called retroactively, leaving final envelope publication/cleanup missing.

**Minimal reproduction:** Pause _observationStarted_ immediately after the open check; close the observer while on_closed is unset; resume handler assignment. Count final observation callback and envelope revision exactly once.

**Expected:** Atomic subscribe-or-deliver semantics: a close before, during or after subscription produces one final notification.

**Likely actual / verification boundary:** Current separate check/assignment can miss the notification. The earlier historical early-close repair is present and is not misreported as absent.

**Existing coverage:** The current early-close branch covers closure before the check, not inside the check-to-assignment gap.

**Why the oracle misses it:** Immediate callback shims do not force this two-thread schedule.

**Regression:** Three latch schedules: close-before-check, close-in-gap, close-after-subscription; final callback exactly once in every case.

**Narrow repair:** Have the observer own a lock-protected completion subscription API with an immutable final snapshot, or register before start. Preserve non-blocking UI dispatch.

**Downstream impact:** M02 final revision and M14 mining/readiness see the closed observation; no change to judgment semantics.

### M08-AUDIT-19 — Clipboard snapshot and native acknowledgment are weaker than their disclosures

**Severity:** MEDIUM · **Confidence:** High for missing checks; native behavior requires local proof · **Category:** Clipboard consistency / adapter acknowledgment · **Probe status:** NOT_RUN

**Canonical requirement:** S18 supported-format preservation; M08-AC02; honest result disclosure.

**Exact code path/symbol:** `ClipboardTransaction.capture/publish/restore_if_owned; SystemPasteboard clear_and_write_text/restore_items`. [S-CLIPBOARD] [S-HOSTS] [S-FIXTURE] [S-RACES] [S-C-INSERT]

**Current behavior:** Capture samples generation and multiple representations without an end-of-snapshot consistency check. Native pasteboard write return values are not all propagated as success/failure. Generation-owned restore itself is present.

**Failure mechanism:** A user copy during capture can produce a mixed snapshot or be overwritten by publication without a documented conflict decision. Native failure can still be disclosed as restored/captured formats even when the operation was not acknowledged.

**Minimal reproduction:** Hold capture between generation and flavor reads while the user replaces all flavors; separately return false from a native helper’s setString/setData/writeObjects while checking the actual board afterward.

**Expected:** Consistent snapshot or explicit conflict/unsupported disposition; truthful publish/restore acknowledgments. Preserve a user copy at every avoidable boundary.

**Likely actual / verification boundary:** The current adapter lacks these end-to-end checks. This is not a claim that an NSPasteboard generation check and write can be made fully atomic.

**Existing coverage:** Fixtures model board operations more atomically and mainly test user copy during settle.

**Why the oracle misses it:** The test board reports successful writes and cannot represent mixed-generation flavor capture/native false acknowledgment.

**Regression:** Barrier-controlled multi-flavor changes, false return values and exact native readback in an isolated board; assert disclosure equals actual supported restored data.

**Narrow repair:** Recheck snapshot consistency, propagate write acknowledgments, expose conflicts and bound retry. Keep unavoidable check-then-write windows explicit rather than promising universal clipboard atomicity.

**Downstream impact:** M09 recovery disclosure and M11 clipboard fallback benefit; no change to unsupported file-promise policy is implied.

## Low Findings

No standalone Low-severity production finding is raised. Maintenance preferences, deliberate clipboard flattening and unrelated subsystem observations are not inflated into findings. This does not imply every low-risk line of the repository was exhaustively reviewed.

## Test Gaps

### M08-AUDIT-20 — The benchmark does not independently prove its measured production work

**Classification:** TEST GAP, acceptance-blocking for the affected claim—not a counted production defect. **Confidence:** High from benchmark inspection; mutants NOT_RUN. **Status:** NOT_RUN.

**Requirement:** M08 separate overhead/verification benchmark; E10/E11; requested work-validity mutation gate. **Location:** `scripts/v2/benchmark_m08.py`. [S-BENCH] [S-EVAL] [S-MILESTONES] [S-FIXTURE]

**Current coverage:** Validation is timed separately from insertion; insertion checks a result state on a simple repeated fixture. The UI measurement is service submit, not actual menu/Hub entry points. Observer cost is an approximation, not a full observer measurement.

**Mechanism:** Removing validation from the insertion path can leave a separate validation microbenchmark intact. Skipped ownership checks can survive a no-race workload. A synchronous queue bypass requires an explicit latency/thread gate to fail, not a printed timing alone.

**Minimal probe:** Run a green control, prove each mutation applied to the actual imported module, then remove validation/no-op writes/skip publish/skip readback/bypass queue/skip ownership one at a time. Judge workload validity before speed.

**Expected:** Every affected benchmark arm becomes invalid or fails its declared gate when required work is missing. A state assertion is useful but not sufficient for all mutants.

**Likely actual / boundary:** Current coverage does not establish all six mutation obligations. This audit does not claim all no-op mutants would survive: existing state checks may kill some.

**Existing coverage and miss:** Historical benchmark numbers exist; they are not current reference-Mac qualification. No independent effect/operation trace tied to each timed sample and insufficient actual-entry-point coverage.

**Regression/repair:** Per-sample effect counts, owner proof, expected text, clipboard generations, method and thread assertions; delay injection conservation; independent cohorts and explicit p50/p95/p99/budget verdict. Repair the benchmark oracle before using new timings as acceptance. Report queue wait, validation, write, publish/post, readback, settle, observation, undo and repaste separately.

**Downstream:** M15 must not import unsupported performance claims. This is a proof gap, not a new measured performance regression.

### M08-AUDIT-21 — The principal tests do not independently model native ownership, coordinates or real UI dispatch

**Classification:** TEST GAP, acceptance-blocking for the affected claim—not a counted production defect. **Confidence:** High from inspected fixtures and native bridge tests. **Status:** NOT_RUN.

**Requirement:** E10 instrumented target; EV-19/EV-20 exact attribution; M08-AC01–05. **Location:** `tests/v2/insertion/fixture_target.py; test_insertion_races.py; test_insertion_attribution.py; test_insertion_pipeline.py; test_native_ax.py; test_selection_capture_m06_seam.py`. [S-FIXTURE] [S-RACES] [S-ATTRIBUTION] [S-PIPELINE] [S-NATIVE] [S-SEAM] [S-H-M06]

**Current coverage:** The core target has one field, Python code-point ranges and favorable pasteboard acknowledgments. Native M06 coverage is real but covers only selected M08 bridge operations. Inline callback substitution does not represent the main run loop.

**Mechanism:** Production code and oracle can agree on an impossible/native-inaccurate world. Ownership and unit defects remain unchallenged; sleep-driven tests fail to force the decisive schedules.

**Minimal probe:** Add an independent A/B/W1/W2/F1/F2 world with typed native ranges and independently logged effects; run actual AppDelegate entry points under real main-thread dispatch and owned helper windows.

**Expected:** Distinguish pure, shim, real-framework, owned-native-helper and manual-app evidence. Tests must demonstrate both valid positive behavior and rejection of adversarial conditions.

**Likely actual / boundary:** Current tests do not prove this broader boundary. This does not invalidate the narrower historical tests or imply their recorded runs were fabricated.

**Existing coverage and miss:** Historical 13 race, 10 attribution and 5 pipeline cases; integrated M06/M11 suites add real protections. The missing dimensions are structural, not fixed by repeating the same simple fixture more often.

**Regression/repair:** Build the corpus adapter around an independent expected-state model; use Events/Barriers; execute real production methods; reject harness errors as mutation kills. Extend, do not replace, historical tests. Add controlled native effect witnesses and thread-aware dispatch; keep arbitrary-app trials manual.

**Downstream:** Protect accepted M06/M11 seams and M02 deletion while proving M08. M12/M14 unrelated harness races remain separately owned.

## Design Concerns

These are decisions to settle explicitly, not extra confirmed bugs:

**Pending clipboard consumption and the next operation.** A generation retained for a late first consumer is not safe merely because transactions are normally serialized; the next publication can still change what that consumer receives. Specify unresolved-paste admission, cancellation and copy-offer behavior without promising control over an unobservable third-party consumer.

**Read versus write capability.** S12 already forbids denied-app content acquisition. Minimal identity/classification metadata, a permitted ordinary insertion, an explicit selection request, passive observation and training retention must be separately authorized. Record any policy refinement before grading cases.

**Strict proof availability.** Decide which method-specific proof can replace an unavailable native fact, and document it. Do not silently weaken the current strict contract to make tests green. Plain caret behavior remains intentionally different.

**Operation identity and cancellation linearization.** Use a final-effect operation identity compatible with M03 attempts and explicit new user repastes. Do not indiscriminately deduplicate all writes by job id or wire a previously rejected store fence without new evidence.

**Observation span growth and ambiguity.** If a changed-length edit cannot be bounded without reading unrelated content, stop/abstain. Do not treat the remaining whole field as owned merely because exact attribution was difficult.

**Recovery lifetime.** Define when undo/repaste text expires and which deletion/exclusion controls revoke it. A default 30-second observation window is not a retention policy for a separate indefinitely cached result.

**Terminal control characters and native residuals.** Qualify CR/CRLF/Unicode separator/control-character handling with a non-executing helper and then the manual terminal trial. No terminal is certified by assumption.

**Metadata after deletion.** A content-free terminal record about an effect that happened before deletion may be useful, but it must not resurrect a job, restore payload/read authority or become training eligibility. Keep this separate from the already enforced artifact barrier. [S-C-INSERT] [S-C-JOB] [S-C-TRAIN] [S-H-M02] [S-STORE]

## Areas Verified Strong

“Verified” here means the named implementation/contract was inspected and its narrower behavior is supported by source; it does not mean newly executed.

| Area | Strength and preservation control |
|---|---|
| Shared M06 identity | Missing and contradictory identity are refused; no reintroduction of `None == None` authority. |
| Ordinary insertion entry | `_finishWithText_` delegates the external insert to the queue rather than performing a settle sleep inline. |
| Queue ordering | Normal distinct transactions are serialized; retain publish/restore order tests. |
| Clipboard ownership | Restore compares generation, not content; a visible newer user generation causes skip. |
| Historical full identical-text guard | Clipboard pre-existing full equality remains ambiguous and does not trigger early restore. |
| Terminal no-context guard | Live bundle classification protects the context-absent multiline case. |
| Lifecycle signal | Wake re-arms; new-dictation timestamps are compared against observer start. |
| No execution keystrokes | No synthetic Return or Backspace in the inspected insertion package. |
| M11 integration | Normalized deny/invalid-list refusal, host-unit selection capture, strict accept and candidate attribution are present. |
| M02 deletion | Deleted-job content artifact writes are fenced; do not weaken this while adding M08 revocation. |
| Evidence semantics | Result states are separate from correctness; immutable roles/reference types and explicit preference rules are preserved. |
| Internal notes | Scratchpad uses its own destination/revision path; external insertion repair must not reroute it. |

These controls are embedded in the corpus so remediation cannot achieve a misleading “safe” result by disabling every successful path. [S-VALIDATION] [S-SERVICE] [S-CLIPBOARD] [S-SEAM] [S-STORE] [S-C-PREF] [S-C-NOTE]

## Adversarial Corpus Summary

The separately delivered `LocalFlow_M08_Adversarial_Corpus.json` contains **125 cases across all 25 requested categories**, **18 stateful probes**, **9 metamorphic relations**, **20 implementation mutation definitions**, and **6 benchmark-work mutation definitions**: **178 specification items, zero executed**. Every item carries `execution_status: "NOT_RUN"` and `observed_result: null`.

The cases include synthetic target/clipboard/AX state; explicit scheduling barriers; expected invariant and semantic outcome; expected evidence state; forbidden canary surfaces; and linked finding ids. The JSON is a **declarative corpus**, not a prebuilt executable runner. Several expectations intentionally describe method-dependent truthful outcomes rather than pretending a proposed semantic label is an existing production enum. The local adapter must concretize state overrides, bind actual production APIs and record its adjudications without weakening the invariant.

| Family range | Categories |
|---|---|
| F01–F05 | identity; window ownership; field ownership; M11 owner drift; deny/read policy |
| F06–F10 | selections/ranges; Unicode/native units; AX insertion; clipboard ownership; user-copy races |
| F11–F15 | delayed paste; identical text; partial insertion; cancellation; duplicate delivery |
| F16–F20 | terminal multiline; undo; Paste Again; observation; re-anchor |
| F21–F25 | lock/wake; evidence; deletion; retention; benchmark validity |

The corpus includes favorable controls, preservation controls, negative cases, native-helper plans and explicit design probes. Design probes require recorded adjudication before a pass/fail score. Native/manual inability is NOT_RUN with a reason, never counted as a passing safety case. The machine-readable findings register is also supplied to simplify traceability.

## Stateful / Metamorphic / Mutation Plan

The 18 stateful probes cover the requested app/window/selection changes, moved-caret positive control, M11 owner drift, denied reads, user-copy and delayed-paste races, identical/partial effects, cancellation, two queued results, undo after edits, reconciliation, lock/wake, new-dictation stop, deletion during publication and delayed transform return. They observe intermediate state as well as the final result.

The nine metamorphic relations enforce monotonicity where it belongs: contradictions and missing proof cannot increase authority; a user-owned clipboard generation cannot permit restoration; missing readback cannot improve confirmation; deletion cannot increase future read/replay/publication authority. Cancellation’s relation explicitly preserves already-witnessed physical effects, and the moved-caret relation is a positive control rather than a blanket refusal rule.

Mutation grading has four mandatory stages: establish a green unmutated control; prove the mutation applied to the actual imported production module; witness the affected workload; and require an invariant assertion or explicit benchmark-validity rejection. A syntax/import error, timeout without a safety witness, wrong worktree import, un-applied mutation, failing control or unreachable test is **HARNESS_ERROR/INVALID**, not a kill. Mutations targeting recommended new guards run on the repaired tree after those guards exist.

Never tune the frozen source corpus by changing expected outcomes until the implementation passes. Use versioned companion policy/adjudication and result files. Preserve failing-base and passing-final records with code SHA, case/family id, method, effect/read logs and evidence disposition; never turn an exposed regression case into a blind holdout.

## Downstream Impact

| Consumer / foundation | Required compatibility boundary |
|---|---|
| M02 | Preserve v11 deletion barriers, content-free metadata, capture-time consent, immutable references and lease precedence. M08 revocation must not wait recursively on the store writer. |
| M03 | Preserve generation/stale-message rejection, cancellation truth, recovery claims and deleted-cache safeguards. Add final effect protection without broadly redesigning worker protocol. |
| M06 | Reuse shared identity, normalized deny decision, owned-element acquisition, native adapter and plain destination policy. Do not reopen browser R5 as M08. |
| M07 | Insert the final authoritative Clean/applied artifact without changing faithful cleanup, normalization or technical tokens. |
| M09 | Preserve saved-result usability, History/Recovery entry points, async UI dispatch and truthful status. New operation ids distinguish deliberate repaste from duplicate delivery. |
| M10 | Preserve terminal/developer classification and literal text. Qualification is not permission to execute newlines or control sequences. |
| M11 | Preserve capture/accept task identity, candidate joins, strict destination, consent, retry semantics and the fixed accept callback. Do not retune its model gate. |
| M12 | Internal notes remain internal. The separately recorded Scratchpad harness race is not repaired opportunistically. |
| M14 | Only exact, authorized observation regions enter learning; no confirmation/no-edit auto-labels. Existing explicit approval and eligibility gates remain intact. |
| M15 | Remains gated; needs trustworthy M08 effects/evidence/performance plus its independent M11/manual prerequisites. |

The M08 changes may require narrow consumer updates in `app.py` and the M11 capture boundary. A touched file is not permission to refactor every feature in it. [S-C-JOB] [S-C-TRAIN] [S-C-NOTE] [S-C-PREF] [S-H-M02] [S-H-M03] [S-H-M06] [S-H-M11]

## Recommended Repair Order

1. **Establish and freeze the local base.** Synchronize safely with canonical main on Daniel’s Mac; inventory callers; record real environment; isolate the desktop; run historical baseline and failing reproductions. Preserve untracked/other-session M11 drafts.
2. **Define the authority and policy contract.** Separate owner-bound destination, read/replace/observe/recovery capabilities, native ranges, operation identity and cancellation linearization. Freeze policy-dependent corpus adjudications with positive controls.
3. **Repair owner/read/native seams.** Address AUDIT-01–05 and the confirmation predicates in 06 before broadly enabling real native writes. Owner/native fixes must not expose an untested destructive undo path.
4. **Repair physical transaction truth.** Address the partial-prefix restore, exact undo payload/target, cancellation, duplicate operation and post-effect exception paths (07–09, 14–16, 19). Define unresolved-paste queue policy.
5. **Repair observation and lifecycle evidence.** Address 10–13 and 18, respecting capture-time consent and M02’s existing durable barrier. Test actual artifacts and downstream candidate eligibility, not only envelope flags.
6. **Repair responsiveness and proof tools.** Move complete repaste work off UI (17); strengthen independent fixture/native oracles and benchmark work validity (20–21). Run every stateful/metamorphic/mutation obligation with valid controls.
7. **Freeze the first pass and review independently.** A fresh-context read-only reviewer in a separate worktree reviews code/tests/contracts/evidence. Reproduce each allegation on that exact frozen SHA; regressions fail there and pass on the final code. Retest both newly repaired and historical controls.
8. **Close out only M08.** Run available owned-native qualification and honest reference-Mac benchmarks; preserve separate manual checks; update contracts/handoff/results and only M08’s runbook section. Push a branch, never merge main, and stop.

No individual finding is an instruction to blindly patch its hypothesis. The local agent must first disposition it as reproduced, narrowed, refuted, already fixed by later main, test-gap only, design-only, or unresolved native/manual—with concrete evidence. A refuted finding is a successful audit outcome when the reproduction and explanation are sound.

## M08 Readiness Verdict

**C — significant remediation is required at the insertion authority, observation and proof boundaries.** This is not a claim that every ordinary dictation fails, nor a native incident report. It is a decision that the current source does not justify accepting the stronger safety/evidence guarantees without the supplied adversarial qualification.

The next action is the companion **Claude Code LOCAL / Opus 5.5 — M08 Remediation Handoff**. It requires local reproduction, a preserved first-pass SHA, a genuine independent read-only review, real owned-native helper checks, validated benchmarks, an M08-only manual runbook update and a pushed unmerged branch. `LOCAL_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION` is available only when the automatable and available local-native obligations actually pass. Otherwise the local report must say exactly which obligation remains unmet.

**No M08 remediation, test execution, benchmark, native qualification or GitHub mutation was performed by this audit. No downstream milestone was started.**

### Source register

Every source below is pinned to `180278ee8a157e7372ba187cfb0106556114293f`. Scopes identify what was actually used; listing a file is not a claim that unrelated code elsewhere in it was audited.

- **S-SERVICE:** [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/service.py) — Entire file; transaction, AX/clipboard, retry, undo, observer admission and exception paths.
- **S-VALIDATION:** [localflow/v2/insertion/validation.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/validation.py) — Entire file; _validate, validate_target, _surroundings_verdict, _as_range.
- **S-HOSTS:** [localflow/v2/insertion/hosts.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/hosts.py) — Entire file; system AX, pasteboard and keyboard adapters.
- **S-LEASE:** [localflow/v2/insertion/target_lease.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/target_lease.py) — Entire file; TargetLease and identity_matches.
- **S-SELECTION:** [localflow/v2/insertion/selection.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/selection.py) — Entire file; capture_selection and surroundings.
- **S-CLIPBOARD:** [localflow/v2/insertion/clipboard.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/clipboard.py) — Entire file; capture, publish and restore_if_owned.
- **S-OBSERVER:** [localflow/v2/insertion/observation.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/observation.py) — Entire file; begin, tick, re-anchor, close and StopSignals.
- **S-RECORD:** [localflow/v2/insertion/record.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/record.py) — Entire file; insertion/observation writer operations.
- **S-RESULT:** [localflow/v2/insertion/result.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/result.py) — Entire file; states, verification and content-free serialization.
- **S-APP:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/app.py) — Targeted coordinator ranges: startup; M11 capture/accept; deletion listener; _finishWithText_; insertion/observation callbacks; Hub/recovery/lock/wake.
- **S-STORE:** [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/store.py) — Targeted writer, artifact, retention, delete-everywhere, tombstone and deletion-listener ranges; not a new whole-store audit.
- **S-TRAINING:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/training.py) — Consent, insertion outcome and observation-close producers; targeted boundary review.
- **S-LEARNING:** [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/learning.py) — Observation-mining entry point and explicit-teach/approval boundary; not a full M14 audit.
- **S-CONFIG:** [localflow/config.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/config.py) — Context policy, collection and observation configuration.
- **S-RACES:** [tests/v2/insertion/test_insertion_races.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/test_insertion_races.py) — Entire file; historical race and clipboard controls.
- **S-ATTRIBUTION:** [tests/v2/insertion/test_insertion_attribution.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/test_insertion_attribution.py) — Entire file; observer and undo controls.
- **S-PIPELINE:** [tests/v2/insertion/test_insertion_pipeline.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/test_insertion_pipeline.py) — Entire file; real coordinator with test callback dispatch.
- **S-FIXTURE:** [tests/v2/insertion/fixture_target.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/fixture_target.py) — Entire file; one-field host, Python ranges, delayed paste and clipboard doubles.
- **S-NATIVE:** [tests/v2/context/test_native_ax.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/context/test_native_ax.py) — Entire file; real M06 AXValue/UTF-16 tests and limited M08 bridge coverage.
- **S-SEAM:** [tests/v2/transforms/test_selection_capture_m06_seam.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/transforms/test_selection_capture_m06_seam.py) — Entire file; integrated M06 deny/M11 capture regressions.
- **S-BENCH:** [scripts/v2/benchmark_m08.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/scripts/v2/benchmark_m08.py) — Entire file; timed regions and current work/state oracles.
- **S-SPEC:** [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/LOCALFLOW_V2_SPEC.md) — Relevant S06/S12/S18/S24/S29 sections, including code-point offsets, consent and observation scope.
- **S-EVAL:** [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md) — E10, E11, EV-19/EV-20-related evidence and reliability requirements.
- **S-MILESTONES:** [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04 and complete M08 section.
- **S-C-INSERT:** [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/insertion.md) — Current insertion, strict replacement, observation, compatibility and limitations contract.
- **S-C-TARGET:** [docs/v2/contracts/targets.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/targets.md) — Current snapshot/transaction invariants.
- **S-C-CONTEXT:** [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/context.md) — Modern ownership, identity, typed native boundary and remediation policies.
- **S-C-ARTIFACT:** [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/artifacts.md) — Entire contract; text coordinate and lease/deletion rules.
- **S-C-JOB:** [docs/v2/contracts/jobs.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/jobs.md) — Entire contract; attempts, cancellation and idempotent transitions.
- **S-C-TRAIN:** [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/training_evidence.md) — Consent and M02/M04–M08/M11 producer boundaries; capture-time consent addendum.
- **S-C-PREF:** [docs/v2/contracts/preferences.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/preferences.md) — Entire contract; retry, automatic apply and explicit judgment are distinct.
- **S-C-NORMALIZE:** [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/normalization.md) — Relevant coordinate, immutable policy and applied-output boundary; no grammar re-audit.
- **S-C-CLEAN:** [docs/v2/contracts/cleanup.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/cleanup.md) — Relevant faithful-output, source-coordinate, fallback and evidence boundary.
- **S-C-TRANSFORM:** [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/transforms.md) — Relevant selected-text capture, strict acceptance, task identity and note routing.
- **S-C-NOTE:** [docs/v2/contracts/scratchpad.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/scratchpad.md) — Relevant internal destination, code-point conversion and note-evidence boundary.
- **S-C-STORE:** [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/store.md) — Current additive v11 authority, writer discipline, leases and deletion rules.
- **S-H-M02:** [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M02.md) — Remediation and independent-review addendum; capture-time consent and deliberate attempt-fence adjudication.
- **S-H-M03:** [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M03.md) — Remediation/independent review; deleted-cache and recovery claim boundaries.
- **S-H-M06:** [docs/v2/handoffs/M06.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M06.md) — Remediation, independent review and post-integration R4 closure.
- **S-H-M07:** [docs/v2/handoffs/M07.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M07.md) — Accepted fidelity remediation; downstream preservation boundary.
- **S-H-M08:** [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M08.md) — Historical acceptance and repaired historical findings, not a current rerun.
- **S-H-M11:** [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M11.md) — Semantic replay and integration addendum; production 9a049b3 and remaining local verification.
- **S-A-M08:** [docs/v2/acceptance/M08/results.json](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/acceptance/M08/results.json) — Historical machine-readable acceptance; not newly executed.
- **S-ORCHESTRATION:** [ORCHESTRATION.html](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/ORCHESTRATION.html) — Current integration realignment and M08-next campaign instruction.
- **S-STATUS:** [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/STATUS.json) — Historical implementation state M14 and dependency eligibility; not audit-campaign clearance.
- **S-START:** [docs/v2/START_HERE.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/START_HERE.md) — Current orientation, privacy and human-verification rules.
- **S-INDEX:** [docs/v2/contracts/INDEX.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/INDEX.md) — Current contract ownership and extensions.
- **S-README:** [README.md](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/README.md) — Orientation only; not evidence of the currently installed build.
- **S-RUNBOOK:** [docs/v2/VERIFICATION.html](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/VERIFICATION.html) — M06 ending and M07–M11 section boundary: M08 is currently a placeholder starting at M08-V001; neighboring instructions/status machinery must be preserved.
- **S-ISOLATION:** [tests/v2/context/run_isolated.py](https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/context/run_isolated.py) — Entire runner; real-framework imports, desktop AX/event blocking, not native Accessibility certification.

[S-SERVICE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/service.py
[S-VALIDATION]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/validation.py
[S-HOSTS]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/hosts.py
[S-LEASE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/target_lease.py
[S-SELECTION]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/selection.py
[S-CLIPBOARD]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/clipboard.py
[S-OBSERVER]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/observation.py
[S-RECORD]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/record.py
[S-RESULT]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/insertion/result.py
[S-APP]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/app.py
[S-STORE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/store.py
[S-TRAINING]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/training.py
[S-LEARNING]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/v2/learning.py
[S-CONFIG]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/localflow/config.py
[S-RACES]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/test_insertion_races.py
[S-ATTRIBUTION]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/test_insertion_attribution.py
[S-PIPELINE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/test_insertion_pipeline.py
[S-FIXTURE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/insertion/fixture_target.py
[S-NATIVE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/context/test_native_ax.py
[S-SEAM]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/transforms/test_selection_capture_m06_seam.py
[S-BENCH]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/scripts/v2/benchmark_m08.py
[S-SPEC]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/LOCALFLOW_V2_SPEC.md
[S-EVAL]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md
[S-MILESTONES]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/LOCALFLOW_V2_MILESTONES.md
[S-C-INSERT]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/insertion.md
[S-C-TARGET]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/targets.md
[S-C-CONTEXT]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/context.md
[S-C-ARTIFACT]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/artifacts.md
[S-C-JOB]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/jobs.md
[S-C-TRAIN]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/training_evidence.md
[S-C-PREF]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/preferences.md
[S-C-NORMALIZE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/normalization.md
[S-C-CLEAN]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/cleanup.md
[S-C-TRANSFORM]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/transforms.md
[S-C-NOTE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/scratchpad.md
[S-C-STORE]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/store.md
[S-H-M02]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M02.md
[S-H-M03]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M03.md
[S-H-M06]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M06.md
[S-H-M07]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M07.md
[S-H-M08]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M08.md
[S-H-M11]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/handoffs/M11.md
[S-A-M08]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/acceptance/M08/results.json
[S-ORCHESTRATION]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/ORCHESTRATION.html
[S-STATUS]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/STATUS.json
[S-START]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/START_HERE.md
[S-INDEX]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/contracts/INDEX.md
[S-README]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/README.md
[S-RUNBOOK]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/docs/v2/VERIFICATION.html
[S-ISOLATION]: https://github.com/scalinity/LocalFlow/blob/180278ee8a157e7372ba187cfb0106556114293f/tests/v2/context/run_isolated.py
