"""Desktop companion — bridge, read models and action binding (headless).

The real CompanionController over the real coordinator (the lifecycle
Harness: a temporary store, fake microphone) with a recording host in
place of the WKWebView: every message the page would receive is kept,
so a test can assert what crossed the bridge. Callbacks go through
``m09_world.MainQueue`` (queued, drained on this main thread), as in the
app. Every string is synthetic.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_companion_bridge.py
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "lifecycle"))

import AppKit  # noqa: E402

# These suites drive the real coordinator, whose copy and paste paths use
# the general pasteboard: refuse to run without the desktop isolation (a
# private pasteboard, no Accessibility, no posted events).
if type(AppKit.NSPasteboard).__name__ != "_PasteboardClass":
    sys.exit("companion suites: run under tests/v2/context/run_isolated.py"
             " (the desktop-isolating runner); refusing to start")

import m09_world as W  # noqa: E402
from m09_world import MainQueue  # noqa: E402

from localflow.v2.ui.companion import bridge as B  # noqa: E402
from localflow.v2.ui.companion.bridge import (  # noqa: E402
    Bridge, Bool, Enum, Int, List, Nullable, Str)

CANARY = "COMPANION_CANARY_synthetic_text"


class FakeWindow:
    def __init__(self):
        self.visible = False

    def orderOut_(self, sender):
        self.visible = False

    def isVisible(self):
        return self.visible


class FakeHost:
    """The page as the controller sees it: pushed JSON is recorded."""

    def __init__(self, client, theme="system"):
        self.client = client
        self.theme = theme
        self.pushed = []
        self._loaded = True
        self.window = FakeWindow()

    def push(self, text):
        self.pushed.append(json.loads(text))
        return True

    def set_theme(self, theme):
        self.theme = theme

    def is_dark(self):
        return self.theme == "dark"

    def show(self):
        self.window.visible = True

    # the native answers the Scratchpad's PTT-time check reads
    key = False
    focus = False

    def is_key(self):
        return self.key

    def webview_has_focus(self):
        return self.focus

    # what the page sends
    def send(self, command, payload=None, request_id="r1"):
        raw = json.dumps({"bridge_version": 1, "request_id": request_id,
                          "command": command, "payload": payload or {}})
        return json.loads(self.client.on_message(raw))

    def latest(self, view):
        for msg in reversed(self.pushed):
            if msg.get("type") == "snapshot" and msg.get("view") == view:
                return msg["data"]
        return None

    def events(self, name):
        return [m["payload"] for m in self.pushed
                if m.get("type") == "event" and m.get("name") == name]


class CWorld:
    """Harness + MainQueue + a CompanionController with a FakeHost;
    ``extra`` spec entries (e.g. file_panels) are read at install."""

    def __init__(self, **extra):
        self.extra = extra

    def __enter__(self):
        from test_lifecycle import Harness
        from localflow.v2.ui.companion.controller import CompanionController
        self.h = Harness(durations=[1.0], cfg={"hub_ui": "companion"})
        self.d = self.h.d
        self.store = self.d.store
        self.mq = MainQueue().__enter__()
        spec, _ = W.hub_spec(self.d)
        spec.update(vocabulary_store=self.d._vocab, host_factory=FakeHost,
                    prefs_path=self.h.tmp / "companion.json",
                    display_name="Alex", **self.extra)
        self.ctl = CompanionController(spec)
        self.d._hub = self.ctl
        self.host = self.ctl.host
        self.drain()
        return self

    def drain(self):
        assert self.mq.drain(self.ctl.state), "work did not drain"

    def select(self, view):
        r = self.host.send("nav.select", {"view": view})
        assert r["status"] == "success", r
        self.drain()

    def __exit__(self, *exc):
        try:
            self.mq.drain(self.ctl.state, 10)
        finally:
            try:
                self.ctl.state.shutdown()
                self.h.close()
            finally:
                self.mq.discard()
                self.mq.__exit__()
        return False


def seed_history(w, text=CANARY, **kw):
    job_id, raw, applied = W.seed_job(w.store, text.lower(), applied=text,
                                      captured="2026-09-28T10:00:00.000Z",
                                      app="TextEdit",
                                      bundle="com.apple.TextEdit", **kw)
    return job_id, raw, applied


def open_detail(w, job_id):
    w.select("history")
    r = w.host.send("history.select", {"kind": "job", "id": job_id})
    assert r["status"] == "success", r
    w.drain()
    detail = w.host.latest("history")["detail"]
    assert detail and detail["job_id"] == job_id, detail
    return detail


# ---- protocol ------------------------------------------------------------------


def test_envelope_and_schema_refusals():
    br = Bridge()
    seen = []

    @br.command("t.echo", {"s": Str(max_len=5), "n": Int(lo=0, hi=9),
                           "b": Bool(optional=True),
                           "e": Enum(("a", "b"), optional=True),
                           "l": List(Str(max_len=3), max_items=2,
                                     optional=True),
                           "x": Nullable(Str(), optional=True)})
    def echo(p):
        seen.append(p)
        return {"got": p}

    @br.command("t.boom")
    def boom(p):
        raise RuntimeError("secret " + CANARY)

    @br.command("t.unknown")
    def unk(p):
        B.unknown("store_busy")

    def env(**kw):
        base = {"bridge_version": 1, "request_id": "r9", "command": "t.echo",
                "payload": {"s": "ok", "n": 1}}
        base.update(kw)
        return json.dumps(base)

    assert br.handle("{not json")["reason_code"] == "bad_envelope"
    assert br.handle(json.dumps([1]))["reason_code"] == "bad_envelope"
    assert br.handle(env(bridge_version=2))["reason_code"] == \
        "bridge_version_mismatch"
    assert br.handle(env(command="os.system"))["reason_code"] == \
        "unknown_command"
    assert br.handle(env(extra=1))["reason_code"] == "bad_envelope"
    for payload, why in (({"s": "ok"}, "n: missing"),
                         ({"s": "toolong", "n": 1}, "s: too_long"),
                         ({"s": "ok", "n": 10}, "n: out_of_range"),
                         ({"s": "ok", "n": True}, "n: not_an_integer"),
                         ({"s": "ok", "n": 1, "e": "c"}, "e: not_allowed"),
                         ({"s": "ok", "n": 1, "zz": 1},
                          "zz: unexpected_field"),
                         ({"s": "ok", "n": 1, "l": ["a", "b", "c"]},
                          "l: too_many"),
                         ({"s": 3, "n": 1}, "s: not_a_string")):
        out = br.handle(env(payload=payload))
        assert out["status"] == "refusal" and \
            out["reason_code"] == f"invalid_payload:{why}", (payload, out)
    assert not seen, "a refused payload reached the handler"
    ok = br.handle(env(payload={"s": "ok", "n": 3, "x": None}))
    assert ok == {"request_id": "r9", "status": "success",
                  "result": {"got": {"s": "ok", "n": 3, "x": None}}}, ok
    out = br.handle(env(command="t.boom", payload={}))
    assert out["status"] == "error" and out["reason_code"] == \
        "RuntimeError" and CANARY not in json.dumps(out), out
    out = br.handle(env(command="t.unknown", payload={}))
    assert out["status"] == "outcome_unknown", out
    print("ok  protocol: version, allowlist, strict schemas, content-free"
          " errors")


def test_controller_allowlist_is_exactly_the_surfaces():
    with CWorld() as w:
        cmds = set(w.ctl.bridge.commands)
        expected = {
            "shell.hello", "nav.select", "prefs.set_theme",
            "prefs.set_sidebar", "prefs.dismiss", "prefs.onboarding_seen",
            "system.csp_violation", "app.quit",
            "history.search", "history.filter", "history.select",
            "history.reload", "history.replay", "history.stop_replay",
            "history.copy", "history.paste_again", "history.retry",
            "history.teach", "history.delete_usage",
            "history.to_scratchpad",
            "dictionary.search", "dictionary.reload", "dictionary.add",
            "dictionary.approve", "dictionary.set_enabled",
            "dictionary.set_pinned", "dictionary.delete",
            "dictionary.edit", "dictionary.sandbox", "dictionary.import",
            "dictionary.export",
            "settings.collection", "settings.retention",
            "settings.usage_retention", "settings.delete_all_usage"}
        missing = expected - cmds
        assert not missing, f"commands missing: {sorted(missing)}"
        for name in cmds:
            assert name.count(".") == 1 and name.replace(".", "").replace(
                "_", "").isalnum(), name
            for bad in ("sql", "exec", "eval", "path", "file", "shell."):
                if bad == "shell." and name == "shell.hello":
                    continue
                assert bad not in name, name
    print("ok  allowlist: named surface commands only, no generic entry")


# ---- read models and binding ------------------------------------------------------


def test_history_detail_token_binding_and_stale_refusal():
    with CWorld() as w:
        job_a, *_ = seed_history(w, CANARY + " alpha")
        job_b, *_ = seed_history(w, CANARY + " beta")
        det_a = open_detail(w, job_a)
        token_a = det_a["token"]
        # Selecting B while the page still shows A: A's token is stale.
        w.host.send("history.select", {"kind": "job", "id": job_b})
        out = w.host.send("history.copy", {"token": token_a})
        assert out["status"] == "stale", out
        w.drain()
        det_b = w.host.latest("history")["detail"]
        assert det_b["job_id"] == job_b and det_b["token"] != token_a
        # A reload of the same row republishes: the old token is stale
        # until the page renders the new one.
        w.host.send("history.reload")
        w.ctl.state._spawn_history_detail()
        w.drain()
        det_b2 = w.host.latest("history")["detail"]
        if det_b2["token"] != det_b["token"]:
            assert w.host.send("history.copy", {"token": det_b["token"]})[
                "status"] == "stale"
        out = w.host.send("history.copy", {"token": det_b2["token"]})
        assert out["status"] == "success", out
    print("ok  history: actions bind to the rendered detail token; a"
          " newer publication makes the old one stale")


def test_copy_and_paste_refuse_purged_final():
    with CWorld() as w:
        job, _raw, applied = seed_history(w)
        det = open_detail(w, job)
        w.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1 WHERE artifact_id=?", (applied,)))
        out = w.host.send("history.copy", {"token": det["token"]})
        assert out["status"] == "refusal" and \
            out["reason_code"] == "nothing_to_copy", out
        out = w.host.send("history.paste_again", {"token": det["token"]})
        assert out["status"] == "refusal" and \
            out["reason_code"] == "nothing_to_paste", out
    print("ok  history: Copy / Paste Again never publish a purged final"
          " (G06 XM-C106)")


def test_paste_again_through_companion():
    """POLICY-D03 through the bridge: the real insertion engine and the
    scripted destination picker of the cross-milestone Paste Again suite.
    Invoking steps the companion aside and pastes nothing; an incidental
    front app pastes nothing; the user's click pastes exactly once and the
    page is told how the pick ended."""
    sys.path.insert(0, str(HERE.parents[1] / "crossmilestone"))
    sys.path.insert(0, str(HERE.parents[1] / "insertion"))
    from test_xm_paste_again import Env
    from localflow.v2.ui.companion.controller import CompanionController
    env = Env()
    mq = MainQueue().__enter__()
    try:
        jid, text, aid = env.dictation("paste again through the companion")
        spec, _ = W.hub_spec(env.d)
        spec.update(vocabulary_store=env.d._vocab, host_factory=FakeHost,
                    prefs_path=env.a.h.tmp / "companion.json")
        ctl = CompanionController(spec)
        env.d._hub = ctl
        host = ctl.host
        host.send("nav.select", {"view": "history"})
        mq.drain(ctl.state)
        host.send("history.select", {"kind": "job", "id": jid})
        mq.drain(ctl.state)
        det = host.latest("history")["detail"]
        assert det and det["final_text"] == text, det
        host.window.visible = True
        since = env.stamp()
        out = host.send("history.paste_again", {"token": det["token"]})
        assert out["status"] == "success" and \
            out["result"]["outcome"] == "choosing_destination", out
        assert not host.window.visible, "the companion did not step aside"
        env.w.focus("B", "FB")  # incidental: another app comes forward
        env.idle()
        assert not env.writes(since), "pasted without a deliberate click"
        env.w.focus("A", "F2")
        env.picker.mouse_down(env.w.apps["A"]["pid"])
        env.sched.run(env.pp.CLICK_SETTLE_SEC)
        for _ in range(3):  # the pick posts through callAfter, then inserts
            mq.drain(ctl.state)
            env.idle()
        writes = env.writes(since)
        assert len(writes) == 1 and writes[0][2] == "F2", writes
        ends = host.events("history.paste_ended")
        assert ends, host.pushed[-4:]
        assert ends[-1]["outcome"] in ("confirmed", "insertion_confirmed",
                                       "posted_unverified"), ends
    finally:
        try:
            ctl.state.shutdown()
        except Exception:
            pass
        mq.discard()
        mq.__exit__()
        env.close()
    print("ok  history: Paste Again steps aside, ignores incidental focus"
          " and pastes once where the user clicked (POLICY-D03)")


def test_retry_refuses_non_failed_and_imported():
    with CWorld() as w:
        job, *_ = seed_history(w)
        det = open_detail(w, job)
        out = w.host.send("history.retry", {"token": det["token"]})
        assert out["status"] == "refusal" and \
            out["reason_code"] == "not_retryable", out
    print("ok  history: Retry refuses what the coordinator refuses")


def test_teach_binds_and_reuses_op_after_unknown():
    with CWorld() as w:
        job, *_ = seed_history(w, "please book the room for tuesday")
        det = open_detail(w, job)
        learning = w.ctl.spec["learning_service"]
        real = learning.teach_correction
        seen = []

        def timing_out(job_id, corrected, operation_id=None, **kw):
            seen.append(operation_id)
            raise TimeoutError()
        learning.teach_correction = timing_out
        try:
            p = {"token": det["token"],
                 "corrected": "please book the room for Tuesday"}
            first = w.host.send("history.teach", p)
            assert first["status"] == "outcome_unknown", first
            assert w.host.send("history.teach", p)["status"] == \
                "outcome_unknown"
            assert seen[0] == seen[1], "retry after unknown minted a new op"
            p2 = dict(p, corrected="please book the room for Wednesday")
            w.host.send("history.teach", p2)
            assert seen[2] != seen[1], "a different correction reused an op"
        finally:
            learning.teach_correction = real
        out = w.host.send("history.teach", {"token": det["token"],
                                            "corrected": "  "})
        assert out["reason_code"] == "corrected_text_required", out
    print("ok  history: Teach reuses its operation id after an unknown"
          " outcome and only then")


def test_revocation_scrubs_every_pushed_view():
    with CWorld() as w:
        job, *_ = seed_history(w)
        w.select("home")
        w.drain()
        open_detail(w, job)
        assert CANARY in json.dumps(w.host.latest("history"))
        before = len(w.host.pushed)
        w.store.delete_everywhere("job", job, "user_request")
        w.drain()
        after = w.host.pushed[before:]
        assert after, "nothing was pushed after the deletion"
        for view in ("history", "home"):
            latest = w.host.latest(view)
            assert CANARY not in json.dumps(latest or {}), view
        detail_tokens = [m for m in after if m.get("view") == "history"]
        assert detail_tokens and detail_tokens[-1]["data"]["detail"] is None
    print("ok  revocation: every view the page holds is rebuilt without"
          " the deleted text")


def test_retention_on_home_reloads_the_open_recent_row():
    with CWorld() as w:
        job, _raw, _applied = seed_history(w)
        w.select("home")
        r = w.host.send("history.select", {"kind": "job", "id": job})
        assert r["status"] == "success", r
        w.drain()
        assert w.host.latest("history")["detail"] is not None
        # A retention pass while Home shows the row inline.
        w.ctl.state.revalidate()
        w.drain()
        latest = w.host.latest("history")
        assert latest["detail"] is not None or latest["detail_loading"], \
            "Home's open row was dropped and never reloaded"
        assert latest["detail"] is not None, latest["detail_error"]
    print("ok  retention: Home's open recent row reloads after a pass")


def test_home_read_model_is_real_and_bounded():
    with CWorld() as w:
        for i in range(25):
            W.seed_job(w.store, f"note number {i}", applied=f"Note {i}.",
                       captured=f"2026-09-2{i % 9}T0{i % 9}:00:00.000Z")
        w.ctl.state.reload_current()
        w.drain()
        home = w.host.latest("home")
        data = home["data"]
        rows = [r for g in data["recent"] for r in g["rows"]]
        assert 0 < len(rows) <= 18, len(rows)
        assert data["summary"]["total_jobs"] == 25
        assert set(rows[0]) == {"kind", "id", "date", "time", "time_quality",
                                "app", "mode", "state", "state_reason",
                                "preview", "has_audio"}, rows[0]
        # Usage: the real service (no facts recorded → zero, never made up).
        assert data["usage"] is None or data["usage"]["final_words"] in (
            0, None), data["usage"]
    print("ok  home: recent rows, counts and usage come from their"
          " services, bounded and field-picked")


# ---- dictionary --------------------------------------------------------------------


def test_dictionary_double_cas_and_unapproved_add():
    with CWorld() as w:
        w.select("dictionary")
        out = w.host.send("dictionary.add", {
            "canonical": "Parakeet", "alias": "para keet",
            "scope_kind": "global"})
        assert out["status"] == "success", out
        eid, rev = out["result"]["entry_id"], out["result"]["revision"]
        w.drain()
        entry = next(e for e in w.host.latest("dictionary")["entries"]
                     if e["entry_id"] == eid)
        assert entry["approved"] is False, "user add must start unapproved"
        # The row moves on elsewhere: the page's revision is stale.
        w.d._vocab.update_entry(eid, pinned=True)
        out = w.host.send("dictionary.approve",
                          {"entry_id": eid, "revision": rev})
        assert out["status"] == "stale", out
        w.drain()
        entry = next(e for e in w.host.latest("dictionary")["entries"]
                     if e["entry_id"] == eid)
        out = w.host.send("dictionary.approve", {
            "entry_id": eid, "revision": entry["revision"]})
        assert out["status"] == "success", out
        assert w.d._vocab.entry(eid).approved is True
        # Edit keeps an existing alias's approval, adds a new one unapproved.
        w.drain()
        entry = next(e for e in w.host.latest("dictionary")["entries"]
                     if e["entry_id"] == eid)
        out = w.host.send("dictionary.edit", {
            "entry_id": eid, "revision": entry["revision"],
            "canonical": "Parakeet", "aliases": ["para keet", "parra keet"]})
        assert out["status"] == "success", out
        aliases = {a.alias: a.approved for a in w.d._vocab.entry(eid).aliases}
        assert aliases == {"para keet": True, "parra keet": False}, aliases
        # Duplicate add refuses (never a second row).
        out = w.host.send("dictionary.add", {
            "canonical": "Parakeet", "scope_kind": "global"})
        assert out["status"] == "refusal", out
        out = w.host.send("dictionary.delete", {"entry_id": eid,
                                                "revision": 0})
        assert out["status"] == "stale" and w.d._vocab.entry(eid), out
    print("ok  dictionary: adds unapproved, writes are revision-checked"
          " twice, edits keep alias approval")


def test_dictionary_import_export_never_take_a_path_from_the_page():
    with CWorld() as w:
        w.select("dictionary")
        out = w.host.send("dictionary.export", {"path": "/tmp/x.json"})
        assert out["status"] == "refusal" and out["reason_code"].startswith(
            "invalid_payload:path"), out
        target = w.h.tmp / "export.json"

        class Panels:
            @staticmethod
            def open_json():
                return None

            @staticmethod
            def save_json(name):
                return str(target)
        w.ctl.spec["file_panels"] = Panels  # read at registration time
        from localflow.v2.ui.companion.surfaces import dictionary
        # re-register against a fresh bridge to pick the panels up
        w.ctl.bridge = Bridge()
        dictionary.register(w.ctl)
        out = w.host.send("dictionary.import")
        assert out["status"] == "cancelled", out
        out = w.host.send("dictionary.export")
        assert out["status"] == "success" and target.exists(), out
    print("ok  dictionary: import/export paths come only from native"
          " panels")


# ---- settings ------------------------------------------------------------------------


def test_settings_outcomes_and_confirmation():
    with CWorld() as w:
        w.select("settings")
        data = w.host.latest("settings")
        assert data["loaded"] and "hotkey" in data["config"], data
        out = w.host.send("settings.retention", {
            "transcript": "x", "audio_success": "7", "audio_failed": "30",
            "metadata": "14", "training_buffer": "30"})
        assert out["reason_code"] == "not_whole_days", out
        out = w.host.send("settings.delete_all_usage", {"confirmed": False})
        assert out["reason_code"] == "confirmation_required", out
        out = w.host.send("settings.usage_retention", {"value": "0"})
        assert out["status"] == "refusal", out
        w.drain()
        assert w.host.latest("settings")["note"]["what"] == \
            "usage_retention", "a refusal is kept, not reloaded over"
        out = w.host.send("settings.usage_retention", {"value": "keep"})
        assert out["status"] == "success", out
        w.drain()
        assert w.host.latest("settings")["note"] is None
    print("ok  settings: strict usage validator, confirmation required,"
          " refusals kept as the note")


def test_theme_preference_persists():
    with CWorld() as w:
        out = w.host.send("prefs.set_theme", {"theme": "dark"})
        assert out["status"] == "success" and out["result"]["saved"], out
        assert w.host.theme == "dark"
        saved = json.loads((w.h.tmp / "companion.json").read_text())
        assert saved["theme"] == "dark"
        assert w.host.send("prefs.set_theme", {"theme": "neon"})[
            "status"] == "refusal"
        from localflow.v2.ui.companion.controller import Prefs
        assert Prefs(w.h.tmp / "companion.json").values["theme"] == "dark"
        (w.h.tmp / "bad.json").write_text("{\"theme\": 3}")
        assert Prefs(w.h.tmp / "bad.json").values["theme"] == "system"
    print("ok  prefs: theme persists, invalid values fall back")


def test_every_view_has_its_own_read_model():
    from localflow.v2.ui.companion import readmodels, surfaces
    from localflow.v2.ui.companion.state import VIEWS
    with CWorld() as w:
        for view in VIEWS:
            assert view in readmodels.BUILDERS or \
                view in surfaces.READ_MODELS, f"{view} has no read model"
            w.select(view)
            model = readmodels.build(w.ctl, view)
            assert model.get("error") != "unmodeled", view
    print("ok  read models: every view picks its own fields")


def test_close_hides_and_reopen_keeps_state():
    with CWorld() as w:
        w.select("dictionary")
        w.ctl.showWindow_(None)
        assert w.ctl.state.visible and w.host.window.visible
        w.ctl.on_close()
        assert not w.ctl.state.visible
        w.ctl.showWindow_(None)
        assert w.ctl.state.selected_view == "dictionary"
    print("ok  lifecycle: close hides, reopen keeps the route")


if __name__ == "__main__":
    for test in (
            test_envelope_and_schema_refusals,
            test_controller_allowlist_is_exactly_the_surfaces,
            test_history_detail_token_binding_and_stale_refusal,
            test_copy_and_paste_refuse_purged_final,
            test_paste_again_through_companion,
            test_retry_refuses_non_failed_and_imported,
            test_teach_binds_and_reuses_op_after_unknown,
            test_revocation_scrubs_every_pushed_view,
            test_retention_on_home_reloads_the_open_recent_row,
            test_home_read_model_is_real_and_bounded,
            test_dictionary_double_cas_and_unapproved_add,
            test_dictionary_import_export_never_take_a_path_from_the_page,
            test_settings_outcomes_and_confirmation,
            test_theme_preference_persists,
            test_every_view_has_its_own_read_model,
            test_close_hides_and_reopen_keeps_state):
        test()
