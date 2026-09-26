"""M05 remediation: can a broken implementation earn a green corpus run?

Applies one production MUTATION at a time (in a subprocess, before the
corpus runner imports the code), runs the full audit-corpus runner
(tests/v2/vocabulary/m05_corpus_runner.py) and records how many cases
fail. A mutation SURVIVES when every case still passes — the acceptance
oracle would then be vacuous for that defect. The unmodified tree is
the control (it must be green).

    .venv/bin/python scripts/v2/m05_mutation_check.py --output PATH
"""

import argparse
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "v2" / "vocabulary" / "m05_corpus_runner.py"

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
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--only")
    args = ap.parse_args()
    out = {"schema_version": 1, "tool": "scripts/v2/m05_mutation_check.py",
           "code_sha": subprocess.run(["git", "-C", str(ROOT), "rev-parse",
                                       "HEAD"], capture_output=True,
                                      text=True).stdout.strip(),
           "python": sys.version.split()[0], "mutations": {}}
    names = list(MUTATIONS)
    if args.only:
        names = [n for n in names if n in args.only.split(",")]
    for name in names:
        res_path = ROOT / f".m05_mut_{name}.json"
        code = (f"import sys, runpy\nsys.path.insert(0, {str(ROOT)!r})\n"
                + MUTATIONS[name]
                + f"sys.argv=[{str(RUNNER)!r}, '--quiet', '--output',"
                f" {str(res_path)!r}, '--label', {name!r}]\n"
                f"runpy.run_path({str(RUNNER)!r}, run_name='__main__')\n")
        t0 = time.monotonic()
        p = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=3600)
        try:
            res = json.loads(res_path.read_text())
            res_path.unlink()
            counts = res["counts"]
            failed = sorted(r["case_id"] for r in res["results"]
                            if r["status"] == "fail")
        except Exception as e:
            counts, failed = {"error": type(e).__name__}, []
        out["mutations"][name] = {
            "exit": p.returncode, "counts": counts,
            "failed_cases": failed[:40], "failed_total": len(failed),
            "survived": name != "control_unmodified" and not failed,
            "seconds": round(time.monotonic() - t0, 1)}
        print(f"{name}: exit={p.returncode} failed={len(failed)}"
              f" survived={out['mutations'][name]['survived']}", flush=True)
    ctl = out["mutations"].get("control_unmodified")
    out["control_green"] = bool(ctl) and ctl["failed_total"] == 0
    out["survivors"] = [n for n, m in out["mutations"].items()
                        if m["survived"]]
    pathlib.Path(args.output).write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
