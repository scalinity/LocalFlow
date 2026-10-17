"""Replace the report's comparison surface with the completed fresh round."""
from __future__ import annotations

import collections
import json
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from .common import *
from .score import aggregate, synthetic, real, canon


def pct(value):
    return "Not run" if value is None else f"{100 * value:.2f}%"


def apply(report):
    root = ART / "remediation"
    decision = read_json(root / "decision.json")
    if not decision:
        return report
    cases = read_jsonl(root / "final-cases.jsonl")
    freeze = read_json(root / "freeze.json")
    if not freeze or file_sha256(root / "final-cases.jsonl") != freeze["cases_sha256"]:
        raise RuntimeError("Fresh report input differs from its freeze")
    models = ["C", "E", "F"]
    byid = {c["case_id"]: c for c in cases}
    rows = {k: read_jsonl(ART / "eval" / f"fresh-{k}.jsonl") for k in models}
    if any(len(v) != len(cases) or {r["case_id"] for r in v} != set(byid) for v in rows.values()):
        raise RuntimeError("Fresh evaluation is incomplete")
    judges = read_jsonl(ART / "judge/fresh-judge/verdicts.jsonl")
    judge_map = {(v["case_id"], v["model"], v["stage"]): v for v in judges}
    required = {(c["case_id"], k, s) for c in cases for k in models for s in ("model_only", "delivered")}
    if not required.issubset(judge_map) or any(judge_map[k]["status"] != "judged" for k in required):
        raise RuntimeError("Fresh blinded assessment is incomplete")
    inspected = read_json(root / "engineering-flag-review.json", {}).get("cases", {})
    flagged = {v["case_id"] for v in judges if v["stage"] == "delivered" and
               (any(v["verdict"][f] for f in ("semantic_damage", "critical_fact_changed", "hallucination", "unwanted_edit"))
                or v["verdict"]["cleanup"] == "wrong")}
    if not flagged.issubset(inspected):
        raise RuntimeError("Fresh checker flags require inspection before a recommendation")
    aggs = {k: aggregate(cases, rows[k]) for k in models}
    maps = {k: {r["case_id"]: r for r in v} for k, v in rows.items()}
    examples = []
    for case in cases:
        outputs = {}
        cid = case["case_id"]
        for key in models:
            row = maps[key][cid]
            score = synthetic(case, row["delivered"], True) if case["origin"] == "synthetic" else real(case, row["delivered"])
            outputs[key] = {
                "delivered": row["delivered"], "model_only": row.get("model_only"),
                "path": row["path"], "ms": row["total_cleanup_ms"], "failures": row.get("validator_failures", []),
                "reference_complete": score.get("reference_complete"), "damage": score.get("damage"),
                "reference_complete_by_stage": {"delivered": score.get("reference_complete"),
                    "model_only": canon(row.get("model_only") or "") == canon(case["target"]) if case["origin"] == "synthetic" else None},
                "assessment": {s: judge_map[(cid, key, s)]["verdict"] for s in ("model_only", "delivered")}}
        examples.append({
            "id": cid, "origin": case["origin"], "category": case["category"], "input": case["model_input"],
            "raw_input": case["raw_input"] if case["origin"] == "real_audio" and case["raw_input"] != case["model_input"] else None,
            "inspection_note": inspected.get(cid, {}).get("reason"), "target": case.get("target") or case.get("raw_transcription"),
            "reference_label": "Frozen fresh synthetic target" if case["origin"] == "synthetic" else "Fixed public transcription",
            "is_noop": case.get("is_noop", False), "outputs": outputs})
    best = decision["best_key"]
    hero = next(c for c in examples if c["id"] == decision["hero_case_id"])
    cats = {}
    for origin in ("synthetic", "real_audio"):
        cats[origin] = {}
        for category in sorted({c["category"] for c in cases if c["origin"] == origin}):
            subset = [c for c in cases if c["origin"] == origin and c["category"] == category]
            ids = {c["case_id"] for c in subset}
            entry = {"n": len(subset)}
            for key in models:
                measured = aggregate(subset, [r for r in rows[key] if r["case_id"] in ids])[origin]
                metric = "reference_complete" if origin == "synthetic" else "wer"
                entry[key] = {s: measured[s].get(metric) for s in ("model_only", "delivered")}
            cats[origin][category] = entry
    scopes, cleanup_scopes, inspections = {}, {}, {}
    for origin in ("synthetic", "real_audio"):
        inspected_cases = [v for cid, v in inspected.items() if byid[cid]["origin"] == origin]
        inspections[origin] = [[k, len(inspected_cases),
            sum(v[k].get("introduced_semantic_damage", False) or v[k].get("critical_fact_change", False) for v in inspected_cases),
            sum(v[k].get("introduced_hallucination", False) for v in inspected_cases),
            sum(v[k].get("meaning_uncertain", False) for v in inspected_cases)] for k in models]
        for stage in ("model_only", "delivered"):
            checks, cleanup = [], []
            for key in models:
                selected = [judge_map[(c["case_id"], key, stage)]["verdict"] for c in cases if c["origin"] == origin]
                checks.append([key, len(selected), *[sum(v[f] for v in selected) for f in
                    ("semantic_damage", "critical_fact_changed", "hallucination", "unwanted_edit")],
                    sum(v["punctuation"] == "improved" for v in selected), sum(v["punctuation"] == "worse" for v in selected)])
                cleanup.append([key, len(selected), *[sum(v["cleanup"] == status for v in selected)
                    for status in ("complete", "partial", "none_needed", "wrong")],
                    *[sum(v["self_correction"] == status for v in selected) for status in ("resolved", "unresolved", "wrong")]])
            scopes[origin + ":" + stage] = checks
            cleanup_scopes[origin + ":" + stage] = cleanup
    audio_cases = [c for c in cases if c["origin"] == "real_audio"]
    audio_baseline = []
    for label, field in (("Raw Parakeet", "raw_input"), ("After upstream normalization", "model_input")):
        metrics = [real(c, c[field]) for c in audio_cases]
        errors = sum(m["wer_errors"] for m in metrics)
        words = sum(m["wer_words"] for m in metrics)
        chars = sum(m["cer_chars"] for m in metrics)
        char_errors = sum(m["cer_errors"] for m in metrics)
        audio_baseline.append([label, len(metrics), pct(errors / words), f"{errors}/{words}", pct(char_errors / chars), f"{char_errors}/{chars}"])
    identities = read_json(ART / "results/model-identities.json")
    runtime, ablation = [], []
    for key in models:
        syn, audio = aggs[key]["synthetic"], aggs[key]["real_audio"]
        rt, rr = syn["runtime"], audio["runtime"]
        ident = identities["D" if key == "F" else key]
        runtime.append([key, f"{rt['median_ms']:.0f}", f"{rt['p95_ms']:.0f}", f"{rr['median_ms']:.0f}", f"{rr['p95_ms']:.0f}",
            f"{max(rt['peak_mlx_bytes'], rr['peak_mlx_bytes']) / 1e9:.2f}", f"{max(rt['peak_rss_bytes'], rr['peak_rss_bytes']) / 1e9:.2f}",
            f"{ident['size_bytes'] / 1e9:.2f}"])
        values = syn["delivered"]
        ablation.append([key, *[pct(values.get(f, {}).get("value")) for f in
            ("reference_repair", "punctuation_only_repaired", "noop_preserved")], pct(rt["fallback_rate"]),
            sum(judge_map[(c["case_id"], key, "delivered")]["verdict"]["semantic_damage"] for c in cases if c["origin"] == "synthetic")])
    long_cases = [c for c in cases if len(c["model_input"].split()) > 200]
    long_ids = {c["case_id"] for c in long_cases}
    long_rows = []
    for key in models:
        measured = aggregate(long_cases, [r for r in rows[key] if r["case_id"] in long_ids]) if long_cases else {}
        if "synthetic" not in measured:
            continue
        syn = measured["synthetic"]
        verdicts = [judge_map[(c["case_id"], key, "delivered")]["verdict"] for c in long_cases if c["origin"] == "synthetic"]
        long_rows.append([key, syn["delivered"]["n"], pct(syn["model_only"].get("reference_repair", {}).get("value")),
            pct(syn["delivered"].get("reference_repair", {}).get("value")), sum(v["cleanup"] == "complete" for v in verdicts),
            sum(v["semantic_damage"] for v in verdicts), pct(syn["runtime"]["fallback_rate"]),
            f"{syn['runtime']['median_ms']:.0f}", f"{syn['runtime']['p95_ms']:.0f}"])
    selection = {s: read_json(root / f"synthetic-{s}-selection.json") for s in ("validation", "test")}
    report.update({
        "intro": f"A fresh comparison after repairing restriction attachment and identifier corruption: {freeze['synthetic']} synthetic cases and {freeze['audio']} new public recordings. C is the installed reference; E and F use the same newer weights.",
        "model_order": models, "best_key": best, "recommendation": decision,
        "hero": {"input": hero["input"], "C": hero["outputs"]["C"]["delivered"], "candidate": hero["outputs"][best]["delivered"],
                 "candidate_label": best + " · Repaired candidate", "caption": hero["id"] + " · fresh held-out synthetic example; not a typical-effect claim"},
        "headlines": decision["headlines"], "quality_findings": decision["quality_findings"],
        "aggregates": aggs, "categories": cats, "examples": examples,
        "history": {"href": "prior-round.html", "label": "Read the earlier 701-example comparison", "note": "The earlier cases informed these source fixes. They are development evidence now; all quality tables and examples on this page use the fresh round."},
        "configuration": read_json(root / "reproducibility.json"), "deployment": read_json(root / "deployment.json"),
        "commands": read_json(root / "reproduction-commands.json", []),
        "checks": read_json(root / "checks.json", []),
        "engine_findings": decision["engine_findings"],
        "engine_note": "C uses its recorded engine and installed weights. E uses the recorded separator repair with the newer weights. F uses those same newer weights with updated source. The E-to-F comparison isolates the combined engine and prompt changes; no new training occurred in this round.",
        "runtime_note": "Fresh C/E/F measurements use the same production wrapper, case order, and machine after model loading and warm-up. Timing includes preparatory correction parsing, validation and fallbacks, excluding ASR, app queuing and insertion. MLX allocator peak and process RSS are different memory views; do not add them together. RSS is the process high-water mark and carries earlier peaks across these serial model runs. These are local measurements, not an isolated system benchmark.",
        "limitations": decision["limitations"],
        "fresh_summary": {"freeze": {k: freeze[k] for k in ("synthetic", "audio", "cases_sha256", "source_hashes")},
                          "development_cases": selection["validation"]["kept"], "test_categories": selection["test"]["categories"],
                          "aggregates": aggs, "blinded_scopes": scopes, "cleanup_scopes": cleanup_scopes, "inspection_scopes": inspections}})
    report["audio_baseline"].update(rows=audio_baseline, note=f"Upstream normalization changed {sum(c.get('normalization_changed', False) for c in audio_cases)} of {len(audio_cases)} new recordings. Sentence IDs and decoded-audio hashes were excluded against both earlier rounds before selection. These clips are read speech, with no unseen-speaker or continuous-long-form claim.")
    report["judge"].update(scopes=scopes, cleanup_scopes=cleanup_scopes)
    report["inspection"].update(scopes=inspections,
        columns=["Model", "Cases inspected", "Clear meaning / fact changes", "Unauthorized added words", "Unresolved interpretation"],
        note="Engineering inspection compares C, E and F on the same union of fresh checker-flagged cases and exact-reference regressions against C or E. Checker flags include unwanted edits and wrong cleanup. Raw flags remain available, and ambiguous interpretations are counted separately. This is not independent human adjudication or a count of errors the checker missed.")
    report["long_form"].update(rows=long_rows)
    report["runtime_table"].update(rows=runtime)
    timing = read_json(root / "timing-result.json", {})
    report["runtime_caveat"] = "The beginning of C's full run overlapped an observed image-generation workload. Full-run latency differences therefore include unequal background conditions. No other task was interrupted."
    if timing.get("status") == "PASS":
        measured = timing["measurements"]
        report["timing_sample"] = {
            "columns": ["Model", "Matched cases", "Median ms", "p95 ms", "Changed delivered outputs"],
            "rows": [[k, measured[k]["n"], f"{measured[k]['median_ms']:.0f}",
                      f"{measured[k]['p95_ms']:.0f}", measured[k]["changed_delivered_outputs"]] for k in models],
            "note": "The first 30 frozen synthetic cases were selected before inspecting final candidate quality, then repeated in F/C/E order. The previously observed GPU worker was absent at each model's start and end. This small matched sample is not a representative audio, native end-to-end, or isolated-system benchmark. Changed outputs are compared with the original full run; the quality tables retain that original run."}
        report["fresh_summary"]["matched_timing"] = {
            "status": timing["status"], "n": 30, "order": timing["plan"]["order"],
            "selection": timing["plan"]["selection"],
            "measurements": {k: {field: measured[k][field] for field in
                ("n", "median_ms", "p95_ms", "changed_delivered_outputs", "changed_raw_outputs")} for k in models}}
    elif timing:
        report["runtime_caveat"] += " Matched repeat: " + timing["status"] + ". " + timing.get("reason", "")
        report["fresh_summary"]["matched_timing"] = {"status": timing["status"], "reason": timing.get("reason", "")}
    report["ablation"].update(rows=ablation)
    report["rejections"].update(rows=[[k, reason, n] for k in models for reason, n in collections.Counter(
        f for r in rows[k] for f in r.get("validator_failures", [])).most_common()])
    report["data_findings"].insert(0, {"title": "The newer weights are unchanged", "body": "The curves below document their original training. This follow-up changes the engine and prompt, using a separate development set before freezing fresh final cases."})
    report["data_method"].insert(0, f"This fresh round uses {selection['validation']['kept']} separate development examples. Final synthetic labels use new scenario domains, independent verification, and exact / shingle exclusions against earlier datasets and all returned fresh development pairs. Accepted labels remain even if the engine cannot deliver them. New public recordings come from Google FLEURS, English (United States), validation split, with the recorded CC-BY-4.0 license and pinned revision in the configuration. The following paragraphs describe the original weight-training round.")
    report["data_method"][-1] = "The original training round evaluated 150 DisfluencySpeech recordings and 70 FLEURS sentence families, with 70 separate audio development clips. Those recordings are excluded from this fresh comparison."
    previous_cost = read_json(root / "previous-report/measurements.json")["spend_usd"]
    ledger = read_json(ART / "claude/ledger.json")
    actual = sum(e.get("actual_usd", 0) for e in ledger["entries"].values())
    report["cost_note"] = (f"This repair round added ${actual - previous_cost:.4f}. Totals include the original version-2 training run, generator study, and fresh repair comparison; the version-1 experiment is excluded. Costs use actual returned token usage at verified batch rates. Billing reconciliation remains unavailable; these are metered usage costs, not an invoice. No credit purchase or payment change was performed.")
    report["fresh_summary"]["additional_spend_usd"] = actual - previous_cost
    report["provenance"] = "Fresh inputs, source hashes, batch receipts, raw verdicts, engineering inspection and every output are retained under the separate remediation run. The earlier complete comparison remains available beside this report. No model was installed or application restarted."
    previous = root / "previous-report/index.html"
    if not previous.exists():
        raise RuntimeError("The earlier complete report must remain available")
    shutil.copyfile(previous, ROOT / CONFIG["paths"]["report_dir"] / "prior-round.html")
    return report


