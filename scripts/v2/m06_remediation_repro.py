"""M06 remediation: reproductions of M06-AUDIT-01..25 against a code root.

Every probe drives REAL production code — ``ContextCollector``,
``ContextSnapshot``, the providers, ``validate_target``/``TargetLease``,
``EvidenceCollector`` + ``Store.publish_example``, ``config.load`` and the
app's hotkey-down → release → finalize → coordinator path — against the
scripted multi-app world of ``tests/v2/context/m06_world.py`` (synthetic
text, paths, credentials and canaries only). The world answers both the
original global-focus host protocol and the job-owned typed protocol, so
the same script runs unchanged on the audited base and on a repaired tree
(``--code-root``).

Run it under the desktop isolation runner — app-level probes construct the
real ``AppDelegate``, whose default collector would otherwise read the live
focused field on a Mac that holds the Accessibility grant:

    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/m06_remediation_repro.py --code-root DIR --output PATH

Concurrency probes force their interleaving with Events/Barriers placed at
host-call boundaries, never with sleeps. Native AX facts are NOT probed
here (``tests/v2/context/test_native_ax.py`` owns them); a probe's result
is a portable observation of the Python logic.

``reproduced: true`` means the defect's failure mechanism was observed on
that code root; ``false`` means the probe ran and did not observe it.
Test-gap and design findings report what the probe measured with
``kind`` set accordingly. Exit code is always 0.
"""

import argparse
import inspect
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import traceback

ap = argparse.ArgumentParser()
ap.add_argument("--code-root",
                default=str(pathlib.Path(__file__).resolve().parents[2]))
ap.add_argument("--output", default=None)
ap.add_argument("--only", default=None)
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
HERE = pathlib.Path(__file__).resolve().parents[2]

sys.path.insert(0, str(CODE))
sys.path.insert(0, str(CODE / "tests" / "v2" / "normalization"))
sys.path.insert(0, str(HERE / "tests" / "v2" / "context"))

from m06_world import (App, WorldHost, AX_CANNOT_COMPLETE,  # noqa: E402
                      CONTENT_ATTRS)
from localflow.v2.context import collector as coll_mod  # noqa: E402
from localflow.v2.context import providers as prov  # noqa: E402
from localflow.v2.context import snapshot as snap_mod  # noqa: E402
from localflow.v2.context.collector import ContextCollector  # noqa: E402

CANARY_A = "CANARY_FIELD_A"
CANARY_B = "CANARY_DENIED_B"


def sink():
    events = []

    def emit(event, level="INFO", **kw):
        events.append((event, json.dumps(kw, default=str)))
        return True
    emit.events = events
    return emit


def field(value, *, token, sel=None, url=None, document=None,
          role="AXTextArea", subrole=None, placeholder=None, **extra):
    f = {"field_token": token, "role": role, "subrole": subrole,
         "value": value, "selected_text_range": sel, "url": url,
         "document": document, "placeholder": placeholder}
    f.update(extra)
    return f


def app_a(**kw):
    return App(101, "com.google.Chrome", "Synthetic Browser A",
               field=field(kw.pop("value", f"alpha {CANARY_A} userId"),
                           token=kw.pop("token", "field-A"),
                           url=kw.pop("url", "https://alpha.example/p?q=1"),
                           sel=kw.pop("sel", [6, 14]), **kw),
               window_title=kw.pop("title", "Compose"), window_token="win-A")


def app_b(**kw):
    return App(202, "com.example.denied", "Synthetic Denied B",
               field=field(f"beta {CANARY_B} secretName",
                           token="field-B", url="https://beta.example/x",
                           sel=[5, 15]),
               window_title=kw.pop("title", "Denied B"), window_token="win-B")


def collector(host, **kw):
    kw.setdefault("emit", sink())
    return ContextCollector(host=host, frontmost=host.frontmost, **kw)


def finalize(c, coll=None, **kw):
    """Call finalize with the handle when the API takes one (repaired
    trees), else the base global-selection API."""
    params = inspect.signature(c.finalize).parameters
    if coll is not None and "coll" in params:
        kw["coll"] = coll
    return c.finalize(**kw)


def wait_done(coll, timeout=5.0):
    ok = coll.done.wait(timeout)
    return bool(ok)


def snap_blob(snap):
    return json.dumps(snap.to_json(), ensure_ascii=False, default=str) \
        if snap is not None else ""


# ---- A01 critical: authority not bound to the AX objects read ------------

def a01():
    out = {}
    # Variant 1: focus moves A -> denied B after the one drift check,
    # before the field provider's focused-element lookup.
    host = WorldHost([app_a(), app_b()], focus_pid=101)
    c = collector(host, denied_apps=("com.example.denied",))

    def after_first_frontmost(n):
        # capture_identity is frontmost call 1, the drift check call 2:
        # switch right after the drift check returns (before any read).
        if n == 3:
            pass
    host.hooks["frontmost"] = after_first_frontmost
    t = c.capture_identity()
    orig_changed = c._destination_changed

    def changed_then_switch(target):
        r = orig_changed(target)
        host.switch(202)                 # system focus + frontmost -> B
        return r
    c._destination_changed = changed_then_switch
    coll = c.begin(t)
    wait_done(coll)
    snap = finalize(c, coll, target_snapshot_id=t.target_snapshot_id)
    b_reads = host.reads_of(202)
    out["v1_focus_switch_before_field"] = {
        "target_app": t.app_bundle, "target_denied": t.denied,
        "b_content_reads": len(b_reads),
        "b_attrs_read": sorted({r[2] for r in b_reads}),
        "b_canary_in_snapshot": CANARY_B in snap_blob(snap),
    }
    # Variant 2: A field completes, then focus moves to B before the
    # window/origin lookups -> hybrid snapshot.
    host2 = WorldHost([app_a(), app_b()], focus_pid=101)
    c2 = collector(host2)
    t2 = c2.capture_identity()
    real_read_field = prov.read_field

    def field_then_switch(*a, **k):
        r = real_read_field(*a, **k)
        host2.switch(202)
        return r
    prov.read_field = field_then_switch
    try:
        coll2 = c2.begin(t2)
        wait_done(coll2)
    finally:
        prov.read_field = real_read_field
    snap2 = finalize(c2, coll2, target_snapshot_id=t2.target_snapshot_id)
    blob2 = snap_blob(snap2)
    out["v2_switch_after_field"] = {
        "a_field_canary": CANARY_A in blob2,
        "b_origin": snap2.site_origin if snap2 else None,
        "window_title": snap2.window_title if snap2 else None,
        "b_reads": len(host2.reads_of(202)),
        "hybrid": (CANARY_A in blob2 and (
            (snap2.site_origin or "").startswith("https://beta")
            or snap2.window_title == "Denied B")),
    }
    out["reproduced"] = bool(
        out["v1_focus_switch_before_field"]["b_content_reads"]
        or out["v1_focus_switch_before_field"]["b_canary_in_snapshot"]
        or out["v2_switch_after_field"]["hybrid"]
        or out["v2_switch_after_field"]["b_reads"])
    return out


