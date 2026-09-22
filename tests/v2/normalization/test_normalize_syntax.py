"""EV-06 / M04: spoken-syntax normalization over the 60 owning fixtures.

Covers M04-AC02 (literal and non-command counterexamples stay
unconverted), AC03 (idempotence, with the documented escape corner),
AC04 (no parser path invokes a shell, sends Enter or executes a skill),
AC05 (rejected/ambiguous proposals retained) and AC06 (short/literal
command controls cannot convert ordinary slash prose into a registered
token).

Run: .venv/bin/python tests/v2/normalization/test_normalize_syntax.py
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
    preview_phrase,
)

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = json.loads((HERE / "fixtures_syntax.json").read_text())
PKG = pathlib.Path(
    __file__).resolve().parents[3] / "localflow" / "v2" / "normalize"


def _policy_for(ctx):
    return NormalizationPolicy(
        locale=ctx.get("locale", "en-US"),
        profile=ctx.get("profile", "technical"),
        registered_skills=ctx.get("registered_skills"))


def _snap_for(ctx):
    if ctx.get("identifiers"):
        return ContextSnapshot(identifiers=ctx["identifiers"])
    return None


def test_fixture_counts():
    assert len(FIXTURES["cases"]) == 60, \
        f"expected exactly 60 syntax fixtures, got {len(FIXTURES['cases'])}"
    ids = [c["case_id"] for c in FIXTURES["cases"]]
    assert len(set(ids)) == 60, "duplicate case ids"
    print("ok  fixture set: exactly 60 unique syntax cases")


def test_all_fixtures_exact():
    failures = []
    for case in FIXTURES["cases"]:
        pol = _policy_for(case["context"])
        res = normalize(case["input_text"], pol, _snap_for(case["context"]))
        if res.text != case["expected_text"]:
            failures.append((case["case_id"], case["input_text"],
                             res.text, case["expected_text"]))
    assert not failures, failures
    n_neg = sum(1 for c in FIXTURES["cases"]
                if "negative_control" in c.get("tags", []))
    print(f"ok  all 60 syntax fixtures exact "
          f"({n_neg} negative controls hold)")


def test_literal_and_noncommand_stay_unconverted():
    """M04-AC02: explicit literal and non-command counterexamples keep
    their words, with the unconverted proposal retained for review."""
    pol = _policy_for({"registered_skills": {"brainstorm": "brainstorm"}})
    for text in ("slash the budget", "the slash character",
                 "a dash of salt", "the period of adjustment"):
        res = normalize(text, pol)
        assert res.text == text, (text, res.text)
    res = normalize("slash the budget", pol)
    reviews = [r for r in res.rejected if r.reason == "unknown_skill"]
    assert reviews, "unknown skill surfaces as a review suggestion"
    assert not res.edits
    print("ok  AC02: literal/non-command counterexamples unconverted, "
          "review suggestion retained")


def test_idempotence_all_fixtures():
    """M04-AC03 on the syntax stratum (LF-SYN-003 declares the corner)."""
    failures = []
    corners = 0
    for case in FIXTURES["cases"]:
        if case.get("idempotence_expected") is False:
            corners += 1
            continue
        pol = _policy_for(case["context"])
        first = normalize(case["input_text"], pol,
                          _snap_for(case["context"]))
        second = normalize(first.text, pol, _snap_for(case["context"]))
        if second.text != first.text or second.edits:
            failures.append((case["case_id"], first.text, second.text))
    assert not failures, failures
    print(f"ok  idempotence on all syntax fixtures ({corners} documented "
          "corner excluded, honestly reported)")


def test_escape_corner_reported_honestly():
    """LF-SYN-003: a bare command word emitted by an escape re-matches
    its command grammar on a second pass. is_idempotent() must report
    False — never silently claim stability."""
    pol = NormalizationPolicy()
    res = normalize("write the word comma", pol)
    assert res.text == "comma"
    assert res.is_idempotent(pol) is False
    res2 = normalize("write the word slash", pol)
    assert res2.text == "slash" and res2.is_idempotent(pol) is True
    print("ok  escape corner: is_idempotent() reports False honestly")


def test_no_shell_no_enter_no_skill_execution():
    """M04-AC04: the parser package is pure text — no process spawning,
    dynamic execution, keyboard/event APIs, network or file-handle
    escapes. Static scan of every module in the package plus an
    import-boundary check."""
    banned = ("subprocess", "os.system", "os.popen", "popen", "system(",
              "eval(", "exec(", "__import__", "importlib", "ctypes",
              "os.exec", "os.spawn", "os.fork", "pty",
              "from subprocess", "from os import",
              "CGEvent", "keyPost", "keyCode", "CoreGraphics",
              "Quartz", "launch", "open(", "urllib", "requests",
              "socket", "http")
    files = sorted(PKG.glob("*.py"))
    # A path typo must never silently turn this scan into a no-op: the
    # expected modules must actually be present and scanned.
    assert {p.name for p in files} >= {
        "__init__.py", "engine.py", "numbers.py", "syntax.py",
        "policy.py", "scoring.py", "span_types.py"}, files
    for py in files:
        src = py.read_text()
        for tok in banned:
            # Word-boundary match: "pty" must not hit "empty", etc.
            pattern = r"\b" + re.escape(tok)
            assert not re.search(pattern, src), \
                f"{py.name} contains {tok!r}"
    import localflow.v2.normalize as n_pkg
    banned_mods = ("subprocess", "socket", "urllib.request", "requests",
                   "ctypes", "importlib")
    for mod in (n_pkg, n_pkg.engine, n_pkg.policy, n_pkg.numbers,
                n_pkg.syntax, n_pkg.scoring, n_pkg.span_types):
        refs = {k: getattr(v, "__name__", None)
                for k, v in vars(mod).items()
                if getattr(v, "__name__", None) in banned_mods}
        assert not refs, (mod.__name__, refs)
    # Behavior proof: emitting a command does nothing but produce text.
    skills = NormalizationPolicy(
        registered_skills={"brainstorm": "brainstorm"})
    res = normalize("slash brainstorm", skills)
    assert res.text == "/brainstorm" and len(res.edits) == 1
    assert res.edits[0].cls == "skill" and not res.rejected
    print("ok  AC04: no shell/Enter/skill-execution path (static + runtime)")


def test_slash_prose_never_converts():
    """M04-AC06: registered tokens convert only on exact spelling;
    near-misses and prose never produce a token."""
    pol = NormalizationPolicy(
        registered_skills={"brainstorm": "brainstorm",
                           "code review": "code-review"})
    for text in ("slash the budget", "slash brainstorms",
                 "budget slash spending", "slash brainstorming ideas",
                 "we should slash costs and brainstorm"):
        res = normalize(text, pol)
        assert res.text == text, (text, res.text)
        assert not [e for e in res.edits if e.cls == "skill"]
    print("ok  AC06: slash prose and near-misses never convert")


def test_rejected_proposals_retained():
    """M04-AC05: rejected and ambiguous proposals are retained with
    reasons — the ledger is evidence, not just the final string."""
    pol = NormalizationPolicy()
    res = normalize("two sixty dot one sixty eight dot one dot ten", pol)
    reasons = {r.reason for r in res.rejected}
    assert "invalid_octet" in reasons, reasons
    assert res.text == "two sixty dot one sixty eight dot one dot ten"
    res = normalize("march thirty two", pol)
    assert any(r.reason == "invalid_day" for r in res.rejected)
    print("ok  AC05: rejected/flagged proposals retained with reasons")


def test_symbol_noun_compounds_stay_prose():
    """Review regression (C2): 'period' inside noun compounds is a noun,
    never the punctuation command."""
    pol = NormalizationPolicy()
    for text in ("there is a grace period here", "the trial period ended",
                 "notice period", "a cooling period helps",
                 "the question is period or no period"):
        res = normalize(text, pol)
        assert res.text == text, (text, res.text)
    # The spoken command still works.
    assert normalize("stop period", pol).text == "stop."
    assert normalize("hello comma world period", pol).text == \
        "hello, world."
    print("ok  'X period' noun compounds stay prose; command still fires")


def test_preview_phrase_api():
    """M04 task 5: the test-phrase API exposes per-edit before/after
    for the future Dictionary/Developer UI."""
    pv = preview_phrase("hello comma world")
    assert pv["changed"] and pv["output"] == "hello, world"
    assert pv["edits"][0]["before"] == "comma"
    assert pv["edits"][0]["after"] == ","
    assert pv["idempotent"] is True
    pv = preview_phrase("nothing to change here")
    assert not pv["changed"] and pv["edits"] == []
    print("ok  preview_phrase: per-edit before/after + idempotence flag")


def test_protected_spans_recorded():
    pol = NormalizationPolicy()
    res = normalize('He said "new line" politely', pol)
    assert res.text == 'He said "new line" politely'
    kinds = {p.kind for p in res.protected}
    assert "quoted" in kinds, kinds
    res = normalize("write the words twelve thousand", pol)
    kinds = {p.kind for p in res.protected}
    assert "literal_escape" in kinds, kinds
    print("ok  protected spans recorded (quoted, literal_escape)")


def main():
    test_fixture_counts()
    test_all_fixtures_exact()
    test_literal_and_noncommand_stay_unconverted()
    test_idempotence_all_fixtures()
    test_escape_corner_reported_honestly()
    test_no_shell_no_enter_no_skill_execution()
    test_slash_prose_never_converts()
    test_rejected_proposals_retained()
    test_symbol_noun_compounds_stay_prose()
    test_preview_phrase_api()
    test_protected_spans_recorded()
    print("all syntax normalization tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
