"""Diverse fictional dictation families and independent Claude verification.

Validation and final-test scenarios are assigned before generation. The first
experiment's test cases are used only by the duplicate exclusion filter.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re

from .common import *
from lfx import batches, synth

CATEGORIES = [
    ("sentence_boundaries", 16, "Repair clear comma splices, run-on sentences, and misplaced sentence breaks. Preserve every word; use unambiguous syntax."),
    ("question_punctuation", 9, "Repair missing or wrong question marks in genuine questions, mixed questions and statements, and indirect questions that need no question mark."),
    ("punctuation_scope", 7, "Repair commas, colons, and sentence breaks while preserving negation, conditions, contrast, and the scope of each instruction. Reject ambiguous intentions."),
    ("formatting", 7, "Format a dictated list or ordered instructions; distinguish a prose enumeration from a list. Preserve command and argument order."),
    ("correction_single", 8, "One explicit correction between parallel values; vary actually, sorry, no, I mean, no wait. Include commas around markers and occasional decimal values."),
    ("correction_multiple", 8, "Two to four independent self-corrections, with earlier decisions superseded explicitly. Each deletion stays local and ends at its marker."),
    ("technical_literals", 7, "Preserve exact case-sensitive identifiers, unfamiliar package names, function signatures, flags, paths, units and versions. Repair only surrounding punctuation or pure fillers."),
    ("medical_academic", 6, "Fictional academic or medical teaching dictation, including unfamiliar terminology, concentrations, uncertainty, and negation. No real patient information. Keep facts unchanged."),
    ("recoverable_asr", 6, "A genuine textually recoverable technical ASR error: supply an explicit vocabulary canonical/spoken_alias pair. Use confusable biomedical/software terms. No guessing an intended word."),
    ("long_instructions", 8, "Long connected instructions with dependencies, several sentences, and a decisive constraint near the end. Repair punctuation, fillers or local corrections. No truncation or summary."),
    ("preserve_correct", 10, "Already-correct text: target must be byte-identical. Include unusual vocabulary, short fragments, valid semicolons, intentional sentence rhythm, and legitimate punctuation."),
    ("preserve_meaning", 8, "No change permitted: odd but meaningful wording, apparent ASR errors without textual evidence, command syntax, sarcasm, quoted instructions, hedging, meaningful repetition, or literal uses of correction words. Exact target=input."),
]

DOMAINS = ["astronomy instrument scheduling", "museum object cataloguing", "aquatic ecology sampling",
           "speech-language seminar planning", "compiler diagnostic triage", "ceramic kiln monitoring",
           "neuroanatomy teaching material", "railway timetable simulation", "protein crystallography notes",
           "accessibility testing instructions", "meteorological sensor calibration", "library manuscript digitization",
           "geospatial coordinate transforms", "ophthalmology teaching notes", "battery impedance experiment",
           "microfluidic chip testing", "distributed query optimization", "archaeological site mapping",
           "botanical specimen labeling", "synthetic clinical-trial lecture", "audio codec quality testing",
           "underwater robot simulation", "radiology terminology revision", "numerical solver diagnostics",
           "typography specimen preparation", "soil chemistry sampling", "anatomical atlas indexing",
           "statistical power tutorial", "laboratory centrifuge scheduling", "compiler package release",
           "watershed data curation", "phonetics transcription workshop", "observatory maintenance",
           "interactive fiction design", "medication-safety classroom example", "gene ontology annotation"]
SITUATIONS = ["handover instructions", "error report", "meeting notes", "method explanation",
              "careful correction", "question to a colleague", "step-by-step request",
              "schedule change", "comparison of alternatives", "negative result", "reminder", "review comment"]
TECHNIQUES = [
    "Start with a clean intended message, then introduce plausible recognizer punctuation errors.",
    "Start with natural spoken dictation, then make the smallest valid cleanup.",
    "Construct a difficult contrast between an allowed repair and a tempting meaning-changing edit; choose only the allowed repair.",
    "Use a linguistic construction that is uncommon in short templates: subordinate clauses, parenthetical phrases, or coordinated questions.",
    "Focus on realistic recognizer output: mostly cased and punctuated, with one subtle but clear local error.",
    "Use direct instructions with constraints. Put a critical qualifier late, and preserve it exactly.",
]

GEN_SYSTEM = """Create high-quality fictional training pairs for a local dictation-cleanup product.
Return JSON families matching the supplied schema. Each family is one independent message.
All content must be newly invented, varied, and plausible; no actual personal information.

