"""The 20 implementation mutations of the M08 audit corpus, run for real.

For each LF-M08-MUT-nn: export the tracked tree at HEAD into a
disposable directory (``git archive``), apply exactly that semantic
weakening to the copied production module (every edit must match its
text exactly once — or, declared, every occurrence), prove the patch
applied (the file's hash changed) and that the killing run imported
``localflow`` from THAT copy, then run the corpus's killing case(s)
there. Outcomes:

- ``killed``        — the unmutated control passed the killer, the
                      mutant made it FAIL (the case was reached and an
                      invariant check failed);
- ``survived``      — control green, mutant still passes;
- ``harness_error`` — anything else: an edit that did not match, an
                      import from the wrong tree, a failing control, an
                      error/NOT_RUN in the killing case, a timeout.
                      Never counted as a kill.

Portable killers run under ``tests/v2/context/run_isolated.py``; the
native killer (LF-M08-MUT-18's primary case F07-C01) runs the owned
native suite, natively, when the terminal holds the Accessibility grant.

    .venv/bin/python scripts/v2/m08_mutation_check.py --json OUT \
        [--only LF-M08-MUT-01,...] [--no-native]
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"
RUNNER = "tests/v2/insertion/m08_corpus_runner.py"
NATIVE = "tests/v2/insertion/test_native_insertion.py"
ISOLATED = "tests/v2/context/run_isolated.py"

VAL = "localflow/v2/insertion/validation.py"
SVC = "localflow/v2/insertion/service.py"
CLIP = "localflow/v2/insertion/clipboard.py"
OBS = "localflow/v2/insertion/observation.py"
SNAP = "localflow/v2/context/snapshot.py"
STORE = "localflow/v2/store.py"

MUTANTS = [
    {"id": "LF-M08-MUT-01", "name": "Ignore contradictory bundle",
     "file": SNAP, "edits": [(
         "    if bundle is not None and live_bundle is not None \\\n"
         "            and bundle != live_bundle:\n"
         "        return False\n", "")],
     "killers": ["LF-M08-F01-C02"]},
    {"id": "LF-M08-MUT-02", "name": "Ignore native window mismatch",
     "file": VAL, "edits": [(
         "            VERIFICATION_PASS if live_win == recorded_win\n"
         "            else VERIFICATION_FAIL)",
         "            VERIFICATION_PASS)")],
     "killers": ["LF-M08-F02-C01"]},
    {"id": "LF-M08-MUT-03", "name": "Ignore readable title mismatch",
     "file": VAL, "edits": [(
         "            else (VERIFICATION_PASS if title == window_title\n"
         "                  else VERIFICATION_FAIL))",
         "            else VERIFICATION_PASS)")],
     "killers": ["LF-M08-F02-C02"]},
    {"id": "LF-M08-MUT-04", "name": "Use unchecked system-focused element",
     "file": VAL, "edits": [(
         "    fn = getattr(host, \"focused_element_for\", None)\n"
         "    el = fn(pid) if fn is not None else None\n",
         "    el = host.focused_element()\n"), (
         "    return (el, True) if host.element_pid(el) == pid"
         " else (None, False)",
         "    return el, True")],
     "killers": ["LF-M08-F04-C01"]},
    {"id": "LF-M08-MUT-05", "name": "Skip applicable deny check",
     "file": VAL, "edits": [(
         "    if snapshot_denied or app_denied(bundle, denied_apps or ()):\n"
         "        return False, \"denied_app\", None\n", "")],
     "killers": ["LF-M08-F05-C01"]},
    {"id": "LF-M08-MUT-06", "name": "Trust unkept nonempty selection range",
     "file": VAL, "edits": [(
         "    elif field.selected_text is None or selected_range is None:",
         "    elif selected_range is None:"), (
         "            same_text = sel_text == field.selected_text",
         "            same_text = field.selected_text is None or"
         " sel_text == field.selected_text")],
     "killers": ["LF-M08-F06-C04"]},
    {"id": "LF-M08-MUT-07", "name": "Remove pre-write consistency read",
     "file": SVC, "edits": [(
         "        region = self._region(el, start, n, total)\n"
         "        if region is None:\n"
         "            return None\n",
         "        region = self._region(el, start, n, total)\n"
         "        if region is None:\n"
         "            region = \"\"\n")],
     "killers": ["LF-M08-F12-C03"]},
    {"id": "LF-M08-MUT-08", "name": "Confirm from LocalFlow clipboard",
     "file": SVC, "edits": [(
         "            cls = self._classify(el, pre, text)\n"
         "            if cls in (\"match\", \"normalized\") \\\n",
         "            cls = (\"match\" if self.pasteboard.string_for_type(\n"
         "                \"public.utf8-plain-text\") == text\n"
         "                else self._classify(el, pre, text))\n"
         "            if cls in (\"match\", \"normalized\") \\\n")],
     "killers": ["LF-M08-F11-C01"]},
    {"id": "LF-M08-MUT-09", "name": "Always restore", "file": CLIP,
     "edits": [(
         "        if current != owned:\n", "        if False:\n")],
     "killers": ["LF-M08-F10-C02"]},
    {"id": "LF-M08-MUT-10",
     "name": "Compare clipboard text instead of generation", "file": CLIP,
     "edits": [(
         "        self.published_generation = self.pb.clear_and_write_text("
         "text)\n",
         "        self._published_text = text\n"
         "        self.published_generation = self.pb.clear_and_write_text("
         "text)\n"), (
         "        if current != owned:\n",
         "        if self.pb.string_for_type(\"public.utf8-plain-text\")"
         " != self._published_text:\n")],
     "killers": ["LF-M08-F10-C04"]},
    {"id": "LF-M08-MUT-11", "name": "Promote partial to confirmed",
     "file": SVC, "edits": [(
         "        if readback == \"match\":\n"
         "            if not lease.destination_recorded:",
         "        if readback in (\"match\", \"partial\"):\n"
         "            if not lease.destination_recorded:")],
     "killers": ["LF-M08-F13-C01"]},
    {"id": "LF-M08-MUT-12", "name": "Bypass terminal guard without context",
     "file": SVC, "edits": [(
         "            category = categorize(bundle) if bundle else \"unknown\"",
         "            category = \"unknown\"")],
     "killers": ["LF-M08-F16-C02"]},
    {"id": "LF-M08-MUT-13", "name": "Do not rearm wake signal", "file": OBS,
     "edits": [("        self._locked.clear()\n", "        pass\n")],
     "killers": ["LF-M08-F21-C02"]},
    {"id": "LF-M08-MUT-14", "name": "Allow undo over changed owned text",
     "file": SVC, "edits": [(
         "        if current != rec[\"inserted_text\"]:",
         "        if False:")],
     "killers": ["LF-M08-F17-C03"]},
    {"id": "LF-M08-MUT-15", "name": "Skip observer field identity validation",
     "file": OBS, "edits": [(
         "        if self.lease.element is not None and el != "
         "self.lease.element:\n"
         "            return None, STOP_FIELD_CHANGED\n", "")],
     "killers": ["LF-M08-F19-C02"]},
    {"id": "LF-M08-MUT-16", "name": "Bypass deletion guard", "file": STORE,
     "edits": [(
         "    conn_assert_job_writable(conn, job_id)  # M02-AUDIT-01 barrier\n",
         "    pass\n")],
     "killers": ["LF-M08-F23-C03"]},
    {"id": "LF-M08-MUT-17", "name": "Run insertion/repaste work on UI callback",
     "file": SVC, "edits": [(
         "        self._q.put((\"repaste\", ids.new_id(\"op\"), last[\"text\"],\n"
         "                     last[\"job_id\"], last[\"attempt\"], on_done))\n",
         "        self._repaste_now(ids.new_id(\"op\"), last[\"text\"],\n"
         "                          last[\"job_id\"], last[\"attempt\"])\n"), (
         "        self._q.put((\"repaste\", ids.new_id(\"op\"), text, job_id,"
         " 1, on_done))\n",
         "        self._repaste_now(ids.new_id(\"op\"), text, job_id, 1)\n")],
     "killers": ["LF-M08-F18-C04"]},
    {"id": "LF-M08-MUT-18", "name": "Use code-point length as UTF-16 length",
     "file": SVC, "edits": [(
         "        n = utf16_len(text)\n", "        n = len(text)\n")],
     "replace_all": True,
     "killers": ["LF-M08-F07-C05"], "native_killers": ["LF-M08-F07-C01"]},
    {"id": "LF-M08-MUT-19", "name": "Observe without capture permission",
     "file": SVC, "edits": [(
         "                or job.get(\"observation_consent\") is not True \\\n",
         "")],
     "killers": ["LF-M08-F19-C04"]},
    {"id": "LF-M08-MUT-20", "name": "Remove operation idempotency fence",
     "file": SVC, "edits": [(
         "            if op_id in self._consumed_ops:\n",
         "            if False:\n")],
     "killers": ["LF-M08-F15-C01"]},
]


def export(dest: pathlib.Path) -> str:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    arch = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"],
                          capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=arch, check=True)
    # Suites that spawn <root>/.venv/bin/python need the interpreter.
    (dest / ".venv").symlink_to(ROOT / ".venv")
    return head


def apply(root: pathlib.Path, m: dict) -> dict:
    path = root / m["file"]
    text = path.read_text()
    before = hashlib.sha256(text.encode()).hexdigest()
    counts = []
    for old, new in m["edits"]:
        n = text.count(old)
        counts.append(n)
        if n == 0 or (n > 1 and not m.get("replace_all")):
            return {"applied": False, "match_counts": counts,
                    "reason": "edit text did not match exactly once"}
        text = text.replace(old, new)
    path.write_text(text)
    after = hashlib.sha256(text.encode()).hexdigest()
    return {"applied": before != after, "match_counts": counts,
            "sha_before": before[:16], "sha_after": after[:16]}


def run_portable(root, killers, timeout=900):
    out = root / "mut_result.json"
    cmd = [str(PY), ISOLATED, RUNNER, "--only", ",".join(killers),
           "--json", str(out)]
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if not out.exists():
        return {"error": f"no result (exit {p.returncode})",
                "stderr": p.stderr[-400:]}
    d = json.loads(out.read_text())
    out.unlink()
    return {"exit": p.returncode,
            "imported_from": d.get("localflow_imported_from_root"),
            "cases": {r["case_id"]: r["status"] for r in d["cases"]}}


def run_native(root, killers, timeout=900):
    out = root / "mut_native.json"
    cmd = [str(PY), NATIVE, "--only", ",".join(killers), "--json", str(out)]
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if p.returncode == 2:
        return {"not_run": p.stdout.strip()[-200:]}
    if not out.exists():
        return {"error": f"no result (exit {p.returncode})",
                "stderr": p.stderr[-400:]}
    d = json.loads(out.read_text())
    out.unlink()
    counted = [r for r in d["results"] if not r.get("diagnostic")]
    return {"exit": p.returncode,
            "cases": {r["case"]: r["status"] for r in counted},
            "witness": {r["case"]: json.dumps(r.get("witness"),
                                              ensure_ascii=False,
                                              default=str)[:400]
                        for r in counted if r["status"] != "pass"}}


def verdict(control, mutant, killers):
    if "error" in control or "error" in mutant:
        return "harness_error", "run error"
    if control.get("imported_from") not in (None, "localflow/__init__.py") \
            or mutant.get("imported_from") not in (
                None, "localflow/__init__.py"):
        return "harness_error", "imported from another tree"
    cs = control["cases"]
    ms = mutant["cases"]
    if any(cs.get(k) != "pass" for k in killers):
        return "harness_error", f"control not green: {cs}"
    if any(ms.get(k) in (None, "error", "not_run") for k in killers):
        return "harness_error", f"killer not reached: {ms}"
    if any(ms.get(k) == "fail" for k in killers):
        return "killed", None
    return "survived", None


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    native_ok = "--no-native" not in argv
    work = pathlib.Path(tempfile.mkdtemp(prefix="m08-mut-"))
    results = []
    try:
        base = work / "control"
        base.mkdir()
        head = export(base)
        todo = [m for m in MUTANTS if not only or m["id"] in only]
        portable_killers = sorted({k for m in todo for k in m["killers"]})
        native_killers = sorted({k for m in todo
                                 for k in m.get("native_killers", [])})
        t0 = time.monotonic()
        control = run_portable(base, portable_killers)
        native_control = run_native(base, native_killers) \
            if native_ok and native_killers else None
        print(f"control: {control.get('cases')} native: "
              f"{(native_control or {}).get('cases')}"
              f" ({time.monotonic() - t0:.0f}s)")
        for m in todo:
            root = work / m["id"]
            shutil.copytree(base, root, symlinks=True)
            proof = apply(root, m)
            rec = {"mutation_id": m["id"], "name": m["name"],
                   "file": m["file"], "proof": proof,
                   "killers": m["killers"]}
            if not proof["applied"]:
                rec.update(outcome="harness_error",
                           reason="mutation not applied")
            else:
                mut = run_portable(root, m["killers"])
                rec["control"] = {k: control.get("cases", {}).get(k)
                                  for k in m["killers"]}
                rec["mutant"] = mut.get("cases", mut)
                rec["imported_from"] = mut.get("imported_from")
                rec["outcome"], rec["reason"] = verdict(control, mut,
                                                        m["killers"])
                nk = m.get("native_killers")
                if nk and native_ok:
                    nm = run_native(root, nk)
                    rec["native"] = {"control": (native_control or {})
                                     .get("cases", native_control),
                                     "mutant": nm.get("cases", nm)}
                    rec["native"]["witness"] = nm.get("witness")
                    if "cases" in nm and (native_control or {}).get(
                            "cases"):
                        nc = native_control["cases"]
                        if not all(nc.get(k) == "pass" for k in nk):
                            rec["native"]["outcome"] = "harness_error"
                            rec["native"]["reason"] = (
                                "native control not green: "
                                f"{native_control.get('witness')}")
                        elif any(nm["cases"].get(k) == "fail" for k in nk):
                            rec["native"]["outcome"] = "killed"
                        elif all(nm["cases"].get(k) == "pass" for k in nk):
                            rec["native"]["outcome"] = "survived"
                        else:
                            rec["native"]["outcome"] = "harness_error"
                    else:
                        rec["native"]["outcome"] = "not_run"
            shutil.rmtree(root, ignore_errors=True)
            results.append(rec)
            print(f"{rec['outcome']:14} {m['id']} {m['name']}"
                  f" {rec.get('reason') or ''}"
                  f" {('native=' + rec['native']['outcome']) if 'native' in rec else ''}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    tally = {}
    for r in results:
        tally[r["outcome"]] = tally.get(r["outcome"], 0) + 1
    print(json.dumps(tally))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            "tool": "scripts/v2/m08_mutation_check.py",
            "code_sha": head, "control": control,
            "native_control": native_control,
            "summary": tally, "results": results}, indent=1) + "\n")
    return 0 if tally.get("killed", 0) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
