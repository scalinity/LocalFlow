#!/usr/bin/env python3
"""M08 remediation: can a benchmark with missing work still pass?

The six benchmark-work mutants of the M08 audit corpus (BMUT-01..06) are
each applied ALONE to a disposable copy of a committed tree (``git
archive <rev>``; the live checkout is never touched), and the copy's
benchmark (scripts/v2/benchmark_m08.py) runs there desktop-isolated.

    .venv/bin/python scripts/v2/m08_benchmark_mutation_check.py \
        --output PATH [--rev HEAD] [--scale 0.25] [--only BMUT-01,...]
        [--benchmark-from-worktree]

``--benchmark-from-worktree`` overlays the working tree's
scripts/v2/benchmark_m08.py onto every copy (control and mutants alike;
its sha256 is recorded) — for a benchmark not yet committed.

A mutant is KILLED only when the copy's benchmark rejects its work
(exit 2, ``work_valid: false``) or a declared gate fails (exit 1 with
``work_valid: true``). It SURVIVES when it provably applied and the
benchmark stayed valid and green (exit 0). Everything else — an anchor
that does not match exactly once, a copy importing another tree, a
failing unmutated control, a timeout, a crash (exit 3) or a missing
report — is a HARNESS ERROR and never a kill.
"""

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "bin" / "python")
SVC = "localflow/v2/insertion/service.py"
CLIP = "localflow/v2/insertion/clipboard.py"
BENCH = "scripts/v2/benchmark_m08.py"

MUTANTS = {
    "LF-M08-BMUT-01": ("Remove target validation", [
        (SVC,
         "        lease, verification = validate_target(\n"
         "            self.host, snapshot, job, denied_apps=self.denied_apps,\n"
         "            deny_invalid=self.deny_invalid)\n",
         "        _fm = self.host.frontmost() or {}\n"
         "        lease, verification = TargetLease(\n"
         "            job_id=job.get(\"job_id\"),\n"
         "            attempt=int(job.get(\"attempt\", 1)),\n"
         "            target_snapshot_id=None, context_snapshot_id=None,\n"
         "            frontmost_pid=_fm.get(\"pid\"),\n"
         "            frontmost_bundle=_fm.get(\"bundle\"),\n"
         "            read_allowed=True, destination_recorded=True,\n"
         "            owner_pid=_fm.get(\"pid\"),\n"
         "            element=self.host.focused_element_for(_fm.get(\"pid\"))"
         "), {}\n")]),
    "LF-M08-BMUT-02": ("Make insertion a no-op", [
        (SVC, "        ok = self.host.set_attribute(el, \"AXSelectedText\","
              " text)\n", "        ok = True\n"),
        (SVC, "        posted = self.keyboard.post_paste()\n",
         "        posted = True\n")]),
    "LF-M08-BMUT-03": ("Skip clipboard publication", [
        (SVC, "        if txn.publish(text) is None:\n",
         "        txn.published_generation = self.pasteboard.change_count()\n"
         "        if False:\n")]),
    "LF-M08-BMUT-04": ("Skip destination readback", [
        (SVC, "            readback = self._classify(el, pre, text, "
              "ax=True)\n", "            readback = \"match\"\n"),
        (SVC, "        readback = self._await_readback(el, pre, text)\n",
         "        readback = \"match\"\n")]),
    "LF-M08-BMUT-05": ("Bypass queue and run inline", [
        (SVC, "        self._q.put((\"insert\", op_id, text, job, on_done,"
              " on_observation))\n",
         "        on_done(self._run_insert(op_id, text, job, "
         "on_observation))\n"),
        (SVC, "        self._q.put((\"repaste\", ids.new_id(\"op\"), "
              "last[\"text\"],\n                     last[\"job_id\"], "
              "last[\"attempt\"], on_done))\n",
         "        _r = self._repaste_now(ids.new_id(\"op\"), last[\"text\"],\n"
         "                               last[\"job_id\"], last[\"attempt\"])\n"
         "        if _r is not None and on_done is not None:\n"
         "            on_done(_r)\n"),
        (SVC, "        self._q.put((\"repaste\", ids.new_id(\"op\"), text, "
              "job_id, 1, on_done))\n",
         "        _r = self._repaste_now(ids.new_id(\"op\"), text, job_id, 1)\n"
         "        if _r is not None and on_done is not None:\n"
         "            on_done(_r)\n"),
        (SVC, "        self._q.put((\"undo\", _deliver))\n",
         "        _deliver(self._undo_now())\n")]),
    "LF-M08-BMUT-06": ("Remove ownership check", [
        (CLIP, "        if current != owned:\n", "        if False:\n")]),
}

ap = argparse.ArgumentParser()
ap.add_argument("--rev", default="HEAD")
ap.add_argument("--output", required=True)
ap.add_argument("--scale", default="0.25")
ap.add_argument("--only", default=None)
ap.add_argument("--benchmark-from-worktree", action="store_true")
ARGS = ap.parse_args()


def sha256(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def extract(dst, sha):
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", sha],
                         capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dst)], input=tar, check=True)
    (dst / ".venv").symlink_to(ROOT / ".venv")
    if ARGS.benchmark_from_worktree:
        shutil.copyfile(ROOT / BENCH, dst / BENCH)


def apply(dst, edits):
    for rel, old, new in edits:
        p = dst / rel
        text = p.read_text()
        n = text.count(old)
        if n != 1:
            return f"anchor matched {n}x in {rel}"
        p.write_text(text.replace(old, new))
        if p.read_text() == text:
            return f"patch left {rel} unchanged"
    return None


