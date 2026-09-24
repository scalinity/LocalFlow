"""M07 remediation regressions (audit 2026-09-24 at d3d3e4b): the
adversarial cases ADV-01..ADV-12 plus the compound variants, all with
injected generators (no model).

Each case names what it checks: validator acceptance (``validate``),
engine output (``CleanupEngine.clean``), or the worker's result message.
"Reject" means the corrupt candidate never becomes the returned
artifact — the final text equals the preserved source. These cases were
exposed by the audit, so they are development/regression cases, not
holdouts.

Run: .venv/bin/python tests/v2/fidelity/test_cleanup_remediation.py
"""

import json
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import (  # noqa: E402
    CleanupEngine,
    plan_windows,
    protected_spans_for_cleanup,
)
from localflow.v2.cleanup.engine import (  # noqa: E402
    _halve_at_sentence,
    parse_correction_output,
)
from localflow.v2.cleanup.validation import validate  # noqa: E402

CORR = "Find the self-corrections"


def payload_of(prompt):
    """The FINAL user message's JSON payload (the job, never a few-shot
    example)."""
    body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
    return json.loads(body)


def make_gen(corrections="NONE", main=None, corr_limit=False, log=None):
    """corrections: the correction pass's text; main(payload) -> str or a
    full result dict (default: identity echo of the transcript)."""
    def gen(prompt, max_tokens):
        if CORR in prompt:
            if log is not None:
                log.append(("corrections", None))
            return {"text": corrections, "output_tokens": 3,
                    "limit_hit": corr_limit, "prompt": prompt}
        p = payload_of(prompt)
        if log is not None:
            log.append(("cleanup", p))
        out = main(p) if main else p["transcript"]
        if isinstance(out, dict):
            return {"prompt": prompt, "output_tokens": 5, **out}
        return {"text": out, "output_tokens": 5, "limit_hit": False,
                "prompt": prompt}
    return gen


def clean(text, gen, **kw):
    return CleanupEngine(gen, model_id="fake").clean(text, **kw)


def rejected(source, output, **kw):
    return not validate(source, output, **kw).accepted


def accepted(source, output, **kw):
    rep = validate(source, output, **kw)
    return rep.accepted, [c.to_json() for c in rep.critical_failures]


# ---------------------------------------------------------------------------
# 01 — polarity, scope, source-word-only inventions (validator + engine)
# ---------------------------------------------------------------------------

def test_01_polarity_scope_inventions():
    assert rejected("Modify the database schema.",
                    "Do not modify the database schema.")
    assert rejected("Do not deploy. Run tests.",
                    "Do not deploy or run tests.")
    assert rejected("Do not modify the schema.",
                    "Do not modify the schema. Modify the schema.")
    # Benign punctuation/formatting controls stay accepted.
    for src, out in [
            ("do not deploy run tests", "Do not deploy. Run tests."),
            ("Do not deploy. Run tests.", "Do not deploy; run tests."),
            ("ship it on friday", "Ship it on Friday."),
            ("we should maybe ship it", "We should maybe ship it."),
            ("send the report and the invoice",
             "Send the report and the invoice."),
            ("if the build fails do not deploy",
             "If the build fails, do not deploy.")]:
        ok, why = accepted(src, out)
        assert ok, (src, out, why)
    # Engine: the final artifact is the preserved source, not the
    # polarity-flipped candidate.
    src = "Modify the database schema."
    res = clean(src, make_gen(
        main=lambda p: "Do not modify the database schema."))
    assert res.text == src and res.path != "llm", (res.path, res.text)


def test_01_compound_negation_number_conditional():
    # negation + number
    assert rejected("Do not run more than 3 jobs.",
                    "Do not run more than 4 jobs.")
    assert rejected("Do not run more than 3 jobs.", "Run more than 3 jobs.")
    ok, why = accepted("do not run more than 3 jobs",
                       "Do not run more than 3 jobs.")
    assert ok, why
    # conditional + exception
    assert rejected("Deploy only if the tests pass, except on Friday.",
                    "Deploy only if the tests pass on Friday.")
    assert rejected("Deploy only if the tests pass. Skip Friday.",
                    "Deploy only if the tests pass or skip Friday.")
    ok, why = accepted("deploy only if the tests pass except on friday",
                       "Deploy only if the tests pass, except on Friday.")
    assert ok, why


