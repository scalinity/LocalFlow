"""Synthetic origin checks; never write to a real TTY or import the app shell.

Run directly, or with unittest discovery. LOCALFLOW_TEST_SOURCE_ROOT selects
another checkout for a read-only check before this file is integrated there.
The only real process query reads this test process's own parent PID.
"""
from __future__ import annotations

import ast
import contextlib
from dataclasses import replace
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


ROOT = Path(os.environ.get("LOCALFLOW_TEST_SOURCE_ROOT",
                          Path(__file__).resolve().parents[3])).resolve()
sys.path.insert(0, str(ROOT))

from localflow.v2.integrations import cli, origin
from localflow.v2.integrations.buffers import BufferSnapshot, PendingEdit


MARKER = "LocalFlow buffer " + "ab" * 16
PUSH = b"\x1b[22;0t\x1b]0;"
POP = b"\x1b[23;0t"


def capture(**changes):
    values = dict(kind="zle", text="prefix draft suffix", cursor=12,
                  start=7, end=12, session="synthetic-session", pid=310,
                  parent_pid=311, tty="/dev/synthetic-tty",
                  cwd="/synthetic/workspace", marker=MARKER)
    values.update(changes)
    return BufferSnapshot(**values)


class FakeTTY:
    """Replace origin.os only, so real temporary-file IO stays unaffected."""

    fd = 170

    def __init__(self, *, is_tty=True, open_error=None, write_results=()):
        self.is_tty = is_tty
        self.open_error = open_error
        self.write_results = iter(write_results)
        self.events = []
        self.sent = bytearray()

    def open(self, path, flags):
        self.events.append(("open", path, flags))
        if self.open_error:
            raise self.open_error
        return self.fd

    def isatty(self, fd):
        self.events.append(("isatty", fd))
        return self.is_tty

    def write(self, fd, data):
        self.events.append(("write", fd, data))
        result = next(self.write_results, len(data))
        if isinstance(result, BaseException):
            raise result
        self.sent.extend(data[:result])
        return result

    def close(self, fd):
        self.events.append(("close", fd))

    def install(self):
        return patch.object(origin, "os", SimpleNamespace(
            open=self.open, isatty=self.isatty, write=self.write,
            close=self.close, O_WRONLY=os.O_WRONLY, O_NOCTTY=os.O_NOCTTY))

    @property
    def writes(self):
        return [event[2] for event in self.events if event[0] == "write"]


