"""M13 corpus drivers, part two (retention, deletion, pruning, legacy,
Undated, readiness, the M12 note seam, the M14 seam, Hub concurrency,
privacy, benchmark validity). See m13_drivers for the result contract.

Native cases (C157 native half, C186, C237, C238, C262) are graded from
the owned-native suite's record (``native_record``), never from a
headless fake; a missing record leaves them NOT_RUN.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

import m13_world as W
import test_m13_remediation as R
from m13_drivers import (DRIVERS, _facts, _note_settlement, check,  # noqa
                         drives, grade, result)
from m13_world import APP_CANARY, AWorld, MainQueue, epoch

from localflow import config as config_mod
from localflow.v2 import analytics as A
from localflow.v2.ui import state as state_mod

ROOT = W.ROOT
NATIVE = {"record": None}


# =============================================================================
# retention (D03)
# =============================================================================

def _raw(value):
    return json.dumps(value)


@drives(*[f"M13-C{n:03d}" for n in range(160, 171)])
def d_retention_primitive(case):
    """The config file, the public command and the native field's text,
    each through its own validator, against the adopted domain: "keep"
    or whole days 1..36500 (integral JSON floats kept for the config
    file's compatibility; the UI text accepts "keep" or digits)."""
    value = case["fixture"]["value"]
    days_cfg, problems = config_mod.retention_policy(
        {"retention_usage_days": value})
    cfg_ok = not problems
    with R.coordinator() as h:
        h.d.store.retention_days["usage"] = 365
        h.d.cfg["retention_usage_days"] = 365
        cmd = h.d.hubApplyUsageRetention(value)
        after_cmd = h.d.store.retention_days["usage"]
        h.d.store.retention_days["usage"] = 365
        text = value if isinstance(value, str) else (
            json.dumps(value) if not isinstance(value, float)
            else repr(value))
        native = h.d.hubApplyUsageRetention(str(text))
        after_native = h.d.store.retention_days["usage"]
    valid_int = (isinstance(value, int) and not isinstance(value, bool)
                 and 1 <= value <= 36500) or (
        isinstance(value, float) and value.is_integer()
        and 1 <= value <= 36500)
    obs = {"config": {"ok": cfg_ok, "usage": days_cfg["usage"]},
           "command": {"outcome": cmd.get("outcome"), "policy": after_cmd},
           "native_text": {"text": str(text),
                           "outcome": native.get("outcome"),
                           "policy": after_native}}
    if valid_int:
        want = int(value)
        ok = cfg_ok and days_cfg["usage"] == want and \
            cmd["outcome"] == "saved" and after_cmd == want
        if isinstance(value, float):
            ok = ok and native["outcome"] == "refused" and \
                after_native == 365
        else:
            ok = ok and native["outcome"] == "saved" and \
                after_native == want
    elif value == "365":
        # A string is not a config-file day count; UI text is.
        ok = not cfg_ok and days_cfg["usage"] is None and \
            cmd["outcome"] == "saved" and after_cmd == 365
    else:
        ok = not cfg_ok and days_cfg["usage"] is None and \
            cmd["outcome"] == "refused" and after_cmd == 365 and \
            native["outcome"] == "refused" and after_native == 365
    return result("PASS" if ok else "FAIL", obs, grading="decision",
                  decision="D03_RETENTION")


def _content_job(s, age_days, now):
    jid, _f = s.create_job(captured_at_utc=A.instant_from_epoch(
        now - age_days * 86400)[:23] + "Z",
        time_quality="known", state="insertion_confirmed")
    aid = s.write_text_artifact(job_id=jid, stage="asr",
                                role="raw_transcript",
                                text="SYNTHETIC_TRANSCRIPT_TEXT",
                                retention_class="transcript")
    old = A.instant_from_epoch(now - age_days * 86400)[:23] + "Z"
    s.submit(lambda c: c.execute(
        "UPDATE artifacts SET created_at_utc=? WHERE artifact_id=?",
        (old, aid)))
    s.submit(lambda c: c.execute(
        "UPDATE jobs SET updated_at_utc=? WHERE job_id=?", (old, jid)))
    return jid, aid


@drives("M13-C171", "M13-C172")
def d_retention_independence(case):
    fx = case["fixture"]
    with AWorld() as w:
        s = w.store
        now = W.CLOCK
        s.retention_days["transcript"] = fx["content_days"]
        s.retention_days["usage"] = fx["usage_days"]
        jid, aid = _content_job(s, fx["age_days"], now)
        w.dictation(jid, activity_at_utc=A.instant_from_epoch(
            now - fx["age_days"] * 86400))
        aggs_before = w.aggs()
        s.prune(now=now)
        w.analytics.expire_usage(now=now)
        purged = s.submit(lambda c: c.execute(
            "SELECT purged FROM artifacts WHERE artifact_id=?",
            (aid,)).fetchone()[0])
        rows = w.rows()
        obs = {"content_purged": bool(purged), "facts": len(rows),
               "aggregates_unchanged": w.aggs() == aggs_before}
    if case["case_id"] == "M13-C171":
        return check({"content_purged": obs["content_purged"],
                      "usage_kept": obs["facts"] == 1
                      and obs["aggregates_unchanged"]}, obs)
    return check({"content_kept": not obs["content_purged"],
                  "usage_removed": obs["facts"] == 0}, obs)


@drives("M13-C173")
def d_retention_dst(case):
    fx = case["fixture"]
    with AWorld(zone="America/New_York", now=epoch(fx["now_utc"])) as w:
        w.store.retention_days["usage"] = fx["days"]
        w.dictation("job-boundary", activity_at_utc=fx["boundary_utc"])
        w.dictation("job-earlier", activity_at_utc=A.instant_from_epoch(
            epoch(fx["boundary_utc"]) - 1e-6))
        w.analytics.expire_usage()
        left = sorted(r["job_id"] for r in w.rows())
    return check({"exact_boundary_kept": left == ["job-boundary"]},
                 {"left": left})


@drives("M13-C174")
def d_retention_rollback(case):
    with AWorld() as w:
        w.store.retention_days["usage"] = 30
        w.dictation("job-old", activity_at_utc="2026-06-01T10:00:00.000Z")
        w.dictation("job-new")
        before_rows, before_aggs = w.rows(), w.aggs()
        # The fault fires after the expired facts were deleted, while the
        # emptied day's aggregate is being removed (before the commit).
        w.store.submit(lambda c: c.execute(
            "CREATE TRIGGER inject_fault BEFORE DELETE ON daily_aggregates"
            " BEGIN SELECT RAISE(ABORT, 'injected'); END"))
        raised = False
        try:
            w.analytics.expire_usage()
        except Exception:
            raised = True
        w.store.submit(lambda c: c.execute("DROP TRIGGER inject_fault"))
        obs = {"raised": raised, "rows_same": w.rows() == before_rows,
               "aggs_same": w.aggs() == before_aggs}
    return check(obs, obs)


@drives("M13-C175")
def d_write_fails(case):
    return _bind("f11_failed_save_changes_nothing")


@drives("M13-C176")
def d_apply_vs_expiry(case):
    return _bind("f11_apply_saves_and_previews_without_deleting")


@drives("M13-C264")
def d_until_cleared(case):
    fx = case["fixture"]
    days, _p = config_mod.retention_policy({})
    with AWorld() as w:
        w.store.retention_days["usage"] = days["usage"]
        w.dictation("job-old", activity_at_utc=A.instant_from_epoch(
            W.CLOCK - fx["older_usage_days"] * 86400))
        out = w.analytics.expire_usage()
        kept = len(w.rows())
    with R.coordinator() as h:
        info = h.d.hubUsageInfo()
    decisions = json.loads((ROOT / "docs/v2/acceptance/M13/remediation/"
                            "decisions.json").read_text())
    contract = (ROOT / "docs/v2/contracts/analytics.md").read_text()
    obs = {"default": days["usage"], "expiry": out, "kept": kept,
           "ui_value": info["usage_retention_days"],
           "decision": decisions["decisions"]["D03_RETENTION"]["chosen"]
           [:40]}
    return check({"keep_default": days["usage"] is None,
                  "old_fact_kept": kept == 1,
                  "ui_says_keep": info["usage_retention_days"] == "keep",
                  "documented": "until" in contract.lower()
                  and "keep" in contract.lower()}, obs,
                 grading="decision", decision="D03_RETENTION")


def _bind(name):
    fn = next(f for f in R.CASES if f.__name__ == name)
    try:
        fn()
        return result("PASS", {"regression": name},
                      witness={"bound_to": name})
    except AssertionError as e:
        return result("FAIL", {"regression": name}, note=str(e)[:400])


# =============================================================================
# deletion
# =============================================================================

@drives("M13-C177")
def d_delete_job_scope(case):
    fx = case["fixture"]
    with AWorld() as w:
        w.dictation("job-a", transform_id="builtin:polish",
                    transform_path="applied")
        for _ in range(fx["job_a"]["repastes"]):
            w.repaste(job_id="job-a")
        w.dictation("job-b", activity_at_utc="2026-09-25T10:00:00.000Z")
        for _ in range(fx["job_b"]["repastes"]):
            w.repaste(job_id="job-b", at="2026-09-25T11:00:00.000Z")
        for _ in range(fx["independent_explicit_transforms"]):
            w.transform()
        w.analytics.delete_usage_for_job("job-a")
        rows = w.rows()
        obs = {"a": sum(r["job_id"] == "job-a" for r in rows),
               "b": sum(r["job_id"] == "job-b" for r in rows),
               "transforms": sum(r["kind"] == "transform" for r in rows),
               "mismatches": w.mismatches()}
    return check({"a_gone": obs["a"] == 0,
                  "b_kept": obs["b"] == 1 + fx["job_b"]["repastes"],
                  "transform_kept": obs["transforms"] == 1,
                  "days_recomputed": not obs["mismatches"]}, obs)


def _content_digest(s):
    return s.submit(lambda c: {
        t: [tuple(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY"
                                        " rowid").fetchall()]
        for t in ("jobs", "artifacts", "training_examples",
                  "training_revisions", "notes", "note_revisions")})


@drives("M13-C178")
def d_delete_all_independent(case):
    sys.path.insert(0, str(ROOT / "tests" / "v2" / "ui"))
    from test_training_data import Env
    from localflow.v2.notes import NoteStore
    with Env() as e:
        a = A.AnalyticsStore(e.store, reporting_timezone="UTC")
        e.add_example()
        e.add_example()
        NoteStore(e.store).create_note(title="Synthetic",
                                       content="SYNTHETIC_NOTE_TEXT")
        for i in range(4):
            a.record_dictation_fact(
                job_id=f"job-u{i}",
                activity_at_utc="2026-09-26T15:00:00.000Z", final_words=3,
                insertion_outcome="confirmed")
        before = _content_digest(e.store)
        a.delete_all_usage()
        after = _content_digest(e.store)
        left = e.store.submit(lambda c: (
            c.execute("SELECT COUNT(*) FROM usage_facts").fetchone()[0],
            c.execute("SELECT COUNT(*) FROM daily_aggregates"
                      ).fetchone()[0]))
    obs = {"usage_left": left, "content_same": before == after}
    return check({"usage_zero": left == (0, 0),
                  "content_unchanged": before == after}, obs)


@drives("M13-C179", "M13-C180", "M13-C227")
def d_profile_copies(case):
    from localflow.v2.profile import ProfileService
    n = case["fixture"].get("snapshot_count") or \
        case["fixture"].get("snapshots") or 1
    sys.path.insert(0, str(ROOT / "tests" / "v2" / "ui"))
    from test_training_data import Env
    with Env() as e:
        a = A.AnalyticsStore(e.store, reporting_timezone="UTC")
        ex = [e.add_example(raw=f"synthetic speech sample {i} words here")
              for i in range(case["fixture"].get("retained_examples", 0))]
        a.record_dictation_fact(
            job_id="job-canary", activity_at_utc="2026-09-26T15:00:00.000Z",
            final_words=4, insertion_outcome="confirmed",
            app_name=APP_CANARY, mode="synthetic-mode",
            utc_offset_minutes=-240)
        prof = ProfileService(e.store, min_words=1)
        for _ in range(n):
            prof.compute()
        speech_before = e.store.submit(lambda c: [json.loads(r[0]).get(
            "eligible_words") for r in c.execute(
            "SELECT measured_json FROM profile_snapshots").fetchall()])
        a.delete_all_usage()
        snaps = e.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT measured_json FROM profile_snapshots").fetchall()])
        speech_after = [json.loads(s).get("eligible_words") for s in snaps]
        current = json.dumps(prof.current())
        live = e.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM training_examples WHERE state IN"
            " ('captured_unreviewed','annotated')").fetchone()[0])
    obs = {"snapshots": len(snaps),
           "with_canary": sum(APP_CANARY in s for s in snaps),
           "speech_fields_kept": speech_before == speech_after,
           "live_examples": live, "examples_seeded": len(ex)}
    return check({"n_snapshots": obs["snapshots"] == n,
                  "no_copies": obs["with_canary"] == 0
                  and APP_CANARY not in current,
                  "speech_kept": obs["speech_fields_kept"],
                  "evidence_kept": live == len(ex)}, obs)


