"""Worker supervision: spawn, readiness, faults, one-retry, stale discard.

The supervisor owns the model-worker subprocess described in
``localflow/v2/worker.py`` (Spec S06/S09, M03). Design invariants:

* **Fresh process, never a fork.** The parent (this process) holds no MLX
  state; every worker is a ``subprocess.Popen`` of a clean interpreter.
* **Generation + attempt reject stale results (M03-AC02).** Each worker
  process gets a new ``generation``; each request echoes the job's
  ``attempt``. A pending request records its immutable expected identity
  (generation, job, attempt, result kind) and resolves only from a frame
  of ITS generation that matches it; anything else is discarded with an
  event, and only the parent's coordinator can act on a result at all.
* **Generation-owned pendings (M03-AUDIT-03).** A reader — including its
  ``finally`` — resolves only the requests its own process owned; an old
  reader can never fail a newer generation's request.
* **One lifecycle authority (M03-AUDIT-04).** Spawn, the automatic
  retry's kill+respawn, manual restart and shutdown all run under one
  re-entrant lifecycle lock; ``shutdown`` closes admission permanently
  first, so nothing spawns, retries or accepts a request afterwards.
* **One automatic retry (M03-AC01).** A FATAL stage failure (runtime
  fault, pipe death, timeout, identity violation) kills the damaged
  worker, spawns a fresh one, waits for the needed engine, and retries the
  stage once with ``attempt + 1``. A second fatal failure retires that
  generation too and raises ``WorkerFailure`` carrying the attempt that
  actually executed (M03-AUDIT-05/06). Non-fatal refusals (bad input,
  engine not ready, closed, revoked) never kill, retry or count a death.
* **Circuit breaker.** Three consecutive worker deaths with no successful
  stage trip the supervisor into ``failed``; further automatic work fails
  fast (audio preserved by the caller). A manual ``restart()`` re-arms it.
* **Serialized GPU.** One request is in flight at a time; ordinary dictation
  stages queue behind each other (S06).

The worker cannot request insertion — the protocol has no such message, and
unknown worker→parent messages are ignored.
"""

import json
import os
import re
import subprocess
import sys
import threading

from . import ids

PROTOCOL_VERSION = 1
BREAKER_LIMIT = 3  # consecutive deaths with zero successful stages
MAX_FRAME = 64 * 1024 * 1024
STDERR_TAIL_BYTES = 16 * 1024  # per generation, bytes (not lines)
STDERR_KEEP_GENERATIONS = 2

_CODE = re.compile(r"^[a-z0-9_.:-]{1,80}\Z")
_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,63}\Z")
_ENGINE_STATES = {"not_started", "loading", "warming", "ready", "failed"}
_RESULT_KIND = {"transcribe": "asr", "clean": "clean",
                "transform": "transform"}
# Worker fault classes that do not indicate a damaged process: the request
# is refused as-is — no kill, no respawn, no retry, no death counted.
_NONFATAL_CLASSES = {"input", "engine", "protocol", "closed", "revoked"}


def safe_code(value, default="unspecified") -> str:
    """Reason codes are controlled tokens, never free text (S07)."""
    return value if isinstance(value, str) and _CODE.match(value) \
        else default


def safe_type(value):
    return value if isinstance(value, str) and _TYPE.match(value) \
        else None


class WorkerFailure(Exception):
    """A stage failed after its one automatic retry (or could not start).

    ``attempt``/``generation`` name the LAST execution actually admitted
    to a worker for this call (None when nothing was sent); ``retried``
    says an automatic retry was admitted; ``fatal`` says the failure
    retired a worker generation (vs. a refusal that left it healthy)."""

    def __init__(self, reason_code, stage=None, detail=None, *,
                 fatal=True, attempt=None, generation=None, retried=False):
        reason_code = safe_code(reason_code, "worker_fault")
        detail = safe_type(detail)
        super().__init__(f"{stage or 'worker'}: {reason_code}"
                         + (f" ({detail})" if detail else ""))
        self.reason_code = reason_code
        self.stage = stage
        self.detail = detail
        self.fatal = fatal
        self.attempt = attempt
        self.generation = generation
        self.retried = retried


class _Pending:
    """One live request and its immutable expected response identity."""

    __slots__ = ("req_id", "op", "kind", "job_id", "attempt", "generation",
                 "event", "msg")

    def __init__(self, req_id=None, *, op=None, job_id=None, attempt=None,
                 generation=None):
        self.req_id = req_id
        self.op = op
        self.kind = _RESULT_KIND.get(op)
        self.job_id = job_id
        self.attempt = attempt
        self.generation = generation
        self.event = threading.Event()
        self.msg = None


