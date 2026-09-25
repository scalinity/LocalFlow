"""M03 remediation — independent review round regressions (portable).

Every test here reproduces one finding of the independent adversarial
review of the frozen first pass (``a992d29``) and FAILS there; it passes
on the final production revision. Tests marked "guard" pin a safety
property of a new review-round path (they are not first-pass failures).

  R1  a stalled store writer delays, never fails, worker-audio publication
      (store: "unavailable" leaves the staged file; app: local
      check-rename-recheck fallback) — guard: deletion still wins
  R2  crash-left staged files are owned by the patterns that own their
      final name: debug-copy job pattern + rotation, artifact orphan scan
  R3  a relaunched root owner never claims a still-running second
      instance's in-flight job (per-process boot lock); a dead one's is
      claimed (control)
  R4  the startup scan and a user retry claim a job exclusively
  R5  "Copy last raw" never copies a deleted job's transcript
  R6  shutdown's hello wake-up cannot be erased by a spawn's clear
  R7  after an ASR load failure a clean request is answered (cleanup
      reported not loaded), never a fatal fault + respawn
  R8  a positioned journal gap is not also reported as an unpositioned
      queue drop
  R9  the journal block CRC covers seq/frames/start_sample
  R10 a revoked job's failure is not announced as a retry
  U1  a dictation transform's automatic retry attempt reaches job + store
  U3  the journal's deletion gate never abandons a queued file open
  U6  a job that failed normally before the relaunch keeps its own state,
      reason and live-capture provenance when the scan restores its item

Run: .venv/bin/python tests/v2/lifecycle/test_m03_review_round.py
"""

import json
import os
import pathlib
import signal
import struct
import subprocess
import sys
import threading
import time
import types
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import (ROOT, App, GateSup, T0, Rec,  # noqa: E402
                         blocks_of, make_sup, run, tmpdir, v1_journal, wav)
import numpy as np  # noqa: E402
from localflow.v2 import capture_journal as cj  # noqa: E402
from localflow.v2 import debug_audio as da  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.supervisor import WorkerFailure, WorkerSupervisor  # noqa: E402,E501


def _prev_job(d, *, state="capturing", reason=None):
    jid, fam = d.store.create_job(boot_id="boot-previous",
                                  captured_at_utc=T0, time_quality="known",
                                  state="capturing")
    if state != "capturing":
        d.store.update_job_state(jid, state, reason=reason)
    return jid, fam


def _events(d):
    seen = []
    real = d.v2log.emit

    def emit(event, *a, **kw):
        seen.append((event, kw))
        return real(event, *a, **kw)

    d.v2log.emit = emit
    return seen


def _close_boot_lock(d):
    fd = getattr(d, "_boot_lock", None)
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
        d._boot_lock = None


# ---- R1 -----------------------------------------------------------------

def test_R1_store_publish_unavailable_leaves_staged():
    with tmpdir() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        root = pathlib.Path(td) / "j"
        root.mkdir()
        st.register_job_payload_dir(root, lambda j: f"job-{j}.*")
        jid, _ = st.create_job()
        final = root / f"job-{jid}.wav"
        samples = np.linspace(-0.2, 0.2, 1600, dtype=np.float32)
        staged = store_mod.stage_wav_f32(final, samples, 16000)
        hold, held = threading.Event(), threading.Event()
        st._submit(lambda: (held.set(), hold.wait(10)))
        assert held.wait(5), "writer never stalled"
        out = st.publish_job_file(jid, staged, final, timeout=0.3)
        assert out == "unavailable", out
        assert staged.exists() and not final.exists()
        # the caller settles it itself; the still-queued rename then
        # tolerates the missing staged file
        os.replace(staged, final)
        hold.set()
        st.sync()
        arr, rate = store_mod.read_wav_f32(final)
        assert rate == 16000 and np.array_equal(arr, samples)
        st.close()
    print("ok  R1 store: a stalled writer reports 'unavailable' and leaves"
          " the staged file; the late queued rename is harmless")


