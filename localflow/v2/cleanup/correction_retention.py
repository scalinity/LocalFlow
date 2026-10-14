"""Keep source postmodifiers when only a repeated quantity is corrected.

A flat deletion cannot represent ``4 liters of dye, no wait, 6 liters``:
the value changes, while ``of dye`` still describes it. Move that exact
source island beside the replacement in a comparison copy. The ordinary
validator can then enforce its order, spelling and multiplicity without
giving obsolete words permission to return.
"""
from __future__ import annotations

import re


_NUMBER = r"[+-]?\d+(?:[.,]\d+)*"
_PREPOSITIONS = r"of|for|per|with|without|at|in|on"
_WORD = r"[^\W\d_]+"
_QUANTITY_DETAIL = re.compile(
    rf"{_NUMBER}[ \t]+(?P<unit>{_WORD}"
    rf"(?:[ \t]+(?!(?:{_PREPOSITIONS})\b){_WORD}){{0,2}})"
    rf"(?P<space>[ \t]+)(?P<detail>(?P<prep>{_PREPOSITIONS})[ \t]+.+)",
    re.IGNORECASE)


def qualifier_retention(source: str, span: tuple, marker_start: int):
    """Return ``((start, end, destination), reason)`` for a source move.

    A repeated quantity head followed by an omitted postmodifier is the
    bounded supported shape. A stated replacement postmodifier supersedes
    the old one. An unsupported replacement for this shape is rejected
    rather than losing its detail. Coordinates refer to the original source.
    """
    start, end = span
    old = source[start:marker_start].rstrip(" \t,;:")
    match = _QUANTITY_DETAIL.fullmatch(old)
    if match is None:
        return None, None
    unit = match.group("unit")
    replacement = re.match(
        rf"[ \t,;:]*{_NUMBER}[ \t]+{re.escape(unit)}(?![\w-])",
        source[end:])
    if replacement is None:
        return None, "unresolved_quantity_qualifier"
    destination = end + replacement.end()
    following = source[destination:]
    # A newly stated value of the same relationship replaces its old
    # detail: ``4 liters of dye ... 6 liters of solvent``.
    if re.match(rf"[ \t,;:]*(?i:{re.escape(match.group('prep'))})\b", following):
        return None, None
    relation = re.match(r"[ \t,;:]*(with|without|of)[ \t]+", following, re.IGNORECASE)
    old_relation = match.group("prep").lower()
    if relation is not None:
        new_relation = relation.group(1).lower()
        if {old_relation, new_relation} in ({"with", "without"}, {"of", "without"}):
            description = match.group("detail")[len(old_relation):].strip()
            core = re.sub(r"^(?:a|an|the)[ \t]+", "", description, flags=re.IGNORECASE)
            same = re.match(r"(?:(?:a|an|the)[ \t]+)?" + re.escape(core),
                            following[relation.end():], re.IGNORECASE)
            rest = following[relation.end() + same.end():] if same else None
            if rest is not None and re.match(
                    rf"[ \t]*(?:$|[,;.!?\n]|(?i:and|or|but|then|because|before|after|"
                    rf"until|when|while|if|unless|only|to|{_PREPOSITIONS})\b)", rest):
                # Explicit presence→absence replaces the descriptor; never
                # concatenate ``with dye without dye``. Removing a negation
                # or changing the substance remains outside this narrow rule.
                if old_relation == "with" and new_relation == "without" \
                        and same.group().lower() == description.lower():
                    return None, None
                return None, "opposing_quantity_qualifier"
    if following and not re.match(
            rf"[ \t]*(?:[,;.!?\n]|$|(?i:and|or|but|then|because|before|after|"
            rf"until|when|while|if|unless|only|to|{_PREPOSITIONS})\b)", following):
        return None, "unresolved_quantity_qualifier"
    return (start + match.start("space"), start + len(old), destination), None


def retention_moves(source: str, corrections: list) -> list:
    """Exact moves for already admitted, non-overlapping corrections."""
    moves = []
    for start, end, marker in corrections:
        move, reason = qualifier_retention(source, (start, end), marker)
        if reason:
            raise ValueError(reason)
        if move is not None:
            moves.append(move)
    return moves


def correction_view(source: str, corrections: list, protected=()) -> tuple:
    """Return source, correction and protection coordinates after moves.

    Moves are exact and local, not model-proposed rewrites. Original source
    and original deletion coordinates remain the engine's stored record.
    Protected occurrences cannot straddle the insertion point.
    """
    view = source
    rebased = list(corrections)
    positions = [tuple(p[:2]) for p in protected]
    for start, end, destination in sorted(
            retention_moves(source, corrections), reverse=True):
        size = end - start
        view = (view[:start] + view[end:destination]
                + view[start:end] + view[destination:])

        def point(offset, *, ending=False):
            moved = start < offset <= end if ending else start <= offset < end
            if moved:
                return destination - size + offset - start
            shifted = end < offset <= destination if ending else end <= offset < destination
            if shifted:
                return offset - size
            return offset

        rebased = [(point(a), point(b, ending=True), point(m))
                   for a, b, m in rebased]
        positions = [(point(a), point(b, ending=True)) for a, b in positions]
    return view, rebased, positions
