"""The insertion service: one serialized transaction queue (S18, M08).

Only the parent's coordinator may issue an insertion (contracts/
worker.md: the worker has no insertion op); within the parent, this
service is the single queue thread — completed jobs never interleave
clipboard transactions (two finishing dictations each used to run
their own 0.6 s restore thread against a shared pasteboard).

Method matrix (settled by capability probes at insert time, recorded
per transaction — contracts/insertion.md):

1. Cancelled job ⇒ no transaction (authority already revoked).
2. Terminal destination + multi-line text + no certified bracketed-
   paste surface ⇒ copy-only offer (``saved_not_inserted``); a
   terminal can execute embedded newlines during paste, so the
   promise is non-execution by default. No synthetic Return exists
   anywhere in this package.
3. Accessibility not trusted ⇒ copy-only offer (V1 recovery parity).
4. Focused element exposes a settable ``AXSelectedText`` ⇒ AX
   replacement — the clipboard is never touched.
5. Otherwise ⇒ the serialized clipboard transaction with ownership
   generations (``clipboard.ClipboardTransaction``).

``confirmed`` requires a pre-write consistency read plus a post-write
readback of the owned range equal to the inserted text — never the
clipboard (reading LocalFlow's own pasteboard proves nothing about the
destination, E10). Everything else is honestly ``posted_unverified``.

Undo is target-bound (``undo_last``): stale ranges and edited regions
show the previous text for manual recovery; destructive backspaces do
not exist here. Retry reconciliation (``paste_again``) reads the
accessible text first and never blindly re-pastes.
"""

from __future__ import annotations

import queue as queue_mod
import threading
import time
from typing import Callable, Optional

from .. import ids
from ..context.providers import categorize
from . import record
from .clipboard import ClipboardTransaction, PASTE_SETTLE_SEC
from .hosts import InsertionHost, KeyboardHost, PasteboardHost
from .observation import OutcomeObserver, StopSignals
from .result import (METHOD_AX, METHOD_CLIPBOARD, METHOD_NONE,
                     STATE_CONFIRMED, STATE_FAILED,
                     STATE_POSTED_UNVERIFIED, STATE_SAVED_NOT_INSERTED,
                     STATE_TARGET_CHANGED, InsertionResult)
from .target_lease import TargetLease
from .validation import validate_target

# Bracketed-paste-certified terminal surfaces. Empty by decision: no
# real terminal surface is verified (E10's terminal trials are the
# pending human check), so every multi-line terminal insert takes the
# copy-only offer until one is certified. The fixture target joins
# this set in tests.
CERTIFIED_BRACKETED_SURFACES: tuple = ()

READBACK_POLL_SEC = 0.05

# paste_again's reconciliation reads at most this many characters of the
# focused field (bounded so a pathological document cannot stall the
# caller — the check is a duplicate guard, not a guarantee).
PASTE_AGAIN_READ_CAP = 200_000


