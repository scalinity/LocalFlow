"""Offline baseline cost projection and cumulative submission caps.

Prices are the experiment's recorded batch prices, not a live price lookup.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .common import ART, CONFIG, PRICES, read_json

PURPOSE = "research_baseline_generation"
CAP_USD = 6.0
CLOUD = {"sonnet-5-5-fewshot": "claude-sonnet-5-5",
         "opus-5-5-fewshot": "claude-opus-5-5"}


def input_bound(params):
    # Same deliberately conservative byte bound used by v2.data.wave.
    return len(json.dumps({k: v for k, v in params.items() if k != "model"},
                          ensure_ascii=False).encode()) + 1500


def charge_bound(params):
    if not isinstance(params["max_tokens"], int) or params["max_tokens"] < 1:
        raise ValueError("max_tokens must be a positive integer")
    price = PRICES[params["model"]]
    return (input_bound(params) * max(price["input"], price["cache_write"])
            + params["max_tokens"] * price["output"]) / 1e6


def amount(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Ledger amounts must be finite and nonnegative")
    return value


def estimate(ledger, plans, *, global_cap=None, new_upper=None):
    """Estimate from settled generation/judging receipts; enforce upper bounds.

    Plans cover the no-split pass. Adaptive retries are checked again before
    every submission; their cost is never silently assumed to be zero.
    """
    entries = ledger["entries"]
    history = [e for e in entries.values() if e["state"] == "settled"
               and e.get("purpose") in ("generation", "judging")]
    if not history or not any(e.get("purpose") == "generation" for e in history) \
            or not any(e.get("purpose") == "judging" for e in history):
        raise ValueError("Need settled generation and judging ledger entries")
    actual = sum(amount(e.get("actual_usd", 0)) for e in entries.values())
    outstanding = sum(amount(e["max_usd"]) for e in entries.values() if e["state"] == "outstanding")
    reserved = sum(amount(v) for v in ledger.get("reservations", {}).values())
    baseline = [e for e in entries.values() if e.get("purpose") == PURPOSE]
    baseline_used = sum(amount(e.get("actual_usd", 0)) +
                        (amount(e["max_usd"]) if e["state"] == "outstanding" else 0)
                        for e in baseline)
    historical_max = sum(amount(e["max_usd"]) for e in history)
    ratio = min(1.0, sum(amount(e.get("actual_usd", 0)) for e in history) / max(historical_max, 1e-12))
    systems = {}
    for plan in plans:
        system = plan["system"]
        if system not in CLOUD or any(p["model"] != CLOUD[system] for p in plan["requests"].values()):
            raise ValueError("Unexpected baseline system/model")
        upper = sum(charge_bound(p) for p in plan["requests"].values())
        systems[system] = {"calls_without_splits": len(plan["requests"]),
                           "estimated_usd": upper * ratio, "upper_usd": upper}
    if len(systems) != len(plans):
        raise ValueError("Duplicate baseline plan")
    upper = sum(s["upper_usd"] for s in systems.values()) if new_upper is None else amount(new_upper)
    cap = min(CONFIG["claude"]["stop_at_usd"], CONFIG["claude"]["spend_cap_usd"])
    if global_cap is not None:
        cap = min(cap, amount(global_cap))
    result = {"systems": systems, "settled_history_entries": len(history),
              "settled_usage": {k: sum(e.get("usage", {}).get(k, 0) for e in history)
                                for k in ("input", "output", "cache_write", "cache_read")},
              "historical_actual_to_reserved_ratio": ratio,
              "estimated_usd": sum(s["estimated_usd"] for s in systems.values()),
              "new_upper_usd": upper, "baseline_used_and_outstanding_usd": baseline_used,
              "combined_projected_usd": baseline_used + upper, "baseline_cap_usd": CAP_USD,
              "global_projected_usd": actual + outstanding + reserved + upper,
              "global_cap_usd": cap,
              "scope": "no-split projection; every adaptive submission is recapped cumulatively"}
    result["allowed"] = result["combined_projected_usd"] <= CAP_USD and result["global_projected_usd"] <= cap
    return result


def require_budget(ledger, plans, **kwargs):
    result = estimate(ledger, plans, **kwargs)
    if not result["allowed"]:
        raise RuntimeError("Baseline cost cap exceeded: " + json.dumps(result, sort_keys=True))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("plans", nargs=2, type=Path)
    p.add_argument("--ledger", type=Path, default=ART / "claude/ledger.json")
    a = p.parse_args()
    plans = [read_json(path) for path in a.plans]
    if {x["system"] for x in plans} != set(CLOUD):
        p.error("Supply one plan for each of Sonnet and Opus")
    result = estimate(read_json(a.ledger), plans)
    print(json.dumps(result, indent=2))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
