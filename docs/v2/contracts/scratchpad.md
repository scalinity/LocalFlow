# Contract: The Scratchpad and local writing versions

**Spec:** S20, S08 (notes/note_revisions tables), S19 (the Hub's
Scratchpad surface), S29.8 (reliable revision events) · **Owner:** M12 ·
**Suites:** EV-14 (tests/v2/notes/), EV-19/EV-20 (producer halves in
test_note_evidence.py + test_scratchpad_hub.py) · **Policy:**
`m12-policy-r1` (docs/v2/acceptance/M12/remediation/adjudications.json)

`localflow.v2.notes` (`NoteStore` + `NotesEditorModel` + `Arrival` + the
span model), `localflow.v2.note_export`, `localflow.v2.ui.scratchpad`
(`ScratchpadEditor`, `ScratchpadPane`) and the coordinator's note
commands deliver S20's note workspace: notes/tabs, the constrained rich
subset (headings, paragraphs, lists, code blocks, links, local image
attachments), autosave, explicit snapshots, pinning, local search,
version restore, Markdown/plain export and quick-open. It is not a word
processor.

## The revision model (the architecture contract, frozen)

- Note revisions are **immutable and parent-linked**; every change —
  typed autosave, explicit snapshot, dictation, transform, restore,
  attachment — APPENDS. A transform creates a version, never an
  untracked overwrite. `origin` ∈ {`created`, `typed`, `dictated`,
  `transform`, `snippet`, `restore`, `attachment`} says WHO changed the
  note; `trigger` ∈ {`system`, `autosave`, `explicit`} says HOW it was
  persisted (an autosave never claims to be an explicit snapshot).
- **Every revision pairs exactly the text and provenance that produced
  it.** The editor buffer advances a `generation` on every change. An
  attributed arrival (dictation, transform, snippet, attachment marker)
  is an immutable `Arrival` — the buffer it landed in (`preimage`), the
  buffer it produced, its provenance and generation — captured under
  the same lock as the buffer change. A save commits, in order, each
  arrival (preceded by the typed text it landed in, as its own `typed`
  revision, when that text was not saved yet) and then the typed tail.
  Two arrivals are two revisions.
- **Receipts.** The `Arrival` is also the arrival's receipt: being
  returned means only that the text is in the buffer. Its outcome
  settles `committed` (naming the revision that holds exactly that
  arrival) when that revision commits, `discarded` when the note was
  deleted, or `failed` when the editor shut down without committing
  it. A failed attempt does not settle it: the arrival stays queued and
  is retried under the same preallocated revision id, so a retry after
  an unknown outcome is one logical effect.
- **Saves are owned and serialized.** The editor owns every save
  thread until it finishes. A save that finds another in progress waits
  for it and then persists what is left — a barrier for the generation
  current at its call, bounded by the caller's timeout; `pending` is
  returned only when that bound expires. Explicit actions (Snapshot,
  Restore, Export) are such barriers; the Hub never reports "saved" for
  a generation that did not commit.
- **A buffer is never silently dropped.** Switching notes starts the
  outgoing buffer's save on an owned thread and waits at most 0.25 s on
  the main thread; when that save fails or is still running, the
  outgoing model is RETAINED — retried by the autosave tick, shown
  again when the note is reopened, listed in the Scratchpad status as
  unsaved, and settled at quit. The tick never queues a second save
  while one runs. `close` refuses new input and keeps admitted work;
  only a note's deletion discards its buffer.
- **The editor never goes back.** The model remembers every revision
  its buffer was based on or committed; a clean editor rebinds only to a
  loaded detail NEWER than that (a reload that read the note before an
  arrival committed is ignored when it publishes).
- **Restore copies forward** (M12-AC02, D02): the buffer is saved first;
  when that completes, restoring version V appends a new revision with
  V's content (`origin=restore`, `restore_of=V`) on top of the
  writer-current revision, and the editor binds the restored text at
  once — before any arrival can reach the pre-restore buffer — so the
  next keystroke or dictation builds on the restore. When the save does
  not complete, the restore is refused and the buffer is kept.
- **Unsaved tail risk** (M12-AC01): the first change after a clean state
  queues the `notes.dirty_at_utc` marker write without blocking the main
  thread; the write applies only while that buffer is still unsaved when
  it runs, and only the commit that saves the NEWEST generation (no
  newer edit, no later arrival — decided inside the writer op) clears
  it. A no-change save clears it under the same rule.
  After a forced interruption, `open_note` returns `unsaved_tail_risk`
  {editing_started_utc, last_saved_utc, last_saved_words} and the Hub
  shows the ⚠ banner — the marker identifies the RISK; unsaved content
  itself is never fabricated. Marker writes on a missing note report a
  no-op.
