"""Minimal Dictionary management panel (V2 M05, Spec S11).

A deliberately simple AppKit surface over the public
``VocabularyStore``/sandbox APIs — search, entries with aliases and
scopes, approve/disable/pin, add with conflict preview, and a phrase
sandbox ("Test this phrase"). The Hub (M09) reuses the same store APIs
rather than this panel's internals; nothing here touches the pipeline,
the coordinator thread or the store connection directly.

Run-loop note: actions run on the main thread and the single-writer
store funnels every mutation through its own writer thread, so a
dictation processing concurrently sees either the old or the new
vocabulary revision — never a torn one (AC03).
"""

from __future__ import annotations

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSFont,
    NSMakeRect,
    NSPopUpButton,
    NSSearchField,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

from . import vocabulary as vocab

SCOPE_MENU = ("global", "app", "site", "profile", "workspace")

_W = 560


def _label(frame, text):
    tf = NSTextField.alloc().initWithFrame_(frame)
    tf.setEditable_(False)
    tf.setBezeled_(False)
    tf.setDrawsBackground_(False)
    tf.setStringValue_(text)
    return tf


def _field(frame, placeholder=""):
    tf = NSTextField.alloc().initWithFrame_(frame)
    tf.setPlaceholderString_(placeholder)
    return tf


