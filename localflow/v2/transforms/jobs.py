"""Bounded native background jobs with durable, sequenced progress."""

from __future__ import annotations

import json
import queue
import threading
import time

from .. import ids
from .conversations import encode, submit


class Cancelled(Exception):
    pass


class JobContext:
    def __init__(self, owner, job_id):
        self.owner, self.job_id = owner, job_id
        self.deadline = time.monotonic() + owner.timeout_seconds
        self.validators = []

    def cancelled(self):
        return (self.owner._closed or self.job_id in self.owner._cancelled
                or time.monotonic() > self.deadline)

    def check(self):
        if self.owner._closed or self.job_id in self.owner._cancelled:
            raise Cancelled()
        if time.monotonic() > self.deadline:
            raise ValueError("job_timeout")

    def progress(self, phase):
        with self.owner._lock:
            self.check()
            self.owner._update(self.job_id, status="running", phase=phase)

    def publish(self, operation):
        # Cancellation and publication serialize on the same lock. The
        # operation must still revalidate source eligibility on Store's writer.
        with self.owner._lock:
            self.check()
            return operation()


class IntelligenceJobs:
    def __init__(self, store, *, max_pending=24, timeout_seconds=180,
                 background_allowed=lambda: True):
        self.store = store
        self.timeout_seconds = timeout_seconds
        self.background_allowed = background_allowed
        self._queue = queue.PriorityQueue(maxsize=max_pending)
        self._lock = threading.RLock()
        self._cancelled = set()
        self._closed = False
        self._counter = 0
        # Requests admitted before a process exit are never replayed: the
        # provider may already have billed them.
        submit(store, lambda db: db.execute(
            "UPDATE intelligence_jobs SET status='failed',phase='interrupted',"
            "error='interrupted',updated_at=? WHERE status IN ('pending','running')",
            (ids.now_utc_iso(),)))
        self._thread = threading.Thread(target=self._run,
                                        name="localflow-intelligence", daemon=True)
        self._thread.start()

    def _update(self, job_id, *, status, phase, result=None, error=None, validate=None):
        def op(db):
            if validate is not None and not validate(db):
                raise ValueError("context_revoked")
            row = db.execute("SELECT sequence,events_json FROM intelligence_jobs"
                             " WHERE job_id=?", (job_id,)).fetchone()
            seq = row[0] + 1
            events = json.loads(row[1])
            events.append({"sequence": seq, "status": status, "phase": phase})
            db.execute("UPDATE intelligence_jobs SET status=?,phase=?,sequence=?,"
                       "events_json=?,result_json=?,error=?,updated_at=?"
                       " WHERE job_id=?", (status, phase, seq, encode(events[-64:]),
                       encode(result) if result is not None else None, error,
                       ids.now_utc_iso(), job_id))
        submit(self.store, op)

    def start(self, kind, work, *, target_id=None, manifest=None, priority=1):
        with self._lock:
            if self._closed:
                raise ValueError("intelligence_closed")
            if self._queue.full():
                raise ValueError("job_queue_full")
            job_id = ids.new_id("ijob")
            now = ids.now_utc_iso()
            submit(self.store, lambda db: db.execute(
                "INSERT INTO intelligence_jobs VALUES(?,?,?,'pending','queued',"
                "1,?,?,NULL,NULL,?,?)", (job_id, kind, target_id,
                encode(manifest or {}), encode([{"sequence": 1,
                "status": "pending", "phase": "queued"}]), now, now)))
            self._counter += 1
            self._queue.put_nowait((priority, self._counter, job_id, work))
            return {"job_id": job_id, "status": "pending"}

    def read(self, job_id, after_sequence=0):
        def op(db):
            row = db.execute("SELECT status,phase,sequence,events_json,result_json,"
                             "error FROM intelligence_jobs WHERE job_id=?",
                             (job_id,)).fetchone()
            if row is None:
                raise ValueError("job_not_found")
            return {"job_id": job_id, "status": row[0], "phase": row[1],
                    "sequence": row[2], "events": [e for e in json.loads(row[3])
                    if e["sequence"] > after_sequence],
                    "result": json.loads(row[4]) if row[4] else None,
                    "error": row[5]}
        return submit(self.store, op)

    def cancel(self, job_id):
        with self._lock:
            state = self.read(job_id)
            if state["status"] in ("pending", "running"):
                self._cancelled.add(job_id)
                self._update(job_id, status="cancelled", phase="cancelled")
            return self.read(job_id)

    def cancel_target(self, target_id):
        jobs = submit(self.store, lambda db: [r[0] for r in db.execute(
            "SELECT job_id FROM intelligence_jobs WHERE target_id=?"
            " AND status IN ('pending','running')", (target_id,))])
        for job_id in jobs:
            self.cancel(job_id)

    def _run(self):
        while not self._closed:
            try:
                priority, sequence, job_id, work = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            ctx = JobContext(self, job_id)
            try:
                ctx.check()
                if priority >= 10 and not self.background_allowed():
                    self._queue.put_nowait((priority, sequence, job_id, work))
                    threading.Event().wait(0.1)
                    continue
                ctx.progress("starting")
                result = work(ctx)
                with self._lock:
                    ctx.check()
                    self._update(job_id, status="succeeded", phase="complete",
                                 result=result,
                                 validate=lambda db: all(v(db) for v in ctx.validators))
            except Cancelled:
                pass  # cancel() already publishes the terminal event
            except Exception as exc:
                with self._lock:
                    if job_id not in self._cancelled and not self._closed:
                        # Exceptions can contain private provider/source text.
                        reason = (str(exc) if isinstance(exc, ValueError)
                                  else type(exc).__name__)
                        self._update(job_id, status="failed", phase="failed",
                                     error=reason if reason.isidentifier()
                                     else type(exc).__name__)
            finally:
                self._queue.task_done()
                self._cancelled.discard(job_id)

    def close(self):
        with self._lock:
            if self._closed:
                return
            jobs = submit(self.store, lambda db: [r[0] for r in db.execute(
                "SELECT job_id FROM intelligence_jobs WHERE status IN"
                " ('pending','running')")])
            for job_id in jobs:
                self.cancel(job_id)
            self._closed = True
