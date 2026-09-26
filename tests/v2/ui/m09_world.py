"""Shared M09 remediation world: synthetic fixtures, a main-thread
dispatcher, latched services and a code stamp.

Everything here is synthetic. Stores are per-Harness temporary
directories (``tests/v2/lifecycle/test_lifecycle.Harness`` repoints
every store/artifact/event/journal path before the coordinator is
configured); texts carry the corpus canaries; audio is built with
numpy. Nothing reads the user's History, audio or logs.

Dispatch
--------
``MainQueue`` replaces ``PyObjCTools.AppHelper.callAfter`` (the one
module object both ``localflow/app.py`` and ``localflow/v2/ui/hub.py``
hold) with a thread-safe queue that only the TEST drains, on its own
thread. These suites run as standalone scripts, so the test thread IS
the process main thread: every Hub refresh and completion then runs on
main exactly as the real run loop would run it. ``drain`` waits for all
admitted query and long-action work before flushing, repeatedly, until
nothing is pending — a truthful drain, not a join on the newest thread.

``MainQueue(inline=True)`` is the isolated NEGATIVE control: callbacks
run on the calling thread (the historical headless shim). It is only
safe together with ``thread_oracle(hub, guard=True)``, which checks the
thread before the real refresh runs and records the violation instead
of touching AppKit off-main.

Latches
-------
``Latch(obj)`` wraps a service; ``hold(name, when, after=True)`` makes
the matching call stop (before or after the real call) until the test
releases it, with an arrival event the test waits on. No sleeps decide
an ordering.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import subprocess
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parents[1] / "lifecycle"))

import numpy as np  # noqa: E402
from PyObjCTools import AppHelper  # noqa: E402

CANARY_A = "M09_CANARY_A_not_user_data"
CANARY_B = "M09_CANARY_B_not_user_data"
CANARY_C = "M09_CANARY_C_not_user_data"
APP_A = "com.example.localflow.m09.targetA"
APP_B = "com.example.localflow.m09.targetB"

QUERY_THREAD = "localflow-hub-query"   # the historical per-query threads
WORK_THREAD = "localflow-hub-work"


def iso(ts: float) -> str:
    t = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def is_main() -> bool:
    return threading.current_thread() is threading.main_thread()


# ---- dispatch -------------------------------------------------------------

class MainQueue:
    def __init__(self, inline=False):
        self.inline = inline
        self._q = collections.deque()
        self._lock = threading.Lock()
        self.dispatched = 0
        self.posted_from = collections.Counter()
        # on_post(fn, args) runs in the POSTING thread right after a
        # callback is queued (a probe can hold that thread there).
        self.on_post = None

    def __enter__(self):
        self._real = AppHelper.callAfter

        def defer(fn, *a, **kw):
            self.posted_from[threading.current_thread().name] += 1
            if self.inline:
                fn(*a, **kw)
                return
            with self._lock:
                self._q.append((fn, a, kw))
            if self.on_post is not None:
                self.on_post(fn, a)

        AppHelper.callAfter = defer
        return self

    def __exit__(self, *exc):
        AppHelper.callAfter = self._real

    def pending(self) -> int:
        with self._lock:
            return len(self._q)

    def flush(self) -> int:
        assert is_main(), "MainQueue.flush must run on the main thread"
        n = 0
        while True:
            with self._lock:
                if not self._q:
                    return n
                fn, a, kw = self._q.popleft()
            fn(*a, **kw)
            n += 1
            self.dispatched += 1

    def discard(self):
        with self._lock:
            self._q.clear()

    def drain(self, state=None, timeout=15.0) -> bool:
        """Wait for every admitted query/long-action, flush on main, and
        repeat until nothing is running or queued."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            join_work(deadline - time.monotonic())
            if state is not None:
                state.wait_for_queries(max(0.1, deadline - time.monotonic()))
            n = self.flush()
            if n == 0 and not busy_threads() and (
                    state is None or _state_idle(state)):
                return True
        return False


def _state_idle(state) -> bool:
    idle = getattr(state, "queries_idle", None)
    if idle is not None:
        return idle()
    t = getattr(state, "_query_thread", None)
    return t is None or not t.is_alive()


