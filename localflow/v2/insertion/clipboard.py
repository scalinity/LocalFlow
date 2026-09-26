"""Serialized clipboard transaction with ownership generations (S18).

The transaction runs entirely on the insertion thread — never the UI
callback. Mechanics:

1. ``capture`` records the pasteboard change count (generation 0) plus
   every supported representation's data; unsupported types (file
   promises, exotic flavors) are reported, never claimed. The count is
   read again after the data: a copy that landed mid-capture makes the
   snapshot mixed, so the capture is retried (bounded); a board still
   changing is a ``conflict`` — the caller must not publish over it.
2. ``publish`` writes the transcript; the new change count is
   LocalFlow's owned generation. A refused write (the adapter returns
   None) leaves no owned generation, only the cleared board's count —
   nothing LocalFlow wrote is there to paste.
3. After the paste settles, ``restore_if_owned`` re-checks the count:
   still ours → restore the captured representations; anyone else's
   (a user copy always wins) → skip with the reason recorded. A refused
   restore write is disclosed (``restore_failed``), never claimed.

Generation checks are not an atomic compare-and-swap: a copy landing
between a check and the following write is the documented residual.

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
# A capture re-reads the board when a copy landed during it; after this
# many attempts a still-changing board is a conflict.
CAPTURE_ATTEMPTS = 3


@dataclasses.dataclass
class ClipboardCapture:
    generation: int
    items: list                      # [(type, data), ...] restorable pairs
    unsupported_types: list          # reported, not restored, not claimed
    conflict: bool = False           # no consistent snapshot was possible


class ClipboardTransaction:
    def __init__(self, pasteboard: PasteboardHost,
                 settle_sec: float = PASTE_SETTLE_SEC,
                 sleep: Callable[[float], None] = time.sleep):
        self.pb = pasteboard
        self.settle_sec = settle_sec
        self._sleep = sleep
        self.captured: Optional[ClipboardCapture] = None
        self.published_generation: Optional[int] = None
        # The count after a refused publication (the board was cleared
        # by LocalFlow but holds nothing of it).
        self.cleared_generation: Optional[int] = None
        self.publish_failed = False
        self.restored_generation: Optional[int] = None
        self.restore_skipped_reason: Optional[str] = None

    def capture(self) -> ClipboardCapture:
        for _ in range(CAPTURE_ATTEMPTS):
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
            if self.pb.change_count() == gen:
                self.captured = ClipboardCapture(gen, items, unsupported)
                return self.captured
        self.captured = ClipboardCapture(self.pb.change_count(), [], [],
                                         conflict=True)
        return self.captured

    def publish(self, text: str) -> Optional[int]:
        """Write the transcript and record the owned generation (None
        when the pasteboard refused the write)."""
        self.published_generation = self.pb.clear_and_write_text(text)
        if self.published_generation is None:
            self.publish_failed = True
            self.cleared_generation = self.pb.change_count()
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
        owned = (self.published_generation
                 if self.published_generation is not None
                 else self.cleared_generation)
        if self.captured is None or owned is None:
            return False
        current = self.pb.change_count()
        if current != owned:
            # Someone else (a user copy, another app) took ownership
            # during the window — their content stays untouched.
            self.restore_skipped_reason = "user_copy_won"
            return False
        # One pasteboard item carrying every captured flavor — an
        # app's copy usually exposes text/rtf/html as flavors of one
        # item, and splitting them would break flavor grouping.
        self.restored_generation = self.pb.clear_and_write_items(
            [self.captured.items])
        if self.restored_generation is None:
            self.restore_skipped_reason = "restore_failed"
            return False
        return True
