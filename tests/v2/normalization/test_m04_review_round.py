"""M04 remediation — independent review round regressions (R1–R23).

The frozen first pass d31245f was reviewed by a separate agent in its own
worktree. Every CONFIRMED finding reproduced there is pinned here: each
test FAILS on d31245f and passes on the final repair, and pairs the
defect with the canonical positive that must keep working. Expectations
are authored strings and typed tuples, never produced by the formatter
under test.

App-seam tests (R15/R16/R18) run the real AppDelegate / collector under
the DECLARED non-native shims of tests/v2/lifecycle (portable
orchestration evidence, never native verification).

Run: .venv/bin/python tests/v2/normalization/test_m04_review_round.py
"""

import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from localflow.v2.normalize import (  # noqa: E402
    NormalizationPolicy,
    normalize,
)

TECH = NormalizationPolicy()
ES = NormalizationPolicy(locale="es-ES")
SKILLS = NormalizationPolicy(registered_skills={
    "code review": "code-review", "costs": "costs",
    "brainstorm": "brainstorm"})


def N(text, pol=TECH, ctx=None):
    return normalize(text, pol, ctx)


def classes(res):
    return {e.cls for e in res.edits}


def check(pairs, pol=TECH):
    for src, want in pairs:
        got = N(src, pol).text
        assert got == want, (src, got, want)


def test_R1_slash_command_needs_command_position():
    """Registry identity is not intent: only a clause start or an
    explicit command frame owns 'slash <alias>'."""
    for text in ("we should really slash code review time",
                 "we must drastically slash code review time",
                 "teams often slash code review time",
                 "managers slash code review time",
                 "we cut hiring and slash code review time",
                 "we don’t slash code review time",
                 "companies slash costs every year",
                 "we do slash costs regularly"):
        res = N(text, SKILLS)
        assert res.text == text, (text, res.text)
        assert "skill" not in classes(res)
    check([("slash code review", "/code-review"),
           ("add slash code review to the list",
            "add /code-review to the list"),
           ("switch to slash code review", "switch to /code-review"),
           ("go to slash code review", "go to /code-review"),
           ("run it and then do slash code review",
            "run it and then do /code-review"),
           ("please run slash brainstorm now", "please run /brainstorm now"),
           ("Done. Slash code review the PR", "Done. /code-review the PR")],
          SKILLS)
    print("ok  R1: prose subjects/adverbs/'and' keep the verb; command "
          "frames insert the token")


def test_R2_scale_and_small_number():
    check([("two thousand and twenty dollars", "$2020"),
           ("port eight thousand and eighty", "port 8080"),
           ("one thousand and one nights", "1001 nights"),
           ("ten by two thousand and five centimeters",
            "10 × 2005 cm"),
           ("March fourth two thousand and twenty six",
            "March 4, 2026")])
    res = N("two thousand and twenty dollars")
    assert [str(e.value) for e in res.edits if e.cls == "currency"] == \
        ["2020"]
    # es has no "y" after "mil": the tail must not convert alone.
    assert N("dos mil y veinte euros", ES).text == "dos mil y veinte euros"
    print("ok  R2: 'thousand and N' is one number (en); never a tail")


def test_R3_hyphenated_compounds_are_number_speech():
    for text in ("three hundred sixty-five days",
                 "two hundred twenty-five dollars",
                 "two thousand twenty-six plans"):
        assert N(text).text == text, (text, N(text).text)
    print("ok  R3: a prefix before a hyphenated compound stays words")


def test_R4_tens_before_ordinal_and_day_first_invalid():
    for text in ("the twenty fifth anniversary",
                 "in the twenty first century", "the twenty third psalm"):
        assert N(text).text == text, (text, N(text).text)
    res = N("the thirty second of May")
    assert res.text == "the thirty second of May", res.text
    assert any(r.cls == "date" and r.reason == "invalid_day"
               for r in res.rejected)
    check([("the first twenty minutes", "the first 20 minutes"),
           ("the fourth of March works for me", "March 4 works for me")])
    print("ok  R4: tens+ordinal never loses its ordinal; day-first "
          "invalid days flagged")


