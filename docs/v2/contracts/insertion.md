# Contract: Safe insertion, clipboard transactions and recovery undo

**Spec:** S18, S12 (revalidation half), S24 (UI-thread rule), S29.8
(outcome observation) · **Owner:** M08 · **Suites:** EV-10
(tests/v2/insertion/), EV-19/EV-20 (attribution half)

`localflow.v2.insertion` (`result`, `hosts`, `clipboard`,
`target_lease`, `validation`, `record`, `observation`, `service`)
delivers the S18 contract: finished text lands only in the intended
field, never overwrites a new user clipboard copy, and every insertion
carries an honest `InsertionResult`.

## The serialized queue (one transaction at a time)

`InsertionService` owns a single daemon thread. The coordinator's
`_finishWithText_` only enqueues (`submit`) — **no AX call, pasteboard
write or settle sleep ever runs on the UI callback** (the V1 path
slept 50 ms inline and restored on a racing 0.6 s thread). Completed
jobs never interleave clipboard transactions: two finishing dictations
share the queue, so one job's restore can never clobber the next job's
publish.

## Target validation (the M06 `same_destination` consumer)

`validation.validate_target(host, snapshot, job)` runs immediately
before writing, on the queue thread, bounded by the host's AX
messaging timeout (0.2 s). The settled matrix:

| Check | Rule | Failure |
|---|---|---|
| identity | the shared M06 rule `snapshot.identity_matches` (`same_destination` on a full snapshot and on a bare PTT-time `TargetSnapshot`; `TargetLease.identity_matches` re-checks with it): a usable pid on both sides, else a usable bundle on both sides; a pid match with two different known bundles is refused; absent identity never matches | `target_changed` |
| window | the M06 window element (in memory on the pre-decode snapshot) vs the live field's `AXWindow`, compared by host identity, when both exist — another window of the same app is a change even under an equal title; the recorded title vs the live focused-window title ALSO applies whenever both exist (tabs share one window element) (the system host resolves `AXFocusedWindow` from the application element; unreadable ⇒ `unavailable`) | `target_changed` |
| field | focused role vs the snapshot's recorded role; an unreadable live role degrades to `unavailable` — identity alone governs | `target_changed` |
| selection | **only a recorded NON-EMPTY selection** (replacement case) must still match exactly (range + text), compared in the host's own AX units: the snapshot's `selected_range_utf16` against the live `AXSelectedTextRange` (a native `AXValue` CFRange, decoded — never parsed), falling back to `selected_range` for hosts without native units; the live text is read with a boxed `AXStringForRange` | `target_changed` |

A moved caret is never a target change: the caret is the insertion
point, and queued results land in dictation order. Another field of the
same role in the same window is not a target change either (a
different role, window, app or identity is). A snapshot with no
field data (denied/unclassifiable/AX off/context disabled) validates on
identity alone — plain dictation proceeds; the live caret is still
read as the owned-range anchor. `target_changed` routes the artifact
to saved history with the text left on the clipboard as the one-action
paste offer; nothing is inserted into the newly focused destination.

**Strict replacement** (`job["strict_replacement"]`, set only by an
accepted selected-text transform — contracts/transforms.md). Replacing
text the user reviewed needs positive proof, so every `unavailable` in
the matrix refuses: the window title must be recorded at capture and
read back equal, and the field's own window element recorded at
capture must be the live one (the M06 element-and-title rule); the
role must read back equal; the recorded non-empty selection must read
back with the same range (host units: `selected_range_utf16`) and
text; and the bounded text recorded on either side of it
(`FieldContext.preceding_text` / `following_text`, up to 200 host
units, captured by `insertion/selection.py`) must read back unchanged
— a second document in the same app can match title, role, range and
text. The verdicts
ride the verification JSON as `surroundings` and `strict`; a refusal
is `target_changed` with the copy offer. Plain dictation (no flag)
keeps the permissive matrix above unchanged.

`TargetLease` is the granted authority token; a cancelled job never
receives one (the service refuses the transaction with
`saved_not_inserted/user_cancelled` and touches nothing).

## Method matrix (probed at insert time, recorded per transaction)

