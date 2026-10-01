"""M15-A frozen-input contracts and content-free scoring. No model imports."""
from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import re
import random
import statistics
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

ROOT = pathlib.Path(__file__).resolve().parents[2]
HEX = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[a-zA-Z0-9_-]{1,100}\Z")
STATES = {"COMPLETE", "LOAD_FAILED", "OOM", "UNSUPPORTED_ADAPTER",
          "TEMPLATE_INCOMPATIBLE", "TIMEOUT", "SKIPPED_BY_CONTRACT"}
MEMORY_FIELDS = {"rss_bytes", "rss_peak_bytes", "mlx_active_bytes",
                 "mlx_cache_bytes", "mlx_peak_bytes", "system_available_bytes"}


def digest(data):
    if not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_manifest(manifest):
    require(manifest.get("schema") == "m15-cleanup-candidates/1", "manifest schema")
    candidates = manifest.get("candidates")
    require(isinstance(candidates, list) and candidates, "candidate list")
    ids = set()
    for c in candidates:
        cid = c.get("candidate_id", "")
        require(isinstance(cid, str) and ID.fullmatch(cid), "candidate id")
        require(cid not in ids, "duplicate candidate id")
        ids.add(cid)
        require(re.fullmatch(r"[\w.-]+/[\w.-]+", c.get("repository_id", "")),
                "repository identity must be a Hub id, never an absolute cache path")
        require(HEX.fullmatch(c.get("immutable_revision", "")), "immutable revision required")
        require(c.get("role") in {"control", "challenger", "ablation", "ceiling"}, "role")
        require(c.get("loader") == "mlx_lm", "unsupported loader")
        require(c.get("sampling") == {"temperature": 0.0,
                "max_tokens_rule": "min(words*3+96,4096); corrections=160",
                "speculative_decoding": False}, "primary sampling contract")
        require(c.get("reasoning_mode") == "direct", "primary reasoning contract")
        require(c.get("compatibility_status") in {"PENDING", "READY"} | STATES |
                {"UNSUPPORTED_ABLATION", "NEEDS_MODEL_SPECIFIC_ADAPTATION"}, "compatibility status")
    require(sum(c["role"] == "control" for c in candidates) == 1, "one control required")
    return candidates


def resolve_cache(candidate, tokenizer_required=True):
    """Exact cached revision only; never implicitly download or use refs/main."""
    from huggingface_hub import snapshot_download
    path = pathlib.Path(snapshot_download(candidate["repository_id"],
                        revision=candidate["immutable_revision"], local_files_only=True))
    require(path.name == candidate["immutable_revision"], "snapshot revision drift")
    for name in (("config.json", "tokenizer_config.json") if tokenizer_required else ("config.json",)):
        require((path / name).is_file(), "missing model asset: " + name)
    require(not tokenizer_required or (path / "tokenizer.json").is_file() or (path / "tokenizer.model").is_file(),
            "missing tokenizer")
    require(any(path.glob("model*.safetensors")), "missing weights")
    index = path / "model.safetensors.index.json"
    if index.exists():
        for name in set(json.loads(index.read_text())["weight_map"].values()):
            require((path / name).is_file(), "missing shard")
    for f in candidate.get("source_file_sizes", []):
        require((path / f["name"]).is_file() and (path / f["name"]).stat().st_size == f["size"],
                "pinned artifact size drift")
    require(not any(path.parent.parent.rglob("*.incomplete")), "incomplete cache")
    return path


def asset(base, record):
    require(isinstance(record, dict) and set(record) == {"path", "sha256"}, "asset schema")
    name = record["path"]
    require(isinstance(name, str) and name and not pathlib.Path(name).is_absolute()
            and ".." not in pathlib.Path(name).parts, "relative private asset required")
    root = pathlib.Path(base).resolve()
    path = root
    for part in pathlib.Path(name).parts:
        path = path / part
        require(not path.is_symlink(), "symlink asset refused")
    require(path.resolve().is_relative_to(root), "asset escapes corpus")
    require(HASH.fullmatch(record["sha256"]), "asset hash required")
    require(file_hash(path) == record["sha256"], "frozen asset hash mismatch")
    return path


