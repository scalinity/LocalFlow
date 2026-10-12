"""Deterministic metrics, paired family bootstrap and the frozen decision rules.

Damage is input-anchored: it counts changed facts, unauthorized omissions,
added content, changed negation and a lost ending relative to the model
input. A fallback that returns the input therefore has zero damage, and
fallback rate is reported as its own headline metric.
"""

from __future__ import annotations

import difflib
import math
import random
import re
from collections import Counter, defaultdict

from .audio import lexical
from .synth import NEGATIONS, words

FILLERS = {"um", "uh", "erm", "ehm", "hmm", "mhm"}
INTERJECTORS = {"oh", "well", "okay", "so"}
LIST_JOINERS = {"and", "or"}
FUNCTION = {"a", "an", "the", "to", "of", "in", "on", "at", "for", "and", "or", "but", "is", "it", "i", "we",
            "you", "he", "she", "they", "be", "with", "that", "this", "as", "by", "from", "my", "our", "your"}
NUM_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
NUM_WORDS.update({w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())})
QUESTIONY = {"question_or_request_as_content", "coding_agent_instruction", "quoted_instruction"}


def canon_numbers(ws: list[str]) -> list[str]:
    """Collapse spoken number words to digits so 'twenty five' == '25'."""
    out, i = [], 0
    while i < len(ws):
        w = ws[i]
        if w in NUM_WORDS:
            v = NUM_WORDS[w]
            if v >= 20 and i + 1 < len(ws) and ws[i + 1] in NUM_WORDS and NUM_WORDS[ws[i + 1]] < 10:
                v += NUM_WORDS[ws[i + 1]]
                i += 1
            out.append(str(v))
        else:
            out.append(w.replace(",", ""))
        i += 1
    return out


def canon_symbols(text: str) -> str:
    """Same quantity, different representation: "$120" == "120 dollars",
    "15%" == "15 percent"."""
    text = re.sub(r"\$\s?(\d[\d,]*(?:\.\d+)?)", r"\1 dollars", text or "")
    return re.sub(r"(\d)\s?%", r"\1 percent", text)


def lex(text: str) -> list[str]:
    return canon_numbers(words(canon_symbols(text)))


def remove_spans(text: str, offsets) -> str:
    out, last = [], 0
    for s, e in sorted(offsets):
        out.append(text[last:s])
        last = e
    out.append(text[last:])
    return " ".join("".join(out).split())


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]


def wer(hyp: list[str], ref: list[str]) -> tuple[int, int]:
    return edit_distance(hyp, ref), max(len(ref), 1)


def list_items(text: str) -> int:
    return len(re.findall(r"^\s*(?:[-*+] |\d+[.)] )", text or "", re.M))


def _gold_words(source: str, offsets: list) -> set[int]:
    """Indices of source words inside gold correction spans."""
    idx, pos = set(), 0
    for i, m in enumerate(re.finditer(r"[^\W_]+(?:['’][^\W_]+)*", source)):
        if any(s <= m.start() < e for s, e in offsets):
            idx.add(i)
    return idx


