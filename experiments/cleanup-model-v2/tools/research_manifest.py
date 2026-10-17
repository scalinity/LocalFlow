"""Reproducibility manifest of the study: runs, data, commits, checkpoints, costs. Aggregates only.

Reads private run records under artifacts/ and writes a public JSON with no case text, no model
outputs and no credentials. Usage (repository root):
  PYTHONPATH=experiments/cleanup-model-v2:experiments/cleanup-model .venv/bin/python \
    experiments/cleanup-model-v2/tools/research_manifest.py docs/v2/research/paper/data/arms.json OUT.json
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ART = HERE / "artifacts"
ROOT = HERE.parents[1]

# Training runs and the dataset each trained on (dataset folder under artifacts/consolidated, commit trained at).
RUNS = {
    "M2-seed0": ("v2-m2-4b-s0", "dataset-v2-merged"), "M2-seed1": ("v2-m2-4b-s1", "dataset-v2-merged"),
    "M2-seed2": ("v2-m2-4b-s2", "dataset-v2-merged"), "M3": ("v2-m3-9b-s0", "dataset-v2-merged"),
    "M1-seed0": ("v2-m1-4bfresh-s0", "dataset-v2-merged"), "M1-seed1": ("v2-m1-4bfresh-s1", "dataset-v2-merged"),
    "M1-seed2": ("v2-m1-4bfresh-s2", "dataset-v2-merged"), "A1": ("v2-a1-4bfresh-s0", "arms/A1"),
    "A3": ("v2-a3-4bfresh-s0", "arms/A3"), "A2": ("v2-a2-4bfresh-s0", "dataset"),
    "A2prime": ("v2-a2prime-4b-s0", "dataset"),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def run_record(name, dataset):
    run = ART / "train" / name
    start = None
    last_train = None
    vals = []
    for line in (run / "metrics.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e.get("event") == "start":
            start = e
        elif e.get("event") == "train":
            last_train = e
        elif e.get("event") in ("val", "validation"):
            vals.append({"update": e["update"], "val_loss": e.get("val_loss", e.get("loss"))})
    ckpt = read_json(run / "checkpoint-validation.json") or {}
    request = read_json(run / "request.json") or {}
    freeze = read_json(ART / "consolidated" / dataset / "freeze.json") or {}
    return {
        "run": name, "dataset": dataset, "dataset_freeze_sha256": sha256(ART / "consolidated" / dataset / "freeze.json"),
        "train_captures": freeze.get("stats", {}).get("train", {}).get("captured"),
        "examples": start and start.get("examples"), "updates": start and start.get("updates"),
        "learning_rate": start and start.get("lr"), "grad_accum": start and start.get("grad_accum"),
        "warmup": start and start.get("warmup"), "save_at": start and start.get("save_at"),
        "fresh_adapter": request.get("base") is not None, "initial_adapter": None if request.get("base") else "C",
        "seed_env": None, "final_train_loss_last_update": last_train and last_train.get("loss"),
        "validation_curve": vals,
        "checkpoint_validation": [{"checkpoint": c["checkpoint"], "val_loss": c["val_loss"]} for c in ckpt.get("checkpoints", [])],
        "selected_checkpoint": ckpt.get("lowest_loss"),
        "validation_examples": ckpt.get("examples"),
    }


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def main():
    arms_file, out = Path(sys.argv[1]), Path(sys.argv[2])
    runs = {k: run_record(*v) for k, v in RUNS.items()}
    for k, r in runs.items():
        if "seed" in k:
            r["seed_env"] = int(k.rsplit("seed", 1)[1])
    ledger = read_json(ART / "live" / "gpu-ledger.json") or {}
    pods = ledger.get("pods", [])
    manifest = {
        "git_head": git("rev-parse", "HEAD"), "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "arms_file_sha256": sha256(arms_file), "runs": runs,
        "gpu": {"pods": len(pods), "price_usd_per_hour": sorted({p["usd_per_hr"] for p in pods}),
                "billed_usd_recorded": sum(p["billed_usd"] for p in pods if p.get("billed_usd")),
                "note": "RunPod billing reports lag running pods; the console balance is authoritative."},
        "datasets": {d: {"freeze_sha256": sha256(ART / "consolidated" / d / "freeze.json"),
                         "train_captures": (read_json(ART / "consolidated" / d / "freeze.json") or {}).get("stats", {}).get("train", {}).get("captured")}
                     for d in ("dataset-v2-merged", "arms/A1", "arms/A3", "dataset")},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print(json.dumps({"runs": len(runs), "out": str(out)}))


if __name__ == "__main__":
    main()
