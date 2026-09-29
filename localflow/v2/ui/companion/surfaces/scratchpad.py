"""Scratchpad (M12, Spec S20, contracts/scratchpad.md) in the companion.

The note editor is the AppKit Hub's own ``ScratchpadEditor`` — model
binding, retention of unsaved buffers, the autosave tick, flush
barriers, arrival receipts, shutdown and the ONE code-point selection
validator — bound to ``WebText``, a mirror of the page's textarea that
answers the few NSTextView calls the editor makes. Nothing about how a
note is saved, or where a dictation lands, is reimplemented here.

The mirror and the page stay in step with versions. Every change bumps
the version: a typed edit the page sends, and a programmatic set (a
note bound, a dictation or transform arriving). The page sends one edit
at a time naming the version it was typed on; when an arrival moved the
text on meanwhile, the typed change is rebased onto it (both are
contiguous ranges of the text at that version) and the merged text is
returned — an arrival is never overwritten by input typed before it
reached the page. A selection counts only when it was reported for the
current version; otherwise the editor's selection reads as invalid, so
a dictation starting then is kept rather than placed at a guessed caret.

Actions act on the note the editor SHOWS (``rendered``): the editor's
binding, the state's selection and the loaded detail must agree.
"""

from __future__ import annotations

import pathlib

import objc

from .. import bridge as B
from ..bridge import Bool, Enum, Int, Nullable, Str
from ...scratchpad import ScratchpadEditor

HISTORY = 48  # versions of the text kept for rebasing an in-flight edit


class _Range:
    def __init__(self, location, length):
        self.location, self.length = location, length


class _Window:
    def __init__(self, mirror):
        self.mirror = mirror

    def isKeyWindow(self):
        return self.mirror.is_key()

    def firstResponder(self):
        return self.mirror if self.mirror.has_focus() else None


def _span(a, b):
    """The single contiguous change turning ``a`` into ``b``:
    (start, end-in-a, inserted)."""
    n = min(len(a), len(b))
    s = 0
    while s < n and a[s] == b[s]:
        s += 1
    e = 0
    while e < n - s and a[len(a) - 1 - e] == b[len(b) - 1 - e]:
        e += 1
    return s, len(a) - e, b[s:len(b) - e]


def rebase(base, typed, current):
    """Apply the typed change (base -> typed) on top of the arrivals
    (base -> current). Disjoint ranges both apply; an overlap keeps the
    arrival and adds the typed insertion right after it."""
    s1, e1, ins1 = _span(base, typed)
    s2, e2, ins2 = _span(base, current)
    if (s1, e1, ins1) == (s1, s1, ""):
        return current
    if e1 <= s2:
        return base[:s1] + ins1 + base[e1:s2] + ins2 + base[e2:]
    if s1 >= e2:
        return base[:s2] + ins2 + base[e2:s1] + ins1 + base[e1:]
    return base[:s2] + ins2 + ins1 + base[max(e1, e2):]


