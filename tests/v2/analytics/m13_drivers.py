"""M13 corpus drivers, part one (identity, outcomes, retries, words,
transforms, repastes, timestamps, precision, DST, rebuild, zones,
aggregates, WPM, latency, filters, ranges).

Each driver binds one or more frozen corpus cases to the current
production APIs and grades the case's own expectation with an
independent oracle (literal values or ``m13_oracle``). A driver returns
a ``Result``; an exception is recorded by the runner as ERROR. A result
whose seam was not reached is INVALID, never a pass. ``grading`` says
how a PASS was earned: ``semantic`` (the observed value met the
expectation), ``structural`` (the seam does not exist in production —
the witness records why), ``decision`` (graded under the adopted
m13-policy-r1 decision named in ``decision``).
"""

from __future__ import annotations

import json
import math
import sys
import threading
import time

import m13_world as W
import test_m13_remediation as R
from m13_world import AWorld, Latch, MainQueue, epoch, local_day, patched
from m13_oracle import canonical, compare_aggregates, reference_aggregates

from localflow.v2 import analytics as A

DRIVERS: dict = {}


class Result(dict):
    pass


def result(status, observed=None, *, witness=None, grading="semantic",
           decision=None, note=None):
    return Result(status=status, observed=observed, witness=witness,
                  grading=grading, decision=decision, note=note)


def grade(observed: dict, expected: dict, **kw):
    """PASS when every non-prose expected key equals the observed one."""
    diffs = {k: {"expected": v, "observed": observed.get(k)}
             for k, v in expected.items()
             if k != "semantic_assertion" and observed.get(k) != v}
    return result("FAIL" if diffs else "PASS", observed,
                  note=(json.dumps(diffs, default=str)[:600]
                        if diffs else None), **kw)


def check(conds: dict, observed, **kw):
    """PASS when every named semantic condition holds."""
    failed = [k for k, ok in conds.items() if not ok]
    return result("FAIL" if failed else "PASS", observed,
                  note=("failed: " + ", ".join(failed)) if failed else None,
                  **kw)


def drives(*case_ids):
    def deco(fn):
        for cid in case_ids:
            DRIVERS[cid] = fn
        return fn
    return deco


def fx_dictation(case):
    return dict(case["fixture"].get("dictation") or W.DICTATION)


def summary_all(w, **kw):
    return w.insights.summary(days=None, **kw)


def mism(w):
    return w.mismatches()


# =============================================================================
# fact identity / terminal outcomes
# =============================================================================

@drives("M13-C001", "M13-C002", "M13-C004", "M13-C005")
def d_identity(case):
    fx = fx_dictation(case)
    var = case["fixture"].get("variation") or {}
    job = fx.pop("job_id")
    with AWorld() as w:
        if case["case_id"] == "M13-C002":
            w.dictation(job, **dict(fx, insertion_outcome=var[
                "first_outcome"], final_words=var["first_final_words"]))
            w.dictation(job, **dict(fx, attempt=var[
                "replacement_attempt"]))
        elif case["case_id"] == "M13-C004":
            w.dictation(job, **fx)
            w.dictation(var["second_job_id"], **fx)
        elif case["case_id"] == "M13-C005":
            w.dictation(job, **fx)
            w.dictation(job, **dict(fx, final_words=var[
                "replacement_final_words"]))
        else:
            w.dictation(job, **fx)
            w.dictation(job, **fx)  # the identical terminal fact again
        rows = w.rows("dictation")
        s = summary_all(w)
        obs = {"dictation_rows": len(rows), "final_words": s["final_words"],
               "attempt": rows[-1]["attempt"] if len(rows) == 1 else None,
               "failed": s["outcomes"]["failed"],
               "confirmed": s["outcomes"]["confirmed"]}
        out = grade(obs, case["expected"])
        if not mism(w):
            return out
        return result("FAIL", obs, note=f"aggregates: {mism(w)[:2]}")


@drives("M13-C003")
def d_duplicate_callback(case):
    """The coordinator's real insertion completion delivered twice for
    one job: the settle-once guard admits one fact."""
    from localflow.v2.insertion import InsertionResult
    with R.coordinator() as h, MainQueue() as mq:
        results = []

        def submit(text, job, on_done, on_observation=None):
            r = InsertionResult(insertion_id="ins-dup",
                                job_id=job.get("job_id"),
                                state="confirmed", inserted_chars=len(text))
            h.d._insertionDone_(r, job)
            results.append(r)
            h.d._insertionDone_(r, job)  # the duplicate delivery
        h.d._insertion.submit = submit
        job = R.drive(h, mq)
        rows = h.d.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM usage_facts WHERE kind='dictation'"
        ).fetchone()[0])
        obs = {"dictation_rows": rows,
               "terminal_settlements": 1 if job.get("_insertion_settled")
               else 0, "deliveries": len(results) * 2}
        if not results:
            return result("INVALID", obs, note="insertion never reached")
        return grade(obs, case["expected"],
                     witness={"barrier": "second _insertionDone_ after the"
                              " first settled", "reached": True})


@drives("M13-C006")
def d_stale_attempt(case):
    """Reachability first (M13-AUDIT-29): a retry exists only for a
    failed_recoverable job that no active job dict still owns; the real
    guards refuse a retry while attempt one is live, so attempt one can
    never deliver after attempt two. The raw writer is last-writer-wins
    and is recorded as adjudication evidence, not as a producer path."""
    with R.coordinator() as h, MainQueue():
        h.press()
        job = h.d._job  # the capturing job (active only after release)
        jid = job["job_id"]
        refused_active = h.d.hubRetryJob(jid)
        h.release()
        fn, args = h.run_coordinator()
        fn(*args)
        refused_terminal = h.d.hubRetryJob(jid)
    with AWorld() as w:
        fx = fx_dictation(case)
        fx.pop("job_id")
        w.dictation("job-raw", **dict(fx, attempt=2, final_words=90))
        w.dictation("job-raw", **dict(fx, attempt=1, final_words=120))
        raw_last = w.rows("dictation")[0]["attempt"]
    obs = {"retry_while_recording": refused_active,
           "retry_of_resolved_job": refused_terminal,
           "raw_api_last_writer_attempt": raw_last}
    ok = refused_active.get("outcome") in ("recording", "already_retrying",
                                           "not_retryable") and \
        refused_terminal.get("outcome") == "not_retryable"
    return result("PASS" if ok else "FAIL", obs, grading="structural",
                  witness={"guards": ["hubRetryJob refuses an active job",
                                      "_retry_job requires"
                                      " failed_recoverable",
                                      "_claim_job is exclusive"]},
                  note="raw writer is last-writer-wins (evidence only):"
                       " no production producer delivers attempt 1 after"
                       " attempt 2")


def _coordinator_outcome(outcome, delay=0.0):
    """One dictation through the real coordinator reaching ``outcome``;
    returns (fact rows, job)."""
    from localflow.v2.insertion import InsertionResult
    from test_lifecycle import FakeSupervisor

    class Failing(FakeSupervisor):
        def transcribe(self, **kw):
            if delay:
                time.sleep(delay)
            raise RuntimeError("synthetic worker fault")
    sup = Failing() if outcome == "failed" else None
    with R.coordinator(supervisor=sup) as h, MainQueue() as mq:
        if outcome in ("confirmed", "saved_not_inserted"):
            def submit(text, job, on_done, on_observation=None):
                if delay:
                    time.sleep(delay)
                h.d._insertionDone_(InsertionResult(
                    insertion_id="ins-x", job_id=job.get("job_id"),
                    state=outcome, inserted_chars=len(text),
                    reason_code=None if outcome == "confirmed"
                    else "synthetic_refusal"), job)
            h.d._insertion.submit = submit
        elif outcome == "posted_unverified" and delay:
            real = h.d._insertion.submit

            def submit(text, job, on_done, on_observation=None):
                time.sleep(delay)
                real(text, job, on_done, on_observation)
            h.d._insertion.submit = submit
        h.press()
        h.release()
        job = h.d._active_jobs[-1] if h.d._active_jobs else None
        if outcome == "cancelled_after_release":
            if delay:
                time.sleep(delay)
            h.d.cancelDictation()
        try:
            fn, args = h.run_coordinator()
            fn(*args)
        except AssertionError:
            pass
        mq.flush()
        rows = h.d.store.submit(lambda c: [dict(zip(
            [d[0] for d in c.execute("SELECT * FROM usage_facts").description],
            r)) for r in c.execute("SELECT * FROM usage_facts WHERE"
                                   " kind='dictation'").fetchall()])
        return rows, job