class MarkerLifecycleTests(unittest.TestCase):
    def test_fresh_random_nonce_is_private_tty_only_and_restored(self):
        markers = []
        for _ in range(2):
            tty = FakeTTY()
            stdout, stderr = io.StringIO(), io.StringIO()
            with tty.install(), contextlib.redirect_stdout(stdout), \
                    contextlib.redirect_stderr(stderr):
                with origin.terminal_marker() as marker:
                    self.assertRegex(marker, r"\ALocalFlow buffer [0-9a-f]{32}\Z")
                    self.assertEqual(b"".join(tty.writes), PUSH + marker.encode() + b"\x07")
                    markers.append(marker)
            self.assertEqual(tty.events[0], ("open", "/dev/tty", os.O_WRONLY | os.O_NOCTTY))
            self.assertEqual(tty.events[-2:], [("write", tty.fd, POP), ("close", tty.fd)])
            self.assertTrue(all(event[1] == tty.fd for event in tty.events[1:]))
            self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))
        self.assertNotEqual(*markers)

    def test_body_errors_and_keyboard_cancellation_always_restore(self):
        for error in (ValueError("synthetic"), OSError("synthetic"), KeyboardInterrupt()):
            tty = FakeTTY()
            with self.subTest(error=type(error).__name__), tty.install():
                with self.assertRaises(type(error)):
                    with origin.terminal_marker():
                        raise error
            self.assertEqual(tty.writes[-1], POP)
            self.assertEqual(tty.events[-1], ("close", tty.fd))

    def test_no_controlling_tty_never_falls_back_to_stdout_or_stderr(self):
        for tty in (FakeTTY(open_error=OSError("no controlling tty")), FakeTTY(is_tty=False)):
            with self.subTest(events=tty.events), tty.install(), \
                    contextlib.redirect_stdout(io.StringIO()) as stdout, \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                with origin.terminal_marker() as marker:
                    self.assertEqual(marker, "")
            self.assertFalse(tty.writes)
            self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))
            closes = [event for event in tty.events if event[0] == "close"]
            self.assertEqual(len(closes), int(tty.open_error is None))

    def test_failed_title_write_cannot_advertise_a_live_marker(self):
        tty = FakeTTY(write_results=[OSError("synthetic write failure")])
        with tty.install():
            with origin.terminal_marker() as marker:
                self.assertEqual(marker, "", "a failed title write cannot bind a pane")
        self.assertEqual(tty.events[-1], ("close", tty.fd))

    def test_failed_title_write_attempts_stack_restoration(self):
        # An error may follow a partial kernel write; a pushed stack must not leak.
        tty = FakeTTY(write_results=[7, OSError("synthetic partial-write failure")])
        with tty.install():
            with origin.terminal_marker():
                pass
        self.assertIn(POP, tty.writes)

    def test_short_write_must_finish_setup_or_refuse_marker(self):
        tty = FakeTTY(write_results=[5])
        with tty.install():
            with origin.terminal_marker() as marker:
                if marker:
                    self.assertEqual(bytes(tty.sent), PUSH + marker.encode() + b"\x07",
                                     "a partial title sequence is not a pane binding")
        self.assertEqual(tty.events[-1], ("close", tty.fd))

    def test_restore_error_still_closes_descriptor(self):
        tty = FakeTTY(write_results=[7, len(b"\x1b]0;" + MARKER.encode() + b"\x07"),
                                    OSError("synthetic restore failure")])
        with tty.install(), self.assertRaises(OSError):
            with origin.terminal_marker():
                pass
        self.assertEqual(tty.events[-1], ("close", tty.fd))


class SnapshotOriginTests(unittest.TestCase):
    def test_cwd_and_marker_are_both_revision_bound(self):
        original = capture()
        for changed in (replace(original, cwd="/synthetic/other"),
                        replace(original, marker="LocalFlow buffer " + "cd" * 16)):
            with self.subTest(changed=changed):
                self.assertEqual(changed.source, original.source)
                self.assertNotEqual(changed.revision, original.revision)
                edit = PendingEdit(changed, "synthetic-operation", 10)
                self.assertFalse(edit.accept("replacement", expected_revision=original.revision))
                self.assertTrue(edit.active)
                self.assertTrue(edit.accept("replacement", expected_revision=changed.revision))

    def test_absolute_bounded_cwd_and_exact_lowercase_nonce_validation(self):
        for cwd in ("", "/", "/synthetic/space and 😀", "/" + "x" * 2047):
            with self.subTest(cwd_length=len(cwd)):
                self.assertEqual(capture(cwd=cwd).cwd, cwd)
        for cwd in (None, 12, b"/synthetic", "relative/path", "/bad\0path", "/" + "x" * 2048):
            with self.subTest(cwd=repr(cwd)), self.assertRaisesRegex(ValueError, "invalid_workspace_path"):
                capture(cwd=cwd)
        for marker in ("", MARKER):
            self.assertEqual(capture(marker=marker).marker, marker)
        for marker in (None, 12, MARKER.encode(), "arbitrary title", MARKER[:-1],
                       MARKER + "a", "LocalFlow buffer " + "A" * 32,
                       "LocalFlow buffer " + "g" * 32, "XocalFlow buffer " + "a" * 32,
                       "LocalFlow buffer " + "a" * 31 + "\0", "x" * 4096):
            with self.subTest(marker=repr(marker)), self.assertRaisesRegex(ValueError, "invalid_terminal_marker"):
                capture(marker=marker)

    def test_cli_snapshot_captures_actual_process_and_workspace_not_title_evidence(self):
        with patch.object(cli.os, "getcwd", return_value="/synthetic/workspace"):
            value = cli.snapshot("zle", "draft", 5, tty="/dev/synthetic-tty", marker=MARKER)
        self.assertEqual((value.pid, value.parent_pid, value.session),
                         (os.getpid(), os.getppid(), str(os.getsid(0))))
        self.assertEqual((value.cwd, value.marker), ("/synthetic/workspace", MARKER))