# ---------------------------------------------------------------------------
# 02 — typed numeric identity (no extra protection supplied)
# ---------------------------------------------------------------------------

def test_02_typed_numbers():
    for src, out in [
            ("Use 3 workers and 4 retries.", "Use 4 workers and 3 retries."),
            ("Set the offset to -5.", "Set the offset to 5."),
            ("Set the cap to 12%.", "Set the cap to 12."),
            ("Set the fee to $12.", "Set the fee to €12."),
            ("Use code 0073.", "Use code 73."),
            ("Meet at 5:30 PM.", "Meet at 6:30 PM."),
            ("Allocate 10 MB.", "Allocate 10 Mb."),
            ("Use Qwen3-4B.", "Use Qwen4-3B."),
            ("Use Qwen3-4B.", "Use qwen3-4b."),
            ("review the q3 goals", "Review the Q4 goals.")]:
        assert rejected(src, out), (src, out)
    # Valid representation changes stay accepted.
    for src, out in [
            ("use thirty percent of the budget", "Use 30% of the budget."),
            ("the fee is twelve dollars", "The fee is $12."),
            ("set it to 12500", "Set it to 12,500."),
            ("use 3 workers and 4 retries", "Use 3 workers and 4 retries."),
            ("meet at 5:30 PM", "Meet at 5:30 PM."),
            ("use Qwen3-4B today", "Use Qwen3-4B today."),
            ("allocate 10 MB", "Allocate 10 MB."),
            # ASR-lowercase identifier: capitalizing is style, not
            # identity (model output seen on LF-STR-022).
            ("review the q3 goals", "Review the Q3 goals."),
            ("the answer is thirty percent", "The answer is 30%.")]:
        ok, why = accepted(src, out)
        assert ok, (src, out, why)


def test_02_corrected_away_value_passes():
    src = "use 3 workers and 4 retries no wait 5 retries"
    res = clean(src, make_gen(corrections="4 retries no wait",
                              main=lambda p: "Use 3 workers and 5 retries."))
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert res.text == "Use 3 workers and 5 retries.", res.text


# ---------------------------------------------------------------------------
# 03 — vocabulary authorization bound to a matched alias span
# ---------------------------------------------------------------------------

def test_03_vocabulary_scoped():
    vp = (("clod code", "Claude Code"),)
    assert rejected("Review code coverage.", "Review coverage.",
                    vocabulary_pairs=vp)
    assert rejected("Review code coverage.", "Review Claude Code coverage.",
                    vocabulary_pairs=vp)
    assert rejected("check clod coverage", "Check coverage.",
                    vocabulary_pairs=vp)
    assert rejected("clod code and clod code", "Claude Code and.",
                    vocabulary_pairs=vp)
    for src, out in [
            ("use clod code for the reviews", "Use Claude Code for the reviews."),
            ("clod code and clod code", "Claude Code and Claude Code."),
            ("clod code and clod code", "Claude Code and clod code.")]:
        ok, why = accepted(src, out, vocabulary_pairs=vp)
        assert ok, (src, out, why)


# ---------------------------------------------------------------------------
# 04 — correction transactions
# ---------------------------------------------------------------------------

def test_04_false_correction_cannot_redefine_reference():
    src = "Never deploy, I mean it."
    res = clean(src, make_gen(corrections="Never deploy, I mean",
                              main=lambda p: "It."))
    assert res.text == src, (res.path, res.text)
    assert res.corrections["applied"] == 0, res.corrections
    # The same shape without a negation to catch it.
    src2 = "Send the report, I mean it."
    res2 = clean(src2, make_gen(corrections="Send the report, I mean",
                                main=lambda p: "It."))
    assert res2.text == src2, (res2.path, res2.text)


