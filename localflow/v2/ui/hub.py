"""The native Hub shell (V2 M09, Spec S19, contract hub.md).

AppKit/PyObjC window binding for ``HubState``: persistent sidebar
(Home / History / Diagnostics / Models / Settings), search, detail
pane, saved window frame, native traffic lights, light/dark via system
controls. The shell owns NO data logic — every question goes through
the query services, every action through a coordinator command (the
architecture contract: no view owns a model or writes into target
apps).

Behavioral rules carried here:

- Closing the Hub only orders the window out; the menu-bar dictation
  service keeps running (explicit Quit is the app's only exit).
- Opening/activating while an insertion transaction is in flight is
  deferred by the coordinator (window actions never steal focus during
  insertion — M09 regression requirement).
- The window is created once; reopening focuses the existing window
  (single instance, state preserved — M09-AC04).

The Hub has three NSTableViews (sidebar, history list, training list);
PyObjC exposes one informal-protocol method per selector, so the
dataSource/delegate implementations route on the table object.
"""

from __future__ import annotations

import difflib
import json

import objc
import Foundation
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSFont,
    NSMakeRect,
    NSPopUpButton,
    NSSearchField,
    NSScrollView,
    NSSegmentedControl,
    NSSegmentStyleAutomatic,
    NSSize,
    NSSwitchButton,
    NSTableView,
    NSTableColumn,
    NSTextField,
    NSTextView,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

from .state import HubState, VIEWS, VIEW_TITLES

SIDEBAR_WIDTH = 190.0
DEFAULT_SIZE = (1100.0, 760.0)
MIN_SIZE = (900.0, 620.0)

_MONO = None


def _mono():
    global _MONO
    if _MONO is None:
        _MONO = NSFont.monospacedSystemFontOfSize_weight_(11.0, 0.0)
    return _MONO


def _label(frame, text):
    tf = NSTextField.alloc().initWithFrame_(frame)
    tf.setEditable_(False)
    tf.setBezeled_(False)
    tf.setDrawsBackground_(False)
    tf.setStringValue_(text)
    return tf


def _button(title, target, action, frame):
    b = NSButton.buttonWithTitle_target_action_(title, target, action)
    b.setFrame_(frame)
    return b


def _textview(frame, text=""):
    tv = NSTextView.alloc().initWithFrame_(frame)
    tv.setEditable_(False)
    tv.setSelectable_(True)
    tv.setFont_(_mono())
    tv.setString_(text)
    return tv


def _scroll(frame, view):
    sc = NSScrollView.alloc().initWithFrame_(frame)
    sc.setDocumentView_(view)
    sc.setHasVerticalScroller_(True)
    sc.setAutohidesScrollers_(True)
    return sc


def _stage_diff(a, b) -> str:
    """A compact unified diff between two lineage stages."""
    if a is None or b is None:
        return "(stage unavailable)"
    diff = difflib.unified_diff(
        a.splitlines() or [""], b.splitlines() or [""],
        fromfile="before", tofile="after", lineterm="", n=1)
    return "\n".join(list(diff)[2:]) or "(no changes)"


