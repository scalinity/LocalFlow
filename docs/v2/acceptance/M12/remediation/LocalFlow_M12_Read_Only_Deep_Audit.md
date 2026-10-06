# LocalFlow V2 — M12 Read-Only Deep Audit

**Scratchpad and Local Writing Versions**

**Frozen canonical main:** `114ba5831c2581d28c96d427ac866c2f92c1b24a`

**Audit date:** September 26, 2026 (America/New_York).

**Execution status:** Source inspection only. All proposed probes and qualification runs are NOT_RUN.

## Executive Assessment

**Verdict: C — Significant revision/durability/authority weaknesses.**

The current M12 implementation has a useful architecture and several real historical repairs, but it is not ready to be treated as a reliable internal destination. The highest-consequence source mechanisms are outside-root attachment access, destructive export rollback, discarding a failed outgoing dirty buffer, and assigning dictated provenance to an unrelated typed word. The broader repair is about ownership and acknowledgment: a visible buffer update is not a revision commit; a Store transaction is not a filesystem transaction; a stable selected ID is not necessarily the currently rendered editor; and a deterministic word alignment is not proof of origin.

This is a source audit, not a completed test campaign. The report contains 26 findings: four Critical, fifteen High, six Medium and one Low. Severity describes the consequence of the stated path under its stated conditions. Confidence describes the source mechanism, not a claimed native reproduction. All supplied corpus cases, metamorphic relations and mutation definitions are NOT_RUN. Native AppKit qualification and current reference-Mac timing remain local gates.

Remediation should preserve the existing single-writer store, immutable ordinary revisions, explicit note destination, and M13/M14 boundary. It should not redesign the Hub or replace the persistence architecture wholesale.

## Audit Boundary

This audit covers committed GitHub state at `114ba5831c2581d28c96d427ac866c2f92c1b24a`. Any uncommitted local state is outside the GPT-6 audit boundary.

The connected GitHub repository was read only. No repository source was edited, no branch/commit was created, no production or test code was executed, and no native/manual verification was performed. The generated Markdown/JSON package is the audit deliverable, not a repository modification. The corpus deliberately remains NOT_RUN.

The requested M12 files, foundational documents, current contracts and relevant remediation addenda were inspected through the connector. Source citations below resolve to the frozen SHA; locations are path plus function rather than invented line numbers from connector JSON wrappers. Large files were inspected by relevant ranges and symbol searches. Connector code search returned incomplete/empty results for known symbols, so this report **does not certify an exhaustive repository-wide caller inventory**. The local handoff makes a full `rg` inventory a hard pre-edit gate. Populated schema-repair behavior, all native event paths and fresh performance remain explicit proof gaps, not silent passes.

M01–M11 are not broadly re-audited. M02/M03 persistence/deletion, M08 external insertion, M09/M10 Hub semantics, M11 transform authority, and current M13/M14 note consumers are examined only where M12 crosses their boundaries.

## Canonical Foundation

The remote `main` resolved to **`114ba5831c2581d28c96d427ac866c2f92c1b24a`**, exactly the prompt-authoring baseline. No intervening commit existed at the freeze. The branch response reports parent `f9907c80328e576883226ae6592d79b44f25cf28`; its timestamp is 2026-09-27T00:23:04Z, still September 26 in America/New_York.

The direct comparison from M10 production `ed5e20631529e063564b151555215485ec316a53` to the frozen head was ahead by eight, behind by zero, with that production commit as merge base. The subsequent commits are test/tooling/evidence/documentation closeout, including the current M10 addendum and final accepted head. Thus the native Styles/Snippets Tab repair is inherited, not a proposed M12 change.

The integrated M06/M11 evidence head `1c074ce0ff3ef25da79e13600be38cfa4fcf843a` is also an ancestor: direct comparison was ahead by 72, behind by zero, merge base equal to that head. The current orchestration and remediation records place the accepted M01–M07 foundation behind that integration and the later M08/M09/M10 campaign on top. The M09 closeout is inherited at `9344fa14e2d013b5c9befef88663fcd03d3c6ef1`, with final production `a304d48c3adf0ef7639fe66986d8affe41a2264a`; M08’s final production is `ea83bc198567d001e3d770ae5103ca369701825d`. Earlier individual milestone acceptance is established here through the integrated history and its current receipts, **not by rerunning or re-adjudicating every earlier milestone**. The local startup must verify the exact accepted anchors it resolves from those receipts before editing.

Importantly, “inherited” is not “every human gate passed.” The current M11 integration addendum records successful portable/native mechanics but also a misdirected Prompt Engineer review, output-limit fallbacks and remaining benchmark/human qualification. Those M15 gates remain untouched. STATUS.json describes the original implementation progression; ORCHESTRATION and remediation addenda describe the sequential audit campaign. They are not interchangeable readiness certificates.

Historical M12 anchors (`96d387f`, `d2ef224`, `d291a4b`) are orientation only; all findings concern current frozen source.

Evidence: [ORCHESTRATION.html](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/ORCHESTRATION.html); [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M02.md); [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M03.md); [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M08.md); [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M09.md); [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M10.md); [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M11.md); [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/STATUS.json); [CLAUDE.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/CLAUDE.md). Direct ancestry records: [main commit](https://github.com/scalinity/LocalFlow/commit/114ba5831c2581d28c96d427ac866c2f92c1b24a), [M10 comparison](https://github.com/scalinity/LocalFlow/compare/ed5e20631529e063564b151555215485ec316a53...114ba5831c2581d28c96d427ac866c2f92c1b24a), [integration comparison](https://github.com/scalinity/LocalFlow/compare/1c074ce0ff3ef25da79e13600be38cfa4fcf843a...114ba5831c2581d28c96d427ac866c2f92c1b24a).

## Current M12 Architecture

`ScratchpadEditor` owns one NSTextView and a `NotesEditorModel`. Typed changes update a memory buffer and dirty timestamp; a timer requests background flushes. Attributed dictation/transform/snippet/attachment arrivals update the same buffer and start an immediate background flush. The model serializes entry to persistence but stores content and one pending-attribution payload separately.

`NoteStore` sits on `Store.submit`. Ordinary appends read the transaction-current parent, insert a revision and update the note pointer/title. Attachments have a separate filesystem root and ownership table. The native Hub binds note lists/details and action selectors to this model. PTT captures a note ID plus numeric anchor, bypassing the M08 external insertion queue. Transforms capture source/range and revalidate at acceptance. The exporter projects a note payload through M07 document nodes and writes portable files.

After a revision commits, a best-effort callback records content-free note observations against existing training examples. M14 consumes certain typed edits overlapping dictated spans; M13 counts jobs, not note revisions. The problematic boundaries are snapshot versus buffer generation, arrival versus persistence acknowledgment, note row versus derived artifact graph, and SQL commit versus irreversible filesystem effects.

Evidence: [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/state.py); [localflow/v2/note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/note_export.py); [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/training.py); [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/learning.py); [localflow/v2/analytics.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/analytics.py); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/transforms_store.py).

## Historical M12 Findings Revisited

**H1 — dead Transform button:** current source uses NSRange attributes, has a transform picker, and calls the coordinator with the expected source/range/destination arguments. The historical wiring repair is present. That does not certify native first-responder behavior or picker preservation; AUDIT-21/23 and the native corpus cover those remaining surfaces.

**H2 — whole-note insertion instead of replacement:** the ordinary path now captures `(0, len(source))`, so ordinary whole-note acceptance replaces rather than inserts. It still treats the captured whole note as a range, allowing appended content outside the old end to escape full-source revalidation (AUDIT-13). Empty source is an explicit refusal, not evidence that the button is dead.

**H3 — Restore fails to rebind:** the clean-editor persisted-revision rebind is present. Dirty buffers deliberately win against passive refresh. Failure during an outgoing flush and explicit operations overtaking an in-flight flush remain different defects (AUDIT-03/08).

**H4 — native binding defects escape headless tests:** still applicable. Programmatic text setters, fake first-responder checks and direct selector calls cannot qualify timer installation, keyboard delivery, actual NSRange units or hit testing. All native results remain unrun here.

Evidence: [docs/v2/handoffs/M12.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M12.md); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py).

## Note Revision Assessment

The SQL append path is structurally sound for ordinary serial appends: parent choice and current pointer change occur under one writer operation, and prior revision payloads are not overwritten by an ordinary edit. Explicit deletion is allowed to blank payloads; that is the specified exception to logical immutability, not itself a revision defect.

The missing guarantee is that the revision’s text and provenance were captured from the same immutable editing generation. AUDIT-04/09/17 expose incorrect attribution even when parent linkage is valid. AUDIT-03 concerns discarding the only unsaved tail, not mutation of a previously committed revision.

Restore reads a historical payload and then appends a new revision; parenting the writer-current revision is a coherent copy-forward policy. A pre-read alone is not proof of a bug. The user-facing policy for a concurrent restore versus autosave must be made explicit and then tested in both orders. The 200-header limit is a projection bound, not retention: 201 and large-chain cases must verify the truncation flag and continued old-revision lookup. Literal LIKE escaping and exclusion of deleted notes are worth preserving. Populated torn-write repair is not certified by empty-table recreation tests.

Evidence: [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [tests/v2/notes/test_note_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_store.py); [docs/v2/contracts/scratchpad.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/scratchpad.md); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/store.py).

## Autosave / Async Flush Assessment

There are four distinct problems that should not be collapsed into one “flaky thread” label: native timer admission under the wrong mode; no complete ownership/drain of UI-spawned workers; a synchronous-looking flush that can return already_flushing; and a content/pending/dirty snapshot not governed by one generation.

A normal failed flush can retain attribution when nothing newer arrived, but that guarantee fails once a newer pending payload exists. Starting a daemon worker also does not establish either a persistent dirty marker or a committed attributed revision. The marker is only a risk signal, not a copy of the tail. A retained hidden Hub may continue its timer by design; process termination requires a stronger ordered settlement.

AUDIT-03/07–10/18 should share a small coherent operation/generation/receipt model rather than accumulate unrelated flags. Evidence: [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M03.md).

## Known M12 Race Ownership Assessment

The current M09 addendum already contains the decisive decomposition: C110 holds the note revision commit and the old text remains; holding only Hub publication does not reproduce that persistence gap. M11’s addendum independently records the same test reading before the note write lands.

Therefore the historical `test_note_transform_never_external` failure has **both** an insufficient test synchronization oracle and a real M12 completion-contract weakness. The test must await an explicit note revision receipt, not sleep, drain only Hub queries, or assume a Store read happens after a worker that has not submitted yet. Production must supply a receipt/drain and stop announcing persistence on the in-memory bool. Fixing only the test would hide false confirmation; fixing only production without an independent barrier test would leave the defect easy to reintroduce.

No failure-rate rerun was performed here. Historical rates are not current measurements. Evidence: [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M09.md); [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M11.md); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py).

## Internal Destination / Dictation Authority Assessment

The note ID and insertion anchor are job-owned capture data rather than one global last-note field. The current first-responder helper requires this editor in a key window. The note-ID check prevents simply redirecting an A result into open B; note appends check whether the note exists. Those are substantive defenses.

