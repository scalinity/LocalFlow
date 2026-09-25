"""Typed numeric grammars for spoken-syntax normalization (M04, S10).

Deterministic, model-free parsing of spoken number forms into typed
values: integers, decimals/signs, percentages, percentage points,
currency, times, month-name dates, codes, phone numbers, versions,
IPs/ports, dimensions and unit-bearing counts. Decimal arithmetic keeps
values exact; invalid candidates (bad octets, day 32, oversized version
components) are proposed as rejected-with-reason, never repaired.
"""

from __future__ import annotations

from decimal import Decimal

from .span_types import (
    JOIN_WORD,
    Proposal,
    Span,
)

# Words that block the following-noun integer conversion: a number word
# followed by one of these is prose ("one of the reasons"), not a count.
STOP_AFTER_INTEGER = {
    "of", "in", "on", "at", "or", "and", "but", "than", "is", "was",
    "were", "be", "been", "am", "are", "to", "from", "with", "for",
    "that", "this", "it", "its", "as", "by", "per", "so", "if", "when",
    "while", "before", "after", "over", "under", "about", "into",
    "through", "comma",
}
# A bare "one" directly after these is an idiom ("the number one reason"),
# not a countable quantity.
IDIOM_PREV_ONE = {"number"}
# A bare "hundred"/"thousand" directly after a quantifier is prose
# ("a few hundred people", "several hundred years"), not a quantity.
QUANTIFIER_PREV_SCALE = {
    "few", "several", "some", "many", "couple", "handful", "hundreds",
    "thousands", "millions", "dozens", "scores",
}
YEAR_MIN, YEAR_MAX = 1000, 2999


class LocaleTables:
    """Word tables and rendering rules for one locale. Built from the
    policy's deeply frozen copy and sealed by the policy: its tables are
    read-only views and its attributes cannot be reassigned
    (M04-AUDIT-12)."""

    def __init__(self, name: str, data):
        self.name = name
        self.units = data["units"]
        self.teens = data["teens"]
        self.tens = data["tens"]
        self.hundreds_mult = data.get("hundreds_mult", {})
        self.hundreds_val = data.get("hundreds_val", {})
        self.big_scales = {
            k: v for k, v in data.get("big_scales", {}).items()
            if v >= 1000}
        self.connector: str | None = data.get("connector")
        self.connector_states = frozenset(
            data.get("connector_states", ()))
        self.integer_stop_after = frozenset(
            {*STOP_AFTER_INTEGER, *data.get("integer_stop_after", ())})
        self.sign_words = data.get("sign_words", {})
        self.decimal_words = frozenset(data.get("decimal_words", ()))
        self.percent_words = frozenset(data.get("percent_words", ()))
        self.pp_words = tuple(data.get("percentage_point_words", ()))
        self.currency_words = data.get("currency_words", {})
        self.currency_codes = data.get("currency_codes", {})
        self.months = data.get("months", {})
        self.ordinal_words = data.get("ordinal_words", {})
        self.grouping = data.get("grouping_separator", ",")
        self.decimal_sep = data.get("decimal_separator", ".")
        self.percent_space = data.get("percent_rendering") == "space"
        self.currency_before = data.get("currency_before", True)
        self.date_rendering = data.get("date_rendering", "month_day")
        self.phone_groups = tuple(data.get("phone_groups", (3, 3, 4)))
        # Month names that are also ordinary words ("may", "march",
        # "august"): a date needs evidence beyond the word (M04-AUDIT-07).
        self.ambiguous_months = frozenset(
            data.get("ambiguous_month_words", ()))
        self.date_previous = frozenset(data.get("date_previous_words", ()))
        self.number_words = frozenset(
            set(self.units) | set(self.teens) | set(self.tens)
            | set(self.hundreds_mult) | set(self.hundreds_val)
            | set(self.big_scales) | set(self.sign_words)
            | self.decimal_words)
        self.cardinal_words = frozenset(
            set(self.units) | set(self.teens) | set(self.tens)
            | set(self.hundreds_mult) | set(self.hundreds_val)
            | set(self.big_scales))
        from types import MappingProxyType
        self.big_scales = MappingProxyType(dict(self.big_scales))

    def seal(self) -> None:
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError(
                f"LocaleTables is immutable (cannot set {name!r})")
        object.__setattr__(self, name, value)

    # ---- rendering ----------------------------------------------------------

    def group_int(self, value: int | Decimal) -> str:
        s = str(int(value))
        if len(s) <= 4:
            return s
        out, rest = "", s
        while len(rest) > 3:
            out = self.grouping + rest[-3:] + out
            rest = rest[:-3]
        return rest + out

    def render_decimal(self, value: Decimal, frac_digits: str) -> str:
        """Render with the exact spoken fractional digits preserved."""
        neg = value < 0
        whole = abs(int(value))
        out = f"{self.group_int(whole)}{self.decimal_sep}{frac_digits}"
        return f"-{out}" if neg else out

    def render_exact(self, value) -> str:
        """Render an exact value with no spoken fraction pattern (a
        scaled quantity): integral values as grouped integers, a
        non-integral value with its exact minimal fraction — never
        truncated through int() (M04-AUDIT-03)."""
        d = Decimal(value)
        if d == d.to_integral_value():
            return self.group_int(int(d)) if d >= 0 else \
                "-" + self.group_int(-int(d))
        text = format(abs(d).normalize(), "f")
        whole, frac = text.split(".")
        out = f"{self.group_int(int(whole))}{self.decimal_sep}{frac}"
        return f"-{out}" if d < 0 else out

    def render_percent(self, text_value: str) -> str:
        gap = " " if self.percent_space else ""
        return f"{text_value}{gap}%"


class ParsedNumber:
    """A parsed spoken quantity: exact value plus how it was spoken."""

    __slots__ = ("value", "count", "frac_digits", "sign", "digit_run")

    def __init__(self, value, count, frac_digits=None, sign=1,
                 digit_run=None):
        self.value = value            # int or Decimal (always positive-semi)
        self.count = count            # tokens consumed
        self.frac_digits = frac_digits  # str when spoken with a decimal part
        self.sign = sign
        self.digit_run = digit_run    # str when spoken as bare digits