# ---- A02 cache cannot distinguish equal-title destinations ---------------

def a02():
    out = {}
    a1 = app_a()
    host = WorldHost([a1], focus_pid=101)
    c = collector(host)
    t = c.capture_identity()
    coll = c.begin(t)
    wait_done(coll)
    s1 = finalize(c, coll, target_snapshot_id=t.target_snapshot_id)
    # Same pid/title/role; the tab now shows another site and another
    # field object (new field/window tokens).
    a1.field = field("beta page userId", token="field-A2",
                     url="https://beta.example/q", sel=[0, 4])
    a1.window_token = "win-A2"
    n_before = len(host.calls)
    t2 = c.capture_identity()
    coll2 = c.begin(t2)
    wait_done(coll2)
    s2 = finalize(c, coll2, target_snapshot_id=t2.target_snapshot_id)
    url_reads_2 = [x for x in host.calls[n_before:] if x[2] == "AXURL"]
    out.update({
        "first_origin": s1.site_origin, "second_origin": s2.site_origin,
        "second_origin_source": s2.origin_source,
        "second_capture_read_url": bool(url_reads_2),
    })
    # Workspace variant: equal title/role, different document path.
    w = App(303, "com.microsoft.VSCode", "Synthetic IDE",
            field=field("x", token="f1", role="AXTextArea",
                        document="file:///Synthetic/alpha/a.py"),
            window_title="a.py", window_token="w1")
    host3 = WorldHost([w], focus_pid=303)
    c3 = collector(host3)
    t3 = c3.capture_identity()
    k = c3.begin(t3)
    wait_done(k)
    finalize(c3, k, target_snapshot_id=t3.target_snapshot_id)
    w.field = field("x", token="f2", role="AXTextArea",
                    document="file:///Synthetic/beta/a.py")
    w.window_token = "w2"
    t4 = c3.capture_identity()
    k4 = c3.begin(t4)
    wait_done(k4)
    s4 = finalize(c3, k4, target_snapshot_id=t4.target_snapshot_id)
    out["workspace_second"] = s4.workspace
    out["reproduced"] = (s2.site_origin == "https://alpha.example"
                         or s4.workspace == "alpha")
    return out


# ---- A03 same_destination absent/contradictory identity ------------------

def a03():
    T = snap_mod.TargetSnapshot
    C = snap_mod.ContextSnapshot

    def snap(pid, bundle):
        return C(context_snapshot_id="ctx-x", stage="pre_decode",
                 target=T(target_snapshot_id="tgt-x", app_pid=pid,
                          app_bundle=bundle))
    rows = {
        "absent_vs_nameonly": snap(None, None).same_destination(
            {"name": "Synthetic B"}),
        "same_pid_conflicting_bundle": snap(101, "synthetic.a")
        .same_destination({"pid": 101, "bundle": "synthetic.b"}),
        "bundle_only_absent_vs_absent": snap(None, None).same_destination(
            {"pid": None, "bundle": None}),
        "control_same": snap(101, "synthetic.a").same_destination(
            {"pid": 101, "bundle": "synthetic.a"}),
        "control_other_pid": snap(101, "synthetic.a").same_destination(
            {"pid": 202, "bundle": "synthetic.a"}),
    }
    # The M08 consumer rows: the inline TargetSnapshot branch and the
    # lease re-check.
    from localflow.v2.insertion import validation as val
    from localflow.v2.insertion.target_lease import TargetLease

    class H:
        def __init__(self, fm):
            self.fm = fm

        def frontmost(self):
            return self.fm

        def focused_element(self):
            return None

        def attribute(self, el, name):
            return None
    tgt = T(target_snapshot_id="tgt-y", app_pid=None, app_bundle=None)
    lease, ver = val.validate_target(H({"name": "Synthetic B"}), tgt,
                                     {"job_id": "job-x"})
    rows["m08_target_snapshot_absent_identity"] = ver.get("identity")
    tl = TargetLease(job_id="j", attempt=1, target_snapshot_id=None,
                     context_snapshot_id=None, frontmost_pid=None,
                     frontmost_bundle=None)
    rows["m08_lease_absent_identity"] = tl.identity_matches(
        {"name": "Synthetic B"})
    reproduced = bool(rows["absent_vs_nameonly"]
                      or rows["same_pid_conflicting_bundle"]
                      or rows["bundle_only_absent_vs_absent"])
    return {"rows": rows, "reproduced": reproduced,
            "controls_ok": rows["control_same"] is True
            and rows["control_other_pid"] is False}


# ---- A04 native boundary masked by test doubles (portable half) ----------

def a04():
    out = {}
    # 1. A REAL native AXValue CFRange (AXValueCreate needs no
    #    Accessibility grant) through the code root's range decoder.
    import ApplicationServices as AS
    value = AS.AXValueCreate(AS.kAXValueCFRangeType, (1, 2))
    decode = getattr(prov, "ax_range", None)
    got = decode(value) if decode is not None else prov._as_range(value)
    out["as_range_native_description"] = list(got) if got else [None, None]
    # 2. base focused_window asks the FIELD element for AXFocusedWindow
    #    (measured natively: kAXErrorAttributeUnsupported on a text view).
    src = inspect.getsource(prov.SystemAXHost)
    out["system_host_window_attr_on_field"] = \
        'attribute(el, "AXFocusedWindow")' in src
    out["system_host_raw_cfrange"] = "CFRange(start, length)" in src
    out["reproduced"] = (out["as_range_native_description"] != [1, 2]
                         or out["system_host_window_attr_on_field"]
                         or out["system_host_raw_cfrange"])
    out["native_evidence"] = "tests/v2/context/test_native_ax.py"
    return out


# ---- A05 nested mutability beneath a fixed id ----------------------------

