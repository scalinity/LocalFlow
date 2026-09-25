"""EV-15 analytics portion (M13): usage facts and versioned aggregates.

Store-level suites over the single-writer store: the additive v9
migration, the one-fact-per-logical-dictation rule (retries/replays/
re-pastes never double count — M13-AC02), unknown dates never entering
dated views, DST day boundaries in the reporting zone, retention expiry
independent of text retention (M13-AC03), versioned recomputation, the
seven-row legacy reconciliation read in place (M13-AC01), explicit
usage deletion controls, and job-row metadata pruning with facts
surviving.

All fixtures are synthetic (sanitized app names, synthetic instants
shaped like the audited aggregate totals — never private data).

Run: .venv/bin/python tests/v2/analytics/test_usage_store.py
"""

import datetime as dt
import pathlib
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import analytics, store as store_mod  # noqa: E402

NY = "America/New_York"


def make_store(tmp, **kw):
    return store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups",
                           **kw)


def seeded_legacy_rows(s):
    """Seven sanitized rows carrying the audited aggregate totals
    (E13's reconciliation figures — public aggregates, synthetic
    text/apps)."""
    rows = []
    base = dt.datetime(2026, 7, 4, 21, 15, 42, 804000,
                       tzinfo=dt.timezone.utc)
    words = [(40, 39), (38, 38), (41, 41), (39, 39), (42, 41), (38, 38),
             (42, 41)]
    for i, (rw, cw) in enumerate(words):
        ts = base + dt.timedelta(seconds=i * 197)
        rows.append({
            "id": i + 1, "ts": ts.timestamp(), "duration_sec": 50.0,
            "raw_text": f"synthetic raw {i}" * 3,
            "cleaned_text": f"synthetic cleaned {i}" * 3,
            "raw_words": rw, "cleaned_words": cw,
            "fixed_words": (11 if i == 0 else 0),
            "wpm": 44.0 + i, "app_name": f"Synth App {i % 2}",
            "app_bundle": f"com.synthetic.{i % 2}", "kind": "dictation",
        })
    for row in rows:
        s.insert_legacy_dictation(row, "synthetic-sha")
    return rows


def test_migration_v9_additive_with_backup_and_repair():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        db = tmp / "v2.db"
        # A genuine v8 database (the M12 schema), version stamped 8.
        pre = sqlite3.connect(db)
        for v in range(1, 9):
            for stmt in store_mod._MIGRATIONS[v]:
                pre.execute(stmt)
        pre.execute("INSERT OR REPLACE INTO schema_meta"
                    " VALUES('schema_version','8')")
        pre.commit()
        pre.close()
        s = make_store(tmp)
        try:
            assert s.submit(lambda db: db.execute(
                "SELECT value FROM schema_meta WHERE"
                " key='schema_version'").fetchone())[0] == \
                str(max(store_mod._MIGRATIONS))  # latest (v11 since M02
            # remediation: additive job_deletions/purge_intents)
            for table in ("usage_facts", "daily_aggregates",
                           "learning_candidates",
                           "training_memberships",
                           "export_manifests"):
                assert s.submit(lambda db, t=table: db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    f" AND name=?", (t,)).fetchone()), table
            assert any((tmp / "backups").glob("v2-pre-migrate-*.db")), \
                "no pre-migration backup taken"
            # Repair: drop the v9 tables, reopen — idempotent DDL
            # rebuilds them (the torn-write repair set covers v9).
            s.close()
            post = sqlite3.connect(db)
            for t in ("usage_facts", "daily_aggregates"):
                post.execute(f"DROP TABLE IF EXISTS {t}")
            post.commit()
            post.close()
            s2 = make_store(tmp)
            try:
                assert s2.submit(lambda db: db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND"
                    " name='usage_facts'").fetchone()), "v9 not repaired"
            finally:
                s2.close()
        finally:
            if not s._stop:
                s.close()
    print("ok  v9 migration additive, backed up, repair-covered")