def parse_cardinal(words: list[str], t: LocaleTables):
    """Longest grammatical cardinal from words[0:]. (value, count) or None.

    English "one hundred twenty six", "twelve thousand", Spanish
    "ciento veinte", "treinta y cinco". A small-value state machine keeps
    the grammar honest: "twenty six" parses, "two one", "one ninety" and
    "twenty thirty" stop before the illegal word — bare digit runs
    ("zero zero seven") parse as a single units word, never as a
    compound cardinal. Malformed scale chains stop too (see
    ``scan_cardinal``).
    """
    value, count, _malformed = scan_cardinal(words, t)
    if not count:
        return None
    return value, count


def scan_cardinal(words: list[str], t: LocaleTables):
    """(value, count, malformed) — the longest valid cardinal prefix and
    whether it stopped on a MALFORMED scale (M04-AUDIT-04): an explicit
    zero multiplier ("zero hundred", "zero thousand"), a scale with no
    multiplier group after another scale ("one thousand million"), or a
    scale not smaller than the previous one ("one million million").
    An explicit zero is tracked separately from an omitted multiplier —
    ``(current or 1)`` would turn "zero thousand" into 1000."""
    total = 0
    current = 0
    count = 0
    seen = False
    explicit_zero = False
    last_scale = None
    # What the current (<1000) group ends with: "empty", "unit" (a bare
    # units word — may still take "hundred"), "tens" (may still take
    # units), "unit_set" (units after tens/hundreds — terminal),
    # "teen" (terminal), "hundreds" (may still take tens/units/teens).
    state = "empty"
    i = 0
    n = len(words)
    while i < n:
        w = words[i]
        if w in t.units:
            if state == "empty":
                state = "unit"
                explicit_zero = t.units[w] == 0
            elif state == "tens":
                state = "unit_set"
            elif state == "hundreds":
                state = "unit_set"
            else:
                break  # "two one", "twenty six one", "twelve one"
            current += t.units[w]
        elif w in t.teens:
            if state in ("empty", "hundreds"):
                state = "teen"
            else:
                break
            current += t.teens[w]
        elif w in t.tens:
            if state in ("empty", "hundreds"):
                state = "tens"
            else:
                break  # "one ninety", "twenty thirty"
            current += t.tens[w]
        elif w in t.hundreds_val:
            if state != "empty":
                break
            current += t.hundreds_val[w]
            state = "hundreds"
        elif w in t.hundreds_mult:
            if state not in ("empty", "unit"):
                break  # "twenty hundred", "hundred hundred"
            if state == "unit" and explicit_zero:
                return total + current, count, True  # "zero hundred"
            current = (current if state == "unit" else 1) \
                * t.hundreds_mult[w]
            state = "hundreds"
        elif w in t.big_scales:
            scale = t.big_scales[w]
            if state == "empty" and not seen:
                break
            if state == "empty" or (state == "unit" and explicit_zero) \
                    or (last_scale is not None and scale >= last_scale):
                # "one thousand million", "zero thousand",
                # "one million two million"
                return total + current, count, True
            total += current * scale
            current = 0
            last_scale = scale
            state = "empty"
            explicit_zero = False
        elif w == t.connector and seen and state in t.connector_states \
                and i + 1 < n and _is_num_word(words[i + 1], t):
            pass  # "one hundred and twenty", "treinta y cinco"
        else:
            break
        count += 1
        seen = True
        i += 1
    return total + current, count, False


def _is_num_word(w: str, t: LocaleTables) -> bool:
    return (w in t.units or w in t.teens or w in t.tens
            or w in t.hundreds_val or w in t.hundreds_mult
            or w in t.big_scales)


def parse_digit_run(words: list[str], t: LocaleTables, min_len: int = 1):
    """Consecutive single-unit words as a digit string ("zero zero seven
    three" → "0073"). (digits, count) or None."""
    digits = []
    count = 0
    for w in words:
        if w in t.units:
            digits.append(str(t.units[w]))
            count += 1
        else:
            break
    if count < min_len:
        return None
    return "".join(digits), count


def parse_signed_quantity(words: list[str], t: LocaleTables):
    """[sign] (cardinal | cardinal decimal digit-run [scale]) as Decimal.

    Returns (ParsedNumber|None). "minus zero point zero five" → -0.05
    with frac_digits "05"; "one point five million" → 1500000.
    """
    sign = 1
    i = 0
    if words and words[0] in t.sign_words:
        sign = t.sign_words[words[0]]
        i = 1
    rest = words[i:]
    if not rest:
        return None
    card = parse_cardinal(rest, t)
    if card is None:
        return None
    value, count = card
    j = count
    frac = None
    if j < len(rest) and rest[j] in t.decimal_words:
        run = parse_digit_run(rest[j + 1:], t)
        if run is None:
            return None
        frac, dcount = run
        j += 1 + dcount
        dec = Decimal(int(value)) + Decimal(f"0.{frac}")
        if j < len(rest) and rest[j] in t.big_scales:
            dec *= Decimal(t.big_scales[rest[j]])
            j += 1
            # The spoken fraction digits no longer describe the scaled
            # value: keep it EXACT (an integral result becomes an int,
            # a fractional one keeps its minimal exact digits) — never
            # int()-truncated (M04-AUDIT-03).
            if dec == dec.to_integral_value():
                value, frac = int(dec), None
            else:
                value = dec
                frac = format(dec.normalize(), "f").split(".")[1]
        else:
            value = dec
    elif j < len(rest) and rest[j] in t.big_scales:
        # A further scale after an integer part ("two thousand million"
        # style) is handled by parse_cardinal itself.
        pass
    return ParsedNumber(value, i + j, frac, sign, None)


def parse_year(words: list[str], t: LocaleTables):
    """Spoken year: full cardinal ("two thousand twenty six") or split
    pairs ("twenty twenty six" → 20|26). Returns int or None."""
    card = parse_cardinal(words, t)
    if card and YEAR_MIN <= card[0] <= YEAR_MAX:
        return card[0]
    for split in range(1, len(words)):
        a = parse_cardinal(words[:split], t)
        b = parse_cardinal(words[split:], t)
        if a and b and a[1] == split and b[1] == len(words) - split:
            a_v, b_v = a[0], b[0]
            if 0 <= a_v <= 99 and 0 <= b_v <= 99:
                year = 100 * a_v + b_v
                if YEAR_MIN <= year <= YEAR_MAX:
                    return year
    return None


# ---------------------------------------------------------------------------
# Grammars. Each takes the engine MatchHost and yields Proposals over the
# token list. Layer 4 (typed numeric grammar).
# ---------------------------------------------------------------------------

def _quantity_at(host, i):
    """Parse a spoken quantity (with optional sign word) starting at
    token i, never across a structural delimiter. Returns ParsedNumber
    or None."""
    words = host.words(i, 14)
    if not words:
        return None
    return parse_signed_quantity(words, host.tables)