@drives("M13-C181")
def d_delete_after_content(case):
    with R.coordinator() as h:
        jid, _f = h.d.store.create_job(
            captured_at_utc="2026-09-26T15:00:00.000Z",
            time_quality="known", state="insertion_confirmed")
        h.d._analytics.record_dictation_fact(
            job_id=jid, activity_at_utc="2026-09-26T15:00:00.000Z",
            final_words=3, insertion_outcome="confirmed")
        h.d.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1 WHERE job_id=?", (jid,)))
        before = len(_facts(h))
        out = h.d.hubDeleteUsageForJob(jid)
        after = len(_facts(h))
    obs = {"before": before, "after": after, "outcome": out.get("outcome")}
    return check({"deletable": out.get("outcome") == "deleted"
                  and before == 1 and after == 0}, obs)


@drives("M13-C182")
def d_delete_all_timeout(case):
    return _bind("f09_timed_out_delete_is_unknown_then_reconciled")


@drives("M13-C183")
def d_delete_one_timeout(case):
    with R.coordinator() as h, MainQueue() as mq:
        R.seed_facts(h, 2)
        R.make_hub(h)
        real_submit = h.d.store.submit
        release, parked = threading.Event(), threading.Event()

        def park(_c):
            parked.set()
            release.wait(30)
        real_submit(park, wait=False)
        parked.wait(10)
        h.d._usage_op_timeout = 0.3
        try:
            out = h.d.hubDeleteUsageForJob("job-seed0")
        finally:
            release.set()
        h.d.store.sync()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and \
                out.get("op_id") not in h.d._usage_reconciled:
            mq.flush()
            time.sleep(0.02)
        rec = h.d._usage_reconciled.get(out.get("op_id"))
        left = h.d._insights.summary(days=None)["dictations"]
    obs = {"first": out.get("outcome"), "reconciled": rec, "left": left}
    return check({"unknown_first": obs["first"] == "outcome_unknown",
                  "committed_later": rec == "committed",
                  "one_left": left == 1}, obs,
                 witness={"barrier": "writer parked; caller wait timed"
                          " out after admission"})


