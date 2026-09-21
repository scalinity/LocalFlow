"""Dated operational event log (Spec S07, contract events.md, schema version 2).

JSON Lines under ``~/Library/Logs/LocalFlow/events-YYYY-MM-DD.jsonl`` (UTC
date in the filename, and — more importantly — in every record), with size
and UTC-day rotation, 0700/0600 permissions, a bounded priority queue and a
single writer thread. Transcript text, audio, credentials and environment
values never enter these records; content lives in the private store.

Priorities: CRITICAL (job terminal states, errors) must reach disk or raise
a visible logging-degraded state; LOW (debug) may coalesce or drop with a
counter. Emission never blocks the caller beyond a short bounded check, and
no fsync happens anywhere near the audio callback (the recorder does not
touch this module at all).
"""

import collections
import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import sys
import threading
import time

from . import ids

SCHEMA_VERSION = 2
DEFAULT_LOG_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow"
ROTATE_BYTES = 10 * 1024 * 1024  # 10 MiB
KEEP_ROLLS = 8
QUEUE_BOUND = 10000

# A second writer's fallback files (events-p<pid>-YYYY-MM-DD.jsonl...).
_OTHER_WRITER_RE = re.compile(r"^events-p\d+-")

CRITICAL, NORMAL, LOW = 0, 1, 2
_LEVEL_NAMES = {"DEBUG": LOW, "INFO": NORMAL, "WARNING": NORMAL, "ERROR": CRITICAL}


