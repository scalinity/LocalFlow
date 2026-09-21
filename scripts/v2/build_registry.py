"""M01: build the requirement/suite registry from the canonical documents.

Parses the LF-Rxx table in Spec S05 and the EV-xx table in Evaluation E08
and cross-references them so the registry is derived from the current
amended Markdown, never from a hard-coded count.

Usage:
    .venv/bin/python scripts/v2/build_registry.py [--output docs/v2/registry.json]
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SPEC = ROOT / "docs/v2/LOCALFLOW_V2_SPEC.md"
EVAL = ROOT / "docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md"

REQ_ROW = re.compile(r"^\|\s*(LF-R\d{2,})\s*\|(.*?)\|(.*?)\|\s*$")
SUITE_ROW = re.compile(r"^\|\s*(EV-\d{2,})\s+([^|]+)\|([^|]*)\|([^|]*)\|\s*$")


def spec_requirements():
    """Requirement rows from the S05 register: id -> (requirement, owners)."""
    out = {}
    in_register = False
    skipped = []
    for line in SPEC.read_text().splitlines():
        if line.startswith("## S05."):
            in_register = True
            continue
        if in_register and line.startswith("## S06."):
            break
        if in_register and line.startswith("|"):
            m = REQ_ROW.match(line)
            if m:
                out[m.group(1)] = {
                    "requirement": m.group(2).strip(),
                    "owner_milestones": m.group(3).strip(),
                }
            elif "LF-R" in line:
                skipped.append(line.strip())
    if skipped:
        print(f"WARNING: {len(skipped)} S05 table row(s) did not match the "
              f"expected shape — format drift or a new ID width; inspect:",
              file=sys.stderr)
        for s in skipped[:5]:
            print(f"  {s[:120]}", file=sys.stderr)
    return out


def eval_suites():
    """Suite rows from the E08 catalog: id -> (name, requirement ids)."""
    out = {}
    in_catalog = False
    skipped = []
    for line in EVAL.read_text().splitlines():
        if line.startswith("## E08."):
            in_catalog = True
            continue
        if in_catalog and line.startswith("## E09."):
            break
        if in_catalog and line.startswith("|"):
            m = SUITE_ROW.match(line)
            if m:
                reqs = re.findall(r"LF-R\d{2,}", m.group(4))
                out[m.group(1)] = {"name": m.group(2).strip(), "requirements": reqs}
            elif "EV-" in line:
                skipped.append(line.strip())
    if skipped:
        print(f"WARNING: {len(skipped)} E08 table row(s) did not match the "
              f"expected shape — inspect:", file=sys.stderr)
        for s in skipped[:5]:
            print(f"  {s[:120]}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=pathlib.Path,
                    default=ROOT / "docs/v2/registry.json")
    args = ap.parse_args()

    reqs = spec_requirements()
    suites = eval_suites()

    req_to_suites = {rid: [] for rid in reqs}
    for sid, s in suites.items():
        for rid in s["requirements"]:
            if rid in req_to_suites:
                req_to_suites[rid].append(sid)

    problems = []
    for rid, s in req_to_suites.items():
        if not s:
            problems.append(f"{rid} has no evaluation suite")
    for sid, s in suites.items():
        if not s["requirements"]:
            problems.append(f"{sid} lists no requirements")
        for rid in s["requirements"]:
            if rid not in reqs:
                problems.append(f"{sid} references unknown {rid}")

    registry = {
        "schema_version": 1,
        "derived_from": {
            "spec": "docs/v2/LOCALFLOW_V2_SPEC.md",
            "evaluation": "docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md",
            "method": "S05 requirement register and E08 suite catalog parsed "
                      "from the current amended Markdown",
        },
        "counts": {
            "requirements": len(reqs),
            "suites": len(suites),
            "requirements_without_suite": [r for r, s in req_to_suites.items() if not s],
        },
        "requirements": [
            {
                "id": rid,
                "requirement": reqs[rid]["requirement"],
                "owner_milestones": reqs[rid]["owner_milestones"],
                "suites": sorted(req_to_suites[rid]),
            }
            for rid in sorted(reqs)
        ],
        "suites": [
            {"id": sid, "name": suites[sid]["name"],
             "requirements": suites[sid]["requirements"]}
            for sid in sorted(suites)
        ],
        "problems": problems,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, indent=2) + "\n")
    print(f"requirements: {len(reqs)}  suites: {len(suites)}")
    print(f"problems: {problems or 'none'}")
    print(f"wrote {args.output}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
