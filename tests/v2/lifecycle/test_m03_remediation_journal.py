"""M03 remediation: capture-journal integrity, gaps and ownership (EV-04).

Journal bytes are built INDEPENDENTLY with ``struct`` (m03_helpers
``v1_journal``/``v2_journal``) — never by the production writer — so a
format both sides misunderstood would fail here. Positive controls sit
beside every negative case.

  08  sequence reorder/duplicate, payload bit flip, bad footer count/hash,
      lone ``{``, partial footer, bytes after the footer, interior
      corruption before valid blocks, torn tail, record-boundary EOF with
      unknown finalization — each classified, never spliced; v2 positions
      name every gap (interior and trailing) at its original sample
  19  the production writer under queue overflow persists gaps at the
      exact dropped positions; a real Recorder on a failing disk keeps the
      full in-memory capture while only the journal degrades; the live
      stats carry no audio discontinuity
  01  ``is_live``: a writing journal is owned (in this and another
      process); a finished or killed writer's file is residue
  02  a writer delayed before it creates its file cannot recreate a
      discarded journal, and a deletion-gated create never happens

Run: .venv/bin/python tests/v2/lifecycle/test_m03_remediation_journal.py
"""

import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import (ROOT, blocks_of, native_shims, run,  # noqa: E402
                         tmpdir, v1_journal, v2_journal)
import numpy as np  # noqa: E402
from localflow import audio as audio_mod  # noqa: E402
from localflow.v2 import capture_journal as cj  # noqa: E402

B = blocks_of(4)
ALL = np.concatenate(B)


def _sha(blocks):
    return hashlib.sha256(b"".join(np.asarray(b, dtype="<f4").tobytes()
                                   for b in blocks)).hexdigest()


def _fin(blocks=4, samples=3200, sha=None, **extra):
    d = {"op": "finalize", "blocks": blocks, "samples": samples,
         "sha256": sha or _sha(B)}
    d.update(extra)
    return json.dumps(d).encode() + b"\n"


def _rec(td, name, **kw):
    p = pathlib.Path(td) / f"{name}.blk"
    builder = kw.pop("builder", v1_journal)
    builder(p, "job-x", kw.pop("blocks", B), **kw)
    return cj.reconstruct(p)


def test_08_v1_integrity_matrix():
    with tmpdir() as td:
        ok = _rec(td, "control", finalize=_fin())
        assert ok.status == cj.STATUS_VERIFIED and ok.finalized is True
        assert np.array_equal(ok.samples, ALL) and ok.integrity == \
            "footer_sha256"
        cases = {
            "reordered": dict(seqs=[1, 3, 2, 4]),
            "duplicate": dict(seqs=[1, 2, 2, 3]),
            "bad_hash": dict(finalize=_fin(sha="0" * 64)),
            "bad_count": dict(finalize=_fin(blocks=9)),
            "after_footer": dict(finalize=_fin(), tail=b"BLK"),
            "bad_footer_json": dict(tail=b'{"op": "finalize"\n'),
        }
        want = {"reordered": ("corrupt", "sequence_break", 800),
                "duplicate": ("corrupt", "sequence_break", 1600),
                "bad_hash": ("corrupt", "footer_mismatch", 3200),
                "bad_count": ("corrupt", "footer_mismatch", 3200),
                "after_footer": ("corrupt", "bytes_after_footer", 3200),
                "bad_footer_json": ("corrupt", "footer_unparsable", 3200)}
        for name, kw in cases.items():
            r = _rec(td, name, **kw)
            st, reason, n = want[name]
            assert (r.status, r.corrupt_reason, r.samples.size) == \
                (st, reason, n), (name, r.status, r.corrupt_reason,
                                  r.samples.size)
            assert r.finalized is None and r.incomplete_tail
            assert np.array_equal(r.samples, ALL[:n]), name
        # a finalized v1 journal whose payload bit flipped
        p = pathlib.Path(td) / "flip.blk"
        v1_journal(p, "job-x", B, finalize=_fin())
        raw = bytearray(p.read_bytes())
        raw[raw.index(b"BLK") + 16 + 40] ^= 0x40
        p.write_bytes(bytes(raw))
        r = cj.reconstruct(p)
        assert (r.status, r.corrupt_reason) == ("corrupt", "footer_mismatch")
        # a lone "{" / a partial footer: finalization UNKNOWN, not clean
        for tail in (b"{", b'{"op": "finali'):
            r = _rec(td, "brace", tail=tail)
            assert r.status == cj.STATUS_TORN_FOOTER, r.status
            assert r.finalized is None and r.samples.size == 3200
        # exact record-boundary EOF: all samples, finalization unknown
        r = _rec(td, "boundary")
        assert r.status == cj.STATUS_UNFINALIZED and r.finalized is None
        assert not r.incomplete_tail and r.integrity == "unverified"
        assert np.array_equal(r.samples, ALL)
        # interior corruption before later VALID blocks ≠ torn tail
        p = pathlib.Path(td) / "interior.blk"
        v1_journal(p, "job-x", B)
        raw = bytearray(p.read_bytes())
        second = raw.index(b"BLK", raw.index(b"BLK") + 3)
        raw[second:second + 3] = b"XXX"
        p.write_bytes(bytes(raw))
        r = cj.reconstruct(p)
        assert (r.status, r.corrupt_reason, r.torn) == (
            "corrupt", "record_invalid", False)
        assert np.array_equal(r.samples, B[0]) and r.torn_bytes > 2 * 3200
        p = pathlib.Path(td) / "torn.blk"
        v1_journal(p, "job-x", B)
        p.write_bytes(p.read_bytes()[:-100])
        r = cj.reconstruct(p)
        assert (r.status, r.torn) == (cj.STATUS_TORN_TAIL, True)
        assert np.array_equal(r.samples, ALL[:2400])
    print("ok  08 v1: reorder/dup/footer hash+count/bit flip/after-footer"
          " corrupt; lone { and partial footer unknown; interior ≠ torn;"
          " boundary EOF unknown finalization")


