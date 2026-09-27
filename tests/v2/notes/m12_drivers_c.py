"""M12 corpus drivers, part C: the 28 stateful probes S001–S028.

Each probe holds its declared seam with a latch NAMED after the corpus
barrier (``m12_world.REACHED`` records it when reached), runs both
orderings where the order matters, and asserts the case's oracle. A
barrier the repaired design removed (the unlink before a commit; the
split content/pending read) is bound as structural in the adjudication
record, and the probe holds the nearest real seam instead."""

from __future__ import annotations

import os
import pathlib
import sqlite3
import sys
import threading

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import m12_world as w  # noqa: E402
import test_m12_remediation as rem  # noqa: E402
from m12_drivers import driver, verdict, via, Outcome, utf16_units  # noqa
from m12_drivers_b import _content, _job, _settled, _run_transform  # noqa

from localflow.v2 import note_export  # noqa: E402
from localflow.v2.notes import (ORIGIN_DICTATED, ORIGIN_RESTORE,  # noqa
                                ORIGIN_TYPED, TRIGGER_AUTOSAVE)

board = rem.board_count


def mark(name):
    w.REACHED.append(name)


def _no_autosave_threads():
    return w.wait_for(lambda: not any(
        t.name == "localflow-notes-autosave" and t.is_alive()
        for t in threading.enumerate()), 5)


@driver("LF-M12-S001")
def s001(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("A😀B")["note_id"]
        fn, args, job = rem._dictate(hw, n, at_utf16=3)
        latch = w.Latch("delivery_before_note_receive",
                        on_reach=lambda: None)
        latch.install(hw.hub, "scratchpad_receive")
        fn(*args)
        _settled(hw)
        final = job["final_text"]
        return verdict({
            "anchor_is_code_point_2":
                job["note_target"]["insertion_point"] == 2,
            "committed_exact": _content(hw, n) == "A😀" + final + "B",
            "confirmed": _job(hw, job)[0] == "insertion_confirmed"},
            barriers=list(w.REACHED))


@driver("LF-M12-S002")
def s002(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("alpha beta")["note_id"]
        fn, args, job = rem._dictate(hw, n, at_utf16=6)
        mark("after_ptt_before_result")
        hw.type("prefix alpha beta")
        b0 = board()
        fn(*args)
        _settled(hw)
        st, reason = _job(hw, job)
        return verdict({
            "policy_refusal": st == "saved_not_inserted"
            and reason == "note_changed_during_dictation",
            "no_stale_offset_write": _content(hw, n) == "prefix alpha beta",
            "no_clipboard": board() == b0, "no_external": hw.h.pastes == []},
            barriers=list(w.REACHED))


@driver("LF-M12-S003")
def s003(case):
    with w.HubWorld() as hw:
        # B holds the SAME text as A: only the note identity can refuse.
        a = hw.notes.create_note("alpha")["note_id"]
        b = hw.notes.create_note("alpha")["note_id"]
        fn, args, job = rem._dictate(hw, a)
        mark("after_ptt_before_result")
        hw.open_note(b)
        b0 = board()
        fn(*args)
        _settled(hw)
        return verdict({"no_write_to_b": _content(hw, b) == "alpha",
                        "a_unchanged": _content(hw, a) == "alpha",
                        "retained_not_inserted": _job(hw, job)[0]
                        == "saved_not_inserted",
                        "no_clipboard": board() == b0,
                        "no_external": hw.h.pastes == []},
                       barriers=list(w.REACHED))


@driver("LF-M12-S004")
def s004(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("A")["note_id"]
        hw.notes.add_attachment(n, w.PNG, "image/png", "p.png")
        # A first dictation commits: the note has a live evidence link
        # (positive population for the closure the deletion must do).
        fn0, args0, job0 = rem._dictate(hw, n)
        fn0(*args0)
        _settled(hw)
        linked = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_evidence_links WHERE note_id=? AND"
            " closed_utc IS NULL", (n,)).fetchone()[0])
        if not linked:
            return Outcome("ERROR", {}, note="no live evidence link"
                                             " (population)")
        fn, args, job = rem._dictate(hw, n)
        mark("after_ptt_before_result")
        hw.hub.scratchpadDelete_(None)
        hw.drain()
        b0 = board()
        fn(*args)
        _settled(hw)
        live = hw.store.submit(lambda db: (
            db.execute("SELECT COUNT(*) FROM note_revisions WHERE note_id=?"
                       " AND purged=0", (n,)).fetchone()[0],
            db.execute("SELECT COUNT(*) FROM note_attachments WHERE"
                       " note_id=? AND purged=0", (n,)).fetchone()[0],
            db.execute("SELECT COUNT(*) FROM note_evidence_links WHERE"
                       " note_id=? AND closed_utc IS NULL",
                       (n,)).fetchone()[0]))
        arts = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND purged=0"
            " AND content_text IS NOT NULL", (job["job_id"],)).fetchone()[0])
        return verdict({"no_resurrection": live == (0, 0, 0)
                        and rem._note(hw, n) is None,
                        "result_retained_in_history": arts >= 1
                        and _job(hw, job)[0] == "saved_not_inserted",
                        "no_clipboard": board() == b0},
                       barriers=list(w.REACHED))


