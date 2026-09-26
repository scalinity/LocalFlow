"""M06 remediation: can a broken implementation earn green evidence?

Each of the audit's 18 mutations (corpus ``mutations``) is applied ALONE
to a disposable copy of a committed tree (``git archive <rev>``; the live
checkout is never touched) and its named killer cases re-run there with
the copy's own corpus runner, plus the copy's regression suite. Four
benchmark mutants (corpus case LF-M06-M005) run the copy's benchmark.

    .venv/bin/python scripts/v2/m06_mutation_check.py --rev HEAD \
        --output PATH [--only MUT-01,MUT-02] [--skip-benchmark]

A mutation is KILLED when a named killer case fails or errors under it,
or the regression suite exits non-zero. It SURVIVES when it provably
applied and everything stayed green. An anchor that does not match its
file exactly once is a harness ERROR — never a kill. The unmutated copy
is the control: every killer case and the suite must pass, else
``control_green`` is false and no kill is claimed. Native killers
(LF-M06-N00x) run without desktop isolation — they only touch the
synthetic helper window — and are ``not_run`` where that is unavailable.
"""

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser()
ap.add_argument("--rev", default="HEAD")
ap.add_argument("--output", required=True)
ap.add_argument("--only", default=None)
ap.add_argument("--skip-benchmark", action="store_true")
ARGS = ap.parse_args()
PY = str(ROOT / ".venv" / "bin" / "python")

COLL = "localflow/v2/context/collector.py"
SNAP = "localflow/v2/context/snapshot.py"
PROV = "localflow/v2/context/providers.py"
APP = "localflow/app.py"

MUTATIONS = {
    "M06-MUT-01": [(COLL,
                    "        if target.denied:\n"
                    "            # Identity only: no Accessibility call of any"
                    " kind.\n            omit_all(OMISSION_DENIED)\n"
                    "            return\n", "")],
    "M06-MUT-02": [(COLL, "                    coll.errors[name] = "
                    "type(e).__name__\n", "                    pass\n")],
    "M06-MUT-03": [(COLL, "        coll.thread.start()\n        return coll\n",
                    "        self._last = coll\n        coll.thread.start()\n"
                    "        return coll\n"),
                   (COLL, "        if coll is None:\n            return None\n"
                    "        if target_snapshot_id is not None \\\n",
                    "        coll = getattr(self, \"_last\", coll)\n"
                    "        if coll is None:\n            return None\n"
                    "        if target_snapshot_id is not None \\\n")],
    "M06-MUT-04": [(COLL, "            el = host.focused_element_for("
                    "target.app_pid)\n            if el is not None and "
                    "host.element_pid(el) != target.app_pid:",
                    "            el = host.focused_element()\n"
                    "            if False:")],
    "M06-MUT-05": [(SNAP, "        object.__setattr__(self, \"identifiers\",\n"
                    "                           None if self.identifiers is "
                    "None\n                           else freeze(dict("
                    "self.identifiers)))\n", "")],
    "M06-MUT-06": [("localflow/v2/training.py",
                    "        if not self.retain_context:\n",
                    "        if not self.retain_context and not downstream:\n")],
    "M06-MUT-07": [(COLL, "            key = (target.app_pid, target.app_bundle,"
                    " el_token, win_token,\n                   doc_url)",
                    "            key = (target.app_pid, target.app_bundle,"
                    " window_title,\n                   doc_url)")],
    "M06-MUT-08": [(APP, "        snap = v2.vocabulary.VocabularySnapshot("
                    "entries, scope)\n",
                    "        snap = v2.vocabulary.VocabularySnapshot("
                    "self._vocab.entries(), scope)\n")],
    "M06-MUT-09": [(APP, "            job[\"scope_disposition\"] = "
                    "\"widening_failed\"\n",
                    "            job[\"scope_disposition\"] = "
                    "\"widening_failed\"\n            if self._widen_cache:\n"
                    "                job[\"norm_context\"] = "
                    "snap.to_engine_context(self._widen_cache[2])\n")],
    "M06-MUT-10": [("localflow/v2/store.py",
                    "        def op():\n            conn_assert_job_writable("
                    "self._db, job_id)\n            env = json.loads(",
                    "        def op():\n            env = json.loads(")],
    "M06-MUT-11": [(COLL, "            coll.sealed = True\n", "")],
    "M06-MUT-12": [(SNAP, "        return live_bundle == bundle\n    return "
                    "False\n", "        return live_bundle == bundle\n"
                    "    return True\n")],
    "M06-MUT-13": [(PROV, "    if type(value).__name__ == \"AXValueRef\":",
                    "    if False:")],
    "M06-MUT-14": [(COLL, "        if key is None or origin is None or "
                    "origin.reason is not None \\\n                or "
                    "origin.value is None or getattr(origin, \"cached\", "
                    "False):", "        if key is None or origin is None:")],
    "M06-MUT-15": [(APP, "        released_mono = time.monotonic()\n",
                    "        released_mono = None\n"),
                   (APP, "                self._m10_finalize_upgrade(job)\n",
                    "                self._m10_finalize_upgrade(job)\n"
                    "                job[\"released_mono\"] = "
                    "time.monotonic()\n")],
    "M06-MUT-16": [(APP, "        hit = self._cached_widening(entries, scope)\n"
                    "        if hit is not None:\n            return hit\n"
                    "        released = ",
                    "        return None\n        released = ")],
    "M06-MUT-17": [("localflow/config.py",
                    "    if not isinstance(enabled, bool):\n        problems"
                    ".append((\"context_enabled\", \"not_a_boolean\"))\n"
                    "        enabled = False\n",
                    "    enabled = bool(enabled)\n")],
    "M06-MUT-18": [("localflow/v2/store.py", "                if not leased:\n",
                    "                if False:\n")],
}

