"""Quantized production-wrapper evaluation; model and engine are separate axes."""
from __future__ import annotations

import argparse
import gc
import json
import os
import resource
import sys
import time
import importlib.metadata
from pathlib import Path
from .common import *
from lfx.evaluate import Runner as BaseRunner, postprocess
from localflow.v2.cleanup import engine as production


class Runner(BaseRunner):
    def __init__(self, key, path=None, variant=False, updated_engine=False, recorded_f=False):
        if sum((variant, updated_engine, recorded_f)) > 1:
            raise ValueError("Choose one recorded engine or updated source")
        if key.startswith("C") and path is None:
            path = c_identity()["snapshot_path"]
        super().__init__(key, Path(path) if path else None)
        self.updated_engine = updated_engine
        self.recorded_f = recorded_f
        if variant:
            from .engine_variant import load
            self.module = load()
            self.engine_name = "separator_fix"
        elif updated_engine:
            self.module = production
            self.engine_name = "updated_source"
        elif recorded_f:
            from .baseline import load
            self.module = load(recorded_f=True)
            self.engine_name = "recorded_f"
        else:
            from .baseline import load
            self.module = load()
            self.engine_name = "production"

    def load(self):
        import mlx.core as mx
        if self.updated_engine:
            from localflow.v2.cleanup.model import ModelRunner
        else:
            from .baseline import load_runner
            ModelRunner = load_runner(self.recorded_f)
        self.mx = mx
        mx.reset_peak_memory()
        start = time.perf_counter()
        self.mr = ModelRunner(str(self.path))
        self.mr.load()
        self.load_ms = (time.perf_counter() - start) * 1000
        self.tokenizer = self.mr._tokenizer
        return {"load_ms": self.load_ms, "template_revision": self.mr.template_revision,
                "peak_after_load_bytes": mx.get_peak_memory(),
                "inference": "production_prefix_cache" if self.updated_engine else "recorded_uncached",
                "inference_source_sha256": file_sha256(Path(sys.modules[ModelRunner.__module__].__file__))}

    def generate(self, prompt, max_tokens):
        if not self.updated_engine:
            return super().generate(prompt, max_tokens)
        start = time.perf_counter()
        first, text, tokens, finish = None, "", 0, None
        for response in self.mr.stream(prompt, max_tokens):
            if first is None:
                first = (time.perf_counter() - start) * 1000
            text += response.text
            tokens += 1
            finish = response.finish_reason
        self.calls.append({"first_token_ms": first, "generation_ms": (time.perf_counter() - start) * 1000,
                           "yields": tokens, "max_tokens": max_tokens, "finish_reason": finish})
        return {"text": text, "output_tokens": tokens, "limit_hit": tokens >= max_tokens, "prompt": prompt}

    def engine(self):
        return self.module.CleanupEngine(self.generate, model_id=str(self.path), render_fn=self.render,
                                        template_revision=self.mr.template_revision)

    def clean(self, case):
        self.calls = []
        start = time.perf_counter()
        result = self.engine().clean(case["model_input"], locale="en-US",
                    destination_profile=case.get("destination_profile"),
                    relevant_vocabulary=case.get("relevant_vocabulary", []),
                    protected_spans=[tuple(s) for s in case.get("protected_spans", [])],
                    vocabulary_pairs=tuple(tuple(p) for p in case.get("vocabulary_pairs", [])))
        elapsed = (time.perf_counter()-start)*1000
        passes = [o for o in result.observations if o.get("kind") in ("corrections", "cleanup")]
        for call, obs in zip(self.calls, passes):
            call.update(role=obs["kind"], depth=obs.get("depth",0), window=obs["window_range"])
        # Record all owned depth-zero windows. The earlier harness retained only
        # the first, which cannot represent long-form model-only performance.
        main = [o for o in passes if o["kind"] == "cleanup" and o.get("depth",0)==0]
        parts = []
        last_end = None
        for o in main:
            s,e = o["window_range"]
            if parts:
                gap = case["model_input"][last_end:s]
                parts.append(gap if gap else " ")
            parts.append(postprocess(o["output"], case["model_input"][s:e]))
            last_end = e
        decisions = [o for o in result.observations if o.get("kind") == "cleanup_decision"]
        corrections = [o for o in result.observations if o.get("kind") == "corrections_applied"]
        selected, reasons = [], []
        for obs in corrections:
            for p in obs["proposals"]:
                if p.get("status") == "selected" and p.get("span"):
                    selected.append([p["span"][0]+obs["window_range"][0], p["span"][1]+obs["window_range"][0]])
                elif p.get("reason"):
                    reasons.append(p["reason"])
        return {"case_id":case["case_id"],"model":self.key,"engine":self.engine_name,
                "delivered":result.text,"model_only":"".join(parts) if parts else None,
                "model_only_windows":[{"range":o["window_range"],"text":o["output"]} for o in main],
                "path":result.path,"fallback_reason":result.fallback_reason,"incomplete":result.incomplete,
                "windows":result.termination.get("windows"),"limit_hits":result.termination.get("limit_hits"),
                "total_cleanup_ms":elapsed,"generation_ms":sum(c["generation_ms"] for c in self.calls),
                "first_token_ms":self.calls[0]["first_token_ms"] if self.calls else None,
                "peak_mem_bytes":self.mx.get_peak_memory(),"rss_peak_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "corrections_applied":result.corrections.get("applied"),"corrections_selected":selected,
                "corrections_rejected":result.corrections.get("rejected"),"correction_reject_reasons":reasons,
                "salvaged_words":sum(d.get("salvaged_words",0) for d in decisions),
                "validator_failures":sorted({c["name"] for d in decisions for c in d["validation"].get("components",[]) if c.get("status")=="fail"}),
                "calls":[{k:c.get(k) for k in ("role","depth","window","first_token_ms","generation_ms","yields","max_tokens","finish_reason")} for c in self.calls]}