def import_origin(dst):
    code = ("import sys; sys.path.insert(0, %r); "
            "import localflow.v2.insertion.service as s, "
            "localflow.v2.insertion.clipboard as c; "
            "print(s.__file__); print(c.__file__)" % str(dst))
    p = subprocess.run([PY, "-c", code], capture_output=True, text=True,
                       cwd=str(dst), timeout=60)
    files = p.stdout.split()
    inside = bool(files) and all(
        pathlib.Path(f).resolve().is_relative_to(dst.resolve())
        for f in files)
    return inside, [str(pathlib.Path(f).resolve().relative_to(dst.resolve()))
                    if inside else f for f in files]


def bench(dst):
    out = dst / "bench_out"
    iso = str(dst / "tests/v2/context/run_isolated.py")
    t0 = time.monotonic()
    try:
        p = subprocess.run([PY, iso, str(dst / BENCH), str(out),
                            "--scale", ARGS.scale],
                           capture_output=True, text=True, timeout=1800,
                           cwd=str(dst),
                           env={"PYTHONDONTWRITEBYTECODE": "1",
                                "HOME": str(pathlib.Path.home()),
                                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
        code, log = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        code, log = "timeout", ""
    rec = {"exit": code, "seconds": round(time.monotonic() - t0, 1)}
    try:
        doc = json.loads((out / "m08.json").read_text())
        rec["work_valid"] = doc.get("work_valid")
        rec["verdicts_failed"] = sorted(
            k for k, v in (doc.get("verdicts") or {}).items()
            if v.startswith("fail"))
        rec["invalid_cohorts"] = {
            k: c.get("problems", [])[:2]
            for k, c in doc.get("cohorts", {}).items()
            if c.get("invalid_samples")}
        rec["imported_from"] = doc.get("environment", {}).get(
            "localflow_imported_from_root")
    except Exception as e:
        rec["report_error"] = type(e).__name__
        rec["log_tail"] = log[-600:]
    isolation = [ln for ln in log.splitlines() if "desktop isolated" in ln]
    rec["isolation"] = isolation[-1] if isolation else None
    return rec


def outcome(rec, applied_ok, origin_ok, control_green):
    if not (applied_ok and origin_ok and control_green):
        return "harness_error"
    if rec.get("exit") == 2 and rec.get("work_valid") is False:
        return "killed"
    if rec.get("exit") == 1 and rec.get("work_valid") is True \
            and rec.get("verdicts_failed"):
        return "killed"
    if rec.get("exit") == 0 and rec.get("work_valid") is True:
        return "survived"
    return "harness_error"


def main():
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", ARGS.rev],
                         capture_output=True, text=True,
                         check=True).stdout.strip()
    only = set(ARGS.only.split(",")) if ARGS.only else None
    report = {"schema_version": 1,
              "tool": "scripts/v2/m08_benchmark_mutation_check.py",
              "rev": sha, "scale": float(ARGS.scale),
              "benchmark_overlay": (
                  {"from": "working tree", "sha256": sha256(ROOT / BENCH)}
                  if ARGS.benchmark_from_worktree else None),
              "rule": "killed = work invalid (exit 2) or a declared gate "
                      "failed (exit 1, work valid); a harness error, "
                      "un-applied patch, wrong import tree, failing "
                      "control or timeout is never a kill",
              "mutants": {}}
    with tempfile.TemporaryDirectory() as td:
        ctl = pathlib.Path(td) / "control"
        ctl.mkdir()
        extract(ctl, sha)
        c_origin_ok, c_files = import_origin(ctl)
        control = bench(ctl)
        control_green = (control.get("exit") == 0
                         and control.get("work_valid") is True
                         and c_origin_ok)
        report["control"] = dict(control, import_files=c_files,
                                 import_inside_copy=c_origin_ok)
        report["control_green"] = control_green
        print(f"control: exit={control.get('exit')} valid="
              f"{control.get('work_valid')} green={control_green}",
              flush=True)
        for mid, (name, edits) in MUTANTS.items():
            if only and mid not in only:
                continue
            dst = pathlib.Path(td) / mid
            dst.mkdir()
            extract(dst, sha)
            before = {rel: sha256(dst / rel) for rel, _, _ in edits}
            err = apply(dst, edits)
            after = {rel: sha256(dst / rel) for rel, _, _ in edits}
            applied_ok = err is None and all(before[r] != after[r]
                                             for r in before)
            origin_ok, files = import_origin(dst)
            rec = bench(dst) if applied_ok and origin_ok else {
                "exit": None, "skipped": "not applied or wrong import tree"}
            res = outcome(rec, applied_ok, origin_ok, control_green)
            report["mutants"][mid] = {
                "name": name, "applied": applied_ok, "apply_error": err,
                "patched_files": {r: {"before": before[r][:16],
                                      "after": after[r][:16]}
                                  for r in before},
                "import_files": files, "import_inside_copy": origin_ok,
                "benchmark": rec, "outcome": res}
            print(f"{mid} {name}: {res} (exit={rec.get('exit')}, "
                  f"valid={rec.get('work_valid')})", flush=True)
    pathlib.Path(ARGS.output).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(ARGS.output).write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n")
    killed = [m for m, r in report["mutants"].items()
              if r["outcome"] == "killed"]
    print(json.dumps({"control_green": report["control_green"],
                      "killed": killed,
                      "not_killed": sorted(set(report["mutants"]) -
                                           set(killed))}))
    return 0 if report["control_green"] and len(killed) == len(
        report["mutants"]) else 1


if __name__ == "__main__":
    sys.exit(main())
