"""Drivers binding the frozen M12 adversarial corpus
(``m12_audit_corpus.json``, sha256 0c1e9cc5…5be9, unchanged) to the
current APIs — the portable cases C001–C125. One driver per case
(families share parameterised drivers); each returns an ``Outcome``
with the corpus runner's taxonomy — PASS / FAIL / ERROR / NARROWED /
MANUAL_PENDING / NOT_RUN — the observed values and, for stateful
cases, the seams actually reached (``m12_world.REACHED``).

Oracles come from each case's declared fixture and assertions and the
policy decisions in ``docs/v2/acceptance/M12/remediation/
adjudications.json``; nothing asks the code under test for its own
expected answer. A driver whose setup cannot be expressed through a
current entry point returns ERROR with the reason — never PASS.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import sqlite3
import sys
import threading

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import m12_world as w  # noqa: E402
import test_m12_remediation as rem  # noqa: E402

from localflow.v2 import note_export  # noqa: E402
from localflow.v2 import notes as notes_mod  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.notes import (ORIGIN_ATTACHMENT, ORIGIN_DICTATED,  # noqa
                                ORIGIN_RESTORE, ORIGIN_SNIPPET,
                                ORIGIN_TRANSFORM, ORIGIN_TYPED,
                                TRIGGER_AUTOSAVE, TRIGGER_EXPLICIT,
                                TRIGGER_SYSTEM)


@dataclasses.dataclass
class Outcome:
    status: str
    observed: dict
    barriers: list = dataclasses.field(default_factory=list)
    note: str = ""


DRIVERS: dict = {}


def driver(*case_ids):
    def deco(fn):
        for cid in case_ids:
            DRIVERS[cid] = fn
        return fn
    return deco


def verdict(checks: dict, observed=None, barriers=None, note=""):
    failed = [k for k, v in checks.items() if not v]
    obs = dict(observed or {})
    obs["checks"] = {k: bool(v) for k, v in checks.items()}
    return Outcome("FAIL" if failed else "PASS", obs, list(barriers or []),
                   note or (f"failed: {failed}" if failed else ""))


def via(regression):
    """Run a fail-first regression as the case's probe: its assertions
    ARE the case oracle (written from the same fixture); the seams its
    latches reached are reported."""
    del w.REACHED[:]
    try:
        regression()
    except AssertionError as e:
        return Outcome("FAIL", {"regression": regression.__name__},
                       list(w.REACHED), str(e)[:300])
    return Outcome("PASS", {"regression": regression.__name__},
                   list(w.REACHED))


def utf16_units(text: str) -> int:
    """Independent UTF-16 length (the encoder, not the code under test)."""
    return len(text.encode("utf-16-le")) // 2


def cp_of_units(text: str, units: int):
    """Independent inverse: the code-point index whose UTF-16 prefix is
    ``units`` long, or None when ``units`` splits a pair / is outside."""
    for i in range(len(text) + 1):
        u = utf16_units(text[:i])
        if u == units:
            return i
        if u > units:
            return None
    return None


def revisions(nw, note_id):
    return nw.revisions(note_id)


def spans_of(content, spans, origin=None):
    return [x for ws, o, _j in w.span_words(content, spans)
            if origin is None or o == origin for x in ws]


# ---- note revisions ------------------------------------------------------

@driver("LF-M12-C001")
def c001(case):
    return via(rem.c01_serial_appends_keep_an_immutable_parent_chain)


@driver("LF-M12-C002")
def c002(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("one")["note_id"]
        for t in ("two", "three", "four", "five"):
            nw.notes.append_revision(n, t, origin=ORIGIN_TYPED,
                                     trigger=TRIGGER_AUTOSAVE)
        before = revisions(nw, n)
        r1, r5 = before[0][0], before[-1][0]
        nw.notes.restore(n, r1)
        after = revisions(nw, n)
        new = after[-1]
        meta = nw.rows("SELECT restore_of FROM note_revisions WHERE"
                       " revision_id=?", (new[0],))[0][0]
        return verdict({
            "older_unchanged": after[:5] == before,
            "copy_of_r1": new[4] == "one" and new[2] == ORIGIN_RESTORE,
            "parent_is_r5": new[1] == r5,
            "restore_of_r1": meta == r1,
        }, {"revisions": len(after)})


@driver("LF-M12-C003")
def c003(case):
    with w.NoteWorld() as nw:
        a = nw.notes.create_note("note a")["note_id"]
        b = nw.notes.create_note("note b")["note_id"]
        ra = revisions(nw, a)[0][0]
        before = revisions(nw, b)
        try:
            nw.notes.restore(b, ra)
            refused = False
        except KeyError:
            refused = True
        return verdict({"refused": refused,
                        "b_unchanged": revisions(nw, b) == before})


@driver("LF-M12-C004", "LF-M12-C037")
def c004(case):
    return via(rem.c07_clean_restore_rebinds_before_the_next_keystroke)


@driver("LF-M12-C005")
def c005(case):
    """D02: the buffer is saved before a restore; a buffer that cannot
    be saved blocks the restore (kept, retried) — never dropped."""
    with w.HubWorld() as hw:
        n = hw.notes.create_note("r1 base")["note_id"]
        hw.notes.append_revision(n, "r2 base", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        hw.open_note(n)
        hw.type("r2 base DIRTY_TAIL")
        st = rem._fail_append(hw.notes)
        vids = list(hw.hub._scratchpad_version_ids)
        hw.hub.scratchpad_versions.selectItemAtIndex_(len(vids) - 1)
        hw.hub.scratchpadRestore_(None)
        hw.drain()
        refused = "restore not done" in str(
            hw.hub.scratchpad_status.stringValue())
        kept = "DIRTY_TAIL" in str(hw.hub.editor.current_content())
        no_restore = not any(r[2] == ORIGIN_RESTORE
                             for r in hw.store.submit(lambda db: db.execute(
                                 "SELECT 1,2,origin FROM note_revisions"
                                 " WHERE note_id=?", (n,)).fetchall()))
        st["armed"] = False
        hw.hub.scratchpad_versions.selectItemAtIndex_(len(vids) - 1)
        hw.hub.scratchpadRestore_(None)
        hw.drain()
        hw.settle_notes()
        chain = [r[0] for r in hw.store.submit(lambda db: db.execute(
            "SELECT content_text FROM note_revisions WHERE note_id=?"
            " ORDER BY rowid", (n,)).fetchall())]
        return verdict({
            "failed_save_blocks_restore": refused and no_restore,
            "dirty_buffer_kept": kept,
            "saved_then_restored": chain[-2:] == ["r2 base DIRTY_TAIL",
                                                  "r1 base"],
        }, {"chain_len": len(chain)})


def _chain(nw, n, count):
    for i in range(1, count):
        nw.notes.append_revision(n, f"v{i}", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)


@driver("LF-M12-C006", "LF-M12-C007", "LF-M12-C008")
def c006(case):
    count = {"LF-M12-C006": 200, "LF-M12-C007": 201,
             "LF-M12-C008": 1000}[case["id"]]
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("v0")["note_id"]
        _chain(nw, n, count)
        d = nw.notes.open_note(n)
        vers = d["versions"]
        want_ids = [r[0] for r in revisions(nw, n)][::-1][:200]
        return verdict({
            "header_count": len(vers) == min(200, count),
            "truncated_flag": d["versions_truncated"] == (count > 200),
            "newest_first_exact_ids": [v["revision_id"] for v in vers]
            == want_ids,
        }, {"revisions": count, "headers": len(vers)})


@driver("LF-M12-C009")
def c009(case):
    with w.NoteWorld() as nw:
        a = nw.notes.create_note("aa")["note_id"]
        b = nw.notes.create_note("bb")["note_id"]
        revs = nw.rows("SELECT COUNT(*) FROM note_revisions")[0][0]
        nw.notes.set_pinned(a, True)
        order = [x["note_id"] for x in nw.notes.notes()]
        nw.notes.set_pinned(a, False)
        nw.notes.set_pinned(a, True)
        revs2 = nw.rows("SELECT COUNT(*) FROM note_revisions")[0][0]
        nw.notes.delete_note(a)
        gone = nw.rows("SELECT COUNT(*) FROM note_revisions WHERE"
                       " note_id=? AND purged=0", (a,))[0][0]
        return verdict({"pinned_first": order[0] == a,
                        "no_revisions_from_pin": revs == revs2,
                        "pin_is_not_retention": gone == 0,
                        "other_note_kept": nw.notes.note(b) is not None})


@driver("LF-M12-C010")
def c010(case):
    return via(rem.l02_populated_m12_table_loss_is_refused)


@driver("LF-M12-C011", "LF-M12-C012", "LF-M12-C013", "LF-M12-C014",
        "LF-M12-C015")
def c011(case):
    literal = {"LF-M12-C011": "%", "LF-M12-C012": "_",
               "LF-M12-C013": "\\", "LF-M12-C014": "café 😀",
               "LF-M12-C015": "不存在"}[case["id"]]
    with w.NoteWorld() as nw:
        texts = ["plain words only", "percent 50% here", "under_score",
                 "back\\slash", "café 😀 party", "caf e plain"]
        ids = {t: nw.notes.create_note(t)["note_id"] for t in texts}
        want = {ids[t] for t in texts if literal in t}
        got = {r["note_id"] for r in nw.notes.search(literal)}
        checks = {"exact_literal_matches": got == want}
        if not want:
            # A positive control proves the search ran over content.
            checks["positive_control"] = {
                r["note_id"] for r in nw.notes.search("plain")} == {
                ids["plain words only"], ids["caf e plain"]}
        return verdict(checks, {"expected": len(want), "got": len(got)})


# ---- UTF-16 ranges -------------------------------------------------------

def _editor(text, loc, length):
    """A real ScratchpadEditor (headless AppKit) bound to a synthetic
    note: the native range is set on its NSTextView."""
    from localflow.v2.ui.scratchpad import ScratchpadEditor
    ed = ScratchpadEditor.alloc().init_editor(None)
    ed.bind_note({"note_id": "note-synthetic",
                  "revision": {"revision_id": None, "content": text}})
    ed.text.setSelectedRange_((loc, length))
    return ed


CARET = {"LF-M12-C016": ("AB", 1), "LF-M12-C017": ("A😀B", 3),
         "LF-M12-C018": ("😀😀B", 4), "LF-M12-C019": ("éclair éx", 9),
         "LF-M12-C020": ("👩‍💻 dev", 5), "LF-M12-C021": ("", 0)}


@driver(*CARET)
def c016(case):
    text, units = CARET[case["id"]]
    ed = _editor(text, units, 0)
    try:
        native = ed._native_range()
        anchor = ed.insertion_point()
        want = cp_of_units(text, units)
        arrival = ed.receive("X", origin=ORIGIN_DICTATED, at_chars=anchor)
        final = str(ed.current_content())
        return verdict({
            "native_units_match_encoder": native == (units, 0),
            "anchor_is_code_point": anchor == want,
            "insertion_at_caret": final == text[:want] + "X" + text[want:],
            "receipt_returned": arrival is not None,
        }, {"anchor": anchor, "want": want})
    finally:
        ed.close()


MALFORMED = {"LF-M12-C022": (2, 1), "LF-M12-C023": (0, 2),
             "LF-M12-C024": (-1, 1), "LF-M12-C025": (0, -1),
             "LF-M12-C026": (4, 1), "LF-M12-C027": (10 ** 12, 10 ** 12)}


@driver(*MALFORMED)
def c022(case):
    text = "A😀B"
    loc, length = MALFORMED[case["id"]]
    try:
        out = notes_mod.utf16_range_to_codepoints(text, loc, length)
        refused = False
    except ValueError:
        out, refused = None, True
    # A valid control converts exactly (the boundary is not refusing all).
    control = notes_mod.utf16_range_to_codepoints(text, 1, 2) == (1, 2)
    return verdict({"refused": refused, "valid_control": control},
                   {"converted": out})


@driver("LF-M12-C028")
def c028(case):
    """D01: a nonzero selection at PTT anchors the dictation at the
    selection's start; the selected text is never replaced."""
    text = "A😀B"
    ed = _editor(text, 1, 2)
    try:
        kind, rng = ed.selection()
        anchor = ed.insertion_point()
        ed.receive("X", origin=ORIGIN_DICTATED, at_chars=anchor)
        return verdict({
            "converted_selection": (kind, rng) == ("range", (1, 2)),
            "anchor_at_start": anchor == 1,
            "selection_kept": str(ed.current_content()) == "AX😀B",
        })
    finally:
        ed.close()


