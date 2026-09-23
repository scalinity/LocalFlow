"""EV-13 / M11 (model-backed): the 30 Prompt Engineer acceptance cases.

Every case runs through the REAL cleanup model (the same ModelRunner
the worker loads) under the builtin:prompt_engineer contract. A case
passes when every enumerated requirement anchor survives in the output
and no hidden added task/enterprise requirement appears — or when the
engine honestly flagged the uncertainty (needs_review with the
original clauses kept), which is never a silent loss (M11-AC02 / the
M11 stop condition).

Run: .venv/bin/python tests/v2/transforms/test_prompt_engineer_cases.py
     [--limit N] [--split dev|validation|held-out]
"""

import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import ModelRunner  # noqa: E402
from localflow.v2 import transforms as tf  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures_prompt_engineer.json"
MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"


def _found(needle: str, low: str) -> bool:
    """Hyphen/whitespace-tolerant containment (the fidelity suite's
    tolerance — representation differences never fail a case)."""
    if needle in low:
        return True
    n = re.sub(r"[\s\-]+", " ", needle).strip()
    h = re.sub(r"[\s\-]+", " ", low).strip()
    return n in h


def run_case(runner, defn, case):
    job = tf.job_for_definition(defn, case["source"],
                                source_kind="selection")
    res = tf.run_transform(job, runner.generate_fn(), runner.render)
    low = (res.output or "").lower()
    missing = [group for group in case.get("require", [])
               if not any(_found(alt.lower(), low) for alt in group)]
    added = [bad for bad in case.get("forbid_added", [])
             if bad.lower() in low]
    silent = bool(missing or added) and res.path == "applied"
    return res, missing, added, silent


def main():
    limit = None
    split = None
    args = sys.argv[1:]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    if "--split" in args:
        split = args[args.index("--split") + 1]

    doc = json.loads(FIXTURES.read_text())
    cases = doc["cases"]
    if split:
        cases = [c for c in cases if c["split"] == split]
    if limit:
        cases = cases[:limit]
    by_split = {}
    for c in cases:
        by_split.setdefault(c["split"], []).append(c)
    assert len(doc["cases"]) == 30, len(doc["cases"])
    assert {s: len(v) for s, v in by_split.items()} == {
        "dev": 15, "validation": 5, "held-out": 10} if not (
            split or limit) else {s: len(v) for s, v in by_split.items()}

    print(f"loading {MODEL} …")
    t0 = time.monotonic()
    runner = ModelRunner(MODEL)
    runner.load()
    print(f"model ready in {time.monotonic() - t0:.1f}s")

    defn = next(d for d in tf.built_ins()
                if d.transform_id == "builtin:prompt_engineer")
    passed = flagged = 0
    silent_losses = []
    total_inference = 0.0
    for case in cases:
        res, missing, added, silent = run_case(runner, defn, case)
        total_inference += res.duration_ms / 1000.0
        if silent:
            silent_losses.append((case["case_id"], missing, added))
            print(f"FAIL {case['case_id']} [{case['split']}] silent:"
                  f" missing={missing} added={added}")
        elif res.path == "needs_review":
            flagged += 1
            print(f"ok   {case['case_id']} [{case['split']}]"
                  f" needs_review ({len(res.review_excerpts)} kept"
                  f" clauses) — no silent loss")
        else:
            passed += 1
            print(f"ok   {case['case_id']} [{case['split']}]"
                  f" applied, all atoms survive"
                  f" ({res.duration_ms:.0f} ms)")
    assert not silent_losses, \
        f"{len(silent_losses)} silent requirement losses: {silent_losses}"
    print(f"{passed + flagged}/{len(cases)} passed "
          f"({passed} applied, {flagged} honestly flagged for review), "
          f"total inference {total_inference:.1f}s")
    print("all prompt engineer cases passed (zero silent losses)")


if __name__ == "__main__":
    main()