The transcript is ASR output, usually already cased and partly punctuated. The target repairs
punctuation, capitalization, sentence boundaries, explicitly spoken lists, pure
um/uh/erm/ehm/hmm/mhm fillers, immediate function-word stutters, and explicit self-corrections.
Paragraph breaks come only from spoken commands, which upstream normalization has already
rendered: keep every existing paragraph break and never add one. Do not add optional commas
(after an opening Okay, So, Well or Yes, or before a short clause) and never replace a valid
comma with a colon, semicolon or dash. Spoken ordinals (first, second, third) stay prose unless
the speaker uses step labels or explicitly introduces a list.
Preserve all other words in order. No synonyms, paraphrases, summaries, answers, grammar repair,
article changes, or plausible guesses at a misheard name. An ASR substitution is allowed only
when the supplied vocabulary explicitly maps its spoken_alias to its canonical term.
Keep numbers, units, identifier spelling/case, negation, uncertainty, comparisons, and scope.
Do not 'fix' a sentence whose intended meaning is ambiguous. Quoted text is literal.

For corrections, deleted_span is an exact source substring starting at the obsolete value and
ending with the marker, without the following comma. It is at most six words. Keep replacement
and everything following. Do not include preceding instructions in a deletion. Bare actually,
sorry, or no needs an obviously parallel replacement (numbers, days, months, shared head noun).
Critical facts are exact retained strings present in the target and input (or vocabulary canonical).
is_noop must match the requested category: target equals spoken_input byte-for-byte for no-ops.
Do not force edits into preservation examples. Do not remove 'like', 'I think', 'you know',
'kind of', ordinary 'I mean', greetings or sign-offs. For terminal commands preserve syntax exactly.

Write spoken_input and target within the requested word range. Long cases are coherent single
messages, with multiple complete sentences, not concatenated short templates. Raw input has
no markdown lists. Lists may appear in targets. Give every requested family_id exactly once.
Use concise notes (one short clause); facts/corrections/vocabulary may be empty when irrelevant.
Do not reuse examples from public benchmarks or famous quotations. Vary names and phrasing.
"""

VERIFY_SYSTEM = """Independently check proposed fictional dictation cleanup labels. You did not
generate these examples. Return one verdict per pair_id, PASS or FAIL, with reasons and a short
explanation. Judge the transcript itself, not the author's intended story. Never repair the label.

