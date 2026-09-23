"""Requirement atoms and the coverage map (V2 M11, Spec S16).

The Prompt Engineer's own contract: extract the draft's explicit
requirement atoms, then report which output span carries each atom.
Coverage is deterministic (excerpt/keyword/anchor based) and honestly
three-valued — ``covered`` (an output span carries the atom),
``uncertain`` (partial evidence only) and ``missing`` (no evidence). A
missing or uncertain atom is a review issue: the original clause is
kept for display and the result is never silently applied — it degrades
to review (never auto-applied) with the original wording surfaced
beside the diff (S16's "keep the original clause or mark a review
issue, rather than dropping it as 'irrelevant'").
"""

from __future__ import annotations

import dataclasses
import re
from typing import Optional

# Atom kinds (the S16 extraction list): explicit task/constraint
# carriers that must survive a prompt reorganization.
QUESTION = "question"
NEGATION = "negation"
COUNT = "count"
ORDERING = "ordering"
EDIT_CONSTRAINT = "edit_constraint"
QUOTED = "quoted"
LINK = "link"
DEADLINE = "deadline"
UNCERTAINTY = "uncertainty"

# Deterministic patterns. Negation and uncertainty multisets follow the
# M07 validator's vocabulary discipline.
_NEGATION_CUES = ("don't", "dont", "do not", "does not", "doesn't",
                  "never", "must not", "cannot", "can not", "won't",
                  "will not", "shall not", "not ")
_UNCERTAINTY_CUES = ("maybe", "might", "possibly", "perhaps",
                     "not sure", "unsure", "if possible", "or not",
                     "whether or not", "i think")
_EDIT_CONSTRAINT_CUES = ("don't edit", "do not edit", "dont edit",
                         "without editing", "don't modify",
                         "do not modify", "don't change",
                         "do not change", "no edits", "don't delete",
                         "do not delete", "don't run", "do not run",
                         "don't implement", "do not implement",
                         "diagnosis only", "read only", "proposal only")
_ORDERING_CUES = ("first", "then", "after that", "before", "second",
                  "third", "finally", "next", "lastly", "prior to",
                  "once", "until")
_DEADLINE_CUES = ("by end of", "before end of", "deadline",
                  "due by", "no later than", "within ", "today",
                  "tomorrow", "tonight", "this week", "next week",
                  "monday", "tuesday", "wednesday", "thursday",
                  "friday", "saturday", "sunday")
_QUESTION_STARTERS = ("what", "why", "how", "when", "who", "where",
                      "which", "can ", "could ", "would ", "should ",
                      "is ", "are ", "do ", "does ", "did ", "any ")

_NUM_WORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|"
             r"eleven|twelve|\d+)")
_COUNT_RE = re.compile(
    rf"\b(?:exactly |precisely |at (?:most|least) |up to |no more than )?"
    rf"{_NUM_WORD}\s+[a-z-]+", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_PATH_RE = re.compile(
    r"(?:[\w.-]+/)+[\w.-]+|\B\.[\w]+\b|[\w.-]+\.(?:py|js|ts|json|md|"
    r"yaml|yml|toml|sh|sql|env)\b")
_QUOTED_RE = re.compile(r"[\"“]([^\"”]{1,120})[\"”]")


@dataclasses.dataclass(frozen=True)
class Atom:
    kind: str
    excerpt: str          # the source clause that carries the atom
    anchors: tuple        # strings that evidence coverage in output
    start: int = 0
    end: int = 0

    def to_json(self) -> dict:
        return {"kind": self.kind, "excerpt": self.excerpt,
                "anchors": list(self.anchors),
                "start": self.start, "end": self.end}


@dataclasses.dataclass(frozen=True)
class Coverage:
    atom: Atom
    status: str           # covered | uncertain | missing
    output_start: Optional[int] = None
    output_end: Optional[int] = None
    evidence: str = ""    # the matched anchor / partial evidence

    @property
    def review_issue(self) -> bool:
        return self.status in ("uncertain", "missing")

    def to_json(self) -> dict:
        return {"kind": self.kind, "status": self.status,
                "source_start": self.atom.start,
                "source_end": self.atom.end,
                "kept_excerpt": self.atom.excerpt,
                "anchors": list(self.atom.anchors),
                "output_start": self.output_start,
                "output_end": self.output_end,
                "evidence": self.evidence}


def _sentence_spans(text: str):
    """Rough clause spans on unpunctuated/punctuated draft text. The
    span covers the stripped clause: start advances past leading
    whitespace so ``[start, start+len(s))`` addresses the excerpt."""
    for m in re.finditer(r"[^.!?\n]+[.?!]?\s*", text):
        raw = m.group(0)
        s = raw.strip()
        if s:
            start = m.start() + (len(raw) - len(raw.lstrip()))
            yield start, start + len(s), s


def _content_words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z][\w'’-]*", s.lower())
            if w not in ("the", "a", "an", "and", "or", "to", "of",
                         "in", "on", "for", "with", "is", "are", "be",
                         "it", "its", "this", "that", "as", "at", "by")]


