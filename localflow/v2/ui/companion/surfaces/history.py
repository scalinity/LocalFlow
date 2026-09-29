"""History (S19, M09-AC01/AC02; POLICY-D03; XM-C042; M12 transfers;
M13 usage deletion; M14 teach) — the AppKit Hub's rules, one for one.

Every action names the detail token it rendered and resolves it through
``ctl.rendered`` (stale otherwise). Copy and Paste Again re-check that
the final text's artifact is still live (G06 XM-C106); the Scratchpad
transfer is bound to the text shown by its hash; Teach is bound to the
cleaned artifact and its hash and carries one operation id per logical
action. A store timeout is an unknown outcome, never a failure.
"""

from __future__ import annotations

from .. import bridge as B
from ..bridge import Bool, Enum, Nullable, Str

KINDS = ("job", "legacy_db", "legacy_log")


def _final_artifact_id(detail):
    stage = next((s for s in detail.get("lineage") or ()
                  if s.get("stage") == detail.get("final_stage")), None)
    return ((stage or {}).get("artifact") or {}).get("artifact_id")


def _live_final_text(ctl, detail):
    """The rendered final text, only while its artifact is still live:
    a retention pass or deletion may have purged it after it was shown."""
    from ....history_queries import final_text
    text = final_text(detail)
    store = ctl.spec.get("store")
    if text is None or store is None:
        return text
    aid = _final_artifact_id(detail)
    if not aid:
        return text
    row = store.submit(lambda conn: conn.execute(
        "SELECT purged FROM artifacts WHERE artifact_id=?",
        (aid,)).fetchone())
    return text if row is not None and not row[0] else None


