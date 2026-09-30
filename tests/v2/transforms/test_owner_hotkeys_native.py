"""Owned native source qualification, with the real cached model and M08.

The app uses an isolated data home and a private general pasteboard. The
target is our existing native helper. Only its own selected synthetic text
is read. Global events are posted ONLY while that helper owns focus. This
is source-process evidence, not qualification of a rebuilt app bundle.
"""
import json
import os
import pathlib
import queue
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def pump(seconds):
    """Deliver NSWorkspace activation notifications before reading its cache."""
    from Foundation import NSDate, NSRunLoop
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.02))


def test_app():
    import AppKit
    from PyObjCTools import AppHelper
    real = AppKit.NSPasteboard
    private = real.pasteboardWithUniqueName()
    class Boards:
        def generalPasteboard(self):
            return private
        def __getattr__(self, name):
            return getattr(real, name)
    AppKit.NSPasteboard = Boards()
    from localflow.app import main
    def command(m):
        d = AppKit.NSApplication.sharedApplication().delegate()
        try:
            if m['cmd'] == 'state':
                panel = d._tf_panel
                st = panel._state if panel else {}
                result = st.get('result')
                reply = {'engines': d.supervisor.engine_state,
                         'front_pid': AppKit.NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier(),
                         'tap': bool(d._transform_hotkeys.tap),
                         'visible': bool(panel and panel.panel.isVisible()),
                         'active': bool(d._tf_active),
                         'transform': st.get('defn').transform_id if st.get('defn') else None,
                         'path': result.path if result else None,
                         'output': result.output if result else None}
            elif m['cmd'] == 'binding':
                d._tf_store.set_hotkey(m['tid'], m['binding'])
                d.tfRefreshHotkeys()
                reply = {'ok': True}
            elif m['cmd'] == 'custom':
                row = d._tf_store.add_transform(name='Synthetic checklist', mode='custom', prompt='Return the same words as a checklist.', hotkey={'key_code': 15, 'modifiers': ['control', 'option']})
                d.tfRefreshHotkeys()
                reply = {'tid': row.transform_id}
            elif m['cmd'] == 'quit':
                AppKit.NSApplication.sharedApplication().terminate_(None)
                return
            else:
                raise ValueError('unknown test command')
        except Exception as e:
            reply = {'error': type(e).__name__}
        print('WITNESS ' + json.dumps(reply), flush=True)
    def read():
        for line in sys.stdin:
            AppHelper.callAfter(command, json.loads(line))
    threading.Thread(target=read, daemon=True).start()
    main()


class AppProcess:
    def __init__(self, home):
        env = dict(os.environ, LOCALFLOW_DATA_HOME=str(home), LOCALFLOW_NO_PROMPT='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        self.proc = subprocess.Popen([sys.executable, str(__file__), '--app'], cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.responses = queue.Queue()
        self.diagnostics = []
        def read():
            for line in self.proc.stdout:
                if line.startswith('WITNESS '):
                    self.responses.put(json.loads(line[8:]))
        def errors():
            for line in self.proc.stderr:
                self.diagnostics.append(line)
        threading.Thread(target=read, daemon=True).start()
        threading.Thread(target=errors, daemon=True).start()

    def cmd(self, **m):
        self.proc.stdin.write(json.dumps(m) + '\n')
        self.proc.stdin.flush()
        return self.responses.get(timeout=15)

    def close(self):
        if self.proc.poll() is None:
            self.proc.send_signal(2)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


class OwnedTarget:
    """LaunchServices gives this synthetic helper its launch activation.
    A shell launcher is test plumbing; no compiler or app build runs."""
    def __init__(self, home):
        import plistlib
        self.home = home
        bundle = home / 'OwnedTarget.app'
        mac = bundle / 'Contents/MacOS'
        mac.mkdir(parents=True)
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'local.localflow.owner-polish-target',
            'CFBundleName': 'LocalFlow Owned Target', 'CFBundleExecutable': 'run',
            'CFBundlePackageType': 'APPL', 'LSUIElement': True}))
        self.inpath = home / 'target-in'
        self.outpath = home / 'target-out'
        os.mkfifo(self.inpath)
        os.mkfifo(self.outpath)
        import shlex
        q = shlex.quote
        launcher = mac / 'run'
        target = ROOT / 'tests/v2/insertion/native_insertion_target.py'
        launcher.write_text('#!/bin/zsh\nexec ' + q(sys.executable) + ' ' + q(str(target)) + ' ' + q(json.dumps({'activate': True, 'lifetime': 300})) + ' < ' + q(str(self.inpath)) + ' > ' + q(str(self.outpath)) + '\n')
        launcher.chmod(0o755)
        subprocess.run(['open', '-n', str(bundle)], check=True)
        self.input = self.inpath.open('w')
        self.output = self.outpath.open()
        self.pid = int(self.output.readline().split()[1])
        pump(.4)

    def cmd(self, **m):
        self.input.write(json.dumps(m) + '\n')
        self.input.flush()
        return json.loads(self.output.readline())

    def view(self, name):
        return self.cmd(cmd='state')['views'][name]

    def close(self):
        self.input.close()
        self.output.close()


def run():
    import ApplicationServices as AS
    import Quartz as Q
    from AppKit import NSApplication, NSRunningApplication, NSWorkspace
    NSApplication.sharedApplication().setActivationPolicy_(1)
    if not AS.AXIsProcessTrusted():
        print('NOT RUN: this test process has no Accessibility grant')
        return 2
    sys.path.insert(0, str(ROOT / 'tests/v2/insertion'))
    prior = NSWorkspace.sharedWorkspace().frontmostApplication()
    evidence = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])
    evidence.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='localflow-owner-hotkeys-') as td:
        home = pathlib.Path(td)
        app = AppProcess(home)
        target = None
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                state = app.cmd(cmd='state')
                if state.get('tap') and state.get('engines', {}).get('cleanup') == 'ready':
                    break
                pump(.3)
            else:
                raise AssertionError('source app tap/model not ready: ' + json.dumps(state))
            target = OwnedTarget(home)
            native = NSRunningApplication.runningApplicationWithProcessIdentifier_(target.pid)
            def focused_pid():
                err, focused = AS.AXUIElementCopyAttributeValue(
                    AS.AXUIElementCreateSystemWide(), 'AXFocusedApplication', None)
                if err != 0 or focused is None:
                    return None
                err, pid = AS.AXUIElementGetPid(focused, None)
                return pid if err == 0 else None
            deadline = time.monotonic() + 5
            while focused_pid() != target.pid and time.monotonic() < deadline:
                pump(.05)
            def owned():
                # Fresh system AX focus is the authority; NSWorkspace's
                # cached application object can become a terminated PID -1.
                front = focused_pid()
                assert front == target.pid, f'owned target not frontmost (target={target.pid}, front={front}, active={bool(native and native.isActive())}); no more events authorized'
            def chord(code, flags):
                owned()
                event = Q.CGEventCreateKeyboardEvent(None, code, True)
                Q.CGEventSetFlags(event, flags)
                Q.CGEventPost(Q.kCGHIDEventTap, event)
                pump(.04)
                owned()
                Q.CGEventSetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat, 1)
                Q.CGEventPost(Q.kCGHIDEventTap, event)
                up = Q.CGEventCreateKeyboardEvent(None, code, False)
                Q.CGEventSetFlags(up, flags)
                owned()
                Q.CGEventPost(Q.kCGHIDEventTap, up)
            def attr(el, name):
                err, value = AS.AXUIElementCopyAttributeValue(el, name, None)
                return value if err == 0 else None
            def press_accept():
                owned()
                root = AS.AXUIElementCreateApplication(app.proc.pid)
                pending = list(attr(root, 'AXWindows') or [])
                for _ in range(200):
                    if not pending:
                        break
                    el = pending.pop(0)
                    if attr(el, 'AXRole') == 'AXButton' and attr(el, 'AXTitle') == 'Accept':
                        assert AS.AXUIElementPerformAction(el, 'AXPress') == 0
                        return
                    pending.extend(list(attr(el, 'AXChildren') or []))
                raise AssertionError('native Accept button unavailable')
            def perform(name, tid, code, flags, stale=False):
                text = 'Please review the draft on monday.'
                target.cmd(cmd='focus', view='F1')
                target.cmd(cmd='set', view='F1', text=text, sel=[0, len(text)])
                owned()
                chord(code, flags)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    state = app.cmd(cmd='state')
                    if state.get('visible') and state.get('transform') == tid and not state.get('active'):
                        break
                    pump(.15)
                else:
                    raise AssertionError('global invocation did not produce review: ' + name + ' ' + json.dumps(state))
                assert target.view('F1')['text'] == text, 'shortcut character leaked into owned text'
                owned()
                expected = state['output']
                if stale:
                    target.cmd(cmd='set', view='F1', text='Owned target changed.', sel=[0, 21])
                    expected = 'Owned target changed.'
                press_accept()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    actual = target.view('F1')['text']
                    if actual == expected:
                        break
                    pump(.1)
                assert actual == expected, name
                owned()
                record = {'case': name, 'status': 'pass', 'shortcut_leak': False, 'focus_stolen': False, 'strict_refusal': stale, 'result_path': state['path']}
                records.append(record)
                print(json.dumps(record), flush=True)
            option = Q.kCGEventFlagMaskAlternate
            for tid, code, name in [('builtin:polish', 18, 'HOTKEY-1'), ('builtin:prompt_engineer', 19, 'HOTKEY-2'), ('builtin:concise', 20, 'HOTKEY-3')]:
                perform(name, tid, code, option)
            app.cmd(cmd='binding', tid='builtin:concise', binding={'key_code': 8, 'modifiers': ['control', 'option']})
            target.cmd(cmd='set', view='F1', text='Owned free chord.', sel=[16, 0])
            chord(20, option)
            pump(.3)
            state = app.cmd(cmd='state')
            assert not state['visible'] and not state['active'], 'old default still invokes Concise'
            records.append({'case': 'OLD-DEFAULT-FREED', 'status': 'pass'})
            perform('REBOUND', 'builtin:concise', 8, option | Q.kCGEventFlagMaskControl)
            custom = app.cmd(cmd='custom')['tid']
            perform('CUSTOM', custom, 15, option | Q.kCGEventFlagMaskControl)
            perform('STALE-TARGET', 'builtin:polish', 18, option, stale=True)
        finally:
            if target:
                front = NSWorkspace.sharedWorkspace().frontmostApplication()
                if front and front.processIdentifier() in (target.pid, app.proc.pid):
                    target.cmd(cmd='restore_front', pid=prior.processIdentifier())
                    deadline = time.monotonic() + 3
                    while NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier() == target.pid and time.monotonic() < deadline:
                        pump(.05)
                target.close()
            app.close()
            logs = home / 'Library/Logs/LocalFlow'
            events = []
            if logs.exists():
                for path in logs.glob('*.jsonl'):
                    for line in path.read_text().splitlines():
                        row = json.loads(line)
                        if row['event'].startswith('transforms.') or row['event'].startswith('insertion.'):
                            events.append({k: row.get(k) for k in ('timestamp_utc', 'event', 'outcome', 'reason_code')})
            (evidence / 'source-native-hotkeys.json').write_text(json.dumps({'source_only': True, 'private_pasteboard': True, 'cases': records, 'events': events}, indent=2) + '\n')
            (evidence / 'source-native-stderr.txt').write_text(''.join(app.diagnostics))
    return 0


if __name__ == '__main__':
    if '--app' in sys.argv:
        test_app()
    else:
        raise SystemExit(run())