# ---- autosave / generations ----------------------------------------------

class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@driver("LF-M12-C029")
def c029(case):
    with w.NoteWorld() as nw:
        out = nw.notes.create_note("base")
        clock = Clock()
        m = notes_mod.NotesEditorModel(out["note_id"], out["revision"],
                                       "base", clock=clock)
        m.edit("base typed")
        early = m.due()
        clock.t = 1.6
        late = m.due()
        r = m.flush(nw.notes)
        last = revisions(nw, out["note_id"])[-1]
        return verdict({"waits_for_debounce": not early and late,
                        "commits_typed_autosave": r["outcome"] == "flushed"
                        and last[2] == ORIGIN_TYPED
                        and last[3] == TRIGGER_AUTOSAVE
                        and last[4] == "base typed"})


@driver("LF-M12-C030")
def c030(case):
    """A no-change flush clears the marker only while no newer edit
    exists: an edit landing while its clear op waits keeps it armed."""
    with w.NoteWorld() as nw:
        out = nw.notes.create_note("saved")
        m = notes_mod.NotesEditorModel(
            out["note_id"], out["revision"], "saved",
            on_dirty=lambda n: nw.notes.mark_dirty(n))
        m.edit("saved x")
        m.edit("saved")                 # back to the saved text
        hold = w.WriterHold(nw.store)
        t = threading.Thread(target=lambda: m.flush(nw.notes))
        t.start()
        assert w.wait_queued(nw.store, 1)
        m.on_dirty = None               # the marker is already armed
        m.edit("saved newer")           # newer generation while queued
        hold.release()
        t.join(10)
        marker = nw.notes.note(out["note_id"])["dirty_at_utc"]
        latest = rem._latest(nw, out["note_id"])["content"]
        r = m.flush(nw.notes)
        # The no-change clear ran while a newer generation existed: it
        # must leave the marker — unless the same flush went on to save
        # that newer generation (then the newest save cleared it).
        return verdict({"newer_generation_keeps_marker": marker is not None
                        or latest == "saved newer",
                        "newest_save_settles_it":
                            rem._latest(nw, out["note_id"])["content"]
                            == "saved newer" and nw.notes.note(
                                out["note_id"])["dirty_at_utc"] is None
                            and r["outcome"] in ("flushed", "no_change")},
                       barriers=list(w.REACHED))


