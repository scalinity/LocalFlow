"""Versioned, input-anchored edit checks, separate from the legacy metrics.

These checks count lexical edits and exact technical-literal occurrences. They
do not assess meaning, punctuation attachment, or whether a reference is true.
An unchanged fallback may miss repairs but never introduces an edit. Reference
conflicts and incomplete metadata remain visible instead of becoming a PASS.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass
from decimal import Decimal


SCORER_VERSION = "strict-lexical-v2-incomplete-openings"
FILLERS = {"um", "uh", "erm", "ehm", "hmm", "mhm"}
STUTTER_WORDS = {"a", "an", "the", "to", "of", "in", "on", "at", "for", "and",
                 "or", "but", "is", "it", "i", "we", "you", "he", "she", "they",
                 "be", "with", "that", "this", "as", "by", "from", "not"}
ENUMERATION = {"first", "second", "third", "fourth", "fifth", "sixth", "seventh",
               "eighth", "ninth", "tenth", "next", "then", "finally", "step"}
NUMBER_WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)))
NUMBER_WORDS.update(dict(zip(
    "twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10))))
NUMERIC = r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
TOKEN = re.compile(r"(?<!\w)" + NUMERIC + r"(?!\w)"
                   r"|[^\W_]+(?:['_’][^\W_]+)*|[$%]", re.UNICODE)
LIST_PREFIX = re.compile(r"^\s*(?:[-*+] |\d+[.)] )", re.MULTILINE)
QUOTED = re.compile(r'''"[^"\n]*"|“[^”\n]*”|`[^`\n]*`|(?<!\w)'[^'\n]*'(?!\w)|‘[^’\n]*’''')


@dataclass(frozen=True)
class Token:
    key: str
    text: str
    start: int
    end: int


def _tokens(text: str, *, list_body: bool = False) -> list[Token]:
    # Replace list prefixes by spaces so source offsets remain meaningful.
    if list_body:
        text = LIST_PREFIX.sub(lambda m: " " * len(m.group()), text)
    matches = list(TOKEN.finditer(text))
    out, i = [], 0
    while i < len(matches):
        m = matches[i]
        word = m.group().casefold().replace("’", "'")
        end = m.end()
        if word in NUMBER_WORDS:
            value = NUMBER_WORDS[word]
            if value >= 20 and i + 1 < len(matches):
                nxt = matches[i + 1]
                number = NUMBER_WORDS.get(nxt.group().casefold())
                if number is not None and number < 10 and text[end:nxt.start()].isspace():
                    value += number
                    i += 1
                    end = nxt.end()
            word = str(value)
        elif re.fullmatch(NUMERIC, word):
            word = format(Decimal(word.replace(",", "")).normalize(), "f")
        elif word == "$":
            word = "dollars"
        elif word == "%":
            word = "percent"
        out.append(Token(word, text[m.start():end], m.start(), end))
        i += 1
    return out


def _counts(tokens):
    return collections.Counter(t.key for t in tokens)


def _items(counts):
    return [{"token": token, "count": n} for token, n in sorted(counts.items()) if n > 0]


def _occurrences(haystack, needle):
    if not needle:
        return 0
    return sum(haystack[i:i + len(needle)] == needle
               for i in range(len(haystack) - len(needle) + 1))


def _keys(text):
    return [t.key for t in _tokens(text)]


def _correction_spans(case, source, issues):
    spans = case.get("gold_offsets") or []
    lines = case.get("gold_lines") or []
    if spans:
        valid = []
        for span in spans:
            if (not isinstance(span, (list, tuple)) or len(span) != 2
                    or any(not isinstance(x, int) for x in span)
                    or not 0 <= span[0] < span[1] <= len(source)):
                issues.append("invalid_correction_offset")
                continue
            valid.append(tuple(span))
        valid.sort()
        if any(a[1] > b[0] for a, b in zip(valid, valid[1:])):
            issues.append("overlapping_correction_offsets")
            return []
        if lines and [source[a:b].casefold() for a, b in valid] != [s.casefold() for s in lines]:
            issues.append("correction_lines_disagree_with_offsets")
            return []
        return valid
    cursor, found = 0, []
    for line in lines:
        # Without offsets an ambiguous occurrence cannot authorize a deletion.
        matches = list(re.finditer(re.escape(line), source[cursor:], re.IGNORECASE)) if line else []
        if len(matches) != 1:
            issues.append("missing_or_ambiguous_correction_span")
            continue
        m = matches[0]
        found.append((cursor + m.start(), cursor + m.end()))
        cursor += m.end()
    return found


def _identifier_counts(text, annotated=()):
    """Conservative candidates plus explicitly annotated identifier strings.

    Bare names and ordinary capitalization are outside automatic ID detection.
    Sentence punctuation around a literal is not counted as part of its name.
    """
    counts = collections.Counter()
    for m in re.finditer(r"\S+", text):
        word = m.group().strip('"“”`\'()[]{}<>,;!?.')
        technical = ("_" in word or "/" in word or "\\" in word or "@" in word
                     or word.startswith("--") or re.search(r"[a-z][A-Z]", word)
                     or re.search(r"[A-Za-z]\d|\d[A-Za-z]", word)
                     or re.search(r"[A-Za-z][\w-]*\.[A-Za-z][\w.-]*", word)
                     or re.search(r"[A-Za-z][\w-]*:[\w-]+", word))
        if word and technical:
            counts[word] += 1
    for word in annotated:
        counts[word] = len(re.findall(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text))
    return counts


def _incomplete_openings(case, text, source_tokens, optional, correction_spans, correction_issues):
    """Prove a proposed restart deletion using an independent sequence walk.

    Only exact token matches, existing optional-token deletions and a bounded
    two-token opening deletion are walk edges. Substitutions, reordered words
    and ambiguous occurrence assignments abstain. In particular, vocabulary
    replacements elsewhere are not handled by this additional authorization.
    """
    if text is None:
        return [], "unavailable"
    source = case["model_input"]
    output = _tokens(text)
    sk, dk = [t.key for t in source_tokens], [t.key for t in output]
    if sk == dk:
        return [], "unchanged_lexical_sequence"
    markers = {"that", "which", "who", "whom"}
    subjects = {"i", "you", "he", "she", "it", "we", "they"}
    auxiliaries = {"am", "is", "are", "was", "were", "has", "have", "had", "do", "does", "did",
                   "can", "could", "will", "would", "shall", "should", "must", "may", "might"}
    openings = [i for i in range(len(sk) - 4)
                if sk[i] in markers and sk[i + 1] in subjects
                and sk[i:i + 2] == sk[i + 2:i + 4] and sk[i + 4] in auxiliaries]
    if not openings:
        return [], "no_incomplete_opening"
    if any(char in source for char in "\"'`‘’“”"):
        return [], "quoted_or_apostrophe_source"
    if correction_issues:
        return [], "invalid_correction_metadata"
    excluded = list(correction_spans)
    for span in case.get("protected_spans") or []:
        if (not isinstance(span, (list, tuple)) or len(span) < 2
                or any(type(offset) is not int for offset in span[:2])
                or not 0 <= span[0] < span[1] <= len(source)):
            return [], "invalid_protected_span"
        excluded.append(tuple(span[:2]))
    for pair in case.get("vocabulary_pairs") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(isinstance(x, str) and x for x in pair):
            return [], "invalid_vocabulary_pair"
        alias = _keys(pair[0])
        for start in range(len(sk) - len(alias) + 1) if alias else ():
            if sk[start:start + len(alias)] == alias:
                excluded.append((source_tokens[start].start, source_tokens[start + len(alias) - 1].end))
    sites = {}
    numeric_anchors = {"hundred", "thousand", "million", "billion", "point",
                       "percent", "percentage", "dollar", "dollars", "euro", "euros"}
    for i in openings:
        if i == 0 or i - 1 in optional:
            continue
        # A numeric or enumeration predecessor cannot supply the clause anchor.
        if not sk[i - 1].isalpha() or sk[i - 1] in ENUMERATION | numeric_anchors:
            continue
        section = source_tokens[i - 1:i + 5]
        if any(not re.fullmatch(r"[ \t]+", source[a.end:b.start]) for a, b in zip(section, section[1:])):
            continue
        if any(a < section[-1].end and section[0].start < b for a, b in excluded):
            continue
        if (i >= 2 and sk[i - 2:i] == sk[i:i + 2]
                and all(re.fullmatch(r"[ \t]+", source[source_tokens[j].end:source_tokens[j + 1].start])
                        for j in (i - 2, i - 1))):
            continue
        line_start = source.rfind("\n", 0, section[0].start) + 1
        # This exclusion covers existing bullet/tab forms without changing the
        # legacy list-prefix normalization used by the rest of the scorer.
        if re.match(r"[ \t]*(?:[-*+•]|\d+[.)])[ \t]+", source[line_start:]):
            continue
        sites[i] = (source_tokens[i].start, source_tokens[i + 1].end)
    if not sites:
        return [], "no_bounded_site"

    # Keep at most two distinct authorization histories per position. Future
    # edges depend only on these positions; two histories already prove that
    # the final occurrence assignment would be ambiguous.
    states = [collections.defaultdict(set) for _ in range(len(sk) + 1)]
    states[0][0].add(frozenset())

    def advance(i, j, histories, span=None):
        bucket = states[i][j]
        for history in histories:
            if len(bucket) < 2:
                bucket.add(history | {span} if span is not None else history)

    for i, positions in enumerate(states[:-1]):
        for j, histories in positions.items():
            if j < len(dk) and sk[i] == dk[j]:
                advance(i + 1, j + 1, histories)
            if i in optional:
                advance(i + 1, j, histories)
            if i in sites and j > 0 and sk[i - 1] == dk[j - 1] and dk[j:j + 3] == sk[i + 2:i + 5]:
                retained = output[j - 1:j + 3]
                if len(retained) == 4 and all(re.fullmatch(r"[ \t]+", text[a.end:b.start])
                                              for a, b in zip(retained, retained[1:])):
                    advance(i + 5, j + 3, histories, sites[i])
    matches = states[-1].get(len(dk), set())
    if not matches:
        return [], "output_sequence_not_proven"
    if len(matches) != 1:
        return [], "ambiguous_occurrence_assignment"
    spans = sorted(next(iter(matches)))
    return spans, "authorized" if spans else "no_restart_deletion"


def score_case(case: dict, text: str | None) -> dict:
    """Return mechanical evidence; no field represents a semantic PASS."""
    source = case["model_input"]
    target = case.get("target")
    issues, review = [], []
    list_target = bool(target and LIST_PREFIX.search(target))
    src = _tokens(source)
    ref = _tokens(target, list_body=list_target) if target is not None else None
    dst = _tokens(text, list_body=list_target) if text is not None else []
    sc, rc, dc = _counts(src), _counts(ref) if ref is not None else None, _counts(dst)
    source_keys, output_keys = [t.key for t in src], [t.key for t in dst]
    reference_keys = [t.key for t in ref] if ref is not None else None
    spans = _correction_spans(case, source, issues)
    quoted = [(m.start(), m.end()) for m in QUOTED.finditer(source)]
    authorized = collections.Counter()
    optional = set()
    for i, token in enumerate(src):
        in_quote = any(a <= token.start < b for a, b in quoted)
        correction = any(a <= token.start and token.end <= b for a, b in spans)
        stutter = (i > 0 and token.key in STUTTER_WORDS and src[i - 1].key == token.key
                   and source[src[i - 1].end:token.start].isspace())
        if correction or (not in_quote and (token.key in FILLERS or stutter)):
            authorized[token.key] += 1
            optional.add(i)

    candidate_spans, candidate_restart_status = _incomplete_openings(case, text, src, optional, spans, issues)
    reference_spans, reference_restart_status = _incomplete_openings(case, target, src, optional, spans, issues)
    candidate_restart = collections.Counter(t.key for t in src
        if any(a <= t.start and t.end <= b for a, b in candidate_spans))
    reference_restart = collections.Counter(t.key for t in src
        if any(a <= t.start and t.end <= b for a, b in reference_spans))
    ordinary = {"unavailable", "unchanged_lexical_sequence", "no_incomplete_opening", "no_restart_deletion", "authorized"}
    if candidate_restart_status not in ordinary:
        review.append("incomplete_restart_authorization_underdetermined")
    if reference_restart_status not in ordinary:
        review.append("reference_incomplete_restart_authorization_underdetermined")

    if list_target:
        markerless = [t.key for t in src if t.key not in ENUMERATION]
        if markerless == reference_keys and case.get("category") in {"formatting", "spoken_list"}:
            authorized.update(t.key for t in src if t.key in ENUMERATION)
        elif any(t.key in ENUMERATION for t in src):
            review.append("list_marker_authorization_ambiguous")
        if text is not None and len(LIST_PREFIX.findall(text)) != len(LIST_PREFIX.findall(target)):
            review.append("list_structure_differs_from_reference")

    # Vocabulary licenses full alias-to-canonical replacements, never a bag of
    # canonical words that can be added while the original alias remains.
    reference_authorized = authorized.copy()
    authorized.update(candidate_restart)
    reference_authorized.update(reference_restart)
    reference_vocab_additions = collections.Counter()
    vocab_additions, vocab_required_ids = collections.Counter(), collections.Counter()
    unfulfilled_vocab = collections.Counter()
    seen_aliases = []
    for pair in case.get("vocabulary_pairs") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(isinstance(s, str) and s for s in pair):
            issues.append("invalid_vocabulary_pair")
            continue
        alias, canonical = pair
        ak, ck = _keys(alias), _keys(canonical)
        if not ak or not ck or any(_occurrences(ak, old) or _occurrences(old, ak) for old in seen_aliases):
            issues.append("empty_or_overlapping_vocabulary_alias")
            continue
        seen_aliases.append(ak)
        removed = max(0, _occurrences(source_keys, ak) - _occurrences(output_keys, ak))
        inserted = max(0, _occurrences(output_keys, ck) - _occurrences(source_keys, ck))
        count = min(removed, inserted)
        if count:
            authorized.update({k: n * count for k, n in collections.Counter(ak).items()})
            vocab_additions.update({k: n * count for k, n in collections.Counter(ck).items()})
            vocab_required_ids.update({k: n * count for k, n in _identifier_counts(canonical).items()})
        if reference_keys is not None:
            expected_removed = max(0, _occurrences(source_keys, ak) - _occurrences(reference_keys, ak))
            expected_inserted = max(0, _occurrences(reference_keys, ck) - _occurrences(source_keys, ck))
            expected = min(expected_removed, expected_inserted)
            reference_authorized.update({k: n * expected for k, n in collections.Counter(ak).items()})
            reference_vocab_additions.update({k: n * expected for k, n in collections.Counter(ck).items()})
        # A dictionary does not authorize deleting the alias and supplying
        # nothing in its place. Keep this distinct from an unresolved alias.
        if removed > count:
            unfulfilled_vocab.update({k: n * (removed - count) for k, n in collections.Counter(ak).items()})

    required = sc - authorized
    if rc is not None:
        # An overbroad correction span cannot license deleting target-required
        # words. The separately proved opening deletion remains input-authorized
        # even when a reference retains the duplicate; reference mismatch stays
        # visible in missing_target_words and reference_exact.
        required |= (sc & rc) - candidate_restart
        target_unlicensed = (sc - rc) - reference_authorized
        if target_unlicensed:
            issues.append("target_omits_words_without_checked_authorization")
        target_new = (rc - sc) - reference_vocab_additions
        if target_new:
            issues.append("target_adds_words_without_checked_authorization")
    else:
        review.append("no_cleanup_target_reference")

    added = dc - (sc - candidate_restart) - vocab_additions
    # Target-consistent deletions with incomplete annotations are uncertain,
    # not proven new damage. Required words shared by input and target remain
    # an independent lower bound, even if correction metadata is overbroad.
    omitted = ((sc & rc) - candidate_restart - dc) if rc is not None else required - dc
    omitted |= unfulfilled_vocab
    unclassified_omissions = (required - dc) - omitted
    if unclassified_omissions:
        review.append("source_omission_authorization_underdetermined")
    facts = case.get("critical_facts") or []
    annotated = [f["text"] for f in facts if f.get("kind") in {"identifier", "path", "filename", "code"}]
    source_ids = _identifier_counts(source, annotated)
    output_ids = _identifier_counts(text or "", annotated)
    target_ids = _identifier_counts(target, annotated) if target is not None else source_ids
    corrected_ids = _identifier_counts(" ".join(source[a:b] for a, b in spans), annotated)
    identifier_changes = []
    for identifier in sorted(set(source_ids) | set(output_ids) | set(vocab_required_ids)):
        lower = (min(source_ids[identifier], target_ids[identifier]) if target is not None
                 else source_ids[identifier] - corrected_ids[identifier])
        lower += vocab_required_ids[identifier]
        upper = source_ids[identifier] + vocab_required_ids[identifier]
        count = output_ids[identifier]
        if count < lower or count > upper:
            identifier_changes.append({"identifier": identifier, "source_count": source_ids[identifier],
                                       "required_count": lower, "maximum_count": upper, "output_count": count})

    missing_facts, introduced_missing_facts = [], []
    for fact in facts:
        fk = _keys(fact["text"])
        before, after = _occurrences(source_keys, fk), _occurrences(output_keys, fk)
        expected = _occurrences(reference_keys, fk) if reference_keys is not None else before
        if not before:
            review.append("critical_fact_not_present_in_source")
        if expected > after:
            missing_facts.append(fact["text"])
        if min(before, expected) > after:
            introduced_missing_facts.append(fact["text"])

    unresolved = []
    for value in case.get("obsolete_values") or []:
        vk = _keys(value)
        expected = _occurrences(reference_keys, vk) if reference_keys is not None else 0
        if _occurrences(output_keys, vk) > expected:
            unresolved.append(value)
    for a, b in spans:
        phrase = source[a:b]
        if _occurrences(output_keys, _keys(phrase)):
            unresolved.append(phrase)

    if text is None:
        # Missing execution is not a measured model edit.
        review.append("output_unavailable")
        added = omitted = collections.Counter()
        unclassified_omissions = collections.Counter()
        identifier_changes = introduced_missing_facts = []
    if text is not None and text != source:
        review.append("meaning_and_attachment_not_assessed")
    introduced = bool(added or omitted or identifier_changes or introduced_missing_facts)
    return {
        "scorer_version": SCORER_VERSION, "case_id": case.get("case_id"),
        "available": text is not None, "source_unchanged": text == source if text is not None else None,
        "reference_exact": text == target if text is not None and target is not None else None,
        "introduced_edit_flag": introduced if text is not None else None,
        "unsupported_additions": _items(added), "introduced_required_omissions": _items(omitted),
        "unclassified_source_omissions": _items(unclassified_omissions),
        "identifier_count_changes": identifier_changes,
        "missing_target_words": _items(rc - dc) if rc is not None and text is not None else None,
        "target_word_excess": _items(dc - rc) if rc is not None and text is not None else None,
        "missing_critical_facts": missing_facts if text is not None else None,
        "introduced_missing_critical_facts": introduced_missing_facts,
        "unresolved_corrections": sorted(set(unresolved)) if text is not None else None,
        "metadata_issues": sorted(set(issues)), "review_flags": sorted(set(review)),
        "incomplete_restart_authorization": {
            "candidate_spans": [list(span) for span in candidate_spans], "candidate_status": candidate_restart_status,
            "reference_spans": [list(span) for span in reference_spans], "reference_status": reference_restart_status},
        "semantic_assessment": "NOT_ASSESSED",
        "identifier_scope": "annotated_identifiers_and_heuristic_technical_literals",
    }


def aggregate(cases: list[dict], rows: list[dict], mode: str = "delivered") -> dict:
    """Require the complete paired population; unavailable outputs stay visible."""
    case_ids = [c["case_id"] for c in cases]
    row_ids = [r["case_id"] for r in rows]
    if len(set(case_ids)) != len(case_ids) or len(set(row_ids)) != len(row_ids):
        raise ValueError("Duplicate case IDs are not a valid strict-score population")
    if set(case_ids) != set(row_ids):
        raise ValueError("Strict-score rows must match the complete case population")
    by_id = {r["case_id"]: r for r in rows}
    scores = [score_case(c, by_id[c["case_id"]].get(mode)) for c in cases]
    fields = ("introduced_edit_flag", "unsupported_additions", "introduced_required_omissions",
              "unclassified_source_omissions", "identifier_count_changes", "missing_target_words", "target_word_excess",
              "introduced_missing_critical_facts", "unresolved_corrections", "metadata_issues")
    return {"scorer_version": SCORER_VERSION, "mode": mode, "n": len(scores),
            "available": sum(s["available"] for s in scores),
            "counts": {field: sum(bool(s[field]) for s in scores) for field in fields},
            "semantic_assessment": "NOT_ASSESSED", "cases": scores}
