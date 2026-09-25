"""Spoken-syntax grammars: literal escape, slash skills, symbol and
Markdown commands, flags, dotfiles, spoken paths, domains/email and
context-fed identifiers (M04, S10).

Nothing here touches a shell, sends a key or executes anything — every
grammar is a pure text proposal (M04-AC04). Punctuation names fire as
commands only with their guards; ordinary phrases ("the slash
character", "a dash of salt") stay prose.
"""

from __future__ import annotations

import re

from ..snippets import expand, split_slots
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
    X…" protects the whole run of words up to the next structural
    delimiter (sentence punctuation, a line break, a non-word token) or
    the end of the utterance. The object words are emitted verbatim
    (SEED-08/12). There is no word cap: a bound that stopped protecting
    mid-phrase would expose the tail of a literal the speaker asked for
    (M04-AUDIT-10). A marker INSIDE an escaped object is part of that
    object — it is never processed as a second escape.
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
        if obj_i >= len(tokens) or not tokens[obj_i].is_word \
                or host.brk[obj_i]:
            i += 1
            continue
        span_all = Span(tokens[i].start, tokens[obj_i].start)
        if host.in_quote_zone(span_all):
            # A quoted instruction about editing words is content (S10).
            i += plen
            continue
        j = obj_i + 1
        if not single:
            # every token of the clause — written tokens included
            # ("version 2", "GPT-5"): the marker is dropped, so an
            # early stop would expose the rest of the literal (R8)
            while j < len(tokens) and not host.brk[j]:
                j += 1
        obj_end = tokens[j - 1].end
        marker = Proposal(
            layer=1, cls="literal_escape", op="escape_marker_drop",
            span=span_all, input_text=_text_of(host, span_all),
            output_text="", value=None, join=JOIN_WORD)
        zone = ProtectedSpan(span=Span(tokens[obj_i].start, obj_end),
                             kind="literal_escape")
        yield marker, zone
        i = j


def _match_escape_pattern(host, i, pats):
    """(pattern word count, single_word_object) when tokens[i:] starts an
    escape pattern, else None."""
    for pat in pats:
        words = pat.split()
        if [_word_at(host, i + k) for k in range(len(words))] == words \
                and host.connected(i, i + len(words)):
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