class HubController(NSObject):
    """Owner of the Hub window. ``initWithSpec_`` is the only entry
    point (from the coordinator's Open Hub menu action); the controller
    lives for the process lifetime once created."""

    @objc.python_method
    def initWithSpec_(self, spec):
        self = self.init()
        self.spec = spec
        self.coordinator = spec.get("coordinator")
        self.replay = spec.get("replay")
        self.state = HubState(
            spec["history_service"],
            training_service=spec.get("training_service"),
            diagnostics_provider=spec.get("diagnostics_provider"),
            coordinator=self.coordinator)
        self.state.on_update = self._state_updated
        self._built_views = {}
        self._history_flat = []  # group markers + rows, in table order
        self._suppress_select = False
        self._building = True
        self._build_window()
        self._building = False
        return self

    # ---- window / sidebar -------------------------------------------------

    @objc.python_method
    def _build_window(self):
        from AppKit import NSScreen
        screen = NSScreen.mainScreen()
        visible = screen.visibleFrame() if screen is not None \
            else NSMakeRect(0, 0, *DEFAULT_SIZE)
        w = min(DEFAULT_SIZE[0], visible.size.width)
        h = min(DEFAULT_SIZE[1], visible.size.height)
        self.window = NSWindow.alloc()\
            .initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(visible.origin.x, visible.origin.y, w, h),
                (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                 | NSWindowStyleMaskMiniaturizable
                 | NSWindowStyleMaskResizable),
                NSBackingStoreBuffered, False)
        self.window.setTitle_("LocalFlow Hub")
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self)
        # Saved window position (native persistence); the clamp keeps
        # the minimum honest on screens smaller than the design default
        # (M09-AC03).
        self.window.setMinSize_(NSSize(
            min(MIN_SIZE[0], visible.size.width),
            min(MIN_SIZE[1], visible.size.height)))
        try:
            self.window.setFrameAutosaveName_("LocalFlowHub")
        except Exception:
            pass
        content = NSView.alloc().initWithFrame_(
            self.window.contentView().bounds())
        self.window.setContentView_(content)

        # Sidebar source list: keyboard arrows move selection; the
        # coordinator's ⌘1..⌘5 menu equivalents land on the same state.
        self.sidebar = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, SIDEBAR_WIDTH,
                       content.bounds().size.height))
        col = NSTableColumn.alloc().initWithIdentifier_("view")
        col.setWidth_(SIDEBAR_WIDTH - 8)
        self.sidebar.addTableColumn_(col)
        self.sidebar.setDataSource_(self)
        self.sidebar.setDelegate_(self)
        self.sidebar.setSelectionHighlightStyle_(1)  # source list
        self.sidebar.setAllowsEmptySelection_(False)
        self.sidebar.setAutoresizingMask_(2)  # height flexible
        side_scroll = _scroll(
            NSMakeRect(0, 0, SIDEBAR_WIDTH + 2,
                       content.bounds().size.height), self.sidebar)
        side_scroll.setAutoresizingMask_(18)  # w+h flexible
        side_scroll.setHasVerticalScroller_(False)
        content.addSubview_(side_scroll)

        self.content = NSView.alloc().initWithFrame_(NSMakeRect(
            SIDEBAR_WIDTH + 4, 0,
            content.bounds().size.width - SIDEBAR_WIDTH - 4,
            content.bounds().size.height))
        self.content.setAutoresizingMask_(2 | 16)  # flexible, left-anchored
        content.addSubview_(self.content)
        self.window.setInitialFirstResponder_(self.sidebar)
        self._select_view_index(0, initial=True)

    def _select_view_index(self, index, initial=False):
        view = VIEWS[int(index)]
        self._suppress_select = True
        try:
            self.sidebar.selectRowIndexes_byExtendingSelection_(
                Foundation.NSIndexSet.indexSetWithIndex_(int(index)),
                False)
        finally:
            self._suppress_select = False
        if view not in self._built_views:
            self._built_views[view] = getattr(
                self, f"_build_{view}_view")()
        for sub in list(self.content.subviews()):
            sub.removeFromSuperview()
        self.content.addSubview_(self._built_views[view])
        self.state.select_view(view)

    # ---- state publish back-edge -------------------------------------------

    @objc.python_method
    def _state_updated(self, state):
        # Called from the query thread; hop to the main thread for UI
        # work. Headless tests replace callAfter to run inline.
        AppHelper.callAfter(self._refresh, state.selected_view)

    @objc.python_method
    def _refresh(self, view):
        if view not in self._built_views:
            return
        getattr(self, f"_refresh_{view}_view")()

    # ---- showing / closing ---------------------------------------------------

    def showWindow_(self, sender):
        """Focus the existing window (single instance). The coordinator
        defers this call while an insertion is in flight."""
        self.window.makeKeyAndOrderFront_(NSApp)
        try:
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass
        self.state.show()

    def windowShouldClose_(self, sender):
        # Close ≠ quit (M09-AC04): hide only; the menu-bar service and
        # every view's state survive.
        self.window.orderOut_(None)
        self.state.close()
        return False

    # ---- shared table routing --------------------------------------------------

    def numberOfRowsInTableView_(self, table):
        if table is getattr(self, "history_table", None):
            return len(self._history_flat)
        if table is getattr(self, "training_table", None):
            rows = (self.state.views["models"].get("data")
                    or {}).get("examples") or []
            return len(rows)
        return len(VIEWS)

    def tableView_objectValueForTableColumn_row_(self, table, col, row):
        if table is getattr(self, "history_table", None):
            entry = self._history_flat[int(row)]
            if entry.get("__group__"):
                return entry["__group__"]
            if col.identifier() == "when":
                return entry.get("date") or "Undated"
            return (entry.get("preview")
                    or f"({entry.get('state')} — no retained text)")
        if table is getattr(self, "training_table", None):
            rows = (self.state.views["models"].get("data")
                    or {}).get("examples") or []
            r = rows[int(row)]
            if col.identifier() == "ex":
                stamp = r.get("captured_at_utc") or ""
                return f"{r['example_id'][:20]} {stamp}"
            audio = "yes" if r["audio"].get("available") else "no"
            return f"{r['state']} · {r['correctness']} · audio {audio}"
        return VIEW_TITLES[VIEWS[int(row)]]

    def tableView_shouldSelectRow_(self, table, row):
        if table is getattr(self, "history_table", None):
            return not self._history_flat[int(row)].get("__group__")
        return True

    def tableViewSelectionDidChange_(self, note):
        if self._suppress_select or getattr(self, "_building", False):
            return
        table = note.object()
        if table is getattr(self, "history_table", None):
            row = self.history_table.selectedRow()
            if 0 <= row < len(self._history_flat):
                entry = self._history_flat[row]
                if not entry.get("__group__"):
                    self.state.select_history_row(entry["kind"],
                                                  entry["id"])
        elif table is getattr(self, "training_table", None):
            row = self.training_table.selectedRow()
            rows = (self.state.views["models"].get("data")
                    or {}).get("examples") or []
            if 0 <= row < len(rows):
                self.state.select_training_example(
                    rows[row]["example_id"])
        elif table is self.sidebar:
            row = self.sidebar.selectedRow()
            if row >= 0:
                self._select_view_index(int(row))

    # ---- History view -----------------------------------------------------------

    @objc.python_method
    def _build_history_view(self):
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.history_search = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(8, ch - 28, 260, 24))
        self.history_search.setTarget_(self)
        self.history_search.setAction_("historySearchChanged:")
        self.history_search.setPlaceholderString_("Search text")
        v.addSubview_(self.history_search)
        v.addSubview_(_button("Reload", self, "historyReload:",
                              NSMakeRect(274, ch - 29, 90, 24)))
        self.history_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw * 0.42, 10))
        for ident, width in (("when", 100.0), ("what", 300.0)):
            c = NSTableColumn.alloc().initWithIdentifier_(ident)
            c.setWidth_(width)
            self.history_table.addTableColumn_(c)
        self.history_table.setDataSource_(self)
        self.history_table.setDelegate_(self)
        self.history_table.setAutoresizingMask_(2)
        list_scroll = _scroll(NSMakeRect(0, 36, cw * 0.45, ch - 40),
                              self.history_table)
        list_scroll.setAutoresizingMask_(18)
        v.addSubview_(list_scroll)
        self.history_detail = _textview(NSMakeRect(0, 0, cw * 0.5, 100))
        detail_scroll = _scroll(NSMakeRect(cw * 0.46, 36,
                                           cw * 0.54 - 8, ch - 72),
                                self.history_detail)
        detail_scroll.setAutoresizingMask_(18 | 16)
        v.addSubview_(detail_scroll)
        # Action row: fit the five buttons into the detail column's
        # width (clamped so nothing clips at the 900×620 minimum).
        avail = max(cw * 0.54 - 16, 5 * 70)
        bw = min(130.0, (avail - 4 * 8) / 5)
        for i, (title, action) in enumerate((
                ("Replay", "historyReplay:"),
                ("Copy", "historyCopy:"),
                ("Paste Again", "historyPasteAgain:"),
                ("Retry", "historyRetry:"),
                ("Diff", "historyDiff:"))):
            v.addSubview_(_button(title, self, action,
                                  NSMakeRect(cw * 0.46 + i * (bw + 8), 4,
                                             bw, 24)))
        return v

    def historySearchChanged_(self, sender):
        self.state.set_history_search(sender.stringValue() or "")

    def historyReload_(self, sender):
        self.state.reload_history()

    def historyReplay_(self, sender):
        detail = self.state.views["history"].get("detail")
        audio = (detail or {}).get("audio") or {}
        if self.replay is None:
            return
        out = self.replay.play_artifact(self.spec["store"],
                                        audio.get("artifact_id"))
        if not out.get("available"):
            # Parity with the training view: an unavailable replay says
            # why instead of looking like a dead button.
            self.history_detail.setString_(
                (self._render_history_detail(detail) or "")
                + f"\n\nreplay unavailable ({out.get('reason')})")

    def historyCopy_(self, sender):
        text = self._current_detail_text()
        if text and self.coordinator is not None:
            self.coordinator.hubCopyText(text)

    def historyPasteAgain_(self, sender):
        detail = self.state.views["history"].get("detail") or {}
        text = self._current_detail_text()
        if text and self.coordinator is not None:
            # The job id rides along so the re-paste keeps its insertion
            # attribution (contracts/insertion.md); legacy rows pass None.
            self.coordinator.hubPasteText(
                text, job_id=detail.get("job_id"))

    def historyRetry_(self, sender):
        detail = self.state.views["history"].get("detail")
        if detail and detail.get("job_id") \
                and self.coordinator is not None:
            self.coordinator.hubRetryJob(detail["job_id"])

    def historyDiff_(self, sender):
        detail = self.state.views["history"].get("detail") or {}
        stages = detail.get("lineage") or []

        def text_of(stage_name):
            for s in stages:
                if s["stage"] == stage_name:
                    art = s.get("artifact")
                    return art.get("text") if art else None
            return None
        self.history_detail.setString_(
            (self._render_history_detail(detail) or "")
            + "\n\n— diff source → cleaned —\n"
            + _stage_diff(text_of("source"), text_of("cleaned")))

    @objc.python_method
    def _current_detail_text(self):
        detail = self.state.views["history"].get("detail") or {}
        for stage in detail.get("lineage") or []:
            art = stage.get("artifact")
            if stage["stage"] == "cleaned" and art and art.get("text"):
                return art["text"]
        for stage in detail.get("lineage") or []:
            art = stage.get("artifact")
            if stage["stage"] == "source" and art and art.get("text"):
                return art["text"]
        return None

    @objc.python_method
    def _render_history_detail(self, detail):
        if detail is None:
            return "Select a row to see its lineage, outcome and actions."
        lines = []
        if detail.get("time_quality") == "unknown":
            lines.append("date: Undated (imported legacy record)")
        elif detail.get("captured_at_utc"):
            lines.append(f"captured (UTC): {detail['captured_at_utc']}"
                         f"  attempt {detail.get('attempt')}")
        if detail.get("app"):
            lines.append(f"app: {detail['app']}")
        if detail.get("state"):
            reason = detail.get("state_reason")
            lines.append(f"state: {detail['state']}"
                         + (f" ({reason})" if reason else ""))
        ins = detail.get("insertion")
        if ins:
            lines.append(f"insertion: {ins.get('state')}"
                         f" via {ins.get('method')}"
                         + (f" — {ins.get('reason_code')}"
                            if ins.get("reason_code") else ""))
        audio = detail.get("audio") or {}
        lines.append("audio: "
                     + ("available" if audio.get("available")
                        else f"unavailable ({audio.get('reason')})"))
        for stage in detail.get("lineage") or []:
            art = stage.get("artifact")
            if art is None:
                lines.append(f"\n── {stage['label']} ──\n"
                             f"({stage.get('reason', 'not captured')})")
            elif not art.get("present"):
                lines.append(f"\n── {stage['label']} ──\n"
                             f"(content expired)")
            else:
                lines.append(f"\n── {stage['label']} ──\n"
                             f"{art.get('text') or '(empty)'}")
        return "\n".join(lines)

    @objc.python_method
    def _refresh_history_view(self):
        view = self.state.views["history"]
        data = view.get("data")
        if data:
            flat = []
            for group in data["groups"]:
                flat.append({"__group__": group["label"]})
                flat.extend(group["rows"])
            self._history_flat = flat
            self.history_table.reloadData()
            # Preserve selection (AC04): reselect the same row id; a
            # refresh never jumps to the newest row.
            sel = view.get("selected_id")
            for i, entry in enumerate(flat):
                if not entry.get("__group__") and entry["id"] == sel:
                    self._suppress_select = True
                    try:
                        self.history_table\
                            .selectRowIndexes_byExtendingSelection_(
                                Foundation.NSIndexSet.indexSetWithIndex_(i),
                                False)
                    finally:
                        self._suppress_select = False
                    break
        if view.get("error"):
            self.history_detail.setString_(f"query failed: {view['error']}")
        elif not data and not view.get("loading"):
            self.history_detail.setString_(
                "No history yet — dictations appear here.")
        else:
            self.history_detail.setString_(
                self._render_history_detail(view.get("detail")))

    # ---- Diagnostics ----------------------------------------------------------------

    @objc.python_method
    def _build_diagnostics_view(self):
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.diag_job_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(8, ch - 28, 220, 22))
        self.diag_job_field.setPlaceholderString_("filter by job id")
        self.diag_job_field.setTarget_(self)
        self.diag_job_field.setAction_("diagnosticsFiltersChanged:")
        v.addSubview_(self.diag_job_field)
        self.diag_level = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(236, ch - 29, 120, 24))
        self.diag_level.addItemsWithTitles_(
            ["All levels", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.diag_level.setTarget_(self)
        self.diag_level.setAction_("diagnosticsFiltersChanged:")
        v.addSubview_(self.diag_level)
        self.diag_utc = NSButton.alloc().init()
        self.diag_utc.setButtonType_(NSSwitchButton)
        self.diag_utc.setTitle_("UTC")
        self.diag_utc.setTarget_(self)
        self.diag_utc.setAction_("diagnosticsFiltersChanged:")
        self.diag_utc.setFrame_(NSMakeRect(364, ch - 28, 70, 22))
        v.addSubview_(self.diag_utc)
        v.addSubview_(_button("Export Redacted…", self,
                              "diagnosticsExport:",
                              NSMakeRect(444, ch - 29, 150, 24)))
        self.diag_text = _textview(NSMakeRect(0, 0, cw - 16, 100))
        sc = _scroll(NSMakeRect(8, 8, cw - 16, ch - 44), self.diag_text)
        sc.setAutoresizingMask_(18 | 16)
        v.addSubview_(sc)
        return v

    def diagnosticsFiltersChanged_(self, sender):
        level = self.diag_level.indexOfSelectedItem()
        self.state.set_diagnostics_filters(
            job=self.diag_job_field.stringValue() or "",
            level=(None if level == 0
                   else self.diag_level.titleOfSelectedItem()),
            utc=bool(self.diag_utc.state()))

    def diagnosticsExport_(self, sender):
        from .. import diagnostics as diag
        spec = self.state.diagnostics_provider() or {}
        view = self.state.views["diagnostics"]
        # The export is bounded to the same filtered window the view
        # displays (the event log caps at 100 MiB — an unbounded parse
        # on the UI thread would freeze the app).
        records = diag.load_events(
            spec.get("events_dir"), job_id=view["job_filter"] or None,
            level=view["level_filter"], last=spec.get("last", 500))
        try:
            from AppKit import NSSavePanel
            panel = NSSavePanel.savePanel()
            panel.setAllowedFileTypes_(["jsonl"])
            if panel.runModal() != 1 or panel.URL() is None:
                return
            path = panel.URL().path()
        except Exception:
            return
        n = diag.redacted_export(records, path)
        self.diag_text.setString_(
            f"wrote {n} redacted events (filtered window,"
            f" newest {spec.get('last', 500)}) to {path}")

    @objc.python_method
    def _refresh_diagnostics_view(self):
        view = self.state.views["diagnostics"]
        data = view.get("data")
        if view.get("error"):
            self.diag_text.setString_(f"query failed: {view['error']}")
            return
        if not data:
            self.diag_text.setString_(
                "No events loaded. Set filters and reload.")
            return
        lines = ["— engines / build —"]
        for k, val in sorted((data.get("engine") or {}).items()):
            lines.append(f"{k}: {val}")
        timeline = data.get("timeline") or []
        if timeline:
            lines.append("")
            lines.append(f"— job timeline ({view['job_filter']}) —")
            lines.extend(timeline)
        lines.append("")
        lines.append(f"— events ({data.get('count')}) —")
        lines.extend(data.get("events") or [])
        self.diag_text.setString_("\n".join(lines))

    # ---- Models / Training Data ---------------------------------------------------------

    @objc.python_method
    def _build_models_view(self):
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.models_tabs = NSSegmentedControl.alloc().init()
        self.models_tabs.setSegmentCount_(2)
        self.models_tabs.setLabel_forSegment_("Engines", 0)
        self.models_tabs.setLabel_forSegment_("Training Data", 1)
        self.models_tabs.setSegmentStyle_(NSSegmentStyleAutomatic)
        self.models_tabs.setTarget_(self)
        self.models_tabs.setAction_("modelsTabChanged:")
        self.models_tabs.setFrame_(NSMakeRect(8, ch - 28, 240, 24))
        v.addSubview_(self.models_tabs)
        self.models_text = _textview(NSMakeRect(0, 0, cw - 20, 100))
        sc = _scroll(NSMakeRect(8, 8, cw - 16, ch - 44), self.models_text)
        sc.setAutoresizingMask_(18 | 16)
        v.addSubview_(sc)
        self.training_pane = self._build_training_pane(cw, ch)
        v.addSubview_(self.training_pane)
        return v

    def modelsTabChanged_(self, sender):
        self.state.select_models_subview(
            "engines" if sender.selectedSegment() == 0 else "training")

    @objc.python_method
    def _build_training_pane(self, cw, ch):
        p = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, cw, ch))
        self.training_search = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(8, ch - 28, 240, 24))
        self.training_search.setTarget_(self)
        self.training_search.setAction_("trainingSearchChanged:")
        self.training_search.setPlaceholderString_("Search evidence")
        p.addSubview_(self.training_search)
        self.training_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw * 0.4, 10))
        for ident, width in (("ex", 190.0), ("st", 170.0)):
            c = NSTableColumn.alloc().initWithIdentifier_(ident)
            c.setWidth_(width)
            self.training_table.addTableColumn_(c)
        self.training_table.setDataSource_(self)
        self.training_table.setDelegate_(self)
        tsc = _scroll(NSMakeRect(0, 150, cw * 0.42, ch - 182),
                      self.training_table)
        tsc.setAutoresizingMask_(18)
        p.addSubview_(tsc)
        self.training_detail = _textview(NSMakeRect(0, 0, cw * 0.5, 100))
        dsc = _scroll(NSMakeRect(cw * 0.44, 150, cw * 0.56 - 8, ch - 182),
                      self.training_detail)
        dsc.setAutoresizingMask_(18 | 16)
        p.addSubview_(dsc)
        self.training_ready = _label(NSMakeRect(8, ch - 56, cw - 16, 20),
                                      "")
        p.addSubview_(self.training_ready)
        for i, (title, action) in enumerate((
                ("Mark Correct", "trainingMarkCorrect:"),
                ("Mark Incorrect", "trainingMarkIncorrect:"),
                ("Pin/Unpin", "trainingPin:"),
                ("Exclude/Include", "trainingExclude:"),
                ("Delete Everywhere", "trainingDelete:"))):
            p.addSubview_(_button(title, self, action,
                                  NSMakeRect(8 + i * 150, 118, 144, 24)))
        p.addSubview_(_label(NSMakeRect(8, 92, 150, 18),
                             "Verbatim (replay first):"))
        self.verbatim_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(160, 90, 300, 22))
        p.addSubview_(self.verbatim_field)
        p.addSubview_(_button("Save Verbatim", self, "trainingVerbatim:",
                              NSMakeRect(468, 89, 130, 24)))
        p.addSubview_(_button("Replay Audio", self, "trainingReplay:",
                              NSMakeRect(606, 89, 120, 24)))
        p.addSubview_(_label(NSMakeRect(8, 64, 150, 18),
                             "Span correction:"))
        self.span_start = NSTextField.alloc().initWithFrame_(
            NSMakeRect(160, 62, 48, 22))
        self.span_start.setPlaceholderString_("start")
        self.span_end = NSTextField.alloc().initWithFrame_(
            NSMakeRect(214, 62, 48, 22))
        self.span_end.setPlaceholderString_("end")
        self.span_stage = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(268, 61, 130, 24))
        self.span_stage.addItemsWithTitles_(["source_text",
                                             "applied_output"])
        self.span_corrected = NSTextField.alloc().initWithFrame_(
            NSMakeRect(404, 62, 240, 22))
        self.span_corrected.setPlaceholderString_("corrected text")
        for sub in (self.span_start, self.span_end, self.span_stage,
                    self.span_corrected):
            p.addSubview_(sub)
        p.addSubview_(_button("Save Span", self, "trainingSpan:",
                              NSMakeRect(650, 61, 110, 24)))
        return p

    def trainingSearchChanged_(self, sender):
        self.state.set_training_search(sender.stringValue() or "")

    @objc.python_method
    def _selected_example_id(self):
        return self.state.views["models"].get("selected_id")

    def _training_action(self, fn, *args):
        """Run one inspector mutation; store stalls surface as text
        instead of escaping the action handler."""
        try:
            return fn(*args)
        except Exception as e:
            self.training_detail.setString_(
                f"action failed: {type(e).__name__}")
            return None

    def trainingMarkCorrect_(self, sender):
        ex = self._selected_example_id()
        if ex and self._training_action(
                self.spec["training_service"].mark_intended, ex, True) \
                is not None:
            self.state.select_training_example(ex)

    def trainingMarkIncorrect_(self, sender):
        ex = self._selected_example_id()
        if ex and self._training_action(
                self.spec["training_service"].mark_intended, ex, False) \
                is not None:
            self.state.select_training_example(ex)

    def trainingPin_(self, sender):
        ex = self._selected_example_id()
        detail = self.state.views["models"].get("detail") or {}
        if ex and self._training_action(
                self.spec["training_service"].pin, ex,
                not detail.get("pinned")) is not None:
            self.state.select_training_example(ex)

    def trainingExclude_(self, sender):
        ex = self._selected_example_id()
        detail = self.state.views["models"].get("detail") or {}
        if ex and self._training_action(
                self.spec["training_service"].exclude, ex,
                detail.get("state") != "excluded") is not None:
            self.state.select_training_example(ex)

    def trainingDelete_(self, sender):
        ex = self._selected_example_id()
        if not ex:
            return
        try:
            from AppKit import NSAlert
            alert = NSAlert.alertWithMessageText_defaultButton_alternateButton_otherButton_informativeTextWithFormat_(
                "Delete this example everywhere?",
                "Delete", "Cancel", None,
                "Revokes every lease and purges audio, transcripts and "
                "derived records. Only a content-free tombstone remains.")
            if alert.runModal() != 1000:  # NSAlertDefaultReturn
                return
        except Exception:
            pass  # headless/test path: the guarded action runs directly
        self._delete_example()

    @objc.python_method
    def _delete_example(self):
        ex = self._selected_example_id()
        if not ex:
            return
        if self._training_action(
                self.spec["training_service"].delete_everywhere, ex) \
                is None:
            return
        self.state.views["models"]["selected_id"] = None
        self.state.reload_training()

    def trainingReplay_(self, sender):
        detail = self.state.views["models"].get("detail") or {}
        audio = detail.get("audio") or {}
        if self.replay is None or not audio.get("available"):
            self.training_detail.setString_(
                "audio unavailable ("
                + (audio.get("reason") or "no artifact") + ")")
            return
        out = self.replay.play_artifact(self.spec["store"],
                                        audio.get("artifact_id"))
        if out.get("status") == "playing":
            # The verbatim gate opens only for THIS example's real
            # playback (E14) — the flag is bound to the example id, so
            # replaying one example never certifies another.
            if detail.get("example_id") == self._selected_example_id():
                self.state.views["models"]["listened_for"] = \
                    detail.get("example_id")
        else:
            self.training_detail.setString_(
                "replay unavailable (" + str(out.get("reason")) + ")")

    def trainingVerbatim_(self, sender):
        ex = self._selected_example_id()
        text = self.verbatim_field.stringValue() or ""
        if not ex or not text:
            return
        listened = (self.state.views["models"].get("listened_for") == ex)
        try:
            self.spec["training_service"].set_verbatim(
                ex, text, listened_audio=listened)
        except ValueError as e:
            self.training_detail.setString_(
                f"verbatim not saved: {e} — replay this example's audio"
                " first")
            return
        except Exception as e:  # store stall etc. — surfaced, never lost
            self.training_detail.setString_(
                f"verbatim not saved: {type(e).__name__}")
            return
        self.state.views["models"]["listened_for"] = None
        self.state.select_training_example(ex)

    def trainingSpan_(self, sender):
        ex = self._selected_example_id()
        try:
            start = int(self.span_start.stringValue())
            end = int(self.span_end.stringValue())
        except ValueError:
            self.training_detail.setString_(
                "span start/end must be code-point integers")
            return
        corrected = self.span_corrected.stringValue() or ""
        stage = self.span_stage.titleOfSelectedItem() or "source_text"
        if not ex or not corrected:
            return
        try:
            self.spec["training_service"].add_span_correction(
                ex, stage, start, end, corrected)
        except ValueError as e:
            self.training_detail.setString_(f"span not saved: {e}")
            return
        except Exception as e:
            self.training_detail.setString_(
                f"span not saved: {type(e).__name__}")
            return
        self.state.select_training_example(ex)

    @objc.python_method
    def _refresh_models_view(self):
        view = self.state.views["models"]
        is_training = view.get("subview", "engines") == "training"
        self.training_pane.setHidden_(not is_training)
        self.models_text.setHidden_(is_training)
        self.models_tabs.setSelectedSegment_(1 if is_training else 0)
        if is_training:
            data = view.get("data") or {}
            rows = data.get("examples") or []
            self.training_table.reloadData()
            ready = data.get("readiness") or {}
            cov = ready.get("dataset_coverage") or {}
            self.training_ready.setStringValue_(
                f"{len(rows)} examples · audio "
                f"{cov.get('retained_audio_examples')} · verbatim "
                f"{cov.get('verbatim_reviewed_examples')} · spans "
                f"{cov.get('span_annotations')} · unreviewed "
                f"{cov.get('unreviewed_outcomes')} · storage "
                f"{(ready.get('storage_bytes') or 0) // 1024} KiB")
            self.training_detail.setString_(
                self._render_training_detail(view.get("detail")))
        else:
            block = (view.get("data") or {}).get("engine") or {}
            lines = ["— engines / build —"]
            lines += [f"{k}: {v}" for k, v in sorted(block.items())]
            caps = self.spec.get("capabilities") or {}
            if caps:
                lines.append("\n— ASR capabilities (S30.1) —")
                for name, c in sorted(
                        (caps.get("capabilities") or {}).items()):
                    lines.append(f"{name}: {c}")
            if len(lines) > 1:
                self.models_text.setString_("\n".join(lines))
            else:
                self.models_text.setString_(
                    "Engine states load when the view opens.")

    @objc.python_method
    def _render_training_detail(self, detail):
        if detail is None:
            return ("Select an example to inspect stages, completeness"
                    " and annotations.")
        lines = [f"example {detail['example_id']}",
                 f"job {detail.get('job_id')} · state {detail['state']}"
                 f" · pinned {detail.get('pinned')}",
                 f"captured {detail.get('captured_at_utc')}"
                 f" (quality {detail.get('time_quality')},"
                 f" attempt {detail.get('attempt')})",
                 f"insertion {detail.get('insertion')} ·"
                 f" correctness {detail.get('correctness')}",
                 f"cleanup path {detail.get('cleanup_path')}",
                 f"families present: {', '.join(detail.get('families'))}"
                 + " — missing: "
                 + ", ".join(f"{k} ({v})" for k, v in
                             sorted((detail.get("missing_reasons")
                                     or {}).items()))]
        audio = detail.get("audio") or {}
        lines.append("audio: " + ("available" if audio.get("available")
                                  else f"unavailable"
                                    f" ({audio.get('reason')})"))
        ctx = detail.get("context_block") or {}
        if ctx.get("present"):
            dest = json.dumps(ctx.get("destination"), sort_keys=True)
            lines.append(f"context: {dest}")
        else:
            lines.append(f"context: absent ({ctx.get('reason')})")
        for stage in detail.get("stages") or []:
            if stage.get("available"):
                lines.append(f"\n── {stage['label']} ──\n{stage['text']}")
            else:
                lines.append(f"\n── {stage['label']} ──\n"
                             f"({stage.get('reason')})")
        anns = detail.get("annotations") or []
        if anns:
            lines.append("\n— annotations —")
            for a in anns:
                lines.append(
                    f"{a.get('kind')} · coverage {a.get('coverage')}"
                    f" · listened {a.get('listened_audio')}")
        chain = detail.get("revision_chain") or []
        lines.append(f"\n{len(chain)} revisions"
                     f" (latest {chain[-1]['revision_id'] if chain else None})")
        return "\n".join(lines)

    # ---- Home -------------------------------------------------------------------------------

    @objc.python_method
    def _build_home_view(self):
        v = NSView.alloc().init()
        self.home_text = _textview(NSMakeRect(0, 0, 100, 100))
        sc = _scroll(NSMakeRect(8, 8,
                                self.content.bounds().size.width - 16,
                                self.content.bounds().size.height - 16),
                     self.home_text)
        sc.setAutoresizingMask_(18 | 16)
        v.addSubview_(sc)
        return v

    @objc.python_method
    def _refresh_home_view(self):
        view = self.state.views["home"]
        data = view.get("data")
        if view.get("error") or not data:
            self.home_text.setString_(
                f"Home unavailable ({view.get('error') or 'loading'}).")
            return
        s = data.get("summary") or {}
        engine = data.get("engine") or {}
        rec = data.get("recovery") or {}
        last = s.get("last_dictation") or {}
        lines = [
            "LocalFlow",
            "",
            f"ASR: {engine.get('asr', 'unknown')}"
            f" · Cleanup: {engine.get('cleanup', 'unknown')}",
            f"Today: {s.get('today_count', 0)} dictations"
            f" · {s.get('total_jobs', 0)} total"
            f" · {s.get('legacy_rows', 0)} imported legacy rows",
            "Last dictation: "
            + (f"{last.get('date_iso')} ({last.get('state')})"
               if last else "none yet"),
            "",
            "Recovery: "
            + ("a failed dictation is available for retry"
               if rec.get("last_failed") or rec.get("recoverable")
               else "nothing to recover"),
            "",
            "Hold the dictation key and speak; release to insert.",
            "Open History to search, replay and re-paste past work.",
        ]
        self.home_text.setString_("\n".join(lines))

    # ---- Settings ------------------------------------------------------------------------------

    @objc.python_method
    def _build_settings_view(self):
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.settings_text = _label(NSMakeRect(8, ch - 26, cw - 16, 20),
                                    "")
        v.addSubview_(self.settings_text)
        y = ch - 66
        v.addSubview_(_label(NSMakeRect(8, y + 3, 200, 18),
                             "Collect training evidence:"))
        for i, (title, action) in enumerate((
                ("Enable", "settingsCollectEnable:"),
                ("Pause", "settingsCollectPause:"),
                ("Disable", "settingsCollectDisable:"))):
            v.addSubview_(_button(title, self, action,
                                  NSMakeRect(216 + i * 110, y - 1, 104, 24)))
        y -= 40
        v.addSubview_(_label(
            NSMakeRect(8, y + 3, 290, 34),
            "Retention (days): transcript · audio ok · audio failed ·"
            " metadata · training buffer"))
        self.retention_fields = []
        for i in range(5):
            f = NSTextField.alloc().initWithFrame_(
                NSMakeRect(304 + i * 64, y, 56, 22))
            v.addSubview_(f)
            self.retention_fields.append(f)
        v.addSubview_(_button("Apply Retention", self,
                              "settingsApplyRetention:",
                              NSMakeRect(640, y - 1, 140, 24)))
        note = _label(NSMakeRect(8, y - 40, cw - 16, 60),
                      "Store retention applies immediately. Event-log"
                      " retention takes effect at next launch. Models,"
                      " hotkey and capture behavior live in config.json.")
        v.addSubview_(note)
        return v

    def settingsCollectEnable_(self, sender):
        self._set_collection("enabled")

    def settingsCollectPause_(self, sender):
        self._set_collection("paused")

    def settingsCollectDisable_(self, sender):
        self._set_collection("disabled")

    @objc.python_method
    def _set_collection(self, new_state):
        if self.coordinator is not None:
            self.coordinator.hubSetCollection(new_state)
        self.state.reload_current()

    def settingsApplyRetention_(self, sender):
        values = []
        for f in self.retention_fields:
            try:
                values.append(max(1, int(f.stringValue())))
            except (ValueError, TypeError):
                self.settings_text.setStringValue_(
                    "retention values must be whole days")
                return
        if self.coordinator is not None and len(values) == 5:
            self.coordinator.hubApplyRetention(values)
        self.state.reload_current()

    @objc.python_method
    def _refresh_settings_view(self):
        view = self.state.views["settings"]
        data = view.get("data") or {}
        self.settings_text.setStringValue_(
            f"Collection: {data.get('collection_state', 'unknown')}")
        ret = data.get("retention") or {}
        keys = ("transcript", "audio_success", "audio_failed",
                "metadata", "training_buffer")
        for f, key in zip(self.retention_fields, keys):
            if not f.stringValue():
                f.setStringValue_(str(ret.get(key, "")))
