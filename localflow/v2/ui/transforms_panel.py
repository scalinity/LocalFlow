"""The transform preview panel (V2 M11, Spec S16).

The review surface for selected-text transforms: an intelligible
block/word diff with the review issues' original clauses kept beside
it, and the actions S16 names — accept (replacement through the M08
queue with revalidation), copy, retry-original, apply-another,
transform-of-result, and save-to-Scratchpad (M12: the output becomes a
new note with its task identity recorded). A NOTE-scope capture (M12)
accepts into the Scratchpad editor instead of the external queue.

The panel is NON-ACTIVATING: opening it never makes LocalFlow the
frontmost app, because accept-time revalidation compares the live
frontmost against the captured target (an activating panel would flip
the destination under its own replacement — the M08 focus-steal
discipline applied to the transform surface).

Undo after an accepted replacement is the M08 target-bound undo (the
Recovery menu's Undo Last Insertion) — this panel never builds a
second undo engine.
"""

from __future__ import annotations

import objc
from AppKit import (NSAppearance, NSAttributedString, NSBezierPath, NSButton, NSFont,
                    NSColor, NSEvent, NSScreen, NSStatusWindowLevel,
                    NSMakeRect, NSMenu, NSMenuItem,
                    NSMutableAttributedString, NSPanel, NSSize,
                    NSScrollView, NSTextField, NSTextView, NSView,
                    NSWindowStyleMaskBorderless,
                    NSWindowStyleMaskNonactivatingPanel,
                    NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorFullScreenAuxiliary,
                    NSTrackingArea, NSTrackingMouseEnteredAndExited,
                    NSTrackingActiveAlways, NSTrackingInVisibleRect)
from Foundation import NSObject

PANEL_W, PANEL_H = 580.0, 480.0

# Two action rows (title, action, enabled, width, row).
_ACTIONS = (
    ("Accept", "panelAccept:", True, 74.0, 0),
    ("Copy", "panelCopy:", True, 62.0, 0),
    ("Retry Original", "panelRetry:", True, 114.0, 0),
    ("Apply Another…", "panelApplyOther:", True, 126.0, 0),
    ("Transform Output…", "panelTransformResult:", True, 146.0, 1),
    ("Save to Scratchpad", "panelSaveToScratchpad:", True, 158.0, 1),
)


BUTTON_GAP = 10.0
BUTTON_H = 32.0
HEADER_H = 94.0
FOOTER_H = 112.0

# The review surface is drawn in warm ink in both appearances (the
# desktop companion's change-review style).
_INK = (0x1C, 0x1B, 0x19)
_INK_TEXT = (0xF3, 0xF0, 0xEA)
_INK_MUTED = (0x90, 0x8B, 0x83)
_INK_ADDED = (0x55, 0xAA, 0xA4)


class SpeechReviewPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


def _rgb(c, alpha=1.0):
    from AppKit import NSColor
    return NSColor.colorWithSRGBRed_green_blue_alpha_(
        c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, alpha)


