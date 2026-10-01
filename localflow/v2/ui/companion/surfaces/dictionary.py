"""Dictionary (Spec S11, M05) — the vocabulary store, formerly a separate
menu-bar panel, as a companion route.

The panel's rules hold: a user-added entry is unapproved until the user
approves it (its conflicts are previewed against the store as it is
now); every write to an existing entry re-reads it at action time and
refuses when its revision moved since the page rendered it, then writes
with ``expected_revision`` (a second, in-op check); a store timeout is an
unknown outcome, never a failure. Import and export run through native
file panels — the page never names a path.
"""

from __future__ import annotations

import json
import pathlib

from .. import bridge as B
from ..bridge import Bool, Enum, Int, List, Nullable, Str

SCOPES = ("global", "app", "site", "profile", "workspace")


def _panels():
    """Native open/save panels (the page never supplies a path)."""
    class Panels:
        @staticmethod
        def open_json():
            from AppKit import NSOpenPanel
            panel = NSOpenPanel.openPanel()
            panel.setAllowedFileTypes_(["json"])
            panel.setCanChooseDirectories_(False)
            if panel.runModal() != 1 or not panel.URLs():
                return None
            return panel.URLs()[0].path()

        @staticmethod
        def save_json(name):
            from AppKit import NSSavePanel
            panel = NSSavePanel.savePanel()
            panel.setAllowedFileTypes_(["json"])
            panel.setNameFieldStringValue_(name)
            if panel.runModal() != 1 or panel.URL() is None:
                return None
            return panel.URL().path()
    return Panels


