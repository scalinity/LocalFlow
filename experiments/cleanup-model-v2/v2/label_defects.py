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
LIST_TARGET = re.compile(r"(^|\n)[ \t]*(\d+[.)]|[-•*])[ \t]")


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
    a = [t[2] for t in _tokens(remove_spans(source, offsets))]
    b = [t[2] for t in _tokens(target)]
    vocabulary = _vocabulary_words(vocabulary_pairs, b)
    out = []
    for tag, i1, i2, j1, j2 in _edits(a, b):
        if tag == "delete" and _benign_deletion(a, i1, i2):
            continue
        if tag in ("delete", "replace") and all(w in vocabulary or _filler(w) for w in a[i1:i2]):
            continue
        out.append((tag, a[i1:i2], b[j1:j2]))
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
    listy = LIST_TARGET.search(target) is not None
    dropped = []
    for tag, removed, _added in _word_edits(source, target, offsets, vocabulary_pairs):
        rest = [w for w in removed if not _filler(w)]
        if tag != "delete" or (listy and all(w in LIST_WORDS or w.isdigit() for w in rest)) \
                or all(w in SPOKEN_PUNCTUATION for w in rest):
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
        if (not re.fullmatch(r"\s*[.!?]\s+", pre[a[i][1]:a[i + 1][0]])
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
    runs = [" ".join(removed) for tag, removed, added in _word_edits(source, target, offsets, vocabulary_pairs)
            if tag == "replace" and added and all(w.isdigit() for w in added)
            and set(removed) <= SEQUENCE_WORDS and set(removed) & {"then", "after", "next"}]
    return {"reason": "sequence_words_made_numbers", "runs": runs} if runs else None


RULES = (gold_deletion_kept_by_target, drops_dictated_word, loses_sentence_boundary,
         sequence_words_made_numbers)


def label_defect(source, target, offsets, vocabulary_pairs=()):
    """The first rule the label breaks, or None."""
    for rule in RULES:
        hit = rule(source, target, offsets, vocabulary_pairs)
        if hit:
            return hit
    return None

