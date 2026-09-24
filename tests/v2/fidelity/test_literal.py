"""EV-09 / M07 literal suite (model-backed): the 20 owning literal /
quoted-command fixtures against the real cleanup model through the V2
engine, with protected spans passed exactly as the pipeline maps them.

S13: "Preserve every protected token exactly. Keep explicit literal
text literal. A discussion of a phrase is not an instruction to edit
that phrase here."

Run: .venv/bin/python tests/v2/fidelity/test_literal.py [--limit N]
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


FIXTURES = pathlib.Path(__file__).parent / "fixtures_literal.json"


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    cases = json.loads(FIXTURES.read_text())["cases"]
    if limit:
        cases = cases[:limit]
    runner = ModelRunner("mlx-community/Qwen3-4B-Instruct-2507-4bit")
    print("loading cleanup model …")
    runner.load()
    engine = runner.engine()
    passed, failed, fallbacks = 0, [], 0
    rescued = 0      # passed only because the fallback kept the source
    t0 = time.monotonic()
    for case in cases:
        protected = []
        for needle in case.get("protected", []):
            idx = case["input"].find(needle)
            if idx >= 0:
                protected.append((idx, idx + len(needle)))
        res = engine.clean(case["input"], protected_spans=protected)
        low = res.text.lower()
        failures = []
        for group in case.get("expect", []):
            if not any(_found(alt.lower(), low) for alt in group):
                failures.append(f"missing {group}")
        if res.path == "llm":
            forbids = list(case.get("forbid", [])) \
                + list(case.get("forbid_on_fallback", []))
        else:
            forbids = list(case.get("forbid_on_fallback", []))
        for bad in forbids:
            if _found(bad.lower(), low):
                failures.append(f"forbidden present: {bad!r}")
        if res.path != "llm":
            fallbacks += 1
        if failures:
            failed.append((case["case_id"], failures))
            print(f"FAIL {case['case_id']}: {failures} "
                  f"[path={res.path} reason={res.fallback_reason}]")
        else:
            passed += 1
            rescued += res.path != "llm"
    elapsed = time.monotonic() - t0
    print(f"{passed}/{len(cases)} passed, {fallbacks} fallback jobs, "
          f"total {elapsed:.1f}s")
    # Safety-fallback scoring stays separate from cleanup success.
    print(f"model-path passes {passed - rescued}/{len(cases)}, "
          f"fallback-rescued passes {rescued}")
    if failed:
        for cid, failures in failed:
            print(f"  {cid}: {failures}")
        return 1
    print("all literal fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