class ReviewActionButton(NSButton):
    """Native button semantics, with centered type and a quiet hover wash."""

    @objc.python_method
    def review_style(self, *, text_only=False, primary=False, sliders=False):
        self._text_only, self._primary, self._sliders = text_only, primary, sliders
        self._hovered = False
        self.setBordered_(False)
        self.setFont_(NSFont.systemFontOfSize_weight_(13, .23))
        self.setNeedsDisplay_(True)

    def updateTrackingAreas(self):
        tracking = getattr(self, '_tracking', None)
        if tracking is not None:
            self.removeTrackingArea_(tracking)
        self._tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            NSMakeRect(0, 0, 0, 0), NSTrackingMouseEnteredAndExited |
            NSTrackingActiveAlways | NSTrackingInVisibleRect, self, None)
        self.addTrackingArea_(self._tracking)
        objc.super(ReviewActionButton, self).updateTrackingAreas()

    def mouseEntered_(self, event):
        self._hovered = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        self._hovered = False
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        from AppKit import NSFontAttributeName, NSForegroundColorAttributeName
        bounds = self.bounds()
        active = self.isEnabled()
        hover = active and (getattr(self, '_hovered', False) or self.isHighlighted())
        text_only = getattr(self, '_text_only', False)
        primary = getattr(self, '_primary', False)
        fill = _INK
        if not text_only or hover:
            if primary and not text_only:
                fill = (0xAE, 0xDA, 0xCF) if hover else (0x9C, 0xC9, 0xBE)
            else:
                fill = (0x3C, 0x3B, 0x37) if hover else (0x2D, 0x2C, 0x29)
            shape = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                bounds, 10, 10)
            _rgb(fill, 1 if active else .45).setFill()
            shape.fill()
        if primary:
            color = (0xB1, 0xD8, 0xCD) if text_only else _INK
        else:
            color = _INK_TEXT if hover else (0xD1, 0xCE, 0xC8)
        if getattr(self, '_sliders', False):
            # Two horizontal rails, with opposite-positioned circular knobs.
            cx, cy = bounds.size.width / 2, bounds.size.height / 2
            rails = NSBezierPath.bezierPath()
            rails.setLineWidth_(1.5)
            rails.setLineCapStyle_(1)
            for dy in (4, -4):
                rails.moveToPoint_((cx - 8, cy + dy))
                rails.lineToPoint_((cx + 8, cy + dy))
            _rgb(color).setStroke()
            rails.stroke()
            for dx, dy in ((-4, 4), (4, -4)):
                knob = NSBezierPath.bezierPathWithOvalInRect_(
                    NSMakeRect(cx + dx - 2.5, cy + dy - 2.5, 5, 5))
                _rgb(fill).setFill()
                knob.fill()
                knob.setLineWidth_(1.5)
                _rgb(color).setStroke()
                knob.stroke()
            return
        label = NSAttributedString.alloc().initWithString_attributes_(str(self.title()), {
            NSFontAttributeName: self.font(),
            NSForegroundColorAttributeName: _rgb(color, 1 if active else .4)})
        size = label.size()
        label.drawAtPoint_(((bounds.size.width - size.width) / 2,
                           (bounds.size.height - size.height) / 2))


def inline_changes(source, output):
    """Presentation only: the output as written, with each change marked.
    Whitespace is kept as its own token so the output's text (line
    breaks included) reads exactly as produced. Returns ``(pieces,
    changes)``: pieces are ``(kind, text)`` with kind equal / added /
    removed; changes counts the edited stretches."""
    import difflib
    import re
    a = re.findall(r"\s+|\S+", source)
    b = re.findall(r"\s+|\S+", output)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    ops = sm.get_opcodes()
    pieces, changes = [], 0
    run = None  # [removed, added] of the change being collected

    def close():
        nonlocal run, changes
        if run is None:
            return
        removed, added = run[0].strip(), run[1]
        if removed or added.strip():
            changes += 1
            if removed:
                pieces.append(("removed", removed))
                if added.strip():
                    pieces.append(("equal", " "))
            lead = added[:len(added) - len(added.lstrip())]
            if lead:
                pieces.append(("equal", lead))
            if added.strip():
                pieces.append(("added", added.strip()))
            trail = added[len(added.rstrip()):]
            if trail:
                pieces.append(("equal", trail))
        run = None

    for k, (tag, i1, i2, j1, j2) in enumerate(ops):
        same = "".join(b[j1:j2])
        if tag == "equal" and not (run is not None and not same.strip()
                                   and k + 1 < len(ops)):
            close()
            pieces.append(("equal", same))
            continue
        # A change, or whitespace between two changes: one edited stretch.
        run = run or ["", ""]
        run[0] += "".join(a[i1:i2])
        run[1] += same if tag == "equal" else "".join(b[j1:j2])
    close()
    return pieces, changes


def action_frames(actions=_ACTIONS):
    """Two centered-label rows, aligned to the body's 24-pt margin."""
    frames = []
    next_x = {}
    for _title, _action, _enabled, w, row in actions:
        x = next_x.get(row, 24.0)
        frames.append((x, 64.0 - row * 40.0, w, BUTTON_H))
        next_x[row] = x + w + BUTTON_GAP
    return frames


