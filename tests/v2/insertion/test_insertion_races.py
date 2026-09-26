"""EV-10 / M08: the insertion race matrix against the instrumented
fixture target (Spec S18, E10).

Every case drives the REAL InsertionService over the fixture: changed
target and changed selection, delayed paste inside and beyond the
settle window, a user copy during restoration (AC02), two queued
results (serialization), partial insertion (AC03: never confirmed),
rich clipboard data with unsupported-format disclosure, cancelled
retry, and the multi-line terminal hazard (AC04).

Run: .venv/bin/python tests/v2/insertion/test_insertion_races.py
"""

import pathlib
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fixture_target import FakePasteboard, FixtureTargetApp  # noqa: E402

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.context.providers import categorize  # noqa: E402
from localflow.v2.context.snapshot import (ContextSnapshot,  # noqa: E402
                                           FieldContext, TargetSnapshot)
from localflow.v2.insertion import service as service_mod  # noqa: E402
from localflow.v2.insertion.service import InsertionService  # noqa: E402


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, level, kw))


class Env:
    def __init__(self, target=None, *, settle=0.6, window=0.0,
                 restore=True):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.store = store_mod.Store(root / "v2.db",
                                     backup_dir=root / "backups")
        self.rec = Recorder()
        self.target = target or FixtureTargetApp()
        self.service = InsertionService(
            host=self.target, pasteboard=self.target.pb,
            keyboard=self.target, store=self.store, emit=self.rec,
            restore_clipboard=restore, observation_window_sec=window,
            settle_sec=settle)

    def close(self):
        self.store.sync()
        self.store.close()
        self.tmp.cleanup()

    def run(self, text, job=None):
        job = job or {"job_id": "job-race", "attempt": 1}
        box, done = {}, threading.Event()

        def on_done(result):
            box["result"] = result
            done.set()

        self.service.submit(text, job, on_done)
        assert done.wait(15), "insertion transaction did not finish"
        return box["result"]

    def run_with_hook(self, text, job, on_post_begin):
        """Run one transaction with an on_post_begin hook — the
        deterministic anchor for mid-flight timing (fires between
        publish and the paste post, on the queue thread)."""
        box, done = {}, threading.Event()

        def on_done(result):
            box["result"] = result
            done.set()

        self.service._on_post_begin = on_post_begin
        try:
            self.service.submit(text, job, on_done)
            assert done.wait(15), "insertion transaction did not finish"
        finally:
            self.service._on_post_begin = None
        return box["result"]


def snapshot(target, *, selected=None, selected_text=None,
             window_title=None, category=None):
    """A ContextSnapshot matching (or deliberately not matching) the
    fixture's live state — the M06 object insertion revalidation eats."""
    if selected is None:
        selected = (0, 0)
    t = TargetSnapshot(
        target_snapshot_id="tsnap-race", app_bundle=target.bundle,
        app_name="Fixture", app_pid=target.pid, denied=False,
        category=category or categorize(target.bundle),
        captured_at_utc="2026-09-22T00:00:00.000Z")
    field = FieldContext(
        role=target.role, subrole=None, classification="text",
        selected_text=selected_text,
        selected_range=tuple(selected))
    return ContextSnapshot(
        context_snapshot_id="csnap-race", stage="pre_decode", target=t,
        field=field, window_title=window_title)


def insertion_row(env, result):
    def op(conn):
        return conn.execute(
            "SELECT state, method, reason_code, verification_json,"
            " clipboard_json FROM insertions WHERE insertion_id=?",
            (result.insertion_id,)).fetchone()
    return env.store.submit(op)