@drives("M13-C184")
def d_delete_all_rollback(case):
    with R.coordinator() as h, MainQueue() as mq:
        R.seed_facts(h, 2)
        hub = R.make_hub(h)
        hub.state.set_insights_filters(range_days=None)
        hub.state.select_view("insights")
        hub.state.wait_for_queries(15)
        before = _facts(h)
        h.d.store.submit(lambda c: c.execute(
            "CREATE TRIGGER inject_fault BEFORE DELETE ON usage_facts"
            " BEGIN SELECT RAISE(ABORT, 'injected'); END"))
        out = h.d.hubDeleteAllUsage()
        h.d.store.submit(lambda c: c.execute("DROP TRIGGER inject_fault"))
        after = _facts(h)
        mq.drain(hub.state)
        hub.state.reload_insights()
        hub.state.wait_for_queries(15)
        shown = hub.state.views["insights"]["data"]["summary"]["dictations"]
    obs = {"outcome": out.get("outcome"), "unchanged": before == after,
           "fresh_read": shown}
    return check({"failed_truthfully": obs["outcome"] == "failed",
                  "db_unchanged": obs["unchanged"], "fresh": shown == 2},
                 obs)


@drives("M13-C185")
def d_delete_during_profile(case):
    """Barrier: the profile read its evidence (and the usage signature)
    before the deletion; its final write op runs after it. The write op
    reads usage inside itself, so no deleted copy is published."""
    from localflow.v2.profile import ProfileService
    with AWorld() as w:
        w.dictation("job-canary", app_name=APP_CANARY)
        prof = ProfileService(w.store, min_words=1)
        gate = W.Latch("profile_after_read")
        real = prof._eligible

        def held(labels):
            out = real(labels)
            gate.hit()
            return out
        prof._eligible = held
        box = {}
        t = threading.Thread(target=lambda: box.setdefault(
            "out", prof.compute()))
        t.start()
        assert gate.reached.wait(10)
        w.analytics.delete_all_usage()
        gate.release()
        t.join(15)
        snaps = w.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT measured_json FROM profile_snapshots").fetchall()])
    obs = {"snapshots": len(snaps),
           "with_canary": sum(APP_CANARY in s for s in snaps)}
    return check({"written": obs["snapshots"] == 1,
                  "no_stale_copy": obs["with_canary"] == 0}, obs,
                 witness={"barrier": gate.name, "reached": True})


# =============================================================================
# metadata pruning (D07)
# =============================================================================

def _aged_job(s, state, days_ago, now):
    at = A.instant_from_epoch(now - days_ago * 86400)[:23] + "Z"
    jid, _f = s.create_job(captured_at_utc=at, time_quality="known",
                           state=state)
    s.submit(lambda c: c.execute(
        "UPDATE jobs SET updated_at_utc=? WHERE job_id=?", (at, jid)))
    return jid, at


@drives(*[f"M13-C{n:03d}" for n in range(187, 195)])
def d_pruning(case):
    fx = case["fixture"]
    cid = case["case_id"]
    now = W.CLOCK
    with AWorld(now=now) as w:
        s = w.store
        s.retention_days.update({"metadata": fx.get("metadata_days", 14),
                                 "audio_failed": fx.get(
                                     "audio_failed_days", 30)})
        journal = w.tmp / "journal"
        journal.mkdir()
        s.register_job_payload_dir(journal, lambda j: f"job-{j}.*")
        state = fx.get("state", "insertion_confirmed")
        jid, at = _aged_job(s, state, fx.get("age_days", 60), now)
        w.dictation(jid, activity_at_utc=at)
        protected = ()
        if fx.get("registered_journal"):
            (journal / f"job-{jid}.wav").write_bytes(b"RIFF-synthetic")
        if fx.get("unpurged_artifacts"):
            s.write_text_artifact(job_id=jid, stage="asr",
                                  role="raw_transcript", text="synthetic",
                                  retention_class="transcript")
        if fx.get("example_state"):
            ex = s.upsert_example(job_id=jid, family_id="fam-x")
            s.submit(lambda c: c.execute(
                "UPDATE training_examples SET state=? WHERE example_id=?",
                (fx["example_state"], ex)))
        if cid == "M13-C193":
            state = "failed_recoverable"
            s.submit(lambda c: c.execute(
                "UPDATE jobs SET state='failed_recoverable', updated_at_utc"
                "='2026-01-01T00:00:00.000Z' WHERE job_id=?", (jid,)))
            protected = (jid,)
        if cid in ("M13-C192", "M13-C194"):
            from localflow.v2.notes import NoteStore
            ns = NoteStore(s)
            note = ns.create_note(title="Synthetic", content="")
            nid = note["note_id"] if isinstance(note, dict) else note
            s.submit(lambda c: c.execute(
                "UPDATE note_revisions SET source_job_id=? WHERE"
                " note_id=?", (jid, nid)))
            if cid == "M13-C194":
                ns.delete_note(nid)
        s.prune_metadata(now=now, protected_job_ids=protected)
        kept = s.job(jid) is not None
        facts = len(w.rows())
    obs = {"job_kept": kept, "usage_facts": facts, "state": state}
    keep = cid in ("M13-C187", "M13-C188", "M13-C189", "M13-C190",
                   "M13-C193")
    if cid in ("M13-C191", "M13-C192", "M13-C194"):
        keep = False  # D07: note provenance is not a pin
    return result("PASS" if (kept == keep and facts == 1) else "FAIL",
                  obs, grading="decision" if cid in ("M13-C192",
                                                     "M13-C194")
                  else "semantic",
                  decision="D07_METADATA_LIVENESS")