1. **Cancelled job** ⇒ no transaction.
2. **Terminal destination + multi-line text + no certified
   bracketed-paste surface** ⇒ copy-only offer
   (`saved_not_inserted/multiline_terminal_unverified`); a terminal can
   execute embedded newlines during paste, so the promise is
   non-execution by default. The category comes from the snapshot, and
   when the job carries no snapshot at all (context disabled / PTT
   identity failed) the LIVE frontmost bundle is classified — the
   guard never depends on the context collector having been available.
   No synthetic Return exists anywhere in this package.
   `CERTIFIED_BRACKETED_SURFACES` is empty until E10's terminal trials
   certify a real surface.
3. **Accessibility not trusted** ⇒ copy-only offer (V1 recovery
   parity, `accessibility_not_trusted`).
4. **Settable `AXSelectedText`** on the focused element ⇒ **AX
   replacement**; the clipboard is never touched.
5. Otherwise ⇒ the **serialized clipboard transaction**.

## Clipboard ownership (S18)

`ClipboardTransaction` on the queue thread: capture the pasteboard
change count (generation 0) plus every supported representation's data
(`public.utf8-plain-text`, `public.rtf`, `public.html`, `public.pdf`,
`public.png`, `public.tiff` — restored as ONE item carrying all
flavors); unsupported types (file promises above all) are reported in
`unsupported_types`, never claimed. Publish the transcript (owned
generation); post the paste; wait the settle bound (0.6 s, the V1
value, now off the UI thread — readback polls cut it short when the
surface is observable); then restore **only if the pasteboard still
holds LocalFlow's owned generation** — a user copy always wins
(`restore_skipped_reason: user_copy_won`).

Delayed targets: when readback is observable and the paste has NOT
landed at the settle bound, ownership is kept
(`readback_pending`) so a late target read still pastes the RIGHT
text; the sacrificed user clipboard is disclosed. Beyond that bound on
unobservable surfaces, the residual delayed-paste risk is documented
and such results stay `posted_unverified`.

## Result states and readback (never the clipboard)

`confirmed · posted_unverified · target_changed · saved_not_inserted
· failed`. `confirmed` requires a pre-write consistency read plus a
post-write readback of the owned range equal to the inserted text —
reading LocalFlow's own pasteboard proves nothing about the
destination and is never used as confirmation. On the clipboard path,
a readback that matches content which the pre-write read showed was
ALREADY there (re-dictated phrase over identical text) is ambiguous
(`readback_ambiguous`): it never confirms and never triggers an early
restore — the owned generation is kept so a late target read still
pastes the right text. Partial readbacks (truncated paste) report
`readback: partial` and stay `posted_unverified`; the target consumed
the paste, so restoring is safe.

## Undo (target-bound) and retry reconciliation

`undo_last` binds to the last insertion's lease: identity must still
match, and the owned range must still hold exactly the inserted text —
a newer user edit (or an application undo of a different revision)
degrades to offering the previous text on the clipboard (no offer when
a caret insert has no previous text). No synthetic Backspace exists.
Undo and paste-again run their bounded work on the queue thread (menu
actions dispatch via callback; the UI never blocks on AX or the
settle wait). `paste_again` is explicit user intent (menu action) and
still reconciles first with capped field reads: if the accessible text
already contains the previous result (substring guard — approximate by
design) it reports `already_present` and pastes nothing; otherwise a
fresh transaction is submitted asynchronously (validated with no
recorded snapshot: insert-on-faith under explicit intent).