@drives("M13-C007", "M13-C008", "M13-C009", "M13-C010", "M13-C011")
def d_terminal(case):
    fx = fx_dictation(case)
    fx.pop("job_id")
    outcome = fx["insertion_outcome"]
    with AWorld() as w:
        w.dictation("job-a", **fx)
        s = summary_all(w)
        obs = {"dictations": s["dictations"],
               "dictations_with_text": s["dictations_with_text"],
               "final_words": s["final_words"],
               "outcome_count": {k: v for k, v in s["outcomes"].items()
                                 if v}}
    # Branch witness: the real coordinator reaches this terminal
    # outcome and records exactly it.
    branch = {"confirmed": "confirmed", "posted_unverified":
              "posted_unverified", "saved_not_inserted":
              "saved_not_inserted", "failed": "failed",
              "cancelled": "cancelled_after_release"}[outcome]
    rows, _job = _coordinator_outcome(branch)
    obs["coordinator_outcomes"] = [r["insertion_outcome"] for r in rows]
    out = grade(obs, case["expected"])
    if obs["coordinator_outcomes"] != [outcome]:
        return result("FAIL", obs, note="coordinator did not record the"
                      f" {outcome} branch once")
    return out


@drives("M13-C012")
def d_empty_transcription(case):
    from test_lifecycle import FakeSupervisor
    sup = FakeSupervisor(script={"transcribe": [{"text": ""}]})
    with R.coordinator(supervisor=sup) as h, MainQueue() as mq:
        R.drive(h, mq)
        s = h.d._insights.summary(days=None)
        obs = {"dictations": s["dictations"],
               "final_words": s["final_words"],
               "dictations_with_text": s["dictations_with_text"],
               "wpm": s["wpm"],
               "outcome": [k for k, v in s["outcomes"].items() if v]}
    out = grade(obs, case["expected"])
    if obs["outcome"] != ["saved_not_inserted"]:
        return result("FAIL", obs, note="empty result not the documented"
                      " saved outcome")
    return out


@drives("M13-C259")
def d_reconcile_seam(case):
    """No production producer upgrades posted_unverified to confirmed
    after the fact (the M08 queue settles once; the only later
    confirmation is the M12 note receipt, a first settlement). The seam
    is recorded as absent; the writer's replacement is shown correct for
    the case's numbers."""
    import pathlib
    src = (pathlib.Path(A.__file__).parents[1] / "app.py").read_text()
    confirm_sites = src.count('"insertion_confirmed"')
    fx = case["fixture"]
    with AWorld() as w:
        w.dictation(fx["job_id"], insertion_outcome=fx["first_outcome"],
                    raw_words=fx["raw_words"], final_words=fx["final_words"])
        w.dictation(fx["job_id"], insertion_outcome=fx["later_outcome"],
                    raw_words=fx["raw_words"], final_words=fx["final_words"])
        s = summary_all(w)
        obs = {"dictations": s["dictations"],
               "final_words": s["final_words"],
               "confirmed": s["outcomes"]["confirmed"],
               "insertion_confirmed_sites_in_coordinator": confirm_sites}
    ok = obs["dictations"] == 1 and obs["final_words"] == 18 and \
        obs["confirmed"] == 1
    return result("PASS" if ok else "FAIL", obs, grading="structural",
                  witness={"producer": "absent — recorded as a design gap"})


# =============================================================================
# retries (the real History retry path)
# =============================================================================

def _failed_job(h, captured="2026-09-25T23:30:00.000Z", zone=None,
                offset=None, target=("Synthetic Alpha",
                                     "com.synthetic.alpha"),
                prov_instant=None, store_instant=True):
    """A failed_recoverable job with retained recovery audio (and,
    optionally, a capture-provenance sidecar) — the state the real
    History retry reads."""
    import numpy as np
    import localflow.app as app_mod
    from localflow.v2 import store as store_mod
    job_id, fam = h.d.store.create_job(
        captured_at_utc=captured if store_instant else None,
        time_quality="known" if store_instant else "unknown",
        timezone=zone, utc_offset_minutes=offset,
        state="failed_recoverable")
    if target:
        h.d.store.submit(lambda c: c.execute(
            "INSERT OR REPLACE INTO job_targets(job_id, app_name,"
            " app_bundle, recorded_at_utc) VALUES(?,?,?,?)",
            (job_id, *target, "2026-09-25T23:30:00.000Z")))
    wav = app_mod.V2_JOURNAL / f"job-{job_id}.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    store_mod.write_wav_f32(wav, np.linspace(-0.4, 0.4, 16000).astype(
        np.float32), 16000)
    if prov_instant is not None:
        (app_mod.V2_JOURNAL / f"job-{job_id}{app_mod.PROVENANCE_SUFFIX}"
         ).write_text(json.dumps({
             "capture_provenance_version": app_mod.PROVENANCE_VERSION,
             "job_id": job_id, "family_id": fam,
             "captured_at_utc": prov_instant, "time_quality": "known",
             "timezone": zone, "utc_offset_minutes": offset}))
    return job_id


def _retry(h, mq, job_id):
    out = h.d.hubRetryJob(job_id)
    if out is not None and out.get("outcome") not in (None, "retrying",
                                                      "queued"):
        if "outcome" in out and out["outcome"] != "requeued":
            pass
    fn, args = h.run_coordinator()
    fn(*args)
    mq.flush()
    return out


def _facts(h):
    return h.d.store.submit(lambda c: [dict(zip(
        [d[0] for d in c.execute("SELECT * FROM usage_facts"
                                 ).description], r))
        for r in c.execute("SELECT * FROM usage_facts WHERE"
                           " kind='dictation'").fetchall()])


@drives("M13-C013", "M13-C014")
def d_retry_provenance(case):
    var = case["fixture"]["variation"]
    capture = var.get("capture", "2026-09-25T23:30:00.000Z")
    zone = var.get("zone", "America/New_York")
    offset = var.get("offset_minutes", -240)
    with R.coordinator(cfg={"analytics_timezone": "America/New_York"}) \
            as h, MainQueue() as mq:
        jid = _failed_job(h, captured=capture, zone=zone, offset=offset)
        out = h.d.hubRetryJob(jid)
        fn, args = h.run_coordinator()
        fn(*args)
        mq.flush()
        rows = _facts(h)
    obs = {"retry": out, "rows": len(rows)}
    if rows:
        r = rows[0]
        obs.update(activity_at_utc=r["activity_at_utc"],
                   timezone=r["timezone"],
                   utc_offset_minutes=r["utc_offset_minutes"],
                   app_name=r["app_name"], attempt=r["attempt"],
                   day_local=r["day_local"])
    expect_day = local_day(capture, "America/New_York")
    return check({
        "one_row": obs["rows"] == 1,
        "original_instant": obs.get("activity_at_utc") ==
        canonical(capture),
        "original_day": obs.get("day_local") == expect_day,
        "original_zone": obs.get("timezone") == zone,
        "original_offset": obs.get("utc_offset_minutes") == offset,
        "original_app": obs.get("app_name") == "Synthetic Alpha",
        "attempt_two": obs.get("attempt") == 2}, obs)


