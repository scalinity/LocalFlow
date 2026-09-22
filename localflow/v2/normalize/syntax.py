"""Spoken-syntax grammars: literal escape, slash skills, symbol and
Markdown commands, flags, dotfiles, spoken paths, domains/email and
context-fed identifiers (M04, S10).

Nothing here touches a shell, sends a key or executes anything — every
grammar is a pure text proposal (M04-AC04). Punctuation names fire as
commands only with their guards; ordinary phrases ("the slash
character", "a dash of salt") stay prose.
"""

from __future__ import annotations

from .span_types import (
    JOIN_ATTACH_LEFT,
    JOIN_ATTACH_RIGHT,
    JOIN_WORD,
    Proposal,
    ProtectedSpan,
    Span,
)

# Words that cannot be an email/domain local part or host name.
_NAME_STOPWORDS = {
    "the", "a", "an", "he", "she", "it", "they", "we", "you", "i",
    "and", "or", "but", "at", "dot", "this", "that", "is", "was",
}
_ESCAPE_MAX_WORDS = 12


def _text_of(host, span: Span) -> str:
    return host.text[span.start:span.end]


def _word_at(host, idx):
    if 0 <= idx < len(host.tokens):
        return host.tokens[idx].word
    return None


# ---------------------------------------------------------------------------
# Layer 1: literal escape ("write the word slash" → drop the marker, keep
# the object literally). Quoted instructions are content, not escapes.
# ---------------------------------------------------------------------------

def find_literal_escapes(host):
    """Yields (marker-drop Proposal, ProtectedSpan for the object).

    "write the word X" protects exactly one word; "write the words/phrase
    X…" protects up to the next sentence punctuation. The object words are
    emitted verbatim (SEED-08/12).
    """
    pats = host.profile.get("escape_patterns", [])
    tokens = host.tokens
    i = 0
    while i < len(tokens):
        matched = _match_escape_pattern(host, i, pats)
        if matched is None:
            i += 1
            continue
        plen, single = matched
        obj_i = i + plen
        if obj_i >= len(tokens) or not tokens[obj_i].is_word:
            i += 1
            continue
        span_all = Span(tokens[i].start, tokens[obj_i].start)
        if host.in_quote_zone(span_all):
            # A quoted instruction about editing words is content (S10).
            i += plen
            continue
        if single:
            obj_end = tokens[obj_i].end
        else:
            j = obj_i
            while (j < len(tokens) and tokens[j].is_word
                   and j - obj_i < _ESCAPE_MAX_WORDS):
                j += 1
            if j == obj_i:
                i += 1
                continue
            obj_end = tokens[j - 1].end
        marker = Proposal(
            layer=1, cls="literal_escape", op="escape_marker_drop",
            span=span_all, input_text=_text_of(host, span_all),
            output_text="", value=None, join=JOIN_WORD)
        zone = ProtectedSpan(span=Span(tokens[obj_i].start, obj_end),
                             kind="literal_escape")
        yield marker, zone
        i = obj_i + 1


def _match_escape_pattern(host, i, pats):
    """(pattern word count, single_word_object) when tokens[i:] starts an
    escape pattern, else None."""
    for pat in pats:
        words = pat.split()
        if [_word_at(host, i + k) for k in range(len(words))] == words:
            return len(words), words[-1] == "word"
    return None


# ---------------------------------------------------------------------------
# Layer 2 helper: quote zones (command grammars stay out of quotes).
# ---------------------------------------------------------------------------

def find_quote_zones(host) -> list[ProtectedSpan]:
    """Paired-quote spans; command grammars stay out of quoted speech
    (S10: quoted instructions about editing words are content). An
    apostrophe between letters never opens a zone."""
    closers = {"“": "”", "\"": "\"", "«": "»"}
    zones = []
    open_pos = None
    open_ch = None
    for ch_i, ch in enumerate(host.text):
        if open_pos is None:
            if ch not in closers:
                continue
            if ch == "\"":
                prev = host.text[ch_i - 1] if ch_i else ""
                if prev and (prev.isalpha() or prev == "'"):
                    continue  # apostrophe, not an opening quote
            open_pos, open_ch = ch_i, ch
        elif ch == closers[open_ch]:
            if ch == "\"" and ch_i + 1 < len(host.text) \
                    and host.text[ch_i + 1].isalpha() and \
                    not host.text[ch_i - 1:ch_i].isspace():
                continue  # straight quote glued to a word on both sides
            zones.append(ProtectedSpan(
                span=Span(open_pos + 1, ch_i), kind="quoted"))
            open_pos, open_ch = None, None
    return zones


# ---------------------------------------------------------------------------
# Layer 3: registered slash skills — exact spelling only.
# ---------------------------------------------------------------------------

