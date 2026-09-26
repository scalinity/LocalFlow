"""M11 remediation regressions — the portable half (audit 2026-09-24 at
1ee8e44). No AppKit, no model: every case drives the real transform
engine with an injected generator, the real worker handler, the real
store/collector, the real insertion validator over the fixture target,
or the model-suite oracle with injected outputs.

Each case names its layer: ``engine`` (run_transform), ``worker``
(Worker._transform + the serve loop's fault branch), ``store``
(TransformStore / EvidenceCollector over a real Store), ``insertion``
(validate_target over FixtureTargetApp), ``oracle``
(test_prompt_engineer_cases.judge) or ``helper`` (a portable helper the
coordinator delegates to). The AppKit coordinator/Hub/panel cases live
in test_transform_remediation_native.py and run on the reference Mac.

"Not applied" means the result's path is not ``applied`` AND the review
excerpts are non-empty (the loss is surfaced, never silent). The audit
exposed every case here, so they are development/regression cases.

Run: .venv/bin/python tests/v2/transforms/test_transform_remediation.py
     [--json OUT.json] [--trace]
"""

import contextlib
import importlib
import importlib.util
import inspect
import io
import json
import pathlib
import re
import sys
import tempfile
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))

from localflow.v2 import ids  # noqa: E402
from localflow.v2 import transforms as tf  # noqa: E402
from localflow.v2.transforms import atoms as tf_atoms  # noqa: E402
from localflow.v2.transforms import engine as tf_engine  # noqa: E402
from localflow.v2.transforms import prompts as tf_prompts  # noqa: E402

CASES = []


def case(layer, new_interface=False):
    """Register a case. ``new_interface`` marks a case that exercises a
    portable helper introduced by the repair (it cannot reproduce on
    inherited code; the inherited behavior was reproduced natively)."""
    def deco(fn):
        CASES.append((fn, layer, new_interface))
        return fn
    return deco


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

MODES = ("polish", "concise", "prompt_engineer", "custom")


def job_for(source, mode="prompt_engineer"):
    return tf_engine.TransformJob(
        transform_id=f"builtin:{mode}", transform_revision=1,
        prompt_revision="m11:test", mode=mode, source=source,
        source_kind="selection",
        instructions="Make it friendlier." if mode == "custom" else "")


def gen_of(output, limit=False):
    def gen(prompt, max_tokens):
        return {"text": output, "output_tokens": 5, "limit_hit": limit}
    return gen


def render(messages):
    return "\n".join(m["content"] for m in messages)


def run(source, output, mode="prompt_engineer"):
    return tf.run_transform(job_for(source, mode), gen_of(output), render)


def not_applied(source, output, mode="prompt_engineer"):
    res = run(source, output, mode)
    assert res.path != tf.PATH_APPLIED, \
        f"[{mode}] applied: {source!r} -> {output!r}"
    assert res.review_excerpts, \
        f"[{mode}] no review excerpt: {source!r} -> {output!r}"
    return res


def applied(source, output, mode="prompt_engineer"):
    res = run(source, output, mode)
    assert res.path == tf.PATH_APPLIED, \
        (f"[{mode}] {res.path}: {source!r} -> {output!r}"
         f" excerpts={res.review_excerpts}")
    return res


def captured_worker(gen):
    """The real Worker._transform with the serve loop's fault branch
    reproduced; returns the messages the worker wrote."""
    from localflow.v2 import worker as worker_mod
    w = worker_mod.Worker(tempfile.mkdtemp())
    w._cleanup_generate = gen
    w._cleanup_render = render
    sent = []
    real = worker_mod._write_msg
    worker_mod._write_msg = sent.append

    def call(msg):
        try:
            w._transform(msg)
        except Exception as e:  # the serve loop's generic branch
            worker_mod._fault(msg, type(e).__name__, worker_mod._reason(e))
    return w, sent, call, (lambda: setattr(worker_mod, "_write_msg", real))


def transform_msg(source, mode="prompt_engineer"):
    return {"op": "transform", "req_id": "r1", "job_id": None,
            "attempt": 1, "generation": 1,
            "transform_id": f"builtin:{mode}", "transform_revision": 1,
            "prompt_revision": "m11:test", "mode": mode,
            "source": source, "source_kind": "selection"}


def new_store():
    from localflow.v2 import store as store_mod
    td = pathlib.Path(tempfile.mkdtemp())
    return store_mod.Store(td / "v2.db", backup_dir=td / "backups")


def rows(st, sql, args=()):
    return st.submit(lambda db: db.execute(sql, args).fetchall())


def pe_result(source, output, mode="prompt_engineer"):
    return run(source, output, mode)


# ---------------------------------------------------------------------------
# 01 — unrepresented requirements (the gate must not fail open)
# ---------------------------------------------------------------------------

F01_PAIRS = [
    ("Only update the tests if the implementation changes.",
     "Update the tests and implementation."),                      # ADV-01
    ("You may optionally add caching.", "Add caching."),            # ADV-02
    ("Use either A or B.", "Use A and B."),                         # ADV-07
    ("Ask whether Redis is appropriate here.", "Use Redis here."),  # ADV-08
    ("Only modify the frontend.",
     "Modify the frontend and backend."),                           # ADV-09
    ("Stop after planning.", "Plan and implement."),                # ADV-17
    ("Review this architecture.",
     "Review this architecture, then implement the changes, run the"
     " benchmarks and write the migration."),                       # ADV-18
    ("Return only JSON.", "Return prose."),
]


@case("engine")
def f01_unrepresented_requirements_not_applied():
    for src, out in F01_PAIRS:
        not_applied(src, out, "prompt_engineer")


@case("engine")
def f01_same_losses_under_polish_and_concise():
    # The cross-mode decision (contracts/transforms.md): Polish and
    # Concise carry the same operator/invention/exact-carry gate.
    for mode in ("polish", "concise"):
        for src, out in F01_PAIRS:
            not_applied(src, out, mode)


# ---------------------------------------------------------------------------
# 02 — false coverage: polarity, order, hedges, quantities, occurrences
# ---------------------------------------------------------------------------

