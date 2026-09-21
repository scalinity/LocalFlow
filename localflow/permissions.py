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
