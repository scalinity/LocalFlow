"""History Paste Again's one-shot destination pick (POLICY-D03).

Invoking Paste Again authorizes nothing by itself: the Hub steps aside,
and only the user's next deliberate click in another application names
the destination. The picker watches for that click and for Esc with
NSEvent global monitors — they observe, never swallow, so the click
still lands where the user aimed it — and ends on the first of: the
click, Esc, a timeout, or an explicit cancel. Exactly one outcome is
delivered; everything after it is ignored.

Main thread only. ``schedule(delay, fn)`` defaults to
``AppHelper.callLater`` and is injectable for tests; the monitors are
installed through ``install``/``remove`` for the same reason.
"""

from __future__ import annotations

ESC_KEY_CODE = 53
# The click lands and moves focus after the monitor sees it; the target is
# read once that settles.
CLICK_SETTLE_SEC = 0.2
PICK_TIMEOUT_SEC = 30.0
HINT = "Click where you'd like to paste — Esc to cancel"


def _call_later(delay, fn):
    from PyObjCTools import AppHelper
    AppHelper.callLater(delay, fn)


def _clicked_owner_pid():
    """The process owning the window under the pointer at the click — a
    menu-bar item, a banner or the Dock included — or None."""
    import Quartz
    from AppKit import NSEvent, NSWindow
    number = NSWindow.windowNumberAtPoint_belowWindowWithWindowNumber_(
        NSEvent.mouseLocation(), 0)
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionIncludingWindow, number) or []
    return info[0].get(Quartz.kCGWindowOwnerPID) if len(info) else None


def _install_monitors(on_mouse_down, on_key_down):
    from AppKit import NSEvent, NSEventMaskKeyDown, NSEventMaskLeftMouseDown
    return [
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskLeftMouseDown,
            lambda e: on_mouse_down(_clicked_owner_pid())),
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, lambda e: on_key_down(e.keyCode())),
    ]


def _remove_monitors(handles):
    from AppKit import NSEvent
    for h in handles:
        if h is not None:
            NSEvent.removeMonitor_(h)


class PasteHint:
    """A one-line, non-activating, click-through label near the bottom of
    the screen under the mouse; it never takes focus or a click."""

    def __init__(self):
        self._panel = None

    def show(self, text):
        from AppKit import (NSBackingStoreBuffered, NSColor, NSEvent,
                            NSFont, NSMakeRect, NSPanel, NSPointInRect,
                            NSScreen, NSStatusWindowLevel, NSTextField,
                            NSWindowStyleMaskBorderless,
                            NSWindowStyleMaskNonactivatingPanel)
        if self._panel is None:
            w, h = 360.0, 30.0
            panel = NSPanel.alloc()
            panel = panel.initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, w, h),
                NSWindowStyleMaskBorderless
                | NSWindowStyleMaskNonactivatingPanel,
                NSBackingStoreBuffered, False)
            panel.setLevel_(NSStatusWindowLevel)
            panel.setIgnoresMouseEvents_(True)
            panel.setHidesOnDeactivate_(False)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(
                NSColor.colorWithWhite_alpha_(0.1, 0.85))
            label = NSTextField.labelWithString_(text)
            label.setFont_(NSFont.systemFontOfSize_(13))
            label.setTextColor_(NSColor.whiteColor())
            label.setFrame_(NSMakeRect(12, 6, w - 24, h - 12))
            panel.contentView().addSubview_(label)
            self._panel, self._label = panel, label
        self._label.setStringValue_(text)
        loc = NSEvent.mouseLocation()
        screen = next((s for s in NSScreen.screens()
                       if NSPointInRect(loc, s.frame())),
                      NSScreen.mainScreen())
        vis = screen.visibleFrame()
        size = self._panel.frame().size
        self._panel.setFrameOrigin_(
            (vis.origin.x + (vis.size.width - size.width) / 2.0,
             vis.origin.y + 70.0))
        self._panel.orderFrontRegardless()

    def hide(self):
        if self._panel is not None:
            self._panel.orderOut_(None)


class DestinationPicker:
    """One pick at a time. ``arm`` starts it; ``on_pick(clicked_pid)`` runs
    once a click has settled (``clicked_pid``: the process that owned
    the clicked window), ``on_cancel(reason)`` for Esc (``cancelled``), the
    timeout (``timed_out``) or ``cancel(reason)`` — which also ends a
    pick whose click is still settling."""

    def __init__(self, schedule=None, install=None, remove=None):
        self.schedule = schedule or _call_later
        self.install = install or _install_monitors
        self.remove = remove or _remove_monitors
        self._gen = 0
        self._state = "idle"          # idle | armed | settling
        self._handles = []
        self._on_pick = self._on_cancel = None

    @property
    def active(self):
        return self._state != "idle"

    def arm(self, on_pick, on_cancel, timeout_sec=PICK_TIMEOUT_SEC):
        self.cancel("superseded")
        self._gen += 1
        gen = self._gen
        self._state = "armed"
        self._on_pick, self._on_cancel = on_pick, on_cancel
        self._handles = self.install(self.mouse_down, self.key_down) or []
        self.schedule(timeout_sec, lambda: self._expire(gen))

    def mouse_down(self, clicked_pid=None):
        if self._state != "armed":
            return
        self._state = "settling"
        self._unhook()
        gen = self._gen
        self.schedule(CLICK_SETTLE_SEC,
                      lambda: self._picked(gen, clicked_pid))

    def key_down(self, key_code):
        if self._state == "armed" and key_code == ESC_KEY_CODE:
            self.cancel("cancelled")

    def cancel(self, reason):
        if not self.active:
            return
        on_cancel = self._on_cancel
        self._finish()
        on_cancel(reason)

    def _picked(self, gen, clicked_pid):
        if gen != self._gen or self._state != "settling":
            return
        on_pick = self._on_pick
        self._finish()
        on_pick(clicked_pid)

    def _expire(self, gen):
        if gen == self._gen and self._state == "armed":
            self.cancel("timed_out")

    def _unhook(self):
        handles, self._handles = self._handles, []
        if handles:
            self.remove(handles)

    def _finish(self):
        self._gen += 1
        self._state = "idle"
        self._unhook()
        self._on_pick = self._on_cancel = None
