"""Real configured-model checks for spoken steps; synthetic input, no insertion."""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.config import load
from localflow.v2.cleanup import ModelRunner
from localflow.v2.cleanup.engine import corrections_prompt_revision
from localflow.v2.cleanup.document_nodes import ListGroup, Paragraph, parse
from localflow.v2.cleanup.prompts import prompt_revision
from tests.v2.structure.test_introduced_lists import words


CASES = (
    {"name": "owner_exact",
     "input": "This is a test. I need you to follow step 1, check if this still "
              "works, step 2 confirm that it does, and step 3 write a report "
              "showing your validations.",
     "intro": "this is a test i need you to follow",
     "items": ["check if this still works", "confirm that it does",
               "write a report showing your validations"]},
    {"name": "spoken_words",
     "input": "follow these steps step one open the folder step two select "
              "the file and step three copy the path",
     "intro": "follow these steps",
     "items": ["open the folder", "select the file", "copy the path"]},
    {"name": "no_intro",
     "input": "step 1 check the cable step 2 restart the router",
     "items": ["check the cable", "restart the router"]},
    {"name": "closing_prohibition",
     "input": "Follow these steps. Step 1 inspect the logs. Step 2 run the "
              "tests. Do not deploy yet.",
     "intro": "follow these steps",
     "items": ["inspect the logs", "run the tests"],
     "outro": "do not deploy yet"},
    {"name": "multiple_sentences",
     "input": "Follow these steps. Step 1 open the folder. Keep the backup. "
              "Step 2 inspect the file. Check its date.",
     "intro": "follow these steps",
     "items": ["open the folder keep the backup", "inspect the file check its date"]},
    {"name": "conditions_and_quantities",
     "input": "Follow these steps step 1 if the test fails do not restart "
              "the service step 2 wait 30 seconds and retry only if it is safe",
     "intro": "follow these steps",
     "items": ["if the test fails do not restart the service",
               "wait 30 seconds and retry only if it is safe"]},
    {"name": "internal_conjunction",
     "input": "step one save and close the file and step two check the backup",
     "items": ["save and close the file", "check the backup"]},
    {"name": "questions",
     "input": "Follow these steps. Step 1 is the cable connected? "
              "Step 2 does the light turn on?",
     "intro": "follow these steps",
     "items": ["is the cable connected", "does the light turn on"],
     "questions": 2},
    {"name": "non_one_start",
     "input": "Continue with step 7 inspect the archive and step 8 record the result",
     "intro": "continue with",
     "start": 7, "items": ["inspect the archive", "record the result"]},
    {"name": "prose_references",
     "input": "Repeat step 1 before step 2 because step 2 depends on step 1.",
     "prose": "repeat step 1 before step 2 because step 2 depends on step 1"},
    {"name": "quoted_steps",
     "input": 'The labels "step one" and "step two" appear in the manual.',
     "prose": "the labels step one and step two appear in the manual",
     "quoted": ['"step one"', '"step two"']},
    {"name": "single_step_reference",
     "input": "I completed step 1 and will check the report tomorrow.",
     "prose": "i completed step 1 and will check the report tomorrow"},
    {"name": "skipped_labels",
     "input": "step 1 open the folder step 3 inspect the file",
     "prose": "step 1 open the folder step 3 inspect the file"},
    {"name": "repeated_labels",
     "input": "step 1 open the folder step 1 inspect the file",
     "prose": "step 1 open the folder step 1 inspect the file"},
    {"name": "reference_inside_step",
     "input": "step 1 inspect the file step 2 return to step 1 if it fails",
     "items": ["inspect the file", "return to step 1 if it fails"]},
    {"name": "word_number_continuation",
     "input": "step eleven inspect the archive step twelve record the result",
     "start": 11, "items": ["inspect the archive", "record the result"]},
    {"name": "filler_and_correction",
     "input": "step one um check monday no wait tuesday and step two write the report",
     "items": ["check tuesday", "write the report"]},
)


def check(case, result):
    errors = []
    if result.path != "llm" or result.incomplete:
        errors.append(f"not complete LLM cleanup: {result.path}, {result.fallback_reason}")
    doc = parse(result.text)
    groups = [n for n in doc.nodes if isinstance(n, ListGroup)]
    if "items" in case:
        if len(groups) != 1 or not groups[0].ordered:
            errors.append("expected one numbered list")
        elif groups[0].start != case.get("start", 1):
            errors.append("numbering start changed")
        actual = [words(item) for group in groups for item in group.items]
        if actual != case["items"]:
            errors.append(f"items/order: {actual}")
        first = next((i for i, n in enumerate(doc.nodes)
                      if isinstance(n, ListGroup)), len(doc.nodes))
        if "intro" in case and not any(
                words(n.render()) == case["intro"]
                for n in doc.nodes[:first] if isinstance(n, Paragraph)):
            errors.append("introduction not retained outside list")
        if "outro" in case and not any(
                words(n.render()) == case["outro"]
                for n in doc.nodes[first + 1:] if isinstance(n, Paragraph)):
            errors.append("closing sentence not retained outside list")
    elif groups or words(result.text) != case["prose"]:
        errors.append("prose reference changed or became a list")
    for quoted in case.get("quoted", []):
        if quoted not in result.text:
            errors.append("quoted step label changed")
    if result.text.count("?") != case.get("questions", 0):
        errors.append("question punctuation changed")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=pathlib.Path)
    parser.add_argument("--profile", default="unknown")
    args = parser.parse_args()
    model_id = load()["cleanup_model"]
    print(f"Loading configured cleanup model: {model_id}", flush=True)
    runner = ModelRunner(model_id)
    runner.load()
    engine = runner.engine()
    rows = []
    for case in CASES:
        result = engine.clean(case["input"], destination_profile=args.profile)
        errors = check(case, result)
        rows.append({"case": case["name"], "input": case["input"],
                     "output": result.text, "path": result.path,
                     "observations": result.observations, "errors": errors})
        print(f"{'FAIL' if errors else 'ok'} {case['name']}: {errors}", flush=True)
    report = {"model": model_id, "destination_profile": args.profile,
              "prompt_revision": prompt_revision(),
              "corrections_prompt_revision": corrections_prompt_revision(),
              "total": len(rows),
              "passed": sum(not r["errors"] for r in rows), "cases": rows}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['passed']}/{len(rows)} real-model spoken-step checks passed")
    return 0 if report["passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
