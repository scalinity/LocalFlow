"""EV-04 / M03: durable capture journal (Spec S06/S09, M03-AC03).

Synthetic blocks exercise: bit-exact round trip, crash reconstruction with
incomplete-tail labeling, disk-pressure degradation that never discards the
active recording's in-memory path, a bounded writer queue under flood, and
callback purity (handoff does no disk work).

Run: .venv/bin/python tests/v2/lifecycle/test_capture_journal.py
"""

import pathlib
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import capture_journal as cj  # noqa: E402


class Rec:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, kw))


def blocks(n, samples_per_block=800):
    rng = np.random.default_rng(11)
    return [(rng.random(samples_per_block).astype(np.float32) - 0.5)
            for _ in range(n)]


def test_round_trip_bit_exact():
    with tempfile.TemporaryDirectory() as td:
        rec = Rec()
        j = cj.CaptureJournal(pathlib.Path(td), job_id="job-rt",
                              family_id="fam-rt", sample_rate=16000,
                              emit=rec)
        data = blocks(12)
        for b in data:
            assert j.handoff_block(b) is True
        stats = j.finalize()
        assert stats["finalized"] and stats["blocks_written"] == 12
        assert stats["queue_dropped"] == 0
        out = cj.reconstruct(j.blk_path)
        expected = np.concatenate(data)
        assert out.samples.dtype == np.float32
        assert np.array_equal(out.samples, expected), "bit-exact recovery"
        assert out.incomplete_tail is False
        assert out.header["job_id"] == "job-rt"
        assert out.header["sample_rate"] == 16000
    print("ok  journal round trip: float32 samples bit-exact")


def test_crash_reconstruction_incomplete_tail():
    """M03-AC03: every complete block survives a crash; a torn tail is
    discarded and labeled, at a block boundary and mid-payload."""
    with tempfile.TemporaryDirectory() as td:
        rec = Rec()
        j = cj.CaptureJournal(pathlib.Path(td), job_id="job-cr",
                              family_id="fam-cr", sample_rate=16000,
                              emit=rec)
        data = blocks(6)
        for b in data:
            j.handoff_block(b)
        j.finalize()
        raw_full = j.blk_path.read_bytes()
        # Simulate the crash: no finalize record, tail cut mid-payload.
        header_end = raw_full.index(b"\n") + 1
        first_end = header_end
        # walk two complete records
        import struct
        off = header_end
        for _ in range(3):
            _magic, _seq, _frames, nbytes = struct.unpack_from("<3sIII", raw_full, off)
            off += 15 + nbytes
        torn_path = pathlib.Path(td) / "job-cr.blk"
        torn_path.write_bytes(raw_full[:off])
        torn_path.write_bytes(raw_full[:off] + raw_full[off:off + 200])
        out = cj.reconstruct(torn_path)
        assert out.complete_blocks == 3
        assert out.incomplete_tail is True
        assert out.torn_bytes > 0
        assert np.array_equal(out.samples, np.concatenate(data[:3]))
        # A crash exactly at a block boundary loses nothing complete but
        # still reads as unfinished (no finalize record).
        boundary = pathlib.Path(td) / "job-cr2.blk"
        boundary.write_bytes(raw_full[:off])
        out2 = cj.reconstruct(boundary)
        assert out2.complete_blocks == 3 and out2.samples.size == 3 * 800
        assert np.array_equal(out2.samples, np.concatenate(data[:3]))
    print("ok  crash reconstruction: complete blocks + torn tail labeled")


