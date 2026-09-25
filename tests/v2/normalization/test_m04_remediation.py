"""M04 remediation regressions (M04-AUDIT-01..20, parser/policy/oracle
seams). Every test here FAILS on the audited base 1c9d981 and passes on
the repair; each pairs its negative with the canonical positive that
must keep working (a safety fix that disabled a grammar family would
fail the positive half).

Expectations are independent: exact authored strings and typed tuples
computed here with Decimal / int arithmetic — never by calling the
formatter under test. Offsets are Python code points.

Run: .venv/bin/python tests/v2/normalization/test_m04_remediation.py
"""

import io
import json
import pathlib
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)

TECH = NormalizationPolicy()
STD = NormalizationPolicy(profile="standard")


def N(text, pol=TECH, ctx=None):
    return normalize(text, pol, ctx)


def edits_of(res, cls):
    return [e for e in res.edits if e.cls == cls]


def replay_independent(src, res):
    """Right-to-left positional replay with bound/slice checks — no
    parser import."""
    out = src
    prev_start = None
    for e in sorted(res.edits, key=lambda e: e.input_span.start,
                    reverse=True):
        s, t = e.input_span.start, e.input_span.end
        assert 0 <= s <= t <= len(src)
        assert src[s:t] == e.input_text, (src[s:t], e.input_text)
        if prev_start is not None:
            assert t <= prev_start, "overlapping edits"
        prev_start = s
        out = out[:s] + e.output_text + out[t:]
    return out


# ---------------------------------------------------------------------------
# 01 — registered alias vs ordinary slash verb
# ---------------------------------------------------------------------------

def test_01_slash_verb_context_stays_prose():
    pol = NormalizationPolicy(registered_skills={
        "code review": "code-review", "costs": "costs",
        "brainstorm": "brainstorm"})
    for text in ("we should slash code review time", "we should slash costs",
                 "they will slash costs", "to slash code review time",
                 "we don't slash costs", "I slash costs"):
        res = N(text, pol)
        assert res.text == text, (text, res.text)
        assert not edits_of(res, "skill")
        assert any(r.reason == "verb_context" for r in res.rejected), text
    # Positives: explicit command positions still insert the token.
    assert N("slash code review", pol).text == "/code-review"
    assert N("add slash code review to the list", pol).text == \
        "add /code-review to the list"
    assert N("slash code review the PR", pol).text == "/code-review the PR"
    assert N("slash brainstorm ideas for the offsite", pol).text == \
        "/brainstorm ideas for the offsite"
    print("ok  01: slash after a modal/pronoun/'to' stays the verb; "
          "command positions insert the token")


# ---------------------------------------------------------------------------
# 02 — punctuation boundaries
# ---------------------------------------------------------------------------

def test_02_punctuation_is_a_boundary():
    cases = {
        "twelve percent.": "12%.",
        "twelve dollars, please": "$12, please",
        "it costs twelve dollars.": "it costs $12.",
        "twelve percent; then more": "12%; then more",
        "wait five minutes, then go": "wait 5 minutes, then go",
        "twelve percent": "12%",           # NBSP is benign whitespace
        "twelve\tpercent": "12%",               # so is a tab
    }
    for src, want in cases.items():
        res = N(src)
        assert res.text == want, (src, res.text)
        assert replay_independent(src, res) == res.text
    for src, bad in (("twenty, five percent", "25"),
                     ("one hundred. five percent", "105"),
                     ("twenty\nfive percent", "25"),
                     ("two hundred, fifty dollars", "250")):
        res = N(src)
        assert bad not in res.text, (src, res.text)
    res = N("twenty, five percent")
    assert res.text == "twenty, 5%", res.text
    # The punctuation stays OUTSIDE every edit span.
    res = N("twelve percent.")
    e = res.edits[0]
    assert e.input_span.as_pair() == [0, 14] and e.input_text == \
        "twelve percent", e
    print("ok  02: delimiters survive and are never parsed through")


