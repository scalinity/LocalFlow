"""M06 remediation: fail-first regressions for the confirmed audit findings.

Authored from the audit's oracles and the recorded policy decisions
(contracts/context.md "Remediation policy"), not from the repaired code:
each test names the defect it guards and fails on the audited base
6a083bd. Every negative assertion is paired with a positive control
proving real work happened (actual provider reads on an allowed field,
a real late completion, two distinguishable jobs, a populated cache, a
retained artifact) — a no-op cannot pass.

Drives the real collector/providers/snapshot/app through the scripted
multi-app world (``m06_world.py``); app-level cases run the real
``AppDelegate`` coordinator. Run under the desktop isolation runner on
a Mac holding the Accessibility grant:

    .venv/bin/python tests/v2/context/run_isolated.py \
        tests/v2/context/test_m06_remediation.py
"""

import json
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "normalization"))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from m06_world import App, WorldHost, AX_CANNOT_COMPLETE, CONTENT_ATTRS  # noqa: E402,E501
from localflow.v2.context import providers as prov  # noqa: E402
from localflow.v2.context import snapshot as snap_mod  # noqa: E402
from localflow.v2.context.collector import ContextCollector  # noqa: E402

CANARY_A = "CANARY_FIELD_A"
CANARY_B = "CANARY_DENIED_B"
DENIED = "com.example.denied"


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
               window_title="Compose", window_token="win-A")


def app_b():
    return App(202, DENIED, "Synthetic Denied B",
               field=field(f"beta {CANARY_B} secretName", token="field-B",
                           url="https://beta.example/x", sel=[5, 15]),
               window_title="Denied B", window_token="win-B")


def collector(host, **kw):
    kw.setdefault("emit", lambda *a, **k: True)
    return ContextCollector(host=host, frontmost=host.frontmost, **kw)


def capture(c, *, settle=True):
    t = c.capture_identity()
    k = c.begin(t)
    if settle and k is not None:
        assert k.done.wait(5), "collection never finished"
    return t, k


def fin(c, k, **kw):
    """Finalize this capture: by its handle where the API takes one; on
    the audited base (global selection) the single live capture is the
    active one, so the behavioral assertion is what fails there."""
    import inspect
    if "coll" in inspect.signature(c.finalize).parameters:
        return c.finalize(k, **kw)
    return c.finalize(**kw)


def has_late(k):
    names = getattr(k, "late_names", None)
    return bool(names()) if names is not None else bool(k.late)


def blob(snap):
    return json.dumps(snap.to_json(), default=str) if snap else ""


# ---- AUDIT-01 ---------------------------------------------------------------

def test_a01_focus_switch_never_reads_other_destination():
    """Guards: reads resolved through the SYSTEM focused element instead of
    the job-owned target's own element (M06-AUDIT-01)."""
    host = WorldHost([app_a(), app_b()], focus_pid=101)
    c = collector(host, denied_apps=(DENIED,))
    real = c._destination_changed

    def switch_after_check(target):
        r = real(target)
        host.switch(202)          # system focus AND frontmost -> denied B
        return r
    c._destination_changed = switch_after_check
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    assert host.reads_of(202) == [], host.reads_of(202)
    assert CANARY_B not in blob(s)
    # The snapshot never carries B's metadata either.
    assert s.window_title != "Denied B"
    assert (s.site_origin or "") != "https://beta.example"
    print("ok  A01 focus switch to a denied app: zero reads of B, no B data")


def test_a01_positive_control_reads_owned_field():
    host = WorldHost([app_a()], focus_pid=101)
    c = collector(host)
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    assert s.field is not None and s.field.classification == "text"
    assert s.field.selected_text == CANARY_A, s.field.selected_text
    assert host.reads_of(101), "positive control made no reads"
    assert s.site_origin == "https://alpha.example"
    assert s.window_title == "Compose"
    print("ok  A01 control: the owned allowed field is really read")


def test_a01_no_hybrid_after_mid_collection_switch():
    host = WorldHost([app_a(), app_b()], focus_pid=101)
    c = collector(host)
    real = prov.read_field

    def field_then_switch(*a, **k):
        r = real(*a, **k)
        host.switch(202)
        return r
    prov.read_field = field_then_switch
    try:
        t, k = capture(c)
    finally:
        prov.read_field = real
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    assert host.reads_of(202) == [], host.reads_of(202)
    assert (s.site_origin or "") != "https://beta.example"
    assert s.window_title != "Denied B"
    print("ok  A01 mid-collection switch: no A-field/B-metadata hybrid")


