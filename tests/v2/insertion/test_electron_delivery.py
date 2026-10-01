"""Electron apps (Claude desktop, Slack, VS Code ...) are web-content
fields like Chromium browsers: they advertise AXSelectedText as settable
and acknowledge a write without applying it. They are recognised by the
Electron framework in their bundle, not by a hand-kept bundle-id list.

Run: .venv/bin/python tests/v2/insertion/test_electron_delivery.py
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_codex_delivery import CodexTarget  # noqa: E402
from test_insertion_races import Env, snapshot  # noqa: E402
from localflow.v2.insertion.hosts import (  # noqa: E402
    bundle_has_electron_framework)
from localflow.v2.insertion.result import METHOD_CLIPBOARD  # noqa: E402


class ElectronTarget(CodexTarget):
    def __init__(self, electron=True):
        super().__init__("com.example.electronapp")
        self.electron = electron

    def is_electron_app(self, bundle):
        return self.electron and bundle == self.bundle


def test_bundle_check_reads_the_framework_directory():
    with tempfile.TemporaryDirectory() as tmp:
        app = pathlib.Path(tmp) / "Some.app"
        frameworks = app / "Contents" / "Frameworks"
        frameworks.mkdir(parents=True)
        assert bundle_has_electron_framework(str(app)) is False
        (frameworks / "Electron Framework.framework").mkdir()
        assert bundle_has_electron_framework(str(app)) is True
    assert bundle_has_electron_framework("/nonexistent/Nope.app") is False
    assert bundle_has_electron_framework(None) is False


def test_electron_app_gets_its_caret_text_by_paste():
    env = Env(ElectronTarget(), settle=.05)
    try:
        target = env.target
        result = env.run("Synthetic dictation", {
            "job_id": "electron-caret", "attempt": 1,
            "context_snapshot": snapshot(target)})
        assert result.method == METHOD_CLIPBOARD, result.method
        assert target.content == "Synthetic dictation"
        assert target.ax_writes == 0
    finally:
        env.close()


def test_non_electron_app_keeps_ax():
    env = Env(ElectronTarget(electron=False), settle=.05)
    try:
        result = env.run("Synthetic dictation", {
            "job_id": "plain-caret", "attempt": 1,
            "context_snapshot": snapshot(env.target)})
        assert result.method == "ax_replacement", result.method
        assert env.target.ax_writes == 1
    finally:
        env.close()


if __name__ == "__main__":
    tests = (test_bundle_check_reads_the_framework_directory,
             test_electron_app_gets_its_caret_text_by_paste,
             test_non_electron_app_keeps_ax)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} electron delivery tests passed")
