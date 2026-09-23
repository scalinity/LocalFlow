"""Worker supervision: spawn, readiness, faults, one-retry, stale discard.

The supervisor owns the model-worker subprocess described in
``localflow/v2/worker.py`` (Spec S06/S09, M03). Design invariants:

* **Fresh process, never a fork.** The parent (this process) holds no MLX
  state; every worker is a ``subprocess.Popen`` of a clean interpreter.
* **Generation + attempt reject stale results (M03-AC02).** Each worker
  process gets a new ``generation``; each request echoes the job's
  ``attempt``. Results resolve a pending request only when both match the
  values the supervisor itself stamped; anything else is discarded with an
  event, and only the parent's coordinator can act on a result at all.
* **One automatic retry (M03-AC01).** A faulted stage kills the damaged
  worker, spawns a fresh one, waits for the needed engine, and retries the
  stage once with ``attempt + 1``. A second fault raises ``WorkerFailure``;
  the caller turns that into a recoverable item. No loop.
* **Circuit breaker.** Three consecutive worker deaths with no successful
  stage trip the supervisor into ``failed``; further automatic work fails
  fast (audio preserved by the caller). A manual ``restart()`` re-arms it.
* **Serialized GPU.** One request is in flight at a time; ordinary dictation
  stages queue behind each other (S06).

The worker cannot request insertion — the protocol has no such message, and
unknown worker→parent messages are ignored.
"""

import collections
import os
import subprocess
import sys
import threading

from . import ids

PROTOCOL_VERSION = 1
BREAKER_LIMIT = 3  # consecutive deaths with zero successful stages


class WorkerFailure(Exception):
    """A stage failed after its one automatic retry (or could not start)."""

    def __init__(self, reason_code, stage=None, detail=None):
        super().__init__(f"{stage or 'worker'}: {reason_code}"
                         + (f" ({detail})" if detail else ""))
        self.reason_code = reason_code
        self.stage = stage
        self.detail = detail


