"""Synthetic world for the M13 remediation suite, corpus runner and
mutation check (2026-09-27 read-only audit at 4e4be15).

Everything here is synthetic: a fresh temporary store per world, a
frozen clock, sanitized app names, the private pasteboard of
``tests/v2/context/run_isolated``. Nothing reads the live usage store,
real History, notes, the live clipboard or the frontmost application.

Ordering is decided by latches at named seams (a held store writer, a
held method), never by sleeps. A latch records that its seam was
REACHED; a probe whose seam was never reached is invalid, not a pass.

The independent reducer (``reference_aggregates``) recomputes every
``daily_aggregates`` field from the raw fact rows with its own zone
conversion (``zoneinfo`` directly) — never through the production
bucketing helper, recompute or query code.
"""

from __future__ import annotations

import contextlib
import inspect
import json
import pathlib
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
for p in (ROOT, HERE.parent, HERE.parents[1] / "ui",
          HERE.parents[1] / "lifecycle"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import AppKit  # noqa: E402

# Everything that loads this world may drive the real coordinator and
# Hub: refuse to run without the desktop isolation (a private
# pasteboard, no Accessibility, no posted events).
if type(AppKit.NSPasteboard).__name__ != "_PasteboardClass":
    sys.exit("m13_world: run under tests/v2/context/run_isolated.py"
             " (the desktop-isolating runner); refusing to start")

from localflow.v2 import analytics as analytics_mod  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402

from m09_world import MainQueue, code_stamp  # noqa: E402,F401
from m13_oracle import (AGG_FIELDS, compare_aggregates,  # noqa: E402,F401
                        local_day, parse_utc, reference_aggregates)

# The corpus's frozen clock (fixture_conventions.time).
CLOCK_ISO = "2026-09-27T12:00:00.000Z"


def epoch(s: str) -> float:
    return parse_utc(s).timestamp()


CLOCK = epoch(CLOCK_ISO)

# Synthetic canaries: data strings only.
APP_CANARY = "SYNTHETIC_USAGE_CANARY_ALPHA"


class Clock:
    def __init__(self, t=CLOCK):
        self.t = float(t)

    def __call__(self):
        return self.t

    def set_iso(self, s):
        self.t = epoch(s)


def _accepts(fn, name) -> bool:
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


DICTATION = {
    "activity_at_utc": "2026-09-26T15:00:00.000Z", "duration_sec": 60.0,
    "raw_words": 120, "final_words": 120, "insertion_outcome": "confirmed",
    "attempt": 1, "mode": "clean", "app_name": "Synthetic Alpha",
    "app_bundle": "com.synthetic.alpha"}


class AWorld:
    """A temp store with the real AnalyticsStore/InsightsQueryService
    under a frozen clock. ``zone`` is the reporting zone."""

    def __init__(self, zone="UTC", now=CLOCK):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.clock = Clock(now)
        self.events = []
        self.store = store_mod.Store(
            self.tmp / "v2.db", artifacts_dir=self.tmp / "arts",
            backup_dir=self.tmp / "bk", now_fn=self.clock)
        self.zone = zone
        self.analytics = analytics_mod.AnalyticsStore(
            self.store, emit=self._emit, now_fn=self.clock,
            reporting_timezone=zone)
        kw = {}
        if _accepts(analytics_mod.InsightsQueryService.__init__, "now_fn"):
            kw["now_fn"] = self.clock
        self.insights = analytics_mod.InsightsQueryService(
            self.store, self.analytics, **kw)
        self.closed = False

    def _emit(self, name, **kw):
        self.events.append((name, kw))

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.store.close()
        finally:
            self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- writers ------------------------------------------------------------

    def dictation(self, job_id, **kw):
        values = dict(DICTATION)
        values.update(kw)
        return self.analytics.record_dictation_fact(job_id=job_id, **values)

    def transform(self, at="2026-09-26T15:00:00.000Z", **kw):
        values = {"transform_id": "builtin:polish",
                  "task_key": "synthetic-task", "path": "applied",
                  "source_kind": "selection", "source_words": 12,
                  "output_words": 9, "duration_ms": 40.0,
                  "activity_at_utc": at}
        values.update(kw)
        return self.analytics.record_transform_fact(**values)

    def repaste(self, job_id=None, at="2026-09-26T15:00:00.000Z"):
        return self.analytics.record_repaste_fact(job_id=job_id,
                                                  activity_at_utc=at)

    # ---- reads (raw rows, no production reducer) -----------------------------

    def rows(self, kind=None):
        def op(conn):
            cur = conn.execute(
                "SELECT * FROM usage_facts" + (" WHERE kind=?" if kind
                                               else "")
                + " ORDER BY rowid", (kind,) if kind else ())
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        return self.store.submit(op)

    def aggs(self):
        def op(conn):
            cur = conn.execute("SELECT * FROM daily_aggregates"
                               " ORDER BY day_local")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        return self.store.submit(op)

    def zone_meta(self):
        """The durable reporting zone when the store records one
        (schema v12's usage_meta), else None."""
        def op(conn):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE"
                            " type='table' AND name='usage_meta'"
                            ).fetchone() is None:
                return None
            row = conn.execute("SELECT value FROM usage_meta WHERE"
                               " key='reporting_timezone'").fetchone()
            return row[0] if row else None
        return self.store.submit(op)

    def mismatches(self, zone=None, version=None):
        """Differences between the stored aggregate rows and the
        independent reduction (empty list = equal on EVERY field)."""
        zone = zone or self.committed_zone()
        version = version if version is not None else \
            analytics_mod.ALGORITHM_VERSION
        return compare_aggregates(self.aggs(),
                                  reference_aggregates(self.rows(), zone,
                                                       version))

    def committed_zone(self):
        return self.zone_meta() or self.analytics.reporting_timezone

    # ---- writer holds --------------------------------------------------------

    @contextlib.contextmanager
    def hold_writer(self):
        """Occupy the single writer: ops queued while held run in FIFO
        order after release. Yields a Latch whose ``reached`` is set once
        the writer is actually parked."""
        latch = Latch("writer_hold")

        def op(_conn):
            latch.hit()
            latch.release_evt.wait(30)
        self.store.submit(op, wait=False)
        assert latch.reached.wait(10), "writer hold never reached"
        try:
            yield latch
        finally:
            latch.release()


class Latch:
    """A named seam: ``reached`` is set when the code arrives; the code
    then waits until ``release()`` (or proceeds at once when not
    blocking)."""

    def __init__(self, name, block=True):
        self.name = name
        self.block = block
        self.reached = threading.Event()
        self.release_evt = threading.Event()
        self.hits = 0

    def hit(self):
        self.hits += 1
        self.reached.set()
        if self.block:
            self.release_evt.wait(30)

    def release(self):
        self.release_evt.set()


@contextlib.contextmanager
def patched(obj, name, wrapper_factory):
    """Replace ``obj.name`` with ``wrapper_factory(original)`` for the
    block (instance or class attribute)."""
    had_own = name in getattr(obj, "__dict__", {})
    original = getattr(obj, name)
    setattr(obj, name, wrapper_factory(original))
    try:
        yield original
    finally:
        if had_own:
            setattr(obj, name, original)
        else:
            try:
                delattr(obj, name)
            except AttributeError:
                setattr(obj, name, original)


def strict_json(obj) -> str:
    """Serialize with NaN/Infinity refused (json's allow_nan=False):
    every emitted number must be finite."""
    return json.dumps(obj, allow_nan=False, sort_keys=True, default=str)