def a05():
    d = {
        "context_snapshot_id": "ctx-fixed", "stage": "pre_decode",
        "target": {"target_snapshot_id": "tgt-1", "app_bundle": "a.b",
                   "app_pid": 1},
        "field": {"classification": "text", "selected_range": [1, 2],
                  "selected_text": "x"},
        "identifiers": {"user id": "userId"},
        "providers": [{"name": "focused_field", "status": "ok"}],
        "omissions": [{"field": "workspace", "reason": "not_exposed"}],
    }
    s = snap_mod.ContextSnapshot.from_json(d)
    before = json.dumps(s.to_json(), sort_keys=True)
    env_before = json.dumps(s.to_envelope_block(), sort_keys=True)
    d["identifiers"]["user id"] = "CANARY_MUTATED"
    d["providers"][0]["status"] = "CANARY_STATUS"
    d["omissions"][0]["reason"] = "CANARY_REASON"
    after_caller = json.dumps(s.to_json(), sort_keys=True)
    direct = None
    try:
        s.identifiers["injected"] = "x"
        direct = "mutated"
    except TypeError:
        direct = "refused"
    try:
        s.providers[0]["status"] = "CANARY2"
        prov_direct = "mutated"
    except TypeError:
        prov_direct = "refused"
    out_json = s.to_json()
    out_json["identifiers"]["detached"] = "y"
    detached_ok = "detached" not in json.dumps(s.to_json())
    after = json.dumps(s.to_json(), sort_keys=True)
    env_after = json.dumps(s.to_envelope_block(), sort_keys=True)
    return {
        "id": s.context_snapshot_id,
        "caller_mutation_changed_bytes": before != after_caller,
        "direct_identifiers_mutation": direct,
        "direct_provider_row_mutation": prov_direct,
        "to_json_detached": detached_ok,
        "bytes_changed_total": before != after,
        "envelope_changed": env_before != env_after,
        "reproduced": before != after_caller or direct == "mutated"
        or prov_direct == "mutated" or env_before != env_after,
    }


# ---- A06 abandon/cancel/delete/shutdown do not revoke handles ------------

def a06():
    out = {}
    gate = threading.Event()
    entered = threading.Event()
    host = WorldHost([app_a()], focus_pid=101)

    def block_origin(n):
        entered.set()
        gate.wait(5)
    c = collector(host)
    t = c.capture_identity()
    real = prov.read_site_origin

    def slow_origin(*a, **k):
        block_origin(0)
        return real(*a, **k)
    prov.read_site_origin = slow_origin
    try:
        coll = c.begin(t)
        entered.wait(5)
        reads_before = len(host.calls)
        revoke = getattr(c, "revoke", None)
        if revoke is not None:
            revoke(coll, reason="cancelled")
        else:
            c.abandon()
        gate.set()
        wait_done(coll)
    finally:
        prov.read_site_origin = real
    reads_after = host.calls[reads_before:]
    late = c.take_downstream(coll)
    out["abandon"] = {
        "api": "revoke" if revoke is not None else "abandon",
        "content_reads_after_revocation": len(
            [r for r in reads_after if r[2] in CONTENT_ATTRS]),
        "downstream_after_revocation": late is not None,
        "thread_alive_after": coll.thread.is_alive(),
    }
    # Admission: several blocked collections at once.
    gate2 = threading.Event()
    host2 = WorldHost([app_a()], focus_pid=101)

    def slow_field(*a, **k):
        gate2.wait(5)
        return prov.ProviderResult("focused_field")
    real_f = prov.read_field
    prov.read_field = slow_field
    try:
        c2 = collector(host2)
        colls = []
        for _ in range(12):
            tt = c2.capture_identity()
            colls.append(c2.begin(tt))
        alive = sum(1 for k in colls if k is not None
                    and k.thread.is_alive())
        shutdown = getattr(c2, "shutdown", None)
        if shutdown is not None:
            shutdown()
        after_shutdown = c2.begin(c2.capture_identity()) \
            if c2.enabled else None
        gate2.set()
        for k in colls:
            if k is not None:
                wait_done(k)
    finally:
        prov.read_field = real_f
    out["admission"] = {"blocked_collections_admitted": alive,
                        "shutdown_api": shutdown is not None,
                        "begin_after_shutdown_accepted":
                            after_shutdown is not None}
    # App wiring: do cancel/delete/quit reach the collection handle?
    app_src = (CODE / "localflow" / "app.py").read_text()
    import re
    def body(name):
        m = re.search(rf"def {name}\(self[^)]*\):(.*?)\n    def ", app_src,
                      re.S)
        return m.group(1) if m else ""
    out["app_paths_touch_context"] = {
        n: any(s in body(n) for s in ("context_coll", "_context.",
                                      "_revoke_context", "\"shutdown\""))
        for n in ("cancelDictation", "_on_job_deleted",
                  "applicationWillTerminate_")}
    out["reproduced"] = bool(
        out["abandon"]["content_reads_after_revocation"]
        or out["abandon"]["downstream_after_revocation"]
        or out["admission"]["blocked_collections_admitted"] > 4
        or not all(out["app_paths_touch_context"].values()))
    return out


# ---- app harness helpers --------------------------------------------------

def app_harness(asr_text, host, *, cfg=None, deadline_ms=75.0):
    from test_normalization_pipeline import Harness, RecordingSupervisor
    sup = RecordingSupervisor(asr_text)
    h = Harness([1.0], cfg=cfg or {}, supervisor=sup)
    if host is not None:
        h.d._context = ContextCollector(
            enabled=True, deadline_ms=deadline_ms, emit=sink(), host=host,
            frontmost=host.frontmost)
    return h, sup


# ---- A07 release clock starts after the release-path work ----------------

def a07():
    import localflow.app as app_mod
    host = WorldHost([app_a()], focus_pid=101)
    h, _ = app_harness("twelve percent", host)
    delay = 0.2
    real = app_mod.AppDelegate._finalize_job_context

    def slow(self, job):
        time.sleep(delay)            # injected, known release-path work
        return real(self, job)
    app_mod.AppDelegate._finalize_job_context = slow
    try:
        h.hk.held = True
        h.hk.on_press()
        time.sleep(0.05)
        h.hk.held = False
        t_release = time.monotonic()
        h.hk.on_release()
        job = h.d._active_jobs[-1]
    finally:
        app_mod.AppDelegate._finalize_job_context = real
    released = job.get("released_mono")
    gap_ms = (released - t_release) * 1000.0 if released else None
    h.run_coordinator()
    h.close()
    return {"injected_delay_ms": delay * 1000,
            "release_event_to_released_mono_ms": round(gap_ms, 3)
            if gap_ms is not None else None,
            "clock_excludes_injected_delay":
                gap_ms is not None and gap_ms >= delay * 1000 * 0.9,
            "reproduced": gap_ms is not None
            and gap_ms >= delay * 1000 * 0.9}