def test_changed_target_routes_to_saved():
    """AC01: an app switch mid-processing must not insert into the new
    frontmost app; the artifact routes to saved history with the offer."""
    env = Env()
    tgt = env.target
    tgt.content = "existing text"
    job = {"job_id": "job-changed", "attempt": 1,
           "context_snapshot": snapshot(tgt)}
    tgt.frontmost_info = {"bundle": "com.other.app", "name": "Other",
                          "pid": 9999}          # user switched apps
    result = env.run("fresh dictation", job)
    assert result.state == "target_changed", result.state
    assert result.reason_code == "revalidation_failed"
    assert result.verification["identity"] == "fail"
    assert tgt.content == "existing text", "nothing may land in the new app"
    assert tgt.pb.current_string() == "fresh dictation", \
        "one-action paste offer stays on the clipboard"
    assert tgt.paste_events == []
    row = insertion_row(env, result)
    assert row[0] == "target_changed" and row[1] == "none"
    env.close()
    print("ok  changed target: saved + offer, nothing inserted")


def test_changed_selection_invalidates_replacement_only():
    """S12: a recorded non-empty selection is replacement authority; a
    moved caret (empty selection) is not a target change."""
    env = Env()
    tgt = env.target
    tgt.content = "replace these old words please"
    tgt.selection = (8, 22)          # "these old words"
    job = {"job_id": "job-repl", "attempt": 1,
           "context_snapshot": snapshot(tgt, selected=(8, 22),
                                        selected_text="these old words")}
    tgt.selection = (29, 29)         # selection vanished — caret only
    result = env.run("brand new words", job)
    assert result.state == "target_changed"
    assert result.verification["selection"] == "fail"
    assert "brand new words" not in tgt.content
    # The same moved caret with an EMPTY recorded selection is fine:
    # the caret is the insertion point; queued results rely on it.
    tgt2 = FixtureTargetApp()
    env2 = Env(tgt2)
    job2 = {"job_id": "job-caret", "attempt": 1,
            "context_snapshot": snapshot(tgt2, selected=(0, 0))}
    tgt2.content = "hello "
    tgt2.selection = (6, 6)          # caret moved; still same field
    r2 = env2.run("world", job2)
    assert r2.state == "confirmed", r2.state
    assert tgt2.content == "hello world"
    env.close()
    env2.close()
    print("ok  changed selection: replacement invalidated; caret move ok")


def test_delayed_paste_inside_and_beyond_settle():
    """AC01: a laggy target inside the settle window is confirmed and
    restored after consumption; beyond it, ownership is kept so the
    late paste still inserts the RIGHT text (no wrong insert).
    Clipboard path throughout (``settable=False`` — no AX writes)."""
    env = Env(FixtureTargetApp(settable=False), settle=0.6)            # lag 0.25 < settle
    env.target.paste_lag = 0.25
    env.target.pb.user_copy("user original")
    r = env.run("lands correctly", {"job_id": "job-lag-in", "attempt": 1,
                                    "context_snapshot": snapshot(env.target)})
    assert r.state == "confirmed", (r.state, r.readback)
    assert env.target.content == "lands correctly"
    assert env.target.pb.current_string() == "user original", \
        "restore happens after the laggy target consumed the paste"
    env.close()

    env2 = Env(FixtureTargetApp(settable=False), settle=0.6)           # lag 0.9 > settle: readback pending
    env2.target.paste_lag = 0.9
    env2.target.pb.user_copy("user original 2")
    r2 = env2.run("still the right text", {"job_id": "job-lag-out",
                                           "context_snapshot":
                                               snapshot(env2.target),
                                           "attempt": 1})
    assert r2.state == "posted_unverified", r2.state
    assert r2.readback == "mismatch", r2.readback
    assert r2.clipboard["restore_skipped_reason"] == "readback_pending"
    deadline = time.monotonic() + 3
    while env2.target.content == "" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert env2.target.content == "still the right text", \
        "the late paste read LocalFlow's owned generation — right text"
    env2.close()
    print("ok  delayed paste: in-window confirmed; beyond window kept"
          " ownership so the late paste is still correct")


