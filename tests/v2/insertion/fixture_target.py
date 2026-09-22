"""The instrumented fixture target for insertion (E10, M08).

An in-process destination with exact readback and reproducible races:
a text field (content, caret, selection), frontmost identity, AX
capability flags, and a scriptable paste consumer whose lag and
truncation model the real hazards — a target that reads the
pasteboard late, or inserts only part of it. The fixture implements
the InsertionHost, PasteboardHost and KeyboardHost protocols over the
same state, so the REAL service, transaction and observer run against
it unmodified.

Race scripting:
- ``paste_lag``      — the target processes the posted ⌘V this many
                       seconds later (reads whatever is on the board
                       at that moment, exactly like a real app).
- ``paste_truncate`` — the target keeps only this many characters of
                       the pasted text (partial insertion).
- ``paste_drops``    — the target ignores the paste entirely.
- ``user_copy(...)`` — a user/app clipboard write at any moment (the
                       ownership-generation race).
"""

from __future__ import annotations

import threading
import time


class FakePasteboard:
    """ChangeCount-accurate pasteboard with multi-representation
    items: ``ops`` records every mutating call in order (the race
    suites assert non-interleaving against it)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._count = 0
        self._items = []           # list of {type: payload}
        self.ops = []

    # ---- PasteboardHost protocol --------------------------------------

    def change_count(self) -> int:
        with self._lock:
            return self._count

    def types(self) -> list:
        with self._lock:
            out = []
            for item in self._items:
                for t in item:
                    if t not in out:
                        out.append(t)
            return out

    def data_for_type(self, ptype):
        # First item that provides the type — the real NSPasteboard
        # resolves dataForType: through items in order (the restore
        # path writes one item, so ordering only matters for the
        # multi-item user-copy fixtures).
        with self._lock:
            for item in self._items:
                if ptype in item:
                    return item[ptype]
            return None

    def string_for_type(self, ptype):
        v = self.data_for_type(ptype)
        return v.decode("utf-8") if isinstance(v, bytes) else v

    def clear_and_write_text(self, text: str) -> int:
        with self._lock:
            self.ops.append(("write_text", len(text)))
            self._count += 1
            self._items = [{"public.utf8-plain-text":
                            text.encode("utf-8")}]
            return self._count

    def clear_and_write_items(self, items) -> int:
        with self._lock:
            self.ops.append(("write_items", len(items)))
            self._count += 1
            self._items = [dict(pairs) for pairs in items]
            return self._count

    # ---- test helpers ---------------------------------------------------

    def current_string(self):
        return self.string_for_type("public.utf8-plain-text")

    def current_types(self):
        return self.types()

    def user_copy(self, text=None, items=None):
        """A user (or another app) takes the clipboard mid-flight."""
        if items is not None:
            return self.clear_and_write_items(items)
        return self.clear_and_write_text(text)


class FixtureTargetApp:
    """The instrumented destination. Also answers the InsertionHost
    protocol over its own state (the focused element token is the app
    itself)."""

    def __init__(self, *, bundle="com.apple.TextEdit", pid=4242,
                 role="AXTextArea", window_title="Untitled.txt",
                 settable=True, ax_readable=True):
        self.bundle = bundle
        self.pid = pid
        self.frontmost_info = {"bundle": bundle, "name": "Fixture",
                               "pid": pid}
        self.role = role
        self.window_title = window_title
        self.settable = settable
        self.ax_readable = ax_readable
        self.content = ""
        self.caret = 0
        self.selection = (0, 0)
        self.paste_lag = 0.0
        self.paste_truncate = 0            # 0 = no truncation
        self.paste_drops = False
        self.paste_events = []             # (t, text_consumed)
        self.pb = FakePasteboard()
        # Field coherence: a real AX text field exposes content and
        # selection atomically to readers; the paste consumer, the
        # insertion thread and the observer all read concurrently.
        self._state_lock = threading.RLock()
        self._timer_lock = threading.Lock()

    # ---- KeyboardHost: the paste consumer --------------------------------

    def post_paste(self) -> bool:
        with self._timer_lock:
            self._timer = threading.Timer(
                self.paste_lag, self._consume_paste)
            self._timer.daemon = True
            self._timer.start()
        return True

    def _consume_paste(self):
        text = self.pb.current_string() or ""
        self.paste_events.append((time.monotonic(), text))
        if self.paste_drops or text == "":
            return
        if self.paste_truncate:
            text = text[:self.paste_truncate]
        self.replace_selection(text)

    # ---- field model -------------------------------------------------------

    def replace_selection(self, text: str):
        with self._state_lock:
            s, e = self.selection
            self.content = self.content[:s] + text + self.content[e:]
            self.caret = s + len(text)
            self.selection = (self.caret, self.caret)

    def type_text(self, text: str, at: int):
        """User typing at an arbitrary offset (outside-range edits)."""
        with self._state_lock:
            self.content = self.content[:at] + text + self.content[at:]
            if self.caret >= at:
                self.caret += len(text)
            self.selection = (self.caret, self.caret)

    def set_content(self, text: str):
        with self._state_lock:
            self.content = text
            self.caret = min(self.caret, len(text))
            self.selection = (self.caret, self.caret)

    # ---- InsertionHost protocol -------------------------------------------

    def is_trusted(self) -> bool:
        return True

    def frontmost(self):
        return dict(self.frontmost_info)

    def focused_element(self):
        return self if self.ax_readable or self.settable else None

    def attribute(self, el, name):
        if el is not self:
            return None
        with self._state_lock:
            if name == "AXRole":
                return self.role
            if name == "AXSelectedTextRange":
                return _Range(self.selection[0],
                              self.selection[1] - self.selection[0])
            if name == "AXNumberOfCharacters":
                return len(self.content)
            if name == "AXFocusedWindow":
                return ("window", self.window_title)
        if name == "AXTitle" and isinstance(el, tuple):
            return el[1]
        return None

    def is_settable(self, el, name) -> bool:
        if el is not self:
            return False
        if name == "AXSelectedText":
            return self.settable
        if name == "AXSelectedTextRange":
            return self.settable
        return False

    def set_attribute(self, el, name, value) -> bool:
        if el is not self or not self.is_settable(el, name):
            return False
        if name == "AXSelectedText":
            self.replace_selection(str(value))
            return True
        if name == "AXSelectedTextRange":
            with self._state_lock:
                loc, length = int(value.location), int(value.length)
                self.selection = (loc, loc + length)
                self.caret = loc + length
            return True
        return False

    def string_for_range(self, el, start: int, length: int):
        if el is not self or not self.ax_readable:
            return None
        with self._state_lock:
            if start < 0 or start + length > len(self.content):
                return None
            return self.content[start:start + length]

    def number_of_characters(self, el):
        if el is not self:
            return None
        with self._state_lock:
            return len(self.content)


class _Range:
    """CFRange-shaped value (location/length) for attribute reads."""

    def __init__(self, location, length):
        self.location = location
        self.length = length