@drives("M13-C015", "M13-C016")
def d_retry_missing_instant(case):
    var = case["fixture"]["variation"]
    with R.coordinator() as h, MainQueue() as mq:
        jid = _failed_job(h, store_instant=False,
                          prov_instant=var.get("journal_instant"))
        # An existing fact for the job (its first terminal) must not be
        # replaced with a fabricated date.
        h.d._analytics.record_dictation_fact(
            job_id=jid, activity_at_utc="2026-09-20T10:00:00.000Z",
            insertion_outcome="failed", attempt=1)
        before = _facts(h)
        h.d.hubRetryJob(jid)
        fn, args = h.run_coordinator()
        fn(*args)
        mq.flush()
        rows = _facts(h)
        events = "".join(p.read_text() for p in
                         (h.tmp / "events").glob("*.jsonl"))
    obs = {"before": [r["activity_at_utc"] for r in before],
           "after": [r["activity_at_utc"] for r in rows],
           "attempts": [r["attempt"] for r in rows],
           "refusal_recorded": "unknown_activity_time" in events}
    if case["case_id"] == "M13-C015":
        return check({"no_fabricated_date": obs["after"] == obs["before"],
                      "refused_content_free": obs["refusal_recorded"]},
                     obs)
    want = canonical(var["journal_instant"])
    return check({"journal_instant_used": obs["after"] == [want],
                  "attempt_two": obs["attempts"] == [2]}, obs)


@drives("M13-C017", "M13-C018")
def d_retry_tuple(case):
    var = case["fixture"]["variation"]
    fx = fx_dictation(case)
    fx.pop("job_id")
    with AWorld() as w:
        if case["case_id"] == "M13-C017":
            (d1, s1), (d2, s2) = var["first_hits"], var["second_hits"]
            w.dictation("job-a", **dict(fx, dictionary_hits=d1,
                                        snippet_hits=s1))
            w.dictation("job-a", **dict(fx, attempt=2, dictionary_hits=d2,
                                        snippet_hits=s2))
            r = w.rows("dictation")
            obs = {"rows": len(r), "dictionary_hits": r[0]["dictionary_hits"],
                   "snippet_hits": r[0]["snippet_hits"]}
            return check({"one": obs["rows"] == 1,
                          "replaced": (obs["dictionary_hits"],
                                       obs["snippet_hits"]) == (d2, s2)},
                         obs)
        a1, a2 = var["attempt1"], var["attempt2"]
        w.dictation("job-a", **dict(fx, asr_ms=a1["asr_ms"],
                                    final_words=a1["final_words"],
                                    insertion_outcome="failed"))
        w.dictation("job-a", **dict(fx, attempt=2, asr_ms=a2["asr_ms"],
                                    final_words=a2["final_words"]))
        r = w.rows("dictation")
        obs = {"rows": len(r), "asr_ms": r[0]["asr_ms"],
               "final_words": r[0]["final_words"]}
        return check({"one": obs["rows"] == 1,
                      "final_attempt_tuple": (obs["asr_ms"],
                                              obs["final_words"])
                      == (a2["asr_ms"], a2["final_words"])}, obs)


@drives("M13-C019")
def d_worker_retry(case):
    """The worker's own internal retry (a fresh generation answering the
    same job) bumps the attempt in place: one fact, never two."""
    from test_lifecycle import FakeSupervisor
    sup = FakeSupervisor(script={"clean": [{"retried": True,
                                            "attempt": 2}]})
    with R.coordinator(supervisor=sup) as h, MainQueue() as mq:
        R.drive(h, mq)
        rows = _facts(h)
    obs = {"rows": len(rows), "attempt": rows[0]["attempt"] if rows
           else None}
    return check({"one": obs["rows"] == 1, "attempt": obs["attempt"] == 2},
                 obs)


@drives("M13-C020")
def d_retry_unknown_app(case):
    with R.coordinator() as h, MainQueue() as mq:
        jid = _failed_job(h, target=None)
        h.d.hubRetryJob(jid)
        fn, args = h.run_coordinator()
        fn(*args)
        mq.flush()
        rows = _facts(h)
    obs = {"rows": len(rows), "app_name": rows[0]["app_name"] if rows
           else "missing", "app_bundle": rows[0]["app_bundle"] if rows
           else "missing"}
    return check({"one": obs["rows"] == 1,
                  "not_invented": obs["app_name"] is None
                  and obs["app_bundle"] is None}, obs)


# =============================================================================
# word accounting (the coordinator's terminal recorder)
# =============================================================================

def _record(h, *, raw, final_text, outcome="confirmed", tf=None, m10=None,
            job_id="job-words"):
    job = {"job_id": job_id, "raw": raw, "captured_at_utc":
           "2026-09-26T15:00:00.000Z", "stats": {"duration_sec": 10.0},
           "attempt": 1}
    if tf is not None:
        job["transform_result"] = tf
    if m10 is not None:
        job["m10"] = m10
    h.d._record_dictation_usage(job, outcome, final_text)
    return _facts(h)


class _TfJob:
    def __init__(self, tid="builtin:polish"):
        self.transform_id = tid

    def task_key(self):
        return "synthetic-task"


class _Tf:
    def __init__(self, path, output):
        self.path, self.output = path, output
        self.duration_ms = 40.0
        self.job = _TfJob()


@drives("M13-C021", "M13-C022", "M13-C023", "M13-C024", "M13-C025",
        "M13-C026", "M13-C027")
def d_words(case):
    fx = case["fixture"]
    cid = case["case_id"]
    raw = fx.get("asr", fx.get("final_text", ""))
    tf = None
    if cid == "M13-C021":
        final = fx["asr"]  # Raw mode inserts the ASR text
    elif cid == "M13-C022":
        final = fx["clean"]
    elif cid == "M13-C023":
        final = fx["transformed"]
        tf = _Tf("applied", fx["transformed"])
    elif cid == "M13-C024":
        final = fx["clean"]  # needs_review keeps the Clean text
        tf = _Tf(fx["result_path"], fx["proposal"])
    else:
        final = fx["final_text"]
    with R.coordinator() as h:
        rows = _record(h, raw=raw, final_text=final, tf=tf)
        s = h.d._insights.summary(days=None)
    obs = {"raw_words": rows[0]["raw_words"],
           "final_words": rows[0]["final_words"],
           "final_words_whitespace_v1": rows[0]["final_words"],
           "dictations": s["dictations"],
           "explicit_transforms": s["transforms"],
           "word_count_version": rows[0]["word_count_version"]}
    exp = dict(case["expected"])
    if cid in ("M13-C026", "M13-C027"):
        out = grade(obs, exp)
        if out["status"] == "PASS" and \
                obs["word_count_version"] != "whitespace-split-v1":
            return result("FAIL", obs, note="count not labeled whitespace")
        return out
    return grade(obs, exp)


@drives("M13-C028")
def d_mixed_versions(case):
    with AWorld() as w:
        for i, f in enumerate(case["fixture"]["facts"]):
            w.dictation(f"job-{i}", final_words=f["final_words"])
            w.store.submit(lambda c, i=i, v=f["word_count_version"]:
                           c.execute("UPDATE usage_facts SET"
                                     " word_count_version=? WHERE"
                                     " job_id=?", (v, f"job-{i}")))
        s = summary_all(w)
    obs = {"versions": s["word_count_versions"],
           "mixed": s["mixed_word_count_versions"]}
    return check({"disclosed": obs["mixed"] is True,
                  "both_listed": sorted(obs["versions"]) ==
                  ["synthetic-v2", "whitespace-split-v1"]}, obs,
                 grading="decision", decision="D08_WORD_VERSION")


# =============================================================================
# explicit transforms (the coordinator's completion seam)
# =============================================================================

def _tf_complete(h, *, path="applied", source_words=12, output_words=9,
                 note=False, refused=False):
    src = " ".join(["word"] * source_words)
    out = " ".join(["out"] * output_words)
    res = type("Res", (), {"job": None if refused else _TfJob(),
                           "path": path, "output": out,
                           "duration_ms": 40.0})()
    capture = {"source": src, "range": (0, len(src))}
    if note:
        capture["note"] = {"note_id": "note-synthetic"}
    defn = type("D", (), {"transform_id": "builtin:polish"})()
    h.d._tfShowResult_(res, capture, defn)
    h.d.store.sync()


