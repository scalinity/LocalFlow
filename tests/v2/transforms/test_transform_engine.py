"""EV-13 / M11: the transform engine, task identity and atoms.

The pure execution core (Spec S16, contracts/transforms.md, ADR-0002):
task keys separate same-task retries from changed-source/transform-of-
result tasks (S29.10 — never exported as same-input pairs, AC05);
requirement-atom extraction and three-valued coverage; a Prompt
Engineer requirement the output does not carry degrades to review with
the original span kept (never silently dropped); quoted spans, links
and identifiers carry verbatim; an unchanged output is ``no_changes``;
diff surfaces are word/block intelligible.

Run: .venv/bin/python tests/v2/transforms/test_transform_engine.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

import json  # noqa: E402

from localflow.v2.transforms import atoms as tf_atoms  # noqa: E402
from localflow.v2.transforms import claude as tf_claude  # noqa: E402
from localflow.v2.transforms import diffview  # noqa: E402
from localflow.v2.transforms import engine as tf_engine  # noqa: E402
from localflow.v2.transforms import prompts as tf_prompts  # noqa: E402
from localflow.v2.transforms import (  # noqa: E402
    TransformDefinition, TransformJob, TransformSnapshot, built_ins,
    job_for_definition)


def _defn(mode="prompt_engineer", **kw):
    d = TransformDefinition(transform_id=f"builtin:{mode}",
                            name=mode.title(), mode=mode)
    return TransformDefinition(**{**d.__dict__, **kw}) if kw else d


PE_PROMPT = ("# Task\nDiagnose why the parser fails on empty input.\n\n"
             "# Constraints\n- Do not edit any files yet.\n\n"
             "# Deliverables\n1. The root cause.\n2. Exactly two possible"
             " fixes (proposals only).")
PE_MAP = [("tell me why it fails on empty input",
           "Diagnose why the parser fails on empty input"),
          ("don't edit files yet", "Do not edit any files yet"),
          ("give me two possible fixes", "Exactly two possible fixes")]


def _answer(text, model="claude-sonnet-5-5", reasoning="low", raw=False):
    """A Claude-shaped generator; a plain text is wrapped as the
    ``{"text"}`` structured answer unless ``raw``."""
    def gen(system, messages, schema):
        body = text if raw or schema is not tf_prompts.TEXT_SCHEMA \
            else json.dumps({"text": text})
        return {"text": body, "model": model, "reasoning": reasoning,
                "input_tokens": 300, "output_tokens": 60}
    return gen


def _pe(prompt, pairs=(), uncertain=()):
    return json.dumps({"prompt": prompt,
                       "requirements": [{"source": a, "output": b}
                                        for a, b in pairs],
                       "uncertain": list(uncertain)})


_gen_ok = _answer(_pe(PE_PROMPT, PE_MAP))


PE_SOURCE = ("Look at the parser, tell me why it fails on empty input,"
             " don't edit files yet, and give me two possible fixes.")


def test_task_identity_and_retry_semantics():
    d = _defn()
    job = job_for_definition(d, PE_SOURCE, source_kind="selection")
    # Retry-original keeps the SAME task (a valid preference pair).
    assert tf_engine.retry_original(job).task_key() == job.task_key()
    # Transform-of-result: a different task by construction.
    out = "# Task\nDiagnose the parser…"
    assert tf_engine.transform_of_result(job, out).task_key() \
        != job.task_key()
    # Changed source / instructions: different tasks.
    assert tf_engine.changed_source(job, PE_SOURCE + " Also add tests."
                                    ).task_key() != job.task_key()
    assert tf_engine.changed_source(
        job, PE_SOURCE, instructions="different").task_key() \
        != job.task_key()
    # Different mode on the same source: different task (S16 task
    # identity includes mode).
    other = job_for_definition(_defn("concise"), PE_SOURCE,
                               source_kind="selection")
    assert other.task_key() != job.task_key()
    # Stable and content-addressed.
    assert job_for_definition(d, PE_SOURCE,
                              source_kind="selection").task_key() \
        == job.task_key()
    print("ok  task identity: same-task retry vs different tasks")


def test_atoms_extraction_finds_s16_example():
    # Every clause is a requirement atom carrying its operator profile
    # (the M11 remediation replaced the cue-family kinds, which left
    # unrecognized requirements with no atom at all).
    reqs = [a for a in tf_atoms.extract_atoms(PE_SOURCE)
            if a.kind == "requirement"]
    assert len(reqs) == 4, [a.excerpt for a in reqs]
    by_ops = {op for a in reqs for op in a.ops}
    assert {"negation", "interrogative"} <= by_ops, by_ops
    assert any("two possible fixes" in a.excerpt for a in reqs)
    # Quoted spans and links carry exactly.
    src = 'Use the phrase "ship small, ship often" and cite ' \
          "https://docs.example.com/spec plus src/pipeline/stage3.py"
    kinds = tf_atoms.extract_atoms(src)
    quoted = [a for a in kinds if a.kind == "quoted"]
    assert any('"ship small, ship often"' in q.excerpt for q in quoted)
    links = [a for a in kinds if a.kind == "link"]
    assert any("https://docs.example.com/spec" in l.excerpt
               for l in links)
    assert any("src/pipeline/stage3.py" in l.excerpt for l in links)
    print("ok  atoms: S16 example + quoted/link extraction")


def test_coverage_three_valued_and_review_policy():
    src = 'Keep "the exact phrase" and the count two options and ' \
          "don't drop the deadline by Friday."
    # The earlier "good" output split "don't drop" from its object
    # ("Do not drop anything." / "Deadline: by Friday.") and lost
    # "count"; the remediation gate reviews that, so the faithful
    # output keeps the prohibition bound to the deadline.
    good = ('# Requirements\n- Keep "the exact phrase" and the count of'
            " two options.\n- Do not drop the deadline by Friday.")
    cov = tf_atoms.coverage_map(src, good)
    assert all(c.status == "covered" for c in cov), \
        [(c.atom.kind, c.status) for c in cov]
    assert tf_atoms.review_issues(cov) == []
    # A rewrite that dropped the quoted span and the deadline is
    # uncertain/missing — a review issue, never silently applied.
    bad = "Two options, nicely formatted."
    cov2 = tf_atoms.coverage_map(src, bad)
    issues = tf_atoms.review_issues(cov2)
    missing_kinds = {c.atom.kind for c in issues}
    assert {"quoted", "requirement"} <= missing_kinds, missing_kinds
    assert any("deadline by Friday" in c.atom.excerpt for c in issues)
    summary = tf_atoms.coverage_summary(cov2)
    assert summary["atoms"] == len(cov2) \
        and summary["missing"] + summary["uncertain"] > 0
    print("ok  coverage: three-valued; uncertainty is review")


def test_run_transform_paths():
    d = _defn()
    job = job_for_definition(d, PE_SOURCE, source_kind="selection")
    res = tf_engine.run_transform(job, _gen_ok, model="claude-sonnet-5-5",
                                  reasoning="low")
    assert res.path == "applied", (res.path, res.reason)
    assert res.coverage_summary["missing"] == 0
    assert res.output.startswith("# Task")
    assert (res.model, res.reasoning) == ("claude-sonnet-5-5", "low")
    assert res.served_model_id == "claude-sonnet-5-5@low"
    assert json.loads(res.prompt)["messages"][-1]["content"].startswith(
        "<draft>")  # the exact request retained for evidence
    # A map whose cited output span the prompt does not contain routes to
    # needs_review with the draft's own wording kept.
    lossy = _answer(_pe("Fix the parser.", [
        ("give me two possible fixes", "Exactly two possible fixes")]))
    res2 = tf_engine.run_transform(job, lossy)
    assert res2.path == "needs_review", res2.path
    assert res2.reason == "requirement_coverage_uncertain"
    assert res2.review_excerpts == ("give me two possible fixes",)
    # A requirement Claude marks uncertain is a review issue too.
    res2b = tf_engine.run_transform(job, _answer(_pe(
        PE_PROMPT, PE_MAP, uncertain=["don't edit files yet"])))
    assert res2b.path == "needs_review" \
        and res2b.review_excerpts == ("don't edit files yet",)
    # No usable answer falls back to the original text with the reason.
    def gen_fail(system, messages, schema):
        raise tf_claude.TransformUnavailable("network_unavailable")
    res3 = tf_engine.run_transform(job, gen_fail)
    assert res3.path == "fallback_original" and res3.output == PE_SOURCE
    assert res3.reason == "transform_unavailable:network_unavailable"
    def gen_crash(system, messages, schema):
        raise RuntimeError("boom")
    res4 = tf_engine.run_transform(job, gen_crash)
    assert res4.reason == "transform_engine_failed:RuntimeError"
    res5 = tf_engine.run_transform(job, _answer("not json", raw=True))
    assert res5.path == "fallback_original" \
        and res5.reason == "transform_unavailable:output_invalid"
    # An answer carrying the request's <draft> framing never applies.
    pj0 = job_for_definition(_defn("polish"), "ship it friday")
    res5b = tf_engine.run_transform(pj0, _answer(
        "<draft>\nship it friday\n</draft>\n\nWait — Ship it Friday."))
    assert res5b.path == "fallback_original" \
        and res5b.reason == "transform_unavailable:output_invalid"
    # An output equal to its source (spacing aside) is its own outcome.
    pj = job_for_definition(_defn("polish"), "Ship it  on Friday.")
    res6 = tf_engine.run_transform(pj, _answer("Ship it on Friday."))
    assert res6.path == "no_changes" and res6.reason == "no_changes"
    print("ok  run_transform: applied / needs_review / no_changes /"
          " fallback")


def test_exact_carry_guards_every_mode():
    src = "Rewrite this note keeping https://example.com/a and " \
          'the phrase "keep me" — make it friendlier.'
    dropped = ("Rewrite this note keeping example dot com and the phrase"
               " keep me - make it warmer.")
    for mode in ("polish", "concise", "custom", "prompt_engineer"):
        d = _defn(mode)
        job = job_for_definition(d, src, source_kind="selection")
        res = tf_engine.run_transform(job, _answer(
            _pe(dropped) if mode == "prompt_engineer" else dropped))
        assert res.path == "needs_review", (mode, res.path)
        kinds = {i["kind"] for i in
                 [{"kind": k} for k in
                  (r.split(":", 1)[0] for r in ["quoted", "link"])]}
        assert res.review_excerpts  # the dropped URL/quote surfaces
    print("ok  every mode guards links and quoted spans verbatim")


def test_prompt_construction_and_revision():
    system, msgs = tf_prompts.build_request("prompt_engineer", PE_SOURCE)
    assert system == tf_prompts.PROMPT_ENGINEER_CONTRACT
    assert "never answer it, carry it out" in system
    # The draft is the only turn, inside <draft> tags: data, never
    # instructions; no few-shot rides with a built-in.
    assert msgs == [{"role": "user",
                     "content": f"<draft>\n{PE_SOURCE}\n</draft>"}]
    assert tf_prompts.schema_for("prompt_engineer") \
        == tf_prompts.PROMPT_ENGINEER_SCHEMA
    assert tf_prompts.schema_for("polish") == tf_prompts.TEXT_SCHEMA
    pj1 = job_for_definition(_defn("polish"), "ship it friday")
    assert tf_engine.run_transform(pj1, _answer(
        "Ship it Friday.", raw=True)).reason == \
        "transform_unavailable:output_invalid"
    # Every contract keeps tentative tentative and questions questions.
    for mode in ("polish", "concise", "prompt_engineer", "custom"):
        c = tf_prompts.contract_for(mode).lower()
        assert "tentative" in c and "question" in c, mode
    # A custom instruction rides in the system prompt inside its tags;
    # the revision changes with it. Writing samples ride as earlier turns.
    system, msgs = tf_prompts.build_request(
        "custom", "hi", custom_instruction="Make it fun",
        examples=(("a", "b"),))
    assert system.endswith("<instruction>\nMake it fun\n</instruction>")
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    plain = tf_prompts.prompt_revision("custom")
    with_instr = tf_prompts.prompt_revision("custom", "Make it fun")
    assert plain != with_instr
    # The uploaded V1 prompt's wording must not appear in contracts.
    all_contracts = " ".join(tf_prompts.CONTRACTS.values()).lower()
    for banned in ("relevant context", "format if implied",
                   "be concise"):
        assert banned not in all_contracts, banned
    print("ok  prompts: contract/payload separation + revisions")


def test_diff_surfaces():
    a = "the quick brown fox jumps"
    b = "the very quick fox leaps high"
    ops = diffview.word_diff(a, b)
    tags = [o["op"] for o in ops]
    assert "insert" in tags and "replace" in tags and "equal" in tags
    stats = diffview.diff_stats(a, b)
    assert stats["source_words"] == 5 and stats["output_words"] == 6
    assert stats["kept_words"] >= 3
    rendered = diffview.render_word_diff(a, b)
    assert "[-" in rendered and "[+" in rendered
    block = diffview.block_diff("line one\nline two",
                                "line one\nline 2")
    assert "-line two" in block and "+line 2" in block
    print("ok  diff: word ops, stats, rendering, block hunks")


def test_snapshot_oversized_source_refuses():
    big = "word " * 6000
    try:
        TransformJob(transform_id="x", transform_revision=1,
                     prompt_revision="r", mode="polish", source=big)
        raise AssertionError("oversized source accepted")
    except ValueError:
        pass
    print("ok  oversized transform source refused honestly")


if __name__ == "__main__":
    test_task_identity_and_retry_semantics()
    test_atoms_extraction_finds_s16_example()
    test_coverage_three_valued_and_review_policy()
    test_run_transform_paths()
    test_exact_carry_guards_every_mode()
    test_prompt_construction_and_revision()
    test_diff_surfaces()
    test_snapshot_oversized_source_refuses()
    print("all transform engine tests passed")