@driver("LF-M12-C031")
def c031(case):
    return via(rem.r03a_failed_switch_save_keeps_the_tail)


@driver("LF-M12-C032")
def c032(case):
    """Snapshot waits (bounded) for the save in flight and then covers
    the generation current at its call."""
    with w.HubWorld() as hw:
        n = hw.notes.create_note("s0")["note_id"]
        hw.open_note(n)
        hw.type("s0 A")
        latch = w.Latch("autosave_before_commit").install(
            hw.notes, "append_revision")
        hw.hub.editor.flush_async()
        assert latch.wait()
        hw.type("s0 A B")
        threading.Timer(0.2, latch.release).start()
        hw.hub.scratchpadSnapshot_(None)
        status = str(hw.hub.scratchpad_status.stringValue())
        committed = rem._latest(hw, n).get("content") == "s0 A B"
        latch.remove()
        hw.settle_notes()
        return verdict({"generation_committed_at_return": committed,
                        "status_names_saved_state": "saved" in status},
                       {"status": status}, barriers=list(w.REACHED))


@driver("LF-M12-C033")
def c033(case):
    with w.NoteWorld() as nw:
        out = nw.notes.create_note("base text")
        m = notes_mod.NotesEditorModel(out["note_id"], out["revision"],
                                       "base text")
        a = m.insert(" OUT", at=9, origin=ORIGIN_TRANSFORM,
                     task_key="ttask:synthetic", transform_id="t:x",
                     transform_revision=3)
        st = rem._fail_append(nw.notes)
        r1 = m.flush(nw.notes)
        st["armed"] = False
        r2 = m.flush(nw.notes)
        row = nw.rows("SELECT origin, task_key, transform_id,"
                      " transform_revision FROM note_revisions WHERE"
                      " revision_id=?", (a.revision_id,))
        return verdict({"first_attempt_failed": r1["outcome"] == "failed",
                        "retry_committed": r2["outcome"] == "flushed",
                        "metadata_kept": row == [(ORIGIN_TRANSFORM,
                                                  "ttask:synthetic", "t:x",
                                                  3)],
                        "receipt_committed": a.outcome == "committed"})