The captured authority does not fully describe a mutable document: revision, text hash, editor/open generation and an explicit rebase/refusal policy are not all present in the PTT note tuple. An edit to A before result delivery can make its stale integer anchor mean a different location. This is D01, not an excuse to import M08 external semantics automatically. A later job must never overwrite an earlier job’s capture tuple even when the usual recorder serializes normal work.

At result delivery, internal writes intentionally bypass M08; `scratchpad_note` can be a legitimate confirmed method with no external insertions row. But confirmation requires a committed note receipt, and a refused destination must not automatically publish to the clipboard. These are AUDIT-07/19. Recovery may retain source/output artifacts under the existing policy; the report does not claim all rejected text is globally lost.

Evidence: [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/insertion.md); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py).

## UTF-16 / Code-Point Assessment

The valid selection conversion and the raw caret return are inconsistent. For `A😀B`, AppKit’s caret immediately before B is UTF-16 location 3, but the Python insertion index is 2. Using 3 yields `A😀BX`, not `A😀XB`. This affects PTT capture as well as insertion-point consumers such as snippets and attachment markers.

Malformed native endpoints need a declared refusal, not rounding into neighboring content. Combining marks and ZWJ sequences remain multiple code points; this audit does not propose treating a grapheme cluster as one storage index. Native and portable cases independently enumerate UTF-16 boundaries and exact final text. See AUDIT-12/22.

Evidence: [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_SPEC.md).

## Transform / Restore Assessment

Ordinary selection acceptance has a valuable exact numeric-range/source comparison; it does not search for the first matching substring. That preserves selection authority when identical phrases occur more than once. Changes outside a selected range can be intentionally allowed when the range remains exactly bound. Whole-note mode needs a separate full-note identity check, as AUDIT-13 demonstrates.

Current transform-of-result code documents preservation of the original destination while changing model input/task. The corpus requires an end-to-end chained witness instead of certifying the complete chain from a comment. Accepted note transforms share the premature persistence acknowledgment and deletion-derived-artifact risks. Restore must retain copy-forward history, honor dirty editor content and settle any flush generation it claims to include.

Evidence: [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/transforms.md); [localflow/v2/ui/transforms_panel.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/transforms_panel.py); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/transforms_store.py); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py).

## Attachment / Filesystem Transaction Assessment

Normal attachment naming and private permissions are useful, but they do not establish authority for a corrupt persisted path, atomic file/row publication or deletion recovery. The three root causes are distinct: unchecked paths (AUDIT-01), precommit destructive deletion and swallowed purge failures (AUDIT-05), and attachment creation without a live-note/admitted-outcome protocol (AUDIT-06).

The M02 addendum explicitly deferred the note-unlink defect to M12 after repairing the same pattern for artifacts. The narrow repair should reuse durable intent, post-commit cleanup and startup reconciliation, not invent a second generic storage service. Managed reads and purges must both use the same confined authority.

Markers are structured references, not arbitrary paths. Missing/purged markers need explicit missing/unsupported reporting. Payload deletion and marker removal are separate effects today; a local complete caller inventory must identify the actual user-facing removal path and test partial failure without pretending a nonexistent control works. Attachment payload size/hash validation and empty/nonregular payload cases remain proof work, not implied by normal upload tests.

Evidence: [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/note_export.py); [tests/v2/notes/test_note_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_store.py); [tests/v2/notes/test_note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_export.py); [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M02.md); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/store.py).

## Note Deletion Assessment

Ordinary late append does not create a deleted note: the writer checks the note’s existence. The current delete operation also blanks note revision content and handles note evidence links and note-derived learning candidates. Do not replace these defenses or invent a revision resurrection finding where this path already refuses.

Deletion is nevertheless incomplete across other M12-owned producers. A late attachment can be admitted without a live owner; a late evidence callback can reopen a link; note transform artifacts can retain or newly publish the deleted note’s text. Filesystem rollback also remains unsafe. These are separate admissions/graphs and require their own deletion-boundary probes.

Existing user-managed Markdown/data exports and backups are not remotely erasable; that boundary should be disclosed. It is not permission for automatically retained internal candidate artifacts to outlive their source. Approved/rejected learning rule decisions have an explicit retained-decision policy; do not erase them merely because their source note is removed.

Evidence: [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/training.py); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/transforms_store.py); [docs/v2/contracts/learning.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/learning.md); [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_SPEC.md).

## History Copy / Move Assessment

The transfer source must be the same final artifact that current History authorizes. The old raw fallback is no longer compatible with M09’s repaired decision/current-attempt semantics (AUDIT-14). The actual Move selector also contains the deferred helper-name error (AUDIT-20).

The basic copy-then-delete ordering is a strength: a thrown/unknown create call does not intentionally authorize immediate deletion of the original. Case A (copy commits, delete fails) should preserve both and report partial completion. Cases B/C must prove deletion never advances on an unknown or nondurable destination. Check the current delete result’s pending-purge/completeness fields, not only absence of an exception. A retry after unknown creation needs reconciliation to avoid unexplained duplicate notes.

Supported legacy database Move remains Copy; legacy log pairs require their own source-kind admission test rather than blindly coercing all legacy IDs to integers. Copying final rendered text into a note does not turn generated/snippet/transform content into raw acoustic truth.

Evidence: [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/hub.md); [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M09.md); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py).

## Export Assessment

The current exporter preserves the source note and explicitly reports missing image payloads in Markdown or unsupported images in plain text. Those are useful properties. They do not make destination writes safe: direct truncation and rollback deletion can destroy existing user files, and a write/chmod failure can leave an untracked partial file (AUDIT-02).

Payloads are loaded before output publication, so a deletion race can result in an older coherent payload snapshot or an explicit missing attachment. The corpus checks that the report never claims all payloads copied when they were not. Exporting all live attachments, including ones with no current marker, needs an explicit policy and visible report. Unsupported structure should be retained/reported rather than silently discarded; this audit tests M12’s projection only, not a broad M07 parser reaudit.

Measure/export only after resolving dirty-buffer/flush semantics; a read-only projection of an old committed revision is not necessarily the user’s latest visible writing. File creation must be staged, collision-aware and independently checked after injected partial failures.

Evidence: [localflow/v2/note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/note_export.py); [tests/v2/notes/test_note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_export.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py).

## Quick-Open / Hub Assessment

Quick-open’s intended operation is one intent: show Hub, select Scratchpad, create a fresh note and focus its editor while respecting M08’s focus guard. The corpus checks that a deferred invocation preserves all of that intent, that duplicate idle wakeups do not repeat one invocation, and that shutdown refuses new admission. Multiple explicit invocations may legitimately mean multiple notes; do not call that duplication without a policy.

Current query generation fencing is inherited from M09, but Scratchpad list/detail/editor authority still needs its own action binding (AUDIT-11). The editor can display A while selected_id is B during a detail load. Transform capture correctly uses the editor’s note identity; several other actions do not. Picker resets and fixed action-row geometry are functional defects, not aesthetic debt (AUDIT-21/23).

Evidence: [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/state.py); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/hub.md).

## Native Scratchpad Functional Assessment

**No native test was run.** The local owned-window gate must use real clicks, native text input, Cmd+A, arrows/selection, the declared Tab/Shift-Tab convention, picker choice, versions, Snapshot, Restore, Pin, Delete, actual hit testing and resize at supported sizes/scales. Programmatic setString_ is fixture setup, not proof of text entry.

The first-responder matrix must include editor, sidebar, both popups, another Hub field and a separate owned foreground helper app. The native Unicode witness must compare actual NSRange units, converted indices, selected_text and the resulting revision. Timer tests must prove a real firing in the normal run loop; direct autosave_tick invocation cannot qualify timer installation.

Apple documents mode-specific timer delivery and the default-mode constants. The current literal "default" is not a substitute for those constants. Default versus common-mode registration during menu/modal tracking is a policy to test, not a demand to run every timer in every mode. Official references: [Apple Run Loop Management](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/Multithreading/RunLoopManagement/RunLoopManagement.html) and [Apple CFRunLoop source](https://github.com/apple-oss-distributions/CF/blob/main/CFRunLoop.c). These references establish API semantics, not a result from Daniel’s machine.

Evidence: [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M10.md); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py).

## Evidence / Privacy Assessment

The NoteStore callback runs after Store.submit returns, and note envelopes primarily carry IDs, origins, counts and revision metadata rather than note prose. Titles are derived content and filenames/export paths can be private; they must never be treated as content-free labels. The exporter’s local return report may contain a path without thereby authorizing logging that path.

Optional evidence failures do not roll back product notes. However, callback identity and deletion fencing are insufficient (AUDIT-16); content-free is not the same as causally correct. The note-transform artifact graph also contradicts any simplistic claim that note text exists only in note_revisions (AUDIT-15).

Most serious, incorrect spans can label typed words as dictated through dirty-prefix indexing or ambiguous repeated words (AUDIT-04/17). Those are reliable-observation failures, not proof that current export already calls them gold acoustic references. Preserve that distinction. Historical M12 acceptance also carries a private absolute local path; its value is intentionally omitted from this report (AUDIT-26).

Evidence: [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/training.py); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/transforms_store.py); [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/learning.py); [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/training_evidence.md); [docs/v2/acceptance/M12/results.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/acceptance/M12/results.json).

## M13 Analytics Boundary

The actual AnalyticsStore implementation upserts one logical dictation fact per job and recomputes aggregates from usage_facts. Note revisions are not the source of dictation totals. Profile/transform/repaste activity is separate. That count-once boundary is supported by current source, not just a contract.

The problem is outcome correctness: the M12 coordinator can mark the one fact confirmed before the note revision commits (AUDIT-07). Repair must not solve that by inventing an external insertions row or creating another usage fact for each note save. The positive witness creates one real fact, then multiple autosaves/snapshots/restores and asserts exactly one contribution—not merely a zero-fact negative test.

Evidence: [localflow/v2/analytics.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/analytics.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [docs/v2/contracts/analytics.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/analytics.md); [tests/v2/notes/test_note_evidence.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_evidence.py).

## M14 Learning Boundary

The current note consumer considers appropriate typed revisions with changed dictated regions and requires resolvable source identity. Transform/restore/snippet/attachment content is not automatically an ASR reference. The profile reader uses retained eligible raw-transcript artifacts, excludes generated snippet examples and does not read note text as speech statistics. These are meaningful boundaries to preserve.

They do not repair an incorrect M12 origin span. A dirty-prefix or repeated-word ownership error can turn an unrelated typed edit into an apparently target-bound candidate. The local regression must follow that exact observation into the current mining and eligibility code, with ASR eligibility asserted separately from candidate existence. Source deletion must revoke managed note-derived candidate payloads/eligibility without inventing authority to erase an independently approved dictionary decision. Existing exported user-managed copies remain disclosed, not silently recalled.

Evidence: [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/learning.py); [localflow/v2/profile.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/profile.py); [docs/v2/contracts/learning.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/learning.md); [docs/v2/contracts/profile.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/profile.md); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/transforms_store.py).

## Test-Oracle Assessment

