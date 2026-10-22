#!/usr/bin/env python
"""Render the LocalFlow app icon (1024x1024 PNG): the Hub's five-bar mark
(frontend/src/app/Brand.svelte) in its dark-mode ink on a squircle of its
dark-mode canvas."""

import sys

from AppKit import (
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSGradient,
    NSGraphicsContext,
    NSShadow,
)
from Foundation import NSMakeRect, NSMakeSize

SIZE = 1024
# macOS icon grid: content squircle inset in a transparent canvas
BOX = 824.0
RADIUS = 184.0

# Brand.svelte's mark on its 22-unit grid: bar x, width, heights, centre.
MARK_X = (2.0, 6.2, 10.4, 14.6, 18.8)
MARK_W = 2.4
MARK_H = (6.0, 14.0, 8.0, 17.0, 9.0)
SCALE = 22.0          # the mark spans ~51% of the squircle


def rgb(hex_, alpha=1.0):
    h = hex_.lstrip("#")
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0, alpha)


def main(out_path):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, SIZE, SIZE, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    inset = (SIZE - BOX) / 2.0
    box = NSMakeRect(inset, inset, BOX, BOX)
    squircle = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        box, RADIUS, RADIUS)

    # The tile's own shadow, as macOS icons carry one.
    NSGraphicsContext.saveGraphicsState()
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_(NSMakeSize(0, -10))
    shadow.setShadowBlurRadius_(26)
    shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.34))
    shadow.set()
    rgb("#1A1917").setFill()
    squircle.fill()
    NSGraphicsContext.restoreGraphicsState()

    # The Hub's dark canvas, lit faintly from above.
    NSGradient.alloc().initWithStartingColor_endingColor_(
        rgb("#26241F"), rgb("#161513")).drawInBezierPath_angle_(squircle, -90)
    edge = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(inset + 2, inset + 2, BOX - 4, BOX - 4),
        RADIUS - 2, RADIUS - 2)
    edge.setLineWidth_(3)
    NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.07).setStroke()
    edge.stroke()

    # The mark, centred, in the Hub's dark-mode ink.
    span = (MARK_X[-1] + MARK_W - MARK_X[0]) * SCALE
    x0 = (SIZE - span) / 2.0 - MARK_X[0] * SCALE
    cy = SIZE / 2.0
    ink = NSGradient.alloc().initWithStartingColor_endingColor_(
        rgb("#FFFCF6"), rgb("#E6E1D7"))
    w = MARK_W * SCALE
    for x, h in zip(MARK_X, MARK_H):
        bar = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(x0 + x * SCALE, cy - h * SCALE / 2.0, w, h * SCALE),
            w / 2.0, w / 2.0)
        ink.drawInBezierPath_angle_(bar, -90)

    ctx.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()

    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    data.writeToFile_atomically_(out_path, True)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/localflow_icon.png")
