"""One narrowly suppressing session event tap for transform commands.

The tap never synthesizes/reposts keys. Unregistered events, including fn,
pass through unchanged. Registered key-down/repeat and paired key-up are
consumed before the foreground app's text handling.
"""
import os
import time
import Quartz as Q
from AppKit import NSWorkspace
from PyObjCTools import AppHelper
from .v2.transform_hotkeys import ShortcutRouter

FLAGS = {"control": Q.kCGEventFlagMaskControl,
         "option": Q.kCGEventFlagMaskAlternate,
         "shift": Q.kCGEventFlagMaskShift,
         "command": Q.kCGEventFlagMaskCommand,
         "fn": Q.kCGEventFlagMaskSecondaryFn}


class TransformHotkeyListener:
    def __init__(self, invoke, report):
        self.router = ShortcutRouter(lambda tid: AppHelper.callAfter(invoke, tid))
        self.report = report
        self.tap = None
        self.source = None
        self.record_until = 0

    def replace(self, bindings):
        self.router.replace(bindings)

    def recording(self, active):
        self.record_until = time.monotonic() + 15 if active else 0

    def start(self):
        if self.tap is not None:
            return True
        mask = Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
        self.tap = Q.CGEventTapCreate(Q.kCGSessionEventTap,
            Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionDefault, mask,
            self._event, None)
        if self.tap is None:
            self.report("unavailable", "event_tap_permission_required")
            return False
        self.source = Q.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        Q.CFRunLoopAddSource(Q.CFRunLoopGetMain(), self.source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self.tap, True)
        self.report("active", None)
        return True

    def stop(self):
        if self.tap is None:
            return
        Q.CGEventTapEnable(self.tap, False)
        Q.CFRunLoopRemoveSource(Q.CFRunLoopGetMain(), self.source, Q.kCFRunLoopCommonModes)
        Q.CFMachPortInvalidate(self.tap)
        self.source = self.tap = None
        self.router.down.clear()

    def _event(self, proxy, kind, event, refcon):
        if kind in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            self.router.down.clear()
            Q.CGEventTapEnable(self.tap, True)
            self.report("reenabled", "event_tap_disabled")
            return event
        code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
        flags = Q.CGEventGetFlags(event)
        mods = tuple(m for m, mask in FLAGS.items() if flags & mask)
        # Recorder suspension is leased and applies only to our own app.
        self.router.suspended = False
        if time.monotonic() < self.record_until:
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            self.router.suspended = front is not None and front.processIdentifier() == os.getpid()
        consume = self.router.handle("down" if kind == Q.kCGEventKeyDown else "up",
            code, mods, bool(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat)))
        return None if consume else event
