"""Read-only bottleneck measurements and preservation receipts."""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path
from .common import *


def preservation():
    identity = c_identity()
    files = list(OLD.rglob("*.py")) + [OLD / "config.yaml", OLD / "README.md"]
    files += list((ROOT / "reports/localflow-cleanup-comparison").glob("*"))
    files += list((ROOT / "localflow/v2/cleanup").glob("*.py"))
    files += [p for p in OLD_ART.rglob("*") if p.is_file() and p.suffix != ".pyc"]
    files += [p for path in (identity["snapshot_path"], identity["adapter_path"])
              for p in Path(path).rglob("*") if p.is_file()]
    # The application bundle and configuration are recorded without reading logs.
    for base in (Path("/Applications/LocalFlow.app"), Path.home() / ".config/localflow"):
        if base.exists():
            files += [p for p in base.rglob("*") if p.is_file() and p.suffix not in (".log", ".db")]
    return {str(p): {"sha256": file_sha256(p), "bytes": p.stat().st_size}
            for p in sorted(set(files))}


def investigate():
    from lfx.synth import words
    stats = read_json(OLD_ART / "dataset/stats.json")
    pairs = read_jsonl(OLD_ART / "dataset/train.jsonl")
    if not pairs:
        raise RuntimeError("Missing original training pairs")
    lengths = sorted(len(p["model_input"].split()) for p in pairs)
    punctuation_only = [p for p in pairs if p["model_input"] != p["target"]
                        and words(p["model_input"]) == words(p["target"])]
    val = {p["case_id"]: p for p in read_jsonl(OLD_ART / "dataset/validation_eval_cases.jsonl")}
    outputs = read_jsonl(OLD_ART / "eval/val-C-ckpt-00642.jsonl")
    bycategory = collections.defaultdict(lambda: collections.Counter())
    examples = []
    for row in outputs:
        p = val[row["case_id"]]
        c = bycategory[p["category"]]
        c["n"] += 1
        c["exact_target"] += row["delivered"] == p["target"]
        c["unchanged"] += row["delivered"] == p["model_input"]
        punct = words(p["model_input"]) == words(p["target"]) and p["model_input"] != p["target"]
        c["punctuation_needed"] += punct
        c["punctuation_exact"] += punct and row["delivered"] == p["target"]
        if len(examples) < 30 and row["delivered"] != p["target"]:
            examples.append({"case_id": p["case_id"], "category": p["category"],
                             "input": p["model_input"], "target": p["target"],
                             "output": row["delivered"], "path": row["path"],
                             "partition": "old_validation"})
    rejects = {}
    for p in (OLD_ART / "pairs").glob("*.stats.json"):
        r = read_json(p)
        rejects[p.stem] = {k: r.get(k) for k in ("pairs_total", "pairs_accepted", "reject_reasons")}
    metrics = read_jsonl(OLD_ART / "train/main/metrics.jsonl")
    out = {"created": utc_now(), "original_dataset": stats,
           "train_length_words": {"max": max(lengths), "median": lengths[len(lengths)//2],
                                  "over_200": sum(n > 200 for n in lengths)},
           "punctuation_only_training_pairs": len(punctuation_only),
           "old_validation_by_category": dict(bycategory), "old_generation_rejections": rejects,
           "original_training_curve": [m for m in metrics if m["event"] in ("val", "done", "start")],
           "original_selection": read_json(OLD_ART / "train/selection.json"),
           "findings": [
               "Original repair_success compares punctuation-stripped lexical tokens and does not measure punctuation correctness.",
               "Original data is selected by current engine reachability; multi-window examples and blocked gold targets are rejected.",
               "Generation favors multi-word correction markers because comma-separated single-word corrections fail the parser's parallel-value check.",
               "The prompt forbids contextual ASR word substitutions without an explicit vocabulary alias; this is a product boundary, not an undertraining diagnosis.",
               "The 803-update checkpoint tied 642 on delivered lexical repair while slightly reducing no-op preservation; more epochs alone were not supported by that validation measure.",
           ]}
    write_json(ART / "investigation.json", out)
    write_json(ART / "old_validation_examples.json", examples)
    print(json.dumps({k: out[k] for k in ("train_length_words", "punctuation_only_training_pairs")}, indent=2))


if __name__ == "__main__":
    import sys
    if sys.argv[1] == "preserve":
        dest = ART / "preservation-before.json"
        if dest.exists():
            raise RuntimeError("Initial preservation receipt already exists")
        write_json(dest, preservation())
        print("Preservation receipt saved")
    elif sys.argv[1] == "check":
        before = read_json(ART / "preservation-before.json")
        changed = [p for p, info in before.items()
                   if not Path(p).exists() or file_sha256(Path(p)) != info["sha256"]]
        write_json(ART / "preservation-after.json", {"checked": utc_now(), "files": len(before), "changed": changed})
        print(json.dumps({"files": len(before), "changed": changed}))
        raise SystemExit(bool(changed))
    else:
        investigate()
