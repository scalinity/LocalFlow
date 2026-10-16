"""Build a development-only blinded annotation packet; never performs inference."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import random
import re
from pathlib import Path

from .common import ART, read_json, write_json, write_jsonl
from .research_inputs import development_cases
from .stats import aligned, index_rows, read_rows


def output_id(case_id, system, stage):
    # Same canonical ID as judge.run. Expanded judge rows also handle dedup IDs.
    return "o" + hashlib.sha256((case_id + "|" + system + "|" + stage).encode()).hexdigest()[:18]


def stratified(cases, n, rng):
    if type(n) is not int or not 1 <= n <= len(cases):
        raise ValueError("N must be positive and no greater than the development population")
    groups = collections.defaultdict(list)
    for case in sorted(cases, key=lambda c: c["case_id"]):
        if not isinstance(case.get("category"), str) or not case["category"]:
            raise ValueError("Every case needs a category for stratification")
        groups[case["category"]].append(case)
    # Proportional allocation by largest remainder, category name breaks ties.
    counts = {k: n * len(v) // len(cases) for k, v in groups.items()}
    order = sorted(groups, key=lambda k: (-(n * len(groups[k]) % len(cases)), k))
    for k in order[:n-sum(counts.values())]:
        counts[k] += 1
    selected = [c for k in sorted(groups) for c in rng.sample(groups[k], counts[k])]
    rng.shuffle(selected)
    return selected


def build_pairs(cases_file, systems, *, n=150, seed=20261015, stage="delivered",
                prefix="development", eval_dir=None, output_dir=None, differing_only=False):
    if len(systems) < 2 or len(set(systems)) != len(systems):
        raise ValueError("Provide at least two distinct systems")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", s) for s in systems):
        raise ValueError("System names must be simple evaluation filename suffixes")
    if stage not in ("delivered", "model_only"):
        raise ValueError("Unknown output stage")
    cases = development_cases(cases_file, prefix)
    case_map = index_rows(cases)
    eval_dir = Path(eval_dir) if eval_dir is not None else ART / "eval"
    outputs = {s: index_rows(read_rows(eval_dir / f"development-{s}.jsonl")) for s in sorted(systems)}
    for system, rows in outputs.items():
        aligned(case_map, rows)
        if any(not isinstance(r.get(stage), str) or not r[stage].strip() or
               r.get("model", system) != system for r in rows.values()):
            raise ValueError("Missing/empty output or mismatched system identity")
    rng = random.Random(seed)
    if differing_only:
        # Opt-in: only cases where at least two systems differ, and only differing system pairs, so no pair is trivially tied.
        eligible = [c for c in cases if len({outputs[s][c["case_id"]][stage] for s in systems}) > 1]
        selected = stratified(eligible, n, rng)
    else:
        selected = stratified(cases, n, rng)
    pairs, key = [], {}

    def pair_id():
        return "p" + f"{rng.getrandbits(128):032x}"

    for case in selected:
        # Uniform random ordered selection simultaneously chooses systems and A/B.
        cid = case["case_id"]
        if differing_only:
            options = [(x, y) for x in sorted(systems) for y in sorted(systems) if x != y
                       and outputs[x][cid][stage] != outputs[y][cid][stage]]
            a, b = rng.choice(options)
        else:
            a, b = rng.sample(sorted(systems), 2)
        pid = pair_id()
        pairs.append({"pair_id": pid, "case_id": cid, "source": case["model_input"],
                      "a": {"text": outputs[a][cid][stage]}, "b": {"text": outputs[b][cid][stage]},
                      "vocabulary": case.get("vocabulary_pairs", [])})
        key[pid] = {"a_system": a, "b_system": b,
                    "a_output_id": output_id(cid, a, stage), "b_output_id": output_id(cid, b, stage),
                    "duplicate_of": None}
    duplicates = math.ceil(n * .1)
    for original in rng.sample(pairs, duplicates):
        pid = pair_id()
        pairs.append({**original, "pair_id": pid})
        key[pid] = {**key[original["pair_id"]], "duplicate_of": original["pair_id"]}
    rng.shuffle(pairs)
    dest = Path(output_dir) if output_dir is not None else ART / "research/annotation"
    pairs_path, key_path = dest / "pairs.jsonl", dest / "pairs-key.json"
    if pairs_path.exists() or key_path.exists():
        if not pairs_path.exists() or not key_path.exists() or read_rows(pairs_path) != pairs or read_json(key_path) != key:
            raise ValueError("Annotation packet exists with different or incomplete contents; preserve it and use a new output directory")
    else:
        write_jsonl(pairs_path, pairs)
        write_json(key_path, key)
    return {"sampled_cases": n, "duplicate_pairs": duplicates, "total_pairs": len(pairs),
            "seed": seed, "stage": stage, "differing_only": differing_only, "category_counts": dict(sorted(collections.Counter(c["category"] for c in selected).items())),
            "pairs_file": str(pairs_path), "key_file": str(key_path)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cases"); p.add_argument("--systems", nargs="+", required=True)
    p.add_argument("--n", type=int, default=150); p.add_argument("--seed", type=int, default=20261015)
    p.add_argument("--stage", choices=("delivered", "model_only"), default="delivered")
    p.add_argument("--prefix", default="development"); p.add_argument("--eval-dir"); p.add_argument("--output-dir")
    p.add_argument("--differing-only", action="store_true", help="sample only cases and system pairs whose texts differ")
    args = p.parse_args(argv)
    print(json.dumps(build_pairs(args.cases, args.systems, n=args.n, seed=args.seed, stage=args.stage,
                               prefix=args.prefix, eval_dir=args.eval_dir, output_dir=args.output_dir)))


if __name__ == "__main__":
    main()