# ---- A08 benchmark_m06 false green ---------------------------------------

def a08_schema2(src):
    """The repaired (schema 2) harness: are the validity mechanics the
    audit asked for present, and does a small run pass them? (Whether
    they REJECT broken work is the mutation check's benchmark mutants.)"""
    rel = src.split("def release(")[1].split("\n    def ")[0] \
        if "def release(" in src else ""
    checks = {
        "off_arm_zero_ax_oracle": "off.host.calls == []" in src,
        "clock_starts_before_release_event":
            rel.find("t0 = time.perf_counter()")
            < rel.find("hk.on_release()") != -1,
        "injected_delay_conservation_gate": "conserved" in src
        and "the release clock does not cover" in src,
        "authored_eligible_set_oracle": "picked == rig.eligible_on" in src,
        "workspace_widening_required": "release_on: workspace not" in src,
        "packaging_inside_measured_path": "hint_set_artifact is not None"
        in src,
        "separate_exit_codes": '"work_invalid", 2' in src
        and '"budget_failed", 1' in src,
    }
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        iso = HERE / "tests" / "v2" / "context" / "run_isolated.py"
        p = subprocess.run(
            [sys.executable, str(iso),
             str(CODE / "scripts" / "v2" / "benchmark_m06.py"), td,
             "--entries", "500", "--reps", "3"],
            cwd=str(CODE), capture_output=True, text=True, timeout=900)
        try:
            rep = json.loads((pathlib.Path(td) / "m06.json").read_text())
        except Exception:
            rep = {}
    run = {"exit": p.returncode, "verdict": rep.get("verdict"),
           "problems": rep.get("problems"),
           "injected_delay": (rep.get("cohorts") or {}).get(
               "injected_delay_control")}
    return {"schema": 2, "checks": checks, "small_run": run,
            "reproduced": not all(checks.values())
            or run["verdict"] != "pass"}


def a08():
    src = (CODE / "scripts" / "v2" / "benchmark_m06.py").read_text()
    out = {}
    if "def pipeline_delta" not in src:
        return a08_schema2(src)
    # Execute the benchmark's own pipeline_delta arms with an instrumented
    # host to count AX reads in the "off" arm.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bench_m06_probe", CODE / "scripts" / "v2" / "benchmark_m06.py")
    mod = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, [str(spec.origin)]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    reads = {"n": 0}
    real_host = mod.FakeAXHost

    class CountingHost(real_host):
        def attribute(self, el, name):
            reads["n"] += 1
            return super().attribute(el, name)
    if hasattr(mod, "pipeline_delta"):
        mod.FakeAXHost = CountingHost
        import test_normalization_pipeline as tnp
        # Only the off arm: context_enabled False.
        h = tnp.Harness([1.0], cfg={"context_enabled": False},
                        supervisor=tnp.RecordingSupervisor("x"))
        s = mod.SCENARIOS["LF-CTX-010"]
        # Mirror the benchmark's one(): it installs an ENABLED collector.
        h.d._context = ContextCollector(
            enabled=True, deadline_ms=75.0, emit=lambda *a, **k: None,
            host=CountingHost(s), frontmost=lambda: s["frontmost"])
        h.press_release()
        h.run_coordinator()
        h.close()
        mod.FakeAXHost = real_host
        out["off_arm_ax_reads"] = reads["n"]
        body = inspect.getsource(mod.pipeline_delta)
        out["off_arm_installs_enabled_collector"] = \
            "enabled=True" in body and "context_enabled\": False" in body
        out["timer_starts_after_press_release"] = \
            body.index("h.press_release()") < body.index("t0 = ")
    scope_body = inspect.getsource(mod.scope_upgrade_cost) \
        if hasattr(mod, "scope_upgrade_cost") else ""
    out["warm_scope_is_tuple_equality"] = "hit = key ==" in scope_body
    out["scope_entries_global_only"] = "scope_kind" not in scope_body
    out["scope_cost_gates_exit"] = "scope_upgrade" in src.split(
        "def main")[-1].split("return 0 if ok")[0].split("ok =")[-1] \
        if "ok =" in src else None
    out["reproduced"] = bool(out.get("off_arm_ax_reads")
                             or out.get("timer_starts_after_press_release")
                             or out["warm_scope_is_tuple_equality"])
    return out


# ---- A09 selection retention has no cap ----------------------------------

def a09():
    big = "S" * 2_000_000
    a = App(101, "com.apple.TextEdit", "Synthetic Editor",
            field=field("pre " + big + " post", token="f",
                        sel=[4, len(big)], selected_text=big),
            window_title="doc", window_token="w")
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t = c.capture_identity()
    k = c.begin(t)
    wait_done(k, 20)
    s = finalize(c, k, target_snapshot_id=t.target_snapshot_id)
    sel_len = len(s.field.selected_text or "") if s and s.field else 0
    blob_len = len(snap_blob(s))
    # Oversized host return for a 600-character flank request.
    a2 = App(102, "com.apple.TextEdit", "Synthetic Editor",
             field=field("x" * 50 + "userId", token="g", sel=[20, 0]),
             window_title="doc2", window_token="w2")
    host2 = WorldHost([a2], focus_pid=102)
    host2.oversize["AXStringForRange"] = " ".join(
        f"fooBar{i}" for i in range(50_000))
    c2 = collector(host2)
    t2 = c2.capture_identity()
    k2 = c2.begin(t2)
    wait_done(k2, 20)
    s2 = finalize(c2, k2, target_snapshot_id=t2.target_snapshot_id)
    pre_len = len(s2.field.preceding_text or "") if s2 and s2.field else 0
    # Negative / inconsistent range.
    a3 = App(103, "com.apple.TextEdit", "Synthetic Editor",
             field=field("short", token="h", sel=[-5, 3]),
             window_title="d3", window_token="w3")
    host3 = WorldHost([a3], focus_pid=103)
    c3 = collector(host3)
    t3 = c3.capture_identity()
    k3 = c3.begin(t3)
    wait_done(k3)
    s3 = finalize(c3, k3, target_snapshot_id=t3.target_snapshot_id)
    return {
        "selected_text_retained_chars": sel_len,
        "snapshot_json_chars": blob_len,
        "oversized_flank_retained_chars": pre_len,
        "negative_range_recorded": list(s3.field.selected_range)
        if s3 and s3.field and s3.field.selected_range else None,
        "reproduced": sel_len >= 2_000_000 or pre_len > prov.NEARBY_CHARS,
    }


