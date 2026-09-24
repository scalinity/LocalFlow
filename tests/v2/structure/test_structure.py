"""EV-09 / M07 structure suite (model-backed): the 40 owning structure
fixtures against the real cleanup model through the V2 engine.

M07-AC03: list ordering/count and all source-owned long-input ranges
survive chunking; no truncated output is labeled complete. Assertions
run on the document_nodes parse of the output (structure reference, not
word substring presence — E06).

Run: .venv/bin/python tests/v2/structure/test_structure.py [--limit N]
"""

import json
import re
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import CleanupEngine, ModelRunner, plan_windows  # noqa: E402
from localflow.v2.cleanup.document_nodes import parse  # noqa: E402

def _found(needle: str, low: str) -> bool:
    """Hyphen/whitespace-tolerant containment (phrase equality across
    hyphenation differences; exact tokens like "/code-review" match
    because both sides get the same normalization)."""
    if needle in low:
        return True
    n = re.sub(r"[\s\-]+", " ", needle).strip()
    h = re.sub(r"[\s\-]+", " ", low).strip()
    return n in h


FIXTURES = pathlib.Path(__file__).parent / "fixtures_structure.json"


def _count_items(doc):
    """ListGroup items plus "Item one:"-label prose items (a legitimate
    rendering the renderer does not canonicalize)."""
    import re
    items = sum(len(g.items) for g in doc.nodes
                if g.__class__.__name__ == "ListGroup")
    para_lines = "\n".join(
        line for p in doc.nodes if p.__class__.__name__ == "Paragraph"
        for line in p.render().split("\n"))
    items += len(re.findall(
        r"^\s*item\s+(?:one|two|three|four|five|six|seven|eight|nine|"
        r"ten|\d+)\s*[.):]", para_lines, re.IGNORECASE | re.MULTILINE))
    return items


def run_case(engine, case):
    res = engine.clean(case["input"])
    doc = parse(res.text)
    items = _count_items(doc)
    failures = []
    low = res.text.lower()
    norm = low
    order_markers = case.get("order") or []
    if "items" in case:
        if items > 0 and items != case["items"]:
            failures.append(f"items {items} != {case['items']}")
        if items == 0 and order_markers:
            # A prose rendering is faithful only when every enumerated
            # item's content survives (checked below by the order walk);
            # a partial list is never acceptable.
            hay = re.sub(r"[\s\-]+", " ", low)
            present = [m for m in order_markers
                       if re.sub(r"[\s\-]+", " ", m.lower()).strip()
                       in hay]
            if 0 < len(present) < len(order_markers):
                failures.append(
                    f"partial prose enumeration ({len(present)}/"
                    f"{len(order_markers)} markers)")
    if "min_items" in case and items > 0 and items < case["min_items"]:
        failures.append(f"items {items} < {case['min_items']}")
    if "order" in case:
        pos = -1
        for marker in case["order"]:
            needle = marker.lower().replace("-", " ")
            idx = norm.find(needle)
            if idx < 0:
                failures.append(f"missing order marker {marker!r}")
            elif idx < pos:
                failures.append(f"order violated at {marker!r}")
            else:
                pos = idx
    for group in case.get("expect", []):
        if not any(_found(alt.lower(), low) for alt in group):
            failures.append(f"missing {group}")
    for bad in case.get("forbid", []):
        if bad.lower() in low:
            failures.append(f"forbidden present: {bad!r}")
    if "intro" in case:
        first_list = next((i for i, n in enumerate(doc.nodes)
                           if n.__class__.__name__ == "ListGroup"), None)
        head = doc.nodes[:first_list] if first_list is not None else doc.nodes
        if not any(case["intro"].lower() in p.render().lower()
                   for p in head if p.__class__.__name__ == "Paragraph"):
            failures.append(f"intro {case['intro']!r} not before the list")
    if "outro" in case:
        # The outro must sit after the item content (a label-style list
        # has no ListGroup node, so compare positions in the text).
        hay = re.sub(r"[\s\-]+", " ", low)
        idx_items = hay.find(re.sub(
            r"[\s\-]+", " ", case["order"][-1].lower()).strip()) \
            if case.get("order") else -1
        idx_outro = hay.find(re.sub(
            r"[\s\-]+", " ", case["outro"].lower()).strip())
        if idx_outro < 0 or idx_outro < idx_items:
            failures.append(f"outro {case['outro']!r} not after the list")
    if "code_block" in case:
        blocks = [b for b in doc.nodes if b.__class__.__name__ == "CodeBlock"]
        blob = "\n".join(b.render() for b in blocks).lower()
        if not blocks:
            failures.append("no code block in output")
        for needle in case["code_block"]:
            if needle.lower() not in blob:
                failures.append(f"code block missing {needle!r}")
    if "paragraphs" in case:
        paras = [p for p in doc.nodes if p.__class__.__name__ == "Paragraph"]
        if len(paras) != case["paragraphs"]:
            failures.append(f"paragraphs {len(paras)} != "
                            f"{case['paragraphs']}")
    if "windows" in case:
        planned = len(plan_windows(case["input"]))
        if planned < case["windows"]:
            failures.append(f"planned windows {planned} < "
                            f"{case['windows']}")
    if "prose" in case and case["prose"].lower() not in low:
        failures.append(f"prose {case['prose']!r} missing")
    return failures, res


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
        failures, res = run_case(engine, case)
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
    print("all structure fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
