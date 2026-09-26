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
- destination: ONE element, the focused element of the live frontmost
  application's own element (``focused_element_for(pid)``), accepted
  only when ``element_pid`` names that application — never whatever
  holds the system focus. A foreign owner ⇒ target_changed
  (``destination_unverified``). The element rides the lease: every
  later write, readback, undo and observation acts on it.
- classification BEFORE any content read (S12): role and subrole of
  that element. Content may be read only for a classifiable text field
  in an app that is not denied (the normalized M06 deny decision; an
  invalid deny list denies every app) — ``read_allowed``. A denied app
  gets the documented minimum only (ownership, window identity,
  settability): no title, role, range or text read. Insertion itself
  stays available without reads; it can then never be confirmed.
- window: the M06 window element (in-memory, compared by host
  identity) when both sides expose it — another window of the same app
  is target_changed even under an equal title; the window title check
  also applies when the snapshot recorded one and it is readable
  (tabs share one window element). The two verdicts are kept apart
  (``window_element``, ``window_title``) and combined as ``window``;
  unreadable ⇒ ``unavailable``, identity alone governs (plain-dictation
  contract).
- field classification/role: mismatch ⇒ target_changed. A snapshot
  without field data (denied/unclassifiable/AX off/PTT-identity-only)
  validates on identity alone — insertion proceeds as plain dictation.