# ---------------------------------------------------------------------------
# 03 — scaled decimals are exact
# ---------------------------------------------------------------------------

def test_03_scaled_decimal_exact():
    for words, digits, scale in (
            ("one point two three four five thousand", "1.2345", 1000),
            ("zero point zero zero zero one thousand", "0.0001", 1000),
            ("two point five five million", "2.55", 10 ** 6),
            ("one point two five thousand", "1.25", 1000),
            ("one point five million", "1.5", 10 ** 6)):
        want = Decimal(digits) * scale
        res = N(words + " dollars")
        e = edits_of(res, "currency")[0]
        assert Decimal(str(e.value)) == want, (words, e.value)
        shown = Decimal(res.text.replace("$", "").replace(",", ""))
        assert shown == want, (words, res.text)
        res = N("minus " + words + " dollars")
        assert Decimal(str(edits_of(res, "currency")[0].value)) == -want
        assert res.text.startswith("$-"), res.text
    assert N("the contract was one point five million dollars").text == \
        "the contract was $1,500,000"
    res = N("one point two three four five thousand percent")
    assert Decimal(str(edits_of(res, "percent")[0].value)) == \
        Decimal("1234.5")
    print("ok  03: scaled decimals render and record the exact amount")


# ---------------------------------------------------------------------------
# 04 — zero multipliers, malformed scales, quantified scales
# ---------------------------------------------------------------------------

def test_04_malformed_and_quantified_scales_whole_literal():
    for text in ("zero hundred dollars", "zero thousand dollars",
                 "one thousand million dollars",
                 "one million million dollars",
                 "one million two million dollars",
                 "a few hundred thousand dollars",
                 "several hundred thousand people",
                 "zero hundred people", "one thousand million percent"):
        res = N(text)
        assert res.text == text, (text, res.text)
        assert any(r.reason in ("malformed_scale", "quantified_scale")
                   for r in res.rejected), text
    for text, want in (("twelve thousand dollars", "$12,000"),
                       ("one hundred and five people", "105 people"),
                       ("two million three thousand dollars",
                        "$2,003,000"),
                       ("about twelve percent", "about 12%"),
                       ("a hundred people", "a 100 people")):
        assert N(text).text == want, (text, N(text).text)
    print("ok  04: zero/repeated/quantified scales stay whole; valid "
          "scales convert")


# ---------------------------------------------------------------------------
# 05 — signs in typed values, port domain
# ---------------------------------------------------------------------------

def test_05_signed_typed_values_and_port_domain():
    res = N("step negative five")
    e = edits_of(res, "anchored_integer")[0]
    assert res.text == "step -5" and e.value == -5, (res.text, e.value)
    for text in ("port negative eighty", "port minus one",
                 "port seventy thousand"):
        res = N(text)
        assert res.text == text, (text, res.text)
        assert not edits_of(res, "port")
        assert any(r.reason == "invalid_port" for r in res.rejected)
    for text, v in (("port eighty", 80), ("port one", 1),
                    ("port sixty five thousand five hundred thirty five",
                     65535)):
        e = edits_of(N(text), "port")[0]
        assert e.value == v, (text, e.value)
    res = N("ten by minus twenty centimeters")
    e = edits_of(res, "dimension")[0]
    assert res.text == "10 × -20 cm" and e.value == "10x-20 cm", e.value
    res = N("minus ten by twenty centimeters")
    assert edits_of(res, "dimension")[0].value == "-10x20 cm"
    assert N("negative twelve percent").edits[0].value == -12
    print("ok  05: every typed value carries its spoken sign; invalid "
          "ports refused")


# ---------------------------------------------------------------------------
# 06 — time ownership
# ---------------------------------------------------------------------------