The historical acceptance records list 30 checks across the five M12 files (7 store, 4 editor, 4 export, 5 evidence, 10 Hub). Those counts describe historical execution, not a current run by this audit.

The important oracle gaps are: normal attachment rows only; no rollback fault after actual unlink; an export failure before the first write; content/span presence instead of exact ownership; direct model flush/clock driving instead of native timer installation; tests joining only their own threads; immediate store reads before UI-spawned note workers commit; no positive populated usage fact in the count-once negative test; direct coordinator transfer rather than the actual Move selector; and no populated repair witness. Native keyboard/focus/hit-testing remains separate from declared shims.

Every repair regression must fail for the intended semantic reason on the frozen base and pass on the repaired candidate. Require exact fixture populations, actual branch reachability, durable rows/hashes and independent origin/path/action identities. A test that errors before the production branch, a no-op fixture or an arbitrary sleep is not proof.

Evidence: [tests/v2/notes/test_note_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_store.py); [tests/v2/notes/test_note_editor.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_editor.py); [tests/v2/notes/test_note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_export.py); [tests/v2/notes/test_note_evidence.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_evidence.py); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py); [docs/v2/acceptance/M12/results.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/acceptance/M12/results.json); [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M09.md).

## Performance / Benchmark Assessment

No current performance verdict is issued. The September 23 values in historical acceptance are orientation only. AUDIT-25 identifies workload and metric-label problems: the nominal 10k-word fixture actually has 11,250 whitespace words; the “ack” path includes a synchronous flush; version populations and true overlap are not independently certified.

The local gate must measure exact 10,000-word open with a populated version list, 200-live-note search, autosave commit, Snapshot, restore, dirty switch, immediate dictated flush, 200/201-version projection and export with actual attachment copies. Separate UI receipt from queue/commit/end-to-end confirmation. Prove overlap outside the isolated timing run. Every measurement must carry SHA, machine/OS/Python, power/load, warm/cold state, populations, inclusion/exclusion of evidence/attachment work and p50/p95/p99.

Injecting delay into a claimed component must move that metric. A no-op open/save or empty search in a positive cohort must make validity fail even if timing is excellent. Do not optimize by omitting work or weakening the new durability receipt.

Evidence: [scripts/v2/benchmark_m12.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/scripts/v2/benchmark_m12.py); [docs/v2/acceptance/M12/results.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/acceptance/M12/results.json); [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md).

## Critical Findings

### M12-AUDIT-01 — Persisted attachment paths can escape managed filesystem authority

**Severity.** CRITICAL

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** attachments / filesystem authority

**Canonical requirement.** S20 managed local attachments; S29.14 deletion authority; the audit’s v2-notes confinement invariant.

**Code location.** NoteStore.attachment_payload, delete_attachment, delete_note; every use of persisted content_path.

**Current behavior.** The code joins the attachment root with the database path and reads or unlinks it without a root-confinement or no-follow check.

**Failure mechanism.** An absolute path replaces the left-hand root; traversal or a symlinked directory resolves outside it. Sanitizing the original upload filename does not validate a later corrupt database row.

**Minimal reproduction — NOT_RUN.** In one owned temporary parent create managed/ and outside/sentinel. Create a normal attachment, replace its content_path with ../outside/sentinel, then call attachment_payload and each deletion path in separate stores. Repeat with an absolute path and with managed/jump -> outside. Record opened/unlinked paths independently.

**Expected behavior.** Refuse an out-of-root or nonregular payload and leave the outside sentinel byte-identical. An invalid row must not expand readable or deletable authority.

**Likely actual behavior / qualification.** The traversal/absolute row is read or unlinked. A directory-symlink path can affect the outside file. A final-component symlink unlink removes the link itself, not its target; use the directory-symlink witness for outside deletion.

**Existing coverage.** The normal attachment test checks managed placement and permissions, not corrupt-row authority.

**Why the oracle misses it.** Only generated pristine paths are supplied; no outside sentinel is asserted.

**Regression recommendation.** Cover read, attachment delete and note delete independently; absolute/traversal/directory symlink/final symlink/FIFO/directory cases, with positive regular-file controls.

**Narrow repair direction.** Centralize attachment path validation and descriptor-based no-follow regular-file access. Keep deletion confined too; a string-prefix or resolve-then-use check alone is insufficient against replacement races.

**Downstream impact.** M02 purge infrastructure must not inherit an unchecked path. M15 cannot qualify managed deletion until this boundary is proven.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/artifacts.md); [docs/v2/contracts/scratchpad.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/scratchpad.md).

### M12-AUDIT-02 — Export can destroy pre-existing destination files and leave untracked partial writes

**Severity.** CRITICAL

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** export integrity

**Canonical requirement.** M12-AC03 and the requested pre-existing-file/atomic-replacement safety invariant.

**Code location.** write_export: direct open(dest, "wb"), chmod, written.append, and exception cleanup.

**Current behavior.** Export truncates destination files in place and later removes all paths in written on failure, without recording whether those files already existed.

**Failure mechanism.** A later attachment failure deletes an overwritten previous Markdown file and earlier colliding attachments. Failure during write or chmod occurs before written.append, leaving that current destination damaged but untracked. A colliding symlink is followed by open.

**Minimal reproduction — NOT_RUN.** Seed a previous Markdown file and first generated attachment with independent KEEP canaries. Export a note with two real attachments; fail the second attachment write after the first succeeds. In separate probes fail midway through the main write and after writing but before chmod completes. Add a destination symlink whose target is a sentinel inside the owned test parent.

**Expected behavior.** A failed export preserves every pre-existing byte and does not claim success; no partial set is presented as complete and no symlink expands the chosen destination authority.

**Likely actual behavior / qualification.** Prior files are truncated, then some are unlinked; the currently failing file may remain partial. Source note revisions remain unchanged, which does not protect destination files.

**Existing coverage.** The failure test uses a destination that cannot be opened before any output is written.

**Why the oracle misses it.** It tests source-note preservation, not rollback ownership of an already-populated destination.

**Regression recommendation.** Snapshot destination names, bytes and link identities before each probe; compare the complete tree after failure. Require at least two nonempty attachment payloads and assert the fault was reached after a successful copy.

**Narrow repair direction.** Stage the complete export in owned temporary files. Define collision/overwrite policy explicitly. Prefer refusing unapproved collisions; any supported replacement needs backups or an equivalent recoverable publication protocol. Never unlink an unowned pre-existing file during cleanup.

**Downstream impact.** Independent of M02 note storage: this can damage user-managed files even though the source note survives. M15 export acceptance is blocked.

**Pinned evidence.** [localflow/v2/note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/note_export.py); [tests/v2/notes/test_note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_export.py); [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_SPEC.md).

### M12-AUDIT-03 — A failed outgoing flush does not prevent discarding the dirty editor

**Severity.** CRITICAL

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** revision durability / editor binding

**Canonical requirement.** S20 reliable local writing; M12-AC01 unsaved-tail honesty; central invariant that asynchronous saving must not lose work.

**Code location.** ScratchpadEditor._flush_outgoing, bind_note, clear; NotesEditorModel.flush.

**Current behavior.** _flush_outgoing catches save failures and returns normally. bind_note and clear then replace or drop the outgoing model and displayed buffer.

**Failure mechanism.** The only copy of the newest typed tail can be discarded after the persistence failure. A dirty timestamp reports possible loss but contains none of the lost text. already_flushing is also not a completed outgoing save.

**Minimal reproduction — NOT_RUN.** Open A with persisted base text, type a unique unsaved tail, and force append_revision to fail. Switch to B through bind_note. Reopen A and inspect all revisions plus any recoverable buffer. Repeat with A’s existing flush held, switch requested, then the held flush failed.

**Expected behavior.** Keep the outgoing buffer recoverable and visibly unsaved, or refuse the switch until the user resolves it. A completed switch must not silently discard the only newest text.

**Likely actual behavior / qualification.** The new model replaces A; A’s stored content lacks the tail and no buffer-recovery record is created by this path.

**Existing coverage.** Historical switch/restore coverage exercises successful flushing and clean rebinds.

**Why the oracle misses it.** No save failure is combined with a model replacement; testing the dirty marker alone is not testing recovery of the content.

**Regression recommendation.** Use a unique tail canary, fail-first store injection, and enumerate both persisted revisions and retained buffers. A status label alone cannot satisfy the oracle.

**Narrow repair direction.** Return and honor a real outgoing-save outcome. Retain failed/in-flight models under owned lifecycle tracking until committed or explicitly discarded, with a recovery surface rather than a silent catch.

**Downstream impact.** M09/M10 binding semantics and M03 quit ordering must preserve this pending buffer; no visual redesign is needed.

**Pinned evidence.** [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py).

### M12-AUDIT-04 — Attribution offsets use the persisted parent instead of the dirty pre-arrival buffer

**Severity.** CRITICAL

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** provenance / M14 input integrity

**Canonical requirement.** S20 typed/dictated distinction, S29.8 reliable observations and M12-AC05.

**Code location.** NoteStore._append span construction from parent_content[:inserted_at_chars]; ScratchpadEditor.receive.

**Current behavior.** The arrival’s character offset refers to the current editor string, but the new word-span start is calculated against the previously persisted revision.

**Failure mechanism.** Typed edits before an arrival shift word positions without changing the persisted parent. The new span can therefore label unrelated typed words as dictated, even at an ordinary word boundary.

**Minimal reproduction — NOT_RUN.** Persist "a". Without saving, set the typed editor buffer to "typed one a ". Dictate "D" at code-point offset 12. Commit and independently split the final string, then resolve every stored dictated span to its actual words and job ID.

**Expected behavior.** Final text is "typed one a D"; only word D belongs to the arriving job. The typed word one must not receive dictated provenance.

**Likely actual behavior / qualification.** The parent prefix contains one word, so the new one-word span starts at index 1 and labels "one" rather than D at index 3.

**Existing coverage.** Arrival tests establish content and presence of origin spans; the historically deferred mid-word heuristic is a different case.

**Why the oracle misses it.** A nonempty span can pass while pointing to the wrong word. The fixture does not place unsaved typed words before the captured offset.

**Regression recommendation.** Use an independent character-to-word ownership oracle on the actual pre-arrival buffer. Include insertion, replacement, dirty prefixes, whitespace and multiple source jobs; then drive a subsequent typed edit through M14 mining.

**Narrow repair direction.** Commit typed changes and each attributed arrival against an immutable, generation-bound preimage, or carry a validated preimage-aware edit operation. Do not calculate offsets against a different revision.

**Downstream impact.** M14 consumes surviving dictated spans as target-bound provenance. This is not proof of automatic gold-ASR export: review and ASR-eligibility gates remain separate and must stay separate.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/learning.py); [docs/v2/contracts/learning.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/learning.md).

## High Findings

### M12-AUDIT-05 — Attachment and note deletion perform irreversible unlinks before SQL commit

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** filesystem/database transaction

**Canonical requirement.** S29.14 durable deletion; M02’s adopted post-commit purge-intent pattern, explicitly deferred to M12.

**Code location.** NoteStore.delete_attachment and delete_note writer callbacks.

**Current behavior.** Rows are updated/deleted and attachment files are unlinked within the callback that Store commits afterwards. Unlink failures are swallowed.

