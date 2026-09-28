"""M14 corpus drivers, group b: human labels, the ASR gate, artifact
ownership and partial grafts.

Binds the frozen corpus entries (tests/v2/personalization/
m14_audit_corpus.json):

- cases LF-M14-C041..C048 (human_labels), C049..C056 (asr_gate),
  C057..C064 (artifact_ownership), C065..C072 (partial_grafts);
- stateful probes LF-M14-S008 (ambiguous label resolved later), S009
  (ASR foreign audio reference), S010 (cleanup foreign/wrong-role
  reference), S013 (deletion while a review form is open — the
  service-level stale action only; the native window half is graded by
  the owned-window suite);
- metamorphic relation LF-M14-MR005 (review resolution).

Policy-dependent entries are graded under m14-policy-r1 D01 (one
effective judgment; changed_intent permanent). Every expectation is a
literal the driver authored, a raw SQL row, file bytes or a count the
driver established while building the fixture — never the production
function under test. Protocol: m14_drivers_common.py.
"""

from __future__ import annotations

import hashlib
import json

from m14_drivers_common import check, drives, invalid
from m14_world import (A_CANARY, B_CANARY, PRIVATE_CANARY, MWorld,
                       accepts, after_each_op, patched, sha256_file,
                       wav_frames)

D01 = "m14-policy-r1:D01"
TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"
GRAFT_RAW = "send the cloud report on friday"


# ---- helpers (independent side: SQL, literals, file bytes) ----------------


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _refused(fn, *a, **kw):
    try:
        return False, fn(*a, **kw)
    except Exception as e:  # noqa: BLE001 — any typed refusal
        return True, f"{type(e).__name__}: {str(e)[:80]}"


def _label(w, ex, kind, **kw):
    return w.review.record_label(ex, edit_kind=kind, **kw)


def _gate(w, ex):
    return w.review.verified_asr_eligible(ex)


def _te(w):
    return w.training.readiness()["readiness_metrics"]["task_eligibility"]


def _label_rows(w, ex):
    return w.rows("SELECT label_id, revision, edit_kind, abstained,"
                  " graft_artifact_id FROM correction_labels WHERE"
                  " example_id=? ORDER BY rowid", (ex,))


def _count(w, sql, args=()):
    return w.one(sql, args)[0]


def _export(w, views, dest="ds", fillers=10):
    """Filler families (no verbatim, no mark — never in any view), a
    split assignment and one export. Returns a dict of what was
    published (records, manifest) or the refusal."""
    from test_m14_remediation import export_or_refusal, export_records
    if fillers:
        w.families(fillers)
    w.splits.assign()
    out, err = export_or_refusal(w, dest, views)
    res = {"out": out, "err": err, "ex": [], "refs": [], "prefs": [],
           "manifest": {}, "root": w.tmp / dest}
    if out is not None:
        res["ex"], res["refs"], res["prefs"] = export_records(w, dest)
        res["manifest"] = json.loads(
            (w.tmp / dest / "dataset_manifest.json").read_text())
    return res


def _ids(res, kind):
    return {e.get("example_id") for e in res["ex"]
            if e.get("task_kind") == kind}


def _excl(res):
    out = {}
    for r in res["manifest"].get("excluded") or []:
        out.setdefault(r.get("example_id"), []).append(r.get("reason"))
    return out


def _recs(res, ex, kind=None):
    return [e for e in res["ex"] if e.get("example_id") == ex
            and (kind is None or e.get("task_kind") == kind)]


def _refs(res, ex, kind=None):
    return [r for r in res["refs"] if r.get("example_id") == ex
            and (kind is None or r.get("task_kind") == kind)]


def _lid(receipt):
    if isinstance(receipt, dict):
        return receipt.get("label_id")
    return receipt


def _span(src, word, after, start=None):
    s = src.index(word) if start is None else start
    return {"start": s, "end": s + len(word), "before_words": [word],
            "after_words": [after]}


def _src_kw(w, aid, text):
    fn = w.review.record_label
    if accepts(fn, "expected_source_artifact_id"):
        return {"expected_source_artifact_id": aid,
                "expected_source_sha256": _sha(text)}
    return {}


def _graft_payload(w, ex):
    row = w.one("SELECT graft_artifact_id FROM correction_labels WHERE"
                " example_id=? AND graft_artifact_id IS NOT NULL ORDER BY"
                " revision DESC LIMIT 1", (ex,))
    if not row:
        return None, None, None
    art = w.artifact_row(row[0])
    return row[0], (json.loads(art[3]) if art and art[3] else None), art


def _grafts(w, job_id=None):
    if job_id:
        return _count(w, "SELECT COUNT(*) FROM artifacts WHERE"
                         " role='span_graft' AND job_id=?", (job_id,))
    return _count(w, "SELECT COUNT(*) FROM artifacts WHERE"
                     " role='span_graft'")


def _set_env(w, ex, slot, aid):
    w.rewrite_envelope(ex, lambda env: env["artifact_ids"].__setitem__(
        slot, aid))


def _origin(w, cid):
    c = w.candidate(cid)
    cls = json.loads(c["classification"] or "{}") if c else {}
    return cls.get("origin_stages")


def _stage_texts(w, example_id, job_id):
    from localflow.v2.curation import review
    fn = review.stage_texts_for
    if accepts(fn, "job_id"):
        return w.store.submit(lambda c: fn(c, example_id, job_id))
    return w.store.submit(lambda c: fn(c, example_id))


def _queue_labeled(w, cid):
    row = next((r for r in w.review.queue()
                if r.get("candidate_id") == cid), None)
    return None if row is None else row.get("labeled")


# =============================================================================
# human_labels — C041..C048
# =============================================================================


@drives("LF-M14-C041")
def c041_label_revisions_append(entry):
    with MWorld() as w:
        ex = w.job("label history target words")["example_id"]
        r1 = _label(w, ex, "recognition_error", origin_stages=("asr",))
        row1 = w.one("SELECT * FROM correction_labels WHERE example_id=?"
                     " AND revision=1", (ex,))
        r2 = _label(w, ex, "representation_error",
                    origin_stages=("normalization",))
        row1_after = w.one("SELECT * FROM correction_labels WHERE"
                           " example_id=? AND revision=1", (ex,))
        rows = _label_rows(w, ex)
        obs = {"revisions": [r[1] for r in rows],
               "kinds": [r[2] for r in rows]}
        return check({
            "two_rows": len(rows) == 2,
            "revisions_1_2": obs["revisions"] == [1, 2],
            "distinct_label_ids": len({r[0] for r in rows}) == 2,
            "kinds_in_save_order": obs["kinds"] == [
                "recognition_error", "representation_error"],
            "rev1_row_not_overwritten": row1 is not None
            and row1 == row1_after,
            "receipts_name_rows": _lid(r1) == rows[0][0]
            and _lid(r2) == rows[1][0],
        }, obs, witness="ReviewService.record_label twice; raw"
                        " correction_labels rows before/after rev2")


@drives("LF-M14-C042")
def c042_ambiguous_resolved(entry):
    with MWorld() as w:
        a = w.ready_asr("ambiguous then resolved")["example_id"]
        ctrl = w.ready_asr("ambiguous never resolved")["example_id"]
        _label(w, a, "ambiguous")
        _label(w, ctrl, "ambiguous")
        g1 = _gate(w, a)
        _label(w, a, "recognition_error", origin_stages=("asr",))
        g2, gc = _gate(w, a), _gate(w, ctrl)
        res = _export(w, ("asr_supervised",))
        te = _te(w)
        rec = _recs(res, a, "asr_supervised")
        obs = {"g1": g1, "g2": g2, "ctrl": gc, "err": res["err"],
               "asr": len(_ids(res, "asr_supervised")),
               "ready": te["asr_supervised"]["count"]}
        return check({
            "rev1_blocks": not g1["eligible"]
            and "ambiguous" in str(g1["reason"]),
            "rev2_resolves": g2["eligible"] is True,
            "unresolved_twin_blocked": not gc["eligible"],
            "export_admits_only_resolved": _ids(res, "asr_supervised")
            == {a},
            "export_effective_revision_2": bool(rec) and rec[0].get(
                "effective_label_revision") == 2,
            "readiness_agrees": te["asr_supervised"]["count"] == 1,
            "history_kept": [r[2] for r in _label_rows(w, a)] == [
                "ambiguous", "recognition_error"],
        }, obs, grading="decision", decision=D01,
            witness="rev1 ambiguous -> gate blocked; rev2 explicit"
                    " recognition -> gate/export/readiness admit (D01)")


@drives("LF-M14-C043")
def c043_rewrite_resolved(entry):
    with MWorld() as w:
        ids_ = {}
        plans = {"resolved": ("user_rewrite", "recognition_error"),
                 "abstained_after": ("user_rewrite", None),
                 "rewrite_latest": ("recognition_error", "user_rewrite"),
                 "rewrite_only": ("user_rewrite",)}
        for name, kinds in plans.items():
            ex = w.ready_asr(f"rewrite {name} words")["example_id"]
            for k in kinds:
                if k is None:
                    _label(w, ex, "unknown", abstained=True)
                else:
                    _label(w, ex, k)
            ids_[name] = ex
        gates = {n: _gate(w, ex) for n, ex in ids_.items()}
        res = _export(w, ("asr_supervised",))
        te = _te(w)
        obs = {n: (g["eligible"], g["reason"]) for n, g in gates.items()}
        obs["ready"] = te["asr_supervised"]["count"]
        return check({
            "explicit_resolution_clears": gates["resolved"]["eligible"]
            is True,
            "abstention_never_resolves": not gates["abstained_after"][
                "eligible"],
            "latest_rewrite_blocks": not gates["rewrite_latest"][
                "eligible"],
            "unresolved_rewrite_blocks": not gates["rewrite_only"][
                "eligible"],
            "export_matches": _ids(res, "asr_supervised")
            == {ids_["resolved"]},
            "readiness_matches": te["asr_supervised"]["count"] == 1,
        }, obs, grading="decision", decision=D01,
            witness="user_rewrite resolved by a later non-abstained"
                    " non-blocking judgment only; not latest-only (an"
                    " abstained latest keeps it blocked), not permanent")