# =============================================================================
# legacy and Undated
# =============================================================================

@drives("M13-C195", "M13-C196")
def d_legacy_manifest(case):
    return _bind("f28_legacy_manifest_is_exact")


@drives("M13-C197")
def d_legacy_wpm(case):
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import test_usage_store as tus
    with AWorld() as w:
        tus.seeded_legacy_rows(w.store)
        s = w.insights.summary(days=None)
        leg = w.insights.legacy_summary()
    obs = {"v2_wpm": s["wpm"], "v2_dictations": s["dictations"],
           "legacy_keys": sorted(leg)}
    return check({"not_in_v2": s["wpm"] is None and s["dictations"] == 0,
                  "legacy_labeled": "legacy_fixed_words" in leg
                  and "wpm" not in leg}, obs)


@drives("M13-C198")
def d_legacy_delete(case):
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import test_usage_store as tus
    with AWorld() as w:
        rows = tus.seeded_legacy_rows(w.store)
        w.dictation("job-a")
        w.dictation("job-b")
        w.analytics.delete_all_usage()
        same = tus.legacy_tuples(w.store) == tus.expected_legacy_tuples(
            rows)
    return check({"legacy_unchanged": same}, {"legacy_unchanged": same})


@drives("M13-C199")
def d_legacy_repaste(case):
    with R.coordinator() as h, MainQueue() as mq:
        w, svc = R.real_insertion(h)
        w.fields["F1"].text = ""
        before = h.d._insights.summary(days=None)
        from m13_drivers import _run_repaste
        _out, ran = _run_repaste(h, svc, lambda: h.d.hubPasteText(
            "synthetic legacy words", job_id="legacy-db:1"))
        mq.flush()
        rows = h.d.store.submit(lambda c: c.execute(
            "SELECT job_id, kind FROM usage_facts").fetchall())
        s = h.d._insights.summary(days=None)
    obs = {"rows": rows, "dictations": s["dictations"],
           "words_delta": s["final_words"] - before["final_words"]}
    return check({"transaction": bool(ran and ran[0] is not None),
                  "one_repaste": rows == [("legacy-db:1", "repaste")],
                  "no_dictation": s["dictations"] == 0}, obs)


@drives("M13-C200", "M13-C201", "M13-C202", "M13-C203")
def d_undated(case):
    fx = case["fixture"]
    with AWorld(zone="America/New_York") as w:
        for i in range(fx["legacy_unknown_date_pairs"]):
            jid, _f = w.store.create_job(job_id=f"legacy-log:{i}",
                                         kind="legacy_log",
                                         time_quality="unknown",
                                         state="insertion_confirmed")
            w.store.write_text_artifact(
                job_id=jid, stage="legacy_log", role="cleaned_transcript",
                text=f"synthetic undated {i}", retention_class="legacy")
        w.dictation("job-dated", activity_at_utc="2026-09-27T11:00:00.000Z")
        w.dictation("job-bad", activity_at_utc="not-a-timestamp")
        scope = fx["scope"]
        days = {"Today service range": 1, "7 days": 7, "30 days": 30,
                "daily table": None}[scope]
        s = w.insights.summary(days=days)
        daily = w.insights.daily(days=days)
        undated = w.insights.undated_count()
    obs = {"undated_count": undated, "dated": s["dictations"],
           "daily_rows": sum(r["dictations"] for r in daily)}
    out = grade(obs, {"undated_count": case["expected"]["undated_count"]})
    if out["status"] == "PASS" and not (obs["dated"] == 1
                                        and obs["daily_rows"] == 1):
        return result("FAIL", obs, note="undated entered a dated view")
    return out


# =============================================================================
# readiness (D12)
# =============================================================================

def _env(now=None):
    sys.path.insert(0, str(ROOT / "tests" / "v2" / "ui"))
    from test_training_data import Env
    return Env(now_fn=(lambda: now) if now else None)


def _env_of(e, ex):
    return e.store.submit(lambda c: json.loads(c.execute(
        "SELECT envelope_json FROM training_revisions WHERE example_id=?"
        " ORDER BY rowid DESC LIMIT 1", (ex,)).fetchone()[0]))


def _ready(e):
    return e.svc.readiness()


@drives("M13-C204")
def d_ready_partition(case):
    return _bind("f13_excluded_failure_is_one_class")


@drives("M13-C205")
def d_ready_completeness(case):
    with _env() as e:
        a, b, c = e.add_example(), e.add_example(), e.add_example()
        e.svc.exclude(b)
        e.store.submit(lambda conn: conn.execute(
            "UPDATE training_examples SET state='expired' WHERE"
            " example_id=?", (c,)))
        cc = _ready(e)["readiness_metrics"]["capture_completeness"]
    obs = {"complete": cc["complete"], "denominator": cc["denominator"],
           "ratio": cc["complete"] / cc["denominator"]
           if cc["denominator"] else None}
    del a
    return grade(obs, case["expected"])


@drives("M13-C206")
def d_ready_missing_family(case):
    with _env() as e:
        e.add_example()
        ex2 = e.add_example()
        env = _env_of(e, ex2)
        env["artifact_ids"]["applied_output"] = None
        env.get("missing_reasons", {}).pop("applied_output", None)
        e.store.submit(lambda conn: conn.execute(
            "UPDATE training_revisions SET envelope_json=? WHERE rowid="
            "(SELECT MAX(rowid) FROM training_revisions WHERE"
            " example_id=?)", (json.dumps(env), ex2)))
        cc = _ready(e)["readiness_metrics"]["capture_completeness"]
    obs = {"complete": cc["complete"], "denominator": cc["denominator"]}
    return check({"denominator_explicit": cc["denominator"] == 2,
                  "missing_counts_incomplete": cc["complete"] == 1}, obs)


@drives("M13-C207")
def d_ready_deleted(case):
    with _env() as e:
        ex = e.add_example()
        e.svc.set_verbatim(ex, "synthetic verbatim", listened_audio=True)
        e.svc.delete_everywhere(ex)
        m = _ready(e)["readiness_metrics"]
    obs = {"eligible_asr": m["task_eligibility"]["asr_supervised"]["count"],
           "reviewed_eligible_seconds":
           m["verbatim_reference_coverage"]["reviewed_seconds"]}
    return grade(obs, {"eligible_asr": 0, "reviewed_eligible_seconds": 0.0})


