"""Desktop companion — the Scratchpad editor over the bridge (headless).

The companion's note editor is the Hub's own ScratchpadEditor bound to a
mirror of the page's textarea. These cases drive it the way the page and
the coordinator do: typed edits naming the version they were typed on,
cursor reports, a PTT-time capture and a dictation arrival, a typed edit
racing that arrival, and the actions that must act on the note shown.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_companion_scratchpad.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

from test_companion_bridge import CWorld  # noqa: E402

from localflow.v2.ui.companion.surfaces.scratchpad import rebase  # noqa: E402


def open_new_note(w):
    w.select("scratchpad")
    out = w.host.send("scratchpad.new")
    assert out["status"] == "success", out
    nid = out["result"]["note_id"]
    w.drain()
    w.ctl.request_flush()
    w.drain()
    ed = w.ctl.scratchpad_editor
    assert ed.note_id == nid and ed.model is not None, (ed.note_id, nid)
    return nid, ed, w.ctl.scratchpad_mirror


def type_text(w, nid, text, caret=None):
    m = w.ctl.scratchpad_mirror
    caret = len(text) if caret is None else caret
    out = w.host.send("scratchpad.edit", {
        "note_id": nid, "base": m.version, "text": text,
        "sel_start": caret, "sel_end": caret})
    assert out["status"] == "success", out
    return out["result"]


def test_rebase_keeps_both_changes():
    assert rebase("hello world", "hello big world", "hello world, again") \
        == "hello big world, again"
    assert rebase("abc", "abXc", "Zabc") == "ZabXc"
    assert rebase("abc", "abc", "abcd") == "abcd"          # nothing typed
    assert rebase("one two", "one", "one two three") == "one three"
    # overlap: the arrival is kept, the typed insertion follows it
    assert rebase("abcdef", "abXYef", "abZZZef") == "abZZZXYef"
    print("ok  rebase: a typed change and an arrival both survive")


def test_typing_reaches_the_model_and_saves():
    with CWorld() as w:
        nid, ed, m = open_new_note(w)
        pushes = w.host.events("scratchpad.content")
        assert pushes and pushes[-1]["note_id"] == nid
        r = type_text(w, nid, "Trip checklist")
        assert r["content"] is None and ed.model.content == "Trip checklist"
        assert ed.model.dirty
        out = w.host.send("scratchpad.snapshot", {"note_id": nid})
        assert out["status"] == "success" and \
            out["result"]["outcome"] == "flushed", out
        saved = w.ctl.spec["notes_service"].open_note(nid)
        assert saved["revision"]["content"] == "Trip checklist"
        # an edit for a note the editor does not show is stale
        out = w.host.send("scratchpad.edit", {
            "note_id": "note-other", "base": m.version, "text": "x",
            "sel_start": 1, "sel_end": 1})
        assert out["status"] == "stale", out
    print("ok  scratchpad: typed text reaches the note model and saves on"
          " the explicit barrier")


def test_ptt_capture_needs_key_focus_and_current_selection():
    with CWorld() as w:
        nid, ed, m = open_new_note(w)
        type_text(w, nid, "hello")
        ctl = w.ctl
        assert not ctl.scratchpad_editor_active(), "active without focus"
        w.host.key = True
        w.host.focus = True
        w.host.send("scratchpad.cursor", {"note_id": nid, "version":
                                          m.version, "sel_start": 5,
                                          "sel_end": 5, "focused": True})
        assert ctl.scratchpad_editor_active()
        target = ctl.scratchpad_capture_target()
        assert target["note_id"] == nid and \
            target["insertion_point"] == 5, target
        # the route changes: the editor is no longer the dictation target
        w.select("home")
        assert not ctl.scratchpad_editor_active()
        w.select("scratchpad")
        # a selection reported for an older version is not trusted
        m.version += 1
        m.history[m.version] = m.value
        target = ctl.scratchpad_capture_target()
        assert target["insertion_point"] is None, target
        job = {"job_id": "job-x", "note_target": target}
        assert ctl.scratchpad_receive("world", job) is None
        assert job["note_refusal"] == "note_anchor_invalid", job
    print("ok  scratchpad: PTT binds only with key window, focus and a"
          " selection reported for the current text")


def test_arrival_lands_at_anchor_and_races_typing():
    with CWorld() as w:
        nid, ed, m = open_new_note(w)
        type_text(w, nid, "hello")
        w.host.key = w.host.focus = True
        w.host.send("scratchpad.cursor", {"note_id": nid, "version":
                                          m.version, "sel_start": 5,
                                          "sel_end": 5, "focused": True})
        target = w.ctl.scratchpad_capture_target()
        base = m.version
        job = {"job_id": "job-y", "note_target": target}
        arrival = w.ctl.scratchpad_receive(" world", job)
        assert arrival is not None and ed.model.content == "hello world"
        push = w.host.events("scratchpad.content")[-1]
        assert push["content"] == "hello world" and push["version"] > base
        # the page typed "!" on the old version, before the push reached it
        out = w.host.send("scratchpad.edit", {
            "note_id": nid, "base": base, "text": "hello!",
            "sel_start": 6, "sel_end": 6})
        assert out["status"] == "success" and \
            out["result"]["content"] == "hello! world", out
        assert ed.model.content == "hello! world"
        assert arrival.wait(5) and arrival.outcome == "committed", \
            arrival.outcome
        # an edit before the anchor removes the authority of a capture
        w.host.send("scratchpad.cursor", {"note_id": nid, "version":
                                          m.version, "sel_start": 12,
                                          "sel_end": 12, "focused": True})
        target = w.ctl.scratchpad_capture_target()
        type_text(w, nid, "Oh, hello! world", caret=16)
        job = {"job_id": "job-z", "note_target": target}
        assert w.ctl.scratchpad_receive(" again", job) is None
        assert job["note_refusal"] == "note_changed_during_dictation"
    print("ok  scratchpad: a dictation lands at its anchor, typing that"
          " raced it is merged, an edit before the anchor refuses")


def test_actions_bind_to_the_shown_note():
    with CWorld() as w:
        nid, ed, m = open_new_note(w)
        out = w.host.send("scratchpad.pin", {"note_id": "note-not-shown"})
        assert out["status"] == "stale", out
        assert w.host.send("scratchpad.pin", {"note_id": nid})[
            "status"] == "success"
        type_text(w, nid, "delete me")
        out = w.host.send("scratchpad.delete", {"note_id": nid})
        assert out["status"] == "success", out
        w.drain()
        w.ctl.request_flush()
        w.drain()
        assert ed.note_id is None and m.note_id is None
        assert w.ctl.spec["notes_service"].open_note(nid) is None
    print("ok  scratchpad: actions refuse a note the editor does not show;"
          " delete forgets the buffer")


class ImagePanel:
    def __init__(self, path):
        self.path = path

    def open_image(self):
        return str(self.path)


def test_attach_needs_a_current_caret_and_says_so():
    # a 1x1 PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6300010000000500010d0a2db40000"
        "000049454e44ae426082")
    import tempfile
    tmp = pathlib.Path(tempfile.mkdtemp()) / "figure.png"
    tmp.write_bytes(png)
    with CWorld(file_panels=ImagePanel(tmp)) as w:
        nid, ed, m = open_new_note(w)
        type_text(w, nid, "Trip checklist")
        # The text moved on (e.g. a dictation arrived) after the page's
        # last caret report: there is no current place for the marker.
        m.version += 1
        m.history[m.version] = m.value
        before = ed.model.content
        out = w.host.send("scratchpad.attach", {"note_id": nid})
        assert out["status"] == "refusal" and \
            out["reason_code"] == "selection_unreadable", out
        assert ed.model.content == before
        svc = w.ctl.spec["notes_service"]
        assert not (svc.open_note(nid).get("attachments") or []), \
            "an attachment was stored without its marker"
        # With a caret reported for the current text, the image lands.
        w.host.send("scratchpad.cursor", {
            "note_id": nid, "version": m.version, "sel_start": 4,
            "sel_end": 4, "focused": True})
        out = w.host.send("scratchpad.attach", {"note_id": nid})
        assert out["status"] == "success", out
        assert ed.model.content != before, "no marker was inserted"
    print("ok  scratchpad: Attach refuses without a caret for the current"
          " text, and inserts its marker with one")


if __name__ == "__main__":
    for test in (test_rebase_keeps_both_changes,
                 test_typing_reaches_the_model_and_saves,
                 test_ptt_capture_needs_key_focus_and_current_selection,
                 test_arrival_lands_at_anchor_and_races_typing,
                 test_actions_bind_to_the_shown_note,
                 test_attach_needs_a_current_caret_and_says_so):
        test()
