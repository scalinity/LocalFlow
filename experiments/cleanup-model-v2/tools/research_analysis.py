"""Pre-registered analysis of the development-set evaluations (aggregates only in the public output).

Implements docs/v2/research/ANALYSIS_PLAN.md: per-case metric vectors from engine scores and judge
verdicts, arm values (seed means), the seven pre-declared contrasts with one shared set of
bootstrap resamples, Holm adjustment, Bonferroni-width adjusted intervals, the seed-SD rule,
and the list/question (H2) subset. No case text is read into the public output.

Usage:
  PYTHONPATH=experiments/cleanup-model-v2:experiments/cleanup-model .venv/bin/python \
    experiments/cleanup-model-v2/tools/research_analysis.py ARMS.json --out-dir DIR \
    --judge anthropic=PATH/verdicts.jsonl [--judge openai=...] [--judge openrouter=...]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cleanup-model"))

SEED = 20261015
RESAMPLES = 10000
ALPHA = 0.05
LQ_SUFFIXES = ("list_structure", "boundary_questions")
FLAGS = ("semantic_damage", "critical_fact_changed", "hallucination", "unwanted_edit")

# The seven pre-declared contrasts: (name, first arm, second arm, seed-SD reference arm, direction).
# direction +1: the hypothesis says the first arm is better (higher on a higher-is-better metric, lower on a
# lower-is-better one); 0: noninferiority only, no superiority claim.
CONTRASTS = [
    ("M2 vs A2prime", "M2", "A2prime", "M2", +1),
    ("M1 vs A2", "M1", "A2", "M1", +1),
    ("M1 vs A1", "M1", "A1", "M1", +1),
    ("M1 vs A3", "M1", "A3", "M1", +1),
    ("M3 vs M1", "M3", "M1", "M1", +1),
    ("M2 vs sonnet-5-5-fewshot", "M2", "sonnet-5-5-fewshot", "M2", 0),
    ("M2 vs opus-5-5-fewshot", "M2", "opus-5-5-fewshot", "M2", 0),
]
LOWER_IS_BETTER = ("damage", "unnecessary_edit", "hallucination", "omission", "fact_changed", "facts_changed",
                   "negation_changed", "unwanted_edit")
NONINFERIORITY_MARGIN = {"M2 vs sonnet-5-5-fewshot": 0.03, "M2 vs opus-5-5-fewshot": 0.03}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def judged_metrics(verdict):
    """Per-output judged metrics (ANALYSIS_PLAN.md)."""
    flags = any(verdict[f] for f in FLAGS)
    return {"judged_pass": float((not flags) and verdict["cleanup"] in ("complete", "none_needed")),
            "judged_clean": float(not flags), "judged_semantic_damage": float(verdict["semantic_damage"]),
            "judged_fact_changed": float(verdict["critical_fact_changed"]),
            "judged_hallucination": float(verdict["hallucination"]),
            "judged_unwanted_edit": float(verdict["unwanted_edit"]),
            "judged_cleanup_complete": float(verdict["cleanup"] == "complete")}


def engine_metrics(cases, art, label):
    from v2 import score
    rows = {r["case_id"]: r for r in read_jsonl(art / "eval" / f"development-{label}.jsonl")}
    if set(rows) != set(cases):
        return None  # an incomplete evaluation is never scored as if it were whole
    out = {}
    for cid, case in cases.items():
        row = rows.get(cid)
        if row is None:
            continue
        m = score.synthetic(case, row.get("delivered"), True)
        wanted = ("damage", "facts_changed", "hallucination", "omission", "negation_changed", "noop_preserved",
                  "unnecessary_edit", "reference_complete", "reference_repair", "repair_success",
                  "correction_success", "punctuation_repaired", "punctuation_exact")
        out[cid] = {f"engine_{k}": float(m[k]) for k in wanted if m.get(k) is not None}
    return out


def judge_table(path):
    """(case_id, model label) -> judged metrics at the delivered stage; unjudged rows are failures."""
    table, missing = {}, 0
    for row in read_jsonl(path):
        if row["stage"] != "delivered":
            continue
        if row.get("status") == "judged" and row.get("verdict"):
            table[(row["case_id"], row["model"])] = judged_metrics(row["verdict"])
        else:
            missing += 1
            table[(row["case_id"], row["model"])] = {k: (0.0 if k == "judged_pass" or k == "judged_clean" else None) for k in
                                                     ("judged_pass", "judged_clean", "judged_semantic_damage", "judged_fact_changed",
                                                      "judged_hallucination", "judged_unwanted_edit", "judged_cleanup_complete")}
    return table, missing


def polarity(metric):
    """+1 when a higher value is better, -1 when a lower value is better."""
    return -1 if any(token in metric for token in LOWER_IS_BETTER) else 1


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def arm_vectors(arms, per_system):
    """arm -> metric -> case_id -> mean over the arm's seeds (cases where every seed defines the metric)."""
    out = {}
    for arm, labels in arms.items():
        have = [per_system[l] for l in labels if l in per_system]
        if len(have) != len(labels):
            continue
        out[arm] = {}
        metrics = set().union(*[set(m) for s in have for m in s.values()])
        for metric in sorted(metrics):
            vec = {}
            for cid in have[0]:
                vals = [s.get(cid, {}).get(metric) for s in have]
                if all(v is not None for v in vals):
                    vec[cid] = sum(vals) / len(vals)
            out[arm][metric] = vec
    return out


