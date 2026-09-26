"""Target revalidation immediately before insertion (S12/S18, M08 task 1).

This is the M06 ``same_destination`` hook's first real consumer: the
finalized context snapshot's destination identity is compared with the
live frontmost app, and the field/selection signature decides whether
replacement authority is still valid. The settled matrix
(contracts/insertion.md):

- identity (the shared M06 rule ``snapshot.identity_matches`` via
  ``same_destination`` on both a full snapshot and a bare PTT-time
  ``TargetSnapshot``: a usable pid or bundle on both sides, a
  contradiction refused, absence never a match): strict — mismatch ⇒
  target_changed.
- window: the M06 window element (in-memory, compared by host
  identity) when both sides expose it — another window of the same app
  is target_changed even under an equal title; otherwise the window
  title when the snapshot recorded one and it is readable, mismatch ⇒
  target_changed (a different document is not the same destination
  even in the same app); unreadable ⇒ ``unavailable``, identity alone
  governs (plain-dictation contract).
- field classification/role: mismatch ⇒ target_changed. A snapshot
  without field data (denied/unclassifiable/AX off/PTT-identity-only)
  validates on identity alone — insertion proceeds as plain dictation.
- selection: only a NON-EMPTY recorded selection (the replacement
  case) must still match exactly — same range and same text. A moved
  caret never blocks insertion (queued results land in dictation
  order; the user's cursor is the insertion point by design), but a
  vanished or altered selection invalidates replacement authority
  (S12: "if selected text changes... invalidate replacement
  authority").

Validation runs on the insertion thread, budgeted by the host's
messaging timeout — never on the UI callback, never on the hotkey path.
"""

from __future__ import annotations

from typing import Optional

from .. import ids
from ..context.providers import ax_range
from ..context.snapshot import ContextSnapshot, TargetSnapshot
from .hosts import InsertionHost
from .target_lease import (VERIFICATION_FAIL, VERIFICATION_NOT_RECORDED,
                           VERIFICATION_PASS, VERIFICATION_UNAVAILABLE,
                           TargetLease)


def _as_range(rng) -> Optional[tuple]:
    """Half-open (start, end) in the host's AX units — a native AXValue
    CFRange is decoded (UTF-16 units on macOS), never parsed."""
    r = ax_range(rng)
    return None if r is None else (r[0], r[0] + r[1])


