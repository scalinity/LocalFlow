#!/usr/bin/env python3
"""Opt-in native transform qualifier. Without --run this prints a plan only.

Only a fresh window made by an exact enabled File menu item can be claimed.
Only its already-focused, empty, settable text field can receive synthetic data.
A separate tagged-event barrier prevents leaked test Returns reaching a chat.
This is not the instrumented target's Return counter and is reported separately.
No providers, shell automation, draft recovery, or app quitting. Web selections
use the production guarded paste path; only owned synthetic fixtures are cleared.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Target:
    path: str
    bundle: str
    menu: tuple[str, str]
    empty_values: tuple[str, ...] = ("",)
    terminal_newline: bool = False


TARGETS = {
    # Observed 26.1016.51333 exposes its visible empty placeholder as AXValue
    # and counts its newline. This admission is for proven fresh test windows.
    "chatgpt": Target("/Applications/ChatGPT.app", "com.openai.codex", ("File", "New Window"), ("", "Ask ChatGPT\n"), True),
    "textedit": Target("/System/Applications/TextEdit.app", "com.apple.TextEdit", ("File", "New")),
    "claude": Target("/Applications/Claude.app", "com.anthropic.claudefordesktop", ("File", "New Session in New Window"), ("", "\n")),
}
RETURN_KEYS = frozenset((36, 76))


class Blocked(RuntimeError):
    """A missing ownership/capability proof; never permission to guess a control."""


class Failed(RuntimeError):
    """Observed incorrect behavior after the required capabilities were established."""


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def verify(condition, reason):
    if not condition:
        raise Failed(reason)


def mark_blocked(report):
    if report["status"] != "FAIL":
        report["status"] = "BLOCKED"


def contains(refs, wanted, same):
    return any(same(ref, wanted) for ref in refs)


def unique_new_window(before, after, same):
    for refs in (before, after):
        require(not any(same(a, b) for i, a in enumerate(refs) for b in refs[i + 1:]),
                "ambiguous_window_references")
    require(all(contains(after, ref, same) for ref in before), "existing_window_disappeared")
    added = [ref for ref in after if not contains(before, ref, same)]
    require(len(added) == 1, "new_window_not_unique")
    return added[0]


def exact_menu_item(host, app, path):
    """Only File -> one AXMenu -> exact leaf. No fuzzy/global control search."""
    bar = host.attribute(app, "AXMenuBar")
    require(bar is not None, "menu_bar_unavailable")
    parents = [ref for ref in host.children(bar)
               if host.attribute(ref, "AXRole") == "AXMenuBarItem"
               and host.attribute(ref, "AXTitle") == path[0]]
    require(len(parents) == 1, "file_menu_not_unique")
    menus = [ref for ref in host.children(parents[0])
             if host.attribute(ref, "AXRole") == "AXMenu"]
    require(len(menus) == 1, "file_menu_unavailable")
    items = [ref for ref in host.children(menus[0])
             if host.attribute(ref, "AXRole") == "AXMenuItem"
             and host.attribute(ref, "AXTitle") == path[1]]
    require(len(items) == 1, "new_window_menu_not_unique")
    item = items[0]
    enabled = host.attribute(item, "AXEnabled")
    require(type(enabled) in (bool, int) and enabled == 1, "new_window_menu_disabled")
    require("AXPress" in host.actions(item), "new_window_menu_not_pressable")
    return item


@dataclass
class OwnedField:
    pid: int
    window: object
    element: object
    before: tuple
    after: tuple
    synthetic_values: frozenset[str]
    known_text: str = ""
    empty_values: tuple[str, ...] = ("",)
    terminal_newline: bool = False

    def check(self, host):
        require(host.front_pid() == self.pid, "foreground_changed")
        live = host.windows(self.pid)
        require(len(live) == len(self.after) and
                all(contains(live, ref, host.same) for ref in self.after), "window_set_changed")
        require(host.same(host.focused_window(self.pid), self.window), "focused_window_changed")
        require(host.same(host.focused_element_for(self.pid), self.element), "focused_field_changed")
        require(host.element_pid(self.element) == self.pid and
                host.element_pid(self.window) == self.pid, "foreign_owner")
        require(host.same(host.attribute(self.element, "AXWindow"), self.window), "field_window_changed")

    def read(self, host):
        self.check(host)
        value = host.attribute(self.element, "AXValue")
        require(isinstance(value, str), "composer_unreadable")
        if value in self.empty_values:
            return ""
        return value[:-1] if self.terminal_newline and value.endswith("\n") else value

    def set_synthetic(self, host, text):
        require(text in self.synthetic_values, "non_synthetic_write_refused")
        require(self.read(host) == self.known_text, "owned_text_changed")
        require(host.is_settable(self.element, "AXValue"), "composer_value_not_settable")
        self.check(host)
        require(host.set_attribute(self.element, "AXValue", text), "seed_write_refused")
        if text and not self.terminal_newline:
            # Some web editors expose a paragraph separator after the exact
            # synthetic seed. Detect only this observed presentation change.
            host.pump(.1) if hasattr(host, 'pump') else None
            if self.read(host) == text + "\n":
                self.terminal_newline = True
        if hasattr(host, "wait"):
            host.wait(lambda: self.read(host) == text, 2, "seed_readback_mismatch")
        else:
            require(self.read(host) == text, "seed_readback_mismatch")
        self.known_text = text


def claim_empty_field(host, pid, before, after, synthetic_values, empty_values=("",), terminal_newline=False):
    window = unique_new_window(before, after, host.same)
    require(host.front_pid() == pid and host.same(host.focused_window(pid), window),
            "new_window_not_focused")
    element = host.focused_element_for(pid)
    require(element is not None and host.element_pid(element) == pid and
            host.element_pid(window) == pid, "new_field_owner_unavailable")
    require(host.same(host.attribute(element, "AXWindow"), window), "new_field_not_in_new_window")
    require(host.attribute(element, "AXRole") in ("AXTextField", "AXTextArea") and
            host.attribute(element, "AXSubrole") in (None, "AXStandardTextField"),
            "new_field_not_plain_text")
    require(host.is_settable(element, "AXValue"), "composer_value_not_settable")
    require(host.attribute(element, "AXDocument") in (None, ""), "new_field_has_existing_document")
    owned = OwnedField(pid, window, element, tuple(before), tuple(after),
                       frozenset(synthetic_values) | {""}, empty_values=empty_values,
                       terminal_newline=terminal_newline)
    require(owned.read(host) == "", "new_composer_not_empty")
    return owned


def check_key_guard(host, owned, listener, scope, barrier, token, code):
    require(code in RETURN_KEYS, "unexpected_test_key")
    owned.check(host)
    require(owned.read(host) == owned.known_text, "owned_text_changed")
    require(scope is not None and scope.valid, "focus_scope_invalid")
    require(host.same(scope.element, owned.element) and host.same(scope.window, owned.window),
            "scope_target_changed")
    require(listener.review_eligible and listener.review_scope is scope, "review_not_eligible")
    lease = listener.review.lease
    require(lease is not None and lease["token"] == token and lease["pid"] == owned.pid and
            lease["ready"] and lease["enabled"] and time.monotonic() < lease["expires"],
            "review_lease_inactive")
    require(barrier.healthy and barrier.enabled() and host.tap_enabled(listener.tap),
            "interception_unavailable")


def tag_should_block(issued_tags, actual_tag):
    return actual_tag in issued_tags


def tagged_settled(listener, barrier):
    return listener.qualifier_posted <= (listener.qualifier_consumed | barrier.blocked_events)


class NoKeyboard:
    def post_paste(self):
        raise Blocked("paste_fallback_forbidden")

    def post_copy(self):
        raise Blocked("copy_fallback_forbidden")


class GuardedPasteKeyboard:
    def __init__(self, host, owned, guarded):
        self.host, self.owned, self.guarded = host, owned, guarded
        self.posts = 0

    def post_paste(self):
        from localflow.v2.insertion.hosts import SystemKeyboard
        self.owned.check(self.host)
        require(self.guarded.effect_enabled and self.posts == 0
                and self.owned.read(self.host) == self.guarded.expected_text,
                "paste_effect_not_owned")
        self.posts += 1
        return SystemKeyboard().post_paste()


class GuardedInsertionHost:
    """Production AX host, bounded to the proven field, with one AX effect."""

    def __init__(self, base, owned, expected_text, replacement):
        self.base, self.owned = base, owned
        self.expected_text, self.replacement = expected_text, replacement
        self.effect_enabled = False
        self.write_attempts = 0

    def __getattr__(self, name):
        return getattr(self.base, name)

    def _owned(self, element):
        require(self.base.same(element, self.owned.element) or
                self.base.same(element, self.owned.window), "unowned_ax_read_refused")

    def focused_element_for(self, pid):
        self.owned.check(self.base)
        require(pid == self.owned.pid, "foreign_capture_pid")
        return self.owned.element

    def attribute(self, element, name):
        self._owned(element)
        return self.base.attribute(element, name)

    def string_for_range(self, element, start, length):
        self._owned(element)
        return self.base.string_for_range(element, start, length)

    def number_of_characters(self, element):
        self._owned(element)
        return self.base.number_of_characters(element)

    def focused_window_title(self, element):
        self._owned(element)
        self.owned.check(self.base)
        return self.base.attribute(self.owned.window, "AXTitle")

    def set_attribute(self, element, name, value):
        require(self.effect_enabled and self.write_attempts == 0 and
                self.base.same(element, self.owned.element) and name == "AXSelectedText" and
                value == self.replacement, "unexpected_insertion_effect")
        require(self.owned.read(self.base) == self.expected_text, "owned_text_changed")
        require(self.base.is_settable(element, name), "selected_text_not_settable")
        self.write_attempts += 1
        return self.base.set_attribute(element, name, value)


class NativeHost:
    """Created only under --run. All UI writes go through ownership guards."""

    def __init__(self, root):
        sys.path.insert(0, str(root))
        import ApplicationServices as AS
        import Quartz as Q
        from AppKit import NSApplication, NSWorkspace
        from localflow.v2.insertion.hosts import SystemInsertionHost
        self.AS, self.Q = AS, Q
        self.base = SystemInsertionHost(messaging_timeout=.1)
        require(AS.AXIsProcessTrusted(), "accessibility_permission_unavailable")
        require(Q.CGPreflightListenEventAccess(), "input_monitoring_unavailable")
        require(Q.CGPreflightPostEventAccess(), "post_event_permission_unavailable")
        self.workspace = NSWorkspace.sharedWorkspace()
        self.prior = self.workspace.frontmostApplication()
        application = NSApplication.sharedApplication()
        application.setActivationPolicy_(1)
        application.finishLaunching()
        self.pump(.1)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def same(self, a, b):
        return bool(a is not None and b is not None and self.Q.CFEqual(a, b))

    def front_pid(self):
        app = self.workspace.frontmostApplication()
        return int(app.processIdentifier()) if app else None

    def app_element(self, pid):
        app = self.AS.AXUIElementCreateApplication(pid)
        self.AS.AXUIElementSetMessagingTimeout(app, .1)
        return app

    def windows(self, pid):
        value = self.attribute(self.app_element(pid), "AXWindows")
        require(value is not None, "windows_unreadable")
        require(len(value) <= 128, "too_many_windows")
        return list(value)

    def focused_window(self, pid):
        return self.attribute(self.app_element(pid), "AXFocusedWindow")

    def children(self, element):
        children = self.attribute(element, "AXChildren")
        require(children is not None and len(children) <= 256, "menu_children_unavailable")
        return list(children)

    def actions(self, element):
        error, actions = self.AS.AXUIElementCopyActionNames(element, None)
        return list(actions or ()) if error == 0 else []

    def press(self, element, pid):
        require(self.front_pid() == pid and self.element_pid(element) == pid,
                "menu_owner_changed")
        require(self.attribute(element, "AXEnabled") in (True, 1) and
                "AXPress" in self.actions(element), "control_not_pressable")
        require(self.AS.AXUIElementPerformAction(element, "AXPress") == 0, "ax_press_failed")

    def tap_enabled(self, tap):
        return tap is not None and bool(self.Q.CGEventTapIsEnabled(tap))

    def focus_empty_editor(self, element, pid, window, empty_values, point=None):
        if element is None:
            # Parent-supplied point from an inspected native screenshot. A
            # click only establishes focus; empty-field proof still precedes
            # every text write. No keyboard action is sent here.
            require(point is not None and self.front_pid() == pid
                    and self.same(self.focused_window(pid), window), "fresh_click_owner_changed")
            position, size = self.attribute(window, "AXPosition"), self.attribute(window, "AXSize")
            ok, origin = self.AS.AXValueGetValue(position, self.AS.kAXValueCGPointType, None)
            ok_size, dimensions = self.AS.AXValueGetValue(size, self.AS.kAXValueCGSizeType, None)
            require(ok and ok_size and origin.x < point[0] < origin.x + dimensions.width
                    and origin.y < point[1] < origin.y + dimensions.height, "fresh_click_outside_window")
        else:
            require(self.front_pid() == pid and self.same(self.focused_window(pid), window)
                and self.same(self.attribute(element, "AXWindow"), window)
                and self.element_pid(element) == pid
                and self.attribute(element, "AXValue") in empty_values,
                "empty_editor_focus_guard_changed")
            position, size = self.attribute(element, "AXPosition"), self.attribute(element, "AXSize")
            require(position is not None and size is not None, "editor_bounds_unavailable")
            ok, origin = self.AS.AXValueGetValue(position, self.AS.kAXValueCGPointType, None)
            ok_size, dimensions = self.AS.AXValueGetValue(size, self.AS.kAXValueCGSizeType, None)
            require(ok and ok_size and dimensions.width > 20 and dimensions.height > 10,
                "editor_bounds_invalid")
            point = (origin.x + min(50, dimensions.width / 3), origin.y + dimensions.height / 2)
        for kind in (self.Q.kCGEventLeftMouseDown, self.Q.kCGEventLeftMouseUp):
            require(self.front_pid() == pid and self.same(self.focused_window(pid), window)
                    and (element is None or self.attribute(element, "AXValue") in empty_values),
                    "empty_editor_focus_guard_changed")
            event = self.Q.CGEventCreateMouseEvent(None, kind, point, self.Q.kCGMouseButtonLeft)
            require(event is not None, "focus_event_unavailable")
            self.Q.CGEventPost(self.Q.kCGHIDEventTap, event)

    def clear_owned_editor(self, owned):
        value = owned.read(self)
        require(value in owned.synthetic_values, "cleanup_refused_changed_text")
        def key(code, flags=0):
            owned.check(self)
            for down in (True, False):
                event = self.Q.CGEventCreateKeyboardEvent(None, code, down)
                self.Q.CGEventSetFlags(event, flags)
                self.Q.CGEventPost(self.Q.kCGHIDEventTap, event)
        key(0, self.Q.kCGEventFlagMaskCommand)  # native Select All
        self.wait(lambda: self.attribute(owned.element, "AXSelectedText") in
                  (value, value + "\n"), 2, "cleanup_selection_unverified")
        require(owned.read(self) == value, "cleanup_refused_changed_text")
        key(51)  # delete only the independently rechecked synthetic selection
        self.wait(lambda: owned.read(self) == "", 2, "cleanup_clear_unverified")
        owned.known_text = ""

    def pump(self, seconds=.05):
        from Foundation import NSDate, NSRunLoop
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))

    def wait(self, predicate, timeout, reason):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            self.pump()
        raise Blocked(reason)

    def activate(self, spec):
        from AppKit import NSRunningApplication, NSWorkspaceOpenConfiguration
        from Foundation import NSBundle, NSURL
        bundle = NSBundle.bundleWithPath_(spec.path)
        require(bundle is not None and str(bundle.bundleIdentifier()) == spec.bundle,
                "installed_bundle_identity_mismatch")
        expected_executable = str(bundle.executablePath())
        apps = [app for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_(spec.bundle)
                if app.executableURL() is not None
                and str(app.executableURL().path()) == expected_executable]
        require(len(apps) <= 1, "multiple_target_processes")
        if not apps:
            answer = []
            config = NSWorkspaceOpenConfiguration.configuration()
            config.setActivates_(False)
            # Claude's browser helper can register the GUI bundle ID. It is
            # not a running GUI instance and cannot receive composer input.
            config.setCreatesNewApplicationInstance_(True)
            self.workspace.openApplicationAtURL_configuration_completionHandler_(
                NSURL.fileURLWithPath_(spec.path), config, lambda app, error: answer.append((app, error)))
            self.wait(lambda: bool(answer), 15, "launch_timeout")
            app, error = answer[0]
            require(app is not None and error is None, "launch_failed")
        else:
            app = apps[0]
        require(str(app.bundleIdentifier()) == spec.bundle, "running_bundle_identity_mismatch")
        require(app.executableURL() is not None and str(app.executableURL().path()) == expected_executable,
                "running_executable_identity_mismatch")
        self.wait(lambda: app.isFinishedLaunching(), 15, "application_launch_not_finished")
        require(app.activateWithOptions_(2), "activation_refused")
        pid = int(app.processIdentifier())
        self.wait(lambda: self.front_pid() == pid, 5, "activation_timeout")
        self.pump(.5)
        return app, pid, str(bundle.objectForInfoDictionaryKey_("CFBundleShortVersionString"))

    def restore(self, target_pid):
        if self.prior is None or self.prior.isTerminated():
            return "prior_application_unavailable"
        if self.front_pid() not in (target_pid, os.getpid()):
            return "skipped_after_unrelated_focus_change"
        if not self.prior.activateWithOptions_(2):
            return "restore_refused"
        try:
            self.wait(lambda: self.front_pid() == int(self.prior.processIdentifier()),
                      3, "restore_timeout")
        except Blocked:
            return "restore_timeout"
        return "restored"


class TaggedBarrier:
    """Independent tail tap: no tagged Return may reach the target on failure."""

    def __init__(self, host):
        self.host = host
        # Reserve low bits for unique edges; zero is ordinary untagged input.
        self.tag = ((uuid.uuid4().int & ((1 << 47) - 1)) or 1) << 16
        self.intercepted = 0
        self.issued = set()
        self.blocked_events = set()
        self.healthy = False
        self.tap = self.source = None
        self.callback = self._event

    def _event(self, proxy, kind, event, refcon):
        Q = self.host.Q
        if kind in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            self.healthy = False
            # No further keys are admitted after this. Keep the owned barrier
            # available to drain any already-posted test events safely.
            Q.CGEventTapEnable(self.tap, True)
            return event
        tag = Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUserData)
        if tag_should_block(self.issued, tag):
            self.intercepted += 1
            self.blocked_events.add(tag)
            return None
        return event

    def start(self):
        Q = self.host.Q
        mask = Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
        self.tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGTailAppendEventTap,
                                    Q.kCGEventTapOptionDefault, mask, self.callback, None)
        require(self.tap is not None, "safety_tap_unavailable")
        self.source = Q.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        require(self.source is not None, "safety_source_unavailable")
        Q.CFRunLoopAddSource(Q.CFRunLoopGetMain(), self.source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self.tap, True)
        self.healthy = self.enabled()
        require(self.healthy, "safety_tap_disabled")

    def enabled(self):
        return self.host.tap_enabled(self.tap)

    def issue_tag(self):
        require(len(self.issued) < 65535, "test_event_tag_budget_exhausted")
        tag = self.tag + len(self.issued) + 1
        self.issued.add(tag)
        return tag

    def stop(self):
        Q = self.host.Q
        self.healthy = False
        if self.tap is not None:
            Q.CGEventTapEnable(self.tap, False)
        if self.source is not None:
            Q.CFRunLoopRemoveSource(Q.CFRunLoopGetMain(), self.source, Q.kCFRunLoopCommonModes)
        if self.tap is not None:
            Q.CFMachPortInvalidate(self.tap)
        self.tap = self.source = None


def post_guarded_burst(host, owned, listener, scope, barrier, token, code):
    """No run-loop pumping between edges: the same live lease guards all three."""
    Q = host.Q
    pending_release = False
    def post(down, repeat=False, guard=True):
        event = Q.CGEventCreateKeyboardEvent(None, code, down)
        require(event is not None, "test_event_unavailable")
        Q.CGEventSetFlags(event, 0)
        tag = barrier.issue_tag()
        Q.CGEventSetIntegerValueField(event, Q.kCGEventSourceUserData, tag)
        Q.CGEventSetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat, int(repeat))
        if guard:
            check_key_guard(host, owned, listener, scope, barrier, token, code)
        listener.qualifier_posted.add(tag)
        Q.CGEventPost(Q.kCGHIDEventTap, event)
    try:
        for down, repeat in ((True, False), (True, True), (False, False)):
            check_key_guard(host, owned, listener, scope, barrier, token, code)
            post(down, repeat)
            pending_release = down
    finally:
        if pending_release:
            # A focus/lease change forbids another down, but the admitted
            # press still needs its tagged release. The tail barrier remains
            # live even when the original Apply lease has been revoked.
            require(barrier.enabled(), "release_barrier_unavailable")
            post(False, guard=False)


class ReferenceLabels:
    def __init__(self, same):
        self.refs, self.same = [], same

    def label(self, ref):
        for i, existing in enumerate(self.refs):
            if self.same(existing, ref):
                return f"window-{i + 1}"
        self.refs.append(ref)
        return f"window-{len(self.refs)}"


def evidence_path(root, output, target):
    path = Path(output) if output else root / "build/native-qualification" / f"{target}-{uuid.uuid4().hex}.json"
    require(path.is_absolute() and path.resolve() == path and path.suffix == ".json", "unsafe_evidence_path")
    require(path.is_relative_to(root / "build"), "evidence_must_stay_in_ignored_build")
    require(not path.exists() and not path.is_symlink(), "evidence_already_exists")
    return path


class PreviewCoordinator:
    def __init__(self, host, owned, listener, scope, barrier, service, guarded, token):
        self.host, self.owned, self.listener = host, owned, listener
        self.scope, self.barrier, self.service, self.guarded = scope, barrier, service, guarded
        self.token = token
        self.accept_callbacks = self.accepted = 0
        self.outcome = self.blocked = None
        self.panel = self.result = self.capture = None

    def review_action(self, action, token):
        if token != self.token:
            self.blocked = "wrong_candidate_callback"
        elif action == "accept":
            self.accept_callbacks += 1
            self.tfAcceptTransform(self.result, self.capture, None)
        else:
            self.blocked = "review_" + action

    def tfAcceptTransform(self, result, capture, candidate_id):
        from PyObjCTools import AppHelper
        try:
            check_key_guard(self.host, self.owned, self.listener, self.scope,
                            self.barrier, self.token, 36)
            require(result is self.result and capture is self.capture, "preview_candidate_changed")
            require(self.listener.review.claim(self.token), "duplicate_accept")
            self.accepted += 1
            self.guarded.effect_enabled = True
            self.panel.panel.orderOut_(None)
            self.service.submit(result.output, {
                "operation_id": self.token, "job_id": self.token, "attempt": 1,
                "context_snapshot": capture["snapshot"], "strict_replacement": True,
                "selection_acquisition": capture.get("acquisition"), "observation_consent": False,
            }, lambda outcome: AppHelper.callAfter(self.done, outcome))
        except Blocked as error:
            self.blocked = str(error)

    def done(self, outcome):
        self.guarded.effect_enabled = False
        self.outcome = outcome

    def tfDismissReview(self):
        self.listener.review.disarm()
        self.blocked = "preview_dismissed"

    def stop(self):
        self.guarded.effect_enabled = False
        self.listener.review.disarm()
        self.scope.stop()
        self.listener.review_scope = None
        if self.panel is not None:
            self.panel.panel.orderOut_(None)


def cleanup_owned(host, owned, *, document_app=False):
    """Never discard changed/user text or touch a save/discard dialog."""
    value = owned.read(host)
    require(value in owned.synthetic_values, "cleanup_refused_changed_text")
    owned.known_text = value
    if owned.terminal_newline:
        host.clear_owned_editor(owned)
    else:
        owned.set_synthetic(host, "")
    # Editing an unsaved TextEdit document may mark it dirty even after clear.
    # Do not create a save sheet or guess a destructive dismissal button.
    edited = host.attribute(owned.window, "AXEdited")
    require(edited not in (True, 1) and (not document_app or edited in (False, 0)),
            "owned_empty_window_save_risk")
    close = host.attribute(owned.window, "AXCloseButton")
    require(close is not None and host.same(host.attribute(close, "AXWindow"), owned.window),
            "owned_close_button_unavailable")
    require(owned.read(host) == "", "cleanup_text_changed")
    host.press(close, owned.pid)
    host.wait(lambda: not contains(host.windows(owned.pid), owned.window, host.same),
              3, "owned_window_did_not_close")
    return "cleared_and_closed_owned_window"


def run_native(root, target_name, focus_point=None):
    spec = TARGETS[target_name]
    report = {"target": target_name, "bundle": spec.bundle, "status": "BLOCKED", "cases": [],
              "target_return_event_counter": None, "target_submission_counter": None,
              "counter_limitation": "Real apps expose no test event counter; instrumented-target proof is separate.",
              "recorded_at_eastern": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p %Z")}
    host = owned = listener = barrier = store = service = coordinator = scope = None
    capture_host = None
    store_path = None
    pid = None
    fresh_window = None
    try:
        host = NativeHost(root)
        app, pid, version = host.activate(spec)
        report["version"] = version
        labels = ReferenceLabels(host.same)
        before = tuple(host.windows(pid))
        report["windows_before"] = [labels.label(ref) for ref in before]
        menu = exact_menu_item(host, host.app_element(pid), spec.menu)
        require(host.front_pid() == pid, "foreground_changed")
        host.press(menu, pid)
        deadline = time.monotonic() + 5
        after = before
        while time.monotonic() < deadline:
            after = tuple(host.windows(pid))
            if len(after) != len(before):
                break
            host.pump()
        report["windows_after"] = [labels.label(ref) for ref in after]
        fresh_window = unique_new_window(before, after, host.same)
        host.base.prepare_text_capture(pid)
        # New Window can leave accessibility focus on the old window until
        # its empty composer is explicitly focused. Search only the proven
        # fresh window, and never focus a nonempty or ambiguous editor.
        require("AXRaise" in host.actions(fresh_window), "new_window_not_raiseable")
        require(host.AS.AXUIElementPerformAction(fresh_window, "AXRaise") == 0,
                "new_window_raise_failed")
        if focus_point:
            host.focus_empty_editor(None, pid, fresh_window, spec.empty_values, focus_point)
        focused_fresh = False
        def editor_ready():
            nonlocal focused_fresh
            require(host.front_pid() == pid, "foreground_changed")
            element = host.focused_element_for(pid)
            report["editor_readiness"] = {
                "focus_present": element is not None,
                "owner_matches": element is not None and host.element_pid(element) == pid,
                "role_allowed": host.attribute(element, "AXRole") in ("AXTextField", "AXTextArea") if element else False,
                "field_in_fresh_window": host.same(host.attribute(element, "AXWindow"), fresh_window) if element else False,
                "fresh_window_focused": host.same(host.focused_window(pid), fresh_window)}
            if (element is not None and host.element_pid(element) == pid
                    and host.same(host.attribute(element, "AXWindow"), fresh_window)
                    and host.attribute(element, "AXRole") in ("AXTextField", "AXTextArea")):
                return True
            if focused_fresh:
                return False
            queue, candidates, seen = [fresh_window], [], []
            while queue:
                node = queue.pop()
                if contains(seen, node, host.same):
                    continue
                seen.append(node)
                require(len(seen) <= 1024, "new_editor_tree_too_large")
                if (host.attribute(node, "AXRole") == "AXTextArea"
                        and host.attribute(node, "AXSubrole") in (None, "AXStandardTextField")
                        and host.same(host.attribute(node, "AXWindow"), fresh_window)
                        and host.is_settable(node, "AXValue")):
                    candidates.append(node)
                queue.extend(host.attribute(node, "AXChildren") or [])
            if len(candidates) == 1:
                value = host.attribute(candidates[0], "AXValue")
                report["fresh_editor"] = {"candidate_count": len(candidates),
                    "value_readable": isinstance(value, str),
                    "value_length": len(value) if isinstance(value, str) else None,
                    "number_of_characters": host.number_of_characters(candidates[0]),
                    "matches_placeholder": value is not None and value == host.attribute(candidates[0], "AXPlaceholderValue"),
                    "empty": value == ""}
                require(value in spec.empty_values, "new_composer_not_empty")
                require(host.front_pid() == pid, "foreground_changed")
                host.focus_empty_editor(candidates[0], pid, fresh_window, spec.empty_values)
                focused_fresh = True
            return False
        host.wait(editor_ready, 8, "new_editor_not_ready")
        stable = tuple(host.windows(pid))
        require(len(stable) == len(after) and all(contains(stable, r, host.same) for r in after),
                "new_window_not_stable")
        run_id = uuid.uuid4().hex[:12]
        prefix, source, suffix = f"LF qualifier {run_id} 🧪 | ", "draft about a paper kite", " | synthetic suffix é"
        replacement = "Revised draft about a paper kite."
        seed, expected = prefix + source + suffix, prefix + replacement + suffix
        owned = claim_empty_field(host, pid, before, after, {seed, expected}, spec.empty_values, spec.terminal_newline)
        from localflow.transform_hotkey import TransformHotkeyListener
        from localflow.v2.store import Store
        from localflow.v2.insertion.service import InsertionService
        from localflow.v2.insertion.hosts import SystemPasteboard
        from AppKit import NSPasteboard
        from localflow.v2.insertion.selection import capture_selection
        from localflow.v2.context.providers import utf16_len
        from localflow.v2.transforms.engine import TransformJob, TransformResult
        from localflow.v2.transforms.definitions import TransformDefinition
        from localflow.v2.transforms.focus_scope import FocusScope
        from localflow.v2.ui.transforms_panel import TransformPreviewPanel
        from PyObjCTools import AppHelper
        barrier = TaggedBarrier(host)
        barrier.start()

        class ProbeListener(TransformHotkeyListener):
            """Count the real production handler's decisions, not target events."""
            def __init__(self):
                super().__init__(lambda tid: None, lambda *a: None)
                self.qualifier_posted = set()
                self.qualifier_consumed = set()

            def _event(self, proxy, kind, event, refcon):
                result = super()._event(proxy, kind, event, refcon)
                if kind in (host.Q.kCGEventKeyDown, host.Q.kCGEventKeyUp) and event is not None:
                    tag = host.Q.CGEventGetIntegerValueField(event, host.Q.kCGEventSourceUserData)
                    if tag in barrier.issued and result is None:
                        self.qualifier_consumed.add(tag)
                return result

        listener = ProbeListener()
        require(listener.start(), "production_event_tap_unavailable")
        require(listener.review_eligible, "input_method_not_eligible")
        scratch = root / "build/native-qualification"
        require(scratch.resolve() == scratch, "unsafe_scratch_directory")
        scratch.mkdir(parents=True, mode=0o700, exist_ok=True)
        store_path = Path(tempfile.mkdtemp(prefix="isolated-store-", dir=scratch))
        store = Store(store_path / "qualification.db", backup_dir=store_path / "backups")
        board = SystemPasteboard()
        if target_name == 'textedit':
            board._pb = NSPasteboard.pasteboardWithUniqueName()
        else:
            from localflow.v2.insertion.hosts import SUPPORTED_PASTEBOARD_TYPES
            require(set(board.types()) <= set(SUPPORTED_PASTEBOARD_TYPES),
                    'clipboard_contains_unrestorable_types')
        for code in (36, 76):
            case = {"key_code": code, "status": "BLOCKED", "phase": "setup"}
            report["cases"].append(case)
            board_before = {str(t): bytes(board.data_for_type(t)) for t in board.types()}
            owned.set_synthetic(host, seed)
            require(host.is_settable(owned.element, "AXSelectedTextRange") and
                    host.is_settable(owned.element, "AXSelectedText"), "selection_not_settable")
            owned.check(host)
            require(host.set_attribute(owned.element, "AXSelectedTextRange",
                                      (utf16_len(prefix), utf16_len(source))), "selection_setup_refused")
            host.pump(.2)
            from localflow.v2.insertion.validation import _as_range
            case["selected_range"] = _as_range(host.attribute(owned.element, "AXSelectedTextRange"))
            case["direct_selection_matches_source"] = host.attribute(owned.element, "AXSelectedText") == source
            case["range_selection_matches_source"] = host.string_for_range(
                owned.element, utf16_len(prefix), utf16_len(source)) == source
            capture_host = GuardedInsertionHost(host, owned, seed, replacement)
            capture, reason = capture_selection(capture_host, expected_pid=pid,
                expected_element=owned.element, expected_window=owned.window)
            case["capture_reason"] = reason
            require(capture is not None and reason is None and capture.get("can_replace"),
                    "capture_unavailable_or_not_replaceable")
            verify(capture["source"] == source, "capture_source_mismatch")
            verify(capture["range"] == (utf16_len(prefix), utf16_len(prefix + source)),
                   "capture_range_mismatch")
            token = "qualifier:" + uuid.uuid4().hex
            capture["operation_id"] = token
            job = TransformJob("qualifier:fixed", 1, "qualification-synthetic-v1", "polish", source,
                               source_kind="selection")
            result = TransformResult(job, replacement, "applied")
            definition = TransformDefinition("qualifier:fixed", "Native qualification", "polish")
            keyboard = GuardedPasteKeyboard(host, owned, capture_host) if target_name != 'textedit' else NoKeyboard()
            service = InsertionService(host=capture_host, pasteboard=board, keyboard=keyboard,
                store=store, emit=lambda *a, **k: None, observation_window_sec=0)
            scope = FocusScope(pid, lambda: AppHelper.callAfter(listener.review.disarm),
                               expected_element=owned.element, expected_window=owned.window)
            require(scope.start(), "focus_scope_unavailable")
            listener.review_scope = scope
            coordinator = PreviewCoordinator(host, owned, listener, scope, barrier,
                                             service, capture_host, token)
            coordinator.result, coordinator.capture = result, capture
            panel = TransformPreviewPanel.alloc().init_panel(coordinator)
            coordinator.panel = panel
            panel.show(result, capture, definition, None)
            panel.configure.setEnabled_(False)
            for action, button in panel._buttons.items():
                if action != "panelAccept:":
                    button.setEnabled_(False)
            listener.review_callback = coordinator.review_action
            listener.review.arm(token, pid, ready=True, enabled=True, ttl=30)
            owned.check(host)  # the production panel must remain non-activating
            before_intercepts = barrier.intercepted
            before_posted = set(listener.qualifier_posted)
            case["phase"] = "guarded_key_burst"
            post_guarded_burst(host, owned, listener, scope, barrier, token, code)
            host.wait(lambda: coordinator.outcome is not None or coordinator.blocked is not None or
                      barrier.intercepted != before_intercepts, 10, "acceptance_timeout")
            host.pump(.3)
            host.wait(lambda: tagged_settled(listener, barrier), 3, "test_events_not_drained")
            require(coordinator.blocked is None, coordinator.blocked or "review_failed")
            require(barrier.healthy, "safety_interception_lost")
            verify(barrier.intercepted == before_intercepts, "production_return_leaked_to_safety_tap")
            verify(coordinator.accept_callbacks == 1 and coordinator.accepted == 1,
                   "accept_not_exactly_once")
            posted = listener.qualifier_posted - before_posted
            verify(len(posted) == 3 and posted <= listener.qualifier_consumed,
                   "repeat_or_keyup_not_consumed")
            verify(not listener.review.consumed and not listener.review.physical,
                   "press_release_not_settled")
            host.wait(lambda: not service.pending, 5, "insertion_still_pending")
            actual = owned.read(host)
            outcome = coordinator.outcome
            case.update({"accept_callbacks": coordinator.accept_callbacks,
                "insertion_write_attempts": capture_host.write_attempts,
                "paste_events": getattr(keyboard, 'posts', 0),
                "clipboard_restored": board_before == {str(t): bytes(board.data_for_type(t)) for t in board.types()},
                "insertion": outcome.to_envelope_block(), "exact_readback": actual == expected,
                "prefix_suffix_preserved": actual.startswith(prefix) and actual.endswith(suffix),
                "safety_intercepts": barrier.intercepted - before_intercepts,
                "posted_key_events": len(posted), "production_consumed_events": len(posted),
                "repeat_and_keyup_consumed": True,
                "target_return_event_counter": None,
                "submission_observation": "synthetic result remained in the bound composer; no submission observed"})
            verify(actual == expected and outcome.state == "confirmed" and
                   capture_host.write_attempts + getattr(keyboard, 'posts', 0) == 1,
                   "replacement_not_verified_exactly_once")
            verify(case['clipboard_restored'], 'clipboard_not_restored')
            owned.known_text = expected
            case.update(status="PASS", phase="readback_verified")
            coordinator.stop()
            coordinator = None
        report["status"] = "PASS"
    except Failed as error:
        report["status"], report["reason"] = "FAIL", str(error)
        if report["cases"]:
            report["cases"][-1].update(status="FAIL", reason=str(error))
    except Blocked as error:
        report["reason"] = str(error)
        if host is not None:
            report["foreground_at_stop"] = host.frontmost()
        if report["cases"] and report["cases"][-1]["status"] != "PASS":
            report["cases"][-1]["reason"] = str(error)
    except Exception as error:
        report["reason"] = "qualifier_exception"
        report["exception_type"] = type(error).__name__
    finally:
        if coordinator is not None and report["cases"]:
            report["cases"][-1].update(accept_callbacks=coordinator.accept_callbacks,
                accepted_operations=coordinator.accepted,
                insertion_write_attempts=coordinator.guarded.write_attempts)
        if capture_host is not None:
            capture_host.effect_enabled = False
        for name, obj in (("coordinator", coordinator), ("focus_scope", scope)):
            if obj is not None:
                try:
                    obj.stop()
                except Exception as error:
                    report.setdefault("teardown_errors", []).append(name + ":" + type(error).__name__)
                    mark_blocked(report)
        # Drain tagged events before removing either interceptor, including a
        # partially posted gesture that failed a later focus/lease guard.
        if listener is not None and barrier is not None:
            try:
                host.wait(lambda: tagged_settled(listener, barrier), 3, "test_events_not_drained")
            except Blocked as error:
                report["event_drain"] = str(error)
                mark_blocked(report)
                print("BLOCKED: retaining Return interception until all posted test events drain.",
                      file=sys.stderr, flush=True)
                # Returning would remove the last tap while an issued Return
                # remains unaccounted. Keep this process and its native loop
                # alive; never turn a drain timeout into permission to leak it.
                while not tagged_settled(listener, barrier):
                    host.pump(.1)
            report["key_events"] = {"posted": len(listener.qualifier_posted),
                "production_consumed": len(listener.qualifier_consumed),
                "safety_blocked": len(barrier.blocked_events),
                "all_tagged_events_accounted_for": tagged_settled(listener, barrier)}
            try:
                listener.stop()
            except Exception as error:
                report.setdefault("teardown_errors", []).append("listener:" + type(error).__name__)
                mark_blocked(report)
        if barrier is not None:
            try:
                barrier.stop()
            except Exception as error:
                report.setdefault("teardown_errors", []).append("barrier:" + type(error).__name__)
                mark_blocked(report)
        idle = service is None or not service.pending
        if owned is not None and idle:
            try:
                report["cleanup"] = cleanup_owned(host, owned, document_app=target_name == "textedit")
            except Exception as error:
                report["cleanup"] = str(error) if isinstance(error, Blocked) else type(error).__name__
                mark_blocked(report)
        elif owned is not None:
            report["cleanup"] = "owned_window_retained_insertion_pending"
            mark_blocked(report)
        else:
            report["cleanup"] = ("new_window_unclaimed_left_untouched" if fresh_window is not None
                                  else "no_field_claimed_no_draft_touched")
        if host is not None and pid is not None and idle:
            try:
                report["prior_app_restore"] = host.restore(pid)
                if report["prior_app_restore"] != "restored":
                    mark_blocked(report)
            except Exception as error:
                report["prior_app_restore"] = type(error).__name__
                mark_blocked(report)
        if store is not None and idle:
            try:
                closed = store.close()
                report["isolated_store_drained"] = closed["drained"]
                if closed["drained"] and store_path is not None:
                    shutil.rmtree(store_path)
            except Exception as error:
                report["isolated_store_cleanup"] = type(error).__name__
                mark_blocked(report)
        if store_path is not None and store_path.exists():
            report["retained_isolated_store"] = str(store_path.relative_to(root))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run", action="store_true", help="enable native windows, preview, and guarded test keys")
    parser.add_argument("--focus-point", nargs=2, type=float,
                        help="textbox screen point inspected by the native parent; click before AX capture")
    args = parser.parse_args(argv)
    root = args.source_root.resolve()
    if not args.run:
        print(json.dumps({"status": "NOT RUN", "target": args.target,
                          "bundle": TARGETS[args.target].bundle,
                          "exact_menu": TARGETS[args.target].menu,
                          "instruction": "Add --run only in the authorized native parent process."}, indent=2))
        return 0
    try:
        require(sys.platform == "darwin", "macos_required")
        output = evidence_path(root, args.output, args.target)
        report = run_native(root, args.target, args.focus_point)
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print(json.dumps({"status": report["status"], "evidence": str(output),
                          "reason": report.get("reason"), "cleanup": report.get("cleanup")}, indent=2))
        return 0 if report["status"] == "PASS" else 1 if report["status"] == "FAIL" else 2
    except Blocked as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