def test_a01_unowned_element_refused():
    """An element whose owner pid is not the target's is never read."""
    host = WorldHost([app_a(), app_b()], focus_pid=101)
    real = host.focused_element_for
    host.focused_element_for = lambda pid: real(202)   # foreign element
    c = collector(host)
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    content = [r for r in host.reads_of(202) if r[2] in CONTENT_ATTRS]
    assert content == [], content
    assert s.field is None or s.field.classification != "text"
    assert CANARY_B not in blob(s)
    print("ok  A01 an element owned by another pid is refused unread")


# ---- AUDIT-02 ---------------------------------------------------------------

def test_a02_equal_title_new_destination_not_reused():
    a = app_a()
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t, k = capture(c)
    s1 = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    assert s1.site_origin == "https://alpha.example"
    a.field = field("beta userId", token="field-A2",
                    url="https://beta.example/q", sel=[0, 4])
    a.window_token = "win-A2"          # same pid, title, role
    t2, k2 = capture(c)
    s2 = fin(c, k2, target_snapshot_id=t2.target_snapshot_id)
    assert s2.site_origin == "https://beta.example", s2.site_origin
    print("ok  A02 equal pid/title/role but a new tab: origin re-resolved")


def test_a02_workspace_not_reused_across_documents():
    w = App(303, "com.microsoft.VSCode", "IDE",
            field=field("x", token="f1",
                        document="file:///Synthetic/alpha/a.py"),
            window_title="a.py", window_token="w1")
    host = WorldHost([w], focus_pid=303)
    c = collector(host)
    t, k = capture(c)
    assert fin(c, k, target_snapshot_id=t.target_snapshot_id
                      ).workspace == "alpha"
    w.field = field("x", token="f2", document="file:///Synthetic/beta/a.py")
    w.window_token = "w2"
    t2, k2 = capture(c)
    s2 = fin(c, k2, target_snapshot_id=t2.target_snapshot_id)
    assert s2.workspace == "beta", s2.workspace
    print("ok  A02 same title, new document: workspace re-derived")


# ---- AUDIT-03 / AUDIT-25 ------------------------------------------------------

def _snap(pid, bundle):
    T, C = snap_mod.TargetSnapshot, snap_mod.ContextSnapshot
    return C(context_snapshot_id="ctx-x", stage="pre_decode",
             target=T(target_snapshot_id="tgt-x", app_pid=pid,
                      app_bundle=bundle))


def test_a03_identity_matrix():
    assert _snap(None, None).same_destination({"name": "B"}) is False
    assert _snap(None, None).same_destination(
        {"pid": None, "bundle": None}) is False
    assert _snap(101, "s.a").same_destination(
        {"pid": 101, "bundle": "s.b"}) is False          # recycled pid
    assert _snap(101, None).same_destination(
        {"pid": None, "bundle": None}) is False
    # positive controls
    assert _snap(101, "s.a").same_destination(
        {"pid": 101, "bundle": "s.a"}) is True
    assert _snap(101, None).same_destination(
        {"pid": 101, "bundle": "s.a"}) is True
    assert _snap(None, "s.a").same_destination(
        {"pid": 5, "bundle": "s.a"}) is True
    assert _snap(101, "s.a").same_destination(
        {"pid": 202, "bundle": "s.a"}) is False
    print("ok  A03 absent/contradictory identity never matches; controls hold")


def test_a03_m08_consumers_share_the_rule():
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
    tgt = snap_mod.TargetSnapshot(target_snapshot_id="t", app_pid=None,
                                  app_bundle=None)
    lease, ver = val.validate_target(H({"name": "B"}), tgt, {"job_id": "j"})
    assert lease is None and ver["identity"] == "fail", ver
    tgt2 = snap_mod.TargetSnapshot(target_snapshot_id="t", app_pid=101,
                                   app_bundle="s.a")
    lease, ver = val.validate_target(H({"pid": 101, "bundle": "s.b"}),
                                     tgt2, {"job_id": "j"})
    assert lease is None, ver
    lease, ver = val.validate_target(H({"pid": 101, "bundle": "s.a"}),
                                     tgt2, {"job_id": "j"})
    assert lease is not None and ver["identity"] == "pass", ver
    tl = TargetLease(job_id="j", attempt=1, target_snapshot_id=None,
                     context_snapshot_id=None, frontmost_pid=None,
                     frontmost_bundle=None)
    assert tl.identity_matches({"name": "B"}) is False
    print("ok  A03 M08 validate_target and the lease use the same rule")


# ---- AUDIT-05 ---------------------------------------------------------------

