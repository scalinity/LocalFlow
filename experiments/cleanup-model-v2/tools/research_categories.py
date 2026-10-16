"""Judged pass rate by case category and arm (aggregates only).

  research_categories.py ARMS.json VERDICTS.jsonl OUT.json

Arm value per category is the mean over the arm's seeds. Categories are the development set's own labels.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research_analysis import judged_metrics, read_jsonl  # noqa: E402


def main():
    arms = json.loads(Path(sys.argv[1]).read_text())["arms"]
    cases = {c["case_id"]: c["category"] for c in read_jsonl(HERE / "artifacts" / "refinement" / "dataset" / "validation.jsonl")}
    label_arm = {label: arm for arm, labels in arms.items() for label in labels}
    seeds = {arm: len(labels) for arm, labels in arms.items()}
    sums = collections.defaultdict(lambda: collections.defaultdict(float))
    counts = collections.Counter(cases.values())
    for row in read_jsonl(sys.argv[2]):
        if row["stage"] != "delivered" or row["model"] not in label_arm:
            continue
        arm = label_arm[row["model"]]
        passed = judged_metrics(row["verdict"])["judged_pass"] if row.get("status") == "judged" and row.get("verdict") else 0.0
        sums[cases[row["case_id"]]][arm] += passed / seeds[arm]
    out = {"cases_per_category": dict(counts), "judged_pass": {cat: {arm: v / counts[cat] for arm, v in per.items()} for cat, per in sums.items()}}
    Path(sys.argv[3]).write_text(json.dumps(out, indent=1, sort_keys=True))
    print(json.dumps({"categories": len(counts)}))


if __name__ == "__main__":
    main()
