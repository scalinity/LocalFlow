"""Shared fixtures for the M03 remediation regression suites.

Everything here drives PRODUCTION code: the real ``AppDelegate`` methods
(under the declared non-native shims of ``native_shims.py``), the real
``WorkerSupervisor`` against the protocol fake or the production worker
entry (``prod_worker_harness.py``), the real ``Store``/collector. Journal
bytes are built independently with ``struct`` — never with the writer.
"""

import json
import os
import pathlib
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import native_shims  # noqa: E402

native_shims.install()

import numpy as np  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow.hotkey import HotkeyListener  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.supervisor import WorkerSupervisor  # noqa: E402

FAKE = HERE / "fake_worker.py"
PROD = HERE / "prod_worker_harness.py"
AppHelper = app_mod.AppHelper
T0 = "2026-01-02T03:04:05.000Z"

CFG = {
    "model": "test-asr", "hotkey": "fn", "sample_rate": 16000,
    "min_duration_sec": 0.3, "max_duration_sec": 0, "append_space": True,
    "restore_clipboard": False, "input_device": None, "cleanup": "llm",
    "cleanup_model": "test-llm", "log_transcripts": False,
    "capture_journal": True, "hands_free": "off", "mouse_trigger": None,
    "cleanup_not_ready_policy": "basic",
}


def shim_banner():
    return ("[portable orchestration under declared non-native shims: "
            + ", ".join(native_shims.SHIMMED) + "]") \
        if native_shims.SHIMMED else "[native modules present]"


class Rec:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def __call__(self, event, level="INFO", **kw):
        with self.lock:
            self.events.append((event, kw))

    def count(self, name):
        with self.lock:
            return sum(1 for e, _ in self.events if e == name)

    def named(self, name):
        with self.lock:
            return [kw for e, kw in self.events if e == name]

    def blob(self):
        with self.lock:
            return json.dumps(self.events, default=str)


def make_sup(td, plan, *, prod=False, worker_cmd=None, **kw):
    td = pathlib.Path(td)
    plan_path = td / f"plan-{time.monotonic_ns()}.json"
    plan_path.write_text(json.dumps(plan))
    rec = Rec()
    args = dict(hello_timeout=15.0, ready_timeout=15.0, request_timeout=15.0)
    args.update(kw)
    s = WorkerSupervisor(
        audio_root=td / "audio", asr_model="fake-asr", cleanup_mode="llm",
        cleanup_model="fake-llm", emit=rec,
        worker_cmd=worker_cmd or [sys.executable,
                                  str(PROD if prod else FAKE)],
        spawn_env={"LOCALFLOW_FAKE_WORKER_PLAN": str(plan_path),
                   "LOCALFLOW_PROD_WORKER_PLAN": str(plan_path),
                   "PYTHONPATH": str(ROOT)}, **args)
    return s, rec


def wav(root, name, n=1600, rate=16000, values=None):
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    p = root / name
    data = values if values is not None else np.linspace(
        -0.1, 0.1, n, dtype=np.float32)
    store_mod.write_wav_f32(p, data, rate)
    return p


def v1_journal(path, job_id, blocks, *, rate=16000, meta=None,
               finalize=None, seqs=None, tail=b""):
    """Journal v1 bytes built with struct (the audited format)."""
    header = {"journal_version": 1, "job_id": job_id, "family_id": None,
              "sample_rate": rate, "channels": 1, "dtype": "float32",
              "meta": meta or {}}
    out = json.dumps(header).encode() + b"\n"
    for i, b in enumerate(blocks):
        data = np.asarray(b, dtype="<f4").tobytes()
        seq = seqs[i] if seqs else i + 1
        out += struct.pack("<3sIII", b"BLK", seq, len(data) // 4,
                           len(data)) + data
    if finalize is not None:
        out += finalize
    out += tail
    pathlib.Path(path).write_bytes(out)


def v2_journal(path, job_id, blocks, *, rate=16000, meta=None, footer=None,
               seqs=None, starts=None, crcs=None, tail=b"", boot_id=None):
    """Journal v2 bytes built with struct, independently of the writer:
    BLK + seq, frames, record_bytes(=12+4*frames) + u64 start + u32 crc."""
    header = {"journal_version": 2, "job_id": job_id, "family_id": None,
              "sample_rate": rate, "channels": 1, "dtype": "float32",
              "boot_id": boot_id, "meta": meta or {}}
    out = json.dumps(header).encode() + b"\n"
    pos = 0
    for i, b in enumerate(blocks):
        data = np.asarray(b, dtype="<f4").tobytes()
        frames = len(data) // 4
        seq = seqs[i] if seqs else i + 1
        start = starts[i] if starts else pos
        crc = crcs[i] if crcs else zlib.crc32(data)
        out += struct.pack("<3sIII", b"BLK", seq, frames, 12 + len(data))
        out += struct.pack("<QI", start, crc) + data
        pos = start + frames
    if footer is not None:
        out += json.dumps(footer).encode() + b"\n"
    out += tail
    pathlib.Path(path).write_bytes(out)


def blocks_of(n, size=800, start=0):
    return [np.arange(start + i * size, start + (i + 1) * size,
                      dtype=np.float32) / 1e6 for i in range(n)]


class FakeOverlay:
    def __init__(self):
        self.visible = False
        self.mode = None

    def showWithMode_(self, mode):
        self.visible, self.mode = True, mode

    def setMode_(self, mode):
        self.mode = mode

    def hide(self):
        self.visible = False