@case("engine")
def f02_polarity_ordering_hedge_quantity():
    for src, out in [
            ("Do not modify the database schema.",
             "Modify the database schema."),                        # ADV-03
            ("Inspect before editing.", "Edit, then inspect."),     # ADV-06
            ("Maybe add a benchmark.", "Add a benchmark."),
            ("Fewer than five suggestions.",
             "More than five suggestions."),                        # ADV-05
            ("Never delete the logs.", "Delete the logs."),
            ("Don't run the migration until the backup finishes.",
             "Run the migration and the backup.")]:
        for mode in ("prompt_engineer", "polish", "concise"):
            not_applied(src, out, mode)


@case("engine")
def f02_negative_control_recognized_comparator():
    not_applied("At most five suggestions.", "At least five suggestions.")


@case("engine")
def f02_wrong_occurrence_and_argument_swaps():
    for src, out in [
            ("Do not modify app.py. Explain why app.py owns startup."
             " You may modify tests for app.py.",
             "Modify app.py. Explain why app.py owns startup. Modify its"
             " tests."),                                            # ADV-12
            ("Do not modify app.py. Do not modify the tests.",
             "Do not modify app.py. Modify the tests."),
            ("Edit a.py but not b.py.", "Edit b.py but not a.py."),
            ("Why does the cache miss? Fix the parser.",
             "Fix the cache miss. Why does the parser fail?"),
            ("Give three examples and five references.",
             "Give five examples and three references."),
            ("Run the tests before merging.",
             "Merge before running the tests.")]:
        not_applied(src, out, "prompt_engineer")


@case("engine")
def f02_governed_words_and_soft_conditions():
    """Found by the remediation's mutation probe: a cue governs only
    the words up to the next operator, and a soft condition ("if they
    exist") is not interchangeable with a hedge ("maybe")."""
    not_applied("Nothing gets archived without my say.",
                "Gets archived without my say.")
    not_applied("Maybe include benchmark numbers if they exist.",
                "Maybe include benchmark numbers.")
    applied("Maybe include benchmark numbers if they exist.",
            "- Maybe include benchmark numbers, if they exist.")
    not_applied("Maybe include benchmark numbers if they exist.",
                "Maybe include benchmark numbers.", "polish")


# ---------------------------------------------------------------------------
# 03 — coverage must cross the worker
# ---------------------------------------------------------------------------

@case("engine")
def f03_coverage_serializes_every_status():
    atom = tf_atoms.Atom(tf_atoms.COUNT, "exactly three options",
                         ("exactly three options",), 5, 26)
    for status in ("covered", "uncertain", "missing"):
        js = tf_atoms.Coverage(atom, status).to_json()
        assert js["kind"] == tf_atoms.COUNT and js["status"] == status
        json.dumps(js)
    res = run("Give exactly three options.", "Give exactly three options.")
    assert res.coverage, "atom-bearing source produced no coverage"
    json.loads(tf_engine.result_json_for_store(res))


@case("worker")
def f03_real_worker_round_trip_nonempty_coverage():
    src = "Give exactly three options."
    _w, sent, call, restore = captured_worker(gen_of(src))
    try:
        call(transform_msg(src))
    finally:
        restore()
    assert len(sent) == 1, sent
    msg = sent[0]
    assert msg["op"] == "result", msg
    assert msg["coverage"], "nonempty coverage expected"
    assert all("kind" in c for c in msg["coverage"])
    assert msg["result"]["path"] == tf.PATH_APPLIED, msg["result"]
    # The parent-side rebuild (the coordinator delegates to this).
    rebuild = getattr(tf_engine, "result_from_message", None)
    assert rebuild is not None, "no portable parent-side rebuild"
    res = rebuild(job_for(src), msg)
    assert res.path == tf.PATH_APPLIED and res.coverage
    assert res.coverage[0].atom.kind == msg["coverage"][0]["kind"]
    assert res.to_json()["validator_revision"] \
        == msg["result"]["validator_revision"]


@case("worker")
def f03_real_worker_fallbacks_still_answer():
    def boom(prompt, n):
        raise RuntimeError("metal fault")
    for gen, reason in ((boom, "transform_engine_failed:RuntimeError"),
                        (gen_of("# partial", limit=True), "output_limit")):
        _w, sent, call, restore = captured_worker(gen)
        try:
            call(transform_msg("Give exactly three options."))
        finally:
            restore()
        assert sent and sent[0]["op"] == "result", sent
        assert sent[0]["result"]["path"] == tf.PATH_FALLBACK_ORIGINAL
        assert sent[0]["result"]["reason"] == reason


# ---------------------------------------------------------------------------
# 04 — exact carry
# ---------------------------------------------------------------------------

@case("engine")
def f04_case_distinct_literals_stay_distinct():
    for mode in MODES:
        not_applied("Keep ABC.py and abc.py unchanged.",
                    "Keep ABC.py unchanged.", mode)


@case("engine")
def f04_technical_tokens_carry_verbatim():
    long_quote = "\"" + ("ship small and ship often " * 6).strip() + "\""
    assert len(long_quote) > 150
    for src, out in [
            ("Use Qwen3-4B-Instruct-2507 for this.",
             "Use another model for this."),
            ("Call load_config_v2 first.", "Call the config loader first."),
            ("Type /review-2 in the chat.", "Type the review command."),
            ("Open ~/Library/Application Support/LocalFlow/v2.db now.",
             "Open the LocalFlow database now."),
            ("Audit checkout.html today.", "Audit the checkout page today."),
            ("See [the spec](https://docs.example.com/spec#s16).",
             "See the spec."),
            (f"Keep {long_quote} as written.", "Keep the tagline as written."),
            ("Keep 'Start free trial' in English.",
             "Keep Start Trial in English."),
            ("Run `make check` before you push.",
             "Run the checks before you push."),
            ("Keep this block:\n```\nx = 1\ny = 2\n```\nThanks.",
             "Keep this block:\n```\nx = 1\ny = 3\n```\nThanks.")]:
        not_applied(src, out, "polish")


