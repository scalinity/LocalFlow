# Contract: The Scratchpad and local writing versions

**Spec:** S20, S08 (notes/note_revisions tables), S19 (the Hub's
Scratchpad surface), S29.8 (reliable revision events) · **Owner:** M12 ·
**Suites:** EV-14 (tests/v2/notes/), EV-19/EV-20 (producer halves in
test_note_evidence.py + test_scratchpad_hub.py)

`localflow.v2.notes` (`NoteStore` + `NotesEditorModel` + the span
model), `localflow.v2.note_export`, `localflow.v2.ui.scratchpad`
(`ScratchpadEditor`) and the coordinator's note commands deliver S20's
note workspace: notes/tabs, the constrained rich subset (headings,
paragraphs, lists, code blocks, links, local image attachments),
autosave, explicit snapshots, pinning, local search, version restore,
Markdown/plain export and quick-open. It is not a word processor.

## The revision model (the architecture contract, frozen)

- Note revisions are **immutable and parent-linked**; every change —
  typed autosave, explicit snapshot, dictation, transform, restore,
  attachment — APPENDS. A transform creates a version, never an
  untracked overwrite. `origin` ∈ {`created`, `typed`, `dictated`,
  `transform`, `snippet`, `restore`, `attachment`} says WHO changed the
  note; `trigger` ∈ {`system`, `autosave`, `explicit`} says HOW it was
  persisted (an autosave-debounce snapshot never claims to be an
  explicit one).
- **Restore copies forward** (M12-AC02): restoring version V appends a
  new revision with V's content, `origin=restore`,
  `restore_of=V`; the current revision stays in the chain. The editor
  rebinds to the restored revision (a refresh rebinds whenever the
  persisted revision moves under a clean editor), so the next keystroke
  builds on the restore — never silently reverts it.
- **Unsaved tail risk** (M12-AC01): the editor arms
  `notes.dirty_at_utc` on the FIRST edit of a burst; the next persisted
  revision (or a no-change flush) clears it. After a forced
  interruption, `open_note` returns `unsaved_tail_risk`
  {editing_started_utc, last_saved_utc, last_saved_words} and the Hub
  shows the ⚠ banner — the marker identifies the RISK; unsaved content
  itself is never fabricated.
- **Region provenance (S29.8):** revisions carry word-offset origin
  spans (`dictated`/`transform`) — `[start, end, origin]`, plus the
  producing job id for a dictated span, which rides along through
  every rebase (spans written before that carry three elements). A
  span survives only while edits leave every covered word untouched
  (word-diff rebase); an edit
  touching it drops it and records a content-free `edited_spans` entry
  — attribution stops where it becomes unreliable. Typed additions
  never create attributed spans (M12-AC05).

## Storage (schema v8, additive; the vocabulary pattern)

`notes` (title derived from the first non-empty line, pinned flag,
`current_revision_id`, `dirty_at_utc`) + `note_revisions` (append-only;
content, hash, word count, origin/trigger, `source_job_id` (dictation
attribution), `task_key`/`transform_id`/`transform_revision` (the M11
task identity), `restore_of`, spans, purged flag) +
`note_attachments` + `note_evidence_links` (note↔example references
with closure state). All access through `NoteStore` over
`Store.submit`; migrations additive/idempotent with pre-migration
backups; the torn-write repair set covers the v8 tables. `open_note`
bounds the version list at 200 (`versions_truncated` says so).

Attachments live in managed private storage
(`…/Application Support/LocalFlow/v2-notes/`, 0700/0600) — local
files, never uploaded; an insert failure unlinks the payload (no
orphans). Content references attachments by
`![alt](attachment:<id>)`; deletion purges row + file; export reports a
missing payload honestly, never silently drops the marker.

## Deletion

`delete_note` purges attachment payloads, blanks every revision's
content (origins/counts/hashes stay as the content-free record),
removes the note row and writes a `note` tombstone; the returned
closure payload feeds `EvidenceCollector.on_note_deleted` so deletion
propagates to evidence references (below). In the same op, learning
candidates mined from the note's edits (contracts/learning.md) lose
their payload artifact and, when still open, go stale with their rule
terms and spans cleared.

## Evidence (S29.8/S29.14 — the note family)

- `EvidenceCollector.on_note_revision` (consent-gated, called AFTER the
  writer op returns — never nested): appends a content-free `notes`
  block entry to the affected examples' envelopes — the arrival's
  source job (`dictated`/`transform` revisions) plus every open
  `note_evidence_links` example (typed edits that touched an attributed
  region; restores). Entries carry ids/origins/counts/`asr_example:
  false`/`evidence_status: reliable_target_observation`, bounded at 32;
  note TEXT never enters an envelope or an event. Links whose example
  was deleted elsewhere close (`example_unavailable`).
- **The M12-AC05 boundary:** note revisions never mint training
  examples, never duplicate dictated-word counts (usage analytics read
  jobs, never note text), and typed additions are recorded as typed —
  never as dictated speech. M13/M14 must treat repeated saved versions
  as revisions of ONE logical dictation; the `notes` block and the
  link rows are the join. Changed-intent classification stays M14's
  (S29.8); M12 only records the events.

