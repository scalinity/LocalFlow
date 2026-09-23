"""EV-13 / M11: the transform engine, task identity and atoms.

The pure execution core (Spec S16, contracts/transforms.md): task
keys separate same-task retries from changed-source/transform-of-
result tasks (S29.10 — never exported as same-input pairs, AC05);
requirement-atom extraction and three-valued coverage; uncertain
coverage degrades to review with the original clauses kept (never
silently dropped); quoted spans, links and identifiers carry verbatim;
diff surfaces are word/block intelligible.

Run: .venv/bin/python tests/v2/transforms/test_transform_engine.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.transforms import atoms as tf_atoms  # noqa: E402
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


def _gen_ok(prompt, max_tokens):
    return {"text": "# Task\nDiagnose the parser failure on empty"
                    " input.\n\n# Constraints\n- Do not edit any files"
                    " yet.\n- Scope: empty-input failure path.\n\n"
                    "# Deliverables\n1. The root cause.\n2. Exactly two"
                    " possible fixes (proposals only).",
            "output_tokens": 60, "limit_hit": False}


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
    found = {a.kind for a in tf_atoms.extract_atoms(PE_SOURCE)}
    assert {"negation", "edit_constraint", "count"} <= found, found
    counts = [a for a in tf_atoms.extract_atoms(PE_SOURCE)
              if a.kind == "count"]
    assert any("two" in c.excerpt.lower() for c in counts)
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
    good = ('# Requirements\n- Keep "the exact phrase" verbatim.\n'
            "- Offer two options.\n- Deadline: by Friday.\n"
            "- Do not drop anything.")
    cov = tf_atoms.coverage_map(src, good)
    assert all(c.status == "covered" for c in cov), \
        [(c.atom.kind, c.status) for c in cov]
    assert tf_atoms.review_issues(cov) == []
    # A rewrite that dropped the quoted span and the deadline is
    # uncertain/missing — a review issue, never silently applied.
    bad = "Two options, nicely formatted."
    cov2 = tf_atoms.coverage_map(src, bad)
    missing_kinds = {c.atom.kind for c in tf_atoms.review_issues(cov2)}
    assert {"quoted", "deadline"} <= missing_kinds, missing_kinds
    summary = tf_atoms.coverage_summary(cov2)
    assert summary["atoms"] == len(cov2) \
        and summary["missing"] + summary["uncertain"] > 0
    print("ok  coverage: three-valued; uncertainty is review")


def test_run_transform_paths():
    d = _defn()
    job = job_for_definition(d, PE_SOURCE, source_kind="selection")
    res = tf_engine.run_transform(job, _gen_ok)
    assert res.path == "applied", (res.path, res.reason)
    assert res.coverage_summary["missing"] == 0
    assert res.output.startswith("# Task")
    assert res.prompt  # exact rendered prompt retained for evidence
    # A generation that loses the count and the no-edit constraint
    # routes to needs_review with the original clauses kept.
    def gen_lossy(prompt, max_tokens):
        return {"text": "Fix the parser.", "output_tokens": 8,
                "limit_hit": False}
    res2 = tf_engine.run_transform(job, gen_lossy)
    assert res2.path == "needs_review", res2.path
    assert res2.reason == "requirement_coverage_uncertain"
    assert res2.review_excerpts  # original wording kept for review
    # A failed/limit generation falls back to the original text.
    def gen_fail(prompt, max_tokens):
        raise RuntimeError("metal fault")
    res3 = tf_engine.run_transform(job, gen_fail)
    assert res3.path == "fallback_original" and res3.output == PE_SOURCE
    def gen_limit(prompt, max_tokens):
        return {"text": "# Task\nDiagn…", "output_tokens": max_tokens,
                "limit_hit": True}
    res4 = tf_engine.run_transform(job, gen_limit)
    assert res4.path == "fallback_original" \
        and res4.reason == "output_limit", res4.reason
    print("ok  run_transform: applied / needs_review / fallback")


def test_exact_carry_guards_every_mode():
    src = "Rewrite this note keeping https://example.com/a and " \
          'the phrase "keep me" — make it friendlier.'
    def gen_drop(prompt, max_tokens):
        return {"text": "Rewrite this note keeping example dot com"
                        " and the phrase keep me - make it warmer.",
                "output_tokens": 30, "limit_hit": False}
    for mode in ("polish", "concise", "custom"):
        d = _defn(mode)
        job = job_for_definition(d, src, source_kind="selection")
        res = tf_engine.run_transform(job, gen_drop)
        assert res.path == "needs_review", (mode, res.path)
        kinds = {i["kind"] for i in
                 [{"kind": k} for k in
                  (r.split(":", 1)[0] for r in ["quoted", "link"])]}
        assert res.review_excerpts  # the dropped URL/quote surfaces
    print("ok  every mode guards links and quoted spans verbatim")


def test_prompt_construction_and_revision():
    msgs = tf_prompts.build_messages(
        "prompt_engineer", PE_SOURCE, locale="en-US")
    assert msgs[0]["role"] == "system"
    assert "without adding or deleting requirements" in msgs[0]["content"]
    assert '"summarize first' not in msgs[0]["content"]
    # The S16 worked example rides as few-shot.
    assert any(m["role"] == "user" and "parser" in m["content"]
               for m in msgs[:-1])
    # The payload is a labeled draft user message, instructions never
    # mixed in (the M07 discipline).
    payload = msgs[-1]["content"]
    assert payload.startswith("Draft to transform"), payload[:40]
    assert PE_SOURCE in payload and "prompt_engineer" in payload
    # Custom instruction rides as its own system message; revision
    # changes with it.
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
