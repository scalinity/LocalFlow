"""M06 remediation review round: regressions for the independent
reviewer's confirmed allegations (R1-R3, R6-R10), each reproduced by the
author on the frozen first pass (scripts/v2/m06_review_repro.py) before
any fix. Every test fails on first-pass production 88ee303 and passes on
the final code; negative assertions are paired with a positive control.

    .venv/bin/python tests/v2/context/run_isolated.py \
        tests/v2/context/test_m06_review_round.py
"""

import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "normalization"))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from m06_world import App, WorldHost  # noqa: E402
from localflow.v2.context import providers as prov  # noqa: E402
from localflow.v2.context.collector import ContextCollector  # noqa: E402


def browser(**kw):
    return App(101, "com.google.Chrome", "Synthetic Browser", field={
        "field_token": kw.get("token", "f1"), "role": "AXTextArea",
        "value": kw.get("value", "hello there"),
        "selected_text_range": kw.get("sel", [3, 0]),
        "url": kw.get("url", "https://alpha.example/c")},
        window_title=kw.get("title", "Tab A - Chat"),
        window_token=kw.get("win", "win-1"))


def capture(host, c=None, **kw):
    c = c or ContextCollector(host=host, frontmost=host.frontmost,
                              emit=lambda *a, **k: True, **kw)
    t = c.capture_identity()
    k = c.begin(t)
    k.done.wait(5)
    return c, c.finalize(k, target_snapshot_id=t.target_snapshot_id)


def test_r1_same_window_other_tab_is_a_changed_target():
    from localflow.v2.insertion import validation as val
    a = browser()
    host = WorldHost([a], focus_pid=101)
    _, s = capture(host)
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    assert lease is not None, "positive control: same tab keeps authority"
    a.field = dict(a.field, field_token="f2")
    a.window_title = "Tab B - Bank support"     # same window element
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    assert lease is None and ver["window"] == "fail", ver
    print("ok  R1 another tab of the same window is a changed target")


def test_r2_unkept_selection_carries_no_replacement_authority():
    from localflow.v2.insertion import validation as val
    big = App(103, "com.apple.TextEdit", "E", field={
        "field_token": "f", "role": "AXTextArea",
        "value": "pre " + "S" * 5000 + " post",
        "selected_text_range": [4, 5000]}, window_title="doc")
    host = WorldHost([big], focus_pid=103)
    _, s = capture(host)
    assert s.field.selected_text is None
    assert s.field.selected_range_utf16 is None
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    assert lease is not None and not lease.replace_selection, ver
    small = App(104, "com.apple.TextEdit", "E", field={
        "field_token": "g", "role": "AXTextArea", "value": "call userId now",
        "selected_text_range": [5, 6]}, window_title="doc2")
    host2 = WorldHost([small], focus_pid=104)
    _, s2 = capture(host2)
    lease2, _ = val.validate_target(host2, s2, {"job_id": "j"})
    assert lease2 is not None and lease2.replace_selection, \
        "positive control: a kept selection is replaceable"
    print("ok  R2 an over-budget selection is a caret, not a refused "
          "replacement")


def test_r3_deferred_widening_keeps_the_captured_profile():
    from test_normalization_pipeline import Harness, RecordingSupervisor
    from localflow.v2 import vocabulary as vm
    host = WorldHost([browser(url="https://chatgpt.com/c", title="ChatGPT")],
                     focus_pid=101)
    h = Harness([1.0] * 4, cfg={}, supervisor=RecordingSupervisor("x"))
    h.d._context = ContextCollector(host=host, frontmost=host.frontmost,
                                    emit=lambda *a, **k: True)
    h.d._styles.add_rule(name="ai", scope_kind="category",
                         scope_value="ai_prompt", number_policy="standard")
    h.d._vocab.add_entry("Servo", ["survo"], approved=True,
                         scope_kind="site", scope_value="https://chatgpt.com")
    gate = threading.Event()
    real = vm.VocabularySnapshot

    class Slow(real):
        def __init__(self, entries, scope=None, *a, **k):
            if scope is not None and getattr(scope, "site_origin", None):
                gate.wait(3)
            super().__init__(entries, scope, *a, **k)
    vm.VocabularySnapshot = Slow
    try:
        h.hk.held = True
        h.hk.on_press()
        captured = h.d._job["norm_policy"].profile
        h.d._widen_cost_ms = 1000.0          # the first-pass knob
        h.d._widen_ms_per_entry = 1000.0     # the final (per-entry) knob
        h.hk.held = False
        h.hk.on_release()
        gate.set()
    finally:
        vm.VocabularySnapshot = real
    job = h.d._active_jobs[-1]
    assert job["scope_disposition"] == "widening_deferred", \
        "positive control: the deferral path ran"
    assert job["norm_policy"].profile == captured, \
        (job["norm_policy"].profile, captured)
    assert job["m10"]["wp"].category != "ai_prompt"
    h.run_coordinator()
    h.close()
    print("ok  R3 a deferred widening keeps the whole captured tuple")


