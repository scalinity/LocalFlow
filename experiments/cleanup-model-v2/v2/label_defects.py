"""TRAIN labels whose target does not say what the speaker dictated.

Every rule is a pure function of one row's source, target, gold correction
offsets and vocabulary pairs. The comparison base is the label's pre-cleanup
text: the source with every gold span removed. Edits the policy permits are
never defects: filler deletion, stutter or restart repeats (a deleted run equal
to the run beside it), list numbering and list words in a list target, spoken
punctuation and vocabulary repairs.
"""
from __future__ import annotations

import difflib
import re

from .policy_score import (ABBREVIATIONS, I_FORMS, LIST_LINE, MONTHS, NUMBERED_LINE, STEP_LABELS, SUBJECT_PRONOUNS,
                           WEEKDAYS, _aligned_gaps, _marks, _pieces, _split)
from .strict_score import FILLERS

WORD = re.compile(r"\w+(?:['’]\w+)*")
STRETCHED_FILLER = re.compile(r"u+m+|u+h+|e+r+m+|e+h+m+|h+m+|m+h+m+")
MARKERS = re.compile(r"\b(sorry|i mean|actually|no wait|wait|make that|scratch that|rather|let me rephrase|"
                     r"i should say|keep it as|correction|that's not right)\b")
CONJUNCTIONS = {"and", "so", "because", "but", "or", "then", "also"}
# Words a list conversion removes in exact rows ("step 1 ..." -> "1. ...").
LIST_WORDS = {"step", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
              "ninth", "tenth", "firstly", "secondly", "thirdly", "finally", "next", "then", "last",
              "lastly", "and", "number", "item", "one", "two", "three", "four", "five", "six",
              "seven", "eight", "nine", "ten"}
SPOKEN_PUNCTUATION = {"slash", "dot", "dash", "hyphen", "underscore", "colon", "comma", "period",
                      "semicolon", "backslash", "hash", "asterisk", "plus", "minus", "equals", "pipe",
                      "tilde", "quote", "unquote", "bracket", "paren", "bullet", "ampersand"}
SEQUENCE_WORDS = {"then", "after", "that", "next", "finally", "lastly", "and"}


def _filler(word):
    return word in FILLERS or STRETCHED_FILLER.fullmatch(word) is not None


def _tokens(text):
    return [(m.start(), m.end(), m.group().casefold().replace("’", "'")) for m in WORD.finditer(text)]


def remove_spans(text, spans):
    """Text with the spans deleted, spaced as the engine applies corrections."""
    for start, end in sorted((tuple(s) for s in spans), reverse=True):
        text = text[:start] + text[end:]
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _edits(a, b):
    return [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]


def _benign_deletion(words, i1, i2):
    """Fillers, or a run (fillers aside, stutters collapsed) that repeats the run beside it."""
    rest = [w for w in words[i1:i2] if not _filler(w)]
    rest = [w for k, w in enumerate(rest) if k == 0 or rest[k - 1] != w]
    if not rest:
        return True
    k, n = len(rest), i2 - i1
    return ((i1 >= k and words[i1 - k:i1] == rest) or words[i2:i2 + k] == rest
            or (i1 >= n and words[i1 - n:i1] == words[i1:i2]))


def _vocabulary_words(vocabulary_pairs, target_words):
    """Spoken words of every vocabulary pair whose canonical form the target uses."""
    joined = " " + " ".join(target_words) + " "
    out = set()
    for pair in vocabulary_pairs or []:
        if len(pair) < 2:
            continue
        canonical = " ".join(t[2] for t in _tokens(pair[1]))
        if canonical and " " + canonical + " " in joined:
            out |= {t[2] for t in _tokens(pair[0])}
    return out


def _word_edits(source, target, offsets, vocabulary_pairs):
    """The word edits from the pre-cleanup text to the target that no deletion rule
    permits, as (tag, removed, added, the two pre-cleanup words before the edit)."""
    a = [t[2] for t in _tokens(remove_spans(source, offsets))]
    b = [t[2] for t in _tokens(target)]
    vocabulary = _vocabulary_words(vocabulary_pairs, b)
    out = []
    for tag, i1, i2, j1, j2 in _edits(a, b):
        if tag == "delete" and _benign_deletion(a, i1, i2):
            continue
        if tag in ("delete", "replace") and all(w in vocabulary or _filler(w) for w in a[i1:i2]):
            continue
        out.append((tag, a[i1:i2], b[j1:j2], a[max(0, i1 - 2):i1]))
    return out


