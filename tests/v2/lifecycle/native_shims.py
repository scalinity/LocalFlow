"""Declared NON-NATIVE interface shims for portable orchestration tests.

``localflow.app`` (and the modules it imports) bind AppKit / Foundation /
Quartz / ApplicationServices / PyObjC / sounddevice at import time. The
cloud container has none of them, so the production ``AppDelegate``
methods cannot even be imported there. ``install()`` registers inert
stand-ins for exactly those native modules — only when the real module
is missing — so the REAL app code (coordinator, recovery scan, retry,
shutdown, trigger state machine, Recorder) runs against declared fakes at
the native seams:

* every attribute of a shimmed framework is an inert class (callable,
  subclassable, attribute-chainable, bit-or-able) — nothing it returns
  models macOS behaviour;
* ``objc.python_method`` is the identity decorator; ``NSObject`` supports
  ``alloc().init()``;
* ``PyObjCTools.AppHelper.callAfter`` records calls instead of posting to a
  run loop (tests drain them explicitly);
* ``sounddevice`` is a scriptable fake (``FakeSoundDevice``) so the real
  ``localflow.audio.Recorder`` can be driven through its stream seam.

``patch_seams(app_mod)`` additionally replaces two SEAMS on every
platform — ``localflow.audio.sd`` (the microphone) and the app's
``AppHelper`` (main-thread hops) — so the same suites run
deterministically on the reference Mac without opening a microphone or
needing a run loop, while real AppKit/PyObjC is used when present.

A pass under these shims is a portable orchestration result. It is NOT
native verification of AppKit, PyObjC, TCC, event taps, microphones or
sleep/wake — those stay PENDING_LOCAL_VERIFICATION (VERIFICATION.html).
``SHIMMED`` lists what was replaced so every suite can print it.
"""

import importlib
import sys
import types

SHIMMED = []


class _StubMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _stub_class(name)

    def __or__(cls, other):
        return cls

    __ror__ = __or__
    __and__ = __or__
    __rand__ = __or__

    def __call__(cls, *a, **kw):
        return super().__call__()


class _Stub(metaclass=_StubMeta):
    def __init__(self, *a, **kw):
        pass

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _stub_class(name)()

    def __call__(self, *a, **kw):
        return _Stub()

    def __bool__(self):
        return False

    # Inert values: empty when iterated, zero when measured, never equal
    # to anything but themselves — a stub never invents data.
    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __contains__(self, item):
        return False

    def __float__(self):
        return 0.0

    def __int__(self):
        return 0

    def __index__(self):
        return 0

    def __lt__(self, other):
        return False

    __le__ = __gt__ = __ge__ = __lt__

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)

    def __str__(self):
        return ""

    @classmethod
    def alloc(cls):
        return cls.__new__(cls)

    def init(self):
        return self


def _stub_class(name):
    return _StubMeta(str(name), (_Stub,), {})


class _Framework(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        cls = _stub_class(name)
        setattr(self, name, cls)
        return cls


class NSObject:
    """Minimal stand-in: PyObjC's two-phase construction only."""

    @classmethod
    def alloc(cls):
        return cls.__new__(cls)

    def init(self):
        return self


class _Timer:
    def __init__(self, *a):
        self.args = a
        self.valid = True

    def invalidate(self):
        self.valid = False


class NSTimer:
    created = []

    @classmethod
    def scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            cls, interval, target, selector, info, repeats):
        t = _Timer(interval, target, selector, info, repeats)
        cls.created.append(t)
        return t


class AppHelper:
    """Records main-thread hops; tests drain them explicitly."""

    calls = []

    @classmethod
    def callAfter(cls, fn, *args):
        cls.calls.append((fn, args))

    @classmethod
    def drain(cls, limit=1000):
        n = 0
        while cls.calls and n < limit:
            fn, args = cls.calls.pop(0)
            fn(*args)
            n += 1
        return n

    @classmethod
    def runEventLoop(cls, *a, **kw):
        raise RuntimeError("no native event loop under the shim")


class FakeStream:
    """A sounddevice.InputStream stand-in with injectable failures."""

    def __init__(self, sd, kwargs):
        self._sd = sd
        self.kwargs = kwargs
        self.callback = kwargs.get("callback")
        self.started = False
        self.closed = False
        self.stop_calls = 0
        self.close_calls = 0
        self.device = kwargs.get("device")
        self.active = False

    def start(self):
        if self._sd.fail_start:
            raise self._sd.fail_start
        self.started = True
        self.active = True

    def stop(self):
        self.stop_calls += 1
        self.active = False
        if self._sd.fail_stop:
            raise self._sd.fail_stop

    def close(self):
        self.close_calls += 1
        self.closed = True
        if self._sd.fail_close:
            raise self._sd.fail_close


class FakeSoundDevice(types.ModuleType):
    def __init__(self):
        super().__init__("sounddevice")
        self.streams = []
        self.fail_start = None
        self.fail_stop = None
        self.fail_close = None

    def InputStream(self, **kwargs):  # noqa: N802 — mirrors the real API
        s = FakeStream(self, kwargs)
        self.streams.append(s)
        return s

    def query_devices(self, index=None):
        dev = {"name": "shim-mic", "max_input_channels": 1}
        return dev if index is not None else [dev]


FAKE_SD = FakeSoundDevice()


def _real(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def install():
    """Install shims for the missing native modules; idempotent."""
    if SHIMMED:
        return SHIMMED
    frameworks = ("AppKit", "Foundation", "Quartz", "ApplicationServices",
                  "CoreFoundation", "WebKit", "Cocoa")
    for name in frameworks:
        if name in sys.modules or _real(name):
            continue
        mod = _Framework(name)
        if name == "Foundation":
            mod.NSObject = NSObject
            mod.NSTimer = NSTimer
        if name == "AppKit":
            mod.NSObject = NSObject
            mod.NSTimer = NSTimer
        sys.modules[name] = mod
        SHIMMED.append(name)
    if not _real("objc"):
        objc = types.ModuleType("objc")
        objc.python_method = lambda f: f
        objc.super = super
        objc.selector = lambda f, **kw: f
        sys.modules["objc"] = objc
        SHIMMED.append("objc")
    if not _real("PyObjCTools"):
        pkg = types.ModuleType("PyObjCTools")
        pkg.AppHelper = AppHelper
        sys.modules["PyObjCTools"] = pkg
        sys.modules["PyObjCTools.AppHelper"] = AppHelper
        SHIMMED.append("PyObjCTools")
    if not _real("sounddevice"):
        sys.modules["sounddevice"] = FAKE_SD
        SHIMMED.append("sounddevice")
    return SHIMMED


def patch_seams(app_mod=None):
    """Declared seam fakes applied on EVERY platform (see module doc)."""
    import localflow.audio as audio_mod
    audio_mod.sd = FAKE_SD
    if app_mod is not None:
        app_mod.AppHelper = AppHelper
    return FAKE_SD


def sounddevice():
    return FAKE_SD