class RecordingInsertion:
    """Admission rule of the real InsertionService (a cancelled job is
    refused before any clipboard/host touch); records every accepted
    submission as a host write."""

    busy = False

    def __init__(self):
        self.submits = []
        self.refused = 0

    def note_new_dictation(self):
        pass

    def note_session_locked(self):
        pass

    def note_session_unlocked(self):
        pass

    def submit(self, text, job, on_done, on_observation=None):
        from localflow.v2.insertion import InsertionResult
        if job.get("cancelled"):
            self.refused += 1
            res = InsertionResult(state="saved_not_inserted",
                                  reason_code="user_cancelled")
        else:
            self.submits.append(len(text))
            res = InsertionResult.legacy_posted(len(text))
        on_done(res)


class GateSup:
    """Scripted supervisor stand-in (protocol-free), optional gate."""

    def __init__(self, text="hello there", gate=None):
        self.text = text
        self.gate = gate
        self.entered = threading.Event()
        self.calls = []
        self.generation = 1
        self.engine_state = {"asr": "ready", "cleanup": "ready"}
        self.supervisor_state = "running"

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None,
                   **kw):
        self.calls.append(("transcribe", attempt, sample_rate, audio_name))
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(10)
        return {"attempt": attempt, "generation": 1, "duration_ms": 1.0,
                "decode_ranges": [[0, 1]], "text": self.text}

    def clean(self, *, job_id, attempt, raw_text, **kw):
        self.calls.append(("clean", attempt, None, None))
        return {"attempt": attempt, "generation": 1, "duration_ms": 1.0,
                "path": "llm", "fallback_reason": None, "text": raw_text,
                "observations": []}

    def wait_engine(self, engine, timeout):
        return "ready"

    def shutdown(self, timeout=5.0):
        pass

    def restart(self):
        pass


class App:
    """The real AppDelegate, configured on temp roots, with native seams
    (overlay, key state, insertion host, clipboard) recorded."""

    def __init__(self, td, cfg=None, start_coordinator=True):
        td = pathlib.Path(td)
        self.td = td
        for k, v in dict(V2_DB=td / "v2.db", V2_ARTIFACTS=td / "art",
                         V2_BACKUPS=td / "bk", V2_EVENTS_DIR=td / "ev",
                         V2_JOURNAL=td / "journal").items():
            setattr(app_mod, k, v)
        app_mod.AUDIO_DEBUG_DIR = td / "dbg"
        self.journal = td / "journal"
        merged = dict(CFG)
        merged.update(cfg or {})
        AppHelper.calls.clear()
        d = app_mod.AppDelegate.alloc().init()
        d.configure(merged)
        d.overlay = FakeOverlay()
        d._context = None
        d._hub = None
        self.phys = False
        hk = HotkeyListener("fn", d.startDictation, d.finishDictation,
                            d.cancelDictation)
        hk.physically_down = lambda: self.phys
        d.hotkey = hk
        self.ins = RecordingInsertion()
        d._insertion = self.ins
        self.copies = []
        app_mod.copy_text = lambda t: self.copies.append(len(t))
        self.d = d
        self._coord = None
        if start_coordinator:
            self.start_coordinator()

    def start_coordinator(self):
        self._coord = threading.Thread(target=self.d._worker, daemon=True)
        self.d._coordinator_thread = self._coord
        self._coord.start()

    def set_sup(self, sup):
        self.d.supervisor = sup

    def sd(self):
        return native_shims.sounddevice()

    def dictate(self, blocks=20, value=0.05, release=True):
        """PTT down → callback blocks through the real Recorder → release.
        Returns (job_id, the exact samples delivered)."""
        self.phys = True
        self.d.startDictation()
        job = self.d._job
        stream = self.sd().streams[-1]
        delivered = []
        for i in range(blocks):
            blk = np.full((800, 1), value + i * 1e-4, dtype=np.float32)
            delivered.append(blk[:, 0].copy())
            stream.callback(blk, 800, None, None)
        if release:
            self.phys = False
            self.d.finishDictation()
        return (job or {}).get("job_id"), np.concatenate(delivered)

    def wait_call(self, name, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for fn, _a in list(AppHelper.calls):
                if getattr(fn, "__name__", "") == name:
                    return True
            time.sleep(0.01)
        return False

    def drain(self):
        return AppHelper.drain()

    def db(self, sql, args=()):
        con = sqlite3.connect(app_mod.V2_DB)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def state(self, job_id):
        rows = self.db("SELECT state FROM jobs WHERE job_id=?", (job_id,))
        return rows[0][0] if rows else None

    def envelope(self, job_id):
        rows = self.db(
            "SELECT r.envelope_json FROM training_revisions r JOIN"
            " training_examples e ON e.example_id=r.example_id WHERE"
            " e.job_id=? ORDER BY r.rowid DESC LIMIT 1", (job_id,))
        return json.loads(rows[0][0]) if rows else None

    def close(self):
        try:
            if getattr(self.d.store, "lifecycle", "open") == "open":
                self.d.store.close(timeout=3)
        except Exception:
            pass
        try:
            self.d.v2log.close(timeout=3)
        except Exception:
            pass
        fd = getattr(self.d, "_journal_root_lock", None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            self.d._journal_root_lock = None


def tmpdir():
    return tempfile.TemporaryDirectory()


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    stat = pathlib.Path(f"/proc/{pid}/stat")
    if stat.exists():
        return stat.read_text().split()[2] != "Z"
    return True


def run(tests, label):
    print(shim_banner())
    for t in tests:
        t()
    print(f"all {label} passed ({len(tests)})")
