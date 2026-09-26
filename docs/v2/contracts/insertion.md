# Contract: Safe insertion, clipboard transactions and recovery undo

**Spec:** S18, S12 (revalidation and read policy), S24 (UI-thread
rule), S29.8 (outcome observation) · **Owner:** M08 · **Suites:** EV-10
(tests/v2/insertion/), EV-19/EV-20 (attribution half)

`localflow.v2.insertion` (`result`, `hosts`, `clipboard`,
`target_lease`, `validation`, `selection`, `record`, `observation`,
`service`) delivers the S18 contract: finished text lands only in the
intended field, never overwrites a new user clipboard copy, and every
insertion carries an honest `InsertionResult`. Authority is explicit
and separate: permission to insert, to replace a selection, to read a
destination's content, to undo, to observe, and to retain evidence are
different grants, each checked where it is used.

## The serialized queue (one operation at a time)

`InsertionService` owns a single daemon thread. The coordinator's
`_finishWithText_` only enqueues (`submit`) — **no AX call, pasteboard
write or settle sleep ever runs on the UI callback**. Recovery's Paste
Again (`paste_again`), History's Paste Again (`paste_text`) and Undo
(`undo_last`) enqueue too and return at once: their reconciliation
reads, destination choice and effects all run on the queue thread.
Completed jobs never interleave clipboard transactions.

**One logical operation, one physical effect.** Every submission
carries an operation id — `job:<job_id>:<attempt>` for a dictation
delivery or an accepted transform (the candidate id is its job id), a
fresh id for every explicit repaste. A second delivery of an admitted
id has no effect and writes no row (`duplicate_operation`); a delivery
for an attempt older than one already admitted for the job is
`saved_not_inserted/stale_attempt`. A deliberate new repaste is a new
id and is never deduplicated by job id. The coordinator settles and
retires a job once (`_insertionDone_`, `_retire_active_job`). The M02
store attempt fence stays unwired (M02's recorded decision); M03's
supervisor still rejects stale worker messages upstream.

## Destination binding and target validation

`validation.validate_target(host, snapshot, job, denied_apps=,
deny_invalid=)` runs immediately before writing, on the queue thread,
bounded by the host's AX messaging timeout (0.2 s).

**The destination is one element.** Validation takes the focused
element OF the live frontmost application's own element
(`focused_element_for(pid)`, the M06 adapter) and accepts it only when
`AXUIElementGetPid` names that application; a foreign owner is
`target_changed` (`owner: fail`), refused unread. The element — with
its owner pid and window — rides the `TargetLease` (in memory only,
never compared, printed or persisted). The method choice, the pre-write
reads, the write, the readbacks, undo and observation act on that
element; nothing re-reads whatever holds the focus.

**The effect boundary.** Immediately before the AX write, before the
clipboard publication and before the paste post, the operation checks
again: a cancelled or deleted job, a destination that is no longer
the frontmost application's focused element, or (where the destination
may be read) a selection other than the one validation authorized — a
recorded replacement range no longer exactly selected, a recorded caret
that is now a selection — stops the effect
(`saved_not_inserted/user_cancelled|job_deleted`,
`target_changed/target_changed_before_effect`,
`target_changed/selection_changed_before_effect`): the AX write and the
paste both replace whatever is selected at that moment. Before the post the
clipboard must also still hold LocalFlow's published generation
(`saved_not_inserted/clipboard_ownership_lost` otherwise — a paste
would insert someone else's copy). The check and the effect are not
atomic: a focus change or copy landing between them is the documented
residual.

**Read capability (S12).** Destination content — range, selected text,
ranged string, character count, value — is read only when the bound
element is an owned, classifiable TEXT field (role AND subrole,
classified before any content read) in an app the normalized M06 deny
decision does not deny (`snapshot.app_denied` over the validated
`context_policy` list; an invalid list denies every app). A denied app
gets the documented metadata minimum only: element ownership, `AXWindow`
identity and settability — no title, role or content read.
`context_enabled=false` alone does not deny. Without read permission
the insert still happens (plain dictation) and is never confirmed or
observed; undo refuses.

The settled matrix:

| Check | Rule | Failure |
|---|---|---|
| identity | the shared M06 rule `snapshot.identity_matches` (`same_destination`): a usable pid on both sides, else a usable bundle on both sides; a pid match with two different known bundles is refused; absent identity never matches | `target_changed` |
| owner | the application's focused element must belong to its pid | `target_changed` |
| window | `window_element`: the M06 window element (in memory) vs the live field's `AXWindow`; `window_title`: the recorded title vs the live focused-window title (resolved on the element's owner application, never on whichever application is frontmost). Either failing is a change — another window of the same app under an equal title, or another tab in the same window; unreadable ⇒ `unavailable`, identity alone governs | `target_changed` |
| field | the bound element's role vs the recorded role; unreadable ⇒ `unavailable` | `target_changed` |
| selection | a recorded NON-EMPTY selection (replacement) must read back with the same range (host units: `selected_range_utf16`, a native `AXValue` decoded, never parsed) and the same text (boxed `AXStringForRange`), and its recorded text must have been kept; missing proof never keeps destructive authority. A recorded caret that is a non-empty live selection now is not a caret move | `target_changed` |