def seed_values(arms, per_system, arm, metric):
    vals = []
    for label in arms[arm]:
        v = [m.get(metric) for m in per_system[label].values() if m.get(metric) is not None]
        vals.append(sum(v) / len(v) if v else None)
    return vals


def bootstrap(diffs_by_contrast, ids, resamples=None, seed=SEED):
    resamples = resamples or RESAMPLES
    """One set of resampled case indices shared by every contrast (percentile bootstrap)."""
    rng = random.Random(seed)
    n = len(ids)
    names = list(diffs_by_contrast)
    vecs = {k: [diffs_by_contrast[k][i] for i in ids] for k in names}
    samples = {k: [] for k in names}
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        for k in names:
            v = vecs[k]
            samples[k].append(sum(v[i] for i in idx) / n)
    return samples


def quantile(sorted_values, p):
    index = (len(sorted_values) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (index - lo)


def interval(samples, level):
    s = sorted(samples)
    tail = (1 - level) / 2
    return [quantile(s, tail), quantile(s, 1 - tail)]


def p_two_sided(samples):
    r = len(samples)
    le = (sum(1 for x in samples if x <= 0) + 1) / (r + 1)
    ge = (sum(1 for x in samples if x >= 0) + 1) / (r + 1)
    return min(1.0, 2 * min(le, ge))


def holm_adjust(pvals):
    order = sorted(range(len(pvals)), key=lambda i: (pvals[i], i))
    adjusted, running = {}, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvals) - rank) * pvals[i]))
        adjusted[i] = running
    return [adjusted[i] for i in range(len(pvals))]