- **Region provenance (S29.8, D04):** revisions carry origin spans
  (`dictated`/`transform`) over whitespace-split words (`str.split`
  semantics: NBSP and other Unicode whitespace separate words; a CJK run
  or a ZWJ emoji sequence without whitespace is one word) —
  `[start, end, origin, job]`. An arrival's span covers exactly the
  words lying wholly inside its characters of the committed text, placed
  against the arrival's own preimage; a word merging arrival characters
  with typed ones is not attributed, and when the writer-current parent
  is not the preimage the arrival abstains (`meta.attribution`). A span
  survives an edit only when every covered word maps through an
  unmodified block of the word diff AND the covered sequence and every
  covered word keep their number of occurrences and their occurrence
  rank — otherwise it is dropped and reported content-free in
  `edited_spans` (with `reason: ambiguous` when only the occurrence
  identity is in doubt).
  Typed additions never create attributed spans (M12-AC05).

## Storage (schema v11; notes tables from v8)

`notes` (title derived from the first non-empty line, pinned flag,
`current_revision_id`, `dirty_at_utc`) + `note_revisions` (append-only;
content, hash, word count, origin/trigger, `source_job_id` (dictation
attribution), `task_key`/`transform_id`/`transform_revision` (the M11
task identity), `restore_of`, spans, meta, purged flag) +
`note_attachments` + `note_evidence_links` (note↔example references
with closure state). All access through `NoteStore` over
`Store.submit`. A populated `notes`, `note_revisions` or
`note_attachments` table missing at open is refused as corruption
(after the pre-repair backup), like the core tables — never recreated
empty. `open_note` bounds the version list at 200 (`versions_truncated`
says so).

**Managed attachment files.** Payloads live in managed private storage
(`…/Application Support/LocalFlow/v2-notes/`, 0700/0600) — local files,
never uploaded. A persisted `content_path` is data, not authority: it
must be ONE plain file name (`[A-Za-z0-9][A-Za-z0-9._-]{0,127}`) inside
that directory, and it is read or unlinked only through a descriptor on
the directory with no-follow opens; only a regular file is read, a FIFO
never blocks the reader, and a symlink, directory or FIFO in the
directory is never unlinked. A name that fails the rule is refused and
counted (`refused_paths`), never used.

**Attachment creation** admits only a live note, at admission and again
at publication. The payload file is durably owned before it exists (an
`attachment_staging` purge intent), written exclusively (0600,
no-follow), and published with the row in one op that retires the
intent. Cleanup runs only after a KNOWN noncommit; an admitted
publication whose answer never came raises `NoteOutcomeUnknown` with
the preallocated attachment id and leaves the payload for reconciliation.
Staging intents drain only when the store opens (no attachment write of
that process can still be running), so a crash between the write and
the row leaves no ownerless file. Content references attachments by
`![alt](attachment:<id>)`.

**Unknown outcomes (U01).** A store call that timed out after admission
may still commit. Note creation, restore and attachments carry
preallocated ids that a later read reconciles; pin and delete are
idempotent. A mutation whose first step (restore's read, the attachment's
admission) got no answer raises `NoteNotStarted`: nothing it would
write was submitted. `notes.failure_kind(exc)` classifies an ending as
`unknown`, `refused` (never admitted or never started: the store is
busy or closing — "not done") or `failed`
(the op ran and rolled back).

## Deletion

`delete_note` blanks every revision's content (origins/counts/hashes
stay as the content-free record), removes the note row and writes a
`note` tombstone, closes the note's evidence links, and — in the same
op — purges the note-derived managed transform graph (the candidate
source/output artifacts of transforms run over the note and their
prompt/decision children; the candidate rows stay as ids and hashes)
and stales/clears the learning candidates mined from its edits
(contracts/learning.md). Attachment payloads are removed only AFTER the
commit, through durable `notes` purge intents (the M02 mechanism): a
rollback keeps live rows with their payloads, and a payload whose
unlink fails stays pending (retried on reconcile and at every open)
with `pending_purges` reported. `delete_attachment` follows the same
rule. Removing a marker by typing is an ordinary typed revision: the
attachment stays live (and is reported as unreferenced by export) until
the note is deleted (X01). An original dictation the note copied is not
note-derived and is not deleted with the note. The returned closure
payload feeds `EvidenceCollector.on_note_deleted`.