A moved caret is never a target change, and another field of the same
role in the same window at validation time is not either (M06 D5 — the
field then focused is the one bound). A snapshot with no field data
validates on identity. A job with **no recorded destination** (no
snapshot: context off, identity failed, an explicit repaste) is inserted
on faith into the frontmost application's own focused element and is
never confirmed or observed (`destination_not_recorded`).
`target_changed` routes the artifact to saved history with the text on
the clipboard as the one-action paste offer.

**Strict replacement** (`job["strict_replacement"]`, set only by an
accepted selected-text transform — contracts/transforms.md). Replacing
text the user reviewed needs positive proof of every item, each read on
the bound element: the recorded window element equals the live
`AXWindow` AND the recorded title equals the live title (neither
substitutes for the other); the role reads back equal; the recorded
non-empty selection reads back with the same range and text; and the
bounded text recorded on BOTH sides of it (`preceding_text` /
`following_text`, up to 200 host units, captured by
`insertion/selection.py`) was recorded and reads back unchanged. The
verdicts ride the verification JSON (`window_element`, `window_title`,
`surroundings`, `strict`); a refusal is `target_changed` with the copy
offer.

**Selection capture** (`selection.capture_selection`, M11's explicit
transform): the M06 denial is decided before any Accessibility call;
the element is the authorized application's own focused element,
proved by owner pid (a foreign one is `destination_unverified`, unread);
only a classified text field is read (`secure_field`,
`unclassifiable_field` refuse unread); every read of the capture uses
that one element.

## Method matrix (probed at insert time, recorded per transaction)

1. **Cancelled or deleted job** ⇒ no transaction.
2. **Terminal destination + text a terminal could act on + no
   certified bracketed-paste surface** ⇒ copy-only offer
   (`saved_not_inserted/multiline_terminal_unverified`). "Could act on"
   is any line separator `str.splitlines` recognizes (LF, CR, CRLF, VT,
   FF, FS, GS, RS, NEL, LS, PS), any C0 control character except TAB,
   or DEL. The category comes from the snapshot; when the job carries
   none (context off, identity failed, a repaste) it is the category of
   the application validation bound — the identity the effect boundary
   re-checks, so a switch between two frontmost reads cannot carry
   newlines into a shell. No
   synthetic Return exists anywhere in this package.
   `CERTIFIED_BRACKETED_SURFACES` is empty until the E10 terminal trial
   certifies a real surface.
3. **Accessibility not trusted** ⇒ copy-only offer
   (`accessibility_not_trusted`).
4. **The bound element's `AXSelectedText` is settable** ⇒ **AX
   replacement**; the clipboard is never touched.
5. Otherwise ⇒ the **serialized clipboard transaction**.

## Clipboard ownership (S18)