**Failure mechanism.** A rollback after unlink restores live database state but cannot restore the file. Conversely, a failed unlink can leave private bytes after the database declares them purged, with no note-owned durable retry intent.

**Minimal reproduction — NOT_RUN.** Create a populated note and real attachment. Hold immediately after unlink and fail the transaction commit, then reopen the store and compare live rows with bytes. Separately inject EACCES on unlink, complete the SQL transaction, restart, and test whether cleanup is retried and honestly reported.

**Expected behavior.** Rollback preserves live payloads. Committed deletion either removes the payload or retains a durable pending-purge record and an incomplete status until cleanup succeeds.

**Likely actual behavior / qualification.** The rollback case leaves a live row referencing a missing file; the unlink-failure case leaves residual bytes with no M12 retry ledger.

**Existing coverage.** Normal deletion tests assert immediate success. M02’s analogous failure tests do not exercise note_attachments.

**Why the oracle misses it.** One Store.submit serializes SQL but does not make filesystem side effects rollbackable.

**Regression recommendation.** Fault after the actual side effect and at commit, plus a child-process exit on either side of commit. Reopen independently to verify rows, bytes and pending cleanup.

**Narrow repair direction.** Reuse the narrow M02 durable intent/post-commit reconciliation pattern for note attachments, with validated paths and truthful complete/pending results.

**Downstream impact.** Preserve M02 semantics and M14 candidate invalidation in the same logical deletion boundary; do not introduce a second conflicting purge subsystem.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/store.py); [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M02.md).

### M12-AUDIT-06 — Attachment creation lacks live-note admission and treats unknown commit outcome as rollback

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** attachment lifecycle / timeout

**Canonical requirement.** S20 managed ownership, S29.14 no late resurrection, current Store timeout contract.

**Code location.** NoteStore.add_attachment; note_attachments schema; its exception cleanup.

**Current behavior.** The payload is written before the INSERT. The insertion does not establish that its note is still live, and any submit exception leads to unlinking the file.

**Failure mechanism.** Deleting the note before admission can produce an ownerless live attachment. A timeout after admission does not cancel the INSERT, so exception cleanup may delete the payload before a late successful commit. A crash before row publication can leave an unregistered payload.

**Minimal reproduction — NOT_RUN.** Three independent probes: call add_attachment with a deleted note ID; hold an admitted INSERT until the caller times out and runs cleanup, then allow commit; exit a child after the file write but before INSERT. Reopen and enumerate files and ownership rows.

**Expected behavior.** Reject deleted owners at writer admission. Unknown outcomes reconcile one stable operation/attachment identity. Crash-left files remain discoverably owned and are reconciled without losing a successfully committed payload.

**Likely actual behavior / qualification.** A row can be admitted for a nonexistent note; a late committed row can point to the file removed by timeout cleanup; an unregistered file can survive a pre-INSERT crash.

**Existing coverage.** The normal creation test and insert-error cleanup do not distinguish failed admission from admitted-but-unknown completion.

**Why the oracle misses it.** The schema’s note_id column is not itself a live-note barrier or a foreign-key enforcement policy.

**Regression recommendation.** Require both orders of delete/admission, timeout/commit, and restart reconciliation, with exactly one stable attachment identity after retry.

**Narrow repair direction.** Preallocate/reconcile operation identity, validate the owner inside the writer, stage with durable ownership, and only perform failure cleanup after a known noncommit—not after an unknown outcome.

**Downstream impact.** M02 timeout/purge compatibility and M09 mutation-status semantics; Add Image must not manufacture orphan payloads.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/store.py); [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/store.md).

### M12-AUDIT-07 — Dictation and transform success are published before the note revision commits

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** acknowledgment / terminal-state integrity

**Canonical requirement.** S08 authoritative committed state; S20 reliable destination; central revision-content/provenance invariant.

**Code location.** ScratchpadEditor.receive/flush_async; AppDelegate._finishWithText_ note branch; note-transform acceptance.

**Current behavior.** receive returns True after changing the buffer and starting a daemon worker. The coordinator treats that as successful insertion and emits terminal state/evidence/usage before a revision receipt exists.

**Failure mechanism.** An unscheduled or failing save worker can leave History and analytics saying insertion_confirmed/scratchpad_note even though the note never committed. Dictation recovery cleanup is advanced on the same premature success path.

**Minimal reproduction — NOT_RUN.** Hold the note worker before Store admission. Complete a note-bound dictation through the real coordinator. Read job state, usage and note revisions from independent committed snapshots before releasing the worker. Repeat with commit failure and with accepted note transform.

**Expected behavior.** The UI may acknowledge receipt immediately, but persisted/confirmed status requires a matching committed revision. Failure preserves a recoverable result with an honest state.

**Likely actual behavior / qualification.** The job can become confirmed while the note still has its prior revision. Transform-applied signaling has the same gap. Retained History stage artifacts may preserve text; do not equate this with guaranteed global loss of all copies.

**Existing coverage.** The Hub tests often read Store state immediately after the callback, racing the asynchronous revision worker.

**Why the oracle misses it.** A bool from the editor is used as a persistence oracle; draining only the Store does not prove an as-yet-unsubmitted worker has finished.

**Regression recommendation.** Assert not-confirmed before the held commit; after success assert exact revision content, source job and terminal receipt. After failure assert no affirmative confirmation and an accessible recovery result.

**Narrow repair direction.** Return an owned completion/commit receipt keyed to job, note, operation and revision. Publish confirmed only after it resolves successfully; separate visible buffer acknowledgment from durable completion.

**Downstream impact.** M13 must keep one fact per job but record the truthful outcome. M02/M03 recovery and M11 accept evidence must not be finalized early. No external insertions row should be fabricated.

**Pinned evidence.** [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/analytics.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/analytics.py).

### M12-AUDIT-08 — Flush workers are untracked and a concurrent flush call is not a durability barrier

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** async ownership / shutdown / explicit actions

**Canonical requirement.** S19 explicit Quit persists recoverable work; S20 immediate attributed-arrival durability.

**Code location.** ScratchpadEditor._flush_thread, flush_async, flush_now, close; NotesEditorModel.flush; app shutdown.

**Current behavior.** Every flush_async starts an untracked daemon thread. The unused _flush_thread does not supply a join/drain. When another flush owns persistence, flush returns already_flushing after setting reflush.

**Failure mechanism.** Snapshot, Restore, Export or note switching can proceed without the buffer generation they intend to flush being committed. Store shutdown drains admitted operations, not workers still before admission. Closing the model can suppress its requested reflush.

**Minimal reproduction — NOT_RUN.** Hold worker A before admission; request Snapshot/Export and begin shutdown. Verify whether each action waits for or truthfully reports pending generation A. Separately hold A inside persistence, edit generation B, request a second flush and then close.

**Expected behavior.** Explicit durable actions bind to and await a specified buffer generation, or report pending without claiming completion. Quit owns and settles all admitted note work before Store closes.

**Likely actual behavior / qualification.** already_flushing is returned before A/B completion, and shutdown has no complete inventory of note workers to drain.

**Existing coverage.** Historical concurrency tests join threads they create directly, not all threads the production UI spawns.

**Why the oracle misses it.** The test’s own thread list is not the production lifecycle. A daemon start is not proof of a durable save.

**Regression recommendation.** Provide a production drain/receipt seam; tests assert worker inventory empty and required generation committed before teardown. Cover pre-admission, writer-held and post-commit callback phases.

**Narrow repair direction.** Track note operations with bounded ownership and a closed-admission state. Make a generation-aware flush barrier distinct from request_reflush. Integrate it ahead of persistence shutdown.

**Downstream impact.** M03 ordered quit, M09 query drains and M11 note acceptance must compose. Hiding a retained Hub window need not itself force a save if the running controller intentionally survives.

**Pinned evidence.** [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M03.md).

### M12-AUDIT-09 — The buffer and single pending attribution slot are not captured atomically

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** concurrency / attribution identity

**Canonical requirement.** S20 exact revision provenance; S29.8 one logical arrival’s identity; failed save must not relabel work.

**Code location.** NotesEditorModel.receive, _flush_once, failure restoration of pending, and flush reflush loop.

**Current behavior.** content and pending are independent mutable fields. _flush_once reads content and then removes pending; editing does not take the flush lock. A failed save restores its old pending value unconditionally.

**Failure mechanism.** An arrival between those reads can attach new metadata to old content. Arrival B can replace A before capture, or be overwritten when failed A restores pending. A later successful retry may have the wrong origin/job/task or lose one arrival’s provenance.

**Minimal reproduction — NOT_RUN.** Use barriers (not sleeps) after content capture, before pending capture, and before a failed A restores pending. Inject arrival B at each point with different text, job and origin. Also enqueue dictation A then transform B before either worker captures its payload.

**Expected behavior.** Every committed content generation has the provenance that actually produced it; retries cannot overwrite a newer operation’s metadata. Either preserve distinct arrivals or explicitly abstain, never falsely assign sole ownership.

**Likely actual behavior / qualification.** The single slot can merge both contents under B or restore A over B. The exact interleaving must be executed locally before repair.

**Existing coverage.** The original handoff expressly deferred two arrivals in one window; failed-write retention was tested without a newer arrival.

**Why the oracle misses it.** The historical accepted limitation concerns text survival, not truthful per-arrival attribution. Current M14 consumers make that distinction material.

**Regression recommendation.** Assert each arrival’s immutable operation identity, committed preimage/postimage and source spans through failure/retry. A final concatenated-text assertion is insufficient.

**Narrow repair direction.** Capture buffer generation and queued arrival metadata under one synchronization discipline. Preserve ordered immutable arrival records, with failure recovery scoped to that operation rather than a shared replaceable slot.

**Downstream impact.** M11 transform identity, M13 single-job counts and M14 note-derived observations depend on this. Adjudicate the historical limitation explicitly; this audit recommends repair, not silent grandfathering.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [docs/v2/handoffs/M12.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M12.md).

### M12-AUDIT-10 — Autosave timer is registered under the literal mode "default"

**Severity.** HIGH

**Confidence.** High source confidence; native delivery must be verified on the reference Mac

**Category.** native autosave / run loop

**Canonical requirement.** M12-AC01 autosave and current native qualification requirement.

**Code location.** ScratchpadEditor.init_editor: NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, "default").

**Current behavior.** An unscheduled timer is added to a string-named mode rather than the documented AppKit/Foundation default-mode constant.

**Failure mechanism.** Run-loop modes are named; the literal custom name is not the normal default mode. Direct calls to autosave_tick bypass this registration issue.

**Minimal reproduction — NOT_RUN.** In an owned native AppKit helper, type a unique tail through real event dispatch and run the ordinary event loop beyond the debounce. Observe timer callback, save admission and durable revision without calling autosave_tick directly. Compare with a timer registered using NSDefaultRunLoopMode.

**Expected behavior.** The normal application loop fires the installed autosave timer and persists the typed generation under the declared menu/modal policy.

**Likely actual behavior / qualification.** Source indicates the custom mode is not serviced by the ordinary loop; runtime/native verification is required. This audit did not execute AppKit.