_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def find_code_zones(host) -> list[ProtectedSpan]:
    """Already-written code is protected existing syntax (layer 2): the
    inside of a ``` fence and of an inline `code` span is never
    normalized — "```twelve percent```" is code the speaker (or a
    snippet) wrote, not number speech (M04-AUDIT-10 adjudication)."""
    zones = []
    taken = []
    for m in _CODE_FENCE_RE.finditer(host.text):
        zones.append(ProtectedSpan(span=Span(m.start(), m.end()),
                                   kind="code"))
        taken.append((m.start(), m.end()))
    for m in _INLINE_CODE_RE.finditer(host.text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        zones.append(ProtectedSpan(span=Span(m.start(), m.end()),
                                   kind="code"))
    return zones


# ---------------------------------------------------------------------------
# Layer 3: registered slash skills — exact spelling only.
# ---------------------------------------------------------------------------

def grammar_skills(host):
    """"slash brainstorm" → "/brainstorm" for a REGISTERED skill or alias
    (exact spelling, multiword aliases map to exact hyphenated names).
    Unknown skill words stay literal and surface as a review suggestion
    (never applied). Ordinary slash prose never converts (AC06).

    Registry membership establishes token IDENTITY, not command INTENT
    (M04-AUDIT-01, review R1). A registered token is inserted only in a
    COMMAND POSITION: at the start of a clause ("slash code review",
    "Done. Slash code review the PR") or right after an explicit command
    frame from the profile (``slash_command_frames``: "add", "run",
    "use", "then", "please", "the" …; "to" only after a motion/change
    verb in ``slash_command_frames_to``: "switch to slash code review").
    Anywhere else — after a subject, modal, adverb, noun or "and" ("we
    should really slash code review time", "managers slash costs") —
    "slash" is the ordinary verb: the words stay literal and the
    considered token is retained as a ``no_command_frame`` review
    suggestion. A frame word after a subject pronoun is itself a verb
    ("we do slash costs"), not a frame."""
    skills = host.policy.registered_skills or {}
    if not skills:
        return
    frames = set(host.profile.get("slash_command_frames", ()))
    frames_to = set(host.profile.get("slash_command_frames_to", ()))
    subjects = set(host.profile.get("slash_subject_words", ()))
    aliases = sorted(skills.keys(), key=lambda a: -len(a.split()))
    for i, tok in enumerate(host.tokens):
        if tok.word != "slash" or not tok.is_word:
            continue
        verb = not _command_position(host, i, frames, frames_to, subjects)
        for alias in aliases:
            words = alias.split()
            seq = [_word_at(host, i + 1 + k) for k in range(len(words))]
            if seq != words or not host.connected(i, i + 1 + len(words)) \
                    or not all(host.tokens[i + 1 + k].is_word
                               for k in range(len(words))):
                continue
            exact = skills[alias]
            span = host.core_span(i, i + 1 + len(words))
            if verb:
                yield Proposal(
                    layer=3, cls="skill", op="slash_skill_token",
                    span=span, input_text=_text_of(host, span),
                    output_text=f"/{exact}", value=exact,
                    unit="skill_token", reason="no_command_frame",
                    review=True)
                break
            yield Proposal(
                layer=3, cls="skill", op="slash_skill_token",
                span=span, input_text=_text_of(host, span),
                output_text=f"/{exact}", value=exact, unit="skill_token",
                join=JOIN_WORD)
            break
        else:
            nxt = _word_at(host, i + 1)
            if nxt and host.tokens[i + 1].is_word and not host.brk[i + 1]:
                # Never applied — retained as a review suggestion so a
                # reviewer can see the command intent was considered.
                span = host.core_span(i, i + 2)
                yield Proposal(
                    layer=3, cls="skill", op="slash_skill_token",
                    span=span, input_text=_text_of(host, span),
                    output_text=f"/{nxt}", value=nxt, unit="skill_token",
                    reason="unknown_skill", review=True)


def _command_position(host, i, frames, frames_to, subjects) -> bool:
    """Token i opens a command: clause start, or an explicit frame."""
    if i == 0 or host.brk[i]:
        return True
    prev = _word_at(host, i - 1)
    prev2 = _word_at(host, i - 2) if i >= 2 and not host.brk[i - 1] \
        else None
    if prev == "to":
        return prev2 in frames_to
    if prev in frames:
        return prev2 not in subjects
    return False


def grammar_snippets(host):
    """Registered snippet intent (S17, M10): an explicit spoken trigger
    expands to its exact stored content, placeholders filled from the
    continuation words (split on the spoken separator). Layer 3 — the
    literal escape and quote zones still outrank/block it, and a
    trigger colliding with a registered skill on the same span loses
    to the same-span ambiguity rule (both stay literal). A placeholder
    continuation longer than ``_SNIPPET_SLOT_WORD_CAP`` words reads as
    prose, not intent: no expansion, words stay literal."""
    snapshot = getattr(host.context, "snippets", None) \
        if host.context else None
    if snapshot is None:
        return
    by_first = snapshot.by_first_word()
    tokens = host.tokens
    for i, tok in enumerate(tokens):
        candidates = by_first.get(tok.word)
        if not candidates or not tok.is_word:
            continue
        for trig, snippet in candidates:
            words = trig.split()
            n = len(words)
            seq = tokens[i:i + n]
            if [t.word for t in seq] != words or not all(
                    t.is_word for t in seq):
                continue
            placeholders = snippet.placeholders
            if not placeholders:
                span = Span(tok.start, tokens[i + n - 1].end)
                yield Proposal(
                    layer=3, cls="snippet", op="snippet_expansion",
                    span=span, input_text=_text_of(host, span),
                    output_text=expand(snippet),
                    value=snippet.snippet_id, unit="snippet",
                    join=JOIN_WORD, rule_id=snippet.snippet_id)
                break
            # Slot continuation: the maximal word-token run after the
            # trigger, to the end of the utterance. Values keep their
            # spoken casing (the token's raw form, edge punctuation
            # stripped) — a signature slot must not decapitalize a name.
            j = i + n
            while j < len(tokens) and tokens[j].is_word:
                j += 1
            cont = [(t.raw.strip(".,;:!?\"'“”«»()") or t.word)
                    for t in tokens[i + n:j]]
            if len(cont) > _SNIPPET_SLOT_WORD_CAP:
                break
            span = Span(tok.start, tokens[j - 1].end)
            values = split_slots(cont, len(placeholders))
            yield Proposal(
                layer=3, cls="snippet", op="snippet_expansion",
                span=span, input_text=_text_of(host, span),
                output_text=expand(snippet, values),
                value=snippet.snippet_id, unit="snippet",
                join=JOIN_WORD, rule_id=snippet.snippet_id)
            break


def grammar_file_tags(host):
    """Explicit file tags (S17, M10): ``attach file <spoken name>``
    resolves against the destination's known files and inserts the
    resolved literal filename — consuming only the words the reference
    matched, so trailing prose survives. A resolution is never
    invented: ambiguous or unresolved references stay literal with a
    retained review suggestion. Layer 3; the attachment ACTION half (a
    real file chip) belongs to a certified surface adapter, not to
    text normalization."""
    resolver = getattr(host.context, "file_resolver", None) \
        if host.context else None
    tokens = host.tokens
    for i, tok in enumerate(tokens):
        if tok.word != "attach" or not tok.is_word:
            continue
        if _word_at(host, i + 1) != "file":
            continue
        j = i + 2
        while j < len(tokens) and tokens[j].is_word \
                and j - (i + 2) < _FILE_REF_WORD_CAP:
            j += 1
        span_end = tokens[j - 1].end if j > i + 2 else tokens[i + 1].end
        span = Span(tok.start, span_end)
        spoken = [t.word for t in tokens[i + 2:j]]
        if not spoken or resolver is None:
            yield Proposal(
                layer=3, cls="file_tag", op="attach_file",
                span=span, input_text=_text_of(host, span),
                output_text=_text_of(host, span), value=None,
                unit="filename", join=JOIN_WORD,
                reason="unresolved_file_reference", review=True)
            continue
        res = resolver.resolve(spoken)
        if res.status == "resolved":
            end = tokens[i + 2 + res.matched_words - 1].end \
                if res.matched_words else tokens[i + 1].end
            span = Span(tok.start, end)
            yield Proposal(
                layer=3, cls="file_tag", op="attach_file",
                span=span, input_text=_text_of(host, span),
                output_text=res.filename, value=res.filename,
                unit="filename", join=JOIN_WORD,
                reason="exact_match")
        else:
            yield Proposal(
                layer=3, cls="file_tag", op="attach_file",
                span=span, input_text=_text_of(host, span),
                output_text=_text_of(host, span), value=None,
                unit="filename", join=JOIN_WORD,
                reason=f"{res.status}_file_reference", review=True)


# A placeholder continuation beyond this many words reads as prose that
# happens to start with a trigger, not slot values (documented bound).
_SNIPPET_SLOT_WORD_CAP = 24

# A file reference beyond this many words reads as prose after the
# action phrase, not a spoken filename (bounds the resolver's prefix
# walk; documentated alongside the snippet cap).
_FILE_REF_WORD_CAP = 12


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


def _guard_blocks(host, i, name_words, always=False, join=None):
    """True when a spoken punctuation/structure name is being used as a
    NOUN, not a command (M04-AUDIT-09). Structural rules, for every
    name:

    * a determiner right before it ("a question mark", "the forward
      slash character", "an exclamation mark", "the comma character");
    * a trailing-punctuation name (or a noun-ambiguous guarded name) at
      the START of a clause with more words after it ("period drama",
      "colon cancer", "pipe tobacco", "question mark placement"): a
      punctuation command attaches to the words BEFORE it, so at a
      clause start it has nothing to punctuate. Alone ("comma") it is
      still the command.

    Guarded names keep their historical lexical blockers (article /
    preposition / "X period" compounds / ordinals)."""
    g = host.profile.get("symbol_guards", {}) if host.profile else {}
    n = len(name_words)
    prev = _word_at(host, i - 1) if i > 0 and not host.brk[i] else None
    nxt_i = i + n
    nxt = _word_at(host, nxt_i) if nxt_i < len(host.tokens) \
        and not host.brk[nxt_i] else None
    joined = " ".join(name_words)
    guarded = always or joined in g.get("guarded_names", [])
    if prev in g.get("determiner_words", []):
        return True
    clause_start = i == 0 or host.brk[i]
    if clause_start and nxt is not None \
            and (join == JOIN_ATTACH_LEFT or guarded):
        # any following token in the clause — a word or a written
        # number ("Period 3 starts at noon"): the guard must not depend
        # on the next token's shape, or a second pass over "Period 5"
        # would convert what the first pass kept (review R7)
        return True
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
    """Spoken punctuation/symbol names → the symbol, with structural noun
    guards ("a dash of salt", "the period of adjustment", "period
    drama", "a question mark" stay prose)."""
    if not host.profile.get("punctuation_commands"):
        return
    for words, spec in _phrase_tables(host, host.profile.get("symbols")):
        n = len(words)
        for i in range(len(host.tokens) - n + 1):
            seq = [tk.word for tk in host.tokens[i:i + n]]
            if seq != words or not all(tk.is_word for tk in
                                       host.tokens[i:i + n]) \
                    or not host.connected(i, i + n):
                continue
            join = spec.get("join", JOIN_WORD)
            if _guard_blocks(host, i, words, join=join):
                continue
            # A command word's own edge punctuation belongs to the
            # command it replaces ("comma," → ","; "new line," at a
            # text start leaves no stray comma — review R23).
            span = Span(host.tokens[i].start, host.tokens[i + n - 1].end)
            yield Proposal(
                layer=4, cls="symbol", op="symbol_command",
                span=span, input_text=_text_of(host, span),
                output_text=spec["out"], value=spec["out"],
                unit="symbol", join=join)


def _markdown_guard_blocks(host, i, name_words):
    """The historical article/idiom guards for structure commands. The
    clause-start rule does not apply: "new bullet ship the release"
    opens with its command by design."""
    g = host.profile.get("symbol_guards", {}) if host.profile else {}
    prev = _word_at(host, i - 1) if i > 0 and not host.brk[i] else None
    nxt_i = i + len(name_words)
    nxt = _word_at(host, nxt_i) if nxt_i < len(host.tokens) \
        and not host.brk[nxt_i] else None
    if prev in g.get("determiner_words", []) \
            or prev in g.get("article_words", []):
        return True
    if nxt in g.get("blocker_next", []) or prev in g.get("blocker_prev", []):
        return True
    return False


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
                                       host.tokens[i:i + n]) \
                    or not host.connected(i, i + n):
                continue
            # "a new bullet point here" / "the new line of the poem"
            # stay prose: article/idiom guards apply to every structure
            # command, not just the guarded symbol names.
            if _markdown_guard_blocks(host, i, words):
                continue
            span = Span(host.tokens[i].start, host.tokens[i + n - 1].end)
            yield Proposal(
                layer=4, cls="markdown", op="markdown_command",
                span=span, input_text=_text_of(host, span),
                output_text=spec["out"], value=words[0],
                unit="markdown", join=spec.get("join", "block"))


