"""A candidate-scoped keyboard lease; no AX, I/O or model work here.

The physical-press latch deliberately outlives the visible review. Hiding
the panel after acceptance must not release a held Return into the target.
"""
from __future__ import annotations

import time

RETURN_KEYS = frozenset((36, 76))
ESCAPE = 53


class ReviewKeyLease:
    def __init__(self, dispatch, clock=time.monotonic):
        self.dispatch = dispatch
        self.clock = clock
        self.lease = None
        self.physical = set()
        self.consumed = set()
        self.claimed = set()

    def arm(self, token, pid, *, ready=False, enabled=False, ttl=300,
            internal_editor=False):
        self.lease = dict(token=token, pid=pid, ready=ready,
                          enabled=enabled, expires=self.clock() + ttl,
                          internal_editor=bool(internal_editor))

    def disarm(self):
        self.lease = None

    def reconcile_held(self, held):
        """After a tap gap, retire releases missed while preserving held presses."""
        self.physical = set(held)
        self.consumed.intersection_update(self.physical)

    def claim(self, token):
        """Shared by mouse and keyboard, on the coordinator thread."""
        lease = self.lease
        if not lease or lease['token'] != token or not lease['ready'] \
                or not lease['enabled'] or token in self.claimed \
                or self.clock() >= lease['expires']:
            return False
        self.claimed.add(token)
        # Keep bounded, while retaining the most recent idempotency token.
        if len(self.claimed) > 256:
            self.claimed = {token}
        self.disarm()
        return True

    def handle(self, kind, code, modifiers=(), repeat=False, *,
               pid=None, eligible=True):
        if code not in RETURN_KEYS and code != ESCAPE:
            return False
        was_down = code in self.physical
        if kind == 'up':
            self.physical.discard(code)
            if code in self.consumed:
                self.consumed.discard(code)
                return True
            return False
        self.physical.add(code)
        if code in self.consumed:
            return True
        lease = self.lease
        if not lease:
            return False
        if pid != lease['pid']:
            self.disarm()
            return False
        # IME composition and modified keys retain their ordinary meaning,
        # including while a timeout callback is waiting on the main loop.
        if modifiers or not eligible:
            return False
        if self.clock() >= lease['expires']:
            # The visible preview may not have received its timeout callback
            # yet. Consume this last press while scheduling its dismissal.
            self.consumed.add(code)
            self.disarm()
            self.dispatch('expired', lease['token'])
            return True
        # LocalFlow menus/composers and IME composition own their keys.
        self.consumed.add(code)
        if repeat or was_down:
            return True  # a key held before this lease cannot accept
        action = ('dismiss' if code == ESCAPE else
                  'accept' if lease['ready'] and lease['enabled'] else
                  'unavailable' if lease['ready'] else 'working')
        self.dispatch(action, lease['token'])
        return True
