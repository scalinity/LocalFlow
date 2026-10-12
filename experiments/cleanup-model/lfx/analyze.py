"""Score the final evaluation, compare paired, apply the frozen rules.

Writes artifacts/results/summary.json (aggregates, comparisons, decision,
provenance) and artifacts/results/cases.json (per-case explorer rows).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict

from . import score as S
from .audio import lexical
from .common import ART, CONFIG, read_json, read_jsonl, sha256_json, utc_now, write_json

EVAL = ART / "eval"
OUT = ART / "results"
MODELS = ("A", "B", "C")
SYN_KEYS = ["damage", "facts_changed", "hallucination", "omission", "negation_changed", "missing_ending",
            "unwanted_answer", "repair_success", "lexical_match", "noop_preserved", "unnecessary_edit",
            "correction_success", "list_ok"]


def pct(x):
    return None if x is None else round(100 * x, 2)


def quant(values, q):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def fixture_pass(case: dict, text: str | None, path: str, model_only: bool) -> bool | None:
    import re as _re
    if text is None:
        return False
    low = text.lower()

    def found(needle):
        if needle in low:
            return True
        return _re.sub(r"[\s\-]+", " ", needle).strip() in _re.sub(r"[\s\-]+", " ", low).strip()
    ok = all(any(found(a.lower()) for a in g) for g in case.get("expect", []))
    forb = list(case.get("forbid_on_fallback", []))
    if model_only or path == "llm":
        forb += list(case.get("forbid", []))
    return ok and not any(b.lower() in low for b in forb)


def score_row(case: dict, row: dict | None) -> dict:
    """All metrics for one case and one model, in three modes."""
    out = {}
    src = case["source"]
    if row is None:
        return {"missing": True}
    texts = {"model_only": row.get("model_only"), "delivered": row.get("delivered")}
    if row.get("teacher_forced"):
        texts["teacher_forced"] = row["teacher_forced"].get("model_only")
    for mode, text in texts.items():
        if src in ("synthetic", "synthetic_longform"):
            out[mode] = S.score_synthetic(case, text, delivered=(mode == "delivered"))
        elif src in ("disfluencyspeech", "fleurs"):
            out[mode] = S.score_real(case, {"normalized": case["model_input"]}, text)
        elif src == "localflow_fixtures":
            out[mode] = {"available": text is not None,
                         "fixture_pass": fixture_pass(case, text, row.get("path", ""), mode != "delivered")}
    return out


def aggregate(case_ids, cases, scored, model, mode) -> dict:
    rows = [scored[model][c][mode] for c in case_ids if mode in scored[model].get(c, {})]
    rows = [r for r in rows if r.get("available", True)]
    agg = {"n": len(rows)}
    if not rows:
        return agg
    for k in SYN_KEYS + ["unauthorized_edit", "fixture_pass", "changed"]:
        vals = [r.get(k) for r in rows if r.get(k) is not None]
        if vals:
            agg[k] = pct(sum(map(float, vals)) / len(vals))
            agg[k + "_n"] = len(vals)
    we = sum(r.get("wer_errors", 0) for r in rows)
    ww = sum(r.get("wer_words", 0) for r in rows)
    if ww:
        agg["wer"] = round(100 * we / ww, 2)
    ce = sum(r.get("cer_errors", 0) for r in rows)
    cc = sum(r.get("cer_chars", 0) for r in rows)
    if cc:
        agg["cer"] = round(100 * ce / cc, 2)
    if any("filler_in" in r for r in rows):
        fin = sum(r.get("filler_in", 0) for r in rows)
        fout = sum(r.get("filler_out", 0) for r in rows)
        agg["filler_removed_share"] = pct((fin - fout) / fin) if fin else None
    if any("filler_residue" in r for r in rows):
        agg["filler_residue_cases"] = pct(sum(r.get("filler_residue", 0) > 0 for r in rows) / len(rows))
    return agg


def engine_stats(case_ids, rows_by_case) -> dict:
    rows = [rows_by_case[c] for c in case_ids if c in rows_by_case]
    n = len(rows)
    if not n:
        return {"n": 0}
    return {"n": n, "fallback": pct(sum(r["path"] != "llm" for r in rows) / n),
            "fallback_reasons": dict(Counter((r.get("fallback_reason") or "").split(":")[0] for r in rows if r["path"] != "llm")),
            "salvaged": pct(sum((r.get("salvaged_words") or 0) > 0 for r in rows) / n),
            "output_limit": pct(sum((r.get("limit_hits") or 0) > 0 for r in rows) / n),
            "think_leak": pct(sum(bool(r.get("think_leak")) for r in rows) / n),
            "errors": sum(1 for r in rows if r.get("error")),
            "corrections_rejected": sum(r.get("corrections_rejected") or 0 for r in rows)}


def latency(rows) -> dict:
    tot = [r["total_cleanup_ms"] for r in rows if r.get("total_cleanup_ms") is not None and not r.get("error")]
    first = [r["first_token_ms"] for r in rows if r.get("first_token_ms")]
    gen = [r["generation_ms"] for r in rows if r.get("generation_ms") is not None]
    val = [r["validation_ms"] for r in rows if r.get("validation_ms") is not None]
    main_first = [c["first_token_ms"] for r in rows for c in r.get("calls", []) if c.get("role") == "cleanup" and c.get("depth") == 0]
    corr = [c["generation_ms"] for r in rows for c in r.get("calls", []) if c.get("role") == "corrections"]
    f = lambda v: {"median": round(statistics.median(v), 1) if v else None, "p95": round(quant(v, 0.95), 1) if v else None,
                   "mean": round(statistics.mean(v), 1) if v else None, "n": len(v)}
    return {"total_cleanup_ms": f(tot), "first_token_ms": f(first), "generation_ms": f(gen), "validation_ms": f(val),
            "main_pass_first_token_ms": f(main_first), "corrections_pass_ms": f(corr),
            "peak_mem_gb": round(max((r.get("peak_mem_bytes") or 0) for r in rows) / 1e9, 2) if rows else None}


def boot(a: dict, b: dict, families: dict, ratio=False):
    if not any(c in b for c in a):
        return {"diff": None, "ci95": [None, None], "diff_pp": None, "ci95_pp": [None, None], "n_cases": 0,
                "n_families": 0, "missing_reason": "no paired cases"}
    n = CONFIG["evaluation"]["bootstrap_resamples"]
    r = S.family_bootstrap(a, b, None, families, n=n, seed=CONFIG["evaluation"]["bootstrap_seed"], ratio=ratio)
    r["diff_pp"] = None if r["diff"] is None else round(100 * r["diff"], 2)
    r["ci95_pp"] = [round(100 * x, 2) for x in r["ci95"]]
    return r


def metric_map(ids, scored, model, mode, key):
    out = {}
    for c in ids:
        m = scored[model].get(c, {}).get(mode)
        if m is None:
            continue
        v = m.get(key)
        if key == "damage" and not m.get("available", True):
            v = True
        if v is not None:
            out[c] = bool(v)
    return out


def wer_map(ids, scored, model, mode):
    return {c: (scored[model][c][mode]["wer_errors"], scored[model][c][mode]["wer_words"]) for c in ids
            if mode in scored[model].get(c, {}) and "wer_errors" in scored[model][c][mode]}


def main() -> dict:
    cases = {c["case_id"]: c for c in read_jsonl(EVAL / "final_cases.jsonl")}
    rows = {m: {r["case_id"]: r for r in read_jsonl(EVAL / f"final-{m}.jsonl")} for m in MODELS
            if (EVAL / f"final-{m}.jsonl").exists()}
    models = [m for m in MODELS if m in rows]
    scored = {m: {c: score_row(cases[c], rows[m].get(c)) for c in cases} for m in models}
    # Baselines: copy-the-input (synthetic) and raw ASR / normalized text (real audio).
    copy = {c: score_row(cases[c], {"model_only": cases[c]["model_input"], "delivered": cases[c]["model_input"],
                                    "path": "llm"}) for c in cases}
    raw = {c: S.score_real(cases[c], {"normalized": cases[c]["model_input"]}, cases[c].get("raw_asr") or "")
           for c in cases if cases[c]["source"] in ("disfluencyspeech", "fleurs")}
    families = {c: cases[c].get("family_id", c) for c in cases}
    slices = {
        "synthetic": [c for c in cases if cases[c]["source"] == "synthetic"],
        "synthetic_repair": [c for c in cases if cases[c]["source"] == "synthetic" and not cases[c].get("is_noop")],
        "synthetic_noop": [c for c in cases if cases[c]["source"] == "synthetic" and cases[c].get("is_noop")],
        "longform": [c for c in cases if cases[c]["source"] == "synthetic_longform"],
        "disfluencyspeech": [c for c in cases if cases[c]["source"] == "disfluencyspeech"],
        "fleurs": [c for c in cases if cases[c]["source"] == "fleurs"],
        "fixtures": [c for c in cases if cases[c]["source"] == "localflow_fixtures"],
    }
    by_cat = defaultdict(list)
    by_profile = defaultdict(list)
    for c in slices["synthetic"]:
        by_cat[cases[c]["category"]].append(c)
        by_profile[str(cases[c].get("destination_profile"))].append(c)
    agg = {}
    for m in models:
        agg[m] = {}
        for sname, ids in slices.items():
            agg[m][sname] = {mode: aggregate(ids, cases, scored, m, mode) for mode in ("model_only", "delivered", "teacher_forced")}
            agg[m][sname]["engine"] = engine_stats(ids, rows[m])
        # Multi-window dictations: the runner keeps the first window's raw proposal
        # only, so model-only text is incomplete there; delivered text is whole.
        agg[m]["longform"]["model_only"] = {"n": 0, "not_computable": "model-only text covers the first cleanup window only"}
        agg[m]["longform"]["teacher_forced"] = {"n": 0}
        agg[m]["by_category"] = {k: {mode: aggregate(v, cases, scored, m, mode) for mode in ("model_only", "delivered")}
                                 for k, v in sorted(by_cat.items())}
        agg[m]["by_profile"] = {k: {mode: aggregate(v, cases, scored, m, mode) for mode in ("model_only", "delivered")}
                                for k, v in sorted(by_profile.items())}
        agg[m]["latency"] = latency(list(rows[m].values()))
    baselines = {"copy_input": {s: aggregate(ids, cases, {"copy": copy}, "copy", "delivered")
                                for s, ids in slices.items() if s != "fixtures"},
                 "raw_asr": {s: _agg_real(raw, slices[s]) for s in ("disfluencyspeech", "fleurs")},
                 "normalized_input": {s: _agg_real({c: S.score_real(cases[c], {"normalized": cases[c]["model_input"]},
                                                                     cases[c]["model_input"]) for c in slices[s]}, slices[s])
                                      for s in ("disfluencyspeech", "fleurs")}}
    # Paired comparisons.
    comps = {}
    pairs = [("B", "A"), ("C", "A"), ("C", "B")]
    for x, y in pairs:
        if x not in models or y not in models:
            continue
        key = f"{x}-{y}"
        syn, rep = slices["synthetic"], slices["synthetic_repair"]
        comps[key] = {
            "model_only_damage": boot(metric_map(syn, scored, y, "model_only", "damage"),
                                      metric_map(syn, scored, x, "model_only", "damage"), families),
            "delivered_damage": boot(metric_map(syn, scored, y, "delivered", "damage"),
                                     metric_map(syn, scored, x, "delivered", "damage"), families),
            "delivered_repair_success": boot(metric_map(rep, scored, y, "delivered", "repair_success"),
                                             metric_map(rep, scored, x, "delivered", "repair_success"), families),
            "model_only_repair_success": boot(metric_map(rep, scored, y, "model_only", "repair_success"),
                                              metric_map(rep, scored, x, "model_only", "repair_success"), families),
            "noop_preserved_model_only": boot(metric_map(slices["synthetic_noop"], scored, y, "model_only", "noop_preserved"),
                                              metric_map(slices["synthetic_noop"], scored, x, "model_only", "noop_preserved"), families),
        }
        for src in ("disfluencyspeech", "fleurs"):
            ids = slices[src]
            comps[key][f"{src}_unauthorized_edit_model_only"] = boot(
                metric_map(ids, scored, y, "model_only", "unauthorized_edit"),
                metric_map(ids, scored, x, "model_only", "unauthorized_edit"), families)
            comps[key][f"{src}_wer_delivered"] = boot(wer_map(ids, scored, y, "delivered"),
                                                      wer_map(ids, scored, x, "delivered"), families, ratio=True)
    decision = decide(models, agg, comps)
    summary = {"created": utc_now(), "models": models, "slices": {k: len(v) for k, v in slices.items()},
               "aggregates": agg, "baselines": baselines, "comparisons": comps, "decision": decision,
               "cold_loads": read_json(EVAL / "cold_loads.json", {}), "fidelity": read_json(EVAL / "fidelity.json", {}),
               "artifact_sizes": read_json(EVAL / "artifact_sizes.json", {}), "pipeline": pipeline_summary(models),
               "judge": judge_summary(), "provenance": provenance()}
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "summary.json", summary)
    write_json(OUT / "cases.json", explorer_rows(cases, rows, scored, models))
    return decision


def _agg_real(scored_map, ids):
    rows = [scored_map[c] for c in ids if c in scored_map]
    we, ww = sum(r.get("wer_errors", 0) for r in rows), sum(r.get("wer_words", 0) for r in rows)
    return {"n": len(rows), "wer": round(100 * we / ww, 2) if ww else None,
            "unauthorized_edit": pct(sum(r["unauthorized_edit"] for r in rows) / len(rows)) if rows else None}


def decide(models, agg, comps) -> dict:
    rules = CONFIG["rules"]
    out = {"rules_sha256": sha256_json(rules), "candidates": {}}
    if "A" not in models:
        return {**out, "outcome": "insufficient_evidence", "reason": "incumbent evaluation missing"}
    lat_a = agg["A"]["latency"]["total_cleanup_ms"]["p95"]
    cold = read_json(EVAL / "cold_loads.json", {})
    cold_med = {m: statistics.median(x["process_to_ready_ms"] for x in v) for m, v in cold.items() if v}
    for x in ("B", "C"):
        if x not in models:
            out["candidates"][x] = {"status": "unavailable", "eligible": False}
            continue
        c = comps[f"{x}-A"]
        upper = lambda k, thr: None if c[k]["ci95_pp"][1] is None else c[k]["ci95_pp"][1] <= thr
        checks = {
            "R1a_model_only_damage": upper("model_only_damage", rules["meaning"]["model_only_damage_upper_ci_pp"]),
            "R1b_delivered_damage": upper("delivered_damage", rules["meaning"]["delivered_damage_upper_ci_pp"]),
        }
        for src in ("disfluencyspeech", "fleurs"):
            checks[f"R1c_{src}_unauthorized_edits"] = upper(f"{src}_unauthorized_edit_model_only",
                                                            rules["meaning"]["real_audio_unauthorized_edit_upper_ci_pp"])
            checks[f"R1c_{src}_wer"] = upper(f"{src}_wer_delivered", rules["meaning"]["real_audio_wer_upper_ci_pp"])
        fa = agg["A"]["fixtures"]["delivered"].get("fixture_pass")
        fx = agg[x]["fixtures"]["delivered"].get("fixture_pass")
        checks["R1d_fixtures_not_below_A"] = fx is not None and fa is not None and fx >= fa
        lo = c["delivered_repair_success"]["ci95_pp"][0]
        checks["R2_delivered_repair_gain"] = None if lo is None else lo > rules["useful_cleanup"]["delivered_repair_success_lower_ci_pp"]
        lat_x = agg[x]["latency"]["total_cleanup_ms"]["p95"]
        checks["R3_warm_p95"] = lat_x is not None and lat_a is not None and lat_x <= rules["responsiveness"]["warm_p95_max_ratio"] * lat_a
        checks["R3_cold_load"] = (x in cold_med and "A" in cold_med and
                                  cold_med[x] <= rules["responsiveness"]["cold_load_max_ratio"] * cold_med["A"])
        unevaluable = [k for k, v in checks.items() if v is None and k.startswith(("R1", "R2"))]
        meaning = all(v for k, v in checks.items() if k.startswith("R1"))
        useful = bool(checks["R2_delivered_repair_gain"])
        fast = bool(checks["R3_warm_p95"] and checks["R3_cold_load"])
        out["candidates"][x] = {"checks": checks, "meaning_ok": meaning, "useful_ok": useful, "fast_ok": fast,
                                "eligible": meaning and useful, "unevaluable": unevaluable}
    b, cc = out["candidates"].get("B", {}), out["candidates"].get("C", {})
    c_over_b = None
    if b.get("eligible") and cc.get("eligible") and "C-B" in comps:
        cb = comps["C-B"]
        c_over_b = cb["delivered_repair_success"]["ci95_pp"][0] > rules["c_over_b"]["repair_success_lower_ci_pp"] and \
            cb["model_only_damage"]["ci95_pp"][1] <= rules["c_over_b"]["damage_upper_ci_pp"]
    out["c_over_b"] = c_over_b
    if b.get("eligible") and not c_over_b:
        outcome = "switch_to_B" if b.get("fast_ok") else "consider_B"
    elif cc.get("eligible"):
        outcome = "consider_C"
    else:
        outcome = "keep_A"
    if outcome == "consider_B":
        outcome = "keep_A"
        out["note"] = "B met meaning and cleanup rules but not responsiveness; rules map that to consider, " \
                      "and 'consider B' is not an allowed outcome, so A is kept"
    if outcome == "keep_A" and any(cand.get("unevaluable") for cand in out["candidates"].values()):
        outcome = "insufficient_evidence"
        out["note"] = "a required rule could not be evaluated: " + ", ".join(
            f"{k}: {v['unevaluable']}" for k, v in out["candidates"].items() if v.get("unevaluable"))
    out["outcome"] = outcome
    return out


def pipeline_summary(models) -> dict:
    out = {}
    for m in models:
        rows = read_jsonl(EVAL / f"pipeline-{m}.jsonl")
        if not rows:
            continue
        f = lambda k: {"median": round(statistics.median(r[k] for r in rows), 1), "p95": round(quant([r[k] for r in rows], .95), 1)}
        out[m] = {"n": len(rows), "asr_ms": f("asr_ms"), "normalize_ms": f("normalize_ms"),
                  "generation_ms": f("generation_ms"), "validation_ms": f("validation_ms"),
                  "cleanup_ms": f("cleanup_ms"), "pipeline_ms": f("pipeline_ms"),
                  "audio_s_median": round(statistics.median(r["audio_s"] for r in rows), 2)}
    return out


def judge_summary() -> dict:
    j = read_json(EVAL / "judge.json")
    if not j:
        return {"status": "not_run"}
    out = {"judge_model": j["judge_model"], "rated_cases": j["rated"], "status": j["status"], "by_model": {}}
    for m in MODELS:
        rs = [r for r in j["ratings"] if r["model"] == m]
        if not rs:
            continue
        out["by_model"][m] = {"n": len(rs), "meaning_preserved": pct(sum(r["meaning_preserved"] for r in rs) / len(rs)),
                              "cleanup": dict(Counter(r["cleanup"] for r in rs)),
                              "problems": dict(Counter(p for r in rs for p in r["problems"] if p != "none"))}
    return out


def provenance() -> dict:
    from .batches import ledger_totals
    return {"incumbent": read_json(ART / "incumbent.json"), "recipe_check": read_json(ART / "export" / "recipe_check.json"),
            "C": read_json(ART / "export" / "C_identity.json"), "selection": read_json(ART / "train" / "selection.json"),
            "freeze": read_json(ART / "frozen" / "freeze.json"), "dataset": read_json(ART / "dataset" / "stats.json"),
            "claude": ledger_totals(), "config": {k: CONFIG[k] for k in ("models", "claude", "targets", "training", "evaluation", "rules")},
            "eval_meta": {m: read_json(EVAL / f"final-{m}.meta.json") for m in MODELS},
            "training_metrics": read_jsonl(ART / "train" / "main" / "metrics.jsonl"),
            "smoke": {"train": read_json(ART / "train" / "smoke" / "train_report.json"),
                      "reload": read_json(ART / "train" / "smoke" / "reload_report.json")},
            "real_audio": {"prepare": read_json(ART / "real" / "prepare_report.json"),
                           "asr": read_json(ART / "real" / "asr_report.json")}}


def explorer_rows(cases, rows, scored, models) -> list[dict]:
    out = []
    for cid, c in cases.items():
        rec = {"id": cid, "src": c["source"], "cat": c.get("category"), "profile": c.get("destination_profile"),
               "noop": c.get("is_noop"), "input": c["model_input"], "raw": c.get("raw_asr"),
               "target": c.get("target") or c.get("lexical_reference") or (c.get("contract_refs") or {}).get("ref_keep"),
               "target_kind": {"synthetic": "synthetic gold, machine-generated and verified",
                               "disfluencyspeech": "machine-derived from DisfluencySpeech annotations, fillers removed",
                               "fleurs": "FLEURS normalized transcription, lexical only, no punctuation",
                               "localflow_fixtures": "LocalFlow fixture expectations",
                               "synthetic_longform": "joined synthetic gold"}.get(c["source"], "reference"),
               "facts": [f["text"] for f in c.get("critical_facts", [])][:12], "gold": c.get("gold_lines"),
               "verification": c.get("verification"), "out": {}}
        if c["source"] == "localflow_fixtures":
            rec["target"] = "expect: " + "; ".join("/".join(g) for g in c.get("expect", [])) + \
                            (" | forbid: " + ", ".join(c.get("forbid", [])) if c.get("forbid") else "")
        for m in models:
            r = rows[m].get(cid)
            if not r:
                continue
            sc = scored[m][cid]
            basis = "delivered" if c["source"] == "synthetic_longform" else "model_only"
            flags = sorted(k for k in ("damage", "facts_changed", "hallucination", "omission", "negation_changed",
                                       "missing_ending", "unwanted_answer", "unauthorized_edit")
                           if (sc.get(basis) or {}).get(k))
            rec["out"][m] = {"mo": r.get("model_only"), "dl": r.get("delivered"), "path": r.get("path"),
                             "mo_partial": c["source"] == "synthetic_longform" or None,
                             "ms": round(r.get("total_cleanup_ms") or 0), "flags": flags,
                             "repair": (sc.get("delivered") or {}).get("repair_success"),
                             "fx": (sc.get("delivered") or {}).get("fixture_pass")}
        outs = {m: (o["mo"] or "").strip() for m, o in rec["out"].items()}
        rec["disagree"] = len(set(outs.values())) > 1
        out.append(rec)
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