def test_06_time_needs_evidence():
    for text in ("three fifteen minute breaks", "one twenty minute session",
                 "five thirty people", "one oh five",
                 "for three fifteen minute breaks",
                 "we took three fifteen minute breaks"):
        res = N(text)
        assert not edits_of(res, "time"), (text, res.text)
        assert res.text == text, (text, res.text)
    for text, want in (("at five thirty", "at 5:30"),
                       ("five thirty PM", "5:30 PM"),
                       ("at nine oh five am", "at 9:05 AM"),
                       ("the train leaves at seven forty five",
                        "the train leaves at 7:45"),
                       ("meet at five thirty.", "meet at 5:30.")):
        assert N(text).text == want, (text, N(text).text)
    print("ok  06: count+duration never becomes a clock time; anchored "
          "and meridiem times convert")


# ---------------------------------------------------------------------------
# 07 — modal may, invalid compound ordinals, narrow calendar check
# ---------------------------------------------------------------------------

def test_07_dates_modal_and_invalid_days():
    for text in ("this may first require approval",
                 "we may first need a review",
                 "we march first to the square"):
        res = N(text)
        assert not edits_of(res, "date"), (text, res.text)
        assert res.text == text
    for text in ("March thirty second", "March thirty second deadline",
                 "February thirty first", "April thirty first",
                 "February twenty ninth twenty twenty five"):
        res = N(text)
        assert res.text == text, (text, res.text)
        assert any(r.cls == "date" and r.reason in ("invalid_day",
                                                    "invalid_date")
                   for r in res.rejected), text
    for text, want, val in (
            ("May first", "May 1", "05-01"),
            ("September twenty fifth", "September 25", "09-25"),
            ("deploy on march fourth", "deploy on March 4", "03-04"),
            ("due on may first", "due on May 1", "05-01"),
            ("March thirty first", "March 31", "03-31"),
            ("February twenty ninth", "February 29", "02-29"),
            ("February twenty ninth twenty twenty four",
             "February 29, 2024", "2024-02-29")):
        res = N(text)
        assert res.text == want, (text, res.text)
        assert edits_of(res, "date")[0].value == val
    print("ok  07: modal may / invalid ordinal days stay whole; dates "
          "convert")


# ---------------------------------------------------------------------------
# 08 — maximal structured candidates
# ---------------------------------------------------------------------------

def test_08_structured_chains_owned_whole():
    for text in ("one point twenty six point four",
                 "one dot two dot three dot four dot five",
                 "one dot two dot three", "one dot two",
                 "point five percent", "minus point five percent",
                 "two sixty dot one sixty eight dot one dot ten",
                 "version one point two point",
                 "version one point two thousand is wrong",
                 "five minus three"):
        res = N(text)
        assert res.text == text, (text, res.text)
    for text, want, comps in (
            ("ten dot zero dot zero dot one", "10.0.0.1", [10, 0, 0, 1]),
            ("one ninety two dot one sixty eight dot one dot ten",
             "192.168.1.10", [192, 168, 1, 10])):
        res = N(text)
        assert res.text == want
        assert [int(c) for c in edits_of(res, "ip")[0].value.split(".")] \
            == comps
    res = N("version one point twenty six point four")
    assert res.text == "version 1.26.4"
    assert [int(c) for c in edits_of(res, "version")[0].value.split(".")] \
        == [1, 26, 4]
    assert N("the ratio is one point two six").text == "the ratio is 1.26"
    print("ok  08: invalid/unanchored chains refused whole; IPv4 and "
          "anchored versions convert")


# ---------------------------------------------------------------------------
# 09 — punctuation names as nouns
# ---------------------------------------------------------------------------

def test_09_punctuation_nouns_stay_prose():
    for pol in (TECH, STD):
        for text in ("period drama", "colon cancer", "pipe tobacco",
                     "a question mark", "the forward slash character",
                     "an exclamation mark", "the comma character",
                     "a semicolon separates clauses",
                     "question mark placement matters",
                     "period drama yesterday", "my comma key is broken"):
            res = N(text, pol)
            assert res.text == text, (pol.profile, text, res.text)
    assert N("dash I asked him").text == "dash I asked him"
    for text, want in (("hello comma how are you", "hello, how are you"),
                       ("stop period", "stop."), ("comma", ","),
                       ("really question mark", "really?"),
                       ("hello comma world period", "hello, world."),
                       ("grep dash i pattern files",
                        "grep -i pattern files"),
                       ("cat notes dot txt pipe grep today",
                        "cat notes dot txt | grep today")):
        assert N(text).text == want, (text, N(text).text)
    print("ok  09: determiner/clause-start/pronoun guards; commands fire")


