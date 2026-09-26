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

The lease also carries the DESTINATION itself: the field element
validation acquired from the target application and proved it owned
(``element``, ``owner_pid``), and that field's window. Every later step
of the operation — the write, the readbacks, undo and observation —
acts on that element, never on whatever holds the focus by then. The
element is an in-memory host object: never compared, printed or
persisted. ``read_allowed`` is the operation's permission to read the
destination's content (the S12 deny/sensitive-field rules), separate
from permission to insert.
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
    # owned-range anchor, host units). None when the surface does not
    # expose it or its content may not be read.
    caret: Optional[int] = None
    verification: dict = dataclasses.field(default_factory=dict)
    # Content-read permission for this destination (S12): False for a
    # denied app, an invalid deny list, a secure/unclassifiable field,
    # or no owned element. Insertion may proceed without it; nothing
    # reads the field, so nothing can be confirmed or observed.
    read_allowed: bool = False
    read_denied_reason: Optional[str] = None
    # Whether validation compared against a recorded destination (a
    # snapshot); without one the insert is on faith and never confirmed.
    destination_recorded: bool = False
    # The bound destination (in memory only).
    owner_pid: Optional[int] = None
    element: Optional[object] = dataclasses.field(
        default=None, compare=False, repr=False)
    window_element: Optional[object] = dataclasses.field(
        default=None, compare=False, repr=False)

    def identity_matches(self, frontmost: Optional[dict]) -> bool:
        from ..context.snapshot import identity_matches
        return identity_matches(self.frontmost_pid, self.frontmost_bundle,
                                frontmost)
