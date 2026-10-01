"""A window title that drifted while the dictation was processed (a
browser retitling the page behind a side-panel field) must not refuse the
insertion when the live focused element is the very element captured at
the start; a different field still routes to saved history.

Run: .venv/bin/python tests/v2/insertion/test_title_drift.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fixture_target import FixtureTargetApp  # noqa: E402

from localflow.v2.context.providers import categorize  # noqa: E402
from localflow.v2.context.snapshot import (ContextSnapshot,  # noqa: E402
                                           FieldContext, TargetSnapshot)
from localflow.v2.insertion.validation import validate_target  # noqa: E402

RECORDED_TITLE = "Untitled.txt"
DRIFTED_TITLE = "A page the extension navigated to"


def snapshot(target, *, field_element=None, replace=False):
    t = TargetSnapshot(
        target_snapshot_id="tsnap-drift", app_bundle=target.bundle,
        app_name="Fixture", app_pid=target.pid, denied=False,
        category=categorize(target.bundle),
        captured_at_utc="2026-10-01T00:00:00.000Z")
    field = FieldContext(
        role=target.role, subrole=None, classification="text",
        selected_text="abc" if replace else None,
        selected_range=(0, 3) if replace else (0, 0),
        selected_range_utf16=(0, 3) if replace else None,
        preceding_text="" if replace else None,
        following_text="" if replace else None)
    return ContextSnapshot(
        context_snapshot_id="csnap-drift", stage="pre_decode", target=t,
        field=field, window_title=RECORDED_TITLE,
        window_element=target.attribute(target, "AXWindow"),
        field_element=field_element)


def test_title_drift_with_same_focused_element_is_not_a_change():
    target = FixtureTargetApp(window_title=DRIFTED_TITLE)
    lease, verification = validate_target(
        target, snapshot(target, field_element=target), {"job_id": "j"})
    assert lease is not None, verification
    assert verification["window"] == "pass"
    assert verification["window_title"] == "pass_same_field"


def test_title_drift_with_a_different_focused_element_is_a_change():
    target = FixtureTargetApp(window_title=DRIFTED_TITLE)
    lease, verification = validate_target(
        target, snapshot(target, field_element=object()), {"job_id": "j"})
    assert lease is None
    assert verification["window_title"] == "fail"


def test_title_drift_without_a_recorded_element_is_a_change():
    target = FixtureTargetApp(window_title=DRIFTED_TITLE)
    lease, verification = validate_target(
        target, snapshot(target), {"job_id": "j"})
    assert lease is None
    assert verification["window_title"] == "fail"


def test_equal_title_still_passes_exactly():
    target = FixtureTargetApp(window_title=RECORDED_TITLE)
    lease, verification = validate_target(
        target, snapshot(target, field_element=target), {"job_id": "j"})
    assert lease is not None, verification
    assert verification["window_title"] == "pass"


def _strict(title):
    target = FixtureTargetApp(window_title=title)
    target.content = "abc"
    target.selection = (0, 3)
    return validate_target(
        target, snapshot(target, field_element=target, replace=True),
        {"job_id": "j", "strict_replacement": True})


def test_strict_replacement_still_requires_an_exact_title():
    lease, verification = _strict(RECORDED_TITLE)
    assert lease is not None and verification["strict"] == "pass", \
        verification
    lease, verification = _strict(DRIFTED_TITLE)
    assert lease is None, verification
    assert verification["window_title"] == "pass_same_field"
    assert verification["strict"] == "fail"


def main():
    test_title_drift_with_same_focused_element_is_not_a_change()
    test_strict_replacement_still_requires_an_exact_title()
    test_title_drift_with_a_different_focused_element_is_a_change()
    test_title_drift_without_a_recorded_element_is_a_change()
    test_equal_title_still_passes_exactly()
    print("all title drift tests passed")


if __name__ == "__main__":
    raise SystemExit(main())
