"""Focused contrast families with disjoint scenarios and independent labels."""
from __future__ import annotations

import argparse
import collections
import random
import re
from .common import *
from . import data

RUN = ART / "refinement"
COUNTS = {"train": 2400, "validation": 600, "test": 1200}
DOMAINS = {'train': ['container image pinning',
           'database index migration rehearsal',
           'certificate renewal rehearsal',
           'firmware telemetry replay',
           'backup catalog maintenance',
           'browser extension settings',
           'cardiac electrophysiology teaching',
           'gait analysis classroom notes',
           'respiratory physiology seminar',
           'tissue staining demonstration',
           'metabolomics sample indexing',
           'prosthetic socket fitting lecture',
           'conference room booking',
           'volunteer shift handover',
           'household recipe preparation',
           'parcel collection instructions',
           'woodwind instrument repair',
           'sailboat rig inspection',
           'elevator maintenance simulation',
           'textile loom setup',
           'photographic darkroom preparation',
           'chess tournament pairing',
           'theatre costume alterations',
           'bookbinding workshop'],
 'validation': ['shader cache invalidation',
                'speech synthesis pronunciation dictionary',
                'endocrine assay teaching',
                'vestibular rehabilitation seminar',
                'hotel housekeeping rota',
                'organ pipe voicing'],
 'test': ['transaction log restore drill',
          'GPU kernel trace labeling',
          'API schema compatibility review',
          'browser permission troubleshooting',
          'renal physiology lesson',
          'diffusion MRI annotation seminar',
          'immunology flow cytometry exercise',
          'biomechanics tendon loading tutorial',
          'food dehydrator maintenance',
          'community choir seating',
          'acoustic panel installation',
          'television caption timing']}
FOCI = [
    ("quantity_qualifier", 18, "Explicit quantity self-correction with a shared unit and an essential retained qualifier after the obsolete quantity. Keep that qualifier attached to the replacement: materials, purpose, location, concentration, uncertainty, or a limiting condition. Vary repeated versus omitted unit and include safe unresolved controls."),
    ("phrase_boundaries", 16, "Punctuation around multiword technical noun phrases, motion names, compound modifiers and ordinary verb phrases. The same words can form a noun phrase or an imperative in different contexts; use unmistakable context. Do not break a phrase into a sentence or detach a conjunction."),
    ("restriction_scope", 16, "Clear attachment of only, only if, only then, unless, except, negation and trailing qualifiers. Include a following independent instruction. Repair a boundary only where syntax establishes which instruction the restriction belongs to."),
    ("identifier_corrections", 12, "Local corrections of exact case-sensitive identifiers, versions, paths, dotted filenames, command flags and decimal units. Vary markers and terminal punctuation. Keep unrelated literals unchanged. Some ordinary actually, sorry and no are not correction markers."),
    ("function_words", 12, "Fragments and unusual but meaningful grammar with articles, pronouns, auxiliaries, prepositions and meaningful repetition. No grammatical completion or inserted connecting words is allowed. Allowed repairs affect punctuation, a pure filler or a genuine immediate function-word stutter only."),
    ("list_structure", 10, "Unambiguous dictated lists or ordered steps with conditions, and prose that only resembles a list. Preserve instruction order, keep conjunctions attached, and never turn a scoped qualifier into a separate action."),
    ("multiple_corrections", 10, "Two to four independently justified corrections, including repeated preposition plus replacement, compound I mean actually markers and a retained qualifier. Keep the surviving fact local and preserve unaffected instructions."),
    ("boundary_questions", 6, "Clear run-ons, questions versus indirect questions, paragraphs and already-valid semicolons or commas. Prefer the smallest defensible punctuation change and preserve optional stylistic punctuation."),
]

CONTRACT = """
This wave emphasizes minimal edits. For a requested preservation contrast, write already-valid
text that contains the tempting construction but requires no cleanup; target is byte-identical.
The contrast_group_id pairs scenarios by linguistic structure, not a request to duplicate text.
Keep its repair and preservation siblings within their assigned split. No public benchmark text.
For a genuine correction with a shared unit/head noun, an essential qualifier after the obsolete
quantity remains and attaches to the corrected quantity. Moving that exact retained qualifier
after the replacement is allowed only when its attachment is unambiguous. Do not invent any word.
If carrying a qualifier would be ambiguous, make a preservation example, not a destructive repair.
Never split a multiword phrase merely to make a sentence. Optional comma styling is not a repair.
"""


