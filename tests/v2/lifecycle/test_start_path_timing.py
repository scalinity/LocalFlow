"""The key-press path records how long it takes, content-free, so a lag
between pressing the hotkey and the pill animating can be measured:
milliseconds from the press to the overlay, and from the overlay to the
return of startDictation (the main-thread tail that keeps the pill's
timer from running).

Run: .venv/bin/python tests/v2/lifecycle/test_start_path_timing.py
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import App, run, tmpdir  # noqa: E402


def test_start_path_timing_is_recorded():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            events = []
            real = a.d.v2log.emit

            def spy(event, *args, **kw):
                events.append((event, kw))
                return real(event, *args, **kw)

            a.d.v2log.emit = spy
            a.dictate(blocks=2)
            timing = [kw for e, kw in events if e == "capture.start_path"]
            assert len(timing) == 1, [e for e, _ in events]
            detail = timing[0].get("detail") or ""
            m = re.fullmatch(
                r"to_overlay_ms=(\d+\.\d) overlay_to_return_ms=(\d+\.\d)",
                detail)
            assert m, detail
            assert timing[0].get("duration_ms") >= float(m.group(1))
            assert timing[0].get("job_id")
        finally:
            a.close()
    print("ok  start path timing is recorded")


if __name__ == "__main__":
    run([test_start_path_timing_is_recorded], "start path timing tests")