def test_04_guard_reasons():
    acc, rej = parse_correction_output(
        "to mark no wait", "send it to mark no wait", [])
    assert not acc and rej[0].reason == "no_replacement", rej
    window = ("move it to friday no wait to monday and the note that says "
              "friday no wait is old")
    acc, rej = parse_correction_output("friday no wait", window, [])
    assert not acc and rej[0].reason == "ambiguous_occurrence", rej
    acc, rej = parse_correction_output("never deploy, i mean",
                                       "never deploy, i mean it", [])
    assert not acc, acc
    acc, rej = parse_correction_output("piano", "play the piano now", [])
    assert not acc and rej[0].reason == "no_marker_ending", rej
    # Valid correction still resolves with exact offsets.
    acc, rej = parse_correction_output(
        "tuesday no wait", "meet tuesday no wait wednesday", [])
    assert acc and acc[0][0] == (5, 20), (acc, rej)


def test_04_truncated_correction_batch_not_applied():
    src = "meet tuesday no wait wednesday because i travel"
    log = []
    res = clean(src, make_gen(corrections="tuesday no wait", corr_limit=True,
                              main=lambda p: "Meet Wednesday because I travel.",
                              log=log))
    main_inputs = [p["transcript"] for k, p in log if k == "cleanup"]
    assert main_inputs == [src], main_inputs     # nothing deleted
    assert res.text == src, res.text
    assert res.corrections["applied"] == 0
    rec = [o for o in res.observations
           if o.get("kind") == "corrections_applied"][0]
    assert "batch_truncated" in rec["rejected_reasons"], rec


def test_04_compound_correction_model_name_and_list():
    src = "use Qwen3-4B no wait Qwen3-8B for the eval"
    res = clean(src, make_gen(corrections="Qwen3-4B no wait",
                              main=lambda p: "Use Qwen3-8B for the eval."))
    assert res.path == "llm" and res.text == "Use Qwen3-8B for the eval.", \
        (res.path, res.fallback_reason, res.text)
    bad = clean(src, make_gen(corrections="Qwen3-4B no wait",
                              main=lambda p: "Use Qwen3-4B for the eval."))
    assert bad.text == src, bad.text
    lst = "1. ship on monday no wait tuesday\n2. run the tests"
    res = clean(lst, make_gen(
        corrections="monday no wait",
        main=lambda p: "1. Ship on Tuesday.\n2. Run the tests."))
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert res.text == "1. Ship on Tuesday.\n2. Run the tests.", res.text


# ---------------------------------------------------------------------------
# 05 — exact, occurrence-mapped protection
# ---------------------------------------------------------------------------

def test_05_protection_exact_and_multiplicity():
    assert rejected("Use UserID.", "Use userid.", protected=["UserID"])
    ok, why = accepted("Use UserID.", "Use UserID.", protected=["UserID"])
    assert ok, why
    assert rejected("Map UserID to UserID now.", "Map UserID to userid now.",
                    protected=["UserID", "UserID"])
    # A literal may take sentence-initial capitalization; a generated
    # (snippet/file-tag) span may not.
    ok, why = accepted("slash and ship it", "Slash and ship it.",
                       protected=[("slash", "literal_escape")])
    assert ok, why
    assert rejected("slash and ship it", "Slash and ship it.",
                    protected=[("slash", "generated")])


def test_05_occurrence_mapping_uses_ledger():
    from localflow.v2.normalize import NormalizationPolicy, normalize
    raw = "the the note says write the words the the"
    res = normalize(raw, NormalizationPolicy(locale="en-US",
                                             profile="technical"))
    assert res.text == "the the note says the the", res.text
    spans = protected_spans_for_cleanup(raw, res.text, res.protected,
                                        res.edits)
    assert [tuple(s[:2]) for s in spans] == [(18, 25)], spans
    assert res.text[18:25] == "the the"
    # Engine: the protected final occurrence survives exactly.
    out = clean(res.text, make_gen(main=lambda p: "The note says the the."),
                protected_spans=spans)
    assert out.path == "llm", (out.path, out.fallback_reason)


# ---------------------------------------------------------------------------
# 06 — the final artifact is not mutated after validation / on fallback
# ---------------------------------------------------------------------------

