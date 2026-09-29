"""CompanionController — the desktop companion (Spec S19 surface, M09
architecture contract) as a WKWebView view over the same state, query
services and coordinator commands as the AppKit Hub.

Division of labour:

- ``CompanionState`` (HubState) owns every read: admission, generations,
  supersession, guarded publication, revocation and revalidation.
- This controller owns what the AppKit ``HubController`` owned: the
  window (through ``CompanionHost``), the binding of actions to what the
  page RENDERED, operation ids, background actions and their notes — and
  the one bridge through which the page asks for anything.
- The page (Svelte, ``frontend/``) renders read models and sends
  allowlisted commands. It never sees a store, a path or a method name.

Publication: ``HubState.on_update`` fires on query/writer threads; the
controller coalesces those into one main-thread flush that rebuilds each
view's UI-safe read model and pushes the ones that changed. Every view is
considered, not only the visible one, so a revocation or retention pass
also scrubs what the page still holds for hidden views.

Rendered binding: a pushed detail carries a token. An action names the
token it rendered; the controller resolves it to the detail object the
state still holds for the selected item, or refuses as ``stale`` — the
M09-AUDIT-01 rule (never act on a detail other than the one on screen).
"""

from __future__ import annotations

import json
import os
import pathlib
import threading

from PyObjCTools import AppHelper

from . import bridge as B
from .bridge import Bridge, Bool, Enum, Str
from .host import THEMES, CompanionHost
from .state import CompanionState, VIEWS

ROUTES = tuple(v for v in VIEWS)  # every view the page may select


class Prefs:
    """The companion's own small UI preferences (theme, sidebar, which
    introductions were dismissed). A separate file beside config.json:
    no config key changes meaning."""

    DEFAULTS = {"theme": "system", "sidebar_collapsed": False,
                "dismissed": [], "onboarding_seen": False}

    def __init__(self, path):
        self.path = pathlib.Path(path) if path else None
        self.values = dict(self.DEFAULTS)
        if self.path is not None and self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            if isinstance(raw, dict):
                self._merge(raw)

    def _merge(self, raw):
        if raw.get("theme") in THEMES:
            self.values["theme"] = raw["theme"]
        if isinstance(raw.get("sidebar_collapsed"), bool):
            self.values["sidebar_collapsed"] = raw["sidebar_collapsed"]
        if isinstance(raw.get("onboarding_seen"), bool):
            self.values["onboarding_seen"] = raw["onboarding_seen"]
        d = raw.get("dismissed")
        if isinstance(d, list):
            self.values["dismissed"] = [x for x in d
                                        if isinstance(x, str)][:32]

    def set(self, **changes) -> bool:
        """Apply and persist; False when the file could not be written
        (the change still applies for this run)."""
        self._merge({**self.values, **changes})
        if self.path is None:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.values, indent=1),
                           encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False


def default_prefs_path():
    from .... import config as config_mod  # localflow.config
    return config_mod.user_override_path().parent / "companion.json"


