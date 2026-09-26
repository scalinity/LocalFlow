"""Synthetic world for the M10 remediation suite, corpus runner and
mutation check (2026-09-26 read-only audit at 9344fa1).

Everything here is synthetic: temporary stores, temporary manifest and
workspace trees whose allowed and forbidden roots are sibling
directories of one fresh temporary root, scripted supervisors and a
scripted context collector. Nothing reads the real home folder, a real
workspace, the live clipboard or the frontmost application.

The coordinator is the REAL ``AppDelegate`` driven through the shared
profiles-pipeline ``Harness`` (real worker loop, stubbed insertion).
Ordering is decided by holds and events at named seams, never by sleeps.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
for p in (ROOT, HERE.parent, HERE.parents[1] / "ui",
          HERE.parents[1] / "lifecycle"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import localflow.app as app_mod  # noqa: E402
from localflow.v2 import snippets as snip_mod  # noqa: E402
from localflow.v2.developer import skills as skills_mod  # noqa: E402

from test_profiles_pipeline import (  # noqa: E402,F401
    CFG, FakeContextCollector, Harness, M10Supervisor, latest_envelope,
    make_mode_item)
from m09_world import MainQueue, code_stamp  # noqa: E402,F401

# Synthetic canaries: data strings only, never executed.
BODY_CANARY = "BODY_CANARY_MUST_NOT_EXECUTE"
OUTSIDE_CANARY = "outside-canary"
PRIVATE_CANARY = "SYNTHETIC_PRIVATE_CANARY"


# ---- files -----------------------------------------------------------------

def write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def skill_md(name=None, aliases=(), body="synthetic body\n") -> str:
    lines = ["---"]
    if name is not None:
        lines.append(f"name: {name}")
    if aliases:
        lines.append("aliases: " + ", ".join(aliases))
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def json_manifest(skills) -> str:
    return json.dumps({"skills": list(skills)})


def replace_keep_mtime(path: pathlib.Path, text: str):
    """Rewrite ``path`` in place and restore its previous mtime (the
    adversarial same-mtime replacement; ctime still moves — the kernel
    sets it on every write and on utime itself)."""
    st = os.stat(path)
    with open(path, "r+", encoding="utf-8") as f:
        f.seek(0)
        f.write(text)
        f.truncate()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))


class FixtureRoot:
    """One fresh temporary root; ``allowed`` and ``outside`` are sibling
    synthetic directories under it (never a real private directory)."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lf-m10-")
        self.root = pathlib.Path(self._tmp.name).resolve()
        self.allowed = self.root / "allowed"
        self.outside = self.root / "outside"
        self.allowed.mkdir()
        self.outside.mkdir()

    def close(self):
        self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---- read log (sys.audit "open" events; installed once) --------------------

class _OpenLog:
    def __init__(self):
        self.active = None
        self._installed = False

    def install(self):
        if self._installed:
            return

        def hook(event, args):
            log = self.active
            if log is None or event != "open":
                return
            path = args[0] if args else None
            if isinstance(path, (bytes, bytearray)):
                path = os.fsdecode(path)
            if isinstance(path, str):
                log.append(path)
        sys.addaudithook(hook)
        self._installed = True

    @contextlib.contextmanager
    def record(self):
        self.install()
        log = []
        self.active = log
        try:
            yield log
        finally:
            self.active = None


OPEN_LOG = _OpenLog()


def resolved_opens_under(log, root: pathlib.Path):
    """Opened paths (absolute ones; an fd-relative open names one
    component only) whose real path lies under ``root``."""
    root = os.path.realpath(root)
    out = []
    for p in log:
        if not os.path.isabs(p):
            continue
        rp = os.path.realpath(p)
        if rp == root or rp.startswith(root + os.sep):
            out.append(p)
    return out


# ---- store seams -----------------------------------------------------------

class WriterHold:
    """Block the store's single writer with a queued op until released
    (the op is admitted first, so everything submitted afterwards queues
    behind it in FIFO order)."""

    def __init__(self, store):
        self.store = store
        self.entered = threading.Event()
        self._go = threading.Event()

        def op():
            self.entered.set()
            self._go.wait(30)
        store._submit(op, wait=False)
        assert self.entered.wait(10), "writer hold never ran"

    def release(self):
        self._go.set()