def build():
    """Keep earlier measurements verbatim; score only the fresh comparison."""
    root = ART / "remediation"
    report = read_json(root / "previous-report/report-data.json")
    previous = read_json(root / "previous-report/measurements.json")
    if not report or not previous:
        raise RuntimeError("The earlier measurements must be preserved before updating the report")
    ledger = read_json(ART / "claude/ledger.json")
    model_by_entry, requests_by_entry = {}, {}
    for manifest_path in (ART / "claude").glob("*/manifest.json"):
        manifest = read_json(manifest_path)
        model = read_json(manifest_path.parent / "pricing.json", {}).get("model", "Unrecorded model")
        for attempt in manifest["attempts"]:
            model_by_entry[attempt["ledger_key"]] = model
            requests_by_entry[attempt["ledger_key"]] = len(attempt.get("custom_ids", []))
    spending = collections.defaultdict(lambda: collections.Counter())
    for key, entry in ledger["entries"].items():
        row = spending[model_by_entry.get(key, "Unrecorded model") + " / " + entry["purpose"]]
        row["cost"] += entry.get("actual_usd", 0)
        row["requests"] += requests_by_entry.get(key, 0)
        for field in ("input", "output", "cache_read", "cache_write"):
            row[field] += entry.get("usage", {}).get(field, 0)
    actual = sum(v["cost"] for v in spending.values())
    outstanding = sum(e["max_usd"] for e in ledger["entries"].values() if e["state"] == "outstanding")
    budget = CONFIG["claude"]["spend_cap_usd"]
    report["cost_table"]["rows"] = [[k, v["requests"], *[f"{v[f]:,}" for f in
        ("input", "output", "cache_read", "cache_write")], f"${v['cost']:.4f}"] for k, v in spending.items()]
    report["cost_headlines"] = [{"value": value, "label": label} for value, label in (
        (f"${actual:.4f}", "Measured usage priced at batch rates"), (f"${budget:.2f}", "Active total budget"),
        (f"${outstanding:.2f}", "Maximum outstanding batch charge"),
        (f"${budget - actual - outstanding:.2f}", "Unspent budget after outstanding requests"))]
    report["created_label"] = datetime.now(ZoneInfo("America/New_York")).strftime("%B %d, %Y · %H:%M ET")
    report = apply(report)
    destination = ROOT / CONFIG["paths"]["report_dir"] / "index.html"
    payload = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    destination.write_text((EXP / "v2/report_template.html").read_text().replace("__REPORT_DATA__", payload))
    write_json(ART / "results/report-data.json", report)
    write_json(destination.with_name("measurements.json"), {
        "created": utc_now(), "recommendation": report["recommendation"]["title"],
        "aggregates": report["aggregates"], "spend_usd": actual, "budget_usd": budget,
        "new_accepted_families": previous["new_accepted_families"], "checks": report["checks"],
        "blinded_assessment": report["judge"], "flagged_case_inspection": report["inspection"],
        "fresh_comparison": report["fresh_summary"], "previous_round_aggregates": previous["aggregates"]})
    print(json.dumps({"report": str(destination), "bytes": destination.stat().st_size,
                      "examples": len(report["examples"]), "spend_usd": actual}))
