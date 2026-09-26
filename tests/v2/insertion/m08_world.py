"""An independent multi-app insertion world for the M08 remediation.

The historical fixture (``fixture_target.py``) is one field in Python
code points with favourable acknowledgments: production code and oracle
can agree on a world no Mac produces (M08-AUDIT-21). This world keeps
its OWN state and answers every host protocol the insertion service,
validation, selection capture and observer use — the historical global
calls (``focused_element``) and the owner-bound M06 calls
(``focused_element_for``/``element_pid``/``window_of``) — so the same
scenario can run against the audited base and the repaired code.

What it models, independently of the code under test:

- applications with a pid and bundle; windows owned by an application,
  titles possibly equal; fields owned by a window, each with its own
  owner pid (which may disagree with its window's application — the
  foreign-owner case), role, subrole and text;
- a per-application focused field and a frontmost application; the
  SYSTEM focus is the frontmost application's focused field unless a
  test pins it elsewhere (``system_focus``);
- ranges in UTF-16 code units (the native Accessibility convention);
- a clipboard with change-count generations, multi-flavour items and
  optional failed acknowledgments;
- a paste consumer that reads the clipboard when IT runs and inserts
  into whatever field holds the system focus at that moment;
- a log of every content-bearing read (``reads``) and every physical
  effect (``effects``), kept by the world — never inferred from a
  result object;
- hooks run BEFORE a host method executes (barriers, focus switches,
  injected failures), keyed by method name and call number.

Every string in it is synthetic.
"""

from __future__ import annotations

import threading
import time

# Content-bearing attributes (the M06 privacy oracle's set, plus the
# parameterized string read): a read of any of these is destination
# content, whether or not the caller keeps it.
CONTENT_ATTRS = frozenset({
    "AXValue", "AXSelectedText", "AXSelectedTextRange",
    "AXNumberOfCharacters", "AXStringForRange", "AXPlaceholderValue",
    "AXDocument", "AXURL",
})
PLAIN = "public.utf8-plain-text"


def u16(s: str) -> int:
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def u16_slice(s: str, start: int, length: int):
    """``s[start:start+length]`` in UTF-16 units, or None when the range
    falls outside the text or cuts a surrogate pair."""
    b = s.encode("utf-16-le", "surrogatepass")
    if start < 0 or length < 0 or (start + length) * 2 > len(b):
        return None
    try:
        return b[start * 2:(start + length) * 2].decode("utf-16-le")
    except UnicodeDecodeError:
        return None


def u16_splice(s: str, start: int, end: int, new: str) -> str:
    b = s.encode("utf-16-le", "surrogatepass")
    return (b[:start * 2] + new.encode("utf-16-le", "surrogatepass")
            + b[end * 2:]).decode("utf-16-le", "surrogatepass")


class Range:
    """A decoded CFRange-shaped value (location/length, UTF-16 units)."""

    def __init__(self, location, length):
        self.location = location
        self.length = length

    def __repr__(self):
        return f"Range({self.location}, {self.length})"


class El:
    """A field element handle. Equality is identity of the field (the
    CFEqual behaviour of a real AXUIElementRef): a later fetch of the
    same field compares equal."""

    __slots__ = ("fid",)

    def __init__(self, fid):
        self.fid = fid

    def __eq__(self, other):
        return isinstance(other, El) and other.fid == self.fid

    def __hash__(self):
        return hash(("el", self.fid))

    def __repr__(self):
        return f"El({self.fid})"


class Win:
    __slots__ = ("wid",)

    def __init__(self, wid):
        self.wid = wid

    def __eq__(self, other):
        return isinstance(other, Win) and other.wid == self.wid

    def __hash__(self):
        return hash(("win", self.wid))

    def __repr__(self):
        return f"Win({self.wid})"


