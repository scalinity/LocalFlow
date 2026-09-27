"""Run the native M12 Scratchpad suite's ACTIVE tier as a launched app.

macOS activation is cooperative: a process started from a terminal may
ask to become active and be refused, and an inactive app has no key
window, so the active cases (typing, ⌘A, Tab, popups, buttons) cannot
run from the terminal directly. An app LaunchServices opens is activated
at launch. This builds a minimal launcher bundle in a temporary folder
(never in the repository), records the application in front, opens the
bundle — which runs ``tests/v2/notes/test_native_m12_scratchpad.py --activate``
under ``tests/v2/context/run_isolated.py`` for the given tree — waits for
it to finish, and prints the result. The suite keeps the launch
activation for the run and hands focus back to the recorded application
once, at the end. Run it only with the owner's go-ahead: keep hands off
the keyboard and mouse while it runs (about two minutes).

    .venv/bin/python scripts/v2/native_m12_active.py --json OUT [--tree ROOT]

``--tree`` is the checkout to test (default: this repository); it must
hold ``.venv`` and the suite. The passive tier runs without this script.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>local.localflow.m12-scratchpad-test</string>
  <key>CFBundleName</key><string>LF-M12-ScratchpadTest</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
"""

# args: <tree root> <result json> <pid to restore>
RUN = """#!/bin/zsh
cd "$1" || exit 90
export LF_NATIVE_RESTORE_PID="$3"
exec "$1/.venv/bin/python" tests/v2/context/run_isolated.py \\
    tests/v2/notes/test_native_m12_scratchpad.py --activate --json "$2" \\
    > "$2.log" 2>&1
"""


def frontmost_pid() -> int:
    from AppKit import NSWorkspace
    return NSWorkspace.sharedWorkspace().frontmostApplication() \
        .processIdentifier()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--tree", default=str(ROOT))
    args = ap.parse_args()
    out = pathlib.Path(args.json).resolve()
    tree = pathlib.Path(args.tree).resolve()
    with tempfile.TemporaryDirectory(prefix="lf-m12-launcher-") as tmp:
        app = pathlib.Path(tmp) / "LF-M12-ScratchpadTest.app"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_text(INFO_PLIST)
        run = app / "Contents" / "MacOS" / "run"
        run.write_text(RUN)
        run.chmod(0o755)
        subprocess.run(["open", "-W", "-n", str(app), "--args", str(tree),
                        str(out), str(frontmost_pid())], check=True)
    if not out.is_file():
        print(f"no result; see {out}.log")
        return 2
    doc = json.loads(out.read_text())
    print(json.dumps({k: doc.get(k) for k in (
        "launch_activation_granted", "prior_frontmost_restored",
        "passed", "ran", "code_root_sha")}))
    return 0 if doc.get("passed") == doc.get("ran") else 1


if __name__ == "__main__":
    raise SystemExit(main())
