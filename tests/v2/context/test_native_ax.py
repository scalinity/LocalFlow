"""EV-08 native half / M06 remediation: real macOS Accessibility, no shims.

Drives the production ``SystemAXHost``, providers, collector and the M08
native range bridge against ``native_ax_target.py`` — a synthetic window
owned by a helper process that is never activated and sits off-screen.
Every element is reached through that helper's own application element
(``focused_element_for(pid)``); the system-wide focused element, and so
whatever the user is doing, is never read.

Needs the real PyObjC frameworks and an Accessibility grant for the
terminal that runs it. When either is missing the suite prints NOT RUN
with the reason and exits 2 — it is never reported as passed.

Run: .venv/bin/python tests/v2/context/test_native_ax.py
"""

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
TARGET = pathlib.Path(__file__).with_name("native_ax_target.py")

TEXT_UNICODE = "A\U0001F600B é café userId end"
TEXT_ASCII = "alpha userId beta fooBar gamma"


def not_run(reason):
    print(f"NOT RUN: native Accessibility suite — {reason}")
    raise SystemExit(2)


try:
    import ApplicationServices as AS
except Exception as e:           # pragma: no cover — non-macOS
    not_run(f"PyObjC unavailable ({type(e).__name__})")
if not AS.AXIsProcessTrusted():
    not_run("this terminal holds no Accessibility grant")

from localflow.v2.context import providers as prov  # noqa: E402
from localflow.v2.context.collector import ContextCollector  # noqa: E402
from localflow.v2.insertion import validation as val  # noqa: E402
from localflow.v2.insertion.hosts import SystemInsertionHost  # noqa: E402