class ClientMarkerTests(unittest.TestCase):
    def invoke(self, argv, request, *, source=b"prefix draft suffix"):
        tty = FakeTTY()
        stdin = io.TextIOWrapper(io.BytesIO(source), encoding="utf-8")
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        stderr = io.StringIO()
        captures = []

        def handoff(value, socket):
            captures.append(value)
            self.assertRegex(value.marker, r"\ALocalFlow buffer [0-9a-f]{32}\Z")
            self.assertEqual(b"".join(tty.writes), PUSH + value.marker.encode() + b"\x07")
            if isinstance(request, BaseException):
                raise request
            if request == "accept":
                edit = PendingEdit(value, "synthetic-operation", 10)
                edit.accept("better\n😀", expected_revision=value.revision)
                return edit.result()
            return request

        with tty.install(), patch.object(cli, "request_edit", side_effect=handoff), \
                patch.object(sys, "stdin", stdin), patch.object(sys, "stdout", stdout), \
                patch.object(sys, "stderr", stderr):
            result = cli.main(argv)
        stdout.flush()
        self.assertEqual(tty.writes[-1], POP)
        self.assertEqual(tty.events[-1], ("close", tty.fd))
        return result, stdout.buffer.getvalue(), stderr.getvalue(), captures

    @staticmethod
    def zle_args():
        return ["zle", "--cursor", "12", "--mark", "7", "--region", "1",
                "--tty", "/dev/synthetic-tty"]

    def test_zle_stdout_is_only_exact_nul_framed_buffer(self):
        status, output, error, captures = self.invoke(self.zle_args(), "accept")
        self.assertEqual((status, error), (0, ""))
        text, cursor = captures[0].replace("better\n😀")
        self.assertEqual(output, str(cursor).encode() + b"\0" + text.encode() + b"\0")
        self.assertEqual(output.count(b"\0"), 2)
        self.assertNotIn(b"\x1b", output)
        self.assertNotIn(captures[0].marker.encode(), output)

    def test_zle_cancel_error_and_interrupt_restore_without_stdout_protocol(self):
        for request, expected in (({"status": "cancelled", "reason": "synthetic-cancel"}, 1),
                                  (OSError("synthetic"), 2), (EOFError("synthetic"), 2),
                                  (ValueError("synthetic"), 2), (KeyboardInterrupt(), 130)):
            with self.subTest(request=type(request).__name__):
                status, output, error, captures = self.invoke(self.zle_args(), request)
                self.assertEqual((status, output), (expected, b""))
                self.assertTrue(error)
                self.assertNotIn(captures[0].marker, error)

    def test_editor_accept_cancel_error_and_post_response_validation_restore(self):
        with tempfile.TemporaryDirectory(prefix="lf-origin-", dir="/private/tmp") as directory:
            root = Path(directory).resolve()
            path = root / "synthetic.md"
            original = "synthetic original\n"
            cases = (("accept", 0, "better\n😀"),
                     ({"status": "cancelled"}, 130, original),
                     (OSError("synthetic"), 2, original),
                     (KeyboardInterrupt(), 130, original),
                     ({"status": "accepted", "text": "would be trimmed\n"}, 2, original))
            for request, expected_status, expected_text in cases:
                with self.subTest(request=type(request).__name__):
                    path.write_text(original)
                    path.chmod(0o600)
                    status, output, _, captures = self.invoke(
                        ["editor", "--root", str(root), str(path)], request)
                    self.assertEqual((status, output), (expected_status, b""))
                    self.assertEqual(path.read_text(), expected_text)
                    self.assertEqual(captures[0].kind, "codex")


