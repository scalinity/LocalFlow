"""Safe insertion, clipboard transactions and recovery undo (V2 M08).

Spec S18 (contracts/insertion.md): finished text lands only in the
intended field, never overwrites a new user clipboard copy, and every
insertion carries an honest InsertionResult state. ``InsertionService``
owns the single serialized transaction queue; ``validate_target`` is
the M06 ``same_destination`` hook's first consumer; the S29.8 bounded
outcome observation begins here, not in M14.
"""

from .result import (METHOD_AX, METHOD_CLIPBOARD, METHOD_NONE,
                     STATE_CONFIRMED, STATE_FAILED,
                     STATE_POSTED_UNVERIFIED, STATE_SAVED_NOT_INSERTED,
                     STATE_TARGET_CHANGED, InsertionResult)
from .service import InsertionService
from .target_lease import TargetLease
from .validation import validate_target

__all__ = [
    "InsertionResult", "TargetLease", "validate_target",
    "InsertionService",
    "STATE_CONFIRMED", "STATE_POSTED_UNVERIFIED", "STATE_TARGET_CHANGED",
    "STATE_SAVED_NOT_INSERTED", "STATE_FAILED",
    "METHOD_AX", "METHOD_CLIPBOARD", "METHOD_NONE",
]