class Target:
    def __init__(self, **spec):
        self.proc = subprocess.Popen(
            [sys.executable, str(TARGET), json.dumps(spec)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.pid = int(self.proc.stdout.readline().split()[1])
        time.sleep(0.6)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class LoggingHost(prov.SystemAXHost):
    def __init__(self):
        super().__init__()
        self.names = []

    def read(self, el, name):
        self.names.append(name)
        return super().read(el, name)


CONTENT = {"AXSelectedText", "AXSelectedTextRange", "AXStringForRange",
           "AXValue", "AXPlaceholderValue", "AXDocument",
           "AXNumberOfCharacters", "AXURL"}


def test_range_bridge_and_units():
    with Target(text=TEXT_UNICODE, selection=[1, 2]) as t:
        host = prov.SystemAXHost()
        el = host.focused_element_for(t.pid)
        assert el is not None and host.element_pid(el) == t.pid
        raw, err = host.read(el, "AXSelectedTextRange")
        assert err == 0 and type(raw).__name__ == "AXValueRef", raw
        assert prov.ax_range(raw) == (1, 2)          # UTF-16 units
        assert host.string_for_range(el, 0, 3) == "A\U0001F600"
        # A boundary inside the surrogate pair never survives a flank.
        assert prov._utf16_clip(host.string_for_range(el, 0, 2), 2) == "A"
        assert host.number_of_characters(el) == prov.utf16_len(TEXT_UNICODE)
        assert host.number_of_characters(el) == len(TEXT_UNICODE) + 1
    print("ok  native AXValue range decodes/boxes; offsets are UTF-16 units")


def test_read_field_native_offsets_and_flanks():
    with Target(text=TEXT_UNICODE, selection=[1, 2]) as t:
        host = LoggingHost()
        r = prov.read_field(host, False, el=host.focused_element_for(t.pid))
        f = r.value
        assert f.classification == "text"
        assert f.selected_text == "\U0001F600"
        assert f.selected_range_utf16 == (1, 3)
        assert f.selected_range == (1, 2)             # exact code points
        assert f.preceding_text == "A"
        assert f.following_text == "B é café userId end"
    with Target(text=TEXT_ASCII, selection=[6, 0]) as t:
        host = LoggingHost()
        r = prov.read_field(host, False, el=host.focused_element_for(t.pid))
        f = r.value
        assert f.preceding_text == "alpha " and f.selected_text is None
        assert "AXSelectedText" not in host.names    # a caret reads none
        assert prov.extract_identifiers(f) == {"user id": "userId",
                                               "foo bar": "fooBar"}
    print("ok  native field: flanks read, emoji selection converted "
          "exactly, identifiers extracted")


def test_secure_field_native_zero_content():
    with Target(text=TEXT_ASCII, selection=[0, 0],
                first_responder="secure") as t:
        host = LoggingHost()
        el = host.focused_element_for(t.pid)
        host.names = []           # the element's own reads only
        r = prov.read_field(host, False, el=el)
        assert r.value.classification == "secure", r.value
        assert r.reason == "secure_field"
        assert set(host.names) <= {"AXRole", "AXSubrole"}, host.names
    print("ok  native secure field: role/subrole only, zero content reads")


def test_window_identity_and_element_equality():
    with Target(text=TEXT_ASCII, selection=[0, 0],
                title="LF-M06 window A") as t:
        host = prov.SystemAXHost()
        el = host.focused_element_for(t.pid)
        win = host.window_of(el)
        assert host.read(win, "AXTitle")[0] == "LF-M06 window A"
        # The field has no AXFocusedWindow of its own (the historical
        # lookup); AXWindow is the field's own window.
        assert host.read(el, "AXFocusedWindow")[1] == prov.AX_ERR_UNSUPPORTED
        assert host.focused_element_for(t.pid) == el   # CFEqual identity
        # The window identity M08 compares: the element M06 recorded
        # equals the live AXWindow the insertion host reads.
        assert SystemInsertionHost().attribute(el, "AXWindow") == win
        assert AS.AXUIElementSetMessagingTimeout(el, 0.2) == 0
    print("ok  native window via AXWindow; element identity stable; "
          "timeout configuration returns kAXErrorSuccess")


def test_collector_end_to_end_native():
    with Target(text=TEXT_ASCII, selection=[6, 0],
                title="LF-M06 window B") as t:
        ident = {"bundle": "org.python.python", "name": "Synthetic",
                 "pid": t.pid}
        c = ContextCollector(enabled=True, deadline_ms=250,
                             frontmost=lambda: ident)
        tgt = c.capture_identity()
        k = c.begin(tgt)
        assert k.done.wait(5)
        s = c.finalize(k, target_snapshot_id=tgt.target_snapshot_id)
        assert s.window_title == "LF-M06 window B"
        assert s.identifiers == {"user id": "userId", "foo bar": "fooBar"}
        assert s.field.selected_range_utf16 == (6, 6)
    print("ok  native collector: owned element, window, flanks, "
          "identifiers end to end")


def test_m08_native_range_bridge():
    with Target(text=TEXT_ASCII, selection=[6, 6]) as t:
        el = prov.SystemAXHost().focused_element_for(t.pid)
        ih = SystemInsertionHost()
        assert val._as_range(ih.attribute(el, "AXSelectedTextRange")) \
            == (6, 12)
        assert ih.string_for_range(el, 6, 6) == "userId"
    print("ok  M08 native bridge: live AXValue range decoded, "
          "AXStringForRange boxed")


def test_dead_process_element_fails_closed():
    t = Target(text=TEXT_ASCII, selection=[6, 6])
    host = LoggingHost()
    el = host.focused_element_for(t.pid)
    t.close()
    time.sleep(0.3)
    host.names = []
    r = prov.read_field(host, False, el=el)
    content = set(host.names) & CONTENT
    assert content == set(), content
    assert r.value is None or r.value.classification != "text", r.value
    print(f"ok  element of a dead process: {r.reason or 'no role'}; "
          "no content read")


def main():
    for fn in (test_range_bridge_and_units,
               test_read_field_native_offsets_and_flanks,
               test_secure_field_native_zero_content,
               test_window_identity_and_element_equality,
               test_collector_end_to_end_native,
               test_m08_native_range_bridge,
               test_dead_process_element_fails_closed):
        fn()
    print("all native Accessibility tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