# ---- A10 privacy config coercion -----------------------------------------

def a10():
    rows = {}
    c = ContextCollector(enabled="false", host=WorldHost([], focus_pid=0),
                         frontmost=lambda: None)
    rows["enabled_string_false"] = c.enabled
    c2 = ContextCollector(denied_apps="com.google.Chrome",
                          host=WorldHost([], focus_pid=0),
                          frontmost=lambda: None)
    rows["denied_string_is_chrome_denied"] = \
        "com.google.Chrome" in c2.denied_apps
    rows["denied_string_members"] = len(c2.denied_apps)
    try:
        c3 = ContextCollector(deadline_ms=float("inf"),
                              host=WorldHost([], focus_pid=0),
                              frontmost=lambda: None)
        rows["deadline_inf_accepted"] = c3.deadline_ms
    except Exception as e:
        rows["deadline_inf_accepted"] = f"refused:{type(e).__name__}"
    # The app's own configuration path.
    host = WorldHost([app_a()], focus_pid=101)
    h, _ = app_harness("x", None, cfg={
        "context_enabled": "false", "training_retain_context": "false",
        "context_denied_apps": "com.google.Chrome",
        "context_deadline_ms": 1e12})
    ctx = h.d._context
    rows["app_context_enabled"] = getattr(ctx, "enabled", None) \
        if ctx is not None else None
    rows["app_retain_context"] = h.d.collector.retain_context
    rows["app_chrome_denied"] = (ctx is not None and "com.google.Chrome"
                                 in getattr(ctx, "denied_apps", ()))
    rows["app_deadline_ms"] = getattr(ctx, "deadline_ms", None) \
        if ctx is not None else None
    h.close()
    del host
    rep = bool(rows["enabled_string_false"] is True
               or rows["app_context_enabled"] is True
               or rows["app_retain_context"] is True
               or (ctx is not None and rows["app_context_enabled"]
                   and not rows["app_chrome_denied"]))
    return {"rows": rows, "reproduced": rep}


# ---- A11 finalize global selection / concurrent idempotence -------------

def a11():
    out = {}
    host = WorldHost([app_a()], focus_pid=101)
    c = collector(host)
    ta = c.capture_identity()
    ka = c.begin(ta)
    tb = c.capture_identity()
    kb = c.begin(tb)
    wait_done(ka)
    wait_done(kb)
    sa = finalize(c, ka, target_snapshot_id=ta.target_snapshot_id)
    out["older_handle_finalize_after_new_begin"] = (
        sa.target.target_snapshot_id if sa is not None else None)
    out["older_lost"] = sa is None
    # Omitted target id with a mismatched job id: which handle answers?
    sx = finalize(c, None, job_id="job-OTHER")
    out["omitted_target_returns"] = (sx.target.target_snapshot_id
                                     if sx is not None else None)
    # Two finalizers of one handle, both past the first snapshot check.
    host2 = WorldHost([app_a()], focus_pid=101)
    c2 = collector(host2)
    t2 = c2.capture_identity()
    k2 = c2.begin(t2)
    wait_done(k2)
    barrier = threading.Barrier(2, timeout=5)
    real_wait = k2.done.wait

    def wait_both(timeout=None):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return real_wait(timeout)
    k2.done.wait = wait_both
    ids_seen = []

    def run():
        s = finalize(c2, k2, target_snapshot_id=t2.target_snapshot_id)
        ids_seen.append(s.context_snapshot_id if s is not None else None)
    th = [threading.Thread(target=run) for _ in range(2)]
    for x in th:
        x.start()
    for x in th:
        x.join(5)
    out["concurrent_ids"] = ids_seen
    out["distinct_ids"] = len(set(i for i in ids_seen if i))
    out["reproduced"] = bool(out["older_lost"]
                             or out["distinct_ids"] > 1
                             or out["omitted_target_returns"] is not None)
    return out


# ---- A12 downstream clearing / wrong dependency bucket -------------------

def a12():
    out = {}
    host = WorldHost([app_a()], focus_pid=101)
    c = collector(host, deadline_ms=10)
    t = c.capture_identity()
    g_field, g_origin, g_ws = (threading.Event(), threading.Event(),
                               threading.Event())
    real_f, real_o, real_w = (prov.read_field, prov.read_site_origin,
                              prov.read_workspace)

    def f(*a, **k):
        g_field.wait(5)
        return real_f(*a, **k)

    def o(*a, **k):
        g_origin.wait(5)
        return real_o(*a, **k)

    def w(*a, **k):
        g_ws.wait(5)
        return real_w(*a, **k)
    prov.read_field, prov.read_site_origin, prov.read_workspace = f, o, w
    try:
        k = c.begin(t)
        s = finalize(c, k, target_snapshot_id=t.target_snapshot_id)
        g_field.set()
        # wait for the field to land in the late bucket
        for _ in range(200):
            if getattr(k, "late", {}) or getattr(k, "_late", {}):
                break
            time.sleep(0.005)
        d1 = c.take_downstream(k)
        g_origin.set()
        g_ws.set()
        wait_done(k)
        d2 = c.take_downstream(k)
    finally:
        prov.read_field, prov.read_site_origin, prov.read_workspace = \
            real_f, real_o, real_w
    out["pre_decode_partial"] = bool(s and s.partial)
    out["first_downstream"] = [p["name"] for p in (d1.providers if d1
                               else ()) if p["status"] == "ok"]
    out["second_downstream"] = d2 is not None
    out["second_downstream_ok_providers"] = [
        p["name"] for p in (d2.providers if d2 else ())
        if p["status"] == "ok"]
    # Late field document feeding workspace derivation.
    ide = App(303, "com.apple.TextEdit", "Synthetic Editor",
              field=field("x", token="t", document=
                          "file:///Synthetic/alpha/a.py"),
              window_title="untitled", window_token="w")
    host2 = WorldHost([ide], focus_pid=303)
    c2 = collector(host2, deadline_ms=10)
    t2 = c2.capture_identity()
    gate = threading.Event()

    def f2(*a, **k):
        gate.wait(5)
        return real_f(*a, **k)
    prov.read_field = f2
    try:
        k2 = c2.begin(t2)
        finalize(c2, k2, target_snapshot_id=t2.target_snapshot_id)
        gate.set()
        wait_done(k2)
        d = c2.take_downstream(k2)
    finally:
        prov.read_field = real_f
    out["late_field_workspace"] = d.workspace if d is not None else None
    out["reproduced"] = bool(out["second_downstream"]
                             or out["late_field_workspace"] != "alpha")
    return out


