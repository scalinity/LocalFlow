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
from dataclasses import dataclass

from .lexicon import (CLAUSE_END, CLAUSE_LINKS, COUNT, DETAIL_PREPOSITIONS,
                      FINITE_AUXILIARIES, FRAME_WORDS, FUNCTION_WORDS, MEASURE_UNIT, MODALS,
                      NEGATION_WORDS, NUMBER, SPELLED_NUMBER, Neighbourhood, alternation,
                      marker_key, plain_words,
                      quoted_regions, restatement, touches)


_NUMBER = NUMBER
_PREPOSITIONS = alternation(DETAIL_PREPOSITIONS)
_WORD = r"[^\W\d_]+"
_LINKS = alternation(CLAUSE_LINKS)
_QUANTITY_DETAIL = re.compile(
    rf"{_NUMBER}[ \t]+(?P<unit>{_WORD}"
    rf"(?:[ \t]+(?!(?:{_PREPOSITIONS})\b){_WORD}){{0,2}})"
    rf"(?P<space>[ \t]+)(?P<detail>(?P<prep>{_PREPOSITIONS})[ \t]+.+)",
    re.IGNORECASE)
# Any quantity head followed by a prepositional detail, wherever it sits.
_ANY_QUANTITY_DETAIL = re.compile(
    rf"(?<![\w.,])(?:{_NUMBER}|{SPELLED_NUMBER})"
    rf"[ \t]+{_WORD}(?:[ \t]+{_WORD}){{0,2}}[ \t]+(?:{_PREPOSITIONS})[ \t]+\S",
    re.IGNORECASE)
# Singular heads from the number profile, plus rotation and volume units.
_FRACTION_UNIT = re.compile(MEASURE_UNIT, re.IGNORECASE)
FRACTION_HEAD = re.compile(
    rf"(?P<count>{COUNT})[ \t]+(?P<denominator>half|halves|quarter|quarters)"
    rf"[ \t]+of[ \t]+(?:a|an)[ \t]+(?P<unit>{_WORD})", re.IGNORECASE)


def fraction_binds(n: Neighbourhood) -> bool:
    """The old value is a complete fraction head corrected to "1 half" or
    "1 quarter" of the same unit, closed, and clear of quotes and code.

    This exception needs the complete original numeric token and a closed
    replacement head. Bare "no" can introduce a negative clause. It
    abstains where a quotation, code span or fence (also one nested inside
    a Markdown container) overlaps or touches the correction.
    """
    source, start, marker_start, end = n.text, n.start, n.marker, n.end
    fraction = FRACTION_HEAD.fullmatch(source[start:marker_start].rstrip(" \t,;:"))
    if (fraction is None or not (start == 0 or source[start - 1].isspace())
            or source[marker_start:end].lower() == "no"):
        return False
    unit = fraction.group("unit")
    singular = fraction.group("denominator").lower() in {"half", "quarter"}
    if singular != (fraction.group("count") == "1") or not _FRACTION_UNIT.fullmatch(unit):
        return False
    replacement = re.match(
        rf"[ \t,;:]*1[ \t]+(?i:half|quarter)[ \t]+{re.escape(unit)}(?![\w-])",
        source[end:])
    return (replacement is not None
            and re.match(CLAUSE_END, source[end + replacement.end():]) is not None
            and not touches(quoted_regions(source), start, end + replacement.end()))


def restates_detail(n: Neighbourhood) -> bool:
    """The replacement restates the old value around its changed words
    (``40 ends per inch, no sorry, thirty-six ends per inch``; ``Please put
    Marta on 4 rooms at the start. Sorry, please put Marta on 6 rooms at
    the start``): every detail is repeated in place, so nothing is left to
    move or to bind. A change that includes a preposition, and so a
    relation, keeps the rules below."""
    shape = restatement(n)
    if shape is None:
        return False
    p, a, _b, _s = shape
    return not any(w in DETAIL_PREPOSITIONS
                   for w in plain_words(n.text[n.start:n.marker])[p:p + a])


def quantity_shaped(old: str) -> bool:
    """``old`` reads as one quantity with a prepositional detail, after an
    optional frame word (a fraction head is one such quantity)."""
    frame = re.match(rf"(?i:{alternation(FRAME_WORDS)})[ \t]+", old)
    return _QUANTITY_DETAIL.fullmatch(old, frame.end() if frame else 0) is not None


def quantity_binds(n: Neighbourhood) -> bool:
    """The old value is such a quantity and retention resolves it against a
    replacement that repeats its unit: the detail either moves beside the
    replacement or is restated there."""
    old = n.text[n.start:n.marker].rstrip(" \t,;:")
    lead = re.match(r"\S+[ \t]+", old).end() if n.frame else 0
    return (_QUANTITY_DETAIL.fullmatch(old, lead) is not None
            and qualifier_retention(n)[1] is None)


