"""M06 native Accessibility probe (reference Mac only; real PyObjC).

Launches ``tests/v2/context/native_ax_target.py`` — a synthetic window
owned by a helper process, never activated, off-screen — and exercises
the code root's REAL ``SystemAXHost`` and providers against it. The
system-wide focused element is never read: on the base code root, whose
host resolves focus globally, the host is subclassed so that every
focus lookup returns the helper application's own focused element.

Records native facts (AXValue range shape, UTF-16 units, window lookup,
element identity, error codes, secure-field classification) and what
the code root's host/providers make of them.

    .venv/bin/python scripts/v2/m06_native_probe.py --code-root DIR \
        --output PATH
Exit 0 always; ``status`` is ``not_run`` with a reason when the
machine cannot run it (no PyObjC, no Accessibility grant).
"""

import argparse
import inspect
import json
import pathlib
import platform
import subprocess
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--code-root",
                default=str(pathlib.Path(__file__).resolve().parents[2]))
ap.add_argument("--output", default=None)
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
HERE = pathlib.Path(__file__).resolve().parents[2]
TARGET = HERE / "tests" / "v2" / "context" / "native_ax_target.py"
sys.path.insert(0, str(CODE))

TEXT_UNICODE = "A\U0001F600B é café userId end"
TEXT_ASCII = "alpha userId beta fooBar gamma"


def launch(spec):
    p = subprocess.Popen([sys.executable, str(TARGET), json.dumps(spec)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True)
    line = p.stdout.readline().strip()
    pid = int(line.split()[1])
    time.sleep(0.6)
    return p, pid


def stop(p):
    try:
        p.stdin.close()
        p.wait(timeout=5)
    except Exception:
        p.kill()


def main():
    report = {"schema_version": 1, "tool": "scripts/v2/m06_native_probe.py",
              "machine": {"macos": platform.mac_ver()[0],
                          "arch": platform.machine(),
                          "python": sys.version.split()[0]}}
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CODE,
                         capture_output=True, text=True).stdout.strip()
    report["code_root_sha"] = sha
    try:
        import ApplicationServices as AS
    except Exception as e:
        report.update(status="not_run",
                      reason=f"pyobjc_unavailable:{type(e).__name__}")
        return finish(report)
    if not AS.AXIsProcessTrusted():
        report.update(status="not_run",
                      reason="accessibility_not_trusted_for_this_process")
        return finish(report)
    from localflow.v2.context import providers as prov
    from localflow.v2.context.collector import ContextCollector

    repaired = hasattr(prov.SystemAXHost, "focused_element_for")
    report["code_root_api"] = "job_owned" if repaired else "global_focus"

    def app_focused(pid):
        app = AS.AXUIElementCreateApplication(pid)
        AS.AXUIElementSetMessagingTimeout(app, 0.5)
        err, el = AS.AXUIElementCopyAttributeValue(
            app, "AXFocusedUIElement", None)
        return app, (el if err == 0 else None), err

    class OwnedHost(prov.SystemAXHost):
        """Base-protocol host whose focus lookups resolve to the
        helper's own focused element — the system-wide focused element
        (another app) is never touched."""
        pid = None
        attrs_read: list = []

        def focused_element(self):
            _, el, _ = app_focused(self.pid)
            return el

        def attribute(self, el, name):
            self.attrs_read.append(name)
            return super().attribute(el, name)

        def read(self, el, name):          # the repaired providers' call
            self.attrs_read.append(name)
            return super().read(el, name)

    scen = {}
    for name, spec in {
        "unicode_selection": {"text": TEXT_UNICODE, "selection": [1, 2]},
        "ascii_selection": {"text": TEXT_ASCII, "selection": [6, 6]},
        "caret_only": {"text": TEXT_ASCII, "selection": [6, 0]},
        "secure_focused": {"text": TEXT_ASCII, "selection": [0, 0],
                           "first_responder": "secure"},
        "plain_field_focused": {"text": TEXT_ASCII, "selection": [0, 0],
                                "first_responder": "field"},
    }.items():
        p, pid = launch(spec)
        try:
            scen[name] = probe_one(AS, prov, ContextCollector, OwnedHost,
                                   app_focused, pid, spec, repaired)
        except Exception as e:      # recorded, never hidden
            import traceback
            scen[name] = {"error": f"{type(e).__name__}: {e}",
                          "traceback": traceback.format_exc()[-1200:]}
        finally:
            stop(p)
    report["status"] = "ran"
    report["scenarios"] = scen
    return finish(report)


