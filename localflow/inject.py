"""Insert text into the frontmost app via pasteboard + synthetic Cmd+V."""

import threading
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString
from ApplicationServices import AXIsProcessTrusted

KEY_V = 9  # ANSI 'V'


def _set_clipboard(text: str):
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def copy_text(text: str) -> bool:
    """Leave text on the clipboard for a manual insert (M03 recovery
    action: raw-export of a failed dictation). No synthetic keystroke."""
    _set_clipboard(text)
    return True


def paste_text(text: str, restore_clipboard: bool = True) -> bool:
    """Paste text at the cursor. Returns True if the Cmd+V was posted.

    Without Accessibility trust the synthetic keystroke would be silently
    dropped, so instead the transcript is left on the clipboard for a
    manual ⌘V and False is returned.
    """
    if not AXIsProcessTrusted():
        _set_clipboard(text)
        print(
            "[localflow] cannot auto-paste: Accessibility is not granted to this "
            "app. Transcript left on the clipboard — press ⌘V to insert it. "
            "Enable LocalFlow under System Settings → Privacy & Security → "
            "Accessibility, then quit and reopen the app."
        )
        return False

    pb = NSPasteboard.generalPasteboard()
    old = pb.stringForType_(NSPasteboardTypeString) if restore_clipboard else None

    _set_clipboard(text)
    time.sleep(0.05)  # let the pasteboard settle before the paste lands

    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    down = Quartz.CGEventCreateKeyboardEvent(src, KEY_V, True)
    up = Quartz.CGEventCreateKeyboardEvent(src, KEY_V, False)
    Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    if old is not None:

        def _restore():
            # Give the target app time to read the pasteboard first
            time.sleep(0.6)
            pb2 = NSPasteboard.generalPasteboard()
            pb2.clearContents()
            pb2.setString_forType_(old, NSPasteboardTypeString)

        threading.Thread(target=_restore, daemon=True).start()
    return True
