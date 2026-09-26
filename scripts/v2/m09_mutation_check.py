"""The M09 audit corpus's implementation mutations M09-MUT01..24, run
for real (MUT25..28 attack the benchmark and are run by
``m09_benchmark_mutation_check.py``).

For each mutation: export the tracked tree at HEAD into a disposable
directory (``git archive``), apply exactly that semantic weakening to
the copied production module(s) — every edit must match its text
exactly once, or, declared, every occurrence — prove the patch applied
(each file's hash changed) and that the killing run imported
``localflow`` from THAT copy, then run the corpus's killing cases there
through ``tests/v2/ui/m09_corpus_runner.py --only``. Outcomes:

- ``killed``        — the unmutated control passed (PASS, or NARROWED:
                      its automatable part passed) every killer, and the
                      mutant made at least one FAIL;
- ``survived``      — control green, the mutant still passes them all;
- ``harness_error`` — anything else: an edit that did not match, an
                      import from the wrong tree, a control that is not
                      green, an ERROR/NOT_RUN in a killer, a timeout.
                      Never counted as a kill.

Everything runs under ``tests/v2/context/run_isolated.py`` (no real
Accessibility, event posting or general pasteboard).

    .venv/bin/python scripts/v2/m09_mutation_check.py --json OUT \
        [--only M09-MUT01,...]
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
RUNNER = "tests/v2/ui/m09_corpus_runner.py"
ISOLATED = "tests/v2/context/run_isolated.py"

STATE = "localflow/v2/ui/state.py"
HUB = "localflow/v2/ui/hub.py"
APP = "localflow/app.py"
HQ = "localflow/v2/history_queries.py"
TD = "localflow/v2/training_data.py"
EV = "localflow/v2/event_view.py"
DIAG = "localflow/v2/diagnostics.py"
INS = "localflow/v2/insertion/service.py"

GREEN = ("PASS", "NARROWED")

# Each edit is (file, old, new); "replace_all" edits carry a 4th True.
MUTANTS = [
    {"id": "M09-MUT01", "name": "Remove the generation comparison",
     "edits": [(STATE,
                "                if self._gens.get(req.key) != req.gen:\n"
                "                    return False\n", "")],
     "killers": ["M09-C001", "M09-C021", "M09-C022"]},
    {"id": "M09-MUT02",
     "name": "Move generation check outside the atomic publication"
             " boundary",
     "edits": [(STATE,
                "        with self._lock:\n"
                "            if self._closed:\n"
                "                return False\n"
                "            if req is not None:\n"
                "                if self._gens.get(req.key) != req.gen:\n"
                "                    return False\n",
                "        if req is not None and \\\n"
                "                self._gens.get(req.key) != req.gen:\n"
                "            return False\n"
                "        with self._lock:\n"
                "            if self._closed:\n"
                "                return False\n"
                "            if req is not None:\n")],
     "killers": ["M09-C023"]},
    {"id": "M09-MUT03",
     "name": "Publish stale detail after a new selected ID (History:"
             " selection keeps the old detail, which renders and acts)",
     "edits": [(STATE,
                "                view.update(selected_kind=kind,"
                " selected_id=row_id,\n"
                "                            detail=None, detail_key=None,\n"
                "                            detail_error=None)\n",
                "                view.update(selected_kind=kind,"
                " selected_id=row_id)\n"),
               (HUB,
                "        if rendered is None or rendered is not"
                " view.get(\"detail\") \\\n"
                "                or view.get(\"detail_key\") != key:\n"
                "            self._history_note(",
                "        if rendered is None:\n"
                "            self._history_note("),
               (HUB,
                "        self._rendered[\"history_detail\"] = detail \\\n"
                "            if detail is not None and"
                " view.get(\"detail_key\") == key \\\n"
                "            else None\n",
                "        self._rendered[\"history_detail\"] = detail\n")],
     "killers": ["M09-C002", "M09-C024"]},
    {"id": "M09-MUT04", "name": "Dispatch refresh inline from a query worker",
     "edits": [(HUB,
                "        AppHelper.callAfter(self._refresh,"
                " state.selected_view)\n",
                "        self._refresh(state.selected_view)\n")],
     "killers": ["M09-C020", "M09-C118", "M09-C122"]},
    {"id": "M09-MUT05",
     "name": "Replace per-example listening identity with one boolean",
     "edits": [(HUB,
                "        listened = (self.state.views[\"models\"]"
                ".get(\"listened_for\") == ex)\n",
                "        listened = bool(self.state.views[\"models\"]"
                ".get(\"listened_for\"))\n")],
     "killers": ["M09-C007", "M09-C064"]},
    {"id": "M09-MUT06", "name": "Grant listen token before sound.play succeeds",
     "edits": [(HUB,
                "        out = self.replay.play_artifact(self.spec[\"store\"],\n"
                "                                        audio.get("
                "\"artifact_id\"))\n"
                "        if out.get(\"status\") == \"playing\":\n",
                "        self.state.views[\"models\"][\"listened_for\"] = \\\n"
                "            ctx[\"example_id\"]\n"
                "        out = self.replay.play_artifact(self.spec[\"store\"],\n"
                "                                        audio.get("
                "\"artifact_id\"))\n"
                "        if out.get(\"status\") == \"playing\":\n")],
     "killers": ["M09-C008"]},
    {"id": "M09-MUT07", "name": "Allow Retry despite active retry claim",
     "edits": [(APP,
                "        if any(j.get(\"job_id\") == job_id for j in"
                " self._active_jobs):\n"
                "            return {\"outcome\": \"already_retrying\"}\n", ""),
               (APP,
                "        if not self._claim_job(job_id):\n"
                "            return {\"outcome\": \"already_retrying\"}\n",
                "        self._claim_job(job_id)\n")],
     "killers": ["M09-C009", "M09-C068"]},
    {"id": "M09-MUT08", "name": "Omit V2 job ID from actual History Paste Again",
     "edits": [(HUB,
                "        out = self.coordinator.hubPasteText(text,"
                " job_id=ctx.get(\"job_id\")) \\\n",
                "        out = self.coordinator.hubPasteText(text,"
                " job_id=None) \\\n")],
     "killers": ["M09-C069"]},
    {"id": "M09-MUT09", "name": "Fabricate a job ID for jobless legacy row",
     "edits": [(HQ,
                "            return {\"kind\": \"legacy_db\","
                " \"id\": f\"legacy-db:{rid}\",\n",
                "            return {\"kind\": \"legacy_db\","
                " \"id\": f\"legacy-db:{rid}\",\n"
                "                    \"job_id\": f\"job-{int(rid):032x}\",\n")],
     "killers": ["M09-C070"]},
    {"id": "M09-MUT10",
     "name": "Flatten missing lineage stage to preceding text",
     "edits": [(HQ,
                "                {\"stage\": \"normalized\","
                " \"label\": \"Normalized\",\n"
                "                 \"artifact\": normalized},\n",
                "                {\"stage\": \"normalized\","
                " \"label\": \"Normalized\",\n"
                "                 \"artifact\": normalized or raw},\n"),
               (HQ,
                "                 \"artifact\": transformed,"
                " \"decision\": decision,\n",
                "                 \"artifact\": transformed or applied,"
                " \"decision\": decision,\n")],
     "killers": ["M09-C054", "M09-C059"]},
    {"id": "M09-MUT11",
     "name": "Restore quarantined/expired evidence after exclude toggle",
     "edits": [(TD,
                "            if current in (\"deleted\", \"expired\","
                " \"quarantined_sensitive\"):\n",
                "            if current in (\"deleted\",):\n")],
     "killers": ["M09-C083", "M09-C084"]},
    {"id": "M09-MUT12",
     "name": "Make annotation state update include excluded as live",
     "edits": [(TD,
                "NON_REVIEWABLE_STATES = (\"deleted\", \"expired\","
                " \"quarantined_sensitive\",\n"
                "                         \"excluded\")\n",
                "NON_REVIEWABLE_STATES = (\"deleted\", \"expired\","
                " \"quarantined_sensitive\")\n"),
               (TD, "('deleted','expired','quarantined_sensitive','excluded')",
                "('deleted','expired','quarantined_sensitive')", True)],
     "killers": ["M09-C086", "M09-C087"]},
    {"id": "M09-MUT13",
     "name": "Remove reviewed artifact/hash comparison from span save",
     "edits": [(TD,
                "            if expected_artifact_id is not None and \\\n"
                "                    stage_aid != expected_artifact_id:\n",
                "            if False:\n"),
               (TD,
                "            if expected_sha256 is not None and \\\n"
                "                    ids.sha256_text(text) !="
                " expected_sha256:\n",
                "            if False:\n")],
     "killers": ["M09-C014", "M09-C076", "M09-C079"]},
    {"id": "M09-MUT14",
     "name": "Revoke review annotation lease during user unpin",
     "edits": [(TD,
                "                    \" artifact_id FROM artifacts WHERE"
                " job_id=? AND role\"\n"
                "                    f\" NOT IN ({marks}))\",\n"
                "                    (now, job_id, *_ANNOTATION_ROLES))\n",
                "                    \" artifact_id FROM artifacts WHERE"
                " job_id=?)\",\n"
                "                    (now, job_id))\n")],
     "killers": ["M09-C015", "M09-C081"]},
    {"id": "M09-MUT15", "name": "Export all event fields except detail",
     "edits": [(EV,
                "        check = REDACTION_ALLOWLIST.get(key)\n"
                "        if check is None or not check(value) or"
                " _secret_like(value):\n",
                "        if key == \"detail\":\n")],
     "killers": ["M09-C100", "M09-C101"]},
    {"id": "M09-MUT16", "name": "Perform History service query on UI thread",
     "edits": [(STATE,
                "        self._executor.submit(req, self._before_run)\n"
                "        return req\n",
                "        self._before_run(req)\n"
                "        fn(req)\n"
                "        return req\n")],
     "killers": ["M09-C018", "M09-C122"]},
    {"id": "M09-MUT17", "name": "Ignore active insertion focus guard",
     "edits": [(APP,
                "        return self.state == STATE_RECORDING or"
                " self._injecting or working\n",
                "        return self.state == STATE_RECORDING or"
                " self._injecting\n")],
     "killers": ["M09-C005", "M09-C006"]},
    {"id": "M09-MUT18",
     "name": "Omit idle notification after no-op reconciliation (every"
             " idle notification)",
     "edits": [(INS,
                "                    listeners = (list(self._idle_listeners)\n"
                "                                 if self._outstanding == 0"
                " else [])\n",
                "                    listeners = []\n")],
     "killers": ["M09-C034", "M09-C035"]},
    {"id": "M09-MUT19",
     "name": "Skip deletion epoch/token check before late publication",
     "edits": [(STATE,
                "                if req.epoch is not None and req.epoch !="
                " self._epoch:\n"
                "                    self._spawn(req.key, req.fn,"
                " **req.inputs)\n"
                "                    return False\n", ""),
               (STATE,
                "        revoked = self._revoked_jobs\n"
                "        if not revoked:\n",
                "        revoked = None\n"
                "        if not revoked:\n")],
     "killers": ["M09-C011", "M09-C090", "M09-C128"]},
    {"id": "M09-MUT20",
     "name": "Resolve action from current row index instead of rendered"
             " stable ID",
     "edits": [(HUB,
                "        return self._rendered_rows.get(name) or []"
                " if name else []\n",
                "        if not name:\n"
                "            return []\n"
                "        view, key = self._TABLE_ROWS[name]\n"
                "        return list(((self.state.views[view].get(\"data\")"
                " or {})\n"
                "                     .get(key)) or [])\n"),
               (HUB,
                "        rows = self._rendered_rows.get(\"review_queue\")\n"
                "        if rows is None or current is not"
                " self._rendered.get(\n"
                "                \"review_queue_src\"):\n",
                "        rows = current\n"
                "        if rows is None:\n")],
     "killers": ["M09-C025", "M09-C108"]},
    {"id": "M09-MUT21",
     "name": "Choose first same-role artifact across attempts",
     "edits": [(HQ,
                "        if manifest is not None:\n"
                "            arts = manifest.get(\"artifact_ids\") or {}\n",
                "        if False:\n"
                "            arts = manifest.get(\"artifact_ids\") or {}\n"),
               (HQ,
                "                if current is not None and role !="
                " \"original_audio\" \\\n"
                "                        and e[\"_attempt\"] != current:\n"
                "                    continue\n", ""),
               (HQ,
                "                chosen[role] = e  # newest within the"
                " chosen attempt\n",
                "                chosen.setdefault(role, e)\n")],
     "killers": ["M09-C055", "M09-C056"]},
    {"id": "M09-MUT22", "name": "Sort merged history by date plus ID only",
     "edits": [(HQ,
                "        dated.sort(key=lambda r: (-r[\"_t\"],"
                " _KIND_RANK[r[\"kind\"]],\n"
                "                                  str(r[\"id\"])))\n",
                "        dated.sort(key=lambda r: (r[\"date\"],"
                " str(r[\"id\"])), reverse=True)\n")],
     "killers": ["M09-C039", "M09-C040", "M09-C044"]},
    {"id": "M09-MUT23", "name": "Use filename ordering for diagnostics",
     "edits": [(DIAG,
                "    return select_events(order_records(recs, warn=False),"
                " job_id=job_id,\n",
                "    return select_events(recs, job_id=job_id,\n"),
               (DIAG,
                "    rows = [r for r in order_records(list(events),"
                " warn=False)\n",
                "    rows = [r for r in list(events)\n")],
     "killers": ["M09-C094", "M09-C095", "M09-C099"]},
    {"id": "M09-MUT24",
     "name": "Unconditionally navigate to Review on Mine completion",
     "edits": [(HUB,
                "            if on_review:\n"
                "                self.state.reload_training()\n"
                "            else:\n"
                "                self._action_notes[\"review\"] = \\\n"
                "                    \"mining finished — the review queue"
                " was updated\"\n",
                "            self.state.select_training_tab(\"review\")\n"
                "            self.state.reload_training()\n")],
     "killers": ["M09-C017", "M09-C105"]},
]


# Equivalence probes (not corpus mutations; reported apart from the
# tally). MUT05 can survive because the verbatim gate is held twice:
# the per-example comparison AND the reset of ``listened_for`` on every
# Training selection change. Each probe removes one or both defenses;
# ``expect`` is what the design predicts.
_RESET = (STATE,
          "            if view.get(\"selected_id\") != example_id:\n"
          "                view[\"listened_for\"] = None\n",
          "            if view.get(\"selected_id\") != example_id:\n")
PROBES = [
    {"id": "M09-MUT05-EQ-both", "for": "M09-MUT05", "expect": "killed",
     "name": "Boolean listening AND no reset on selection change",
     "edits": [MUTANTS[4]["edits"][0], _RESET], "killers": ["M09-C007"]},
    {"id": "M09-MUT05-EQ-reset", "for": "M09-MUT05", "expect": "survived",
     "name": "No reset on selection change (per-example comparison kept)",
     "edits": [_RESET], "killers": ["M09-C007"]},
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
    texts, before, counts = {}, {}, []
    for edit in m["edits"]:
        rel, old, new = edit[:3]
        replace_all = len(edit) > 3 and edit[3]
        if rel not in texts:
            texts[rel] = (root / rel).read_text()
            before[rel] = hashlib.sha256(texts[rel].encode()).hexdigest()
        n = texts[rel].count(old)
        counts.append(n)
        if n == 0 or (n > 1 and not replace_all):
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


def run_killers(root, killers, timeout=900):
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
            "cases": {cid: r["status"] for cid, r in d["cases"].items()},
            "details": {cid: (r.get("detail") or r.get("where") or "")[:300]
                        for cid, r in d["cases"].items()
                        if r["status"] not in GREEN}}


def verdict(root, control, mutant, killers):
    if "error" in control or "error" in mutant:
        return "harness_error", "run error"
    if mutant.get("imported_from") != root.name:
        return "harness_error", ("imported from another tree: "
                                 f"{mutant.get('imported_from')}")
    cs, ms = control["cases"], mutant["cases"]
    if any(cs.get(k) not in GREEN for k in killers):
        return "harness_error", f"control not green: {cs}"
    if any(ms.get(k) not in GREEN + ("FAIL",) for k in killers):
        return "harness_error", f"killer not reached: {ms}"
    if any(ms.get(k) == "FAIL" for k in killers):
        return "killed", None
    return "survived", None


def check_edits(todo):
    """Read-only: every mutant's edits match the checked-out sources."""
    bad = 0
    for m in todo:
        texts, counts = {}, []
        for edit in m["edits"]:
            rel, old, new = edit[:3]
            text = texts.setdefault(rel, (ROOT / rel).read_text())
            counts.append(text.count(old))
            texts[rel] = text.replace(old, new)
        ok = all(n == 1 or (n > 1 and len(e) > 3 and e[3])
                 for n, e in zip(counts, m["edits"]))
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {m['id']} {counts}")
    return 1 if bad else 0