def test_one_dictation_counts_once_retry_replaces():
    """M13-AC02: a retry reaching a terminal outcome again REPLACES the
    fact; re-pastes and transforms never increment dictated words."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        try:
            at = "2026-09-23T14:00:00.000Z"
            a.record_dictation_fact(
                job_id="job-a", activity_at_utc=at, duration_sec=10.0,
                raw_words=20, final_words=19,
                insertion_outcome="confirmed", attempt=1)
            # The same logical job fails first, retries, succeeds: one
            # row, final attempt recorded.
            a.record_dictation_fact(
                job_id="job-a", activity_at_utc=at, duration_sec=10.0,
                raw_words=20, final_words=19,
                insertion_outcome="failed", attempt=1)
            a.record_dictation_fact(
                job_id="job-a", activity_at_utc=at, duration_sec=10.0,
                raw_words=20, final_words=19,
                insertion_outcome="confirmed", attempt=2)
            rows = s.submit(lambda db: db.execute(
                "SELECT attempt, insertion_outcome, raw_words,"
                " final_words FROM usage_facts WHERE"
                " kind='dictation'").fetchall())
            assert rows == [(2, "confirmed", 20, 19)], rows
            # A re-paste of the same job: activity row, no word counts.
            a.record_repaste_fact(job_id="job-a")
            a.record_repaste_fact(job_id="job-a")
            q = analytics.InsightsQueryService(s, a)
            summ = q.summary(days=3650)
            assert summ["dictations"] == 1, summ
            assert summ["final_words"] == 19
            assert summ["repastes"] == 2
            # An explicit transform: its own count, never dictation
            # words (M13-AC02's second half).
            a.record_transform_fact(
                transform_id="builtin:polish", task_key="tk", path="applied",
                source_kind="selection", source_words=19,
                output_words=17, duration_ms=500.0)
            summ = q.summary(days=3650)
            assert summ["dictations"] == 1 and summ["final_words"] == 19
            assert summ["transforms"] == 1
            assert summ["transform_words"] == 19
        finally:
            s.close()
    print("ok  one dictation counts once; retry replaces; transform and"
          " re-paste are separate kinds")


def test_unknown_dates_never_enter_dated_views():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        try:
            # An unparseable instant is refused outright — never parked
            # on a fabricated day (S21).
            out = a.record_dictation_fact(
                job_id="job-x", activity_at_utc="not-a-timestamp",
                insertion_outcome="confirmed", final_words=3)
            assert out is None
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM usage_facts").fetchone())[0] == 0
            # Undated legacy log pairs surface only as the explicit
            # count, never inside the dated table.
            s.submit(lambda db: db.execute(
                "INSERT INTO artifacts(artifact_id, job_id, stage, kind,"
                " role, content_text, sha256, bytes, meta_json,"
                " retention_class, purged, created_at_utc)"
                " VALUES('art-u', NULL, 'legacy_log', 'legacy_text',"
                " 'cleaned_transcript', 'x', 'h', 1, '{}', 'legacy', 0,"
                " '2026-01-01T00:00:00.000Z')"))
            q = analytics.InsightsQueryService(s, a)
            assert q.daily(days=30) == []
            assert q.undated_count() == 1
        finally:
            s.close()
    print("ok  unknown dates stay out of dated views")


def test_dst_day_boundaries():
    """Day buckets follow the reporting zone across spring-forward and
    fall-back (S21/EV-15)."""
    # 2026-03-08: US spring forward at 02:00 local (07:00Z). Midnight
    # New York is 05:00Z; the skipped hour maps through zoneinfo.
    assert analytics.local_day_for(
        "2026-03-08T04:59:59.000Z", NY) == "2026-03-07"
    assert analytics.local_day_for(
        "2026-03-08T05:00:00.000Z", NY) == "2026-03-08"
    assert analytics.local_day_for(
        "2026-03-08T07:30:00.000Z", NY) == "2026-03-08"  # 03:30 EDT
    # 2026-11-01: fall back at 02:00 local (06:00Z). Midnight is 05:00Z
    # EDT; after the transition midnight is 04:00Z EST (clock moved
    # back — Nov 2 starts an hour earlier UTC).
    assert analytics.local_day_for(
        "2026-11-01T05:30:00.000Z", NY) == "2026-11-01"  # 01:30 EDT
    assert analytics.local_day_for(
        "2026-11-01T06:30:00.000Z", NY) == "2026-11-01"  # 01:30 EST
    assert analytics.local_day_for(
        "2026-11-02T04:30:00.000Z", NY) == "2026-11-01"  # 23:30 EST
    assert analytics.local_day_for(
        "2026-11-02T05:00:00.000Z", NY) == "2026-11-02"
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        try:
            # A dictation before midnight and one after the
            # spring-forward jump land on their true local days.
            a.record_dictation_fact(
                job_id="job-dst-1", activity_at_utc="2026-03-08T04:59:00.000Z",
                duration_sec=5.0, final_words=5,
                insertion_outcome="confirmed")
            a.record_dictation_fact(
                job_id="job-dst-2", activity_at_utc="2026-03-08T07:01:00.000Z",
                duration_sec=5.0, final_words=5,
                insertion_outcome="confirmed")
            days = s.submit(lambda db: db.execute(
                "SELECT day_local, COUNT(*) FROM usage_facts WHERE"
                " kind='dictation' GROUP BY day_local ORDER BY"
                " day_local").fetchall())
            assert days == [("2026-03-07", 1), ("2026-03-08", 1)], days
        finally:
            s.close()
    print("ok  DST spring-forward/fall-back day boundaries")


def test_text_prune_does_not_empty_usage_and_expiry_does():
    """M13-AC03: transcript retention expiry never touches usage
    graphs; only the explicit usage controls and the usage knob do."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        q = analytics.InsightsQueryService(s, a)
        try:
            old = "2026-08-01T12:00:00.000Z"
            job_id, _fam = s.create_job(
                captured_at_utc=old, released_at_utc=old,
                state="insertion_confirmed")
            art = s.write_text_artifact(
                job_id=job_id, stage="asr", role="raw_transcript",
                text="synthetic retained text", retention_class="history")
            s.grant_lease(art, "history", days=1)
            a.record_dictation_fact(
                job_id=job_id, activity_at_utc=old, duration_sec=8.0,
                raw_words=3, final_words=3,
                insertion_outcome="confirmed")
            assert q.summary(days=365)["dictations"] == 1
            # Push time past every content lease: the text purges.
            now = time.mktime((2026, 9, 23, 12, 0, 0, 0, 0, -1)) + \
                60 * 86400
            out = s.prune(now=now)
            assert out["purged"] >= 1, "text did not expire"
            purged = s.artifact(art)
            assert purged["purged"]
            # ...and the usage graph is untouched (AC03).
            summ = q.summary(days=365)
            assert summ["dictations"] == 1 and summ["final_words"] == 3, \
                "text expiry emptied usage graphs"
            # The explicit per-job control empties exactly that usage.
            a.delete_usage_for_job(job_id)
            assert q.summary(days=365)["dictations"] == 0
            # The usage retention knob expires old facts on its own.
            a.record_dictation_fact(
                job_id="job-old2", activity_at_utc=old,
                insertion_outcome="confirmed", final_words=2)
            s.retention_days["usage"] = 30
            out = a.expire_usage(now=now)
            assert out["facts_removed"] == 1, out
            assert q.summary(days=3650)["dictations"] == 0
        finally:
            s.close()
    print("ok  AC03: text prune keeps usage; explicit deletion and the"
          " usage knob remove it")


