"""Punctuation and layout policy checks, separate from exact reference matching.

Repairs may need a boundary or accept an optional comma, but a label's optional
polish is not required, and an output must not add, remove or replace
punctuation the label kept. Paragraph breaks come only from spoken commands, so
a blank line the source lacks is counted as invented formatting. Every model is
scored identically against the same source and label.
"""
from __future__ import annotations

import difflib
import re

WORD = re.compile(r"\w+(?:['’]\w+)*")
BOUNDARY = set(".!?;:")
FIELDS = ("invented_breaks", "extra_format_edits")


def _split(text):
    """Casefolded words and the n + 1 gaps around them (leading and trailing included)."""
    matches = list(WORD.finditer(text))
    words = [m.group().casefold().replace("’", "'") for m in matches]
    bounds = [0] + [x for m in matches for x in (m.start(), m.end())] + [len(text)]
    return words, [text[bounds[i]:bounds[i + 1]] for i in range(0, len(bounds), 2)]


def _marks(gap):
    return "".join(re.findall(r"[^\w\s]", gap))


def _blank_line(gap):
    return re.search(r"\n\s*\n", gap) is not None


def _aligned_gaps(a_words, b_words):
    """Map each b gap to the a gap between the same two consecutive matched words."""
    matched = {}
    for block in difflib.SequenceMatcher(None, a_words, b_words, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            matched[block.b + k] = block.a + k
    gaps = {0: 0, len(b_words): len(a_words)}
    for k in range(1, len(b_words)):
        j = matched.get(k - 1)
        if j is not None and matched.get(k) == j + 1:
            gaps[k] = j + 1
    return gaps


def _gap_ok(s, t, o):
    ps, pt, po = _marks(s), _marks(t), _marks(o)
    if pt == ps:
        return po == ps
    if not ps and set(pt) == {","}:
        return po in ("", ",")
    if not ps and (set(pt) & BOUNDARY or ("\n" in t and "\n" not in s)):
        return bool(po) or "\n" in o
    return po in (ps, pt)


def score(case, text):
    is_noop = case.get("is_noop")
    if text is None:
        return {"words_ok": False, "policy_repair": None if is_noop else False,
                "invented_breaks": None, "extra_format_edits": None}
    source_words, source_gaps = _split(case["model_input"])
    target_words, target_gaps = _split(case["target"])
    output_words, output_gaps = _split(text)
    target_to_source = _aligned_gaps(source_words, target_words)
    words_ok = output_words == target_words
    policy_ok = words_ok and all(
        ("?" in _marks(o)) == ("?" in _marks(t))
        and (k not in target_to_source or _gap_ok(source_gaps[target_to_source[k]], t, o))
        for k, (t, o) in enumerate(zip(target_gaps, output_gaps)))
    source_to_target = {j: k for k, j in target_to_source.items()}
    output_to_source = _aligned_gaps(source_words, output_words)
    invented = sum(_blank_line(output_gaps[k]) and not _blank_line(source_gaps[j])
                   for k, j in output_to_source.items())
    changed = sum(j in source_to_target
                  and _marks(source_gaps[j]) == _marks(target_gaps[source_to_target[j]])
                  and _marks(output_gaps[k]) != _marks(source_gaps[j])
                  for k, j in output_to_source.items())
    return {"words_ok": words_ok, "policy_repair": None if is_noop else policy_ok,
            "invented_breaks": invented, "extra_format_edits": invented + changed}


def aggregate(cases, scores):
    """Format-edit totals and per-case means for no-ops, repairs and long sources."""
    scopes = {"noop": lambda c: c["is_noop"], "repair": lambda c: not c["is_noop"],
              "long_over_200": lambda c: len(c["model_input"].split()) > 200}
    out = {}
    for scope, member in scopes.items():
        rows = [s for c, s in zip(cases, scores) if member(c)]
        measured = [s for s in rows if s["invented_breaks"] is not None]
        out[scope] = {"n": len(rows), "unavailable": len(rows) - len(measured)}
        for field in FIELDS:
            total = sum(s[field] for s in measured)
            out[scope][field] = {"total": total, "per_case": total / len(measured) if measured else None}
    return out
