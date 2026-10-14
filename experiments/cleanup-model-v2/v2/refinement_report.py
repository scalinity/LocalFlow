"""Render the selected refinement from complete, frozen comparison records."""
from __future__ import annotations

import collections
import json
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from .common import *
from .refinement import RUN, DATASET, require_final
from .score import aggregate, canon, real, synthetic
from .strict_score import SCORER_VERSION, aggregate as strict_aggregate


def pct(value):
    return "Not run" if value is None else f"{100 * value:.2f}%"


def build():
    cases_path = RUN / "final-cases.jsonl"
    freeze = require_final(cases_path, candidate=True)
    comparison = read_json(RUN / "goal-comparison.json", {})
    readiness = comparison.get("readiness", {})
    receipt = {k: v for k, v in readiness.items() if k != "receipt_sha256"}
    if (readiness.get("status") != "COMPLETE_MATCHED_INPUTS"
            or readiness.get("output_text_binding") != "VERIFIED"
            or readiness.get("cases_sha256") != freeze["cases_sha256"]
            or readiness.get("final_freeze_sha256") != file_sha256(RUN / "final-freeze.json")
            or readiness.get("receipt_sha256") != sha256_text(json.dumps(receipt, sort_keys=True, ensure_ascii=False))
            or not readiness.get("input_hashes")
            or any(file_sha256(ART / path) != digest for path, digest in readiness["input_hashes"].items())
            or not readiness.get("scoring_source_hashes")
            or any(file_sha256(ROOT / path) != digest for path, digest in readiness["scoring_source_hashes"].items())):
        raise RuntimeError("A current comparison receipt must bind judgments to the exact output text")
    selection = read_json(RUN / "candidate-selection.json")
    decision = read_json(RUN / "decision.json")
    if not decision:
        raise RuntimeError("The final comparison has no recorded interpretation")
    candidate = selection["candidate"]["key"]
    models = ["C", "F", candidate]
    cases = read_jsonl(cases_path)
    byid = {c["case_id"]: c for c in cases}
    rows = {k: read_jsonl(ART / "eval" / f"refined-{k}.jsonl") for k in models}
    for key, value in rows.items():
        if len(value) != len(byid) or {r["case_id"] for r in value} != set(byid):
            raise RuntimeError("Incomplete or duplicate final outputs: " + key)
        meta = read_json(ART / "eval" / f"refined-{key}.meta.json")
        if (not meta or not meta["runs"][-1].get("finished")
                or meta["identity"]["model"] != key
                or meta["identity"]["cases_sha256"] != freeze["cases_sha256"]
                or meta["identity"]["model_content_digest"] != freeze["models"][key]["content_digest"]
                or meta["identity"]["engine"] != freeze["models"][key]["engine"]):
            raise RuntimeError("Final output identity does not match the selected model: " + key)
        if key == candidate:
            expected = {Path(p).name: digest for p, digest in freeze["source_hashes"].items()
                        if Path(p).name != "model.py"}
            if (meta["identity"]["engine_source_sha256"] != expected
                    or meta["identity"]["inference_source_sha256"] != freeze["source_hashes"]["localflow/v2/cleanup/model.py"]):
                raise RuntimeError("Candidate output source does not match the final freeze")
    judge_identity = read_json(ART / "judge/refined-judge/identity.json", {})
    if (judge_identity.get("cases_sha256") != freeze["cases_sha256"]
            or judge_identity.get("models") != models or judge_identity.get("prefix") != "refined"):
        raise RuntimeError("Blinded assessment belongs to a different comparison")
    judgments = read_jsonl(ART / "judge/refined-judge/verdicts.jsonl")
    judges = {(v["case_id"], v["model"], v["stage"]): v for v in judgments}
    required = {(c["case_id"], k, s) for c in cases for k in models for s in ("model_only", "delivered")}
    if set(judges) != required or len(judges) != len(judgments) or any(v["status"] != "judged" for v in judges.values()):
        raise RuntimeError("Complete blinded assessment is required")
    inspection_path = RUN / "engineering-flag-review.json"
    if (not inspection_path.is_file()
            or file_sha256(inspection_path) != (comparison.get("engineering_inspection") or {}).get("file_sha256")):
        raise RuntimeError("Engineering inspection changed after the comparison")
    inspected = read_json(inspection_path, {}).get("cases", {})
    flagged = {v["case_id"] for v in judgments if
               (any(v["verdict"][f] for f in ("semantic_damage", "critical_fact_changed", "hallucination", "unwanted_edit"))
                or v["verdict"]["cleanup"] == "wrong")}
    for key in models:
        for stage in ("model_only", "delivered"):
            mechanical = strict_aggregate(cases, rows[key], stage)
            flagged.update(v["case_id"] for v in mechanical["cases"]
                           if v["introduced_edit_flag"] or v["unclassified_source_omissions"])
    output_maps = {key: {r["case_id"]: r for r in rows[key]} for key in models}
    for case in cases:
        if case["origin"] != "synthetic":
            continue
        cid = case["case_id"]
        for stage in ("model_only", "delivered"):
            if case["is_noop"] and any(output_maps[key][cid][stage] != case["model_input"] for key in models):
                flagged.add(cid)
            if (canon(output_maps[candidate][cid][stage] or "") != canon(case["target"])
                    and any(canon(output_maps[key][cid][stage] or "") == canon(case["target"]) for key in ("C", "F"))):
                flagged.add(cid)
    review_fields = ("introduced_semantic_damage", "critical_fact_change", "introduced_hallucination", "meaning_uncertain")
    if (not flagged.issubset(inspected) or set(inspected) - set(byid)
            or any(set(models) - set(v) for v in inspected.values())
            or any(type(v[key].get(field)) is not bool for v in inspected.values()
                   for key in models for field in review_fields)):
        raise RuntimeError("Flagged cases need a matched engineering inspection")
    previous = RUN / "previous-report"
    saved = read_json(previous / "preserved.json")["files"]
    if any(file_sha256(previous / name) != digest for name, digest in saved.items()):
        raise RuntimeError("An earlier report snapshot changed")
    report = read_json(previous / "report-data.json")
    report.pop("fresh_summary", None)
    previous_measurements = read_json(previous / "measurements.json")
    aggs = {k: aggregate(cases, rows[k]) for k in models}
    maps = {k: {r["case_id"]: r for r in value} for k, value in rows.items()}
    examples, categories, scopes, cleanup_scopes, strict_scopes, inspection_scopes = [], {}, {}, {}, {}, {}
    strict_records = {}
    for case in cases:
        cid = case["case_id"]
        outputs = {}
        for key in models:
            row = maps[key][cid]
            score = synthetic(case, row["delivered"], True) if case["origin"] == "synthetic" else real(case, row["delivered"])
            outputs[key] = {"delivered": row["delivered"], "model_only": row.get("model_only"),
                "path": row["path"], "ms": row["total_cleanup_ms"], "failures": row.get("validator_failures", []),
                "reference_complete": score.get("reference_complete"), "damage": score.get("damage"),
                "reference_complete_by_stage": {s: canon(row.get(s) or "") == canon(case["target"])
                    if case["origin"] == "synthetic" else None for s in ("model_only", "delivered")},
                "assessment": {s: judges[(cid, key, s)]["verdict"] for s in ("model_only", "delivered")}}
        examples.append({"id": cid, "origin": case["origin"], "category": case["category"],
            "input": case["model_input"], "raw_input": case.get("raw_input") if case["origin"] == "real_audio" else None,
            "target": case.get("target") or case.get("raw_transcription"), "is_noop": case.get("is_noop", False),
            "reference_label": "Fixed independent synthetic target" if case["origin"] == "synthetic" else "Pinned public transcription",
            "inspection_note": inspected.get(cid, {}).get("reason"), "outputs": outputs})
    for origin in ("synthetic", "real_audio"):
        cohort = [c for c in cases if c["origin"] == origin]
        ids = {c["case_id"] for c in cohort}
        categories[origin] = {}
        for category in sorted({c["category"] for c in cohort}):
            subset = [c for c in cohort if c["category"] == category]
            subset_ids = {c["case_id"] for c in subset}
            item = {"n": len(subset)}
            for key in models:
                values = aggregate(subset, [r for r in rows[key] if r["case_id"] in subset_ids])[origin]
                field = "reference_complete" if origin == "synthetic" else "wer"
                item[key] = {s: values[s].get(field) for s in ("model_only", "delivered")}
            categories[origin][category] = item
        reviewed = [v for cid, v in inspected.items() if byid[cid]["origin"] == origin]
        inspection_scopes[origin] = [[key, len(reviewed),
            sum(v[key]["introduced_semantic_damage"] or v[key]["critical_fact_change"] for v in reviewed),
            sum(v[key]["introduced_hallucination"] for v in reviewed),
            sum(v[key]["meaning_uncertain"] for v in reviewed)] for key in models]
        for stage in ("model_only", "delivered"):
            label = origin + ":" + stage
            scopes[label], cleanup_scopes[label], strict_scopes[label] = [], [], []
            for key in models:
                values = [judges[(c["case_id"], key, stage)]["verdict"] for c in cohort]
                scopes[label].append([key, len(values), *[sum(v[f] for v in values) for f in
                    ("semantic_damage", "critical_fact_changed", "hallucination", "unwanted_edit")],
                    sum(v["punctuation"] == "improved" for v in values), sum(v["punctuation"] == "worse" for v in values)])
                cleanup_scopes[label].append([key, len(values), *[sum(v["cleanup"] == status for v in values)
                    for status in ("complete", "partial", "none_needed", "wrong")],
                    *[sum(v["self_correction"] == status for v in values) for status in ("resolved", "unresolved", "wrong")]])
                strict = strict_aggregate(cohort, [r for r in rows[key] if r["case_id"] in ids], stage)
                strict_records[label + ":" + key] = {k: v for k, v in strict.items() if k != "cases"}
                strict_scopes[label].append([key, strict["n"], strict["available"], *[strict["counts"][f] for f in
                    ("unsupported_additions", "introduced_required_omissions", "unclassified_source_omissions", "identifier_count_changes",
                     "unresolved_corrections", "metadata_issues")]])
    audio = [c for c in cases if c["origin"] == "real_audio"]
    baseline = []
    for label, field in (("Raw Parakeet", "raw_input"), ("After normalization", "model_input")):
        values = [real(c, c[field]) for c in audio]
        e, n = sum(v["wer_errors"] for v in values), sum(v["wer_words"] for v in values)
        ce, cn = sum(v["cer_errors"] for v in values), sum(v["cer_chars"] for v in values)
        baseline.append([label, len(values), pct(e/n), f"{e}/{n}", pct(ce/cn), f"{ce}/{cn}"])
    runtime, long_rows = [], []
    artifact_sizes = comparison.get("artifact_sizes_bytes", {})
    if (set(artifact_sizes) != set(models)
            or any(type(size) is not int or size <= 0 for size in artifact_sizes.values())):
        raise RuntimeError("Recorded artifact sizes are incomplete")
    long_cases = [c for c in cases if c["origin"] == "synthetic" and len(c["model_input"].split()) > 200]
    long_ids = {c["case_id"] for c in long_cases}
    for key in models:
        syn, aud = aggs[key]["synthetic"]["runtime"], aggs[key]["real_audio"]["runtime"]
        size = artifact_sizes[key]
        runtime.append([key, f"{syn['median_ms']:.0f}", f"{syn['p95_ms']:.0f}",
            f"{aud['median_ms']:.0f}", f"{aud['p95_ms']:.0f}",
            f"{max(syn['peak_mlx_bytes'],aud['peak_mlx_bytes'])/1e9:.2f}",
            f"{max(syn['peak_rss_bytes'],aud['peak_rss_bytes'])/1e9:.2f}", f"{size/1e9:.2f}"])
        if long_cases:
            values = aggregate(long_cases, [r for r in rows[key] if r["case_id"] in long_ids])["synthetic"]
            js = [judges[(c["case_id"], key, "delivered")]["verdict"] for c in long_cases]
            long_rows.append([key, len(long_cases), pct(values["model_only"]["reference_repair"]["value"]),
                pct(values["delivered"]["reference_repair"]["value"]), sum(v["cleanup"] == "complete" for v in js),
                sum(v["semantic_damage"] for v in js), pct(values["runtime"]["fallback_rate"]),
                f"{values['runtime']['median_ms']:.0f}", f"{values['runtime']['p95_ms']:.0f}"])
    hero = next((c for c in examples if c["id"] == decision.get("hero_case_id")), None)
    report.update(model_order=models, model_names={"C": "C · Installed reference", "F": "F · Previous candidate", candidate: candidate + " · Focused refinement"},
        best_key=decision["best_key"], candidate_key=candidate, recommendation=decision, aggregates=aggs, examples=examples, categories=categories,
        created_label=datetime.now(ZoneInfo("America/New_York")).strftime("%B %d, %Y · %H:%M ET"),
        intro=f"A fixed comparison of {freeze['synthetic']} independently checked synthetic cases and {freeze['audio']} disjoint public recordings, after targeted data curation, further training, and cleanup-code repairs.",
        history={"href": "previous-494.html", "label": "Earlier 494-case comparison", "note": "Earlier comparisons informed development and remain unchanged.",
                 "links": [{"href": "prior-round.html", "label": "Original 701-case comparison"}]},
        hero={"input": hero["input"], "C": hero["outputs"]["C"]["delivered"], "candidate": hero["outputs"][candidate]["delivered"],
              "candidate_label": candidate + " · Focused refinement", "caption": hero["id"] + " · selected example, not a typical-effect claim"} if hero else None,
        headlines=decision["headlines"], quality_findings=decision["quality_findings"], engine_findings=decision["engine_findings"],
        limitations=decision["limitations"], engine_note=decision["engine_note"], runtime_note=decision["runtime_note"],
        runtime_caveat=decision["runtime_caveat"], checks=read_json(RUN / "checks.json"),
        configuration=read_json(RUN / "reproducibility.json"), commands=read_json(RUN / "reproduction-commands.json"),
        deployment=read_json(RUN / "deployment.json"), data_findings=decision["data_findings"], data_method=decision["data_method"],
        provenance="Frozen model identities, source hashes, labels, outputs, batch receipts and case inspections remain in the separate local refinement records. No candidate was installed and no application restarted.")
    report["judge"].update(scopes=scopes, cleanup_scopes=cleanup_scopes)
    report["inspection"].update(scopes=inspection_scopes, note=decision["inspection_note"])
    report["strict"] = {"columns": ["Model", "Cases", "Available", "Added-word flags", "Required-word omission flags", "Unclassified omissions", "Identifier flags", "Unresolved corrections", "Metadata issues"],
        "scopes": strict_scopes, "note": f"{SCORER_VERSION} checks source-anchored word and literal counts, including independently proved incomplete-opening deletions. These are mechanical flags, not meaning judgments; unclassified omissions and metadata issues remain visible. Unchanged fallbacks can miss repairs without introducing an edit."}
    report["audio_baseline"].update(rows=baseline, note=decision["audio_note"])
    report["long_form"].update(rows=long_rows, note=decision["long_note"])
    report["runtime_table"].update(rows=runtime)
    report["timing_sample"] = read_json(RUN / "timing-report.json")
    report["ablation"] = read_json(RUN / "development-report.json")
    report["rejections"]["rows"] = [[key, reason, n] for key in models for reason, n in collections.Counter(
        f for r in rows[key] for f in r.get("validator_failures", [])).most_common()]
    training_report = read_json(RUN / "training-report.json")
    for field in ("curves", "scaling_series", "scaling_table", "scaling_note", "scaling_x_label"):
        report[field] = training_report[field]
    ledger = read_json(ART / "claude/ledger.json")
    actual = sum(e.get("actual_usd", 0) for e in ledger["entries"].values())
    outstanding = sum(e["max_usd"] for e in ledger["entries"].values() if e["state"] == "outstanding")
    report["cost_table"] = read_json(RUN / "cost-table.json")
    report["cost_headlines"] = [{"value": f"${value:.4f}", "label": label} for value, label in
        ((actual, "Measured version-2 usage"), (actual-previous_measurements["spend_usd"], "Added in this refinement"),
         (outstanding, "Maximum outstanding charge"), (CONFIG["claude"]["spend_cap_usd"]-actual-outstanding, "Remaining under refinement cap"))]
    report["cost_note"] = "Usage is priced from returned token counts and recorded batch rates; billing reconciliation remains unavailable. Totals exclude the version-1 experiment. No credit purchase or payment change occurred."
    summary = {"created": utc_now(), "freeze": {k: v for k, v in freeze.items() if k != "models"},
        "aggregates": aggs, "strict_scores": strict_records, "blinded_assessment": report["judge"],
        "flagged_case_inspection": report["inspection"], "spend_usd": actual, "additional_spend_usd": actual-previous_measurements["spend_usd"],
        "recommendation": decision["title"], "checks": report["checks"],
        "goal_comparison": {"candidate_key": comparison["candidate_key"],
            "status_counts": comparison["status_counts"],
            "goal_status": comparison["goal_status"],
            "receipt_sha256": readiness["receipt_sha256"]},
        "previous_round_aggregates": previous_measurements["aggregates"]}
    destination = ROOT / CONFIG["paths"]["report_dir"]
    shutil.copyfile(previous / "index.html", destination / "previous-494.html")
    shutil.copyfile(previous / "prior-round.html", destination / "prior-round.html")
    payload = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    (destination / "index.html").write_text((EXP / "v2/report_template.html").read_text().replace("__REPORT_DATA__", payload))
    write_json(ART / "results/report-data.json", report)
    write_json(destination / "measurements.json", summary)
    print(json.dumps({"report": str(destination / "index.html"), "cases": len(cases), "spend_usd": actual}))


if __name__ == "__main__":
    build()
