"""Screenshots of the desktop companion over a SYNTHETIC world.

The real coordinator (the lifecycle Harness: a temporary store, fake
microphone) and the real CompanionController/WKWebView render every
route in light and dark. Every string, count and name is synthetic;
nothing reads the user's store, logs or home folder, and the page's
preferences file lives in the temporary folder.

Passive: the app is never activated and the window stays off-screen, so
nothing on the user's desktop changes. Window images come from the
window server (the window's own backing, titlebar included) when it
answers, else from the web view's snapshot.

    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/companion_screens.py --out DIR [--only home,dictionary]
        [--themes light,dark] [--size 1150x715] [--dump-fixtures DIR]
        [--script STEPS.json]

The review set (every route plus the modal and state shots the
reference-fidelity review cites), one process per theme so no selection
or tab carries from one theme's shots into the other's:

    for t in light dark; do .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/companion_screens.py --out DIR --themes $t \
        --script scripts/v2/companion_review_steps.json; done
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/v2/ui"))
sys.path.insert(0, str(ROOT / "tests/v2/lifecycle"))

import AppKit  # noqa: E402
from AppKit import (NSApplication, NSBitmapImageFileTypePNG,  # noqa: E402
                    NSBitmapImageRep, NSWorkspace)
from Foundation import NSDate, NSRunLoop  # noqa: E402

# The real coordinator runs here: the general pasteboard must be the
# isolating runner's private one.
if type(AppKit.NSPasteboard).__name__ != "_PasteboardClass":
    sys.exit("companion_screens: run under tests/v2/context/run_isolated.py"
             " (the desktop-isolating runner); refusing to start")

ROUTE_LABELS = {"home": "Home", "history": "History", "insights": "Insights",
                "dictionary": "Dictionary", "snippets": "Snippets",
                "styles": "Styles", "transforms": "Transforms",
                "scratchpad": "Scratchpad", "models": "Models",
                "diagnostics": "Diagnostics"}

APPS = (("Mail", "com.apple.mail"), ("Notes", "com.apple.Notes"),
        ("TextEdit", "com.apple.TextEdit"), ("Terminal", "com.apple.Terminal"),
        ("Xcode", "com.apple.dt.Xcode"), ("Messages", "com.apple.MobileSMS"))

SENTENCES = (
    "Can we move the design review to Thursday afternoon so the prototype has one more pass?",
    "Add oat milk, lemons and fresh basil to the shopping list.",
    "The build finished and every check passed, so I'll tag the release after lunch.",
    "Remember to water the plants before the long weekend.",
    "Draft a short note thanking the team for the careful review of the parser changes.",
    "The train leaves at seven fifteen tomorrow morning from platform four.",
    "Rename the folder to archive before sharing it with the group.",
    "Let's keep the introduction to two paragraphs and move the history to an appendix.",
    "Check the tyre pressure before the drive to the coast.",
    "Book a table for four on Friday evening, somewhere quiet near the river.",
    "Summarise the three open questions from the planning meeting in one list.",
    "Please send the slides to everyone after the call.",
    "The chart needs a clearer legend and a label on the vertical axis.",
    "Pick up the prints from the framing shop on Saturday.",
)


def pump(sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.02))


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def seed(d, store):
    """Synthetic History (with usage facts), vocabulary, snippets, style
    rules, notes and training evidence."""
    import m09_world as W
    now = dt.datetime.now().astimezone()
    base = now.replace(hour=11, minute=45, second=0, microsecond=0)
    for i, text in enumerate(SENTENCES):
        day = i // 4
        at = base - dt.timedelta(days=day, minutes=37 * (i % 4) + 3)
        app_name, bundle = APPS[i % len(APPS)]
        mode = ("llm", "llm", "basic", "llm")[i % 4]
        state = "insertion_confirmed"
        if i == 5:
            state = "saved_not_inserted"
        job_id, _raw, _app = W.seed_job(store, text.lower().rstrip(".?"),
                                        applied=text, captured=iso(at),
                                        app=app_name, bundle=bundle,
                                        state=state, mode=mode)
        words = len(text.split())
        if d._analytics is not None:
            d._analytics.record_dictation_fact(
                job_id=job_id, activity_at_utc=iso(at),
                utc_offset_minutes=int(at.utcoffset().total_seconds() // 60),
                duration_sec=words / 2.4, raw_words=words, final_words=words,
                cleanup_path=mode, mode=mode, app_name=app_name,
                app_bundle=bundle, insertion_outcome="confirmed",
                asr_ms=180 + 7 * i, cleanup_ms=420 + 11 * i,
                end_to_end_ms=900 + 23 * i, dictionary_hits=i % 3)
    vocab = d._vocab
    if vocab is not None:
        for canonical, alias, approve in (
                ("LocalFlow", "local flow", True),
                ("Parakeet", "para keet", True),
                ("SwiftUI", "swift you eye", False),
                ("Kubernetes", "cube a net ease", True),
                ("Figma", None, False)):
            eid = vocab.add_entry(canonical,
                                  aliases=[alias] if alias else [],
                                  origin="user", approved=False)
            if approve:
                vocab.approve_entry(eid)
    snips = d._snip_store
    if snips is not None:
        for trigger, content, kind in (
                ("my address", "14 Harbour Lane, Brightwater", "plain"),
                ("standup notes", "Yesterday:\nToday:\nBlockers:", "plain"),
                ("review prompt", "Review this change for correctness first,"
                 " then clarity. List issues by severity.", "prompt")):
            try:
                snips.add_snippet(trigger=trigger, name=trigger,
                                  content=content, kind=kind,
                                  allow_rewrite=False)
            except Exception as e:
                print("seed skipped:", type(e).__name__, e)
    styles = d._styles
    if styles is not None:
        for name, kind, value, mode in (
                ("Email stays polished", "category", "email", "polish"),
                ("Terminal is raw", "app", "com.apple.Terminal", "raw")):
            try:
                styles.add_rule(name=name, scope_kind=kind, scope_value=value,
                                mode=mode, number_policy="inherit")
            except Exception as e:
                print("seed skipped:", type(e).__name__, e)
    notes = d._notes_store
    if notes is not None:
        for text in ("Trip checklist\n\n- passport\n- chargers\n- train tickets",
                     "Parser ideas\n\nKeep offsets as code points everywhere.",
                     "Weekend\n\nFarmers market, then the long walk by the river."):
            try:
                notes.create_note(text)
            except Exception as e:
                print("seed skipped:", type(e).__name__, e)
    for raw in ("call the library about the overdue book",
                "the draft needs one more pass on the introduction"):
        W.seed_example(store, raw)
    # Enough synthetic evidence for Your Voice to interpret (2,000 words
    # over at least 10 examples), then the real profile computation.
    n = len(SENTENCES)
    for i in range(42):
        parts = [SENTENCES[(i * 3 + k) % n] for k in range(4)]
        text = f"note {i + 1}: " + " ".join(parts) + \
            " the parser keeps offsets as code points for the release notes"
        W.seed_example(store, text.lower(),
                       captured=iso(now - dt.timedelta(hours=5 * i + 1)))
    store.sync()
    if d._profile is not None:
        try:
            d._profile.compute()
        except Exception as e:
            print("seed skipped: profile", type(e).__name__, e)
    store.sync()


def window_image(win, host, path):
    """The window as the window server has it (titlebar included); the
    web view's own snapshot when that is unavailable."""
    try:
        import Quartz
        img = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
            win.windowNumber(), Quartz.kCGWindowImageBoundsIgnoreFraming)
        if img is not None and Quartz.CGImageGetWidth(img) > 0:
            rep = NSBitmapImageRep.alloc().initWithCGImage_(img)
            rep.representationUsingType_properties_(
                NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(
                    str(path), True)
            return "window"
    except Exception:
        pass
    box = {}
    host.webview.takeSnapshotWithConfiguration_completionHandler_(
        None, lambda img, err: box.setdefault("img", img))
    end = time.monotonic() + 3
    while "img" not in box and time.monotonic() < end:
        pump(0.05)
    if box.get("img") is None:
        return None
    rep = NSBitmapImageRep.imageRepWithData_(box["img"].TIFFRepresentation())
    rep.representationUsingType_properties_(
        NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(path), True)
    return "webview"


def js(host, src, wait=2.0):
    box = {}
    host.webview.evaluateJavaScript_completionHandler_(
        src, lambda res, err: box.update(res=res, err=err))
    end = time.monotonic() + wait
    while "res" not in box and time.monotonic() < end:
        pump(0.02)
    return box.get("res")


def click_nav(host, label):
    return js(host, "(() => { const b = [...document.querySelectorAll("
                    "'nav button')].find(x => x.textContent.trim() === "
                    + json.dumps(label) + "); if (!b) return false; "
                    "b.click(); return true; })()")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--size", default="1150x715")
    ap.add_argument("--dump-fixtures", default=None)
    ap.add_argument("--eval", default=None,
                    help="JS evaluated after each route; its result printed")
    ap.add_argument("--script", default=None,
                    help="a JSON list of [route, js] steps run after"
                         " navigating (for modals and states)")
    ap.add_argument("--package", help="Load production modules from this .app")
    ap.add_argument("--seed-out", help="Export synthetic data to a new isolated data home")
    args = ap.parse_args(argv)
    if args.package:
        resources = pathlib.Path(args.package).resolve() / "Contents/Resources"
        sys.path.insert(0, str(resources))
        import localflow
        assert pathlib.Path(localflow.__file__).resolve().is_relative_to(resources)
        print("packaged_modules", localflow.__file__)
    if args.dump_fixtures:
        # Committed fixtures never carry this machine's zone: History,
        # the seed and the reporting zone all resolve TZ (the slash form
        # is the one ids.local_zone_name() accepts).
        import os
        os.environ["TZ"] = "Etc/UTC"
        time.tzset()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    width, height = (float(x) for x in args.size.split("x"))
    routes = [r for r in (args.only.split(",") if args.only
                          else ROUTE_LABELS) if r]

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)
    front = NSWorkspace.sharedWorkspace().frontmostApplication()\
        .processIdentifier()

    import m09_world as W
    from test_lifecycle import Harness
    from localflow.v2.ui.companion.controller import CompanionController

    h = Harness(durations=[1.0], cfg={"hub_ui": "companion"})
    try:
        d = h.d
        seed(d, d.store)
        if args.seed_out:
            import shutil
            import sqlite3
            dest = pathlib.Path(args.seed_out).resolve()
            dest.mkdir(exist_ok=False)
            support = dest / "Library/Application Support/LocalFlow"
            support.mkdir(parents=True)
            def backup(conn):
                with sqlite3.connect(support / "v2.db") as copy:
                    conn.backup(copy)
            d.store.submit(backup)
            shutil.copytree(h.tmp / "artifacts", support / "v2-artifacts")
            print("synthetic_seed_exported", dest)
        spec, _sounds = W.hub_spec(d)
        spec.update(vocabulary_store=d._vocab, display_name="Alex",
                    prefs_path=h.tmp / "companion.json")
        spec["prefs_path"].write_text(json.dumps(
            {"theme": args.themes.split(",")[0]}))
        ctl = CompanionController(spec)
        d._hub = ctl
        # Harness only: an off-screen window counts as occluded and
        # WebKit then freezes transitions and animations mid-way, so the
        # capture would show a half-finished frame. Not used by the app.
        try:
            ctl.host.webview._setWindowOcclusionDetectionEnabled_(False)
        except Exception:
            pass
        win = ctl.host.window
        win.setFrame_display_(((-4000, 300), (width, height)), True)
        win.orderFront_(None)
        ctl.state.show()
        deadline = time.monotonic() + 10
        while not ctl.host._loaded and time.monotonic() < deadline:
            pump(0.05)
        pump(1.0)
        steps = json.loads(pathlib.Path(args.script).read_text()) \
            if args.script else []
        shots = []
        for theme in args.themes.split(","):
            ctl.host.set_theme(theme)
            pump(0.4)
            for route in routes:
                if not click_nav(ctl.host, ROUTE_LABELS[route]):
                    print("no nav for", route)
                    continue
                pump(1.2)
                if args.eval:
                    print("eval", route, theme, js(ctl.host, args.eval))
                kind = window_image(win, ctl.host,
                                    out / f"{route}-{theme}.png")
                shots.append((route, theme, kind))
                for step in steps:
                    # [route, js, shot name, keep open?]
                    step_route, src, name = step[:3]
                    if step_route != route:
                        continue
                    js(ctl.host, src)
                    pump(1.0)
                    if args.eval:
                        print("eval", name, theme, js(ctl.host, args.eval))
                    window_image(win, ctl.host,
                                 out / f"{name}-{theme}.png")
                    if not (len(step) > 3 and step[3]):
                        js(ctl.host, "window.dispatchEvent(new KeyboardEvent("
                                     "'keydown', {key: 'Escape'}))")
                        pump(0.4)
        if args.dump_fixtures:
            from localflow.v2.ui.companion import readmodels
            fx = pathlib.Path(args.dump_fixtures)
            fx.mkdir(parents=True, exist_ok=True)
            st = ctl.state

            def settle():
                st.wait_for_queries(5)
                pump(0.6)
                ctl.request_flush()
                pump(0.3)

            payload = {"shell": ctl.shell_model(), "views": {}}
            for view in ("home", "history", "dictionary", "settings",
                         "styles", "snippets", "transforms", "scratchpad",
                         "insights", "diagnostics", "models"):
                st.select_view(view)
                settle()
                if view == "history":
                    rows = W.history_rows(ctl)
                    if rows:
                        st.select_history_row(rows[0]["kind"], rows[0]["id"])
                        settle()
                if view == "scratchpad":
                    notes = (st.views["scratchpad"].get("data") or {}) \
                        .get("notes") or []
                    if notes:
                        st.select_scratchpad_note(notes[0]["note_id"])
                        settle()
                    payload["scratchpad_content"] = {
                        "note_id": ctl.scratchpad_editor.note_id,
                        "version": ctl.scratchpad_mirror.version,
                        "content": ctl.scratchpad_mirror.value}
                payload["views"][view] = readmodels.build(ctl, view)
                if view == "insights":
                    st.select_insights_subview("voice")
                    settle()
                    payload["views"]["insights_voice"] = \
                        readmodels.build(ctl, view)
                    st.select_insights_subview("usage")
                    settle()
                if view == "models":
                    for tab in ("evidence", "review", "splits", "export"):
                        st.select_models_subview("training")
                        st.select_training_tab(tab)
                        settle()
                        if tab == "evidence":
                            ex = ((st.views["models"].get("data") or {})
                                  .get("examples") or [])
                            if ex:
                                st.select_training_example(
                                    ex[0]["example_id"])
                                settle()
                        payload["views"][f"models_{tab}"] = \
                            readmodels.build(ctl, view)
                    st.select_models_subview("engines")
                    settle()
            payload["note"] = ("Synthetic fixtures for the browser preview"
                               " (npm run dev): read models captured from"
                               " scripts/v2/companion_screens.py over a"
                               " temporary store. Never used by the app.")
            (fx / "synthetic.json").write_text(
                json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
        print(json.dumps({
            "shots": shots, "csp_violations": ctl.csp_violations,
            "frontmost_unchanged": NSWorkspace.sharedWorkspace()
            .frontmostApplication().processIdentifier() == front}))
    finally:
        try:
            ctl.state.shutdown()
        except Exception:
            pass
        h.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
