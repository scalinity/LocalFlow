"""TRAIN-only minimal pairs for two conventions the earlier labels contradict.

Spoken step labels make a numbered list and an explicit item-list introduction
makes bullets, while the same content spoken with ordinals stays prose; a direct
question run into a because-clause is split, while an indirect one stays a
statement. Both twins of a family come from one request, so they share content
and differ only in the trigger words. Domains are disjoint from every other split.
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import random
import re
from .common import *
from . import data
from .policy_score import _aligned_gaps, _marks, _pieces, _split, minimal_target
from lfx import batches

NAME = "contrast-train"
RETRY = NAME + "-retry"
WAVES = (NAME, RETRY)
REFERENCE = "refinement-train"
CEILING_USD = 15.0
KINDS = {"steps": 60, "items": 60, "question": 80}
SIDES = {"steps": ("list", "prose"), "items": ("list", "prose"), "question": ("split", "statement")}
DOMAINS = [
    "community garden plot allocation", "sourdough bakery production", "bike-share fleet rebalancing",
    "aquarium water chemistry", "school robotics club", "farmers market stall setup",
    "home brewing fermentation", "wildfire lookout radio checks", "film festival projection booth",
    "ice rink resurfacing", "sign language interpreting rota", "tree nursery grafting",
    "animal shelter adoption events", "ski patrol equipment checks", "public pool lifeguard rota",
    "model railway club layout", "food bank delivery routes", "escape room puzzle resets",
    "violin rental program", "tide pool field class", "makerspace laser cutter",
    "coffee roastery cupping", "solar panel cleaning crew", "rowing club boat maintenance",
]
BANDS = {"steps": ["15-35", "36-70", "71-120"], "items": ["15-35", "36-70", "71-120"],
         "question": ["10-25", "26-50", "51-90"]}
NOISE = [
    "Raw recognizer run-on: all lowercase, no punctuation at all.",
    "Lowercase-leaning: lowercase sentence starts, a stray comma or two, no final period.",
    "Mostly cased with some sentence punctuation, but a run-on join and no final period.",
    "Lowercase with one or two um or uh fillers.",
]
PROFILES = ["notes", "email", "messaging", "documents", None]

LEAD_GEN = "\nThis wave teaches these conventions with minimal pairs; where they are stricter than the rules above, they win.\n"
LEAD_VERIFY = "\nIndependent checking applies these conventions; where they are stricter than the rules above, they win.\n"
POLICY = """
Lists
- A numbered list comes only from two or more consecutive spoken step labels ("step 1 ... step 2",
  "step one ... step two") introducing actions or questions. Each label is replaced by its "1." or
  "2." marker at the start of the item's line; the item keeps its words, starts with a capital
  letter and ends with a period. A connective that only joins two step labels ("and step 3") is
  dropped.