@driver("LF-M12-S005")
def s005(case):
    del w.REACHED[:]
    mark("after_transform_capture_before_accept")
    out = via(rem.r13_whole_note_accept_refuses_after_growth)
    out.barriers = ["after_transform_capture_before_accept"] + out.barriers
    return out


@driver("LF-M12-S006")
def s006(case):
    res = {}
    for order in ("save_then_restore", "restore_before_save"):
        with w.HubWorld() as hw:
            n = hw.notes.create_note("R1 one")["note_id"]
            for t in ("R2", "R3", "R4", "R5 five"):
                hw.notes.append_revision(n, t, origin=ORIGIN_TYPED,
                                         trigger=TRIGGER_AUTOSAVE)
            hw.open_note(n)
            hw.type("R5 five six")
            save = w.Latch("autosave_before_commit").install(
                hw.notes, "append_revision")
            rest = w.Latch("restore_before_writer", on_reach=lambda: None)
            rest.install(hw.notes, "restore")
            hw.hub.editor.flush_async()
            assert save.wait()
            vids = list(hw.hub._scratchpad_version_ids)
            hw.hub.scratchpad_versions.selectItemAtIndex_(len(vids) - 1)
            if order == "save_then_restore":
                threading.Timer(0.2, save.release).start()
            hw.hub.scratchpadRestore_(None)
            status = str(hw.hub.scratchpad_status.stringValue())
            save.release()
            _no_autosave_threads()
            save.remove()
            rest.remove()
            _settled(hw)
            chain = hw.store.submit(lambda db: db.execute(
                "SELECT revision_id, parent_revision_id, origin,"
                " content_text FROM note_revisions WHERE note_id=? ORDER"
                " BY rowid", (n,)).fetchall())
            res[order] = (chain, status)
    chain1, _s1 = res["save_then_restore"]
    chain2, s2 = res["restore_before_save"]
    last1 = chain1[-1]
    return verdict({
        "restore_parents_the_current_revision":
            last1[2] == ORIGIN_RESTORE and last1[1] == chain1[-2][0]
            and last1[3] == "R1 one",
        "dirty_text_saved_first": chain1[-2][3] == "R5 five six",
        "stale_restore_refused_explicitly": "restore not done" in s2
        and not any(r[2] == ORIGIN_RESTORE for r in chain2),
        "dirty_text_kept_when_refused": chain2[-1][3] == "R5 five six"},
        barriers=list(w.REACHED))