class AncestryTests(unittest.TestCase):
    def test_os_lookup_walks_actual_parents_with_bounded_ps_arguments(self):
        parents = {310: 311, 311: 200}

        def ps(argv, **kwargs):
            self.assertEqual(argv[:4], ["/bin/ps", "-o", "ppid=", "-p"])
            self.assertEqual(kwargs, dict(capture_output=True, text=True, timeout=.2))
            return SimpleNamespace(returncode=0, stdout="  " + str(parents[int(argv[4])]) + "\n")

        with patch.object(origin.subprocess, "run", side_effect=ps) as run:
            self.assertTrue(origin.has_ancestor(310, 200))
        self.assertEqual([entry.args[0][-1] for entry in run.call_args_list], ["310", "311"])

    def test_cycles_missing_process_and_depth_limit_refuse(self):
        read = Mock(side_effect={310: 311, 311: 310}.__getitem__)
        self.assertFalse(origin.has_ancestor(310, 200, read_parent=read))
        self.assertEqual(read.call_args_list, [call(310), call(311)])
        read = Mock(return_value=0)
        self.assertFalse(origin.has_ancestor(310, 200, read_parent=read))
        read.assert_called_once_with(310)
        read = Mock(side_effect=lambda pid: pid + 1)
        self.assertFalse(origin.has_ancestor(310, 400, read_parent=read))
        self.assertLessEqual(read.call_count, 16)
        self.assertTrue(origin.has_ancestor(310, 325, read_parent=lambda pid: pid + 1))
        self.assertFalse(origin.has_ancestor(310, 326, read_parent=lambda pid: pid + 1))

    def test_lookup_errors_and_unparseable_or_dead_ps_fail_closed(self):
        for error in (OSError("synthetic"), ValueError("synthetic"),
                      subprocess.TimeoutExpired("/bin/ps", .2)):
            with self.subTest(error=type(error).__name__):
                self.assertFalse(origin.has_ancestor(310, 200, read_parent=Mock(side_effect=error)))
        for result in (SimpleNamespace(returncode=1, stdout="200"),
                       SimpleNamespace(returncode=0, stdout=""),
                       SimpleNamespace(returncode=0, stdout="invalid")):
            with self.subTest(result=result), patch.object(origin.subprocess, "run", return_value=result):
                self.assertFalse(origin.has_ancestor(310, 200))

    def test_real_ps_reads_only_this_test_process_parent(self):
        pid, parent = os.getpid(), os.getppid()
        try:
            result = subprocess.run(["/bin/ps", "-o", "ppid=", "-p", str(pid)],
                                    capture_output=True, text=True, timeout=.2)
        except OSError as error:
            self.skipTest("own-process ps unavailable: " + str(error))
        if result.returncode:
            self.skipTest("own-process ps refused: " + result.stderr.strip())
        self.assertEqual(int(result.stdout.strip()), parent)
        self.assertTrue(origin.has_ancestor(pid, parent))


class FakeFocusHost:
    def __init__(self):
        self.pid = 200
        self.front = {"pid": self.pid, "bundle": "com.mitchellh.ghostty"}
        self.element = "synthetic-field"
        self.field_window = self.focused_window = "synthetic-window"
        self.owners = {self.element: self.pid, self.field_window: self.pid,
                       "other-window": self.pid, "foreign-window": 900}
        self.titles = {self.field_window: "terminal — " + MARKER,
                       "other-window": MARKER, "foreign-window": MARKER}
        self.calls = []

    def frontmost(self):
        self.calls.append(("frontmost",))
        return self.front

    def focused_element_for(self, pid):
        self.calls.append(("focus", pid))
        return self.element

    def element_pid(self, element):
        self.calls.append(("owner", element))
        return self.owners.get(element)

    def focused_window_title(self, element):
        self.calls.append(("focused_title", element))
        return self.titles.get(self.focused_window)

    def attribute(self, element, name):
        self.calls.append(("attribute", element, name))
        if name == "AXWindow" and element == self.element:
            return self.field_window
        if name == "AXFocusedWindow":
            return self.focused_window
        if name == "AXTitle":
            return self.titles.get(element)
        raise AssertionError("unexpected content/control read: " + name)