def test_R1_app_store_stall_delays_not_fails_dictation():
    saved = (store_mod.Store.run_unless_deleted.__defaults__,
             store_mod.Store.publish_job_file.__defaults__,
             store_mod.stage_wav_f32)
    # Time-scaled store bounds (production 15 s): the first pass waited
    # the default bound, then failed the job.
    store_mod.Store.run_unless_deleted.__defaults__ = (1.5,)
    store_mod.Store.publish_job_file.__defaults__ = (1.5,)
    try:
        with tmpdir() as td:
            a = App(td, start_coordinator=False)
            d = a.d
            try:
                seen = _events(d)
                sup = GateSup(text="hello world")
                a.set_sup(sup)
                busy = threading.Event()
                real = saved[2]

                def staged(path, *args, **kw):
                    if "job-" in str(path) and not busy.is_set():
                        d.store._submit(lambda: (busy.set(),
                                                 time.sleep(4.0)))
                        busy.wait(5)
                    return real(path, *args, **kw)

                store_mod.stage_wav_f32 = staged
                a.start_coordinator()
                jid, _ = a.dictate()
                assert a.wait_call("_finishWithText_", 30)
                a.drain()
                assert busy.is_set(), "the store stall never happened"
                d.store.sync(timeout=15)
                assert [c[0] for c in sup.calls] == ["transcribe", "clean"]
                assert a.ins.submits == [len("hello world ")], \
                    a.ins.submits
                assert a.state(jid) == "insertion_unverified", a.state(jid)
                assert any(e == "store.publish_fallback" for e, _ in seen)
            finally:
                a.close()
    finally:
        (store_mod.Store.run_unless_deleted.__defaults__,
         store_mod.Store.publish_job_file.__defaults__,
         store_mod.stage_wav_f32) = saved
    print("ok  R1 app: a 4 s store stall past the publish bound delays the"
          " dictation (local fallback), text delivered once")


def test_R1_guard_deletion_during_stall_still_wins():
    saved = store_mod.stage_wav_f32
    try:
        with tmpdir() as td:
            a = App(td, start_coordinator=False)
            d = a.d
            gate = threading.Event()
            try:
                sup = GateSup(text="secret words", gate=gate)
                a.set_sup(sup)
                busy = threading.Event()

                def staged(path, *args, **kw):
                    if "job-" in str(path) and not busy.is_set():
                        d.store._submit(lambda: (busy.set(),
                                                 time.sleep(3.0)))
                        busy.wait(5)
                    return saved(path, *args, **kw)

                store_mod.stage_wav_f32 = staged
                a.start_coordinator()
                jid, _ = a.dictate()
                assert sup.entered.wait(15), "fallback never published"
                w = a.journal / f"job-{jid}.wav"
                assert w.exists(), "the fallback did not publish the WAV"
                out = d.store.delete_everywhere("job", jid)
                assert out["complete"]
                assert not w.exists(), "fallback-published WAV survived"
                gate.set()
                assert a.wait_call("_finishWithText_", 10)
                a.drain()
                time.sleep(0.3)
                assert a.ins.submits == [] and a.copies == []
                assert list(a.journal.glob(f"job-{jid}.*")) == []
            finally:
                gate.set()
                a.close()
    finally:
        store_mod.stage_wav_f32 = saved
    print("ok  R1 guard: deletion queued behind the stall purges the"
          " fallback-published WAV and revokes delivery")


# ---- R2 -----------------------------------------------------------------

_CRASH_CHILD = r"""
import os, sys, signal, pathlib
sys.path.insert(0, sys.argv[1])
import numpy as np
from localflow.v2 import store as sm, debug_audio as da
td = pathlib.Path(sys.argv[2]); which = sys.argv[3]; jid = sys.argv[4]
audio = np.full(16000, 0.25, np.float32)
def die(*a, **k):
    os.kill(os.getpid(), signal.SIGKILL)
if which == "artifact":
    st = sm.Store(td / "v2.db")
    jid, _ = st.create_job()
    st.sync()
    print(jid, flush=True)
    os.replace = die
    st.write_audio_artifact(job_id=jid, stage="capture", samples=audio,
                            sample_rate=16000)
else:
    print(jid, flush=True)
    os.replace = die
    da.write_debug_copy(td / "dbg", jid, audio, 16000, keep=5)
print("NOT KILLED", flush=True)
"""


def _crash(td, which, jid=""):
    p = subprocess.run([sys.executable, "-c", _CRASH_CHILD, str(ROOT),
                        str(td), which, jid], capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == -signal.SIGKILL, (p.returncode, p.stderr[-500:])
    return p.stdout.split()[0]


def test_R2_crash_left_staged_files_are_owned():
    with tmpdir() as td:
        td = pathlib.Path(td)
        dbg = td / "dbg"
        st = store_mod.Store(td / "v2.db")
        st.register_job_payload_dir(dbg, da.job_pattern)
        # (a) delete-everywhere owns a crash-left staged debug copy
        jid, _ = st.create_job()
        st.sync()
        _crash(td, "debug", jid)
        left = [p.name for p in dbg.iterdir()]
        assert len(left) == 1 and jid in left[0], left
        assert st.delete_everywhere("job", jid)["complete"]
        assert [p for p in dbg.iterdir() if jid in p.name] == [], \
            "staged debug copy of a deleted job survived"
        # (b) rotation owns one too
        other, _ = st.create_job()
        st.sync()
        _crash(td, "debug", other)
        newest, _ = st.create_job()
        for i in range(3):
            da.write_debug_copy(dbg, newest, np.zeros(10, np.float32),
                                16000, keep=1, seq=i + 2)
        names = sorted(p.name for p in dbg.iterdir())
        assert len(names) == 1 and newest in names[0], names
        st.close()
        # (c) the artifact orphan scan sees a crash-left staged artifact
        crashed = _crash(td, "artifact")
        st = store_mod.Store(td / "v2.db")
        staged = [p.name for p in st.artifacts_dir.iterdir() if p.is_file()]
        assert len(staged) == 1, staged
        assert staged[0] in st.verify()["orphan_files"], \
            "staged artifact invisible to verify()"
        assert st.sweep_orphans(grace_sec=0) == staged
        assert crashed
        st.close()
    print("ok  R2 crash-left staged debug copy: deleted with its job and"
          " rotated; staged artifact reported and swept as an orphan")


# ---- R3 -----------------------------------------------------------------

_HOLD_ROOT = r"""
import fcntl, os, sys
root = sys.argv[1]
os.makedirs(root, exist_ok=True)
fd = os.open(os.path.join(root, ".owner.lock"), os.O_CREAT | os.O_RDWR,
             0o600)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
print("held", flush=True)
sys.stdin.readline()
"""


def test_R3_relaunched_owner_never_claims_live_instance_work():
    with tmpdir() as td:
        jroot = pathlib.Path(td) / "journal"
        holder = subprocess.Popen([sys.executable, "-c", _HOLD_ROOT,
                                   str(jroot)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True)
        gate = threading.Event()
        b = a2 = a3 = None
        try:
            assert holder.stdout.readline().strip() == "held"
            b = App(td, start_coordinator=False)   # second instance
            assert b.d._journal_root_lock is None
            sup_b = GateSup(text="dictated once", gate=gate)
            b.set_sup(sup_b)
            b.start_coordinator()
            jid, _ = b.dictate()
            assert sup_b.entered.wait(5)
            blk = jroot / f"job-{jid}.blk"
            assert blk.exists() and b.state(jid) == "transcribing"
            holder.stdin.write("x\n")
            holder.stdin.flush()
            holder.wait(5)
            a2 = App(td, start_coordinator=False)  # relaunched owner
            assert a2.d._journal_root_lock is not None
            a2.d._recover_journals()
            assert b.state(jid) == "transcribing", b.state(jid)
            assert not any(i["job_id"] == jid for i in a2.d._recoverable)
            assert blk.exists(), "live instance's journal removed"
            gate.set()
            assert b.wait_call("_finishWithText_", 10)
            b.drain()
            b.d.store.sync()
            assert b.ins.submits == [len("dictated once ")]
            # control: an instance that died mid-job is residue
            jid2, _ = b.dictate()
            b.d.store.sync()
            dead_boot = b.d.v2log.boot_id
            _close_boot_lock(b.d)            # the process 'crashed'
            a2.close()
            a3 = App(td, start_coordinator=False)
            a3.d._recover_journals()
            assert any(i["job_id"] == jid2 for i in a3.d._recoverable), \
                "a dead instance's job was not recovered"
            assert not (jroot / f".boot-{dead_boot}.lock").exists()
        finally:
            gate.set()
            if holder.poll() is None:
                holder.kill()
            for x in (a3, a2, b):
                if x is not None:
                    _close_boot_lock(x.d)
                    x.close()
    print("ok  R3 relaunched root owner leaves a live second instance's job"
          " (delivered once by it); a dead instance's job is recovered")


# ---- R4 -----------------------------------------------------------------

def test_R4_scan_and_retry_claim_exclusively():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        d = a.d
        gate = threading.Event()
        try:
            jid, fam = _prev_job(d, state="failed_recoverable",
                                 reason="asr_failed")
            a.journal.mkdir(parents=True, exist_ok=True)
            w = a.journal / f"job-{jid}.wav"
            store_mod.write_wav_f32(w, np.full(16000, 0.02, np.float32),
                                    16000)
            info = {"job_id": jid, "family_id": fam, "wav": str(w),
                    "raw": None, "attempt": 1}
            a.set_sup(GateSup(text="retried text"))
            entered = threading.Event()
            real = d.collector.job_started

            def held(*args, **kw):
                entered.set()
                gate.wait(10)
                return real(*args, **kw)

            d.collector.job_started = held
            out = {}
            t = threading.Thread(target=lambda: out.update(
                r=d._retry_job(info)))
            t.start()
            assert entered.wait(5)
            assert a.state(jid) == "queued"  # re-opened, not yet live
            d._recover_journals()
            assert a.state(jid) == "queued", a.state(jid)
            assert not any(i["job_id"] == jid for i in d._recoverable)
            # a second click of the same job while the first holds it
            assert d._retry_job(dict(info))["outcome"] == "already_retrying"
            gate.set()
            t.join(10)
            assert out["r"]["outcome"] == "requeued"
            a.start_coordinator()
            assert a.wait_call("_finishWithText_", 10)
            a.drain()
            d.store.sync()
            assert a.ins.submits == [len("retried text ")]
            assert a.state(jid) == "insertion_unverified"
            assert jid not in d._live_job_ids(), "claim never released"
        finally:
            gate.set()
            a.close()
    print("ok  R4 scan during the retry window leaves the claimed job;"
          " second click refused; delivered once, claim released")


# ---- R5 -----------------------------------------------------------------

class _CleanFails(GateSup):
    def clean(self, *, job_id, attempt, raw_text, **kw):
        self.calls.append(("clean", attempt, None, None))
        raise WorkerFailure("stage_exception", stage="clean",
                            attempt=attempt + 1, generation=2, retried=True)


def test_R5_copy_last_raw_after_delete():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        d = a.d
        try:
            a.set_sup(_CleanFails(text="my private words"))
            a.start_coordinator()
            jid, _ = a.dictate()
            assert a.wait_call("_finishWithText_", 10)
            a.drain()
            assert (d._last_failed or {}).get("raw") == "my private words"
            a.copies.clear()
            d.copyLastRaw_(None)
            assert a.copies == [len("my private words")]  # control
            assert d.store.delete_everywhere("job", jid)["complete"]
            a.drain()
            a.copies.clear()
            d.copyLastRaw_(None)
            assert a.copies == [], "deleted transcript copied"
            assert d._last_failed is None
        finally:
            a.close()
    print("ok  R5 'Copy last raw' copies before deletion, nothing after;"
          " the cached failure is dropped")


# ---- R6 -----------------------------------------------------------------

class _HookedEvent(threading.Event):
    def __init__(self):
        super().__init__()
        self.shutdown_set = threading.Event()
        self.on_first_clear = None

    def set(self):
        super().set()
        if threading.current_thread().name == "r6-shutdown":
            self.shutdown_set.set()

    def clear(self):
        cb, self.on_first_clear = self.on_first_clear, None
        if cb is not None:
            cb()
        super().clear()


def test_R6_shutdown_wake_cannot_be_erased():
    with tmpdir() as td:
        s = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio", asr_model="x",
            emit=Rec(), worker_cmd=[sys.executable, "-c",
                                    "import time; time.sleep(60)"],
            hello_timeout=8.0)
        ev = _HookedEvent()
        s._hello = ev
        res = {}

        def shut():
            res["status"] = s.shutdown(timeout=1.0)

        def at_clear():
            # shutdown lands between the spawn's closed-check and its
            # clear (the first pass let it complete here)
            threading.Thread(target=shut, name="r6-shutdown").start()
            ev.shutdown_set.wait(1.0)

        ev.on_first_clear = at_clear
        t0 = time.monotonic()
        try:
            s.ensure_running()
            res["spawn"] = "returned"
        except WorkerFailure as e:
            res["spawn"] = e.reason_code
        spawn_sec = time.monotonic() - t0
        deadline = time.monotonic() + 5
        while "status" not in res and time.monotonic() < deadline:
            time.sleep(0.01)
        assert res["spawn"] == "supervisor_closed", res
        assert spawn_sec < 4.0, f"spawn held the lifecycle {spawn_sec:.1f}s"
        assert res["status"]["lifecycle_acquired"] is True, res
        assert s._proc is None
    print(f"ok  R6 shutdown during the spawn's clear: spawn woken in"
          f" {spawn_sec:.2f}s (hello_timeout 8 s), lifecycle acquired")


# ---- R7 -----------------------------------------------------------------

def test_R7_clean_after_asr_load_failure_is_answered():
    with tmpdir() as td:
        s, rec = make_sup(td, {"asr_load": "fail"}, prod=True)
        try:
            s.ensure_running()
            assert s.wait_engine("asr", 15) == "failed"
            assert s.wait_engine("cleanup", 5) == "failed", s.engine_state
            out = s.clean(job_id="job-x", attempt=1, raw_text="um hello")
            assert out["path"] != "llm", out
            assert not out.get("retried") and out["attempt"] == 1
            assert out["generation"] == 1
            for name in ("worker.died", "worker.restarting",
                         "worker.retired"):
                assert rec.count(name) == 0, (name, rec.named(name))
            assert rec.count("worker.spawned") == 1
        finally:
            s.shutdown()
    print("ok  R7 ASR load failure: cleanup reported failed, a clean request"
          " answered by generation 1 (no death, no respawn)")


# ---- R8 -----------------------------------------------------------------

def test_R8_gap_not_double_reported():
    import hashlib
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        d = a.d
        try:
            d.consent.set("enabled")
            rev = d.store.current_consent_id()
            jid, fam = _prev_job(d)
            d.store.upsert_example(job_id=jid, family_id=fam,
                                   consent_revision_id=rev)
            a.journal.mkdir(parents=True, exist_ok=True)
            blocks = blocks_of(12)
            starts = [i * 800 for i in range(6)] + \
                [6400 + i * 800 for i in range(6)]  # 2 blocks lost @4800
            sha = hashlib.sha256(b"".join(np.asarray(b, "<f4").tobytes()
                                          for b in blocks)).hexdigest()
            footer = {"op": "finalize", "blocks": 12, "samples": 9600,
                      "sha256": sha, "offered_samples": 11200,
                      "dropped_blocks": 2, "dropped_samples": 1600}
            from m03_helpers import v2_journal
            v2_journal(a.journal / f"job-{jid}.blk", jid, blocks,
                       footer=footer, starts=starts,
                       meta={"captured_at_utc": T0, "time_quality": "known"})
            d._recover_journals()
            info = next(i for i in d._recoverable if i["job_id"] == jid)
            a.set_sup(GateSup(text="words"))
            a.start_coordinator()
            d._retry_job(info)
            assert a.wait_call("_finishWithText_", 15)
            a.drain()
            d.store.sync()
            disc = a.envelope(jid)["audio_preparation"]["discontinuities"]
            kinds = [x["kind"] for x in disc]
            gaps = [x for x in disc if x["kind"] == "journal_gap"]
            assert [(g["at_sample"], g["missing_samples"]) for g in gaps] \
                == [(4800, 1600)], disc
            assert "journal_queue_drop" not in kinds, kinds
        finally:
            a.close()
    print("ok  R8 the lost span is reported once, positioned"
          " (journal_gap @4800 x1600), not also as a queue drop")


# ---- R9 -----------------------------------------------------------------

def _blk_offsets(raw):
    out, i = [], raw.find(b"BLK")
    while i >= 0:
        out.append(i)
        i = raw.find(b"BLK", i + 3)
    return out


def test_R9_crc_covers_positions():
    with tmpdir() as td:
        j = cj.CaptureJournal(td, job_id="job-crc", sample_rate=16000)
        for b in blocks_of(4):
            j.handoff_block(b)
        assert j.finalize(timeout=10)["finalized"]
        raw = bytearray(j.blk_path.read_bytes())
        ok = cj.reconstruct(j.blk_path)
        assert ok.status == cj.STATUS_VERIFIED and ok.gaps == []
        offs = _blk_offsets(bytes(raw))
        assert len(offs) == 4
        for field, delta in (("start_sample", 15 + 4), ("seq", 3),
                             ("frames", 7)):
            bad = bytearray(raw)
            bad[offs[3] + delta] ^= 0x01
            p = pathlib.Path(td) / f"bad-{field}.blk"
            p.write_bytes(bytes(bad))
            r = cj.reconstruct(p)
            assert r.status != cj.STATUS_VERIFIED, (field, r.status)
            assert not r.gaps or all(g["missing_samples"] < 2 ** 31
                                     for g in r.gaps), (field, r.gaps)
        # the documented definition, independently of the writer:
        # crc32(<u32 seq><u32 frames><u64 start> + payload)
        payload = np.asarray(blocks_of(1)[0], "<f4").tobytes()
        o = offs[0] + 3
        seq, frames, _rb = struct.unpack_from("<III", raw, o)
        start, crc = struct.unpack_from("<QI", raw, o + 12)
        assert crc == zlib.crc32(payload, zlib.crc32(
            struct.pack("<IIQ", seq, frames, start)))
    print("ok  R9 one flipped bit in start_sample/seq/frames makes the"
          " journal not-verified (no fabricated gap); CRC definition pinned")


# ---- R10 ----------------------------------------------------------------

def test_R10_revoked_failure_not_announced_as_retry():
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-r.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:A", "ok:never"]})
        sent = []
        real = s._send

        def send(msg, **kw):
            sent.append(msg.get("op"))
            return real(msg, **kw)

        s._send = send
        try:
            s.revoke_job("job-r")
            try:
                s.transcribe(job_id="job-r", attempt=1, audio_name=w.name)
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure as e:
                assert e.reason_code == "request_revoked", e.reason_code
                assert e.fatal is True and not e.retried
                assert e.attempt == 1, "executed attempt not carried"
            assert sent.count("transcribe") == 1
            assert rec.count("worker.restarting") == 0, \
                rec.named("worker.restarting")
            assert rec.count("worker.spawned") == 1
            assert [x.get("reason_code") for x in
                    rec.named("worker.retry_skipped")] == ["request_revoked"]
        finally:
            s.shutdown()
    print("ok  R10 revoked job: one attempt, no 'restarting' event, the"
          " skipped retry recorded as such")


# ---- U1 -----------------------------------------------------------------

def test_U1_transform_retry_attempt_acknowledged():
    from localflow.v2 import transforms as T
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        d = a.d
        s = None
        try:
            s, _rec = make_sup(td, {"transform": ["fault:X",
                                                  "ok:TRANSFORMED"]})
            sent = []
            real = s._send

            def send(msg, **kw):
                if msg.get("op") == "transform":
                    sent.append(msg.get("attempt"))
                return real(msg, **kw)

            s._send = send
            a.set_sup(s)
            defn = T.definitions.built_ins()[0]
            jid, _ = d.store.create_job(boot_id=d.v2log.boot_id)
            snap = types.SimpleNamespace(
                auto_apply_decision=lambda *x: (defn, None))
            wp = types.SimpleNamespace(mode=defn.mode, profile_name="p",
                                       category=None)
            job = {"job_id": jid, "attempt": 1,
                   "m10": {"wp": wp, "transforms": snap}}
            d._m11_apply_transform(job, "some clean text here", None)
            d.store.sync()
            assert sent == [1, 2], sent
            assert job["attempt"] == 2, job["attempt"]
            assert d.store.job(jid)["attempt"] == 2
        finally:
            if s is not None:
                s.shutdown()
            a.close()
    print("ok  U1 dictation transform retried as attempt 2: job and store"
          " attempt follow it")


# ---- U3 -----------------------------------------------------------------

def _fds_on(path):
    """Descriptors of this process open on ``path`` (Linux /proc), or
    None where /proc is unavailable (macOS)."""
    if not os.path.isdir("/proc/self/fd"):
        return None
    out = []
    for fd in os.listdir("/proc/self/fd"):
        try:
            if os.readlink(f"/proc/self/fd/{fd}") == str(path):
                out.append(fd)
        except OSError:
            continue
    return out


def test_U3_journal_gate_never_abandons_its_open():
    saved = store_mod.Store.run_unless_deleted.__defaults__
    store_mod.Store.run_unless_deleted.__defaults__ = (0.5,)
    try:
        with tmpdir() as td:
            a = App(td, start_coordinator=False)
            d = a.d
            try:
                jid, _ = d.store.create_job(boot_id=d.v2log.boot_id)
                d.store.sync()
                held = threading.Event()
                d.store._submit(lambda: (held.set(), time.sleep(1.5)))
                assert held.wait(5)
                root = pathlib.Path(td) / "u3"
                j = cj.CaptureJournal(root, job_id=jid, sample_rate=16000,
                                      open_gate=d._journal_open_gate(jid))
                blocks = blocks_of(6)
                for b in blocks:
                    j.handoff_block(b)
                stats = j.finalize(timeout=10)
                d.store.sync()
                r = cj.reconstruct(j.blk_path)
                assert stats["finalized"] and not j.degraded, stats
                assert r.status == cj.STATUS_VERIFIED, r.status
                assert np.array_equal(r.samples, np.concatenate(blocks))
                leaked = _fds_on(j.blk_path.resolve())
                assert leaked in ([], None), "leaked fd"
                fd_note = "no orphaned descriptor" if leaked == [] \
                    else "descriptor check n/a (no /proc)"
            finally:
                a.close()
    finally:
        store_mod.Store.run_unless_deleted.__defaults__ = saved
    print("ok  U3 a store stall past the default bound: the journal waits"
          f" for its gated open, finalizes verified, {fd_note}")


# ---- U6 -----------------------------------------------------------------

def test_U6_prior_normal_failure_keeps_its_labels():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        d = a.d
        try:
            jid, fam = _prev_job(d, state="failed_recoverable",
                                 reason="asr_failed")
            a.journal.mkdir(parents=True, exist_ok=True)
            w = a.journal / f"job-{jid}.wav"
            samples = np.full(16000, 0.02, np.float32)
            store_mod.write_wav_f32(w, samples, 16000)
            prov = {"capture_provenance_version": 1, "job_id": jid,
                    "family_id": fam, "captured_at_utc": T0,
                    "time_quality": "known", "sample_rate": 16000,
                    "sample_count": 16000, "channels": 1,
                    "source": "live_memory", "complete": True}
            (a.journal / f"job-{jid}.capture.json").write_text(
                json.dumps(prov))
            v1_journal(a.journal / f"job-{jid}.blk", jid, blocks_of(12))
            d._recover_journals()
            d.store.sync()
            row = d.store.job(jid)
            assert row["state"] == "failed_recoverable"
            assert row.get("state_reason") == "asr_failed", \
                row.get("state_reason")
            assert any(i["job_id"] == jid for i in d._recoverable)
            back = json.loads((a.journal / f"job-{jid}.capture.json")
                              .read_text())
            assert not back.get("recovered"), back
            assert back["source"] == "live_memory"
        finally:
            a.close()
    print("ok  U6 a normally failed job is re-offered with its own state"
          " reason and live-capture provenance (not relabeled a crash)")


def main():
    run([test_R1_store_publish_unavailable_leaves_staged,
         test_R1_app_store_stall_delays_not_fails_dictation,
         test_R1_guard_deletion_during_stall_still_wins,
         test_R2_crash_left_staged_files_are_owned,
         test_R3_relaunched_owner_never_claims_live_instance_work,
         test_R4_scan_and_retry_claim_exclusively,
         test_R5_copy_last_raw_after_delete,
         test_R6_shutdown_wake_cannot_be_erased,
         test_R7_clean_after_asr_load_failure_is_answered,
         test_R8_gap_not_double_reported,
         test_R9_crc_covers_positions,
         test_R10_revoked_failure_not_announced_as_retry,
         test_U1_transform_retry_attempt_acknowledged,
         test_U3_journal_gate_never_abandons_its_open,
         test_U6_prior_normal_failure_keeps_its_labels],
        "m03 review round tests")


if __name__ == "__main__":
    main()