def test_a05_snapshot_transitively_immutable():
    d = {"context_snapshot_id": "ctx-fixed", "stage": "pre_decode",
         "target": {"target_snapshot_id": "tgt-1", "app_bundle": "a.b",
                    "app_pid": 1},
         "field": {"classification": "text", "selected_range": [1, 2],
                   "selected_text": "x"},
         "identifiers": {"user id": "userId"},
         "providers": [{"name": "focused_field", "status": "ok"}],
         "omissions": [{"field": "workspace", "reason": "not_exposed"}]}
    s = snap_mod.ContextSnapshot.from_json(d)
    before = json.dumps(s.to_json(), sort_keys=True)
    env = json.dumps(s.to_envelope_block(), sort_keys=True)
    d["identifiers"]["user id"] = "MUTATED"
    d["providers"][0]["status"] = "MUTATED"
    d["omissions"][0]["reason"] = "MUTATED"
    d["field"]["selected_range"].append(9)
    def write_identifiers():
        s.identifiers["x"] = "y"

    def write_provider():
        s.providers[0]["status"] = "z"

    def write_omission():
        s.omissions[0]["reason"] = "z"
    for attempt in (write_identifiers, write_provider, write_omission):
        try:
            attempt()
            raise AssertionError("nested snapshot state accepted a write")
        except TypeError:
            pass
    j = s.to_json()
    j["identifiers"]["detached"] = "y"
    j["providers"][0]["status"] = "detached"
    assert json.dumps(s.to_json(), sort_keys=True) == before
    assert json.dumps(s.to_envelope_block(), sort_keys=True) == env
    assert s.to_engine_context(None).identifiers == {"user id": "userId"}
    assert tuple(s.field.selected_range) == (1, 2)
    print("ok  A05 caller/consumer mutation never changes a frozen id's bytes")


# ---- AUDIT-06 ---------------------------------------------------------------

def test_a06_revoked_handle_stops_and_publishes_nothing():
    gate, entered = threading.Event(), threading.Event()
    host = WorldHost([app_a()], focus_pid=101)
    real = prov.read_site_origin

    def blocked(*a, **k):
        entered.set()
        gate.wait(5)
        return real(*a, **k)
    prov.read_site_origin = blocked
    try:
        c = collector(host)
        t = c.capture_identity()
        k = c.begin(t)
        assert entered.wait(5), "origin provider never started"
        assert host.reads_of(101), "positive control: field was read"
        n = len(host.calls)
        c.revoke(k, reason="cancelled")
        gate.set()
        assert k.done.wait(5)
    finally:
        prov.read_site_origin = real
    # Even the origin stage already in flight never reaches the app:
    # every host call checks the handle first.
    after = [r for r in host.calls[n:] if r[2] in CONTENT_ATTRS]
    assert after == [], after
    assert fin(c, k, target_snapshot_id=t.target_snapshot_id) is None
    assert c.take_downstream(k) is None
    print("ok  A06 a revoked handle stops reading and publishes nothing")


def test_a06_admission_bounded_and_shutdown_closes():
    gate = threading.Event()
    host = WorldHost([app_a()], focus_pid=101)
    real = prov.read_field

    def slow(*a, **k):
        gate.wait(5)
        return real(*a, **k)
    prov.read_field = slow
    try:
        c = collector(host)
        handles = [c.begin(c.capture_identity()) for _ in range(10)]
        admitted = [h for h in handles if h is not None]
        assert 1 <= len(admitted) <= 4, len(admitted)
        c.shutdown()
        assert c.begin(c.capture_identity()) is None
        gate.set()
        for h in admitted:
            assert h.done.wait(5)
    finally:
        prov.read_field = real
    print(f"ok  A06 admission bounded ({len(admitted)} of 10 live); "
          "shutdown refuses new work")


# ---- app harness ----------------------------------------------------------

def app_harness(asr_text, host, *, cfg=None, deadline_ms=75.0):
    from test_normalization_pipeline import Harness, RecordingSupervisor
    sup = RecordingSupervisor(asr_text)
    h = Harness([1.0], cfg=cfg or {}, supervisor=sup)
    if host is not None:
        h.d._context = ContextCollector(
            enabled=True, deadline_ms=deadline_ms,
            emit=lambda *a, **k: True, host=host, frontmost=host.frontmost)
    return h, sup


def test_a06_app_cancel_revokes_the_job_handle():
    gate, entered = threading.Event(), threading.Event()
    host = WorldHost([app_a()], focus_pid=101)
    real = prov.read_site_origin

    def blocked(*a, **k):
        entered.set()
        gate.wait(5)
        return real(*a, **k)
    prov.read_site_origin = blocked
    try:
        h, _ = app_harness("x", host)
        h.hk.held = True
        h.hk.on_press()
        assert entered.wait(5)
        handle = h.d._job["context_coll"]
        h.d.cancelDictation()
        assert handle.revoked, "cancel left the context handle live"
        gate.set()
        assert handle.done.wait(5)
    finally:
        prov.read_site_origin = real
    h.close()
    print("ok  A06 cancelDictation revokes the job's context handle")


# ---- AUDIT-07 ---------------------------------------------------------------