BENCH = "scripts/v2/benchmark_m06.py"
BENCH_MUTANTS = {
    "force_enabled_off_arm": [(BENCH, "cfg={\"context_enabled\": "
                               "context_on})",
                               "cfg={\"context_enabled\": True})")],
    "clock_after_release_work": [(BENCH,
                                  "        t0 = time.perf_counter()\n"
                                  "        hk.on_release()\n"
                                  "        ms = (time.perf_counter() - t0)",
                                  "        hk.on_release()\n"
                                  "        t0 = time.perf_counter()\n"
                                  "        ms = (time.perf_counter() - t0)")],
    "noop_scope_upgrade": MUTATIONS["M06-MUT-16"],
    "omit_hint_packaging": [("localflow/v2/training.py",
                             "        if not ctx.collecting or hint_set is "
                             "None or ctx.example_id:\n",
                             "        if True:\n")],
}


def killers():
    corpus = json.loads((ROOT / "tests/v2/context/m06_audit_corpus.json")
                        .read_text())
    return {m["mutation_id"]: m["must_be_killed_by_case_ids"]
            for m in corpus["mutations"]}


def extract(dst):
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", ARGS.rev],
                         capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dst)], input=tar, check=True)
    (dst / ".venv").symlink_to(ROOT / ".venv")


def apply(dst, edits):
    for rel, old, new in edits:
        p = dst / rel
        text = p.read_text()
        n = text.count(old)
        if n != 1:
            return f"anchor matched {n}x in {rel}"
        p.write_text(text.replace(old, new))
    return None


