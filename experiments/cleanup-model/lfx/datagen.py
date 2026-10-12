"""Generation and verification waves -> accepted, captured pairs per split."""

from __future__ import annotations

import json
import random
from collections import Counter

from . import batches, synth
from .common import ART, CONFIG, anthropic_client, read_json, read_jsonl, utc_now, write_json, write_jsonl

PAIRS = ART / "pairs"
CAPTURES = ART / "captures"
GEN_INPUT_TOKENS = 6500        # measured 5,896 with count_tokens for a 6-family request, plus margin
VERIFY_INPUT_TOKENS = 4500

_clients = {}


def clients():
    if not _clients:
        _clients["c"] = anthropic_client(max_retries=4)
        _clients["n"] = anthropic_client(max_retries=0)
    return _clients["c"], _clients["n"]


def plan_requests(name: str, specs: list[dict]) -> tuple[dict, dict]:
    per = CONFIG["claude"]["families_per_request"]
    requests, spec_map = {}, {}
    for i in range(0, len(specs), per):
        chunk = specs[i:i + per]
        rid = f"{name}-{i // per:04d}"
        requests[rid] = synth.generation_params(chunk)
        for s in chunk:
            spec_map[s["family_id"]] = s
    return requests, spec_map


def run_generation(name: str, specs: list[dict], log=print) -> batches.Wave:
    requests, spec_map = plan_requests(name, specs)
    write_json(ART / "claude" / name / "specs.json", spec_map)
    c, n = clients()
    w = batches.Wave(name, requests, parse=synth.parse_generation,
                     est_input_tokens=lambda p: GEN_INPUT_TOKENS, client=c, client_noretry=n,
                     purpose="generation", log=log)
    w.run()
    return w


def process_generation(name: str, rng_seed: str = "variants") -> dict:
    """Turn a finished generation wave into gated, captured pairs."""
    from .capture import capture
    w_dir = ART / "claude" / name
    spec_map = read_json(w_dir / "specs.json")
    outcomes = read_json(w_dir / "outcomes.json", {})
    requests = read_json(w_dir / "requests.json")
    pairs, rejects = [], Counter()
    seen = set()
    for rid in requests:
        o = outcomes.get(rid, {})
        if o.get("status") != batches.FINAL_OK:
            rejects[f"request_{o.get('status', 'missing')}"] += 1
            continue
        for fam in o["value"]:
            fid = fam.get("family_id")
            if fid not in spec_map or fid in seen:
                rejects["unknown_or_duplicate_family_id"] += 1
                continue
            seen.add(fid)
            p = synth.prepare_family(fam, spec_map[fid])
            p["provenance"] = {"wave": name, "request": rid, "custom_id": o.get("custom_id"),
                               "batch_id": o.get("batch_id"), "generator": CONFIG["claude"]["model"],
                               "generated": utc_now()}
            pairs.append(p)
    missing = [fid for fid in spec_map if fid not in seen]
    rejects["family_missing_from_response"] += len(missing)
    rng = random.Random(f"{CONFIG['experiment_id']}:{name}:{rng_seed}")
    out, captures = [], []
    for p in pairs:
        group = [p]
        if p["split"] == "train":
            v = synth.filler_variant(p, rng) if rng.random() < 0.35 else None
            if v:
                group.append(v)
        if not p["is_noop"] and rng.random() < 0.30:
            v = synth.fixpoint_variant(p)
            if v:
                group.append(v)
        for q in group:
            if q["reject"]:
                q["accepted_gates"] = False
            else:
                c = capture(q)
                q["accepted_gates"] = c["accepted"]
                q["reject"] = c["reject"]
                q["gold_offsets"] = c.get("gold_offsets", [])
                q["protected_spans"] = c.get("protected_spans", [])
                q["corrections_triggered"] = c.get("corrections_triggered")
                q["delivered_reference"] = c.get("delivered")
                q["list_and_salvage"] = c.get("list_and_salvage", False)
                if c["accepted"]:
                    captures.append({"pair_id": q["pair_id"], "family_id": q["family_id"], "split": q["split"],
                                     "calls": [{k: x[k] for k in ("role", "prompt", "completion", "max_tokens")}
                                               for x in c["calls"]]})
            for r in q["reject"]:
                rejects[r.split(":")[0]] += 1
            out.append(q)
    write_jsonl(PAIRS / f"{name}.jsonl", out)
    write_jsonl(CAPTURES / f"{name}.jsonl", captures)
    accepted = [q for q in out if q["accepted_gates"]]
    stats = {"wave": name, "families_requested": len(spec_map), "families_returned": len(pairs),
             "pairs_total": len(out), "pairs_accepted": len(accepted),
             "accepted_noop": sum(q["is_noop"] for q in accepted),
             "by_variant": dict(Counter(q["variant"] for q in accepted)),
             "by_category": dict(Counter(q["category"] for q in accepted)),
             "normalization_changed": sum(q["normalization_changed"] for q in out),
             "reject_reasons": dict(rejects), "processed": utc_now()}
    write_json(PAIRS / f"{name}.stats.json", stats)
    return stats