def test_a07_release_clock_covers_release_path_work():
    import localflow.app as app_mod
    host = WorldHost([app_a()], focus_pid=101)
    h, _ = app_harness("twelve percent", host)
    real = app_mod.AppDelegate._finalize_job_context

    def slow(self, job):
        time.sleep(0.2)
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
    gap_ms = (job["released_mono"] - t_release) * 1000.0
    assert gap_ms < 50.0, f"release clock started {gap_ms:.1f} ms late"
    assert time.monotonic() - job["released_mono"] >= 0.2
    h.run_coordinator()
    h.close()
    print(f"ok  A07 released_mono is the release boundary "
          f"(+{gap_ms:.1f} ms), the injected 200 ms lies after it")


class _CountingWiden:
    """Counts (and optionally blocks) WIDENED VocabularySnapshot builds —
    the scoped rebuilds whose scope carries a workspace."""

    def __init__(self, gate=None):
        from localflow.v2 import vocabulary as vocab_mod
        self.mod, self.real = vocab_mod, vocab_mod.VocabularySnapshot
        self.builds, self.gate = 0, gate
        outer, real = self, vocab_mod.VocabularySnapshot

        class Widen(real):
            def __init__(self, entries, scope=None, *a, **k):
                if scope is not None and getattr(scope, "workspace", None):
                    outer.builds += 1
                    if outer.gate is not None:
                        outer.gate.wait(5)
                super().__init__(entries, scope, *a, **k)
        self.cls = Widen

    def __enter__(self):
        self.mod.VocabularySnapshot = self.cls
        return self

    def __exit__(self, *exc):
        self.mod.VocabularySnapshot = self.real


def _press(h):
    h.hk.held = True
    h.hk.on_press()
    return h.d._job


def _release(h):
    h.hk.held = False
    t0 = time.monotonic()
    h.hk.on_release()
    return h.d._active_jobs[-1], (time.monotonic() - t0) * 1000.0


def test_a07_release_uses_the_precomputed_projection():
    h, _ = app_harness("run survo tests", _ide_host())
    h.d._vocab.add_entry("Servo", ["survo"], approved=True,
                         scope_kind="workspace", scope_value="alpha")
    job = _press(h)
    assert job["prewiden_done"].wait(5), "precompute never finished"
    with _CountingWiden() as cw:
        job, _ = _release(h)
    assert cw.builds == 0, f"release rebuilt the projection {cw.builds}x"
    assert job["scope_disposition"] == "widened"
    assert job["norm_context"].vocabulary.scope_ctx.workspace == "alpha"
    fn, (text, _) = h.run_coordinator()
    assert text == "run Servo tests", text     # the widened scope applied
    h.close()
    print("ok  A07 the release path takes the recording-time projection "
          "(0 rebuilds) and the widened scope applies")


def test_a07_unready_projection_is_an_explicit_bounded_downgrade():
    h, _ = app_harness("run survo tests", _ide_host())
    h.d._vocab.add_entry("Servo", ["survo"], approved=True,
                         scope_kind="workspace", scope_value="alpha")
    gate = threading.Event()
    with _CountingWiden(gate) as cw:
        job = _press(h)
        h.d._widen_ms_per_entry = 1000.0  # a measured cost over budget
        job, release_ms = _release(h)
        gate.set()
        assert job["prewiden_done"].wait(5)
    assert cw.builds >= 1, "positive control: a widened build was attempted"
    assert job["scope_disposition"] == "widening_deferred", \
        job.get("scope_disposition")
    assert job["norm_context"].vocabulary.scope_ctx.workspace is None
    assert release_ms < 75.0 + 60.0, f"release took {release_ms:.1f} ms"
    fn, (text, _) = h.run_coordinator()
    assert text == "run survo tests", text     # narrower scope, honestly
    h.close()
    print(f"ok  A07 an unready projection defers explicitly; release "
          f"stayed bounded ({release_ms:.1f} ms)")


def test_a07_projection_uses_captured_entries_only():
    h, _ = app_harness("run survo tests", _ide_host())
    gate = threading.Event()
    real = prov.read_field

    def held(*a, **k):
        gate.wait(5)
        return real(*a, **k)
    prov.read_field = held
    try:
        job = _press(h)
        # A dictionary edit during recording — made while the collection,
        # and so the recording-time projection, is still pending — must
        # not reach this job.
        h.d._vocab.add_entry("Servo", ["survo"], approved=True,
                             scope_kind="workspace", scope_value="alpha")
        gate.set()
        job["prewiden_done"].wait(5)
    finally:
        prov.read_field = real
    job, _ = _release(h)
    assert job["scope_disposition"] == "widened"
    ids = {e.canonical for e in job["norm_context"].vocabulary.entries}
    assert "Servo" not in ids, "the live dictionary leaked into the job"
    fn, (text, _) = h.run_coordinator()
    assert text == "run survo tests", text
    h.close()
    print("ok  A07 the precomputed projection is built from the job's "
          "captured entries only")