def _quantity_text(pn: ParsedNumber, t: LocaleTables) -> str:
    if pn.frac_digits is not None:
        return t.render_decimal(pn.value * pn.sign, pn.frac_digits)
    return t.render_exact(pn.value * pn.sign)


def _signed(pn: ParsedNumber):
    """The quantity's typed value: magnitude composed with its sign —
    every consumer validates and records THIS, the value it renders
    (M04-AUDIT-05)."""
    v = pn.value * pn.sign
    return int(v) if isinstance(v, int) or (
        isinstance(v, Decimal) and pn.frac_digits is None
        and v == v.to_integral_value()) else v


def _span(host, i, count) -> Span:
    """Span of tokens i..i+count-1 — their lexical cores, so edge
    punctuation stays outside every edit (M04-AUDIT-02)."""
    return host.core_span(i, i + count)


# Words that continue spoken digit/number speech: a number standing
# next to one of these is part of a longer run (a code, a time, a
# version, a second quantity), never a standalone count.
_DIGIT_SPEECH = frozenset({"oh", "o", "dot"})


def _num_like(host, idx) -> bool:
    """Token idx is number speech: a cardinal word, a sign or decimal
    word, or a digit-speech joiner."""
    w = _word_at(host, idx)
    if w is None:
        return False
    t = host.tables
    return (w in t.cardinal_words or w in t.sign_words
            or w in t.decimal_words or w in _DIGIT_SPEECH)


def _juxtaposed_before(host, start) -> bool:
    """The phrase starting at token ``start`` directly follows other
    number speech in the same clause ("three FIFTEEN minute", "point
    FIVE percent", "one ninety two dot ONE"): it is the tail of a
    longer run, so no grammar may convert it alone — adjacent digits
    ("3 15") would change how the run reads (M04-AUDIT-06/-08)."""
    return start > 0 and not host.brk[start] and _num_like(host, start - 1)


def _juxtaposed_after(host, end) -> bool:
    """Number speech continues right after the phrase ending before
    token ``end`` (same clause)."""
    return end < len(host.tokens) and not host.brk[end] \
        and _num_like(host, end)


def _quantified(host, start) -> bool:
    """A quantity that opens with a bare scale word right after a
    quantifier ("a few HUNDRED thousand", "several hundred") is
    approximate prose, not an exact amount (M04-AUDIT-04)."""
    t = host.tables
    first = _word_at(host, start)
    return (first in t.hundreds_mult or first in t.big_scales) \
        and start > 0 and not host.brk[start] \
        and (_word_at(host, start - 1) or "") in QUANTIFIER_PREV_SCALE


def _text_of(host, span: Span) -> str:
    return host.text[span.start:span.end]


def _end_index(host, i, count) -> int:
    return min(i + count, len(host.tokens))


def _word_at(host, idx):
    if 0 <= idx < len(host.tokens):
        return host.tokens[idx].word
    return None


def grammar_integer(host):
    """Number words followed by a non-function word → digits ("twelve
    retries" → "12 retries"); single "one" after idioms stays prose.
    Bare digit runs belong to the phone/code grammars and a bare "zero"
    is prose, not a count. A number standing next to other number
    speech ("three fifteen minute breaks", "point five percent", "five
    minus three") is part of a longer run and stays words; a quantity
    after a quantifier ("a few hundred thousand") is approximate prose."""
    if not host.profile.get("integers"):
        return
    t = host.tables
    i = 0
    while i < len(host.tokens):
        tok = host.tokens[i]
        if not _is_num_word(tok.word, t) or tok.word in t.sign_words:
            i += 1
            continue
        pn = _quantity_at(host, i)
        if pn is None or pn.value < 0 or pn.value == 0:
            i += 1
            continue
        end = _end_index(host, i, pn.count)
        nxt = _word_at(host, end)
        if nxt is None or end >= len(host.tokens) or host.brk[end] \
                or nxt in host.tables.integer_stop_after:
            i += 1
            continue
        if pn.value == 1 and pn.count == 1 \
                and _word_at(host, i - 1) in IDIOM_PREV_ONE:
            i += 1
            continue
        if _quantified(host, i) or _juxtaposed_before(host, i) \
                or _juxtaposed_after(host, end):
            # quantified prose / inside a longer number run (digit run,
            # year speech, time, version, a second quantity)
            i += pn.count if pn.count > 1 else 1
            continue
        if pn.frac_digits is None:
            span = _span(host, i, pn.count)
            out = _quantity_text(pn, host.tables)
            yield Proposal(
                layer=4, cls="integer", op="number_word_to_digits",
                span=span, input_text=_text_of(host, span),
                output_text=out, value=_signed(pn),
                join=JOIN_WORD)
        # A decimal ("one point two six …") is the decimal grammar's job.
        i += pn.count if pn.count > 1 else 1


def grammar_anchored_integer(host):
    """Technical anchors convert a trailing cardinal ("milestone
    fourteen" → "milestone 14"); the typed value carries the spoken
    sign ("step negative five" → -5, M04-AUDIT-05). A cardinal followed
    by more number speech ("section five thirty") stays words."""
    anchors = set(host.profile.get("integer_anchors", []))
    for i, tok in enumerate(host.tokens):
        if tok.word not in anchors or i + 1 >= len(host.tokens) \
                or host.brk[i + 1]:
            continue
        j = i + 1
        pn = _quantity_at(host, j)
        if pn is None or pn.frac_digits is not None:
            continue
        if _juxtaposed_after(host, j + pn.count):
            continue
        span = _span(host, j, pn.count)
        yield Proposal(
            layer=4, cls="anchored_integer", op="number_word_to_digits",
            span=span, input_text=_text_of(host, span),
            output_text=_quantity_text(pn, host.tables),
            value=_signed(pn), join=JOIN_WORD)