def gold_deletion_kept_by_target(source, target, offsets, vocabulary_pairs=()):
    """At the place a gold span is removed, the target keeps a run of that span's
    own words: a leading frame word ('on' of 'on Tuesday, no' when the target
    reads 'on Wednesday', 'not' of 'not in the lexer, sorry'), or the repair
    when the gold line runs past its marker ('Tuesday, no Wednesday'). The
    corrections target then deletes words the cleanup target keeps. Quantity
    detail retention ('4 liters of dye, no wait, 6 liters' -> '6 liters of dye')
    keeps its words after the repair, not at the span, and is not matched."""
    if not offsets:
        return None
    src = _tokens(source)
    in_gold = [any(s <= a0 and a1 <= e for s, e in offsets) for a0, a1, _w in src]
    kept = [k for k in range(len(src)) if not in_gold[k]]
    a = [src[k][2] for k in kept]
    b = [t[2] for t in _tokens(target)]
    numbering = {m.group(2) for m in re.finditer(r"(^|\n)[ \t]*(\d+)[.)][ \t]", target)}
    runs = []
    for tag, i1, i2, j1, j2 in _edits(a, b):
        if tag not in ("insert", "replace"):
            continue
        lo = kept[i1 - 1] + 1 if i1 > 0 else 0
        hi = kept[i2] if i2 < len(kept) else len(src)
        gold = [src[k][2] for k in range(lo, hi) if in_gold[k]]
        words = [w for w in b[j1:j2] if w in gold and w not in numbering]
        n = len(words)
        if n and any(gold[k:k + n] == words for k in range(len(gold) - n + 1)):
            runs.append({"kept": " ".join(words), "gold": " ".join(gold)})
    return {"reason": "gold_deletion_kept_by_target", "runs": runs} if runs else None


def drops_dictated_word(source, target, offsets, vocabulary_pairs=()):
    """The target deletes a word of the pre-cleanup text that no permitted edit
    explains. With a correction marker in the run, the label applied a
    correction no gold line lists."""
    listy = LIST_LINE.search(target) is not None
    dropped = []
    for tag, removed, _added, before in _word_edits(source, target, offsets, vocabulary_pairs):
        rest = [w for w in removed if not _filler(w)]
        # "step 1 is clean the filter" -> "1. Clean the filter": the verb goes with the spoken label.
        label_verb = listy and rest in (["is"], ["is", "to"]) and len(before) == 2 and before[0] == "step"
        if tag != "delete" or (listy and all(w in LIST_WORDS or w.isdigit() for w in rest)) \
                or all(w in SPOKEN_PUNCTUATION for w in rest) or label_verb:
            continue
        text = " ".join(removed)
        kind = ("unlisted_correction" if MARKERS.search(text) else
                "conjunction_at_split" if all(w in CONJUNCTIONS for w in rest) else
                "list_conversion_drops_words" if listy else "other_word")
        dropped.append({"kind": kind, "words": text})
    return {"reason": "drops_dictated_word", "dropped": dropped} if dropped else None


def loses_sentence_boundary(source, target, offsets, vocabulary_pairs=()):
    """A '. ', '? ' or '! ' boundary before a capitalised word of the pre-cleanup
    text leaves only spaces in the target and the next word still capitalised:
    a run-on the speaker did not dictate ('without warnings Does anyone object').
    A comma merge is not matched."""
    pre = remove_spans(source, offsets)
    a, b = _tokens(pre), _tokens(target)
    matched = {}
    for block in difflib.SequenceMatcher(None, [t[2] for t in a], [t[2] for t in b],
                                         autojunk=False).get_matching_blocks():
        for k in range(block.size):
            matched[block.a + k] = block.b + k
    hits = []
    for i in range(len(a) - 1):
        gap = pre[a[i][1]:a[i + 1][0]]
        # The period of "Dr. Patel" or "St. Louis" ends no sentence.
        if (not re.fullmatch(r"\s*[.!?]\s+", gap) or (gap.lstrip().startswith(".") and a[i][2] in ABBREVIATIONS)
                or i not in matched or matched.get(i + 1) != matched[i] + 1):
            continue
        j = matched[i]
        if pre[a[i + 1][0]].isupper() and target[b[j + 1][0]].isupper() \
                and not target[b[j][1]:b[j + 1][0]].strip(" \t"):
            hits.append(target[max(0, b[j][1] - 25):b[j + 1][1] + 15])
    return {"reason": "loses_sentence_boundary", "at": hits} if hits else None


