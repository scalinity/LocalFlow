"""Benchmark work-validity/timing gate (AUDIT-16): the GATED selection
timings (warm_selection, scoped_selection, cached_retrieval) call select() on
the SAME snapshot every iteration, so after the first call every timed rep is
a _select_memo dict hit. A mutation that makes every REAL (memo-miss)
selection cost ~150 ms CPU still gets verdict 'pass' (exit 0) with gated
p95 far under 25 ms; only the ungated scope_upgrade cohort shows the cost."""
import json, os, subprocess, sys, pathlib
S = pathlib.Path(__file__).resolve().parent
import os as _os
W = _os.environ.get('M05_CODE', "/tmp/claude-0/-home-user-LocalFlow/60feaa92-3367-5b00-af84-78a53bb5703a/scratchpad/review_fp")
PY = "/home/user/LocalFlow/.venv/bin/python"
MUT = r'''
import time, hashlib
import localflow.v2.vocabulary as V
_real = V.RelevantVocabularySelector.select
def _slow(self, snap, scope_ctx=None, **kw):
    own = (scope_ctx or snap.scope_ctx) == snap.scope_ctx
    if not own or (self.SELECTOR_REVISION, self.max_terms) not in snap._select_memo:
        t = time.perf_counter()
        while time.perf_counter() - t < 0.150:   # CPU burn, not a sleep
            hashlib.sha256(b"x" * 64).digest()
    return _real(self, snap, scope_ctx, **kw)
V.RelevantVocabularySelector.select = _slow
'''
out = S / "bench_memo_out"
code = ("import sys; sys.dont_write_bytecode=True\n"
        f"sys.path.insert(0, {W!r})\n" + MUT +
        f"import runpy; sys.argv=['benchmark_m05.py','--entries','1000','--reps','60','--out',{str(out)!r}]\n"
        f"runpy.run_path({W + '/scripts/v2/benchmark_m05.py'!r}, run_name='__main__')\n")
p = subprocess.run([PY, "-c", code], cwd=str(S), capture_output=True, text=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), timeout=1800)
print(p.stdout[-1500:], p.stderr[-800:])
rep = json.loads((out / "m05_benchmark.json").read_text())
t = rep["timings"]
obs = {"verdict": rep["verdict"], "exit": p.returncode,
       "warm_selection_p95": t["warm_selection"]["p95_ms"],
       "scoped_selection_p95": t["scoped_selection"]["p95_ms"],
       "cached_retrieval_p95": t["cached_retrieval"]["p95_ms"],
       "scope_upgrade_p95(ungated)": t["scope_upgrade_and_packaging"]["p95_ms"]}
print("OBSERVED:", obs)
bad = rep["verdict"] == "pass" and obs["scope_upgrade_p95(ungated)"] >= 150
print("a >=150 ms-per-selection implementation passes the 25 ms selection gate:", bad)
sys.exit(1 if bad else 0)
