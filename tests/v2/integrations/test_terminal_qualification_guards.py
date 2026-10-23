"""Offline guards only: never launch a shell, Codex, PTY, socket, or model.

Run: .venv/bin/python -m unittest discover -s tests/v2/integrations \
       -p test_terminal_qualification_guards.py -v
"""

import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/v2/qualify_transform_terminals.py'
SPEC = importlib.util.spec_from_file_location('terminal_qualification', SCRIPT)
qualification = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qualification
SPEC.loader.exec_module(qualification)


class InputGuards(unittest.TestCase):
    def test_no_raw_return_submit_exec_or_arbitrary_text_operation(self):
        for operation in ('return', 'enter', 'submit', 'execute', 'write', 'text', 'paste_raw', 'key'):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                qualification.input_frame(operation)
        for frame in qualification.KEYS.values():
            self.assertNotIn(b'\r', frame)
            self.assertNotIn(b'\n', frame)
        self.assertEqual(b'\x07', qualification.input_frame('codex_editor'))

    def test_multiline_source_requires_observed_bracketed_mode(self):
        with self.assertRaises(qualification.Blocked):
            qualification.input_frame('paste', qualification.CODEX_SOURCE)
        frame = qualification.input_frame('paste', qualification.CODEX_SOURCE, bracketed=True)
        self.assertEqual(qualification.PASTE_START + qualification.CODEX_SOURCE.encode() +
                         qualification.PASTE_END, frame)
        self.assertNotIn(b'\r', frame)
        self.assertIn(b'\n', frame[len(qualification.PASTE_START):-len(qualification.PASTE_END)])

    def test_escape_control_and_paste_delimiters_cannot_escape_payload(self):
        for text in ('x\r', 'x\x00', 'x\x03', 'x\x07', 'x\x1b[201~', 'x\x7f', 'x\x85'):
            with self.subTest(text=repr(text)), self.assertRaises(ValueError):
                qualification.input_frame('paste', text, bracketed=True)

    def test_session_mode_does_not_allow_cross_protocol_keys(self):
        child = object.__new__(qualification.OwnedPTY)
        child.kind = 'codex'
        with self.assertRaisesRegex(ValueError, 'not_allowed'):
            child.send('zle_transform')
        child.kind = 'zle'
        with self.assertRaisesRegex(ValueError, 'not_allowed'):
            child.send('paste', qualification.CODEX_SOURCE)

    def test_latest_bracketed_mode_controls_admission(self):
        child = object.__new__(qualification.OwnedPTY)
        child.output = bytearray(qualification.MODE_ON)
        self.assertTrue(child.bracketed)
        child.output.extend(qualification.MODE_OFF)
        self.assertFalse(child.bracketed)
        child.output.extend(qualification.MODE_ON)
        self.assertTrue(child.bracketed)

    def test_all_terminal_replies_are_fixed_and_have_no_return(self):
        for query, (name, frame) in qualification.TERMINAL_QUERIES.items():
            self.assertTrue(query.startswith(b'\x1b'))
            self.assertEqual(frame, qualification.input_frame(name))
            self.assertNotIn(b'\r', frame)
            self.assertNotIn(b'\n', frame)


