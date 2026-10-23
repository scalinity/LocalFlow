"""One candidate's AX focus lease, observed away from the event-tap callback.

``start()`` establishes and subscribes to an exact field/window pair on a
dedicated run-loop thread. ``valid`` reads only cached state. ``on_invalidated``
takes no arguments and normally runs on that observer thread (the caller thread
reports a startup timeout); an AppKit caller should enqueue UI cleanup.
``stop()`` is silent and permanent. Create a new scope for each candidate, and
still revalidate the insertion target before writing.

No field value, selection, document, or title text is read. Terminal titles
serve only as change notifications: a title notification revokes the lease.
"""
from __future__ import annotations

import threading

from ..context.providers import TERMINAL_BUNDLES

FOCUSED_ELEMENT = "AXFocusedUIElementChanged"
FOCUSED_WINDOW = "AXFocusedWindowChanged"
DEACTIVATED = "AXApplicationDeactivated"
TITLE_CHANGED = "AXTitleChanged"
MENU_OPENED = "AXMenuOpened"


class _NativeHost:
    """The existing PyObjC AX bridge and Quartz/CoreFoundation run-loop API."""

    def __init__(self):
        import ApplicationServices as AS
        import Quartz as Q
        import objc
        self.AS, self.Q = AS, Q
        self._pool = objc.autorelease_pool()
        self._pool.__enter__()
        self._native_callback = None

    def trusted(self):
        return bool(self.AS.AXIsProcessTrusted())

    def application(self, pid):
        app = self.AS.AXUIElementCreateApplication(pid)
        self.AS.AXUIElementSetMessagingTimeout(app, .05)
        return app

    def read(self, element, attribute):
        error, value = self.AS.AXUIElementCopyAttributeValue(element, attribute, None)
        if error != 0 or value is None:
            raise ValueError("focus_unavailable")
        return value

    def pid_of(self, element):
        error, pid = self.AS.AXUIElementGetPid(element, None)
        if error != 0:
            raise ValueError("focus_owner_unavailable")
        self.AS.AXUIElementSetMessagingTimeout(element, .05)
        return int(pid)

    def frontmost_pid(self):
        # System-wide AXFocusedApplication can return cannotComplete even
        # while the application's owned focus attributes work. Use the same
        # native application identity source as insertion, then read only that
        # application's AX field/window and verify their actual owner.
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            raise ValueError("focus_unavailable")
        return int(app.processIdentifier())

    def same(self, left, right):
        return bool(left is not None and right is not None and self.Q.CFEqual(left, right))

    def bundle_id(self, pid):
        from AppKit import NSRunningApplication
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        return str(app.bundleIdentifier()) if app and app.bundleIdentifier() else None

    def observer(self, pid, callback):
        import objc
        # callbackFor does not support decorating methods. A plain closure also
        # keeps the candidate callback alive until native source teardown.
        def deliver(observer, element, notification, context):
            callback(observer, element, notification, context)
        self._native_callback = objc.callbackFor(self.AS.AXObserverCreate)(deliver)
        error, observer = self.AS.AXObserverCreate(pid, self._native_callback, None)
        if error != 0 or observer is None:
            raise ValueError("observer_unavailable")
        return observer

    def source(self, observer):
        source = self.AS.AXObserverGetRunLoopSource(observer)
        if source is None:
            raise ValueError("observer_source_unavailable")
        return source

    def current_loop(self):
        return self.Q.CFRunLoopGetCurrent()

    def add_source(self, loop, source):
        self.Q.CFRunLoopAddSource(loop, source, self.Q.kCFRunLoopDefaultMode)
        if not self.Q.CFRunLoopContainsSource(loop, source, self.Q.kCFRunLoopDefaultMode):
            raise ValueError("observer_source_unavailable")

    def remove_source(self, loop, source):
        self.Q.CFRunLoopRemoveSource(loop, source, self.Q.kCFRunLoopDefaultMode)
        self.Q.CFRunLoopSourceInvalidate(source)

    def add_notification(self, observer, element, name):
        if self.AS.AXObserverAddNotification(observer, element, name, None) != 0:
            raise ValueError("focus_notification_unavailable")

    def remove_notification(self, observer, element, name):
        self.AS.AXObserverRemoveNotification(observer, element, name)

    def run_once(self):
        # This waits for notifications; it does not poll Accessibility. A bounded
        # wait also closes the stop-before-CFRunLoopRun race during startup.
        result = self.Q.CFRunLoopRunInMode(self.Q.kCFRunLoopDefaultMode, .1, False)
        return result not in (self.Q.kCFRunLoopRunFinished, self.Q.kCFRunLoopRunStopped)

    def wake(self, loop):
        self.Q.CFRunLoopStop(loop)
        self.Q.CFRunLoopWakeUp(loop)

    def close(self):
        self._native_callback = None
        self._pool.__exit__(None, None, None)
        self._pool = None