@drives("LF-M14-C044")
def c044_changed_intent_history(entry):
    with MWorld() as w:
        a = w.ready_asr("changed intent history")["example_id"]
        ctrl = w.ready_asr("recognition history twin")["example_id"]
        _label(w, a, "changed_intent", origin_stages=("user_intent",))
        _label(w, a, "recognition_error", origin_stages=("asr",))
        _label(w, ctrl, "recognition_error", origin_stages=("asr",))
        _label(w, ctrl, "recognition_error", origin_stages=("asr",))
        ga, gc = _gate(w, a), _gate(w, ctrl)
        res = _export(w, ("asr_supervised",))
        te = _te(w)
        rows = _label_rows(w, a)
        obs = {"a": ga, "ctrl": gc, "rows": [r[2] for r in rows],
               "ready": te["asr_supervised"]["count"]}
        return check({
            "changed_intent_still_blocks": not ga["eligible"]
            and "changed_intent" in str(ga["reason"]),
            "twin_without_it_eligible": gc["eligible"] is True,
            "export_excludes_blocked": _ids(res, "asr_supervised")
            == {ctrl},
            "readiness_agrees": te["asr_supervised"]["count"] == 1,
            "history_never_cleared": [r[2] for r in rows] == [
                "changed_intent", "recognition_error"],
        }, obs, witness="rev1 changed_intent + rev2 recognition: gate,"
                        " export and readiness keep the permanent block")