def load_corpus(path):
    path = pathlib.Path(path)
    corpus = json.loads(path.read_text())
    require(corpus.get("schema") == "m15-frozen-corpus/1", "corpus schema")
    require(corpus.get("reference_state") == "frozen", "references must be frozen")
    require(isinstance(corpus.get("cases"), list) and corpus["cases"], "empty corpus")
    ids, families = set(), {}
    for c in corpus["cases"]:
        require(ID.fullmatch(c.get("case_id", "")), "opaque case id required")
        require(c["case_id"] not in ids, "duplicate case id")
        ids.add(c["case_id"])
        require(ID.fullmatch(c.get("family_id", "")), "opaque family id required")
        require(ID.fullmatch(c.get("stratum", "")), "stratum label required")
        require(c.get("origin") in {"human", "synthetic"}, "origin required")
        require(c.get("split") in {"dev", "validation", "held_out"}, "split required")
        require(isinstance(c.get("exposed"), bool), "exposure required")
        require(c["split"] != "held_out" or not c["exposed"], "exposed holdout")
        old = families.setdefault(c["family_id"], c["split"])
        require(old == c["split"], "family split leakage")
        require(c.get("reference_type") in {"intended_writing", "verbatim", "negative"}, "reference type")
        require(c.get("reviewed") is True, "adjudicated reference required")
        source = asset(path.parent, c["normalized"]).read_text()
        if "asr_artifact" in c:
            asset(path.parent, c["asr_artifact"])
        reference = json.loads(asset(path.parent, c["reference"]).read_text())
        require(isinstance(reference.get("text"), str), "reference text required")
        for start, end in c.get("protected_spans", []):
            require(type(start) is int and type(end) is int and 0 <= start < end <= len(source), "protected offsets")
        for span in reference.get("correction_spans", []):
            require(len(span) == 2 and all(type(n) is int for n in span)
                    and 0 <= span[0] < span[1] <= len(source), "gold correction offsets")
        if "audio" in c:
            require(asset(path.parent, c["audio"]).suffix == ".wav", "WAV required")
        require(isinstance(c.get("normalization_revision"), str) and c["normalization_revision"], "normalization identity")
        if c.get("m07_v002"):
            require(c["origin"] == "human" and c["reference_type"] == "intended_writing", "M07 real-text eligibility")
    reuse = [c for c in corpus["cases"] if c.get("m07_v002")]
    if reuse:
        require(Counter(c["split"] for c in reuse) == {"dev": 30, "validation": 10, "held_out": 20},
                "M07-V002 preserves 30/10/20")
    return corpus


def frozen_case(base, case):
    """Recheck bytes before EACH replay, including every resumed unit."""
    source = asset(base, case["normalized"]).read_text()
    reference = json.loads(asset(base, case["reference"]).read_text())
    audio = asset(base, case["audio"]) if "audio" in case else None
    if "asr_artifact" in case:
        asset(base, case["asr_artifact"])
    if "verbatim_reference" in case:
        asset(base, case["verbatim_reference"])
    return source, reference, audio


