"""Run one AppKit-importing test file under the DECLARED non-native shims.

    .venv/bin/python tests/v2/lifecycle/run_with_shims.py <test file> [args]

For portable (non-macOS) orchestration evidence only: native_shims.py
installs inert stand-ins for AppKit/PyObjC/Quartz/sounddevice when (and
only when) the real modules are missing. A pass here is NOT native
verification — on the reference Mac run the test file directly.
"""

import os
import runpy
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import native_shims  # noqa: E402

installed = native_shims.install()
target = os.path.abspath(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(target))  # as `python file.py` does
print("[declared non-native shims: " + (", ".join(installed) or "none")
      + "]", file=sys.stderr)
runpy.run_path(target, run_name="__main__")
