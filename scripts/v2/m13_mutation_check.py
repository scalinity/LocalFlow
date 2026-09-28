"""The M13 audit corpus's 26 mutations M13-MUT01..26, run for real.

For each mutation: export the tracked tree at HEAD into a disposable
directory (``git archive``), apply exactly that semantic weakening to the
copied file(s) — every edit must match its text exactly once — prove the
patch applied (each file's hash changed) and that the killing run
imported ``localflow`` from THAT copy, then run the killers there.

Killers are the mutation's own ``killer_case_ids`` from the frozen
corpus (native cases excluded — they are graded on the owned-native
record, NOT_RUN in a copy), plus ``EXTRA`` where the named killers
cannot observe the weakening (MUT19: a no-op query makes every
``--noop`` variant exit invalid exactly as before, so the VALID
acceptance run, C247, is the case that notices). Outcomes:

- ``killed``        — the unmutated control is PASS on every killer and
                      the mutant makes at least one FAIL (an independent
                      semantic assertion, after its branch ran);
- ``survived``      — control green, the mutant still passes them all;
- ``harness_error`` — anything else: an edit that did not match, an
                      import from the wrong tree, a control that is not
                      green, an ERROR/NOT_RUN/INVALID in a killer, a
                      timeout. Never counted as a kill.

Everything runs under ``tests/v2/context/run_isolated.py``; the live
checkout is never modified.

    .venv/bin/python scripts/v2/m13_mutation_check.py --json OUT \
        [--only M13-MUT01,...] [--check-edits]
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
RUNNER = "tests/v2/analytics/m13_corpus_runner.py"
ISOLATED = "tests/v2/context/run_isolated.py"
CORPUS = ROOT / "tests" / "v2" / "analytics" / "m13_audit_corpus.json"

A = "localflow/v2/analytics.py"
STORE = "localflow/v2/store.py"
APP = "localflow/app.py"
STATE = "localflow/v2/ui/state.py"
NOTES = "localflow/v2/notes.py"
READY = "localflow/v2/training_data.py"
BENCH = "scripts/v2/benchmark_m13.py"
TTD = "tests/v2/ui/test_training_data.py"

NATIVE = {"M13-C157", "M13-C186", "M13-C237", "M13-C238", "M13-C262"}
EXTRA = {"M13-MUT19": ["M13-C247"]}

# Each edit is (file, old, new).
EDITS = {
    "M13-MUT01": [(APP,
                   '            captured = row.get("captured_at_utc") \\\n'
                   '                or prov.get("captured_at_utc")\n',
                   '            captured = v2.ids.now_utc_iso()\n')],
    "M13-MUT02": [(STORE,
                   "CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_facts_job",
                   "CREATE INDEX IF NOT EXISTS idx_usage_facts_job"),
                  (A,
                   '            fact_id = prev[0] if prev else ids.new_id("uf")\n',
                   '            fact_id = ids.new_id("uf") if attempt > 1'
                   ' else (prev[0] if prev else ids.new_id("uf"))\n')],
    "M13-MUT03": [(A,
                   "                # (recomputed) or loses its row when it"
                   " emptied.\n"
                   "                self._recompute_day(conn, prev_day, zone)\n",
                   "                # (recomputed) or loses its row when it"
                   " emptied.\n                pass\n")],
    "M13-MUT04": [(A,
                   '            self._write_fact(conn, fact_id=fact_id,'
                   ' kind="repaste",\n'
                   '                             zone=zone, values={\n'
                   '                                 "activity_at_utc": at,'
                   ' "day_local": day,\n'
                   '                                 "job_id": job_id,'
                   ' "meta": meta})\n',
                   '            self._write_fact(conn, fact_id=fact_id,'
                   ' kind="dictation",\n'
                   '                             zone=zone, values={\n'
                   '                                 "activity_at_utc": at,'
                   ' "day_local": day,\n'
                   '                                 "job_id": None,'
                   ' "final_words": 5, "meta": meta})\n')],
    "M13-MUT05": [(APP,
                   '                attempt=job.get("attempt", 1),\n'
                   '                meta=meta)\n',
                   '                attempt=job.get("attempt", 1),\n'
                   '                meta=meta)\n'
                   '            if tf_job is not None:\n'
                   '                self._analytics.record_transform_fact('
                   'transform_id=tf_job.transform_id, task_key="auto",'
                   ' path=getattr(tf, "path", None),'
                   ' source_kind="dictation", source_words=1)\n')],
    "M13-MUT06": [(A,
                   '            "wpm": (round(60.0 * rate_words /'
                   ' rate_seconds, 1)\n'
                   '                    if rate_jobs else None),\n',
                   '            "wpm": (round(conn.execute("SELECT'
                   ' AVG(60.0 * final_words / duration_sec) FROM usage_facts'
                   ' WHERE " + where + " AND final_words > 0 AND'
                   ' duration_sec > 0", params).fetchone()[0], 1)\n'
                   '                    if rate_jobs else None),\n')],
    "M13-MUT07": [(A,
                   '            " SUM(CASE WHEN final_words > 0 AND'
                   ' duration_sec > 0"\n'
                   '            "  THEN duration_sec ELSE 0.0 END),"\n',
                   '            " SUM(CASE WHEN duration_sec > 0"\n'
                   '            "  THEN duration_sec ELSE 0.0 END),"\n')],
    "M13-MUT08": [(A,
                   '            " SUM(CASE WHEN final_words > 0 AND'
                   ' duration_sec > 0"\n'
                   '            "  THEN final_words ELSE 0 END),"\n',
                   '            " SUM(CASE WHEN final_words > 0"\n'
                   '            "  THEN final_words ELSE 0 END),"\n')],
    "M13-MUT09": [(A,
                   '        return None, "unknown_zone"\n',
                   '        return value, None\n'),
                  (A,
                   '        raise ValueError("invalid reporting timezone")'
                   ' from e\n',
                   '        return zoneinfo.ZoneInfo("UTC")\n')],
    "M13-MUT10": [(A,
                   '        conn.execute("DELETE FROM daily_aggregates")\n'
                   '        conn.execute("INSERT OR REPLACE INTO'
                   ' usage_meta(key, value)"\n',
                   '        conn.execute("INSERT OR REPLACE INTO'
                   ' usage_meta(key, value)"\n'),
                  (A,
                   '        # One row per day: any row of another'
                   ' zone/version for this day\n'
                   '        # is replaced, never left beside the current'
                   ' one.\n'
                   '        conn.execute("DELETE FROM daily_aggregates WHERE'
                   ' day_local=?",\n'
                   '                     (day_local,))\n',
                   '        conn.execute("DELETE FROM daily_aggregates WHERE'
                   ' day_local=? AND reporting_timezone=?",\n'
                   '                     (day_local, zone))\n')],
    "M13-MUT11": [(A,
                   '            target = zone or self._zone_in(conn)\n'
                   '            out = self._rebuild(conn, target)\n',
                   '            target = zone or self._zone_in(conn)\n'
                   '            self._committed_zone = target\n'
                   '            out = self._rebuild(conn, target)\n')],
    "M13-MUT12": [(A,
                   '    def _cutoff(self, days, now):\n'
                   '        return instant_from_epoch(now - days * 86400)\n',
                   '    def _cutoff(self, days, now):\n'
                   '        return ids.now_utc_iso(now - days * 86400)\n'),
                  (A,
                   '        at = canonical_instant(activity_at_utc)\n'
                   '        if at is None:\n'
                   '            return self._refuse(job_id=job_id)\n',
                   '        at = (activity_at_utc if canonical_instant('
                   'activity_at_utc) else None)\n'
                   '        if at is None:\n'
                   '            return self._refuse(job_id=job_id)\n'),
                  # The raw string still buckets (so the mutant fails on
                  # ORDER, not on a parse crash).
                  (A,
                   '    return dt.datetime.strptime(iso,'
                   ' "%Y-%m-%dT%H:%M:%S.%fZ").replace(\n'
                   '        tzinfo=dt.timezone.utc)\n',
                   '    return dt.datetime.fromisoformat(iso.replace("Z",'
                   ' "+00:00"))\n')],
    "M13-MUT13": [(A,
                   '        transforms = repastes = transform_words = None\n',
                   '        transforms = repastes = transform_words = 0\n')],
    "M13-MUT14": [(NOTES,
                   '                 json.dumps(meta, ensure_ascii=False),'
                   ' now))\n',
                   '                 json.dumps(meta, ensure_ascii=False),'
                   ' now))\n'
                   '            db.execute("INSERT INTO usage_facts(fact_id,'
                   ' kind, job_id, activity_at_utc, day_local,'
                   ' reporting_timezone, algorithm_version, created_at_utc,'
                   ' final_words) VALUES(?, \'dictation\', NULL,'
                   ' \'2026-09-26T15:00:00.000000Z\', \'2026-09-26\','
                   ' \'UTC\', 1, ?, ?)", (revision_id, now,'
                   ' word_count(content)))\n')],
    "M13-MUT15": [(READY,
                   '                    audio_referenced += 1\n'
                   '                    arow = conn.execute(\n',
                   '                    arow = conn.execute(\n'),
                  (READY,
                   '                        audio_count += 1\n'
                   '                        audio_ok = True\n',
                   '                        audio_count += 1\n'
                   '                        audio_referenced += 1\n'
                   '                        audio_ok = True\n')],
    "M13-MUT16": [(A,
                   '                "legacy_fixed_words": row[4],\n',
                   '                "legacy_fixed_words": row[4],'
                   ' "wpm": row[4],\n')],
    "M13-MUT17": [(A,
                   '            "dictations": n or 0,\n',
                   '            "dictations": (n or 0) +'
                   ' self._undated(conn),\n')],
    "M13-MUT18": [(STATE,
                   "                if self._gens.get(req.key) != req.gen:\n"
                   "                    return False\n", "")],
    "M13-MUT19": [(BENCH,
                   '        "report_30d": (lambda: q.report(days=30),\n',
                   '        "report_30d": (lambda: {},\n')],
    "M13-MUT20": [(READY,
                   '                if state == "excluded":\n'
                   '                    excluded_class += 1\n'
                   '                    continue\n'
                   '                if state not in live_example_states:\n',
                   '                if state == "excluded":\n'
                   '                    excluded_class += 1\n'
                   '                if state not in live_example_states and'
                   ' state != "excluded":\n')],
    "M13-MUT21": [(READY,
                   '                if has_verbatim:\n'
                   '                    if audio_ok:\n',
                   '                if has_verbatim:\n'
                   '                    if True:\n')],
    "M13-MUT22": [(BENCH,
                   '            t = time.perf_counter()\n'
                   '            r = fn()\n'
                   '            samples.append((time.perf_counter() - t)'
                   ' * 1000.0)\n',
                   '            r = fn()\n'
                   '            t = time.perf_counter()\n'
                   '            samples.append((time.perf_counter() - t)'
                   ' * 1000.0)\n')],
    "M13-MUT23": [(A,
                   '    def _per_mode(self, conn, days, app, mode)'
                   ' -> list[dict]:\n'
                   '        zone, start, end, cohort, cparams ='
                   ' self._ctx(conn, days, app, mode)\n',
                   '    def _per_mode(self, conn, days, app, mode)'
                   ' -> list[dict]:\n'
                   '        zone, start, end, cohort, cparams ='
                   ' self._ctx(conn, days, None, mode)\n')],
    "M13-MUT24": [(STATE,
                   "    def set_insights_filters(self, range_days=..., app=...,"
                   " mode=...):\n",
                   "    def set_insights_filters(self, range_days=None,"
                   " app=..., mode=...):\n")],
    "M13-MUT25": [(A,
                   "        conn_redact_usage_copies(conn, reason,\n"
                   "                                 ids.now_utc_iso("
                   "self.now_fn()))\n", "")],
    "M13-MUT26": [(TTD,
                   "    test_readiness_triad_honest()\n"
                   "    test_readiness_aggregates_m13()\n",
                   "    test_readiness_triad_honest()\n")],
}


def mutants():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    out = []
    for m in corpus["mutations"]:
        killers = [c for c in m["killer_case_ids"] if c not in NATIVE]
        killers += [k for k in EXTRA.get(m["mutation_id"], [])
                    if k not in killers]
        out.append({"id": m["mutation_id"], "name": m["mutation"],
                    "kill_rule": m["kill_rule"],
                    "edits": EDITS.get(m["mutation_id"], []),
                    "killers": killers})
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


def run_killers(root, killers, timeout=3600):
    out = root / "mut_result.json"
    cmd = [str(PY), ISOLATED, RUNNER, "--no-relations", "--only",
           ",".join(killers), "--out", str(out)]
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if not out.exists():
        return {"error": f"no result (exit {p.returncode})",
                "stderr": p.stderr[-600:]}
    d = json.loads(out.read_text())
    out.unlink()
    cases, details = {}, {}
    for r in d["cases"]:
        cases[r["case_id"]] = r["status"]
        if r["status"] != "PASS":
            details[r["case_id"]] = (r.get("note") or "")[:300]
    return {"imported_from": d["code"].get("localflow_imported_from_root"),
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
              f" killers={m['killers']}")
    return 1 if bad else 0


def run_one(base, control, m):
    root = base.parent / m["id"]
    shutil.copytree(base, root, symlinks=True)
    proof = apply(root, m)
    rec = {"mutation_id": m["id"], "name": m["name"],
           "kill_rule": m["kill_rule"],
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
    work = pathlib.Path(tempfile.mkdtemp(prefix="m13-mut-"))
    results = []
    try:
        base = work / "control"
        base.mkdir()
        head = export(base)
        killers = sorted({k for m in todo for k in m["killers"]})
        t0 = time.monotonic()
        control = run_killers(base, killers, timeout=7200)
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
            "tool": "scripts/v2/m13_mutation_check.py",
            "runner": RUNNER, "code_sha": head,
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "killer_rule": "each mutation's killer_case_ids from the frozen"
                           " corpus minus native cases, plus EXTRA (MUT19:"
                           " C247, the valid acceptance run)",
            "control": control, "summary": tally, "results": results},
            indent=1) + "\n")
    return 0 if all(r["outcome"] == "killed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