def test_versioned_recompute_and_zone_change():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        q = analytics.InsightsQueryService(s, a)
        try:
            a.record_dictation_fact(
                job_id="job-v1", activity_at_utc="2026-09-23T02:30:00.000Z",
                duration_sec=10.0, raw_words=10, final_words=10,
                insertion_outcome="confirmed")
            before = q.summary(days=3650)
            day_ny = s.submit(lambda db: db.execute(
                "SELECT day_local FROM usage_facts WHERE"
                " kind='dictation'").fetchone())[0]
            assert day_ny == "2026-09-22"  # 22:30 local in New York
            # Full rebuild under the same zone: identical totals
            # (count-version change keeps the arithmetic).
            a.rebuild_aggregates()
            after = q.summary(days=3650)
            assert after["dictations"] == before["dictations"] == 1
            assert after["final_words"] == before["final_words"] == 10
            # Changing the reporting zone re-buckets every day.
            a.rebuild_aggregates(reporting_timezone="UTC")
            day_utc = s.submit(lambda db: db.execute(
                "SELECT day_local FROM usage_facts WHERE"
                " kind='dictation'").fetchone())[0]
            assert day_utc == "2026-09-23"
            # Exactly one zone's aggregates exist afterwards.
            zones = s.submit(lambda db: db.execute(
                "SELECT COUNT(DISTINCT reporting_timezone) FROM"
                " daily_aggregates").fetchone())[0]
            assert zones == 1, zones
            # An unknown zone is refused, never guessed.
            assert a.rebuild_aggregates(
                reporting_timezone="Mars/Olympus")["outcome"] == \
                "unknown_timezone"
        finally:
            s.close()
    print("ok  versioned recompute; zone change re-buckets; one zone"
          " at a time")