@case("engine")
def f04_literals_allow_surrounding_prose_edits():
    for src, out in [
            ("please read https://docs.example.com/spec.",
             "Please read https://docs.example.com/spec"),
            ("check src/pipeline/stage3.py and tell me",
             "Check src/pipeline/stage3.py and tell me."),
            ("keep ABC.py and abc.py unchanged please",
             "Please keep ABC.py and abc.py unchanged."),
            ("use Qwen3-4B-Instruct-2507 for this one",
             "Use Qwen3-4B-Instruct-2507 for this one."),
            ("see (https://example.com/a) for details",
             "See (https://example.com/a) for details.")]:
        applied(src, out, "polish")


# ---------------------------------------------------------------------------
# 05 — the model-suite oracle
# ---------------------------------------------------------------------------

def _pec():
    return importlib.import_module("test_prompt_engineer_cases")


def _fixture_cases():
    here = HERE.parent
    v2 = here / "fixtures_prompt_engineer_v2.json"
    v1 = here / "fixtures_prompt_engineer.json"
    out = {}
    for p in (v1, v2):
        if p.exists():
            for c in json.loads(p.read_text())["cases"]:
                out.setdefault(c["case_id"], {}).update(c)
    return out


def _oracle_verdict(case_d, output, path="applied", excerpts=()):
    """``judge`` when the oracle has one; else the legacy arithmetic of
    run_case/main (missing any-of groups or a forbidden substring
    fails only when applied; everything else prints as a pass)."""
    pec = _pec()
    if hasattr(pec, "judge"):
        return pec.judge(case_d, output, path, excerpts)["verdict"]
    low = output.lower()
    missing = [g for g in case_d.get("require", [])
               if not any(pec._found(a.lower(), low) for a in g)]
    added = [b for b in case_d.get("forbid_added", []) if b.lower() in low]
    if (missing or added) and path == "applied":
        return "applied_semantic_failure"
    if path == "needs_review":
        return "review_addresses_loss"
    return "applied"


@case("oracle")
def f05_oracle_never_reports_fallback_as_applied():
    pec = _pec()

    class Runner:
        def __init__(self, model):
            pass

        def load(self):
            pass

        def generate_fn(self):
            def gen(prompt, n):
                raise RuntimeError("generation failed")
            return gen

        def render(self, messages):
            return render(messages)

    real = pec.ModelRunner
    real_argv = sys.argv
    pec.ModelRunner = Runner
    sys.argv = ["test_prompt_engineer_cases.py", "--limit", "3"]
    buf = io.StringIO()
    failed = False
    try:
        with contextlib.redirect_stdout(buf):
            pec.main()
    except (AssertionError, SystemExit):
        failed = True
    finally:
        pec.ModelRunner = real
        sys.argv = real_argv
    text = buf.getvalue()
    assert "applied, all atoms survive" not in text, text[-400:]
    assert failed, "an all-fallback model run must not pass"


@case("oracle")
def f05_oracle_fixture_relations():
    cases = _fixture_cases()
    bad = {
        # benchmark made mandatory and unconditional
        "PE-DEV-010": ("# Task\nEvaluate the caching approach.\n\n"
                       "# Requirements\n- Include benchmark numbers.\n"
                       "- Flag anything uncertain."),
        # five detached from the questions; no per-question hints
        "PE-VAL-004": ("# Task\nInterview prep.\n- Give five tips.\n"
                       "- List the most likely questions.\n- Write an"
                       " answer hint.\n- Never write full answers for me."
                       " Keep it to one sentence."),
        # proceeds regardless when a lead is unavailable
        "PE-HOLD-006": ("# Task\nGet the on-call runbook reviewed by both"
                        " platform leads before Thursday's freeze.\n"
                        "- If either is unavailable, say so and proceed"
                        " with the other."),
        # 'three' once — positives and negatives not both counted
        "PE-HOLD-010": ("# Retrospective\n- Three things that went well"
                        " and what didn't.\n- One experiment for next"
                        " sprint.\n- Nothing about tooling; that is a"
                        " separate meeting."),
    }
    for cid, out in bad.items():
        v = _oracle_verdict(cases[cid], out)
        assert v == "applied_semantic_failure", (cid, v)
    good = ("# Task\nRequest the changelog for versions 1.2.6 through"
            " 1.3.0 only.\n- Order: reverse order.\n- Include links to"
            " the PRs.\n- Do not include code snippets.")
    v = _oracle_verdict(cases["PE-HOLD-004"], good)
    assert v == "applied", v


@case("oracle")
def f05_oracle_checks_review_addresses_the_loss():
    pec = _pec()
    assert hasattr(pec, "judge"), "oracle has no independent judge"
    c = _fixture_cases()["PE-DEV-005"]
    out = ("# Task\nTrace the bug in src/pipeline/stage3.py and report"
           " only the root cause.")
    v = pec.judge(c, out, "needs_review",
                  ("trace the bug in src/pipeline/stage3.py",))["verdict"]
    assert v == "review_misdirected", v
    v = pec.judge(c, out, "needs_review",
                  ("without modifying any file",))["verdict"]
    assert v == "review_addresses_loss", v
    assert pec.judge(c, c["source"], "fallback_original")["verdict"] \
        == "fallback"


# ---------------------------------------------------------------------------
# 06 — selected-text replacement authority (portable layers)
# ---------------------------------------------------------------------------

def _strict_snapshot(tgt, *, rng, text, title="Doc A.txt",
                     preceding=None, following=None, role="AXTextArea"):
    from localflow.v2.context.snapshot import (ContextSnapshot,
                                               FieldContext, TargetSnapshot)
    target = TargetSnapshot(target_snapshot_id=ids.new_id("tgt"),
                            app_bundle=tgt.bundle, app_pid=tgt.pid)
    field = FieldContext(role=role, classification="text",
                         selected_text=text, selected_range=rng,
                         preceding_text=preceding, following_text=following)
    return ContextSnapshot(context_snapshot_id=ids.new_id("ctx"),
                           stage="transform_selection", target=target,
                           field=field, window_title=title)


def _titled(t):
    """The fixture's window title reads through ``focused_window_title``
    (the system host's method shape; added to fixture_target.py by the
    remediation). Older fixtures answered no title at all."""
    if not hasattr(type(t), "focused_window_title"):
        t.focused_window_title = lambda el: t.window_title \
            if t.ax_readable else None
    return t