class CompanionController:
    """One per process (Open Hub… focuses the existing window). Closing
    hides; explicit Quit is the only exit (M09-AC04)."""

    def __init__(self, spec):
        self.spec = spec
        self.coordinator = spec.get("coordinator")
        self.replay = spec.get("replay")
        self.state = CompanionState(
            spec["history_service"],
            vocabulary_store=spec.get("vocabulary_store"),
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
        self.prefs = Prefs(spec["prefs_path"] if "prefs_path" in spec
                           else default_prefs_path())
        self.bridge = Bridge(on_error=self._command_failed)
        self.notes = {}  # surface -> {tone, code, detail}: lasting notes
        self.csp_violations = 0
        self._tokens = {}  # view -> (detail object, token)
        self._token_seq = 0
        self._seq = 0
        self._pushed = {}  # view -> last pushed JSON
        self._flush_lock = threading.Lock()
        self._flush_posted = False
        self._engine_recheck = False
        self.usage_reconciled_hooks = []
        self.pre_flush_hooks = []  # main thread, before read models build
        self.paste_again_ended = lambda outcome: None
        self._register()
        self.state.on_update = self._state_updated
        self.state.on_revoked = self._state_revoked
        self.state.on_revalidated = self._state_revalidated
        store = spec.get("store")
        if store is not None and hasattr(store, "add_job_deletion_listener"):
            store.add_job_deletion_listener(self._store_job_deleted)
        self.host = spec.get("host_factory", CompanionHost)(
            self, theme=self.prefs.values["theme"])

    # ---- coordinator-facing surface (the AppKit Hub's names) ---------------

    @property
    def window(self):
        return self.host.window

    def showWindow_(self, sender):
        """Focus the existing window (single instance). The coordinator
        defers this call while an insertion is in flight."""
        self.host.show()
        self.state.show()


    def pasteAgainEnded(self, outcome):
        """Paste Again's pick finished (the coordinator's report, main
        thread): History keeps the outcome as its note."""
        self.paste_again_ended(outcome)

    def usage_outcome_reconciled(self, result):
        """Main thread: an outcome-unknown usage deletion finished; the
        surface that said 'not known yet' now says what happened."""
        for hook in list(self.usage_reconciled_hooks):
            try:
                hook(result)
            except Exception:
                pass

    # Scratchpad dictation target (M12) — replaced by the Scratchpad
    # surface when it registers; until then no note editor is active, so
    # dictation falls through to normal insertion.
    def scratchpad_editor_active(self):
        return False

    def scratchpad_capture_target(self):
        return None

    def scratchpad_receive(self, text, job):
        job["note_refusal"] = "note_closed_during_dictation"
        return None

    def scratchpad_apply_transform(self, result, capture):
        return None, "note_not_open"

    def scratchpad_shutdown(self, timeout=3.0):
        return {"drained": True, "unsaved": []}

    def scratchpad_note_created(self, note_id):
        self.state.reload_scratchpad()

    def scratchpad_quick_open(self):
        self.state.select_view("scratchpad")
        self.emit("shell.route", {"view": "scratchpad"})

    def show_route(self, view):
        """Bring a route forward (the menu's Dictionary… item)."""
        self.state.select_view(view)
        self.emit("shell.route", {"view": view})
    # ---- host client ---------------------------------------------------------

    def on_message(self, raw):
        return json.dumps(self.bridge.handle(raw), ensure_ascii=False)

    def on_page_loaded(self):
        # A (re)loaded page holds nothing: everything is pushed again.
        self._pushed.clear()
        self.request_flush()

    def on_close(self):
        self.state.close()

    def on_toolbar(self, name):
        if name == "sidebar":
            self.prefs.set(
                sidebar_collapsed=not self.prefs.values["sidebar_collapsed"])
            self.request_flush()
        elif name == "utility":
            self.emit("shell.utility", {})

    def on_key_changed(self, key):
        pass

    def on_appearance_changed(self):
        self.request_flush()

    # ---- publication -----------------------------------------------------------

    def _state_updated(self, state):
        self.request_flush()

    def request_flush(self):
        """Coalesce publications from any thread into one main-thread
        flush."""
        with self._flush_lock:
            if self._flush_posted:
                return
            self._flush_posted = True
        AppHelper.callAfter(self._flush)

    def _flush(self):
        with self._flush_lock:
            self._flush_posted = False
        if not getattr(self.host, "_loaded", False):
            return
        from . import readmodels
        for hook in list(self.pre_flush_hooks):
            try:
                hook()
            except Exception as e:
                self._command_failed("pre_flush", type(e).__name__)
        shell = self.shell_model()
        for view in VIEWS:
            try:
                model = readmodels.build(self, view)
            except Exception as e:  # a read model must never stop the pump
                self._command_failed(f"read:{view}", type(e).__name__)
                continue
            text = B.dumps({"shell": shell, "data": model})
            if self._pushed.get(view) == text:
                continue
            self._pushed[view] = text
            self._seq += 1
            self.host.push(B.dumps({
                "bridge_version": B.BRIDGE_VERSION, "type": "snapshot",
                "seq": self._seq, "view": view, "shell": shell,
                "data": model}))
        self._schedule_engine_recheck(shell)

    def _schedule_engine_recheck(self, shell):
        """While the window is shown and a model is still loading, look
        again in two seconds — a bounded wait for readiness that stops by
        itself, not a polling loop."""
        engine = shell.get("engine") or {}
        waiting = any(engine.get(k) in ("not_started", "loading", "warming")
                      for k in ("asr", "cleanup"))
        if not waiting or self._engine_recheck or not self.state.visible:
            return
        self._engine_recheck = True

        def again():
            self._engine_recheck = False
            self._pushed.pop("home", None)
            self.request_flush()
        AppHelper.callLater(2.0, again)

    def emit(self, name, payload):
        """A named event to the page (e.g. a Paste Again pick ended)."""
        self._seq += 1
        self.host.push(B.dumps({"bridge_version": B.BRIDGE_VERSION,
                                "type": "event", "seq": self._seq,
                                "name": name, "payload": payload}))

    def shell_model(self):
        engine = {}
        if self.coordinator is not None:
            try:
                engine = dict(self.coordinator.hubEngineStates())
            except Exception:
                engine = {}
        cfg = self._config_summary()
        return {"view": self.state.selected_view,
                "theme": self.prefs.values["theme"],
                "is_dark": self.host.is_dark()
                if hasattr(self.host, "is_dark") else False,
                "sidebar_collapsed": self.prefs.values["sidebar_collapsed"],
                "engine": {"asr": engine.get("asr"),
                           "cleanup": engine.get("cleanup")},
                "dictation_key": cfg.get("hotkey"),
                "version": self._version(),
                "dismissed": list(self.prefs.values["dismissed"]),
                "onboarding_seen": self.prefs.values["onboarding_seen"],
                "name": self._display_name()}

    def _config_summary(self):
        coord = self.coordinator
        if coord is None or not hasattr(coord, "hubConfigSummary"):
            return {}
        try:
            return dict(coord.hubConfigSummary() or {})
        except Exception:
            return {}

    def _display_name(self):
        """The greeting's first name: the macOS account's full name
        (local, never sent anywhere) unless the spec names one (the
        synthetic screenshot fixtures do)."""
        if "display_name" in self.spec:
            return self.spec["display_name"]
        try:
            from Foundation import NSFullUserName
            full = str(NSFullUserName() or "").strip()
        except Exception:
            full = ""
        return full.split()[0] if full else None

    _VERSION = ...

    def _version(self):
        if self._VERSION is ...:
            version = None
            try:
                from Foundation import NSBundle
                info = NSBundle.mainBundle().infoDictionary() or {}
                if info.get("CFBundleIdentifier") == "com.danny.localflow":
                    version = str(info.get("CFBundleShortVersionString"))
            except Exception:
                version = None
            CompanionController._VERSION = version
        return self._VERSION

    # ---- rendered binding ---------------------------------------------------------

    def token_for(self, view, detail):
        """The token a pushed detail carries (stable while the state holds
        the same detail object)."""
        if detail is None:
            return None
        cur = self._tokens.get(view)
        if cur is not None and cur[0] is detail:
            return cur[1]
        self._token_seq += 1
        token = f"{view[:2]}{self._token_seq}"
        self._tokens[view] = (detail, token)
        return token

    def rendered(self, view, token):
        """The detail the page rendered under ``token`` — only while the
        state still holds that very object as the selected item's detail.
        Otherwise the action refuses as stale (loading, failed, deleted or
        replaced by a newer publication not yet on screen)."""
        cur = self._tokens.get(view)
        v = self.state.views[view]
        if cur is None or cur[1] != token or cur[0] is not v.get("detail"):
            B.stale("detail_not_current")
        return cur[0]

    def _forget_tokens(self, job_id=None):
        for view, (detail, _tok) in list(self._tokens.items()):
            if job_id is None or (isinstance(detail, dict)
                                  and detail.get("job_id") == job_id):
                del self._tokens[view]

    # ---- revocation ----------------------------------------------------------------

    def _store_job_deleted(self, job_id):
        """Store listener, inside the delete op on the writer thread:
        flag-only revocation of cached state and replay."""
        self.state.revoke_job(job_id)
        replay = self.replay
        if replay is not None and hasattr(replay, "revoke_job") \
                and replay.revoke_job(job_id):
            AppHelper.callAfter(replay.stop_revoked)

    def _state_revoked(self, job_id):
        AppHelper.callAfter(self._revoke_rendered, job_id)

    def _revoke_rendered(self, job_id):
        """Main thread: nothing the page can see or act on still carries
        the deleted job's text (its tokens no longer resolve; every view's
        read model is rebuilt and pushed)."""
        self._forget_tokens(job_id)
        for hook in self._revoke_hooks:
            try:
                hook(job_id)
            except Exception:
                pass
        if self.replay is not None and hasattr(self.replay, "stop_revoked"):
            self.replay.stop_revoked()
        self.request_flush()

    def _state_revalidated(self):
        AppHelper.callAfter(self._revalidate_rendered)

    def _revalidate_rendered(self):
        store = self.spec.get("store")
        if self.replay is not None and store is not None and \
                hasattr(self.replay, "stop_unavailable"):
            self.replay.stop_unavailable(store)
        self.request_flush()

    # ---- commands ---------------------------------------------------------------------

    def _command_failed(self, command, exc_type):
        log = getattr(self.coordinator, "v2log", None)
        if log is not None:
            try:
                log.emit("companion.command_failed", level="WARNING",
                         reason_code=exc_type)
            except Exception:
                pass

    def _register(self):
        br = self.bridge
        self._revoke_hooks = []

        @br.command("shell.hello")
        def hello(p):
            self._pushed.clear()
            self.request_flush()
            return {"shell": self.shell_model(), "commands": br.commands}

        @br.command("nav.select", {"view": Enum(ROUTES)})
        def select(p):
            self.state.select_view(p["view"])
            return {"view": p["view"]}

        @br.command("prefs.set_theme", {"theme": Enum(THEMES)})
        def set_theme(p):
            saved = self.prefs.set(theme=p["theme"])
            self.host.set_theme(p["theme"])
            self.request_flush()
            return {"theme": p["theme"], "saved": saved}

        @br.command("prefs.set_sidebar", {"collapsed": Bool()})
        def set_sidebar(p):
            self.prefs.set(sidebar_collapsed=p["collapsed"])
            self.request_flush()
            return {"collapsed": p["collapsed"]}

        @br.command("prefs.dismiss", {"id": Enum(
            ("hero.dictionary", "hero.snippets", "hero.transforms",
             "hero.scratchpad", "hero.styles"))})
        def dismiss(p):
            if p["id"] not in self.prefs.values["dismissed"]:
                self.prefs.set(dismissed=self.prefs.values["dismissed"]
                               + [p["id"]])
            self.request_flush()
            return {}

        @br.command("prefs.onboarding_seen", {"seen": Bool()})
        def onboarding(p):
            self.prefs.set(onboarding_seen=p["seen"])
            self.request_flush()
            return {}

        @br.command("system.csp_violation", {"directive": Str(max_len=60)})
        def csp(p):
            self.csp_violations += 1
            self._command_failed("csp", "csp_violation")
            return {}

        @br.command("app.quit")
        def quit_app(p):
            from AppKit import NSApp
            AppHelper.callAfter(NSApp.terminate_, None)
            return {}

        from . import surfaces
        surfaces.register_all(self)