def test_legacy_seven_row_reconciliation():
    """M13-AC01: the imported rows reconcile exactly, in place — never
    rewritten into usage_facts, never relabeled."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        q = analytics.InsightsQueryService(s, a)
        try:
            seeded_legacy_rows(s)
            legacy = q.legacy_summary()
            assert legacy["rows"] == 7
            assert legacy["raw_words"] == 280
            assert legacy["cleaned_words"] == 277
            assert legacy["capture_seconds"] == 350.0  # 7 × 50.0
            assert legacy["legacy_fixed_words"] == 11
            assert legacy["rows_without_instant"] == 0
            # The rows themselves are byte-identical after all M13
            # machinery ran (instants, counts, kind, fixed words).
            rows = s.submit(lambda db: db.execute(
                "SELECT id, ts, duration_sec, raw_words, cleaned_words,"
                " fixed_words, kind FROM legacy_dictations ORDER BY"
                " id").fetchall())
            assert len(rows) == 7
            assert sum(r[3] for r in rows) == 280
            assert sum(r[4] for r in rows) == 277
            assert sum(abs(r[2] - 50.0) < 1e-9 for r in rows) == 7
            assert sum(r[5] for r in rows) == 11
            # Legacy rows never became usage facts.
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM usage_facts").fetchone())[0] == 0
            # And they are not deletable usage (the lossless import).
            assert a.delete_usage_for_job("legacy-db:1")["days_touched"] \
                == 0
        finally:
            s.close()
    print("ok  seven-row legacy reconciliation unchanged and separate")


def test_delete_all_usage_removes_only_usage():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        try:
            job_id, _fam = s.create_job(state="insertion_confirmed")
            s.write_text_artifact(job_id=job_id, stage="asr",
                                  role="raw_transcript",
                                  text="kept", retention_class="history")
            a.record_dictation_fact(
                job_id=job_id, activity_at_utc="2026-09-23T12:00:00.000Z",
                final_words=1, insertion_outcome="confirmed")
            out = a.delete_all_usage()
            assert out["facts_deleted"] == 1
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM usage_facts").fetchone())[0] == 0
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM daily_aggregates").fetchone())[0] == 0
            # Content survives (delete-content vs delete-usage).
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM artifacts WHERE purged=0"
            ).fetchone())[0] == 1
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM jobs").fetchone())[0] == 1
        finally:
            s.close()
    print("ok  delete-all-usage removes counters only")


def test_cross_day_retry_moves_the_fact_and_fixes_both_days():
    """Review critical (both reviewers): a retry completing on another
    local day must move the fact to the capture day's bucket AND the
    departed day's aggregate must be recomputed (or deleted when it
    emptied) — the two tables never disagree."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone="UTC")
        try:
            # Attempt 1 fails late on Sep 21; the retry succeeds early
            # on Sep 22 (same logical job, same capture instant).
            a.record_dictation_fact(
                job_id="job-x1", activity_at_utc="2026-09-21T23:58:00.000Z",
                duration_sec=10.0, raw_words=20, final_words=None,
                insertion_outcome="failed", attempt=1)
            assert s.submit(lambda db: db.execute(
                "SELECT dictations, failed FROM daily_aggregates WHERE"
                " day_local='2026-09-21'").fetchone()) == (1, 1)
            a.record_dictation_fact(
                job_id="job-x1", activity_at_utc="2026-09-21T23:58:00.000Z",
                duration_sec=10.0, raw_words=20, final_words=20,
                insertion_outcome="confirmed", attempt=2)
            days = s.submit(lambda db: db.execute(
                "SELECT day_local, dictations, final_words,"
                " insertion_confirmed FROM daily_aggregates ORDER BY"
                " day_local").fetchall())
            # The fact keeps its capture day; the departed (empty) day
            # is gone entirely.
            assert days == [("2026-09-21", 1, 20, 1)], days
            # With the retry landing on a different day_local (the
            # reviewer's literal scenario: the REWRITE carries a
            # different instant), both days stay consistent.
            a.record_dictation_fact(
                job_id="job-x2", activity_at_utc="2026-09-21T23:58:00.000Z",
                duration_sec=10.0, raw_words=20, final_words=None,
                insertion_outcome="failed", attempt=1)
            a.record_dictation_fact(
                job_id="job-x2", activity_at_utc="2026-09-22T00:05:00.000Z",
                duration_sec=10.0, raw_words=20, final_words=21,
                insertion_outcome="confirmed", attempt=2)
            assert aggregates_match_facts(s)
            days = s.submit(lambda db: db.execute(
                "SELECT day_local, dictations FROM daily_aggregates ORDER"
                " BY day_local").fetchall())
            assert ("2026-09-22", 1) in days and \
                ("2026-09-21", 1) in days  # job-x1 stays on the 21st
        finally:
            s.close()
    print("ok  cross-day retry: fact moves, both days stay consistent")