def _open_exclusive(path: pathlib.Path) -> int | None:
    """Advisory single-writer lock; None when another process holds it."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


class EventWriter:
    """Asynchronous writer for the dated V2 event stream."""

    def __init__(self, log_dir=None, *, boot_id=None, session_id=None,
                 worker_generation=1, retention_days=14,
                 cap_bytes=100 * 1024 * 1024,
                 now_fn=time.time, mono_fn=time.monotonic,
                 unresolved_jobs_fn=None, mirror_stderr=None):
        self.log_dir = pathlib.Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        self.retention_days = retention_days
        self.cap_bytes = cap_bytes
        self.now_fn = now_fn
        self.mono_fn = mono_fn
        # The app supplies a callable returning unresolved job IDs so event
        # retention keeps files that still carry recoverable metadata (S07).
        self.unresolved_jobs_fn = unresolved_jobs_fn or (lambda: set())
        self.boot_id = boot_id or ids.new_id("boot")
        self.session_id = session_id or ids.new_id("session")
        self.worker_generation = worker_generation
        self.process_id = os.getpid()
        self.dropped_low = 0
        self.dropped_normal = 0
        self.dropped_critical = 0
        self.critical_retries = 0
        self.degraded = False
        self._degrade_reason = None
        self._stderr = sys.stderr  # bound now: a stderr capture must not
        # swallow the writer's own mirror/degraded warnings
        self._mirror = self._stderr.isatty() if mirror_stderr is None else mirror_stderr
        self._base_kwargs = dict(
            boot_id=self.boot_id, session_id=self.session_id,
            process_id=self.process_id, worker_generation=self.worker_generation,
            source_revision=ids.source_revision(), pipeline_revision=ids.PIPELINE_REVISION,
        )
        self._sequence = 0
        self._seq_lock = threading.Lock()
        self._queues = [collections.deque() for _ in range(3)]
        self._spill = collections.deque()  # critical events awaiting retry
        self._qcond = threading.Condition()
        self._writing = False
        self._stop = False
        self._file = None
        self._file_name = None
        self._file_bytes = 0
        self._lock_fd = None
        self._name_prefix = "events-"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.log_dir, 0o700)
        except OSError:
            pass
        self._lock_fd = _open_exclusive(self.log_dir / "events.lock")
        if self._lock_fd is None:
            # Another LocalFlow process owns this directory. Keep this
            # process's events under a pid-prefixed name instead of
            # interleaving lines into the shared files.
            self._name_prefix = f"events-p{self.process_id}-"
            self._degrade("event directory locked by another process")
        self._thread = threading.Thread(
            target=self._run, name="localflow-v2-events", daemon=True)
        self._thread.start()

    # ---- emission ------------------------------------------------------

    def emit(self, event, level="INFO", *, job_id=None, attempt=None, stage=None,
             outcome=None, reason_code=None, detail=None, duration_ms=None,
             model_id=None, model_revision=None, config_hash=None,
             prompt_hash=None, artifact_ids=None):
        """Queue one event. Never blocks on disk; returns False when a
        non-critical event was dropped under queue pressure."""
        now = self.now_fn()  # single read: timestamp and offset agree
        rec = {
            "schema_version": SCHEMA_VERSION,
            "event_id": ids.new_id("evt"),
            "timestamp_utc": ids.now_utc_iso(now),
            "timezone": ids.local_zone_name(),
            "utc_offset_minutes": ids.utc_offset_minutes(now),
            **self._base_kwargs,
            "sequence": None,  # assigned by the writer thread
            "job_id": job_id, "attempt": attempt, "stage": stage,
            "event": event, "level": level, "outcome": outcome,
            "reason_code": reason_code, "detail": detail,
            "duration_ms": duration_ms, "queue_wait_ms": None,
            "model_id": model_id, "model_revision": model_revision,
            "config_hash": config_hash, "prompt_hash": prompt_hash,
            "artifact_ids": list(artifact_ids) if artifact_ids else None,
        }
        prio = _LEVEL_NAMES.get(level, NORMAL)
        queued_mono = self.mono_fn()
        with self._qcond:
            pending = sum(len(q) for q in self._queues) + len(self._spill)
            if pending >= QUEUE_BOUND:
                if prio == LOW:
                    self.dropped_low += 1
                    return False
                if prio == NORMAL:
                    self.dropped_normal += 1
                    self._degrade("event queue full")
                    self._qcond.notify()
                    return False
                if len(self._spill) >= QUEUE_BOUND:
                    # Even the critical retry list has a bound; beyond it,
                    # surface the loss loudly rather than grow unbounded.
                    self.dropped_critical += 1
                    self._degrade("critical spill overflow")
                    self._qcond.notify()
                    return False
                self._spill.append((rec, queued_mono))  # CRITICAL: retry
                self._qcond.notify()
                return True
            self._queues[prio].append((rec, queued_mono))
            self._qcond.notify()
        return True

    def stats(self):
        with self._qcond:
            pending = sum(len(q) for q in self._queues) + len(self._spill)
            reason = self._degrade_reason
        return {
            "pending": pending, "dropped_low": self.dropped_low,
            "dropped_normal": self.dropped_normal,
            "dropped_critical": self.dropped_critical,
            "degraded": self.degraded,
            "degrade_reason": reason, "critical_retries": self.critical_retries,
            "boot_id": self.boot_id, "session_id": self.session_id,
            "sequence": self._sequence,
        }

    def flush(self, timeout=5.0):
        """Block until everything emitted so far reached disk (or failed)."""
        deadline = self.mono_fn() + timeout
        with self._qcond:
            while (any(self._queues) or self._spill or self._writing) and not self._stop:
                if not self._qcond.wait(max(0.01, deadline - self.mono_fn())):
                    return False
        return True

    def close(self, timeout=5.0):
        self.flush(timeout)
        with self._qcond:
            self._stop = True
            self._qcond.notify_all()
        self._thread.join(timeout=timeout)
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None

    # ---- writer thread -------------------------------------------------

    def _run(self):
        last_retention = 0.0
        while True:
            item = None
            with self._qcond:
                while (not self._stop and not any(self._queues)
                       and not self._spill):
                    if self.now_fn() - last_retention >= 3600:
                        break  # idle: run the periodic retention pass
                    self._qcond.wait(0.5)
                if self._stop and not any(self._queues) and not self._spill:
                    return
                for q in self._queues:  # CRITICAL queue first
                    if q:
                        item = q.popleft()
                        break
                else:
                    if self._spill:
                        item = self._spill.popleft()
                self._writing = True
            try:
                if item is not None:
                    ok = self._write(item)
                    if not ok:
                        # Persistent write failure (e.g. disk full): retry
                        # criticals with backoff instead of spinning.
                        time.sleep(0.5)
                else:
                    last_retention = self.now_fn()
                    self.apply_retention_now()
            finally:
                with self._qcond:
                    self._writing = False
                    self._qcond.notify_all()

    def _write(self, item) -> bool:
        rec, queued_mono = item
        with self._seq_lock:
            self._sequence += 1
            rec["sequence"] = self._sequence
        # Monotonic in-process elapsed; clamped defensively so a clock
        # anomaly can never surface as a negative latency (S07).
        rec["queue_wait_ms"] = max(0.0, round((self.mono_fn() - queued_mono) * 1000.0, 3))
        line = json.dumps(rec, ensure_ascii=True, separators=(",", ":")) + "\n"
        if self._mirror:
            try:
                print(self.human_line(rec), file=self._stderr)
            except OSError:
                pass
        try:
            self._ensure_file()
            self._file.write(line)
            self._file.flush()
            self._file_bytes += len(line.encode("utf-8"))
            if self._file_bytes >= ROTATE_BYTES:
                self._rotate()
            if self.degraded:
                self._recover()
            return True
        except (OSError, ValueError) as e:
            # Disk full or a closed file after a failed rotation: a
            # recoverable degraded state, never a crash and never a silent
            # loss of the dictation flow. (A closed file raises ValueError,
            # which must not kill the writer thread.)
            self._degrade(f"event write failed ({type(e).__name__}"
                          + (f" errno {e.errno}" if isinstance(e, OSError)
                             else "") + ")")
            if _LEVEL_NAMES.get(rec.get("level"), NORMAL) == CRITICAL:
                self.critical_retries += 1
                with self._qcond:
                    self._spill.append((rec, queued_mono))  # retried by _run
            else:
                self.dropped_normal += 1
            return False

    def _ensure_file(self):
        stamp = dt.datetime.fromtimestamp(
            self.now_fn(), tz=dt.timezone.utc).strftime("%Y-%m-%d")
        name = f"{self._name_prefix}{stamp}.jsonl"
        # `_file.closed` matters: a failed rotation can leave a closed
        # handle that must be reopened, not written to.
        if self._file is None or self._file.closed or self._file_name != name:
            if self._file is not None and not self._file.closed:
                self._file.close()
            # UTC-day boundary: the previous day's file simply stays as-is.
            self._file_name = name
            path = self.log_dir / name
            existed = path.exists()
            if existed:
                self._file = open(path, "a", encoding="utf-8")
                self._file_bytes = path.stat().st_size
            else:
                fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND,
                             0o600)
                self._file = os.fdopen(fd, "a", encoding="utf-8")
                self._file_bytes = 0
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            self._apply_retention()

    def _rotate(self):
        self._file.close()
        path = self.log_dir / self._file_name
        # Allocate above every existing roll so suffix order always matches
        # age; reusing a freed low number would make the newest roll look
        # oldest to the pruner below.
        existing = [int(p.name.rsplit(".", 1)[-1])
                    for p in self.log_dir.glob(f"{self._file_name}.*")
                    if p.name.rsplit(".", 1)[-1].isdigit()]
        suffix = (max(existing) + 1) if existing else 1
        os.replace(path, self.log_dir / f"{self._file_name}.{suffix}")
        rolls = sorted(
            (p for p in self.log_dir.glob(f"{self._file_name}.*")
             if p.name.rsplit(".", 1)[-1].isdigit()),
            key=lambda p: int(p.name.rsplit(".", 1)[-1]))
        for extra in rolls[:-KEEP_ROLLS]:
            extra.unlink(missing_ok=True)
        self._file = None  # reopened by _ensure_file on the next write
        self._file_bytes = 0

    def apply_retention_now(self):
        """Run age/cap pruning immediately (also called hourly by the
        writer thread and whenever the active file (re)opens)."""
        if self._file_name is None:
            return
        try:
            self._apply_retention()
        except Exception:
            pass

    def _apply_retention(self):
        """Age and cap pruning; never touches the file being written, keeps
        any file that still mentions an unresolved job (S07), and never
        manages another writer's pid-prefixed files (the fallback path a
        second LocalFlow process uses for its own active file)."""
        try:
            candidates = sorted(
                (p for p in self.log_dir.glob(f"{self._name_prefix}*.jsonl*")
                 if p.name != self._file_name
                 and not _OTHER_WRITER_RE.match(p.name)),
                key=lambda p: p.stat().st_mtime)  # oldest first
        except OSError:
            return
        if not candidates:
            return
        cutoff = self.now_fn() - self.retention_days * 86400
        unresolved = None
        try:
            total = sum(p.stat().st_size for p in candidates)
        except OSError:
            return
        for p in candidates:
            try:
                if p.stat().st_mtime > cutoff and total <= self.cap_bytes:
                    continue
                if unresolved is None:
                    unresolved = set(self.unresolved_jobs_fn())
                if unresolved:
                    text = p.read_text(encoding="utf-8", errors="replace")
                    if any(j in text for j in unresolved):
                        continue  # crash/recovery metadata stays
                total -= p.stat().st_size
                p.unlink(missing_ok=True)
            except OSError:
                continue

    # ---- degraded-state handling ----------------------------------------

    def _degrade(self, reason):
        first = not self.degraded
        self.degraded = True
        self._degrade_reason = reason
        if first:
            self._warn_stderr(
                f"[localflow] logging degraded: {reason} — events are being"
                " retried; dictation is unaffected")

    def _recover(self):
        self.degraded = False
        self._degrade_reason = None

    # _degrade/_recover are called with self._qcond held (from emit) and
    # without it (from the writer thread); both only touch plain attributes.

    def _warn_stderr(self, msg):
        try:
            print(msg, file=self._stderr, flush=True)
        except OSError:
            pass

    @staticmethod
    def human_line(rec, utc: bool = False) -> str:
        """Human view per S07: wall time (local by default, UTC on request
        — display choice never changes the stored instant), level,
        correlation, reason."""
        ts = rec.get("timestamp_utc") or ""
        try:
            t = dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=dt.timezone.utc)
            shown = t if utc else t.astimezone()
            stamp = shown.strftime("%Y-%m-%d %H:%M:%S.") + \
                f"{shown.microsecond // 1000:03d}"
            if utc:
                stamp += " +00:00"
            else:
                stamp += " " + shown.strftime("%z")[:3] + ":" + \
                    shown.strftime("%z")[3:]
        except (ValueError, TypeError):
            stamp = ts
        parts = [stamp, str(rec.get("level") or "INFO")]
        if rec.get("job_id"):
            parts.append(f"job={str(rec['job_id'])[:12]}")
        if rec.get("attempt"):
            parts.append(f"attempt={rec['attempt']}")
        if rec.get("stage"):
            parts.append(str(rec["stage"]))
        desc = str(rec.get("outcome") or "")
        if rec.get("reason_code"):
            desc += f": {rec['reason_code']}" if desc else str(rec["reason_code"])
        if desc:
            parts.append(desc)
        elif rec.get("event"):
            parts.append(str(rec["event"]))
        if rec.get("duration_ms") is not None:
            parts.append(f"({rec['duration_ms']} ms)")
        return " ".join(parts)


class _StderrCapture:
    """Bounded sink for third-party stderr (tqdm, download progress): keeps
    the last bytes in memory so they can never interleave with a job event,
    and reports only sizes/flags — never content — as a diagnostic record."""

    LIMIT = 64 * 1024

    def __init__(self):
        self.chunks = []
        self.total = 0
        self.truncated = False

    def write(self, s):
        try:
            self.total += len(s)
            self.chunks.append(s)
            buf = "".join(self.chunks)
            if len(buf) > self.LIMIT:
                self.chunks = [buf[-self.LIMIT:]]
                self.truncated = True
        except Exception:
            pass
        return len(s)

    def flush(self):
        pass


class capture_stderr:
    """Context manager routing third-party stderr into a separate bounded
    diagnostic record (Spec S07). Python-level capture: tqdm and huggingface
    progress write via sys.stderr and are caught; the writer's own mirror
    and degraded warnings use the stderr bound at init and pass through."""

    def __init__(self, writer):
        self.writer = writer

    def __enter__(self):
        self._saved = sys.stderr
        self._sink = _StderrCapture()
        sys.stderr = self._sink
        return self._sink

    def __exit__(self, exc_type, exc, tb):
        sys.stderr = self._saved
        if self._sink.total:
            self.writer.emit(
                "third_party.stderr", level="DEBUG",
                reason_code="coalesced",
                detail=f"bytes={self._sink.total}"
                       f"{' truncated' if self._sink.truncated else ''}")
        return False
