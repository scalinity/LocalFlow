"""M12 corpus drivers, part B: note destinations, note transforms,
attachments, exports, History transfer, quick-open, Hub binding,
evidence and the M13/M14 seams (C052–C125). Same contract as
``m12_drivers``: oracles from the case fixture, never from the code
under test; ERROR, never PASS, for a probe that cannot run."""

from __future__ import annotations

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
from m12_drivers import driver, verdict, via, Outcome  # noqa: E402

from localflow.v2 import ids  # noqa: E402
from localflow.v2 import note_export  # noqa: E402
from localflow.v2.notes import (ORIGIN_ATTACHMENT, ORIGIN_DICTATED,  # noqa
                                ORIGIN_RESTORE, ORIGIN_SNIPPET,
                                ORIGIN_TRANSFORM, ORIGIN_TYPED,
                                TRIGGER_AUTOSAVE, TRIGGER_EXPLICIT,
                                TRIGGER_SYSTEM)

board = rem.board_count


def _content(hw, note_id):
    return rem._latest(hw, note_id).get("content")


def _settled(hw):
    hw.settle_notes()
    hw.drain()


# ---- note destination (D01) ---------------------------------------------

@driver("LF-M12-C052")
def c052(case):
    """Edit BEFORE the anchor during dictation removes authority; an
    edit AFTER it keeps it (the anchor's prefix is unchanged)."""
    out = {}
    with w.HubWorld() as hw:
        n = hw.notes.create_note("alpha beta")["note_id"]
        fn, args, job = rem._dictate(hw, n, at_utf16=6)
        hw.type("ALPHA beta")                       # before the anchor
        b0 = board()
        fn(*args)
        _settled(hw)
        out["before"] = (_job(hw, job), _content(hw, n), board() == b0)
    with w.HubWorld() as hw:
        n = hw.notes.create_note("alpha beta")["note_id"]
        fn, args, job = rem._dictate(hw, n, at_utf16=6)
        hw.type("alpha beta gamma")                 # after the anchor
        fn(*args)
        _settled(hw)
        final = job["final_text"]
        out["after"] = (_job(hw, job), _content(hw, n),
                        "alpha " + final + "beta gamma")
    (st1, reason1), c1, board1 = out["before"]
    (st2, _r2), c2, want2 = out["after"]
    return verdict({
        "edit_before_anchor_refuses": st1 == "saved_not_inserted"
        and reason1 == "note_changed_during_dictation"
        and c1 == "ALPHA beta",
        "no_clipboard_on_refusal": board1,
        "edit_after_anchor_delivers": st2 == "insertion_confirmed"
        and c2 == want2})


def _job(hw, job):
    j = hw.store.job(job["job_id"]) or {}
    return j.get("state"), j.get("state_reason")


@driver("LF-M12-C053")
def c053(case):
    with w.HubWorld() as hw:
        a = hw.notes.create_note("alpha beta")["note_id"]
        b = hw.notes.create_note("other")["note_id"]
        fn, args, job = rem._dictate(hw, a, at_utf16=6)
        hw.open_note(b)
        hw.open_note(a)                  # switched away and back
        b0 = board()
        fn(*args)
        _settled(hw)
        final = job["final_text"]
        return verdict({
            "delivered_at_anchor": _content(hw, a)
            == "alpha " + final + "beta",
            "b_untouched": _content(hw, b) == "other",
            "confirmed": _job(hw, job)[0] == "insertion_confirmed",
            "no_clipboard": board() == b0,
            "no_external": hw.h.pastes == []})


@driver("LF-M12-C054")
def c054(case):
    return via(rem.r19a_closed_note_dictation_does_not_touch_the_clipboard)


@driver("LF-M12-C055")
def c055(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("to delete")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        hw.hub.scratchpadDelete_(None)
        hw.drain()
        b0 = board()
        fn(*args)
        _settled(hw)
        revs = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_revisions WHERE note_id=? AND"
            " purged=0", (n,)).fetchone()[0])
        return verdict({"saved_not_inserted": _job(hw, job)[0]
                        == "saved_not_inserted",
                        "no_resurrection": rem._note(hw, n) is None
                        and revs == 0,
                        "no_clipboard": board() == b0,
                        "no_external": hw.h.pastes == []})


