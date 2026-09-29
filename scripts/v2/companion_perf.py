"""Desktop companion timings and memory over a SYNTHETIC world.

The same passive, off-screen setup as companion_screens.py: the lifecycle
Harness (a temporary store, fake microphone), the real CompanionController
and WKWebView, the window never activated. Timings are taken inside the
page (performance.now, from the action until the result is usable);
memory is the resident size of this process plus the WebKit processes
that appeared when the companion was created.

    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/companion_perf.py [--rows 2000]

Prints one JSON object.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/v2"))

import companion_screens as CS  # noqa: E402  (sets up sys.path)

from AppKit import NSApplication  # noqa: E402


def rss_kb(pids):
    out = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(map(str, pids))],
                         capture_output=True, text=True).stdout
    return sum(int(x) for x in out.split())


def webkit_pids():
    out = subprocess.run(["pgrep", "-f", "com.apple.WebKit"],
                         capture_output=True, text=True).stdout
    return {int(x) for x in out.split()}


def timed(host, action, ready, timeout=10.0):
    """ms from running `action` (JS) until `ready` (a JS expression)
    holds, checked on every frame."""
    CS.js(host, "window.__perf = null; window.__t0 = performance.now(); ("
                + action + "); (function check() { if (" + ready + ") "
                "window.__perf = performance.now() - window.__t0; else "
                "requestAnimationFrame(check); })(); 1")
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = CS.js(host, "window.__perf === null ? -1 : window.__perf")
        if isinstance(v, (int, float)) and v >= 0:
            return round(v, 1)
        CS.pump(0.02)
    return None


def nav_action(label):
    return ("[...document.querySelectorAll('nav button')].find(b => "
            "b.textContent.trim() === " + json.dumps(label) + ").click()")


ON = ("document.querySelector('nav [aria-current=\"page\"]')"
      "?.textContent.trim() === {label}")
ROUTE_READY = ("document.querySelector('nav [aria-current=\"page\"]')"
               "?.textContent.trim() === {label} && (document.querySelector"
               "('main')?.innerText || '').length > 20 && !(document."
               "querySelector('main')?.innerText || '').includes('Loading')")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=2000)
    args = ap.parse_args(argv)
    import m09_world as W
    from test_lifecycle import Harness
    from localflow.v2.ui.companion.controller import CompanionController

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)
    me = [__import__("os").getpid()]
    out = {"rows": args.rows}
    h = Harness(durations=[1.0], cfg={"hub_ui": "companion"})
    try:
        d = h.d
        CS.seed(d, d.store)
        now = CS.dt.datetime.now(CS.dt.timezone.utc)
        for i in range(args.rows):
            W.seed_job(d.store, f"synthetic dictation number {i}",
                       applied=f"Synthetic dictation number {i}.",
                       captured=CS.iso(now - CS.dt.timedelta(minutes=9 * i)))
        d.store.sync()
        CS.pump(0.5)
        wk0 = webkit_pids()
        out["rss_kb_never_opened"] = {"python": rss_kb(me)}

        spec, _ = W.hub_spec(d)
        spec.update(vocabulary_store=d._vocab, display_name="Alex",
                    prefs_path=h.tmp / "companion.json")
        t = time.perf_counter()
        ctl = CompanionController(spec)
        out["ms_controller_and_webview"] = round(
            (time.perf_counter() - t) * 1000, 1)
        d._hub = ctl
        host = ctl.host
        try:
            host.webview._setWindowOcclusionDetectionEnabled_(False)
        except Exception:
            pass
        win = host.window
        win.setFrame_display_(((-4000, 300), (1150, 715)), True)
        win.orderFront_(None)
        t = time.perf_counter()
        ctl.state.show()
        while not host._loaded:
            CS.pump(0.005)
        out["ms_show_to_page_loaded"] = round(
            (time.perf_counter() - t) * 1000, 1)
        while not CS.js(host, "!!document.querySelector('nav button')"
                              " && (document.querySelector('main')"
                              "?.innerText || '').length > 20", 0.5):
            CS.pump(0.005)
        out["ms_show_to_first_render"] = round(
            (time.perf_counter() - t) * 1000, 1)
        CS.pump(2.0)
        wk_ours = sorted(webkit_pids() - wk0)
        out["webkit_processes"] = len(wk_ours)
        out["rss_kb_open_home"] = {"python": rss_kb(me),
                                   "webkit": rss_kb(wk_ours)}

        routes = {}
        for route in ("home", "dictionary", "snippets", "styles",
                      "transforms", "models", "diagnostics", "home"):
            label = CS.ROUTE_LABELS[route]
            routes[route] = timed(host, nav_action(label),
                                  ROUTE_READY.format(label=json.dumps(label)))
        out["ms_route_switch"] = routes
        out["ms_history_first_rows"] = timed(
            host, nav_action("History"),
            ON.format(label='"History"') + " && document.querySelectorAll("
            "'main [data-row]').length > 0")
        out["history_rows_rendered"] = CS.js(
            host, "document.querySelectorAll('[data-row]').length")
        out["ms_insights_load"] = timed(
            host, nav_action("Insights"),
            ON.format(label='"Insights"') + " && !!document.querySelector("
            "'main .metric, main .empty')")
        CS.pump(0.5)
        out["ms_scratchpad_open_note"] = timed(
            host, nav_action("Scratchpad") + "; setTimeout(() => document"
            ".querySelector('ul.list .row')?.click(), 0)",
            "(document.querySelector('textarea.note')?.value || '')"
            ".length > 0")
        host.set_theme("light")
        CS.pump(0.6)
        dark = ("getComputedStyle(document.documentElement).getPropertyValue"
                "('--canvas').trim().toLowerCase() === '#1a1917'")
        out["ms_theme_switch_to_dark"] = timed(
            host, "window.webkit.messageHandlers.lf.postMessage(JSON"
                  ".stringify({bridge_version: 1, request_id: 'p1', command:"
                  " 'prefs.set_theme', payload: {theme: 'dark'}}))", dark)
        CS.js(host, nav_action("History"))
        CS.pump(1.5)
        CS.js(host, "document.querySelector('main').scrollTop = 1e6; 1")
        CS.pump(1.5)
        out["rss_kb_largest_surface_history"] = {
            "python": rss_kb(me), "webkit": rss_kb(wk_ours)}
        ctl.on_close()
        CS.pump(5.0)
        out["rss_kb_closed"] = {"python": rss_kb(me),
                                "webkit": rss_kb(wk_ours)}
        ctl.state.shutdown()
        win.orderOut_(None)
    finally:
        h.close()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