## Evidence (S29.8/S29.14 — the note family)

- `EvidenceCollector.on_note_revision` (consent-gated, called AFTER the
  writer op returns — never nested): appends a content-free `notes`
  block entry to the affected examples' envelopes — the arrival's
  source job (`dictated`/`transform` revisions) plus every open
  `note_evidence_links` example (typed edits that touched an attributed
  region; restores). The evidence writer admits an observation only for
  a live revision of a live note (a late callback cannot reopen a
  deleted note), and records one observation per (revision, kind)
  within the envelope's retained window. Entries carry
  ids/origins/counts/`asr_example: false`/`evidence_status:
  reliable_target_observation`, bounded at 32; note TEXT never enters
  an envelope or an event. Links whose example was deleted elsewhere
  close (`example_unavailable`).
- **Completeness (E01):** evidence is optional. A callback failure never
  rolls back the revision and is reported as
  `training.note_capture_failed`. A crash between a revision's commit
  and its callback is not reconciled: that observation is missing.
- **The M12-AC05 boundary:** note revisions never mint training
  examples, never duplicate dictated-word counts (usage analytics read
  jobs, never note text), and typed additions are recorded as typed —
  never as dictated speech. M13/M14 treat repeated saved versions as
  revisions of ONE logical dictation; the `notes` block and the link
  rows are the join. Changed-intent classification stays M14's.

## The surfaces

- **The Hub view (the M09 `_build_/_refresh_/_load` triple):** notes
  list (pinned first) + search field (the History LIKE-with-escaping
  discipline over current revisions), tab strip over open notes, the
  `ScratchpadEditor` NSTextView, versions popup + Restore, the
  note-scope transform picker + Transform…, Snapshot, Add Image…,
  Export .md/.txt, Pin, Delete. The `ScratchpadPane` lays its controls
  out again for every size it is given; the nine actions sit in two rows
  that fit the minimum window. Every action acts on the note the editor
  SHOWS — only while the selection and the loaded detail agree with it —
  and is refused with the reason during a list/detail gap; Add Image
  revalidates that binding after its dialog, so an attachment's owner
  and its marker are always the same note. The popups keep one item per
  stable id (items are added through the menu, so equal labels never
  merge) and the chosen id survives a refresh; a vanished choice leaves
  nothing selected. A tab chip closes the note it shows. Status lines
  distinguish an unknown, refused or not-started
  outcome from a failure, and list notes whose unsaved buffers are
  being retried. The autosave timer runs in the common run-loop modes
  (T01): a typed tail saves while a menu or modal panel is open.
- **Dictation into the note (the internal destination, D01):** a PTT
  start with the editor as the key window's first responder binds the
  job (`note_target` = note id + a CODE-POINT anchor from the one
  validated UTF-16 conversion + a hash of the text before it; a
  selection anchors at its start and is never replaced). Delivery
  inserts at that anchor while the same note is open and the text before
  the anchor is unchanged (edits after it are fine; switching away and
  back is fine). The job is `insertion_posted` on delivery and
  `insertion_confirmed/scratchpad_note` — with the revision named — only
  when the revision holding the arrival commits; one usage fact per job
  records that outcome (M13-AC02). A refusal (another note, a closed
  editor, an edit before the anchor, an unreadable anchor) or a save
  that never commits is `saved_not_inserted` with the text kept in
  History for an explicit Copy or → Scratchpad. **The M08 external
  insertion queue is never involved, and the clipboard is never
  written on the user's behalf.**