def test_R5_time_followed_by_content_is_not_a_clock():
    for text in ("sold at three fifty dollars", "at three fifteen percent",
                 "bake at three fifty degrees",
                 "we expect about one twenty people",
                 "it weighs about two twenty kilograms",
                 "at five thirty people"):
        res = N(text)
        assert "time" not in classes(res), (text, res.text)
    check([("the movie starts at eight fifteen sharp",
            "the movie starts at 8:15 sharp"),
           ("meet at five thirty tomorrow", "meet at 5:30 tomorrow"),
           ("at five thirty we leave", "at 5:30 we leave"),
           ("come at five thirty", "come at 5:30"),
           ("see you at five thirty PM for the review",
            "see you at 5:30 PM for the review")])
    print("ok  R5: a clock time is followed only by clause material")


def test_R6_object_pronouns_keep_punctuation_commands():
    check([("let's do that period", "let's do that."),
           ("call her period", "call her."),
           ("I told her comma thanks", "I told her, thanks"),
           ("send it to her exclamation mark", "send it to her!"),
           ("grab those comma please", "grab those, please"),
           ("what about that question mark", "what about that?")])
    for text in ("a question mark", "the comma character", "my comma key",
                 "an exclamation mark"):
        assert N(text).text == text
    print("ok  R6: determiners guard nouns; object pronouns keep commands")


def test_R7_clause_start_noun_guard_any_token_and_idempotent():
    for text in ("Period 3 starts at noon", "Pipe 2 is leaking",
                 "Colon 3 surgery went well"):
        assert N(text).text == text, (text, N(text).text)
    a = N("Period five starts at noon")
    b = N(a.text)
    assert b.text == a.text and not b.edits, (a.text, b.text)
    assert N("comma").text == ","
    print("ok  R7: clause-start noun guard independent of the next "
          "token's shape; second pass stable")


def test_R8_escape_payload_includes_written_tokens():
    check([("write the phrase version 2 is twelve percent period",
            "version 2 is twelve percent period"),
           ("write the phrase use GPT-5 for twelve percent",
            "use GPT-5 for twelve percent"),
           ("write the words twelve percent. then twelve percent",
            "twelve percent. then 12%")])
    print("ok  R8: the literal payload runs to the delimiter, whatever "
          "its tokens")


def test_R9_spoken_paths_with_dotted_names():
    check([("path slash etc slash nginx dot conf", "/etc/nginx.conf"),
           ("path slash users slash danny slash dot env",
            "/users/danny/.env"),
           ("path slash Users slash Ada slash notes dot txt",
            "/Users/Ada/notes.txt"),
           ("path slash etc slash hosts", "/etc/hosts")])
    res = N("path slash etc slash nginx dot conf")
    assert [e.value for e in res.edits if e.cls == "path"] == \
        ["/etc/nginx.conf"]
    print("ok  R9: dotted names inside spoken paths join; no hybrids")


def test_R10_flag_letter_case_and_position():
    check([("ls dash L", "ls -L"), ("tar dash X", "tar -X"),
           ("grep dash I pattern files", "grep -I pattern files"),
           ("grep dash i pattern files", "grep -i pattern files"),
           ("use dash r recursively", "use -r recursively"),
           ("run with dash dash verbose output",
            "run with --verbose output"),
           ("dash dash verbose", "--verbose"),
           ("dash I asked him", "dash I asked him")])
    print("ok  R10: flag letters keep their case; a single-letter flag "
          "follows a command")


def test_R11_may_needs_date_shaped_context():
    for text in ("the libraries we build on may first require updates",
                 "items checked in may first be inspected",
                 "May first responders get priority?"):
        res = N(text)
        assert "date" not in classes(res), (text, res.text)
    check([("May first", "May 1"), ("due on may first", "due on May 1"),
           ("deploy on march fourth", "deploy on March 4"),
           ("on May first at noon", "on May 1 at noon"),
           # narrowed: "the Nth of <month>" is date-shaped by itself
           ("the fourth of may", "May 4"),
           ("the fourth of March works for me", "March 4 works for me")])
    print("ok  R11: ambiguous month words need a date-shaped context")


