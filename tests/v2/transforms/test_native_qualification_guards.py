"""Offline guard/source checks. Never instantiate the native host or post keys."""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/v2/qualify_transform_apps.py"
spec = importlib.util.spec_from_file_location("native_qualification_under_test", SCRIPT)
qualifier = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = qualifier
spec.loader.exec_module(qualifier)


class FakeHost:
    def __init__(self):
        self.pid = self.front = 101
        self.live_windows = ["old-window", "new-window"]
        self.window = "new-window"
        self.element = "field"
        self.text = ""
        self.reads, self.writes, self.presses = [], [], []
        self.settable = {"AXValue", "AXSelectedText", "AXSelectedTextRange"}
        self.attrs = {
            ("field", "AXWindow"): "new-window", ("field", "AXRole"): "AXTextArea",
            ("field", "AXSubrole"): None, ("field", "AXDocument"): None,
            ("new-window", "AXEdited"): False, ("new-window", "AXCloseButton"): "close",
            ("close", "AXWindow"): "new-window", ("close", "AXEnabled"): True,
            ("app", "AXMenuBar"): "bar", ("file", "AXRole"): "AXMenuBarItem",
            ("file", "AXTitle"): "File", ("menu", "AXRole"): "AXMenu",
            ("new", "AXRole"): "AXMenuItem", ("new", "AXTitle"): "New Window",
            ("new", "AXEnabled"): True,
        }
        self.child_map = {"bar": ["file"], "file": ["menu"], "menu": ["new"]}
        self.action_map = {"new": ["AXPress"], "close": ["AXPress"]}
        self.taps_enabled = True

    def same(self, a, b):
        return a is not None and b is not None and a == b

    def front_pid(self):
        return self.front

    def windows(self, pid):
        return list(self.live_windows)

    def focused_window(self, pid):
        return self.window

    def focused_element_for(self, pid):
        return self.element

    def element_pid(self, element):
        return 202 if element == "foreign" else self.pid

    def attribute(self, element, name):
        self.reads.append((element, name))
        if name == "AXValue":
            if element != "field":
                raise AssertionError("attempted existing-draft read")
            return self.text
        return self.attrs.get((element, name))

    def is_settable(self, element, name):
        return element == "field" and name in self.settable

    def set_attribute(self, element, name, value):
        self.writes.append((element, name, value))
        if name in ("AXValue", "AXSelectedText"):
            self.text = value
        return True

    def children(self, element):
        return self.child_map.get(element, [])

    def actions(self, element):
        return self.action_map.get(element, [])

    def press(self, element, pid):
        self.presses.append(element)
        if element == "close":
            self.live_windows.remove("new-window")

    def wait(self, predicate, timeout, reason):
        qualifier.require(predicate(), reason)

    def tap_enabled(self, tap):
        return self.taps_enabled and tap is not None


class FakeQuartz:
    kCGEventSourceUserData = 1
    kCGKeyboardEventAutorepeat = 2
    kCGHIDEventTap = 3
    kCGEventKeyDown = 10
    kCGEventKeyUp = 11
    kCGEventTapDisabledByTimeout = 12
    kCGEventTapDisabledByUserInput = 13

    def __init__(self):
        self.posted = []
        self.after_post = None
        self.enables = []

    def CGEventCreateKeyboardEvent(self, source, code, down):
        return {"code": code, "down": down}

    def CGEventSetFlags(self, event, flags):
        event["flags"] = flags

    def CGEventSetIntegerValueField(self, event, key, value):
        event[key] = value

    def CGEventGetIntegerValueField(self, event, key):
        return event.get(key, 0)

    def CGEventPost(self, tap, event):
        self.posted.append(dict(event))
        if self.after_post is not None:
            self.after_post()

    def CGEventTapEnable(self, tap, enabled):
        self.enables.append((tap, enabled))


def claim(host):
    return qualifier.claim_empty_field(host, 101, ("old-window",),
        ("old-window", "new-window"), {"seed", "result"})


def key_fixture():
    host = FakeHost()
    owned = claim(host)
    owned.set_synthetic(host, "seed")
    scope = SimpleNamespace(valid=True, element="field", window="new-window")
    lease = {"token": "test", "pid": 101, "ready": True, "enabled": True,
             "expires": time.monotonic() + 30}
    listener = SimpleNamespace(review=SimpleNamespace(lease=lease), review_eligible=True,
        review_scope=scope, tap=object(), qualifier_posted=set(), qualifier_consumed=set())
    host.Q = FakeQuartz()
    barrier = qualifier.TaggedBarrier(host)
    barrier.healthy, barrier.tap = True, object()
    return host, owned, listener, scope, barrier