def register(ctl):
    br = ctl.bridge
    st = ctl.state
    coord = ctl.coordinator
    ctl.history_usage_unknown = False

    def detail(p):
        return ctl.rendered("history", p["token"])

    @br.command("history.search", {"text": Str(max_len=500)})
    def search(p):
        st.set_history_search(p["text"])
        return {}

    @br.command("history.filter", {"app": Nullable(Str(max_len=200),
                                                   optional=True),
                                   "mode": Nullable(Str(max_len=40),
                                                    optional=True)})
    def filters(p):
        from ....history_queries import MODES
        kw = {}
        if "app" in p:
            kw["app"] = p["app"] or ""
        if "mode" in p:
            if p["mode"] is not None and p["mode"] not in MODES:
                B.refuse("unknown_mode")
            kw["mode"] = p["mode"]
        st.set_history_filters(**kw)
        return {}

    @br.command("history.select", {"kind": Enum(KINDS),
                                   "id": Str(max_len=200, allow_empty=False)})
    def select(p):
        st.select_history_row(p["kind"], p["id"])
        return {}

    @br.command("history.reload")
    def reload(p):
        st.reload_history()
        return {}

    @br.command("history.replay", {"token": Str(max_len=40)})
    def replay(p):
        d = detail(p)
        if ctl.replay is None:
            B.unavailable("replay_unavailable")
        audio = d.get("audio") or {}
        out = ctl.replay.play_artifact(ctl.spec["store"],
                                       audio.get("artifact_id"))
        if not out.get("available"):
            # The detail's own reason when it has one (G06 XM-C108).
            reason = audio.get("reason") if not audio.get("available") \
                and audio.get("reason") else out.get("reason")
            B.refuse(reason or "unavailable")
        return {"playing": True}

    @br.command("history.stop_replay")
    def stop_replay(p):
        if ctl.replay is not None and hasattr(ctl.replay, "stop"):
            ctl.replay.stop()
        return {}

    @br.command("history.copy", {"token": Str(max_len=40)})
    def copy(p):
        d = detail(p)
        if coord is None:
            B.unavailable()
        text = _live_final_text(ctl, d)
        if text is None:
            B.refuse("nothing_to_copy")
        out = coord.hubCopyText(text) or {}
        if out.get("outcome") == "clipboard_busy":
            B.refuse("clipboard_busy")
        return {"outcome": "copied"}

    @br.command("history.paste_again", {"token": Str(max_len=40)})
    def paste_again(p):
        d = detail(p)
        if coord is None:
            B.unavailable()
        text = _live_final_text(ctl, d)
        if text is None:
            B.refuse("nothing_to_paste")
        # The job id keeps the re-paste's insertion attribution; the
        # final's artifact binds the source as shown (POLICY-D03).
        out = coord.hubPasteText(
            text, job_id=d.get("job_id"),
            source={"artifact_id": _final_artifact_id(d)}) or {}
        outcome = out.get("outcome")
        ctl.notes.pop("history", None)
        if outcome == "choosing_destination":
            return {"outcome": outcome}
        B.refuse(outcome or "unavailable")

    @br.command("history.retry", {"token": Str(max_len=40)})
    def retry(p):
        d = detail(p)
        if coord is None:
            B.unavailable()
        job_id = d.get("job_id")
        if not job_id:
            B.refuse("imported_row")
        # No destination of its own: the result is kept, never inserted
        # into whatever has focus (XM-C042).
        out = coord.hubRetryJob(job_id) or {}
        outcome, reason = out.get("outcome"), out.get("reason")
        if outcome == "requeued":
            return {"outcome": outcome}
        B.refuse(outcome or "unavailable", {"reason": reason})

    @br.command("history.teach", {"token": Str(max_len=40),
                                  "corrected": Str(max_len=20_000)})
    def teach(p):
        learning = ctl.spec.get("learning_service")
        corrected = (p["corrected"] or "").strip()
        if learning is None:
            B.unavailable("learning_unavailable")
        if not corrected:
            B.refuse("corrected_text_required")
        d = detail(p)
        job_id = d.get("job_id")
        if not job_id:
            B.refuse("imported_row")
        if d.get("final_stage") == "transformed":
            B.refuse("transformed_final")
        shown = next((s.get("artifact") for s in d.get("lineage") or ()
                      if s.get("stage") == "cleaned"), None)
        if not shown or not shown.get("present") or not shown.get("text"):
            B.refuse("no_retained_cleaned_text")
        from .... import ids
        expected = {"expected_final_artifact_id": shown["artifact_id"],
                    "expected_final_sha256": ids.sha256_text(shown["text"])}
        op = ctl.ops.get("teach", (job_id, shown["artifact_id"],
                                   ids.sha256_text(corrected)))
        unknown = False
        try:
            out = learning.teach_correction(job_id, corrected,
                                            operation_id=op, **expected)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except ValueError as e:
            B.refuse(str(e))
        finally:
            ctl.ops.settled("teach", unknown)
        sugg = out.get("suggestion") or None
        return {"candidate_id": out.get("candidate_id"),
                "status": out.get("status"),
                "suggestion": None if not sugg else {
                    "alias": sugg.get("alias"),
                    "canonical": sugg.get("canonical")}}

    @br.command("history.delete_usage", {"token": Str(max_len=40)})
    def delete_usage(p):
        if coord is None or not hasattr(coord, "hubDeleteUsageForJob"):
            B.unavailable()
        d = detail(p)
        out = coord.hubDeleteUsageForJob(d.get("job_id")) or {}
        outcome = out.get("outcome")
        ctl.history_usage_unknown = outcome == "outcome_unknown"
        if outcome == "deleted":
            return {"outcome": "deleted" if out.get("facts_deleted")
                    else "nothing_recorded"}
        if outcome == "outcome_unknown":
            B.unknown("usage_outcome_unknown")
        B.refuse(outcome or "unavailable")

    @br.command("history.to_scratchpad", {"token": Str(max_len=40),
                                          "move": Bool()})
    def to_scratchpad(p):
        if coord is None:
            B.unavailable()
        d = detail(p)
        from ....history_queries import final_text
        from .... import ids
        shown = final_text(d)
        if shown is None:
            B.refuse("no_final_text")
        kind, row_id = st.views["history"].get("detail_key")
        out = coord.hubSaveHistoryRow(
            kind, row_id, move=p["move"],
            expected_sha256=ids.sha256_text(shown)) or {}
        outcome = out.get("outcome")
        if kind == "job" and outcome == "moved":
            st.reload_history()
        if outcome in ("copied", "moved", "move_degrades_to_copy_legacy",
                       "move_failed_note_copied"):
            return {"outcome": outcome}
        if outcome in ("source_deletion_unknown", "create_unknown"):
            B.unknown(outcome)
        if outcome == "history_changed":
            B.stale("history_changed")
        B.refuse(outcome or "unavailable")

    def paste_ended(outcome):
        ctl.notes["history"] = {"kind": "paste", "code": outcome}
        ctl.emit("history.paste_ended", {"outcome": outcome})
        ctl.request_flush()
    ctl.paste_again_ended = paste_ended

    def usage_reconciled(result):
        if ctl.history_usage_unknown:
            ctl.history_usage_unknown = False
            ctl.notes["history"] = {"kind": "usage_reconciled",
                                    "code": result}
            ctl.request_flush()
    ctl.usage_reconciled_hooks.append(usage_reconciled)
