"""Codex caret delivery: a successful AX setter can leave text unchanged.

The real insertion service runs with an in-process target and private fake
pasteboard. No desktop focus, system clipboard or keyboard events are used.
"""

from test_insertion_races import Env, snapshot
from fixture_target import FixtureTargetApp
from localflow.v2.insertion.result import METHOD_CLIPBOARD
from localflow.v2.insertion.selection import capture_selection


class CodexTarget(FixtureTargetApp):
    def __init__(self):
        super().__init__(bundle="com.openai.codex", settable=True)
        self.ax_writes = 0

    def set_attribute(self, el, name, value):
        if name == "AXSelectedText":
            self.ax_writes += 1
            return True  # Reports success without applying the edit.
        return super().set_attribute(el, name, value)


def test_caret_delivery():
    env = Env(CodexTarget(), settle=.05)
    try:
        target = env.target
        target.pb.user_copy("original clipboard")
        result = env.run("Synthetic dictation", {
            "job_id": "codex-caret", "attempt": 1,
            "context_snapshot": snapshot(target)})
        assert result.state == "confirmed", (result.state, result.reason_code)
        assert result.method == METHOD_CLIPBOARD, result.method
        assert target.content == "Synthetic dictation"
        assert target.ax_writes == 0, "Do not write AX and then attempt paste"
        assert len(target.paste_events) == 1
        assert target.pb.current_string() == "original clipboard"
    finally:
        env.close()


def test_other_app_keeps_ax():
    env = Env(FixtureTargetApp(), settle=.05)
    try:
        result = env.run("Synthetic dictation", {
            "job_id": "textedit-caret", "attempt": 1,
            "context_snapshot": snapshot(env.target)})
        assert result.state == "confirmed"
        assert result.method == "ax_replacement"
        assert env.target.paste_events == []
    finally:
        env.close()


def test_recorded_selection_keeps_ax():
    env = Env(CodexTarget(), settle=.05)
    try:
        target = env.target
        target.content = "original"
        target.selection = (0, 8)
        captured, reason = capture_selection(target, denied_apps=())
        assert captured is not None, reason
        result = env.run("replacement", {
            "job_id": "codex-selection", "attempt": 1,
            "strict_replacement": True,
            "context_snapshot": captured["snapshot"]})
        assert result.method == "ax_replacement"
        assert result.verification["strict"] == "pass"
        assert result.state == "posted_unverified"
        assert target.ax_writes == 1
        assert target.paste_events == [], "Never retry an uncertain AX write"
        assert target.content == "original"
    finally:
        env.close()


def test_dropped_paste_is_unverified():
    env = Env(CodexTarget(), settle=.05)
    try:
        env.target.paste_drops = True
        result = env.run("Synthetic dictation", {
            "job_id": "codex-dropped", "attempt": 1,
            "context_snapshot": snapshot(env.target)})
        assert result.method == METHOD_CLIPBOARD
        assert result.state == "posted_unverified"
        assert env.target.content == ""
        assert env.target.ax_writes == 0
        assert len(env.target.paste_events) == 1
    finally:
        env.close()


def test_focus_change_before_paste_refuses():
    env = Env(CodexTarget(), settle=.05)
    try:
        target = env.target
        target.pb.user_copy("original clipboard")

        def switch_app():
            target.frontmost_info = {"bundle": "com.other.app", "pid": 9999}

        result = env.run_with_hook("Synthetic dictation", {
            "job_id": "codex-switch", "attempt": 1,
            "context_snapshot": snapshot(target)}, switch_app)
        assert result.state == "target_changed"
        assert result.reason_code == "target_changed_before_effect"
        assert target.content == ""
        assert target.ax_writes == 0 and target.paste_events == []
        assert target.pb.current_string() == "original clipboard"
    finally:
        env.close()


if __name__ == "__main__":
    tests = (test_caret_delivery, test_other_app_keeps_ax,
             test_recorded_selection_keeps_ax, test_dropped_paste_is_unverified,
             test_focus_change_before_paste_refuses)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} Codex delivery tests passed")
