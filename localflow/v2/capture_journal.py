"""Durable capture journal (Spec S06/S09, M03-AC03).

The audio callback hands fixed float32 blocks to a bounded queue drained by
one writer thread — the callback itself never touches the disk. Each
dictation journals to ``<root>/job-<job_id>.blk``:

    line 1  : header JSON + "\\n"
              {"journal_version":2,"job_id":…,"sample_rate":…,"boot_id":…}
    records : b"BLK" + <u32 seq> <u32 frames> <u32 record_bytes>
              + <u64 start_sample> <u32 crc32(payload)> + float32 payload
              (record_bytes = 12 + 4 * frames; seq counts PERSISTED records
              1, 2, 3 … with no holes)
    finish  : finalize JSON line {"op":"finalize","blocks","samples",
              "sha256","offered_samples","dropped_blocks",…} + "\\n"

``start_sample`` is the block's position in the capture timeline — every
block the callback OFFERED counts, persisted or dropped — so a queue drop
survives a crash as an explicit gap at its original position instead of
silently compressed audio (M03-AUDIT-08). Journal version 1 (no positions,
no per-block checksum) is still read; its positions and unfinalized
integrity are reported as unknown, never assumed.

A clean release finalizes the journal; the live path keeps using the
in-memory buffer, so the journal only matters when the process dies.
Reconstruction returns the verified prefix and one explicit status:
``finalized_verified`` (footer counts + SHA-256 match), ``unfinalized``
(clean EOF at a record boundary — finalization unknown, not assumed),
``torn_tail`` (EOF inside a record), ``torn_footer`` (EOF inside the
finalize line), or ``corrupt`` (sequence break, bad CRC/magic/length,
footer mismatch, bytes after the footer) — never resynchronizing past a
bad record and splicing unrelated samples.

Ownership (M03-AUDIT-01/02): the writer holds an exclusive ``flock`` on
its file for as long as it may append, so a recovery scan in any process
can tell a live journal from crash residue; file creation can be gated
through the store's deletion barrier; and a discard revokes the writer's
creation authority — a writer delayed past ``close_discard`` removes any
file it then creates, so a cancelled journal can never reappear.

Queue pressure: ``handoff_block`` is a non-blocking enqueue. If the writer
stalls, blocks are dropped from the *journal only* (counted, positioned);
the recorder's in-memory buffer still holds them, so live dictation loses
nothing — only crash-recovery completeness degrades, honestly flagged.
Disk-full degrades the same way: capture continues from memory, the journal
is marked degraded, and an event reports it (S07: a full disk must not
silently discard an active recording). Durability here is process-crash
persistence (bytes handed to the OS by ``os.write``), not a per-block
power-loss guarantee: no fsync is issued per block (M03-AUDIT-27).
"""

import collections
import hashlib
import json
import os
import pathlib
import struct
import threading
import zlib

import numpy as np

try:
    import fcntl
except ImportError:  # pragma: no cover — non-POSIX
    fcntl = None

JOURNAL_VERSION = 2
QUEUE_BOUND = 256  # 50 ms blocks → 12.8 s of writer headroom
MAX_BLOCK_FRAMES = 1 << 20
_BLK_MAGIC = b"BLK"
_BLK_HEAD = struct.Struct("<3sIII")  # magic, seq, frames, record bytes
_BLK_EXT = struct.Struct("<QI")      # v2: start_sample, crc32(payload)
_BLOCK_DTYPE = np.dtype("<f4")

STATUS_VERIFIED = "finalized_verified"
STATUS_UNFINALIZED = "unfinalized"
STATUS_TORN_TAIL = "torn_tail"
STATUS_TORN_FOOTER = "torn_footer"
STATUS_CORRUPT = "corrupt"
STATUS_NO_HEADER = "no_header"