def sequence_words_made_numbers(source, target, offsets, vocabulary_pairs=()):
    """A list target replaces spoken sequence words ('then', 'after that',
    'next') with list numbers. Ordinals and 'step' are the conversions exact
    rows use; no exact row numbers a 'then', and the engine vetoes every one."""
    runs = [" ".join(removed) for tag, removed, added, _before in _word_edits(source, target, offsets, vocabulary_pairs)
            if tag == "replace" and added and all(w.isdigit() for w in added)
            and set(removed) <= SEQUENCE_WORDS and set(removed) & {"then", "after", "next"}]
    return {"reason": "sequence_words_made_numbers", "runs": runs} if runs else None


def gold_line_not_marker_terminated(source, target, offsets, vocabulary_pairs=()):
    """A gold line the corrections parser never admits: stripped as the parser strips
    a proposed line, it does not end with a correction marker. It stops at a filler
    ('12 score sheets, uh'), runs into the replacement ('Tuesday, no Wednesday') or
    keeps sentence punctuation after the marker ('on Monday. Sorry.'). Every
    corrections call of such a row would teach a line the parser rejects; a marker
    the engine later adds stops the rule firing."""
    from localflow.v2.cleanup.engine import SPAN_ENDS_WITH_MARKER_RE
    lines = [source[s:e] for s, e in offsets or []]
    bad = [line for line in lines if not SPAN_ENDS_WITH_MARKER_RE.search(line.strip().strip('"').strip())]
    return {"reason": "gold_line_not_marker_terminated", "lines": bad} if bad else None


# Direct questions, after the model-gap lane's detector: a sentence-initial auxiliary and
# subject, a wh-word and auxiliary, or a tail such as ", should we". It is heuristic, so a
# question rule excludes a row and never relabels it.
AUX = (r"(?:can|could|would|will|should|shall|do|does|did|is|are|was|were|has|have|had|may|might|am|isn't|"
       r"aren't|wasn't|weren't|doesn't|didn't|can't|couldn't|wouldn't|won't|shouldn't|haven't|hasn't)")
SUBJECT = (r"(?:you|we|i|they|he|she|it|there|the|this|that|these|those|a|an|anyone|someone|everyone|anybody|"
           r"somebody|our|your|my|their|his|her|its|any|all|each|every)")
LEAD = (r"(?:(?:and|also|so|okay|ok|but|or|then|now|well|oh|hey|right|alright|first|second|third|finally|"
        r"quick question|one more thing)[,:]?\s+)*")
PHRASE = r"(?:(?:for|in|on|about|with|regarding|after|before|during)\s[^,?.]{1,70},\s*)"
# A subject between a wh-word and its verb makes a clause, not a question: "when everything is done, post it".
PRONOUN = (r"(?:i|we|you|they|he|she|it|there|the|a|an|this|that|these|those|my|our|your|their|everything|everyone|"
           r"everybody|anything|anyone|anybody|something|someone|somebody|nothing|nobody)")
SUBJECT_PRONOUN = "(?:" + "|".join(sorted(SUBJECT_PRONOUNS)) + ")"
WH = r"(?:who|what|which|why|when|where|how)"
QUESTIONS = [
    re.compile(rf"^{LEAD}{PHRASE}?{AUX}\s+{SUBJECT}\b", re.I),
    re.compile(rf"^{LEAD}(?:{WH}|whose)\b(?:\s+(?:of\s+(?:the|these|those)\s+)?(?!{PRONOUN}\b)[\w'-]+){{0,2}}\s+{AUX}\b", re.I),
    re.compile(rf"^{LEAD}{PHRASE}{WH}\b(?:\s+(?!{PRONOUN}\b)[\w'-]+){{0,2}}\s+{AUX}\s+{SUBJECT_PRONOUN}\b", re.I),
    re.compile(rf",\s+(?:and\s+|or\s+)?{AUX}\s+(?:you|we|i|they|it|there|anyone)\b", re.I),
    re.compile(rf",\s+(?:and\s+|or\s+)?{WH}\b(?:\s+(?!{PRONOUN}\b)[\w'-]+){{0,2}}\s+{AUX}\s+{SUBJECT_PRONOUN}\b", re.I),
]
IMPERATIVE = re.compile(rf"^\W*{LEAD}{PHRASE}?(?:do not|don't|please|have the|have them|have someone|have a|have each|"
                        r"have every)\b", re.I)
