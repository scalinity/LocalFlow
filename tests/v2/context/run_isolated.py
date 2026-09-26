"""Run one test file NATIVELY with the live desktop isolated.

    .venv/bin/python tests/v2/context/run_isolated.py <test file> [args]

On a Mac whose terminal holds the Accessibility grant, an app-level
harness that keeps the default ``ContextCollector`` (``SystemAXHost``)
would read whatever field is focused while the suite runs — another
app's text, not a fixture. This runner keeps the real AppKit/PyObjC
modules (unlike ``tests/v2/lifecycle/run_with_shims.py``) and replaces
only the calls that touch the live desktop: every AXUIElement read,
write or action returns ``kAXErrorAPIDisabled``, ``AXIsProcessTrusted``
reports untrusted, and ``CGEventPost`` posts nothing. Each blocked call
is counted and the totals are printed on exit, so a suite that silently
reached for the desktop is visible.

A pass here is native for imports and object construction; it is NOT
native Accessibility evidence (that is ``test_native_ax.py``, which
drives a synthetic window it owns).
"""

import atexit
import os
import runpy
import sys

import ApplicationServices as AS
import Quartz

K_AX_ERROR_API_DISABLED = -25211
BLOCKED = {"ax": 0, "trust_queries": 0, "cg_event_post": 0}

_AX_CALLS = (
    "AXUIElementCopyAttributeValue",
    "AXUIElementCopyAttributeValues",
    "AXUIElementCopyMultipleAttributeValues",
    "AXUIElementCopyAttributeNames",
    "AXUIElementCopyParameterizedAttributeValue",
    "AXUIElementCopyParameterizedAttributeNames",
    "AXUIElementCopyActionNames",
    "AXUIElementCopyElementAtPosition",
    "AXUIElementSetAttributeValue",
    "AXUIElementPerformAction",
)


def _blocked_ax(*_a, **_k):
    BLOCKED["ax"] += 1
    return (K_AX_ERROR_API_DISABLED, None)


def _blocked_post(*_a, **_k):
    BLOCKED["cg_event_post"] += 1


for _name in _AX_CALLS:
    if hasattr(AS, _name):
        setattr(AS, _name, _blocked_ax)


def _untrusted(*_a, **_k):
    BLOCKED["trust_queries"] += 1
    return False


AS.AXIsProcessTrusted = _untrusted
AS.AXIsProcessTrustedWithOptions = _untrusted
Quartz.CGEventPost = _blocked_post


@atexit.register
def _report():
    print(f"[desktop isolated: ax_calls_blocked={BLOCKED['ax']}"
          f" ax_trust_queries={BLOCKED['trust_queries']}"
          f" cg_event_posts_blocked={BLOCKED['cg_event_post']}]",
          file=sys.stderr, flush=True)


_real_exit = os._exit


def _exit_with_report(code):
    # Suites that end with os._exit skip atexit; report first.
    _report()
    _real_exit(code)


os._exit = _exit_with_report


target = os.path.abspath(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(target))   # as `python file.py` does
runpy.run_path(target, run_name="__main__")