# ---- A13 provider status honesty -----------------------------------------

def a13():
    out = {}
    a = app_a(url=None)             # no AXURL, no title domain -> omitted
    a.window_title = "Compose"
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    rows = []
    for _ in range(2):
        t = c.capture_identity()
        k = c.begin(t)
        wait_done(k)
        s = finalize(c, k, target_snapshot_id=t.target_snapshot_id)
        rows.append({p["name"]: p for p in s.providers}["site_origin"])
    out["origin_rows"] = rows
    out["cached_absence_ok"] = (rows[1]["status"] == "ok"
                                and rows[0]["status"] != "ok")
    # Window lookup failure after a successful field read.
    host2 = WorldHost([app_a()], focus_pid=101)
    host2.raise_on["focused_window"] = RuntimeError("synthetic")
    host2.raise_on["window_of"] = RuntimeError("synthetic")
    c2 = collector(host2)
    t2 = c2.capture_identity()
    k2 = c2.begin(t2)
    wait_done(k2)
    s2 = finalize(c2, k2, target_snapshot_id=t2.target_snapshot_id)
    fr = {p["name"]: p for p in s2.providers}["focused_field"]
    out["field_row_after_window_failure"] = fr
    out["field_value_present"] = s2.field is not None \
        and s2.field.classification == "text"
    out["populated_field_labeled_failed"] = (
        fr.get("reason") == coll_mod.OMISSION_PROVIDER
        and out["field_value_present"])
    # Native error classes flattened: a failed subrole read vs absent.
    host3 = WorldHost([App(104, "com.apple.TextEdit", "E", field=field(
        "abc", token="z", role="AXTextField",
        subrole_error=AX_CANNOT_COMPLETE), window_title="t")],
        focus_pid=104)
    c3 = collector(host3)
    t3 = c3.capture_identity()
    k3 = c3.begin(t3)
    wait_done(k3)
    s3 = finalize(c3, k3, target_snapshot_id=t3.target_snapshot_id)
    out["failed_subrole_classification"] = (
        s3.field.classification if s3.field else None)
    out["failed_subrole_content_read"] = bool(
        [r for r in host3.calls if r[2] in ("AXSelectedText",
                                            "AXStringForRange")])
    out["reproduced"] = bool(out["cached_absence_ok"]
                             or out["populated_field_labeled_failed"]
                             or out["failed_subrole_content_read"])
    return out


# ---- A14 origin userinfo / title false positives -------------------------

def a14():
    cases = {
        "userinfo": "https://synthetic-user:CANARY_URL_CRED@alpha.example/p",
        "port": "https://alpha.example:8443/x",
        "javascript": "javascript:alert(1)",
        "file": "file:///Synthetic/a.txt",
    }
    url_rows = {k: prov._url_origin(v) for k, v in cases.items()}
    titles = {"upper_ext": "foo.com.TXT", "email": "author@alpha.example",
              "version": "Version 3.14", "control": "alpha.example — Inbox"}
    title_rows = {}
    for k, v in titles.items():
        a = App(101, "com.google.Chrome", "B", field=field(
            "x", token="f", url=None), window_title=v, window_token="w")
        host = WorldHost([a], focus_pid=101)
        el = host.focused_element_for(101)
        params = inspect.signature(prov.read_site_origin).parameters
        if "el" in params:
            r = prov.read_site_origin(host, "browser", v, el=el)
        else:
            r = prov.read_site_origin(host, "browser", v)
        title_rows[k] = [r.value, r.provenance]
    return {"url": url_rows, "title": title_rows,
            "reproduced": bool(
                (url_rows["userinfo"] or "").find("CANARY") >= 0
                or title_rows["upper_ext"][0] is not None
                or title_rows["email"][0] is not None)}


# ---- A15 optimistic retention metadata ------------------------------------

def a15():
    from localflow.v2 import store as store_mod
    out = {}
    for failpoint in ("artifact_insert", "lease_insert"):
        host = WorldHost([app_a()], focus_pid=101)
        h, _ = app_harness("twelve percent", host)
        h.d.consent.set("enabled", note="m06 repro")
        real_ins = store_mod.insert_text_artifact_row
        real_lease = store_mod.grant_lease_row

        def bad_ins(db, **kw):
            if kw.get("role") == "context_snapshot":
                raise RuntimeError("synthetic writer failure")
            return real_ins(db, **kw)
        ctx_art = {}

        def bad_lease(db, artifact_id, holder, **kw):
            if artifact_id in ctx_art.values():
                raise RuntimeError("synthetic lease failure")
            return real_lease(db, artifact_id, holder, **kw)
        real_write = h.d.store.write_text_artifact

        def spy_write(**kw):
            aid = real_write(**kw)
            if kw.get("role") == "context_snapshot":
                ctx_art[kw.get("stage")] = aid
            return aid
        h.d.store.write_text_artifact = spy_write
        if failpoint == "artifact_insert":
            store_mod.insert_text_artifact_row = bad_ins
        else:
            store_mod.grant_lease_row = bad_lease
        try:
            h.press_release()
            fn, args = h.run_coordinator()
            text, job = args
            h.d._finishWithText_(text, job)
            h.d.store.sync()
        finally:
            store_mod.insert_text_artifact_row = real_ins
            store_mod.grant_lease_row = real_lease
        st = h.d.store
        latest = st.latest_example()
        env = st.latest_revision(latest[0]) if latest else None
        dest = (env or {}).get("context", {}).get("destination") or {}
        aid = ctx_art.get("pre_decode_context")
        leases = st.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM artifact_leases WHERE artifact_id=?",
            (aid,)).fetchone()[0]) if aid else None
        row = st.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM artifacts WHERE artifact_id=?",
            (aid,)).fetchone()[0]) if aid else None
        out[failpoint] = {
            "envelope_retained": dest.get("retained"),
            "envelope_artifact_id": dest.get("artifact_id"),
            "artifact_rows": row, "lease_rows": leases,
            "missing_reasons": sorted(((env or {}).get("missing_reasons")
                                       or {}).keys()),
            "completeness": (env or {}).get("completeness"),
        }
        h.close()
    ai, li = out["artifact_insert"], out["lease_insert"]
    out["reproduced"] = bool(
        (ai["envelope_retained"] is True and not ai["artifact_rows"])
        or (li["envelope_retained"] is True and not li["lease_rows"]))
    return out