**Existing coverage.** Headless editor tests advance a synthetic clock or invoke tick/flush directly.

**Why the oracle misses it.** Calling a timer handler proves the handler, not that the installed timer ever receives a native firing.

**Regression recommendation.** Record an actual timer firing in the normal mode and test menu/modal behavior separately; repeated editor creation/teardown must not leave live timers.

**Narrow repair direction.** Use the official default/common-mode constant according to an explicit policy, and retain/invalidate the owned timer correctly.

**Downstream impact.** Do not describe typed autosave as qualified until the native installation path is tested. This is functional, not Quiet Editorial styling.

**Pinned evidence.** [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [tests/v2/notes/test_note_editor.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_editor.py).

### M12-AUDIT-11 — Scratchpad actions mix selected state with an older rendered editor binding

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** Hub action authority / attachment ownership

**Canonical requirement.** Current M09/M10 Hub contract: act on the visibly rendered, stably identified item.

**Code location.** HubState.select_scratchpad_note/_load_scratchpad_both; Scratchpad Delete/Pin/Add Image/Export and tab actions.

**Current behavior.** selected_id changes before new detail is ready. List publication and detail publication are separate. Several actions read selected_id while the editor can still display the old note.

**Failure mechanism.** During the load gap an action may operate on B while A’s editor remains visible. Add Image captures one note ID for the attachment but inserts the marker into whichever editor is current when the modal action resumes.

**Minimal reproduction — NOT_RUN.** Render A, select B, and hold B’s detail load while allowing list publication. Invoke each action and record the bound ID independently. For Add Image, hold the owned dialog seam and change binding before returning its synthetic file.

**Expected behavior.** An action uses one validated note/revision/editor binding or is disabled/refused during mismatch. Attachment owner and marker revision always refer to the same authorized note.

**Likely actual behavior / qualification.** Mixed bindings are possible. A selected B row does not by itself prove the user intended A; the defect is inconsistent action authority and display, not a universal claim that every such delete is wrong.

**Existing coverage.** Historical tests generally drain the state loader before acting; M09 fixes covered other rendered-item surfaces.

**Why the oracle misses it.** Stable IDs in the data model alone do not make actions safe when their visible detail and editor carry another ID.

**Regression recommendation.** Hold the list/detail gap, record rendered/editor/selected identities and assert one action ticket. Include an action after a list reorder and tab-close while an old tab strip is still rendered.

**Narrow repair direction.** Use a stable rendered Scratchpad action binding and revoke it while loading/mismatched. Revalidate after modal work before inserting an attachment marker. Preserve dirty outgoing buffers.

**Downstream impact.** M09/M10 action semantics must extend to M12. The transform capture path already uses editor.note_id; do not replace it with a weaker selected_id lookup.

**Pinned evidence.** [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/state.py); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/hub.md).

### M12-AUDIT-12 — The native caret’s UTF-16 location is used as a Python code-point index

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** Unicode / captured insertion authority

**Canonical requirement.** S29.4 explicit native/code-point conversion; PTT-time anchor correctness.

**Code location.** ScratchpadEditor.insertion_point; receive at_chars; PTT note target capture; snippet/attachment insertions.

**Current behavior.** selected_range converts valid NSRange coordinates, but insertion_point returns raw selectedRange.location.

**Failure mechanism.** Astral characters consume two UTF-16 units and one Python code point. The incorrect caret shifts the note insertion, including the job’s frozen anchor.

**Minimal reproduction — NOT_RUN.** Use note "A😀B" and an owned native caret at UTF-16 location 3, visually before B. Insert "X" through the real note-bound delivery. Repeat with BMP, multiple emoji, combining marks, ZWJ sequences and a nonzero selection.

**Expected behavior.** The captured code-point anchor is 2 and result "A😀XB". Selection length must follow an explicit insertion/replacement policy.

**Likely actual behavior / qualification.** The raw anchor is 3 and the insertion becomes "A😀BX" in the minimal witness.

**Existing coverage.** Valid selected-range conversion is covered separately; an ASCII caret cannot expose the mismatch.

**Why the oracle misses it.** The fixture does not compare native units with an independently computed code-point offset at the actual insertion seam.

**Regression recommendation.** Use native NSRange plus a separate UTF-16 prefix-length oracle; assert exact final bytes and captured per-job anchor, not just presence of dictated text.

**Narrow repair direction.** Route caret and selection through one validated conversion boundary; do not normalize grapheme clusters into one code point.

**Downstream impact.** M08 external insertion remains separate. M11 note transforms and M12 snippet/attachment insertion must consume the correct unit convention.

**Pinned evidence.** [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py).

### M12-AUDIT-13 — Whole-note transform acceptance accepts an unchanged prefix after the note grows

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** transform authority

**Canonical requirement.** S16 source revalidation; requested whole-note-change refusal; range authority must not expand.

**Code location.** note_destination_check; tfRunNoteTransform whole-note range; note accept path.

**Current behavior.** Range-less captures become (0, len(source)), but acceptance checks the captured slice, not an explicit whole-note scope and full-note identity.

**Failure mechanism.** Appending text outside the old range preserves the captured prefix, so the predicate that is appropriate for a selection also permits a stale whole-note transform.

**Minimal reproduction — NOT_RUN.** Capture whole note "alpha" at (0,5), append " tail", then accept output "ALPHA". Include empty, multiline, Unicode and a duplicate-substring selection control.

**Expected behavior.** A changed whole note refuses according to its full-source policy. An ordinary selection may intentionally allow changes outside the exact numeric range.

**Likely actual behavior / qualification.** The old prefix matches, so the operation can replace that prefix and retain the appended tail instead of refusing the changed whole-note source.

**Existing coverage.** Historical H2 repair covers ordinary whole-note replacement; the changed-source case changes the captured slice, not only its suffix.

**Why the oracle misses it.** A whole-note range is represented as an ordinary numeric selection with no surviving scope discriminator.

**Regression recommendation.** Test appended/deleted prefix/suffix, same-length outside-selection edits and duplicate source strings. Assert whole-note refusal and exact selection-only authorization separately.

**Narrow repair direction.** Carry explicit scope plus immutable source identity. Validate whole-note length/hash (or a deliberately documented revision policy); retain numeric selection checks for selection mode.

**Downstream impact.** M11 chaining must keep the original destination capture. Do not broaden this into an engine rewrite.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/transforms.md).

### M12-AUDIT-14 — History transfer bypasses the repaired final-stage and current-attempt resolver

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** History copy/move source integrity

**Canonical requirement.** Current M09 final text: applied transform output, otherwise cleaned output; unavailable required final stage never silently becomes source ASR.

**Code location.** AppDelegate.hubSaveHistoryRow inline artifact selection.

**Current behavior.** The transfer uses its historical applied/cleaned/raw fallback lookup rather than the current decision-aware History final-text contract.

**Failure mechanism.** The copied note can contain a pre-transform stage, a stale artifact from a prior attempt, or raw ASR when the required final stage is unavailable, disagreeing with the row’s actual final result.

**Minimal reproduction — NOT_RUN.** Create a job with raw, cleaned and applied transform outputs all distinct and current-attempt identity. Transfer it and assert the committed note equals the resolved final artifact. Repeat with a missing final artifact and a retained older attempt.

**Expected behavior.** Copy/move binds to the currently displayed/authorized final artifact. Missing final text produces an honest refusal, not a raw substitute.

**Likely actual behavior / qualification.** The inline fallback can select a different stage from current History. This must be reproduced through current production services, not a fixture duplicating the same fallback.

**Existing coverage.** Historical M12 acceptance explicitly praises the old applied→cleaned→raw behavior; M09 later superseded that policy.

**Why the oracle misses it.** An old expected value can make a newly forbidden fallback look like a passing rescue test.

**Regression recommendation.** Use the real current History resolver, independent artifact IDs/hashes and transform decision; test legacy database rows separately from legacy log pairs.

**Narrow repair direction.** Share the canonical final-stage resolver with an expected artifact/attempt identity. Do not reimplement a second fallback chain.

**Downstream impact.** M09 compatibility and M14 source provenance. Preserve copy-before-delete ordering and the legacy move-to-copy rule.

**Pinned evidence.** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/hub.md); [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M09.md); [docs/v2/handoffs/M12.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M12.md).

### M12-AUDIT-15 — Deleting a note does not revoke its retained transform copies or fence late candidate publication

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** deletion / derived private content

**Canonical requirement.** S20 note deletion follows history’s derived-content rules; S29.14 deletion overrides ordinary immutability.

**Code location.** NoteStore.delete_note; record_candidate; note source_meta and transform preview state.

**Current behavior.** Deletion clears note revisions, attachments, links and note-mined learning payloads, but it does not traverse the note’s transform source/output/prompt/decision artifacts. Candidate publication checks job deletion, not note liveness.

**Failure mechanism.** A pre-existing transform candidate can retain the note’s private text after deletion. A generation finishing after deletion can publish new note-derived copies. Source metadata links the note but does not enforce authority.

**Minimal reproduction — NOT_RUN.** With collection enabled, transform a synthetic note containing a unique canary. Delete the note and inspect all joined candidate artifacts, including output children. Then hold a second generation before record_candidate, delete its note, release publication, and search only the owned test store for its canary.

**Expected behavior.** Managed note-derived content loses eligibility and is purged/revoked under the declared deletion boundary; a late producer cannot recreate it. Explicit user-managed exported copies remain a separately disclosed boundary.

**Likely actual behavior / qualification.** Transform artifacts can remain or be created after note deletion because no note barrier is checked in that writer operation.

**Existing coverage.** M12 deletion tests inspect note tables/links; M11’s job-deletion detachment does not supply a note-deletion barrier.

**Why the oracle misses it.** Checking only note_revisions makes deletion look complete while an internal derived artifact graph retains the same text.

**Regression recommendation.** Assert both deletion orders and all candidate descendants; include preview accept/copy/retry after deletion and exported-candidate eligibility without attempting to erase user-managed exports.

**Narrow repair direction.** Bind note-origin artifacts/candidates to a revocable note identity and check it inside publication. Purge the reachable managed graph with the existing artifact machinery; invalidate stale cached actions.

**Downstream impact.** Narrow M11/M14 deletion seam only. Do not delete an independently retained original dictation merely because a note copied it.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/transforms_store.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/ui/transforms_panel.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/transforms_panel.py); [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_SPEC.md).

### M12-AUDIT-16 — Note evidence callbacks are neither revision-idempotent nor fenced by note deletion

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** evidence consistency

**Canonical requirement.** S29.8 exact observation identity; M12 deletion closes evidence links; evidence remains best-effort without falsely claiming completeness.

**Code location.** on_note_revision; note_evidence_links insertion and envelope append.

**Current behavior.** The callback runs after note commit, which is appropriate, but its writer operation does not validate the note/revision’s continued liveness or deduplicate the logical revision event.

**Failure mechanism.** A delayed callback after deletion can append an arrival and create a new open link when none existed at deletion time. Repeating the same callback appends another observation even when INSERT OR IGNORE deduplicates the link.

