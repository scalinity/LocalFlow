"""TRAIN-only contrast families for the remaining weak spots: long dictation with
several self-corrections, sentence-level restatements, spoken ordinals that stay
prose, and label-like openings that keep their comma. Every family is a repair
and an already-correct twin; domains are disjoint from development and final."""
from __future__ import annotations

import argparse
import collections
import random
from .common import *
from . import data

NAME = "longform-train"
GROUPS = 600
DOMAINS = [
    "glacier mass-balance fieldwork", "apiary inspection rounds", "orchestra library parts",
    "hospital pharmacy restock", "radio telescope calibration", "vineyard canopy management",
    "kiln firing schedule", "ferry timetable changes", "climbing gym route setting",
    "seed bank germination tests", "podcast audio mastering", "veterinary clinic intake",
    "bicycle wheel truing", "archive digitization queue", "soil moisture sensor rollout",
    "printmaking studio etching", "warehouse cycle counting", "planetarium show programming",
    "dental lab crown milling", "marathon aid station planning",
]
FOCI = [
    ("long_corrections", 9, "A long single message (220-600 words) with two to five explicit self-corrections of different kinds: a quantity with its unit and a retained qualifier, a corrected name or identifier, an 'I mean' or 'no wait' correction, and a sentence-level restatement after 'Sorry'. Also include a few genuine punctuation repairs (a run-on between complete instructions, a missing question mark), contractions, and ordinary non-correction uses of actually, sorry and no. Occasionally the speaker says 'new paragraph'; that break is already rendered and must be kept exactly. Never add a paragraph break."),
    ("restatement", 4, "A correction made by restating the whole previous sentence or clause after 'Sorry', 'No wait' or 'I mean' with one value changed (for example: assign 4 rooms to Marta. Sorry, 6 rooms to Marta). The target keeps only the restatement and every other word. The preservation twin uses sorry, no or actually in their ordinary senses (an apology, a refusal, emphasis) with nothing to correct."),
    ("ordinal_prose", 4, "Steps or reasons spoken with ordinals (first, second, third, finally) inside ordinary sentences, with no step labels and no explicit list introduction. They stay prose exactly as dictated. The repair twin fixes something else (a filler, a run-on, a missing question mark) and leaves the ordinals and their commas untouched."),
    ("heading_openings", 3, "A message that opens with a label-like phrase followed by a comma (for example 'Handover note for the night shift, the dryer on two is down' or 'Reminder, bring the gauge') or with 'Okay so'. The opening stays exactly as dictated: no colon, no added comma. The repair twin fixes a real error later in the message."),
]
CONTRACT = """
This wave teaches minimal edits on long and tricky dictation. For a preservation twin, write
already-valid text containing the tempting construction; the target is byte-identical. Paragraph
breaks are never added. Optional commas are never added and a valid comma is never replaced by a
colon, semicolon or dash. Spoken ordinals stay prose. A sentence-level restatement correction
deletes the obsolete sentence or clause through its marker and keeps the restatement; such a
deleted_span may exceed six words only when the restatement repeats the same frame with one value
changed. Keep every other word, number, unit, qualifier, recipient, negation and identifier.
"""


