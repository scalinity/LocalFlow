"""EV-19/EV-20 attribution / M08: the S29.8 bounded outcome observation
against the instrumented fixture target (Spec S29.8, E19.3).

The observer watches ONLY the owned range with exact target/job/region
attribution: typing outside the range re-anchors instead of becoming an
owned-region edit, an edit intersecting the range is recorded with
lease-governed before/after artifacts, selection movement is not an
edit, stop conditions end the window with recorded reasons, an undo of
a different revision is never attributed to LocalFlow's own, and
no-edit intervals plus confirmed pastes never create verified positive
training labels (M08-AC05/AC06). Unsupported surfaces report
outcome_observation_unavailable instead of polling.

Run: .venv/bin/python tests/v2/insertion/test_insertion_attribution.py
"""

import json
import pathlib
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fixture_target import FixtureTargetApp  # noqa: E402

from localflow.v2 import ids, store as store_mod, training  # noqa: E402
from localflow.v2.insertion.service import InsertionService  # noqa: E402


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, level, kw))


class Env:
    def __init__(self, target=None, *, window=1.2, settle=0.05):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.store = store_mod.Store(root / "v2.db",
                                     backup_dir=root / "backups")
        self.rec = Recorder()
        self.target = target or FixtureTargetApp()
        self.service = InsertionService(
            host=self.target, pasteboard=self.target.pb,
            keyboard=self.target, store=self.store, emit=self.rec,
            restore_clipboard=True, observation_window_sec=window,
            settle_sec=settle)

    def close(self):
        self.store.sync()
        self.store.close()
        self.tmp.cleanup()

    def insert(self, text, job_id="job-obs"):
        """Insert via the real service; returns (result, observer)."""
        box, done = {}, threading.Event()

        def on_done(result):
            box["result"] = result
            done.set()

        def on_observation(info):
            box["observer"] = info["observer"]

        # A recorded destination and capture-time collection consent:
        # the observer's admission conditions (M08 remediation — an
        # insert with no recorded destination is never confirmed, and a
        # capture without consent is never observed).
        from test_insertion_races import snapshot
        self.service.submit(
            text, {"job_id": job_id, "attempt": 1,
                   "context_snapshot": snapshot(self.target),
                   "observation_consent": True}, on_done,
            on_observation=on_observation)
        assert done.wait(15), "insertion did not finish"
        obs = box.get("observer")
        if obs is not None:
            deadline = time.monotonic() + 3
            while obs.observation_id is None and \
                    time.monotonic() < deadline:
                time.sleep(0.01)
        return box["result"], obs

    def observation_row(self, obs):
        def op(conn):
            return conn.execute(
                "SELECT stop_reason, edited, reanchors, ticks,"
                " before_artifact_id, after_artifact_id, meta_json"
                " FROM insertion_observations WHERE observation_id=?",
                (obs.observation_id,)).fetchone()
        return self.store.submit(op)


def settle_observer(obs, timeout=5.0):
    obs.join(timeout)
    assert obs.stop_reason is not None, "observer did not stop"


def collector_env():
    """A real EvidenceCollector with one finalized example, mirroring
    the M02 collector suite's minimal capture."""
    td = pathlib.Path(tempfile.mkdtemp())
    st = store_mod.Store(td / "v2.db", backup_dir=td / "backups")
    rec = Recorder()
    consent = training.ConsentManager(st, rec)
    consent.set("enabled", note="m08 test")
    collector = training.EvidenceCollector(st, rec, consent,
                                           lambda: {"policy": "test"})
    ctx = collector.job_started(
        ids.new_id("job"), ids.new_id("fam"),
        captured_at_utc=ids.now_utc_iso(), timezone=None,
        utc_offset_minutes=None)
    collector.bind_current(ctx)
    collector.attach_capture_meta(
        ctx, {"device": "test", "duration_sec": 1.0, "voiced_pct": 50.0,
              "trailing_silence_sec": 0.1, "overflow_blocks": 0}, 16000)
    collector.on_asr_result(
        ctx, "raw words", model_id="asr-m", model_revision="r1",
        stage_duration_ms=5.0)
    collector.on_cleaner_observation(
        {"kind": "cleanup", "model_id": "llm-m", "input": "raw words",
         "system_prompt": "SYS", "examples_count": 1, "prompt": "<p>",
         "max_tokens": 8, "output": "Raw words."})
    collector.on_cleanup_result(ctx, "Raw words.", path="llm")
    collector.finalize(ctx)
    return st, collector, ctx