def grammar_flags(host):
    """Spoken shell flags: "dash dash verbose" → "--verbose", "dash r" →
    "-r". Emission is text only — nothing executes (AC04). The flag
    keeps the written case of its letters ("ls dash L" → "-L"; "-L" and
    "-l" are different flags — review R10). A single-letter flag
    follows a command in the same clause; a clause-initial "dash I …"
    is prose ("dash I asked him")."""
    if not host.profile.get("flag_commands"):
        return
    tokens = host.tokens
    for i, tok in enumerate(tokens):
        if tok.word != "dash" or not tok.is_word:
            continue
        w1 = _word_at(host, i + 1)
        if w1 is None or host.brk[i + 1]:
            continue
        if w1 == "dash":
            w2 = _word_at(host, i + 2)
            if w2 and i + 2 < len(tokens) and not host.brk[i + 2] and \
                    tokens[i + 2].is_word and len(w2) > 1 and \
                    w2.isalpha() and not _guard_blocks(host, i, ["dash"]):
                flag = "--" + tokens[i + 2].core
                span = host.core_span(i, i + 3)
                yield Proposal(
                    layer=4, cls="flag", op="flag_words",
                    span=span, input_text=_text_of(host, span),
                    output_text=flag, value=flag,
                    unit="flag", join=JOIN_WORD)
        elif (len(w1) == 1 and w1.isalpha() and tokens[i + 1].is_word
              and i > 0 and not host.brk[i]):
            flag = "-" + tokens[i + 1].core
            span = host.core_span(i, i + 2)
            yield Proposal(
                layer=4, cls="flag", op="flag_words",
                span=span, input_text=_text_of(host, span),
                output_text=flag, value=flag,
                unit="flag", join=JOIN_WORD)


