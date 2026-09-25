"""M04 remediation: the audit's adversarial corpus as an executable oracle.

``m04_audit_corpus.json`` is the read-only audit's authored synthetic
challenge corpus (368 text cases / 171 families + 10 stateful probes,
committed verbatim — sha256 recorded in the M04 remediation addendum).
It is DEVELOPMENT evidence: it was consulted while repairing, so it is
not an unseen holdout, and wrappers/profile variants share a family and
are not independent samples.

Each case is scored by its declared oracle kind — never by calling a
production grammar to produce the expectation:

* ``literal_exact`` / ``exact_supported_control`` /
  ``exact_preserving_boundary`` — exact output text.
* ``whole_literal_or_review`` — the whole input survives unchanged.
* ``structured_or_literal`` — whole literal, or an edit whose typed
  value/unit/components equal the INDEPENDENT oracle (Decimal
  arithmetic here, not the parser), with the ledger sign matching the
  rendered sign; a forbidden output never appears.
* ``literal_payload_or_whole_refusal`` — exactly the escaped payload, or
  the untouched input.
* ``profile_contract`` — off is an exact passthrough; technical vs
  standard differ only by the declared switches (bare integers, flags).
* ``intent_invariant`` / ``design_adjudication`` — the explicit
  per-case adjudication in ``m04_corpus_adjudications.json`` (a
  predicate id below plus the rationale). A case the adjudication marks
  ``residual_ambiguity`` is REPORTED with its reason, never counted as a
  pass.

Run: .venv/bin/python tests/v2/normalization/test_m04_audit_corpus.py
"""

import json
import pathlib
import re
import sys
from decimal import Decimal, InvalidOperation

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.normalize import (  # noqa: E402
    NormalizationPolicy,
    normalize,
)

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "m04_audit_corpus.json").read_text())
ADJ = json.loads((HERE / "m04_corpus_adjudications.json").read_text())

STANDARD_SWITCH_CLASSES = {"integer", "flag"}


def _policy(case, profile=None):
    return NormalizationPolicy(
        locale=case.get("locale", "en-US"),
        profile=profile or case["profile"],
        registered_skills=case.get("registered_skills") or {})


def _dec(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError):
        return None


def _rendered_sign_matches(edit):
    """The ledger sign equals the rendered sign (independent check)."""
    v = _dec(edit.value)
    if v is None:
        return True
    shown_negative = edit.output_text.lstrip("$€").startswith("-")
    return (v < 0) == shown_negative


# ---- adjudicated predicates (intent_invariant / design_adjudication) ----

def _p_not_merged_comma(inp, res):
    t = res.text
    return "25" not in t and re.match(r"^(twenty|20),", t) is not None \
        and ("five percent" in t or "5%" in t)


def _p_not_merged_sentence(inp, res):
    t = res.text
    return "105" not in t and re.match(r"^(one hundred|100)\.", t) \
        is not None and ("five percent" in t or "5%" in t)


def _p_no_time_count_duration(inp, res):
    return not any(e.cls == "time" for e in res.edits) and ":" not in \
        res.text and res.text == inp


def _p_code_fence_preserved(inp, res):
    return res.text == inp


def _p_email_case_preserved(inp, res):
    return res.text in (inp, "UserName@example.com")


def _p_year_whole(inp, res):
    return res.text == inp


def _p_subtraction_operands(inp, res):
    return res.text in ("five minus three", "5 minus 3") and "-3" not in \
        res.text


def _p_range_endpoints(inp, res):
    return res.text in ("minus five through five", "-5 through 5")


def _p_literal(inp, res):
    return res.text == inp


def _p_invalid_calendar_literal(inp, res):
    return res.text == inp and any(
        r.cls == "date" and r.reason in ("invalid_day", "invalid_date")
        for r in res.rejected)


def _p_feb29_no_year(inp, res):
    return res.text == "February 29" and any(
        e.cls == "date" and e.value == "02-29" for e in res.edits)


def _p_feb29_leap(inp, res):
    return res.text == "February 29, 2024" and any(
        e.cls == "date" and e.value == "2024-02-29" for e in res.edits)


def _p_period_command_after_word(inp, res):
    return res.text == "literally."


PREDICATES = {
    "not_merged_comma": _p_not_merged_comma,
    "not_merged_sentence": _p_not_merged_sentence,
    "no_time_count_duration": _p_no_time_count_duration,
    "code_fence_preserved": _p_code_fence_preserved,
    "email_case_preserved": _p_email_case_preserved,
    "year_whole": _p_year_whole,
    "subtraction_operands": _p_subtraction_operands,
    "range_endpoints": _p_range_endpoints,
    "literal": _p_literal,
    "invalid_calendar_literal": _p_invalid_calendar_literal,
    "feb29_no_year": _p_feb29_no_year,
    "feb29_leap": _p_feb29_leap,
    "period_command_after_word": _p_period_command_after_word,
}


