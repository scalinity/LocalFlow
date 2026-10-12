"""Run a cleanup model through LocalFlow's real engine and validator.

Each model runs in its own process (``python -m lfx.evaluate run KEY``). The
generate function reproduces ``localflow.v2.cleanup.model.ModelRunner``
exactly (greedy ``stream_generate``; every yield counts toward
``max_tokens``) and adds first-token and per-role timing. Rendering is the
production ``ModelRunner.render`` (``enable_thinking=False``).

Per case it records the model-only proposals (depth-0 pass outputs), the
delivered text/path/fallback, salvage, timings and, for cases with gold
corrections, a teacher-forced main pass (gold corrections applied, real
model main pass).
"""

from __future__ import annotations

import gc
import json
import os
import re
import sys
import time
from pathlib import Path

from .common import ART, CONFIG, read_json, read_jsonl, utc_now, write_json

EVAL_DIR = ART / "eval"


def model_path(key: str) -> Path:
    from .capture import snapshot
    m = CONFIG["models"][key]
    if key == "C":
        info = read_json(ART / "export" / "C_identity.json")
        return Path(info["snapshot_path"])
    return snapshot(m["repository_id"], m["revision"])


class Runner:
    def __init__(self, key: str, path: Path | None = None):
        self.key = key
        self.path = Path(path) if path else model_path(key)
        self.calls: list = []

    def load(self) -> dict:
        import mlx.core as mx
        from localflow.v2.cleanup.model import ModelRunner
        self.mx = mx
        mx.reset_peak_memory()
        t0 = time.perf_counter()
        self.mr = ModelRunner(str(self.path))
        self.mr.load()                         # production load + 8-token warmup
        self.load_ms = (time.perf_counter() - t0) * 1000
        self.tokenizer = self.mr._tokenizer
        return {"load_ms": self.load_ms, "template_revision": self.mr.template_revision,
                "peak_after_load_bytes": mx.get_peak_memory()}

    def render(self, messages):
        return self.mr.render(messages)

    def generate(self, prompt: str, max_tokens: int) -> dict:
        from mlx_lm.generate import stream_generate
        from mlx_lm.sample_utils import make_sampler
        t0 = time.perf_counter()
        first, text, tokens, finish = None, "", 0, None
        for r in stream_generate(self.mr._model, self.tokenizer, prompt=prompt, max_tokens=max_tokens,
                                 sampler=make_sampler(temp=0.0)):
            if first is None:
                first = (time.perf_counter() - t0) * 1000
            text += r.text
            tokens += 1
            finish = r.finish_reason
        self.calls.append({"first_token_ms": first, "generation_ms": (time.perf_counter() - t0) * 1000,
                           "yields": tokens, "max_tokens": max_tokens, "finish_reason": finish,
                           "prompt_tokens": None})
        return {"text": text, "output_tokens": tokens, "limit_hit": tokens >= max_tokens, "prompt": prompt}

    def engine(self):
        from localflow.v2.cleanup.engine import CleanupEngine
        return CleanupEngine(self.generate, model_id=str(self.path), render_fn=self.render,
                             template_revision=self.mr.template_revision)

    def clean(self, case: dict) -> dict:
        """Delivered + model-only record for one case (engine path)."""
        from localflow.v2.cleanup import engine as module
        self.calls = []
        validation_ms = [0.0]
        original = module.validate

        def timed_validate(*a, **k):
            t = time.perf_counter()
            r = original(*a, **k)
            validation_ms[0] += (time.perf_counter() - t) * 1000
            return r

        module.validate = timed_validate
        t0 = time.perf_counter()
        error = None
        try:
            result = self.engine().clean(
                case["model_input"], locale="en-US", destination_profile=case.get("destination_profile"),
                relevant_vocabulary=case.get("relevant_vocabulary") or [],
                protected_spans=[tuple(s) for s in case.get("protected_spans") or []],
                vocabulary_pairs=tuple(tuple(p) for p in case.get("vocabulary_pairs") or []))
        except Exception as exc:
            result, error = None, f"{type(exc).__name__}: {exc}"[:300]
        finally:
            module.validate = original
        total_ms = (time.perf_counter() - t0) * 1000
        rec = {"case_id": case["case_id"], "model": self.key, "error": error, "total_cleanup_ms": total_ms,
               "validation_ms": validation_ms[0]}
        if result is None:
            rec.update(delivered=case["model_input"], path="error", model_only=None)
            return rec
        passes = [o for o in result.observations if o.get("kind") in ("corrections", "cleanup")]
        for o, c in zip(passes, self.calls):
            c["role"] = o["kind"]
            c["depth"] = o.get("depth", 0)
        main0 = next((o for o in passes if o["kind"] == "cleanup" and o.get("depth", 0) == 0), None)
        corr0 = next((o for o in passes if o["kind"] == "corrections" and o.get("depth", 0) == 0), None)
        raw_main = main0["output"] if main0 else None
        decisions = [o for o in result.observations if o.get("kind") == "cleanup_decision"]
        selected = []
        for o in result.observations:
            if o.get("kind") == "corrections_applied":
                for p in o["proposals"]:
                    if p.get("status") == "selected" and p.get("span"):
                        selected.append([p["span"][0] + o["window_range"][0], p["span"][1] + o["window_range"][0]])
        rec.update(
            delivered=result.text, path=result.path, fallback_reason=result.fallback_reason,
            incomplete=result.incomplete, windows=result.termination.get("windows"),
            limit_hits=result.termination.get("limit_hits"),
            salvaged_words=sum(d.get("salvaged_words", 0) for d in decisions),
            validator_failures=sorted({c["name"] for d in decisions for c in d["validation"].get("components", [])
                                       if c.get("status") == "fail"}) if decisions else [],
            model_only=postprocess(raw_main, case["model_input"]) if raw_main is not None else None,
            model_only_raw=raw_main, corrections_raw=corr0["output"] if corr0 else None,
            corrections_selected=selected,
            corrections_applied=result.corrections.get("applied"), corrections_rejected=result.corrections.get("rejected"),
            think_leak=bool(raw_main and "<think>" in raw_main),
            calls=[{k: c.get(k) for k in ("role", "depth", "first_token_ms", "generation_ms", "yields",
                                          "max_tokens", "finish_reason")} for c in self.calls],
        )
        rec["first_token_ms"] = self.calls[0]["first_token_ms"] if self.calls else None
        rec["generation_ms"] = sum(c["generation_ms"] for c in self.calls)
        rec["main_generation_ms"] = sum(c["generation_ms"] for c in self.calls if c.get("role") == "cleanup")
        rec["corrections_generation_ms"] = sum(c["generation_ms"] for c in self.calls if c.get("role") == "corrections")
        return rec

    def teacher_forced(self, case: dict) -> dict | None:
        """Gold corrections, real main pass (isolates main-pass quality)."""
        from .capture import capture
        if not case.get("gold_lines"):
            return None
        self.calls = []
        pair = {**case, "pair_id": case["case_id"]}
        c = capture(pair, render_override=self.render, main_answer=self.generate)
        main = next((x for x in c["calls"] if x["role"] == "main"), None)
        return {"delivered": c.get("delivered"), "path": c.get("path"),
                "model_only": postprocess(main["completion"], case["model_input"]) if main else None,
                "reject": c["reject"]}

    def unload(self):
        self.mr = None
        gc.collect()
        self.mx.clear_cache()