**Minimal reproduction — NOT_RUN.** Hold the first arrival callback after the note revision commits but before evidence admission; delete the note, then release it. Separately invoke the exact same event twice and compare observation identities. Inject callback failure after commit to characterize missing-evidence reporting.

**Expected behavior.** No late callback reopens deleted note authority. One logical revision event contributes at most one observation; a failed optional callback never rolls back the note and its completeness limitation is honest.

**Likely actual behavior / qualification.** A new open link/arrival or duplicate envelope observation can be recorded. This does not create an extra ASR example by itself.

**Existing coverage.** Evidence tests cover sequential arrivals/deletion and repeated ordinary saves, not duplicate delivery of one event or delete-before-callback.

**Why the oracle misses it.** Link uniqueness is mistaken for observation uniqueness; the note commit and later callback are separate transactions.

**Regression recommendation.** Independent counts keyed by note/revision/event kind; require a live positive arrival, then delayed, duplicate, unavailable-example and callback-failure variants.

**Narrow repair direction.** Use a stable logical observation key and note/revision liveness check inside the evidence writer. Add a narrow reconciliation/completeness policy if crash-gap recovery is promised.

**Downstream impact.** M02 deletion barrier discipline and M14 mining observations; do not make optional training collection a condition for saving product notes.

**Pinned evidence.** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/training.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [tests/v2/notes/test_note_evidence.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_evidence.py).

### M12-AUDIT-17 — Ambiguous repeated-word alignment can transfer dictated provenance to typed text

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** span rebasing / evidence reliability

**Canonical requirement.** S20 origin distinction; S29.8 attribution stops when no longer reliable.

**Code location.** rebase_spans using SequenceMatcher over whitespace-split words.

**Current behavior.** The matcher chooses one equal-word alignment without representing non-unique ownership.

**Failure mechanism.** Identical text from different origins can survive a deletion with a different actual identity, but a text-only alignment still assigns the earlier dictated span to it.

**Minimal reproduction — NOT_RUN.** Persist "echo echo" with only the first echo attributed to job A and the second explicitly typed. Delete the first word through a known editor operation, leaving the typed echo. Rebase and inspect the survivor’s provenance; repeat with duplicated phrases and a move.

**Expected behavior.** The surviving typed word is not asserted to be dictated. When text-only evidence cannot decide which occurrence survived, attribution abstains.

**Likely actual behavior / qualification.** SequenceMatcher can align the old first occurrence with the new sole occurrence and preserve A’s span over typed text.

**Existing coverage.** The normal span test uses unambiguous tokens and checks a touched word, not competing identical occurrences.

**Why the oracle misses it.** A deterministic alignment is not an independent proof of provenance.

**Regression recommendation.** Keep an independent edit-operation/ownership oracle and compare stored spans with it. Include repeated words, repeated phrases, whitespace/punctuation and source-job ambiguity.

**Narrow repair direction.** Conservatively drop or mark ambiguous spans when alignment is non-unique; preserve operation-aware identity where already available. Do not silently select the first textual match.

**Downstream impact.** M14 can otherwise mine a typed edit as a target-bound dictation correction. ASR review gates still remain separate.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/learning.py); [docs/v2/contracts/learning.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/learning.md).

### M12-AUDIT-18 — An older save can clear the dirty marker for a newer unsaved generation

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** unsaved-tail honesty

**Canonical requirement.** M12-AC01 truthful possible-tail-loss marker; asynchronous saving cannot hide newer unsaved work.

**Code location.** NotesEditorModel.edit/receive/_flush_once; NoteStore._append dirty_at_utc=NULL; mark_dirty/clear_dirty.

**Current behavior.** The database marker is cleared on every append. A second edit while dirty is already true does not re-arm it; attributed receive does not call on_dirty.

**Failure mechanism.** When A is saving and the buffer advances to B, A’s commit can clear the marker even though B is still unsaved. A crash then leaves no marker for that tail. A late marker admission can also mark a clean note dirty.

**Minimal reproduction — NOT_RUN.** Type A and hold its commit. Type B while dirty remains true, release A, and stop before any B save. Inspect the marker and reopen after a controlled child exit. Test attributed receive with a failing immediate save and a no-change flush racing an edit.

**Expected behavior.** The marker corresponds to the latest unsaved generation, not merely the most recent completed SQL append. Deleted-note marker operations report a no-op/refusal honestly.

**Likely actual behavior / qualification.** Stored A can have a null marker while B exists only in memory. A failed attributed arrival may never have armed the marker.

**Existing coverage.** Tests arm/clear a marker sequentially around a single edit burst.

**Why the oracle misses it.** They do not place a newer edit between an older snapshot and its committed marker clear.

**Regression recommendation.** Assert generation-aware dirty state, marker and last committed revision at each barrier; distinguish false-positive and false-negative banners.

**Narrow repair direction.** Associate dirty intent and acknowledgment with buffer generation. Clear only the acknowledged generation, or re-arm a newer tail reliably before exposing a clean state.

**Downstream impact.** M03 quit/crash recovery and M09 status display; fixing receipt ownership should share this generation model rather than add another unsynchronized flag.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py).

### M12-AUDIT-19 — A refused note destination writes to the clipboard without the recovery action being chosen

**Severity.** HIGH

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** internal-destination recovery / clipboard authority

**Canonical requirement.** The requested note-close/switch invariant: no external insertion and no clipboard effect until explicit recovery action; M08 ownership of pending clipboard payloads.

**Code location.** AppDelegate._finishWithText_ closed-note fallback; refused note-transform application copy path.

**Current behavior.** The fallback described as a copy offer directly calls copy_text on the result instead of merely retaining it for an explicit Copy action.

**Failure mechanism.** This changes unrelated clipboard content and bypasses the external insertion service’s pending-payload ownership discipline. No synthetic paste event is needed for a clipboard side effect to be real.

**Minimal reproduction — NOT_RUN.** Bind dictation to A, switch/close A, and finish. Use an isolated private pasteboard with a sentinel and a publication log. Repeat while a synthetic M08 transaction owns an unresolved clipboard payload; do not use the system pasteboard.

**Expected behavior.** Retain saved-not-inserted output with an explicit recovery action; clipboard publication occurs only when authorized and when ownership permits it.

**Likely actual behavior / qualification.** copy_text publishes automatically even though external paste events remain absent.

**Existing coverage.** The closed-note test checks an empty external-paste list, not an unchanged clipboard generation/content.

**Why the oracle misses it.** “No paste” is weaker than “no clipboard side effect.” Historical copy-offer wording hid the distinction.

**Regression recommendation.** Assert zero clipboard publications on refusal, then exactly one guarded publication after the explicit Copy action; include transform refusal and pending M08 ownership.

**Narrow repair direction.** Make the fallback a retained-result offer. Route an explicitly chosen copy through the existing clipboard ownership guard, without routing note writes through the M08 external insertion queue.

**Downstream impact.** M08’s repaired late-consumer protection must not be bypassed by M12 recovery. Preserve History access to the result.

**Pinned evidence.** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/insertion.md); [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M08.md); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py).

## Medium Findings

### M12-AUDIT-20 — History Move-to-Scratchpad calls a nonexistent helper

**Severity.** MEDIUM

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** native action wiring

**Canonical requirement.** S20 working History move; broken controls are in scope despite a future visual redesign.

**Code location.** HubController.historyMoveToScratchpad_ versus _history_to_scratchpad.

**Current behavior.** The Move selector calls _historyToScratchpad, while the implemented shared helper is named _history_to_scratchpad.

**Failure mechanism.** Invoking the actual button/selector raises rather than reaching the coordinator transfer.

**Minimal reproduction — NOT_RUN.** Dispatch the real Move selector on a Hub with a rendered synthetic V2 row. Record entry into the actual transfer helper and durable note creation/source deletion. Keep the legacy copy-only control.

**Expected behavior.** The selector reaches the supported helper with the rendered row identity and move=True.

**Likely actual behavior / qualification.** AttributeError before transfer. M09’s current handoff already records this deferred M12-owned lead.

**Existing coverage.** Coordinator-level transfer tests can pass without invoking this selector.

**Why the oracle misses it.** A direct hubSaveHistoryRow call does not test the button’s method name.

**Regression recommendation.** Add the actual selector path to the owned native and isolated dispatch suites; assert downstream effects, not only no exception.

**Narrow repair direction.** Correct the helper call and pin the production selector-to-command wiring with a regression.

**Downstream impact.** No new deletion authority for legacy data. This is M12, not a reason to reopen M09.

**Pinned evidence.** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py); [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M09.md).

### M12-AUDIT-21 — Fixed Scratchpad action geometry extends beyond the available pane

**Severity.** MEDIUM

**Confidence.** High confidence in the fixed-width risk; exact native clipping/interaction must be verified

**Category.** functional layout / hit testing

**Canonical requirement.** S19 usable controls at supported sizes; M12 functional resize scope.

**Code location.** HubController._build_scratchpad fixed action row and editor/control frames.

**Current behavior.** The action row starts inside the right-hand editor area but uses a fixed aggregate width; it does not wrap or adapt to the available pane.

**Failure mechanism.** At the default/minimum window widths, later actions extend beyond the pane, making some controls partially or wholly inaccessible. The M10 pane key-loop repair does not qualify this row.

**Minimal reproduction — NOT_RUN.** Construct the real Scratchpad in an owned window at default and minimum sizes, then resize. Compare every action’s converted bounds against its clipped visible area and send a hit-tested click to each enabled control.

**Expected behavior.** Every supported action is visible, reachable and attached to its intended selector at all supported sizes and text scales.

**Likely actual behavior / qualification.** Source geometry indicates clipping of later actions. Exact native visibility and hit-testing require reference-Mac verification; no native run occurred here.

**Existing coverage.** Historical tests invoke methods without requiring a click inside a visible button.

**Why the oracle misses it.** A constructed NSButton outside the visible bounds still exists and can be called programmatically.

**Regression recommendation.** Assert visible hit-test ownership and reachable keyboard navigation for Snapshot, Add Image, Export, Pin and Delete before and after resize.

**Narrow repair direction.** Use a narrow responsive/wrapped layout or adjust functional geometry; do not redesign typography, colors or the whole Hub.

**Downstream impact.** M10 native keyboard compatibility must remain green; Quiet Editorial remains a separate track.

**Pinned evidence.** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/hub.md).

### M12-AUDIT-22 — Malformed native ranges are clamped/rounded instead of explicitly refused

**Severity.** MEDIUM

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** Unicode range validation

**Canonical requirement.** S29.4 exact coordinate semantics; invalid ranges must not silently select adjacent content.

**Code location.** utf16_range_to_codepoints and selected_range callers.

**Current behavior.** The converter accepts offsets that are negative, outside the string or inside a surrogate pair and resolves them through clamping/rounding behavior.

**Failure mechanism.** A malformed start/end can silently change the authorized slice. Conversion of valid Unicode ranges does not establish safe behavior for invalid endpoints.

**Minimal reproduction — NOT_RUN.** For "A😀B", request a start or end inside the emoji’s UTF-16 pair. Add negative location/length, a reversed endpoint and very large offsets. Record the accepted/refused result and selected text independently.

