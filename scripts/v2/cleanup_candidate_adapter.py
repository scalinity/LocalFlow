"""Benchmark-only official-template MLX adapter. One resident candidate."""
from __future__ import annotations

import gc
import json
import os
import pathlib
import re
import resource
import subprocess
import time

from cleanup_benchmark import (TemplateError, digest, file_hash, require,
                               resolve_cache, runtime_versions, validate_memory)


def system_memory():
    try:
        raw = subprocess.check_output(["vm_stat"], text=True)
        page = int(re.search(r"page size of (\d+) bytes", raw)[1])
        fields = {k.strip('" '): int(v) for k, v in re.findall(r"^([^:]+):\s+(\d+)\.", raw, re.M)}
        # Reclaimable estimate, not physical free RAM or guaranteed allocation headroom.
        available = page * sum(fields.get(k, 0) for k in
                               ("Pages free", "Pages inactive", "Pages speculative"))
        return {"system_available_bytes": available, "swapouts": fields.get("Swapouts")}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return {"system_available_bytes": None, "swapouts": None}


def memory_snapshot(mx=None):
    try:
        rss = int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())], text=True)) * 1024
    except (OSError, subprocess.SubprocessError, ValueError):
        rss = None
    memory = {"mechanism": "ps_rss+resource_ru_maxrss+mlx_allocator+vm_stat",
              "rss_bytes": rss, "rss_peak_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
              "mlx_active_bytes": int(mx.get_active_memory()) if mx else None,
              "mlx_cache_bytes": int(mx.get_cache_memory()) if mx else None,
              "mlx_peak_bytes": int(mx.get_peak_memory()) if mx else None,
              "system_available_bytes": system_memory()["system_available_bytes"],
              "missing_reason": "allocator_not_loaded_or_system_probe_unavailable"}
    return validate_memory(memory)


