"""EV-11 (history halves) / M09: the History query layer.

Date grouping with the explicit Undated group for legacy imports,
text/app/mode search, the distinct source→normalized→cleaned lineage
(M09-AC01) and honest audio-availability reasons (M09-AC02). All data
synthetic.

Run: .venv/bin/python tests/v2/ui/test_history_queries.py
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.history_queries import (  # noqa: E402
    HistoryQueryService, UNDATED)
from localflow.v2.store import Store  # noqa: E402

TZ = dt.timezone.utc


class Env:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.store = Store(self.tmp / "v2.db",
                           artifacts_dir=self.tmp / "arts",
                           backup_dir=self.tmp / "bk")
        self.svc = HistoryQueryService(self.store, tz=TZ)
        return self

    def __exit__(self, *exc):
        self.store.close()
        self._tmp.cleanup()

    def add_job(self, captured, state="insertion_confirmed", app=None,
                bundle=None, raw=None, cleaned=None, mode=None,
                normalized=None):
        job_id, family_id = self.store.create_job(
            captured_at_utc=captured, time_quality="known", state=state)
        if app or bundle:
            self.store.set_job_target(job_id, app, bundle)
        if raw is not None:
            self.store.write_text_artifact(
                job_id=job_id, stage="asr", role="raw_transcript",
                text=raw, retention_class="history")
        if normalized is not None:
            self.store.write_text_artifact(
                job_id=job_id, stage="normalization",
                role="normalized_text", text=normalized,
                retention_class="history")
        if cleaned is not None:
            self.store.write_text_artifact(
                job_id=job_id, stage="cleanup", role="applied_output",
                text=cleaned, retention_class="history",
                meta={"cleanup_path": mode or "llm"})
        return job_id

    def add_legacy_pair(self, raw, cleaned):
        return self.store.import_legacy_pair(
            raw_text=raw, cleaned_text=cleaned, raw_meta={},
            cleaned_meta={}, source_kind="legacy_log",
            source_sha="sha-synthetic", locator=f"lines-{id(raw)}")


def test_grouping_and_undated():
    with Env() as e:
        e.add_job("2026-09-21T10:00:00.000Z", raw="alpha synthetic",
                  cleaned="Alpha synthetic.")
        e.add_job("2026-09-22T11:00:00.000Z", raw="beta synthetic",
                  cleaned="Beta synthetic.")
        e.add_legacy_pair("gamma synthetic", "Gamma synthetic.")
        res = e.svc.search()
        labels = [g["label"] for g in res["groups"]]
        assert labels == ["2026-09-22", "2026-09-21", UNDATED], labels
        undated = res["groups"][-1]["rows"][0]
        assert undated["kind"] == "legacy_log"
        assert undated["time_quality"] == "unknown"
        assert undated["date"] is None
        print("ok  date grouping newest-first; legacy imports Undated")


def test_text_app_mode_filters():
    with Env() as e:
        j1 = e.add_job("2026-09-22T10:00:00.000Z", app="Xcode",
                       bundle="com.apple.dt.Xcode",
                       raw="fix the flaky fixture",
                       cleaned="Fix the flaky fixture.", mode="llm")
        e.add_job("2026-09-22T11:00:00.000Z", app="Notes",
                  bundle="com.apple.Notes", raw="remember the milk",
                  cleaned="Remember the milk.", mode="basic")
        e.add_legacy_pair("legacy words", "Legacy words.")
        # Text search matches both halves of the corpus.
        res = e.svc.search(text="flaky")
        assert res["total"] == 1 and res["groups"][0]["rows"][0]["id"] == j1
        res = e.svc.search(text="legacy words")
        assert res["total"] == 1
        assert res["groups"][0]["label"] == UNDATED
        # App filter.
        res = e.svc.search(app="xcode")
        assert res["total"] == 1 and res["groups"][0]["rows"][0]["id"] == j1
        # Mode filter (the cleanup path of the applied artifact).
        res = e.svc.search(mode="basic")
        assert res["total"] == 1
        assert res["groups"][0]["rows"][0]["mode"] == "basic"
        res = e.svc.search(mode="legacy")
        assert res["total"] == 1
        assert res["groups"][0]["rows"][0]["kind"] == "legacy_log"
        try:
            e.svc.search(mode="'); DROP TABLE jobs;--")
            raise AssertionError("arbitrary mode accepted")
        except ValueError:
            pass
        print("ok  text/app/mode filters; mode from a fixed vocabulary")


def test_lineage_distinct_stages():
    """M09-AC01: source → normalized → cleaned → transformed are distinct
    entries; the absent transform says why instead of flattening."""
    with Env() as e:
        j1 = e.add_job("2026-09-22T10:00:00.000Z",
                       raw="fix issue twenty two",
                       normalized="fix issue 22",
                       cleaned="Fix issue 22.")
        detail = e.svc.job_detail(j1)
        stages = [s["stage"] for s in detail["lineage"]]
        assert stages == ["source", "normalized", "cleaned",
                          "transformed"], stages
        texts = [s["artifact"]["text"] for s in detail["lineage"][:3]]
        assert texts == ["fix issue twenty two", "fix issue 22",
                         "Fix issue 22."], texts
        tf = detail["lineage"][3]
        assert tf["artifact"] is None and tf["reason"] == \
            "not_applicable"
        assert detail["app"] is None  # no identity read recorded
        print("ok  AC01: lineage stages distinct, transform honestly absent")


def test_lineage_transform_stage_resolves():
    """M11: a job with a transform_output artifact resolves the
    transformed stage from it (the cleaned stage keeps the Clean
    text — never a flattened copy)."""
    with Env() as e:
        j1 = e.add_job("2026-09-22T10:00:00.000Z",
                       raw="fix issue twenty two",
                       normalized="fix issue 22",
                       cleaned="Fix issue 22.")
        e.store.write_text_artifact(
            job_id=j1, stage="transform", role="transform_output",
            text="Fix issue 22. (polished)", retention_class="history",
            meta={"transform_id": "builtin:polish"})
        detail = e.svc.job_detail(j1)
        stages = {s["stage"]: s for s in detail["lineage"]}
        assert stages["cleaned"]["artifact"]["text"] == "Fix issue 22."
        tf = stages["transformed"]
        assert tf["artifact"] is not None and tf["reason"] is None
        assert tf["artifact"]["text"] == "Fix issue 22. (polished)"
        print("ok  M11: transform stage resolves from its artifact")


def test_audio_and_purged_reasons():
    """M09-AC02 query half: missing audio is labeled unavailable with a
    reason — never fabricated."""
    with Env() as e:
        import numpy as np
        j1 = e.add_job("2026-09-22T10:00:00.000Z", raw="x", cleaned="X.")
        detail = e.svc.job_detail(j1)
        assert detail["audio"] == {"available": False,
                                   "reason": "no_audio_artifact"}
        art = e.store.write_audio_artifact(
            job_id=j1, stage="capture",
            samples=np.zeros(1600, dtype=np.float32), sample_rate=16000)
        detail = e.svc.job_detail(j1)
        assert detail["audio"]["available"] is True
        assert detail["audio"]["artifact_id"] == art
        e.store.delete_everywhere("job", j1, reason="test purge")
        detail = e.svc.job_detail(j1)
        assert detail["audio"]["available"] is False
        assert detail["audio"]["reason"] == "purged"
        print("ok  AC02: audio unavailable reasons (none/purged)")


def test_insertion_outcome_in_detail():
    with Env() as e:
        j1 = e.add_job("2026-09-22T10:00:00.000Z", raw="x", cleaned="X.")
        from localflow.v2 import store as store_mod
        from localflow.v2.insertion import record as ins_record
        from localflow.v2.insertion.result import InsertionResult
        ins_record.record_insertion(e.store, InsertionResult(
            insertion_id="ins-test-1", job_id=j1,
            state="posted_unverified", reason_code="readback_unavailable",
            method="clipboard_transaction", inserted_chars=2,
            verification={}, clipboard={},
            created_at_utc="2026-09-22T10:00:02.000Z"))
        detail = e.svc.job_detail(j1)
        assert detail["insertion"]["state"] == "posted_unverified"
        assert detail["insertion"]["method"] == "clipboard_transaction"
        print("ok  insertion outcome carried into the detail")


def test_empty_history():
    with Env() as e:
        res = e.svc.search()
        assert res == {"groups": [], "total": 0}
        assert e.svc.home_summary() == {
            "today_count": 0, "total_jobs": 0, "legacy_rows": 0,
            "last_dictation": None}
        print("ok  empty history and Home are honest empties")


def test_home_summary():
    with Env() as e:
        now = dt.datetime.now(TZ)
        e.add_job(now.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        e.add_job("2026-09-01T10:00:00.000Z")
        e.store.insert_legacy_dictation(
            {"id": 1, "ts": 1750000000.0, "duration_sec": 1.0,
             "raw_text": "a", "cleaned_text": "a", "raw_words": 1,
             "cleaned_words": 1, "fixed_words": 0, "wpm": 60.0,
             "app_name": "OldApp", "app_bundle": "old", "kind":
             "dictation"}, "sha-x")
        s = e.svc.home_summary()
        assert s["today_count"] == 1
        assert s["total_jobs"] == 2
        assert s["legacy_rows"] == 1
        assert s["last_dictation"]["state"] == "insertion_confirmed"
        print("ok  Home summary counts (jobs facts only, no M13 analytics)")


def test_legacy_db_rows_surface():
    with Env() as e:
        e.store.insert_legacy_dictation(
            {"id": 7, "ts": 1783000000.0, "duration_sec": 2.0,
             "raw_text": "seven synthetic words", "cleaned_text":
             "Seven synthetic words", "raw_words": 3, "cleaned_words": 3,
             "fixed_words": 0, "wpm": 90.0, "app_name": "Slack",
             "app_bundle": "com.tinyspeck.slackmacgap", "kind":
             "dictation"}, "sha-y")
        res = e.svc.search(text="seven synthetic")
        assert res["total"] == 1
        row = res["groups"][0]["rows"][0]
        assert row["kind"] == "legacy_db" and row["app"] == "Slack"
        assert row["date"] == "2026-07-02"  # preserved instant, UTC display
        print("ok  legacy analytics rows searchable with their own dates")


def test_like_escaping_and_overall_limit():
    """Review coverage: literal % and _ in the needle are escaped (a %
    in the needle must not wildcard-match other rows), and the limit
    applies to the merged result."""
    with Env() as e:
        e.add_job("2026-09-22T10:00:00.000Z",
                  raw="100% synthetic_understood", cleaned="X.")
        e.add_job("2026-09-22T11:00:00.000Z",
                  raw="100X would only match a wildcard",
                  cleaned="Y.")
        res = e.svc.search(text="100%")
        assert res["total"] == 1, res["total"]
        assert "wildcard" not in json.dumps(res)
        # The underscore is a literal too: it matches the substring it
        # is, never as a single-character wildcard.
        res = e.svc.search(text="synthetic_")
        assert res["total"] == 1
        for i in range(6):
            e.add_job(f"2026-09-1{i}T10:00:00.000Z",
                      raw=f"row {i} synthetic", cleaned=f"R{i}.")
        res = e.svc.search(limit=4)
        assert res["total"] == 4, "limit applies to merged sections"
    print("ok  LIKE escaping; limit applied to merged result")


def test_legacy_detail_pairs():
    with Env() as e:
        pair = e.add_legacy_pair("legacy raw half", "legacy cleaned half")
        detail = e.svc.legacy_detail(pair[1])
        assert detail["kind"] == "legacy_log"
        assert detail["time_quality"] == "unknown"
        assert detail["audio"] == {"available": False,
                                   "reason": "legacy_no_audio"}
        stages = {s["stage"]: s["artifact"]["text"]
                  for s in detail["lineage"]}
        assert stages == {"source": "legacy raw half",
                          "cleaned": "legacy cleaned half"}
    print("ok  legacy pair detail (raw + cleaned halves)")


if __name__ == "__main__":
    test_grouping_and_undated()
    test_text_app_mode_filters()
    test_lineage_distinct_stages()
    test_lineage_transform_stage_resolves()
    test_audio_and_purged_reasons()
    test_insertion_outcome_in_detail()
    test_empty_history()
    test_home_summary()
    test_legacy_db_rows_surface()
    test_like_escaping_and_overall_limit()
    test_legacy_detail_pairs()
    print("all history query tests passed")
