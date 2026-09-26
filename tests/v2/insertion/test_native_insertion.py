"""M08 owned-native qualification: real Accessibility, real NSPasteboard.

Drives the PRODUCTION InsertionService, validation and observer against
``native_insertion_target.py`` — a helper process of this suite's own,
never activated, off-screen, synthetic text only. The host is
``SystemInsertionHost`` with ONE override, ``frontmost()`` (the helper's
identity instead of the real frontmost app); every Accessibility call —
element acquisition, ownership, attributes, settability, writes, ranged
reads — is the production adapter's. The pasteboard is the production
``SystemPasteboard`` over a private, uniquely named NSPasteboard (the
user's clipboard is never read or written). The ⌘V consumer is EMULATED
by the helper, which reads that named pasteboard and inserts into its
first responder when the keyboard double's ``post_paste`` asks — no key
event is ever posted; that emulation is the disclosed limit of the
clipboard evidence. The destination text is witnessed by the helper's
own AppKit state, never by Accessibility.

Cases marked ``[diagnostic]`` re-run an AX-method case with a test host
that makes the settability call itself (with the out-parameter PyObjC
requires); they never count toward the result. At 4260fe3 production
omitted that parameter and every surface looked unsettable natively —
these cases were the independent proof of the fix. The clipboard cases
declare a surface whose AXSelectedText is not settable
(``ClipboardSurface``): that is when production uses the clipboard.

Needs PyObjC and an Accessibility grant for the terminal that runs it;
otherwise it prints NOT RUN with the reason and exits 2 — never a pass.
Run natively (NOT under run_isolated.py — it must reach its own helper):

    .venv/bin/python tests/v2/insertion/test_native_insertion.py [--json OUT]
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
TARGET = pathlib.Path(__file__).with_name("native_insertion_target.py")


def not_run(reason):
    print(f"NOT RUN: native M08 insertion suite — {reason}")
    raise SystemExit(2)


try:
    import ApplicationServices as AS
    from AppKit import (NSPasteboard, NSPasteboardItem,
                        NSPasteboardTypeString)
except Exception as e:           # pragma: no cover — non-macOS
    not_run(f"PyObjC unavailable ({type(e).__name__})")
if not AS.AXIsProcessTrusted():
    not_run("this terminal holds no Accessibility grant")

from localflow.v2 import ids, store as store_mod  # noqa: E402
from localflow.v2.context.snapshot import (ContextSnapshot,  # noqa: E402
                                           FieldContext, TargetSnapshot)
from localflow.v2.insertion import service as service_mod  # noqa: E402
from localflow.v2.insertion.hosts import (SystemInsertionHost,  # noqa: E402
                                          SystemPasteboard)
from localflow.v2.insertion.service import InsertionService  # noqa: E402

CONTENT_ATTRS = {"AXSelectedText", "AXSelectedTextRange", "AXValue",
                 "AXNumberOfCharacters", "AXStringForRange"}
OLD = "CANARY_OLD_CLIPBOARD"


def u16(s):
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


class Helper:
    def __init__(self, **spec):
        self.proc = subprocess.Popen(
            [sys.executable, str(TARGET), json.dumps(spec)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.pid = int(self.proc.stdout.readline().split()[1])
        self.lock = threading.Lock()
        self.bundle = f"com.example.m08-native-helper.{self.pid}"
        time.sleep(0.6)

    def cmd(self, **m):
        with self.lock:
            self.proc.stdin.write(json.dumps(m) + "\n")
            self.proc.stdin.flush()
            return json.loads(self.proc.stdout.readline())

    def view(self, name):
        return self.cmd(cmd="state")["views"][name]

    def identity(self):
        return {"bundle": self.bundle, "name": "M08NativeHelper",
                "pid": self.pid}

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class HelperHost(SystemInsertionHost):
    """The production host; only ``frontmost`` answers the test's
    identity. Optionally logs every call by (element, attribute)."""

    def __init__(self, ident, log=None):
        super().__init__()
        self._ident = ident
        self.log = log

    def frontmost(self):
        return self._ident()

    def _note(self, el, name):
        if self.log is not None:
            self.log.append((el, name))

    def attribute(self, el, name):
        self._note(el, name)
        return super().attribute(el, name)

    def string_for_range(self, el, start, length):
        self._note(el, "AXStringForRange")
        return super().string_for_range(el, start, length)

    def number_of_characters(self, el):
        self._note(el, "AXNumberOfCharacters")
        return super().number_of_characters(el)

    def is_settable(self, el, name):
        self._note(el, f"settable:{name}")
        return super().is_settable(el, name)

    def set_attribute(self, el, name, value):
        self._note(el, f"set:{name}")
        return super().set_attribute(el, name, value)


class DiagHost(HelperHost):
    """[diagnostic] ``is_settable`` made directly with the out-parameter
    PyObjC needs. At 4260fe3 production passed two arguments and always
    answered False (no AX method, no undo natively); the production fix
    makes the same call, so these cases now confirm it independently."""

    def is_settable(self, el, name):
        self._note(el, f"settable:{name}")
        try:
            err, ok = AS.AXUIElementIsAttributeSettable(el, name, None)
        except Exception:
            return False
        return err == 0 and bool(ok)


class ClipboardSurface(HelperHost):
    """A surface whose AXSelectedText is not settable — the condition
    under which production uses the clipboard method (declared: the
    helper's text view itself is settable)."""

    def is_settable(self, el, name):
        self._note(el, f"settable:{name}")
        if name == "AXSelectedText":
            return False
        return super().is_settable(el, name)


class Unreadable(ClipboardSurface):
    """Content reads unavailable (an unobservable clipboard surface)."""

    def string_for_range(self, el, start, length):
        self._note(el, "AXStringForRange")
        return None

    def number_of_characters(self, el):
        self._note(el, "AXNumberOfCharacters")
        return None


class AckBoard:
    """A real private NSPasteboard whose setString_forType_ and/or
    writeObjects_ report refusal (and store nothing), and an optional
    hook before the N-th clearContents."""

    def __init__(self, board, *, fail_set_string=False,
                 fail_write_objects=False, before_clear=None):
        self._b = board
        self.fail_set_string = fail_set_string
        self.fail_write_objects = fail_write_objects
        self.before_clear = before_clear or {}
        self.clears = 0

    def clearContents(self):
        self.clears += 1
        hook = self.before_clear.get(self.clears)
        if hook is not None:
            hook(self._b)
        return self._b.clearContents()

    def setString_forType_(self, s, t):
        if self.fail_set_string:
            return False
        return self._b.setString_forType_(s, t)

    def writeObjects_(self, objs):
        if self.fail_write_objects:
            return False
        return self._b.writeObjects_(objs)

    def __getattr__(self, name):
        return getattr(self._b, name)


def private_board():
    return NSPasteboard.pasteboardWithUniqueName()


def seed_board(board, text=OLD, rtf=True):
    """The 'user's clipboard' of this case: synthetic, on a private board."""
    board.clearContents()
    it = NSPasteboardItem.alloc().init()
    it.setString_forType_(text, NSPasteboardTypeString)
    if rtf:
        it.setData_forType_(b"{\\rtf1 synthetic old}", "public.rtf")
    board.writeObjects_([it])


def production_pasteboard(board):
    """The production SystemPasteboard over a private board (built
    without ever asking for the general pasteboard)."""
    pb = SystemPasteboard.__new__(SystemPasteboard)
    pb._pb = board
    return pb


def board_state(board):
    b = getattr(board, "_b", board)
    s = b.stringForType_(NSPasteboardTypeString)
    return {"string": str(s) if s is not None else None,
            "types": [str(t) for t in (b.types() or [])]}


class HelperKeyboard:
    """``post_paste`` asks the helper to consume the named pasteboard
    (now, or after ``delay`` seconds) — never a key event."""

    def __init__(self, helper, board_name, delay=0.0):
        self.helper = helper
        self.name = board_name
        self.delay = delay
        self.posts = 0
        self.consumed = []

    def post_paste(self):
        self.posts += 1

        def consume():
            self.consumed.append(self.helper.cmd(
                cmd="consume_paste", pasteboard=self.name).get("consumed"))
        if self.delay:
            threading.Timer(self.delay, consume).start()
        else:
            consume()
        return True


def snapshot(host, helper, el, *, sel=None, sel_text=None, pre=None,
             fol=None):
    role = host.attribute(el, "AXRole")
    win = host.attribute(el, "AXWindow")
    title = host.attribute(win, "AXTitle") if win is not None else None
    ident = helper.identity()
    target = TargetSnapshot(
        target_snapshot_id=ids.new_id("tgt"), app_bundle=ident["bundle"],
        app_name=ident["name"], app_pid=ident["pid"], category="unknown",
        captured_at_utc=ids.now_utc_iso())
    field = FieldContext(role=str(role) if role else None,
                         classification="text", selected_text=sel_text,
                         selected_range=None, selected_range_utf16=sel,
                         preceding_text=pre, following_text=fol)
    return ContextSnapshot(
        context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
        target=target, field=field,
        window_title=str(title) if title else None, window_element=win,
        captured_at_utc=ids.now_utc_iso())


class Env:
    def __init__(self, helper, host, board, *, window=0.0, settle=0.3,
                 delay=0.0):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.store = store_mod.Store(root / "v2.db",
                                     backup_dir=root / "backups")
        self.events = []
        name = str(getattr(board, "_b", board).name())
        self.kb = HelperKeyboard(helper, name, delay=delay)
        self.svc = InsertionService(
            host=host, pasteboard=production_pasteboard(board),
            keyboard=self.kb, store=self.store,
            emit=lambda ev, **kw: self.events.append((ev, kw)),
            restore_clipboard=True, observation_window_sec=window,
            settle_sec=settle)

    def run(self, text, job, on_observation=None):
        box, done = {}, threading.Event()
        self.svc.submit(text, job, lambda r: (box.__setitem__("r", r),
                                              done.set()),
                        on_observation=on_observation)
        assert done.wait(20), "transaction did not finish"
        return box["r"]

    def close(self):
        self.store.sync()
        self.store.close()
        self.tmp.cleanup()


def job(s, **kw):
    j = {"job_id": ids.new_id("job"), "attempt": 1,
         "context_snapshot": s, "observation_consent": False}
    j.update(kw)
    return j


def res(r):
    return {"state": r.state, "reason_code": r.reason_code,
            "method": r.method, "readback": r.readback,
            "owned": [r.owned_start, r.owned_end],
            "clipboard": {k: r.clipboard.get(k) for k in
                          ("restore_skipped_reason", "restored_types",
                           "publish_failed")}}


CASES = []


def case(cid, *, diagnostic=False):
    def deco(fn):
        CASES.append((cid, fn, diagnostic))
        return fn
    return deco


# ---- F07: native UTF-16 ranges through the service ----------------------

def _astral(host_cls):
    h = Helper(f1="A\U0001F600B")
    try:
        h.cmd(cmd="select", view="F1", sel=[4, 0])
        host = host_cls(h.identity)
        board = private_board()
        seed_board(board)
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        r = env.run("X\U0001F600Y", job(snapshot(host, h, el, sel=(4, 4))))
        text = h.view("F1")["text"]
        env.close()
        ok = (text == "A\U0001F600BX\U0001F600Y"
              and r.state in ("confirmed", "posted_unverified")
              and (r.state != "confirmed"
                   or (r.owned_start, r.owned_end) == (4, 8)))
        return ok, {"appkit_text": text, "result": res(r)}
    finally:
        h.close()


@case("LF-M08-F07-C01")
def f07_c01():
    return _astral(HelperHost)


@case("LF-M08-F07-C01", diagnostic=True)
def f07_c01_diag():
    return _astral(DiagHost)


def _replace_and_undo(host_cls, text, sel16, new, pre, fol):
    h = Helper(f1=text)
    try:
        h.cmd(cmd="select", view="F1", sel=[sel16[0], sel16[1] - sel16[0]])
        host = host_cls(h.identity)
        board = private_board()
        seed_board(board)
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        raw_type = type(host.attribute(el, "AXSelectedTextRange")).__name__
        selected = text.encode("utf-16-le", "surrogatepass")[
            sel16[0] * 2:sel16[1] * 2].decode("utf-16-le", "surrogatepass")
        r = env.run(new, job(snapshot(host, h, el, sel=sel16,
                                      sel_text=selected, pre=pre,
                                      fol=fol)))
        after = h.view("F1")["text"]
        u = env.svc.undo_last()
        restored = h.view("F1")["text"]
        env.close()
        expected_after = text[:len(pre)] + new + text[len(pre) +
                                                      len(selected):]
        ok = (after == expected_after and u.get("outcome") == "undone"
              and restored == text)
        return ok, {"appkit_after": after, "appkit_after_undo": restored,
                    "undo": u, "result": res(r),
                    "raw_range_type": raw_type}
    finally:
        h.close()


@case("LF-M08-F07-C02")
def f07_c02():
    return _replace_and_undo(HelperHost, "pre é post", (4, 6),
                             "É", "pre ", " post")


@case("LF-M08-F07-C02", diagnostic=True)
def f07_c02_diag():
    return _replace_and_undo(DiagHost, "pre é post", (4, 6),
                             "É", "pre ", " post")


ZWJ = "\U0001F469‍\U0001F4BB"


@case("LF-M08-F07-C03")
def f07_c03():
    return _replace_and_undo(HelperHost, f"before {ZWJ} after", (7, 12),
                             "X", "before ", " after")


@case("LF-M08-F07-C03", diagnostic=True)
def f07_c03_diag():
    return _replace_and_undo(DiagHost, f"before {ZWJ} after", (7, 12),
                             "X", "before ", " after")


def _axvalue(host_cls):
    ok, w = _replace_and_undo(host_cls, "keep OLD words", (5, 8), "NEW",
                              "keep ", " words")
    ok = ok and w["raw_range_type"] == "AXValueRef"
    return ok, w


@case("LF-M08-F07-C04")
def f07_c04():
    return _axvalue(HelperHost)


@case("LF-M08-F07-C04", diagnostic=True)
def f07_c04_diag():
    return _axvalue(DiagHost)


# ---- F12-C04: identical replacement ------------------------------------

def _identical(host_cls):
    h = Helper(f1="say hello now")
    try:
        h.cmd(cmd="select", view="F1", sel=[4, 5])
        host = host_cls(h.identity)
        board = private_board()
        seed_board(board)
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        r = env.run("hello", job(snapshot(host, h, el, sel=(4, 9),
                                          sel_text="hello", pre="say ",
                                          fol=" now")))
        v = h.view("F1")
        env.close()
        # Confirmation is acceptable ONLY with the AX method's
        # selection-moved proof; otherwise honest ambiguity.
        ok = v["text"] == "say hello now" and (
            (r.state == "confirmed" and r.method == "ax_replacement")
            or (r.state == "posted_unverified"
                and r.readback == "match_ambiguous"))
        return ok, {"appkit": v, "result": res(r)}
    finally:
        h.close()


@case("LF-M08-F12-C04")
def f12_c04():
    return _identical(HelperHost)


@case("LF-M08-F12-C04", diagnostic=True)
def f12_c04_diag():
    return _identical(DiagHost)


# ---- F09: native acknowledgments -----------------------------------------

@case("LF-M08-F09-C04")
def f09_c04():
    h = Helper(f1="field ")
    try:
        host = ClipboardSurface(h.identity)
        real = private_board()
        seed_board(real)
        board = AckBoard(real, fail_set_string=True)
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        r = env.run("dictated", job(snapshot(host, h, el, sel=(6, 6))))
        text = h.view("F1")["text"]
        bs = board_state(board)
        posts = env.kb.posts
        env.close()
        ok = (posts == 0 and r.state == "failed"
              and r.reason_code == "clipboard_publish_failed"
              and text == "field " and bs["string"] == OLD
              and "public.rtf" in bs["types"])
        return ok, {"posts": posts, "appkit_text": text, "board": bs,
                    "result": res(r)}
    finally:
        h.close()


@case("LF-M08-F09-C05")
def f09_c05():
    h = Helper(f1="field ")
    try:
        host = ClipboardSurface(h.identity)
        real = private_board()
        seed_board(real)
        board = AckBoard(real, fail_write_objects=True)
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        r = env.run("dictated", job(snapshot(host, h, el, sel=(6, 6))))
        text = h.view("F1")["text"]
        bs = board_state(board)
        env.close()
        ok = (text == "field dictated" and r.state == "confirmed"
              and r.clipboard.get("restore_skipped_reason")
              == "restore_failed" and r.clipboard.get("restored_types")
              == [] and bs["string"] != OLD)
        return ok, {"appkit_text": text, "board_after": bs,
                    "result": res(r)}
    finally:
        h.close()


@case("LF-M08-F10-C05")
def f10_c05():
    """Characterization, never a pass of atomicity: a copy landing
    between the ownership check and the restore write is overwritten."""
    h = Helper(f1="field ")
    try:
        host = ClipboardSurface(h.identity)
        real = private_board()
        seed_board(real)

        def user_copy(b):
            b.clearContents()
            b.setString_forType_("CANARY_USER_COPY", NSPasteboardTypeString)
        # clearContents #1 = publication, #2 = the restore write (after
        # the generation check passed).
        board = AckBoard(real, before_clear={2: user_copy})
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        r = env.run("dictated", job(snapshot(host, h, el, sel=(6, 6))))
        bs = board_state(board)
        env.close()
        lost = bs["string"] != "CANARY_USER_COPY"
        return "residual", {"user_copy_overwritten": lost, "board_after": bs,
                            "result": res(r),
                            "note": "generation check then native write is "
                                    "not atomic; documented residual"}
    finally:
        h.close()


@case("LF-M08-F11-C02")
def f11_c02():
    h = Helper(f1="field ")
    try:
        host = Unreadable(h.identity)
        real = private_board()
        seed_board(real)
        env = Env(h, host, real, settle=0.3, delay=0.8)
        el = host.focused_element_for(h.pid)
        r = env.run("dictated", job(snapshot(host, h, el, sel=(6, 6))))
        time.sleep(1.2)
        text = h.view("F1")["text"]
        env.close()
        ok = r.state == "posted_unverified" and r.state != "confirmed"
        return ok, {"result": res(r), "appkit_text_after_late_consumer": text,
                    "residual_old_clipboard_pasted": OLD in text}
    finally:
        h.close()


# ---- binding: owner, window, secure field, observer ---------------------

class after_validation:
    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        self._real = service_mod.validate_target
        real, fn = self._real, self.fn

        def wrapped(host, snapshot, job, **kw):
            out = real(host, snapshot, job, **kw)
            fn(job)
            return out
        service_mod.validate_target = wrapped

    def __exit__(self, *exc):
        service_mod.validate_target = self._real


@case("binding-two-processes")
def binding_two_processes():
    a = Helper(f1="alpha ")
    b = Helper(f1="bravo ")
    try:
        ident = {"cur": a.identity()}
        host = HelperHost(lambda: dict(ident["cur"]))
        board = private_board()
        seed_board(board)
        env = Env(a, host, board)
        el = host.focused_element_for(a.pid)
        s = snapshot(host, a, el, sel=(6, 6))
        with after_validation(lambda j: ident.__setitem__(
                "cur", b.identity())):
            r = env.run("dictated", job(s))
        ta, tb = a.view("F1")["text"], b.view("F1")["text"]
        posts = env.kb.posts
        env.close()
        ok = (r.state == "target_changed" and ta == "alpha "
              and tb == "bravo " and posts == 0)
        return ok, {"a": ta, "b": tb, "posts": posts, "result": res(r)}
    finally:
        a.close()
        b.close()


@case("binding-equal-title-windows")
def binding_equal_title_windows():
    h = Helper(f1="one ", f2="two ")
    try:
        host = HelperHost(h.identity)
        board = private_board()
        seed_board(board)
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        s = snapshot(host, h, el, sel=(4, 4))
        h.cmd(cmd="focus", view="F2")
        el2 = host.focused_element_for(h.pid)
        w1 = host.attribute(el, "AXWindow")
        w2 = host.attribute(el2, "AXWindow")
        t1 = host.attribute(w1, "AXTitle")
        t2 = host.attribute(w2, "AXTitle")
        r = env.run("dictated", job(s))
        f1, f2 = h.view("F1")["text"], h.view("F2")["text"]
        env.close()
        ok = (str(t1) == str(t2) and w1 != w2
              and r.state == "target_changed" and f1 == "one "
              and f2 == "two ")
        return ok, {"titles_equal": str(t1) == str(t2),
                    "window_elements_differ": w1 != w2,
                    "verification": r.verification, "f1": f1, "f2": f2,
                    "result": res(r)}
    finally:
        h.close()


@case("binding-secure-field")
def binding_secure_field():
    h = Helper(f1="plain ")
    try:
        log = []
        host = HelperHost(h.identity, log=log)
        board = private_board()
        seed_board(board)
        env = Env(h, host, board)
        el = host.focused_element_for(h.pid)
        s = snapshot(host, h, el, sel=(6, 6))
        h.cmd(cmd="focus", view="SF")
        sf = host.focused_element_for(h.pid)
        del log[:]
        r = env.run("dictated", job(s))
        on_sf = [name for (e, name) in log if e == sf]
        content = [n for n in on_sf if n in CONTENT_ATTRS
                   or n.startswith("set:")]
        v = h.view("SF")
        env.close()
        ok = content == [] and r.state != "confirmed" \
            and v["length"] == len("CANARY_SECURE_NATIVE")
        return ok, {"calls_on_secure_element": on_sf, "result": res(r),
                    "secure_length": v["length"]}
    finally:
        h.close()


@case("binding-observer-field-change")
def binding_observer():
    h = Helper(f1="obs ", f2="CANARY_FOREIGN ")
    try:
        log = []
        host = HelperHost(h.identity, log=log)
        board = private_board()
        seed_board(board)
        env = Env(h, host, board, window=3.0)
        el = host.focused_element_for(h.pid)
        s = snapshot(host, h, el, sel=(4, 4))
        box = {}
        r = env.run("watched", job(s, observation_consent=True),
                    on_observation=lambda info: box.__setitem__(
                        "obs", info["observer"]))
        obs = box.get("obs")
        h.cmd(cmd="focus", view="F2")
        f2 = host.focused_element_for(h.pid)
        mark = len(log)
        if obs is not None:
            obs.join(5)
        f2_reads = [n for (e, n) in log[mark:]
                    if e == f2 and n in CONTENT_ATTRS]
        env.close()
        ok = (r.state == "confirmed" and obs is not None
              and obs.stop_reason in ("field_changed", "focus_lost")
              and f2_reads == [] and not obs.edited)
        return ok, {"result": res(r),
                    "stop_reason": obs.stop_reason if obs else None,
                    "f2_content_reads": f2_reads,
                    "ticks": obs.ticks if obs else None}
    finally:
        h.close()


def stamp():
    def git(*a):
        try:
            return subprocess.run(["git", "-C", str(ROOT), *a],
                                  capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:
            return None
    from importlib.metadata import version
    dirty = git("status", "--porcelain", "--untracked-files=no")
    prod = git("status", "--porcelain", "--untracked-files=no",
               "--", "localflow")
    return {"code_root_sha": git("rev-parse", "HEAD"),
            "production_tree_modified": bool(prod) if prod is not None
            else None,
            "tracked_files_modified": bool(dirty) if dirty is not None
            else None,
            "python": sys.version.split()[0],
            "pyobjc": version("pyobjc-core"),
            "accessibility_trusted": bool(AS.AXIsProcessTrusted())}


def main(argv):
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    results = []
    for cid, fn, diag in CASES:
        if only and cid not in only:
            continue
        t0 = time.monotonic()
        try:
            ok, witness = fn()
            status = ("residual" if ok == "residual"
                      else ("pass" if ok else "fail"))
        except Exception as e:
            status, witness = "error", {
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc()[-1500:]}
        label = f"{cid}{' [diagnostic]' if diag else ''}"
        results.append({"case": cid, "diagnostic": diag, "status": status,
                        "witness": witness,
                        "seconds": round(time.monotonic() - t0, 3)})
        print(f"{'ok ' if status == 'pass' else status.upper()} {label}: "
              f"{json.dumps(witness, ensure_ascii=False, default=str)[:300]}")
    counted = [r for r in results if not r["diagnostic"]
               and r["status"] != "residual"]
    passed = sum(r["status"] == "pass" for r in counted)
    print(f"{passed}/{len(counted)} native M08 cases passed "
          f"({sum(r['status'] == 'residual' for r in results)} residual "
          f"characterized, {sum(r['diagnostic'] for r in results)} "
          f"diagnostic)")
    if out:
        pathlib.Path(out).write_text(json.dumps(
            {"suite": "tests/v2/insertion/test_native_insertion.py",
             **stamp(), "passed": passed, "counted": len(counted),
             "results": results}, indent=2, ensure_ascii=False,
            default=str) + "\n")
    return 0 if passed == len(counted) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