def grammar_dotfile(host):
    """"dot env" → ".env" for known dotfile names (SEED-29)."""
    names = set(host.profile.get("dotfile_names", []))
    for i in range(len(host.tokens) - 1):
        if host.tokens[i].word != "dot" or not host.tokens[i].is_word:
            continue
        nxt = host.tokens[i + 1]
        if not nxt.is_word or nxt.word not in names or host.brk[i + 1]:
            continue
        span = host.core_span(i, i + 2)
        yield Proposal(
            layer=4, cls="path", op="dotfile_words",
            span=span, input_text=_text_of(host, span),
            output_text=f".{nxt.word}", value=f".{nxt.word}",
            unit="dotfile", join=JOIN_WORD)


def _path_component(host, j):
    """(text, tokens used) for one spoken path component starting at
    token j: a word, optionally joined to further words by spoken "dot"
    ("nginx dot conf" → "nginx.conf"), or a dotted name ("dot env" →
    ".env"). Written spelling is kept. (None, 0) when token j is not a
    plain word."""
    tokens = host.tokens
    if j >= len(tokens) or host.brk[j] or not tokens[j].is_word:
        return None, 0
    parts = []
    k = j
    if tokens[k].word == "dot":
        if k + 1 >= len(tokens) or host.brk[k + 1] \
                or not tokens[k + 1].is_word:
            return None, 0
        parts.append("." + tokens[k + 1].core)
        k += 2
    else:
        parts.append(tokens[k].core)
        k += 1
    while k + 1 < len(tokens) and _word_at(host, k) == "dot" \
            and not host.brk[k] and not host.brk[k + 1] \
            and tokens[k + 1].is_word:
        parts.append("." + tokens[k + 1].core)
        k += 2
    return "".join(parts), k - j


