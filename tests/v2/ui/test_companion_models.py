"""Desktop companion — Review, Undo, Export/Validate and Your Voice
(headless).

The real CompanionController over the real coordinator's M14 services
(the lifecycle Harness) with the recording host of test_companion_bridge:
each action names the list or snapshot the page rendered, and a list or
snapshot that has changed since is refused, never guessed at. Export's
folder comes from a stand-in for the native panel, inside the temporary
folder. Every string is synthetic.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_companion_models.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
for p in (HERE.parents[3], HERE.parent, HERE.parents[1] / "lifecycle"):
    sys.path.insert(0, str(p))

from test_companion_bridge import CWorld  # noqa: E402
from test_training_review_hub import _seed_example  # noqa: E402


def review(w):
    for command, payload in (("models.subview", {"subview": "training"}),
                             ("training.tab", {"tab": "review"})):
        r = w.host.send(command, payload)
        assert r["status"] == "success", r
        w.drain()
    w.ctl.request_flush()
    w.drain()
    return w.host.latest("models")["data"]


def test_mine_approve_undo_bind_to_the_rendered_lists():
    with CWorld() as w:
        w.select("models")
        _seed_example(w.d, "ship the clod code branch",
                      "Ship the clod code branch",
                      observation=("Ship the clod code branch",
                                   "Ship the Claude Code branch"))
        assert w.host.send("review.mine")["status"] == "success"
        w.drain()
        data = review(w)
        row = next(r for r in data["queue"] if (r.get("suggestion") or {})
                   .get("alias") == "clod")
        cid, token = row["candidate_id"], data["queue_token"]
        # A candidate the page did not render, or a list that changed
        # since, is refused.
        out = w.host.send("review.approve", {
            "queue_token": token, "candidate_id": "cand-not-rendered",
            "counterexample": ""})
        assert out["status"] == "stale", out
        out = w.host.send("review.approve", {
            "queue_token": "0" * 16, "candidate_id": cid,
            "counterexample": ""})
        assert out["status"] == "stale", out
        out = w.host.send("review.approve", {
            "queue_token": token, "candidate_id": cid, "counterexample": ""})
        assert out["status"] == "success", out
        approved = w.d._learning.candidates(status="approved")
        assert [c["candidate_id"] for c in approved] == [cid], approved
        # Before the page has the new queue, the service itself refuses a
        # second approval; once the new queue is rendered, the old list
        # is stale.
        out = w.host.send("review.approve", {
            "queue_token": token, "candidate_id": cid, "counterexample": ""})
        assert out["status"] == "refusal" and \
            out["reason_code"] == "not_pending:approved", out
        data = review(w)
        out = w.host.send("review.approve", {
            "queue_token": token, "candidate_id": cid, "counterexample": ""})
        assert out["status"] == "stale", out
        assert [a["candidate_id"] for a in data["approved"]] == [cid]
        out = w.host.send("review.undo", {
            "approved_token": data["approved_token"], "candidate_id": cid})
        assert out["status"] == "success", out
        assert not w.d._learning.candidates(status="approved")
        again = w.host.send("review.undo", {
            "approved_token": data["approved_token"], "candidate_id": cid})
        assert again["status"] == "refusal" and \
            again["reason_code"] == "not_approved:pending", again
        old = data["approved_token"]
        review(w)
        again = w.host.send("review.undo", {"approved_token": old,
                                            "candidate_id": cid})
        assert again["status"] == "stale", again
        w.drain()
        assert w.host.latest("models")["note"]["code"] == "undone"
    print("ok  review: mining, approve and undo name the list the page"
          " rendered; a changed list is stale, never guessed")


class Panels:
    """Stands in for the native folder panel; None is a cancel."""
    answer = None

    def choose_folder(self):
        return self.answer


def test_export_and_validate_bind_to_the_chosen_folder():
    panels = Panels()
    with CWorld(file_panels=panels) as w:
        folder = w.h.tmp / "exports"
        folder.mkdir()
        w.select("models")
        _seed_example(w.d, "a synthetic example", "A synthetic example.")
        assert w.host.send("export.validate")["reason_code"] == \
            "choose_folder"
        out = w.host.send("export.choose_folder")
        assert out["status"] == "cancelled" and w.ctl.export_folder is None
        panels.answer = str(folder)
        out = w.host.send("export.choose_folder")
        assert out["status"] == "success" and \
            out["result"]["folder"] == str(folder), out
        out = w.host.send("export.run", {"views": ["not_a_view"]})
        assert out["reason_code"] == "choose_views_and_folder", out
        # While an export of the folder runs, or its outcome is unknown,
        # neither a second export nor a Validate starts.
        w.ctl.exports_running[str(folder)] = 1
        assert w.host.send("export.validate")["reason_code"] == \
            "export_running_or_unknown"
        assert w.host.send("export.run", {"views": ["cleanup_supervised"]})[
            "reason_code"] == "export_running"
        w.ctl.exports_running.clear()
        w.ctl.exports_unknown.add(str(folder))
        assert w.host.send("export.validate")["reason_code"] == \
            "export_running_or_unknown"
        w.ctl.exports_unknown.clear()
        # Without collection consent the exporter refuses, and the page
        # is told why.
        out = w.host.send("export.run", {"views": ["cleanup_supervised"]})
        assert out["status"] == "success", out
        w.drain()
        note = w.ctl.notes.get("export") or {}
        assert note.get("code") == "export_failed" and \
            note.get("type") == "ExportError" and note.get("reason"), note
        w.d.consent.set("enabled", note="companion export test")
        out = w.host.send("splits.assign")
        assert out["status"] == "success", out
        w.drain()
        out = w.host.send("export.run", {"views": ["cleanup_supervised"]})
        assert out["status"] == "success", out
        w.drain()
        assert not w.ctl.exports_running
        note = w.ctl.notes.get("export") or {}
        assert note.get("code") == "exported", note
        out = w.host.send("export.validate")
        assert out["status"] == "success", out
        w.drain()
        v = w.ctl.export_validation
        assert v["folder"] == str(folder) and v["state"] == "done" \
            and v["valid"] is True, v
    print("ok  export: the folder comes from the panel; run and validate"
          " bind to it and never overlap")


def test_voice_exclusion_names_the_rendered_snapshot():
    with CWorld() as w:
        for i in range(3):
            _seed_example(w.d, f"synthetic voice sample {i}",
                          f"Synthetic voice sample {i}.")
        w.select("insights")
        assert w.host.send("insights.subview", {"subview": "voice"})[
            "status"] == "success"
        assert w.host.send("voice.generate")["status"] == "success"
        w.drain()
        current = w.d._profile.current()
        assert current is not None
        out = w.host.send("voice.exclude", {
            "snapshot_id": "snap-not-current", "example_id": "ex-x"})
        assert out["status"] == "stale", out
        out = w.host.send("voice.exclude", {
            "snapshot_id": current["snapshot_id"],
            "example_id": "ex-not-evidence"})
        assert out["status"] == "refusal" and \
            out["reason_code"] == "not_evidence_of_this_snapshot", out
        assert w.d._profile.current()["snapshot_id"] == \
            current["snapshot_id"], "a refused exclusion changed the profile"
    print("ok  your voice: Measure again runs the local service; exclusion"
          " names the snapshot the page rendered")


class SavePanels(Panels):
    def save_jsonl(self, name):
        return self.answer


def test_diagnostics_export_writes_the_rendered_window_redacted():
    import json
    panels = SavePanels()
    with CWorld(file_panels=panels) as w:
        w.d.v2log.emit("companion.test_event", level="INFO",
                       detail="CANARY_detail_text_never_exported")
        w.d.v2log.flush()
        w.select("diagnostics")
        w.ctl.request_flush()
        w.drain()
        token = w.host.latest("diagnostics")["data"]["token"]
        out = w.host.send("diagnostics.export", {"token": "0" * 16})
        assert out["status"] == "stale", out
        out = w.host.send("diagnostics.export", {"token": token})
        assert out["status"] == "cancelled", out
        path = w.h.tmp / "events.jsonl"
        panels.answer = str(path)
        out = w.host.send("diagnostics.export", {"token": token})
        assert out["status"] == "success", out
        w.drain()
        lines = path.read_text().splitlines()
        assert len(lines) == out["result"]["records"] > 0, len(lines)
        assert all(json.loads(x) for x in lines)
        # the event is in the window; only its free text is withheld
        assert "companion.test_event" in path.read_text()
        assert "CANARY_detail_text_never_exported" not in path.read_text()
        assert w.ctl.notes["diagnostics"]["code"] == "exported"
    print("ok  diagnostics: Export Redacted writes the window the page"
          " rendered, through the allowlist, to the panel's path")


if __name__ == "__main__":
    from AppKit import NSApplication
    NSApplication.sharedApplication().setActivationPolicy_(1)
    for test in (
            test_mine_approve_undo_bind_to_the_rendered_lists,
            test_export_and_validate_bind_to_the_chosen_folder,
            test_voice_exclusion_names_the_rendered_snapshot,
            test_diagnostics_export_writes_the_rendered_window_redacted):
        test()