def grammar_skills(host):
    """"slash brainstorm" → "/brainstorm" for a REGISTERED skill or alias
    (exact spelling, multiword aliases map to exact hyphenated names).
    Unknown skill words stay literal and surface as a review suggestion
    (never applied). Ordinary slash prose never converts (AC06)."""
    skills = host.policy.registered_skills or {}
    if not skills:
        return
    aliases = sorted(skills.keys(), key=lambda a: -len(a.split()))
    for i, tok in enumerate(host.tokens):
        if tok.word != "slash" or not tok.is_word:
            continue
        for alias in aliases:
            words = alias.split()
            seq = [_word_at(host, i + 1 + k) for k in range(len(words))]
            if seq != words:
                continue
            exact = skills[alias]
            span = Span(tok.start,
                        host.tokens[i + len(words)].end)
            yield Proposal(
                layer=3, cls="skill", op="slash_skill_token",
                span=span, input_text=_text_of(host, span),
                output_text=f"/{exact}", value=exact, unit="skill_token",
                join=JOIN_WORD)
            break
        else:
            nxt = _word_at(host, i + 1)
            if nxt and host.tokens[i + 1].is_word:
                # Never applied — retained as a review suggestion so a
                # reviewer can see the command intent was considered.
                span = Span(tok.start, host.tokens[i + 1].end)
                yield Proposal(
                    layer=3, cls="skill", op="slash_skill_token",
                    span=span, input_text=_text_of(host, span),
                    output_text=f"/{nxt}", value=nxt, unit="skill_token",
                    reason="unknown_skill", review=True)


# ---------------------------------------------------------------------------
# Layer 4: symbols, Markdown commands, flags, dotfiles, paths,
# domains/email.
# ---------------------------------------------------------------------------

def _phrase_tables(host, table):
    """Multiword phrase table sorted longest-first: [(words, spec)]."""
    out = []
    for phrase, spec in (table or {}).items():
        out.append((phrase.split(), spec))
    out.sort(key=lambda p: -len(p[0]))
    return out


def _guard_blocks(host, i, name_words, always=False):
    g = host.profile.get("symbol_guards", {}) if host.profile else {}
    prev = _word_at(host, i - 1)
    nxt = _word_at(host, i + len(name_words))
    joined = " ".join(name_words)
    guarded = always or joined in g.get("guarded_names", [])
    if guarded:
        if prev in g.get("article_words", []):
            return True
        if nxt in g.get("blocker_next", []):
            return True
        if prev in g.get("blocker_prev", []):
            return True
        if prev in host.tables.ordinal_words and \
                joined in g.get("ordinal_previous", []):
            return True
    return False


def grammar_symbols(host):
    """Spoken punctuation/symbol names → the symbol, with article/idiom
    guards ("a dash of salt", "the period of adjustment" stay prose)."""
    if not host.profile.get("punctuation_commands"):
        return
    for words, spec in _phrase_tables(host, host.profile.get("symbols")):
        n = len(words)
        for i in range(len(host.tokens) - n + 1):
            seq = [tk.word for tk in host.tokens[i:i + n]]
            if seq != words or not all(tk.is_word for tk in
                                       host.tokens[i:i + n]):
                continue
            if _guard_blocks(host, i, words):
                continue
            span = Span(host.tokens[i].start, host.tokens[i + n - 1].end)
            join = spec.get("join", JOIN_WORD)
            yield Proposal(
                layer=4, cls="symbol", op="symbol_command",
                span=span, input_text=_text_of(host, span),
                output_text=spec["out"], value=spec["out"],
                unit="symbol", join=join)


def grammar_markdown(host):
    """Explicit structure commands produce document nodes; nothing turns
    ordinary enumeration prose into structure (S10 Markdown row)."""
    if not host.profile.get("markdown_commands"):
        return
    for words, spec in _phrase_tables(host,
                                      host.profile.get("markdown_commands")):
        n = len(words)
        for i in range(len(host.tokens) - n + 1):
            seq = [tk.word for tk in host.tokens[i:i + n]]
            if seq != words or not all(tk.is_word for tk in
                                       host.tokens[i:i + n]):
                continue
            # "a new bullet point here" / "the new line of the poem"
            # stay prose: article/idiom guards apply to every structure
            # command, not just the guarded symbol names.
            if _guard_blocks(host, i, words, always=True):
                continue
            span = Span(host.tokens[i].start, host.tokens[i + n - 1].end)
            yield Proposal(
                layer=4, cls="markdown", op="markdown_command",
                span=span, input_text=_text_of(host, span),
                output_text=spec["out"], value=words[0],
                unit="markdown", join=spec.get("join", "block"))


