"""Shared action plumbing for the companion's surfaces."""

from __future__ import annotations

import threading

from PyObjCTools import AppHelper



def refusal_text(e):
    """A service refusal's content-free reason, or None. Raised inside a
    writer op it arrives as the store's ``RuntimeError('ValueError: …')``
    (the AppKit Hub's rule, hub.py ``_refusal_text``)."""
    msg = str(e)
    if isinstance(e, ValueError):
        return msg
    if isinstance(e, RuntimeError) and msg.startswith("ValueError: "):
        return msg[len("ValueError: "):]
    return None


class OpIds:
    """Operation ids per logical action (M14-AUDIT-17): the same action on
    the same target and payload reuses its id until a KNOWN outcome
    retires it, so repeating an action whose outcome was unknown
    reconciles instead of acting twice. One pending id per kind, as in
    the AppKit Hub; the unknown flag is per call, not shared."""

    def __init__(self):
        self._pending = {}

    def get(self, kind, key):
        from .... import ids
        cur = self._pending.get(kind)
        if cur is not None and cur[0] == key:
            return cur[1]
        op = ids.new_id("op")
        self._pending[kind] = (key, op)
        return op

    def settled(self, kind, unknown):
        if not unknown:
            self._pending.pop(kind, None)

    def forget(self, kind):
        self._pending.pop(kind, None)


class Background:
    """Long actions (export, mining, Your Voice generation, redacted
    diagnostics export) run off the main thread and report back on it.
    Each carries a key and a token: a completion reports as current only
    while it is the newest action of its key."""

    def __init__(self):
        self._seq = 0
        self._tokens = {}

    def run(self, key, work, done):
        self._seq += 1
        token = self._seq
        self._tokens[key] = token

        def body():
            out, err = None, None
            try:
                out = work()
            except BaseException as e:  # reported, never raised off-thread
                err = e
            AppHelper.callAfter(
                lambda: done(out, err, self._tokens.get(key) == token))
        threading.Thread(target=body, name="localflow-hub-work",
                         daemon=True).start()
        return token

    def supersede(self, key):
        self._tokens.pop(key, None)