def grammar_decimal(host):
    """Sign + cardinal + decimal word + digit run ("minus zero point zero
    five" → "-0.05"). A decimal never starts inside a longer number run
    ("one point TWENTY SIX point four") and a run with a second decimal
    word is version-speak, owned by grammar_numeric_chains."""
    t = host.tables
    i = 0
    while i < len(host.tokens):
        start = i
        sign = 1
        j = i
        if host.tokens[j].word in t.sign_words:
            sign = t.sign_words[host.tokens[j].word]
            j += 1
            if j >= len(host.tokens) or host.brk[j]:
                i += 1
                continue
        if _juxtaposed_before(host, start):
            i += 1
            continue
        card = parse_cardinal(host.words(j, 14), t)
        if card is None:
            i += 1
            continue
        value, count = card
        k = j + count
        if k >= len(host.tokens) or host.brk[k] \
                or _word_at(host, k) not in t.decimal_words:
            i += 1
            continue
        if k + 1 >= len(host.tokens) or host.brk[k + 1]:
            i += 1
            continue
        run = parse_digit_run(host.words(k + 1, 13), t, min_len=1)
        if run is None:
            i += 1
            continue
        frac, dcount = run
        consumed = k + 1 + dcount
        if consumed < len(host.tokens) and not host.brk[consumed] \
                and _word_at(host, consumed) in t.decimal_words:
            # version-speak: the chain grammar owns (and flags) it
            i = consumed
            continue
        dec = Decimal(int(value)) + Decimal(f"0.{frac}")
        total = consumed - start
        span = _span(host, start, total)
        out = host.tables.render_decimal(dec * sign, frac)
        yield Proposal(
            layer=4, cls="decimal", op="decimal_words",
            span=span, input_text=_text_of(host, span),
            output_text=out, value=dec * sign, join=JOIN_WORD)
        i = start + total


def grammar_numeric_chains(host):
    """Maximal number-speech chains that no single grammar may own in
    part (M04-AUDIT-08). Each flagged chain is a STRUCTURAL review
    region — nothing inside or straddling it converts:

    * two or more decimal words without a version anchor
      ("one point twenty six point four") — unanchored version-speak;
    * a chain opening with a decimal word ("point five percent") — the
      whole-number part is missing; converting "five percent" would
      change the value;
    * number components joined by "dot" whose arity is not the four
      octets of an IPv4 address ("one dot two dot three",
      "... dot four dot five"), or dots mixed with decimal words.
    """
    t = host.tables
    tokens = host.tokens
    n = len(tokens)

    def member(k):
        w = tokens[k].word
        return tokens[k].is_word and (
            w in t.cardinal_words or w in t.sign_words
            or w in t.decimal_words or w == "dot" or w in ("oh", "o"))

    i = 0
    while i < n:
        if not member(i):
            i += 1
            continue
        j = i
        while j + 1 < n and member(j + 1) and not host.brk[j + 1]:
            j += 1
        # trim joiners that do not sit between number words
        lo, hi = i, j
        while lo <= hi and tokens[lo].word == "dot":
            lo += 1
        while hi >= lo and (tokens[hi].word == "dot"
                            or tokens[hi].word in t.decimal_words
                            and hi > lo):
            hi -= 1
        i = j + 1
        if lo > hi:
            continue
        words = [tokens[k].word for k in range(lo, hi + 1)]
        points = sum(1 for w in words if w in t.decimal_words)
        dots = sum(1 for w in words if w == "dot")
        reason = None
        lead = 1 if words[0] in t.sign_words else 0
        if len(words) > lead + 1 and words[lead] in t.decimal_words \
                and words[lead + 1] in t.cardinal_words:
            reason = "leading_decimal"
        elif dots and points:
            reason = "dotted_number_arity"
        elif points >= 2:
            reason = "unanchored_version"
        elif dots and dots + 1 != 4:
            reason = "dotted_number_arity"
        if reason is None or not any(w in t.cardinal_words
                                     for w in words):
            continue
        span = _span(host, lo, hi - lo + 1)
        yield Proposal(
            layer=4, cls="version" if reason == "unanchored_version"
            else "number_chain", op="number_chain",
            span=span, input_text=_text_of(host, span),
            output_text="", value=None, reason=reason, review=True)


def grammar_malformed_quantity(host):
    """Whole-span refusal of malformed or quantified scale speech
    (M04-AUDIT-04): an explicit zero multiplier, a repeated or
    increasing scale, or a bare scale opening a quantity right after a
    quantifier ("a few hundred thousand dollars"). The number run
    becomes a STRUCTURAL review region so no currency, percent, unit or
    integer grammar converts a valid-looking part of it."""
    t = host.tables
    tokens = host.tokens
    n = len(tokens)
    i = 0
    while i < n:
        if tokens[i].word not in t.cardinal_words or not tokens[i].is_word:
            i += 1
            continue
        j = i
        while j + 1 < n and not host.brk[j + 1] and (
                tokens[j + 1].word in t.cardinal_words
                or tokens[j + 1].word == t.connector):
            j += 1
        words = [tokens[k].word for k in range(i, j + 1)]
        reason = None
        if _quantified(host, i):
            reason = "quantified_scale"
        else:
            pos = 0
            while pos < len(words):
                # A cardinal never spans more than the 14-word window
                # every other grammar parses; bounding the slice keeps
                # a long number-word run linear.
                _v, c, bad = scan_cardinal(words[pos:pos + 16], t)
                if bad:
                    reason = "malformed_scale"
                    break
                pos += c if c else 1
        if reason is not None:
            span = _span(host, i, j - i + 1)
            yield Proposal(
                layer=4, cls="quantity", op="number_words",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None, reason=reason, review=True)
        i = j + 1


def _seq_at(host, i, words) -> bool:
    """tokens[i:] spell ``words`` as one connected phrase."""
    n = len(words)
    return i + n <= len(host.tokens) and \
        [tk.word for tk in host.tokens[i:i + n]] == words \
        and host.connected(i, i + n)


def grammar_percent(host):
    """Number phrase + percent word(s) → "N%"; the value is preserved so
    later checks know 12% and "twelve percent" are the same quantity.
    Percent markers may be multiword phrases ("por ciento")."""
    t = host.tables
    phrases = sorted(t.percent_words, key=lambda s: -len(s.split()))
    for phrase in phrases:
        words = phrase.split()
        n = len(words)
        for i in range(len(host.tokens) - n + 1):
            if not _seq_at(host, i, words):
                continue
            pn = _quantity_before(host, i, t)
            if pn is None:
                continue
            start = i - pn.count
            span = _span(host, start, pn.count + n)
            num_text = _quantity_text(pn, t)
            yield Proposal(
                layer=4, cls="percent", op="percent_words",
                span=span, input_text=_text_of(host, span),
                output_text=t.render_percent(num_text),
                value=_signed(pn), unit="%", join=JOIN_WORD)