# A singular subject takes "does" and "has", so these never ask: "do this first", ", and have it log the rows".
NEVER_QUESTION = re.compile(r"\b(?:do\s+(?:it|this|that)|have\s+it)\b", re.I)
BECAUSE_CLAUSE = re.compile(r"\bbecause\b(?!\s+of\b)", re.I)
# An alternative after the clause makes the cause what the question asks: "…because A or because B?"
CAUSE_ALTERNATIVE = re.compile(r"\bor\s+(?:because|is|was|did|does)\b", re.I)
NUMBER_WORDS = {w: n for n, w in enumerate("one two three four five six seven eight nine ten".split(), 1)}


def is_direct_question(sentence):
    """Whether a sentence reads as a direct question or a "Can/Could/Would/Will you" request."""
    sentence = sentence.strip().strip('"“”')
    probe = NEVER_QUESTION.sub("x", sentence)
    return not IMPERATIVE.search(sentence) and any(q.search(probe) for q in QUESTIONS)


def _sentences(text):
    """Each sentence of text with the marks of the gap that ends it and that gap's index. A
    sentence ends at a line break or where . ! ? closes a word and whitespace follows, but
    not at an abbreviation's period ("Dr. Okonkwo"), before a lower-case word ("8 a.m. or
    at noon") or at a dot standing apart from the word before it ("./build.sh", "-e . in")."""
    words, gaps = _pieces(text)
    out, start = [], 0
    for k in range(1, len(words) + 1):
        gap = gaps[k]
        if k == len(words) or "\n" in gap or (
                re.match(r"[^\w\s]*[.!?][^\w\s]*\s", gap) and not words[k][:1].islower()
                and not (gap.startswith(".") and words[k - 1].casefold() in ABBREVIATIONS)):
            if start < k:
                out.append(("".join(words[i] + (gaps[i + 1] if i < k - 1 else "") for i in range(start, k)),
                            _marks(gap), k))
            start = k
    return out


def question_keeps_period(source, target, offsets, vocabulary_pairs=()):
    """A direct question or a "Can/Could/Would/Will you" request the target ends with a
    period. The prompt asks for question punctuation and every development label ends such
    a sentence with "?"; a label keeping the dictation's period teaches the opposite. A no-op
    label decided nothing and is never excluded: it teaches leaving readable text alone."""
    if target == source:
        return None
    hits = [s for s, end, _k in _sentences(target) if "." in end and "?" not in end and is_direct_question(s)]
    return {"reason": "question_keeps_period", "sentences": hits} if hits else None


def question_keeps_because_clause(source, target, offsets, vocabulary_pairs=()):
    """A direct question that keeps a because-clause after it in the same sentence ("did it
    pass, because I think the cache is stale?"). Development labels end the question and
    start the clause anew ("Did it pass? Because I think the cache is stale."). A clause
    before the question ("I ask because the log is empty, and could you") and a cause the
    question asks about ("did it fail because A or because B") are not matched. Only what the
    label decided counts: never a no-op label, and never a "?" the source already had."""
    if target == source:
        return None
    source_words, source_gaps = _split(source)
    aligned = _aligned_gaps(source_words, _split(target)[0])
    copied = lambda end, k: "?" in end and k in aligned and "?" in _marks(source_gaps[aligned[k]])
    hits = [s for s, end, k in _sentences(target)
            if (m := BECAUSE_CLAUSE.search(s, 1)) and is_direct_question(s[:m.start()])
            and not CAUSE_ALTERNATIVE.search(s, m.end()) and not copied(end, k)]
    return {"reason": "question_keeps_because_clause", "sentences": hits} if hits else None


def step_labels_kept_as_prose(source, target, offsets, vocabulary_pairs=()):
    """Two or more consecutive spoken step labels ("step 1 ... step 2", "step one ... step
    two") that the target keeps as prose. The prompt makes such steps a numbered list; "the
    next step is" and "a step back" carry no number and are not step labels. A no-op label
    decided nothing and is never excluded."""
    if target == source or NUMBERED_LINE.search(target):
        return None
    numbers = [int(m.group(1)) if m.group(1).isdigit() else NUMBER_WORDS[m.group(1).casefold()]
               for m in STEP_LABELS.finditer(source)]
    runs = [(a, b) for a, b in zip(numbers, numbers[1:]) if b == a + 1]
    return {"reason": "step_labels_kept_as_prose", "labels": runs} if runs else None


