"""Mutation-harness evidence gap (scripts/v2/m05_mutation_check.py): when the
corpus runner crashes and writes no result file, the harness records
failed_total=0 for the control and reports control_green=True (and
'survived' is decided without looking at the runner's exit code). Simulated
by a runner stand-in that exits 1 and writes nothing -- no file is created
in the worktree (the stand-in never writes ROOT/.m05_mut_*.json)."""
import importlib.util, json, subprocess, sys, pathlib
sys.dont_write_bytecode = True
import os as _os
W = _os.environ.get('M05_CODE', "/tmp/claude-0/-home-user-LocalFlow/60feaa92-3367-5b00-af84-78a53bb5703a/scratchpad/review_fp")
S = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mc", W + "/scripts/v2/m05_mutation_check.py")
mc = importlib.util.module_from_spec(spec); spec.loader.exec_module(mc)
real_run = subprocess.run
def fake_run(cmd, *a, **kw):
    if cmd and cmd[0] == "git":
        return real_run(cmd, *a, **kw)
    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ImportError: crashed runner")
mc.subprocess.run = fake_run
out = S / "p13_harness_out.json"
sys.argv = ["m05_mutation_check.py", "--output", str(out), "--only", "control_unmodified,identity_matcher"]
mc.main()
rep = json.loads(out.read_text())
print(json.dumps({k: rep[k] for k in ("control_green", "survivors")}),
      {n: (m["exit"], m["counts"], m["failed_total"]) for n, m in rep["mutations"].items()})
assert not list(pathlib.Path(W).glob(".m05_mut_*.json")), "no file may be left in the worktree"
bad = rep["control_green"] is True
print("crashed control reported green:", bad)
sys.exit(1 if bad else 0)