@drives("M13-C208", "M13-C210", "M13-C211")
def d_ready_audio(case):
    cid = case["case_id"]
    with _env() as e:
        ex = e.add_example()
        e.svc.set_verbatim(ex, "synthetic verbatim", listened_audio=True)
        env = _env_of(e, ex)
        aid = env["artifact_ids"]["original_audio"]
        if cid == "M13-C208":
            e.store.submit(lambda c: c.execute(
                "UPDATE artifacts SET purged=1 WHERE artifact_id=?",
                (aid,)))
        elif cid == "M13-C210":
            other = e.add_example()
            oaid = _env_of(e, other)["artifact_ids"]["original_audio"]
            env["artifact_ids"]["original_audio"] = oaid
        else:
            env["artifact_ids"]["original_audio"] = \
                env["artifact_ids"]["source_text"]
        if cid != "M13-C208":
            e.store.submit(lambda c: c.execute(
                "UPDATE training_revisions SET envelope_json=? WHERE rowid="
                "(SELECT MAX(rowid) FROM training_revisions WHERE"
                " example_id=?)", (json.dumps(env), ex)))
        m = _ready(e)["readiness_metrics"]
    j = m["exact_audio_join_coverage"]
    asr = m["task_eligibility"]["asr_supervised"]["count"]
    if cid == "M13-C208":
        return grade({"eligible_asr": asr}, case["expected"])
    if cid == "M13-C210":
        # The foreign example's own audio still joins; ours must not.
        return check({"not_joined": j["joined"] == j["denominator"] - 1,
                      "asr_not_eligible": asr == 0},
                     {"join": j, "eligible_asr": asr})
    return grade({"joined_audio": j["joined"]}, case["expected"])


@drives("M13-C209")
def d_ready_dangling(case):
    with _env() as e:
        e.add_example()
        ex = e.add_example()
        env = _env_of(e, ex)
        env["artifact_ids"]["original_audio"] = "art-does-not-exist"
        e.store.submit(lambda c: c.execute(
            "UPDATE training_revisions SET envelope_json=? WHERE rowid="
            "(SELECT MAX(rowid) FROM training_revisions WHERE"
            " example_id=?)", (json.dumps(env), ex)))
        j = _ready(e)["readiness_metrics"]["exact_audio_join_coverage"]
    return grade({"joined": j["joined"], "denominator": j["denominator"]},
                 case["expected"])


@drives("M13-C212")
def d_ready_partial(case):
    with _env() as e:
        ex = e.add_example()
        e.svc.add_span_correction(ex, "source_text", 0, 4, "Synthetic")
        v = _ready(e)["readiness_metrics"]["verbatim_reference_coverage"]
    obs = {"reviewed_seconds": v["reviewed_seconds"],
           "examples": v["examples"]}
    return check({"no_whole_clip_claim": v["reviewed_seconds"] == 0.0
                  and v["examples"] == 0,
                  "seconds_definition_honest": "no audio alignment" in
                  v["seconds_definition"]}, obs)


@drives("M13-C213")
def d_ready_transform(case):
    return _bind("f14_purged_transform_candidate_is_not_eligible")


@drives("M13-C214")
def d_ready_pairs(case):
    with _env() as e:
        jid, _f = e.store.create_job(
            captured_at_utc="2026-09-22T10:00:00.000Z",
            time_quality="known", state="insertion_unverified")
        arts = [e.store.write_text_artifact(
            job_id=jid, stage="transform", role="transform_output",
            text=f"synthetic {i}", retention_class="training")
            for i in range(4)]

        def op(c):
            for i, (task, cid) in enumerate((("synthetic-task-a", "ca"),
                                             ("synthetic-task-b", "cb"))):
                c.execute(
                    "INSERT INTO transform_candidates(candidate_id,"
                    " task_key, task_kind, transform_id, transform_revision,"
                    " prompt_revision, source_sha256, instructions_sha256,"
                    " source_artifact_id, output_artifact_id, path,"
                    " created_at_utc) VALUES(?,?,'transform_selection',"
                    "'builtin:polish',1,'p','s','i',?,?,'applied',"
                    "'2026-09-22T10:00:00.000Z')",
                    (cid, task, arts[2 * i], arts[2 * i + 1]))
            c.execute(
                "INSERT INTO preference_observations(observation_id,"
                " task_key, candidate_id, candidate_b_id, judgment,"
                " provenance, created_at_utc) VALUES('obs-1',"
                "'synthetic-task-a','ca','cb','prefer_a','review',"
                "'2026-09-22T10:00:00.000Z')")
        e.store.submit(op)
        n = _ready(e)["readiness_metrics"]["task_eligibility"][
            "preference_pairs"]["count"]
    return grade({"eligible_preference_pairs": n}, case["expected"])


@drives("M13-C215")
def d_ready_near_expiry(case):
    return _bind("f24_nearing_expiry_counts_the_live_future_window")


@drives("M13-C216")
def d_ready_quarantine(case):
    with _env() as e:
        ex = e.add_example()
        e.svc.set_verbatim(ex, "synthetic verbatim", listened_audio=True)
        e.svc.mark_intended(ex, True)
        e.store.submit(lambda c: c.execute(
            "UPDATE training_examples SET state='quarantined_sensitive'"
            " WHERE example_id=?", (ex,)))
        r = _ready(e)
    t = r["readiness_metrics"]["task_eligibility"]
    obs = {"eligible_tasks": sum(v["count"] for v in t.values()),
           "stored_as_state": r["examples_by_state"],
           "class_population": r["outcome_balance"]["population"]}
    return check({"no_tasks": obs["eligible_tasks"] == 0,
                  "not_a_class": obs["class_population"] == 0,
                  "storage_counted": r["examples_by_state"].get(
                      "quarantined_sensitive") == 1}, obs)


@drives("M13-C217")
def d_ready_no_inference(case):
    with _env() as e:
        e.add_example()
        r = _ready(e)
    obs = {"population_wer": r["readiness_metrics"]["not_available"][
        "population_wer"], "observed_model_improvement":
        r["observed_model_improvement"]}
    return check({"no_wer": obs["population_wer"] ==
                  "no_references_no_population_claims",
                  "no_improvement": obs["observed_model_improvement"]
                  is None}, obs)


@drives("M13-C218")
def d_ready_activation(case):
    return _bind("f27_readiness_test_runs_from_the_standalone_runner")


@drives("M13-C261")
def d_skill_hits(case):
    return _bind("f16_dictionary_skill_hits_reach_the_fact")


@drives("M13-C263")
def d_negative_counts(case):
    refused, stored = [], []
    for field in case["fixture"]["fields"]:
        with AWorld() as w:
            try:
                if field in ("source_words", "output_words"):
                    w.transform(**{field: case["fixture"]["value"]})
                else:
                    w.dictation("job-a", **{field: case["fixture"]["value"]})
            except ValueError:
                refused.append(field)
                continue
            stored.append((field, [r.get(field) for r in w.rows()]))
    obs = {"refused": refused, "stored": stored}
    return check({"every_negative_refused":
                  sorted(refused) == sorted(case["fixture"]["fields"])},
                 obs)