`ClipboardTransaction` on the queue thread: capture the pasteboard
change count (generation 0) plus every supported representation's data
(`public.utf8-plain-text`, `public.rtf`, `public.html`, `public.pdf`,
`public.png`, `public.tiff` — restored as ONE item carrying all
flavors); unsupported types (file promises above all) are reported in
`unsupported_types`, never claimed. The count is read again after the
data: a copy landing mid-capture makes the snapshot mixed, so capture
retries (3 attempts); a board still changing is a conflict
(`saved_not_inserted/clipboard_capture_conflict`, nothing published).
Publish the transcript (owned generation); a refused native write
(`setString_forType_`/`writeObjects_` false) publishes nothing — no
post, the original is restored while the board is still ours
(`failed/clipboard_publish_failed`). Post the paste; wait the settle
bound (0.6 s — readback polls cut it short when the destination may be
read); then restore **only if the pasteboard still holds LocalFlow's
generation** — a user copy always wins (`restore_skipped_reason:
user_copy_won`); a refused restore write is disclosed
(`restore_failed`), never claimed.

**The pending payload.** A paste with no attributable consumption at
the settle bound on a destination that was read before the post keeps
LocalFlow's generation so a late consumer still pastes the right text
(`readback_pending` / `readback_ambiguous`, and a readback whose read
failed at the deadline — a readable destination that could not be read
just then is not an unobservable one; the user's clipboard is the
disclosed sacrifice). That payload is pending:
while it is unresolved no later clipboard publication, copy offer or
undo recovery offer may replace it — a later clipboard-method job is
`saved_not_inserted/clipboard_payload_pending` and stays in History (a
copy offer is withheld: `offer: withheld_payload_pending`); AX-method
jobs are unaffected. It resolves when its destination shows the paste
landed — `match`, `partial` or `normalized` (the user's original is
restored first, so the next capture sees it) — when the board moved on
(a user copy won), when its job was deleted (restored away; its
destination is not read again), or when its lifetime has passed
(`PENDING_PAYLOAD_SEC`, 5 s after the post: the paste never landed, and
the payload is restored away while the board is still ours). Resolution
happens at the next clipboard publication, copy offer or recovery
offer; until then the dictation stays on the clipboard for a manual
paste.

## Result states, readback and units (never the clipboard)