@driver("LF-M12-S007")
def s007(case):
    res = {}
    for variant in ("success", "failure"):
        with w.HubWorld() as hw:
            a = hw.notes.create_note("A")["note_id"]
            b = hw.notes.create_note("B")["note_id"]
            hw.open_note(a)
            hw.type("A UNSAVED_A")
            latch = w.Latch("flush_before_admission").install(
                hw.notes, "append_revision")
            hw.hub.editor.flush_async()
            assert latch.wait()
            hw.hub.state.select_scratchpad_note(b)
            hw.drain()
            switched = hw.hub.editor.note_id == b
            latch.release(fault=RuntimeError("injected")
                          if variant == "failure" else None)
            _no_autosave_threads()
            latch.remove()
            # Right after the attempt: a failed save is kept and visible,
            # and reopening the note shows the unsaved buffer.
            kept = a in hw.hub.editor.unsaved_notes()
            not_yet = _content(hw, a) != "A UNSAVED_A"
            hw.open_note(a)
            shown = "UNSAVED_A" in str(hw.hub.editor.current_content())
            hw.hub.state.select_scratchpad_note(b)
            hw.drain()
            hw.settle_notes()            # the retry
            durable = _content(hw, a) == "A UNSAVED_A"
            res[variant] = (switched, durable, kept, shown, not_yet,
                            _content(hw, b) == "B")
    s_ok = res["success"]
    f_ok = res["failure"]
    # After the held save fails, A's text is never lost: either a queued
    # retry already made it durable, or it is kept, listed unsaved and
    # shown on reopen — and the retry during drain makes it durable.
    return verdict({"switch_completes": s_ok[0] and f_ok[0],
                    "success_is_durable": s_ok[1],
                    "failure_never_loses_the_text": (not f_ok[4])
                    or (f_ok[2] and f_ok[3]),
                    "failure_ends_durable": f_ok[1],
                    "b_not_overwritten": s_ok[5] and f_ok[5]},
                   barriers=list(w.REACHED))


@driver("LF-M12-S008")
def s008(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("a")["note_id"]
        hw.open_note(n)
        hw.type("typed one a ")
        latch = w.Latch("after_content_snapshot").install(
            hw.notes, "append_revision")
        hw.hub.editor.flush_async()
        assert latch.wait()
        arrival = hw.hub.editor.receive(
            "D", origin=ORIGIN_DICTATED, source_job_id="job-A", at_chars=12)
        latch.release()
        _no_autosave_threads()
        latch.remove()
        hw.settle_notes()
        rows = hw.store.submit(lambda db: db.execute(
            "SELECT origin, content_text, source_job_id, spans_json FROM"
            " note_revisions WHERE note_id=? ORDER BY rowid",
            (n,)).fetchall())
        final = rem._latest(hw, n)
        owned = [x for ws, o, j in w.span_words(final["content"],
                                                final["spans"])
                 if o == ORIGIN_DICTATED for x in ws]
        marker = rem._note(hw, n)["dirty_at_utc"]
        return verdict({
            "typed_generation_paired": rows[-2][:2] == (ORIGIN_TYPED,
                                                       "typed one a "),
            "arrival_paired": rows[-1][:3] == (ORIGIN_DICTATED,
                                               "typed one a D", "job-A"),
            "span_exact": owned == ["D"],
            "receipt_committed": arrival.outcome == "committed",
            "marker_settled_only_at_newest": marker is None},
            barriers=list(w.REACHED))


@driver("LF-M12-S009")
def s009(case):
    del w.REACHED[:]
    mark("flush_before_snapshot")
    out = via(rem.r09a_two_arrivals_keep_their_own_provenance)
    out.barriers = ["flush_before_snapshot"] + out.barriers
    return out


@driver("LF-M12-S010")
def s010(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("A")["note_id"]
        hw.open_note(n)
        hw.type("A PRIVATE_TAIL")
        latch = w.Latch("append_before_writer").install(
            hw.notes, "append_revision")
        hw.hub.editor.flush_async()
        assert latch.wait()
        payload = hw.notes.delete_note(n)
        hw.d.hubNoteDeleted(payload)
        latch.release()
        _no_autosave_threads()
        latch.remove()
        hw.hub.state.reload_scratchpad()
        hw.drain()
        hw.settle_notes()
        tail = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_revisions WHERE content_text LIKE"
            " '%PRIVATE_TAIL%'").fetchone()[0])
        return verdict({"no_new_revision": tail == 0,
                        "no_resurrection": rem._note(hw, n) is None,
                        "not_retained_for_recovery": n not in
                        hw.hub.editor.unsaved_notes()},
                       barriers=list(w.REACHED))