class StartupAndEnvironmentGuards(unittest.TestCase):
    def test_codex_command_is_fresh_and_has_no_prompt_or_policy_override(self):
        command = qualification.codex_command('/managed/codex', '/owned/workspace')
        self.assertEqual(command, ['/managed/codex', '--no-alt-screen',
                                   '-C', '/owned/workspace'])
        for forbidden in ('resume', 'exec', '--dangerously-bypass-approvals-and-sandbox',
                          '--yolo', '--full-auto', '--prompt', '-p', '-a', '--sandbox'):
            self.assertNotIn(forbidden, command)

    def test_child_only_editor_scope_preserves_native_home_permissions_and_parent(self):
        parent = {'CODEX_HOME': '/native/home', 'CODEX_THREAD_ID': 'inherited-thread',
                  'CODEX_SESSION_ID': 'inherited-session', 'VISUAL': 'prior-visual',
                  'EDITOR': 'prior-editor', 'CODEX_SANDBOX_NETWORK_DISABLED': '1',
                  'OPENAI_API_KEY': 'opaque-fixture-never-read', 'HOME': '/home'}
        child = qualification.child_environment(parent, VISUAL='/owned/editor', EDITOR='/owned/editor')
        self.assertNotIn('CODEX_THREAD_ID', child)
        self.assertNotIn('CODEX_SESSION_ID', child)
        for name in ('CODEX_HOME', 'HOME', 'CODEX_SANDBOX_NETWORK_DISABLED', 'OPENAI_API_KEY'):
            self.assertEqual(parent[name], child[name])
        self.assertEqual('prior-visual', parent['VISUAL'])
        self.assertEqual('prior-editor', parent['EDITOR'])
        self.assertEqual('/owned/editor', child['VISUAL'])

    def test_unknown_worker_bootstrap_blocks_instead_of_widening_permissions(self):
        parent = {'NATIVEPEERS_WORKER_BOOTSTRAP': 'opaque', 'CODEX_HOME': '/native/home'}
        with self.assertRaises(qualification.Blocked):
            qualification.child_environment(parent)
        self.assertEqual('opaque', parent['NATIVEPEERS_WORKER_BOOTSTRAP'])

    def test_trust_auth_policy_and_controller_prompts_block(self):
        for prompt in (b'Do you trust this workspace?', b'Sign in to continue',
                       b'CALLER_UNBOUND', b'CAPABILITY_MISMATCH', b'Approval required',
                       b'controller refused startup', b'error: failed to initialize'):
            with self.subTest(prompt=prompt):
                self.assertTrue(qualification.startup_reasons(prompt))
                self.assertFalse(qualification.composer_ready(prompt + ' ›'.encode()))

    def test_blank_screen_or_bracketed_mode_alone_is_not_composer_proof(self):
        self.assertFalse(qualification.composer_ready(b''))
        self.assertFalse(qualification.composer_ready(qualification.MODE_ON))
        self.assertTrue(qualification.composer_ready('Codex\n› '.encode()))

    def test_total_budget_cannot_exceed_harness_bound(self):
        for seconds in (0, -1, 101, 120):
            with self.assertRaises(ValueError):
                qualification.Budget(seconds)

    def test_missing_integration_blocks_before_any_runtime_or_pty_launch(self):
        with tempfile.TemporaryDirectory() as td, \
                patch.object(qualification, 'OwnedPTY', side_effect=AssertionError('unexpected_pty')), \
                patch.object(qualification.subprocess, 'run', side_effect=AssertionError('unexpected_process')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = qualification.main(['--repo', td])
            self.assertEqual(2, result)
            report = json.loads(output.getvalue())
            self.assertEqual('BLOCKED', report['status'])
            self.assertEqual([], report['cases'])
            self.assertEqual(0, report['raw_return_writes'])

    def test_artifacts_cannot_escape_repo_via_build_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            repo, outside = root / 'repo', root / 'outside'
            repo.mkdir()
            outside.mkdir()
            (repo / 'build').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(qualification.Blocked):
                qualification.run_directory(repo)
            self.assertEqual([], list(outside.iterdir()))


class ZleAndProtocolGuards(unittest.TestCase):
    def test_nonexecuting_accept_guard_precedes_real_widget_source(self):
        rc = qualification.ZSH_RC
        self.assertLess(rc.index('zle -N accept-line _lf_no_accept'), rc.index('source "$LF_WIDGET"'))
        self.assertIn("bindkey '^M' accept-line", rc)
        self.assertIn("bindkey '^J' accept-line", rc)
        self.assertIn('function zle-line-init()', rc)
        self.assertIn('function _lf_dump()', rc)
        self.assertNotIn('eval ', rc)
        self.assertNotIn('zle .accept-line', rc)
        self.assertIn("'FORGE claude-son'", rc)
        self.assertIn("'200 tx'", rc)

    def test_selected_region_expected_result_preserves_prefix_and_suffix(self):
        case = next(case for case in qualification.ZLE_CASES if case.name == 'marked-region')
        self.assertEqual('This is a test prompt', case.source)
        self.assertEqual('prefix Rewritten 😀 region suffix', case.expected)
        self.assertEqual(qualification.MANUAL_EDIT,
                         next(case for case in qualification.ZLE_CASES if case.name == 'stale').expected)

    def test_wrong_source_is_cancelled_without_retaining_unexpected_content(self):
        probe = qualification.ProtocolProbe([{'buffer': 'expected', 'source': 'expected',
                                               'action': 'accept', 'output': 'result'}], Path('/owned'))
        probe.owner = types.SimpleNamespace(pid=123)
        snapshot = types.SimpleNamespace(kind='codex', revision='revision', pid=124,
            parent_pid=123, session='123', tty='/dev/owned', cwd='/owned',
            start=0, end=20, cursor=20, text='unexpected private-looking content',
            source='unexpected private-looking content')
        cancelled, accepted = [], []
        edit = types.SimpleNamespace(snapshot=snapshot, cancel=cancelled.append,
                                     accept=lambda *args, **kw: accepted.append(args))
        probe.open(edit)
        self.assertEqual(['qualification_wrong_source'], cancelled)
        self.assertFalse(accepted)
        self.assertNotIn('buffer', probe.records[0])
        self.assertNotIn('source', probe.records[0])
        self.assertIn('text_sha256', probe.records[0])

    def test_stale_signal_refuses_a_changed_owner_before_signalling(self):
        probe = qualification.ProtocolProbe([{'buffer': 'expected', 'source': 'expected',
                                               'action': 'accept', 'output': 'result'}],
                                             Path('/owned'), stale=Path('/owned/marker'))
        probe.owner = types.SimpleNamespace(pid=123, poll=lambda: None)
        snapshot = types.SimpleNamespace(kind='zle', revision='revision', pid=124,
            parent_pid=123, session='123', tty='/dev/owned', cwd='/owned',
            start=0, end=8, cursor=8, text='expected', source='expected')
        cancelled, accepted = [], []
        edit = types.SimpleNamespace(snapshot=snapshot, cancel=cancelled.append,
                                     accept=lambda *args, **kw: accepted.append(args))
        with patch.object(qualification.os, 'getpgid', return_value=999), \
                patch.object(qualification.os, 'kill') as kill:
            probe.open(edit)
            kill.assert_not_called()
        self.assertEqual(['qualification_stale_blocked'], cancelled)
        self.assertFalse(accepted)

    def test_external_editor_wrapper_uses_real_cli_and_preserves_cancel_exit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wrapper = root / 'editor'
            qualification.make_client(wrapper, '/owned/python', root / 'socket',
                editor_root=Path('/native/.codex/editor'), status_file=root / 'status', files_file=root / 'files')
            source = wrapper.read_text()
            self.assertIn('-m localflow.v2.integrations.cli', source)
            self.assertIn('--socket', source)
            self.assertIn('editor --root', source)
            self.assertIn('status=$?', source)
            self.assertIn('exit "$status"', source)
            self.assertNotIn('exec codex', source)
            self.assertNotIn('source ', source)

    def test_pty_bytes_have_a_single_guarded_writer(self):
        tree = ast.parse(SCRIPT.read_text())
        writes = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                  and node.func.value.id == 'os' and node.func.attr == 'write']
        self.assertEqual(1, len(writes))
        self.assertNotIn('CGEventPost', SCRIPT.read_text())

    def test_cleanup_refuses_changed_or_unowned_process_group(self):
        child = object.__new__(qualification.OwnedPTY)
        child.pid, child.fd = 12345, 678
        child.poll = lambda: None
        with patch.object(qualification.os, 'getpgid', return_value=1), \
                patch.object(qualification.os, 'killpg') as kill, \
                patch.object(qualification.os, 'close') as close:
            with self.assertRaises(qualification.Blocked):
                child.close()
            kill.assert_not_called()
            close.assert_called_once_with(678)

    def test_cleanup_signals_only_recorded_fresh_session_leader(self):
        child = object.__new__(qualification.OwnedPTY)
        child.pid, child.fd = 12345, 678
        polls = iter([None, 0, 0, 0])
        child.poll = lambda: next(polls, 0)
        with patch.object(qualification.os, 'getpgid', return_value=12345), \
                patch.object(qualification.os, 'getsid', return_value=12345), \
                patch.object(qualification.os, 'killpg') as kill, \
                patch.object(qualification.os, 'close'):
            child.close()
            kill.assert_called_once_with(12345, qualification.signal.SIGTERM)

    def test_version_probe_blocks_if_controller_retains_terminal_after_exit(self):
        closed = []
        child = types.SimpleNamespace(status=0, fd=678, eof=False, output=bytearray(b'0.163.0'),
            wait=lambda *args, **kwargs: None, poll=lambda: 0,
            close=lambda: closed.append(True))
        with patch.object(qualification, 'OwnedPTY', return_value=child), \
                patch.object(qualification.select, 'select', return_value=([], [], [])):
            with self.assertRaisesRegex(qualification.Blocked, 'retained_tty'):
                qualification.metadata_command(['/managed/codex', '--version'], {}, Path('/owned'),
                                               qualification.Budget(10), seconds=1)
        self.assertEqual([True], closed)

    def test_version_probe_returns_only_after_owned_terminal_eof(self):
        closed = []
        child = types.SimpleNamespace(status=0, fd=678, eof=True, output=bytearray(b'codex-cli 0.163.0'),
            wait=lambda *args, **kwargs: None, poll=lambda: 0,
            close=lambda: closed.append(True))
        with patch.object(qualification, 'OwnedPTY', return_value=child), \
                patch.object(qualification.select, 'select', return_value=([], [], [])):
            result = qualification.metadata_command(['/managed/codex', '--version'], {}, Path('/owned'),
                                                    qualification.Budget(10), seconds=1)
        self.assertEqual(0, result.returncode)
        self.assertEqual('codex-cli 0.163.0', result.stdout)
        self.assertEqual([True], closed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