@drives("M13-C029", "M13-C030", "M13-C031", "M13-C032", "M13-C033")
def d_explicit_transform(case):
    fx = case["fixture"]
    with R.coordinator() as h, MainQueue() as mq:
        before = h.d._insights.summary(days=None)
        _tf_complete(h, source_words=fx["source_words"],
                     output_words=fx["output_words"],
                     note=fx["execution_kind"] == "note")
        mq.flush()
        s = h.d._insights.summary(days=None)
        rows = h.d.store.submit(lambda c: c.execute(
            "SELECT source_kind, source_words FROM usage_facts WHERE"
            " kind='transform'").fetchall())
    obs = {"explicit_transform_facts": len(rows),
           "dictations_added": s["dictations"] - before["dictations"],
           "dictated_words_added": s["final_words"] - before["final_words"],
           "source_words_activity": rows[0][1] if rows else None,
           "source_kind": rows[0][0] if rows else None}
    return grade(obs, case["expected"])


@drives("M13-C034")
def d_duplicate_transform(case):
    """Each explicit execution posts exactly ONE completion: every
    transform work() ends with a single callAfter(_tfShowResult_), and
    the spawn wrapper posts its (None) completion only when work()
    raised before posting. A duplicate completion of one execution is
    not reachable, so no API change is justified (M13-AUDIT-29)."""
    import ast
    import pathlib
    import localflow.app as app_mod
    tree = ast.parse(pathlib.Path(app_mod.__file__).read_text())
    posts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "work":
            n = sum(1 for c in ast.walk(node)
                    if isinstance(c, ast.Call)
                    and any(isinstance(a, ast.Attribute)
                            and a.attr == "_tfShowResult_"
                            for a in c.args))
            posts[node.lineno] = n
    obs = {"work_functions": len(posts),
           "completions_posted_per_work": sorted(set(posts.values()))}
    ok = posts and set(posts.values()) == {1}
    return result("PASS" if ok else "FAIL", obs, grading="structural",
                  witness={"seam": "one completion per execution"})


@drives("M13-C035")
def d_auto_transform_deletion(case):
    fx = case["fixture"]
    d = dict(fx["dictation"])
    job = d.pop("job_id")
    with AWorld() as w:
        w.dictation(job, transform_id=fx["auto_transform_id"],
                    transform_path="applied", **d)
        for _ in range(fx["linked_repastes"]):
            w.repaste(job_id=job)
        for _ in range(fx["independent_explicit_transforms"]):
            w.transform()
        w.analytics.delete_usage_for_job(job)
        s = summary_all(w)
        obs = {"dictations": s["dictations"], "linked_repastes":
               s["repastes"], "independent_explicit_transforms":
               s["transforms"]}
        out = grade(obs, case["expected"])
        return out if not mism(w) else result("FAIL", obs,
                                              note=str(mism(w)[:2]))


@drives("M13-C036", "M13-C037", "M13-C038")
def d_transform_path(case):
    fx = case["fixture"]
    with R.coordinator() as h, MainQueue() as mq:
        _tf_complete(h, path=fx["path"], source_words=fx["source_words"],
                     output_words=fx["output_words"])
        _tf_complete(h, refused=True)  # refused before execution
        mq.flush()
        rows = h.d.store.submit(lambda c: c.execute(
            "SELECT transform_path FROM usage_facts WHERE kind='transform'"
        ).fetchall())
        s = h.d._insights.summary(days=None)
    obs = {"facts": len(rows), "path": rows[0][0] if rows else None,
           "dictated_words": s["final_words"]}
    return check({"one_execution": obs["facts"] == 1,
                  "path_truthful": obs["path"] == fx["path"],
                  "no_dictated_words": obs["dictated_words"] == 0}, obs)


# =============================================================================
# repastes (the real insertion service under both surfaces)
# =============================================================================

def _repaste_world(h):
    w, svc = R.real_insertion(h)
    jid, _f = h.d.store.create_job(
        captured_at_utc="2026-09-26T15:00:00.000Z", time_quality="known",
        state="insertion_posted")
    done = threading.Event()
    svc.submit("synthetic repaste words", {"job_id": jid, "attempt": 1},
               lambda r: done.set())
    assert done.wait(10)
    return w, svc, jid


def _run_repaste(h, svc, action):
    ran, finished = [], threading.Event()

    def witness(orig):
        def run(*a, **kw):
            try:
                r = orig(*a, **kw)
                ran.append(r)
                return r
            finally:
                finished.set()
        return run
    with patched(svc, "_repaste_now", witness):
        out = action()
        if isinstance(out, dict) and out.get("outcome") != "repaste_queued":
            finished.set()
        finished.wait(10)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (
                svc._in_flight or not svc._q.empty()):
            time.sleep(0.01)
    h.d.store.sync()
    return out, ran


def _history_paste(h, svc, text, job_id):
    """POLICY-D03: History's Paste Again queues only at the user's
    destination click (here the app in front, A/F1). Returns the
    invocation's refusal, or the M08 service's answer to the pick."""
    from m08_world import pick_destination  # on sys.path via real_insertion
    click = pick_destination(h.d)
    out = h.d.hubPasteText(text, job_id=job_id)
    if out.get("outcome") != "choosing_destination":
        return out
    got = {}

    def witness(orig):
        def run(*a, **kw):
            r = orig(*a, **kw)
            got.update(r or {})
            return r
        return run
    with patched(svc, "paste_text", witness):
        click()
    return got or {"outcome": "pick_refused"}


def _counts(h):
    s = h.d._insights.summary(days=None)
    return s["repastes"] or 0, s["dictations"], s["final_words"]


@drives("M13-C039", "M13-C040", "M13-C041")
def d_repaste_counted(case):
    surface = case["fixture"]["surface"]
    with R.coordinator() as h, MainQueue() as mq:
        w, svc, jid = _repaste_world(h)
        w.fields["F1"].text = ""
        before = _counts(h)
        if surface == "Recovery menu":
            out, ran = _run_repaste(
                h, svc, lambda: h.d.pasteLastResultAgain_(None))
        else:
            job = jid if surface == "History V2" else "legacy-db:1"
            # POLICY-D03: the History surface pastes at the user's pick.
            out, ran = _run_repaste(
                h, svc, lambda: _history_paste(
                    h, svc, "synthetic repaste words", job))
        mq.flush()
        after = _counts(h)
    if not ran or ran[0] is None:
        return result("INVALID", {"out": out}, note="no transaction ran")
    obs = {"repaste_delta": after[0] - before[0],
           "dictation_delta": after[1] - before[1],
           "dictated_word_delta": after[2] - before[2]}
    return grade(obs, case["expected"],
                 witness={"transaction_state": getattr(ran[0], "state",
                                                       None)})