def probe_one(AS, prov, ContextCollector, OwnedHost, app_focused, pid, spec,
              repaired):
    out = {"spec": spec}
    app, el, err = app_focused(pid)
    out["app_focused_element_err"] = err
    if el is None:
        return out
    e, owner = AS.AXUIElementGetPid(el, None)
    out["element_pid_matches"] = (e == 0 and owner == pid)
    _, el2, _ = app_focused(pid)
    out["element_equal_across_fetches"] = bool(el == el2)
    out["element_hash_equal"] = hash(el) == hash(el2)
    out["set_timeout_rc"] = AS.AXUIElementSetMessagingTimeout(el, 0.2)
    for a in ("AXRole", "AXSubrole"):
        e, v = AS.AXUIElementCopyAttributeValue(el, a, None)
        out[a] = [e, v if isinstance(v, str) else None]
    e, rng = AS.AXUIElementCopyAttributeValue(el, "AXSelectedTextRange",
                                              None)
    out["range_type"] = type(rng).__name__ if rng is not None else None
    if rng is not None:
        ok, cf = AS.AXValueGetValue(rng, AS.kAXValueCFRangeType, None)
        out["range_decoded_utf16"] = list(cf) if ok else None
    e, n = AS.AXUIElementCopyAttributeValue(el, "AXNumberOfCharacters", None)
    out["number_of_characters"] = int(n) if e == 0 else [e]
    out["python_len"] = len(spec["text"])
    e, _ = AS.AXUIElementCopyAttributeValue(el, "AXFocusedWindow", None)
    out["field_AXFocusedWindow_err"] = e
    e, w = AS.AXUIElementCopyAttributeValue(el, "AXWindow", None)
    out["field_AXWindow_err"] = e
    e, fw = AS.AXUIElementCopyAttributeValue(app, "AXFocusedWindow", None)
    out["app_AXFocusedWindow_err"] = e
    if w is not None and fw is not None:
        out["field_window_equals_app_focused_window"] = bool(w == fw)
    # ---- the code root's host + providers ---------------------------
    host = OwnedHost()
    host.pid = pid
    host.attrs_read = []
    raw = host.attribute(el, "AXSelectedTextRange")
    if repaired:
        r = prov.ax_range(raw)
        out["host_as_range"] = list(r) if r else [None, None]
    else:
        out["host_as_range"] = list(prov._as_range(raw))
    out["host_string_for_range_0_3"] = host.string_for_range(el, 0, 3)
    win = host.window_of(el) if repaired else host.focused_window(el)
    out["host_focused_window_found"] = win is not None
    if win is None:
        out["host_window_title"] = None
    elif repaired:
        out["host_window_title"] = host.read(win, "AXTitle")[0]
    else:
        out["host_window_title"] = host.window_title(win)
    if repaired:
        o = host.focused_element_for(pid)
        out["owned_element_pid_matches"] = host.element_pid(o) == pid
        out["owned_element_equal_across_fetches"] = bool(
            o == host.focused_element_for(pid))
    host.attrs_read = []
    if repaired:
        fr = prov.read_field(host, False, el=host.focused_element_for(pid))
    else:
        fr = prov.read_field(host, False)
    f = fr.value
    out["read_field"] = {
        "reason": fr.reason,
        "classification": getattr(f, "classification", None),
        "selected_text": getattr(f, "selected_text", None),
        "selected_range": list(f.selected_range)
        if f is not None and f.selected_range else None,
        "selected_range_utf16": list(f.selected_range_utf16)
        if f is not None and getattr(f, "selected_range_utf16", None)
        else None,
        "preceding_text": getattr(f, "preceding_text", None),
        "following_text": getattr(f, "following_text", None),
        "content_attrs_read": sorted(set(host.attrs_read) & {
            "AXSelectedText", "AXSelectedTextRange", "AXStringForRange",
            "AXValue", "AXPlaceholderValue", "AXDocument",
            "AXNumberOfCharacters"}),
    }
    # the collector end to end, bound to this helper's identity
    ident = {"bundle": "org.python.python", "name": "Synthetic target",
             "pid": pid}
    c = ContextCollector(enabled=True, deadline_ms=2000, host=host,
                         frontmost=lambda: ident)
    t = c.capture_identity()
    k = c.begin(t)
    k.done.wait(5)
    params = inspect.signature(c.finalize).parameters
    s = c.finalize(**({"coll": k} if "coll" in params else {}),
                   target_snapshot_id=t.target_snapshot_id)
    out["collector"] = {
        "window_title": s.window_title if s else None,
        "identifiers": dict(s.identifiers or {}) if s else None,
        "providers": [dict(p) for p in s.providers] if s else None,
        "field_classification": s.field.classification
        if s and s.field else None,
    }
    return out


def finish(report):
    text = json.dumps(report, indent=1, sort_keys=True, default=str,
                      ensure_ascii=True)
    print(text)
    if ARGS.output:
        pathlib.Path(ARGS.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(ARGS.output).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