def test_disk_pressure_degrades_not_discards():
    """A full disk marks the journal degraded and reports it; blocks keep
    flowing through handoff (the recording's memory path is unaffected)."""
    import os
    with tempfile.TemporaryDirectory() as td:
        rec = Rec()
        j = cj.CaptureJournal(pathlib.Path(td), job_id="job-full",
                              family_id="fam", sample_rate=16000,
                              emit=rec)
        real_write = os.write

        def full_disk(fd, data):
            raise OSError(28, "No space left on device")

        os.write = full_disk
        try:
            for b in blocks(4):
                assert j.handoff_block(b) is True, \
                    "handoff must never fail on disk pressure"
            deadline = time.monotonic() + 5
            while not j.degraded and time.monotonic() < deadline:
                time.sleep(0.05)
        finally:
            os.write = real_write
        assert j.degraded
        assert any(e == "capture.journal_degraded" for e, _ in rec.events)
        # The in-memory capture path continues after the disk recovered.
        stats = j.finalize()
        assert stats["degraded"] and not stats["finalized"]
    print("ok  disk pressure: degraded + reported, capture path unaffected")


def test_bounded_queue_under_flood():
    """The writer queue has a hard bound; flooding handoff never blocks and
    drops are counted (S24: capture-writer queue stays bounded)."""
    import os
    with tempfile.TemporaryDirectory() as td:
        rec = Rec()
        j = cj.CaptureJournal(pathlib.Path(td), job_id="job-flood",
                              family_id="fam", sample_rate=16000,
                              emit=rec)
        real_write = os.write

        def slow_write(fd, data):
            time.sleep(0.004)
            return real_write(fd, data)

        os.write = slow_write
        try:
            data = blocks(2000, samples_per_block=800)
            lat = []
            for b in data:
                t0 = time.perf_counter()
                j.handoff_block(b)
                lat.append((time.perf_counter() - t0) * 1000.0)
            # Non-blocking handoff even under total backlog.
            assert max(lat) < 5.0, f"handoff blocked: max {max(lat):.3f} ms"
            with j._lock:
                qlen = len(j._queue)
            assert qlen <= cj.QUEUE_BOUND, qlen
        finally:
            os.write = real_write
        stats = j.finalize(timeout=10)
        assert stats["queue_dropped"] > 0, "flood must overflow the bound"
        assert (stats["blocks_written"] + stats["queue_dropped"]) == 2000
        assert stats["blocks_written"] <= 2000
    print("ok  bounded queue: flood drops counted, handoff never blocks")


def test_handoff_does_no_disk_work():
    """With the filesystem unusable, handoff still enqueues (the audio
    callback must stay pure; only the writer thread touches disk)."""
    import os
    with tempfile.TemporaryDirectory() as td:
        rec = Rec()
        j = cj.CaptureJournal(pathlib.Path(td), job_id="job-pure",
                              family_id="fam", sample_rate=16000,
                              emit=rec)
        real_open = os.open

        def no_open(*a, **k):
            raise OSError(5, "I/O error")

        os.open = no_open
        try:
            t0 = time.perf_counter()
            assert j.handoff_block(blocks(1)[0]) is True
            dt = (time.perf_counter() - t0) * 1000.0
            assert dt < 5.0, f"handoff touched disk? {dt:.3f} ms"
        finally:
            os.open = real_open
        deadline = time.monotonic() + 5
        while not j.degraded and time.monotonic() < deadline:
            time.sleep(0.05)
        j.finalize()
    print("ok  callback purity: handoff is enqueue-only")


def test_cancel_discards_journal():
    with tempfile.TemporaryDirectory() as td:
        rec = Rec()
        j = cj.CaptureJournal(pathlib.Path(td), job_id="job-x",
                              family_id="fam", sample_rate=16000,
                              emit=rec)
        for b in blocks(2):
            j.handoff_block(b)
        j.close_discard()
        assert not j.blk_path.exists()
        assert cj.unfinished_journals(pathlib.Path(td)) == []
    print("ok  cancelled capture: journal deleted")


def main():
    test_round_trip_bit_exact()
    test_crash_reconstruction_incomplete_tail()
    test_disk_pressure_degrades_not_discards()
    test_bounded_queue_under_flood()
    test_handoff_does_no_disk_work()
    test_cancel_discards_journal()
    print("all capture journal tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
