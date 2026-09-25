"""Model worker subprocess (Spec S06, contracts/worker.md, M03).

A fresh process — spawned, never a fork of initialized Metal state — owns
all MLX/GPU state for ASR and cleanup. It speaks a versioned, length-framed
JSON protocol over inherited pipes (stdin/stdout):

  parent→worker : load, transcribe, clean, transform, shutdown
  worker→parent : hello, engine, result, fault, diag

Boundaries that hold by construction:
  * The worker cannot request an insertion — no such message exists. Only
    the parent's coordinator ever issues an insertion.
  * Audio arrives as a parent-created file name under a root fixed at
    spawn; the worker refuses separators, symlinks and anything that is
    not a regular file, and parses the declared WAV strictly (a truncated
    payload is refused, never transcribed as a shorter "complete" input).
  * Failures are structured ``fault`` messages carrying a CONTROLLED
    reason code, the exception class name and a fault class — never
    exception text (S07: transcripts/paths/secrets can hide there).
  * Control and GPU work are separate threads (M03-AUDIT-07): the control
    thread always reads the next request, so a cleanup request during a
    long cleanup-model load is answered NOW on the CPU (basic/unchanged,
    honestly labeled) instead of queueing behind the load; every model
    operation — loads included — still runs one at a time on the single
    GPU thread (S06).

Every message carries ``v`` (protocol version) and echoes the request's
``job_id``/``attempt``/``generation`` so stale results are detectable
(M03-AC02). Stage durations are measured with this process's monotonic
clock and reported as elapsed-ms only (S07: never compare absolute
monotonic values across processes).

Run: python -m localflow.v2.worker --audio-root <dir>
"""

import argparse
import errno
import os
import re
import stat
import sys
import threading
import time

PROTOCOL_VERSION = 1
MAX_FRAME = 64 * 1024 * 1024
MAX_AUDIO_BYTES = 2 * 1024 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\Z")
_CODE = re.compile(r"^[a-z0-9_.:-]{1,80}\Z")
_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,63}\Z")
_WRITE_LOCK = threading.Lock()


class ProtocolError(Exception):
    """A request the worker refuses; ``code`` is a controlled token."""

    fault_class = "protocol"

    def __init__(self, code="protocol_error", request=None):
        super().__init__(code)
        self.code = code
        self.request = request


class InputError(ProtocolError):
    """The parent-provided input cannot be used as given (deterministic:
    retrying on a fresh worker would fail identically)."""

    fault_class = "input"


class EngineNotReady(ProtocolError):
    fault_class = "engine"


class _FramingError(Exception):
    """The byte stream can no longer be trusted (bad length / EOF)."""


def _write_msg(msg: dict):
    import json
    data = json.dumps(msg, ensure_ascii=True).encode("utf-8")
    if len(data) > MAX_FRAME:
        raise ProtocolError("response_too_large")
    frame = memoryview(len(data).to_bytes(4, "big") + data)
    # Write ALL of it (M03-AUDIT-13): a short os.write must never leave the
    # next frame parsed as the remainder of this one. Two threads (control
    # and GPU) write, so frames are serialized whole.
    with _WRITE_LOCK:
        while frame:
            n = os.write(1, frame)
            if n <= 0:
                raise OSError(errno.EIO, "protocol write made no progress")
            frame = frame[n:]