def extract_atoms(source: str) -> list[Atom]:
    """Deterministic requirement-atom extraction from the draft. Every
    atom carries its source excerpt and the anchors that evidence its
    survival in a reorganized output."""
    atoms: list[Atom] = []
    spans = list(_sentence_spans(source))

    def clause_span(idx):
        start, end, s = spans[idx]
        return start, end, s

    for i, (start, end, s) in enumerate(spans):
        low = " " + s.lower() + " "
        if s.rstrip().endswith("?") or any(
                low.strip().startswith(q) for q in _QUESTION_STARTERS):
            words = _content_words(s)
            anchors = tuple(words[:6]) or (s.strip(),)
            atoms.append(Atom(QUESTION, s.strip(), anchors, start, end))
        negs = [c for c in _NEGATION_CUES if c in low]
        if negs:
            words = _content_words(s)
            anchors = (negs[0].strip(),) + tuple(
                w for w in words if w not in negs[0].split())[:4]
            atoms.append(Atom(NEGATION, s.strip(), anchors, start, end))
        if any(c in low for c in _EDIT_CONSTRAINT_CUES):
            cue = next(c for c in _EDIT_CONSTRAINT_CUES if c in low)
            words = _content_words(s)
            atoms.append(Atom(
                EDIT_CONSTRAINT, s.strip(),
                (cue.strip(),) + tuple(words[:4]), start, end))
        if any(c in low for c in _UNCERTAINTY_CUES):
            cue = next(c for c in _UNCERTAINTY_CUES if c in low)
            words = _content_words(s)
            atoms.append(Atom(
                UNCERTAINTY, s.strip(),
                (cue.strip(),) + tuple(words[:3]), start, end))
        if any(c in low for c in _DEADLINE_CUES):
            cue = next(c for c in _DEADLINE_CUES if c in low)
            words = _content_words(s)
            atoms.append(Atom(
                DEADLINE, s.strip(),
                (cue.strip(),) + tuple(words[:3]), start, end))
        ords = [c for c in _ORDERING_CUES
                if re.search(rf"\b{re.escape(c)}\b", low)]
        if ords:
            words = _content_words(s)
            atoms.append(Atom(
                ORDERING, s.strip(),
                (ords[0],) + tuple(words[:3]), start, end))
        for m in _COUNT_RE.finditer(s):
            atoms.append(Atom(
                COUNT, m.group(0).strip(),
                (m.group(0).strip().lower(),),
                start + m.start(), start + m.end()))

    # Exact-carry classes: quoted spans, URLs and technical paths must
    # appear verbatim in the output (case-sensitive — an identifier is
    # not a suggestion).
    for m in _QUOTED_RE.finditer(source):
        atoms.append(Atom(QUOTED, m.group(0),
                          (m.group(0),), m.start(), m.end()))
    for m in _URL_RE.finditer(source):
        atoms.append(Atom(LINK, m.group(0), (m.group(0),),
                          m.start(), m.end()))
    for m in _PATH_RE.finditer(source):
        tok = m.group(0)
        if "/" in tok or tok.startswith(".") or re.search(
                r"\.(py|js|ts|json|md|yaml|yml|toml|sh|sql|env)$", tok):
            atoms.append(Atom(LINK, tok, (tok,), m.start(), m.end()))

    # Deduplicate identical (kind, excerpt) atoms from overlapping
    # sentence/clause spans, preserving first-seen order.
    seen: set = set()
    out = []
    for a in atoms:
        key = (a.kind, a.excerpt.lower())
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def _find_anchor(anchor: str, output: str,
                 case_sensitive: bool) -> Optional[tuple[int, int]]:
    """Locate an anchor. Single-word anchors match on word boundaries
    (a bare substring would let "not" be "covered" by "annotated" —
    the false-covered direction is the unsafe one); multi-word
    anchors match by contained phrase (hyphen/spacing variants are
    the model's representation freedom)."""
    hay = output if case_sensitive else output.lower()
    needle = anchor if case_sensitive else anchor.lower()
    if re.search(r"\s", needle):
        idx = hay.find(needle)
    else:
        m = re.search(rf"\b{re.escape(needle)}\b", hay)
        return (m.start(), m.end()) if m else None
    if idx < 0:
        return None
    return idx, idx + len(anchor)


def cover(atom: Atom, output: str) -> Coverage:
    """Three-valued coverage of one atom against a candidate output.
    ``covered`` needs positive evidence (an anchor located); anchors
    partially present (key content words found but no full anchor) are
    ``uncertain`` — honest, never guessed into covered."""
    first: Optional[Coverage] = None
    for anchor in atom.anchors:
        # Quoted spans and links/identifiers carry verbatim
        # (case-sensitive — an identifier is not a suggestion); counts
        # match case-insensitively with their value in the anchor.
        case_sensitive = atom.kind in (QUOTED, LINK)
        hit = _find_anchor(anchor, output, case_sensitive)
        if hit is not None:
            return Coverage(atom, "covered", hit[0], hit[1], anchor)
        if first is None:
            # Partial evidence: the anchor's distinctive words mostly
            # present, order-free (≥ 3/4 of content words, min 1).
            words = _content_words(anchor)
            if words:
                present = sum(1 for w in words
                              if re.search(rf"\b{re.escape(w)}\b",
                                           output.lower()))
                if present and present / len(words) >= 0.75:
                    first = Coverage(atom, "uncertain", None, None,
                                     f"{present}/{len(words)} words")
    if first is not None:
        return first
    return Coverage(atom, "missing")


def coverage_map(source: str, output: str) -> list[Coverage]:
    """The S16 requirement-atom map: every extracted atom with its
    output span or its review issue."""
    return [cover(a, output) for a in extract_atoms(source)]


def review_issues(coverage: list[Coverage]) -> list[Coverage]:
    return [c for c in coverage if c.review_issue]


def coverage_summary(coverage: list[Coverage]) -> dict:
    """Content-free summary for the evidence envelope (counts only)."""
    by = {}
    for c in coverage:
        by[c.status] = by.get(c.status, 0) + 1
    return {"atoms": len(coverage), "covered": by.get("covered", 0),
            "uncertain": by.get("uncertain", 0),
            "missing": by.get("missing", 0)}