def contrast_table(vectors, arms, per_system, metric, available):
    rows = [(n, a, b, ref, d) for n, a, b, ref, d in CONTRASTS if a in available and b in available]
    if not rows:
        return []
    ids = None
    diffs = {}
    for name, a, b, ref, d in rows:
        va, vb = vectors[a].get(metric), vectors[b].get(metric)
        if va is None or vb is None:
            continue
        common = sorted(set(va) & set(vb))
        ids = common if ids is None else sorted(set(ids) & set(common))
        diffs[name] = {i: va[i] - vb[i] for i in common}
    if not diffs:
        return []
    samples = bootstrap(diffs, ids)
    k = len(CONTRASTS)
    out = []
    for name, a, b, ref, d in rows:
        if name not in diffs:
            continue
        est = sum(diffs[name][i] for i in ids) / len(ids)
        sd_vals = seed_values(arms, per_system, ref, metric)
        sd = statistics.stdev([v for v in sd_vals if v is not None]) if len([v for v in sd_vals if v is not None]) > 1 else None
        out.append({"contrast": name, "first": a, "second": b, "metric": metric, "n_cases": len(ids), "difference": est,
                    "ci95": interval(samples[name], 1 - ALPHA), "ci_adjusted_bonferroni": interval(samples[name], 1 - ALPHA / k),
                    "p": p_two_sided(samples[name]), "reference_seed_sd": sd, "direction": d,
                    "noninferiority_margin": NONINFERIORITY_MARGIN.get(name)})
    # The pre-declared family has seven contrasts; contrasts without data count as p = 1 so Holm is not loosened.
    padded = [r["p"] for r in out] + [1.0] * (k - len(out))
    adjusted = holm_adjust(padded)[:len(out)]
    sign = polarity(metric)
    for r, padj in zip(out, adjusted):
        r["p_holm"] = padj
        r["polarity"] = sign
        # Express the interval so that positive means the first arm is better.
        lo, hi = sorted((sign * x for x in r["ci_adjusted_bonferroni"]))
        good = sign * r["difference"]
        r["difference_first_better"] = good
        sd = r["reference_seed_sd"]
        if r["direction"] != 0:
            excludes = lo > 0
            exceeds = None if sd is None else good > sd
            r["superiority_supported"] = None if sd is None else bool(padj < ALPHA and excludes and exceeds)
        if r["noninferiority_margin"] is not None:
            # "M2 is noninferior": the adjusted interval's lower end (first arm better) exceeds minus the margin.
            r["noninferiority_supported"] = bool(lo > -r["noninferiority_margin"])
    return out


EXPLORATORY = [("M1 vs C", "M1", "C"), ("M2 vs C", "M2", "C"), ("M3 vs C", "M3", "C"),
               ("M2 vs base-4b-prod-prompt", "M2", "base-4b-prod-prompt"), ("M2 vs M1", "M2", "M1"),
               ("A2prime vs C", "A2prime", "C")]


def exploratory_table(vectors, available, metric):
    """Contrasts outside the pre-declared family: percentile interval and p, no multiplicity adjustment."""
    rows = [(n, a, b) for n, a, b in EXPLORATORY if a in available and b in available
            and vectors[a].get(metric) and vectors[b].get(metric)]
    if not rows:
        return []
    ids = None
    diffs = {}
    for name, a, b in rows:
        common = sorted(set(vectors[a][metric]) & set(vectors[b][metric]))
        ids = common if ids is None else sorted(set(ids) & set(common))
        diffs[name] = {i: vectors[a][metric][i] - vectors[b][metric][i] for i in common}
    samples = bootstrap(diffs, ids)
    sign = polarity(metric)
    out = []
    for name, a, b in rows:
        est = sum(diffs[name][i] for i in ids) / len(ids)
        lo, hi = sorted(sign * x for x in interval(samples[name], 1 - ALPHA))
        out.append({"contrast": name, "first": a, "second": b, "metric": metric, "n_cases": len(ids), "difference": est,
                    "difference_first_better": sign * est, "ci95_first_better": [lo, hi], "p": p_two_sided(samples[name]),
                    "polarity": sign, "exploratory": True, "multiplicity_adjusted": False})
    return out


def h2_subset(cases, vectors, available, metric_names):
    """H2 on list and question cases (A1 vs M1): wrongful-edit and repair-recall, with exact counts."""
    if not {"M1", "A1"} <= set(available):
        return None
    lq = {cid for cid, c in cases.items() if any(c["category"].endswith(s) for s in LQ_SUFFIXES)}
    preserve = sorted(cid for cid in lq if cases[cid]["is_noop"])
    repair = sorted(cid for cid in lq if not cases[cid]["is_noop"])
    out = {"list_question_cases": len(lq), "no_change_cases": len(preserve), "repair_cases": len(repair), "metrics": {}}
    for metric in metric_names:
        for subset_name, subset in (("no_change", preserve), ("repair", repair)):
            row = {}
            for arm in available:
                vec = vectors[arm].get(metric, {})
                vals = [vec[i] for i in subset if i in vec]
                row[arm] = {"n": len(vals), "mean": mean(vals), "events": sum(vals) if vals else None}
            out["metrics"][f"{metric}@{subset_name}"] = row
    return out


