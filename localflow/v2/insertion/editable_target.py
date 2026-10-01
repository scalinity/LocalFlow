"""History Paste Again authority tied to an editable AX hit, not focus.

Only metadata/capabilities are read here; no value or selected text.
Opaque element identities stay in memory and never enter snapshot JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from ..context.snapshot import TargetSnapshot, FIELD_TEXT, classify_field


@dataclass(frozen=True)
class EditableHit:
    pid: int
    element: object = field(repr=False)
    window: object = field(repr=False)


@dataclass(frozen=True)
class EditableTargetSnapshot(TargetSnapshot):
    element: object = field(default=None, compare=False, repr=False)
    window_element: object = field(default=None, compare=False, repr=False)

    def matches_element(self, host, el):
        return (el is not None and el == self.element
                and host.element_pid(el) == self.app_pid
                and self.window_element is not None
                and host.attribute(el, "AXWindow") == self.window_element
                and is_editable(host, el))


def is_editable(host, el):
    """Positive text and write evidence; uncertainty never grants authority."""
    role = host.attribute(el, "AXRole")
    subrole = host.attribute(el, "AXSubrole")
    enabled = host.attribute(el, "AXEnabled")
    if subrole == "AXSecureTextField" or (enabled is not None and not enabled):
        return False
    text = classify_field(role, subrole) == FIELD_TEXT
    editable = host.attribute(el, "AXEditable")
    if editable is False or not (text or editable is True):
        return False
    return (host.is_settable(el, "AXSelectedText")
            or host.is_settable(el, "AXValue")
            or (editable is True
                and host.is_settable(el, "AXSelectedTextRange")))


def resolve_editable_hit(host, pid, point):
    """Resolve only the hit or its bounded text container, never AX focus.

    A nested rendered text/group may belong to an editable container;
    an independent control/window is a traversal boundary. Every
    candidate must contain the original screen point and share ownership.
    """
    if pid is None or point is None or not host.is_trusted():
        return None
    try:
        x, y = point
        if not all(math.isfinite(v) for v in (x, y)):
            return None
        el = host.element_at_position(pid, point)
        seen = []
        for _ in range(8):
            if el is None or el in seen or host.element_pid(el) != pid:
                return None
            seen.append(el)
            rect = host.element_frame(el)
            if rect is None:
                return None
            left, top, width, height = rect
            if not (width > 0 and height > 0
                    and left <= x < left + width and top <= y < top + height):
                return None
            role = host.attribute(el, "AXRole")
            if is_editable(host, el):
                window = host.attribute(el, "AXWindow")
                if window is None or host.element_pid(window) != pid:
                    return None
                return EditableHit(pid, el, window)
            # Only rendered descendants can resolve upward. Never turn
            # a button, toolbar, sidebar row or titlebar into its field.
            if role not in ("AXStaticText", "AXGroup", "AXLayoutArea"):
                return None
            el = host.attribute(el, "AXParent")
    except Exception:
        return None
    return None