# ---------------------------------------------------------------------------
# 10 — literal escape scope
# ---------------------------------------------------------------------------

def test_10_literal_escape_scope():
    payload = " ".join(["alpha"] * 12 + ["period"])
    res = N("write the phrase " + payload)
    assert res.text == payload, res.text
    long_payload = " ".join(["beta"] * 40 + ["comma", "twelve", "percent"])
    assert N("write the words " + long_payload).text == long_payload
    res = N("write the phrase please write the word comma")
    assert res.text == "please write the word comma", res.text
    assert len(edits_of(res, "literal_escape")) == 1
    # The escape ends at sentence punctuation; after it, commands work.
    assert N("write the words new line. hello comma world").text == \
        "new line. hello, world"
    assert N("write the word slash").text == "slash"
    code = "```\ntwelve percent\n```"
    assert N(code).text == code
    assert N("run `twelve percent` now").text == "run `twelve percent` now"
    print("ok  10: literal payloads protected whole, nested markers are "
          "content, code is protected")


# ---------------------------------------------------------------------------
# 11 — spoken path / email spelling
# ---------------------------------------------------------------------------

def test_11_path_case_and_incomplete_chains():
    assert N("path slash Users slash Ada slash MyProject").text == \
        "/Users/Ada/MyProject"
    for text in ("path slash Users slash Ada slash build2",
                 "path slash etc slash"):
        res = N(text)
        assert res.text == text, (text, res.text)
        assert any(r.reason == "incomplete_path" for r in res.rejected)
    assert N("/Users/Ada/MyProject").text == "/Users/Ada/MyProject"
    assert N("path slash etc slash hosts").text == "/etc/hosts"
    assert N("UserName at example dot com").text == "UserName@example.com"
    assert N("danny at localflow dot dev").text == "danny@localflow.dev"
    print("ok  11: path/email spelling preserved; incomplete chains whole")


# ---------------------------------------------------------------------------
# 12 — deep immutability (isolated interpreter: tables are cached)
# ---------------------------------------------------------------------------

def test_12_policy_deeply_immutable():
    code = r"""
import sys, json
sys.path.insert(0, sys.argv[1])
from localflow.v2.normalize import (NormalizationPolicy, ContextSnapshot,
    normalize, load_profiles)
out = {}
p = NormalizationPolicy()
rev = p.policy_revision
def attempt(label, fn):
    try:
        fn(); out[label] = "accepted"
    except (TypeError, AttributeError):
        out[label] = "refused"
attempt("teens", lambda: p.tables.teens.__setitem__("twelve", 13))
attempt("symbols", lambda: p.profile_table["symbols"].__setitem__("comma", {}))
attempt("guards", lambda: p.profile_table["symbol_guards"]["blocker_prev"].append("x"))
attempt("anchors", lambda: p.profile_table["integer_anchors"].append("y"))
attempt("attr", lambda: setattr(p, "profile", "standard"))
attempt("tables_attr", lambda: setattr(p.tables, "units", {}))
attempt("skills", lambda: p.registered_skills.__setitem__("x", "y"))
cache = load_profiles()
cache["locales"]["en-US"]["teens"]["twelve"] = 13  # a caller's own copy
q = NormalizationPolicy()
out["fresh_after_caller_mutation"] = normalize("twelve percent", q).text
out["same_revision"] = q.policy_revision == rev
out["old_output"] = normalize("twelve percent", p).text
ids = {"user id": "userId"}
c = ContextSnapshot(identifiers=ids)
ids["user id"] = "USER_ID"
out["context_snapshot"] = normalize("the user id field", p, c).text
a = NormalizationPolicy(registered_skills={"a b": "a-b", "c": "c"})
b = NormalizationPolicy(registered_skills={"c": "c", "a b": "a-b"})
out["order_equivalent_revision"] = a.policy_revision == b.policy_revision
out["distinct_semantic_revision"] = NormalizationPolicy(
    profile="standard").policy_revision != rev
print(json.dumps(out))
"""
    r = subprocess.run([sys.executable, "-c", code, str(ROOT)],
                       capture_output=True, text=True, timeout=60)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    for k in ("teens", "symbols", "guards", "anchors", "attr",
              "tables_attr", "skills"):
        assert out[k] == "refused", (k, out)
    assert out["fresh_after_caller_mutation"] == "12%", out
    assert out["same_revision"] and out["old_output"] == "12%", out
    assert out["context_snapshot"] == "the userId field", out
    assert out["order_equivalent_revision"], out
    assert out["distinct_semantic_revision"], out
    print("ok  12: policy/tables/context deeply immutable; revisions "
          "order-stable and semantic")