def validate_target(host: InsertionHost,
                    snapshot: Optional[ContextSnapshot | TargetSnapshot],
                    job: dict) -> tuple[Optional[TargetLease], dict]:
    """Return ``(lease, verification)`` — lease None means the target
    changed and the artifact must be routed to saved history."""
    verification: dict = {}
    if isinstance(snapshot, TargetSnapshot) and not isinstance(
            snapshot, ContextSnapshot):
        target, field, window_title = snapshot, None, None
        same_fn = snapshot.same_destination
    elif isinstance(snapshot, ContextSnapshot):
        target = snapshot.target
        field = snapshot.field
        window_title = snapshot.window_title
        same_fn = snapshot.same_destination
    else:
        target = field = window_title = same_fn = None
    frontmost = host.frontmost()
    if target is None:
        # No context at all (feature off / identity failed at PTT): no
        # recorded destination to validate against. Insert on faith —
        # the result is posted_unverified and observation is
        # unavailable (unreliable_target). The live caret is still
        # anchored when readable: queued results must land at the
        # cursor, not at a stale zero offset.
        for key in ("identity", "window", "field", "selection"):
            verification[key] = VERIFICATION_NOT_RECORDED
        caret = None
        el = host.focused_element()
        if el is not None:
            rng = _as_range(host.attribute(el, "AXSelectedTextRange"))
            caret = rng[0] if rng is not None else None
        return TargetLease(
            job_id=job.get("job_id"), attempt=int(job.get("attempt", 1)),
            target_snapshot_id=None, context_snapshot_id=None,
            frontmost_pid=frontmost.get("pid") if frontmost else None,
            frontmost_bundle=frontmost.get("bundle") if frontmost else None,
            caret=caret, verification=verification), verification
    same = same_fn(frontmost)
    verification["identity"] = VERIFICATION_PASS if same else VERIFICATION_FAIL
    if not same:
        # No further reads: the destination is wrong and nothing about
        # the field can repair that.
        for key in ("window", "field", "selection"):
            verification[key] = VERIFICATION_UNAVAILABLE
        return None, verification

    el = host.focused_element()
    # The M06 window identity (an in-memory host element; equal titles
    # are not unique): when both sides expose it, it decides — a
    # different window of the same app is a changed target; a moved
    # caret or another field of the SAME window is not.
    recorded_win = getattr(snapshot, "window_element", None) \
        if isinstance(snapshot, ContextSnapshot) else None
    live_win = host.attribute(el, "AXWindow") \
        if recorded_win is not None and el is not None else None
    if live_win is not None:
        verification["window"] = (VERIFICATION_PASS
                                  if live_win == recorded_win
                                  else VERIFICATION_FAIL)
    elif window_title is None:
        verification["window"] = VERIFICATION_NOT_RECORDED
    elif el is None:
        verification["window"] = VERIFICATION_UNAVAILABLE
    else:
        # The real AX API hangs AXFocusedWindow off the APPLICATION
        # element; the system host resolves it there, the fixture
        # answers on the field element — prefer the host method when it
        # exists.
        title_fn = getattr(host, "focused_window_title", None)
        if title_fn is not None:
            title = title_fn(el)
        else:
            win = host.attribute(el, "AXFocusedWindow")
            title = None
            if win is not None:
                t = host.attribute(win, "AXTitle")
                title = str(t) if t else None
        verification["window"] = (
            VERIFICATION_UNAVAILABLE if title is None
            else (VERIFICATION_PASS if title == window_title
                  else VERIFICATION_FAIL))
    if verification["window"] == VERIFICATION_FAIL:
        verification["field"] = VERIFICATION_UNAVAILABLE
        verification["selection"] = VERIFICATION_UNAVAILABLE
        return None, verification

    if el is None:
        verification["field"] = VERIFICATION_UNAVAILABLE
        verification["selection"] = VERIFICATION_UNAVAILABLE
        return TargetLease(
            job_id=job.get("job_id"), attempt=int(job.get("attempt", 1)),
            target_snapshot_id=target.target_snapshot_id,
            context_snapshot_id=(snapshot.context_snapshot_id
                                 if isinstance(snapshot, ContextSnapshot)
                                 else None),
            frontmost_pid=target.app_pid, frontmost_bundle=target.app_bundle,
            field_role=field.role if field else None,
            field_classification=field.classification if field else None,
            verification=verification), verification

    role = host.attribute(el, "AXRole")
    role = str(role) if role else None
    if field is None:
        verification["field"] = VERIFICATION_NOT_RECORDED
    elif role is None:
        # A transient AX hiccup (busy app, messaging timeout) degrades
        # like the window check: unavailable, identity alone governs —
        # an unreadable role is not evidence the field changed.
        verification["field"] = VERIFICATION_UNAVAILABLE
    else:
        ok = role == field.role if field.role else True
        verification["field"] = VERIFICATION_PASS if ok else VERIFICATION_FAIL
    if verification["field"] == VERIFICATION_FAIL:
        verification["selection"] = VERIFICATION_UNAVAILABLE
        return None, verification

    # Selection authority: only a recorded NON-EMPTY selection must
    # still exist exactly as recorded (replacement case). A caret
    # (empty range) moves freely — the caret is the insertion point.
    selected_range = _as_range(host.attribute(el, "AXSelectedTextRange"))
    caret = selected_range[0] if selected_range is not None else None
    # Host units on both sides: the native selection (UTF-16 on macOS)
    # when the snapshot recorded one, else the fixture's own range.
    snap_range = ((field.selected_range_utf16 or field.selected_range)
                  if field else None)
    replace_selection = bool(snap_range and snap_range[1] > snap_range[0])
    if not replace_selection:
        verification["selection"] = (
            VERIFICATION_PASS if selected_range is not None
            else VERIFICATION_UNAVAILABLE)
    elif selected_range is None:
        verification["selection"] = VERIFICATION_UNAVAILABLE
    else:
        sel_text = host.string_for_range(
            el, selected_range[0], selected_range[1] - selected_range[0])
        if sel_text is None:
            verification["selection"] = VERIFICATION_UNAVAILABLE
        else:
            same_range = tuple(selected_range) == tuple(snap_range)
            same_text = sel_text == (field.selected_text or "")
            verification["selection"] = (
                VERIFICATION_PASS if same_range and same_text
                else VERIFICATION_FAIL)
    if verification["selection"] == VERIFICATION_FAIL:
        return None, verification
    return TargetLease(
        job_id=job.get("job_id"), attempt=int(job.get("attempt", 1)),
        target_snapshot_id=target.target_snapshot_id,
        context_snapshot_id=(snapshot.context_snapshot_id
                             if isinstance(snapshot, ContextSnapshot)
                             else None),
        frontmost_pid=target.app_pid, frontmost_bundle=target.app_bundle,
        replace_selection=replace_selection,
        selected_range=tuple(snap_range) if snap_range else None,
        selected_text_sha=(ids.sha256_text(field.selected_text or "")
                           if replace_selection and field else None),
        field_role=field.role if field else None,
        field_classification=field.classification if field else None,
        caret=caret, verification=verification), verification