class InsertionService:
    """Owns the single insertion thread. ``submit`` enqueues and returns
    immediately — the UI callback never waits on AX, the pasteboard or
    a settle sleep (the benchmark proves the enqueue path's cost)."""

    def __init__(self, *, host: InsertionHost, pasteboard: PasteboardHost,
                 keyboard: KeyboardHost, store, emit,
                 restore_clipboard: bool = True,
                 observation_window_sec: float = 30.0,
                 settle_sec: Optional[float] = None,
                 on_post_begin: Optional[Callable] = None,
                 on_post_end: Optional[Callable] = None,
                 sleep=time.sleep):
        self.host = host
        self.pasteboard = pasteboard
        self.keyboard = keyboard
        self.store = store
        self.emit = emit
        self.restore_clipboard = bool(restore_clipboard)
        self.observation_window_sec = float(observation_window_sec)
        self._settle_sec = settle_sec
        self._on_post_begin = on_post_begin
        self._on_post_end = on_post_end
        self._sleep = sleep
        self.signals = StopSignals()
        self._q: "queue_mod.Queue" = queue_mod.Queue()
        self._undo_lock = threading.Lock()
        self._undo_record: Optional[dict] = None
        self._last_text: Optional[str] = None
        self._thread = threading.Thread(
            target=self._run, name="localflow-v2-insertion", daemon=True)
        self._thread.start()

    # ---- public API (called from the coordinator/UI thread) ----------

    def submit(self, text: str, job: dict, on_done: Callable,
               on_observation: Optional[Callable] = None) -> None:
        """Enqueue one insertion; ``on_done(result)`` and (optionally)
        ``on_observation(info)`` fire on the queue/observer threads —
        callers dispatch to their own thread."""
        self._q.put(("insert", text, job, on_done, on_observation))

    def note_new_dictation(self):
        """S29.8 stop condition: a new dictation ends observation."""
        self.signals.note_new_dictation()

    def note_session_locked(self):
        self.signals.note_session_locked()

    def note_session_unlocked(self):
        """Wake/unlock re-arms observation — a lock is a state, not a
        one-way event (otherwise the first sleep would end every future
        observation window at tick 0)."""
        self.signals.note_session_unlocked()

    # ---- undo (target-bound, S18) ------------------------------------

    def undo_last(self, on_done: Optional[Callable] = None) -> Optional[dict]:
        """Undo LocalFlow's own most recent insertion. Never deletes
        newer user edits: a range that no longer holds exactly our
        text, or a destination that is no longer the recorded target,
        degrades to showing the previous text (clipboard copy) —
        no synthetic Backspace is ever sent. Runs on the queue thread
        (bounded AX writes never touch the UI callback); ``on_done``
        receives the outcome dict there, otherwise the caller blocks
        on completion (tests)."""
        holder = {}
        done = threading.Event()

        def _deliver(outcome):
            holder["outcome"] = outcome
            if on_done is not None:
                try:
                    on_done(outcome)
                except Exception:
                    pass
            done.set()

        self._q.put(("undo", _deliver))
        if on_done is None:
            done.wait(15.0)
            return holder.get("outcome")
        return None

    def _undo_now(self) -> dict:
        with self._undo_lock:
            rec = self._undo_record
        if rec is None:
            return {"outcome": "nothing_to_undo"}
        lease: TargetLease = rec["lease"]
        if not lease.identity_matches(self.host.frontmost()):
            self.emit("insertion.undo", level="INFO",
                      job_id=lease.job_id, outcome="no_authority",
                      reason_code="target_changed")
            return {"outcome": "no_authority"}
        el = self.host.focused_element()
        if el is None or not self.host.is_settable(el, "AXSelectedText") \
                or not self.host.is_settable(el, "AXSelectedTextRange"):
            self._offer_recovery(rec["before_text"])
            self.emit("insertion.undo", level="INFO",
                      job_id=lease.job_id, outcome="unsupported_surface",
                      reason_code="ax_range_write_unsupported")
            return {"outcome": "unsupported_surface",
                    "recovery": "clipboard_copy" if rec["before_text"]
                    else "none"}
        start, end = rec["owned_range"]
        current = self.host.string_for_range(el, start, end - start)
        if current != rec["inserted_text"]:
            # The region changed after our insert (user edits, another
            # paste, an application undo of a different revision):
            # showing the previous text is the safe recovery.
            self._offer_recovery(rec["before_text"])
            self.emit("insertion.undo", level="INFO",
                      job_id=lease.job_id, outcome="stale_range_shown",
                      reason_code="owned_range_no_longer_ours")
            return {"outcome": "stale_range",
                    "recovery": "clipboard_copy" if rec["before_text"]
                    else "none"}
        from CoreFoundation import CFRange
        if not self.host.set_attribute(
                el, "AXSelectedTextRange", CFRange(start, end - start)):
            self._offer_recovery(rec["before_text"])
            return {"outcome": "unsupported_surface",
                    "recovery": "clipboard_copy" if rec["before_text"]
                    else "none"}
        if not self.host.set_attribute(el, "AXSelectedText",
                                       rec["before_text"]):
            self._offer_recovery(rec["before_text"])
            self.emit("insertion.undo", level="WARNING",
                      job_id=lease.job_id, outcome="undo_unverified",
                      reason_code="selected_text_write_failed")
            return {"outcome": "undo_unverified"}
        after = self.host.string_for_range(
            el, start, len(rec["before_text"]))
        undone = after == rec["before_text"]
        self.emit("insertion.undo", level="INFO", job_id=lease.job_id,
                  outcome="undone" if undone else "undo_unverified")
        with self._undo_lock:
            self._undo_record = None
        return {"outcome": "undone" if undone else "undo_unverified"}

    # ---- retry reconciliation (S18) -----------------------------------

    def paste_again(self) -> dict:
        """Explicit user intent (menu action). Reconciles first with
        bounded reads: if the accessible text already contains the
        previous result, report ``already_present`` and paste nothing
        (no duplicate insert); otherwise submit a fresh transaction for
        the same text — the actual paste runs on the queue thread, so
        this never blocks the caller on the settle wait (the re-paste
        revalidates with no recorded snapshot: insert-on-faith under
        explicit intent). The substring reconciliation is a duplicate
        guard, not a guarantee — a short dictated phrase that appears
        anywhere in the field counts as present."""
        with self._undo_lock:
            rec = self._undo_record
            text = self._last_text
        if rec is None or text is None:
            return {"outcome": "nothing_to_paste"}
        el = self.host.focused_element()
        if el is not None:
            total = self.host.number_of_characters(el)
            if total is not None:
                cap = min(total, PASTE_AGAIN_READ_CAP)
                content = self.host.string_for_range(el, 0, cap) or ""
                if text in content:
                    self.emit(
                        "insertion.paste_again", level="INFO",
                        job_id=rec["lease"].job_id,
                        outcome="already_present",
                        reason_code="reconciled_accessible_text")
                    return {"outcome": "already_present"}
        # Explicit intent authorizes the re-paste; a fresh transaction
        # still runs asynchronously on the queue (the target may have
        # changed since the original insert).
        self.submit(text, {"job_id": rec["lease"].job_id,
                           "attempt": rec["lease"].attempt},
                    lambda _r: None)
        self.emit("insertion.paste_again", level="INFO",
                  job_id=rec["lease"].job_id, outcome="repaste_submitted")
        return {"outcome": "repaste_submitted"}

    # ---- queue thread --------------------------------------------------

    def _run(self):
        while True:
            item = self._q.get()
            if item[0] == "undo":
                _tag, deliver = item
                try:
                    outcome = self._undo_now()
                except Exception as e:
                    outcome = {"outcome": "undo_error",
                               "reason_code": type(e).__name__}
                deliver(outcome)
                continue
            _tag, text, job, on_done, on_observation = item
            try:
                result = self._transaction(text, job, on_observation)
            except Exception as e:
                result = InsertionResult(
                    insertion_id=ids.new_id("ins"),
                    job_id=job.get("job_id"),
                    attempt=int(job.get("attempt", 1)),
                    state=STATE_FAILED,
                    reason_code=f"transaction_error:{type(e).__name__}",
                    method=METHOD_NONE,
                    created_at_utc=ids.now_utc_iso())
            try:
                on_done(result)
            except Exception:
                pass

    def _transaction(self, text, job, on_observation) -> InsertionResult:
        insertion_id = ids.new_id("ins")
        snapshot = job.get("context_snapshot") or job.get("target")
        category = getattr(
            getattr(snapshot, "target", snapshot), "category", "unknown")
        if category == "unknown":
            # No snapshot carried a category (context disabled / PTT
            # identity failed): classify the LIVE frontmost bundle so
            # the terminal guard never depends on the context collector
            # having been available (review critical — a missing
            # snapshot must not let newlines paste into a shell).
            fm = self.host.frontmost()
            live_bundle = fm.get("bundle") if fm else None
            category = categorize(live_bundle) if live_bundle else "unknown"
        common = dict(
            insertion_id=insertion_id, job_id=job.get("job_id"),
            attempt=int(job.get("attempt", 1)),
            target_snapshot_id=getattr(
                getattr(snapshot, "target", snapshot),
                "target_snapshot_id", None),
            context_snapshot_id=getattr(snapshot, "context_snapshot_id",
                                        None),
            created_at_utc=ids.now_utc_iso())

        # 1. Cancelled: insertion authority was revoked the moment the
        #    user cancelled — no transaction, no clipboard touch.
        if job.get("cancelled"):
            return self._finish(InsertionResult(
                state=STATE_SAVED_NOT_INSERTED,
                reason_code="user_cancelled", method=METHOD_NONE,
                inserted_chars=0, **common))

        # 2. Multi-line terminal hazard: without a certified
        #    bracketed-paste surface, offer copy-only. Never a
        #    synthetic Return, never a blind paste that could execute
        #    partial commands.
        surface = getattr(snapshot, "site_origin", None) or category
        if (category == "terminal" and "\n" in text
                and surface not in CERTIFIED_BRACKETED_SURFACES):
            self.pasteboard.clear_and_write_text(text)
            return self._finish(InsertionResult(
                state=STATE_SAVED_NOT_INSERTED,
                reason_code="multiline_terminal_unverified",
                method=METHOD_NONE, inserted_chars=0,
                clipboard={"restored_types": [],
                           "unsupported_types": [],
                           "offer": "clipboard_copy"},
                **common))

        # 3. Accessibility trust (V1 recovery parity): copy-only offer.
        if not self.host.is_trusted():
            self.pasteboard.clear_and_write_text(text)
            return self._finish(InsertionResult(
                state=STATE_SAVED_NOT_INSERTED,
                reason_code="accessibility_not_trusted",
                method=METHOD_NONE, inserted_chars=0,
                clipboard={"restored_types": [],
                           "unsupported_types": [],
                           "offer": "clipboard_copy"},
                **common))

        # 4. Revalidate immediately before writing.
        lease, verification = validate_target(self.host, snapshot, job)
        if lease is None:
            # Target changed: the output is already a history artifact
            # upstream; leave it on the clipboard as the one-action
            # paste offer. Never insert into the newly focused
            # destination.
            self.pasteboard.clear_and_write_text(text)
            return self._finish(InsertionResult(
                state=STATE_TARGET_CHANGED,
                reason_code="revalidation_failed", method=METHOD_NONE,
                inserted_chars=0, verification=verification,
                clipboard={"restored_types": [],
                           "unsupported_types": [],
                           "offer": "clipboard_copy"},
                **common))

        # 5. Method selection: AX replacement when the focused element
        #    exposes a settable AXSelectedText; else the clipboard
        #    transaction.
        el = self.host.focused_element()
        if el is not None and self.host.is_settable(el, "AXSelectedText"):
            return self._ax_insert(text, lease, el, common, on_observation)
        return self._clipboard_insert(text, lease, common, on_observation)

    # ---- AX replacement -------------------------------------------------

    def _ax_insert(self, text, lease, el, common, on_observation):
        sel_range = self._current_range(el)
        precheck = sel_range is not None
        owned_start = (lease.selected_range[0]
                       if lease.replace_selection and lease.selected_range
                       else (sel_range[0] if sel_range is not None else 0))
        # The overwritten selection must be read BEFORE the write —
        # after it, the old range holds the new text (undo before-text).
        before_text = self._replaced_text(lease, el)
        if not self.host.set_attribute(el, "AXSelectedText", text):
            return self._finish(InsertionResult(
                state=STATE_FAILED, reason_code="ax_write_failed",
                method=METHOD_AX, verification=lease.verification,
                inserted_chars=0, **common))
        owned = (owned_start, owned_start + len(text))
        readback = self._readback(el, owned, text)
        state = (STATE_CONFIRMED
                 if readback == "match" and precheck
                 else STATE_POSTED_UNVERIFIED)
        result = InsertionResult(
            state=state,
            reason_code=None if state == STATE_CONFIRMED
            else f"readback_{readback or 'unavailable'}",
            method=METHOD_AX, verification=lease.verification,
            owned_start=owned[0], owned_end=owned[1],
            inserted_chars=len(text), readback=readback or "unavailable",
            **common)
        self._remember_undo(lease, text, owned, before_text=before_text)
        return self._finish(result,
                            self._observe(result, lease, text, owned,
                                          on_observation))

    def _replaced_text(self, lease, el) -> str:
        """The text a replacement insert is about to overwrite (undo's
        before-text); empty for caret inserts."""
        if not lease.replace_selection or not lease.selected_range:
            return ""
        s, e = lease.selected_range
        return self.host.string_for_range(el, s, e - s) or ""

    # ---- clipboard transaction -------------------------------------------

    def _clipboard_insert(self, text, lease, common, on_observation):
        txn = ClipboardTransaction(
            self.pasteboard,
            settle_sec=(self._settle_sec if self._settle_sec is not None
                        else PASTE_SETTLE_SEC),
            sleep=self._sleep)
        # Pre-write consistency read (the contract's confirmed rule): the
        # owned range BEFORE the paste. If it already equals the text
        # (re-dictated phrase over identical content), an early poll
        # match is ambiguous — it may be the pre-existing text, not our
        # paste landing — and must never confirm or trigger an early
        # restore (the paste could still be pending).
        caret = lease.caret if lease.caret is not None else 0
        el0 = self.host.focused_element()
        pre_content = None
        if el0 is not None:
            pre_content = self.host.string_for_range(el0, caret, len(text))
        captured = txn.capture()
        txn.publish(text)
        if self._on_post_begin is not None:
            try:
                self._on_post_begin()
            except Exception:
                pass
        posted = self.keyboard.post_paste()
        if self._on_post_end is not None:
            try:
                self._on_post_end()
            except Exception:
                pass
        if not posted:
            return self._finish(InsertionResult(
                state=STATE_FAILED, reason_code="paste_post_failed",
                method=METHOD_CLIPBOARD, verification=lease.verification,
                inserted_chars=0,
                clipboard=self._clipboard_block(txn, captured, None),
                **common))
        readback, owned = self._await_readback(
            text, lease, ambiguous_pre=(pre_content == text))
        restored = None
        if self.restore_clipboard:
            if readback == "match" or readback == "partial":
                # match: the paste landed; partial: the target already
                # consumed it (content changed) — both are safe to
                # restore. None (unobservable) restores per the V1
                # protocol.
                restored = txn.restore_if_owned()
            elif readback is None:
                restored = txn.restore_if_owned()
            else:
                # mismatch or ambiguous: the paste may not have landed.
                # Keep the owned generation so a late target read still
                # pastes the right text; the sacrificed user clipboard
                # is disclosed via restore_skipped_reason (wrong-insert
                # prevention outranks restore on observable surfaces).
                txn.restore_skipped_reason = (
                    "readback_ambiguous" if readback == "match_ambiguous"
                    else "readback_pending")
        result = InsertionResult(
            state=(STATE_CONFIRMED
                   if readback == "match" else STATE_POSTED_UNVERIFIED),
            reason_code=None if readback == "match"
            else f"readback_{readback or 'unavailable'}",
            method=METHOD_CLIPBOARD, verification=lease.verification,
            owned_start=owned[0], owned_end=owned[1],
            inserted_chars=len(text), readback=readback or "unavailable",
            clipboard=self._clipboard_block(txn, captured, restored),
            **common)
        self._remember_undo(lease, text, owned, before_text="")
        return self._finish(result,
                            self._observe(result, lease, text, owned,
                                          on_observation))

    def _await_readback(self, text, lease, ambiguous_pre: bool = False):
        """Wait the settle bound for the target to consume the paste,
        polling readback when the surface exposes it (early exit once
        the owned range shows the text — UNLESS the pre-write read
        already matched, where an early match proves nothing). Returns
        (readback, owned); readback None means the surface is
        unobservable; 'match_ambiguous' means the range holds the text
        but it held it before the paste too."""
        el = self.host.focused_element()
        caret = lease.caret if lease.caret is not None else 0
        owned = (caret, caret + len(text))
        settle = (self._settle_sec if self._settle_sec is not None
                  else PASTE_SETTLE_SEC)
        deadline = time.monotonic() + settle
        if el is None:
            self._sleep(max(0.0, deadline - time.monotonic()))
            return None, owned
        while True:
            if time.monotonic() >= deadline:
                if ambiguous_pre:
                    # The range shows the text but showed it before the
                    # paste as well — unattributable, never confirmed.
                    final = self._readback(el, owned, text)
                    if final == "match":
                        return "match_ambiguous", owned
                    return final, owned
                return self._readback(el, owned, text), owned
            content = self.host.string_for_range(
                el, owned[0], owned[1] - owned[0])
            if content == text and not ambiguous_pre:
                return "match", owned
            self._sleep(READBACK_POLL_SEC)

    # ---- shared helpers ---------------------------------------------------

    def _current_range(self, el):
        rng = self.host.attribute(el, "AXSelectedTextRange")
        try:
            return (int(rng.location),
                    int(rng.location) + int(rng.length))
        except (AttributeError, TypeError, ValueError):
            return None

    def _readback(self, el, owned, text) -> Optional[str]:
        """Read the owned range clamped to the field: an out-of-bounds
        read on a live element means the text has NOT landed (the range
        extends past the end) — that is a mismatch, not an unavailable
        surface; None is reserved for surfaces that cannot be read at
        all (they restore per the V1 protocol)."""
        total = self.host.number_of_characters(el)
        if total is None:
            return None
        start, end = owned
        cstart = max(0, min(start, total))
        cend = max(cstart, min(end, total))
        content = self.host.string_for_range(
            el, cstart, cend - cstart)
        if content is None:
            return None
        if content == text:
            return "match"
        if 0 < len(content) < len(text) and text.startswith(content):
            return "partial"
        return "mismatch"

    def _clipboard_block(self, txn, captured, restored):
        return {
            "generation_before": captured.generation,
            "generation_published": txn.published_generation,
            "generation_after_restore": txn.restored_generation,
            "captured_types": [t for t, _ in captured.items],
            "restored_types": ([t for t, _ in captured.items]
                               if restored else []),
            "unsupported_types": captured.unsupported_types,
            "restore_skipped_reason": txn.restore_skipped_reason,
        }

    def _remember_undo(self, lease, text, owned, before_text):
        with self._undo_lock:
            self._undo_record = {
                "lease": lease, "inserted_text": text,
                "owned_range": owned, "before_text": before_text}
            self._last_text = text

    def _offer_recovery(self, text: str):
        """Non-destructive recovery: the previous text goes to the
        clipboard for a manual paste — never a synthetic keystroke."""
        if text:
            self.pasteboard.clear_and_write_text(text)

    def _observe(self, result, lease, text, owned, on_observation):
        """S29.8: observe only certified (= readback-consistent)
        surfaces; a confirmed insertion is the evidence. Uncertified
        surfaces never poll — the envelope reports
        outcome_observation_unavailable instead (M08-AC05)."""
        if result.state != STATE_CONFIRMED \
                or self.observation_window_sec <= 0:
            return None
        try:
            retention = self.store.retention_days.get("training_buffer", 30)
        except AttributeError:
            retention = 30
        observer = OutcomeObserver(
            self.host, self.store, lease, text, owned[0], owned[1],
            result.insertion_id,
            window_sec=self.observation_window_sec,
            stop_signals=self.signals,
            retention_days=retention)
        try:
            observer.begin()
        except Exception:
            return None
        if on_observation is not None:
            try:
                on_observation({"observer": observer,
                                "insertion": result})
            except Exception:
                pass
        return observer

    def _finish(self, result: InsertionResult,
                observation: Optional[OutcomeObserver] = None
                ) -> InsertionResult:
        try:
            record.record_insertion(self.store, result)
        except Exception as e:
            self.emit("insertion.record_failed", level="WARNING",
                      job_id=result.job_id,
                      reason_code=type(e).__name__)
        return result
