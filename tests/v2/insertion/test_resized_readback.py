"""A paste that demonstrably landed (the owned region now equals the text
and changed) but left the field a different length than expected — a
composer clearing its placeholder — is consumed: the user's clipboard is
restored, and it is never confirmed.

Run: .venv/bin/python tests/v2/insertion/test_resized_readback.py
"""

from test_insertion_races import Env, snapshot
from fixture_target import FixtureTargetApp
from localflow.v2.insertion.result import METHOD_CLIPBOARD

TEXT = "Synthetic dictation "


class PlaceholderTarget(FixtureTargetApp):
    """An empty composer whose AX value is its placeholder; the first
    paste replaces the whole value."""

    PLACEHOLDER = "Ask anything.."

    def __init__(self):
        super().__init__(bundle="com.example.composer", settable=False)
        self.content = self.PLACEHOLDER
        self.selection = (0, 0)

    def replace_selection(self, text):
        self.content = text
        self.selection = (len(text), len(text))


def test_cleared_placeholder_is_consumed_not_confirmed():
    env = Env(PlaceholderTarget(), settle=.05)
    try:
        target = env.target
        target.pb.user_copy("original clipboard")
        result = env.run(TEXT, {
            "job_id": "resized", "attempt": 1,
            "context_snapshot": snapshot(target)})
        assert result.method == METHOD_CLIPBOARD, result.method
        assert target.content == TEXT
        assert result.state == "posted_unverified", result.state
        assert result.reason_code == "readback_resized", result.reason_code
        assert target.pb.current_string() == "original clipboard"
        assert result.clipboard.get("restore_skipped_reason") is None
    finally:
        env.close()


def test_changed_region_that_is_not_the_text_stays_mismatch():
    class Garbling(PlaceholderTarget):
        def replace_selection(self, text):
            self.content = "x" * (len(text) - 1)

    env = Env(Garbling(), settle=.05)
    try:
        target = env.target
        target.pb.user_copy("original clipboard")
        result = env.run(TEXT, {
            "job_id": "garbled", "attempt": 1,
            "context_snapshot": snapshot(target)})
        assert result.reason_code == "readback_mismatch", result.reason_code
        assert target.pb.current_string() != "original clipboard"
    finally:
        env.close()


if __name__ == "__main__":
    tests = (test_cleared_placeholder_is_consumed_not_confirmed,
             test_changed_region_that_is_not_the_text_stays_mismatch)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} resized readback tests passed")