class JournalRecovery:
    def __init__(self, header, samples, complete_blocks, torn, torn_bytes,
                 *, status=STATUS_UNFINALIZED, corrupt_reason=None,
                 version=None, segments=None, gaps=None, footer=None,
                 integrity="unverified"):
        self.header = header
        self.samples = samples  # float32 ndarray (possibly empty)
        self.complete_blocks = complete_blocks
        self.torn = torn  # True when EOF cut a record (the torn tail)
        self.torn_bytes = torn_bytes  # bytes after the verified prefix
        self.status = status
        self.corrupt_reason = corrupt_reason
        self.version = version
        # v2: [[recovered_offset, start_sample, frames], …]; None = unknown
        self.segments = segments
        # v2: [{"at_sample", "missing_samples", "recovered_offset"}, …]
        self.gaps = gaps
        self.footer = footer
        # "crc32_per_block" (v2), "footer_sha256" (v1 finalized) or
        # "unverified" (v1 without a verified footer)
        self.integrity = integrity

    @property
    def corrupt(self) -> bool:
        return self.status == STATUS_CORRUPT

    @property
    def finalized(self):
        """True: footer verified; None: unknown (never assumed True)."""
        return True if self.status == STATUS_VERIFIED else None

    @property
    def incomplete_tail(self) -> bool:
        """Samples after the recovered prefix may be missing."""
        return self.status in (STATUS_TORN_TAIL, STATUS_CORRUPT,
                               STATUS_NO_HEADER)

    @property
    def positions_known(self) -> bool:
        return self.segments is not None

    def stats(self) -> dict:
        rate = self.header.get("sample_rate") or 0
        return {
            "job_id": self.header.get("job_id"),
            "family_id": self.header.get("family_id"),
            "complete_blocks": self.complete_blocks,
            "sample_count": int(self.samples.size),
            "duration_sec": (self.samples.size / rate) if rate else 0.0,
            "incomplete_tail": self.incomplete_tail,
            "torn_bytes": self.torn_bytes,
            "status": self.status,
            "corrupt_reason": self.corrupt_reason,
            "journal_version": self.version,
            "integrity": self.integrity,
            "positions_known": self.positions_known,
            "gaps": list(self.gaps or []),
        }


class JournalDiscarded(Exception):
    pass