@case("insertion")
def f06_strict_replacement_requires_positive_proof():
    from fixture_target import FixtureTargetApp
    from localflow.v2.insertion.validation import validate_target
    strict = {"job_id": "tcand_x", "attempt": 1,
              "strict_replacement": True}

    def fresh(title="Doc A.txt"):
        t = _titled(FixtureTargetApp(window_title=title))
        t.set_content("alpha rewrite this rough sentence omega")
        t.selection = (6, 33)
        return t
    # Positive proof: selection, title and surroundings all match.
    t = fresh()
    snap = _strict_snapshot(t, rng=(6, 33),
                            text="rewrite this rough sentence",
                            preceding="alpha ", following=" omega")
    lease, ver = validate_target(t, snap, strict)
    assert lease is not None and lease.replace_selection, ver
    # FLOW-03: the selection became unreadable — no replacement.
    t = fresh()
    t.ax_readable = False
    lease, ver = validate_target(t, snap, strict)
    assert lease is None, ("unreadable selection granted strict", ver)
    # A recorded title that cannot be read now refuses.
    t = fresh()
    t.focused_window_title = lambda el: None
    lease, ver = validate_target(t, snap, strict)
    assert lease is None, ("unreadable window title granted strict", ver)
    # FLOW-02 variant: same app, same title, same role/range/text, but
    # the surrounding text differs (another document).
    t = fresh()
    t.set_content("gamma rewrite this rough sentence delta!")
    t.selection = (6, 33)
    lease, ver = validate_target(t, snap, strict)
    assert lease is None, ("different surroundings granted strict", ver)
    # A strict job without a recorded title refuses outright.
    t = fresh()
    snap2 = _strict_snapshot(t, rng=(6, 33),
                             text="rewrite this rough sentence", title=None,
                             preceding="alpha ", following=" omega")
    lease, ver = validate_target(t, snap2, strict)
    assert lease is None, ("strict job without a window title", ver)


@case("insertion")
def f06_plain_dictation_contract_unchanged():
    """Control: M08 plain dictation keeps its permissive rules (an
    unreadable recorded selection still gets a lease)."""
    from fixture_target import FixtureTargetApp
    from localflow.v2.insertion.validation import validate_target
    t = FixtureTargetApp(window_title="Doc A.txt")
    t.set_content("alpha rewrite this rough sentence omega")
    t.selection = (6, 33)
    snap = _strict_snapshot(t, rng=(6, 33),
                            text="rewrite this rough sentence")
    t.ax_readable = False
    lease, ver = validate_target(t, snap, {"job_id": "job_1",
                                           "attempt": 1})
    assert lease is not None, ver


@case("helper", new_interface=True)
def f06_capture_classifies_before_reading():
    from fixture_target import FixtureTargetApp
    from localflow.v2.insertion.selection import capture_selection
    t = FixtureTargetApp(role="AXSecureTextField")
    t.set_content("hunter2")
    t.selection = (0, 7)
    reads = []
    real = t.attribute

    def spy(el, name):
        reads.append(name)
        return real(el, name)
    t.attribute = spy
    real_range = t.string_for_range
    t.string_for_range = lambda *a: reads.append("range_text") \
        or real_range(*a)
    capture, reason = capture_selection(t, denied_apps=())
    assert capture is None and reason == "secure_field", (capture, reason)
    assert "AXSelectedTextRange" not in reads and "range_text" not in reads


@case("helper", new_interface=True)
def f06_capture_records_window_and_surroundings():
    from fixture_target import FixtureTargetApp
    from localflow.v2.insertion.selection import capture_selection
    t = _titled(FixtureTargetApp(window_title="Doc A.txt"))
    t.set_content("alpha rewrite this rough sentence omega")
    t.selection = (6, 33)
    capture, reason = capture_selection(t, denied_apps=())
    assert capture is not None, reason
    snap = capture["snapshot"]
    assert capture["source"] == "rewrite this rough sentence"
    assert snap.window_title == "Doc A.txt"
    assert snap.field.classification == "text"
    assert snap.field.preceding_text == "alpha "
    assert snap.field.following_text == " omega"
    t.bundle = "com.example.denied"
    t.frontmost_info["bundle"] = t.bundle
    assert capture_selection(t, denied_apps=("com.example.denied",))[1] \
        == "app_denied"


# ---------------------------------------------------------------------------
# 07 — Scratchpad destination authority (portable helpers)
# ---------------------------------------------------------------------------

@case("helper", new_interface=True)
def f07_note_destination_identity_and_region():
    from localflow.v2.notes import note_destination_check
    dest = {"note_id": "note_A", "revision_id": "rev_1",
            "range": (0, 5), "text": "alpha"}
    ok, reason = note_destination_check(dest, "note_A", "alpha beta")
    assert ok and reason is None
    assert note_destination_check(dest, "note_B", "alpha beta") \
        == (False, "note_changed")
    assert note_destination_check(dest, "note_A", "ALPHA beta") \
        == (False, "note_range_changed")
    assert note_destination_check(None, "note_A", "alpha") \
        == (False, "no_destination")
    assert note_destination_check(dest, None, "alpha") \
        == (False, "note_not_open")


@case("helper", new_interface=True)
def f07_utf16_offsets_convert():
    from localflow.v2.notes import utf16_range_to_codepoints
    text = "😀 alpha beta"
    # NSRange of "alpha" in UTF-16 units: the emoji is 2 units.
    s, e = utf16_range_to_codepoints(text, 3, 5)
    assert text[s:e] == "alpha", (s, e, text[s:e])
    s, e = utf16_range_to_codepoints("plain alpha", 6, 5)
    assert (s, e) == (6, 11)
    s, e = utf16_range_to_codepoints("a😀b", 1, 2)
    assert "a😀b"[s:e] == "😀"


# ---------------------------------------------------------------------------
# 08 / 09 / 10 — evidence (store and collector layers)
# ---------------------------------------------------------------------------

def _tstore():
    from localflow.v2 import training
    from localflow.v2.transforms_store import TransformStore
    st = new_store()
    consent = training.ConsentManager(st, lambda *a, **k: None)
    return st, consent, TransformStore(st)


