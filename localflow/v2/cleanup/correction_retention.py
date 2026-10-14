"""Preserve source details around explicitly marked quantity corrections.

A flat deletion cannot represent ``4 liters of dye, no wait, 6 liters``:
the value changes, while ``of dye`` still describes it. Move that exact
source island beside the replacement in a comparison copy. The ordinary
validator can then enforce its order, spelling and multiplicity without
giving obsolete words permission to return.

An exact repeated modal predicate after a compound marker is authorized
separately, with its original source coordinates retained by the engine.
"""
from __future__ import annotations

import re


_NUMBER = r"[+-]?\d+(?:[.,]\d+)*"
_PREPOSITIONS = r"of|for|per|with|without|at|in|on|to"
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
        if match.group("prep").lower() == "to":
            # "To be signed" is a purpose, not a restated recipient.
            # Require a bounded determiner-led noun phrase or pronoun on
            # both sides. Capitalization alone cannot distinguish a name
            # from an infinitive such as "to Deliver before Friday".
            boundaries = (rf"{_PREPOSITIONS}|and|or|but|then|because|before|after|"
                          r"until|when|while|if|unless|be|have|do")
            noun_word = rf"(?!(?i:{boundaries})\b){_WORD}"
            recipient = (rf"(?:(?i:the|a|an|this|that|these|those)[ \t]+"
                         rf"{noun_word}(?:[ \t]+{noun_word}){{0,3}}"
                         rf"|(?i:me|you|him|her|it|us|them))")
            old_tail = match.group("detail")[2:].strip()
            new_tail = re.sub(r"^[ \t,;:]*(?i:to)[ \t]+", "", following)
            if (re.fullmatch(recipient, old_tail) is None
                    or re.match(recipient + rf"(?=$|[,;.!?\n]|[ \t]+(?i:{boundaries})\b)",
                                new_tail) is None):
                return None, "unresolved_quantity_qualifier"
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


def repeated_restart(source: str, span: tuple, marker_start: int):
    """Find an exact redundant ``it <modal> be`` after a compound marker.

    Only typed quantities with the same unit and the same adjacent modal
    predicate qualify. The original subject and predicate remain in place;
    a changed subject form, modality, negation or unit cannot be discarded.
    Returned coordinates include the separator after the original marker.
    No span and no reason means ordinary correction admission still applies;
    an attempted but unproved restart instead returns a rejection reason.
    """
    start, end = span
    if source[marker_start:end].lower() != "i mean actually":
        return None, None
    opening = re.split(r"[.!?](?:\s|$)|[,;\n]",
                       source[end:].lstrip(" \t,;:"), maxsplit=1)[0]
    words = opening.lower().split()[:5]
    first = re.split("['’]", words[0])[0] if words else ""
    pronoun = first in {"i", "you", "he", "she", "it", "we", "they",
                        "this", "that", "these", "those", "there"}
    auxiliaries = {"should", "must", "could", "would", "may", "might", "can",
                   "will", "shall", "am", "is", "are", "was", "were", "be",
                   "has", "have", "had", "do", "does", "did"}
    boundaries = set(_PREPOSITIONS.split("|")) | {
        "and", "or", "but", "then", "because", "before", "after", "until",
        "when", "while", "if", "unless", "only",
    }
    named_predicate = False
    for index, word in enumerate(words):
        if word in boundaries or not re.fullmatch(rf"{_WORD}(?:['’]{_WORD})?", word):
            break
        if index and word in auxiliaries:
            named_predicate = True
            break
    # Openings outside these bounded restart shapes grant no extra
    # deletion. Later clauses stay required source text. Pronoun-looking
    # names and incomplete name/auxiliary openings remain ambiguous.
    if not pronoun and not named_predicate:
        return None, None
    reason = "unresolved_repeated_restart"
    quantity = re.fullmatch(
        rf"{_NUMBER}[ \t]+(?P<unit>{_WORD})[ \t]*,?[ \t]*",
        source[start:marker_start])
    predicate = re.search(
        r"\b(?P<frame>(?:should|must|could|would|may|might|can|will)[ \t]+be)[ \t]+$",
        source[:start], re.IGNORECASE)
    if quantity is None or predicate is None:
        return None, reason
    subject = re.split(r"[.!?;\n]", source[:predicate.start()])[-1]
    from .validation import FUNCTION_WORDS, NEGATION_WORDS
    subject_words = re.findall(r"[^\W_]+(?:['’][^\W_]+)*", subject.lower())
    nominal = subject_words[1:] if subject_words[:1] in (
        ["the"], ["a"], ["an"], ["this"], ["that"]) else []
    subject_functions = FUNCTION_WORDS | NEGATION_WORDS | {
        "all", "both", "each", "either", "few", "many", "much", "several", "some", "these", "those",
    }
    # Support only a determiner plus a short simple nominal, or an exact
    # repeated ``it``.
    # Postmodifiers, coordinated subjects and other pronouns can change
    # the referent. Reject plural-looking words anywhere in the nominal;
    # this intentionally also declines singular nouns ending in s.
    simple_nominal = (1 <= len(nominal) <= 3 and all(
        word.isalpha() and word not in subject_functions
        and not word.endswith("s")
        and word not in {"children", "feet", "men", "mice", "people", "teeth", "women"}
        for word in nominal))
    if (re.search(r"[^\w \t]", subject)
            or not (subject_words == ["it"] or simple_nominal)):
        return None, reason
    replacement = re.match(
        rf"(?P<restart>[ \t,]*(?i:it)[ \t]+(?i:{re.escape(predicate.group('frame'))}))"
        rf"[ \t]+{_NUMBER}[ \t]+{re.escape(quantity.group('unit'))}(?![\w-])",
        source[end:])
    if replacement is None:
        return None, reason
    following = source[end + replacement.end():]
    if not re.match(
            r"[ \t]*(?:$|[,;.!?\n]|(?i:and|or|but|then|because|before|after|"
            r"until|when|while|if|unless|only)\b)", following):
        return None, reason
    return (end, end + replacement.end("restart")), None


def correction_view(source: str, corrections: list, protected=()) -> tuple:
    """Return the comparison source and authorized correction coordinates.

    Moves are exact and local, not model-proposed rewrites. Original source
    and original deletion coordinates remain the engine's stored record.
    Protected occurrences cannot straddle the insertion point.
    Exact redundant restarts extend comparison spans while the engine
    continues to record the original marker-terminated proposal spans.
    """
    view = source
    rebased = []
    for start, end, marker in corrections:
        restart, reason = repeated_restart(source, (start, end), marker)
        if reason:
            raise ValueError(reason)
        rebased.append((start, restart[1] if restart else end, marker))
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
