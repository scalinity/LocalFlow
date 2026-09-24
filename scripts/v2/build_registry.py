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


def _read_catalog(path, label, problems):
    try:
        return pathlib.Path(path).read_text()
    except OSError as e:
        problems.append(f"{label} catalog unreadable: {path} "
                        f"({type(e).__name__})")
        return None


def spec_requirements(path=None, problems=None):
    """Requirement rows from the S05 register: id -> (requirement, owners).

    Structural problems (missing/unreadable catalog, missing section, empty
    register, duplicate IDs, malformed rows) are appended to ``problems``
    when a list is given — never silently dropped (M01-AUDIT-10)."""
    problems = [] if problems is None else problems
    out = {}
    text = _read_catalog(path or SPEC, "S05 requirement", problems)
    if text is None:
        return out
    in_register = found = False
    for line in text.splitlines():
        if line.startswith("## S05."):
            in_register = found = True
            continue
        if in_register and line.startswith("## S06."):
            break
        if in_register and line.startswith("|"):
            m = REQ_ROW.match(line)
            if m:
                rid = m.group(1)
                if rid in out:
                    problems.append(f"duplicate requirement row {rid}")
                    continue
                owners = m.group(3).strip()
                if not m.group(2).strip() or not owners:
                    problems.append(f"{rid} row has an empty requirement "
                                    f"or owner cell")
                out[rid] = {
                    "requirement": m.group(2).strip(),
                    "owner_milestones": owners,
                }
            elif "LF-R" in line:
                problems.append(f"malformed S05 row: {line.strip()[:100]}")
    if not found:
        problems.append("S05 requirement register section not found")
    elif not out:
        problems.append("S05 requirement register is empty")
    return out


def eval_suites(path=None, problems=None):
    """Suite rows from the E08 catalog: id -> (name, requirement ids)."""
    problems = [] if problems is None else problems
    out = {}
    text = _read_catalog(path or EVAL, "E08 suite", problems)
    if text is None:
        return out
    in_catalog = found = False
    for line in text.splitlines():
        if line.startswith("## E08."):
            in_catalog = found = True
            continue
        if in_catalog and line.startswith("## E09."):
            break
        if in_catalog and line.startswith("|"):
            m = SUITE_ROW.match(line)
            if m:
                sid = m.group(1)
                if sid in out:
                    problems.append(f"duplicate suite row {sid}")
                    continue
                reqs = re.findall(r"LF-R\d{2,}", m.group(4))
                if re.search(r"LF-R(?!\d{2,})", m.group(4)):
                    problems.append(f"{sid} lists a malformed requirement ID")
                out[sid] = {"name": m.group(2).strip(), "requirements": reqs}
            elif "EV-" in line:
                problems.append(f"malformed E08 row: {line.strip()[:100]}")
    if not found:
        problems.append("E08 suite catalog section not found")
    elif not out:
        problems.append("E08 suite catalog is empty")
    return out


def derive(spec_path=None, eval_path=None):
    """(requirements, suites, reverse edges, problems) from the catalogs."""
    problems = []
    reqs = spec_requirements(spec_path, problems)
    suites = eval_suites(eval_path, problems)
    req_to_suites = {rid: [] for rid in reqs}
    for sid, s in suites.items():
        for rid in s["requirements"]:
            if rid in req_to_suites:
                req_to_suites[rid].append(sid)
    for rid, s in req_to_suites.items():
        if not s:
            problems.append(f"{rid} has no evaluation suite")
    for sid, s in suites.items():
        if not s["requirements"]:
            problems.append(f"{sid} lists no requirements")
        for rid in s["requirements"]:
            if rid not in reqs:
                problems.append(f"{sid} references unknown {rid}")
    return reqs, suites, req_to_suites, problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=pathlib.Path,
                    default=ROOT / "docs/v2/registry.json")
    args = ap.parse_args(argv)

    reqs, suites, req_to_suites, problems = derive()

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
    if problems:
        print("ERROR: registry derivation found problems; exit 1",
              file=sys.stderr)
    print(f"wrote {args.output}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