class TransformPreviewPanel(NSObject):
    """One lazily-constructed panel per process; ``show`` refreshes it
    for the latest result. All calls land on the main thread."""

    @objc.python_method
    def init_panel(self, coordinator, *, action_style='text'):
        self = self.init()
        self.coordinator = coordinator
        self.panel = SpeechReviewPanel.alloc()\
            .initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, PANEL_W, PANEL_H),
                NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                2, False)
        self.panel.setReleasedWhenClosed_(False)
        self.panel.setMinSize_(NSSize(460.0, 240.0))
        self._style_panel()
        content = NSView.alloc().initWithFrame_(
            self.panel.contentView().bounds())
        self.panel.setContentView_(content)
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(26.0)
        content.layer().setBackgroundColor_(_rgb(_INK).CGColor())
        content.layer().setMasksToBounds_(True)
        self.name = NSTextField.labelWithString_("")
        self.name.setFont_(NSFont.boldSystemFontOfSize_(17.0))
        self.name.setTextColor_(_rgb(_INK_TEXT))
        self.name.setFrame_(NSMakeRect(24, PANEL_H - 52, 440, 24))
        self.name.setAutoresizingMask_(8)
        content.addSubview_(self.name)
        # Header: how many edits, and the way to the transform's settings.
        self.count = NSTextField.labelWithString_("")
        self.count.setFont_(NSFont.systemFontOfSize_(12.0))
        self.count.setTextColor_(_rgb(_INK_MUTED))
        self.count.setFrame_(NSMakeRect(24, PANEL_H - 76, 500, 18))
        self.count.setAutoresizingMask_(8)  # pinned to the top
        content.addSubview_(self.count)
        self.configure = ReviewActionButton.buttonWithTitle_target_action_(
            "", self, "panelConfigure:")
        self.configure.review_style(text_only=True, sliders=True)
        self.configure.setAccessibilityLabel_("Configure transform")
        self.configure.setToolTip_("Configure transform")
        self.configure.setFrame_(NSMakeRect(PANEL_W - 96, PANEL_H - 56, 32, 32))
        self.configure.setAutoresizingMask_(1 | 8)
        content.addSubview_(self.configure)
        self.dismiss = ReviewActionButton.buttonWithTitle_target_action_("×", self, "panelDismiss:")
        self.dismiss.review_style(text_only=True)
        self.dismiss.setFont_(NSFont.systemFontOfSize_(20))
        self.dismiss.setAccessibilityLabel_("Dismiss transform review")
        self.dismiss.setFrame_(NSMakeRect(PANEL_W - 56, PANEL_H - 56, 32, 32))
        self.dismiss.setAutoresizingMask_(1 | 8)
        content.addSubview_(self.dismiss)
        self.text = NSTextView.alloc().initWithFrame_(
            NSMakeRect(24, FOOTER_H, PANEL_W - 48, PANEL_H - FOOTER_H - HEADER_H))
        self.text.setEditable_(False)
        self.text.setRichText_(False)
        self.text.setDrawsBackground_(False)
        self.text.setTextContainerInset_(NSSize(0.0, 4.0))
        self.text.setFont_(NSFont.systemFontOfSize_(15.0))
        self.text.setTextColor_(_rgb(_INK_TEXT))
        self.scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(24, FOOTER_H, PANEL_W - 48, PANEL_H - FOOTER_H - HEADER_H))
        self.scroll.setDocumentView_(self.text)
        self.scroll.setHasVerticalScroller_(True)
        self.scroll.setDrawsBackground_(False)
        self.scroll.setBorderType_(0)
        self.scroll.setAutoresizingMask_(2 | 16)  # w+h flexible
        content.addSubview_(self.scroll)
        self._buttons = {}
        for (title, action, enabled, _w, _row), (x, y, w, h) in zip(
                _ACTIONS, action_frames()):
            btn = ReviewActionButton.buttonWithTitle_target_action_(
                title, self if action else None, action)
            btn.review_style(text_only=action_style == 'text', primary=action == 'panelAccept:')
            btn.setEnabled_(enabled)
            btn.setFrame_(NSMakeRect(x, y, w, h))
            content.addSubview_(btn)
            self._buttons[action or title] = btn
        self._other_menu = None
        self._state = {"result": None, "capture": None, "defn": None,
                       "candidate_id": None}
        return self

    @objc.python_method
    def _style_panel(self):
        """Matte warm ink, speech-pill shadow and no titlebar chrome."""
        try:
            self.panel.setAppearance_(NSAppearance.appearanceNamed_(
                "NSAppearanceNameDarkAqua"))
            self.panel.setOpaque_(False)
            self.panel.setBackgroundColor_(NSColor.clearColor())
            self.panel.setHasShadow_(True)
            self.panel.setHidesOnDeactivate_(False)
            self.panel.setLevel_(NSStatusWindowLevel)
            self.panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary)
        except Exception:
            pass

    @objc.python_method
    def _append(self, text, s, kind):
        """One run of the review text: kept words in ink, added words on
        a teal wash, removed words struck in muted ink."""
        from AppKit import (NSBackgroundColorAttributeName,
                            NSFontAttributeName,
                            NSForegroundColorAttributeName,
                            NSMutableParagraphStyle,
                            NSParagraphStyleAttributeName,
                            NSStrikethroughStyleAttributeName)
        para = NSMutableParagraphStyle.alloc().init()
        para.setLineSpacing_(6.0)
        attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(15.0),
                 NSForegroundColorAttributeName: _rgb(_INK_TEXT),
                 NSParagraphStyleAttributeName: para}
        if kind == "added":
            attrs[NSBackgroundColorAttributeName] = _rgb(_INK_ADDED, 0.32)
        elif kind == "removed":
            attrs[NSForegroundColorAttributeName] = _rgb(_INK_MUTED)
            attrs[NSStrikethroughStyleAttributeName] = 1
        elif kind == "note":
            attrs[NSForegroundColorAttributeName] = _rgb((0xAA, 0xA5, 0x9D))
            attrs[NSFontAttributeName] = NSFont.systemFontOfSize_(13.0)
        text.appendAttributedString_(
            NSAttributedString.alloc().initWithString_attributes_(s, attrs))

    @objc.python_method
    def _fit_height(self):
        """Size the panel to its text (a short result is a compact card;
        a long one scrolls inside the full height)."""
        lm = self.text.layoutManager()
        tc = self.text.textContainer()
        frame = self.panel.frame()
        width = frame.size.width - 48
        tc.setContainerSize_(NSSize(width, 1e7))
        lm.ensureLayoutForTextContainer_(tc)
        used = lm.usedRectForTextContainer_(tc).size.height + 8
        content_h = min(PANEL_H, max(240.0, FOOTER_H + HEADER_H + used + 16))
        self.panel.setContentSize_(NSSize(frame.size.width, content_h))
        self.scroll.setFrame_(NSMakeRect(24, FOOTER_H, width,
                                         content_h - FOOTER_H - HEADER_H))
        self.text.setFrameSize_(NSSize(width, max(used, self.scroll.contentSize().height)))

    @objc.python_method
    def _anchor(self):
        """Grow upward from the same bottom-center pill anchor."""
        overlay = getattr(self.coordinator, "overlay", None)
        pill = getattr(overlay, "_panel", None)
        frame = self.panel.frame()
        if pill is not None:
            anchor = pill.frame()
            x = anchor.origin.x + (anchor.size.width - frame.size.width) / 2
            y = anchor.origin.y
        else:
            from Foundation import NSPointInRect
            screen = next((s for s in NSScreen.screens() if NSPointInRect(NSEvent.mouseLocation(), s.frame())), NSScreen.mainScreen())
            visible = screen.visibleFrame()
            x = visible.origin.x + (visible.size.width - frame.size.width) / 2
            y = visible.origin.y + 20
        self.panel.setFrameOrigin_((x, y))

    def panelDismiss_(self, sender):
        self.panel.orderOut_(None)

    def panelConfigure_(self, sender):
        """Open this transform in the Hub (its settings). The Hub opens
        through the coordinator's own guard; the review stays here."""
        coord = self.coordinator
        try:
            coord.openHub_(None)
            hub = getattr(coord, "_hub", None)
            if hub is not None and hasattr(hub, "show_route"):
                hub.show_route("transforms")
        except Exception:
            pass

    @objc.python_method
    def show(self, result, capture, defn, candidate_id):
        self._state = {"result": result, "capture": capture,
                       "defn": defn, "candidate_id": candidate_id}
        title = {"applied": "ready to apply",
                 "needs_review": "needs review — original clauses kept",
                 "fallback_original": "fallback: original kept"}.get(
            result.path, result.path)
        self.panel.setTitle_(f"{defn.name} — {title}")
        self.name.setStringValue_(defn.name)
        source = result.job.source if result.job else capture["source"]
        pieces, changes = inline_changes(source, result.output)
        self.count.setStringValue_(
            ("No changes" if not changes else f"{changes} change{'' if changes == 1 else 's'}") + " · " + title)
        text = NSMutableAttributedString.alloc().init()
        for kind, s in pieces:
            self._append(text, s, kind)
        tail = []
        if result.review_excerpts:
            tail.append("\n\nREVIEW — these source requirements have"
                        " uncertain coverage; their original wording"
                        " is kept for review:")
            for ex in result.review_excerpts:
                tail.append(f"\n  • {ex}")
        if result.path == "fallback_original":
            tail.append(f"\n\nReason: {result.reason}")
        if tail:
            self._append(text, "".join(tail), "note")
        self.text.textStorage().setAttributedString_(text)
        self._fit_height()
        # Retry needs a task (a refused job has none to re-run).
        self._buttons["panelRetry:"].setEnabled_(result.job is not None)
        self._buttons["panelAccept:"].setEnabled_(True)
        self._anchor()
        self.panel.orderFrontRegardless()

    @objc.python_method
    def reoffer(self, message, result):
        """M12-AUDIT-19: an accept that could not be applied keeps the
        result here — Copy and Save to Scratchpad stay the explicit
        recovery choices; nothing is published on the user's behalf.
        Only while the panel still shows THAT result: a later preview
        is never relabelled by an earlier one's outcome."""
        if self._state.get("result") is not result:
            return
        defn = self._state.get("defn")
        self.panel.setTitle_(f"{defn.name if defn else 'Transform'} —"
                             f" not applied: {message}")
        self.count.setStringValue_(f"Not applied: {message}")
        self._buttons["panelAccept:"].setEnabled_(False)
        self.panel.orderFrontRegardless()

    # ---- actions (main thread; the generation runs off it) -------------

    def panelAccept_(self, sender):
        st = self._state
        if st["result"] is None or st["capture"] is None:
            return
        self.panel.orderOut_(None)
        self.coordinator.tfAcceptTransform(
            st["result"], st["capture"], st["candidate_id"])

    def panelCopy_(self, sender):
        st = self._state
        if st["result"] is not None:
            self.coordinator.tfCopyTransform(st["result"])
        self.panel.orderOut_(None)

    def panelRetry_(self, sender):
        st = self._state
        if st["result"] is None or st["capture"] is None:
            return
        self.panel.orderOut_(None)
        self.coordinator.tfRetryOriginal(
            st["result"], st["capture"], st["defn"], st["candidate_id"])

    def _choose_definition(self, sender, action):
        st = self._state
        if st["result"] is None or st["capture"] is None:
            return
        snapshot = self.coordinator._transforms_snapshot()
        defs = [d for d in (snapshot.definitions if snapshot else [])
                if d.transform_id != st["defn"].transform_id]
        if not defs:
            return
        menu = NSMenu.alloc().init()
        for d in defs:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"{d.name} ({d.mode})", action, "")
            item.setTarget_(self)
            item.setRepresentedObject_(d.transform_id)
            menu.addItem_(item)
        self._other_menu = menu  # keep alive while open
        menu.popUpMenuPositioningItem_atLocation_inView_(
            None, sender.frame().origin, sender.superview())

    def panelApplyOther_(self, sender):
        self._choose_definition(sender, "panelOtherChosen:")

    def panelOtherChosen_(self, sender):
        st = self._state
        other = sender.representedObject()
        if st["result"] is None or st["capture"] is None or not other:
            return
        self.panel.orderOut_(None)
        self.coordinator.tfApplyAnother(
            st["result"], st["capture"], st["defn"], other)

    def panelTransformResult_(self, sender):
        self._choose_definition(sender, "panelResultChosen:")

    @objc.python_method
    def reoffer_save(self, message, result):
        """A Save to Scratchpad that did not settle keeps the result
        here with the reason, so Save can be pressed again for the same
        result (xm-policy-r1 D09) — only while no later preview has
        replaced it."""
        if self._state.get("result") is not result:
            return
        defn = self._state.get("defn")
        self.panel.setTitle_(f"{defn.name if defn else 'Transform'} —"
                             f" Save to Scratchpad: {message}")
        self.count.setStringValue_(f"Save to Scratchpad: {message}")
        self.panel.orderFrontRegardless()

    def panelResultChosen_(self, sender):
        st = self._state
        other = sender.representedObject()
        if st["result"] is None or st["capture"] is None or not other:
            return
        self.panel.orderOut_(None)
        self.coordinator.tfTransformOfResult(
            st["result"], st["capture"], other)

    def panelSaveToScratchpad_(self, sender):
        """M12: the transform output becomes a new Scratchpad note
        (origin=transform, task identity recorded). The panel closes —
        the note, not the selection, receives the output."""
        st = self._state
        if st["result"] is None or st["defn"] is None:
            return
        self.panel.orderOut_(None)
        self.coordinator.tfSaveToScratchpad(st["result"], st["defn"])