class OwnershipTests(unittest.TestCase):
    def test_exactly_one_added_window_and_all_previous_windows_must_survive(self):
        same = lambda a, b: a == b
        self.assertEqual(qualifier.unique_new_window(["old"], ["old", "new"], same), "new")
        for before, after in ((["old"], ["old"]), (["old"], ["new"]),
                              (["old"], ["old", "one", "two"]),
                              (["old"], ["old", "new", "new"])):
            with self.assertRaises(qualifier.Blocked):
                qualifier.unique_new_window(before, after, same)

    def test_existing_or_other_window_focus_refuses_before_content_read(self):
        for change in ("window", "element", "owner", "secure", "search", "role", "settable", "document"):
            host = FakeHost()
            if change == "window":
                host.window = "old-window"
            elif change == "element":
                host.attrs["field", "AXWindow"] = "old-window"
            elif change == "owner":
                host.element = "foreign"
            elif change == "secure":
                host.attrs["field", "AXSubrole"] = "AXSecureTextField"
            elif change == "search":
                host.attrs["field", "AXSubrole"] = "AXSearchTextField"
            elif change == "role":
                host.attrs["field", "AXRole"] = "AXButton"
            elif change == "settable":
                host.settable.clear()
            else:
                host.attrs["field", "AXDocument"] = "existing-document"
            with self.assertRaises(qualifier.Blocked, msg=change):
                claim(host)
            self.assertNotIn(("field", "AXValue"), host.reads, change)
            self.assertFalse(host.writes)

    def test_nonempty_fresh_composer_is_never_overwritten(self):
        host = FakeHost()
        host.text = "existing unsent draft"
        with self.assertRaisesRegex(qualifier.Blocked, "new_composer_not_empty"):
            claim(host)
        self.assertFalse(host.writes)
        self.assertEqual(host.text, "existing unsent draft")

    def test_seed_is_whitelisted_settable_and_read_back(self):
        host = FakeHost()
        owned = claim(host)
        owned.set_synthetic(host, "seed")
        self.assertEqual(host.text, "seed")
        with self.assertRaises(qualifier.Blocked):
            owned.set_synthetic(host, "arbitrary text")
        host.text = "manual correction"
        with self.assertRaises(qualifier.Blocked):
            owned.set_synthetic(host, "result")
        self.assertEqual(host.text, "manual correction")

    def test_menu_requires_one_exact_enabled_leaf_and_press_action(self):
        host = FakeHost()
        self.assertEqual(qualifier.exact_menu_item(host, "app", ("File", "New Window")), "new")
        for change in ("title", "disabled", "duplicate", "action"):
            host = FakeHost()
            if change == "title":
                host.attrs["new", "AXTitle"] = "New Temporary Chat"
            elif change == "disabled":
                host.attrs["new", "AXEnabled"] = False
            elif change == "duplicate":
                host.child_map["menu"].append("new")
            else:
                host.action_map["new"] = []
            with self.assertRaises(qualifier.Blocked):
                qualifier.exact_menu_item(host, "app", ("File", "New Window"))
            self.assertFalse(host.presses)


