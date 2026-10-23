"""Synthetic terminal integration checks; no active terminal/app is touched."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from localflow.v2.integrations import BufferServer, PendingEdit, PreviewAdapter
from localflow.v2.integrations.buffers import MAX_TEXT_BYTES, validate_text
from localflow.v2.integrations.cli import snapshot
from localflow.v2.integrations.editor import EditorFile
from localflow.v2.integrations.install import install, uninstall
from localflow.v2.integrations.ipc import receive_frame, request_edit, send_frame


class BufferTests(unittest.TestCase):
    def test_region_offsets_preserve_unicode_prefix_suffix_and_duplicate_text(self):
        capture = snapshot("zle", "😀 cafe\u0301 sample | sample\n", 14, 8, 14)
        self.assertEqual(capture.source, "sample")
        result, cursor = capture.replace("two\nlines\t🙂\n")
        self.assertEqual(result, "😀 cafe\u0301 two\nlines\t🙂\n | sample\n")
        self.assertEqual(cursor, 20)
        self.assertEqual(capture.scope, "Marked region")
        self.assertNotEqual(capture.revision, replace(capture, cursor=13).revision)

    def test_reject_controls_and_oversize_without_truncation(self):
        for text in ("a\0b", "x\x1b[200~", "x\r", "x\x7f", "x\x85",
                     "x" * (MAX_TEXT_BYTES + 1)):
            with self.assertRaises(ValueError):
                validate_text(text)
        self.assertEqual(validate_text("\n😀\t"), "\n😀\t")

    def test_blank_region_and_fake_codex_region_refused(self):
        for args in (("zle", "", 0), ("codex", "buffer", 2, 1, 4)):
            with self.assertRaises(ValueError):
                snapshot(*args)

    def test_accept_is_explicit_revision_bound_and_exactly_once(self):
        capture = snapshot("zle", "original", 8)
        edit = PendingEdit(capture, "test-operation", 10)
        self.assertFalse(edit.accept("stale", expected_revision="wrong"))
        results = []
        workers = [threading.Thread(target=lambda: results.append(
            edit.accept("replacement", expected_revision=capture.revision))) for _ in range(12)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(sum(results), 1)
        self.assertEqual(edit.result()["text"], "replacement")

    def test_cancel_and_timeout_prevent_late_accept(self):
        capture = snapshot("zle", "original", 8)
        edit = PendingEdit(capture, "test", .01)
        edit.cancel()
        self.assertFalse(edit.accept("late", expected_revision=capture.revision))
        edit = PendingEdit(capture, "test", .001)
        time.sleep(.003)
        self.assertFalse(edit.accept("late", expected_revision=capture.revision))


class SocketTests(unittest.TestCase):
    def setUp(self):
        # Short Unix paths also work on macOS's 104-byte sockaddr_un limit.
        self.temp = tempfile.TemporaryDirectory(prefix="lf-", dir="/private/tmp")
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "private/editor.sock"
        self.servers = []
        self.opened = []
        self.closed = threading.Event()

    def tearDown(self):
        for server in self.servers:
            server.stop()
        self.temp.cleanup()

    def server(self, handler, timeout=1):
        adapter = PreviewAdapter(lambda fn: fn(), handler,
                                 lambda edit: self.closed.set())
        try:
            server = BufferServer(adapter, self.path, timeout=timeout).start()
        except PermissionError as error:
            self.skipTest("Unix socket bind blocked by sandbox: " + str(error))
        self.servers.append(server)
        return server

    def test_same_user_real_socket_returns_only_logical_region(self):
        def preview(edit):
            self.opened.append(edit.snapshot.source)
            edit.accept("better\n😀\n", expected_revision=edit.snapshot.revision)
        self.server(preview)
        capture = snapshot("zle", "left sample right", 11, 5, 11)
        result = request_edit(capture, self.path)
        self.assertEqual(self.opened, ["sample"])
        self.assertEqual(result["text"], "left better\n😀\n right")
        self.assertEqual(result["revision"], capture.revision)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_wrong_token_and_claimed_pid_never_open_preview(self):
        self.server(self.opened.append)
        for wrong_token in (True, False):
            with socket.socket(socket.AF_UNIX) as conn:
                conn.connect(str(self.path))
                challenge = receive_frame(conn)
                capture = snapshot("zle", "sample", 6)
                if not wrong_token:
                    capture = replace(capture, pid=os.getpid() + 1000)
                send_frame(conn, {"version": 1, "token": "wrong" if wrong_token else
                                  challenge["token"], "snapshot": asdict(capture),
                                  "revision": capture.revision})
                with self.assertRaises(EOFError):
                    receive_frame(conn)
        self.assertFalse(self.opened)

    def test_disconnect_revokes_pending_preview_and_late_accept(self):
        shown = threading.Event()
        def preview(edit):
            self.opened.append(edit)
            shown.set()
        self.server(preview)
        conn = socket.socket(socket.AF_UNIX)
        conn.connect(str(self.path))
        challenge = receive_frame(conn)
        capture = snapshot("zle", "sample", 6)
        send_frame(conn, {"version": 1, "token": challenge["token"],
                          "snapshot": asdict(capture), "revision": capture.revision})
        self.assertTrue(shown.wait(1))
        conn.close()
        self.assertTrue(self.closed.wait(1))
        self.assertFalse(self.opened[0].accept("late", expected_revision=capture.revision))

    def test_busy_and_timeout_release_editor(self):
        shown = threading.Event()
        self.server(lambda edit: shown.set(), timeout=.2)
        capture = snapshot("zle", "sample", 6)
        first = []
        worker = threading.Thread(target=lambda: first.append(request_edit(capture, self.path)))
        worker.start()
        self.assertTrue(shown.wait(1))
        result = request_edit(capture, self.path)
        self.assertEqual(result["reason"], "preview_busy")
        worker.join(2)
        self.assertEqual(first[0]["reason"], "timeout")

    def test_existing_endpoint_and_symlink_are_not_removed(self):
        self.path.parent.mkdir(mode=0o700)
        self.path.write_text("owned elsewhere")
        adapter = PreviewAdapter(lambda fn: fn(), self.opened.append, lambda edit: None)
        with self.assertRaises(ValueError):
            BufferServer(adapter, self.path).start()
        self.assertEqual(self.path.read_text(), "owned elsewhere")
        self.path.unlink()
        self.path.symlink_to(self.root / "other")
        with self.assertRaises(ValueError):
            request_edit(snapshot("zle", "sample", 6), self.path)

    def test_oversize_frame_rejected_before_source_read(self):
        self.server(self.opened.append)
        with socket.socket(socket.AF_UNIX) as conn:
            conn.connect(str(self.path))
            receive_frame(conn)
            conn.sendall(struct.pack("!I", 100_000_000))
            with self.assertRaises(EOFError):
                receive_frame(conn)
        self.assertFalse(self.opened)

    def test_editor_cli_accept_and_cancel_preserve_original_on_cancel(self):
        accept = [True]
        def preview(edit):
            if accept[0]:
                edit.accept("new\n😀", expected_revision=edit.snapshot.revision)
            else:
                edit.cancel()
        self.server(preview)
        editor_root = self.root / "codex-editor"
        editor_root.mkdir(mode=0o700)
        draft = editor_root / "draft.md"
        draft.write_text("original")
        draft.chmod(0o600)
        command = [sys.executable, "-m", "localflow.v2.integrations.cli", "--socket",
                   str(self.path), "editor", "--root", str(editor_root), str(draft)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(draft.read_text(), "new\n😀")
        accept[0] = False
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertEqual(draft.read_text(), "new\n😀")

    def test_zle_cli_frames_multiline_unicode_without_paste_or_newline_events(self):
        self.server(lambda edit: edit.accept("new\n😀\n", expected_revision=edit.snapshot.revision))
        result = subprocess.run([sys.executable, "-m", "localflow.v2.integrations.cli",
            "--socket", str(self.path), "zle", "--cursor", "4", "--mark", "0",
            "--region", "0"], input=b"old\n", capture_output=True, cwd=ROOT, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "6\0new\n😀\n\0".encode())


class ConnectedProtocolTests(unittest.TestCase):
    """Real same-user kernel credentials on socketpair, without a bound listener."""

    def connect(self, handler, timeout=.2):
        self.closed = threading.Event()
        adapter = PreviewAdapter(lambda fn: fn(), handler, lambda edit: self.closed.set())
        server = BufferServer(adapter, timeout=timeout)
        client, remote = socket.socketpair()
        server._slots.acquire()
        server._connections.add(remote)
        thread = threading.Thread(target=server._handle, args=(remote,))
        thread.start()
        self.addCleanup(client.close)
        self.addCleanup(thread.join, 2)
        client.settimeout(2)
        return client, receive_frame(client), server

    def send(self, client, challenge, capture, **extra):
        request = {"version": 1, "token": challenge["token"],
                   "snapshot": asdict(capture), "revision": capture.revision}
        request.update(extra)
        send_frame(client, request)

    def test_real_peer_revision_region_and_token_round_trip(self):
        opened = []
        def handler(edit):
            opened.append(edit.snapshot.source)
            edit.accept("replacement\n😀", expected_revision=edit.snapshot.revision)
        client, challenge, _ = self.connect(handler)
        capture = snapshot("zle", "prefix draft suffix", 12, 7, 12)
        self.send(client, challenge, capture)
        result = receive_frame(client)
        self.assertEqual(result["text"], "prefix replacement\n😀 suffix")
        self.assertEqual(result["revision"], capture.revision)
        self.assertEqual(result["operation_id"], challenge["token"])
        self.assertEqual(opened, ["draft"])
        self.assertTrue(self.closed.wait(1))

    def test_disconnect_cancels_and_closes_preview(self):
        opened = []
        shown = threading.Event()
        def handler(edit):
            opened.append(edit)
            shown.set()
        client, challenge, _ = self.connect(handler)
        capture = snapshot("zle", "draft", 5)
        self.send(client, challenge, capture)
        self.assertTrue(shown.wait(1))
        client.close()
        self.assertTrue(self.closed.wait(1))
        self.assertFalse(opened[0].active)
        self.assertFalse(opened[0].accept("late", expected_revision=capture.revision))

    def test_timeout_is_no_op_and_releases_preview(self):
        client, challenge, _ = self.connect(lambda edit: None, timeout=.02)
        self.send(client, challenge, snapshot("codex", "draft", 5))
        result = receive_frame(client)
        self.assertEqual(result, {"status": "cancelled", "reason": "timeout",
                                  "operation_id": challenge["token"]})

    def test_replayed_challenge_on_new_connection_is_rejected(self):
        opened = []
        first, challenge, _ = self.connect(opened.append)
        first.close()
        second, second_challenge, _ = self.connect(opened.append)
        self.assertNotEqual(challenge["token"], second_challenge["token"])
        self.send(second, challenge, snapshot("zle", "draft", 5))
        with self.assertRaises(EOFError):
            receive_frame(second)
        self.assertFalse(opened)

    def test_mismatched_pid_session_revision_and_oversize_frame_are_rejected(self):
        opened = []
        for field in ("pid", "session", "revision", "size"):
            client, challenge, _ = self.connect(opened.append)
            capture = snapshot("zle", "draft", 5)
            if field == "size":
                client.sendall(struct.pack("!I", 100_000_000))
            elif field == "pid":
                self.send(client, challenge, replace(capture, pid=capture.pid + 1000))
            elif field == "session":
                self.send(client, challenge, replace(capture, session="false-session"))
            else:
                self.send(client, challenge, capture, revision="false-revision")
            with self.assertRaises(EOFError):
                receive_frame(client)
        self.assertFalse(opened)

    def test_queued_preview_is_not_opened_after_cancellation(self):
        queue, opened, closed = [], [], []
        adapter = PreviewAdapter(queue.append, opened.append, closed.append)
        edit = PendingEdit(snapshot("zle", "draft", 5), "test", 1)
        adapter.open(edit)
        edit.cancel()
        queue.pop(0)()
        self.assertFalse(opened)
        adapter.close(edit)
        queue.pop(0)()
        self.assertEqual(closed, [edit])


class ZleWidgetTests(unittest.TestCase):
    def run_widget(self, *, stale=False):
        with tempfile.TemporaryDirectory(prefix="lf-", dir="/private/tmp") as temp:
            directory = Path(temp).resolve()
            client = directory / "fixture-client"
            client.write_text("#!" + sys.executable + "\n" +
                "import os,sys,signal,time\n" +
                "from pathlib import Path\n" +
                "Path(os.environ['CAPTURE']).write_bytes(sys.stdin.buffer.read())\n" +
                ("os.kill(int(os.environ['TEST_SHELL_PID']), signal.SIGUSR1); time.sleep(.03)\n"
                 if stale else "") +
                "sys.stdout.buffer.write('6\\0new\\n😀\\n\\0'.encode())\n")
            client.chmod(0o700)
            output = directory / "buffer"
            captured = directory / "capture"
            operations = directory / "operations"
            script = """