@driver("LF-M12-S011")
def s011(case):
    with w.HubWorld(consent=True) as hw:
        hw.h.d.supervisor.transform_output = f"{rem.CANARY} OUT"
        n = hw.notes.create_note(f"{rem.CANARY} source")["note_id"]

        def delete_now():
            payload = hw.notes.delete_note(n)
            hw.d.hubNoteDeleted(payload)
            hw.hub.editor.forget_note(n)
        latch = w.Latch("candidate_before_writer", on_reach=delete_now)
        latch.install(hw.d._tf_store, "record_candidate")
        panel = _run_transform(hw, n)
        latch.remove()
        mark("accept_before_effect")
        if panel is not None and panel._state.get("result") is not None:
            panel.panelAccept_(None)
        _settled(hw)
        revs = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_revisions WHERE note_id=? AND"
            " purged=0", (n,)).fetchone()[0])
        return verdict({"no_late_artifacts": rem._live_canaries(hw) == 0,
                        "no_accepted_revision": revs == 0
                        and rem._note(hw, n) is None},
                       barriers=list(w.REACHED))


@driver("LF-M12-S012")
def s012(case):
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("owner")["note_id"]
        proxy = {}

        def install():
            proxy["p"] = rem._FailCommitOnce(nw.store._db)
            nw.store._db = proxy["p"]
        nw.store._submit(install, wait=True)
        # The file now exists; the row's commit is the next commit.
        latch = w.Latch("add_after_file_before_commit",
                        on_reach=lambda: setattr(proxy["p"], "armed", True))
        latch.install(nw.notes, "_write_payload", after=True)
        try:
            nw.notes.add_attachment(n, w.PNG, "image/png", "p.png")
        except Exception:
            pass
        latch.remove()
        fired = proxy["p"].fired

        def remove():
            nw.store._db = proxy["p"]._db
        nw.store._submit(remove, wait=True)
        rows = nw.rows("SELECT content_path FROM note_attachments WHERE"
                       " purged=0")
        files = rem._managed_files(nw)
        pairs_ok = all(r[0] in files for r in rows)
        return verdict({"commit_failed": fired,
                        "no_live_row_without_file": pairs_ok,
                        "no_unowned_orphan": not files or bool(rows)},
                       barriers=list(w.REACHED))


def _structural(regression, seam):
    del w.REACHED[:]
    out = via(regression)
    out.barriers = [seam] + out.barriers
    return out


@driver("LF-M12-S013")
def s013(case):
    return _structural(rem.r05a_rolled_back_attachment_delete_keeps_payload,
                       "delete_before_commit")


@driver("LF-M12-S014")
def s014(case):
    return _structural(rem.r05b_rolled_back_note_delete_keeps_payload,
                       "note_delete_before_commit")


