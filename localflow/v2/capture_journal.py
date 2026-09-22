"""Durable capture journal (Spec S06/S09, M03-AC03).

The audio callback hands fixed float32 blocks to a bounded queue drained by
one writer thread — the callback itself never touches the disk. Each
dictation journals to ``<root>/job-<job_id>.blk``:

    line 1  : header JSON + "\\n"
              {"journal_version":1,"job_id":…,"sample_rate":…,…}
    records : b"BLK" + uint32 seq + uint32 frames + uint32 bytes + payload
    finish  : finalize JSON line {"op":"finalize",…} + "\\n"

A clean release finalizes the journal; the live path keeps using the
in-memory buffer, so the journal only matters when the process dies. On the
next launch, reconstruction returns every complete block, discards the torn
tail as uncertain (incomplete-tail status), and stops at the first record
that fails its magic/length checks — never guessing past a hole.

Queue pressure: ``handoff_block`` is a non-blocking enqueue. If the writer
stalls, blocks are dropped from the *journal only* (counted, reported);
the recorder's in-memory buffer still holds them, so live dictation loses
nothing — only crash-recovery completeness degrades, honestly flagged.
Disk-full degrades the same way: capture continues from memory, the journal
is marked degraded, and an event reports it (S07: a full disk must not
silently discard an active recording).
"""

import collections
import hashlib
import json
import os
import pathlib
import queue
import struct
import threading

import numpy as np

JOURNAL_VERSION = 1
QUEUE_BOUND = 256  # 50 ms blocks → 12.8 s of writer headroom
_BLK_MAGIC = b"BLK"
_BLK_HEAD = struct.Struct("<3sIII")  # magic, seq, frames, byte length
_BLOCK_DTYPE = np.dtype("<f4")


class JournalRecovery:
    def __init__(self, header, samples, complete_blocks, torn, torn_bytes):
        self.header = header
        self.samples = samples  # float32 ndarray (possibly empty)
        self.complete_blocks = complete_blocks
        self.torn = torn  # True when the tail failed its checks
        self.torn_bytes = torn_bytes

    @property
    def incomplete_tail(self) -> bool:
        return self.torn

    def stats(self) -> dict:
        rate = self.header.get("sample_rate") or 0
        return {
            "job_id": self.header.get("job_id"),
            "family_id": self.header.get("family_id"),
            "complete_blocks": self.complete_blocks,
            "sample_count": int(self.samples.size),
            "duration_sec": (self.samples.size / rate) if rate else 0.0,
            "incomplete_tail": self.torn,
            "torn_bytes": self.torn_bytes,
        }