NESTED = ("1. Modify only the test fixture.\n"
          "   1. Do not change production code.\n"
          "2. Run the tests.")
FENCE = ("Run this:\n\n```python\n    def f():\n        return  1\n```")


def test_06_identity_and_fallback_preserve_final():
    for text in (NESTED, FENCE, "3. third item\n4. fourth item"):
        ident = clean(text, make_gen())
        assert ident.path == "llm", (ident.path, ident.fallback_reason)
        assert ident.text == text, repr(ident.text)
        bad = clean(text, make_gen(main=lambda p: "invented garbage words"))
        assert bad.path != "llm"
        assert bad.text == text, repr(bad.text)
        lim = clean(text, make_gen(main=lambda p: {
            "text": "trunc", "limit_hit": True}))
        assert lim.incomplete and lim.text == text, repr(lim.text)


def test_06_protected_list_not_renumbered():
    text = "Steps:\n\n1. alpha step\n1. beta step"
    s = text.index("1. alpha")
    res = clean(text, make_gen(),
                protected_spans=[(s, len(text), "generated")])
    assert res.text == text, repr(res.text)
    # Unprotected: the renderer still controls numbering.
    res2 = clean(text, make_gen())
    assert res2.text == "Steps:\n\n1. alpha step\n2. beta step", \
        repr(res2.text)


# ---------------------------------------------------------------------------
# 07 — safe cuts, intact protected units, output multiplicity
# ---------------------------------------------------------------------------

def test_07_protected_long_literal_never_cut():
    lit = '"' + " ".join(["alpha"] * 500) + '"'
    text = "Keep " + lit + " exactly"
    span = (5, 5 + len(lit))
    windows = plan_windows(text, [span])
    owners = [w for w in windows if w.start <= span[0] and span[1] <= w.end]
    assert len(owners) == 1, [(w.start, w.end) for w in windows]
    for w in windows:
        assert not (w.start < span[0] < w.end < span[1]), (w.start, w.end)
        assert not (span[0] < w.start < span[1]), (w.start, w.end)
    assert _halve_at_sentence("alpha beta gamma delta epsilon zeta") == []


def test_07_forced_limit_without_safe_cut_preserves_source():
    lit = '"' + " ".join(["beta"] * 60) + '"'
    text = "Alpha keeps " + lit + " and gamma"
    s = text.index(lit)
    log = []
    res = clean(text, make_gen(main=lambda p: {"text": "trunc",
                                              "limit_hit": True}, log=log),
                protected_spans=[(s, s + len(lit))])
    assert res.text == text and res.incomplete, repr(res.text)
    assert len([k for k, _ in log if k == "cleanup"]) == 1, log


def test_07_oversized_code_block_not_split():
    code = "```\n" + "\n".join(f"line_{i} = {i}" for i in range(260)) + "\n```"
    windows = plan_windows(code)
    assert len(windows) == 1, [(w.start, w.end) for w in windows]


def test_07_overlap_copy_not_duplicated():
    # Window 2's own words cover the copied context, so only output
    # multiplicity (not word novelty) can catch the duplication.
    para1 = " ".join("Ship the alpha build today." for _ in range(45))
    para2 = "Ship the alpha build today. Then rest."
    text = para1 + "\n\n" + para2

    def main(p):
        ro = p.get("read_only_context")
        if ro:
            tail = ro.split(": ", 1)[1]
            return tail + " " + p["transcript"]
        return p["transcript"]

    res = clean(text, make_gen(main=main))
    assert res.termination["windows"] >= 2, res.termination
    assert any("novelty" in (w["reason"] or "") for w in res.windows)
    assert res.text.count("Ship the alpha build today.") == 46, \
        res.text[-300:]
    assert res.text.count("Then rest.") == 1


def test_07_unique_final_requirement_near_limit():
    body = " ".join(f"Step {i} runs the suite." for i in range(20))
    text = body + " Finally never push to main."

    def main(p):
        if len(p["transcript"].split()) > 70:
            return {"text": "Step 0 runs", "limit_hit": True}
        return p["transcript"]

    res = clean(text, make_gen(main=main))
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert res.text.count("never push to main") == 1, res.text


