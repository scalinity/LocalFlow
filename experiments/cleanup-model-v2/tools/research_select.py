"""Apply the model-selection rule of docs/v2/research/ANALYSIS_PLAN.md to the analysis outputs.

  research_select.py ANALYSIS_JSON LATENCY_JSON SIZES_JSON OUT_JSON

SIZES_JSON maps an arm to the bytes of its quantized weights (C included). Candidates: M1, M2, M3.
The rule (gates, score, ties, cross-check, keep-C fallback) is implemented exactly as written there;
nothing here chooses by looking at results.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CANDIDATES = ("M1", "M2", "M3")
PRIMARY = "anthropic:judged_pass"
CROSS = "openai:judged_pass"
DAMAGE = "anthropic:judged_semantic_damage"
FACTS = "anthropic:judged_fact_changed"
NOOP = "engine_noop_preserved"
LATENCY_FACTOR = 1.5
SIZE_FACTOR = 1.5
NOOP_FLOOR = 0.97
SHIPPED_RUN = {"M1": "M1s0-ck426", "M2": "M2s0-ck426", "M3": "M3-ck426"}


def value(analysis, arm, metric):
    return analysis["arm_values"].get(arm, {}).get(metric)


def select(analysis, latency, sizes):
    steps = []
    c = {m: (value(analysis, "C", m) or {}).get("mean") for m in (PRIMARY, CROSS, DAMAGE, FACTS, NOOP)}
    if any(c[m] is None for m in (PRIMARY, DAMAGE, FACTS, NOOP)) or "C" not in latency or "C" not in sizes:
        return {"decision": "NOT_EVALUABLE", "reason": "C's reference values, latency or size are missing", "steps": steps}
    survivors = []
    for arm in CANDIDATES:
        if arm not in analysis["available_arms"]:
            steps.append({"arm": arm, "gate": "available", "passed": False, "detail": "no evaluation"})
            continue
        v = {m: (value(analysis, arm, m) or {}).get("mean") for m in (PRIMARY, CROSS, DAMAGE, FACTS, NOOP)}
        gates = {
            "judged_damage_not_above_C": (v[DAMAGE] is not None and v[DAMAGE] <= c[DAMAGE], v[DAMAGE], c[DAMAGE]),
            "judged_fact_changes_not_above_C": (v[FACTS] is not None and v[FACTS] <= c[FACTS], v[FACTS], c[FACTS]),
            "engine_noop_preserved_at_least_0.97": (v[NOOP] is not None and v[NOOP] >= NOOP_FLOOR, v[NOOP], NOOP_FLOOR),
        }
        lat = latency.get(arm, {}).get("total_cleanup_ms", {}).get("median")
        gates["median_latency_within_1.5x_C"] = (lat is not None and lat <= LATENCY_FACTOR * latency["C"]["total_cleanup_ms"]["median"],
                                                 lat, LATENCY_FACTOR * latency["C"]["total_cleanup_ms"]["median"])
        size = sizes.get(arm)
        gates["quantized_size_within_1.5x_C"] = (size is not None and size <= SIZE_FACTOR * sizes["C"], size, SIZE_FACTOR * sizes["C"])
        passed = all(g[0] for g in gates.values())
        steps.append({"arm": arm, "gates": {k: {"passed": bool(g[0]), "value": g[1], "limit": g[2]} for k, g in gates.items()}, "passed_all": passed})
        if passed and v[PRIMARY] is not None:
            survivors.append((arm, v[PRIMARY], lat))
    if not survivors:
        return {"decision": "KEEP_C", "reason": "no candidate passed the gates", "steps": steps}
    best_arm, best_score, _ = max(survivors, key=lambda s: s[1])
    sds = {arm: (value(analysis, arm, PRIMARY) or {}).get("seed_sd") for arm, _, _ in survivors}
    tied = []
    for arm, score, lat in survivors:
        sd_pool = [sd for sd in (sds[arm], sds[best_arm]) if sd is not None]
        threshold = max(sd_pool) if sd_pool else 0.0
        if best_score - score < threshold or arm == best_arm:
            tied.append((arm, score, lat))
    steps.append({"survivors": [s[0] for s in survivors], "best_by_score": best_arm, "tied_with_best": [t[0] for t in tied]})
    if len(tied) > 1:
        fastest = min(t[2] for t in tied)
        tied = [t for t in tied if t[2] == fastest]
        if len(tied) > 1:
            tied = [t for t in tied if t[0] == "M2"] or tied
    winner = tied[0][0]
    if c[CROSS] is not None:
        winner_cross = (value(analysis, winner, CROSS) or {}).get("mean")
        if winner_cross is None or winner_cross < c[CROSS]:
            return {"decision": "JUDGE_DISAGREEMENT", "winner_by_primary": winner,
                    "reason": "the OpenAI judged pass rate of the winner is below C's", "steps": steps}
    else:
        return {"decision": "NOT_EVALUABLE", "reason": "the OpenAI cross-check is missing", "winner_by_primary": winner, "steps": steps}
    return {"decision": "SHIP", "winner": winner, "shipped_run": SHIPPED_RUN[winner], "steps": steps}


def main():
    analysis, latency, sizes = (json.loads(Path(p).read_text()) for p in sys.argv[1:4])
    result = select(analysis, latency, sizes)
    Path(sys.argv[4]).write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps({k: v for k, v in result.items() if k != "steps"}))


if __name__ == "__main__":
    main()