class KeyGuards(unittest.TestCase):
    def test_all_focus_lease_and_interception_failures_block_before_any_post(self):
        mutations = [lambda h, o, l, s, b: setattr(h, "front", 202),
            lambda h, o, l, s, b: setattr(h, "element", "different"),
            lambda h, o, l, s, b: setattr(h, "window", "old-window"),
            lambda h, o, l, s, b: h.live_windows.append("another"),
            lambda h, o, l, s, b: setattr(h, "text", "changed"),
            lambda h, o, l, s, b: setattr(s, "valid", False),
            lambda h, o, l, s, b: setattr(s, "element", "different"),
            lambda h, o, l, s, b: setattr(s, "window", "different"),
            lambda h, o, l, s, b: setattr(l, "review_eligible", False),
            lambda h, o, l, s, b: setattr(l, "review_scope", None),
            lambda h, o, l, s, b: l.review.lease.update(token="other"),
            lambda h, o, l, s, b: l.review.lease.update(pid=202),
            lambda h, o, l, s, b: l.review.lease.update(ready=False),
            lambda h, o, l, s, b: l.review.lease.update(enabled=False),
            lambda h, o, l, s, b: l.review.lease.update(expires=0),
            lambda h, o, l, s, b: setattr(l.review, "lease", None),
            lambda h, o, l, s, b: setattr(b, "healthy", False),
            lambda h, o, l, s, b: setattr(h, "taps_enabled", False)]
        for mutate in mutations:
            h, o, l, s, b = key_fixture()
            mutate(h, o, l, s, b)
            with self.assertRaises(qualifier.Blocked):
                qualifier.post_guarded_burst(h, o, l, s, b, "test", 36)
            self.assertFalse(h.Q.posted)

    def test_return_and_keypad_bursts_have_distinct_tags_and_exact_edges(self):
        for code in (36, 76):
            h, o, l, s, b = key_fixture()
            qualifier.post_guarded_burst(h, o, l, s, b, "test", code)
            self.assertEqual([e["code"] for e in h.Q.posted], [code] * 3)
            self.assertEqual([e["down"] for e in h.Q.posted], [True, True, False])
            self.assertEqual([e[2] for e in h.Q.posted], [0, 1, 0])
            self.assertTrue(all(e["flags"] == 0 for e in h.Q.posted))
            self.assertEqual({e[1] for e in h.Q.posted}, l.qualifier_posted)
            self.assertEqual(len(l.qualifier_posted), 3)
            self.assertTrue(all(0 < tag < 1 << 63 for tag in l.qualifier_posted))

    def test_each_later_edge_rechecks_the_lease_and_focus(self):
        for change in ("lease", "focus"):
            h, o, l, s, b = key_fixture()
            h.Q.after_post = (lambda: setattr(l.review, "lease", None)) if change == "lease" else \
                             (lambda: setattr(h, "front", 202))
            with self.assertRaises(qualifier.Blocked):
                qualifier.post_guarded_burst(h, o, l, s, b, "test", 76)
            self.assertEqual([e["down"] for e in h.Q.posted], [True, False])
            self.assertEqual(len(l.qualifier_posted), 2)
            self.assertFalse(qualifier.tagged_settled(l, b))
            b.blocked_events.update(l.qualifier_posted)
            self.assertTrue(qualifier.tagged_settled(l, b))

    def test_guard_uses_the_real_focus_scope_public_interface(self):
        sys.path.insert(0, str(ROOT))
        from localflow.v2.transforms.focus_scope import FocusScope
        h, o, l, _, b = key_fixture()
        scope = FocusScope(o.pid, lambda: None, expected_element=o.element, expected_window=o.window)
        scope._element, scope._window, scope._valid = o.element, o.window, True
        l.review_scope = scope
        qualifier.check_key_guard(h, o, l, scope, b, "test", 36)

    def test_barrier_only_blocks_issued_test_tags_without_ax_reads(self):
        h, o, l, s, b = key_fixture()
        tag = b.issue_tag()
        reads = list(h.reads)
        unrelated = {1: tag + 100}
        self.assertIs(b._event(None, 10, unrelated, None), unrelated)
        ordinary = {1: 0}
        self.assertIs(b._event(None, 10, ordinary, None), ordinary)
        self.assertIsNone(b._event(None, 10, {1: tag}, None))
        self.assertEqual(b.blocked_events, {tag})
        self.assertEqual(b.intercepted, 1)
        self.assertEqual(h.reads, reads)
        b._event(None, h.Q.kCGEventTapDisabledByTimeout, None, None)
        self.assertFalse(b.healthy)

    def test_drain_accounts_for_each_tag_and_cannot_mask_a_missing_release(self):
        h, o, l, s, b = key_fixture()
        l.qualifier_posted = {1, 2, 3}
        l.qualifier_consumed = {1, 2}
        self.assertFalse(qualifier.tagged_settled(l, b))
        b.blocked_events.add(2)  # a duplicate count cannot stand for key-up 3
        self.assertFalse(qualifier.tagged_settled(l, b))
        b.blocked_events.add(3)
        self.assertTrue(qualifier.tagged_settled(l, b))

    def test_no_other_key_is_admitted(self):
        h, o, l, s, b = key_fixture()
        for code in (0, 9, 53):
            with self.assertRaises(qualifier.Blocked):
                qualifier.post_guarded_burst(h, o, l, s, b, "test", code)
        self.assertFalse(h.Q.posted)


