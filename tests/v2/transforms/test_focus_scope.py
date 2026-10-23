"""Candidate focus guard: fake lifecycle plus a content-free native source smoke.

Run with the repository venv's Python. No windows/apps are opened or activated
and no input events are posted. Native smoke allocates a source for this process
and passively checks current focus references, never field/title text.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import queue
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from localflow.v2.transforms.focus_scope import (
    DEACTIVATED, FOCUSED_ELEMENT, FOCUSED_WINDOW, TITLE_CHANGED, MENU_OPENED, FocusScope,
)


@dataclass(frozen=True)
class Ref:
    key: str
    pid: int = 101


class FakeHost:
    def __init__(self):
        self.app = Ref("app")
        self.element = Ref("field")
        self.window = Ref("window")
        self.containing_window = self.window
        self.front = 101
        self.permission = True
        self.bundle = "com.apple.TextEdit"
        self.observer_ref = Ref("observer")
        self.source_ref = object()
        self.loop_ref = object()
        self.callback = None
        self.registrations = []
        self.removed = []
        self.sources = []
        self.reads = []
        self.native_threads = set()
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.delivered = threading.Event()
        self.fail = None
        self.on_subscribe = None
        self.read_gate = None

    def trusted(self):
        self.native_threads.add(threading.get_ident())
        return self.permission

    def application(self, pid):
        self.native_threads.add(threading.get_ident())
        return self.app

    def read(self, element, attribute):
        self.native_threads.add(threading.get_ident())
        self.reads.append((element, attribute))
        if self.read_gate is not None:
            self.read_gate.wait(2)
        if self.fail == attribute:
            raise ValueError("focus_unavailable")
        # A title or value read is a test failure, including during startup.
        if attribute == "AXFocusedUIElement":
            return self.element
        if attribute == "AXFocusedWindow":
            return self.window
        if attribute == "AXWindow":
            return self.containing_window
        raise AssertionError("content read: " + attribute)

    def pid_of(self, element):
        if element is None:
            raise ValueError("focus_unavailable")
        return element.pid

    def frontmost_pid(self):
        return self.front

    def same(self, left, right):
        return left is not None and right is not None and left == right

    def bundle_id(self, pid):
        return self.bundle

    def observer(self, pid, callback):
        if self.fail == "observer":
            raise ValueError("observer_unavailable")
        self.callback = callback
        return self.observer_ref

    def source(self, observer):
        if self.fail == "source":
            raise ValueError("observer_source_unavailable")
        return self.source_ref

    def current_loop(self):
        return self.loop_ref

    def add_source(self, loop, source):
        self.sources.append((loop, source))
        if self.fail == "add_source":
            raise ValueError("observer_source_unavailable")

    def remove_source(self, loop, source):
        self.sources.remove((loop, source))
        if self.fail == "remove_source":
            raise RuntimeError("synthetic cleanup failure")

    def add_notification(self, observer, element, name):
        if self.fail == name:
            raise ValueError("focus_notification_unavailable")
        self.registrations.append((element, name))
        if self.on_subscribe is not None:
            self.on_subscribe(name)

    def remove_notification(self, observer, element, name):
        self.removed.append((element, name))
        if self.fail == "remove_notification":
            raise RuntimeError("synthetic cleanup failure")

    def run_once(self):
        try:
            event = self.events.get(timeout=.02)
        except queue.Empty:
            return True
        if event == "finished":
            return False
        if event == "wake":
            return True
        name, element, observer = event
        self.callback(observer, element, name, None)
        self.delivered.set()
        return True

    def wake(self, loop):
        self.events.put("wake")

    def close(self):
        self.closed.set()

    def emit(self, name, element=None, observer=None):
        self.delivered.clear()
        self.events.put((name, element if element is not None else self.app,
                         observer if observer is not None else self.observer_ref))


class FocusScopeTests(unittest.TestCase):
    def make_scope(self, host=None, callback=None, **kwargs):
        host = host or FakeHost()
        calls = []
        scope = FocusScope(101, callback or (lambda: calls.append(threading.get_ident())),
                           host=host, **kwargs)
        self.addCleanup(scope.stop)
        return scope, host, calls

    def assert_closed(self, scope, host):
        self.assertTrue(host.closed.wait(1), "observer did not close")
        scope.stop()
        self.assertFalse(scope.valid)
        self.assertFalse(host.sources)
        self.assertCountEqual(host.removed, host.registrations)
        self.assertIsNone(scope._observer)
        self.assertIsNone(scope._source)
        self.assertIsNone(scope._callback)

    def test_exact_capture_subscriptions_and_no_ax_work_in_valid(self):
        scope, host, calls = self.make_scope(expected_element=Ref("field"),
                                              expected_window=Ref("window"))
        self.assertTrue(scope.start())
        self.assertTrue(scope.start())
        self.assertEqual(len(host.registrations), 4)
        self.assertEqual({name for _, name in host.registrations},
                         {FOCUSED_ELEMENT, FOCUSED_WINDOW, DEACTIVATED, MENU_OPENED})
        reads = list(host.reads)
        for _ in range(100):
            self.assertTrue(scope.valid)
        self.assertEqual(host.reads, reads)
        self.assertNotIn(threading.get_ident(), host.native_threads)
        self.assertEqual(len(host.native_threads), 1)
        self.assertFalse(calls)
        scope.stop()
        self.assert_closed(scope, host)
        self.assertFalse(scope.start())  # one candidate, never revived

    def test_expected_element_and_window_use_value_identity_and_refuse_mismatch(self):
        for expected in ({"expected_element": Ref("different")},
                         {"expected_window": Ref("different")}):
            scope, host, calls = self.make_scope(**expected)
            self.assertFalse(scope.start())
            self.assert_closed(scope, host)
            self.assertEqual(len(calls), 1)
            self.assertIsNone(host.callback)

    def test_internal_webview_window_requires_exact_bounded_ancestry(self):
        class WebHost(FakeHost):
            def __init__(self):
                super().__init__()
                self.containing_window = None
                self.web = Ref('web')
                self.parents = {self.element: self.web, self.web: self.window}

            def read(self, element, attribute):
                if attribute == 'AXParent':
                    self.reads.append((element, attribute))
                    parent = self.parents.get(element)
                    if parent is None:
                        raise ValueError('focus_unavailable')
                    return parent
                if attribute == 'AXRole':
                    return ('AXWindow' if 'window' in element.key else
                            'AXTextArea' if element == self.element else 'AXGroup')
                return super().read(element, attribute)

        host = WebHost()
        scope, host, calls = self.make_scope(host, allow_window_ancestors=True,
                                           required_role='AXTextArea')
        self.assertTrue(scope.start())
        self.assertIn((host.element, 'AXParent'), host.reads)
        host.parents[host.web] = Ref('other-window')
        host.emit(FOCUSED_ELEMENT)
        self.assert_closed(scope, host)
        self.assertEqual(len(calls), 1)
        # The external path still requires its normal AXWindow proof.
        scope, host, _ = self.make_scope(WebHost())
        self.assertFalse(scope.start())
        self.assert_closed(scope, host)
        scope, host, _ = self.make_scope(WebHost(), allow_window_ancestors=True,
                                       required_role='AXTextField')
        self.assertFalse(scope.start())
        self.assert_closed(scope, host)
        for failure in ('cycle', 'foreign', 'wrong_window', 'too_deep'):
            host = WebHost()
            if failure == 'cycle':
                host.parents[host.web] = host.element
            elif failure == 'foreign':
                host.parents[host.element] = Ref('foreign', 202)
            elif failure == 'wrong_window':
                host.containing_window = Ref('other-window')
            else:
                chain = [host.element] + [Ref(f'group-{i}') for i in range(17)] + [host.window]
                host.parents = dict(zip(chain, chain[1:]))
            scope, host, _ = self.make_scope(host, allow_window_ancestors=True)
            self.assertFalse(scope.start(), failure)
            self.assert_closed(scope, host)

    def test_no_permission_no_frontmost_and_missing_focus_all_fail_closed(self):
        cases = (("permission", False), ("front", 202), ("element", None),
                 ("window", None), ("element", Ref("foreign", 202)),
                 ("containing_window", Ref("different-window")))
        for attribute, value in cases:
            host = FakeHost()
            setattr(host, attribute, value)
            scope, host, calls = self.make_scope(host)
            self.assertFalse(scope.start(), attribute)
            self.assert_closed(scope, host)
            self.assertEqual(len(calls), 1, attribute)
            self.assertIsNone(host.callback)

    def test_all_required_observation_failures_refuse_and_unwind_partial_setup(self):
        for failure in ("observer", "source", "add_source", FOCUSED_ELEMENT,
                        FOCUSED_WINDOW, DEACTIVATED, MENU_OPENED):
            host = FakeHost()
            host.fail = failure
            scope, host, calls = self.make_scope(host)
            self.assertFalse(scope.start(), failure)
            self.assert_closed(scope, host)
            self.assertEqual(len(calls), 1)

    def test_terminal_and_unknown_bundle_require_window_title_observation_without_read(self):
        for bundle in ("com.mitchellh.ghostty", "com.apple.Terminal", None):
            host = FakeHost()
            host.bundle = bundle
            scope, host, calls = self.make_scope(host)
            self.assertTrue(scope.start())
            self.assertIn((host.window, TITLE_CHANGED), host.registrations)
            self.assertNotIn("AXTitle", [attr for _, attr in host.reads])
            host.emit(TITLE_CHANGED, host.window)
            self.assert_closed(scope, host)
            self.assertEqual(len(calls), 1)
            self.assertEqual(scope.reason, "focus_window_title_changed")

    def test_native_menu_retires_lease_even_when_editor_focus_is_unchanged(self):
        scope, host, calls = self.make_scope()
        self.assertTrue(scope.start())
        host.emit(MENU_OPENED, Ref('menu'))
        self.assert_closed(scope, host)
        self.assertEqual(scope.reason, 'focus_menu_opened')
        self.assertEqual(len(calls), 1)

    def test_unobservable_terminal_title_does_not_fall_back_to_pid(self):
        host = FakeHost()
        host.bundle = "com.mitchellh.ghostty"
        host.fail = TITLE_CHANGED
        scope, host, calls = self.make_scope(host)
        self.assertFalse(scope.start())
        self.assert_closed(scope, host)
        self.assertEqual(len(calls), 1)

    def test_same_target_notifications_remain_valid(self):
        scope, host, calls = self.make_scope()
        self.assertTrue(scope.start())
        for name, element in ((FOCUSED_ELEMENT, Ref("field")),
                              (FOCUSED_WINDOW, Ref("window")),
                              (FOCUSED_ELEMENT, Ref("app"))):
            host.emit(name, element)
            self.assertTrue(host.delivered.wait(1))
            self.assertTrue(scope.valid)
        self.assertFalse(calls)

    def test_different_field_in_same_window_invalidates_once(self):
        scope, host, calls = self.make_scope()
        self.assertTrue(scope.start())
        host.element = Ref("another-field")
        host.emit(FOCUSED_ELEMENT, host.app)
        self.assert_closed(scope, host)
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0], threading.get_ident())
        # A previously retained/queued native callback cannot invalidate again.
        host.callback(host.observer_ref, host.app, FOCUSED_ELEMENT, None)
        self.assertEqual(len(calls), 1)

    def test_different_window_in_same_pid_invalidates(self):
        scope, host, calls = self.make_scope()
        self.assertTrue(scope.start())
        host.window = host.containing_window = Ref("another-window")
        host.emit(FOCUSED_WINDOW, host.app)
        self.assert_closed(scope, host)
        self.assertEqual(len(calls), 1)

    def test_queued_away_and_back_target_is_not_mistaken_for_unchanged_focus(self):
        for name, changed in ((FOCUSED_ELEMENT, Ref("transient-field")),
                              (FOCUSED_WINDOW, Ref("transient-window"))):
            scope, host, calls = self.make_scope()
            self.assertTrue(scope.start())
            host.emit(name, changed)  # current focus has already returned
            self.assert_closed(scope, host)
            self.assertEqual(len(calls), 1)

    def test_app_deactivation_revokes_even_if_it_has_already_reactivated(self):
        scope, host, calls = self.make_scope()
        self.assertTrue(scope.start())
        host.emit(DEACTIVATED)
        self.assert_closed(scope, host)
        self.assertEqual(scope.reason, "focus_app_changed")
        self.assertEqual(len(calls), 1)

    def test_failed_focus_read_or_unexpected_observer_event_revokes(self):
        for failure in ("read", "observer", "unknown"):
            scope, host, calls = self.make_scope()
            self.assertTrue(scope.start())
            if failure == "read":
                host.fail = "AXFocusedUIElement"
                host.emit(FOCUSED_ELEMENT)
            elif failure == "observer":
                host.emit(FOCUSED_ELEMENT, observer=Ref("different-observer"))
            else:
                host.emit("unexpected-notification")
            self.assert_closed(scope, host)
            self.assertEqual(len(calls), 1)

    def test_focus_change_during_subscription_never_admits_enter(self):
        host = FakeHost()
        def change_focus(name):
            if name == FOCUSED_WINDOW:
                host.element = Ref("changed-during-start")
        host.on_subscribe = change_focus
        scope, host, calls = self.make_scope(host)
        self.assertFalse(scope.start())
        self.assert_closed(scope, host)
        self.assertEqual(scope.reason, "focus_changed_during_start")
        self.assertEqual(len(calls), 1)

    def test_stop_is_silent_idempotent_and_late_callback_is_ignored(self):
        scope, host, calls = self.make_scope()
        self.assertTrue(scope.start())
        callback = host.callback
        scope.stop()
        scope.stop()
        self.assert_closed(scope, host)
        callback(host.observer_ref, Ref("another-field"), FOCUSED_ELEMENT, None)
        self.assertFalse(calls)

    def test_stop_before_start_does_not_allocate_or_notify(self):
        scope, host, calls = self.make_scope()
        scope.stop()
        self.assertFalse(scope.start())
        self.assertFalse(host.native_threads)
        self.assertFalse(calls)

    def test_stop_during_startup_cannot_publish_a_valid_scope(self):
        host = FakeHost()
        host.read_gate = threading.Event()
        scope, host, calls = self.make_scope(host)
        result = []
        starter = threading.Thread(target=lambda: result.append(scope.start()))
        starter.start()
        stopper = threading.Thread(target=scope.stop)
        stopper.start()
        host.read_gate.set()
        starter.join(2)
        stopper.join(2)
        self.assertEqual(result, [False])
        self.assert_closed(scope, host)
        self.assertFalse(calls)

    def test_startup_timeout_revokes_before_a_late_capture_can_publish(self):
        host = FakeHost()
        host.read_gate = threading.Event()
        scope, host, calls = self.make_scope(host)
        try:
            self.assertFalse(scope.start())
            self.assertEqual(scope.reason, "focus_startup_timeout")
            self.assertEqual(calls, [threading.get_ident()])
        finally:
            host.read_gate.set()
        self.assert_closed(scope, host)
        self.assertEqual(len(calls), 1)

    def test_invalidation_callback_can_stop_or_raise_without_leaking_source(self):
        for action in ("stop", "raise"):
            holder = []
            calls = []
            def callback():
                calls.append(True)
                if action == "stop":
                    holder[0].stop()
                else:
                    raise RuntimeError("synthetic client failure")
            scope, host, _ = self.make_scope(callback=callback)
            holder.append(scope)
            self.assertTrue(scope.start())
            host.emit(DEACTIVATED)
            self.assert_closed(scope, host)
            self.assertEqual(calls, [True])

    def test_runloop_loss_is_an_invalidation_not_a_valid_pid_fallback(self):
        scope, host, calls = self.make_scope()
        self.assertTrue(scope.start())
        host.events.put("finished")
        self.assert_closed(scope, host)
        self.assertEqual(scope.reason, "focus_observer_stopped")
        self.assertEqual(len(calls), 1)

    def test_cleanup_continues_when_a_removal_raises(self):
        for failure in ("remove_notification", "remove_source"):
            scope, host, calls = self.make_scope()
            self.assertTrue(scope.start())
            host.fail = failure
            scope.stop()
            self.assert_closed(scope, host)
            self.assertFalse(calls)

    def test_invalid_arguments_are_rejected(self):
        for pid in (None, True, 0, -1, "101"):
            with self.assertRaises(ValueError):
                FocusScope(pid, lambda: None)
        with self.assertRaises(ValueError):
            FocusScope(101, None)


@unittest.skipUnless(sys.platform == "darwin", "macOS native source smoke")
class NativeSourceSmoke(unittest.TestCase):
    def test_native_observer_source_attaches_and_detaches_for_this_process_only(self):
        from localflow.v2.transforms.focus_scope import _NativeHost
        host = _NativeHost()
        observer = source = loop = None
        class Receiver:
            def receive(self, observer, element, notification, refcon):
                pass
        callback = Receiver().receive
        try:
            own_app = host.application(os.getpid())
            self.assertEqual(host.pid_of(own_app), os.getpid())
            self.assertTrue(host.same(own_app, host.application(os.getpid())))
            observer = host.observer(os.getpid(), callback)
            source = host.source(observer)
            loop = host.current_loop()
            host.add_source(loop, source)
            self.assertTrue(host.Q.CFRunLoopContainsSource(loop, source,
                                                         host.Q.kCFRunLoopDefaultMode))
            host.remove_source(loop, source)
            self.assertFalse(host.Q.CFRunLoopContainsSource(loop, source,
                                                          host.Q.kCFRunLoopDefaultMode))
            self.assertFalse(host.Q.CFRunLoopSourceIsValid(source))
            source = None
        finally:
            if source is not None and loop is not None:
                host.remove_source(loop, source)
            observer = source = callback = None
            host.close()

    def test_native_scope_passively_establishes_or_refuses_current_focus(self):
        from localflow.v2.transforms.focus_scope import _NativeHost
        host = _NativeHost()
        try:
            if not host.trusted():
                self.skipTest("native Accessibility unavailable; no permission prompt requested")
            try:
                pid = host.frontmost_pid()
            except ValueError as error:
                self.skipTest("native focused-app reference unavailable: " + str(error))
        finally:
            host.close()
        calls = []
        scope = FocusScope(pid, lambda: calls.append(True))
        try:
            established = scope.start()
            if not established:
                # Capability refusals are supported. Bridge/runtime errors are
                # failures, rather than being hidden as environment exclusions.
                self.assertIn(scope.reason, {
                    "focus_unavailable", "focus_window_changed", "focus_owner_changed",
                    "focus_changed_during_start", "focus_notification_unavailable",
                    "observer_unavailable", "observer_source_unavailable",
                    "focus_app_changed", "focus_target_changed", "focus_window_title_changed",
                })
                self.assertEqual(calls, [True])
                self.skipTest("native focus guard refused current target: " + scope.reason)
            self.assertTrue(scope.valid)
        finally:
            scope.stop()
        self.assertFalse(scope.valid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