class Field:
    def __init__(self, fid, window, owner_pid, *, role="AXTextArea",
                 subrole=None, text="", sel=None, settable=True,
                 readable=True):
        self.fid = fid
        self.window = window
        self.owner_pid = owner_pid
        self.role = role
        self.subrole = subrole
        self.text = text
        n = u16(text)
        self.sel = tuple(sel) if sel is not None else (n, n)
        self.settable = settable
        self.range_settable = settable
        self.readable = readable
        # AXSelectedText setter behaviour: "normal", "noop" (acknowledges
        # without changing anything), "fail" (refuses, no effect),
        # ("partial", n) (writes the first n UTF-16 units, then refuses)
        self.set_behavior = "normal"


class World:
    def __init__(self):
        self.apps = {}          # name -> {"pid", "bundle", "name"}
        self.windows = {}       # wid -> {"owner": app name, "title"}
        self.fields = {}        # fid -> Field
        self.front_app = None   # app name, or None
        self.app_focus = {}     # app name -> fid (or None)
        self.system_focus = None  # fid pinned by a test, else derived
        self.trusted = True
        self.lock = threading.RLock()
        self.seq = 0
        self.reads = []         # (seq, method, fid, owner_pid, attr)
        self.meta_reads = []    # (seq, method, fid-or-wid, attr)
        self.effects = []       # (seq, kind, fid, detail)
        self.calls = {}         # method -> count
        self._hooks = {}        # method -> [(nth or None, fn)]
        self.raise_on = {}      # method -> exception (one shot)

    # ---- construction -------------------------------------------------

    def add_app(self, name, pid, bundle):
        self.apps[name] = {"pid": pid, "bundle": bundle, "name": name}
        self.app_focus.setdefault(name, None)
        return self

    def add_window(self, wid, owner, title):
        self.windows[wid] = {"owner": owner, "title": title}
        return self

    def add_field(self, fid, window, *, owner_pid=None, **kw):
        if owner_pid is None:
            owner_pid = self.apps[self.windows[window]["owner"]]["pid"]
        self.fields[fid] = Field(fid, window, owner_pid, **kw)
        return self.fields[fid]

    def focus(self, app, fid=None, *, frontmost=True):
        """Give ``app`` keyboard focus (and make it frontmost)."""
        with self.lock:
            if fid is not None:
                self.app_focus[app] = fid
            if frontmost:
                self.front_app = app
        return self

    # ---- scripting ------------------------------------------------------

    def on(self, method, fn, nth=None):
        """Run ``fn(world, *args)`` before call number ``nth`` (1-based;
        every call when None) of host method ``method``."""
        self._hooks.setdefault(method, []).append((nth, fn))

    def _enter(self, method, *args):
        with self.lock:
            self.calls[method] = n = self.calls.get(method, 0) + 1
            hooks = list(self._hooks.get(method, ()))
            exc = self.raise_on.pop(method, None)
        for nth, fn in hooks:
            if nth is None or nth == n:
                fn(self, *args)
        if exc is not None:
            raise exc

    def _stamp(self):
        with self.lock:
            self.seq += 1
            return self.seq

    def _read(self, method, fid, attr):
        f = self.fields.get(fid)
        self.reads.append((self._stamp(), method, fid,
                           f.owner_pid if f else None, attr))

    def _effect(self, kind, fid, detail=None):
        self.effects.append((self._stamp(), kind, fid, detail))

    # ---- oracle helpers ---------------------------------------------------

    def text(self, fid):
        return self.fields[fid].text

    def content_reads(self, fids=None):
        return [r for r in self.reads if fids is None or r[2] in fids]

    def writes(self, fids=None):
        return [e for e in self.effects
                if e[1] in ("ax_set_text", "ax_set_range",
                            "paste_consumed")
                and (fids is None or e[2] in fids)]

    def pid_of(self, app):
        return self.apps[app]["pid"]

    def _system_fid(self):
        if self.system_focus is not None:
            return self.system_focus
        if self.front_app is None:
            return None
        return self.app_focus.get(self.front_app)

    def _app_by_pid(self, pid):
        for name, a in self.apps.items():
            if a["pid"] == pid:
                return name
        return None

    # ---- InsertionHost (historical global calls + M06 owner-bound) -------

    def is_trusted(self):
        self._enter("is_trusted")
        return self.trusted

    def frontmost(self):
        self._enter("frontmost")
        with self.lock:
            if self.front_app is None:
                return None
            return dict(self.apps[self.front_app])

    def focused_element(self):
        self._enter("focused_element")
        with self.lock:
            fid = self._system_fid()
        return El(fid) if fid is not None else None

    def focused_element_for(self, pid):
        self._enter("focused_element_for", pid)
        with self.lock:
            app = self._app_by_pid(pid)
            fid = self.app_focus.get(app) if app is not None else None
        return El(fid) if fid is not None else None

    def element_pid(self, el):
        self._enter("element_pid", el)
        f = self.fields.get(getattr(el, "fid", None))
        return f.owner_pid if f is not None else None

    def window_of(self, el):
        self._enter("window_of", el)
        f = self.fields.get(getattr(el, "fid", None))
        return Win(f.window) if f is not None else None

    def attribute(self, el, name):
        self._enter("attribute", el, name)
        with self.lock:
            if isinstance(el, Win):
                w = self.windows.get(el.wid)
                self.meta_reads.append((self._stamp(), "attribute",
                                        el.wid, name))
                if w is None:
                    return None
                return w["title"] if name == "AXTitle" else None
            f = self.fields.get(getattr(el, "fid", None))
            if f is None:
                return None
            if name in ("AXRole", "AXSubrole", "AXWindow"):
                self.meta_reads.append((self._stamp(), "attribute",
                                        f.fid, name))
                if name == "AXRole":
                    return f.role
                if name == "AXSubrole":
                    return f.subrole
                return Win(f.window)
            if name in CONTENT_ATTRS:
                self._read("attribute", f.fid, name)
                if not f.readable:
                    return None
                if name == "AXSelectedTextRange":
                    return Range(f.sel[0], f.sel[1] - f.sel[0])
                if name == "AXNumberOfCharacters":
                    return u16(f.text)
                if name == "AXSelectedText":
                    return u16_slice(f.text, f.sel[0], f.sel[1] - f.sel[0])
                if name == "AXValue":
                    return f.text
            return None

    def focused_window_title(self, el):
        """The SystemInsertionHost semantics: a field has no
        AXFocusedWindow of its own, so the system host resolves the
        FRONTMOST application's focused window — not the field's."""
        self._enter("focused_window_title", el)
        with self.lock:
            if self.front_app is None:
                return None
            fid = self.app_focus.get(self.front_app)
            f = self.fields.get(fid)
            if f is None:
                return None
            self.meta_reads.append((self._stamp(), "focused_window_title",
                                    f.window, "AXTitle"))
            return self.windows[f.window]["title"]

    def is_settable(self, el, name):
        self._enter("is_settable", el, name)
        f = self.fields.get(getattr(el, "fid", None))
        if f is None:
            return False
        if name == "AXSelectedText":
            return f.settable
        if name == "AXSelectedTextRange":
            return f.range_settable
        return False

    @staticmethod
    def _decode_range(value):
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return int(value[0]), int(value[1])
        if hasattr(value, "location") and hasattr(value, "length"):
            return int(value.location), int(value.length)
        if isinstance(value, dict):
            return int(value["location"]), int(value.get("length", 0))
        return None

    def set_attribute(self, el, name, value):
        self._enter("set_attribute", el, name)
        with self.lock:
            f = self.fields.get(getattr(el, "fid", None))
            if f is None:
                return False
            if name == "AXSelectedTextRange":
                if not f.range_settable:
                    return False
                r = self._decode_range(value)
                if r is None:
                    return False
                loc, ln = r
                if loc < 0 or loc + ln > u16(f.text):
                    return False
                f.sel = (loc, loc + ln)
                self._effect("ax_set_range", f.fid, (loc, ln))
                return True
            if name == "AXSelectedText":
                if not f.settable:
                    return False
                text = str(value)
                beh = f.set_behavior
                if beh == "noop":
                    self._effect("ax_set_noop", f.fid, text)
                    return True
                if beh == "fail":
                    return False
                if isinstance(beh, tuple) and beh[0] == "partial":
                    b = text.encode("utf-16-le", "surrogatepass")
                    text = b[:beh[1] * 2].decode("utf-16-le",
                                                 "surrogatepass")
                s, e = f.sel
                f.text = u16_splice(f.text, s, e, text)
                caret = s + u16(text)
                f.sel = (caret, caret)
                self._effect("ax_set_text", f.fid, text)
                return not isinstance(beh, tuple)
            return False

    def string_for_range(self, el, start, length):
        self._enter("string_for_range", el, start, length)
        with self.lock:
            f = self.fields.get(getattr(el, "fid", None))
            if f is None:
                return None
            self._read("string_for_range", f.fid, "AXStringForRange")
            if not f.readable:
                return None
            return u16_slice(f.text, int(start), int(length))

    def number_of_characters(self, el):
        self._enter("number_of_characters", el)
        with self.lock:
            f = self.fields.get(getattr(el, "fid", None))
            if f is None:
                return None
            self._read("number_of_characters", f.fid,
                       "AXNumberOfCharacters")
            if not f.readable:
                return None
            return u16(f.text)

    # ---- physical user actions (the oracle's own edits) -----------------

    def user_type(self, fid, at, s):
        with self.lock:
            f = self.fields[fid]
            f.text = u16_splice(f.text, at, at, s)
            n = u16(s)
            a, b = f.sel
            f.sel = (a + n if a >= at else a, b + n if b >= at else b)
            self._effect("user_edit", fid, ("insert", at, s))

    def user_replace(self, fid, start, end, s):
        with self.lock:
            f = self.fields[fid]
            f.text = u16_splice(f.text, start, end, s)
            caret = start + u16(s)
            f.sel = (caret, caret)
            self._effect("user_edit", fid, ("replace", start, end, s))

    def user_select(self, fid, start, end):
        with self.lock:
            self.fields[fid].sel = (start, end)