def grammar_flags(host):
    """Spoken shell flags: "dash dash verbose" → "--verbose", "dash r" →
    "-r". Emission is text only — nothing executes (AC04)."""
    if not host.profile.get("flag_commands"):
        return
    tokens = host.tokens
    for i, tok in enumerate(tokens):
        if tok.word != "dash" or not tok.is_word:
            continue
        w1 = _word_at(host, i + 1)
        if w1 == "dash":
            w2 = _word_at(host, i + 2)
            if w2 and tokens[i + 2].is_word and len(w2) > 1 and \
                    w2.isalpha() and not _guard_blocks(host, i, ["dash"]):
                span = Span(tok.start, tokens[i + 2].end)
                yield Proposal(
                    layer=4, cls="flag", op="flag_words",
                    span=span, input_text=_text_of(host, span),
                    output_text=f"--{w2}", value=f"--{w2}",
                    unit="flag", join=JOIN_WORD)
        elif (w1 and len(w1) == 1 and w1.isalpha()
              and tokens[i + 1].is_word):
            span = Span(tok.start, tokens[i + 1].end)
            yield Proposal(
                layer=4, cls="flag", op="flag_words",
                span=span, input_text=_text_of(host, span),
                output_text=f"-{w1}", value=f"-{w1}",
                unit="flag", join=JOIN_WORD)


def grammar_dotfile(host):
    """"dot env" → ".env" for known dotfile names (SEED-29)."""
    names = set(host.profile.get("dotfile_names", []))
    for i in range(len(host.tokens) - 1):
        if host.tokens[i].word != "dot" or not host.tokens[i].is_word:
            continue
        nxt = host.tokens[i + 1]
        if not nxt.is_word or nxt.word not in names:
            continue
        span = Span(host.tokens[i].start, nxt.end)
        yield Proposal(
            layer=4, cls="path", op="dotfile_words",
            span=span, input_text=_text_of(host, span),
            output_text=f".{nxt.word}", value=f".{nxt.word}",
            unit="dotfile", join=JOIN_WORD)


def grammar_spoken_path(host):
    """Anchored spoken paths: "path slash users slash danny" →
    "/users/danny" — path intent is distinct from an ordinary slash word;
    no filesystem action runs."""
    anchors = set(host.profile.get("path_anchors", []))
    tokens = host.tokens
    for i, tok in enumerate(tokens):
        if tok.word not in anchors or not tok.is_word:
            continue
        j = i + 1
        if _word_at(host, j) != "slash":
            continue
        segs = []
        while _word_at(host, j) == "slash":
            seg = tokens[j + 1] if j + 1 < len(tokens) else None
            if seg is None or not seg.is_word:
                break
            segs.append(seg.word)
            j += 2
        if len(segs) < 2:
            continue
        span = Span(tok.start, tokens[j - 1].end)
        yield Proposal(
            layer=4, cls="path", op="spoken_path_words",
            span=span, input_text=_text_of(host, span),
            output_text="/" + "/".join(segs),
            value="/" + "/".join(segs), unit="path", join=JOIN_WORD)


def grammar_domain_email(host):
    """Spoken dot/at forms become syntax only in address patterns:
    "danny at gmail dot com" → email; "example dot com" → domain, with
    known TLDs. Punctuation and spelling are never invented."""
    tlds = set(host.profile.get("known_tlds", []))
    tokens = host.tokens
    n = len(tokens)
    # email: name at name (dot tld)+
    for i in range(n - 3):
        if not tokens[i].is_word or tokens[i].word in _NAME_STOPWORDS:
            continue
        if _word_at(host, i + 1) != "at" or not tokens[i + 2].is_word \
                or tokens[i + 2].word in _NAME_STOPWORDS:
            continue
        j = i + 3
        if _word_at(host, j) != "dot":
            continue
        tld = _word_at(host, j + 1)
        if tld not in tlds:
            continue
        host_parts = [tokens[i + 2].word, tld]
        j += 2
        while _word_at(host, j) == "dot":
            t2 = _word_at(host, j + 1)
            if t2 not in tlds:
                break
            host_parts.append(t2)
            j += 2
        span = Span(tokens[i].start, tokens[j - 1].end)
        email = f"{tokens[i].word}@{'.'.join(host_parts)}"
        yield Proposal(
            layer=4, cls="email", op="spoken_email_words",
            span=span, input_text=_text_of(host, span),
            output_text=email, value=email, unit="email",
            join=JOIN_WORD)
    # domain: name (dot tld)+ without a preceding "at name"
    for i in range(n - 2):
        if not tokens[i].is_word or tokens[i].word in _NAME_STOPWORDS:
            continue
        if _word_at(host, i + 1) != "dot":
            continue
        tld = _word_at(host, i + 2)
        if tld not in tlds:
            continue
        # Skip when an email proposal already covers this span.
        if _word_at(host, i - 1) == "at":
            continue
        parts = [tokens[i].word, tld]
        j = i + 3
        while _word_at(host, j) == "dot":
            t2 = _word_at(host, j + 1)
            if t2 not in tlds:
                break
            parts.append(t2)
            j += 2
        span = Span(tokens[i].start, tokens[j - 1].end)
        domain = ".".join(parts)
        yield Proposal(
            layer=4, cls="domain", op="spoken_domain_words",
            span=span, input_text=_text_of(host, span),
            output_text=domain, value=domain, unit="domain",
            join=JOIN_WORD)