def _count_candidates(st):
    return (rows(st, "SELECT COUNT(*) FROM transform_candidates")[0][0],
            rows(st, "SELECT COUNT(*) FROM artifacts WHERE role LIKE"
                     " 'transform%'")[0][0])


@case("store")
def f08_store_candidate_respects_collection_consent():
    src = "Give exactly three options."
    res = pe_result(src, src)
    for state in (None, "disabled", "paused"):
        st, consent, ts = _tstore()
        try:
            if state:
                consent.set(state, note="test")
            cid = ts.record_candidate(res, source_artifact_text=src,
                                      output_artifact_text=res.output)
            assert cid is None, (state, cid)
            assert _count_candidates(st) == (0, 0), (state,
                                                    _count_candidates(st))
        finally:
            st.close()
    st, consent, ts = _tstore()
    try:
        consent.set("enabled", note="test")
        cid = ts.record_candidate(res, source_artifact_text=src,
                                  output_artifact_text=res.output)
        assert cid and _count_candidates(st)[0] == 1
        # Revoked while the generation ran: the write-time state wins.
        consent.set("disabled", note="test")
        assert ts.record_candidate(res, source_artifact_text=src,
                                   output_artifact_text=res.output) is None
        assert _count_candidates(st)[0] == 1
    finally:
        st.close()


@case("store")
def f08_dictation_candidate_follows_captured_consent():
    src = "Give exactly three options."
    res = pe_result(src, src)
    sig = inspect.signature(
        importlib.import_module(
            "localflow.v2.transforms_store").TransformStore.record_candidate)
    assert "collecting" in sig.parameters, \
        "no captured-consent parameter for the dictation path"
    st, consent, ts = _tstore()
    try:
        consent.set("enabled", note="test")
        assert ts.record_candidate(res, task_kind="dictation_auto_apply",
                                   collecting=False) is None
        assert _count_candidates(st)[0] == 0
        consent.set("disabled", note="test")
        # Captured at job start (enabled): the job's evidence stays.
        assert ts.record_candidate(res, task_kind="dictation_auto_apply",
                                   collecting=True)
        assert _count_candidates(st)[0] == 1
    finally:
        st.close()


def _children(st, parent):
    return {r[0]: (r[1], json.loads(r[2] or "{}")) for r in rows(
        st, "SELECT role, content_text, meta_json FROM artifacts WHERE"
            " parent_artifact_id=?", (parent,))}


@case("store")
def f09_selected_candidate_retains_prompt_and_decision():
    src = "Do not modify the database schema."
    res = pe_result(src, "Modify the database schema.")
    assert res.path == tf.PATH_NEEDS_REVIEW, res.path
    st, consent, ts = _tstore()
    try:
        consent.set("enabled", note="test")
        cid = ts.record_candidate(res, source_artifact_text=src,
                                  output_artifact_text=res.output)
        out_art = rows(st, "SELECT output_artifact_id FROM"
                           " transform_candidates WHERE candidate_id=?",
                       (cid,))[0][0]
        kids = _children(st, out_art)
        assert "transform_prompt" in kids, kids.keys()
        assert kids["transform_prompt"][0] == res.prompt
        assert "transform_decision" in kids, kids.keys()
        decision = json.loads(kids["transform_decision"][0])
        assert decision["path"] == res.path
        assert decision["review_excerpts"] == list(res.review_excerpts)
        assert decision["coverage"] and decision["validator_revision"]
    finally:
        st.close()


@case("store")
def f09_note_candidate_records_destination_revision():
    src = "alpha beta"
    res = pe_result(src, "Alpha beta.", "polish")
    st, consent, ts = _tstore()
    try:
        consent.set("enabled", note="test")
        kw = {}
        if "source_meta" in inspect.signature(ts.record_candidate).parameters:
            kw["source_meta"] = {"note_id": "note_A",
                                 "note_revision_id": "rev_1"}
        cid = ts.record_candidate(res, task_kind="transform_note",
                                  source_artifact_text=src,
                                  output_artifact_text=res.output, **kw)
        meta = json.loads(rows(
            st, "SELECT a.meta_json FROM artifacts a JOIN"
                " transform_candidates c ON c.source_artifact_id ="
                " a.artifact_id WHERE c.candidate_id=?", (cid,))[0][0])
        assert meta.get("note_id") == "note_A", meta
        assert meta.get("note_revision_id") == "rev_1", meta
    finally:
        st.close()


@case("store")
def f09_dictation_decision_map_retained():
    from localflow.v2 import training
    src = "Do not modify the database schema."
    res = pe_result(src, src)
    st = new_store()
    try:
        consent = training.ConsentManager(st, lambda *a, **k: None)
        consent.set("enabled", note="test")
        coll = training.EvidenceCollector(st, lambda *a, **k: None,
                                          consent, lambda: {"p": "t"})
        ctx = coll.job_started(ids.new_id("job"), ids.new_id("fam"),
                               captured_at_utc=ids.now_utc_iso(),
                               timezone="UTC", utc_offset_minutes=0)
        coll.on_transform_result(ctx, res, applied=True)
        st.sync()
        roles = {r[0]: r[1] for r in rows(
            st, "SELECT role, content_text FROM artifacts WHERE job_id=?",
            (ctx.job_id,))}
        assert "transform_decision" in roles, roles.keys()
        decision = json.loads(roles["transform_decision"])
        assert decision["path"] == res.path and decision["coverage"]
        assert ctx.transform_block["validator_revision"]
    finally:
        st.close()


@case("store")
def f10_retry_lineage_recorded_on_the_new_candidate():
    src = "alpha beta"
    res = pe_result(src, "Alpha beta.", "polish")
    st, consent, ts = _tstore()
    try:
        consent.set("enabled", note="test")
        first = ts.record_candidate(res, source_artifact_text=src,
                                    output_artifact_text=res.output)
        kw = {}
        if "retry_of" in inspect.signature(ts.record_candidate).parameters:
            kw["retry_of"] = first
        second = ts.record_candidate(res, source_artifact_text=src,
                                     output_artifact_text=res.output,
                                     display_order=2, **kw)
        meta = json.loads(rows(
            st, "SELECT a.meta_json FROM artifacts a JOIN"
                " transform_candidates c ON c.output_artifact_id ="
                " a.artifact_id WHERE c.candidate_id=?", (second,))[0][0])
        assert meta.get("retry_of") == first, meta
        assert rows(st, "SELECT COUNT(*) FROM preference_observations"
                    )[0][0] == 0
    finally:
        st.close()


