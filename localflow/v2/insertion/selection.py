"""Selected-text capture for transforms (V2 M11, Spec S12/S16/S18).

The capture half of selected-text replacement authority. The focused
field is classified BEFORE any of its content is read (the S12 rule
the context provider follows): a secure field refuses without reading
its selection, range or value. For every other field the capture
records what accept-time revalidation needs to prove it is replacing
the same selection in the same document — app identity, window title,
role/classification, the selected range and text, and bounded text on
either side of the selection (a second document in the same app with
the same title, role, range and text differs there).

Denial is the M06 rule (``snapshot.app_denied`` over the validated
``config.context_policy`` list) and is decided before any Accessibility
call. The element read is the focused element OF the authorized
application (``focused_element_for(pid)``, the M06 ownership rule),
accepted only when ``element_pid`` names that application: a focus
change after the decision can never make the capture read another
app's field — it is refused unread (``destination_unverified``), and
every later read of the capture uses that one element. The selection
is recorded in the host's own units
(``selected_range_utf16``, exactly as ``validate_target`` reads it
back) and in code points only when exactly derivable (the M06 field
convention); the field's own window element is recorded so the M06/M08
window check applies, not the title alone. The returned ``range`` stays
in host units.
"""

from __future__ import annotations

from typing import Optional

from .. import ids
from ..context.providers import (_LONE_SURROGATE, NEARBY_CHARS, categorize,
                                 utf16_len)
from ..context.snapshot import (FIELD_SECURE, FIELD_TEXT, ContextSnapshot,
                                FieldContext, TargetSnapshot, app_denied,
                                classify_field)
from .validation import _as_range, acquire_destination

SURROUNDING_CHARS = min(NEARBY_CHARS, 200)


def window_title(host, el) -> Optional[str]:
    """The focused window's title — the host method when it exists
    (the real AX API hangs AXFocusedWindow off the application), else
    AXFocusedWindow → AXTitle on the element (the validator's rule)."""
    fn = getattr(host, "focused_window_title", None)
    if fn is not None:
        return fn(el)
    win = host.attribute(el, "AXFocusedWindow")
    if win is None:
        return None
    t = host.attribute(win, "AXTitle")
    return str(t) if t else None


def surroundings(host, el, start: int, end: int):
    """Bounded text before and after ``[start, end)`` (None when the
    host cannot read it)."""
    total = host.number_of_characters(el)
    p0 = max(0, start - SURROUNDING_CHARS)
    preceding = host.string_for_range(el, p0, start - p0) \
        if start > p0 else ""
    following = ""
    if total is not None and end < total:
        following = host.string_for_range(
            el, end, min(SURROUNDING_CHARS, total - end))
    elif total is None:
        following = None
    return preceding, following


def capture_selection(host, *, denied_apps=(), expected_pid=None, copy_selected=None,
                      expected_element=None, expected_window=None):
    """Capture the focused selection for a selected-text transform.
    Returns ``(capture, None)`` or ``(None, reason)``; the capture is
    ``{"source", "range", "snapshot", "target"}``."""
    fm = host.frontmost()
    if not fm:
        return None, "no_frontmost_application"
    if expected_pid is not None and fm.get("pid") != expected_pid:
        return None, "destination_unverified"
    bundle = fm.get("bundle")
    if app_denied(bundle, denied_apps or ()):
        return None, "app_denied"
    prepare = getattr(host, "prepare_text_capture", None)
    if prepare is not None:
        prepare(fm.get("pid"))
        if (host.frontmost() or {}).get("pid") != fm.get("pid"):
            return None, "destination_unverified"
    el, owned = acquire_destination(host, fm.get("pid"))
    if not owned:
        return None, "destination_unverified"
    if el is None:
        return None, "no_focused_element"
    if expected_element is not None and el != expected_element:
        return None, "destination_unverified"
    if expected_window is not None and host.attribute(el, "AXWindow") != expected_window:
        return None, "destination_unverified"
    role = host.attribute(el, "AXRole")
    subrole = host.attribute(el, "AXSubrole")
    role = role if isinstance(role, str) else None
    subrole = subrole if isinstance(subrole, str) else None
    classification = classify_field(role, subrole)
    if classification == FIELD_SECURE:
        # Absolute rule: nothing of a secure field is read.
        return None, "secure_field"
    if classification != FIELD_TEXT:
        # S12: an unclassifiable field gets no content read — an
        # explicit transform needs a classified text field.
        return None, "unclassifiable_field"
    # A terminal's AX range describes its screen/scrollback, not its
    # shell or coding-CLI composer. Never generate from those coordinates.
    # Logical-buffer adapters acquire their source through a separate path.
    if categorize(bundle) == "terminal":
        return None, "terminal_buffer_integration_required"
    raw = host.attribute(el, "AXSelectedTextRange")
    if isinstance(raw, tuple) and len(raw) == 2:
        # The repo convention (providers._as_range): a plain tuple is
        # (location, length), never (start, end).
        rng = (int(raw[0]), int(raw[0]) + int(raw[1]))
    else:
        rng = _as_range(raw)
    if rng is None or rng[1] <= rng[0]:
        return None, "no_selection"
    text = host.string_for_range(el, rng[0], rng[1] - rng[0])
    direct = host.attribute(el, "AXSelectedText")
    if isinstance(direct, str) and direct and text is not None and direct != text:
        return None, "selection_apis_disagree"
    acquisition = "ax_crosschecked" if direct and text else "ax_range"
    can_replace = True
    if text is None and isinstance(direct, str) and direct:
        text, acquisition = direct, "ax_selected_text"
    if text is None and copy_selected is not None:
        text, acquisition = copy_selected(el, fm["pid"]), "fresh_copy"
        # A fresh copy proves acquisition, not a stable replacement API.
        # The result remains useful in Copy/workspace without a blind paste.
        can_replace = False
    if not text or not text.strip():
        return None, "no_selection"
    if utf16_len(text) != rng[1] - rng[0] or _LONE_SURROGATE.search(text):
        return None, "selection_range_units_unverified"
    title = window_title(host, el)
    window_el = host.attribute(el, "AXWindow")
    preceding, following = surroundings(host, el, rng[0], rng[1])
    # Code points are exact only when the whole prefix was read and every
    # unit of the prefix and the selection came back (the M06 rule).
    cp_range = None
    if rng[0] <= SURROUNDING_CHARS and preceding is not None \
            and utf16_len(preceding) == rng[0] \
            and utf16_len(text) == rng[1] - rng[0] \
            and not _LONE_SURROGATE.search(preceding + text):
        cp_range = (len(preceding), len(preceding) + len(text))
    target = TargetSnapshot(
        target_snapshot_id=ids.new_id("tgt"),
        app_bundle=bundle, app_name=fm.get("name"), app_pid=fm.get("pid"),
        category=categorize(bundle) if bundle else "unknown",
        captured_at_utc=ids.now_utc_iso())
    field = FieldContext(
        role=role, subrole=subrole, classification=classification,
        selected_text=text, selected_range=cp_range,
        selected_range_utf16=tuple(rng),
        preceding_text=preceding, following_text=following,
        document_url=host.attribute(el, "AXDocument"))
    snap = ContextSnapshot(
        context_snapshot_id=ids.new_id("ctx"),
        stage="transform_selection", target=target, field=field,
        window_title=title, window_element=window_el,
        field_element=el,
        captured_at_utc=ids.now_utc_iso())
    return {"source": text, "range": tuple(rng), "snapshot": snap,
            "target": target, "acquisition": acquisition, "can_replace": can_replace,
            "review_element": el, "review_window": window_el}, None
