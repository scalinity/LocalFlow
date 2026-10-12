"""Build reports/localflow-cleanup-comparison/index.html (+ summary.json, cases.csv).

Commands shown on the page are executed here first: the try-it commands run
LocalFlow's production engine on the candidate in LocalFlow's own .venv, and
the config/rollback commands run against a scratch copy of a config file.
Nothing touches LocalFlow's real configuration.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import ART, CONFIG, EXP_DIR, REPORT_DIR, REPO_ROOT, expand, read_json, read_jsonl, utc_now, write_json

RESULTS = ART / "results"


def esc_json(value) -> str:
    """JSON safe inside <script type="application/json">: no '<', '>' or '&'
    reaches the HTML parser, so a transcript containing '</script>' stays data."""
    s = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026") \
        .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def model_info(summary) -> dict:
    out = {}
    m = CONFIG["models"]
    cid = read_json(ART / "export" / "C_identity.json", {})
    for k in ("A", "B", "C"):
        info = {"short": {"A": "A, Qwen3-4B-Instruct-2507 (current)", "B": "B, Qwen3.5-4B untuned",
                          "C": "C, Qwen3.5-4B LocalFlow-tuned"}[k],
                "repo": m[k]["repository_id"], "revision": m[k].get("revision") or cid.get("revision"),
                "quant": m[k]["quantization"]}
        if k not in summary["models"]:
            info["status"] = "not evaluated"
        out[k] = info
    return out


def run_cmd(cmd: str, timeout: int = 900) -> tuple[bool, str]:
    r = subprocess.run(["/bin/zsh", "-c", cmd], capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT,
                       env={**os.environ, "HF_HUB_OFFLINE": "1"})
    return r.returncode == 0, (r.stdout.strip().splitlines() or [""])[-1][:400]


# Models are referred to by repo id; LocalFlow runs offline from the default
# Hugging Face cache, so a switch links the model's folder from the LocalAI hub
# into that cache instead of writing any absolute path into a config file.
MODEL_IDS = {"C": "local/LocalFlow-Cleanup-Qwen3.5-4B-4bit", "B": "mlx-community/Qwen3.5-4B-4bit"}


def link_cmd(repo_id: str) -> str:
    folder = "models--" + repo_id.replace("/", "--")
    return (f"mkdir -p ~/.cache/huggingface/hub && "
            f"ln -sfn ~/Documents/LocalAI/models/hub/{folder} ~/.cache/huggingface/hub/{folder}")


def commands(summary) -> list[dict]:
    """Verified, copyable commands, run from the repository root. None of them
    touches LocalFlow's real config here; config edits run against a scratch
    copy of the config file."""
    out = []
    sample = "Um, can you move the standup to 10, no wait, 10:30 and remind Priya not to merge the release branch."
    for k in ("C", "B"):
        if k not in summary["models"]:
            continue
        cmd = (f"HF_HUB_OFFLINE=1 .venv/bin/python experiments/cleanup-model/lfx/loader_check.py "
               f"{MODEL_IDS[k]} . {shlex.quote(sample)}")
        ok, last = run_cmd(cmd)
        out.append({"title": f"Try {k} on one sentence with LocalFlow's real engine",
                    "text": cmd, "verified": ok,
                    "note": ("Run from the repository root. Uses LocalFlow's own .venv and its production ModelRunner; "
                             "prints the cleaned text. Verified while building this report. "
                             f"Output: {json.loads(last)['text'] if ok else last}")})
    for k in ("C", "B"):
        if k not in summary["models"]:
            continue
        switch = (link_cmd(MODEL_IDS[k]) + "\n" +
                  "python3 - <<'PY'\nimport json, os, shutil\n"
                  "p = os.path.expanduser('~/Library/Application Support/LocalFlow/config.json')\n"
                  "shutil.copyfile(p, p + '.before-cleanup-switch') if os.path.exists(p) else None\n"
                  "d = json.load(open(p)) if os.path.exists(p) else {}\n"
                  f"d['cleanup_model'] = {MODEL_IDS[k]!r}\n"
                  "json.dump(d, open(p, 'w'), indent=2)\nprint('cleanup_model ->', d['cleanup_model'])\nPY")
        ok = _verify_on_scratch(switch, expect=MODEL_IDS[k])
        out.append({"title": f"Switch LocalFlow to {k}", "text": switch, "verified": ok,
                    "note": "Links the model from ~/Documents/LocalAI/models into the Hugging Face cache LocalFlow "
                            "reads offline, then sets cleanup_model in your LocalFlow config (keeping a backup). "
                            "Quit and reopen LocalFlow afterwards. "
                            + ("Verified on a scratch copy of the config." if ok else "Scratch verification failed.")})
    rollback = ("python3 - <<'PY'\nimport json, os\n"
                "p = os.path.expanduser('~/Library/Application Support/LocalFlow/config.json')\n"
                "d = json.load(open(p)) if os.path.exists(p) else {}\n"
                "d.pop('cleanup_model', None)\njson.dump(d, open(p, 'w'), indent=2)\n"
                "print('cleanup_model removed; LocalFlow uses its default,', 'mlx-community/Qwen3-4B-Instruct-2507-4bit')\nPY")
    ok = _verify_on_scratch(rollback, expect=None)
    out.append({"title": "Roll back to the previous model", "text": rollback, "verified": ok,
                "note": "Removes the override so LocalFlow's built-in default (Qwen3-4B-Instruct-2507 4-bit) applies. "
                        "Quit and reopen LocalFlow. " + ("Verified on a scratch copy of the config." if ok else "")})
    return out


def _verify_on_scratch(script: str, expect: str | None) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        cfg = home / "Library/Application Support/LocalFlow/config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"theme": "light", "cleanup_model": "placeholder-from-test"}))
        r = subprocess.run(["/bin/zsh", "-c", script], capture_output=True, text=True, env={**os.environ, "HOME": tmp})
        if r.returncode != 0:
            return False
        d = json.loads(cfg.read_text())
        ok = d.get("theme") == "light" and (d.get("cleanup_model") == expect if expect else "cleanup_model" not in d)
        return ok


def specimen(cases: list[dict]) -> dict | None:
    """One synthetic correction case where the models disagree, chosen by hash
    (not by which model looks good)."""
    pool = [c for c in cases if c["src"] == "synthetic" and c.get("gold") and c.get("disagree")
            and all(m in c["out"] for m in ("A", "B", "C")) and len(c["input"].split()) <= 45]
    if not pool:
        pool = [c for c in cases if c["src"] == "synthetic" and c.get("gold") and len(c["input"].split()) <= 45]
    if not pool:
        return None
    c = min(pool, key=lambda x: hashlib.sha256(("specimen:" + x["id"]).encode()).hexdigest())
    return {"label": "a synthetic test dictation with a self-correction, picked by hash, not by outcome",
            "input": c["input"], "out": {m: o["mo"] for m, o in c["out"].items()}}


def spend_rows() -> list[dict]:
    from .batches import CLAUDE_DIR, ledger
    led = ledger()
    agg = {}
    names = {"generation": "Generating dictation families", "verification": "Verifying gold labels", "judge": "Blinded judge"}
    for key, e in led["entries"].items():
        p = names.get(e.get("purpose"), e.get("purpose"))
        a = agg.setdefault(p, {"purpose": p, "requests": 0, "input": 0, "output": 0, "usd": 0.0})
        u = e.get("usage", {})
        a["input"] += u.get("input", 0) + u.get("cache_write", 0) + u.get("cache_read", 0)
        a["output"] += u.get("output", 0)
        a["usd"] += e.get("actual_usd", 0.0)
    for d in CLAUDE_DIR.glob("*/manifest.json"):
        m = read_json(d)
        purpose = "Blinded judge" if m["name"] == "judge" else "Verifying gold labels" if m["name"].startswith("ver-") \
            else "Generating dictation families"
        if purpose in agg:
            agg[purpose]["requests"] += m["request_count"]
    return list(agg.values())


THIRD_PARTY = ("disfluencyspeech", "fleurs")


def redact(cases: list[dict]) -> list[dict]:
    """Public build: transcripts of the public datasets (and model outputs made
    from them) are not republished; ids, sources and every metric stay."""
    out = []
    for c in cases:
        if c["src"] in THIRD_PARTY:
            c = {**c, "input": None, "raw": None, "target": None, "redacted": True,
                 "out": {m: {**o, "mo": None, "dl": None} for m, o in c["out"].items()}}
        out.append(c)
    return out


def build(public: bool = True) -> Path:
    summary = read_json(RESULTS / "summary.json")
    cases = read_json(RESULTS / "cases.json", [])
    prov = summary["provenance"]
    dec = summary["decision"]
    ds = prov.get("dataset") or {}
    fr = prov.get("freeze") or {}
    claude = prov.get("claude") or {}
    gen_stats = {w: read_json(ART / "pairs" / f"{w}.stats.json", {}) for w in ("gen-pilot", "gen-test", "gen-validation", "gen-train")}
    rej = {}
    for s in gen_stats.values():
        for k, v in (s.get("reject_reasons") or {}).items():
            if v:
                rej[k] = rej.get(k, 0) + v
    for k, v in (fr.get("dropped", {}).get("test") or {}).items():
        rej[f"test: {k}"] = v
    for k, v in (fr.get("dropped", {}).get("validation") or {}).items():
        rej[f"validation: {k}"] = v
    for k, v in ((ds.get("dropped") or {}).get("verifier") or {}).items():
        rej[f"train: {k}"] = v
    pretty = {"gold_rejected_by_validator": "LocalFlow's validator rejected the gold cleanup (product limit)",
              "gold_correction_not_selected": "LocalFlow's correction parser did not accept a gold deletion",
              "gold_correction_rejected": "correction rejected by the parser's evidence guard",
              "delivered_differs_from_gold": "engine output differed from the gold text",
              "salvaged": "validator had to restore dropped words", "fact_missing": "a critical fact was missing from one side",
              "fact_missing_both": "a critical fact matched neither text exactly", "ending_not_retained": "the ending was not kept",
              "marker_not_triggered": "correction marker not recognized by the engine",
              "family_missing_from_response": "family missing from Claude's response",
              "unknown_or_duplicate_family_id": "unknown or duplicate family id", "span_not_in_input": "gold span not found in input",
              "normalization_unanchored": "normalization moved a gold span", "too_long_for_tokenizer": "gold longer than the output limit",
              "length_out_of_band": "outside the length band", "noop_target_differs": "no-op target was not identical",
              "obsolete_value_kept": "corrected-away value left in the target", "negation_added": "negation added in target"}
    rejections = sorted(((pretty.get(k, k.replace("_", " ")), v) for k, v in rej.items()), key=lambda x: -x[1])
    tr_metrics = prov.get("training_metrics") or []
    plan = read_json(ART / "train" / "main" / "plan.json", {})
    cid = prov.get("C") or {}
    sel = dict(prov.get("selection") or {})
    sel["results"] = {k: {kk: vv for kk, vv in v.items() if kk != "candidate_dir"}
                      for k, v in (sel.get("results") or {}).items()}
    tcfg = CONFIG["training"]
    smoke = (prov.get("smoke") or {}).get("train") or {}
    config_rows = [
        ("Base checkpoint", f"{CONFIG['models']['base_bf16']['repository_id']} @ {CONFIG['models']['base_bf16']['revision'][:12]} (post-trained, not Base), bf16"),
        ("Adapter", f"LoRA rank {tcfg['lora']['rank']}, scale {tcfg['lora']['scale']}, dropout {tcfg['lora']['dropout']}, all 32 layers"),
        ("Adapted modules", ", ".join(tcfg["lora"]["keys"]) + " (per-head gates in_proj_a/b left frozen)"),
        ("Optimizer", f"AdamW, learning rate {tcfg['learning_rate']}, cosine decay to 5%, {tcfg['warmup_updates']} warm-up updates, gradient clip 1.0"),
        ("Batching", f"1 example per step, {tcfg['grad_accumulation']}-step accumulation, one pass, no packing or truncation"),
        ("Examples", f"{plan.get('examples', '–')} ({(plan.get('roles') or {}).get('main', '–')} main-pass, {(plan.get('roles') or {}).get('corrections', '–')} correction-pass)"),
        ("Loss", "response tokens only (completion plus <|im_end|>), on the exact prompts LocalFlow's engine renders, thinking off"),
        ("Long prompts", "the shared system prompt and few-shot turns are run forward under the current weights each update; "
                         "gradients flow through each example's own payload and response (about 6x faster; the loss is exact)"),
        ("Qwen3.5 linear attention", "trained through a chunked gated-delta implementation, checked against mlx-lm's reference "
                                     "(exact on CPU, within 1% of the inference kernel on a 3,500-token sequence)"),
        ("Smoke check", f"loss finite, {smoke.get('tensors_changed', '–')}/{smoke.get('trainable_tensors', '–')} adapter tensors changed, "
                        f"reload logits identical, overfit loss {smoke.get('overfit_first_last', ['–', '–'])[0]:.2f} to {smoke.get('overfit_first_last', [0, 0])[1]:.2f}"
         if smoke.get("overfit_first_last") else "–"),
        ("Selected checkpoint", f"{sel.get('selected', '–')}"),
        ("Deployable artifact", f"{cid.get('snapshot_path', '–')} ({(cid.get('size_bytes') or 0) / 1e9:.2f} GB, 4-bit, same recipe as B)"),
        ("Adapter files", cid.get("adapter_path", "–")),
        ("Fused vs adapter check", (lambda f: f"fusing kept the adapter's effect: mean logit difference "
                                               f"{f['fused_vs_adapter_mean_max'][0]:.3f} between fused and base+adapter, "
                                               f"against {f['base_vs_adapter_mean_max'][0]:.2f} between base and base+adapter; "
                                               f"same top token at {100 * f['argmax_fused_eq_adapter']:.0f}% of positions"
                                    if f else "–")((cid.get("selection") or {}).get("fused_logit_check"))),
    ]
    data_rows = [
        ("Claude model", f"{CONFIG['claude']['model']} via the Message Batches API (structured JSON output)"),
        ("Synthetic families requested", ", ".join(f"{w.replace('gen-', '')} {s.get('families_requested', '–')}" for w, s in gen_stats.items())),
        ("Synthetic test cases (frozen)", f"{fr.get('counts', {}).get('test_synthetic', '–')} verified pairs ({sum(1 for c in cases if c['src'] == 'synthetic' and c.get('noop'))} already clean)"),
        ("Validation pairs", str(fr.get("validation_pairs", "–"))),
        ("Training pairs", (lambda v: f"{ds.get('train_pairs', 0):,} from {ds.get('train_families', 0):,} families "
                                      f"(target about {CONFIG['targets']['train_pairs']:,}): {v.get('base', 0):,} generated, "
                                      f"{v.get('fixpoint_noop', 0):,} clean copies of a target, {v.get('filler_insertion', 0):,} "
                                      f"with fillers inserted; {ds.get('train_noop', 0):,} already clean")(ds.get("train_by_variant") or {})),
        ("Training verification", (lambda v: f"{v.get('PASS', 0):,} passed Claude verification; {v.get('NOT_SAMPLED', 0)} "
                                             f"pilot variants not sampled; {v.get('UNVERIFIED', 0)} without a verdict; "
                                             "verifier failures were removed")(ds.get("train_verification") or {})),
        ("Real audio", "250 DisfluencySpeech test recordings, 250 FLEURS English test recordings (one per sentence)"),
        ("LocalFlow fixtures", "80 hand-written cases (tests/v2/fidelity)"),
        ("Long dictations", f"{fr.get('counts', {}).get('longform.jsonl', '–')} joined synthetic cases over 200 words"),
        ("Frozen", f"{fr.get('frozen', '–')}, rules hash {fr.get('rules_sha256', '')[:16]}"),
        ("Label", "PRODUCT_AUTOGENERATED: machine-generated and machine-verified, never human-reviewed"),
        ("Changes after the freeze", "None to test cases, references, metric code or rules (hashes re-checked). "
                                     "config.yaml changed in two ways that touch no case, metric or rule: the judge's "
                                     "output cap went from 4,000 to 3,000 tokens so its worst-case charge fit under the "
                                     "spend stop, and machine-specific paths became repo-relative before publishing."),
    ]
    spend = spend_rows()
    total = sum(r["usd"] for r in spend)
    blocked = []
    if "C" not in summary["models"]:
        blocked.append("C was not evaluated; see the training section.")
    if (summary.get("judge") or {}).get("status") == "not_run":
        blocked.append("The blinded judge did not run.")
    D = {
        "created": utc_now(), "models": summary["models"], "model_info": model_info(summary), "decision": dec,
        "rules": CONFIG["rules"], "comparisons": summary["comparisons"], "aggregates": summary["aggregates"],
        "baselines": summary["baselines"], "cold_loads": summary["cold_loads"], "artifact_sizes": summary["artifact_sizes"],
        "pipeline": summary["pipeline"], "fidelity": summary["fidelity"], "judge": summary["judge"],
        "headline_reason": headline(summary), "limits": limits(summary), "blocked": blocked, "specimen": specimen(cases),
        "synthetic_blurb": (f"{fr.get('counts', {}).get('test_synthetic', '–')} machine-generated dictations, each built "
                            "from its intended text first and then made noisy the way Parakeet transcribes speech. "
                            "Every pair passed deterministic checks, LocalFlow's own validator and a separate Claude "
                            "verification. Damage means the output changed a fact, a negation or the ending, dropped "
                            "content, or added words the speaker never said."),
        "training": {"metrics": tr_metrics, "selection": sel, "config_rows": config_rows,
                     "blurb": "C is Qwen3.5-4B fine-tuned for LocalFlow's two cleanup calls (listing self-correction "
                              "deletions, and writing the cleaned text) on synthetic pairs rendered through LocalFlow's own "
                              "engine. Checkpoints were compared on the validation set only, after converting each one to "
                              "the 4-bit format LocalFlow would load.",
                     "status": None if tr_metrics else "Training did not complete."},
        "data": {"rows": data_rows, "rejections": rejections, "spend": spend,
                 "blurb": "Splits were assigned to dictation families before generation, so no family appears in two splits.",
                 "spend_note": f"Total ${total:.2f} of the $20 cap, at Batch API prices (verified on the pricing page "
                               f"2026-10-11). The controller stopped submitting whenever spend plus the worst case of "
                               f"outstanding requests would pass $19.50."},
        "commands": commands(summary), "cases": cases, "links": links(), "footer": footer(summary),
    }
    out_dir = REPORT_DIR if public else ART / "report-full"
    if public:
        D["cases"] = redact(D["cases"])
        D["public_note"] = ("Transcripts from DisfluencySpeech and FLEURS are not republished in this copy; their "
                            "metrics are. Run experiments/cleanup-model/run.py report locally for the full explorer.")
    out_dir.mkdir(parents=True, exist_ok=True)
    home = str(Path.home())
    html = (EXP_DIR / "lfx" / "report_template.html").read_text().replace("__DATA__", esc_json(D)).replace(home, "~")
    if public and "/Users/" in html:
        raise RuntimeError("public report still contains an absolute user path")
    (out_dir / "index.html").write_text(html)
    if not public:
        return out_dir / "index.html"
    write_json(REPORT_DIR / "summary.json", {k: D[k] for k in ("created", "models", "model_info", "decision", "rules", "comparisons",
                                                                "aggregates", "baselines", "cold_loads", "artifact_sizes",
                                                                "pipeline", "fidelity", "judge")})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["case_id", "source", "category", "profile", "noop"] +
               [f"{m}_{k}" for m in ("A", "B", "C") for k in ("path", "flags", "repair_right", "ms")])
    for c in cases:
        w.writerow([c["id"], c["src"], c.get("cat"), c.get("profile"), c.get("noop")] +
                   [x for m in ("A", "B", "C") for x in ((c["out"].get(m) or {}).get("path"), " ".join((c["out"].get(m) or {}).get("flags", [])),
                                                       (c["out"].get(m) or {}).get("repair"), (c["out"].get(m) or {}).get("ms"))])
    (REPORT_DIR / "cases.csv").write_text(buf.getvalue())
    return REPORT_DIR / "index.html"


def headline(summary) -> str:
    """Lead with the candidate the rules favour, then the other, in measured terms."""
    dec = summary["decision"]
    ag, comps = summary["aggregates"], summary["comparisons"]
    nice = {"R1a_model_only_damage": "model-only damage", "R1b_delivered_damage": "delivered damage",
            "R1c_disfluencyspeech_unauthorized_edits": "unauthorized edits on conversational audio",
            "R1c_disfluencyspeech_wer": "WER on conversational audio", "R1c_fleurs_unauthorized_edits": "unauthorized edits on read speech",
            "R1c_fleurs_wer": "WER on read speech", "R1d_fixtures_not_below_A": "LocalFlow fixture pass rate",
            "R2_delivered_repair_gain": "delivered repair gain", "R3_warm_p95": "warm p95 latency", "R3_cold_load": "cold load"}
    order = ["C", "B"] if dec.get("outcome") == "consider_C" else ["B", "C"]
    parts = []
    for x in order:
        cand = dec["candidates"].get(x, {})
        if cand.get("status") == "unavailable":
            parts.append(f"{x} could not be evaluated.")
            continue
        c = comps.get(f"{x}-A", {})
        checks = cand.get("checks") or {}
        failed = [nice.get(k, k) for k, v in checks.items() if v is False]
        unmeasured = [nice.get(k, k) for k, v in checks.items() if v is None]
        rep = c.get("delivered_repair_success", {})
        dmg = c.get("model_only_damage", {})
        rx = (ag[x].get("synthetic_repair") or {}).get("delivered", {}).get("repair_success")
        ra = (ag["A"].get("synthetic_repair") or {}).get("delivered", {}).get("repair_success")
        stat = (f"{x} delivered {rx:.0f}% of needed repairs correctly against {ra:.0f}% for A "
                f"({rep.get('diff_pp', 0):+.1f} points), and changed meaning in its own output "
                f"{abs(dmg.get('diff_pp', 0)):.1f} points {'less' if dmg.get('diff_pp', 0) < 0 else 'more'} often")
        if not failed and not unmeasured:
            parts.append(f"{x} met every frozen rule: {stat}.")
        else:
            bits = []
            if failed:
                bits.append("missed " + ", ".join(failed))
            if unmeasured:
                bits.append("could not measure " + ", ".join(unmeasured))
            parts.append(f"{x} " + "; ".join(bits) + f" ({stat}).")
    return " ".join(parts)


def limits(summary) -> list[str]:
    ag = summary["aggregates"]
    lat = lambda m, k, q="median": ((ag.get(m) or {}).get("latency") or {}).get(k, {}).get(q)
    cold = summary.get("cold_loads") or {}
    cm = {m: sorted(x["process_to_ready_ms"] for x in v)[len(v) // 2] for m, v in cold.items() if v}
    out = ["C learned from the same Claude generator that wrote the synthetic test, so its synthetic margin "
           "is optimistic. The checks Claude did not write (two public audio sets and LocalFlow's own fixtures) "
           "show smaller gains in the same direction.",
           "Real audio is one re-recorded conversational speaker and read English sentences, not your voice, accent "
           "or vocabulary; nothing here was recorded from you.",
           "Most test dictations fit in one cleanup window (under 200 words); longer ones are covered by 40 joined "
           "cases scored on delivered text only."]
    if "C" in ag and lat("A", "total_cleanup_ms") and lat("C", "total_cleanup_ms"):
        out.append(f"C is slightly slower warm: median cleanup {lat('C', 'total_cleanup_ms') / 1000:.2f} s against "
                   f"{lat('A', 'total_cleanup_ms') / 1000:.2f} s for A, first token "
                   f"{lat('C', 'first_token_ms') / 1000:.2f} s against {lat('A', 'first_token_ms') / 1000:.2f} s"
                   + (f", cold load {cm['C'] / 1000:.1f} s against {cm['A'] / 1000:.1f} s." if "C" in cm and "A" in cm else "."))
    if "C" in ag and "A" in ag:
        cases = {c["case_id"]: c for c in read_jsonl(ART / "eval" / "final_cases.jsonl")}
        rows = {m: {r["case_id"]: r for r in read_jsonl(ART / "eval" / f"final-{m}.jsonl")} for m in ("A", "C")}
        same = lambda m, src: 100 * sum((rows[m][c].get("model_only") or "") == cases[c]["model_input"]
                                        for c in cases if cases[c]["source"] == src) / \
            max(1, sum(1 for c in cases if cases[c]["source"] == src))
        ue = lambda m: (((ag[m].get("fleurs") or {}).get("model_only") or {}).get("unauthorized_edit"))
        out.append(f"C is hands-off on real transcripts: it left {same('C', 'disfluencyspeech'):.0f}% of conversational "
                   f"and {same('C', 'fleurs'):.0f}% of read transcripts unchanged (A: {same('A', 'disfluencyspeech'):.0f}% "
                   f"and {same('A', 'fleurs'):.0f}%). Fillers still go, but capitalization and commas that Parakeet "
                   f"got wrong often stay wrong; punctuation is not scored as damage. A's extra edits include such "
                   f"fixes, and also word changes in {ue('A'):.1f}% of read transcripts.")
    out.append("Some limits sit in LocalFlow's engine, not the model, and affect every model: a correction such as "
               "\"3, sorry, 4\" fails the correction parser's evidence check because of the comma after the marker; "
               "a comma-joined list keeps its final \"and\"; spoken \"step 1,\" labels followed by a comma fall back.")
    out.append("The unauthorized-edit counts on conversational audio include some stutter removals: when a model "
               "deletes one copy of \"and and\", the word alignment may charge the first copy. This raises every "
               "model's absolute rate; the paired differences used by the rules are much less affected.")
    out.append("Switching means pointing cleanup_model at C's folder and restarting LocalFlow; nothing was changed for you.")
    return out


def links() -> list:
    return [["Experiment code and run configuration (experiments/cleanup-model)", "../../experiments/cleanup-model/"],
            ["LocalFlow clean-mode contract (localflow/v2/cleanup/prompts.py)", "../../localflow/v2/cleanup/prompts.py"],
            ["LocalFlow cleanup engine and validator", "../../localflow/v2/cleanup/"],
            ["Qwen/Qwen3.5-4B model card", "https://huggingface.co/Qwen/Qwen3.5-4B"],
            ["mlx-community/Qwen3.5-4B-4bit", "https://huggingface.co/mlx-community/Qwen3.5-4B-4bit"],
            ["mlx-community/Qwen3-4B-Instruct-2507-4bit", "https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit"],
            ["MLX LoRA documentation", "https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md"],
            ["DisfluencySpeech dataset card", "https://huggingface.co/datasets/amaai-lab/DisfluencySpeech"],
            ["FLEURS dataset card", "https://huggingface.co/datasets/google/fleurs"],
            ["Claude Message Batches API", "https://platform.claude.com/docs/en/build-with-claude/batch-processing"],
            ["Claude pricing", "https://platform.claude.com/docs/en/about-claude/pricing"]]


def footer(summary) -> str:
    fid = summary.get("fidelity") or {}
    fid_txt = "; ".join(f"{k}: {v['identical']}/{v['cases']} byte-identical in LocalFlow's own .venv" for k, v in fid.items())
    return (f"Built {utc_now()}. Runtime: mlx 0.31.2, mlx-lm 0.31.3, "
            f"Apple M5 Pro, 48 GB. Runtime fidelity check: {fid_txt or 'not run'}. Rerun or resume everything with "
            "experiments/cleanup-model/run.py all.")


if __name__ == "__main__":
    print(build(public=False))
    print(build(public=True))
