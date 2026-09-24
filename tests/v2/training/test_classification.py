"""EV-20 correction and preference quality (V2 M14, E19.3): the
multi-axis classifier over the 100-record fixture pack, the
correction-graft mechanics, and the suggestion gate — precision with
its exact numerator/denominator, zero changed-intent/wrong-target
negatives promoted (M14-AC05).

Synthetic fixtures prove mechanics; they do not establish real
classification accuracy (E19.3) — the per-class assertions below run
against the pack's declared ground truth, and rare classes stay
unqualified on real data until 60 real observations are reviewed.

Run: .venv/bin/python tests/v2/training/test_classification.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from evidence_pack import build_pack, build_negatives  # noqa: E402
from localflow.v2 import learning, store as store_mod, training_data  # noqa: E402
from localflow.v2.curation import classify, review  # noqa: E402
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402


def make_store(tmp):
    return store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups")


def test_axes_over_pack():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack = build_pack(s)
            # Recognition corrections: deterministic axes per ground
            # truth (asr for even variants, cleanup for odd).
            per_kind = {}
            for ex, truth in pack["examples"].items():
                if truth["category"] != "recognition_correction":
                    continue
                detail = training_data.TrainingDataService(s) \
                    .example_detail(ex)
                stages = {st["stage"]: st.get("text")
                          for st in detail["stages"]}
                obs = s.submit(lambda c, j=truth and detail["job_id"]:
                               c.execute(
                                   "SELECT b.content_text, a.content_text"
                                   " FROM insertion_observations o JOIN"
                                   " artifacts b ON b.artifact_id="
                                   " o.before_artifact_id JOIN artifacts"
                                   " a ON a.artifact_id="
                                   " o.after_artifact_id WHERE o.job_id=?"
                                   " ORDER BY o.rowid DESC LIMIT 1",
                                   (j,)).fetchone())
                c = classify.classify_observation(
                    obs[0], obs[1],
                    stage_texts={"raw": stages.get("source_text"),
                                 "applied": stages.get("applied_output")})
                assert c["edit_kind"] == truth["expect_edit_kind"], \
                    (ex, truth, c)
                if truth["subkind"] == "recognition":
                    if truth["regression"]:
                        assert c["origin_stages"] == ["cleanup"] \
                            and c["pipeline_effect"] == "regression", c
                    else:
                        assert c["origin_stages"] == ["asr"], c
                else:
                    # A spoken "twelve percent" the user reformatted is
                    # an asr-origin representation change, neutral.
                    assert c["origin_stages"] == ["asr"] \
                        and c["pipeline_effect"] == "neutral", c
                per_kind[c["edit_kind"]] = \
                    per_kind.get(c["edit_kind"], 0) + 1
            assert per_kind.get("recognition_error", 0) == 10
            assert per_kind.get("representation_error", 0) == 10
            print("ok  axes: recognition/representation attribution"
                  " with asr vs cleanup-regression origins")
            # Mixed edits aggregate to changed_intent — never promoted.
            for ex, truth in pack["examples"].items():
                if truth["category"] != "mixed_changed_intent":
                    continue
                obs = s.submit(lambda c, j=pack["examples"][ex].get(
                        "job_id") or _job_of(s, ex): c.execute(
                    "SELECT b.content_text, a.content_text FROM"
                    " insertion_observations o JOIN artifacts b ON"
                    " b.artifact_id=o.before_artifact_id JOIN artifacts"
                    " a ON a.artifact_id=o.after_artifact_id WHERE"
                    " o.job_id=? ORDER BY o.rowid DESC LIMIT 1",
                    (j,)).fetchone())
                c = classify.classify_observation(obs[0], obs[1])
                assert c["edit_kind"] == "changed_intent", (ex, c)
            print("ok  mixed edits: cloud→Claude + friday→Monday is"
                  " changed intent, never an ASR correction")
        finally:
            s.close()


def _job_of(s, ex):
    return s.submit(lambda c: c.execute(
        "SELECT job_id FROM training_examples WHERE example_id=?",
        (ex,)).fetchone()[0])


def test_graft_mechanics():
    regions = classify.changed_regions(
        "ship the cloud report on friday",
        "ship the Claude report on Monday")
    cloud = [r for r in regions if r["before_words"] == ["cloud"]]
    assert len(cloud) == 1
    graft = classify.build_graft(
        "ship the cloud report on friday", cloud)
    assert graft["grafted_text"] == "ship the Claude report on friday"
    assert graft["coverage_kind"] == "partial"
    assert len(graft["coverage"]) == 1
    # Overlapping confirmed spans refuse; Unicode offsets are exact.
    assert classify.build_graft("abc", [
        {"start": 0, "end": 2, "after_words": ["x"]},
        {"start": 1, "end": 3, "after_words": ["y"]}]) is None
    uni = classify.changed_regions("héllo wörld café", "héllo wörld Café")
    assert uni[0]["start"] == 12 and uni[0]["end"] == 16
    print("ok  grafts: partial coverage only; Unicode code-point"
          " offsets exact; overlaps refused")


def test_negatives_never_promoted():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack = build_pack(s)
            negatives = build_negatives(s)
            vs = VocabularyStore(s)
            ls = learning.LearningService(
                s, emit=lambda *a, **k: None, vocabulary=vs)
            rs = review.ReviewService(s, emit=lambda *a, **k: None)
            ls.mine_observation_candidates(limit=500)
            cands = ls.candidates()
            # Negatives may surface for REVIEW (an ambiguous edit is
            # evidence to resolve), but never as a one-click RULE —
            # and never promoted (below).
            suggested_negatives = [
                c for c in cands if c["alias"]
                and c["example_id"] in
                {n["example_id"] for n in negatives
                 if n.get("example_id")}]
            assert not suggested_negatives, suggested_negatives
            # Unrelated pastes and unchanged outputs mint NOTHING.
            dismissed = [c for c in cands if c["status"] == "dismissed"]
            assert len(dismissed) >= 20  # pastes + no-edit negatives
            # Every changed-intent fixture is barred from verified ASR
            # (M14-AC05) — through the gate, not by convention — and
            # so are the negatives (no verbatim, and ambiguous labels).
            for n in negatives:
                if n.get("example_id"):
                    gate = rs.verified_asr_eligible(n["example_id"])
                    assert not gate["eligible"], (n, gate)
            for ex, truth in pack["examples"].items():
                gate = rs.verified_asr_eligible(ex)
                if truth["category"] == "mixed_changed_intent":
                    rs.record_label(
                        ex, edit_kind="changed_intent",
                        origin_stages=("user_intent",),
                        evidence_status="explicit_intent_review")
                    gate = rs.verified_asr_eligible(ex)
                    assert not gate["eligible"], (ex, gate)
                if truth["category"] == "sensitive_excluded":
                    assert not gate["eligible"], (ex, gate)
                if truth["category"] == "reviewed_success":
                    assert gate["eligible"], (ex, gate)
            print("ok  AC05: wrong-target/unrelated/unchanged negatives"
                  " mint nothing; changed-intent and quarantined/excluded"
                  " fixtures never pass the ASR gate")
        finally:
            s.close()


def test_suggestion_gate_precision():
    """E19.3's gate: ≥95% precision on reviewed recognition-correction
    suggestions, exact numerator/denominator shown; insufficient
    evidence keeps suggestions visibly unverified (they already are —
    candidates stay pending until explicit review)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack = build_pack(s)
            vs = VocabularyStore(s)
            ls = learning.LearningService(
                s, emit=lambda *a, **k: None, vocabulary=vs)
            ls.mine_observation_candidates(limit=500)
            cands = ls.candidates(status="pending")
            suggestions = [c for c in cands if c["alias"]]
            truth = pack["examples"]
            true_positives = 0
            false_positives = []
            for c in suggestions:
                t = truth.get(c["example_id"]) or {}
                if t.get("category") == "recognition_correction" \
                        and t.get("subkind") == "recognition" \
                        and not t.get("regression") \
                        and c["classification"].get("edit_kind") == \
                        "recognition_error" \
                        and c["alias"] and c["canonical"]:
                    true_positives += 1
                else:
                    false_positives.append(
                        (c["example_id"], c["alias"],
                         c["classification"].get("edit_kind")))
            denominator = len(suggestions)
            precision = (true_positives / denominator
                         if denominator else None)
            print(f"     gate: {true_positives}/{denominator}"
                  f" = {precision}")
            # The pack's 10 asr-variant recognition corrections; the
            # 10 cleanup-regression variants and every negative carry
            # NO rule (teaching an alias there would mask the real
            # origin — S29.7).
            assert denominator == 5, \
                "unexpected suggestion population"
            assert precision is not None and precision >= 0.95, \
                false_positives
            # Changed-intent fixtures never carry a suggestion.
            changed = [c for c in cands
                       if (truth.get(c["example_id"]) or {}).get(
                           "category") == "mixed_changed_intent"]
            assert all(not c["alias"] or c["status"] != "pending"
                       for c in changed)
            print("ok  suggestion gate ≥95% precision with exact"
                  " denominator; changed-intent never suggested")
        finally:
            s.close()