def main():
    global RESAMPLES
    ap = argparse.ArgumentParser()
    ap.add_argument("arms")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--judge", action="append", default=[], help="backend=path/to/verdicts.jsonl")
    ap.add_argument("--private-dir", help="per-case scores (no case text) are written here")
    ap.add_argument("--resamples", type=int, default=RESAMPLES, help="the pre-registered value is 10,000; lower only for tests")
    args = ap.parse_args()
    RESAMPLES = args.resamples
    config = json.loads(Path(args.arms).read_text())
    art = HERE / "artifacts"
    cases = {c["case_id"]: c for c in read_jsonl(art / "refinement" / "dataset" / "validation.jsonl")}
    arms = config["arms"]
    labels = sorted({l for ls in arms.values() for l in ls})
    per_system = {}
    for label in labels:
        if (art / "eval" / f"development-{label}.jsonl").exists():
            scored = engine_metrics(cases, art, label)
            if scored is not None:
                per_system[label] = scored
    judge_missing = {}
    for spec in args.judge:
        backend, path = spec.split("=", 1)
        table, missing = judge_table(path)
        judge_missing[backend] = missing
        for label in labels:
            if label not in per_system:
                continue
            for cid in per_system[label]:
                m = table.get((cid, label))
                if m:
                    per_system[label][cid].update({f"{backend}:{k}": v for k, v in m.items() if v is not None})
    available = [a for a, ls in arms.items() if all(l in per_system for l in ls)]
    vectors = arm_vectors(arms, per_system)
    metrics = sorted({m for a in available for m in vectors[a]})
    arm_values = {}
    for arm in available:
        arm_values[arm] = {}
        for metric in metrics:
            vec = vectors[arm].get(metric)
            if not vec:
                continue
            seeds = seed_values(arms, per_system, arm, metric)
            clean = [s for s in seeds if s is not None]
            arm_values[arm][metric] = {"n": len(vec), "mean": mean(vec.values()), "seeds": seeds,
                                       "seed_sd": statistics.stdev(clean) if len(clean) > 1 else None}
    primary = "anthropic:judged_pass"
    results = {"seed": SEED, "resamples": RESAMPLES, "arms": arms, "available_arms": available,
               "judge_unjudged_rows": judge_missing, "arm_values": arm_values, "contrasts": {}}
    for metric in ([primary] if primary in metrics else []) + [m for m in metrics if m != primary and (m.startswith(("openai:judged_pass", "openrouter:judged_pass", "engine_damage", "engine_repair_success", "engine_noop")))]:
        table = contrast_table(vectors, arms, per_system, metric, available)
        if table:
            results["contrasts"][metric] = table
    results["exploratory_contrasts"] = {}
    for metric in [primary] + [m for m in metrics if m.endswith(("judged_clean", "judged_unwanted_edit", "judged_cleanup_complete", "judged_semantic_damage"))] + ["engine_damage"]:
        table = exploratory_table(vectors, available, metric) if metric in metrics else []
        if table:
            results["exploratory_contrasts"][metric] = table
    results["h2_subset"] = h2_subset(cases, vectors, available,
                                     [m for m in metrics if m in ("engine_unnecessary_edit", "engine_reference_repair") or m.endswith(("judged_unwanted_edit", "judged_semantic_damage", "judged_cleanup_complete"))])
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(results, indent=1, sort_keys=True))
    if args.private_dir:
        Path(args.private_dir).mkdir(parents=True, exist_ok=True)
        (Path(args.private_dir) / "per_case_scores.json").write_text(json.dumps(per_system))
    print(json.dumps({"arms": available, "metrics": len(metrics), "contrast_metrics": list(results["contrasts"])}))


if __name__ == "__main__":
    main()
