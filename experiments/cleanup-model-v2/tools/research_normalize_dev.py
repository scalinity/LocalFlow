"""Re-reference cases to the minimal-edit policy.

  research_normalize_dev.py OUT.jsonl [--input CASES.jsonl] [--changed CHANGED.jsonl]

Each target is passed through `v2.policy_score.minimal_target`, the policy the new training
labels were normalized to. A target that normalizes is replaced by its normalized form; a target the
policy excludes (it needs a structure that was not dictated) is kept as it was. Inputs, categories and
no-op flags are untouched. The input defaults to the development set (supplementary, post-hoc);
Amendment 1 rewrites the final references once, after the seal. --changed also writes the rows that
differ from their input, beside OUT. OUT.record.json holds the source, rewritten and changed-subset
hashes, which `v2.refinement.require_final` reads to accept the rewrite for judging. Prints the
counts. The outputs hold case text and stay private.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cleanup-model"))

from v2.common import file_sha256  # noqa: E402
from v2.policy_score import minimal_target  # noqa: E402


def write_rows(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--input", type=Path, default=HERE / "artifacts" / "refinement" / "dataset" / "validation.jsonl")
    ap.add_argument("--changed", type=Path, help="also write only the rows the rewrite changes")
    args = ap.parse_args(argv)
    if args.changed and args.changed.resolve().parent != args.out.resolve().parent:
        ap.error("--changed must sit beside OUT, where its record is read")
    cases = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
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
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_rows(args.out, rows)
    changed = [row for row, case in zip(rows, cases) if row != case]
    record = {"source": str(args.input), "source_sha256": file_sha256(args.input),
              "rewritten_sha256": file_sha256(args.out), "cases": len(rows), "changed": len(changed),
              "tool_sha256": file_sha256(Path(__file__)), "policy_sha256": file_sha256(HERE / "v2" / "policy_score.py")}
    if args.changed:
        write_rows(args.changed, changed)
        record["changed_sha256"] = file_sha256(args.changed)
    args.out.with_suffix(".record.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps({"cases": len(rows), **stats, "changed": len(changed),
                      "normalized_by_category": dict(sorted(by_category.items()))}))


if __name__ == "__main__":
    main()