# ---- A16 engine-context seam coupled to vocabulary -----------------------

def a16():
    import localflow.app as app_mod
    from localflow.v2 import vocabulary as vocab_mod
    out = {}
    host = WorldHost([App(101, "com.microsoft.VSCode", "IDE", field=field(
        "call userId then fooBar", token="f", sel=[5, 0],
        document="file:///Synthetic/alpha/a.py"), window_title="a.py",
        window_token="w")], focus_pid=101)
    h, _ = app_harness("user id", host)
    h.d._vocab = None                   # vocabulary subsystem unavailable
    h.press_release()
    job = h.d._active_jobs[-1]
    snap = job.get("context_snapshot")
    nc = job.get("norm_context")
    out["no_vocab"] = {
        "snapshot_identifiers": len(snap.identifiers or {}) if snap else None,
        "engine_identifiers": len(getattr(nc, "identifiers", None) or {})
        if nc is not None else None,
        "engine_destination": getattr(nc, "destination_app", None)
        if nc is not None else None,
    }
    h.run_coordinator()
    h.close()
    # Failure inside the upgrade: which authorities end up mixed?
    host2 = WorldHost([App(101, "com.microsoft.VSCode", "IDE", field=field(
        "call userId", token="f", sel=[5, 0],
        document="file:///Synthetic/alpha/a.py"), window_title="a.py",
        window_token="w")], focus_pid=101)
    h2, _ = app_harness("user id", host2)
    h2.d._vocab.add_entry("Servo", ["survo"], approved=True,
                          scope_kind="workspace", scope_value="alpha")
    real_vs = vocab_mod.VocabularySnapshot
    calls = {"n": 0}

    class FailingVS(real_vs):
        # Fails ONLY the widened (workspace) rebuild; the hotkey-down
        # app-scope snapshot is built normally.
        def __init__(self, entries, scope=None, *a, **k):
            calls["n"] += 1
            if scope is not None and getattr(scope, "workspace", None):
                raise RuntimeError("synthetic upgrade failure")
            super().__init__(entries, scope, *a, **k)
    vocab_mod.VocabularySnapshot = FailingVS
    events = []
    real_emit = h2.d.v2log.emit

    def spy(event, **kw):
        events.append([event, kw.get("outcome"), kw.get("reason_code")])
        return real_emit(event, **kw)
    h2.d.v2log.emit = spy
    try:
        h2.press_release()
    finally:
        vocab_mod.VocabularySnapshot = real_vs
    job2 = h2.d._active_jobs[-1]
    snap2 = job2.get("context_snapshot")
    nc2 = job2.get("norm_context")
    vocab2 = getattr(nc2, "vocabulary", None)
    out["upgrade_failure"] = {
        "failing_constructor_calls": calls["n"],
        "events": [e for e in events if e[0].startswith(
            ("vocabulary", "context", "profiles"))],
        "finalized_workspace": snap2.workspace if snap2 else None,
        "resolved_profile": job2["m10"]["wp"].profile_name
        if job2.get("m10") else None,
        "hint_set_id": getattr(job2.get("hint_set"), "hint_set_id", None),
        "context_snapshot_finalized": snap2 is not None,
        "engine_identifiers": len(getattr(nc2, "identifiers", None) or {})
        if nc2 is not None else None,
        "vocabulary_scope_workspace": getattr(getattr(
            vocab2, "scope_ctx", None), "workspace", None),
        "scope_upgraded_flag": job2.get("scope_upgraded"),
        "explicit_downgrade_recorded": any(
            k for k in job2 if "downgrade" in str(k)
            or "scope_disposition" in str(k)),
    }
    h2.run_coordinator()
    h2.close()
    nv = out["no_vocab"]
    uf = out["upgrade_failure"]
    # Observation (not the verdict): the finalized destination's engine
    # identifiers ride beside the hotkey-down vocabulary scope after a
    # failed widening, with no recorded disposition naming that mix.
    uf["mixed_tuple_observed"] = bool(
        uf["engine_identifiers"] and uf["finalized_workspace"]
        and not uf["vocabulary_scope_workspace"]
        and not uf["explicit_downgrade_recorded"])
    out["reproduced"] = bool(nv["snapshot_identifiers"]
                             and not nv["engine_identifiers"])
    return out


# ---- A17..A21 test gaps: measured coverage, not defects -------------------

def _read(rel):
    p = CODE / rel
    return p.read_text() if p.exists() else ""


def a17():
    """Does an INDEPENDENT oracle instrument every content-bearing
    attribute the providers can reach (a read counts even when its
    return is discarded)? The historical suite watched four."""
    import re
    hist = _read("tests/v2/context/test_context_snapshot.py")
    m = re.search(r"CONTENT_ATTRS = \(([^)]*)\)", hist, re.S)
    hist_attrs = sorted(re.findall(r'"(AX\w+)"', m.group(1))) if m else []
    world = _read("tests/v2/context/m06_world.py")
    m2 = re.search(r"CONTENT_ATTRS = frozenset\(\{([^}]*)\}", world, re.S)
    world_attrs = sorted(re.findall(r'"(AX\w+)"', m2.group(1))) if m2 \
        else []
    surface = sorted(set(re.findall(
        r'"(AX(?:URL|Document|Title|SelectedText(?:Range)?|Placeholder'
        r'Value|StringForRange|NumberOfCharacters|Value))"',
        inspect.getsource(prov))))
    runner = _read("tests/v2/context/m06_corpus_runner.py")
    covered = set(world_attrs) if "forbid_field_calls" in runner else set()
    return {"kind": "test_gap", "historical_attrs": hist_attrs,
            "independent_oracle_attrs": world_attrs,
            "provider_content_surface": surface,
            "uncovered": sorted(set(surface) - covered),
            "reproduced": bool(set(surface) - covered)}


def a18():
    suites = [_read(f) for f in (
        "tests/v2/context/test_m06_remediation.py",
        "tests/v2/context/m06_corpus_runner.py")]
    barriers = sum(t.count("Barrier(") + t.count("Event()")
                   for t in suites)
    return {"kind": "test_gap", "latch_uses_in_m06_remediation_suites":
            barriers, "reproduced": barriers == 0}


def a19():
    r = _read("tests/v2/context/m06_corpus_runner.py")
    full = "build_messages" in r and "vocabulary_pairs" in r
    return {"kind": "test_gap",
            "full_request_and_rendered_prompt_oracle": full,
            "reproduced": not full}