def _read_exact(fd: int, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise EOFError("control pipe closed")
        buf += chunk
    return buf


def _read_msg(fd: int) -> dict:
    """One request. Raises ``_FramingError``/``EOFError`` when the stream
    is unusable, and ``ProtocolError`` for a well-framed but invalid body
    (the next frame is still trustworthy)."""
    import json
    length = int.from_bytes(_read_exact(fd, 4), "big")
    if length <= 0 or length > MAX_FRAME:
        raise _FramingError(f"bad frame length {length}")
    body = _read_exact(fd, length)
    try:
        msg = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ProtocolError("unparsable_request")
    if not isinstance(msg, dict):
        raise ProtocolError("non_object_request")
    if msg.get("v") != PROTOCOL_VERSION:
        raise ProtocolError("protocol_version_mismatch", request=msg)
    return msg


def _validate(msg):
    """Field shape for the request ops (the op itself is checked by the
    dispatcher). Content never appears in the refusal code."""
    req_id = msg.get("req_id")
    if not isinstance(req_id, str) or not 0 < len(req_id) <= 128:
        raise ProtocolError("bad_request_fields")
    if not isinstance(msg.get("generation"), int) \
            or isinstance(msg.get("generation"), bool):
        raise ProtocolError("bad_request_fields")
    attempt = msg.get("attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool) \
            or attempt < 1:
        raise ProtocolError("bad_request_fields")
    if msg.get("job_id") is not None and not isinstance(msg.get("job_id"),
                                                        str):
        raise ProtocolError("bad_request_fields")


class _BoundedStderr:
    """Keep the last bytes of third-party stderr (tqdm, loaders) so it can
    never interleave with the protocol stream; report sizes only."""

    LIMIT = 64 * 1024

    def __init__(self):
        self.total = 0
        self.truncated = False
        self._buf = ""

    def write(self, s):
        try:
            self.total += len(s)
            self._buf = (self._buf + s)[-self.LIMIT:]
            if len(self._buf) == self.LIMIT:
                self.truncated = True
        except Exception:
            pass
        return len(s)

    def flush(self):
        pass


def parse_wav_f32(raw: bytes):
    """Strict mono float32 WAV parse (the M03 input boundary): the data
    chunk must be present in full — a truncated payload raises
    ``store.WavIncompleteError`` rather than yielding fewer samples."""
    from .store import parse_wav_f32 as _parse
    return _parse(raw)


class Worker:
    def __init__(self, audio_root: str):
        self.audio_root = os.path.abspath(audio_root)
        self.transcriber = None
        self.cleaner = None
        self.cleanup_mode = "off"
        self.asr_model = None
        self._load_error = {}
        # M07 (S13–S14): the V2 faithful-cleanup engine, selected by the
        # load message's cleanup_implementation ("v2"); "v1" keeps the
        # TranscriptCleaner control path unchanged.
        self.cleanup_implementation = "v2"
        self.cleanup_engine = None
        # A failed V2 load answers with the unchanged normalized input
        # (the last preserved artifact), never a protection-blind pass.
        self._v2_load_failed = False
        # M11 (S16): the cleanup engine's raw generation/render pair —
        # a transform runs one bounded local generation on the SAME
        # loaded model (no second engine, no model change).
        self._cleanup_generate = None
        self._cleanup_render = None
        self._cleanup_model = None
        # M03-AUDIT-07 scheduling state (control thread ↔ GPU thread).
        self.asr_state = "not_started"
        self.cleanup_state = "not_started"
        self._cond = threading.Condition()
        self._tasks = []           # FIFO of ("transcribe"|…, msg)
        self._loads = []           # pending "load_asr"/"load_cleanup"
        self._defer_cleanup = False
        self._request_seen = False
        self._stopping = False

    # ---- engines -----------------------------------------------------------

    def _configure(self, msg):
        self.asr_model = msg.get("asr_model")
        self.cleanup_mode = msg.get("cleanup_mode", "off")
        self._cleanup_model = msg.get("cleanup_model")
        self.cleanup_implementation = msg.get("cleanup_implementation", "v2")
        # A fresh load starts from a clean engine slate (defensive: the
        # supervisor spawns a fresh process per load, so this only
        # matters for direct Worker reuse in tests).
        self.cleanup_engine = None
        self._v2_load_failed = False

    def _load(self, msg):
        """Synchronous full load (ASR, then cleanup) — the GPU thread runs
        the same two steps as separate tasks."""
        self._configure(msg)
        if self._load_asr():
            self._load_cleanup()

    def _load_asr(self) -> bool:
        from ..stt import Transcriber
        t = Transcriber(self.asr_model)
        self.asr_state = "loading"

        def phase(name):
            if name == "loading":
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "asr", "state": "loading",
                            "model_id": self.asr_model})
            else:
                self.asr_state = "warming"
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "asr", "state": "warming",
                            "model_id": self.asr_model})

        try:
            with _capture_stderr():
                t.load(on_phase=phase)
        except Exception as e:
            self._load_error["asr"] = f"{type(e).__name__}"
            self.asr_state = "failed"
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "asr", "state": "failed",
                        "model_id": self.asr_model,
                        "reason_code": "asr_engine_load_failed",
                        "error_type": _safe_type(type(e).__name__)})
            return False
        self.transcriber = t
        self.asr_state = "ready"
        _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                    "engine": "asr", "state": "ready",
                    "model_id": self.asr_model})
        return True

    def _load_cleanup(self):
        cleanup_model = self._cleanup_model
        if self.cleanup_mode == "llm" \
                and self.cleanup_implementation == "v2":
            from .cleanup import CleanupEngine, ModelRunner  # noqa: F401
            self.cleanup_state = "loading"
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "loading",
                        "model_id": cleanup_model})
            try:
                runner = ModelRunner(cleanup_model)
                with _capture_stderr():
                    runner.load()
                self.cleanup_engine = runner.engine()
                self._cleanup_generate = runner.generate_fn()
                self._cleanup_render = runner.render
            except Exception as e:
                # Load failure degrades — the engine is failed, not the
                # worker. The degraded answer is the unchanged normalized
                # input with the honest cleanup_engine_failed reason: the
                # basic regex pass would strip fillers inside protected
                # literals and code ('Keep "um" literal.' → 'Keep ""
                # literal.'). The v1 path keeps its own basic fallback.
                self._load_error["cleanup"] = f"{type(e).__name__}"
                self._v2_load_failed = True
                self.cleanup_state = "failed"
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "cleanup", "state": "failed",
                            "model_id": cleanup_model,
                            "reason_code": "cleanup_engine_load_failed",
                            "error_type": _safe_type(type(e).__name__)})
                return
            self.cleanup_state = "ready"
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "ready",
                        "model_id": cleanup_model})
            return
        if self.cleanup_mode == "llm":
            from ..cleanup import TranscriptCleaner
            c = TranscriptCleaner(self.cleanup_mode, cleanup_model,
                                  notifier=lambda m, level="INFO": None,
                                  observer=None)
            self.cleanup_state = "loading"
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "loading",
                        "model_id": cleanup_model})
            try:
                with _capture_stderr():
                    c.load()
            except Exception as e:
                # Load failure leaves the cleaner in basic-fallback mode —
                # a degraded engine, not a dead one (S09).
                self._load_error["cleanup"] = f"{type(e).__name__}"
                self.cleaner = c
                self.cleanup_state = "failed"
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "cleanup", "state": "failed",
                            "model_id": cleanup_model,
                            "reason_code": "cleanup_engine_load_failed",
                            "error_type": _safe_type(type(e).__name__)})
                return
            if c.load_failed:
                # TranscriptCleaner.load() swallows its own model errors and
                # falls back to basic — surface that honestly as a failed
                # engine instead of "ready".
                self._load_error["cleanup"] = "CleanupModelLoadError"
                self.cleaner = c
                self.cleanup_state = "failed"
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "cleanup", "state": "failed",
                            "model_id": cleanup_model,
                            "reason_code": "cleanup_engine_failed"})
                return
            self.cleaner = c
            self.cleanup_state = "ready"
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "ready",
                        "model_id": cleanup_model})
        else:
            if self.cleaner is None:
                self.cleaner = self._plain_cleaner()
            self.cleanup_state = "ready"
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "ready",
                        "reason_code": "not_llm_mode"})

    def _plain_cleaner(self):
        from ..cleanup import TranscriptCleaner
        return TranscriptCleaner(
            self.cleanup_mode, self._cleanup_model,
            notifier=lambda m, level="INFO": None, observer=None)

    # ---- stages ------------------------------------------------------------

    def _audio_path(self, name):
        if not isinstance(name, str) or not _SAFE_NAME.match(name) \
                or name in (".", ".."):
            raise InputError("unsafe_audio_reference")
        path = os.path.abspath(os.path.join(self.audio_root, name))
        if os.path.dirname(path) != self.audio_root:
            raise InputError("unsafe_audio_reference")
        return path

    def _read_input(self, name):
        """Open the parent's input by NAME under the fixed root without
        following a symlink, refuse anything that is not a regular file
        (a FIFO can no longer block the decoder), and read the bytes from
        that one descriptor (M03-AUDIT-14)."""
        path = self._audio_path(name)
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_CLOEXEC", 0))
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            raise InputError("audio_missing")
        except OSError as e:
            if e.errno in (errno.ELOOP, errno.EMLINK):
                raise InputError("audio_symlink_refused")
            if e.errno == errno.EISDIR:
                raise InputError("audio_not_regular_file")
            raise InputError("audio_unreadable")
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise InputError("audio_not_regular_file")
            if st.st_size > MAX_AUDIO_BYTES:
                raise InputError("audio_too_large")
            chunks = []
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(fd)
        from .store import WavFormatError, WavIncompleteError
        try:
            return parse_wav_f32(raw)
        except WavIncompleteError:
            raise InputError("audio_incomplete")
        except WavFormatError:
            raise InputError("audio_invalid")

    def _transcribe(self, msg):
        samples, rate = self._read_input(
            (msg.get("audio") or {}).get("name", ""))
        declared = msg.get("sample_rate")
        if declared is not None and declared != rate:
            # The parent's claim and the retained bytes disagree: never
            # relabel a rate (M03-AUDIT-09).
            raise InputError("audio_rate_mismatch")
        model_rate = getattr(self.transcriber, "model_sample_rate", None)
        model_rate = model_rate() if callable(model_rate) else None
        if model_rate and rate != model_rate:
            # No implicit resampling: an explicit refusal instead of a
            # transcript of mis-rated audio.
            raise InputError("audio_unsupported_rate")
        t0 = time.monotonic()
        text = self.transcriber.transcribe(samples)
        elapsed = round((time.monotonic() - t0) * 1000.0, 1)
        _write_msg({
            "v": PROTOCOL_VERSION, "op": "result", "kind": "asr",
            "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
            "attempt": msg.get("attempt"), "generation": msg.get("generation"),
            "text": text, "duration_ms": elapsed,
            "sample_count": int(samples.size), "sample_rate": int(rate),
            "decode_ranges": getattr(self.transcriber,
                                     "last_decode_ranges", None),
        })

    def _clean(self, msg):
        raw_text = msg.get("raw_text") or ""
        if self.cleanup_engine is not None:
            self._clean_v2(msg, raw_text)
            return
        if self._v2_load_failed:
            self._v2_unchanged(msg, raw_text, "load_failed", None)
            return
        observations = []
        # Request-scoped sink: warmup generations attach to nothing and
        # observations from one request can never leak into another job.
        self.cleaner.observer = observations.append
        try:
            t0 = time.monotonic()
            text = self.cleaner.clean(raw_text)
            elapsed = round((time.monotonic() - t0) * 1000.0, 1)
            out = {
                "v": PROTOCOL_VERSION, "op": "result", "kind": "clean",
                "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
                "attempt": msg.get("attempt"),
                "generation": msg.get("generation"),
                "text": text, "duration_ms": elapsed,
                "path": getattr(self.cleaner, "last_path", None),
                "fallback_reason": getattr(self.cleaner,
                                           "last_fallback_reason", None),
                "observations": observations,
            }
            if getattr(self.cleaner, "last_runtime_error", None):
                # A generation EXCEPTION (not a semantic rejection) fell
                # back to basic: the text is preserved, the process is
                # retired by the supervisor (M03-AUDIT-06).
                out["retire_generation"] = True
                out["runtime_error_type"] = _safe_type(
                    self.cleaner.last_runtime_error)
            _write_msg(out)
        finally:
            self.cleaner.observer = None

    def _clean_now(self, msg):
        """Control-thread answer while the cleanup model is not usable yet
        (basic-now, M03-AC04): CPU only, never touches a model object the
        GPU thread may be loading, labeled with the path that produced
        it."""
        raw_text = msg.get("raw_text") or ""
        if self.cleanup_mode == "llm" \
                and self.cleanup_implementation == "v2":
            self._v2_unchanged(msg, raw_text, "not_ready", None,
                               fallback_reason="cleanup_not_ready")
            return
        from ..cleanup import basic_cleanup
        _write_msg({
            "v": PROTOCOL_VERSION, "op": "result", "kind": "clean",
            "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
            "attempt": msg.get("attempt"),
            "generation": msg.get("generation"),
            "text": basic_cleanup(raw_text) if self.cleanup_mode != "off"
            else raw_text,
            "duration_ms": 0.0,
            "path": "basic" if self.cleanup_mode != "off" else "raw",
            "fallback_reason": "cleanup_not_ready"
            if self.cleanup_mode == "llm" else None,
            "observations": [],
        })

    def _v2_unchanged(self, msg, raw_text, kind, error, *,
                      fallback_reason="cleanup_engine_failed",
                      retire=False):
        """The V2 failure answer: the normalized input exactly as
        received — protected literals, quotes and code bytes included —
        labeled honestly (never "llm")."""
        out = {
            "v": PROTOCOL_VERSION, "op": "result", "kind": "clean",
            "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
            "attempt": msg.get("attempt"),
            "generation": msg.get("generation"),
            "text": raw_text, "duration_ms": 0.0,
            "path": "llm_fallback_normalized",
            "fallback_reason": fallback_reason,
            "observations": [],
            "v2": {"stage": "normalized", "incomplete": False,
                   "termination": {"kind": "engine_error"
                                   if kind != "not_ready"
                                   else "engine_not_ready"},
                   "failure": kind, "error": error},
        }
        if retire:
            out["retire_generation"] = True
        _write_msg(out)

    def _clean_v2(self, msg, raw_text):
        """M07 faithful cleanup (S13–S14): the V2 engine with permitted
        context (protected spans, scoped vocabulary, destination
        profile). A load failure answers through ``_v2_unchanged``; so
        does an in-flight engine exception — which additionally retires
        the generation: an exception escaping the engine is a runtime
        failure, not a semantic rejection (validation rejections are
        results inside the engine)."""
        try:
            t0 = time.monotonic()
            result = self.cleanup_engine.clean(
                raw_text,
                destination_profile=msg.get("destination_profile"),
                locale=msg.get("locale") or "en-US",
                relevant_vocabulary=msg.get("relevant_vocabulary") or [],
                protected_spans=[tuple(s)
                                 for s in msg.get("protected_spans") or []],
                vocabulary_pairs=[tuple(p)
                                  for p in msg.get("vocabulary_pairs") or []],
            )
            elapsed = round((time.monotonic() - t0) * 1000.0, 1)
            meta = {k: v for k, v in result.to_json().items()
                    if k not in ("text", "observations")}
            _write_msg({
                "v": PROTOCOL_VERSION, "op": "result", "kind": "clean",
                "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
                "attempt": msg.get("attempt"),
                "generation": msg.get("generation"),
                "text": result.text, "duration_ms": elapsed,
                "path": result.path,
                "fallback_reason": result.fallback_reason,
                "observations": result.observations,
                "v2": meta,
            })
        except Exception as e:
            self._v2_unchanged(msg, raw_text, "in_flight",
                               _safe_type(type(e).__name__), retire=True)

    def _transform(self, msg):
        """M11 (S16): one bounded transform generation on the loaded
        cleanup model. The parent validates coverage and decides
        application — this side only renders the prompt (contract
        system message + few-shot + structured payload, built in the
        transforms package) and runs the generation with recorded
        sampling."""
        from .transforms import engine as tf_engine
        try:
            job = tf_engine.TransformJob(
                transform_id=msg.get("transform_id") or "",
                transform_revision=int(msg.get("transform_revision") or 1),
                prompt_revision=msg.get("prompt_revision") or "",
                mode=msg.get("mode") or "custom",
                source=msg.get("source") or "",
                source_kind=msg.get("source_kind") or "selection",
                instructions=msg.get("instructions") or "",
                examples_revision=msg.get("examples_revision") or "",
                examples=tuple(
                    tuple(ex) for ex in msg.get("examples") or []),
                locale=msg.get("locale") or "en-US")
            result = tf_engine.run_transform(
                job, self._cleanup_generate, self._cleanup_render)
        except ValueError as e:
            # e.g. an oversized selection refused honestly (S16) —
            # reported as a refusal, not a fault.
            _write_msg({
                "v": PROTOCOL_VERSION, "op": "result",
                "kind": "transform", "req_id": msg.get("req_id"),
                "job_id": msg.get("job_id"),
                "attempt": msg.get("attempt"),
                "generation": msg.get("generation"),
                "refused": str(e)[:160],
            })
            return
        _write_msg({
            "v": PROTOCOL_VERSION, "op": "result",
            "kind": "transform", "req_id": msg.get("req_id"),
            "job_id": msg.get("job_id"), "attempt": msg.get("attempt"),
            "generation": msg.get("generation"),
            "result": result.to_json(),
            "output": result.output,
            "coverage": [c.to_json() for c in result.coverage],
            "review_excerpts": list(result.review_excerpts),
            "task_manifest": result.job.task_manifest(),
            # Content-bearing: the exact rendered prompt rides the
            # message only so the parent can retain it as a
            # lease-governed artifact (never an envelope field).
            "prompt": result.prompt,
        })

    # ---- scheduling (M03-AUDIT-07) --------------------------------------------

    def _enqueue(self, kind, msg):
        with self._cond:
            self._tasks.append((kind, msg))
            self._cond.notify_all()

    def _next_task(self):
        """The GPU thread's next unit of work. Order: the ASR load; then
        queued requests (FIFO) — except that a request needing the cleanup
        engine first runs the pending cleanup load; the cleanup load
        itself runs when nothing is queued, unless a spawn made for a
        waiting request deferred it until that request arrived."""
        with self._cond:
            while True:
                if self._stopping:
                    return None
                if "load_asr" in self._loads:
                    self._loads.remove("load_asr")
                    return ("load_asr", None)
                if self._tasks:
                    kind, msg = self._tasks[0]
                    if kind == "transform" \
                            and "load_cleanup" in self._loads:
                        self._loads.remove("load_cleanup")
                        return ("load_cleanup", None)
                    return self._tasks.pop(0)
                if "load_cleanup" in self._loads and (
                        not self._defer_cleanup or self._request_seen):
                    self._loads.remove("load_cleanup")
                    return ("load_cleanup", None)
                self._cond.wait(0.5)

    def _gpu_loop(self):
        while True:
            task = self._next_task()
            if task is None:
                return
            kind, msg = task
            try:
                if kind == "load_asr":
                    if not self._load_asr():
                        with self._cond:
                            # No ASR: cleanup is never loaded either (the
                            # pre-split behavior), but requests queued for
                            # it are answered, not stranded.
                            if "load_cleanup" in self._loads:
                                self._loads.remove("load_cleanup")
                            self.cleanup_state = "failed"
                elif kind == "load_cleanup":
                    self._load_cleanup()
                elif kind == "transcribe":
                    if self.transcriber is None:
                        raise EngineNotReady("asr_engine_not_ready")
                    self._transcribe(msg)
                elif kind == "clean":
                    self._clean(msg)
                elif kind == "transform":
                    if self._cleanup_generate is None:
                        raise EngineNotReady("cleanup_engine_not_ready")
                    self._transform(msg)
            except ProtocolError as e:
                _fault(msg or {}, type(e).__name__, e.code, e.fault_class)
            except Exception as e:
                _fault(msg or {}, type(e).__name__, "stage_exception",
                       "runtime")

    def _dispatch(self, msg):
        op = msg.get("op")
        if op == "load":
            with self._cond:
                self._configure(msg)
                self._defer_cleanup = bool(
                    msg.get("defer_cleanup_until_request"))
                if self.cleanup_mode != "llm":
                    # Model-free cleanup is ready as soon as configured.
                    self.cleaner = self._plain_cleaner()
                self._loads = ["load_asr", "load_cleanup"]
                self._cond.notify_all()
            return
        if op not in ("transcribe", "clean", "transform"):
            raise ProtocolError("unknown_op")
        _validate(msg)
        with self._cond:
            self._request_seen = True
            self._cond.notify_all()
        if op == "transcribe":
            if self.asr_state == "failed":
                raise EngineNotReady("asr_engine_failed")
            self._enqueue("transcribe", msg)
            return
        if op == "clean":
            if self.cleanup_state == "ready" \
                    or self.cleanup_mode != "llm":
                self._enqueue("clean", msg)
            elif self.cleanup_state == "failed":
                # A failed engine's degraded answer runs on the GPU
                # thread's order too (it may still need the v1 cleaner
                # object, which only that thread touches).
                self._enqueue("clean", msg)
            else:
                self._clean_now(msg)
            return
        if self.cleanup_state == "failed" or (
                self.cleanup_mode != "llm"
                or self.cleanup_implementation != "v2"):
            raise EngineNotReady("cleanup_engine_not_ready")
        self._enqueue("transform", msg)

    # ---- loop ----------------------------------------------------------------

    def serve(self):
        gpu = threading.Thread(target=self._gpu_loop, daemon=True,
                               name="localflow-worker-gpu")
        gpu.start()
        try:
            while True:
                try:
                    msg = _read_msg(0)
                except ProtocolError as e:
                    # Well framed, invalid body: refuse it, keep reading.
                    _fault(e.request or {}, "ProtocolError", e.code,
                           e.fault_class)
                    continue
                except (EOFError, _FramingError, OSError):
                    return 0
                if msg.get("op") == "shutdown":
                    return 0
                try:
                    self._dispatch(msg)
                except ProtocolError as e:
                    _fault(msg, type(e).__name__, e.code, e.fault_class)
                except Exception as e:
                    _fault(msg, type(e).__name__, "stage_exception",
                           "runtime")
        finally:
            # Queued work is abandoned (the parent already refused it);
            # the operation in progress finishes before the process exits.
            with self._cond:
                self._stopping = True
                self._tasks.clear()
                self._cond.notify_all()
            gpu.join()


