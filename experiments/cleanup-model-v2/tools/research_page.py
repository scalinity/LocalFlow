"""Build the local comparison page for the cleanup study.

Every figure comes from the committed results directory; the worked examples come from the
private development outputs, cases and Opus verdicts under ARTIFACTS. The page embeds case
text, so OUTPUT belongs in an ignored location (reports/localflow-cleanup-comparison-v2/).

usage: research_page.py RESULTS_DIR ARTIFACTS_DIR OUTPUT_HTML
"""
import datetime
import json
import sys
from pathlib import Path

# key, label, plain description, family, size, start, seed-0 evaluation label
SYSTEMS = [
    ("C", "C", "today's model", "today", "4B", "continue", "C-merged"),
    ("M2", "M2", "new data, continued from C", "new", "4B", "continue", "M2s0-ck426"),
    ("M1", "M1", "new data, fresh adapter", "new", "4B", "fresh", "M1s0-ck426"),
    ("M3", "M3", "new data, 9B", "new", "9B", "fresh", "M3-ck426"),
    ("A1", "A1", "new data without contrast pairs", "ingredient", "4B", "fresh", "A1-ck624"),
    ("A3", "A3", "new data, vetoed rows kept", "ingredient", "4B", "fresh", "A3-ck434"),
    ("A2prime", "A2′", "earlier data, continued from C", "earlier", "4B", "continue", "A2prime-ck199"),
    ("A2", "A2", "earlier data, fresh adapter", "earlier", "4B", "fresh", "A2-ck199"),
    ("base-4b-prod-prompt", "4B", "Qwen3.5 4B, untuned", "untuned", "4B", "fresh", "base-4b-prod-prompt"),
    ("base-9b-prod-prompt", "9B", "Qwen3.5 9B, untuned", "untuned", "9B", "fresh", "base-9b-prod-prompt"),
]
CATEGORIES = {
    "boundary_questions": "Questions at sentence boundaries", "function_words": "Function words",
    "identifier_corrections": "Identifier corrections", "list_structure": "List structure",
    "multiple_corrections": "Several corrections", "phrase_boundaries": "Phrase boundaries",
    "quantity_qualifier": "Quantity qualifiers", "restriction_scope": "Restriction scope",
}
FLAGS = ("semantic_damage", "critical_fact_changed", "hallucination", "unwanted_edit")