# ---------------------------------------------------------------------------
# 14 — same-span precedence with equal outputs; typed disagreement
# ---------------------------------------------------------------------------

def test_14_equal_output_keeps_higher_layer():
    pol = NormalizationPolicy(registered_skills={"period": "period"})
    ctx = ContextSnapshot(identifiers={"slash period": "/period"})
    res = N("slash period", pol, ctx)
    assert res.text == "/period", res.text
    assert [(e.cls, e.layer) for e in res.edits] == [("skill", 3)]
    assert any(r.cls == "identifier" and r.reason ==
               "lower_layer_same_span" for r in res.rejected)
    # Permutation: proposal discovery order cannot change the owner.
    from localflow.v2.normalize import engine
    from localflow.v2.normalize import syntax as syn
    real = syn.ALL_SYNTAX_GRAMMARS
    try:
        syn.ALL_SYNTAX_GRAMMARS = tuple(reversed(real))
        res2 = N("slash period", pol, ctx)
    finally:
        syn.ALL_SYNTAX_GRAMMARS = real
    assert [(e.cls, e.layer, e.output_text) for e in res2.edits] == \
        [(e.cls, e.layer, e.output_text) for e in res.edits]
    # Same text, same layer, DIFFERENT typed values: ambiguous, rejected.
    from localflow.v2.normalize.span_types import Proposal, Span

    def fake(host):
        yield Proposal(layer=4, cls="integer", op="x", span=Span(0, 6),
                       input_text="twelve", output_text="12", value=12)
        yield Proposal(layer=4, cls="decimal", op="x", span=Span(0, 6),
                       input_text="twelve", output_text="12",
                       value=Decimal("-12"))
    real_num = engine.num_mod.ALL_NUMERIC_GRAMMARS
    try:
        engine.num_mod.ALL_NUMERIC_GRAMMARS = (fake,)
        res3 = N("twelve")
    finally:
        engine.num_mod.ALL_NUMERIC_GRAMMARS = real_num
    assert res3.text == "twelve" and not res3.edits, res3.text
    assert {r.reason for r in res3.rejected} == {"ambiguous_same_span"}
    print("ok  14: equal output keeps the highest layer; typed "
          "disagreement is ambiguous")


# ---------------------------------------------------------------------------
# 15 — canonical identifiers are a no-op
# ---------------------------------------------------------------------------

def test_15_identifier_noop_idempotent():
    ctx = ContextSnapshot(identifiers={"user id": "user ID"})
    a = N("user id", TECH, ctx)
    b = N(a.text, TECH, ctx)
    assert a.text == "user ID" and b.text == a.text
    assert not b.edits, [(e.cls, e.input_text) for e in b.edits]
    assert a.is_idempotent(TECH, ctx) is True
    ctx2 = ContextSnapshot(identifiers={"user id": "userId"})
    assert N("the user ID field", TECH, ctx2).text == "the userId field"
    print("ok  15: already-canonical identifier emits no second-pass edit")


