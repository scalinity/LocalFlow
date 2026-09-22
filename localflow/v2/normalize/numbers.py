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
    """Word tables and rendering rules for one locale."""

    def __init__(self, name: str, data: dict):
        self.name = name
        self.units: dict[str, int] = data["units"]
        self.teens: dict[str, int] = data["teens"]
        self.tens: dict[str, int] = data["tens"]
        self.hundreds_mult: dict[str, int] = data.get("hundreds_mult", {})
        self.hundreds_val: dict[str, int] = data.get("hundreds_val", {})
        self.big_scales: dict[str, int] = {
            k: v for k, v in data.get("big_scales", {}).items()
            if v >= 1000}
        self.connector: str | None = data.get("connector")
        self.connector_states: set[str] = set(
            data.get("connector_states", []))
        self.integer_stop_after: set[str] = {
            *STOP_AFTER_INTEGER, *data.get("integer_stop_after", [])}
        self.sign_words: dict[str, int] = data.get("sign_words", {})
        self.decimal_words: set[str] = set(data.get("decimal_words", []))
        self.percent_words: set[str] = set(data.get("percent_words", []))
        self.pp_words: list[str] = data.get("percentage_point_words", [])
        self.currency_words: dict[str, str] = data.get("currency_words", {})
        self.currency_codes: dict[str, str] = data.get("currency_codes", {})
        self.months: dict[str, int] = data.get("months", {})
        self.ordinal_words: dict[str, int] = data.get("ordinal_words", {})
        self.grouping = data.get("grouping_separator", ",")
        self.decimal_sep = data.get("decimal_separator", ".")
        self.percent_space = data.get("percent_rendering") == "space"
        self.currency_before = data.get("currency_before", True)
        self.date_rendering = data.get("date_rendering", "month_day")
        self.phone_groups: list[int] = data.get("phone_groups", [3, 3, 4])
        self.number_words: set[str] = (
            set(self.units) | set(self.teens) | set(self.tens)
            | set(self.hundreds_mult) | set(self.hundreds_val)
            | set(self.big_scales) | set(self.sign_words)
            | self.decimal_words)

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
    compound cardinal.
    """
    total = 0
    current = 0
    count = 0
    seen = False
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
            current = (current or 1) * t.hundreds_mult[w]
            state = "hundreds"
        elif w in t.big_scales:
            if state == "empty" and not seen:
                break
            total += (current or 1) * t.big_scales[w]
            current = 0
            state = "empty"
        elif w == t.connector and seen and state in t.connector_states \
                and i + 1 < n and _is_num_word(words[i + 1], t):
            pass  # "one hundred and twenty", "treinta y cinco"
        else:
            break
        count += 1
        seen = True
        i += 1
    if not seen:
        return None
    return total + current, count


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
            value = dec
            frac = None  # scaled to an integer-valued quantity
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
    token i. Returns ParsedNumber or None."""
    words = [tok.word for tok in host.tokens[i:i + 14]]
    if not words:
        return None
    return parse_signed_quantity(words, host.tables)


def _quantity_text(pn: ParsedNumber, t: LocaleTables) -> str:
    if pn.frac_digits is not None:
        return t.render_decimal(pn.value * pn.sign, pn.frac_digits)
    return t.group_int(int(pn.value) * pn.sign)


