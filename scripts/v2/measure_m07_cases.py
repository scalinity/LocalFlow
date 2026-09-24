"""Per-case M07 model outcomes on the frozen EV-09 corpus: path,
fallback reason, fixture pass and engine latency for every fidelity,
literal and structure fixture, so model success (path llm and passed)
is reported separately from fallback-rescued passes.

The repo root is an argument so the same driver can measure another
checkout of the code (e.g. a ``git archive`` export of an earlier
commit) with that checkout's own harnesses. Output is content-free
apart from fixture ids and failure labels.

Run: .venv/bin/python scripts/v2/measure_m07_cases.py <repo_root> <out.json>
"""

import json
import pathlib
import sys
import time

root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tests/v2/fidelity"))
sys.path.insert(0, str(root / "tests/v2/structure"))

from localflow.v2.cleanup import ModelRunner  # noqa: E402
import test_fidelity as tf  # noqa: E402
import test_literal as tl  # noqa: E402
import test_structure as ts  # noqa: E402


def protected_of(case):
    spans = []
    for needle in case.get("protected", []):
        i = case["input"].find(needle)
        if i >= 0:
            spans.append((i, i + len(needle)))
    return spans


def literal_case(engine, case):
    """The test_literal loop body for one fixture."""
    res = engine.clean(case["input"], protected_spans=protected_of(case))
    low = res.text.lower()
    failures = []
    for group in case.get("expect", []):
        if not any(tl._found(alt.lower(), low) for alt in group):
            failures.append(f"missing {group}")
    forbids = list(case.get("forbid_on_fallback", []))
    if res.path == "llm":
        forbids += list(case.get("forbid", []))
    for bad in forbids:
        if tl._found(bad.lower(), low):
            failures.append(f"forbidden present: {bad!r}")
    return failures, res


def main():
    runner = ModelRunner("mlx-community/Qwen3-4B-Instruct-2507-4bit")
    runner.load()
    engine = runner.engine()
    suites = [
        ("fidelity", tf.FIXTURES,
         lambda c: tf.run_case(engine, c, protected_of(c))),
        ("literal", tl.FIXTURES, lambda c: literal_case(engine, c)),
        ("structure", ts.FIXTURES, lambda c: ts.run_case(engine, c)),
    ]
    out = {"template_revision": runner.template_revision, "cases": []}
    for suite, fixtures, run in suites:
        for case in json.loads(fixtures.read_text())["cases"]:
            t0 = time.monotonic()
            failures, res = run(case)
            out["cases"].append({
                "suite": suite, "id": case["case_id"], "path": res.path,
                "reason": res.fallback_reason, "passed": not failures,
                "failures": failures,
                "ms": round((time.monotonic() - t0) * 1000.0, 1),
                "words": len(case["input"].split())})
    pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
    print("done", len(out["cases"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