def busy_threads():
    return [t for t in threading.enumerate()
            if t.name in (QUERY_THREAD, WORK_THREAD) and t.is_alive()]


def join_work(timeout=10.0):
    deadline = time.monotonic() + max(0.0, timeout)
    for t in busy_threads():
        t.join(max(0.0, deadline - time.monotonic()))


def thread_oracle(hub, guard=False):
    """Record the thread of every Hub refresh (and optionally refuse an
    off-main one BEFORE the real refresh touches AppKit)."""
    log = []
    real = hub._refresh

    def wrapped(*a, **kw):
        main = is_main()
        log.append({"entry": "_refresh", "args": a, "main": main,
                    "thread": threading.current_thread().name})
        if guard and not main:
            return None  # intercepted: no native mutation off-main
        return real(*a, **kw)

    hub._refresh = wrapped
    return log


# ---- latched services ------------------------------------------------------

class Gate:
    def __init__(self, when, after, error=None):
        self.when = when
        self.after = after
        self.error = error
        self.arrived = threading.Event()
        self.release = threading.Event()
        self.hits = 0


class Latch:
    """Proxy a service; calls matching a gate stop until released."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_gates", {})
        object.__setattr__(self, "_fails", {})
        object.__setattr__(self, "calls", [])

    def hold(self, name, when=lambda *a, **k: True, after=True,
             error=None):
        gate = Gate(when, after, error)
        self._gates.setdefault(name, []).append(gate)
        return gate

    def fail(self, name, error, when=lambda *a, **k: True):
        """Matching calls raise ``error`` at once (no hold, no real
        call)."""
        self._fails.setdefault(name, []).append((when, error))

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def call(*a, **kw):
            self.calls.append((name, a, dict(kw),
                               threading.current_thread().name))
            for when, error in self._fails.get(name, ()):
                if when(*a, **kw):
                    raise error
            gate = next((g for g in self._gates.get(name, ())
                         if not g.release.is_set() and g.when(*a, **kw)),
                        None)
            if gate is None:
                return attr(*a, **kw)
            gate.hits += 1
            if not gate.after:
                gate.arrived.set()
                gate.release.wait(30)
            out = attr(*a, **kw)
            if gate.after:
                gate.arrived.set()
                gate.release.wait(30)
            if gate.error is not None:
                raise gate.error
            return out
        return call

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


# ---- synthetic fixtures ------------------------------------------------------

def seed_job(store, text, *, captured, app=None, bundle=None,
             state="insertion_confirmed", mode="llm", applied=None,
             retention="history"):
    job_id, _fam = store.create_job(captured_at_utc=captured,
                                    time_quality="known", state=state)
    raw = store.write_text_artifact(job_id=job_id, stage="asr",
                                    role="raw_transcript", text=text,
                                    retention_class=retention)
    app_id = store.write_text_artifact(
        job_id=job_id, stage="cleanup", role="applied_output",
        text=applied if applied is not None else text,
        retention_class=retention, meta={"cleanup_path": mode})
    if app or bundle:
        store.set_job_target(job_id, app, bundle)
    store.sync()
    return job_id, raw, app_id


def audio_samples(seconds=1.0, rate=16000, freq=440.0):
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    return (0.1 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def seed_example(store, raw, applied=None, *, audio=True, state=None,
                 captured="2026-09-22T10:00:00.000Z"):
    """A training example with retained source/applied text (and
    float32 audio). Returns dict(example_id, job_id, raw, applied,
    audio)."""
    job_id, fam = store.create_job(captured_at_utc=captured,
                                   time_quality="known",
                                   state="insertion_unverified")
    raw_id = store.write_text_artifact(
        job_id=job_id, stage="asr", role="raw_transcript", text=raw,
        retention_class="training")
    app_id = store.write_text_artifact(
        job_id=job_id, stage="cleanup", role="applied_output",
        text=applied if applied is not None else raw,
        retention_class="training", parent_artifact_id=raw_id,
        meta={"cleanup_path": "llm"})
    audio_id = None
    if audio:
        audio_id = store.write_audio_artifact(
            job_id=job_id, stage="capture", samples=audio_samples(),
            sample_rate=16000)
    ex = store.upsert_example(job_id=job_id, family_id=fam)
    arts = {"source_text": raw_id, "applied_output": app_id}
    if audio_id:
        arts["original_audio"] = audio_id
    store.append_revision(ex, {
        "training_schema_version": 1, "example_id": ex, "job_id": job_id,
        "family_id": fam, "attempt": 1, "origin": "live_capture",
        "task_kind": "dictation", "captured_at_utc": captured,
        "time_quality": "known", "artifact_ids": arts,
        "missing_reasons": {}, "annotations": [],
        "outcome": {"insertion": "posted_unverified",
                    "correctness": "unreviewed"},
        "state": "captured_unreviewed"})
    if state is not None:
        store.set_example_state(ex, state)
    store.sync()
    return {"example_id": ex, "job_id": job_id, "raw": raw_id,
            "applied": app_id, "audio": audio_id}


def advance_stage(store, example_id, stage_key, text, role=None):
    """Append a revision whose ``stage_key`` artifact is a NEW immutable
    artifact holding ``text`` (the R1 → R2 source change)."""
    env = json.loads(json.dumps(store.latest_revision(example_id)))
    parent = env.pop("revision_id", None)  # append mints a new one
    job_id = env["job_id"]
    role = role or {"source_text": "raw_transcript",
                    "applied_output": "applied_output"}[stage_key]
    new_id = store.write_text_artifact(
        job_id=job_id, stage="review", role=role, text=text,
        retention_class="training")
    env.setdefault("artifact_ids", {})[stage_key] = new_id
    store.append_revision(example_id, env, parent_revision_id=parent)
    store.sync()
    return new_id


def seed_legacy_db(store, rid, *, raw, cleaned, ts, app=None,
                   bundle=None):
    store.insert_legacy_dictation({
        "id": rid, "ts": ts, "duration_sec": 2.0, "raw_text": raw,
        "cleaned_text": cleaned, "raw_words": len(raw.split()),
        "cleaned_words": len(cleaned.split()), "fixed_words": 0,
        "wpm": 0.0, "app_name": app, "app_bundle": bundle,
        "kind": "dictation"}, "sha-m09-fixture")
    store.sync()
    return f"legacy-db:{rid}"


def seed_legacy_pair(store, raw, cleaned, locator):
    return store.import_legacy_pair(
        raw_text=raw, cleaned_text=cleaned, raw_meta={}, cleaned_meta={},
        source_kind="legacy_log", source_sha="sha-m09-log",
        locator=locator)


def write_events(events_dir, name, records, raw_lines=()):
    p = pathlib.Path(events_dir)
    p.mkdir(parents=True, exist_ok=True)
    with open(p / name, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        for line in raw_lines:
            f.write(line + "\n")
    return p / name


def event(seq, ts, *, boot="a", job=None, level="INFO", name="stage.done",
          **extra):
    rec = {"schema_version": 1,
           "event_id": "evt-" + f"{seq:032x}"[-32:],
           "timestamp_utc": ts, "boot_id": "boot-" + (boot * 32)[:32],
           "session_id": "session-" + (boot * 32)[:32],
           "process_id": 100 if boot == "a" else 200, "sequence": seq,
           "event": name, "level": level}
    if job is not None:
        rec["job_id"] = job
    rec.update(extra)
    return rec


# ---- Hub construction --------------------------------------------------------

class SoundLog:
    def __init__(self):
        self.events = []
        self.fail_play = False

    def factory(self, wav_bytes):
        snd = FakeSound(self, len(wav_bytes))
        self.events.append(("create", snd.sid, len(wav_bytes)))
        return snd

    def live(self):
        return [e for e in self.events]


class FakeSound:
    _n = 0

    def __init__(self, log, nbytes):
        FakeSound._n += 1
        self.sid = FakeSound._n
        self.log = log
        self.nbytes = nbytes
        self.playing = False

    def play(self):
        if self.log.fail_play:
            self.log.events.append(("play_failed", self.sid))
            return False
        self.playing = True
        self.log.events.append(("play", self.sid))
        return True

    def stop(self):
        self.playing = False
        self.log.events.append(("stop", self.sid))

    def isPlaying(self):
        return self.playing


def hub_spec(d, sounds=None, **overrides):
    from localflow.v2.history_queries import HistoryQueryService
    from localflow.v2.training_data import TrainingDataService
    from localflow.v2.ui import ReplayService
    sounds = sounds or SoundLog()
    spec = {
        "store": d.store,
        "history_service": HistoryQueryService(d.store),
        "training_service": TrainingDataService(d.store),
        "diagnostics_provider": d._hub_diagnostics_spec,
        "coordinator": d,
        "replay": ReplayService(sound_factory=sounds.factory),
        "capabilities": d._capability_manifest,
        "styles_service": d._styles,
        "snippets_service": d._snip_store,
        "transforms_service": d._tf_store,
        "notes_service": d._notes_store,
        "insights_service": d._insights,
        "learning_service": d._learning,
        "review_service": d._review,
        "sampling_service": d._sampling,
        "splits_service": d._splits,
        "profile_service": d._profile,
        "export_service": d._exporter,
        "transforms_store": d._tf_store,
    }
    spec.update(overrides)
    return spec, sounds


def build_hub(d, **overrides):
    """A HubController over the harness coordinator's production
    services. The caller owns dispatch (build inside a MainQueue)."""
    from localflow.v2.ui import HubController
    spec, sounds = hub_spec(d, **overrides)
    hub = HubController.alloc().initWithSpec_(spec)
    return hub, sounds


class World:
    """Harness (real AppDelegate over a temporary store) + MainQueue +
    a Hub over the coordinator's production services. Teardown drains
    every admitted task BEFORE the store closes, then drops callbacks
    that would reference the closed store."""

    def __init__(self, durations=(1.0,), build=True, **hub_overrides):
        self.durations = list(durations)
        self.build = build
        self.hub_overrides = hub_overrides
        self.hub = None

    def __enter__(self):
        from test_lifecycle import Harness
        self.h = Harness(durations=self.durations)
        self.d = self.h.d
        self.store = self.h.d.store
        self.mq = MainQueue().__enter__()
        if self.build:
            self.hub, self.sounds = build_hub(self.d, **self.hub_overrides)
            self.mq.drain(self.hub.state)
        return self

    def _state(self):
        hub = self.hub or getattr(self.d, "_hub", None)
        return hub.state if hub is not None else None

    def drain(self):
        assert self.mq.drain(self._state()), "work did not drain"

    def __exit__(self, *exc):
        drained = True
        try:
            drained = self.mq.drain(self._state(), 10)
        finally:
            try:
                if getattr(self.d, "_closing", False):
                    # The app really quit (applicationWillTerminate_):
                    # its store and event writer are already closed.
                    self.h._tmp.cleanup()
                else:
                    self.h.close()
            finally:
                self.mq.discard()
                self.mq.__exit__()
        # A request still stuck at the end is a failure the test's own
        # asserts may not see (unless the test is already failing).
        if exc[0] is None and not drained:
            raise AssertionError("admitted work never drained")
        return False


def open_view(hub, mq, view):
    from localflow.v2.ui.state import VIEWS
    hub._select_view_index(VIEWS.index(view))
    mq.drain(hub.state)


def history_rows(hub):
    data = hub.state.views["history"].get("data") or {}
    return [r for g in data.get("groups", ()) for r in g["rows"]]


def rendered_text(view) -> str:
    return str(view.string())


# ---- provenance --------------------------------------------------------------

def code_stamp(suite):
    import localflow
    root = pathlib.Path(localflow.__file__).resolve().parents[1]

    def git(*a):
        p = subprocess.run(["git", "-C", str(root), *a],
                           capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    status = git("status", "--porcelain", "--untracked-files=no")
    prod = git("status", "--porcelain", "--untracked-files=no", "--",
               "localflow")
    import hashlib
    suite_path = root / suite
    return {"suite": suite,
            # The exact test/driver text that produced these results
            # (the base runs execute this file against base production).
            "suite_sha256": hashlib.sha256(suite_path.read_bytes())
            .hexdigest() if suite_path.is_file() else None,
            "code_root_sha": git("rev-parse", "HEAD"),
            "tracked_files_modified": bool(status) if status is not None
            else None,
            "production_tree_modified": bool(prod) if prod is not None
            else None,
            "localflow_imported_from_root": root.name,
            "python": sys.version.split()[0]}