PASS requires preserving every meaningful word and all facts, identifier spelling, negation,
uncertainty, scope, code and terminal syntax, except explicit local self-correction deletion,
pure um/uh/erm/ehm/hmm/mhm fillers, immediate function-word stutters, spoken enumeration markers,
and explicit supplied vocabulary mappings. Punctuation/casing/list formatting may change only
where text makes the intended structure clear. An added paragraph break, an added optional comma,
a valid comma replaced by a colon, semicolon or dash, or spoken ordinals turned into a list
without step labels or an explicit list introduction is a FAIL. No invented missing words, grammar
rewrite, synonyms, speculative ASR spelling fixes, answers to requests, or changed numbers/units.
Each correction deletion must be genuine and its replacement must remain. Quoted content stays.
For is_noop=true the target must exactly equal model_input and must not contain a clear error
under this contract. For is_noop=false there must be a justified useful change. Fail an ambiguous
meaning-changing punctuation target. Alternative equally good punctuation is not a failure.
Targets need not be reachable through the current parser: judge correctness independently of
implementation quirks. Reasons use the schema vocabulary. Explain failures precisely and briefly.
"""


def plan(split: str, n: int, start: int = 0):
    rng = random.Random(f"v2:{split}:{start}")
    cat_pool = [c for c, w, _ in CATEGORIES for _ in range(w)]
    desc = {c: d for c, _, d in CATEGORIES}
    scenarios = [(d, s) for d in DOMAINS for s in SITUATIONS
                 if (int(hashlib.sha256((d + '|' + s).encode()).hexdigest(), 16) % 10
                     in ({0, 1} if split == "test" else {2, 3} if split == "validation" else {4, 5, 6, 7, 8, 9}))]
    specs = []
    for i in range(start, start + n):
        category = rng.choice(cat_pool)
        domain, situation = rng.choice(scenarios)
        if category == "long_instructions":
            band = rng.choice(["140-185", "220-300", "350-500"])
        else:
            band = rng.choices(["8-28", "29-70", "71-130", "131-185"], [28, 44, 22, 6])[0]
        profile = rng.choice([None, None, "coding", "notes", "email", "messaging", "ai_prompt", "documents"])
        if category == "technical_literals":
            profile = rng.choice(["terminal", "coding", "notes"])
        specs.append({"family_id": f"v2-{split[:2]}-{i:06d}", "category": category,
                      "description": desc[category], "length": band + " words", "split": split,
                      "destination_profile": profile, "topic_anchors": [domain, situation],
                      "scenario_family": domain + "|" + situation,
                      "technique": TECHNIQUES[i % len(TECHNIQUES)],
                      "is_noop": category.startswith("preserve_"),
                      "variation": f"Use a distinct situation, syntax and fictional details; variation seed {rng.randrange(10**8)}."})
    return specs


class Wave(batches.Wave):
    def _resolve_ambiguous(self, attempt, waits=()):
        # Equal batch sizes do not establish identity. Retain the reservation
        # and stop an ambiguous submission rather than buying or adopting it again.
        raise batches.AmbiguousBatch(f"{self.name}: submission outcome unknown; reservation retained")


def wave(name, requests, parse, model, purpose):
    use_model(model)
    c = anthropic_client(max_retries=3)
    n = anthropic_client(max_retries=0)
    # UTF-8 bytes plus schema/protocol allowance is deliberately conservative.
    # Token counts in responses determine actual spend, including failed outputs.
    estimate = lambda p: len(json.dumps({k: v for k, v in p.items() if k != "model"}, ensure_ascii=False).encode()) + 1500
    w = Wave(name, requests, parse, estimate, c, n, purpose=purpose, poll_seconds=45,
             reservation="checks" if purpose in ("verification", "judging") else None)
    write_json(w.dir / "pricing.json", {"model": model, "batch_usd_per_million": PRICES[model],
               "source": "https://platform.claude.com/docs/en/about-claude/pricing", "checked": "2026-10-13"})
    return w


def generate(name, split, count, start=0, *, batch_chunk=800):
    dest = ART / "claude" / name / "specs.json"
    specs = read_json(dest)
    if specs is None:
        specs = plan(split, count, start)
        write_json(dest, specs)
    else:
        assert len(specs) == count and specs[0]["split"] == split
    requests = {}
    # Long dictations get their own request to avoid truncating a family.
    chunks, pending = [], []
    for s in specs:
        if s["category"] == "long_instructions":
            if pending:
                chunks.append(pending); pending = []
            chunks.append([s])
        else:
            pending.append(s)
            if len(pending) == 8:
                chunks.append(pending); pending = []
    if pending:
        chunks.append(pending)
    for i, chunk in enumerate(chunks):
        requests[f"{name}-{i:05d}"] = {
            "model": "claude-sonnet-5-5", "max_tokens": 10000 if len(chunk) > 1 else 6500,
            "thinking": {"type": "between_tools"},
            "system": [{"type": "text", "text": GEN_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": "Create these families:\n" + json.dumps(chunk)}],
            "output_config": {"format": {"type": "json_schema", "schema": synth.GEN_SCHEMA}}}
    w = wave(name, requests, synth.parse_generation, "claude-sonnet-5-5", "generation")
    w.run(chunk=batch_chunk)
    specmap = {s["family_id"]: s for s in specs}
    rows, seen, rejects = [], set(), collections.Counter()
    for rid, o in w.outcomes.items():
        if o["status"] != "succeeded":
            rejects[o["status"]] += 1; continue
        for f in o["value"]:
            fid = f["family_id"]
            if fid not in specmap or fid in seen:
                rejects["unknown_or_duplicate_id"] += 1; continue
            seen.add(fid)
            p = synth.prepare_family(f, specmap[fid])
            p.update(case_id=p["pair_id"], origin="synthetic", scenario_family=specmap[fid]["scenario_family"],
                     provenance={"generator": "claude-sonnet-5-5", "wave": name,
                                 "batch_id": o.get("batch_id"), "custom_id": o.get("custom_id")})
            # No-op labels cannot silently turn a requested repair into identity.
            if p["is_noop"] != specmap[fid]["is_noop"]:
                p["reject"].append("requested_noop_mismatch")
            if not p["is_noop"] and p["model_input"] == p["target"]:
                p["reject"].append("empty_repair")
            p["reject"] = sorted(set(p["reject"]))
            rows.append(p)
            rejects.update(p["reject"])
    write_jsonl(ART / "pairs" / f"{name}.jsonl", rows)
    write_json(ART / "pairs" / f"{name}.stats.json", {"requested": count, "returned": len(rows),
               "structurally_valid": sum(not p["reject"] for p in rows), "rejects": dict(rejects)})
    print(json.dumps({"wave": name, "returned": len(rows), "valid": sum(not p["reject"] for p in rows)}))


def verify(name):
    rows = [p for p in read_jsonl(ART / "pairs" / f"{name}.jsonl") if not p["reject"]]
    requests, ids = {}, {}
    for i in range(0, len(rows), 10):
        chunk = rows[i:i+10]
        rid = f"ver-{name}-{i//10:05d}"
        ids[rid] = [p["pair_id"] for p in chunk]
        requests[rid] = {
            "model": "claude-opus-5-5", "max_tokens": 3000,
            "thinking": {"type": "adaptive"},
            "system": [{"type": "text", "text": VERIFY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": synth.verify_user(chunk)}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": synth.VERIFY_SCHEMA}}}
    w = wave("ver-" + name, requests, synth.parse_verify, "claude-opus-5-5", "verification")
    w.run(chunk=400)
    verdicts = {}
    for rid, pids in ids.items():
        o = w.outcomes.get(rid, {})
        vs = o.get("value", []) if o.get("status") == "succeeded" else []
        counts = collections.Counter(v.get("pair_id") for v in vs)
        for pid in pids:
            v = next((v for v in vs if v.get("pair_id") == pid), None)
            verdicts[pid] = v if v and counts[pid] == 1 else {"verdict": "UNVERIFIED", "reasons": ["missing_or_duplicate_verdict"]}
    accepted = []
    for p in rows:
        p["verification"] = verdicts[p["pair_id"]]
        if p["verification"]["verdict"] == "PASS":
            accepted.append(p)
    write_jsonl(ART / "accepted" / f"{name}.jsonl", accepted)
    write_json(ART / "claude" / ("ver-" + name) / "verdicts.json", verdicts)
    print(json.dumps({"wave": name, "checked": len(rows), "accepted": len(accepted),
                      "verdicts": dict(collections.Counter(v["verdict"] for v in verdicts.values())),
                      "cost": batches.ledger_totals()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["generate", "verify", "status"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--split", choices=["train", "validation", "test"])
    parser.add_argument("--count", type=int)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()
    if args.stage == "generate":
        generate(args.name, args.split, args.count, args.start)
    elif args.stage == "verify":
        verify(args.name)
    else:
        print(json.dumps(batches.ledger_totals(), indent=2))
