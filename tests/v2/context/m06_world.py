"""A scripted multi-app Accessibility world for M06 remediation probes.

``WorldHost`` models several synthetic applications, each with its own
focused field and window, plus a movable SYSTEM focus. It answers both
host protocols the collector has used: the original global-focus calls
(``focused_element``/``attribute``/``focused_window``/``window_title``/
``string_for_range``/``number_of_characters``) and the job-owned typed
calls (``focused_element_for``/``element_pid``/``element_token``/
``window_of``/``window_token``/``read``/``read_range``). Every call is
logged with the owning pid and attribute, so a probe can assert WHICH
destination was read — not only what the finished snapshot contains.

Units: ranges and ``AXNumberOfCharacters`` are served in UTF-16 code
units when ``native_units=True`` (the real AX convention, measured on
the reference Mac), else in Python code points (the historical fixture
convention). All content is synthetic.
"""

from __future__ import annotations

import threading

AX_OK = 0
AX_UNSUPPORTED = -25205          # kAXErrorAttributeUnsupported
AX_NO_VALUE = -25212             # kAXErrorNoValue
AX_CANNOT_COMPLETE = -25204      # kAXErrorCannotComplete
AX_INVALID_ELEMENT = -25202      # kAXErrorInvalidUIElement

CONTENT_ATTRS = frozenset({
    "AXValue", "AXSelectedText", "AXSelectedTextRange", "AXPlaceholderValue",
    "AXDocument", "AXURL", "AXStringForRange", "AXNumberOfCharacters",
    "AXTitle",
})


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def utf16_slice(s: str, start: int, length: int) -> str:
    b = s.encode("utf-16-le")[start * 2:(start + length) * 2]
    return b.decode("utf-16-le", errors="surrogatepass")


class App:
    def __init__(self, pid, bundle, name, *, field=None, window_title=None,
                 window_token=None):
        self.pid = pid
        self.bundle = bundle
        self.name = name
        self.field = field               # dict or None
        self.window_title = window_title
        self.window_token = window_token or f"win-{pid}"


