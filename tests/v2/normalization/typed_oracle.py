"""Independent typed-semantics oracle for the M04 fixture suites
(M04-AUDIT-18).

A fixture's ``protected_values`` state the MEANING that must survive
(``{"type": "percent", "value": "12", "unit": "%"}``). This module checks
them against the result's typed edit ledger with its own arithmetic —
Decimal equality, ordered integer components, a 24-hour clock mapping —
never by calling a production grammar or formatter. A value that is
already written in the input (an existing URL, path, IP, "12%") must
appear verbatim in the output instead.

It also checks, for every numeric edit, that the ledger's sign equals
the sign the output text shows: a mutation of the typed value alone
(text unchanged) fails here.

The time mapping is the one documented representation: an edit value
"H:MM" (meridiem unknown) or "H:MMAM"/"H:MMPM" maps to "HH:MM" on a
24-hour clock, keeping the spoken hour when no meridiem was spoken.
"""

from decimal import Decimal, InvalidOperation

NUMERIC_TYPES = {
    # fixture type → acceptable edit classes (None = any numeric class)
    "count": {"integer", "anchored_integer", "unit_number"},
    "decimal": {"decimal"},
    "percent": {"percent"},
    "percentage_points": {"percentage_points"},
    "currency": {"currency"},
    "currency_word": None,
    "data": {"unit_number"},
    "duration": {"unit_number"},
    "port": {"port"},
}
STRING_TYPES = {
    "date": {"date"},
    "code": {"code"},
    "phone": {"phone"},
    "identifier": {"identifier"},
    "skill_token": {"skill"},
    "flag": {"flag"},
    "email": {"email"},
    "domain": {"domain"},
    "dotfile": {"path"},
    "path": {"path"},
}
COMPONENT_TYPES = {"version": {"version"}, "ipv4": {"ip"}}
NUMERIC_EDIT_CLASSES = {
    "integer", "anchored_integer", "unit_number", "decimal", "percent",
    "percentage_points", "currency", "port",
}


def _dec(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def clock_24h(edit_value: str):
    """'5:30PM' → '17:30', '9:05AM' → '09:05', '5:30' → '05:30'."""
    v = str(edit_value)
    mer = None
    for m in ("AM", "PM"):
        if v.endswith(m):
            mer, v = m, v[:-2]
    h, mm = v.split(":")
    h = int(h)
    if mer == "PM" and h < 12:
        h += 12
    if mer == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{int(mm):02d}"


def sign_problems(res):
    """Numeric edits whose ledger sign differs from the rendered sign."""
    out = []
    for e in res.edits:
        if e.cls not in NUMERIC_EDIT_CLASSES:
            continue
        v = _dec(e.value)
        if v is None:
            continue
        shown_neg = e.output_text.lstrip("$€ ").startswith("-")
        if (v < 0) != shown_neg:
            out.append((e.cls, e.output_text, str(e.value)))
    return out


def check(case, res):
    """List of problems (empty = the protected meaning survived)."""
    problems = [("sign", p) for p in sign_problems(res)]
    edits = res.edits
    for pv in case.get("protected_values", []):
        typ, want = pv["type"], str(pv["value"])
        unit = pv.get("unit")
        # Already-written values: must survive verbatim.
        if not edits or (want in case["input_text"]
                         and want in res.text):
            if want in res.text or (typ == "symbol" and all(
                    ch in res.text for ch in want)):
                continue
        ok = False
        if typ in NUMERIC_TYPES:
            classes = NUMERIC_TYPES[typ]
            for e in edits:
                if classes is not None and e.cls not in classes:
                    continue
                if _dec(e.value) is None or _dec(e.value) != Decimal(want):
                    continue
                if typ == "decimal" and str(e.value) != want:
                    continue  # significant zeros are part of the value
                if unit is not None and typ not in ("currency_word",) \
                        and e.unit != unit:
                    continue
                ok = True
        elif typ == "time":
            ok = any(e.cls == "time" and clock_24h(e.value) == want
                     for e in edits)
        elif typ in STRING_TYPES:
            ok = any(e.cls in STRING_TYPES[typ] and str(e.value) == want
                     for e in edits)
        elif typ in COMPONENT_TYPES:
            comps = [int(c) for c in want.split(".")]
            for e in edits:
                if e.cls in COMPONENT_TYPES[typ] and e.value is not None:
                    got = [int(c) for c in str(e.value).split(".")]
                    if got == comps and (typ != "ipv4" or (
                            len(got) == 4
                            and all(0 <= c <= 255 for c in got))):
                        ok = True
        elif typ == "dimension":
            comps = [Decimal(c) for c in want.split("x")]
            for e in edits:
                if e.cls == "dimension" and e.unit == unit:
                    head = str(e.value).split(" ")[0]
                    if [Decimal(c) for c in head.split("x")] == comps:
                        ok = True
        elif typ == "symbol":
            ok = all(any(e.cls == "symbol" and e.value == ch
                         for e in edits) for ch in want)
        elif typ == "markdown":
            ok = any(e.cls == "markdown" for e in edits)
        elif typ == "url":
            ok = want in res.text  # already-written; never spoken
        else:
            problems.append(("unknown_type", typ))
            continue
        if not ok:
            problems.append((typ, want, [(e.cls, str(e.value), e.unit)
                                         for e in edits]))
    return problems