class DictionaryPanelController(NSObject):
    """Owner of the Dictionary window; ``initWithVocabularyStore_`` is the
    only entry point (called once from the app's menu)."""

    @objc.python_method
    def initWithVocabularyStore_(self, vstore):
        self = self.init()
        self.vstore = vstore
        self._build_ui()
        return self

    @objc.python_method
    def _build_ui(self):
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _W, 470),
            (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
             | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable),
            NSBackingStoreBuffered, False)
        self.window.setTitle_("LocalFlow Dictionary")
        self.window.setReleasedWhenClosed_(False)
        self.window.makeKeyAndOrderFront_(None)
        self.window.center()
        self.search = NSSearchField.alloc().initWithFrame_(
            NSMakeRect(16, 432, _W - 32, 24))
        self.search.setTarget_(self)
        self.search.setAction_("searchChanged:")
        self.window.contentView().addSubview_(self.search)
        # Entries summary (content-free): a compact count + numbered
        # selection list; keep the surface minimal and data-driven for
        # the Hub to reuse the same store APIs.
        self.listing = NSTextField.alloc().initWithFrame_(
            NSMakeRect(16, 268, _W - 32, 156))
        self.listing.setEditable_(False)
        self.listing.setSelectable_(True)
        self.listing.setFont_(NSFont.monospacedSystemFontOfSize_weight_(
            11.0, 0.0))
        self.window.contentView().addSubview_(self.listing)
        # Add-entry row.
        y = 236
        self.window.contentView().addSubview_(
            _label(NSMakeRect(16, y + 4, 90, 20), "Canonical:"))
        self.canonical = _field(NSMakeRect(108, y, 150, 22), "Claude Code")
        self.window.contentView().addSubview_(self.canonical)
        self.window.contentView().addSubview_(
            _label(NSMakeRect(266, y + 4, 48, 20), "Alias:"))
        self.alias = _field(NSMakeRect(316, y, 120, 22), "clod code")
        self.window.contentView().addSubview_(self.alias)
        self.scope_popup = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(444, y, 100, 24))
        self.scope_popup.addItemsWithTitles_(list(SCOPE_MENU))
        self.window.contentView().addSubview_(self.scope_popup)
        self.scope_value = _field(NSMakeRect(16, y - 30, 200, 22),
                                  "scope value (workspace/profile/…)")
        self.window.contentView().addSubview_(self.scope_value)
        self.window.contentView().addSubview_(_label(
            NSMakeRect(224, y - 26, 120, 20),
            "scope value (n/a for global)"))
        add = NSButton.buttonWithTitle_target_action_(
            "Add / Preview Conflicts", self, "addEntry:")
        add.setFrame_(NSMakeRect(360, y - 31, 184, 24))
        self.window.contentView().addSubview_(add)
        # Phrase sandbox.
        y2 = 150
        self.window.contentView().addSubview_(
            _label(NSMakeRect(16, y2 + 4, 90, 20), "Test phrase:"))
        self.phrase = _field(NSMakeRect(108, y2, 330, 22),
                             "use clod code for the cloud deployment")
        self.phrase.setTarget_(self)
        self.phrase.setAction_("runSandbox:")
        self.window.contentView().addSubview_(self.phrase)
        run = NSButton.buttonWithTitle_target_action_(
            "Test", self, "runSandbox:")
        run.setFrame_(NSMakeRect(448, y2 - 1, 96, 24))
        self.window.contentView().addSubview_(run)
        self.sandbox = NSTextField.alloc().initWithFrame_(
            NSMakeRect(16, 44, _W - 32, 100))
        self.sandbox.setEditable_(False)
        self.sandbox.setSelectable_(True)
        self.window.contentView().addSubview_(self.sandbox)
        # Management buttons.
        for idx, (title, action) in enumerate((
                ("Approve", "approveEntry:"), ("Disable/Enable", "toggleEntry:"),
                ("Pin", "pinEntry:"), ("Delete", "deleteEntry:"))):
            b = NSButton.buttonWithTitle_target_action_(title, self, action)
            b.setFrame_(NSMakeRect(16 + idx * 90, 8, 84, 26))
            self.window.contentView().addSubview_(b)
        self._entries = []
        self._shown = []
        self._selected = None
        self.refresh()

    # ---- data ------------------------------------------------------------

    @objc.python_method
    def refresh(self):
        try:
            self._entries = self.vstore.entries()
        except Exception as e:
            self.listing.setStringValue_(f"store read failed: {e}")
            self._entries = []
            self._shown = []
            return
        needle = (self.search.stringValue() or "").strip().lower()
        shown = [e for e in self._entries
                 if not needle or needle in e.canonical.lower()
                 or any(needle in a.alias.lower() for a in e.aliases)]
        lines = [f"{len(self._entries)} entries"
                 f" ({len(shown)} shown) — click a line to select:\n"]
        for i, e in enumerate(shown):
            state = []
            if not e.enabled:
                state.append("disabled")
            if not e.approved:
                state.append(f"suggested ({e.verification})")
            if e.pinned:
                state.append("pinned")
            aliases = ", ".join(a.alias for a in e.aliases) or "—"
            scope = e.scope_kind + (
                f":{e.scope_value}" if e.scope_value else "")
            suffix = f" [{'; '.join(state)}]" if state else ""
            lines.append(f"{i + 1:3d}. {e.canonical}  ({aliases})"
                         f"  · {scope} · used {e.usage_count}{suffix}")
        self._shown = shown
        self.listing.setStringValue_("\n".join(lines))

    @objc.python_method
    def _selected_entry(self):
        if self._selected is not None and 0 <= self._selected < len(
                self._shown):
            return self._shown[self._selected]
        return None

    def searchChanged_(self, sender):
        self.refresh()

    def addEntry_(self, sender):
        canonical = (self.canonical.stringValue() or "").strip()
        alias = (self.alias.stringValue() or "").strip()
        scope_kind = self.scope_popup.titleOfSelectedItem() or "global"
        scope_value = (self.scope_value.stringValue() or "").strip() \
            if scope_kind != "global" else None
        if not canonical:
            self.sandbox.setStringValue_("canonical spelling required")
            return
        try:
            entry_id = self.vstore.add_entry(
                canonical=canonical,
                aliases=[alias] if alias else [],
                scope_kind=scope_kind, scope_value=scope_value,
                origin="user", approved=False)
            conflicts = vocab.preview_entry_conflicts(
                self.vstore.entry(entry_id), self._entries)
            self._selected = None
            self.refresh()
            if conflicts:
                self.sandbox.setStringValue_(
                    "added with conflicts:\n" + "\n".join(
                        f"· {c['alias']}: {c['kind']}"
                        + (f" — {c['detail']}" if c.get("detail") else "")
                        for c in conflicts))
            else:
                self.sandbox.setStringValue_(
                    f"added {canonical!r} (unapproved — approve to make it"
                    " rewrite text)")
        except Exception as e:
            self.sandbox.setStringValue_(f"not added: {e}")

    def approveEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self.sandbox.setStringValue_(
                "select an entry first (type its line number in Test"
                " phrase and press Test)")
            return
        try:
            self.vstore.approve_entry(e.entry_id)
            self.refresh()
            self.sandbox.setStringValue_(f"approved {e.canonical}")
        except Exception as ex:
            self.sandbox.setStringValue_(f"not approved: {ex}")

    def toggleEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self.sandbox.setStringValue_("select an entry first")
            return
        try:
            self.vstore.set_enabled(e.entry_id, not e.enabled)
            self.refresh()
        except Exception as ex:
            self.sandbox.setStringValue_(f"not toggled: {ex}")

    def pinEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self.sandbox.setStringValue_("select an entry first")
            return
        try:
            self.vstore.update_entry(e.entry_id, pinned=not e.pinned)
            self.refresh()
        except Exception as ex:
            self.sandbox.setStringValue_(f"not pinned: {ex}")

    def deleteEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self.sandbox.setStringValue_("select an entry first")
            return
        try:
            self.vstore.delete_entry(e.entry_id)
            self._selected = None
            self.refresh()
        except Exception as ex:
            self.sandbox.setStringValue_(f"not deleted: {ex}")

    def runSandbox_(self, sender):
        text = (self.phrase.stringValue() or "").strip()
        # A bare number in the Test field selects that listing line.
        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(self._shown):
                self._selected = idx
                e = self._shown[idx]
                self.sandbox.setStringValue_(
                    f"selected: {e.canonical} ({e.scope_kind}:"
                    f"{e.scope_value or '-'})")
                return
        if not text:
            return
        try:
            snapshot = self.vstore.snapshot(None)
            out = vocab.sandbox_phrase(text, snapshot)
        except Exception as e:
            self.sandbox.setStringValue_(f"sandbox failed: {e}")
            return
        lines = [f"→ {out['output']}",
                 f"vocabulary {out['vocabulary_revision']} ·"
                 f" {len(out['applied'])} applied,"
                 f" {len(out['suggestions'])} suggested"]
        for a in out["applied"]:
            lines.append(f"  applied: {a['before']!r} → {a['after']!r}"
                         f" ({a['verification']})")
        for s in out["suggestions"]:
            scope_note = ""
            if not s.get("in_scope", True):
                kind, value = s["scope"]
                where = f"{kind}:{value}" if value else kind
                scope_note = f" (needs {where} context active)"
            lines.append(f"  suggested: {s['text']!r} would become"
                         f" {s['canonical']!r} if approved{scope_note}")
        for c in out["conflicts"]:
            lines.append(f"  conflict: alias {c['alias']!r} masked"
                         f" ({c['reason']})")
        for r in out["rejected"]:
            lines.append(f"  not applied: {r['before']!r} ({r['reason']})")
        self.sandbox.setStringValue_("\n".join(lines))

    def showWindow_(self, sender):
        self.refresh()
        self.window.makeKeyAndOrderFront_(NSApp)