def qualifier_retention(n: Neighbourhood):
    """Return ``((start, end, destination), reason)`` for a source move.

    A repeated quantity head followed by an omitted postmodifier is the
    bounded supported shape. A stated replacement postmodifier supersedes
    the old one. An unsupported replacement for this shape is rejected
    rather than losing its detail. Coordinates refer to the original source.
    """
    source, start, marker_start, end = n.text, n.start, n.marker, n.end
    old = source[start:marker_start].rstrip(" \t,;:")
    if fraction_binds(n) or restates_detail(n):
        # The repeated unit is part of both complete fraction heads, or the
        # replacement repeats the whole detail. Everything after the
        # replacement stays required.
        return None, None
    # A frame word repeated after the marker leads both quantities: in
    # ``with 4 liters of dye, sorry, with 6 liters`` the detail binds
    # after the frame, and the replacement repeats it.
    lead, frame = 0, ""
    if n.frame:
        head = re.match(rf"(?i:{re.escape(n.frame)})[ \t]+", old)
        if head is None:
            # The old value is the frame word alone (``every, no, every other
            # day``) or the frame is not followed by a quantity: this rule
            # has nothing to bind, so the other checks decide.
            if _ANY_QUANTITY_DETAIL.search(old):
                return None, "unresolved_quantity_qualifier"
            return None, None
        lead = head.end()
        frame = rf"(?i:{re.escape(n.frame)})[ \t]+"
    match = _QUANTITY_DETAIL.fullmatch(old, lead)
    if match is None:
        # A quantity detail this rule cannot bind (a spelled number, a
        # determiner before the number, an unrepeated frame) keeps the source.
        if _ANY_QUANTITY_DETAIL.search(old):
            return None, "unresolved_quantity_qualifier"
        return None, None
    unit = match.group("unit")
    replacement = re.match(
        rf"[ \t,;:]*{frame}{_NUMBER}[ \t]+{re.escape(unit)}(?![\w-])",
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
            boundaries = rf"{_PREPOSITIONS}|{_LINKS}|be|have|do"
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
                    rf"[ \t]*(?:$|[,;.!?\n]|(?i:{_LINKS}|only|to|{_PREPOSITIONS})\b)", rest):
                # Explicit presence→absence replaces the descriptor; never
                # concatenate ``with dye without dye``. Removing a negation
                # or changing the substance remains outside this narrow rule.
                if old_relation == "with" and new_relation == "without" \
                        and same.group().lower() == description.lower():
                    return None, None
                return None, "opposing_quantity_qualifier"
    if following and not re.match(
            rf"[ \t]*(?:[,;.!?\n]|$|(?i:{_LINKS}|only|to|{_PREPOSITIONS})\b)", following):
        return None, "unresolved_quantity_qualifier"
    return (start + match.start("space"), start + len(old), destination), None


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
    if marker_key(source[marker_start:end]) != "i mean actually":
        return None, None
    opening = re.split(r"[.!?](?:\s|$)|[,;\n]",
                       source[end:].lstrip(" \t,;:"), maxsplit=1)[0]
    words = opening.lower().split()[:5]
    first = re.split("['’]", words[0])[0] if words else ""
    pronoun = first in {"i", "you", "he", "she", "it", "we", "they",
                        "this", "that", "these", "those", "there"}
    boundaries = DETAIL_PREPOSITIONS | CLAUSE_LINKS | {"only"}
    named_predicate = False
    for index, word in enumerate(words):
        if word in boundaries or not re.fullmatch(rf"{_WORD}(?:['’]{_WORD})?", word):
            break
        if index and word in FINITE_AUXILIARIES:
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
        rf"\b(?P<frame>(?:{'|'.join(sorted(MODALS))})[ \t]+be)[ \t]+$",
        source[:start], re.IGNORECASE)
    if quantity is None or predicate is None:
        return None, reason
    subject = re.split(r"[.!?;\n]", source[:predicate.start()])[-1]
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
    if not re.match(rf"[ \t]*(?:$|[,;.!?\n]|(?i:{_LINKS}|only)\b)", following):
        return None, reason
    return (end, end + replacement.end("restart")), None


@dataclass(frozen=True)
class AdmittedCorrection:
    """One admitted deletion with the exact edits proved for it.

    ``span`` is the marker-terminated proposal and ``marker`` the offset
    where its marker begins. ``restart`` is an authorized redundant restart
    after the marker and ``move`` a retained qualifier ``(start, end,
    destination)``. Offsets are source code points. Admission decides them
    once; every later step reads them rather than deriving them again.
    """
    span: tuple
    delete: str
    marker: int
    restart: tuple | None = None
    move: tuple | None = None

    def shifted(self, offset: int) -> "AdmittedCorrection":
        """The same correction in a containing text that starts ``offset``
        code points earlier (a split-retry half inside its parent)."""
        def shift(points):
            return tuple(p + offset for p in points) if points else points
        return AdmittedCorrection(shift(self.span), self.delete, self.marker + offset,
                                  shift(self.restart), shift(self.move))


def correction_view(source: str, corrections: list, protected=()) -> tuple:
    """Return the comparison source and authorized correction coordinates.

    ``corrections`` are AdmittedCorrection records for ``source``. Moves
    are exact and local, not model-proposed rewrites. Original source and
    original deletion coordinates remain the engine's stored record.
    Protected occurrences cannot straddle the insertion point. Exact
    redundant restarts extend comparison spans while the engine continues
    to record the original marker-terminated proposal spans.
    """
    view = source
    rebased = [(c.span[0], c.restart[1] if c.restart else c.span[1], c.marker)
               for c in corrections]
    positions = [tuple(p[:2]) for p in protected]
    for start, end, destination in sorted(
            (c.move for c in corrections if c.move), reverse=True):
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