@drives("M13-C265")
def d_fallback_denominators(case):
    fx = case["fixture"]
    with AWorld() as w:
        for i in range(fx["cleanup_fallback_jobs"]):
            w.dictation(f"job-f{i}", cleanup_path="llm_fallback_normalized",
                        fallback_reason="synthetic_timeout")
        for i in range(fx["raw_or_no_cleanup_jobs"]):
            w.dictation(f"job-r{i}", cleanup_path="raw", mode="raw")
        s = w.insights.summary(days=None)
    obs = {"all_dictation_incidence": s["fallback_rate"],
           "cleanup_requested_rate": s["cleanup_fallback"]["rate"],
           "cleanup_requested": s["cleanup_fallback"]["requested"]}
    return grade(obs, case["expected"], grading="decision",
                 decision="D05_FALLBACK_COHORT")


# =============================================================================
# the M12 note seam (the coordinator's real note branch, real receipts)
# =============================================================================

@drives("M13-C219")
def d_note_committed(case):
    rows = _note_settlement("committed", delay=0.25)
    obs = {"rows": len(rows),
           "outcome": rows[0]["insertion_outcome"] if rows else None,
           "e2e": rows[0]["end_to_end_ms"] if rows else None}
    return check({"one_confirmed": obs["rows"] == 1
                  and obs["outcome"] == "confirmed",
                  "e2e_includes_delay": (obs["e2e"] or 0) >= 250.0}, obs,
                 witness={"barrier": "receipt pending before settlement"})


@drives("M13-C220", "M13-C221")
def d_note_not_confirmed(case):
    outcome = "discarded" if case["case_id"] == "M13-C220" else "failed"
    rows = _note_settlement(outcome)
    meta = json.loads(rows[0]["meta_json"]) if rows else {}
    obs = {"rows": len(rows),
           "outcome": rows[0]["insertion_outcome"] if rows else None,
           "reason": meta.get("reason")}
    return check({"one_saved": obs["rows"] == 1
                  and obs["outcome"] == "saved_not_inserted",
                  "reason": obs["reason"] == ("note_deleted_before_save"
                                              if outcome == "discarded"
                                              else "note_save_failed")},
                 obs)


@drives("M13-C222")
def d_note_retry_pending(case):
    rows, pending, before = _note_settlement("committed", retry_first=True)
    obs = {"before": before, "after_failed_attempt": pending,
           "after_commit": len(rows),
           "outcome": rows[0]["insertion_outcome"] if rows else None}
    return check({"pending_until_final": before == 0 and pending == 0,
                  "counted_once": len(rows) == 1
                  and obs["outcome"] == "confirmed"}, obs)


@drives("M13-C223")
def d_note_duplicate(case):
    rows = _note_settlement("committed", dup=True)
    return check({"one": len(rows) == 1}, {"rows": len(rows)},
                 witness={"barrier": "second settlement after the pop"})


@drives("M13-C224", "M13-C225")
def d_note_revisions(case):
    """One dictated arrival (its job's one usage fact), then typed
    autosaves, explicit snapshots and a restore through the real
    NoteStore — the revision count must grow (witness) while usage
    stays exactly the one logical dictation."""
    from localflow.v2 import notes as N
    fx = case["fixture"]
    with AWorld() as w:
        ns = N.NoteStore(w.store)
        created = ns.create_note("", title="Synthetic")
        nid = created["note_id"]
        words = " ".join(["dictated"] * fx.get("initial_dictation_words",
                                              10))
        first = ns.append_revision(nid, words, origin=N.ORIGIN_DICTATED,
                                   trigger=N.TRIGGER_SYSTEM,
                                   source_job_id="job-note")
        w.dictation("job-note", final_words=len(words.split()))
        before = w.rows()
        text = words
        for i in range(fx.get("typed_edits", 5)):
            text += f" typed{i}"
            ns.append_revision(nid, text, origin=N.ORIGIN_TYPED,
                               trigger=N.TRIGGER_AUTOSAVE)
        for i in range(fx.get("snapshots", 3)):
            ns.append_revision(nid, text, origin=N.ORIGIN_TYPED,
                               trigger=N.TRIGGER_EXPLICIT)
        for _ in range(fx.get("restores", 1)):
            ns.restore(nid, first["revision_id"])
        revisions = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM note_revisions WHERE note_id=?",
            (nid,)).fetchone()[0])
        if case["case_id"] == "M13-C225":
            ns.delete_note(nid)
        after = w.rows()
        s = w.insights.summary(days=None)
    obs = {"revisions_written": revisions, "facts_before": len(before),
           "facts_after": len(after), "dictations": s["dictations"],
           "final_words": s["final_words"]}
    if revisions < 2:
        return result("INVALID", obs, note="no note revisions written")
    return check({"no_new_usage": before == after,
                  "one_dictation": s["dictations"] == 1
                  and s["final_words"] == fx.get(
                      "initial_dictation_words", 10)}, obs,
                 witness={"revisions_written": revisions})


# =============================================================================
# the M14 consumer seam
# =============================================================================

@drives("M13-C226")
def d_m14_separate(case):
    from localflow.v2.profile import ProfileService
    with AWorld() as w:
        for i in range(10):
            w.dictation(f"job-{i}", app_name="Synthetic App")
        out = ProfileService(w.store).compute()
    obs = {"cards": out["cards"], "eligible_words":
           out["measured"]["eligible_words"],
           "usage_source": out["measured"]["sources"]["usage"]}
    return check({"no_interpretation": out["cards"] == []
                  and not out["interpretive_available"],
                  "speech_separate": obs["eligible_words"] == 0}, obs)


@drives("M13-C228", "M13-C229")
def d_m14_signature(case):
    from localflow.v2.profile import ProfileService
    with AWorld() as w:
        w.dictation("job-a", mode="clean")
        prof = ProfileService(w.store, min_words=1)
        prof.compute()
        first = prof.compute(only_if_changed=True)
        if case["case_id"] == "M13-C228":
            w.transform()
        else:
            w.dictation("job-a", mode="polish", attempt=2)
        second = prof.compute(only_if_changed=True)
    obs = {"unchanged_skipped": first.get("skipped"),
           "after_change_skipped": second.get("skipped", False)}
    return check({"idle_skips": first.get("skipped") is True,
                  "change_detected": not second.get("skipped")}, obs)


@drives("M13-C230")
def d_m14_shape(case):
    with _env() as e:
        r = e.svc.readiness()
    with AWorld() as w:
        s = w.insights.summary(days=None)
    obs = {"readiness_revision": r.get("readiness_definition_revision"),
           "wpm_keys": sorted(k for k in s if k.startswith("wpm")),
           "legacy_keys_kept": all(k in r["outcome_balance"] for k in (
               "unreviewed", "verified_positive", "verified_failure",
               "unobserved", "excluded"))}
    return check({"declared": obs["readiness_revision"] == "m13-r1",
                  "additive": obs["legacy_keys_kept"]
                  and "wpm_excluded" in obs["wpm_keys"]}, obs)


# =============================================================================
# Hub concurrency (state/coordinator; native halves from the native record)
# =============================================================================

