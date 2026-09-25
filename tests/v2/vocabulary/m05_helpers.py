"""Shared synthetic fixtures for the M05 remediation regression suites.

Everything here drives PRODUCTION code: the real ``VocabularyStore`` over
a temporary ``Store``, the real engine, and — for app seams — the real
``AppDelegate`` under the DECLARED non-native shims of
tests/v2/lifecycle/native_shims.py with a scripted M06 context service
and a scripted supervisor. Concurrency is serialized with an explicit
turnstile over ``Store.submit`` (a scripted order per thread), never
with sleeps. All terms are synthetic.
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "v2" / "lifecycle"))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import vocabulary as V  # noqa: E402
from localflow.v2 import vocabulary_store as VS  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)


def ent(eid, canonical, aliases=(), **kw):
    kw.setdefault("approved", True)
    kw.setdefault("verification", "explicit" if kw["approved"]
                  else "suggested")
    return V.VocabularyEntry(
        entry_id=eid, canonical=canonical,
        aliases=tuple(a if isinstance(a, V.Alias) else V.Alias(a)
                      for a in aliases), **kw)


def run(text, entries, scope=None, policy=None, snapshot=None):
    snap = snapshot or V.VocabularySnapshot(entries, scope)
    return normalize(text, policy or NormalizationPolicy(),
                     ContextSnapshot(vocabulary=snap))


def vocab_edits(res):
    return [(e.input_text, e.output_text, e.rule_id)
            for e in res.edits if e.cls == "vocabulary"]


class TempStore:
    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self._td.name) / "v2.db"
        self.events = []

        def emit(n, **kw):
            self.events.append({"event": n, **kw})
        self.store = store_mod.Store(self.path, emit=emit)
        self.vs = VS.VocabularyStore(self.store)

    @property
    def dir(self):
        return pathlib.Path(self._td.name)

    def sql(self, q, args=()):
        self.store.sync()
        con = sqlite3.connect(self.path)
        try:
            return con.execute(q, args).fetchall()
        finally:
            con.close()

    def close(self):
        try:
            self.store.close()
        finally:
            self._td.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Turnstile:
    """Deterministic interleaving of writer admission: a participating
    thread may call ``Store.submit`` only when the script's head names
    it; a finished thread's remaining turns are skipped. ``timeouts``
    counts liveness guards that fired (asserted zero by the tests)."""

    def __init__(self, store, script):
        self.store = store
        self.real = store.submit
        self.script = list(script)
        self.cond = threading.Condition()
        self.done = set()
        self.participants = set(script)
        self.timeouts = 0
        store.submit = self.submit

    def submit(self, fn, *a, **kw):
        name = threading.current_thread().name
        if name not in self.participants:
            return self.real(fn, *a, **kw)
        with self.cond:
            while True:
                while self.script and self.script[0] in self.done:
                    self.script.pop(0)
                if not self.script or self.script[0] == name:
                    break
                if not self.cond.wait(10):
                    self.timeouts += 1
                    break
        try:
            return self.real(fn, *a, **kw)
        finally:
            with self.cond:
                if self.script and self.script[0] == name:
                    self.script.pop(0)
                self.cond.notify_all()

    def finished(self, name):
        with self.cond:
            self.done.add(name)
            self.cond.notify_all()

    def restore(self):
        self.store.submit = self.real


def race(store, script, fns):
    """Run name→callable threads under a turnstile; returns
    (name→("ok", value) | ("error", type, message), turnstile)."""
    ts = Turnstile(store, script)
    out = {}

    def wrap(name, fn):
        try:
            out[name] = ("ok", fn())
        except Exception as e:
            out[name] = ("error", type(e).__name__, str(e))
        finally:
            ts.finished(name)
    threads = [threading.Thread(target=wrap, args=(n, f), name=n)
               for n, f in fns.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    ts.restore()
    return out, ts


# ---------------------------------------------------------------------------
# App seams (declared shims)
# ---------------------------------------------------------------------------

def helpers():
    import m03_helpers as h  # noqa: E402  (installs the declared shims)
    return h


class FakeContext:
    """Scripted M06 context service returning real snapshot objects."""

    def __init__(self):
        self.identity = None
        self.final = None
        self.on_finalize = None

    def capture_identity(self):
        return self.identity

    def begin(self, identity):
        return object()

    def abandon(self):
        pass

    def finalize(self, job_id=None, target_snapshot_id=None, **kw):
        if self.on_finalize is not None:
            self.on_finalize()
        return self.final


def target(bundle, category="editor"):
    from localflow.v2 import ids
    from localflow.v2.context import snapshot as csnap
    return csnap.TargetSnapshot(target_snapshot_id=ids.new_id("tgt"),
                                app_bundle=bundle, app_name=bundle,
                                category=category)


def final(tgt, workspace=None, site=None):
    from localflow.v2 import ids
    from localflow.v2.context import snapshot as csnap
    return csnap.ContextSnapshot(
        context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
        target=tgt, workspace=workspace, site_origin=site)


class AppRun:
    """The real AppDelegate on temp roots: hotkey-down identity →
    release/finalize → coordinator → cleanup (recorded)."""

    def __init__(self, text, cfg=None):
        h = helpers()
        self.h = h
        self._td = tempfile.TemporaryDirectory()
        self.a = h.App(self._td.name, cfg=cfg, start_coordinator=False)
        self.d = self.a.d
        self.fc = FakeContext()
        self.d._context = self.fc
        self.events = []
        real_emit = self.d.v2log.emit

        def emit(name, **kw):
            self.events.append({"event": name, **kw})
            return real_emit(name, **kw)
        self.d.v2log.emit = emit
        outer = self

        class Sup(h.GateSup):
            def transcribe(self, **kw):
                if outer.on_transcribe is not None:
                    outer.on_transcribe()
                return super().transcribe(**kw)

            def clean(self, **kw):
                outer.clean_kwargs.append(kw)
                return super().clean(**kw)
        self.on_transcribe = None
        self.clean_kwargs = []
        self.sup = Sup(text=text)
        self.a.set_sup(self.sup)
        self.a.start_coordinator()

    def job(self, bundle, workspace=None, site=None, category="editor"):
        h = self.h
        self.fc.identity = target(bundle, category) if bundle else None
        self.fc.final = final(self.fc.identity, workspace, site) \
            if bundle else None
        h.AppHelper.calls.clear()
        n = len(self.clean_kwargs)
        self.a.dictate(blocks=10)
        ok = self.a.wait_call("_finishWithText_", 20)
        text, job = None, None
        for fn, args in list(h.AppHelper.calls):
            if getattr(fn, "__name__", "") == "_finishWithText_":
                text, job = args[0], args[1]
        self.a.drain()
        kw = self.clean_kwargs[n] if len(self.clean_kwargs) > n else {}
        return {"finished": ok, "text": text, "job": job,
                "pairs": [tuple(p) for p in
                          (kw.get("vocabulary_pairs") or [])],
                "relevant": list(kw.get("relevant_vocabulary") or [])}

    def close(self):
        try:
            self.a.close()
        finally:
            self._td.cleanup()


class Field:
    """Recorded stand-in for an AppKit text field / popup."""

    def __init__(self, v=""):
        self.v = v

    def stringValue(self):
        return self.v

    def setStringValue_(self, v):
        self.v = v

    def titleOfSelectedItem(self):
        return self.v or "global"


def panel(vs):
    helpers()
    from localflow.v2 import dictionary_panel as dp
    ctl = dp.DictionaryPanelController.alloc().initWithVocabularyStore_(vs)
    for name in ("search", "phrase", "sandbox", "listing", "canonical",
                 "alias", "scope_value"):
        setattr(ctl, name, Field())
    ctl.scope_popup = Field("global")
    ctl.refresh()
    return ctl
