"""ITN-independent local scoring for short-command text counterparts
(M04 task 7, E18.4).

Text-only: no model call, no cloud dependency (M15 owns the optional
comparator). Exact intended-token accuracy on command cases and the
false-command rate on non-command controls carry separate denominators;
number-word→digit changes are counted from the edit ledger, separately
from lexical ASR (AC05).
"""

from __future__ import annotations

from .policy import ContextSnapshot, NormalizationPolicy
from .span_types import NUMERIC_CLASSES


def score_command_corpus(cases: list[dict],
                         default_policy: NormalizationPolicy | None = None
                         ) -> dict:
    """Score short-command text counterparts.

    Each case: {"id", "input", "expected", "kind": "command"|"non_command",
                "context": {"profile", "locale", "registered_skills",
                            "identifiers"} (optional)}.
    Command cases score exact intended-token matches; non-command cases
    must pass through unchanged (a change is a false command).
    """
    policy = default_policy or NormalizationPolicy()
    from .engine import normalize

    results = []
    commands = non_commands = 0
    command_hits = 0
    false_commands = 0
    number_word_edits = 0
    for case in cases:
        ctx_policy = policy
        cctx = case.get("context") or {}
        if cctx:
            ctx_policy = NormalizationPolicy(
                locale=cctx.get("locale", policy.locale),
                profile=cctx.get("profile", policy.profile),
                registered_skills=cctx.get("registered_skills"),
                identifiers=cctx.get("identifiers"))
        snap = ContextSnapshot(identifiers=cctx.get("identifiers")) \
            if cctx.get("identifiers") else None
        res = normalize(case["input"], ctx_policy, snap)
        got = res.text
        kind = case.get("kind", "command")
        ok = got == case["expected"]
        if kind == "command":
            commands += 1
            command_hits += int(ok)
        else:
            non_commands += 1
            changed = got != case["input"]
            false_commands += int(changed)
            ok = not changed
        number_word_edits += res.number_word_to_digit_count
        results.append({
            "id": case["id"], "kind": kind, "ok": ok,
            "input": case["input"], "expected": case["expected"],
            "got": got,
            "edit_classes": res.class_counts(),
        })
    return {
        "cases": len(cases),
        "command_cases": commands,
        "command_exact_hits": command_hits,
        "command_exact_accuracy": (
            command_hits / commands) if commands else None,
        "non_command_cases": non_commands,
        "false_commands": false_commands,
        "false_command_rate": (
            false_commands / non_commands) if non_commands else None,
        "number_word_to_digit_edits": number_word_edits,
        "results": results,
    }


def separate_scores(result) -> dict:
    """AC05: split a normalization result into representation changes
    (number-word→digit, from the ledger) vs everything else, so lexical
    ASR scoring never counts representation edits."""
    numeric = [e for e in result.edits if e.cls in NUMERIC_CLASSES]
    other = [e for e in result.edits if e.cls not in NUMERIC_CLASSES]
    return {
        "number_word_to_digit_edits": len(numeric),
        "number_word_to_digit_ops": sorted({e.cls for e in numeric}),
        "other_edits": len(other),
        "other_ops": sorted({e.cls for e in other}),
        "rejected_proposals": len(result.rejected),
    }