def _span(host, i, count) -> Span:
    return Span(host.tokens[i].start, host.tokens[i + count - 1].end)


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
    is prose, not a count."""
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
        if pn is None or pn.value < 0 or int(pn.value) == 0:
            i += 1
            continue
        end = _end_index(host, i, pn.count)
        nxt = _word_at(host, end)
        if nxt is None or nxt in host.tables.integer_stop_after:
            i += 1
            continue
        if int(pn.value) == 1 and pn.count == 1 \
                and _word_at(host, i - 1) in IDIOM_PREV_ONE:
            i += 1
            continue
        if pn.count == 1 and tok.word in t.hundreds_mult \
                and (_word_at(host, i - 1) or "") in QUANTIFIER_PREV_SCALE:
            i += 1  # "a few hundred people" — quantified prose, not a count
            continue
        if pn.count == 1 and tok.word in t.units \
                and (nxt in t.units
                     or (_word_at(host, i - 1) or "") in t.units):
            i += 1  # inside a spoken digit run (phone/code territory)
            continue
        if pn.count == 1 and (tok.word in t.teens or tok.word in t.tens) \
                and nxt in (t.units | t.teens | t.tens):
            i += 1  # year-speak ("nineteen eighty four") — dates own it
            continue
        if pn.frac_digits is None:
            span = _span(host, i, pn.count)
            out = _quantity_text(pn, host.tables)
            yield Proposal(
                layer=4, cls="integer", op="number_word_to_digits",
                span=span, input_text=_text_of(host, span),
                output_text=out, value=int(pn.value) * pn.sign,
                join=JOIN_WORD)
        # A decimal ("one point two six …") is the decimal grammar's job.
        i += pn.count if pn.count > 1 else 1


def grammar_anchored_integer(host):
    """Technical anchors convert a trailing cardinal ("milestone
    fourteen" → "milestone 14")."""
    anchors = set(host.profile.get("integer_anchors", []))
    for i, tok in enumerate(host.tokens):
        if tok.word not in anchors:
            continue
        j = i + 1
        pn = _quantity_at(host, j)
        if pn is None or pn.frac_digits is not None:
            continue
        span = _span(host, j, pn.count)
        yield Proposal(
            layer=4, cls="anchored_integer", op="number_word_to_digits",
            span=span, input_text=_text_of(host, span),
            output_text=_quantity_text(pn, host.tables),
            value=int(pn.value), join=JOIN_WORD)


def grammar_decimal(host):
    """Sign + cardinal + decimal word + digit run ("minus zero point zero
    five" → "-0.05"). More than one decimal word in the phrase is
    version-speak, not a decimal (see grammar_version)."""
    t = host.tables
    i = 0
    while i < len(host.tokens):
        start = i
        sign = 1
        j = i
        if host.tokens[j].word in t.sign_words:
            sign = t.sign_words[host.tokens[j].word]
            j += 1
        words_ahead = [tk.word for tk in host.tokens[j:j + 14]]
        card = parse_cardinal(words_ahead, t)
        if card is None:
            i += 1
            continue
        value, count = card
        k = j + count
        if _word_at(host, k) not in t.decimal_words:
            i += 1
            continue
        run = parse_digit_run(
            [tk.word for tk in host.tokens[k + 1:k + 14]], t, min_len=1)
        if run is None:
            i += 1
            continue
        frac, dcount = run
        # A second decimal word right after the fraction digits is
        # version-speak ("one point two six point four"), not a decimal.
        consumed = k + 1 + dcount
        if _word_at(host, consumed) in t.decimal_words:
            # Longest version-shaped run: digits/points to the end.
            tail = consumed
            while True:
                nxt_run = parse_digit_run(
                    [tk.word for tk in host.tokens[tail + 1:tail + 14]],
                    t, min_len=1)
                if nxt_run is None:
                    break
                tail += 1 + nxt_run[1]
                if _word_at(host, tail) not in t.decimal_words:
                    break
            span = _span(host, start, tail - start)
            yield Proposal(
                layer=4, cls="version", op="version_words",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None,
                reason="unanchored_version", review=True)
            i = tail
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
            seq = [tk.word for tk in host.tokens[i:i + n]]
            if seq != words:
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
                value=pn.value * pn.sign, unit="%", join=JOIN_WORD)


def grammar_percentage_points(host):
    """'two percentage points' converts the number only; the phrase stays
    words so it can never read as a relative percent change (SEED-02)."""
    t = host.tables
    for phrase in t.pp_words:
        words = phrase.split()
        for i in range(len(host.tokens) - len(words) + 1):
            if [tk.word for tk in host.tokens[i:i + len(words)]] != words:
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
                             f"{_text_of(host, Span(host.tokens[i].start,
                                                   host.tokens[i + len(words) - 1].end))}"),
                value=pn.value * pn.sign, unit="percentage_points",
                join=JOIN_WORD)


