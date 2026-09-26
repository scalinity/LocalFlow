"""Reviewer mutation driver (scratch-only). Applies ONE production mutation
in a fresh subprocess BEFORE the evidence tool imports the code, then runs:
  corpus  = tests/v2/vocabulary/m05_corpus_runner.py (output -> scratch)
  domain  = tests/v2/vocabulary/test_m05_remediation.py
  app     = tests/v2/vocabulary/test_m05_remediation_app.py
A mutation SURVIVES a tool when that tool still exits 0.
Nothing is written inside the worktree (PYTHONDONTWRITEBYTECODE=1, outputs in
scratch)."""
import json, os, subprocess, sys, pathlib
import os as _os
W = _os.environ.get('M05_CODE', "/tmp/claude-0/-home-user-LocalFlow/60feaa92-3367-5b00-af84-78a53bb5703a/scratchpad/review_fp")
S = pathlib.Path(__file__).resolve().parent
PY = "/home/user/LocalFlow/.venv/bin/python"
TOOLS = {
    "corpus": (W + "/tests/v2/vocabulary/m05_corpus_runner.py", ["--quiet", "--output"]),
    "domain": (W + "/tests/v2/vocabulary/test_m05_remediation.py", []),
    "app": (W + "/tests/v2/vocabulary/test_m05_remediation_app.py", []),
}

def src_mutation(module, func, old, new, cls=None):
    """Re-define one function from its own source with a textual change."""
    return (
        "import inspect, textwrap, importlib\n"
        f"_m = importlib.import_module({module!r})\n"
        f"_owner = getattr(_m, {cls!r}) if {cls!r} else _m\n"
        f"_f = getattr(_owner, {func!r})\n"
        "_f = getattr(_f, '__func__', _f)\n"
        "_src = textwrap.dedent(inspect.getsource(_f))\n"
        f"assert {old!r} in _src, 'mutation anchor missing'\n"
        f"_src = _src.replace({old!r}, {new!r}, 1)\n"
        "_ns = {}\n"
        "exec(compile(_src, '<mut>', 'exec'), _m.__dict__, _ns)\n"
        f"setattr(_owner, {func!r}, _ns[{func!r}])\n")

MUTATIONS = {
    "control_unmodified": "",
    # claim vs proposal: equal-length tie no longer broken by start
    "claim_tie_ignored": src_mutation(
        "localflow.v2.normalize.syntax", "grammar_vocabulary",
        "if any(best[k] is not None and best[k] < key",
        "if any(best[k] is not None and best[k][0] < key[0]"),
    # hint-set identity no longer binds term scores
    "score_not_in_hint_id": src_mutation(
        "localflow.v2.vocabulary", "_hint_set_id",
        '"terms": [t.to_json() for t in terms],',
        '"terms": [{k: v for k, v in t.to_json().items() if k != "score"} for t in terms],'),
    # snapshot revision no longer depends on the scope it was filtered for
    "revision_scope_blind": src_mutation(
        "localflow.v2.vocabulary", "_revision",
        "self.scope_ctx.to_json()", "{}", cls="VocabularySnapshot"),
    # partial work: vocabulary proposals starting beyond char 60 are dropped
    "partial_edits_after_60": (
        "import localflow.v2.normalize.syntax as s\n"
        "_r = s.grammar_vocabulary\n"
        "def _g(host):\n"
        "    for p in _r(host):\n"
        "        if p.span.start < 60:\n"
        "            yield p\n"
        "s.grammar_vocabulary = _g\n"),
    # applied-rule manifest records the whole in-scope dictionary
    "applied_rules_unbounded": src_mutation(
        "localflow.v2.training", "on_normalization_result",
        "applied = sorted(set(term_ids) | set(skill_ids))",
        "applied = sorted({e.entry_id for e in vocab_snapshot.entries}) if (term_ids or skill_ids) else []",
        cls="EvidenceCollector"),
    # usage: every applied rule counted once per OCCURRENCE instead of per job
    "hits_per_occurrence": src_mutation(
        "localflow.v2.vocabulary_store", "record_hits",
        "uniq = sorted(set(entry_ids))", "uniq = list(entry_ids)",
        cls="VocabularyStore"),
    # sandbox never reports a would-be-masked suggestion
    "sandbox_drops_masked": src_mutation(
        "localflow.v2.vocabulary", "sandbox_phrase",
        "if not hits and any(", "if False and any("),
    # qualification ignores the runtime component
    "qualify_ignores_runtime": src_mutation(
        "localflow.v2.capabilities", "biasing_qualified",
        '"runtime": manifest.get("runtime")}', '"runtime": ident.get("runtime")}'),
    # import identity: alias ORDER becomes identity again (AUDIT-10 revert)
    "alias_order_identity": src_mutation(
        "localflow.v2.vocabulary_store", "_alias_identity",
        "return sorted((a.alias.casefold()", "return list((a.alias.casefold()"),
}

def run(name, tool):
    target, extra = TOOLS[tool]
    out = S / f"mut_{name}_{tool}.json"
    argv = [target] + (extra + [str(out)] if extra else [])
    code = ("import sys; sys.dont_write_bytecode=True\n"
            f"sys.path.insert(0, {W!r}); sys.path.insert(0, {W + '/tests/v2/lifecycle'!r})\n"
            + MUTATIONS[name] +
            f"import runpy; sys.argv={argv!r}\n"
            f"runpy.run_path({target!r}, run_name='__main__')\n")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([PY, "-c", code], cwd=str(S), capture_output=True,
                       text=True, timeout=1800, env=env)
    detail = ""
    if tool == "corpus":
        try:
            d = json.loads(out.read_text())
            fails = [r["case_id"] for r in d["results"] if r["status"] in ("fail", "not_run")]
            detail = f"failed={len(fails)} {fails[:8]}"
        except Exception as e:
            detail = f"no result ({type(e).__name__}) {p.stderr[-300:]}"
    else:
        tail = [l for l in (p.stdout + p.stderr).splitlines() if l.startswith("FAIL") or "passed" in l or "FAILED" in l or "Error" in l]
        detail = " | ".join(tail[-4:])[:600]
    return p.returncode, detail

if __name__ == "__main__":
    names = sys.argv[1].split(",") if len(sys.argv) > 1 else list(MUTATIONS)
    tools = sys.argv[2].split(",") if len(sys.argv) > 2 else list(TOOLS)
    summary = {}
    for n in names:
        summary[n] = {}
        for t in tools:
            rc, det = run(n, t)
            summary[n][t] = {"exit": rc, "survived": rc == 0 and n != "control_unmodified", "detail": det}
            print(f"{n:28s} {t:7s} exit={rc} {det}", flush=True)
    (S / "mutdrv_summary.json").write_text(json.dumps(summary, indent=1))