def grammar_spoken_path(host):
    """Anchored spoken paths: "path slash users slash danny" →
    "/users/danny" — path intent is distinct from an ordinary slash word;
    no filesystem action runs. Components keep the speaker's exact
    written spelling ("path slash Users slash Ada" → "/Users/Ada"): a
    path is case-significant and M04 never assumes the destination
    filesystem is not (M04-AUDIT-11). A component may carry spoken dots
    ("nginx dot conf" → "nginx.conf", "slash dot env" → "/.env"), so a
    file name never leaves a path/speech hybrid behind (review R9). A
    chain whose next component is not a plain word ("... slash build2")
    is refused WHOLE, never emitted as a valid-looking prefix."""
    anchors = set(host.profile.get("path_anchors", []))
    tokens = host.tokens
    for i, tok in enumerate(tokens):
        if tok.word not in anchors or not tok.is_word:
            continue
        j = i + 1
        if _word_at(host, j) != "slash" or host.brk[j]:
            continue
        segs = []
        complete = True
        while j < len(tokens) and _word_at(host, j) == "slash" \
                and not host.brk[j]:
            seg, used = _path_component(host, j + 1)
            if seg is None:
                complete = False
                j += 2 if j + 1 < len(tokens) and not host.brk[j + 1] \
                    else 1
                break
            segs.append(seg)
            j += 1 + used
        if len(segs) < 2 and complete:
            continue
        span = host.core_span(i, min(j, len(tokens)))
        if not complete:
            yield Proposal(
                layer=4, cls="path", op="spoken_path_words",
                span=span, input_text=_text_of(host, span),
                output_text="", value=None, unit="path",
                reason="incomplete_path", review=True)
            continue
        yield Proposal(
            layer=4, cls="path", op="spoken_path_words",
            span=span, input_text=_text_of(host, span),
            output_text="/" + "/".join(segs),
            value="/" + "/".join(segs), unit="path", join=JOIN_WORD)


