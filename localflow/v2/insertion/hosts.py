"""Injectable system hosts for the insertion path (V2 M08, Spec S18).

Every macOS call the insertion transaction needs — Accessibility reads
AND writes, the pasteboard, the synthetic paste keystroke — sits behind
an injectable host so the EV-10 race matrix and the EV-19/EV-20
attribution tests run against the instrumented fixture target
(``tests/v2/insertion/fixture_target.py``) instead of the live desktop.
The system hosts follow the M06 ``SystemAXHost`` pattern: one cached
element per surface, a per-call messaging timeout so an unresponsive
app can never stall the queue thread.

Insertion code runs on the insertion service's own serialized thread,
never on the AppKit UI callback (S18/S24: no sleep, pasteboard wait or
delayed restore may block the UI thread).
"""

from __future__ import annotations

import threading
from typing import Optional, Protocol

AX_MESSAGING_TIMEOUT = 0.2


class InsertionHost(Protocol):
    """The Accessibility surface insertion needs (read + write).

    Destination elements come from ``focused_element_for(pid)`` — the
    focused element OF that application, checked with ``element_pid`` —
    never from whatever holds the system focus (the M06 ownership rule;
    ``focused_element`` remains for callers outside M08). Ranges are
    host units (UTF-16 code units on macOS); ``set_attribute`` takes a
    ``(location, length)`` tuple for a range attribute and boxes it."""

    def is_trusted(self) -> bool: ...
    def frontmost(self) -> Optional[dict]: ...
    def focused_element(self): ...
    def focused_element_for(self, pid): ...
    def element_pid(self, el) -> Optional[int]: ...
    def attribute(self, el, name): ...
    def is_settable(self, el, name) -> bool: ...
    def set_attribute(self, el, name, value) -> bool: ...
    def string_for_range(self, el, start: int, length: int) -> Optional[str]: ...
    def number_of_characters(self, el) -> Optional[int]: ...


class SystemInsertionHost:
    """AX reads/writes + NSWorkspace frontmost, each bounded by a
    messaging timeout (an unresponsive target degrades to an honest
    unavailable, never a hung queue thread)."""

    def __init__(self, messaging_timeout: float = AX_MESSAGING_TIMEOUT):
        from ..context.providers import SystemAXHost
        self.messaging_timeout = messaging_timeout
        self._system_el = None
        self._lock = threading.Lock()
        # The M06 typed adapter: application-owned acquisition and the
        # AXUIElementGetPid ownership check (one implementation).
        self._owned = SystemAXHost(messaging_timeout)

    def is_trusted(self) -> bool:
        import ApplicationServices as AS
        return bool(AS.AXIsProcessTrusted())

    def _system(self):
        import ApplicationServices as AS
        with self._lock:
            if self._system_el is None:
                el = AS.AXUIElementCreateSystemWide()
                AS.AXUIElementSetMessagingTimeout(el, self.messaging_timeout)
                self._system_el = el
            return self._system_el

    def frontmost(self) -> Optional[dict]:
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return None
            return {"bundle": app.bundleIdentifier(),
                    "name": app.localizedName(),
                    "pid": app.processIdentifier()}
        except Exception:
            return None

    def focused_element(self):
        import ApplicationServices as AS
        try:
            err, el = AS.AXUIElementCopyAttributeValue(
                self._system(), "AXFocusedUIElement", None)
        except Exception:
            return None
        if err == 0 and el is not None:
            AS.AXUIElementSetMessagingTimeout(
                el, self.messaging_timeout)
            return el
        return None

    def focused_element_for(self, pid):
        """The focused element WITHIN application ``pid`` (or None)."""
        try:
            return self._owned.focused_element_for(pid)
        except Exception:
            return None

    def element_pid(self, el) -> Optional[int]:
        return self._owned.element_pid(el)

    def attribute(self, el, name):
        import ApplicationServices as AS
        try:
            err, val = AS.AXUIElementCopyAttributeValue(el, name, None)
        except Exception:
            return None
        return val if err == 0 else None

    def focused_window_title(self, el) -> Optional[str]:
        """The focused window's title. On the real AX API the window
        lives on the APPLICATION element, not the focused field: the
        system host resolves it there (the fixture answers on the
        field element — both paths land here)."""
        import ApplicationServices as AS
        win = self.attribute(el, "AXFocusedWindow")
        if win is None:
            fm = self.frontmost()
            if fm is None or fm.get("pid") is None:
                return None
            try:
                app_el = AS.AXUIElementCreateApplication(fm["pid"])
                AS.AXUIElementSetMessagingTimeout(
                    app_el, self.messaging_timeout)
                err, val = AS.AXUIElementCopyAttributeValue(
                    app_el, "AXFocusedWindow", None)
            except Exception:
                return None
            win = val if err == 0 else None
            if win is None:
                return None
        title = self.attribute(win, "AXTitle")
        return str(title) if title else None

    def is_settable(self, el, name) -> bool:
        import ApplicationServices as AS
        try:
            # The trailing None is PyObjC's out-parameter placeholder:
            # without it the call raises TypeError, which would make
            # every surface look unsettable (no AX method, no undo).
            err, settable = AS.AXUIElementIsAttributeSettable(
                el, name, None)
        except Exception:
            return False
        return err == 0 and bool(settable)

    def set_attribute(self, el, name, value) -> bool:
        import ApplicationServices as AS
        from ..context.providers import ax_box_range
        try:
            if isinstance(value, tuple) and len(value) == 2:
                # A range write must be a boxed AXValue CFRange (host
                # units) — a bare CFRange is refused natively.
                value = ax_box_range(value[0], value[1])
            err = AS.AXUIElementSetAttributeValue(el, name, value)
        except Exception:
            return False
        return err == 0

    def string_for_range(self, el, start: int, length: int) -> Optional[str]:
        import ApplicationServices as AS
        from ..context.providers import ax_box_range
        try:
            # The range must be a boxed AXValue CFRange — a bare CFRange
            # is refused natively (kAXErrorIllegalArgument).
            err, val = AS.AXUIElementCopyParameterizedAttributeValue(
                el, "AXStringForRange", ax_box_range(start, length), None)
        except Exception:
            return None
        return str(val) if err == 0 and val is not None else None

    def number_of_characters(self, el) -> Optional[int]:
        n = self.attribute(el, "AXNumberOfCharacters")
        try:
            return int(n)
        except (TypeError, ValueError):
            return None