class _Pending:
    def __init__(self):
        self.event = threading.Event()
        self.msg = None


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
        self.supervisor_state = "idle"  # idle|running|degraded|failed
        self._proc = None
        self._hello = threading.Event()
        self._engine_events = {"asr": threading.Event(),
                               "cleanup": threading.Event()}
        self._pending = {}
        self._send_lock = threading.Lock()
        self._gpu_lock = threading.Lock()  # one in-flight model request (S06)
        self._spawn_lock = threading.Lock()  # check-and-spawn is atomic
        self._state_lock = threading.Lock()
        self._consecutive_deaths = 0
        self._stderr_tail = collections.deque(maxlen=20)
        self._reader = None
        self._req_counter = 0
        os.makedirs(self.audio_root, exist_ok=True)
        try:
            os.chmod(self.audio_root, 0o700)
        except OSError:
            pass

    # ---- process lifecycle ------------------------------------------------

    def _spawn(self):
        """Start a fresh worker process (never a fork of Metal state)."""
        self.generation += 1
        env = dict(os.environ)
        env.update(self.spawn_env)
        # No unexpected downloads during dictation (S09): the worker runs
        # offline; a missing cache fails loudly with an install/repair hint.
        # Forced (not setdefault) so an inherited HF_HUB_OFFLINE=0 from the
        # launching shell cannot defeat it.
        env["HF_HUB_OFFLINE"] = "1"
        env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        env.setdefault("PYTHONPATH", os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self._hello.clear()
        for evt in self._engine_events.values():
            evt.clear()
        # A new process starts with a clean fault-context: stale stderr from
        # a previous generation must never bleed into this one's traces.
        self._stderr_tail.clear()
        with self._state_lock:
            self.engine_state = {"asr": "not_started",
                                 "cleanup": "not_started"}
        self._proc = subprocess.Popen(
            self.worker_cmd + ["--audio-root", self.audio_root],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env)
        self._reader = threading.Thread(
            target=self._read_loop, args=(self._proc, self.generation),
            name=f"localflow-worker-read-g{self.generation}", daemon=True)
        self._reader.start()
        threading.Thread(
            target=self._drain_stderr, args=(self._proc,),
            name=f"localflow-worker-err-g{self.generation}",
            daemon=True).start()
        self.emit("worker.spawned", level="INFO",
                  worker_generation=self.generation,
                  reason_code="fresh_subprocess",
                  detail=f"pid={self._proc.pid}")
        if not self._hello.wait(self.hello_timeout):
            self._record_death("hello_timeout")
            self._kill()
            raise WorkerFailure("hello_timeout", stage="spawn")
        try:
            self._send({"v": PROTOCOL_VERSION, "op": "load",
                        "asr_model": self.asr_model,
                        "cleanup_mode": self.cleanup_mode,
                        "cleanup_model": self.cleanup_model,
                        "cleanup_implementation": self.cleanup_implementation})
        except (OSError, ValueError) as e:
            self._record_death(f"load_send_{type(e).__name__}")
            self._kill()
            raise WorkerFailure("load_send_failed", stage="spawn",
                                detail=type(e).__name__)

    def ensure_running(self):
        """Spawn if needed; returns False when the breaker is tripped. The
        check-and-spawn is serialized so the launch-time warm-up and the
        first request can never race each other into two workers."""
        with self._spawn_lock:
            with self._state_lock:
                if self.supervisor_state == "failed":
                    return False
            if self._proc is not None and self._proc.poll() is None \
                    and self._hello.is_set():
                return True
            self._spawn()
            return True

    def _read_loop(self, proc, generation):
        try:
            while True:
                raw = proc.stdout.read(4)
                if not raw or len(raw) < 4:
                    return
                length = int.from_bytes(raw, "big")
                if length <= 0 or length > 64 * 1024 * 1024:
                    self.emit("worker.protocol_error", level="ERROR",
                              worker_generation=generation,
                              reason_code="bad_frame_length",
                              detail=f"len={length}")
                    return
                body = proc.stdout.read(length)
                try:
                    import json
                    msg = json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self.emit("worker.protocol_error", level="ERROR",
                              worker_generation=generation,
                              reason_code="unparsable_frame")
                    continue
                self._handle_message(msg, generation, proc)
        except (OSError, ValueError):
            return
        finally:
            # The pipe closed: the worker died. Everything still waiting on
            # this process resolves as a fault immediately — a request must
            # never hang on a dead pipe (the crash IS the fault signal).
            # req_ids are unique per request, so resolving unconditionally
            # can never mis-attribute a newer generation's pendings.
            if generation == self.generation:
                self.emit("worker.pipe_closed", level="ERROR",
                          worker_generation=generation,
                          reason_code="worker_process_exited")
            with self._state_lock:
                stuck = list(self._pending.items())
                self._pending.clear()
            for _req_id, pending in stuck:
                pending.msg = {
                    "v": PROTOCOL_VERSION, "op": "fault",
                    "req_id": _req_id,
                    "error_type": "WorkerProcessExited",
                    "reason_code": "worker_process_exited"}
                pending.event.set()

    def _drain_stderr(self, proc):
        try:
            for line in proc.stderr:
                self._stderr_tail.append(line)
        except (OSError, ValueError):
            pass

    def _handle_message(self, msg, generation, proc):
        if msg.get("v") != PROTOCOL_VERSION:
            self.emit("worker.protocol_error", level="ERROR",
                      worker_generation=generation,
                      reason_code="version_mismatch",
                      detail=f"worker_v={msg.get('v')}")
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
            if engine in self.engine_state:
                with self._state_lock:
                    self.engine_state[engine] = state
                # The event signals "reached a scheduling-terminal state"
                # (ready or failed) — intermediate loading/warming updates
                # the visible state without waking waiters.
                if state in ("ready", "failed"):
                    self._engine_events[engine].set()
                self.on_engine(engine, state, msg)
                self.emit("worker.engine_state", level="INFO",
                          worker_generation=generation, model_id=msg.get(
                              "model_id"),
                          outcome=state,
                          reason_code=msg.get("reason_code"))
            return
        if op == "diag":
            self.emit("worker.diag", level="DEBUG",
                      worker_generation=generation,
                      reason_code=msg.get("kind"),
                      detail=f"bytes={msg.get('bytes')}"
                             f"{' truncated' if msg.get('truncated') else ''}")
            return
        if op == "fault":
            self._resolve(msg.get("req_id"), msg, generation)
            self.emit("worker.fault", level="ERROR",
                      worker_generation=generation,
                      job_id=msg.get("job_id"),
                      stage=msg.get("stage"),
                      reason_code=msg.get("reason_code"),
                      detail=self._fault_detail())
            return
        if op == "result":
            req_id = msg.get("req_id")
            with self._state_lock:
                pending = self._pending.get(req_id)
            if pending is None:
                # Stale by construction: late or unknown — discarded, never
                # inserted or counted.
                self.emit("worker.stale_result_discarded", level="WARNING",
                          worker_generation=generation,
                          job_id=msg.get("job_id"),
                          reason_code="unknown_request")
                return
            if generation != self.generation or \
                    msg.get("generation") != generation:
                # Stale by construction: a result echoing an old worker
                # generation can never satisfy the current request (M03-AC02).
                self.emit("worker.stale_result_discarded", level="WARNING",
                          worker_generation=generation,
                          job_id=msg.get("job_id"),
                          reason_code="stale_generation")
                with self._state_lock:
                    self._pending.pop(req_id, None)
                pending.msg = {"v": PROTOCOL_VERSION, "op": "fault",
                               "req_id": req_id,
                               "error_type": "StaleGeneration",
                               "reason_code": "stale_generation"}
                pending.event.set()
                return
            self._resolve(req_id, msg, generation)
            self._consecutive_deaths = 0
            return
        # Unknown op — including anything resembling an insertion request —
        # is ignored: the worker has no insertion authority (S06).
        self.emit("worker.protocol_error", level="WARNING",
                  worker_generation=generation,
                  reason_code="unknown_op",
                  detail=f"op={op}")

    def _resolve(self, req_id, msg, generation):
        with self._state_lock:
            pending = self._pending.pop(req_id, None)
        if pending is not None:
            pending.msg = msg
            pending.event.set()

    def _fault_detail(self):
        """Content-free digest of the worker's stderr tail — line/byte
        counts and a traceback flag only; the raw lines stay in memory
        for local debugging and never enter the event stream."""
        lines = [ln for ln in self._stderr_tail if ln.strip()]
        total = sum(len(ln) for ln in lines)
        has_tb = any("Traceback" in ln for ln in lines)
        return (f"stderr_lines={len(lines)} bytes~={total}"
                f" traceback={'yes' if has_tb else 'no'}")

    # ---- requests -----------------------------------------------------------

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        return self._request("transcribe", "asr", {
            "job_id": job_id, "attempt": attempt,
            "audio": {"name": audio_name},
            "sample_rate": sample_rate,
        })

    def clean(self, *, job_id, attempt, raw_text, protected_spans=None,
              relevant_vocabulary=None, vocabulary_pairs=None,
              destination_profile=None, locale=None):
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
        return self._request("clean", "cleanup", payload, engine_wait=0.0)

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

    def _request(self, op, engine, payload, _retry=True, engine_wait=None):
        # Serialize ordinary GPU jobs: one request runs at a time across
        # all callers; queued work waits here (Spec S06).
        with self._gpu_lock:
            return self._request_locked(op, engine, payload, _retry,
                                        engine_wait)

    def _request_locked(self, op, engine, payload, _retry=True,
                        engine_wait=None):
        if not self.ensure_running():
            raise WorkerFailure("supervisor_breaker_tripped", stage=op)
        wait = self.ready_timeout if engine_wait is None else engine_wait
        # ASR must be ready before transcribing; cleanup may run degraded
        # (basic fallback inside the worker) but not mid-load.
        if not self._wait_engine(engine, wait):
            state = self.engine_state.get(engine)
            if engine == "asr":
                raise WorkerFailure(f"asr_engine_{state}", stage=op)
        try:
            return self._request_once(op, engine, payload)
        except WorkerFailure as first:
            self.emit("worker.restarting", level="WARNING",
                      worker_generation=self.generation, job_id=payload.get(
                          "job_id"),
                      stage=op, reason_code=first.reason_code,
                      outcome="retry_once")
            with self._state_lock:
                if self.supervisor_state == "failed" or \
                        self._consecutive_deaths >= BREAKER_LIMIT:
                    raise WorkerFailure("supervisor_breaker_tripped",
                                        stage=op)
                self.supervisor_state = "degraded"
            self._kill()
            self._spawn()
            if not self._wait_engine(engine, wait):
                state = self.engine_state.get(engine)
                if engine == "asr":
                    raise WorkerFailure(f"asr_engine_{state}", stage=op)
            # The retry is a new attempt of the same job (contracts/jobs.md):
            # old-attempt results can never satisfy it.
            payload = dict(payload)
            payload["attempt"] = int(payload.get("attempt") or 1) + 1
            result = self._request_once(op, engine, payload)
            result["retried"] = True
            return result

    def _request_once(self, op, engine, payload):
        req_id = ids.new_id("req")
        with self._state_lock:
            pending = self._pending[req_id] = _Pending()
        msg = {"v": PROTOCOL_VERSION, "op": op, "req_id": req_id,
               "generation": self.generation}
        msg.update(payload)
        try:
            self._send(msg)
        except (OSError, ValueError) as e:
            with self._state_lock:
                self._pending.pop(req_id, None)
            self._record_death(f"send_{type(e).__name__}")
            raise WorkerFailure("worker_pipe_broken", stage=op,
                                detail=type(e).__name__)
        proc = self._proc
        if not pending.event.wait(self.request_timeout):
            with self._state_lock:
                self._pending.pop(req_id, None)
            self._record_death("request_timeout")
            raise WorkerFailure("request_timeout", stage=op)
        out = pending.msg
        if out is None:  # resolved without a message — reader died
            raise WorkerFailure("worker_died", stage=op)
        if out.get("op") == "fault":
            self._record_death(f"stage_fault:"
                               f"{out.get('reason_code', 'unknown')}")
            raise WorkerFailure(
                out.get("reason_code") or out.get("error_type") or
                "worker_fault", stage=op,
                detail=out.get("error_type"))
        out.setdefault("generation", self.generation)
        return out

    def _send(self, msg):
        import json
        with self._send_lock:
            proc = self._proc
            if proc is None or proc.stdin is None:
                raise OSError("worker not running")
            data = json.dumps(msg, ensure_ascii=True).encode("utf-8")
            proc.stdin.write(len(data).to_bytes(4, "big") + data)
            proc.stdin.flush()

    def _wait_engine(self, engine, timeout) -> bool:
        """True when the engine reached a terminal-for-scheduling state
        (ready or failed). ASR failure is fatal to transcribe; cleanup
        failure only means the worker answers in basic mode."""
        with self._state_lock:
            state = self.engine_state.get(engine)
        if state in ("ready", "failed"):
            return state == "ready"
        self._engine_events[engine].wait(timeout)
        with self._state_lock:
            state = self.engine_state.get(engine)
        return state == "ready"

    def wait_engine(self, engine, timeout) -> str:
        """Public readiness wait (used by the cleanup hold policy)."""
        if self._wait_engine(engine, timeout):
            return "ready"
        with self._state_lock:
            return self.engine_state.get(engine)

    # ---- faults ---------------------------------------------------------------

    def _kill(self):
        proc, self._proc = self._proc, None
        if proc is None:
            return
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

    def _record_death(self, reason):
        self._consecutive_deaths += 1
        self.emit("worker.died", level="ERROR",
                  worker_generation=self.generation, reason_code=reason,
                  outcome=f"death_{self._consecutive_deaths}")
        if self._consecutive_deaths >= BREAKER_LIMIT:
            with self._state_lock:
                self.supervisor_state = "failed"
            self.emit("worker.breaker_tripped", level="ERROR",
                      worker_generation=self.generation,
                      reason_code="consecutive_deaths",
                      detail=f"no successful stage in the last"
                             f" {self._consecutive_deaths} deaths; manual"
                             " restart required")
            self._kill()

    def restart(self):
        """Manual restart: re-arms the breaker and spawns a fresh worker."""
        with self._spawn_lock:
            with self._state_lock:
                self.supervisor_state = "running"
            self._consecutive_deaths = 0
            self._kill()
            self._spawn()
        self.emit("worker.manual_restart", level="INFO",
                  worker_generation=self.generation,
                  reason_code="user_action")

    def shutdown(self, timeout=5.0):
        try:
            self._send({"v": PROTOCOL_VERSION, "op": "shutdown"})
        except (OSError, ValueError):
            pass
        proc = self._proc
        if proc is not None:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._kill()
                return
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except (OSError, ValueError):
                    pass
            self._proc = None