def test_no_edit_window_is_never_a_positive_label():
    """AC06: a quiet window ends window_elapsed/no_edit_observed and the
    envelope's correctness stays unreviewed — never a verified
    positive."""
    env = Env()
    result, obs = env.insert("observed text")
    assert result.state == "confirmed", result.state
    assert obs is not None, "a confirmed (certified) insert observes"
    settle_observer(obs)
    assert obs.stop_reason == "window_elapsed"
    assert obs.edited is False
    row = env.observation_row(obs)
    assert row[0] == "window_elapsed" and row[1] == 0
    st, collector, ctx = collector_env()
    collector.on_insertion_result(ctx, result)
    collector.on_observation_closed(ctx, result, obs)
    env_outcome = st.latest_revision(st.latest_example()[0])["outcome"]
    assert env_outcome["insertion"] == "confirmed"
    assert env_outcome["correctness"] == "unreviewed", \
        "no-edit interval must not create a correctness label"
    assert env_outcome["observation"]["no_edit_observed"] is True
    assert env_outcome["observation"]["edited"] is False
    assert "preference" not in json.dumps(env_outcome).lower()
    st.close()
    env.close()
    print("ok  no-edit window: recorded, never a positive label")


def test_typing_outside_range_reanchors_without_attribution():
    """AC05: changes outside the owned region are not scraped — the
    range re-anchors and no edit is attributed."""
    env = Env()
    result, obs = env.insert("owned words")
    time.sleep(0.15)
    env.target.type_text("before ", at=0)     # user types before it
    settle_observer(obs)
    assert obs.stop_reason == "window_elapsed"
    assert obs.edited is False, "outside-range typing is not our edit"
    assert obs.reanchors >= 1
    row = env.observation_row(obs)
    assert row[3] >= 1 and row[1] == 0
    assert row[4] is None and row[5] is None, "no edit artifacts"
    env.close()
    print("ok  typing outside range: re-anchored, not attributed")


def test_edit_inside_owned_range_recorded_with_attribution():
    """AC05: a delayed correction inside the range is captured with
    before/after artifacts and exact job/region attribution."""
    env = Env(window=2.0)
    job_id = "job-edit"
    result, obs = env.insert("the qwen release", job_id=job_id)
    time.sleep(0.6)                            # a delayed correction
    env.target.set_content("the Qwen release")  # one word fixed inside
    settle_observer(obs)
    assert obs.stop_reason == "owned_range_edited"
    assert obs.edited is True
    row = env.observation_row(obs)
    assert row[1] == 1 and row[0] == "owned_range_edited"
    assert row[4] and row[5], "before/after artifacts recorded"

    def artifact_job(art_id):
        return env.store.submit(
            lambda conn: conn.execute(
                "SELECT job_id, role, meta_json FROM artifacts"
                " WHERE artifact_id=?", (art_id,)).fetchone())
    before, after = artifact_job(row[4]), artifact_job(row[5])
    assert before[0] == job_id and after[0] == job_id, \
        "exact job attribution"
    assert before[1] == "observation_before_range"
    assert after[1] == "observation_after_range"
    env.close()
    print("ok  in-range edit: before/after artifacts, exact attribution")


