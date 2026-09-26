#!/usr/bin/env python3
"""M08 insertion benchmark, schema 2: work-valid timings (M08 remediation).

Every timed sample must PROVE the work it claims before any speed
verdict (M08-AUDIT-20, corpus F25, benchmark mutants BMUT-01..06). The
independent witness is the synthetic world's own log
(``tests/v2/insertion/m08_world.py``: every content read, physical
effect and clipboard operation, recorded by the world — never inferred
from a result object), plus instance-level probes on the benchmark's
own service. Each sample uses unique field contents and unique payloads,
so pre-existing equality can never stand in for an insertion.

Cohorts (each reported with n, p50/p95/p99/max in ms and its clock):

- ``ui_*`` — the REAL AppDelegate entry points on the calling thread
  (``_finishWithText_``, Recovery ``pasteLastResultAgain_``, History
  ``hubPasteText``, ``undoLastInsertion_``) with a 200 ms delay injected
  into every Accessibility content read: the callback clock must exclude
  the delay, the worker clock must include it, and no Accessibility call
  may run on the calling thread. S24 budget (canonical): UI
  acknowledgment p95 <= 50 ms, "no model or disk work on UI callback".
- ``ax_transaction`` / ``clipboard_transaction`` — enqueue (the caller's
  cost), queue wait (enqueue -> worker start), worker execution, and
  inside it: target validation of the actual bound element (the real
  ``validate_target`` call inside the transaction, never a separate
  microbenchmark), the AX write, clipboard snapshot/publish/post,
  destination readback and restore. A quarter of the clipboard samples
  contend: a synthetic user copy lands right before the restore check,
  and the generation guard must leave it in place.
- ``clipboard_settle`` — a late target: consumption inside the settle
  bound (the readback clock includes the delay) and beyond it (the
  deliberate settle wait, ownership kept, the late paste still correct).
- ``observer_tick`` / ``observer_reanchor_tick`` / ``observer_stop`` —
  the FULL observer tick (field authority, classification, owned-range
  read), a tick that re-anchors after typing before the range, and the
  final tick that records an edit and closes. The tick cadence is
  compressed (10 ms sleeps instead of 500 ms) — the work per tick is
  unchanged. No primitive-read approximation is reported.
- ``undo`` / ``repaste_absent`` / ``repaste_present`` — target-bound undo
  and the queued reconcile-then-paste, measured on the queue thread.
- ``cold_process`` — separate processes (desktop-isolated), each one AX
  and one clipboard transaction after a cold import.
- ``native_ax`` / ``native_ax_cold`` (``--native``) — the real
  SystemInsertionHost (AXUIElement, boxed AXValue ranges) writing into an
  owned synthetic text view of a helper process reached by its pid (this
  script's ``--helper`` mode: off-screen, accessory policy, never
  activated); the helper's own AppKit state is the witness. No key event
  is posted and no pasteboard is used on this path. Proposed budget
  (NOT canonical): PROPOSED-M08-B1 p95 <= 150 ms for validation -> write
  -> readback — a share of S24's 0.75 s p50 end-to-end target for short
  dictations.

Exit codes: 0 work valid and every declared gate met; 1 work valid, a
gate failed; 2 WORK INVALID (a sample lacks its witness, a delay was not
conserved) — no speed verdict is given; 3 harness error.

Run (desktop-isolated; the native cohort is spawned natively and only
reaches its own helper):

    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/benchmark_m08.py <outdir> [--scale 1.0] [--native] \
        [--code-rev SHA --overlay PATH,...]

``--code-rev``/``--overlay`` record provenance when the benchmark runs in
a ``git archive`` copy (no .git): the archived SHA and any overlaid file.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
UI_DELAY = 0.2                 # injected into every AX content read (UI)
S24_UI_P95_MS = 50.0           # S24: UI acknowledgment / hotkey response
PROPOSED_NATIVE_P95_MS = 150.0  # PROPOSED-M08-B1 (not canonical)
TICK_SLEEP = 0.01              # compressed observer cadence
HOST_METHODS = ("frontmost", "focused_element", "focused_element_for",
                "element_pid", "window_of", "attribute",
                "focused_window_title", "is_settable", "set_attribute",
                "string_for_range", "number_of_characters", "is_trusted")
WORKER = "localflow-v2-insertion"


def perf():
    return time.perf_counter()


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, int(-(-len(xs) * p // 100)) - 1))
    return xs[k]


def summary(xs_ms):
    if not xs_ms:
        return {"n": 0}
    return {"n": len(xs_ms), "p50_ms": round(pct(xs_ms, 50), 3),
            "p95_ms": round(pct(xs_ms, 95), 3),
            "p99_ms": round(pct(xs_ms, 99), 3),
            "max_ms": round(max(xs_ms), 3)}


def token(i):
    return f"{i:03d}{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# The owned native helper (``--helper``): an AppKit text view of this
# process, off-screen, never activated; answers its OWN state on stdin.
# ---------------------------------------------------------------------------

def run_helper(spec):
    from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                        NSBackingStoreBuffered, NSMakeRect, NSTextView,
                        NSWindow)
    from PyObjCTools import AppHelper
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(-20000, -20000, 420, 140), 1, NSBackingStoreBuffered,
        False)
    win.setTitle_(spec.get("title", "LF-M08 benchmark helper"))
    tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 420, 140))
    tv.setString_(spec.get("text", ""))
    n = len(spec.get("text", "").encode("utf-16-le")) // 2
    tv.setSelectedRange_((n, 0))
    win.contentView().addSubview_(tv)
    win.makeFirstResponder_(tv)
    win.orderFrontRegardless()
    print(f"READY {os.getpid()}", flush=True)

    def on_main(fn):
        box, ev = {}, threading.Event()

        def run():
            try:
                box["v"] = fn()
            finally:
                ev.set()
        AppHelper.callAfter(run)
        ev.wait(5)
        return box.get("v")

    def serve():
        for line in sys.stdin:
            try:
                cmd = json.loads(line)
            except ValueError:
                continue
            if cmd.get("cmd") == "state":
                def st():
                    r = tv.selectedRange()
                    return {"text": str(tv.string()),
                            "sel": [int(r.location), int(r.length)]}
                out = on_main(st)
            elif cmd.get("cmd") == "set":
                def put():
                    tv.setString_(cmd["text"])
                    loc, ln = cmd["sel"]
                    tv.setSelectedRange_((int(loc), int(ln)))
                    return {"ok": True}
                out = on_main(put)
            else:
                out = {"error": "unknown"}
            print(json.dumps(out), flush=True)
        AppHelper.callAfter(app.terminate_, None)

    threading.Thread(target=serve, daemon=True).start()
    threading.Timer(300.0, lambda: os._exit(0)).start()
    AppHelper.runEventLoop()


# ---------------------------------------------------------------------------
# Probes: instance-level instrumentation of the benchmark's own service.
# ---------------------------------------------------------------------------

class Sample:
    def __init__(self, key, kind):
        self.key = key
        self.kind = kind
        self.done = threading.Event()
        self.result = None
        self.t = {}           # named perf timestamps
        self.d = {}           # named durations (ms)
        self.info = {}        # witnesses gathered by probes
        self.problems = []

    def ms(self, name, a, b):
        self.d[name] = round((b - a) * 1000.0, 4)


class Probe:
    """Wraps the service's own seams on THIS instance (the production
    code is unchanged) and binds worker-side timings to the sample that
    is executing on the queue thread."""

    def __init__(self, svc, service_mod, clipboard_mod, host=None, kb=None):
        self.svc = svc
        self.by_key = {}
        self.tl = threading.local()
        self._restore = []
        self.contend = None     # callable(sample) run before a restore
        s = self

        real_run = svc._run_insert

        def run_insert(op_id, text, job, on_obs, **kw):
            smp = s.by_key.get(job.get("job_id") or text)
            prev = getattr(s.tl, "cur", None)
            s.tl.cur = smp
            t0 = perf()
            if smp is not None:
                smp.t["worker_start"] = t0
                smp.info["worker_thread"] = threading.current_thread().name
                smp.info["op_id"] = op_id
            try:
                return real_run(op_id, text, job, on_obs, **kw)
            finally:
                if smp is not None:
                    smp.t["worker_end"] = perf()
                s.tl.cur = prev
        svc._run_insert = run_insert

        real_validate = service_mod.validate_target

        def validate(host_, snapshot, job, **kw):
            t0 = perf()
            out = real_validate(host_, snapshot, job, **kw)
            smp = getattr(s.tl, "cur", None)
            if smp is not None:
                smp.ms("validation", t0, perf())
                lease = out[0]
                smp.info["validation"] = {
                    "lease": lease is not None,
                    "element": repr(getattr(lease, "element", None)),
                    "owner_pid": getattr(lease, "owner_pid", None),
                    "read_allowed": getattr(lease, "read_allowed", None)}
            return out
        service_mod.validate_target = validate
        self._restore.append((service_mod, "validate_target", real_validate))

        for name, label in (("_pre_state", "pre_read"),
                            ("_await_readback", "readback"),
                            ("_classify", None), ("_undo_now", "undo_exec"),
                            ("_repaste_now", "repaste_exec")):
            real = getattr(svc, name)

            def wrap(*a, _real=real, _label=label, _name=name, **kw):
                t0 = perf()
                try:
                    return _real(*a, **kw)
                finally:
                    smp = getattr(s.tl, "cur", None)
                    if _name == "_classify" and smp is not None:
                        smp.info.setdefault("classify_calls", 0)
                        smp.info["classify_calls"] += 1
                        smp.d["classify"] = round(
                            smp.d.get("classify", 0.0)
                            + (perf() - t0) * 1000.0, 4)
                    elif _name in ("_undo_now",):
                        s.last_undo_ms = (perf() - t0) * 1000.0
                        s.last_undo_thread = threading.current_thread().name
                    elif _name == "_repaste_now":
                        s.last_repaste = ((perf() - t0) * 1000.0,
                                          threading.current_thread().name,
                                          a[1] if len(a) > 1 else None)
                    elif smp is not None and _label:
                        smp.ms(_label, t0, perf())
            setattr(svc, name, wrap)

        base = clipboard_mod.ClipboardTransaction
        probe = self

        class TimedTxn(base):
            def capture(self_):
                t0 = perf()
                try:
                    return super().capture()
                finally:
                    probe._cur_ms("clip_snapshot", t0)

            def publish(self_, text):
                t0 = perf()
                try:
                    return super().publish(text)
                finally:
                    probe._cur_ms("clip_publish", t0)

            def restore_if_owned(self_):
                smp = getattr(probe.tl, "cur", None)
                if probe.contend is not None and smp is not None:
                    probe.contend(smp)
                t0 = perf()
                try:
                    return super().restore_if_owned()
                finally:
                    probe._cur_ms("clip_restore", t0)
        service_mod.ClipboardTransaction = TimedTxn
        self._restore.append((service_mod, "ClipboardTransaction", base))

        if kb is not None:
            real_post = kb.post_paste

            def post():
                t0 = perf()
                try:
                    return real_post()
                finally:
                    probe._cur_ms("clip_post", t0)
                    smp = getattr(probe.tl, "cur", None)
                    if smp is not None:
                        smp.info["post_thread"] = \
                            threading.current_thread().name
            kb.post_paste = post
        if host is not None:
            real_set = host.set_attribute

            def set_attr(el, name, value):
                t0 = perf()
                try:
                    return real_set(el, name, value)
                finally:
                    if name == "AXSelectedText":
                        probe._cur_ms("ax_write", t0)
            host.set_attribute = set_attr

    def _cur_ms(self, name, t0):
        smp = getattr(self.tl, "cur", None)
        if smp is not None:
            smp.ms(name, t0, perf())

    def close(self):
        for mod, name, real in self._restore:
            setattr(mod, name, real)


# ---------------------------------------------------------------------------
# The portable rig: the independent world, a temporary store, the service.
# ---------------------------------------------------------------------------

class CallLog:
    """Every host call with its thread and time (world hooks run before
    the call, on the calling thread)."""

    def __init__(self, world):
        self.calls = []
        self.lock = threading.Lock()
        for m in HOST_METHODS:
            world.on(m, self._hook(m))

    def _hook(self, method):
        def rec(_w, *args):
            el = args[0] if args else None
            detail = getattr(el, "fid", None)
            if method == "focused_element_for":
                detail = args[0] if args else None
            name = args[1] if method in ("attribute", "is_settable",
                                         "set_attribute") and len(args) > 1 \
                else None
            with self.lock:
                self.calls.append((perf(), threading.current_thread().name,
                                   threading.get_ident(), method, detail,
                                   name))
        return rec

    def since(self, t0, t1=None):
        with self.lock:
            return [c for c in self.calls
                    if c[0] >= t0 and (t1 is None or c[0] <= t1)]


def load_world():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests/v2/insertion"))
    import m08_world
    return m08_world


def snapshot_for(world, app="A", fid="F1"):
    from localflow.v2 import ids
    from localflow.v2.context.snapshot import (ContextSnapshot,
                                               FieldContext, TargetSnapshot)
    a = world.apps[app]
    f = world.fields[fid]
    target = TargetSnapshot(
        target_snapshot_id=ids.new_id("tgt"), app_bundle=a["bundle"],
        app_name=app, app_pid=a["pid"], category="unknown",
        captured_at_utc=ids.now_utc_iso())
    field = FieldContext(role=f.role, subrole=f.subrole,
                         classification="text")
    import m08_world
    return ContextSnapshot(
        context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
        target=target, field=field,
        window_title=world.windows[f.window]["title"],
        window_element=m08_world.Win(f.window),
        captured_at_utc=ids.now_utc_iso())


class BenchKeyboard:
    """KeyboardHost with a per-post consumption plan: ``sync``,
    ``("delay", sec)`` or ``hold`` (released by ``release()``). The
    consumer reads the clipboard when IT runs and inserts into the field
    holding the system focus then (the m08_world rule)."""

    def __init__(self, world, pb):
        self.world = world
        self.pb = pb
        self.plan = "sync"
        self.posts = 0
        self._held = []

    def post_paste(self):
        self.world._enter("post_paste")
        self.posts += 1
        self.world._effect("post", self.world._system_fid(), None)
        plan = self.plan
        if plan == "sync":
            self._consume()
        elif isinstance(plan, tuple) and plan[0] == "delay":
            t = threading.Timer(plan[1], self._consume)
            t.daemon = True
            t.start()
        elif plan == "hold":
            ev = threading.Event()
            self._held.append(ev)
            threading.Thread(target=lambda: (ev.wait(30), self._consume()),
                             daemon=True).start()
        return True

    def release(self):
        while self._held:
            self._held.pop(0).set()

    def _consume(self):
        import m08_world
        w = self.world
        with w.lock:
            fid = w._system_fid()
            text = self.pb.plain() or ""
            f = w.fields.get(fid)
            if f is not None and text:
                s, e = f.sel
                f.text = m08_world.u16_splice(f.text, s, e, text)
                c = s + m08_world.u16(text)
                f.sel = (c, c)
            w._effect("paste_consumed", fid, text)


class Rig:
    def __init__(self, *, settle=0.6, window=0.0, settable=True,
                 text_f1=""):
        import tempfile
        from localflow.v2 import store as store_mod
        from localflow.v2.insertion import clipboard as clipboard_mod
        from localflow.v2.insertion import service as service_mod
        self.m = load_world()
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.store = store_mod.Store(root / "v2.db",
                                     backup_dir=root / "backups")
        self.w, self.pb, _kb = self.m.standard_world(text_f1=text_f1)
        self.w.fields["F1"].settable = settable
        self.kb = BenchKeyboard(self.w, self.pb)
        self.log = CallLog(self.w)
        self.events = []
        self.svc = service_mod.InsertionService(
            host=self.w, pasteboard=self.pb, keyboard=self.kb,
            store=self.store, emit=lambda *a, **k: self.events.append(a),
            restore_clipboard=True, observation_window_sec=window,
            settle_sec=settle)
        self.probe = Probe(self.svc, service_mod, clipboard_mod,
                           host=self.w, kb=self.kb)

    def close(self):
        self.probe.close()
        try:
            self.store.sync()
            self.store.close()
        finally:
            self.tmp.cleanup()

    def rows(self, sql, *args):
        return self.store.submit(lambda c: c.execute(sql, args).fetchall())


def effects_since(w, seq, fids=None, kinds=None):
    return [e for e in w.effects if e[0] > seq
            and (fids is None or e[2] in fids)
            and (kinds is None or e[1] in kinds)]


def reads_since(w, seq, fid):
    return [r for r in w.reads if r[0] > seq and r[2] == fid]


WRITE_KINDS = ("ax_set_text", "ax_set_range", "paste_consumed",
               "ax_set_noop")


def run_submit(rig, text, job, smp):
    rig.probe.by_key[job["job_id"]] = smp

    def on_done(r):
        smp.result = r
        smp.t["done"] = perf()
        smp.done.set()
    smp.t["enqueue_start"] = perf()
    rig.svc.submit(text, job, on_done)
    smp.t["enqueue_end"] = perf()
    if not smp.done.wait(20):
        smp.problems.append("transaction did not finish")


def worker_timings(smp):
    t = smp.t
    smp.ms("enqueue", t["enqueue_start"], t["enqueue_end"])
    if "worker_start" in t:
        smp.ms("queue_wait", t["enqueue_end"], t["worker_start"])
        smp.ms("worker_exec", t["worker_start"], t["worker_end"])
    else:
        smp.problems.append("no worker start witnessed")


def check_bound(smp, pid=101, fid="F1"):
    v = smp.info.get("validation")
    if not v:
        smp.problems.append("validation of the actual target not witnessed")
    elif not v["lease"] or v["owner_pid"] != pid \
            or v["element"] != f"El({fid})":
        smp.problems.append(f"validation not bound to {fid}/{pid}: {v}")
    if smp.info.get("worker_thread") != WORKER:
        smp.problems.append(
            f"transaction ran on {smp.info.get('worker_thread')!r}")
    op = smp.info.get("op_id")
    if not op:
        smp.problems.append("no operation id witnessed")


def ax_sample(rig, i):
    w = rig.w
    tok = token(i)
    text = f"ax-{tok} "
    jid = f"job-bench-ax-{tok}"
    pre = w.text("F1")
    seq = w.seq
    smp = Sample(jid, "ax")
    job = {"job_id": jid, "attempt": 1,
           "context_snapshot": snapshot_for(w)}
    ops0 = len(rig.pb.ops)
    run_submit(rig, text, job, smp)
    worker_timings(smp)
    check_bound(smp)
    r = smp.result
    eff = effects_since(w, seq, kinds=WRITE_KINDS)
    if r is None or r.state != "confirmed" or r.method != "ax_replacement":
        smp.problems.append(f"result {getattr(r, 'state', None)}/"
                            f"{getattr(r, 'method', None)}")
    if [(e[1], e[2], e[3]) for e in eff] != [("ax_set_text", "F1", text)]:
        smp.problems.append(f"effects {eff}")
    if w.text("F1") != pre + text:
        smp.problems.append("field bytes differ from the expected insert")
    if len(rig.pb.ops) != ops0:
        smp.problems.append("the AX path touched the clipboard")
    write_seq = eff[0][0] if eff else None
    rd = reads_since(w, seq, "F1")
    if write_seq is None or not [x for x in rd if x[0] < write_seq] \
            or not [x for x in rd if x[0] > write_seq]:
        smp.problems.append("pre-read and readback not both witnessed")
    for k in ("validation", "ax_write", "pre_read"):
        if k not in smp.d:
            smp.problems.append(f"no {k} timing")
    smp.info["expected_bytes"] = len((pre + text).encode("utf-8"))
    return smp


def clipboard_sample(rig, i, *, contend):
    w, pb = rig.w, rig.pb
    tok = token(i)
    text = f"cb-{tok} "
    jid = f"job-bench-cb-{tok}"
    orig = f"USER-ORIGINAL-{tok}"
    contender = f"USER-CONTENDER-{tok}"
    pb.user_copy(items=[[("public.utf8-plain-text", orig.encode()),
                         ("public.rtf", ("{\\rtf1 " + orig + "}").encode())]])
    pre = w.text("F1")
    seq = w.seq
    ops0 = len(pb.ops)
    smp = Sample(jid, "clipboard")
    rig.probe.contend = (lambda s: pb.user_copy(contender)) \
        if contend else None
    job = {"job_id": jid, "attempt": 1,
           "context_snapshot": snapshot_for(w)}
    run_submit(rig, text, job, smp)
    rig.probe.contend = None
    worker_timings(smp)
    check_bound(smp)
    r = smp.result
    if r is None or r.state != "confirmed" \
            or r.method != "clipboard_transaction":
        smp.problems.append(f"result {getattr(r, 'state', None)}/"
                            f"{getattr(r, 'method', None)}")
    ops = pb.ops[ops0:]
    pub = [o for o in ops if o[1] == "write_text" and o[2] == text]
    eff = effects_since(w, seq, kinds=("post",) + WRITE_KINDS)
    post = [e for e in eff if e[1] == "post"]
    cons = [e for e in eff if e[1] == "paste_consumed"]
    if len(pub) != 1 or len(post) != 1 or len(cons) != 1 \
            or not pub[0][0] < post[0][0] < cons[0][0]:
        smp.problems.append(f"publish->post->consume not witnessed: "
                            f"{ops} {eff}")
    elif cons[0][2] != "F1" or cons[0][3] != text:
        smp.problems.append(f"consumed {cons[0]}")
    if w.text("F1") != pre + text:
        smp.problems.append("field bytes differ from the expected insert")
    rd = reads_since(w, seq, "F1")
    if not cons or not [x for x in rd if x[0] > cons[0][0]]:
        smp.problems.append("destination readback after consumption not "
                            "witnessed")
    clip = r.clipboard if r is not None else {}
    if contend:
        if pb.plain() != contender \
                or clip.get("restore_skipped_reason") != "user_copy_won":
            smp.problems.append("generation guard not witnessed: board="
                                f"{pb.plain()!r} clip={clip}")
    else:
        restored = [o for o in ops if o[1] == "write_items"]
        if pb.plain() != orig or not restored \
                or clip.get("generation_after_restore") is None:
            smp.problems.append(f"restore of the owned generation not "
                                f"witnessed: board={pb.plain()!r}")
    smp.info["contended"] = contend
    smp.info["generation_published"] = clip.get("generation_published")
    for k in ("validation", "clip_snapshot", "clip_publish", "clip_post",
              "readback"):
        if k not in smp.d:
            smp.problems.append(f"no {k} timing")
    return smp


def settle_sample(i, *, delay, settle):
    rig = Rig(settle=settle, settable=False)
    try:
        w, pb = rig.w, rig.pb
        tok = token(i)
        text = f"st-{tok} "
        jid = f"job-bench-st-{tok}"
        pb.user_copy(f"USER-ORIGINAL-{tok}")
        rig.kb.plan = ("delay", delay)
        smp = Sample(jid, "settle")
        run_submit(rig, text, {"job_id": jid, "attempt": 1,
                               "context_snapshot": snapshot_for(w)}, smp)
        worker_timings(smp)
        check_bound(smp)
        r = smp.result
        rb = smp.d.get("readback")
        if rb is None:
            smp.problems.append("no readback timing")
        inside = delay < settle
        # Delay conservation: the readback clock contains the consumer's
        # delay (inside) or the whole settle bound (beyond); the caller's
        # clock contains neither.
        if rb is not None and rb < min(delay, settle) * 1000.0 * 0.95:
            smp.problems.append(f"readback {rb} ms excludes the injected "
                                f"delay")
        if smp.d.get("enqueue", 0) > 0.25 * delay * 1000.0:
            smp.problems.append("the caller's clock carries the delay")
        if inside:
            if r is None or r.state != "confirmed":
                smp.problems.append(f"inside-settle result "
                                    f"{getattr(r, 'state', None)}")
        else:
            if r is None or r.state != "posted_unverified" or \
                    r.clipboard.get("restore_skipped_reason") != \
                    "readback_pending":
                smp.problems.append("beyond-settle ownership not kept")
            self_ok = self_wait(lambda: w.text("F1") == text, 3)
            if not self_ok:
                smp.problems.append("the late paste did not land exactly")
            if pb.plain() != text:
                smp.problems.append("owned payload replaced before the "
                                    "late consumer")
        if w.text("F1") != text and inside:
            smp.problems.append("field bytes differ")
        smp.info["population"] = "inside_settle" if inside \
            else "beyond_settle"
        return smp
    finally:
        rig.close()


def self_wait(pred, timeout):
    deadline = perf() + timeout
    while not pred():
        if perf() >= deadline:
            return False
        time.sleep(0.005)
    return True


# ---------------------------------------------------------------------------
# Observer cohorts: full ticks, a re-anchoring tick, the stopping tick.
# ---------------------------------------------------------------------------

class TickClock:
    """Stand-in for ``observation.time`` in this process only: real
    monotonic time, compressed sleeps, and a boundary per sleep so a tick
    is exactly the work between two sleeps of one observer thread."""

    def __init__(self):
        self.bounds = {}       # thread ident -> [(t_sleep_start, t_end, obs state)]
        self.observers = {}

    def monotonic(self):
        return time.monotonic()

    def sleep(self, _sec):
        ident = threading.get_ident()
        t0 = perf()
        obs = self.observers.get(ident)
        state = (obs.reanchors, obs.ticks, obs.start) if obs else None
        time.sleep(TICK_SLEEP)
        self.bounds.setdefault(ident, []).append((t0, perf(), state))


def observer_cohorts(scale):
    from localflow.v2.insertion import observation as observation_mod
    clock = TickClock()
    real_time = observation_mod.time
    observation_mod.time = clock
    steady, reanchor, stop = [], [], []
    required = {"frontmost", "focused_element_for", "element_pid",
                "number_of_characters", "string_for_range"}
    try:
        n_obs = max(2, int(6 * scale))
        for i in range(n_obs):
            rig = Rig(window=30.0)
            try:
                w = rig.w
                tok = token(i)
                text = f"ob-{tok}"
                jid = f"job-bench-ob-{tok}"
                box = {}
                smp = Sample(jid, "observer_insert")
                rig.probe.by_key[jid] = smp

                def on_obs(info, _b=box):
                    _b["obs"] = info["observer"]
                done = threading.Event()
                rig.svc.submit(text, {"job_id": jid, "attempt": 1,
                                      "context_snapshot": snapshot_for(w),
                                      "observation_consent": True},
                               lambda r: done.set(), on_observation=on_obs)
                done.wait(10)
                obs = box.get("obs")
                if obs is None:
                    s = Sample(jid, "observer")
                    s.problems.append("no observer started")
                    steady.append(s)
                    continue
                clock.observers[obs._thread.ident] = obs
                closed = threading.Event()
                close_t = {}
                obs.subscribe_close(lambda: (close_t.__setitem__(
                    "t", perf()), closed.set()))
                self_wait(lambda: len(clock.bounds.get(
                    obs._thread.ident, [])) >= 25, 5)
                # Re-anchoring ticks: type before the owned range.
                for k in range(max(2, int(4 * scale))):
                    before = obs.reanchors
                    old_start = obs.start
                    w.user_type("F1", 0, "x")
                    if not self_wait(lambda: obs.reanchors > before, 3):
                        s = Sample(jid, "reanchor")
                        s.problems.append("re-anchor never happened")
                        reanchor.append(s)
                        break
                    s = Sample(f"{jid}-ra{k}", "reanchor")
                    s.info["expected_start"] = old_start + 1
                    s.info["observed_start"] = obs.start
                    if obs.start != old_start + 1:
                        s.problems.append("re-anchored to the wrong offset")
                    reanchor.append(s)
                    s.info["_ident"] = obs._thread.ident
                    s.info["_reanchors"] = obs.reanchors
                self_wait(lambda: len(clock.bounds.get(
                    obs._thread.ident, [])) >= 45, 5)
                # The stopping tick: replace our text with a longer word.
                new = f"EDITED-{tok}"
                start = obs.start
                n = rig.m.u16(text)
                t_edit = perf()
                w.user_replace("F1", start, start + n, new)
                closed.wait(5)
                s = Sample(f"{jid}-stop", "stop")
                s.info["_ident"] = obs._thread.ident
                s.info["_t_edit"] = t_edit
                s.info["_t_close"] = close_t.get("t")
                if obs.stop_reason != "owned_range_edited":
                    s.problems.append(f"stop {obs.stop_reason}")
                rig.store.sync()
                after = rig.rows("SELECT content_text FROM artifacts WHERE"
                                 " artifact_id=?", obs.after_artifact)
                if not after or after[0][0] != new:
                    s.problems.append(f"after-text {after} != {new!r}")
                s.info["after_matches_edit"] = bool(after) and \
                    after[0][0] == new
                stop.append(s)
                # Steady ticks: every bound on this thread before the
                # first edit whose state shows no re-anchor change.
                bounds = clock.bounds.get(obs._thread.ident, [])
                calls = rig.log.calls
                obs_calls = [c for c in calls if c[2] == obs._thread.ident]
                ra_marks = [x.info.get("_reanchors") for x in reanchor
                            if x.info.get("_ident") == obs._thread.ident]
                for a, b in zip(bounds, bounds[1:]):
                    t_start, t_stop = a[1], b[0]
                    tick_calls = [c for c in obs_calls
                                  if t_start <= c[0] <= t_stop]
                    methods = {c[3] for c in tick_calls}
                    names = {c[5] for c in tick_calls if c[3] == "attribute"}
                    changed = a[2] is not None and b[2] is not None \
                        and b[2][0] != a[2][0]
                    ms = (t_stop - t_start) * 1000.0
                    if changed:
                        # the tick in which a re-anchor happened
                        for x in reanchor:
                            if x.info.get("_ident") == obs._thread.ident \
                                    and x.info.get("_reanchors") == b[2][0] \
                                    and "tick" not in x.d:
                                x.d["tick"] = round(ms, 4)
                                win = [c for c in tick_calls
                                       if c[3] == "string_for_range"]
                                x.info["window_reads"] = len(win)
                                if len(win) < 2:
                                    x.problems.append("no bounded window "
                                                      "read in the tick")
                        continue
                    s2 = Sample(f"{jid}-t", "tick")
                    s2.d["tick"] = round(ms, 4)
                    miss = required - methods
                    if miss or not {"AXRole", "AXSubrole"} <= names:
                        s2.problems.append(f"full tick not witnessed: "
                                           f"missing {sorted(miss)} "
                                           f"{sorted(names)}")
                    bad = [c for c in tick_calls if c[4] not in
                           ("F1", 101, None)]
                    if bad:
                        s2.problems.append(f"read outside F1: {bad[:2]}")
                    steady.append(s2)
                last = bounds[-1][1] if bounds else None
                if last is not None and close_t.get("t"):
                    s.d["stop_tick"] = round((close_t["t"] - max(
                        last, t_edit)) * 1000.0, 4)
                else:
                    s.problems.append("stop tick boundary missing")
                del ra_marks
            finally:
                rig.close()
        for x in reanchor:
            if "tick" not in x.d and not x.problems:
                x.problems.append("re-anchor tick not measured")
    finally:
        observation_mod.time = real_time
    return steady, reanchor, stop


# ---------------------------------------------------------------------------
# Undo and repaste on the queue thread.
# ---------------------------------------------------------------------------

def undo_repaste_cohorts(scale):
    undo, absent, present = [], [], []
    rig = Rig()
    try:
        w = rig.w
        n = max(3, int(20 * scale))
        for i in range(n):
            base = ax_sample(rig, 1000 + i)
            if base.problems:
                s = Sample(base.key, "undo")
                s.problems.append(f"setup insert: {base.problems}")
                undo.append(s)
                continue
            text = base.key.replace("job-bench-ax-", "ax-") + " "
            pre = w.text("F1")[:-len(text)]
            seq = w.seq
            t0 = perf()
            out = rig.svc.undo_last()
            s = Sample(base.key, "undo")
            s.d["undo_call"] = round((perf() - t0) * 1000.0, 4)
            s.d["undo_exec"] = round(getattr(rig.probe, "last_undo_ms", -1), 4)
            if getattr(rig.probe, "last_undo_thread", None) != WORKER:
                s.problems.append("undo not on the queue thread")
            eff = effects_since(w, seq, kinds=WRITE_KINDS)
            kinds = [(e[1], e[2]) for e in eff]
            if (out or {}).get("outcome") != "undone" or kinds != [
                    ("ax_set_range", "F1"), ("ax_set_text", "F1")] \
                    or w.text("F1") != pre:
                s.problems.append(f"undo not witnessed: {out} {eff}")
            undo.append(s)
        for i in range(n):
            base = ax_sample(rig, 2000 + i)
            text = base.key.replace("job-bench-ax-", "ax-") + " "
            full = w.text("F1")
            w.user_replace("F1", rig.m.u16(full) - rig.m.u16(text),
                           rig.m.u16(full), "")
            for label, bucket in (("absent", absent), ("present", present)):
                seq = w.seq
                t_call = perf()
                rig.probe.last_repaste = None
                out = rig.svc.paste_text(text, job_id=base.key)
                t_ret = perf()
                s = Sample(f"{base.key}-{label}", f"repaste_{label}")
                s.d["repaste_call"] = round((t_ret - t_call) * 1000.0, 4)
                ok = self_wait(lambda: rig.probe.last_repaste is not None
                               and not rig.svc.busy, 5)
                time.sleep(0.01)
                if not ok or out.get("outcome") != "repaste_queued":
                    s.problems.append(f"repaste not run: {out}")
                    bucket.append(s)
                    continue
                ms, thread, _ = rig.probe.last_repaste
                s.d["repaste_exec"] = round(ms, 4)
                if thread != WORKER:
                    s.problems.append(f"repaste ran on {thread}")
                rd = [c for c in rig.log.since(t_call)
                      if c[3] in ("number_of_characters", "string_for_range")
                      and c[1] == WORKER]
                if len(rd) < 2:
                    s.problems.append("reconciliation reads not witnessed")
                eff = effects_since(w, seq, kinds=WRITE_KINDS)
                count = w.text("F1").count(text.strip())
                if label == "absent":
                    if [(e[1], e[3]) for e in eff] != [("ax_set_text", text)] \
                            or count != 1:
                        s.problems.append(f"repaste effect {eff}")
                else:
                    if eff or count != 1:
                        s.problems.append(f"already-present pasted {eff}")
                bucket.append(s)
    finally:
        rig.close()
    return undo, absent, present


# ---------------------------------------------------------------------------
# The real AppDelegate entry points.
# ---------------------------------------------------------------------------

class AppRig:
    def __init__(self):
        sys.path.insert(0, str(ROOT / "tests/v2/normalization"))
        import test_normalization_pipeline as tnp
        import localflow.app as app_mod
        from localflow.v2.insertion import clipboard as clipboard_mod
        from localflow.v2.insertion import service as service_mod
        self.app_mod = app_mod
        self.m = load_world()
        stub = tnp.StubInsertionService
        tnp.StubInsertionService = lambda d: d._insertion
        try:
            self.h = tnp.Harness([1.0], cfg={"outcome_observation_sec": 0},
                                 supervisor=tnp.RecordingSupervisor("x"))
        finally:
            tnp.StubInsertionService = stub
        d = self.d = self.h.d
        d._context = None
        self.svc = d._insertion
        self.w, self.pb, _kb = self.m.standard_world()
        self.kb = BenchKeyboard(self.w, self.pb)
        self.svc.host, self.svc.pasteboard = self.w, self.pb
        self.svc.keyboard = self.kb
        self.svc._settle_sec = 0.05
        self.log = CallLog(self.w)
        self.probe = Probe(self.svc, service_mod, clipboard_mod,
                           host=self.w, kb=self.kb)
        self.deferred = []
        self._real_after = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = \
            lambda fn, *a: self.deferred.append((fn, a))
        self.delay = False
        for m in ("number_of_characters", "string_for_range"):
            self.w.on(m, lambda _w, *a: time.sleep(UI_DELAY)
                      if self.delay else None)

    def flush(self):
        """Deferred AppHelper.callAfter work, run on this (main) thread;
        returns the durations of each callback."""
        out = []
        while self.deferred:
            fn, a = self.deferred.pop(0)
            t0 = perf()
            fn(*a)
            out.append((getattr(fn, "__name__", "?"),
                        (perf() - t0) * 1000.0))
        return out

    def job(self, tok):
        jid, _fam = self.d.store.create_job(state="cleaning")
        job = {"job_id": jid, "ctx": None, "attempt": 1, "cancelled": False,
               "failed": False, "journal": None,
               "context_snapshot": snapshot_for(self.w)}
        job["target"] = job["context_snapshot"].target
        self.d._pending += 1
        self.d._active_jobs.append(job)
        return job

    def idle(self, timeout=20):
        return self_wait(lambda: not self.svc.busy
                         and self.svc._q.empty(), timeout)

    def close(self):
        self.app_mod.AppHelper.callAfter = self._real_after
        self.probe.close()
        self.h.close()


def ui_cohorts(scale):
    rig = AppRig()
    d, w = rig.d, rig.w
    caller = threading.current_thread().name
    cohorts = {"ui_finish_with_text": [], "ui_insertion_done_callback": [],
               "ui_recovery_paste_again": [], "ui_history_paste_text": [],
               "ui_undo_last_insertion": []}
    n = max(3, int(20 * scale))

    def ui_checks(s, t_call, t_ret, effect_pred, name):
        s.ms("callback", t_call, t_ret)
        on_caller = [c for c in rig.log.since(t_call) if c[1] == caller]
        if on_caller:
            s.problems.append(f"{len(on_caller)} AX call(s) on the "
                              f"calling thread")
        ok = self_wait(effect_pred, 30)
        t_eff = perf()
        if not ok:
            s.problems.append(f"{name}: effect never witnessed")
            return
        s.ms("to_effect", t_call, t_eff)
        # Delay conservation: the worker clock carries >= one injected
        # read delay; the callback clock carries none.
        if s.d["to_effect"] < UI_DELAY * 1000.0:
            s.problems.append("the injected delay is not in the worker "
                              "clock")
        if s.d["callback"] >= UI_DELAY * 1000.0:
            s.problems.append("the injected delay is in the callback clock")
    try:
        rig.delay = True
        # _finishWithText_: all n submitted back to back (a busy queue:
        # each call arrives while earlier transactions still execute).
        pending = []
        for i in range(n):
            tok = token(i)
            text = f"ui-{tok} "
            job = rig.job(tok)
            smp = Sample(job["job_id"], "ui_finish")
            rig.probe.by_key[job["job_id"]] = smp
            seq = w.seq
            t_call = perf()
            d._finishWithText_(text, job)
            t_ret = perf()
            smp.ms("callback", t_call, t_ret)
            smp.info["busy_at_call"] = rig.svc.busy or not rig.svc._q.empty()
            pending.append((smp, text, job, t_call, seq))
        rig.idle(120)
        durs = rig.flush()
        for name, ms in durs:
            if name == "_insertionDone_":
                s = Sample("done", "ui_done")
                s.d["callback"] = round(ms, 4)
                cohorts["ui_insertion_done_callback"].append(s)
        expected = "".join(p[1] for p in pending)
        for smp, text, job, t_call, seq in pending:
            on_caller = [c for c in rig.log.calls
                         if c[1] == caller and c[0] >= t_call]
            if on_caller:
                smp.problems.append("AX call on the calling thread")
            if "worker_start" not in smp.t:
                smp.problems.append("no worker witnessed")
            else:
                smp.ms("to_worker_end", t_call, smp.t["worker_end"])
                if smp.d["to_worker_end"] < UI_DELAY * 1000.0:
                    smp.problems.append("delay not in the worker clock")
            if smp.d["callback"] >= UI_DELAY * 1000.0:
                smp.problems.append("delay in the callback clock")
            eff = [e for e in w.effects if e[1] == "ax_set_text"
                   and e[3] == text]
            if len(eff) != 1 or eff[0][2] != "F1":
                smp.problems.append(f"effect {eff}")
            if smp.result is None and job not in d._active_jobs:
                pass
            if job in d._active_jobs:
                smp.problems.append("job never settled on the main thread")
            check_bound(smp)
            cohorts["ui_finish_with_text"].append(smp)
        if w.text("F1") != expected:
            cohorts["ui_finish_with_text"][-1].problems.append(
                "field bytes differ from the ordered inserts")
        if sum(1 for s in cohorts["ui_finish_with_text"]
               if s.info.get("busy_at_call")) < n - 1:
            cohorts["ui_finish_with_text"][-1].problems.append(
                "the queue was not busy at the calls")

        # Recovery Paste Again: a fresh result each time, removed from the
        # field, then the menu action (queue busy with nothing else).
        for i in range(n):
            rig.delay = False
            tok = token(100 + i)
            text = f"rc-{tok} "
            job = rig.job(tok)
            d._finishWithText_(text, job)
            rig.idle()
            rig.flush()
            full = w.text("F1")
            w.user_replace("F1", rig.m.u16(full) - rig.m.u16(text),
                           rig.m.u16(full), "")
            rig.delay = True
            s = Sample(f"rc-{tok}", "ui_recovery")
            seq = w.seq
            t_call = perf()
            d.pasteLastResultAgain_(None)
            t_ret = perf()
            ui_checks(s, t_call, t_ret,
                      lambda: any(e[0] > seq and e[1] == "ax_set_text"
                                  and e[3] == text for e in w.effects),
                      "recovery")
            rig.idle()
            rig.flush()
            if w.text("F1").count(text) != 1:
                s.problems.append("recovery repaste count != 1")
            cohorts["ui_recovery_paste_again"].append(s)

        # History Paste Again (idle queue: the Hub refuses mid-flight).
        for i in range(n):
            rig.delay = True
            rig.idle()
            tok = token(200 + i)
            text = f"hi-{tok} "
            s = Sample(f"hi-{tok}", "ui_history")
            seq = w.seq
            t_call = perf()
            out = d.hubPasteText(text, job_id=None)
            t_ret = perf()
            if out.get("outcome") != "repaste_queued":
                s.problems.append(f"hub refused: {out}")
            ui_checks(s, t_call, t_ret,
                      lambda: any(e[0] > seq and e[1] == "ax_set_text"
                                  and e[3] == text for e in w.effects),
                      "history")
            rig.idle()
            rig.flush()
            cohorts["ui_history_paste_text"].append(s)

        # Undo Last Insertion: a fresh insert, then the menu action.
        for i in range(n):
            rig.delay = False
            tok = token(300 + i)
            text = f"un-{tok} "
            job = rig.job(tok)
            d._finishWithText_(text, job)
            rig.idle()
            rig.flush()
            pre = w.text("F1")[:-len(text)]
            rig.delay = True
            s = Sample(f"un-{tok}", "ui_undo")
            seq = w.seq
            t_call = perf()
            d.undoLastInsertion_(None)
            t_ret = perf()
            ui_checks(s, t_call, t_ret,
                      lambda: any(e[0] > seq and e[1] == "ax_set_text"
                                  and e[3] == "" for e in w.effects)
                      and w.text("F1") == pre, "undo")
            rig.idle()
            rig.flush()
            cohorts["ui_undo_last_insertion"].append(s)
    finally:
        rig.delay = False
        rig.close()
    return cohorts


# ---------------------------------------------------------------------------
# Cold processes and the native cohort (subprocesses).
# ---------------------------------------------------------------------------

def cold_sample_main(out_path):
    t0 = perf()
    import localflow.v2.insertion.service  # noqa: F401 — the cold import
    rig = Rig()
    t_ready = perf()
    try:
        ax = ax_sample(rig, 0)
    finally:
        rig.close()
    rig2 = Rig(settable=False)
    try:
        cb = clipboard_sample(rig2, 0, contend=False)
    finally:
        rig2.close()
    pathlib.Path(out_path).write_text(json.dumps({
        "import_and_setup_ms": round((t_ready - t0) * 1000.0, 3),
        "ax": {"d": ax.d, "problems": ax.problems},
        "clipboard": {"d": cb.d, "problems": cb.problems}}))


def native_main(out_path, samples, helper_cmd):
    """Real Accessibility, owned helper only (never run isolated)."""
    import tempfile
    import ApplicationServices as AS
    from AppKit import NSPasteboard
    from localflow.v2 import store as store_mod
    from localflow.v2.context.snapshot import TargetSnapshot
    from localflow.v2.insertion import clipboard as clipboard_mod
    from localflow.v2.insertion import hosts as hosts_mod
    from localflow.v2.insertion import service as service_mod
    rep = {"trusted": bool(AS.AXIsProcessTrusted()), "samples": []}
    if not rep["trusted"]:
        rep["not_run"] = "no Accessibility grant for this terminal"
        pathlib.Path(out_path).write_text(json.dumps(rep))
        return
    t_proc = perf()
    proc = subprocess.Popen(helper_cmd + [json.dumps({"text": ""})],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True)
    pid = int(proc.stdout.readline().split()[1])
    time.sleep(0.6)

    def helper(cmd):
        proc.stdin.write(json.dumps(cmd) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    ident = {"pid": pid, "bundle": None, "name": "LF-M08 helper"}
    try:
        from AppKit import NSRunningApplication
        ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            pid)
        ident["bundle"] = ra.bundleIdentifier() if ra else None
    except Exception:
        pass

    class OwnedHost(hosts_mod.SystemInsertionHost):
        # Only the frontmost identity is pinned to the helper: every
        # element is still acquired from the helper's own application
        # element and checked with AXUIElementGetPid.
        def frontmost(self):
            return dict(ident)

        def focused_element(self):
            raise RuntimeError("system-wide focus must never be read")

    class NoKeyboard:
        posts = 0

        def post_paste(self):
            NoKeyboard.posts += 1
            raise RuntimeError("no key event may be posted")

    pb = hosts_mod.SystemPasteboard.__new__(hosts_mod.SystemPasteboard)
    pb._pb = NSPasteboard.pasteboardWithUniqueName()
    host = OwnedHost()
    tmp = tempfile.TemporaryDirectory()
    st = store_mod.Store(pathlib.Path(tmp.name) / "v2.db",
                         backup_dir=pathlib.Path(tmp.name) / "b")
    svc = service_mod.InsertionService(
        host=host, pasteboard=pb, keyboard=NoKeyboard(), store=st,
        emit=lambda *a, **k: None, observation_window_sec=0,
        settle_sec=0.05)
    probe = Probe(svc, service_mod, clipboard_mod, host=host)
    rep["setup_ms"] = round((perf() - t_proc) * 1000.0, 3)
    try:
        for i in range(samples):
            tok = token(i)
            pre = f"native pre {tok} "
            text = f"X\U0001F600Y {tok}" if i % 3 == 2 else f"native {tok}"
            n16 = len(pre.encode("utf-16-le")) // 2
            helper({"cmd": "set", "text": pre, "sel": [n16, 0]})
            jid = f"job-native-{tok}"
            smp = Sample(jid, "native")
            probe.by_key[jid] = smp
            tgt = TargetSnapshot(target_snapshot_id=f"tgt-{tok}",
                                 app_bundle=ident["bundle"],
                                 app_pid=pid)
            done = threading.Event()

            def on_done(r, _s=smp):
                _s.result = r
                _s.t["done"] = perf()
                done.set()
            smp.t["enqueue_start"] = perf()
            svc.submit(text, {"job_id": jid, "attempt": 1, "target": tgt},
                       on_done)
            smp.t["enqueue_end"] = perf()
            done.wait(20)
            worker_timings(smp)
            state = helper({"cmd": "state"})
            r = smp.result
            if state.get("text") != pre + text:
                smp.problems.append("AppKit text differs from pre+text")
            if r is None or r.method != "ax_replacement":
                smp.problems.append(f"method {getattr(r, 'method', None)}")
            if r is not None:
                want = (n16, n16 + len(text.encode("utf-16-le")) // 2)
                if (r.owned_start, r.owned_end) != want:
                    smp.problems.append(f"owned {(r.owned_start, r.owned_end)}"
                                        f" != {want} (UTF-16 host units)")
            v = smp.info.get("validation") or {}
            if not v.get("lease") or v.get("owner_pid") != pid:
                smp.problems.append(f"validation not bound to the helper: "
                                    f"{v}")
            if smp.info.get("worker_thread") != WORKER:
                smp.problems.append("not on the queue thread")
            if NoKeyboard.posts:
                smp.problems.append("a key event was attempted")
            rep["samples"].append({
                "d": smp.d, "state": getattr(r, "state", None),
                "readback": getattr(r, "readback", None),
                "reason": getattr(r, "reason_code", None),
                "astral": "\U0001F600" in text, "problems": smp.problems})
    finally:
        probe.close()
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        st.close()
        tmp.cleanup()
    pathlib.Path(out_path).write_text(json.dumps(rep))


# ---------------------------------------------------------------------------
# Environment, aggregation, verdicts.
# ---------------------------------------------------------------------------

def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:
        return None


def environment(code_rev=None):
    import hashlib
    from importlib.metadata import version, PackageNotFoundError

    def v(name):
        try:
            return version(name)
        except PackageNotFoundError:
            return None
    try:
        import AppKit
        isolated = type(AppKit.NSPasteboard).__name__ == "_PasteboardClass"
    except Exception:
        isolated = None
    is_repo = (ROOT / ".git").exists()
    dirty = sh("git", "-C", str(ROOT), "status", "--porcelain",
               "--untracked-files=no") if is_repo else None
    import localflow
    origin = pathlib.Path(localflow.__file__).resolve()
    try:
        rel = origin.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = None
    return {
        "macos": {"product_version": sh("sw_vers", "-productVersion"),
                  "build": sh("sw_vers", "-buildVersion")},
        "machine": sh("uname", "-m"), "model": sh("sysctl", "-n",
                                                   "hw.model"),
        "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "ncpu": os.cpu_count(),
        "memory_bytes": int(sh("sysctl", "-n", "hw.memsize") or 0),
        "python": sys.version.split()[0],
        "pyobjc": v("pyobjc-core"),
        "power": (sh("pmset", "-g", "batt") or "").splitlines()[:1],
        "load_average": [round(x, 2) for x in os.getloadavg()],
        "desktop_isolated": isolated,
        "code_root_kind": ("git checkout" if is_repo else
                           "git archive copy (tracked files of "
                           "code_root_sha; overlays listed)"),
        "code_root_sha": (sh("git", "-C", str(ROOT), "rev-parse", "HEAD")
                          if is_repo else code_rev),
        "tracked_files_modified": bool(dirty) if dirty is not None else None,
        "tracked_modified_paths": (dirty.splitlines() if dirty else []),
        "benchmark_sha256": hashlib.sha256(
            pathlib.Path(__file__).resolve().read_bytes()).hexdigest(),
        "localflow_imported_from_root": rel,
    }


def cohort_doc(samples, fields, boundary, gate=None, warmth="warm"):
    doc = {"boundary": boundary, "warmth": warmth, "n": len(samples),
           "invalid_samples": sum(1 for s in samples if s.problems),
           "problems": [p for s in samples for p in s.problems][:6]}
    for f in fields:
        doc[f] = summary([s.d[f] for s in samples if f in s.d])
    if gate is not None:
        doc["budget"] = gate
    return doc


def main(argv):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests/v2/insertion"))
    if "--cold-sample" in argv:
        cold_sample_main(argv[argv.index("--cold-sample") + 1])
        return 0
    if "--native-cohort" in argv:
        i = argv.index("--native-cohort")
        native_main(argv[i + 1], int(argv[i + 2]),
                    [sys.executable, str(pathlib.Path(__file__).resolve()),
                     "--helper"])
        return 0
    outdir = pathlib.Path(argv[0]) if argv and not argv[0].startswith("--") \
        else None
    scale = float(argv[argv.index("--scale") + 1]) \
        if "--scale" in argv else 1.0
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests/v2/insertion"))
    t_start = time.time()
    env = environment(argv[argv.index("--code-rev") + 1]
                      if "--code-rev" in argv else None)
    if "--overlay" in argv:
        env["overlays"] = argv[argv.index("--overlay") + 1].split(",")
    cohorts = {}
    n = max(4, int(60 * scale))

    rig = Rig()
    ax = [ax_sample(rig, i) for i in range(n)]
    rig.close()
    cohorts["ax_transaction"] = cohort_doc(
        ax, ["enqueue", "queue_wait", "worker_exec", "validation",
             "pre_read", "ax_write"],
        "enqueue = submit() on the caller; queue_wait = enqueue end -> "
        "worker start; worker_exec = the whole transaction on the queue "
        "thread; validation = validate_target inside it on the bound "
        "element; ax_write = the AXSelectedText set (world double)",
        gate={"enqueue_p95_ms_max": S24_UI_P95_MS, "source": "S24"})

    rig = Rig(settable=False)
    cb = [clipboard_sample(rig, i, contend=(i % 4 == 3)) for i in range(n)]
    rig.close()
    cohorts["clipboard_transaction"] = cohort_doc(
        cb, ["enqueue", "queue_wait", "worker_exec", "validation",
             "pre_read", "clip_snapshot", "clip_publish", "clip_post",
             "readback", "clip_restore"],
        "clipboard path, instant consumer; readback = the settle-bounded "
        "poll that ends at the first attributable match; clip_restore = "
        "the generation-checked restore (every 4th sample contends: a "
        "user copy lands before the check and must survive)",
        gate={"enqueue_p95_ms_max": S24_UI_P95_MS, "source": "S24"})

    st = []
    for i in range(max(2, int(10 * scale))):
        st.append(settle_sample(i, delay=0.12, settle=0.3))
        st.append(settle_sample(100 + i, delay=0.45, settle=0.25))
    cohorts["clipboard_settle_inside"] = cohort_doc(
        [s for s in st if s.info.get("population") == "inside_settle"],
        ["enqueue", "readback", "worker_exec"],
        "consumer delayed 120 ms, settle 300 ms: the readback clock "
        "contains the delay, the caller's does not")
    cohorts["clipboard_settle_beyond"] = cohort_doc(
        [s for s in st if s.info.get("population") == "beyond_settle"],
        ["enqueue", "readback", "worker_exec"],
        "consumer delayed 450 ms, settle 250 ms: readback = the deliberate "
        "settle wait; ownership kept; the late paste lands the right text")

    steady, ra, stop = observer_cohorts(scale)
    cohorts["observer_tick"] = cohort_doc(
        steady, ["tick"], "one FULL observer tick (identity, owned element, "
        "owner pid, role+subrole, length, owned-range read) between two "
        "compressed sleeps; no approximation")
    cohorts["observer_reanchor_tick"] = cohort_doc(
        ra, ["tick"], "a tick that re-anchors (one bounded window read) "
        "after typing before the owned range")
    cohorts["observer_stop"] = cohort_doc(
        stop, ["stop_tick"], "user edit -> the tick that records the "
        "bounded edit (artifacts, lease) -> close callback")

    undo, absent, present = undo_repaste_cohorts(scale)
    cohorts["undo"] = cohort_doc(
        undo, ["undo_call", "undo_exec"], "target-bound undo; undo_exec = "
        "on the queue thread")
    cohorts["repaste_absent"] = cohort_doc(
        absent, ["repaste_call", "repaste_exec"], "History/Recovery engine: "
        "repaste_call = the caller's cost; repaste_exec = reconcile + "
        "transaction on the queue thread")
    cohorts["repaste_present"] = cohort_doc(
        present, ["repaste_call", "repaste_exec"], "reconcile finds the "
        "text: no effect")

    ui = ui_cohorts(scale)
    gate = {"callback_p95_ms_max": S24_UI_P95_MS, "source": "S24 UI "
            "acknowledgment / hotkey response; no model or disk work on "
            "the UI callback"}
    cohorts["ui_finish_with_text"] = cohort_doc(
        ui["ui_finish_with_text"], ["callback", "to_worker_end"],
        "AppDelegate._finishWithText_ on the calling thread, each call "
        "while earlier transactions execute, 200 ms injected per AX content "
        "read on the worker", gate=gate)
    cohorts["ui_recovery_paste_again"] = cohort_doc(
        ui["ui_recovery_paste_again"], ["callback", "to_effect"],
        "AppDelegate.pasteLastResultAgain_ (Recovery) on the calling "
        "thread; to_effect = call -> witnessed repaste effect", gate=gate)
    cohorts["ui_history_paste_text"] = cohort_doc(
        ui["ui_history_paste_text"], ["callback", "to_effect"],
        "AppDelegate.hubPasteText (History) on the calling thread",
        gate=gate)
    cohorts["ui_undo_last_insertion"] = cohort_doc(
        ui["ui_undo_last_insertion"], ["callback", "to_effect"],
        "AppDelegate.undoLastInsertion_ on the calling thread", gate=gate)
    cohorts["ui_insertion_done_callback"] = cohort_doc(
        ui["ui_insertion_done_callback"], ["callback"],
        "AppDelegate._insertionDone_ on the main thread (completion "
        "bookkeeping: job states, usage, evidence — store writes); reported, "
        "not an S24 acknowledgment path")

    cold = []
    iso = str(ROOT / "tests/v2/context/run_isolated.py")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for i in range(max(2, int(12 * scale))):
            out = pathlib.Path(td) / f"cold{i}.json"
            p = subprocess.run([sys.executable, iso, __file__,
                                "--cold-sample", str(out)],
                               capture_output=True, text=True, timeout=180)
            s = Sample(f"cold{i}", "cold")
            try:
                rec = json.loads(out.read_text())
                s.d["import_and_setup"] = rec["import_and_setup_ms"]
                for k in ("ax", "clipboard"):
                    for f, val in rec[k]["d"].items():
                        s.d[f"{k}_{f}"] = val
                    s.problems += [f"{k}: {x}" for x in rec[k]["problems"]]
            except Exception as e:
                s.problems.append(f"cold process failed ({p.returncode}): "
                                  f"{type(e).__name__}")
            cold.append(s)
    cohorts["cold_process"] = cohort_doc(
        cold, ["import_and_setup", "ax_worker_exec", "clipboard_worker_exec",
               "ax_validation"],
        "a fresh desktop-isolated process per sample: cold import + setup, "
        "then its FIRST AX and clipboard transactions", warmth="cold")

    native = {"not_run": "not requested (pass --native)"}
    if "--native" in argv:
        native = native_cohorts(scale)

    valid = all(c.get("invalid_samples", 0) == 0 and c.get("n", 0) > 0
                for c in cohorts.values())
    if isinstance(native, dict) and "cohorts" in native:
        for c in native["cohorts"].values():
            if c.get("invalid_samples", 0) or not c.get("n"):
                valid = False
    verdicts = {}
    if valid:
        for name, c in cohorts.items():
            b = c.get("budget")
            if not b:
                verdicts[name] = "reported (no declared budget)"
                continue
            key = "callback" if "callback_p95_ms_max" in b else "enqueue"
            lim = b.get("callback_p95_ms_max", b.get("enqueue_p95_ms_max"))
            p95 = c[key].get("p95_ms")
            verdicts[name] = "pass" if p95 is not None and p95 <= lim \
                else "fail"
        if isinstance(native, dict) and "cohorts" in native:
            for name, c in native["cohorts"].items():
                p95 = c["worker_exec"].get("p95_ms")
                verdicts[name] = ("pass (PROPOSED-M08-B1)"
                                  if p95 is not None
                                  and p95 <= PROPOSED_NATIVE_P95_MS
                                  else "fail (PROPOSED-M08-B1)")
    doc = {
        "schema_version": 2, "milestone": "M08", "kind":
        "insertion-benchmark-work-valid",
        "tool": "scripts/v2/benchmark_m08.py",
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime(t_start)),
        "duration_sec": round(time.time() - t_start, 1),
        "scale": scale, "environment": env,
        "harness": "tests/v2/insertion/m08_world.py (independent world, "
                   "UTF-16 host units, own read/effect/clipboard logs); "
                   "real InsertionService/validation/observer/store; the "
                   "real AppDelegate for ui_* cohorts",
        "budgets": {
            "S24_ui_acknowledgment_p95_ms": S24_UI_P95_MS,
            "PROPOSED-M08-B1_native_ax_transaction_p95_ms":
                PROPOSED_NATIVE_P95_MS,
            "note": "Only the S24 figure is canonical. Fixture (world) "
                    "timings of AX/clipboard internals measure M08's own "
                    "code over a Python double and carry no budget."},
        "injected_delays": {"ui_ax_content_read_sec": UI_DELAY,
                            "settle_inside_consumer_sec": 0.12,
                            "settle_beyond_consumer_sec": 0.45},
        "work_valid": valid, "cohorts": cohorts, "native": native,
        "verdicts": verdicts if valid else None,
    }
    text = json.dumps(doc, indent=1, sort_keys=False)
    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "m08.json").write_text(text + "\n")
    summary_rows = {k: {f: v for f, v in c.items()
                        if isinstance(v, dict) and "p95_ms" in v}
                    for k, c in cohorts.items()}
    print(json.dumps({"work_valid": valid, "verdicts": doc["verdicts"],
                      "invalid": {k: c["problems"]
                                  for k, c in cohorts.items()
                                  if c.get("invalid_samples")}},
                     indent=1))
    del summary_rows
    if not valid:
        print("WORK INVALID: at least one timed sample lacks its witness "
              "— no speed verdict", file=sys.stderr)
        return 2
    return 0 if all(v.startswith("pass") or v.startswith("reported")
                    for v in verdicts.values()) else 1


def native_cohorts(scale):
    """Spawned NATIVELY (not isolated): real AX into the owned helper."""
    import tempfile
    py = str(ROOT / ".venv" / "bin" / "python")
    me = str(pathlib.Path(__file__).resolve())
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
           "HOME": str(pathlib.Path.home()), "PYTHONDONTWRITEBYTECODE": "1"}
    out = {"cohorts": {}, "helper": "benchmark_m08.py --helper (owned, "
           "off-screen, accessory policy, never activated; reached by pid)",
           "keyboard": "none (a post attempt is a failure)",
           "pasteboard": "a private uniquely named NSPasteboard"}
    with tempfile.TemporaryDirectory() as td:
        warm_file = pathlib.Path(td) / "warm.json"
        p = subprocess.run([py, me, "--native-cohort", str(warm_file),
                            str(max(4, int(30 * scale)))],
                           capture_output=True, text=True, timeout=600,
                           env=env, cwd=str(ROOT))
        out["warm_exit"] = p.returncode
        colds = []
        for i in range(max(2, int(6 * scale))):
            f = pathlib.Path(td) / f"cold{i}.json"
            q = subprocess.run([py, me, "--native-cohort", str(f), "1"],
                               capture_output=True, text=True, timeout=300,
                               env=env, cwd=str(ROOT))
            try:
                colds.append(json.loads(f.read_text()))
            except Exception:
                colds.append({"error": f"exit {q.returncode}",
                              "stderr": q.stderr[-300:]})
        try:
            warm = json.loads(warm_file.read_text())
        except Exception:
            return {"not_run": f"native cohort failed (exit {p.returncode})",
                    "stderr": p.stderr[-500:]}
    if warm.get("not_run"):
        return {"not_run": warm["not_run"]}

    def to_samples(recs):
        out_s = []
        for r in recs:
            s = Sample("n", "native")
            s.d = r["d"]
            s.problems = list(r["problems"])
            s.info = {"state": r.get("state"), "astral": r.get("astral")}
            out_s.append(s)
        return out_s
    warm_s = to_samples(warm["samples"][1:])     # first sample = warm-up
    cold_s = []
    for c in colds:
        if "samples" in c and c["samples"]:
            cold_s += to_samples(c["samples"][:1])
        else:
            s = Sample("n", "native")
            s.problems.append(c.get("error") or c.get("not_run") or
                              "no sample")
            cold_s.append(s)
    fields = ["enqueue", "queue_wait", "worker_exec", "validation",
              "pre_read", "ax_write"]
    out["cohorts"]["native_ax"] = cohort_doc(
        warm_s, fields, "real SystemInsertionHost: validation (owned element "
        "+ AXUIElementGetPid) -> AXSelectedText write -> AX readback, into "
        "the helper's NSTextView; AppKit-side text is the witness",
        gate={"worker_exec_p95_ms_max": PROPOSED_NATIVE_P95_MS,
              "source": "PROPOSED-M08-B1 (not canonical)"})
    out["cohorts"]["native_ax_cold"] = cohort_doc(
        cold_s, fields, "the FIRST transaction of a fresh process against a "
        "fresh helper", warmth="cold",
        gate={"worker_exec_p95_ms_max": PROPOSED_NATIVE_P95_MS,
              "source": "PROPOSED-M08-B1 (not canonical)"})
    out["states"] = sorted({str(r.get("state")) for r in warm["samples"]})
    out["astral_samples"] = sum(1 for r in warm["samples"] if r.get("astral"))
    return out


if __name__ == "__main__":
    if "--helper" in sys.argv:
        run_helper(json.loads(sys.argv[sys.argv.index("--helper") + 1]))
        raise SystemExit(0)
    try:
        code = main(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 3
    sys.stdout.flush()
    os._exit(code)