# ---------------------------------------------------------------------------
# 08 — V2 error paths keep protection
# ---------------------------------------------------------------------------

def _worker_clean(raw_text, engine, protected=None):
    import localflow.v2.worker as wm
    w = wm.Worker("/tmp")
    w.cleanup_mode, w.cleanup_implementation = "llm", "v2"
    sent, real = [], wm._write_msg
    wm._write_msg = sent.append
    try:
        w.cleanup_engine = engine
        w._clean({"req_id": "r", "job_id": "j", "attempt": 1,
                  "generation": 1, "raw_text": raw_text,
                  "protected_spans": protected or []})
    finally:
        wm._write_msg = real
    return sent[0]


def test_08_engine_exception_keeps_protected_text():
    class Boom:
        def clean(self, raw_text, **kw):
            raise RuntimeError("engine exploded")

    for text, prot in [('Keep "um" literal.', [[5, 9]]),
                       ("say um exactly", [[4, 6]]),
                       ('the header said "the the" twice', [[16, 25]]),
                       ("Run:\n\n```\n    x  =  1\n        y = 2\n```", [])]:
        msg = _worker_clean(text, Boom(), prot)
        assert msg["text"] == text, (text, msg["text"])
        assert msg["path"] == "llm_fallback_normalized", msg["path"]
        assert msg["fallback_reason"] == "cleanup_engine_failed"
        assert msg["v2"]["termination"]["kind"] == "engine_error"


def test_08_load_failure_keeps_protected_text():
    import types
    import localflow.v2.worker as wm
    import localflow.v2.cleanup as v2c

    class FakeTranscriber:
        def __init__(self, model):
            pass

        def load(self, on_phase=None):
            pass

    class FailingRunner:
        def __init__(self, model_id):
            pass

        def load(self):
            raise RuntimeError("no model")

    fake_stt = types.ModuleType("localflow.stt")
    fake_stt.Transcriber = FakeTranscriber
    saved_stt = sys.modules.get("localflow.stt")
    saved_runner = v2c.ModelRunner
    sys.modules["localflow.stt"] = fake_stt
    v2c.ModelRunner = FailingRunner
    sent, real = [], wm._write_msg
    wm._write_msg = sent.append
    try:
        w = wm.Worker("/tmp")
        w._load({"asr_model": "a", "cleanup_mode": "llm",
                 "cleanup_model": "c", "cleanup_implementation": "v2"})
        failed = [m for m in sent if m.get("engine") == "cleanup"
                  and m.get("state") == "failed"]
        assert failed, sent
        sent.clear()
        w._clean({"req_id": "r", "job_id": "j", "attempt": 1,
                  "generation": 1, "raw_text": 'Keep "um" literal.',
                  "protected_spans": [[5, 9]]})
    finally:
        wm._write_msg = real
        v2c.ModelRunner = saved_runner
        if saved_stt is not None:
            sys.modules["localflow.stt"] = saved_stt
        else:
            sys.modules.pop("localflow.stt", None)
    msg = sent[0]
    assert msg["op"] == "result", msg
    assert msg["text"] == 'Keep "um" literal.', msg["text"]
    assert msg["fallback_reason"] == "cleanup_engine_failed"
    assert msg["path"] != "llm"


# ---------------------------------------------------------------------------
# 09 — retry children slice their own text
# ---------------------------------------------------------------------------

def test_09_retry_child_protection_coordinates():
    def run(prefix):
        text = prefix + "Alpha. Keep UserID unchanged."
        s = text.index("UserID")
        seen = {"n": 0}
        payloads = []

        def main(p):
            if "UserID" not in p["transcript"] and "Alpha" not in \
                    p["transcript"]:
                return p["transcript"]
            seen["n"] += 1
            payloads.append(p)
            if seen["n"] == 1:
                return {"text": "Alpha. Keep", "limit_hit": True}
            return p["transcript"]

        res = clean(text, make_gen(main=main),
                    protected_spans=[(s, s + 6)])
        return res, payloads

    res, payloads = run("")
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert "UserID" in res.text
    right = [p for p in payloads if p["transcript"].startswith("Keep")]
    assert right and right[0]["protected_spans"] == ["UserID"], \
        [p["protected_spans"] for p in payloads]
    # Nonzero parent offset: the limited window starts after a first
    # window of its own.
    prefix = " ".join(f"word{i}" for i in range(199)) + ".\n\n"
    res2, _ = run(prefix)
    assert res2.termination["windows"] == 2, res2.termination
    assert res2.path == "llm", (res2.path, res2.fallback_reason)