`confirmed · posted_unverified · target_changed · saved_not_inserted
· failed`. **`confirmed`** requires a recorded destination, read
permission, a pre-write read of the owned region (clamped to the
field's end) and of the field length, a post-write readback of the
owned range equal to the text, and an attributable change: the length
moved by exactly the inserted minus the replaced units and the region's
content changed. An identical-text AX replacement (nothing visibly
changes) is confirmed only by the method-specific proof that the AX
selection moved from the replaced range to a caret at the owned end;
otherwise `match_ambiguous`. Reading LocalFlow's own pasteboard proves
nothing about the destination and is never used.

Readbacks: `match`, `match_ambiguous` (the text was already there — a
clipboard paste over identical text never confirms and never triggers
an early restore), `partial` (a changed proper prefix and a grown field
— the target consumed part of it; restoring is safe), `normalized` (the
field grew by exactly the inserted minus the replaced units and the
owned region changed, but not to the text — the target consumed the
paste and rewrote it, e.g. a newline or spaces normalized; restoring is
safe, never confirmed), `mismatch` (a readback that did not change is
pending, never a consumed partial),
`changed` (an AX setter reported failure but the field changed — a
partial effect, `posted_unverified`), `unavailable`. A setter that
reports failure with no change is `failed/ax_write_failed`.

**Transaction truth.** The insertion id is minted before the
transaction and a phase ledger records publication, the post and the
AX write. A fault after any of them keeps the same id, the real method
and the known effect (`posted_unverified`,
`transaction_error_after_effect:<Exc>`); a fault before any effect is
`failed`. Published-but-not-posted text is taken back while the board
is still ours. Evidence persistence failing never changes the physical
result (`insertion.record_failed`).

**Units.** Ranges are host units — UTF-16 code units on macOS —
throughout: `ax_range` decodes native `AXValue` ranges, range writes
are boxed by the host, lengths are UTF-16 lengths. `owned_start` /
`owned_end` are host units (null when not read) and the envelope block
labels them `range_units: utf16_host`; no code-point offset is derived
here.

## Undo (target-bound) and retry reconciliation

`undo_last` exists only for an insertion whose readback attributed the
owned range to it (`match`: an ambiguous, partial, rewritten, pending or
unread readback leaves nothing to undo — equal text there may be the
user's own). It acts on the original destination only while it is still
the application's focused element, only when its content may be read,
and only on a range that still holds exactly the inserted text; it
selects the owned range (a boxed host-unit range) and writes the
previous text back — the replaced selection for an AX **or clipboard**
replacement, empty for a caret insert. `undone` requires the previous
text read back at the range AND the field length moved by exactly the
restored minus the owned units; otherwise `undo_unverified`. Anything else (another field or
window holding equal text, a newer edit, a stale range, an unsupported
surface) degrades to offering the previous text on the clipboard (none
for a caret insert). No synthetic Backspace exists.

`paste_again` (the last result) and `paste_text(text, job_id=None,
on_done=None)` (History) are explicit user intent: on the queue thread
they read the frontmost application's own focused element (only where
reading is permitted) and report `already_present` when it already
contains the text — a substring guard, approximate by design — else run
a fresh transaction (insert-on-faith, never confirmed). They return
`repaste_queued` at once; `on_done(result)` fires when a transaction
ran. The job id keeps the `insertions` row attributed; a jobless
repaste records no row.

**Recovery lifetime.** The in-memory recovery cache (the last result's
text and its undo record) ends after `RECOVERY_CACHE_TTL_SEC` (3600 s),
at the next insertion, at deletion of its job (a job deleted while its
transaction ran never enters it), or at quit; it is never persisted. **`busy`** reports whether an operation is executing on the
queue thread — the coordinator's focus-steal guard (see `hub.md`).

## S29.8 bounded outcome observation (starts here, not in M14)

**Admission.** A window opens only for an attributably confirmed
insertion whose destination may be read, whose job carries capture-time
collection consent (`job["observation_consent"]`: the coordinator sets
it from the job's capture context — the push-to-talk snapshot, or a
retry's original-and-current grant; an accepted transform has it when
its candidate was recorded) and is not deleted; `outcome_observation_sec`
(default 30 s; 0 disables). A later enable never authorizes an earlier
capture; a pause after an authorized capture does not revoke it;
delete-everywhere does, at once.

**Every tick re-proves, before any content read:** not revoked,
identity, that the application's focused element is the bound element,
its owner pid, and a classifiable text field (role and subrole) with
the recorded role. Reads cover the owned range, plus one bounded read
(±400 host units) to prove provenance — the neighbourhood's other
occurrences and the unchanged text on either side (≤16 units, in
memory only, never persisted).

**Re-anchoring** needs a UNIQUE occurrence of the inserted text in that
neighbourhood, with no equal text already there, that still carries the
recorded provenance: the unchanged text recorded on at least one side
sits right beside it (a side recorded at the field's edge must still be
that edge) — an equal text written since, e.g. by a same-length edit
that leaves the field length unchanged, is not ours; ambiguity
(`reanchor_ambiguous`), a failed read (`target_read_failed`) or an
exhausted deadline (`reanchor_deadline`) stops the window without
attributing an edit. **An edit intersecting the owned region** is
recorded with lease-governed before/after artifacts carrying exact
target/job/region attribution (`owned_range_edited`); the after-text
is the region with its new length, kept only when the recorded
unchanged text still bounds it on both sides — otherwise the edit is
recorded without text (`owned_edit_unbounded`). Stop reasons:
`window_elapsed`, `focus_lost`, `field_changed`,
`secure_field_transition`, `new_dictation` (timestamped: only
dictations starting after the window opened), `session_locked` (re-armed
on wake), `target_read_failed`, `reanchor_ambiguous`,
`reanchor_deadline`, `authority_revoked`, `owned_range_edited`,
`owned_edit_unbounded`. Uncertified surfaces never poll — the envelope
records `outcome_observation_unavailable` (`unreliable_target`).

An undo-like revert is inferred only weakly (content gone, field shrank
by exactly the inserted length) and recorded as `undo_candidate`, never
as approval; `no_edit_observed` and confirmed pastes never create
correctness labels or preferences (M08-AC06).

**Close notification** is subscribe-or-deliver (`subscribe_close`): a
window that closed before, during or after the subscription produces
exactly one final notification (the coordinator's final evidence
revision).

## Deletion

`revoke_job(job_id)` runs from the app's store deletion listener,
inside the delete-everywhere op: flags only — no store call, no wait,
no pasteboard write. The job's cached recovery text and undo record go,
queued deliveries for it are refused (`job_deleted`), its running
observers stop before their next read (`authority_revoked`), and an
unresolved pending payload of it is restored away by the queue thread.
A content-free insertion row for an effect that happened remains
allowed (truth, never payload or read authority); an observation row is
never OPENED for a deleted job (checked inside the writer op). The M02
artifact barrier (`insert_text_artifact_row`) refuses any late
content.

## Persistence (tables added at store schema v4; the store is additive)

`insertions` (one row per transaction: state, method, verification
JSON, owned range in host units, clipboard JSON with ownership
generations and disclosures) and `insertion_observations` (window rows:
stop reason, edited, reanchors, ticks, before/after artifact ids;
`meta_json` carries `undo_candidate`, `after_region`, `range_units`) —
all writes through `Store.submit`. Observed-range texts are
lease-governed artifacts (`range_units: utf16_host` in their meta);
rows and envelope blocks are content-free.

**Transform accepts are attributed to their candidate:** an accepted
selected-text transform submits with `job_id` = its transform candidate
id (`tcand-…`), so its `insertions` row (and any observation rows) join
the reviewed candidate. With collection consent off there is no
candidate: the accept writes no row and is never observed.

## Evidence (S29.4 outcome family)

`EvidenceCollector.on_insertion_result(ctx, result, observation=)`
writes the outcome revision: the real state machine, method, readback,
verification and clipboard disclosure; the observation block (interim
at insert time, final when `on_observation_closed` appends its
revision). The legacy `on_insertion(ctx, posted, chars)` entry keeps
the V1 baseline semantics pinned by the M02 suite. Posted/confirmed/
unknown stays independent of correct/incorrect labels.

## Events

`insertion.confirmed`, `insertion.posted`, `insertion.target_changed`,
`insertion.saved_not_inserted`, `insertion.failed`, `insertion.skipped`
(`duplicate_operation`, `stale_attempt`, `job_deleted`,
`user_cancelled`), `insertion.undo`, `insertion.paste_again`,
`insertion.record_failed`, `insertion.service_unavailable`,
`insertion.cancelled_after_insert` — content-free (chars, method,
reason codes).

## Hosts and testability

`SystemInsertionHost` (element acquisition and ownership through the
M06 `SystemAXHost`; boxed range writes; settability with PyObjC's
out-parameter), `SystemPasteboard` (acknowledgments propagated) and
`SystemKeyboard` isolate every macOS call.

- `tests/v2/insertion/fixture_target.py` — the historical one-field
  instrumented target (scriptable lag, truncation, drops, user copy).
- `tests/v2/insertion/m08_world.py` — the independent multi-app world:
  separate app and element-owner pids, equal-title windows, UTF-16 host
  ranges, a generation clipboard with per-flavour data, a paste
  consumer bound to the system focus, and its own logs of every content
  read and physical effect.
- `tests/v2/insertion/test_m08_remediation.py` — fail-first regressions
  for M08-AUDIT-01..19; `m08_corpus_runner.py` with
  `m08_corpus_adjudications.json` — the frozen audit corpus
  (`m08_audit_corpus.json`); `scripts/v2/m08_mutation_check.py` — its
  20 mutations.
- `tests/v2/insertion/test_native_insertion.py` with
  `native_insertion_target.py` — real Accessibility, real NSPasteboard,
  an owned helper reached by pid (two equal-title windows, text views,
  a field and a secure field, AppKit-side witnesses); the ⌘V consumer is
  emulated by the helper reading a private named pasteboard — no key
  event, never the user's clipboard.

Suites run under `tests/v2/context/run_isolated.py` (live-desktop AX
calls and synthetic events blocked; the general pasteboard redirected
to a private one). Real-destination behavior is the human trial in
`docs/v2/VERIFICATION.html` (M08-V001…).

## Caller inventory (local `rg`, remediation)

Commands: `rg -n` over `localflow tests scripts docs/v2` for
`InsertionService|validate_target|TargetLease|capture_selection|
same_destination|identity_matches`, and over `localflow tests scripts`
for `AXSelectedText|AXSelectedTextRange|AXStringForRange|focused_element|
AXUIElementGetPid|ax_range|ax_box_range`,
`paste_again|paste_text|undo_last|_insertionDone_|_observationStarted_|
_observationFinished_|_retire_active_job`,
`context_denied_apps|app_denied|context_policy|strict_replacement|
outcome_observation`,
`delete_everywhere|_on_job_deleted|job_deleted|conn_job_deleted|
training_buffer|capture_consent|consent_revision|on_observation_closed`
and `record_insertion|record_observation|InsertionResult|
insertion_observations|owned_range_edited|mine_observation_candidates`.
Production consumers, classified:

- **Coordinator (`app.py`):** `configure` (the service with the
  validated deny policy), `startDictation` (`note_new_dictation`), the
  lock/wake handlers (`note_session_locked`/`_unlocked`),
  `_finishWithText_` (`submit`, `observation_consent`),
  `_insertionDone_`/`_retire_active_job` (settle/retire once),
  `_observationStarted_` (`subscribe_close`)/`_observationFinished_`,
  `_on_job_deleted` (`revoke_job`), `_m11_capture_selection` →
  `selection.capture_selection`, `tfAcceptTransform` (strict submit,
  candidate attribution, `observation_consent`), `undoLastInsertion_`
  (`undo_last`), `pasteLastResultAgain_` (`paste_again`), `hubPasteText`
  (`paste_text`), `_tf_pipeline_busy`/`_hub_blocks_show` (`busy`).
- **Hub (`v2/ui/hub.py`):** `historyPasteAgain_` → `hubPasteText`.
- **Evidence (`v2/training.py`):** `on_insertion_result`,
  `on_observation_closed`, `_observation_block` (content-free blocks).
- **Learning/review (`v2/learning.py`, `v2/curation/review.py`):**
  mining reads `owned_range_edited` rows with both artifacts; review
  joins before/after artifacts (`owned_edit_unbounded` rows carry none
  and are never classified).
- **Store (`v2/store.py`):** the `insertions`/`insertion_observations`
  tables, the metadata prune, delete-everywhere and its listeners, the
  artifact barrier.
- **Shared M06 rules:** `context/snapshot.py` (`identity_matches`,
  `app_denied`, `classify_field`), `context/providers.py` (`ax_range`,
  `ax_box_range`, `utf16_len`, `SystemAXHost`).
- **Not M08:** `inject.py` (`copy_text` for recovery offers; the V1
  `paste_text` is unused by the V2 path); `transforms_store.
  record_observation` (M11 preference observations).

## Remediation policy (m08-policy-v1)

The decisions behind the rules above, numbered as in
`tests/v2/insertion/m08_corpus_adjudications.json`: D1 read capability
· D2 recorded destination · D3 destination binding and the effect
boundary · D4 plain destination (M06 D5 carried over; a new live
selection is not a caret move) · D5 strict proof · D6 confirmation · D7
bound readback · D8 the pending clipboard payload · D9 ownership before
the post · D10 operation identity · D11 cancellation linearization ·
D12 observation · D13 deletion · D14 recovery lifetime · D15 terminal
text · D16 substring reconciliation · D17 native evidence · D18
benchmark cases.

## Limitations (documented, not hidden)

- The clipboard method has an inherent window between publication and
  the target's read, and the restore's ownership check and write are
  not atomic (native characterization: a copy landing between them is
  overwritten). The effect-boundary check and the effect are not atomic
  either. Pasteboard atomicity does not exist to close these.
- A target consuming the paste later than the settle bound on a surface
  whose content may not be read pastes after restore — the documented
  residual of `posted_unverified`; readable surfaces keep ownership
  for `PENDING_PAYLOAD_SEC` (5 s) — a consumer later than that, after
  the payload was restored away, pastes the user's clipboard.
- The paste post itself goes to the key focus; the bound check before
  it narrows, but cannot close, a focus change in between.
- Undo needs settable `AXSelectedTextRange`/`AXSelectedText` and the
  original field still focused; otherwise it degrades to the copy
  offer.
- `CERTIFIED_BRACKETED_SURFACES` is empty — every terminal insert that
  a terminal could act on takes the copy-only offer.
- The observer's undo inference is content-based and weak by design;
  changed-length edits keep text only when bounded on both sides.
- An application whose focused element is served by another process
  (for example an out-of-process panel) fails the ownership proof and
  takes the copy offer — to be qualified in M08-V001.
