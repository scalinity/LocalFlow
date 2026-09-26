"""InsertionResult — the S18 outcome state machine (V2 M08).

States (contracts/targets.md, contracts/insertion.md):

- ``confirmed``         — readback of the owned range in the recorded,
                          readable destination equals the inserted text
                          (never the clipboard: LocalFlow reading its own
                          pasteboard proves nothing about the destination),
                          against a pre-write read of the same region and
                          field length that shows an attributable change —
                          equal bytes alone never confirm, so a stale-AX
                          surface or a no-op write cannot self-confirm.
- ``posted_unverified`` — the insert event was posted but acceptance could
                          not be observed (no readback, or readback
                          disagreed/partial).
- ``target_changed``    — revalidation failed; the artifact was routed to
                          saved history (plus a clipboard copy as the
                          one-action paste offer) instead of inserting.
- ``saved_not_inserted``— no insert attempted by policy (multiline
                          terminal surface, AX not trusted, cancelled).
- ``failed``            — the transaction errored.

A posted event is never a confirmed insertion, and neither state says
anything about correctness (S29.6: a confirmed paste is not a confirmed
transcript).
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .. import ids

STATE_CONFIRMED = "confirmed"
STATE_POSTED_UNVERIFIED = "posted_unverified"
STATE_TARGET_CHANGED = "target_changed"
STATE_SAVED_NOT_INSERTED = "saved_not_inserted"
STATE_FAILED = "failed"

STATES = (STATE_CONFIRMED, STATE_POSTED_UNVERIFIED, STATE_TARGET_CHANGED,
          STATE_SAVED_NOT_INSERTED, STATE_FAILED)

METHOD_AX = "ax_replacement"
METHOD_CLIPBOARD = "clipboard_transaction"
METHOD_NONE = "none"


@dataclasses.dataclass(frozen=True)
class InsertionResult:
    """One insertion transaction's honest outcome. Carries ids, counts,
    ranges and reason codes only — transcript text never travels on the
    result (it lives in the store artifacts and the undo record)."""

    insertion_id: str
    job_id: Optional[str]
    attempt: int = 1
    state: str = STATE_POSTED_UNVERIFIED
    reason_code: Optional[str] = None
    method: str = METHOD_NONE
    verification: dict = dataclasses.field(default_factory=dict)
    owned_start: Optional[int] = None      # host units (UTF-16 on macOS);
                                           # None when not read
    owned_end: Optional[int] = None
    inserted_chars: int = 0
    readback: Optional[str] = None         # match | match_ambiguous |
                                           # partial | mismatch | changed |
                                           # unavailable
    clipboard: dict = dataclasses.field(default_factory=dict)
    target_snapshot_id: Optional[str] = None
    context_snapshot_id: Optional[str] = None
    created_at_utc: str = ""

    def __post_init__(self):
        if self.state not in STATES:
            raise ValueError(f"unknown insertion state {self.state!r}")
        if self.method not in (METHOD_AX, METHOD_CLIPBOARD, METHOD_NONE):
            raise ValueError(f"unknown insertion method {self.method!r}")

    @staticmethod
    def legacy_posted(chars: int) -> "InsertionResult":
        """The V1 baseline semantic (contracts/targets.md): Cmd+V posted,
        target unobservable. Used by the collector's legacy entry point."""
        return InsertionResult(
            insertion_id=ids.new_id("ins"), job_id=None,
            state=STATE_POSTED_UNVERIFIED, reason_code="v1_target_unobservable",
            method=METHOD_CLIPBOARD, inserted_chars=chars,
            readback="unavailable",
            created_at_utc=ids.now_utc_iso())

    def to_envelope_block(self) -> dict:
        """Content-free outcome fields for the evidence envelope. The
        state key stays ``insertion`` — the frozen outcome vocabulary
        (contracts/targets.md) M02's suite pins."""
        return {
            "insertion_id": self.insertion_id,
            "insertion": self.state,
            "reason_code": self.reason_code,
            "method": self.method,
            "attempt": self.attempt,
            "inserted_chars": self.inserted_chars,
            "owned_start": self.owned_start,
            "owned_end": self.owned_end,
            "range_units": "utf16_host",
            "readback": self.readback,
            "verification": dict(self.verification),
            "clipboard": {
                "restored_types": list(
                    self.clipboard.get("restored_types", [])),
                "unsupported_types": list(
                    self.clipboard.get("unsupported_types", [])),
                "restore_skipped_reason":
                    self.clipboard.get("restore_skipped_reason"),
            },
            "target_snapshot_id": self.target_snapshot_id,
            "context_snapshot_id": self.context_snapshot_id,
        }