# ---------------------------------------------------------------------------
# 10 — standalone "actually" correction
# ---------------------------------------------------------------------------

def test_10_standalone_actually():
    log = []
    res = clean("Meet Tuesday actually Thursday.", make_gen(
        corrections="Tuesday actually",
        main=lambda p: "Meet Thursday.", log=log))
    assert [k for k, _ in log][0] == "corrections", log
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert res.text == "Meet Thursday."
    assert res.corrections["applied"] == 1, res.corrections
    # Negative controls: emphasis "actually" and "I mean it" stay.
    for src, proposal in [("We actually shipped early.", "We actually"),
                          ("I mean it.", "I mean"),
                          ("Ship it now, I mean it.", "Ship it now, I mean")]:
        r = clean(src, make_gen(corrections=proposal))
        assert r.text == src, (src, r.text)
        assert r.corrections["applied"] == 0, (src, r.corrections)


# ---------------------------------------------------------------------------
# 11 — engine-side decision evidence
# ---------------------------------------------------------------------------

def test_11_decision_statuses_and_counts():
    # Correction accepted by the guards, main candidate rejected: the
    # correction is rolled back and not counted as applied.
    res = clean("meet tuesday no wait wednesday because i travel",
                make_gen(corrections="tuesday no wait",
                         main=lambda p: "We meet Wednesday."))
    assert res.path != "llm"
    c = res.corrections
    assert c["applied"] == 0 and c["rolled_back"] == 1, c
    props = [p for o in res.observations if o.get("kind") ==
             "corrections_applied" for p in o["proposals"]]
    assert [p["status"] for p in props] == ["rolled_back"], props
    ok = clean("meet tuesday no wait wednesday because i travel",
               make_gen(corrections="tuesday no wait",
                        main=lambda p: "Meet Wednesday because I travel."))
    assert ok.path == "llm" and ok.corrections["applied"] == 1, \
        (ok.path, ok.corrections)
    # Every pass has an identity; decisions carry the window and status.
    passes = [o for o in ok.observations
              if o.get("kind") in ("cleanup", "corrections")]
    assert len({o["pass_id"] for o in passes}) == len(passes) >= 2
    dec = [o for o in ok.observations if o.get("kind") == "cleanup_decision"]
    assert dec and dec[0]["status"] == "selected" and dec[0]["pass_id"]


def test_11_split_recovery_keeps_child_lineage_and_revisions():
    text = ("First half sentence one. " + "Filler words grow it. " * 7
            + "Second half sentence one. " + "Filler words grow it. " * 7)

    def main(p):
        if len(p["transcript"].split()) > 60:
            return {"text": "TRUNC", "limit_hit": True}
        return p["transcript"]

    eng = CleanupEngine(make_gen(main=main), model_id="fake",
                        template_revision="tmpl:abc")
    res = eng.clean(text)
    assert res.path == "llm", (res.path, res.fallback_reason)
    j = res.to_json()
    assert j["template_revision"] == "tmpl:abc"
    assert j["corrections_prompt_revision"].startswith("m07c:")
    win = j["windows"][0]
    assert len(win["children"]) == 2, win
    assert all(ch["stage"] == "clean" for ch in win["children"])
    limit = [o for o in res.observations if o.get("kind") == "cleanup"
             and o.get("limit_hit")]
    kids = [o for o in res.observations if o.get("kind") == "cleanup"
            and o.get("parent_pass_id")]
    assert limit and limit[0]["accepted"] is False
    assert {k["parent_pass_id"] for k in kids} == {limit[0]["pass_id"]}
    child_decisions = [o for o in res.observations
                       if o.get("kind") == "cleanup_decision"
                       and o.get("depth") == 1]
    assert len(child_decisions) == 2
    assert all(d["validation"]["components"] for d in child_decisions)
    assert res.validation["windows_validated"] == 1


