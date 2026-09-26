"""Benchmark-validity mutants for scripts/v2/benchmark_m09.py (corpus
C114–C120, MR14, M09-MUT25..28).

Each mutant removes mandatory work or moves it outside the timed
boundary (benchmark_m09.MUTANTS). The quick benchmark runs once as a
control and once per mutant, each in its own process under the
desktop-isolating runner. Outcomes:

- ``killed``        — the control is work-valid, and the mutant's
                      report marks the cohort it attacks INVALID (so its
                      timing can never qualify, however fast);
- ``survived``      — the control is valid and the mutant still passes
                      that cohort's validity;
- ``harness_error`` — no report, a crash, or an invalid control. Never a
                      kill.

The timer-sensitivity check (C119) runs the quick benchmark with a
known delay injected inside every timed History search: the measured
median must move by at least that delay.

    .venv/bin/python scripts/v2/m09_benchmark_mutation_check.py --json OUT
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "v2" / "context" / "run_isolated.py"
BENCH = ROOT / "scripts" / "v2" / "benchmark_m09.py"

TARGETS = {
    "empty_hit": ("history_search", ["M09-C114", "M09-MUT26"]),
    "skip_view": ("shell", ["M09-C115", "M09-MUT25"]),
    "omit_service": ("shell", ["M09-C115", "M09-MUT25"]),
    "zero_examples": ("training", ["M09-C116", "M09-MUT28"]),
    "drop_publication": ("shell", ["M09-C117"]),
    "inline_dispatch": ("shell", ["M09-C118"]),
    "enqueue_timer": ("shell", ["M09-C119", "M09-MUT27"]),
    "memory_five_views": ("memory", ["M09-C120"]),
}


def run(extra):
    with tempfile.TemporaryDirectory() as td:
        p = subprocess.run(
            [sys.executable, str(RUNNER), str(BENCH), "--quick", "--out",
             td, *extra], cwd=str(ROOT), capture_output=True, text=True,
            timeout=1800)
        path = pathlib.Path(td) / "m09.json"
        report = json.loads(path.read_text()) if path.is_file() else None
    return p.returncode, report, (p.stderr or p.stdout)[-600:]


def main(argv):
    out_path = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv \
        else None
    results = {}
    code, control, tail = run([])
    control_ok = bool(control and control.get("work_valid"))
    results["control"] = {"exit": code, "work_valid": control_ok,
                          "validity": (control or {}).get("validity"),
                          "tail": None if control_ok else tail}
    print(f"control: work_valid={control_ok}", flush=True)
    for name, (cohort, cases) in TARGETS.items():
        if only and name not in only:
            continue
        code, rep, tail = run(["--mutant", name])
        if not control_ok or rep is None:
            outcome, why = "harness_error", ("control invalid"
                                             if not control_ok else tail)
        elif rep.get("mutant") != name:
            outcome, why = "harness_error", "mutant not applied"
        elif rep["validity"].get(cohort) is False:
            outcome, why = "killed", f"{cohort} validity failed"
        else:
            outcome, why = "survived", f"{cohort} still valid"
        results[name] = {"outcome": outcome, "cohort": cohort,
                         "cases": cases, "why": why,
                         "validity": (rep or {}).get("validity"),
                         "work_valid": (rep or {}).get("work_valid"),
                         "timing_qualified":
                             (rep or {}).get("timing_qualified")}
        print(f"{name}: {outcome} ({why})", flush=True)
    # C119 timer sensitivity: an injected delay must appear in the
    # measured median of every search case.
    delay = 50.0
    code, rep, tail = run(["--inject-delay-ms", str(delay)])
    moved = {}
    if rep and control:
        for case, c in rep["history_search"].items():
            base = control["history_search"][case]["p50_ms"]
            moved[case] = round(c["p50_ms"] - base, 1)
    sensitive = bool(moved) and all(v >= delay * 0.9 for v in
                                    moved.values())
    results["timer_sensitivity"] = {"injected_ms": delay,
                                    "p50_delta_ms": moved,
                                    "sensitive": sensitive,
                                    "cases": ["M09-C119"]}
    print(f"timer sensitivity: {sensitive} {moved}", flush=True)
    mutants = [v for k, v in results.items()
               if k not in ("control", "timer_sensitivity")]
    summary = {o: sum(1 for m in mutants if m["outcome"] == o)
               for o in ("killed", "survived", "harness_error")}
    doc = {"tool": "scripts/v2/m09_benchmark_mutation_check.py",
           "benchmark": "scripts/v2/benchmark_m09.py --quick",
           "control_environment": (control or {}).get("environment"),
           "summary": summary, "results": results}
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps(doc, indent=1) + "\n")
    return 0 if summary["killed"] == len(mutants) and sensitive else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