class FocusScope:
    """Fail-closed, one-use field/window guard with an injectable native host.

    start() returns whether the target was established and all required
    notifications subscribed. Startup failure also calls on_invalidated once.
    host= is for focused lifecycle tests; production uses the native host.
    """

    def __init__(self, pid, on_invalidated, expected_element=None,
                 expected_window=None, *, host=None, allow_window_ancestors=False,
                 required_role=None):
        if type(pid) is not int or pid <= 0 or not callable(on_invalidated):
            raise ValueError("invalid_focus_scope")
        self.pid = pid
        self.on_invalidated = on_invalidated
        self.expected_element = expected_element
        self.expected_window = expected_window
        self.allow_window_ancestors = bool(allow_window_ancestors)
        self.required_role = required_role
        self.reason = None
        self._host = host
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._started = False
        self._valid = False
        self._invalidated = False
        self._thread = None
        self._loop = self._observer = self._source = None
        self._app = self._element = self._window = None
        self._callback = None
        self._title_guard = False

    @property
    def valid(self):
        with self._lock:
            return self._valid

    @property
    def element(self):
        with self._lock:
            return self._element

    @property
    def window(self):
        with self._lock:
            return self._window

    def start(self):
        with self._lock:
            if self._started or self._stopping.is_set():
                return self._valid
            self._started = True
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="LocalFlow candidate focus")
            self._thread.start()
        if not self._ready.wait(2):
            self._invalidate("focus_startup_timeout")
        return self.valid

    def stop(self):
        with self._lock:
            self._valid = False
            self._stopping.set()
            loop, host, thread = self._loop, self._host, self._thread
        if loop is not None and host is not None:
            try:
                host.wake(loop)
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _invalidate(self, reason):
        with self._lock:
            if self._stopping.is_set() or self._invalidated:
                return
            self._valid = False
            self.reason = reason
            self._invalidated = True
            self._stopping.set()
        try:
            self.on_invalidated()
        except Exception:
            pass  # client cleanup must not strand the native source

    def _capture(self):
        host = self._host
        if not host.trusted() or host.frontmost_pid() != self.pid:
            raise ValueError("focus_unavailable")
        element = host.read(self._app, "AXFocusedUIElement")
        window = host.read(self._app, "AXFocusedWindow")
        if host.pid_of(element) != self.pid or host.pid_of(window) != self.pid:
            raise ValueError("focus_owner_changed")
        if self.required_role is not None and host.read(element, "AXRole") != self.required_role:
            raise ValueError("focus_role_changed")
        try:
            containing = window if host.same(element, window) else host.read(element, "AXWindow")
        except ValueError:
            if not self.allow_window_ancestors:
                raise
            containing = None
        if self.allow_window_ancestors and not host.same(containing, window):
            # WKWebView can expose a non-window AXWindow value. Only the
            # internal note path opts in; prove the exact window by ancestry.
            if containing is not None:
                role = None
                try:
                    role = host.read(containing, "AXRole")
                except ValueError:
                    pass
                if role == "AXWindow":
                    raise ValueError("focus_window_changed")
            ancestor, seen = element, []
            for _ in range(16):
                if host.same(ancestor, window):
                    containing = window
                    break
                if any(host.same(ancestor, old) for old in seen) or \
                        host.pid_of(ancestor) != self.pid:
                    break
                seen.append(ancestor)
                ancestor = host.read(ancestor, "AXParent")
        if not host.same(containing, window) or host.frontmost_pid() != self.pid:
            raise ValueError("focus_window_changed")
        return element, window

    def _notification(self, observer, element, notification, refcon):
        if self._stopping.is_set():
            return
        try:
            host = self._host
            name = str(notification)
            if not host.same(observer, self._observer):
                raise ValueError("focus_observer_changed")
            if name == DEACTIVATED:
                raise ValueError("focus_app_changed")
            if name == MENU_OPENED:
                # Native menus can track keys while AX still reports the
                # editor as first responder. Retire this candidate's lease.
                raise ValueError("focus_menu_opened")
            if name == TITLE_CHANGED and self._title_guard:
                raise ValueError("focus_window_title_changed")
            target = {FOCUSED_ELEMENT: self._element, FOCUSED_WINDOW: self._window}.get(name)
            if target is None:
                raise ValueError("focus_notification_unknown")
            # The notification can carry the changed target. Check it as well
            # as current focus so a queued away-and-back change is not missed.
            if not host.same(element, self._app) and not host.same(element, target):
                raise ValueError("focus_target_changed")
            current_element, current_window = self._capture()
            if not host.same(current_element, self._element) or \
                    not host.same(current_window, self._window):
                raise ValueError("focus_target_changed")
        except Exception as error:
            self._invalidate(str(error) if isinstance(error, ValueError) else "focus_check_failed")

    def _run(self):
        registrations = []
        source_added = False
        try:
            if self._host is None:
                self._host = _NativeHost()
            host = self._host
            self._app = host.application(self.pid)
            self._element, self._window = self._capture()
            if self.expected_element is not None and not host.same(self.expected_element, self._element):
                raise ValueError("expected_element_changed")
            if self.expected_window is not None and not host.same(self.expected_window, self._window):
                raise ValueError("expected_window_changed")
            # Unknown bundle identity cannot exempt a possible terminal from
            # title observation. No title text is needed or retained.
            bundle = host.bundle_id(self.pid)
            self._title_guard = bundle is None or bundle in TERMINAL_BUNDLES
            self._callback = self._notification  # retained until source teardown
            self._observer = host.observer(self.pid, self._callback)
            self._source = host.source(self._observer)
            self._loop = host.current_loop()
            source_added = True
            host.add_source(self._loop, self._source)
            required = [(self._app, FOCUSED_ELEMENT), (self._app, FOCUSED_WINDOW),
                        (self._app, DEACTIVATED), (self._app, MENU_OPENED)]
            if self._title_guard:
                required.append((self._window, TITLE_CHANGED))
            for element, name in required:
                host.add_notification(self._observer, element, name)
                registrations.append((element, name))
            # Close the capture/subscription gap before admitting Enter.
            element, window = self._capture()
            if not host.same(element, self._element) or not host.same(window, self._window):
                raise ValueError("focus_changed_during_start")
            with self._lock:
                self._valid = not self._stopping.is_set()
            self._ready.set()
            while not self._stopping.is_set():
                if not host.run_once():
                    self._invalidate("focus_observer_stopped")
        except Exception as error:
            self._invalidate(str(error) if isinstance(error, ValueError) else "focus_observer_failed")
        finally:
            self._ready.set()
            with self._lock:
                self._valid = False
            host = self._host
            for element, name in reversed(registrations):
                try:
                    host.remove_notification(self._observer, element, name)
                except Exception:
                    pass
            if source_added:
                try:
                    host.remove_source(self._loop, self._source)
                except Exception:
                    pass
            self._observer = self._source = self._callback = self._loop = None
            self._app = self._element = self._window = None
            if host is not None:
                try:
                    host.close()
                except Exception:
                    pass
