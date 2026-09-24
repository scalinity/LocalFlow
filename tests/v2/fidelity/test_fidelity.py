"""EV-09 / M07 fidelity suite (model-backed): the 60 owning fidelity
fixtures against the real cleanup model through the V2 engine.

Every fixture is critical for M07-AC01/AC04: dictated instructions are
never answered or executed; corrections keep the surviving replacement
and reason clause; negation, uncertainty, names, quantities and
technical tokens survive; cloud stays cloud.

Run: .venv/bin/python tests/v2/fidelity/test_fidelity.py [--limit N]
"""

import json
import re
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import CleanupEngine, ModelRunner  # noqa: E402

def _found(needle: str, low: str) -> bool:
    """Hyphen/whitespace-tolerant containment (phrase equality across
    hyphenation differences; exact tokens like "/code-review" match
    because both sides get the same normalization)."""
    if needle in low:
        return True
    n = re.sub(r"[\s\-]+", " ", needle).strip()
    h = re.sub(r"[\s\-]+", " ", low).strip()
    return n in h


FIXTURES = pathlib.Path(__file__).parent / "fixtures_fidelity.json"


def run_case(engine, case, protected_spans):
    res = engine.clean(
        case["input"], protected_spans=protected_spans,
        destination_profile=case.get("destination_profile"))
    text = res.text
    low = text.lower()
    failures = []
    for group in case.get("expect", []):
        if not any(_found(alt.lower(), low) for alt in group):
            failures.append(f"missing {group}")
    # Corrected-away/filler forbids apply to the validated clean output;
    # a fallback path carries the normalized source by construction, so
    # only the safety forbids (answers/injections) are checked there.
    if res.path == "llm":
        forbids = list(case.get("forbid", [])) \
            + list(case.get("forbid_on_fallback", []))
    else:
        forbids = list(case.get("forbid_on_fallback", []))
    for bad in forbids:
        if bad.lower() in low:
            failures.append(f"forbidden present: {bad!r}")
    return failures, res


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    cases = json.loads(FIXTURES.read_text())["cases"]
    if limit:
        cases = cases[:limit]
    runner = ModelRunner(
        "mlx-community/Qwen3-4B-Instruct-2507-4bit")
    print("loading cleanup model …")
    runner.load()
    engine = runner.engine()
    passed, failed = 0, []
    t0 = time.monotonic()
    fallbacks = 0
    rescued = 0      # passed only because the fallback kept the source
    for case in cases:
        protected = []
        for needle in case.get("protected", []):
            idx = case["input"].find(needle)
            if idx >= 0:
                protected.append((idx, idx + len(needle)))
        failures, res = run_case(engine, case, protected)
        if res.path != "llm":
            fallbacks += 1
        if failures:
            failed.append((case["case_id"], failures, res.path,
                           res.fallback_reason))
            print(f"FAIL {case['case_id']}: {failures} "
                  f"[path={res.path} reason={res.fallback_reason}]")
        else:
            passed += 1
            rescued += res.path != "llm"
    elapsed = time.monotonic() - t0
    print(f"{passed}/{len(cases)} passed, {fallbacks} fallback-window jobs"
          f", total {elapsed:.1f}s")
    # Safety-fallback scoring stays separate from cleanup success.
    print(f"model-path passes {passed - rescued}/{len(cases)}, "
          f"fallback-rescued passes {rescued}")
    if failed:
        for cid, failures, path, reason in failed:
            print(f"  {cid}: {failures} path={path} reason={reason}")
        return 1
    print("all fidelity fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
