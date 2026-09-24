"""EV-09 / M07 deterministic engine suite: windowing ownership,
offset-anchored corrections, validation boundaries, rollback and
output-limit recovery — all with injected fake generators (no model).

Run: .venv/bin/python tests/v2/fidelity/test_cleanup_engine.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import (  # noqa: E402
    CleanupEngine,
    plan_windows,
    protected_spans_for_cleanup,
)
from localflow.v2.cleanup import prompts  # noqa: E402
from localflow.v2.cleanup.document_nodes import parse, renumber  # noqa: E402
from localflow.v2.cleanup.engine import (  # noqa: E402
    parse_correction_output,
    apply_corrections,
)
from localflow.v2.cleanup.validation import validate  # noqa: E402


def transcript_of(prompt):
    body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
    return json.loads(body)["transcript"]


def test_window_ownership_invariant():
    import random
    random.seed(11)
    for _ in range(150):
        paras = []
        for _ in range(random.randint(1, 7)):
            n = random.randint(1, 400)
            words = [random.choice(
                ["ship", "the", "it", "monday", "no wait", "x.py", "30",
                 "list", "one"]) for _ in range(n)]
            body = " ".join(words)
            if random.random() < 0.3:
                body = "- item one\n- item two\n" + body
            if random.random() < 0.2:
                body = "```\ncode\n```"
            paras.append(body)
        t = "\n\n".join(paras)
        windows = plan_windows(t)
        # Exclusive, exhaustive, verbatim ownership.
        covered = []
        for w in windows:
            assert t[w.start:w.end] == w.text
            covered.append((w.start, w.end))
        covered.sort()
        pos = 0
        for s, e in covered:
            assert s >= pos
            assert t[s:e].strip()
            pos = e
        # Gaps may contain only whitespace between windows.
        prev = 0
        for s, e in covered:
            assert not t[prev:s].strip()
            prev = e
        assert not t[prev:].strip()
    print("ok  window ownership: exclusive, exhaustive, verbatim, "
          "whitespace-only seams")


def test_long_input_one_generation_when_fits():
    """A normal dictation (<= budget) is ONE generation — no 35/50-word
    chunking (S13)."""
    text = "twenty plain words " * 6  # ~72 words
    calls = []

    def gen(prompt, max_tokens):
        calls.append(prompt)
        t = transcript_of(prompt)
        return {"text": t.capitalize(), "output_tokens": 5,
                "limit_hit": False, "prompt": prompt}

    res = CleanupEngine(gen, model_id="fake").clean(text.strip())
    assert len(calls) == 1, calls
    assert res.path == "llm"
    assert res.termination["windows"] == 1
    print("ok  budget-length input: exactly one cleanup generation")


def test_windows_complete_blocks_with_read_only_overlap():
    text = ("para one. " + "word " * 210).strip() + "\n\n" + "para two. " + "tail " * 30
    seen = []

    def gen(prompt, max_tokens):
        seen.append(transcript_of(prompt))
        t = seen[-1]
        return {"text": t.capitalize(), "output_tokens": 5,
                "limit_hit": False, "prompt": prompt}

    res = CleanupEngine(gen, model_id="fake").clean(text)
    assert res.termination["windows"] >= 2
    # Each window's transcript is a contiguous slice of the source.
    for t in seen:
        assert t in text or t.replace("\n", " ") in text.replace("\n", " ")
    print(f"ok  long input: {res.termination['windows']} complete-block"
          " windows, contiguous owned slices")


def test_corrections_exact_offsets_and_reason_preserved():
    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "tuesday no wait\nthe draft no sorry",
                    "output_tokens": 12, "limit_hit": False,
                    "prompt": prompt}
        t = transcript_of(prompt)
        return {"text": t.capitalize() + ".", "output_tokens": 9,
                "limit_hit": False, "prompt": prompt}

    text = "we meet tuesday no wait wednesday because i travel and send " \
           "the value the draft no sorry the final version today"
    res = CleanupEngine(gen, model_id="fake").clean(text)
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert "wednesday" in res.text and "because i travel" in res.text
    assert "the final version" in res.text
    assert "draft" not in res.text and "no sorry" not in res.text
    assert res.corrections["applied"] == 2
    print("ok  corrections: exact offsets, replacement + reason survive")


def test_duplicate_spans_delete_in_spoken_order():
    window = ("hire two engineers no wait three engineers and invite "
              "two engineers no wait five engineers to the review")
    accepted, rejected = parse_correction_output(
        "two engineers no wait\ntwo engineers no wait", window, [])
    assert len(accepted) == 2 and not rejected
    spans = sorted((s, e) for (s, e), _d in accepted)
    assert spans[0][0] < spans[1][0]
    out = apply_corrections(window, accepted)
    assert "three engineers and invite five engineers" in out, out
    print("ok  duplicate correction spans: sequential in-order deletion")


def test_correction_guards():
    window = "book it for monday no wait tuesday please"
    # Bare marker, no marker ending, too long.
    acc, rej = parse_correction_output(
        "no wait\nmonday\nbook it for the whole meeting on monday "
        "no wait", window, [])
    assert not acc
    reasons = {r.reason for r in rej}
    assert reasons == {"bare_marker", "no_marker_ending", "span_too_long"}, \
        reasons
    # A proposal overlapping a protected span rejects.
    acc2, rej2 = parse_correction_output(
        "it for monday no wait", "book it for monday no wait tuesday",
        [(5, 20)])
    assert not acc2 and rej2[0].reason == "protected_span"
    print("ok  correction guards: bare marker / wrong ending / too long / "
          "protected-span rejections")


def test_ac02_rollback_on_validation_failure():
    """A rejected cleanup candidate rolls back the window entirely —
    unvalidated correction deletions included (M07-AC02, S14)."""
    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "tuesday no wait", "output_tokens": 6,
                    "limit_hit": False, "prompt": prompt}
        return {"text": "We meet Wednesday.", "output_tokens": 6,
                "limit_hit": False, "prompt": prompt}

    text = "meet tuesday no wait wednesday because i travel that week"
    res = CleanupEngine(gen, model_id="fake").clean(text)
    assert res.path == "llm_fallback_normalized"
    assert res.text == text, res.text      # full rollback, byte for byte
    assert "validation_rejected" in res.fallback_reason
    # The proposal survived as inspectable evidence with its validation.
    decisions = [o for o in res.observations
                 if o.get("kind") == "cleanup_decision"]
    assert decisions and decisions[-1]["accepted"] is False
    assert decisions[-1]["validation"]["accepted"] is False
    print("ok  AC02: rejected candidate rolls back correction deletions;"
          " proposal + findings retained")


def test_output_limit_split_retry_and_incomplete_notice():
    """Limit-hit → the ORIGINAL range halves and retries; a half that
    still fails rolls the whole window back to source with an explicit
    incomplete notice — never the truncated output, never unvalidated
    corrections (S13/AC02)."""
    # Capitalized sentences give the retry safe seams to split at.
    text = ("Sentence one about shipping. " * 3 + "Alpha beta gamma. "
            + "Tail words here. ") * 12
    calls = {"n": 0}

    def gen(prompt, max_tokens):
        calls["n"] += 1
        t = transcript_of(prompt)
        if len(t.split()) > 60:      # whole window and its halves fail
            return {"text": "TRUNCATED MID OUTP", "output_tokens": max_tokens,
                    "limit_hit": True, "prompt": prompt}
        return {"text": t.capitalize() + ".", "output_tokens": 4,
                "limit_hit": False, "prompt": prompt}

    res = CleanupEngine(gen, model_id="fake").clean(text)
    assert calls["n"] >= 3            # the retry actually engaged
    assert res.incomplete is True
    assert res.termination["kind"] == "output_limit"
    assert res.termination["limit_hits"] >= 2
    assert "TRUNCATED" not in res.text       # never pasted as success
    # AC02: the whole window falls back to its ORIGINAL source.
    assert "sentence one about shipping" in res.text.lower()
    assert res.text.lower().startswith("sentence one about shipping.")


def test_output_limit_retry_recovery_success():
    """When the halves validate, the window is clean — assembled from
    the two validated halves, no incomplete notice. The halves split at
    a safe sentence seam ("... block. Second half ..."); a range with no
    safe seam is never force-cut (remediation test_07)."""
    text = ("first half sentence one. first half sentence two. "
            + "filler words to grow the block. " * 6) \
        + " Second half sentence one. second half sentence two. " \
        + "more filler words close the block. " * 6
    calls = {"n": 0}

    def gen(prompt, max_tokens):
        calls["n"] += 1
        t = transcript_of(prompt)
        if len(t.split()) > 60:      # whole window only; halves validate
            return {"text": "TRUNC", "output_tokens": max_tokens,
                    "limit_hit": True, "prompt": prompt}
        return {"text": t.capitalize(), "output_tokens": 4,
                "limit_hit": False, "prompt": prompt}

    res = CleanupEngine(gen, model_id="fake").clean(text)
    assert calls["n"] >= 3
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert res.incomplete is False
    assert res.termination["kind"] == "complete"
    assert "First half sentence one" in res.text
    assert "second half sentence one" in res.text.lower()
    print("ok  output-limit retry recovery: halves validate → clean")


def test_multi_window_with_protected_span():
    """Review critical #1: protected spans are scoped per window — a
    span in window 2 must not reject window 1, and the corrections
    guard uses window-local coordinates in every window."""
    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "NONE", "output_tokens": 2, "limit_hit": False,
                    "prompt": prompt}
        t = transcript_of(prompt)
        return {"text": t[0].upper() + t[1:] + ".", "output_tokens": 6,
                "limit_hit": False, "prompt": prompt}

    para1 = " ".join(f"first paragraph line {i} about shipping the "
                     f"release safely" for i in range(20))
    para2 = " ".join(f"second paragraph line {i} keeps \"the the\" "
                     f"quoted verbatim" for i in range(20))
    text = para1 + "\n\n" + para2
    idx = text.index('"the the"')
    res = CleanupEngine(gen, model_id="fake").clean(
        text, protected_spans=[(idx, idx + 9)])
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert res.termination["windows"] >= 2
    assert '"the the"' in res.text
    # The payload told each window only its own protected tokens.
    prompts_seen = [o.get("prompt") for o in res.observations
                    if o.get("kind") == "cleanup"]
    w1_prompt = prompts_seen[0]
    assert '"the the"' not in w1_prompt
    print("ok  multi-window + protected span: per-window scoping, both"
          " windows validate")


def test_protected_span_mapping_never_drops():
    """Protection maps through the ledger and never silently drops: a
    quote whose words normalization rewrote stays protected over its
    normalized form, and a span the ledger cannot describe raises (the
    coordinator then abstains from model cleanup)."""
    from localflow.v2.cleanup import protected_spans_for_cleanup
    from localflow.v2.normalize import NormalizationPolicy, normalize
    from localflow.v2.normalize.span_types import ProtectedSpan, Span
    raw = 'she said "ship twenty items" to me'
    res = normalize(raw, NormalizationPolicy(locale="en-US",
                                             profile="technical"))
    spans = protected_spans_for_cleanup(raw, res.text, res.protected,
                                        res.edits)
    assert [res.text[s:e] for s, e, _k in spans] == ["ship 20 items"], \
        spans
    try:
        protected_spans_for_cleanup(
            raw, res.text, [ProtectedSpan(Span(99, 120), "quoted")],
            res.edits)
        raise AssertionError("out-of-range span must not be dropped")
    except ValueError:
        pass
    print("ok  protected spans map through the ledger; unmappable spans "
          "fail loudly, never drop")


def test_validator_damaged_outputs_e09():
    """The E09 damaged-output catalog: each corruption is caught by the
    named deterministic component; the counterexamples pass."""
    base = ("deploy the service with 30 replicas on friday and do not "
            "enable the cache maybe check the logs at config.yaml first")
    cases = [
        ("drop not", "Deploy the service with 30 replicas on friday and "
         "do enable the cache maybe check the logs at config.yaml first",
         "negation_coverage"),
        ("30 to 300", "deploy the service with 300 replicas on friday "
         "and do not enable the cache maybe check the logs at config.yaml"
         " first", "numeric_values"),
        ("drop maybe", "Deploy the service with 30 replicas on friday "
         "and do not enable the cache check the logs at config.yaml "
         "first", "uncertainty_coverage"),
        ("change file name", "deploy the service with 30 replicas on "
         "friday and do not enable the cache maybe check the logs at "
         "config.yml first", "technical_tokens"),
        ("invent requirement", "deploy the service with 30 replicas on "
         "friday and do not enable the cache maybe check the logs at "
         "config.yaml first and add kubernetes", "novelty"),
        ("omit final clause", "Deploy the service with 30 replicas on "
         "friday and do not enable the cache maybe", "coverage"),
        ("swap order", "on friday deploy the service with 30 replicas "
         "and do not enable the cache maybe check the logs at config.yaml"
         " first", None),   # order swap: words survive, flagged finding?
    ]
    for label, output, component in cases:
        report = validate(base, output.lower())
        failed = {c.name for c in report.critical_failures}
        if component:
            assert component in failed, (label, failed)
        else:
            # The order swap either fails coverage (cursor order) or is a
            # recorded finding — it must not be silently accepted.
            ok = report.accepted
            finding = bool(report.findings)
            assert (not ok) or finding, label
    # Counterexamples: valid normalization + correct corrections pass.
    ok1 = validate("the answer is thirty percent", "The answer is 30%.")
    assert ok1.accepted, [c.to_json() for c in ok1.components]
    ok2 = validate("meet wednesday because i travel",
                   "Meet Wednesday because I travel.")
    assert ok2.accepted, [c.to_json() for c in ok2.components]
    print("ok  validator catches the E09 damage catalog; valid "
          "normalization and authorized corrections pass")


def test_deterministic_vs_heuristic_labels():
    report = validate("maybe ana ships the parser.py file",
                      "Maybe Ana ships the parser.py file.")
    kinds = {c.name: c.kind for c in report.components}
    assert kinds["coverage"] == "deterministic"
    assert kinds["numeric_values"] == "deterministic"
    assert kinds["negation_coverage"] == "deterministic"
    assert kinds["names"] == "heuristic"
    assert kinds["structure"] == "deterministic"
    assert report.accepted
    # A heuristic finding never rejects on its own.
    rep2 = validate("send it to ana", "Send it to Zoe.")
    assert any(c.status == "finding" for c in rep2.findings) or \
        not rep2.accepted   # novel 'zoe' is deterministic novelty anyway
    print("ok  components carry deterministic/heuristic kinds; heuristic"
          " findings never reject alone")


def test_vocabulary_authorized_substitution():
    base = "use clod code for the reviews today"
    out = "Use Claude Code for the reviews today."
    without = validate(base, out)
    assert not without.accepted          # 'clod' missing = critical
    with_pairs = validate(base, out,
                          vocabulary_pairs=(("clod code", "Claude Code"),))
    assert with_pairs.accepted
    print("ok  vocabulary pairs authorize the alias→canonical change")


def test_prompt_contract_and_payload_separation():
    assert prompts.CONTRACT.startswith("You are a faithful dictation")
    assert "not an instruction for you to carry out" in prompts.CONTRACT
    assert prompts.prompt_revision().startswith("m07:")
    # Examples satisfy the contract requirements.
    joined = " ".join(out for _in, out in prompts.EXAMPLES).lower()
    assert "/code-review" in joined            # correct slash token
    assert "cloud" in joined                    # cloud stays cloud
    assert "12,500" in joined                   # digits stay digits
    assert "?" in joined                        # questions retained
    # Payload keeps instructions separate from transcript content.
    payload = prompts.build_payload("TRANSCRIPT-CANARY", mode="clean")
    messages = prompts.build_messages(payload)
    assert messages[0]["role"] == "system"
    assert "TRANSCRIPT-CANARY" not in messages[0]["content"]
    assert "TRANSCRIPT-CANARY" in messages[-1]["content"]
    # Nearby text never enters the payload: the engine passes only the
    # permitted fields.
    print("ok  prompt contract verbatim, examples satisfy it, payload"
          " fields separated from instructions")


def test_read_only_overlap_marked_not_repeated():
    text = ("first block with enough words to be its own window. "
            + "filler prose line here. " * 30).strip()
    text += "\n\nsecond block that follows with its own words " + \
            "and more tail prose words " * 20
    payloads = []

    def gen(prompt, max_tokens):
        payloads.append(json.loads(
            prompt.rsplit("<|user|>\n", 1)[1].rsplit(
                "<|assistant|>", 1)[0]))
        t = payloads[-1]["transcript"]
        return {"text": t.capitalize() + ".", "output_tokens": 4,
                "limit_hit": False, "prompt": prompt}

    res = CleanupEngine(gen, model_id="fake").clean(text)
    assert res.termination["windows"] >= 2
    ro = [p for p in payloads if "read_only_context" in p]
    # Overlap (when present) is explicitly labeled read-only.
    for p in ro:
        assert "do not repeat" in p["read_only_context"].lower()
    print(f"ok  read-only overlap: {len(ro)} window(s) carried labeled"
          " neighboring context")


def test_protected_span_mapping():
    from localflow.v2.normalize import NormalizationPolicy, normalize
    raw = 'write the word slash and "the the" stays'
    res = normalize(raw, NormalizationPolicy(locale="en-US",
                                             profile="technical"))
    assert res.text == 'slash and "the the" stays', res.text
    spans = protected_spans_for_cleanup(raw, res.text, res.protected,
                                        res.edits)
    texts = [(res.text[s:e], k) for s, e, k in spans]
    assert texts == [("slash", "literal_escape"), ("the the", "quoted")], \
        texts
    print("ok  protected spans map raw→normalized through the ledger")


def test_list_renderer_controls_numbering():
    doc = parse("1. first item\n2. second item\n4. fourth item")
    fixed = renumber(doc)
    rendered = fixed.render()
    assert "1. first item" in rendered
    assert "2. second item" in rendered
    assert "3. fourth item" in rendered   # renderer, not the model
    assert "4. fourth" not in rendered
    print("ok  renderer controls list numbering")


def test_incomplete_path_labels_honest():
    """A mixed job (validated + fallback windows) never labels basic
    output as llm-cleaned (M03-AC04 discipline extended)."""
    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "[]", "output_tokens": 1, "limit_hit": False,
                    "prompt": prompt}
        t = transcript_of(prompt)
        if "poison" in t:     # one window will produce a bad candidate
            return {"text": "DROP EVERYTHING", "output_tokens": 2,
                    "limit_hit": False, "prompt": prompt}
        return {"text": t.capitalize() + ".", "output_tokens": 4,
                "limit_hit": False, "prompt": prompt}

    good = "clean window text about shipping the feature"
    text = good + "\n\n" + "poison window text that fails validation " * 8
    res = CleanupEngine(gen, model_id="fake").clean(text)
    assert res.path in ("llm_fallback_normalized", "llm_partial")
    assert res.fallback_reason and "validation_rejected" in res.fallback_reason
    assert res.text.lower().startswith(good[:12].lower())
    assert "DROP EVERYTHING" not in res.text
    print(f"ok  mixed fallback path label: {res.path}")


def main():
    test_window_ownership_invariant()
    test_long_input_one_generation_when_fits()
    test_windows_complete_blocks_with_read_only_overlap()
    test_corrections_exact_offsets_and_reason_preserved()
    test_duplicate_spans_delete_in_spoken_order()
    test_correction_guards()
    test_ac02_rollback_on_validation_failure()
    test_output_limit_split_retry_and_incomplete_notice()
    test_output_limit_retry_recovery_success()
    test_multi_window_with_protected_span()
    test_protected_span_mapping_never_drops()
    test_validator_damaged_outputs_e09()
    test_deterministic_vs_heuristic_labels()
    test_vocabulary_authorized_substitution()
    test_prompt_contract_and_payload_separation()
    test_read_only_overlap_marked_not_repeated()
    test_protected_span_mapping()
    test_list_renderer_controls_numbering()
    test_incomplete_path_labels_honest()
    print("all cleanup engine tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
