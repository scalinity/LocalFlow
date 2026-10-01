"""A readback that does not attribute the paste records content-free
numbers and booleans saying why: where the text sat and by how much the
field grew beyond the expected length. Never any text.

Run: .venv/bin/python tests/v2/insertion/test_readback_detail.py
"""

import json

from test_insertion_races import Env, insertion_row, snapshot
from fixture_target import FixtureTargetApp

TEXT = "Synthetic dictation"


class TrailingNewlineTarget(FixtureTargetApp):
    """Lands the paste at the caret but the field keeps one extra
    character (a composer normalising the paste)."""

    def replace_selection(self, text):
        super().replace_selection(text + "\n")


class TailTarget(FixtureTargetApp):
    """Lands the paste at the end of the field, not at the recorded
    caret (a terminal prompt)."""

    def replace_selection(self, text):
        self.selection = (len(self.content), len(self.content))
        super().replace_selection(text)


def _run(target):
    env = Env(target, settle=.05)
    try:
        target.settable = False         # clipboard path
        target.content = "existing text here"
        target.selection = (0, 0)
        result = env.run(TEXT, {
            "job_id": "detail", "attempt": 1,
            "context_snapshot": snapshot(target)})
        row = insertion_row(env, result)
        return result, json.loads(row[3])
    finally:
        env.close()


def test_extra_growth_is_recorded():
    result, verification = _run(TrailingNewlineTarget())
    assert result.reason_code == "readback_mismatch", result.reason_code
    detail = verification["readback_detail"]
    assert detail["region_matches"] is True, detail
    assert detail["extra_units"] == 1, detail
    assert TEXT not in json.dumps(verification)


def test_tail_landing_is_recorded():
    result, verification = _run(TailTarget())
    detail = verification["readback_detail"]
    assert detail["region_matches"] is False, detail
    assert detail["found_at_tail"] is True, detail
    assert detail["found_near_start"] is False, detail
    assert TEXT not in json.dumps(verification)


def test_exact_match_records_no_detail():
    result, verification = _run(FixtureTargetApp())
    assert result.state == "confirmed", (result.state, result.reason_code)
    assert "readback_detail" not in verification


if __name__ == "__main__":
    tests = (test_extra_growth_is_recorded, test_tail_landing_is_recorded,
             test_exact_match_records_no_detail)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} readback detail tests passed")
