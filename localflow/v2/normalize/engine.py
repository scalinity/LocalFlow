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

import bisect
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
# Edge punctuation a word token may carry. It is never part of the
# token's lexical CORE: an edit covers the core only, so "twelve
# percent." keeps its period and "twelve dollars, please" its comma
# (M04-AUDIT-02).
EDGE_PUNCT = ".,;:!?\"'“”«»()"


@dataclass
class Token:
    start: int
    end: int
    word: str        # lowercase core (edge punctuation stripped for words)
    raw: str
    is_word: bool    # pure word token (no digits/symbols)
    core_start: int = -1   # code-point span of the lexical core (words:
    core_end: int = -1     # edge punctuation excluded; others: the run)
    lead: bool = False     # carries leading edge punctuation
    trail: bool = False    # carries trailing edge punctuation

    @property
    def core(self) -> str:
        return self.raw[self.core_start - self.start:
                        self.core_end - self.start]


def tokenize(text: str) -> list[Token]:
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        run = m.group(0)
        wm = _WORD_RE.fullmatch(run.rstrip(".,;:!?") .lstrip(".,;:!?"))
        if wm:
            core = run.strip(EDGE_PUNCT)
            lead = len(run) - len(run.lstrip(EDGE_PUNCT))
            trail = len(run) - len(run.rstrip(EDGE_PUNCT))
            tokens.append(Token(m.start(), m.end(), core.lower(), run, True,
                                m.start() + lead, m.end() - trail,
                                bool(lead), bool(trail)))
        else:
            tokens.append(Token(m.start(), m.end(), run.lower(), run, False,
                                m.start(), m.end()))
    return tokens


# Every character str.splitlines() treats as a line boundary — a
# paragraph or record separator is as much a delimiter as "\n"
# (review R14) — plus the unit separator U+001F, the one C0
# information separator splitlines() omits (M05 review R18). Unicode
# space separators (category Zs) and the tab stay benign word gaps.
_LINE_BREAKS = frozenset(
    "\n\r\x0b\x0c\x1c\x1d\x1e\x1f\x85\u2028\u2029")


def _barriers(text: str, tokens: list[Token]) -> list[bool]:
    """brk[k] is True when a STRUCTURAL delimiter separates token k-1
    from token k: edge punctuation between them (a comma, a sentence
    period, a quote or parenthesis) or a line break. Plain spaces, tabs
    and no-break spaces are benign. No grammar may parse a phrase
    across a barrier (M04-AUDIT-02): "twenty, five percent" is two
    quantities, never 25%."""
    brk = [False] * len(tokens)
    for k in range(1, len(tokens)):
        a, b = tokens[k - 1], tokens[k]
        gap = text[a.end:b.start]
        brk[k] = a.trail or b.lead or any(ch in _LINE_BREAKS for ch in gap)
    return brk


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
        self.brk = _barriers(text, self.tokens)
        self._words = [tk.word for tk in self.tokens]
        # run_end[i]: first token index after i that starts a new
        # clause (a barrier precedes it), or len(tokens).
        n = len(self.tokens)
        self.run_end = [n] * (n + 1)
        for k in range(n - 1, -1, -1):
            self.run_end[k] = k + 1 if k + 1 < n and self.brk[k + 1] \
                else self.run_end[k + 1]
        # Barrier gaps (left core end, right core start), in text order.
        self._gap_left = []
        self._gap_right = []
        for k in range(1, n):
            if self.brk[k]:
                self._gap_left.append(self.tokens[k - 1].core_end)
                self._gap_right.append(self.tokens[k].core_start)
        self._quote_zones: list[ProtectedSpan] | None = None
        self._code_zones: list[ProtectedSpan] | None = None

    # ---- structural boundaries (M04-AUDIT-02) ------------------------------

    def connected(self, i: int, j: int) -> bool:
        """Tokens i..j-1 form one phrase: no barrier between them."""
        if i < 0:
            i = 0
        if j - i <= 1 or i >= len(self.tokens):
            return True
        return min(j, len(self.tokens)) <= self.run_end[i]

    def words(self, i: int, n: int) -> list[str]:
        """Up to n token words from i, stopping at the first barrier."""
        if i < 0 or i >= len(self.tokens):
            return []
        return self._words[i:min(i + n, self.run_end[i])]

    def crosses_barrier(self, span: Span) -> bool:
        """The span covers a structural delimiter between two of its
        tokens (the delimiter is outside every token core)."""
        k = bisect.bisect_right(self._gap_left, span.start)
        return k < len(self._gap_left) and self._gap_right[k] < span.end

    def core_span(self, i: int, j: int) -> Span:
        """Code-point span of tokens i..j-1, lexical cores only."""
        return Span(self.tokens[i].core_start, self.tokens[j - 1].core_end)

    def quote_zones(self) -> list[ProtectedSpan]:
        if self._quote_zones is None:
            self._quote_zones = syn_mod.find_quote_zones(self)
        return self._quote_zones

    def code_zones(self) -> list[ProtectedSpan]:
        if self._code_zones is None:
            self._code_zones = syn_mod.find_code_zones(self)
        return self._code_zones

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


