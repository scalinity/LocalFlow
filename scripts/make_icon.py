#!/usr/bin/env python
"""Render the LocalFlow app icon (1024x1024 PNG): black squircle, white waveform."""

import sys

from AppKit import (
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSGraphicsContext,
)
from Foundation import NSMakeRect

SIZE = 1024
# macOS icon grid: content squircle inset in a transparent canvas
BOX = 824.0
RADIUS = 184.0

BAR_W = 28.0
BAR_GAP = 24.5
BAR_MIN = 40.0
BAR_MAX = 200.0
# Symmetric, speech-like arrangement (matches the dictation pill's look)
FRACTIONS = [0.30, 0.55, 0.40, 0.72, 0.52, 0.88, 1.0, 0.88, 0.52, 0.72, 0.40, 0.55, 0.30]


def main(out_path):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, SIZE, SIZE, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    inset = (SIZE - BOX) / 2.0
    squircle = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(inset, inset, BOX, BOX), RADIUS, RADIUS
    )
    NSColor.colorWithCalibratedWhite_alpha_(0.05, 1.0).setFill()
    squircle.fill()

    n = len(FRACTIONS)
    total = n * BAR_W + (n - 1) * BAR_GAP
    x = (SIZE - total) / 2.0
    cy = SIZE / 2.0
    NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.95).setFill()
    for f in FRACTIONS:
        h = max(BAR_MIN, f * BAR_MAX)
        r = NSMakeRect(x, cy - h / 2.0, BAR_W, h)
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            r, BAR_W / 2.0, BAR_W / 2.0
        ).fill()
        x += BAR_W + BAR_GAP

    ctx.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()

    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    data.writeToFile_atomically_(out_path, True)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/localflow_icon.png")
