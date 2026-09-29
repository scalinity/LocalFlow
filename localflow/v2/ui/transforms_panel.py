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
from AppKit import (NSAppearance, NSAttributedString, NSButton, NSFont,
                    NSMakeRect, NSMenu, NSMenuItem,
                    NSMutableAttributedString, NSPanel, NSSize,
                    NSScrollView, NSTextField, NSTextView, NSView,
                    NSWindowStyleMaskClosable,
                    NSWindowStyleMaskNonactivatingPanel,
                    NSWindowStyleMaskResizable,
                    NSWindowStyleMaskTitled)
from Foundation import NSObject

from ..transforms import diffview

PANEL_W, PANEL_H = 580.0, 480.0
WORD_DIFF_MAX_WORDS = 40   # inline word diff below this size

# Two action rows (title, action, enabled, width, row).
_ACTIONS = (
    ("Accept", "panelAccept:", True, 76.0, 0),
    ("Copy", "panelCopy:", True, 62.0, 0),
    ("Retry Original", "panelRetry:", True, 108.0, 0),
    ("Apply Another…", "panelApplyOther:", True, 118.0, 0),
    ("Transform Output…", "panelTransformResult:", True, 138.0, 1),
    ("Save to Scratchpad", "panelSaveToScratchpad:", True, 148.0, 1),
)


BUTTON_GAP = 8.0
BUTTON_H = 28.0
HEADER_H = 40.0

# The review surface is drawn in warm ink in both appearances (the
# desktop companion's change-review style).
_INK = (0x1C, 0x1B, 0x19)
_INK_TEXT = (0xF3, 0xF0, 0xEA)
_INK_MUTED = (0x90, 0x8B, 0x83)
_INK_ADDED = (0x55, 0xAA, 0xA4)


def _rgb(c, alpha=1.0):
    from AppKit import NSColor
    return NSColor.colorWithSRGBRed_green_blue_alpha_(
        c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, alpha)


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
    """(x, y, w, h) for every action: buttons in a row sit side by side
    from the left margin with a fixed gap (the widest row, 76+62+108+118
    plus gaps = 388 pt, fits the 460-pt minimum width)."""
    frames = []
    next_x = {}
    for _title, _action, _enabled, w, row in actions:
        x = next_x.get(row, 12.0)
        frames.append((x, 62.0 - row * 34.0, w, BUTTON_H))
        next_x[row] = x + w + BUTTON_GAP
    return frames


class TransformPreviewPanel(NSObject):
    """One lazily-constructed panel per process; ``show`` refreshes it
    for the latest result. All calls land on the main thread."""

    @objc.python_method
    def init_panel(self, coordinator):
        self = self.init()
        self.coordinator = coordinator
        self.panel = NSPanel.alloc()\
            .initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, PANEL_W, PANEL_H),
                NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                | NSWindowStyleMaskResizable
                | NSWindowStyleMaskNonactivatingPanel,
                2, False)
        self.panel.setTitle_("Transform Preview")
        self.panel.setReleasedWhenClosed_(False)
        self.panel.setMinSize_(NSSize(460.0, 360.0))
        self._style_panel()
        content = NSView.alloc().initWithFrame_(
            self.panel.contentView().bounds())
        self.panel.setContentView_(content)
        # Header: how many edits, and the way to the transform's settings.
        self.count = NSTextField.labelWithString_("")
        self.count.setFont_(NSFont.boldSystemFontOfSize_(15.0))
        self.count.setTextColor_(_rgb(_INK_TEXT))
        self.count.setFrame_(NSMakeRect(16, PANEL_H - HEADER_H + 8,
                                        260, 22))
        self.count.setAutoresizingMask_(8)  # pinned to the top
        content.addSubview_(self.count)
        self.configure = NSButton.buttonWithTitle_target_action_(
            "Configure", self, "panelConfigure:")
        self.configure.setBordered_(False)
        self.configure.setContentTintColor_(_rgb(_INK_TEXT))
        self.configure.setFrame_(NSMakeRect(PANEL_W - 176,
                                            PANEL_H - HEADER_H + 6,
                                            164, 26))
        self.configure.setAlignment_(2)  # right
        self.configure.setAutoresizingMask_(1 | 8)
        content.addSubview_(self.configure)
        self.text = NSTextView.alloc().initWithFrame_(
            NSMakeRect(12, 118, PANEL_W - 24, PANEL_H - 142 - HEADER_H))
        self.text.setEditable_(False)
        self.text.setRichText_(False)
        self.text.setDrawsBackground_(False)
        self.text.setTextContainerInset_(NSSize(4.0, 6.0))
        self.text.setFont_(NSFont.systemFontOfSize_(15.0))
        self.text.setTextColor_(_rgb(_INK_TEXT))
        self.scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(12, 118, PANEL_W - 24, PANEL_H - 142 - HEADER_H))
        self.scroll.setDocumentView_(self.text)
        self.scroll.setHasVerticalScroller_(True)
        self.scroll.setDrawsBackground_(False)
        self.scroll.setBorderType_(0)
        self.scroll.setAutoresizingMask_(2 | 16)  # w+h flexible
        content.addSubview_(self.scroll)
        self._buttons = {}
        for (title, action, enabled, _w, _row), (x, y, w, h) in zip(
                _ACTIONS, action_frames()):
            btn = NSButton.buttonWithTitle_target_action_(
                title, self if action else None, action)
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
        """Warm ink in either appearance; the native titlebar stays (the
        panel keeps its title, controls and non-activating behavior)."""
        try:
            self.panel.setAppearance_(NSAppearance.appearanceNamed_(
                "NSAppearanceNameDarkAqua"))
            self.panel.setTitlebarAppearsTransparent_(True)
            self.panel.setBackgroundColor_(_rgb(_INK))
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
        width = frame.size.width - 24
        tc.setContainerSize_(NSSize(width - 8, 1e7))
        lm.ensureLayoutForTextContainer_(tc)
        used = lm.usedRectForTextContainer_(tc).size.height + 20
        content_h = min(PANEL_H, max(300.0, 118 + HEADER_H + used + 20))
        self.panel.setContentSize_(NSSize(frame.size.width, content_h))
        self.scroll.setFrame_(NSMakeRect(12, 118, width,
                                         content_h - 142 - HEADER_H + 24))

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
        source = result.job.source if result.job else capture["source"]
        pieces, changes = inline_changes(source, result.output)
        self.count.setStringValue_(
            "No changes" if not changes else
            f"{changes} change{'' if changes == 1 else 's'}")
        self.configure.setTitle_(f"Configure {defn.name}")
        text = NSMutableAttributedString.alloc().init()
        if len(source.split()) <= WORD_DIFF_MAX_WORDS:
            # Short text: the output as written, each change marked.
            for kind, s in pieces:
                self._append(text, s, kind)
        else:
            self._append(text, diffview.block_diff(source, result.output),
                         "equal")
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
        self.panel.center()
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
