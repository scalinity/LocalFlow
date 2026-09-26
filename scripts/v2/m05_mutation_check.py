"""M05 remediation: can a broken implementation earn green evidence?

Applies one production MUTATION at a time (in a fresh subprocess, before
the tool imports the code) and runs every evidence tool under it:

  corpus  — tests/v2/vocabulary/m05_corpus_runner.py (226 audit cases)
  domain  — tests/v2/vocabulary/test_m05_remediation.py
  app     — tests/v2/vocabulary/test_m05_remediation_app.py (shims)
  review  — tests/v2/vocabulary/test_m05_review_round.py (shims)

A tool KILLS a mutation when it exits non-zero (the corpus also when any
case fails or its result file is missing). A mutation SURVIVES only when
it provably applied and every tool stayed green — the evidence would be
vacuous for that defect. Each source mutation is first applied alone:
an anchor that no longer matches is a harness ERROR, never a kill. The
unmodified tree is the control: every tool must exit 0 with a complete
result, or ``control_green`` is false (review R10).

    .venv/bin/python scripts/v2/m05_mutation_check.py --output PATH
        [--only a,b] [--tools corpus,domain,app,review]
"""

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
VOC = ROOT / "tests" / "v2" / "vocabulary"
SHIM = ROOT / "tests" / "v2" / "lifecycle" / "run_with_shims.py"
TOOLS = {
    "corpus": VOC / "m05_corpus_runner.py",
    "domain": VOC / "test_m05_remediation.py",
    "app": VOC / "test_m05_remediation_app.py",
    "review": VOC / "test_m05_review_round.py",
}


def src_mutation(module, func, old, new, cls=None):
    """Re-define one function from its own source with a textual change
    (the anchor must match exactly once, or the mutation is an error)."""
    return (
        "import inspect, textwrap, importlib\n"
        f"_m = importlib.import_module({module!r})\n"
        f"_owner = getattr(_m, {cls!r}) if {cls!r} else _m\n"
        f"_f = getattr(_owner, {func!r})\n"
        "_f = getattr(_f, '__func__', _f)\n"
        "_src = textwrap.dedent(inspect.getsource(_f))\n"
        f"assert _src.count({old!r}) == 1, 'MUTATION_ANCHOR_MISSING'\n"
        f"_src = _src.replace({old!r}, {new!r}, 1)\n"
        "_ns = {}\n"
        "exec(compile(_src, '<mutation>', 'exec'), _m.__dict__, _ns)\n"
        "_new = _ns[" + repr(func) + "]\n"
        + (f"setattr(_owner, {func!r}, staticmethod(_new) if isinstance("
           f"inspect.getattr_static(_owner, {func!r}), staticmethod)"
           f" else _new)\n" if cls else
           f"setattr(_owner, {func!r}, _new)\n"))