def test_user_copy_during_restoration_wins():
    """AC02: a user copy while LocalFlow still holds the pasteboard
    survives — the restore is skipped, the user's content is intact at
    the end. Uses the full-settle (unreadable-surface) path; the copy
    thread anchors on the post-begin hook (publish happened) rather
    than a clock sleep, so the race is deterministic under load."""
    env = Env(FixtureTargetApp(settable=False, ax_readable=False),
              settle=0.6)
    env.target.paste_lag = 0.1       # target consumes early
    env.target.pb.user_copy("precious user text")
    published = threading.Event()

    def user_copies_midflight():
        # After publish + consumption, before the 0.6 s ownership check.
        published.wait(5)
        time.sleep(0.3)
        env.target.pb.user_copy("USER COPIED MIDFLIGHT")

    threading.Thread(target=user_copies_midflight, daemon=True).start()

    def on_post_begin():
        published.set()

    r = env.run_with_hook(
        "dictated text", {"job_id": "job-copy", "attempt": 1},
        on_post_begin)
    assert r.state == "posted_unverified", r.state
    assert r.readback == "unavailable", r.readback
    assert r.clipboard["restore_skipped_reason"] == "user_copy_won"
    assert env.target.pb.current_string() == "USER COPIED MIDFLIGHT", \
        "a user copy always wins over restoration"
    assert env.target.content == "dictated text"
    env.close()
    print("ok  user copy during restoration wins (AC02)")


def test_two_queued_results_serialize_in_order():
    """AC01: two finishing jobs share ONE queue — no interleaved
    clipboard transactions, order preserved, single restore at the end."""
    env = Env(FixtureTargetApp(settable=False), settle=0.35)
    env.target.paste_lag = 0.05
    env.target.pb.user_copy("user original")
    results = []
    lock = threading.Lock()

    def on_done(r):
        with lock:
            results.append(r)

    env.service.submit("first dictation. ",
                       {"job_id": "job-q1", "attempt": 1}, on_done)
    env.service.submit("second dictation.",
                       {"job_id": "job-q2", "attempt": 1}, on_done)
    deadline = time.monotonic() + 15
    while len(results) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(results) == 2
    assert env.target.content == "first dictation. second dictation."
    # The pasteboard op log proves serialization: after the initial user
    # copy, the pattern is publish → restore → publish → restore with no
    # interleaving (a second transaction never publishes before the
    # previous one restored).
    ops = [o[0] for o in env.target.pb.ops]
    assert ops == ["write_text", "write_text", "write_items",
                   "write_text", "write_items"], ops
    assert env.target.pb.current_string() == "user original"
    env.close()
    print("ok  two queued results: serialized, ordered, restored once")


def test_partial_insertion_is_never_confirmed():
    """AC03: a target that keeps only part of the paste (max-length
    field) reads back partial — posted_unverified, never confirmed."""
    env = Env(FixtureTargetApp(settable=False))
    env.target.paste_truncate = 5
    r = env.run("a much longer sentence", {"job_id": "job-partial",
                                           "attempt": 1})
    assert r.state == "posted_unverified"
    assert r.readback == "partial", r.readback
    assert r.reason_code == "readback_partial"
    assert env.target.content == "a muc"
    assert r.inserted_chars == len("a much longer sentence")
    env.close()
    print("ok  partial insertion: honest partial readback, not confirmed")


def test_rich_data_preserved_and_unsupported_disclosed():
    """AC02/E10: supported representations (text, RTF, PNG) are
    restored; a file promise is reported unsupported, never claimed.
    Clipboard path (no AX writes)."""
    env = Env(FixtureTargetApp(settable=False))
    env.target.pb.user_copy(items=[
        [("public.utf8-plain-text", b"styled text"),
         ("public.rtf", b"{\\rtf1 styled}")],
        [("public.png", b"\x89PNG-fake-bytes"),
         ("com.apple.pasteboard.promised-file-url",
          b"file:///Users/x/report.pdf")],
    ])
    r = env.run("plain insert", {"job_id": "job-rich", "attempt": 1,
                                 "context_snapshot": snapshot(env.target)})
    assert r.state == "confirmed"
    restored = set(r.clipboard["restored_types"])
    assert restored == {"public.utf8-plain-text", "public.rtf",
                        "public.png"}, r.clipboard
    assert "com.apple.pasteboard.promised-file-url" in \
        r.clipboard["unsupported_types"], "the promise is disclosed"
    assert env.target.pb.data_for_type("public.rtf") == \
        b"{\\rtf1 styled}"
    assert env.target.pb.data_for_type("public.png") == \
        b"\x89PNG-fake-bytes"
    assert env.target.pb.data_for_type(
        "com.apple.pasteboard.promised-file-url") is None, \
        "a one-shot promise cannot round trip — and is not claimed"
    env.close()
    print("ok  rich data: supported restored, promise disclosed")


