"""M14 corpus drivers, group a: explicit_teaching (LF-M14-C001..C008),
m08_observation_mining (C009..C015), m12_note_mining (C016..C025),
candidate_liveness (C026..C032) and classifier_axes (C033..C040); the
stateful probes LF-M14-S001, S002, S003, S004, S011, S012, S033; and the
metamorphic relation LF-M14-MR003 (rejection stability).

Protocol: tests/v2/personalization/m14_drivers_common.py. Every driver
builds a fresh synthetic ``MWorld``, applies the entry's delta, runs the
real production operation (``LearningService.teach_correction`` /
``mine_observation_candidates`` — note mining runs through the same
entry point, which calls ``_mine_note_candidates`` — approve / reject,
the store's retention and deletion paths, the real ``NoteStore``, the
classifier and, for C007, the real HubController headless) and grades
the entry's predicate against literal expectations and raw SQL rows.
Each refusal or negative carries a same-shape eligible companion whose
success is asserted too.
"""

from __future__ import annotations

import hashlib
import json
import threading

from m14_drivers_common import check, drives, invalid
from m14_world import APP, PRIVATE_CANARY, TYPED_CANARY, MWorld, \
    accepts, after_each_op

from localflow.v2 import ids
from localflow.v2 import notes as notes_mod
from localflow.v2.curation import classify

TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"

_REVIEW_ROLES = ("verbatim_reference", "span_correction", "span_graft",
                 "candidate_observation", "counterexample_result")

# =============================================================================
# helpers (independent readers; never the function under test)
# =============================================================================


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _refused(fn, *a, **kw):
    """(True, message) when the call raised, else (False, result)."""
    try:
        return False, fn(*a, **kw)
    except Exception as e:  # noqa: BLE001 — a refusal of any typed kind
        return True, f"{type(e).__name__}: {e}"


def _render(w, aid):
    """What History showed: the final's artifact id and its text hash,
    read straight from the artifacts table."""
    row = w.artifact_row(aid)
    return aid, _sha(row[3])


def _teach(w, job_id, text, rendered=None):
    kw = {}
    if rendered is not None and accepts(w.learning.teach_correction,
                                        "expected_final_artifact_id"):
        kw = {"expected_final_artifact_id": rendered[0],
              "expected_final_sha256": rendered[1]}
    return _refused(w.learning.teach_correction, job_id, text, **kw)


def _counts(w):
    return {t: w.one(f"SELECT COUNT(*) FROM {t}")[0] for t in (
        "learning_candidates", "artifacts", "artifact_leases",
        "training_examples")}


_CCOLS = ("candidate_id", "job_id", "example_id", "source",
          "observation_id", "status", "proposed_alias",
          "proposed_canonical", "changed_spans_json",
          "classification_json", "after_artifact_id")


def _cands(w, where="1=1", args=()):
    out = []
    for r in w.rows(f"SELECT {', '.join(_CCOLS)} FROM learning_candidates"
                    f" WHERE {where} ORDER BY rowid", args):
        d = dict(zip(_CCOLS, r))
        d["spans"] = json.loads(d.pop("changed_spans_json") or "[]")
        d["axes"] = json.loads(d.pop("classification_json") or "{}")
        d["alias"] = d.pop("proposed_alias")
        d["canonical"] = d.pop("proposed_canonical")
        d["payload_aid"] = d.pop("after_artifact_id")
        out.append(d)
    return out


def _payload(w, aid):
    """(role, job_id, purged, text) of a payload artifact, or None."""
    row = w.one("SELECT role, job_id, purged, content_text FROM artifacts"
                " WHERE artifact_id=?", (aid,)) if aid else None
    return row


def _forever(w, aid):
    return w.one("SELECT COUNT(*) FROM artifact_leases WHERE artifact_id=?"
                 " AND expires_at_utc IS NULL AND revoked_at_utc IS NULL",
                 (aid,))[0]


def _finite_live(w, aid):
    return w.one("SELECT COUNT(*) FROM artifact_leases WHERE artifact_id=?"
                 " AND expires_at_utc IS NOT NULL AND revoked_at_utc IS"
                 " NULL", (aid,))[0]


def _mine(w):
    return w.learning.mine_observation_candidates()


def _obs_row(w, job_id, stop, *, edited=1, before=None, after=None):
    """An observation row exactly as the M08 producer closes a window
    that never wrote before/after artifacts (secure field, drift)."""
    obs_id = ids.new_id("obs")
    now = ids.now_utc_iso()
    w.store.submit(lambda c: c.execute(
        "INSERT INTO insertion_observations(observation_id, insertion_id,"
        " job_id, started_at_utc, stopped_at_utc, stop_reason, edited,"
        " reanchors, ticks, before_artifact_id, after_artifact_id,"
        " meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (obs_id, ids.new_id("ins"), job_id, now, now, stop, edited, 0, 4,
         before, after, json.dumps({"range_units": "utf16_host"}))))
    return obs_id


def _entries_with_alias(w, alias):
    return {eid: e for eid, e in w.entries().items()
            if any(a.lower() == alias.lower() and ok for a, ok in e[6])}


def _no_review_truth(w, j):
    """No ASR truth written for the job: no verbatim/graft artifacts, no
    correction labels, envelope annotations still empty."""
    arts = w.one("SELECT COUNT(*) FROM artifacts WHERE job_id=? AND role IN"
                 " ('verbatim_reference','span_graft','span_correction')",
                 (j["job_id"],))[0]
    labels = w.one("SELECT COUNT(*) FROM correction_labels WHERE"
                   " example_id=?", (j["example_id"],))[0] \
        if j.get("example_id") else 0
    env = w.envelope(j["example_id"]) if j.get("example_id") else {}
    return arts == 0 and labels == 0 and not (env or {}).get("annotations")


# ---- notes -----------------------------------------------------------------


def _ns(w):
    return notes_mod.NoteStore(w.store)


def _link(w, nid, j):
    w.store.submit(lambda c: c.execute(
        "INSERT INTO note_evidence_links(note_id, example_id, job_id,"
        " first_seen_utc) VALUES(?,?,?,?)",
        (nid, j["example_id"], j["job_id"], ids.now_utc_iso())))


def _typed(ns, nid, text):
    return ns.append_revision(nid, text, origin=notes_mod.ORIGIN_TYPED,
                              trigger=notes_mod.TRIGGER_AUTOSAVE)


def _arrive(ns, nid, content, at, text, job_id, preimage=None):
    """A dictated arrival: ``text`` landed at code point ``at``."""
    return ns.append_revision(
        nid, content, origin=notes_mod.ORIGIN_DICTATED,
        trigger=notes_mod.TRIGGER_SYSTEM, source_job_id=job_id,
        inserted_at_chars=at, inserted_text=text, preimage=preimage)


def _latest_spans(w, nid):
    row = w.one("SELECT spans_json FROM note_revisions WHERE note_id=?"
                " ORDER BY rowid DESC LIMIT 1", (nid,))
    return json.loads(row[0] or "[]") if row else None


def _note_single(w, ns, j):
    nid = ns.create_note(j["raw"], origin=notes_mod.ORIGIN_DICTATED,
                         source_job_id=j["job_id"])["note_id"]
    _link(w, nid, j)
    return nid


A_TEXT = "alpha checks the modul today"
B_TEXT = "bravo sends our reprot tonight"


def _note_ab(w, ns):
    """One note holding dictation A then dictation B (each span carrying
    its job), both linked. Returns (a, b, nid, spans)."""
    a = w.job(A_TEXT)
    b = w.job(B_TEXT)
    nid = ns.create_note(A_TEXT, origin=notes_mod.ORIGIN_DICTATED,
                         source_job_id=a["job_id"])["note_id"]
    _arrive(ns, nid, f"{A_TEXT} {B_TEXT}", len(A_TEXT) + 1, B_TEXT,
            b["job_id"])
    _link(w, nid, a)
    _link(w, nid, b)
    return a, b, nid, _latest_spans(w, nid)


def _ab_spans_ok(spans, a, b):
    return spans == [[0, 5, "dictated", a["job_id"]],
                     [5, 10, "dictated", b["job_id"]]]


def _note_cands(w):
    return _cands(w, "source='note_revision'")


# =============================================================================
# explicit_teaching
# =============================================================================