class _FailAfterFirstCopy:
    """The first write-open after an attachment copy exists in ``dest``
    fails — 'after attachment 1, before attachment 2' independent of the
    implementation's file order."""

    def __init__(self):
        self.dest = None
        self.fired = False
        sys.addaudithook(self)

    def __call__(self, event, args):
        if self.dest is None or self.fired or event != "open":
            return
        flags = args[2] if len(args) > 2 else 0
        mode = args[1] if len(args) > 1 else None
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")
                   ) or (isinstance(flags, int) and flags & (
                       os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        if not writing:
            return
        try:
            done = any(p.is_file() and not p.is_symlink()
                       and p.read_bytes() in (w.PNG, w.PNG2)
                       for p in self.dest.iterdir())
        except OSError:
            done = False
        if done:
            self.fired = True
            mark("after_attachment_1_before_attachment_2")
            raise OSError(28, "injected failure after the first copy")


_AFTER_FIRST = _FailAfterFirstCopy()


def _export_after_first(preexisting):
    nw, note_id, dest = rem._export_world()
    try:
        if preexisting:
            (dest / "note.md").write_bytes(w.KEEP_BYTES)
            (dest / "note-01.png").write_bytes(w.KEEP_BYTES)
            (dest / "note-02.png").write_bytes(w.KEEP_BYTES)
        before = w.tree_digest(dest)
        _AFTER_FIRST.dest, _AFTER_FIRST.fired = dest, False
        try:
            rep = note_export.write_export(dest / "note.md",
                                           nw.notes.open_note(note_id),
                                           nw.notes, "markdown")
        finally:
            _AFTER_FIRST.dest = None
        return rep, before, w.tree_digest(dest), _AFTER_FIRST.fired
    finally:
        nw.close()


@driver("LF-M12-S015")
def s015(case):
    del w.REACHED[:]
    rep, before, after, fired = _export_after_first(False)
    return verdict({"fault_reached": fired,
                    "not_labelled_complete": rep["ok"] is False,
                    "no_partial_set_left": after == before},
                   barriers=list(w.REACHED))


@driver("LF-M12-S016")
def s016(case):
    del w.REACHED[:]
    rep, before, after, fired = _export_after_first(True)
    return verdict({"fault_reached": fired,
                    "failed_honestly": rep["ok"] is False,
                    "preexisting_tree_identical": after == before},
                   barriers=list(w.REACHED))


@driver("LF-M12-S017")
def s017(case):
    with w.HubWorld(select_scratchpad=False) as hw:
        job_id, _r, _a = __import__("m09_world").seed_job(
            hw.store, "FINAL", captured="2026-09-25T06:00:00Z")
        latch = w.Latch("after_note_commit_before_source_delete",
                        on_reach=lambda: None)
        latch.install(hw.store, "delete_everywhere")
        latch.fault = RuntimeError("injected delete failure")
        out = hw.d.hubSaveHistoryRow("job", job_id, move=True)
        latch.remove()
        nid = out.get("note_id")
        arts = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND purged=0",
            (job_id,)).fetchone()[0])
        notes = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM notes").fetchone()[0])
        return verdict({
            "explicit_partial_result": out.get("outcome")
            == "move_failed_note_copied",
            "no_data_loss": nid and _content(hw, nid) == "FINAL"
            and arts >= 1,
            "exactly_one_copy": notes == 1},
            barriers=list(w.REACHED))


@driver("LF-M12-S018")
def s018(case):
    from m12_drivers_b import _deferred_quick_open
    with w.HubWorld(select_scratchpad=False) as hw:
        mark("insertion_busy_before_idle")
        deferred, made = _deferred_quick_open(hw, 2)
        return verdict({"intent_survives": deferred and made >= 1,
                        "one_note": made == 1},
                       barriers=list(w.REACHED))


@driver("LF-M12-S019")
def s019(case):
    with w.HubWorld(consent=True) as hw:
        n = hw.notes.create_note("")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        from localflow.v2 import training_data as td
        real = td._conn_append_revision
        events = rem._events(hw)
        latch = w.Latch("note_commit_before_evidence_admission",
                        on_reach=lambda: None)
        latch.install(hw.notes, "on_evidence")

        def failing(*a, **k):
            raise sqlite3.OperationalError("injected evidence failure")
        td._conn_append_revision = failing
        try:
            fn(*args)
            _settled(hw)
        finally:
            td._conn_append_revision = real
        latch.remove()
        committed = rem._latest(hw, n)
        honest = any(e[0] == "training.note_capture_failed"
                     for e in events)
        # Retry the same logical event (recorded policy: redelivery is
        # idempotent): exactly one observation.
        ev = {"revision_id": committed["revision_id"], "note_id": n,
              "kind": "note_region_arrival", "origin": ORIGIN_DICTATED,
              "source_job_id": job["job_id"]}
        hw.notes.on_evidence(dict(ev))
        hw.notes.on_evidence(dict(ev))
        obs = rem._note_observations(hw, job["job_id"],
                                     committed["revision_id"]) or []
        return verdict({"note_remains": bool(committed.get("content")),
                        "failure_reported": honest,
                        "no_duplicate_after_retry": len(obs) == 1},
                       barriers=list(w.REACHED))