- Bullets come only when the transcript explicitly introduces a list of distinct items ("here is my
  packing list", "for saturday the shopping list"). Each item goes on its own "- " line with its
  dictated words and case and no period; the final "and" joining the last two items is dropped,
  while an "and" inside an item stays ("salt and pepper").
- An introduction stays prose ending with a colon on the line before the first item; a dictated
  comma there becomes the colon. A closing sentence stays outside the list, on the next line after
  a single newline. A blank line is never added.
- Ordinal words (first, second, third, fourth, fifth, next, then, finally) never make a list, even
  when the speaker mentions "steps" or "list", even right after a list introduction. That text
  stays prose with only the required repairs and keeps every ordinal word.
- Prose repairs keep every dictated mark, capitalize sentence starts, names and "I", and end the
  message with a period. A complete instruction that runs straight into the next ordinal ends with
  a period, and the ordinal starts the next sentence. Ordinal-introduced noun phrases that run
  together are separated by commas, with no comma before "and". A complete introductory sentence
  ("here is my packing list") ends with a period. No colon and no comma after an ordinal word.

Questions
- A direct question run into a because-clause that gives the speaker's reason for asking is split:
  the question ends with "?" and "Because" opens the next sentence ("Did you check the cable?
  Because I think it's loose."). A dictated comma before because becomes that question mark.
- An indirect question ("I wonder whether the cable is loose because ...") is a statement: no "?"
  and no split before because; a dictated comma before because stays.

Minimal edits
- Readable text stays exactly as dictated. Only um, uh, erm, ehm, hmm and mhm fillers are deleted.
  No paragraph break is added (only a spoken "new paragraph" makes one), no "Okay," polish and no
  undictated word.
- A comma the dictation lacked is added only when it separates list items, sets off an addressed
  person ("Hey Ana, are we ..."), prevents a likely misreading, or follows a date, place or number
  convention.
"""
PAIRING = """
Each request holds both twins of one contrast family (one contrast_group_id). Write them from one
shared message: the same topic, names, numbers, wording, fillers and punctuation, so the transcripts
differ only in the trigger words the twin descriptions name, and the targets differ only in those
words and the formatting the rules prescribe.
- Write the recognizer noise the technique names. Both twins need at least one repair besides the
  list or question decision; is_noop is false for both.
- No self-corrections, repeated words, quotation marks or question marks in any transcript. No mark
  right after a spoken step label. The only ordinal words are first, second, third, fourth, fifth,
  next, then and finally.
- A bullet introduction ends with the word list right before the first item, or is the opening
  sentence of the message and begins with "here is" or "here are". No filler between a bullet
  introduction and the last item.
- A question family says "because" exactly once, and its because-clause is the speaker's own reason
  for asking, never the thing the question asks about.
"""
# Generator-only emphasis for the retry, from the first wave's losses: number words listed as facts
# the normalizer turned into digits, fillers before bullet items (the engine matches the introduction
# and items word for word, fillers included), introductions left without a colon, commas around
# ordinals, and an "and" deleted to split a sentence. Verification keeps the first wave's contract.
RETRY_GUIDANCE = """
The first wave lost families to these mistakes; avoid them.
- Write quantities, times and counts as digits (3, 12, 6:30), as the recognizer does.
- critical_facts: only names and numbers, copied exactly as the target writes them. Never list a
  step label, an ordinal word or a list marker as a fact.
- In an item family no filler appears anywhere before the last item, the introduction included,
  because the app matches the introduction and the items word for word; fillers may appear only
  after the last item. Bullet items start with a lowercase word, as dictated.
- In a list twin, whatever text comes right before the first item ends with a colon, even where the
  transcript has a comma or period there.
- In a prose twin, no comma follows an ordinal word or comes before "and", a dictated comma stays a
  comma, and "and" before an ordinal never starts a new sentence.
- Keep every word except fillers, step labels, connectives joining two step labels and the final
  list-joining "and"; never delete an "and" to make a sentence break.
"""


def _describe(gid, kind, side, f):
    unit = "action" if kind == "steps" else "item"
    # prepare_family rejects a target missing any of the last three source words, so a final
    # list-joining "and" must not be among them.
    closing = (f"Close with one short sentence after the last {unit}." if f["closing"] else
               f"Nothing follows the last {unit}, which has at least three words after its label or 'and'.")
    ordinals = "an ordinal word (first, second, third, fourth, fifth, next, then, finally)"
    prose = "Target: prose with only the required repairs."
    if kind == "steps" and side == "list":
        intro = ("Open with a short introduction that mentions the steps in passing, such as 'here are the steps "
                 "for ...' or 'follow these steps to ...'." if f["mention"] else
                 "Open with a short lead-in that never says step, steps or list, such as 'for the pump swap'."
                 if f["intro"] else "Start with the first step label; no introduction.")
        return (f"Twin (i) of {gid}. {f['items']} actions, each opened by a spoken step label counting up from "
                f"step one (as words or digits), with no mark after a label. {intro} {closing} "
                "Target: the numbered list.")
    if kind == "steps":
        mention = ("Its introduction still mentions the steps in passing; that makes no list." if f["mention"]
                   else "It never says step, steps or list.")
        return f"Twin (ii) of {gid}. Twin (i)'s transcript with each step label replaced by {ordinals} and nothing else changed. {mention} {prose}"
    if kind == "items" and side == "list":
        return (f"Twin (i) of {gid}. An introduction that ends with the word list right before the first item "
                "(for example 'here is my packing list' or 'for saturday the shopping list'), then "
                f"{f['items']} distinct short items (noun phrases), the last two joined by 'and'. {closing} "
                "Target: the introduction ending with a colon, then one bulleted item per line.")
    if kind == "items" and f["mention"]:
        return (f"Twin (ii) of {gid}. Twin (i)'s transcript, list introduction included, with {ordinals} added "
                "before each item and nothing else changed. The list is only mentioned in passing; the ordinals "
                f"keep it prose. {prose}")
    if kind == "items":
        return (f"Twin (ii) of {gid}. Twin (i)'s transcript with its list introduction replaced by a plain lead-in "
                "of at most eight words that never says list or steps (for example 'for saturday we need'), and "
                f"{ordinals} added before each item; nothing else changed. {prose}")
    if side == "split":
        return (f"Twin (i) of {gid}. A direct question run into a because-clause that gives the speaker's own "
                f"reason for asking, with {'a comma' if f['comma'] else 'no mark'} before because. "
                "Target: the question ends with '?' and 'Because' opens the next sentence.")
    return (f"Twin (ii) of {gid}. Twin (i)'s transcript with the direct question reworded as an indirect question "
            "('I wonder whether ...', 'I'm not sure if ...', 'I was wondering if you could ...'), changing at most "
            "six words at its start and in its verb form; the because-clause and everything else stay identical. "
            "Target: a statement with no '?' and no split before because.")


def plan(wave: str = NAME) -> list[dict]:
    """Two twin specs per family, adjacent and list or split side first. Family attributes are
    the same for every wave; only the wording seed changes, so a retry keeps the plan balance."""
    rng = random.Random(NAME)
    specs = []
    for k, (kind, count) in enumerate(KINDS.items()):
        for n in range(count):
            gid = f"v6-tr-{kind}-{n:03d}"
            family = {"items": rng.choice([2, 3, 3, 4, 5]), "intro": rng.random() < 0.5,
                      "closing": rng.random() < 0.4, "mention": kind != "question" and n % 2 == 0,
                      "comma": n % 2 == 1}
            length = rng.choice(BANDS[kind])
            profile = rng.choice(PROFILES)
            domain = DOMAINS[(n + 8 * k) % len(DOMAINS)]
            situation = data.SITUATIONS[(5 * n + k) % len(data.SITUATIONS)]
            seed = random.Random(f"{wave}:{gid}").randrange(10**8)
            for side in SIDES[kind]:
                specs.append({
                    "family_id": f"{gid}-{side}", "contrast_group_id": gid, "focus": kind, "twin": side,
                    "category": f"{kind}_{side}", "description": _describe(gid, kind, side, family),
                    "length": length + " words", "split": "train", "destination_profile": profile,
                    "topic_anchors": [domain, situation], "scenario_family": domain + "|" + situation,
                    "technique": NOISE[(n + k) % len(NOISE)], "is_noop": False,
                    "mentions_steps_or_list": family["mention"],
                    "variation": f"Fresh wording for contrast {gid}; seed {seed}.",
                })
    return specs


# ---------------------------------------------------------------- twin check

FILLERS = {"um", "uh", "erm", "ehm", "hmm", "mhm"}
ORDINALS = {"first", "second", "third", "fourth", "fifth", "next", "then", "finally"}
NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
CONNECTIVES = {"and", "also"}
MENTIONS = {"step", "steps", "list", "lists"}
FRAME_WORDS = 8
ITEM_LINE = re.compile(r"^\s*(?:\d+\.|[-•*])\s")
MARKER = re.compile(r"(?m)^(?:\d+\.|[-•*])[ \t]+")
NUMBERED = re.compile(r"^(\d+)\. \S")
BULLET = re.compile(r"^- \S")


def _skeleton(text):
    """Words without spoken step labels and ordinal words, the mark in each gap between kept
    words (None where a trigger sat), trigger counts and the kept position of the first trigger."""
    words, gaps = _pieces(text)
    words = [w.casefold().replace("’", "'") for w in words]
    kept, marks = [], [_marks(gaps[0])]
    labels = ordinals = 0
    first = None
    i = 0
    while i < len(words):
        j = i + 1 + (i + 1 < len(words) and words[i + 1] == "number")
        label = words[i] == "step" and j < len(words) and (words[j].isdigit() or words[j] in NUMBER_WORDS)
        if label or words[i] in ORDINALS:
            labels += label
            ordinals += not label
            first = len(kept) if first is None else first
            marks[-1] = None
            i = j + 1 if label else i + 1
            continue
        kept.append(words[i])
        marks.append(_marks(gaps[i + 1]))
        i += 1
    return {"words": kept, "marks": marks, "labels": labels, "ordinals": ordinals,
            "first_trigger": len(kept) if first is None else first}


def _differences(a, b, connectives=False):
    """Non-equal opcodes between two skeletons, optionally ignoring connectives only side b keeps."""
    ops = difflib.SequenceMatcher(None, a["words"], b["words"], autojunk=False).get_opcodes()
    return ops, [op for op in ops if op[0] != "equal" and not (
        connectives and op[0] == "insert" and set(b["words"][op[3]:op[4]]) <= CONNECTIVES)]


def _marks_match(ops, a, b):
    """Gap marks agree wherever both sides keep the same two neighbouring words."""
    for tag, i1, i2, j1, j2 in ops:
        if tag != "equal":
            continue
        lo = 0 if i1 == 0 and j1 == 0 else 1
        hi = i2 - i1 if i2 == len(a["words"]) and j2 == len(b["words"]) else i2 - i1 - 1
        for k in range(lo, hi + 1):
            if None not in (a["marks"][i1 + k], b["marks"][j1 + k]) and a["marks"][i1 + k] != b["marks"][j1 + k]:
                return False
    return True


def _frame_ok(diffs, end_a, end_b):
    """Some, but at most FRAME_WORDS, differing words per side, all before the given kept positions."""
    return (bool(diffs) and sum(op[2] - op[1] for op in diffs) <= FRAME_WORDS
            and sum(op[4] - op[3] for op in diffs) <= FRAME_WORDS
            and max(op[2] for op in diffs) <= end_a and max(op[4] for op in diffs) <= end_b)


def _list_shape(target, numbered):
    """Problem with the prescribed list layout, else None."""
    lines = target.split("\n")
    marker = NUMBERED if numbered else BULLET
    items = [i for i, line in enumerate(lines) if marker.match(line)]
    if len(items) < 2 or items != list(range(items[0], items[0] + len(items))) \
            or [i for i, line in enumerate(lines) if ITEM_LINE.match(line)] != items:
        return "list_not_one_run"
    if any(not line.strip() for line in lines):
        return "blank_line"
    if items[0] and not lines[items[0] - 1].rstrip().endswith(":"):
        return "introduction_without_colon"
    if any(re.match(r"(?:\d+\.|-) and\b", lines[i], re.I) or re.search(r"\band\.?$", lines[i]) for i in items):
        return "list_join_kept"
    if not numbered and (not items[0] or "list" not in _skeleton(lines[items[0] - 1])["words"]):
        return "bullets_without_list_introduction"
    return None


def _added_marks(row):
    """Punctuation a prose or statement twin adds beyond its required repairs, else None: a sentence
    break before a dictated "and" or in place of a dictated comma, or a comma at an ordinal."""
    source_words, source_gaps = _split(row["model_input"])
    words, gaps = _split(row["target"])
    for k, j in _aligned_gaps(source_words, words).items():
        if not 0 < k < len(words):
            continue
        s, t = _marks(source_gaps[j]), _marks(gaps[k])
        if re.search(r"[.!?]", t) and not re.search(r"[.!?]", s) and (words[k] == "and" or "," in s):
            return "adds_sentence_break"
        at_ordinal = words[k - 1] in ORDINALS or (words[k] == "and" and k + 1 < len(words) and words[k + 1] in ORDINALS)
        if "," in t and "," not in s and at_ordinal:
            return "adds_comma_at_ordinal"
    return None


def twin_check(kind, mention, first, second):
    """Why two twins differ in more than their trigger words and prescribed formatting, else None.

    first is the list or split twin and second the prose or statement twin. Sources must match
    once step labels and ordinals are removed; a question frame, or the list introduction of an
    item family that never mentions a list, may differ in a few words before the content they share.
    """
    sa, sb = _skeleton(first["model_input"]), _skeleton(second["model_input"])
    ta, tb = _skeleton(MARKER.sub("", first["target"])), _skeleton(second["target"])
    ops, diffs = _differences(sa, sb)
    if kind == "question":
        if sa["words"].count("because") != 1 or sb["words"].count("because") != 1:
            return "because_not_said_once"
        if not _frame_ok(diffs, sa["words"].index("because"), sb["words"].index("because")):
            return "question_frames_differ_beyond_opening"
        if not _marks_match(ops, sa, sb):
            return "source_marks_differ"
        if first["target"].count("?") != 1 or not re.search(r"\? Because\b", first["target"]) or "\n" in first["target"]:
            return "direct_question_not_split"
        if "?" in second["target"] or "\n" in second["target"] or re.search(r"[.!?]\s+because\b", second["target"], re.I):
            return "indirect_question_not_a_statement"
        _, t_diffs = _differences(ta, tb)
        if "because" not in ta["words"] or "because" not in tb["words"] or not _frame_ok(
                t_diffs, ta["words"].index("because"), tb["words"].index("because")):
            return "targets_differ_beyond_frame"
        added = _added_marks(second)
        return "statement_" + added if added else None
    said = {w.casefold() for w in _pieces(second["model_input"])[0]}
    if bool(said & MENTIONS) != mention:
        return "mention_does_not_match_plan"
    if sb["labels"] or sb["ordinals"] < 2 or (sa["labels"] < 2 if kind == "steps" else sa["labels"]):
        return "trigger_words_missing"
    framed = kind == "items" and not mention
    if framed:
        changed = {w for op in diffs for w in sa["words"][op[1]:op[2]]}
        if not _frame_ok(diffs, len(sa["words"]), sb["first_trigger"]) or "list" not in changed:
            return "introductions_differ_beyond_lead_in"
    elif diffs:
        return "sources_differ_beyond_triggers"
    if not _marks_match(ops, sa, sb):
        return "source_marks_differ"
    shape = _list_shape(first["target"], kind == "steps")
    if shape:
        return shape
    if kind == "steps":
        numbers = [int(m[1]) for m in map(NUMBERED.match, first["target"].split("\n")) if m]
        spoken = re.search(r"\bstep\s+(?:number\s+)?(\d+)", first["model_input"], re.I)
        if len(numbers) != sa["labels"] or ta["labels"] or not spoken or numbers != list(
                range(int(spoken[1]), int(spoken[1]) + len(numbers))):
            return "numbering_does_not_match_labels"
    if "\n" in second["target"] or tb["labels"] or tb["ordinals"] != sb["ordinals"]:
        return "ordinal_twin_not_prose"
    added = _added_marks(second)
    if added:
        return "prose_" + added
    _, t_diffs = _differences(ta, tb, connectives=True)
    if framed:
        lines = first["target"].split("\n")
        intro = "\n".join(lines[:next(i for i, line in enumerate(lines) if BULLET.match(line))])
        if not _frame_ok(t_diffs, len(_skeleton(intro)["words"]), tb["first_trigger"]):
            return "targets_differ_beyond_lead_in"
    elif t_diffs:
        return "targets_differ_beyond_triggers"
    return None


# ---------------------------------------------------------------- spend

def _settled(wave):
    return sum(e.get("actual_usd", 0.0) for k, e in batches.ledger()["entries"].items() if k.split("#")[0] == wave)


def spend() -> dict:
    """Settled USD of each wave in this lane, from the shared ledger."""
    return {w: round(_settled(w), 6) for name in WAVES for w in (name, "ver-" + name)}


def _rates(wave):
    """Settled generation and verification USD per returned row of a finished wave."""
    rows = len(read_jsonl(ART / "pairs" / (wave + ".jsonl")))
    return _settled(wave) / rows, _settled("ver-" + wave) / rows


def _check_budget(stage, rows, usd_per_row):
    spent = sum(spend().values())
    estimate = rows * usd_per_row
    print(json.dumps({"stage": stage, "rows": rows, "usd_per_row": round(usd_per_row, 5),
                      "estimate_usd": round(estimate, 4), "lane_spent_usd": round(spent, 4),
                      "ceiling_usd": CEILING_USD}))
    if spent + estimate > CEILING_USD:
        raise batches.BudgetExceeded(f"{stage}: ${estimate:.2f} estimated on top of ${spent:.2f} spent "
                                     f"crosses the lane's ${CEILING_USD:.2f} ceiling")


# ---------------------------------------------------------------- waves

class _BudgetedWave(data.Wave):
    def submit_pending(self, limit=None):
        bases = self.pending()[:limit or None]
        if bases:
            names = {w for name in WAVES for w in (name, "ver-" + name)}
            entries = [entry for key, entry in batches.ledger()["entries"].items()
                       if key.split("#")[0] in names]
            committed = sum(entry.get("actual_usd", 0.0)
                            + (entry["max_usd"] if entry["state"] == "outstanding" else 0.0)
                            for entry in entries)
            maximum = sum(batches.max_charge(self.est_input_tokens(self.requests[base]),
                                            self.requests[base]["max_tokens"]) for base in bases)
            if committed + maximum > CEILING_USD:
                raise batches.BudgetExceeded(
                    f"{self.name}: ${committed:.2f} committed plus ${maximum:.2f} maximum "
                    f"crosses the lane's ${CEILING_USD:.2f} ceiling")
        # The shared controller still enforces the global cap and handles retries.
        return super().submit_pending(limit)


def _wave(name, specs, rates, guidance="") -> None:
    path = ART / "claude" / name / "specs.json"
    existing = read_json(path)
    if existing is not None and existing != specs:
        raise RuntimeError(f"{name} already has a different generation plan")
    write_json(path, specs)
    old_gen, old_verify, old_wave = data.GEN_SYSTEM, data.VERIFY_SYSTEM, data.Wave
    try:
        data.Wave = _BudgetedWave
        data.GEN_SYSTEM += LEAD_GEN + POLICY + PAIRING + guidance
        data.VERIFY_SYSTEM += LEAD_VERIFY + POLICY
        _check_budget(name, len(specs), rates[0])
        # per_request=2 puts both twins of one family, which are adjacent, in one request.
        data.generate(name, "train", len(specs), batch_chunk=200, model="claude-sonnet-5-5", per_request=2,
                      thinking={"type": "adaptive"}, effort="medium", max_tokens=8000)
        checked = sum(not r["reject"] for r in read_jsonl(ART / "pairs" / (name + ".jsonl")))
        _check_budget("ver-" + name, checked, rates[1])
        data.verify(name)
    finally:
        data.GEN_SYSTEM, data.VERIFY_SYSTEM = old_gen, old_verify
        data.Wave = old_wave
    meta = {s["family_id"]: s for s in specs}
    for kind in ("pairs", "accepted"):
        dest = ART / kind / (name + ".jsonl")
        rows = read_jsonl(dest)
        for row in rows:
            row.update(contrast_group_id=meta[row["family_id"]]["contrast_group_id"], focus=meta[row["family_id"]]["focus"])
        write_jsonl(dest, rows)


def generate() -> None:
    _wave(NAME, plan(NAME), _rates(REFERENCE))


def retry() -> None:
    """Regenerate, with fresh wording, every family the first wave did not carry through every filter."""
    from .assemble import capture
    from .consolidate import _held_out_texts
    _, kept = funnel(_load(NAME), _held_out_texts(), capture)
    missing = [s for s in plan(RETRY) if s["contrast_group_id"] not in kept]
    if not missing:
        print("nothing to retry")
        return
    _wave(RETRY, missing, _rates(NAME), RETRY_GUIDANCE)


# ---------------------------------------------------------------- selection

STAGES = ("generation", "verification", "held_out", "minimal_target", "twin", "capture", "final")


def _load(name):
    """A wave's plan, returned and accepted rows, verdicts and the request status behind each planned row."""
    statuses = {}
    outcomes = read_json(ART / "claude" / name / "outcomes.json", {})
    for rid, params in read_json(ART / "claude" / name / "requests.json", {}).items():
        for spec in json.loads(params["messages"][0]["content"].split("\n", 1)[1]):
            statuses[spec["family_id"]] = outcomes.get(rid, {}).get("status", "pending")
    return {"name": name, "specs": read_json(ART / "claude" / name / "specs.json", []),
            "returned": read_jsonl(ART / "pairs" / (name + ".jsonl")),
            "accepted": {r["family_id"]: r for r in read_jsonl(ART / "accepted" / (name + ".jsonl"))},
            "verdicts": read_json(ART / "claude" / ("ver-" + name) / "verdicts.json", {}), "statuses": statuses}


def funnel(wave, held_out, capture):
    """Per-row records for one wave, and the rows of each family whose twins pass every stage.

    A family stops at the first stage either twin fails; the twin that passed it is recorded
    as dropped with its sibling. The engine capture keeps only oracle-exact targets.
    """
    from .consolidate import _vocabulary
    returned = {r["family_id"]: r for r in wave["returned"]}
    families = collections.defaultdict(list)
    for spec in wave["specs"]:
        families[spec["contrast_group_id"]].append(spec)
    records, kept = [], {}
    for gid, specs in families.items():
        rows = [returned.get(s["family_id"]) for s in specs]
        fail = {}
        for spec, row in zip(specs, rows):
            if row is None:
                fail[spec["family_id"]] = "not_returned:" + wave["statuses"].get(spec["family_id"], "unsubmitted")
            elif row["reject"]:
                fail[spec["family_id"]] = "structural:" + ",".join(row["reject"])
        verdicts = {s["family_id"]: wave["verdicts"].get(s["family_id"] + "-base") for s in specs}
        stage = "generation"
        if not fail:
            stage = "verification"
            for spec in specs:
                v = verdicts[spec["family_id"]] or {"verdict": "UNVERIFIED", "reasons": ["not_checked"]}
                if v["verdict"] != "PASS" or spec["family_id"] not in wave["accepted"]:
                    fail[spec["family_id"]] = f"verifier_{v['verdict']}:" + ",".join(v.get("reasons") or [])
            # Accepted rows carry the verification the TRAIN schema keeps.
            rows = [wave["accepted"].get(s["family_id"]) for s in specs]
        if not fail:
            stage = "held_out"
            for row in rows:
                if any(" ".join(row[f].casefold().split()) in held_out for f in ("model_input", "target")):
                    fail[row["family_id"]] = "shares_text_with_development_or_final"
        if not fail:
            stage = "minimal_target"
            for row in rows:
                normalized, changes, exclusion = minimal_target(row["model_input"], row["target"], _vocabulary(row))
                if exclusion or changes or normalized != row["target"]:
                    fail[row["family_id"]] = "minimal_target:" + (exclusion or ",".join(changes) or "rebuilt_differs")
        if not fail:
            stage = "twin"
            reason = twin_check(specs[0]["focus"], specs[0]["mentions_steps_or_list"], *rows)
            if reason:
                fail = {row["family_id"]: "twin:" + reason for row in rows}
        oracle = {}
        if not fail:
            stage = "capture"
            for row in rows:
                try:
                    capture(row)
                except (ValueError, RuntimeError) as exc:
                    fail[row["family_id"]] = "capture_error:" + str(exc)
                    continue
                oracle[row["family_id"]] = row["engine_oracle"]["exact"]
                if not oracle[row["family_id"]]:
                    fail[row["family_id"]] = "oracle_not_exact:" + str(row["engine_oracle"].get("fallback_reason"))
        for spec in specs:
            fid = spec["family_id"]
            records.append({"case_id": fid + "-base", "family_id": fid, "contrast_group_id": gid,
                            "focus": spec["focus"], "twin": spec["twin"], "wave": wave["name"],
                            "verdict": (verdicts[fid] or {}).get("verdict"), "oracle_exact": oracle.get(fid),
                            "stage": stage if fail else "final", "kept": not fail,
                            "reason": fail.get(fid, "sibling_dropped:" + stage) if fail else "kept"})
        if not fail:
            kept[gid] = rows
    return records, kept


def counts(records) -> dict:
    """Rows reaching each stage, by family type and twin side and in total."""
    groups = collections.defaultdict(list)
    for r in records:
        groups[r["focus"] + "/" + r["twin"]].append(r)
        groups["all"].append(r)
    passed = lambda rs, stage: sum(STAGES.index(r["stage"]) > STAGES.index(stage) for r in rs)
    return {g: {"planned": len(rs),
                "returned": sum(not r["reason"].startswith("not_returned") for r in rs),
                "structurally_valid": sum(not r["reason"].startswith(("not_returned", "structural")) for r in rs),
                "verifier_pass": sum(r["verdict"] == "PASS" for r in rs),
                "both_twins_pass": passed(rs, "verification"), "held_out": passed(rs, "held_out"),
                "minimal_target": passed(rs, "minimal_target"), "twin": passed(rs, "twin"),
                "oracle_exact": sum(bool(r["oracle_exact"]) for r in rs), "final": sum(r["kept"] for r in rs)}
            for g, rs in sorted(groups.items())}


def assemble(held_out=None, capture=None) -> dict:
    """Keep families whose twins pass every filter, the first wave to deliver a family winning."""
    from .refinement import SOURCE_FILES
    if held_out is None:
        from .consolidate import _held_out_texts
        held_out = _held_out_texts()
    if capture is None:
        from .assemble import capture
    dest = ART / "contrast" / "train.jsonl"
    if dest.exists():
        return {"already_assembled": len(read_jsonl(dest))}
    hashes = {p: file_sha256(ROOT / p) for p in SOURCE_FILES}
    rows, records, by_wave, chosen = [], [], {}, {}
    for name in WAVES:
        if not (ART / "claude" / name / "specs.json").exists():
            continue
        wave_records, kept = funnel(_load(name), held_out, capture)
        records += wave_records
        by_wave[name] = counts(wave_records)
        for gid, pair in kept.items():
            if gid not in chosen:
                chosen[gid] = name
                rows += pair
    if any(file_sha256(ROOT / p) != digest for p, digest in hashes.items()):
        raise RuntimeError("Engine source changed during capture")
    for row in rows:
        row.pop("engine_oracle", None)
        row.update(origin="contrast", split="train")
    for r in records:
        r["selected"] = r["kept"] and chosen.get(r["contrast_group_id"]) == r["wave"]
    final = collections.Counter(r["focus"] + "/" + r["twin"] for r in records if r["selected"])
    write_jsonl(dest, rows)
    receipt = {"created": utc_now(), "accepted": len(rows), "families": len(chosen), "sha256": file_sha256(dest),
               "final": dict(sorted(final.items()), all=sum(final.values())), "by_wave": by_wave,
               "spend_usd": spend(), "capture_source_hashes": hashes,
               "held_out_check": "exact text overlap with consolidate._held_out_texts (development and final)",
               "records": records}
    write_json(ART / "contrast" / "train.selection.json", receipt)
    return {k: v for k, v in receipt.items() if k != "records"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["plan", "generate", "retry", "assemble", "spend"])
    stage = p.parse_args().stage
    if stage == "plan":
        specs = plan()
        print(json.dumps({"rows": len(specs), "families": len({s["contrast_group_id"] for s in specs}),
                          "category": dict(collections.Counter(s["category"] for s in specs)),
                          "mentions": dict(collections.Counter(f"{s['category']}:{s['mentions_steps_or_list']}"
                                                               for s in specs if s["twin"] == "prose"))}))
    elif stage == "spend":
        print(json.dumps(spend()))
    else:
        result = {"generate": generate, "retry": retry, "assemble": assemble}[stage]()
        print(json.dumps(result))
