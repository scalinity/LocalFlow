"""M12 remediation regressions (the 2026-09-26 read-only audit at
114ba58, findings M12-AUDIT-01..26).

Each case drives a PRODUCTION entry point that exists on both the
audited base and the repair, holds the named seam with a latch where
ordering matters (never a sleep), and asserts an oracle computed from
the fixture — sentinel bytes, the committed revision chain, the private
pasteboard's change count, word ownership resolved from the final
string. A case FAILs on the base for its finding's semantic reason (an
AssertionError naming it); an ERROR (any other exception) is an invalid
probe, never counted as a reproduction.

Run (desktop isolated — private pasteboard, no AX, no event posting):
    .venv/bin/python tests/v2/context/run_isolated.py \
        tests/v2/notes/test_m12_remediation.py [--json OUT] [-k SUBSTR]
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import m12_world as w  # noqa: E402

from AppKit import NSPasteboard  # noqa: E402

from localflow.v2 import note_export  # noqa: E402
from localflow.v2 import notes as notes_mod  # noqa: E402
from localflow.v2.notes import (ORIGIN_DICTATED, ORIGIN_TRANSFORM,  # noqa
                                ORIGIN_TYPED, TRIGGER_AUTOSAVE)

CASES = []


def case(finding, *, native=False):
    def deco(fn):
        fn.finding = finding
        fn.native = native
        CASES.append(fn)
        return fn
    return deco


def board_count():
    return NSPasteboard.generalPasteboard().changeCount()


# ---- helpers ---------------------------------------------------------------

def _attachment(nw, content="note with image"):
    out = nw.notes.create_note(content)
    att = nw.notes.add_attachment(out["note_id"], w.PNG, "image/png",
                                  "pic.png")
    return out["note_id"], att["attachment_id"]


def _content_path(nw, attachment_id):
    row = nw.rows("SELECT content_path FROM note_attachments WHERE"
                  " attachment_id=?", (attachment_id,))
    return row[0][0] if row else None


def _dictate(hw, note_id, caret=None, at_utf16=None):
    """A note-bound PTT through the real coordinator: focus the editor
    (the headless focus seam), optionally place the native caret, press
    and release, run the worker, return (finish fn, args, job)."""
    hw.open_note(note_id)
    assert hw.focus(), "editor focus seam unavailable"
    if at_utf16 is not None:
        hw.hub.editor.text.setSelectedRange_((at_utf16, 0))
    hw.h.press()
    hw.h.release()
    fn, args = hw.h.run_coordinator()
    return fn, args, args[1]


def _latest(world_or_notes, note_id):
    """The current revision read straight from the rows (content, spans)
    — independent of the editor and of ``open_note``'s shaping."""
    store = world_or_notes.store
    row = store.submit(lambda db: db.execute(
        "SELECT r.revision_id, r.content_text, r.spans_json, r.origin"
        " FROM notes n JOIN note_revisions r ON r.revision_id ="
        " n.current_revision_id WHERE n.note_id=?", (note_id,)).fetchone())
    if row is None:
        return {}
    return {"revision_id": row[0], "content": row[1],
            "spans": json.loads(row[2] or "[]"), "origin": row[3]}


def _note(world, note_id):
    """The note row or None (raw read; no production helper)."""
    row = world.store.submit(lambda db: db.execute(
        "SELECT pinned, dirty_at_utc FROM notes WHERE note_id=?",
        (note_id,)).fetchone())
    return None if row is None else {"pinned": bool(row[0]),
                                     "dirty_at_utc": row[1]}


def _job(hw, job_id):
    return hw.store.job(job_id) or {}


def _usage_outcome(hw, job_id):
    rows = hw.store.submit(lambda db: db.execute(
        "SELECT insertion_outcome FROM usage_facts WHERE job_id=? AND"
        " kind='dictation'", (job_id,)).fetchall())
    return [r[0] for r in rows]


def _events(hw):
    """Record coordinator and evidence-collector events (name, kwargs)
    from now on (the collector holds its own emit reference)."""
    log = []
    for owner in (hw.d.v2log, getattr(hw.d, "collector", None)):
        if owner is None or not hasattr(owner, "emit"):
            continue
        real = owner.emit

        def emit(name, *a, _real=real, **kw):
            log.append((name, kw))
            return _real(name, *a, **kw)
        owner.emit = emit
    return log


def _wait_revision(nw_or_hw, note_id, pred, timeout=5.0):
    notes = getattr(nw_or_hw, "notes")
    return w.wait_for(lambda: pred(_latest(notes, note_id)), timeout)


# ============================================================================
# M12-AUDIT-01 — managed attachment path confinement
# ============================================================================

def _confinement_probe(kind):
    """Returns (world, attachment_id, note_id) with the row's persisted
    path replaced by an out-of-root or nonregular variant."""
    nw = w.NoteWorld()
    note_id, att = _attachment(nw)
    managed = nw.managed
    if kind == "parent_traversal":
        nw.set_content_path(att, "../../outside/sentinel")
    elif kind == "absolute":
        nw.set_content_path(att, str(nw.sentinel))
    elif kind == "directory_symlink":
        os.symlink(nw.outside, managed / "jump")
        nw.set_content_path(att, "jump/sentinel")
    elif kind == "final_symlink":
        os.symlink(nw.sentinel, managed / "att-link.png")
        nw.set_content_path(att, "att-link.png")
    elif kind == "fifo":
        os.mkfifo(managed / "att-fifo.png")
        nw.set_content_path(att, "att-fifo.png")
    elif kind == "directory":
        (managed / "att-dir.png").mkdir()
        nw.set_content_path(att, "att-dir.png")
    return nw, att, note_id