# ---------------------------------------------------------------------------
# Review follow-up (independent review of this remediation, 2026-09-24):
# each case is a confirmed repro against the first repair.
# ---------------------------------------------------------------------------

def test_r1_single_word_marker_needs_parallel_values():
    for src, proposal in [
            ("Actually, deploy the fix no matter what.", "deploy the fix no"),
            ("We should actually deploy on Friday.", "should actually"),
            ("The team actually shipped the fix.", "team actually")]:
        res = clean(src, make_gen(corrections=proposal))
        assert res.text == src, (src, res.text)
    # Parallel single-word corrections still apply.
    for src, proposal, out in [
            ("meet at 5 actually 6 tonight", "5 actually",
             "Meet at 6 tonight."),
            ("ship it friday actually saturday", "friday actually",
             "Ship it Saturday.")]:
        res = clean(src, make_gen(corrections=proposal, main=lambda p, o=out: o))
        assert res.path == "llm" and res.text == out, \
            (src, res.path, res.fallback_reason, res.text)


def test_r2_corrected_away_value_cannot_return():
    res = clean("send it to mark no wait to lisa", make_gen(
        corrections="to mark no wait",
        main=lambda p: "Send it to Lisa and Mark."))
    assert res.text == "send it to mark no wait to lisa", res.text
    assert rejected("meet tuesday no wait wednesday",
                    "Meet Wednesday and Tuesday.",
                    correction_spans=[(5, 20, 13)])


def test_r3_render_never_changes_a_bound_value():
    for src, out in [("We need:\n3 servers\n5 workers",
                      "We need:\n3. servers\n5. workers"),
                     ("Keep 3 replicas and 2 shards.",
                      "Keep\n3. replicas and\n2. shards.")]:
        res = clean(src, make_gen(main=lambda p, o=out: o))
        assert res.text == src, (src, res.text)
    assert rejected("Keep it.", "Keep it 5.", continued_list_start=3)
    assert rejected("Keep it.", "Keep\n7. it.")
    # A list's start number survives; markdown-style "1. 1." renumbers.
    assert rejected("3. third\n4. fourth", "1. Third.\n2. Fourth.")
    ok, why = accepted("1. alpha\n1. beta", "1. Alpha.\n2. Beta.")
    assert ok, why


def test_r4_protected_occurrence_not_merely_text():
    src = "the the note says the the"
    assert rejected(src, "The the note says the.",
                    protected=[("the the", "literal_escape")],
                    protected_positions=[(18, 25)])
    assert rejected("type um then say um", "Type then say um.",
                    protected=[("um", "literal_escape")],
                    protected_positions=[(5, 7)])
    res = clean(src, make_gen(main=lambda p: "The note says the the."),
                protected_spans=[(18, 25, "literal_escape")])
    assert res.path == "llm", (res.path, res.fallback_reason)


def test_r5_scope_merge_across_line_break():
    assert rejected("Do not deploy\nRun tests", "Do not deploy and run tests.")
    assert rejected("Never deploy on Friday\nRun the tests",
                    "Never deploy on Friday and run the tests.")
    ok, why = accepted("Do not deploy. Run tests.", "Do not deploy — run tests.")
    assert ok, why


def test_r6_enumeration_marker_bound_to_rendered_item():
    assert rejected("Restart the second server.\n\n- alpha\n- beta",
                    "Restart the server.\n\n- alpha\n- beta")
    assert rejected("Deploy build number two.\n\n- alpha\n- beta",
                    "Deploy build.\n\n- alpha\n- beta")
    ok, why = accepted("two updates number one the quote is signed number two "
                       "the team is hired",
                       "Two updates:\n1. The quote is signed.\n"
                       "2. The team is hired.")
    assert ok, why
    # Real model outputs (LF-STR-009, LF-STR-036 shapes): a marker whose
    # first content word a correction removed, and a sentence-final
    # marker the output turns into a list intro.
    ok, why = accepted(
        "three reminders number one call the dentist no wait the clinic "
        "number two renew the passport number three water the plants",
        "Three reminders:\n1. The clinic.\n2. Renew the passport.\n"
        "3. Water the plants.", correction_spans=[(27, 51, 44)])
    assert ok, why
    ok, why = accepted(
        "so the retro board first. number one the deploy froze. number two "
        "the alerts fired.",
        "So, the retro board:\n1. The deploy froze.\n2. The alerts fired.")
    assert ok, why