class WorldHost:
    def __init__(self, apps, *, focus_pid, frontmost_pid=None,
                 trusted=True, native_units=False):
        self.apps = {a.pid: a for a in apps}
        self.focus_pid = focus_pid
        self.frontmost_pid = focus_pid if frontmost_pid is None \
            else frontmost_pid
        self.trusted = trusted
        self.native_units = native_units
        self.calls: list[tuple] = []     # (method, owner_pid, attr)
        self.hooks: dict = {}            # method -> callable(n) run BEFORE
        self.counts: dict = {}
        self.raise_on: dict = {}         # method -> exception instance
        self.oversize: dict = {}         # attr -> replacement text
        self.lock = threading.Lock()

    # ---- scripting ----------------------------------------------------

    def switch(self, pid, *, frontmost=True):
        self.focus_pid = pid
        if frontmost:
            self.frontmost_pid = pid

    def _enter(self, method, owner=None, attr=None):
        with self.lock:
            n = self.counts.get(method, 0) + 1
            self.counts[method] = n
            self.calls.append((method, owner, attr))
        hook = self.hooks.get(method)
        if hook is not None:
            hook(n)
        exc = self.raise_on.get(method)
        if exc is not None:
            raise exc

    def frontmost(self):
        self._enter("frontmost")
        a = self.apps.get(self.frontmost_pid)
        if a is None:
            return None
        return {"bundle": a.bundle, "name": a.name, "pid": a.pid}

    def reads_of(self, pid, attrs=CONTENT_ATTRS):
        return [c for c in self.calls if c[1] == pid and c[2] in attrs]

    # ---- shared ---------------------------------------------------------

    def is_trusted(self):
        self._enter("is_trusted")
        return self.trusted

    def _field_el(self, app):
        if app is None or app.field is None:
            return None
        return ("field", app.pid, app.field.get("field_token",
                                                f"field-{app.pid}"))

    def _app_of(self, el):
        return self.apps.get(el[1]) if el is not None else None

    # ---- original global-focus protocol ---------------------------------

    def focused_element(self):
        self._enter("focused_element", self.focus_pid)
        return self._field_el(self.apps.get(self.focus_pid))

    def attribute(self, el, name):
        v, err = self.read(el, name)
        return v if err == AX_OK else None

    def focused_window(self, el):
        self._enter("focused_window", el[1] if el else None)
        a = self._app_of(el)
        return None if a is None else ("window", a.pid, a.window_token)

    def window_title(self, win):
        self._enter("window_title", win[1] if win else None, "AXTitle")
        a = self.apps.get(win[1]) if win else None
        return a.window_title if a is not None else None

    def string_for_range(self, el, start, length):
        self._enter("string_for_range", el[1] if el else None,
                    "AXStringForRange")
        a = self._app_of(el)
        if a is None or a.field is None:
            return None
        if "AXStringForRange" in self.oversize:
            return self.oversize["AXStringForRange"]
        v = a.field.get("value") or ""
        if self.native_units:
            return utf16_slice(v, start, length)
        return v[start:start + length]

    def number_of_characters(self, el):
        v, err = self.read(el, "AXNumberOfCharacters")
        return v if err == AX_OK else None

    # ---- job-owned typed protocol ----------------------------------------

    def focused_element_for(self, pid):
        self._enter("focused_element_for", pid)
        return self._field_el(self.apps.get(pid))

    def element_pid(self, el):
        self._enter("element_pid", el[1] if el else None)
        return el[1] if el is not None else None

    def element_token(self, el):
        return el[2] if el is not None else None

    def window_of(self, el):
        self._enter("window_of", el[1] if el else None)
        a = self._app_of(el)
        return None if a is None else ("window", a.pid, a.window_token)

    def window_token(self, win):
        return win[2] if win is not None else None

    def focused_window_title(self, el):
        """The insertion host's live title lookup (the system host reads
        the application's focused window): the owning app's title."""
        self._enter("focused_window_title", el[1] if el else None, "AXTitle")
        a = self._app_of(el)
        return a.window_title if a is not None else None

    def read(self, el, name):
        owner = el[1] if el is not None else None
        self._enter("read", owner, name)
        if el is None:
            return None, AX_INVALID_ELEMENT
        if el[0] == "window":
            a = self.apps.get(el[1])
            if name == "AXTitle":
                t = a.window_title if a else None
                return (t, AX_OK) if t is not None else (None, AX_NO_VALUE)
            return None, AX_UNSUPPORTED
        a = self._app_of(el)
        f = (a.field if a else None) or {}
        if name in self.oversize:
            return self.oversize[name], AX_OK
        if name == "AXRole":
            return (f.get("role"), AX_OK) if f.get("role") is not None \
                else (None, AX_NO_VALUE)
        if name == "AXSubrole":
            if f.get("subrole_error") is not None:
                return None, f["subrole_error"]
            return (f.get("subrole"), AX_OK) if f.get("subrole") \
                else (None, AX_UNSUPPORTED)
        if name == "AXSelectedText":
            loc, ln = self._rng(f)
            if loc is None or not ln:
                return None, AX_NO_VALUE
            v = f.get("value") or ""
            if "selected_text" in f and f["selected_text"] is not None:
                return f["selected_text"], AX_OK
            s = utf16_slice(v, loc, ln) if self.native_units \
                else v[loc:loc + ln]
            return s, AX_OK
        if name == "AXSelectedTextRange":
            loc, ln = self._rng(f)
            return ((loc, ln), AX_OK) if loc is not None \
                else (None, AX_NO_VALUE)
        if name == "AXNumberOfCharacters":
            v = f.get("value") or ""
            return (utf16_len(v) if self.native_units else len(v)), AX_OK
        if name == "AXWindow":
            return ("window", a.pid, a.window_token), AX_OK
        key = {"AXURL": "url", "AXDocument": "document",
               "AXPlaceholderValue": "placeholder",
               "AXValue": "value"}.get(name)
        if key is None:
            return None, AX_UNSUPPORTED
        val = f.get(key)
        return (val, AX_OK) if val is not None else (None, AX_UNSUPPORTED)

    def read_range(self, el, name="AXSelectedTextRange"):
        v, err = self.read(el, name)
        return (tuple(v) if v is not None else None), err

    @staticmethod
    def _rng(f):
        r = f.get("selected_text_range")
        if not r:
            return None, None
        return int(r[0]), int(r[1])