def _read_bounded(nw, att, seconds=3.0):
    """attachment_payload in a thread: a FIFO read blocks forever on the
    base; a still-running read after the bound is a failure, then
    released by opening the FIFO's write end from here."""
    box = {}

    def run():
        try:
            box["out"] = nw.notes.attachment_payload(att)
        except Exception as e:  # noqa: BLE001
            box["exc"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        fifo = nw.managed / "att-fifo.png"
        if fifo.exists():
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
        t.join(5)
        return {"blocked": True}
    return box


@case("M12-AUDIT-01")
def r01a_read_refuses_parent_traversal():
    nw, att, _ = _confinement_probe("parent_traversal")
    try:
        with w.FS_LOG.record() as log:
            out = nw.notes.attachment_payload(att)
        opened = w.touched_under(log, nw.outside, ("open",))
        assert out is None and not opened, \
            f"an out-of-root payload was read (opened={len(opened)})"
    finally:
        nw.close()


@case("M12-AUDIT-01")
def r01b_read_refuses_absolute_and_dir_symlink_and_final_symlink():
    for kind in ("absolute", "directory_symlink", "final_symlink"):
        nw, att, _ = _confinement_probe(kind)
        try:
            with w.FS_LOG.record() as log:
                out = nw.notes.attachment_payload(att)
            read_outside = out == w.OUTSIDE_BYTES or bool(
                w.touched_under(log, nw.outside, ("open",)))
            assert not read_outside and out is None, \
                f"{kind}: the outside sentinel was readable"
        finally:
            nw.close()


@case("M12-AUDIT-01")
def r01c_read_refuses_fifo_and_directory():
    for kind in ("fifo", "directory"):
        nw, att, _ = _confinement_probe(kind)
        try:
            box = _read_bounded(nw, att)
            assert not box.get("blocked"), \
                f"{kind}: the payload read blocked on a nonregular file"
            assert box.get("out") is None and "exc" not in box, \
                f"{kind}: a nonregular payload was not refused ({box})"
        finally:
            nw.close()


@case("M12-AUDIT-01")
def r01d_delete_attachment_keeps_outside_sentinel():
    for kind in ("parent_traversal", "absolute", "directory_symlink"):
        nw, att, _ = _confinement_probe(kind)
        try:
            nw.notes.delete_attachment(att)
            nw.store.sync()
            assert nw.sentinel_intact(), \
                f"{kind}: delete_attachment removed the outside sentinel"
        finally:
            nw.close()


@case("M12-AUDIT-01")
def r01e_delete_note_keeps_outside_sentinel():
    for kind in ("parent_traversal", "absolute", "directory_symlink"):
        nw, att, note_id = _confinement_probe(kind)
        try:
            nw.notes.delete_note(note_id)
            nw.store.sync()
            assert nw.sentinel_intact(), \
                f"{kind}: delete_note removed the outside sentinel"
        finally:
            nw.close()


# ============================================================================
# M12-AUDIT-02 — export destination preservation
# ============================================================================

def _export_world():
    nw = w.NoteWorld()
    out = nw.notes.create_note("x")
    a1 = nw.notes.add_attachment(out["note_id"], w.PNG, "image/png",
                                 "one.png")
    a2 = nw.notes.add_attachment(out["note_id"], w.PNG2, "image/png",
                                 "two.png")
    content = (f"# Title\n\nline\n\n{a1['marker']}\n\n{a2['marker']}\n")
    nw.notes.append_revision(out["note_id"], content, origin=ORIGIN_TYPED,
                             trigger=TRIGGER_AUTOSAVE)
    dest = nw.root / "export"
    dest.mkdir()
    return nw, out["note_id"], dest


class _FailNthWriteOpen:
    """An audit hook that makes the Nth write-mode open (or the Nth
    chmod) raise OSError while armed — the fault is 'the third file
    write cannot happen', whatever the implementation's file names."""

    def __init__(self, n, event="open"):
        self.n = n
        self.event = event
        self.seen = 0
        self.armed = False
        self.fired = False
        sys.addaudithook(self)

    def __call__(self, event, args):
        if not self.armed or event != self.event:
            return
        if event == "open":
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            writing = (isinstance(mode, str) and any(
                c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            if not writing:
                return
        self.seen += 1
        if self.seen == self.n:
            self.fired = True
            self.armed = False
            raise OSError(28, "injected write failure")


_HOOKS = {}


def _hook(key, n, event="open"):
    h = _HOOKS.get(key)
    if h is None:
        h = _HOOKS[key] = _FailNthWriteOpen(n, event)
    h.n, h.seen, h.fired, h.armed = n, 0, False, True
    return h


@case("M12-AUDIT-02")
def r02a_failure_after_first_attachment_keeps_preexisting_files():
    nw, note_id, dest = _export_world()
    try:
        main = dest / "note.md"
        main.write_bytes(w.KEEP_BYTES)
        sib = dest / "note-01.png"
        sib.write_bytes(w.KEEP_BYTES)
        before = w.tree_digest(dest)
        note = nw.notes.open_note(note_id)
        hook = _hook("export3", 3)
        try:
            report = note_export.write_export(main, note, nw.notes,
                                              "markdown")
        finally:
            hook.armed = False
        assert hook.fired, "the injected third write never happened"
        after = w.tree_digest(dest)
        lost = [k for k, v in before.items() if after.get(k) != v]
        assert not lost, f"pre-existing files damaged: {len(lost)}"
        assert report.get("ok") is False, "a failed export claimed ok"
        extra = [k for k in after if k not in before
                 and not k.startswith(".")]
        assert not extra, f"a partial set was left: {len(extra)} files"
    finally:
        nw.close()


@case("M12-AUDIT-02")
def r02b_chmod_failure_keeps_preexisting_main_file():
    nw, note_id, dest = _export_world()
    try:
        main = dest / "note.md"
        main.write_bytes(w.KEEP_BYTES)
        before = w.tree_digest(dest)
        note = nw.notes.open_note(note_id)
        hook = _hook("chmod1", 1, event="os.chmod")
        try:
            report = note_export.write_export(main, note, nw.notes,
                                              "markdown")
        finally:
            hook.armed = False
        assert hook.fired, "the injected chmod failure never happened"
        after = w.tree_digest(dest)
        assert after.get("note.md") == before["note.md"], \
            "the pre-existing main file was replaced by a failed export"
        assert report.get("ok") is False
    finally:
        nw.close()


@case("M12-AUDIT-02")
def r02c_destination_symlink_never_writes_through():
    nw, note_id, dest = _export_world()
    try:
        target = nw.root / "outside" / "sentinel"
        os.symlink(target, dest / "note.md")
        note = nw.notes.open_note(note_id)
        note_export.write_export(dest / "note.md", note, nw.notes,
                                 "markdown")
        assert nw.sentinel_intact(), \
            "export wrote through a destination symlink"
    finally:
        nw.close()


@case("M12-AUDIT-02")
def r02d_unapproved_sibling_is_never_overwritten():
    nw, note_id, dest = _export_world()
    try:
        sib = dest / "note-01.png"
        sib.write_bytes(w.KEEP_BYTES)
        note = nw.notes.open_note(note_id)
        report = note_export.write_export(dest / "note.md", note, nw.notes,
                                          "markdown")
        assert sib.read_bytes() == w.KEEP_BYTES, \
            "a pre-existing sibling file was overwritten"
        assert report.get("ok") is True
        text = (dest / "note.md").read_text()
        # Every image the Markdown names exists with the right bytes.
        import re
        names = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
        got = sorted((dest / n).read_bytes() for n in names)
        assert got == sorted([w.PNG, w.PNG2]), \
            "exported image references do not resolve to the payloads"
    finally:
        nw.close()


# ============================================================================
# M12-AUDIT-03 — a failed outgoing save never discards the only tail
# ============================================================================

def _fail_append(notes):
    real = notes.append_revision
    state = {"armed": True, "calls": 0}

    def failing(*a, **kw):
        if state["armed"]:
            state["calls"] += 1
            raise RuntimeError("injected append failure")
        return real(*a, **kw)
    notes.append_revision = failing
    return state


def _tail_somewhere(hw, note_id, tail):
    revs = hw.store.submit(lambda db: db.execute(
        "SELECT content_text FROM note_revisions WHERE note_id=?",
        (note_id,)).fetchall())
    in_store = any(tail in r[0] for r in revs)
    hw.open_note(note_id)
    in_editor = tail in str(hw.hub.editor.current_content())
    return in_store or in_editor


@case("M12-AUDIT-03")
def r03a_failed_switch_save_keeps_the_tail():
    with w.HubWorld() as hw:
        a = hw.notes.create_note("persisted base")["note_id"]
        b = hw.notes.create_note("other note")["note_id"]
        hw.open_note(a)
        hw.type("persisted base UNIQUE_TAIL_A")
        st = _fail_append(hw.notes)
        hw.hub.state.select_scratchpad_note(b)
        hw.drain()
        assert st["calls"] >= 1, "the outgoing save was never attempted"
        st["armed"] = False
        assert _tail_somewhere(hw, a, "UNIQUE_TAIL_A"), \
            "the failed outgoing save discarded the only newest text"


@case("M12-AUDIT-03")
def r03b_held_then_failed_save_keeps_the_tail():
    with w.HubWorld() as hw:
        a = hw.notes.create_note("persisted base")["note_id"]
        b = hw.notes.create_note("other note")["note_id"]
        hw.open_note(a)
        hw.type("persisted base UNIQUE_TAIL_B")
        latch = w.Latch("append_before_commit").install(
            hw.notes, "append_revision")
        hw.hub.editor.flush_async()
        assert latch.wait(), "the flush never reached persistence"
        hw.hub.state.select_scratchpad_note(b)
        hw.drain()
        latch.release(fault=RuntimeError("injected held failure"))
        w.wait_for(lambda: latch.calls >= 1 and not any(
            t.name == "localflow-notes-autosave" and t.is_alive()
            for t in threading.enumerate()), 5)
        latch.remove()
        hw.settle_notes()
        assert _tail_somewhere(hw, a, "UNIQUE_TAIL_B"), \
            "a held save that then failed lost the only newest text"


# ============================================================================
# M12-AUDIT-04 — attribution against the dirty pre-arrival buffer
# ============================================================================

@case("M12-AUDIT-04")
def r04_typed_prefix_never_gets_dictated_provenance():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("a")["note_id"]
        hw.open_note(n)
        hw.type("typed one a ")
        hw.hub.editor.receive("D", origin=ORIGIN_DICTATED,
                              source_job_id="job-synthetic-d",
                              at_chars=12)
        assert _wait_revision(hw, n, lambda r: r.get("content") ==
                              "typed one a D"), "the arrival never committed"
        hw.settle_notes()
        rev = _latest(hw.notes, n)
        owned = [ws for ws, origin, job in
                 w.span_words(rev["content"], rev["spans"])
                 if origin == ORIGIN_DICTATED]
        flat = [x for ws in owned for x in ws]
        assert flat == ["D"], \
            f"dictated provenance covers {flat!r}, not exactly the arrival"


# ============================================================================
# M12-AUDIT-05 — unlink only after the SQL commit
# ============================================================================

class _FailCommitOnce:
    def __init__(self, db):
        self._db = db
        self.armed = False   # armed by the test after its own install op
        self.fired = False

    def commit(self):
        if self.armed:
            self.armed = False
            self.fired = True
            raise sqlite3.OperationalError("injected commit failure")
        return self._db.commit()

    def __getattr__(self, name):
        return getattr(self._db, name)


def _with_failing_commit(nw, fn):
    """Run ``fn`` with the writer's next commit failing (the writer then
    rolls back). The proxy is installed and removed ON the writer."""
    proxy = {}

    def install():
        proxy["p"] = _FailCommitOnce(nw.store._db)
        nw.store._db = proxy["p"]
    nw.store._submit(install, wait=True)
    proxy["p"].armed = True
    try:
        try:
            fn()
        except Exception:
            pass
    finally:
        def remove():
            nw.store._db = proxy["p"]._db
        nw.store._submit(remove, wait=True)
    return proxy["p"].fired


@case("M12-AUDIT-05")
def r05a_rolled_back_attachment_delete_keeps_payload():
    with w.NoteWorld() as nw:
        note_id, att = _attachment(nw)
        path = nw.managed / _content_path(nw, att)
        assert path.read_bytes() == w.PNG
        fired = _with_failing_commit(
            nw, lambda: nw.notes.delete_attachment(att))
        assert fired, "the injected commit failure never ran"
        live = nw.rows("SELECT purged FROM note_attachments WHERE"
                       " attachment_id=?", (att,))
        assert live and live[0][0] == 0, "the rollback did not keep the row"
        assert path.is_file() and path.read_bytes() == w.PNG, \
            "a rolled-back delete removed a live payload"


@case("M12-AUDIT-05")
def r05b_rolled_back_note_delete_keeps_payload():
    with w.NoteWorld() as nw:
        note_id, att = _attachment(nw)
        path = nw.managed / _content_path(nw, att)
        fired = _with_failing_commit(
            nw, lambda: nw.notes.delete_note(note_id))
        assert fired
        assert _note(nw, note_id) is not None, "rollback lost the note"
        assert path.is_file() and path.read_bytes() == w.PNG, \
            "a rolled-back note delete removed a live payload"


@case("M12-AUDIT-05")
def r05c_failed_unlink_is_durably_pending_and_retried():
    with w.NoteWorld() as nw:
        note_id, att = _attachment(nw)
        path = nw.managed / _content_path(nw, att)
        os.chmod(nw.managed, 0o500)
        try:
            out = nw.notes.delete_note(note_id)
            nw.store.sync()
            pending = nw.rows("SELECT COUNT(*) FROM purge_intents WHERE"
                              " completed_at_utc IS NULL")[0][0]
            still = path.exists()
        finally:
            os.chmod(nw.managed, 0o700)
        assert not still or pending >= 1, \
            "a failed unlink left the payload with no durable pending purge"
        assert not still or (out or {}).get("pending_purges", 0) >= 1, \
            "the deletion reported complete while the payload remained"
        nw.store.reconcile_purges()
        assert not path.exists(), "the pending purge was never retried"


# ============================================================================
# M12-AUDIT-06 — attachment admission and unknown outcome
# ============================================================================

def _managed_files(nw):
    d = nw.managed
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


@case("M12-AUDIT-06")
def r06a_deleted_owner_is_refused():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("gone")["note_id"]
        nw.notes.delete_note(n)
        try:
            nw.notes.add_attachment(n, w.PNG, "image/png", "p.png")
        except Exception:
            pass
        nw.store.sync()
        rows = nw.rows("SELECT COUNT(*) FROM note_attachments WHERE"
                       " note_id=? AND purged=0", (n,))[0][0]
        assert rows == 0, "a deleted note gained a live attachment row"
        assert not _managed_files(nw), \
            "a refused attachment left a payload file"


@case("M12-AUDIT-06")
def r06b_timeout_then_late_commit_keeps_payload():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("owner")["note_id"]
        hold = w.WriterHold(nw.store)
        box = {}

        def call():
            try:
                with w.short_submit_timeout(nw.store, 0.2):
                    box["out"] = nw.notes.add_attachment(
                        n, w.PNG, "image/png", "p.png")
            except Exception as e:  # noqa: BLE001
                box["exc"] = e
        t = threading.Thread(target=call)
        t.start()
        t.join(10)
        hold.release()
        nw.store.sync()
        nw.store.sync()
        live = nw.rows("SELECT attachment_id FROM note_attachments WHERE"
                       " note_id=? AND purged=0", (n,))
        for (aid,) in live:
            assert nw.notes.attachment_payload(aid) == w.PNG, \
                "a committed attachment row lost its payload to cleanup"
        assert live or not _managed_files(nw), \
            "no row committed but a payload file remained"


_CHILD = r"""
import os, pathlib, sys
sys.path.insert(0, sys.argv[1])
from localflow.v2 import store as store_mod
from localflow.v2.notes import NoteStore
root = pathlib.Path(sys.argv[2])
s = store_mod.Store(root / "v2.db")
ns = NoteStore(s)
n = ns.create_note("owner")["note_id"]
real = s.submit
def submit(fn, *a, **kw):
    d = ns.attachments_dir
    if d.exists() and any(d.iterdir()):
        os._exit(0)
    return real(fn, *a, **kw)
s.submit = submit
ns.add_attachment(n, b"\x89PNG-SYNTHETIC-CHILD", "image/png", "p.png")
os._exit(3)
"""


@case("M12-AUDIT-06")
def r06c_crash_after_payload_write_is_reconciled():
    with w.NoteWorld() as nw:
        root = nw.root / "child"
        root.mkdir()
        p = subprocess.run([sys.executable, "-c", _CHILD, str(w.ROOT),
                            str(root)], capture_output=True, timeout=60)
        assert p.returncode == 0, \
            f"the child did not exit at the seam (rc={p.returncode})"
        from localflow.v2 import store as store_mod
        s = store_mod.Store(root / "v2.db")
        try:
            ns = notes_mod.NoteStore(s)
            files = sorted(x.name for x in ns.attachments_dir.iterdir()) \
                if ns.attachments_dir.exists() else []
            rows = {r[0] for r in s.submit(lambda db: db.execute(
                "SELECT content_path FROM note_attachments WHERE"
                " purged=0").fetchall())}
            intents = {r[0] for r in s.submit(lambda db: db.execute(
                "SELECT path FROM purge_intents WHERE completed_at_utc"
                " IS NULL").fetchall())}
            orphans = [f for f in files if f not in rows
                       and f not in intents]
            assert not orphans, \
                f"crash-left payloads with no owner: {len(orphans)}"
        finally:
            s.close()


# ============================================================================
# M12-AUDIT-07 — confirmation follows the committed revision
# ============================================================================

@case("M12-AUDIT-07")
def r07a_held_commit_is_not_confirmed():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("dictate here")["note_id"]
        fn, args, job = _dictate(hw, n)
        latch = w.Latch("note_before_commit").install(
            hw.notes, "append_revision")
        try:
            fn(*args)
            assert latch.wait(), "the note save never reached persistence"
            state = _job(hw, job["job_id"]).get("state")
            usage = _usage_outcome(hw, job["job_id"])
            assert state != "insertion_confirmed", \
                "confirmed before the note revision committed"
            assert "confirmed" not in usage, \
                "usage recorded confirmed before the revision committed"
        finally:
            latch.release()
            latch.remove()
            hw.settle_notes()
            hw.drain()


@case("M12-AUDIT-07")
def r07b_failed_commit_is_never_confirmed():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("dictate here")["note_id"]
        fn, args, job = _dictate(hw, n)
        latch = w.Latch("note_before_commit").install(
            hw.notes, "append_revision")
        fn(*args)
        assert latch.wait()
        latch.release(fault=RuntimeError("injected commit failure"))
        w.wait_for(lambda: not any(
            t.name == "localflow-notes-autosave" and t.is_alive()
            for t in threading.enumerate()), 5)
        latch.remove()
        _fail_append(hw.notes)  # retries fail too: the outcome is failure
        hw.settle_notes(2.0)
        hw.drain()
        state = _job(hw, job["job_id"]).get("state")
        assert state != "insertion_confirmed", \
            "a failed note save is recorded as a confirmed insertion"


@case("M12-AUDIT-07")
def r07c_transform_applied_waits_for_the_revision():
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("polish this text")["note_id"]
        hw.open_note(n)
        hw.focus()
        hw.hub.scratchpad_transforms.selectItemAtIndex_(0)
        hw.hub.scratchpadTransform_(None)
        w.wait_for(lambda: hw.d._tf_active is None, 10)
        hw.drain()
        events = _events(hw)
        latch = w.Latch("note_before_commit").install(
            hw.notes, "append_revision")
        try:
            hw.d._tf_panel.panelAccept_(None)
            assert latch.wait(), "the accepted transform never persisted"
            names = [e[0] for e in events]
            assert "notes.transform_applied" not in names, \
                "transform_applied published before the revision committed"
        finally:
            latch.release()
            latch.remove()
            hw.settle_notes()
            hw.drain()


# ============================================================================
# M12-AUDIT-08 — owned flushes, generation barrier, shutdown drain
# ============================================================================

@case("M12-AUDIT-08")
def r08a_snapshot_does_not_claim_an_uncommitted_generation():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("gen zero")["note_id"]
        hw.open_note(n)
        hw.type("gen zero A")
        latch = w.Latch("autosave_before_commit").install(
            hw.notes, "append_revision")
        hw.hub.editor.flush_async()
        assert latch.wait()
        hw.type("gen zero A B")
        releaser = threading.Timer(0.3, latch.release)
        releaser.start()
        hw.hub.scratchpadSnapshot_(None)
        status = str(hw.hub.scratchpad_status.stringValue())
        committed = _latest(hw.notes, n).get("content") == "gen zero A B"
        releaser.join()
        latch.remove()
        hw.settle_notes()
        claims_saved = "saved" in status and "pending" not in status \
            and "unknown" not in status
        assert committed or not claims_saved, \
            "Snapshot reported saved while generation B was uncommitted"


@case("M12-AUDIT-08")
def r08b_quit_settles_admitted_note_work():
    hw = w.HubWorld()
    db_path = hw.store.db_path
    n = hw.notes.create_note("before quit")["note_id"]
    hw.open_note(n)
    hw.type("before quit QUIT_TAIL")
    latch = w.Latch("autosave_before_admission").install(
        hw.notes, "append_revision")
    hw.hub.editor.flush_async()
    assert latch.wait()
    settle_point = threading.Event()
    real_close = hw.store.close

    def close(*a, **kw):
        settle_point.set()
        return real_close(*a, **kw)
    hw.store.close = close
    ed = hw.hub.editor
    real_drain = getattr(ed, "drain", None)
    if real_drain is not None:
        def drain(*a, **kw):
            settle_point.set()
            return real_drain(*a, **kw)
        ed.drain = drain
    threading.Thread(target=lambda: (settle_point.wait(10),
                                     latch.release()), daemon=True).start()
    hw.mq.discard()
    try:
        hw.d.applicationWillTerminate_(None)
    finally:
        hw.mq.__exit__(None, None, None)
    w.wait_for(lambda: not any(t.name == "localflow-notes-autosave"
                               and t.is_alive()
                               for t in threading.enumerate()), 5)
    from localflow.v2 import store as store_mod
    s = store_mod.Store(db_path)
    try:
        got = s.submit(lambda db: db.execute(
            "SELECT content_text FROM note_revisions WHERE note_id=?"
            " ORDER BY rowid DESC LIMIT 1", (n,)).fetchone())
        dirty = s.submit(lambda db: db.execute(
            "SELECT dirty_at_utc FROM notes WHERE note_id=?",
            (n,)).fetchone())
    finally:
        s.close()
        hw.h._tmp.cleanup()
    assert (got and got[0] == "before quit QUIT_TAIL") or (
        dirty and dirty[0]), \
        "quit closed the store under admitted note work: tail lost unflagged"
    assert got and got[0] == "before quit QUIT_TAIL", \
        "quit did not settle the admitted note save before the store closed"


@case("M12-AUDIT-08")
def r08c_close_during_flush_keeps_the_newer_generation():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("g0")["note_id"]
        hw.open_note(n)
        hw.type("g0 A")
        latch = w.Latch("persist_A").install(hw.notes, "append_revision")
        hw.hub.editor.flush_async()
        assert latch.wait()
        hw.type("g0 A B")
        hw.hub.editor.flush_async()  # the second request while A owns it
        closer = threading.Timer(0.2, latch.release)
        closer.start()
        drain = getattr(hw.hub.editor, "drain", None)
        hw.hub.editor.close()
        closer.join()
        w.wait_for(lambda: not any(t.name == "localflow-notes-autosave"
                                   and t.is_alive()
                                   for t in threading.enumerate()), 5)
        latch.remove()
        if drain is not None:
            drain(timeout=5)
        assert _latest(hw.notes, n).get("content") == "g0 A B", \
            "closing during flush A dropped the admitted generation B"


# ============================================================================
# M12-AUDIT-09 — per-arrival provenance, coherent capture
# ============================================================================

def _no_async(editor):
    """Keep the flush worker from being scheduled (the seam: both
    arrivals land before any worker captures); returns the undo."""
    real = editor.flush_async
    editor.flush_async = lambda *a, **kw: None

    def undo():
        editor.flush_async = real
    return undo


@case("M12-AUDIT-09")
def r09a_two_arrivals_keep_their_own_provenance():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("start")["note_id"]
        hw.open_note(n)
        ed = hw.hub.editor
        restore = _no_async(ed)   # both arrive before any worker captures
        ed.receive(" ALPHA", origin=ORIGIN_DICTATED,
                   source_job_id="job-synthetic-a", at_chars=5)
        ed.receive(" BETA", origin=ORIGIN_TRANSFORM,
                   task_key="ttask:synthetic-b", at_chars=11)
        restore()
        ed.flush_async()
        assert _wait_revision(hw, n, lambda r: r.get("content") ==
                              "start ALPHA BETA")
        hw.settle_notes()
        revs = hw.store.submit(lambda db: db.execute(
            "SELECT origin, source_job_id, task_key, spans_json FROM"
            " note_revisions WHERE note_id=? ORDER BY rowid",
            (n,)).fetchall())
        a_rev = [r for r in revs if r[1] == "job-synthetic-a"]
        assert a_rev and a_rev[0][0] == ORIGIN_DICTATED, \
            "arrival A lost its own revision/provenance to arrival B"
        final = _latest(hw.notes, n)
        owned = {}
        for ws, origin, job in w.span_words(final["content"],
                                            final["spans"]):
            owned.setdefault(origin, []).extend(ws)
        assert owned.get(ORIGIN_DICTATED) == ["ALPHA"], owned
        assert owned.get(ORIGIN_TRANSFORM) == ["BETA"], owned


@case("M12-AUDIT-09")
def r09b_failed_older_arrival_never_overwrites_newer_identity():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("s")["note_id"]
        hw.open_note(n)
        ed = hw.hub.editor
        latch = w.Latch("A_captured").install(hw.notes, "append_revision")
        ed.receive(" AAA", origin=ORIGIN_DICTATED,
                   source_job_id="job-synthetic-a", at_chars=1)
        assert latch.wait(), "arrival A's save never reached persistence"
        ed.receive(" BBB", origin=ORIGIN_TRANSFORM,
                   task_key="ttask:synthetic-b", at_chars=5)
        latch.release(fault=RuntimeError("injected A failure"))
        w.wait_for(lambda: not any(t.name == "localflow-notes-autosave"
                                   and t.is_alive()
                                   for t in threading.enumerate()), 5)
        latch.remove()
        ed.flush_now()
        hw.settle_notes()
        final = _latest(hw.notes, n)
        assert final.get("content") == "s AAA BBB", final.get("content")
        owned = {}
        for ws, origin, job in w.span_words(final["content"],
                                            final["spans"]):
            owned.setdefault(origin, []).extend(ws)
        assert owned.get(ORIGIN_TRANSFORM) == ["BBB"], \
            f"arrival B's identity was overwritten: {owned}"


# ============================================================================
# M12-AUDIT-10 — the autosave timer fires in the ordinary run loop
# ============================================================================

@case("M12-AUDIT-10")
def r10_timer_fires_in_the_default_run_loop():
    from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop
    with w.HubWorld() as hw:
        n = hw.notes.create_note("timer base")["note_id"]
        hw.open_note(n)
        hw.type("timer base TYPED_TIMER_TAIL")
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.1))
            if _latest(hw.notes, n).get("content") == \
                    "timer base TYPED_TIMER_TAIL":
                break
        hw.settle_notes()
        assert _latest(hw.notes, n).get("content") == \
            "timer base TYPED_TIMER_TAIL", \
            "the installed autosave timer never fired in the default mode"


# ============================================================================
# M12-AUDIT-11 — actions use the rendered editor binding
# ============================================================================

def _render_a_select_b(hw):
    a = hw.notes.create_note("note A rendered")["note_id"]
    b = hw.notes.create_note("note B selected")["note_id"]
    hw.open_note(a)
    latch = w.Latch("detail_load").install(hw.notes, "open_note")
    hw.hub.state.select_scratchpad_note(b)
    assert latch.wait(), "B's detail load never started"
    hw.mq.flush()  # the list publication renders; B's detail is held
    return a, b, latch


@case("M12-AUDIT-11")
def r11a_pin_and_delete_never_act_on_an_unrendered_note():
    with w.HubWorld() as hw:
        a, b, latch = _render_a_select_b(hw)
        try:
            assert hw.hub.editor.note_id == a
            hw.hub.scratchpadPin_(None)
            pinned_b = _note(hw, b)["pinned"]
            hw.hub.scratchpadDelete_(None)
            b_alive = _note(hw, b) is not None
        finally:
            latch.release()
            latch.remove()
            hw.drain()
        assert not pinned_b, "Pin acted on the selected, unrendered note"
        assert b_alive, "Delete acted on the selected, unrendered note"


@case("M12-AUDIT-11")
def r11b_add_image_revalidates_after_the_dialog():
    import AppKit
    from Foundation import NSURL
    with w.HubWorld() as hw:
        a = hw.notes.create_note("note A")["note_id"]
        b = hw.notes.create_note("note B")["note_id"]
        hw.open_note(a)
        img = hw.h.tmp / "synthetic.png"
        img.write_bytes(w.PNG)

        class Panel:
            def setCanChooseDirectories_(self, v): pass
            def setCanChooseFiles_(self, v): pass
            def setAllowsMultipleSelection_(self, v): pass

            def runModal(self):
                hw.open_note(b)    # the binding changes behind the modal
                return 1

            def URLs(self):
                return [NSURL.fileURLWithPath_(str(img))]
        real = AppKit.NSOpenPanel
        AppKit.NSOpenPanel = type("P", (), {"openPanel":
                                            staticmethod(Panel)})
        try:
            hw.hub.scratchpadAttach_(None)
        finally:
            AppKit.NSOpenPanel = real
        hw.settle_notes()
        hw.drain()
        owners = [r[0] for r in hw.store.submit(lambda db: db.execute(
            "SELECT note_id FROM note_attachments WHERE purged=0")
            .fetchall())]
        b_text = _latest(hw.notes, b).get("content", "")
        marker_in_b = "attachment:" in b_text
        assert not (owners == [a] and marker_in_b), \
            "the attachment belongs to A but its marker landed in B"
        assert not owners or (owners == [b]) == marker_in_b, \
            "attachment owner and marker note disagree"


# ============================================================================
# M12-AUDIT-12 — UTF-16 caret converted to a code-point anchor
# ============================================================================

@case("M12-AUDIT-12")
def r12_emoji_before_caret_lands_at_the_caret():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("A😀B")["note_id"]
        fn, args, job = _dictate(hw, n, at_utf16=3)
        fn(*args)
        final = job.get("final_text")
        assert final, "the job carried no final text"
        want = "A😀" + final + "B"
        _wait_revision(hw, n, lambda r: r.get("content") in (
            want, "A😀B" + final))
        hw.settle_notes()
        got = _latest(hw.notes, n).get("content")
        assert got == want, "the dictation did not land at the caret"


# ============================================================================
# M12-AUDIT-13 — whole-note transforms refuse a grown note
# ============================================================================

@case("M12-AUDIT-13")
def r13_whole_note_accept_refuses_after_growth():
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("alpha")["note_id"]
        hw.open_note(n)
        hw.focus()
        hw.hub.scratchpad_transforms.selectItemAtIndex_(0)
        hw.hub.scratchpadTransform_(None)
        w.wait_for(lambda: hw.d._tf_active is None, 10)
        hw.drain()
        hw.type("alpha tail")
        hw.hub.editor.flush_now()
        hw.d._tf_panel.panelAccept_(None)
        hw.settle_notes()
        hw.drain()
        got = _latest(hw.notes, n).get("content")
        assert got == "alpha tail", \
            "a whole-note transform replaced part of a note that changed"


# ============================================================================
# M12-AUDIT-14 — History transfer uses the current final stage
# ============================================================================

def _seed_attempts(store, *, purge_final=False):
    job_id, _fam = store.create_job(captured_at_utc="2026-09-25T10:00:00Z",
                                    time_quality="known",
                                    state="insertion_confirmed")
    ids = {}
    for attempt in (1, 2):
        ids[f"raw{attempt}"] = store.write_text_artifact(
            job_id=job_id, stage="asr", role="raw_transcript",
            text=f"raw text attempt {attempt}", retention_class="history",
            meta={"attempt": attempt})
        ids[f"clean{attempt}"] = store.write_text_artifact(
            job_id=job_id, stage="cleanup", role="applied_output",
            text=f"cleaned text attempt {attempt}",
            retention_class="history",
            meta={"attempt": attempt, "cleanup_path": "llm"})
        ids[f"tf{attempt}"] = store.write_text_artifact(
            job_id=job_id, stage="transform", role="transform_output",
            text=f"transformed final attempt {attempt}",
            retention_class="history",
            meta={"attempt": attempt, "path": "applied"})
    # An OLDER attempt's cleaned artifact written last (retained retry
    # debris) — rowid order is not attempt order.
    store.write_text_artifact(
        job_id=job_id, stage="cleanup", role="applied_output",
        text="stale cleaned attempt 1 written late",
        retention_class="history", meta={"attempt": 1})
    store.sync()
    if purge_final:
        store.submit(lambda db: db.execute(
            "UPDATE artifacts SET content_text=NULL, purged=1 WHERE"
            " artifact_id=?", (ids["tf2"],)))
    return job_id


@case("M12-AUDIT-14")
def r14a_copy_uses_the_current_attempt_final_artifact():
    with w.HubWorld(select_scratchpad=False) as hw:
        job_id = _seed_attempts(hw.store)
        out = hw.d.hubSaveHistoryRow("job", job_id)
        nid = out.get("note_id")
        got = _latest(hw.notes, nid).get("content") if nid else None
        assert got == "transformed final attempt 2", \
            "the transfer did not bind to the displayed final artifact"


@case("M12-AUDIT-14")
def r14b_missing_final_is_refused_not_substituted():
    with w.HubWorld(select_scratchpad=False) as hw:
        job_id = _seed_attempts(hw.store, purge_final=True)
        out = hw.d.hubSaveHistoryRow("job", job_id)
        nid = out.get("note_id")
        got = _latest(hw.notes, nid).get("content") if nid else None
        assert got is None, \
            "a missing final stage was replaced by an earlier stage"


# ============================================================================
# M12-AUDIT-15 — note deletion revokes note-derived candidates
# ============================================================================

CANARY = "SYNTHETIC_NOTE_CANARY"


def _live_canaries(hw):
    return hw.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM artifacts WHERE purged=0 AND content_text"
        " LIKE ?", (f"%{CANARY}%",)).fetchone()[0])


