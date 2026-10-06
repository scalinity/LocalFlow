"""Training submenu: what the menu shows follows the saved consent state.

Builds the real Training NSMenu headless (no status item) and checks it the
way the menu bar would draw it:

- the check mark on Collect Training Evidence reflects the stored state the
  moment the menu is built, not only after the first click;
- Pause Collection is greyed out while collection is off, because there is
  nothing to pause (macOS re-validates items when the menu opens, so the
  menu must not auto-enable them).

Run from this directory: ../../../.venv/bin/python test_training_menu.py
"""

import sys

from test_lifecycle import Harness

COLLECT = "toggleTrainingCollection"
PAUSE = "toggleTrainingPause"
CHECK = "✓"


def _menu(state):
    """A Harness with `state` saved before the menu is built, and the menu."""
    h = Harness(durations=[1.0])
    if state != "disabled":
        h.d.consent.set(state, note="test")
    menu = h.d._build_training_menu()
    return h, menu


def _shown(h, menu):
    """(collect title, pause title, pause enabled) as the menu holds them.

    While a menu auto-enables its items, AppKit re-validates them each time
    it opens and discards any manual setEnabled_ (every item whose target
    answers its action comes back live). Headless there is no active app to
    validate against, so update() cannot be used to observe that; the
    contract is asserted directly: auto-enable is off, so the flag we set
    is the flag the menu bar draws."""
    assert not menu.autoenablesItems(), (
        "the menu re-enables Pause Collection whenever it opens")
    collect = h.d._training_items[COLLECT]
    pause = h.d._training_items[PAUSE]
    return str(collect.title()), str(pause.title()), bool(pause.isEnabled())


def test_off_at_build_shows_no_check_and_pause_greyed():
    h, menu = _menu("disabled")
    try:
        collect, pause, pause_on = _shown(h, menu)
        assert CHECK not in collect, collect
        assert not pause_on, "Pause Collection is live while collection is off"
        assert CHECK not in pause, pause
    finally:
        h.close()
    print("ok  collection off: no check mark, Pause Collection greyed out")


def test_on_at_build_shows_check_and_pause_live():
    h, menu = _menu("enabled")
    try:
        collect, pause, pause_on = _shown(h, menu)
        assert CHECK in collect, f"saved 'enabled' drew no check: {collect!r}"
        assert pause_on, "Pause Collection is greyed while collection is on"
        assert CHECK not in pause, pause
    finally:
        h.close()
    print("ok  collection on (saved before launch): check mark, Pause live")


def test_paused_at_build_marks_pause_and_keeps_it_live():
    h, menu = _menu("paused")
    try:
        collect, pause, pause_on = _shown(h, menu)
        assert CHECK not in collect, collect
        assert CHECK in pause, f"saved 'paused' drew no check: {pause!r}"
        assert pause_on, "a paused collection could not be resumed"
    finally:
        h.close()
    print("ok  collection paused: Pause marked, still live to resume")


def test_clicking_collect_turns_it_on_then_off_and_menu_follows():
    h, menu = _menu("disabled")
    try:
        h.d.toggleTrainingCollection_(None)
        collect, pause, pause_on = _shown(h, menu)
        assert h.d.consent.state() == "enabled"
        assert CHECK in collect and pause_on, (collect, pause_on)
        h.d.toggleTrainingCollection_(None)
        collect, pause, pause_on = _shown(h, menu)
        assert h.d.consent.state() == "disabled"
        assert CHECK not in collect and not pause_on, (collect, pause_on)
    finally:
        h.close()
    print("ok  click turns collection on, again turns it off; menu follows")


def test_fresh_store_starts_with_collection_on():
    h = Harness(durations=[1.0])
    try:
        assert h.d.consent.revision_id() is None, "fixture: store not fresh"
        h.d._seed_default_collection()
        assert h.d.consent.state() == "enabled", h.d.consent.state()
        rev = h.d.consent.revision_id()
        h.d._seed_default_collection()
        assert h.d.consent.revision_id() == rev, "seeding again wrote a row"
    finally:
        h.close()
    print("ok  fresh store: collection starts on, seeded exactly once")


def test_a_saved_choice_is_never_overridden_by_the_default():
    for saved in ("disabled", "paused"):
        h = Harness(durations=[1.0])
        try:
            h.d.consent.set(saved, note="test")
            h.d._seed_default_collection()
            assert h.d.consent.state() == saved, (
                f"the default overrode a saved {saved!r}")
        finally:
            h.close()
    print("ok  saved off / paused survive the default (no re-override)")


def main():
    test_fresh_store_starts_with_collection_on()
    test_a_saved_choice_is_never_overridden_by_the_default()
    test_off_at_build_shows_no_check_and_pause_greyed()
    test_on_at_build_shows_check_and_pause_live()
    test_paused_at_build_marks_pause_and_keeps_it_live()
    test_clicking_collect_turns_it_on_then_off_and_menu_follows()
    print("all training menu tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
