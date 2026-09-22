"""Model worker subprocess (Spec S06, contracts/worker.md, M03).

A fresh process — spawned, never a fork of initialized Metal state — owns
all MLX/GPU state for ASR and cleanup. It speaks a versioned, length-framed
JSON protocol over inherited pipes (stdin/stdout):

  parent→worker : load, transcribe, clean, shutdown
  worker→parent : hello, engine, result, fault, diag

Boundaries that hold by construction:
  * The worker cannot request an insertion — no such message exists. Only
    the parent's coordinator ever issues an insertion.
  * Audio arrives as a parent-created file name under a root fixed at
    spawn; the worker refuses separators and never opens anything outside
    that root.
  * Failures are structured ``fault`` messages (exception type + stage),
    never silent; a worker that dies anyway is one more fault class to the
    supervisor.

Every message carries ``v`` (protocol version) and echoes the request's
``job_id``/``attempt``/``generation`` so stale results are detectable
(M03-AC02). Stage durations are measured with this process's monotonic
clock and reported as elapsed-ms only (S07: never compare absolute
monotonic values across processes).

Run: python -m localflow.v2.worker --audio-root <dir>
"""

import argparse
import os
import re
import sys
import time

PROTOCOL_VERSION = 1
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\Z")


class ProtocolError(Exception):
    pass


def _write_msg(msg: dict):
    import json
    data = json.dumps(msg, ensure_ascii=True).encode("utf-8")
    os.write(1, len(data).to_bytes(4, "big") + data)


