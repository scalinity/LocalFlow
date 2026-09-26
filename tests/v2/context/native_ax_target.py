"""Synthetic native AX target for M06 qualification (run as a subprocess).

One small window of this helper's own, holding synthetic text only: a
text view, a plain text field and a secure field. The app uses the
accessory activation policy and the window is ordered front WITHOUT
activating (``orderFrontRegardless``) and placed off-screen, so the
user's keyboard focus and frontmost application never change. Probes
reach it through ``AXUIElementCreateApplication(<this pid>)`` — never
through the system-wide focused element.

    python native_ax_target.py '<json spec>'
      spec: {"text": str, "selection": [loc, len] (UTF-16 units),
             "first_responder": "textview"|"field"|"secure"}

Prints ``READY <pid>`` and exits when stdin closes (or after 30 s).
"""

import json
import os
import sys
import threading

from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                    NSBackingStoreBuffered, NSMakeRect, NSSecureTextField,
                    NSTextField, NSTextView, NSWindow)
from PyObjCTools import AppHelper

SPEC = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
TEXT = SPEC.get("text", "synthetic text")
SEL = SPEC.get("selection", [0, 0])
FIRST = SPEC.get("first_responder", "textview")
TITLE = SPEC.get("title", "LF-M06 synthetic window")

app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    NSMakeRect(-20000, -20000, 320, 120), 1, NSBackingStoreBuffered, False)
win.setTitle_(TITLE)
tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 60, 320, 60))
tv.setString_(TEXT)
tv.setSelectedRange_((int(SEL[0]), int(SEL[1])))
tf = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 30, 320, 24))
tf.setStringValue_("synthetic field")
sf = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 320, 24))
sf.setStringValue_("CANARY_SECURE_NATIVE")
for v in (tv, tf, sf):
    win.contentView().addSubview_(v)
win.makeFirstResponder_({"textview": tv, "field": tf,
                         "secure": sf}.get(FIRST, tv))
win.orderFrontRegardless()
print(f"READY {os.getpid()}", flush=True)


def _stop():
    sys.stdin.read()
    AppHelper.callAfter(app.terminate_, None)


threading.Thread(target=_stop, daemon=True).start()
threading.Timer(30.0, lambda: os._exit(0)).start()
AppHelper.runEventLoop()