def run_one(base, control, m):
    root = base.parent / m["id"]
    shutil.copytree(base, root, symlinks=True)
    proof = apply(root, m)
    rec = {"mutation_id": m["id"], "name": m["name"],
           "files": sorted({e[0] for e in m["edits"]}),
           "proof": proof, "killers": m["killers"]}
    if not proof["applied"]:
        rec.update(outcome="harness_error",
                   reason=proof.get("reason", "mutation not applied"))
    else:
        mut = run_killers(root, m["killers"])
        rec["control"] = {k: control.get("cases", {}).get(k)
                          for k in m["killers"]}
        rec["mutant"] = mut.get("cases", mut)
        rec["mutant_details"] = mut.get("details")
        rec["imported_from"] = mut.get("imported_from")
        rec["outcome"], rec["reason"] = verdict(root, control, mut,
                                                m["killers"])
    shutil.rmtree(root, ignore_errors=True)
    print(f"{rec['outcome']:14} {m['id']} {m['name']}"
          f" {rec.get('reason') or ''} {rec.get('mutant', '')}", flush=True)
    return rec


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    todo = [m for m in MUTANTS if not only or m["id"] in only]
    probes = [p for p in PROBES if not only or p["id"] in only
              or p["for"] in only]
    if "--check-edits" in argv:
        return check_edits(todo + probes)
    work = pathlib.Path(tempfile.mkdtemp(prefix="m09-mut-"))
    results, probe_results = [], []
    try:
        base = work / "control"
        base.mkdir()
        head = export(base)
        killers = sorted({k for m in todo + probes for k in m["killers"]})
        t0 = time.monotonic()
        control = run_killers(base, killers, timeout=1800)
        if control.get("imported_from") not in (None, base.name):
            control = {"error": "control imported from another tree"}
        print(f"control: {control.get('cases', control)}"
              f" ({time.monotonic() - t0:.0f}s)", flush=True)
        for m in todo:
            results.append(run_one(base, control, m))
        for p in probes:
            rec = run_one(base, control, p)
            rec.update({"for": p["for"], "expect": p["expect"],
                        "as_expected": rec["outcome"] == p["expect"]})
            probe_results.append(rec)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # A survivor is annotated equivalent only when every probe for it
    # ran and behaved as the design predicts; it is never a kill.
    for r in results:
        mine = [p for p in probe_results if p["for"] == r["mutation_id"]]
        if r["outcome"] == "survived" and mine:
            r["equivalent_by_probe"] = all(p["as_expected"] for p in mine)
    tally = {}
    for r in results:
        tally[r["outcome"]] = tally.get(r["outcome"], 0) + 1
    tally["survived_equivalent_by_probe"] = sum(
        1 for r in results if r.get("equivalent_by_probe"))
    print(json.dumps(tally))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            "tool": "scripts/v2/m09_mutation_check.py",
            "runner": RUNNER, "code_sha": head, "control": control,
            "summary": tally, "results": results,
            "equivalence_probes": probe_results}, indent=1) + "\n")
    unexplained = [r for r in results if r["outcome"] != "killed"
                   and not r.get("equivalent_by_probe")]
    return 0 if not unexplained else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