# ---------------------------------------------------------------- verification

def run_verification(name: str, pairs: list[dict], reservation: str | None = "verify", log=print,
                     chunk: int | None = None) -> batches.Wave:
    per = CONFIG["claude"]["verify_pairs_per_request"]
    requests = {}
    for i in range(0, len(pairs), per):
        requests[f"{name}-{i // per:04d}"] = synth.verify_params(pairs[i:i + per])
    write_json(ART / "claude" / name / "pair_ids.json", {f"{name}-{i // per:04d}": [p["pair_id"] for p in pairs[i:i + per]]
                                                        for i in range(0, len(pairs), per)})
    c, n = clients()
    w = batches.Wave(name, requests, parse=synth.parse_verify, est_input_tokens=lambda p: VERIFY_INPUT_TOKENS,
                     client=c, client_noretry=n, purpose="verification", reservation=reservation, log=log)
    w.run(chunk=chunk)
    return w


def verdicts(name: str) -> dict:
    w_dir = ART / "claude" / name
    ids = read_json(w_dir / "pair_ids.json", {})
    outcomes = read_json(w_dir / "outcomes.json", {})
    out = {}
    for rid, pids in ids.items():
        o = outcomes.get(rid, {})
        if o.get("status") != batches.FINAL_OK:
            for pid in pids:
                out[pid] = {"verdict": "UNVERIFIED", "reasons": [f"request_{o.get('status', 'missing')}"]}
            continue
        got = {v["pair_id"]: v for v in o["value"]}
        for pid in pids:
            out[pid] = got.get(pid, {"verdict": "UNVERIFIED", "reasons": ["verdict_missing"]})
    return out


HARD_CATEGORIES = {"self_correction_multiple", "self_correction_single", "spoken_list", "quoted_instruction",
                   "question_or_request_as_content", "vocabulary_authorized", "asr_mishearing_preserve",
                   "preservation_discourse"}


def verify_wave(wave: str, fraction: float = 1.0, seed: int = 7, log=print, chunk: int | None = 200) -> dict:
    """Verify a wave's accepted base pairs: every pair when fraction == 1,
    otherwise all hard-category / correction pairs plus a random fraction."""
    pairs = [p for p in read_jsonl(PAIRS / f"{wave}.jsonl") if p["accepted_gates"] and p["variant"] == "base"]
    if fraction < 1.0:
        rng = random.Random(seed)
        pairs = [p for p in pairs if p["category"] in HARD_CATEGORIES or p["gold_lines"] or rng.random() < fraction]
    name = "ver-" + wave.replace("gen-", "")
    run_verification(name, pairs, log=log, chunk=chunk)
    v = verdicts(name)
    return {"wave": wave, "verified": len(pairs), "verdicts": dict(Counter(x["verdict"] for x in v.values())),
            "reasons": dict(Counter(r for x in v.values() for r in x["reasons"]))}


def verify_remaining(wave: str, done_names: list[str], name: str, log=print, chunk: int | None = 200) -> dict:
    """Verify the accepted base pairs of a wave that earlier verification
    waves did not cover (budget permitting)."""
    covered = set()
    for d in done_names:
        for ids in read_json(ART / "claude" / d / "pair_ids.json", {}).values():
            covered.update(ids)
    pairs = [p for p in read_jsonl(PAIRS / f"{wave}.jsonl")
             if p["accepted_gates"] and p["variant"] == "base" and p["pair_id"] not in covered]
    run_verification(name, pairs, log=log, chunk=chunk)
    v = verdicts(name)
    return {"wave": wave, "verified": len(pairs), "verdicts": dict(Counter(x["verdict"] for x in v.values())),
            "reasons": dict(Counter(r for x in v.values() for r in x["reasons"]))}