def _transform_note(hw, n):
    hw.open_note(n)
    hw.focus()
    hw.hub.scratchpad_transforms.selectItemAtIndex_(0)
    hw.hub.scratchpadTransform_(None)
    w.wait_for(lambda: hw.d._tf_active is None, 10)


@case("M12-AUDIT-15")
def r15a_delete_purges_the_note_transform_graph():
    with w.HubWorld(consent=True) as hw:
        hw.h.d.supervisor.transform_output = f"{CANARY} OUTPUT"
        n = hw.notes.create_note(f"{CANARY} source words")["note_id"]
        _transform_note(hw, n)
        hw.drain()
        assert _live_canaries(hw) >= 1, \
            "no candidate artifacts were recorded (positive population)"
        hw.hub.scratchpadDelete_(None)
        hw.drain()
        assert _note(hw, n) is None, "the note was not deleted"
        assert _live_canaries(hw) == 0, \
            "note-derived transform artifacts survived the note's deletion"


@case("M12-AUDIT-15")
def r15b_late_candidate_cannot_republish_a_deleted_note():
    with w.HubWorld(consent=True) as hw:
        hw.h.d.supervisor.transform_output = f"{CANARY} LATE"
        n = hw.notes.create_note(f"{CANARY} late source")["note_id"]

        def delete_now():
            payload = hw.notes.delete_note(n)
            hw.d.hubNoteDeleted(payload)
        latch = w.Latch("before_record_candidate", on_reach=delete_now)
        latch.install(hw.d._tf_store, "record_candidate")
        _transform_note(hw, n)
        hw.drain()
        latch.remove()
        assert latch.reached.is_set(), "publication was never reached"
        assert _note(hw, n) is None
        assert _live_canaries(hw) == 0, \
            "a late producer recreated a deleted note's content"


