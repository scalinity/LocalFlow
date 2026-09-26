"""Run every tests/**/test_*.py of a code root under the declared
non-native shim runner and record exit status + ok-line counts (M05
remediation compatibility sweep; same method as the M04 addendum).

    .venv/bin/python scripts/v2/m05_test_sweep.py --code-root DIR \
        --output PATH [--jobs 4] [--timeout 900]

A pass under the shims is portable orchestration evidence, not native
verification; model-backed suites fail identically on every tree that
lacks MLX/models (recorded, not hidden).
"""

import argparse
import concurrent.futures as cf
import json
import pathlib
import subprocess
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--code-root", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--jobs", type=int, default=4)
ap.add_argument("--timeout", type=int, default=900)
ap.add_argument("--only", default=None)
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
SHIM = CODE / "tests" / "v2" / "lifecycle" / "run_with_shims.py"


def run_one(path: pathlib.Path):
    rel = path.relative_to(CODE).as_posix()
    t0 = time.monotonic()
    try:
        p = subprocess.run([sys.executable, str(SHIM), str(path)],
                           cwd=str(CODE), capture_output=True, text=True,
                           timeout=ARGS.timeout)
        code, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        code = "timeout"
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) \
            else (e.stdout or "")
        err = ""
    oks = sum(1 for ln in out.splitlines() if ln.startswith("ok"))
    tail = (err.strip().splitlines() or out.strip().splitlines() or [""])
    return rel, {"exit": code, "ok_lines": oks,
                 "seconds": round(time.monotonic() - t0, 1),
                 "last_line": tail[-1][:200]}


def main():
    files = sorted(p for p in (CODE / "tests").rglob("test_*.py"))
    if ARGS.only:
        files = [f for f in files if ARGS.only in f.as_posix()]
    results = {}
    with cf.ThreadPoolExecutor(ARGS.jobs) as ex:
        for rel, r in ex.map(run_one, files):
            results[rel] = r
            print(f"{rel}: exit={r['exit']} ok={r['ok_lines']}"
                  f" ({r['seconds']}s)", flush=True)
    out = {"schema_version": 1, "tool": "scripts/v2/m05_test_sweep.py",
           "code_root_sha": subprocess.run(
               ["git", "-C", str(CODE), "rev-parse", "HEAD"],
               capture_output=True, text=True).stdout.strip(),
           "code_root_modified": bool(subprocess.run(
               ["git", "-C", str(CODE), "status", "--porcelain",
                "--untracked-files=no"], capture_output=True,
               text=True).stdout.strip()),
           "python": sys.version.split()[0], "files": len(results),
           "results": results}
    pathlib.Path(ARGS.output).write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
