"""Synthetic world for the M12 remediation suite, corpus runner and
mutation check (2026-09-26 read-only audit at 114ba58).

Everything here is synthetic: a fresh temporary root per world whose
managed note directory (the store's ``v2-notes``) and an ``outside``
directory holding sentinel files are siblings under that root; scripted
supervisors; the private pasteboard of ``tests/v2/context/run_isolated``.
Nothing reads real notes, History, attachments, the live clipboard or
the frontmost application.

Ordering is decided by latches at named seams (a held store writer, a
held method, a blocked flush worker), never by sleeps. A latch records
that its seam was REACHED; a probe whose seam was never reached is
invalid, not a pass.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import pathlib
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
for p in (ROOT, HERE.parent, HERE.parents[1] / "ui",
          HERE.parents[1] / "lifecycle", HERE.parents[1] / "insertion"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import notes as notes_mod  # noqa: E402

from m09_world import MainQueue, code_stamp  # noqa: E402,F401

# Synthetic canaries: data strings only.
OUTSIDE_BYTES = b"SYNTHETIC-OUTSIDE-SENTINEL-KEEP\n"
KEEP_BYTES = b"SYNTHETIC-PREEXISTING-KEEP\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"SYNTHETIC-IMAGE-PAYLOAD" * 4
PNG2 = b"\x89PNG\r\n\x1a\n" + b"SYNTHETIC-SECOND-IMAGE" * 4
TITLE_CANARY = "SYNTHETIC_TITLE_CANARY"
FILENAME_CANARY = "SYNTHETIC_FILENAME_CANARY.png"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- filesystem effect log (sys.audit; installed once) ---------------------

_FS_EVENTS = ("open", "os.remove", "os.rename", "os.link", "os.rmdir",
              "os.symlink", "os.chmod", "os.truncate")


class _FsLog:
    def __init__(self):
        self.active = None
        self._installed = False

    def install(self):
        if self._installed:
            return

        def hook(event, args):
            log = self.active
            if log is None or event not in _FS_EVENTS:
                return
            rec = [event]
            for a in args:
                if isinstance(a, (bytes, bytearray)):
                    a = os.fsdecode(a)
                if isinstance(a, os.PathLike):
                    a = os.fspath(a)
                rec.append(a if isinstance(a, (str, int, type(None)))
                           else repr(a))
            log.append(tuple(rec))
        sys.addaudithook(hook)
        self._installed = True

    @contextlib.contextmanager
    def record(self):
        self.install()
        log = []
        self.active = log
        try:
            yield log
        finally:
            self.active = None


FS_LOG = _FsLog()


def touched_under(log, root, events=_FS_EVENTS):
    """Absolute paths an event named that resolve under ``root``."""
    root = os.path.realpath(root)
    out = []
    for rec in log:
        if rec[0] not in events:
            continue
        for a in rec[1:]:
            if isinstance(a, str) and os.path.isabs(a):
                rp = os.path.realpath(a)
                if rp == root or rp.startswith(root + os.sep):
                    out.append((rec[0], a))
    return out


def tree_digest(root) -> dict:
    """{relative path: sha256 | 'dir' | 'symlink->target' | 'fifo'} of
    everything under ``root`` (no-follow)."""
    root = pathlib.Path(root)
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = pathlib.Path(dirpath) / name
            rel = str(p.relative_to(root))
            if p.is_symlink():
                out[rel] = "symlink->" + os.readlink(p)
            elif p.is_dir():
                out[rel] = "dir"
            elif p.is_fifo():
                out[rel] = "fifo"
            else:
                out[rel] = sha(p.read_bytes())
    return out


# ---- store seams -----------------------------------------------------------

# Every seam a latch or writer hold actually reached, in order (drivers
# clear it before a probe and report it: a declared barrier that is not
# here was never reached).
REACHED = []


class WriterHold:
    """Block the store's single writer with an admitted op until
    released: everything submitted afterwards queues behind it (FIFO)."""

    def __init__(self, store, name="writer_held"):
        self.store = store
        self.entered = threading.Event()
        self._go = threading.Event()

        def op():
            REACHED.append(name)
            self.entered.set()
            self._go.wait(30)
        store._submit(op, wait=False)
        assert self.entered.wait(10), "writer hold never ran"

    def release(self):
        self._go.set()


def queued(store) -> int:
    with store._cond:
        return len(store._queue)


def wait_queued(store, n, timeout=10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if queued(store) >= n:
            return True
        time.sleep(0.002)
    return False


def wait_for(pred, timeout=10.0) -> bool:
    """Poll a predicate that an EVENT elsewhere makes true (a thread
    finishing, a latch reached) — never a stand-in for ordering."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.002)
    return bool(pred())


@contextlib.contextmanager
def short_submit_timeout(store, seconds=0.2):
    """Shorten the caller's wait on ``store.submit`` so an admitted op
    can outlive its caller (the op itself is never cancelled)."""
    real = store.submit

    def submit(fn, wait=True, timeout=15.0):
        return real(fn, wait=wait, timeout=min(timeout, seconds))
    store.submit = submit
    try:
        yield
    finally:
        store.submit = real