def grammar_percentage_points(host):
    """'two percentage points' converts the number only; the phrase stays
    words so it can never read as a relative percent change (SEED-02)."""
    t = host.tables
    for phrase in t.pp_words:
        words = phrase.split()
        for i in range(len(host.tokens) - len(words) + 1):
            if not _seq_at(host, i, words):
                continue
            pn = _quantity_before(host, i, t)
            if pn is None:
                continue
            start = i - pn.count
            span = _span(host, start, pn.count + len(words))
            yield Proposal(
                layer=4, cls="percentage_points",
                op="percentage_point_words",
                span=span, input_text=_text_of(host, span),
                output_text=(f"{_quantity_text(pn, t)} "
                             f"{_text_of(host, host.core_span(i, i + len(words)))}"),
                value=_signed(pn), unit="percentage_points",
                join=JOIN_WORD)


def _quantity_before(host, i, t):
    """Parse a quantity ending right before token i, inside the same
    clause (no structural delimiter between its words or before token
    i). None when it is quantified prose ("a few hundred dollars"), the
    tail of a longer number run ("three FIFTEEN minute", "point FIVE
    percent"), or does not parse — so no typed grammar rewrites part of
    a phrase it does not own."""
    if i <= 0 or host.brk[i]:
        return None
    best = None
    for back in range(1, min(13, i + 1)):
        if back > 1 and host.brk[i - back + 1]:
            break  # a delimiter inside the would-be quantity
        words = [tk.word for tk in host.tokens[i - back:i]]
        pn = parse_signed_quantity(words, t)
        if pn is not None and pn.count == back:
            best = pn
    if best is None:
        return None
    start = i - best.count
    first = start + (1 if host.tokens[start].word in t.sign_words else 0)
    if _quantified(host, first) or _juxtaposed_before(host, start):
        return None
    return best


def grammar_currency(host):
    """Number phrase + currency word → symbol form when the locale has a
    symbol for it; otherwise digits keep the currency word (S10)."""
    t = host.tables
    for i, tok in enumerate(host.tokens):
        cur = tok.word
        if cur not in t.currency_words:
            continue
        pn = _quantity_before(host, i, t)
        if pn is None:
            continue
        start = i - pn.count
        span = _span(host, start, pn.count + 1)
        num = _quantity_text(pn, t)
        symbol = t.currency_words.get(cur)
        if symbol and t.currency_before:
            out = f"{symbol}{num}"
        elif symbol:
            out = f"{num}{symbol}"
        else:
            out = f"{num} {cur}"
        yield Proposal(
            layer=4, cls="currency", op="currency_words",
            span=span, input_text=_text_of(host, span),
            output_text=out, value=_signed(pn),
            unit=t.currency_codes.get(cur, cur), join=JOIN_WORD)


# A spoken clock time almost always follows one of these ("the meeting
# is at five thirty"). Without one, an hour+minute word pair is likelier
# an ordinal or count context ("chapter five thirty two") and stays
# prose.
TIME_PREVIOUS = {
    "at", "by", "around", "before", "after", "until", "till", "near",
    "past", "from", "for", "about", "starting", "begins",
}


def grammar_time(host):
    """'five thirty PM' → '5:30 PM'. The meridiem is kept only when
    spoken; no timezone or AM/PM is ever invented (S10).

    Time ownership needs EVIDENCE (M04-AUDIT-06): a time preposition
    right before the hour ("at five thirty") or a spoken meridiem
    ("five thirty PM"). Utterance start alone is not evidence ("three
    fifteen minute breaks", "one oh five"), and an hour+minute pair
    followed by a duration unit is a count plus a duration, never a
    clock time ("for three fifteen minute breaks")."""
    t = host.tables
    meridiems = host.profile.get("time_words", {})
    units = host.profile.get("dimension_units", {})
    durations = {w for w, sym in units.items()
                 if sym in ("s", "min", "h", "d", "wk")}
    i = 0
    while i < len(host.tokens) - 1:
        hour_tok = host.tokens[i]
        prev = _word_at(host, i - 1)
        anchored = i > 0 and not host.brk[i] and prev in TIME_PREVIOUS
        if i > 0 and not anchored and not host.brk[i] \
                and _num_like(host, i - 1):
            i += 1  # inside a longer number run
            continue
        hour = _single_small_number(hour_tok.word, t)
        if hour is None or not 1 <= hour <= 12 or host.brk[i + 1]:
            i += 1
            continue
        minute, mcount = _minute_parse(host, i + 1, t)
        if minute is None or minute < 1:
            i += 1
            continue
        end = i + 1 + mcount
        suffix = ("", 0)
        if end < len(host.tokens) and not host.brk[end]:
            suffix = _meridiem_at(host, end, meridiems)
        if not suffix[0]:
            if not anchored:
                i += 1
                continue
            if end < len(host.tokens) and not host.brk[end] \
                    and (_word_at(host, end) in durations
                         or _num_like(host, end)):
                i += 1  # "for three fifteen minute breaks"
                continue
        else:
            end += suffix[1]
        span = _span(host, i, end - i)
        clock = f"{hour}:{minute:02d}"
        yield Proposal(
            layer=4, cls="time", op="time_words",
            span=span, input_text=_text_of(host, span),
            output_text=f"{clock}{suffix[0]}",
            value=f"{clock}{suffix[0].strip()}",
            unit="clock_time", join=JOIN_WORD)
        i = end if end > i + 1 else i + 1


def _meridiem_at(host, end, meridiems):
    """(suffix like ' PM', tokens consumed) at token index end."""
    w = _word_at(host, end)
    w2 = _word_at(host, end + 1) if host.connected(end, end + 2) else None
    if w is None:
        return "", 0
    pair = f"{w} {w2}" if w2 else None
    if pair in meridiems:
        return f" {meridiems[pair]}", 2
    if w in meridiems:
        return f" {meridiems[w]}", 1
    return "", 0


def _single_small_number(w: str, t: LocaleTables):
    if w in t.units:
        return t.units[w]
    if w in t.teens:
        return t.teens[w]
    if w in t.tens:
        return t.tens[w]
    return None


def _minute_parse(host, i, t):
    """Minutes 1..59 as spoken: 'oh five', 'thirty', 'thirty five',
    'fifteen'. A bare single unit ('five five') is NOT a minute — that
    shape belongs to phone/code digit runs, so a unit only counts after
    'oh'/'o' or as tens/teens."""
    tokens = host.tokens
    w = tokens[i].word
    joined = i + 1 < len(tokens) and not host.brk[i + 1]
    if w in ("oh", "o"):
        if joined and tokens[i + 1].word in t.units:
            v = t.units[tokens[i + 1].word]
            return (v, 2) if 1 <= v <= 59 else (None, 0)
        return None, 0
    if w in t.teens:
        v = t.teens[w]
        return (v, 1) if 1 <= v <= 59 else (None, 0)
    if w in t.tens:
        if joined and tokens[i + 1].word in t.units \
                and t.connector in (None, "and", "y"):
            v = t.tens[w] + t.units[tokens[i + 1].word]
            return (v, 2) if 1 <= v <= 59 else (None, 0)
        v = t.tens[w]
        return (v, 1) if 1 <= v <= 59 else (None, 0)
    return None, 0


