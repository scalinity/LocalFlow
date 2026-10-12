"""Blinded, fixed-rubric Claude batch judge on a bounded stratified sample.

Supplementary only: judge-derived scores are reported separately and never
enter the frozen decision rules. Outputs are shown under hashed labels; the
judge never sees model names and never rewrites references.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter

from . import batches
from .common import ART, CONFIG, read_json, read_jsonl, utc_now, write_json
from .datagen import clients

EVAL = ART / "eval"
PROBLEMS = ["changed_meaning", "dropped_content", "added_content", "answered_or_executed", "paraphrased",
            "missed_filler", "missed_correction", "wrong_correction", "bad_punctuation", "bad_list_format",
            "unnecessary_edit", "none"]

SCHEMA = {"type": "object", "properties": {"ratings": {"type": "array", "items": {
    "type": "object",
    "properties": {"label": {"type": "string"},
                   "meaning_preserved": {"type": "boolean"},
                   "cleanup": {"type": "string", "enum": ["none_needed_and_none_made", "complete", "partial", "none", "harmful"]},
                   "problems": {"type": "array", "items": {"type": "string", "enum": PROBLEMS}},
                   "note": {"type": "string"}},
    "required": ["label", "meaning_preserved", "cleanup", "problems", "note"], "additionalProperties": False}}},
    "required": ["ratings"], "additionalProperties": False}


def system() -> str:
    from localflow.v2.cleanup import prompts
    return f"""You rate candidate outputs of a dictation clean-mode model against a fixed contract. Each output is shown under an anonymous label. Judge every output independently against the contract, not against one another and not against your own style preferences.

<contract>
{prompts.CONTRACT}

{prompts.LIST_FORMATTING}
</contract>

Allowed edits: removing pure fillers (um, uh, erm, ehm, hmm, mhm), resolving explicit self-corrections (delete the outdated value and its marker, keep the replacement), removing immediately repeated function words, fixing punctuation, capitalization and sentence or paragraph breaks, and formatting explicitly spoken lists or steps. Anything else, such as synonyms, reworded grammar, dropped discourse words like "like", "you know" or "I think", answers to questions, or added words, counts as a problem.

For each output:
- meaning_preserved: false if any request, constraint, negation, uncertainty, name, number, unit, path, identifier or detail was changed, dropped or added.
- cleanup: "none_needed_and_none_made" when the input was already clean and the output left it unchanged; "complete" when every allowed fix the input needed was made; "partial" when only some were; "none" when nothing needed was fixed; "harmful" when the output is worse than the input.
- problems: every problem you see, or ["none"].
A reference cleanup is sometimes given. It is one acceptable answer, not the only one."""


def sample(cases: list[dict], n: int, seed: int = 31) -> list[dict]:
    rng = random.Random(seed)
    strata = {"syn_repair": [c for c in cases if c.get("source") == "synthetic" and not c.get("is_noop")],
              "syn_noop": [c for c in cases if c.get("source") == "synthetic" and c.get("is_noop")],
              "disfluencyspeech": [c for c in cases if c.get("source") == "disfluencyspeech"],
              "fleurs": [c for c in cases if c.get("source") == "fleurs"]}
    quota = {"syn_repair": int(n * 0.42), "syn_noop": int(n * 0.16), "disfluencyspeech": int(n * 0.21)}
    quota["fleurs"] = n - sum(quota.values())
    out = []
    for k, pool in strata.items():
        pool = sorted(pool, key=lambda c: c["case_id"])
        rng.shuffle(pool)
        out += [dict(c, stratum=k) for c in pool[: quota[k]]]
    return out


def build_requests(picked: list[dict], outputs: dict) -> tuple[dict, dict]:
    reqs, keys = {}, {}
    sys_text = system()
    for i, c in enumerate(picked):
        models = sorted(outputs, key=lambda m: hashlib.sha256(f"judge:{c['case_id']}:{m}".encode()).hexdigest())
        labels = {f"output_{j + 1}": m for j, m in enumerate(models)}
        body = {"input_transcript": c["model_input"],
                "reference_cleanup": c.get("target") if c.get("source") == "synthetic" else None,
                "outputs": {lab: outputs[m].get(c["case_id"]) or "" for lab, m in labels.items()}}
        rid = f"judge-{i:04d}"
        reqs[rid] = {"model": CONFIG["claude"]["model"], "max_tokens": CONFIG["claude"]["judge_max_tokens"],
                     "thinking": {"type": "adaptive"},
                     "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                     "system": [{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}],
                     "messages": [{"role": "user", "content": "Rate each output:\n" + json.dumps(body, ensure_ascii=False, indent=1)}]}
        keys[rid] = {"case_id": c["case_id"], "stratum": c["stratum"], "labels": labels}
    return reqs, keys


def run() -> dict:
    cases = {c["case_id"]: c for c in read_jsonl(EVAL / "final_cases.jsonl")}
    outputs = {}
    for m in ("A", "B", "C"):
        rows = read_jsonl(EVAL / f"final-{m}.jsonl")
        outputs[m] = {r["case_id"]: (r.get("model_only") if r.get("model_only") is not None else r.get("delivered"))
                      for r in rows}
    picked = sample(list(cases.values()), CONFIG["evaluation"]["judge_cases"])
    reqs, keys = build_requests(picked, outputs)
    write_json(ART / "claude" / "judge" / "keys.json", keys)
    c, n = clients()
    w = batches.Wave("judge", reqs, parse=lambda t: json.loads(t)["ratings"], est_input_tokens=lambda p: 3500,
                     client=c, client_noretry=n, purpose="judge", reservation="judge")
    w.run(chunk=120)
    batches.set_reservation("judge", 0.0)
    vals = w.values()
    per = []
    for rid, ratings in vals.items():
        k = keys[rid]
        for r in ratings:
            model = k["labels"].get(r["label"])
            if model:
                per.append({"case_id": k["case_id"], "stratum": k["stratum"], "model": model, **r})
    write_json(EVAL / "judge.json", {"created": utc_now(), "judge_model": CONFIG["claude"]["model"],
                                     "requests": len(reqs), "rated": len(vals), "status": w.status_counts(),
                                     "ratings": per})
    return {"rated": len(vals)}


if __name__ == "__main__":
    print(run())
