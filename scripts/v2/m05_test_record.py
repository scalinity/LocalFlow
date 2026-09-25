"""Record per-test outcomes of the M05 remediation suites against a code
root (fail-first / pass-final evidence).

Copies the named test modules (and their helper) from THIS checkout into
a scratch directory, puts ``--code-root`` first on ``sys.path`` so the
tests import that tree's production code, runs every ``test_*`` function
in its own subprocess, and writes one JSON record per function
(pass/fail, exception type, first line of the message).

Usage:
    .venv/bin/python scripts/v2/m05_test_record.py --code-root DIR \
        --output PATH tests/v2/vocabulary/test_m05_remediation.py [...]
"""

import argparse
import json
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parents[2]

ap = argparse.ArgumentParser()
ap.add_argument("--code-root", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("tests", nargs="+")
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()

RUNNER = r"""
import importlib.util, sys, traceback, os
sys.path.insert(0, {code!r})
sys.path.insert(0, {code!r} + "/tests/v2/lifecycle")
sys.path.insert(0, {scratch!r})
import m05_helpers
m05_helpers.ROOT = __import__("pathlib").Path({code!r})
spec = importlib.util.spec_from_file_location("mod", {path!r})
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    getattr(mod, {name!r})()
    print("RESULT pass")
except BaseException as e:
    msg = str(e).splitlines()[0][:300] if str(e) else ""
    print("RESULT fail " + type(e).__name__ + " " + msg)
sys.stdout.flush()
os._exit(0)
"""


def main():
    out = {"schema_version": 1, "tool": "scripts/v2/m05_test_record.py",
           "code_root_sha": subprocess.run(
               ["git", "-C", str(CODE), "rev-parse", "HEAD"],
               capture_output=True, text=True).stdout.strip(),
           "code_root_modified": bool(subprocess.run(
               ["git", "-C", str(CODE), "status", "--porcelain",
                "--untracked-files=no"], capture_output=True,
               text=True).stdout.strip()),
           "tests_from_sha": subprocess.run(
               ["git", "-C", str(HERE), "rev-parse", "HEAD"],
               capture_output=True, text=True).stdout.strip(),
           "python": platform.python_version(),
           "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
           "results": {}}
    with tempfile.TemporaryDirectory() as td:
        # Mirror the repo layout so the helper's ROOT (parents[3]) is the
        # scratch root; production code comes from --code-root only.
        scratch = pathlib.Path(td) / "tests" / "v2" / "vocabulary"
        scratch.mkdir(parents=True)
        shutil.copy(HERE / "tests/v2/vocabulary/m05_helpers.py", scratch)
        for rel in ARGS.tests:
            src = HERE / rel
            dst = scratch / src.name
            shutil.copy(src, dst)
            text = dst.read_text(encoding="utf-8")
            names = [ln.split("(")[0][4:] for ln in text.splitlines()
                     if ln.startswith("def test_")]
            for name in names:
                code = RUNNER.format(code=str(CODE), scratch=str(scratch),
                                     path=str(dst), name=name)
                t0 = time.monotonic()
                p = subprocess.run([sys.executable, "-c", code],
                                   capture_output=True, text=True,
                                   timeout=600, cwd=str(CODE))
                line = next((ln for ln in p.stdout.splitlines()
                             if ln.startswith("RESULT ")), "RESULT error "
                            + (p.stderr.strip().splitlines() or [""])[-1])
                parts = line.split(" ", 3)
                out["results"][f"{src.name}::{name}"] = {
                    "status": parts[1],
                    "exception": parts[2] if len(parts) > 2 else None,
                    "message": parts[3] if len(parts) > 3 else None,
                    "seconds": round(time.monotonic() - t0, 2)}
                print(f"{src.name}::{name}: {parts[1]}", flush=True)
    s = [r["status"] for r in out["results"].values()]
    out["counts"] = {k: s.count(k) for k in sorted(set(s))}
    pathlib.Path(ARGS.output).write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(out["counts"])


if __name__ == "__main__":
    main()
