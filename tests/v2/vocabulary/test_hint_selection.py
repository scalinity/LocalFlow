"""EV-18 / M05: Relevant Vocabulary Selector, immutable HintSets and
context discrimination.

Covers deterministic selection, term limits with recorded omissions,
the unsupported-adapter boundary (offered-but-ignored disposition, no
fabricated request fields), offered-vs-applied provenance (a post-ASR
dictionary repair is never a decoder hit), the wrong-workspace
condition, the E18.3 text-side matrix (40 labeled bases x four primary
hint conditions, mangled and correct variants per family) and the
no-post-answer-leakage rule (S29.11). Text-only: no acoustic claim is
made anywhere (M05-AC06); M15 owns audio.

Run: .venv/bin/python tests/v2/vocabulary/test_hint_selection.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import capabilities as caps  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)
from localflow.v2.vocabulary import (  # noqa: E402
    Alias,
    RelevantVocabularySelector,
    ScopeContext,
    VocabularyEntry,
    VocabularySnapshot,
)
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
MATRIX = json.loads((HERE / "fixtures_hint_matrix.json").read_text())

IN_SCOPE = ScopeContext(profile="coding")
WRONG_WORKSPACE = ScopeContext(workspace="somewhere-else")


def _entry(canonical, aliases, *, scope=("profile", "coding"),
           approved=True, **kw):
    return VocabularyEntry(
        entry_id="hm-" + canonical.lower().replace(" ", "-"),
        canonical=canonical,
        scope_kind=scope[0], scope_value=scope[1],
        approved=approved, verification="explicit" if approved
        else "suggested",
        aliases=tuple(Alias(a) for a in aliases), **kw)


def _bases():
    """Expand 8 targets x 5 templates into the 40 labeled bases."""
    out = []
    for t in MATRIX["targets"]:
        for k, template in enumerate(MATRIX["templates"]):
            mangled_text = template.replace("{X}", t["mangled"])
            correct_text = template.replace("{X}", t["canonical"])
            out.append({
                "base_id": f"LF-HM-{t['target_id']}-{k + 1}",
                "family_id": t["family_id"],
                "target_canonical": t["canonical"],
                "mangled": t["mangled"],
                "mangled_text": mangled_text,
                "correct_text": correct_text,
                "true": _entry(t["canonical"], [t["mangled"]]),
                "distractor": _entry(
                    t["distractor_canonical"], [t["distractor_alias"]]),
            })
    return out


def _run_text(text, entries, scope=IN_SCOPE):
    snap = VocabularySnapshot(entries, scope)
    pol = NormalizationPolicy(registered_skills=dict(snap.skills))
    res = normalize(text, pol, ContextSnapshot(vocabulary=snap))
    return res, snap


def test_deterministic_selection():
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        vs = VocabularyStore(st)
        vs.seed_legacy_terms(["Qwen", "MLX", "Parakeet", "LocalFlow",
                              "Wispr Flow", "PyObjC", "MacBook"])
        snap = vs.snapshot(None)
        sel = RelevantVocabularySelector(100)
        hs1 = sel.select(snap, now_utc="2026-09-22T00:00:00.000Z")
        hs2 = sel.select(snap, now_utc="2026-09-22T00:00:00.000Z")
        assert [t.entry_id for t in hs1.terms] == \
            [t.entry_id for t in hs2.terms]
        assert hs1.hint_set_id == hs2.hint_set_id
        # Ranking follows pin > scope > recency > frequency (S11).
        eid = vs.add_entry("Zeta", ["zeeta"], approved=True)
        vs.update_entry(eid, pinned=True)
        snap2 = vs.snapshot(None)
        hs3 = sel.select(snap2)
        assert hs3.terms[0].canonical == "Zeta"
        assert hs3.terms[0].score[0] == 1  # pinned leads the score tuple
        st.close()
    print("ok  selection deterministic; ranks pin/scope/recency/frequency")


def test_term_limits_and_omissions_recorded():
    entries = [_entry(f"Term{i:03d}", [f"term {i}"]) for i in range(30)]
    snap = VocabularySnapshot(entries, IN_SCOPE)
    hs = RelevantVocabularySelector(10).select(snap)
    assert len(hs.terms) == 10
    assert len(hs.omitted) == 20
    assert all(o["reason"] == "budget_limit" for o in hs.omitted)
    assert {o["canonical"] for o in hs.omitted} == \
        {e.canonical for e in entries[10:]}
    assert hs.term_limit == 10
    # The doc records the omission policy explicitly (S30.1).
    doc = hs.to_json()
    assert doc["omitted"][0]["reason"] == "budget_limit"
    print("ok  term limit truncates with recorded budget omissions")


def test_unsupported_adapter_stays_honest():
    """The current manifest has contextual biasing disabled: the
    disposition is offered-but-ignored, the request-field extension
    point returns None, and nothing pretends hints reached the decoder."""
    snap = VocabularySnapshot(
        [_entry("Claude Code", ["clod code"])], IN_SCOPE)
    hs = RelevantVocabularySelector(100).select(snap)
    manifest = caps.asr_capability_manifest("parakeet-mlx")
    assert manifest["capabilities"]["contextual_biasing"][
        "supported"] is False
    disp = caps.hint_disposition(manifest, hs)
    assert disp["offered_terms"] == len(hs.terms)
    assert disp["accepted_terms"] == 0
    assert disp["ignored"] is True
    assert disp["ignored_reason"] == "disabled_until_qualified"
    assert disp["hint_set_id"] == hs.hint_set_id
    assert caps.asr_hint_request_fields(hs, manifest) is None
    # No-hint-set call sites keep the honest zero disposition.
    zero = caps.hint_disposition(manifest)
    assert zero["offered_terms"] == 0 and zero["ignored"] is False
    print("ok  unsupported hints: offered-but-ignored, no fabricated"
          " request fields")


def test_offered_vs_applied_provenance():
    """M05-AC05: one HintSet feeds every supported consumer and each
    records actual use or an explicit reason. Pre-decode: ignored
    (unqualified). Post-ASR recovery: actual use via the ledger's
    vocabulary edits with rule ids — never marked as decoder hits."""
    entries = [_entry("Claude Code", ["clod code"])]
    snap = VocabularySnapshot(entries, IN_SCOPE)
    hs = RelevantVocabularySelector(100).select(snap)
    manifest = caps.asr_capability_manifest("parakeet-mlx")
    disp = caps.hint_disposition(manifest, hs)
    assert disp["accepted_terms"] == 0  # the decoder accepted nothing
    res, _ = _run_text("ship it with clod code now", entries)
    applied = [e for e in res.edits if e.cls == "vocabulary"]
    assert applied and applied[0].rule_id == entries[0].entry_id
    # The applied repair lives in the normalization ledger, NOT in the
    # ASR disposition (S09: "a post-ASR dictionary repair is never
    # recorded as a decoder vocabulary hit").
    assert disp["accepted_terms"] == 0
    print("ok  offered/applied provenance: repairs are ledger edits,"
          " never decoder hits")


def test_wrong_workspace_condition():
    entries = [_entry("Servo", ["survo"],
                      scope=("workspace", "web"))]
    res, _ = _run_text("run survo tests", entries, scope=WRONG_WORKSPACE)
    assert res.text == "run survo tests"
    assert not [e for e in res.edits if e.cls == "vocabulary"]
    # And a hint set selected for the wrong workspace carries the web
    # terms — supplying them must not adopt them into other text.
    snap = VocabularySnapshot(entries, ScopeContext(workspace="web"))
    hs = RelevantVocabularySelector(100).select(snap)
    assert hs.terms and hs.terms[0].canonical == "Servo"
    res2, _ = _run_text("run the servo motor quietly", entries,
                        scope=WRONG_WORKSPACE)
    assert res2.text == "run the servo motor quietly"
    print("ok  wrong-workspace: scoped entries neither match nor adopt")


def test_matrix_conditions():
    """E18.3 text-side matrix: 40 bases x {none, true, true+distractor,
    distractor-only} x {mangled, correct}. Reports correct-context
    recovery, false contextual substitution on non-target spans and the
    distractor flip rate. AC06: recovery is distinguished from false
    adoption — masking prevents the hijack whenever the true term
    exists; an approved WRONG entry alone does rewrite its alias (that
    is what an approved rule does), measured here and never hidden."""
    bases = _bases()
    assert len(bases) == 40

    def target_span(text, needle):
        i = text.index(needle)
        return (i, i + len(needle))

    recovery = {"none": 0, "true": 0, "true+distractor": 0,
                "distractor": 0}
    flips = {"none": 0, "true": 0, "true+distractor": 0,
             "distractor": 0}
    false_substitutions = 0
    for b in bases:
        for variant, text, span_key in (
                ("mangled", b["mangled_text"], "mangled"),
                ("correct", b["correct_text"], "target_canonical")):
            span = target_span(text, b[span_key])
            for cond, entries in (
                    ("none", []),
                    ("true", [b["true"]]),
                    ("true+distractor", [b["true"], b["distractor"]]),
                    ("distractor", [b["distractor"]])):
                res, _ = _run_text(text, entries)
                out_span_text = None
                for e in res.edits:
                    if e.cls == "vocabulary" and \
                            (e.input_span.start, e.input_span.end) == span:
                        out_span_text = e.output_text
                    elif e.cls == "vocabulary":
                        false_substitutions += 1
                if variant == "mangled":
                    if out_span_text == b["target_canonical"]:
                        recovery[cond] += 1
                else:
                    if out_span_text is not None and \
                            out_span_text != b["target_canonical"]:
                        flips[cond] += 1
    n = len(bases)
    assert recovery["true"] == n, recovery
    assert recovery["true+distractor"] == n, recovery
    assert recovery["none"] == 0 and recovery["distractor"] == 0
    assert false_substitutions == 0
    assert flips["true"] == 0
    assert flips["true+distractor"] == 0, \
        "the distractor must not hijack a correct term when the true" \
        " entry exists (same-scope masking)"
    # Honest measurement, not a hidden failure: a lone approved wrong
    # entry rewrites its own alias — reported, expected, documented.
    assert flips["distractor"] == n, flips
    print(f"ok  matrix 40x4: recovery {recovery['true']}/{n} (true),"
          f" {recovery['true+distractor']}/{n} (true+distractor);"
          f" flips 0 (true), 0 (true+distractor),"
          f" {flips['distractor']}/{n} (lone wrong entry, measured);"
          f" false substitutions 0")


def test_no_post_answer_hint_leakage():
    """S29.11: the hint set is frozen before decoding. Store edits after
    freezing cannot change the set, and the frozen content identifies
    the vocabulary revision it came from — a corrected dictionary is
    never rewritten into 'original hints'."""
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        vs = VocabularyStore(st)
        vs.seed_legacy_terms(["Qwen", "MLX"])
        snap = vs.snapshot(None)
        hs = RelevantVocabularySelector(100).select(snap)
        frozen = hs.to_json()
        # The answer arrives (a correction is learned) — the store now
        # has an extra term and even a usage hit.
        eid = vs.add_entry("Claude Code", ["clod code"], approved=True)
        vs.record_hits([eid])
        assert hs.to_json() == frozen
        assert hs.vocabulary_revision == snap.revision
        later = RelevantVocabularySelector(100).select(
            vs.snapshot(None))
        assert later.hint_set_id != hs.hint_set_id
        assert later.vocabulary_revision != hs.vocabulary_revision
        st.close()
    print("ok  hint sets frozen pre-decode; later corrections never"
          " relabel original hints")


def test_hint_set_feeds_all_supported_consumers():
    """M05-AC05 with the consumer set named: pre-decode ASR (ignored,
    unqualified), post-ASR recovery (actual use through the snapshot the
    set was built from). Cleanup consumes permitted context from M07 —
    not a consumer yet, so nothing records a disposition for it (no
    speculative field is written)."""
    entries = [_entry("Claude Code", ["clod code"])]
    snap = VocabularySnapshot(entries, IN_SCOPE)
    hs = RelevantVocabularySelector(100).select(snap)
    # Consumer 1: pre-decode request — unqualified adapter.
    manifest = caps.asr_capability_manifest("parakeet-mlx")
    assert caps.asr_hint_request_fields(hs, manifest) is None
    assert caps.hint_disposition(manifest, hs)["ignored_reason"] == \
        "disabled_until_qualified"
    # Consumer 2: post-ASR recovery — the same dictionary source (the
    # snapshot), actual use recorded as ledger edits with rule ids.
    res, snap2 = _run_text("fix with clod code", entries)
    applied = [e for e in res.edits if e.cls == "vocabulary"]
    assert applied and applied[0].rule_id in {e.entry_id
                                              for e in snap2.entries}
    assert hs.vocabulary_revision == snap2.revision
    print("ok  one HintSet, two live consumers with recorded"
          " dispositions; cleanup deferred to M07 (not a consumer yet)")


def test_request_fields_shape_pinned_for_qualified_adapter():
    """Review CA1-S6: the qualified-adapter branch of the extension
    point is pinned by a synthetic supported manifest so M06+ cannot
    silently redefine the S30.1 request shape."""
    snap = VocabularySnapshot([_entry("Claude Code", ["clod code"])],
                              IN_SCOPE)
    hs = RelevantVocabularySelector(100).select(snap)
    manifest = caps.asr_capability_manifest("qualified-adapter")
    manifest["capabilities"]["contextual_biasing"] = {
        "supported": True, "reason": "synthetic_test",
        "evidence": "synthetic manifest for shape pinning"}
    fields = caps.asr_hint_request_fields(hs, manifest)
    assert fields is not None
    assert set(fields) == {"hint_set_id", "context_snapshot_id",
                           "terms", "language_hint", "term_limit"}
    assert fields["hint_set_id"] == hs.hint_set_id
    assert fields["context_snapshot_id"] is None  # M06 feeds it
    assert fields["language_hint"] is None        # separately qualified
    assert fields["term_limit"] == 100
    assert set(fields["terms"][0]) == {"canonical", "scope", "source",
                                       "score"}
    print("ok  qualified-adapter request-field shape pinned"
          " (synthetic manifest)")


if __name__ == "__main__":
    test_deterministic_selection()
    test_term_limits_and_omissions_recorded()
    test_unsupported_adapter_stays_honest()
    test_offered_vs_applied_provenance()
    test_wrong_workspace_condition()
    test_matrix_conditions()
    test_no_post_answer_hint_leakage()
    test_hint_set_feeds_all_supported_consumers()
    test_request_fields_shape_pinned_for_qualified_adapter()
    print("all hint selection tests passed")
