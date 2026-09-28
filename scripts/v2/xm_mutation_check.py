"""The cross-milestone remediation's mutations, run for real (the merged
three-audit campaign over 340c566).

Each mutation re-introduces one repaired defect (or weakens one repaired
guard) as an exact source edit. For each: export the tracked tree at
HEAD into a disposable directory (``git archive``), apply exactly that
edit to the copied file(s) — every edit must match its text exactly
once — prove the patch applied (each file's hash changed), then run its
killers there.

Each mutant carries a REACH MARKER: the mutated branch appends the
mutation id to the file named by ``XM_MUT_REACH`` when it executes. A
kill needs both halves: the mutated branch was reached AND an
independent semantic assertion failed.

- ``killed``        — control green on every killer, the branch ran, and
                      at least one killer FAILs;
- ``survived``      — control green, branch ran, every killer passes;
- ``not_reached``   — control green but the branch never ran (invalid,
                      never a kill);
- ``harness_error`` — an edit that did not match, a control that is not
                      green, an ERROR in a killer, a timeout. Never a kill.

Killers are the fail-first regressions and controls of
tests/v2/crossmilestone/ (store families run plainly; the rest under
tests/v2/context/run_isolated.py). The live checkout is never modified.

    .venv/bin/python scripts/v2/xm_mutation_check.py --json OUT \
        [--only XM-MU01,...] [--check-edits]
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"
ISOLATED = "tests/v2/context/run_isolated.py"
FAM = "tests/v2/crossmilestone/test_xm_store_families.py"
REM = "tests/v2/crossmilestone/test_xm_remediation.py"

ST = "localflow/v2/store.py"
APP = "localflow/app.py"
TS = "localflow/v2/transforms_store.py"
HUB = "localflow/v2/ui/hub.py"
HQ = "localflow/v2/history_queries.py"
LN = "localflow/v2/learning.py"
PR = "localflow/v2/profile.py"
EV = "localflow/v2/curation/evidence.py"
TR = "localflow/v2/training.py"
EX = "localflow/v2/curation/export.py"


def mark(mid, indent):
    """A statement that records the mutated branch ran."""
    return (" " * indent + "(__import__('os').environ.get('XM_MUT_REACH')"
            f" and open(__import__('os').environ['XM_MUT_REACH'], 'a')"
            f".write('{mid}\\n'))\n")


def mexpr(mid):
    """The same marker as an expression that evaluates true."""
    return ("((__import__('os').environ.get('XM_MUT_REACH') and"
            " open(__import__('os').environ['XM_MUT_REACH'], 'a')"
            f".write('{mid}\\n')) or True)")


FAMILY_LOOP = ("            for table in sorted(missing_tables &"
               " set(_CORE_DEPENDENTS)):\n"
               "                for probe in _CORE_DEPENDENTS[table]:\n")


def skip_family(mid, table):
    """The repair path treats ``table`` as recreatable again."""
    return [(ST, FAMILY_LOOP,
             "            for table in sorted(missing_tables &"
             " set(_CORE_DEPENDENTS)):\n"
             f"                if table == {table!r}:\n"
             + mark(mid, 20) + "                    continue\n"
             "                for probe in _CORE_DEPENDENTS[table]:\n")]


# (id, merged finding, title, edits, killers {suite: [cases]})
MUTATIONS = [
    ("XM-MU01", "MERGED-X01", "lost training_memberships recreated empty",
     skip_family("XM-MU01", "training_memberships"),
     {FAM: ["x01a_lost_memberships_never_return_exposed_family_to_holdout"]}),
    ("XM-MU02", "MERGED-X01", "lost profile_evidence recreated empty",
     skip_family("XM-MU02", "profile_evidence"),
     {FAM: ["x01b_lost_profile_evidence_never_keeps_dead_private_text"]}),
    ("XM-MU03", "MERGED-X01", "lost learning_vocabulary_deltas recreated",
     skip_family("XM-MU03", "learning_vocabulary_deltas"),
     {FAM: ["x01c_lost_deltas_never_let_undo_destroy_a_user_edit"]}),
    ("XM-MU04", "MERGED-X01", "lost usage_facts recreated empty",
     skip_family("XM-MU04", "usage_facts"),
     {FAM: ["x01d_lost_usage_facts_never_keep_deleted_usage_in_aggregates"]}),
    ("XM-MU05", "MERGED-X01", "lost learning_candidates recreated empty",
     skip_family("XM-MU05", "learning_candidates"),
     {FAM: ["x01e_lost_candidates_never_forget_a_permanent_rejection"]}),
    ("XM-MU06", "MERGED-X02", "Recovery copy bypasses the guard",
     [(APP, "        if not self._guarded_copy(self._last_failed[\"raw\"]):\n",
       mark("XM-MU06", 8)
       + "        if not (copy_text(self._last_failed[\"raw\"]) or True):\n")],
     {REM: ["x02_recovery_copy_never_replaces_a_pending_payload"]}),
    ("XM-MU07", "MERGED-X03", "update merges into a pre-op read",
     [(TS, "            current = _row_to_def(row)\n",
       "            current = _row_to_def(row)\n"
       "            if getattr(self, '_xm_pre', None) is not None:\n"
       + mark("XM-MU07", 16) + "                current = self._xm_pre\n"),
      (TS, "        status, out = self.store.submit(op)\n"
           "        if status == \"missing\":\n",
       "        self._xm_pre = self.definition(transform_id)\n"
       "        status, out = self.store.submit(op)\n"
       "        if status == \"missing\":\n")],
     {REM: ["x03_interleaved_updates_preserve_the_committed_definition"]}),
    ("XM-MU08", "MERGED-X04", "Update sends the whole stale form",
     [(HUB, "        diff = {k: v for k, v in form.items()\n"
            "                if v != editor[\"baseline\"].get(k)}\n"
            "        if not diff:\n"
            "            self.transforms_status.setStringValue_(\"no changes"
            " to save\")\n",
       mark("XM-MU08", 8) + "        diff = dict(form)\n"
       "        if not diff:\n"
       "            self.transforms_status.setStringValue_(\"no changes"
       " to save\")\n")],
     {REM: ["x04_stale_form_never_reverses_a_newer_opt_out",
            "x04_unknown_update_then_stale_refill_never_reenables_auto"]}),
    ("XM-MU09", "LOCAL-XM-01", "instruction view setEnabled_ again",
     [(HUB, "        self.tf_prompt.setEditable_(editable)\n",
       mark("XM-MU09", 8) + "        self.tf_prompt.setEnabled_(editable)\n")],
     {REM: ["local01_selected_transform_fills_its_own_instruction"]}),
    ("XM-MU10", "MERGED-X08", "Add mints a new id on every press",
     [(HUB, "            new_id = pending[\"id\"] if pending and"
            " pending[\"form\"] == form \\\n"
            "                else ids.new_id(\"tf\")\n",
       mark("XM-MU10", 12) + "            new_id = ids.new_id(\"tf\")\n")],
     {REM: ["x08_admitted_add_timeout_is_unknown_and_one_transform_results"]}),
    ("XM-MU11", "MERGED-X08", "an admitted timeout reads as not saved",
     [(HUB, "        if isinstance(e, TimeoutError):\n"
            "            self.transforms_status.setStringValue_(\n"
            "                \"outcome unknown: the store is busy and the"
            " change may\"\n",
       "        if isinstance(e, TimeoutError) and not " + mexpr("XM-MU11")
       + ":\n"
       "            self.transforms_status.setStringValue_(\n"
       "                \"outcome unknown: the store is busy and the"
       " change may\"\n")],
     {REM: ["x08_admitted_add_timeout_is_unknown_and_one_transform_results"]}),
    ("XM-MU12", "MERGED-X09", "Save to Scratchpad forgets the note id",
     [(APP, "        pending = self._tf_pending_saves.get(key)\n"
            "        note_id = pending or v2.ids.new_id(\"note\")\n",
       mark("XM-MU12", 8) + "        pending = None\n"
       "        note_id = v2.ids.new_id(\"note\")\n")],
     {REM: ["x09_admitted_save_timeout_then_retry_makes_one_note"]}),
    ("XM-MU13", "MERGED-X10", "unknown deletion reported as failed",
     [(APP, "                    outcome = (\"source_deletion_unknown\"\n"
            "                               if isinstance(e, TimeoutError)\n"
            "                               else \"move_failed_note_copied\")\n",
       mark("XM-MU13", 20)
       + "                    outcome = \"move_failed_note_copied\"\n")],
     {REM: ["x10_unknown_source_deletion_is_reported_and_retry_settles"]}),
    ("XM-MU14", "MERGED-X10", "a repeated transfer mints a new note id",
     [(APP, "        note_id = pending[\"note_id\"] if pending else"
            " v2.ids.new_id(\"note\")\n",
       mark("XM-MU14", 8) + "        note_id = v2.ids.new_id(\"note\")\n")],
     {REM: ["x10_unknown_copy_create_then_retry_makes_one_note"]}),
    ("XM-MU15", "MERGED-X06", "History trusts a superseded manifest",
     [(HQ, "        if superseded:\n            manifest = None\n",
       mark("XM-MU15", 8) + "        superseded = False\n"
       "        if superseded:\n            manifest = None\n")],
     {REM: ["x06_history_resolves_the_current_attempt_after_collection_off_retry"]}),
    ("XM-MU16", "MERGED-X06", "Teach trusts a superseded example",
     [(LN, "            if superseded:\n"
           "                # A retry ran without collection: the example"
           " describes\n",
       mark("XM-MU16", 12) + "            superseded = False\n"
       "            if superseded:\n"
       "                # A retry ran without collection: the example"
       " describes\n")],
     {REM: ["x06_history_resolves_the_current_attempt_after_collection_off_retry"]}),
    ("XM-MU17", "MERGED-X07", "each attempt speaks for its own capture",
     [(PR, "            best = per_job.get(job)\n",
       mark("XM-MU17", 12) + "            job = ex_id\n"
       "            best = per_job.get(job)\n")],
     {REM: ["x07_retries_never_manufacture_dictations_or_words",
            "x07_excluded_latest_attempt_never_falls_back_to_an_older_one"]}),
    ("XM-MU18", "MERGED-X05", "a lost normalized input reads as raw",
     [(EV, "        return {\"eligible\": False,\n"
           "                \"reason\": \"normalization_input_not_retained\"}\n",
       mark("XM-MU18", 8) + "        pass\n")],
     {REM: ["x05_failed_normalized_retention_is_never_a_complete_task"]}),
    ("XM-MU19", "MERGED-X05", "the producer always claims a change",
     [(TR, "\"failed_step\": step, \"input_changed\": result.text != src}",
       "\"failed_step\": step, \"input_changed\": " + mexpr("XM-MU19")
       + "}")],
     {REM: ["c_ledger_failure_with_unchanged_text_keeps_raw_input"]}),
    ("XM-MU20", "MERGED-X11", "technical terms use today's spelling",
     [(PR, "                    name = applied_names[ex].get(rid)\n",
       mark("XM-MU20", 20)
       + "                    name = conn.execute(\"SELECT canonical FROM"
         " vocabulary_entries WHERE entry_id=?\", (rid,)).fetchone()[0]\n")],
     {REM: ["x11_renamed_entry_never_relabels_historical_speech"]}),
    ("XM-MU21", "MERGED-X12", "the pane forgets the validation",
     [(HUB, "        validation = self._export_validation\n",
       mark("XM-MU21", 8) + "        validation = None\n")],
     {REM: ["x12_older_refresh_never_repaints_over_a_validate_result",
            "x12_validate_result_binds_to_its_destination_across_pane_switch"]}),
    ("XM-MU22", "MERGED-X13", "Validate runs on the UI thread",
     [(HUB, "        self._in_background(lambda:"
            " export_mod.validate_dataset(dest),\n"
            "                            done, key=\"validate\")\n",
       mark("XM-MU22", 8)
       + "        done(export_mod.validate_dataset(dest), None, True)\n")],
     {REM: ["x13_validate_never_runs_filesystem_work_on_the_ui_thread"]}),
    ("XM-MU23", "MERGED-X14", "no publication intent before the rename",
     [(EX, "            self._record(export_id, \"publishing\", task_views,"
           " manifest,\n"
           "                         destination, fingerprint,"
           " summary_counts)\n",
       mark("XM-MU23", 12) + "            pass\n")],
     {REM: ["x14_post_rename_crash_is_recognized_not_lost_or_relabeled"]}),
    ("XM-MU24", "MERGED-X14", "reconciliation invents a completion",
     [(EX, "            self._record(export_id, \"published_unconfirmed\","
           " views, None,\n",
       mark("XM-MU24", 12)
       + "            self._record(export_id, \"complete\", views, None,\n")],
     {REM: ["x14_post_rename_crash_is_recognized_not_lost_or_relabeled"]}),
    ("XM-MU25", "MERGED-X15", "Undo Approval drops its operation id",
     [(HUB, "            operation_id=self._op_id(\"undo\","
            " row[\"candidate_id\"]))\n",
       "            operation_id=None if " + mexpr("XM-MU25") + " else"
       " self._op_id(\"undo\", row[\"candidate_id\"]))\n")],
     {REM: ["x15_hub_undo_unknown_outcome_then_retry_is_one_undo"]}),
]


def mutants():
    return [{"id": mid, "finding": f, "name": title, "edits": edits,
             "killers": killers}
            for mid, f, title, edits, killers in MUTATIONS]


def export(dest: pathlib.Path) -> str:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    arch = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"],
                          capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=arch, check=True)
    (dest / ".venv").symlink_to(ROOT / ".venv")
    return head


def apply(root: pathlib.Path, m: dict) -> dict:
    texts, before, counts = {}, {}, []
    for rel, old, new in m["edits"]:
        if rel not in texts:
            texts[rel] = (root / rel).read_text()
            before[rel] = hashlib.sha256(texts[rel].encode()).hexdigest()
        n = texts[rel].count(old)
        counts.append(n)
        if n != 1:
            return {"applied": False, "match_counts": counts,
                    "reason": f"edit in {rel} did not match exactly once"}
        texts[rel] = texts[rel].replace(old, new)
    files = {}
    for rel, text in texts.items():
        (root / rel).write_text(text)
        after = hashlib.sha256(text.encode()).hexdigest()
        files[rel] = {"sha_before": before[rel][:16],
                      "sha_after": after[:16],
                      "changed": after != before[rel]}
    return {"applied": all(f["changed"] for f in files.values()),
            "match_counts": counts, "files": files}


def run_killers(root, killers, timeout=5400):
    reach = root / "reach.txt"
    reach.unlink(missing_ok=True)
    env = dict(os.environ, XM_MUT_REACH=str(reach))
    cases, details = {}, {}
    try:
        for suite, names in sorted(killers.items()):
            if not names:
                continue
            out = root / "killer_out.json"
            cmd = ([str(PY), ISOLATED, suite] if suite == REM
                   else [str(PY), suite])
            p = subprocess.run(cmd + ["--json", str(out), *sorted(names)],
                               cwd=root, capture_output=True, text=True,
                               timeout=timeout, env=env)
            if not out.exists():
                return {"error": f"no result from {suite}"
                                 f" (exit {p.returncode})",
                        "stderr": p.stderr[-600:]}
            d = json.loads(out.read_text())
            out.unlink()
            for r in d["results"]:
                cases[r["case"]] = r["status"]
                if r["status"] != "PASS":
                    details[r["case"]] = (r.get("detail") or "")[:300]
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    reached = sorted(set(reach.read_text().split())) if reach.exists() \
        else []
    return {"cases": cases, "details": details, "reached": reached}


def all_killers(todo):
    out = {}
    for m in todo:
        for suite, names in m["killers"].items():
            out.setdefault(suite, set()).update(names)
    return {s: sorted(n) for s, n in out.items()}


def verdict(control, mutant, m):
    if "error" in control or "error" in mutant:
        return "harness_error", "run error: " + str(
            mutant.get("error") or control.get("error"))
    names = [n for ns in m["killers"].values() for n in ns]
    cs, ms = control["cases"], mutant["cases"]
    if any(cs.get(k) != "PASS" for k in names):
        return "harness_error", "control not green: " + json.dumps(
            {k: cs.get(k) for k in names if cs.get(k) != "PASS"})
    if any(ms.get(k) not in ("PASS", "FAIL") for k in names):
        return "harness_error", "killer errored: " + json.dumps(
            {k: ms.get(k) for k in names if ms.get(k) not in
             ("PASS", "FAIL")})
    if m["id"] not in mutant.get("reached", []):
        return "not_reached", "the mutated branch never ran"
    if any(ms.get(k) == "FAIL" for k in names):
        return "killed", None
    return "survived", None


def check_edits(todo):
    bad = 0
    for m in todo:
        texts, counts = {}, []
        for rel, old, new in m["edits"]:
            text = texts.setdefault(rel, (ROOT / rel).read_text())
            counts.append(text.count(old))
            texts[rel] = text.replace(old, new)
        ok = bool(m["edits"]) and all(n == 1 for n in counts)
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {m['id']} {counts}")
    return 1 if bad else 0


def run_one(base, control, m):
    root = base.parent / m["id"]
    shutil.copytree(base, root, symlinks=True)
    proof = apply(root, m)
    rec = {"mutation_id": m["id"], "finding": m["finding"],
           "name": m["name"], "files": sorted({e[0] for e in m["edits"]}),
           "proof": proof, "killers": m["killers"]}
    if not proof["applied"]:
        rec.update(outcome="harness_error",
                   reason=proof.get("reason", "mutation not applied"))
    else:
        t0 = time.monotonic()
        mut = run_killers(root, m["killers"])
        rec["seconds"] = round(time.monotonic() - t0, 1)
        rec["mutant"] = mut.get("cases", mut)
        rec["branch_reached"] = m["id"] in mut.get("reached", [])
        rec["failed_killers"] = sorted(
            k for k, s in mut.get("cases", {}).items() if s == "FAIL")
        rec["mutant_details"] = mut.get("details")
        rec["outcome"], rec["reason"] = verdict(control, mut, m)
    shutil.rmtree(root, ignore_errors=True)
    print(f"{rec['outcome']:14} {m['id']} {m['name'][:48]}"
          f" {rec.get('reason') or ''}", flush=True)
    return rec


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    todo = [m for m in mutants() if not only or m["id"] in only]
    if "--check-edits" in argv:
        return check_edits(todo)
    work = pathlib.Path(tempfile.mkdtemp(prefix="xm-mut-"))
    results = []
    try:
        base = work / "control"
        base.mkdir()
        head = export(base)
        control = run_killers(base, all_killers(todo), timeout=10800)
        if control.get("reached"):
            control = {"error": "control wrote reach markers"
                                f" {control['reached']}"}
        not_green = {k: s for k, s in control.get("cases", {}).items()
                     if s != "PASS"}
        print(f"control: {len(control.get('cases', {}))} killers,"
              f" not green {not_green}", flush=True)
        for m in todo:
            results.append(run_one(base, control, m))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    tally = {}
    for r in results:
        tally[r["outcome"]] = tally.get(r["outcome"], 0) + 1
    print(json.dumps(tally))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            "tool": "scripts/v2/xm_mutation_check.py", "code_sha": head,
            "killer_rule": "the fail-first regressions/controls of"
                           " tests/v2/crossmilestone/ named per mutation;"
                           " a kill needs the reach marker AND a failed"
                           " killer",
            "control": control, "summary": tally, "results": results},
            indent=1) + "\n")
    return 0 if all(r["outcome"] == "killed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
