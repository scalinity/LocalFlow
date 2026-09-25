"""EV-06 / M04: numeric normalization over the 80 owning fixtures.

Covers M04-AC01 (all owning fixtures pass; incorrect sign/value/unit/
version changes rejected), AC03 (idempotence — second application yields
identical text and zero edits, with the one documented escape corner
flagged per-fixture), AC05 (ledger replay reproduces the output from
input + ledger; number-word→digit edits counted separately).

Run: .venv/bin/python tests/v2/normalization/test_normalize_numbers.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import typed_oracle  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = json.loads((HERE / "fixtures_numeric.json").read_text())


def _policy_for(ctx):
    return NormalizationPolicy(
        locale=ctx.get("locale", "en-US"),
        profile=ctx.get("profile", "technical"))


def _snap_for(ctx):
    if ctx.get("identifiers"):
        return ContextSnapshot(identifiers=ctx["identifiers"])
    return None


def test_fixture_counts():
    assert len(FIXTURES["cases"]) == 80, \
        f"expected exactly 80 numeric fixtures, got {len(FIXTURES['cases'])}"
    ids = [c["case_id"] for c in FIXTURES["cases"]]
    assert len(set(ids)) == 80, "duplicate case ids"
    print("ok  fixture set: exactly 80 unique numeric cases")


def test_all_fixtures_exact():
    """M04-AC01: every fixture produces its expected text; forbidden
    outputs never appear."""
    failures = []
    for case in FIXTURES["cases"]:
        pol = _policy_for(case["context"])
        res = normalize(case["input_text"], pol, _snap_for(case["context"]))
        if res.text != case["expected_text"]:
            failures.append((case["case_id"], case["input_text"],
                             res.text, case["expected_text"]))
        for bad in case.get("forbidden_outputs", []):
            if res.text == bad:
                failures.append((case["case_id"], "forbidden", res.text, bad))
    assert not failures, failures
    n_neg = sum(1 for c in FIXTURES["cases"]
                if "negative_control" in c.get("tags", []))
    print(f"ok  all 80 numeric fixtures exact "
          f"({n_neg} negative controls hold)")


# The ONLY fixtures allowed to declare idempotence_expected=false: none
# in the numeric stratum (the documented escape corners live in the
# syntax fixtures). A new flag must be added here with its reason — a
# flag cannot silently exempt an ordinary case (M04-AUDIT-18).
IDEMPOTENCE_EXCEPTIONS: dict = {}


def test_idempotence_exception_inventory():
    flagged = {c["case_id"] for c in FIXTURES["cases"]
               if c.get("idempotence_expected") is False}
    assert flagged == set(IDEMPOTENCE_EXCEPTIONS), \
        f"undeclared idempotence exceptions: {flagged ^ set(IDEMPOTENCE_EXCEPTIONS)}"
    print(f"ok  idempotence exception inventory: exactly "
          f"{len(IDEMPOTENCE_EXCEPTIONS)} declared")


def test_typed_semantics_independent_oracle():
    """M04-AUDIT-18: every fixture's protected_values checked against
    the typed ledger with independent arithmetic (Decimal equality,
    ordered components, 24-hour clock) plus ledger-sign == rendered-sign
    on every numeric edit."""
    failures = []
    checked = 0
    for case in FIXTURES["cases"]:
        pol = _policy_for(case["context"])
        res = normalize(case["input_text"], pol, _snap_for(case["context"]))
        probs = typed_oracle.check(case, res)
        checked += len(case.get("protected_values", []))
        if probs:
            failures.append((case["case_id"], probs))
    assert not failures, failures
    assert checked >= 60, checked
    print(f"ok  typed semantics: {checked} protected values independently "
          "verified; ledger signs match rendered signs")


def test_idempotence_all_fixtures():
    """M04-AC03: normalize(normalize(x)) == normalize(x) with an empty
    second ledger — asserted per fixture unless the fixture itself
    declares the documented escape corner."""
    failures = []
    for case in FIXTURES["cases"]:
        if case.get("idempotence_expected") is False:
            assert case["case_id"] in IDEMPOTENCE_EXCEPTIONS
            continue
        pol = _policy_for(case["context"])
        first = normalize(case["input_text"], pol,
                          _snap_for(case["context"]))
        second = normalize(first.text, pol, _snap_for(case["context"]))
        if second.text != first.text or second.edits:
            failures.append((case["case_id"], first.text, second.text))
    assert not failures, failures
    print("ok  idempotence: second application is a no-op on all fixtures")


def test_ledger_replay():
    """M04-AC05: the ledger alone rebuilds the output from the retained
    input text, byte for byte."""
    for case in FIXTURES["cases"]:
        pol = _policy_for(case["context"])
        res = normalize(case["input_text"], pol, _snap_for(case["context"]))
        assert res.replay(case["input_text"]) == res.text, case["case_id"]
    print("ok  ledger replay reproduces every fixture output")


def test_typed_values_and_units():
    """S10: parsed values and units ride on the edits so later checks
    know 'twelve percent' and 12% are the same quantity (AC05)."""
    pol = NormalizationPolicy()
    res = normalize("twelve percent", pol)
    e = res.edits[0]
    assert e.cls == "percent" and str(e.value) == "12" and e.unit == "%", e
    assert res.number_word_to_digit_count == 1

    res = normalize("ten by twenty centimeters", pol)
    e = res.edits[0]
    assert e.cls == "dimension" and e.unit == "cm" and e.value == "10x20 cm"

    res = normalize("twelve thousand dollars", pol)
    e = res.edits[0]
    assert e.cls == "currency" and str(e.value) == "12000" and e.unit == "USD"

    res = normalize("the download took twelve megabytes", pol)
    units = {e.unit for e in res.edits}
    assert "MB" in units, units
    res = normalize("the link carries twelve megabits", pol)
    units = {e.unit for e in res.edits}
    assert "Mb" in units, units
    print("ok  typed values/units: percent, dimension, currency, MB vs Mb")


def test_decimal_exactness():
    """S10: decimal arithmetic — exact values, significant zeros."""
    from decimal import Decimal
    pol = NormalizationPolicy()
    res = normalize("keep zero point five zero exactly", pol)
    e = res.edits[0]
    assert e.value == Decimal("0.50"), e.value
    assert e.output_text == "0.50"
    res = normalize("the constant is minus zero point zero five", pol)
    e = res.edits[0]
    assert e.value == Decimal("-0.05") and e.output_text == "-0.05"
    print("ok  decimal exactness: significant zeros and signs preserved")


def test_conflicting_edits_rejected_not_reordered():
    """M04 task 3: two grammars claiming overlapping spans resolve by
    span precedence; the loser is retained as a rejected proposal —
    never applied by substitution order."""
    pol = NormalizationPolicy()
    res = normalize("twelve thousand dollars", pol)
    applied = [(e.cls, e.input_text) for e in res.edits]
    assert applied == [("currency", "twelve thousand dollars")], applied
    losers = [r for r in res.rejected if r.cls == "integer"]
    assert losers, "the overlapping integer proposal must be retained"
    assert all(r.reason in ("overlap_conflict", "ambiguous_same_span")
               for r in res.rejected)
    print("ok  span precedence: overlapping integer retained as rejected")


def test_standard_profile_keeps_integers():
    """S10: the standard profile keeps bare integers as words; typed
    forms still convert."""
    std = NormalizationPolicy(profile="standard")
    assert normalize("twelve retries failed", std).text == \
        "twelve retries failed"
    assert normalize("twelve percent", std).text == "12%"
    assert normalize("twelve thousand dollars", std).text == "$12,000"
    print("ok  standard profile: bare integers stay words, typed forms convert")


def test_off_profile():
    off = NormalizationPolicy(profile="off")
    res = normalize("twelve percent and slash brainstorm", off)
    assert res.text == "twelve percent and slash brainstorm"
    assert not res.edits and not res.applied
    print("ok  off profile: exact passthrough, no edits")


def test_quantified_scale_is_prose():
    """Review regression (C1): a bare 'hundred' after a quantifier is
    prose, on every typed grammar — never 'a few 100 people' or
    'some $100'."""
    pol = NormalizationPolicy()
    for text in ("a few hundred people", "the last several hundred years",
                 "some hundred dollars", "a couple hundred lines",
                 "a few hundred percent"):
        res = normalize(text, pol)
        assert res.text == text, (text, res.text)
    # A real quantity still converts.
    assert normalize("one hundred people arrived", pol).text == \
        "100 people arrived"
    print("ok  quantified 'hundred' stays prose; real quantities convert")


def test_time_requires_time_context():
    """Review regression (W2): an hour+minute word pair without a time
    preposition is ordinal/count context, not a clock. The oracle is
    semantic (M04-AUDIT-18): no time-class edit and the words kept —
    not merely the absence of one forbidden substring."""
    pol = NormalizationPolicy()
    for text in ("chapter five thirty two", "question five thirty",
                 "three fifteen minute breaks", "one twenty minute session"):
        res = normalize(text, pol)
        assert not [e for e in res.edits if e.cls == "time"], \
            (text, res.text)
        assert res.text == text, (text, res.text)
    assert normalize("the meeting is at five thirty", pol).text == \
        "the meeting is at 5:30"
    print("ok  time grammar gated on time context ('at five thirty')")


def main():
    test_fixture_counts()
    test_all_fixtures_exact()
    test_typed_semantics_independent_oracle()
    test_idempotence_exception_inventory()
    test_idempotence_all_fixtures()
    test_ledger_replay()
    test_typed_values_and_units()
    test_decimal_exactness()
    test_conflicting_edits_rejected_not_reordered()
    test_standard_profile_keeps_integers()
    test_off_profile()
    test_quantified_scale_is_prose()
    test_time_requires_time_context()
    print("all numeric normalization tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