# ---------------------------------------------------------------------------
# 11 — preview action geometry (the pure layout; hit-testing is native)
# ---------------------------------------------------------------------------

@case("helper", new_interface=True)
def f11_action_frames_do_not_overlap():
    import types
    stubs = {}
    if importlib.util.find_spec("AppKit") is None:
        appkit = types.ModuleType("AppKit")
        for name in ("NSButton", "NSMakeRect", "NSMenu", "NSMenuItem",
                     "NSPanel", "NSSize", "NSScrollView", "NSTextView",
                     "NSView", "NSWindowStyleMaskClosable",
                     "NSWindowStyleMaskNonactivatingPanel",
                     "NSWindowStyleMaskResizable",
                     "NSWindowStyleMaskTitled"):
            setattr(appkit, name, 0)
        foundation = types.ModuleType("Foundation")
        foundation.NSObject = type("NSObject", (), {})
        objc_mod = types.ModuleType("objc")
        objc_mod.python_method = lambda f: f
        stubs = {"AppKit": appkit, "Foundation": foundation,
                 "objc": objc_mod}
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            "_panel_layout", HERE.parents[3] / "localflow" / "v2" / "ui"
            / "transforms_panel.py",
            submodule_search_locations=None)
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "localflow.v2.ui"
        spec.loader.exec_module(mod)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    frames = mod.action_frames()
    assert len(frames) == len(mod._ACTIONS)
    for i, a in enumerate(frames):
        for b in frames[i + 1:]:
            overlap = (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                       and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])
            assert not overlap, (a, b)
    min_w = 460.0
    assert max(x + w for x, _y, w, _h in frames) + 12.0 <= min_w, frames


# ---------------------------------------------------------------------------
# 12 — unchanged quoted literals
# ---------------------------------------------------------------------------

@case("engine")
def f12_unchanged_quoted_literal_applies():
    for mode in MODES:
        res = applied('Keep "foo" unchanged.', 'Keep "foo" unchanged.', mode)
        assert len(res.review_excerpts) == len(set(res.review_excerpts))


# ---------------------------------------------------------------------------
# preservation controls and test gaps
# ---------------------------------------------------------------------------

@case("engine")
def pc_faithful_reorganizations_apply():
    applied(tf_prompts.PE_EXAMPLE_USER, tf_prompts.PE_EXAMPLE_ASSISTANT)
    for src in ("Do not modify the database schema.",
                "Only update the tests if the implementation changes.",
                "You may optionally add caching.",
                "Ask whether Redis is appropriate here."):
        applied(src, src)
    applied("First outline the chapter, then critique the outline.",
            "# Task\n1. Outline the chapter.\n2. Critique the outline.")
    applied("Do not modify app.py.", "# Constraints\n- Do not modify app.py.")
    applied("please send me the report by friday and don't forget the"
            " charts", "Please send me the report by Friday, and don't"
            " forget the charts.", "polish")
    applied("so basically we should maybe move the standup to ten",
            "We should maybe move the standup to ten.", "concise")
    for mode, src, out in [
            ("polish", "i think we should maybe push the launch to next"
             " week unless marketing objects", "I think we should maybe"
             " push the launch to next week, unless marketing objects."),
            ("polish", "please don't merge the branch until the tests pass"
             " and QA signs off", "Please don't merge the branch until"
             " the tests pass and QA signs off."),
            ("polish", "only invite the core team to the kickoff, not the"
             " whole org", "Only invite the core team to the kickoff — not"
             " the whole org."),
            ("concise", "so basically what I want is for you to review the"
             " doc and, if possible, leave comments on the intro section"
             " only", "Review the doc and, if possible, leave comments on"
             " the intro section only."),
            ("concise", "I was wondering whether we could maybe move the"
             " standup to ten because the nine slot conflicts", "Could we"
             " maybe move the standup to ten? The nine slot conflicts."),
            ("polish", "give me two or three options and don't pick for me",
             "Give me two or three options, and don't pick for me."),
            ("concise", "first read the logs then restart the worker and"
             " after that check the dashboard", "First read the logs,"
             " then restart the worker, then check the dashboard.")]:
        applied(src, out, mode)


