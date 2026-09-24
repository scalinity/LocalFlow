"""The Scratchpad editor surface (V2 M12, Spec S20, contracts/scratchpad.md).

``ScratchpadEditor`` is the AppKit half of the note editor: an editable
plain-text NSTextView bound to a pure-Python ``NotesEditorModel`` (the
HubState discipline — the model owns autosave/origin/concurrency logic
and is headless-testable; this object only binds AppKit to it).

Origin-aware writing: typed edits ride the autosave debounce; dictated
and transform arrivals replace/insert at the editor's captured
insertion point and flush IMMEDIATELY (never left only in memory behind
a debounce). Debounced autosaves run on a worker thread so typing never
blocks on the store writer; the explicit actions (snapshot, restore,
switching notes) flush synchronously — bounded by the measured store
latency (flush p95 well under a millisecond at personal scale).
"""

from __future__ import annotations

import threading

import objc
from AppKit import (NSMakeRect, NSRunLoop, NSScrollView, NSTextView,
                    NSTimer)
from Foundation import NSObject

from ..notes import (NotesEditorModel, ORIGIN_ATTACHMENT,
                     ORIGIN_DICTATED, ORIGIN_SNIPPET, ORIGIN_TRANSFORM,
                     TRIGGER_EXPLICIT, TRIGGER_SYSTEM)

EDITOR_MIN_W = 360.0


class ScratchpadEditor(NSObject):
    """One editor per Hub process; rebound to whichever note is open."""

    @objc.python_method
    def init_editor(self, hub):
        self = self.init()
        self.hub = hub
        self.model = None
        self.note_id = None
        self._programmatic = False
        self._flush_thread = None
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
        self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "autosaveTick:", None, True)
        from AppKit import NSRunLoop
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, "default")
        return self

    # ---- note binding ------------------------------------------------------

    @objc.python_method
    def bind_note(self, detail):
        """Show one note (an ``open_note`` payload). The outgoing note's
        unsaved debounce tail is flushed first — switching notes never
        discards a dirty buffer. A note with an armed dirty marker
        surfaces the unsaved-tail risk banner (M12-AC01): the marker
        says editing began and no save followed after the forced
        interruption."""
        self._flush_outgoing()
        self._programmatic = True
        try:
            rev = detail.get("revision") or {}
            self.note_id = detail["note_id"]
            self.model = NotesEditorModel(
                detail["note_id"], rev.get("revision_id"),
                rev.get("content") or "",
                on_dirty=self._mark_dirty)
            self.text.setString_(rev.get("content") or "")
        finally:
            self._programmatic = False

    @objc.python_method
    def clear(self):
        self._flush_outgoing()
        self._programmatic = True
        try:
            self.note_id = None
            self.model = None
            self.text.setString_("")
        finally:
            self._programmatic = False

    @objc.python_method
    def _flush_outgoing(self):
        """Persist the outgoing model's debounce tail (bounded by the
        measured flush p95; personal scale)."""
        model, svc = self.model, self._service()
        if model is not None and svc is not None and model.dirty:
            try:
                model.flush(svc)
            except Exception:
                pass  # the dirty marker stays armed — the honest signal

    @objc.python_method
    def _mark_dirty(self, note_id):
        svc = self._service()
        if svc is not None:
            try:
                svc.mark_dirty(note_id)
            except Exception:
                pass

    def _service(self):
        return (self.hub.spec or {}).get("notes_service") \
            if self.hub is not None else None

    # ---- editing ----------------------------------------------------------

    def textDidChange_(self, notification):
        if self._programmatic or self.model is None:
            return
        self.model.edit(self.text.string())

    def autosaveTick_(self, timer):
        self.autosave_tick()

    @objc.python_method
    def autosave_tick(self):
        """Timer tick (and the headless test entry): flush when the
        debounce expired — on a worker thread, never the UI callback."""
        if self.model is not None and self.model.due():
            self.flush_async()

    @objc.python_method
    def flush_async(self, trigger="autosave"):
        model, svc = self.model, self._service()
        if model is None or svc is None:
            return
        def work():
            try:
                model.flush(svc, trigger=trigger)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True,
                         name="localflow-notes-autosave").start()

    @objc.python_method
    def flush_now(self, trigger=TRIGGER_EXPLICIT):
        """Synchronous flush (explicit snapshot button; tests)."""
        if self.model is not None and self._service() is not None:
            return self.model.flush(self._service(), trigger=trigger)
        return {"outcome": "no_model"}

    # ---- attributed arrivals (main thread; flush is immediate) ------------

    @objc.python_method
    def insertion_point(self):
        sel = self.text.selectedRange()
        return int(sel.location)

    @objc.python_method
    def selected_range(self):
        """The selection as a half-open CODE-POINT range over the
        editor's content (NSRange counts UTF-16 units; an emoji before
        the selection would otherwise shift the slice)."""
        from ..notes import utf16_range_to_codepoints
        sel = self.text.selectedRange()
        return utf16_range_to_codepoints(
            str(self.text.string()), int(sel.location), int(sel.length))

    @objc.python_method
    def selected_text(self):
        sel = self.text.selectedRange()
        if sel.length > 0:
            s, e = self.selected_range()
            return str(self.text.string())[s:e]
        return None

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
        """Insert (or replace a range with) attributed text — at the
        caller's captured anchor when given (the PTT-time promise), else
        the editor's current position; flushes immediately on a worker
        thread. A note that was closed mid-dictation reports False (the
        coordinator routes to saved_not_inserted, never an external
        paste)."""
        if self.model is None or self.note_id is None:
            return False
        content = self.text.string()
        start = self.insertion_point() if at_chars is None \
            else int(at_chars)
        start = max(0, min(start, len(content)))
        if replace_range is not None:
            start = int(replace_range[0])
            end = int(replace_range[1])
            content = content[:start] + text + content[end:]
        else:
            content = content[:start] + text + content[start:]
        self._programmatic = True
        try:
            self.text.setString_(content)
        finally:
            self._programmatic = False
        self.model.receive(
            content, origin=origin, trigger=TRIGGER_SYSTEM,
            source_job_id=source_job_id, task_key=task_key,
            transform_id=transform_id,
            transform_revision=transform_revision,
            inserted_at_chars=start, inserted_text=text)
        self.flush_async()
        return True

    @objc.python_method
    def insert_snippet(self, text):
        return self.receive(text, origin=ORIGIN_SNIPPET)

    @objc.python_method
    def insert_attachment_marker(self, marker):
        return self.receive(marker, origin=ORIGIN_ATTACHMENT)

    @objc.python_method
    def current_content(self):
        return self.text.string()

    # ---- shutdown ------------------------------------------------------------

    @objc.python_method
    def close(self):
        if self.model is not None:
            self.model.close()
        if self.timer is not None:
            self.timer.invalidate()