## The surfaces

- **The Hub view (VIEWS 8→9, the M09 `_build_/_refresh_/_load`
  triple):** notes list (pinned first) + search field (the History
  LIKE-with-escaping discipline over current revisions), tab strip over
  open notes, the `ScratchpadEditor` NSTextView, versions popup +
  Restore, the note-scope transform picker + Transform…, Snapshot,
  Add Image…, Export .md/.txt, Pin, Delete. The editor model
  (`NotesEditorModel`) is pure Python; flushes are serialized
  (concurrent autosave can never interleave two revisions of one buffer
  state — EV-14); debounced autosaves run on a worker thread; explicit
  actions flush synchronously (bounded by the measured flush p95,
  < 1 ms at personal scale). Switching notes/closing tabs flushes the
  outgoing buffer first — the debounce tail is never discarded.
- **Dictation into the note (the internal destination):** a PTT start
  with the editor as the key window's first responder binds the job
  (`note_target` = note id + insertion point captured at hotkey-down —
  the M08 promise discipline: the anchor promised at request time is
  the anchor that receives). `_finishWithText_` delivers into the
  editor — an immediate `dictated` revision with `source_job_id`; the
  job records `insertion_confirmed/scratchpad_note`. **The M08
  external insertion queue is never involved** (a note dictation can
  never overwrite an external target); if the note closed or changed
  mid-dictation, the text routes to the clipboard offer
  (`saved_not_inserted/note_closed_during_dictation`) — never a paste
  into whatever app is now focused.
- **Note-scope transforms:** the picker's definition over the
  selection, or the WHOLE NOTE (range `(0, len)` — accept REPLACES the
  note's content); through the M11 engine (`source_kind="note"`,
  task identity frozen; candidates carry `task_kind=
  transform_note`). Accept revalidates the captured source still sits
  at the range (`note_range_changed` → the copy offer — a changed
  region is never blindly overwritten); the applied revision records
  the task identity. The preview panel's Save-to-Scratchpad (honestly
  disabled in M11) is live: the output becomes a NEW note (origin=
  transform, task identity recorded).
- **History copy/move:** `hubSaveHistoryRow` creates a note from a
  row's retained final text (applied → cleaned → raw fallbacks; V2 jobs
  attribute `source_job_id`, legacy rows are honest `typed`). Move
  additionally applies delete-everywhere to the V2 job; a legacy move
  degrades honestly to copy (legacy history is lossless by contract).
- **Quick-open:** one status-menu action (Hub + Scratchpad view + a
  fresh note) behind the same focus-steal guard as Open Hub — deferred
  during recording/insertion with the intent carried to the flush. The
  key equivalent is the menu's own; no global hotkey grab (the S16
  binding discipline).

## Export (M12-AC03)

`note_export.write_export` renders through the M07 `document_nodes`
renderer (the renderer controls numbering/separators). Markdown keeps
headings/paragraphs/lists/fences/links and copies attachment payloads
beside the file (portable); plain text indents code, keeps list
markers and links, and REPORTS image attachments as unsupported — an
unsupported element never silently drops (its marker stays verbatim).
A failed export cleans up its partial files and retains the source
note untouched (exports never mutate notes).

## Events (content-free; ids ride `detail` — the envelope's fixed
field vocabulary)

`notes.dictation_bound`, `notes.dictation_inserted`,
`notes.receive_failed`, `notes.transform_applied`,
`notes.transform_target_lost`, `notes.note_created`,
`notes.deleted`, `notes.export_done/failed`,
`training.note_revision_recorded`, `training.note_deleted_recorded`,
`training.note_capture_failed`.

## Testability split

Store/model/export/evidence layers are fully automatable headless
(EV-14: migration, revisions/restore, tail risk, attachments,
concurrent autosave, spans, export round trip, Unicode; EV-19/EV-20:
arrival/edited/restored/deleted producer cases, consent gating). The
Hub + coordinator suite drives the REAL coordinator (note-bound
dictations, the button-path transform, restore rebind, quick-open
deferral, copy/move) — the headless harness defers `callAfter` to the
main thread and patches the PTT focus probe at the seam (a headless
session has no key window; the key-window guard is load-bearing in
production). Native visual checks (layout, text scale, the picker,
focus rings) are the pending human trial.

## Limitations (documented, not hidden)

- **Revision growth:** every autosave append stores full content;
  nothing coalesces yet. The versions LIST is bounded (200, flagged),
  but the store grows with long typing sessions. Coalescing or a
  retention pass is M13+/M16 analytics/retention work — the append-only
  contract forbids silent rewrites here.
- Two attributed arrivals inside one debounce window merge under the
  second's origin (sub-second window; both texts persist, one span).
- Mid-word caret insertions place the attributed span at the enclosing
  word boundary (a documented heuristic; spans are evidence hints).
- No global quick-open hotkey (the menu action + its key equivalent
  are the M12 surface; a second global grab needs hotkey-module work).