# ---- AUDIT-09 ---------------------------------------------------------------

def test_a09_selection_and_flanks_bounded():
    big = "S" * 200_000
    a = App(101, "com.apple.TextEdit", "E",
            field=field("pre " + big + " post", token="f",
                        sel=[4, len(big)]), window_title="d")
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    assert s.field is not None and s.field.classification == "text"
    assert s.field.selected_text is None, "oversized selection retained"
    assert s.field.selected_range is None, \
        "incomplete selection kept replacement authority"
    assert not [r for r in host.calls if r[2] == "AXSelectedText"], \
        "oversized selection was read before its size was checked"
    assert len(blob(s)) < 20_000
    # oversized host return for a 600-unit flank request
    a2 = App(102, "com.apple.TextEdit", "E",
             field=field("x" * 50 + "userId", token="g", sel=[20, 0]),
             window_title="d2")
    host2 = WorldHost([a2], focus_pid=102)
    host2.oversize["AXStringForRange"] = " ".join(
        f"fooBar{i}" for i in range(50_000))
    c2 = collector(host2)
    t2, k2 = capture(c2)
    s2 = fin(c2, k2, target_snapshot_id=t2.target_snapshot_id)
    assert len(s2.field.preceding_text or "") <= prov.NEARBY_CHARS
    assert len(s2.identifiers or {}) <= prov.IDENTIFIER_LIMIT
    # a normal small selection is still retained (positive control)
    a3 = App(103, "com.apple.TextEdit", "E",
             field=field("call userId now", token="h", sel=[5, 6]),
             window_title="d3")
    host3 = WorldHost([a3], focus_pid=103)
    c3 = collector(host3)
    t3, k3 = capture(c3)
    s3 = fin(c3, k3, target_snapshot_id=t3.target_snapshot_id)
    assert s3.field.selected_text == "userId"
    assert tuple(s3.field.selected_range) == (5, 11)
    # negative / inconsistent range is rejected
    a4 = App(104, "com.apple.TextEdit", "E",
             field=field("short", token="i", sel=[-5, 3]), window_title="d")
    host4 = WorldHost([a4], focus_pid=104)
    c4 = collector(host4)
    t4, k4 = capture(c4)
    s4 = fin(c4, k4, target_snapshot_id=t4.target_snapshot_id)
    assert s4.field.selected_range is None
    print("ok  A09 selection read only within budget; flanks truncated; "
          "small selection kept")


# ---- AUDIT-10 ---------------------------------------------------------------

def test_a10_privacy_config_fails_closed():
    from localflow import config
    h, _ = app_harness("x", None, cfg={
        "context_enabled": "false", "training_retain_context": "false"})
    ctx_enabled = h.d._context is not None and h.d._context.enabled
    retain = h.d.collector.retain_context
    h.close()
    assert ctx_enabled is False, "string 'false' enabled context"
    assert retain is False, "string 'false' kept context retention on"
    vals, probs = config.context_policy({
        "context_enabled": "false", "training_retain_context": "false",
        "context_denied_apps": ["com.google.Chrome"],
        "context_deadline_ms": 1e12})
    assert vals["context_enabled"] is False
    assert vals["training_retain_context"] is False
    assert vals["context_deadline_ms"] == 75
    assert {p[0] for p in probs} >= {"context_enabled",
                                     "training_retain_context",
                                     "context_deadline_ms"}
    vals, probs = config.context_policy(
        {"context_denied_apps": "com.google.Chrome"})
    assert vals["context_enabled"] is False, \
        "a malformed deny list must not allow collection"
    for bad in (float("inf"), float("nan"), -1, True, "75", None, 251):
        vals, _ = config.context_policy({"context_deadline_ms": bad})
        assert vals["context_deadline_ms"] == 75, bad
    good, probs = config.context_policy({
        "context_enabled": True, "training_retain_context": False,
        "context_denied_apps": ["com.a", "com.b"],
        "context_deadline_ms": 40})
    assert probs == [] and good["context_enabled"] is True
    assert good["context_denied_apps"] == ("com.a", "com.b")
    assert good["context_deadline_ms"] == 40
    print("ok  A10 malformed privacy controls fail closed; valid ones kept")


# ---- AUDIT-11 ---------------------------------------------------------------