def freeze_requirements(path, corpus):
    """Owner adjudication and coverage gate; never creates a reference."""
    require(corpus.get("owner_review_complete") is True, "CORPUS_FREEZE_REQUIRED: owner review")
    require(corpus.get("asr") == {
        "repository_id": "mlx-community/parakeet-tdt-0.6b-v3",
        "immutable_revision": "ed2b7e8c15f9aaa0b5772e2efb986255eaef7e15"}, "pinned Parakeet required")
    cases = corpus["cases"]
    speech = [c for c in cases if c.get("speech_band") in {"short", "diverse"}]
    require(Counter(c["speech_band"] for c in speech) == {"short": 60, "diverse": 80},
            "CORPUS_FREEZE_REQUIRED: 60 short / 80 diverse speech")
    negatives = [c for c in cases if c["reference_type"] == "negative"]
    require(len(negatives) == 20, "CORPUS_FREEZE_REQUIRED: 20 negatives")
    reuse = [c for c in cases if c.get("m07_v002")]
    require(Counter(c["split"] for c in reuse) == {"dev": 30, "validation": 10, "held_out": 20},
            "CORPUS_FREEZE_REQUIRED: M07-V002 30/10/20")
    require(all(c.get("m07_source") == "legacy_749" for c in reuse), "M07 legacy provenance required")
    required = {"ordinary_prose", "long_developer_prompt", "corrections", "standalone_markers",
                "numeric", "technical_names", "questions", "negation_constraints", "literal",
                "lists_steps", "paragraphs", "multilingual", "quiet", "noisy"}
    require(required <= {tag for c in speech for tag in c.get("coverage_tags", [])},
            "CORPUS_FREEZE_REQUIRED: speech strata")
    audio_hashes = set()
    for c in cases:
        require(c.get("adjudication_status") == "CONFIRMED" and c.get("retention_status") == "OWNER_APPROVED"
                and c.get("privacy_class") == "PRIVATE_OWNER_ONLY", "review/retention/privacy required")
        _, reference, audio = frozen_case(pathlib.Path(path).parent, c)
        require(reference.get("author") == "owner" and reference.get("candidate_output_used") is False,
                "owner reference provenance required")
        if c in speech or c in negatives:
            require(audio is not None, "speech/negative WAV required")
            require(c["audio"]["sha256"] not in audio_hashes, "duplicate counted audio")
            audio_hashes.add(c["audio"]["sha256"])
        if c in speech:
            require(c["origin"] == "human" and c["reference_type"] == "intended_writing",
                    "human speech intended-writing reference required")
            asset(pathlib.Path(path).parent, c.get("verbatim_reference"))
        if c in negatives:
            require(c.get("negative_type") in {"silence", "background"} and reference["text"] == "",
                    "reviewed no-speech negative required")
    normalizer = ROOT / "localflow/v2/normalize"
    files = sorted([*normalizer.rglob("*.py"), *normalizer.rglob("*.json")])
    require(corpus.get("normalized_input_identity") == {
        "asr": corpus["asr"],
        "normalizer_files_sha256": digest({str(p.relative_to(ROOT)): file_hash(p) for p in files}),
        "runtime": runtime_versions()}, "normalized input generation identity drift")


def validate_freeze_lock(path, corpus):
    freeze_requirements(path, corpus)
    lock = json.loads(pathlib.Path(str(path) + ".freeze-lock.json").read_text())
    require(lock == {"state": "M15A_CORPUS_FROZEN_READY_TO_BENCHMARK",
                    "corpus_sha256": file_hash(path)}, "corpus/split/context freeze lock drift")


def runtime_versions():
    result = {}
    for name in ("mlx", "mlx-lm", "transformers", "huggingface-hub", "numpy", "parakeet-mlx", "soundfile"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def source_identity():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    files = [*sorted((ROOT / "localflow/v2/cleanup").glob("*.py")),
             *sorted((ROOT / "localflow/v2/normalize").rglob("*.py")),
             *sorted((ROOT / "localflow/v2/normalize").rglob("*.json")), ROOT / "localflow/stt.py",
             *sorted((ROOT / "scripts/v2").glob("*cleanup*candidate*.py")),
             ROOT / "scripts/v2/cleanup_benchmark.py", ROOT / "scripts/v2/cleanup_candidate_adapter.py"]
    return {"localflow_source_sha": sha, "benchmark_code_sha": sha,
            "source_files_sha256": digest({str(p.relative_to(ROOT)): file_hash(p) for p in files}),
            "runtime": runtime_versions()}


def quantiles(values, failures=0):
    require(all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values), "invalid latency")
    if not values:
        return {"n": 0, "failures": failures, "p50": None, "p95": None, "p99": None, "max": None,
                "missing_reason": "no_successful_measurements"}
    s = sorted(values)
    return {"n": len(s), "failures": failures, "p50": statistics.median(s),
            "p95": s[math.ceil(.95 * len(s)) - 1], "p99": s[math.ceil(.99 * len(s)) - 1], "max": s[-1]}


