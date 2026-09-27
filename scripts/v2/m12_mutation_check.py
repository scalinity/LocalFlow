"""The M12 audit corpus's 22 mutations LF-M12-MUT01..22, run for real.

For each mutation: export the tracked tree at HEAD into a disposable
directory (``git archive``), apply exactly that semantic weakening to
the copied module(s) — every edit must match its text exactly once —
prove the patch applied (each file's hash changed) and that the killing
run imported ``localflow`` from THAT copy, then run the killers there.

Killers are not chosen per mutant: they are every corpus case that
shares a finding with the mutation (``finding_ids`` in the frozen
corpus), minus the native cases (graded on the separately produced
native record: NOT_RUN in a copy). Where the mutation's own kill oracle
names a check that no finding-linked case carries, that check is added
explicitly (``EXTRA``: MUT05's "next typed input builds on the wrong
revision" is C004/C037; MUT19's owned normal-loop autosave firing is
the regression r10). Outcomes:

- ``killed``        — the unmutated control is PASS on every killer and
                      the mutant makes at least one FAIL (an independent
                      semantic assertion, after its branch ran);
- ``survived``      — control green, the mutant still passes them all;
- ``harness_error`` — anything else: an edit that did not match, an
                      import from the wrong tree, a control that is not
                      green, an ERROR/NOT_RUN in a killer, a timeout.
                      Never counted as a kill.

Everything runs under ``tests/v2/context/run_isolated.py``.

    .venv/bin/python scripts/v2/m12_mutation_check.py --json OUT \
        [--only LF-M12-MUT01,...] [--check-edits]
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
RUNNER = "tests/v2/notes/m12_corpus_runner.py"
REGRESSIONS = "tests/v2/notes/test_m12_remediation.py"
ISOLATED = "tests/v2/context/run_isolated.py"
CORPUS = ROOT / "tests" / "v2" / "notes" / "m12_audit_corpus.json"

NOTES = "localflow/v2/notes.py"
STORE = "localflow/v2/store.py"
EXPORT = "localflow/v2/note_export.py"
SCRATCH = "localflow/v2/ui/scratchpad.py"
HUB = "localflow/v2/ui/hub.py"
APP = "localflow/app.py"
TRAIN = "localflow/v2/training.py"
BENCH = "scripts/v2/benchmark_m12.py"

EXTRA = {"LF-M12-MUT05": ["LF-M12-C004", "LF-M12-C037"],
         "LF-M12-MUT19": ["regression:r10_timer_fires_in_the_default_run_loop"]}

# Each edit is (file, old, new).
EDITS = {
    "LF-M12-MUT01": [(SCRATCH,
                      "        kind, rng = self.selection()\n"
                      "        return None if rng is None else rng[0]\n",
                      "        return int(self.text.selectedRange().location)\n")],
    "LF-M12-MUT02": [(NOTES,
                      "    if dest.get(\"note_id\") != open_note_id:\n"
                      "        return False, \"note_changed\"\n", ""),
                     (HUB,
                      "        if editor.note_id != target.get(\"note_id\"):\n"
                      "            return refuse(\"note_changed_during_dictation\")\n",
                      "")],
    "LF-M12-MUT03": [(NOTES,
                      "    s, e = (int(x) for x in dest[\"range\"])\n"
                      "    if content[s:e] != dest.get(\"text\"):\n"
                      "        return False, \"note_range_changed\"\n"
                      "    return True, None\n",
                      "    return True, None\n")],
    "LF-M12-MUT04": [(HUB,
                      "        rng = tuple(dest[\"range\"])\n"
                      "        job = result.job\n",
                      "        rng = (0, 0) if dest.get(\"scope\") == \"whole\""
                      " else tuple(dest[\"range\"])\n"
                      "        job = result.job\n")],
    "LF-M12-MUT05": [(HUB,
                      "            rebind = self.editor.note_id != wanted or (\n"
                      "                model is not None and not model.dirty\n"
                      "                and model.revision_id != current_rev)\n",
                      "            rebind = self.editor.note_id != wanted\n")],
    "LF-M12-MUT06": [(NOTES,
                      "            while self._flushing:\n"
                      "                if deadline is None:\n",
                      "            if self._flushing:\n"
                      "                return {\"outcome\": \"already_flushing\","
                      " \"generation\": target}\n"
                      "            while False:\n"
                      "                if deadline is None:\n")],
    "LF-M12-MUT07": [(NOTES,
                      "            if note is None:\n"
                      "                return {\"_missing\": True}   # nothing written\n",
                      "            if note is None:\n"
                      "                note = (None,)\n")],
    "LF-M12-MUT08": [(NOTES,
                      "            intents, refused = self._purge_intents_for(db, [row[0]],\n",
                      "            unlink_managed_file(self.attachments_dir, row[0] or \"\")\n"
                      "            intents, refused = self._purge_intents_for(db, [row[0]],\n")],
    "LF-M12-MUT09": [(STORE,
                      "    if not managed_name_ok(name):\n"
                      "        return None\n",
                      "    try:\n"
                      "        return (pathlib.Path(directory) / name).read_bytes()\n"
                      "    except OSError:\n"
                      "        return None\n"),
                     (STORE,
                      "    if not managed_name_ok(name):\n"
                      "        return PATH_REFUSED\n",
                      "    try:\n"
                      "        (pathlib.Path(directory) / name).unlink()\n"
                      "    except OSError:\n"
                      "        pass\n"
                      "    return None\n"),
                     (NOTES,
                      "            if not managed_name_ok(p):\n"
                      "                refused += 1\n"
                      "                continue\n", "")],
    "LF-M12-MUT10": [(NOTES,
                      "                    \"edited_spans\": edited,\n"
                      "                    \"created_at_utc\": now}\n",
                      "                    \"edited_spans\": edited, \"title\": title,\n"
                      "                    \"created_at_utc\": now}\n"),
                     (TRAIN,
                      "                \"evidence_status\": \"reliable_target_observation\",\n"
                      "            }\n",
                      "                \"evidence_status\": \"reliable_target_observation\",\n"
                      "                \"title\": event.get(\"title\"),\n"
                      "            }\n")],
    "LF-M12-MUT11": [(NOTES,
                      "            title = title_override if title_override is not None \\\n",
                      "            db.execute(\"INSERT INTO usage_facts(fact_id, kind, job_id,"
                      " activity_at_utc, day_local, reporting_timezone,"
                      " algorithm_version, insertion_outcome, final_words,"
                      " created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)\","
                      " (ids.new_id(\"fact\"), \"dictation\", revision_id, now,"
                      " now[:10], \"UTC\", 1, \"confirmed\", word_count(content),"
                      " now))\n"
                      "            title = title_override if title_override is not None \\\n")],
    "LF-M12-MUT12": [(NOTES,
                      "                        base = parent_content if preimage is None \\\n"
                      "                            else preimage\n"
                      "                        if base == parent_content:\n"
                      "                            span = arrival_span(\n"
                      "                                content, inserted_at_chars or 0,\n"
                      "                                len(inserted_text))\n"
                      "                            if span is not None:\n"
                      "                                insert_span(spans, span[0],\n"
                      "                                            span[1] - span[0], origin,\n"
                      "                                            job_id=source_job_id)\n"
                      "                        else:\n"
                      "                            meta[\"attribution\"] = \"abstained_parent_moved\"\n",
                      "                        start_word = len(\n"
                      "                            parent_content[:inserted_at_chars or 0].split())\n"
                      "                        insert_span(spans, start_word,\n"
                      "                                    word_count(inserted_text), origin,\n"
                      "                                    job_id=source_job_id)\n"),
                     (NOTES,
                      "                    if arrival.preimage != saved:\n"
                      "                        self._commit_typed(store, arrival.preimage,\n"
                      "                                           arrival.generation - 1, trigger)\n",
                      "")],
    "LF-M12-MUT13": [(NOTES,
                      "            if note is None:\n"
                      "                return {\"_missing\": True}   # nothing written\n",
                      "            if note is None:\n"
                      "                db.execute(\"INSERT INTO notes(note_id, title, pinned,"
                      " current_revision_id, dirty_at_utc, created_at_utc,"
                      " updated_at_utc) VALUES(?,'',0,NULL,NULL,?,?)\","
                      " (note_id, now, now))\n"
                      "                note = (None,)\n")],
    "LF-M12-MUT14": [(EXPORT,
                      "    def fail(reason):\n"
                      "        for p in created:\n",
                      "    def fail(reason):\n"
                      "        try:\n"
                      "            os.unlink(path)\n"
                      "        except OSError:\n"
                      "            pass\n"
                      "        for p in created:\n")],
    "LF-M12-MUT15": [(APP,
                      "                        self._job_state(job_id, \"insertion_posted\")\n"
                      "                    self._note_deliveries[arrival.op_id] = (job, ctx, text,\n",
                      "                        self._job_state(job_id, \"insertion_posted\")\n"
                      "                        self._job_state(job_id, \"insertion_confirmed\",\n"
                      "                                        reason=\"scratchpad_note\")\n"
                      "                    self._note_deliveries[arrival.op_id] = (job, ctx, text,\n")],
    "LF-M12-MUT16": [(NOTES,
                      "            db.execute(\n"
                      "                \"UPDATE note_evidence_links SET closed_utc=?,\"\n"
                      "                \" close_reason='note_deleted' WHERE note_id=? AND\"\n"
                      "                \" closed_utc IS NULL\", (now, note_id))\n", "")],
    "LF-M12-MUT17": [(BENCH,
                      "            pause(\"note_open_10k\")\n"
                      "            return ns.open_note(big)\n",
                      "            pause(\"note_open_10k\")\n"
                      "            return None\n")],
    "LF-M12-MUT18": [(BENCH,
                      "            if noop == \"search\":\n"
                      "                return []\n"
                      "            return ns2.search(MATCH_TOKEN)\n",
                      "            return []\n")],
    "LF-M12-MUT19": [(SCRATCH,
                      "            self.timer, NSRunLoopCommonModes)\n",
                      "            self.timer, \"default\")\n")],
    "LF-M12-MUT20": [(TRAIN,
                      "                if any(o.get(\"note_revision_id\") ==\n"
                      "                       observation[\"note_revision_id\"]\n"
                      "                       and o.get(\"kind\") == observation[\"kind\"]\n"
                      "                       for o in notes):\n"
                      "                    continue\n", "")],
    "LF-M12-MUT21": [(NOTES,
                      "                        arrival.attempts += 1\n",
                      "                        arrival.attempts += 1\n"
                      "                        self.arrivals = [arrival]\n")],
    "LF-M12-MUT22": [(NOTES,
                      "    for v in (location, length):\n"
                      "        if isinstance(v, bool) or not isinstance(v, int):\n",
                      "    def to_cp(units):\n"
                      "        seen = 0\n"
                      "        for i, ch in enumerate(text):\n"
                      "            if seen >= units:\n"
                      "                return i\n"
                      "            seen += 2 if ord(ch) > 0xFFFF else 1\n"
                      "        return len(text)\n"
                      "    start = to_cp(int(location))\n"
                      "    return start, to_cp(int(location) + int(length))\n"
                      "    for v in (location, length):\n"
                      "        if isinstance(v, bool) or not isinstance(v, int):\n")],
}


def mutants():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    out = []
    for m in corpus["mutation_definitions"]:
        found = set(m["finding_ids"])
        killers = sorted(c["id"] for c in corpus["cases"]
                         if found & set(c["finding_ids"])
                         and c["kind"] != "native")
        killers += [k for k in EXTRA.get(m["id"], []) if k not in killers]
        out.append({"id": m["id"], "name": m["name"],
                    "findings": m["finding_ids"],
                    "kill_oracle": m["semantic_kill_oracle"],
                    "edits": EDITS.get(m["id"], []), "killers": killers})
    return out


def export(dest: pathlib.Path) -> str:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    arch = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"],
                          capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=arch, check=True)
    (dest / ".venv").symlink_to(ROOT / ".venv")
    return head


def apply(root: pathlib.Path, m: dict) -> dict:
    if not m["edits"]:
        return {"applied": False, "reason": "no edit defined"}
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


def run_killers(root, killers, timeout=1800):
    cases, details, imported = {}, {}, set()
    corpus_ids = [k for k in killers if not k.startswith("regression:")]
    regs = [k.split(":", 1)[1] for k in killers
            if k.startswith("regression:")]
    if corpus_ids:
        out = root / "mut_result.json"
        cmd = [str(PY), ISOLATED, RUNNER, "--quiet", "--only",
               ",".join(corpus_ids), "--json", str(out)]
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
        imported.add(d.get("localflow_imported_from_root"))
        for r in d["results"]:
            cases[r["id"]] = r["status"]
            if r["status"] != "PASS":
                details[r["id"]] = (r.get("note") or "")[:300]
    if regs:
        out = root / "mut_regressions.json"
        cmd = [str(PY), ISOLATED, REGRESSIONS, "-k", ",".join(regs),
               "--json", str(out)]
        try:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}
        if not out.exists():
            return {"error": f"no regression result (exit {p.returncode})",
                    "stderr": p.stderr[-400:]}
        d = json.loads(out.read_text())
        out.unlink()
        imported.add(d.get("localflow_imported_from_root"))
        for r in d["results"]:
            key = f"regression:{r['id']}"
            cases[key] = r["status"]
            if r["status"] != "PASS":
                details[key] = (r.get("note") or "")[:300]
    return {"imported_from": imported.pop() if len(imported) == 1
            else sorted(map(str, imported)),
            "cases": cases, "details": details}


def verdict(root, control, mutant, killers):
    if "error" in control or "error" in mutant:
        return "harness_error", "run error"
    if mutant.get("imported_from") != root.name:
        return "harness_error", ("imported from another tree: "
                                 f"{mutant.get('imported_from')}")
    cs, ms = control["cases"], mutant["cases"]
    if any(cs.get(k) != "PASS" for k in killers):
        return "harness_error", "control not green: " + json.dumps(
            {k: cs.get(k) for k in killers if cs.get(k) != "PASS"})
    if any(ms.get(k) not in ("PASS", "FAIL") for k in killers):
        return "harness_error", "killer not reached: " + json.dumps(
            {k: ms.get(k) for k in killers
             if ms.get(k) not in ("PASS", "FAIL")})
    if any(ms.get(k) == "FAIL" for k in killers):
        return "killed", None
    return "survived", None


def check_edits(todo):
    """Read-only: every mutant's edits match the checked-out sources."""
    bad = 0
    for m in todo:
        texts, counts = {}, []
        for rel, old, new in m["edits"]:
            text = texts.setdefault(rel, (ROOT / rel).read_text())
            counts.append(text.count(old))
            texts[rel] = text.replace(old, new)
        ok = bool(m["edits"]) and all(n == 1 for n in counts)
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {m['id']} {counts}"
              f" killers={len(m['killers'])}")
    return 1 if bad else 0