class WindowMarkerTests(unittest.TestCase):
    def test_matching_nonce_requires_current_foreground_and_owned_element(self):
        host = FakeFocusHost()
        self.assertTrue(origin.window_has_marker(host, host.pid, MARKER))
        self.assertFalse(origin.window_has_marker(host, host.pid, MARKER[:-1] + "c"))
        self.assertFalse(origin.window_has_marker(host, host.pid, ""))
        self.assertFalse(origin.window_has_marker(host, host.pid, "arbitrary title"))
        host.front = {"pid": 900}
        host.calls.clear()
        self.assertFalse(origin.window_has_marker(host, host.pid, MARKER))
        self.assertFalse(any(event[0] in ("focus", "focused_title", "attribute") for event in host.calls))

    def test_missing_or_foreign_field_is_refused_before_title_read(self):
        for field, owner in ((None, None), ("synthetic-field", 900), ("synthetic-field", None)):
            host = FakeFocusHost()
            host.element = field
            host.owners[field] = owner
            with self.subTest(field=field, owner=owner):
                self.assertFalse(origin.window_has_marker(host, host.pid, MARKER))
                self.assertFalse(any(event[0] in ("focused_title", "attribute") for event in host.calls))

    def test_unreadable_or_changed_nonce_does_not_bind(self):
        for title in (None, "", "unmarked terminal", "LocalFlow buffer " + "cd" * 16):
            host = FakeFocusHost()
            host.titles[host.focused_window] = title
            with self.subTest(title=title):
                self.assertFalse(origin.window_has_marker(host, host.pid, MARKER))

    def test_foreign_containing_window_cannot_supply_marker(self):
        host = FakeFocusHost()
        host.field_window = host.focused_window = "foreign-window"
        self.assertFalse(origin.window_has_marker(host, host.pid, MARKER))

    def test_missing_containing_window_cannot_supply_marker(self):
        host = FakeFocusHost()
        host.field_window = None
        self.assertFalse(origin.window_has_marker(host, host.pid, MARKER))

    def test_another_focused_window_title_is_not_the_fields_pane(self):
        host = FakeFocusHost()
        host.titles[host.field_window] = "unmarked original window"
        host.focused_window = "other-window"
        self.assertFalse(origin.window_has_marker(host, host.pid, MARKER))


class MarkerDeliveryTests(unittest.TestCase):
    def start_wait(self, host, edit, **kwargs):
        self.pending, self.outcomes = [], []
        self.now = 0
        with patch.object(origin, 'has_ancestor', return_value=True):
            started = origin.await_window_marker(host, edit,
                lambda: self.outcomes.append('ready'), lambda: self.outcomes.append('missing'),
                lambda delay, callback: self.pending.append(callback),
                clock=lambda: self.now, **kwargs)
        return started

    def test_delayed_osc_title_can_arrive_after_ipc_without_blocking(self):
        host = FakeFocusHost();host.titles[host.field_window] = 'old title'
        self.assertTrue(self.start_wait(host, PendingEdit(capture(), 'op', 10)))
        self.pending.pop(0)()
        self.assertEqual(self.outcomes, [])
        host.titles[host.field_window] = MARKER
        self.pending.pop(0)()
        self.assertEqual(self.outcomes, ['ready'])
        self.assertEqual(self.pending, [])

    def test_switching_pane_during_title_delivery_cannot_acquire_request(self):
        host = FakeFocusHost();host.titles[host.field_window] = 'old title'
        self.start_wait(host, PendingEdit(capture(), 'op', 10))
        host.field_window = 'other-window'
        self.pending.pop(0)()
        self.assertEqual(self.outcomes, ['missing'])

    def test_missing_marker_has_a_deadline_and_disconnect_stops_callbacks(self):
        host = FakeFocusHost();host.titles[host.field_window] = 'old title'
        edit = PendingEdit(capture(), 'op', 10)
        self.start_wait(host, edit)
        self.now = .6;self.pending.pop(0)()
        self.assertEqual(self.outcomes, ['missing'])
        self.start_wait(host, edit)
        edit.cancel();self.pending.pop(0)()
        self.assertEqual(self.outcomes, [])

    def test_invalid_ancestry_cannot_start_a_wait(self):
        with patch.object(origin, 'has_ancestor', return_value=False):
            callback = Mock()
            self.assertFalse(origin.await_window_marker(FakeFocusHost(), PendingEdit(capture(), 'op', 10), callback, callback, callback))
            callback.assert_not_called()