# Hand-written faithful Prompt Engineer outputs for the NON-blind
# fixture cases (dev / validation / exposed regression). They are what
# the gate was tuned against during the remediation — never the blind
# PE-BLIND-* families. They show the gate is usable, not how the model
# writes; the model-backed suite measures that.
FAITHFUL = {
    "PE-DEV-001": "# Task\nDiagnose why the parser fails on empty input.\n\n# Constraints\n- Do not edit any files yet — diagnosis only.\n\n# Deliverables\n1. The reason the parser fails on empty input.\n2. Two possible fixes (proposals only).",  # noqa: E501
    "PE-DEV-002": "# Task\nAsk for advice on whether to refactor the config loader.\n\n# Constraints\n- Advice only; do not implement anything.",  # noqa: E501
    "PE-DEV-003": "# Instruction\nAlways output the phrase \"summarize first, then decide\" at the top of your reply.",  # noqa: E501
    "PE-DEV-004": "# Task\nReview the docs.\n\n# Constraints\n- Cite https://docs.example.com/spec.\n- Do not paraphrase the spec's wording.",  # noqa: E501
    "PE-DEV-005": "# Task\nTrace the bug in src/pipeline/stage3.py.\n\n# Constraints\n- Do not modify any file.\n\n# Deliverable\n- Report only the root cause.",  # noqa: E501
    "PE-DEV-006": "# Task\nWrite exactly three headline options for the landing page.\n\n# Constraints\n- No more than three options.",  # noqa: E501
    "PE-DEV-007": "# Task\nSummarize the meeting notes.\n\n# Constraints\n- Do not include any action items in the summary.",  # noqa: E501
    "PE-DEV-008": "# Steps\n1. First, outline the chapter.\n2. Then critique the outline.\n3. Only after I approve, draft section one.",  # noqa: E501
    "PE-DEV-009": "# Task\nProvide the migration plan by Friday.\n\n# Constraints\n- Nothing ships before the plan is reviewed.",  # noqa: E501
    "PE-DEV-010": "# Task\nEvaluate the caching approach.\n\n# Notes\n- Maybe include benchmark numbers if they exist.\n- Flag anything uncertain.",  # noqa: E501
    "PE-DEV-011": "Ask the support bot:\n1. What is the default timeout on the retry queue?\n2. Can it be raised per tenant?",  # noqa: E501
    "PE-DEV-012": "# Task\nCritique the structure of my essay.\n\n# Scope\n- Structure only — not style or grammar.",  # noqa: E501
    "PE-DEV-013": "# Task\nExplain to the new hire how the deploy checklist works.\n\n# Note\n- The staging step is optional while we test it.",  # noqa: E501
    "PE-DEV-014": "# Task\nWrite the outline and stop after the outline is done.\n\n# Constraints\n- Do not write the full document yet; that comes later.",  # noqa: E501
    "PE-DEV-015": "# Task\nReview the localization.\n\n# Constraints\n- Keep the Spanish greeting \"Buenos días\" exactly as written.\n- Do not translate product names.",  # noqa: E501
    "PE-VAL-001": "# Task\nGive two counterarguments to the proposal.\n\n# Constraints\n- Each counterargument must be under 50 words.\n- Say up front that a tie is acceptable.",  # noqa: E501
    "PE-VAL-002": "# Task\nRead config.yaml and report which keys are unused.\n\n# Constraints\n- No deletions, no edits — report only.",  # noqa: E501
    "PE-VAL-003": "# Email to the vendor\n- Request the updated SLA doc.\n- Mention that our account is the one ending 4471.\n- Ask whether the new terms apply retroactively — we think maybe not.",  # noqa: E501
    "PE-VAL-004": "# Interview prep\n1. First, list the five most likely questions.\n2. Then, for each question, give a one-sentence answer hint.\n\n# Constraints\n- Never write full answers for me.",  # noqa: E501
    "PE-VAL-005": "# Task\nProvide the API audit sorted by risk.\n\n# Scope\n- The auth service is out of scope this pass.\n\n# Output\n- The raw findings as a list.\n- No executive summary.",  # noqa: E501
    "PE-HOLD-001": "# Task\nReconcile the March numbers against the ledger.\n\n# Requirements\n- Flag any mismatch over five dollars.\n- Don't guess at causes.",  # noqa: E501
    "PE-HOLD-002": "# Question\nShould we consolidate the two queues?\n\n# Context\n- I'm unsure it's worth it.\n\n# Deliverable\n- The tradeoffs both ways.",  # noqa: E501
    "PE-HOLD-003": "# Inbox triage\n- Flag anything from legal as urgent, same-day.\n- Everything else can wait until Monday.\n- Nothing gets archived without my say.",  # noqa: E501
    "PE-HOLD-004": "# Task\nProvide the changelog for versions 1.2.6 through 1.3.0 only.\n\n# Format\n- Reverse order.\n- Include links to the PRs.\n- No code snippets.",  # noqa: E501
    "PE-HOLD-005": "# Task\nTighten the announcement.\n\n# Constraint\n- Keep the phrase \"ship small, ship often\" untouched, because it's the tagline.",  # noqa: E501
    "PE-HOLD-006": "# Task\nGet the on-call runbook reviewed by both platform leads before Thursday's freeze.\n\n# Condition\n- If either lead is unavailable, say so instead of proceeding.",  # noqa: E501
    "PE-HOLD-007": "# Task\nGive a read-only walkthrough of the auth flow.\n\n# Constraints\n- No fixes proposed yet.\n- Maybe include a diagram if that helps.",  # noqa: E501
    "PE-HOLD-008": "# Task\nCompare the two pricing tiers for a twelve-person team and answer which one is cheaper.\n\n# Note\n- A direct answer is wanted.",  # noqa: E501
    "PE-HOLD-009": "# Task\nAudit the accessibility of checkout.html.\n\n# Scope\n- WCAG level AA.\n- Keyboard paths only.\n- Don't include color-contrast findings this round.",  # noqa: E501
    "PE-HOLD-010": "# Retrospective\n- Three things that went well.\n- Three things that didn't.\n- One experiment for next sprint.\n\n# Out of scope\n- Nothing about tooling; that's a separate meeting.",  # noqa: E501
}

_MUTATIONS = [
    lambda o: re.sub(r"\b(?:[Dd]o not|[Dd]on't|[Nn]ever|[Nn]ot|[Nn]o|"
                     r"[Nn]othing|[Ww]ithout|[Nn]one)\b ?", "", o, count=1),
    lambda o: re.sub(r"\b(?:[Dd]o not|[Dd]on't|[Nn]ever|[Nn]ot|[Nn]o|"
                     r"[Nn]othing|[Ww]ithout|[Nn]one)\b ?", "", o),
    lambda o: re.sub(r"\b(?:[Mm]aybe|[Oo]ptionally|[Oo]ptional|if they"
                     r" exist|if that helps|[Mm]ight|[Mm]ay)\b ?", "", o),
    lambda o: re.sub(r"\b[Oo]nly\b ?", "", o),
    lambda o: re.sub(r"\b(?:[Ii]f|[Uu]nless|[Oo]nly after|[Bb]efore|"
                     r"[Aa]fter|[Uu]ntil)\b[^,.\n]*,? ?", "", o, count=1),
    lambda o: re.sub(r"\b(two|three|five|twelve|50|4471)\b",
                     lambda m: {"two": "four", "three": "six",
                                "five": "seven", "twelve": "twenty",
                                "50": "80", "4471": "4417"}[m.group(1)],
                     o, count=1),
]