def _optional_year(host, end, t):
    """(year|None, tokens_consumed) for a spoken year at token index
    end ("march fourth twenty twenty six"), same clause only."""
    if end >= len(host.tokens) or host.brk[end]:
        return None, 0
    ywords = host.words(end, 6)
    if not ywords:
        return None, 0
    y = parse_year(ywords, t)
    if y is None:
        return None, 0
    yc = _year_count(ywords, t, y)
    if not yc:
        return None, 0
    return y, yc


# Days per month for the NARROW calendar check (design D1): a day past
# the month's maximum is refused; February allows 29 unless a spoken
# year makes it a non-leap year. Nothing else about calendars (weekday,
# era, relative dates) is inferred.
_MONTH_DAYS = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31,
               9: 30, 10: 31, 11: 30, 12: 31}


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _date_refusal(month, day, year):
    """None when the (month, day[, year]) triple can exist; else the
    review reason."""
    if not 1 <= day <= _MONTH_DAYS[month]:
        return "invalid_day"
    if year is not None and month == 2 and day == 29 and not _leap(year):
        return "invalid_date"
    return None


def _month_evidence(host, i) -> bool:
    """A month word that is also an ordinary word ("may", "march",
    "august") names a month only with evidence: its written
    capitalization or a date preposition right before it ("on march
    fourth"). "this may first require approval" stays prose
    (M04-AUDIT-07)."""
    t = host.tables
    tok = host.tokens[i]
    if tok.word not in t.ambiguous_months:
        return True
    if tok.core[:1].isupper():
        return True
    return i > 0 and not host.brk[i] and \
        _word_at(host, i - 1) in t.date_previous


def grammar_date(host):
    """Unambiguous month-name dates: 'March fourth' → 'March 4', optional
    spoken year; 'the fourth of March' / 'el cuatro de marzo' render per
    locale. Numeric dates are never touched. An impossible day (March
    thirty second, February thirty first) is flagged as a whole, never
    shortened to a valid-looking prefix."""
    t = host.tables
    for i, tok in enumerate(host.tokens):
        if tok.word not in t.months or not tok.is_word:
            continue
        month = t.months[tok.word]
        j = i + 1
        if j >= len(host.tokens) or host.brk[j]:
            continue
        day, dcount = _day_parse(host, j, t)
        if day is None or not dcount:
            continue
        end = j + dcount
        year, yc = _optional_year(host, end, t)
        refusal = _date_refusal(month, day, year) if 1 <= day <= 31 \
            else "invalid_day"
        if refusal is not None:
            # "March thirty two" — flagged, never repaired (S10 dates).
            stop = end + (yc if year is not None
                          and refusal == "invalid_date" else 0)
            span = _span(host, i, stop - i)
            yield Proposal(
                layer=4, cls="date", op="date_words",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None, reason=refusal,
                review=True)
            continue
        if not _month_evidence(host, i):
            span = _span(host, i, end - i)
            yield Proposal(
                layer=4, cls="date", op="date_words",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None,
                reason="ambiguous_month_word", review=True)
            continue
        if year is not None:
            end += yc
        span = _span(host, i, end - i)
        out = _render_date(host, i, month, day, year)
        yield Proposal(
            layer=4, cls="date", op="date_words",
            span=span, input_text=_text_of(host, span),
            output_text=out,
            value=(f"{year:04d}-{month:02d}-{day:02d}" if year
                   else f"{month:02d}-{day:02d}"),
            unit="date", join=JOIN_WORD)


def grammar_date_day_first(host):
    """"the fourth of March" (en) / "el cuatro de marzo" (es)."""
    t = host.tables
    for i in range(len(host.tokens)):
        if i > 0 and not host.brk[i] and _num_like(host, i - 1):
            continue
        day, dcount = _day_parse(host, i, t)
        if day is None or not 1 <= day <= 31 or not dcount:
            continue
        j = i + dcount
        if j + 1 >= len(host.tokens) or not host.connected(i, j + 2):
            continue
        if _word_at(host, j) not in ("of", "de"):
            continue
        m_idx = j + 1
        mword = _word_at(host, m_idx)
        if mword not in t.months:
            continue
        month = t.months[mword]
        end = m_idx + 1
        year, yc = _optional_year(host, end, t)
        refusal = _date_refusal(month, day, year)
        if refusal is not None:
            stop = end + (yc if year is not None
                          and refusal == "invalid_date" else 0)
            span = _span(host, i, stop - i)
            yield Proposal(
                layer=4, cls="date", op="date_words",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None, reason=refusal, review=True)
            continue
        if year is not None:
            end += yc
        span = _span(host, i, end - i)
        out = _render_date(host, m_idx, month, day, year)
        yield Proposal(
            layer=4, cls="date", op="date_words",
            span=span, input_text=_text_of(host, span),
            output_text=out,
            value=(f"{year:04d}-{month:02d}-{day:02d}" if year
                   else f"{month:02d}-{day:02d}"),
            unit="date", join=JOIN_WORD)


def _day_parse(host, i, t):
    """Day-of-month as spoken: an ordinal ("fourth"), a compound
    tens-ordinal ("twenty third" = 23), a 1-2 word cardinal
    ("twenty six") or article-prefixed ("the fourth", "el cuatro").
    Returns (value, count) — the caller validates the day and rejects
    (never repairs) an impossible one. A tens word followed by an
    ordinal is ONE compound day even when it is out of range ("thirty
    second" = 32): it is never shortened to its valid prefix "thirty"
    (M04-AUDIT-07)."""
    tokens = host.tokens
    if i >= len(tokens):
        return None, 0
    w = tokens[i].word
    joined = i + 1 < len(tokens) and not host.brk[i + 1]
    if w in ("the", "el", "la"):
        if not joined:
            return None, 0
        day, c = _day_parse(host, i + 1, t)
        return (day, c + 1) if day is not None else (None, 0)
    if w in t.ordinal_words:
        return t.ordinal_words[w], 1
    # "twenty third" / "thirty first" — tens word plus ordinal unit.
    if w in t.tens and joined and tokens[i + 1].word in t.ordinal_words:
        return t.tens[w] + t.ordinal_words[tokens[i + 1].word], 2
    words = [w]
    if joined and _is_num_word(tokens[i + 1].word, t):
        words.append(tokens[i + 1].word)
    card = parse_cardinal(words, t)
    if card is not None and 1 <= card[0] <= 99:
        return card[0], card[1]
    return None, 0