def alignment(source: str, out: str, *, gold_offsets=(), vocab_pairs=(), list_out=False) -> dict:
    """Word alignment of output against the model input, classifying every
    change as authorized or not."""
    src_raw = words(canon_symbols(source))
    src, dst = canon_numbers(src_raw), lex(out)
    if len(src) != len(src_raw):          # number collapse shifted indices: drop gold-span precision
        gold_idx = set()
    else:
        gold_idx = _gold_words(source, gold_offsets)
    vocab_alias = {w for a, _ in vocab_pairs for w in words(a)}
    vocab_canon = {w for _, c in vocab_pairs for w in words(c)}
    sm = difflib.SequenceMatcher(a=src, b=dst, autojunk=False)
    omitted, added, substituted, authorized_del = [], [], [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        dels = list(range(i1, i2)) if op in ("delete", "replace") else []
        ins = dst[j1:j2] if op in ("insert", "replace") else []
        for i in dels:
            w = src[i]
            prev = src[i - 1] if i else None
            ok = (w in FILLERS or i in gold_idx or (prev == w and w in FUNCTION | INTERJECTORS)
                  or (w in INTERJECTORS) or (list_out and (w in LIST_JOINERS or w == "step"))
                  or w in vocab_alias or w in ("no", "wait", "sorry", "actually", "mean", "scratch", "that")
                  and i in gold_idx)
            if ok:
                authorized_del += 1
            else:
                omitted.append(w)
        for w in ins:
            if w in vocab_canon or (list_out and w.isdigit()):
                continue
            added.append(w)
        if op == "replace":
            substituted.append((" ".join(src[i1:i2]), " ".join(dst[j1:j2])))
    return {"omitted": omitted, "added": added, "substituted": substituted, "authorized_deletions": authorized_del,
            "lexical_edits": edit_distance(src, dst)}


def score_synthetic(case: dict, text: str | None, *, delivered: bool) -> dict:
    """Metrics for one synthetic case and one output (model-only or delivered)."""
    if text is None:
        return {"available": False, "damage": True, "repair_success": False, "failure": True}
    I, E = case["model_input"], case["target"]
    E_ref = case.get("delivered_reference") or E if delivered else E
    list_out = list_items(E) > 0
    vp = case.get("vocabulary_pairs") or []
    # Additions are judged against the raw input (a word the speaker never said);
    # omissions against the input with the gold corrections applied, so a correctly
    # resolved correction cannot be misread as dropped content.
    al = alignment(I, text, vocab_pairs=vp, list_out=list_out)
    al_corr = alignment(remove_spans(I, case.get("gold_offsets") or []), text, vocab_pairs=vp, list_out=list_out)
    al["omitted"] = al_corr["omitted"]
    tl = text.casefold()
    facts_missing = [f["text"] for f in case.get("critical_facts", []) if f["text"].casefold() not in tl
                     and " ".join(lex(f["text"])) not in " ".join(lex(text))]
    obs_kept = [o for o in case.get("obsolete_values", [])
                if len(re.findall(r"(?<!\w)" + re.escape(o.casefold()) + r"(?!\w)", tl))
                > len(re.findall(r"(?<!\w)" + re.escape(o.casefold()) + r"(?!\w)", E.casefold()))]
    neg_out = sum(w in NEGATIONS or w.endswith("n't") for w in words(text))
    neg_ref = sum(w in NEGATIONS or w.endswith("n't") for w in words(E))
    neg_in = sum(w in NEGATIONS or w.endswith("n't") for w in words(I))
    negation_changed = not (neg_out == neg_ref or neg_out == neg_in)
    ending = [w for w in lex(E) if w not in FILLERS][-3:]
    tail = lex(text)[-14:]
    missing_ending = bool(ending) and not all(w in tail for w in ending)
    content_added = [w for w in al["added"] if w not in FUNCTION or w in {"not", "or", "if", "nor"}]
    content_omitted = [w for w in al["omitted"] if w not in FUNCTION]
    out_words, in_words = len(words(text)), max(len(words(I)), 1)
    unwanted_answer = (len(content_added) >= 3 and case.get("category") in QUESTIONY) or out_words > 1.5 * in_words + 5
    hallucination = len(content_added) >= 1
    omission = len(content_omitted) >= 1
    paraphrase = sum(1 for a, b in al["substituted"] if set(a.split()) - FUNCTION and set(b.split()) - FUNCTION)
    damage = bool(facts_missing or hallucination or omission or negation_changed or missing_ending or unwanted_answer)
    lexical_match = lex(text) == lex(E_ref) or [w for w in lex(text) if w not in INTERJECTORS] == \
        [w for w in lex(E_ref) if w not in INTERJECTORS]
    list_ok = (not list_out) or list_items(text) == list_items(E_ref)
    is_noop = case.get("is_noop", False)
    filler_residue = sum(w in FILLERS for w in words(text))
    corr_success = None
    if case.get("gold_lines"):
        corr_success = not obs_kept and not facts_missing
    hyp, ref = lex(text), lex(E_ref)
    errs, n = wer(hyp, ref)
    ch_e = edit_distance(list(" ".join(hyp)), list(" ".join(ref)))
    return {
        "available": True, "damage": damage, "facts_changed": bool(facts_missing), "facts_missing": facts_missing,
        "hallucination": hallucination, "added_content": content_added[:12], "omission": omission,
        "omitted_content": content_omitted[:12], "negation_changed": negation_changed,
        "missing_ending": missing_ending, "unwanted_answer": bool(unwanted_answer), "paraphrase_subs": paraphrase,
        "exact_match": text == E_ref if is_noop else None, "lexical_match": lexical_match and list_ok,
        "repair_success": (not is_noop) and lexical_match and list_ok and not damage,
        "noop_preserved": text == I if is_noop else None,
        "unnecessary_edit": (text != I) if is_noop else None,
        "lexical_edits_vs_input": al["lexical_edits"], "filler_residue": filler_residue,
        "correction_success": corr_success, "obsolete_kept": obs_kept,
        "list_ok": list_ok if list_out else None, "wer_errors": errs, "wer_words": n,
        "cer_errors": ch_e, "cer_chars": max(len(" ".join(ref)), 1),
    }


def score_real(case: dict, asr: dict, text: str | None) -> dict:
    if text is None:
        return {"available": False, "damage": True, "failure": True}
    I = asr["normalized"]
    al = alignment(I, text)
    unauthorized = len(al["omitted"]) + len(al["added"])
    out = {"available": True, "unauthorized_edits": unauthorized, "unauthorized_edit": unauthorized > 0,
           "added_content": al["added"][:12], "omitted_content": al["omitted"][:12],
           "lexical_edits_vs_input": al["lexical_edits"], "damage": unauthorized > 0,
           "filler_in": sum(w in FILLERS for w in words(I)), "filler_out": sum(w in FILLERS for w in words(text)),
           "changed": text != I}
    if case["source"] == "fleurs":
        e, n = wer(lexical(text), lexical(case["lexical_reference"]))
        out.update(wer_errors=e, wer_words=n)
    else:
        best = min((wer(lexical(text), lexical(r)) for r in case["contract_refs"].values()), key=lambda x: x[0] / x[1])
        out.update(wer_errors=best[0], wer_words=best[1])
    return out


# ---------------------------------------------------------------- bootstrap

def family_bootstrap(rows_a: dict, rows_b: dict, metric, families: dict, n: int = 2000, seed: int = 15,
                     ratio: bool = False) -> dict:
    """Paired family bootstrap of mean(metric_b) - mean(metric_a).
    ``rows_*``: case_id -> metric value (bool/float) or (num, den) when ratio."""
    ids = [c for c in rows_a if c in rows_b]
    fam = defaultdict(list)
    for c in ids:
        fam[families.get(c, c)].append(c)
    keys = sorted(fam)

    def stat(case_ids):
        if ratio:
            na = sum(rows_a[c][0] for c in case_ids); da = sum(rows_a[c][1] for c in case_ids)
            nb = sum(rows_b[c][0] for c in case_ids); db = sum(rows_b[c][1] for c in case_ids)
            return (nb / db if db else 0) - (na / da if da else 0)
        return (sum(float(rows_b[c]) for c in case_ids) - sum(float(rows_a[c]) for c in case_ids)) / len(case_ids)

    point = stat(ids) if ids else None
    rng = random.Random(seed)
    samples = []
    for _ in range(n):
        draw = [c for k in rng.choices(keys, k=len(keys)) for c in fam[k]]
        samples.append(stat(draw))
    samples.sort()
    lo, hi = samples[int(0.025 * n)], samples[int(0.975 * n) - 1]
    return {"diff": point, "ci95": [lo, hi], "n_cases": len(ids), "n_families": len(keys), "resamples": n}


def rate(values) -> float | None:
    v = [float(x) for x in values if x is not None]
    return sum(v) / len(v) if v else None


def mde(p: float, n: int, z: float = 1.96, power_z: float = 0.84) -> float:
    """Approximate minimum detectable difference for two paired proportions
    near base rate p (conservative: treats them as independent)."""
    return (z + power_z) * math.sqrt(2 * p * (1 - p) / n) if n else float("inf")
