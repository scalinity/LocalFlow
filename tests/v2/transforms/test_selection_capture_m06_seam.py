"""M11 selected-text capture on the M06 authority model: the M06 review
R4 regression and the capture/revalidation seam.

R4: ``AppDelegate._m11_capture_selection`` decided denial on the raw
``context_denied_apps`` value, so a padded or case-variant entry, or a
malformed list, let a selected-text transform read a denied app's
selection while the M06 collector denied the same app. Every R4 case
drives the real ``AppDelegate`` (configuration through ``configure`` and
``config.context_policy``) over a synthetic host that records every
Accessibility call: a denied app must see NONE — not merely a ``None``
capture. The allowed control proves the instrument sees reads.

Seam: the capture records the selection in the host's own units
(``selected_range_utf16``; code points only when exact) and the field's
own window element, so strict accept-time revalidation applies the
M06/M08 rules (contracts/insertion.md) instead of a title alone.

    .venv/bin/python tests/v2/context/run_isolated.py \\
        tests/v2/transforms/test_selection_capture_m06_seam.py \\
        [--code-root DIR]

``--code-root`` runs the same cases against another checkout (the
stale M11 reader on the M06 head, or the historical M11 branch).
Synthetic apps and text only.
"""

import argparse
import pathlib
import sys
import types

ap = argparse.ArgumentParser()
ap.add_argument("--code-root",
                default=str(pathlib.Path(__file__).resolve().parents[3]))
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(CODE / "tests" / "v2" / "transforms"))

import test_transform_pipeline as tp  # noqa: E402
from localflow.v2.insertion.validation import validate_target  # noqa: E402

DENIED = "com.example.vault"
ALLOWED = "com.example.editor"
STRICT = {"job_id": "tcand-seam", "attempt": 1, "strict_replacement": True}


class Host:
    """One text field in one window of one synthetic app. Offsets are
    UTF-16 units, as on macOS Accessibility. Every call except
    ``frontmost`` (NSWorkspace identity, not Accessibility) is
    recorded."""

    def __init__(self, bundle, text="alpha rewrite this sentence omega",
                 selected="rewrite this sentence", title="Draft",
                 window="win-1", pid=4242):
        self.app = {"bundle": bundle, "name": "Synthetic", "pid": pid}
        self.text, self.title, self.window = text, title, window
        start = self.units(text[:text.index(selected)])
        self.selection = (start, start + self.units(selected))
        self.calls = []

    @staticmethod
    def units(s):
        return len(s.encode("utf-16-le", "surrogatepass")) // 2

    def frontmost(self):
        return dict(self.app)

    def focused_element(self):
        self.calls.append("focused_element")
        return "field"

    def attribute(self, el, name):
        self.calls.append(name)
        s, e = self.selection
        return {"AXRole": "AXTextArea", "AXSelectedTextRange": (s, e - s),
                "AXWindow": self.window}.get(name)

    def focused_window_title(self, el):
        self.calls.append("focused_window_title")
        return self.title

    def number_of_characters(self, el):
        self.calls.append("number_of_characters")
        return self.units(self.text)

    def string_for_range(self, el, start, length):
        self.calls.append("string_for_range")
        b = self.text.encode("utf-16-le", "surrogatepass")
        return b[2 * start:2 * (start + length)].decode(
            "utf-16-le", "surrogatepass")


def harness(deny, **cfg):
    return tp.Harness([1.0], cfg=dict({"context_denied_apps": deny}, **cfg))


def capture(deny, host, **cfg):
    h = harness(deny, **cfg)
    try:
        h.d._insertion = types.SimpleNamespace(host=host)
        return h.d._m11_capture_selection()
    finally:
        h.close()


def assert_nothing_read(deny, bundle, reason):
    host = Host(bundle)
    cap, why = capture(deny, host)
    assert cap is None, f"deny={deny!r}: a capture was returned"
    assert host.calls == [], \
        f"deny={deny!r}: prohibited Accessibility reads {host.calls}"
    assert why == reason, f"deny={deny!r}: reason {why!r}"


def test_r4_allowed_app_selection_is_read():
    host = Host(ALLOWED)
    cap, why = capture([DENIED], host)
    assert cap is not None, why
    assert cap["source"] == "rewrite this sentence", cap["source"]
    # The instrument sees content reads — so zero below means zero.
    assert "AXSelectedTextRange" in host.calls, host.calls
    assert "string_for_range" in host.calls, host.calls
    print("ok  R4 control: an allowed app's selection is read")