def evaluate(key, cases_path, name, path=None, variant=False, limit=None, updated_engine=False, recorded_f=False):
    if sum((variant, updated_engine, recorded_f)) > 1:
        raise ValueError("Choose one recorded engine or updated source")
    cases_path = Path(cases_path)
    cases = read_jsonl(cases_path)
    if limit:
        cases = cases[:limit]
    if not cases:
        raise ValueError("No evaluation cases")
    test = any(c.get("split")=="test" for c in cases)
    if test and not (ART / "dataset/freeze.json").exists():
        raise RuntimeError("Synthetic evaluation labels must exist and be fixed before final model evaluation")
    if name.startswith("fresh-"):
        freeze = read_json(ART / "remediation/freeze.json")
        if not freeze or file_sha256(cases_path) != freeze["cases_sha256"]:
            raise RuntimeError("Fresh evaluation requires its exact frozen comparison file")
        if updated_engine and any(file_sha256(ROOT / "localflow/v2/cleanup" / n) != digest
                                  for n, digest in freeze["source_hashes"].items()):
            raise RuntimeError("Candidate source changed after the fresh evaluation freeze")
    refinement_input = test and cases_path.resolve().is_relative_to((ART / "refinement").resolve())
    if name.startswith("refined-") or refinement_input:
        from .refinement import require_final
        require_final(cases_path, candidate=updated_engine, key=key, model_path=path,
                      engine="updated_source" if updated_engine else "separator_fix" if variant else "recorded_f" if recorded_f else "production")
    out = ART / "eval" / f"{name}.jsonl"
    meta_path = out.with_suffix(".meta.json")
    prior = read_json(meta_path)
    if out.exists() and out.stat().st_size and not prior:
        raise RuntimeError("Existing evaluation outputs have no identity metadata")
    runner = Runner(key, path, variant, updated_engine, recorded_f)
    from lfx.export import content_digest
    if updated_engine:
        inference_source = ROOT / "localflow/v2/cleanup/model.py"
    else:
        from .baseline import load_runner
        recorded_runner = load_runner(recorded_f)
        inference_source = Path(sys.modules[recorded_runner.__module__].__file__)
    identity = {"model":key,"path":str(path or c_identity()["snapshot_path"] if key.startswith("C") else path or key),
                "engine":"updated_source" if updated_engine else "separator_fix" if variant else "recorded_f" if recorded_f else "production","cases_sha256":file_sha256(cases_path),"limit":limit,
                "model_content_digest":content_digest(runner.path),
                "inference_source_sha256":file_sha256(inference_source),
                "engine_source_sha256":{n:file_sha256(Path(runner.module.__file__).with_name(n))
                    for n in ("engine.py","validation.py","prompts.py","document_nodes.py","correction_retention.py")
                    if Path(runner.module.__file__).with_name(n).exists()}}
    if prior and prior["identity"] != identity:
        raise RuntimeError("Evaluation name already belongs to another artifact or dataset")
    done = {r["case_id"] for r in read_jsonl(out)}
    todo = [c for c in cases if c["case_id"] not in done]
    if not todo:
        return {"already_complete":len(done)}
    info = runner.load()
    meta = prior or {"identity":identity,"runs":[]}
    meta["runs"].append({"started":utc_now(),"load":info,"pid":os.getpid(),"todo":len(todo),
                         "interpreter":sys.executable,"python":sys.version.split()[0],
                         "engine_sources":{name:file_sha256(Path(runner.module.__file__).with_name(name))
                                           for name in ("engine.py","validation.py","prompts.py","document_nodes.py","correction_retention.py")
                                           if Path(runner.module.__file__).with_name(name).exists()},
                         "packages":{p:importlib.metadata.version(p) for p in ("mlx","mlx-lm","transformers")}})
    write_json(meta_path,meta)
    with out.open("a") as fh:
        for i,c in enumerate(todo):
            row = runner.clean(c)
            fh.write(json.dumps(row, ensure_ascii=False)+"\n");fh.flush()
            if (i+1)%25==0:
                print(json.dumps({"name":name,"done":len(done)+i+1,"total":len(cases)}),flush=True)
    meta["runs"][-1].update(finished=utc_now(),peak_mem_bytes=runner.mx.get_peak_memory())
    write_json(meta_path,meta)
    runner.unload()
    return {"complete":len(cases)}


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("model");p.add_argument("cases");p.add_argument("name")
    p.add_argument("--path");p.add_argument("--variant",action="store_true");p.add_argument("--limit",type=int)
    p.add_argument("--updated-engine",action="store_true")
    p.add_argument("--recorded-f",action="store_true")
    a=p.parse_args()
    print(json.dumps(evaluate(a.model,a.cases,a.name,a.path,a.variant,a.limit,a.updated_engine,a.recorded_f)))