@driver("LF-M12-S020")
def s020(case):
    with w.HubWorld() as hw:
        n = hw.notes.create_note("")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        fn(*args)
        hw.settle_notes()
        mark("note_commit_before_fact_confirmation")
        pre = rem._usage_outcome(hw, job["job_id"])
        pre_state = _job(hw, job)[0]
        hw.drain()
        base = _content(hw, n)
        for i in range(8):
            hw.notes.append_revision(n, base + f" later {i}",
                                     origin=ORIGIN_TYPED,
                                     trigger=TRIGGER_AUTOSAVE)
        hw.d._analytics.rebuild_aggregates()
        facts = hw.store.submit(lambda db: db.execute(
            "SELECT insertion_outcome, final_words FROM usage_facts WHERE"
            " kind='dictation'").fetchall())
        revs = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_revisions WHERE note_id=?",
            (n,)).fetchone()[0])
        return verdict({
            "not_confirmed_before_the_receipt": "confirmed" not in pre
            and pre_state == "insertion_posted",
            "confirmed_after_it": _job(hw, job)[0] == "insertion_confirmed",
            "one_positive_fact": facts == [("confirmed", 3)],
            "nine_revisions_zero_extra_dictations": revs == 10},
            {"facts": facts, "revisions": revs}, barriers=list(w.REACHED))


@driver("LF-M12-S021")
def s021(case):
    with w.HubWorld(consent=True) as hw:
        # A real dictation of "echo" (cleanup upper-cases it) with its
        # training example, so the note is linked and mining runs.
        hw.h.d.supervisor.script = {"transcribe": [{"text": "echo"}]}
        n = hw.notes.create_note("")["note_id"]
        fn, args, job = rem._dictate(hw, n)
        fn(*args)
        _settled(hw)
        d = _content(hw, n).strip()
        links = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM note_evidence_links WHERE note_id=?",
            (n,)).fetchone()[0])
        for t in (f"{d} {d}", d, d + "ES"):    # typed; drop the first
            hw.notes.append_revision(n, t, origin=ORIGIN_TYPED,
                                     trigger=TRIGGER_AUTOSAVE)
        mark("after_edit_before_note_mining")
        from localflow.v2.learning import LearningService
        LearningService(hw.store).mine_observation_candidates()
        cands = hw.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM learning_candidates").fetchone()[0])
        final = rem._latest(hw, n)
        env = rem._note_observations(hw, job["job_id"]) or []
        return verdict({"linked_population": links >= 1 and bool(env),
                        "no_correction_attributed": cands == 0,
                        "no_dictated_claim_left": not [
                            x for x in final["spans"]
                            if x[2] == ORIGIN_DICTATED],
                        "never_asr_example": all(
                            o.get("asr_example") is False for o in env)},
                       barriers=list(w.REACHED))


@driver("LF-M12-S022")
def s022(case):
    """Portable half (the native half is N002/N004 in the native
    record): the NSTextView's selectedRange against the encoder."""
    text = "A😀B 👩‍💻 C"
    with w.HubWorld() as hw:
        n = hw.notes.create_note(text)["note_id"]
        hw.open_note(n)
        cp = text.index("B")
        units = utf16_units(text[:cp])
        hw.focus()
        hw.hub.editor.text.setSelectedRange_((units, 1))
        mark("native_selection_before_ptt_capture")
        native = hw.hub.editor._native_range()
        sel = hw.hub.editor.selection()
        fn, args, job = rem._dictate(hw, n, at_utf16=units)
        fn(*args)
        _settled(hw)
        final = job["final_text"]
        return verdict({"native_units_match": native == (units, 1),
                        "converted": sel == ("range", (cp, cp + 1)),
                        "inserted_exact": _content(hw, n)
                        == text[:cp] + final + text[cp:]},
                       barriers=list(w.REACHED))


@driver("LF-M12-S023")
def s023(case):
    return _structural(rem.r06b_timeout_then_late_commit_keeps_payload,
                       "insert_admitted_before_commit")


@driver("LF-M12-S024")
def s024(case):
    del w.REACHED[:]
    out = via(rem.r18_old_save_cannot_clear_a_newer_generation)
    return out


@driver("LF-M12-S025")
def s025(case):
    return _structural(
        rem.r09b_failed_older_arrival_never_overwrites_newer_identity,
        "atomic_capture")


@driver("LF-M12-S026")
def s026(case):
    return via(rem.r16a_late_callback_cannot_reopen_a_deleted_note)


@driver("LF-M12-S027")
def s027(case):
    return via(rem.r08b_quit_settles_admitted_note_work)


@driver("LF-M12-S028")
def s028(case):
    del w.REACHED[:]
    mark("dialog_before_return")
    out = via(rem.r11b_add_image_revalidates_after_the_dialog)
    out.barriers = ["dialog_before_return"] + out.barriers
    return out