- selection: only a NON-EMPTY recorded selection (the replacement
  case) carries destructive authority, and only while it is still
  exactly there — same range and same text, both read back. A recorded
  selection whose text was not kept, a live selection that cannot be
  read, or a destination whose content may not be read cannot prove
  it: the replacement is refused (S12: "if selected text changes...
  invalidate replacement authority"). A moved caret never blocks
  insertion (queued results land in dictation order; the user's cursor
  is the insertion point by design), and another field of the same
  role in the same window is not a change for plain dictation (M06 D5).
  A caret recorded at capture that is now a non-empty live selection is
  not a caret move: replacing text the user selected afterwards has no
  authority (``selection: fail``).

Strict replacement (``job["strict_replacement"]``, set only by an
accepted selected-text transform, M11-AC03): replacing text the user
reviewed needs POSITIVE proof of every item, each read on the bound
element — the recorded window element must be the live one AND the
recorded window title must read back equal (neither substitutes for the
other), the role must read back equal, the recorded non-empty selection
must read back with the same range and text, and the bounded text
recorded on BOTH sides of it must have been recorded and read back
unchanged (a second document in the same app can match title, role,
range and text). Any missing proof refuses. Plain dictation keeps the
permissive matrix.

Validation runs on the insertion thread, budgeted by the host's
messaging timeout — never on the UI callback, never on the hotkey path.
"""

from __future__ import annotations

from typing import Optional

from .. import ids
from ..context.providers import ax_range
from ..context.snapshot import (FIELD_SECURE, FIELD_TEXT, ContextSnapshot,
                                TargetSnapshot, app_denied, classify_field)
from .hosts import InsertionHost
from .target_lease import (VERIFICATION_FAIL, VERIFICATION_NOT_RECORDED,
                           VERIFICATION_PASS, VERIFICATION_UNAVAILABLE,
                           TargetLease)


def _as_range(rng) -> Optional[tuple]:
    """Half-open (start, end) in the host's AX units — a native AXValue
    CFRange is decoded (UTF-16 units on macOS), never parsed."""
    r = ax_range(rng)
    return None if r is None else (r[0], r[0] + r[1])


def acquire_destination(host, pid):
    """The focused element of application ``pid`` and whether it is
    provably that application's: ``(element, owned)``. ``(None, True)``
    means the application has no focused element (nothing foreign);
    ``(None, False)`` a foreign or unprovable owner."""
    if pid is None:
        return None, True
    fn = getattr(host, "focused_element_for", None)
    el = fn(pid) if fn is not None else None
    if el is None:
        return None, True
    return (el, True) if host.element_pid(el) == pid else (None, False)


def read_permission(host, el, *, bundle, denied_apps=(), deny_invalid=False,
                    snapshot_denied=False):
    """Content-read permission for ``el`` (S12): ``(allowed, reason,
    role)``. Denial is decided before any Accessibility call; otherwise
    role and subrole are read (metadata) and only a text field may be
    read."""
    if deny_invalid:
        return False, "deny_list_invalid", None
    if snapshot_denied or app_denied(bundle, denied_apps or ()):
        return False, "denied_app", None
    if el is None:
        return False, "no_owned_element", None
    role = host.attribute(el, "AXRole")
    subrole = host.attribute(el, "AXSubrole")
    cls = classify_field(role if isinstance(role, str) else None,
                         subrole if isinstance(subrole, str) else None)
    role = role if isinstance(role, str) else None
    if cls == FIELD_TEXT:
        return True, None, role
    return False, ("secure_field" if cls == FIELD_SECURE
                   else "unclassifiable_field"), role


def validate_target(host: InsertionHost,
                    snapshot: Optional[ContextSnapshot | TargetSnapshot],
                    job: dict, *, denied_apps=(), deny_invalid=False
                    ) -> tuple[Optional[TargetLease], dict]:
    """Return ``(lease, verification)`` — lease None means the target
    changed and the artifact must be routed to saved history."""
    lease, verification = _validate(host, snapshot, job, denied_apps,
                                    deny_invalid)
    if lease is None or not job.get("strict_replacement"):
        return lease, verification
    field = snapshot.field if isinstance(snapshot, ContextSnapshot) \
        else None
    proven = (verification.get("identity") == VERIFICATION_PASS
              and verification.get("window_element") == VERIFICATION_PASS
              and verification.get("window_title") == VERIFICATION_PASS
              and verification.get("field") == VERIFICATION_PASS
              and verification.get("selection") == VERIFICATION_PASS
              and lease.replace_selection and lease.read_allowed)
    if proven:
        if field is None or field.preceding_text is None \
                or field.following_text is None:
            # Both flanks are part of the strict proof: one that was
            # never recorded cannot have read back unchanged.
            verification["surroundings"] = VERIFICATION_NOT_RECORDED
            proven = False
        else:
            verification["surroundings"] = _surroundings_verdict(
                host, lease.element, field)
            proven = verification["surroundings"] == VERIFICATION_PASS
    if not proven:
        verification["strict"] = VERIFICATION_FAIL
        return None, verification
    verification["strict"] = VERIFICATION_PASS
    return lease, verification


def _surroundings_verdict(host, el, field) -> str:
    from .selection import surroundings
    if el is None:
        return VERIFICATION_UNAVAILABLE
    # Host units, as recorded (the selection check's convention).
    s, e = field.selected_range_utf16 or field.selected_range
    pre, fol = surroundings(host, el, s, e)
    if pre is None or fol is None:
        return VERIFICATION_UNAVAILABLE
    same = pre == field.preceding_text and fol == field.following_text
    return VERIFICATION_PASS if same else VERIFICATION_FAIL


def _window_verdicts(host, el, recorded_win, window_title, verification,
                     *, title_allowed):
    """Fill ``window_element``/``window_title`` and the combined
    ``window`` verdict; the live window element (or None)."""
    live_win = host.attribute(el, "AXWindow") if el is not None else None
    if recorded_win is None:
        verification["window_element"] = VERIFICATION_NOT_RECORDED
    elif live_win is None:
        verification["window_element"] = VERIFICATION_UNAVAILABLE
    else:
        verification["window_element"] = (
            VERIFICATION_PASS if live_win == recorded_win
            else VERIFICATION_FAIL)
    if window_title is None:
        verification["window_title"] = VERIFICATION_NOT_RECORDED
    elif el is None or not title_allowed:
        verification["window_title"] = VERIFICATION_UNAVAILABLE
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
        verification["window_title"] = (
            VERIFICATION_UNAVAILABLE if title is None
            else (VERIFICATION_PASS if title == window_title
                  else VERIFICATION_FAIL))
    parts = (verification["window_element"], verification["window_title"])
    if VERIFICATION_FAIL in parts:
        verification["window"] = VERIFICATION_FAIL
    elif VERIFICATION_PASS in parts:
        verification["window"] = VERIFICATION_PASS
    elif VERIFICATION_UNAVAILABLE in parts:
        verification["window"] = VERIFICATION_UNAVAILABLE
    else:
        verification["window"] = VERIFICATION_NOT_RECORDED
    return live_win


def _validate(host, snapshot, job, denied_apps, deny_invalid):
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
    live_pid = frontmost.get("pid") if frontmost else None
    live_bundle = frontmost.get("bundle") if frontmost else None
    common = dict(job_id=job.get("job_id"),
                  attempt=int(job.get("attempt", 1)))
    if target is None:
        # No context at all (feature off / identity failed at PTT): no
        # recorded destination to validate against. Insert on faith —
        # the result is posted_unverified and observation is
        # unavailable (unreliable_target). The destination is still the
        # frontmost application's own focused element, and the live
        # caret is still anchored when its content may be read: queued
        # results must land at the cursor, not at a stale zero offset.
        for key in ("identity", "window", "field", "selection"):
            verification[key] = VERIFICATION_NOT_RECORDED
        el, owned = acquire_destination(host, live_pid)
        if not owned:
            verification["owner"] = VERIFICATION_FAIL
            return None, verification
        allowed, why, _role = read_permission(
            host, el, bundle=live_bundle, denied_apps=denied_apps,
            deny_invalid=deny_invalid)
        verification["read"] = "allowed" if allowed else why
        caret = None
        if allowed:
            rng = _as_range(host.attribute(el, "AXSelectedTextRange"))
            caret = rng[0] if rng is not None else None
        return TargetLease(
            target_snapshot_id=None, context_snapshot_id=None,
            frontmost_pid=live_pid, frontmost_bundle=live_bundle,
            caret=caret, verification=verification,
            read_allowed=allowed, read_denied_reason=why,
            destination_recorded=False, owner_pid=live_pid, element=el,
            window_element=(host.attribute(el, "AXWindow")
                            if el is not None else None),
            **common), verification
    same = same_fn(frontmost)
    verification["identity"] = VERIFICATION_PASS if same else VERIFICATION_FAIL
    if not same:
        # No further reads: the destination is wrong and nothing about
        # the field can repair that.
        for key in ("window", "field", "selection"):
            verification[key] = VERIFICATION_UNAVAILABLE
        return None, verification

    el, owned = acquire_destination(host, live_pid)
    if not owned:
        # The application's focused element belongs to another process:
        # not provably this destination — refused unread.
        verification["owner"] = VERIFICATION_FAIL
        for key in ("window", "field", "selection"):
            verification[key] = VERIFICATION_UNAVAILABLE
        return None, verification
    verification["owner"] = (VERIFICATION_PASS if el is not None
                             else VERIFICATION_UNAVAILABLE)
    denied = deny_invalid or bool(target.denied) \
        or app_denied(live_bundle, denied_apps or ())
    allowed, why, role = read_permission(
        host, el, bundle=live_bundle, denied_apps=denied_apps,
        deny_invalid=deny_invalid, snapshot_denied=bool(target.denied))
    verification["read"] = "allowed" if allowed else why

    # The M06 window identity (an in-memory host element) ADDS to the
    # title check: a different window element is a changed target even
    # under an equal title; the same element still fails on a different
    # readable title (tabs share one window). A moved caret or another
    # field of the same window and title is not a change.
    recorded_win = getattr(snapshot, "window_element", None) \
        if isinstance(snapshot, ContextSnapshot) else None
    live_win = _window_verdicts(host, el, recorded_win, window_title,
                                verification, title_allowed=not denied)
    if verification["window"] == VERIFICATION_FAIL:
        verification["field"] = VERIFICATION_UNAVAILABLE
        verification["selection"] = VERIFICATION_UNAVAILABLE
        return None, verification

    lease_common = dict(
        target_snapshot_id=target.target_snapshot_id,
        context_snapshot_id=(snapshot.context_snapshot_id
                             if isinstance(snapshot, ContextSnapshot)
                             else None),
        frontmost_pid=target.app_pid, frontmost_bundle=target.app_bundle,
        field_role=field.role if field else None,
        field_classification=field.classification if field else None,
        read_allowed=allowed, read_denied_reason=why,
        destination_recorded=True, owner_pid=live_pid, element=el,
        window_element=live_win, **common)
    snap_range = ((field.selected_range_utf16 or field.selected_range)
                  if field else None)
    replace_selection = bool(snap_range and snap_range[1] > snap_range[0])

    if el is None:
        verification["field"] = VERIFICATION_UNAVAILABLE
        verification["selection"] = VERIFICATION_UNAVAILABLE
        if replace_selection:
            return None, verification
        return TargetLease(verification=verification,
                           **lease_common), verification

    # (the role was read by the permission check; a denied app is not
    # asked)
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
    # still exist exactly as recorded (replacement case) — and every
    # part of that must be READ, which needs content permission. A caret
    # (empty range) moves freely — the caret is the insertion point.
    selected_range = None
    if allowed:
        selected_range = _as_range(host.attribute(el, "AXSelectedTextRange"))
    caret = selected_range[0] if selected_range is not None else None
    if not replace_selection:
        recorded_caret = snap_range is not None
        if selected_range is None:
            verification["selection"] = VERIFICATION_UNAVAILABLE
        elif recorded_caret and selected_range[1] > selected_range[0]:
            # A caret at capture, a selection now: the user selected
            # text after the request — no authority to replace it.
            verification["selection"] = VERIFICATION_FAIL
        else:
            verification["selection"] = VERIFICATION_PASS
    elif field.selected_text is None or selected_range is None:
        verification["selection"] = VERIFICATION_UNAVAILABLE
    else:
        sel_text = host.string_for_range(
            el, selected_range[0], selected_range[1] - selected_range[0])
        if sel_text is None:
            verification["selection"] = VERIFICATION_UNAVAILABLE
        else:
            same_range = tuple(selected_range) == tuple(snap_range)
            same_text = sel_text == field.selected_text
            verification["selection"] = (
                VERIFICATION_PASS if same_range and same_text
                else VERIFICATION_FAIL)
    if verification["selection"] == VERIFICATION_FAIL or (
            replace_selection
            and verification["selection"] != VERIFICATION_PASS):
        # Missing proof never keeps destructive authority.
        return None, verification
    return TargetLease(
        replace_selection=replace_selection,
        selected_range=tuple(snap_range) if snap_range else None,
        selected_text_sha=(ids.sha256_text(field.selected_text or "")
                           if replace_selection and field else None),
        caret=caret, verification=verification, **lease_common), verification
