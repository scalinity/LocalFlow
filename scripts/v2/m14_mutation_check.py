"""The M14 audit corpus's 32 mutations LF-M14-MU001..032, run for real.

For each mutation: export the tracked tree at HEAD into a disposable
directory (``git archive``), apply exactly that semantic weakening to the
copied file(s) — every edit must match its text exactly once — prove the
patch applied (each file's hash changed), then run the killers there.

Each mutant also carries a REACH MARKER: the mutated branch appends the
mutation id to the file named by ``M14_MUT_REACH`` when it executes
(nothing when the variable is unset). A kill needs both halves the
corpus requires — the mutated branch was reached AND an independent
semantic assertion failed:

- ``killed``        — control green on every killer, the marker shows the
                      branch ran, and at least one killer FAILs;
- ``survived``      — control green, branch ran, every killer passes;
- ``not_reached``   — control green but the branch never ran (invalid,
                      never a kill);
- ``harness_error`` — an edit that did not match, a control that is not
                      green, an ERROR/NOT_RUN/INVALID in a killer, a
                      timeout. Never counted as a kill.

Killers: the mutation's ``test_case_ids`` from the frozen corpus minus
native/performance entries (graded on their own records, NOT_RUN in a
copy), plus the matching fail-first regressions of
tests/v2/personalization/test_m14_remediation.py (``EXTRA``). Everything
runs under tests/v2/context/run_isolated.py; the live checkout is never
modified.

    .venv/bin/python scripts/v2/m14_mutation_check.py --json OUT \
        [--only LF-M14-MU001,...] [--check-edits]
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
RUNNER = "tests/v2/personalization/m14_corpus_runner.py"
SUITE = "tests/v2/personalization/test_m14_remediation.py"
CORPUS = ROOT / "tests" / "v2" / "personalization" / "m14_audit_corpus.json"

EV = "localflow/v2/curation/evidence.py"
RV = "localflow/v2/curation/review.py"
EX = "localflow/v2/curation/export.py"
SP = "localflow/v2/curation/splits.py"
CL = "localflow/v2/curation/classify.py"
LN = "localflow/v2/learning.py"
PR = "localflow/v2/profile.py"
TD = "localflow/v2/training_data.py"
AN = "localflow/v2/analytics.py"
HUB = "localflow/v2/ui/hub.py"
BM = "scripts/v2/benchmark_m14.py"


def mark(mid, indent):
    """A statement that records the mutated branch ran."""
    return (" " * indent + "(__import__('os').environ.get('M14_MUT_REACH')"
            f" and open(__import__('os').environ['M14_MUT_REACH'], 'a')"
            f".write('{mid}\\n'))\n")


def mexpr(mid):
    """The same marker as an expression that evaluates true."""
    return ("((__import__('os').environ.get('M14_MUT_REACH') and"
            " open(__import__('os').environ['M14_MUT_REACH'], 'a')"
            f".write('{mid}\\n')) or True)")


# Each edit is (file, old, new); the new text carries the reach marker.
EDITS = {
    "LF-M14-MU001": [(RV,
        "    audio = ev.qualify(conn, audio_aid, \"original_audio\","
        " job_id=job_id)\n",
        mark("LF-M14-MU001", 4)
        + "    audio = ev.qualify(conn, audio_aid, \"original_audio\","
          " job_id=(conn.execute(\"SELECT job_id FROM artifacts WHERE"
          " artifact_id=?\", (audio_aid,)).fetchone() or [job_id])[0])\n")],
    "LF-M14-MU002": [(EV,
        "    return role in SLOT_ROLES.get(slot, ())\n",
        "    if slot == \"source_text\":\n"
        + mark("LF-M14-MU002", 8) + "        return True\n"
        "    return role in SLOT_ROLES.get(slot, ())\n")],
    "LF-M14-MU003": [(RV,
        "            if state is None or state[0] not in TRAINABLE_STATES:\n",
        "            if state is not None and state[0] not in"
        " TRAINABLE_STATES:\n" + mark("LF-M14-MU003", 16)
        + "            if state is None:\n")],
    "LF-M14-MU004": [(RV,
        "        resolved = effective is not None \\\n"
        "            and effective[\"edit_kind\"] not in _ASR_BLOCKING_KINDS\n",
        "        resolved = False and " + mexpr("LF-M14-MU004") + "\n"
        + mark("LF-M14-MU004", 8))],
    "LF-M14-MU005": [(RV,
        "    if any(k in _ASR_PERMANENT_BLOCKERS for k in history):\n",
        mark("LF-M14-MU005", 4)
        + "    if effective is not None and effective[\"edit_kind\"] in"
          " _ASR_PERMANENT_BLOCKERS:\n")],
    "LF-M14-MU006": [(CL,
        "        \"coverage_kind\": \"partial\",\n",
        "        \"coverage_kind\": \"full\" if " + mexpr("LF-M14-MU006")
        + " else \"partial\",\n")],
    "LF-M14-MU007": [(LN,
        "            \" AND o.observation_id NOT IN (SELECT observation_id"
        " FROM\"\n"
        "            \" learning_candidates WHERE observation_id IS NOT"
        " NULL)\"\n", ""),
        (LN,
        "            if conn.execute(\n"
        "                    \"SELECT 1 FROM learning_candidates WHERE\"\n"
        "                    \" observation_id=?\", (obs_id,)).fetchone():\n",
        mark("LF-M14-MU007", 12) + "            if False:\n")],
    "LF-M14-MU008": [(LN,
        "            suppressed = any(\n",
        mark("LF-M14-MU008", 12) + "            suppressed = False and any(\n")],
    "LF-M14-MU009": [(LN,
        "            eid = vs.find_in(conn, canonical, kind, value)\n",
        mark("LF-M14-MU009", 12) + "            eid = None\n")],
    "LF-M14-MU010": [(LN,
        "        scope_ctx = vocab_mod.ScopeContext(\n"
        "            **({_SCOPE_FIELDS[kind]: value} if kind in _SCOPE_FIELDS\n"
        "               else {}))\n",
        mark("LF-M14-MU010", 8)
        + "        scope_ctx = vocab_mod.ScopeContext()\n")],
    "LF-M14-MU011": [(LN,
        "    if action == \"created\":\n"
        "        rev = delta.get(\"revision_after_approval\")\n",
        "    if True:\n" + mark("LF-M14-MU011", 8)
        + "        rev = None\n")],
    "LF-M14-MU012": [(EX,
        "                \"chosen\": (\"a\" if judgment == \"prefer_a\"\n"
        "                           else \"b\" if judgment == \"prefer_b\""
        " else None),\n",
        "                \"chosen\": (\"b\" if judgment == \"prefer_a\" and "
        + mexpr("LF-M14-MU012") + "\n"
        "                           else \"a\" if judgment == \"prefer_b\""
        " else None),\n")],
    "LF-M14-MU013": [(HUB,
        "        self._rendered[\"review_pair\"] = {\"task_key\":"
        " pair[\"task_key\"],\n"
        "                                         \"a\": a[\"candidate_id\"],\n"
        "                                         \"b\": b[\"candidate_id\"]}\n",
        mark("LF-M14-MU013", 8)
        + "        self._rendered[\"review_pair\"] = {\"task_key\":"
          " pair[\"task_key\"],\n"
          "                                         \"a\": b[\"candidate_id\"],\n"
          "                                         \"b\": a[\"candidate_id\"]}\n")],
    "LF-M14-MU014": [(EV,
        "    if len(by_id) != 2 or any(r[1] != task_key for r in rows):\n",
        mark("LF-M14-MU014", 4) + "    if len(by_id) != 2:\n"),
        (EV,
        "    if a[2:5] != b[2:5]:\n        return {\"eligible\": False,"
        " \"reason\": \"input_hashes_differ\"}\n",
        ""),
        (EV,
        "        if ids.sha256_text(q[\"artifact\"][\"text\"]) != cand[2]:\n"
        "            return {\"eligible\": False, \"reason\":"
        " \"source_digest_mismatch\"}\n        source = q[\"artifact\"]\n",
        "        source = q[\"artifact\"]\n")],
    "LF-M14-MU015": [(SP,
        "                partition = partitions.get(fam, \"unassigned\")\n",
        "                partition = (_family_bucket(seed, ex_id) if"
        " partitions and " + mexpr("LF-M14-MU015")
        + " else \"unassigned\")\n")],
    "LF-M14-MU016": [(EX,
        "            memberships[ex_id] = (fam, part,\n"
        "                                  bool(exposed) or fam in"
        " exposed_ever)\n",
        mark("LF-M14-MU016", 12)
        + "            memberships[ex_id] = (fam, part, bool(exposed))\n")],
    "LF-M14-MU017": [(EX,
        "        destination.parent.mkdir(parents=True, exist_ok=True)\n"
        "        staging = destination.parent / \\\n",
        "        destination.parent.mkdir(parents=True, exist_ok=True)\n"
        "        if (destination.parent / f\".{destination.name}.building\")"
        ".exists():\n" + mark("LF-M14-MU017", 12)
        + "            shutil.rmtree(destination.parent /"
          " f\".{destination.name}.building\", ignore_errors=True)\n"
          "        staging = destination.parent / \\\n")],
    "LF-M14-MU018": [(EX,
        "            if n != len(chunk):\n"
        "                return \"input_purged_or_absent\"\n",
        "            if n != len(chunk):\n" + mark("LF-M14-MU018", 16)
        + "                pass\n")],
    "LF-M14-MU019": [(EX,
        "        inputs = deps[\"inputs\"]\n",
        "        if conn.execute(\"SELECT COUNT(*) FROM deletion_tombstones\")"
        ".fetchone()[0] > deps.get(\"tombstones\", 0):\n"
        + mark("LF-M14-MU019", 12)
        + "            return \"tombstone_moved\"\n"
          "        inputs = deps[\"inputs\"]\n"),
        (EX,
        "        return {\"inputs\": inputs, \"examples\": examples,"
        " \"pairs\": pairs,\n                \"accepts\": accepts}\n",
        "        return {\"inputs\": inputs, \"examples\": examples,"
        " \"pairs\": pairs,\n                \"accepts\": accepts,"
        " \"tombstones\": conn.execute(\"SELECT COUNT(*) FROM"
        " deletion_tombstones\").fetchone()[0]}\n")],
    "LF-M14-MU020": [(EX,
        "        if _sha256_file(p) != digest:\n",
        mark("LF-M14-MU020", 8) + "        if False:\n"),
        (EX,
        "    if _fingerprint(semantic) != manifest.get(\"content_fingerprint\"):\n",
        "    if False:\n")],
    "LF-M14-MU021": [(PR,
        "                if row is None or row[0] not in _LIVE_STATES:\n"
        "                    return {\"stale\": True}  # evidence died during"
        " the read\n",
        mark("LF-M14-MU021", 16)
        + "                if row is None:\n"
          "                    return {\"stale\": True}\n")],
    "LF-M14-MU022": [(PR,
        "                        \"evidence_example_ids\":"
        " label_examples[top][:5],\n",
        "                        \"evidence_example_ids\": sorted("
        "eligible_ids)[:5] if " + mexpr("LF-M14-MU022") + " else [],\n")],
    "LF-M14-MU023": [(PR,
        "            if last and last[1] == \"current\" and json.loads(\n"
        "                    last[2]).get(\"input_signature\") == quick:\n",
        mark("LF-M14-MU023", 12) + "            if False:\n")],
    "LF-M14-MU024": [(AN,
        "        for k in USAGE_DERIVED_PROFILE_FIELDS:\n"
        "            if k in measured:\n"
        "                measured[k] = None\n",
        mark("LF-M14-MU024", 8))],
    "LF-M14-MU025": [(TD,
        "                    if q[\"eligible\"]:\n"
        "                        cleanup_eligible += 1\n"
        "                        bump(cleanup_tiers, q[\"tier\"])\n",
        "                    if correctness in (\"correct\", \"incorrect\"):\n"
        + mark("LF-M14-MU025", 24)
        + "                        cleanup_eligible += 1\n"
          "                        bump(cleanup_tiers, q.get(\"tier\"))\n")],
    "LF-M14-MU026": [(BM,
        "        \"mining\": mine_observations_only,\n",
        "        \"mining\": lambda: " + mexpr("LF-M14-MU026") + " and 0,\n")],
    "LF-M14-MU027": [(EV,
        "        if not path or not managed_name_ok(path):\n",
        mark("LF-M14-MU027", 8) + "        if not path:\n"),
        (EX,
        "                src = open_managed_file(self.store.artifacts_dir,\n"
        "                                        artifact[\"path\"])\n",
        "                src = open(self.store.artifacts_dir /"
        " artifact[\"path\"], \"rb\")\n")],
    "LF-M14-MU028": [(PR,
        "                if not ev.qualify(conn, raw_aid, \"source_text\",\n"
        "                                  job_id=row[2])[\"ok\"]:\n",
        mark("LF-M14-MU028", 16) + "                if False:\n"),
        (PR,
        "            \" (a.artifact_id IS NULL OR a.purged=1)\").fetchall():\n",
        "            \" 0\").fetchall():\n")],
    "LF-M14-MU029": [(TD,
        "_ANNOTATION_ROLES = (\"verbatim_reference\", \"span_correction\",\n"
        "                     \"span_graft\", \"candidate_observation\",\n"
        "                     \"counterexample_result\")\n",
        "_ANNOTATION_ROLES = (\"verbatim_reference\", \"span_correction\")\n"),
        (TD,
        "            if pinned:\n",
        mark("LF-M14-MU029", 12) + "            if pinned:\n")],
    "LF-M14-MU030": [(LN,
        "        if not touching:\n"
        "            continue  # the user's own writing\n",
        "        if not touching:\n" + mark("LF-M14-MU030", 12)
        + "            keep.append((i1, i2, j1, j2))\n            continue\n")],
    "LF-M14-MU031": [(LN,
        "            if expected_final_artifact_id is not None and \\\n"
        "                    final[\"artifact\"][\"id\"] !="
        " expected_final_artifact_id:\n",
        mark("LF-M14-MU031", 12) + "            if False:\n"),
        (LN,
        "            if expected_final_sha256 is not None and \\\n"
        "                    ids.sha256_text(final_text) !="
        " expected_final_sha256:\n",
        "            if False:\n")],
    "LF-M14-MU032": [(PR,
        "                \"vocabulary\": [_vocabulary_revision(conn)] + list(\n",
        "                \"vocabulary\": ([] if " + mexpr("LF-M14-MU032")
        + " else []) + list(\n")],
}

# The fail-first regressions that observe each weakening (in addition to
# the corpus's own test_case_ids).
EXTRA = {
    "LF-M14-MU001": ["f01_foreign_audio_is_not_asr_evidence"],
    "LF-M14-MU002": ["f01_foreign_or_wrong_stage_cleanup_source_is_refused"],
    "LF-M14-MU003": ["c_label_refuses_restricted_states"],
    "LF-M14-MU004": ["d01_resolved_ambiguity_no_longer_blocks_asr"],
    "LF-M14-MU005": ["c_changed_intent_blocks_asr_forever"],
    "LF-M14-MU006": [],
    "LF-M14-MU007": [],
    "LF-M14-MU008": ["d05_case_variant_of_rejected_pair_stays_suppressed"],
    "LF-M14-MU009": ["f22_equivalent_app_scope_composes_with_existing_entry"],
    "LF-M14-MU010": [],
    "LF-M14-MU011": ["f10_concurrent_user_alias_survives_alias_undo"],
    "LF-M14-MU012": ["c_prefer_b_exports_b"],
    "LF-M14-MU013": ["f16_pair_judgment_binds_to_the_rendered_pair"],
    "LF-M14-MU014": ["f08_purged_task_source_makes_pair_ineligible"],
    "LF-M14-MU015": [],
    "LF-M14-MU016": ["f04_new_export_from_old_version_cannot_reclaim_blindness"],
    "LF-M14-MU017": ["f02_unowned_staging_directory_is_never_removed"],
    "LF-M14-MU018": ["c_selected_purge_before_fence_aborts"],
    "LF-M14-MU019": ["c_unrelated_deletion_does_not_abort"],
    "LF-M14-MU020": [],
    "LF-M14-MU021": [],
    "LF-M14-MU022": [],
    "LF-M14-MU023": ["c_unchanged_idle_pass_adds_no_snapshot"],
    "LF-M14-MU024": [],
    "LF-M14-MU025": ["f14_readiness_matches_export_membership"],
    "LF-M14-MU026": ["f28_benchmark_rejects_a_noop_component"],
    "LF-M14-MU027": ["f05_outside_audio_path_is_never_read"],
    "LF-M14-MU028": ["f03_purged_artifact_mid_compute_is_not_published"],
    "LF-M14-MU029": ["f24_unpin_keeps_review_retention_leases"],
    "LF-M14-MU030": ["f13_typed_only_region_is_not_dictation_evidence"],
    "LF-M14-MU031": ["f11_teach_refuses_a_final_newer_than_the_rendered_one"],
    "LF-M14-MU032": ["f23_used_term_canonical_edit_refreshes_the_profile_once"],
}


def mutants():
    corpus = json.loads(CORPUS.read_text())
    kinds = {c["id"]: c["kind"] for c in corpus["cases"]}
    out = []
    for m in corpus["mutations"]:
        corpus_killers = [c for c in m["test_case_ids"]
                          if kinds.get(c) == "portable"]
        out.append({"id": m["id"], "name": m["title"],
                    "kill_rule": m["kill_rule"],
                    "edits": EDITS.get(m["id"], []),
                    "corpus_killers": corpus_killers,
                    "suite_killers": EXTRA.get(m["id"], []),
                    "killers": corpus_killers + EXTRA.get(m["id"], [])})
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


def run_killers(root, m_or_all, timeout=5400):
    """Run corpus killers through the corpus runner and suite killers
    through the regression suite, in ``root``. Returns statuses, the
    importing tree and the reach markers written."""
    corpus_k = sorted({k for m in m_or_all for k in m["corpus_killers"]})
    suite_k = sorted({k for m in m_or_all for k in m["suite_killers"]})
    reach = root / "reach.txt"
    reach.unlink(missing_ok=True)
    env = dict(os.environ, M14_MUT_REACH=str(reach))
    cases, details, imported = {}, {}, set()
    try:
        if corpus_k:
            out = root / "corpus_out.json"
            p = subprocess.run(
                [str(PY), ISOLATED, RUNNER, "--only", ",".join(corpus_k),
                 "--out", str(out)], cwd=root, capture_output=True,
                text=True, timeout=timeout, env=env)
            if not out.exists():
                return {"error": f"no corpus result (exit {p.returncode})",
                        "stderr": p.stderr[-600:]}
            d = json.loads(out.read_text())
            out.unlink()
            imported.add(d["code"]["code_root_sha"] and root.name)
            for r in d["cases"]:
                cases[r["id"]] = r["status"]
                if r["status"] != "PASS":
                    details[r["id"]] = (r.get("note") or "")[:300]
        if suite_k:
            out = root / "suite_out.json"
            p = subprocess.run(
                [str(PY), ISOLATED, SUITE, "--json", str(out), *suite_k],
                cwd=root, capture_output=True, text=True,
                timeout=timeout, env=env)
            if not out.exists():
                return {"error": f"no suite result (exit {p.returncode})",
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


def verdict(control, mutant, m):
    if "error" in control or "error" in mutant:
        return "harness_error", "run error: " + str(
            mutant.get("error") or control.get("error"))
    cs, ms = control["cases"], mutant["cases"]
    killers = m["killers"]
    if any(cs.get(k) != "PASS" for k in killers):
        return "harness_error", "control not green: " + json.dumps(
            {k: cs.get(k) for k in killers if cs.get(k) != "PASS"})
    if any(ms.get(k) not in ("PASS", "FAIL") for k in killers):
        return "harness_error", "killer not reached: " + json.dumps(
            {k: ms.get(k) for k in killers
             if ms.get(k) not in ("PASS", "FAIL")})
    if m["id"] not in mutant.get("reached", []):
        return "not_reached", "the mutated branch never ran"
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
           "kill_rule": m["kill_rule"],
           "files": sorted({e[0] for e in m["edits"]}),
           "proof": proof, "killers": m["killers"]}
    if not proof["applied"]:
        rec.update(outcome="harness_error",
                   reason=proof.get("reason", "mutation not applied"))
    else:
        t0 = time.monotonic()
        mut = run_killers(root, [m])
        rec["seconds"] = round(time.monotonic() - t0, 1)
        rec["mutant"] = mut.get("cases", mut)
        rec["branch_reached"] = m["id"] in mut.get("reached", [])
        rec["failed_killers"] = sorted(
            k for k, s in mut.get("cases", {}).items() if s == "FAIL")
        rec["mutant_details"] = mut.get("details")
        rec["outcome"], rec["reason"] = verdict(control, mut, m)
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
    work = pathlib.Path(tempfile.mkdtemp(prefix="m14-mut-"))
    results = []
    try:
        base = work / "control"
        base.mkdir()
        head = export(base)
        t0 = time.monotonic()
        control = run_killers(base, todo, timeout=10800)
        stray = control.get("reached") or []
        if stray:
            control = {"error": f"control wrote reach markers {stray}"}
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
            "tool": "scripts/v2/m14_mutation_check.py",
            "runner": RUNNER, "suite": SUITE, "code_sha": head,
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "killer_rule": "each mutation's portable test_case_ids from the"
                           " frozen corpus plus the matching fail-first"
                           " regressions (EXTRA); a kill needs the reach"
                           " marker AND a failed killer",
            "control": control, "summary": tally, "results": results},
            indent=1) + "\n")
    return 0 if all(r["outcome"] == "killed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
