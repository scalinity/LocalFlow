"""One consolidated TRAIN set instead of stacked narrow continuations.

Every verified TRAIN label from the earlier rounds, the newest reviewed version of
each row first, normalized to one minimal-edit policy, captured with the current
engine; validation is recaptured with the same source so its loss describes the
prompts the model is served with. Development and final labels are never edited.
"""
from __future__ import annotations

import argparse
import collections
import random
import re
from .common import *
from .policy_score import LIST_LINE, WORD, _aligned_gaps, _split, minimal_target

RUN = ART / "consolidated"
DATASET = RUN / "dataset"
REFINEMENT = ART / "refinement"
# Newest reviewed version of a row wins: later slices retargeted earlier labels.
SLICES = ["dataset-minimal-style-current", "dataset-vocative-literal-current", "dataset-final-vocative-current",
          "dataset-literal-preservation", "dataset-acknowledgment", "dataset"]
# Rows excluded by earlier label reviews (disputed targets, conflicting supervision,
# rejected donors); the refinement freeze's own label conflicts are added at build time.
REVIEWED_EXCLUSIONS = {
    "v2-tr-001561-base", "v2-tr-002574-base", "v2-tr-002976-base", "v2-tr-004501-base",
    "v4-tr-00025-repair-base", "v4-tr-00080-repair-base", "v4-tr-00272-repair-base", "v4-tr-00275-repair-base",
    "v4-tr-00475-preserve-base", "v4-tr-00745-repair-base", "v4-tr-00867-repair-base", "v4-tr-01065-repair-base",
    "v4-tr-01145-repair-base", "v4-tr-00480-repair-base",
}
LIST_INTRO = re.compile(r"\b(list|lists|steps?|following|items)\b", re.I)
C_ERA_SAMPLE = 1200
# Rows reviewed to teach the comma before a sentence-final addressed name keep every added comma.
# A guarantee for such rows: today the comma classification and the addressee check already keep
# every comma these rows add, so it changes none of the current labels.
VOCATIVE_FOCUS = "question_final_vocative_comma"
# Per TRAIN row, the kind of each comma a label added at an unpunctuated source gap, keyed by
# source gap index (written by hard-cases/tools/comma_classify.py). The build needs it.
COMMA_KINDS = ART / "hard-cases" / "labels" / "comma-kinds-train.json"


def _vocabulary(row):
    out = []
    for pair in row.get("vocabulary_pairs") or []:
        out.append(pair.get("canonical", "") if isinstance(pair, dict) else str(pair))
    return out


def _comma_gaps(source, target):
    """Source gap indices whose aligned label gap holds a comma."""
    s_words, _ = _split(source)
    t_words, t_gaps = _split(target)
    return {j for k, j in _aligned_gaps(s_words, t_words).items() if "," in t_gaps[k]}


def _kept_commas(row, comma_kinds):
    """Source gap indices whose added label comma stays: every gap of a row reviewed to
    teach the final vocative comma or left unclassified by the table (when unsure, keep),
    otherwise the gaps whose classified kind does a job."""
    rid = row.get("pair_id", row["case_id"])
    if row.get("focus") == VOCATIVE_FOCUS or rid in comma_kinds.get("unclassified_rows", []):
        return set(range(len(WORD.findall(row["model_input"])) + 1))  # every gap of the source
    kept = set(comma_kinds.get("kept_kinds", []))
    gaps = {int(j) for j, kind in comma_kinds.get("rows", {}).get(rid, {}).items() if kind in kept}
    if gaps - _comma_gaps(row["model_input"], row["target"]):
        # The label changed after the table classified it, so its gap indices may name other commas.
        raise RuntimeError(f"{COMMA_KINDS.name} is stale for {rid}; rerun comma_classify.py")
    return gaps


def _restored_conjunctions(row, target):
    """The target with the conjunctions it dropped at a new sentence put back, or None."""
    from .label_defects import restore_split_conjunctions
    from .refinement_data import correction_offsets
    try:
        offsets = correction_offsets(row)
    except ValueError:
        return None  # capture records the unanchored line
    return restore_split_conjunctions(row["model_input"], target, offsets, row.get("vocabulary_pairs"))


def _held_out_texts():
    texts = set()
    for path in [REFINEMENT / "dataset" / "validation.jsonl", REFINEMENT / "dataset" / "test.jsonl",
                 ART / "dataset" / "validation.jsonl", ART / "dataset" / "test.jsonl"]:
        for row in read_jsonl(path):
            for field in ("model_input", "target"):
                if row.get(field):
                    texts.add(" ".join(row[field].casefold().split()))
    return texts