def register(ctl):
    br = ctl.bridge
    st = ctl.state
    panels = ctl.spec.get("file_panels") or _panels()

    def vstore():
        s = st.vocabulary_store
        if s is None:
            B.unavailable("vocabulary_unavailable")
        return s

    def failed(e):
        """A write's exception → its outcome class."""
        from ....vocabulary_store import StaleEntryError
        if isinstance(e, B.Outcome):
            raise e
        if isinstance(e, TimeoutError):
            B.unknown("store_busy")
        if isinstance(e, StaleEntryError):
            st.reload_dictionary()
            B.stale("entry_changed")
        if isinstance(e, KeyError):
            B.refuse("entry_gone")
        if isinstance(e, ValueError):
            B.refuse(str(e))
        raise e

    def current(p):
        """The entry as it is now — only if it is still the revision the
        page rendered (the panel's ``_selected_entry``)."""
        s = vstore()
        try:
            e = s.entry(p["entry_id"])
        except TimeoutError:
            B.unknown("store_busy")
        if e is None:
            st.reload_dictionary()
            B.refuse("entry_gone")
        if e.revision != p["revision"]:
            st.reload_dictionary()
            B.stale("entry_changed")
        return s, e

    ENTRY = {"entry_id": Str(max_len=80, allow_empty=False),
             "revision": Int(lo=0)}

    @br.command("dictionary.search", {"text": Str(max_len=200)})
    def search(p):
        st.set_dictionary_search(p["text"])
        return {}

    @br.command("dictionary.reload")
    def reload(p):
        st.reload_dictionary()
        return {}

    @br.command("dictionary.add", {
        "canonical": Str(max_len=200),
        "alias": Str(max_len=200, optional=True),
        "scope_kind": Enum(SCOPES),
        "scope_value": Nullable(Str(max_len=300), optional=True)})
    def add(p):
        from .... import vocabulary as vocab
        s = vstore()
        canonical = (p["canonical"] or "").strip()
        alias = (p.get("alias") or "").strip()
        kind = p["scope_kind"]
        value = (p.get("scope_value") or "").strip() or None \
            if kind != "global" else None
        if not canonical:
            B.refuse("canonical_required")
        try:
            entry_id = s.add_entry(canonical=canonical,
                                   aliases=[alias] if alias else [],
                                   scope_kind=kind, scope_value=value,
                                   origin="user", approved=False)
            conflicts = vocab.preview_entry_conflicts(
                s.entry(entry_id),
                [e for e in s.entries() if e.entry_id != entry_id])
        except Exception as e:
            failed(e)
        st.reload_dictionary()
        added = s.entry(entry_id)
        return {"entry_id": entry_id,
                "revision": added.revision if added else None,
                "conflicts": [{"alias": c.get("alias"), "kind": c.get("kind"),
                               "active": bool(c.get("active")),
                               "detail": c.get("detail")}
                              for c in conflicts]}

    def write(p, fn):
        s, e = current(p)
        try:
            fn(s, e)
        except Exception as ex:
            failed(ex)
        st.reload_dictionary()
        after = s.entry(e.entry_id)
        return {"revision": after.revision if after else None}

    @br.command("dictionary.approve", ENTRY)
    def approve(p):
        return write(p, lambda s, e: s.approve_entry(
            e.entry_id, expected_revision=e.revision))

    @br.command("dictionary.set_enabled", {**ENTRY, "enabled": Bool()})
    def set_enabled(p):
        return write(p, lambda s, e: s.set_enabled(
            e.entry_id, p["enabled"], expected_revision=e.revision))

    @br.command("dictionary.set_pinned", {**ENTRY, "pinned": Bool()})
    def set_pinned(p):
        return write(p, lambda s, e: s.update_entry(
            e.entry_id, pinned=p["pinned"], expected_revision=e.revision))

    @br.command("dictionary.delete", ENTRY)
    def delete(p):
        s, e = current(p)
        try:
            s.delete_entry(e.entry_id, expected_revision=e.revision)
        except Exception as ex:
            failed(ex)
        st.reload_dictionary()
        return {"deleted": e.entry_id}

    @br.command("dictionary.edit", {
        **ENTRY, "canonical": Str(max_len=200),
        "aliases": List(Str(max_len=200), max_items=40)})
    def edit(p):
        """Canonical spelling and the alias list. An alias the entry
        already had keeps its own approval; a new one arrives unapproved
        (approval stays an explicit act, M05)."""
        canonical = (p["canonical"] or "").strip()
        if not canonical:
            B.refuse("canonical_required")

        def apply(s, e):
            known = {a.alias: a for a in e.aliases}
            seen, items = set(), []
            for text in p["aliases"]:
                text = " ".join(text.split())
                if not text or text in seen:
                    continue
                seen.add(text)
                old = known.get(text)
                items.append((text, old.approved if old else False,
                              old.language if old else None))
            changes = {}
            if canonical != e.canonical:
                changes["canonical"] = canonical
            if [i[0] for i in items] != [a.alias for a in e.aliases]:
                changes["aliases"] = items
            if not changes:
                B.refuse("no_changes")
            s.update_entry(e.entry_id, expected_revision=e.revision,
                           **changes)
        return write(p, apply)

    @br.command("dictionary.sandbox", {
        "text": Str(max_len=2000),
        "scope_kind": Enum(SCOPES),
        "scope_value": Nullable(Str(max_len=300), optional=True)})
    def sandbox(p):
        from .... import vocabulary as vocab
        s = vstore()
        kind = p["scope_kind"]
        value = (p.get("scope_value") or "").strip()
        field = {"app": "app_bundle", "site": "site_origin",
                 "profile": "profile", "workspace": "workspace"}.get(kind)
        ctx = vocab.ScopeContext(**{field: value}) \
            if field and value else None
        try:
            out = vocab.sandbox_phrase(p["text"], s.snapshot(ctx))
        except TimeoutError:
            B.unknown("store_busy")
        return {
            "output": out.get("output"), "changed": out.get("changed"),
            "scope": "global" if ctx is None else f"{kind}",
            "applied": [{"before": a.get("before"), "after": a.get("after")}
                        for a in out.get("applied") or ()],
            "suggestions": [{"alias": x.get("alias"),
                             "would_become": x.get("would_become"),
                             "canonical": x.get("canonical"),
                             "masked": bool(x.get("masked")),
                             "in_scope": x.get("in_scope")}
                            for x in out.get("suggestions") or ()],
            "conflicts": [{"alias": c.get("alias"),
                           "reason": c.get("reason")}
                          for c in out.get("conflicts") or ()],
            "rejected": [{"before": r.get("before"),
                          "reason": r.get("reason")}
                         for r in out.get("rejected") or ()]}

    @br.command("dictionary.import")
    def import_json(p):
        from ....vocabulary_store import ImportRejected
        s = vstore()
        path = panels.open_json()
        if not path:
            raise B.Outcome("cancelled", "cancelled")
        try:
            result = s.import_json(path)
        except TimeoutError:
            B.unknown("store_busy")
        except ImportRejected as e:
            B.refuse(f"import_rejected:{getattr(e, 'code', 'invalid')}")
        st.reload_dictionary()
        return {"created": result.get("created"),
                "updated": result.get("updated"),
                "unchanged": result.get("unchanged")}

    @br.command("dictionary.export")
    def export_json(p):
        s = vstore()
        path = panels.save_json("LocalFlow Dictionary.json")
        if not path:
            raise B.Outcome("cancelled", "cancelled")
        try:
            doc = s.export_json()
            pathlib.Path(path).write_text(
                json.dumps(doc, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except TimeoutError:
            B.unknown("store_busy")
        except OSError as e:
            B.refuse(f"write_failed:{type(e).__name__}")
        return {"entries": len(doc.get("entries") or ())}
