"""Qualify real ZLE and Codex external-editor buffers in fresh owned PTYs.

Run from the integrated checkout, using its Python environment:
  .venv/bin/python scripts/v2/qualify_transform_terminals.py --only all
  .venv/bin/python scripts/v2/qualify_transform_terminals.py --only zle

Artifacts stay in ignored build/tf-pty/run-*/. No source is submitted, no
Return is sent, and no existing shell, Codex history, configuration, or process
is changed. A synthetic PendingEdit decision tests the actual client/editor
handoff, not generation, native preview UI, or arbitrary terminal compatibility.
Unsupported startup, trust/authentication, or native-controller prompts block
qualification; this harness never answers them. Total runtime is bounded below
120 seconds, including owned-process cleanup. Importing this module is inert.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time


KEYS = {'zle_transform': b'\x18\x0c', 'zle_dump': b'\x18\x04',
        'codex_editor': b'\x07'}
TERMINAL_QUERIES = {
    b'\x1b[6n': ('terminal_cursor', b'\x1b[1;1R'),
    b'\x1b[c': ('terminal_attributes', b'\x1b[?1;2c'),
    b'\x1b[>c': ('terminal_secondary_attributes', b'\x1b[>0;0;0c'),
    b'\x1b[?u': ('terminal_keyboard', b'\x1b[?0u'),
    b'\x1b]10;?\x07': ('terminal_foreground', b'\x1b]10;rgb:dddd/dddd/dddd\x1b\\'),
    b'\x1b]11;?\x07': ('terminal_background', b'\x1b]11;rgb:1111/1111/1111\x1b\\'),
}
KEYS.update({name: response for name, response in TERMINAL_QUERIES.values()})
PASTE_START, PASTE_END = b'\x1b[200~', b'\x1b[201~'
MODE_ON, MODE_OFF = b'\x1b[?2004h', b'\x1b[?2004l'
SESSION_KEYS = frozenset({'CODEX_SESSION_ID', 'CODEX_THREAD_ID', 'CODEX_CONVERSATION_ID'})
CODEX_SOURCE = 'This is a test prompt\nSynthetic café 😀 second line'
CODEX_OUTPUT = 'A synthetic transformed prompt\nVerified café 😀 final line'
MANUAL_EDIT = 'A synthetic manual change made during the handoff'


class Blocked(RuntimeError):
    pass


class Failed(AssertionError):
    pass


def safe_text(text):
    if not isinstance(text, str) or not text or len(text.encode('utf-8')) > 256 * 1024:
        raise ValueError('invalid_synthetic_payload')
    if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 for c in text):
        raise ValueError('control_character_in_payload')
    return text


def input_frame(kind, text=None, *, bracketed=False):
    """The only path from the harness into a PTY; no raw text/key fallback."""
    if kind == 'paste':
        if not bracketed:
            raise Blocked('bracketed_paste_not_observed')
        return PASTE_START + safe_text(text).encode('utf-8') + PASTE_END
    if text is not None or kind not in KEYS:
        raise ValueError('unsupported_pty_input')
    return KEYS[kind]


def child_environment(original, **changes):
    """Keep the native home, credentials, permissions and executable policy.

    Only inherited conversation IDs are removed to prevent a fresh CLI from
    borrowing this worker's session. Unknown worker bootstrap variables block
    the run rather than being stripped to obtain a different permission mode.
    """
    environment = dict(original)
    for key in SESSION_KEYS:
        environment.pop(key, None)
    for key in environment:
        if key.startswith(('NATIVEPEERS_', 'NPEER_')) and any(
                word in key for word in ('BOOTSTRAP', 'BINDING', 'WORKER', 'CALLER')):
            raise Blocked('inherited_worker_bootstrap_requires_separate_native_launch')
    environment.update({key: str(value) for key, value in changes.items()})
    return environment


def codex_command(executable, workspace):
    # No prompt, resume, exec, approval override, or permission/sandbox flags.
    # The installed 0.163.0 interactive CLI has no --ephemeral flag (exec
    # alone supports it). Use a fresh zero-turn TUI with no submitted prompt.
    return [str(executable), '--no-alt-screen', '-C', str(workspace)]


def startup_reasons(output):
    text = re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]', b'', output).decode('utf-8', 'replace').lower()
    groups = {
        'trust_prompt': ('do you trust', 'trust this', 'trust the files', 'trust this workspace'),
        'authentication_prompt': ('sign in', 'log in', 'login with', 'authenticate', 'enter your api key'),
        'controller_or_policy': ('caller_unbound', 'capability_mismatch', 'admission_deferred',
                                 'permission denied', 'controller refused', 'approval required'),
        'startup_error': ('unrecognized argument', 'unexpected argument', 'error: failed'),
    }
    return [name for name, anchors in groups.items() if any(anchor in text for anchor in anchors)]


def composer_ready(output):
    reasons = startup_reasons(output)
    if reasons:
        return False
    return any(anchor in output.lower() for anchor in (
        '›'.encode(), '❯'.encode(), b'? for shortcuts', b'context left', b'ctrl+g'))


class Budget:
    def __init__(self, seconds):
        if not 1 <= seconds <= 100:
            raise ValueError('timeout_must_be_between_1_and_100_seconds')
        self.end = time.monotonic() + seconds

    def left(self, maximum=100):
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise Blocked('total_timeout')
        return min(maximum, remaining)


class OwnedPTY:
    def __init__(self, command, environment, cwd, budget, *, kind='zle'):
        self.command, self.budget = command, budget
        self.kind = kind
        self.output = bytearray()
        self.audit = []
        self.status = None
        self.eof = False
        self._query_tail = b''
        self.last_output = time.monotonic()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                os.chdir(cwd)
                os.execvpe(command[0], command, environment)
            except BaseException:
                os._exit(127)
        os.set_blocking(self.fd, False)
        self.resize(24, 80)

    @property
    def bracketed(self):
        return self.output.rfind(MODE_ON) > self.output.rfind(MODE_OFF)

    def resize(self, rows, columns):
        if not 2 <= rows <= 200 or not 8 <= columns <= 400:
            raise ValueError('invalid_pty_size')
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))

    def poll(self):
        if self.status is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.status = os.waitstatus_to_exitcode(status)
        return self.status

    def read(self, seconds=.05):
        if select.select([self.fd], [], [], min(seconds, self.budget.left()))[0]:
            try:
                data = os.read(self.fd, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                data = b''
            self.output.extend(data)
            if not data:
                self.eof = True
            if data:
                self.last_output = time.monotonic()
                joined = self._query_tail + data
                for query, (kind, _) in TERMINAL_QUERIES.items():
                    start = 0
                    while (index := joined.find(query, start)) >= 0:
                        start = index + len(query)
                        if start > len(self._query_tail):
                            self.send(kind)
                self._query_tail = joined[-32:]
            # Screen data is transient and never written into the report.
            if len(self.output) > 256 * 1024:
                del self.output[:-256 * 1024]

    def wait(self, predicate, phase, *, seconds=6, inspect_startup=False):
        end = time.monotonic() + self.budget.left(seconds)
        while time.monotonic() < end:
            if inspect_startup:
                reasons = startup_reasons(self.output)
                if reasons:
                    raise Blocked(phase + ':' + ','.join(reasons))
            if predicate():
                return
            if self.poll() is not None:
                if predicate():
                    return
                raise Blocked(phase + ':owned_process_exited:' + str(self.status))
            self.read()
        raise Blocked(phase + ':timeout')

    def send(self, kind, text=None):
        terminal_reply = kind.startswith('terminal_') and kind in KEYS
        allowed = {'codex': {'paste', 'codex_editor'},
                   'zle': {'zle_transform', 'zle_dump'}, 'metadata': set()}[self.kind]
        if kind not in allowed and not terminal_reply:
            raise ValueError('input_not_allowed_for_owned_session')
        frame = input_frame(kind, text, bracketed=self.bracketed)
        self.budget.left()
        remaining = memoryview(frame)
        while remaining:
            _, writable, _ = select.select([], [self.fd], [], self.budget.left(1))
            if not writable:
                raise Blocked('pty_input_timeout')
            remaining = remaining[os.write(self.fd, remaining):]
        self.audit.append({'kind': kind, 'bytes': len(frame),
                           'payload': text if kind == 'paste' else None,
                           'key_hex': frame.hex() if kind != 'paste' else None})

    def close(self):
        # A recorded direct child/session leader is the only signal target.
        # No process discovery, pkill, terminal injection, or existing session.
        try:
            if self.poll() is None:
                if os.getpgid(self.pid) != self.pid or os.getsid(self.pid) != self.pid:
                    raise Blocked('owned_process_group_changed_cleanup_not_proven')
                os.killpg(self.pid, signal.SIGTERM)
                end = time.monotonic() + .5
                while self.poll() is None and time.monotonic() < end:
                    time.sleep(.01)
                if self.poll() is None:
                    os.killpg(self.pid, signal.SIGKILL)
                    end = time.monotonic() + .5
                    while self.poll() is None and time.monotonic() < end:
                        time.sleep(.01)
                if self.poll() is None:
                    raise Blocked('owned_process_cleanup_unconfirmed')
        except ProcessLookupError:
            if self.poll() is None:
                raise Blocked('owned_process_cleanup_unconfirmed') from None
        finally:
            os.close(self.fd)


def metadata_command(command, environment, cwd, budget, *, seconds):
    """Bound version/git probes even if a managed wrapper retains output pipes."""
    child = OwnedPTY(command, environment, cwd, budget, kind='metadata')
    try:
        child.wait(lambda: child.poll() is not None, 'metadata_command', seconds=seconds)
        # A reaped producer may still have one final output frame in the PTY.
        for _ in range(4):
            if not select.select([child.fd], [], [], 0)[0]:
                break
            child.read(.01)
        if not child.eof:
            raise Blocked('metadata_controller_retained_tty_cleanup_unconfirmed')
        return subprocess.CompletedProcess(command, child.status,
                                           stdout=child.output.decode('utf-8', 'replace'), stderr='')
    finally:
        child.close()


ZSH_RC = r'''
setopt multibyte
unsetopt beep
HISTFILE=/dev/null
SAVEHIST=0
PROMPT='lf-qualification> '
LF_ACCEPT_ATTEMPTS=0
LF_DUMPS=0
print -r -- 0 > "$LF_ACCEPT_COUNT"
function _lf_no_accept() {
    (( LF_ACCEPT_ATTEMPTS += 1 ))
    print -r -- "$LF_ACCEPT_ATTEMPTS" > "$LF_ACCEPT_COUNT"
    zle -M 'Qualification refuses command acceptance'
}
zle -N accept-line _lf_no_accept
bindkey -e
bindkey '^M' accept-line
bindkey '^J' accept-line
function _lf_dump() {
    print -rn -- "$BUFFER" > "$LF_DUMP"
    (( LF_DUMPS += 1 ))
    print -r -- "$LF_DUMPS:$CURSOR:$MARK:$REGION_ACTIVE" > "$LF_DUMP_META"
}
zle -N _lf_dump
function _lf_apply_manual_change() {
    IFS= read -r -d $'\0' BUFFER < "$LF_MANUAL_FILE"
    CURSOR=${#BUFFER}
    MARK=0
    REGION_ACTIVE=0
    print -r -- changed > "$LF_STALE_MARKER"
}
zle -N _lf_apply_manual_change
function TRAPUSR1() {
    zle _lf_apply_manual_change
}
# Install the nonexecuting accept-line widget BEFORE loading the real adapter.
source "$LF_WIDGET"
bindkey '^X^L' localflow-transform
bindkey '^X^D' _lf_dump
function zle-line-init() {
    IFS= read -r -d $'\0' BUFFER < "$LF_SEED_FILE"
    CURSOR=$LF_SEED_CURSOR
    MARK=$LF_SEED_MARK
    REGION_ACTIVE=$LF_SEED_REGION
    _lf_dump
    print -r -- ready > "$LF_READY"
}
zle -N zle-line-init
# Deliberate screen contamination must never enter the logical source.
print -r -- 'FORGE claude-son'
print -r -- '200 tx'
'''


def write_executable(path, source):
    path.write_text(source)
    path.chmod(0o700)


def make_client(path, python, socket_path, *, editor_root=None, status_file=None, files_file=None):
    command = [str(python), '-m', 'localflow.v2.integrations.cli', '--socket', str(socket_path)]
    if editor_root is not None:
        command += ['editor', '--root', str(editor_root)]
    source = '#!/bin/sh\n'
    if files_file is not None:
        source += 'printf \'%s\\0\' "$@" >> ' + shlex.quote(str(files_file)) + '\n'
    source += shlex.join(command) + ' "$@"\nstatus=$?\n'
    if status_file is not None:
        source += 'printf \'%s\\n\' "$status" >> ' + shlex.quote(str(status_file)) + '\n'
    source += 'exit "$status"\n'
    write_executable(path, source)


class ProtocolProbe:
    def __init__(self, steps, workspace, *, stale=None):
        self.steps, self.workspace, self.stale = steps, workspace, stale
        self.owner = None
        self.records, self.errors = [], []
        self.lock = threading.Lock()

    def open(self, edit):
        with self.lock:
            index = len(self.records)
            capture = edit.snapshot
            record = {'kind': capture.kind, 'revision': capture.revision,
                      'pid': capture.pid, 'parent_pid': capture.parent_pid,
                      'session': capture.session, 'tty': capture.tty,
                      'start': capture.start, 'end': capture.end, 'cursor': capture.cursor}
            self.records.append(record)
            if self.owner is None or capture.session != str(self.owner.pid) or capture.cwd != str(self.workspace):
                self.errors.append('unexpected_process_session_or_workspace')
                edit.cancel('qualification_wrong_owner')
                return
            if index >= len(self.steps):
                self.errors.append('unexpected_extra_editor_request')
                edit.cancel('qualification_unexpected_request')
                return
            step = self.steps[index]
            if capture.text != step['buffer'] or capture.source != step['source']:
                # Never retain unexpected (potentially private) text.
                record.update(text_bytes=len(capture.text.encode('utf-8')),
                              text_sha256=hashlib.sha256(capture.text.encode()).hexdigest())
                self.errors.append('wrong_source')
                edit.cancel('qualification_wrong_source')
                return
            record.update(buffer=capture.text, source=capture.source)
            if self.stale is not None:
                marker = self.stale
                if self.owner.poll() is not None or os.getpgid(self.owner.pid) != self.owner.pid or \
                        os.getsid(self.owner.pid) != self.owner.pid:
                    self.errors.append('stale_owner_changed')
                    edit.cancel('qualification_stale_blocked')
                    return
                os.kill(self.owner.pid, signal.SIGUSR1)
                # ZLE defers its trap while blocked reading the editor pipe.
                # The trap runs as the pipe returns, before the widget's
                # compare-and-assign check. Verify its acknowledgement and
                # preserved manual buffer after that handoff, not before.
                record['manual_change_signal_sent_before_accept'] = True
            if step['action'] == 'cancel':
                record['decision'] = 'cancelled'
                edit.cancel('qualification_cancelled')
            else:
                record['decision'] = 'accepted'
                record['replacement'] = step['output']
                record['accepted'] = edit.accept(step['output'], expected_revision=capture.revision)


def statuses(path):
    try:
        return [int(line) for line in path.read_text().splitlines() if line]
    except (FileNotFoundError, ValueError):
        return []


def dump_sequence(path):
    try:
        return int(path.read_text().split(':')[0])
    except (FileNotFoundError, ValueError):
        return 0


def read_dump(shell, directory):
    metadata = directory / 'dump-meta'
    previous = dump_sequence(metadata)
    shell.send('zle_dump')
    shell.wait(lambda: dump_sequence(metadata) > previous, 'zle_dump')
    return (directory / 'dump').read_text()


@dataclass(frozen=True)
class ZleCase:
    name: str
    seed: str
    replacement: str
    start: int = 0
    end: int | None = None
    action: str = 'accept'
    narrow: bool = False

    @property
    def stop(self):
        return len(self.seed) if self.end is None else self.end

    @property
    def source(self):
        return self.seed[self.start:self.stop]

    @property
    def expected(self):
        if self.action == 'cancel':
            return self.seed
        if self.action == 'stale':
            return MANUAL_EDIT
        return self.seed[:self.start] + self.replacement + self.seed[self.stop:]


ZLE_CASES = (
    ZleCase('wrong-source', 'This is a test prompt', 'A synthetic transformed prompt'),
    ZleCase('unicode-multiline', 'Synthetic café 😀\nsecond line\n', 'New e\u0301 😀\nsecond replacement\n'),
    ZleCase('marked-region', 'prefix This is a test prompt suffix', 'Rewritten 😀 region', 7, 28),
    ZleCase('resize-wrapping', 'Synthetic wrapped prompt ' * 12, 'Synthetic wrapped result ' * 10, narrow=True),
    ZleCase('cancel', 'A synthetic draft kept on cancellation', 'Must never be applied', action='cancel'),
    ZleCase('stale', 'A synthetic draft changed during handoff', 'Must never overwrite a manual change', action='stale'),
)


def integration_server(probe, socket_path, budget):
    from localflow.v2.integrations.buffers import PreviewAdapter
    from localflow.v2.integrations.ipc import BufferServer
    adapter = PreviewAdapter(lambda callback: callback(), probe.open, lambda edit: None)
    return BufferServer(adapter, socket_path, timeout=budget.left(8)).start()


def zle_case(case, repo, run, python, budget):
    directory = run / case.name
    directory.mkdir(mode=0o700)
    (directory / 'seed').write_bytes(case.seed.encode('utf-8') + b'\0')
    (directory / 'manual').write_bytes(MANUAL_EDIT.encode('utf-8') + b'\0')
    (directory / '.zshenv').write_text('unsetopt GLOBAL_RCS\n')
    (directory / '.zshrc').write_text(ZSH_RC)
    client, client_status = directory / 'client', directory / 'client-status'
    make_client(client, python, run / 'socket', status_file=client_status)
    region = case.start != 0 or case.stop != len(case.seed)
    python_path = os.pathsep.join(filter(None, (str(repo), os.environ.get('PYTHONPATH', ''))))
    environment = child_environment(os.environ, PYTHONPATH=python_path, ZDOTDIR=directory,
        TERM='xterm-256color',
        LC_ALL='en_US.UTF-8', LOCALFLOW_TERMINAL_CLIENT=client,
        LF_WIDGET=repo / 'localflow/v2/integrations/zle.zsh',
        LF_SEED_FILE=directory / 'seed', LF_MANUAL_FILE=directory / 'manual',
        LF_SEED_CURSOR=case.stop if region else len(case.seed), LF_SEED_MARK=case.start,
        LF_SEED_REGION=int(region), LF_DUMP=directory / 'dump',
        LF_DUMP_META=directory / 'dump-meta', LF_ACCEPT_COUNT=directory / 'accept-count',
        LF_READY=directory / 'ready', LF_STALE_MARKER=directory / 'stale-marker')
    step = {'buffer': case.seed, 'source': case.source,
            'action': 'cancel' if case.action == 'cancel' else 'accept', 'output': case.replacement}
    probe = ProtocolProbe([step], directory,
                          stale=directory / 'stale-marker' if case.action == 'stale' else None)
    server = shell = None
    result = {'name': case.name, 'kind': 'zle', 'source': case.source,
              'seed': case.seed, 'expected': case.expected,
              'command': ['/bin/zsh', '-d', '-i']}
    try:
        server = integration_server(probe, run / 'socket', budget)
        shell = OwnedPTY(['/bin/zsh', '-d', '-i'], environment, directory, budget)
        probe.owner = shell
        shell.wait(lambda: (directory / 'ready').exists(), 'zle_startup')
        initial = (directory / 'dump').read_text()
        if initial != case.seed:
            raise Failed('initial_logical_buffer_mismatch')
        if case.narrow:
            shell.resize(12, 24)
        shell.send('zle_transform')
        shell.wait(lambda: bool(statuses(client_status)), 'zle_client')
        actual = read_dump(shell, directory)
        if actual in {case.expected, case.seed, MANUAL_EDIT, 'FORGE claude-son', '200 tx'}:
            result['readback'] = actual
        else:
            result.update(readback_bytes=len(actual.encode('utf-8')),
                          readback_sha256=hashlib.sha256(actual.encode('utf-8')).hexdigest())
        result.update(protocol=probe.records,
                      client_exits=statuses(client_status),
                      accept_line_attempts=int((directory / 'accept-count').read_text()))
        if probe.errors:
            error = ','.join(probe.errors)
            if any(reason in error for reason in ('stale_change_not_observed',
                                                  'stale_owner_changed', 'unexpected_process_session')):
                raise Blocked(error)
            raise Failed(error)
        if actual != case.expected or result['accept_line_attempts'] != 0:
            raise Failed('logical_readback_or_nonexecution_check_failed')
        if case.action == 'stale' and not (directory / 'stale-marker').exists():
            raise Failed('manual_change_trap_not_observed')
        expected_exit = 1 if case.action == 'cancel' else 0
        if case.action != 'stale' and result['client_exits'] != [expected_exit]:
            raise Failed('client_exit_does_not_match_decision')
        result['status'] = 'PASS'
    except (Blocked, OSError, ValueError) as error:
        result.update(status='BLOCKED', reason=str(error))
    except Failed as error:
        result.update(status='FAIL', reason=str(error))
    finally:
        if shell:
            result['pty_inputs'] = shell.audit
            try:
                shell.close()
                result['owned_process_closed'] = True
            except (Blocked, OSError) as error:
                result.update(status='BLOCKED', cleanup_reason=str(error))
        if server:
            server.stop()
    return result


def codex_case(repo, run, python, executable, budget, *, trusted_repo=False):
    directory = run / 'codex'
    directory.mkdir(parents=True, mode=0o700)
    workspace = repo if trusted_repo else directory / 'workspace'
    if not trusted_repo:
        workspace.mkdir(mode=0o700)
    editor_root = Path.home() / '.codex/editor'
    status_file, files_file = directory / 'editor-status', directory / 'editor-files'
    wrapper = directory / 'external-editor'
    make_client(wrapper, python, run / 'socket', editor_root=editor_root,
                status_file=status_file, files_file=files_file)
    python_path = os.pathsep.join(filter(None, (str(repo), os.environ.get('PYTHONPATH', ''))))
    environment = child_environment(os.environ, PYTHONPATH=python_path, TERM='xterm-256color',
                                    VISUAL=shlex.quote(str(wrapper)), EDITOR=shlex.quote(str(wrapper)))
    steps = [{'buffer': CODEX_SOURCE, 'source': CODEX_SOURCE, 'action': 'accept', 'output': CODEX_OUTPUT},
             {'buffer': CODEX_OUTPUT, 'source': CODEX_OUTPUT, 'action': 'cancel'}]
    probe = ProtocolProbe(steps, workspace)
    server = child = None
    result = {'name': 'codex-external-editor', 'kind': 'codex', 'source': CODEX_SOURCE,
              'expected': CODEX_OUTPUT, 'approved_editor_root': str(editor_root)}
    try:
        configured_home = Path(environment.get('CODEX_HOME', str(Path.home() / '.codex')))
        if configured_home != Path.home() / '.codex' or editor_root.resolve() != editor_root:
            raise Blocked('native_codex_home_does_not_match_approved_editor_root')
        if trusted_repo:
            import tomllib
            config = tomllib.loads((configured_home / 'config.toml').read_text())
            if config.get('projects', {}).get(str(repo), {}).get('trust_level') != 'trusted':
                raise Blocked('repository_not_already_trusted_in_native_config')
        version = metadata_command([str(executable), '--version'], environment, workspace, budget, seconds=5)
        match = re.search(r'\b0\.163\.0\b', version.stdout)
        if version.returncode != 0 or not match:
            raise Blocked('installed_codex_version_is_not_0.163.0')
        result['version'] = '0.163.0'
        result['version_command'] = version.args
        if not trusted_repo:
            initialized = metadata_command(['git', 'init', '--quiet', '--template=', str(workspace)],
                                           environment, workspace, budget, seconds=3)
            if initialized.returncode != 0:
                raise Blocked('disposable_git_workspace_initialization_failed')
        server = integration_server(probe, run / 'socket', budget)
        command = codex_command(executable, workspace)
        result['command'] = command
        child = OwnedPTY(command, environment, workspace, budget, kind='codex')
        probe.owner = child
        child.wait(lambda: child.bracketed and composer_ready(child.output) and
                   child.output.rfind(b']7501;state=idle:app=codex') >
                       child.output.rfind(b']7501;state=working:app=codex') and
                   time.monotonic() - child.last_output >= .8,
                   'codex_startup', seconds=40, inspect_startup=True)
        result['bracketed_paste_observed_before_seed'] = True
        child.send('paste', CODEX_SOURCE)
        child.wait(lambda: b'This is a test prompt' in re.sub(
            rb'\x1b\[[0-?]*[ -/]*[@-~]', b'', child.output),
            'codex_seed_visible', seconds=5, inspect_startup=True)
        child.read(.3)  # let the native paste aggregator settle before Ctrl+G
        child.send('codex_editor')
        child.wait(lambda: len(statuses(status_file)) >= 1, 'codex_first_editor',
                   seconds=12, inspect_startup=True)
        if 'unexpected_process_session_or_workspace' in probe.errors:
            raise Blocked('native_controller_changed_editor_session')
        if not probe.records and statuses(status_file)[0] != 0:
            raise Blocked('external_editor_refused_or_approved_root_unavailable')
        if probe.errors or statuses(status_file)[0] != 0 or not probe.records:
            raise Failed('first_editor_handoff_failed:' + ','.join(probe.errors))
        # Consume editor teardown/redraw before sending the second key.
        child.read(.1)
        child.send('codex_editor')
        child.wait(lambda: len(statuses(status_file)) >= 2, 'codex_readback_editor',
                   seconds=12, inspect_startup=True)
        if probe.errors or len(probe.records) != 2:
            raise Failed('independent_composer_readback_failed:' + ','.join(probe.errors))
        if statuses(status_file) != [0, 130]:
            raise Failed('editor_accept_or_cancellation_exit_mismatch')
        paths = [Path(p) for p in files_file.read_text().split('\0') if p]
        if len(paths) != 2 or any(p.parent != editor_root or p.suffix != '.md' for p in paths):
            raise Failed('actual_editor_file_outside_approved_root')
        result.update(status='PASS', readback=probe.records[1]['buffer'], protocol=probe.records,
                      editor_exits=statuses(status_file), editor_files=[str(p) for p in paths],
                      cancellation_exit=130)
    except (Blocked, OSError, ValueError, subprocess.SubprocessError) as error:
        result.update(status='BLOCKED', reason=str(error))
    except Failed as error:
        result.update(status='FAIL', reason=str(error))
    finally:
        if child:
            result['pty_inputs'] = child.audit
            result['startup_observations'] = startup_reasons(child.output)
            if result.get('status') != 'PASS':
                diagnostic = directory / 'owned-startup-screen.private.txt'
                diagnostic.write_text(re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]', b'',
                    child.output).decode('utf-8', 'replace'))
                diagnostic.chmod(0o600)
                result['private_diagnostic'] = str(diagnostic)
            try:
                child.close()
                result['owned_process_closed'] = True
            except (Blocked, OSError) as error:
                result.update(status='BLOCKED', cleanup_reason=str(error))
        if server:
            server.stop()
    return result


def run_directory(repo):
    root = repo / 'build/tf-pty'
    if not root.resolve().is_relative_to(repo):
        raise Blocked('artifact_directory_escapes_repository')
    root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='run-', dir=root)).resolve()
    if len(os.fsencode(run / 'socket')) >= 104:
        run.rmdir()
        raise Blocked('socket_path_too_long_run_from_canonical_parent_checkout')
    return run


def write_report(path, report):
    staged = path.with_suffix('.tmp')
    staged.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    staged.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--only', choices=['all', 'zle', 'codex'], default='all')
    parser.add_argument('--codex', type=Path, default=shutil.which('codex'))
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--timeout', type=float, default=95)
    parser.add_argument('--trusted-repo-composer', action='store_true',
        help='test a fresh zero-turn composer in this already trusted repo; never alter native trust')
    args = parser.parse_args(argv)
    started = time.monotonic()
    report = {'status': 'BLOCKED', 'cases': [], 'synthetic_decisions_only': True,
              'provider_verified': False, 'native_preview_ui_verified': False,
              'raw_return_writes': 0, 'unframed_newline_writes': 0}
    output = None
    try:
        budget = Budget(args.timeout)
        repo = args.repo.resolve(strict=True)
        if not (repo / 'localflow/v2/integrations/zle.zsh').is_file():
            raise Blocked('integrated_production_modules_missing_use_repo_argument')
        run = run_directory(repo)
        output = run / 'report.json'
        report['artifacts'] = str(run)
        report['production_sources'] = {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
            for name in ('localflow/v2/integrations/zle.zsh', 'localflow/v2/integrations/cli.py',
                         'localflow/v2/integrations/buffers.py', 'localflow/v2/integrations/ipc.py',
                         'localflow/v2/integrations/editor.py')}
        # Production imports are deliberately deferred until an explicit run.
        sys.path.insert(0, str(repo))
        version = metadata_command(['/bin/zsh', '--version'], child_environment(os.environ),
                                   run, budget, seconds=3)
        report['zsh_version'] = version.stdout.strip()
        if args.only in ('all', 'zle'):
            for case in ZLE_CASES:
                budget.left()
                report['cases'].append(zle_case(case, repo, run, args.python, budget))
                write_report(output, report)
        if args.only in ('all', 'codex'):
            if args.codex is None:
                report['cases'].append({'name': 'codex-external-editor', 'status': 'BLOCKED',
                                        'reason': 'managed_codex_executable_not_found'})
            else:
                report['cases'].append(codex_case(repo, run, args.python, args.codex, budget,
                    trusted_repo=args.trusted_repo_composer))
        states = [case['status'] for case in report['cases']]
        report['status'] = 'FAIL' if 'FAIL' in states else 'BLOCKED' if 'BLOCKED' in states else 'PASS'
    except (Blocked, OSError, ValueError, ImportError, subprocess.SubprocessError) as error:
        report.update(status='BLOCKED', reason=str(error))
    except KeyboardInterrupt:
        report.update(status='BLOCKED', reason='qualification_cancelled')
    except Exception as error:
        report.update(status='FAIL', reason='harness_error:' + type(error).__name__)
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    if output:
        write_report(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
