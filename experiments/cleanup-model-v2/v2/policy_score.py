"""Punctuation and layout policy checks, separate from exact reference matching.

Repairs may need a boundary or accept an optional comma, but a label's optional
polish is not required, and an output must not add, remove or replace
punctuation the label kept. Paragraph breaks come only from spoken commands, so
a blank line the source lacks is counted as invented formatting. Every model is
scored identically against the same source and label.
"""
from __future__ import annotations

import collections
import difflib
import re

WORD = re.compile(r"\w+(?:['’]\w+)*")
BOUNDARY = set(".!?;:")
FIELDS = ("invented_breaks", "extra_format_edits")


def _split(text):
    """Casefolded words and the n + 1 gaps around them (leading and trailing included)."""
    matches = list(WORD.finditer(text))
    words = [m.group().casefold().replace("’", "'") for m in matches]
    bounds = [0] + [x for m in matches for x in (m.start(), m.end())] + [len(text)]
    return words, [text[bounds[i]:bounds[i + 1]] for i in range(0, len(bounds), 2)]


def _marks(gap):
    return "".join(re.findall(r"[^\w\s]", gap))


def _blank_line(gap):
    return re.search(r"\n\s*\n", gap) is not None


def _aligned_gaps(a_words, b_words):
    """Map each b gap to the a gap between the same two consecutive matched words."""
    matched = {}
    for block in difflib.SequenceMatcher(None, a_words, b_words, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            matched[block.b + k] = block.a + k
    gaps = {0: 0, len(b_words): len(a_words)}
    for k in range(1, len(b_words)):
        j = matched.get(k - 1)
        if j is not None and matched.get(k) == j + 1:
            gaps[k] = j + 1
    return gaps


def _gap_ok(s, t, o):
    ps, pt, po = _marks(s), _marks(t), _marks(o)
    if pt == ps:
        return po == ps
    if not ps and set(pt) == {","}:
        return po in ("", ",")
    if not ps and (set(pt) & BOUNDARY or ("\n" in t and "\n" not in s)):
        return bool(po) or "\n" in o
    return po in (ps, pt)


def score(case, text):
    is_noop = case.get("is_noop")
    if text is None:
        return {"words_ok": False, "policy_repair": None if is_noop else False,
                "invented_breaks": None, "extra_format_edits": None}
    source_words, source_gaps = _split(case["model_input"])
    target_words, target_gaps = _split(case["target"])
    output_words, output_gaps = _split(text)
    target_to_source = _aligned_gaps(source_words, target_words)
    words_ok = output_words == target_words
    policy_ok = words_ok and all(
        ("?" in _marks(o)) == ("?" in _marks(t))
        and (k not in target_to_source or _gap_ok(source_gaps[target_to_source[k]], t, o))
        for k, (t, o) in enumerate(zip(target_gaps, output_gaps)))
    source_to_target = {j: k for k, j in target_to_source.items()}
    output_to_source = _aligned_gaps(source_words, output_words)
    invented = sum(_blank_line(output_gaps[k]) and not _blank_line(source_gaps[j])
                   for k, j in output_to_source.items())
    changed = sum(j in source_to_target
                  and _marks(source_gaps[j]) == _marks(target_gaps[source_to_target[j]])
                  and _marks(output_gaps[k]) != _marks(source_gaps[j])
                  for k, j in output_to_source.items())
    return {"words_ok": words_ok, "policy_repair": None if is_noop else policy_ok,
            "invented_breaks": invented, "extra_format_edits": invented + changed}


DISCOURSE = {"okay", "ok", "so", "alright", "well", "yeah", "yes", "right", "now", "also", "hi", "hey", "anyway"}
ORDINALS = re.compile(r"\b(first|firstly|one)\b[ ,].{3,200}?\b(second|secondly|two)\b[ ,]", re.I | re.S)
LIST_LINE = re.compile(r"(^|\n)[ \t]*(\d+\.|[-•*])[ \t]")
# A numbered list comes only from spoken step labels ("step 1 ... step 2"), never from ordinal words.
NUMBERED_LINE = re.compile(r"(^|\n)[ \t]*\d+\.[ \t]")
STEP_LABELS = re.compile(r"\bsteps?\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
SEQUENCE = re.compile(r"\b(first|firstly)\b.{3,400}?\b(then|next|third|finally|lastly)\b", re.I | re.S)
# An introduced list of distinct items takes bullets, never numbers.
ITEM_LIST_WORDS = re.compile(r"\b(list|lists|following|items)\b", re.I)


def _pieces(text):
    """Original word strings and the n + 1 gaps around them."""
    matches = list(WORD.finditer(text))
    bounds = [0] + [x for m in matches for x in (m.start(), m.end())] + [len(text)]
    return [m.group() for m in matches], [text[bounds[i]:bounds[i + 1]] for i in range(0, len(bounds), 2)]


# The prompt requires commas that set off a directly addressed person, so a revert keeps them.
GROUP_ADDRESSEES = {"everyone", "everybody", "all", "team", "guys", "folks", "sir", "madam", "ma'am", "class",
                    "people", "kids", "students", "friends", "ladies", "gentlemen", "y'all", "mom", "mum",
                    "dad", "honey"}
# April, May, June and August are also given names, so they may be addressed ("Thanks, June.").
NOT_PERSONS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january",
               "february", "march", "july", "september", "october", "november", "december"}
I_FORMS = {"i", "i'm", "i'll", "i've", "i'd"}
# Capitalised only because they open a sentence, these are never part of a name ("In June, we ship").
FUNCTION_WORDS = {"in", "on", "at", "by", "for", "from", "to", "with", "into", "onto", "over", "under", "after",
                  "before", "since", "until", "during", "about", "between", "the", "a", "an", "this", "that",
                  "these", "those", "my", "our", "your", "their", "his", "her", "its", "if", "when", "while",
                  "because", "and", "but", "or", "as", "of", "we", "you", "they", "he", "she", "it", "there",
                  "here", "what", "which", "who", "where", "why", "how"}
# A period after these ends no sentence: "Dr. Patel", "St. Louis".
ABBREVIATIONS = {"dr", "mr", "mrs", "ms", "st", "prof", "jr", "sr", "vs", "mt", "ft"}
TITLES = {"dr", "mr", "mrs", "ms", "prof"}
# Sentence openers that may precede a name ("Hey Marta,") but are never the one addressed ("First, run it").
OPENERS = DISCOURSE | {"hi", "hello", "dear", "thanks", "thank", "morning", "evening", "afternoon", "first",
                       "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
                       "next", "then", "last", "lastly", "finally", "however", "otherwise", "instead",
                       "meanwhile", "overall", "afterward", "afterwards", "honestly", "actually",
                       "importantly", "firmly", "still", "rather", "remember", "wait", "oh", "no", "please"}
# Words a greeting puts between its opener and the name: "Good morning Marta," "Thank you Marta,".
GREETING_WORDS = {"good", "there", "you", "me", "excuse", "welcome"}
# A sentence-initial name followed by one of these, in a sentence that neither asks nor says "you", is its subject.
FINITE = {"is", "was", "has", "had", "does", "did", "will", "would", "can", "could", "should", "must", "may",
          "might", "shall", "says", "said", "isn't", "wasn't", "hasn't", "doesn't", "didn't", "won't", "can't"}
# After a finite verb, a subject pronoun makes a question without its mark: "Marta, could we move it."
SUBJECT_PRONOUNS = {"i", "we", "you", "they", "he", "she", "it", "there"}


def _addressee(word):
    """A capitalised name (O'Brien and McKay too) or a group addressee; days, months, "I"
    and acronyms are not."""
    key = word.casefold().replace("’", "'")
    letters = word.replace("'", "").replace("’", "")
    return key in GROUP_ADDRESSEES or (word[:1].isupper() and letters.isalpha() and not letters.isupper()
                                       and key not in NOT_PERSONS | I_FORMS | FUNCTION_WORDS)


def _opens(words, gaps, i):
    """Whether word i opens the text or a sentence. Only a title's period ("Dr. Okafor")
    ends no sentence: "40 ms. Marta" and "Main St. Sam" start a new one."""
    if i == 0 or "\n" in gaps[i]:
        return True
    return re.search(r"[.!?][\"'”’)\]]*\s", gaps[i]) is not None and not (
        gaps[i].startswith(".") and words[i - 1].casefold() in TITLES and words[i - 1][:1].isupper())


def _sets_off_addressee(words, gaps, k):
    """Whether the comma in gap k sets off a person being addressed.

    Before the person: "Thanks, Marta." or "Can you check this, Sam?" (up to three
    name words, joined by spaces, hyphens or "and", that end the sentence or the
    clause, or are set off again mid-sentence). After the person: "Marta, can you
    send it", "Hi Marta, ...", "Good morning Marta, ...". A sentence-initial name
    followed by a finite verb is the subject and its comma is not kept, unless the
    sentence asks or says "you". Unsure cases count as addressed: a kept optional
    comma costs little, a stripped required one teaches the opposite of the prompt.
    """
    n = len(words)
    if not 0 < k < n:
        return False
    named = lambda i: _addressee(words[i]) and not _opens(words, gaps, i)
    # Word i continues the name before it: "Jean-Luc", "Marta Lopez", "Dr. Okafor".
    joined = lambda i: gaps[i].strip() in ("", "-") or (gaps[i].strip() == "." and words[i - 1].casefold() in TITLES)
    for m in range(k, min(k + 4, n)):
        if m > k and not joined(m):
            break
        if m > k and words[m].casefold() == "and" and m + 1 < n and _addressee(words[m + 1]):
            continue
        if not _addressee(words[m]):
            break
        after = gaps[m + 1]
        # A sentence end, colon, semicolon or line break after the name also closes the address.
        if m + 1 == n or re.search(r"[.!?:;\n]", after) or ("," in after and not named(k - 1)):
            return True
    p = k - 1
    if not _addressee(words[p]):
        return False
    while p >= 1 and k - p < 4 and joined(p):  # the name's earlier words: "Dr Patel," "Marta and Sam,"
        if words[p - 1].casefold() == "and" and p >= 2 and _addressee(words[p - 2]) and joined(p - 1):
            p -= 2
        elif words[p][:1].isupper() and _addressee(words[p - 1]) and words[p - 1].casefold() not in OPENERS:
            p -= 1
        else:
            break
    # A sentence-opening "And Marta," leaves the name sentence-initial, subject check and all.
    if _opens(words, gaps, p) or (p >= 1 and words[p - 1].casefold() in ("and", "but", "or")
                                  and _opens(words, gaps, p - 1)):
        if words[p].casefold() in OPENERS:
            return False
        end = next((i for i in range(k, n) if re.search(r"[.!?\n]", gaps[i + 1])), n - 1)
        sentence = {w.casefold() for w in words[k:end + 1]}
        verb = words[k].casefold().replace("’", "'")
        asks = ("?" in gaps[end + 1] or sentence & {"you", "your", "yours", "yourself"}
                or (verb in FINITE and k + 1 < n and words[k + 1].casefold() in SUBJECT_PRONOUNS))
        return bool(asks) or verb not in FINITE
    q = p - 1
    # The label's own comma after an opener ("Okay, so Priya,") does not end the walk.
    while q >= 0 and words[q].casefold() in OPENERS | GREETING_WORDS and _marks(gaps[q + 1]) in ("", ",") \
            and "\n" not in gaps[q + 1]:
        if _opens(words, gaps, q):
            return True  # after greetings or openers: "Hi Marta," "Okay, so Priya," "Good morning Marta,"
        q -= 1
    return "," in gaps[p] and p >= 1 and not named(p - 1)  # set off on both sides: "for you, Maren, about"


def minimal_target(source, target, vocabulary=(), keep=frozenset()):
    """Remove optional polish from a training label without touching its repairs.

    Returns (target, changes, exclusion). Invented paragraph breaks and a colon
    replacing a valid comma after a short label-like opening are reverted to the
    source. A comma the dictation lacked stays only when it separates items of a list
    of three or more, sets off an addressed person, prevents a likely misreading, or
    follows a date, place or number convention; every other added comma reverts. The
    revert applies at an aligned gap the source left unpunctuated on one line, where
    score() never requires the comma: after a sentence-opening discourse word it
    reverts (opening_discourse_comma) unless it is the only comma setting off an
    addressee ("Yes, Marta."), elsewhere it reverts (optional_gap_comma) unless keep
    holds the source gap's index or the comma sets off an addressed person. Commas the dictation already had are never touched. A label that turns
    spoken ordinals into a list without step labels or a list introduction, or into a
    numbered list without spoken step labels, that numbers an introduced list of items,
    or that adds a word the speaker did not say, is excluded rather than rewritten.
    """
    if LIST_LINE.search(target) and not LIST_LINE.search(source) and ORDINALS.search(source) \
            and not re.search(r"\b(step|steps|list)\b", source, re.I):
        return target, [], "ordinals_made_a_list"
    if NUMBERED_LINE.search(target) and not NUMBERED_LINE.search(source) and not STEP_LABELS.search(source) \
            and (ORDINALS.search(source) or SEQUENCE.search(source)):
        return target, [], "ordinals_made_a_numbered_list"
    # Excluded rather than converted to bullets: a spoken "number one" may make the number dictated.
    if NUMBERED_LINE.search(target) and not NUMBERED_LINE.search(source) and not STEP_LABELS.search(source) \
            and ITEM_LIST_WORDS.search(source):
        return target, [], "introduced_items_made_a_numbered_list"
    source_words, source_gaps = _split(source)
    target_words, _ = _split(target)
    allowed = {w.casefold() for v in vocabulary for w in WORD.findall(str(v))}
    extra = collections.Counter(target_words) - collections.Counter(source_words)
    added = sorted(w for w in extra if w not in allowed and not w.isdigit())
    if added:
        return target, [], "adds_undictated_words:" + ",".join(added[:5])
    from .label_defects import _keeps_capital
    words, gaps = _pieces(target)
    source_pieces = _pieces(source)[0]
    label_gaps = list(gaps)
    changes = []
    for k, j in _aligned_gaps(source_words, target_words).items():
        s, t = source_gaps[j], gaps[k]
        if _blank_line(t) and not _blank_line(s):
            t = re.sub(r"[ \t]*\n\s*\n\s*", " ", t)
            changes.append("invented_paragraph")
            # Without the paragraph the next word no longer opens a sentence ("Hi Marta,
            # please"): it takes the dictated case unless it is capitalised for itself.
            if k < len(words) and not re.search(r"[.!?:]", t) and source_pieces[j][:1].islower() \
                    and words[k][:1].isupper() and not _keeps_capital(words[k], target):
                words[k] = words[k][:1].lower() + words[k][1:]
        opens_sentence = k == 1 or (k >= 2 and re.search(r"[.!?\n]", label_gaps[k - 1]))
        if not _marks(s) and _marks(t) == ",":
            if k >= 1 and target_words[k - 1] in DISCOURSE and opens_sentence:
                end = k  # the addressee's last word: "Marta Lopez", "Jean-Luc"
                while end + 1 < len(words) and label_gaps[end + 1].strip() in ("", "-") and _addressee(words[end + 1]):
                    end += 1
                # "Okay Dana, these are" keeps the comma after the name; "Yes, Marta." has only this one.
                if not (_sets_off_addressee(words, label_gaps, k) and "," not in label_gaps[end + 1]):
                    t = t.replace(",", "", 1)
                    changes.append("opening_discourse_comma")
            # The label's own gap decides: a comma it gave a line break stays though the break reverted.
            elif "\n" not in s + label_gaps[k] and j not in keep and not _sets_off_addressee(words, label_gaps, k):
                # A comma between two touching words reverts to the source gap, keeping them two words.
                t = t.replace(",", "", 1) or s
                changes.append("optional_gap_comma")
        if _marks(s) == "," and _marks(t) == ":" and "\n" not in t:
            opening = 0
            for back in range(k - 1, -1, -1):
                opening += 1
                if back == 0 or re.search(r"[.!?\n]", gaps[back]):
                    break
            if opening <= 8:
                t = t.replace(":", ",", 1)
                changes.append("label_colon")
        gaps[k] = t
    return gaps[0] + "".join(w + g for w, g in zip(words, gaps[1:])), changes, None


def aggregate(cases, scores):
    """Format-edit totals and per-case means for no-ops, repairs and long sources."""
    scopes = {"noop": lambda c: c["is_noop"], "repair": lambda c: not c["is_noop"],
              "long_over_200": lambda c: len(c["model_input"].split()) > 200}
    out = {}
    for scope, member in scopes.items():
        rows = [s for c, s in zip(cases, scores) if member(c)]
        measured = [s for s in rows if s["invented_breaks"] is not None]
        out[scope] = {"n": len(rows), "unavailable": len(rows) - len(measured)}
        for field in FIELDS:
            total = sum(s[field] for s in measured)
            out[scope][field] = {"total": total, "per_case": total / len(measured) if measured else None}
    return out