def _year_count(words, t, year):
    """Tokens parse_year consumed (full cardinal, or split halves)."""
    card = parse_cardinal(words, t)
    if card and card[0] == year:
        return card[1]
    for split in range(1, len(words)):
        a = parse_cardinal(words[:split], t)
        b = parse_cardinal(words[split:], t)
        if a and b and a[1] == split and b[1] == len(words) - split:
            a_v, b_v = a[0], b[0]
            if 0 <= a_v <= 99 and 0 <= b_v <= 99 \
                    and 100 * a_v + b_v == year:
                return split + b[1]
    return 0


def _month_display(host, i) -> str:
    """Month rendering: capitalized for en, lowercase for es (each
    locale's written convention)."""
    raw = host.tokens[i].core
    if host.tables.date_rendering == "day_de_month":
        return raw.lower()
    return raw.capitalize()


def _render_date(host, month_idx, month, day, year):
    if host.tables.date_rendering == "day_de_month":
        m = host.tokens[month_idx].core.lower()
        return (f"{day} de {m} de {year}" if year
                else f"{day} de {m}")
    m = _month_display(host, month_idx)
    return f"{m} {day}, {year}" if year else f"{m} {day}"


def grammar_code(host):
    """Anchored digit runs keep order and leading zeros ("code zero zero
    seven three" → "code 0073"). One linking "is" may sit between the
    anchor and the run ("the code is one zero zero zero one")."""
    t = host.tables
    anchors = set(host.profile.get("code_anchors", []))
    for i, tok in enumerate(host.tokens):
        if tok.word not in anchors:
            continue
        j = i + 1
        if j < len(host.tokens) and not host.brk[j] \
                and _word_at(host, j) == "is":
            j += 1
        if j >= len(host.tokens) or host.brk[j]:
            continue
        run = parse_digit_run(host.words(j, 16), t, min_len=2)
        if run is None:
            continue
        digits, count = run
        span = _span(host, j, count)
        yield Proposal(
            layer=4, cls="code", op="digit_run_code",
            span=span, input_text=_text_of(host, span),
            output_text=digits, value=digits, join=JOIN_WORD)


def grammar_phone(host):
    """Ten bare digit words → locale groups; explicit separator words
    ("dash") between digit groups join with '-'. No country code is
    invented."""
    t = host.tables
    seps = set(host.profile.get("phone_separators", ["dash"]))
    i = 0
    tokens = host.tokens
    while i < len(tokens):
        run = parse_digit_run(host.words(i, 12), t, min_len=1)
        if run is None or run[1] < 2:
            i += 1
            continue
        first, count = run
        j = i + count
        groups = [first]
        while j < len(tokens) and not host.brk[j] \
                and _word_at(host, j) in seps \
                and j + 1 < len(tokens) and not host.brk[j + 1]:
            nxt = parse_digit_run(host.words(j + 1, 11), t, min_len=1)
            if nxt is None:
                break
            groups.append(nxt[0])
            j += 1 + nxt[1]
        total_digits = sum(len(g) for g in groups)
        span = _span(host, i, j - i)
        if len(groups) == 1 and total_digits == 10:
            out = _group_phone(first, t)
        elif len(groups) > 1 and 7 <= total_digits <= 11:
            out = "-".join(groups)
        else:
            i = j
            continue
        yield Proposal(
            layer=4, cls="phone", op="digit_run_phone",
            span=span, input_text=_text_of(host, span),
            output_text=out, value=out.replace("-", ""),
            join=JOIN_WORD)
        i = j


def _group_phone(digits: str, t: LocaleTables) -> str:
    parts, rest = [], digits
    for size in t.phone_groups:
        if not rest:
            break
        parts.append(rest[:size])
        rest = rest[size:]
    if rest:
        parts.append(rest)
    return "-".join(parts)


def grammar_version(host):
    """Anchored dotted versions ("version one point two six point four" →
    "version 1.26.4"). Components validate as versions, not decimals."""
    t = host.tables
    anchors = set(host.profile.get("version_anchors", []))
    for i, tok in enumerate(host.tokens):
        if tok.word not in anchors or i + 1 >= len(host.tokens) \
                or host.brk[i + 1]:
            continue
        j = i + 1
        comps = []
        ok = True
        words = host.words(j, 20)
        # first component
        comp, c = _version_component(words, t)
        if comp is None:
            continue
        comps.append(comp)
        used = c
        while True:
            rest = words[used:]
            if not rest or rest[0] not in t.decimal_words:
                break
            comp, c = _version_component(rest[1:], t)
            if comp is None:
                ok = False
                break
            comps.append(comp)
            used += 1 + c
        if len(comps) < 2:
            continue
        span = _span(host, i, 1 + used)
        if not ok or any(int(c) > 999 for c in comps if c.isdigit()):
            yield Proposal(
                layer=4, cls="version", op="version_words",
                span=span, input_text=_text_of(host, span),
                output_text=".".join(comps), value=None,
                reason="invalid_version", review=True)
            continue
        yield Proposal(
            layer=4, cls="version", op="version_words",
            span=span, input_text=_text_of(host, span),
            output_text=f"{tok.core} {'.'.join(comps)}",
            value=".".join(comps), unit="version", join=JOIN_WORD)


def _version_component(words, t):
    """One version component: a cardinal ('twelve') or a digit run
    ('two six' → '26', leading zeros preserved). The longer grammatical
    parse wins, so 'two thousand' is the invalid component 2000, not 2."""
    card = parse_cardinal(words, t)
    run = parse_digit_run(words, t, min_len=1)
    if run is None and card is None:
        return None, 0
    if run is not None and (card is None or run[1] > card[1]):
        return run[0], run[1]
    if card is not None and 0 <= card[0] <= 999:
        return str(card[0]), card[1]
    if card is not None:
        return str(card[0]), card[1]  # caller validates the bound
    return None, 0