def test_R12_noun_point_and_dot_do_not_block():
    check([("at this point twelve percent of users churn",
            "at this point 12% of users churn"),
           ("at that point five people left",
            "at that point 5 people left"),
           ("the dot twelve domain", "the dot 12 domain")])
    for text in ("point five percent", "one point twenty six point four"):
        assert N(text).text == text
    print("ok  R12: the nouns 'point'/'dot' are not number speech")


def test_R13_spanish_accented_numbers():
    check([("doscientos veintiséis por ciento", "226 %"),
           ("el cuatro de marzo de dos mil veintiséis",
            "4 de marzo de dos mil veintiséis"),
           ("dieciséis euros", "16€"), ("un millón de euros",
                                        "un millón de euros")], ES)
    print("ok  R13: accented es spellings are the same numbers")


def test_R14_unicode_line_breaks_are_barriers():
    for sep in (" ", " ", "\x0b", "\x0c", "\x85", "\x1e"):
        res = N("twenty" + sep + "five percent")
        assert "25" not in res.text, (repr(sep), res.text)
    print("ok  R14: every Unicode line/paragraph separator is a barrier")


def test_R19_locale_tables_have_no_writable_dict():
    p = NormalizationPolicy()
    try:
        d = p.tables.__dict__
        d["teens"] = {**p.tables.teens, "twelve": 13}
        mutated = True
    except (AttributeError, TypeError):
        mutated = False
    assert not mutated and N("twelve percent", p).text == "12%"
    print("ok  R19: LocaleTables has no instance __dict__ to rewrite")


def test_R20_corpus_component_oracle_is_exact():
    import test_m04_audit_corpus as T
    from localflow.v2.normalize.span_types import EditRecord, Span
    case = next(c for c in T.CORPUS["cases"] if c["case_id"] == "M04-C0313")

    class Fake:
        text = "10 × -200 cm"
        edits = [EditRecord(cls="dimension", op="x", input_span=Span(0, 1),
                            output_span=Span(0, 1), input_text="x",
                            output_text="10 × -200 cm",
                            value="10x-200 cm", unit="cm", layer=4,
                            reason=None)]
    ok, _why = T._structured(case, Fake())
    assert not ok, "10x-200 accepted for 10 x -20"
    print("ok  R20: dimension components compared exactly")


def test_R21_benchmark_validity_is_exact():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "m04rr_bench", ROOT / "scripts" / "v2" / "benchmark_m04.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    real = bench.normalize
    dropped = []

    def lossy(text, policy, context=None):
        # Silently skip every 4th edit (about 25% of the work) while
        # keeping every edit class present.
        res = real(text, policy, context)
        if len(res.edits) >= 8:
            dropped.append(1)
            seen, keep = {}, []
            for i, e in enumerate(res.edits):
                seen[e.cls] = seen.get(e.cls, 0) + 1
                if i % 4 == 3 and seen[e.cls] > 1:
                    continue        # drop it, but never a class's first
                keep.append(e)
            res.edits = keep
        return res

    bench.normalize = lossy
    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        code = bench.main(["--iterations-scale", "0.05"])
    bench.normalize = real
    assert dropped and code == 2, code
    print("ok  R21: a normalizer silently skipping ~25% of its work is "
          "invalid")


def test_R22_arbitration_and_apply_scale():
    text = " ".join(["twelve percent"] * 4000)
    t0 = time.monotonic()
    res = N(text)
    dt = time.monotonic() - t0
    assert len(res.edits) == 4000
    small = " ".join(["twelve percent"] * 500)
    t1 = time.monotonic()
    N(small)
    ds = time.monotonic() - t1
    # 8x the input may take at most ~16x the time (n log n with slack),
    # never the ~64x of a quadratic arbiter.
    assert dt < max(16 * ds, 0.5), (dt, ds)
    print(f"ok  R22: 8000 words / 4000 edits in {dt*1000:.0f} ms "
          f"(500-word run {ds*1000:.0f} ms)")