MUTATIONS = {
    "control_unmodified": "",
    "identity_matcher": (
        "import localflow.v2.normalize.syntax as s\n"
        "s.grammar_vocabulary = lambda host: iter(())\n"),
    "skip_every_fourth_edit": (
        "import localflow.v2.normalize.syntax as s\n"
        "_r = s.grammar_vocabulary\n"
        "def _g(host):\n"
        "    for i, p in enumerate(_r(host)):\n"
        "        if i % 4 != 3:\n"
        "            yield p\n"
        "s.grammar_vocabulary = _g\n"),
    "partial_edits_after_60": (
        "import localflow.v2.normalize.syntax as s\n"
        "_r = s.grammar_vocabulary\n"
        "def _g(host):\n"
        "    for p in _r(host):\n"
        "        if p.span.start < 60:\n"
        "            yield p\n"
        "s.grammar_vocabulary = _g\n"),
    "remove_scoped_contenders": (
        "import localflow.v2.vocabulary as V\n"
        "V.VocabularyEntry.scope_matches = lambda self, ctx:"
        " self.scope_kind == 'global'\n"),
    "rank_tie_break_changed": (
        "import localflow.v2.vocabulary as V\n"
        "V.VocabularySnapshot._rank_key = staticmethod(lambda e: ("
        "1 if e.pinned else 0, V.SCOPE_PRECEDENCE[e.scope_kind],"
        " e.last_used_utc or '', e.usage_count, -e.priority))\n"),
    "drop_rule_ids": (
        "import dataclasses\n"
        "import localflow.v2.normalize.syntax as s\n"
        "_r = s.grammar_vocabulary\n"
        "def _g(host):\n"
        "    for p in _r(host):\n"
        "        yield dataclasses.replace(p, rule_id=None)\n"
        "s.grammar_vocabulary = _g\n"),
    "drop_skill_provenance": (
        # The engine iterates ALL_SYNTAX_GRAMMARS (captured functions),
        # so the tuple entry itself is replaced.
        "import localflow.v2.normalize.syntax as s\n"
        "_r = s.grammar_skills\n"
        "import dataclasses\n"
        "def _g(host):\n"
        "    for p in _r(host):\n"
        "        yield dataclasses.replace(p, rule_id=None)\n"
        "s.ALL_SYNTAX_GRAMMARS = tuple(_g if f is _r else f\n"
        "                              for f in s.ALL_SYNTAX_GRAMMARS)\n"),
    "scope_blind_selector": (
        "import localflow.v2.vocabulary as V\n"
        "_r = V.RelevantVocabularySelector.select\n"
        "def _sel(self, snap, scope_ctx=None, **kw):\n"
        "    return _r(self, V.VocabularySnapshot(snap.entries, None),"
        " None, **kw)\n"
        "V.RelevantVocabularySelector.select = _sel\n"),
    "no_barrier_check": (
        "import localflow.v2.normalize.engine as E\n"
        "E.MatchHost.connected = lambda self, i, j: True\n"),
    # Independent review round (R8): mutations that survived the
    # first-pass tools, re-anchored on the final code.
    "claim_tie_ignored": src_mutation(
        "localflow.v2.normalize.syntax", "grammar_vocabulary",
        "cands = [((-strength, span.start, 0), i, j)",
        "cands = [((-strength, span.start, 2), i, j)"),
    "claim_strength_is_occurrence": src_mutation(
        "localflow.v2.normalize.syntax", "grammar_vocabulary",
        "max(strength, span.end - span.start))",
        "span.end - span.start)"),
    "score_not_in_hint_id": (
        "import localflow.v2.vocabulary as V\n"
        "_r = V._hint_set_id\n"
        "class _T:\n"
        "    def __init__(self, t): self.t = t\n"
        "    def to_json(self):\n"
        "        d = self.t.to_json(); d.pop('score'); return d\n"
        "def _id(a, b, c, terms, *rest, **kw):\n"
        "    return _r(a, b, c, [_T(t) for t in terms], *rest, **kw)\n"
        "V._hint_set_id = _id\n"),
    "revision_scope_blind": src_mutation(
        "localflow.v2.vocabulary", "_revision",
        "self.scope_ctx.to_json()", "{}", cls="VocabularySnapshot"),
    "applied_rules_unbounded": src_mutation(
        "localflow.v2.training", "on_normalization_result",
        "applied = sorted(set(term_ids) | set(skill_ids))",
        "applied = sorted({e.entry_id for e in vocab_snapshot.entries})"
        " if (term_ids or skill_ids) else []", cls="EvidenceCollector"),
    "hits_per_occurrence": src_mutation(
        "localflow.v2.vocabulary_store", "record_hits",
        "uniq = sorted(set(entry_ids))", "uniq = list(entry_ids)",
        cls="VocabularyStore"),
    "sandbox_drops_masked": src_mutation(
        "localflow.v2.vocabulary", "sandbox_phrase",
        "if not hits and any(", "if False and any("),
    "qualify_ignores_runtime": src_mutation(
        "localflow.v2.capabilities", "biasing_qualified",
        '"runtime": manifest.get("runtime")}',
        '"runtime": ident.get("runtime")}'),
    "alias_order_identity": src_mutation(
        "localflow.v2.vocabulary_store", "_alias_identity",
        "return sorted((a.alias.casefold()",
        "return list((a.alias.casefold()"),
}


def _prelude(name):
    return ("import sys\nsys.dont_write_bytecode = True\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            f"sys.path.insert(0, {str(ROOT / 'tests/v2/lifecycle')!r})\n"
            f"sys.path.insert(0, {str(VOC)!r})\n"
            "import native_shims\nnative_shims.install()\n"
            + MUTATIONS[name])


def applies(name):
    """(ok, detail): the mutation code runs alone without error."""
    p = subprocess.run([sys.executable, "-c", _prelude(name)],
                       cwd=str(ROOT), capture_output=True, text=True,
                       timeout=300)
    tail = (p.stderr.strip().splitlines() or [""])[-1]
    return p.returncode == 0, tail[:200]