class CaptureJournal:
    """One dictation's crash-resilient block journal (parent-owned)."""

    def __init__(self, root, *, job_id, family_id=None, sample_rate=16000,
                 channels=1, meta=None, emit=None):
        self.root = pathlib.Path(root)
        self.job_id = job_id
        self.blk_path = self.root / f"job-{job_id}.blk"
        self.wav_path = self.root / f"job-{job_id}.wav"
        self.emit = emit or (lambda *a, **k: None)
        self.header = {
            "journal_version": JOURNAL_VERSION, "job_id": job_id,
            "family_id": family_id, "sample_rate": int(sample_rate),
            "channels": int(channels), "dtype": "float32",
            "meta": dict(meta or {}),
        }
        self.queue_dropped = 0
        self.degraded = False
        self.degrade_reason = None
        self.blocks_written = 0
        self.samples_written = 0
        self.finalized = False
        self._queue = collections.deque()
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._closing = False
        self._error = None
        self._thread = threading.Thread(
            target=self._run, name=f"journal-{job_id[:16]}", daemon=True)
        self._thread.start()

    # ---- audio-callback side (non-blocking, no disk) ---------------------

    def handoff_block(self, samples: np.ndarray) -> bool:
        """Enqueue one fixed block. Called from the real-time callback:
        never blocks, never touches the disk."""
        with self._lock:
            if self._closing or self.finalized:
                return False
            if len(self._queue) >= QUEUE_BOUND:
                self.queue_dropped += 1
                return False
            self._queue.append(samples)
            self._wake.notify()
        return True

    # ---- writer thread ---------------------------------------------------

    def _run(self):
        fd = None
        seq = 0
        rolling = hashlib.sha256()
        try:
            while True:
                with self._lock:
                    while not self._queue and not self._closing:
                        self._wake.wait(0.5)
                    if self._queue:
                        block = self._queue.popleft()
                    elif self._closing:
                        break
                    else:
                        continue
                if fd is None:
                    fd = self._open_file()
                seq += 1
                data = np.ascontiguousarray(block, dtype=_BLOCK_DTYPE).tobytes()
                frames = len(data) // 4
                rec = _BLK_HEAD.pack(_BLK_MAGIC, seq, frames, len(data)) + data
                # os.write may write partially (pipes aside, regular files
                # rarely do, but the contract is a complete record or a
                # torn one — never a silent short write).
                view = memoryview(rec)
                while view:
                    n = os.write(fd, view)
                    view = view[n:]
                self.blocks_written += 1
                self.samples_written += frames
                rolling.update(data)
        except OSError as e:
            # Disk full / device gone: capture continues from memory; only
            # crash recovery degrades. Reported, never raised.
            self._degrade(f"journal write failed ({type(e).__name__}"
                          + (f" errno {e.errno}" if e.errno else "") + ")")
        except BaseException as e:  # never kill the process from the journal
            self._error = e
            self._degrade(f"journal writer failed ({type(e).__name__})")
        finally:
            if fd is not None:
                try:
                    if not self.degraded and self._closing and \
                            not self._queue:
                        os.write(fd, json.dumps({
                            "op": "finalize",
                            "blocks": self.blocks_written,
                            "samples": self.samples_written,
                            "sha256": rolling.hexdigest(),
                        }).encode("utf-8") + b"\n")
                        self.finalized = True
                    os.close(fd)
                except OSError as e:
                    self._degrade(f"journal finalize failed"
                                  f" ({type(e).__name__})")

    def _open_file(self):
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        fd = os.open(self.blk_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND,
                     0o600)
        size = os.fstat(fd).st_size
        if size == 0:
            os.write(fd, json.dumps(self.header).encode("utf-8") + b"\n")
        return fd

    def _degrade(self, reason):
        first = not self.degraded
        self.degraded = True
        self.degrade_reason = reason
        if first:
            self.emit("capture.journal_degraded", level="WARNING",
                      job_id=self.job_id, reason_code="journal_write_failed",
                      detail=reason + " — capture continues from memory;"
                      " crash recovery for this dictation is incomplete")

    # ---- lifecycle ---------------------------------------------------------

    def finalize(self, timeout: float = 5.0) -> dict:
        """Drain and close after a clean release. Bounded: if the writer
        cannot finish within ``timeout`` the caller proceeds with the
        in-memory buffer and the writer finishes on its own."""
        with self._lock:
            self._closing = True
            self._wake.notify_all()
        self._thread.join(timeout=timeout)
        return self.stats()

    def close_discard(self):
        """Cancelled/too-short capture: stop writing and delete the journal."""
        with self._lock:
            self._closing = True
            self._wake.notify_all()
        self._thread.join(timeout=2.0)
        try:
            self.blk_path.unlink(missing_ok=True)
        except OSError:
            pass

    def stats(self) -> dict:
        return {
            "job_id": self.job_id,
            "blocks_written": self.blocks_written,
            "samples_written": self.samples_written,
            "queue_dropped": self.queue_dropped,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
            "finalized": self.finalized,
            "path": str(self.blk_path),
        }


# ---- crash reconstruction -------------------------------------------------

def reconstruct(blk_path: pathlib.Path) -> JournalRecovery:
    """Recover every complete block; the first record failing its checks is
    the incomplete tail (M03-AC03). Works for finalized journals too (a
    crash after release, before the job resolved)."""
    raw = pathlib.Path(blk_path).read_bytes()
    header, offset = {}, 0
    nl = raw.find(b"\n")
    if nl < 0:
        return JournalRecovery(header, np.zeros(0, dtype=np.float32), 0,
                               True, len(raw))
    try:
        header = json.loads(raw[:nl].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JournalRecovery({}, np.zeros(0, dtype=np.float32), 0, True,
                               len(raw))
    offset = nl + 1
    chunks = []
    blocks = 0
    torn = False
    torn_bytes = 0
    head_size = _BLK_HEAD.size
    while offset < len(raw):
        if raw[offset:offset + 1] == b"{":
            break  # finalize record: journal was closed cleanly
        if len(raw) - offset < head_size:
            torn, torn_bytes = True, len(raw) - offset
            break
        magic, _seq, frames, nbytes = _BLK_HEAD.unpack_from(raw, offset)
        if magic != _BLK_MAGIC or nbytes != frames * 4:
            torn, torn_bytes = True, len(raw) - offset
            break
        start = offset + head_size
        if len(raw) - start < nbytes:
            torn, torn_bytes = True, len(raw) - offset
            break
        chunks.append(np.frombuffer(raw, dtype=_BLOCK_DTYPE, count=frames,
                                    offset=start))
        blocks += 1
        offset = start + nbytes
    samples = (np.concatenate(chunks) if chunks
               else np.zeros(0, dtype=np.float32))
    return JournalRecovery(header, samples, blocks, torn, torn_bytes)


def unfinished_journals(root) -> list:
    """Journal files present at startup: crashed captures (no finalize
    record) or unresolved jobs. Both are recovery candidates."""
    root = pathlib.Path(root)
    if not root.is_dir():
        return []
    return sorted(root.glob("job-*.blk"))