def plan() -> list[dict]:
    rng = random.Random(NAME)
    pool = [f for f, n, _ in FOCI for _ in range(n)]
    rng.shuffle(pool)
    describe = {f: d for f, _, d in FOCI}
    specs = []
    for group in range(GROUPS):
        focus = pool[group % len(pool)]
        domain = DOMAINS[group % len(DOMAINS)]
        situation = data.SITUATIONS[(group // len(DOMAINS)) % len(data.SITUATIONS)]
        long = focus == "long_corrections"
        length = rng.choice(["220-300", "300-420", "420-600"]) if long else rng.choice(["20-45", "46-90", "91-160"])
        gid = f"v5-tr-{group:05d}"
        for noop in (False, True):
            role = "preserve" if noop else "repair"
            specs.append({
                "family_id": f"{gid}-{role}", "contrast_group_id": gid, "focus": focus,
                "category": "long_instructions" if long else ("preserve_" if noop else "repair_") + focus,
                "description": describe[focus] + (" Already correct: target must be exactly the input." if noop
                                                  else " Make every needed repair and nothing optional."),
                "length": length + " words", "split": "train",
                "destination_profile": rng.choice(["notes", "email", "messaging", "documents", None]),
                "topic_anchors": [domain, situation], "scenario_family": domain + "|" + situation,
                "technique": data.TECHNIQUES[group % len(data.TECHNIQUES)],
                "is_noop": noop,
                "variation": f"Independent wording for {role} contrast {gid}; seed {rng.randrange(10**8)}.",
            })
    return specs


def generate() -> None:
    specs = plan()
    path = ART / "claude" / NAME / "specs.json"
    existing = read_json(path)
    if existing is not None and existing != specs:
        raise RuntimeError("A longform generation plan already exists with different contents")
    write_json(path, specs)
    old_gen, old_verify = data.GEN_SYSTEM, data.VERIFY_SYSTEM
    try:
        data.GEN_SYSTEM += CONTRACT
        data.VERIFY_SYSTEM += CONTRACT.replace("This wave teaches", "Independent checking applies")
        data.generate(NAME, "train", len(specs), batch_chunk=200, model="claude-haiku-5-5", per_request=1,
                      thinking={"type": "adaptive"}, effort="medium")
        data.verify(NAME)
    finally:
        data.GEN_SYSTEM, data.VERIFY_SYSTEM = old_gen, old_verify
    meta = {s["family_id"]: s for s in specs}
    for kind in ("pairs", "accepted"):
        dest = ART / kind / (NAME + ".jsonl")
        rows = read_jsonl(dest)
        for row in rows:
            row.update(contrast_group_id=meta[row["family_id"]]["contrast_group_id"], focus=meta[row["family_id"]]["focus"])
        write_jsonl(dest, rows)


def assemble() -> dict:
    """Keep independently accepted pairs that share no text with any other split or earlier wave."""
    from .assemble import Dedup
    from .refinement_data import correction_offsets
    from lfx.assemble import production_examples, fixture_texts
    from lfx.synth import normalize_text, shingles, jaccard
    from localflow.v2.cleanup import protected_spans_for_cleanup
    dest = ART / "longform" / "train.jsonl"
    if dest.exists():
        return {"already_assembled": len(read_jsonl(dest))}
    idx = Dedup()
    sources = [
        *[OLD_ART / "dataset" / (s + ".jsonl") for s in ("train", "validation")],
        *sorted((OLD_ART / "frozen").glob("*.jsonl")),
        *[ART / "dataset" / (s + ".jsonl") for s in ("train", "validation", "test")],
        *[ART / "refinement" / "dataset" / (s + ".jsonl") for s in ("train", "validation", "test")],
        *[p for p in sorted((ART / "pairs").glob("*.jsonl")) if p.name != NAME + ".jsonl"],
    ]
    for path in sources:
        for row in read_jsonl(path):
            for field in ("model_input", "target"):
                if row.get(field):
                    idx.add(row[field], str(path.relative_to(ROOT)), check=False)
    for text in production_examples() + fixture_texts():
        idx.add(text, "prompt_or_fixture", check=False)
    groups = collections.defaultdict(list)
    for row in read_jsonl(ART / "accepted" / (NAME + ".jsonl")):
        groups[row["contrast_group_id"]].append(row)
    kept, rejected = [], []
    for gid, rows in sorted(groups.items()):
        accepted = []
        for row in rows:
            texts = (row["model_input"], row["target"])
            hit = next((idx.exact.get(" ".join(t.casefold().split())) for t in texts
                        if idx.exact.get(" ".join(t.casefold().split()))), None)
            if not hit:
                sh = shingles(row["model_input"] + " " + row["target"])
                cands = set().union(*(idx.index.get(s, set()) for s in sh)) if sh else set()
                hit = next((idx.shingles[i][1] for i in sorted(cands) if jaccard(sh, idx.shingles[i][0]) >= 0.6), None)
            if hit:
                rejected.append({"case_id": row["case_id"], "reason": "duplicate", "matched": hit})
                continue
            norm = normalize_text(row["raw_input"])
            if norm.text != row["model_input"]:
                rejected.append({"case_id": row["case_id"], "reason": "normalization_mismatch"})
                continue
            try:
                row["gold_offsets"] = correction_offsets(row)
            except ValueError as exc:
                rejected.append({"case_id": row["case_id"], "reason": str(exc)})
                continue
            row["protected_spans"] = [list(p) for p in protected_spans_for_cleanup(row["raw_input"], norm.text, norm.protected, norm.edits)]
            accepted.append(row)
        for row in accepted:
            for text in (row["model_input"], row["target"]):
                idx.add(text, gid, check=False)
        kept.extend(accepted)
    write_jsonl(dest, kept)
    receipt = {"created": utc_now(), "accepted": len(kept), "sha256": file_sha256(dest),
               "noops": sum(bool(r["is_noop"]) for r in kept),
               "long_over_200": sum(len(r["model_input"].split()) > 200 for r in kept),
               "focus": dict(collections.Counter(r["focus"] for r in kept)), "excluded": rejected}
    write_json(ART / "longform" / "train.selection.json", receipt)
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["plan", "generate", "assemble"])
    stage = p.parse_args().stage
    if stage == "plan":
        specs = plan()
        print(__import__("json").dumps({"families": len(specs), "focus": dict(collections.Counter(s["focus"] for s in specs))}))
    else:
        result = generate() if stage == "generate" else assemble()
        print(__import__("json").dumps(result))