def test_unrelated_paste_over_range_is_an_observed_edit():
    """EV-20: a pasted replacement over the owned region is observed
    with the replaced content as the after-text — an observation, never
    a correctness/preference judgment."""
    env = Env(window=2.0)
    result, obs = env.insert("our dictation")
    time.sleep(0.3)
    tgt = env.target
    tgt.set_content(tgt.content[:0] + "PASTED OVER" + tgt.content[13:])
    settle_observer(obs)
    assert obs.edited is True and obs.stop_reason == "owned_range_edited"
    row = env.observation_row(obs)
    after = env.store.submit(
        lambda conn: conn.execute(
            "SELECT content_text FROM artifacts WHERE artifact_id=?",
            (row[5],)).fetchone())
    assert after[0] == "PASTED OVER"
    env.close()
    print("ok  unrelated paste over range: observed as an edit")


def test_selection_movement_is_not_an_edit():
    """EV-19 selection races: moving the caret/selection changes
    nothing in the owned range — the window continues unedited."""
    env = Env()
    result, obs = env.insert("stable words")
    time.sleep(0.2)
    env.target.selection = (3, 3)     # selection race mid-window
    time.sleep(0.2)
    env.target.selection = (0, 5)
    settle_observer(obs)
    assert obs.edited is False
    assert obs.stop_reason == "window_elapsed"
    env.close()
    print("ok  selection movement: not an edit")


def test_stop_conditions_end_the_window():
    """S29.8 stop reasons: a new dictation, focus loss and a secure-
    field transition each end observation with a recorded reason."""
    # New dictation (the coordinator's note_new_dictation)
    env = Env(window=3.0)
    result, obs = env.insert("stop one")
    time.sleep(0.2)
    env.service.note_new_dictation()
    settle_observer(obs)
    assert obs.stop_reason == "new_dictation"
    env.close()
    # Focus loss (user switched apps)
    env = Env(window=3.0)
    result, obs = env.insert("stop two")
    time.sleep(0.2)
    env.target.frontmost_info = {"bundle": "other", "pid": 99,
                                 "name": "Other"}
    settle_observer(obs)
    assert obs.stop_reason == "focus_lost"
    env.close()
    # Secure-field transition
    env = Env(window=3.0)
    result, obs = env.insert("stop three")
    time.sleep(0.2)
    env.target.role = "AXSecureTextField"
    settle_observer(obs)
    assert obs.stop_reason == "secure_field_transition"
    env.close()
    # Session lock
    env = Env(window=3.0)
    result, obs = env.insert("stop four")
    time.sleep(0.2)
    env.service.note_session_locked()
    settle_observer(obs)
    assert obs.stop_reason == "session_locked"
    env.close()
    print("ok  stop conditions: new dictation, focus, secure field, lock")


def test_undo_of_different_revision_not_ours():
    """EV-20: an application undo that removes the user's OWN typing
    (not LocalFlow's insert) is never attributed to our revision."""
    env = Env(window=3.0)
    result, obs = env.insert("our sentence")
    time.sleep(0.7)                                 # > one tick
    env.target.type_text("typed by user ", at=0)   # user edits before
    time.sleep(0.7)                                 # tick re-anchors
    assert obs.reanchors >= 1
    env.target.set_content("our sentence")          # app undo of typing
    time.sleep(0.7)
    settle_observer(obs)
    assert obs.edited is False, \
        "an undo of a different revision is not an owned-region edit"
    assert obs.undo_candidate is False
    assert obs.reanchors >= 2, "shift both ways re-anchored"
    env.close()
    print("ok  undo of a different revision: not attributed to ours")


def test_undo_of_our_revision_flagged_weakly():
    """An undo that removes exactly our insert is recorded as an
    undo_candidate — an observation, never approval or a label."""
    env = Env(window=2.2)
    result, obs = env.insert("to be undone")
    time.sleep(0.3)
    env.target.set_content("")            # app undo removed our insert
    settle_observer(obs)
    assert obs.edited is True
    assert obs.undo_candidate is True, \
        "content-based undo inference of our own revision"
    row = env.observation_row(obs)
    assert json.loads(row[6])["undo_candidate"] is True
    env.close()
    print("ok  undo of our revision: weak undo_candidate recorded")


