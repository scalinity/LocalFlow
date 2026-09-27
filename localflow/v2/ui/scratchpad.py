"""The Scratchpad editor surface (V2 M12, Spec S20, contracts/scratchpad.md).

``ScratchpadEditor`` is the AppKit half of the note editor: an editable
plain-text NSTextView bound to a pure-Python ``NotesEditorModel`` (the
HubState discipline — the model owns autosave/origin/concurrency logic
and is headless-testable; this object only binds AppKit to it).

Origin-aware writing: typed edits ride the autosave debounce; dictated
and transform arrivals replace/insert at the editor's captured
insertion point and flush IMMEDIATELY (never left only in memory behind
a debounce). Saves run on worker threads the editor OWNS (tracked until
they finish, drained before the store closes); explicit actions wait
for the generation they settle, bounded, and say ``pending`` when the
bound expires — never "saved" for something uncommitted.

A note whose outgoing save failed or is still in flight when the editor
switches away is RETAINED (its buffer and queued arrivals), retried by
the autosave tick, shown again when the note is reopened, and settled
at quit — never silently replaced (M12-AUDIT-03).
"""

from __future__ import annotations

import threading
import time

import objc
from AppKit import (NSMakeRect, NSRunLoop, NSRunLoopCommonModes,
                    NSScrollView, NSTextView, NSTimer, NSView)
from Foundation import NSObject

from ..notes import (NotesEditorModel, ORIGIN_ATTACHMENT,
                     ORIGIN_DICTATED, ORIGIN_SNIPPET, ORIGIN_TRANSFORM,
                     TRIGGER_AUTOSAVE, TRIGGER_EXPLICIT, TRIGGER_SYSTEM,
                     utf16_range_to_codepoints)

EDITOR_MIN_W = 360.0
FLUSH_THREAD_NAME = "localflow-notes-autosave"
# How long a switch waits for the outgoing note's save before retaining
# it instead (the main thread never blocks on a slow store for longer).
SWITCH_WAIT_SEC = 0.25


class ScratchpadPane(NSView):
    """The Scratchpad view's container. The Hub shell sizes every pane to
    its content area without autoresizing the children (their frames
    assume the build-time size); this pane instead lays its children out
    again for every size it is given (M12-AUDIT-21), so every action
    stays inside it from the minimum window size up."""

    def setFrameSize_(self, size):
        objc.super(ScratchpadPane, self).setFrameSize_(size)
        layout = getattr(self, "layout_cb", None)
        if layout is not None:
            layout()