# ---------------------------------------------------------------------------
# 17 — duration covers the complete stage
# ---------------------------------------------------------------------------

def test_17_duration_includes_apply():
    import time as _t
    from localflow.v2.normalize import engine
    real = engine._apply

    def slow(*a, **k):
        _t.sleep(0.03)
        return real(*a, **k)

    engine._apply = slow
    try:
        res = N("twelve percent")
    finally:
        engine._apply = real
    assert res.duration_ms >= 30.0, res.duration_ms
    print("ok  17: duration_ms includes assembly and application")


# ---------------------------------------------------------------------------
# 18/19/20 — oracle and harness strength
# ---------------------------------------------------------------------------

def _load(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("m04rem_" + path.stem,
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _failures(mod):
    failed = []
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        try:
            with redirect_stdout(io.StringIO()):
                getattr(mod, name)()
        except Exception:
            failed.append(name)
    return failed


def test_18_oracle_mutations_are_caught():
    """Mutate only a typed value / an unrelated time rewrite / an
    idempotence flag: the fixture suites must go red each time."""
    from localflow.v2.normalize.span_types import EditRecord
    nums = _load(HERE / "test_normalize_numbers.py")
    real = nums.normalize

    def flip(text, policy, context=None):
        res = real(text, policy, context)
        res.edits = [EditRecord(**{**e.__dict__, "value": (
            -e.value if isinstance(e.value, (int, Decimal))
            and not isinstance(e.value, bool) and e.value else e.value)})
            for e in res.edits]
        return res

    def unit_swap(text, policy, context=None):
        res = real(text, policy, context)
        res.edits = [EditRecord(**{**e.__dict__, "unit": (
            "Mb" if e.unit == "MB" else e.unit)}) for e in res.edits]
        return res

    def time_rewrite(text, policy, context=None):
        res = real(text, policy, context)
        if text == "chapter five thirty two":
            res.text = "chapter 05h32"
        return res

    for label, fn in (("sign", flip), ("unit", unit_swap),
                      ("time", time_rewrite)):
        nums.normalize = fn
        failed = _failures(nums)
        nums.normalize = real
        assert failed, f"{label} mutation not caught"
    data = json.loads((HERE / "fixtures_numeric.json").read_text())
    for c in data["cases"]:
        if c["case_id"] == "LF-NUM-016":
            c["idempotence_expected"] = False
    nums.FIXTURES = data
    assert _failures(nums), "unjustified idempotence flag not caught"
    print("ok  18: typed-sign, unit, time-rewrite and exception-flag "
          "mutations all turn the suite red")


def test_19_scanner_sees_nested_and_aliased_capabilities():
    syn_suite = _load(HERE / "test_normalize_syntax.py")
    pkg_src = ROOT / "localflow" / "v2" / "normalize"
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        pkg = root / "normalize"
        pkg.mkdir()
        for f in pkg_src.glob("*.py"):
            (pkg / f.name).write_text(f.read_text())
        (root / "snippets.py").write_text(
            (ROOT / "localflow" / "v2" / "snippets.py").read_text())
        assert syn_suite.scan_boundary(pkg) == [], "clean copy flagged"
        # Harmless controls: comments and strings are not code.
        (pkg / "engine.py").write_text(
            (pkg / "engine.py").read_text()
            + "\n# never subprocess.run or os.system here\n"
              "_DOC = 'eval( open( os.system'\n")
        assert syn_suite.scan_boundary(pkg) == [], "comment/string flagged"
        # A nested helper reaching a capability through an alias.
        (pkg / "helpers").mkdir()
        (pkg / "helpers" / "__init__.py").write_text("")
        (pkg / "helpers" / "run.py").write_text(
            "import os as _o\nRUN = getattr(_o, 'sys' + 'tem')\n")
        probs = syn_suite.scan_boundary(pkg)
        kinds = {p[0] if p[0] == "population" else p[1] for p in probs}
        assert {"population", "import", "dynamic_attr"} <= kinds, probs
    print("ok  19: scanner catches nested files, aliased imports and "
          "dynamic attributes; ignores comments/strings")


def test_19b_collaborators_never_spawn_or_connect():
    """Runtime capability check across the reachable collaborators: a
    snippet expansion and a file-tag resolution through normalize with
    every process/network entry point booby-trapped."""
    import os
    import socket
    from localflow.v2 import snippets as snip
    trap_calls = []

    def trap(*a, **k):
        trap_calls.append(1)
        raise AssertionError("capability reached")

    saved = (subprocess.run, subprocess.Popen, os.system,
             socket.socket.connect)
    subprocess.run = subprocess.Popen = os.system = trap
    socket.socket.connect = trap
    try:
        s1 = snip.Snippet(snippet_id="s1", trigger="sign off",
                          name="sig", content="Best, {{name}}")
        snap = snip.SnippetSnapshot([s1]) if hasattr(
            snip, "SnippetSnapshot") else None

        class Resolver:
            def resolve(self, words):
                class R:
                    status = "resolved"
                    filename = "notes.md"
                    matched_words = 1
                return R()

        ctx = ContextSnapshot(snippets=snap, file_resolver=Resolver())
        res = N("attach file notes then sign off Ada", TECH, ctx)
        assert "notes.md" in res.text, res.text
        if snap is not None:
            assert "Best, Ada" in res.text, res.text
    finally:
        (subprocess.run, subprocess.Popen, os.system,
         socket.socket.connect) = saved
    assert not trap_calls
    print("ok  19b: snippet/file-tag composition reaches no process or "
          "network capability")


def test_20_benchmark_rejects_noop_and_reports_budget_failure():
    bench = _load(ROOT / "scripts" / "v2" / "benchmark_m04.py")
    from localflow.v2.normalize.span_types import NormalizationResult
    real = bench.normalize

    def identity(text, policy, context=None):
        return NormalizationResult(text=text, edits=[], rejected=[],
                                   protected=[],
                                   policy_revision=policy.policy_revision,
                                   applied=True, duration_ms=0.0)

    bench.normalize = identity
    with redirect_stdout(io.StringIO()):
        code = bench.main(["--iterations-scale", "0.05"])
    assert code == 2, code          # workload invalid beats any speed
    bench.normalize = real
    with redirect_stdout(io.StringIO()):
        code = bench.main(["--iterations-scale", "0.05",
                           "--budget-ms", "0.0001"])
    assert code == 1, code          # real work, forced budget miss
    import time as _t

    def slow_plain(text, policy, context=None):
        res = real(text, policy, context)
        if not res.edits:
            _t.sleep(0.03)          # only the no-match cohort is slow
        return res

    bench.normalize = slow_plain
    with redirect_stdout(io.StringIO()):
        code = bench.main(["--iterations-scale", "0.05"])
    bench.normalize = real
    assert code == 1, code          # the no-match cohort is gated too
    print("ok  20: identity normalizer → exit 2; forced/no-match budget "
          "miss → exit 1")


def main():
    test_01_slash_verb_context_stays_prose()
    test_02_punctuation_is_a_boundary()
    test_03_scaled_decimal_exact()
    test_04_malformed_and_quantified_scales_whole_literal()
    test_05_signed_typed_values_and_port_domain()
    test_06_time_needs_evidence()
    test_07_dates_modal_and_invalid_days()
    test_08_structured_chains_owned_whole()
    test_09_punctuation_nouns_stay_prose()
    test_10_literal_escape_scope()
    test_11_path_case_and_incomplete_chains()
    test_12_policy_deeply_immutable()
    test_14_equal_output_keeps_higher_layer()
    test_15_identifier_noop_idempotent()
    test_17_duration_includes_apply()
    test_18_oracle_mutations_are_caught()
    test_19_scanner_sees_nested_and_aliased_capabilities()
    test_19b_collaborators_never_spawn_or_connect()
    test_20_benchmark_rejects_noop_and_reports_budget_failure()
    print("all M04 remediation regressions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