class CaptureJournal:
    """One dictation's crash-resilient block journal (parent-owned)."""

    def __init__(self, root, *, job_id, family_id=None, sample_rate=16000,
                 channels=1, meta=None, emit=None, boot_id=None,
                 open_gate=None):
        self.root = pathlib.Path(root)
        self.job_id = job_id
        self.blk_path = self.root / f"job-{job_id}.blk"
        self.wav_path = self.root / f"job-{job_id}.wav"
        self.emit = emit or (lambda *a, **k: None)
        # ``open_gate(opener) -> (allowed, fd)`` serializes the file's
        # creation with delete-everywhere (M03-AUDIT-02); None = ungated.
        self._open_gate = open_gate
        self.header = {
            "journal_version": JOURNAL_VERSION, "job_id": job_id,
            "family_id": family_id, "sample_rate": int(sample_rate),
            "channels": int(channels), "dtype": "float32",
            "boot_id": boot_id, "meta": dict(meta or {}),
        }
        self.queue_dropped = 0
        self.dropped_samples = 0
        self.offered_samples = 0
        self.degraded = False
        self.degrade_reason = None
        self.blocks_written = 0
        self.samples_written = 0
        self.finalized = False
        self.discarded = False
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
        never blocks, never touches the disk. Every offered block advances
        the capture timeline, so a dropped block leaves a positioned gap."""
        n = int(len(samples))
        with self._lock:
            if self._closing or self.finalized:
                return False
            start = self.offered_samples
            self.offered_samples += n
            if len(self._queue) >= QUEUE_BOUND:
                self.queue_dropped += 1
                self.dropped_samples += n
                return False
            self._queue.append((start, samples))
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
                    if self.discarded:
                        break
                    if self._queue:
                        start, block = self._queue.popleft()
                    elif self._closing:
                        break
                    else:
                        continue
                if fd is None:
                    fd = self._open_file()
                    if fd is None:
                        break  # discarded or deleted: nothing is created
                with self._lock:
                    if self.discarded:
                        break
                seq += 1
                data = np.ascontiguousarray(block, dtype=_BLOCK_DTYPE).tobytes()
                frames = len(data) // 4
                rec = (_BLK_HEAD.pack(_BLK_MAGIC, seq, frames,
                                      _BLK_EXT.size + len(data))
                       + _BLK_EXT.pack(start, zlib.crc32(data)) + data)
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
                    with self._lock:
                        discarded = self.discarded
                        drained = self._closing and not self._queue
                        offered = self.offered_samples
                        dropped = self.queue_dropped
                        dropped_samples = self.dropped_samples
                    if discarded:
                        self._unlink_quiet()
                    elif not self.degraded and drained:
                        os.write(fd, json.dumps({
                            "op": "finalize",
                            "blocks": self.blocks_written,
                            "samples": self.samples_written,
                            "sha256": rolling.hexdigest(),
                            "offered_samples": offered,
                            "dropped_blocks": dropped,
                            "dropped_samples": dropped_samples,
                        }).encode("utf-8") + b"\n")
                        self.finalized = True
                    os.close(fd)  # releases the owner lock last
                except OSError as e:
                    self._degrade(f"journal finalize failed"
                                  f" ({type(e).__name__})")

    def _create(self):
        """Create/open the file, take the owner lock, write the header."""
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        fd = os.open(self.blk_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND,
                     0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.fstat(fd).st_size == 0:
                os.write(fd, json.dumps(self.header).encode("utf-8") + b"\n")
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _open_file(self):
        """The writer's one creation of the journal file. Returns None when
        a discard or the deletion barrier revoked creation authority."""
        with self._lock:
            if self.discarded:
                return None
        if self._open_gate is not None:
            allowed, fd = self._open_gate(self._create)
            if not allowed:
                self._degrade("journal not created: job deleted")
                return None
        else:
            fd = self._create()
        with self._lock:
            discarded = self.discarded
        if discarded:
            # close_discard() ran while this thread was creating the file:
            # the creator removes what it created (M03-AUDIT-02, R15).
            os.close(fd)
            self._unlink_quiet()
            return None
        return fd

    def _unlink_quiet(self):
        try:
            self.blk_path.unlink(missing_ok=True)
        except OSError:
            pass

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
        in-memory buffer and the writer finishes on its own — the stats
        then say ``finalized: False`` and ``writer_alive: True`` (a
        journal-only condition; the live capture is still complete)."""
        with self._lock:
            self._closing = True
            self._wake.notify_all()
        self._thread.join(timeout=timeout)
        return self.stats()

    def close_discard(self, join_timeout: float = 0.5):
        """Cancelled/too-short/resolved capture: revoke the writer's
        authority, then delete the journal. Correct without the join: a
        writer still creating the file removes it itself."""
        with self._lock:
            self._closing = True
            self.discarded = True
            self._queue.clear()
            self._wake.notify_all()
        if join_timeout:
            self._thread.join(timeout=join_timeout)
        self._unlink_quiet()

    def stats(self) -> dict:
        return {
            "job_id": self.job_id,
            "blocks_written": self.blocks_written,
            "samples_written": self.samples_written,
            "queue_dropped": self.queue_dropped,
            "dropped_samples": self.dropped_samples,
            "offered_samples": self.offered_samples,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
            "finalized": self.finalized,
            "writer_alive": self._thread.is_alive(),
            "path": str(self.blk_path),
        }


# ---- ownership ------------------------------------------------------------

def is_live(blk_path) -> bool:
    """True while some process's writer still owns ``blk_path`` (its
    exclusive flock is held). A crashed or finished writer's lock is gone.
    Without flock support the answer is conservatively True."""
    if fcntl is None:
        return True
    try:
        fd = os.open(blk_path, os.O_RDONLY)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


# ---- crash reconstruction -------------------------------------------------

def _header_ok(header) -> bool:
    return (isinstance(header, dict)
            and header.get("journal_version") in (1, 2)
            and isinstance(header.get("sample_rate"), int)
            and header["sample_rate"] > 0
            and header.get("channels", 1) == 1
            and header.get("dtype", "float32") == "float32")


