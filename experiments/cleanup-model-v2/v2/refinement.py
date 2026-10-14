"""Prepare focused supervision and freeze the final comparison separately."""
from __future__ import annotations

import argparse
import collections
import copy
import random
import shutil
from .common import *

RUN = ART / "refinement"
DATASET = RUN / "dataset"
SOURCE_FILES = ["localflow/v2/cleanup/" + name for name in
                ("engine.py", "prompts.py", "validation.py", "document_nodes.py",
                 "correction_retention.py", "model.py")]


def prepare():
    from .refinement_data import assemble
    from .assemble import capture
    if (DATASET / "freeze.json").exists():
        return read_json(DATASET / "freeze.json")
    if any(not (ART / "accepted" / ("refinement-" + s + ".jsonl")).exists()
           for s in ("train", "validation", "test")):
        raise RuntimeError("All disjoint generation and verification splits must finish first")
    source_hashes = {p: file_sha256(ROOT / p) for p in SOURCE_FILES}
    DATASET.mkdir(parents=True, exist_ok=True)
    for split in ("test", "validation", "train"):
        assemble(split)
        shutil.copyfile(RUN / ("synthetic-" + split + ".jsonl"), DATASET / (split + ".jsonl"))
    stats = {}
    for split in ("validation", "train"):
        captures, failures, oracle = [], [], collections.Counter()
        for row in read_jsonl(DATASET / (split + ".jsonl")):
            row = copy.deepcopy(row)
            try:
                captures.append(capture(row))
                oracle[str(row["engine_oracle"]["exact"])] += 1
            except (ValueError, RuntimeError) as exc:
                failures.append({"case_id": row["case_id"], "reason": str(exc)})
        write_jsonl(DATASET / (split + "_captures.jsonl"), captures)
        stats[split] = {"captured": len(captures), "oracle_exact": dict(oracle), "capture_failures": failures}
    # Historical TRAIN labels only; exposed evaluations never become supervision.
    replay = [c for c in read_jsonl(ART / "dataset/train.jsonl") if c.get("engine_oracle", {}).get("exact")]
    random.Random(20261014).shuffle(replay)
    replay_captures, failures = [], []
    wanted = max(1, stats["train"]["captured"] // 5)
    for row in replay:
        try:
            replay_captures.append(capture(copy.deepcopy(row)))
        except (ValueError, RuntimeError) as exc:
            failures.append({"case_id": row["case_id"], "reason": str(exc)})
        if len(replay_captures) == wanted:
            break
    if not replay_captures or not all(stats[s]["captured"] for s in stats):
        raise RuntimeError("Focused supervision or historical replay is empty")
    write_jsonl(DATASET / "replay_captures.jsonl", replay_captures)
    stats["replay"] = {"captured": len(replay_captures), "capture_failures": failures,
                       "source": "Historical independently checked training labels, recaptured with current prompts"}
    if any(file_sha256(ROOT / p) != digest for p, digest in source_hashes.items()):
        raise RuntimeError("Prompt source changed during supervision capture")
    freeze = {"created": utc_now(), "files": {p.name: file_sha256(p) for p in sorted(DATASET.glob("*.jsonl"))},
              "capture_source_hashes": source_hashes,
              "stats": stats, "final_candidate_outputs_existed": False,
              "labels": "No final oracle capture or candidate-based exclusion. Sibling scenarios remain in their assigned split."}
    write_json(DATASET / "freeze.json", freeze)
    return freeze


def train(name="focused-2400", lr=2e-5):
    from .training import run
    freeze = read_json(DATASET / "freeze.json")
    if not freeze:
        raise RuntimeError("Focused data has not been captured and frozen")
    old = read_json(ART / "export/diverse-6000-ckpt-00761.identity.json")
    return run(name, freeze["stats"]["train"]["captured"], initial_adapter=old["adapter"],
               lr=lr, dataset_dir=DATASET)


def freeze_final():
    from lfx.export import content_digest
    from .training import checked_dataset
    if (RUN / "final-freeze.json").exists():
        raise RuntimeError("The final comparison is already frozen")
    selection = read_json(RUN / "candidate-selection.json")
    if not selection or not selection.get("ready_for_final"):
        raise RuntimeError("Development selection is not complete")
    checked_dataset(DATASET)
    selected = selection.get("candidate", {})
    if not selected.get("key") or selected["key"] in ("C", "F") or not selected.get("path") or not selected.get("content_digest"):
        raise RuntimeError("Selection must identify candidate key, model path and content digest")
    fixed_f = read_json(ART / "export/diverse-6000-ckpt-00761.identity.json")
    fixed_c = c_identity()
    models = {"C": {"path":fixed_c["snapshot_path"], "engine":"production"},
              "F": {"path":fixed_f["quantized"], "engine":"recorded_f"},
              selected["key"]: {"path":selected["path"], "engine":"updated_source"}}
    for key, binding in models.items():
        binding["path"] = str(Path(binding["path"]).resolve())
        binding["content_digest"] = content_digest(Path(binding["path"]))
        if key == selected["key"] and binding["content_digest"] != selected["content_digest"]:
            raise RuntimeError("Selected candidate model files changed")
        if key == "F" and binding["content_digest"] != fixed_f["content_digest"]:
            raise RuntimeError("Recorded F model files changed")
        if key == "C" and binding["content_digest"] != fixed_c["revision"]:
            raise RuntimeError("Recorded C model files changed")
        if (ART / "eval" / ("refined-" + key + ".jsonl")).exists():
            raise RuntimeError("Final candidate outputs already exist before freeze")
    synthetic = read_jsonl(DATASET / "test.jsonl")
    audio = read_jsonl(RUN / "audio-asr.jsonl")
    selected_audio = read_jsonl(RUN / "audio-cases.jsonl")
    if not synthetic or len(audio) != 300 or {c["case_id"] for c in audio} != {c["case_id"] for c in selected_audio}:
        raise RuntimeError("The fixed synthetic and audio comparison is incomplete")
    rows = synthetic + audio
    if len({r["case_id"] for r in rows}) != len(rows) or any(r["split"] != "test" for r in rows):
        raise RuntimeError("Final case identities or roles disagree")
    path = RUN / "final-cases.jsonl"
    write_jsonl(path, rows)
    freeze = {"created": utc_now(), "n": len(rows), "synthetic": len(synthetic), "audio": len(audio),
              "cases_sha256": file_sha256(path), "selection_sha256": file_sha256(RUN / "candidate-selection.json"),
              "source_hashes": {p: file_sha256(ROOT / p) for p in SOURCE_FILES},
              "models":models,
              "data_freeze_sha256": file_sha256(DATASET / "freeze.json"),
              "candidate_outputs_existed": False}
    write_json(RUN / "final-freeze.json", freeze)
    return freeze


def require_final(path, *, candidate=False, key=None, model_path=None, engine=None):
    from lfx.export import content_digest
    freeze = read_json(RUN / "final-freeze.json")
    if not freeze or file_sha256(Path(path)) != freeze["cases_sha256"]:
        raise ValueError("Refined evaluation requires its exact frozen comparison file")
    if file_sha256(RUN / "candidate-selection.json") != freeze["selection_sha256"]:
        raise ValueError("Development selection changed after final freeze")
    if file_sha256(DATASET / "freeze.json") != freeze["data_freeze_sha256"]:
        raise ValueError("Dataset identity changed after final freeze")
    if key is not None:
        binding = freeze["models"].get(key)
        actual_path = str(Path(model_path or c_identity()["snapshot_path"] if key.startswith("C") else model_path or key).resolve())
        if not binding or actual_path != binding["path"] or engine != binding["engine"]:
            raise ValueError("Evaluation model or engine differs from the final selection")
        if content_digest(Path(actual_path)) != binding["content_digest"]:
            raise ValueError("Frozen evaluation model files changed")
    if candidate and any(file_sha256(ROOT / p) != digest for p, digest in freeze["source_hashes"].items()):
        raise ValueError("Candidate source changed after final comparison freeze")
    return freeze


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["prepare", "train", "freeze"])
    args = p.parse_args()
    result = {"prepare": prepare, "train": train, "freeze": freeze_final}[args.stage]()
    print(__import__("json").dumps(result))