def test_r7_comma_grouping_is_checked():
    assert rejected("use ports 3,4", "Use ports 34.")
    assert rejected("set it to 12500", "Set it to 1,2500.")


def test_r8_operator_symbols_and_questions():
    assert rejected("x = 5 - 3", "x = 5 + 3")
    assert rejected("if x > 5 stop", "If x < 5, stop.")
    assert rejected("if x >= 5 stop", "If x = 5, stop.")
    assert rejected("we ship friday?", "We ship Friday.")
    ok, why = accepted("x equals 5", "x = 5")
    assert ok, why
    ok, why = accepted("do we ship friday", "Do we ship Friday?")
    assert ok, why


def test_r9_quotes_in_the_text_are_kept():
    for src in ('He said "stop"', '"Hello" is the greeting'):
        res = clean(src, make_gen())
        assert res.text == src, (src, res.text)
    res = clean("ship it", make_gen(main=lambda p: '"Ship it."'))
    assert res.text == "Ship it.", res.text


def test_r10_window_seams_use_the_source_separator():
    para1 = " ".join(f"alpha{i} word here." for i in range(50))
    items = "\n".join(f"{i}. item{i} thing" for i in range(1, 14))
    para2 = " ".join(f"Closing beta{i} note." for i in range(34))
    text = para1 + "\n\n" + items + "\n\n" + para2
    res = clean(text, make_gen())
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert "13. item13 thing\n\nClosing beta0" in res.text, \
        res.text[res.text.find("13."):][:60]
    assert res.text == text


def test_r11_interjector_only_at_phrase_start():
    assert rejected("we need um so much more", "We need much more.")
    assert rejected("ship it by five so the team can rest",
                    "Ship it by 5, the team can rest.")
    ok, why = accepted("okay so for the redesign we keep it",
                       "Okay, for the redesign we keep it.")
    assert ok, why


def test_r12_split_retry_counts_and_incomplete_flag():
    text = ("First we meet monday no wait tuesday for the plan. "
            + "Filler words grow it. " * 7 + "Second half sentence one. "
            + "Filler words grow it. " * 7)

    def main(p):
        if len(p["transcript"].split()) > 60:
            return {"text": "TRUNC", "limit_hit": True}
        return p["transcript"].replace("monday no wait ", "")

    res = clean(text, make_gen(corrections="monday no wait", main=main))
    assert res.path == "llm", (res.path, res.fallback_reason)
    c = res.corrections
    assert (c["applied"], c["proposed"], c["rolled_back"]) == (1, 1, 0), c

    def bad_assembly(p):
        if len(p["transcript"].split()) > 60:
            return {"text": "TRUNC", "limit_hit": True}
        if p["transcript"].startswith("Second"):
            return "First we meet tuesday for the plan. " + p["transcript"]
        return p["transcript"]

    res2 = clean(text.replace("monday no wait ", ""),
                 make_gen(main=bad_assembly))
    assert res2.text == text.replace("monday no wait ", "").strip()
    assert res2.incomplete and res2.termination["kind"] == "output_limit", \
        (res2.fallback_reason, res2.incomplete)


TESTS = [v for k, v in sorted(globals().items())
         if k.startswith("test_") and callable(v)]


def main():
    failed = []
    for t in TESTS:
        try:
            t()
            print(f"ok    {t.__name__}")
        except Exception as e:     # report every case, not just the first
            failed.append(t.__name__)
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"[:400])
            if "-v" in sys.argv:
                traceback.print_exc()
    print(f"{len(TESTS) - len(failed)}/{len(TESTS)} remediation cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
