"""M04 remediation: score the audit corpus against any code root.

Loads the corpus, its adjudications and the oracle logic from THIS
checkout (tests/v2/normalization/test_m04_audit_corpus.py) and the
normalizer from ``--code-root`` (the audited base, a first pass, the
final repair), then writes per-case outcomes plus denominators by role,
oracle kind, family and finding. Oracles never call the grammar under
test to produce an expectation.

Usage:
    .venv/bin/python scripts/v2/m04_corpus_report.py \
        [--code-root DIR] [--output PATH]
"""

import argparse
import collections
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser()
ap.add_argument("--code-root", default=str(HERE))
ap.add_argument("--output")
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
sys.path.insert(0, str(CODE))

import localflow.v2.normalize  # noqa: E402,F401  (bind the code root first)

spec = importlib.util.spec_from_file_location(
    "m04_corpus_oracles",
    HERE / "tests" / "v2" / "normalization" / "test_m04_audit_corpus.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)
assert pathlib.Path(sys.modules["localflow"].__file__).resolve() \
    .is_relative_to(CODE), "normalizer not loaded from the code root"


def main():
    rows = []
    for case in T.CORPUS["cases"]:
        status, why, out = T.evaluate(case)
        rows.append({"case_id": case["case_id"],
                     "family_id": case["family_id"], "role": case["role"],
                     "oracle": case["oracle"]["kind"],
                     "finding_ids": case["finding_ids"],
                     "input": case["input"], "output": out,
                     "status": status, "detail": why})
    by = {}
    for key in ("role", "oracle"):
        c = collections.defaultdict(collections.Counter)
        for r in rows:
            c[r[key]][r["status"]] += 1
        by[key] = {k: dict(v) for k, v in sorted(c.items())}
    fam = collections.defaultdict(set)
    for r in rows:
        fam[r["status"]].add(r["family_id"])
    finding = collections.defaultdict(collections.Counter)
    for r in rows:
        for f in r["finding_ids"] or ["(none)"]:
            finding[f][r["status"]] += 1
    report = {
        "schema_version": 1, "tool": "scripts/v2/m04_corpus_report.py",
        "code_root_sha": subprocess.run(
            ["git", "-C", str(CODE), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip(),
        "oracle_checkout_sha": subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip(),
        "python": sys.version.split()[0],
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "exposure": "development evidence: consulted during the M04 "
                    "remediation; not an unseen holdout; variants share "
                    "families and are not independent samples",
        "totals": dict(collections.Counter(r["status"] for r in rows)),
        "cases": len(rows),
        "families_total": len({r["family_id"] for r in rows}),
        "families_with_fail": len(fam["fail"]),
        "families_with_residual": len(fam["residual"]),
        "by_role": by["role"], "by_oracle": by["oracle"],
        "by_finding": {k: dict(v) for k, v in sorted(finding.items())},
        "non_pass": [r for r in rows if r["status"] != "pass"],
    }
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if ARGS.output:
        pathlib.Path(ARGS.output).write_text(text + "\n")
    print(json.dumps({k: report[k] for k in (
        "code_root_sha", "totals", "families_with_fail",
        "families_with_residual")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