def validate_memory(memory):
    require(isinstance(memory, dict), "memory object")
    require(memory.get("mechanism") == "ps_rss+resource_ru_maxrss+mlx_allocator+vm_stat", "memory mechanism")
    for k in MEMORY_FIELDS:
        value = memory.get(k)
        require(value is None or type(value) is int and value >= 0, "invalid memory " + k)
        require(value is not None or memory.get("missing_reason"), "unknown memory reason required")
    return memory


def failure_state(exc):
    if isinstance(exc, MemoryError) or any(t in str(exc).lower() for t in
            ("out of memory", "memory limit", "metal memory", "insufficient memory")):
        return "OOM"
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, TemplateError):
        return "TEMPLATE_INCOMPATIBLE"
    return "LOAD_FAILED"


class TemplateError(ValueError):
    pass


def token_key(text):
    return re.findall(r"\w+|[^\w\s]", text.casefold())


def score(source, reference, result, protected_spans=()):
    from localflow.v2.cleanup.validation import validate
    from localflow.v2.cleanup.engine import CORRECTION_MARKER_RE
    out = result.text
    expected = reference["text"]
    gold_spans = {tuple(s) for s in reference.get("correction_spans", [])}
    selected, proposal_count = [], 0
    for o in result.observations:
        if o.get("kind") == "corrections_applied":
            offset = o["window_range"][0]
            for p in o["proposals"]:
                if p.get("status") != "superseded":
                    proposal_count += 1
                if p.get("status") == "selected" and p.get("span") is not None:
                    selected.append((p["span"][0] + offset, p["span"][1] + offset))
    selected = set(selected)
    correct = len(selected & gold_spans)
    wrong = len(selected - gold_spans)
    final = validate(expected, out, protected=[source[s:e] for s, e, *_ in protected_spans])
    components = {c.name: c.status for c in final.components}
    # Mechanical gates are not an assertion that every human meaning defect is detectable.
    checks = reference.get("checks", {})
    literal_pass = all(s in out for s in checks.get("literals", []))
    required_pass = all(any(alt.casefold() in out.casefold() for alt in alternatives)
                        for alternatives in checks.get("required", []))
    forbidden_pass = all(s.casefold() not in out.casefold() for s in checks.get("forbidden", []))
    critical = any(c.kind == "deterministic" and c.status == "fail" for c in final.components)
    critical |= not (literal_pass and required_pass and forbidden_pass)
    fallback = result.path != "llm"
    engine_failures = sum(c["counts"].get("fail", 0) for c in result.validation["components"])
    exact = token_key(expected) == token_key(out)
    return {
        "accepted": result.path == "llm", "critical_failure": bool(critical),
        "validator_critical_failures": engine_failures,
        "validator_reject": any(o.get("kind") == "cleanup_decision" and not o["accepted"] for o in result.observations),
        "validator_findings": sum(c["counts"].get("finding", 0) for c in result.validation["components"]),
        "fallback": fallback, "fallback_reason": safe_reason(result.fallback_reason),
        "output_limit": bool(result.termination.get("limit_hits")),
        "useful_cleanup": not fallback and out != source and not critical,
        "reference_exact_match": exact, "reference_components": components,
        "literal_pass": literal_pass and components.get("literal_spans", "pass") != "fail",
        "protected_pass": components.get("protected_tokens", "pass") != "fail",
        "number_pass": components.get("numeric_values", "pass") != "fail",
        "negation_pass": components.get("negation_coverage", "pass") != "fail",
        "constraint_pass": components.get("clause_scope", "pass") != "fail" and required_pass,
        "technical_pass": components.get("technical_tokens", "pass") != "fail",
        "structure_pass": components.get("structure", "pass") != "fail",
        "invention_finding": components.get("novelty") == "fail",
        "answer_vs_edit_violation": components.get("novelty") == "fail" or not forbidden_pass,
        "list_item_count": len(re.findall(r"^\s*(?:[-*+] |\d+[.)] )", out, re.M)),
        "list_order_pass": components.get("coverage", "pass") != "fail",
        "correction_opportunities": len(gold_spans), "correct_resolutions": correct,
        "missed_corrections": len(gold_spans) - correct, "wrong_corrections": wrong,
        "over_deletions": sum(any(s < gs or e > ge for gs, ge in gold_spans if s < ge and e > gs)
                              for s, e in selected - gold_spans),
        "marker_residue": max(0, len(CORRECTION_MARKER_RE.findall(out)) - len(CORRECTION_MARKER_RE.findall(expected))),
        "correction_exact_match": exact if gold_spans else None,
        "fallback_after_correction": bool(gold_spans) and fallback,
        "validator_rollback": result.corrections["rolled_back"],
        "no_proposal": bool(gold_spans) and proposal_count == 0,
        "accepted_correction_count": result.corrections["applied"],
        "correction_precision_denominator": len(selected),
        "rejected_correction_count": result.corrections["rejected"],
        "stage_lineage": {"source_sha256": digest(source.encode()), "reference_sha256": digest(expected.encode()),
                          "final_sha256": digest(out.encode()), "path": result.path, "stage": result.stage},
    }