def _read_exact(fd: int, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise EOFError("control pipe closed")
        buf += chunk
    return buf


def _read_msg(fd: int) -> dict:
    import json
    length = int.from_bytes(_read_exact(fd, 4), "big")
    if length <= 0 or length > 64 * 1024 * 1024:
        raise ProtocolError(f"bad frame length {length}")
    return json.loads(_read_exact(fd, length).decode("utf-8"))


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

    # ---- engines -----------------------------------------------------------

    def _load(self, msg):
        self.asr_model = msg.get("asr_model")
        self.cleanup_mode = msg.get("cleanup_mode", "off")
        cleanup_model = msg.get("cleanup_model")
        self.cleanup_implementation = msg.get("cleanup_implementation", "v2")
        # A fresh load starts from a clean engine slate (defensive: the
        # supervisor spawns a fresh process per load, so this only
        # matters for direct Worker reuse in tests).
        self.cleanup_engine = None

        from ..stt import Transcriber
        t = Transcriber(self.asr_model)

        def phase(name):
            if name == "loading":
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "asr", "state": "loading",
                            "model_id": self.asr_model})
            else:
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "asr", "state": "warming",
                            "model_id": self.asr_model})

        try:
            with _capture_stderr():
                t.load(on_phase=phase)
        except Exception as e:
            self._load_error["asr"] = f"{type(e).__name__}"
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "asr", "state": "failed",
                        "model_id": self.asr_model,
                        "reason_code": _reason(e)})
            return
        self.transcriber = t
        _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                    "engine": "asr", "state": "ready",
                    "model_id": self.asr_model})

        if self.cleanup_mode == "llm" \
                and self.cleanup_implementation == "v2":
            from .cleanup import CleanupEngine, ModelRunner
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "loading",
                        "model_id": cleanup_model})
            try:
                runner = ModelRunner(cleanup_model)
                with _capture_stderr():
                    runner.load()
                self.cleanup_engine = runner.engine()
            except Exception as e:
                # Load failure degrades to basic answers, exactly like
                # the v1 path — the engine is failed, not the worker.
                # The basic TranscriptCleaner is the degraded answerer so
                # every M03 label (path "basic", cleanup_engine_failed)
                # stays identical for both implementations.
                self._load_error["cleanup"] = f"{type(e).__name__}"
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "cleanup", "state": "failed",
                            "model_id": cleanup_model,
                            "reason_code": _reason(e)})
                from ..cleanup import TranscriptCleaner
                self.cleaner = TranscriptCleaner(
                    "basic", cleanup_model,
                    notifier=lambda m, level="INFO": None,
                    observer=None)
                return
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "ready",
                        "model_id": cleanup_model})
            return
        if self.cleanup_mode == "llm":
            from ..cleanup import TranscriptCleaner
            c = TranscriptCleaner(self.cleanup_mode, cleanup_model,
                                  notifier=lambda m, level="INFO": None,
                                  observer=None)
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
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "cleanup", "state": "failed",
                            "model_id": cleanup_model,
                            "reason_code": _reason(e)})
                self.cleaner = c
                return
            if c.load_failed:
                # TranscriptCleaner.load() swallows its own model errors and
                # falls back to basic — surface that honestly as a failed
                # engine instead of "ready".
                self._load_error["cleanup"] = "CleanupModelLoadError"
                _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                            "engine": "cleanup", "state": "failed",
                            "model_id": cleanup_model,
                            "reason_code": "cleanup_engine_failed"})
                self.cleaner = c
                return
            self.cleaner = c
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "ready",
                        "model_id": cleanup_model})
        else:
            from ..cleanup import TranscriptCleaner
            self.cleaner = TranscriptCleaner(
                self.cleanup_mode, cleanup_model,
                notifier=lambda m, level="INFO": None, observer=None)
            _write_msg({"v": PROTOCOL_VERSION, "op": "engine",
                        "engine": "cleanup", "state": "ready",
                        "reason_code": "not_llm_mode"})

    # ---- stages ------------------------------------------------------------

    def _audio_path(self, name):
        if not isinstance(name, str) or not _SAFE_NAME.match(name):
            raise ProtocolError(f"unsafe audio reference {name!r}")
        path = os.path.abspath(os.path.join(self.audio_root, name))
        if os.path.dirname(path) != self.audio_root:
            raise ProtocolError(f"audio reference escapes root: {name!r}")
        return path

    def _transcribe(self, msg):
        from .store import read_wav_f32
        path = self._audio_path((msg.get("audio") or {}).get("name", ""))
        samples, rate = read_wav_f32(path)
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
        observations = []
        # Request-scoped sink: warmup generations attach to nothing and
        # observations from one request can never leak into another job.
        self.cleaner.observer = observations.append
        try:
            t0 = time.monotonic()
            text = self.cleaner.clean(raw_text)
            elapsed = round((time.monotonic() - t0) * 1000.0, 1)
            _write_msg({
                "v": PROTOCOL_VERSION, "op": "result", "kind": "clean",
                "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
                "attempt": msg.get("attempt"),
                "generation": msg.get("generation"),
                "text": text, "duration_ms": elapsed,
                "path": getattr(self.cleaner, "last_path", None),
                "fallback_reason": getattr(self.cleaner,
                                           "last_fallback_reason", None),
                "observations": observations,
            })
        finally:
            self.cleaner.observer = None

    def _clean_v2(self, msg, raw_text):
        """M07 faithful cleanup (S13–S14): the V2 engine with permitted
        context (protected spans, scoped vocabulary, destination
        profile). A load failure never reaches here (the degraded basic
        TranscriptCleaner answers, M03-AC04 labels identical); an
        in-flight engine exception falls back to basic honestly."""
        from ..cleanup import basic_cleanup
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
            t0 = time.monotonic()
            text = basic_cleanup(raw_text)
            _write_msg({
                "v": PROTOCOL_VERSION, "op": "result", "kind": "clean",
                "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
                "attempt": msg.get("attempt"),
                "generation": msg.get("generation"),
                "text": text,
                "duration_ms": round((time.monotonic() - t0) * 1000.0, 1),
                "path": "basic",
                "fallback_reason": "cleanup_engine_failed",
                "observations": [],
                "v2": {"stage": "basic", "incomplete": False,
                       "termination": {"kind": "engine_error"},
                       "error": type(e).__name__},
            })

    # ---- loop ----------------------------------------------------------------

    def serve(self):
        while True:
            try:
                msg = _read_msg(0)
            except (EOFError, ProtocolError):
                return 0
            op = msg.get("op")
            try:
                if op == "shutdown":
                    return 0
                if op == "load":
                    self._load(msg)
                elif op == "transcribe":
                    if self.transcriber is None:
                        _fault(msg, "EngineNotReady",
                               "asr_engine_not_ready")
                    else:
                        self._transcribe(msg)
                elif op == "clean":
                    if self.cleaner is None and self.cleanup_engine is None:
                        _fault(msg, "EngineNotReady",
                               "cleanup_engine_not_ready")
                    else:
                        self._clean(msg)
                else:
                    _fault(msg, "ProtocolError", "unknown_op")
            except ProtocolError as e:
                _fault(msg, "ProtocolError", str(e))
            except Exception as e:
                _fault(msg, type(e).__name__, _reason(e))


def _fault(req, error_type, reason_code):
    _write_msg({"v": PROTOCOL_VERSION, "op": "fault",
                "req_id": req.get("req_id"), "job_id": req.get("job_id"),
                "stage": req.get("op"), "error_type": str(error_type),
                "reason_code": str(reason_code)[:120]})


def _reason(e) -> str:
    """Sanitized, content-free reason for an exception (S07)."""
    r = type(e).__name__
    msg = str(e)
    if msg:
        r += ": " + msg[:120]
    return r


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
