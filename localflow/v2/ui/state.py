"""HubState — the Hub's view-model (V2 M09, contract hub.md).

Pure-Python state with no AppKit import: everything EV-11 names at the
state level is testable headless here (view transitions, search, close
vs quit, empty/undated history, selection preservation across
close/reopen, keyboard-driven view switching). The AppKit shell in
``hub.py`` binds to this object and never owns data logic.

Query discipline: every load is a request admitted with an immutable
snapshot of its inputs and the next generation for its KEY — a view's
``list`` or ``detail`` part. One worker thread runs admitted requests
in admission order; a newer request for a key replaces an older one
that has not started yet (the older one never runs), so rapid input
costs at most one running and one pending query per key, never a
thread per keystroke. A result publishes only if, under the state
lock, its request is still the newest for its key and a detail request
still names the selected item — the check and the mutation are one
step, and success, error and loading all follow it. Observers are
notified after the lock is released.

Selection: choosing another History row or Training example clears the
previous detail at once; the shell's actions bind to the rendered
detail of the selected item, so no interval exists in which B is
selected while A's detail is still actionable.

Deletion: ``revoke_job`` runs inside the store's delete-everywhere op
(the store's deletion listener, on the writer thread). It only marks
the job revoked and scrubs cached rows/detail under the lock — pure
data, no store call, no AppKit work. Every later publication is fenced
by the revoked set, and a request that was executing when a revocation
(or a retention pass, ``revalidate``) happened is dropped and re-run,
so a read taken before the deletion can never republish its text.
"""

from __future__ import annotations

import collections
import threading

VIEWS = ("home", "history", "styles", "snippets", "transforms",
         "scratchpad", "insights", "diagnostics", "models", "settings")

VIEW_TITLES = {
    "home": "Home",
    "history": "History",
    "styles": "Styles",
    "snippets": "Snippets",
    "transforms": "Transforms",
    "scratchpad": "Scratchpad",
    "insights": "Insights",
    "diagnostics": "Diagnostics",
    "models": "Models",
    "settings": "Settings",
}

# The Insights range selector's fixed choices (days; None = all time).
INSIGHT_RANGES = (7, 30, 90, None)

# The Training Data pane's M14 sections (S29.15: mining, classified
# review, split selection and portable export on the same surface).
TRAINING_TABS = ("evidence", "review", "splits", "export")

QUERY_THREAD_NAME = "localflow-hub-query-worker"


class _Request:
    """One admitted load: its key, generation, loader and the inputs
    captured at admission. ``epoch`` is the revocation epoch observed
    when the worker started it."""

    __slots__ = ("key", "gen", "fn", "inputs", "epoch")

    def __init__(self, key, gen, fn, inputs):
        self.key = key
        self.gen = gen
        self.fn = fn
        self.inputs = inputs
        self.epoch = None


class QueryExecutor:
    """One long-lived worker thread with per-key latest-request
    coalescing and full accounting (every admitted request is started,
    or counted as superseded before it started)."""

    def __init__(self, name=QUERY_THREAD_NAME):
        self._cond = threading.Condition()
        self._pending = collections.OrderedDict()
        self._running = None
        self._thread = None
        self._name = name
        self._closed = False
        self.stats = {"admitted": 0, "superseded_before_start": 0,
                      "started": 0, "completed": 0, "peak_pending": 0,
                      "threads_started": 0}

    def submit(self, req, before_run) -> bool:
        with self._cond:
            if self._closed:
                return False
            if req.key in self._pending:
                del self._pending[req.key]
                self.stats["superseded_before_start"] += 1
            self._pending[req.key] = (req, before_run)
            self.stats["admitted"] += 1
            self.stats["peak_pending"] = max(self.stats["peak_pending"],
                                             len(self._pending))
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, daemon=True, name=self._name)
                self.stats["threads_started"] += 1
                self._thread.start()
            self._cond.notify_all()
        return True

    def _run(self):
        while True:
            with self._cond:
                while not self._pending and not self._closed:
                    self._cond.wait()
                if not self._pending:
                    return
                _key, (req, before_run) = self._pending.popitem(last=False)
                self._running = req
                self.stats["started"] += 1
            try:
                before_run(req)
                req.fn(req)
            except Exception:
                pass  # loaders publish their own (guarded) errors
            finally:
                with self._cond:
                    self._running = None
                    self.stats["completed"] += 1
                    self._cond.notify_all()

    def idle(self) -> bool:
        with self._cond:
            return not self._pending and self._running is None

    def wait_idle(self, timeout) -> bool:
        with self._cond:
            return self._cond.wait_for(
                lambda: not self._pending and self._running is None,
                timeout)

    def close(self):
        """Closed admission: pending requests are dropped (counted as
        superseded); a running one finishes and its publication is
        refused by the closed state."""
        with self._cond:
            self._closed = True
            self.stats["superseded_before_start"] += len(self._pending)
            self._pending.clear()
            self._cond.notify_all()