def plan(split, count=None):
    if split not in COUNTS:
        raise ValueError(split)
    count = COUNTS[split] if count is None else count
    if count <= 0 or count % 2:
        raise ValueError("Contrast plans require a positive even count")
    rng = random.Random("refinement:" + split)
    pool = [f for f, n, _ in FOCI for _ in range(n)]
    descriptions = {f: d for f, _, d in FOCI}
    specs = []
    for group in range(count // 2):
        focus = pool[group % len(pool)]
        domain = DOMAINS[split][group % len(DOMAINS[split])]
        situation = data.SITUATIONS[(group // len(DOMAINS[split])) % len(data.SITUATIONS)]
        long = group % 5 == 0
        length = rng.choice(["220-290", "330-430"]) if long else rng.choice(["15-35", "36-75", "76-140"])
        gid = f"v4-{split[:2]}-{group:05d}"
        for noop in (False, True):
            role = "preserve" if noop else "repair"
            specs.append({
                "family_id": gid + "-" + role, "contrast_group_id": gid,
                "focus": focus, "category": "long_instructions" if long else ("preserve_" if noop else "repair_") + focus,
                "description": descriptions[focus] + (" Already correct: target must be exactly the input." if noop else " Make one or more clear useful repairs without any optional styling."),
                "length": length + " words", "split": split, "destination_profile": "notes",
                "topic_anchors": [domain, situation], "scenario_family": domain + "|" + situation,
                "technique": "A coherent single message with a decisive qualifier late in the message." if long else data.TECHNIQUES[group % len(data.TECHNIQUES)],
                "is_noop": noop, "variation": f"Independent wording for {role} contrast {gid}; seed {rng.randrange(10**8)}.",
            })
    return specs


def generate(split):
    name = "refinement-" + split
    specs = plan(split)
    path = ART / "claude" / name / "specs.json"
    existing = read_json(path)
    if existing is not None and existing != specs:
        raise RuntimeError("A refinement generation plan already exists with different contents")
    write_json(path, specs)
    old_gen, old_verify = data.GEN_SYSTEM, data.VERIFY_SYSTEM
    try:
        data.GEN_SYSTEM += CONTRACT
        data.VERIFY_SYSTEM += CONTRACT.replace("This wave emphasizes", "Independent checking requires")
        data.generate(name, split, len(specs), batch_chunk=80)
        data.verify(name)
    finally:
        data.GEN_SYSTEM, data.VERIFY_SYSTEM = old_gen, old_verify
    metadata = {s["family_id"]: s for s in specs}
    for kind in ("pairs", "accepted"):
        dest = ART / kind / (name + ".jsonl")
        rows = read_jsonl(dest)
        for row in rows:
            spec = metadata[row["family_id"]]
            row.update(contrast_group_id=spec["contrast_group_id"], focus=spec["focus"])
        write_jsonl(dest, rows)


def correction_offsets(row):
    """Anchor checked correction labels without running any candidate engine."""
    source = row["model_input"]
    offsets, cursor = [], 0
    for line in row.get("gold_lines", []):
        if not isinstance(line, str) or not line:
            raise ValueError(f"Empty correction label in {row['case_id']}")
        pattern = (r"(?<!\w)" if line[0].isalnum() or line[0] == "_" else "")
        pattern += re.escape(line)
        pattern += r"(?!\w)" if line[-1].isalnum() or line[-1] == "_" else ""
        matches = list(re.finditer(pattern, source[cursor:], re.IGNORECASE))
        if len(matches) != 1:
            kind = "Missing" if not matches else "Ambiguous"
            raise ValueError(f"{kind} correction label in {row['case_id']}")
        match = matches[0]
        start, end = cursor + match.start(), cursor + match.end()
        offsets.append([start, end])
        cursor = end
    return offsets


def assemble(split):
    """Filter by independent labels and prior text, never candidate success."""
    from .assemble import Dedup
    from lfx.assemble import production_examples, fixture_texts
    from lfx.synth import normalize_text, shingles, jaccard
    from localflow.v2.cleanup import protected_spans_for_cleanup
    if split not in COUNTS:
        raise ValueError(split)
    dest = RUN / ("synthetic-" + split + ".jsonl")
    if dest.exists():
        existing = read_jsonl(dest)
        if any(row.get("gold_offsets") != correction_offsets(row) for row in existing):
            raise RuntimeError("Existing assembled labels lack matching correction offsets; do not reuse them")
        return {"already_assembled": len(existing)}
    idx = Dedup()
    exclusions = [
        *[OLD_ART / "dataset" / (s + ".jsonl") for s in ("train", "validation")],
        *sorted((OLD_ART / "frozen").glob("*.jsonl")),
        *[ART / "dataset" / (s + ".jsonl") for s in ("train", "validation", "test")],
        *sorted((ART / "pairs").glob("*.jsonl")),
    ]
    # Every returned other-split pair is excluded, even rejected labels. Similar
    # siblings within the same contrast group are intentionally allowed.
    for path in exclusions:
        if path.name == "refinement-" + split + ".jsonl":
            continue
        for row in read_jsonl(path):
            for field in ("model_input", "target"):
                text = row.get(field)
                if text:
                    idx.add(text, str(path.relative_to(ROOT)), check=False)
    for text in production_examples() + fixture_texts():
        idx.add(text, "prompt_or_fixture", check=False)
    groups = collections.defaultdict(list)
    for row in read_jsonl(ART / "accepted" / ("refinement-" + split + ".jsonl")):
        groups[row["contrast_group_id"]].append(row)
    if not groups:
        raise RuntimeError("No independently accepted labels")
    kept, rejected = [], []
    for gid, rows in sorted(groups.items()):
        accepted = []
        for row in rows:
            # Check without mutating the shared index until both siblings have
            # been checked. A near-duplicate sibling is part of the design.
            text = row["model_input"] + " " + row["target"]
            hit = idx.exact.get(" ".join(text.casefold().split()))
            sh = shingles(text)
            candidates = set().union(*(idx.index.get(s, set()) for s in sh)) if sh else set()
            if not hit:
                hit = next((idx.shingles[i][1] for i in sorted(candidates)
                            if jaccard(sh, idx.shingles[i][0]) >= 0.6), None)
            if hit:
                rejected.append({"case_id": row["case_id"], "reason": "duplicate", "matched": hit})
                continue
            norm = normalize_text(row["raw_input"])
            if norm.text != row["model_input"]:
                raise RuntimeError("Label normalization changed")
            row["gold_offsets"] = correction_offsets(row)
            row["protected_spans"] = [list(p) for p in protected_spans_for_cleanup(row["raw_input"], norm.text, norm.protected, norm.edits)]
            accepted.append(row)
        for row in accepted:
            for text in (row["model_input"], row["target"], row["model_input"] + " " + row["target"]):
                idx.add(text, gid, check=False)
        kept.extend(accepted)
    write_jsonl(dest, kept)
    receipt = {"created": utc_now(), "accepted": len(kept), "sha256": file_sha256(dest),
               "noops": sum(r["is_noop"] for r in kept),
               "long_over_200": sum(len(r["model_input"].split()) > 200 for r in kept),
               "focus": dict(collections.Counter(r["focus"] for r in kept)), "excluded": rejected,
               "labels": "Independent Opus acceptance; no engine-output or model-success filtering",
               "exclusion_files": {str(p.relative_to(ROOT)): file_sha256(p) for p in exclusions}}
    write_json(RUN / ("synthetic-" + split + ".selection.json"), receipt)
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["generate", "assemble"])
    p.add_argument("split", choices=list(COUNTS))
    args = p.parse_args()
    result = generate(args.split) if args.stage == "generate" else assemble(args.split)
    print(__import__("json").dumps(result))