def load(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def mean(values, key):
    return values[key]["mean"] if key in values else None


def arm_block(analysis):
    out = {}
    for key, *_ in SYSTEMS:
        v = analysis["arm_values"][key]
        out[key] = {
            "opus": mean(v, "anthropic:judged_pass"), "opus_seeds": v["anthropic:judged_pass"]["seeds"],
            "opus_sd": v["anthropic:judged_pass"]["seed_sd"],
            "sol": mean(v, "openai:judged_pass"), "muse": mean(v, "openrouter:judged_pass"),
            "damage": mean(v, "engine_damage"), "damage_seeds": v["engine_damage"]["seeds"],
            "noop": mean(v, "engine_noop_preserved"), "repair": mean(v, "engine_repair_success"),
            "complete": mean(v, "anthropic:judged_cleanup_complete"),
            "semantic": mean(v, "anthropic:judged_semantic_damage"),
            "unwanted": mean(v, "anthropic:judged_unwanted_edit"),
        }
    return out


def contrast_rows(rows):
    keep = ("contrast", "first", "second", "metric", "difference_first_better", "ci95", "ci95_first_better",
            "ci_adjusted_bonferroni", "p", "p_holm", "superiority_supported", "polarity")
    return [{k: r[k] for k in keep if k in r} for r in rows]


def examples(artifacts, opus_verdicts):
    cases = {c["case_id"]: c for c in jsonl(artifacts / "refinement/dataset/validation.jsonl")}
    outputs = {key: {r["case_id"]: r["delivered"] for r in jsonl(artifacts / f"eval/development-{label}.jsonl")}
               for key, *_, label in SYSTEMS}
    labels = {label: key for key, *_, label in SYSTEMS}
    verdicts = {}
    for row in jsonl(opus_verdicts):
        if row["stage"] == "delivered" and row["model"] in labels and row["status"] == "judged":
            verdicts[(row["case_id"], labels[row["model"]])] = row["verdict"]

    def view(cid):
        out = {}
        for key, *_ in SYSTEMS:
            v = verdicts.get((cid, key))
            flags = [f for f in FLAGS if v and v[f]]
            out[key] = {"text": outputs[key][cid], "pass": bool(v and not flags and v["cleanup"] in ("complete", "none_needed")),
                        "flags": flags, "cleanup": v and v["cleanup"], "reason": v and v["reason"]}
        return out

    candidates = []
    for cid, case in sorted(cases.items()):
        if not 110 <= len(case["model_input"]) <= 460 or any((cid, k) not in verdicts for k, *_ in SYSTEMS):
            continue
        out = view(cid)
        distinct = len({o["text"] for o in out.values()})
        passes = sum(o["pass"] for o in out.values())
        if distinct >= 4 and 2 <= passes <= 8:
            candidates.append((cid, case, out, distinct))
    # Buckets show the study's contrasts in order; within a bucket the most varied, shortest case wins.
    buckets = [
        ("C misses it; M2 gets it", lambda c, o: not o["C"]["pass"] and o["M2"]["pass"], 2),
        ("The earlier data repairs more", lambda c, o: o["A2"]["pass"] and not o["M2"]["pass"], 2),
        ("Should be left alone", lambda c, o: c["is_noop"] and any(o[k]["flags"] for k, *_ in SYSTEMS), 1),
        ("Untuned models rewrite", lambda c, o: any(o[k]["flags"] for k in ("base-4b-prod-prompt", "base-9b-prod-prompt")), 1),
        ("The 9B and the 4B disagree", lambda c, o: o["M3"]["pass"] != o["M1"]["pass"], 1),
    ]
    chosen, used = [], set()
    for title, test, count in buckets:
        pool = sorted((c for c in candidates if c[0] not in used and test(c[1], c[2])),
                      key=lambda c: (-c[3], len(c[1]["model_input"]), c[0]))
        for cid, case, out, _ in pool[:count]:
            used.add(cid)
            topic = case["category"].split("_", 1)[1] if case["category"].startswith(("preserve_", "repair_")) else case["category"]
            chosen.append({"title": title, "category": CATEGORIES.get(topic, "Long instructions"),
                           "is_noop": case["is_noop"], "source": case["model_input"], "reference": case["target"],
                           "outputs": out})
    return chosen


def main(results_dir, artifacts_dir, output):
    results, artifacts = Path(results_dir), Path(artifacts_dir)
    analysis = load(results / "analysis.json")
    reliability = load(results / "judge_reliability.json")
    supp = results / "supplementary"
    normalized = load(supp / "normalized_references_selected/analysis.json")
    final = load(supp / "final_checkpoints/analysis.json")
    normalized_final = load(supp / "normalized_references_final/analysis.json")
    categories = load(results / "categories_selected.json")
    latency = load(results / "latency.json")
    original = {c["case_id"]: c for c in jsonl(artifacts / "refinement/dataset/validation.jsonl")}
    rewritten = {c["case_id"]: c for c in jsonl(artifacts / "research/dev-normalized/validation.jsonl")}
    repairs = [k for k, c in original.items() if not c["is_noop"]]
    data = {
        "generated": datetime.date.today().isoformat(),
        "systems": [dict(zip(("key", "label", "about", "family", "size", "start", "eval"), s)) for s in SYSTEMS],
        "arm": arm_block(analysis),
        "judge_runs": analysis["judge_runs"], "unjudged_rows": analysis["judge_unjudged_rows"],
        "contrasts": {m: contrast_rows(rows) for m, rows in analysis["contrasts"].items()},
        "versus_c": {m: contrast_rows([r for r in rows if r["second"] == "C"])
                     for m, rows in analysis["exploratory_contrasts"].items()
                     if m in ("anthropic:judged_pass", "engine_damage", "anthropic:judged_semantic_damage")},
        "references": {k: {"original": mean(analysis["arm_values"][k], "anthropic:judged_pass"),
                           "rewritten": mean(normalized["arm_values"][k], "anthropic:judged_pass"),
                           "original_final": mean(final["arm_values"][k], "anthropic:judged_pass"),
                           "rewritten_final": mean(normalized_final["arm_values"][k], "anthropic:judged_pass")}
                       for k, *_ in SYSTEMS},
        "rewritten_references": {"repair_cases": len(repairs),
                                 "changed": sum(rewritten[k]["target"] != original[k]["target"] for k in repairs)},
        "categories": categories,
        "latency": {k: {"median_s": v["total_cleanup_ms"]["median"] / 1000, "p95_s": v["total_cleanup_ms"]["p95"] / 1000,
                        "first_token_s": v["first_token_ms_median"] / 1000, "peak_gb": v["peak_mlx_gb"],
                        "fallback": v["fallback_rate"]} for k, v in latency.items()},
        "selection": load(results / "selection.json"),
        "reliability": {"kappa": {k: v["judged_pass"]["kappa"] for k, v in reliability["pairwise"].items()},
                        "alpha": reliability["krippendorff_alpha_judged_pass"]["alpha"],
                        "order": reliability["order_stability"], "pass_rate": reliability["pass_rate"],
                        "unjudged": reliability["unjudged_outputs"]},
        "costs": load(results / "judge_costs.json"),
        "examples": examples(artifacts, artifacts / "judge/dev-main-anthropic/verdicts.jsonl"),
    }
    template = (Path(__file__).with_name("research_page_template.html")).read_text()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    Path(output).write_text(template.replace("/*DATA*/null", payload))
    print(json.dumps({"output": str(output), "examples": len(data["examples"])}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