def test_a11_finalize_is_handle_owned_and_idempotent():
    host = WorldHost([app_a()], focus_pid=101)
    c = collector(host)
    ta, ka = capture(c)
    tb, kb = capture(c)
    sa = c.finalize(ka, target_snapshot_id=ta.target_snapshot_id)
    assert sa is not None and \
        sa.target.target_snapshot_id == ta.target_snapshot_id
    sb = c.finalize(kb, target_snapshot_id=tb.target_snapshot_id)
    assert sb.target.target_snapshot_id == tb.target_snapshot_id
    assert c.finalize(None) is None
    assert c.finalize(ka, target_snapshot_id=tb.target_snapshot_id) is None
    # two finalizers of one handle at the same boundary: one id
    t2, k2 = capture(c)
    barrier = threading.Barrier(2, timeout=5)
    real_wait = k2.done.wait

    def both(timeout=None):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return real_wait(timeout)
    k2.done.wait = both
    got = []
    th = [threading.Thread(target=lambda: got.append(c.finalize(
        k2, target_snapshot_id=t2.target_snapshot_id).context_snapshot_id))
        for _ in range(2)]
    for x in th:
        x.start()
    for x in th:
        x.join(5)
    assert len(got) == 2 and got[0] == got[1], got
    print("ok  A11 finalize takes the job's handle; concurrent calls "
          "publish one id")


# ---- AUDIT-12 / AUDIT-24 -----------------------------------------------------

def test_a12_downstream_sealed_with_parent_link():
    host = WorldHost([app_a()], focus_pid=101)
    c = collector(host, deadline_ms=10)
    gates = {n: threading.Event() for n in ("f", "o", "w")}
    real = (prov.read_field, prov.read_site_origin, prov.read_workspace)

    def gated(fn, g):
        def inner(*a, **k):
            gates[g].wait(5)
            return fn(*a, **k)
        return inner
    prov.read_field = gated(real[0], "f")
    prov.read_site_origin = gated(real[1], "o")
    prov.read_workspace = gated(real[2], "w")
    try:
        t = c.capture_identity()
        k = c.begin(t)
        pre = fin(c, k, target_snapshot_id=t.target_snapshot_id)
        assert pre.partial
        gates["f"].set()
        for _ in range(400):
            if has_late(k):
                break
            time.sleep(0.005)
        d1 = c.take_downstream(k)
        assert d1 is not None, "positive control: a real late field"
        gates["o"].set()
        gates["w"].set()
        assert k.done.wait(5)
        d2 = c.take_downstream(k)
    finally:
        prov.read_field, prov.read_site_origin, prov.read_workspace = real
    assert d2 is None, "a consumed downstream handle refilled"
    assert d1.parent_context_snapshot_id == pre.context_snapshot_id
    assert d1.revision_kind == "late_delta"
    assert pre.to_json()["stage"] == "pre_decode"
    print("ok  A12 one sealed downstream revision linked to its parent")


def test_a12_late_field_document_feeds_workspace():
    ide = App(303, "com.apple.TextEdit", "E",
              field=field("x", token="t",
                          document="file:///Synthetic/alpha/a.py"),
              window_title="untitled")
    host = WorldHost([ide], focus_pid=303)
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
        fin(c, k, target_snapshot_id=t.target_snapshot_id)
        gate.set()
        assert k.done.wait(5)
        d = c.take_downstream(k)
    finally:
        prov.read_field = real
    assert d is not None and d.workspace == "alpha", \
        getattr(d, "workspace", None)
    print("ok  A12 a late field's document still derives the workspace")


# ---- AUDIT-13 ---------------------------------------------------------------

def test_a13_cached_absence_never_reported_resolved():
    a = app_a(url=None)
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    rows = []
    for _ in range(2):
        t, k = capture(c)
        s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
        rows.append({p["name"]: p for p in s.providers}["site_origin"])
        assert s.site_origin is None
    assert all(r["status"] == "omitted" for r in rows), rows
    print("ok  A13 an absent origin stays omitted on the repeat capture")


def test_a13_window_failure_does_not_relabel_field():
    host = WorldHost([app_a()], focus_pid=101)
    host.raise_on["window_of"] = RuntimeError("synthetic")
    host.raise_on["focused_window"] = RuntimeError("synthetic")
    c = collector(host)
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    row = {p["name"]: p for p in s.providers}["focused_field"]
    assert s.field is not None and s.field.classification == "text"
    assert row["status"] == "ok", row
    assert s.window_title is None
    print("ok  A13 a window lookup failure leaves the field row ok")


def test_a13_failed_subrole_is_not_promoted_to_text():
    host = WorldHost([App(104, "com.apple.TextEdit", "E", field=field(
        f"abc {CANARY_A}", token="z", role="AXTextField", sel=[0, 3],
        subrole_error=AX_CANNOT_COMPLETE), window_title="t")],
        focus_pid=104)
    c = collector(host)
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    content = [r for r in host.calls
               if r[2] in CONTENT_ATTRS - {"AXTitle"}]
    assert content == [], content
    assert s.field.classification == "unclassifiable"
    assert s.omission_reason("focused_field") == "classification_failed"
    assert CANARY_A not in blob(s)
    print("ok  A13 a failed subrole read fails closed: no content read")


# ---- AUDIT-14 ---------------------------------------------------------------

def test_a14_origin_minimized_and_title_heuristic_narrowed():
    assert prov._url_origin(
        "https://synthetic-user:CANARY_URL_CRED@alpha.example/p") \
        == "https://alpha.example"
    assert prov._url_origin("https://alpha.example:8443/x") \
        == "https://alpha.example:8443"
    # Host case is kept as written (M05 compares case-insensitively).
    assert prov._url_origin("HTTPS://Alpha.Example/x") \
        == "https://Alpha.Example"
    assert prov._url_origin("https://[::1]:8443/p") == "https://[::1]:8443"
    for bad in ("javascript:alert(1)", "file:///Synthetic/a.txt",
                "https://alpha.example:99999/x", "https:///nohost",
                "ftp://alpha.example/x"):
        assert prov._url_origin(bad) is None, bad
    for title, want in (("foo.com.TXT", None),
                        ("author@alpha.example", None),
                        ("Version 3.14", None),
                        ("alpha.example — Inbox", "https://alpha.example")):
        a = App(101, "com.google.Chrome", "B",
                field=field("x", token="f", url=None), window_title=title)
        host = WorldHost([a], focus_pid=101)
        r = prov.read_site_origin(host, "browser", title,
                                  el=host.focused_element_for(101))
        assert r.value == want, (title, r.value)
    print("ok  A14 origin drops userinfo/invalid forms; title negatives hold")


# ---- AUDIT-15 ---------------------------------------------------------------

def _run_evidence(failpoint):
    from localflow.v2 import store as store_mod
    host = WorldHost([app_a()], focus_pid=101)
    h, _ = app_harness("twelve percent", host)
    h.d.consent.set("enabled", note="m06 regression")
    ctx_art = {}
    real_write = h.d.store.write_text_artifact

    def spy(**kw):
        aid = real_write(**kw)
        if kw.get("role") == "context_snapshot":
            ctx_art[kw["stage"]] = aid
        return aid
    h.d.store.write_text_artifact = spy
    real_ins, real_lease = (store_mod.insert_text_artifact_row,
                            store_mod.grant_lease_row)

    def bad_ins(db, **kw):
        if kw.get("role") == "context_snapshot":
            raise RuntimeError("synthetic writer failure")
        return real_ins(db, **kw)

    def bad_lease(db, artifact_id, holder, **kw):
        if artifact_id in ctx_art.values():
            raise RuntimeError("synthetic lease failure")
        return real_lease(db, artifact_id, holder, **kw)
    if failpoint == "insert":
        store_mod.insert_text_artifact_row = bad_ins
    elif failpoint == "lease":
        store_mod.grant_lease_row = bad_lease
    try:
        h.press_release()
        fn, (text, job) = h.run_coordinator()
        h.d._finishWithText_(text, job)
        h.d.store.sync()
    finally:
        store_mod.insert_text_artifact_row = real_ins
        store_mod.grant_lease_row = real_lease
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    aid = ctx_art.get("pre_decode_context")
    leases = st.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM artifact_leases WHERE artifact_id=?",
        (aid,)).fetchone()[0])
    h.close()
    return env, aid, leases


def test_a15_retained_means_acknowledged():
    env, aid, leases = _run_evidence(None)
    dest = env["context"]["destination"]
    assert dest["retained"] is True and dest["artifact_id"] == aid
    assert leases >= 1, "positive control: a retained artifact with a lease"
    for fp in ("insert", "lease"):
        env, aid, leases = _run_evidence(fp)
        dest = env["context"]["destination"]
        assert dest["retained"] is False, (fp, dest)
        assert dest.get("retention_reason") == "retention_write_failed", dest
        assert env["missing_reasons"].get("context_snapshot_payload"), fp
    print("ok  A15 retained=true only with a committed artifact and lease")


# ---- AUDIT-16 ---------------------------------------------------------------

def _ide_host():
    return WorldHost([App(101, "com.microsoft.VSCode", "IDE", field=field(
        "call userId then fooBar", token="f", sel=[5, 0],
        document="file:///Synthetic/alpha/a.py"), window_title="a.py")],
        focus_pid=101)


def test_a16_engine_context_independent_of_vocabulary():
    h, _ = app_harness("user id", _ide_host())
    h.d._vocab = None
    h.press_release()
    job = h.d._active_jobs[-1]
    snap = job["context_snapshot"]
    assert snap.identifiers, "positive control: identifiers were extracted"
    nc = job.get("norm_context")
    assert nc is not None and nc.identifiers == dict(snap.identifiers)
    assert nc.destination_app == "com.microsoft.VSCode"
    h.run_coordinator()
    h.close()
    print("ok  A16 identifiers/destination attach without a vocabulary")