**Expected behavior.** Valid code-point boundaries convert exactly. Invalid native ranges have one documented refusal result and do not grant adjacent text replacement authority.

**Likely actual behavior / qualification.** The current helper can normalize malformed coordinates into a different range rather than refuse them; local tests must pin every endpoint behavior.

**Existing coverage.** Current range tests emphasize valid astral selection.

**Why the oracle misses it.** Expected values derived by the same clamping formula cannot detect an authority-changing conversion.

**Regression recommendation.** Use a table of independently enumerated valid UTF-16 boundaries, and test every gap as invalid.

**Narrow repair direction.** Validate types, nonnegative length, bounds and surrogate boundaries before conversion; callers must handle refusal without broadening to whole-note scope.

**Downstream impact.** M11 note transform selection must fail closed. This does not require changing grapheme-cluster semantics.

**Pinned evidence.** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py).

### M12-AUDIT-23 — Scratchpad refresh rebuilds picker contents without retaining the chosen stable identity

**Severity.** MEDIUM

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** Hub picker state

**Canonical requirement.** S19 keyboard/action consistency and current stable-ID Hub discipline.

**Code location.** HubController._refresh_scratchpad transform and versions popup reconstruction.

**Current behavior.** Refresh removes and recreates popup entries while the user’s chosen version/definition is not preserved as a stable selection binding.

**Failure mechanism.** A background list/detail update can reset which transform or version the next action uses, even though the user already selected another entry.

**Minimal reproduction — NOT_RUN.** Render two transform definitions and multiple versions, choose a nondefault stable ID, trigger a Scratchpad refresh without changing that item’s availability, then invoke the action. Separately remove the selected definition/revision to test honest invalidation.

**Expected behavior.** An unchanged chosen ID survives refresh; a missing item disables/refuses the action rather than silently selecting a replacement.

**Likely actual behavior / qualification.** The rebuilt popup can reset selection to its default entry. Native tracking-loop interaction needs local qualification.

**Existing coverage.** Tests select and invoke without an intervening publication.

**Why the oracle misses it.** The popup has valid items, so tests of presence/count do not detect a changed intended selection.

**Regression recommendation.** Assert the selected represented ID before/after refresh and the exact ID passed to the coordinator.

**Narrow repair direction.** Preserve selected stable IDs across refresh, update only when necessary, and explicitly invalidate disappeared choices.

**Downstream impact.** M10 keyboard semantics and M11 definition identity; no aesthetic changes required.

**Pinned evidence.** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/state.py).

### M12-AUDIT-24 — M12 mutation UI reports generic failure for admitted writes with unknown outcomes

**Severity.** MEDIUM

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** mutation acknowledgment / retries

**Canonical requirement.** Current post-M09 Store contract distinguishes pre-admission failure from admitted outcome unknown.

**Code location.** Create/quick-open, Snapshot, Pin, Restore, Add Image and Delete exception/status paths.

**Current behavior.** Generic exception handlers present failed wording without a mutation identity or reconciliation state; some IDs are allocated only inside the service call.

**Failure mechanism.** A TimeoutError can occur after admission and a later commit. A retry can create a duplicate note/attachment or display a state inconsistent with the committed mutation.

**Minimal reproduction — NOT_RUN.** Hold each mutation after admission until the caller times out, release to commit, and invoke the displayed recovery/retry path. Contrast with a read timeout before any mutation and an admission refusal.

**Expected behavior.** Only a proven noncommit is described as failed. Unknown is explicitly pending/unknown and reconciles one stable operation before retrying.

**Likely actual behavior / qualification.** The UI can report failed even when the mutation later commits. Attachment cleanup’s destructive timeout consequence is separately covered by AUDIT-06.

**Existing coverage.** Historical M12 tests mainly use successful synchronous calls or immediate errors.

**Why the oracle misses it.** All exceptions are treated as the same phase; tests do not prove the point at which the write was admitted.

**Regression recommendation.** Use phase-latched read/admission/commit probes, stable IDs and exact row counts after reconciliation. Check all affected action labels.

**Narrow repair direction.** Expose structured mutation outcomes and a stable operation ID; reuse current Store reconciliation semantics. Do not introduce a large async CRUD redesign merely to address wording.

**Downstream impact.** M09’s documented synchronous-CRUD limitation remains a separate policy; History Move must not delete after unknown note creation.

**Pinned evidence.** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/store.md); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/hub.md).

### M12-AUDIT-25 — The benchmark does not certify its advertised workload or acknowledgment metric

**Severity.** MEDIUM

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** benchmark validity / measurement semantics

**Canonical requirement.** EV-14/19/20 honest evidence; work-validity and reference-Mac performance requirements.

**Code location.** scripts/v2/benchmark_m12.py fixture construction, responsiveness loop and result schema.

**Current behavior.** The nominal 10,000-word fixture has 11,250 whitespace words. The acknowledgment cohort includes synchronous model.flush, and the side thread does not independently prove simultaneous save/search. The open cohort does not populate the 200-version boundary.

**Failure mechanism.** Timing success can be reported without certifying exact work, newest durable content or actual overlap. Shared fixture populations and sparse metadata make labels weaker than the numbers suggest.

**Minimal reproduction — NOT_RUN.** Instrument real opened note IDs, whitespace word counts, version headers, matched IDs and committed hashes. Replace open/save/search separately with no-op or zero-population variants; inject one component delay and observe which metric moves.

**Expected behavior.** A benchmark refuses invalid work and labels UI acknowledgment, queue wait and commit latency separately. Fixture size/count/revisions and timing inclusion are exact.

**Likely actual behavior / qualification.** Several no-op/under-populated variants can retain favorable timings; the advertised acknowledgment is not isolated UI receipt time. No fresh timing was run by this audit.

**Existing coverage.** The historical results record latency budgets but not an independent work-validity certificate.

**Why the oracle misses it.** Fast execution is used as a proxy for completed work; real concurrent ordering and durable outputs are not asserted.

**Regression recommendation.** Require positive population and operation reachability before every timing verdict; no-op mutants must be rejected for semantic invalidity, not import errors.

**Narrow repair direction.** Correct fixture labels and timer boundaries; add exact population/hash/overlap oracles, current environment/SHA and p50/p95/p99. Run timing alone on the Mac.

**Downstream impact.** M15 must not inherit September 23 benchmark numbers as current proof. No claim that the current implementation necessarily misses a latency budget.

**Pinned evidence.** [scripts/v2/benchmark_m12.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/scripts/v2/benchmark_m12.py); [docs/v2/acceptance/M12/results.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/acceptance/M12/results.json); [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md).

## Low Findings

### M12-AUDIT-26 — Historical M12 acceptance contains a private absolute working-directory path

**Severity.** LOW

**Confidence.** High confidence in the source mechanism; runtime reproduction NOT_RUN

**Category.** evidence/documentation privacy

**Canonical requirement.** S07 content-free operational evidence and the requested local-path privacy discipline.

**Code location.** docs/v2/acceptance/M12/results.json environment and human-verification command.

**Current behavior.** The historical record includes an absolute home-directory working path despite broad privacy claims. This audit deliberately does not reproduce that value.

**Failure mechanism.** Copying the old environment/command into new evidence perpetuates an unnecessary local identity/path disclosure.

**Minimal reproduction — NOT_RUN.** Scan the historical record and proposed new evidence with a path-class detector, reporting field names and counts only; do not print the matched private values.

**Expected behavior.** New reports use repository-relative paths or an explicit placeholder; any historical redaction is recorded as such rather than silently changing scientific outcomes.

**Likely actual behavior / qualification.** The historical fields match an absolute-home-path pattern. No new runtime privacy leak was demonstrated by this audit.

**Existing coverage.** Prior privacy checks were scoped to earlier milestone diffs and did not certify every old record.

**Why the oracle misses it.** A historical “privacy clean” statement is not a substitute for scanning the exact new artifact set.

**Regression recommendation.** Add a content-free artifact privacy check for home paths, note titles, filenames, exports and exception strings, with synthetic positive/negative detector controls.

**Narrow repair direction.** Avoid carrying the values forward; make a narrowly documented historical redaction only under the project’s evidence-preservation policy. Keep all measured outcomes intact.

**Downstream impact.** M10’s pre-push privacy discipline applies to all generated M12 evidence; do not broaden into unrelated historical cleanup.

**Pinned evidence.** [docs/v2/acceptance/M12/results.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/acceptance/M12/results.json); [docs/v2/handoffs/M12.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M12.md); [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M10.md).

## Test Gaps

### TG01 — Owned AppKit execution

Real text input, responder ownership, picker behavior, timer firing, hit testing and resizing remain NOT_RUN. Native-safe automation must precede manual-only deferral.

### TG02 — Complete caller inventory

Connector search was not exhaustive. Local rg must enumerate direct/indirect note writes, callbacks, delete/export/clipboard seams and every evidence-link producer.

### TG03 — Populated schema repair

Prove behavior with populated notes, revisions, attachments and links; empty-table recreation is not a data-preservation oracle.

### TG04 — Crash and commit-fault filesystem qualification

Run controlled rollback, commit failure and child-process termination in synthetic filesystems, including APFS behavior on the reference Mac.

### TG05 — Evidence callback completeness

Exactly-once event identity, unavailable examples and crash after note commit/before callback need independent result records; no guarantee is inferred from best-effort callbacks.

### TG06 — History move phase boundaries

Cover known copy failure, admitted-unknown copy, copy committed/delete failed, and delete pending-purge results through actual UI/command paths.

### TG07 — Transform chain and deletion graph

Execute original-destination preservation through chained transforms and verify all note-origin candidate descendants and cached actions after deletion.

### TG08 — Work-valid reference-Mac benchmark

Repair population/timer/overlap oracles, reject no-op mutants, then obtain fresh isolated measurements; historical numbers do not qualify the repaired code.

## Design Concerns

### D01 — PTT authority under same-note edits/reopen

Define whether changed content or a new editor/open generation removes authority, or whether a bounded validated rebase is supported. An unexplained stale integer is not a policy. Define nonzero selection behavior separately.

### D02 — Restore linearization and dirty editor

Choose explicit copy-forward-on-writer-current or stale-action refusal. No choice permits silently discarding dirty content or reporting a generation saved before its receipt.

### D03 — Two attributed arrivals

The historical limitation was disclosed, but current provenance consumers make sole-origin coalescing unsafe. This audit recommends repair under AUDIT-09 rather than accepting false attribution as historical debt.

### D04 — Word spans and mid-word edits

Whitespace splitting is a versioned storage convention, not linguistic segmentation. Keep the documented mid-word heuristic labeled/limited; abstain on ambiguous ownership and do not extend the limitation to unrelated-word false provenance.

### D05 — Revision growth

Full-content revisions and a 200-header UI bound are known design choices. Measure growth/performance; do not redesign retention/coalescing during this repair without concrete necessity and explicit authority.

### D06 — Export and deletion boundaries

Specify collision/overwrite behavior and whether markerless live attachments are included. Disclose user-managed exported-copy limitations. Internal automatic training/transform copies remain subject to managed deletion.

## Areas Verified Strong

**1.** Ordinary revisions append under one SQL writer with transaction-current parent and pointer/title updates; explicit deletion remains the documented immutability exception.