def _drop_history_rows(data, revoked):
    groups = []
    total = 0
    for g in data.get("groups") or []:
        rows = [r for r in g["rows"]
                if not (r.get("kind") == "job" and r.get("id") in revoked)]
        if rows:
            groups.append({"label": g["label"], "rows": rows})
            total += len(rows)
    return {**data, "groups": groups, "total": total}


def _drop_model_rows(data, revoked):
    out = dict(data)
    for key in ("examples", "queue"):
        if out.get(key):
            out[key] = [r for r in out[key]
                        if r.get("job_id") not in revoked]
    return out


class HubState:
    def __init__(self, history_service, training_service=None,
                 diagnostics_provider=None, coordinator=None,
                 styles_service=None, snippets_service=None,
                 transforms_service=None, notes_service=None,
                 insights_service=None, learning_service=None,
                 review_service=None, sampling_service=None,
                 splits_service=None, profile_service=None,
                 export_service=None, transforms_store=None):
        """``diagnostics_provider()`` returns a dict with events_dir and
        whatever filters the shell set; ``coordinator`` is the app
        delegate's command surface (engine states, pipeline info,
        recovery, paste/retry commands, M10 effective-profile/preview).
        ``styles_service``/``snippets_service``/``transforms_service``/
        ``notes_service``/``insights_service`` are the M10–M13 stores
        (the training_service pattern: read/CRUD through the service,
        never a second store connection). The M14 services
        (``learning``/``review``/``sampling``/``splits``/``profile``/
        ``export`` + ``transforms_store`` for pair judgments) follow
        the same pattern; absent services degrade honestly per view."""
        self.history_service = history_service
        self.training_service = training_service
        self.styles_service = styles_service
        self.snippets_service = snippets_service
        self.transforms_service = transforms_service
        self.notes_service = notes_service
        self.insights_service = insights_service
        self.learning_service = learning_service
        self.review_service = review_service
        self.sampling_service = sampling_service
        self.splits_service = splits_service
        self.profile_service = profile_service
        self.export_service = export_service
        self.transforms_store = transforms_store
        self.diagnostics_provider = diagnostics_provider \
            or (lambda: {"events_dir": None})
        self.coordinator = coordinator
        self.selected_view = "home"
        self.visible = False
        self.views = {v: self._blank_view(v) for v in VIEWS}
        self._lock = threading.RLock()
        self._gens = {}
        self._admitted = 0
        self._epoch = 0
        self._closed = False
        self._revoked_jobs = set()
        self._executor = QueryExecutor()
        self.on_update = None   # shell installs; called after publishes
        self.on_revoked = None  # shell installs; called after revoke_job

    @property
    def _generation(self):
        """Monotonic admission counter (every admitted request)."""
        return self._admitted

    # ---- view switching (mouse, keyboard ⌘1..⌘5, arrows all land here)

    @staticmethod
    def _blank_view(view):
        state = {"loading": False, "error": None, "search": "",
                 "selected_id": None, "selected_kind": None,
                 "detail": None, "data": None, "detail_loading": False,
                 "detail_error": None, "detail_key": None}
        if view == "history":
            state.update({"app": None, "mode": None})
        if view == "diagnostics":
            state.update({"utc": False, "job_filter": "",
                          "level_filter": None})
        if view == "models":
            state.update({"subview": "engines",
                          "training_tab": "evidence"})
        if view in ("styles", "snippets", "transforms"):
            state.update({"selected_id": None, "preview": None})
        if view == "scratchpad":
            state.update({"selected_id": None, "open_ids": [],
                          "versions": [], "attachments": [],
                          "unsaved_tail_risk": None})
        if view == "insights":
            state.update({"range": 30, "app": None, "mode": None,
                          "subview": "usage"})
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
        if self.selected_view in ("history", "models"):
            self.reload_current(detail_only=True)
        self._publish()

    def shutdown(self):
        """App quit: admission closes, pending loads are dropped and no
        later publication or notification reaches the shell."""
        with self._lock:
            self._closed = True
        self._executor.close()

    # ---- History ----------------------------------------------------------

    def set_history_search(self, text):
        self.set_history_filters(text=text)

    def set_history_filters(self, text=..., app=..., mode=...):
        """Text / app / mode filters (``...`` leaves a field unchanged;
        an empty app or ``None`` mode clears that filter)."""
        if mode is not ... and mode is not None:
            from ..history_queries import MODES
            if mode not in MODES:
                raise ValueError(f"unknown mode filter {mode!r}")
        with self._lock:
            view = self.views["history"]
            if text is not ...:
                view["search"] = text or ""
            if app is not ...:
                view["app"] = (app or "").strip() or None
            if mode is not ...:
                view["mode"] = mode or None
        self.reload_history()

    def select_history_row(self, kind, row_id):
        with self._lock:
            view = self.views["history"]
            if (view["selected_kind"], view["selected_id"]) != \
                    (kind, row_id):
                view.update(selected_kind=kind, selected_id=row_id,
                            detail=None, detail_key=None,
                            detail_error=None)
        self._spawn_history_detail()
        self._publish()

    def reload_history(self):
        with self._lock:
            view = self.views["history"]
            inputs = {"text": (view["search"] or "").strip() or None,
                      "app": view.get("app"), "mode": view.get("mode")}
        self._spawn(("history", "list"), self._load_history, **inputs)

    def _spawn_history_detail(self):
        with self._lock:
            view = self.views["history"]
            kind, row_id = view["selected_kind"], view["selected_id"]
        if kind is None or row_id is None:
            return
        self._spawn(("history", "detail"), self._load_history_detail,
                    kind=kind, row_id=row_id)

    def _load_history(self, req):
        try:
            result = self.history_service.search(
                text=req.inputs["text"], app=req.inputs["app"],
                mode=req.inputs["mode"])
        except Exception as e:
            self._publish_locked("history", req, error=type(e).__name__,
                                 loading=False)
            return

        def expire_selection(view):
            # Selection expired (deleted/pruned/filtered out): clear
            # honestly rather than keep a hidden actionable detail.
            sel = (view["selected_kind"], view["selected_id"])
            if sel[1] is None:
                return
            rows = [r for g in (view.get("data") or {}).get("groups", ())
                    for r in g["rows"]]
            if not any((r["kind"], r["id"]) == sel for r in rows):
                view.update(selected_kind=None, selected_id=None,
                            detail=None, detail_key=None,
                            detail_error=None, detail_loading=False)
        self._publish_locked("history", req, after=expire_selection,
                             error=None, loading=False, data=result)

    def _load_history_detail(self, req):
        kind, row_id = req.inputs["kind"], req.inputs["row_id"]
        try:
            if kind == "job":
                detail = self.history_service.job_detail(row_id)
            elif kind == "legacy_db":
                detail = self.history_service.legacy_db_detail(row_id)
            else:
                detail = self.history_service.legacy_detail(row_id)
        except Exception as e:
            self._publish_locked("history", req, detail=None,
                                 detail_key=None, detail_loading=False,
                                 detail_error=type(e).__name__)
            return
        self._publish_locked("history", req, detail=detail,
                             detail_key=(kind, row_id),
                             detail_loading=False,
                             detail_error=None if detail is not None
                             else "not_found")

    # ---- Models → Training Data -------------------------------------------

    def select_models_subview(self, subview):
        if subview not in ("engines", "training"):
            raise ValueError(f"unknown subview {subview!r}")
        self.views["models"]["subview"] = subview
        self.reload_current()
        self._publish()

    def select_training_tab(self, tab):
        """The Training Data pane's M14 sections (S29.15)."""
        if tab not in TRAINING_TABS:
            raise ValueError(f"unknown training tab {tab!r}")
        self.views["models"]["training_tab"] = tab
        self.reload_training()
        self._publish()

    def set_training_search(self, text):
        self.views["models"]["search"] = text
        self.reload_training()

    def select_training_example(self, example_id):
        # E14: listening is per-example — selecting a different example
        # closes any verbatim gate a previous replay opened for another,
        # and the previous example's detail stops being actionable.
        with self._lock:
            view = self.views["models"]
            if view.get("selected_id") != example_id:
                view["listened_for"] = None
                view.update(selected_id=example_id, detail=None,
                            detail_key=None, detail_error=None)
        if example_id is not None:
            self._spawn(("models", "detail"), self._load_training_detail,
                        example_id=example_id)
        self._publish()

    def reload_training(self):
        with self._lock:
            view = self.views["models"]
            inputs = {"tab": view.get("training_tab", "evidence"),
                      "text": (view.get("search") or "").strip() or None}
        self._spawn(("models", "list"), self._load_training, **inputs)

    def _load_training(self, req):
        if self.training_service is None:
            self._publish_locked("models", req, loading=False)
            return
        tab = req.inputs["tab"]
        try:
            if tab == "evidence":
                data = {"examples": self.training_service.examples(
                    text=req.inputs["text"])}
            elif tab == "review":
                data = self._load_training_review()
            elif tab == "splits":
                data = self._load_training_splits()
            else:
                data = self._load_training_export()
            readiness = self.training_service.readiness(
                consent_state=(self.coordinator.collection_state()
                               if self.coordinator else None))
        except Exception as e:
            self._publish_locked("models", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("models", req, error=None, loading=False,
                             data={**data, "readiness": readiness,
                                   "training_tab": tab})

    def _load_training_review(self):
        """The review queue (learning candidates + sampled examples),
        the sampling coverage report and the same-task preference
        pairs awaiting judgment (S29.9/S29.10)."""
        data = {"queue": [], "coverage": None, "preference_pairs": []}
        if self.review_service is not None:
            data["queue"] = self.review_service.queue()
        if self.sampling_service is not None:
            data["coverage"] = self.sampling_service.coverage()
        if self.review_service is not None:
            data["preference_pairs"] = \
                self.review_service.preference_pairs()
        return data

    def _load_training_splits(self):
        data = {"summary": None, "families": [], "contamination": None}
        if self.splits_service is not None:
            data["summary"] = self.splits_service.summary()
            data["families"] = self.splits_service.family_report()
            data["contamination"] = self.splits_service.contamination()
        return data

    def _load_training_export(self):
        data = {"last_export": None, "views": ()}
        if self.export_service is not None:
            data["last_export"] = self.export_service.last_export()
        from ..curation.export import TASK_VIEWS
        data["views"] = tuple(TASK_VIEWS)
        return data

    def _load_training_detail(self, req):
        if self.training_service is None:
            return
        ex_id = req.inputs["example_id"]
        try:
            detail = self.training_service.example_detail(ex_id)
        except Exception as e:
            self._publish_locked("models", req, detail=None,
                                 detail_key=None, detail_loading=False,
                                 detail_error=type(e).__name__)
            return
        self._publish_locked("models", req, detail=detail,
                             detail_key=ex_id, detail_loading=False,
                             detail_error=None)

    # ---- Styles / Snippets (M10, Spec S15/S17) --------------------------

    def reload_styles(self):
        self._spawn(("styles", "list"), self._load_styles)

    def _load_styles(self, req):
        if self.styles_service is None:
            self._publish_locked("styles", req, error="styles_unavailable",
                                 loading=False)
            return
        try:
            rules = [r.to_json() for r in self.styles_service.rules()]
            effective = self.coordinator.hubEffectiveProfile() \
                if self.coordinator is not None else None
        except Exception as e:
            self._publish_locked("styles", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("styles", req, error=None, loading=False,
                             data={"rules": rules,
                                   "effective": effective})

    def reload_snippets(self):
        self._spawn(("snippets", "list"), self._load_snippets)

    def _load_snippets(self, req):
        if self.snippets_service is None:
            self._publish_locked("snippets", req,
                                 error="snippets_unavailable", loading=False)
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
            self._publish_locked("snippets", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("snippets", req, error=None, loading=False,
                             data={"snippets": rows,
                                   "conflicts": conflicts})

    def set_developer_preview(self, view, preview):
        self.views[view]["preview"] = preview
        self._publish()

    # ---- Transforms (M11, Spec S16) --------------------------------------

    def reload_transforms(self):
        self._spawn(("transforms", "list"), self._load_transforms)

    def _load_transforms(self, req):
        if self.transforms_service is None:
            self._publish_locked("transforms", req,
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
            self._publish_locked("transforms", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("transforms", req, error=None, loading=False,
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
        self.reload_scratchpad()

    def close_scratchpad_tab(self, note_id):
        view = self.views["scratchpad"]
        open_ids = [i for i in view["open_ids"] if i != note_id]
        view["open_ids"] = open_ids
        if view["selected_id"] == note_id:
            view["selected_id"] = open_ids[-1] if open_ids else None
            # The editor must not stay bound to the closed note: load
            # the newly selected tab's detail (or clear it honestly).
            self._spawn(("scratchpad", "list"),
                        self._load_scratchpad_detail,
                        note_id=view["selected_id"])
        else:
            self._publish()

    def reload_scratchpad(self):
        view = self.views["scratchpad"]
        self._spawn(("scratchpad", "list"), self._load_scratchpad_both,
                    text=(view["search"] or "").strip(),
                    note_id=view["selected_id"])

    def _load_scratchpad_both(self, req):
        """One request for list + detail (select/reload paths): they
        share a key, so a select can never supersede (and silently
        drop) the list refresh — the note that was just created
        actually appears in the table."""
        if self._load_scratchpad(req):
            self._load_scratchpad_detail(req)

    def _load_scratchpad(self, req):
        if self.notes_service is None:
            self._publish_locked("scratchpad", req,
                                 error="notes_unavailable", loading=False)
            return False
        text = req.inputs["text"]
        try:
            notes = (self.notes_service.search(text) if text
                     else self.notes_service.notes())
        except Exception as e:
            self._publish_locked("scratchpad", req, error=type(e).__name__,
                                 loading=False)
            return False
        return self._publish_locked("scratchpad", req, error=None,
                                    loading=False, data={"notes": notes})

    def _load_scratchpad_detail(self, req):
        if self.notes_service is None:
            return
        note_id = req.inputs["note_id"]
        if note_id is None:
            self._publish_locked("scratchpad", req, detail=None)
            return
        try:
            detail = self.notes_service.open_note(note_id)
        except Exception as e:
            self._publish_locked("scratchpad", req,
                                 error=type(e).__name__)
            return
        if detail is None:
            # Deleted elsewhere: clear honestly, never a stale editor.
            self._publish_locked("scratchpad", req, selected_id=None,
                                 detail=None)
            return
        self._publish_locked("scratchpad", req, detail=detail)

    # ---- Insights (M13, Spec S21) ----------------------------------------

    def set_insights_filters(self, range_days=None, app=..., mode=...):
        """Cohort filters (``...`` leaves a field unchanged). ``app``/
        ``mode`` of None clear the filter; ``range_days`` comes from
        INSIGHT_RANGES."""
        view = self.views["insights"]
        if range_days is not ...:
            if range_days is not None and range_days not in INSIGHT_RANGES:
                raise ValueError(f"unknown range {range_days!r}")
            view["range"] = range_days
        if app is not ...:
            view["app"] = app or None
        if mode is not ...:
            view["mode"] = mode or None
        self.reload_insights()

    def select_insights_subview(self, subview):
        """Usage (M13 metrics) or Your Voice (M14 profile, S22) — the
        S19 surface table puts the communication profile under
        Insights."""
        if subview not in ("usage", "voice"):
            raise ValueError(f"unknown insights subview {subview!r}")
        self.views["insights"]["subview"] = subview
        self.reload_insights()
        self._publish()

    def reload_insights(self):
        view = self.views["insights"]
        self._spawn(("insights", "list"), self._load_insights,
                    days=view["range"], app=view["app"],
                    mode=view["mode"],
                    subview=view.get("subview", "usage"))

    def _load_insights(self, req):
        if self.insights_service is None:
            self._publish_locked("insights", req,
                                 error="insights_unavailable",
                                 loading=False)
            return
        days, app, mode = (req.inputs["days"], req.inputs["app"],
                           req.inputs["mode"])
        try:
            data = {"subview": req.inputs["subview"]}
            if data["subview"] == "voice":
                # Your Voice (S22): the current profile snapshot —
                # honest measured totals; the state machine surfaces
                # invalidated/absent snapshots instead of stale cards.
                if self.profile_service is not None:
                    data["profile"] = self.profile_service.current()
                else:
                    data["profile"] = None
                    data["profile_reason"] = "profile_service_unavailable"
            else:
                summary = self.insights_service.summary(
                    days=days, app=app, mode=mode)
                daily = self.insights_service.daily(
                    days=days, app=app, mode=mode)
                per_app = ([] if app else self.insights_service.per_app(
                    days=days))
                per_mode = ([] if mode else self.insights_service.per_mode(
                    days=days))
                undated = self.insights_service.undated_count()
                legacy = self.insights_service.legacy_summary()
                apps = self.insights_service.apps_available()
                modes = self.insights_service.modes_available()
                data.update({"summary": summary, "daily": daily,
                             "per_app": per_app, "per_mode": per_mode,
                             "undated": undated, "legacy": legacy,
                             "apps": apps, "modes": modes})
        except Exception as e:
            self._publish_locked("insights", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("insights", req, error=None, loading=False,
                             data=data)

    # ---- Diagnostics --------------------------------------------------------

    def set_diagnostics_filters(self, job=..., level=..., utc=...):
        """``...`` leaves a filter unchanged; ``level=None`` (All levels)
        and ``job=""`` clear theirs."""
        view = self.views["diagnostics"]
        if job is not ...:
            view["job_filter"] = job or ""
        if level is not ...:
            view["level_filter"] = level or None
        if utc is not ...:
            view["utc"] = bool(utc)
        self._spawn_diagnostics()

    def _spawn_diagnostics(self):
        view = self.views["diagnostics"]
        self._spawn(("diagnostics", "list"), self._load_diagnostics,
                    job=view["job_filter"] or None,
                    level=view["level_filter"], utc=bool(view["utc"]))

    def _load_diagnostics(self, req):
        from .. import diagnostics as diag
        from .. import ids
        spec = self.diagnostics_provider() or {}
        job, level, utc = (req.inputs["job"], req.inputs["level"],
                           req.inputs["utc"])
        last = spec.get("last", 500)
        try:
            stats = {}
            # One parse of the retained files, ordered by the accepted
            # per-stream/UTC policy; the window and the job timeline are
            # both cut from it.
            records = diag.load_events(spec.get("events_dir"),
                                       stats=stats) \
                if spec.get("events_dir") else []
            events = diag.select_events(records, job_id=job, level=level,
                                        last=last)
            rendered = [diag.render(r, utc) for r in events]
            block = diag.engine_block(
                spec.get("pipeline_info") or {},
                spec.get("engine_states") or {})
            timeline = diag.job_timeline(records, job, utc=utc) \
                if job else []
        except Exception as e:
            self._publish_locked("diagnostics", req,
                                 error=type(e).__name__, loading=False)
            return
        self._publish_locked(
            "diagnostics", req, error=None, loading=False,
            data={"events": rendered, "records": events, "engine": block,
                  "count": len(events), "timeline": timeline,
                  "skipped_lines": stats.get("skipped", 0),
                  "filters": {"job": job, "level": level, "utc": utc,
                              "last": last},
                  "loaded_at_utc": ids.now_utc_iso()})

    # ---- Home / Settings -----------------------------------------------------

    def _load_home(self, req):
        try:
            summary = self.history_service.home_summary()
            engine = {}
            recovery = {}
            if self.coordinator is not None:
                engine = self.coordinator.hubEngineStates()
                recovery = self.coordinator.hubRecoveryInfo()
        except Exception as e:
            self._publish_locked("home", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("home", req, error=None, loading=False,
                             data={"summary": summary, "engine": engine,
                                   "recovery": recovery})

    def _load_settings(self, req):
        data = {}
        try:
            if self.coordinator is not None:
                data = {
                    "collection_state": self.coordinator.collection_state(),
                    "retention": dict(getattr(
                        self.coordinator, "hubRetentionDays",
                        lambda: {})()),
                    # M13: the usage-analytics block (retention knob +
                    # reporting zone) — present when the coordinator
                    # exposes the command, absent under a stubbed harness.
                    "usage": (self.coordinator.hubUsageInfo()
                              if hasattr(self.coordinator,
                                         "hubUsageInfo") else None),
                }
        except Exception as e:
            self._publish_locked("settings", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("settings", req, error=None, loading=False,
                             data=data)

    # ---- query plumbing -------------------------------------------------------

    def reload_current(self, detail_only=False):
        view = self.selected_view
        if view == "home":
            self._spawn(("home", "list"), self._load_home)
        elif view == "history":
            if detail_only:
                self._spawn_history_detail()
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
        elif view == "insights":
            self.reload_insights()
        elif view == "diagnostics":
            self._spawn_diagnostics()
        elif view == "models":
            if detail_only:
                ex = self.views["models"].get("selected_id")
                if ex is not None:
                    self._spawn(("models", "detail"),
                                self._load_training_detail, example_id=ex)
            elif self.views["models"]["subview"] == "training":
                self.reload_training()
            else:
                self._spawn(("models", "list"), self._load_models_engines)
        elif view == "settings":
            self._spawn(("settings", "list"), self._load_settings)

    def _load_models_engines(self, req):
        from .. import diagnostics as diag
        spec = self.diagnostics_provider() or {}
        try:
            block = diag.engine_block(
                spec.get("pipeline_info") or {},
                spec.get("engine_states") or {})
        except Exception as e:
            self._publish_locked("models", req, error=type(e).__name__,
                                 loading=False)
            return
        self._publish_locked("models", req, error=None, loading=False,
                             data={"engine": block})

    def _spawn(self, key, fn, **inputs):
        """Admit one load for ``key``; it supersedes any not-yet-started
        request for the same key and every older one's publication."""
        view, part = key
        with self._lock:
            if self._closed:
                return None
            self._admitted += 1
            req = _Request(key, self._admitted, fn, inputs)
            self._gens[key] = req.gen
            if part == "list":
                self.views[view]["loading"] = True
            else:
                self.views[view]["detail_loading"] = True
        self._executor.submit(req, self._before_run)
        return req

    def _before_run(self, req):
        with self._lock:
            req.epoch = self._epoch

    def _target_current(self, req) -> bool:
        view, part = req.key
        if part != "detail":
            return True
        v = self.views[view]
        if view == "history":
            return (v["selected_kind"], v["selected_id"]) == (
                req.inputs["kind"], req.inputs["row_id"])
        if view == "models":
            return v.get("selected_id") == req.inputs["example_id"]
        return True

    def wait_for_queries(self, timeout=10.0):
        """True once EVERY admitted request has run or been superseded
        before starting (a full drain, not the newest thread)."""
        return self._executor.wait_idle(timeout)

    def queries_idle(self) -> bool:
        return self._executor.idle()

    def query_stats(self) -> dict:
        return dict(self._executor.stats)

    # ---- revocation (delete-everywhere / retention) ----------------------

    def _fence(self, view, changes):
        """Remove revoked jobs' rows and detail from a publication."""
        revoked = self._revoked_jobs
        if not revoked:
            return changes
        out = dict(changes)
        if view in ("history", "models"):
            data = out.get("data")
            if data:
                out["data"] = (_drop_history_rows(data, revoked)
                               if view == "history"
                               else _drop_model_rows(data, revoked))
            detail = out.get("detail")
            if detail and detail.get("job_id") in revoked:
                out.update(detail=None, detail_key=None,
                           detail_error="deleted")
        return out

    def revoke_job(self, job_id):
        """Delete-everywhere reached this job (store listener, writer
        thread, inside the delete op): mark it revoked and scrub every
        cached row/detail that carries it. Pure data under the lock —
        no store call, no AppKit work; the shell clears rendered
        widgets on main via ``on_revoked``."""
        if not job_id:
            return
        with self._lock:
            self._revoked_jobs.add(job_id)
            self._epoch += 1
            for name in ("history", "models"):
                view = self.views[name]
                had = view.get("detail")
                scrub = self._fence(name, {"data": view.get("data"),
                                           "detail": had})
                view["data"] = scrub["data"]
                if had is not None and scrub["detail"] is None:
                    view.update(detail=None, detail_key=None,
                                detail_error="deleted", selected_id=None,
                                selected_kind=None)
                    if name == "models":
                        view["listened_for"] = None
            ins = self.views["insights"]
            if (ins.get("data") or {}).get("profile") is not None:
                # A cached profile may carry phrases from the deleted
                # evidence (the store invalidates the snapshot itself).
                ins["data"] = None
        self._publish()
        cb = self.on_revoked
        if cb is not None:
            try:
                cb(job_id)
            except Exception:
                pass

    def revalidate(self):
        """A retention pass may have purged payload: results computed
        before it are dropped and re-run, hidden views drop cached
        payload (reloaded when shown) and the visible view reloads."""
        with self._lock:
            self._epoch += 1
            for name in ("history", "models", "insights"):
                if name != self.selected_view:
                    self.views[name].update(data=None, detail=None,
                                            detail_key=None)
        self.reload_current()
        if self.selected_view in ("history", "models"):
            self.reload_current(detail_only=True)
        self._publish()

    # ---- publication ------------------------------------------------------------

    def _publish(self):
        if self._closed:
            return
        if self.on_update is not None:
            try:
                self.on_update(self)
            except Exception:
                pass

    def _publish_locked(self, view, req=None, after=None, **changes):
        """Guarded publication: under the lock, apply ``changes`` only if
        ``req`` is still the newest request for its key (and a detail
        request still names the selected item), fenced by revocation.
        A request that raced a revocation is dropped and re-admitted.
        Observers are notified after the lock is released. Returns
        whether the changes were applied."""
        readmit = False
        with self._lock:
            if self._closed:
                return False
            if req is not None:
                if self._gens.get(req.key) != req.gen:
                    return False
                if req.epoch is not None and req.epoch != self._epoch:
                    readmit = True
                elif not self._target_current(req):
                    return False
            if not readmit:
                self.views[view].update(self._fence(view, changes))
                if after is not None:
                    after(self.views[view])
        if readmit:
            self._spawn(req.key, req.fn, **req.inputs)
            return False
        self._publish()
        return True
