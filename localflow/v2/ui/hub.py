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
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertStyleWarning,
    NSApp,
    NSApplication,
    NSBackingStoreBuffered,
    NSButton,
    NSFont,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
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


def _ensure_edit_menu():
    """Text fields and text views take ⌘A/⌘C/⌘V/⌘X/⌘Z from the
    application's Edit menu (standard selectors sent down the responder
    chain). A menu-bar-only app has no main menu, so those keys did
    nothing in any Hub field (M10-AUDIT-26); the Hub installs a minimal
    Edit menu when the app has none. An accessory app shows no menu bar
    — only the key equivalents take effect."""
    app = NSApplication.sharedApplication()
    if app.mainMenu() is not None:
        return
    main = NSMenu.alloc().init()
    top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Edit", None, "")
    edit = NSMenu.alloc().initWithTitle_("Edit")
    for title, action, key in (("Undo", "undo:", "z"),
                               ("Redo", "redo:", "Z"),
                               ("Cut", "cut:", "x"),
                               ("Copy", "copy:", "c"),
                               ("Paste", "paste:", "v"),
                               ("Select All", "selectAll:", "a")):
        edit.addItem_(NSMenuItem.alloc()
                      .initWithTitle_action_keyEquivalent_(
                          title, action, key))
    top.setSubmenu_(edit)
    main.addItem_(top)
    app.setMainMenu_(main)


