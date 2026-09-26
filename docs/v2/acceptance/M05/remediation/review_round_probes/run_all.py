"""Run every review-round-1 probe against a code root; record exit and
the verdict lines. Usage: reprobe_run.py CODE_ROOT OUT.json"""
import json, os, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent / "reprobe"
code = str(pathlib.Path(sys.argv[1]).resolve())
SHIM = {"fam_rev1.py", "p12_panel_unseen_alias.py", "p14_hub_preview_scope.py",
        "p17_torn_entries_and_history.py", "p18_lastgood_resurrects_disabled.py",
        "p21_hint_limit_config.py"}
PROBES = sorted(p.name for p in HERE.glob("p*.py") if p.name not in (
    "p06_det_child.py",)) + ["fam_rev1.py"]
env = dict(os.environ, M05_CODE=code, PYTHONDONTWRITEBYTECODE="1")
py = "/home/user/LocalFlow/.venv/bin/python"
out = {"code_root": code, "code_sha": subprocess.run(["git", "-C", code, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
       "code_root_modified": bool(subprocess.run(["git", "-C", code, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()),
       "probes": {}}
for name in PROBES:
    cmd = [py, str(pathlib.Path(code) / "tests/v2/lifecycle/run_with_shims.py"), name] if name in SHIM else [py, name]
    if name == "p10_mutation_witness.py":
        pass
    p = subprocess.run(cmd, cwd=str(HERE), env=env, capture_output=True, text=True, timeout=3600)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith(("FAIL", "OK", "VIOLATIONS"))]
    out["probes"][name] = {"exit": p.returncode, "violations": [ln for ln in lines if ln.startswith("FAIL")][:20],
                           "summary": [ln for ln in lines if ln.startswith("VIOLATIONS")][-1:] or p.stdout.strip().splitlines()[-1:],
                           "stderr_tail": p.stderr.strip().splitlines()[-2:]}
    print(name, "exit", p.returncode, out["probes"][name]["summary"], flush=True)
pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
