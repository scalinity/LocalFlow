"""Serialized clipboard transaction with ownership generations (S18).

The transaction runs entirely on the insertion thread — never the UI
callback. Mechanics:

1. ``capture`` records the pasteboard change count (generation 0) plus
   every supported representation's data; unsupported types (file
   promises, exotic flavors) are reported, never claimed.
2. ``publish`` writes the transcript; the new change count is
   LocalFlow's owned generation.
3. After the paste settles, ``restore_if_owned`` re-checks the count:
   still ours → restore the captured representations; anyone else's
   (a user copy always wins) → skip with the reason recorded.

The settle wait is a bounded constant on this thread, not the V1
fixed 0.05 s sleep on the caller (which was the UI thread); the
benchmark reports it separately from target verification.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Callable, Optional

from .hosts import (SUPPORTED_PASTEBOARD_TYPES, PasteboardHost)

# How long the queue thread waits for the target to read the pasteboard
# before restoring (the V1 production value, now off the UI thread). A
# target that reads later than this bound is the documented residual
# risk of unobservable surfaces — such results stay posted_unverified
# and are never confirmed.
PASTE_SETTLE_SEC = 0.6


@dataclasses.dataclass
class ClipboardCapture:
    generation: int
    items: list                      # [(type, data), ...] restorable pairs
    unsupported_types: list          # reported, not restored, not claimed


class ClipboardTransaction:
    def __init__(self, pasteboard: PasteboardHost,
                 settle_sec: float = PASTE_SETTLE_SEC,
                 sleep: Callable[[float], None] = time.sleep):
        self.pb = pasteboard
        self.settle_sec = settle_sec
        self._sleep = sleep
        self.captured: Optional[ClipboardCapture] = None
        self.published_generation: Optional[int] = None
        self.restored_generation: Optional[int] = None
        self.restore_skipped_reason: Optional[str] = None

    def capture(self) -> ClipboardCapture:
        gen = self.pb.change_count()
        items, unsupported = [], []
        for ptype in self.pb.types():
            if str(ptype) not in SUPPORTED_PASTEBOARD_TYPES:
                unsupported.append(str(ptype))
                continue
            data = self.pb.data_for_type(ptype)
            if data is None:
                unsupported.append(str(ptype))
            else:
                items.append((str(ptype), data))
        self.captured = ClipboardCapture(gen, items, unsupported)
        return self.captured

    def publish(self, text: str) -> int:
        """Write the transcript and record the owned generation."""
        self.published_generation = self.pb.clear_and_write_text(text)
        return self.published_generation

    def wait_for_target(self):
        self._sleep(self.settle_sec)

    def restore_if_owned(self) -> bool:
        """Restore the pre-transaction clipboard only if the pasteboard
        still holds LocalFlow's owned generation (S18: a user copy
        always wins). Returns whether a restore happened. When nothing
        restorable was captured the board is still cleared of the
        transcript — a leftover dictation would duplicate on the user's
        next manual ⌘V; the loss is disclosed via unsupported_types."""
        if self.captured is None or self.published_generation is None:
            return False
        current = self.pb.change_count()
        if current != self.published_generation:
            # Someone else (a user copy, another app) took ownership
            # during the window — their content stays untouched.
            self.restore_skipped_reason = "user_copy_won"
            return False
        # One pasteboard item carrying every captured flavor — an
        # app's copy usually exposes text/rtf/html as flavors of one
        # item, and splitting them would break flavor grouping.
        self.restored_generation = self.pb.clear_and_write_items(
            [self.captured.items])
        return True
