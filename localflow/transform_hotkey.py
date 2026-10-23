"""One narrowly suppressing session event tap for transform commands.

The tap never synthesizes/reposts keys. Unregistered events, including fn,
pass through unchanged. Registered key-down/repeat and paired key-up are
consumed before the foreground app's text handling.
"""
import os
import time
import Quartz as Q
from AppKit import NSWorkspace, NSWorkspaceDidActivateApplicationNotification
from Foundation import NSDistributedNotificationCenter
from PyObjCTools import AppHelper
from .v2.transform_hotkeys import ShortcutRouter
from .v2.transforms.review_keys import ReviewKeyLease, RETURN_KEYS, ESCAPE


def current_input_is_layout():
    """Query the active source, including input methods without named modes."""
    import ctypes
    try:
        carbon = ctypes.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')
        cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        carbon.TISCopyCurrentKeyboardInputSource.argtypes = []
        carbon.TISCopyCurrentKeyboardInputSource.restype = ctypes.c_void_p
        carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
        cf.CFEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFEqual.restype = ctypes.c_ubyte
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        source = carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            return False
        try:
            kind = carbon.TISGetInputSourceProperty(source,
                ctypes.c_void_p.in_dll(carbon, 'kTISPropertyInputSourceType').value)
            layout = ctypes.c_void_p.in_dll(carbon, 'kTISTypeKeyboardLayout').value
            return bool(kind and cf.CFEqual(kind, layout))
        finally:
            cf.CFRelease(source)
    except (OSError, AttributeError, ValueError):
        return False

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
        self.review = ReviewKeyLease(self._review_action)
        self.review_callback = None
        self.review_eligible = True
        self.review_scope = None
        self._activation_observer = None
        self._input_observer = None

    def _invalidate_review(self, reason):
        lease = self.review.lease
        self.review.disarm()
        if lease:
            self._review_action(reason, lease['token'])

    def _input_changed(self, note):
        self.refresh_input_source()
        self._invalidate_review('interception_lost')

    def _app_changed(self, note):
        lease = self.review.lease
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if lease and (front is None or front.processIdentifier() != lease['pid']):
            self._invalidate_review('interception_lost')

    def refresh_input_source(self):
        # Conservatively leave Enter to input methods. Marked composition is
        # not exposed consistently by third-party AX editors; do not guess.
        self.review_eligible = current_input_is_layout()

    def _reconcile_review_keys(self):
        held = {code for code in RETURN_KEYS | {ESCAPE}
                if Q.CGEventSourceKeyState(Q.kCGEventSourceStateCombinedSessionState, code)}
        self.review.reconcile_held(held)

    def _review_action(self, action, token):
        if self.review_callback is not None:
            AppHelper.callAfter(self.review_callback, action, token)

    def replace(self, bindings):
        self.router.replace(bindings)

    def recording(self, active):
        self.record_until = time.monotonic() + 15 if active else 0

    def start(self):
        if self.tap is not None:
            return bool(Q.CGEventTapIsEnabled(self.tap))
        mask = Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
        self.tap = Q.CGEventTapCreate(Q.kCGSessionEventTap,
            Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionDefault, mask,
            self._event, None)
        if self.tap is None:
            self.report("unavailable", "event_tap_permission_required")
            return False
        self.source = Q.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        if self.source is None:
            Q.CFMachPortInvalidate(self.tap)
            self.tap = None
            self.report("unavailable", "event_tap_source_unavailable")
            return False
        Q.CFRunLoopAddSource(Q.CFRunLoopGetMain(), self.source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self.tap, True)
        if not Q.CGEventTapIsEnabled(self.tap):
            self.stop()
            self.report("unavailable", "event_tap_permission_required")
            return False
        self._activation_observer = NSWorkspace.sharedWorkspace().notificationCenter() \
            .addObserverForName_object_queue_usingBlock_(
                NSWorkspaceDidActivateApplicationNotification, None, None, self._app_changed)
        self.refresh_input_source()
        self._reconcile_review_keys()
        self._input_observer = NSDistributedNotificationCenter.defaultCenter() \
            .addObserverForName_object_queue_usingBlock_(
                "com.apple.Carbon.TISNotifySelectedKeyboardInputSourceChanged",
                None, None, self._input_changed)
        self.report("active", None)
        return True

    def stop(self):
        self.review.disarm()
        scope, self.review_scope = getattr(self, "review_scope", None), None
        if scope is not None:
            scope.stop()
        if self._input_observer is not None:
            NSDistributedNotificationCenter.defaultCenter().removeObserver_(self._input_observer)
            self._input_observer = None
        if self._activation_observer is not None:
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self._activation_observer)
            self._activation_observer = None
        if self.tap is None:
            return
        Q.CGEventTapEnable(self.tap, False)
        Q.CFRunLoopRemoveSource(Q.CFRunLoopGetMain(), self.source, Q.kCFRunLoopCommonModes)
        Q.CFMachPortInvalidate(self.tap)
        self.source = self.tap = None
        self.router.down.clear()

    def _event(self, proxy, kind, event, refcon):
        if kind in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            self._invalidate_review('interception_lost')
            self.router.down.clear()
            self._reconcile_review_keys()
            Q.CGEventTapEnable(self.tap, True)
            self.report("reenabled", "event_tap_disabled")
            return event
        code = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
        flags = Q.CGEventGetFlags(event)
        mods = tuple(m for m, mask in FLAGS.items() if flags & mask)
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        pid = front.processIdentifier() if front is not None else None
        if self.review.lease and pid != self.review.lease['pid']:
            self._invalidate_review('interception_lost')
        if self.review.handle(
                'down' if kind == Q.kCGEventKeyDown else 'up', code, mods,
                bool(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat)),
                pid=pid, eligible=self.review_eligible and (
                    pid != os.getpid() or bool(self.review.lease and
                        self.review.lease.get('internal_editor')))
                    and (self.review_scope is None or self.review_scope.valid)):
            return None
        # Recorder suspension is leased and applies only to our own app.
        self.router.suspended = False
        if time.monotonic() < self.record_until:
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            self.router.suspended = front is not None and front.processIdentifier() == os.getpid()
        consume = self.router.handle("down" if kind == Q.kCGEventKeyDown else "up",
            code, mods, bool(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat)))
        return None if consume else event