# ---------------------------------------------------------------------------
# Layer 5: context-supported vocabulary (M05 dictionary snapshot) and
# context-fed identifiers (M06-fed; absent context means no proposal —
# casing conventions are never invented).
# ---------------------------------------------------------------------------

def grammar_identifiers(host):
    mapping = host.context.identifiers if host.context else None
    if not mapping:
        return
    spoken = sorted(mapping.keys(), key=lambda s: -len(s.split()))
    for phrase in spoken:
        words = phrase.lower().split()
        n = len(words)
        for i in range(len(host.tokens) - n + 1):
            seq = [tk.word for tk in host.tokens[i:i + n]]
            if seq != words or not all(tk.is_word for tk in
                                       host.tokens[i:i + n]):
                continue
            # Match token cores so edge punctuation survives (same rule
            # as grammar_vocabulary).
            toks = host.tokens[i:i + n]
            raw = host.text[toks[0].start:toks[-1].end]
            lead = len(raw) - len(raw.lstrip(".,;:!?\"'“”«»()"))
            trail = len(raw) - len(raw.rstrip(".,;:!?\"'“”«»()"))
            span = Span(toks[0].start + lead, toks[-1].end - trail)
            yield Proposal(
                layer=5, cls="identifier", op="context_identifier",
                span=span, input_text=_text_of(host, span),
                output_text=mapping[phrase], value=mapping[phrase],
                unit="identifier", join=JOIN_WORD)


def grammar_vocabulary(host):
    """Scoped dictionary terms (S11): approved aliases → canonical, token
    boundaries only, never substrings. The snapshot already applied scope
    filtering and conflict masking; each proposal carries the approving
    entry id (AC04 attribution). An already-canonical span emits nothing
    and claims the span, so a shorter overlapping alias cannot rewrite
    inside it on a later pass (idempotence shield). Sits at layer 5:
    literals, protected syntax, skill intent and the typed grammar all
    outrank it. Position-driven lookup by the alias's first word keeps
    this O(tokens × candidates) instead of O(aliases × tokens)."""
    snapshot = getattr(host.context, "vocabulary", None) \
        if host.context else None
    if snapshot is None:
        return
    by_first = snapshot.by_first_word()
    claimed: list[Span] = []
    tokens = host.tokens
    for i, tok in enumerate(tokens):
        candidates = by_first.get(tok.word)
        if not candidates or not tok.is_word:
            continue
        for alias, target in candidates:
            words = alias.split()
            n = len(words)
            if i + n > len(tokens):
                continue
            seq = tokens[i:i + n]
            if [t.word for t in seq] != words or not all(
                    t.is_word for t in seq):
                continue
            # Match the token CORES: edge punctuation attached to a raw
            # token ("code,") is not part of the phrase and must survive.
            raw = host.text[seq[0].start:seq[-1].end]
            lead = len(raw) - len(raw.lstrip(".,;:!?\"'“”«»()"))
            trail = len(raw) - len(raw.rstrip(".,;:!?\"'“”«»()"))
            span = Span(seq[0].start + lead, seq[-1].end - trail)
            text = host.text[span.start:span.end]
            if text == target.canonical:
                # Already canonical: no edit — but CLAIM the span so a
                # shorter overlapping alias cannot rewrite inside it on
                # a later pass ("Status Page" must not drift to "Status
                # Pager"). Candidates iterate longest-first per position.
                claimed.append(span)
                continue
            if any(span.overlaps(c) for c in claimed):
                continue
            yield Proposal(
                layer=5, cls="vocabulary", op="scoped_alias",
                span=span, input_text=text,
                output_text=target.canonical, value=target.canonical,
                unit="term", join=JOIN_WORD,
                reason=target.verification, rule_id=target.entry_id)


ALL_SYNTAX_GRAMMARS = (
    grammar_skills,
    grammar_symbols,
    grammar_markdown,
    grammar_flags,
    grammar_dotfile,
    grammar_spoken_path,
    grammar_domain_email,
)

# Command-shaped classes blocked inside quote zones (numbers still
# convert inside quotes). Vocabulary is blocked there too: a quoted
# literal is content (S11 "do not replace … a quoted literal").
COMMAND_CLASSES = frozenset({
    "skill", "symbol", "markdown", "flag", "path", "domain", "email",
    "vocabulary",
})