def test_r6_title_origin_is_rederived_not_cached():
    a = browser(url=None, title="alpha.example - Inbox")
    host = WorldHost([a], focus_pid=101)
    c = ContextCollector(host=host, frontmost=host.frontmost,
                         emit=lambda *a, **k: True)
    _, s1 = capture(host, c)
    assert s1.site_origin == "https://alpha.example"   # positive control
    a.window_title = "beta.example - Inbox"
    _, s2 = capture(host, c)
    assert s2.site_origin == "https://beta.example", s2.site_origin
    row = {p["name"]: p for p in s2.providers}["site_origin"]
    assert not row.get("cached"), row
    print("ok  R6 a title-derived origin follows the current title")


def test_r7_released_handle_cannot_warm_the_projection():
    host = WorldHost([browser()], focus_pid=101)
    c = ContextCollector(host=host, frontmost=host.frontmost,
                         emit=lambda *a, **k: True)
    t = c.capture_identity()
    k = c.begin(t)
    k.done.wait(5)
    assert c.preview(k) is not None, "positive control: preview while live"
    c.finalize(k, target_snapshot_id=t.target_snapshot_id)
    assert c.preview(k) is None
    print("ok  R7 a released handle previews nothing (no late eviction)")


def test_r7_widening_cost_scales_with_the_dictionary():
    import localflow.app as app_mod
    src = pathlib.Path(app_mod.__file__).read_text()
    assert "_widen_ms_per_entry" in src and "* len(entries)" in src
    print("ok  R7 the synchronous-build estimate scales per entry")


def test_r8_r9_window_is_the_fields_own_with_a_timeout():
    import ApplicationServices as AS
    host = prov.SystemAXHost()
    calls = []
    real_set = AS.AXUIElementSetMessagingTimeout
    AS.AXUIElementSetMessagingTimeout = lambda el, t: calls.append(el) or 0
    try:
        host.read = lambda el, name: (("win", 0) if name == "AXWindow"
                                      else (None, prov.AX_ERR_UNSUPPORTED))
        assert host.window_of("field") == "win"      # positive control
        assert calls == ["win"], calls               # R9
        host.read = lambda el, name: ((None, -25204) if name == "AXWindow"
                                      else (("other-window", 0)
                                            if name == "AXFocusedWindow"
                                            else (None, -25205)))
        host.element_pid = lambda el: 101
        assert host.window_of("field") is None       # R8: no substitute
    finally:
        AS.AXUIElementSetMessagingTimeout = real_set
    print("ok  R8/R9 the field's own window, with the messaging timeout")


def test_r10_api_disabled_is_permission_and_bundle_change_is_drift():
    a = App(104, "com.apple.TextEdit", "E", field={
        "field_token": "z", "role": "AXTextField", "value": "abc",
        "subrole_error": -25211}, window_title="t")
    host = WorldHost([a], focus_pid=104)
    _, s = capture(host)
    assert s.omission_reason("focused_field") == "permission_unavailable", \
        s.omission_reason("focused_field")
    c = ContextCollector(host=host, frontmost=lambda: {
        "pid": 104, "bundle": "com.other.app"})
    from localflow.v2.context.snapshot import TargetSnapshot
    tgt = TargetSnapshot(target_snapshot_id="t", app_pid=104,
                         app_bundle="com.apple.TextEdit")
    assert c._destination_changed(tgt) is True
    same = ContextCollector(host=host, frontmost=lambda: {
        "pid": 104, "bundle": "com.apple.TextEdit"})
    assert same._destination_changed(tgt) is False   # positive control
    print("ok  R10 API disabled => permission; a recycled pid is drift")


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = []
    for fn in tests:
        try:
            fn()
        except Exception as e:
            failed.append(fn.__name__)
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}"[:300])
    print(f"{len(tests) - len(failed)}/{len(tests)} M06 review-round "
          "regressions passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