def safe_reason(reason):
    if not reason:
        return None
    # Only controlled labels; arbitrary exception/output text never becomes public evidence.
    allowed = {"output_limit", "empty_output", "retry_assembly_rejected", "no_output"}
    if reason in allowed:
        return reason
    if reason.startswith("validation_rejected:"):
        return "validation_rejected"
    return "other_recorded_privately"


def public_row(row):
    """Allowlist export; nested private payloads cannot hitchhike in a public row."""
    fields = {"candidate_id", "case_id", "family_id", "repetition", "track", "status", "origin", "stratum",
              "split", "reference_type", "length_band", "input_sha256", "audio_sha256",
              "timing_ms", "memory", "metrics", "identity", "failure_kind", "timestamp"}
    out = {k: v for k, v in row.items() if k in fields}
    metric_keys = {"accepted", "critical_failure", "validator_critical_failures", "validator_reject",
        "validator_findings", "fallback", "fallback_reason", "output_limit", "useful_cleanup",
        "reference_exact_match", "reference_components", "literal_pass", "protected_pass", "number_pass",
        "negation_pass", "constraint_pass", "technical_pass", "structure_pass", "invention_finding",
        "answer_vs_edit_violation", "list_item_count", "list_order_pass", "correction_opportunities",
        "correct_resolutions", "missed_corrections", "wrong_corrections", "over_deletions", "marker_residue",
        "correction_exact_match", "fallback_after_correction", "validator_rollback", "no_proposal",
        "accepted_correction_count", "rejected_correction_count", "stage_lineage", "correction_missing_reason",
        "correction_precision_denominator"}
    if "metrics" in out:
        out["metrics"] = {k: v for k, v in out["metrics"].items() if k in metric_keys}
        if "stage_lineage" in out["metrics"]:
            out["metrics"]["stage_lineage"] = {k: v for k, v in out["metrics"]["stage_lineage"].items()
                if k in {"source_sha256", "reference_sha256", "final_sha256", "path", "stage"}}
    if "identity" in out:
        identity_keys = {"candidate_id", "repository_id", "immutable_revision", "quantization", "runtime",
            "chat_template_sha256", "config_sha256", "reasoning_mode", "text_only", "speculative_decoding",
            "cleanup_prompt_sha256", "cleanup_prompt_revision", "correction_prompt_revision",
            "correction_prompt_sha256", "asr", "normalization_revision", "asr_sha256", "normalized_sha256"}
        out["identity"] = {k: v for k, v in out["identity"].items() if k in identity_keys}
    return out