def collect():
    """Gather, normalize and filter TRAIN rows; no capture."""
    conflicts = {c["case_id"] for c in read_json(REFINEMENT / "dataset" / "freeze.json")["stats"]["train"]["label_conflicts"]}
    excluded_ids = REVIEWED_EXCLUSIONS | conflicts
    if not COMMA_KINDS.exists():
        # Without it every list, meaning and convention comma a label added would revert.
        raise RuntimeError(f"{COMMA_KINDS} is missing; run hard-cases/tools/comma_classify.py")
    comma_kinds = read_json(COMMA_KINDS)
    ordered = []
    for name in SLICES:
        ordered += [(name, r) for r in read_jsonl(REFINEMENT / name / "train.jsonl")]
    ordered += [("diverse", r) for r in read_jsonl(ART / "dataset" / "train.jsonl")]
    ordered += [("longform", r) for r in read_jsonl(ART / "longform" / "train.jsonl")]
    c_era = [r for r in read_jsonl(OLD_ART / "dataset" / "train.jsonl") if r.get("verification") == "PASS"]
    random.Random(20261015).shuffle(c_era)
    for r in c_era[:C_ERA_SAMPLE]:
        r = dict(r, case_id=r["pair_id"], scenario_family=r.get("category", "c-era"))
        ordered.append(("c-era", r))
    held_out = _held_out_texts()
    seen_ids, seen_inputs, rows = set(), set(), []
    stats = collections.Counter()
    exclusions = collections.Counter()
    for origin, row in ordered:
        cid = row.get("case_id") or row["pair_id"]
        row = dict(row, case_id=cid)
        if cid in seen_ids:
            stats["superseded_by_newer_version"] += 1
            continue
        seen_ids.add(cid)
        if cid in excluded_ids:
            exclusions["reviewed_label_exclusion"] += 1
            continue
        source, target = row["model_input"], row["target"]
        if " ".join(source.casefold().split()) in held_out or " ".join(target.casefold().split()) in held_out:
            exclusions["shares_text_with_development_or_final"] += 1
            continue
        if LIST_LINE.search(target) and not LIST_LINE.search(source) and not LIST_INTRO.search(source):
            exclusions["list_without_introduction"] += 1
            continue
        normalized, changes, exclusion = minimal_target(source, target, _vocabulary(row),
                                                        _kept_commas(row, comma_kinds))
        if exclusion:
            exclusions[exclusion.split(":")[0]] += 1
            continue
        key = " ".join(source.casefold().split())
        if key in seen_inputs:
            exclusions["duplicate_input"] += 1
            continue
        seen_inputs.add(key)
        restored = _restored_conjunctions(row, normalized)
        if restored:
            # The label split a run-on and dropped a dictated conjunction (label_defects.CONJUNCTIONS).
            normalized, changes = restored, changes + ["restored_split_conjunction"]
            stats["split_conjunctions_restored"] += 1
        row = dict(row, target=normalized, split="train", consolidated_origin=origin, policy_changes=changes)
        if changes:
            row["original_target"] = target
            stats["labels_normalized"] += 1
        if normalized == source and not row.get("is_noop"):
            row["is_noop"] = True
            stats["repair_became_already_correct"] += 1
        stats["kept_" + origin] += 1
        rows.append(row)
    summary = {"kept": len(rows), "noop": sum(bool(r["is_noop"]) for r in rows),
               "long_over_200": sum(len(r["model_input"].split()) > 200 for r in rows),
               "stats": dict(stats), "exclusions": dict(exclusions),
               "comma_kinds_sha256": file_sha256(COMMA_KINDS)}
    return rows, summary


