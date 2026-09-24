"""EV-13 analytics portion (M13): the Insights query layer's honest
metrics — weighted WPM (never a row average), sample-aware latency
percentiles with cohort sizes, fallback rate denominators, cohort
filters, per-app/per-mode breakdowns, and the distinct legacy/undated
lines (M13-AC04's labeled-denominator discipline).

All fixtures synthetic. Run:
.venv/bin/python tests/v2/analytics/test_insights_service.py
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import analytics, store as store_mod  # noqa: E402

NY = "America/New_York"


def make(tmp):
    s = store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups")
    a = analytics.AnalyticsStore(s, reporting_timezone=NY)
    return s, a, analytics.InsightsQueryService(s, a)


def test_weighted_wpm_not_row_average():
    """S21/metrics.md: WPM aggregation is 60 × sum(words) /
    sum(capture_seconds) — two 60-wpm-and-120-wpm jobs must weight to
    ~65.5, not average to 90. A cancelled job's capture seconds never
    enter the denominator (AC04: one cohort for number and label)."""
    with tempfile.TemporaryDirectory() as td:
        s, a, q = make(pathlib.Path(td))
        try:
            a.record_dictation_fact(
                job_id="job-w1", activity_at_utc="2026-09-20T15:00:00.000Z",
                duration_sec=600.0, raw_words=600, final_words=600,
                insertion_outcome="confirmed")
            a.record_dictation_fact(
                job_id="job-w2", activity_at_utc="2026-09-20T16:00:00.000Z",
                duration_sec=60.0, raw_words=120, final_words=120,
                insertion_outcome="confirmed")
            summ = q.summary(days=3650)
            # Row-average would be (60 + 120) / 2 = 90; the weighted
            # formula is 60 × 720 / 660 = 65.45 → 65.5 rounded.
            assert summ["wpm"] == 65.5, summ["wpm"]
            assert summ["wpm_denominator"] == {
                "jobs": 2, "words": 720, "capture_seconds": 660.0}
            # A cancelled job carries real capture seconds but no text:
            # the WPM and its denominator are unchanged (the whole-
            # cohort minute total still counts it, labeled separately).
            a.record_dictation_fact(
                job_id="job-w3", activity_at_utc="2026-09-20T17:00:00.000Z",
                duration_sec=300.0, insertion_outcome="cancelled")
            summ2 = q.summary(days=3650)
            assert summ2["wpm"] == 65.5, summ2
            assert summ2["wpm_denominator"] == {
                "jobs": 2, "words": 720, "capture_seconds": 660.0}
            assert summ2["capture_seconds"] == 960.0  # all outcomes
            # No voiced data ⇒ no WPM, never a zero (honest null).
            empty = q.summary(days=3650, app="Nowhere")
            assert empty["wpm"] is None
        finally:
            s.close()
    print("ok  weighted WPM, one cohort for number and denominator")


def test_latency_percentiles_sample_aware():
    """E06/metrics.md: quantiles state cohort size; failed jobs stay in
    the cohort denominator so a slow failure cannot vanish."""
    with tempfile.TemporaryDirectory() as td:
        s, a, q = make(pathlib.Path(td))
        try:
            for i in range(1, 21):
                a.record_dictation_fact(
                    job_id=f"job-l{i}",
                    activity_at_utc=f"2026-09-20T1{i % 10}:00:00.000Z",
                    duration_sec=5.0, final_words=5,
                    insertion_outcome="confirmed", asr_ms=float(i * 100),
                    end_to_end_ms=float(1000 + i * 100))
            # A failed job with no latency samples: still counted in
            # the cohort, absent from every latency n.
            a.record_dictation_fact(
                job_id="job-lfail",
                activity_at_utc="2026-09-20T19:00:00.000Z",
                insertion_outcome="failed")
            summ = q.summary(days=3650)
            asr = summ["latency"]["asr"]
            assert asr["n"] == 20, asr
            # Nearest-rank on n=20: p50 = 10th value, p95 = 19th value.
            assert asr["p50"] == 1000.0 and asr["p95"] == 1900.0, asr
            assert asr["kind"] == "stage"
            e2e = summ["latency"]["end_to_end"]
            assert e2e["p50"] == 2000.0 and e2e["p95"] == 2900.0
            assert e2e["kind"] == "end_to_end"
            assert summ["dictations"] == 21  # the failure stayed counted
            # No samples at all: p50/p95 are None, never zeros.
            empty = q.summary(days=3650, app="Nowhere")
            assert empty["latency"]["asr"]["p50"] is None
            assert empty["latency"]["asr"]["n"] == 0
        finally:
            s.close()
    print("ok  sample-aware percentiles; failures stay in the cohort")


def test_cohort_filters_and_breakdowns():
    with tempfile.TemporaryDirectory() as td:
        s, a, q = make(pathlib.Path(td))
        try:
            at = "2026-09-21T15:00:00.000Z"
            a.record_dictation_fact(
                job_id="job-f1", activity_at_utc=at, duration_sec=10.0,
                raw_words=10, final_words=10, mode="clean",
                app_name="Synth Notes", app_bundle="com.synth.notes",
                insertion_outcome="confirmed", cleanup_path="llm",
                fallback_reason=None, dictionary_hits=2)
            a.record_dictation_fact(
                job_id="job-f2", activity_at_utc=at, duration_sec=20.0,
                raw_words=20, final_words=18, mode="polish",
                app_name="Synth Code", app_bundle="com.synth.code",
                insertion_outcome="confirmed", cleanup_path="llm",
                fallback_reason="protected_quantity_changed")
            a.record_transform_fact(
                transform_id="builtin:polish", task_key="tk-9",
                path="applied", source_kind="selection", source_words=30,
                output_words=28)
            all_summ = q.summary(days=3650)
            assert all_summ["dictations"] == 2
            assert all_summ["dictionary_hits"] == 2
            assert all_summ["fallback_jobs"] == 1
            assert all_summ["fallback_rate"] == 0.5  # 1 of 2, denominator
            assert all_summ["transforms"] == 1
            # App cohort.
            app_summ = q.summary(days=3650, app="Synth Code")
            assert app_summ["dictations"] == 1
            assert app_summ["final_words"] == 18
            # Activity kinds are honestly absent under a filter (they
            # carry no app/mode) — never borrowed from another cohort.
            assert app_summ["transforms"] is None
            assert q.daily(days=3650, app="Synth Code")[0]["transforms"] \
                is None
            # Mode cohort + breakdowns.
            assert q.summary(days=3650, mode="polish")["dictations"] == 1
            per_app = {r["app"]: r for r in q.per_app(days=3650)}
            assert set(per_app) == {"Synth Notes", "Synth Code"}
            assert per_app["Synth Code"]["final_words"] == 18
            per_mode = {r["mode"]: r for r in q.per_mode(days=3650)}
            assert set(per_mode) == {"clean", "polish"}
            assert per_mode["polish"]["dictations"] == 1
        finally:
            s.close()
    print("ok  cohort filters, honest activity-kind absence, breakdowns")


def test_daily_rows_and_range():
    with tempfile.TemporaryDirectory() as td:
        s, a, q = make(pathlib.Path(td))
        try:
            # 2026-09-20T02:00Z is 2026-09-19 22:00 in New York.
            a.record_dictation_fact(
                job_id="job-r1", activity_at_utc="2026-09-20T02:00:00.000Z",
                duration_sec=60.0, final_words=60,
                insertion_outcome="confirmed")
            a.record_dictation_fact(
                job_id="job-r2", activity_at_utc="2026-09-20T20:00:00.000Z",
                duration_sec=30.0, final_words=30,
                insertion_outcome="confirmed")
            daily = q.daily(days=3650)
            days = {r["day"]: r for r in daily}
            assert set(days) == {"2026-09-19", "2026-09-20"}, days
            assert days["2026-09-19"]["final_words"] == 60
            assert days["2026-09-20"]["final_words"] == 30
            # The 7-day window (relative to the real clock) excludes
            # nothing here in 2026 — but the boundary arithmetic is
            # zone-based; assert the shape only.
            assert all(r["dictations"] == 1 for r in daily)
        finally:
            s.close()
    print("ok  daily rows bucket by reporting zone")


def test_legacy_and_undated_lines():
    with tempfile.TemporaryDirectory() as td:
        s, a, q = make(pathlib.Path(td))
        try:
            for i in range(7):
                s.insert_legacy_dictation({
                    "id": i + 1, "ts": 1750000000.0 + i,
                    "duration_sec": 50.0,
                    "raw_text": "synthetic", "cleaned_text": "synthetic",
                    "raw_words": 40, "cleaned_words": 39,
                    "fixed_words": 1, "wpm": 48.0,
                    "app_name": "Synth App", "app_bundle": None,
                    "kind": "dictation"}, "sha")
            legacy = q.legacy_summary()
            assert legacy["rows"] == 7 and legacy["raw_words"] == 280
            assert legacy["legacy_fixed_words"] == 7
            # Legacy rows never appear as V2 facts or in daily rows.
            assert q.daily(days=3650) == []
            assert q.summary(days=3650)["dictations"] == 0
            # The legacy label is explicit — fixed_words stays under its
            # legacy name, never reused as a V2 metric (the stop
            # condition: the row-level wpm formula is unknown).
            assert "legacy_fixed_words" in legacy
            assert "wpm" not in legacy
        finally:
            s.close()
    print("ok  legacy line reconciles separately; undated stays apart")


def test_no_data_state():
    with tempfile.TemporaryDirectory() as td:
        s, a, q = make(pathlib.Path(td))
        try:
            summ = q.summary(days=30)
            assert summ["dictations"] == 0
            assert summ["wpm"] is None
            assert summ["outcomes"] == {
                "confirmed": 0, "posted_unverified": 0,
                "saved_not_inserted": 0, "cancelled": 0, "failed": 0}
            assert q.daily(days=30) == []
            assert q.per_app(days=30) == []
            assert q.legacy_summary() is None
            assert q.undated_count() == 0
        finally:
            s.close()
    print("ok  empty store reports honest zeros and nulls")


if __name__ == "__main__":
    test_weighted_wpm_not_row_average()
    test_latency_percentiles_sample_aware()
    test_cohort_filters_and_breakdowns()
    test_daily_rows_and_range()
    test_legacy_and_undated_lines()
    test_no_data_state()
    print("all insights service tests passed")
