"""Render results/RESULTS.md and CSV tables from the analysis outputs. Aggregates only; never edited by hand.

  research_report.py RESULTS_DIR

Reads RESULTS_DIR/analysis.json (required) and, when present, latency.json, selection.json, judge_costs.json,
judge_reliability.json. Writes RESULTS.md and arm_values.csv.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROWS = [
    ("anthropic:judged_pass", "Opus judged pass (primary)"), ("anthropic:judged_clean", "Opus judged no-flag"),
    ("anthropic:judged_semantic_damage", "Opus semantic damage"), ("anthropic:judged_hallucination", "Opus hallucination"),
    ("anthropic:judged_unwanted_edit", "Opus unwanted edit"), ("anthropic:judged_cleanup_complete", "Opus cleanup complete"),
    ("openai:judged_pass", "gpt-6.1-sol judged pass"), ("openrouter:judged_pass", "Muse judged pass"),
    ("engine_damage", "Engine damage"), ("engine_noop_preserved", "Engine no-op preserved"),
    ("engine_repair_success", "Engine repair success"), ("engine_correction_success", "Engine correction success"),
]
ORDER = ["C", "base-4b-prod-prompt", "base-9b-prod-prompt", "sonnet-5-5-fewshot", "opus-5-5-fewshot",
         "A2prime", "A2", "A1", "A3", "M1", "M2", "M3"]


def pct(x, digits=1):
    return "-" if x is None else f"{100 * x:.{digits}f}%"


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def arm_table(analysis):
    arms = [a for a in ORDER if a in analysis["available_arms"]]
    lines = ["| Metric | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for metric, label in ROWS:
        cells = []
        for arm in arms:
            v = analysis["arm_values"].get(arm, {}).get(metric)
            if not v:
                cells.append("-")
                continue
            sd = v.get("seed_sd")
            cells.append(pct(v["mean"]) + (f" (sd {100 * sd:.1f})" if sd is not None else ""))
        if any(c != "-" for c in cells):
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines), arms


def contrast_table(rows):
    lines = ["| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s = r.get("polarity", 1)
        lo, hi = sorted(s * x for x in r["ci95"])
        alo, ahi = sorted(s * x for x in r["ci_adjusted_bonferroni"])
        sup = r.get("superiority_supported")
        ni = r.get("noninferiority_supported")
        verdict = ("noninferior: " + ("yes" if ni else "no")) if ni is not None else ("-" if sup is None else ("yes" if sup else "no"))
        lines.append(f"| {r['contrast']} | {r['n_cases']} | {100 * r['difference_first_better']:+.2f} pts | [{100 * lo:+.2f}, {100 * hi:+.2f}] | "
                     f"[{100 * alo:+.2f}, {100 * ahi:+.2f}] | {r['p']:.4f} | {r['p_holm']:.4f} | "
                     f"{'-' if r['reference_seed_sd'] is None else f'{100 * r['reference_seed_sd']:.2f} pts'} | {verdict} |")
    return "\n".join(lines)


def main():
    out = Path(sys.argv[1])
    analysis = load(out / "analysis.json")
    latency, selection = load(out / "latency.json"), load(out / "selection.json")
    costs, reliability = load(out / "judge_costs.json"), load(out / "judge_reliability.json")
    parts = ["# Results (generated; do not edit)", "",
             "Development set, 431 cases, delivered text, selected checkpoint of each run. Percent values; seed spread is the sample SD over seeds (M1, M2 only).",
             f"Bootstrap: {analysis['resamples']} resamples, seed {analysis['seed']}. Unjudged rows counted as failures: {analysis['judge_unjudged_rows']}.", ""]
    table, arms = arm_table(analysis)
    parts += ["## Arm values", "", table, ""]
    for metric, rows in analysis["contrasts"].items():
        parts += [f"## Contrasts on {metric}", "", contrast_table(rows), ""]
    for metric, rows in analysis.get("exploratory_contrasts", {}).items():
        parts += [f"## Exploratory contrasts on {metric} (outside the pre-declared family; no multiplicity adjustment)", "",
                  "| Contrast | n | Difference (first better) | 95% interval | p |", "|---|---|---|---|---|"]
        for r in rows:
            lo, hi = r["ci95_first_better"]
            parts.append(f"| {r['contrast']} | {r['n_cases']} | {100 * r['difference_first_better']:+.2f} pts | [{100 * lo:+.2f}, {100 * hi:+.2f}] | {r['p']:.4f} |")
        parts.append("")
    if analysis.get("h2_subset"):
        h2 = analysis["h2_subset"]
        parts += ["## H2 subset (list and question cases)", "",
                  f"{h2['list_question_cases']} cases: {h2['no_change_cases']} need no change, {h2['repair_cases']} need repair. Underpowered; exploratory.", "",
                  "| Metric | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
        for key, per in h2["metrics"].items():
            cells = [("-" if per.get(a, {}).get("n") in (None, 0) else f"{per[a]['events']:.0f}/{per[a]['n']}" if key.split('@')[0].endswith(('unnecessary_edit', 'damage', 'unwanted_edit')) else pct(per[a]['mean'])) for a in arms]
            if any(c != "-" for c in cells):
                parts.append(f"| {key} | " + " | ".join(cells) + " |")
        parts.append("")
    checkpoints = load(out / "checkpoints.json")
    if checkpoints:
        parts += ["## Selected versus final checkpoint (programmatic, delivered text)", "",
                  "| Run | Damage selected / final | No-op preserved selected / final | Repair success selected / final | Corrections selected / final |", "|---|---|---|---|---|"]
        for run, rec in checkpoints.items():
            cells = [f"{pct(rec['selected'][m])} / {pct(rec['final'][m])}" for m in ("engine_damage", "engine_noop_preserved", "engine_repair_success", "engine_correction_success")]
            parts.append(f"| {run} ({rec['selected']['label']}, {rec['final']['label']}) | " + " | ".join(cells) + " |")
        parts.append("")
    if latency:
        parts += ["## Latency (sequential clean pass on an idle Mac, 4-bit)", "",
                  "| System | median total (s) | p95 total (s) | median first token (s) | peak MLX (GB) | fallback | same text as earlier run |", "|---|---|---|---|---|---|---|"]
        for arm in ORDER:
            r = latency.get(arm)
            if r:
                eq = r.get("delivered_equals_earlier_run")
                parts.append(f"| {arm} | {r['total_cleanup_ms']['median'] / 1000:.2f} | {r['total_cleanup_ms']['p95'] / 1000:.2f} | "
                             f"{r['first_token_ms_median'] / 1000:.2f} | {r['peak_mlx_gb']:.1f} | {pct(r['fallback_rate'])} | "
                             f"{'-' if not eq else str(eq['equal']) + '/' + str(eq['of'])} |")
        parts.append("")
    if selection:
        parts += ["## Model selection (ANALYSIS_PLAN.md rule)", "", f"Decision: **{selection['decision']}**"
                  + (f", winner {selection.get('winner')}, shipped run {selection.get('shipped_run')}" if selection.get("winner") else ""), ""]
        if selection.get("reason"):
            parts += [selection["reason"], ""]
        for step in selection["steps"]:
            if "gates" in step:
                bad = [k for k, g in step["gates"].items() if not g["passed"]]
                parts.append(f"- {step['arm']}: " + ("passed every gate" if not bad else "failed " + ", ".join(bad)))
            elif "survivors" in step:
                parts.append(f"- survivors {step['survivors']}; best by score {step['best_by_score']}; tied with best {step['tied_with_best']}")
        parts.append("")
    if costs:
        parts += ["## Costs", "", "| Item | USD |", "|---|---|"] + [f"| {k} | {v:.2f} |" for k, v in costs.items()] + [""]
    if reliability:
        parts += ["## Judge reliability", "", "```json", json.dumps(reliability, indent=1)[:4000], "```", ""]
    (out / "RESULTS.md").write_text("\n".join(parts))
    with open(out / "arm_values.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "metric", "mean", "seed_sd", "seeds", "n"])
        for arm, metrics in analysis["arm_values"].items():
            for metric, v in metrics.items():
                w.writerow([arm, metric, v["mean"], v["seed_sd"], json.dumps(v["seeds"]), v["n"]])
    print(json.dumps({"written": ["RESULTS.md", "arm_values.csv"]}))


if __name__ == "__main__":
    main()
