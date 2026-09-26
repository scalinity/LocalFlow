"""Synthetic native insertion target for M08 qualification (a subprocess).

Two windows of this helper's own with EQUAL titles: W1 holds a text view
(F1), a plain text field (TF) and a secure field (SF); W2 holds a text
view (F2). Synthetic text only. The app uses the accessory activation
policy and its windows are ordered front WITHOUT activating
(``orderFrontRegardless``) and placed off-screen, so the user's keyboard
focus and frontmost application never change. Probes reach it only
through ``AXUIElementCreateApplication(<this pid>)``.

Line protocol on stdin/stdout: one JSON object per line in, one JSON
reply per line out (after the first line, ``READY <pid>``).

    {"cmd": "state"}                     -> {"views": {name: {text, sel}}}
         (read from AppKit — the independent witness, never AX)
    {"cmd": "focus", "view": "F2"}       -> key window + first responder
    {"cmd": "set", "view", "text", "sel": [loc, len]}
    {"cmd": "select", "view", "sel": [loc, len]}
    {"cmd": "title", "window": "W1", "title": str}
    {"cmd": "consume_paste", "pasteboard": name}
         -> the emulated ⌘V consumer: reads the NAMED pasteboard's string
            now and inserts it into the current first responder
    {"cmd": "quit"}

Exits when stdin closes, on quit, or after 60 s.
"""

import json
import os
import sys
import threading

from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                    NSBackingStoreBuffered, NSMakeRect, NSPasteboard,
                    NSPasteboardTypeString, NSSecureTextField, NSTextField,
                    NSTextView, NSWindow)
from Foundation import NSNotFound
from PyObjCTools import AppHelper

SPEC = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
TITLE = SPEC.get("title", "LF-M08 synthetic window")

app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)


def _window(y, title):
    w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(-20000, y, 320, 140), 1, NSBackingStoreBuffered, False)
    w.setTitle_(title)
    return w


W = {"W1": _window(-20000, SPEC.get("title_w1", TITLE)),
     "W2": _window(-19800, SPEC.get("title_w2", TITLE))}
V = {}
V["F1"] = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 80, 320, 60))
V["TF"] = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 50, 320, 24))
V["SF"] = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 20, 320, 24))
V["F2"] = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 80, 320, 60))
WINDOW_OF = {"F1": "W1", "TF": "W1", "SF": "W1", "F2": "W2"}
V["F1"].setString_(SPEC.get("f1", "synthetic one"))
V["F2"].setString_(SPEC.get("f2", "synthetic two"))
V["TF"].setStringValue_("synthetic field")
V["SF"].setStringValue_("CANARY_SECURE_NATIVE")
for name, view in V.items():
    W[WINDOW_OF[name]].contentView().addSubview_(view)
W["W2"].orderFrontRegardless()
W["W1"].orderFrontRegardless()
W["W1"].makeKeyWindow()
W["W1"].makeFirstResponder_(V["F1"])
CURRENT = {"view": "F1"}


def _state():
    out = {}
    for name, v in V.items():
        if isinstance(v, NSTextView):
            r = v.selectedRange()
            out[name] = {"text": str(v.string()),
                         "sel": [int(r.location), int(r.length)]}
        elif name == "SF":
            out[name] = {"length": len(str(v.stringValue()))}
        else:
            out[name] = {"text": str(v.stringValue())}
    key = app.keyWindow()
    out["_key_window"] = next((k for k, w in W.items() if w == key), None)
    out["_current"] = CURRENT["view"]
    return out


def _handle(msg):
    cmd = msg.get("cmd")
    if cmd == "state":
        return {"ok": True, "views": _state()}
    if cmd == "focus":
        name = msg["view"]
        win = W[WINDOW_OF[name]]
        win.orderFrontRegardless()
        win.makeKeyWindow()
        ok = bool(win.makeFirstResponder_(V[name]))
        CURRENT["view"] = name
        return {"ok": ok}
    if cmd == "set":
        v = V[msg["view"]]
        v.setString_(msg["text"])
        loc, ln = msg.get("sel", [len(msg["text"]), 0])
        v.setSelectedRange_((int(loc), int(ln)))
        return {"ok": True}
    if cmd == "select":
        loc, ln = msg["sel"]
        V[msg["view"]].setSelectedRange_((int(loc), int(ln)))
        return {"ok": True}
    if cmd == "title":
        W[msg["window"]].setTitle_(msg["title"])
        return {"ok": True}
    if cmd == "consume_paste":
        pb = NSPasteboard.pasteboardWithName_(msg["pasteboard"])
        s = pb.stringForType_(NSPasteboardTypeString)
        view = V[CURRENT["view"]]
        if s is None:
            return {"ok": True, "consumed": None}
        if isinstance(view, NSTextView):
            view.insertText_replacementRange_(s, (NSNotFound, 0))
        return {"ok": True, "consumed": str(s)}
    if cmd == "quit":
        AppHelper.callAfter(app.terminate_, None)
        return {"ok": True}
    return {"ok": False, "error": f"unknown command {cmd!r}"}


def _serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        box, done = {}, threading.Event()

        def run(m=json.loads(line)):
            try:
                box["r"] = _handle(m)
            except Exception as e:   # reported, never raised
                box["r"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            done.set()
        AppHelper.callAfter(run)
        done.wait(10)
        print(json.dumps(box.get("r", {"ok": False, "error": "timeout"})),
              flush=True)
    AppHelper.callAfter(app.terminate_, None)


print(f"READY {os.getpid()}", flush=True)
threading.Thread(target=_serve, daemon=True).start()
threading.Timer(60.0, lambda: os._exit(0)).start()
AppHelper.runEventLoop()