def _structured(case, res):
    o = case["oracle"]
    inp = case["input"]
    for bad in o.get("forbidden", []):
        if bad in res.text:
            return False, f"forbidden {bad!r}"
    if res.text == inp and o.get("allow_whole_literal", True):
        return True, "whole_literal"
    if "expected" in o:
        return res.text == o["expected"], "exact_structured"
    typed = [e for e in res.edits if e.cls != "literal_escape"]
    if not typed:
        return False, "changed_without_typed_edit"
    for e in typed:
        if not _rendered_sign_matches(e):
            return False, "ledger_sign_mismatch"
    if "components" in o:
        # exact component tuple + unit (review R20: a prefix match let
        # "10x-200 cm" pass for 10 × -20)
        want = [Decimal(c) for c in o["components"]]
        ok = False
        for e in typed:
            if not isinstance(e.value, str) or " " not in e.value:
                continue
            head, unit = e.value.split(" ", 1)
            try:
                got = [Decimal(c) for c in head.split("x")]
            except InvalidOperation:
                continue
            ok |= got == want and (o.get("unit") is None
                                   or unit == o["unit"])
        return ok, "components"
    if "semantic_value" in o:
        want = Decimal(o["semantic_value"])
        ok = any(_dec(e.value) == want
                 and (o.get("unit") is None or e.unit == o["unit"])
                 for e in typed)
        return ok, "semantic_value"
    return False, "no_oracle"


def _profile_contract(case):
    inp = case["input"]
    fam = case["family_id"]
    if case["oracle"]["profile"] == "off":
        res = normalize(inp, _policy(case, "off"))
        return res.text == inp and not res.edits, "off_passthrough"
    tech = normalize(inp, _policy(case, "technical"))
    std = normalize(inp, _policy(case, "standard"))
    t_edits = {(e.input_span.as_pair()[0], e.input_span.as_pair()[1],
                e.output_text, e.cls) for e in tech.edits}
    s_edits = {(e.input_span.as_pair()[0], e.input_span.as_pair()[1],
                e.output_text, e.cls) for e in std.edits}
    extra_std = s_edits - t_edits
    extra_tech = {e for e in t_edits - s_edits
                  if e[3] not in STANDARD_SWITCH_CLASSES}
    return (not extra_std and not extra_tech), f"{fam}_relation"


def evaluate(case):
    """(status, detail): pass | fail | residual."""
    cid = case["case_id"]
    o = case["oracle"]
    kind = o["kind"]
    inp = case["input"]
    adj = ADJ["cases"].get(cid)
    if kind == "profile_contract":
        ok, why = _profile_contract(case)
        return ("pass" if ok else "fail"), why, None
    res = normalize(inp, _policy(case))
    if adj is not None:
        if adj["decision"] == "residual_ambiguity":
            ok = res.text == o.get("expected", inp)
            return ("pass" if ok else "residual"), adj["reason"], res.text
        ok = PREDICATES[adj["predicate"]](inp, res)
        return ("pass" if ok else "fail"), adj["predicate"], res.text
    if kind in ("literal_exact", "exact_supported_control",
                "exact_preserving_boundary"):
        return ("pass" if res.text == o["expected"] else "fail"), kind, \
            res.text
    if kind == "whole_literal_or_review":
        return ("pass" if res.text == inp else "fail"), kind, res.text
    if kind == "structured_or_literal":
        ok, why = _structured(case, res)
        return ("pass" if ok else "fail"), why, res.text
    if kind == "literal_payload_or_whole_refusal":
        ok = res.text in (o["payload"], inp)
        return ("pass" if ok else "fail"), kind, res.text
    return "fail", f"unadjudicated {kind}", res.text


def run_corpus():
    results = {"pass": [], "fail": [], "residual": []}
    for case in CORPUS["cases"]:
        status, why, out = evaluate(case)
        results[status].append((case["case_id"], case["family_id"],
                                case["input"], out, why))
    return results


def test_corpus_shape():
    cases = CORPUS["cases"]
    assert len(cases) == 368, len(cases)
    assert len({c["family_id"] for c in cases}) == 171
    assert len(CORPUS["stateful_probes"]) == 10
    kinds = {c["oracle"]["kind"] for c in cases}
    need_adj = [c["case_id"] for c in cases
                if c["oracle"]["kind"] in ("intent_invariant",
                                           "design_adjudication")]
    missing = [c for c in need_adj if c not in ADJ["cases"]]
    assert not missing, f"unadjudicated intent/design cases: {missing}"
    for cid, a in ADJ["cases"].items():
        assert a["decision"] in ("adjudicated", "residual_ambiguity",
                                 "oracle_rejected"), (cid, a)
        assert a.get("reason"), cid
        if a["decision"] == "adjudicated":
            assert a["predicate"] in PREDICATES, (cid, a)
    print(f"ok  corpus: 368 cases / 171 families / 10 stateful probes; "
          f"{len(kinds)} oracle kinds; {len(need_adj)} intent/design cases "
          "all adjudicated")


def test_corpus_oracles():
    r = run_corpus()
    total = sum(len(v) for v in r.values())
    residual_ids = {x[0] for x in r["residual"]}
    declared = {cid for cid, a in ADJ["cases"].items()
                if a["decision"] == "residual_ambiguity"}
    for cid, fam, inp, out, why in r["fail"]:
        print(f"  FAIL {cid} {fam} {inp!r} -> {out!r} ({why})")
    for cid, fam, inp, out, why in r["residual"]:
        print(f"  residual {cid} {fam} {inp!r} -> {out!r}: {why}")
    assert not r["fail"], f"{len(r['fail'])} corpus oracle failures"
    # A residual must be declared, never silently absorbed.
    assert residual_ids <= declared, residual_ids - declared
    print(f"ok  corpus oracles: {len(r['pass'])}/{total} pass, "
          f"{len(r['residual'])} declared residual ambiguities, 0 fail")


def main():
    test_corpus_shape()
    test_corpus_oracles()
    print("all M04 audit-corpus tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
