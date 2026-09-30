"""Owner-requested list formatting against the real configured cleanup model.

Synthetic text only. Runs cleanup directly, without insertion, AX, clipboard
or keyboard events. A fallback does not count as a formatting pass.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.config import load
from localflow.v2.context.providers import categorize
from localflow.v2.cleanup import ModelRunner
from localflow.v2.cleanup.document_nodes import ListGroup, Paragraph, parse
from localflow.v2.cleanup.prompts import prompt_revision


CASES = (
    {"name": "grocery_spoken",
     "input": "here is a list of grocery items tomatoes potatoes and lemons",
     "intro": "here is a list of grocery items",
     "items": ["tomatoes", "potatoes", "lemons"]},
    {"name": "grocery_punctuated",
     "input": "Here is a list of grocery items: tomatoes, potatoes, and lemons.",
     "intro": "here is a list of grocery items",
     "items": ["tomatoes", "potatoes", "lemons"]},
    {"name": "unseen_supplies",
     "input": "here is a list of supplies pencils erasers and notebooks",
     "intro": "here is a list of supplies",
     "items": ["pencils", "erasers", "notebooks"]},
    {"name": "multiword_packing",
     "input": "packing list rain jacket phone charger and hiking boots",
     "intro": "packing list",
     "items": ["rain jacket", "phone charger", "hiking boots"]},
    {"name": "closing_condition",
     "input": "here is a list of grocery items tomatoes potatoes and lemons. "
              "do not buy onions.",
     "intro": "here is a list of grocery items",
     "items": ["tomatoes", "potatoes", "lemons"],
     "outro": "do not buy onions"},
    {"name": "ordinary_prose",
     "input": "I bought tomatoes potatoes and lemons for dinner.",
     "prose": "i bought tomatoes potatoes and lemons for dinner"},
    {"name": "list_discussion",
     "input": "The list includes tomatoes potatoes and lemons but we "
              "haven't decided what to buy.",
     "prose": "the list includes tomatoes potatoes and lemons but we "
              "haven't decided what to buy"},
    {"name": "quoted_phrase",
     "input": 'The phrase "shopping list" appears in the title.',
     "prose": 'the phrase shopping list appears in the title'},
)


def words(text):
    import re
    return " ".join(re.findall(r"[\w']+", text.lower()))


def check(case, result):
    errors = []
    if result.path != "llm":
        errors.append(f"fallback: {result.fallback_reason}")
    if result.incomplete:
        errors.append("incomplete output")
    doc = parse(result.text)
    groups = [n for n in doc.nodes if isinstance(n, ListGroup)]
    if "items" in case:
        if len(groups) != 1 or groups[0].ordered:
            errors.append("expected one bulleted list")
        actual = [words(item) for group in groups for item in group.items]
        if actual != case["items"]:
            errors.append(f"items/order: {actual}")
        first = next((i for i, n in enumerate(doc.nodes)
                      if isinstance(n, ListGroup)), len(doc.nodes))
        if not any(words(n.render()) == case["intro"]
                   for n in doc.nodes[:first] if isinstance(n, Paragraph)):
            errors.append("introduction not retained outside list")
        if "outro" in case and not any(
                words(n.render()) == case["outro"]
                for n in doc.nodes[first + 1:] if isinstance(n, Paragraph)):
            errors.append("closing condition not retained outside list")
    else:
        if groups:
            errors.append("ordinary prose became a list")
        if words(result.text) != case["prose"]:
            errors.append("prose wording changed")
    if case["name"] == "quoted_phrase" and '"shopping list"' not in result.text:
        errors.append("quoted phrase changed")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=pathlib.Path)
    parser.add_argument("--profile", default=categorize("com.openai.codex"))
    args = parser.parse_args()
    model_id = load()["cleanup_model"]
    print(f"Loading configured cleanup model: {model_id}", flush=True)
    runner = ModelRunner(model_id)
    runner.load()
    engine = runner.engine()
    rows = []
    for case in CASES:
        result = engine.clean(case["input"],
                              destination_profile=args.profile)
        errors = check(case, result)
        rows.append({"case": case["name"], "input": case["input"],
                     "output": result.text, "path": result.path,
                     "observations": result.observations,
                     "errors": errors})
        print(f"{'FAIL' if errors else 'ok'} {case['name']}: {errors}", flush=True)
    report = {"model": model_id, "destination_profile": args.profile,
              "prompt_revision": prompt_revision(),
              "passed": sum(not r["errors"] for r in rows),
              "total": len(rows), "cases": rows}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['passed']}/{len(rows)} real-model list formatting checks passed")
    return 0 if report["passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