@drives("LF-M14-C001")
def c001_positive_word_correction(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        norm_before = w.normalize(TEACH_RAW, app=APP)
        entries_before = w.entries()
        was_refused, out = _teach(w, j["job_id"], TEACH_FIX,
                                  _render(w, j["applied_aid"]))
        rows = _cands(w)
        c = rows[0] if len(rows) == 1 else {}
        p = _payload(w, c.get("payload_aid"))
        body = json.loads(p[3]) if p and p[3] else {}
        return check({
            "teach_accepted": not was_refused,
            "one_candidate": len(rows) == 1,
            "job_owned": c.get("job_id") == j["job_id"]
            and c.get("example_id") == j["example_id"],
            "live_pending": c.get("status") == "pending",
            "payload_retained_and_owned": bool(p) and p[0] ==
            "candidate_observation" and p[1] == j["job_id"] and not p[2],
            "payload_is_the_rendered_final": body.get("before") == TEACH_RAW
            and body.get("after") == TEACH_FIX,
            "no_vocabulary_change": w.entries() == entries_before == {},
            "no_pipeline_change": w.normalize(TEACH_RAW, app=APP)
            == norm_before == TEACH_RAW,
        }, {"candidates": len(rows), "status": c.get("status"),
            "alias": c.get("alias"), "canonical": c.get("canonical")},
            witness="teach_correction single writer op; rows and payload"
                    " read by SQL; M05 sandbox normalize unchanged")


@drives("LF-M14-C002")
def c002_collection_off(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW, example=False)
        ex_before = w.one("SELECT COUNT(*) FROM training_examples")[0]
        was_refused, out = _teach(w, j["job_id"], TEACH_FIX,
                                  _render(w, j["applied_aid"]))
        rows = _cands(w)
        c = rows[0] if len(rows) == 1 else {}
        app_refused, app = _refused(w.learning.approve,
                                    c.get("candidate_id"))
        after = _cands(w)
        ex_after = w.one("SELECT COUNT(*) FROM training_examples")[0]
        return check({
            "teach_accepted": not was_refused,
            "one_job_only_candidate": len(rows) == 1
            and c.get("job_id") == j["job_id"]
            and c.get("example_id") is None,
            "pending": c.get("status") == "pending",
            "actionable_approve": not app_refused and after
            and after[0]["status"] == "approved"
            and bool(_entries_with_alias(w, "modul")),
            "no_example_invented": ex_before == ex_after == 0,
        }, {"candidates": len(rows), "approve": None if app_refused
            else "ok", "examples": ex_after},
            witness="job with no training example; teach falls back to"
                    " the job's own applied_output; approve composes")


@drives("LF-M14-C003")
def c003_punctuation_only(entry):
    with MWorld() as w:
        j = w.job("Wait here.")
        was_refused, out = _teach(w, j["job_id"], "Wait here!",
                                  _render(w, j["applied_aid"]))
        rows = _cands(w)
        c = rows[0] if rows else {}
        p = _payload(w, c.get("payload_aid"))
        regions = (json.loads(p[3]) if p and p[3] else {}).get("regions")
        unchanged_refused, _ = _teach(w, j["job_id"], "Wait here.",
                                      _render(w, j["applied_aid"]))
        k = w.job(TEACH_RAW)
        ctl_refused, _ = _teach(w, k["job_id"], TEACH_FIX,
                                _render(w, k["applied_aid"]))
        return check({
            "recorded_not_refused": not was_refused and len(rows) == 1,
            "punctuation_axis": c.get("axes", {}).get("edit_kind")
            == "punctuation_or_structure",
            "no_asr_alias": c.get("alias") is None
            and c.get("canonical") is None and w.entries() == {},
            "character_level_span": c.get("spans") == [{"start": 9,
                                                        "end": 10}]
            and bool(regions) and regions[0].get("before_chars") == "."
            and regions[0].get("after_chars") == "!",
            "true_unchanged_still_refused": unchanged_refused,
            "word_control_still_taught": not ctl_refused,
        }, {"edit_kind": c.get("axes", {}).get("edit_kind"),
            "spans": c.get("spans"), "refused": out if was_refused
            else None}, witness="D13 punctuation branch (format_regions)",
            grading="decision", decision="m14-policy-r1:D13")


@drives("LF-M14-C004")
def c004_identical(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        before = _counts(w)
        was_refused, msg = _teach(w, j["job_id"], TEACH_RAW,
                                  _render(w, j["applied_aid"]))
        after_refusal = _counts(w)
        ok_refused, _ = _teach(w, j["job_id"], TEACH_FIX,
                               _render(w, j["applied_aid"]))
        after_positive = _counts(w)
        return check({
            "refused_unchanged": was_refused and "unchanged" in str(msg),
            "nothing_added": before == after_refusal,
            "positive_companion_taught": not ok_refused,
            "counters_observe_a_teach": after_positive[
                "learning_candidates"] == before["learning_candidates"] + 1
            and after_positive["artifacts"] == before["artifacts"] + 1
            and after_positive["artifact_leases"]
            == before["artifact_leases"] + 1,
        }, {"refusal": msg if was_refused else None, "before": before,
            "after_refusal": after_refusal,
            "after_positive": after_positive},
            witness="teach refused before mint; SQL counts of candidates,"
                    " artifacts and leases")


@drives("LF-M14-C005")
def c005_stale_final(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        f1 = _render(w, j["applied_aid"])       # rendered F1
        f2_text = "please check the modal today again"
        f2 = w.store.write_text_artifact(
            job_id=j["job_id"], stage="cleanup", role="applied_output",
            text=f2_text, retention_class="training",
            parent_artifact_id=j["raw_aid"])
        w.rewrite_envelope(j["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("applied_output", f2))
        before = _counts(w)
        was_refused, out = _teach(w, j["job_id"], TEACH_FIX, f1)
        rows = _cands(w, "job_id=?", (j["job_id"],))
        compared = None
        for c in rows:
            p = _payload(w, c["payload_aid"])
            compared = (json.loads(p[3]) if p and p[3] else {}).get(
                "before")
        k = w.job(TEACH_RAW)
        ctl_refused, _ = _teach(w, k["job_id"], TEACH_FIX,
                                _render(w, k["applied_aid"]))
        return check({
            "refused_stale": was_refused,
            "no_candidate": not rows,
            "nothing_added": _counts(w)["learning_candidates"]
            == before["learning_candidates"] + (0 if ctl_refused else 1),
            "never_compared_to_f2_or_raw": compared not in (f2_text,
                                                            TEACH_RAW)
            or compared is None,
            "current_render_control_taught": not ctl_refused,
        }, {"refusal": out if was_refused else None,
            "compared_against": "F2" if compared == f2_text else
            ("raw" if compared == TEACH_RAW else compared)},
            witness="F2 appended after render; teach carries F1 identity",
            grading="decision", decision="m14-policy-r1:D13")


@drives("LF-M14-C006")
def c006_missing_applied(entry):
    fixed = "Please check the module today."
    obs = {}
    conds = {}
    for example in (True, False):
        tag = "example" if example else "job_only"
        with MWorld() as w:
            j = w.job(TEACH_RAW, "Please check the modul today.",
                      example=example)
            shown = _render(w, j["applied_aid"])
            w.purge(j["applied_aid"])
            raw_row = w.artifact_row(j["raw_aid"])
            was_refused, out = _teach(w, j["job_id"], fixed, shown)
            rows = _cands(w)
            raw_used = any(TEACH_RAW in ((_payload(w, c["payload_aid"])
                                          or (0, 0, 0, ""))[3] or "")
                           for c in rows)
            k = w.job(TEACH_RAW, "Please check the modul today.",
                      example=example)
            ctl_refused, _ = _teach(w, k["job_id"], fixed,
                                    _render(w, k["applied_aid"]))
            conds[f"{tag}_refused"] = was_refused
            conds[f"{tag}_no_candidate"] = not [
                c for c in rows if c["job_id"] == j["job_id"]]
            conds[f"{tag}_no_raw_fallback"] = not raw_used
            conds[f"{tag}_raw_still_retained"] = raw_row is not None \
                and not raw_row[2]
            conds[f"{tag}_retained_control_taught"] = not ctl_refused
            obs[tag] = out if was_refused else "taught"
    return check(conds, obs, witness="applied_output purged via the"
                 " store purge path; raw kept; with and without example",
                 grading="decision", decision="m14-policy-r1:D13")


@drives("LF-M14-C007")
def c007_transformed_final_guard(entry):
    from test_m14_remediation import _hub_env, _make_hub
    Harness, MainQueue = _hub_env()
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = _make_hub(h)
            assert mq.drain(hub.state, 60)
            from localflow.v2.history_queries import HistoryQueryService
            from localflow.v2.ui.state import VIEWS
            learning = h.d._learning
            calls = []
            orig = learning.teach_correction

            def spy(job_id, corrected, **kw):
                calls.append(job_id)
                return orig(job_id, corrected, **kw)
            learning.teach_correction = spy
            s = h.d.store

            def mkjob(transformed):
                job, _fam = s.create_job()
                s.write_text_artifact(job_id=job, stage="asr",
                                      role="raw_transcript", text=TEACH_RAW,
                                      retention_class="history")
                s.write_text_artifact(job_id=job, stage="cleanup",
                                      role="applied_output", text=TEACH_RAW,
                                      retention_class="history")
                if transformed:
                    s.write_text_artifact(
                        job_id=job, stage="transform",
                        role="transform_output",
                        text="Please check the modul today, formally.",
                        retention_class="history")
                s.update_job_state(job, "confirmed")
                return job
            tjob, cjob = mkjob(True), mkjob(False)
            hq = HistoryQueryService(s)
            stages = {j: (hq.job_detail(j) or {}).get("final_stage")
                      for j in (tjob, cjob)}
            if stages != {tjob: "transformed", cjob: "cleaned"}:
                return invalid("fixture: History did not render the"
                               " transformed/cleaned final stages",
                               {"stages": sorted(stages.values(),
                                                 key=str)})
            for job in (tjob, cjob):
                hub._select_view_index(VIEWS.index("history"))
                assert mq.drain(hub.state, 60)
                hub.state.select_history_row("job", job)
                assert mq.drain(hub.state, 60)
                hub.teach_field.setStringValue_(TEACH_FIX)
                hub.historyTeach_(None)
            per_job = {job: s.submit(lambda c, j=job: c.execute(
                "SELECT COUNT(*) FROM learning_candidates WHERE job_id=?",
                (j,)).fetchone()[0]) for job in (tjob, cjob)}
            return check({
                "transformed_row_refused_before_service": tjob not in calls,
                "no_candidate_for_transformed": per_job[tjob] == 0,
                "cleaned_control_reaches_teach": cjob in calls,
                "cleaned_control_candidate": per_job[cjob] == 1,
            }, {"teach_calls": len(calls), "transformed_candidates":
                per_job[tjob], "cleaned_candidates": per_job[cjob]},
                witness="HubController.historyTeach_ headless; History"
                        " detail final_stage transformed vs cleaned")
    finally:
        h.close()


@drives("LF-M14-C008")
def c008_restricted(entry):
    with MWorld() as w:
        conds, obs = {}, {}
        for st in ("excluded", "expired", "quarantined_sensitive",
                   "deleted"):
            j = w.job(TEACH_RAW)
            shown = _render(w, j["applied_aid"])
            if st == "deleted":
                w.store.delete_everywhere("job", j["job_id"])
            else:
                w.set_state(j["example_id"], st)
            before = _counts(w)
            live_arts = w.one("SELECT COUNT(*) FROM artifacts WHERE"
                              " job_id=? AND purged=0", (j["job_id"],))[0]
            was_refused, msg = _teach(w, j["job_id"], TEACH_FIX, shown)
            state = w.one("SELECT state FROM training_examples WHERE"
                          " example_id=?", (j["example_id"],))[0]
            conds[f"{st}_refused"] = was_refused
            conds[f"{st}_nothing_created"] = _counts(w) == before
            conds[f"{st}_state_not_restored"] = state == st
            conds[f"{st}_no_evidence_restored"] = w.one(
                "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                " purged=0", (j["job_id"],))[0] == live_arts
            obs[st] = msg if was_refused else "taught"
        k = w.job(TEACH_RAW)
        ctl_refused, _ = _teach(w, k["job_id"], TEACH_FIX,
                                _render(w, k["applied_aid"]))
        conds["live_control_taught"] = not ctl_refused
        return check(conds, obs, witness="each restricted state admitted"
                     " independently; SQL counts per variant")


# =============================================================================
# m08_observation_mining
# =============================================================================


@drives("LF-M14-C009")
def c009_positive_owned_edit(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        obs = w.observation(j["job_id"], TEACH_RAW, TEACH_FIX)
        n1 = _mine(w)
        n2 = _mine(w)
        rows = _cands(w, "observation_id=?", (obs,))
        c = rows[0] if len(rows) == 1 else {}
        p = _payload(w, c.get("payload_aid"))
        return check({
            "exactly_one": len(rows) == 1 and n1 == 1 and n2 == 0,
            "source_observation_id": c.get("observation_id") == obs
            and c.get("source") == "edit_observation",
            "live_ownership": c.get("job_id") == j["job_id"]
            and c.get("example_id") == j["example_id"]
            and c.get("status") == "pending",
            "payload_owned_and_retained": bool(p) and p[1] == j["job_id"]
            and not p[2],
        }, {"mined": [n1, n2], "status": c.get("status"),
            "alias": c.get("alias")},
            witness="owned_range_edited observation with the job's own"
                    " observation_before_range/after_range artifacts")


def _mining_negative(entry, stops, *, witness, extra=None):
    """Observations with non-certified stop reasons never mint; a
    certified same-shape observation in the same world does."""
    with MWorld() as w:
        neg = []
        for stop in stops:
            j = w.job(TEACH_RAW)
            neg.append((stop, j, w.observation(j["job_id"], TEACH_RAW,
                                               TEACH_FIX, stop=stop)))
        p = w.job(TEACH_RAW)
        pobs = w.observation(p["job_id"], TEACH_RAW, TEACH_FIX)
        _mine(w)
        conds = {}
        for stop, j, obs in neg:
            rows = _cands(w, "observation_id=? OR job_id=?",
                          (obs, j["job_id"]))
            conds[f"{stop}_no_candidate"] = not [
                r for r in rows if r["status"] in ("pending", "suppressed")
                or r["alias"]]
            conds[f"{stop}_no_payload"] = w.one(
                "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                " role='candidate_observation'", (j["job_id"],))[0] == 0
            conds[f"{stop}_no_asr_truth"] = _no_review_truth(w, j)
        prow = _cands(w, "observation_id=?", (pobs,))
        conds["certified_control_mined"] = len(prow) == 1 and \
            prow[0]["status"] == "pending"
        return check(conds, {"negatives": len(neg), "control": [
            r["status"] for r in prow]}, witness=witness)


@drives("LF-M14-C010")
def c010_ambiguous(entry):
    return _mining_negative(entry, ("owned_edit_unbounded",
                                    "reanchor_ambiguous"),
                            witness="uncertified stop reasons beside an"
                                    " owned_range_edited control")


@drives("LF-M14-C011")
def c011_selection_drift(entry):
    return _mining_negative(entry, ("field_changed", "focus_lost",
                                    "target_read_failed",
                                    "reanchor_deadline"),
                            witness="drift stop reasons beside an"
                                    " owned_range_edited control")


@drives("LF-M14-C012")
def c012_denied_secure(entry):
    with MWorld() as w:
        protected = f"hunter2 {PRIVATE_CANARY}"
        # Producer shape: a secure/denied window never writes artifacts.
        s = w.job(TEACH_RAW)
        d = w.job(TEACH_RAW)
        o_secure = _obs_row(w, s["job_id"], "secure_field_transition")
        o_denied = _obs_row(w, d["job_id"], "authority_revoked")
        # Corrupted shape: artifacts exist but the stop is not an owned
        # edit — still never mined.
        x = w.job(TEACH_RAW)
        o_x = w.observation(x["job_id"], TEACH_RAW, protected,
                            stop="secure_field_transition")
        canary_arts = {r[0] for r in w.rows(
            "SELECT artifact_id FROM artifacts WHERE content_text LIKE ?",
            (f"%{PRIVATE_CANARY}%",))}
        p = w.job(TEACH_RAW)
        pobs = w.observation(p["job_id"], TEACH_RAW, TEACH_FIX)
        _mine(w)
        after_arts = {r[0] for r in w.rows(
            "SELECT artifact_id FROM artifacts WHERE content_text LIKE ?",
            (f"%{PRIVATE_CANARY}%",))}
        row_text = [v for r in w.rows("SELECT * FROM learning_candidates")
                    for v in r if isinstance(v, str)
                    and PRIVATE_CANARY in v]
        neg = _cands(w, "observation_id IN (?,?,?)",
                     (o_secure, o_denied, o_x))
        prow = _cands(w, "observation_id=?", (pobs,))
        return check({
            "no_candidate_for_secure_or_denied": not neg,
            "no_new_protected_content": after_arts == canary_arts,
            "no_protected_text_in_rows": not row_text,
            "no_candidate_payloads": w.one(
                "SELECT COUNT(*) FROM artifacts WHERE role="
                "'candidate_observation' AND job_id IN (?,?,?)",
                (s["job_id"], d["job_id"], x["job_id"]))[0] == 0,
            "owned_control_mined": len(prow) == 1
            and prow[0]["status"] == "pending",
        }, {"negatives": len(neg), "fixture_protected_artifacts":
            len(canary_arts), "control": [r["status"] for r in prow]},
            witness="secure_field_transition / authority_revoked rows"
                    " (producer shape, no artifacts) and a corrupted"
                    " variant with artifacts")


@drives("LF-M14-C013")
def c013_foreign_payload(entry):
    with MWorld() as w:
        a = w.job(TEACH_RAW)
        b = w.job(f"bravo unrelated dictation {PRIVATE_CANARY}")
        obs = w.observation(a["job_id"], TEACH_RAW, TEACH_FIX,
                            before_job=b["job_id"], after_job=b["job_id"])
        p = w.job(TEACH_RAW)
        pobs = w.observation(p["job_id"], TEACH_RAW, TEACH_FIX)
        _mine(w)
        rows = _cands(w, "observation_id=?", (obs,))
        prow = _cands(w, "observation_id=?", (pobs,))
        return check({
            "refused_foreign": not [r for r in rows if r["status"] in (
                "pending", "suppressed", "approved") or r["alias"]],
            "no_payload_minted_for_a": w.one(
                "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND role="
                "'candidate_observation'", (a["job_id"],))[0] == 0,
            "own_observation_control_mined": len(prow) == 1
            and prow[0]["status"] == "pending",
        }, {"rows": [(r["status"], r["axes"].get("abstain_reason"))
                     for r in rows], "control": [r["status"]
                                                 for r in prow]},
            witness="before/after artifacts owned by job B on A's"
                    " observation; D11 observation roles",
            grading="decision", decision="m14-policy-r1:D11")


@drives("LF-M14-C014")
def c014_unmatched_text(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        obs = w.observation(
            j["job_id"], TEACH_RAW,
            "the quarterly budget spreadsheet has seventeen columns now")
        p = w.job(TEACH_RAW)
        pobs = w.observation(p["job_id"], TEACH_RAW, TEACH_FIX)
        _mine(w)
        rows = _cands(w, "observation_id=?", (obs,))
        prow = _cands(w, "observation_id=?", (pobs,))
        return check({
            "abstained_or_dismissed": all(r["status"] in (
                "dismissed", "stale") for r in rows),
            "no_recognition_learning": not [
                r for r in rows if r["alias"]
                or r["axes"].get("edit_kind") == "recognition_error"],
            "no_asr_truth": _no_review_truth(w, j),
            "control_learns_recognition": len(prow) == 1
            and prow[0]["alias"] == "modul"
            and prow[0]["status"] == "pending",
        }, {"rows": [(r["status"], r["axes"].get("edit_kind"))
                     for r in rows]},
            witness="low-overlap after text; classifier reliability gate")


@drives("LF-M14-C015")
def c015_deleted_job(entry):
    with MWorld() as w:
        t = w.job(TEACH_RAW)
        tobs = w.observation(t["job_id"], TEACH_RAW, TEACH_FIX)
        p = w.job(TEACH_RAW)
        pobs = w.observation(p["job_id"], TEACH_RAW, TEACH_FIX)
        state = {"fired": False, "cands_at_fire": None}

        def hook():
            if state["fired"]:
                return
            state["fired"] = True
            state["cands_at_fire"] = w.one(
                "SELECT COUNT(*) FROM learning_candidates")[0]
            w.store.delete_everywhere("job", t["job_id"])
        with after_each_op(w.store, hook):
            _mine(w)
        if not state["fired"] or state["cands_at_fire"] != 0:
            return invalid("deletion did not land before the miner's"
                           " first writer op", state)
        again = _mine(w)
        trows = _cands(w, "observation_id=? OR job_id=?",
                       (tobs, t["job_id"]))
        prow = _cands(w, "observation_id=?", (pobs,))
        return check({
            "no_candidate_for_deleted_job": not [
                r for r in trows if r["status"] in ("pending", "suppressed",
                                                    "approved")],
            "no_payload_resurrected": w.one(
                "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                " purged=0", (t["job_id"],))[0] == 0,
            "second_pass_still_nothing": not [
                r for r in _cands(w, "job_id=?", (t["job_id"],))
                if r["status"] == "pending"],
            "live_control_mined": len(prow) == 1
            and prow[0]["status"] == "pending",
        }, {"deleted_job_rows": len(trows), "second_pass": again},
            witness="after_each_op: delete_everywhere after the miner's"
                    " scan op, before its per-observation writer op",
            reached="m14_c015_after_scan")


# =============================================================================
# m12_note_mining
# =============================================================================


@drives("LF-M14-C016")
def c016_positive_single(entry):
    with MWorld() as w:
        ns = _ns(w)
        a = w.job(A_TEXT)
        nid = _note_single(w, ns, a)
        _typed(ns, nid, "alpha checks the module today")
        _mine(w)
        rows = _note_cands(w)
        c = rows[0] if len(rows) == 1 else {}
        p = _payload(w, c.get("payload_aid"))
        body = json.loads(p[3]) if p and p[3] else {}
        regions = body.get("regions") or []
        return check({
            "one_candidate": len(rows) == 1,
            "job_identity": c.get("job_id") == a["job_id"]
            and c.get("example_id") == a["example_id"],
            "only_a_region": [(r.get("before_words"), r.get("after_words"))
                              for r in regions] == [(["modul"],
                                                     ["module"])]
            and set(body) == {"regions"},
            "offsets": c.get("spans") == [{"start": 17, "end": 22}],
        }, {"candidates": len(rows), "spans": c.get("spans")},
            witness="real NoteStore dictated note + typed revision;"
                    " note_evidence_links; mine_observation_candidates",
            grading="decision", decision="m14-policy-r1:D14")


def _ab_edit(entry, edit_a, *, witness, reached=None):
    """A+B note; ``edit_a`` True edits only A's words, False only B's."""
    with MWorld() as w:
        ns = _ns(w)
        a, b, nid, spans = _note_ab(w, ns)
        if not _ab_spans_ok(spans, a, b):
            return invalid("A+B spans/links did not persist", spans)
        if edit_a:
            _typed(ns, nid, f"alpha checks the module today {B_TEXT}")
            own, other, words = a, b, (["modul"], ["module"])
        else:
            _typed(ns, nid, f"{A_TEXT} bravo sends our report tonight")
            own, other, words = b, a, (["reprot"], ["report"])
        _mine(w)
        rows = _note_cands(w)
        mine_rows = [r for r in rows if r["job_id"] == own["job_id"]]
        c = mine_rows[0] if len(mine_rows) == 1 else {}
        p = _payload(w, c.get("payload_aid"))
        regions = (json.loads(p[3]) if p and p[3] else {}).get(
            "regions") or []
        return check({
            "edited_job_receives_evidence": len(mine_rows) == 1
            and c.get("example_id") == own["example_id"]
            and c.get("status") == "pending",
            "exact_regions_only": [(r.get("before_words"),
                                    r.get("after_words"))
                                   for r in regions] == [words],
            "other_job_receives_none": not [
                r for r in rows if r["job_id"] == other["job_id"]],
        }, {"rows": [(r["job_id"] == a["job_id"] and "A" or "B",
                      r["status"]) for r in rows]},
            witness=witness, grading="decision",
            decision="m14-policy-r1:D14", reached=reached)


@drives("LF-M14-C017")
def c017_edit_first_of_two(entry):
    return _ab_edit(entry, True, witness="A+B spans persisted"
                    " (dictated arrival with job); typed edit inside A")


@drives("LF-M14-C018")
def c018_edit_second_of_two(entry):
    return _ab_edit(entry, False, witness="A+B spans persisted"
                    " (dictated arrival with job); typed edit inside B")


def _ab_cross(entry, *, witness, reached=None):
    with MWorld() as w:
        ns = _ns(w)
        a, b, nid, spans = _note_ab(w, ns)
        if not _ab_spans_ok(spans, a, b):
            return invalid("A+B spans/links did not persist", spans)
        # One replaced region: A's last word + B's first word.
        _typed(ns, nid, "alpha checks the modul todaybravo sends our"
                        " reprot tonight")
        _mine(w)
        rows = _note_cands(w)
        with MWorld() as w2:
            ns2 = _ns(w2)
            a2, b2, nid2, spans2 = _note_ab(w2, ns2)
            _typed(ns2, nid2, f"alpha checks the module today {B_TEXT}")
            _mine(w2)
            ctl = _note_cands(w2)
        return check({
            "no_single_job_attribution": not [
                r for r in rows if r["status"] in ("pending", "suppressed")
                or r["job_id"] in (a["job_id"], b["job_id"])],
            "inside_a_control_attributed": len(ctl) == 1
            and ctl[0]["job_id"] == a2["job_id"],
        }, {"rows": len(rows), "control": len(ctl)}, witness=witness,
            grading="decision", decision="m14-policy-r1:D14",
            reached=reached)


@drives("LF-M14-C019")
def c019_cross_two(entry):
    return _ab_cross(entry, witness="one replace opcode straddling the"
                     " A/B span boundary; control edits inside A")


@drives("LF-M14-C020")
def c020_typed_plus_dictated(entry):
    with MWorld() as w:
        ns = _ns(w)
        a = w.job(A_TEXT)
        nid = _note_single(w, ns, a)
        _typed(ns, nid, f"{A_TEXT} and {TYPED_CANARY} words")
        _typed(ns, nid, f"alpha checks the module today and"
                        f" {TYPED_CANARY}x words")
        _mine(w)
        rows = _note_cands(w)
        leaks, regions = [], []
        for c in rows:
            p = _payload(w, c["payload_aid"])
            text = p[3] if p and p[3] else ""
            if TYPED_CANARY in text:
                leaks.append(c["candidate_id"])
            regions += (json.loads(text) if text else {}).get(
                "regions") or []
        return check({
            "typed_region_excluded": not leaks,
            "a_correction_kept": len(rows) == 1
            and rows[0]["job_id"] == a["job_id"]
            and [(r.get("before_words"), r.get("after_words"))
                 for r in regions] == [(["modul"], ["module"])],
        }, {"candidates": len(rows), "leaks": len(leaks)},
            witness="one typed revision: a correction inside A's span plus"
                    " a change to typed-only words",
            grading="decision", decision="m14-policy-r1:D14")


@drives("LF-M14-C021")
def c021_legacy_no_job(entry):
    with MWorld() as w:
        ns = _ns(w)
        a = w.job(A_TEXT)
        b = w.job(B_TEXT)
        # A pre-attribution span: dictated, no producing job recorded.
        nid = ns.create_note(A_TEXT, origin=notes_mod.ORIGIN_DICTATED)[
            "note_id"]
        spans = _latest_spans(w, nid)
        _link(w, nid, a)
        _link(w, nid, b)
        _typed(ns, nid, "alpha checks the module today")
        # Control: the same legacy span with exactly one live link.
        c = w.job("charlie reads the modul aloud")
        nid2 = ns.create_note(c["raw"], origin=notes_mod.ORIGIN_DICTATED)[
            "note_id"]
        _link(w, nid2, c)
        _typed(ns, nid2, "charlie reads the module aloud")
        if spans != [[0, 5, "dictated"]]:
            return invalid("fixture: legacy span carried a job", spans)
        _mine(w)
        rev_ids = [r[0] for r in w.rows(
            "SELECT revision_id FROM note_revisions WHERE note_id=?",
            (nid,))]
        guessed = [r for r in _note_cands(w)
                   if r["observation_id"] in rev_ids]
        ctl = [r for r in _note_cands(w) if r["job_id"] == c["job_id"]]
        return check({
            "no_guessed_job": not guessed,
            "single_link_control_attributed": len(ctl) == 1
            and ctl[0]["example_id"] == c["example_id"],
        }, {"guessed": len(guessed), "control": len(ctl)},
            witness="job-less dictated span with two live links vs one")


@drives("LF-M14-C022")
def c022_repeated_words(entry):
    conds, obs = {}, {}

    def single(content, edited):
        with MWorld() as w:
            ns = _ns(w)
            a = w.job(content)
            nid = _note_single(w, ns, a)
            _typed(ns, nid, edited)
            _mine(w)
            return _note_cands(w), a

    # Change of the second occurrence, all words A's: offsets must name
    # the second occurrence (a reassignment would name [0, 3]).
    rows, a = single("foo x foo", "foo x fob")
    conds["x_second_change_not_reassigned"] = len(rows) == 1 and \
        rows[0]["spans"] == [{"start": 6, "end": 9}]
    obs["foo_x_foo"] = [r["spans"] for r in rows]
    # Among identical copies the word diff may read the change as an
    # insertion plus a deletion; either the exact second-occurrence
    # offsets or an abstaining, rule-free record is acceptable — never
    # a region on the first occurrence.
    rows, a = single("foo foo foo", "foo fob foo")
    conds["triple_second_change_not_reassigned"] = len(rows) <= 1 and all(
        r["spans"] == [{"start": 4, "end": 7}]
        or (r["alias"] is None and r["axes"].get("abstained")
            and {"start": 0, "end": 3} not in r["spans"]) for r in rows)
    obs["foo_foo_foo_change"] = [(r["spans"], r["axes"].get("edit_kind"))
                                 for r in rows]
    # Delete the second occurrence: which copy went cannot be told.
    rows, a = single("foo foo foo", "foo foo")
    conds["triple_delete_abstains"] = all(
        r["alias"] is None and r["axes"].get("abstained")
        and r["spans"] != [{"start": 0, "end": 3}] for r in rows)
    obs["foo_foo_foo_delete"] = [(r["spans"], r["axes"].get("edit_kind"))
                                 for r in rows]
    # Declared origin map independent of the diff: A dictated only the
    # FIRST "foo" (arrival at 0 into typed "x foo"); the typed second
    # occurrence changes — never reassigned to A.
    with MWorld() as w:
        ns = _ns(w)
        a = w.job("foo")
        nid = ns.create_note("x foo")["note_id"]
        _arrive(ns, nid, "foo x foo", 0, "foo", a["job_id"],
                preimage="x foo")
        spans = _latest_spans(w, nid)
        _link(w, nid, a)
        _typed(ns, nid, "foo x fob")
        _mine(w)
        rows = _note_cands(w)
    if spans != [[0, 1, "dictated", a["job_id"]]]:
        return invalid("fixture: declared first-occurrence span absent",
                       spans)
    conds["typed_occurrence_not_given_to_a"] = not rows
    obs["declared_first_only"] = [r["spans"] for r in rows]
    return check(conds, obs, witness="rebase_spans occurrence check +"
                 " per-region attribution; offsets vs literal positions",
                 grading="decision", decision="m14-policy-r1:D14")


@drives("LF-M14-C023")
def c023_whitespace_unicode(entry):
    conds, obs = {}, {}
    with MWorld() as w:
        ns = _ns(w)
        arrival = "check the modul, today\nplease \U0001F389"
        a = w.job("check the modul today please")
        c0 = "intro\U0001F642 text"
        nid = ns.create_note(c0)["note_id"]
        c1 = f"{c0} {arrival}"
        _arrive(ns, nid, c1, len(c0) + 1, arrival, a["job_id"],
                preimage=c0)
        spans = _latest_spans(w, nid)
        _link(w, nid, a)
        c2 = c1.replace("modul,", "module,").replace(" text ", " texts ")
        _typed(ns, nid, c2)
        _mine(w)
        rows = _note_cands(w)
        if spans != [[2, 8, "dictated", a["job_id"]]]:
            return invalid("fixture: arrival span not placed", spans)
        c = rows[0] if len(rows) == 1 else {}
        p = _payload(w, c.get("payload_aid"))
        text = p[3] if p and p[3] else ""
        start = c1.index("modul")
        sp = (c.get("spans") or [{}])[0]
        conds["one_a_candidate"] = len(rows) == 1 and \
            c.get("job_id") == a["job_id"]
        conds["offsets_exact_original_chars"] = c.get("spans") == [
            {"start": start, "end": start + 5}] and \
            c1[sp.get("start", 0):sp.get("end", 0)] == "modul"
        conds["typed_word_not_acquired"] = "texts" not in text and \
            "intro" not in text
        obs["spans"] = c.get("spans")
        obs["expected_start"] = start
    with MWorld() as w:
        ns = _ns(w)
        a = w.job("modul to today")
        nid = ns.create_note("pre")["note_id"]
        _arrive(ns, nid, "premodul to today", 3, "modul to today",
                a["job_id"], preimage="pre")
        spans = _latest_spans(w, nid)
        _link(w, nid, a)
        _typed(ns, nid, "premodule to todays")
        _mine(w)
        rows = _note_cands(w)
        if spans != [[1, 3, "dictated", a["job_id"]]]:
            return invalid("fixture: partial-word arrival span", spans)
        c = rows[0] if len(rows) == 1 else {}
        p = _payload(w, c.get("payload_aid"))
        text = p[3] if p and p[3] else ""
        conds["partial_word_not_acquired"] = "premodul" not in text
        conds["whole_arrived_word_kept"] = len(rows) == 1 and \
            c.get("spans") == [{"start": 12, "end": 17}] and \
            "todays" in text
        obs["partial_spans"] = c.get("spans")
    return check(conds, obs, witness="NBSP/newline/emoji/punctuation"
                 " arrival via NoteStore; partial-word arrival abstains",
                 grading="decision", decision="m14-policy-r1:D14")


@drives("LF-M14-C024")
def c024_typed_transform_only(entry):
    with MWorld() as w:
        ns = _ns(w)
        a = w.job(A_TEXT)
        typed_nid = ns.create_note(A_TEXT)["note_id"]      # typed origin
        _link(w, typed_nid, a)
        _typed(ns, typed_nid, "alpha checks the module today")
        tf_nid = ns.create_note(A_TEXT, origin=notes_mod.ORIGIN_TRANSFORM,
                                task_key="synthetic-task")["note_id"]
        tf_spans = _latest_spans(w, tf_nid)
        _link(w, tf_nid, a)
        _typed(ns, tf_nid, "alpha checks the module today")
        b = w.job(B_TEXT)
        ctl_nid = _note_single(w, ns, b)
        _typed(ns, ctl_nid, "bravo sends our report tonight")
        _mine(w)
        revs = {r[0] for r in w.rows(
            "SELECT revision_id FROM note_revisions WHERE note_id IN"
            " (?,?)", (typed_nid, tf_nid))}
        bad = [r for r in _note_cands(w) if r["observation_id"] in revs
               or r["job_id"] == a["job_id"]]
        ctl = [r for r in _note_cands(w) if r["job_id"] == b["job_id"]]
        return check({
            "transform_span_is_not_dictated": all(
                s[2] != "dictated" for s in tf_spans or []),
            "no_dictated_speech_candidate": not bad,
            "dictated_control_mined": len(ctl) == 1,
        }, {"bad": len(bad), "control": len(ctl), "tf_spans": [
            s[2] for s in tf_spans or []]},
            witness="typed-only and transform-origin notes linked to a"
                    " job; dictated control note")


@drives("LF-M14-C025")
def c025_deleted_note(entry):
    with MWorld() as w:
        ns = _ns(w)
        a = w.job(f"alpha checks the modul today {PRIVATE_CANARY}")
        d_nid = _note_single(w, ns, a)
        _typed(ns, d_nid, f"alpha checks the module today {PRIVATE_CANARY}")
        b = w.job(B_TEXT)
        u_nid = _note_single(w, ns, b)
        _typed(ns, u_nid, "bravo sends our report tonight")
        ns.delete_note(d_nid)
        _mine(w)
        d_rows = [r for r in _note_cands(w) if r["job_id"] == a["job_id"]]
        u_rows = [r for r in _note_cands(w) if r["job_id"] == b["job_id"]]
        leak = w.one("SELECT COUNT(*) FROM artifacts WHERE role="
                     "'candidate_observation' AND content_text LIKE ?",
                     ("%module today%",))[0]
        return check({
            "no_deleted_note_candidate": not d_rows,
            "no_deleted_note_payload": leak == 0,
            "unrelated_note_still_mines": len(u_rows) == 1
            and u_rows[0]["status"] == "pending",
        }, {"deleted": len(d_rows), "unrelated": len(u_rows)},
            witness="NoteStore.delete_note before mining; unrelated note"
                    " edit mined in the same pass")


# =============================================================================
# candidate_liveness
# =============================================================================


def _mined(w, raw=TEACH_RAW, fixed=TEACH_FIX, **kw):
    j = w.job(raw, **kw)
    obs = w.observation(j["job_id"], raw, fixed)
    _mine(w)
    rows = _cands(w, "observation_id=?", (obs,))
    return j, obs, (rows[0] if len(rows) == 1 else None)


@drives("LF-M14-C026")
def c026_positive_live_pending(entry):
    with MWorld() as w:
        j, obs, c = _mined(w)
        if c is None:
            return invalid("fixture: no mined candidate")
        in_queue = [x["candidate_id"] for x in
                    w.learning.candidates("pending")]
        forever_any = w.one("SELECT COUNT(*) FROM artifact_leases WHERE"
                            " expires_at_utc IS NULL AND revoked_at_utc IS"
                            " NULL")[0]
        pay_finite = _finite_live(w, c["payload_aid"])
        refused_, out = _refused(w.learning.approve, c["candidate_id"])
        return check({
            "reviewable_pending": c["status"] == "pending"
            and c["candidate_id"] in in_queue,
            "sources_retained": all(not w.artifact_row(x)[2] for x in (
                j["raw_aid"], j["applied_aid"], c["payload_aid"])),
            "no_permanent_machine_lease": forever_any == 0
            and pay_finite == 1,
            "approval_succeeds": not refused_
            and bool(_entries_with_alias(w, "modul")),
        }, {"forever_leases": forever_any, "payload_finite": pay_finite,
            "approve": "ok" if not refused_ else out},
            witness="mined candidate; lease rows by SQL; approve",
            grading="decision", decision="m14-policy-r1:D08")


@drives("LF-M14-C027")
def c027_pending_expiry(entry):
    with MWorld() as w:
        j, obs, c = _mined(w)
        if c is None:
            return invalid("fixture: no mined candidate")
        payload_before = _payload(w, c["payload_aid"])
        w.clock.advance_days(90)
        w.store.prune_training(now=w.clock())
        w.store.prune(now=w.clock())
        p = _payload(w, c["payload_aid"])
        app_refused, msg = _refused(w.learning.approve, c["candidate_id"])
        _mine(w)
        t_refused, _ = _teach(w, j["job_id"], TEACH_FIX)
        after = _cands(w, "job_id=?", (j["job_id"],))
    with MWorld() as w2:
        _j2, _o2, c2 = _mined(w2)
        ctl_refused, _ = _refused(w2.learning.approve, c2["candidate_id"]) \
            if c2 else (True, None)
    return check({
        "payload_was_live": bool(payload_before) and not payload_before[2],
        "payload_unavailable": p is None or bool(p[2]),
        "approval_refused": app_refused,
        "no_resurrection": not [r for r in after if r["status"] in (
            "pending", "approved")] and t_refused,
        "unexpired_control_approves": not ctl_refused,
    }, {"status": [r["status"] for r in after], "approve": msg},
        witness="fixed clock +90d; Store.prune_training + prune; re-mine"
                " and re-teach")


@drives("LF-M14-C028")
def c028_pending_job_delete(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW, example=False)
        _r, out = _teach(w, j["job_id"], TEACH_FIX,
                         _render(w, j["applied_aid"]))
        k = w.job(TEACH_RAW, example=False)
        _r2, out2 = _teach(w, k["job_id"], TEACH_FIX,
                           _render(w, k["applied_aid"]))
        if _r or _r2:
            return invalid("fixture: job-only teach refused", [out, out2])
        cid, kid = out["candidate_id"], out2["candidate_id"]
        w.store.delete_everywhere("job", j["job_id"])
        c = _cands(w, "candidate_id=?", (cid,))[0]
        app_refused, msg = _refused(w.learning.approve, cid)
        ctl_refused, _ = _refused(w.learning.approve, kid)
        return check({
            "job_keyed_stale": c["status"] == "stale"
            and c["alias"] is None and c["spans"] == [],
            "payload_gone": w.payload(cid) is None,
            "action_refused": app_refused,
            "live_control_approves": not ctl_refused,
        }, {"status": c["status"], "approve": msg},
            witness="delete_everywhere(job) on a job-only candidate")


@drives("LF-M14-C029")
def c029_pending_example_delete(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        _r, out = _teach(w, j["job_id"], TEACH_FIX,
                         _render(w, j["applied_aid"]))
        k = w.job(TEACH_RAW)
        _r2, out2 = _teach(w, k["job_id"], TEACH_FIX,
                           _render(w, k["applied_aid"]))
        if _r or _r2:
            return invalid("fixture: teach refused", [out, out2])
        cid, kid = out["candidate_id"], out2["candidate_id"]
        pay = w.candidate(cid)["payload_aid"]
        w.store.delete_everywhere("example", j["example_id"])
        c = _cands(w, "candidate_id=?", (cid,))[0]
        live_leases = w.one("SELECT COUNT(*) FROM artifact_leases WHERE"
                            " artifact_id=? AND revoked_at_utc IS NULL",
                            (pay,))[0]
        app_refused, msg = _refused(w.learning.approve, cid)
        ctl_refused, _ = _refused(w.learning.approve, kid)
        return check({
            "candidate_revoked": c["status"] == "stale"
            and c["alias"] is None and c["spans"] == [],
            "payload_purged_leases_revoked": w.payload(cid) is None
            and live_leases == 0,
            "action_refused": app_refused,
            "live_control_approves": not ctl_refused,
        }, {"status": c["status"], "live_leases": live_leases},
            witness="delete_everywhere(example) while pending")


@drives("LF-M14-C030")
def c030_pending_note_delete(entry):
    with MWorld() as w:
        ns = _ns(w)
        a = w.job("alpha runs mlx today")
        d_nid = _note_single(w, ns, a)
        _typed(ns, d_nid, "alpha runs MLX today")
        b = w.job("bravo buys gpu time")
        u_nid = _note_single(w, ns, b)
        _typed(ns, u_nid, "bravo buys GPU time")
        _mine(w)
        d = [r for r in _note_cands(w) if r["job_id"] == a["job_id"]]
        u = [r for r in _note_cands(w) if r["job_id"] == b["job_id"]]
        if len(d) != 1 or len(u) != 1 or not d[0]["alias"]:
            return invalid("fixture: note candidates not minted with a"
                           " rule", {"d": len(d), "u": len(u)})
        ns.delete_note(d_nid)
        dc = _cands(w, "candidate_id=?", (d[0]["candidate_id"],))[0]
        app_refused, msg = _refused(w.learning.approve,
                                    d[0]["candidate_id"])
        ctl_refused, _ = _refused(w.learning.approve, u[0]["candidate_id"])
        return check({
            "candidate_invalidated": dc["status"] == "stale"
            and dc["alias"] is None,
            "evidence_invalidated": w.payload(d[0]["candidate_id"]) is None,
            "action_refused": app_refused,
            "other_note_control_approves": not ctl_refused,
        }, {"status": dc["status"], "approve": msg},
            witness="NoteStore.delete_note on a note-derived candidate"
                    " (case-only edit, so a rule is proposed)")


@drives("LF-M14-C031")
def c031_rejected_retention(entry):
    with MWorld() as w:
        j, obs, c = _mined(w)
        if c is None or c["alias"] != "modul":
            return invalid("fixture: no mined modul candidate")
        w.learning.reject(c["candidate_id"])
        obs_arts = w.one("SELECT before_artifact_id, after_artifact_id"
                         " FROM insertion_observations WHERE"
                         " observation_id=?", (obs,))
        live_before = _payload(w, c["payload_aid"])
        w.clock.advance_days(90)
        w.store.prune_training(now=w.clock())
        w.store.prune(now=w.clock())
        row = _cands(w, "candidate_id=?", (c["candidate_id"],))[0]
        live_obs = [a for a in obs_arts if a and not w.artifact_row(a)[2]]
        text_left = w.one(
            "SELECT COUNT(*) FROM artifacts WHERE purged=0 AND"
            " (content_text LIKE '%check the modul%' OR content_text LIKE"
            " '%check the module%')")[0]
        row_blob = json.dumps(w.one("SELECT * FROM learning_candidates"
                                    " WHERE candidate_id=?",
                                    (c["candidate_id"],)))
        # The kept metadata still works: the pair stays suppressed.
        j2, obs2, c2 = _mined(w)
        return check({
            "payload_was_live": bool(live_before) and not live_before[2],
            "pair_metadata_survives": row["status"] == "rejected"
            and row["alias"] == "modul" and row["canonical"] == "module",
            "no_whole_observation": not live_obs and text_left == 0
            and TEACH_RAW not in row_blob and row["spans"] == [],
            "payload_gone": w.payload(c["candidate_id"]) is None,
            "suppression_still_effective": c2 is not None
            and c2["status"] == "suppressed",
        }, {"status": row["status"], "live_obs_artifacts": len(live_obs),
            "text_left": text_left},
            witness="reject then fixed clock +90d retention",
            grading="decision", decision="m14-policy-r1:D05")


@drives("LF-M14-C032")
def c032_reviewed_vs_user_pin(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        _r, out = _teach(w, j["job_id"], TEACH_FIX,
                         _render(w, j["applied_aid"]))
        g = w.job("send the cloud report on friday")
        spans = classify.changed_regions(g["raw"],
                                         "send the Claude report on friday")
        kw = {}
        if accepts(w.review.record_label, "expected_source_artifact_id"):
            kw = {"expected_source_artifact_id": g["raw_aid"],
                  "expected_source_sha256": _sha(g["raw"])}
        lab = w.review.record_label(g["example_id"],
                                    edit_kind="recognition_error",
                                    confirmed_spans=[spans[0]], **kw)
        m, _obs, mc = _mined(w, "please check the modal today",
                             "please check the model today")
        if _r or mc is None or not lab.get("graft_artifact_id"):
            return invalid("fixture incomplete", {"teach": out,
                                                  "mined": bool(mc)})
        teach_pay = w.candidate(out["candidate_id"])["payload_aid"]
        graft = lab["graft_artifact_id"]
        pinned_raw = {}
        for x in (j, g, m):
            w.training.pin(x["example_id"], True)
            pinned_raw[x["job_id"]] = _forever(w, x["raw_aid"])
            w.training.pin(x["example_id"], False)
        return check({
            "pin_ran": all(v == 1 for v in pinned_raw.values()),
            "unpin_ran": all(_forever(w, x["raw_aid"]) == 0
                             for x in (j, g, m)),
            "review_leases_survive_unpin": _forever(w, teach_pay) >= 1
            and _forever(w, graft) >= 1,
            "machine_candidate_stays_finite": _forever(
                w, mc["payload_aid"]) == 0
            and _finite_live(w, mc["payload_aid"]) == 1,
        }, {"teach_forever": _forever(w, teach_pay),
            "graft_forever": _forever(w, graft),
            "machine_forever": _forever(w, mc["payload_aid"])},
            witness="TrainingDataService.pin True/False on teach, graft and"
                    " machine-mined jobs; lease rows by SQL",
            grading="decision", decision="m14-policy-r1:D08")


# =============================================================================
# classifier_axes
# =============================================================================


def _modul_control(w):
    """The recognition positive companion (C033's shape) in any world."""
    _j, _o, c = _mined(w)
    return c is not None and c["alias"] == "modul" and \
        c["canonical"] == "module" and c["status"] == "pending"


@drives("LF-M14-C033")
def c033_positive_recognition(entry):
    ax = classify.classify_observation(
        TEACH_RAW, TEACH_FIX, stage_texts={"raw": TEACH_RAW,
                                           "applied": TEACH_RAW},
        evidence_status="reliable_target_observation")
    with MWorld() as w:
        j, obs, c = _mined(w)
        state = w.one("SELECT state FROM training_examples WHERE"
                      " example_id=?", (j["example_id"],))[0]
        return check({
            "classifier_recognition_asr": ax["edit_kind"]
            == "recognition_error" and ax["origin_stages"] == ["asr"],
            "caller_suggests_rule": c is not None and c["alias"] == "modul"
            and c["canonical"] == "module",
            "machine_unverified": c is not None
            and c["status"] == "pending"
            and c["axes"].get("evidence_status")
            == "reliable_target_observation",
            "no_full_asr_promotion": _no_review_truth(w, j)
            and state == "captured_unreviewed"
            and not _entries_with_alias(w, "modul"),
        }, {"edit_kind": ax["edit_kind"], "origin": ax["origin_stages"],
            "status": c and c["status"]},
            witness="classify_observation with retained stage texts +"
                    " mine_observation_candidates admission")


@drives("LF-M14-C034")
def c034_cleanup_regression(entry):
    wrong = "please check the modul today"
    ax = classify.classify_observation(
        wrong, TEACH_FIX, stage_texts={"raw": TEACH_FIX, "applied": wrong},
        evidence_status="reliable_target_observation")
    with MWorld() as w:
        j = w.job(TEACH_FIX, wrong)
        obs = w.observation(j["job_id"], wrong, TEACH_FIX)
        k = w.job(TEACH_FIX, wrong)
        t_refused, _ = _teach(w, k["job_id"], TEACH_FIX,
                              _render(w, k["applied_aid"]))
        ctl = _modul_control(w)
        rows = _cands(w, "observation_id=? OR job_id=?", (obs, k["job_id"]))
        return check({
            "classifier_origin_cleanup": ax["origin_stages"] == ["cleanup"]
            and ax["pipeline_effect"] == "regression",
            "caller_origin_cleanup": len(rows) == 2 and all(
                r["axes"].get("origin_stages") == ["cleanup"]
                for r in rows) and not t_refused,
            "no_learned_asr_alias": not [r for r in rows if r["alias"]],
            "asr_control_still_suggested": ctl,
        }, {"origin": ax["origin_stages"], "rows": [
            (r["source"], r["axes"].get("origin_stages"), r["alias"])
            for r in rows]},
            witness="raw right, applied wrong; mined + taught")


def _axis_callers(w, before, after):
    """Mine an observation and teach the same edit on a twin job."""
    j = w.job(before)
    obs = w.observation(j["job_id"], before, after)
    k = w.job(before)
    t_refused, t_out = _teach(w, k["job_id"], after,
                              _render(w, k["applied_aid"]))
    _mine(w)
    mined = _cands(w, "observation_id=?", (obs,))
    taught = _cands(w, "job_id=?", (k["job_id"],))
    return j, mined, taught, (t_out if t_refused else None)


@drives("LF-M14-C035")
def c035_formatting(entry):
    pairs = (("buy milk eggs bread", "buy:\n- milk\n- eggs\n- bread"),
             ("first point. second point.",
              "first point.\n\nsecond point."))
    conds, obs = {}, {}
    with MWorld() as w:
        for i, (b, a) in enumerate(pairs):
            ax = classify.classify_observation(b, a)
            j, mined, taught, refusal = _axis_callers(w, b, a)
            rows = mined + taught
            conds[f"{i}_classifier_formatting"] = ax["edit_kind"] == \
                "punctuation_or_structure"
            conds[f"{i}_teach_records_formatting"] = len(taught) == 1 and \
                taught[0]["axes"].get("edit_kind") == \
                "punctuation_or_structure"
            conds[f"{i}_not_speech_truth"] = not [
                r for r in rows if r["alias"] or r["axes"].get("edit_kind")
                == "recognition_error"] and _no_review_truth(w, j)
            obs[i] = [(r["source"], r["status"], r["axes"].get(
                "edit_kind")) for r in rows]
        conds["recognition_control"] = _modul_control(w)
    return check(conds, obs, witness="list/paragraph re-rendering;"
                 " classifier + teach + mining callers")


@drives("LF-M14-C036")
def c036_punctuation(entry):
    ax = classify.classify_observation("Wait here.", "Wait here!")
    with MWorld() as w:
        j, mined, taught, refusal = _axis_callers(w, "Wait here.",
                                                  "Wait here!")
        ctl = _modul_control(w)
        return check({
            "classifier_punctuation": ax["edit_kind"]
            == "punctuation_or_structure",
            "teach_keeps_it": refusal is None and len(taught) == 1
            and taught[0]["status"] == "pending"
            and taught[0]["axes"].get("edit_kind")
            == "punctuation_or_structure",
            "miner_keeps_classification": len(mined) == 1
            and mined[0]["axes"].get("edit_kind")
            == "punctuation_or_structure",
            "no_alias": not [r for r in mined + taught if r["alias"]],
            "recognition_control": ctl,
        }, {"teach": refusal or [r["status"] for r in taught],
            "mined": [(r["status"], r["axes"].get("edit_kind"))
                      for r in mined]},
            witness="classifier, teach and miner separately",
            grading="decision", decision="m14-policy-r1:D13")


@drives("LF-M14-C037")
def c037_number_date(entry):
    pairs = (("meet on friday at noon", "meet on monday at noon"),
             ("order 15 units today", "order 50 units today"),
             ("order fifteen units today", "order fifty units today"))
    conds, obs = {}, {}
    with MWorld() as w:
        for i, (b, a) in enumerate(pairs):
            ax = classify.classify_observation(b, a)
            j, mined, taught, refusal = _axis_callers(w, b, a)
            rows = mined + taught
            conds[f"{i}_classifier_changed_intent"] = ax["edit_kind"] == \
                "changed_intent"
            conds[f"{i}_never_asr_gold"] = not [
                r for r in rows if r["alias"] or r["axes"].get("edit_kind")
                == "recognition_error"] and _no_review_truth(w, j)
            conds[f"{i}_qualified_by_evidence"] = all(
                r["axes"].get("evidence_status") in (
                    "explicit_intent_review", "reliable_target_observation")
                for r in rows) and bool(rows)
            obs[i] = [(r["source"], r["status"], r["axes"].get(
                "edit_kind")) for r in rows]
        conds["recognition_control"] = _modul_control(w)
    return check(conds, obs, witness="weekday and numeric value changes,"
                 " including a distance-close number word")


@drives("LF-M14-C038")
def c038_negation(entry):
    pairs = (("please do deploy the build", "please do not deploy the"
              " build"), ("the change is safe now",
                          "the change isn't safe now"))
    conds, obs = {}, {}
    with MWorld() as w:
        for i, (b, a) in enumerate(pairs):
            ax = classify.classify_observation(b, a)
            j, mined, taught, refusal = _axis_callers(w, b, a)
            rows = mined + taught
            conds[f"{i}_classifier_not_recognition"] = ax["edit_kind"] != \
                "recognition_error" and "negation" in ax["domains"]
            conds[f"{i}_no_automatic_suggestion"] = not [
                r for r in rows if r["alias"]]
            obs[i] = [(r["source"], r["status"], r["axes"].get(
                "edit_kind")) for r in rows]
        conds["recognition_control"] = _modul_control(w)
    return check(conds, obs, witness="negation flips via classifier,"
                 " teach and mining")


@drives("LF-M14-C039")
def c039_direction(entry):
    pairs = (("please increase the output level today",
              "please decrease the output level today"),
             ("please enable the backup schedule now",
              "please disable the backup schedule now"))
    conds, obs = {}, {}
    with MWorld() as w:
        for i, (b, a) in enumerate(pairs):
            ax = classify.classify_observation(b, a)
            j, mined, taught, refusal = _axis_callers(w, b, a)
            rows = mined + taught
            conds[f"{i}_classifier_not_recognition"] = ax["edit_kind"] != \
                "recognition_error"
            conds[f"{i}_not_certified"] = not [
                r for r in rows if r["alias"] or r["axes"].get("edit_kind")
                == "recognition_error"]
            obs[i] = [(r["source"], r["status"], r["axes"].get(
                "edit_kind")) for r in rows]
        conds["recognition_control"] = _modul_control(w)
    return check(conds, obs, witness="direction swaps with high"
                 " surrounding overlap")


@drives("LF-M14-C040")
def c040_large_unrelated(entry):
    conds, obs = {}, {}
    rewrite = "the quarterly budget spreadsheet has seventeen columns"
    with MWorld() as w:
        ax = classify.classify_observation(TEACH_RAW, rewrite)
        j, mined, taught, refusal = _axis_callers(w, TEACH_RAW, rewrite)
        conds["rewrite_abstains"] = ax["edit_kind"] == "user_rewrite" \
            and ax["abstained"] and refusal is not None and not taught \
            and all(r["status"] == "dismissed" for r in mined)
        obs["rewrite"] = [r["status"] for r in mined + taught]
        b, a = "send the gamma report today", "send the delta report today"
        ax = classify.classify_observation(b, a)
        j, mined, taught, refusal = _axis_callers(w, b, a)
        conds["unrelated_abstains"] = ax["abstained"] and \
            ax["edit_kind"] != "recognition_error"
        conds["unrelated_no_alias"] = not [r for r in mined + taught
                                           if r["alias"]]
        obs["unrelated"] = [(r["status"], r["axes"].get("edit_kind"))
                            for r in mined + taught]
        ax = classify.classify_observation(TEACH_RAW, TEACH_RAW)
        j, mined, taught, refusal = _axis_callers(w, TEACH_RAW, TEACH_RAW)
        conds["identical_unchanged"] = ax["abstained"] and \
            ax["abstain_reason"] == "unchanged_output" and \
            refusal is not None and not taught and \
            not [r for r in mined if r["status"] == "pending"
                 or r["alias"]]
        obs["identical"] = [r["status"] for r in mined + taught]
        conds["recognition_control"] = _modul_control(w)
    return check(conds, obs, witness="large rewrite, unrelated word"
                 " swap and identical input as separate cases")


# =============================================================================
# stateful probes
# =============================================================================


def _counting_submit(store):
    """Count waited submits the caller makes (the writer-op boundary)."""
    orig = store.submit
    n = {"ops": 0}

    def submit(fn, wait=True, timeout=15.0):
        n["ops"] += 1
        return orig(fn, wait=wait, timeout=timeout)
    return orig, submit, n


@drives("LF-M14-S001")
def s001_teach_while_example_deleted(entry):
    # Positive control: identical fixture, no invalidating action; it
    # also measures how many writer ops a teach takes.
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        orig, counting, n = _counting_submit(w.store)
        shown = _render(w, j["applied_aid"])
        w.store.submit = counting
        try:
            ctl_refused, _ = _teach(w, j["job_id"], TEACH_FIX, shown)
        finally:
            w.store.submit = orig
        teach_ops = n["ops"]
    # Alternate valid order: teach commits, then the deletion.
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        alt_refused, alt = _teach(w, j["job_id"], TEACH_FIX,
                                  _render(w, j["applied_aid"]))
        w.store.delete_everywhere("job", j["job_id"])
        alt_ok = not alt_refused and w.candidate(alt["candidate_id"])[
            "status"] == "stale" and w.payload(alt["candidate_id"]) is None
    # The probe.
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        u = w.job("unrelated bravo dictation stays live")
        shown = _render(w, j["applied_aid"])    # the visible final read
        state = {"fired": False, "counts": None, "where": None}
        orig = w.store.submit

        def delete_now(where):
            state["fired"] = True
            state["where"] = where
            w.store.delete_everywhere("job", j["job_id"])
            state["counts"] = {t: orig(lambda c, t=t: c.execute(
                f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in (
                "learning_candidates", "artifacts", "artifact_leases")}
        if teach_ops <= 1:
            # Read and mint are ONE writer op: the only boundary after
            # the visible read is before that op's admission.
            def submit(fn, wait=True, timeout=15.0):
                if not state["fired"]:
                    delete_now("before_single_teach_op")
                return orig(fn, wait=wait, timeout=timeout)
            w.store.submit = submit
            try:
                was_refused, msg = _teach(w, j["job_id"], TEACH_FIX, shown)
            finally:
                w.store.submit = orig
        else:
            def hook():
                if not state["fired"]:
                    delete_now("between_read_and_mint_ops")
            with after_each_op(w.store, hook):
                was_refused, msg = _teach(w, j["job_id"], TEACH_FIX, shown)
        if not state["fired"]:
            return invalid("deletion seam never reached", state)
        after = {t: w.one(f"SELECT COUNT(*) FROM {t}")[0] for t in (
            "learning_candidates", "artifacts", "artifact_leases")}
        u_live = w.one("SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                       " purged=0", (u["job_id"],))[0]
        u_state = w.one("SELECT state FROM training_examples WHERE"
                        " example_id=?", (u["example_id"],))[0]
        return check({
            "refused": was_refused,
            "no_candidate_artifact_or_lease": after == state["counts"]
            and after["learning_candidates"] == 0,
            "unrelated_job_live": u_live >= 4
            and u_state == "captured_unreviewed",
            "positive_control_taught": not ctl_refused,
            "alternate_order_coherent": alt_ok,
        }, {"teach_ops": teach_ops, "seam": state["where"],
            "refusal": msg if was_refused else None},
            witness=f"m14_s001_authority_boundary at {state['where']}"
                    f" (teach writer ops={teach_ops})",
            reached=entry["barrier"]["name"])


@drives("LF-M14-S002")
def s002_mined_while_artifact_expires(entry):
    def fixture(w):
        j = w.job(TEACH_RAW)
        obs = w.observation(j["job_id"], TEACH_RAW, TEACH_FIX)
        before_aid = w.one("SELECT before_artifact_id FROM"
                           " insertion_observations WHERE"
                           " observation_id=?", (obs,))[0]
        return j, obs, before_aid
    with MWorld() as w:
        _j, obs, _b = fixture(w)
        _mine(w)
        ctl = _cands(w, "observation_id=?", (obs,))
    with MWorld() as w:          # alternate order: miner first
        _j, obs, before_aid = fixture(w)
        _mine(w)
        w.purge(before_aid)
        alt = _cands(w, "observation_id=?", (obs,))
        alt_ok = len(alt) == 1 and alt[0]["status"] == "pending" and \
            w.payload(alt[0]["candidate_id"]) is not None
    with MWorld() as w:
        _j, obs, before_aid = fixture(w)
        state = {"fired": False, "cands": None}

        def hook():
            if state["fired"]:
                return
            state["fired"] = True
            w.purge(before_aid)
            state["cands"] = w.one("SELECT COUNT(*) FROM"
                                   " learning_candidates")[0]
            state["purged"] = bool(w.artifact_row(before_aid)[2])
        with after_each_op(w.store, hook):
            _mine(w)
        if not state["fired"] or state["cands"] != 0 or \
                not state.get("purged"):
            return invalid("purge did not commit before the miner's"
                           " writer op", state)
        rows = _cands(w, "observation_id=?", (obs,))
        return check({
            "no_candidate_from_expired_input": not [
                r for r in rows if r["status"] in ("pending", "suppressed")
                or r["alias"]],
            "no_payload_minted": w.one(
                "SELECT COUNT(*) FROM artifacts WHERE role="
                "'candidate_observation'")[0] == 0,
            "positive_control_mined": len(ctl) == 1
            and ctl[0]["status"] == "pending",
            "miner_first_order_coherent": alt_ok,
        }, {"rows": [(r["status"], r["axes"].get("abstain_reason"))
                     for r in rows]},
            witness="m14_s002_authority_boundary: purge committed via the"
                    " store retention primitive after the scan op",
            reached=entry["barrier"]["name"], grading="decision",
            decision="m14-policy-r1:D11")


@drives("LF-M14-S003")
def s003_two_concurrent_miners(entry):
    with MWorld() as w:         # serial control (and alternate order)
        j = w.job(TEACH_RAW)
        obs = w.observation(j["job_id"], TEACH_RAW, TEACH_FIX)
        _mine(w)
        _mine(w)
        ctl = _cands(w, "observation_id=?", (obs,))
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        obs = w.observation(j["job_id"], TEACH_RAW, TEACH_FIX)
        barrier = threading.Barrier(2, timeout=20)
        orig = w.store.submit
        local = threading.local()
        state = {"arrived": 0, "broken": False}
        lock = threading.Lock()

        def submit(fn, wait=True, timeout=15.0):
            out = orig(fn, wait=wait, timeout=timeout)
            if getattr(local, "armed", False) and \
                    not getattr(local, "passed", False):
                local.passed = True
                # Caller thread, between writer ops: both scans have
                # committed before either miner submits its mint op.
                try:
                    barrier.wait()
                    with lock:
                        state["arrived"] += 1
                except threading.BrokenBarrierError:
                    state["broken"] = True
            return out
        results, errors = [], []

        def miner():
            local.armed = True
            try:
                results.append(w.learning.mine_observation_candidates())
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {e}")
        w.store.submit = submit
        try:
            threads = [threading.Thread(target=miner) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        finally:
            w.store.submit = orig
        if state["broken"] or state["arrived"] != 2:
            return invalid("both miners never reached the barrier", state)
        rows = _cands(w, "observation_id=?", (obs,))
        pays = [r[0] for r in w.rows(
            "SELECT artifact_id FROM artifacts WHERE role="
            "'candidate_observation' AND job_id=?", (j["job_id"],))]
        leases = w.one("SELECT COUNT(*) FROM artifact_leases WHERE"
                       " artifact_id IN (SELECT artifact_id FROM artifacts"
                       " WHERE role='candidate_observation')")[0]
        return check({
            "no_miner_error": not errors,
            "exactly_one_logical_candidate": len(rows) == 1
            and sorted(results) == [0, 1],
            "no_duplicate_payload_or_lease": len(pays) == 1 and leases == 1,
            "serial_control_one": len(ctl) == 1
            and ctl[0]["status"] == "pending",
        }, {"results": sorted(results), "rows": len(rows),
            "payloads": len(pays), "leases": leases},
            witness="m14_s003_authority_boundary: threading.Barrier(2) in"
                    " the caller threads after both scan ops",
            reached=entry["barrier"]["name"])


def _pair_obs(w, raw, fixed, app=APP):
    j = w.job(raw, app=app)
    return j, w.observation(j["job_id"], raw, fixed)


@drives("LF-M14-S004")
def s004_reject_then_identical(entry):
    extras = ((TEACH_RAW, TEACH_FIX, APP),
              (TEACH_RAW, TEACH_FIX, "com.synthetic.other"),
              ("please check the Modul today", TEACH_FIX, APP))

    def run(reject):
        with MWorld() as w:
            _j, obs0 = _pair_obs(w, TEACH_RAW, TEACH_FIX)
            _mine(w)
            c0 = _cands(w, "observation_id=?", (obs0,))[0]
            if reject:
                w.learning.reject(c0["candidate_id"])
            committed = _cands(w, "observation_id=?", (obs0,))[0]["status"]
            new = [_pair_obs(w, *e)[1] for e in extras]
            _o1 = _pair_obs(w, TEACH_RAW, "please check the modal today")[1]
            _o2 = _pair_obs(w, "send the cloud report on friday",
                            "send the Claude report on friday")[1]
            _mine(w)
            rows = _cands(w, f"observation_id IN ({','.join('?' * 3)})",
                          tuple(new))
            others = _cands(w, "observation_id IN (?,?)", (_o1, _o2))
            return committed, rows, others
    committed, rows, others = run(True)
    c_committed, c_rows, _c_others = run(False)
    return check({
        "rejection_committed_first": committed == "rejected",
        "no_pending_reappearance": len(rows) == 3
        and all(r["status"] == "suppressed" for r in rows),
        "different_canonical_and_alias_not_suppressed": len(others) == 2
        and all(r["status"] == "pending" and r["alias"] for r in others),
        "positive_control_pending_without_rejection":
            c_committed == "pending" and len(c_rows) == 3
            and all(r["status"] == "pending" for r in c_rows),
    }, {"after_reject": [r["status"] for r in rows],
        "no_reject": [r["status"] for r in c_rows],
        "others": [(r["alias"], r["canonical"], r["status"])
                   for r in others]},
        witness="m14_s004_authority_boundary: exact-pair observations"
                " recorded and mined after the rejection commits (same"
                " app, another app, alias case variant)",
        reached=entry["barrier"]["name"], grading="decision",
        decision="m14-policy-r1:D05")


@drives("LF-M14-S011")
def s011_note_a_edited_among_ab(entry):
    return _ab_edit(entry, True, witness="m14_s011_authority_boundary:"
                    " A+B spans/links verified persisted by SQL, then"
                    " A-only edit and mine (control: C018 B-only shape)",
                    reached=entry["barrier"]["name"])


@drives("LF-M14-S012")
def s012_note_edit_crosses_ab(entry):
    return _ab_cross(entry, witness="m14_s012_authority_boundary: A+B"
                     " spans/links verified persisted, then one"
                     " cross-boundary edit and mine",
                     reached=entry["barrier"]["name"])


@drives("LF-M14-S033")
def s033_reviewed_artifact_unpinned(entry):
    def run(unpin):
        with MWorld() as w:
            j = w.job(TEACH_RAW)
            _r, out = _teach(w, j["job_id"], TEACH_FIX,
                             _render(w, j["applied_aid"]))
            if _r:
                return None
            pay = w.candidate(out["candidate_id"])["payload_aid"]
            reviewed_lease = _forever(w, pay)       # the barrier
            m, _o, mc = _mined(w, "send the cloud report on friday",
                               "send the Claude report on friday")
            pin_effect = []
            for x in (j, m):
                w.training.pin(x["example_id"], True)
                pin_effect.append(_forever(w, x["raw_aid"]))
                if unpin:
                    w.training.pin(x["example_id"], False)
            w.clock.advance_days(90)
            w.store.prune_training(now=w.clock())
            w.store.prune(now=w.clock())
            marks = ",".join("?" * len(_REVIEW_ROLES))
            unreviewed_forever = w.one(
                "SELECT COUNT(*) FROM artifact_leases l JOIN artifacts a"
                " ON a.artifact_id=l.artifact_id WHERE l.expires_at_utc IS"
                " NULL AND l.revoked_at_utc IS NULL AND (a.role NOT IN"
                f" ({marks}) OR a.artifact_id=?)",
                (*_REVIEW_ROLES, mc["payload_aid"] if mc else ""))[0]
            return {"reviewed_lease_before": reviewed_lease,
                    "reviewed_lease_after": _forever(w, pay),
                    "payload_live": not w.artifact_row(pay)[2],
                    "pin_effect": pin_effect,
                    "unreviewed_forever": unreviewed_forever,
                    "machine_forever": _forever(w, mc["payload_aid"])
                    if mc else None,
                    "example_state": w.one(
                        "SELECT state FROM training_examples WHERE"
                        " example_id=?", (j["example_id"],))[0]}
    probe = run(True)
    ctl = run(False)
    if probe is None or ctl is None or probe["reviewed_lease_before"] != 1:
        return invalid("reviewed lease never existed", probe)
    return check({
        "pin_ran": probe["pin_effect"] == [1, 1],
        "review_lease_survives": probe["reviewed_lease_after"] == 1
        and probe["payload_live"],
        "no_unreviewed_permanent_lease": probe["unreviewed_forever"] == 0
        and probe["machine_forever"] == 0,
        "pinned_control_keeps_review_lease":
            ctl["reviewed_lease_after"] == 1,
    }, {"probe": probe, "control_unreviewed_forever":
        ctl["unreviewed_forever"]},
        witness="m14_s033_authority_boundary: forever review lease"
                " observed, then pin/unpin, clock +90d, retention",
        reached=entry["barrier"]["name"], grading="decision",
        decision="m14-policy-r1:D08")


# =============================================================================
# metamorphic relation
# =============================================================================


@drives("LF-M14-MR003")
def mr003_rejection_stability(entry):
    series = {}
    control = {}
    for k in (1, 3, 5):
        with MWorld() as w:
            _j, obs0 = _pair_obs(w, TEACH_RAW, TEACH_FIX)
            _mine(w)
            w.learning.reject(_cands(w, "observation_id=?",
                                     (obs0,))[0]["candidate_id"])
            apps = (APP, "com.synthetic.other")
            new = [_pair_obs(w, TEACH_RAW if i % 2 == 0 else
                             "please check the MODUL today", TEACH_FIX,
                             apps[i % 2])[1] for i in range(k)]
            ctl = _pair_obs(w, TEACH_RAW, "please check the modal today")[1]
            _mine(w)
            rows = _cands(w, f"observation_id IN ({','.join('?' * k)})",
                          tuple(new))
            series[k] = {"pending": sum(r["status"] == "pending"
                                        for r in rows),
                         "suppressed": sum(r["status"] == "suppressed"
                                           for r in rows)}
            c = _cands(w, "observation_id=?", (ctl,))
            control[k] = bool(c) and c[0]["status"] == "pending"
    return check({
        "pending_stays_zero": all(v["pending"] == 0
                                  for v in series.values()),
        "every_occurrence_recorded_suppressed": all(
            series[k]["suppressed"] == k for k in series),
        "different_canonical_control_pending": all(control.values()),
    }, series, witness="k=1,3,5 repeated exact/case-variant occurrences"
                       " across two app scopes after one rejection",
        grading="decision", decision="m14-policy-r1:D05")