def grammar_ip(host):
    """Four octets separated by spoken 'dot' ("one ninety two dot one
    sixty eight dot one dot ten" → 192.168.1.10). Invalid octets are
    flagged, never repaired; a dotted chain of any other arity is owned
    by grammar_numeric_chains. The spoken octet separator is 'dot' in
    every locale this grammar supports (es fixtures do not cover IPs)."""
    t = host.tables
    tokens = host.tokens
    for i in range(len(tokens)):
        # A match may not start mid-phrase: if the previous token is a
        # number word, an earlier (possibly invalid) match owns this run.
        if i > 0 and not host.brk[i] and _num_like(host, i - 1):
            continue
        comp, c, valid = _ip_component(host, i, t)
        if comp is None:
            continue
        j = i + c
        comps = [(comp, valid)]
        while len(comps) < 4 and j + 1 < len(tokens) \
                and not host.brk[j] and not host.brk[j + 1] \
                and _word_at(host, j) == "dot":
            comp2, c2, valid2 = _ip_component(host, j + 1, t)
            if comp2 is None:
                break
            comps.append((comp2, valid2))
            j += 1 + c2
        if len(comps) != 4:
            continue
        span = _span(host, i, j - i)
        values = [c_ for c_, v in comps]
        if all(v for _, v in comps):
            yield Proposal(
                layer=4, cls="ip", op="ip_words",
                span=span, input_text=_text_of(host, span),
                output_text=".".join(values), value=".".join(values),
                unit="ipv4", join=JOIN_WORD)
        else:
            yield Proposal(
                layer=4, cls="ip", op="ip_words",
                span=span, input_text=_text_of(host, span),
                output_text=".".join(values), value=None,
                reason="invalid_octet", review=True)


def _ip_component(host, i, t):
    """IP octet as spoken: digit run ('two five five'), unit+tens
    ('one ninety two' → 192) or a plain cardinal ('ten')."""
    words = host.words(i, 4)
    run = parse_digit_run(words, t, min_len=1)
    if run is not None and run[1] >= 2:
        v = int(run[0])
        return str(v), run[1], v <= 255
    if len(words) >= 2 and words[0] in t.units and t.units[words[0]] >= 1 \
            and (words[1] in t.tens or words[1] in t.teens):
        hi = t.units[words[0]]
        lo = (t.tens.get(words[1]) or t.teens.get(words[1], 0))
        if len(words) >= 3 and words[2] in t.units and words[1] in t.tens:
            lo += t.units[words[2]]
            v = 100 * hi + lo
            return str(v), 3, v <= 255
        v = 100 * hi + lo
        return str(v), 2, v <= 255
    card = parse_cardinal(words, t)
    if card is not None and 0 <= card[0] <= 999:
        return str(card[0]), card[1], card[0] <= 255
    return None, 0, False


def grammar_port(host):
    """"port eight thousand" → "port 8000". The anchor list is
    profile-driven like every other anchored grammar. The SIGNED value
    is what is validated and recorded: "port negative eighty" or a
    port past 65535 is refused as a whole, never emitted as a valid
    port (M04-AUDIT-05)."""
    anchors = set(host.profile.get("port_anchors", ["port"]))
    for i, tok in enumerate(host.tokens):
        if tok.word not in anchors or i + 1 >= len(host.tokens) \
                or host.brk[i + 1]:
            continue
        pn = _quantity_at(host, i + 1)
        if pn is None or pn.frac_digits is not None:
            continue
        if _juxtaposed_after(host, i + 1 + pn.count):
            continue
        span = _span(host, i + 1, pn.count)
        value = _signed(pn)
        if not (isinstance(value, int) and 1 <= value <= 65535):
            yield Proposal(
                layer=4, cls="port", op="number_word_to_digits",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None, unit="port",
                reason="invalid_port", review=True)
            continue
        yield Proposal(
            layer=4, cls="port", op="number_word_to_digits",
            span=span, input_text=_text_of(host, span),
            output_text=_quantity_text(pn, host.tables),
            value=value, unit="port", join=JOIN_WORD)


def grammar_dimension(host):
    """'ten by twenty centimeters' → '10 × 20 cm' — no unit conversion,
    no rounding; MB/Mb stay distinct. Both components carry their
    spoken sign in the typed value, exactly as rendered."""
    t = host.tables
    units = host.profile.get("dimension_units", {})
    bys = set(host.profile.get("by_words", ["by"]))
    for i in range(len(host.tokens)):
        if host.tokens[i].word not in bys or i + 1 >= len(host.tokens) \
                or host.brk[i + 1]:
            continue
        a = _quantity_before(host, i, t)
        if a is None:
            continue
        pn_b = _quantity_at(host, i + 1)
        if pn_b is None or pn_b.frac_digits is not None:
            continue
        endb = i + 1 + pn_b.count
        if endb >= len(host.tokens) or host.brk[endb]:
            continue
        uword = _word_at(host, endb)
        if uword not in units:
            continue
        sym = units[uword]
        start = i - a.count
        span = _span(host, start, endb + 1 - start)
        out = (f"{_quantity_text(a, t)} × "
               f"{_quantity_text(pn_b, t)} {sym}")
        yield Proposal(
            layer=4, cls="dimension", op="dimension_words",
            span=span, input_text=_text_of(host, span),
            output_text=out,
            value=f"{_signed(a)}x{_signed(pn_b)} {sym}",
            unit=sym, join=JOIN_WORD)


def grammar_unit_number(host):
    """Number + unit word converts the number, keeps the spoken unit
    ("thirty seconds" → "30 seconds"); the canonical symbol is carried in
    the edit's unit field (MB vs Mb recorded even when words remain)."""
    t = host.tables
    units = host.profile.get("dimension_units", {})
    for i, tok in enumerate(host.tokens):
        if tok.word not in units:
            continue
        pn = _quantity_before(host, i, t)
        if pn is None or pn.frac_digits is not None:
            continue
        start = i - pn.count
        span = _span(host, start, pn.count)
        yield Proposal(
            layer=4, cls="unit_number", op="number_word_to_digits",
            span=span, input_text=_text_of(host, span),
            output_text=_quantity_text(pn, t),
            value=_signed(pn), unit=units[tok.word],
            join=JOIN_WORD)


ALL_NUMERIC_GRAMMARS = (
    grammar_integer,
    grammar_anchored_integer,
    grammar_decimal,
    grammar_numeric_chains,
    grammar_malformed_quantity,
    grammar_percent,
    grammar_percentage_points,
    grammar_currency,
    grammar_time,
    grammar_date,
    grammar_date_day_first,
    grammar_code,
    grammar_phone,
    grammar_version,
    grammar_ip,
    grammar_port,
    grammar_dimension,
    grammar_unit_number,
)
