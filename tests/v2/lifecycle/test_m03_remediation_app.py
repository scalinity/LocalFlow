"""M03 remediation: production app orchestration (EV-04/EV-19, portable).

The REAL ``AppDelegate`` methods — startDictation/finishDictation, the
coordinator ``_worker``, ``_recover_journals``, ``_retry_job``,
``applicationWillTerminate_``, the watchdog — run against the real Store,
collector and Recorder, with only the native seams shimmed (declared in
native_shims.py: AppKit/PyObjC stubs, a scriptable sounddevice stream, a
recording insertion host and clipboard). Oracles are independent: direct
SQLite reads, exact bytes on disk, recorded host/clipboard writes.

  01  recovery never claims live/other-owner/resolved work and never
      replaces better audio; an abandoned journal still recovers exactly
  02  delete-everywhere vs worker-WAV publication (both orders), cached
      delivery, recovery retry, recovery residue, debug copy
  04  quit: capture stopped and kept, worker reaped without respawn,
      coordinator settled before the store closes, admission refused
  05  a failed automatic retry's executed attempt reaches store, recovery
      item, failure evidence and usage; the next retry is monotonic
  09  a T1 retry of a T0 capture keeps T0, the retained rate and the
      journal's gaps/tail; an unknown original instant stays unknown
  10  a truncated worker WAV recovers as an explicitly truncated prefix
  11  stream stop/close/start failures through the app keep the prefix
      and leave a working next capture
  15  forced ends clear the hands-free latch; a lost idle mouse-up is
      reconciled (a held button is not)
  17  the insertion-unavailable fallback retires its job once
  20  an out-of-bounds decode range is refused by production
  23  recovery-retry consent stays original permission AND enabled now

Run: .venv/bin/python tests/v2/lifecycle/test_m03_remediation_app.py
"""

import json
import pathlib
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import (App, GateSup, T0,  # noqa: E402
                         blocks_of, make_sup, run, tmpdir, v1_journal,
                         v2_journal)
import numpy as np  # noqa: E402
import localflow.app as app_mod  # noqa: E402
from localflow.hotkey import MouseTriggerListener  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import training  # noqa: E402


def _prev_job(d, *, state="capturing", captured=T0):
    jid, fam = d.store.create_job(boot_id="boot-previous",
                                  captured_at_utc=captured,
                                  time_quality="known" if captured
                                  else "unknown", state=state)
    return jid, fam


def test_01_recovery_ownership_and_selection():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            a.set_sup(GateSup())
            # (a) a live capture of THIS session, file on disk
            live, _ = a.dictate(blocks=6, release=False)
            blk = a.journal / f"job-{live}.blk"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not (
                    blk.exists() and blk.stat().st_size > 6 * 3200):
                time.sleep(0.01)
            size = blk.stat().st_size
            # (b) a resolved job's leftover journal
            done, _ = _prev_job(d)
            for st in ("queued", "transcribing", "ready_to_insert",
                       "insertion_posted", "insertion_confirmed"):
                d.store.update_job_state(done, st)
            v1_journal(a.journal / f"job-{done}.blk", done, blocks_of(8))
            # (c) a fuller complete WAV beside a half-length journal
            full_id, _ = _prev_job(d, state="transcribing")
            full = np.arange(16000, dtype=np.float32) / 1e5
            store_mod.write_wav_f32(a.journal / f"job-{full_id}.wav", full,
                                    16000)
            wav_bytes = (a.journal / f"job-{full_id}.wav").read_bytes()
            v1_journal(a.journal / f"job-{full_id}.blk", full_id,
                       [full[:8000]])
            # (d) positive control: abandoned v2 journal, no row at all
            ab = "job-abandoned0001"
            ab_blocks = blocks_of(10)
            v2_journal(a.journal / f"job-{ab}.blk", ab, ab_blocks,
                       meta={"captured_at_utc": T0,
                             "time_quality": "known"},
                       boot_id="boot-previous")
            d._recover_journals()
            offered = {i["job_id"] for i in d._recoverable}
            assert live not in offered and blk.exists()
            assert blk.stat().st_size >= size, "live journal truncated"
            assert a.state(live) == "capturing"
            assert done not in offered and a.state(done) == \
                "insertion_confirmed"
            assert not (a.journal / f"job-{done}.blk").exists(), \
                "consumed residue kept"
            assert (a.journal / f"job-{full_id}.wav").read_bytes() == \
                wav_bytes, "better audio replaced"
            assert full_id in offered
            prov = d._read_provenance(full_id)
            assert prov["source"] == "worker_wav" and \
                prov["sample_count"] == 16000
            assert ab in offered, "abandoned control not recovered"
            got, rate = store_mod.read_wav_f32(a.journal / f"job-{ab}.wav")
            assert np.array_equal(got, np.concatenate(ab_blocks))
            assert a.state(ab) == "failed_recoverable"
            row = d.store.job(ab)
            assert row["captured_at_utc"] == T0
            prov = d._read_provenance(ab)
            assert prov["source"] == "journal_reconstruction"
            assert prov["journal"]["status"] == "unfinalized"
            assert prov["complete"] is None  # end unknown, not assumed
            d.cancelDictation()
        finally:
            a.close()
    print("ok  01 recovery: live capture untouched, resolved residue"
          " removed, fuller WAV kept byte-exact; abandoned v2 journal"
          " recovered exactly with T0 and unknown completion")


HOLD_ROOT = r"""
import fcntl, os, sys, time
root = sys.argv[1]
os.makedirs(root, exist_ok=True)
fd = os.open(os.path.join(root, ".owner.lock"), os.O_CREAT | os.O_RDWR,
             0o600)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
print("held", flush=True)
sys.stdin.readline()
"""


def test_01_other_owner_root_claims_nothing():
    with tmpdir() as td:
        jroot = pathlib.Path(td) / "journal"
        holder = subprocess.Popen([sys.executable, "-c", HOLD_ROOT,
                                   str(jroot)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True)
        try:
            assert holder.stdout.readline().strip() == "held"
            v1_journal(jroot / "job-orphan00001.blk", "orphan00001",
                       blocks_of(12))
            a = App(td, start_coordinator=False)
            try:
                assert a.d._journal_root_lock is None
                a.d._recover_journals()
                assert a.d._recoverable == []
                assert (jroot / "job-orphan00001.blk").exists()
                ev = [e for e in _events(a) if e.get("event") ==
                      "capture.recovery_skipped"]
                assert ev and ev[-1]["reason_code"] == \
                    "journal_root_owned_elsewhere"
            finally:
                a.close()
        finally:
            holder.stdin.write("x\n")
            holder.stdin.flush()
            holder.wait(5)
    print("ok  01 journal root owned by another live process: nothing"
          " claimed, reported")


def _events(a):
    a.d.v2log.flush() if hasattr(a.d.v2log, "flush") else None
    time.sleep(0.2)
    out = []
    for p in sorted(pathlib.Path(app_mod.V2_EVENTS_DIR).glob("*")):
        try:
            for line in p.read_text().splitlines():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
        except OSError:
            pass
    return out


def test_02_delete_vs_worker_wav_publication_both_orders():
    # order A: deletion wins before the coordinator publishes
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            gate, entered = threading.Event(), threading.Event()
            real_state = d._job_state

            def gated(job_id, state, reason=None, retry=False):
                if state == "transcribing":
                    entered.set()
                    gate.wait(10)
                return real_state(job_id, state, reason=reason, retry=retry)

            d._job_state = gated
            sup = GateSup()
            a.set_sup(sup)
            a.start_coordinator()
            jid, _ = a.dictate()
            assert entered.wait(5)
            out = d.store.delete_everywhere("job", jid)
            assert out["complete"]
            gate.set()
            assert a.wait_call("_finishWithText_", 10)
            a.drain()
            time.sleep(0.3)
            assert sup.calls == [], "model ran for a deleted job"
            assert list(a.journal.glob(f"job-{jid}.*")) == []
            assert a.ins.submits == [] and a.copies == []
            assert a.db("SELECT COUNT(*) FROM usage_facts WHERE job_id=?",
                        (jid,))[0][0] == 0
        finally:
            gate.set()
            a.close()
    # order B: the WAV is published first; deletion then purges it and
    # revokes the cached delivery
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            gate = threading.Event()
            sup = GateSup(gate=gate)
            a.set_sup(sup)
            a.start_coordinator()
            jid, _ = a.dictate()
            assert sup.entered.wait(5)
            w = a.journal / f"job-{jid}.wav"
            assert w.exists(), "WAV not published before the model call"
            d.store.delete_everywhere("job", jid)
            assert not w.exists(), "published WAV survived deletion"
            gate.set()
            assert a.wait_call("_finishWithText_", 10)
            a.drain()
            time.sleep(0.3)
            assert a.ins.submits == [] and a.copies == []
            assert list(a.journal.glob(f"job-{jid}.*")) == []
        finally:
            gate.set()
            a.close()
    print("ok  02 delete before publish: no WAV, no model, no delivery;"
          " publish before delete: WAV purged, delivery revoked")


def test_02_store_arbitration_orders():
    with tmpdir() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        root = pathlib.Path(td) / "j"
        root.mkdir()
        st.register_job_payload_dir(root, lambda j: f"job-{j}.*")
        jid, _ = st.create_job()
        target = root / f"job-{jid}.wav"
        gate, entered = threading.Event(), threading.Event()

        def publish():
            entered.set()
            gate.wait(10)
            target.write_bytes(b"x")

        res = {}
        t = threading.Thread(target=lambda: res.update(
            pub=st.run_unless_deleted(jid, publish)))
        t.start()
        assert entered.wait(5)
        d = threading.Thread(target=lambda: res.update(
            dele=st.delete_everywhere("job", jid)))
        d.start()
        time.sleep(0.1)
        gate.set()
        t.join(10)
        d.join(10)
        assert res["pub"][0] is True
        assert res["dele"]["complete"] and not target.exists(), \
            "a publication serialized before deletion survived it"
        ok, _ = st.run_unless_deleted(jid, lambda: target.write_bytes(b"y"))
        assert ok is False and not target.exists()
        staged = store_mod.stage_wav_f32(target, np.zeros(4, np.float32),
                                         16000)
        assert st.publish_job_file(jid, staged, target) == "deleted"
        assert not staged.exists() and not target.exists()
        st.close()
    print("ok  02 store arbitration: publish-then-delete purged,"
          " delete-then-publish refused (staged file removed)")


def test_02_retry_recovery_and_debug_copy_after_delete():
    with tmpdir() as td:
        a = App(td, cfg={"log_transcripts": True}, start_coordinator=False)
        try:
            d = a.d
            a.set_sup(GateSup(text="retried"))
            jid, fam = _prev_job(d)
            d.store.update_job_state(jid, "failed_recoverable")
            a.journal.mkdir(parents=True, exist_ok=True)
            w = a.journal / f"job-{jid}.wav"
            store_mod.write_wav_f32(w, np.full(16000, 0.02, np.float32),
                                    16000)
            info = {"job_id": jid, "family_id": fam, "wav": str(w),
                    "raw": None, "attempt": 1}
            d._recoverable.append(info)
            d._last_failed = dict(info)
            d.store.delete_everywhere("job", jid)
            assert d._retry_job(info)["outcome"] == "not_retryable"
            assert d.hubRetryJob(jid)["outcome"] == "not_retryable"
            assert d._recoverable == [] and d._last_failed is None
            # residue appearing later is never resurrected
            v1_journal(a.journal / f"job-{jid}.blk", jid, blocks_of(12))
            d._recover_journals()
            assert d._recoverable == []
            assert list(a.journal.glob(f"job-{jid}.*")) == [] or \
                _wait_gone(a.journal, jid)
            # the transcript-logging debug copy is never recreated
            d._dump_audio(np.zeros(1600, np.float32), jid)
            assert list(app_mod.AUDIO_DEBUG_DIR.glob(f"*{jid}*")) == []
            # control: a live job's debug copy is written
            jid2, _ = d.store.create_job(boot_id=d.v2log.boot_id)
            d._dump_audio(np.zeros(1600, np.float32), jid2)
            assert list(app_mod.AUDIO_DEBUG_DIR.glob(f"*{jid2}*"))
        finally:
            a.close()
    print("ok  02 after deletion: retry refused (menu + History), residue"
          " not resurrected, debug copy not recreated; live control written")


def _wait_gone(root, jid, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not list(root.glob(f"job-{jid}.*")):
            return True
        time.sleep(0.02)
    return False


def test_04_quit_is_ordered():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            sup, srec = make_sup(td, {"transcribe": ["delay:5000|ok:late"]})
            sup.audio_root = str(a.journal)
            a.set_sup(sup)
            a.start_coordinator()
            j1, _ = a.dictate()
            deadline = time.monotonic() + 10
            while not sup._pending and time.monotonic() < deadline:
                time.sleep(0.01)
            assert sup._pending, "no request in flight at quit"
            worker = sup._proc
            j2, said = a.dictate(release=False)
            stream = a.sd().streams[-1]
            refused = []
            real = d.store._submit

            def counting(fn, *args, **kw):
                try:
                    return real(fn, *args, **kw)
                except RuntimeError as e:
                    if "store is" in str(e):
                        refused.append(1)
                    raise

            d.store._submit = counting
            spawns = srec.count("worker.spawned")
            d.applicationWillTerminate_(None)
            assert stream.closed and not d.recorder.recording
            assert worker.poll() is not None, "worker not reaped"
            assert srec.count("worker.spawned") == spawns
            assert not a._coord.is_alive(), "coordinator outlived the store"
            assert refused == [], "a producer wrote after the store closed"
            assert a.state(j1) == "failed_recoverable"
            assert a.state(j2) == "failed_recoverable"
            got, _ = store_mod.read_wav_f32(a.journal / f"job-{j2}.wav")
            assert np.array_equal(got, said), "quit lost captured speech"
            assert (a.journal / f"job-{j1}.wav").exists()
            d.startDictation()
            assert d.state != app_mod.STATE_RECORDING
            assert d._retry_job({"job_id": j1, "wav": "x"})["outcome"] \
                == "closing"
        finally:
            a.close()
    print("ok  04 quit: mic closed with speech kept, in-flight job"
          " recoverable, worker reaped (no respawn), coordinator settled"
          " first, zero post-close writes, admission refused")


def test_05_failed_retry_identity_end_to_end():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.consent.set("enabled")
            sup, _ = make_sup(td, {"transcribe": ["fault:A", "fault:B",
                                                  "ok:third"]})
            sup.audio_root = str(a.journal)
            sent = []
            real = sup._send

            def send(msg, **kw):
                if msg.get("op") == "transcribe":
                    sent.append(msg["attempt"])
                return real(msg, **kw)

            sup._send = send
            a.set_sup(sup)
            a.start_coordinator()
            jid, _ = a.dictate()
            assert a.wait_call("_finishWithText_", 30)
            a.drain()
            d.store.sync()
            assert sent == [1, 2]
            assert d.store.job(jid)["attempt"] == 2
            assert d._last_failed["attempt"] == 2
            env = a.envelope(jid)
            assert env["attempt"] == 2
            assert env["stage_generations"].get("asr") == 2
            assert a.db("SELECT attempt FROM usage_facts WHERE job_id=?",
                        (jid,))[0][0] == 2
            d._retry_job(d._last_failed)
            assert a.wait_call("_finishWithText_", 30)
            a.drain()
            d.store.sync()
            assert sent == [1, 2, 3], sent
            assert d.store.job(jid)["attempt"] == 3
            assert a.db("SELECT COUNT(*) FROM usage_facts WHERE job_id=?",
                        (jid,))[0][0] == 1, "one logical job, one fact"
            sup.shutdown()
        finally:
            a.close()
    print("ok  05 executed attempt 2 in store/recovery/evidence/usage;"
          " recovery retry runs attempt 3; one usage fact")


def test_09_t0_rate_and_gaps_survive_a_t1_retry():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.consent.set("enabled")
            rev = d.store.current_consent_id()
            jid, fam = _prev_job(d)
            d.store.upsert_example(job_id=jid, family_id=fam,
                                   consent_revision_id=rev)
            a.journal.mkdir(parents=True, exist_ok=True)
            blocks = blocks_of(12)
            # blocks 0-5 at 0.., a 1600-sample gap, blocks 6-11 after it
            starts = [i * 800 for i in range(6)] + \
                [6400 + i * 800 for i in range(6)]
            v2_journal(a.journal / f"job-{jid}.blk", jid, blocks, rate=8000,
                       starts=starts, tail=b"BLK\x01",
                       meta={"captured_at_utc": T0,
                             "time_quality": "known"})
            d._recover_journals()
            info = next(i for i in d._recoverable if i["job_id"] == jid)
            sup = GateSup(text="recovered words")
            a.set_sup(sup)
            a.start_coordinator()
            d._retry_job(info)
            assert a.wait_call("_finishWithText_", 15)
            a.drain()
            d.store.sync()
            assert sup.calls[0][2] == 8000, "rate relabeled"
            env = a.envelope(jid)
            assert env["captured_at_utc"] == T0
            assert env["time_quality"] == "known"
            cap = env["capture"]
            assert cap["sample_rate"] == 8000
            assert cap["audio_source"] == "journal_reconstruction"
            assert cap["journal_status"] == "torn_tail"
            kinds = [x["kind"] for x in
                     env["audio_preparation"]["discontinuities"]]
            assert "incomplete_tail" in kinds
            gaps = [x for x in env["audio_preparation"]["discontinuities"]
                    if x["kind"] == "journal_gap"]
            assert gaps == [{"kind": "journal_gap",
                             "source": "capture_journal", "at_sample": 4800,
                             "missing_samples": 1600,
                             "recovered_offset": 4800}], gaps
            assert a.db("SELECT activity_at_utc FROM usage_facts WHERE"
                        " job_id=?", (jid,))[0][0] == T0
            assert d.store.job(jid)["family_id"] == fam
        finally:
            a.close()
    # unknown original instant stays unknown
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.consent.set("enabled")
            rev = d.store.current_consent_id()
            jid, fam = _prev_job(d, captured=None)
            d.store.upsert_example(job_id=jid, family_id=fam,
                                   consent_revision_id=rev)
            a.journal.mkdir(parents=True, exist_ok=True)
            v1_journal(a.journal / f"job-{jid}.blk", jid, blocks_of(12))
            d._recover_journals()
            info = next(i for i in d._recoverable if i["job_id"] == jid)
            a.set_sup(GateSup())
            a.start_coordinator()
            d._retry_job(info)
            assert a.wait_call("_finishWithText_", 15)
            a.drain()
            d.store.sync()
            env = a.envelope(jid)
            assert env["captured_at_utc"] is None
            assert env["time_quality"] == "unknown"
            kinds = [x["kind"] for x in
                     env["audio_preparation"]["discontinuities"]]
            assert "timeline_unverified" in kinds  # v1: no positions
            assert "capture_end_unknown" in kinds  # no footer
        finally:
            a.close()
    print("ok  09 T1 retry keeps T0, 8 kHz, the torn tail and the gap at"
          " sample 4800; unknown instant stays unknown (v1: positions"
          " unverified, end unknown)")


def test_10_truncated_worker_wav_recovers_as_explicit_prefix():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.consent.set("enabled")
            rev = d.store.current_consent_id()
            jid, fam = _prev_job(d, state="transcribing")
            d.store.upsert_example(job_id=jid, family_id=fam,
                                   consent_revision_id=rev)
            a.journal.mkdir(parents=True, exist_ok=True)
            w = a.journal / f"job-{jid}.wav"
            full = np.arange(16000, dtype=np.float32) / 1e5
            store_mod.write_wav_f32(w, full, 16000)
            w.write_bytes(w.read_bytes()[:44 + 8000 * 4 + 2])
            d._recover_journals()
            info = next(i for i in d._recoverable if i["job_id"] == jid)
            got, _ = store_mod.read_wav_f32(w)  # strict read now succeeds
            assert np.array_equal(got, full[:8000])
            prov = d._read_provenance(jid)
            assert prov["source"] == "worker_wav_prefix"
            assert prov["complete"] is False
            assert prov["wav"] == {"declared_samples": 16000,
                                   "available_samples": 8000}
            row = d.store.job(jid)
            assert row["state_reason"] == "app_crash_audio_truncated"
            a.set_sup(GateSup())
            a.start_coordinator()
            d._retry_job(info)
            assert a.wait_call("_finishWithText_", 15)
            a.drain()
            d.store.sync()
            kinds = {x["kind"]: x for x in a.envelope(jid)[
                "audio_preparation"]["discontinuities"]}
            assert kinds["truncated_wav"]["declared_samples"] == 16000
            assert kinds["truncated_wav"]["available_samples"] == 8000
        finally:
            a.close()
    print("ok  10 truncated worker WAV: prefix republished whole, labeled"
          " truncated (16000 declared / 8000 kept) through the retry")


def test_11_stream_teardown_failures_through_the_app():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            sd = a.sd()
            a.set_sup(GateSup())
            for which in ("stop", "close"):
                jid, said = a.dictate(release=False)
                stream = sd.streams[-1]
                setattr(sd, f"fail_{which}", RuntimeError("device gone"))
                a.phys = False
                d.finishDictation()  # must not raise
                setattr(sd, f"fail_{which}", None)
                job = d._active_jobs[-1]
                assert job["job_id"] == jid
                assert np.array_equal(job["audio"], said)
                assert job["stats"]["stream_teardown_error"] == \
                    "RuntimeError"
                assert stream.close_calls == 1
                assert d.state == app_mod.STATE_PROCESSING
                d._active_jobs.clear()
                d._pending = 0
                d.state = app_mod.STATE_IDLE
            sd.fail_start = RuntimeError("no mic")
            a.phys = True
            d.startDictation()
            sd.fail_start = None
            assert d.state == app_mod.STATE_IDLE
            assert not d.recorder.recording
            n = len(sd.streams)
            jid, said = a.dictate()
            assert len(sd.streams) == n + 1 and sd.streams[-1].started
            assert np.array_equal(d._active_jobs[-1]["audio"], said)
        finally:
            a.close()
    print("ok  11 stop/close failure: prefix kept, close attempted, job"
          " queued; start failure: next capture opens a fresh stream")


def test_15_trigger_latches():
    for cause in ("max_duration", "device_loss"):
        with tmpdir() as td:
            a = App(td, cfg={"hands_free": "double_tap"},
                    start_coordinator=False)
            try:
                d = a.d
                a.set_sup(GateSup())
                sd = a.sd()
                a.phys = True
                d.startDictation()
                a.phys = False
                d.finishDictation()  # short tap → deferred
                a.phys = True
                d.startDictation()  # second tap → hands-free
                a.phys = False
                assert d._hands_free_active
                st = sd.streams[-1]
                for _ in range(20):
                    st.callback(np.full((800, 1), 0.05, np.float32), 800,
                                None, None)
                if cause == "max_duration":
                    d.maxDurationHit_(None)
                else:
                    d.recorder.callback_error = "PortAudioError"
                    d.watchdog_(None)
                assert d.state == app_mod.STATE_PROCESSING
                assert not d._hands_free_active
                n = len(sd.streams)
                a.phys = True
                d.startDictation()
                assert d.state == app_mod.STATE_RECORDING
                assert len(sd.streams) == n + 1
                d.cancelDictation()
            finally:
                a.close()
    with tmpdir() as td:
        a = App(td, cfg={"mouse_trigger": "middle"},
                start_coordinator=False)
        try:
            d = a.d
            a.set_sup(GateSup())
            phys = {"down": False}
            mt = MouseTriggerListener(
                "middle", lambda: d.startDictation(source="mouse"),
                lambda: d.finishDictation(source="mouse"))
            mt.physically_down = lambda: phys["down"]
            d.mouse_trigger = mt

            class Ev:
                def buttonNumber(self):
                    return 2

            phys["down"] = True
            mt._down(Ev())
            st = a.sd().streams[-1]
            for _ in range(20):
                st.callback(np.full((800, 1), 0.05, np.float32), 800,
                            None, None)
            d._abandon_capture_for_system("system_sleep")
            # control: the button is still physically held → not reset
            for _ in range(3):
                d.watchdog_(None)
            assert mt.held
            phys["down"] = False  # released, but the up event was lost
            d.watchdog_(None)
            assert mt.held, "reset on a single tick"
            d.watchdog_(None)
            assert not mt.held
            n = len(a.sd().streams)
            phys["down"] = True
            mt._down(Ev())
            assert d.state == app_mod.STATE_RECORDING
            assert len(a.sd().streams) == n + 1
            d.cancelDictation()
        finally:
            a.close()
    print("ok  15 max-duration/device-loss end clears hands-free (next press"
          " records); lost mouse-up reconciled after 2 idle ticks, a held"
          " button is not")


def test_17_insertion_unavailable_retires_once():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d._insertion = None
            a.set_sup(GateSup(text="kept text"))
            a.start_coordinator()
            jid, _ = a.dictate()
            assert a.wait_call("_finishWithText_", 10)
            a.drain()
            assert a.copies == [len("kept text ")]
            assert d._active_jobs == [] and d._pending == 0
            assert d.state == app_mod.STATE_IDLE
            assert a.state(jid) == "saved_not_inserted"
            assert (a.journal / f"job-{jid}.wav").exists(), \
                "saved-not-inserted keeps its recovery audio"
        finally:
            a.close()
    print("ok  17 insertion unavailable: copied once, job retired, pending"
          " 0, audio kept for retry")


def test_20_out_of_bounds_range_refused_in_production():
    with tmpdir() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        consent = training.ConsentManager(st, lambda *a, **k: None)
        consent.set("enabled")
        col = training.EvidenceCollector(st, lambda *a, **k: None, consent,
                                         lambda: {"p": 1})
        results = {}
        for name, ranges in (("ok", [[0, 1600]]), ("oob", [[0, 1601]]),
                             ("neg", [[-1, 10]]), ("empty", [[5, 5]]),
                             ("shape", [[0]])):
            jid, fam = st.create_job()
            ctx = col.job_started(jid, fam, captured_at_utc=T0,
                                  timezone="UTC", utc_offset_minutes=0)
            col.attach_capture_meta(ctx, {"device": "d"}, 16000)
            col.on_audio(ctx, np.zeros(1600, np.float32), 16000, {})
            col.on_asr_result(ctx, "x", model_id="m", model_revision="r",
                              stage_duration_ms=1.0, decode_ranges=ranges)
            col.on_cleanup_result(ctx, "x", path="raw")
            col.finalize(ctx)
            st.sync()
            env = st.latest_revision(ctx.example_id)
            assert env is not None, name
            results[name] = env
        assert results["ok"]["audio_preparation"]["decode_ranges"] == \
            [[0, 1600]]
        for bad in ("oob", "neg", "empty", "shape"):
            env = results[bad]
            assert env["audio_preparation"] is None, bad
            assert env["recognition"]["decode_ranges_rejected"]
        st.close()
    print("ok  20 production refuses out-of-bounds/negative/empty/malformed"
          " decode ranges; in-bounds control joined")


def test_23_retry_consent_is_original_and_enabled_now():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.consent.set("enabled")
            rev = d.store.current_consent_id()
            collected, fam1 = _prev_job(d)
            d.store.upsert_example(job_id=collected, family_id=fam1,
                                   consent_revision_id=rev)
            never, _ = _prev_job(d)
            assert d.collector.retry_snapshot(collected).collecting
            assert not d.collector.retry_snapshot(never).collecting
            d.consent.set("paused")
            assert not d.collector.retry_snapshot(collected).collecting
        finally:
            a.close()
    print("ok  23 retry consent unchanged: original permission AND enabled"
          " now")


def main():
    run([test_01_recovery_ownership_and_selection,
         test_01_other_owner_root_claims_nothing,
         test_02_delete_vs_worker_wav_publication_both_orders,
         test_02_store_arbitration_orders,
         test_02_retry_recovery_and_debug_copy_after_delete,
         test_04_quit_is_ordered,
         test_05_failed_retry_identity_end_to_end,
         test_09_t0_rate_and_gaps_survive_a_t1_retry,
         test_10_truncated_worker_wav_recovers_as_explicit_prefix,
         test_11_stream_teardown_failures_through_the_app,
         test_15_trigger_latches,
         test_17_insertion_unavailable_retires_once,
         test_20_out_of_bounds_range_refused_in_production,
         test_23_retry_consent_is_original_and_enabled_now],
        "m03 remediation app tests")


if __name__ == "__main__":
    main()