@driver("LF-M12-C034")
def c034(case):
    return via(rem.r09b_failed_older_arrival_never_overwrites_newer_identity)


@driver("LF-M12-C035")
def c035(case):
    with w.NoteWorld() as nw:
        out = nw.notes.create_note("base")
        m = notes_mod.NotesEditorModel(
            out["note_id"], out["revision"], "base",
            on_dirty=lambda n: nw.notes.mark_dirty(n))
        rem._fail_append(nw.notes)
        a = m.insert(" spoken", at=4, origin=ORIGIN_DICTATED,
                     source_job_id="job-synthetic")
        r = m.flush(nw.notes)
        marker = nw.notes.note(out["note_id"])["dirty_at_utc"]
        return verdict({"failed": r["outcome"] == "failed",
                        "marker_armed_durably": marker is not None,
                        "receipt_not_committed": a.outcome is None,
                        "buffer_kept": m.content == "base spoken"})


@driver("LF-M12-C036")
def c036(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("x")["note_id"]
        nw.notes.delete_note(n)
        armed = nw.notes.mark_dirty(n)
        cleared = nw.notes.clear_dirty(n)
        rows = nw.rows("SELECT COUNT(*) FROM notes WHERE note_id=?", (n,))
        return verdict({"mark_reports_no_op": armed is False,
                        "clear_reports_no_op": cleared is False,
                        "no_row_recreated": rows[0][0] == 0})


@driver("LF-M12-C038")
def c038(case):
    with w.NoteWorld() as nw:
        out = nw.notes.create_note("c")
        m = notes_mod.NotesEditorModel(out["note_id"], out["revision"], "c")
        m.edit("c admitted")
        m.close()
        m.edit("c refused")
        a = m.insert(" X", at=0, origin=ORIGIN_DICTATED)
        r = m.flush(nw.notes)
        again = m.flush(nw.notes)
        return verdict({"new_input_refused": a is None
                        and m.content == "c admitted",
                        "admitted_work_saved": r["outcome"] == "flushed"
                        and rem._latest(nw, out["note_id"])["content"]
                        == "c admitted",
                        "closed_after": again["outcome"] == "closed"})


# ---- region provenance -----------------------------------------------------

def _arrival_case(persisted, typed, text, at, *, replace=None,
                  origin=ORIGIN_DICTATED):
    """Persist ``persisted``, type ``typed`` (unsaved), then an arrival;
    returns (final content, [dictated/transform words])."""
    with w.NoteWorld() as nw:
        out = nw.notes.create_note(persisted)
        m = notes_mod.NotesEditorModel(out["note_id"], out["revision"],
                                       persisted)
        m.edit(typed)
        m.insert(text, at=at, replace=replace, origin=origin,
                 source_job_id="job-synthetic"
                 if origin == ORIGIN_DICTATED else None,
                 task_key="ttask:synthetic"
                 if origin == ORIGIN_TRANSFORM else None)
        m.flush(nw.notes)
        rev = rem._latest(nw, out["note_id"])
        return rev["content"], spans_of(rev["content"], rev["spans"],
                                        origin)


@driver("LF-M12-C039")
def c039(case):
    return via(rem.r04_typed_prefix_never_gets_dictated_provenance)


@driver("LF-M12-C040")
def c040(case):
    final, owned = _arrival_case("alpha beta", "typed word alpha beta",
                                 "OMEGA", 11, replace=(11, 16),
                                 origin=ORIGIN_TRANSFORM)
    return verdict({"final": final == "typed word OMEGA beta",
                    "only_output_words": owned == ["OMEGA"]},
                   {"owned": owned})


@driver("LF-M12-C041")
def c041(case):
    final, owned = _arrival_case("a", "a   ", "D", 4)
    return verdict({"final": final == "a   D", "only_arrival": owned ==
                    ["D"]}, {"owned": owned})


@driver("LF-M12-C042")
def c042(case):
    typed = "😀 typed é "
    final, owned = _arrival_case("x", typed, "D", len(typed))
    return verdict({"final": final == typed + "D",
                    "only_arrival": owned == ["D"]}, {"owned": owned})


def _rebase_case(start, dictated_words, typed_steps):
    """A dictated first arrival then typed full-text steps; returns the
    final content and its dictated words."""
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("")["note_id"]
        nw.notes.append_revision(n, start, origin=ORIGIN_DICTATED,
                                 trigger=TRIGGER_SYSTEM,
                                 source_job_id="job-synthetic",
                                 inserted_at_chars=0,
                                 inserted_text=dictated_words)
        for t in typed_steps:
            nw.notes.append_revision(n, t, origin=ORIGIN_TYPED,
                                     trigger=TRIGGER_AUTOSAVE)
        rev = rem._latest(nw, n)
        return rev["content"], spans_of(rev["content"], rev["spans"],
                                        ORIGIN_DICTATED)


@driver("LF-M12-C043", "LF-M12-C044", "LF-M12-C045")
def c043(case):
    """The corpus fixture verbatim through the production rebase helper:
    the dictated occurrence was deleted, the typed one survived."""
    fx = case["synthetic_fixture"]
    s, e = fx["dictated_span"]
    surviving, edited = notes_mod.rebase_spans(
        fx["old"], [[s, e, ORIGIN_DICTATED, "job-synthetic"]], fx["new"])
    owned = spans_of(fx["new"], surviving, ORIGIN_DICTATED)
    checks = {"typed_survivor_not_claimed": owned == [],
              "abstention_reported": len(edited) == 1}
    if case["id"] == "LF-M12-C043":
        # ...and end to end through the note store's revision chain.
        checks["store_path"] = via(
            rem.r17_surviving_typed_echo_is_not_dictated).status == "PASS"
    return verdict(checks, {"owned": owned, "edited": edited})


WS = {"LF-M12-C046": "a,b c", "LF-M12-C047": "a\xa0b",
      "LF-M12-C048": "你好世界", "LF-M12-C049": "👩‍💻 😀",
      "LF-M12-C050": "a\n\nb", "LF-M12-C051": "a    b"}


@driver(*WS)
def c046(case):
    text = WS[case["id"]]
    with w.NoteWorld() as nw:
        out = nw.notes.create_note("")
        m = notes_mod.NotesEditorModel(out["note_id"], out["revision"], "")
        m.insert(text, at=0, origin=ORIGIN_DICTATED,
                 source_job_id="job-synthetic")
        m.flush(nw.notes)
        rev = rem._latest(nw, out["note_id"])
        owned = spans_of(rev["content"], rev["spans"], ORIGIN_DICTATED)
        wc = nw.rows("SELECT word_count FROM note_revisions WHERE"
                     " revision_id=?", (rev["revision_id"],))[0][0]
        return verdict({"spans_are_whitespace_words": owned
                        == text.split(),
                        "word_count_whitespace": wc == len(text.split())},
                       {"owned": owned})