def aggregate(rows):
    successful = [r for r in rows if r["status"] == "COMPLETE"]
    n, failed = len(successful), len(rows) - len(successful)
    counts = Counter()
    for r in successful:
        counts.update({k: int(v) for k, v in r["metrics"].items() if type(v) in (int, bool)})
    ratio = lambda a, b: counts[a] / counts[b] if counts[b] else None
    return {"attempted": len(rows), "completed": n, "failed": failed,
            "unique_cases": len({r["case_id"] for r in rows}),
            "unique_families": len({r.get("family_id", r["case_id"]) for r in rows}),
            "count_basis": "candidate_case_repetition_units; rates condition on completed units",
            "failure_states": dict(Counter(r["status"] for r in rows if r["status"] != "COMPLETE")),
            "counts": dict(counts),
            "correction_precision": ratio("correct_resolutions", "correction_precision_denominator"),
            "correction_recall": ratio("correct_resolutions", "correction_opportunities"),
            "rates": {k: counts[k] / n if n else None for k in ("critical_failure", "validator_reject", "fallback",
                       "output_limit", "useful_cleanup", "reference_exact_match", "literal_pass", "protected_pass",
                       "number_pass", "negation_pass", "constraint_pass", "technical_pass", "structure_pass")},
            "timing_ms": {k: quantiles([r["timing_ms"][k] for r in successful
                              if r["timing_ms"].get(k) is not None], failed)
                          for k in ("first_token", "generation", "validation", "cleanup", "end_to_end", "asr", "normalization")},
            "peak_memory_bytes": max((r["memory"]["mlx_peak_bytes"] for r in successful
                                       if r["memory"].get("mlx_peak_bytes") is not None), default=None),
            "rate_intervals": cluster_intervals(successful),
            "semantic_gate": "FAIL" if counts["critical_failure"] or counts["wrong_corrections"] else
                             "INCOMPLETE" if failed or not n else "MECHANICAL_PASS_PENDING_HUMAN_QUALIFICATION"}


def cluster_intervals(rows):
    """Deterministic family bootstrap, so five repeats aren't five independent speakers."""
    families = defaultdict(list)
    for row in rows:
        families[row.get("family_id", row["case_id"])].append(row)
    if len(families) < 2:
        return {"method": "family-bootstrap-200-seed-15", "confidence": .95,
                "intervals": None, "missing_reason": "fewer_than_two_independent_families"}
    rng = random.Random(15)
    keys = sorted(families)
    samples = defaultdict(list)
    for _ in range(200):
        draw = [r for key in rng.choices(keys, k=len(keys)) for r in families[key]]
        for metric in ("critical_failure", "useful_cleanup", "fallback", "validator_reject"):
            samples[metric].append(sum(bool(r["metrics"].get(metric)) for r in draw) / len(draw))
    return {"method": "family-bootstrap-200-seed-15", "confidence": .95,
            "families": len(families), "intervals": {k: [sorted(v)[4], sorted(v)[194]] for k, v in samples.items()},
            "limitation": "empirical intervals; zero observed defects do not establish zero population risk"}


def grouped(rows):
    groups = defaultdict(list)
    for r in rows:
        key = (r["candidate_id"], r["track"], r["origin"], r["stratum"],
               r["length_band"], r["reference_type"], r["split"])
        groups[key].append(r)
    return [{"cohort": list(k), **aggregate(v)} for k, v in sorted(groups.items())]


def pareto(points, minimize):
    valid = [p for p in points if all(p.get(k) is not None for k in minimize)]
    return [p["candidate_id"] for p in valid if not any(
        all(q[k] <= p[k] for k in minimize) and any(q[k] < p[k] for k in minimize)
        for q in valid if q is not p)]