def _refusal_text(e):
    """A service refusal's reason, or None. Raised inside a writer op it
    reaches the caller as the store's ``RuntimeError('ValueError: …')``;
    refusal reasons are content-free ids/states by contract, so they are
    shown — any other failure shows its type only."""
    msg = str(e)
    if isinstance(e, ValueError):
        return msg
    if isinstance(e, RuntimeError) and msg.startswith("ValueError: "):
        return msg[len("ValueError: "):]
    return None


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
            coordinator=self.coordinator,
            styles_service=spec.get("styles_service"),
            snippets_service=spec.get("snippets_service"),
            transforms_service=spec.get("transforms_service"),
            notes_service=spec.get("notes_service"),
            insights_service=spec.get("insights_service"),
            learning_service=spec.get("learning_service"),
            review_service=spec.get("review_service"),
            sampling_service=spec.get("sampling_service"),
            splits_service=spec.get("splits_service"),
            profile_service=spec.get("profile_service"),
            export_service=spec.get("export_service"),
            transforms_store=spec.get("transforms_store"))
        self.state.on_update = self._state_updated
        self.state.on_revoked = self._state_revoked
        self.state.on_revalidated = self._state_revalidated
        self._built_views = {}
        self._history_flat = []  # group markers + rows, in table order
        # What each pane last RENDERED (main thread only): actions bind
        # to these snapshots — a table row index names the row the user
        # sees, and a detail action acts only on the rendered detail of
        # the selected item (M09-AUDIT-01).
        self._rendered = {}
        self._rendered_rows = {}
        self._editor_bound = None  # example the Training editors belong to
        self._teach_key = None  # History row the teach buffer belongs to
        self._pending_annotation = None  # unknown-outcome save to reuse
        # M10 editors (bound id, revision, baseline form) and adds whose
        # outcome was unknown (their pre-allocated id is reused by a
        # retry of the same form — never a duplicate rule).
        self._style_editor = None
        self._snippet_editor = None
        self._pending_adds = {}
        self._action_seq = 0
        self._action_tokens = {}
        self._action_notes = {}
        self._suppress_select = False
        self._building = True
        # Delete-everywhere revokes the Hub's cached payload and replay
        # (store deletion listener: writer thread, flags only).
        store = spec.get("store")
        if store is not None and hasattr(store, "add_job_deletion_listener"):
            store.add_job_deletion_listener(self._store_job_deleted)
        self._build_window()
        self._building = False
        return self

    # ---- revocation (delete-everywhere) -----------------------------------

    @objc.python_method
    def _store_job_deleted(self, job_id):
        """Store listener, inside the delete op on the writer thread:
        flag-only revocation of cached state and replay; the rendered
        widgets are cleared on the main thread."""
        self.state.revoke_job(job_id)
        replay = self.replay
        if replay is not None and hasattr(replay, "revoke_job") \
                and replay.revoke_job(job_id):
            AppHelper.callAfter(replay.stop_revoked)

    @objc.python_method
    def _state_revoked(self, job_id):
        AppHelper.callAfter(self._revoke_rendered, job_id)

    @objc.python_method
    def _state_revalidated(self):
        AppHelper.callAfter(self._revalidate_rendered)

    @objc.python_method
    def _revalidate_rendered(self):
        """Main thread, after a retention pass: audio it purged stops
        playing and its buffer is released."""
        store = self.spec.get("store")
        if self.replay is not None and store is not None and \
                hasattr(self.replay, "stop_unavailable"):
            self.replay.stop_unavailable(store)

    @objc.python_method
    def _revoke_rendered(self, job_id):
        """Main thread: nothing the user can see or act on still carries
        the deleted job's text."""
        hist = self._rendered.get("history_detail")
        if hist is not None and hist.get("job_id") == job_id:
            self._rendered["history_detail"] = None
        # Keyed on the row, not the rendered detail: a refresh queued by
        # the same revocation may already have cleared that.
        if self._teach_key == ("job", job_id) and \
                hasattr(self, "teach_field"):
            self.teach_field.setStringValue_("")
        train = self._rendered.get("training_detail")
        if train is not None and train.get("job_id") == job_id:
            self._rendered["training_detail"] = None
            self._clear_training_editors()
            # The Models refresh below redraws only the subview on
            # screen; a hidden Training detail is cleared here.
            if getattr(self, "training_detail", None) is not None:
                self.training_detail.setString_(self._training_pane_text())
        queue = self._rendered_rows.get("review_queue") or []
        if any(r.get("job_id") == job_id for r in queue):
            # A rendered Review queue listing the job (on screen or not)
            # drops its text and rows; it reloads when the tab is shown,
            # and Approve/Reject refuse until then.
            self._rendered_rows["review_queue"] = None
            self._rendered["review_queue_src"] = None
            if getattr(self, "review_text", None) is not None:
                self.review_text.setString_(
                    "A dictation in this queue was deleted; the queue"
                    " reloads when this tab is shown.")
        if self._rendered.get("voice") and \
                self.state.views["insights"].get("data") is None:
            # The state dropped the cached profile (it may draw on the
            # deleted dictation); the pane stops showing it.
            self._rendered["voice"] = False
            self.voice_pane.text.setString_(
                "The profile shown here drew on a deleted dictation and"
                " was cleared. Generate again for a current profile.")
            if self.state.selected_view == "insights":
                self.state.reload_insights()
        if self._pending_annotation is not None and \
                self._pending_annotation.get("job_id") == job_id:
            self._pending_annotation = None
        if "history" in self._built_views:
            self._refresh_history_view()
        if "models" in self._built_views:
            self._refresh_models_view()
        if self.replay is not None and hasattr(self.replay, "stop_revoked"):
            self.replay.stop_revoked()

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
        # coordinator's ⌘1..⌘7 menu equivalents land on the same state.
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
        _ensure_edit_menu()
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
        pane = self._built_views[view]
        # Every pane fills the content area it is shown in and follows it
        # on resize (M10-AUDIT-26): a pane created with init() has a zero
        # frame, and a view hit-tests only inside its own frame — its
        # controls drew, but no click reached them. The children keep
        # exactly the layout they were built with: sizing the pane must
        # not autoresize them (their masks assumed a different origin).
        pane.setAutoresizesSubviews_(False)
        pane.setFrame_(self.content.bounds())
        pane.setAutoresizingMask_(18)  # width + height flexible
        for sub in list(self.content.subviews()):
            sub.removeFromSuperview()
        self.content.addSubview_(pane)
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

    # Rendered row snapshots per table: (view, data key). A table only
    # ever indexes the list it last rendered (``_render_rows``).
    _TABLE_ROWS = {"training_table": ("models", "examples"),
                   "styles_table": ("styles", "rules"),
                   "snippets_table": ("snippets", "snippets"),
                   "transforms_table": ("transforms", "transforms"),
                   "scratchpad_table": ("scratchpad", "notes"),
                   "insights_table": ("insights", "daily")}

    @objc.python_method
    def _table_name(self, table):
        for name in self._TABLE_ROWS:
            if table is getattr(self, name, None):
                return name
        return None

    @objc.python_method
    def _render_rows(self, name, id_key=None, selected=None):
        """Snapshot the state's rows for ``name``, reload the table from
        that snapshot and reselect the stable ``selected`` id (or clear
        the selection when that row is gone) — a refresh never leaves
        the highlight on a different item than the one acted on."""
        view, key = self._TABLE_ROWS[name]
        rows = list(((self.state.views[view].get("data") or {})
                     .get(key)) or [])
        self._rendered_rows[name] = rows
        table = getattr(self, name)
        table.reloadData()
        if id_key is None:
            return rows
        idx = next((i for i, r in enumerate(rows)
                    if r.get(id_key) == selected), None)
        self._suppress_select = True
        try:
            if idx is None:
                table.deselectAll_(None)
            else:
                table.selectRowIndexes_byExtendingSelection_(
                    Foundation.NSIndexSet.indexSetWithIndex_(idx), False)
        finally:
            self._suppress_select = False
        return rows

    @objc.python_method
    def _rows_of(self, table):
        name = self._table_name(table)
        return self._rendered_rows.get(name) or [] if name else []

    def numberOfRowsInTableView_(self, table):
        if table is getattr(self, "history_table", None):
            return len(self._history_flat)
        if self._table_name(table) is not None:
            return len(self._rows_of(table))
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
            rows = self._rows_of(table)
            r = rows[int(row)]
            if col.identifier() == "ex":
                stamp = r.get("captured_at_utc") or ""
                return f"{r['example_id'][:20]} {stamp}"
            audio = "yes" if r["audio"].get("available") else "no"
            return f"{r['state']} · {r['correctness']} · audio {audio}"
        if table is getattr(self, "styles_table", None):
            rows = self._rows_of(table)
            r = rows[int(row)]
            if col.identifier() == "mode":
                return f"{r['mode']} · {r['number_policy']}" \
                    + ("" if r.get("enabled") else " · off")
            return f"{r['name']} ({r['scope'][0]}" \
                + (f": {r['scope'][1]}" if r["scope"][1] else "") + ")"
        if table is getattr(self, "snippets_table", None):
            rows = self._rows_of(table)
            r = rows[int(row)]
            if col.identifier() == "kind":
                return r["kind"] + ("" if r.get("enabled") else " · off")
            return r["trigger"]
        if table is getattr(self, "transforms_table", None):
            rows = self._rows_of(table)
            r = rows[int(row)]
            if col.identifier() == "mode":
                auto = "auto-apply" if r.get("auto_apply") else "manual"
                return (f"{r['mode']} · {auto}"
                        + ("" if r.get("enabled") else " · off"))
            return r["name"] + (" (legacy)" if r.get("origin") == "legacy"
                                else "")
        if table is getattr(self, "scratchpad_table", None):
            rows = self._rows_of(table)
            r = rows[int(row)]
            if col.identifier() == "words":
                return str(r.get("word_count", 0))
            return r.get("title") or "untitled"
        if table is getattr(self, "insights_table", None):
            rows = self._rows_of(table)
            r = rows[int(row)]
            key = col.identifier()
            if key == "day":
                return r["day"]
            if key == "dict":
                return str(r["dictations"])
            if key == "words":
                return str(r["final_words"])
            if key == "min":
                return f"{r['capture_seconds'] / 60.0:.1f}"
            if key == "tf":
                return "–" if r.get("transforms") is None else str(
                    r["transforms"])
            return str(r["fallbacks"])
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
            rows = self._rows_of(table)
            if 0 <= row < len(rows):
                self.state.select_training_example(
                    rows[row]["example_id"])
        elif table is getattr(self, "styles_table", None):
            row = self.styles_table.selectedRow()
            rows = self._rows_of(table)
            if 0 <= row < len(rows):
                r = rows[row]
                self.state.views["styles"]["selected_id"] = \
                    r["rule_id"]
                self._fill_style_editor(r)
        elif table is getattr(self, "snippets_table", None):
            row = self.snippets_table.selectedRow()
            rows = self._rows_of(table)
            if 0 <= row < len(rows):
                s = rows[row]
                self.state.views["snippets"]["selected_id"] = \
                    s["snippet_id"]
                self._fill_snippet_editor(s)
        elif table is getattr(self, "transforms_table", None):
            row = self.transforms_table.selectedRow()
            rows = self._rows_of(table)
            if 0 <= row < len(rows):
                t = rows[row]
                self.state.views["transforms"]["selected_id"] = \
                    t["transform_id"]
                self._fill_transform_editor(t)
        elif table is getattr(self, "scratchpad_table", None):
            row = self.scratchpad_table.selectedRow()
            rows = self._rows_of(table)
            if 0 <= row < len(rows):
                self.state.select_scratchpad_note(rows[row]["note_id"])
        elif table is self.sidebar:
            row = self.sidebar.selectedRow()
            if row >= 0:
                self._select_view_index(int(row))

    # ---- M10 editors: bound to the rendered row (M10-AUDIT-20) ------------
    #
    # An editor buffer belongs to the stable id and revision it was
    # filled from. Update writes ONLY the fields changed in the form
    # (the store merges them onto the writer-current row and validates
    # the result), so a stale form never overwrites a field it did not
    # touch; a row that disappears clears the editor.

    @objc.python_method
    def _fill_style_editor(self, r):
        self.style_name.setStringValue_(r.get("name") or "")
        scope = (r.get("scope") or ["global", None])
        self.style_scope.selectItemWithTitle_(scope[0])
        self.style_scope_value.setStringValue_(scope[1] or "")
        self.style_mode.selectItemWithTitle_(r.get("mode") or "clean")
        self.style_numbers.selectItemWithTitle_(
            r.get("number_policy") or "inherit")
        self._style_editor = {"id": r.get("rule_id"),
                              "revision": r.get("revision"),
                              "baseline": self._style_form()}

    @objc.python_method
    def _style_form(self):
        return {"name": self.style_name.stringValue() or "",
                "scope_kind": self.style_scope.titleOfSelectedItem()
                or "global",
                "scope_value": self.style_scope_value.stringValue() or None,
                "mode": self.style_mode.titleOfSelectedItem() or "clean",
                "number_policy": self.style_numbers.titleOfSelectedItem()
                or "inherit"}

    @objc.python_method
    def _clear_style_editor(self, note=None):
        self._style_editor = None
        self.state.views["styles"]["selected_id"] = None
        self.style_name.setStringValue_("")
        self.style_scope.selectItemWithTitle_("global")
        self.style_scope_value.setStringValue_("")
        self.style_mode.selectItemWithTitle_("clean")
        self.style_numbers.selectItemWithTitle_("inherit")
        if note:
            self.styles_status.setStringValue_(note)

    @objc.python_method
    def _fill_snippet_editor(self, s):
        self.snip_trigger.setStringValue_(s.get("trigger") or "")
        self.snip_name.setStringValue_(s.get("name") or "")
        self.snip_kind.selectItemWithTitle_(s.get("kind") or "plain")
        self.snip_rewrite.setState_(1 if s.get("allow_rewrite") else 0)
        self.snip_content.setString_(s.get("content") or "")
        self._snippet_editor = {"id": s.get("snippet_id"),
                                "revision": s.get("revision"),
                                "baseline": self._snippet_form()}

    @objc.python_method
    def _snippet_form(self):
        return {"trigger": self.snip_trigger.stringValue() or "",
                "name": self.snip_name.stringValue() or "",
                "kind": self.snip_kind.titleOfSelectedItem() or "plain",
                "content": self.snip_content.string() or "",
                "allow_rewrite": bool(self.snip_rewrite.state())}

    @objc.python_method
    def _clear_snippet_editor(self, note=None):
        self._snippet_editor = None
        self.state.views["snippets"]["selected_id"] = None
        self.snip_trigger.setStringValue_("")
        self.snip_name.setStringValue_("")
        self.snip_kind.selectItemWithTitle_("plain")
        self.snip_rewrite.setState_(0)
        self.snip_content.setString_("")
        if note:
            self.snippets_status.setStringValue_(note)

    @staticmethod
    def _row_form(view, r):
        """The editor-shaped values of a rendered row."""
        if view == "styles":
            scope = r.get("scope") or ["global", None]
            return {"name": r.get("name") or "", "scope_kind": scope[0],
                    "scope_value": scope[1] or None,
                    "mode": r.get("mode") or "clean",
                    "number_policy": r.get("number_policy") or "inherit"}
        return {"trigger": r.get("trigger") or "",
                "name": r.get("name") or "",
                "kind": r.get("kind") or "plain",
                "content": r.get("content") or "",
                "allow_rewrite": bool(r.get("allow_rewrite"))}

    @objc.python_method
    def _m10_target(self, view):
        """What an M10 action acts on: the SELECTED item as rendered —
        its editor binding when the editor was filled from it, else the
        rendered row itself (never an index, never a stale buffer)."""
        sel = self.state.views[view].get("selected_id")
        if not sel:
            return None
        editor = self._style_editor if view == "styles" \
            else self._snippet_editor
        if editor is not None and editor.get("id") == sel:
            return editor
        id_key = "rule_id" if view == "styles" else "snippet_id"
        row = next((r for r in self._rendered_rows.get(f"{view}_table", ())
                    if r.get(id_key) == sel), None)
        if row is None:
            return None
        return {"id": sel, "revision": row.get("revision"),
                "baseline": self._row_form(view, row)}

    @objc.python_method
    def _sync_editor(self, view, rows, id_key, fill, form):
        """After a refresh: a vanished selection clears its editor; a
        row that changed elsewhere refills an UNEDITED editor and marks
        an edited one (its Update still writes only its own changes)."""
        editor = getattr(self, f"_{view}_editor", None)
        if editor is None:
            return None
        row = next((r for r in rows if r.get(id_key) == editor["id"]),
                   None)
        if row is None:
            return "deleted"
        if row.get("revision") != editor["revision"]:
            if form() == editor["baseline"]:
                fill(row)
                return None
            return "changed_elsewhere"
        return None

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
        # M14 (S22/S29.2): explicit "teach correction" for the selected
        # V2 job — the corrected text's minimal changed spans become a
        # LearningCandidate (Suggestion review happens in Models →
        # Training Data → Review).
        self.teach_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(372, ch - 28, 300, 24))
        self.teach_field.setPlaceholderString_(
            "corrected text — teach correction for the selected job")
        v.addSubview_(self.teach_field)
        v.addSubview_(_button("Teach", self, "historyTeach:",
                              NSMakeRect(678, ch - 29, 84, 24)))
        # App and mode filters (S19): an app name/bundle substring and a
        # cleanup mode; empty / "All modes" clears each one.
        v.addSubview_(_label(NSMakeRect(8, ch - 55, 34, 18), "App:"))
        self.history_app = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(44, ch - 58, 180, 24))
        self.history_app.setPlaceholderString_("app name or bundle")
        self.history_app.setTarget_(self)
        self.history_app.setAction_("historyAppChanged:")
        v.addSubview_(self.history_app)
        v.addSubview_(_label(NSMakeRect(236, ch - 55, 44, 18), "Mode:"))
        from ..history_queries import MODES
        self.history_mode = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(282, ch - 59, 170, 24))
        self.history_mode.addItemsWithTitles_(["All modes", *MODES])
        self.history_mode.setTarget_(self)
        self.history_mode.setAction_("historyModeChanged:")
        v.addSubview_(self.history_mode)
        self.history_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw * 0.42, 10))
        for ident, width in (("when", 100.0), ("what", 300.0)):
            c = NSTableColumn.alloc().initWithIdentifier_(ident)
            c.setWidth_(width)
            self.history_table.addTableColumn_(c)
        self.history_table.setDataSource_(self)
        self.history_table.setDelegate_(self)
        self.history_table.setAutoresizingMask_(2)
        list_scroll = _scroll(NSMakeRect(0, 36, cw * 0.45, ch - 70),
                              self.history_table)
        list_scroll.setAutoresizingMask_(18)
        v.addSubview_(list_scroll)
        self.history_detail = _textview(NSMakeRect(0, 0, cw * 0.5, 100))
        detail_scroll = _scroll(NSMakeRect(cw * 0.46, 36,
                                           cw * 0.54 - 8, ch - 102),
                                self.history_detail)
        detail_scroll.setAutoresizingMask_(18 | 16)
        v.addSubview_(detail_scroll)
        # Action row: fit the buttons into the detail column's width
        # (clamped so nothing clips at the 900×620 minimum).
        avail = max(cw * 0.54 - 16, 7 * 70)
        buttons = (
                ("Replay", "historyReplay:"),
                ("Copy", "historyCopy:"),
                ("Paste Again", "historyPasteAgain:"),
                ("Retry", "historyRetry:"),
                ("Diff", "historyDiff:"),
                ("Save→Scratchpad", "historyToScratchpad:"),
                ("Move→Scratchpad", "historyMoveToScratchpad:"),
                ("Delete Usage", "historyDeleteUsage:"))
        bw = min(130.0, (avail - (len(buttons) - 1) * 8) / len(buttons))
        for i, (title, action) in enumerate(buttons):
            v.addSubview_(_button(title, self, action,
                                  NSMakeRect(cw * 0.46 + i * (bw + 8), 4,
                                             bw, 24)))
        return v

    def historySearchChanged_(self, sender):
        self.state.set_history_search(sender.stringValue() or "")

    def historyAppChanged_(self, sender):
        self.state.set_history_filters(app=sender.stringValue() or "")

    def historyModeChanged_(self, sender):
        idx = sender.indexOfSelectedItem()
        self.state.set_history_filters(
            mode=None if idx <= 0 else str(sender.titleOfSelectedItem()))

    def historyReload_(self, sender):
        self.state.reload_history()

    @objc.python_method
    def _history_ctx(self):
        """The action context: the RENDERED detail of the selected row —
        or None, with the reason shown, while the selection's detail is
        still loading, failed, or was replaced by a newer publication
        not yet on screen. An action never uses a detail other than the
        one the user sees for the row they selected (M09-AUDIT-01)."""
        view = self.state.views["history"]
        rendered = self._rendered.get("history_detail")
        key = (view.get("selected_kind"), view.get("selected_id"))
        if rendered is None or rendered is not view.get("detail") \
                or view.get("detail_key") != key:
            self._history_note("Select a row and wait for its detail to"
                               " load before acting on it.")
            return None
        return rendered

    @objc.python_method
    def _history_note(self, note):
        if getattr(self, "history_detail", None) is None:
            return  # the History view was never built: nothing to show
        base = self._history_pane_text()
        self.history_detail.setString_(f"{base}\n\n{note}" if base
                                       else note)

    def historyReplay_(self, sender):
        ctx = self._history_ctx()
        if ctx is None or self.replay is None:
            return
        audio = ctx.get("audio") or {}
        # An unavailable item still ends the current playback (one
        # replay authority: the item last asked for, or nothing).
        out = self.replay.play_artifact(self.spec["store"],
                                        audio.get("artifact_id"))
        if not out.get("available"):
            self._history_note(
                f"Replay unavailable ({out.get('reason')}).")

    def historyCopy_(self, sender):
        ctx = self._history_ctx()
        if ctx is None or self.coordinator is None:
            return
        text = self._final_text(ctx)
        if text is None:
            self._history_note("Nothing to copy: this row has no retained"
                               " final text.")
            return
        self.coordinator.hubCopyText(text)
        self._history_note("Copied the final text.")

    _PASTE_NOTES = {
        "repaste_queued": "Paste Again queued: it pastes into the app in"
                          " front when it runs.",
        "recording": "Paste Again refused: recording in progress.",
        "insertion_in_flight": "Paste Again refused: an insertion is in"
                               " progress. Try again when it finishes.",
        "job_deleted": "Paste Again refused: this dictation was deleted.",
        "copy_only": "Copied instead: pasting is unavailable here.",
        "copy_only_no_service": "Copied instead: pasting is unavailable.",
        "nothing_to_paste": "Nothing to paste.",
    }

    def historyPasteAgain_(self, sender):
        ctx = self._history_ctx()
        if ctx is None or self.coordinator is None:
            return
        text = self._final_text(ctx)
        if text is None:
            self._history_note("Nothing to paste: this row has no retained"
                               " final text.")
            return
        # The job id rides along so the re-paste keeps its insertion
        # attribution (contracts/insertion.md); legacy rows pass None.
        out = self.coordinator.hubPasteText(text, job_id=ctx.get("job_id")) \
            or {}
        outcome = out.get("outcome")
        self._history_note(self._PASTE_NOTES.get(
            outcome, f"Paste Again returned {outcome}."))

    def historyRetry_(self, sender):
        ctx = self._history_ctx()
        if ctx is None or self.coordinator is None:
            return
        job_id = ctx.get("job_id")
        if not job_id:
            self._history_note("Retry refused: imported rows have no"
                               " recording to retry.")
            return
        out = self.coordinator.hubRetryJob(job_id) or {}
        outcome, reason = out.get("outcome"), out.get("reason")
        self._history_note({
            "requeued": "Retry queued.",
            "already_retrying": "Retry refused: this dictation is already"
                                " being retried.",
            "not_retryable": f"Retry refused: not retryable ({reason}).",
            "audio_unavailable": f"Retry refused: {reason}.",
            "recording": "Retry refused: recording in progress.",
        }.get(outcome, f"Retry returned {outcome}"
                       + (f" ({reason})" if reason else "") + "."))

    def historyTeach_(self, sender):
        """M14 (S22): explicit teach-correction. The submitted text is
        diffed against the selected job's retained final text; a
        reliable bounded correction becomes a pending LearningCandidate
        (an unchanged or whole-rewrite submission refuses with the
        reason — never a fabricated correction)."""
        learning = self.spec.get("learning_service")
        corrected = (self.teach_field.stringValue() or "").strip()
        if learning is None or not corrected:
            return
        ctx = self._history_ctx()
        if ctx is None:
            return
        job_id = ctx.get("job_id")
        if not job_id:
            self._history_note("Teach refused: imported rows are not"
                               " dictations.")
            return
        if ctx.get("final_stage") == "transformed":
            # Teach measures a correction against the cleaned output;
            # this row's inserted text is the transform's, which is not
            # the text the correction would be compared with.
            self._history_note("Teach refused: this dictation's final"
                               " text came from a transform, and Teach"
                               " corrects the cleaned text.")
            return
        try:
            out = learning.teach_correction(job_id, corrected)
            note = (f"candidate {out['candidate_id'][:20]}… created"
                    f" ({out['status']})"
                    + (f" — suggested: {out['suggestion']['alias']} →"
                       f" {out['suggestion']['canonical']}"
                       if out.get("suggestion") else
                       " — spans recorded for review"))
        except ValueError as e:
            note = f"teach correction refused: {e}"
        except Exception as e:
            note = f"teach correction failed: {type(e).__name__}"
        self._history_note(note)

    def historyDeleteUsage_(self, sender):
        """M13 (S21/M13-AC03): the explicit 'delete associated usage'
        control for one V2 job — counters only, never content. Legacy
        rows refuse honestly (the lossless import carries no deletable
        usage facts)."""
        if self.coordinator is None or \
                not hasattr(self.coordinator, "hubDeleteUsageForJob"):
            return
        ctx = self._history_ctx()
        if ctx is None:
            return
        out = self.coordinator.hubDeleteUsageForJob(ctx.get("job_id")) or {}
        note = {"deleted": "usage for this dictation deleted — graphs"
                           " recomputed",
                "not_a_v2_job": "legacy rows carry no deletable usage"
                                " facts (lossless import)",
                "unavailable": "usage analytics unavailable",
                "failed": "usage deletion failed — see Diagnostics"}
        self._history_note(note.get(out.get("outcome"), "usage deletion"
                                    " returned " + str(out.get("outcome"))))

    def historyToScratchpad_(self, sender):
        self._history_to_scratchpad(move=False)

    def historyMoveToScratchpad_(self, sender):
        self._historyToScratchpad(move=True)

    @objc.python_method
    def _history_to_scratchpad(self, move):
        """M12 (S20 task 4): explicit copy/move from History into the
        Scratchpad. Move's delete-everywhere only applies to V2 jobs —
        legacy rows degrade honestly to copy (reported in the detail)."""
        if self.coordinator is None:
            return
        ctx = self._history_ctx()
        if ctx is None:
            return
        kind, row_id = self.state.views["history"].get("detail_key")
        out = self.coordinator.hubSaveHistoryRow(kind, row_id, move=move)
        note = {"copied": "saved to a new Scratchpad note",
                "moved": "moved — the History row's content was deleted"
                         " everywhere (the note keeps it)",
                "move_degrades_to_copy_legacy":
                    "saved to a new note; legacy history is preserved"
                    " as-is (lossless by contract), so this was a copy",
                "move_failed_note_copied":
                    "the note was created but the History deletion"
                    " failed — row kept",
                }.get(out.get("outcome"), out.get("outcome"))
        self._history_note(f"→ Scratchpad: {note}")
        if kind == "job" and out.get("outcome") == "moved":
            self.state.reload_history()

    def historyDiff_(self, sender):
        ctx = self._history_ctx()
        if ctx is None:
            return
        stages = ctx.get("lineage") or []

        def text_of(stage_name):
            for s in stages:
                if s["stage"] == stage_name:
                    art = s.get("artifact")
                    return art.get("text") if art else None
            return None
        self._history_note("— diff source → cleaned —\n"
                           + _stage_diff(text_of("source"),
                                         text_of("cleaned")))

    @objc.python_method
    def _final_text(self, detail):
        """The text that was actually inserted: the transform output
        when its recorded decision says applied, else the cleaned
        output. A final stage that is gone yields None — the source
        transcript is never a substitute for it."""
        stages = {s["stage"]: s for s in detail.get("lineage") or []}

        def text(name):
            art = (stages.get(name) or {}).get("artifact")
            return art["text"] if art and art.get("present") \
                and art.get("text") else None
        if detail.get("final_stage") == "transformed":
            return text("transformed")
        return text("cleaned")

    @objc.python_method
    def _current_detail_text(self):
        detail = self._rendered.get("history_detail")
        return self._final_text(detail) if detail else None

    @objc.python_method
    def _render_history_detail(self, detail):
        if detail is None:
            return "Select a row to see its lineage, outcome and actions."
        lines = []
        if detail.get("time_quality") == "unknown":
            lines.append("date: Undated (imported legacy record)")
        elif detail.get("captured_at_utc"):
            lines.append(f"captured (UTC): {detail['captured_at_utc']}"
                         + (f"  attempt {detail.get('attempt')}"
                            if detail.get("attempt") else ""))
        if detail.get("kind") == "legacy_db":
            lines.append("imported legacy record — no recording, not a"
                         " V2 dictation")
        if detail.get("app"):
            lines.append(f"app: {detail['app']}")
        if detail.get("state"):
            reason = detail.get("state_reason")
            lines.append(f"state: {detail['state']}"
                         + (f" ({reason})" if reason else ""))
        la = detail.get("lineage_attempt")
        if la and detail.get("attempt") and la != detail.get("attempt"):
            lines.append(f"stages recorded by attempt {la}")
        if detail.get("lineage_ambiguous"):
            lines.append("several attempts recorded without attempt ids —"
                         " showing the newest stages")
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
            label = stage["label"]
            decision = stage.get("decision")
            if decision:
                if decision.get("applied"):
                    label += f" — applied ({decision.get('path')})"
                else:
                    label += (f" — not applied: {decision.get('path')}"
                              + (f" ({decision.get('reason')})"
                                 if decision.get("reason") else "")
                              + "; proposal kept, not inserted")
            if art is None:
                lines.append(f"\n── {label} ──\n"
                             f"({stage.get('reason', 'not captured')})")
            elif not art.get("present"):
                lines.append(f"\n── {label} ──\n(content expired)")
            else:
                lines.append(f"\n── {label} ──\n"
                             f"{art.get('text') or '(empty)'}")
        return "\n".join(lines)

    @objc.python_method
    def _history_pane_text(self):
        view = self.state.views["history"]
        data = view.get("data")
        if view.get("error"):
            return (f"History could not load ({view['error']})."
                    + (" The rows shown are from the last successful"
                       " load." if data else ""))
        if not data or not data.get("groups"):
            # A loaded empty result is {"groups": [], ...}: still empty.
            if view.get("loading"):
                return "Loading history…"
            if view.get("search") or view.get("app") or view.get("mode"):
                return ("Nothing matches these filters. Clear the search"
                        " or filters to see all history.")
            return "No history yet — dictations appear here."
        if view.get("selected_id") is None:
            return self._render_history_detail(None)
        rendered = self._rendered.get("history_detail")
        if rendered is not None:
            return self._render_history_detail(rendered)
        if view.get("detail_loading"):
            return "Loading the selected dictation…"
        err = view.get("detail_error")
        if err == "deleted":
            return "This dictation was deleted."
        if err:
            return f"This row's detail could not load ({err})."
        return self._render_history_detail(None)

    @objc.python_method
    def _refresh_history_view(self):
        view = self.state.views["history"]
        data = view.get("data")
        if data is not None:
            flat = []
            for group in data["groups"]:
                flat.append({"__group__": group["label"]})
                flat.extend(group["rows"])
            self._history_flat = flat
            self.history_table.reloadData()
            # Preserve selection (AC04): reselect the same row id; a
            # refresh never jumps to the newest row, and a row that is
            # gone leaves no stale highlight.
            sel = (view.get("selected_kind"), view.get("selected_id"))
            idx = next((i for i, e in enumerate(flat)
                        if not e.get("__group__")
                        and (e["kind"], e["id"]) == sel), None)
            self._suppress_select = True
            try:
                if idx is None:
                    self.history_table.deselectAll_(None)
                else:
                    self.history_table.selectRowIndexes_byExtendingSelection_(
                        Foundation.NSIndexSet.indexSetWithIndex_(idx),
                        False)
            finally:
                self._suppress_select = False
        elif self._history_flat:
            # Data dropped by a retention pass: no stale (possibly purged)
            # rows while the reload runs.
            self._history_flat = []
            self.history_table.reloadData()
        detail = view.get("detail")
        key = (view.get("selected_kind"), view.get("selected_id"))
        self._rendered["history_detail"] = detail \
            if detail is not None and view.get("detail_key") == key \
            else None
        if key != self._teach_key:
            # A typed correction belongs to the row it was typed against.
            self._teach_key = key
            self.teach_field.setStringValue_("")
        self.history_detail.setString_(self._history_pane_text())

    # ---- Styles (M10, Spec S15) -------------------------------------------

    @objc.python_method
    def _build_styles_view(self):
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.styles_status = _label(NSMakeRect(8, ch - 24, cw - 16, 18), "")
        v.addSubview_(self.styles_status)
        self.styles_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw * 0.34, 10))
        for ident, width in (("rule", 150.0), ("mode", 90.0)):
            c = NSTableColumn.alloc().initWithIdentifier_(ident)
            c.setWidth_(width)
            self.styles_table.addTableColumn_(c)
        self.styles_table.setDataSource_(self)
        self.styles_table.setDelegate_(self)
        tsc = _scroll(NSMakeRect(8, 150, cw * 0.36, ch - 180),
                      self.styles_table)
        tsc.setAutoresizingMask_(2)
        v.addSubview_(tsc)
        # Rule editor (right column): the live S15 rule dimensions. The
        # transform-backed modes (M11) select their transform; a mode
        # whose definition has not opted in to auto-apply resolves to
        # Clean with the honest reason shown in the status line.
        x = cw * 0.38
        self.style_name = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 54, 220, 22))
        self.style_name.setPlaceholderString_("rule name")
        v.addSubview_(_label(NSMakeRect(x, ch - 51, 60, 18), "Name:"))
        v.addSubview_(self.style_name)
        self.style_scope = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 82, 130, 24))
        self.style_scope.addItemsWithTitles_(
            ["global", "category", "app", "site", "workspace"])
        v.addSubview_(_label(NSMakeRect(x, ch - 79, 60, 18), "Scope:"))
        v.addSubview_(self.style_scope)
        self.style_scope_value = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + 208, ch - 82, 200, 22))
        self.style_scope_value.setPlaceholderString_(
            "bundle / origin / workspace / category")
        v.addSubview_(self.style_scope_value)
        self.style_mode = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 110, 130, 24))
        self.style_mode.addItemsWithTitles_(
            ["clean", "raw", "polish", "concise", "prompt_engineer",
             "custom"])
        v.addSubview_(_label(NSMakeRect(x, ch - 107, 60, 18), "Mode:"))
        v.addSubview_(self.style_mode)
        self.style_numbers = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(x + 208, ch - 110, 130, 24))
        self.style_numbers.addItemsWithTitles_(
            ["inherit", "technical", "standard"])
        v.addSubview_(_label(NSMakeRect(x + 140, ch - 107, 66, 18),
                             "Numbers:"))
        v.addSubview_(self.style_numbers)
        for i, (title, action) in enumerate((
                ("Add", "stylesAdd:"),
                ("Update", "stylesUpdate:"),
                ("Delete", "stylesDelete:"),
                ("Enable/Disable", "stylesToggle:"))):
            v.addSubview_(_button(title, self, action,
                                  NSMakeRect(x + i * 130, 118, 124, 24)))
        # The phrase sandbox: what the current registries + the resolved
        # style's policy would do to a phrase (S15 sample output).
        self.style_phrase = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x, 88, cw - x - 130, 22))
        self.style_phrase.setPlaceholderString_("test a phrase")
        v.addSubview_(self.style_phrase)
        v.addSubview_(_button("Preview", self, "stylesPreview:",
                              NSMakeRect(cw - 116, 87, 108, 24)))
        self.styles_detail = _textview(NSMakeRect(0, 0, cw - x - 16, 80))
        sdc = _scroll(NSMakeRect(x, 8, cw - x - 16, 78), self.styles_detail)
        sdc.setAutoresizingMask_(2 | 16)
        v.addSubview_(sdc)
        return v

    def stylesAdd_(self, sender):
        self._m10_add("styles")

    def stylesUpdate_(self, sender):
        self._m10_update("styles")

    @objc.python_method
    def _m10_outcome(self, view, verb, e):
        """One honest status line per failure class: an admitted write
        whose caller stopped waiting is UNKNOWN (it may still commit —
        repeating the same action is safe), a vanished row is gone, and
        everything else was refused before or by the writer (nothing
        committed)."""
        from .. import profiles_store as ps
        status = self.styles_status if view == "styles" \
            else self.snippets_status
        if isinstance(e, ps.OutcomeUnknownError):
            status.setStringValue_(
                f"outcome unknown: the {verb} was queued and may still"
                f" complete — press {verb.capitalize()} again with the"
                " same fields to confirm (no duplicate is created)")
        elif isinstance(e, ps.NotFoundError):
            status.setStringValue_(
                f"not {verb}d: the selected item no longer exists")
        elif isinstance(e, ps.StaleRevisionError):
            status.setStringValue_(
                f"not {verb}d: it changed elsewhere — reloaded")
        elif isinstance(e, (ValueError, KeyError)):
            status.setStringValue_(f"not saved: {e}")
        else:
            status.setStringValue_(f"not saved: {type(e).__name__}")

    @objc.python_method
    def _m10_add(self, view):
        """Add with a pre-allocated id: a retry of the SAME form after an
        unknown outcome reuses the id, so the store either confirms the
        earlier commit or performs it once (M10-AUDIT-21)."""
        from .. import ids
        svc = self.spec.get(f"{view}_service")
        status = self.styles_status if view == "styles" \
            else self.snippets_status
        if svc is None:
            status.setStringValue_(f"{view} unavailable")
            return
        form = self._style_form() if view == "styles" \
            else self._snippet_form()
        pending = self._pending_adds.get(view)
        new_id = pending["id"] if pending and pending["form"] == form \
            else ids.new_id("style" if view == "styles" else "snip")
        self._pending_adds[view] = {"id": new_id, "form": form}
        try:
            if view == "styles":
                svc.add_rule(name=form["name"],
                             scope_kind=form["scope_kind"],
                             scope_value=form["scope_value"],
                             mode=form["mode"],
                             number_policy=form["number_policy"],
                             rule_id=new_id)
            else:
                svc.add_snippet(trigger=form["trigger"],
                                name=form["name"] or form["trigger"],
                                content=form["content"], kind=form["kind"],
                                allow_rewrite=form["allow_rewrite"],
                                snippet_id=new_id)
        except Exception as e:
            from .. import profiles_store as ps
            if not isinstance(e, ps.OutcomeUnknownError):
                self._pending_adds.pop(view, None)
            self._m10_outcome(view, "save", e)
            return
        self._pending_adds.pop(view, None)
        status.setStringValue_(
            "added (confirmed)" if pending and pending["id"] == new_id
            else "added")
        getattr(self.state, f"reload_{view}")()

    @objc.python_method
    def _m10_update(self, view):
        """Write only the fields changed since the editor was filled from
        its row; the store validates the merge against the row as it is
        now (M10-AUDIT-20)."""
        svc = self.spec.get(f"{view}_service")
        status = self.styles_status if view == "styles" \
            else self.snippets_status
        editor = self._m10_target(view)
        if svc is None:
            status.setStringValue_(f"{view} unavailable")
            return
        if editor is None or not editor.get("id"):
            status.setStringValue_("select an item to update")
            return
        form = self._style_form() if view == "styles" \
            else self._snippet_form()
        diff = {k: v for k, v in form.items()
                if v != editor["baseline"].get(k)}
        if view == "snippets" and "name" in diff and not diff["name"]:
            diff["name"] = form["trigger"]
        if not diff:
            status.setStringValue_("no changes to save")
            return
        try:
            if view == "styles":
                updated = svc.update_rule(editor["id"], **diff)
            else:
                updated = svc.update_snippet(editor["id"], **diff)
        except Exception as e:
            from .. import profiles_store as ps
            if isinstance(e, ps.NotFoundError):
                (self._clear_style_editor if view == "styles"
                 else self._clear_snippet_editor)()
            self._m10_outcome(view, "save", e)
            getattr(self.state, f"reload_{view}")()
            return
        binding = {"id": editor["id"], "revision": updated.revision,
                   "baseline": form}
        if view == "styles":
            self._style_editor = binding
        else:
            self._snippet_editor = binding
        status.setStringValue_("saved")
        getattr(self.state, f"reload_{view}")()

    @objc.python_method
    def _m10_delete(self, view):
        svc = self.spec.get(f"{view}_service")
        editor = self._m10_target(view)
        if svc is None or editor is None or not editor.get("id"):
            return
        try:
            if view == "styles":
                svc.delete_rule(editor["id"])
            else:
                svc.delete_snippet(editor["id"])
        except Exception as e:
            from .. import profiles_store as ps
            if isinstance(e, ps.NotFoundError):
                (self._clear_style_editor if view == "styles"
                 else self._clear_snippet_editor)()
            self._m10_outcome(view, "delete", e)
            getattr(self.state, f"reload_{view}")()
            return
        (self._clear_style_editor if view == "styles"
         else self._clear_snippet_editor)("deleted")
        getattr(self.state, f"reload_{view}")()

    @objc.python_method
    def _m10_toggle(self, view):
        """Flip the RENDERED row's state, refused if the row changed
        since it was rendered (a stale toggle never re-enables what was
        disabled elsewhere)."""
        svc = self.spec.get(f"{view}_service")
        editor = self._m10_target(view)
        if svc is None or editor is None or not editor.get("id"):
            return
        key, id_key = (("rules", "rule_id") if view == "styles"
                       else ("snippets", "snippet_id"))
        table = f"{view}_table"
        row = next((r for r in self._rendered_rows.get(table, ())
                    if r.get(id_key) == editor["id"]), None)
        if row is None:
            return
        try:
            svc.set_enabled(editor["id"], not row.get("enabled", True),
                            expected_revision=row.get("revision"))
        except Exception as e:
            self._m10_outcome(view, "save", e)
            getattr(self.state, f"reload_{view}")()
            return
        getattr(self.state, f"reload_{view}")()

    def stylesDelete_(self, sender):
        self._m10_delete("styles")

    def stylesToggle_(self, sender):
        self._m10_toggle("styles")

    def stylesPreview_(self, sender):
        text = self.style_phrase.stringValue() or ""
        if self.coordinator is None:
            return
        # The sandbox previews the style the editor shows — its mode and
        # number policy — in the declared global scope (M10-AUDIT-19).
        out = self.coordinator.hubPreviewPhrase(
            text, mode=self.style_mode.titleOfSelectedItem() or "clean",
            number_policy=self.style_numbers.titleOfSelectedItem())
        self.state.set_developer_preview("styles", out)
        self._render_styles_preview(out)

    @objc.python_method
    def _render_styles_preview(self, out):
        if not out:
            return
        if out.get("error"):
            self.styles_detail.setString_(
                f"preview failed: {out['error']}")
            return
        lines = [f"→ {out.get('output')}",
                 f"(preview: {out.get('mode', 'clean')} in"
                 f" {out.get('scope', 'global only')} —"
                 f" {out.get('scope_detail', '')})", ""]
        for e in out.get("edits") or []:
            lines.append(f"edit: {e['before']!r} → {e['after']!r}"
                         f"  ({e['cls']})")
        for r in out.get("rejected") or []:
            lines.append(f"kept literal: {r['before']!r}  ({r['reason']})")
        self.styles_detail.setString_("\n".join(lines))

    @objc.python_method
    def _refresh_styles_view(self):
        view = self.state.views["styles"]
        data = view.get("data")
        if view.get("error"):
            self.styles_status.setStringValue_(
                f"styles unavailable ({view['error']})")
            self._render_rows("styles_table", "rule_id",
                              self.state.views["styles"].get("selected_id"))
            return
        rows = self._render_rows(
            "styles_table", "rule_id",
            self.state.views["styles"].get("selected_id"))
        sync = self._sync_editor("style", rows, "rule_id",
                                 self._fill_style_editor, self._style_form)
        if sync == "deleted":
            self._clear_style_editor(
                "The selected rule no longer exists; its editor was"
                " cleared.")
            return
        if sync == "changed_elsewhere":
            self.styles_status.setStringValue_(
                "This rule changed since you opened it; Update writes"
                " only the fields you changed.")
            return
        eff = (data or {}).get("effective") or {}
        profile = eff.get("profile") or {}
        if profile:
            fallback = profile.get("fallback_reason")
            self.styles_status.setStringValue_(
                f"Effective: {profile.get('effective_mode')} ·"
                f" profile {profile.get('profile_name') or 'default'} ·"
                f" {profile.get('source')}"
                + (f" — {fallback}" if fallback else ""))
        else:
            self.styles_status.setStringValue_(
                "Effective profile appears after the next dictation."
                if not (data or {}).get("rules")
                else "Rules below; effective profile after a dictation.")
        preview = view.get("preview")
        if preview:
            self._render_styles_preview(preview)
        elif not data or not data.get("rules"):
            self.styles_detail.setString_(
                "No style rules. Add one: a scope (category, app bundle,"
                " site origin or workspace), a mode (clean/raw) and a"
                " number policy. Resolution: next-job override →"
                " destination rule → category default → global default.")

    # ---- Snippets (M10, Spec S17) ------------------------------------------

    @objc.python_method
    def _build_snippets_view(self):
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.snippets_status = _label(NSMakeRect(8, ch - 24, cw - 16, 18),
                                      "")
        v.addSubview_(self.snippets_status)
        self.snippets_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw * 0.3, 10))
        for ident, width in (("trigger", 130.0), ("kind", 90.0)):
            c = NSTableColumn.alloc().initWithIdentifier_(ident)
            c.setWidth_(width)
            self.snippets_table.addTableColumn_(c)
        self.snippets_table.setDataSource_(self)
        self.snippets_table.setDelegate_(self)
        tsc = _scroll(NSMakeRect(8, 150, cw * 0.32, ch - 180),
                      self.snippets_table)
        tsc.setAutoresizingMask_(2)
        v.addSubview_(tsc)
        x = cw * 0.34
        self.snip_trigger = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 54, 220, 22))
        self.snip_trigger.setPlaceholderString_("spoken trigger")
        v.addSubview_(_label(NSMakeRect(x, ch - 51, 60, 18), "Trigger:"))
        v.addSubview_(self.snip_trigger)
        self.snip_name = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + 300, ch - 54, 160, 22))
        self.snip_name.setPlaceholderString_("name")
        v.addSubview_(self.snip_name)
        self.snip_kind = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 82, 130, 24))
        self.snip_kind.addItemsWithTitles_(
            ["plain", "rich", "url", "signature", "code", "prompt"])
        v.addSubview_(_label(NSMakeRect(x, ch - 79, 60, 18), "Kind:"))
        v.addSubview_(self.snip_kind)
        self.snip_rewrite = NSButton.alloc().init()
        self.snip_rewrite.setButtonType_(NSSwitchButton)
        self.snip_rewrite.setTitle_("allow later rewriting")
        self.snip_rewrite.setFrame_(NSMakeRect(x + 210, ch - 84, 220, 22))
        v.addSubview_(self.snip_rewrite)
        self.snip_content = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw - x - 16, 60))
        self.snip_content.setFont_(_mono())
        scc = _scroll(NSMakeRect(x, 148, cw - x - 16, 62),
                      self.snip_content)
        scc.setAutoresizingMask_(2 | 16)
        v.addSubview_(scc)
        for i, (title, action) in enumerate((
                ("Add", "snippetsAdd:"),
                ("Update", "snippetsUpdate:"),
                ("Delete", "snippetsDelete:"),
                ("Enable/Disable", "snippetsToggle:"),
                ("Collisions", "snippetsCollisions:"))):
            v.addSubview_(_button(title, self, action,
                                  NSMakeRect(x + i * 120, 116, 114, 24)))
        self.snippets_detail = _textview(NSMakeRect(0, 0, cw - x - 16, 96))
        ndc = _scroll(NSMakeRect(x, 8, cw - x - 16, 104),
                      self.snippets_detail)
        ndc.setAutoresizingMask_(2 | 16)
        v.addSubview_(ndc)
        return v

    def snippetsAdd_(self, sender):
        self._m10_add("snippets")

    def snippetsUpdate_(self, sender):
        self._m10_update("snippets")

    def snippetsDelete_(self, sender):
        self._m10_delete("snippets")

    def snippetsToggle_(self, sender):
        self._m10_toggle("snippets")

    def snippetsCollisions_(self, sender):
        """Preview this form before saving (S17) — through the
        coordinator, which runs the same engine call dictation makes in
        the declared preview scope. The form is an edit of the selected
        snippet (so it never collides with itself), or a new one."""
        form = self._snippet_form()
        if not form["trigger"] or self.coordinator is None:
            return
        editor = self._m10_target("snippets") or {}
        out = self.coordinator.hubSnippetCollisionPreview(
            form["trigger"], snippet_id=editor.get("id"),
            content=form["content"], kind=form["kind"]) \
            if hasattr(self.coordinator, "hubSnippetCollisionPreview") \
            else []
        lines = []
        for c in out:
            lines.append(f"{c['kind']}: {c['detail']}")
        self.snippets_detail.setString_(
            "\n".join(lines) or "no collisions for this trigger (preview"
            " scope: global only — no destination, no workspace)")

    @objc.python_method
    def _refresh_snippets_view(self):
        view = self.state.views["snippets"]
        data = view.get("data")
        rows = self._render_rows(
            "snippets_table", "snippet_id",
            self.state.views["snippets"].get("selected_id"))
        if view.get("error"):
            self.snippets_status.setStringValue_(
                f"snippets unavailable ({view['error']})")
            return
        sync = self._sync_editor("snippet", rows, "snippet_id",
                                 self._fill_snippet_editor,
                                 self._snippet_form)
        if sync == "deleted":
            self._clear_snippet_editor(
                "The selected snippet no longer exists; its editor was"
                " cleared.")
            return
        if sync == "changed_elsewhere":
            self.snippets_status.setStringValue_(
                "This snippet changed since you opened it; Update writes"
                " only the fields you changed.")
            return
        rows = (data or {}).get("snippets") or []
        conflicts = (data or {}).get("conflicts") or []
        self.snippets_status.setStringValue_(
            f"{len(rows)} snippets"
            + (f" · {len(conflicts)} masked trigger conflict(s)"
               if conflicts else ""))
        if conflicts:
            self.snippets_detail.setString_("\n".join(
                f"masked: {c['trigger']} ({c['reason']})"
                for c in conflicts))
        elif not rows:
            self.snippets_detail.setString_(
                "No snippets. Add one: a spoken trigger, exact content"
                " ({{placeholders}} fill from the utterance after the"
                " trigger, split on the spoken word 'comma').")

    # ---- Transforms (M11, Spec S16) ----------------------------------------

    @objc.python_method
    def _build_transforms_view(self):
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.transforms_status = _label(
            NSMakeRect(8, ch - 24, cw - 16, 18), "")
        v.addSubview_(self.transforms_status)
        self.transforms_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw * 0.34, 10))
        for ident, width in (("name", 170.0), ("mode", 130.0)):
            c = NSTableColumn.alloc().initWithIdentifier_(ident)
            c.setWidth_(width)
            self.transforms_table.addTableColumn_(c)
        self.transforms_table.setDataSource_(self)
        self.transforms_table.setDelegate_(self)
        tsc = _scroll(NSMakeRect(8, 150, cw * 0.36, ch - 180),
                      self.transforms_table)
        tsc.setAutoresizingMask_(2)
        v.addSubview_(tsc)
        # Definition editor (right column). Legacy rows are preserved
        # revisions — selectable/readable, never editable (AC01).
        x = cw * 0.38
        self.tf_name = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 54, 220, 22))
        self.tf_name.setPlaceholderString_("transform name")
        v.addSubview_(_label(NSMakeRect(x, ch - 51, 60, 18), "Name:"))
        v.addSubview_(self.tf_name)
        self.tf_mode = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 82, 150, 24))
        self.tf_mode.addItemsWithTitles_(
            ["custom", "polish", "concise", "prompt_engineer"])
        v.addSubview_(_label(NSMakeRect(x, ch - 79, 60, 18), "Mode:"))
        v.addSubview_(self.tf_mode)
        self.tf_auto = NSButton.buttonWithTitle_target_action_(
            "Auto-apply before insertion (opt-in)", self,
            None)
        self.tf_auto.setButtonType_(4)  # NSSwitchButton
        self.tf_auto.setFrame_(NSMakeRect(x + 230, ch - 84, 240, 22))
        v.addSubview_(self.tf_auto)
        self.tf_shortcut = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + 70, ch - 110, 44, 22))
        self.tf_shortcut.setPlaceholderString_("key")
        v.addSubview_(_label(
            NSMakeRect(x, ch - 107, 60, 18), "Shortcut:"))
        v.addSubview_(self.tf_shortcut)
        self.tf_targets = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + 196, ch - 110, 240, 22))
        self.tf_targets.setPlaceholderString_(
            "target profiles (comma, empty = all)")
        v.addSubview_(_label(
            NSMakeRect(x + 122, ch - 107, 72, 18), "Profiles:"))
        v.addSubview_(self.tf_targets)
        self.tf_prompt = _textview(NSMakeRect(0, 0, cw - x - 16, 96))
        pc = _scroll(NSMakeRect(x, 152, cw - x - 16, 96), self.tf_prompt)
        pc.setAutoresizingMask_(2 | 16)
        v.addSubview_(pc)
        v.addSubview_(_label(
            NSMakeRect(x, 252, cw - x - 16, 18),
            "Custom instruction (custom mode; built-ins use their"
            " frozen contract):"))
        for i, (title, action) in enumerate((
                ("Add", "transformsAdd:"),
                ("Update", "transformsUpdate:"),
                ("Enable/Disable", "transformsToggle:"))):
            v.addSubview_(_button(title, self, action,
                                  NSMakeRect(x + i * 130, 118, 124, 24)))
        self.transforms_detail = _textview(
            NSMakeRect(0, 0, cw - x - 16, 80))
        tdc = _scroll(NSMakeRect(x, 8, cw - x - 16, 78),
                      self.transforms_detail)
        tdc.setAutoresizingMask_(2 | 16)
        v.addSubview_(tdc)
        return v

    def transformsAdd_(self, sender):
        self._transform_write("add")

    def transformsUpdate_(self, sender):
        self._transform_write("update")

    @objc.python_method
    def _transform_write(self, action):
        svc = self.spec.get("transforms_service")
        if svc is None:
            self.transforms_status.setStringValue_(
                "transforms unavailable")
            return
        name = self.tf_name.stringValue() or ""
        mode = self.tf_mode.titleOfSelectedItem() or "custom"
        shortcut = self.tf_shortcut.stringValue() or None
        targets = [t.strip() for t in
                   (self.tf_targets.stringValue() or "").split(",")
                   if t.strip()]
        prompt = self.tf_prompt.string() or ""
        try:
            if action == "add":
                svc.add_transform(
                    name=name, mode=mode, prompt=prompt,
                    shortcut=shortcut, target_profiles=targets,
                    auto_apply=bool(self.tf_auto.state()))
            else:
                transform_id = self.state.views["transforms"].get(
                    "selected_id")
                if not transform_id:
                    self.transforms_status.setStringValue_(
                        "select a transform to update")
                    return
                svc.update_transform(
                    transform_id, name=name, mode=mode, prompt=prompt,
                    shortcut=shortcut, target_profiles=targets,
                    auto_apply=bool(self.tf_auto.state()))
        except (ValueError, KeyError) as e:
            self.transforms_status.setStringValue_(f"not saved: {e}")
            return
        except Exception as e:
            self.transforms_status.setStringValue_(
                f"not saved: {type(e).__name__}")
            return
        self.state.reload_transforms()

    def transformsToggle_(self, sender):
        svc = self.spec.get("transforms_service")
        transform_id = self.state.views["transforms"].get("selected_id")
        data = (self.state.views["transforms"].get("data") or {})
        if svc is None or not transform_id:
            return
        enabled = next(
            (t.get("enabled") for t in data.get("transforms", ())
             if t.get("transform_id") == transform_id), True)
        try:
            svc.set_enabled(transform_id, not enabled)
        except Exception as e:
            self.transforms_status.setStringValue_(
                f"not toggled: {type(e).__name__}")
            return
        self.state.reload_transforms()

    @objc.python_method
    def _fill_transform_editor(self, t):
        self.tf_name.setStringValue_(t.get("name") or "")
        self.tf_mode.selectItemWithTitle_(t.get("mode") or "custom")
        self.tf_shortcut.setStringValue_(t.get("shortcut") or "")
        self.tf_targets.setStringValue_(
            ", ".join(t.get("target_profiles") or ()))
        self.tf_auto.setState_(1 if t.get("auto_apply") else 0)
        legacy = t.get("origin") == "legacy"
        builtin = t.get("origin") == "builtin"
        editable = not legacy
        for ctrl in (self.tf_name, self.tf_mode, self.tf_shortcut,
                     self.tf_targets, self.tf_auto, self.tf_prompt):
            ctrl.setEnabled_(editable)
        # A built-in IS its mode (polish/concise/prompt_engineer bind
        # by id+mode): the mode stays fixed so a Hub edit can never
        # silently unbind or cross-bind the mode executors.
        self.tf_mode.setEnabled_(editable and not builtin)
        self.tf_prompt.setString_(
            (t.get("prompt") or
             ("(built-in frozen contract — see Transforms contract)"
              if builtin else "")) if editable else (t.get("prompt") or ""))
        detail = [
            f"{t.get('transform_id')} · revision {t.get('revision')}"
            f" · prompt {t.get('prompt_revision')}"]
        if legacy:
            detail.append(
                "Preserved legacy revision (M11-AC01): prompt kept"
                " verbatim; edits create a custom transform instead.")
            if t.get("legacy_key"):
                detail.append(
                    f"legacy key {t['legacy_key']!r} recorded, never"
                    " bound as a shortcut")
        self.transforms_detail.setString_("\n".join(detail))

    @objc.python_method
    def _refresh_transforms_view(self):
        view = self.state.views["transforms"]
        data = view.get("data")
        if view.get("error"):
            self.transforms_status.setStringValue_(
                f"transforms unavailable ({view['error']})")
            self._render_rows("transforms_table", "transform_id",
                              self.state.views["transforms"].get("selected_id"))
            return
        self._render_rows("transforms_table", "transform_id",
                          self.state.views["transforms"].get("selected_id"))
        conflicts = (data or {}).get("shortcut_conflicts") or []
        if conflicts:
            self.transforms_status.setStringValue_(
                f"shortcut collisions: "
                + ", ".join(c["shortcut"] for c in conflicts))
        elif not data or not data.get("transforms"):
            self.transforms_detail.setString_(
                "No transform definitions. Built-ins seed on first run;"
                " Add creates a custom transform (instruction + optional"
                " writing samples via JSON import). Auto-apply is"
                " opt-in per definition (M11-AC04).")
        else:
            self.transforms_status.setStringValue_(
                f"{len(data['transforms'])} definitions")

    # ---- Scratchpad (M12, Spec S20) ----------------------------------------

    @objc.python_method
    def _build_scratchpad_view(self):
        """M12 (Spec S20): notes list + tab strip + editor + actions.
        The editor is the ScratchpadEditor NSObject (ui/scratchpad.py);
        the shell owns no note logic — actions go through notes_service
        and coordinator commands."""
        from .scratchpad import ScratchpadEditor
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        self.scratchpad_status = _label(
            NSMakeRect(8, ch - 24, cw * 0.6, 18), "")
        v.addSubview_(self.scratchpad_status)
        self.scratchpad_search = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(cw * 0.62, ch - 26, cw * 0.36, 22))
        self.scratchpad_search.setTarget_(self)
        self.scratchpad_search.setAction_("scratchpadSearchChanged:")
        v.addSubview_(self.scratchpad_search)
        self.scratchpad_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw * 0.26, 10))
        for ident, width in (("title", 150.0), ("words", 52.0)):
            c = NSTableColumn.alloc().initWithIdentifier_(ident)
            c.setWidth_(width)
            self.scratchpad_table.addTableColumn_(c)
        self.scratchpad_table.setDataSource_(self)
        self.scratchpad_table.setDelegate_(self)
        stc = _scroll(NSMakeRect(8, 118, cw * 0.28, ch - 150),
                      self.scratchpad_table)
        stc.setAutoresizingMask_(2)
        v.addSubview_(stc)
        # Tab strip over open notes (S20 tabs): one chip per open note.
        self.scratchpad_tabs = NSView.alloc().initWithFrame_(
            NSMakeRect(cw * 0.30, ch - 52, cw * 0.68, 24))
        v.addSubview_(self.scratchpad_tabs)
        self.editor = ScratchpadEditor.alloc().init_editor(self)
        ecw = cw * 0.68
        self.editor.scroll.setFrame_(
            NSMakeRect(cw * 0.30, 96, ecw - 8, ch - 152))
        self.editor.scroll.setAutoresizingMask_(2 | 16)
        v.addSubview_(self.editor.scroll)
        x = cw * 0.30
        for title, action, w in (
                ("New", "scratchpadNew:", 60.0),
                ("Pin", "scratchpadPin:", 54.0),
                ("Snapshot", "scratchpadSnapshot:", 92.0),
                ("Add Image…", "scratchpadAttach:", 96.0),
                ("Transform…", "scratchpadTransform:", 100.0),
                ("Restore", "scratchpadRestore:", 74.0),
                ("Export .md", "scratchpadExportMD:", 88.0),
                ("Export .txt", "scratchpadExportTXT:", 88.0),
                ("Delete", "scratchpadDelete:", 66.0)):
            v.addSubview_(_button(title, self, action,
                                  NSMakeRect(x, 62, w, 24)))
            x += w + 8
        self.scratchpad_versions = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(cw * 0.30, 30, cw * 0.42, 24))
        self.scratchpad_versions.setTarget_(self)
        self.scratchpad_versions.setAction_("scratchpadVersionChosen:")
        v.addSubview_(self.scratchpad_versions)
        self._scratchpad_version_ids = []
        # The note-scope transform picker (S20 visible scope): one item
        # per enabled definition; the Transform… action resolves it.
        self.scratchpad_transforms = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(cw * 0.30 + cw * 0.44, 30, cw * 0.20, 24))
        v.addSubview_(self.scratchpad_transforms)
        self._scratchpad_transform_ids = []
        return v

    def scratchpadSearchChanged_(self, sender):
        self.state.set_scratchpad_search(
            sender.stringValue() or "")

    def scratchpadNew_(self, sender):
        svc = self.spec.get("notes_service")
        if svc is None:
            return
        try:
            out = svc.create_note("")
        except Exception as e:
            self.scratchpad_status.setStringValue_(
                f"new note failed: {type(e).__name__}")
            return
        self.state.views["scratchpad"]["search"] = ""
        self.scratchpad_search.setStringValue_("")
        self.state.reload_scratchpad()
        self.state.select_scratchpad_note(out["note_id"])

    def scratchpadPin_(self, sender):
        svc = self.spec.get("notes_service")
        note_id = self.state.views["scratchpad"].get("selected_id")
        detail = self.state.views["scratchpad"].get("detail") or {}
        if svc is None or not note_id:
            return
        try:
            svc.set_pinned(note_id, not detail.get("pinned"))
        except Exception as e:
            self.scratchpad_status.setStringValue_(
                f"pin failed: {type(e).__name__}")
            return
        self.state.reload_scratchpad()

    def scratchpadSnapshot_(self, sender):
        """Explicit snapshot: flush the buffer as trigger=explicit (an
        autosave-debounce revision never claims to be one)."""
        if self.editor.model is None:
            return
        out = self.editor.flush_now(trigger="explicit")
        self.scratchpad_status.setStringValue_(
            f"snapshot saved ({out.get('outcome')})")
        self.state.reload_scratchpad()

    def scratchpadAttach_(self, sender):
        from AppKit import NSOpenPanel
        svc = self.spec.get("notes_service")
        note_id = self.state.views["scratchpad"].get("selected_id")
        if svc is None or not note_id or self.editor.model is None:
            return
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(False)
        panel.setCanChooseFiles_(True)
        panel.setAllowsMultipleSelection_(False)
        if panel.runModal() != 1 or not panel.URLs():
            return
        url = panel.URLs()[0]
        try:
            import pathlib
            data = pathlib.Path(str(url.path())).read_bytes()
            mime = "image/" + (url.pathExtension() or "png").lower()
            out = svc.add_attachment(note_id, data, mime,
                                     str(url.lastPathComponent()))
            self.editor.insert_attachment_marker(out["marker"])
            self.state.reload_scratchpad()
        except Exception as e:
            self.scratchpad_status.setStringValue_(
                f"attachment failed: {type(e).__name__}")

    def scratchpadTransform_(self, sender):
        """Note-scope transform (S20): the definition chosen in the
        picker, applied to the selection — or the WHOLE NOTE when
        nothing is selected (accept then replaces the note's full
        range). Visible scope, through the M11 engine; never the M08
        external queue."""
        coordinator = self.coordinator
        if coordinator is None or self.editor.model is None:
            return
        idx = self.scratchpad_transforms.indexOfSelectedItem()
        chosen = self._scratchpad_transform_ids[idx] \
            if 0 <= idx < len(self._scratchpad_transform_ids) else None
        snapshot = coordinator._transforms_snapshot()
        defn = snapshot.by_id(chosen) if snapshot is not None else None
        if defn is None or not defn.enabled:
            self.scratchpad_status.setStringValue_(
                "choose a transform first")
            return
        source = self.editor.selected_text()
        rng = None
        if source is None:
            source = self.editor.current_content()
            rng = (0, len(source))  # whole-note scope: accept replaces
        else:
            # NSRange counts UTF-16 units; the captured range is in the
            # content's code points (what acceptance slices).
            rng = self.editor.selected_range()
        coordinator.tfRunNoteTransform(
            defn.transform_id, source, rng,
            {"note_id": self.editor.note_id,
             "revision_id": self.editor.model.revision_id})

    def scratchpadVersionChosen_(self, sender):
        # Selecting a version only arms the Restore button; restore is
        # the explicit action (AC02: a restore creates a revision, it
        # never discards the current one silently).
        pass

    def scratchpadRestore_(self, sender):
        svc = self.spec.get("notes_service")
        note_id = self.state.views["scratchpad"].get("selected_id")
        idx = self.scratchpad_versions.indexOfSelectedItem()
        if svc is None or not note_id:
            return
        if not (0 <= idx < len(self._scratchpad_version_ids)):
            self.scratchpad_status.setStringValue_(
                "choose a version first")
            return
        revision_id = self._scratchpad_version_ids[idx]
        # Persist the buffer first (bounded), then restore: the refresh
        # rebinds the editor to the restored revision (the rebind-when-
        # moved guard below) so the next keystroke cannot silently
        # revert the restore.
        if self.editor.model is not None and self.editor.note_id == note_id:
            self.editor.flush_now()
        try:
            svc.restore(note_id, revision_id)
        except Exception as e:
            self.scratchpad_status.setStringValue_(
                f"restore failed: {type(e).__name__}")
            return
        self.scratchpad_status.setStringValue_(
            "restored — the previous version stays in the history")
        self.state.reload_scratchpad()
        self.state.select_scratchpad_note(note_id)

    def _scratchpad_save_panel(self, default_name, fmt):
        from AppKit import NSSavePanel
        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_(default_name)
        if panel.runModal() != 1 or not panel.URL():
            return None
        return str(panel.URL().path())

    def scratchpadExportMD_(self, sender):
        self._scratchpad_export("markdown")

    def scratchpadExportTXT_(self, sender):
        self._scratchpad_export("plain")

    @objc.python_method
    def _scratchpad_export(self, fmt):
        coordinator = self.coordinator
        note_id = self.state.views["scratchpad"].get("selected_id")
        detail = self.state.views["scratchpad"].get("detail") or {}
        if coordinator is None or not note_id:
            return
        # Export the buffer the user sees: flush the debounce tail so
        # the last ≤1.5 s of edits are included.
        if self.editor.model is not None:
            self.editor.flush_now()
        from ..note_export import _slug
        title = _slug(detail.get("title") or "", "note")[:40]
        path = self._scratchpad_save_panel(
            f"{title}.{'md' if fmt == 'markdown' else 'txt'}", fmt)
        if path is None:
            return
        report = coordinator.hubExportNote(note_id, path, fmt)
        if report.get("ok"):
            n = len(report.get("unsupported") or [])
            self.scratchpad_status.setStringValue_(
                f"exported {report.get('bytes')} bytes"
                + (f" — {n} unsupported element(s) reported"
                   if n else ""))
        else:
            self.scratchpad_status.setStringValue_(
                f"export failed ({report.get('reason')}) — note kept")

    def scratchpadDelete_(self, sender):
        svc = self.spec.get("notes_service")
        coordinator = self.coordinator
        note_id = self.state.views["scratchpad"].get("selected_id")
        if svc is None or not note_id:
            return
        try:
            payload = svc.delete_note(note_id)
        except Exception as e:
            self.scratchpad_status.setStringValue_(
                f"delete failed: {type(e).__name__}")
            return
        if coordinator is not None:
            coordinator.hubNoteDeleted(payload)
        self.editor.clear()
        self.state.close_scratchpad_tab(note_id)
        self.state.reload_scratchpad()

    @objc.python_method
    def _refresh_scratchpad_view(self):
        view = self.state.views["scratchpad"]
        data = view.get("data")
        if view.get("error"):
            self.scratchpad_status.setStringValue_(
                f"notes unavailable ({view['error']})")
            self._render_rows("scratchpad_table", "note_id",
                              self.state.views["scratchpad"].get("selected_id"))
            return
        self._render_rows("scratchpad_table", "note_id",
                          self.state.views["scratchpad"].get("selected_id"))
        notes = (data or {}).get("notes") or []
        detail = view.get("detail")
        # Transform picker: rebuild from the frozen snapshot (ids ride
        # the parallel list — the title is display-only).
        self.scratchpad_transforms.removeAllItems()
        self._scratchpad_transform_ids = []
        snapshot = self.coordinator._transforms_snapshot() \
            if self.coordinator is not None else None
        for d in (snapshot.definitions if snapshot else []):
            if not d.enabled:
                continue
            self.scratchpad_transforms.addItemWithTitle_(d.name)
            self._scratchpad_transform_ids.append(d.transform_id)
        # Tab strip: rebuild chips for open notes.
        for sub in list(self.scratchpad_tabs.subviews()):
            sub.removeFromSuperview()
        open_ids = view.get("open_ids") or []
        by_id = {n["note_id"]: n for n in notes}
        for i, nid in enumerate(open_ids):
            title = (by_id.get(nid, {}).get("title") or "untitled")[:16]
            btn = _button(f"{title} ×", self, "scratchpadTabClose:",
                          NSMakeRect(i * 120.0, 0, 116.0, 22))
            btn.setTag_(i)
            self.scratchpad_tabs.addSubview_(btn)
        if detail is not None:
            wanted = detail["note_id"]
            current_rev = (detail.get("revision") or {}).get("revision_id")
            model = getattr(self.editor, "model", None)
            # Rebind when the NOTE changed, or when the persisted
            # revision moved under a CLEAN editor (restore, dictation
            # insert elsewhere). A dirty buffer is newer than the
            # store — it keeps the editor until its own flush lands.
            rebind = self.editor.note_id != wanted or (
                model is not None and not model.dirty
                and model.revision_id != current_rev)
            if rebind:
                self.editor.bind_note(detail)
            risk = detail.get("unsaved_tail_risk")
            if risk:
                self.scratchpad_status.setStringValue_(
                    "⚠ unsaved changes may have been lost — edits started "
                    f"{risk['editing_started_utc']}; last saved version "
                    f"({risk['last_saved_words']} words) shown below")
            else:
                atts = detail.get("attachments") or []
                self.scratchpad_status.setStringValue_(
                    f"{len(notes)} notes · {detail.get('word_count', 0)}"
                    f" words · {len(detail.get('versions') or [])}"
                    f" versions"
                    + (f" · {len(atts)} image(s)" if atts else ""))
            # Versions popup (newest first; restore copies content
            # forward — nothing is discarded).
            self.scratchpad_versions.removeAllItems()
            self._scratchpad_version_ids = []
            for ver in (detail.get("versions") or [])[1:]:
                label = (f"{ver['origin']}/{ver['trigger']} · "
                         f"{ver['word_count']}w · "
                         f"{(ver['created_at_utc'] or '')[11:19]}")
                self.scratchpad_versions.addItemWithTitle_(label)
                self._scratchpad_version_ids.append(ver["revision_id"])
        else:
            self.editor.clear()
            if not notes:
                self.scratchpad_status.setStringValue_(
                    "No notes yet — New (⌘N equivalent via the button) starts"
                    " one; dictation with this editor focused inserts at the"
                    " caret.")

    def scratchpadTabClose_(self, sender):
        view = self.state.views["scratchpad"]
        open_ids = view.get("open_ids") or []
        idx = int(sender.tag())
        if 0 <= idx < len(open_ids):
            # bind_note/clear flush the outgoing model's dirty tail, so
            # closing a tab never discards unsaved content.
            self.state.close_scratchpad_tab(open_ids[idx])
            self._refresh("scratchpad")

    # ---- scratchpad editor surface for the coordinator ---------------------

    @objc.python_method
    def scratchpad_editor_active(self):
        editor = getattr(self, "editor", None)
        return editor is not None and editor.editor_active()

    @objc.python_method
    def scratchpad_receive(self, text, job):
        """Coordinator command: a note-bound dictation's final text lands
        at the PTT-time anchor — the note captured at hotkey-down, at
        the insertion point captured then (the M08 discipline: the
        anchor promised at request time is the anchor that receives). A
        different note now open, or the note closed, returns False —
        the coordinator routes to saved_not_inserted, never an external
        paste."""
        from ..notes import ORIGIN_DICTATED
        editor = getattr(self, "editor", None)
        note_target = (job or {}).get("note_target") or {}
        if editor is None or editor.model is None:
            return False
        if editor.note_id != note_target.get("note_id"):
            return False
        return editor.receive(
            text, origin=ORIGIN_DICTATED,
            source_job_id=(job or {}).get("job_id"),
            at_chars=note_target.get("insertion_point"))

    @objc.python_method
    def scratchpad_apply_transform(self, result, capture):
        """Note-scope transform accept: revalidate the captured
        destination — the SAME note, and its captured text still at the
        captured range (a changed region or another open note is never
        written) — then replace exactly that region. A chained
        Transform Output carries the original destination unchanged.
        Returns (applied, reason)."""
        from ..notes import ORIGIN_TRANSFORM, note_destination_check
        editor = getattr(self, "editor", None)
        if editor is None or editor.model is None:
            return False, "note_not_open"
        dest = capture.get("destination")
        if dest is None and capture.get("range") is not None:
            # A capture recorded before destinations existed.
            dest = {"note_id": (capture.get("note") or {}).get("note_id"),
                    "range": capture.get("range"),
                    "text": capture.get("source")}
        ok, reason = note_destination_check(
            dest, editor.note_id, editor.current_content())
        if not ok:
            return False, reason
        rng = tuple(dest["range"])
        job = result.job
        ok = editor.receive(
            result.output, origin=ORIGIN_TRANSFORM,
            source_job_id=job.parent_job_id if job is not None else None,
            task_key=job.task_key() if job is not None else None,
            transform_id=job.transform_id if job is not None else None,
            transform_revision=(job.transform_revision
                                if job is not None else None),
            replace_range=rng)
        return (True, None) if ok else (False, "note_not_open")

    @objc.python_method
    def scratchpad_note_created(self, note_id):
        """A note was created outside the view (Save-to-Scratchpad,
        History copy/move): refresh and open it as the selected tab."""
        self.state.reload_scratchpad()
        self.state.select_scratchpad_note(note_id)

    @objc.python_method
    def scratchpad_quick_open(self):
        """Quick-open: select the Scratchpad view and start a fresh
        note ready for dictation (the focused editor is what binds the
        next dictation to the note)."""
        from .state import VIEWS
        self._select_view_index(VIEWS.index("scratchpad"))
        self.scratchpadNew_(None)
        try:
            self.window.makeFirstResponder_(self.editor.text)
        except Exception:
            pass

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
        """Export exactly the window on screen: the displayed records and
        filters are frozen here (main thread, no file parse); only the
        save panel runs here too; redaction and the write run off the
        main thread (M09-AUDIT-20). Redaction is the accepted typed
        allowlist (M09-AUDIT-08)."""
        from .. import diagnostics as diag
        # The window last drawn — a newer load not yet on screen is not
        # what the user is exporting.
        data = self._rendered.get("diagnostics")
        if not data:
            self._diag_note("Nothing to export: no event window is"
                            " displayed.")
            return
        records = list(data.get("records") or [])
        filters = dict(data.get("filters") or {})
        loaded = data.get("loaded_at_utc")
        try:
            from AppKit import NSSavePanel
            panel = NSSavePanel.savePanel()
            panel.setAllowedFileTypes_(["jsonl"])
            if panel.runModal() != 1 or panel.URL() is None:
                return
            path = str(panel.URL().path())
        except Exception as e:
            self._diag_note(f"Export needs a destination ({type(e).__name__}).")
            return
        window = (f"the window displayed at {loaded or 'load time'}"
                  f" — job {filters.get('job') or 'any'},"
                  f" level {filters.get('level') or 'all'},"
                  f" newest {filters.get('last')}")

        def done(n, err, current):
            if err is not None:
                self._diag_note(
                    f"Export failed ({type(err).__name__}); the file at"
                    f" {path} may be incomplete.")
                return
            self._diag_note(f"Wrote {n} redacted events ({window}) to"
                            f" {path}.")
        self._in_background(lambda: diag.redacted_export(records, path),
                            done, key="diag_export")

    @objc.python_method
    def _diag_note(self, note):
        if getattr(self, "diag_text", None) is None:
            return
        self.diag_text.setString_(f"{note}\n\n{self.diag_text.string()}")

    @objc.python_method
    def _refresh_diagnostics_view(self):
        view = self.state.views["diagnostics"]
        data = view.get("data")
        self._rendered["diagnostics"] = None
        if view.get("error"):
            self.diag_text.setString_(f"query failed: {view['error']}")
            return
        if not data:
            self.diag_text.setString_(
                "No events loaded. Set filters and reload.")
            return
        self._rendered["diagnostics"] = data
        lines = ["— engines / build —"]
        for k, val in sorted((data.get("engine") or {}).items()):
            lines.append(f"{k}: {val}")
        timeline = data.get("timeline") or []
        if timeline:
            lines.append("")
            lines.append("— job timeline ("
                         f"{(data.get('filters') or {}).get('job')}) —")
            lines.extend(timeline)
        lines.append("")
        lines.append(f"— events ({data.get('count')}) —")
        if data.get("skipped_lines"):
            lines.append(f"({data['skipped_lines']} unreadable log lines"
                         " skipped)")
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
        self._training_evidence_views = []
        # M14 (S29.15): the Training Data pane's sections — evidence
        # (the M09 inspector), review (queue + classification),
        # splits, export — one surface, four tabs.
        self.training_tab_buttons = []
        x = 260
        for i, title in enumerate(("Evidence", "Review", "Splits",
                                   "Export")):
            b = _button(title, self, "trainingTab:",
                        NSMakeRect(x, ch - 28, 84, 22))
            b.setTag_(i)
            self.training_tab_buttons.append(b)
            p.addSubview_(b)
            x += 88
        self.training_search = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(8, ch - 28, 240, 24))
        self.training_search.setTarget_(self)
        self.training_search.setAction_("trainingSearchChanged:")
        self.training_search.setPlaceholderString_("Search evidence")
        p.addSubview_(self.training_search)
        self._training_evidence_views.append(self.training_search)
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
        self._training_evidence_views.append(tsc)
        self.training_detail = _textview(NSMakeRect(0, 0, cw * 0.5, 100))
        dsc = _scroll(NSMakeRect(cw * 0.44, 150, cw * 0.56 - 8, ch - 182),
                      self.training_detail)
        dsc.setAutoresizingMask_(18 | 16)
        p.addSubview_(dsc)
        self._training_evidence_views.append(dsc)
        self.training_ready = _label(NSMakeRect(8, ch - 56, cw - 16, 20),
                                     "")
        p.addSubview_(self.training_ready)
        self._training_evidence_views.append(self.training_ready)
        for i, (title, action) in enumerate((
                ("Mark Correct", "trainingMarkCorrect:"),
                ("Mark Incorrect", "trainingMarkIncorrect:"),
                ("Pin/Unpin", "trainingPin:"),
                ("Exclude/Include", "trainingExclude:"),
                ("Delete Everywhere", "trainingDelete:"))):
            b = _button(title, self, action,
                        NSMakeRect(8 + i * 150, 118, 144, 24))
            p.addSubview_(b)
            self._training_evidence_views.append(b)
        p.addSubview_(_label(NSMakeRect(8, 92, 150, 18),
                             "Verbatim (replay first):"))
        self.verbatim_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(160, 90, 300, 22))
        p.addSubview_(self.verbatim_field)
        self._training_evidence_views.append(self.verbatim_field)
        b = _button("Save Verbatim", self, "trainingVerbatim:",
                    NSMakeRect(468, 89, 130, 24))
        p.addSubview_(b)
        self._training_evidence_views.append(b)
        b = _button("Replay Audio", self, "trainingReplay:",
                    NSMakeRect(606, 89, 120, 24))
        p.addSubview_(b)
        self._training_evidence_views.append(b)
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
            self._training_evidence_views.append(sub)
        b = _button("Save Span", self, "trainingSpan:",
                    NSMakeRect(650, 61, 110, 24))
        p.addSubview_(b)
        self._training_evidence_views.append(b)
        self._build_training_review_pane(p, cw, ch)
        self._build_training_splits_pane(p, cw, ch)
        self._build_training_export_pane(p, cw, ch)
        return p

    # ---- Training Data: Review / Splits / Export (M14) ----------------------

    def trainingTab_(self, sender):
        from .state import TRAINING_TABS
        self.state.select_training_tab(TRAINING_TABS[int(sender.tag())])

    def _build_training_review_pane(self, p, cw, ch):
        self.review_pane = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw, ch - 34))
        self.review_pane.setAutoresizingMask_(18 | 16)
        self.review_status = _label(NSMakeRect(8, ch - 58, cw - 16, 20),
                                    "")
        self.review_pane.addSubview_(self.review_status)
        self.review_text = _textview(NSMakeRect(0, 0, cw - 16, 100))
        sc = _scroll(NSMakeRect(8, 108, cw - 16, ch - 172),
                     self.review_text)
        sc.setAutoresizingMask_(18 | 16)
        self.review_pane.addSubview_(sc)
        b = _button("Draw Sample", self, "reviewSample:",
                    NSMakeRect(8, 78, 110, 24))
        self.review_pane.addSubview_(b)
        b = _button("Mine Candidates", self, "reviewMine:",
                    NSMakeRect(124, 78, 130, 24))
        self.review_pane.addSubview_(b)
        p.addSubview_(self.review_pane)
        # Candidate decision row: the selected queue row's candidate
        # approves (through the vocabulary store) or rejects.
        self.review_counter = NSTextField.alloc().initWithFrame_(
            NSMakeRect(260, 76, 300, 22))
        self.review_counter.setPlaceholderString_(
            "counterexample phrase (optional)")
        self.review_pane.addSubview_(self.review_counter)
        b = _button("Approve Cand.", self, "reviewApprove:",
                    NSMakeRect(568, 77, 118, 24))
        self.review_pane.addSubview_(b)
        b = _button("Reject Cand.", self, "reviewReject:",
                    NSMakeRect(692, 77, 110, 24))
        self.review_pane.addSubview_(b)
        # Label row: record a reviewed classification on the selected
        # example (the evidence list selection drives it).
        self.review_kind = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(8, 46, 190, 24))
        from ..curation.classify import AXIS_EDIT_KINDS
        self.review_kind.addItemsWithTitles_(list(AXIS_EDIT_KINDS))
        self.review_pane.addSubview_(self.review_kind)
        self.review_example = NSTextField.alloc().initWithFrame_(
            NSMakeRect(204, 46, 240, 22))
        self.review_example.setPlaceholderString_("example id")
        self.review_pane.addSubview_(self.review_example)
        b = _button("Record Label", self, "reviewLabel:",
                    NSMakeRect(452, 47, 118, 24))
        self.review_pane.addSubview_(b)
        b = _button("Pair: prefer A", self, "reviewPairA:",
                    NSMakeRect(8, 16, 110, 24))
        self.review_pane.addSubview_(b)
        b = _button("prefer B", self, "reviewPairB:",
                    NSMakeRect(122, 16, 90, 24))
        self.review_pane.addSubview_(b)
        b = _button("tie", self, "reviewPairTie:",
                    NSMakeRect(216, 16, 60, 24))
        self.review_pane.addSubview_(b)
        b = _button("neither", self, "reviewPairNeither:",
                    NSMakeRect(280, 16, 84, 24))
        self.review_pane.addSubview_(b)
        b = _button("uncertain", self, "reviewPairUncertain:",
                    NSMakeRect(368, 16, 90, 24))
        self.review_pane.addSubview_(b)
        self.review_pair_task = NSTextField.alloc().initWithFrame_(
            NSMakeRect(462, 14, 200, 22))
        self.review_pair_task.setPlaceholderString_("preference task key")
        self.review_pane.addSubview_(self.review_pair_task)

    def _build_training_splits_pane(self, p, cw, ch):
        self.splits_pane = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw, ch - 34))
        self.splits_pane.setAutoresizingMask_(18 | 16)
        self.splits_status = _label(NSMakeRect(8, ch - 58, cw - 16, 20),
                                    "")
        self.splits_pane.addSubview_(self.splits_status)
        self.splits_text = _textview(NSMakeRect(0, 0, cw - 16, 100))
        sc = _scroll(NSMakeRect(8, 64, cw - 16, ch - 128),
                     self.splits_text)
        sc.setAutoresizingMask_(18 | 16)
        self.splits_pane.addSubview_(sc)
        b = _button("Assign (new version)", self, "splitsAssign:",
                    NSMakeRect(8, 32, 160, 24))
        self.splits_pane.addSubview_(b)
        self.splits_family = NSTextField.alloc().initWithFrame_(
            NSMakeRect(176, 32, 220, 22))
        self.splits_family.setPlaceholderString_("family id to expose")
        self.splits_pane.addSubview_(self.splits_family)
        b = _button("Mark Exposed", self, "splitsExpose:",
                    NSMakeRect(402, 33, 118, 24))
        self.splits_pane.addSubview_(b)
        p.addSubview_(self.splits_pane)

    def _build_training_export_pane(self, p, cw, ch):
        self.export_pane = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw, ch - 34))
        self.export_pane.setAutoresizingMask_(18 | 16)
        self.export_status = _label(NSMakeRect(8, ch - 58, cw - 16, 20),
                                    "")
        self.export_pane.addSubview_(self.export_status)
        self.export_text = _textview(NSMakeRect(0, 0, cw - 16, 100))
        sc = _scroll(NSMakeRect(8, 92, cw - 16, ch - 156),
                     self.export_text)
        sc.setAutoresizingMask_(18 | 16)
        self.export_pane.addSubview_(sc)
        self.export_checks = {}
        for i, view in enumerate(("asr_supervised", "cleanup_supervised",
                                  "preference_pairs",
                                  "asr_span_graft_weak",
                                  "transform_supervised")):
            from AppKit import NSButtonTypeSwitch
            cb = NSButton.alloc().initWithFrame_(
                NSMakeRect(8 + i * 190, 60, 186, 22))
            cb.setButtonType_(NSButtonTypeSwitch)
            cb.setTitle_(view)
            cb.setState_(1 if i < 3 else 0)
            self.export_checks[view] = cb
            self.export_pane.addSubview_(cb)
        self.export_dest = NSTextField.alloc().initWithFrame_(
            NSMakeRect(8, 30, 460, 22))
        self.export_dest.setPlaceholderString_(
            "export destination directory")
        self.export_pane.addSubview_(self.export_dest)
        b = _button("Export", self, "exportRun:",
                    NSMakeRect(476, 31, 90, 24))
        self.export_pane.addSubview_(b)
        b = _button("Validate", self, "exportValidate:",
                    NSMakeRect(572, 31, 96, 24))
        self.export_pane.addSubview_(b)
        p.addSubview_(self.export_pane)

    def trainingSearchChanged_(self, sender):
        self.state.set_training_search(sender.stringValue() or "")

    @objc.python_method
    def _selected_example_id(self):
        return self.state.views["models"].get("selected_id")

    @objc.python_method
    def _training_ctx(self, quiet=False):
        """The action context: the RENDERED detail of the selected
        example — or None, with the reason shown, while the selection's
        detail is still loading, failed, or a newer publication is not
        yet on screen. Judgments are only ever attached to the example
        whose text the user is looking at (M09-AUDIT-01)."""
        view = self.state.views["models"]
        rendered = self._rendered.get("training_detail")
        sel = view.get("selected_id")
        if rendered is None or rendered is not view.get("detail") \
                or rendered.get("example_id") != sel \
                or view.get("detail_key") != sel:
            if not quiet:
                self._training_note("Select an example and wait for its"
                                    " detail to load before acting on it.")
            return None
        return rendered

    @objc.python_method
    def _training_note(self, note):
        if getattr(self, "training_detail", None) is None:
            return
        base = self._training_pane_text()
        self.training_detail.setString_(f"{base}\n\n{note}" if base
                                        else note)

    @objc.python_method
    def _clear_training_editors(self):
        for name in ("verbatim_field", "span_start", "span_end",
                     "span_corrected"):
            field = getattr(self, name, None)
            if field is not None:
                field.setStringValue_("")
        self._editor_bound = None

    @objc.python_method
    def _annotation_id(self, ctx, kind, text):
        """A stable operation id per (example, kind, text): a save whose
        outcome was unknown (the caller's wait timed out) is retried
        with the SAME id, so a late commit is never duplicated."""
        from .. import ids
        key = (ctx["example_id"], kind, ids.sha256_text(text))
        pending = self._pending_annotation
        if pending is not None and pending["key"] == key:
            return pending["annotation_id"]
        self._pending_annotation = {"key": key, "job_id": ctx.get("job_id"),
                                    "annotation_id": ids.new_id("ann")}
        return self._pending_annotation["annotation_id"]

    @objc.python_method
    def _in_background(self, work, done, key=None):
        """Run a long curation action (export, mining, generation) off
        the AppKit main thread so the Hub stays responsive;
        ``done(out, err, current)`` runs back on the main thread.
        ``current`` is False when a newer action with the same ``key``
        started since (its result must not overwrite the newer one's
        status). The services' writes go through the store's writer
        like any other caller."""
        import threading
        token = None
        if key is not None:
            self._action_seq += 1
            token = self._action_seq
            self._action_tokens[key] = token

        def run():
            try:
                out, err = work(), None
            except Exception as e:
                out, err = None, e
            AppHelper.callAfter(self._finish_action, done, key, token,
                                out, err)
        threading.Thread(target=run, daemon=True,
                         name="localflow-hub-work").start()
        return token

    @objc.python_method
    def _finish_action(self, done, key, token, out, err):
        current = key is None or self._action_tokens.get(key) == token
        done(out, err, current)

    @objc.python_method
    def _on_training_tab(self, tab):
        view = self.state.views["models"]
        return (self.state.selected_view == "models"
                and view.get("subview") == "training"
                and view.get("training_tab") == tab)

    def _training_action(self, fn, *args, **kwargs):
        """Run one inspector/curation mutation; failures and refusals
        surface as text in the section on screen (the Training Data
        tab showing, or Your Voice) instead of escaping the action
        handler. Service refusal messages are content-free ids and
        reasons, so the reason is shown with the type."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            view = self.training_detail
            if self.state.selected_view == "insights":
                view = self.voice_pane.text
            else:
                tab = self.state.views["models"].get("training_tab")
                view = {"review": getattr(self, "review_text", view),
                        "splits": getattr(self, "splits_text", view),
                        "export": getattr(self, "export_text", view)
                        }.get(tab, view)
            if isinstance(e, TimeoutError):
                # The store was busy; the change may still commit.
                view.setString_("outcome unknown: the store is busy and the"
                                " change may still complete — check this"
                                " item before repeating it.")
            else:
                view.setString_(f"action failed: {type(e).__name__}: {e}")
            return None

    def trainingMarkCorrect_(self, sender):
        self._mark_intended(True)

    def trainingMarkIncorrect_(self, sender):
        self._mark_intended(False)

    @objc.python_method
    def _mark_intended(self, correct):
        ctx = self._training_ctx()
        if ctx is None:
            return
        ex = ctx["example_id"]
        if self._training_action(
                self.spec["training_service"].mark_intended, ex, correct) \
                is not None:
            self.state.select_training_example(ex)

    def trainingPin_(self, sender):
        ctx = self._training_ctx()
        if ctx is None:
            return
        ex = ctx["example_id"]
        if self._training_action(
                self.spec["training_service"].pin, ex,
                not ctx.get("pinned")) is not None:
            self.state.select_training_example(ex)

    def trainingExclude_(self, sender):
        ctx = self._training_ctx()
        if ctx is None:
            return
        ex = ctx["example_id"]
        want = ctx.get("state") != "excluded"
        new = self._training_action(
            self.spec["training_service"].exclude, ex, want)
        if new is None:
            return
        self.state.select_training_example(ex)
        if want != (new == "excluded"):
            # The service keeps deleted/expired/quarantined authoritative
            # in both directions (M09-AUDIT-04): say so.
            self._training_note(
                f"{'Exclude' if want else 'Include'} refused: the example"
                f" is {new}.")

    def trainingDelete_(self, sender):
        ctx = self._training_ctx()
        if ctx is None:
            return
        # The identity the user confirms is captured BEFORE the modal: a
        # selection change while it is open cannot redirect the delete.
        ex = ctx["example_id"]
        try:
            from AppKit import NSAlert
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Delete this example everywhere?")
            alert.setInformativeText_(
                f"Example {ex[:24]}… — revokes every lease and purges"
                " audio, transcripts and derived records. Only a"
                " content-free tombstone remains.")
            alert.setAlertStyle_(NSAlertStyleWarning)
            alert.addButtonWithTitle_("Delete Everywhere")
            alert.addButtonWithTitle_("Cancel")
            if alert.runModal() != NSAlertFirstButtonReturn:
                return
        except Exception as e:
            # No confirmation, no delete: this cannot be undone.
            self._training_note(f"Delete needs a confirmation that could"
                                f" not be shown ({type(e).__name__}); nothing"
                                " was deleted.")
            return
        self._delete_example(ex)

    @objc.python_method
    def _delete_example(self, ex=None):
        if ex is None:
            ctx = self._training_ctx(quiet=True)
            ex = ctx["example_id"] if ctx else self._selected_example_id()
        if not ex:
            return
        if self._training_action(
                self.spec["training_service"].delete_everywhere, ex) \
                is None:
            return
        # The store listener has already revoked the job in the state
        # and replay; what this pane shows goes now, on the main thread.
        rendered = self._rendered.get("training_detail")
        if rendered is not None and rendered.get("example_id") == ex:
            self._rendered["training_detail"] = None
            self._clear_training_editors()
            self.training_detail.setString_("This example was deleted.")
        if self._selected_example_id() == ex:
            self.state.select_training_example(None)
        self.state.reload_training()

    def trainingReplay_(self, sender):
        ctx = self._training_ctx()
        if ctx is None:
            return
        audio = ctx.get("audio") or {}
        if self.replay is None or not audio.get("available"):
            if self.replay is not None:
                self.replay.stop()
            self._training_note(
                "audio unavailable ("
                + (audio.get("reason") or "no artifact") + ")")
            return
        out = self.replay.play_artifact(self.spec["store"],
                                        audio.get("artifact_id"))
        if out.get("status") == "playing":
            # The verbatim gate opens only for THIS example's successful
            # playback start (E14) — bound to the rendered, selected
            # example; a start is not proof the whole recording was
            # heard (the contract's playback-start gate).
            if self._training_ctx(quiet=True) is ctx:
                self.state.views["models"]["listened_for"] = \
                    ctx["example_id"]
        else:
            self._training_note(
                "replay unavailable (" + str(out.get("reason")) + ")")

    _UNKNOWN_SAVE = ("save outcome unknown: the store is busy and the save"
                     " may still complete. Saving the same text again will"
                     " not duplicate it.")

    def trainingVerbatim_(self, sender):
        text = self.verbatim_field.stringValue() or ""
        if not text:
            return
        ctx = self._training_ctx()
        if ctx is None:
            return
        ex = ctx["example_id"]
        listened = (self.state.views["models"].get("listened_for") == ex)
        ann_id = self._annotation_id(ctx, "verbatim", text)
        try:
            self.spec["training_service"].set_verbatim(
                ex, text, listened_audio=listened, annotation_id=ann_id)
        except TimeoutError:
            self._training_note("verbatim " + self._UNKNOWN_SAVE)
            return
        except Exception as e:  # refused or failed: nothing committed
            self._pending_annotation = None
            reason = _refusal_text(e)
            hint = (" — replay this example's audio first"
                    if reason and "listen_before_verbatim" in reason else "")
            self._training_note("verbatim not saved: "
                                + (reason or type(e).__name__) + hint)
            return
        self._pending_annotation = None
        self.state.views["models"]["listened_for"] = None
        self.state.select_training_example(ex)

    def trainingSpan_(self, sender):
        try:
            start = int(self.span_start.stringValue())
            end = int(self.span_end.stringValue())
        except ValueError:
            self._training_note("span start/end must be code-point"
                                " integers")
            return
        corrected = self.span_corrected.stringValue() or ""
        stage = self.span_stage.titleOfSelectedItem() or "source_text"
        if not corrected:
            return
        ctx = self._training_ctx()
        if ctx is None:
            return
        ex = ctx["example_id"]
        # The exact stage text the user reviewed: its immutable artifact
        # and hash travel into the writer op (M09-AUDIT-06).
        reviewed = next((s for s in ctx.get("stages") or []
                         if s.get("stage") == stage and s.get("available")),
                        None)
        if reviewed is None:
            self._training_note(f"span not saved: the {stage} text is not"
                                " available")
            return
        from .. import ids
        ann_id = self._annotation_id(ctx, f"span:{stage}:{start}:{end}",
                                     corrected)
        try:
            self.spec["training_service"].add_span_correction(
                ex, stage, start, end, corrected,
                expected_artifact_id=reviewed["artifact_id"],
                expected_sha256=ids.sha256_text(reviewed["text"]),
                annotation_id=ann_id)
        except TimeoutError:
            self._training_note("span " + self._UNKNOWN_SAVE)
            return
        except Exception as e:  # refused (stale, not reviewable) or failed
            self._pending_annotation = None
            self._training_note("span not saved: "
                                + (_refusal_text(e) or type(e).__name__))
            return
        self._pending_annotation = None
        self.state.select_training_example(ex)

    # ---- Training Data M14 actions -------------------------------------------

    def reviewSample_(self, sender):
        svc = self.spec.get("sampling_service")
        if svc is None:
            return
        out = self._training_action(svc.refresh)
        if out is not None:
            self.state.select_training_tab("review")

    def reviewMine_(self, sender):
        svc = self.spec.get("learning_service")
        if svc is None:
            return
        self.review_text.setString_("mining observations…")

        def done(_out, err, current):
            # A late completion reports under its own action and never
            # navigates: the user may have moved on (M09-AUDIT-21).
            if not current:
                return
            on_review = self._on_training_tab("review")
            if err is not None:
                msg = f"action failed: {type(err).__name__}: {err}"
                if on_review:
                    self.review_text.setString_(msg)
                else:
                    self._action_notes["review"] = "mining " + msg
                return
            if on_review:
                self.state.reload_training()
            else:
                self._action_notes["review"] = \
                    "mining finished — the review queue was updated"
        self._in_background(svc.mine_observation_candidates, done,
                            key="mine")

    @objc.python_method
    def _selected_queue_row(self):
        """The queue row an Approve/Reject acts on: the selected
        example's row in the RENDERED queue — refused with no selection,
        when the selection has no row, and while a newer queue is not
        yet on screen, so nothing but the chosen row is ever acted on."""
        view = self.state.views["models"]
        current = (view.get("data") or {}).get("queue")
        rows = self._rendered_rows.get("review_queue")
        if rows is None or current is not self._rendered.get(
                "review_queue_src"):
            self.review_text.setString_(
                "The review queue is refreshing — try again.")
            return None
        sel = view.get("selected_id")
        if not sel:
            # Only the row the user chose — never a first-row default.
            self.review_text.setString_(
                "Select the example to approve or reject in Evidence"
                " first; nothing was approved or rejected.")
            return None
        for row in rows:
            if row.get("example_id") == sel:
                return row
        self.review_text.setString_(
            "The example selected in Evidence has no row in the review"
            " queue, so nothing was approved or rejected.")
        return None

    def reviewApprove_(self, sender):
        learning = self.spec.get("learning_service")
        if learning is None:
            return
        row = self._selected_queue_row()
        counter = (self.review_counter.stringValue() or "").strip()
        if row is None:
            return
        if not row.get("candidate_id"):
            self.review_text.setString_(
                "no pending candidate for the selected queue row")
            return
        out = self._training_action(
            learning.approve, row["candidate_id"],
            counterexamples=((counter,) if counter else ()))
        if out is None:
            return  # the refusal reason stays on screen
        if out.get("flips"):
            self.review_text.setString_(
                "approval REFUSED — the rule would flip the"
                " counterexample:\n"
                + "\n".join(f"  {f['phrase']} → {f['applied']}"
                            for f in out["flips"]))
            return
        self.state.select_training_tab("review")

    def reviewReject_(self, sender):
        learning = self.spec.get("learning_service")
        if learning is None:
            return
        row = self._selected_queue_row()
        if row is None:
            return
        if not row.get("candidate_id"):
            self.review_text.setString_(
                "no pending candidate for the selected queue row")
            return
        if self._training_action(learning.reject,
                                 row["candidate_id"]) is None:
            return
        self.state.select_training_tab("review")

    def reviewLabel_(self, sender):
        review = self.spec.get("review_service")
        # A typed id is explicit; otherwise the RENDERED example — never
        # a selection whose detail is not on screen yet.
        ex = (self.review_example.stringValue() or "").strip() \
            or (self._training_ctx(quiet=True) or {}).get("example_id")
        if review is None or not ex:
            return
        kind = self.review_kind.titleOfSelectedItem() or "unknown"
        out = self._training_action(
            review.record_label, ex, edit_kind=kind)
        if out is not None:
            self.state.select_training_tab("review")

    def _review_pair_judgment(self, judgment):
        review = self.spec.get("review_service")
        tf_store = self.spec.get("transforms_store")
        task = (self.review_pair_task.stringValue() or "").strip()
        if review is None or tf_store is None or not task:
            return
        pairs = self._training_action(review.preference_pairs) or []
        pair = next((p for p in pairs if p["task_key"] == task), None)
        if pair is None or len(pair["candidates"]) < 2:
            self.review_text.setString_(
                f"no same-task candidate pair found for {task}")
            return
        a, b = (pair["candidates"][0]["candidate_id"],
                pair["candidates"][1]["candidate_id"])
        self._training_action(
            review.record_pair_judgment, tf_store, task, a, b, judgment)
        self.state.select_training_tab("review")

    def reviewPairA_(self, sender):
        self._review_pair_judgment("prefer_a")

    def reviewPairB_(self, sender):
        self._review_pair_judgment("prefer_b")

    def reviewPairTie_(self, sender):
        self._review_pair_judgment("tie")

    def reviewPairNeither_(self, sender):
        self._review_pair_judgment("neither")

    def reviewPairUncertain_(self, sender):
        self._review_pair_judgment("uncertain")

    def splitsAssign_(self, sender):
        svc = self.spec.get("splits_service")
        if svc is not None and \
                self._training_action(svc.assign) is not None:
            self.state.select_training_tab("splits")

    def splitsExpose_(self, sender):
        svc = self.spec.get("splits_service")
        family = (self.splits_family.stringValue() or "").strip()
        if svc is not None and family and self._training_action(
                svc.mark_exposed, [family],
                "inspected_during_tuning") is not None:
            self.state.select_training_tab("splits")

    def exportRun_(self, sender):
        svc = self.spec.get("export_service")
        if svc is None:
            return
        views = [v for v, cb in self.export_checks.items()
                 if cb.state()]
        dest = (self.export_dest.stringValue() or "").strip()
        if not dest or not views:
            self.export_text.setString_(
                "choose at least one task view and a destination"
                " directory")
            return
        self.export_text.setString_("exporting…")

        def done(out, err, current):
            # An older export finishing after a newer one started keeps
            # its own record (export history) but never takes over the
            # current status (M09-AUDIT-21).
            if not current:
                return
            if err is not None:
                # The refusal reason stays on screen (no reload over it).
                msg = f"action failed: {type(err).__name__}: {err}"
            else:
                counts = json.dumps(out.get("counts") or {},
                                    sort_keys=True)
                msg = (f"export {out['state']} · {out['export_id']}\n"
                       f"counts: {counts}\nfingerprint:"
                       f" {(out.get('fingerprint') or '')[:16]}…")
            if self._on_training_tab("export"):
                self.export_text.setString_(msg)
                if err is None:
                    self.state.reload_training()
            else:
                self._action_notes["export"] = msg
        self._in_background(
            lambda: svc.build(dest, task_views=views), done, key="export")

    def exportValidate_(self, sender):
        from ..curation.export import validate_dataset
        dest = (self.export_dest.stringValue() or "").strip()
        if not dest:
            return
        report = self._training_action(validate_dataset, dest)
        if report is not None:
            self.export_text.setString_(
                f"valid: {report['valid']}\n"
                + ("\n".join(report["issues"])
                   if report["issues"] else "all checks passed"))

    @objc.python_method
    def _apply_training_tab(self, tab):
        for v in self._training_evidence_views:
            v.setHidden_(tab != "evidence")
        self.review_pane.setHidden_(tab != "review")
        self.splits_pane.setHidden_(tab != "splits")
        self.export_pane.setHidden_(tab != "export")
        from .state import TRAINING_TABS
        for i, b in enumerate(self.training_tab_buttons):
            b.setEnabled_(TRAINING_TABS[i] != tab)

    @objc.python_method
    def _training_pane_text(self):
        view = self.state.views["models"]
        if view.get("selected_id") is None:
            return self._render_training_detail(None)
        rendered = self._rendered.get("training_detail")
        if rendered is not None:
            return self._render_training_detail(rendered)
        if view.get("detail_loading"):
            return "Loading the selected example…"
        err = view.get("detail_error")
        if err == "deleted":
            return "This example was deleted."
        if err:
            return f"This example's detail could not load ({err})."
        return self._render_training_detail(None)

    @objc.python_method
    def _refresh_models_view(self):
        view = self.state.views["models"]
        is_training = view.get("subview", "engines") == "training"
        self.training_pane.setHidden_(not is_training)
        self.models_text.setHidden_(is_training)
        self.models_tabs.setSelectedSegment_(1 if is_training else 0)
        if is_training:
            data = view.get("data") or {}
            tab = data.get("training_tab") or \
                view.get("training_tab") or "evidence"
            self._apply_training_tab(tab)
            ready = data.get("readiness") or {}
            cov = ready.get("dataset_coverage") or {}
            if view.get("error"):
                # A failed refresh never passes for a fresh success.
                status = (f"Training Data refresh failed ({view['error']})"
                          + (" — showing the rows from the last successful"
                             " load" if data else ""))
            elif view.get("loading") and not data:
                status = "Loading training data…"
            else:
                status = (
                    f"{len(data.get('examples') or [])} examples · audio "
                    f"{cov.get('retained_audio_examples')} · verbatim "
                    f"{cov.get('verbatim_reviewed_examples')} · spans "
                    f"{cov.get('span_annotations')} · unreviewed "
                    f"{cov.get('unreviewed_outcomes')} · storage "
                    f"{(ready.get('storage_bytes') or 0) // 1024} KiB")
            self.training_ready.setStringValue_(status)
            if tab == "review":
                self._refresh_review_pane(data)
            elif tab == "splits":
                self._refresh_splits_pane(data)
            elif tab == "export":
                self._refresh_export_pane(data)
            else:
                sel = view.get("selected_id")
                self._render_rows("training_table", "example_id", sel)
                detail = view.get("detail")
                self._rendered["training_detail"] = detail \
                    if detail is not None and view.get("detail_key") == sel \
                    and detail.get("example_id") == sel else None
                rendered = self._rendered["training_detail"]
                # Editor buffers belong to the example AND the stage
                # texts they were typed against: another example, or a
                # new stage text under the same example, never inherits
                # them (a revision leaving the stages alone keeps them).
                shown = None if rendered is None else (
                    rendered.get("example_id"),
                    tuple(sorted((s.get("stage"), s.get("artifact_id"))
                                 for s in rendered.get("stages") or []
                                 if s.get("available"))))
                cleared_typing = False
                if shown != self._editor_bound:
                    if self._editor_bound is not None:
                        cleared_typing = shown is not None and \
                            shown[0] == self._editor_bound[0] and any(
                                getattr(self, n).stringValue()
                                for n in ("verbatim_field",
                                          "span_corrected"))
                        self._clear_training_editors()
                    self._editor_bound = shown
                self.training_detail.setString_(self._training_pane_text())
                if cleared_typing:
                    self._training_note(
                        "This example's text changed, so the correction"
                        " fields were cleared — nothing typed against the"
                        " old text is saved.")
        else:
            if view.get("error"):
                self.models_text.setString_(
                    f"Engine status could not load ({view['error']}).")
                return
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
    def _refresh_review_pane(self, data):
        queue = data.get("queue") or []
        # The queue as rendered: Approve/Reject resolve against it.
        self._rendered["review_queue_src"] = data.get("queue")
        self._rendered_rows["review_queue"] = list(queue)
        coverage = data.get("coverage") or {}
        strata = json.dumps(coverage.get("by_stratum") or {},
                            sort_keys=True)
        note = self._action_notes.pop("review", None)
        self.review_status.setStringValue_(
            f"{len(queue)} review rows · strata {strata}"
            + (f" · {note}" if note else ""))
        lines = ["— review queue —"]
        for row in queue[:60]:
            cls = row.get("classification") or {}
            sug = row.get("suggestion")
            lines.append(
                f"{row['example_id'] or row['job_id']}  [{row['kind']}"
                f"{'/' + row['candidate_status'] if row.get('candidate_status') else ''}]"
                f"  axes: {cls.get('edit_kind')}"
                f" {cls.get('origin_stages')}"
                f"{' abstain' if cls.get('abstained') else ''}"
                + (f"  suggest: {sug['alias']} → {sug['canonical']}"
                   if sug else "")
                + ("  [labeled]" if row.get("labeled") else ""))
        pairs = data.get("preference_pairs") or []
        if pairs:
            lines.append("\n— same-task candidate pairs —")
            for pair in pairs[:20]:
                lines.append(
                    f"{pair['task_key'][:20]}… candidates"
                    f" {len(pair['candidates'])} · judgment: "
                    f"{pair.get('comparable_judgment') or 'unreviewed'}")
        self.review_text.setString_("\n".join(lines))

    @objc.python_method
    def _refresh_splits_pane(self, data):
        summary = data.get("summary") or {}
        if not summary.get("assignment_version"):
            self.splits_status.setStringValue_("No assignment yet")
            self.splits_text.setString_(
                "No families are assigned. Assign creates a versioned"
                " 80/10/10 family-level split (unassigned below the"
                " minimum family count, with the reason).")
            return
        self.splits_status.setStringValue_(
            f"v{summary['assignment_version']} · {summary['policy']}"
            f" · {summary['families']} families · exposed"
            f" {summary.get('exposed_families', 0)}")
        cont = data.get("contamination") or {}
        lines = ["— families —"]
        for fam in (data.get("families") or [])[:60]:
            lines.append(f"{fam['family_id']}  {fam['partition']}"
                         f"  ×{fam['examples']}"
                         + ("  EXPOSED" if fam["exposed"] else ""))
        lines.append("\n— contamination —")
        lines.append(json.dumps(cont, sort_keys=True, indent=1))
        self.splits_text.setString_("\n".join(lines))

    @objc.python_method
    def _refresh_export_pane(self, data):
        last = data.get("last_export")
        note = self._action_notes.pop("export", None)
        if note:
            self.export_status.setStringValue_("Export finished while you"
                                               " were away")
            self.export_text.setString_(note)
            return
        if not last:
            self.export_status.setStringValue_("No export run yet")
            self.export_text.setString_(
                "Choose task views and a destination directory, then"
                " Export. The dataset builds into a staging directory"
                " and finalizes atomically; Validate runs the"
                " standalone validator over the written files.")
            return
        self.export_status.setStringValue_(
            f"last export {last['state']} ·"
            f" {(last.get('finalized_at_utc') or '')[:19]}")
        self.export_text.setString_(
            f"export {last['export_id']}\nstate {last['state']}"
            f" · views {', '.join(last.get('task_views') or [])}\n"
            f"examples {last.get('examples_count')} · excluded"
            f" {last.get('excluded_count')}\nfingerprint"
            f" {(last.get('fingerprint') or '')[:16]}…"
            + (f"\nerror {last.get('error')}" if last.get("error")
               else ""))

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

    # ---- Insights (M13, Spec S21) ------------------------------------------

    @objc.python_method
    def _build_insights_view(self):
        from .state import INSIGHT_RANGES
        from .your_voice import YourVoicePane
        self._insight_ranges = INSIGHT_RANGES
        v = NSView.alloc().init()
        cw = self.content.bounds().size.width
        ch = self.content.bounds().size.height
        y = ch - 28
        # M14 (S19's surface table): Usage metrics and the Your Voice
        # communication profile are the Insights view's two sections.
        self.insights_subview_buttons = []
        for i, (title, action) in enumerate((
                ("Usage", "insightsSubview:"),
                ("Your Voice", "insightsSubview:"))):
            b = _button(title, self, action, NSMakeRect(8 + i * 108, y,
                                                        100, 22))
            b.setTag_(i)
            self.insights_subview_buttons.append(b)
            v.addSubview_(b)
        self.insights_status = _label(NSMakeRect(220, y + 3, 240, 18), "")
        v.addSubview_(self.insights_status)
        x = cw - 470
        for i, days in enumerate(INSIGHT_RANGES):
            title = "All" if days is None else f"{days}d"
            b = _button(title, self, "insightsRange:",
                        NSMakeRect(x, y, 52, 22))
            b.setTag_(i)
            v.addSubview_(b)
            x += 56
        v.addSubview_(_label(NSMakeRect(x, y + 3, 32, 18), "App:"))
        x += 36
        self.insights_app = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(x, y, 140, 24), False)
        self.insights_app.setTarget_(self)
        self.insights_app.setAction_("insightsAppChanged:")
        v.addSubview_(self.insights_app)
        x += 146
        v.addSubview_(_label(NSMakeRect(x, y + 3, 40, 18), "Mode:"))
        x += 44
        self.insights_mode = NSPopUpButton.alloc()\
            .initWithFrame_pullsDown_(NSMakeRect(x, y, 110, 24), False)
        self.insights_mode.setTarget_(self)
        self.insights_mode.setAction_("insightsModeChanged:")
        v.addSubview_(self.insights_mode)
        # Summary block (cards + breakdowns + definitions), then the
        # dated table (the accessible daily graph — virtualized rows).
        table_h = (ch - 60) * 0.42
        summary_h = ch - 56 - table_h - 34
        self.insights_text = _textview(NSMakeRect(0, 0, 100, 100))
        sc = _scroll(NSMakeRect(8, ch - 44 - summary_h, cw - 16,
                                summary_h), self.insights_text)
        sc.setAutoresizingMask_(18 | 16)
        v.addSubview_(sc)
        self.insights_table = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw - 16, table_h))
        for key, title, width in (("day", "Day", 96), ("dict", "Dictations",
                                                       90),
                                  ("words", "Words", 90),
                                  ("min", "Minutes", 80),
                                  ("tf", "Transforms", 96),
                                  ("fb", "Fallbacks", 84)):
            col = NSTableColumn.alloc().initWithIdentifier_(key)
            col.headerCell().setTitle_(title)
            col.setWidth_(width)
            self.insights_table.addTableColumn_(col)
        self.insights_table.setDataSource_(self)
        tsc = _scroll(NSMakeRect(8, 26, cw - 16, table_h),
                      self.insights_table)
        tsc.setAutoresizingMask_(18 | 16)
        v.addSubview_(tsc)
        v.addSubview_(_button("Reload", self, "insightsReload:",
                              NSMakeRect(cw - 96, y - 27, 88, 22)))
        self._usage_views = [self.insights_text, sc, tsc,
                             self.insights_table]
        for extra in v.subviews():
            if extra not in self._usage_views and extra not in \
                    self.insights_subview_buttons \
                    and extra is not self.insights_status:
                self._usage_views.append(extra)
        self.voice_pane = YourVoicePane(self, cw, ch - 30)
        self.voice_pane.view.setAutoresizingMask_(18 | 16)
        v.addSubview_(self.voice_pane.view)
        return v

    def insightsSubview_(self, sender):
        self.state.select_insights_subview(
            "usage" if int(sender.tag()) == 0 else "voice")

    def insightsRange_(self, sender):
        self.state.set_insights_filters(
            range_days=self._insight_ranges[int(sender.tag())])

    def insightsReload_(self, sender):
        self.state.reload_insights()

    def insightsAppChanged_(self, sender):
        if getattr(self, "_insights_building", False):
            return
        item = sender.selectedItem()
        self.state.set_insights_filters(
            app=(item.representedObject() if item else None))

    def insightsModeChanged_(self, sender):
        if getattr(self, "_insights_building", False):
            return
        item = sender.selectedItem()
        self.state.set_insights_filters(
            mode=(item.representedObject() if item else None))

    @objc.python_method
    def _refresh_insights_view(self):
        view = self.state.views["insights"]
        data = view.get("data")
        if view.get("error") or not data:
            self.insights_status.setStringValue_(
                f"Insights unavailable ({view.get('error') or 'loading'}).")
            return
        subview = data.get("subview", "usage")
        for i, b in enumerate(self.insights_subview_buttons):
            b.setEnabled_((i == 0) != (subview == "usage"))
        for uv in self._usage_views:
            uv.setHidden_(subview != "usage")
        self.voice_pane.view.setHidden_(subview != "voice")
        if subview == "voice":
            self.voice_pane.refresh(data)
            self._rendered["voice"] = data.get("profile") is not None
            note = self._action_notes.get("voice")
            if note:
                self.voice_pane.text.setString_(
                    f"{note}\n\n{self.voice_pane.text.string()}")
            return
        s = data.get("summary") or {}
        cohort = s.get("cohort") or {}
        self.insights_status.setStringValue_(
            f"Zone {s.get('reporting_timezone')} · algorithm v"
            f"{s.get('algorithm_version')}")
        self.insights_text.setString_(self._insights_summary_text(data))
        self._refresh_insights_popups(data)
        self._render_rows("insights_table")

    # ---- Your Voice actions (M14, S22) ----------------------------------------

    def voiceGenerate_(self, sender):
        """On-demand profile generation (S22), off the main thread; a
        failure is shown in the pane, never swallowed — it stays until
        the next generation starts (a routine refresh re-applies it)."""
        profile = self.spec.get("profile_service")
        if profile is None:
            return
        self._action_notes.pop("voice", None)

        def done(_out, err, current):
            if not current:
                return  # a newer generation owns the status
            if err is not None:
                msg = f"generation failed: {type(err).__name__}: {err}"
                self._action_notes["voice"] = msg
                view = self.state.views["insights"]
                if self.state.selected_view == "insights" and \
                        view.get("subview") == "voice":
                    self.voice_pane.text.setString_(
                        f"{msg}\n\n{self.voice_pane.text.string()}")
                return
            self.state.reload_insights()
        self._in_background(profile.compute, done, key="voice")

    def voiceExcludeEvidence_(self, sender):
        profile = self.spec.get("profile_service")
        current = self._training_action(
            profile.current) if profile is not None else None
        ex = (self.voice_pane.exclude_field.stringValue() or "").strip()
        if profile is None or not current or not ex:
            return
        self._training_action(profile.exclude_evidence,
                              current["snapshot_id"], ex)
        self.state.reload_insights()

    @objc.python_method
    def _refresh_insights_popups(self, data):
        self._insights_building = True
        try:
            for popup, items, current, all_label in (
                    (self.insights_app, data.get("apps") or [],
                     (self.state.views["insights"].get("app")),
                     "All apps"),
                    (self.insights_mode, data.get("modes") or [],
                     (self.state.views["insights"].get("mode")),
                     "All modes")):
                popup.removeAllItems()
                popup.addItemWithTitle_(all_label)
                popup.lastItem().setRepresentedObject_(None)
                for value in items:
                    popup.addItemWithTitle_(str(value))
                    popup.lastItem().setRepresentedObject_(value)
                idx = 0
                if current:
                    titles = [popup.itemTitleAtIndex_(i)
                              for i in range(popup.numberOfItems())]
                    if str(current) in titles:
                        idx = titles.index(str(current))
                popup.selectItemAtIndex_(idx)
        finally:
            self._insights_building = False

    @staticmethod
    def _fmt_ms(value):
        return "–" if value is None else f"{value:.0f} ms"

    @objc.python_method
    def _insights_summary_text(self, data) -> str:
        s = data.get("summary") or {}
        out = s.get("outcomes") or {}
        lat = s.get("latency") or {}
        den = s.get("wpm_denominator") or {}
        lines = []
        rng = s.get("cohort", {}).get("days")
        rng_label = "all time" if rng is None else f"last {rng} days"
        lines.append(f"Usage — {rng_label}"
                     + (f" · app {s['cohort']['app']}"
                        if s.get("cohort", {}).get("app") else "")
                     + (f" · mode {s['cohort']['mode']}"
                        if s.get("cohort", {}).get("mode") else ""))
        lines.append(
            f"Dictations: {s.get('dictations', 0)}"
            f" ({s.get('dictations_with_text', 0)} produced text"
            f" · {out.get('confirmed', 0)} confirmed"
            f" · {out.get('posted_unverified', 0)} posted-unverified"
            f" · {out.get('saved_not_inserted', 0)} saved"
            f" · {out.get('cancelled', 0)} cancelled"
            f" · {out.get('failed', 0)} failed)")
        lines.append(
            f"Words: {s.get('raw_words', 0)} raw → {s.get('final_words', 0)}"
            f" final · capture {s.get('capture_seconds', 0) / 60.0:.1f} min")
        wpm = s.get("wpm")
        lines.append(
            f"Full-capture WPM: {wpm if wpm is not None else 'n/a'}"
            f"  (60 × {den.get('words', 0)} final words ÷"
            f" {den.get('capture_seconds', 0)} s over"
            f" {den.get('jobs', 0)} jobs — weighted, not row-average)")
        fr = s.get("fallback_rate")
        lines.append(
            f"Fallback jobs: {s.get('fallback_jobs', 0)}"
            + (f" ({fr:.0%} of {s.get('dictations', 0)})"
               if fr is not None else "")
            + f" · dictionary hits {s.get('dictionary_hits', 0)}"
            f" · snippet hits {s.get('snippet_hits', 0)}")
        tf = s.get("transforms")
        if tf is None:
            lines.append(
                "Explicit transforms: n/a under a cohort filter —"
                " transform runs carry no destination app or mode")
        else:
            lines.append(
                f"Explicit transforms: {tf}"
                f" ({s.get('transform_words', 0)} source words)"
                f" · re-pastes {s.get('repastes')}")
        for key, label in (("asr", "ASR (stage)"),
                           ("cleanup", "Cleanup (stage)"),
                           ("transform", "Transform (stage)"),
                           ("end_to_end", "End-to-end (release→outcome)")):
            block = lat.get(key) or {}
            lines.append(
                f"Latency {label}: p50 {self._fmt_ms(block.get('p50'))}"
                f" · p95 {self._fmt_ms(block.get('p95'))}"
                f" · n={block.get('n', 0)} of {s.get('dictations', 0)}"
                " cohort (failures stay counted)")
        for row in (data.get("per_app") or [])[:8]:
            lines.append(f"  {row['app']}: {row['dictations']} dictations"
                         f" · {row['final_words']} words"
                         f" · {row['capture_seconds'] / 60.0:.1f} min")
        for row in (data.get("per_mode") or [])[:6]:
            lines.append(f"  mode {row['mode']}: {row['dictations']}"
                         f" dictations · {row['final_words']} words")
        legacy = data.get("legacy")
        if legacy:
            lines.append(
                f"Imported legacy history: {legacy['rows']} dictations"
                f" · {legacy['raw_words']} raw /"
                f" {legacy['cleaned_words']} cleaned words"
                f" · {legacy['capture_seconds']} s capture"
                f" · fixed words {legacy['legacy_fixed_words']}"
                " (legacy formula — not a V2 metric)")
        if data.get("undated"):
            lines.append(
                f"Undated history: {data['undated']} legacy log pairs"
                " (unknown dates — never in dated views)")
        lines += [
            "",
            "Definitions",
            "WPM — 60 × sum(final words) ÷ sum(capture seconds) over the"
            " cohort's text-producing jobs; denominators shown above.",
            "Legacy edits — the imported fixed-words count; its formula"
            " is unknown and stays labeled legacy (never reused).",
            "Model edits — pipeline word changes (raw → final word"
            " counts); a change rate, never a correctness claim.",
            "Reference-based accuracy — requires reviewed references;"
            " none exist yet, so no accuracy or WER is shown here.",
        ]
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
        # M13 (Spec S21): usage analytics retention — its own control,
        # independent of the text/audio knobs above (deleting expired
        # text never empties usage graphs), plus the explicit
        # delete-all-usage action.
        y -= 40
        v.addSubview_(_label(
            NSMakeRect(8, y + 3, 330, 34),
            "Usage data (Insights) retention days — independent of text"
            " retention:"))
        self.usage_retention_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(344, y, 56, 22))
        v.addSubview_(self.usage_retention_field)
        v.addSubview_(_button("Apply Usage", self,
                              "settingsApplyUsage:",
                              NSMakeRect(410, y - 1, 110, 24)))
        v.addSubview_(_button("Delete All Usage…", self,
                              "settingsDeleteUsage:",
                              NSMakeRect(528, y - 1, 160, 24)))
        note = _label(NSMakeRect(8, y - 40, cw - 16, 60),
                      "Store retention applies immediately. Event-log"
                      " retention takes effect at next launch. Models,"
                      " hotkey and capture behavior live in config.json."
                      " Usage deletion removes counters only — never"
                      " transcripts or audio.")
        v.addSubview_(note)
        return v

    def settingsCollectEnable_(self, sender):
        self._set_collection("enabled")

    def settingsCollectPause_(self, sender):
        self._set_collection("paused")

    def settingsCollectDisable_(self, sender):
        self._set_collection("disabled")

    @objc.python_method
    def _settings_call(self, what, fn, *args):
        """Run one Settings coordinator command; a failure is shown (the
        exception type only — never a payload) and nothing reloads over
        it (M09-AUDIT-22)."""
        try:
            fn(*args)
        except Exception as e:
            self.settings_text.setStringValue_(
                f"{what} failed ({type(e).__name__}) — nothing changed on"
                " screen; see Diagnostics")
            return False
        self.state.reload_current()
        return True

    @objc.python_method
    def _set_collection(self, new_state):
        if self.coordinator is not None:
            self._settings_call("Changing collection",
                                self.coordinator.hubSetCollection, new_state)

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
            self._settings_call("Applying retention",
                                self.coordinator.hubApplyRetention, values)

    def settingsApplyUsage_(self, sender):
        if self.coordinator is None or \
                not hasattr(self.coordinator, "hubApplyUsageRetention"):
            return
        try:
            days = max(1, int(self.usage_retention_field.stringValue()))
        except (ValueError, TypeError):
            self.settings_text.setStringValue_(
                "usage retention must be whole days")
            return
        self._settings_call("Applying usage retention",
                            self.coordinator.hubApplyUsageRetention, days)

    def settingsDeleteUsage_(self, sender):
        """The explicit delete-all-usage control (S21): counters and
        aggregates only. Confirmation is AppKit's standard alert; a
        headless run proceeds through the coordinator command."""
        if self.coordinator is None or \
                not hasattr(self.coordinator, "hubDeleteAllUsage"):
            return
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Delete all usage data?")
        alert.setInformativeText_(
            "Insights counters and daily aggregates are removed."
            " Transcripts, audio, jobs and training evidence are"
            " untouched. This cannot be undone.")
        alert.setAlertStyle_(NSAlertStyleWarning)
        alert.addButtonWithTitle_("Delete Usage Data")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        self._settings_call("Deleting usage data",
                            self.coordinator.hubDeleteAllUsage)

    @objc.python_method
    def _refresh_settings_view(self):
        view = self.state.views["settings"]
        data = view.get("data") or {}
        if view.get("error"):
            self.settings_text.setStringValue_(
                f"Settings could not load ({view['error']})")
            return
        self.settings_text.setStringValue_(
            f"Collection: {data.get('collection_state', 'unknown')}")
        ret = data.get("retention") or {}
        keys = ("transcript", "audio_success", "audio_failed",
                "metadata", "training_buffer")
        for f, key in zip(self.retention_fields, keys):
            if not f.stringValue():
                f.setStringValue_(str(ret.get(key, "")))
        usage = data.get("usage") or {}
        if usage and not self.usage_retention_field.stringValue():
            self.usage_retention_field.setStringValue_(
                str(usage.get("usage_retention_days", "")))
