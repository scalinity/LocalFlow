"""CompanionState — HubState plus the two things the desktop companion
shows that the AppKit Hub never had: a Dictionary view (the M05
vocabulary store, previously a separate menu-bar panel) and a richer
Home (recent dictations, the usage summary and the Your Voice summary,
all from their real services).

Everything else — admission, generations, supersession, the guarded
publication, revocation and revalidation fences — is HubState's own
code, unchanged. A subclass keeps ``localflow.v2.ui.state`` byte-stable,
so the AppKit Hub, its suites and their mutation gates are untouched.
"""

from __future__ import annotations

from ..state import HubState, VIEWS as HUB_VIEWS

VIEWS = HUB_VIEWS + ("dictionary",)

HOME_RECENT_LIMIT = 24


class CompanionState(HubState):
    def __init__(self, history_service, vocabulary_store=None, **services):
        super().__init__(history_service, **services)
        self.vocabulary_store = vocabulary_store
        self.views["dictionary"] = self._blank_view("dictionary")

    # ---- views ------------------------------------------------------------

    def select_view(self, view):
        if view != "dictionary":
            return super().select_view(view)
        self.selected_view = view
        self.reload_current()
        self._publish()

    def reload_current(self, detail_only=False):
        if self.selected_view == "dictionary":
            self.reload_dictionary()
            return
        super().reload_current(detail_only)

    def revalidate(self):
        """A retention pass may have purged payload that a hidden Home
        (recent rows, the profile) or Dictionary still caches: drop it
        (reloaded when shown), then HubState's own revalidation."""
        with self._lock:
            for name in ("home", "dictionary"):
                if name != self.selected_view:
                    self.views[name].update(data=None)
        super().revalidate()

    # ---- Dictionary (M05 vocabulary) --------------------------------------

    def set_dictionary_search(self, text):
        self.views["dictionary"]["search"] = text or ""
        self.reload_dictionary()

    def reload_dictionary(self):
        view = self.views["dictionary"]
        self._spawn(("dictionary", "list"), self._load_dictionary,
                    text=(view.get("search") or "").strip())

    def _load_dictionary(self, req):
        store = self.vocabulary_store
        if store is None:
            self._publish_locked("dictionary", req,
                                 error="vocabulary_unavailable",
                                 loading=False)
            return
        try:
            entries = [e.to_json() for e in store.entries()]
        except Exception as e:
            self._publish_locked("dictionary", req, error=type(e).__name__,
                                 loading=False)
            return
        text = req.inputs["text"].casefold()
        if text:
            entries = [e for e in entries
                       if text in (e.get("canonical") or "").casefold()
                       or any(text in (a.get("alias") or "").casefold()
                              for a in e.get("aliases") or ())]
        self._publish_locked("dictionary", req, error=None, loading=False,
                             data={"entries": entries})

    # ---- Home ----------------------------------------------------------------

    def _load_home(self, req):
        """The AppKit Home's summary/engine/recovery, plus the recent
        dictations (the History query, limited), the usage summary for
        all time and the current Your Voice snapshot's state. Each part
        is read from its own service; a part whose service is absent or
        fails is reported as unavailable rather than invented."""
        try:
            summary = self.history_service.home_summary()
            engine, recovery = {}, {}
            if self.coordinator is not None:
                engine = self.coordinator.hubEngineStates()
                recovery = self.coordinator.hubRecoveryInfo()
        except Exception as e:
            self._publish_locked("home", req, error=type(e).__name__,
                                 loading=False)
            return
        data = {"summary": summary, "engine": engine, "recovery": recovery}
        try:
            data["recent"] = self.history_service.search(
                limit=HOME_RECENT_LIMIT)
        except Exception as e:
            data["recent_error"] = type(e).__name__
        if self.insights_service is not None:
            try:
                data["usage"] = self.insights_service.summary(days=None)
            except Exception as e:
                data["usage_error"] = type(e).__name__
        if self.profile_service is not None:
            try:
                data["profile"] = self.profile_service.current()
            except Exception as e:
                data["profile_error"] = type(e).__name__
        self._publish_locked("home", req, error=None, loading=False,
                             data=data)

    # ---- revocation --------------------------------------------------------

    def revoke_job(self, job_id):
        """HubState scrubs History/Models/Insights; the companion's Home
        shows recent rows and a profile, so its cached data goes too (it
        reloads when shown)."""
        if job_id:
            with self._lock:
                if self.views["home"].get("data") is not None:
                    self.views["home"]["data"] = None
        super().revoke_job(job_id)  # advances the epoch: in-flight Home
        # reads taken before the deletion are dropped and re-run
        if job_id and self.selected_view == "home":
            self.reload_current()
