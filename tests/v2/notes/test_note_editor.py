"""EV-14 / M12: the editor model (Spec S20) — debounce, immediate
attributed flushes, concurrent autosave serialization, and the
dirty-marker arming. Pure Python: no AppKit, headless by construction
(the AppKit binding lives in ui/scratchpad.py and is covered by the
hub suite).

Run: .venv/bin/python tests/v2/notes/test_note_editor.py
"""

import pathlib
import sys
import tempfile
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.notes import (NoteStore, NotesEditorModel,  # noqa: E402
                                ORIGIN_DICTATED, ORIGIN_TYPED,
                                ORIGIN_TRANSFORM, TRIGGER_AUTOSAVE,
                                TRIGGER_EXPLICIT, TRIGGER_SYSTEM)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def make(tmp):
    s = store_mod.Store(tmp / "v2.db", backup_dir=None)
    ns = NoteStore(s)
    out = ns.create_note("base line")
    return s, ns, out


def test_debounce_and_autosave():
    with tempfile.TemporaryDirectory() as td:
        s, ns, out = make(pathlib.Path(td))
        try:
            clock = Clock()
            dirty_notes = []
            m = NotesEditorModel(out["note_id"], out["revision"],
                                 "base line", on_dirty=dirty_notes.append,
                                 clock=clock)
            # Typing arms the marker on the FIRST edit only.
            m.edit("base line one")
            m.edit("base line one two")
            assert dirty_notes == [out["note_id"]]
            assert not m.due()  # debounce still running
            clock.advance(2.0)
            assert m.due()
            r = m.flush(ns, trigger=TRIGGER_AUTOSAVE)
            assert r["outcome"] == "flushed" and r["origin"] == \
                ORIGIN_TYPED and r["trigger"] == TRIGGER_AUTOSAVE
            assert not m.dirty
            detail = ns.open_note(out["note_id"])
            assert detail["revision"]["content"] == "base line one two"
            assert detail["revision"]["trigger"] == TRIGGER_AUTOSAVE
            # An unchanged buffer flush is a no-op (no empty revisions).
            clock.advance(5.0)
            m.edit("base line one two")  # identical content
            clock.advance(5.0)
            assert m.flush(ns)["outcome"] == "no_change"
            versions = ns.open_note(out["note_id"])["versions"]
            assert len(versions) == 2
            # Explicit snapshot differs from autosave by trigger only.
            m.edit("base line one two three")
            r = m.flush(ns, trigger=TRIGGER_EXPLICIT)
            assert r["trigger"] == TRIGGER_EXPLICIT
            last = ns.open_note(out["note_id"])["versions"][0]
            assert last["origin"] == ORIGIN_TYPED and \
                last["trigger"] == TRIGGER_EXPLICIT
        finally:
            s.close()
    print("ok  debounce arms dirty once; autosave vs explicit trigger")


def test_attributed_arrivals_flush_immediately():
    with tempfile.TemporaryDirectory() as td:
        s, ns, out = make(pathlib.Path(td))
        try:
            m = NotesEditorModel(out["note_id"], out["revision"],
                                 "base line")
            m.receive("base line DICTATED TAIL", origin=ORIGIN_DICTATED,
                      trigger=TRIGGER_SYSTEM, source_job_id="job-9",
                      inserted_at_chars=9, inserted_text="DICTATED TAIL")
            assert m.due(), "attributed arrival must be due at once"
            r = m.flush(ns)
            assert r["origin"] == ORIGIN_DICTATED
            detail = ns.open_note(out["note_id"])
            assert detail["revision"]["content"] == \
                "base line DICTATED TAIL"
            rev = s.submit(lambda db: db.execute(
                "SELECT source_job_id, origin FROM note_revisions WHERE"
                " revision_id=?",
                (detail["current_revision_id"],)).fetchone())
            assert rev == ("job-9", ORIGIN_DICTATED)
            assert detail["revision"]["spans"], \
                "dictated region not attributed"
            # A transform arrival replaces a range and carries identity.
            m.receive("base line TRANSFORMED", origin=ORIGIN_TRANSFORM,
                      trigger=TRIGGER_EXPLICIT, task_key="ttask:k",
                      transform_id="builtin:polish",
                      transform_revision=1, inserted_at_chars=9,
                      inserted_text="TRANSFORMED")
            r = m.flush(ns)
            assert r["origin"] == ORIGIN_TRANSFORM
            rev = s.submit(lambda db: db.execute(
                "SELECT task_key, transform_id, origin FROM"
                " note_revisions ORDER BY rowid DESC LIMIT 1").fetchone())
            assert rev == ("ttask:k", "builtin:polish",
                           ORIGIN_TRANSFORM)
        finally:
            s.close()
    print("ok  dictated/transform arrivals flush immediately + attributed")


def test_concurrent_autosave_serializes():
    """EV-14: two flushes racing produce an ordered parent chain —
    never interleaved duplicate revisions of one buffer state."""
    with tempfile.TemporaryDirectory() as td:
        s, ns, out = make(pathlib.Path(td))
        try:
            m = NotesEditorModel(out["note_id"], out["revision"],
                                 "base line")
            results = []
            barrier = threading.Barrier(4)

            def flusher(i):
                barrier.wait()
                m.edit(f"base line v{i}")     # racing edits + flushes
                results.append(m.flush(ns))

            threads = [threading.Thread(target=flusher, args=(i,))
                       for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            # Every flush either committed or deferred to the reflush
            # loop; the store chain is strictly parent-linked with no
            # duplicate (parent, content) revisions from interleaving.
            chain = s.submit(lambda db: db.execute(
                "SELECT revision_id, parent_revision_id, content_text"
                " FROM note_revisions WHERE note_id=? ORDER BY rowid",
                (out["note_id"],)).fetchall())
            assert all(chain[i][1] == chain[i - 1][0]
                       for i in range(1, len(chain))), "chain broken"
            assert len({(r[1], r[2]) for r in chain[1:]}) == \
                len(chain) - 1, "duplicate (parent, content) revisions"
            # The model ended consistent with the store's last word.
            final = ns.open_note(out["note_id"])["revision"]["content"]
            assert m.saved_content == final
        finally:
            s.close()
    print("ok  concurrent autosave serializes; chain stays ordered")


def test_close_and_closed_model_refuses():
    with tempfile.TemporaryDirectory() as td:
        s, ns, out = make(pathlib.Path(td))
        try:
            m = NotesEditorModel(out["note_id"], out["revision"], "x")
            m.close()
            m.edit("y")            # ignored
            assert not m.due()
            assert m.flush(ns)["outcome"] == "closed"
        finally:
            s.close()
    print("ok  closed model refuses edits and flushes")


if __name__ == "__main__":
    test_debounce_and_autosave()
    test_attributed_arrivals_flush_immediately()
    test_concurrent_autosave_serializes()
    test_close_and_closed_model_refuses()
    print("all note editor tests passed")