def test_cancelled_retry_never_pastes():
    """EV-10 cancelled retry: authority was revoked before the
    transaction started — no publish, no paste, no clipboard touch."""
    env = Env()
    env.target.pb.user_copy("user original")
    job = {"job_id": "job-cancelled", "attempt": 2, "cancelled": True,
           "context_snapshot": snapshot(env.target)}
    r = env.run("must not appear", job)
    assert r.state == "saved_not_inserted"
    assert r.reason_code == "user_cancelled"
    assert env.target.content == ""
    assert env.target.pb.current_string() == "user original"
    assert len(env.target.pb.ops) == 1, \
        "the transaction added no clipboard op beyond the user copy"
    env.close()
    print("ok  cancelled retry: no transaction at all")


def test_terminal_multiline_guards_and_single_line_inserts():
    """AC04: an uncertified terminal + multi-line text offers copy only
    (non-execution by default); single-line terminal text inserts; a
    certified bracketed-paste surface may take the multi-line insert."""
    env = Env()
    term = FixtureTargetApp(bundle="com.apple.Terminal")
    env_t = Env(term)
    job = {"job_id": "job-term", "attempt": 1,
           "context_snapshot": snapshot(term)}
    r = env_t.run("git add -A\ngit commit -m 'wip'\n", job)
    assert r.state == "saved_not_inserted", r.state
    assert r.reason_code == "multiline_terminal_unverified"
    assert term.content == "", "no newline-carrying paste into a shell"
    assert "git commit" in term.pb.current_string(), \
        "preview/copy offer holds the text"
    # Single line into the same terminal is ordinary insertion:
    term2 = FixtureTargetApp(bundle="com.apple.Terminal")
    env_t2 = Env(term2)
    r2 = env_t2.run("git status",
                    {"job_id": "job-term1", "attempt": 1,
                     "context_snapshot": snapshot(term2)})
    assert r2.state == "confirmed", r2.state
    assert term2.content == "git status"
    # A certified bracketed-paste surface may accept multi-line text:
    old = service_mod.CERTIFIED_BRACKETED_SURFACES
    service_mod.CERTIFIED_BRACKETED_SURFACES = ("terminal",)
    try:
        term3 = FixtureTargetApp(bundle="com.apple.Terminal")
        env_t3 = Env(term3)
        r3 = env_t3.run("echo one\necho two\n",
                        {"job_id": "job-term-c", "attempt": 1,
                         "context_snapshot": snapshot(term3)})
        assert r3.state == "confirmed", r3.state
        assert term3.content == "echo one\necho two\n"
        env_t3.close()
    finally:
        service_mod.CERTIFIED_BRACKETED_SURFACES = old
    env.close()
    env_t.close()
    env_t2.close()
    print("ok  terminal: multiline guarded (copy offer), single line and"
          " certified surfaces insert")


def test_ax_untrusted_degrades_to_copy_only():
    """V1 recovery parity: without Accessibility trust the transcript
    is left for a manual ⌘V and the result says saved_not_inserted."""
    env = Env()
    env.target.settable = False

    class Untrusted(env.target.__class__):
        def is_trusted(self):
            return False

    env.target.__class__ = Untrusted
    r = env.run("manual paste me", {"job_id": "job-untrusted",
                                    "attempt": 1})
    assert r.state == "saved_not_inserted"
    assert r.reason_code == "accessibility_not_trusted"
    assert env.target.pb.current_string() == "manual paste me"
    assert env.target.content == ""
    env.close()
    print("ok  AX untrusted: copy-only offer, honest state")


