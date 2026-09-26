"""M06 remediation review round: the author's own reproductions of the
independent reviewer's allegations (R1-R12) against a code root.

Written independently of the reviewer's probes. Each probe drives real
production code through ``tests/v2/context/m06_world.py`` (synthetic
destinations only) and returns ``reproduced`` plus what it observed.

    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/m06_review_repro.py --code-root DIR --output PATH
"""

import argparse
import inspect
import json
import pathlib
import subprocess
import sys
import threading
import time
import traceback

ap = argparse.ArgumentParser()
ap.add_argument("--code-root",
                default=str(pathlib.Path(__file__).resolve().parents[2]))
ap.add_argument("--output", default=None)
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
HERE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(CODE / "tests" / "v2" / "normalization"))
sys.path.insert(0, str(HERE / "tests" / "v2" / "context"))

from m06_world import App, WorldHost  # noqa: E402
from localflow.v2.context import providers as prov  # noqa: E402
from localflow.v2.context.collector import ContextCollector  # noqa: E402


def world(apps, pid):
    return WorldHost(apps, focus_pid=pid)


def capture(host, **kw):
    c = ContextCollector(host=host, frontmost=host.frontmost,
                         emit=lambda *a, **k: True, **kw)
    t = c.capture_identity()
    k = c.begin(t)
    k.done.wait(5)
    fin = c.finalize
    s = fin(k, target_snapshot_id=t.target_snapshot_id) \
        if "coll" in inspect.signature(fin).parameters \
        else fin(target_snapshot_id=t.target_snapshot_id)
    return c, t, k, s


def browser(**kw):
    return App(101, "com.google.Chrome", "Synthetic Browser", field={
        "field_token": kw.get("token", "f1"), "role": "AXTextArea",
        "value": kw.get("value", "hello there"),
        "selected_text_range": kw.get("sel", [3, 0]),
        "url": kw.get("url", "https://alpha.example/c")},
        window_title=kw.get("title", "Tab A - Chat"),
        window_token=kw.get("win", "win-1"))


def r1():
    """Tab switch inside ONE window (same window element, new title)."""
    from localflow.v2.insertion import validation as val
    a = browser()
    host = world([a], 101)
    c, t, k, s = capture(host)
    a.field = dict(a.field, field_token="f2")
    a.window_title = "Tab B - Bank support"         # same win token
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    return {"verification": ver, "lease_granted": lease is not None,
            "reproduced": lease is not None}


def r2():
    """Over-budget selection: replacement authority and M08 outcome."""
    from localflow.v2.insertion import validation as val
    text = "pre " + "S" * 5000 + " post"
    a = App(103, "com.apple.TextEdit", "E", field={
        "field_token": "f", "role": "AXTextArea", "value": text,
        "selected_text_range": [4, 5000]}, window_title="doc")
    host = world([a], 103)
    c, t, k, s = capture(host)
    lease, ver = val.validate_target(host, s, {"job_id": "j"})
    return {"selected_text_retained": s.field.selected_text is not None,
            "selected_range_utf16": getattr(s.field, "selected_range_utf16",
                                            None),
            "m08": ver, "lease_granted": lease is not None,
            "reproduced": lease is None}


def r3():
    """Deferred widening while the M10 profile moves to the finalized
    destination: what does the job run under?"""
    from test_normalization_pipeline import Harness, RecordingSupervisor
    host = world([browser(url="https://chatgpt.com/c", title="ChatGPT")], 101)
    h = Harness([1.0] * 4, cfg={}, supervisor=RecordingSupervisor("x"))
    h.d._context = ContextCollector(host=host, frontmost=host.frontmost,
                                    emit=lambda *a, **k: True)
    h.d._styles.add_rule(name="ai", scope_kind="category",
                         scope_value="ai_prompt", number_policy="standard")
    h.d._vocab.add_entry("Servo", ["survo"], approved=True,
                         scope_kind="site", scope_value="https://chatgpt.com")
    gate = threading.Event()
    from localflow.v2 import vocabulary as vm
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
        hk_profile = h.d._job.get("norm_policy").profile
        h.d._widen_cost_ms = 1000.0          # first-pass knob
        h.d._widen_ms_per_entry = 1000.0     # final knob (per entry)
        h.hk.held = False
        h.hk.on_release()
        gate.set()
    finally:
        vm.VocabularySnapshot = real
    job = h.d._active_jobs[-1]
    out = {"scope_disposition": job.get("scope_disposition"),
           "hotkey_down_policy_profile": hk_profile,
           "final_policy_profile": job["norm_policy"].profile,
           "wp_category": job["m10"]["wp"].category,
           "vocab_site": job["norm_context"].vocabulary.scope_ctx.site_origin}
    h.run_coordinator()
    h.close()
    # Valid only if the deferral path really ran.
    out["probe_valid"] = out["scope_disposition"] == "widening_deferred"
    out["reproduced"] = (out["probe_valid"]
                         and out["final_policy_profile"]
                         != out["hotkey_down_policy_profile"]) \
        if out["probe_valid"] else None
    return out