def test_08_v2_positions_crc_and_gaps():
    with tmpdir() as td:
        # blocks at 0, 800, [gap 800 samples], 2400, 3200 → offered 4800
        starts = [0, 800, 2400, 3200]
        foot = {"op": "finalize", "blocks": 4, "samples": 3200,
                "sha256": _sha(B), "offered_samples": 4800,
                "dropped_blocks": 2, "dropped_samples": 1600}
        r = _rec(td, "gaps", builder=v2_journal, starts=starts, footer=foot)
        assert r.status == cj.STATUS_VERIFIED and r.integrity == \
            "crc32_per_block"
        assert np.array_equal(r.samples, ALL)
        assert r.gaps == [
            {"at_sample": 1600, "missing_samples": 800,
             "recovered_offset": 1600},
            {"at_sample": 4000, "missing_samples": 800,
             "recovered_offset": 3200}], r.gaps
        assert r.segments[2] == [1600, 2400, 800]
        # a payload bit flip is caught by the per-block CRC (no footer)
        crcs = [None] * 4
        import zlib
        crcs = [zlib.crc32(np.asarray(b, "<f4").tobytes()) for b in B]
        crcs[2] ^= 1
        r = _rec(td, "crc", builder=v2_journal, crcs=crcs)
        assert (r.status, r.corrupt_reason) == ("corrupt", "crc_mismatch")
        assert np.array_equal(r.samples, ALL[:1600])
        # overlapping positions are corrupt, never spliced
        r = _rec(td, "overlap", builder=v2_journal,
                 starts=[0, 800, 1200, 2000])
        assert (r.status, r.corrupt_reason) == ("corrupt",
                                                "position_overlap")
        # unfinalized v2: positions known, trailing extent unknown
        r = _rec(td, "open", builder=v2_journal, starts=[0, 1600, 2400,
                                                         3200])
        assert r.status == cj.STATUS_UNFINALIZED and r.positions_known
        assert r.gaps == [{"at_sample": 800, "missing_samples": 800,
                           "recovered_offset": 800}]
    print("ok  08 v2: CRC per block, positioned interior + trailing gaps,"
          " overlap corrupt, unfinalized extent unknown")


