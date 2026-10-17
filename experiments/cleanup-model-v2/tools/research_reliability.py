"""Agreement between judge vendors and order stability of each judge (aggregates only).

  research_reliability.py OUT.json --judge anthropic=V.jsonl [--judge openai=...] \
      [--swapped anthropic=VS.jsonl ...]

Unit: one (case, system) delivered output. Metrics: pass rate per judge; pairwise observed agreement and
Cohen's kappa on judged_pass and on each flag; Krippendorff's alpha across all supplied judges on
judged_pass; for each judge with a swapped-order run, the share of outputs whose judged_pass changed
and the pass-rate difference between orders. Unjudged outputs are omitted from agreement and counted.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cleanup-model"))

from v2.stats import cohen_kappa, krippendorff_alpha  # noqa: E402
from research_analysis import FLAGS, judged_metrics, read_jsonl  # noqa: E402


def table(path):
    out, unjudged = {}, 0
    for row in read_jsonl(path):
        if row["stage"] != "delivered":
            continue
        key = (row["case_id"], row["model"])
        if row.get("status") == "judged" and row.get("verdict"):
            out[key] = {**judged_metrics(row["verdict"]), **{f: float(row["verdict"][f]) for f in FLAGS},
                        "cleanup": row["verdict"]["cleanup"]}
        else:
            out[key] = None
            unjudged += 1
    return out, unjudged


def agreement(a, b, field):
    keys = sorted(set(a) & set(b))
    x = [None if a[k] is None else a[k][field] for k in keys]
    y = [None if b[k] is None else b[k][field] for k in keys]
    kappa = cohen_kappa(x, y)
    return {"n": kappa["n"], "observed_agreement": kappa.get("observed_agreement"), "kappa": kappa["kappa"]}


def main():
    out = Path(sys.argv[1])
    main_runs, swapped_runs, result = {}, {}, {"unjudged_outputs": {}}
    args = sys.argv[2:]
    for i in range(0, len(args), 2):
        kind, spec = args[i], args[i + 1]
        backend, path = spec.split("=", 1)
        target = main_runs if kind == "--judge" else swapped_runs
        target[backend], missing = table(path)
        result["unjudged_outputs"][f"{backend}{'' if kind == '--judge' else ':swapped'}"] = missing
    result["pass_rate"] = {b: (lambda v: sum(x["judged_pass"] for x in v) / len(v))([x for x in t.values() if x]) for b, t in main_runs.items()}
    result["pairwise"] = {}
    for a, b in itertools.combinations(sorted(main_runs), 2):
        result["pairwise"][f"{a} vs {b}"] = {field: agreement(main_runs[a], main_runs[b], field)
                                             for field in ("judged_pass", "judged_clean", *FLAGS)}
    if len(main_runs) >= 2:
        keys = sorted(set.intersection(*[set(t) for t in main_runs.values()]))
        units = [[None if main_runs[b][k] is None else main_runs[b][k]["judged_pass"] for b in sorted(main_runs)] for k in keys]
        result["krippendorff_alpha_judged_pass"] = krippendorff_alpha(units)
    result["order_stability"] = {}
    for backend, swapped in swapped_runs.items():
        base = main_runs.get(backend)
        if not base:
            continue
        keys = [k for k in sorted(set(base) & set(swapped)) if base[k] and swapped[k]]
        flips = sum(base[k]["judged_pass"] != swapped[k]["judged_pass"] for k in keys)
        result["order_stability"][backend] = {
            "outputs": len(keys), "judged_pass_changed": flips, "share_changed": flips / len(keys) if keys else None,
            "pass_rate_forward": sum(base[k]["judged_pass"] for k in keys) / len(keys) if keys else None,
            "pass_rate_reversed": sum(swapped[k]["judged_pass"] for k in keys) / len(keys) if keys else None}
    out.write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps({"judges": sorted(main_runs), "swapped": sorted(swapped_runs)}))


if __name__ == "__main__":
    main()