RULES = (gold_deletion_kept_by_target, drops_dictated_word, loses_sentence_boundary,
         sequence_words_made_numbers, gold_line_not_marker_terminated, step_labels_kept_as_prose,
         question_keeps_period, question_keeps_because_clause)


def label_defect(source, target, offsets, vocabulary_pairs=()):
    """The first rule the label breaks, or None."""
    for rule in RULES:
        hit = rule(source, target, offsets, vocabulary_pairs)
        if hit:
            return hit
    return None


def unexplained_rewrites(before, after, vocabulary_pairs=()):
    """Word replacements and insertions from before to after that no permitted conversion
    explains. A written word is explained when it carries a digit (a spoken number or list
    number written out), is part of a vocabulary pair's canonical form, or joins or splits
    the words it replaces ("data frame" -> "dataframe"); a number changed into another
    number never is."""
    a, b = [t[2] for t in _tokens(before)], [t[2] for t in _tokens(after)]
    canonical = {t[2] for pair in vocabulary_pairs or [] if len(pair) > 1 for t in _tokens(pair[1])}
    digit = lambda word: any(ch.isdigit() for ch in word)
    out = []
    for tag, i1, i2, j1, j2 in _edits(a, b):
        removed, added = a[i1:i2], b[j1:j2]
        if tag == "delete" or "".join(removed) == "".join(added):
            continue
        changed_number = bool(removed) and all(digit(w) for w in removed + added)
        if changed_number or not all(digit(w) or w in canonical for w in added):
            out.append((" ".join(removed), " ".join(added)))
    return out


# Words that keep their capital wherever they stand.
ALWAYS_CAPITALISED = I_FORMS | WEEKDAYS | MONTHS


def _keeps_capital(word, text):
    """Whether a word text capitalises at a sentence start is capitalised for itself: "I", a
    day or month, a word with an inner capital ("GitHub"), or one text also capitalises
    mid-sentence (a name)."""
    if word.casefold().replace("’", "'") in ALWAYS_CAPITALISED or (len(word) > 1 and not word[1:].islower()):
        return True
    for m in re.finditer(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text):
        before = text[:m.start()].rstrip(" \t")
        if before and before[-1] not in ".!?:\n\"'”’":
            return True
    return False


def restore_split_conjunctions(source, target, offsets, vocabulary_pairs=()):
    """Where the target starts a new sentence exactly where the pre-cleanup text
    had a run of conjunctions it dropped ('cold room and before' -> 'cold room.
    Before'), put the dictated run back after the boundary, capitalised, and
    give the next word its pre-cleanup case unless it is capitalised for itself
    ("I", a name, a day). Returns the restored target, or
    None when there is no such drop or another dropped word would remain. A
    list target is never restored: its dropped 'and' is a list conversion, and
    neither is a stuttered run."""
    if LIST_LINE.search(target):
        return None
    pre = remove_spans(source, offsets)
    a, b = _tokens(pre), _tokens(target)
    aw, bw = [t[2] for t in a], [t[2] for t in b]
    inserts = []
    for tag, i1, i2, j1, _j2 in _edits(aw, bw):
        dropped = aw[i1:i2]
        # A stuttered run ("and and", "and then and then") has no single dictated form to restore.
        if tag != "delete" or _benign_deletion(aw, i1, i2) or not all(w in CONJUNCTIONS for w in dropped) \
                or len(set(dropped)) < len(dropped):
            continue
        if not 0 < j1 < len(b) or not re.fullmatch(r"[.!?]\s+", target[b[j1 - 1][1]:b[j1][0]]):
            continue
        run = pre[a[i1][0]:a[i2 - 1][1]]
        following = pre[a[i2][0]:a[i2][1]] if i2 < len(a) else ""
        inserts.append((b[j1][0], run[:1].upper() + run[1:], following))
    if not inserts:
        return None
    out = target
    for position, run, following in sorted(inserts, reverse=True):
        rest = out[position:]
        word = WORD.match(rest)
        if following[:1].islower() and word and not _keeps_capital(word.group(), target):
            rest = rest[:1].lower() + rest[1:]
        out = out[:position] + run + " " + rest
    return None if drops_dictated_word(source, out, offsets, vocabulary_pairs) else out