def reconstruct(blk_path: pathlib.Path) -> JournalRecovery:
    """Recover the verified prefix of a journal and classify the rest
    (M03-AC03, M03-AUDIT-08). Works for finalized journals too (a crash
    after release, before the job resolved)."""
    raw = pathlib.Path(blk_path).read_bytes()
    empty = np.zeros(0, dtype=np.float32)
    nl = raw.find(b"\n")
    if nl < 0:
        return JournalRecovery({}, empty, 0, True, len(raw),
                               status=STATUS_NO_HEADER)
    try:
        header = json.loads(raw[:nl].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        header = None
    if not _header_ok(header):
        return JournalRecovery(header if isinstance(header, dict) else {},
                               empty, 0, False, len(raw) - nl - 1,
                               status=STATUS_CORRUPT,
                               corrupt_reason="header_invalid")
    version = header["journal_version"]
    offset = nl + 1
    chunks = []
    segments = [] if version >= 2 else None
    gaps = [] if version >= 2 else None
    blocks = 0
    recovered = 0
    next_start = 0
    rolling = hashlib.sha256()
    status, reason, torn, footer = STATUS_UNFINALIZED, None, False, None
    head = _BLK_HEAD.size
    while offset < len(raw):
        if raw[offset:offset + 1] == b"{":
            end = raw.find(b"\n", offset)
            if end < 0:
                # EOF inside the finalize line: finalization unknown.
                status = STATUS_TORN_FOOTER
                break
            try:
                footer = json.loads(raw[offset:end].decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                footer = None
            if not isinstance(footer, dict) \
                    or footer.get("op") != "finalize":
                status, reason = STATUS_CORRUPT, "footer_unparsable"
                break
            if footer.get("blocks") != blocks \
                    or footer.get("samples") != recovered \
                    or footer.get("sha256") != rolling.hexdigest():
                status, reason = STATUS_CORRUPT, "footer_mismatch"
                break
            if end + 1 != len(raw):
                status, reason = STATUS_CORRUPT, "bytes_after_footer"
                offset = end + 1
                break
            status = STATUS_VERIFIED
            offset = end + 1
            break
        if len(raw) - offset < head:
            status, torn = STATUS_TORN_TAIL, True
            break
        magic, seq, frames, nbytes = _BLK_HEAD.unpack_from(raw, offset)
        ext = _BLK_EXT.size if version >= 2 else 0
        if magic != _BLK_MAGIC or not 0 < frames <= MAX_BLOCK_FRAMES \
                or nbytes != ext + frames * 4:
            status, reason = STATUS_CORRUPT, "record_invalid"
            break
        if seq != blocks + 1:
            # Reordered, duplicated or missing records are never spliced.
            status, reason = STATUS_CORRUPT, "sequence_break"
            break
        start = offset + head
        if len(raw) - start < nbytes:
            status, torn = STATUS_TORN_TAIL, True
            break
        pstart = start + ext
        payload = raw[pstart:pstart + frames * 4]
        if version >= 2:
            start_sample, crc = _BLK_EXT.unpack_from(raw, start)
            if zlib.crc32(payload) != crc:
                status, reason = STATUS_CORRUPT, "crc_mismatch"
                break
            if start_sample < next_start:
                status, reason = STATUS_CORRUPT, "position_overlap"
                break
            if start_sample > next_start:
                gaps.append({"at_sample": next_start,
                             "missing_samples": start_sample - next_start,
                             "recovered_offset": recovered})
            segments.append([recovered, start_sample, frames])
            next_start = start_sample + frames
        chunks.append(np.frombuffer(payload, dtype=_BLOCK_DTYPE).copy())
        rolling.update(payload)
        blocks += 1
        recovered += frames
        offset = start + nbytes
    if status == STATUS_VERIFIED and version >= 2:
        offered = footer.get("offered_samples")
        if isinstance(offered, int) and offered > next_start:
            gaps.append({"at_sample": next_start,
                         "missing_samples": offered - next_start,
                         "recovered_offset": recovered})
    samples = np.concatenate(chunks) if chunks else empty
    if version >= 2:
        integrity = "crc32_per_block"
    elif status == STATUS_VERIFIED:
        integrity = "footer_sha256"
    else:
        integrity = "unverified"
    return JournalRecovery(header, samples, blocks, torn,
                           len(raw) - offset if status != STATUS_VERIFIED
                           else 0,
                           status=status, corrupt_reason=reason,
                           version=version, segments=segments, gaps=gaps,
                           footer=footer, integrity=integrity)


def unfinished_journals(root) -> list:
    """Journal files present at startup: crashed captures (no finalize
    record) or unresolved jobs. Both are recovery CANDIDATES — the caller
    still establishes ownership (``is_live``) and job state."""
    root = pathlib.Path(root)
    if not root.is_dir():
        return []
    return sorted(root.glob("job-*.blk"))