@driver("LF-M12-C056")
def c056(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("not focused")["note_id"]
        hw.open_note(n)
        hw.hub.scratchpad_editor_active = lambda: False   # another responder
        hw.h.press()
        bound = "note_target" in (hw.d._job or {})
        hw.h.release()
        fn, args = hw.h.run_coordinator()
        fn(*args)
        _settled(hw)
        return verdict({"not_note_bound": not bound,
                        "note_unchanged": _content(hw, n) == "not focused",
                        "went_to_external_path": len(hw.h.pastes) == 1})


@driver("LF-M12-C057")
def c057(case):
    s = "012345678901234567890123456789"
    with w.HubWorld() as hw:
        n = hw.notes.create_note(s)["note_id"]
        hw.open_note(n)
        ed = hw.hub.editor
        ed.text.setSelectedRange_((10, 0))
        ta = hw.hub.scratchpad_capture_target()
        ed.text.setSelectedRange_((20, 0))
        tb = hw.hub.scratchpad_capture_target()
        ja = {"job_id": "job-synthetic-a", "note_target": ta}
        jb = {"job_id": "job-synthetic-b", "note_target": tb}
        rb = hw.hub.scratchpad_receive("BB", jb)     # B finishes first
        ra = hw.hub.scratchpad_receive("AA", ja)
        _settled(hw)
        want = s[:10] + "AA" + s[10:20] + "BB" + s[20:]
        rows = hw.store.submit(lambda db: db.execute(
            "SELECT source_job_id, spans_json FROM note_revisions WHERE"
            " note_id=? AND origin='dictated' ORDER BY rowid",
            (n,)).fetchall())
        return verdict({
            "anchors_captured_independently":
                (ta["insertion_point"], tb["insertion_point"]) == (10, 20),
            "both_delivered": rb is not None and ra is not None
            and rb.op_id != ra.op_id,
            "final_exact": _content(hw, n) == want,
            "own_job_per_revision": [r[0] for r in rows]
            == ["job-synthetic-b", "job-synthetic-a"],
            "no_external": hw.h.pastes == []})


# ---- note transforms -----------------------------------------------------

def _run_transform(hw, n, sel=None):
    hw.open_note(n)
    hw.focus()
    if sel is not None:
        hw.hub.editor.text.setSelectedRange_(sel)
    hw.hub.scratchpad_transforms.selectItemAtIndex_(0)
    hw.hub.scratchpadTransform_(None)
    w.wait_for(lambda: hw.d._tf_active is None, 10)
    hw.drain()
    return hw.d._tf_panel


@driver("LF-M12-C058")
def c058(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("polish this whole note")["note_id"]
        panel = _run_transform(hw, n)
        panel.panelAccept_(None)
        _settled(hw)
        rev = hw.store.submit(lambda db: db.execute(
            "SELECT origin, task_key FROM note_revisions WHERE note_id=?"
            " ORDER BY rowid DESC LIMIT 1", (n,)).fetchone())
        return verdict({"replaced_whole": _content(hw, n)
                        == "TRANSFORMED OUTPUT",
                        "transform_identity": rev[0] == ORIGIN_TRANSFORM
                        and bool(rev[1]),
                        "no_external": hw.h.pastes == []})


@driver("LF-M12-C059")
def c059(case):
    return via(rem.r13_whole_note_accept_refuses_after_growth)


@driver("LF-M12-C060")
def c060(case):
    return via(rem.c05_selection_transform_allows_an_outside_edit)


@driver("LF-M12-C061")
def c061(case):
    res = {}
    for label, edit, want in (
            ("unchanged_range", "ALPHA alpha",
             "ALPHA TRANSFORMED OUTPUT"),
            ("shifted_text", "x alpha alpha", "x alpha alpha")):
        with w.HubWorld(consent=True) as hw:
            n = hw.notes.create_note("alpha alpha")["note_id"]
            panel = _run_transform(hw, n, sel=(6, 5))
            hw.type(edit)
            hw.hub.editor.flush_now()
            panel.panelAccept_(None)
            _settled(hw)
            res[label] = _content(hw, n) == want
    return verdict({"replaces_only_the_captured_range":
                    res["unchanged_range"],
                    "never_retargets_the_other_copy": res["shifted_text"]})


@driver("LF-M12-C062")
def c062(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("alpha beta gamma")["note_id"]
        panel = _run_transform(hw, n, sel=(6, 4))
        hw.type("alpha BETA gamma")
        hw.hub.editor.flush_now()
        b0 = board()
        panel.panelAccept_(None)
        _settled(hw)
        return verdict({"refused": _content(hw, n) == "alpha BETA gamma",
                        "no_clipboard": board() == b0})


@driver("LF-M12-C063")
def c063(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("alpha beta gamma")["note_id"]
        panel = _run_transform(hw, n, sel=(0, 5))
        st = panel._state
        hw.d.tfTransformOfResult(st["result"], st["capture"],
                                 "builtin:concise")
        w.wait_for(lambda: hw.d._tf_active is None, 10)
        hw.drain()
        dest = hw.d._tf_panel._state["capture"].get("destination") or {}
        hw.hub.editor.text.setSelectedRange_((16, 0))   # caret elsewhere
        hw.d._tf_panel.panelAccept_(None)
        _settled(hw)
        return verdict({"chain_keeps_destination": dest.get("range")
                        in ((0, 5), [0, 5]),
                        "replaced_original_region": _content(hw, n)
                        == "TRANSFORMED OUTPUT beta gamma"})


@driver("LF-M12-C064")
def c064(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("")["note_id"]
        hw.open_note(n)
        before = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM transform_candidates").fetchone()[0])
        hw.hub.scratchpad_transforms.selectItemAtIndex_(0)
        hw.hub.scratchpadTransform_(None)
        w.wait_for(lambda: hw.d._tf_active is None, 5)
        hw.drain()
        after = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM transform_candidates").fetchone()[0])
        return verdict({"no_generation": hw.d._tf_panel is None
                        and after == before,
                        "note_unchanged": _content(hw, n) == ""})


@driver("LF-M12-C065")
def c065(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("doomed destination")["note_id"]
        panel = _run_transform(hw, n)
        hw.hub.scratchpadDelete_(None)
        hw.drain()
        b0 = board()
        panel.panelAccept_(None)
        _settled(hw)
        return verdict({"refused_no_resurrection":
                        rem._note(hw, n) is None,
                        "no_clipboard": board() == b0})


# ---- attachments: confinement family ---------------------------------------

CONFINE = {}
for i, kind in enumerate(("absolute", "parent_traversal",
                          "directory_symlink", "final_symlink",
                          "directory", "fifo")):
    for j, op in enumerate(("read", "delete_attachment", "delete_note")):
        CONFINE[f"LF-M12-C{66 + i * 3 + j:03d}"] = (kind, op)


@driver(*CONFINE)
def c066(case):
    kind, op = CONFINE[case["id"]]
    nw, att, note_id = rem._confinement_probe(kind)
    try:
        managed_before = w.tree_digest(nw.managed)
        with w.FS_LOG.record() as log:
            if op == "read":
                box = rem._read_bounded(nw, att)
                read_ok = not box.get("blocked") and box.get("out") is None
            elif op == "delete_attachment":
                nw.notes.delete_attachment(att)
                read_ok = True
            else:
                nw.notes.delete_note(note_id)
                read_ok = True
            nw.store.sync()
        outside_touched = w.touched_under(log, nw.outside)
        checks = {"refused_or_confined": read_ok,
                  "outside_sentinel_intact": nw.sentinel_intact(),
                  "outside_never_touched": not outside_touched}
        if op != "read" and kind in ("directory", "fifo",
                                     "final_symlink"):
            # A non-regular object in the root is never unlinked.
            name = {"directory": "att-dir.png", "fifo": "att-fifo.png",
                    "final_symlink": "att-link.png"}[kind]
            checks["nonregular_left_in_place"] = \
                name in w.tree_digest(nw.managed)
        if op != "read":
            checks["row_purged"] = nw.rows(
                "SELECT purged FROM note_attachments WHERE"
                " attachment_id=?", (att,))[0][0] == 1
        return verdict(checks, {"kind": kind, "op": op,
                                "managed_entries": len(managed_before)})
    finally:
        nw.close()


@driver("LF-M12-C084")
def c084(case):
    return via(rem.r06a_deleted_owner_is_refused)


@driver("LF-M12-C085")
def c085(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("owner")["note_id"]
        real = nw.notes.store.submit
        calls = {"n": 0}

        def submit(fn, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 2:          # the row publication
                def failing(db):
                    fn(db)
                    raise sqlite3.IntegrityError("injected insert failure")
                return real(failing, *a, **kw)
            return real(fn, *a, **kw)
        nw.notes.store.submit = submit
        try:
            nw.notes.add_attachment(n, w.PNG, "image/png", "p.png")
            raised = False
        except Exception:
            raised = True
        finally:
            nw.notes.store.submit = real
        rows = nw.rows("SELECT COUNT(*) FROM note_attachments")[0][0]
        files = rem._managed_files(nw)
        open_intents = nw.rows("SELECT COUNT(*) FROM purge_intents WHERE"
                               " completed_at_utc IS NULL")[0][0]
        return verdict({"reported_failure": raised, "no_row": rows == 0,
                        "no_orphan_file": not files,
                        "no_open_staging_intent": open_intents == 0})


@driver("LF-M12-C086")
def c086(case):
    return via(rem.r05a_rolled_back_attachment_delete_keeps_payload)


@driver("LF-M12-C087")
def c087(case):
    return via(rem.r05b_rolled_back_note_delete_keeps_payload)


@driver("LF-M12-C088")
def c088(case):
    return via(rem.r05c_failed_unlink_is_durably_pending_and_retried)


@driver("LF-M12-C089")
def c089(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("x")["note_id"]
        live = nw.notes.add_attachment(n, w.PNG, "image/png", "l.png")
        gone = nw.notes.add_attachment(n, w.PNG2, "image/png", "g.png")
        nw.notes.delete_attachment(gone["attachment_id"])
        missing = "![m](attachment:att-synthetic-missing)"
        nw.notes.append_revision(
            n, f"{live['marker']}\n\n{live['marker']}\n\n{gone['marker']}"
               f"\n\n{missing}\n", origin=ORIGIN_TYPED,
            trigger=TRIGGER_AUTOSAVE)
        dest = nw.root / "exp"
        dest.mkdir()
        rep = note_export.write_export(dest / "n.md", nw.notes.open_note(n),
                                       nw.notes, "markdown")
        text = (dest / "n.md").read_text()
        copied = [p for p in dest.iterdir() if p.name != "n.md"]
        return verdict({
            "one_copy_for_duplicate_marker": len(copied) == 1
            and copied[0].read_bytes() == w.PNG,
            "both_live_markers_rewritten": text.count(copied[0].name) == 2,
            "purged_and_missing_verbatim": gone["marker"].split("(")[1]
            in text and "attachment:att-synthetic-missing" in text,
            "reported": sorted(u["detail"] for u in rep["unsupported"])
            == ["payload_missing", "payload_missing"]})


@driver("LF-M12-C090")
def c090(case):
    """No Hub action removes an attachment; removing its marker by
    typing leaves the payload live and owned, reported as unreferenced
    at export (D06) — nothing deletes a payload behind a marker edit."""
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("x")["note_id"]
        a = nw.notes.add_attachment(n, w.PNG, "image/png", "p.png")
        nw.notes.append_revision(n, f"see {a['marker']}",
                                 origin=ORIGIN_ATTACHMENT,
                                 trigger=TRIGGER_SYSTEM)
        nw.notes.append_revision(n, "see", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        dest = nw.root / "exp"
        dest.mkdir()
        rep = note_export.write_export(dest / "n.md", nw.notes.open_note(n),
                                       nw.notes, "markdown")
        from localflow.v2.ui import hub as hub_mod
        actions = [x for x in dir(hub_mod.HubController)
                   if "ttachment" in x and x.endswith("_")
                   and "delete" in x.lower()]
        return verdict({"no_removal_action_exists": not actions,
                        "payload_still_live": nw.notes.attachment_payload(
                            a["attachment_id"]) == w.PNG,
                        "export_reports_unreferenced":
                            rep.get("unreferenced_attachments") == 1
                            and rep["attachments_copied"] == 0},
                       note="no attachment-removal action exists (reported)")


# ---- exports ---------------------------------------------------------------

@driver("LF-M12-C091")
def c091(case):
    nw, note_id, dest = rem._export_world()
    try:
        (dest / "note.md").write_bytes(w.KEEP_BYTES)
        (dest / "note-01.png").write_bytes(w.KEEP_BYTES)
        rep = note_export.write_export(dest / "note.md",
                                       nw.notes.open_note(note_id),
                                       nw.notes, "markdown")
        text = (dest / "note.md").read_text()
        names = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
        return verdict({
            "approved_main_replaced": rep["ok"]
            and text.startswith("# Title"),
            "unapproved_sibling_kept": (dest / "note-01.png").read_bytes()
            == w.KEEP_BYTES,
            "complete_set": sorted((dest / x).read_bytes() for x in names)
            == sorted([w.PNG, w.PNG2])})
    finally:
        nw.close()


@driver("LF-M12-C092")
def c092(case):
    nw, note_id, dest = rem._export_world()
    try:
        (dest / "note.txt").write_bytes(w.KEEP_BYTES)
        before = w.tree_digest(dest)
        hook = rem._hook("main1", 1)
        try:
            rep = note_export.write_export(dest / "note.txt",
                                           nw.notes.open_note(note_id),
                                           nw.notes, "plain")
        finally:
            hook.armed = False
        return verdict({"fault_ran": hook.fired,
                        "failed_honestly": rep["ok"] is False,
                        "tree_identical": w.tree_digest(dest) == before})
    finally:
        nw.close()


@driver("LF-M12-C093")
def c093(case):
    return via(rem.r02b_chmod_failure_keeps_preexisting_main_file)


@driver("LF-M12-C094")
def c094(case):
    nw, note_id, dest = rem._export_world()
    try:
        os.symlink(nw.sentinel, dest / "note-01.png")
        rep = note_export.write_export(dest / "note.md",
                                       nw.notes.open_note(note_id),
                                       nw.notes, "markdown")
        return verdict({"ok": rep["ok"],
                        "sentinel_intact": nw.sentinel_intact(),
                        "link_untouched": os.readlink(dest / "note-01.png")
                        == str(nw.sentinel)})
    finally:
        nw.close()


@driver("LF-M12-C095")
def c095(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("no marker")["note_id"]
        nw.notes.add_attachment(n, w.PNG, "image/png", "p.png")
        dest = nw.root / "exp"
        dest.mkdir()
        rep = note_export.write_export(dest / "n.md", nw.notes.open_note(n),
                                       nw.notes, "markdown")
        return verdict({"declared_policy": rep.get(
            "unreferenced_attachments") == 1,
            "no_hidden_copy": sorted(p.name for p in dest.iterdir())
            == ["n.md"]})


@driver("LF-M12-C096")
def c096(case):
    content = ("# Heading café 😀\n\nParagraph 你好.\n\n- one\n- two\n\n"
               "1. first\n2. second\n\n```\ncode line\n```\n\n"
               "[link](https://docs.example.com/x)\n")
    with w.NoteWorld() as nw:
        n = nw.notes.create_note(content)["note_id"]
        dest = nw.root / "exp"
        dest.mkdir()
        md = note_export.write_export(dest / "n.md", nw.notes.open_note(n),
                                      nw.notes, "markdown")
        pl = note_export.write_export(dest / "n.txt",
                                      nw.notes.open_note(n), nw.notes,
                                      "plain")
        mt = (dest / "n.md").read_text()
        pt = (dest / "n.txt").read_text()
        return verdict({
            "markdown_structure": all(x in mt for x in (
                "# Heading café 😀", "Paragraph 你好.", "- one",
                "1. first", "```", "[link](https://docs.example.com/x)")),
            "plain_structure": "Heading café 😀" in pt
            and "    code line" in pt and "- one" in pt,
            "both_ok": md["ok"] and pl["ok"]})


@driver("LF-M12-C097")
def c097(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("x")["note_id"]
        a = nw.notes.add_attachment(n, w.PNG, "image/png",
                                    "../../evil/../x.p/n/g")
        nw.notes.append_revision(n, a["marker"], origin=ORIGIN_ATTACHMENT,
                                 trigger=TRIGGER_SYSTEM)
        dest = nw.root / "exp"
        dest.mkdir()
        with w.FS_LOG.record() as log:
            rep = note_export.write_export(dest / "../exp/we ird*.md",
                                           nw.notes.open_note(n), nw.notes,
                                           "markdown")
        created = [p for p in dest.iterdir()]
        # Effects that create or change files (reading the managed
        # payloads through their directory is not an export effect).
        writes = [rec for rec in log if rec[0] != "open" or (
            len(rec) > 3 and isinstance(rec[3], int)
            and rec[3] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            or (len(rec) > 2 and isinstance(rec[2], str)
                and any(c in rec[2] for c in "wax+"))]
        outside = [x for x in w.touched_under(writes, nw.root)
                   if not os.path.realpath(x[1]).startswith(
                       os.path.realpath(dest))]
        return verdict({"ok": rep["ok"],
                        "only_direct_children": all(p.parent == dest
                                                    for p in created),
                        "nothing_outside_dest": not outside})


@driver("LF-M12-C098")
def c098(case):
    nw, note_id, dest = rem._export_world()
    try:
        (dest / "note.md").write_bytes(w.KEEP_BYTES)
        before = w.tree_digest(dest)
        note = nw.notes.open_note(note_id)

        def boom(_aid):
            raise RuntimeError("store is closing")
        nw.notes.attachment_payload = boom
        rep = note_export.write_export(dest / "note.md", note, nw.notes,
                                       "markdown")
        return verdict({"honest_failure": rep["ok"] is False
                        and rep["reason"] == "RuntimeError",
                        "tree_identical": w.tree_digest(dest) == before})
    finally:
        nw.close()


# ---- History transfer ------------------------------------------------------

@driver("LF-M12-C099", "LF-M12-C101")
def c099(case):
    return via(rem.r14a_copy_uses_the_current_attempt_final_artifact)


@driver("LF-M12-C100")
def c100(case):
    return via(rem.r14b_missing_final_is_refused_not_substituted)


@driver("LF-M12-C102")
def c102(case):
    with w.HubWorld(select_scratchpad=False) as hw:
        job_id, _r, _a = __import__("m09_world").seed_job(
            hw.store, "move but fail", captured="2026-09-25T07:00:00Z")

        def fail(*a, **k):
            raise RuntimeError("injected delete failure")
        hw.store.delete_everywhere = fail
        out = hw.d.hubSaveHistoryRow("job", job_id, move=True)
        nid = out.get("note_id")
        arts = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND purged=0",
            (job_id,)).fetchone()[0])
        return verdict({"explicit_partial": out.get("outcome")
                        == "move_failed_note_copied",
                        "note_has_text": nid and _content(hw, nid)
                        == "move but fail",
                        "source_kept": arts >= 1})


@driver("LF-M12-C103")
def c103(case):
    return via(rem.r24b_history_copy_unknown_is_not_failure_and_never_deletes)


@driver("LF-M12-C104")
def c104(case):
    return via(rem.l01_legacy_row_transfer_is_honest)


@driver("LF-M12-C105")
def c105(case):
    m09 = __import__("m09_world")
    with w.HubWorld(select_scratchpad=False) as hw:
        out = m09.seed_legacy_pair(hw.store, "pair raw words",
                                   "pair cleaned words", "log:synthetic:1")
        root = out if isinstance(out, str) else (
            out.get("raw_artifact_id") if isinstance(out, dict)
            else out[0])
        try:
            r = hw.d.hubSaveHistoryRow("legacy_log", root, move=True)
        except Exception as e:  # noqa: BLE001
            return Outcome("FAIL", {}, note=f"raised {type(e).__name__}")
        nid = r.get("note_id")
        return verdict({"copied_cleaned": nid is not None
                        and _content(hw, nid) == "pair cleaned words",
                        "move_degrades": r.get("outcome")
                        == "move_degrades_to_copy_legacy"})


@driver("LF-M12-C106")
def c106(case):
    return via(rem.r20_move_selector_reaches_the_transfer)


# ---- quick-open --------------------------------------------------------------

def _notes_count(hw):
    return hw.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM notes").fetchone()[0])


@driver("LF-M12-C107")
def c107(case):
    with w.HubWorld(select_scratchpad=False) as hw:
        before = _notes_count(hw)
        hw.d.quickOpenScratchpad_(None)
        hub = hw.d._hub
        hub.state.wait_for_queries()
        hw.mq.drain(hub.state)
        return verdict({"view": hub.state.selected_view == "scratchpad",
                        "one_note": _notes_count(hw) == before + 1,
                        "editor_bound": hub.editor.note_id is not None})


def _deferred_quick_open(hw, wakes):
    orig = hw.d._hub_blocks_show
    hw.d._hub_blocks_show = lambda: True
    try:
        hw.d.quickOpenScratchpad_(None)
        deferred = hw.d._hub_show_pending is True
    finally:
        hw.d._hub_blocks_show = orig
    before = _notes_count(hw)
    for _ in range(wakes):
        hw.d._flush_pending_hub_show()
        hw.mq.drain(hw.d._hub.state)
    return deferred, _notes_count(hw) - before


@driver("LF-M12-C108")
def c108(case):
    with w.HubWorld(select_scratchpad=False) as hw:
        deferred, made = _deferred_quick_open(hw, 1)
        return verdict({"deferred": deferred, "intent_survived": made == 1,
                        "view": hw.d._hub.state.selected_view
                        == "scratchpad"})


@driver("LF-M12-C109")
def c109(case):
    with w.HubWorld(select_scratchpad=False) as hw:
        deferred, made = _deferred_quick_open(hw, 2)
        return verdict({"deferred": deferred, "one_note": made == 1})


@driver("LF-M12-C110")
def c110(case):
    with w.HubWorld(select_scratchpad=False) as hw:
        before = _notes_count(hw)
        hw.d._closing = True
        try:
            hw.d.quickOpenScratchpad_(None)
        finally:
            hw.d._closing = False
        return verdict({"no_new_note": _notes_count(hw) == before})


# ---- Hub binding -------------------------------------------------------------

@driver("LF-M12-C111")
def c111(case):
    return via(rem.r11a_pin_and_delete_never_act_on_an_unrendered_note)


@driver("LF-M12-C112")
def c112(case):
    return via(rem.r23_chosen_transform_and_version_survive_refresh)


@driver("LF-M12-C113")
def c113(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("A")["note_id"]
        hw.open_note(n)
        hw.type("A UNSAVED_A")
        latch = w.Latch("hold_autosave").install(hw.notes,
                                                 "append_revision")
        payload = hw.notes.delete_note(n)            # independent action
        hw.d.hubNoteDeleted(payload)
        latch.release()
        hw.hub.state.reload_scratchpad()
        hw.drain()
        latch.remove()
        hw.settle_notes()
        revs = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_revisions WHERE note_id=? AND"
            " purged=0", (n,)).fetchone()[0])
        return verdict({"editor_revoked": hw.hub.editor.note_id is None,
                        "no_revision_to_deleted_note": revs == 0,
                        "not_resurrected": rem._note(hw, n) is None,
                        "not_retained": n not in
                        hw.hub.editor.unsaved_notes()})


# ---- evidence ----------------------------------------------------------------

@driver("LF-M12-C114")
def c114(case):
    return via(rem.r16b_same_revision_event_counts_once)


@driver("LF-M12-C115")
def c115(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note(f"# {w.TITLE_CANARY}\n\nbody")["note_id"]
        hw.notes.add_attachment(n, w.PNG, "image/png", w.FILENAME_CANARY)
        fn, args, job = rem._dictate(hw, n)
        fn(*args)
        _settled(hw)
        hw.d.v2log.close()
        envs = hw.store.submit(lambda db: db.execute(
            "SELECT envelope_json FROM training_revisions").fetchall())
        blob = "\n".join(e[0] for e in envs)
        events = "\n".join(p.read_text(errors="replace")
                           for p in (hw.h.tmp / "events").rglob("*")
                           if p.is_file())
        populated = '"notes"' in blob
        leak = [c for c in (w.TITLE_CANARY, w.FILENAME_CANARY.split(".")[0])
                if c in blob or c in events]
        return verdict({"positive_population": populated and events != "",
                        "no_title_or_filename": not leak})


@driver("LF-M12-C116")
def c116(case):
    with w.NoteWorld() as nw:
        def boom(event):
            raise RuntimeError("injected evidence failure")
        nw.notes.on_evidence = boom
        n = nw.notes.create_note("x")["note_id"]
        rev = nw.notes.append_revision(n, "x spoken", origin=ORIGIN_DICTATED,
                                       trigger=TRIGGER_SYSTEM,
                                       source_job_id="job-synthetic",
                                       inserted_at_chars=1,
                                       inserted_text=" spoken")
        return verdict({"note_committed": rem._latest(nw, n)["revision_id"]
                        == rev["revision_id"]})


@driver("LF-M12-C117")
def c117(case):
    return via(rem.r16a_late_callback_cannot_reopen_a_deleted_note)


@driver("LF-M12-C118")
def c118(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("link base")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        fn(*args)
        _settled(hw)
        links = hw.store.submit(lambda db: db.execute(
            "SELECT example_id FROM note_evidence_links WHERE note_id=?",
            (n,)).fetchall())
        if not links:
            return Outcome("ERROR", {}, note="no evidence link (population)")
        hw.store.set_example_state(links[0][0], "deleted")
        hw.notes.append_revision(n, _content(hw, n) + " typed more",
                                 origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        hw.notes.on_evidence(dict(
            revision_id=rem._latest(hw, n)["revision_id"], note_id=n,
            kind="note_region_edited", origin=ORIGIN_TYPED))
        row = hw.store.submit(lambda db: db.execute(
            "SELECT closed_utc, close_reason FROM note_evidence_links"
            " WHERE note_id=?", (n,)).fetchone())
        return verdict({"closed_unavailable": row[0] is not None
                        and row[1] == "example_unavailable"})


@driver("LF-M12-C119")
def c119(case):
    return via(rem.c06_consent_off_keeps_notes_working)


# ---- M13 / M14 seams ---------------------------------------------------------

def _dictation_facts(hw, job_id):
    return hw.store.submit(lambda db: db.execute(
        "SELECT insertion_outcome, final_words FROM usage_facts WHERE"
        " job_id=? AND kind='dictation'", (job_id,)).fetchall())


@driver("LF-M12-C120")
def c120(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        fn(*args)
        _settled(hw)
        hw.type(_content(hw, n) + " typed")
        hw.hub.editor.flush_now()
        hw.hub.scratchpadSnapshot_(None)
        hw.hub.scratchpadPin_(None)
        hw.drain()
        vids = list(hw.hub._scratchpad_version_ids)
        hw.hub.scratchpad_versions.selectItemAtIndex_(len(vids) - 1)
        hw.hub.scratchpadRestore_(None)
        hw.drain()
        facts = _dictation_facts(hw, job["job_id"])
        return verdict({"one_fact": len(facts) == 1,
                        "confirmed": facts and facts[0][0] == "confirmed",
                        "final_words_of_the_job": facts and facts[0][1]
                        == len(job["final_text"].split())},
                       {"facts": facts})


@driver("LF-M12-C121")
def c121(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        fn(*args)
        _settled(hw)
        before = hw.store.submit(lambda db: db.execute(
            "SELECT * FROM usage_facts ORDER BY fact_id").fetchall())
        for _ in range(3):
            hw.hub.scratchpadPin_(None)
            hw.drain()
        after = hw.store.submit(lambda db: db.execute(
            "SELECT * FROM usage_facts ORDER BY fact_id").fetchall())
        return verdict({"usage_unchanged": before == after and before})


def _learning(hw):
    from localflow.v2.learning import LearningService
    return LearningService(hw.store)


@driver("LF-M12-C122")
def c122(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        fn(*args)
        _settled(hw)
        base = _content(hw, n)
        hw.notes.append_revision(n, base + " unrelated note tail",
                                 origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        hw.notes.append_revision(n, base + " unrelated NOTE tail",
                                 origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE)
        _learning(hw).mine_observation_candidates()
        cands = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM learning_candidates WHERE"
            " source='note_revision'").fetchone()[0])
        env = rem._note_observations(hw, job["job_id"]) or []
        return verdict({"linked_population": bool(env),
                        "no_candidate_from_typed_region": cands == 0,
                        "never_asr_example": all(
                            o.get("asr_example") is False for o in env)})


@driver("LF-M12-C123")
def c123(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("seed words")["note_id"]
        steps = [("seed words OUT", ORIGIN_TRANSFORM, 10, " OUT"),
                 ("seed words OUT snip", ORIGIN_SNIPPET, 14, " snip"),
                 ("seed words OUT snip ![a](attachment:x)",
                  ORIGIN_ATTACHMENT, 19, " ![a](attachment:x)")]
        for text, origin, at, ins in steps:
            nw.notes.append_revision(n, text, origin=origin,
                                     trigger=TRIGGER_SYSTEM,
                                     task_key="ttask:syn" if origin ==
                                     ORIGIN_TRANSFORM else None,
                                     inserted_at_chars=at,
                                     inserted_text=ins)
        first = nw.revisions(n)[0][0]
        nw.notes.restore(n, first)
        spans = [s for r in nw.revisions(n) for s in json.loads(r[7])]
        return verdict({"no_dictated_region": not any(
            s[2] == ORIGIN_DICTATED for s in spans),
            "no_source_job": all(r[6] is None for r in nw.revisions(n))})


@driver("LF-M12-C124")
def c124(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("alpha beta")["note_id"]
        rev = nw.revisions(n)[0][0]
        art = nw.store.write_text_artifact(
            job_id=None, stage="review", role="note_after",
            text="SYNTHETIC mined words", retention_class="training")
        now = ids.now_utc_iso()
        for cid, status in (("c-open", "pending"),
                            ("c-appr", "approved"),
                            ("c-rej", "rejected")):
            nw.store.submit(lambda db, c=cid, s=status: db.execute(
                "INSERT INTO learning_candidates(candidate_id, job_id,"
                " source, observation_id, after_artifact_id,"
                " changed_spans_json, proposed_alias, status,"
                " created_at_utc, updated_at_utc) VALUES(?,?,?,?,?,?,?,?,"
                "?,?)", (c, "job-synthetic", "note_revision", rev,
                         art if c == "c-open" else None, "[[0,1]]",
                         "alias", s, now, now)))
        nw.notes.delete_note(n)
        rows = dict((r[0], r[1:]) for r in nw.rows(
            "SELECT candidate_id, status, changed_spans_json,"
            " proposed_alias FROM learning_candidates"))
        art_row = nw.rows("SELECT purged, content_text FROM artifacts"
                          " WHERE artifact_id=?", (art,))[0]
        return verdict({
            "open_goes_stale_cleared": rows["c-open"] == ("stale", "[]",
                                                          None),
            "open_payload_purged": art_row == (1, None),
            "approved_decision_kept": rows["c-appr"][0] == "approved"
            and rows["c-appr"][1] == "[]",
            "rejected_decision_kept": rows["c-rej"][0] == "rejected"
            and rows["c-rej"][1] == "[]"})


@driver("LF-M12-C125")
def c125(case):
    return via(rem.r15a_delete_purges_the_note_transform_graph)