def aggregates_match_facts(s) -> bool:
    """The invariant: every daily_aggregates row equals what a fresh
    recompute over that day's facts would produce."""
    def op(db):
        for (day, dictations, with_text, confirmed, unverified, saved,
             cancelled, failed, raw_w, final_w, secs, fallbacks, dh,
             sh, tf, tfw, rp) in db.execute(
                "SELECT day_local, dictations, dictations_with_text,"
                " insertion_confirmed, insertion_unverified,"
                " saved_not_inserted, cancelled, failed, raw_words,"
                " final_words, ROUND(capture_seconds,3), fallback_jobs,"
                " dictionary_hits, snippet_hits, transforms,"
                " transform_words, repastes FROM daily_aggregates"
            ).fetchall():
                row = db.execute(
                    "SELECT COUNT(*),"
                    " COALESCE(SUM(CASE WHEN final_words IS NOT NULL AND"
                    " final_words > 0 THEN 1 ELSE 0 END),0),"
                    " COALESCE(SUM(CASE WHEN insertion_outcome="
                    " 'confirmed' THEN 1 ELSE 0 END),0),"
                    " COALESCE(SUM(COALESCE(raw_words,0)),0),"
                    " COALESCE(SUM(COALESCE(final_words,0)),0),"
                    " ROUND(COALESCE(SUM(COALESCE(duration_sec,0.0)),"
                    " 0.0),3)"
                    " FROM usage_facts WHERE kind='dictation' AND"
                    " day_local=?", (day,)).fetchone()
                if (dictations, with_text, confirmed, raw_w, final_w,
                        secs) != row:
                    return False
        # No aggregate row for a factless day, and vice versa.
        fact_days = {r[0] for r in db.execute(
            "SELECT DISTINCT day_local FROM usage_facts")}
        agg_days = {r[0] for r in db.execute(
            "SELECT DISTINCT day_local FROM daily_aggregates")}
        return fact_days == agg_days
    return s.submit(op)