class WebText:
    """The page's textarea as the editor sees it."""

    def __init__(self, ctl):
        self.ctl = ctl
        self.value = ""
        self.version = 0
        self.history = {0: ""}
        self.note_id = None  # the note the page's text belongs to
        self.sel = None      # (utf16 location, length, version)
        self.focused = False

    # -- the NSTextView subset ScratchpadEditor uses --
    def string(self):
        return self.value

    def setString_(self, text):
        """A programmatic set (bind, arrival): the page is told."""
        self._commit(str(text))
        editor = self.ctl.scratchpad_editor
        self.note_id = editor.note_id if editor is not None else None
        self.ctl.emit("scratchpad.content", {
            "note_id": self.note_id, "version": self.version,
            "content": self.value})

    def selectedRange(self):
        if self.sel is not None and self.sel[2] == self.version:
            return _Range(self.sel[0], self.sel[1])
        # Not reported for the text as it is now: out of range, which the
        # editor's validator refuses (never a guessed caret).
        return _Range(len(self.value.encode("utf-16-le")) // 2 + 1, 0)

    def window(self):
        return _Window(self)

    # -- window/focus as the coordinator's PTT-time check needs them --
    def is_key(self):
        host = self.ctl.host
        return bool(getattr(host, "is_key", lambda: False)())

    def has_focus(self):
        host = self.ctl.host
        return (self.focused
                and self.ctl.state.selected_view == "scratchpad"
                and self.note_id is not None
                and bool(getattr(host, "webview_has_focus",
                                 lambda: False)()))

    # -- page -> Python --
    def _commit(self, text):
        self.version += 1
        self.value = text
        self.history[self.version] = text
        for v in [v for v in self.history if v < self.version - HISTORY]:
            del self.history[v]

    def typed(self, base, text):
        """A typed edit made on version ``base``. Returns the text now in
        the editor and whether it differs from what the page sent."""
        if base == self.version:
            self._commit(text)
            return self.value, False
        base_text = self.history.get(base)
        if base_text is None:
            return None, True  # too old to merge: the page reloads
        self._commit(rebase(base_text, text, self.value))
        return self.value, True


class WebScratchpadEditor(ScratchpadEditor):
    """The Hub's editor bound to the page instead of an NSTextView."""

    @objc.python_method
    def init_with_mirror(self, hub, mirror):
        self = self.init_editor(hub)
        # init_editor built a native text view for the AppKit pane; the
        # companion's text lives in the page — the mirror stands in.
        self.text = mirror
        self.scroll = None
        return self


def register(ctl):
    br = ctl.bridge
    st = ctl.state
    mirror = WebText(ctl)
    editor = WebScratchpadEditor.alloc().init_with_mirror(ctl, mirror)
    ctl.scratchpad_editor = editor
    ctl.scratchpad_mirror = mirror
    panels = ctl.spec.get("file_panels")

    def svc():
        s = ctl.spec.get("notes_service")
        if s is None:
            B.unavailable("notes_unavailable")
        return s

    def rendered(note_id):
        """The note the editor shows, only while the editor's binding, the
        selection and the loaded detail all name it (M12-AUDIT-11)."""
        view = st.views["scratchpad"]
        detail = view.get("detail") or {}
        if editor.model is None or editor.note_id is None \
                or editor.note_id != note_id \
                or view.get("selected_id") != note_id \
                or detail.get("note_id") != note_id:
            B.stale("note_loading")
        return detail

    def failed(verb, e):
        from ....notes import failure_kind
        kind = failure_kind(e)
        if kind == "unknown":
            B.unknown(f"{verb}_pending")
        if kind == "refused":
            B.refuse(f"{verb}_refused")
        B.refuse(f"{verb}_failed:{type(e).__name__}")

    NOTE = {"note_id": Str(max_len=80, allow_empty=False)}

    # ---- list, tabs, selection -------------------------------------------------

    @br.command("scratchpad.search", {"text": Str(max_len=200)})
    def search(p):
        st.set_scratchpad_search(p["text"])
        return {}

    @br.command("scratchpad.open", {"note_id": Nullable(Str(max_len=80))})
    def open_note(p):
        st.select_scratchpad_note(p["note_id"])
        return {}

    @br.command("scratchpad.close_tab", NOTE)
    def close_tab(p):
        # bind_note/clear save the outgoing buffer first and retain it
        # when that save does not settle: closing never discards text.
        st.close_scratchpad_tab(p["note_id"])
        return {}

    @br.command("scratchpad.new")
    def new(p):
        from .... import ids
        s = svc()
        # A preallocated id: an admitted create whose answer never came is
        # the same note when (if) it commits — never a second one.
        note_id = ids.new_id("note")
        try:
            s.create_note("", note_id=note_id)
        except Exception as e:
            from ....notes import failure_kind
            if failure_kind(e) != "unknown":
                failed("new_note", e)
        st.views["scratchpad"]["search"] = ""
        st.reload_scratchpad()
        st.select_scratchpad_note(note_id)
        return {"note_id": note_id}

    # ---- the text ------------------------------------------------------------------

    @br.command("scratchpad.sync", {"note_id": Nullable(Str(max_len=80))})
    def sync(p):
        """The page (re)mounted its editor: send the editor's own text
        (a retained buffer can be newer than the store)."""
        return {"note_id": editor.note_id, "version": mirror.version,
                "content": mirror.value if editor.note_id else ""}

    @br.command("scratchpad.edit", {
        "note_id": Str(max_len=80), "base": Int(lo=0),
        "text": Str(max_len=1_000_000),
        "sel_start": Int(lo=0), "sel_end": Int(lo=0)})
    def edit(p):
        if editor.model is None or editor.note_id != p["note_id"] \
                or mirror.note_id != p["note_id"]:
            B.stale("note_not_bound")
        text, changed = mirror.typed(p["base"], p["text"])
        if text is None:
            B.stale("resync")
        editor.textDidChange_(None)  # the model takes the text as typed
        if not changed:
            mirror.sel = (p["sel_start"], p["sel_end"] - p["sel_start"],
                          mirror.version)
        return {"version": mirror.version,
                "content": text if changed else None}

    @br.command("scratchpad.cursor", {
        "note_id": Str(max_len=80), "version": Int(lo=0),
        "sel_start": Int(lo=0), "sel_end": Int(lo=0),
        "focused": Bool()})
    def cursor(p):
        if p["note_id"] == mirror.note_id and p["version"] == mirror.version:
            mirror.sel = (p["sel_start"], max(0, p["sel_end"]
                                              - p["sel_start"]),
                          mirror.version)
        mirror.focused = bool(p["focused"]) and \
            p["note_id"] == mirror.note_id
        return {}

    # ---- note actions ----------------------------------------------------------------

    @br.command("scratchpad.pin", NOTE)
    def pin(p):
        s = svc()
        detail = rendered(p["note_id"])
        try:
            s.set_pinned(p["note_id"], not detail.get("pinned"))
        except Exception as e:
            failed("pin", e)
        st.reload_scratchpad()
        return {"pinned": not detail.get("pinned")}

    @br.command("scratchpad.snapshot", NOTE)
    def snapshot(p):
        rendered(p["note_id"])
        out = editor.flush_now(trigger="explicit")
        st.reload_scratchpad()
        return {"outcome": out.get("outcome")}

    @br.command("scratchpad.restore", {**NOTE,
                                       "revision_id": Str(max_len=80)})
    def restore(p):
        from .... import ids
        s = svc()
        rendered(p["note_id"])
        out = editor.flush_now()
        if out.get("outcome") not in ("flushed", "no_change"):
            B.refuse("not_saved_yet")
        try:
            s.restore(p["note_id"], p["revision_id"],
                      new_revision_id=ids.new_id("nrev"))
            # Bind the restored text NOW, before anything can reach the
            # pre-restore buffer.
            restored = s.open_note(p["note_id"])
        except Exception as e:
            failed("restore", e)
        if restored is not None and editor.note_id == p["note_id"]:
            editor.bind_note(restored)
        st.reload_scratchpad()
        st.select_scratchpad_note(p["note_id"])
        return {}

    @br.command("scratchpad.export", {**NOTE,
                                      "format": Enum(("markdown", "plain"))})
    def export(p):
        coord = ctl.coordinator
        detail = rendered(p["note_id"])
        if coord is None:
            B.unavailable()
        out = editor.flush_now()
        if out.get("outcome") not in ("flushed", "no_change"):
            B.refuse("not_saved_yet")
        from ....note_export import _slug
        name = _slug(detail.get("title") or "", "note")[:40] + \
            (".md" if p["format"] == "markdown" else ".txt")
        path = (panels.save_path(name) if panels is not None
                else _save_panel(name))
        if not path:
            raise B.Outcome("cancelled", "cancelled")
        report = coord.hubExportNote(p["note_id"], path, p["format"]) or {}
        if not report.get("ok"):
            B.refuse(f"export_failed:{report.get('reason')}")
        return {"bytes": report.get("bytes"),
                "unsupported": len(report.get("unsupported") or ())}

    @br.command("scratchpad.attach", NOTE)
    def attach(p):
        s = svc()
        rendered(p["note_id"])
        model = editor.model
        path = panels.open_image() if panels is not None else _open_panel()
        if not path:
            raise B.Outcome("cancelled", "cancelled")
        # The dialog was modal: the owner and the marker must be the note
        # that was shown when it opened.
        if editor.note_id != p["note_id"] or editor.model is not model:
            B.stale("note_changed")
        try:
            data = pathlib.Path(path).read_bytes()
            ext = pathlib.Path(path).suffix.lstrip(".").lower() or "png"
            out = s.add_attachment(p["note_id"], data, "image/" + ext,
                                   pathlib.Path(path).name)
        except Exception as e:
            failed("add_image", e)
        editor.insert_attachment_marker(out["marker"])
        st.reload_scratchpad()
        return {}

    @br.command("scratchpad.transform", {**NOTE,
                                         "transform_id": Str(max_len=200)})
    def transform(p):
        coord = ctl.coordinator
        rendered(p["note_id"])
        if coord is None or not hasattr(coord, "tfRunNoteTransform"):
            B.unavailable()
        snap = coord._transforms_snapshot()
        defn = snap.by_id(p["transform_id"]) if snap is not None else None
        if defn is None or not defn.enabled:
            B.refuse("choose_transform")
        kind, rng = editor.selection()
        if kind == "invalid":
            B.refuse("selection_unreadable")
        content = editor.model.content
        if kind == "range":
            source, scope = content[rng[0]:rng[1]], "selection"
        else:
            source, rng, scope = content, None, "whole"
        coord.tfRunNoteTransform(
            defn.transform_id, source, rng,
            {"note_id": editor.note_id,
             "revision_id": editor.model.revision_id}, scope=scope)
        return {"scope": scope}

    @br.command("scratchpad.delete", NOTE)
    def delete(p):
        s = svc()
        coord = ctl.coordinator
        rendered(p["note_id"])
        try:
            payload = s.delete_note(p["note_id"])
        except Exception as e:
            failed("delete", e)
        if coord is not None:
            coord.hubNoteDeleted(payload or {"note_id": p["note_id"]})
        editor.forget_note(p["note_id"])
        st.close_scratchpad_tab(p["note_id"])
        st.reload_scratchpad()
        return {"pending_purges": (payload or {}).get("pending_purges") or 0}

    # ---- the editor follows the state (the AppKit refresh rule) ----------------

    def sync_editor():
        """Rebind when the NOTE changed, or when the persisted revision
        moved under a CLEAN buffer it does not already know; a dirty
        buffer is newer than the store and keeps the editor."""
        if st.selected_view != "scratchpad":
            return
        view = st.views["scratchpad"]
        detail = view.get("detail")
        if view.get("error"):
            return
        if detail is not None:
            wanted = detail["note_id"]
            current_rev = (detail.get("revision") or {}).get("revision_id")
            model = editor.model
            if editor.note_id != wanted or (
                    model is not None and not model.dirty
                    and model.revision_id != current_rev
                    and not model.knows(current_rev)):
                editor.bind_note(detail)
        elif editor.note_id is not None:
            editor.clear()
    ctl.pre_flush_hooks.append(sync_editor)

    # ---- the coordinator's Scratchpad surface (hub.py's names) ------------------

    def editor_active():
        return editor.editor_active()

    def capture_target():
        from .... import ids
        if editor.model is None or editor.note_id is None:
            return None
        kind, rng = editor.selection()
        if rng is None:
            return {"note_id": editor.note_id, "insertion_point": None}
        anchor = rng[0]
        return {"note_id": editor.note_id, "insertion_point": anchor,
                "selection_length": rng[1] - rng[0],
                "prefix_sha256": ids.sha256_text(
                    editor.model.content[:anchor])}

    def receive(text, job):
        from .... import ids
        from ....notes import ORIGIN_DICTATED
        target = (job or {}).get("note_target") or {}

        def refuse(reason):
            if job is not None:
                job["note_refusal"] = reason
            return None
        if editor.model is None:
            return refuse("note_closed_during_dictation")
        if editor.note_id != target.get("note_id"):
            return refuse("note_changed_during_dictation")
        anchor = target.get("insertion_point")
        if anchor is None:
            return refuse("note_anchor_invalid")
        content = editor.model.content
        if anchor > len(content) or target.get("prefix_sha256") != \
                ids.sha256_text(content[:anchor]):
            return refuse("note_changed_during_dictation")
        arrival = editor.receive(
            text, origin=ORIGIN_DICTATED,
            source_job_id=(job or {}).get("job_id"), at_chars=anchor)
        return arrival if arrival is not None else \
            refuse("note_closed_during_dictation")

    def apply_transform(result, capture):
        from ....notes import ORIGIN_TRANSFORM, note_destination_check
        if editor.model is None:
            return None, "note_not_open"
        dest = capture.get("destination")
        if dest is None and capture.get("range") is not None:
            dest = {"note_id": (capture.get("note") or {}).get("note_id"),
                    "range": capture.get("range"),
                    "text": capture.get("source")}
        ok, reason = note_destination_check(dest, editor.note_id,
                                            editor.model.content)
        if not ok:
            return None, reason
        job = result.job
        arrival = editor.receive(
            result.output, origin=ORIGIN_TRANSFORM,
            source_job_id=job.parent_job_id if job is not None else None,
            task_key=job.task_key() if job is not None else None,
            transform_id=job.transform_id if job is not None else None,
            transform_revision=(job.transform_revision
                                if job is not None else None),
            replace_range=tuple(dest["range"]))
        return (arrival, None) if arrival is not None \
            else (None, "note_not_open")

    def shutdown(timeout=3.0):
        return editor.shutdown(timeout)

    def note_created(note_id):
        st.reload_scratchpad()
        st.select_scratchpad_note(note_id)

    def quick_open():
        st.select_view("scratchpad")
        ctl.emit("shell.route", {"view": "scratchpad"})
        try:
            new({})
        except B.Outcome:
            return
        ctl.emit("scratchpad.focus_editor", {})

    ctl.scratchpad_editor_active = editor_active
    ctl.scratchpad_capture_target = capture_target
    ctl.scratchpad_receive = receive
    ctl.scratchpad_apply_transform = apply_transform
    ctl.scratchpad_shutdown = shutdown
    ctl.scratchpad_note_created = note_created
    ctl.scratchpad_quick_open = quick_open


def _save_panel(name):
    from AppKit import NSSavePanel
    panel = NSSavePanel.savePanel()
    panel.setNameFieldStringValue_(name)
    if panel.runModal() != 1 or not panel.URL():
        return None
    return str(panel.URL().path())


def _open_panel():
    from AppKit import NSOpenPanel
    panel = NSOpenPanel.openPanel()
    panel.setCanChooseDirectories_(False)
    panel.setCanChooseFiles_(True)
    panel.setAllowsMultipleSelection_(False)
    panel.setAllowedFileTypes_(["png", "jpg", "jpeg", "gif", "heic",
                                "webp", "tiff"])
    if panel.runModal() != 1 or not panel.URLs():
        return None
    return str(panel.URLs()[0].path())


def scratchpad_model(ctl):
    v = ctl.state.views["scratchpad"]
    data = v.get("data")
    detail = v.get("detail")
    editor = getattr(ctl, "scratchpad_editor", None)
    notes = (data or {}).get("notes") or []
    by_id = {n.get("note_id"): n for n in notes}
    coord = ctl.coordinator
    transforms = []
    if coord is not None and hasattr(coord, "_transforms_snapshot"):
        try:
            snap = coord._transforms_snapshot()
            transforms = [{"transform_id": d.transform_id, "name": d.name}
                          for d in (snap.definitions if snap else [])
                          if d.enabled]
        except Exception:
            transforms = []
    return {
        "loading": bool(v.get("loading")), "error": v.get("error"),
        "search": v.get("search") or "",
        "notes": None if data is None else [
            {k: n.get(k) for k in ("note_id", "title", "pinned",
                                   "updated_at_utc", "created_at_utc",
                                   "word_count", "revision_count")}
            for n in notes],
        "tabs": [{"note_id": nid,
                  "title": (by_id.get(nid) or {}).get("title")}
                 for nid in v.get("open_ids") or ()],
        "selected_id": v.get("selected_id"),
        "detail": None if not detail else {
            "note_id": detail.get("note_id"), "title": detail.get("title"),
            "pinned": bool(detail.get("pinned")),
            "word_count": (detail.get("revision") or {}).get(
                "word_count", detail.get("word_count")),
            "updated_at_utc": detail.get("updated_at_utc"),
            "versions": [{k: x.get(k) for k in (
                "revision_id", "origin", "trigger", "word_count",
                "restore_of", "created_at_utc")}
                for x in detail.get("versions") or ()],
            "versions_truncated": bool(detail.get("versions_truncated")),
            "attachments": [{k: a.get(k) for k in (
                "attachment_id", "filename", "bytes", "purged")}
                for a in detail.get("attachments") or ()],
            "unsaved_tail_risk": detail.get("unsaved_tail_risk")},
        "editor": {"note_id": editor.note_id if editor else None,
                   "unsaved": editor.unsaved_notes() if editor else []},
        "transforms": transforms,
        "note": ctl.notes.get("scratchpad"),
    }


READ_MODELS = {"scratchpad": scratchpad_model}
