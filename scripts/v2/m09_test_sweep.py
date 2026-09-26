"""Run every tracked tests/**/test_*.py of a code root, one file at a
time, under the desktop-isolating runner and record exit status and
ok-line counts (M09 remediation compatibility sweep; the M08 record
shape).

    .venv/bin/python scripts/v2/m09_test_sweep.py --code-root DIR \
        --output PATH [--only SUBSTR] [--timeout 900]

Files run sequentially: several suites patch the shared AppHelper
dispatcher, so running them in parallel would let one suite's patch
reach another's threads. The model-backed suites are excluded and
listed (they need MLX models; M09 changes no model seam). The live
general pasteboard's change COUNT is read before and after each file —
a counter, never content — so a suite that reached the user's
clipboard despite the isolation is visible.
"""

import argparse
import json
import pathlib
import subprocess
import sys
import time

MODEL_BACKED = (
    "tests/test_cleanup.py",
    "tests/v2/lifecycle/test_worker_live.py",
    "tests/v2/training/test_live_pipeline.py",
    "tests/v2/transforms/test_prompt_engineer_cases.py",
    "tests/v2/fidelity/test_fidelity.py",
)

ap = argparse.ArgumentParser()
ap.add_argument("--code-root", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--only", default=None)
ap.add_argument("--timeout", type=int, default=900)
ap.add_argument("--declared-sha", default=None,
                help="the commit an exported (git archive) tree came from")
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
RUNNER = CODE / "tests" / "v2" / "context" / "run_isolated.py"


def change_count():
    try:
        from AppKit import NSPasteboard
        return int(NSPasteboard.generalPasteboard().changeCount())
    except Exception:
        return None


def tracked_tests():
    out = subprocess.run(["git", "-C", str(CODE), "ls-files", "tests"],
                         capture_output=True, text=True).stdout.split()
    if not out:  # an exported tree (git archive) has no index
        out = [p.relative_to(CODE).as_posix()
               for p in (CODE / "tests").rglob("*.py")]
    return sorted(p for p in out
                  if pathlib.PurePosixPath(p).name.startswith("test_")
                  and p.endswith(".py"))


def run_one(rel):
    before = change_count()
    t0 = time.monotonic()
    try:
        p = subprocess.run([sys.executable, str(RUNNER), str(CODE / rel)],
                           cwd=str(CODE), capture_output=True, text=True,
                           timeout=ARGS.timeout)
        code, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        code = "timeout"
        out = e.stdout.decode() if isinstance(e.stdout, bytes) \
            else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) \
            else (e.stderr or "")
    after = change_count()
    iso = next((ln.strip("[] ").split(": ", 1)[-1]
                for ln in err.splitlines()
                if ln.startswith("[desktop isolated:")), None)
    tail = (err.strip().splitlines() or out.strip().splitlines() or [""])
    return {"file": rel, "exit": code,
            "ok_lines": sum(1 for ln in out.splitlines()
                            if ln.startswith("ok")),
            "seconds": round(time.monotonic() - t0, 1),
            "live_clipboard_changes": (None if None in (before, after)
                                       else after - before),
            "isolation": iso,
            "last_line": tail[-1][:240]}


def main():
    files = [f for f in tracked_tests() if f not in MODEL_BACKED]
    if ARGS.only:
        files = [f for f in files if ARGS.only in f]
    results = []
    for rel in files:
        r = run_one(rel)
        results.append(r)
        print(f"{rel}: exit={r['exit']} ok={r['ok_lines']}"
              f" ({r['seconds']}s)", flush=True)
    sha = subprocess.run(["git", "-C", str(CODE), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(CODE), "status", "--porcelain",
         "--untracked-files=no"], capture_output=True, text=True)
    out = {"schema_version": 1, "tool": "scripts/v2/m09_test_sweep.py",
           "runner": ".venv/bin/python tests/v2/context/run_isolated.py"
                     " <file>, sequential",
           "code_root_sha": sha or ARGS.declared_sha,
           "code_root_is_export": not sha,
           "code_root_modified": (bool(dirty.stdout.strip())
                                  if dirty.returncode == 0 else None),
           "python": sys.version.split()[0],
           "excluded_model_backed": list(MODEL_BACKED),
           "files": len(results),
           "exit_zero": sum(1 for r in results if r["exit"] == 0),
           "ok_lines": sum(r["ok_lines"] for r in results),
           "live_clipboard_changes": [r["file"] for r in results
                                      if r["live_clipboard_changes"]],
           "results": results}
    pathlib.Path(ARGS.output).write_text(
        json.dumps(out, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