def test_uncertified_surface_reports_unavailable():
    """AC05/AC03: an unreadable surface is never confirmed and never
    polled — the envelope records outcome_observation_unavailable with
    the unreliable_target reason, and no observation row exists."""
    env = Env(FixtureTargetApp(settable=False, ax_readable=False))
    result, obs = env.insert("unobservable")
    assert result.state == "posted_unverified", result.state
    assert result.readback == "unavailable"
    assert obs is None, "uncertified surfaces are never polled"

    def count(conn):
        return conn.execute(
            "SELECT COUNT(*) FROM insertion_observations").fetchone()[0]
    assert env.store.submit(count) == 0
    st, collector, ctx = collector_env()
    collector.on_insertion_result(ctx, result)
    env_outcome = st.latest_revision(st.latest_example()[0])["outcome"]
    assert env_outcome["insertion"] == "posted_unverified"
    assert env_outcome["observation"]["status"] == \
        "outcome_observation_unavailable"
    missing = st.latest_revision(st.latest_example()[0])[
        "missing_reasons"]
    assert missing["outcome_observation"] == "unreliable_target"
    st.close()
    env.close()
    print("ok  uncertified surface: unavailable, never confirmed")


def test_target_bound_undo_never_deletes_newer_edits():
    """AC04: undo applies only when the owned range still holds exactly
    our text; a newer edit degrades to offering the previous text."""
    env = Env(window=0.0)
    # Replacement insert over a recorded selection, then clean undo.
    env.target.content = "keep this REAL part safe"
    env.target.selection = (10, 14)               # "REAL"
    from test_insertion_races import snapshot
    job = {"job_id": "job-undo", "attempt": 1,
           "context_snapshot": snapshot(env.target, selected=(10, 14),
                                        selected_text="REAL")}
    box, done = {}, threading.Event()
    env.service.submit("ACTUAL", job,
                       lambda r: (box.__setitem__("r", r), done.set()))
    assert done.wait(15)
    assert box["r"].state == "confirmed"
    assert env.target.content == "keep this ACTUAL part safe"
    r = env.service.undo_last()
    assert r["outcome"] == "undone", r
    assert env.target.content == "keep this REAL part safe"
    # A newer user edit in the range: undo must NOT delete it.
    env.target.content = "keep this EDITED part safe"
    r2 = env.service.undo_last()
    assert r2["outcome"] == "nothing_to_undo", \
        "the consumed undo record is gone"
    env.close()

    # Stale-range case: fresh insert, then an edit INSIDE the owned
    # range, then undo — the range no longer holds exactly our text, so
    # undo degrades to the non-destructive offer (never deletes it).
    env2 = Env(window=0.0)
    result, _ = env2.insert("our fresh text")
    time.sleep(0.05)
    env2.target.set_content("our FRESH text")    # user edit inside
    r3 = env2.service.undo_last()
    assert r3["outcome"] == "stale_range", r3
    assert env2.target.content == "our FRESH text", \
        "newer user edits survive undo"
    assert env2.target.pb.current_string() is None, \
        "caret-insert undo has no previous text to offer"
    env2.close()
    print("ok  target-bound undo: clean undo; edits never deleted")


def main():
    test_no_edit_window_is_never_a_positive_label()
    test_typing_outside_range_reanchors_without_attribution()
    test_edit_inside_owned_range_recorded_with_attribution()
    test_unrelated_paste_over_range_is_an_observed_edit()
    test_selection_movement_is_not_an_edit()
    test_stop_conditions_end_the_window()
    test_undo_of_different_revision_not_ours()
    test_undo_of_our_revision_flagged_weakly()
    test_uncertified_surface_reports_unavailable()
    test_target_bound_undo_never_deletes_newer_edits()
    print("all insertion attribution tests passed")


if __name__ == "__main__":
    raise SystemExit(main())