# ============================================================================
# M12-AUDIT-16 — evidence callbacks: idempotent, fenced by deletion
# ============================================================================

def _dictated_note_with_example(hw):
    """A job with a training example (consent on), and a note revision
    attributed to it through the production arrival path."""
    n = hw.notes.create_note("evidence base")["note_id"]
    fn, args, job = _dictate(hw, n)
    return n, fn, args, job


def _open_links(hw, note_id):
    return hw.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM note_evidence_links WHERE note_id=? AND"
        " closed_utc IS NULL", (note_id,)).fetchone()[0])


def _note_observations(hw, job_id, revision_id=None):
    env = hw.store.submit(lambda db: db.execute(
        "SELECT r.envelope_json FROM training_examples e JOIN"
        " training_revisions r ON r.revision_id = e.latest_revision_id"
        " WHERE e.job_id=?", (job_id,)).fetchone())
    if not env:
        return None
    notes = json.loads(env[0]).get("notes") or []
    return [o for o in notes if revision_id is None
            or o.get("note_revision_id") == revision_id]


@case("M12-AUDIT-16")
def r16a_late_callback_cannot_reopen_a_deleted_note():
    with w.HubWorld(consent=True) as hw:
        n, fn, args, job = _dictated_note_with_example(hw)

        def delete_now():
            payload = hw.notes.delete_note(n)
            hw.d.hubNoteDeleted(payload)
        latch = w.Latch("evidence_before_admission", on_reach=delete_now)
        latch.install(hw.notes, "on_evidence")
        fn(*args)
        hw.settle_notes()
        w.wait_for(lambda: latch.reached.is_set(), 5)
        hw.drain()
        assert latch.reached.is_set(), "the evidence callback never ran"
        assert _note(hw, n) is None
        assert _open_links(hw, n) == 0, \
            "a late evidence callback reopened a deleted note's link"


