#!/usr/bin/env python
"""Render the pill view offscreen to a PNG for visual verification."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from AppKit import NSApplication, NSBitmapImageFileTypePNG  # noqa: E402
from Foundation import NSMakeRect  # noqa: E402

from localflow.overlay import PILL_H, PILL_W, MODE_PROCESSING, PillView  # noqa: E402


def render(path, mode, level, ticks=24):
    view = PillView.alloc().initWithFrame_(NSMakeRect(0, 0, PILL_W, PILL_H))
    view.setMode_(mode)
    view.setLevel_(level)
    for _ in range(ticks):
        view.tick()
    rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    data.writeToFile_atomically_(path, True)
    print(f"wrote {path}")


if __name__ == "__main__":
    NSApplication.sharedApplication()
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pill.png"
    base = pathlib.Path(out)
    render(str(base.with_name("pill_speech.png")), "recording", 0.85)
    render(str(base.with_name("pill_quiet.png")), "recording", 0.15)
    render(str(base.with_name("pill_processing.png")), MODE_PROCESSING, 0.0)
