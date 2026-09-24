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
from AppKit import (NSButton, NSMakeRect, NSMenu, NSMenuItem, NSPanel,
                    NSSize, NSScrollView, NSTextView, NSView,
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
        content = NSView.alloc().initWithFrame_(
            self.panel.contentView().bounds())
        self.panel.setContentView_(content)
        self.text = NSTextView.alloc().initWithFrame_(
            NSMakeRect(12, 118, PANEL_W - 24, PANEL_H - 142))
        self.text.setEditable_(False)
        self.text.setRichText_(False)
        self.scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(12, 118, PANEL_W - 24, PANEL_H - 142))
        self.scroll.setDocumentView_(self.text)
        self.scroll.setHasVerticalScroller_(True)
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
    def show(self, result, capture, defn, candidate_id):
        self._state = {"result": result, "capture": capture,
                       "defn": defn, "candidate_id": candidate_id}
        title = {"applied": "ready to apply",
                 "needs_review": "needs review — original clauses kept",
                 "fallback_original": "fallback: original kept"}.get(
            result.path, result.path)
        self.panel.setTitle_(f"{defn.name} — {title}")
        parts = [diffview.block_diff(result.job.source if result.job
                                     else capture["source"],
                                     result.output)]
        source = result.job.source if result.job else capture["source"]
        if len(source.split()) <= WORD_DIFF_MAX_WORDS:
            parts.append("")
            parts.append("Word diff: "
                         + diffview.render_word_diff(source,
                                                     result.output))
        if result.review_excerpts:
            parts.append("\nREVIEW — these source requirements have"
                         " uncertain coverage; their original wording"
                         " is kept for review:")
            for ex in result.review_excerpts:
                parts.append(f"  • {ex}")
        if result.path == "fallback_original":
            parts.append(f"\nReason: {result.reason}")
        self.text.setString_("\n".join(parts))
        frame = self.panel.frame()
        self.scroll.setFrameSize_(
            NSSize(frame.size.width - 24, frame.size.height - 142))
        # Retry needs a task (a refused job has none to re-run).
        self._buttons["panelRetry:"].setEnabled_(result.job is not None)
        self.panel.center()
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
