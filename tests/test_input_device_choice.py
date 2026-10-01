"""input_device may be an ordered list of preferences: the first one that
is connected wins, and the system default is the last resort. A headset
that is the system default (AirPods) is only used when nothing listed is
present — its microphone starts late and records leading silence.

Run: .venv/bin/python tests/test_input_device_choice.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import localflow.audio as audio_mod  # noqa: E402

BUILTIN = {"name": "MacBook Pro Microphone", "max_input_channels": 1}
SPEAKERS = {"name": "MacBook Pro Speakers", "max_input_channels": 0}
AIRPODS = {"name": "Daniel's AirPods Max", "max_input_channels": 1}
DJI = {"name": "DJI MIC MINI", "max_input_channels": 2}
PREFER = ["DJI Mic", "MacBook Pro Microphone"]


def resolve(choice, devices):
    real = audio_mod.sd.query_devices
    audio_mod.sd.query_devices = lambda *a, **k: devices
    notes = []
    try:
        rec = audio_mod.Recorder(input_device=choice, notifier=notes.append)
        return rec._resolve_device(), notes
    finally:
        audio_mod.sd.query_devices = real


def test_dji_wins_when_connected():
    got, _ = resolve(PREFER, [AIRPODS, BUILTIN, SPEAKERS, DJI])
    assert got == 3


def test_builtin_beats_airpods_default_when_no_dji():
    got, notes = resolve(PREFER, [AIRPODS, BUILTIN, SPEAKERS])
    assert got == 1 and notes == []


def test_nothing_listed_connected_uses_default_and_says_so():
    got, notes = resolve(PREFER, [AIRPODS, SPEAKERS])
    assert got is None
    assert len(notes) == 1 and "not found" in notes[0], notes


def test_single_name_and_none_keep_working():
    assert resolve("MacBook Pro Microphone", [AIRPODS, BUILTIN])[0] == 1
    assert resolve(None, [AIRPODS, BUILTIN]) == (None, [])
    assert resolve(2, [AIRPODS, BUILTIN, DJI])[0] == 2


def test_output_only_device_is_never_chosen():
    got, _ = resolve(["MacBook Pro Speakers"], [SPEAKERS, AIRPODS])
    assert got is None


if __name__ == "__main__":
    tests = (test_dji_wins_when_connected,
             test_builtin_beats_airpods_default_when_no_dji,
             test_nothing_listed_connected_uses_default_and_says_so,
             test_single_name_and_none_keep_working,
             test_output_only_device_is_never_chosen)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} input device choice tests passed")
