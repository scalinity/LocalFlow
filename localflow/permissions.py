"""macOS permission checks (Accessibility / Input Monitoring)."""

import Quartz
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt


def ensure_permissions(prompt: bool = True) -> dict:
    """Check (and optionally prompt for) the permissions the app needs.

    Accessibility: global hotkey monitoring + synthetic Cmd+V.
    Input Monitoring: some macOS versions gate global key monitors on this.
    Microphone is prompted automatically by the system on first recording.
    """
    trusted = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt})

    listen = Quartz.CGPreflightListenEventAccess()
    if not listen and prompt:
        Quartz.CGRequestListenEventAccess()

    return {"accessibility": bool(trusted), "input_monitoring": bool(listen)}


class KeyboardAccess:
    """Start global input only after this app's native identity is trusted.

    In particular, an untrusted app must not record from a partial modifier
    stream while its transform chord is being typed into the destination.
    The coordinator refreshes this on its existing timer after OS grants.
    """
    def __init__(self, dictation_listeners, transforms):
        self.dictation_listeners = dictation_listeners
        self.transforms = transforms
        self.dictation_active = False
        self.transforms_active = False

    def refresh(self, permissions):
        before = (self.dictation_active, self.transforms_active)
        allowed = permissions.get("accessibility") is True and \
            permissions.get("input_monitoring") is True
        if not allowed:
            if self.dictation_active:
                for listener in self.dictation_listeners:
                    listener.stop()
                    listener.held = False
            self.transforms.stop()
            self.dictation_active = self.transforms_active = False
        else:
            if not self.dictation_active:
                for listener in self.dictation_listeners:
                    listener.start()
                self.dictation_active = True
            self.transforms_active = bool(self.transforms.start())
        return before != (self.dictation_active, self.transforms_active)
