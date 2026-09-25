"""M03 remediation: content-free reproductions of M03-AUDIT-01..17 (+27).

Each probe drives the REAL production code (supervisor, worker, capture
journal, store, Recorder, AppDelegate methods) with synthetic audio/text
in temporary directories and reports what it OBSERVED as booleans and
counts — never ids, paths or text. The same script runs against the
audited base and the repaired tree (``--code-root``): probes use seams
that exist in both (the app's own methods, module attributes, the worker
entry point); where a repair renamed an internal the probe follows the
new name when it exists and says so (``wiring``).

AppKit / PyObjC / sounddevice are replaced by the DECLARED non-native
shims in tests/v2/lifecycle/native_shims.py; model loaders by
tests/v2/lifecycle/prod_worker_harness.py. A probe result is therefore a
portable orchestration observation — never native or model-backed
evidence.

``reproduced: true`` means the defect's failure mechanism was observed.

Usage:
    .venv/bin/python scripts/v2/m03_remediation_repro.py \
        [--code-root DIR] [--output PATH] [--only p01,p02]
Exit code is always 0 (a reproduction is an observation, not a failure).
"""

import argparse
import json
import os
import pathlib
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent.parent.parent
LIFECYCLE = HERE / "tests" / "v2" / "lifecycle"

ap = argparse.ArgumentParser()
ap.add_argument("--code-root", default=str(HERE))
ap.add_argument("--output")
ap.add_argument("--only")
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(LIFECYCLE))

import native_shims  # noqa: E402

native_shims.install()

import numpy as np  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow import audio as audio_mod  # noqa: E402
from localflow.hotkey import HotkeyListener, MouseTriggerListener  # noqa: E402
from localflow.v2 import capture_journal as cj  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import supervisor as sup_mod  # noqa: E402
from localflow.v2 import worker as worker_mod  # noqa: E402
from localflow.v2.supervisor import WorkerFailure, WorkerSupervisor  # noqa: E402

FAKE = LIFECYCLE / "fake_worker.py"
PROD = LIFECYCLE / "prod_worker_harness.py"
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


# ---- helpers ----------------------------------------------------------------

class Rec:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def __call__(self, event, level="INFO", **kw):
        with self.lock:
            self.events.append((event, kw))

    def count(self, name):
        return sum(1 for e, _ in self.events if e == name)

    def blob(self):
        return json.dumps(self.events, default=str)


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
    """Same admission rule as the real InsertionService (a cancelled job
    is refused before any clipboard/host touch); records submissions."""

    busy = False

    def __init__(self, d):
        self.d = d
        self.submits = []

    def note_new_dictation(self):
        pass

    def note_session_locked(self):
        pass

    def note_session_unlocked(self):
        pass

    def submit(self, text, job, on_done, on_observation=None):
        from localflow.v2.insertion import InsertionResult
        if job.get("cancelled"):
            res = InsertionResult(state="saved_not_inserted",
                                  reason_code="user_cancelled")
        else:
            self.submits.append(len(text))
            res = InsertionResult.legacy_posted(len(text))
        on_done(res)