def grammar_domain_email(host):
    """Spoken dot/at forms become syntax only in address patterns:
    "danny at gmail dot com" → email; "example dot com" → domain, with
    known TLDs. Punctuation and spelling are never invented: every
    component keeps the speaker's written spelling — an email local
    part is case-significant ("UserName at example dot com" →
    "UserName@example.com", M04-AUDIT-11)."""
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
        if tld not in tlds or not host.connected(i, j + 2):
            continue
        host_parts = [tokens[i + 2].core, tokens[j + 1].core]
        j += 2
        while _word_at(host, j) == "dot" and host.connected(j - 1, j + 2):
            t2 = _word_at(host, j + 1)
            if t2 not in tlds:
                break
            host_parts.append(tokens[j + 1].core)
            j += 2
        span = host.core_span(i, j)
        email = f"{tokens[i].core}@{'.'.join(host_parts)}"
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
        if tld not in tlds or not host.connected(i, i + 3):
            continue
        # Skip when an email proposal already covers this span.
        if _word_at(host, i - 1) == "at":
            continue
        parts = [tokens[i].core, tokens[i + 2].core]
        j = i + 3
        while _word_at(host, j) == "dot" and host.connected(j - 1, j + 2):
            t2 = _word_at(host, j + 1)
            if t2 not in tlds:
                break
            parts.append(tokens[j + 1].core)
            j += 2
        span = host.core_span(i, j)
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
    """Context-fed identifiers (spoken form → canonical). A span that
    already reads exactly as its canonical form is a no-op: it emits no
    edit — a second pass over normalized text stays empty (M04-AC03,
    M04-AUDIT-15) — and CLAIMS the span so a shorter overlapping
    spoken form cannot rewrite inside it."""
    mapping = host.context.identifiers if host.context else None
    if not mapping:
        return
    claimed: list[Span] = []
    spoken = sorted(mapping.keys(), key=lambda s: -len(s.split()))
    for phrase in spoken:
        words = phrase.lower().split()
        n = len(words)
        for i in range(len(host.tokens) - n + 1):
            seq = [tk.word for tk in host.tokens[i:i + n]]
            if seq != words or not all(tk.is_word for tk in
                                       host.tokens[i:i + n]) \
                    or not host.connected(i, i + n):
                continue
            # Match token cores so edge punctuation survives (same rule
            # as grammar_vocabulary).
            span = host.core_span(i, i + n)
            if host.text[span.start:span.end] == mapping[phrase]:
                claimed.append(span)
                continue
            if any(span.overlaps(c) for c in claimed):
                continue
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
    grammar_snippets,
    grammar_file_tags,
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
    "skill", "snippet", "file_tag", "symbol", "markdown", "flag",
    "path", "domain", "email", "vocabulary",
})