def _safe_type(name):
    return name if isinstance(name, str) and _TYPE.match(name) else \
        "Exception"


def _fault(req, error_type, reason_code, fault_class="runtime"):
    """A structured fault. ``reason_code`` must be a controlled token;
    anything else (exception text, a path, a transcript) is replaced —
    truncation is not redaction (M03-AUDIT-12)."""
    code = reason_code if isinstance(reason_code, str) \
        and _CODE.match(reason_code) else "stage_exception"
    _write_msg({"v": PROTOCOL_VERSION, "op": "fault",
                "req_id": req.get("req_id")
                if isinstance(req.get("req_id"), str) else None,
                "job_id": req.get("job_id")
                if isinstance(req.get("job_id"), str) else None,
                "stage": req.get("op") if req.get("op") in (
                    "transcribe", "clean", "transform", "load") else None,
                "error_type": _safe_type(str(error_type)),
                "reason_code": code, "fault_class": fault_class})


def _reason(e) -> str:
    """Content-free reason for an exception (S07): a controlled code only.
    The exception class travels separately as ``error_type``; its message
    never leaves this process."""
    return "stage_exception"


class _capture_stderr:
    """Swap stderr into a bounded sink around model loads; report a
    content-free diag record (bytes, truncated flag) afterwards."""

    def __enter__(self):
        self._saved = sys.stderr
        self._sink = _BoundedStderr()
        sys.stderr = self._sink
        return self._sink

    def __exit__(self, exc_type, exc, tb):
        sys.stderr = self._saved
        if self._sink.total:
            _write_msg({"v": PROTOCOL_VERSION, "op": "diag",
                        "kind": "third_party_stderr",
                        "bytes": self._sink.total,
                        "truncated": self._sink.truncated})
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="localflow.v2.worker")
    ap.add_argument("--audio-root", required=True)
    args = ap.parse_args(argv)
    # The protocol stream is the only thing allowed on fd 1.
    sys.stdout = sys.stderr
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    _write_msg({"v": PROTOCOL_VERSION, "op": "hello", "pid": os.getpid(),
                "protocol": PROTOCOL_VERSION,
                "python": sys.version.split()[0]})
    return Worker(args.audio_root).serve()


if __name__ == "__main__":
    raise SystemExit(main())