def test_19_writer_overflow_persists_gap_positions():
    with tmpdir() as td:
        j = cj.CaptureJournal(td, job_id="job-flood", sample_rate=16000)
        gate = threading.Event()
        real = cj.CaptureJournal._open_file

        def held(self, *a, **kw):
            gate.wait(10)
            return real(self, *a, **kw)

        cj.CaptureJournal._open_file = held
        try:
            n_blocks = cj.QUEUE_BOUND + 40
            for i in range(n_blocks):
                j.handoff_block(np.full(160, float(i), dtype=np.float32))
            gate.set()
            stats = j.finalize(timeout=10)
        finally:
            cj.CaptureJournal._open_file = real
        # the queue held blocks 1..QUEUE_BOUND (block 0 was popped first)
        assert stats["queue_dropped"] > 0 and stats["finalized"]
        r = cj.reconstruct(j.blk_path)
        assert r.status == cj.STATUS_VERIFIED
        kept = [int(r.samples[k * 160]) for k in range(r.samples.size // 160)]
        dropped = sorted(set(range(n_blocks)) - set(kept))
        assert len(dropped) == stats["queue_dropped"]
        # every gap starts where the first missing block was offered, and
        # the missing samples are exactly the dropped blocks
        missing = []
        for g in r.gaps:
            assert g["at_sample"] % 160 == 0
            missing += list(range(g["at_sample"] // 160,
                                  (g["at_sample"] + g["missing_samples"])
                                  // 160))
        assert missing == dropped, (missing[:5], dropped[:5])
    print(f"ok  19 writer overflow: {len(dropped)} dropped blocks persisted"
          " as gaps at their exact original positions")


def test_19_recorder_memory_complete_while_journal_degrades():
    sd = native_shims.sounddevice()
    with tmpdir() as td:
        r = audio_mod.Recorder(sample_rate=16000)
        r.journal = cj.CaptureJournal(td, job_id="job-disk",
                                      sample_rate=16000)
        real = os.write

        def full(fd, data):
            raise OSError(28, "No space left on device")

        os.write = full
        try:
            r.start()
            st = sd.streams[-1]
            sent = []
            for i in range(30):
                blk = np.full((800, 1), 0.001 * (i + 1), dtype=np.float32)
                sent.append(blk[:, 0].copy())
                st.callback(blk, 800, None, None)
            deadline = time.monotonic() + 5
            while not r.journal.degraded and time.monotonic() < deadline:
                time.sleep(0.01)
            assert r.journal.degraded, "disk failure never reached writer"
        finally:
            os.write = real
        buf = r.stop()
        assert np.array_equal(buf, np.concatenate(sent)), \
            "live capture lost samples to a journal failure"
        assert buf.size == 24000
        cjs = r.stats["crash_journal"]
        assert cjs["degraded"] and cjs["finalized"] is False
        assert "journal_dropped_blocks" not in r.stats
        assert "incomplete_tail" not in r.stats, \
            "journal state reported as a live-audio discontinuity"
    print("ok  19 real Recorder on a full disk: 24000/24000 samples in"
          " memory; journal degraded; no false live discontinuity")


CHILD = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import numpy as np
from localflow.v2 import capture_journal as cj
j = cj.CaptureJournal(sys.argv[2], job_id="job-other", sample_rate=16000)
j.handoff_block(np.ones(800, dtype=np.float32))
while not (j.blk_path.exists() and j.blk_path.stat().st_size > 3200):
    time.sleep(0.01)
print("ready", flush=True)
time.sleep(60)
"""


def test_01_is_live_ownership():
    with tmpdir() as td:
        j = cj.CaptureJournal(td, job_id="job-live", sample_rate=16000)
        j.handoff_block(np.ones(800, dtype=np.float32))
        deadline = time.monotonic() + 5
        while not j.blk_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)
        assert cj.is_live(j.blk_path), "in-process writer not owning"
        j.finalize()
        assert not cj.is_live(j.blk_path), "finished writer still owns"
        child = subprocess.Popen([sys.executable, "-c", CHILD, str(ROOT),
                                  td], stdout=subprocess.PIPE, text=True)
        try:
            assert child.stdout.readline().strip() == "ready"
            other = pathlib.Path(td) / "job-job-other.blk"
            assert cj.is_live(other), "another process's writer not owning"
            child.send_signal(signal.SIGKILL)
            child.wait(5)
            assert other.exists() and not cj.is_live(other), \
                "a killed writer's file must read as residue"
        finally:
            if child.poll() is None:
                child.kill()
    print("ok  01 ownership: live writer (this/other process) owns; finished"
          " and SIGKILLed writers leave residue")


def test_02_delayed_writer_cannot_recreate():
    with tmpdir() as td:
        for variant in ("discard", "gate_refused"):
            gate, entered = threading.Event(), threading.Event()
            real = cj.CaptureJournal._open_file

            def held(self, *a, **kw):
                entered.set()
                gate.wait(10)
                return real(self, *a, **kw)

            refused = []

            def deleted_gate(opener):
                refused.append(1)
                return (False, None)

            cj.CaptureJournal._open_file = held
            try:
                j = cj.CaptureJournal(
                    td, job_id=f"job-{variant}", sample_rate=16000,
                    open_gate=deleted_gate if variant == "gate_refused"
                    else None)
                j.handoff_block(np.ones(800, dtype=np.float32))
                assert entered.wait(5), "writer never reached its open"
                if variant == "discard":
                    j.close_discard(join_timeout=0.05)
                gate.set()
                j._thread.join(5)
                assert not j._thread.is_alive()
                assert not j.blk_path.exists(), f"{variant}: reappeared"
                if variant == "gate_refused":
                    assert refused and j.degraded
            finally:
                cj.CaptureJournal._open_file = real
                gate.set()
        # positive control: an unrevoked writer does create the file
        j = cj.CaptureJournal(td, job_id="job-control", sample_rate=16000)
        j.handoff_block(np.ones(800, dtype=np.float32))
        j.finalize()
        assert j.blk_path.exists() and j.finalized
    print("ok  02 delayed writer: discard and deletion-gate refusal leave no"
          " file; unrevoked control creates one")


def main():
    run([test_08_v1_integrity_matrix, test_08_v2_positions_crc_and_gaps,
         test_19_writer_overflow_persists_gap_positions,
         test_19_recorder_memory_complete_while_journal_degrades,
         test_01_is_live_ownership, test_02_delayed_writer_cannot_recreate],
        "m03 remediation journal tests")


if __name__ == "__main__":
    main()