# Review reasons that mark a STRUCTURED candidate the grammar recognized
# but refuses as a whole (invalid, malformed, ambiguous or quantified).
# Such a region is owned: no other proposal may rewrite any part of it —
# not only proposals inside it, but also ones that straddle its edge
# (a valid four-octet prefix of a five-part dotted chain, the "five
# percent" tail of "point five percent"). A proposal that CONTAINS the
# whole region (the anchored version grammar over an unanchored
# version-shaped run) is the more specific match and still applies
# (M04-AUDIT-04/-07/-08).
STRUCTURAL_REVIEW_REASONS = frozenset({
    "invalid_day", "invalid_date", "invalid_octet", "unanchored_version",
    "invalid_version", "malformed_scale", "quantified_scale",
    "dotted_number_arity", "leading_decimal", "invalid_port",
    "incomplete_path",
})

# Classes the structural-delimiter safety net leaves to their owning
# milestone's own matching rules (M05 vocabulary, M10 snippets and file
# tags); every M04 grammar is held to it.
_BARRIER_EXEMPT = frozenset({"literal_escape", "vocabulary", "snippet",
                             "file_tag"})


def normalize(text: str, policy: NormalizationPolicy,
              context: ContextSnapshot | None = None) -> NormalizationResult:
    t0 = time.monotonic()
    if policy.profile == "off":
        return NormalizationResult(
            text=text, edits=[], rejected=[], protected=[],
            policy_revision=policy.policy_revision, applied=False,
            duration_ms=0.0)
    host = MatchHost(text, policy, context)

    # Layer 1 + 2: code zones (already-written code is protected
    # existing syntax), quote zones (quoted instructions are content),
    # then literal escapes outside both.
    code_zones = host.code_zones()
    quote_zones = host.quote_zones()
    escapes = list(syn_mod.find_literal_escapes(host))
    escape_zones = [z for _, z in escapes]
    protected = list(escape_zones) + list(quote_zones) + list(code_zones)

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
    # "flagged, never repaired" (S10). Structural refusals also own
    # their edges (STRUCTURAL_REVIEW_REASONS). A candidate that CONTAINS
    # the flagged span (e.g. the anchored version grammar over the same
    # words) is the more specific match and still applies.
    review_spans = [p for p in proposals if p.review]
    keep = []
    for p in candidates:
        if any(r.span.contains(p.span) for r in review_spans) or any(
                r.reason in STRUCTURAL_REVIEW_REASONS
                and r.span.overlaps(p.span)
                and not p.span.contains(r.span) for r in review_spans):
            rejected.append(_reject(p, "flagged_region"))
        elif p.cls not in _BARRIER_EXEMPT and host.crosses_barrier(p.span):
            rejected.append(_reject(p, "crosses_delimiter"))
        else:
            keep.append(p)
    candidates = keep

    # Protected spans: code and escape zones block everything (an escape
    # marker inside a code zone included); quote zones block
    # command-shaped grammars only.
    zone_rejected: list[RejectedProposal] = []
    keep = []
    for p in candidates:
        if any(z.span.overlaps(p.span) for z in code_zones):
            zone_rejected.append(_reject(p, "protected_span"))
            continue
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

    # Exact-same-span proposals. The S10 precedence chain decides FIRST,
    # whatever the outputs: the highest-precedence layer present owns
    # the span and every lower-layer proposal is rejected — also when
    # its output text happens to be identical, because the retained
    # record's layer decides later overlaps and carries the provenance
    # (M04-AUDIT-14; M10: a snippet trigger over a same-span dictionary
    # alias composes instead of annihilating both). Within the owning
    # layer, identical output AND identical typed value agree: keep one
    # deterministically (the unit-bearing record, then class name).
    # Different outputs — or the same text with different typed
    # values — at one layer are ambiguous: reject every one rather than
    # pick by order.
    by_span: dict[tuple, list[Proposal]] = {}
    for p in candidates:
        by_span.setdefault((p.span.start, p.span.end), []).append(p)
    same_span_keep: dict[tuple, Proposal] = {}
    for k, ps in by_span.items():
        top = min(p.layer for p in ps)
        for p in ps:
            if p.layer > top:
                rejected.append(_reject(p, "lower_layer_same_span"))
        ps = [p for p in ps if p.layer == top]
        outputs = {p.output_text for p in ps}
        values = {_value_key(p.value) for p in ps}
        if len(outputs) > 1 or len(values) > 1:
            for p in ps:
                rejected.append(_reject(p, "ambiguous_same_span"))
        else:
            same_span_keep[k] = sorted(
                ps, key=lambda p: (p.unit is None, p.cls))[0]

    # Greedy accept by (layer, longer span, position, class): overlap
    # losers are rejected with their reason, never substituted.
    # Accepted spans never overlap, so they stay sorted by start and a
    # new span can only collide with its two neighbors: O(n log n)
    # instead of a scan of every accepted span (review R22).
    accepted: list[Proposal] = []
    starts: list[int] = []
    ordered: list[Proposal] = []
    for p in sorted(same_span_keep.values(), key=_sort_key):
        k = bisect.bisect_left(starts, p.span.start)
        clash = (k < len(ordered) and ordered[k].span.overlaps(p.span)) \
            or (k > 0 and ordered[k - 1].span.overlaps(p.span))
        if clash:
            rejected.append(_reject(p, "overlap_conflict"))
        else:
            starts.insert(k, p.span.start)
            ordered.insert(k, p)
            accepted.append(p)

    edits = _assemble(host, accepted)
    out_text = _apply(host.text, edits)
    # The complete stage: tokenize, propose, arbitrate, assemble AND
    # apply (M04-AUDIT-17).
    duration_ms = (time.monotonic() - t0) * 1000.0
    return NormalizationResult(
        text=out_text,
        edits=[e.edit for e in edits],
        rejected=rejected + zone_rejected,
        protected=protected,
        policy_revision=policy.policy_revision,
        applied=True,
        duration_ms=duration_ms)


def _value_key(value) -> str | None:
    """Typed-value identity for same-span agreement (Decimal('12') and
    12 agree; 12 and -12 do not)."""
    if value is None:
        return None
    try:
        from decimal import Decimal
        if isinstance(value, (int, Decimal)) and not isinstance(value,
                                                                bool):
            return "n:" + str(Decimal(value).normalize())
    except Exception:
        pass
    return "s:" + str(value)


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
    # One left-to-right join (review R22): repeated slicing of the whole
    # string per edit was quadratic in the edit count.
    pieces = []
    pos = 0
    for ae in sorted(applied, key=lambda a: a.eff_start):
        pieces.append(text[pos:ae.eff_start])
        pieces.append(ae.edit.output_text)
        pos = ae.eff_end
    pieces.append(text[pos:])
    out = "".join(pieces)
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
