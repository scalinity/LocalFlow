"""TargetLease — insertion authority, granted once, consumed once (S18).

Revalidation grants the lease immediately before writing: the recorded
destination identity must still be the live destination. Cancellation
or a target change revokes authority — an old result carrying a stale
lease (or no lease) is never appended into a target
(contracts/targets.md invariant 1, contracts/jobs.md invariant 3).

The lease is deliberately cheap to re-check: identity is pid/bundle
equality (the M06 ``ContextSnapshot.same_destination`` hook), the field
signature is role/classification plus — for replacement insertions —
the exact selection. Nothing here reads clipboard content or model
state.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

VERIFICATION_PASS = "pass"
VERIFICATION_FAIL = "fail"
VERIFICATION_UNAVAILABLE = "unavailable"
VERIFICATION_NOT_RECORDED = "not_recorded"


@dataclasses.dataclass(frozen=True)
class TargetLease:
    """The authority token one insertion transaction consumes."""

    job_id: Optional[str]
    attempt: int
    target_snapshot_id: Optional[str]
    context_snapshot_id: Optional[str]
    # Identity the insert must land in (the shared M06 rule,
    # snapshot.identity_matches: absent or contradictory never matches).
    frontmost_pid: Optional[int]
    frontmost_bundle: Optional[str]
    # Replacement authority: a non-empty selection recorded at snapshot
    # time may only be replaced while it is still exactly there.
    replace_selection: bool = False
    selected_range: Optional[tuple] = None      # half-open, host AX units
                                                # (UTF-16 on macOS)
    selected_text_sha: Optional[str] = None
    # Field signature for observation continuity and undo binding.
    field_role: Optional[str] = None
    field_classification: Optional[str] = None
    # The caret location observed at validation time (clipboard-path
    # owned-range anchor). None when the surface does not expose it.
    caret: Optional[int] = None
    verification: dict = dataclasses.field(default_factory=dict)

    def identity_matches(self, frontmost: Optional[dict]) -> bool:
        from ..context.snapshot import identity_matches
        return identity_matches(self.frontmost_pid, self.frontmost_bundle,
                                frontmost)