**History's Paste Again engine (M09):** `paste_text(text, job_id=None,
on_done=None)` is the same reconcile-then-submit contract for
arbitrary retained text. The job id rides along so the `insertions`
row and any observation stay attributed; a jobless (legacy-row)
repaste records no attribution row rather than failing the NOT NULL
constraint. **`busy`** reports whether an insertion or undo op is
executing on the queue thread — the coordinator's focus-steal guard
defers Hub window actions for exactly that window (see `hub.md`).

## S29.8 bounded outcome observation (starts here, not in M14)

A `confirmed` insertion proves the surface's AX reads self-consistent
— that is the certification. `OutcomeObserver` then watches the owned
range for up to `outcome_observation_sec` (default 30 s; 0 disables),
on its own daemon thread, 0.5 s ticks: reads cover ONLY the owned
range (edits outside it re-anchor the range within ±400 code points
and are never attributed); an edit intersecting the range stops the
window (`owned_range_edited`) with before/after texts as
lease-governed artifacts carrying exact target/job/region attribution.
Stop conditions with recorded reasons: `window_elapsed`,
`focus_lost`, `field_changed`, `secure_field_transition` (always, even
without a recorded role), `new_dictation` (timestamped: only
dictations starting after the window opened), `session_locked`,
`target_read_failed`. Uncertified surfaces never poll — the envelope
records `outcome_observation_unavailable` with the
`unreliable_target` reason. An undo-like revert is inferred only
weakly (content returned to the pre-insertion state, field shrank by
exactly the inserted length) and recorded as `undo_candidate`, never
as approval; `no_edit_observed` and confirmed pastes never create
correctness labels or preferences (M08-AC06).

## Persistence (store schema v4, additive)

`insertions` (one row per transaction: state, method, verification
JSON, owned range, clipboard JSON with ownership generations) and
`insertion_observations` (window rows: stop reason, edited, reanchors,
ticks, before/after artifact ids) — all writes through `Store.submit`
(writer-thread discipline). Observed-range texts are lease-governed
artifacts; rows and envelope blocks are content-free. The jobs table
is unchanged (attribution joins through `job_id`).

**Transform accepts are attributed to their candidate:** an accepted
selected-text transform submits with `job_id` = its transform
candidate id (`tcand-…`), so its `insertions` row (and any observation
rows) join the reviewed candidate. There is no `jobs` row for that id,
so the dictation metadata-retention pass never prunes it; the row is
content-free. With collection consent off there is no candidate and
the accept writes no row (the jobless repaste pattern).

## Evidence (S29.4 outcome family)

`EvidenceCollector.on_insertion_result(ctx, result, observation=)`
writes the outcome revision: the real state machine, method,
readback, verification and clipboard disclosure; the observation block
(interim at insert time, final when `on_observation_closed` appends
its revision). The legacy `on_insertion(ctx, posted, chars)` entry
keeps the V1 baseline semantics pinned by the M02 suite. Posted/
confirmed/unknown stays independent of correct/incorrect labels;
repeated dictations link only through job/attempt ids.

## Events

`insertion.confirmed`, `insertion.posted`, `insertion.target_changed`,
`insertion.saved_not_inserted`, `insertion.failed`,
`insertion.skipped` (existing), `insertion.undo`,
`insertion.paste_again`, `insertion.record_failed`,
`insertion.service_unavailable` (construction failure ⇒ copy-only),
`insertion.cancelled_after_insert` (a cancel that landed mid-
transaction after the insert physically ran — the evidence records the
real state) — content-free (chars, method, reason codes).

## Hosts and testability

`SystemInsertionHost`/`SystemPasteboard`/`SystemKeyboard` isolate
every macOS call; the instrumented fixture target
(`tests/v2/insertion/fixture_target.py`) implements all three host
protocols over one coherent field state with scriptable races
(`paste_lag` delayed consumption, `paste_truncate` partial insertion,
`paste_drops`, `user_copy`) — E10's "instrumented fixture app for
exact target readback and reproducible races". Real-destination
behavior is the pending human trial (E10's eight destination classes).

## Limitations (documented, not hidden)

- The clipboard method has an inherent vulnerability window between
  publish and the target's read (tens of ms): a clipboard write
  landing exactly there can be pasted instead of the transcript. The
  AX method has no such window; no clipboard-based inserter can close
  it. Documented, not claimed solved. The restore's check-then-write
  carries the same micro-window (a copy landing between the ownership
  check and the restore write is overwritten) — pasteboard atomicity
  does not exist to close it.
- A target consuming the paste later than the settle bound on an
  unobservable surface pastes after restore — the documented residual
  of `posted_unverified`; observable surfaces keep ownership instead
  (`readback_pending`).
- Undo of clipboard-path inserts requires settable
  `AXSelectedTextRange`/`AXSelectedText`; otherwise it degrades to the
  copy offer.
- `CERTIFIED_BRACKETED_SURFACES` is empty — every multi-line terminal
  insert takes the copy-only offer until a surface is certified by
  the E10 terminal trial.
- The observer's undo inference is content-based and weak by design;
  when the field shrank below the insert span, the after-text is the
  whole remaining field (attribution over the region).