**2.** The ordinary late append path refuses a missing note instead of silently recreating it.

**3.** Historical Transform button/picker/arity and ordinary whole-note replacement repairs are present; clean-editor restore rebinding is present.

**4.** The normal selection check binds an exact numeric range and source, rather than searching for an arbitrary first equal substring.

**5.** The native helper checks key-window/first-responder ownership, and valid selected ranges use explicit UTF-16 conversion.

**6.** The model serializes flush ownership and retains a failed arrival’s attribution in the simple no-newer-arrival case; the report identifies where those guarantees stop.

**7.** Note revision evidence is dispatched after the note commit and does not itself create a new ASR example; content-free envelopes are structurally separated from private payloads.

**8.** Normal note deletion blanks revision payloads and closes known note-evidence links; managed attachment permissions are explicitly attempted.

**9.** M13’s actual SQL counts one fact per logical job, not one per note revision. The actual profile reader consumes eligible raw transcripts rather than Scratchpad prose.

**10.** Literal search escaping, bounded version headers with a truncation indicator and queryable older revisions are sound intended semantics to preserve.

**11.** History copy precedes source deletion, and supported legacy Move intentionally degrades to Copy.

**12.** Internal Scratchpad insertion is intentionally separate from M08 AX/clipboard insertion; no external confirmation row should be invented.

These are current source-supported properties or deliberately narrow preservation claims, not a claim of new runtime qualification. Evidence: [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py); [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py); [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/training.py); [localflow/v2/analytics.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/analytics.py); [localflow/v2/profile.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/profile.py); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py).

## Adversarial Corpus Summary

`LocalFlow_M12_Adversarial_Corpus.json` contains **175 cases**: 125 portable cases, 28 stateful probes (including all 22 explicitly requested probes), 12 native qualification cases and 10 performance-validity cases. It also defines **14 metamorphic relations** and **22 semantic mutation checks**. All are **NOT_RUN**. It is a driver/oracle specification, not an executable test runner and not a result record.

Each case carries a synthetic fixture, production schedule, required barriers/faults, independent assertions, reachability rules, source paths and policy dependencies. The local run must preserve the supplied JSON byte-identical and write separate base/first-pass/final results. The structured finding register permits stable cross-reference without replacing the full finding evidence above.

## Stateful / Metamorphic / Mutation Plan

The first 22 stateful cases map in order to the prompt’s required stateful list; six additional probes separate admitted-unknown attachment creation, dirty-generation clearing, split content/pending capture, late evidence-link publication, pre-admission quit and modal Add Image retargeting. Barriers must latch the real production phase and be observed independently. Arbitrary sleeps or timeouts before reaching the barrier are invalid probes.

Metamorphic relations enforce monotonic authority, immutable older revisions, per-job capture freeze, delete monotonicity, filesystem confinement, typed-origin independence, pin independence, retry/event idempotency and component-sensitive timing. Mutation success means the relevant branch was reached and an independent semantic assertion failed. Compilation/import/interface failures do not kill a semantic mutant. Equivalent/surviving mutants require a written explanation and strengthened oracles where necessary.

## Downstream Impact

| Boundary | Preserve | M12 repair must prove |
|---|---|---|
| M02/M03 | One writer, admitted-outcome semantics, durable purge intents, job deletion and ordered quit | Confined attachment effects, correct note drain and note-owned producer fences |
| M08 | Bound external target, serialized clipboard ownership, pending-payload protection | Internal writes stay internal; refusals do not publish an unrequested clipboard result |
| M09/M10 | Rendered stable-ID action authority, decision-aware History, native keyboard behavior | Scratchpad actions/pickers/resize and History transfer obey current contracts |
| M11 | Task identity, captured source/range, chained original destination | Whole-note revalidation, committed accept receipt and note-derived artifact deletion |
| M13 | One logical dictation fact per job | Exact count-once positive cohort and truthful confirmed outcome |
| M14 | Separate candidate observations from acoustic references; raw profile inputs | Correct origin spans, deleted-source revocation and no typed-to-acoustic promotion |
| M15 | No qualification by historical labels | Exact repaired SHA, independent review, valid corpus/native/performance receipts |

## Recommended Repair Order

1. **Freeze and reproduce before changing architecture.** Verify local safety, ancestry, complete callers and exact base symptoms; preserve the supplied corpus unchanged.
2. **Contain destructive filesystem paths first:** AUDIT-01/02/05/06. Add no-follow confinement, recoverable attachment admission/purge and collision-safe staged exports using existing M02 patterns.
3. **Unify note generation, pending-operation ownership and commit acknowledgment:** AUDIT-03/07/08/09/10/18. Retain failed outgoing buffers, fix actual timer registration, expose generation-specific receipts and integrate shutdown before Store closes.
4. **Repair origin/range authority:** AUDIT-04/12/13/17 and D01/D02. Bind exact preimages, convert caret units, distinguish whole-note scope, and abstain on ambiguous provenance.
5. **Complete deletion and optional-evidence fences:** AUDIT-15/16. Cover late producer orders and all note-derived candidate descendants without erasing independently authorized data.
6. **Repair Hub/History/recovery seams:** AUDIT-11/14/19/20/21/23/24, plus malformed-range handling in AUDIT-22. Preserve stable rendered identities and require explicit guarded clipboard recovery.
7. **Qualify, do not merely claim:** repair AUDIT-25 benchmark validity; scan AUDIT-26/new evidence privacy; run corpus, stateful/metamorphic/mutation and compatibility suites, owned native tests and isolated benchmarks; complete independent review and exact-SHA reruns.
8. **Document and finish only M12.** Update contracts/addenda/runbook/orchestration, push and merge only when the current authorized completion policy is satisfied. Do not begin M13, M14, M15 or Quiet Editorial.

## M12 Readiness Verdict

**C. Significant revision/durability/authority weaknesses.** The current source has multiple material failure paths, including four Critical consequences under the stated synthetic schedules/conditions. Existing strengths do not neutralize them, and historical green acceptance cannot qualify changed Hub/store/transform seams.

This is not an “audit inconclusive” verdict: enough current source was inspected to identify actionable mechanisms and deterministic reproductions. It is also not runtime certification. Local reproduction can narrow or refute individual findings; every such disposition must be evidenced rather than assumed. Until the confirmed defects, native qualification, benchmark validity and independent review are complete, M12 must not be promoted to ready merely because the UI displays a saved/inserted status.

The next authorized work is the supplied **Claude Code LOCAL / Opus 5.5 M12 remediation handoff**, not M13/M14/M15.

## Pinned Source Index

All repository links below are pinned to the audited commit. The index is an evidence navigation aid, not a claim that connector search enumerated every caller.

- **N** — [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/notes.py): NoteStore, NotesEditorModel, ranges and span rebasing.
- **U** — [localflow/v2/ui/scratchpad.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/scratchpad.py): Native binding, timer, arrivals and flush workers.
- **X** — [localflow/v2/note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/note_export.py): Markdown/plain export and destination effects.
- **A** — [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/app.py): PTT capture, terminal delivery, note commands and shutdown.
- **H** — [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/hub.py): Scratchpad and History actions, widget refresh.
- **Q** — [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/state.py): Scratchpad selection, list/detail publication and query lifecycle.
- **S** — [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/store.py): Writer admission/commit, deletion infrastructure and schema.
- **E** — [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/training.py): Post-commit note evidence callback.
- **L** — [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/learning.py): M14 note-edit attribution consumer.
- **T** — [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/transforms_store.py): Note transform candidate and artifact persistence.
- **P** — [localflow/v2/ui/transforms_panel.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/ui/transforms_panel.py): Transform preview actions and retained state.
- **Y** — [localflow/v2/analytics.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/analytics.py): Job-based fact upsert and aggregates.
- **V** — [localflow/v2/profile.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/localflow/v2/profile.py): Eligible raw-transcript profile inputs.
- **NS** — [tests/v2/notes/test_note_store.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_store.py): Historical note-store suite.
- **NE** — [tests/v2/notes/test_note_editor.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_editor.py): Historical editor suite.
- **NX** — [tests/v2/notes/test_note_export.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_export.py): Historical export suite.
- **NN** — [tests/v2/notes/test_note_evidence.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_note_evidence.py): Historical evidence suite.
- **NH** — [tests/v2/notes/test_scratchpad_hub.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/tests/v2/notes/test_scratchpad_hub.py): Historical coordinator/Hub suite.
- **B** — [scripts/v2/benchmark_m12.py](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/scripts/v2/benchmark_m12.py): Historical M12 measurement implementation.
- **CS** — [docs/v2/contracts/scratchpad.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/scratchpad.md): M12 invariants and documented limitations.
- **CH** — [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/hub.md): Current M09/M10 rendered-item and action contract.
- **CT** — [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/transforms.md): Task identity and destination authority.
- **CE** — [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/training_evidence.md): Content-free evidence and provenance.
- **CA** — [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/artifacts.md): Managed payload ownership and deletion.
- **CI** — [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/insertion.md): M08 external insertion and clipboard ownership.
- **CY** — [docs/v2/contracts/analytics.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/analytics.md): Count-once boundary.
- **CL** — [docs/v2/contracts/learning.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/learning.md): Note-derived candidates and deletion semantics.
- **CV** — [docs/v2/contracts/profile.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/profile.md): Eligible speech and profile deletion boundary.
- **CSTORE** — [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/store.md): Store authority, timeout and purge semantics.
- **SPEC** — [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_SPEC.md): S08, S16, S20, S29.4/.8/.14/.15.
- **MILES** — [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_MILESTONES.md): M12 acceptance and P01–P04 discipline.
- **EVAL** — [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md): EV-14/19/20 and evaluation boundaries.
- **M12H** — [docs/v2/handoffs/M12.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M12.md): Historical implementation and review claims.
- **M12R** — [docs/v2/acceptance/M12/results.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/acceptance/M12/results.json): Historical results, not current execution proof.
- **M02** — [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M02.md): Remediation addendum: purge intents, commit and lifecycle.
- **M03** — [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M03.md): Remediation addendum: job deletion and ordered shutdown.
- **M08** — [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M08.md): Remediation addendum: authority and pending clipboard.
- **M09** — [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M09.md): Remediation addendum: C110 note-commit race and Move typo.
- **M10** — [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M10.md): Accepted production/native repair and campaign handoff.
- **M11** — [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/handoffs/M11.md): Integrated transform remediation and outstanding gates.
- **GIT** — [CLAUDE.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/CLAUDE.md): Current completed-remediation merge policy.
- **ORCH** — [ORCHESTRATION.html](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/ORCHESTRATION.html): Campaign chronology and integration state.
- **README** — [README.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/README.md): Repository entry point.
- **START** — [docs/v2/START_HERE.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/START_HERE.md): V2 reading route.
- **STATUS** — [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/STATUS.json): Original milestone build status.
- **INDEX** — [docs/v2/contracts/INDEX.md](https://github.com/scalinity/LocalFlow/blob/114ba5831c2581d28c96d427ac866c2f92c1b24a/docs/v2/contracts/INDEX.md): Current contract index.
