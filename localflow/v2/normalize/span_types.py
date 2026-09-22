"""Typed spans and edit ledger for spoken-syntax normalization (M04, S10).

All text offsets are zero-based half-open Unicode code-point offsets
(contracts/artifacts.md); they never mix with UTF-16 or token offsets.
Every edit carries its parsed value and the operation/reason that produced
it, so a later check can see that ``twelve percent`` and ``12%`` represent
the same value without re-running the grammar.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any, Optional

SCHEMA_VERSION = 1

# Grammar classes whose edits are number-word→digit representation changes
# (AC05: scored separately from lexical ASR, never as recognition edits).
NUMERIC_CLASSES = frozenset({
    "integer", "anchored_integer", "unit_number", "decimal", "percent",
    "percentage_points", "currency", "time", "date", "version", "ip",
    "port", "code", "phone", "dimension",
})


def _value_json(value: Any) -> Any:
    """A JSONable representation of a parsed value (Decimal → string)."""
    if isinstance(value, Decimal):
        return str(value)
    return value


@dataclasses.dataclass(frozen=True)
class Span:
    """Zero-based half-open [start, end) code-point span."""

    start: int
    end: int

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: "Span") -> bool:
        return self.start <= other.start and other.end <= self.end

    def as_pair(self) -> list[int]:
        return [self.start, self.end]


# Join behavior used when assembling the output text.
JOIN_WORD = "word"          # replacement sits between its neighbors
JOIN_ATTACH_LEFT = "left"   # trailing punctuation: swallows the space before
JOIN_ATTACH_RIGHT = "right" # leading punctuation: swallows the space after
JOIN_TIGHT = "tight"        # intra-word symbols (hyphen, underscore): no
                            # spaces either side
JOIN_PAIR = "pair"          # delimiting symbols (asterisk): the first
                            # occurrence attaches right, its match left
JOIN_BLOCK = "block"        # structural newline output: joins both sides


@dataclasses.dataclass(frozen=True)
class Proposal:
    """One grammar's candidate rewrite before conflict resolution."""

    layer: int              # precedence layer (1 literal escape … 5 vocab)
    cls: str                # grammar class, e.g. "percent"
    op: str                 # operation, e.g. "number_word_to_digits"
    span: Span
    input_text: str
    output_text: str
    value: Any = None       # exact parsed value (int/Decimal/str)
    unit: Optional[str] = None
    join: str = JOIN_WORD
    reason: Optional[str] = None
    review: bool = False    # surface as a review suggestion, never applied

    def to_edit(self, output_span: Span) -> "EditRecord":
        return EditRecord(
            cls=self.cls, op=self.op, input_span=self.span,
            output_span=output_span, input_text=self.input_text,
            output_text=self.output_text, value=self.value, unit=self.unit,
            layer=self.layer, reason=self.reason)


@dataclasses.dataclass(frozen=True)
class EditRecord:
    """An accepted edit in the ledger: replayable against the input text."""

    cls: str
    op: str
    input_span: Span
    output_span: Span
    input_text: str
    output_text: str
    value: Any
    unit: Optional[str]
    layer: int
    reason: Optional[str]

    def to_json(self) -> dict:
        return {
            "cls": self.cls, "op": self.op,
            "input_span": self.input_span.as_pair(),
            "output_span": self.output_span.as_pair(),
            "input_text": self.input_text, "output_text": self.output_text,
            "value": _value_json(self.value), "unit": self.unit,
            "layer": self.layer, "reason": self.reason,
        }

    @staticmethod
    def from_json(d: dict) -> "EditRecord":
        return EditRecord(
            cls=d["cls"], op=d["op"],
            input_span=Span(*d["input_span"]),
            output_span=Span(*d["output_span"]),
            input_text=d["input_text"], output_text=d["output_text"],
            value=d["value"], unit=d.get("unit"), layer=d.get("layer", 4),
            reason=d.get("reason"))


@dataclasses.dataclass(frozen=True)
class RejectedProposal:
    """A proposal that was considered and not applied, with its reason."""

    cls: str
    op: str
    span: Span
    input_text: str
    output_text: str
    value: Any
    unit: Optional[str]
    reason: str            # e.g. overlap_conflict, ambiguous_same_span,
                           # invalid_value, unknown_skill, protected_span

    def to_json(self) -> dict:
        return {
            "cls": self.cls, "op": self.op, "span": self.span.as_pair(),
            "input_text": self.input_text,
            "output_text": self.output_text,
            "value": _value_json(self.value), "unit": self.unit,
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True)
class ProtectedSpan:
    """A span no grammar may rewrite, with why it is protected."""

    span: Span
    kind: str              # literal_escape | quoted | existing_syntax

    def to_json(self) -> dict:
        return {"span": self.span.as_pair(), "kind": self.kind}


class NormalizationResult:
    """Outcome of one normalization pass; the ledger is the source of truth.

    ``replay`` re-applies the ledger to the retained input and must
    reproduce ``text`` byte for byte (AC05). ``is_idempotent`` evaluates a
    second pass on the output and reports it honestly, including the
    documented corner where a literal-escape emits a bare command word
    (S10 escape arrow) that a second pass would then convert.
    """

    def __init__(self, text: str, edits: list[EditRecord],
                 rejected: list[RejectedProposal],
                 protected: list[ProtectedSpan],
                 policy_revision: str, applied: bool,
                 duration_ms: Optional[float] = None):
        self.text = text
        self.edits = edits
        self.rejected = rejected
        self.protected = protected
        self.policy_revision = policy_revision
        self.applied = applied
        self.duration_ms = duration_ms
        self._idempotent: Optional[bool] = None

    # ---- ledger replay (AC05) ---------------------------------------------

    def replay(self, input_text: str) -> str:
        """Rebuild the output from the ledger alone (no grammar re-run)."""
        out = input_text
        for edit in sorted(self.edits,
                           key=lambda e: e.input_span.start,
                           reverse=True):
            s, e = edit.input_span.start, edit.input_span.end
            if input_text[s:e] != edit.input_text:
                raise ValueError(
                    f"ledger desync at {s}:{e}: {input_text[s:e]!r} != "
                    f"{edit.input_text!r}")
            out = out[:s] + edit.output_text + out[e:]
        return out

    # ---- metrics ------------------------------------------------------------

    def class_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.edits:
            counts[e.cls] = counts.get(e.cls, 0) + 1
        return counts

    @property
    def number_word_to_digit_count(self) -> int:
        """Number-word→digit edits, scored separately from lexical ASR
        (AC05): these are representation changes, not recognition."""
        return sum(1 for e in self.edits if e.cls in NUMERIC_CLASSES)

    def is_idempotent(self, policy, context=None) -> bool:
        if self._idempotent is None:
            from .engine import normalize as _normalize
            second = _normalize(self.text, policy, context)
            self._idempotent = (second.text == self.text
                                and not second.edits)
        return self._idempotent

    @property
    def idempotence(self) -> Optional[bool]:
        """The evaluated idempotence result, or None before/without
        evaluation (null, never a guessed False)."""
        return self._idempotent

    # ---- serialization -------------------------------------------------------

    def to_json(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_revision": self.policy_revision,
            "applied": self.applied,
            "text": self.text,
            "edits": [e.to_json() for e in self.edits],
            "rejected": [r.to_json() for r in self.rejected],
            "protected": [p.to_json() for p in self.protected],
            "class_counts": self.class_counts(),
            "number_word_to_digit_count": self.number_word_to_digit_count,
            "duration_ms": self.duration_ms,
        }