- **Note-scope transforms:** the picker's definition over the
  selection, or the WHOLE NOTE; through the M11 engine
  (`source_kind="note"`, task identity frozen; candidates carry
  `task_kind=transform_note`, with `note_id`/`note_revision_id` on the
  source artifact, published only while the note is live). The capture
  holds an immutable **destination** — `{note_id, revision_id, range,
  text, scope}`, the range in code points of the note's content (a
  native selection that cannot be converted is refused, never widened).
  Accept revalidates it with `notes.note_destination_check`: the open
  note must be the captured note (`note_changed`); a `selection` must
  still hold the captured text at the exact range (`note_range_changed`
  — edits outside it are allowed); a `whole` destination requires the
  whole note to be exactly the captured text (`note_content_changed`).
  A refusal re-offers the preview — only while it still shows that
  result (Copy and Save to Scratchpad remain
  the user's explicit choices; nothing is copied automatically); a
  chained Transform Output keeps the original destination.
  `notes.transform_applied` is published when the revision commits. The
  preview panel's Save-to-Scratchpad makes the output a NEW note
  (origin=transform, task identity recorded).
- **History copy/move (L01):** the transfer resolves the row through the
  same detail History displays and `history_queries.final_text`: the
  applied transform output of the current attempt, else its cleaned
  output; a missing final stage is refused (`no_retained_text`), never
  replaced by an earlier stage, and a row that changed since it was
  shown is refused (`history_changed`). V2 jobs attribute
  `source_job_id` — the note is `dictated` for a cleaned final and
  `transform` for an applied transform's output (model text, never
  acoustic); legacy rows are honest `typed`. Move additionally
  applies delete-everywhere to the V2 job — never after an unknown note
  creation (`create_unknown`) — and a legacy move degrades honestly to
  copy.
- **Clipboard recovery.** An explicitly chosen copy (History Copy, the
  preview's Copy) publishes only while no insertion owns the clipboard
  (an admitted insertion, or an M08 payload still waiting for its late
  consumer — `InsertionService.clipboard_payload_pending`); otherwise it
  reports that the clipboard is busy.
- **Quick-open:** one status-menu action (Hub + Scratchpad view + a
  fresh note) behind the same focus-steal guard as Open Hub — deferred
  during recording/insertion with the intent carried to the flush, and
  refused once quitting began. The key equivalent is the menu's own; no
  global hotkey grab (the S16 binding discipline).
- **Quit:** after the coordinator settles, the Scratchpad closes
  admission, stops its timer and drains every owned save and retained
  buffer while the store still accepts writes; every note delivery is
  then recorded as what it became, and only then does the store close.

## Export (M12-AC03, D06)

`note_export.write_export` renders through the M07 `document_nodes`
renderer (the renderer controls numbering/separators). Markdown keeps
headings/paragraphs/lists/fences/links and copies the payloads of the
attachments the content REFERENCES beside the file (a live attachment
without a marker is counted as `unreferenced_attachments`, not
copied); plain text indents code, keeps list markers and links, and
REPORTS image attachments as unsupported — an unsupported element never
silently drops (its marker stays verbatim). Publication: the chosen
file (the one the save panel approved replacing) is written as a
private temporary file beside it and renamed into place last (a symlink
there is replaced as a link, never written through); attachment copies
are created exclusively under the first free name `stem-NN[-k].ext`,
never overwriting an existing file. Any failure — a write, a chmod, a
payload read — removes exactly the files the export created and
reports `ok: False`: every file that existed before is byte-identical
and the source note is untouched (exports never mutate notes). Exported
copies are user-managed and are not recalled by note deletion.

## Events (content-free; ids ride `detail` — the envelope's fixed
field vocabulary)

`notes.dictation_bound`, `notes.dictation_received`,
`notes.dictation_inserted`, `notes.receive_failed`,
`notes.transform_received`, `notes.transform_applied`,
`notes.transform_target_lost`, `notes.note_created`,
`notes.note_create_unknown`, `notes.deleted`,
`notes.export_done/failed`, `notes.shutdown`,
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
session has no key window). The remediation suites
(`tests/v2/notes/test_m12_remediation.py`, the corpus runner) hold the
real seams with latches; `tests/v2/notes/test_native_m12_scratchpad.py`
drives the Scratchpad with events built for its own window (a passive
tier that never activates the app; an active tier launched as an app).
Installed-product feel, real dictation and enlarged system text scale
are the pending human trial.

## Limitations (documented, not hidden)

- **Revision growth (D05):** every save stores full content; nothing
  coalesces. The versions LIST is bounded (200, flagged), but the store
  grows with long typing sessions. Coalescing or a retention pass is
  later analytics/retention work — the append-only contract forbids
  silent rewrites here.
- Spans are whitespace words, not linguistic tokens or grapheme
  clusters; a mid-word arrival attributes only its whole words, and an
  edit that leaves the text identical (deleting one "echo" of "echo
  echo" and retyping it) is indistinguishable from no edit.
- Note evidence has no crash-gap reconciliation (E01); observation
  de-duplication covers the envelope's retained window (32 entries).
- Snapshot during a running autosave writes no second revision when the
  autosave already committed the clicked generation (S01).
- No global quick-open hotkey (the menu action + its key equivalent
  are the M12 surface; a second global grab needs hotkey-module work).