def test_R23_command_punctuation_and_digit_speech():
    check([("new line, hello", "hello"),
           ("hello comma, how are you", "hello, how are you"),
           ("stop period.", "stop."),
           ("oh twelve people came", "oh 12 people came"),
           ("code oh one two", "code oh one two"),
           ("the room is one oh five", "the room is one oh five")])
    print("ok  R23: a command word's own punctuation is part of it; "
          "'oh' is digit speech only next to a digit")


# ---- app seams (declared non-native shims) --------------------------------

def _app():
    sys.path.insert(0, str(ROOT / "tests" / "v2" / "lifecycle"))
    import m03_helpers as h
    return h


def test_R15_retry_does_not_inherit_previous_destination_scope():
    h = _app()
    from localflow.v2.developer import skills as v2_skills
    with tempfile.TemporaryDirectory() as td:
        a = h.App(td, start_coordinator=False)
        try:
            d = a.d
            rec = v2_skills.SkillRecord(
                name="deploy-prod", aliases=("deploy prod",),
                scope="workspace:clientA")
            d._vocab_job_state(None, m10={
                "norm_profile": "standard", "skill_records": (rec,),
                "skill_records_rev": "synthetic-ws"})
            assert "deploy prod" in dict(d._norm_policy.registered_skills)
            pol, ctx, source = d._retry_norm_state()
            assert pol.profile == "technical"
            assert "deploy prod" not in dict(pol.registered_skills)
            assert source == "retry_unscoped_default"
            assert ctx is None or not getattr(ctx, "identifiers", None)
        finally:
            a.close()
    print("ok  R15: a retry gets an unscoped snapshot, never the previous "
          "destination's workspace skills or context")


def test_R16_published_normalized_text_stays_referenced():
    from localflow.v2 import ids, store as store_mod, training
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        rec = (lambda *a, **k: None)
        consent = training.ConsentManager(st, rec)
        col = training.EvidenceCollector(st, rec, consent,
                                         lambda: {"live": "x"})
        consent.set("enabled")
        ctx = col.job_started(ids.new_id("job"), ids.new_id("fam"),
                              captured_at_utc=ids.now_utc_iso(),
                              timezone=None, utc_offset_minutes=None)
        col.on_asr_result(ctx, "twelve percent", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        real_w = st.write_text_artifact

        def w(**kw):
            if kw.get("role") == "normalization_ledger":
                raise OSError("synthetic")
            return real_w(**kw)

        st.write_text_artifact = w
        res = normalize("twelve percent", TECH)
        col.on_normalization_result(ctx, res, source_text="twelve percent",
                                    policy=TECH)
        st.write_text_artifact = real_w
        col.on_cleanup_result(ctx, res.text, cleanup_context={"x": 1})
        env = st.latest_revision(col.finalize(ctx))
        assert env["missing_reasons"]["normalization"] == \
            "retention_write_failed"
        norm_aid = env["artifact_ids"].get("normalization")
        assert norm_aid, "published normalized text is unreferenced"
        assert st.artifact(norm_aid)["role"] == "normalized_text"
        cc = st.artifact(ctx.cleanup_context_artifact)
        assert cc["parent_artifact_id"] == norm_aid, cc
        st.close()
    print("ok  R16: a fully published normalized-text artifact stays "
          "referenced (and is cleanup's parent) when the ledger fails")


def test_R18_preview_fallback_uses_configuration():
    h = _app()
    with tempfile.TemporaryDirectory() as td:
        a = h.App(td, start_coordinator=False)
        try:
            d = a.d
            d._vocab_job_state(None, m10={"norm_profile": "standard",
                                          "skill_records": (),
                                          "skill_records_rev": None})

            def boom():
                raise RuntimeError("synthetic")

            d._norm_preview_profile = boom
            out = d.hubPreviewPhrase("twelve retries failed")
            assert out["output"] == "12 retries failed", out
        finally:
            a.close()
    print("ok  R18: preview fallback resolves inherit to the configuration")


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_R") and callable(v)]
    tests.sort(key=lambda f: int(f.__name__.split("_")[1][1:]))
    for t in tests:
        t()
    print(f"all M04 review-round regressions passed ({len(tests)})")
    return 0


if __name__ == "__main__":
    import os
    code = main()
    sys.stdout.flush()
    os._exit(code)