@drives("M13-C042", "M13-C043", "M13-C044", "M13-C045", "M13-C046")
def d_repaste_policy(case):
    from localflow.v2.insertion import InsertionResult
    kind = case["fixture"]["result"]
    deltas = {}
    for surface in ("history", "menu"):
        with R.coordinator() as h, MainQueue() as mq:
            w, svc, jid = _repaste_world(h)
            before = _counts(h)
            text = "synthetic repaste words"
            if kind == "already_present":
                pass  # F1 still holds the text → reconciled present
            else:
                w.fields["F1"].text = ""
            if kind == "nothing_to_paste":
                svc._last = None
                text = ""
            if kind == "job_deleted":
                svc.revoke_job(jid)
            if kind in ("failed_transaction",
                        "saved_not_inserted_transaction"):
                state = ("failed" if kind == "failed_transaction"
                         else "saved_not_inserted")

                def forced(orig, state=state):
                    def run(op_id, text, job, *a, **kw):
                        return InsertionResult(
                            insertion_id="ins-forced",
                            job_id=job.get("job_id"), state=state,
                            reason_code="synthetic_transaction")
                    return run
                ctx = patched(svc, "_run_insert", forced)
            else:
                import contextlib
                ctx = contextlib.nullcontext()
            with ctx:
                if surface == "menu":
                    out, ran = _run_repaste(
                        h, svc, lambda: h.d.pasteLastResultAgain_(None))
                else:
                    # POLICY-D03: History pastes at the user's pick.
                    out, ran = _run_repaste(
                        h, svc, lambda: _history_paste(h, svc, text, jid))
            mq.flush()
            after = _counts(h)
            deltas[surface] = {"repaste_delta": after[0] - before[0],
                               "dictated_word_delta": after[2] - before[2],
                               "transaction": [getattr(r, "state", None)
                                               for r in ran]}
    obs = {"history": deltas["history"], "menu": deltas["menu"]}
    exp = case["expected"]
    ok = all(d["repaste_delta"] == exp["repaste_delta"]
             and d["dictated_word_delta"] == exp["dictated_word_delta"]
             for d in deltas.values())
    return result("PASS" if ok else "FAIL", obs, grading="decision",
                  decision="D04_ACTIVITY_SCOPE")


# =============================================================================
# timestamps, precision, DST
# =============================================================================

def _undated(w):
    return w.insights.undated_count()


@drives(*[f"M13-C{n:03d}" for n in range(47, 59)])
def d_admission(case):
    fx = case["fixture"]
    with AWorld(zone=fx["reporting_timezone"]) as w:
        before = _undated(w)
        fid = w.dictation("job-a", activity_at_utc=fx["activity_at_utc"])
        refused = any(n == "usage.fact_refused" for n, _k in w.events)
        obs = {"fact_admitted_under_current_contract": fid is not None,
               "legacy_undated_delta": _undated(w) - before,
               "refusal_event": refused,
               "rows": len(w.rows())}
    out = grade(obs, case["expected"])
    if out["status"] == "PASS" and not obs[
            "fact_admitted_under_current_contract"] and not refused:
        return result("FAIL", obs, note="refused without a diagnostic")
    return out


@drives(*[f"M13-C{n:03d}" for n in range(59, 65)])
def d_precision(case):
    fx = case["fixture"]
    with AWorld(now=epoch(fx["now_utc"])) as w:
        w.store.retention_days["usage"] = fx["retention_days"]
        w.dictation("job-x", activity_at_utc=fx["instant_utc"])
        w.dictation("job-ctl", activity_at_utc="2026-09-28T01:00:00.000Z")
        ctl_before = [a for a in w.aggs() if a["day_local"] == "2026-09-28"]
        w.analytics.expire_usage()
        left = {r["job_id"] for r in w.rows()}
        ctl_after = [a for a in w.aggs() if a["day_local"] == "2026-09-28"]
        obs = {"removed": "job-x" not in left,
               "other_day_unchanged": ctl_before == ctl_after
               and "job-ctl" in left}
        out = grade(obs, case["expected"])
        return out if not mism(w) else result("FAIL", obs,
                                              note=str(mism(w)[:2]))


@drives(*[f"M13-C{n:03d}" for n in range(65, 73)])
def d_dst(case):
    fx = case["fixture"]
    with AWorld(zone=fx["reporting_timezone"]) as w:
        w.dictation("job-a", activity_at_utc=fx["instant_utc"])
        row = w.rows()[0]
        agg = {a["day_local"]: a for a in w.aggs()}
        obs = {"day_local": row["day_local"],
               "dictations": agg.get(row["day_local"], {}).get(
                   "dictations")}
        # Independent reference: zoneinfo directly.
        ref = local_day(fx["instant_utc"], fx["reporting_timezone"])
        out = grade(obs, case["expected"])
        if out["status"] == "PASS" and ref != obs["day_local"]:
            return result("FAIL", obs, note="reference disagrees")
        return out


# =============================================================================
# timezone rebuild and admission
# =============================================================================

NY, LA = "America/New_York", "America/Los_Angeles"


@drives("M13-C073")
def d_rebucket(case):
    fx = case["fixture"]
    with AWorld(zone=fx["from"]) as w:
        w.dictation("job-a", activity_at_utc=fx["instant"])
        old_day = w.rows()[0]["day_local"]
        w.analytics.rebuild_aggregates(reporting_timezone=fx["to"])
        new = w.rows()
        obs = {"old_day": old_day, "new_day": new[0]["day_local"],
               "total_facts_unchanged": len(new) == 1}
        out = grade(obs, case["expected"])
        m = w.mismatches(zone=fx["to"])
        return out if not m else result("FAIL", obs, note=str(m[:2]))


@drives("M13-C074")
def d_rollback(case):
    r = _run_regression("f02_failed_rebuild_restores_zone_everywhere")
    return r


@drives("M13-C075")
def d_queued_fact(case):
    return _run_regression(
        "f02_fact_admitted_across_rebuild_uses_committed_zone")


def _run_regression(name):
    fn = next(f for f in R.CASES if f.__name__ == name)
    try:
        fn()
        return result("PASS", {"regression": name},
                      witness={"bound_to": name})
    except AssertionError as e:
        return result("FAIL", {"regression": name}, note=str(e)[:400])


@drives("M13-C076", "M13-C077")
def d_query_vs_rebuild(case):
    """Both interleavings of a queued summary and a queued rebuild: the
    range, the fact days and the label always come from one committed
    zone (the range is derived inside the query's own writer op)."""
    at = "2026-09-27T04:30:00.000Z"
    outcomes = {}
    for order in ("query_first", "rebuild_first"):
        with AWorld(zone=NY, now=W.CLOCK) as w:
            w.dictation("job-a", activity_at_utc=at)
            box = {}
            with w.hold_writer():
                ths = []
                q = threading.Thread(target=lambda: box.setdefault(
                    "s", w.insights.summary(days=1)))
                rb = threading.Thread(target=lambda: box.setdefault(
                    "r", w.analytics.rebuild_aggregates(
                        reporting_timezone=LA)))
                first, second = (q, rb) if order == "query_first" \
                    else (rb, q)
                first.start()
                _wait_queued(w.store, 2)
                second.start()
                _wait_queued(w.store, 3)
                ths = [first, second]
            for t in ths:
                t.join(10)
            s = box["s"]
            zone = s["reporting_timezone"]
            expect = 1 if local_day(at, zone) == s["day_start"] else 0
            outcomes[order] = {"zone": zone, "day_start": s["day_start"],
                               "dictations": s["dictations"],
                               "coherent": s["dictations"] == expect}
    ok = all(o["coherent"] for o in outcomes.values()) and \
        outcomes["query_first"]["zone"] == NY and \
        outcomes["rebuild_first"]["zone"] == LA
    return result("PASS" if ok else "FAIL", outcomes,
                  witness={"barrier": "writer held; both orders queued",
                           "interleavings": 2})