@drives("M13-C231")
def d_rapid_filters(case):
    """The M09 executor keeps one running and one pending request per
    key; every older publication is refused. The final view holds only
    the newest request's inputs and data."""
    with AWorld() as w:
        R.seed_cohort(w)
        w.dictation("job-beta-raw", app_name="Synthetic Beta",
                    app_bundle="com.synthetic.beta", mode="raw",
                    final_words=7)
        st = R.hub_state(w)
        gate = W.Latch("first_query_running")
        real = w.insights.report

        def slow(*a, **kw):
            if not gate.reached.is_set():
                gate.hit()
            return real(*a, **kw)
        w.insights.report = slow
        try:
            st.select_view("insights")
            assert gate.reached.wait(10)
            for step in (dict(range_days=30), dict(range_days=7),
                         dict(app="bundle:com.synthetic.alpha"),
                         dict(app="bundle:com.synthetic.beta"),
                         dict(mode="raw")):
                st.set_insights_filters(**step)
            # Oldest LAST: the newest request (the executor runs two per
            # key) publishes first; only then is the gated oldest one let
            # go, so its publication must be refused, not overwrite.
            final = {"app": "bundle:com.synthetic.beta", "mode": "raw",
                     "days": 7}
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and (
                    (st.views["insights"].get("data") or {}).get(
                        "summary", {}).get("cohort") != final):
                time.sleep(0.01)
            gate.release()
            st.wait_for_queries(15)
            v = st.views["insights"]
            s = v["data"]["summary"]
        finally:
            w.insights.report = real
            gate.release()
            st.close()
    obs = {"range": v["range"], "app": v["app"], "mode": v["mode"],
           "cohort": s["cohort"], "dictations": s["dictations"]}
    return check({"newest_only": s["cohort"] == {
        "app": "bundle:com.synthetic.beta", "mode": "raw", "days": 7},
        "state_matches": (v["range"], v["app"], v["mode"]) ==
        (7, "bundle:com.synthetic.beta", "raw"),
        "data": s["dictations"] == 1}, obs)


@drives("M13-C232")
def d_hub_delete_all(case):
    return _bind("f08_delete_all_revokes_a_materialized_report")


@drives("M13-C233")
def d_hub_delete_one(case):
    with R.coordinator() as h, MainQueue() as mq:
        R.seed_facts(h, 2)
        hub = R.make_hub(h)
        st = hub.state
        gate = W.Latch("report_materialized")
        real = h.d._insights.report
        armed = {"on": True}

        def held(*a, **kw):
            out = real(*a, **kw)
            if armed["on"]:
                armed["on"] = False
                gate.hit()
            return out
        h.d._insights.report = held
        try:
            st.set_insights_filters(range_days=None)
            st.select_view("insights")
            assert gate.reached.wait(10)
            h.d.hubDeleteUsageForJob("job-seed0")
            gate.release()
            st.wait_for_queries(15)
            mq.drain(st)
            st.wait_for_queries(15)
            data = st.views["insights"]["data"]
        finally:
            h.d._insights.report = real
            gate.release()
    obs = {"shown": data["summary"]["dictations"] if data else None}
    return check({"remaining_only": obs["shown"] == 1}, obs,
                 witness={"barrier": gate.name})


@drives("M13-C234")
def d_hub_retention(case):
    with R.coordinator() as h, MainQueue() as mq:
        old = A.instant_from_epoch(time.time() - 40 * 86400)
        h.d._analytics.record_dictation_fact(
            job_id="job-old", activity_at_utc=old, final_words=3,
            insertion_outcome="confirmed")
        R.seed_facts(h, 1)
        h.d.store.retention_days["usage"] = 30
        hub = R.make_hub(h)
        st = hub.state
        gate = W.Latch("report_materialized")
        real = h.d._insights.report
        armed = {"on": True}

        def held(*a, **kw):
            out = real(*a, **kw)
            if armed["on"]:
                armed["on"] = False
                gate.hit()
            return out
        h.d._insights.report = held
        try:
            st.set_insights_filters(range_days=None)
            st.select_view("insights")
            assert gate.reached.wait(10)
            h.d._retention_pass()
            gate.release()
            st.wait_for_queries(15)
            mq.drain(st)
            st.wait_for_queries(15)
            data = st.views["insights"]["data"]
        finally:
            h.d._insights.report = real
            gate.release()
    obs = {"shown": data["summary"]["dictations"] if data else None}
    return check({"stale_rejected": obs["shown"] == 1}, obs)


@drives("M13-C235")
def d_hub_rebuild(case):
    """A rebuild between a report's admission and its publication: the
    report is one writer op, so it is entirely old-zone or entirely
    new-zone; the label always matches the bucketing."""
    at = "2026-09-27T04:30:00.000Z"
    with AWorld(zone="America/New_York") as w:
        w.dictation("job-a", activity_at_utc=at)
        st = R.hub_state(w)
        gate = W.Latch("report_admitted")
        real = w.insights.report

        def held(*a, **kw):
            gate.hit()
            return real(*a, **kw)
        w.insights.report = held
        try:
            st.set_insights_filters(range_days=None)
            st.select_view("insights")
            assert gate.reached.wait(10)
            w.analytics.rebuild_aggregates(
                reporting_timezone="America/Los_Angeles")
            gate.release()
            st.wait_for_queries(15)
            d = st.views["insights"]["data"]
        finally:
            w.insights.report = real
            gate.release()
            st.close()
    zone = d["summary"]["reporting_timezone"]
    day = d["daily"][0]["day"]
    obs = {"zone": zone, "day": day}
    return check({"coherent": day == W.local_day(at, zone)}, obs)


@drives("M13-C236")
def d_hub_mixed(case):
    return _bind("f07_one_report_is_one_generation")


# =============================================================================
# privacy canaries
# =============================================================================

def _scan(paths, canary):
    hits = []
    for p in paths:
        try:
            if canary in p.read_text(errors="replace"):
                hits.append(str(p))
        except (OSError, IsADirectoryError):
            continue
    return hits