def queued(store) -> int:
    with store._cond:
        return len(store._queue)


def wait_queued(store, n, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if queued(store) >= n:
            return True
        time.sleep(0.002)
    return False


@contextlib.contextmanager
def short_submit_timeout(store, seconds=0.2):
    """The M10 stores call ``store.submit(op)`` with the default 15 s
    caller wait; shorten it so an admitted op can outlive its caller in
    a test (the op itself is never cancelled — Store contract)."""
    real = store.submit

    def submit(fn, wait=True, timeout=15.0):
        return real(fn, wait=wait, timeout=min(timeout, seconds))
    store.submit = submit
    try:
        yield
    finally:
        store.submit = real


def raw_rows(store, table, key):
    cols = {"style_rules": "rule_id, name, scope_kind, scope_value, mode,"
                           " number_policy, profile_name, enabled, revision",
            "snippets": "snippet_id, trigger, name, kind, content,"
                        " allow_rewrite, enabled, revision",
            "transforms": "transform_id, auto_apply, enabled, revision"}
    return store.submit(lambda db: db.execute(
        f"SELECT {cols[table]} FROM {table} ORDER BY {key}").fetchall())


def meta_counter(store, key):
    row = store.submit(lambda db: db.execute(
        "SELECT value FROM profiles_meta WHERE key=?", (key,)).fetchone())
    return int(row[0]) if row else 0


# ---- coordinator driving ---------------------------------------------------

def run_job(h, asr_text):
    """One real dictation through the real coordinator: (text, job)."""
    h.d.supervisor.asr_text = asr_text
    h.press_release()
    _fn, args = h.run_coordinator()
    return args


def harness(*, bundle="com.example.editor", category="editor", origin=None,
            workspace=None, document_url=None, asr="ok", durations=4,
            cfg=None):
    sup = M10Supervisor(asr)
    ctx = FakeContextCollector(bundle, category, origin=origin,
                               workspace=workspace,
                               document_url=document_url)
    h = Harness([1.0] * durations, supervisor=sup, context=ctx, cfg=cfg)
    return h, sup, ctx


class HookedCollector(FakeContextCollector):
    """The scripted collector with a hook that runs inside finalize (the
    release-time boundary) — a named seam for mid-flight edits."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.on_finalize = None

    def finalize(self, *, coll=None, job_id, target_snapshot_id=None):
        if self.on_finalize is not None:
            self.on_finalize()
        return super().finalize(coll=coll, job_id=job_id,
                                target_snapshot_id=target_snapshot_id)


def hooked_harness(*, bundle="com.example.editor", category="editor",
                   origin=None, workspace=None, document_url=None, asr="ok",
                   durations=4, cfg=None):
    sup = M10Supervisor(asr)
    ctx = HookedCollector(bundle, category, origin=origin,
                          workspace=workspace, document_url=document_url)
    h = Harness([1.0] * durations, supervisor=sup, context=ctx, cfg=cfg)
    return h, sup, ctx


def set_manifests(h, paths):
    """Point the app at synthetic manifest paths (the tests' established
    seam: the configured tuple plus a cold cache)."""
    h.d._skill_manifest_paths = tuple(str(p) for p in paths)
    h.d._skill_cache_key = None


def snippet(sid="snip:alpha", trigger="quick reply", content="ACK", **kw):
    return snip_mod.Snippet(snippet_id=sid, trigger=trigger,
                            name=kw.pop("name", "Synthetic reply"),
                            content=content, **kw)


def discover_names(paths):
    return sorted(r.name for r in skills_mod.discover(list(paths)))


def all_artifacts(store, job_id):
    return store.submit(lambda db: db.execute(
        "SELECT artifact_id, role, kind, content_text, meta_json"
        " FROM artifacts WHERE job_id=? ORDER BY created_at_utc",
        (job_id,)).fetchall())


def app_events(h):
    """Every event line the coordinator wrote so far (content check)."""
    h.d.v2log.flush() if hasattr(h.d.v2log, "flush") else None
    out = []
    for p in sorted(pathlib.Path(app_mod.V2_EVENTS_DIR).glob("*.jsonl")):
        out.extend(p.read_text(encoding="utf-8").splitlines())
    return out