class Pasteboard:
    """PasteboardHost over a change-count generation and multi-flavour
    items. ``ops`` is the ordered write log; ``write_ack`` False makes the
    next write clear the board but not store the data and report failure
    with None (a refused native write)."""

    def __init__(self, world=None):
        self.world = world
        self.lock = threading.RLock()
        self.count = 0
        self.items = []          # list of {type: bytes}
        self.ops = []            # (seq, op, detail)
        self.write_ack = True
        self._hooks = {}
        self.calls = {}

    def on(self, method, fn, nth=None):
        self._hooks.setdefault(method, []).append((nth, fn))

    def _enter(self, method):
        with self.lock:
            self.calls[method] = n = self.calls.get(method, 0) + 1
            hooks = list(self._hooks.get(method, ()))
        for nth, fn in hooks:
            if nth is None or nth == n:
                fn(self)

    def _op(self, op, detail):
        seq = self.world._stamp() if self.world is not None else None
        self.ops.append((seq, op, detail))

    def change_count(self):
        self._enter("change_count")
        with self.lock:
            return self.count

    def types(self):
        self._enter("types")
        with self.lock:
            out = []
            for it in self.items:
                for t in it:
                    if t not in out:
                        out.append(t)
            return out

    def data_for_type(self, ptype):
        self._enter("data_for_type")
        with self.lock:
            for it in self.items:
                if ptype in it:
                    return it[ptype]
            return None

    def string_for_type(self, ptype):
        v = self.data_for_type(ptype)
        return v.decode("utf-8") if isinstance(v, bytes) else v

    def plain(self):
        with self.lock:
            for it in self.items:
                if PLAIN in it:
                    v = it[PLAIN]
                    return v.decode("utf-8") if isinstance(v, bytes) else v
            return None

    def clear_and_write_text(self, text):
        self._enter("clear_and_write_text")
        with self.lock:
            self.count += 1
            if not self.write_ack:
                self.write_ack = True
                self.items = []
                self._op("write_text_refused", len(text))
                return None
            self.items = [{PLAIN: text.encode("utf-8")}]
            self._op("write_text", text)
            return self.count

    def clear_and_write_items(self, items):
        self._enter("clear_and_write_items")
        with self.lock:
            self.count += 1
            if not self.write_ack:
                self.write_ack = True
                self.items = []
                self._op("write_items_refused", len(items))
                return None
            self.items = [dict(pairs) for pairs in items]
            self._op("write_items", [sorted(d) for d in self.items])
            return self.count

    def user_copy(self, text=None, items=None):
        """A user (or another app) takes the clipboard."""
        with self.lock:
            self.count += 1
            self.items = ([dict(p) for p in items] if items is not None
                          else [{PLAIN: text.encode("utf-8")}])
            self._op("user_copy", text if items is None else "items")
            return self.count