@drives(*[f"M13-C{n:03d}" for n in range(239, 247)])
def d_privacy(case):
    """Production producers run with the canary in the field its type
    belongs to; the canary may appear only on its allowed governed
    surface — never in usage meta_json, content-free events, profile
    snapshots after deletion, or any committed M13 evidence."""
    canary = case["fixture"]["canary"]
    kind = case["fixture"]["canary_type"]
    with R.coordinator() as h, MainQueue() as mq:
        a = h.d._analytics
        if kind == "app metadata":
            a.record_dictation_fact(
                job_id="job-p", activity_at_utc="2026-09-26T15:00:00.000Z",
                app_name=canary, final_words=3,
                insertion_outcome="confirmed")
        elif kind == "profile name":
            a.record_dictation_fact(
                job_id="job-p", activity_at_utc="2026-09-26T15:00:00.000Z",
                profile_name=canary, final_words=3,
                insertion_outcome="confirmed")
        else:
            # Content canaries travel as the dictation's TEXT through the
            # real terminal recorder; only counts may reach usage.
            from m13_drivers import _record
            _record(h, raw=f"alpha {canary} beta",
                    final_text=f"Alpha {canary} beta.", job_id="job-p")
        from localflow.v2.profile import ProfileService
        ProfileService(h.d.store, min_words=1).compute()
        h.d.hubDeleteAllUsage()
        mq.flush()
        meta = h.d.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT meta_json FROM usage_facts").fetchall()])
        snaps = h.d.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT measured_json FROM profile_snapshots").fetchall()])
        h.d.v2log.flush()
        events = list((h.tmp / "events").glob("*.jsonl"))
        ev_hits = _scan(events, canary)
        # Positive control: the scanned log really holds this run's
        # events (an empty or unflushed log would pass vacuously).
        ev_text = "".join(p.read_text(errors="replace") for p in events)
        if "usage.deleted" not in ev_text:
            return result("INVALID", {"events": len(events)},
                          note="event log not written; scan would be"
                          " vacuous")
    committed = [p for p in (ROOT / "docs" / "v2").rglob("*")
                 if p.is_file() and ("M13" in str(p) or "m13" in p.name)
                 and p.suffix in (".json", ".md", ".html")]
    committed += list((ROOT / "tests" / "v2" / "analytics").glob("*.json"))
    committed_hits = [p for p in _scan(committed, canary)
                      if "m13_audit_corpus.json" not in p
                      and "Read_Only_Deep_Audit" not in p]
    obs = {"meta_hits": sum(canary in m for m in meta),
           "event_hits": len(ev_hits),
           "snapshot_hits": sum(canary in s for s in snaps),
           "committed_hits": committed_hits}
    return check({"meta": obs["meta_hits"] == 0,
                  "events": obs["event_hits"] == 0,
                  "snapshots_after_delete": obs["snapshot_hits"] == 0,
                  "committed": not committed_hits}, obs)


# =============================================================================
# benchmark validity (the script's own gate)
# =============================================================================

BENCH = ROOT / "scripts" / "v2" / "benchmark_m13.py"


def _bench(*args):
    p = subprocess.run([sys.executable, str(BENCH), *args],
                       capture_output=True, text=True, timeout=1800)
    return p.returncode, (p.stdout + p.stderr)[-600:]


@drives("M13-C247", "M13-C248", "M13-C253", "M13-C254", "M13-C255",
        "M13-C256")
def d_bench_shape(case):
    shape = {"M13-C247": "acceptance", "M13-C248": "mixed_facts",
             "M13-C253": "busy_day", "M13-C254": "many_days",
             "M13-C255": "rebuild", "M13-C256": "expiry"}[case["case_id"]]
    rc, tail = _bench("--validate-only", "--scale", "small", "--shapes",
                      shape)
    rec = NATIVE.get("bench")
    full = None
    if rec is not None:
        full = (rec.get("status"), shape in (rec.get("results") or {}))
    obs = {"validity_exit": rc, "tail": tail[-200:], "full_run": full}
    ok = rc == 0 and (full is None or full == ("valid", True))
    return result("PASS" if ok else "FAIL", obs,
                  note=None if full else "full-scale timing graded from"
                  " the benchmark record when supplied")


@drives("M13-C249", "M13-C250", "M13-C251", "M13-C252")
def d_bench_rejects(case):
    variant = {"M13-C249": "filter", "M13-C250": "filter",
               "M13-C251": "query", "M13-C252": "write"}[case["case_id"]]
    rc, tail = _bench("--validate-only", "--scale", "small", "--shapes",
                      "acceptance", "--noop", variant)
    return check({"invalid_exit": rc == 3}, {"exit": rc,
                                             "tail": tail[-200:]})


@drives("M13-C257")
def d_bench_delay(case):
    """MR14 on the query measurement: a delay injected INSIDE the timed
    report moves its p50 by at least the delay; the same delay in an
    excluded phase (outside the timed window) does not."""
    import tempfile
    outs = {}
    with tempfile.TemporaryDirectory() as td:
        for tag, delay in (("base", None), ("inside", "query:200"),
                           ("outside", "outside:200")):
            args = ["--scale", "small", "--shapes", "acceptance",
                    "--samples", "5", "--warmups", "1", "--writes", "3",
                    "--copies", "1", "--out", f"{td}/{tag}"]
            if delay:
                args += ["--delay", delay]
            rc, _t = _bench(*args)
            data = json.loads(pathlib.Path(f"{td}/{tag}/m13.json")
                              .read_text())
            outs[tag] = (rc, data["results"]["acceptance"]["queries"][
                "report_30d"]["p50_ms"])
    shift_in = outs["inside"][1] - outs["base"][1]
    shift_out = outs["outside"][1] - outs["base"][1]
    obs = {"base": outs["base"], "inside": outs["inside"],
           "outside": outs["outside"], "shift_inside_ms": shift_in,
           "shift_outside_ms": shift_out}
    return check({"inside_moves": shift_in >= 190.0,
                  "outside_does_not": abs(shift_out) < 40.0}, obs)


@drives("M13-C258")
def d_bench_environment(case):
    rec = NATIVE.get("bench")
    if rec is None:
        return result("NOT_RUN", None, note="the reference-Mac benchmark"
                      " record was not supplied to this run")
    env = rec.get("environment") or {}
    need = ("code_sha", "mac_model", "macos", "python", "sqlite", "power",
            "load_average")
    q = rec["results"]["acceptance"]["queries"]["report_30d"]
    obs = {k: env.get(k) for k in need}
    obs.update(samples=rec.get("samples"), p99=q.get("p99_ms"))
    return check({"environment": all(env.get(k) for k in need),
                  "samples": rec.get("samples", 0) >= 50,
                  "percentiles": all(q.get(k) is not None for k in
                                     ("p50_ms", "p95_ms", "p99_ms"))},
                 obs)


# =============================================================================
# native cases (graded from the owned-native record)
# =============================================================================

NATIVE_CASES = {"M13-C157": "range_kept_through_native_handlers",
                "M13-C186": "delete_all_cancel_admits_nothing",
                "M13-C237": "returned_refusal_rendered",
                "M13-C238": "controls_contained_and_reachable",
                "M13-C262": "invalid_retention_refused_natively"}


def native_driver(case):
    rec = NATIVE.get("record")
    name = NATIVE_CASES[case["case_id"]]
    if rec is None:
        return result("NOT_RUN", None, note="owned-native record not"
                      " supplied")
    row = (rec.get("checks") or {}).get(name)
    if row is None:
        return result("NOT_RUN", None, note=f"native check {name} absent")
    return result("PASS" if row.get("status") == "PASS" else "FAIL", row,
                  grading="native", witness={"native_check": name})


for _cid in NATIVE_CASES:
    DRIVERS[_cid] = native_driver