def test_terminal_guard_without_context_snapshot():
    """Review critical: the guard must never depend on the context
    collector having been available — with no snapshot on the job, the
    LIVE frontmost bundle is classified and multi-line text still gets
    the copy-only offer (context_enabled=false must not let newlines
    paste into a shell)."""
    term = FixtureTargetApp(bundle="com.apple.Terminal")
    env = Env(term)
    r = env.run("echo a\necho b", {"job_id": "job-term-nc",
                                   "attempt": 1})   # no snapshot at all
    assert r.state == "saved_not_inserted", r.state
    assert r.reason_code == "multiline_terminal_unverified"
    assert term.content == ""
    assert "echo a" in term.pb.current_string()
    env.close()
    print("ok  terminal guard fires from the live bundle when the job"
          " carries no snapshot")


def test_preexisting_identical_text_never_confirms_clipboard_paste():
    """Review critical: dictating text that already sits at the caret
    (re-dictated phrase) must not confirm off the pre-existing content,
    and the restore must not run while the paste may still be pending."""
    env = Env(FixtureTargetApp(settable=False), settle=0.3)
    tgt = env.target
    tgt.paste_lag = 0.25
    tgt.set_content("hello world")     # caret reset to end
    tgt.selection = (6, 6)             # caret right before "world"
    r = env.run("world", {"job_id": "job-amb", "attempt": 1})
    assert r.state == "posted_unverified", r.state
    assert r.readback in ("match_ambiguous",), r.readback
    assert r.reason_code == "readback_match_ambiguous"
    assert r.clipboard["restore_skipped_reason"] == "readback_ambiguous"
    deadline = time.monotonic() + 3
    while tgt.content != "hello worldworld" and \
            time.monotonic() < deadline:
        time.sleep(0.05)
    assert tgt.content == "hello worldworld", \
        "the paste read the owned generation — the right text at the caret"
    env.close()
    print("ok  pre-existing identical text: ambiguous, never confirmed,"
          " ownership kept")


def test_session_lock_releases_on_wake():
    """Review critical: a lock is a state, not a one-way event — after
    wake/unlock, observation windows run again instead of dying at
    tick 0 for the rest of the process."""
    env = Env(window=1.2)

    def observed_insert(text, job_id):
        box, done = {}, threading.Event()

        def on_done(r):
            box["result"] = r
            done.set()

        def on_observation(info):
            box["observer"] = info["observer"]

        env.service.submit(text, {"job_id": job_id, "attempt": 1,
                                  "context_snapshot": snapshot(env.target),
                                  "observation_consent": True},
                           on_done, on_observation=on_observation)
        assert done.wait(15)
        return box.get("result"), box.get("observer")

    env.service.note_session_locked()
    r1, obs1 = observed_insert("before sleep", "job-lock-1")
    assert r1.state == "confirmed"
    assert obs1 is not None
    obs1.join(3)
    assert obs1.stop_reason == "session_locked", obs1.stop_reason
    time.sleep(0.2)
    env.service.note_session_unlocked()   # didWake_
    r2, obs2 = observed_insert("after wake", "job-lock-2")
    assert r2.state == "confirmed"
    assert obs2 is not None
    obs2.join(5)
    assert obs2.stop_reason == "window_elapsed", obs2.stop_reason
    assert obs2.ticks >= 1, "the window actually observed after unlock"
    env.close()
    print("ok  session lock re-arms on wake")


def main():
    test_changed_target_routes_to_saved()
    test_changed_selection_invalidates_replacement_only()
    test_delayed_paste_inside_and_beyond_settle()
    test_user_copy_during_restoration_wins()
    test_two_queued_results_serialize_in_order()
    test_partial_insertion_is_never_confirmed()
    test_rich_data_preserved_and_unsupported_disclosed()
    test_cancelled_retry_never_pastes()
    test_terminal_multiline_guards_and_single_line_inserts()
    test_ax_untrusted_degrades_to_copy_only()
    test_terminal_guard_without_context_snapshot()
    test_preexisting_identical_text_never_confirms_clipboard_paste()
    test_session_lock_releases_on_wake()
    print("all insertion race tests passed")


if __name__ == "__main__":
    raise SystemExit(main())