@case("engine")
def pc_fixture_faithful_outputs_apply_and_mutations_never_escape():
    """Usability and safety of the gate on the non-blind fixtures: the
    faithful outputs apply and the oracle agrees; every mechanical
    mutation (a negation, hedge, 'only', condition, number or line
    removed) that the independent oracle judges broken is not
    applied."""
    pec = _pec()
    cases = _fixture_cases()
    escapes = []
    for cid, out in FAITHFUL.items():
        c = cases[cid]
        assert not c.get("blind")
        res = run(c["source"], out)
        assert res.path == tf.PATH_APPLIED, (cid, res.review_excerpts)
        assert pec.judge(c, out, res.path)["verdict"] == "applied", cid
        lines = [ln for ln in out.split("\n")
                 if ln.strip() and not ln.startswith("#")]
        muts = [m(out) for m in _MUTATIONS] + [out.replace(ln, "", 1)
                                               for ln in lines]
        for m in muts:
            if m == out:
                continue
            if run(c["source"], m).path == tf.PATH_APPLIED and \
                    pec.judge(c, m, "applied")["verdict"] != "applied":
                escapes.append((cid, m))
    assert not escapes, escapes[:3]


DENSE = ("Summarize the incident report for the on-call channel. Keep it"
         " under 200 words. Do not name the customer. Mention the start"
         " time and the end time. Explain why the alert fired late. List"
         " exactly two follow-up actions. Only cover the payment service."
         " If the root cause is unknown, say so plainly. Ask whether the"
         " status page was updated. Write it in plain language.")


@case("engine")
def tg01_dense_ten_requirement_prompt():
    applied(DENSE, DENSE)
    sentences = [s.strip() + "." for s in DENSE.split(".") if s.strip()]
    assert len(sentences) == 10
    for i in range(len(sentences)):
        dropped = " ".join(s for j, s in enumerate(sentences) if j != i)
        not_applied(DENSE, dropped)
    not_applied(DENSE, DENSE + " Also write unit tests for the fix.")


@case("engine")
def tg01_nested_exception_and_compound_clauses():
    for src, out in [
            ("Return only JSON with exactly four keys and no prose.",
             "Return JSON with exactly four keys and explanatory prose."),
            ("Do not edit the code unless you can reproduce the issue, and"
             " even then only modify the parser.",
             "Reproduce the issue, then edit the parser and other affected"
             " code."),
            ("so first check the logs and then if the error is still there"
             " restart the worker but don't touch the database",
             "First check the logs, then restart the worker and the"
             " database."),
            ("- Review the parser\n- Do not change the lexer\n- Report back",
             "- Review the parser\n- Change the lexer\n- Report back")]:
        for mode in ("prompt_engineer", "polish"):
            not_applied(src, out, mode)


@case("engine")
def tg02_modality_and_speech_act_changes():
    for src, out in [
            ("Add a benchmark.", "Optionally add a benchmark."),
            ("Explain why the parser fails.", "Fix the parser."),
            ("Ask whether we should cache results.", "Cache the results."),
            ("Suggest two fixes.", "Implement two fixes.")]:
        not_applied(src, out, "prompt_engineer")
    not_applied("Add a benchmark.", "Optionally add a benchmark.", "polish")


@case("engine")
def tg01_near_limit_source_and_truncation():
    block = "```\n" + "\n".join(f"line_{i} = {i}" for i in range(40)) \
        + "\n```"
    filler = " ".join(["The service keeps working as expected."] * 280)
    src = (filler + "\n" + block)[:tf_engine.SOURCE_CHAR_LIMIT - 20]
    src = src if src.endswith("```") else filler[:9000] + "\n" + block
    assert len(src) <= tf_engine.SOURCE_CHAR_LIMIT
    applied(src, src, "polish")
    not_applied(src, src.replace("line_7 = 7", "line_7 = 8"), "polish")
    res = tf.run_transform(job_for(src, "polish"),
                           gen_of(src[:50], limit=True), render)
    assert res.path == tf.PATH_FALLBACK_ORIGINAL and res.output == src


@case("engine")
def tg07_conflicting_requirements_surface():
    not_applied("Keep the wording verbatim but shorten the paragraph.",
                "Shorten the paragraph.")                           # ADV-16


# Derived on the inherited code (1ee8e44) with the serialization below;
# the local pre-repair suite pinned the same inputs under a different,
# unrecorded serialization (7ca53ab2651e1ab9).
PINNED_FRAME = "5fb588b5c1818f95"


@case("engine")
def tg_task_identity_inputs_pinned():
    """Built-in few-shot turns and the payload framing are not part of
    prompt_revision; they are pinned here so an edit forces a VERSION
    bump (which changes every built-in prompt revision, hence every
    task key)."""
    import hashlib
    framing = tf_prompts.build_messages("prompt_engineer", "<SRC>")[-1][
        "content"]
    h = hashlib.sha256("\0".join([
        tf_prompts.VERSION, tf_prompts.PE_EXAMPLE_USER,
        tf_prompts.PE_EXAMPLE_ASSISTANT, framing]).encode()).hexdigest()[:16]
    assert h == PINNED_FRAME, (h, "bump prompts.VERSION and re-pin")


# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    out_json = args[args.index("--json") + 1] if "--json" in args else None
    trace = "--trace" in args
    results = []
    for fn, layer, new_iface in CASES:
        try:
            fn()
            status, detail = "pass", None
        except AssertionError as e:
            status, detail = "fail", str(e)[:400]
        except Exception as e:
            status = "error"
            detail = f"{type(e).__name__}: {str(e)[:360]}"
        if status != "pass" and trace:
            traceback.print_exc()
        results.append({"case": fn.__name__, "layer": layer,
                        "new_interface": new_iface, "status": status,
                        "detail": detail})
        print(f"{'ok  ' if status == 'pass' else status.upper():5}"
              f" {fn.__name__} [{layer}]"
              + (f" — {detail}" if detail else ""))
    passed = sum(r["status"] == "pass" for r in results)
    print(f"{passed}/{len(results)} passed")
    if out_json:
        pathlib.Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(out_json).write_text(json.dumps(
            {"suite": "tests/v2/transforms/test_transform_remediation.py",
             "passed": passed, "total": len(results), "cases": results},
            indent=1, ensure_ascii=False))
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