def _quantity_before(host, i, t):
    """Parse a quantity ending right before token i. A bare multiplier
    directly after a quantifier word is prose, not a quantity — return
    None so no typed grammar rewrites "a few hundred dollars"."""
    best = None
    for back in range(1, min(13, i + 1)):
        words = [tk.word for tk in host.tokens[i - back:i]]
        pn = parse_signed_quantity(words, t)
        if pn is not None and pn.count == back:
            best = pn
    if best is not None and best.count == 1:
        first = host.tokens[i - 1].word
        prev_idx = i - 2
        if first in t.hundreds_mult and prev_idx >= 0 \
                and host.tokens[prev_idx].word in QUANTIFIER_PREV_SCALE:
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
            output_text=out, value=pn.value * pn.sign,
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
    spoken; no timezone or AM/PM is ever invented (S10)."""
    t = host.tables
    meridiems = host.profile.get("time_words", {})
    i = 0
    while i < len(host.tokens) - 1:
        hour_tok, minute_tok = host.tokens[i], host.tokens[i + 1]
        prev = _word_at(host, i - 1)
        if i > 0 and prev not in TIME_PREVIOUS:
            i += 1
            continue
        hour = _single_small_number(hour_tok.word, t)
        if hour is None or not 1 <= hour <= 12:
            i += 1
            continue
        minute, mcount = _minute_parse(host.tokens, i + 1, t)
        if minute is None or minute < 1:
            i += 1
            continue
        end = i + 1 + mcount
        suffix = _meridiem_at(host, end, meridiems)
        if suffix[0]:
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
    w2 = _word_at(host, end + 1)
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


def _minute_parse(tokens, i, t):
    """Minutes 1..59 as spoken: 'oh five', 'thirty', 'thirty five',
    'fifteen'. A bare single unit ('five five') is NOT a minute — that
    shape belongs to phone/code digit runs, so a unit only counts after
    'oh'/'o' or as tens/teens."""
    w = tokens[i].word
    if w in ("oh", "o"):
        if i + 1 < len(tokens) and tokens[i + 1].word in t.units:
            v = t.units[tokens[i + 1].word]
            return (v, 2) if 1 <= v <= 59 else (None, 0)
        return None, 0
    if w in t.teens:
        v = t.teens[w]
        return (v, 1) if 1 <= v <= 59 else (None, 0)
    if w in t.tens:
        if i + 1 < len(tokens) and tokens[i + 1].word in t.units \
                and t.connector in (None, "and", "y"):
            v = t.tens[w] + t.units[tokens[i + 1].word]
            return (v, 2) if 1 <= v <= 59 else (None, 0)
        v = t.tens[w]
        return (v, 1) if 1 <= v <= 59 else (None, 0)
    return None, 0


def _optional_year(host, end, t):
    """(year|None, tokens_consumed) for a spoken year at token index
    end ("march fourth twenty twenty six")."""
    ywords = [tk.word for tk in host.tokens[end:end + 6]]
    if not ywords:
        return None, 0
    y = parse_year(ywords, t)
    if y is None:
        return None, 0
    yc = _year_count(ywords, t, y)
    if not yc:
        return None, 0
    return y, yc


def grammar_date(host):
    """Unambiguous month-name dates: 'March fourth' → 'March 4', optional
    spoken year; 'the fourth of March' / 'el cuatro de marzo' render per
    locale. Numeric dates are never touched."""
    t = host.tables
    for i, tok in enumerate(host.tokens):
        if tok.word not in t.months:
            continue
        month = t.months[tok.word]
        j = i + 1
        day, dcount = _day_parse(host.tokens, j, t)
        if day is None or not dcount:
            continue
        if not 1 <= day <= 31:
            # "March thirty two" — flagged, never repaired (S10 dates).
            span = _span(host, i, 1 + dcount)
            yield Proposal(
                layer=4, cls="date", op="date_words",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None, reason="invalid_day",
                review=True)
            continue
        end = j + dcount
        year, yc = _optional_year(host, end, t)
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
        day, dcount = _day_parse(host.tokens, i, t)
        if day is None or not 1 <= day <= 31 or not dcount:
            continue
        j = i + dcount
        if _word_at(host, j) not in ("of", "de"):
            continue
        m_idx = j + 1
        mword = _word_at(host, m_idx)
        if mword not in t.months:
            continue
        end = m_idx + 1
        year, yc = _optional_year(host, end, t)
        if year is not None:
            end += yc
        span = _span(host, i, end - i)
        month = t.months[mword]
        out = _render_date(host, m_idx, month, day, year)
        yield Proposal(
            layer=4, cls="date", op="date_words",
            span=span, input_text=_text_of(host, span),
            output_text=out,
            value=(f"{year:04d}-{month:02d}-{day:02d}" if year
                   else f"{month:02d}-{day:02d}"),
            unit="date", join=JOIN_WORD)


def _day_parse(tokens, i, t):
    """Day-of-month as spoken: an ordinal ("fourth"), a compound
    tens-ordinal ("twenty third" = 23), a 1-2 word cardinal
    ("twenty six") or article-prefixed ("the fourth", "el cuatro").
    Returns (value, count) — the caller validates 1..31 and rejects
    (never repairs) out-of-range days."""
    if i >= len(tokens):
        return None, 0
    w = tokens[i].word
    if w in ("the", "el", "la"):
        day, c = _day_parse(tokens, i + 1, t)
        return (day, c + 1) if day is not None else (None, 0)
    if w in t.ordinal_words:
        return t.ordinal_words[w], 1
    # "twenty third" / "thirty first" — tens word plus ordinal unit.
    if w in t.tens and i + 1 < len(tokens) \
            and tokens[i + 1].word in t.ordinal_words:
        v = t.tens[w] + t.ordinal_words[tokens[i + 1].word]
        if 1 <= v <= 31:
            return v, 2
    words = [w]
    if i + 1 < len(tokens) and _is_num_word(tokens[i + 1].word, t):
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
    raw = host.tokens[i].raw
    if host.tables.date_rendering == "day_de_month":
        return raw.lower()
    return raw.capitalize()


def _render_date(host, month_idx, month, day, year):
    if host.tables.date_rendering == "day_de_month":
        m = host.tokens[month_idx].raw.lower()
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
        if _word_at(host, j) == "is":
            j += 1
        run = parse_digit_run(
            [tk.word for tk in host.tokens[j:j + 16]], t, min_len=2)
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
        run = parse_digit_run([tk.word for tk in tokens[i:i + 12]], t,
                              min_len=1)
        if run is None or run[1] < 2:
            i += 1
            continue
        first, count = run
        j = i + count
        groups = [first]
        while _word_at(host, j) in seps:
            nxt = parse_digit_run(
                [tk.word for tk in tokens[j + 1:j + 12]], t, min_len=1)
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
        if tok.word not in anchors:
            continue
        j = i + 1
        comps = []
        count = 0
        ok = True
        words = [tk.word for tk in host.tokens[j:j + 20]]
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
            output_text=f"{tok.raw} {'.'.join(comps)}",
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
    flagged, never repaired. The spoken octet separator is 'dot' in
    every locale this grammar supports (es fixtures do not cover IPs)."""
    t = host.tables
    tokens = host.tokens
    for i in range(len(tokens)):
        # A match may not start mid-phrase: if the previous token is a
        # number word, an earlier (possibly invalid) match owns this run.
        if i > 0 and _is_num_word(tokens[i - 1].word, t):
            continue
        comp, c, valid = _ip_component(tokens, i, t)
        if comp is None:
            continue
        j = i + c
        comps = [(comp, valid)]
        while _word_at(host, j) == "dot" and len(comps) < 4:
            comp2, c2, valid2 = _ip_component(tokens, j + 1, t)
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