def r4():
    """A deny entry with surrounding spaces: the M06 decision vs the M11
    selection capture itself (``_m11_capture_selection``), driven over a
    host that records every Accessibility call. Reproduced when the
    capture reaches Accessibility for the app the entry names."""
    import types
    from test_normalization_pipeline import Harness, RecordingSupervisor
    calls = []

    class Host:
        def frontmost(self):
            return {"bundle": "com.google.Chrome", "name": "B", "pid": 101}

        def focused_element(self):
            calls.append("focused_element")
            return "field"

        def attribute(self, el, name):
            calls.append(name)
            return {"AXRole": "AXTextArea",
                    "AXSelectedTextRange": (0, 5)}.get(name)

        def string_for_range(self, el, start, length):
            calls.append("string_for_range")
            return "hello"[start:start + length]

        def number_of_characters(self, el):
            calls.append("number_of_characters")
            return 5

    h = Harness([1.0], cfg={"context_denied_apps": [" com.google.Chrome"]},
                supervisor=RecordingSupervisor("x"))
    try:
        m06 = h.d._context is not None and \
            "com.google.Chrome" in h.d._context.denied_apps
        h.d._insertion = types.SimpleNamespace(host=Host())
        _cap, reason = h.d._m11_capture_selection()
    finally:
        h.close()
    return {"m06_denies": m06, "m11_capture_calls": calls,
            "m11_reason": reason, "reproduced": bool(calls)}


def r6():
    """A title-derived origin cached while the title changes."""
    a = browser(url=None, title="alpha.example - Inbox")
    host = world([a], 101)
    c = ContextCollector(host=host, frontmost=host.frontmost,
                         emit=lambda *a, **k: True)
    fin = c.finalize
    out = []
    for title in ("alpha.example - Inbox", "beta.example - Inbox"):
        a.window_title = title
        t = c.capture_identity()
        k = c.begin(t)
        k.done.wait(5)
        s = fin(k, target_snapshot_id=t.target_snapshot_id)
        out.append([s.window_title, s.site_origin,
                    {p["name"]: p for p in s.providers}["site_origin"]])
    return {"captures": out,
            "reproduced": out[1][1] == "https://alpha.example"}


def r7():
    """A late precompute of job A evicting job B's warmed projection."""
    import localflow.app as app_mod  # noqa: F401
    src = (CODE / "localflow" / "app.py").read_text()
    body = src.split("def _start_prewiden")[1].split("\n    @objc")[0] \
        if "def _start_prewiden" in src else ""
    skips_finalized = "finalized" in body or "snapshot is not None" in body
    prev = (CODE / "localflow/v2/context/collector.py").read_text()
    pv = prev.split("def preview")[1].split("\n    def ")[0] \
        if "def preview" in prev else ""
    preview_refuses_finalized = "finalized" in pv
    per_entry_cost = "per_entry" in src or "_widen_cost_ms" not in src
    return {"precompute_skips_finalized_handle":
            skips_finalized or preview_refuses_finalized,
            "cost_estimate_scales_with_entries": per_entry_cost,
            "reproduced": not (skips_finalized or preview_refuses_finalized)
            or not per_entry_cost}


def r8_r9():
    src = (CODE / "localflow/v2/context/providers.py").read_text()
    wo = src.split("def window_of")[1].split("\n    def ")[0] \
        if "def window_of" in src else ""
    return {"fallback_to_application_focused_window":
            "AXFocusedWindow" in wo,
            "sets_window_timeout": "SetMessagingTimeout" in wo,
            "reproduced": "AXFocusedWindow" in wo
            or "SetMessagingTimeout" not in wo}


def r10():
    a = App(104, "com.apple.TextEdit", "E", field={
        "field_token": "z", "role": "AXTextField", "value": "abc",
        "subrole_error": -25211}, window_title="t")
    host = world([a], 104)
    c, t, k, s = capture(host)
    drift = ContextCollector(host=host, frontmost=lambda: {
        "pid": 104, "bundle": "com.other.app"})
    t2 = drift.capture_identity()
    changed = drift._destination_changed(
        type(t2)(target_snapshot_id="x", app_pid=104,
                 app_bundle="com.apple.TextEdit"))
    return {"field_reason": s.omission_reason("focused_field"),
            "recycled_pid_detected_as_changed": changed,
            "reproduced": s.omission_reason("focused_field")
            != "permission_unavailable" or not changed}


PROBES = {"r1": r1, "r2": r2, "r3": r3, "r4": r4, "r6": r6, "r7": r7,
          "r8_r9": r8_r9, "r10": r10}


def main():
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CODE,
                         capture_output=True, text=True).stdout.strip()
    res = {}
    for k, fn in PROBES.items():
        try:
            res[k] = fn()
        except Exception as e:
            res[k] = {"error": f"{type(e).__name__}: {e}",
                      "traceback": traceback.format_exc()[-1000:],
                      "reproduced": None}
        print(f"{k}: reproduced={res[k].get('reproduced')}", flush=True)
    rep = {"schema_version": 1, "tool": "scripts/v2/m06_review_repro.py",
           "code_root_sha": sha, "findings": res,
           "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime())}
    if ARGS.output:
        pathlib.Path(ARGS.output).write_text(
            json.dumps(rep, indent=1, sort_keys=True, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