def test_r4_denied_app_reads_nothing():
    assert_nothing_read([DENIED], DENIED, "app_denied")
    print("ok  R4 an exactly listed app: no Accessibility call")


def test_r4_padded_deny_entry_reads_nothing():
    for deny in ([f" {DENIED}"], [f"{DENIED}\t"], [f"  {DENIED}\n"]):
        assert_nothing_read(deny, DENIED, "app_denied")
    print("ok  R4 a padded deny entry: no Accessibility call")


def test_r4_case_variant_deny_entry_reads_nothing():
    # CFBundleIdentifier: "Bundle IDs are case-insensitive" (Apple).
    assert_nothing_read(["COM.Example.VAULT"], DENIED, "app_denied")
    assert_nothing_read([DENIED], "com.Example.Vault", "app_denied")
    print("ok  R4 a case-variant deny entry or bundle: no Accessibility "
          "call")


def test_r4_malformed_deny_list_denies_every_app_for_transforms():
    # The deny intent cannot be honored, so no app is read — including
    # one the intended list would not have named.
    for deny in (DENIED, [DENIED, ""], [DENIED, 42], {"app": DENIED}):
        assert_nothing_read(deny, ALLOWED, "deny_list_invalid")
    print("ok  R4 a malformed deny list: transforms read no app")


def test_r4_m06_collector_and_m11_capture_agree():
    for deny, bundle in (([DENIED], DENIED), ([f" {DENIED} "], DENIED),
                         (["COM.EXAMPLE.VAULT"], DENIED),
                         ([DENIED], "Com.Example.Vault"),
                         ([DENIED], ALLOWED)):
        host = Host(bundle)
        h = harness(deny, context_enabled=True)
        try:
            h.d._context.frontmost = host.frontmost
            m06 = h.d._context.capture_identity().denied
            h.d._insertion = types.SimpleNamespace(host=host)
            cap, _ = h.d._m11_capture_selection()
        finally:
            h.close()
        m11 = cap is None and host.calls == []
        assert m06 == m11 == (bundle != ALLOWED), \
            f"deny={deny!r} bundle={bundle!r}: M06 denied={m06}, " \
            f"M11 read nothing={m11}"
    print("ok  R4 the M06 collector and the M11 capture take one decision")


def test_seam_capture_records_host_units_and_exact_code_points():
    # One astral character before the selection: 2 UTF-16 units, 1 code
    # point — the two conventions differ by one.
    host = Host(ALLOWED, text="\U0001F600 alpha rewrite this omega",
                selected="rewrite this")
    cap, why = capture([], host)
    assert cap is not None, why
    f = cap["snapshot"].field
    assert cap["source"] == "rewrite this"
    assert f.selected_range_utf16 == (9, 21), f.selected_range_utf16
    assert f.selected_range == (8, 20), f.selected_range
    lease, ver = validate_target(host, cap["snapshot"], STRICT)
    assert lease is not None and ver.get("strict") == "pass", ver
    # A prefix beyond the bounded read: code points are not exact, so
    # none are claimed; the host units still carry the authority.
    far = Host(ALLOWED, text="x" * 300 + "\U0001F600 rewrite this",
               selected="rewrite this")
    cap, why = capture([], far)
    assert cap is not None, why
    assert cap["snapshot"].field.selected_range is None, \
        cap["snapshot"].field.selected_range
    assert cap["snapshot"].field.selected_range_utf16 == (303, 315)
    lease, ver = validate_target(far, cap["snapshot"], STRICT)
    assert lease is not None and ver.get("strict") == "pass", ver
    print("ok  seam: host units recorded, code points only when exact")


def test_seam_other_window_with_equal_title_refuses_strict_accept():
    host = Host(ALLOWED)
    cap, why = capture([], host)
    assert cap is not None, why
    lease, ver = validate_target(host, cap["snapshot"], STRICT)
    assert lease is not None, f"positive control: same window {ver}"
    host.window = "win-2"            # same title, text and selection
    lease, ver = validate_target(host, cap["snapshot"], STRICT)
    assert lease is None and ver.get("window") == "fail", ver
    print("ok  seam: another window under an equal title refuses")


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    failed = []
    for fn in tests:
        try:
            fn()
        except Exception as e:
            failed.append(fn.__name__)
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}"[:400])
    print(f"{len(tests) - len(failed)}/{len(tests)} selection-capture "
          f"M06 seam regressions passed (code root {CODE.name})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