def run(cmd, cwd, timeout=900):
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout,
                           env={"PYTHONDONTWRITEBYTECODE": "1",
                                "LOCALFLOW_NO_PROMPT": "1",
                                "HOME": str(pathlib.Path.home()),
                                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
        return p.returncode, p.stdout + p.stderr, time.monotonic() - t0
    except subprocess.TimeoutExpired:
        return "timeout", "", time.monotonic() - t0


def evaluate(dst, cases):
    iso = str(dst / "tests/v2/context/run_isolated.py")
    runner = str(dst / "tests/v2/context/m06_corpus_runner.py")
    out = {}
    plain = [c for c in cases if not c.startswith("LF-M06-N")]
    native = [c for c in cases if c.startswith("LF-M06-N")]
    for group, isolated in ((plain, True), (native, False)):
        if not group:
            continue
        res = dst / f"corpus_{'iso' if isolated else 'native'}.json"
        cmd = ([PY, iso] if isolated else [PY]) + [
            runner, "--code-root", str(dst), "--only", ",".join(group),
            "--output", str(res)] + (["--skip-native"] if isolated else [])
        code, log, secs = run(cmd, dst)
        try:
            rep = json.loads(res.read_text())["cases"]
        except Exception:
            rep = {}
        for c in group:
            out[c] = rep.get(c, {}).get("status", f"no_result(exit={code})")
    code, log, secs = run([PY, iso, str(dst / "tests/v2/context/"
                                          "test_m06_remediation.py")], dst)
    last = [ln for ln in log.splitlines() if "regressions passed" in ln]
    out["regression_suite"] = {"exit": code,
                               "summary": last[-1] if last else None}
    return out


def verdict(result, cases):
    killed_by = [c for c in cases if result.get(c) in ("fail", "error")]
    if result["regression_suite"]["exit"] != 0:
        killed_by.append("tests/v2/context/test_m06_remediation.py")
    return killed_by


def bench(dst):
    iso = str(dst / "tests/v2/context/run_isolated.py")
    out = dst / "bench"
    code, log, secs = run([PY, iso, str(dst / BENCH), str(out),
                           "--entries", "2000", "--reps", "6"], dst)
    try:
        rep = json.loads((out / "m06.json").read_text())
        return {"exit": code, "verdict": rep.get("verdict"),
                "problems": rep.get("problems", [])[:4],
                "seconds": round(secs, 1)}
    except Exception:
        return {"exit": code, "verdict": None, "seconds": round(secs, 1)}


def main():
    kmap = killers()
    only = set(ARGS.only.split(",")) if ARGS.only else None
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", ARGS.rev],
                         capture_output=True, text=True).stdout.strip()
    report = {"schema_version": 1, "tool": "scripts/v2/m06_mutation_check.py",
              "rev": sha, "mutations": {}, "benchmark_mutants": {}}
    all_cases = sorted({c for v in kmap.values() for c in v})
    with tempfile.TemporaryDirectory() as td:
        ctl = pathlib.Path(td) / "control"
        ctl.mkdir()
        extract(ctl)
        control = evaluate(ctl, all_cases)
        green = all(control[c] == "pass" or (
            c.startswith("LF-M06-N") and control[c] == "not_run")
            for c in all_cases) and control["regression_suite"]["exit"] == 0
        report["control"] = control
        report["control_green"] = green
        print(f"control green={green}", flush=True)
        for mid, edits in MUTATIONS.items():
            if only and mid not in only:
                continue
            dst = pathlib.Path(td) / mid
            dst.mkdir()
            extract(dst)
            err = apply(dst, edits)
            if err:
                report["mutations"][mid] = {"disposition": "harness_error",
                                            "reason": err}
                print(f"{mid}: harness_error {err}", flush=True)
                continue
            res = evaluate(dst, kmap[mid])
            killed_by = verdict(res, kmap[mid])
            disp = ("killed" if killed_by and green else
                    "survived" if green else "control_invalid")
            report["mutations"][mid] = {"disposition": disp,
                                        "killed_by": killed_by,
                                        "killer_cases": kmap[mid],
                                        "results": res}
            print(f"{mid}: {disp} by {killed_by}", flush=True)
        if not ARGS.skip_benchmark:
            bctl = pathlib.Path(td) / "bench_control"
            bctl.mkdir()
            extract(bctl)
            base = bench(bctl)
            report["benchmark_control"] = base
            report["benchmark_control_pass"] = base.get("exit") == 0
            for name, edits in BENCH_MUTANTS.items():
                dst = pathlib.Path(td) / f"bench_{name}"
                dst.mkdir()
                extract(dst)
                err = apply(dst, edits)
                if err:
                    report["benchmark_mutants"][name] = {
                        "rejected": False, "harness_error": err}
                    continue
                r = bench(dst)
                r["rejected"] = r.get("exit") == 2
                report["benchmark_mutants"][name] = r
                print(f"bench {name}: {r}", flush=True)
    pathlib.Path(ARGS.output).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(ARGS.output).write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n")
    surv = [m for m, r in report["mutations"].items()
            if r["disposition"] != "killed"]
    bsurv = [m for m, r in report["benchmark_mutants"].items()
             if not r.get("rejected")]
    print(json.dumps({"control_green": report["control_green"],
                      "not_killed": surv, "benchmark_not_rejected": bsurv}))
    return 0 if report["control_green"] and not surv and not bsurv else 1


if __name__ == "__main__":
    raise SystemExit(main())