class Keyboard:
    """KeyboardHost: a posted ⌘V is consumed by whatever field holds the
    SYSTEM focus when the consumer runs, reading the clipboard at THAT
    moment. ``mode``: "sync" (consumed before post returns), "gate"
    (consumed when ``release()`` is called, on a thread), "drop" (never).
    ``truncate`` keeps only that many UTF-16 units of the paste."""

    def __init__(self, world, pasteboard):
        self.world = world
        self.pb = pasteboard
        self.mode = "sync"
        self.truncate = 0
        self.posts = 0
        self.post_ok = True
        self._gate = threading.Event()
        self._consumed = threading.Event()
        self._pending = 0

    def post_paste(self):
        self.world._enter("post_paste")
        if not self.post_ok:
            return False
        self.posts += 1
        self.world._effect("post", self.world._system_fid(), None)
        if self.mode == "sync":
            self._consume()
        elif self.mode == "gate":
            self._pending += 1
            threading.Thread(target=self._gated, daemon=True).start()
        return True

    def _gated(self):
        self._gate.wait(30)
        self._consume()

    def release(self, wait=True):
        self._gate.set()
        if wait:
            self._consumed.wait(5)

    def _consume(self):
        w = self.world
        with w.lock:
            fid = w._system_fid()
            text = self.pb.plain() or ""
            f = w.fields.get(fid)
            if f is not None and text:
                if self.truncate:
                    b = text.encode("utf-16-le", "surrogatepass")
                    text = b[:self.truncate * 2].decode(
                        "utf-16-le", "surrogatepass")
                s, e = f.sel
                f.text = u16_splice(f.text, s, e, text)
                caret = s + u16(text)
                f.sel = (caret, caret)
            w._effect("paste_consumed", fid, text)
        self._consumed.set()


def standard_world(*, text_f1="", sel_f1=None, role="AXTextArea"):
    """App A (pid 101) with two equal-title windows W1/W2 holding F1/F2,
    and app B (pid 202) with window WB holding FB — the corpus base
    world. F1 is focused in A; A is frontmost."""
    w = World()
    w.add_app("A", 101, "com.example.a").add_app("B", 202, "com.example.b")
    w.add_window("W1", "A", "Draft").add_window("W2", "A", "Draft")
    w.add_window("WB", "B", "Other")
    w.add_field("F1", "W1", role=role, text=text_f1, sel=sel_f1)
    w.add_field("F2", "W2", role=role, text="CANARY_FOREIGN_FIELD",
                sel=(0, 0))
    w.add_field("FB", "WB", role=role, text="CANARY_B_SELECTION",
                sel=(0, 0))
    w.app_focus["A"] = "F1"
    w.app_focus["B"] = "FB"
    w.front_app = "A"
    pb = Pasteboard(w)
    kb = Keyboard(w, pb)
    return w, pb, kb


def wait_for(pred, timeout=5.0, step=0.01):
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() >= deadline:
            return False
        time.sleep(step)
    return True