@drives("LF-M14-C045")
def c045_abstain_then_explicit(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        ex = j["example_id"]
        cid = w.learning.teach_correction(j["job_id"], TEACH_FIX)[
            "candidate_id"]
        w.verbatim(ex, j["raw"])
        _label(w, ex, "ambiguous", abstained=True)
        q1, g1 = _queue_labeled(w, cid), _gate(w, ex)
        _label(w, ex, "recognition_error", origin_stages=("asr",))
        q2, g2 = _queue_labeled(w, cid), _gate(w, ex)
        res = _export(w, ("asr_supervised",))
        rec = _recs(res, ex, "asr_supervised")
        obs = {"q1": q1, "q2": q2, "g1": g1, "g2": g2}
        if q1 is None or q2 is None:
            return invalid("queue row for the taught candidate absent",
                           obs)
        return check({
            "abstained_first_is_unresolved": q1 is False,
            "abstained_blocker_blocks": not g1["eligible"],
            "explicit_second_is_labeled": q2 is True,
            "explicit_second_resolves": g2["eligible"] is True,
            "export_uses_rev2": bool(rec) and rec[0].get(
                "effective_label_revision") == 2,
        }, obs, witness="queue 'labeled' and ASR gate read the latest"
                        " non-abstained revision (D01 effective judgment)")


@drives("LF-M14-C046")
def c046_explicit_then_abstain(entry):
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        ex = j["example_id"]
        cid = w.learning.teach_correction(j["job_id"], TEACH_FIX)[
            "candidate_id"]
        w.verbatim(ex, j["raw"])
        _label(w, ex, "ambiguous")
        _label(w, ex, "recognition_error", origin_stages=("asr",))
        q_mid, g_mid = _queue_labeled(w, cid), _gate(w, ex)
        _label(w, ex, "unknown", abstained=True)
        q_end, g_end = _queue_labeled(w, cid), _gate(w, ex)
        res = _export(w, ("asr_supervised",))
        obs = {"q_mid": q_mid, "g_mid": g_mid, "q_end": q_end,
               "g_end": g_end, "excluded": _excl(res).get(ex)}
        if q_mid is None or q_end is None:
            return invalid("queue row for the taught candidate absent",
                           obs)
        return check({
            "control_resolved_before_abstain": q_mid is True
            and g_mid["eligible"] is True,
            "latest_abstain_is_unresolved": q_end is False,
            "old_explicit_row_not_used_for_gate": not g_end["eligible"],
            "export_excludes": ex not in _ids(res, "asr_supervised"),
        }, obs, witness="rev3 abstained after explicit rev2: queue and"
                        " gate fall back to unresolved, never rev2")


@drives("LF-M14-C047")
def c047_restricted_save(entry):
    with MWorld() as w:
        def restrict(st, ex):
            if st == "deleted":
                w.training.delete_everywhere(ex)
            elif st == "excluded":
                w.training.exclude(ex, True)
            else:
                w.set_state(ex, st)

        results = {}
        reached = 0
        for st in ("expired", "excluded", "quarantined_sensitive",
                   "deleted", None):
            ex = w.job(f"restricted save {st} words")["example_id"]
            fired = []

            def hook(st=st, ex=ex, fired=fired):
                if fired or st is None:
                    return
                fired.append(1)
                restrict(st, ex)
            with after_each_op(w.store, hook):
                rendered = w.training.example_detail(ex)
            reached += len(fired)
            was_refused, _ = _refused(_label, w, ex, "recognition_error")
            state = w.one("SELECT state FROM training_examples WHERE"
                          " example_id=?", (ex,))[0]
            results[st or "live_control"] = {
                "rendered": rendered is not None,
                "refused": was_refused,
                "labels": _count(w, "SELECT COUNT(*) FROM"
                                    " correction_labels WHERE"
                                    " example_id=?", (ex,)),
                "state": state}
        if reached != 4:
            return invalid("render->restrict seam not reached", results)
        conds = {}
        for st in ("expired", "excluded", "quarantined_sensitive",
                   "deleted"):
            r = results[st]
            conds[f"{st}_refused"] = r["refused"]
            conds[f"{st}_no_label"] = r["labels"] == 0
            conds[f"{st}_state_kept"] = r["state"] == st
        c = results["live_control"]
        conds["control_saved"] = (not c["refused"] and c["labels"] == 1
                                  and c["state"] == "annotated")
        return check(conds, results,
                     witness="state restricted between example_detail"
                             " (render) and record_label (save) via"
                             " after_each_op")


@drives("LF-M14-C048")
def c048_retry_same_action(entry):
    with MWorld() as w:
        ex = w.job("label retry unknown outcome")["example_id"]
        fn = w.review.record_label
        kw = {"operation_id": "op-b-label-retry"} \
            if accepts(fn, "operation_id") else {}
        state = {"n": 0}

        def factory(orig):
            def submit(op, wait=True, timeout=15.0):
                out = orig(op, wait=wait, timeout=timeout)
                state["n"] += 1
                if state["n"] == 1:
                    # The op committed; the caller never heard back.
                    raise TimeoutError("synthetic unknown outcome")
                return out
            return submit
        with patched(w.store, "submit", factory):
            first_refused, _ = _refused(_label, w, ex,
                                        "recognition_error", **kw)
        committed = _count(w, "SELECT COUNT(*) FROM correction_labels"
                              " WHERE example_id=?", (ex,))
        retry_refused, r2 = _refused(_label, w, ex, "recognition_error",
                                     **kw)
        rows = _label_rows(w, ex)
        after_retry = len(rows)
        other = {"operation_id": "op-b-label-other"} if kw else {}
        _label(w, ex, "representation_error", **other)
        after_other = _count(w, "SELECT COUNT(*) FROM correction_labels"
                                " WHERE example_id=?", (ex,))
        obs = {"first_unknown": first_refused, "committed": committed,
               "retry_refused": retry_refused, "after_retry": after_retry,
               "after_other": after_other,
               "operation_id_supported": bool(kw)}
        if not first_refused or committed != 1:
            return invalid("unknown-outcome seam not reached", obs)
        return check({
            "one_logical_revision": after_retry == 1,
            "retry_returns_recorded_receipt": not retry_refused
            and bool(rows) and _lid(r2) == rows[0][0],
            "distinct_action_still_appends": after_other == 2,
        }, obs, witness="Store.submit patched: op commits then caller"
                        " sees TimeoutError; retry with the same"
                        " operation_id")


# =============================================================================
# asr_gate — C049..C056
# =============================================================================


def _store_frames(w, aid):
    path = w.artifact_row(aid)[4]
    return wav_frames(w.store.artifacts_dir / path)


@drives("LF-M14-C049")
def c049_positive_full(entry):
    with MWorld() as w:
        a = w.ready_asr(f"positive full witness {A_CANARY}", freq=330.0)
        ex = a["example_id"]
        g = _gate(w, ex)
        own = w.artifact_row(a["audio_aid"])
        res = _export(w, ("asr_supervised",))
        te = _te(w)
        recs = _recs(res, ex)
        refs = _refs(res, ex, "asr_supervised")
        exp_file = res["root"] / recs[0]["audio"] if recs and recs[0].get(
            "audio") else None
        obs = {"gate": g, "records": len(recs), "refs": len(refs),
               "err": res["err"], "ready": te["asr_supervised"]["count"]}
        return check({
            "gate_true": g["eligible"] is True,
            "one_asr_record": len(recs) == 1
            and recs[0].get("task_kind") == "asr_supervised",
            "own_audio_bytes": exp_file is not None and exp_file.is_file()
            and wav_frames(exp_file) == _store_frames(w, a["audio_aid"]),
            "own_audio_digest": exp_file is not None
            and sha256_file(exp_file) == own[5],
            "exact_reference": len(refs) == 1
            and refs[0].get("text") == a["raw"]
            and refs[0].get("coverage") == "full",
            "readiness_one": te["asr_supervised"]["count"] == 1,
        }, obs, witness="ready_asr (own audio + listened verbatim) ->"
                        " gate, export file bytes vs store WAV frames")


@drives("LF-M14-C050")
def c050_no_listen(entry):
    with MWorld() as w:
        a = w.job("unlistened verbatim alpha")
        b = w.job("unlistened verbatim bravo")
        c = w.job("string listened verbatim charlie")
        ctrl = w.ready_asr("listened control words")["example_id"]
        refused_api, _ = _refused(w.training.set_verbatim,
                                  a["example_id"], a["raw"],
                                  listened_audio=False)
        a_refs = _count(w, "SELECT COUNT(*) FROM artifacts WHERE"
                           " role='verbatim_reference' AND job_id=?",
                        (a["job_id"],))
        for j, flag in ((b, False), (c, "true")):
            aid = w.text_artifact(j["job_id"], "verbatim_reference",
                                  j["raw"])

            def add(env, aid=aid, flag=flag, text=j["raw"]):
                env.setdefault("annotations", []).append({
                    "annotation_id": f"ann-b-{aid[-6:]}",
                    "kind": "verbatim_reference", "coverage": "full",
                    "listened_audio": flag, "artifact_id": aid,
                    "text_sha256": _sha(text), "source": "hub_manual"})
            w.rewrite_envelope(j["example_id"], add)
        gb, gc, gk = (_gate(w, b["example_id"]), _gate(w, c["example_id"]),
                      _gate(w, ctrl))
        res = _export(w, ("asr_supervised",))
        te = _te(w)
        obs = {"api_refused": refused_api, "b": gb, "c": gc, "ctrl": gk,
               "ready": te["asr_supervised"]["count"]}
        return check({
            "api_refuses_without_listen": refused_api and a_refs == 0,
            "listened_false_ineligible": not gb["eligible"],
            "listened_string_ineligible": not gc["eligible"],
            "control_eligible": gk["eligible"] is True,
            "export_only_control": _ids(res, "asr_supervised") == {ctrl},
            "readiness_only_control": te["asr_supervised"]["count"] == 1,
        }, obs, witness="set_verbatim(listened_audio=False) and envelope"
                        " annotations without listened_audio is True")


@drives("LF-M14-C051")
def c051_audio_missing_purged(entry):
    obs = {}
    with MWorld() as w:
        a = w.ready_asr("purged audio alpha")
        b = w.ready_asr("purged audio control")
        w.purge(a["audio_aid"])
        purged = w.artifact_row(a["audio_aid"])[2]
        ga, gb = _gate(w, a["example_id"]), _gate(w, b["example_id"])
        res = _export(w, ("asr_supervised",))
        te = _te(w)["asr_supervised"]
        reasons = _excl(res).get(a["example_id"]) or []
        obs["purged"] = {"a": ga, "b": gb, "excluded": reasons,
                         "ready": te["count"], "ready_excl": te["excluded"]}
        conds = {
            "purged_row": purged == 1,
            "purged_gate_false": not ga["eligible"]
            and "purged" in str(ga["reason"]),
            "purged_no_asr_row": a["example_id"] not in _ids(
                res, "asr_supervised"),
            "purged_clear_reason": any("purged" in str(r)
                                       for r in reasons),
            "control_exported": _ids(res, "asr_supervised")
            == {b["example_id"]},
            "readiness_reason": te["count"] == 1 and any(
                "purged" in k for k in te["excluded"]),
        }
    with MWorld() as w:
        a = w.ready_asr("removed file alpha")
        b = w.ready_asr("removed file control")
        path = w.store.artifacts_dir / w.artifact_row(a["audio_aid"])[4]
        path.unlink()
        ga = _gate(w, a["example_id"])
        res = _export(w, ("asr_supervised",))
        a_rows = a["example_id"] in _ids(res, "asr_supervised")
        obs["file_removed"] = {"a": ga, "err": res["err"],
                               "a_row": a_rows,
                               "ready": _te(w)["asr_supervised"]["count"],
                               "b_published": b["example_id"] in _ids(
                                   res, "asr_supervised"),
                               "excluded": _excl(res).get(
                                   a["example_id"])}
        conds["file_removed_no_asr_row"] = not a_rows
        conds["file_removed_reason_named"] = (
            (res["err"] is not None and a["audio_aid"] in res["err"])
            or bool(_excl(res).get(a["example_id"])))
    return check(conds, obs,
                 witness="store purge path (row purged) and an unlinked"
                         " managed WAV under a live row")


@drives("LF-M14-C052")
def c052_graft_only(entry):
    with MWorld() as w:
        j = w.job(GRAFT_RAW)
        ex = j["example_id"]
        _label(w, ex, "recognition_error", origin_stages=("asr",),
               confirmed_spans=[_span(GRAFT_RAW, "cloud", "Claude")],
               **_src_kw(w, j["raw_aid"], GRAFT_RAW))
        ctrl = w.ready_asr("graft only control")["example_id"]
        g, gk = _gate(w, ex), _gate(w, ctrl)
        res = _export(w, ("asr_supervised", "asr_span_graft_weak"))
        te = _te(w)
        weak = _refs(res, ex, "asr_span_graft_weak")
        obs = {"gate": g, "ctrl": gk, "weak": len(weak), "err": res["err"]}
        return check({
            "graft_not_full_asr": not g["eligible"],
            "control_full_asr": gk["eligible"] is True,
            "asr_view_only_control": _ids(res, "asr_supervised") == {ctrl},
            "weak_view_admits_graft": len(weak) == 1
            and weak[0].get("coverage") == "partial",
            "readiness_only_control": te["asr_supervised"]["count"] == 1,
        }, obs, witness="record_label(confirmed_spans) without verbatim:"
                        " gate false; weak view carries the graft")


@drives("LF-M14-C053")
def c053_foreign_audio(entry):
    with MWorld() as w:
        a = w.ready_asr(f"foreign audio alpha {A_CANARY}", freq=300.0)
        b = w.ready_asr(f"foreign audio bravo {B_CANARY}", freq=700.0)
        pre = _gate(w, a["example_id"])
        b_row = w.artifact_row(b["audio_aid"])
        b_revs = _count(w, "SELECT COUNT(*) FROM training_revisions WHERE"
                           " example_id=?", (b["example_id"],))
        _set_env(w, a["example_id"], "original_audio", b["audio_aid"])
        ga, gb = _gate(w, a["example_id"]), _gate(w, b["example_id"])
        res = _export(w, ("asr_supervised",))
        b_frames = _store_frames(w, b["audio_aid"])
        a_carries_b = any(
            e.get("audio") and wav_frames(res["root"] / e["audio"])
            == b_frames for e in _recs(res, a["example_id"]))
        b_recs = _recs(res, b["example_id"], "asr_supervised")
        obs = {"pre": pre, "a": ga, "b": gb, "err": res["err"]}
        if not pre["eligible"]:
            return invalid("A's own-audio positive never established", obs)
        return check({
            "a_ineligible": not ga["eligible"],
            "a_not_exported": a["example_id"] not in _ids(
                res, "asr_supervised"),
            "no_b_bytes_as_a": not a_carries_b,
            "b_eligible_and_exported": gb["eligible"] is True
            and len(b_recs) == 1,
            "b_exports_own_bytes": bool(b_recs) and wav_frames(
                res["root"] / b_recs[0]["audio"]) == b_frames,
            "b_row_unchanged": w.artifact_row(b["audio_aid"]) == b_row,
            "b_revisions_unchanged": _count(
                w, "SELECT COUNT(*) FROM training_revisions WHERE"
                   " example_id=?", (b["example_id"],)) == b_revs,
        }, obs, witness="A envelope original_audio -> B's valid"
                        " original_audio artifact")


@drives("LF-M14-C054")
def c054_wrong_role_audio(entry):
    from m14_world import RATE, tone
    with MWorld() as w:
        a = w.ready_asr("wrong role audio alpha")
        ctrl = w.ready_asr("wrong role control")["example_id"]
        other = w.store.write_audio_artifact(
            job_id=a["job_id"], stage="capture", samples=tone(440.0),
            sample_rate=RATE, role="debug_audio")
        row = w.artifact_row(other)
        data = (w.store.artifacts_dir / row[4]).read_bytes()
        _set_env(w, a["example_id"], "original_audio", other)
        ga, gk = _gate(w, a["example_id"]), _gate(w, ctrl)
        res = _export(w, ("asr_supervised",))
        obs = {"a": ga, "ctrl": gk, "role": row[1]}
        return check({
            "fixture_valid_own_wav": row[0] == a["job_id"]
            and data[:4] == b"RIFF" and data[8:12] == b"WAVE",
            "a_ineligible": not ga["eligible"]
            and "role" in str(ga["reason"]),
            "export_only_control": _ids(res, "asr_supervised") == {ctrl},
            "control_eligible": gk["eligible"] is True,
        }, obs, witness="own job's valid WAV with role debug_audio named"
                        " as original_audio")


@drives("LF-M14-C055")
def c055_foreign_verbatim(entry):
    with MWorld() as w:
        a = w.ready_asr(f"foreign verbatim alpha {A_CANARY}")
        b = w.ready_asr(f"foreign verbatim bravo {B_CANARY}")
        b_ref = w.envelope(b["example_id"])["annotations"][0][
            "artifact_id"]

        def swap(env):
            env["annotations"][0]["artifact_id"] = b_ref
            env["annotations"][0]["text_sha256"] = _sha(b["raw"])
        w.rewrite_envelope(a["example_id"], swap)
        ga, gb = _gate(w, a["example_id"]), _gate(w, b["example_id"])
        res = _export(w, ("asr_supervised",))
        leak = [r for r in _refs(res, a["example_id"])
                if B_CANARY in (r.get("text") or "")]
        obs = {"a": ga, "b": gb, "err": res["err"]}
        return check({
            "a_ineligible_on_lineage": not ga["eligible"]
            and "verbatim" in str(ga["reason"]),
            "no_foreign_text_as_a": not leak and a["example_id"]
            not in _ids(res, "asr_supervised"),
            "b_exported": _ids(res, "asr_supervised")
            == {b["example_id"]},
        }, obs, witness="A listened annotation -> B's verbatim_reference"
                        " artifact (digest consistent)")


@drives("LF-M14-C056")
def c056_historical_blocker(entry):
    with MWorld() as w:
        a = w.ready_asr("historic changed intent")["example_id"]
        c = w.ready_asr("unresolved ambiguity")["example_id"]
        b = w.ready_asr("blocker control")["example_id"]
        _label(w, a, "changed_intent", origin_stages=("user_intent",))
        _label(w, a, "recognition_error", origin_stages=("asr",))
        _label(w, c, "ambiguous")
        _label(w, b, "recognition_error", origin_stages=("asr",))
        gates = {n: _gate(w, x) for n, x in (("a", a), ("c", c),
                                              ("b", b))}
        res = _export(w, ("asr_supervised",))
        te = _te(w)["asr_supervised"]
        ex = _excl(res)
        obs = {"gates": {k: (g["eligible"], g["reason"])
                         for k, g in gates.items()},
               "ready": te["count"], "ready_excl": te["excluded"],
               "excluded": {"a": ex.get(a), "c": ex.get(c)}}
        return check({
            "gate_blocks_a_and_c": not gates["a"]["eligible"]
            and not gates["c"]["eligible"],
            "gate_admits_control": gates["b"]["eligible"] is True,
            "export_set": _ids(res, "asr_supervised") == {b},
            "readiness_count": te["count"] == 1,
            "readiness_reasons": te["excluded"].get(
                "blocking_label_changed_intent") == 1
            and te["excluded"].get("blocking_label_ambiguous") == 1,
            "export_reasons": any("changed_intent" in str(r)
                                  for r in ex.get(a) or [])
            and any("ambiguous" in str(r) for r in ex.get(c) or []),
        }, obs, witness="gate, readiness and export over the same three"
                        " examples agree on the D01 blocking policy")


# =============================================================================
# artifact_ownership — C057..C064
# =============================================================================


@drives("LF-M14-C057")
def c057_positive_owned_roles(entry):
    with MWorld() as w:
        raw = "positive owned roles hello world"
        norm = "positive owned roles hello, world"
        applied = "Positive owned roles: hello, world."
        a = w.job(raw, applied, normalized=norm)
        ex = a["example_id"]
        w.verbatim(ex, raw)
        w.training.mark_intended(ex, True)
        verb_aid = w.envelope(ex)["annotations"][-1]["artifact_id"]
        t = w.transform_task("owned transform source", ["Out one.",
                                                        "Out two."],
                             job_id=a["job_id"])
        cand = t["candidates"][0]
        w.accept(t, cand["candidate_id"])
        res = _export(w, ("asr_supervised", "cleanup_supervised",
                          "transform_supervised"))
        te = _te(w)

        def inputs(rec):
            return {(i.get("artifact_id"), i.get("role"))
                    for i in (rec.get("lineage") or {}).get("inputs") or []}
        asr = _recs(res, ex, "asr_supervised")
        cln = _recs(res, ex, "cleanup_supervised")
        tfm = [e for e in res["ex"] if e.get("task_kind")
               == "transform_supervised"]
        want_asr = {(a["audio_aid"], "original_audio"),
                    (verb_aid, "verbatim_reference")}
        want_cln = {(a["raw_aid"], "raw_transcript"),
                    (a["applied_aid"], "applied_output"),
                    (a["norm_aid"], "normalized_text")} | {
            (p, "cleanup_input_cleanup") for p in a["prompt_aids"]}
        want_tfm = {(cand["source_aid"], "transform_source"),
                    (cand["output_aid"], "transform_output")}
        obs = {"asr": len(asr), "cleanup": len(cln), "transform": len(tfm),
               "err": res["err"],
               "ready": {k: te[k]["count"] for k in (
                   "asr_supervised", "cleanup_supervised",
                   "transform_supervised")}}
        return check({
            "asr_exact_inputs": len(asr) == 1
            and inputs(asr[0]) == want_asr,
            "asr_owner_job": len(asr) == 1 and (
                asr[0].get("lineage") or {}).get("job_id") == a["job_id"],
            "cleanup_exact_inputs": len(cln) == 1
            and inputs(cln[0]) == want_cln,
            "cleanup_stage_texts": len(cln) == 1
            and cln[0].get("input_text") == norm
            and cln[0].get("output_text") == applied
            and cln[0].get("source_text") == raw,
            "transform_exact": len(tfm) == 1
            and tfm[0].get("candidate_id") == cand["candidate_id"]
            and tfm[0].get("input_text") == "owned transform source"
            and tfm[0].get("output_text") == "Out one."
            and want_tfm <= inputs(tfm[0]),
            "readiness_counts": obs["ready"] == {
                "asr_supervised": 1, "cleanup_supervised": 1,
                "transform_supervised": 1},
        }, obs, witness="one job with every producer role; export lineage"
                        " ids/roles vs ids the fixture minted")


def _teach_origin(swap):
    """A taught job whose envelope ``swap(w, job)`` rewrote first; the
    teach's stage attribution origin, or the refusal."""
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        swap(w, j)
        was_refused, out = _refused(w.learning.teach_correction,
                                    j["job_id"], TEACH_FIX)
        if was_refused:
            return {"refused": out}
        return {"origin": _origin(w, out["candidate_id"])}


def _cleanup_pair(swap_a):
    """A and control B, both marked correct; ``swap_a(w, a)`` corrupts A
    only. Returns export/readiness facts."""
    with MWorld() as w:
        a = w.ready_cleanup(f"cleanup alpha {A_CANARY}")
        b = w.ready_cleanup(f"cleanup bravo {B_CANARY}")
        swap_a(w, a, b)
        res = _export(w, ("cleanup_supervised",))
        ready = _te(w)["cleanup_supervised"]
        got = _ids(res, "cleanup_supervised")
        return {"a_in": a["example_id"] in got,
                "b_in": b["example_id"] in got,
                "a_reason": _excl(res).get(a["example_id"]),
                "ready": ready["count"], "err": res["err"],
                "export_n": len(got)}


@drives("LF-M14-C058")
def c058_foreign_raw(entry):
    def foreign_stage(w, j):
        b = w.job(TEACH_FIX, example=False)
        _set_env(w, j["example_id"], "source_text", b["raw_aid"])
    stage = _teach_origin(foreign_stage)
    stage_ctrl = _teach_origin(lambda w, j: None)
    cleanup = _cleanup_pair(lambda w, a, b: _set_env(
        w, a["example_id"], "source_text", b["raw_aid"]))
    with MWorld(min_words=10) as w:
        a = w.job(f"alpha speaks {A_CANARY} {A_CANARY}", audio=False)
        b = w.job(f"bravo speaks {B_CANARY} {B_CANARY} with more words",
                  audio=False)
        c = w.job("charlie foreign words never spoken by alpha at all",
                  audio=False, example=False)
        _set_env(w, a["example_id"], "source_text", c["raw_aid"])
        m = w.profile.compute()["measured"]
        prof = (m["eligible_examples"], m["eligible_words"])
        prof_want = (1, len(b["raw"].split()))
    obs = {"stage": stage, "stage_ctrl": stage_ctrl, "cleanup": cleanup,
           "profile": prof}
    return check({
        "stage_ignores_foreign_raw": stage.get("origin") == ["unknown"],
        "stage_control_reads_own_raw": stage_ctrl.get("origin") == ["asr"],
        "cleanup_rejects_foreign": not cleanup["a_in"] and cleanup["b_in"]
        and cleanup["ready"] == 1,
        "profile_rejects_foreign": prof == prof_want,
    }, obs, witness="A source_text -> another job's raw_transcript;"
                    " teach attribution, cleanup export/readiness and"
                    " profile compute")


@drives("LF-M14-C059")
def c059_transform_as_raw(entry):
    def tf_stage(w, j):
        t = w.transform_task("transform source", [TEACH_FIX],
                             job_id=j["job_id"])
        _set_env(w, j["example_id"], "source_text",
                 t["candidates"][0]["output_aid"])
    stage = _teach_origin(tf_stage)

    def tf_cleanup(w, a, b):
        t = w.transform_task("transform source", [a["raw"]],
                             job_id=a["job_id"])
        _set_env(w, a["example_id"], "source_text",
                 t["candidates"][0]["output_aid"])
    cleanup = _cleanup_pair(tf_cleanup)
    obs = {"stage": stage, "cleanup": cleanup}
    return check({
        "stage_refuses_wrong_stage": stage.get("origin") == ["unknown"],
        "cleanup_refuses_wrong_role": not cleanup["a_in"]
        and any("wrong_role" in str(r) for r in cleanup["a_reason"] or []),
        "control_kept": cleanup["b_in"] and cleanup["ready"] == 1,
    }, obs, witness="source_text -> own job's transform_output artifact"
                    " (same text as the raw)")


@drives("LF-M14-C060")
def c060_same_job_wrong_stage(entry):
    def swap(w, a, b=None):
        env_arts = w.envelope(a["example_id"])["artifact_ids"]
        n, ap = env_arts["normalization"], env_arts["applied_output"]

        def mut(env):
            env["artifact_ids"]["normalization"] = ap
            env["artifact_ids"]["applied_output"] = n
        w.rewrite_envelope(a["example_id"], mut)
    with MWorld() as w:
        a = w.job("swap stage alpha words", "Swap stage alpha words.",
                  normalized="swap stage alpha, words")
        b = w.job("swap stage bravo words", "Swap stage bravo words.",
                  normalized="swap stage bravo, words")
        for x in (a, b):
            w.training.mark_intended(x["example_id"], True)
        swap(w, a)
        res = _export(w, ("cleanup_supervised",))
        ready = _te(w)["cleanup_supervised"]
        got = _ids(res, "cleanup_supervised")
        a_teach, _m = _refused(w.learning.teach_correction, a["job_id"],
                               "Swap stage alpha verbs.")
        b_teach, _n = _refused(w.learning.teach_correction, b["job_id"],
                               "Swap stage bravo verbs.")
        reasons = _excl(res).get(a["example_id"]) or []
        obs = {"a_in": a["example_id"] in got, "reasons": reasons,
               "ready": ready["count"], "a_teach_refused": a_teach,
               "b_teach_refused": b_teach}
        return check({
            "cleanup_refuses_swap": a["example_id"] not in got
            and any("wrong_role" in str(r) for r in reasons),
            "control_exported": b["example_id"] in got
            and ready["count"] == 1,
            "teach_refuses_swapped_final": a_teach,
            "teach_control_accepted": not b_teach,
        }, obs, witness="own job's normalized_text/applied_output"
                        " exchanged in the envelope")


@drives("LF-M14-C061")
def c061_foreign_transform(entry):
    with MWorld() as w:
        t1 = w.transform_task(f"alpha task source {A_CANARY}",
                              ["Alpha one.", "Alpha two."])
        t2 = w.transform_task(f"bravo task source {B_CANARY}",
                              ["Bravo one.", "Bravo two."])
        c1 = t1["candidates"][0]["candidate_id"]
        foreign_out = t2["candidates"][0]["output_aid"]
        w.store.submit(lambda c: c.execute(
            "UPDATE transform_candidates SET output_artifact_id=? WHERE"
            " candidate_id=?", (foreign_out, c1)))
        w.accept(t1, c1)
        ctrl = t2["candidates"][1]["candidate_id"]
        w.accept(t2, ctrl)
        res = _export(w, ("transform_supervised",))
        te = _te(w)["transform_supervised"]
        rows = [e for e in res["ex"]
                if e.get("task_kind") == "transform_supervised"]
        obs = {"rows": [(r.get("candidate_id") == ctrl,
                         r.get("output_text")) for r in rows],
               "ready": te["count"], "ready_excl": te["excluded"],
               "err": res["err"]}
        return check({
            "no_foreign_candidate_row": not any(
                r.get("candidate_id") == c1 for r in rows),
            "no_foreign_output_text": not any(
                r.get("output_text") == "Bravo one." for r in rows),
            "control_exported": [r.get("candidate_id") for r in rows]
            == [ctrl] and rows[0].get("output_text") == "Bravo two.",
            "readiness_one": te["count"] == 1,
        }, obs, witness="T1 candidate's output_artifact_id -> T2's"
                        " transform_output; accept on both tasks")


@drives("LF-M14-C062")
def c062_wrong_verbatim_role(entry):
    with MWorld() as w:
        a = w.ready_asr("verbatim role alpha")
        ctrl = w.ready_asr("verbatim role control")["example_id"]

        def swap(env):
            env["annotations"][-1]["artifact_id"] = a["applied_aid"]
            env["annotations"][-1]["text_sha256"] = _sha(a["applied"])
            env["annotations"][-1]["listened_audio"] = True
        w.rewrite_envelope(a["example_id"], swap)
        ga, gk = _gate(w, a["example_id"]), _gate(w, ctrl)
        res = _export(w, ("asr_supervised",))
        obs = {"a": ga, "ctrl": gk}
        return check({
            "role_mismatch_refused": not ga["eligible"]
            and "role" in str(ga["reason"]),
            "export_only_control": _ids(res, "asr_supervised") == {ctrl},
            "control_eligible": gk["eligible"] is True,
        }, obs, witness="listened verbatim annotation -> own"
                        " applied_output artifact")


def _drop_row(w, aid):
    def op(c):
        c.execute("DELETE FROM artifact_leases WHERE artifact_id=?", (aid,))
        c.execute("DELETE FROM artifacts WHERE artifact_id=?", (aid,))
    w.store.submit(op)


@drives("LF-M14-C063")
def c063_deleted_artifact_row(entry):
    obs = {}
    with MWorld() as w:
        a = w.ready_asr("absent row alpha")
        b = w.ready_asr("absent row control")
        _drop_row(w, a["audio_aid"])
        gone = w.one("SELECT COUNT(*) FROM artifacts WHERE artifact_id=?",
                     (a["audio_aid"],))[0] == 0
        ga = _gate(w, a["example_id"])
        res = _export(w, ("asr_supervised",))
        obs["pre"] = {"a": ga, "excluded": _excl(res).get(
            a["example_id"])}
        conds = {
            "row_absent": gone,
            "absent_ineligible": not ga["eligible"]
            and "absent" in str(ga["reason"]),
            "absent_not_exported": _ids(res, "asr_supervised")
            == {b["example_id"]},
        }

    def fence_run(drop):
        from test_m14_remediation import export_or_refusal
        with MWorld() as w:
            a = w.ready_asr("fence alpha")
            w.families(10)
            w.splits.assign()
            fired = []
            # The seam is the op AFTER the export snapshot (its selection
            # runs inside that op); later reconcile reads may precede it
            # (cross-milestone D13).
            selected = []
            real_select = w.exporter._select

            def select(*a, **k):
                out = real_select(*a, **k)
                selected.append(1)
                return out
            w.exporter._select = select

            def hook():
                if fired or not selected:
                    return
                fired.append(1)
                if drop:
                    _drop_row(w, a["audio_aid"])
            with after_each_op(w.store, hook):
                out, err = export_or_refusal(w, "ds", ("asr_supervised",))
            return {"fired": bool(fired), "published": out is not None,
                    "err": err, "dest": (w.tmp / "ds").exists(),
                    "complete_rows": _count(
                        w, "SELECT COUNT(*) FROM export_manifests WHERE"
                           " state='complete'")}
    fence, ctrl = fence_run(True), fence_run(False)
    obs["fence"], obs["fence_ctrl"] = fence, ctrl
    if not fence["fired"]:
        return invalid("snapshot->publish seam not reached", obs)
    conds["fence_refuses_absent_row"] = (not fence["published"]
                                         and not fence["dest"]
                                         and fence["complete_rows"] == 0)
    conds["fence_control_publishes"] = ctrl["published"] and ctrl["dest"]
    return check(conds, obs,
                 witness="artifact row DELETEd (not purged) before the"
                         " gate, and between export snapshot and the"
                         " publish fence (after_each_op)")


@drives("LF-M14-C064")
def c064_fallback_job_role(entry):
    obs = {}
    with MWorld() as w:
        j = w.job(TEACH_RAW, example=False)
        st = _stage_texts(w, None, j["job_id"])
        cid = w.learning.teach_correction(j["job_id"], TEACH_FIX)[
            "candidate_id"]
        obs["positive"] = {"stages": sorted(st), "origin": _origin(w, cid)}
        conds = {
            "job_only_stage_texts": st == {"raw": TEACH_RAW,
                                           "applied": TEACH_RAW},
            "job_only_attribution_asr": obs["positive"]["origin"]
            == ["asr"],
        }

    def tampered(example):
        with MWorld() as w:
            j = w.job(TEACH_RAW, example=example)
            w.store.submit(lambda c: c.execute(
                "UPDATE artifacts SET content_text=? WHERE artifact_id=?",
                (TEACH_FIX, j["raw_aid"])))
            st = _stage_texts(w, j.get("example_id"), j["job_id"])
            cid = w.learning.teach_correction(j["job_id"], TEACH_FIX)[
                "candidate_id"]
            return {"raw_read": "raw" in st, "origin": _origin(w, cid)}
    job_only, env_twin = tampered(False), tampered(True)
    obs["tampered_job_only"], obs["tampered_envelope"] = job_only, env_twin
    conds["job_only_refuses_digest_mismatch"] = not job_only["raw_read"] \
        and job_only["origin"] == ["unknown"]
    conds["as_strict_as_envelope"] = job_only == env_twin
    return check(conds, obs,
                 witness="collection-off teach: stage_texts_for job+role"
                         " fallback; raw digest tamper vs envelope twin")


# =============================================================================
# partial_grafts — C065..C072
# =============================================================================


def _save_graft(w, j, spans, source_text=None, source_aid=None):
    return _refused(_label, w, j["example_id"], "recognition_error",
                    origin_stages=("asr",), confirmed_spans=spans,
                    **_src_kw(w, source_aid or j["raw_aid"],
                              source_text or j["raw"]))


@drives("LF-M14-C065")
def c065_positive_one_span(entry):
    with MWorld() as w:
        j = w.job(GRAFT_RAW)
        ex = j["example_id"]
        was_refused, _ = _save_graft(w, j, [_span(GRAFT_RAW, "cloud",
                                                  "Claude")])
        gid, payload, art = _graft_payload(w, ex) if not was_refused \
            else (None, None, None)
        res = _export(w, ("asr_supervised", "asr_span_graft_weak"))
        refs = _refs(res, ex, "asr_span_graft_weak")
        obs = {"refused": was_refused, "payload": payload is not None,
               "refs": len(refs)}
        p = payload or {}
        return check({
            "saved": not was_refused and gid is not None,
            "graft_row_owned": art is not None and art[0] == j["job_id"]
            and art[1] == "span_graft",
            "grafted_text": p.get("grafted_text")
            == "send the Claude report on friday",
            "coverage_exact": p.get("coverage") == [[9, 14]],
            "partial_kind": p.get("coverage_kind") == "partial",
            "source_link": p.get("source_artifact_id") == j["raw_aid"]
            and p.get("source_sha256") == _sha(GRAFT_RAW),
            "weak_record": len(refs) == 1
            and refs[0].get("coverage_spans") == [[9, 14]]
            and refs[0].get("source_text") == GRAFT_RAW
            and refs[0].get("grafted_text")
            == "send the Claude report on friday"
            and refs[0].get("reference_quality") == "weak_partial",
            "not_asr_supervised": ex not in _ids(res, "asr_supervised"),
        }, obs, witness="record_label one confirmed span bound to the"
                        " rendered raw id/sha; weak export view")


@drives("LF-M14-C066")
def c066_positive_several(entry):
    raw = "send the cloud report to jon on friday"
    with MWorld() as w:
        j = w.job(raw)
        ex = j["example_id"]
        s1, s2 = _span(raw, "cloud", "Claude"), _span(raw, "jon", "Jon")
        was_refused, _ = _save_graft(w, j, [s2, s1])
        _g, payload, _a = _graft_payload(w, ex) if not was_refused \
            else (None, None, None)
        res = _export(w, ("asr_supervised", "asr_span_graft_weak"))
        refs = _refs(res, ex, "asr_span_graft_weak")
        want_cov = [[9, 14], [25, 28]]
        p = payload or {}
        covered = sum(e - s for s, e in (p.get("coverage") or []))
        obs = {"refused": was_refused, "coverage": p.get("coverage"),
               "covered_chars": covered, "len": len(raw)}
        return check({
            "saved": not was_refused,
            "fixture_offsets": [s1["start"], s1["end"], s2["start"],
                                s2["end"]] == [9, 14, 25, 28],
            "only_confirmed_covered": p.get("coverage") == want_cov,
            "grafted_text": p.get("grafted_text")
            == "send the Claude report to Jon on friday",
            "remainder_unverified": covered == 8 and covered < len(raw)
            and p.get("coverage_kind") == "partial",
            "export_spans": len(refs) == 1
            and refs[0].get("coverage_spans") == want_cov
            and refs[0].get("coverage") == "partial",
            "not_asr_supervised": ex not in _ids(res, "asr_supervised"),
        }, obs, witness="two non-overlapping spans in one save; coverage"
                        " mask vs authored offsets")


@drives("LF-M14-C067")
def c067_overlap_adjacent(entry):
    raw = "send the cloud report"
    with MWorld() as w:
        j = w.job(raw)
        ex = j["example_id"]
        overlap = [{"start": 9, "end": 14, "before_words": ["cloud"],
                    "after_words": ["Claude"]},
                   {"start": 12, "end": 21,
                    "before_words": ["oud", "report"],
                    "after_words": ["memo"]}]
        over_refused, _ = _save_graft(w, j, overlap)
        after_overlap = (_count(w, "SELECT COUNT(*) FROM correction_labels"
                                   " WHERE example_id=?", (ex,)),
                         _grafts(w))
        adjacent = [{"start": 9, "end": 14, "before_words": ["cloud"],
                     "after_words": ["Claude"]},
                    {"start": 14, "end": 21, "before_words": ["report"],
                     "after_words": ["memo"]}]
        adj_refused, _ = _save_graft(w, j, adjacent)
        _g, payload, _a = _graft_payload(w, ex) if not adj_refused \
            else (None, None, None)
        p = payload or {}
        cov = p.get("coverage") or []
        union = set()
        dup = False
        for s, e in cov:
            span = set(range(s, e))
            dup = dup or bool(union & span)
            union |= span
        g = _gate(w, ex)
        obs = {"overlap_refused": over_refused,
               "after_overlap": after_overlap,
               "adjacent_refused": adj_refused, "coverage": cov}
        return check({
            "overlap_refused_no_write": over_refused
            and after_overlap == (0, 0),
            "adjacent_saved": not adj_refused,
            "adjacent_coverage": cov == [[9, 14], [14, 21]],
            "union_exact_no_dup": not dup and union == set(range(9, 21)),
            "no_duplicated_text": p.get("grafted_text")
            == "send the Claudememo",
            "never_full_gold": p.get("coverage_kind") == "partial"
            and not g["eligible"],
        }, obs, witness="overlapping spans refused before any write;"
                        " adjacent [9,14)+[14,21) accepted once each")


@drives("LF-M14-C068")
def c068_malformed_range(entry):
    with MWorld() as w:
        j = w.job(GRAFT_RAW)
        ex = j["example_id"]
        good = _span(GRAFT_RAW, "cloud", "Claude")
        bad = {
            "negative": dict(good, start=-1),
            "reversed": dict(good, start=14, end=9),
            "out_of_range": dict(good, end=999),
            "bool": dict(good, start=True, end=7),
            "string": dict(good, start="9", end="14"),
            "float_integral": dict(good, start=9.0, end=14.0),
            "float_fraction": dict(good, start=9.5),
        }
        results = {}
        for name, span in bad.items():
            if name == "bool":
                # start=True slices [1:7] of "a cloud report" -> " cloud"
                # and would pass a word check; a bool is not an offset.
                jb = w.job("a cloud report on friday")
                results[name] = _save_graft(w, jb, [span])[0]
                results["bool_rows"] = _count(
                    w, "SELECT COUNT(*) FROM correction_labels WHERE"
                       " example_id=?", (jb["example_id"],))
            else:
                results[name] = _save_graft(w, j, [span])[0]
        before_good = (_count(w, "SELECT COUNT(*) FROM correction_labels"),
                       _grafts(w))
        good_refused, _ = _save_graft(w, j, [good])
        after_good = (_count(w, "SELECT COUNT(*) FROM correction_labels"
                                " WHERE example_id=?", (ex,)),
                      _grafts(w, j["job_id"]))
        obs = {"refused": results, "before_good": before_good,
               "after_good": after_good}
        conds = {f"{n}_refused": results[n] for n in bad}
        conds["no_partial_writes"] = before_good == (0, 0)
        conds["valid_span_saves"] = not good_refused \
            and after_good == (1, 1)
        return check(conds, obs, witness="record_label confirmed_spans"
                                         " admission (D13 strict ints)")


@drives("LF-M14-C069")
def c069_unicode_offsets(entry):
    raw = "the café \U0001F469‍\U0001F4BB cloud report"
    with MWorld() as w:
        j = w.job(raw)
        ex = j["example_id"]
        s_cafe = {"start": 4, "end": 9, "before_words": ["cafe"],
                  "after_words": ["Café"]}
        cs = raw.index("cloud")
        s_cloud = {"start": cs, "end": cs + 5, "before_words": ["cloud"],
                   "after_words": ["Claude"]}
        u16 = len(raw[:cs].encode("utf-16-le")) // 2
        jn = w.job(raw)
        neg_refused, _ = _save_graft(w, jn, [dict(s_cloud, start=u16,
                                                  end=u16 + 5)])
        neg_rows = _count(w, "SELECT COUNT(*) FROM correction_labels"
                             " WHERE example_id=?", (jn["example_id"],))
        pos_refused, _ = _save_graft(w, j, [s_cafe, s_cloud])
        _g, payload, _a = _graft_payload(w, ex) if not pos_refused \
            else (None, None, None)
        p = payload or {}
        res = _export(w, ("asr_span_graft_weak",))
        refs = _refs(res, ex, "asr_span_graft_weak")
        want = [[4, 9], [cs, cs + 5]]
        slices = [refs[0]["source_text"][s:e] for s, e in
                  refs[0].get("coverage_spans") or []] if refs else []
        obs = {"cloud_cp": cs, "cloud_utf16": u16,
               "neg_refused": neg_refused, "pos_refused": pos_refused,
               "coverage": p.get("coverage"), "slices_ok": slices == [
                   "café", "cloud"]}
        return check({
            "fixture_offsets_differ": u16 != cs and raw[4:9]
            == "café",
            "utf16_offsets_refused": neg_refused and neg_rows == 0,
            "codepoint_spans_saved": not pos_refused,
            "coverage_code_points": p.get("coverage") == want,
            "grafted_text": p.get("grafted_text") == (
                "the Café \U0001F469‍\U0001F4BB Claude report"),
            "export_slices_exact": slices == ["café", "cloud"],
        }, obs, witness="combining mark, ZWJ emoji before the span;"
                        " code-point vs UTF-16 offsets")


@drives("LF-M14-C070")
def c070_stale_same_substring(entry):
    with MWorld() as w:
        j = w.job(GRAFT_RAW)
        ex = j["example_id"]
        s1 = j["raw_aid"]
        new_text = "send the cloud memo to sunday"
        s2 = w.store.write_text_artifact(
            job_id=j["job_id"], stage="asr", role="raw_transcript",
            text=new_text, retention_class="training")
        _set_env(w, ex, "source_text", s2)
        span = _span(GRAFT_RAW, "cloud", "Claude")
        same_offset = new_text[span["start"]:span["end"]] == "cloud"
        stale_refused, _ = _save_graft(w, j, [span], GRAFT_RAW, s1)
        after_stale = (_count(w, "SELECT COUNT(*) FROM correction_labels"
                                 " WHERE example_id=?", (ex,)), _grafts(w))
        fresh_refused, _ = _save_graft(w, j, [span], new_text, s2)
        _g, payload, _a = _graft_payload(w, ex) if not fresh_refused \
            else (None, None, None)
        obs = {"stale_refused": stale_refused, "after_stale": after_stale,
               "fresh_refused": fresh_refused,
               "kw_supported": bool(_src_kw(w, s1, GRAFT_RAW))}
        return check({
            "fixture_same_substring": same_offset,
            "stale_save_refused": stale_refused
            and after_stale == (0, 0),
            "current_identity_saves": not fresh_refused
            and (payload or {}).get("source_artifact_id") == s2,
        }, obs, witness="new raw_transcript artifact keeps 'cloud' at"
                        " [9,14); save bound to the old id/sha")


@drives("LF-M14-C071")
def c071_source_purge(entry):
    with MWorld() as w:
        a = w.job(GRAFT_RAW)
        b = w.job("send the cloud memo on monday")
        c = w.job("send the cloud note on tuesday")
        span = _span(GRAFT_RAW, "cloud", "Claude")
        w.purge(a["raw_aid"])
        a_refused, _ = _save_graft(w, a, [span])
        a_rows = (_count(w, "SELECT COUNT(*) FROM correction_labels WHERE"
                            " example_id=?", (a["example_id"],)),
                  _grafts(w, a["job_id"]))
        b_refused, _ = _save_graft(w, b, [span])
        c_refused, _ = _save_graft(w, c, [span])
        w.purge(b["raw_aid"])
        b_gid, _p, b_art = _graft_payload(w, b["example_id"])
        b_meta_kept = b_art is not None and b_art[2] == 0 \
            and _count(w, "SELECT COUNT(*) FROM correction_labels WHERE"
                          " example_id=?", (b["example_id"],)) == 1
        res = _export(w, ("asr_span_graft_weak",))
        weak = _ids(res, "asr_span_graft_weak")
        obs = {"a_refused": a_refused, "a_rows": a_rows,
               "b_saved": not b_refused, "c_saved": not c_refused,
               "b_meta_kept": b_meta_kept,
               "b_excluded": _excl(res).get(b["example_id"]),
               "err": res["err"]}
        if b_refused or c_refused:
            return invalid("graft fixtures B/C could not be saved", obs)
        return check({
            "save_from_purged_source_refused": a_refused
            and a_rows == (0, 0),
            "label_and_payload_kept": b_meta_kept,
            "weak_view_refuses_purged_source": b["example_id"]
            not in weak and bool(_excl(res).get(b["example_id"])),
            "intact_control_exported": c["example_id"] in weak,
        }, obs, witness="source purged before Save (A) and after Save"
                        " before export (B), control C intact")


@drives("LF-M14-C072")
def c072_no_gold_upgrade(entry):
    raw = "cloud report friday"
    with MWorld() as w:
        j = w.job(raw)
        ex = j["example_id"]
        spans = [_span(raw, "cloud", "Claude"),
                 _span(raw, "report", "memo"),
                 _span(raw, "friday", "Friday")]
        was_refused, _ = _save_graft(w, j, spans)
        ctrl = w.ready_asr("gold control words")["example_id"]
        g = _gate(w, ex)
        res = _export(w, ("asr_supervised", "asr_span_graft_weak"))
        te = _te(w)["asr_supervised"]
        refs = _refs(res, ex, "asr_span_graft_weak")
        obs = {"refused": was_refused, "gate": g, "refs": len(refs),
               "ready": te["count"]}
        return check({
            "saved": not was_refused,
            "gate_false": not g["eligible"],
            "not_asr_supervised": _ids(res, "asr_supervised") == {ctrl},
            "weak_partial": len(refs) == 1
            and refs[0].get("coverage") == "partial"
            and refs[0].get("reference_quality") == "weak_partial"
            and refs[0].get("coverage_spans") == [[0, 5], [6, 12],
                                                  [13, 19]],
            "readiness_only_control": te["count"] == 1,
        }, obs, witness="every visible word covered by spans, no"
                        " listened verbatim")


# =============================================================================
# stateful probes
# =============================================================================


@drives("LF-M14-S008")
def s008_ambiguous_resolved_later(entry):
    def run(first, second, interleave):
        with MWorld() as w:
            ex = w.ready_asr(f"probe {first} words")["example_id"]
            seen = {}

            def hook():
                if "fired" in seen or not interleave:
                    return
                seen["fired"] = True
                seen["between"] = _gate(w, ex)["eligible"]
                _label(w, ex, second, origin_stages=("asr",))
            with after_each_op(w.store, hook):
                _label(w, ex, first)
            if second and not interleave:
                _label(w, ex, second, origin_stages=("asr",))
            g = _gate(w, ex)
            rows = [r[2] for r in _label_rows(w, ex)]
            return {"reached": seen.get("fired", False),
                    "between": seen.get("between"),
                    "eligible": g["eligible"], "reason": g["reason"],
                    "rows": rows}
    inter = run("ambiguous", "recognition_error", True)
    ci = run("changed_intent", "recognition_error", True)
    none = run("ambiguous", None, False)
    alt = run("recognition_error", "ambiguous", False)
    obs = {"interleaved": inter, "changed_intent": ci,
           "no_action": none, "alternate_order": alt}
    if not (inter["reached"] and ci["reached"]):
        return invalid("rev1->rev2 seam not reached", obs)
    return check({
        "blocked_at_barrier": inter["between"] is False,
        "resolution_clears": inter["eligible"] is True
        and inter["rows"] == ["ambiguous", "recognition_error"],
        "changed_intent_preserved": ci["between"] is False
        and ci["eligible"] is False and ci["rows"] == [
            "changed_intent", "recognition_error"],
        "control_unresolved_blocks": none["eligible"] is False,
        "alternate_order_blocks": alt["eligible"] is False,
    }, obs, grading="decision", decision=D01,
        witness="after_each_op after rev1 commit: gate observed, rev2"
                " saved between writer ops")


@drives("LF-M14-S009")
def s009_asr_foreign_audio(entry):
    from test_m14_remediation import export_or_refusal

    def run(mode):
        with MWorld() as w:
            a = w.ready_asr(f"s009 alpha {A_CANARY}", freq=310.0)
            b = w.ready_asr(f"s009 bravo {B_CANARY}", freq=690.0)
            seen = {}
            # The alternate seam is the op AFTER the export snapshot (its
            # selection runs inside that op); reconcile reads may precede
            # it (cross-milestone D13).
            selected = []
            real_select = w.exporter._select

            def select(*a_, **k_):
                out = real_select(*a_, **k_)
                selected.append(1)
                return out
            w.exporter._select = select

            def swap():
                _set_env(w, a["example_id"], "original_audio",
                         b["audio_aid"])

            def hook():
                if "fired" in seen or (mode == "during_export"
                                       and not selected):
                    return
                seen["fired"] = True
                swap()
            pre = None
            if mode == "after_gate":
                with after_each_op(w.store, hook):
                    pre = _gate(w, a["example_id"])["eligible"]
            else:
                pre = _gate(w, a["example_id"])["eligible"]
            w.families(10)
            w.splits.assign()
            if mode == "during_export":
                with after_each_op(w.store, hook):
                    out, err = export_or_refusal(w, "ds",
                                                 ("asr_supervised",))
            else:
                out, err = export_or_refusal(w, "ds", ("asr_supervised",))
            from test_m14_remediation import export_records
            exs = export_records(w, "ds")[0] if out is not None else []
            b_frames = _store_frames(w, b["audio_aid"])
            a_frames = _store_frames(w, a["audio_aid"])
            a_recs = [e for e in exs if e["example_id"] == a["example_id"]]
            return {
                "reached": seen.get("fired", False), "pre": pre,
                "published": out is not None, "err": err,
                "a_gate": _gate(w, a["example_id"])["eligible"],
                "b_gate": _gate(w, b["example_id"])["eligible"],
                "a_exported": bool(a_recs),
                "a_has_b_bytes": any(wav_frames(w.tmp / "ds" / e["audio"])
                                     == b_frames for e in a_recs),
                "a_has_own_bytes": any(wav_frames(w.tmp / "ds"
                                                  / e["audio"])
                                       == a_frames for e in a_recs),
                "b_exported": any(e["example_id"] == b["example_id"]
                                  for e in exs)}
    inter, ctrl, alt = run("after_gate"), run("none"), run("during_export")
    obs = {"interleaved": inter, "control": ctrl, "alternate": alt}
    if not (inter["reached"] and alt["reached"]) or not inter["pre"]:
        return invalid("own-audio eligibility -> substitution seam not"
                       " reached", obs)
    return check({
        "a_gate_refuses": inter["a_gate"] is False,
        "a_export_refuses": inter["published"]
        and not inter["a_exported"],
        "b_remains_eligible": inter["b_gate"] is True
        and inter["b_exported"],
        "control_exports_own_audio": ctrl["published"]
        and ctrl["a_has_own_bytes"] and not ctrl["a_has_b_bytes"],
        "alternate_never_publishes_b_bytes_as_a": not alt["a_has_b_bytes"]
        and (not alt["published"] or alt["a_has_own_bytes"]),
    }, obs, witness="after_each_op after A's eligible gate read (and,"
                    " alternate order, after the export snapshot op)")


@drives("LF-M14-S010")
def s010_cleanup_foreign_wrong_role(entry):
    def build(w):
        xs = {n: w.ready_cleanup(f"s010 {n} words") for n in (
            "foreign", "transform", "wrong_stage", "control")}
        donor = w.job("s010 donor raw words", example=False)
        tfm = w.transform_task("s010 transform source",
                               [xs["transform"]["raw"]],
                               job_id=xs["transform"]["job_id"])
        return xs, donor, tfm

    def substitute(w, xs, donor, tfm):
        _set_env(w, xs["foreign"]["example_id"], "source_text",
                 donor["raw_aid"])
        _set_env(w, xs["transform"]["example_id"], "source_text",
                 tfm["candidates"][0]["source_aid"])
        _set_env(w, xs["wrong_stage"]["example_id"], "source_text",
                 xs["wrong_stage"]["applied_aid"])

    def outcome(w, xs):
        res = _export(w, ("cleanup_supervised",))
        got = _ids(res, "cleanup_supervised")
        return {"in": sorted(n for n, x in xs.items()
                             if x["example_id"] in got),
                "ready": _te(w)["cleanup_supervised"]["count"],
                "err": res["err"]}

    with MWorld() as w:
        xs, donor, tfm = build(w)
        seen = {}

        def hook():
            if "fired" in seen:
                return
            seen["fired"] = True
            substitute(w, xs, donor, tfm)
        with after_each_op(w.store, hook):
            pre = _te(w)["cleanup_supervised"]["count"]
        inter = outcome(w, xs)
        inter["pre"], inter["reached"] = pre, seen.get("fired", False)
    with MWorld() as w:
        xs, donor, tfm = build(w)
        ctrl = outcome(w, xs)
    with MWorld() as w:
        # Alternate order: substitutions land before the qualifying mark.
        xs = {n: w.job(f"s010 alt {n} words", f"S010 alt {n} words.")
              for n in ("foreign", "transform", "wrong_stage", "control")}
        donor = w.job("s010 alt donor", example=False)
        tfm = w.transform_task("s010 alt transform", [xs["transform"][
            "raw"]], job_id=xs["transform"]["job_id"])
        substitute(w, xs, donor, tfm)
        for x in xs.values():
            w.training.mark_intended(x["example_id"], True)
        alt = outcome(w, xs)
    obs = {"interleaved": inter, "control": ctrl, "alternate": alt}
    if not inter["reached"] or inter["pre"] != 4:
        return invalid("positive qualification -> substitution seam not"
                       " reached", obs)
    return check({
        "negatives_excluded": inter["in"] == ["control"]
        and inter["ready"] == 1,
        "control_all_qualified": ctrl["in"] == sorted(
            ["foreign", "transform", "wrong_stage", "control"])
        and ctrl["ready"] == 4,
        "alternate_order_excluded": alt["in"] == ["control"]
        and alt["ready"] == 1,
    }, obs, witness="after_each_op after readiness counted 4 qualified;"
                    " foreign raw, transform_source and own"
                    " applied_output substituted as source_text")


@drives("LF-M14-S013")
def s013_deletion_while_form_open(entry):
    from test_m14_remediation import db_text_dump

    def run(mode):
        with MWorld() as w:
            raw = f"review form {PRIVATE_CANARY} cloud report"
            j = w.job(raw)
            ex = j["example_id"]
            seen = {}

            def hook():
                if "fired" in seen or mode != "delete_before_save":
                    return
                seen["fired"] = True
                w.training.delete_everywhere(ex)
            with after_each_op(w.store, hook):
                detail = w.training.example_detail(ex)
            src = next((s for s in (detail or {}).get("stages") or []
                        if s.get("stage") == "source_text"), None)
            if src is None or not src.get("available"):
                return {"rendered": False}
            text, aid = src["text"], src["artifact_id"]
            span = _span(text, "cloud", "Claude")
            label_r, _ = _refused(_label, w, ex, "recognition_error",
                                  origin_stages=("asr",),
                                  confirmed_spans=[span],
                                  **_src_kw(w, aid, text))
            verb_r, _ = _refused(w.training.set_verbatim, ex, text,
                                 listened_audio=True)
            mark_r, _ = _refused(w.training.mark_intended, ex, True)
            if mode == "delete_after_save":
                w.training.delete_everywhere(ex)
            return {
                "rendered": True, "reached": seen.get("fired", False),
                "label_refused": label_r, "verbatim_refused": verb_r,
                "mark_refused": mark_r,
                "labels": _count(w, "SELECT COUNT(*) FROM"
                                    " correction_labels WHERE"
                                    " example_id=?", (ex,)),
                "live_grafts": _count(w, "SELECT COUNT(*) FROM artifacts"
                                         " WHERE role='span_graft' AND"
                                         " purged=0"),
                "live_verbatim": _count(w, "SELECT COUNT(*) FROM"
                                           " artifacts WHERE"
                                           " role='verbatim_reference'"
                                           " AND purged=0"),
                "state": w.one("SELECT state FROM training_examples"
                               " WHERE example_id=?", (ex,))[0],
                "canary_rows": sorted({t for t, v in db_text_dump(w)
                                       if PRIVATE_CANARY in v})}
    inter = run("delete_before_save")
    ctrl = run("none")
    alt = run("delete_after_save")
    obs = {"interleaved": inter, "control": ctrl, "alternate": alt}
    if not inter.get("rendered") or not inter.get("reached"):
        return invalid("rendered-form -> deletion seam not reached", obs)
    return check({
        "stale_label_refused": inter["label_refused"],
        "stale_verbatim_refused": inter["verbatim_refused"],
        "stale_mark_refused": inter["mark_refused"],
        "nothing_written": inter["labels"] == 0
        and inter["live_grafts"] == 0 and inter["live_verbatim"] == 0,
        "state_stays_deleted": inter["state"] == "deleted",
        "no_private_content_resurrected": inter["canary_rows"] == [],
        "control_saves": not ctrl["label_refused"]
        and not ctrl["verbatim_refused"] and not ctrl["mark_refused"]
        and ctrl["labels"] == 1 and ctrl["live_grafts"] == 1
        and bool(ctrl["canary_rows"]),
        "alternate_order_deletes_all": not alt["label_refused"]
        and alt["labels"] == 0 and alt["live_grafts"] == 0
        and alt["live_verbatim"] == 0 and alt["canary_rows"] == [],
    }, obs, witness="service level: example_detail (the rendered form)"
                    " -> delete_everywhere between writer ops -> label/"
                    "verbatim/mark with the rendered source identity; the"
                    " native Hub window half is graded by the owned-window"
                    " suite, not here")


# =============================================================================
# metamorphic relation
# =============================================================================


@drives("LF-M14-MR005")
def mr005_review_resolution(entry):
    with MWorld() as w:
        pairs = {}
        for kind in ("ambiguous", "user_rewrite", "changed_intent"):
            src = w.ready_asr(f"mr005 source {kind}")["example_id"]
            fol = w.ready_asr(f"mr005 followup {kind}")["example_id"]
            _label(w, src, kind)
            _label(w, fol, kind)
            # The transformation: an explicitly supported resolution.
            _label(w, fol, "recognition_error", origin_stages=("asr",))
            pairs[kind] = (src, fol)
        gates = {k: (_gate(w, s)["eligible"], _gate(w, f)["eligible"])
                 for k, (s, f) in pairs.items()}
        res = _export(w, ("asr_supervised",))
        got = _ids(res, "asr_supervised")
        ci_rows = [r[2] for r in _label_rows(w, pairs["changed_intent"][1])]
        obs = {"gates": gates, "exported": sorted(
            k for k, (s, f) in pairs.items() if f in got),
            "ci_rows": ci_rows}
        return check({
            "sources_all_blocked": all(not s for s, _f in gates.values()),
            "ambiguous_follows_resolution": gates["ambiguous"][1] is True,
            "rewrite_follows_resolution": gates["user_rewrite"][1] is True,
            "changed_intent_not_cleared": gates["changed_intent"][1]
            is False and ci_rows == ["changed_intent",
                                     "recognition_error"],
            "export_follows_gate": got == {pairs["ambiguous"][1],
                                           pairs["user_rewrite"][1]},
        }, obs, grading="decision", decision=D01,
            witness="source (blocking label) vs follow-up (+ explicit"
                    " recognition revision) for three blocking kinds")