def test_label_versions_and_coverage():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack = build_pack(s)
            rs = review.ReviewService(s, emit=lambda *a, **k: None)
            ex = pack["by_category"]["recognition_correction"][0]
            l1 = rs.record_label(ex, edit_kind="recognition_error",
                                 origin_stages=("asr",),
                                 evidence_status="explicit_intent_review")
            l2 = rs.record_label(ex, edit_kind="recognition_error",
                                 origin_stages=("asr",),
                                 evidence_status="explicit_intent_review")
            assert l2["revision"] == 2
            labels = rs.labels(ex)
            assert [l["revision"] for l in labels] == [1, 2]
            cov = rs.label_coverage()
            assert cov["labels_total"] >= 2
            assert cov["by_edit_kind"].get("recognition_error", 0) >= 2
            # Validation of axis values.
            try:
                rs.record_label(ex, edit_kind="not_a_kind")
                raise AssertionError("invalid edit_kind accepted")
            except ValueError:
                pass
            print("ok  labels: append-only revisions, coverage counts,"
                  " axis validation")
        finally:
            s.close()


def test_stage_attribution_and_gates():
    """Origin attribution reads the retained stages under their real
    keys: a normalization regression is the normalization stage's, a
    cleanup regression cleanup's, no retained carrier abstains; the
    envelope's ledger-valued ``normalization`` slot means "unchanged"
    (normalized text = raw), never ledger JSON read as text. Re-casing
    a whole passage is style, not a name fix; a contraction negation
    flip abstains."""
    wrong, right = "the valu is fine", "the value is fine"
    for stages, origin in (
            ({"raw": right, "normalized": wrong, "applied": wrong},
             "normalization"),
            ({"raw": right, "normalized": right, "applied": wrong},
             "cleanup"),
            ({"raw": right}, "unknown")):
        r = classify.classify_observation(wrong, right,
                                          stage_texts=stages)
        assert r["origin_stages"] == [origin] and \
            r["pipeline_effect"] == "regression", (stages, r)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            job, fam = s.create_job()
            raw = s.write_text_artifact(
                job_id=job, stage="asr", role="raw_transcript",
                text=right, retention_class="training")
            ledger = s.write_text_artifact(
                job_id=job, stage="normalization",
                role="normalization_ledger", kind="ledger_json",
                text=json.dumps({"text": right, "edits": []}),
                retention_class="training")
            applied = s.write_text_artifact(
                job_id=job, stage="cleanup", role="applied_output",
                text=wrong, retention_class="training")
            ex = s.upsert_example(job_id=job, family_id=fam)
            s.append_revision(ex, {
                "example_id": ex, "job_id": job, "family_id": fam,
                "artifact_ids": {"source_text": raw,
                                 "normalization": ledger,
                                 "applied_output": applied},
                "annotations": [], "missing_reasons": {}})
            texts = s.submit(lambda c: review.stage_texts_for(c, ex))
            assert texts["normalized"] == right, texts
            r = classify.classify_observation(wrong, right,
                                              stage_texts=texts)
            assert r["origin_stages"] == ["cleanup"], r
        finally:
            s.close()
    r = classify.classify_observation(
        "please review the notes", "PLEASE REVIEW THE NOTES",
        stage_texts={"raw": "please review the notes"})
    assert r["edit_kind"] == "style_preference", r
    r = classify.classify_observation(
        "we can ship it today", "we can't ship it today",
        stage_texts={"raw": "we can ship it today"})
    assert r["edit_kind"] == "ambiguous" and r["abstained"] and \
        "negation" in r["domains"], r
    print("ok  stage attribution under real keys (normalization /"
          " cleanup / unknown; ledger = unchanged); case and negation"
          " gates")


if __name__ == "__main__":
    test_axes_over_pack()
    test_graft_mechanics()
    test_negatives_never_promoted()
    test_suggestion_gate_precision()
    test_label_versions_and_coverage()
    test_stage_attribution_and_gates()
    print("all classification tests passed")