@case("M12-AUDIT-16")
def r16b_same_revision_event_counts_once():
    with w.HubWorld(consent=True) as hw:
        n, fn, args, job = _dictated_note_with_example(hw)
        seen = []
        real = hw.notes.on_evidence

        def record(event):
            seen.append(dict(event))
            return real(event)
        hw.notes.on_evidence = record
        fn(*args)
        hw.settle_notes()
        w.wait_for(lambda: seen, 5)
        hw.drain()
        assert seen, "no evidence event (positive population)"
        rev = seen[0]["revision_id"]
        first = _note_observations(hw, job["job_id"], rev)
        assert first, "the first delivery recorded nothing"
        real(seen[0])   # the exact same logical event, redelivered
        again = _note_observations(hw, job["job_id"], rev)
        assert len(again) == len(first), \
            "a redelivered revision event added a second observation"


# ============================================================================
# M12-AUDIT-17 — ambiguous repeated words abstain
# ============================================================================

@case("M12-AUDIT-17")
def r17_surviving_typed_echo_is_not_dictated():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("")["note_id"]
        nw.notes.append_revision(n, "echo", origin=ORIGIN_DICTATED,
                                 trigger="system",
                                 source_job_id="job-synthetic-echo",
                                 inserted_at_chars=0, inserted_text="echo")
        nw.notes.append_revision(n, "echo echo", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        # The user deletes the FIRST (dictated) echo; the typed one stays.
        nw.notes.append_revision(n, "echo", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        rev = _latest(nw, n)
        assert rev["content"] == "echo"
        dictated = [ws for ws, o, j in w.span_words(rev["content"],
                                                    rev["spans"])
                    if o == ORIGIN_DICTATED]
        assert not dictated, \
            "the surviving typed word was asserted to be dictated"


# ============================================================================
# M12-AUDIT-18 — the dirty marker follows the newest unsaved generation
# ============================================================================

@case("M12-AUDIT-18")
def r18_old_save_cannot_clear_a_newer_generation():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("m0")["note_id"]
        hw.open_note(n)
        hw.type("m0 A")
        latch = w.Latch("A_before_commit").install(
            hw.notes, "append_revision")
        hw.hub.editor.flush_async()
        assert latch.wait()
        hw.type("m0 A B")                      # newer, unsaved generation
        latch.release()
        # A commits (a repaired flush may go on to save B as well).
        assert _wait_revision(hw, n, lambda r: r.get("content") in
                              ("m0 A", "m0 A B"))
        w.wait_for(lambda: not any(t.name == "localflow-notes-autosave"
                                   and t.is_alive()
                                   for t in threading.enumerate()), 5)
        latch.remove()
        marker = _note(hw, n)["dirty_at_utc"]
        content = _latest(hw.notes, n).get("content")
        assert content == "m0 A B" or marker, \
            "an older save cleared the marker while B was unsaved"


# ============================================================================
# M12-AUDIT-19 — no automatic clipboard publication on refusal
# ============================================================================

@case("M12-AUDIT-19")
def r19a_closed_note_dictation_does_not_touch_the_clipboard():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("to close")["note_id"]
        fn, args, job = _dictate(hw, n)
        hw.hub.editor.clear()
        before = board_count()
        fn(*args)
        hw.drain()
        assert board_count() == before, \
            "a refused note destination published to the clipboard"
        assert _job(hw, job["job_id"]).get("state") == "saved_not_inserted"


@case("M12-AUDIT-19")
def r19b_refused_note_transform_does_not_touch_the_clipboard():
    with w.HubWorld(consent=True) as hw:
        a = hw.notes.create_note("alpha source")["note_id"]
        b = hw.notes.create_note("beta other")["note_id"]
        _transform_note(hw, a)
        hw.drain()
        hw.open_note(b)
        before = board_count()
        hw.d._tf_panel.panelAccept_(None)
        hw.drain()
        assert board_count() == before, \
            "a refused note transform published to the clipboard"
        assert _latest(hw.notes, b).get("content") == "beta other"


# ============================================================================
# M12-AUDIT-20 — History Move reaches the transfer helper
# ============================================================================

@case("M12-AUDIT-20")
def r20_move_selector_reaches_the_transfer():
    from localflow.v2.ui.state import VIEWS
    with w.HubWorld(select_scratchpad=False) as hw:
        job_id, _fam = hw.store.create_job(
            captured_at_utc="2026-09-25T09:00:00Z", time_quality="known",
            state="insertion_confirmed")
        hw.store.write_text_artifact(job_id=job_id, stage="asr",
                                     role="raw_transcript",
                                     text="move me raw",
                                     retention_class="history")
        hw.store.write_text_artifact(job_id=job_id, stage="cleanup",
                                     role="applied_output",
                                     text="move me final",
                                     retention_class="history",
                                     meta={"cleanup_path": "llm"})
        hw.store.sync()
        hw.hub._select_view_index(VIEWS.index("history"))
        hw.hub.state.select_history_row("job", job_id)
        hw.drain()
        try:
            hw.hub.historyMoveToScratchpad_(None)
        except AttributeError as e:
            raise AssertionError(
                f"the Move selector raised {type(e).__name__}") from None
        hw.drain()
        texts = [r[0] for r in hw.store.submit(lambda db: db.execute(
            "SELECT r.content_text FROM notes n JOIN note_revisions r ON"
            " r.revision_id = n.current_revision_id").fetchall())]
        assert "move me final" in texts, "Move created no note"
        assert hw.store.job(job_id) is None or \
            hw.hub.state.history_service.job_detail(job_id) is None, \
            "Move did not delete the source row"


# ============================================================================
# M12-AUDIT-21 — every Scratchpad action lies inside its pane
# ============================================================================

@case("M12-AUDIT-21")
def r21_actions_fit_at_default_and_minimum_sizes():
    from AppKit import NSButton, NSMakeSize
    from localflow.v2.ui import hub as hub_mod
    with w.HubWorld() as hw:
        pane = hw.hub._built_views["scratchpad"]
        bad = []
        for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
            hw.hub.window.setContentSize_(NSMakeSize(*size))
            hw.hub.window.contentView().layoutSubtreeIfNeeded()
            pb = pane.bounds()
            for v in pane.subviews():
                if not isinstance(v, NSButton) or not v.action():
                    continue
                f = v.frame()
                inside = (f.origin.x >= pb.origin.x - 0.5
                          and f.origin.x + f.size.width
                          <= pb.origin.x + pb.size.width + 0.5
                          and f.origin.y >= -0.5
                          and f.origin.y + f.size.height
                          <= pb.size.height + 0.5)
                if not inside:
                    bad.append((size, str(v.title())))
        assert not bad, f"actions outside the pane: {bad}"


# ============================================================================
# M12-AUDIT-22 — malformed native ranges are refused
# ============================================================================

@case("M12-AUDIT-22")
def r22_malformed_ranges_refuse():
    text = "A😀B"
    accepted = []
    for loc, length in ((2, 0), (1, 1), (-1, 1), (0, -1), (3, 5),
                        (10 ** 9, 1), (0, 10 ** 9)):
        try:
            out = notes_mod.utf16_range_to_codepoints(text, loc, length)
        except ValueError:
            continue
        accepted.append(((loc, length), out))
    assert not accepted, f"malformed native ranges converted: {accepted}"
    assert notes_mod.utf16_range_to_codepoints(text, 3, 1) == (2, 3)
    assert notes_mod.utf16_range_to_codepoints(text, 1, 2) == (1, 2)


# ============================================================================
# M12-AUDIT-23 — picker choices survive a refresh
# ============================================================================

@case("M12-AUDIT-23")
def r23_chosen_transform_and_version_survive_refresh():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("v1")["note_id"]
        for t in ("v2", "v3", "v4"):
            hw.notes.append_revision(n, t, origin=ORIGIN_TYPED,
                                     trigger=TRIGGER_AUTOSAVE)
        hw.open_note(n)
        ids = list(hw.hub._scratchpad_transform_ids)
        assert len(ids) >= 2, "fewer than two transforms (population)"
        hw.hub.scratchpad_transforms.selectItemAtIndex_(1)
        vids = list(hw.hub._scratchpad_version_ids)
        assert len(vids) >= 2
        hw.hub.scratchpad_versions.selectItemAtIndex_(1)
        chosen_t, chosen_v = ids[1], vids[1]
        hw.hub.state.reload_scratchpad()
        hw.drain()
        idx = hw.hub.scratchpad_transforms.indexOfSelectedItem()
        vidx = hw.hub.scratchpad_versions.indexOfSelectedItem()
        got_t = hw.hub._scratchpad_transform_ids[idx] if idx >= 0 else None
        got_v = hw.hub._scratchpad_version_ids[vidx] if vidx >= 0 else None
        assert got_t == chosen_t, "the chosen transform reset on refresh"
        assert got_v == chosen_v, "the chosen version reset on refresh"


# ============================================================================
# M12-AUDIT-24 — admitted-unknown mutations are not reported as failed
# ============================================================================

def _unknown_status(hw, action):
    hold = w.WriterHold(hw.store)
    try:
        with w.short_submit_timeout(hw.store, 0.2):
            action()
    finally:
        hold.release()
    hw.store.sync()
    return str(hw.hub.scratchpad_status.stringValue())


@case("M12-AUDIT-24")
def r24a_pin_and_new_with_unknown_outcome_do_not_claim_failure():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("pin me")["note_id"]
        hw.open_note(n)
        s1 = _unknown_status(hw, lambda: hw.hub.scratchpadPin_(None))
        s2 = _unknown_status(hw, lambda: hw.hub.scratchpadNew_(None))
        hw.drain()
        for s in (s1, s2):
            assert "failed" not in s, \
                "an admitted mutation with an unknown outcome was" \
                " reported as failed"


@case("M12-AUDIT-24")
def r24b_history_copy_unknown_is_not_failure_and_never_deletes():
    with w.HubWorld(select_scratchpad=False) as hw:
        job_id, _raw, _app = __import__("m09_world").seed_job(
            hw.store, "history row text", captured="2026-09-25T08:00:00Z")
        real_create = hw.notes.create_note
        holds = []

        def create_unknown(*a, **kw):
            # Only the note creation is admitted-then-unanswered: the
            # History read before it ran normally.
            holds.append(w.WriterHold(hw.store))
            with w.short_submit_timeout(hw.store, 0.2):
                return real_create(*a, **kw)
        hw.notes.create_note = create_unknown
        try:
            try:
                out = hw.d.hubSaveHistoryRow("job", job_id, move=True)
            except Exception as e:  # noqa: BLE001
                out = {"outcome": f"raised {type(e).__name__}"}
        finally:
            for hd in holds:
                hd.release()
            hw.notes.create_note = real_create
        assert holds, "the note creation was never reached"
        hw.store.sync()
        hw.store.sync()
        assert "failed" not in str(out.get("outcome")), \
            f"an unknown creation was reported as failed ({out})"
        assert hw.store.job(job_id) is not None, \
            "Move deleted the source after an unknown note creation"


# ============================================================================
# M12-AUDIT-25 — the benchmark certifies its workload
# ============================================================================

@case("M12-AUDIT-25")
def r25_benchmark_fixture_and_validity():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "benchmark_m12", w.ROOT / "scripts" / "v2" / "benchmark_m12.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert len(mod.WORD10K.split()) == 10000, \
        f"the 10,000-word fixture has {len(mod.WORD10K.split())} words"
    validate = getattr(mod, "validate_open", None)
    assert validate is not None, "the benchmark has no work-validity oracle"
    assert validate({"revision": None, "versions": []}) is False, \
        "an empty open result was not rejected"


# ============================================================================
# M12-AUDIT-26 — no private absolute paths in M12 evidence
# ============================================================================

@case("M12-AUDIT-26")
def r26_m12_results_carry_no_private_absolute_path():
    import re
    pat = re.compile(r"/(Users|home)/[^/\s\"']+")
    hits = {}

    def walk(obj, key="$"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{key}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{key}[{i}]")
        elif isinstance(obj, str) and pat.search(obj):
            hits[key] = hits.get(key, 0) + 1
    base = w.ROOT / "docs" / "v2" / "acceptance" / "M12"
    for p in sorted(base.rglob("*.json")):
        walk(json.loads(p.read_text()), p.name)
    assert not hits, f"private absolute paths in fields: {sorted(hits)}"


# ============================================================================
# LOCAL — History transfer of legacy rows
# ============================================================================

@case("LOCAL-M12-01")
def l01_legacy_row_transfer_is_honest():
    m09 = __import__("m09_world")
    with w.HubWorld(select_scratchpad=False) as hw:
        rid = m09.seed_legacy_db(hw.store, 7, raw="legacy raw words",
                                 cleaned="legacy cleaned words",
                                 ts=1767225600.0)
        try:
            out = hw.d.hubSaveHistoryRow("legacy_db", rid, move=True)
        except Exception as e:  # noqa: BLE001
            raise AssertionError(
                f"legacy transfer raised {type(e).__name__}") from None
        nid = out.get("note_id")
        assert nid, f"legacy copy created no note ({out.get('outcome')})"
        assert _latest(hw.notes, nid).get("content") == \
            "legacy cleaned words"
        assert out.get("outcome") == "move_degrades_to_copy_legacy"


@case("LOCAL-M12-02")
def l02_populated_m12_table_loss_is_refused():
    """A populated Scratchpad table missing at open is corruption: the
    repair path must refuse (after its backup), never recreate it empty
    and present the survivors as intact."""
    from localflow.v2 import store as store_mod
    silent = []
    for table in ("notes", "note_revisions", "note_attachments"):
        with w.NoteWorld() as nw:
            for i in range(2):
                n = nw.notes.create_note(f"note {i} r1")["note_id"]
                for r in (2, 3):
                    nw.notes.append_revision(
                        n, f"note {i} r{r}", origin=ORIGIN_TYPED,
                        trigger=TRIGGER_AUTOSAVE)
                nw.notes.add_attachment(n, w.PNG, "image/png", "p.png")
            db = nw.store.db_path
            nw.store.close()
            c = sqlite3.connect(db)
            c.execute(f"DROP TABLE {table}")
            c.commit()
            c.close()
            try:
                s = store_mod.Store(db, backup_dir=nw.app / "backups")
            except RuntimeError:
                continue          # refused: the honest outcome
            s.close()
            silent.append(table)
    assert not silent, f"recreated empty and opened as intact: {silent}"


@case("LOCAL-M12-03")
def l03_identical_version_labels_restore_the_chosen_revision():
    """Autosaves in the same second with the same word count get the
    same label; the versions popup must still map every shown item to
    its own revision (NSPopUpButton.addItemWithTitle_ drops an item
    whose title already exists)."""
    from localflow.v2 import ids as ids_mod
    with w.HubWorld() as hw:
        real_now = ids_mod.now_utc_iso
        ids_mod.now_utc_iso = lambda *a: "2026-09-26T12:00:00.000Z"
        try:
            n = hw.notes.create_note("created words")["note_id"]
            for t in ("two", "three", "four", "latest text"):
                hw.notes.append_revision(n, t, origin=ORIGIN_TYPED,
                                         trigger=TRIGGER_AUTOSAVE)
        finally:
            ids_mod.now_utc_iso = real_now
        hw.open_note(n)
        pop = hw.hub.scratchpad_versions
        shown = int(pop.numberOfItems())
        mapped = len(hw.hub._scratchpad_version_ids)
        pop.selectItemAtIndex_(shown - 1)   # the oldest: the created one
        hw.hub.scratchpadRestore_(None)
        hw.drain()
        hw.settle_notes()
        assert shown == mapped, \
            f"the popup shows {shown} versions for {mapped} revisions"
        assert _latest(hw, n)["content"] == "created words", \
            "Restore restored a different version than the one chosen"


# ============================================================================
# CONTROLS — behavior the repair must keep (pass on base AND repair)
# ============================================================================

@case("CONTROL")
def c01_serial_appends_keep_an_immutable_parent_chain():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("first")["note_id"]
        nw.notes.append_revision(n, "second", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        before = nw.revisions(n)
        nw.notes.append_revision(n, "third", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        after = nw.revisions(n)
        assert after[:2] == before, "an older revision changed"
        assert [r[1] for r in after] == [None, after[0][0], after[1][0]]
        assert [r[4] for r in after] == ["first", "second", "third"]


@case("CONTROL")
def c02_late_append_after_delete_is_refused():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("doomed")["note_id"]
        nw.notes.delete_note(n)
        try:
            nw.notes.append_revision(n, "revived", origin=ORIGIN_TYPED,
                                     trigger=TRIGGER_AUTOSAVE)
            raised = False
        except Exception:
            raised = True
        assert raised, "a late append recreated a deleted note"
        assert not nw.rows("SELECT 1 FROM note_revisions WHERE note_id=?"
                           " AND purged=0", (n,))


@case("CONTROL")
def c03_ordinary_switch_persists_the_outgoing_tail():
    with w.HubWorld() as hw:
        a = hw.notes.create_note("control base")["note_id"]
        b = hw.notes.create_note("control other")["note_id"]
        hw.open_note(a)
        hw.type("control base CONTROL_TAIL")
        hw.hub.state.select_scratchpad_note(b)
        hw.drain()
        hw.settle_notes()
        assert _latest(hw, a).get("content") == "control base CONTROL_TAIL"


@case("CONTROL")
def c04_ascii_caret_dictation_lands_at_the_caret():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("AB")["note_id"]
        fn, args, job = _dictate(hw, n, at_utf16=1)
        fn(*args)
        want = "A" + job["final_text"] + "B"
        assert _wait_revision(hw, n, lambda r: r.get("content") == want)
        hw.settle_notes()
        hw.drain()
        assert _job(hw, job["job_id"]).get("state") == "insertion_confirmed"


@case("CONTROL")
def c05_selection_transform_allows_an_outside_edit():
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("keep alpha beta")["note_id"]
        hw.open_note(n)
        hw.focus()
        hw.hub.editor.text.setSelectedRange_((5, 5))     # "alpha"
        hw.hub.scratchpad_transforms.selectItemAtIndex_(0)
        hw.hub.scratchpadTransform_(None)
        w.wait_for(lambda: hw.d._tf_active is None, 10)
        hw.drain()
        hw.type("keep alpha beta gamma")                 # outside edit
        hw.hub.editor.flush_now()
        hw.d._tf_panel.panelAccept_(None)
        hw.settle_notes()
        hw.drain()
        assert _latest(hw, n).get("content") == \
            "keep TRANSFORMED OUTPUT beta gamma"


@case("CONTROL")
def c06_consent_off_keeps_notes_working():
    with w.HubWorld(consent=False) as hw:
        n = hw.notes.create_note("no consent")["note_id"]
        fn, args, job = _dictate(hw, n)
        fn(*args)
        want = "no consent" + job["final_text"]
        assert _wait_revision(hw, n, lambda r: r.get("content") == want)
        hw.settle_notes()
        links = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_evidence_links").fetchone()[0])
        assert links == 0


@case("CONTROL")
def c07_clean_restore_rebinds_before_the_next_keystroke():
    with w.HubWorld() as hw:
        n = hw.notes.create_note("r1 text")["note_id"]
        hw.notes.append_revision(n, "r2 text", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        hw.open_note(n)
        vids = list(hw.hub._scratchpad_version_ids)
        hw.hub.scratchpad_versions.selectItemAtIndex_(len(vids) - 1)
        hw.hub.scratchpadRestore_(None)
        hw.drain()
        assert str(hw.hub.editor.current_content()) == "r1 text"
        hw.type("r1 text typed")
        hw.hub.editor.flush_now()
        hw.settle_notes()
        assert _latest(hw, n).get("content") == "r1 text typed"


@case("CONTROL")
def c08_ordinary_export_round_trip():
    nw, note_id, dest = _export_world()
    try:
        note = nw.notes.open_note(note_id)
        rep = note_export.write_export(dest / "n.md", note, nw.notes,
                                       "markdown")
        assert rep["ok"] and rep["attachments_copied"] == 2
        assert (dest / "n.md").read_text().startswith("# Title")
        rep = note_export.write_export(dest / "n.txt", note, nw.notes,
                                       "plain")
        assert rep["ok"] and len(rep["unsupported"]) == 2
    finally:
        nw.close()


# ---------------------------------------------------------------------------

def run(select=None, json_out=None):
    results = []
    for fn in CASES:
        if select and not any(s in fn.__name__ for s in select):
            continue
        t0 = time.monotonic()
        wall0 = time.time()
        try:
            fn()
            status, note = "PASS", ""
        except AssertionError as e:
            status, note = "FAIL", str(e)[:300]
        except Exception as e:  # noqa: BLE001
            status, note = "ERROR", f"{type(e).__name__}: {e}"[:300]
            traceback.print_exc()
        results.append({"id": fn.__name__, "finding": fn.finding,
                        "status": status, "note": note,
                        "seconds": round(time.monotonic() - t0, 2),
                        # Wall-clock window: lets an outside monitor of
                        # the live pasteboard's change COUNT attribute
                        # any change to a case (or to none).
                        "window_epoch": [round(wall0, 3),
                                         round(time.time(), 3)]})
        print(f"{status:5} {fn.__name__}"
              + (f" — {note}" if note else ""), flush=True)
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(json.dumps(counts))
    if json_out:
        pathlib.Path(json_out).write_text(json.dumps({
            **w.code_stamp("tests/v2/notes/test_m12_remediation.py"),
            "counts": counts, "results": results}, indent=1) + "\n")
    return 0 if counts.get("FAIL", 0) + counts.get("ERROR", 0) == 0 else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    sel = argv[argv.index("-k") + 1].split(",") if "-k" in argv else None
    raise SystemExit(run(sel, out))
