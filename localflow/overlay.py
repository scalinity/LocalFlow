"""Floating pill overlay — black capsule with white speech-reactive bars."""

import math
import random

import objc
from AppKit import (
    NSAnimationContext,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakeRect, NSObject, NSPointInRect, NSTimer

PILL_W, PILL_H = 118.0, 38.0
N_BARS = 13
BAR_W = 3.5
BAR_GAP = 3.0
BAR_MIN = 4.0
BAR_MAX = 21.0
FPS = 30.0

MODE_RECORDING = "recording"
MODE_PROCESSING = "processing"
MODE_FAILED = "failed"  # M03: a dictation failed after retry; recovery actions live in the menu
MODE_TRANSFORMING = "transforming"  # M11: a selected-text transform generation is running (S19 named stage)


class PillView(NSView):
    """Draws the capsule and animates the bars from a shared mic level."""

    def initWithFrame_(self, frame):
        self = objc.super(PillView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._mode = MODE_RECORDING
        self._level = 0.0
        self._display = 0.0
        self._t = 0.0
        rnd = random.Random(7)
        self._freq = [rnd.uniform(6.0, 11.0) for _ in range(N_BARS)]
        self._phase = [rnd.uniform(0.0, math.tau) for _ in range(N_BARS)]
        self._heights = [BAR_MIN] * N_BARS
        return self

    def setMode_(self, mode):
        self._mode = mode

    def setLevel_(self, level):
        self._level = min(1.0, max(0.0, float(level)))

    def tick(self):
        dt = 1.0 / FPS
        self._t += dt
        # Fast attack, slow release — feels responsive without jitter
        k = 0.75 if self._level > self._display else 0.25
        self._display += (self._level - self._display) * k

        c = (N_BARS - 1) / 2.0
        raw = []
        for i in range(N_BARS):
            # Center-weighted envelope like the Wispr pill
            env = 0.38 + 0.62 * math.exp(-(((i - c) / (0.40 * N_BARS)) ** 2) * 3.0)
            if self._mode == MODE_FAILED:
                # Flat, subdued: the dictation is recoverable from the menu
                target = BAR_MIN + (BAR_MAX - BAR_MIN) * 0.22 * env
            elif self._mode in (MODE_PROCESSING, MODE_TRANSFORMING):
                # Gentle traveling shimmer while transcribing/transforming
                wob = 0.5 + 0.5 * math.sin(self._t * 6.0 - i * 0.75)
                target = BAR_MIN + (BAR_MAX - BAR_MIN) * 0.30 * env * wob
            else:
                # Two traveling waves (plus a touch of per-bar character)
                # keep neighbouring bars coherent instead of spiky
                wob = (
                    0.55
                    + 0.30 * math.sin(self._t * 6.3 - i * 0.8)
                    + 0.15 * math.sin(self._t * 9.7 - i * 1.35 + self._phase[i] * 0.3)
                )
                drive = min(1.0, self._display * 1.45)
                target = BAR_MIN + (BAR_MAX - BAR_MIN) * env * drive * wob
            raw.append(target)
        # Spatial smoothing: each bar leans toward its neighbours so the
        # whole strip reads as one wave
        for i in range(N_BARS):
            left = raw[i - 1] if i > 0 else raw[i]
            right = raw[i + 1] if i < N_BARS - 1 else raw[i]
            smoothed = 0.25 * left + 0.5 * raw[i] + 0.25 * right
            self._heights[i] += (smoothed - self._heights[i]) * 0.5
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        b = self.bounds()
        pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            b, b.size.height / 2.0, b.size.height / 2.0
        )
        NSColor.colorWithCalibratedWhite_alpha_(0.05, 0.97).setFill()
        pill.fill()

        total = N_BARS * BAR_W + (N_BARS - 1) * BAR_GAP
        x = (b.size.width - total) / 2.0
        cy = b.size.height / 2.0
        if self._mode == MODE_FAILED:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.85, 0.28, 0.28, 0.95).setFill()
        else:
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.95).setFill()
        for h in self._heights:
            r = NSMakeRect(x, cy - h / 2.0, BAR_W, h)
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                r, BAR_W / 2.0, BAR_W / 2.0
            ).fill()
            x += BAR_W + BAR_GAP


class Overlay(NSObject):
    """Owns the floating panel. All methods must be called on the main thread."""

    def init(self):
        self = objc.super(Overlay, self).init()
        if self is None:
            return None
        rect = NSMakeRect(0, 0, PILL_W, PILL_H)
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        panel.setLevel_(NSStatusWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        view = PillView.alloc().initWithFrame_(rect)
        panel.setContentView_(view)
        panel.setAlphaValue_(0.0)
        self._panel = panel
        self._view = view
        self._timer = None
        self._level_source = None  # callable returning 0..1
        return self

    def setLevelSource_(self, fn):
        self._level_source = fn

    def _screen_under_mouse(self):
        loc = NSEvent.mouseLocation()
        for s in NSScreen.screens():
            if NSPointInRect(loc, s.frame()):
                return s
        return NSScreen.mainScreen()

    def showWithMode_(self, mode):
        vis = self._screen_under_mouse().visibleFrame()
        x = vis.origin.x + (vis.size.width - PILL_W) / 2.0
        y = vis.origin.y + 20.0
        self._panel.setFrameOrigin_((x, y))
        self._view.setMode_(mode)
        self._panel.orderFrontRegardless()
        if self._timer is None:
            self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / FPS, self, "tick:", None, True
            )
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.15)
        self._panel.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

    def setMode_(self, mode):
        self._view.setMode_(mode)

    def hide(self):
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.20)
        self._panel.animator().setAlphaValue_(0.0)
        NSAnimationContext.endGrouping()

    def tick_(self, timer):
        if self._level_source is not None:
            self._view.setLevel_(self._level_source())
        self._view.tick()