class ScratchpadEditor(NSObject):
    """One editor per Hub process; rebound to whichever note is open."""

    @objc.python_method
    def init_editor(self, hub):
        self = self.init()
        self.hub = hub
        self.model = None
        self.note_id = None
        self._programmatic = False
        # Owned save work: every worker thread until it finishes, and
        # the models of notes switched away from with unsaved work.
        self._ops_lock = threading.Lock()
        self._threads = set()
        self._retained = {}
        self._admission_open = True
        self.text = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 400, 200))
        self.text.setEditable_(True)
        self.text.setRichText_(False)
        self.text.setUsesFontPanel_(False)
        self.text.setDelegate_(self)
        self.scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 400, 200))
        self.scroll.setDocumentView_(self.text)
        self.scroll.setHasVerticalScroller_(True)
        self.scroll.setBorderType_(3)  # NSBezelBorder
        # M12-AUDIT-10: the official mode constant. Common modes include
        # the default mode AND menu tracking / modal panels, so a typed
        # tail still saves while a menu or the export panel is open (the
        # tick touches only the model; saves run on worker threads).
        self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "autosaveTick:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(
            self.timer, NSRunLoopCommonModes)
        return self

    # ---- note binding ------------------------------------------------------

    @objc.python_method
    def bind_note(self, detail):
        """Show one note (an ``open_note`` payload). The outgoing note's
        unsaved work is saved first — or, when that save fails or is
        still running, the outgoing model is retained (never replaced
        or dropped). Reopening a note whose model is retained shows that
        model's buffer, which is newer than the store. A note with an
        armed dirty marker surfaces the unsaved-tail banner (M12-AC01)."""
        self._release_outgoing()
        self._programmatic = True
        try:
            rev = detail.get("revision") or {}
            note_id = detail["note_id"]
            with self._ops_lock:
                kept = self._retained.pop(note_id, None)
            if kept is not None and not kept.deleted:
                self.model = kept
            else:
                model = NotesEditorModel(
                    note_id, rev.get("revision_id"),
                    rev.get("content") or "")
                model.on_dirty = \
                    lambda nid, m=model: self._mark_dirty(nid, m)
                self.model = model
            self.note_id = note_id
            self.text.setString_(self.model.content)
        finally:
            self._programmatic = False

    @objc.python_method
    def clear(self):
        self._release_outgoing()
        self._programmatic = True
        try:
            self.note_id = None
            self.model = None
            self.text.setString_("")
        finally:
            self._programmatic = False

    @objc.python_method
    def forget_note(self, note_id):
        """The note was deleted: its retained or bound buffer has nowhere
        to be saved. Queued arrivals settle as discarded."""
        with self._ops_lock:
            kept = self._retained.pop(note_id, None)
        for m in (kept, self.model if self.note_id == note_id else None):
            if m is not None:
                m.discard("note_deleted")
        if self.note_id == note_id:
            self.model = None
            self.clear()

    @objc.python_method
    def _release_outgoing(self):
        """Save the outgoing model on an owned thread, waiting at most
        SWITCH_WAIT_SEC on the main thread; retain the model when that
        save did not settle everything it holds (the tick, a reopen or
        quit finishes it)."""
        model = self.model
        if model is None or not model.dirty:
            return
        t = self.flush_async(model=model)
        if t is not None:
            t.join(SWITCH_WAIT_SEC)
        if model.dirty and not model.deleted:
            with self._ops_lock:
                self._retained[model.note_id] = model

    @objc.python_method
    def unsaved_notes(self):
        """Note ids whose buffers are held here with unsaved work (the
        current one included) — the Hub's visible 'not saved' surface."""
        with self._ops_lock:
            out = [nid for nid, m in self._retained.items() if m.dirty]
        if self.model is not None and self.model.dirty \
                and self.model.last_error is not None:
            out.append(self.model.note_id)
        return out

    @objc.python_method
    def _mark_dirty(self, note_id, model):
        """Arm the unsaved-tail marker without waiting on the store, and
        only if this buffer is still unsaved when the write runs (a
        marker landing after the save of the same edit is a no-op)."""
        svc = self._service()
        if svc is not None:
            try:
                svc.mark_dirty(note_id, only_if=lambda: model.dirty,
                               wait=False)
            except Exception:
                pass

    def _service(self):
        return (self.hub.spec or {}).get("notes_service") \
            if self.hub is not None else None

    # ---- editing ----------------------------------------------------------

    def textDidChange_(self, notification):
        if self._programmatic or self.model is None:
            return
        self.model.edit(str(self.text.string()))

    def autosaveTick_(self, timer):
        self.autosave_tick()

    @objc.python_method
    def autosave_tick(self):
        """Timer tick (and the headless test entry): save every model
        whose debounce expired — the open note's and every retained
        one — on owned worker threads, never the UI callback."""
        if self.model is not None and self.model.due():
            self.flush_async()
        with self._ops_lock:
            kept = list(self._retained.values())
        for m in kept:
            if m.deleted or not m.dirty:
                with self._ops_lock:
                    if self._retained.get(m.note_id) is m:
                        del self._retained[m.note_id]
            elif m.due():
                self.flush_async(model=m)

    @objc.python_method
    def flush_async(self, trigger=TRIGGER_AUTOSAVE, model=None):
        model = model or self.model
        svc = self._service()
        if model is None or svc is None:
            return None

        def work():
            try:
                model.flush(svc, trigger=trigger)
            except Exception:
                pass
            finally:
                with self._ops_lock:
                    self._threads.discard(threading.current_thread())
        with self._ops_lock:
            if not self._admission_open:
                return None     # shutdown settles admitted work itself
            t = threading.Thread(target=work, daemon=True,
                                 name=FLUSH_THREAD_NAME)
            self._threads.add(t)
            t.start()
        return t

    @objc.python_method
    def flush_now(self, trigger=TRIGGER_EXPLICIT, timeout=2.0):
        """The explicit barrier (Snapshot, Restore, Export): persist the
        buffer through the generation current NOW, waiting — bounded —
        for a save already in progress. Returns the model's result;
        ``pending`` means the bound expired first (never "saved")."""
        if self.model is not None and self._service() is not None:
            return self.model.flush(self._service(), trigger=trigger,
                                    timeout=timeout)
        return {"outcome": "no_model"}

    @objc.python_method
    def drain(self, timeout=5.0):
        """Wait for every owned save thread, then save whatever is still
        admitted (the open model and every retained one). Returns
        ``{"drained": bool, "unsaved": [note ids]}``."""
        deadline = time.monotonic() + timeout
        with self._ops_lock:
            threads = list(self._threads)
        for t in threads:
            t.join(max(0.0, deadline - time.monotonic()))
        svc = self._service()
        with self._ops_lock:
            models = list(self._retained.values())
        if self.model is not None:
            models.append(self.model)
        for m in models:
            if m.dirty and svc is not None:
                try:
                    m.flush(svc, timeout=max(
                        0.0, deadline - time.monotonic()))
                except Exception:
                    pass
        with self._ops_lock:
            alive = [t for t in self._threads if t.is_alive()]
        unsaved = [m.note_id for m in models if m.dirty]
        return {"drained": not alive and not unsaved, "unsaved": unsaved,
                "threads_alive": len(alive)}

    @objc.python_method
    def shutdown(self, timeout=3.0):
        """Quit (before the store closes): refuse new input, stop the
        timer, settle every admitted save, and settle any arrival that
        still did not commit as failed (its job then records that
        honestly). Unsaved typed text keeps the store's marker armed,
        so the next open names the tail risk."""
        with self._ops_lock:
            self._admission_open = False
            models = list(self._retained.values())
        if self.model is not None:
            models.append(self.model)
        for m in models:
            m.close()
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None
        status = self.drain(timeout)
        for m in models:
            m.fail_pending("shutdown_before_commit")
        return status

    # ---- attributed arrivals (main thread; flush is immediate) ------------

    @objc.python_method
    def _native_range(self):
        sel = self.text.selectedRange()
        return int(sel.location), int(sel.length)

    @objc.python_method
    def selection(self):
        """The native selection through the ONE validated conversion
        (M12-AUDIT-12/22): ``("none", (cp, cp))`` for a caret,
        ``("range", (s, e))`` for a selection, ``("invalid", None)`` when
        AppKit's range does not fit the text (refused — never widened to
        the whole note or a neighbouring slice)."""
        loc, length = self._native_range()
        try:
            s, e = utf16_range_to_codepoints(str(self.text.string()),
                                             loc, length)
        except ValueError:
            return "invalid", None
        return ("range" if e > s else "none"), (s, e)

    @objc.python_method
    def insertion_point(self):
        """The caret as a CODE-POINT index into the note's content (None
        when the native range is invalid). A nonzero selection anchors
        at its start; a dictation never replaces the selection."""
        kind, rng = self.selection()
        return None if rng is None else rng[0]

    @objc.python_method
    def selected_range(self):
        """The selection as a half-open CODE-POINT range, or None when
        there is no selection or the native range is invalid."""
        kind, rng = self.selection()
        return rng if kind == "range" else None

    @objc.python_method
    def selected_text(self):
        rng = self.selected_range()
        if rng is None:
            return None
        return str(self.text.string())[rng[0]:rng[1]]

    @objc.python_method
    def editor_active(self):
        """The key window's first responder is this editor — the
        coordinator's PTT-time check for a note-bound dictation."""
        window = self.text.window()
        if window is None or not window.isKeyWindow():
            return False
        return window.firstResponder() is not None and \
            window.firstResponder() == self.text

    @objc.python_method
    def receive(self, text, *, origin=ORIGIN_DICTATED,
                source_job_id=None, task_key=None, transform_id=None,
                transform_revision=None, replace_range=None,
                at_chars=None):
        """Insert (or replace a code-point range with) attributed text —
        at the caller's captured anchor when given (the PTT-time
        promise), else the current caret — and start its save at once.
        Returns the arrival's RECEIPT (``notes.Arrival``): truthy means
        the text is in the buffer; durable success is its ``committed``
        outcome. A closed note, or a range that no longer fits, returns
        None (the caller routes to its retained-result path)."""
        if self.model is None or self.note_id is None:
            return None
        if replace_range is None and at_chars is None:
            at_chars = self.insertion_point()
            if at_chars is None:
                return None
        arrival = self.model.insert(
            text, at=at_chars, replace=replace_range, origin=origin,
            trigger=TRIGGER_SYSTEM, source_job_id=source_job_id,
            task_key=task_key, transform_id=transform_id,
            transform_revision=transform_revision)
        if arrival is None:
            return None
        self._programmatic = True
        try:
            self.text.setString_(self.model.content)
        finally:
            self._programmatic = False
        self.flush_async()
        return arrival

    @objc.python_method
    def insert_snippet(self, text):
        return self.receive(text, origin=ORIGIN_SNIPPET)

    @objc.python_method
    def insert_attachment_marker(self, marker):
        return self.receive(marker, origin=ORIGIN_ATTACHMENT)

    @objc.python_method
    def current_content(self):
        return self.text.string()

    @objc.python_method
    def fit_to_scroll(self):
        """Keep the text view as wide as its scroll view's visible area
        and at least as tall (a click anywhere in the editor lands in the
        text view; typed lines wrap at the visible width)."""
        from AppKit import NSMakeSize
        cs = self.scroll.contentSize()
        self.text.setMinSize_(NSMakeSize(0, cs.height))
        self.text.setMaxSize_(NSMakeSize(1e7, 1e7))
        self.text.setVerticallyResizable_(True)
        self.text.setHorizontallyResizable_(False)
        self.text.setAutoresizingMask_(2)       # width follows the clip
        self.text.textContainer().setWidthTracksTextView_(True)
        f = self.text.frame()
        self.text.setFrameSize_(NSMakeSize(cs.width,
                                           max(cs.height, f.size.height)))

    # ---- shutdown ------------------------------------------------------------

    @objc.python_method
    def close(self):
        """Close the editor: new input refused, admitted work settled
        (the model's close never discards it)."""
        return self.shutdown()
