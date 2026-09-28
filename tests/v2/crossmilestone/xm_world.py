"""Shared helpers for the cross-milestone remediation suite (the merged
three-audit campaign over 340c566).

Everything is synthetic: temporary stores, fixed canaries, the
``com.synthetic.*`` identities of the M14 world, generated tones. Nothing
reads the live store, History, notes, usage or the user's clipboard (the
Hub/AppKit cases run under ``tests/v2/context/run_isolated.py``, whose
general pasteboard is a private one).

Seams are decided by latches and a writer hold, never sleeps:

- ``WriterHold`` queues ONE op that blocks the single Store writer until
  released, and records that the writer actually reached it. Every op
  admitted after it is queued behind it — admitted, not executed.
- ``caller_timeout`` shortens only the CALLER's wait of every waited
  ``Store.submit``. With the writer held, the wait provably expires and
  the real ``Store._submit`` raises its own ``TimeoutError`` while the
  op stays queued (M02: a timeout is not a cancellation); releasing the
  hold lets it commit. That is the admitted-then-unknown outcome the
  audits describe, produced by production code, not simulated.

Oracles read raw rows with plain SQL through the writer (the sanctioned
read path) and never call the production function under test.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import sqlite3
import sys
import threading

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
for p in (ROOT, HERE.parent, ROOT / "tests" / "v2" / "personalization"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import m14_world as M  # noqa: E402  (the M14 synthetic world)
from m14_world import Latch, code_stamp  # noqa: E402,F401

# Distinct canaries (data strings only).
PRIVATE = "PRIVATE_PHRASE_CANARY_59"
OLD_RAW = "OLDRAWCANARY recovery words"
NEW_FINAL = "NEWFINALCANARY pending words"
ALPHA = "alpha attempt one words"
BETA = "beta attempt two words"


class WriterHold:
    """Block the single Store writer until ``release()``.

    ``__enter__`` returns once the writer is INSIDE the holding op (the
    ``reached`` latch), so every later submit is admitted behind it."""

    def __init__(self, store, name="writer_hold"):
        self.store = store
        self.name = name
        self.reached = threading.Event()
        self._go = threading.Event()
        self.released = False

    def _op(self, _conn):
        self.reached.set()
        assert self._go.wait(60), f"{self.name} never released"

    def __enter__(self):
        self.store.submit(self._op, wait=False)
        assert self.reached.wait(10), f"{self.name}: writer never reached"
        return self

    def release(self):
        self.released = True
        self._go.set()

    def __exit__(self, *exc):
        self.release()


@contextlib.contextmanager
def caller_timeout(store, seconds=0.25):
    """Every waited submission waits at most ``seconds`` (the real
    ``queue.Empty -> TimeoutError`` branch of ``Store._submit``, which
    ``submit`` and the Store's own methods — delete_everywhere, publish
    — all go through)."""
    original = store._submit

    def _submit(fn, wait=False, timeout=15.0):
        return original(fn, wait=wait,
                        timeout=min(timeout, seconds) if wait else timeout)
    store._submit = _submit
    try:
        yield
    finally:
        del store._submit


class hold_at:
    """Admit-then-time-out exactly ONE named writer op: the first
    ``store.submit`` whose op's qualified name contains ``marker`` is
    queued behind a WriterHold and its caller waits only ``seconds``
    (the real ``Store._submit`` TimeoutError); every other submission is
    untouched. ``release()`` lets the held op commit."""

    def __init__(self, store, marker, seconds=0.25):
        self.store, self.marker, self.seconds = store, marker, seconds
        self.hold = None

    def __enter__(self):
        real = self.store.submit

        def submit(fn, wait=True, timeout=15.0):
            name = getattr(fn, "__qualname__", "")
            if self.hold is None and self.marker in name:
                self.hold = WriterHold(self.store, f"hold_at:{self.marker}")
                self.hold.__enter__()
                return real(fn, wait=wait, timeout=self.seconds)
            return real(fn, wait=wait, timeout=timeout)
        self.store.submit = submit
        return self

    def release(self):
        if self.hold is not None:
            self.hold.release()

    def __exit__(self, *exc):
        del self.store.submit
        self.release()

    @property
    def reached(self):
        return self.hold is not None


def rows(store, sql, args=()):
    return store.submit(lambda c: c.execute(sql, args).fetchall())


def one(store, sql, args=()):
    got = rows(store, sql, args)
    return got[0] if got else None


def raw_rows(db_path, sql, args=()):
    """A read of a CLOSED store file (a separate read-only connection;
    never used while a Store owns the file)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def drop_table(db_path, table):
    """The synthetic corruption fixture: remove exactly one table (and
    nothing else) from a CLOSED synthetic store copy."""
    con = sqlite3.connect(db_path)
    try:
        con.execute(f"DROP TABLE {table}")
        con.commit()
    finally:
        con.close()


def strict(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)