def test_aggregates_always_match_facts_under_writes_and_deletions():
    """The general invariant under mixed writes, retries, deletions and
    expiry (guards future formula changes too)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone="UTC")
        try:
            for i in range(6):
                day = f"2026-09-1{i % 3}"
                a.record_dictation_fact(
                    job_id=f"job-inv-{i}",
                    activity_at_utc=f"{day}T1{i}:00:00.000Z",
                    duration_sec=5.0, raw_words=5 + i,
                    final_words=(5 + i if i != 4 else None),
                    insertion_outcome=("failed" if i == 4
                                       else "confirmed"))
            a.record_transform_fact(
                transform_id="builtin:polish", task_key="tk-inv",
                path="applied", source_kind="selection", source_words=9)
            a.record_repaste_fact(
                activity_at_utc="2026-09-10T18:00:00.000Z")
            assert aggregates_match_facts(s)
            a.delete_usage_for_job("job-inv-1")
            assert aggregates_match_facts(s)
            s.retention_days["usage"] = 1
            a.expire_usage(now=1790000000.0)  # ~Sep 27 2026
            assert aggregates_match_facts(s)
        finally:
            s.close()
    print("ok  fact/aggregate invariant holds under writes, retries,"
          " deletions, expiry")


def test_prune_metadata_keeps_usage_and_guards_examples():
    """The M02 metadata knob (enforced from M13): terminal job rows go
    when their content is gone — usage facts carry their own copies and
    survive (AC03); a live training example pins the job row."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        a = analytics.AnalyticsStore(s, reporting_timezone=NY)
        q = analytics.InsightsQueryService(s, a)
        try:
            old = "2026-08-01T12:00:00.000Z"
            # Job 1: terminal, no artifacts, no example — prunable.
            j1, _ = s.create_job(captured_at_utc=old, state="cancelled")
            s.submit(lambda db: db.execute(
                "UPDATE jobs SET updated_at_utc=? WHERE job_id=?",
                (old, j1)))
            a.record_dictation_fact(
                job_id=j1, activity_at_utc=old, duration_sec=2.0,
                final_words=2, insertion_outcome="cancelled")
            # Job 2: live training example — pinned.
            j2, _ = s.create_job(captured_at_utc=old,
                                 state="insertion_confirmed")
            s.submit(lambda db: db.execute(
                "UPDATE jobs SET updated_at_utc=? WHERE job_id=?",
                (old, j2)))
            s.upsert_example(job_id=j2, family_id="fam-2")
            # Job 3: retained artifact — pinned by content.
            j3, _ = s.create_job(captured_at_utc=old,
                                 state="insertion_confirmed")
            s.submit(lambda db: db.execute(
                "UPDATE jobs SET updated_at_utc=? WHERE job_id=?",
                (old, j3)))
            s.write_text_artifact(job_id=j3, stage="asr",
                                  role="raw_transcript", text="kept",
                                  retention_class="training")
            now = time.mktime((2026, 9, 23, 12, 0, 0, 0, 0, -1))
            out = s.prune_metadata(now=now)
            assert out["jobs_deleted"] == 1, out
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM jobs WHERE job_id=?",
                (j1,))).fetchone()[0] == 0
            for j in (j2, j3):
                assert s.submit(lambda db, jj=j: db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE job_id=?",
                    (jj,))).fetchone()[0] == 1
            # The pruned job's usage survives with its own copies.
            summ = q.summary(days=3650)
            assert summ["dictations"] == 1 and summ["final_words"] == 2, \
                "job-row pruning emptied usage graphs"
        finally:
            s.close()
    print("ok  metadata pruning: facts survive, live examples and"
          " content pin job rows")


if __name__ == "__main__":
    test_migration_v9_additive_with_backup_and_repair()
    test_one_dictation_counts_once_retry_replaces()
    test_unknown_dates_never_enter_dated_views()
    test_dst_day_boundaries()
    test_cross_day_retry_moves_the_fact_and_fixes_both_days()
    test_aggregates_always_match_facts_under_writes_and_deletions()
    test_text_prune_does_not_empty_usage_and_expiry_does()
    test_versioned_recompute_and_zone_change()
    test_legacy_seven_row_reconciliation()
    test_delete_all_usage_removes_only_usage()
    test_prune_metadata_keeps_usage_and_guards_examples()
    print("all usage store tests passed")
