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
        # Selection is a STABLE entry id (M05-AUDIT-08) — never a row
        # index into whatever the listing shows after a filter change or
        # a store-driven reorder.
        self._selected_id = None
        # The revision the user SAW when selecting (review Q3): actions
        # compare-and-swap against it, so a change made elsewhere after
        # the selection (an alias added by an import or the Hub) is
        # never approved, toggled or deleted unseen.
        self._selected_rev = None
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
        if self._selected_id is not None and not any(
                e.entry_id == self._selected_id for e in self._entries):
            self._selected_id = None      # the selected entry is gone
            self._selected_rev = None
        lines = [f"{len(self._entries)} entries"
                 f" ({len(shown)} shown) — to select one, type its line"
                 " number in Test phrase and press Test:\n"]
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
            mark = "›" if e.entry_id == self._selected_id else " "
            lines.append(f"{mark}{i + 1:3d}. {e.canonical}  ({aliases})"
                         f"  · {scope} · used {e.usage_count}{suffix}")
        self._shown = shown
        self.listing.setStringValue_("\n".join(lines))

    @objc.python_method
    def _selected_entry(self):
        """The selected entry, RE-READ from the store at action time;
        None — and the selection cleared — when it no longer exists, and
        None (selection kept, listing refreshed) when it CHANGED since
        the user selected it: the action waits for a fresh look. An
        action never infers its target from a row position."""
        if self._selected_id is None:
            return None
        try:
            e = self.vstore.entry(self._selected_id)
        except Exception:
            e = None
        if e is None:
            self._selected_id = None
            self._selected_rev = None
            self.sandbox.setStringValue_(
                "the selected entry no longer exists — select again")
            return None
        if self._selected_rev is not None \
                and e.revision != self._selected_rev:
            self._selected_rev = e.revision
            self.refresh()
            self.sandbox.setStringValue_(
                f"{e.canonical} changed since you selected it — review"
                " the listing, then press the action again")
            return None
        return e

    @objc.python_method
    def _acted(self, entry_id):
        """After this panel's own successful write: the user sees the
        result in the refreshed listing, so the selection follows it."""
        try:
            e = self.vstore.entry(entry_id)
        except Exception:
            e = None
        self._selected_rev = e.revision if e is not None else None

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
            # Preview against the store as it is NOW (review R14), not
            # the listing's last read: a contender added elsewhere since
            # the last refresh is reported too.
            conflicts = vocab.preview_entry_conflicts(
                self.vstore.entry(entry_id),
                [e for e in self.vstore.entries()
                 if e.entry_id != entry_id])
            self._selected_id = None
            self._selected_rev = None
            self.refresh()
            if conflicts:
                self.sandbox.setStringValue_(
                    "added with conflicts:\n" + "\n".join(
                        f"· {c['alias']}: {c['kind']}"
                        + ("" if c.get("active") else " (if approved/"
                           "enabled — not active now)")
                        + (f" — {c['detail']}" if c.get("detail") else "")
                        for c in conflicts))
            else:
                self.sandbox.setStringValue_(
                    f"added {canonical!r} (unapproved — approve to make it"
                    " rewrite text)")
        except Exception as e:
            self.sandbox.setStringValue_(f"not added: {e}")

    @objc.python_method
    def _no_selection(self):
        if self._selected_id is None and not (
                self.sandbox.stringValue() or "").startswith("the selected"):
            self.sandbox.setStringValue_(
                "select an entry first (type its line number in Test"
                " phrase and press Test)")

    def approveEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self._no_selection()
            return
        try:
            # Compare-and-swap on the revision just read: the approval
            # lands on exactly the state the action was decided on.
            self.vstore.approve_entry(e.entry_id,
                                      expected_revision=e.revision)
            self._acted(e.entry_id)
            self.refresh()
            self.sandbox.setStringValue_(f"approved {e.canonical}")
        except Exception as ex:
            self.sandbox.setStringValue_(f"not approved: {ex}")

    def toggleEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self._no_selection()
            return
        try:
            self.vstore.set_enabled(e.entry_id, not e.enabled,
                                    expected_revision=e.revision)
            self._acted(e.entry_id)
            self.refresh()
        except Exception as ex:
            self.sandbox.setStringValue_(f"not toggled: {ex}")

    def pinEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self._no_selection()
            return
        try:
            self.vstore.update_entry(e.entry_id, pinned=not e.pinned,
                                     expected_revision=e.revision)
            self._acted(e.entry_id)
            self.refresh()
        except Exception as ex:
            self.sandbox.setStringValue_(f"not pinned: {ex}")

    def deleteEntry_(self, sender):
        e = self._selected_entry()
        if e is None:
            self._no_selection()
            return
        try:
            self.vstore.delete_entry(e.entry_id,
                                     expected_revision=e.revision)
            self._selected_id = None
            self._selected_rev = None
            self.refresh()
        except Exception as ex:
            self.sandbox.setStringValue_(f"not deleted: {ex}")

    @objc.python_method
    def _sandbox_scope(self):
        """The ScopeContext the sandbox tests: the scope chosen in the
        panel's scope controls (global entries always apply). Explicit —
        no destination is scraped (M05-AUDIT-13)."""
        kind = self.scope_popup.titleOfSelectedItem() or "global"
        value = (self.scope_value.stringValue() or "").strip()
        field = {"app": "app_bundle", "site": "site_origin",
                 "profile": "profile", "workspace": "workspace"}.get(kind)
        if field is None or not value:
            return None, "scope: global only"
        return vocab.ScopeContext(**{field: value}), \
            f"scope: {kind}={value} (+ global)"

    def runSandbox_(self, sender):
        text = (self.phrase.stringValue() or "").strip()
        # A bare number in the Test field selects that listing line.
        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(self._shown):
                e = self._shown[idx]
                self._selected_id = e.entry_id
                self._selected_rev = e.revision
                self.sandbox.setStringValue_(
                    f"selected: {e.canonical} ({e.scope_kind}:"
                    f"{e.scope_value or '-'})")
                return
        if not text:
            return
        try:
            scope_ctx, scope_label = self._sandbox_scope()
            snapshot = self.vstore.snapshot(scope_ctx)
            out = vocab.sandbox_phrase(text, snapshot)
        except Exception as e:
            self.sandbox.setStringValue_(f"sandbox failed: {e}")
            return
        lines = [f"→ {out['output']}",
                 f"{scope_label} · vocabulary"
                 f" {out['vocabulary_revision']} ·"
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
            if s.get("masked"):
                lines.append(f"  suggested: {s['canonical']!r} would be"
                             " masked by a conflicting approved entry if"
                             f" approved{scope_note}")
                continue
            lines.append(f"  suggested: {s['text']!r} would become"
                         f" {s.get('would_become', s['canonical'])!r} if"
                         f" approved{scope_note}")
        for c in out["conflicts"]:
            lines.append(f"  conflict: alias {c['alias']!r} masked"
                         f" ({c['reason']})")
        for r in out["rejected"]:
            lines.append(f"  not applied: {r['before']!r} ({r['reason']})")
        self.sandbox.setStringValue_("\n".join(lines))

    def showWindow_(self, sender):
        self.refresh()
        self.window.makeKeyAndOrderFront_(NSApp)