def run_one(base, control, m):
    root = base.parent / m["id"]
    shutil.copytree(base, root, symlinks=True)
    proof = apply(root, m)
    rec = {"mutation_id": m["id"], "name": m["name"],
           "finding_ids": m["findings"], "kill_oracle": m["kill_oracle"],
           "files": sorted({e[0] for e in m["edits"]}),
           "proof": proof, "killers": m["killers"]}
    if not proof["applied"]:
        rec.update(outcome="harness_error",
                   reason=proof.get("reason", "mutation not applied"))
    else:
        t0 = time.monotonic()
        mut = run_killers(root, m["killers"])
        rec["seconds"] = round(time.monotonic() - t0, 1)
        rec["mutant"] = mut.get("cases", mut)
        rec["failed_killers"] = sorted(
            k for k, s in mut.get("cases", {}).items() if s == "FAIL")
        rec["mutant_details"] = mut.get("details")
        rec["imported_from"] = mut.get("imported_from")
        rec["outcome"], rec["reason"] = verdict(root, control, mut,
                                                m["killers"])
    shutil.rmtree(root, ignore_errors=True)
    print(f"{rec['outcome']:14} {m['id']} {m['name'][:50]}"
          f" {rec.get('reason') or ''}"
          f" failed={rec.get('failed_killers', [])[:6]}", flush=True)
    return rec


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    todo = [m for m in mutants() if not only or m["id"] in only]
    if "--check-edits" in argv:
        return check_edits(todo)
    work = pathlib.Path(tempfile.mkdtemp(prefix="m12-mut-"))
    results = []
    try:
        base = work / "control"
        base.mkdir()
        head = export(base)
        killers = sorted({k for m in todo for k in m["killers"]})
        t0 = time.monotonic()
        control = run_killers(base, killers, timeout=3600)
        if control.get("imported_from") not in (None, base.name):
            control = {"error": "control imported from another tree: "
                                f"{control.get('imported_from')}"}
        not_green = {k: s for k, s in control.get("cases", {}).items()
                     if s != "PASS"}
        print(f"control: {len(control.get('cases', {}))} killers,"
              f" not green {not_green} ({time.monotonic() - t0:.0f}s)",
              flush=True)
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
            "tool": "scripts/v2/m12_mutation_check.py",
            "runner": RUNNER, "code_sha": head,
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "killer_rule": "every non-native corpus case sharing a finding"
                           " id with the mutation, plus EXTRA (MUT05:"
                           " C004/C037; MUT19: regression r10)",
            "control": control, "summary": tally, "results": results},
            indent=1) + "\n")
    return 0 if all(r["outcome"] == "killed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