def run_tool(name, tool, scratch):
    target = TOOLS[tool]
    res_path = scratch / f"{name}_{tool}.json"
    argv = [str(target)] + (["--quiet", "--output", str(res_path),
                             "--label", name] if tool == "corpus" else [])
    code = (_prelude(name)
            + f"import runpy\nsys.argv = {argv!r}\n"
            f"runpy.run_path({str(target)!r}, run_name='__main__')\n")
    p = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=3600)
    out = {"exit": p.returncode}
    if tool == "corpus":
        try:
            res = json.loads(res_path.read_text())
            failed = sorted(r["case_id"] for r in res["results"]
                            if r["status"] == "fail")
            out.update(counts=res["counts"], failed_total=len(failed),
                       failed_cases=failed[:20], complete=True)
        except Exception as e:
            out.update(complete=False, error=type(e).__name__)
        out["killed"] = (p.returncode != 0 or not out["complete"]
                         or out.get("failed_total", 0) > 0)
    else:
        lines = (p.stdout + p.stderr).splitlines()
        out["fail_lines"] = [ln[:160] for ln in lines
                             if ln.startswith("FAIL")][:8]
        out["last_line"] = (lines or [""])[-1][:200]
        out["complete"] = any("tests passed" in ln or "FAILED" in ln
                              for ln in lines)
        out["killed"] = p.returncode != 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--only")
    ap.add_argument("--tools", default=",".join(TOOLS))
    ap.add_argument("--jobs", type=int, default=4,
                    help="parallel tool runs (outcomes never depend on"
                         " timing: the benchmark test uses a scripted"
                         " clock)")
    args = ap.parse_args()
    tools = [t for t in args.tools.split(",") if t in TOOLS]
    out = {"schema_version": 2, "tool": "scripts/v2/m05_mutation_check.py",
           "code_sha": subprocess.run(["git", "-C", str(ROOT), "rev-parse",
                                       "HEAD"], capture_output=True,
                                      text=True).stdout.strip(),
           "code_root_modified": bool(subprocess.run(
               ["git", "-C", str(ROOT), "status", "--porcelain",
                "--untracked-files=no"], capture_output=True,
               text=True).stdout.strip()),
           "python": sys.version.split()[0], "tools": tools,
           "mutations": {}}
    names = list(MUTATIONS)
    if args.only:
        names = [n for n in names if n in args.only.split(",")]
    import concurrent.futures as cf
    with tempfile.TemporaryDirectory() as td:
        scratch = pathlib.Path(td)
        applied = {n: applies(n) for n in names}
        tasks = [(n, t) for n in names if applied[n][0] for t in tools]
        t0 = time.monotonic()
        with cf.ThreadPoolExecutor(max(1, args.jobs)) as ex:
            futs = {ex.submit(run_tool, n, t, scratch): (n, t)
                    for n, t in tasks}
            results = {}
            for f in cf.as_completed(futs):
                results[futs[f]] = f.result()
        for name in names:
            ok, detail = applied[name]
            rec = {"applied": ok}
            if not ok:
                rec.update(error=detail, survived=None)
            else:
                rec["tools"] = {t: results[(name, t)] for t in tools}
                killed_by = [t for t, r in rec["tools"].items()
                             if r["killed"]]
                rec["killed_by"] = killed_by
                rec["survived"] = (name != "control_unmodified"
                                   and not killed_by)
            out["mutations"][name] = rec
            print(f"{name}: applied={ok} killed_by="
                  f"{rec.get('killed_by')} survived={rec['survived']}",
                  flush=True)
        out["seconds"] = round(time.monotonic() - t0, 1)
    ctl = out["mutations"].get("control_unmodified")
    out["control_green"] = bool(ctl) and ctl["applied"] and all(
        r["complete"] and not r["killed"] for r in ctl["tools"].values())
    out["errors"] = [n for n, m in out["mutations"].items()
                     if not m["applied"]]
    out["survivors"] = [n for n, m in out["mutations"].items()
                        if m.get("survived")]
    pathlib.Path(args.output).write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"control_green={out['control_green']} survivors={out['survivors']}"
          f" errors={out['errors']}")
    return 0 if out["control_green"] and not out["survivors"] \
        and not out["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
