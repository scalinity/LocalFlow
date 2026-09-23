"""HubState — the Hub's view-model (V2 M09, contract hub.md).

Pure-Python state with no AppKit import: everything EV-11 names at the
state level is testable headless here (view transitions, search, close
vs quit, empty/undated history, selection preservation across
close/reopen, keyboard-driven view switching). The AppKit shell in
``hub.py`` binds to this object and never owns data logic.

Thread discipline: queries run on one daemon query thread; results are
published to ``on_update`` (the shell dispatches to the main thread).
Searches are cancellable by generation — a stale result is dropped,
never rendered (S19). The state itself is mutated only from the
calling/main context plus the query thread's guarded publish.
"""

from __future__ import annotations

import threading

VIEWS = ("home", "history", "styles", "snippets", "transforms",
         "scratchpad", "diagnostics", "models", "settings")

VIEW_TITLES = {
    "home": "Home",
    "history": "History",
    "styles": "Styles",
    "snippets": "Snippets",
    "transforms": "Transforms",
    "scratchpad": "Scratchpad",
    "diagnostics": "Diagnostics",
    "models": "Models",
    "settings": "Settings",
}


class HubState:
    def __init__(self, history_service, training_service=None,
                 diagnostics_provider=None, coordinator=None,
                 styles_service=None, snippets_service=None,
                 transforms_service=None, notes_service=None):
        """``diagnostics_provider()`` returns a dict with events_dir and
        whatever filters the shell set; ``coordinator`` is the app
        delegate's command surface (engine states, pipeline info,
        recovery, paste/retry commands, M10 effective-profile/preview).
        ``styles_service``/``snippets_service``/``transforms_service``/
        ``notes_service`` are the M10–M12 stores (the training_service
        pattern: read/CRUD through the service, never a second store
        connection)."""
        self.history_service = history_service
        self.training_service = training_service
        self.styles_service = styles_service
        self.snippets_service = snippets_service
        self.transforms_service = transforms_service
        self.notes_service = notes_service
        self.diagnostics_provider = diagnostics_provider \
            or (lambda: {"events_dir": None})
        self.coordinator = coordinator
        self.selected_view = "home"
        self.visible = False
        self.views = {v: self._blank_view(v) for v in VIEWS}
        self._query_lock = threading.Lock()
        self._query_thread = None
        self._generation = 0
        self.on_update = None  # shell installs; called after publishes

    # ---- view switching (mouse, keyboard ⌘1..⌘5, arrows all land here)

    @staticmethod
    def _blank_view(view):
        state = {"loading": False, "error": None, "search": "",
                 "selected_id": None, "selected_kind": None,
                 "detail": None, "data": None}
        if view == "diagnostics":
            state.update({"utc": False, "job_filter": "",
                          "level_filter": None})
        if view == "models":
            state.update({"subview": "engines"})
        if view in ("styles", "snippets", "transforms"):
            state.update({"selected_id": None, "preview": None})
        if view == "scratchpad":
            state.update({"selected_id": None, "open_ids": [],
                          "versions": [], "attachments": [],
                          "unsaved_tail_risk": None})
        return state

    def select_view(self, view):
        if view not in VIEWS:
            raise ValueError(f"unknown view {view!r}")
        self.selected_view = view
        self.reload_current()
        self._publish()

    def select_view_by_index(self, index):
        self.select_view(VIEWS[int(index) % len(VIEWS)])

    def next_view(self, step=1):
        i = VIEWS.index(self.selected_view)
        self.select_view(VIEWS[(i + step) % len(VIEWS)])

    # ---- window lifecycle (close ≠ quit: M09-AC04) ----------------------

    def close(self):
        """Hide only. The menu-bar dictation service is untouched and
        every view's selection/search state survives (the controller
        object persists; nothing is deallocated)."""
        self.visible = False
        self._publish()

    def show(self):
        self.visible = True
        self.reload_current()
        self._publish()

    # ---- History ----------------------------------------------------------

    def set_history_search(self, text):
        self.views["history"]["search"] = text
        self.reload_history()

    def select_history_row(self, kind, row_id):
        self.views["history"]["selected_kind"] = kind
        self.views["history"]["selected_id"] = row_id
        self.reload_current(detail_only=True)

    def reload_history(self):
        self._spawn(self._load_history)

    def _load_history(self, generation):
        view = self.views["history"]
        text = view["search"].strip() or None
        try:
            result = self.history_service.search(text=text)
        except Exception as e:
            self._publish_locked("history", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return  # a newer search superseded this one
        rows = [r for g in result["groups"] for r in g["rows"]]
        sel = view["selected_id"]
        expired = sel is not None and not any(r["id"] == sel for r in rows)
        self._publish_locked("history", error=None, loading=False,
                             data=result)
        if expired and generation == self._generation:
            # Selection expired (deleted/pruned): clear honestly rather
            # than showing a stale detail pane. Re-checked after the
            # publish so a concurrent newer operation is never
            # clobbered by this one.
            self._publish_locked("history", selected_id=None,
                                 selected_kind=None, detail=None)

    def _load_history_detail(self, generation):
        view = self.views["history"]
        kind, row_id = view["selected_kind"], view["selected_id"]
        if kind is None or row_id is None:
            return
        try:
            if kind == "job":
                detail = self.history_service.job_detail(row_id)
            else:
                detail = self.history_service.legacy_detail(row_id)
        except Exception as e:
            self._publish_locked("history", error=type(e).__name__)
            return
        if generation != self._generation:
            return
        self._publish_locked("history", detail=detail)

    # ---- Models → Training Data -------------------------------------------

    def select_models_subview(self, subview):
        if subview not in ("engines", "training"):
            raise ValueError(f"unknown subview {subview!r}")
        self.views["models"]["subview"] = subview
        self.reload_current()
        self._publish()

    def set_training_search(self, text):
        self.views["models"]["search"] = text
        self.reload_training()

    def select_training_example(self, example_id):
        # E14: listening is per-example — selecting a different example
        # closes any verbatim gate a previous replay opened for another.
        if self.views["models"].get("selected_id") != example_id:
            self.views["models"]["listened_for"] = None
        self.views["models"]["selected_id"] = example_id
        self._spawn(self._load_training_detail)

    def reload_training(self):
        self._spawn(self._load_training)

    def _load_training(self, generation):
        if self.training_service is None:
            return
        view = self.views["models"]
        text = view["search"].strip() or None
        try:
            rows = self.training_service.examples(text=text)
            readiness = self.training_service.readiness(
                consent_state=(self.coordinator.collection_state()
                               if self.coordinator else None))
        except Exception as e:
            self._publish_locked("models", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("models", error=None, loading=False,
                             data={"examples": rows,
                                   "readiness": readiness})

    def _load_training_detail(self, generation):
        if self.training_service is None:
            return
        ex_id = self.views["models"]["selected_id"]
        if ex_id is None:
            return
        try:
            detail = self.training_service.example_detail(ex_id)
        except Exception as e:
            self._publish_locked("models", error=type(e).__name__)
            return
        if generation != self._generation:
            return
        self._publish_locked("models", detail=detail)

    # ---- Styles / Snippets (M10, Spec S15/S17) --------------------------

    def reload_styles(self):
        self._spawn(self._load_styles)

    def _load_styles(self, generation):
        if self.styles_service is None:
            self._publish_locked("styles", error="styles_unavailable",
                                 loading=False)
            return
        try:
            rules = [r.to_json() for r in self.styles_service.rules()]
            effective = self.coordinator.hubEffectiveProfile() \
                if self.coordinator is not None else None
        except Exception as e:
            self._publish_locked("styles", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("styles", error=None, loading=False,
                             data={"rules": rules,
                                   "effective": effective})

    def reload_snippets(self):
        self._spawn(self._load_snippets)

    def _load_snippets(self, generation):
        if self.snippets_service is None:
            self._publish_locked("snippets", error="snippets_unavailable",
                                 loading=False)
            return
        try:
            from .. import snippets as snippets_mod
            stored = self.snippets_service.snippets()  # one read
            rows = [s.to_json() for s in stored]
            # The frozen registry view the engine would build now —
            # masked duplicate triggers surface here, exactly as they
            # would behave at dictation time.
            snapshot = snippets_mod.SnippetSnapshot(stored)
            conflicts = list(snapshot.conflicts)
        except Exception as e:
            self._publish_locked("snippets", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("snippets", error=None, loading=False,
                             data={"snippets": rows,
                                   "conflicts": conflicts})

    def set_developer_preview(self, view, preview):
        self.views[view]["preview"] = preview
        self._publish()

    # ---- Transforms (M11, Spec S16) --------------------------------------

    def reload_transforms(self):
        self._spawn(self._load_transforms)

    def _load_transforms(self, generation):
        if self.transforms_service is None:
            self._publish_locked("transforms",
                                 error="transforms_unavailable",
                                 loading=False)
            return
        try:
            from .. import transforms as transforms_mod
            stored = self.transforms_service.definitions()
            rows = [d.to_json() for d in stored]
            snapshot = transforms_mod.TransformSnapshot(stored)
            conflicts = transforms_mod.shortcut_conflicts(
                snapshot.definitions)
        except Exception as e:
            self._publish_locked("transforms", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("transforms", error=None, loading=False,
                             data={"transforms": rows,
                                   "shortcut_conflicts": conflicts})

    # ---- Scratchpad (M12, Spec S20) --------------------------------------

    def set_scratchpad_search(self, text):
        self.views["scratchpad"]["search"] = text
        self.reload_scratchpad()

    def select_scratchpad_note(self, note_id):
        view = self.views["scratchpad"]
        if note_id is not None and note_id not in view["open_ids"]:
            view["open_ids"] = (view["open_ids"] + [note_id])[-8:]
        view["selected_id"] = note_id
        self._spawn(self._load_scratchpad_both)

    def close_scratchpad_tab(self, note_id):
        view = self.views["scratchpad"]
        open_ids = [i for i in view["open_ids"] if i != note_id]
        view["open_ids"] = open_ids
        if view["selected_id"] == note_id:
            view["selected_id"] = open_ids[-1] if open_ids else None
            # The editor must not stay bound to the closed note: load
            # the newly selected tab's detail (or clear it honestly).
            self._spawn(self._load_scratchpad_detail)
        else:
            self._publish()

    def reload_scratchpad(self):
        self._spawn(self._load_scratchpad_both)

    def _load_scratchpad_both(self, generation):
        """One loader for list + detail (select/reload paths): the list
        load and the detail load share a generation, so a select can
        never supersede (and silently drop) the list refresh — the note
        that was just created actually appears in the table."""
        self._load_scratchpad(generation)
        if generation == self._generation:
            self._load_scratchpad_detail(generation)

    def _load_scratchpad(self, generation):
        if self.notes_service is None:
            self._publish_locked("scratchpad",
                                 error="notes_unavailable", loading=False)
            return
        view = self.views["scratchpad"]
        text = view["search"].strip()
        try:
            notes = (self.notes_service.search(text) if text
                     else self.notes_service.notes())
        except Exception as e:
            self._publish_locked("scratchpad", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("scratchpad", error=None, loading=False,
                             data={"notes": notes})

    def _load_scratchpad_detail(self, generation):
        if self.notes_service is None:
            return
        note_id = self.views["scratchpad"]["selected_id"]
        if note_id is None:
            self._publish_locked("scratchpad", detail=None)
            return
        try:
            detail = self.notes_service.open_note(note_id)
        except Exception as e:
            self._publish_locked("scratchpad", error=type(e).__name__)
            return
        if generation != self._generation:
            return
        if detail is None:
            # Deleted elsewhere: clear honestly, never a stale editor.
            self._publish_locked("scratchpad", selected_id=None,
                                 detail=None)
            return
        self._publish_locked("scratchpad", detail=detail)

    # ---- Diagnostics --------------------------------------------------------

    def set_diagnostics_filters(self, job=None, level=None, utc=None):
        view = self.views["diagnostics"]
        if job is not None:
            view["job_filter"] = job
        if level is not None:
            view["level_filter"] = level
        if utc is not None:
            view["utc"] = bool(utc)
        self._spawn(self._load_diagnostics)

    def _load_diagnostics(self, generation):
        from .. import diagnostics as diag
        spec = self.diagnostics_provider() or {}
        view = self.views["diagnostics"]
        try:
            events = diag.load_events(
                spec.get("events_dir"), job_id=view["job_filter"] or None,
                level=view["level_filter"],
                last=spec.get("last", 500)) or []
            rendered = [diag.render(r, view["utc"]) for r in events]
            block = diag.engine_block(
                spec.get("pipeline_info") or {},
                spec.get("engine_states") or {})
            # A job filter also assembles the dated timeline for that
            # one job (stage transitions in sequence order).
            timeline = diag.job_timeline(
                diag.load_events(spec.get("events_dir")),
                view["job_filter"]) if view["job_filter"] else []
        except Exception as e:
            self._publish_locked("diagnostics", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("diagnostics", error=None, loading=False,
                             data={"events": rendered, "engine": block,
                                   "count": len(events),
                                   "timeline": timeline})

    # ---- Home / Settings -----------------------------------------------------

    def _load_home(self, generation):
        try:
            summary = self.history_service.home_summary()
            engine = {}
            recovery = {}
            if self.coordinator is not None:
                engine = self.coordinator.hubEngineStates()
                recovery = self.coordinator.hubRecoveryInfo()
        except Exception as e:
            self._publish_locked("home", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("home", error=None, loading=False,
                             data={"summary": summary, "engine": engine,
                                   "recovery": recovery})

    def _load_settings(self, generation):
        data = {}
        if self.coordinator is not None:
            data = {
                "collection_state": self.coordinator.collection_state(),
                "retention": dict(getattr(
                    self.coordinator, "hubRetentionDays", lambda: {})()),
            }
        self._publish_locked("settings", error=None, loading=False,
                             data=data)

    # ---- query plumbing -------------------------------------------------------

    def reload_current(self, detail_only=False):
        view = self.selected_view
        if view == "home":
            self._spawn(self._load_home)
        elif view == "history":
            if detail_only:
                self._spawn(self._load_history_detail)
            else:
                self.reload_history()
        elif view == "styles":
            self.reload_styles()
        elif view == "snippets":
            self.reload_snippets()
        elif view == "transforms":
            self.reload_transforms()
        elif view == "scratchpad":
            self.reload_scratchpad()
        elif view == "diagnostics":
            self._spawn(self._load_diagnostics)
        elif view == "models":
            if self.views["models"]["subview"] == "training":
                self.reload_training()
            else:
                self._spawn(self._load_models_engines)
        elif view == "settings":
            self._spawn(self._load_settings)

    def _load_models_engines(self, generation):
        from .. import diagnostics as diag
        spec = self.diagnostics_provider() or {}
        try:
            block = diag.engine_block(
                spec.get("pipeline_info") or {},
                spec.get("engine_states") or {})
        except Exception as e:
            self._publish_locked("models", error=type(e).__name__,
                                 loading=False)
            return
        if generation != self._generation:
            return
        self._publish_locked("models", error=None, loading=False,
                             data={"engine": block})

    def _spawn(self, fn):
        """Run one query asynchronously; every in-flight query is
        superseded by the next (cancellable searches, S19)."""
        with self._query_lock:
            self._generation += 1
            generation = self._generation
            done = threading.Event()

            def run():
                try:
                    fn(generation)
                finally:
                    done.set()

            self._query_thread = threading.Thread(
                target=run, daemon=True, name="localflow-hub-query")
            self._query_thread._done = done
            self._query_thread.start()

    def wait_for_queries(self, timeout=10.0):
        t = self._query_thread
        if t is not None:
            t.join(timeout)
        return not (t and t.is_alive())

    def _publish(self):
        if self.on_update is not None:
            try:
                self.on_update(self)
            except Exception:
                pass

    def _publish_locked(self, view, **changes):
        self.views[view].update(changes)
        self._publish()