function zle() { print -r -- "$*" >> "$OPERATIONS"; }
source "$WIDGET"
BUFFER=$'original\n😀'
CURSOR=10
MARK=0
REGION_ACTIVE=0
CONTEXT=start
export TEST_SHELL_PID=$$
trap 'BUFFER="manual edit"' USR1
localflow-transform
result=$?
print -rn -- "$BUFFER" > "$OUTPUT"
exit $result
"""
            env = dict(os.environ, LOCALFLOW_TERMINAL_CLIENT=str(client),
                       CAPTURE=str(captured), OUTPUT=str(output), OPERATIONS=str(operations),
                       WIDGET=str(ROOT / "localflow/v2/integrations/zle.zsh"))
            result = subprocess.run(["/bin/zsh", "-dfc", script], env=env,
                                    capture_output=True, timeout=5)
            self.assertEqual(captured.read_text(), "original\n😀")
            calls = operations.read_text()
            self.assertNotIn("accept-line", calls)
            return result, output.read_text(), calls

    def test_multiline_unicode_return_updates_only_the_logical_buffer(self):
        result, buffer, calls = self.run_widget()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(buffer, "new\n😀\n")
        self.assertIn("redisplay", calls)

    def test_user_edit_during_handoff_is_preserved(self):
        result, buffer, calls = self.run_widget(stale=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(buffer, "manual edit")
        self.assertIn("Buffer changed", calls)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lf-", dir="/private/tmp")
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "draft.md"
        self.path.write_text("original\n😀\n")
        self.path.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_file_readback_and_mode(self):
        with EditorFile(self.path, self.root) as editor:
            editor.commit("replacement\n\n")
        self.assertEqual(self.path.read_bytes(), b"replacement\n\n")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_changed_buffer_and_inode_refuse_update(self):
        with EditorFile(self.path, self.root) as editor:
            self.path.write_text("manual edit")
            with self.assertRaisesRegex(ValueError, "buffer_changed"):
                editor.commit("replacement")
        self.assertEqual(self.path.read_text(), "manual edit")

    def test_symlink_hardlink_outside_root_and_public_file_refused(self):
        alias = self.root / "alias.md"
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            EditorFile(alias, self.root)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaises(ValueError):
            EditorFile(self.path, self.root)
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            EditorFile(self.path, self.root)
        with self.assertRaises(ValueError):
            EditorFile(self.path, self.root.parent)

    def test_editor_cancellation_exits_without_codex_reapplying_or_trimming(self):
        from localflow.v2.integrations.cli import main
        original = self.path.read_bytes()
        with patch("localflow.v2.integrations.cli.request_edit", return_value={"status": "cancelled"}):
            self.assertEqual(main(["editor", "--root", str(self.root), str(self.path)]), 130)
        self.assertEqual(self.path.read_bytes(), original)

    def test_editor_refuses_output_that_codex_would_trim(self):
        import contextlib
        import io
        from localflow.v2.integrations.cli import main
        original = self.path.read_bytes()
        message = io.StringIO()
        with patch("localflow.v2.integrations.cli.request_edit",
                   return_value={"status": "accepted", "text": "new\n"}), \
                contextlib.redirect_stderr(message):
            self.assertEqual(main(["editor", "--root", str(self.root), str(self.path)]), 2)
        self.assertIn("trailing whitespace", message.getvalue())
        self.assertEqual(self.path.read_bytes(), original)

    def test_editor_accepts_multiline_text_and_reads_back_exact_bytes(self):
        from localflow.v2.integrations.cli import main
        with patch("localflow.v2.integrations.cli.request_edit",
                   return_value={"status": "accepted", "text": "first\n😀 final"}):
            self.assertEqual(main(["editor", "--root", str(self.root), str(self.path)]), 0)
        self.assertEqual(self.path.read_bytes(), "first\n😀 final".encode())


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lf-", dir="/private/tmp")
        self.root = Path(self.temp.name).resolve()
        self.directory = self.root / "integration with spaces"
        self.editor_root = self.root / "editor"
        self.rc = self.root / ".zshrc"
        self.original = b"export VISUAL='existing editor'\nexport EDITOR=other\n# no final newline"
        self.rc.write_bytes(self.original)

    def tearDown(self):
        self.temp.cleanup()

    def test_idempotent_install_uninstall_restores_exact_rc(self):
        install(self.directory, self.editor_root, self.rc)
        first = self.rc.read_bytes()
        install(self.directory, self.editor_root, self.rc)
        self.assertEqual(self.rc.read_bytes(), first)
        uninstall(self.directory, self.rc)
        self.assertEqual(self.rc.read_bytes(), self.original)
        uninstall(self.directory, self.rc)

    def test_modified_owned_files_refuse_uninstall_and_preserve_rc(self):
        install(self.directory, self.editor_root, self.rc)
        first = self.rc.read_bytes()
        script = self.directory / "localflow-editor"
        script.write_text("custom edit")
        with self.assertRaises(ValueError):
            uninstall(self.directory, self.rc)
        self.assertEqual(script.read_text(), "custom edit")
        self.assertEqual(self.rc.read_bytes(), first)

    def test_codex_wrapper_scopes_environment_and_preserves_arguments(self):
        install(self.directory, self.editor_root)
        fake = self.root / "fake-codex"
        fake.write_text("#!/bin/sh\nexec " + str(sys.executable) +
                        " -c 'import json,os,sys; print(json.dumps([os.environ[\"VISUAL\"],"
                        "os.environ[\"EDITOR\"],sys.argv[1:]]))' \"$@\"\n")
        fake.chmod(0o700)
        env = dict(os.environ, VISUAL="previous", EDITOR="previous-other", LOCALFLOW_CODEX=str(fake))
        result = subprocess.run([str(self.directory / "codex-localflow"), "--name", "synthetic title"],
                                env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        visual, editor, args = json.loads(result.stdout)
        import shlex
        self.assertEqual(shlex.split(visual), [str(self.directory / "localflow-editor")])
        self.assertEqual(editor, visual)
        self.assertEqual(args, ["--name", "synthetic title"])
        self.assertEqual(env["VISUAL"], "previous")

    def test_interactive_wrapper_preserves_existing_codex_function_and_editor_scope(self):
        install(self.directory, self.editor_root, self.rc)
        script = '''
function codex() { print -r -- "managed:$*"; print -r -- "$VISUAL"; }
source "$RC"
VISUAL=previous
codex-localflow -r "synthetic title" --flag
print -r -- "$VISUAL"
localflow-terminal-unload
(( ! ${+functions[codex-localflow]} ))
'''
        result = subprocess.run(['/bin/zsh', '-dfc', script],
            env=dict(os.environ, RC=str(self.rc)), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], 'managed:-r synthetic title --flag')
        import shlex
        self.assertEqual(shlex.split(lines[1]), [str(self.directory / 'localflow-editor')])
        self.assertEqual(lines[2], 'previous')

    def test_preexisting_scoped_launch_function_is_not_overwritten_or_unloaded(self):
        install(self.directory, self.editor_root, self.rc)
        script = '''
function codex-localflow() { print -r -- existing; }
source "$RC"
codex-localflow
localflow-terminal-unload
codex-localflow
'''
        result = subprocess.run(['/bin/zsh', '-dfc', script],
            env=dict(os.environ, RC=str(self.rc)), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['existing', 'existing'])

    def test_owned_binding_can_be_unloaded_without_changing_existing_binding(self):
        install(self.directory, self.editor_root, self.rc)
        script = """
bindkey -M emacs '^X^L' beginning-of-line
bindkey -M viins -r '^X^L'
source "$RC"
bindkey -M emacs '^X^L'
bindkey -M viins '^X^L'
localflow-terminal-unload
bindkey -M emacs '^X^L'
bindkey -M viins '^X^L'
"""
        result = subprocess.run(["/bin/zsh", "-dfc", script],
            env=dict(os.environ, RC=str(self.rc)), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = result.stdout.splitlines()
        self.assertIn("beginning-of-line", rows[0])
        self.assertIn("localflow-transform", rows[1])
        self.assertIn("beginning-of-line", rows[2])
        self.assertIn("undefined-key", rows[3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