def blind_queue(case, source, reference, outputs, seed="m15-a"):
    require(len(outputs) == 2, "two finalists required")
    order = sorted(outputs, key=lambda cid: digest((seed + case + cid).encode()))
    return ({"case_id": case, "source": source, "reference": reference,
             "Output A": outputs[order[0]], "Output B": outputs[order[1]],
             "labels": ["A", "B", "tie", "neither", "uncertain"]},
            {"case_id": case, "A": order[0], "B": order[1]})


def write_report(output, rows, identity, cold_loads):
    by = defaultdict(list)
    for r in rows:
        by[(r["candidate_id"], r["track"], r["origin"])].append(r)
    summaries = [{"candidate_id": c, "track": t, "origin": o, **aggregate(v)}
                 for (c, t, o), v in sorted(by.items())]
    fronts = []
    for track, origin in sorted({(s["track"], s["origin"]) for s in summaries}):
        cohort = [s for s in summaries if s["track"] == track and s["origin"] == origin and not s["failed"]]
        points = [{"candidate_id": s["candidate_id"], "fidelity_failures": s["counts"].get("critical_failure", 0),
                   "latency": s["timing_ms"]["cleanup"]["p95"], "memory": s["peak_memory_bytes"],
                   "fallback": s["rates"]["fallback"], "not_useful": 1-s["rates"]["useful_cleanup"]} for s in cohort]
        fronts.append({"track": track, "origin": origin,
                       "fidelity_latency": pareto(points, ["fidelity_failures", "latency"]),
                       "fidelity_memory": pareto(points, ["fidelity_failures", "memory"]),
                       "useful_fallback": pareto(points, ["not_useful", "fallback"])})
    atomic_json(pathlib.Path(output) / "results.json", {"schema": "m15-a-results/1", "identity": identity,
                 "candidate_summaries": summaries, "cohorts": grouped(rows), "pareto": fronts,
                 "cold_loads": cold_loads, "rows": [public_row(r) for r in rows], "promotion": "NOT_AUTHORIZED"})
    lines = ["# M15-A automated comparison", "", "File replay excludes physical microphone/device/insertion latency.",
             "Human and synthetic denominators remain separate. Mechanical checks do not certify all meaning.", "",
             "|Candidate / track / origin|Critical|Wrong|Missed|Precision|Recall|Useful %|Reject %|Fallback %|Limit %|Constraint %|Literal %|Number %|Structure %|Cleanup p50 / p95 ms|E2E p95 ms|MLX peak bytes|Cold load p50 ms|Status / gate|",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|"]
    for s in summaries:
        c, r, t = s["counts"], s["rates"], s["timing_ms"]
        pct = lambda key: round(100*r[key], 2) if r[key] is not None else "unavailable"
        cold = quantiles([l["cold_load_ms"] for l in cold_loads if l["candidate_id"] == s["candidate_id"]
                          and l.get("cold_load_ms") is not None])["p50"]
        state = "INCOMPLETE" if s["failed"] else "COMPLETE"
        lines.append(f"|{s['candidate_id']} / {s['track']} / {s['origin']}|{c.get('critical_failure',0)}|{c.get('wrong_corrections',0)}|{c.get('missed_corrections',0)}|{s['correction_precision']}|{s['correction_recall']}|{pct('useful_cleanup')}|{pct('validator_reject')}|{pct('fallback')}|{pct('output_limit')}|{pct('constraint_pass')}|{pct('literal_pass')}|{pct('number_pass')}|{pct('structure_pass')}|{t['cleanup']['p50']} / {t['cleanup']['p95']}|{t['end_to_end']['p95']}|{s['peak_memory_bytes']}|{cold}|{state} / {s['semantic_gate']}|")
    lines += ["", "Full component, stratum, length, reference and split counts are in results.json.",
              "No scalar ranking or automatic promotion. M07-V001/V002, M11, offline packaging, safe memory headroom and explicit owner approval remain gates."]
    (pathlib.Path(output) / "report.md").write_text("\n".join(lines) + "\n")


def utc_now():
    return datetime.now(timezone.utc).isoformat()
