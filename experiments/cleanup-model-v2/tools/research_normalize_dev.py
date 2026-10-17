"""Re-reference the development set to the minimal-edit policy (supplementary, post-hoc).

  research_normalize_dev.py OUT.jsonl

Each development target is passed through `v2.policy_score.minimal_target`, the policy the new training
labels were normalized to. A target that normalizes is replaced by its normalized form; a target the
policy excludes (it needs a structure that was not dictated) is kept as it was. Inputs, categories and
no-op flags are untouched. Prints the counts. The output holds case text and stays private.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cleanup-model"))

from v2.policy_score import minimal_target  # noqa: E402


def main():
    source = HERE / "artifacts" / "refinement" / "dataset" / "validation.jsonl"
    cases = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    stats, by_category, rows = collections.Counter(), collections.Counter(), []
    for case in cases:
        normalized, changes, exclusion = minimal_target(case["model_input"], case["target"], case.get("vocabulary_pairs") or [])
        if exclusion:
            stats["kept_policy_exclusion"] += 1
            rows.append(case)
        elif normalized != case["target"] or changes:
            stats["normalized"] += 1
            by_category[case["category"]] += 1
            rows.append({**case, "target": normalized, "reference_policy": "minimal-edit-normalized"})
        else:
            stats["unchanged"] += 1
            rows.append(case)
    Path(sys.argv[1]).parent.mkdir(parents=True, exist_ok=True)
    Path(sys.argv[1]).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(json.dumps({"cases": len(rows), **stats, "normalized_by_category": dict(sorted(by_category.items()))}))


if __name__ == "__main__":
    main()