def postprocess(out: str, source: str) -> str:
    """The engine's own reply cleanup (strip, drop a leading think block,
    unwrap one pair of whole-reply quotes unless the source is quoted)."""
    out = (out or "").strip()
    out = re.sub(r"(?s)^\s*<think>.*?</think>\s*", "", out).strip()
    src = source.strip()
    if len(out) >= 2 and out[0] == out[-1] == '"' and not (src[:1] == src[-1:] == '"'):
        out = out[1:-1].strip()
    return out


# ---------------------------------------------------------------- process entry points

def run_cases(key: str, cases: list[dict], out_name: str, path: str | None = None,
              teacher_forced: bool = True) -> dict:
    import mlx.core as mx
    out_path = EVAL_DIR / f"{out_name}.jsonl"
    done = {r["case_id"] for r in read_jsonl(out_path)}
    todo = [c for c in cases if c["case_id"] not in done]
    r = Runner(key, path)
    info = r.load()
    meta_path = EVAL_DIR / f"{out_name}.meta.json"
    meta = read_json(meta_path, {"runs": []})
    meta["runs"].append({"started": utc_now(), "model_path": str(r.path), "load": info,
                         "cases_todo": len(todo), "python": sys.version.split()[0],
                         "mlx": mx.__version__, "pid": os.getpid()})
    write_json(meta_path, meta)
    with open(out_path, "a") as fh:
        for i, case in enumerate(todo):
            rec = r.clean(case)
            if teacher_forced and case.get("gold_lines"):
                rec["teacher_forced"] = r.teacher_forced(case)
            rec["peak_mem_bytes"] = mx.get_peak_memory()
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
    meta["runs"][-1].update(finished=utc_now(), peak_mem_bytes=mx.get_peak_memory())
    write_json(meta_path, meta)
    r.unload()
    return {"done": len(todo)}