class EffectAndCleanupTests(unittest.TestCase):
    def test_service_host_can_only_write_one_exact_selected_text_effect(self):
        h, owned, *_ = key_fixture()
        guarded = qualifier.GuardedInsertionHost(h, owned, "seed", "result")
        with self.assertRaises(qualifier.Blocked):
            guarded.set_attribute("field", "AXSelectedText", "result")
        guarded.effect_enabled = True
        for element, name, value in (("other", "AXSelectedText", "result"),
                                     ("field", "AXValue", "result"),
                                     ("field", "AXSelectedText", "other")):
            with self.assertRaises(qualifier.Blocked):
                guarded.set_attribute(element, name, value)
        self.assertTrue(guarded.set_attribute("field", "AXSelectedText", "result"))
        with self.assertRaises(qualifier.Blocked):
            guarded.set_attribute("field", "AXSelectedText", "result")
        self.assertEqual(guarded.write_attempts, 1)

    def test_foreign_content_reads_and_keyboard_fallbacks_are_refused(self):
        h, owned, *_ = key_fixture()
        guarded = qualifier.GuardedInsertionHost(h, owned, "seed", "result")
        with self.assertRaises(qualifier.Blocked):
            guarded.attribute("old-field", "AXValue")
        for method in (qualifier.NoKeyboard().post_paste, qualifier.NoKeyboard().post_copy):
            with self.assertRaises(qualifier.Blocked):
                method()

    def test_cleanup_only_clears_and_closes_owned_synthetic_field(self):
        h, owned, *_ = key_fixture()
        self.assertEqual(qualifier.cleanup_owned(h, owned), "cleared_and_closed_owned_window")
        self.assertEqual(h.text, "")
        self.assertEqual(h.live_windows, ["old-window"])
        self.assertEqual(h.presses, ["close"])

    def test_cleanup_preserves_user_edits_and_never_guesses_save_dialog(self):
        h, owned, *_ = key_fixture()
        h.text = "manual change"
        with self.assertRaises(qualifier.Blocked):
            qualifier.cleanup_owned(h, owned)
        self.assertEqual(h.text, "manual change")
        self.assertFalse(h.presses)
        for edited in (True, None):
            h, owned, *_ = key_fixture()
            h.attrs["new-window", "AXEdited"] = edited
            with self.assertRaisesRegex(qualifier.Blocked, "save_risk"):
                qualifier.cleanup_owned(h, owned, document_app=True)
            self.assertEqual(h.text, "")
            self.assertFalse(h.presses)


class SourceSafetyTests(unittest.TestCase):
    def test_observed_failure_is_distinct_from_missing_capability(self):
        with self.assertRaises(qualifier.Failed):
            qualifier.verify(False, "wrong_readback")
        with self.assertRaises(qualifier.Blocked):
            qualifier.require(False, "permission_unavailable")
        report = {"status": "FAIL"}
        qualifier.mark_blocked(report)
        self.assertEqual(report["status"], "FAIL")

    def test_import_and_default_plan_never_construct_native_host(self):
        output = io.StringIO()
        with patch.object(qualifier, "NativeHost", side_effect=AssertionError("native UI attempted")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(qualifier.main(["--target", "chatgpt"]), 0)
        self.assertIn('"status": "NOT RUN"', output.getvalue())
        self.assertIn("com.openai.codex", output.getvalue())

    def test_evidence_cannot_overwrite_or_escape_ignored_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            good = root / "build/test.json"
            self.assertEqual(qualifier.evidence_path(root, good, "chatgpt"), good)
            good.parent.mkdir()
            good.write_text("prior evidence")
            for path in (good, root / "public.json", root / "build/report.txt"):
                with self.assertRaises(qualifier.Blocked):
                    qualifier.evidence_path(root, path, "chatgpt")
            alias = root / "build/alias.json"
            alias.symlink_to(good)
            with self.assertRaises(qualifier.Blocked):
                qualifier.evidence_path(root, alias, "chatgpt")

    def test_source_has_one_guarded_post_site_no_provider_or_destructive_app_calls(self):
        tree = ast.parse(SCRIPT.read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        posts = [node for node in calls if isinstance(node.func, ast.Attribute)
                 and node.func.attr == "CGEventPost"]
        self.assertEqual(len(posts), 3)  # Return, mouse focus, owned synthetic cleanup
        burst = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == "post_guarded_burst")
        source = ast.get_source_segment(SCRIPT.read_text(), burst)
        self.assertEqual(source.count("check_key_guard("), 2)
        post = next(node for node in burst.body if isinstance(node, ast.FunctionDef) and node.name == "post")
        posting_source = ast.get_source_segment(SCRIPT.read_text(), post)
        self.assertLess(posting_source.index("check_key_guard("), posting_source.index("Q.CGEventPost("))
        self.assertIn('post(False, guard=False)', source)
        forbidden = {"system", "kill", "terminate", "terminate_", "forceTerminate", "run_transform",
                     "read_api_key", "urlopen"}
        # post_paste exists only as a refusal method, never as a called fallback.
        self.assertFalse([node for node in calls if isinstance(node.func, ast.Attribute)
                          and node.func.attr in forbidden])
        for statement in tree.body:
            if isinstance(statement, ast.ImportFrom):
                self.assertFalse((statement.module or "").startswith(("AppKit", "Quartz", "localflow")))
            if isinstance(statement, ast.Import):
                self.assertFalse(any(alias.name in {"subprocess", "Quartz", "AppKit"}
                                     for alias in statement.names))

    def test_real_app_counter_claims_stay_unknown(self):
        tree = ast.parse(SCRIPT.read_text())
        found = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in {
                            "target_return_event_counter", "target_submission_counter"}:
                        self.assertIsInstance(value, ast.Constant)
                        self.assertIsNone(value.value)
                        found += 1
        self.assertGreaterEqual(found, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