class CandidateAdapter:
    def __init__(self, candidate):
        self.candidate = candidate
        self.model = self.tokenizer = self.mx = None
        self.calls = []
        self.validation_ms = 0.0
        self.validation_reports = []
        self.asr = None
        self.identity = {}

    def load(self):
        from mlx_lm import load
        import mlx.core as mx
        self.mx = mx
        self.baseline = memory_snapshot(mx)
        # Honest allocation guard on this benchmark process; no simultaneous candidates.
        total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))
        mx.set_memory_limit(int(total * .72))
        mx.set_cache_limit(256 * 1024**2)
        mx.reset_peak_memory()
        path = resolve_cache(self.candidate)
        started = time.perf_counter()
        self.model, self.tokenizer = load(str(path))
        mx.eval(self.model.parameters())
        mx.synchronize()
        self.cold_load_ms = (time.perf_counter() - started) * 1000
        template = self.tokenizer.chat_template
        if not template:
            raise TemplateError("official template missing")
        self.identity = {"candidate_id": self.candidate["candidate_id"],
                         "repository_id": self.candidate["repository_id"],
                         "immutable_revision": self.candidate["immutable_revision"],
                         "quantization": self.candidate["quantization"],
                         "runtime": runtime_versions(), "chat_template_sha256": digest(template),
                         "config_sha256": file_hash(path / "config.json"),
                         "reasoning_mode": "direct", "text_only": True,
                         "speculative_decoding": False}
        probe = self.render([{"role": "system", "content": "probe"}, {"role": "user", "content": "café"}])
        require("probe" in probe and "café" in probe, "template lost system/user Unicode")
        self.loaded_idle = memory_snapshot(mx)
        return {"identity": self.identity, "cold_load_ms": self.cold_load_ms,
                "baseline": self.baseline, "loaded_idle": self.loaded_idle,
                "template_result": "PASS", "direct_mode_control": "enable_thinking=False"}

    def render(self, messages):
        try:
            return self.tokenizer.apply_chat_template(messages, tokenize=False,
                        add_generation_prompt=True, enable_thinking=False)
        except Exception as exc:
            raise TemplateError("official template rejected semantic messages") from exc

    def generate(self, prompt, max_tokens):
        from mlx_lm.generate import stream_generate
        from mlx_lm.sample_utils import make_sampler
        started = time.perf_counter()
        first = None
        text, tokens, finish = "", 0, None
        for response in stream_generate(self.model, self.tokenizer, prompt=prompt,
                max_tokens=max_tokens, sampler=make_sampler(temp=0.0)):
            if first is None:
                first = (time.perf_counter() - started) * 1000
            text += response.text
            tokens = response.generation_tokens
            finish = response.finish_reason
        elapsed = (time.perf_counter() - started) * 1000
        # No model-specific output repair or prompt tuning in the primary comparison.
        if any(tag in text for tag in ("<think>", "</think>", "<|channel>thought", "<|think|>")):
            raise TemplateError("reasoning contamination in direct response")
        self.calls.append({"first_token_ms": first, "generation_ms": elapsed,
                           "output_tokens": tokens, "finish_reason": finish})
        return {"text": text, "output_tokens": tokens,
                "limit_hit": finish == "length" or tokens >= max_tokens, "prompt": prompt}

    def clean(self, source, case, protected=None):
        from localflow.v2.cleanup import engine as module
        from localflow.v2.cleanup import prompts
        self.calls = []
        self.validation_ms = 0.0
        self.validation_reports = []
        self.last_protected = protected if protected is not None else case.get("protected_spans", [])
        original = module.validate

        def timed_validate(*args, **kwargs):
            t = time.perf_counter()
            report = original(*args, **kwargs)
            self.validation_ms += (time.perf_counter() - t) * 1000
            self.validation_reports.append(report.to_json())
            return report

        module.validate = timed_validate  # instrumentation only, private subprocess lifetime
        try:
            engine = module.CleanupEngine(self.generate, model_id=self.candidate["repository_id"],
                        render_fn=self.render, template_revision=self.identity["chat_template_sha256"])
            started = time.perf_counter()
            result = engine.clean(source, locale=case.get("locale", "en-US"),
                        destination_profile=case.get("destination_profile"),
                        relevant_vocabulary=case.get("relevant_vocabulary", []),
                        protected_spans=self.last_protected,
                        vocabulary_pairs=tuple(tuple(p) for p in case.get("vocabulary_pairs", [])))
            elapsed = (time.perf_counter() - started) * 1000
        finally:
            module.validate = original
        identity = {**self.identity, "cleanup_prompt_sha256": digest((prompts.CONTRACT + prompts.prompt_revision()).encode()),
                    "cleanup_prompt_revision": prompts.prompt_revision(),
                    "correction_prompt_revision": module.corrections_prompt_revision(),
                    "correction_prompt_sha256": digest((module.CORRECTIONS_INSTRUCTION +
                                            json.dumps(module.CORRECTIONS_EXAMPLES)).encode())}
        timing = {"first_token": self.calls[0]["first_token_ms"] if self.calls else None,
                  "generation": sum(c["generation_ms"] for c in self.calls),
                  "validation": self.validation_ms, "cleanup": elapsed,
                  "asr": None, "normalization": None, "end_to_end": None}
        return result, timing, identity

    def load_asr(self, corpus):
        from localflow.stt import Transcriber
        candidate = corpus.get("asr", {})
        require(candidate.get("repository_id") and candidate.get("immutable_revision"), "ASR identity required")
        path = resolve_cache(candidate, tokenizer_required=False)
        self.asr = Transcriber(str(path))
        self.asr.load()
        self.asr_identity = {"repository_id": candidate["repository_id"],
                             "immutable_revision": candidate["immutable_revision"]}

    def audio_replay(self, audio, case):
        import numpy as np
        import soundfile as sf
        from localflow.v2.normalize import normalize, NormalizationPolicy, ContextSnapshot
        from localflow.v2.cleanup import protected_spans_for_cleanup
        started = time.perf_counter()
        samples, rate = sf.read(str(audio), dtype="float32", always_2d=True)
        require(samples.shape[1] == 1 and rate == self.asr.model_sample_rate(), "audio format mismatch")
        require(np.isfinite(samples).all(), "nonfinite audio")
        t = time.perf_counter()
        raw = self.asr.transcribe(samples[:, 0])
        asr_ms = (time.perf_counter() - t) * 1000
        policy = NormalizationPolicy(**case.get("normalization_policy", {}))
        context = ContextSnapshot(**case.get("normalization_context", {}))
        t = time.perf_counter()
        normalized = normalize(raw, policy, context)
        normalize_ms = (time.perf_counter() - t) * 1000
        protected = protected_spans_for_cleanup(raw, normalized.text, normalized.protected, normalized.edits)
        result, timing, identity = self.clean(normalized.text, case, protected)
        timing.update(asr=asr_ms, normalization=normalize_ms,
                      end_to_end=(time.perf_counter() - started) * 1000)
        identity.update(asr=self.asr_identity, normalization_revision=policy.policy_revision,
                        asr_sha256=digest(raw.encode()), normalized_sha256=digest(normalized.text.encode()))
        return normalized.text, result, timing, identity

    def unload(self):
        self.model = self.tokenizer = self.asr = None
        gc.collect()
        if self.mx:
            self.mx.synchronize()
            self.mx.clear_cache()
        return memory_snapshot(self.mx)