class GateSup:
    """Scripted supervisor stand-in; optional gate inside transcribe."""

    def __init__(self, text="hello there", gate=None):
        self.text = text
        self.gate = gate
        self.entered = threading.Event()
        self.calls = []
        self.wav_root = None
        self.wav_seen = []
        self.generation = 1
        self.engine_state = {"asr": "ready", "cleanup": "ready"}
        self.supervisor_state = "running"

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None,
                   **kw):
        self.calls.append(("transcribe", attempt, sample_rate))
        if self.wav_root is not None:
            self.wav_seen.append((pathlib.Path(self.wav_root)
                                  / audio_name).exists())
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(10)
        return {"attempt": attempt, "generation": 1, "duration_ms": 1.0,
                "decode_ranges": [[0, 1]], "text": self.text}

    def clean(self, *, job_id, attempt, raw_text, **kw):
        self.calls.append(("clean", attempt, None))
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
        self.ins = RecordingInsertion(d)
        d._insertion = self.ins
        self.copies = []
        app_mod.copy_text = lambda t: self.copies.append(len(t))
        self.d = d
        self.sup = None
        self._coord = None
        if start_coordinator:
            self.start_coordinator()

    def start_coordinator(self):
        self._coord = threading.Thread(target=self.d._worker, daemon=True)
        # as applicationDidFinishLaunching_ does (read by quit, if at all)
        self.d._coordinator_thread = self._coord
        self._coord.start()

    def set_sup(self, sup):
        self.sup = sup
        self.d.supervisor = sup

    def drain(self):
        return AppHelper.drain()

    def wait_call(self, name, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for fn, _a in list(AppHelper.calls):
                if getattr(fn, "__name__", "") == name:
                    return True
            time.sleep(0.01)
        return False

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


def q(db, sql, args=()):
    import sqlite3
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def write_v1_journal(path, job_id, blocks, *, rate=16000, meta=None,
                     finalize=None, seqs=None, tail=b""):
    """Independent v1 journal bytes (the audited format), built with
    struct — never with the production writer."""
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
    path.write_bytes(out)


def blocks_of(n_blocks, size=800, start=0):
    return [np.arange(start + i * size, start + (i + 1) * size,
                      dtype=np.float32) / 1e6 for i in range(n_blocks)]


def make_sup(td, plan, *, prod=False, gen_env=None, **kw):
    td = pathlib.Path(td)
    plan_path = td / "plan.json"
    plan_path.write_text(json.dumps(plan))
    rec = Rec()
    env = {"LOCALFLOW_FAKE_WORKER_PLAN": str(plan_path),
           "LOCALFLOW_PROD_WORKER_PLAN": str(plan_path),
           "LOCALFLOW_CODE_ROOT": str(CODE), "PYTHONPATH": str(CODE)}
    env.update(gen_env or {})
    args = dict(hello_timeout=15.0, ready_timeout=15.0, request_timeout=15.0)
    args.update(kw)
    s = WorkerSupervisor(
        audio_root=td / "audio", asr_model="fake-asr", cleanup_mode="llm",
        cleanup_model="fake-llm", emit=rec,
        worker_cmd=[sys.executable, str(PROD if prod else FAKE)],
        spawn_env=env, **args)
    return s, rec


def wav(root, name, n=1600, rate=16000):
    root.mkdir(parents=True, exist_ok=True)
    p = root / name
    store_mod.write_wav_f32(p, np.linspace(-0.1, 0.1, n, dtype=np.float32),
                            rate)
    return p


def pids_alive(pids):
    alive = 0
    for pid in pids:
        try:
            os.kill(pid, 0)
            # a zombie still answers kill(0); check /proc state
            st = pathlib.Path(f"/proc/{pid}/stat")
            if st.exists() and st.read_text().split()[2] == "Z":
                continue
            alive += 1
        except OSError:
            pass
    return alive


PROBES = {}


def probe(name):
    def deco(fn):
        PROBES[name] = fn
        return fn
    return deco


# ---- M03-AUDIT-01 ----------------------------------------------------------

@probe("p01")
def p01():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            sd = native_shims.sounddevice()
            # (a) a LIVE current-session capture through the real
            # startDictation + Recorder (shimmed stream).
            a.phys = True
            d.startDictation()
            live_job = d._job["job_id"] if d._job else None
            stream = sd.streams[-1]
            for i in range(6):
                stream.callback(np.full((800, 1), 0.01 * (i + 1),
                                        dtype=np.float32), 800, None, None)
            blk = a.journal / f"job-{live_job}.blk"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not (
                    blk.exists() and blk.stat().st_size > 800 * 4 * 6):
                time.sleep(0.01)
            obs["live_blk_present_before_scan"] = blk.exists()
            d._recover_journals()
            obs["live_blk_unlinked_by_scan"] = not blk.exists()
            obs["live_wav_created_by_scan"] = (
                a.journal / f"job-{live_job}.wav").exists()
            obs["live_offered_as_recovery"] = any(
                i.get("job_id") == live_job for i in d._recoverable)
            row = d.store.job(live_job) or {}
            obs["live_row_state_after_scan"] = row.get("state")
            # finish the capture normally afterwards
            d.cancelDictation()

            # (c) a completed job from a previous boot with leftover .blk
            done = "job-done-" + "0" * 8
            d.store.create_job(job_id=done, boot_id="boot-previous",
                               state="capturing", captured_at_utc=T0)
            for st in ("queued", "transcribing", "ready_to_insert",
                       "insertion_posted", "insertion_confirmed"):
                d.store.update_job_state(done, st)
            write_v1_journal(a.journal / f"job-{done}.blk", done,
                             blocks_of(8))
            # (d) a fuller WAV beside a half-length journal (unresolved,
            # previous boot)
            fuller = "job-full-" + "0" * 8
            d.store.create_job(job_id=fuller, boot_id="boot-previous",
                               state="transcribing", captured_at_utc=T0)
            full = np.arange(16000, dtype=np.float32) / 1e5
            store_mod.write_wav_f32(a.journal / f"job-{fuller}.wav", full,
                                    16000)
            write_v1_journal(a.journal / f"job-{fuller}.blk", fuller,
                             [full[:8000]])
            d._recoverable.clear()
            d._recover_journals()
            obs["completed_job_offered"] = any(
                i.get("job_id") == done for i in d._recoverable)
            obs["completed_row_state"] = (d.store.job(done) or {}).get(
                "state")
            got, _r = store_mod.read_wav_f32(a.journal / f"job-{fuller}.wav")
            obs["fuller_wav_samples_before"] = int(full.size)
            obs["fuller_wav_samples_after"] = int(got.size)
            obs["fuller_wav_replaced_by_shorter"] = got.size < full.size
        finally:
            a.close()
    # (b) a second process owning a live journal (different boot)
    with tempfile.TemporaryDirectory() as td:
        jroot = pathlib.Path(td) / "journal"
        jroot.mkdir()
        child = subprocess.Popen(
            [sys.executable, "-c", CHILD_JOURNAL, str(CODE), str(jroot)],
            stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True)
        try:
            ready = child.stdout.readline().strip()
            a = App(td, start_coordinator=False)
            try:
                blk = jroot / f"job-{ready}.blk"
                obs["other_process_blk_present"] = blk.exists()
                a.d._recover_journals()
                obs["other_process_live_blk_claimed"] = not blk.exists() \
                    or any(i.get("job_id") == ready
                           for i in a.d._recoverable)
            finally:
                a.close()
        finally:
            try:
                child.stdin.write("stop\n")
                child.stdin.flush()
            except OSError:
                pass
            child.wait(10)
    obs["reproduced"] = bool(
        obs["live_blk_unlinked_by_scan"] or obs["live_offered_as_recovery"]
        or obs["completed_job_offered"]
        or obs["fuller_wav_replaced_by_shorter"]
        or obs["other_process_live_blk_claimed"])
    return obs


CHILD_JOURNAL = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import numpy as np
from localflow.v2 import capture_journal as cj
j = cj.CaptureJournal(sys.argv[2], job_id="other0000live", sample_rate=16000,
                      meta={"captured_at_utc": "2026-01-01T00:00:00.000Z"})
for i in range(4):
    j.handoff_block(np.full(800, 0.02, dtype=np.float32))
p = j.blk_path
while not (p.exists() and p.stat().st_size > 800 * 4 * 4):
    time.sleep(0.01)
print("other0000live", flush=True)
sys.stdin.readline()
j.finalize()
"""


# ---- M03-AUDIT-02 ----------------------------------------------------------

@probe("p02")
def p02():
    obs = {}
    # (a) coordinator paused before worker-WAV creation; delete; release
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            gate, entered = threading.Event(), threading.Event()
            real_state = d._job_state

            def gated_state(job_id, state, reason=None, retry=False):
                if state == "transcribing":
                    entered.set()
                    gate.wait(10)
                return real_state(job_id, state, reason=reason, retry=retry)

            d._job_state = gated_state
            sup = GateSup()
            sup.wav_root = a.journal
            a.set_sup(sup)
            a.start_coordinator()
            a.phys = True
            d.startDictation()
            jid = d._job["job_id"]
            stream = native_shims.sounddevice().streams[-1]
            for _ in range(20):
                stream.callback(np.full((800, 1), 0.05, dtype=np.float32),
                                800, None, None)
            a.phys = False
            d.finishDictation()
            entered.wait(5)
            out = d.store.delete_everywhere("job", jid)
            obs["delete_reported_complete"] = bool(out.get("complete"))
            gate.set()
            a.wait_call("_finishWithText_", 10)
            a.drain()
            time.sleep(0.2)
            obs["worker_wav_after_delete"] = (
                a.journal / f"job-{jid}.wav").exists() or any(sup.wav_seen)
            obs["model_called_after_delete"] = any(
                c[0] == "transcribe" for c in sup.calls)
            obs["insert_after_delete"] = len(a.ins.submits)
        finally:
            a.close()
    # (b) delivery gated after output exists; delete; release delivery
    with tempfile.TemporaryDirectory() as td:
        a = App(td)
        try:
            d = a.d
            a.set_sup(GateSup(text="deliver me"))
            a.phys = True
            d.startDictation()
            jid = d._job["job_id"]
            stream = native_shims.sounddevice().streams[-1]
            for _ in range(20):
                stream.callback(np.full((800, 1), 0.05, dtype=np.float32),
                                800, None, None)
            a.phys = False
            d.finishDictation()
            assert a.wait_call("_finishWithText_", 10)
            d.store.delete_everywhere("job", jid)
            a.drain()
            obs["host_insert_after_delete"] = len(a.ins.submits)
            obs["clipboard_after_delete"] = len(a.copies)
        finally:
            a.close()
    # (c) journal writer paused before it opens its file; job deleted;
    # writer released → does the cancelled/deleted journal reappear?
    for variant in ("discard", "delete"):
        with tempfile.TemporaryDirectory() as td:
            a = App(td, start_coordinator=False)
            try:
                d = a.d
                jid, _fam = d.store.create_job(boot_id=d.v2log.boot_id)
                gate, entered = threading.Event(), threading.Event()
                real_open = cj.CaptureJournal._open_file

                def gated_open(self, *args, **kw):
                    entered.set()
                    gate.wait(10)
                    return real_open(self, *args, **kw)

                cj.CaptureJournal._open_file = gated_open
                try:
                    kwargs = {}
                    if "open_gate" in cj.CaptureJournal.__init__.__code__\
                            .co_varnames:
                        kwargs["open_gate"] = d._journal_open_gate(jid)
                    j = cj.CaptureJournal(a.journal, job_id=jid,
                                          sample_rate=16000, **kwargs)
                    j.handoff_block(np.full(800, 0.1, dtype=np.float32))
                    entered.wait(5)
                    t0 = time.monotonic()
                    if variant == "discard":
                        j.close_discard()
                    else:
                        d.store.delete_everywhere("job", jid)
                        j.finalize(timeout=0.2)
                    obs[f"{variant}_returned_s"] = round(
                        time.monotonic() - t0, 2)
                    gate.set()
                    j._thread.join(5)
                    obs[f"journal_reappeared_after_{variant}"] = \
                        j.blk_path.exists()
                finally:
                    cj.CaptureJournal._open_file = real_open
                    gate.set()
            finally:
                a.close()
    # (d) recovery retry, then deletion before the coordinator runs it
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            a.set_sup(GateSup(text="retried text"))
            jid, fam = d.store.create_job(boot_id="boot-previous",
                                          captured_at_utc=T0,
                                          state="transcribing")
            d.store.update_job_state(jid, "failed_recoverable")
            w = a.journal / f"job-{jid}.wav"
            a.journal.mkdir(parents=True, exist_ok=True)
            store_mod.write_wav_f32(w, np.full(16000, 0.02,
                                               dtype=np.float32), 16000)
            info = {"job_id": jid, "family_id": fam, "wav": str(w),
                    "raw": None, "attempt": 1}
            d._recoverable.append(info)
            d._retry_job(info)
            d.store.delete_everywhere("job", jid)
            a.start_coordinator()
            a.wait_call("_finishWithText_", 10)
            a.drain()
            obs["retry_insert_after_delete"] = len(a.ins.submits)
            obs["retry_wav_after_delete"] = w.exists()
        finally:
            a.close()
    # (e) residue of a deleted job at recovery time
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            jid, _ = d.store.create_job(boot_id="boot-previous",
                                        captured_at_utc=T0)
            d.store.delete_everywhere("job", jid)
            a.journal.mkdir(parents=True, exist_ok=True)
            write_v1_journal(a.journal / f"job-{jid}.blk", jid, blocks_of(12))
            d._recover_journals()
            obs["deleted_job_resurrected_by_recovery"] = any(
                i.get("job_id") == jid for i in d._recoverable) or (
                a.journal / f"job-{jid}.wav").exists()
        finally:
            a.close()
    obs["reproduced"] = bool(
        obs["worker_wav_after_delete"] or obs["model_called_after_delete"]
        or obs["insert_after_delete"] or obs["host_insert_after_delete"]
        or obs["clipboard_after_delete"]
        or obs["journal_reappeared_after_discard"]
        or obs["journal_reappeared_after_delete"]
        or obs["retry_insert_after_delete"]
        or obs["deleted_job_resurrected_by_recovery"])
    return obs


# ---- M03-AUDIT-03 ----------------------------------------------------------

@probe("p03")
def p03():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "audio"
        w = wav(root, "job-g2.wav")
        s, rec = make_sup(td, {"transcribe": ["ok:g1 answer",
                                              "delay:1500|ok:g2 answer",
                                              "ok:spurious retry"]})
        hold, held = threading.Event(), threading.Event()
        real_emit = s.emit

        def emit(event, level="INFO", **kw):
            if event == "worker.pipe_closed" and \
                    kw.get("worker_generation") == 1:
                held.set()
                hold.wait(10)
            real_emit(event, level=level, **kw)

        s.emit = emit
        try:
            s.transcribe(job_id="job-g1", attempt=1, audio_name=w.name)
            g1 = s._proc
            g1.kill()
            obs["g1_finalizer_held"] = held.wait(5)
            result = {}

            def run():
                try:
                    result["res"] = s.transcribe(job_id="job-g2", attempt=1,
                                                 audio_name=w.name)
                except WorkerFailure as e:
                    result["err"] = e.reason_code

            t = threading.Thread(target=run)
            t.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with s._state_lock:
                    if s._pending and s.generation == 2:
                        break
                time.sleep(0.01)
            obs["g2_request_pending_when_released"] = bool(s._pending)
            hold.set()
            t.join(20)
            res = result.get("res") or {}
            obs["g2_retried_spuriously"] = bool(res.get("retried"))
            obs["g2_request_failed"] = "err" in result
            obs["spawns"] = rec.count("worker.spawned")
            obs["deaths_recorded"] = rec.count("worker.died")
        finally:
            hold.set()
            s.shutdown()
    obs["reproduced"] = bool(obs["g2_retried_spuriously"]
                             or obs["g2_request_failed"])
    return obs


# ---- M03-AUDIT-04 ----------------------------------------------------------

@probe("p04")
def p04():
    obs = {}
    # (a) submit after shutdown
    with tempfile.TemporaryDirectory() as td:
        w = wav(pathlib.Path(td) / "audio", "job-x.wav")
        s, rec = make_sup(td, {"transcribe": ["ok:a", "ok:b"]})
        s.transcribe(job_id="job-x", attempt=1, audio_name=w.name)
        s.shutdown()
        before = rec.count("worker.spawned")
        try:
            s.transcribe(job_id="job-x", attempt=1, audio_name=w.name)
            obs["submit_after_shutdown_accepted"] = True
        except WorkerFailure as e:
            obs["submit_after_shutdown_accepted"] = False
            obs["refusal_code"] = e.reason_code
        obs["spawns_after_shutdown"] = rec.count("worker.spawned") - before
        leaked = s._proc
        if leaked is not None:
            leaked.kill()
            leaked.wait(5)
    # (b) shutdown during an in-flight request: does the fault respawn?
    with tempfile.TemporaryDirectory() as td:
        w = wav(pathlib.Path(td) / "audio", "job-y.wav")
        s, rec = make_sup(td, {"transcribe": ["delay:800|ok:a",
                                              "delay:3000|ok:b"]})
        pids = []
        real_popen = sup_mod.subprocess.Popen

        def popen(*a, **kw):
            p = real_popen(*a, **kw)
            pids.append(p.pid)
            return p

        sup_mod.subprocess.Popen = popen
        try:
            s.ensure_running()
            out = {}

            def run():
                try:
                    out["res"] = s.transcribe(job_id="job-y", attempt=1,
                                              audio_name=w.name)
                except WorkerFailure as e:
                    out["err"] = e.reason_code

            t = threading.Thread(target=run)
            t.start()
            time.sleep(0.3)
            s.shutdown(timeout=0.2)
            t.join(15)
            time.sleep(0.3)
            obs["spawned_after_shutdown_began"] = len(pids) > 1
            obs["children_alive_after_shutdown"] = pids_alive(pids)
        finally:
            sup_mod.subprocess.Popen = real_popen
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
    # (c) manual restart racing the automatic retry's spawn
    with tempfile.TemporaryDirectory() as td:
        w = wav(pathlib.Path(td) / "audio", "job-z.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:Injected", "ok:after"]})
        procs = []
        gate, entered = threading.Event(), threading.Event()
        real_popen = sup_mod.subprocess.Popen

        def popen(*a, **kw):
            n = len(procs)
            if n == 1:  # the automatic retry's spawn
                entered.set()
                gate.wait(10)
            p = real_popen(*a, **kw)
            procs.append(p)
            return p

        sup_mod.subprocess.Popen = popen
        try:
            s.ensure_running()
            out = {}

            def run():
                try:
                    out["res"] = s.transcribe(job_id="job-z", attempt=1,
                                              audio_name=w.name)
                except WorkerFailure as e:
                    out["err"] = e.reason_code

            t = threading.Thread(target=run)
            t.start()
            obs["retry_spawn_held"] = entered.wait(10)
            rt = threading.Thread(target=lambda: s.restart())
            rt.start()
            rt.join(1.5)
            obs["restart_completed_while_retry_spawning"] = \
                not rt.is_alive()
            gate.set()
            rt.join(15)
            t.join(15)
            s.shutdown()
            time.sleep(0.3)
            obs["processes_spawned"] = len(procs)
            obs["orphaned_children"] = sum(
                1 for p in procs if p.poll() is None)
        finally:
            gate.set()
            sup_mod.subprocess.Popen = real_popen
            for p in procs:
                if p.poll() is None:
                    p.kill()
                    p.wait(5)
    # (d) app termination while recording and while a job is in flight
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            gate = threading.Event()
            sup, srec = make_sup(td, {"transcribe": ["delay:3000|ok:late"]})
            sup.audio_root = str(a.journal)
            a.set_sup(sup)
            a.start_coordinator()
            a.phys = True
            d.startDictation()
            j1 = d._job["job_id"]
            stream = native_shims.sounddevice().streams[-1]
            for _ in range(20):
                stream.callback(np.full((800, 1), 0.05, dtype=np.float32),
                                800, None, None)
            a.phys = False
            d.finishDictation()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not sup._pending:
                time.sleep(0.01)
            a.phys = True
            d.startDictation()
            j2 = d._job["job_id"]
            stream2 = native_shims.sounddevice().streams[-1]
            for _ in range(20):
                stream2.callback(np.full((800, 1), 0.05, dtype=np.float32),
                                 800, None, None)
            refused = []
            real_submit = d.store._submit

            def counting_submit(fn, *args, **kw):
                try:
                    return real_submit(fn, *args, **kw)
                except RuntimeError as e:
                    if "store is" in str(e):
                        refused.append(1)
                    raise

            d.store._submit = counting_submit
            spawns_before_quit = srec.count("worker.spawned")
            d.applicationWillTerminate_(None)
            time.sleep(1.0)
            obs["worker_spawns_during_quit"] = \
                srec.count("worker.spawned") - spawns_before_quit
            obs["worker_alive_after_quit"] = bool(
                sup._proc is not None and sup._proc.poll() is None)
            obs["mic_stream_still_active_after_quit"] = bool(
                stream2.active and not stream2.closed)
            import sqlite3
            con = sqlite3.connect(app_mod.V2_DB)
            s1 = con.execute("SELECT state FROM jobs WHERE job_id=?",
                             (j1,)).fetchone()
            s2 = con.execute("SELECT state FROM jobs WHERE job_id=?",
                             (j2,)).fetchone()
            con.close()
            obs["inflight_job_state_after_quit"] = s1[0] if s1 else None
            obs["recording_job_state_after_quit"] = s2[0] if s2 else None
            obs["producer_writes_refused_after_close"] = len(refused)
        finally:
            gate.set()
            a.close()
    obs["reproduced"] = bool(
        obs["submit_after_shutdown_accepted"]
        or obs["spawned_after_shutdown_began"]
        or obs["children_alive_after_shutdown"]
        or obs["orphaned_children"]
        or obs["mic_stream_still_active_after_quit"]
        or obs["producer_writes_refused_after_close"]
        or obs["worker_spawns_during_quit"]
        or obs["worker_alive_after_quit"])
    return obs


# ---- M03-AUDIT-05 ----------------------------------------------------------

@probe("p05")
def p05():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.consent.set("enabled")
            s, rec = make_sup(td, {"transcribe": ["fault:Injected",
                                                  "fault:Injected"]})
            s.audio_root = str(a.journal)
            sent = []
            real_send = s._send

            def send(msg, **kw):
                if msg.get("op") == "transcribe":
                    sent.append(msg.get("attempt"))
                return real_send(msg, **kw)

            s._send = send
            a.set_sup(s)
            a.start_coordinator()
            a.phys = True
            d.startDictation()
            jid = d._job["job_id"]
            stream = native_shims.sounddevice().streams[-1]
            for _ in range(20):
                stream.callback(np.full((800, 1), 0.05, dtype=np.float32),
                                800, None, None)
            a.phys = False
            d.finishDictation()
            assert a.wait_call("_finishWithText_", 30)
            a.drain()
            d.store.sync()
            obs["executed_attempts"] = sent
            obs["store_attempt"] = (d.store.job(jid) or {}).get("attempt")
            lf = d._last_failed or {}
            obs["recovery_item_attempt"] = lf.get("attempt")
            env = q(app_mod.V2_DB,
                    "SELECT r.envelope_json FROM training_revisions r JOIN"
                    " training_examples e ON e.example_id=r.example_id"
                    " WHERE e.job_id=? ORDER BY r.rowid DESC LIMIT 1",
                    (jid,))
            obs["failure_envelope_attempt"] = (
                json.loads(env[0][0]).get("attempt") if env else None)
            try:
                u = q(app_mod.V2_DB,
                      "SELECT attempt FROM usage_facts WHERE job_id=?",
                      (jid,))
                obs["usage_fact_attempt"] = u[0][0] if u else None
            except Exception:
                obs["usage_fact_attempt"] = "unavailable"
            # explicit recovery retry numbering
            s._send = real_send
            if lf:
                d._retry_job(lf)
                d.store.sync()
                obs["recovery_retry_attempt"] = (
                    d.store.job(jid) or {}).get("attempt")
            s.shutdown()
        finally:
            a.close()
    executed = max(obs["executed_attempts"] or [1])
    obs["reproduced"] = bool(
        obs["store_attempt"] != executed
        or obs["recovery_item_attempt"] != executed
        or obs["failure_envelope_attempt"] != executed
        or obs.get("recovery_retry_attempt") is not None
        and obs["recovery_retry_attempt"] <= executed)
    return obs


# ---- M03-AUDIT-06 ----------------------------------------------------------

@probe("p06")
def p06():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        w = wav(pathlib.Path(td) / "audio", "job-f.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:FatalGpu",
                                              "fault:FatalGpu", "ok:next"]})
        try:
            try:
                s.transcribe(job_id="job-f", attempt=1, audio_name=w.name)
            except WorkerFailure:
                pass
            g2 = s._proc
            obs["second_failed_child_alive"] = bool(
                g2 is not None and g2.poll() is None)
            gen_before = s.generation
            s.transcribe(job_id="job-n", attempt=1, audio_name=w.name)
            obs["next_job_reused_failed_generation"] = \
                s.generation == gen_before
        finally:
            s.shutdown()
    # runtime cleanup exception in the PRODUCTION worker → success result?
    with tempfile.TemporaryDirectory() as td:
        s, rec = make_sup(td, {"clean": ["raise:boom in generation",
                                         "ok:fine"]}, prod=True)
        try:
            s.ensure_running()
            s.wait_engine("cleanup", 10)
            gen = s.generation
            out = s.clean(job_id="job-c", attempt=1, raw_text="keep me")
            obs["runtime_exception_returned_as_result"] = \
                out.get("op") == "result"
            obs["fallback_text_preserved"] = out.get("text") == "keep me"
            obs["death_streak_after"] = s._consecutive_deaths
            s.clean(job_id="job-c2", attempt=1, raw_text="next")
            obs["next_request_same_generation"] = s.generation == gen
        finally:
            s.shutdown()
    obs["reproduced"] = bool(obs["next_job_reused_failed_generation"]
                             or obs["next_request_same_generation"])
    return obs


# ---- M03-AUDIT-07 ----------------------------------------------------------

@probe("p07")
def p07():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        latch = pathlib.Path(td) / "release"
        w = wav(pathlib.Path(td) / "audio", "job-l.wav")
        s, rec = make_sup(td, {"cleanup_load_latch": str(latch),
                               "transcribe": ["ok:asr text"]},
                          prod=True, request_timeout=4.0)
        try:
            s.ensure_running()
            obs["asr_state"] = s.wait_engine("asr", 10)
            time.sleep(0.2)
            obs["cleanup_state_while_latched"] = s.engine_state.get(
                "cleanup")
            t0 = time.monotonic()
            try:
                out = s.clean(job_id="job-l", attempt=1, raw_text="um hi")
                obs["basic_now_answered"] = True
                obs["basic_now_path"] = out.get("path")
                obs["basic_now_reason"] = out.get("fallback_reason")
            except WorkerFailure as e:
                obs["basic_now_answered"] = False
                obs["basic_now_failure"] = e.reason_code
            obs["basic_now_latency_s"] = round(time.monotonic() - t0, 2)
            t0 = time.monotonic()
            try:
                s.transcribe(job_id="job-l", attempt=1, audio_name=w.name)
                obs["asr_answered_while_latched"] = True
            except WorkerFailure as e:
                obs["asr_answered_while_latched"] = False
                obs["asr_failure"] = e.reason_code
            obs["asr_latency_s"] = round(time.monotonic() - t0, 2)
            obs["spawns"] = rec.count("worker.spawned")
        finally:
            latch.write_text("go")
            s.shutdown()
    obs["reproduced"] = not obs.get("basic_now_answered") or \
        obs["basic_now_latency_s"] >= 3.5
    return obs


# ---- M03-AUDIT-08 ----------------------------------------------------------

def _classify(rec):
    """Version-neutral view of a JournalRecovery."""
    return {"samples": int(rec.samples.size),
            "status": getattr(rec, "status", None),
            "torn": bool(rec.torn),
            "finalized": getattr(rec, "finalized", None)}


@probe("p08")
def p08():
    obs = {}
    b = blocks_of(4)
    import hashlib
    good_sha = hashlib.sha256(b"".join(
        np.asarray(x, dtype="<f4").tobytes() for x in b)).hexdigest()
    fin = lambda blocks, samples, sha: (json.dumps(  # noqa: E731
        {"op": "finalize", "blocks": blocks, "samples": samples,
         "sha256": sha}).encode() + b"\n")
    cases = {}
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        def run(name, **kw):
            p = td / f"{name}.blk"
            write_v1_journal(p, "job-x", kw.pop("blocks", b), **kw)
            cases[name] = _classify(cj.reconstruct(p))

        run("control_finalized", finalize=fin(4, 3200, good_sha))
        run("reordered", seqs=[1, 3, 2, 4])
        run("duplicate", seqs=[1, 2, 2, 3])
        run("bad_footer_hash", finalize=fin(4, 3200, "0" * 64))
        run("bad_footer_count", finalize=fin(9, 3200, good_sha))
        run("lone_brace", tail=b"{")
        run("partial_footer", tail=b'{"op": "finali')
        # payload bit flip inside a finalized journal
        p = td / "bitflip.blk"
        write_v1_journal(p, "job-x", b, finalize=fin(4, 3200, good_sha))
        raw = bytearray(p.read_bytes())
        raw[raw.index(b"BLK") + 16 + 40] ^= 0x40
        p.write_bytes(bytes(raw))
        cases["bitflip_finalized"] = _classify(cj.reconstruct(p))
        # interior corruption followed by later valid blocks
        p = td / "interior.blk"
        write_v1_journal(p, "job-x", b)
        raw = bytearray(p.read_bytes())
        second = raw.index(b"BLK", raw.index(b"BLK") + 3)
        raw[second:second + 3] = b"XXX"
        p.write_bytes(bytes(raw))
        cases["interior_corruption"] = _classify(cj.reconstruct(p))
        # genuine torn tail (EOF mid-record)
        p = td / "torn.blk"
        write_v1_journal(p, "job-x", b)
        p.write_bytes(p.read_bytes()[:-100])
        cases["torn_tail"] = _classify(cj.reconstruct(p))
        # exact record-boundary EOF (no footer): finalization unknown
        run("boundary_eof")
        # production writer under queue overflow: are gap positions kept?
        j = cj.CaptureJournal(td / "flood", job_id="job-flood",
                              sample_rate=16000)
        gate = threading.Event()
        real_open = cj.CaptureJournal._open_file

        def slow_open(self, *a, **kw):
            gate.wait(10)
            return real_open(self, *a, **kw)

        cj.CaptureJournal._open_file = slow_open
        try:
            offered = 0
            for i in range(cj.QUEUE_BOUND + 40):
                j.handoff_block(np.full(160, float(i), dtype=np.float32))
                offered += 1
            gate.set()
            j.finalize(timeout=10)
        finally:
            cj.CaptureJournal._open_file = real_open
        rec = cj.reconstruct(j.blk_path)
        cases["overflow"] = _classify(rec)
        gaps = getattr(rec, "gaps", None)
        obs["overflow_dropped_in_memory"] = j.queue_dropped
        obs["overflow_gap_positions_persisted"] = bool(gaps)
    obs["cases"] = cases

    def accepted_as_clean(c):
        return (not c["torn"] and c["status"] in (None, "finalized",
                                                  "finalized_verified"))

    obs["reorder_accepted"] = accepted_as_clean(cases["reordered"]) \
        and cases["reordered"]["samples"] == 3200
    obs["duplicate_accepted"] = accepted_as_clean(cases["duplicate"]) \
        and cases["duplicate"]["samples"] == 3200
    obs["bad_hash_accepted_as_finalized"] = accepted_as_clean(
        cases["bad_footer_hash"])
    obs["bad_count_accepted_as_finalized"] = accepted_as_clean(
        cases["bad_footer_count"])
    obs["bitflip_accepted_as_finalized"] = accepted_as_clean(
        cases["bitflip_finalized"])
    obs["lone_brace_treated_as_clean_finalize"] = accepted_as_clean(
        cases["lone_brace"])
    obs["interior_same_class_as_torn_tail"] = (
        cases["interior_corruption"]["torn"] == cases["torn_tail"]["torn"]
        and cases["interior_corruption"]["status"]
        == cases["torn_tail"]["status"])
    obs["boundary_eof_claims_finalized_or_clean"] = (
        cases["boundary_eof"]["status"] in (None, "finalized",
                                            "finalized_verified")
        and not cases["boundary_eof"]["torn"])
    obs["reproduced"] = bool(
        obs["reorder_accepted"] or obs["duplicate_accepted"]
        or obs["bad_hash_accepted_as_finalized"]
        or obs["bad_count_accepted_as_finalized"]
        or obs["bitflip_accepted_as_finalized"]
        or obs["lone_brace_treated_as_clean_finalize"]
        or obs["interior_same_class_as_torn_tail"]
        or not obs["overflow_gap_positions_persisted"])
    return obs


# ---- M03-AUDIT-09 ----------------------------------------------------------

@probe("p09")
def p09():
    obs = {}
    for variant in ("known", "unknown"):
        with tempfile.TemporaryDirectory() as td:
            a = App(td, start_coordinator=False)
            try:
                d = a.d
                d.consent.set("enabled")
                rev = d.store.current_consent_id()
                cap = T0 if variant == "known" else None
                jid, fam = d.store.create_job(
                    boot_id="boot-previous", captured_at_utc=cap,
                    time_quality="known" if cap else "unknown",
                    state="capturing")
                d.store.upsert_example(job_id=jid, family_id=fam,
                                       consent_revision_id=rev)
                a.journal.mkdir(parents=True, exist_ok=True)
                meta = {"captured_at_utc": T0, "time_quality": "known"} \
                    if cap else {}
                write_v1_journal(a.journal / f"job-{jid}.blk", jid,
                                 blocks_of(20, size=800), rate=8000,
                                 meta=meta, tail=b"BLK\x01")
                d._recover_journals()
                info = next((i for i in d._recoverable
                             if i.get("job_id") == jid), None)
                obs[f"{variant}_recovered"] = info is not None
                if info is None:
                    continue
                sup = GateSup(text="recovered words")
                a.set_sup(sup)
                a.start_coordinator()
                d._retry_job(info)
                assert a.wait_call("_finishWithText_", 15)
                a.drain()
                d.store.sync()
                env = q(app_mod.V2_DB,
                        "SELECT r.envelope_json FROM training_revisions r"
                        " JOIN training_examples e ON"
                        " e.example_id=r.example_id WHERE e.job_id=?"
                        " ORDER BY r.rowid DESC LIMIT 1", (jid,))
                e = json.loads(env[0][0]) if env else {}
                obs[f"{variant}_envelope_captured_at"] = (
                    "T0" if e.get("captured_at_utc") == T0 else
                    ("null" if e.get("captured_at_utc") is None
                     else "other"))
                obs[f"{variant}_envelope_time_quality"] = e.get(
                    "time_quality")
                capm = e.get("capture") or {}
                obs[f"{variant}_envelope_sample_rate"] = capm.get(
                    "sample_rate")
                obs[f"{variant}_capture_incomplete_tail"] = capm.get(
                    "incomplete_tail")
                disc = (e.get("audio_preparation") or {}).get(
                    "discontinuities") or []
                obs[f"{variant}_discontinuity_kinds"] = sorted(
                    {x.get("kind") for x in disc})
                obs[f"{variant}_worker_rate_passed"] = [
                    c[2] for c in sup.calls if c[0] == "transcribe"]
                u = q(app_mod.V2_DB, "SELECT activity_at_utc FROM"
                      " usage_facts WHERE job_id=?", (jid,))
                obs[f"{variant}_usage_activity"] = (
                    "T0" if u and u[0][0] == T0 else
                    ("null" if not u or u[0][0] is None else "other"))
            finally:
                a.close()
    obs["reproduced"] = bool(
        obs.get("known_envelope_captured_at") != "T0"
        or obs.get("known_envelope_sample_rate") != 8000
        or "incomplete_tail" not in obs.get("known_discontinuity_kinds", [])
        or obs.get("unknown_envelope_time_quality") == "known"
        or 16000 in obs.get("known_worker_rate_passed", []))
    return obs


# ---- M03-AUDIT-10 ----------------------------------------------------------

@probe("p10")
def p10():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        full = td / "full.wav"
        n = 16000
        store_mod.write_wav_f32(full, np.linspace(-1, 1, n,
                                                  dtype=np.float32), 16000)
        raw = full.read_bytes()
        half = td / "half.wav"
        half.write_bytes(raw[:44 + (n // 2) * 4])
        try:
            got, _r = store_mod.read_wav_f32(half)
            obs["truncated_read_silently"] = True
            obs["declared"], obs["returned"] = n, int(got.size)
        except Exception as e:
            obs["truncated_read_silently"] = False
            obs["truncated_error"] = type(e).__name__
        odd = td / "odd.wav"
        odd.write_bytes(raw[:44 + 1000 * 4 + 3])
        try:
            store_mod.read_wav_f32(odd)
            obs["misaligned_accepted"] = True
        except Exception as e:
            obs["misaligned_accepted"] = False
            obs["misaligned_error"] = type(e).__name__
        got, _r = store_mod.read_wav_f32(full)
        obs["complete_control_samples"] = int(got.size)
        # interrupted write: the final path must not hold a prefix
        dst = td / "interrupted.wav"

        class Boom:
            def __buffer__(self, flags):
                raise OSError("disk vanished")

        header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + 400,
                             b"WAVE", b"fmt ", 16, 3, 1, 16000, 64000, 4,
                             32, b"data", 400)
        try:
            store_mod._write_wav(dst, header, Boom())
        except Exception:
            pass
        obs["interrupted_write_left_final_path"] = dst.exists()
    # the production worker's input path on the truncated file
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "audio"
        w = wav(root, "job-t.wav", n=16000)
        raw = w.read_bytes()
        w.write_bytes(raw[:44 + 8000 * 4])
        recf = pathlib.Path(td) / "rec.jsonl"
        s, rec = make_sup(td, {"transcribe": ["ok:x"], "record": str(recf)},
                          prod=True)
        try:
            try:
                s.transcribe(job_id="job-t", attempt=1, audio_name=w.name)
                obs["worker_transcribed_truncated_input"] = True
            except WorkerFailure as e:
                obs["worker_transcribed_truncated_input"] = False
                obs["worker_refusal"] = e.reason_code
            lines = [json.loads(x) for x in recf.read_text().splitlines()] \
                if recf.exists() else []
            obs["model_input_samples"] = [x["samples"] for x in lines
                                          if x["event"] == "transcribe"]
        finally:
            s.shutdown()
    obs["reproduced"] = bool(obs["truncated_read_silently"]
                             or obs["worker_transcribed_truncated_input"]
                             or obs["interrupted_write_left_final_path"])
    return obs


# ---- M03-AUDIT-11 ----------------------------------------------------------

@probe("p11")
def p11():
    obs = {}
    sd = native_shims.sounddevice()
    r = audio_mod.Recorder(sample_rate=16000)
    sd.fail_start = RuntimeError("start failed")
    try:
        r.start()
    except RuntimeError:
        pass
    sd.fail_start = None
    obs["recording_flag_after_failed_start"] = bool(r.recording)
    n_before = len(sd.streams)
    try:
        r.start()
    except Exception:
        pass
    obs["next_start_created_stream"] = len(sd.streams) > n_before
    obs["next_start_stream_started"] = bool(
        sd.streams[-1].started) if len(sd.streams) > n_before else False
    for which in ("stop", "close"):
        r2 = audio_mod.Recorder(sample_rate=16000)
        r2.start()
        st = sd.streams[-1]
        for i in range(5):
            st.callback(np.full((800, 1), 0.1 * (i + 1), dtype=np.float32),
                        800, None, None)
        setattr(sd, f"fail_{which}", RuntimeError(f"{which} failed"))
        try:
            buf = r2.stop()
            obs[f"{which}_failure_prefix_samples"] = int(buf.size)
            obs[f"{which}_failure_raised"] = False
        except RuntimeError:
            obs[f"{which}_failure_prefix_samples"] = 0
            obs[f"{which}_failure_raised"] = True
        setattr(sd, f"fail_{which}", None)
        obs[f"{which}_failure_close_attempted"] = st.close_calls > 0
    # app level: a stop failure during _finishCapture
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            a.set_sup(GateSup())
            a.phys = True
            d.startDictation()
            st = sd.streams[-1]
            for _ in range(20):
                st.callback(np.full((800, 1), 0.05, dtype=np.float32), 800,
                            None, None)
            sd.fail_stop = RuntimeError("device gone")
            a.phys = False
            try:
                d.finishDictation()
                obs["app_finish_raised"] = False
            except RuntimeError:
                obs["app_finish_raised"] = True
            sd.fail_stop = None
            obs["app_state_after_stop_failure"] = d.state
            obs["app_job_queued_with_audio"] = any(
                j.get("audio") is not None and len(j["audio"])
                for j in d._active_jobs)
        finally:
            sd.fail_stop = None
            a.close()
    obs["reproduced"] = bool(
        obs["recording_flag_after_failed_start"]
        or not obs["next_start_created_stream"]
        or obs["stop_failure_raised"] or obs["close_failure_raised"]
        or obs["app_finish_raised"])
    return obs


# ---- M03-AUDIT-12 ----------------------------------------------------------

CANARY = "CANARY-/Users/someone/secret-path transcript-words sk-TOKEN123"


@probe("p12")
def p12():
    obs = {}
    sent = []
    real = worker_mod._write_msg
    worker_mod._write_msg = sent.append
    try:
        worker_mod._fault({"req_id": "r", "op": "transcribe"},
                          "RuntimeError",
                          worker_mod._reason(RuntimeError(CANARY)))
    finally:
        worker_mod._write_msg = real
    obs["worker_fault_frame_contains_canary"] = "CANARY" in json.dumps(sent)
    with tempfile.TemporaryDirectory() as td:
        w = wav(pathlib.Path(td) / "audio", "job-c.wav")
        s, rec = make_sup(td, {"transcribe": ["raise:" + CANARY,
                                              "raise:" + CANARY]},
                          prod=True)
        try:
            try:
                s.transcribe(job_id="job-c", attempt=1, audio_name=w.name)
            except WorkerFailure as e:
                obs["workerfailure_reason_contains_canary"] = \
                    "CANARY" in str(e.reason_code)
            obs["operational_events_contain_canary"] = "CANARY" in rec.blob()
        finally:
            s.shutdown()
    obs["reproduced"] = bool(obs["worker_fault_frame_contains_canary"]
                             or obs["operational_events_contain_canary"]
                             or obs.get("workerfailure_reason_contains_canary"))
    return obs


# ---- M03-AUDIT-13 ----------------------------------------------------------

@probe("p13")
def p13():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        s, rec = make_sup(td, {})
        try:
            s.ensure_running()
            gen = s.generation
            for kind, patch in (("wrong_job", {"job_id": "job-OTHER"}),
                                ("old_attempt", {"attempt": 0}),
                                ("wrong_kind", {"kind": "clean"})):
                req = "req-live-" + kind
                pend = sup_mod._Pending() if "_Pending" in dir(sup_mod) \
                    else None
                if hasattr(s, "_new_pending"):
                    pend = s._new_pending(req, op="transcribe",
                                          job_id="job-A", attempt=1,
                                          generation=gen)
                    with s._state_lock:
                        s._pending[req] = pend
                else:
                    with s._state_lock:
                        s._pending[req] = pend
                msg = {"v": 1, "op": "result", "kind": "asr",
                       "req_id": req, "job_id": "job-A", "attempt": 1,
                       "generation": gen, "text": "x"}
                msg.update(patch)
                s._handle_message(msg, gen, s._proc)
                got = pend.msg or {}
                obs[f"{kind}_accepted_as_result"] = \
                    got.get("op") == "result"
                with s._state_lock:
                    s._pending.pop(req, None)
            # an OLD generation's fault naming a live request
            req = "req-live-fault"
            if hasattr(s, "_new_pending"):
                pend = s._new_pending(req, op="transcribe", job_id="job-A",
                                      attempt=1, generation=gen)
            else:
                pend = sup_mod._Pending()
            with s._state_lock:
                s._pending[req] = pend
            s._handle_message({"v": 1, "op": "fault", "req_id": req,
                               "reason_code": "x"}, gen - 1 if gen > 1
                              else 0, None)
            obs["old_generation_fault_resolved_live_request"] = \
                pend.event.is_set()
            with s._state_lock:
                s._pending.pop(req, None)
            # a non-object JSON frame
            try:
                s._handle_message([1, 2, 3], gen, None)
                obs["non_object_frame_raised"] = False
            except Exception:
                obs["non_object_frame_raised"] = True
        finally:
            s.shutdown()
    # outbound short write in the worker
    buf = bytearray()
    real_write = worker_mod.os.write

    def short_write(fd, data):
        chunk = bytes(data[:7])
        buf.extend(chunk)
        return len(chunk)

    worker_mod.os.write = short_write
    try:
        worker_mod._write_msg({"v": 1, "op": "result", "text": "x" * 100})
    except Exception:
        pass
    finally:
        worker_mod.os.write = real_write
    if len(buf) >= 4:
        need = int.from_bytes(buf[:4], "big")
        obs["short_write_frame_complete"] = len(buf) - 4 == need
    else:
        obs["short_write_frame_complete"] = False
    # a malformed JSON body with a trustworthy length to the real worker
    with tempfile.TemporaryDirectory() as td:
        plan = pathlib.Path(td) / "plan.json"
        plan.write_text(json.dumps({}))
        env = dict(os.environ, LOCALFLOW_PROD_WORKER_PLAN=str(plan),
                   LOCALFLOW_CODE_ROOT=str(CODE), PYTHONPATH=str(CODE))
        p = subprocess.Popen([sys.executable, str(PROD), "--audio-root", td],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env)
        try:
            body = b"{not json"
            p.stdin.write(len(body).to_bytes(4, "big") + body)
            p.stdin.flush()
            time.sleep(0.5)
            obs["worker_exited_on_malformed_frame"] = p.poll() is not None
        finally:
            p.kill()
            p.wait(5)
    obs["reproduced"] = bool(
        obs["wrong_job_accepted_as_result"]
        or obs["old_attempt_accepted_as_result"]
        or obs["wrong_kind_accepted_as_result"]
        or obs["old_generation_fault_resolved_live_request"]
        or obs["non_object_frame_raised"]
        or not obs["short_write_frame_complete"]
        or obs["worker_exited_on_malformed_frame"])
    return obs


# ---- M03-AUDIT-14 ----------------------------------------------------------

@probe("p14")
def p14():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        root = td / "audio"
        root.mkdir()
        outside = td / "outside.wav"
        store_mod.write_wav_f32(outside, np.full(800, 0.3, np.float32),
                                16000)
        os.symlink(outside, root / "job-link.wav")
        os.mkfifo(root / "job-fifo.wav")
        (root / "job-dir.wav").mkdir()
        w = worker_mod.Worker(str(root))

        class T:
            last_decode_ranges = None

            def transcribe(self, samples):
                return "read"

        w.transcriber = T()
        sent = []
        real = worker_mod._write_msg
        worker_mod._write_msg = sent.append
        try:
            for name in ("job-link.wav", "job-fifo.wav", "job-dir.wav"):
                sent.clear()
                done = threading.Event()
                box = {}

                def run(n=name):
                    try:
                        w._transcribe({"req_id": "r", "op": "transcribe",
                                       "audio": {"name": n}})
                        box["outcome"] = "result"
                    except Exception as e:
                        box["outcome"] = type(e).__name__
                    done.set()

                t = threading.Thread(target=run, daemon=True)
                t.start()
                finished = done.wait(1.5)
                if not finished and name == "job-fifo.wav":
                    # unblock the reader so the probe never hangs
                    fd = os.open(root / name, os.O_WRONLY | os.O_NONBLOCK)
                    os.close(fd)
                    done.wait(2)
                obs[name.split(".")[0] + "_outcome"] = (
                    box.get("outcome") if finished else "blocked")
            try:
                w._audio_path("../outside.wav")
                obs["traversal_accepted"] = True
            except Exception:
                obs["traversal_accepted"] = False
        finally:
            worker_mod._write_msg = real
    obs["reproduced"] = bool(obs["job-link_outcome"] == "result"
                             or obs["job-fifo_outcome"] == "blocked")
    return obs


# ---- M03-AUDIT-15 ----------------------------------------------------------

@probe("p15")
def p15():
    obs = {}
    sd = native_shims.sounddevice()

    def feed():
        st = sd.streams[-1]
        for _ in range(20):
            st.callback(np.full((800, 1), 0.05, dtype=np.float32), 800,
                        None, None)

    for cause in ("max_duration", "device_loss"):
        with tempfile.TemporaryDirectory() as td:
            a = App(td, cfg={"hands_free": "double_tap"},
                    start_coordinator=False)
            try:
                d = a.d
                a.set_sup(GateSup())
                # tap (short) then press again → hands-free
                a.phys = True
                d.startDictation()
                a.phys = False
                d.finishDictation()
                a.phys = True
                d.startDictation()
                a.phys = False
                feed()
                obs[f"{cause}_hands_free_entered"] = bool(
                    d._hands_free_active)
                if cause == "max_duration":
                    d.maxDurationHit_(None)
                else:
                    d.recorder.callback_error = "PortAudioError"
                    d.watchdog_(None)
                obs[f"{cause}_latch_after_forced_end"] = bool(
                    d._hands_free_active)
                n = len(sd.streams)
                a.phys = True
                d.startDictation()
                obs[f"{cause}_next_press_started_capture"] = (
                    d.state == app_mod.STATE_RECORDING
                    and len(sd.streams) > n)
                d.cancelDictation()
            finally:
                a.close()
    with tempfile.TemporaryDirectory() as td:
        a = App(td, cfg={"mouse_trigger": "middle"},
                start_coordinator=False)
        try:
            d = a.d
            a.set_sup(GateSup())
            mphys = {"down": False}
            mt = MouseTriggerListener(
                "middle", lambda: d.startDictation(source="mouse"),
                lambda: d.finishDictation(source="mouse"))
            mt.physically_down = lambda: mphys["down"]
            d.mouse_trigger = mt

            class Ev:
                def buttonNumber(self):
                    return 2

            mphys["down"] = True
            mt._down(Ev())
            feed()
            d._abandon_capture_for_system("system_sleep")
            mphys["down"] = False  # the mouse-up event is lost
            for _ in range(3):
                d.watchdog_(None)
            obs["mouse_held_after_idle_watchdog"] = bool(mt.held)
            n = len(sd.streams)
            mphys["down"] = True
            mt._down(Ev())
            obs["mouse_next_press_started_capture"] = (
                d.state == app_mod.STATE_RECORDING and len(sd.streams) > n)
            d.cancelDictation()
        finally:
            a.close()
    obs["reproduced"] = bool(
        not obs["max_duration_next_press_started_capture"]
        or not obs["device_loss_next_press_started_capture"]
        or not obs["mouse_next_press_started_capture"])
    return obs


# ---- M03-AUDIT-16 ----------------------------------------------------------

@probe("p16")
def p16():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        w = wav(pathlib.Path(td) / "audio", "job-d.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:Injected", "ok:after"]})
        try:
            s.ensure_running()
            per_gen = hasattr(s, "_stderr_tails")
            obs["wiring"] = "per_generation" if per_gen else "shared_tail"
            if per_gen:
                s._stderr_tails[s.generation].feed(b"a stderr line\n")
            else:
                s._stderr_tail.append(b"a stderr line\n")
            try:
                s._fault_detail(s.generation) if per_gen else \
                    s._fault_detail()
                obs["digest_raised"] = False
            except TypeError:
                obs["digest_raised"] = True
            try:
                res = s.transcribe(job_id="job-d", attempt=1,
                                   audio_name=w.name)
                obs["fault_resolved_with_worker_reason"] = True
                obs["retried"] = bool(res.get("retried"))
            except WorkerFailure as e:
                obs["fault_resolved_with_worker_reason"] = False
                obs["failure"] = e.reason_code
            obs["worker_fault_event_emitted"] = rec.count("worker.fault") > 0
            # a newline-free 4 MiB stderr stream
            big = b"x" * (4 * 1024 * 1024)

            class P:
                class stderr_cls:
                    def __init__(self):
                        self.done = False

                    def __iter__(self):
                        yield big

                    def read1(self, n=-1):
                        if self.done:
                            return b""
                        self.done = True
                        return big

                    def fileno(self):
                        raise OSError("no fd")

                stderr = stderr_cls()

            if per_gen:
                s._drain_stderr(P(), s.generation)
                kept = s._stderr_tails[s.generation].size()
            else:
                s._stderr_tail.clear()
                s._drain_stderr(P())
                kept = sum(len(x) for x in s._stderr_tail)
            obs["stderr_bytes_retained_from_4MiB_line"] = kept
            # an old generation's drainer writing after a replacement
            old_gen = s.generation
            s.restart()

            class Old:
                class e:
                    def __iter__(self):
                        yield b"late line from old generation\n"

                    def read1(self, n=-1):
                        if getattr(self, "d", False):
                            return b""
                        self.d = True
                        return b"late line from old generation\n"

                    def fileno(self):
                        raise OSError("no fd")

                stderr = e()

            if per_gen:
                s._drain_stderr(Old(), old_gen)
                cur = s._stderr_tails.get(s.generation)
                contaminated = bool(cur and cur.size())
            else:
                s._drain_stderr(Old())
                contaminated = any(b"old generation" in x
                                   for x in s._stderr_tail)
            obs["old_drainer_contaminated_new_generation"] = contaminated
        finally:
            s.shutdown()
    obs["reproduced"] = bool(
        obs["digest_raised"] or not obs["fault_resolved_with_worker_reason"]
        or not obs["worker_fault_event_emitted"]
        or obs["stderr_bytes_retained_from_4MiB_line"] > 256 * 1024
        or obs["old_drainer_contaminated_new_generation"])
    return obs


# ---- M03-AUDIT-17 ----------------------------------------------------------

@probe("p17")
def p17():
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d._insertion = None
            jid, fam = d.store.create_job(boot_id=d.v2log.boot_id,
                                          captured_at_utc=T0)
            job = {"job_id": jid, "family_id": fam, "ctx": None,
                   "failed": False, "cancelled": False, "attempt": 1,
                   "raw": "hi", "wav": None, "journal": None,
                   "captured_at_utc": T0, "stats": {}}
            d._pending = 1
            d._active_jobs.append(job)
            d.state = app_mod.STATE_PROCESSING
            d._finishWithText_("hello world", job)
            obs["clipboard_copies"] = len(a.copies)
            obs["active_jobs_after"] = len(d._active_jobs)
            obs["pending_after"] = d._pending
            obs["state_after"] = d.state
        finally:
            a.close()
    obs["reproduced"] = bool(obs["active_jobs_after"] or obs["pending_after"])
    return obs


# ---- design concerns ---------------------------------------------------------

@probe("d24")
def d24():
    """Per-stage retry budget: ASR fault+retry, cleanup fault+retry."""
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        w = wav(pathlib.Path(td) / "audio", "job-r.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:A", "ok:asr"],
                               "clean": ["fault:B", "ok:clean"]})
        sent = []
        real = s._send

        def send(msg, **kw):
            if msg.get("op") in ("transcribe", "clean"):
                sent.append([msg["op"], msg.get("attempt"),
                             msg.get("generation")])
            return real(msg, **kw)

        s._send = send
        try:
            r1 = s.transcribe(job_id="job-r", attempt=1, audio_name=w.name)
            r2 = s.clean(job_id="job-r", attempt=r1["attempt"],
                         raw_text="x")
            obs["executions"] = sent
            obs["final_attempt"] = r2["attempt"]
            obs["spawns"] = rec.count("worker.spawned")
        finally:
            s.shutdown()
    return obs


@probe("d25")
def d25():
    """Journal disabled: is a worker WAV still written and recoverable?"""
    obs = {}
    with tempfile.TemporaryDirectory() as td:
        a = App(td, cfg={"capture_journal": False}, start_coordinator=False)
        try:
            d = a.d
            gate = threading.Event()
            a.set_sup(GateSup(gate=gate))
            a.start_coordinator()
            a.phys = True
            d.startDictation()
            jid = d._job["job_id"]
            st = native_shims.sounddevice().streams[-1]
            for _ in range(20):
                st.callback(np.full((800, 1), 0.05, dtype=np.float32), 800,
                            None, None)
            a.phys = False
            d.finishDictation()
            d.supervisor.entered.wait(5)
            obs["blk_written"] = (a.journal / f"job-{jid}.blk").exists()
            obs["worker_wav_written"] = (a.journal
                                         / f"job-{jid}.wav").exists()
            gate.set()
        finally:
            gate.set()
            a.close()
    return obs


@probe("d27")
def d27():
    """Callback cost of the real Recorder callback + journal handoff
    (cloud CPU; not a reference-Mac measurement)."""
    sd = native_shims.sounddevice()
    with tempfile.TemporaryDirectory() as td:
        r = audio_mod.Recorder(sample_rate=16000)
        r.journal = cj.CaptureJournal(td, job_id="job-perf",
                                      sample_rate=16000)
        r.start()
        st = sd.streams[-1]
        block = np.random.default_rng(1).standard_normal(
            (800, 1)).astype(np.float32) * 0.01
        times = []
        for _ in range(2000):
            t0 = time.perf_counter()
            st.callback(block, 800, None, None)
            times.append((time.perf_counter() - t0) * 1e3)
        r.stop()
    times.sort()
    return {"blocks": len(times),
            "p50_ms": round(times[len(times) // 2], 4),
            "p99_ms": round(times[int(len(times) * 0.99)], 4),
            "max_ms": round(times[-1], 4)}


def main():
    names = sorted(PROBES)
    if ARGS.only:
        names = [n for n in names if n in ARGS.only.split(",")]
    out = {"schema_version": 1, "tool": "scripts/v2/m03_remediation_repro.py",
           "code_root_sha": subprocess.run(
               ["git", "-C", str(CODE), "rev-parse", "HEAD"],
               capture_output=True, text=True).stdout.strip(),
           "working_tree_modified": bool(subprocess.run(
               ["git", "-C", str(CODE), "status", "--porcelain",
                "--untracked-files=no"], capture_output=True,
               text=True).stdout.strip()),
           "python": sys.version.split()[0], "numpy": np.__version__,
           "native_shims": list(native_shims.SHIMMED),
           "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
           "findings": {}}
    for n in names:
        t0 = time.monotonic()
        try:
            res = PROBES[n]()
        except Exception as e:
            res = {"probe_error": type(e).__name__,
                   "trace_tail": traceback.format_exc().splitlines()[-3:]}
        res["seconds"] = round(time.monotonic() - t0, 2)
        out["findings"][n] = res
        print(f"{n}: reproduced={res.get('reproduced')}"
              f" ({res['seconds']}s)", flush=True)
    text = json.dumps(out, indent=1, sort_keys=True, default=str)
    if ARGS.output:
        pathlib.Path(ARGS.output).write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
