"""Normalization engine: typed-span precedence, conflict resolution and
edit-ledger assembly (M04, S10).

Precedence (S10): literal escape → protected existing syntax →
registered explicit skill intent → typed numeric/symbol grammar →
context-supported vocabulary → ordinary prose. Conflicts resolve by
source span (layer, then longer span, then position) — never by
substitution order. The result is idempotent and deterministic for
identical inputs.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from . import numbers as num_mod
from . import syntax as syn_mod
from .policy import ContextSnapshot, NormalizationPolicy
from .span_types import (
    JOIN_ATTACH_LEFT,
    JOIN_ATTACH_RIGHT,
    JOIN_BLOCK,
    JOIN_PAIR,
    JOIN_TIGHT,
    JOIN_WORD,
    EditRecord,
    NormalizationResult,
    Proposal,
    ProtectedSpan,
    RejectedProposal,
    Span,
)

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\u2011-][^\W\d_]+)*", re.UNICODE)
_TOKEN_RE = re.compile(r"\S+")
_WS_RE = re.compile(r"\s+")


@dataclass
class Token:
    start: int
    end: int
    word: str        # lowercase core (edge punctuation stripped for words)
    raw: str
    is_word: bool    # pure word token (no digits/symbols)


def tokenize(text: str) -> list[Token]:
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        run = m.group(0)
        wm = _WORD_RE.fullmatch(run.rstrip(".,;:!?") .lstrip(".,;:!?"))
        if wm:
            core = run.strip(".,;:!?\"'“”«»()")
            tokens.append(Token(m.start(), m.end(), core.lower(), run, True))
        else:
            tokens.append(Token(m.start(), m.end(), run.lower(), run, False))
    return tokens


class MatchHost:
    """Read-only view of the tokenized text shared by all grammars."""

    def __init__(self, text: str, policy: NormalizationPolicy,
                 context: ContextSnapshot | None):
        self.text = text
        self.policy = policy
        self.tables = policy.tables
        self.profile = policy.profile_table
        self.context = context
        self.tokens = tokenize(text)
        self._quote_zones: list[ProtectedSpan] | None = None

    def quote_zones(self) -> list[ProtectedSpan]:
        if self._quote_zones is None:
            self._quote_zones = syn_mod.find_quote_zones(self)
        return self._quote_zones

    def in_quote_zone(self, span: Span) -> bool:
        return any(z.span.overlaps(span) or z.span.contains(span)
                   for z in self.quote_zones())


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _sort_key(p: Proposal):
    return (p.layer, -(p.span.end - p.span.start), p.span.start, p.cls)


def _reject(p: Proposal, reason: str) -> RejectedProposal:
    return RejectedProposal(cls=p.cls, op=p.op, span=p.span,
                            input_text=p.input_text,
                            output_text=p.output_text, value=p.value,
                            unit=p.unit, reason=reason, rule_id=p.rule_id)


def normalize(text: str, policy: NormalizationPolicy,
              context: ContextSnapshot | None = None) -> NormalizationResult:
    t0 = time.monotonic()
    if policy.profile == "off":
        return NormalizationResult(
            text=text, edits=[], rejected=[], protected=[],
            policy_revision=policy.policy_revision, applied=False,
            duration_ms=0.0)
    host = MatchHost(text, policy, context)

    # Layer 1 + 2: quote zones first (quoted instructions are content),
    # then literal escapes outside quotes.
    quote_zones = host.quote_zones()
    escapes = list(syn_mod.find_literal_escapes(host))
    escape_zones = [z for _, z in escapes]
    protected = list(escape_zones) + list(quote_zones)

    # Collect every proposal.
    proposals: list[Proposal] = [m for m, _ in escapes]
    for grammar in num_mod.ALL_NUMERIC_GRAMMARS:
        proposals.extend(grammar(host))
    for grammar in syn_mod.ALL_SYNTAX_GRAMMARS:
        proposals.extend(grammar(host))
    proposals.extend(syn_mod.grammar_identifiers(host))
    proposals.extend(syn_mod.grammar_vocabulary(host))

    # Review suggestions never apply (unknown skills, invalid values…).
    rejected: list[RejectedProposal] = [
        _reject(p, p.reason or "review_suggestion")
        for p in proposals if p.review]
    candidates = [p for p in proposals if not p.review]

    # A flagged region (invalid octet, invalid day, unanchored version)
    # keeps its words: no smaller grammar may rewrite inside it either —
    # "flagged, never repaired" (S10). A candidate that CONTAINS the
    # flagged span (e.g. the anchored version grammar over the same
    # words) is the more specific match and still applies.
    review_spans = [p for p in proposals if p.review]
    keep = []
    for p in candidates:
        if any(r.span.contains(p.span) for r in review_spans):
            rejected.append(_reject(p, "flagged_region"))
        else:
            keep.append(p)
    candidates = keep

    # Protected spans: escape zones block everything; quote zones block
    # command-shaped grammars only.
    zone_rejected: list[RejectedProposal] = []
    keep = []
    for p in candidates:
        if p.cls == "literal_escape":
            keep.append(p)
            continue
        blocked = any(z.span.overlaps(p.span) for z in escape_zones)
        if not blocked and p.cls in syn_mod.COMMAND_CLASSES:
            blocked = any(z.span.overlaps(p.span) for z in quote_zones)
        if blocked:
            zone_rejected.append(_reject(p, "protected_span"))
        else:
            keep.append(p)
    candidates = keep

    # Exact-same-span proposals from different grammars: identical output
    # means the grammars agree — keep one deterministically (prefer the
    # unit-bearing record, then class name). Different outputs are
    # ambiguous: reject every one rather than pick by order.
    by_span: dict[tuple, list[Proposal]] = {}
    for p in candidates:
        by_span.setdefault((p.span.start, p.span.end), []).append(p)
    same_span_keep: dict[tuple, Proposal] = {}
    for k, ps in by_span.items():
        outputs = {p.output_text for p in ps}
        if len(outputs) > 1:
            for p in ps:
                rejected.append(_reject(p, "ambiguous_same_span"))
        else:
            same_span_keep[k] = sorted(
                ps, key=lambda p: (p.unit is None, p.cls))[0]

    # Greedy accept by (layer, longer span, position, class): overlap
    # losers are rejected with their reason, never substituted.
    accepted: list[Proposal] = []
    for p in sorted(same_span_keep.values(), key=_sort_key):
        if any(p.span.overlaps(a.span) for a in accepted):
            rejected.append(_reject(p, "overlap_conflict"))
        else:
            accepted.append(p)

    edits = _assemble(host, accepted)
    duration_ms = (time.monotonic() - t0) * 1000.0
    return NormalizationResult(
        text=_apply(host.text, edits),
        edits=[e.edit for e in edits],
        rejected=rejected + zone_rejected,
        protected=protected,
        policy_revision=policy.policy_revision,
        applied=True,
        duration_ms=duration_ms)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

@dataclass
class _AppliedEdit:
    edit: EditRecord
    eff_start: int   # effective span after join-space swallowing
    eff_end: int


def _assemble(host, accepted: list[Proposal]) -> list[_AppliedEdit]:
    """Compute join-extended effective spans left-to-right, then emit
    EditRecords (output spans filled by the caller's apply pass).

    Tight symbols are pair-aware: the first unmatched occurrence swallows
    the space to its right (opening), the next matching occurrence
    swallows the space to its left (closing) — "asterisk bold asterisk"
    renders "*bold*" with outer spacing intact, and an unpaired one
    behaves as an opening join.
    """
    ordered = sorted(accepted, key=lambda p: p.span.start)
    out: list[_AppliedEdit] = []
    prev_end = 0
    open_tight: dict[str, bool] = {}
    for idx, p in enumerate(ordered):
        start, end = p.span.start, p.span.end
        nxt_start = ordered[idx + 1].span.start if idx + 1 < len(ordered) \
            else len(host.text)
        join = p.join
        if join == JOIN_TIGHT:
            while start > prev_end and host.text[start - 1].isspace():
                start -= 1
            while end < nxt_start and host.text[end].isspace():
                end += 1
        elif join == JOIN_PAIR:
            if open_tight.get(p.output_text):
                # Closing occurrence: attach to the word before it.
                while start > prev_end and host.text[start - 1].isspace():
                    start -= 1
                open_tight[p.output_text] = False
            else:
                # Opening occurrence: attach to the word after it.
                while end < nxt_start and host.text[end].isspace():
                    end += 1
                open_tight[p.output_text] = True
        else:
            if join in (JOIN_ATTACH_LEFT, JOIN_BLOCK):
                while start > prev_end and host.text[start - 1].isspace():
                    start -= 1
            if join in (JOIN_ATTACH_RIGHT, JOIN_BLOCK):
                while end < nxt_start and host.text[end].isspace():
                    end += 1
            if join == JOIN_ATTACH_LEFT:
                # "hello comma there" already carries its own comma:
                # swallow an immediately-following duplicate symbol.
                sym = p.output_text
                probe = end
                if probe < nxt_start and host.text[probe] == " ":
                    probe += 1
                if probe < nxt_start and sym and \
                        host.text[probe:probe + len(sym)] == sym:
                    end = min(probe + len(sym), nxt_start)
        out.append(_AppliedEdit(edit=None, eff_start=start, eff_end=end))
        out[-1].edit = _make_edit(host, p, start, end)
        prev_end = end
    return out


def _make_edit(host, p: Proposal, eff_start: int, eff_end: int) -> EditRecord:
    input_text = host.text[eff_start:eff_end]
    output_text = p.output_text
    if p.join == JOIN_BLOCK:
        # Structural output: no leading break when the command opens the
        # text, no trailing break when it closes it — but a block command
        # that IS the whole utterance keeps its break (that is the
        # command's content).
        has_left = any(not c.isspace()
                       for c in host.text[:eff_start])
        has_right = any(not c.isspace()
                        for c in host.text[eff_end:])
        if not has_left and has_right:
            output_text = output_text.lstrip("\n")
        elif has_left and not has_right:
            output_text = output_text.rstrip("\n")
    return EditRecord(
        cls=p.cls, op=p.op,
        input_span=Span(eff_start, eff_end), output_span=Span(0, 0),
        input_text=input_text, output_text=output_text,
        value=p.value, unit=p.unit, layer=p.layer, reason=p.reason,
        rule_id=p.rule_id)


def _apply(text: str, applied: list[_AppliedEdit]) -> str:
    """Apply effective spans right-to-left; then compute output spans."""
    out = text
    for ae in sorted(applied, key=lambda a: a.eff_start, reverse=True):
        out = out[:ae.eff_start] + ae.edit.output_text + out[ae.eff_end:]
    # Output spans: walk accepted edits left-to-right over the output.
    delta = 0
    for ae in sorted(applied, key=lambda a: a.eff_start):
        o_start = ae.eff_start + delta
        o_end = o_start + len(ae.edit.output_text)
        ae.edit = EditRecord(
            cls=ae.edit.cls, op=ae.edit.op,
            input_span=ae.edit.input_span,
            output_span=Span(o_start, o_end),
            input_text=ae.edit.input_text,
            output_text=ae.edit.output_text, value=ae.edit.value,
            unit=ae.edit.unit, layer=ae.edit.layer,
            reason=ae.edit.reason, rule_id=ae.edit.rule_id)
        delta += len(ae.edit.output_text) \
            - (ae.eff_end - ae.eff_start)
    return out