# Pasteboard types LocalFlow can capture as data and restore faithfully.
# Anything else (file promises above all — one-shot, cannot round trip)
# is reported unsupported rather than silently dropped or claimed.
SUPPORTED_PASTEBOARD_TYPES = (
    "public.utf8-plain-text",
    "public.rtf",
    "public.html",
    "public.pdf",
    "public.png",
    "public.tiff",
)
STRING_TYPE = "public.utf8-plain-text"


class PasteboardHost(Protocol):
    """Writes return the new change count when the pasteboard
    acknowledged every write, else None (the board was cleared but the
    data was refused — nothing LocalFlow wrote is on it)."""

    def change_count(self) -> int: ...
    def types(self) -> list: ...
    def data_for_type(self, ptype): ...
    def string_for_type(self, ptype) -> Optional[str]: ...
    def clear_and_write_text(self, text: str) -> Optional[int]: ...
    def clear_and_write_items(self, items) -> Optional[int]: ...


class SystemPasteboard:
    """NSPasteboard wrapper. Ownership generations are the pasteboard's
    own changeCount: capture before publishing, verify the count is
    still LocalFlow's before restoring — a user copy always wins. Each
    native write's acknowledgment is propagated (None = refused)."""

    def __init__(self):
        from AppKit import NSPasteboard
        self._pb = NSPasteboard.generalPasteboard()

    def change_count(self) -> int:
        return int(self._pb.changeCount())

    def types(self) -> list:
        return list(self._pb.types() or [])

    def data_for_type(self, ptype):
        return self._pb.dataForType_(ptype)

    def string_for_type(self, ptype) -> Optional[str]:
        v = self._pb.stringForType_(ptype)
        return str(v) if v is not None else None

    def clear_and_write_text(self, text: str) -> Optional[int]:
        from AppKit import NSPasteboardTypeString
        self._pb.clearContents()
        ok = self._pb.setString_forType_(text, NSPasteboardTypeString)
        return self.change_count() if ok else None

    def clear_and_write_items(self, items) -> Optional[int]:
        from AppKit import NSPasteboardItem
        pb_items = []
        ok = True
        for type_data in items:
            it = NSPasteboardItem.alloc().init()
            for ptype, data in type_data:
                ok = bool(it.setData_forType_(data, ptype)) and ok
            pb_items.append(it)
        self._pb.clearContents()
        ok = bool(self._pb.writeObjects_(pb_items)) and ok
        return self.change_count() if ok else None


KEY_V = 9  # ANSI 'V'


class KeyboardHost(Protocol):
    def post_paste(self) -> bool: ...


class SystemKeyboard:
    """Synthetic Cmd+V via the HID event tap. No Return/Enter synthesis
    exists anywhere in this package (S17/S18: non-execution by default)."""

    def post_paste(self) -> bool:
        try:
            import Quartz
            src = Quartz.CGEventSourceCreate(
                Quartz.kCGEventSourceStateHIDSystemState)
            down = Quartz.CGEventCreateKeyboardEvent(src, KEY_V, True)
            up = Quartz.CGEventCreateKeyboardEvent(src, KEY_V, False)
            Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            return True
        except Exception:
            return False