def build(dataset=DATASET, consistent=False):
    """Capture TRAIN and validation with the current engine and freeze the dataset.

    consistent also supervises a row the engine does not deliver exactly, with
    only the calls whose prompt and target agree (assemble.capture).
    """
    from .assemble import capture
    from .refinement import SOURCE_FILES
    from .training import checked_dataset
    dataset = Path(dataset)
    if (dataset / "freeze.json").exists():
        freeze = read_json(dataset / "freeze.json")
        if consistent != ("supervision" in freeze):
            raise RuntimeError(f"{dataset} is frozen with the other supervision mode")
        return freeze
    if (dataset / "train.jsonl").exists():
        # Without a freeze this may be a source collect reads (longform/train.jsonl); never overwrite it.
        raise RuntimeError(f"{dataset} holds train.jsonl without a freeze")
    rows, summary = collect()
    source_hashes = {p: file_sha256(ROOT / p) for p in SOURCE_FILES}
    dataset.mkdir(parents=True, exist_ok=True)
    captures, failures, oracle = [], collections.Counter(), collections.Counter()
    vetoed, partial, vetoed_calls = collections.Counter(), collections.Counter(), collections.Counter()
    for row in rows:
        # An engine_oracle or capture_error already on the row came from an earlier capture of its
        # source dataset.
        row.pop("capture_error", None)
        try:
            cap = capture(row, consistent_only=consistent)
        except (ValueError, RuntimeError) as exc:
            failures[str(exc).split(":")[0]] += 1
            row.pop("engine_oracle", None)
            row["capture_error"] = str(exc)
            continue
        exact = bool(row.get("engine_oracle", {}).get("exact"))
        oracle[str(exact)] += 1
        focus = row.get("focus") or row.get("category") or "unknown"
        if not exact:
            for call in row["engine_oracle"].get("supervision", []):
                vetoed_calls[call["role"] + ":" + call["why"]] += 1
            if not consistent or not cap["calls"]:
                # The serving engine would discard this target; keep it out of supervision.
                vetoed[focus] += 1
                continue
            partial[focus] += 1
        captures.append(cap)
    write_jsonl(dataset / "train.jsonl", rows)
    write_jsonl(dataset / "train_captures.jsonl", captures)
    validation = read_jsonl(REFINEMENT / "dataset" / "validation.jsonl")
    write_jsonl(dataset / "validation.jsonl", validation)
    val_caps, val_failures = [], collections.Counter()
    for row in validation:
        try:
            val_caps.append(capture(dict(row)))
        except (ValueError, RuntimeError) as exc:
            val_failures[str(exc).split(":")[0]] += 1
    write_jsonl(dataset / "validation_captures.jsonl", val_caps)
    write_jsonl(dataset / "replay_captures.jsonl", [])
    if any(file_sha256(ROOT / p) != digest for p, digest in source_hashes.items()):
        raise RuntimeError("Engine source changed during capture")
    train_stats = {"captured": len(captures), "capture_failures": dict(failures),
                   "oracle_exact": dict(oracle), "engine_vetoed_by_focus": dict(vetoed)}
    if consistent:
        train_stats.update(partially_supervised_by_focus=dict(partial), vetoed_row_calls=dict(vetoed_calls))
    freeze = {"created": utc_now(),
              "files": {p.name: file_sha256(p) for p in sorted(dataset.glob("*.jsonl"))},
              "capture_source_hashes": source_hashes, "validation_capture_source_hashes": source_hashes,
              "stats": {"collect": summary,
                        "train": train_stats,
                        "validation": {"captured": len(val_caps), "capture_failures": dict(val_failures)},
                        "replay": {"captured": 0, "source": "none: historical labels are part of the consolidated TRAIN set"}},
              "labels": ("TRAIN labels normalized by policy_score.minimal_target and "
                         "label_defects.restore_split_conjunctions; development and final labels unchanged."),
              "final_candidate_outputs_existed": False}
    if consistent:
        freeze["supervision"] = "Rows the engine vetoes keep only calls whose prompt and target agree."
    write_json(dataset / "freeze.json", freeze)
    checked_dataset(dataset)
    return freeze


def train(name, lr=3e-5, checkpoints=4, log_every=1, base=None, dataset=DATASET):
    # 3e-5 with cosine decay is the rate that trained D/F on the diverse corpus;
    # validation loss was still falling at the end of that epoch. Another base
    # (the 4-bit 9B) trains a fresh adapter instead of continuing C's.
    from .training import run
    freeze = read_json(Path(dataset) / "freeze.json")
    if not freeze:
        raise RuntimeError("Build the consolidated dataset first")
    return run(name, freeze["stats"]["train"]["captured"], initial_adapter=None if base else c_identity()["adapter_path"],
               lr=lr, dataset_dir=dataset, checkpoints=checkpoints, log_every=log_every, base=base)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["collect", "build", "train"])
    p.add_argument("--name", default="consolidated-c")
    p.add_argument("--lr", type=float, default=3e-5)
    p.add_argument("--checkpoints", type=int, default=4)
    p.add_argument("--log-every", type=int, default=1, help="log training loss every N updates")
    p.add_argument("--base", help="local model directory to train a fresh adapter on instead of continuing C")
    p.add_argument("--dataset", type=Path, default=DATASET, help="dataset directory to build or train from")
    p.add_argument("--consistent", action="store_true",
                   help="build: also supervise vetoed rows with their calls whose prompt and target agree")
    a = p.parse_args()
    if a.stage == "collect":
        print(__import__("json").dumps(collect()[1], indent=1))
    elif a.stage == "build":
        print(__import__("json").dumps(build(a.dataset, a.consistent)["stats"], indent=1))
    else:
        print(__import__("json").dumps(train(a.name, a.lr, a.checkpoints, a.log_every, a.base, a.dataset)))