def a20():
    r = _read("tests/v2/context/m06_corpus_runner.py")
    ok = "ProfileA" in r and "ProfileB" in r and "retry_unscoped_default" in r
    return {"kind": "test_gap", "profile_ab_and_retry_oracles": ok,
            "reproduced": not ok}


def a21():
    rg = subprocess.run(
        ["rg", "-n", "--no-heading", "-g", "*.py",
         r"TargetSnapshot|ContextSnapshot|same_destination|take_downstream"
         r"|context_coll|on_context_snapshot|ContextCollector",
         "localflow", "scripts"], cwd=CODE, capture_output=True, text=True)
    files = sorted({ln.split(":", 1)[0] for ln in rg.stdout.splitlines()})
    native = (CODE / "tests/v2/context/test_native_ax.py").exists()
    inventory = "Caller inventory" in _read("docs/v2/contracts/context.md")
    return {"kind": "test_gap", "local_caller_files": files,
            "native_suite_present": native,
            "caller_inventory_documented": inventory,
            "reproduced": not (native and inventory)}


# ---- A22..A25 design concerns: what the base does today -------------------

def a22():
    # Secure browser: which metadata is read for a secure field?
    a = App(101, "com.google.Chrome", "B", field=field(
        "CANARY_SECURE", token="s", role="AXTextField",
        subrole="AXSecureTextField", url="https://alpha.example/login"),
        window_title="Sign in — alpha.example", window_token="w")
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t = c.capture_identity()
    k = c.begin(t)
    wait_done(k)
    s = finalize(c, k, target_snapshot_id=t.target_snapshot_id)
    attrs = sorted({r[2] for r in host.calls if r[1] == 101 and r[2]})
    return {"kind": "design", "secure_field_attrs_read": attrs,
            "secure_origin": s.site_origin,
            "secure_window_title_retained": s.window_title,
            "secure_value_read": "AXValue" in attrs
            or "AXSelectedText" in attrs,
            "secure_origin_source": s.origin_source,
            # Condition: the secure ELEMENT answered more than its
            # classification (content or its own AXURL).
            "reproduced": bool(set(attrs) - {"AXRole", "AXSubrole",
                                             "AXTitle"})}


def a23():
    T = snap_mod.TargetSnapshot
    C = snap_mod.ContextSnapshot
    t = T(target_snapshot_id="t", app_bundle="com.google.Chrome")
    direct = C(context_snapshot_id="c1", stage="pre_decode", target=t,
               site_origin="https://alpha.example", origin_source="ax_url")
    heur = C(context_snapshot_id="c2", stage="pre_decode", target=t,
             site_origin="https://alpha.example",
             origin_source="window_title")
    return {"kind": "design",
            "scope_equal_direct_vs_title":
                direct.to_scope_context() == heur.to_scope_context(),
            "workspace_collision": [
                prov._workspace_from_path("/Synthetic/teamA/project/a.py"),
                prov._workspace_from_path("/Synthetic/teamB/project/a.py")],
            "reproduced": direct.to_scope_context() == heur.to_scope_context()}


def a24():
    """A REAL late revision: the field provider misses the cut, lands
    late, and its downstream JSON is inspected for lineage."""
    host = WorldHost([app_a()], focus_pid=101)
    c = collector(host, deadline_ms=10)
    gate = threading.Event()
    real = prov.read_field

    def late(*a, **k):
        gate.wait(5)
        return real(*a, **k)
    prov.read_field = late
    try:
        t = c.capture_identity()
        k = c.begin(t)
        pre = finalize(c, k, target_snapshot_id=t.target_snapshot_id)
        gate.set()
        wait_done(k)
        d = c.take_downstream(k)
    finally:
        prov.read_field = real
    keys = set(d.to_json()) if d is not None else set()
    parent = d.to_json().get("parent_context_snapshot_id") if d else None
    return {"kind": "design",
            "late_revision_produced": d is not None,
            "parent_link_in_json": parent is not None,
            "parent_is_pre_decode": bool(pre) and parent
            == pre.context_snapshot_id,
            "revision_kind_in_json": "revision_kind" in keys,
            "reproduced": d is not None and parent is None}


def a25():
    """Two windows of one app with the same title and role and no
    selection: does M08 still grant authority after focus moved to the
    other window? A moved caret in the same field is the control."""
    from localflow.v2.insertion import validation as val
    a = app_a(sel=[3, 0])
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t = c.capture_identity()
    k = c.begin(t)
    wait_done(k)
    s = finalize(c, k, target_snapshot_id=t.target_snapshot_id)
    a.field = dict(a.field, selected_text_range=[9, 0])
    same_lease, same_ver = val.validate_target(host, s, {"job_id": "j"})
    a.field = dict(a.field, field_token="field-A2")
    a.window_token = "win-A2"
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    return {"kind": "design",
            "moved_caret_keeps_authority": same_lease is not None,
            "other_equal_title_window": ver,
            "reproduced": lease is not None}


PROBES = {f"a{i:02d}": globals()[f"a{i:02d}"] for i in range(1, 26)}


def main():
    only = set(ARGS.only.split(",")) if ARGS.only else None
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CODE,
                         capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain", "--", "localflow", "scripts",
         "tests"], cwd=CODE, capture_output=True, text=True).stdout.strip())
    results = {}
    for key, fn in PROBES.items():
        if only and key not in only:
            continue
        t0 = time.monotonic()
        try:
            r = fn()
        except Exception as e:
            r = {"error": f"{type(e).__name__}: {e}",
                 "traceback": traceback.format_exc()[-1500:],
                 "reproduced": None}
        r["seconds"] = round(time.monotonic() - t0, 3)
        results[key] = r
        print(f"{key}: reproduced={r.get('reproduced')} "
              f"({r['seconds']}s){' ERROR ' + r['error'] if 'error' in r else ''}",
              flush=True)
    report = {
        "schema_version": 1,
        "tool": "scripts/v2/m06_remediation_repro.py",
        "code_root_sha": sha,
        "code_root_modified": dirty,
        "python": sys.version.split()[0],
        "desktop_isolation": getattr(__import__(
            "ApplicationServices").AXIsProcessTrusted, "__name__", "")
        == "_untrusted",
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "findings": results,
    }
    text = json.dumps(report, indent=1, sort_keys=True, default=str)
    if ARGS.output:
        pathlib.Path(ARGS.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(ARGS.output).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