class _StderrTail:
    """Byte-bounded tail of one generation's stderr (raw bytes stay in
    memory for local debugging and never enter the event stream)."""

    def __init__(self, limit=STDERR_TAIL_BYTES):
        self.limit = limit
        self.total = 0
        self._buf = bytearray()
        self._lock = threading.Lock()

    def feed(self, chunk):
        if not chunk:
            return
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", "replace")
        with self._lock:
            self.total += len(chunk)
            self._buf += chunk[-self.limit:]
            if len(self._buf) > self.limit:
                del self._buf[:len(self._buf) - self.limit]

    def size(self) -> int:
        with self._lock:
            return len(self._buf)

    def digest(self) -> str:
        with self._lock:
            data = bytes(self._buf)
            total = self.total
        lines = [ln for ln in data.split(b"\n") if ln.strip()]
        return (f"stderr_lines={len(lines)} bytes~={total}"
                f" traceback={'yes' if b'Traceback' in data else 'no'}")


class WorkerSupervisor:
    def __init__(self, *, audio_root, asr_model, cleanup_mode="off",
                 cleanup_model=None, cleanup_implementation="v2",
                 emit=None, on_engine=None,
                 worker_cmd=None, spawn_env=None, request_timeout=600.0,
                 ready_timeout=600.0, hello_timeout=15.0):
        self.audio_root = str(audio_root)
        self.asr_model = asr_model
        self.cleanup_mode = cleanup_mode
        self.cleanup_model = cleanup_model
        # M07: which cleanup implementation the worker loads — "v2"
        # (faithful cleanup, Spec S13–S14) or "v1" (the TranscriptCleaner
        # control kept for the ablation and as selectable fallback).
        self.cleanup_implementation = cleanup_implementation
        self.emit = emit or (lambda *a, **k: None)
        self.on_engine = on_engine or (lambda engine, state, info: None)
        self.worker_cmd = worker_cmd or [sys.executable, "-m",
                                         "localflow.v2.worker"]
        self.spawn_env = dict(spawn_env or {})
        self.request_timeout = request_timeout
        self.ready_timeout = ready_timeout
        self.hello_timeout = hello_timeout
        self.generation = 0
        # Engine states per S09: not_started/loading/warming/ready/failed
        # (degraded is supervisor-level: a fault happened, worker rebuilt).
        self.engine_state = {"asr": "not_started", "cleanup": "not_started"}
        self.supervisor_state = "idle"  # idle|running|degraded|failed|closed
        self._proc = None
        self._hello = threading.Event()
        self._engine_events = {"asr": threading.Event(),
                               "cleanup": threading.Event()}
        self._pending = {}
        self._send_lock = threading.Lock()
        self._gpu_lock = threading.Lock()  # one in-flight model request (S06)
        # The ONE lifecycle authority (M03-AUDIT-04): spawn, the retry's
        # kill+respawn, restart, retirement and shutdown. Re-entrant so a
        # death recorded inside a spawn can retire the process it owns.
        # Order: lifecycle lock → state lock, never the reverse.
        self._spawn_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._closed = False
        self._consecutive_deaths = 0
        self._stderr_tails = {}
        self._readers = {}
        self._finalized = set()  # generations whose reader has finished
        # Jobs whose authority was revoked (cancel / delete-everywhere):
        # a fatal failure of theirs retires the generation but is never
        # retried (M03-AUDIT-02).
        self._revoked = {}
        os.makedirs(self.audio_root, exist_ok=True)
        try:
            os.chmod(self.audio_root, 0o700)
        except OSError:
            pass

    @property
    def closed(self) -> bool:
        with self._state_lock:
            return self._closed

    # ---- process lifecycle ------------------------------------------------

    def _spawn(self, defer_cleanup=False):
        """Start a fresh worker process (never a fork of Metal state).
        Caller holds the lifecycle lock."""
        with self._spawn_lock:
            with self._state_lock:
                if self._closed:
                    raise WorkerFailure("supervisor_closed", stage="spawn",
                                        fatal=False)
                self.generation += 1
                generation = self.generation
                self.engine_state = {"asr": "not_started",
                                     "cleanup": "not_started"}
            env = dict(os.environ)
            env.update(self.spawn_env)
            # No unexpected downloads during dictation (S09): the worker
            # runs offline; a missing cache fails loudly with an
            # install/repair hint. Forced (not setdefault) so an inherited
            # HF_HUB_OFFLINE=0 from the launching shell cannot defeat it.
            env["HF_HUB_OFFLINE"] = "1"
            env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            env.setdefault("PYTHONPATH", os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            self._hello.clear()
            for evt in self._engine_events.values():
                evt.clear()
            # A new process starts with its own byte-bounded stderr tail;
            # an old generation's drainer can never write into it.
            self._stderr_tails[generation] = _StderrTail()
            for old in sorted(self._stderr_tails)[:-STDERR_KEEP_GENERATIONS]:
                self._stderr_tails.pop(old, None)
            proc = subprocess.Popen(
                self.worker_cmd + ["--audio-root", self.audio_root],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env)
            self._proc = proc
            reader = threading.Thread(
                target=self._read_loop, args=(proc, generation),
                name=f"localflow-worker-read-g{generation}", daemon=True)
            self._readers[generation] = reader
            reader.start()
            threading.Thread(
                target=self._drain_stderr, args=(proc, generation),
                name=f"localflow-worker-err-g{generation}",
                daemon=True).start()
            self.emit("worker.spawned", level="INFO",
                      worker_generation=generation,
                      reason_code="fresh_subprocess",
                      detail=f"pid={proc.pid}")
            ok = self._hello.wait(self.hello_timeout)
            if self.closed:
                # shutdown() woke this wait: the new child never serves.
                self._kill_proc(proc)
                if self._proc is proc:
                    self._proc = None
                raise WorkerFailure("supervisor_closed", stage="spawn",
                                    fatal=False)
            if not ok:
                self._record_death("hello_timeout")
                self._kill_proc(proc)
                if self._proc is proc:
                    self._proc = None
                raise WorkerFailure("hello_timeout", stage="spawn")
            try:
                self._send({"v": PROTOCOL_VERSION, "op": "load",
                            "asr_model": self.asr_model,
                            "cleanup_mode": self.cleanup_mode,
                            "cleanup_model": self.cleanup_model,
                            "cleanup_implementation":
                                self.cleanup_implementation,
                            # A spawn made FOR a waiting request lets that
                            # request run before the long cleanup load
                            # (M03-AUDIT-07): GPU work stays serialized.
                            "defer_cleanup_until_request":
                                bool(defer_cleanup)}, proc=proc)
            except (OSError, ValueError) as e:
                self._record_death(f"load_send_{type(e).__name__}")
                self._kill_proc(proc)
                if self._proc is proc:
                    self._proc = None
                raise WorkerFailure("load_send_failed", stage="spawn",
                                    detail=type(e).__name__)

    def ensure_running(self, defer_cleanup=False):
        """Spawn if needed; returns False when the breaker is tripped and
        raises ``WorkerFailure('supervisor_closed')`` after shutdown. The
        check-and-spawn is serialized with every other lifecycle change so
        the launch-time warm-up, a request, a retry and a restart can never
        race each other into two workers."""
        with self._spawn_lock:
            with self._state_lock:
                if self._closed:
                    raise WorkerFailure("supervisor_closed", stage="spawn",
                                        fatal=False)
                if self.supervisor_state == "failed":
                    return False
            if self._proc is not None and self._proc.poll() is None \
                    and self._hello.is_set():
                return True
            if self._proc is not None:
                # Dead or never-greeted child of an earlier generation:
                # reap it before its replacement exists.
                self._kill()
            self._spawn(defer_cleanup=defer_cleanup)
            return True

    def _read_loop(self, proc, generation):
        reason = "worker_process_exited"
        try:
            while True:
                raw = _read_exact(proc.stdout, 4)
                if raw is None:
                    return
                length = int.from_bytes(raw, "big")
                if length <= 0 or length > MAX_FRAME:
                    reason = "bad_frame_length"
                    self.emit("worker.protocol_error", level="ERROR",
                              worker_generation=generation,
                              reason_code="bad_frame_length",
                              detail=f"len={length}")
                    return
                body = _read_exact(proc.stdout, length)
                if body is None:
                    # EOF mid-frame: the stream is no longer trustworthy.
                    reason = "truncated_frame"
                    self.emit("worker.protocol_error", level="ERROR",
                              worker_generation=generation,
                              reason_code="truncated_frame")
                    return
                try:
                    msg = json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # The length was trustworthy: framing is intact, only
                    # this frame is lost.
                    self.emit("worker.protocol_error", level="ERROR",
                              worker_generation=generation,
                              reason_code="unparsable_frame")
                    continue
                try:
                    self._handle_message(msg, generation, proc)
                except Exception as e:  # a handler bug never kills reading
                    self.emit("worker.protocol_error", level="ERROR",
                              worker_generation=generation,
                              reason_code="handler_error",
                              detail=safe_type(type(e).__name__))
        except (OSError, ValueError):
            return
        finally:
            self._finalize_generation(generation, reason)

    def _finalize_generation(self, generation, reason):
        """The pipe closed: the worker died. Every request THIS process
        owned resolves as a fault immediately — a request must never hang
        on a dead pipe — and nothing another generation owns is touched
        (M03-AUDIT-03)."""
        self.emit("worker.pipe_closed",
                  level="ERROR" if generation == self.generation
                  else "INFO",
                  worker_generation=generation, reason_code=reason)
        with self._state_lock:
            self._finalized.add(generation)
            stuck = [(rid, p) for rid, p in self._pending.items()
                     if p.generation == generation]
            for rid, _p in stuck:
                self._pending.pop(rid, None)
        for req_id, pending in stuck:
            pending.msg = {
                "v": PROTOCOL_VERSION, "op": "fault", "req_id": req_id,
                "error_type": "WorkerProcessExited",
                "reason_code": "worker_process_exited",
                "fault_class": "runtime"}
            pending.event.set()

    def _drain_stderr(self, proc, generation):
        tail = self._stderr_tails.get(generation)
        if tail is None:
            tail = _StderrTail()
        stream = proc.stderr
        try:
            read = getattr(stream, "read1", None)
            if read is not None:
                while True:
                    chunk = read(4096)
                    if not chunk:
                        return
                    tail.feed(chunk)
            for chunk in stream:
                tail.feed(chunk[-STDERR_TAIL_BYTES:])
        except (OSError, ValueError):
            pass

    def _handle_message(self, msg, generation, proc):
        if not isinstance(msg, dict):
            self.emit("worker.protocol_error", level="ERROR",
                      worker_generation=generation,
                      reason_code="non_object_frame")
            return
        if msg.get("v") != PROTOCOL_VERSION:
            v = msg.get("v")
            self.emit("worker.protocol_error", level="ERROR",
                      worker_generation=generation,
                      reason_code="version_mismatch",
                      detail=f"worker_v={v if isinstance(v, int) else '?'}")
            return
        op = msg.get("op")
        if op == "hello":
            if generation == self.generation:
                self._hello.set()
            return
        if op == "engine":
            if generation != self.generation:
                # A late engine message from a dying generation must not
                # mutate the fresh worker's readiness.
                return
            engine = msg.get("engine")
            state = msg.get("state")
            if engine in self.engine_state and state in _ENGINE_STATES:
                with self._state_lock:
                    self.engine_state[engine] = state
                # The event signals "reached a scheduling-terminal state"
                # (ready or failed) — intermediate loading/warming updates
                # the visible state without waking waiters.
                if state in ("ready", "failed"):
                    self._engine_events[engine].set()
                self.on_engine(engine, state, msg)
                model = msg.get("model_id")
                self.emit("worker.engine_state", level="INFO",
                          worker_generation=generation,
                          model_id=model if isinstance(model, str)
                          else None,
                          outcome=state,
                          reason_code=safe_code(msg.get("reason_code"),
                                                None))
            return
        if op == "diag":
            n = msg.get("bytes")
            self.emit("worker.diag", level="DEBUG",
                      worker_generation=generation,
                      reason_code=safe_code(msg.get("kind")),
                      detail=f"bytes={n if isinstance(n, int) else '?'}"
                             f"{' truncated' if msg.get('truncated') else ''}")
            return
        if op == "fault":
            req_id = msg.get("req_id")
            resolved = self._resolve(req_id, msg, generation)
            self.emit("worker.fault", level="ERROR",
                      worker_generation=generation,
                      job_id=msg.get("job_id")
                      if isinstance(msg.get("job_id"), str) else None,
                      stage=safe_code(msg.get("stage"), None),
                      reason_code=safe_code(msg.get("reason_code")),
                      outcome=None if resolved else "unowned_fault_ignored",
                      detail=self._fault_detail(generation))
            return
        if op == "result":
            req_id = msg.get("req_id")
            with self._state_lock:
                pending = self._pending.get(req_id) \
                    if isinstance(req_id, str) else None
            if pending is None:
                # Stale by construction: late or unknown — discarded, never
                # inserted or counted.
                self.emit("worker.stale_result_discarded", level="WARNING",
                          worker_generation=generation,
                          reason_code="unknown_request")
                return
            if pending.generation != generation:
                # Another generation's request: never this reader's to
                # resolve, whatever the frame claims.
                self.emit("worker.stale_result_discarded", level="WARNING",
                          worker_generation=generation,
                          reason_code="foreign_generation")
                return
            if generation != self.generation \
                    or msg.get("generation") != generation:
                # Stale by construction: a result from, or echoing, another
                # worker generation can never satisfy this request
                # (M03-AC02).
                self.emit("worker.stale_result_discarded", level="WARNING",
                          worker_generation=generation,
                          job_id=pending.job_id,
                          reason_code="stale_generation")
                self._resolve(req_id, {
                    "v": PROTOCOL_VERSION, "op": "fault", "req_id": req_id,
                    "error_type": "StaleGeneration",
                    "reason_code": "stale_generation",
                    "fault_class": "runtime"}, pending.generation)
                return
            if msg.get("job_id") != pending.job_id \
                    or msg.get("attempt") != pending.attempt \
                    or msg.get("kind") != pending.kind:
                # A live request id with the wrong job/attempt/kind is a
                # worker protocol violation (M03-AUDIT-13): it resolves as
                # a fault, never as this request's result.
                self.emit("worker.protocol_error", level="ERROR",
                          worker_generation=generation,
                          job_id=pending.job_id,
                          reason_code="result_identity_mismatch")
                self._resolve(req_id, {
                    "v": PROTOCOL_VERSION, "op": "fault", "req_id": req_id,
                    "error_type": "ProtocolError",
                    "reason_code": "result_identity_mismatch",
                    "fault_class": "runtime"}, generation)
                return
            self._resolve(req_id, msg, generation)
            return
        # Unknown op — including anything resembling an insertion request —
        # is ignored: the worker has no insertion authority (S06).
        self.emit("worker.protocol_error", level="WARNING",
                  worker_generation=generation,
                  reason_code="unknown_op",
                  detail=f"op={safe_code(op, '?')}")

    def _resolve(self, req_id, msg, generation) -> bool:
        """Resolve one request — only if the frame's generation owns it."""
        with self._state_lock:
            pending = self._pending.get(req_id) \
                if isinstance(req_id, str) else None
            if pending is None or pending.generation != generation:
                return False
            self._pending.pop(req_id, None)
        pending.msg = msg
        pending.event.set()
        return True

    def _new_pending(self, req_id, *, op, job_id, attempt, generation):
        return _Pending(req_id, op=op, job_id=job_id, attempt=attempt,
                        generation=generation)

    def _fault_detail(self, generation=None) -> str:
        """Content-free digest of ONE generation's stderr tail — line/byte
        counts and a traceback flag only. Never raises: diagnostics can
        never change a request's disposition (M03-AUDIT-16)."""
        try:
            tail = self._stderr_tails.get(
                self.generation if generation is None else generation)
            return tail.digest() if tail is not None else "stderr_lines=0"
        except Exception:
            return "stderr_digest_unavailable"

    # ---- requests -----------------------------------------------------------

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None,
                   revoked=None):
        return self._request("transcribe", "asr", {
            "job_id": job_id, "attempt": attempt,
            "audio": {"name": audio_name},
            "sample_rate": sample_rate,
        }, revoked=revoked)

    def clean(self, *, job_id, attempt, raw_text, protected_spans=None,
              relevant_vocabulary=None, vocabulary_pairs=None,
              destination_profile=None, locale=None, revoked=None):
        # Cleanup never blocks on engine readiness: a loading/failed engine
        # answers in basic mode and says so in the result (M03-AC04). The
        # parent's "wait" policy does its own bounded wait_engine first.
        # M07 permitted context (additive, None-safe): protected spans in
        # normalized-text coordinates, the frozen scoped vocabulary and
        # the destination profile — never nearby text (contracts/context.md).
        payload = {"job_id": job_id, "attempt": attempt, "raw_text": raw_text}
        for key, val in (("protected_spans", protected_spans),
                         ("relevant_vocabulary", relevant_vocabulary),
                         ("vocabulary_pairs", vocabulary_pairs),
                         ("destination_profile", destination_profile),
                         ("locale", locale)):
            if val is not None:
                payload[key] = val
        return self._request("clean", "cleanup", payload, engine_wait=0.0,
                             revoked=revoked)

    def transform(self, *, job_id=None, attempt=1, transform_id,
                  transform_revision, prompt_revision, mode, source,
                  source_kind="selection", instructions="",
                  examples_revision="", examples=(), locale=None):
        """M11 (S16): one bounded transform generation on the cleanup
        engine's model. Serialized with every other GPU request (a
        concurrent dictation's ASR waits its turn — recorded, never
        starved). Coverage validation happens in the worker's engine."""
        payload = {"job_id": job_id, "attempt": attempt,
                   "transform_id": transform_id,
                   "transform_revision": transform_revision,
                   "prompt_revision": prompt_revision, "mode": mode,
                   "source": source, "source_kind": source_kind,
                   "instructions": instructions,
                   "examples_revision": examples_revision,
                   "examples": [list(ex) for ex in examples]}
        if locale is not None:
            payload["locale"] = locale
        return self._request("transform", "cleanup", payload,
                             engine_wait=0.0)

    def _request(self, op, engine, payload, _retry=True, engine_wait=None,
                 revoked=None):
        # Serialize ordinary GPU jobs: one request runs at a time across
        # all callers; queued work waits here (Spec S06).
        with self._gpu_lock:
            return self._request_locked(op, engine, payload, _retry,
                                        engine_wait, revoked)

    def _request_locked(self, op, engine, payload, _retry=True,
                        engine_wait=None, revoked=None):
        if self.closed:
            raise WorkerFailure("supervisor_closed", stage=op, fatal=False)
        if not self.ensure_running(defer_cleanup=True):
            raise WorkerFailure("supervisor_breaker_tripped", stage=op,
                                fatal=False)
        wait = self.ready_timeout if engine_wait is None else engine_wait
        # ASR must be ready before transcribing; cleanup may run degraded
        # (basic fallback inside the worker) but not mid-load.
        if not self._wait_engine(engine, wait):
            if self.closed:
                raise WorkerFailure("supervisor_closed", stage=op,
                                    fatal=False)
            state = self.engine_state.get(engine)
            if engine == "asr":
                raise WorkerFailure(f"asr_engine_{state}", stage=op,
                                    fatal=False)
        if op == "transcribe" and self.engine_state.get("cleanup") in (
                "loading", "warming"):
            # One GPU owner (S06): ASR waits for a cleanup load already in
            # progress. Stated, never hidden (M03-AUDIT-07).
            self.emit("worker.request_queued_behind_load", level="INFO",
                      worker_generation=self.generation,
                      job_id=payload.get("job_id"), stage=op,
                      reason_code="cleanup_load_in_progress")
        try:
            return self._request_once(op, engine, payload)
        except WorkerFailure as first:
            if not first.fatal or not _retry:
                raise
            try:
                return self._retry_once(op, engine, payload, wait, first,
                                        revoked)
            except WorkerFailure as second:
                if second.attempt is None:
                    # The retry never reached a worker: the execution that
                    # actually ran is still the first one.
                    second.attempt = first.attempt
                    second.generation = first.generation
                raise

    def _retry_once(self, op, engine, payload, wait, first, revoked):
        self.emit("worker.restarting", level="WARNING",
                  worker_generation=first.generation,
                  job_id=payload.get("job_id"),
                  stage=op, reason_code=first.reason_code,
                  outcome="retry_once")
        with self._spawn_lock:
            # The damaged generation is retired whatever happens next.
            self._retire(first.generation, "fatal_stage_failure")
            if first.generation is None:
                self._kill()
            if (revoked is not None and revoked()) \
                    or self.is_revoked(payload.get("job_id")):
                raise WorkerFailure("request_revoked", stage=op,
                                    fatal=False)
            with self._state_lock:
                if self._closed:
                    raise WorkerFailure("supervisor_closed", stage=op,
                                        fatal=False)
                if self.supervisor_state == "failed" or \
                        self._consecutive_deaths >= BREAKER_LIMIT:
                    raise WorkerFailure("supervisor_breaker_tripped",
                                        stage=op, fatal=False)
                self.supervisor_state = "degraded"
            fresh = (self._proc is not None and self._proc.poll() is None
                     and self._hello.is_set()
                     and self.generation != first.generation)
            if not fresh:
                # (A concurrent manual restart may already have provided a
                # fresh worker; otherwise spawn one.)
                self._kill()
                self._spawn(defer_cleanup=True)
        if not self._wait_engine(engine, wait):
            if self.closed:
                raise WorkerFailure("supervisor_closed", stage=op,
                                    fatal=False)
            state = self.engine_state.get(engine)
            if engine == "asr":
                raise WorkerFailure(f"asr_engine_{state}", stage=op,
                                    fatal=False)
        # The retry is a new attempt of the same job (contracts/jobs.md):
        # old-attempt results can never satisfy it.
        payload = dict(payload)
        payload["attempt"] = int(payload.get("attempt") or 1) + 1
        try:
            result = self._request_once(op, engine, payload)
        except WorkerFailure as second:
            second.retried = second.attempt is not None
            if second.fatal:
                # A second fatal failure retires its generation even below
                # the breaker threshold: a poisoned process is never
                # reused by the next job (M03-AUDIT-06).
                self._retire(second.generation, "second_fatal_failure")
            raise
        result["retried"] = True
        return result

    def _request_once(self, op, engine, payload):
        req_id = ids.new_id("req")
        attempt = payload.get("attempt")
        # Registration and send happen under the lifecycle lock, so the
        # request is stamped with — and written to — one process: no
        # restart can swap the child between the two.
        with self._spawn_lock:
            with self._state_lock:
                if self._closed:
                    raise WorkerFailure("supervisor_closed", stage=op,
                                        fatal=False)
                generation = self.generation
                proc = self._proc
                pending = self._new_pending(
                    req_id, op=op, job_id=payload.get("job_id"),
                    attempt=attempt, generation=generation)
                if generation in self._finalized:
                    # Its reader already finished: resolve now instead of
                    # hanging on a pipe nobody reads.
                    pending.msg = {"v": PROTOCOL_VERSION, "op": "fault",
                                   "req_id": req_id,
                                   "error_type": "WorkerProcessExited",
                                   "reason_code": "worker_process_exited",
                                   "fault_class": "runtime"}
                    pending.event.set()
                else:
                    self._pending[req_id] = pending
            msg = {"v": PROTOCOL_VERSION, "op": op, "req_id": req_id,
                   "generation": generation}
            msg.update(payload)
            try:
                if not pending.event.is_set():
                    self._send(msg, proc=proc)
            except _FrameTooLarge:
                with self._state_lock:
                    self._pending.pop(req_id, None)
                raise WorkerFailure("request_too_large", stage=op,
                                    fatal=False)
            except (OSError, ValueError) as e:
                with self._state_lock:
                    self._pending.pop(req_id, None)
                self._record_death(f"send_{type(e).__name__}")
                raise WorkerFailure("worker_pipe_broken", stage=op,
                                    detail=type(e).__name__,
                                    generation=generation)
        # From here the request was admitted to generation `generation`.
        if not pending.event.wait(self.request_timeout):
            with self._state_lock:
                self._pending.pop(req_id, None)
            self._record_death("request_timeout")
            raise WorkerFailure("request_timeout", stage=op,
                                attempt=attempt, generation=generation)
        out = pending.msg
        if out is None:  # resolved without a message — reader died
            raise WorkerFailure("worker_died", stage=op, attempt=attempt,
                                generation=generation)
        if out.get("op") == "fault":
            fclass = out.get("fault_class")
            fatal = fclass not in _NONFATAL_CLASSES
            reason = safe_code(out.get("reason_code"), None) or safe_type(
                out.get("error_type")) or "worker_fault"
            if fatal:
                self._record_death(f"stage_fault:{reason}")
            raise WorkerFailure(reason, stage=op,
                                detail=out.get("error_type"), fatal=fatal,
                                attempt=attempt, generation=generation)
        out.setdefault("generation", generation)
        if out.get("retire_generation"):
            # A runtime failure the worker answered with preserved text
            # (e.g. an in-flight cleanup exception): the output survives,
            # the generation does not (M03-AUDIT-06). Never counted as a
            # healthy success.
            self._record_death("runtime_fallback")
            self._retire(generation, "runtime_fallback")
            out["retired_generation"] = True
            return out
        self._consecutive_deaths = 0
        return out

    def _send(self, msg, proc=None):
        data = json.dumps(msg, ensure_ascii=True).encode("utf-8")
        if len(data) > MAX_FRAME:
            raise _FrameTooLarge()
        with self._send_lock:
            if proc is None or proc.stdin is None:
                raise OSError("worker not running")
            proc.stdin.write(len(data).to_bytes(4, "big") + data)
            proc.stdin.flush()

    def revoke_job(self, job_id):
        """The parent withdrew this job's authority (user cancel or
        delete-everywhere): no automatic retry is admitted for it."""
        if not job_id:
            return
        with self._state_lock:
            self._revoked[job_id] = True
            while len(self._revoked) > 512:
                self._revoked.pop(next(iter(self._revoked)))

    def is_revoked(self, job_id) -> bool:
        if not job_id:
            return False
        with self._state_lock:
            return job_id in self._revoked

    def _wait_engine(self, engine, timeout) -> bool:
        """True when the engine reached a terminal-for-scheduling state
        (ready or failed). ASR failure is fatal to transcribe; cleanup
        failure only means the worker answers in basic mode."""
        with self._state_lock:
            state = self.engine_state.get(engine)
            if self._closed:
                return False
        if state in ("ready", "failed"):
            return state == "ready"
        self._engine_events[engine].wait(timeout)
        with self._state_lock:
            state = self.engine_state.get(engine)
            if self._closed:
                return False
        return state == "ready"

    def wait_engine(self, engine, timeout) -> str:
        """Public readiness wait (used by the cleanup hold policy)."""
        if self._wait_engine(engine, timeout):
            return "ready"
        with self._state_lock:
            return self.engine_state.get(engine)

    # ---- faults ---------------------------------------------------------------

    def _kill_proc(self, proc):
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass

    def _kill(self):
        with self._spawn_lock:
            proc, self._proc = self._proc, None
            if proc is not None:
                self._kill_proc(proc)

    def _retire(self, generation, reason):
        """Retire one generation: kill it if it is still the current
        process. A newer generation is never touched."""
        with self._spawn_lock:
            if generation is None or generation != self.generation \
                    or self._proc is None:
                return False
            self._kill()
        self.emit("worker.retired", level="WARNING",
                  worker_generation=generation, reason_code=reason)
        return True

    def _record_death(self, reason):
        self._consecutive_deaths += 1
        self.emit("worker.died", level="ERROR",
                  worker_generation=self.generation,
                  reason_code=safe_code(reason, "worker_death"),
                  outcome=f"death_{self._consecutive_deaths}")
        if self._consecutive_deaths >= BREAKER_LIMIT:
            with self._state_lock:
                if not self._closed:
                    self.supervisor_state = "failed"
            self.emit("worker.breaker_tripped", level="ERROR",
                      worker_generation=self.generation,
                      reason_code="consecutive_deaths",
                      detail=f"no successful stage in the last"
                             f" {self._consecutive_deaths} deaths; manual"
                             " restart required")
            self._kill()

    def restart(self):
        """Manual restart: re-arms the breaker and spawns a fresh worker.
        Refused after shutdown (closed admission is permanent)."""
        with self._spawn_lock:
            with self._state_lock:
                if self._closed:
                    raise WorkerFailure("supervisor_closed", stage="restart",
                                        fatal=False)
                self.supervisor_state = "running"
            self._consecutive_deaths = 0
            self._kill()
            self._spawn()
        self.emit("worker.manual_restart", level="INFO",
                  worker_generation=self.generation,
                  reason_code="user_action")

    def shutdown(self, timeout=5.0):
        """Close admission permanently, then retire the worker. Every
        request still waiting resolves as ``supervisor_closed`` (a
        non-fatal refusal: no retry, no respawn), a spawn in progress is
        woken and kills its own child, and the current child is asked to
        exit, then killed and reaped. Returns a status dict."""
        with self._state_lock:
            first = not self._closed
            self._closed = True
            self.supervisor_state = "closed"
            stuck = list(self._pending.items())
            self._pending.clear()
        for req_id, pending in stuck:
            pending.msg = {"v": PROTOCOL_VERSION, "op": "fault",
                           "req_id": req_id, "error_type": "SupervisorClosed",
                           "reason_code": "supervisor_closed",
                           "fault_class": "closed"}
            pending.event.set()
        # Wake any spawn waiting for hello and any engine waiter.
        self._hello.set()
        for evt in self._engine_events.values():
            evt.set()
        acquired = self._spawn_lock.acquire(timeout=max(0.1, timeout))
        reaped = False
        try:
            proc, self._proc = self._proc, None
            if proc is not None:
                # A graceful exit request, bounded: a child that stopped
                # reading could otherwise block this write forever.
                def _bye(p=proc):
                    try:
                        self._send({"v": PROTOCOL_VERSION,
                                    "op": "shutdown"}, proc=p)
                    except (OSError, ValueError):
                        pass
                bye = threading.Thread(target=_bye, daemon=True,
                                       name="localflow-worker-bye")
                bye.start()
                bye.join(timeout=0.5)
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    pass
                self._kill_proc(proc)
                reaped = proc.poll() is not None
        finally:
            if acquired:
                self._spawn_lock.release()
        for reader in list(self._readers.values()):
            if reader is not threading.current_thread():
                reader.join(timeout=0.5)
        if first:
            self.emit("worker.shutdown", level="INFO",
                      worker_generation=self.generation,
                      reason_code="supervisor_closed",
                      outcome="reaped" if reaped or proc is None
                      else "lifecycle_busy" if not acquired
                      else "reap_pending",
                      detail=f"requests_refused={len(stuck)}")
        return {"closed": True, "requests_refused": len(stuck),
                "lifecycle_acquired": acquired}


class _FrameTooLarge(ValueError):
    pass


def _read_exact(stream, n):
    """Exactly ``n`` bytes from a pipe, or None at EOF (a short read at
    EOF is a truncated frame, never a smaller message)."""
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf
