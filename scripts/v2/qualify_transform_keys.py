"""Actual session event delivery into a disposable native text target.

Only synthetic content is used. The target counts Return events and writes.
This proves session-tap suppression, not compatibility with every real app.
"""
import argparse
import json
import os
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import objc
import Quartz as Q
from AppKit import (NSApplication, NSApplicationActivationPolicyRegular,
    NSWindow, NSTextView, NSMakeRect, NSWorkspace, NSRunningApplication)
from PyObjCTools import AppHelper
from localflow.transform_hotkey import TransformHotkeyListener
from localflow.v2.transforms.focus_scope import FocusScope

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=pathlib.Path, required=True)
args = parser.parse_args()
import plistlib
import subprocess
build = args.output.resolve().parent / 'keyboard-target'
bundle = build / 'LocalFlow Keyboard Qualification.app'
contents = bundle / 'Contents'
(contents / 'MacOS').mkdir(parents=True, exist_ok=True)
source = pathlib.Path(__file__).resolve().parents[2] / 'tests/v2/transforms/native_key_target.m'
executable = contents / 'MacOS/keyboard-target'
subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Cocoa',str(source),'-o',str(executable)], check=True, capture_output=True)
(contents/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'keyboard-target',
    'CFBundleIdentifier':'com.localflow.keyboardqualification','CFBundleName':'LocalFlow Keyboard Qualification',
    'CFBundlePackageType':'APPL'}))
state_path = build/'state.json';command_path = build/'command.json'
for path in (state_path,command_path):
    path.unlink(missing_ok=True)
previous = NSWorkspace.sharedWorkspace().frontmostApplication()
report = {'return_events':0,'writes':0,'actions':[],'tap':[],'cases':[]}
subprocess.run(['open','-n',str(bundle),'--args',str(state_path),str(command_path)],check=True)

def state():
    return json.loads(state_path.read_text()) if state_path.exists() else {}

def command(action, operation, **kwargs):
    temp=command_path.with_suffix('.tmp')
    temp.write_text(json.dumps({'action':action,'operation':operation,**kwargs}));temp.replace(command_path)

listener = TransformHotkeyListener(lambda _: None, lambda *x: report['tap'].append(x))


def action(kind, token):
    report['actions'].append([kind, token])
    if kind == 'accept' and listener.review.claim(token):
        report['writes'] += 1
        command('replace', token, text='A synthetic transformed prompt')
    elif kind == 'dismiss':
        listener.review.disarm()


listener.review_callback = action


def post(code, down, repeat=False):
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None or front.processIdentifier() != state().get('pid'):
        raise RuntimeError('Synthetic key refused: disposable target is not frontmost')
    event = Q.CGEventCreateKeyboardEvent(None, code, down)
    Q.CGEventSetFlags(event, 0)
    if repeat:
        Q.CGEventSetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat, 1)
    Q.CGEventPost(Q.kCGHIDEventTap, event)


def start():
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    report['target_pid'] = state().get('pid')
    report['front_pid'] = front.processIdentifier() if front else None
    if report['target_pid'] is None or report['front_pid'] != report['target_pid']:
        finish('BLOCKED: disposable native target does not own foreground')
        return
    if not listener.start():
        finish('BLOCKED: event tap unavailable')
        return
    listener.review_scope = FocusScope(report['target_pid'], lambda: None)
    if not listener.review_scope.start():
        finish('BLOCKED: exact native focus observation unavailable: ' + str(listener.review_scope.reason))
        return
    listener.review.arm('return', report['target_pid'], ready=True, enabled=True)
    post(36, True)
    AppHelper.callLater(.15, repeat)


def repeat():
    post(36, True, True)
    post(36, True, True)
    post(36, False)
    AppHelper.callLater(.15, keypad)


def keypad():
    report['cases'].append({'case': 'return_held_after_apply', 'writes': report['writes'], 'leaks': report['return_events']})
    listener.review.arm('keypad', report['target_pid'], ready=True, enabled=True)
    post(76, True)
    AppHelper.callLater(.1, lambda: post(76, False))
    AppHelper.callLater(.25, disabled)


def disabled():
    report['cases'].append({'case': 'keypad_enter', 'writes': report['writes'], 'leaks': report['return_events']})
    listener.review.arm('disabled', report['target_pid'], ready=True, enabled=False)
    post(36, True)
    AppHelper.callLater(.1, lambda: post(36, False))
    AppHelper.callLater(.25, escape)


def escape():
    listener.review.arm('escape', report['target_pid'], ready=True, enabled=True)
    post(53, True)
    AppHelper.callLater(.1, lambda: post(53, False))
    AppHelper.callLater(.3, finish)


def finish(blocked=None):
    if listener.review_scope is not None:
        listener.review_scope.stop()
    listener.stop()
    report.update(state())
    report['verdict'] = blocked or ('PASS' if report['writes'] == 2 and report['return_events'] == 0
        and ['unavailable', 'disabled'] in report['actions'] and ['dismiss', 'escape'] in report['actions'] else 'FAIL')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    command('quit', 'quit')
    if previous:
        previous.activateWithOptions_(3)
    AppHelper.stopEventLoop()


AppHelper.callLater(.5, start)
try:
    AppHelper.runConsoleEventLoop()
except Exception as error:
    # A foreground guard can fail in a scheduled callback. Still tear down
    # the owned native target and publish the refusal instead of leaking it.
    finish('BLOCKED: ' + str(error))
