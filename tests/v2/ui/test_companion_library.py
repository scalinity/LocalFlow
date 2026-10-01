"""Desktop companion — Snippets, Styles and Transforms (headless).

The real CompanionController over the real M10/M11 stores (the lifecycle
Harness) with the recording host of test_companion_bridge. An Add reuses
its pre-allocated id only after an unknown outcome, so a retry confirms
the same row instead of adding a second; Enable/Disable names the
revision the page rendered; forms are schema-checked. Every string is
synthetic.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_companion_library.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
for p in (HERE.parents[3], HERE.parent, HERE.parents[1] / "lifecycle"):
    sys.path.insert(0, str(p))

from test_companion_bridge import CWorld  # noqa: E402

SNIPPET = {"trigger": "my address", "name": "Address",
           "content": "12 Orchard Lane, Springfield", "kind": "plain",
           "allow_rewrite": False}


def rows(w, view, key):
    w.ctl.request_flush()
    w.drain()
    return w.host.latest(view)[key]


def test_snippet_add_survives_an_unknown_outcome_once():
    with CWorld() as w:
        w.select("snippets")
        svc = w.ctl.spec["snippets_service"]
        real = svc.add_snippet
        calls = []

        def lost_reply(**kw):
            calls.append(kw["snippet_id"])
            real(**kw)             # written, but the answer is lost
            raise TimeoutError("store busy")
        svc.add_snippet = lost_reply
        out = w.host.send("snippets.add", SNIPPET)
        assert out["status"] == "outcome_unknown", out
        svc.add_snippet = lambda **kw: calls.append(kw["snippet_id"]) \
            or real(**kw)
        out = w.host.send("snippets.add", SNIPPET)
        # The retry names the same id; the store answers for that row.
        assert len(calls) == 2 and calls[0] == calls[1], calls
        assert out["status"] == "success" and \
            out["result"] == {"id": calls[0], "confirmed": True}, out
        mine = [s for s in rows(w, "snippets", "snippets")
                if s["trigger"] == "my address"]
        assert len(mine) == 1, mine
        # A fresh Add after that is a new row with a new id.
        out = w.host.send("snippets.add", dict(SNIPPET, trigger="sign off",
                                               content="Thanks, talk soon."))
        assert out["status"] == "success" and \
            out["result"]["id"] != calls[0], out
    print("ok  snippets: an Add retried after an unknown outcome is the"
          " same row; a fresh Add is a new one")


def test_snippet_enable_names_the_rendered_revision():
    with CWorld() as w:
        w.select("snippets")
        assert w.host.send("snippets.add", SNIPPET)["status"] == "success"
        row = rows(w, "snippets", "snippets")[0]
        out = w.host.send("snippets.update", {
            "snippet_id": row["snippet_id"],
            "changes": {"content": "14 Harbour Lane, Brightwater"}})
        assert out["status"] == "success", out
        # The page still shows the old revision: its toggle is stale.
        out = w.host.send("snippets.set_enabled", {
            "snippet_id": row["snippet_id"], "revision": row["revision"],
            "enabled": False})
        assert out["status"] == "stale" and \
            out["reason_code"] == "changed_elsewhere", out
        row = rows(w, "snippets", "snippets")[0]
        out = w.host.send("snippets.set_enabled", {
            "snippet_id": row["snippet_id"], "revision": row["revision"],
            "enabled": False})
        assert out["status"] == "success", out
        assert rows(w, "snippets", "snippets")[0]["enabled"] is False
        assert w.host.send("snippets.update", {
            "snippet_id": row["snippet_id"], "changes": {}})[
            "reason_code"] == "no_changes"
        out = w.host.send("snippets.add", dict(SNIPPET, colour="red"))
        assert out["status"] == "refusal" and \
            out["reason_code"].startswith("invalid_payload:colour"), out
    print("ok  snippets: Enable/Disable names the rendered revision; empty"
          " updates and unknown fields refuse")


def test_styles_and_transforms_round_trip():
    with CWorld() as w:
        w.select("styles")
        out = w.host.send("styles.add", {
            "name": "Mail", "scope_kind": "app", "scope_value": "Mail",
            "mode": "polish", "number_policy": "inherit"})
        assert out["status"] == "success", out
        rule = next(r for r in rows(w, "styles", "rules")
                    if r["name"] == "Mail")
        out = w.host.send("styles.set_enabled", {
            "rule_id": rule["rule_id"], "revision": rule["revision"] + 7,
            "enabled": False})
        assert out["status"] == "stale", out
        out = w.host.send("styles.preview", {
            "text": "hello team", "mode": "polish",
            "number_policy": "inherit"})
        assert out["status"] in ("success", "unavailable"), out
        w.select("transforms")
        out = w.host.send("transforms.add", {
            "name": "Shorter", "mode": "concise",
            "prompt": "Make it shorter without losing a requirement.",
            "shortcut": None, "target_profiles": [], "auto_apply": False})
        assert out["status"] == "success", out
        tid = out["result"]["id"]
        mine = [t for t in rows(w, "transforms", "transforms")
                if t["transform_id"] == tid]
        assert len(mine) == 1 and mine[0]["enabled"], mine
        out = w.host.send("transforms.set_enabled", {"transform_id": tid,
                                                     "enabled": False})
        assert out["status"] == "success", out
        assert [t for t in rows(w, "transforms", "transforms")
                if t["transform_id"] == tid][0]["enabled"] is False
    print("ok  styles/transforms: add, stale toggle refused, preview and"
          " enable round-trip through the real stores")


if __name__ == "__main__":
    from AppKit import NSApplication
    NSApplication.sharedApplication().setActivationPolicy_(1)
    for test in (
            test_snippet_add_survives_an_unknown_outcome_once,
            test_snippet_enable_names_the_rendered_revision,
            test_styles_and_transforms_round_trip):
        test()