def buffer_origin_method():
    """Compile only the current method, without running AppKit app startup."""
    path = ROOT / "localflow/app.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AppDelegate")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_tf_buffer_origin")
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])
    namespace = {"__package__": "localflow"}
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[method.name]


class AppOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin_method = staticmethod(buffer_origin_method())

    def setUp(self):
        self.host = FakeFocusHost()
        self.app = SimpleNamespace(_insertion=SimpleNamespace(host=self.host),
                                   _context_deny_invalid=False,
                                   _context_policy={"context_denied_apps": []})
        self.edit = PendingEdit(capture(), "synthetic-operation", 10)

    def resolve(self, **kwargs):
        return self.origin_method(self.app, self.edit, **kwargs)

    def test_actual_os_ancestry_accepts_even_when_claimed_parent_differs(self):
        self.edit = PendingEdit(capture(parent_pid=901), "synthetic-operation", 10)
        with patch.object(origin.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=str(self.host.pid))) as ps:
            self.assertEqual(self.resolve(), self.host.pid)
        self.assertEqual(ps.call_args.args[0], ["/bin/ps", "-o", "ppid=", "-p", "310"])

    def test_spoofed_client_parent_cannot_replace_os_ancestry(self):
        self.edit = PendingEdit(capture(parent_pid=self.host.pid), "synthetic-operation", 10)
        with patch.object(origin.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout="1")) as ps:
            self.assertIsNone(self.resolve())
        ps.assert_called_once()

    def test_terminal_policy_expected_pid_and_active_lease_are_required(self):
        mutations = (
            lambda: self.edit.cancel(),
            lambda: setattr(self.host, "front", None),
            lambda: self.host.front.update(pid=None),
            lambda: self.host.front.update(bundle="com.apple.TextEdit"),
            lambda: setattr(self.app, "_context_deny_invalid", True),
            lambda: self.app._context_policy.update(context_denied_apps=[" COM.MITCHELLH.GHOSTTY "]),
        )
        for mutate in mutations:
            self.setUp()
            mutate()
            with self.subTest(mutate=mutations.index(mutate)), \
                    patch.object(origin, "has_ancestor") as ancestry:
                self.assertIsNone(self.resolve())
                ancestry.assert_not_called()
        self.setUp()
        with patch.object(origin, "has_ancestor") as ancestry:
            self.assertIsNone(self.resolve(expected_pid=900))
            ancestry.assert_not_called()

    def test_final_effect_rechecks_marker_even_when_pid_and_ancestry_match(self):
        with patch.object(origin, "has_ancestor", return_value=True) as ancestry:
            self.assertEqual(self.resolve(expected_pid=self.host.pid), self.host.pid)
            self.host.titles[self.host.focused_window] = "different pane"
            self.assertIsNone(self.resolve(expected_pid=self.host.pid))
            self.assertEqual(ancestry.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