def _ip_component(tokens, i, t):
    """IP octet as spoken: digit run ('two five five'), unit+tens
    ('one ninety two' → 192) or a plain cardinal ('ten')."""
    words = [tk.word for tk in tokens[i:i + 4]]
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
    profile-driven like every other anchored grammar."""
    anchors = set(host.profile.get("port_anchors", ["port"]))
    for i, tok in enumerate(host.tokens):
        if tok.word not in anchors:
            continue
        pn = _quantity_at(host, i + 1)
        if pn is None or pn.frac_digits is not None:
            continue
        if not 1 <= int(pn.value) <= 65535:
            continue
        span = _span(host, i + 1, pn.count)
        yield Proposal(
            layer=4, cls="port", op="number_word_to_digits",
            span=span, input_text=_text_of(host, span),
            output_text=_quantity_text(pn, host.tables),
            value=int(pn.value), unit="port", join=JOIN_WORD)


def grammar_dimension(host):
    """'ten by twenty centimeters' → '10 × 20 cm' — no unit conversion,
    no rounding; MB/Mb stay distinct."""
    t = host.tables
    units = host.profile.get("dimension_units", {})
    bys = set(host.profile.get("by_words", ["by"]))
    for i in range(len(host.tokens)):
        if host.tokens[i].word not in bys:
            continue
        a = _quantity_before(host, i, t)
        if a is None:
            continue
        pn_b = _quantity_at(host, i + 1)
        if pn_b is None or pn_b.frac_digits is not None:
            continue
        endb = i + 1 + pn_b.count
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
            value=f"{a.value * a.sign}x{pn_b.value} {sym}",
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
            value=pn.value * pn.sign, unit=units[tok.word],
            join=JOIN_WORD)


ALL_NUMERIC_GRAMMARS = (
    grammar_integer,
    grammar_anchored_integer,
    grammar_decimal,
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
