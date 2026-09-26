"""The M10 audit corpus's 26 mutations M10-MUT01..26, run for real.

For each mutation: export the tracked tree at HEAD into a disposable
directory (``git archive``), apply exactly that semantic weakening to
the copied module(s) — every edit must match its text exactly once —
prove the patch applied (each file's hash changed) and that the killing
run imported ``localflow`` from THAT copy, then run the killers there.

Killers are not chosen per mutant: they are every corpus case that
shares a finding with the mutation (``related_findings`` in the frozen
corpus), minus the cases that grade a separately produced record
(``RECORD_CASES``: they are NOT_RUN without it). MUT26 attacks the pane
sizing only a native run can observe; its killers are the passive-tier
cases of ``tests/v2/ui/test_native_m10_panes.py``. Outcomes:

- ``killed``        — the unmutated control is PASS on every killer and
                      the mutant makes at least one FAIL;
- ``survived``      — control green, the mutant still passes them all;
- ``harness_error`` — anything else: an edit that did not match, an
                      import from the wrong tree, a control that is not
                      green, an ERROR/NOT_RUN in a killer, a timeout.
                      Never counted as a kill.

Everything runs under ``tests/v2/context/run_isolated.py`` (no real
Accessibility, event posting or general pasteboard); the native cases
are the passive tier (the app is never activated).

    .venv/bin/python scripts/v2/m10_mutation_check.py --json OUT \
        [--only M10-MUT01,...] [--check-edits]
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
RUNNER = "tests/v2/profiles/m10_corpus_runner.py"
NATIVE = "tests/v2/ui/test_native_m10_panes.py"
ISOLATED = "tests/v2/context/run_isolated.py"
CORPUS = ROOT / "tests" / "v2" / "profiles" / "m10_audit_corpus.json"

# Cases graded on a record produced elsewhere (the native active tier,
# the isolated benchmark run): NOT_RUN in a copy, so never killers.
RECORD_CASES = {"M10-C175", "M10-C176", "M10-C199"}

APP = "localflow/app.py"
PROF = "localflow/v2/profiles.py"
PSTORE = "localflow/v2/profiles_store.py"
SNIP = "localflow/v2/snippets.py"
SSTORE = "localflow/v2/snippets_store.py"
VOCAB = "localflow/v2/vocabulary.py"
TDEF = "localflow/v2/transforms/definitions.py"
TSTORE = "localflow/v2/transforms_store.py"
SYNTAX = "localflow/v2/normalize/syntax.py"
SKILLS = "localflow/v2/developer/skills.py"
FTAGS = "localflow/v2/developer/file_tags.py"
HUB = "localflow/v2/ui/hub.py"
BENCH = "scripts/v2/benchmark_m10.py"

# Each edit is (file, old, new).
EDITS = {
    "M10-MUT01": [(PROF,
                   "        key=lambda r: (-SCOPE_PRECEDENCE[r.scope_kind],"
                   " r.rule_id))\n",
                   "        key=lambda r: (SCOPE_PRECEDENCE[r.scope_kind],"
                   " r.rule_id))\n")],
    "M10-MUT02": [(PROF,
                   "    have = canonical_scope(rule.scope_kind, have)\n"
                   "    return have is not None and have == canonical_scope(\n"
                   "        rule.scope_kind, rule.scope_value)\n",
                   "    return have is not None and have == rule.scope_value\n")],
    "M10-MUT03": [(APP,
                   "        m10[\"wp\"] = v2_profiles.resolve(m10[\"override\"],"
                   " m10[\"rules\"],\n",
                   "        m10[\"wp\"] = v2_profiles.resolve(m10[\"override\"],"
                   " self._styles.rules(),\n")],
    "M10-MUT04": [(VOCAB,
                   "    if type(value) is not bool:\n"
                   "        raise AdmissionError(\"not_a_boolean\", field)\n"
                   "    return value\n",
                   "    return bool(value)\n"),
                  (PROF,
                   "        if type(self.enabled) is not bool:\n"
                   "            raise AdmissionError(\"not_a_boolean\","
                   " \"enabled\")\n",
                   "        object.__setattr__(self, \"enabled\","
                   " bool(self.enabled))\n"),
                  (SNIP,
                   "            if type(v) is not bool:\n"
                   "                raise _admission(\"not_a_boolean\", f)\n",
                   "            object.__setattr__(self, f, bool(v))\n"),
                  (TDEF,
                   "            if type(getattr(self, f)) is not bool:\n"
                   "                raise ValueError(f\"not_a_boolean: {f}\")\n",
                   "            object.__setattr__(self, f,"
                   " bool(getattr(self, f)))\n"),
                  (TSTORE,
                   "            if field in changes and type(changes[field])"
                   " is not bool:\n"
                   "                raise ValueError(f\"not_a_boolean:"
                   " {field}\")\n",
                   "            if field in changes:\n"
                   "                changes[field] = bool(changes[field])\n")],
    "M10-MUT05": [(PSTORE,
                   "        now = ids.now_utc_iso()\n\n"
                   "        def op(db):\n"
                   "            row = db.execute(\n"
                   "                f\"SELECT {', '.join(_RULE_COLS)} FROM"
                   " style_rules\"\n"
                   "                f\" WHERE rule_id=?\", (rule_id,))"
                   ".fetchone()\n"
                   "            if row is None:\n"
                   "                return (\"not_found\", None)\n"
                   "            current = _row_to_rule(row)\n",
                   "        now = ids.now_utc_iso()\n"
                   "        pre = self.rule(rule_id)\n\n"
                   "        def op(db):\n"
                   "            row = db.execute(\n"
                   "                f\"SELECT {', '.join(_RULE_COLS)} FROM"
                   " style_rules\"\n"
                   "                f\" WHERE rule_id=?\", (rule_id,))"
                   ".fetchone()\n"
                   "            if row is None:\n"
                   "                return (\"not_found\", None)\n"
                   "            current = pre or _row_to_rule(row)\n"),
                  (PSTORE,
                   "                f\"{', '.join(f'{c}=?' for c in cols)},"
                   " revision=?,\"\n"
                   "                f\" updated_at_utc=? WHERE rule_id=? AND"
                   " revision=?\",\n"
                   "                (*vals, updated.revision, now, rule_id,"
                   " current.revision))\n",
                   "                f\"{', '.join(f'{c}=?' for c in cols)},"
                   " revision=revision+1,\"\n"
                   "                f\" updated_at_utc=? WHERE rule_id=?\",\n"
                   "                (*vals, now, rule_id))\n"),
                  (SSTORE,
                   "        now = ids.now_utc_iso()\n\n"
                   "        def op(db):\n"
                   "            row = db.execute(\n"
                   "                f\"SELECT {', '.join(_SNIPPET_COLS)} FROM"
                   " snippets\"\n"
                   "                f\" WHERE snippet_id=?\", (snippet_id,))"
                   ".fetchone()\n"
                   "            if row is None:\n"
                   "                return (\"not_found\", None)\n"
                   "            current = _row_to_snippet(row)\n",
                   "        now = ids.now_utc_iso()\n"
                   "        pre = self.snippet(snippet_id)\n\n"
                   "        def op(db):\n"
                   "            row = db.execute(\n"
                   "                f\"SELECT {', '.join(_SNIPPET_COLS)} FROM"
                   " snippets\"\n"
                   "                f\" WHERE snippet_id=?\", (snippet_id,))"
                   ".fetchone()\n"
                   "            if row is None:\n"
                   "                return (\"not_found\", None)\n"
                   "            current = pre or _row_to_snippet(row)\n"),
                  (SSTORE,
                   "                f\"{', '.join(f'{c}=?' for c in cols)},"
                   " revision=?,\"\n"
                   "                f\" updated_at_utc=? WHERE snippet_id=? AND"
                   " revision=?\",\n"
                   "                (*vals, updated.revision, now, snippet_id,\n"
                   "                 current.revision))\n",
                   "                f\"{', '.join(f'{c}=?' for c in cols)},"
                   " revision=revision+1,\"\n"
                   "                f\" updated_at_utc=? WHERE snippet_id=?\",\n"
                   "                (*vals, now, snippet_id))\n")],
    "M10-MUT06": [(SNIP,
                   "            else:\n"
                   "                unique[trig] = cands[0]\n",
                   "            unique[trig] = cands[0]\n")],
    "M10-MUT07": [(SYNTAX,
                   "                    t.is_word for t in seq) or not"
                   " host.connected(i, i + n):\n"
                   "                continue\n"
                   "            placeholders = snippet.placeholders\n",
                   "                    t.is_word for t in seq):\n"
                   "                continue\n"
                   "            placeholders = snippet.placeholders\n"),
                  (SYNTAX,
                   "            while j < len(tokens) and tokens[j].is_word \\\n"
                   "                    and not host.hard_break_before(j) \\\n"
                   "                    and j not in hard_spoken:\n",
                   "            while j < len(tokens) and tokens[j].is_word:\n")],
    "M10-MUT08": [(APP,
                   "                        norm_result = v2_normalize.normalize(\n"
                   "                            raw, norm_policy, norm_context)\n"
                   "                        norm_text = norm_result.text\n",
                   "                        norm_result = v2_normalize.normalize(\n"
                   "                            raw, norm_policy, norm_context)\n"
                   "                        norm_result = v2_normalize.normalize(\n"
                   "                            norm_result.text, norm_policy,"
                   " norm_context)\n"
                   "                        norm_text = norm_result.text\n")],
    "M10-MUT09": [(SKILLS,
                   "    first_nl = data.find(b\"\\n\")\n"
                   "    first = data if first_nl < 0 else data[:first_nl]\n"
                   "    if first.rstrip(b\"\\r \\t\") != b\"---\":\n"
                   "        return None, (), \"no_frontmatter\"\n"
                   "    lines = data.split(b\"\\n\")\n",
                   "    lines = data.split(b\"\\n\")\n"
                   "    start = next((i for i in range(len(lines))\n"
                   "                  if lines[i].rstrip(b\"\\r \\t\") =="
                   " b\"---\"), None)\n"
                   "    if start is None:\n"
                   "        return None, (), \"no_frontmatter\"\n"
                   "    lines = lines[start:]\n")],
    "M10-MUT10": [(SKILLS,
                   "        else \"workspace\"\n"
                   "    for i, p in enumerate(manifest_paths):\n",
                   "        else \"workspace\"\n"
                   "    if not manifest_paths:\n"
                   "        manifest_paths = (os.path.expanduser("
                   "\"~/.claude/skills\"),)\n"
                   "    for i, p in enumerate(manifest_paths):\n")],
    "M10-MUT11": [(APP,
                   "            records = list(m10.get(\"global_skill_records\",\n"
                   "                                   m10.get(\"skill_records\"))"
                   " or ())\n",
                   "            records = list(m10.get(\"global_skill_records\",\n"
                   "                                   m10.get(\"skill_records\"))"
                   " or ()) + [\n"
                   "                r for c in self._ws_skill_cache.values()\n"
                   "                for r in c[1].records]\n")],
    "M10-MUT12": [(FTAGS,
                   "            found = set(self._match(spoken))\n"
                   "            if doc is not None and low in (doc_full,"
                   " doc_base):\n",
                   "            found = set(self._match(spoken))\n"
                   "            if doc is not None and low in (doc_full,"
                   " doc_base):\n"
                   "                return FileResolution(\"resolved\","
                   " filename=doc,\n"
                   "                                      matched_words=k)\n"
                   "            if doc is not None and low in (doc_full,"
                   " doc_base):\n")],
    "M10-MUT13": [(FTAGS,
                   "        \"method\": \"literal_filename\",\n"
                   "        \"attachment_created\": False,\n",
                   "        \"method\": \"literal_filename\",\n"
                   "        \"attachment_created\": True,\n")],
    "M10-MUT14": [(TDEF,
                   "        if not d.auto_apply:\n"
                   "            return d, f\"transform_auto_apply_disabled:"
                   "{mode}\"\n", "")],
    "M10-MUT15": [(APP,
                   "            skills = dict(registry.policy_skills)\n"
                   "            prov = dict(registry.policy_provenance)\n", "")],
    "M10-MUT16": [(HUB,
                   "        sel = self.state.views[view].get(\"selected_id\")\n"
                   "        if not sel:\n"
                   "            return None\n"
                   "        editor = self._style_editor if view == \"styles\" \\\n",
                   "        idx = getattr(self, f\"{view}_table\").selectedRow()\n"
                   "        latest = (self.state.views[view].get(\"data\") or"
                   " {}).get(\n"
                   "            \"rules\" if view == \"styles\" else"
                   " \"snippets\") or []\n"
                   "        if not 0 <= idx < len(latest):\n"
                   "            return None\n"
                   "        sel = latest[idx][\"rule_id\" if view == \"styles\""
                   " else \"snippet_id\"]\n"
                   "        editor = self._style_editor if view == \"styles\" \\\n")],
    "M10-MUT17": [(APP,
                   "        try:\n"
                   "            res = v2_normalize.normalize(text, policy,"
                   " context)\n"
                   "        except Exception as e:\n"
                   "            return {\"input\": text, \"error\":"
                   " type(e).__name__, **scope}\n"
                   "        return {\n",
                   "        try:\n"
                   "            res = v2_normalize.normalize(text, policy,"
                   " context)\n"
                   "        except Exception as e:\n"
                   "            return {\"input\": text, \"error\":"
                   " type(e).__name__, **scope}\n"
                   "        self._snip_store.record_hits([e.rule_id for e in"
                   " res.edits\n"
                   "                                      if e.cls =="
                   " \"snippet\" and e.rule_id])\n"
                   "        self._vocab.record_hits([e.rule_id for e in"
                   " res.edits\n"
                   "                                 if e.cls =="
                   " \"vocabulary\" and e.rule_id])\n"
                   "        return {\n")],
    "M10-MUT18": [(APP,
                   "                and key[0] == paths \\\n"
                   "                and key[1] == v2_skills.fingerprint(paths):\n",
                   "                and key[0] == paths:\n")],
    "M10-MUT19": [(SKILLS,
                   "        if link:\n"
                   "            # A child link is never followed: planted or"
                   " swapped, its\n"
                   "            # target lies outside the authority this"
                   " directory grants.\n"
                   "            refused += 1\n"
                   "            continue\n"
                   "        if not is_dir:\n"
                   "            continue\n",
                   "        if not is_dir and not link:\n"
                   "            continue\n"),
                  (SKILLS,
                   "    return os.open(name, os.O_RDONLY | _O_DIRECTORY |"
                   " _O_NOFOLLOW\n"
                   "                   | _O_CLOEXEC, dir_fd=parent_fd)\n",
                   "    return os.open(name, os.O_RDONLY | _O_DIRECTORY\n"
                   "                   | _O_CLOEXEC, dir_fd=parent_fd)\n")],
    "M10-MUT20": [(APP,
                   "            skills = dict(registry.policy_skills)\n"
                   "            prov = dict(registry.policy_provenance)\n",
                   "            skills = dict(registry.policy_skills)\n"
                   "            prov = dict(registry.policy_provenance)\n"
                   "            m10[\"skills\"] = registry\n"
                   "            m10[\"skill_records\"] = list(registry.records)\n")],
    "M10-MUT21": [(APP,
                   "                    self._job[\"m10\"] = self._m10_degraded(\n"
                   "                        override, type(e).__name__)\n",
                   "                    self._job[\"m10\"] = self._m10_degraded(\n"
                   "                        None, type(e).__name__)\n")],
    "M10-MUT22": [(PSTORE,
                   "            raise OutcomeUnknownError(action, entity_id)"
                   " from None\n",
                   "            raise RuntimeError(\"write failed\") from None\n"),
                  (SSTORE,
                   "            raise OutcomeUnknownError(action, entity_id)"
                   " from None\n",
                   "            raise RuntimeError(\"write failed\") from None\n")],
    "M10-MUT23": [(HUB,
                   "        diff = {k: v for k, v in form.items()\n"
                   "                if v != editor[\"baseline\"].get(k)}\n",
                   "        diff = dict(form)\n"),
                  (HUB,
                   "            svc.set_enabled(editor[\"id\"], not"
                   " row.get(\"enabled\", True),\n"
                   "                            expected_revision="
                   "row.get(\"revision\"))\n",
                   "            svc.set_enabled(editor[\"id\"], not"
                   " row.get(\"enabled\", True))\n")],
    "M10-MUT24": [(BENCH,
                   "        work_valid = all(v[\"valid\"] for v in"
                   " validity.values())\n",
                   "        work_valid = True\n")],
    "M10-MUT25": [(SNIP,
                   "                conflicts.append(MappingProxyType({\n"
                   "                    \"trigger\": trig,\n"
                   "                    \"snippets\": tuple(sorted(c.snippet_id\n"
                   "                                             for c in"
                   " cands)),\n"
                   "                    \"reason\": \"duplicate_trigger\",\n"
                   "                }))\n",
                   "                conflicts.append({\n"
                   "                    \"trigger\": trig,\n"
                   "                    \"snippets\": sorted(c.snippet_id\n"
                   "                                       for c in cands),\n"
                   "                    \"reason\": \"duplicate_trigger\",\n"
                   "                })\n"),
                  (SNIP,
                   "        _set(self, \"conflicts\", tuple(conflicts))\n",
                   "        _set(self, \"conflicts\", conflicts)\n"),
                  (SNIP,
                   "        return [{\"trigger\": c[\"trigger\"], \"snippets\":"
                   " list(c[\"snippets\"]),\n"
                   "                 \"reason\": c[\"reason\"]} for c in"
                   " self.conflicts]\n",
                   "        return self.conflicts\n")],
    "M10-MUT26": [(HUB,
                   "        pane.setAutoresizesSubviews_(False)\n"
                   "        pane.setFrame_(self.content.bounds())\n"
                   "        pane.setAutoresizingMask_(18)  # width + height"
                   " flexible\n", "")],
}

# MUT26's killers: the passive native cases (the only observers of a
# pane's geometry; the app is never activated).
NATIVE_KILLERS = {"M10-MUT26": [
    "native:n01_every_input_is_hittable_in_both_panes",
    "native:n02p_click_focus_typing_and_popup_while_inactive"]}


def mutants():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    out = []
    for m in corpus["mutations"]:
        found = set(m["related_findings"])
        killers = sorted(c["id"] for c in corpus["cases"]
                         if found & set(c["related_findings"])
                         and c["id"] not in RECORD_CASES)
        if m["id"] in NATIVE_KILLERS:
            killers = NATIVE_KILLERS[m["id"]]
        out.append({"id": m["id"], "name": m["change"],
                    "findings": m["related_findings"],
                    "edits": EDITS.get(m["id"], []), "killers": killers})
    return out


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


def _norm(status):
    return {"pass": "PASS", "fail": "FAIL", "error": "ERROR",
            "not_run": "NOT_RUN"}.get(status, status)


def run_killers(root, killers, timeout=1200):
    cases, details, imported = {}, {}, set()
    corpus_ids = [k for k in killers if not k.startswith("native:")]
    native = [k.split(":", 1)[1] for k in killers if k.startswith("native:")]
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
    if native:
        out = root / "mut_native.json"
        cmd = [str(PY), ISOLATED, NATIVE, "--json", str(out)]
        try:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}
        if not out.exists():
            return {"error": f"no native result (exit {p.returncode})",
                    "stderr": p.stderr[-400:]}
        d = json.loads(out.read_text())
        out.unlink()
        imported.add(d.get("localflow_imported_from_root"))
        for r in d["results"]:
            if r["case"] in native:
                key = f"native:{r['case']}"
                cases[key] = _norm(r["status"])
                if r["status"] != "pass":
                    details[key] = (r.get("detail") or "")[:300]
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
           "related_findings": m["findings"],
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
    print(f"{rec['outcome']:14} {m['id']} {m['name'][:60]}"
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
    work = pathlib.Path(tempfile.mkdtemp(prefix="m10-mut-"))
    results = []
    try:
        base = work / "control"
        base.mkdir()
        head = export(base)
        killers = sorted({k for m in todo for k in m["killers"]})
        t0 = time.monotonic()
        control = run_killers(base, killers, timeout=2400)
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
        # Only this run's own temporary tree is removed.
        shutil.rmtree(work, ignore_errors=True)
    tally = {}
    for r in results:
        tally[r["outcome"]] = tally.get(r["outcome"], 0) + 1
    print(json.dumps(tally))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            "tool": "scripts/v2/m10_mutation_check.py",
            "runner": RUNNER, "native_suite": NATIVE, "code_sha": head,
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "killer_rule": "every corpus case sharing a related finding,"
                           " minus " + ", ".join(sorted(RECORD_CASES))
                           + "; MUT26: passive native pane cases",
            "control": control, "summary": tally, "results": results},
            indent=1) + "\n")
    return 0 if all(r["outcome"] == "killed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