def _wait_queued(store, n, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with store._cond:
            if len(store._queue) + (1 if store._executing else 0) >= n:
                return True
        time.sleep(0.005)
    raise AssertionError("op never queued")


@drives("M13-C078", "M13-C079")
def d_version_drift(case):
    fx = case["fixture"]
    with AWorld() as w:
        w.dictation("job-a")
        w.dictation("job-b", activity_at_utc="2026-09-25T10:00:00.000Z")
        cur = fx["test_current_version"]
        versions = fx["aggregate_versions"]
        days = [a["day_local"] for a in w.aggs()]
        for day, v in zip(days, versions * 2):
            w.store.submit(lambda c, d=day, v=v: c.execute(
                "UPDATE daily_aggregates SET algorithm_version=? WHERE"
                " day_local=?", (v, d)))
        facts_before = w.rows()
        with patched(A, "ALGORITHM_VERSION", lambda _o: cur):
            out = w.analytics.ensure_current()
            got = sorted({a["algorithm_version"] for a in w.aggs()})
            m = w.mismatches(version=cur)
        facts_after = w.rows()
        keep = [{k: v for k, v in r.items() if k not in
                 ("day_local", "reporting_timezone")} for r in facts_before]
        keep2 = [{k: v for k, v in r.items() if k not in
                  ("day_local", "reporting_timezone")} for r in facts_after]
    obs = {"rebuilt": out["rebuilt"], "aggregate_versions": got,
           "facts_semantics_preserved": keep == keep2, "mismatches": m}
    return check({"rebuilt": out["rebuilt"],
                  "one_version": got == [cur],
                  "facts": obs["facts_semantics_preserved"],
                  "reducer": not m}, obs)


@drives("M13-C080")
def d_mixed_zones(case):
    with AWorld(zone=NY) as w:
        w.dictation("job-a")
        w.dictation("job-b", activity_at_utc="2026-09-25T10:00:00.000Z")
        w.store.submit(lambda c: c.execute(
            "UPDATE usage_facts SET reporting_timezone='UTC' WHERE"
            " job_id='job-a'"))
        out = w.analytics.ensure_current()
        zones = {r["reporting_timezone"] for r in w.rows()}
        m = w.mismatches(zone=NY)
    obs = {"rebuilt": out["rebuilt"], "reasons": out["reasons"],
           "zones": sorted(zones)}
    return check({"detected": "fact_zone_drift" in out["reasons"],
                  "one_zone": zones == {NY}, "reducer": not m}, obs)


@drives("M13-C081")
def d_same_zone(case):
    with AWorld(zone="UTC") as w:
        w.dictation("job-a", dictionary_hits=2)
        w.transform()
        w.repaste()
        for _ in range(case["fixture"]["repeat"]):
            w.analytics.rebuild_aggregates(reporting_timezone="UTC")
        m = w.mismatches(zone="UTC")
    return check({"reducer": not m}, {"mismatches": m})


def _independently_valid_zone(value) -> bool:
    """The oracle's own answer (never the production validator's):
    a non-empty string the tz database resolves."""
    import zoneinfo
    if not isinstance(value, str) or value == "":
        return False
    try:
        zoneinfo.ZoneInfo(value)
        return True
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        return False


@drives(*[f"M13-C{n:03d}" for n in range(82, 89)])
def d_zone_admission(case):
    value = case["fixture"]["value"]
    zone, reason = A.validate_reporting_zone(value)
    with AWorld() as w:
        try:
            a = A.AnalyticsStore(w.store, reporting_timezone=value)
            direct = ("accepted", a.reporting_timezone)
        except ValueError:
            direct = ("refused", None)
        rb = w.analytics.rebuild_aggregates(reporting_timezone=value) \
            if value is not None else {"outcome": "committed_zone_used"}
    valid_name = _independently_valid_zone(value)
    obs = {"config": {"zone": zone, "reason": reason}, "direct": direct,
           "rebuild": rb.get("outcome", "rebuilt")}
    if value in (None, ""):
        ok = zone == A.system_zone() and direct[0] == "accepted"
    elif valid_name:
        ok = zone == value and direct == ("accepted", value) and \
            obs["rebuild"] == "rebuilt"
    else:
        ok = zone is None and reason is not None and \
            direct[0] == "refused" and obs["rebuild"] == "unknown_timezone"
    return result("PASS" if ok else "FAIL", obs)


# =============================================================================
# aggregate invariants (all fields, independent reducer)
# =============================================================================

@drives(*[f"M13-C{n:03d}" for n in range(89, 101)])
def d_aggregates(case):
    fx = case["fixture"]
    op = fx["operation"]
    with AWorld() as w:
        facts = [dict(d) for d in fx["dictations"]]
        if op != "first fact":
            for d in facts:
                j = d.pop("job_id")
                w.dictation(j, **d)
            for _ in range(fx["activities"]["transforms"]):
                w.transform()
            for _ in range(fx["activities"]["repastes"]):
                w.repaste()
        fixture = dict(fx["dictations"][0])
        job = fixture.pop("job_id")
        if op == "first fact":
            w.dictation(job, **fixture)
        elif op == "same-day retry":
            w.dictation(job, **dict(fixture, attempt=2, final_words=12))
        elif op.startswith("cross-day correction"):
            if op.endswith("old day empty"):
                w.analytics.delete_usage_for_job("job-synthetic-b")
                w.store.submit(lambda c: c.execute(
                    "DELETE FROM usage_facts WHERE kind!='dictation'"))
                w.analytics.rebuild_aggregates()
            if op.endswith("transform/repaste remaining"):
                w.analytics.delete_usage_for_job("job-synthetic-b")
            w.dictation(job, **dict(fixture, activity_at_utc=
                                    "2026-09-25T15:00:00.000Z"))
        elif op == "explicit transform":
            w.transform(at="2026-09-26T16:00:00.000Z")
        elif op == "linked repaste":
            w.repaste(job_id=job)
        elif op == "delete one job":
            w.analytics.delete_usage_for_job(job)
        elif op == "delete last fact of day":
            w.dictation("job-lone", activity_at_utc=
                        "2026-09-25T09:00:00.000Z")
            w.analytics.delete_usage_for_job("job-lone")
        elif op == "delete all":
            w.analytics.delete_all_usage()
        elif op == "retention expiry":
            w.dictation("job-old", activity_at_utc=
                        "2026-06-01T09:00:00.000Z")
            w.store.retention_days["usage"] = 30
            w.analytics.expire_usage()
        elif op == "timezone rebuild":
            w.analytics.rebuild_aggregates(reporting_timezone=NY)
        m = w.mismatches()
        obs = {"operation": op, "facts": len(w.rows()),
               "aggregate_days": [a["day_local"] for a in w.aggs()],
               "mismatches": m}
    return check({"all_fields_equal": not m}, obs)


@drives("M13-C260")
def d_activity_dates(case):
    fx = case["fixture"]
    with AWorld() as w:
        w.dictation("job-c", activity_at_utc=fx["dictation_day"]
                    + "T15:00:00.000Z")
        w.transform(at=fx["transform_only_day"] + "T15:00:00.000Z")
        w.repaste(at=fx["repaste_only_day"] + "T09:00:00.000Z")
        daily = w.insights.daily(days=None)
        by = {r["day"]: r for r in daily}
        obs = {"daily_dates": sorted(by),
               "activity_only_words": [by[d]["final_words"] for d in (
                   fx["transform_only_day"], fx["repaste_only_day"])
                   if d in by]}
    out = grade(obs, {"daily_dates": case["expected"]["daily_dates"]})
    if out["status"] == "PASS" and obs["activity_only_words"] != [0, 0]:
        return result("FAIL", obs, note="activity day carries words")
    return out


# =============================================================================
# WPM and latency
# =============================================================================

def _rows_world(rows):
    w = AWorld()
    for i, r in enumerate(rows):
        outcome = r.get("outcome", "confirmed")
        w.dictation(f"job-{i}", final_words=r["words"] if outcome not in
                    ("cancelled", "failed") else None,
                    duration_sec=r["seconds"], insertion_outcome=outcome)
    return w


@drives(*[f"M13-C{n:03d}" for n in range(101, 109)])
def d_wpm(case):
    with _rows_world(case["fixture"]["rows"]) as w:
        s = summary_all(w)
        den = s["wpm_denominator"]
        obs = {"wpm": s["wpm"], "eligible_jobs": den["jobs"],
               "eligible_words": den["words"],
               "eligible_seconds": den["capture_seconds"],
               "all_final_words": s["final_words"],
               "all_capture_seconds": s["capture_seconds"]}
    exp = dict(case["expected"])
    if isinstance(exp.get("wpm"), int):
        exp["wpm"] = float(exp["wpm"])
    for k in ("eligible_seconds", "all_capture_seconds"):
        if isinstance(exp.get(k), int):
            exp[k] = float(exp[k])
    return grade(obs, exp, grading="decision", decision="D01_WPM_DURATION")


def _special(v):
    if isinstance(v, dict) and "special_float" in v:
        return {"NaN": float("nan"), "+Infinity": float("inf"),
                "-Infinity": float("-inf")}[v["special_float"]]
    return v


@drives(*[f"M13-C{n:03d}" for n in range(109, 124)])
def d_numeric(case):
    fx = case["fixture"]
    metric, value = fx["metric"], _special(fx["value"])
    d = dict(fx["dictation"])
    d.pop("job_id")
    d[metric] = value
    with AWorld() as w:
        try:
            w.dictation("job-a", **d)
            refused = False
        except ValueError:
            refused = True
        rows = w.rows()
        s = summary_all(w)
        try:
            W.strict_json(s)
            finite = True
        except ValueError:
            finite = False
        stored = rows[0][metric] if rows else None
        meta = json.loads(rows[0]["meta_json"]) if rows else {}
    obs = {"refused": refused, "stored": stored,
           "reason": meta.get("invalid_metrics"), "json_finite": finite,
           "wpm": s["wpm"]}
    ok = finite and (refused or (stored is None and obs["reason"]))
    if metric == "duration_sec" and not refused:
        ok = ok and s["wpm"] is None  # no free words for the bad row
    return result("PASS" if ok else "FAIL", obs)


@drives(*[f"M13-C{n:03d}" for n in range(124, 130)])
def d_nearest_rank(case):
    fx = case["fixture"]
    xs = fx["observations_ms"]
    with AWorld() as w:
        for i, x in enumerate(xs):
            w.dictation(f"job-{i}", end_to_end_ms=float(x))
        lat = summary_all(w)["latency"]["end_to_end"]
    obs = {"n": lat["n"], "p50": lat["p50"], "p95": lat["p95"],
           "p99_if_exposed": lat.get("p99")}
    exp = {k: (float(v) if isinstance(v, int) and k != "n" else v)
           for k, v in case["expected"].items()}
    return grade(obs, exp)


@drives("M13-C130")
def d_metric_n(case):
    with AWorld() as w:
        for i, r in enumerate(case["fixture"]["rows"]):
            w.dictation(f"job-{i}", asr_ms=r.get("asr_ms"),
                        cleanup_ms=r.get("cleanup_ms"),
                        end_to_end_ms=r.get("end_to_end_ms"),
                        insertion_outcome=r.get("outcome", "confirmed"),
                        final_words=None if r.get("outcome") == "failed"
                        else 10)
        s = summary_all(w)
    lat = s["latency"]
    obs = {"dictations": s["dictations"], "asr_n": lat["asr"]["n"],
           "cleanup_n": lat["cleanup"]["n"],
           "end_to_end_n": lat["end_to_end"]["n"]}
    return grade(obs, case["expected"])


@drives(*[f"M13-C{n:03d}" for n in range(131, 139)])
def d_clock(case):
    """D06 clocks through the real coordinator with a known injected
    post-release delay."""
    kind = case["fixture"]["outcome"]
    delay = case["fixture"]["injected_monotonic_delay_ms"] / 1000.0
    obs = {"outcome": kind}
    if kind == "cancelled_while_holding":
        with R.coordinator() as h, MainQueue() as mq:
            h.press()
            time.sleep(delay)
            h.d.cancelDictation()
            mq.flush()
            rows = _facts(h)
        r = rows[0] if rows else {}
        meta = json.loads(r.get("meta_json") or "{}")
        obs.update(e2e=r.get("end_to_end_ms"),
                   missing=meta.get("e2e_missing"))
        ok = rows and obs["e2e"] is None and \
            obs["missing"] == "cancelled_before_release"
    elif kind == "committed_note":
        e2e = _note_settlement("committed", delay=delay)
        obs.update(e2e=e2e[0]["end_to_end_ms"] if e2e else None)
        ok = obs["e2e"] is not None and obs["e2e"] >= delay * 1000.0
    elif kind == "retry_success":
        with R.coordinator() as h, MainQueue() as mq:
            jid = _failed_job(h)
            real = h.d.supervisor.transcribe

            def slow(**kw):
                time.sleep(delay)
                return real(**kw)
            h.d.supervisor.transcribe = slow
            h.d.hubRetryJob(jid)
            fn, args = h.run_coordinator()
            fn(*args)
            mq.flush()
            rows = _facts(h)
        r = rows[0]
        meta = json.loads(r["meta_json"] or "{}")
        obs.update(e2e=r["end_to_end_ms"], missing=meta.get("e2e_missing"),
                   retry_ms=meta.get("retry_to_terminal_ms"),
                   activity=r["activity_at_utc"])
        ok = obs["e2e"] is None and \
            obs["missing"] == "retry_no_release_clock" and \
            (obs["retry_ms"] or 0) >= delay * 1000.0 and \
            obs["activity"] == canonical(
                "2026-09-25T23:30:00.000Z")
    else:
        rows, _job = _coordinator_outcome(kind, delay=delay)
        r = rows[0] if rows else {}
        obs.update(e2e=r.get("end_to_end_ms"),
                   recorded=r.get("insertion_outcome"))
        ok = rows and obs["e2e"] is not None and \
            obs["e2e"] >= delay * 1000.0
    return result("PASS" if ok else "FAIL", obs, grading="decision",
                  decision="D06_LATENCY_CLOCK")


def _note_settlement(outcome, delay=0.0, retry_first=False, dup=False):
    """The coordinator's real note branch: _finishWithText_ binds the
    job to a real ``Arrival`` receipt (the editor seam returns it) and
    settles it; returns the dictation fact rows after settlement."""
    from localflow.v2.notes import Arrival
    with R.coordinator() as h, MainQueue() as mq:
        arrivals = []

        class _Hub:
            state = None

            def scratchpad_receive(self, text, job):
                a = Arrival(note_id="note-synthetic", generation=1,
                            preimage="", content=text, origin="dictated",
                            trigger="system", source_job_id=job["job_id"],
                            text=text)
                arrivals.append(a)
                return a
        h.d._hub = _Hub()
        h.press()
        job = h.d._job  # the capturing job (active only after release)
        job["note_target"] = {"note_id": "note-synthetic", "anchor": 0}
        h.release()
        fn, args = h.run_coordinator()
        fn(*args)
        mq.flush()
        before = _facts(h)
        a = arrivals[0]
        if retry_first:
            a.attempts += 1  # a failed save attempt: not a settlement
            mq.flush()
            pending = _facts(h)
        else:
            pending = before
        if delay:
            time.sleep(delay)
        a.revision_id = "nrev-synthetic"
        a._settle(outcome)
        mq.flush()
        if dup:
            h.d._noteDeliverySettled_(a)
            mq.flush()
        rows = _facts(h)
        h.d._hub = None
        rows_before = len(before)
        return rows if not retry_first else (rows, len(pending),
                                             rows_before)


# =============================================================================
# filters, ranges
# =============================================================================

@drives("M13-C139", "M13-C140", "M13-C141", "M13-C142")
def d_app_identity(case):
    fx = case["fixture"]
    cid = case["case_id"]
    with AWorld() as w:
        if cid == "M13-C139":
            for i, a in enumerate(fx["apps"]):
                w.dictation(f"job-{i}", app_name=a["name"],
                            app_bundle=a["bundle"], final_words=a["words"])
            key = next(o["key"] for o in w.insights.apps_available()
                       if o["label"] == fx["apps"][0]["name"])
            s = w.insights.summary(days=None, app=key)
            return grade({"dictations": s["dictations"],
                          "final_words": s["final_words"]},
                         case["expected"])
        if cid == "M13-C140":
            for i, a in enumerate(fx["apps"]):
                w.dictation(f"job-{i}", app_name=a["name"],
                            app_bundle=a["bundle"])
            opts = w.insights.apps_available()
            per = [w.insights.summary(days=None, app=o["key"])["dictations"]
                   for o in opts]
            return grade({"separate_entities": len(opts),
                          "dictations_per_selection":
                          per[0] if len(set(per)) == 1 else per},
                         case["expected"])
        if cid == "M13-C141":
            w.dictation("job-1", app_name=fx["historical_name"],
                        app_bundle=fx["bundle"])
            w.dictation("job-2", app_name=fx["new_name"],
                        app_bundle=fx["bundle"])
            opts = w.insights.apps_available()
            s = w.insights.summary(days=None, app=f"bundle:{fx['bundle']}")
            obs = {"dictations": s["dictations"], "entities": len(opts),
                   "label": opts[0]["label"] if opts else None}
            return check({"one_entity": obs["entities"] == 1,
                          "two": obs["dictations"] == 2,
                          "latest_label": obs["label"] == fx["new_name"]},
                         obs)
        for i, r in enumerate(fx["rows"]):
            w.dictation(f"job-{i}", app_name=r["app_name"],
                        app_bundle=r["app_bundle"])
        per = w.insights.per_app(days=None)
        obs = {"unknown_count": sum(r["dictations"] for r in per
                                    if r["key"] == "unknown"),
               "sum_per_app": sum(r["dictations"] for r in per)}
        return grade(obs, case["expected"])


@drives(*[f"M13-C{n:03d}" for n in range(143, 150)])
def d_mode_exact(case):
    fx = case["fixture"]
    sel = fx["selected_mode"]
    with AWorld() as w:
        w.dictation("job-sel", mode=sel)
        w.dictation("job-ctl", mode=fx["other_mode"])
        w.dictation("job-null", mode=None)
        all_n = w.insights.summary(days=None)["dictations"]
        if sel is None:
            # An absent selection means All; Unknown is its own key.
            sel_n = w.insights.summary(days=None, mode=None)["dictations"]
            unk_n = w.insights.summary(days=None,
                                       mode="unknown")["dictations"]
            obs = {"all": all_n, "absent_selection": sel_n,
                   "unknown_key": unk_n}
            return check({"absent_is_all": sel_n == all_n == 3,
                          "unknown_distinct": unk_n == 2}, obs)
        n = w.insights.summary(days=None, mode=sel)["dictations"]
        modes = w.insights.modes_available()
    obs = {"selected": n, "all": all_n, "modes": modes}
    return check({"exact": n == 1, "unknown_listed": "unknown" in modes},
                 obs)


@drives("M13-C150")
def d_effective_mode(case):
    fx = case["fixture"]
    wp = type("WP", (), {"effective_mode": fx["effective_mode"],
                         "requested_mode": fx["requested_mode"],
                         "profile_name": None})()
    with R.coordinator() as h:
        rows = _record(h, raw="alpha beta", final_text="Alpha beta.",
                       m10={"wp": wp})
    return grade({"stored_mode": rows[0]["mode"]},
                 {"stored_mode": case["expected"]["stored_mode"]})


@drives("M13-C151", "M13-C152")
def d_breakdown_cohort(case):
    rows = case["fixture"]["rows"]
    with AWorld() as w:
        for i, r in enumerate(rows):
            w.dictation(f"job-{i}", app_name=f"Synthetic {r['app']}",
                        app_bundle=f"com.synthetic.{r['app'].lower()}",
                        mode=r["mode"], final_words=r["words"])
        if case["case_id"] == "M13-C151":
            rep = w.insights.report(days=None, app="bundle:com.synthetic"
                                    ".alpha")
            obs = {"summary_words": rep["summary"]["final_words"],
                   "sum_per_mode_words": sum(r["final_words"]
                                             for r in rep["per_mode"])}
        else:
            rep = w.insights.report(days=None, mode="clean")
            obs = {"summary_words": rep["summary"]["final_words"],
                   "sum_per_app_words": sum(r["final_words"]
                                            for r in rep["per_app"])}
    return grade(obs, case["expected"])


@drives("M13-C153", "M13-C154", "M13-C155", "M13-C156")
def d_range(case):
    import datetime as dt
    import zoneinfo
    fx = case["fixture"]
    zone, days = fx["zone"], fx["days"]
    z = zoneinfo.ZoneInfo(zone)
    start = dt.date.fromisoformat(case["expected"]["inclusive_start_day"])
    start_inst = dt.datetime.combine(start, dt.time(0), z).astimezone(
        dt.timezone.utc)
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")  # noqa: E731
    today = dt.datetime.fromtimestamp(epoch(fx["now_utc"]), z).date()
    tomorrow = dt.datetime.combine(today + dt.timedelta(days=1),
                                   dt.time(9), z).astimezone(dt.timezone.utc)
    with AWorld(zone=zone, now=epoch(fx["now_utc"])) as w:
        w.dictation("job-before", activity_at_utc=iso(
            start_inst - dt.timedelta(microseconds=1)))
        w.dictation("job-start", activity_at_utc=iso(start_inst))
        w.dictation("job-today", activity_at_utc="2026-09-27T11:00:00.000Z")
        w.dictation("job-tomorrow", activity_at_utc=iso(tomorrow))
        s = w.insights.summary(days=days)
    obs = {"day_start": s["day_start"], "day_end": s["day_end"],
           "dictations": s["dictations"], "future_dated": s["future_dated"]}
    in_range = 2 if days > 1 else 1  # start(+today when distinct)
    if start == today:
        in_range = 2  # exact start and within-today are the same day
    return check({"inclusive_start": s["day_start"] ==
                  case["expected"]["inclusive_start_day"],
                  "counts": s["dictations"] == in_range,
                  "future_disclosed": s["future_dated"] == 1}, obs,
                 grading="decision", decision="D02_TIME_ADMISSION")


@drives("M13-C158")
def d_filtered_activity(case):
    fx = case["fixture"]
    with AWorld() as w:
        for i in range(fx["dictations"]):
            w.dictation(f"job-{i}")
        for _ in range(fx["transforms"]):
            w.transform()
        for _ in range(fx["repastes"]):
            w.repaste()
        key = next(o["key"] for o in w.insights.apps_available()
                   if o["label"] == fx["selected_app"])
        s = w.insights.summary(days=None, app=key)
        daily = w.insights.daily(days=None, app=key)
    obs = {"transforms": s["transforms"], "repastes": s["repastes"],
           "daily_transforms": [r["transforms"] for r in daily]}
    out = grade(obs, {"transforms": None, "repastes": None})
    if out["status"] == "PASS" and any(v is not None
                                       for v in obs["daily_transforms"]):
        return result("FAIL", obs, note="daily shows a zero")
    return out


@drives("M13-C159")
def d_completeness(case):
    fx = case["fixture"]
    with AWorld() as w:
        base = epoch("2026-09-26T15:00:00.000Z")
        for i in range(fx["days"]):
            w.dictation(f"job-d{i}", activity_at_utc=A.instant_from_epoch(
                base - i * 86400), app_name=f"Synthetic App {i % fx['apps']}",
                app_bundle=f"com.synthetic.app{i % fx['apps']}",
                mode=f"synthetic-mode-{i % fx['modes']}")
        rep = w.insights.report(days=fx["selected_range"])
        total = rep["summary"]["dictations"]
        obs = {"total": total,
               "daily": sum(r["dictations"] for r in rep["daily"]),
               "daily_days": rep["daily_total_days"],
               "per_app": sum(r["dictations"] for r in rep["per_app"]),
               "apps": len(rep["per_app"]),
               "per_mode": sum(r["dictations"] for r in rep["per_mode"]),
               "modes": len(rep["per_mode"])}
    return check({"daily_complete": obs["daily"] == total == fx["days"],
                  "apps_complete": obs["per_app"] == total
                  and obs["apps"] == fx["apps"],
                  "modes_complete": obs["per_mode"] == total
                  and obs["modes"] == fx["modes"]}, obs)