class Latch:
    """Hold a callable at a named seam. ``install(obj, attr)`` wraps
    ``obj.attr``: the first ``times`` calls signal ``reached`` and wait
    for ``release()``; ``fault`` (an exception) is raised instead of
    calling through when set before release."""

    def __init__(self, name, times=1, on_reach=None):
        self.name = name
        self.reached = threading.Event()
        self._go = threading.Event()
        self.fault = None
        self.times = times
        self.calls = 0
        self._restore = None
        # Run the interleaving INSIDE the seam on the reaching thread
        # (deterministic, no second thread): the seam proceeds after it.
        self.on_reach = on_reach
        if on_reach is not None:
            self._go.set()

    def _hold(self):
        REACHED.append(self.name)
        self.reached.set()
        if self.on_reach is not None:
            self.on_reach()
        self._go.wait(30)
        if self.fault is not None:
            raise self.fault

    def install(self, obj, attr, after=False):
        real = getattr(obj, attr)
        latch = self

        def wrapped(*a, **kw):
            latch.calls += 1
            held = latch.calls <= latch.times
            if held and not after:
                latch._hold()
            out = real(*a, **kw)
            if held and after:
                latch._hold()
            return out
        setattr(obj, attr, wrapped)
        self._restore = (obj, attr, real)
        return self

    def wait(self, timeout=10.0) -> bool:
        return self.reached.wait(timeout)

    def release(self, fault=None):
        self.fault = fault
        self._go.set()

    def remove(self):
        if self._restore is not None:
            obj, attr, real = self._restore
            try:
                delattr(obj, attr)
            except AttributeError:
                pass
            if getattr(obj, attr, None) is not real:
                setattr(obj, attr, real)
            self._restore = None


# ---- a note-store world ------------------------------------------------------

class NoteWorld:
    """A temporary root holding the store (``root/app/v2.db``, managed
    notes under ``root/app/v2-notes``) and ``root/outside`` with a
    sentinel file; everything is removed on close."""

    def __init__(self, on_evidence=None):
        self._tmp = tempfile.TemporaryDirectory(prefix="lf-m12-")
        self.root = pathlib.Path(self._tmp.name).resolve()
        self.app = self.root / "app"
        self.app.mkdir()
        self.outside = self.root / "outside"
        self.outside.mkdir()
        self.sentinel = self.outside / "sentinel"
        self.sentinel.write_bytes(OUTSIDE_BYTES)
        self.store = store_mod.Store(self.app / "v2.db",
                                     backup_dir=self.app / "backups")
        self.notes = notes_mod.NoteStore(self.store, on_evidence=on_evidence)

    @property
    def managed(self) -> pathlib.Path:
        return self.notes.attachments_dir

    def sentinel_intact(self) -> bool:
        return self.sentinel.is_file() and not self.sentinel.is_symlink() \
            and self.sentinel.read_bytes() == OUTSIDE_BYTES

    def rows(self, sql, args=()):
        return self.store.submit(lambda db: db.execute(sql, args)
                                 .fetchall())

    def revisions(self, note_id):
        return self.rows(
            "SELECT revision_id, parent_revision_id, origin, trigger_kind,"
            " content_text, content_sha256, source_job_id, spans_json,"
            " meta_json FROM note_revisions WHERE note_id=? ORDER BY rowid",
            (note_id,))

    def set_content_path(self, attachment_id, value):
        self.store.submit(lambda db: db.execute(
            "UPDATE note_attachments SET content_path=? WHERE"
            " attachment_id=?", (value, attachment_id)))

    def close(self):
        try:
            if self.store.lifecycle == "open":
                self.store.close(timeout=5.0)
        finally:
            self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def span_words(content, spans):
    """[(words, origin, job)] each stored span resolves to — computed
    from the final string by whitespace splitting (the declared word
    convention), independent of the production span code."""
    words = content.split()
    out = []
    for sp in spans:
        s, e = int(sp[0]), int(sp[1])
        out.append((words[s:e], sp[2], sp[3] if len(sp) > 3 else None))
    return out


# ---- a Hub world (real coordinator + real Hub, headless) --------------------

class HubWorld:
    """The shared lifecycle Harness (real AppDelegate) with the M11
    transform supervisor and the real Hub, main-thread callbacks queued
    for the test to run. ``close`` settles the Scratchpad's note work
    through the production shutdown seam when it exists, then drains
    queries, then closes the store — the intended lifecycle order."""

    def __init__(self, consent=False, select_scratchpad=True):
        from test_lifecycle import Harness
        import test_scratchpad_hub as tsh
        self.tsh = tsh
        self.mq = MainQueue().__enter__()
        self.h = Harness(durations=[1.0], supervisor=tsh.TFSupervisor())
        self.d = self.h.d
        if consent:
            self.d.consent.set("enabled", note="test")
        self.hub = tsh.make_hub(self.h)
        self.d._hub = self.hub
        self.notes = self.d._notes_store
        self.store = self.d.store
        if select_scratchpad:
            from localflow.v2.ui.state import VIEWS
            self.hub._select_view_index(VIEWS.index("scratchpad"))
        self.drain()

    def drain(self):
        assert self.mq.drain(self.hub.state), "Hub work did not drain"

    def open_note(self, note_id):
        self.hub.state.select_scratchpad_note(note_id)
        self.drain()
        assert self.hub.editor.note_id == note_id, "note did not bind"

    def type(self, text):
        """Replace the editor text the way AppKit would after typing:
        the text storage changes and the delegate hears of it."""
        self.hub.editor.text.setString_(text)
        self.hub.editor.textDidChange_(None)

    def focus(self):
        return self.tsh.focus_editor(self.hub)

    def settle_notes(self, timeout=10.0):
        """Wait for every note operation the editor owns (the repaired
        design exposes ``drain``); the base has no owned inventory."""
        ed = self.hub.editor
        drain = getattr(ed, "drain", None)
        if drain is not None:
            return drain(timeout=timeout)
        return None

    def close(self):
        try:
            try:
                self.settle_notes(5.0)
            except Exception:
                pass
            try:
                self.mq.drain(self.hub.state, 5)
            except Exception:
                pass
            self.mq.discard()
        finally:
            self.mq.__exit__(None, None, None)
            try:
                if not getattr(self.d, "_closing", False):
                    self.h.close()
                else:
                    self.h._tmp.cleanup()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