def test_a16_failed_widening_is_an_explicit_coherent_downgrade():
    from localflow.v2 import vocabulary as vocab_mod
    h, _ = app_harness("user id", _ide_host())
    h.d._vocab.add_entry("Servo", ["survo"], approved=True,
                         scope_kind="workspace", scope_value="alpha")
    events = []
    real_emit = h.d.v2log.emit

    def spy(event, **kw):
        events.append((event, kw.get("outcome")))
        return real_emit(event, **kw)
    h.d.v2log.emit = spy
    real_vs = vocab_mod.VocabularySnapshot

    class FailingVS(real_vs):
        def __init__(self, entries, scope=None, *a, **k):
            if scope is not None and getattr(scope, "workspace", None):
                raise RuntimeError("synthetic upgrade failure")
            super().__init__(entries, scope, *a, **k)
    vocab_mod.VocabularySnapshot = FailingVS
    try:
        h.press_release()
    finally:
        vocab_mod.VocabularySnapshot = real_vs
    job = h.d._active_jobs[-1]
    assert job["context_snapshot"].workspace == "alpha"
    assert job.get("scope_disposition") == "widening_failed", \
        job.get("scope_disposition")
    vocab = job["norm_context"].vocabulary
    assert vocab.scope_ctx.workspace is None   # the captured narrower scope
    assert ("context.finalize_failed", "hotkey_down_scope_kept") \
        not in events, events
    h.run_coordinator()
    h.close()
    print("ok  A16 a failed widening keeps a coherent recorded downgrade")


# ---- AUDIT-22 / AUDIT-23 policy ------------------------------------------------

def test_a22_secure_element_reads_only_classification():
    a = App(101, "com.google.Chrome", "B", field=field(
        "CANARY_SECURE", token="s", role="AXTextField",
        subrole="AXSecureTextField", url="https://alpha.example/login"),
        window_title="Sign in")
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    el_reads = {r[2] for r in host.calls if r[0] == "read" and r[1] == 101
                and r[2] != "AXTitle"}
    assert el_reads <= {"AXRole", "AXSubrole"}, el_reads
    assert s.field.classification == "secure"
    assert "CANARY_SECURE" not in blob(s)
    assert s.window_title == "Sign in"       # allowed destination metadata
    print("ok  A22 a secure element answers role/subrole only")


def test_a23_title_origin_is_evidence_not_scope():
    T, C = snap_mod.TargetSnapshot, snap_mod.ContextSnapshot
    t = T(target_snapshot_id="t", app_bundle="com.google.Chrome")
    heur = C(context_snapshot_id="c", stage="pre_decode", target=t,
             site_origin="https://alpha.example",
             origin_source="window_title")
    direct = C(context_snapshot_id="d", stage="pre_decode", target=t,
               site_origin="https://alpha.example", origin_source="ax_url")
    assert heur.to_scope_context().site_origin is None
    assert direct.to_scope_context().site_origin == "https://alpha.example"
    assert heur.site_origin == "https://alpha.example"   # still evidence
    print("ok  A23 a title-derived origin is evidence, never site scope")


def test_a25_equal_title_other_window_is_a_changed_target():
    """AUDIT-25: two windows of one app with the same title/role and no
    selection were indistinguishable to M08; the M06 window identity now
    decides. A moved caret — and another field of the SAME window —
    keeps authority (the deliberate caret policy)."""
    from localflow.v2.insertion import validation as val
    a = app_a(sel=[3, 0])
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t, k = capture(c)
    s = fin(c, k, target_snapshot_id=t.target_snapshot_id)
    assert s.window_element is not None, "positive control: window read"
    # Same window, caret moved: authority kept.
    a.field = dict(a.field, selected_text_range=[9, 0])
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    assert lease is not None and ver["window"] == "pass", ver
    # Another field in the same window: still the same destination.
    a.field = dict(a.field, field_token="field-A-other")
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    assert lease is not None and ver["window"] == "pass", ver
    # Another window with the SAME title and role, empty selection.
    a.field = dict(a.field, field_token="field-A2")
    a.window_token = "win-A2"
    assert a.window_title == "Compose"
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    assert lease is None and ver["window"] == "fail", ver
    print("ok  A25 an equal-title second window is a changed target; "
          "caret and same-window field moves keep authority")


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = []
    for fn in tests:
        try:
            fn()
        except Exception as e:     # report every regression, not the first
            failed.append(fn.__name__)
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}"[:400])
    print(f"{len(tests) - len(failed)}/{len(tests)} M06 remediation "
          "regressions passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