def cold_load(key: str, path: str | None = None) -> dict:
    t0 = time.perf_counter()
    import mlx.core as mx
    r = Runner(key, path)
    info = r.load()
    return {"model": key, "process_to_ready_ms": (time.perf_counter() - t0) * 1000, "load_ms": info["load_ms"],
            "peak_after_load_bytes": info["peak_after_load_bytes"]}


def pipeline_replay(key: str, case_ids: list[str], warmups: int, repeats: int, path: str | None = None) -> list[dict]:
    """Audio -> Parakeet -> normalize -> protected spans -> cleanup, one
    process with both models resident (as in the worker)."""
    import soundfile as sf
    from huggingface_hub import snapshot_download
    from localflow.stt import Transcriber
    from localflow.v2.normalize import normalize, NormalizationPolicy, ContextSnapshot
    from localflow.v2.cleanup import protected_spans_for_cleanup
    cases = {c["case_id"]: c for c in read_jsonl(ART / "real" / "cases.jsonl")}
    asr_cfg = CONFIG["models"]["asr"]
    t = Transcriber(snapshot_download(asr_cfg["repository_id"], revision=asr_cfg["revision"], local_files_only=True))
    t.load()
    r = Runner(key, path)
    r.load()
    policy = NormalizationPolicy()
    rows = []
    for cid in case_ids:
        samples, _ = sf.read(str(ART / cases[cid]["audio_path"]), dtype="float32")
        for rep in range(warmups + repeats):
            t0 = time.perf_counter()
            raw = t.transcribe(samples)
            t1 = time.perf_counter()
            norm = normalize(raw, policy, ContextSnapshot())
            spans = protected_spans_for_cleanup(raw, norm.text, norm.protected, norm.edits)
            t2 = time.perf_counter()
            rec = r.clean({"case_id": cid, "model_input": norm.text, "protected_spans": spans})
            t3 = time.perf_counter()
            if rep >= warmups:
                rows.append({"case_id": cid, "model": key, "repeat": rep - warmups,
                             "asr_ms": (t1 - t0) * 1000, "normalize_ms": (t2 - t1) * 1000,
                             "generation_ms": rec.get("generation_ms"), "validation_ms": rec.get("validation_ms"),
                             "cleanup_ms": rec["total_cleanup_ms"], "pipeline_ms": (t3 - t0) * 1000,
                             "audio_s": len(samples) / 16000, "path": rec.get("path")})
    return rows


if __name__ == "__main__":
    cmd, key = sys.argv[1], sys.argv[2]
    path = os.environ.get("LFX_MODEL_PATH")
    if cmd == "run":
        cases = read_jsonl(Path(sys.argv[3]))
        tf = os.environ.get("LFX_TEACHER_FORCED", "1") == "1"
        print(json.dumps(run_cases(key, cases, sys.argv[4], path, teacher_forced=tf)))
    elif cmd == "cold":
        print("COLD " + json.dumps(cold_load(key, path)))
    elif cmd == "pipeline":
        ids = json.loads(Path(sys.argv[3]).read_text())
        rows = pipeline_replay(key, ids, CONFIG["evaluation"]["pipeline_warmups"],
                               CONFIG["evaluation"]["pipeline_repeats"], path)
        from .common import write_jsonl
        write_jsonl(EVAL_DIR / f"pipeline-{key}.jsonl", rows)
        print(json.dumps({"rows": len(rows)}))
