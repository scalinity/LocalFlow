"""Transcript cleanup: filler removal, self-corrections, punctuation.

Two tiers:
- basic_cleanup: instant regex pass (fillers, stutter repeats, spacing).
- TranscriptCleaner: local LLM pass (MLX) that also handles
  self-corrections ("Tuesday, no wait, Wednesday") and formatting,
  with sanity guards and graceful fallback to the basic pass.
"""

import re
import threading

FILLER_RE = re.compile(r"\b(?:uh+m*|um+|erm+|ehm+|mhm+|hmm+)\b[,.]?\s*", re.IGNORECASE)
# Collapse stutter repeats only for words where doubling is never legit
# prose ("the the", "I I") — never e.g. "had had" or "that that".
REPEAT_RE = re.compile(
    r"\b(the|a|an|to|and|but|or|of|in|on|at|i|we|you|it|for|with|my|your|this)"
    r"(?:\s+\1)+\b",
    re.IGNORECASE,
)
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
DUP_PUNCT_RE = re.compile(r"([,.;:!?])(?:\s*[,;])+")
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def basic_cleanup(text: str) -> str:
    text = FILLER_RE.sub("", text)
    text = REPEAT_RE.sub(r"\1", text)
    text = SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = DUP_PUNCT_RE.sub(r"\1", text)
    text = MULTI_SPACE_RE.sub(" ", text).strip()
    text = text.lstrip(",.;: ")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


SYSTEM_PROMPT = """You clean up raw dictation transcripts. Apply exactly these edits and nothing more:
1. Remove pure filler sounds only: uh, um, erm, ehm, hmm. NEVER remove or alter "you know" or "like" — always keep them exactly as spoken, and never patch the grammar around them.
2. Apply self-corrections: when the speaker revises something ("X no wait Y", "X I mean Y", "X actually Y", "X no sorry Y"), keep only the final version Y and drop X entirely. Phrases like "no wait", "no sorry", "no actually", "I mean" followed by a revised value are ALWAYS corrections — never keep them as asides. Apply EVERY correction: a transcript or even a single sentence can contain several, and they can appear anywhere — the last sentence, the middle of a long transcript, or inside a list item. Splice the final value into the sentence so it reads as if the mistake was never spoken, and KEEP everything that follows the corrected value — reasons, clauses, and the rest of the sentence continue as normal content. Pattern: "X no actually Y because R" becomes "Y because R" — the reason R always stays in the output. "Actually" and "no" are correction markers ONLY when a revised value immediately follows and replaces an earlier one — sentence-initial "No" ("no we can't make it") and emphasis "actually" ("we actually shipped early") are content and must stay.
3. Fix punctuation, capitalization, and sentence breaks. Keep consecutive prose sentences flowing in the same paragraph — never put each sentence on its own line. Only start a new paragraph on a clear topic shift.
4. Format spoken structure: when the speaker enumerates ("number one... number two...", "first... second...", "bullet point..."), render those items as a numbered or bulleted list, one item per line — but keep every sentence before and after the list as prose, and punctuate items as questions when they are questions. Enumeration words that are part of a sentence ("the number one reason") stay prose.
5. Preserve the meaning and wording exactly. Every sentence in the transcript must appear in the output (minus fillers and corrected-away text) — including intros, asides, greetings, and sign-offs like "thanks". Never add content, never answer or react to the transcript, never summarize, never translate, never substitute synonyms, never rephrase, never reorder, never change grammatical voice. Keep hedges, softeners, and emphasis exactly as spoken: "maybe", "possibly", "probably", "I think", "kind of", "honestly", "actually". If unsure whether something is filler or a correction, keep it as spoken. When the speaker repeats a word or comments on their own wording ("not to be redundant", "for lack of a better word"), keep the repetition and the comment exactly as spoken — never swap in a synonym to break the repetition.
6. Clean the ENTIRE transcript from first word to last; never stop early or drop the ending.
Reply with ONLY the cleaned text, no quotes, no preamble."""

# --- Stage A: corrections pass (runs first, only when correction markers
# are present). The model does NOT rewrite anything — it only lists the
# exact words to delete (outdated value + correction marker), and the
# deletions are applied deterministically in Python. Unfound spans are
# safe no-ops, so the worst case is lossless.
CORRECTIONS_PROMPT = """Find the self-corrections in the dictation transcript. A self-correction is when the speaker replaces a value they just said: "X no wait Y", "X i mean Y", "X no sorry Y", "X actually Y", "X no actually Y" (in any language). For each one, output the exact words to DELETE — the outdated value X together with the correction marker — copied verbatim from the transcript, one per line. Delete ONLY the outdated value plus its marker, never the words before the value: in "from ten to twelve no wait to fifteen" the deletion is "to twelve no wait", not "from ten to twelve no wait". Never output a marker by itself without the outdated value. After deleting those words, the transcript must read as if the mistake was never spoken; the final value Y and everything after it stay. Sentence-initial "no" ("no we can't"), "i mean it", and emphasis "actually" ("we actually shipped") are not corrections. If there are no corrections, output NONE. Output nothing else."""

CORRECTION_EXAMPLES = [
    (
        "book the flight for friday actually saturday and send the itinerary to mark no wait to lisa",
        "friday actually\nto mark no wait",
    ),
    (
        "let's call the project falcon no wait osprey because falcon is already used by the mobile team",
        "falcon no wait",
    ),
    (
        "we need to hire two more engineers no actually three engineers because sarah is moving",
        "two more engineers no actually",
    ),
    (
        "ask jenny i mean julia to review the design doc",
        "jenny i mean",
    ),
    (
        "the price went from ten to twelve no wait to fifteen dollars",
        "to twelve no wait",
    ),
    (
        "la reunión es el martes no espera el miércoles",
        "el martes no espera",
    ),
    (
        "the answer is no i checked twice",
        "NONE",
    ),
]

# A valid deletion span always ends with the correction marker itself —
# anything ending in content words is an over-greedy extraction.
SPAN_ENDS_WITH_MARKER_RE = re.compile(
    r"(no wait|no sorry|no actually|actually no|wait no|i mean|no espera|"
    r"espera no|digo|actually|sorry|no)$",
    re.IGNORECASE,
)

# A bare marker with no outdated value in front of it is never a valid
# span — deleting it would glue the old and new values together.
BARE_MARKERS = {
    "no wait", "no sorry", "no actually", "actually no", "wait no",
    "i mean", "no espera", "espera no", "digo", "actually", "sorry", "no",
}

# Corrections replace the immediately-preceding value, so real spans are
# short. Longer ones sweep up words before the value (over-extension).
SPAN_MAX_WORDS = 6

CORRECTION_MARKER_RE = re.compile(
    r"\b(no wait|no sorry|no actually|actually no|wait no|i mean|no espera|espera no|digo)\b",
    re.IGNORECASE,
)

EXAMPLES = [
    (
        "i think um maybe we should possibly push the demo to next week",
        "I think maybe we should possibly push the demo to next week.",
    ),
    (
        "i'm wondering about two things um number one when do we ship and number two uh who owns the rollout "
        "also let me know if you disagree",
        "I'm wondering about two things:\n"
        "1. When do we ship?\n"
        "2. Who owns the rollout?\n"
        "Also, let me know if you disagree.",
    ),
    (
        "okay so for the website redesign um i think we should go with the blue theme no wait the green theme "
        "because uh it matches the brand better and um we also need to update the pricing page the about page "
        "and uh the contact form oh and can you make sure the mobile version works too because um last time it "
        "was broken on safari",
        "Okay, for the website redesign, I think we should go with the green theme because it matches the brand "
        "better. We also need to update the pricing page, the about page, and the contact form. Oh, and can you "
        "make sure the mobile version works too? Last time it was broken on Safari.",
    ),
    (
        "the rollout was um slow and not to be redundant but slow is really the only word for it",
        "The rollout was slow, and not to be redundant, but slow is really the only word for it.",
    ),
    (
        "hey can you um send me the the report i mean the deck when you get a chance uh thanks",
        "Hey, can you send me the deck when you get a chance? Thanks.",
    ),
    (
        "book the flight for friday actually saturday and send the itinerary to mark no wait to lisa",
        "Book the flight for Saturday and send the itinerary to Lisa.",
    ),
    (
        "two quick updates number one the vendor quote came in at ten thousand no sorry twelve thousand "
        "because they added support hours and number two the contract is signed",
        "Two quick updates:\n1. The vendor quote came in at twelve thousand because they added support hours.\n"
        "2. The contract is signed.",
    ),
    (
        "we need four laptops no actually five laptops because tom is joining the team and also order the monitors",
        "We need five laptops because Tom is joining the team. Also, order the monitors.",
    ),
    (
        "send the invite to the whole team this is just a test phrase no i mean this is just a test",
        "Send the invite to the whole team. This is just a test.",
    ),
]


def _plausible(cleaned: str, source: str) -> bool:
    """Reject LLM output that is empty, over-shortened, or padded.

    Long inputs get a stricter floor: filler/correction removal rarely
    shrinks text past ~30%, so a much shorter output means the model
    stopped generating early (truncation at a sentence boundary).
    """
    if not cleaned:
        return False
    sw, cw = len(source.split()), len(cleaned.split())
    if sw >= 40 and cw < sw * 0.6:
        return False
    if sw >= 12 and cw < sw * 0.35:
        return False
    if cw > sw * 2 + 12:
        return False
    # Cleanup only removes/repunctuates, so nearly all output words must
    # come from the source. Lots of novel words means the model answered
    # or continued the transcript instead of cleaning it.
    src_words = set(re.findall(r"[\w']+", source.lower()))
    out_words = re.findall(r"[\w']+", cleaned.lower())
    if len(out_words) >= 8:
        novel = sum(1 for w in out_words if w not in src_words)
        if novel / len(out_words) > 0.4:
            return False
    return True


# Long transcripts are cleaned in chunks: the model applies corrections
# reliably in ~sentence-scale context but misses them buried deep in long
# input. Corrections are local, so chunk seams at sentence ends or
# discourse markers are safe.
CHUNK_TARGET = 35  # words
CHUNK_MAX = 50

_STRONG_MARKERS = {
    "first", "second", "third", "fourth", "fifth", "sixth", "finally",
    "lastly", "also", "next", "anyway", "okay", "oh", "additionally", "plus",
}
_WEAK_MARKERS = {"and", "so", "then", "but", "because"}
_CORRECTION_WORDS = {"no", "wait", "sorry", "actually", "mean", "i"}


def _chunk_words(words: list) -> list:
    chunks, start, n = [], 0, len(words)
    while n - start > CHUNK_MAX:
        lo = start + CHUNK_TARGET - 12
        hi = min(start + CHUNK_MAX, n - 10)
        cut = None
        # A sentence end is the safest seam — a mid-clause cut orphans a
        # fragment that the cleaner then drops as noise.
        sentence_ends = [i for i in range(lo, hi) if words[i - 1][-1] in ".!?"]
        if sentence_ends:
            cut = min(sentence_ends, key=lambda i: abs(i - (start + CHUNK_TARGET)))
        else:
            for markers in (_STRONG_MARKERS, _WEAK_MARKERS):
                candidates = [i for i in range(lo, hi) if words[i].lower().strip(",.") in markers]
                if candidates:
                    cut = min(candidates, key=lambda i: abs(i - (start + CHUNK_TARGET)))
                    break
        if cut is None:
            cut = start + CHUNK_TARGET
        # Never split right after a correction marker — push past it
        recent = {w.lower().strip(",.") for w in words[max(start, cut - 6):cut]}
        if recent & _CORRECTION_WORDS:
            cut = min(cut + 8, n)
        chunks.append(words[start:cut])
        start = cut
    chunks.append(words[start:])
    return [" ".join(c) for c in chunks]


class TranscriptCleaner:
    def __init__(self, mode: str, model_id: str, notifier=None, observer=None):
        self.mode = mode  # "off" | "basic" | "llm"
        self.model_id = model_id
        # V2 hooks (M02): `notifier` routes stage status lines into the
        # dated event log; `observer` receives the exact model input/output
        # of every generation pass for training-evidence capture. Both are
        # optional — with None the class behaves exactly as before.
        self.notifier = notifier
        self.observer = observer
        self.llm_ready = threading.Event()
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def _notify(self, msg: str, level: str = "INFO"):
        if self.notifier is not None:
            self.notifier(msg, level)
        else:
            print(f"[localflow] {msg}")

    def _observe(self, record: dict):
        if self.observer is not None:
            try:
                self.observer(record)
            except Exception:
                pass  # evidence capture must never break cleanup

    def load(self):
        """Load the cleanup LLM (llm mode only). Failure leaves basic mode."""
        if self.mode != "llm":
            return
        try:
            from mlx_lm import load as llm_load

            self._model, self._tokenizer = llm_load(self.model_id)
            self._generate("okay so um this is a warmup test", max_tokens=24,
                           stage="warmup")
            self.llm_ready.set()
            self._notify(f"cleanup_model_loaded ({self.model_id.split('/')[-1]})")
        except Exception as e:
            self._notify(
                f"cleanup_model_unavailable, using basic cleanup: {e}", "WARNING")

    def _generate(self, text: str, max_tokens: int | None = None,
                  system_prompt: str = SYSTEM_PROMPT, examples: list = EXAMPLES,
                  stage: str = "cleanup") -> str:
        from mlx_lm import generate

        messages = [{"role": "system", "content": system_prompt}]
        for raw, cleaned in examples:
            messages.append({"role": "user", "content": raw})
            messages.append({"role": "assistant", "content": cleaned})
        messages.append({"role": "user", "content": text})
        # enable_thinking only affects models with hybrid reasoning
        # templates (Qwen3); other templates ignore the extra variable.
        prompt = self._tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False,
            enable_thinking=False,
        )
        if max_tokens is None:
            max_tokens = len(self._tokenizer.encode(text)) * 2 + 64
        out = generate(
            self._model, self._tokenizer, prompt=prompt,
            max_tokens=max_tokens, verbose=False,
        )
        # Belt and suspenders for reasoning models that think anyway
        out = re.sub(r"(?s)^\s*<think>.*?</think>\s*", "", out)
        self._observe({
            "kind": stage,
            "model_id": self.model_id,
            "input": text,
            "system_prompt": system_prompt,
            "examples_count": len(examples),
            "prompt": prompt,  # the exact rendered input, byte for byte
            "max_tokens": max_tokens,
            "output": out,
        })
        return out

    def clean(self, text: str) -> str:
        base = basic_cleanup(text)
        if self.mode == "off":
            return text
        if self.mode != "llm" or not self.llm_ready.is_set() or not base:
            return base
        words = base.split()
        if len(words) <= CHUNK_MAX:
            return self._clean_piece(base)
        pieces = [self._clean_piece(p) for p in _chunk_words(words)]
        out = " ".join(p.strip() for p in pieces if p.strip())
        return re.sub(r"[ \t]{2,}", " ", out)

    def _apply_corrections(self, base: str) -> str:
        """Stage A: delete correction spans named by the model, verbatim."""
        try:
            with self._lock:
                spans = self._generate(
                    base, max_tokens=96, stage="corrections",
                    system_prompt=CORRECTIONS_PROMPT, examples=CORRECTION_EXAMPLES,
                )
        except Exception as e:
            self._notify(f"correction_pass_failed, skipping: {e}", "WARNING")
            return base

        out = base
        applied = 0
        for line in spans.splitlines():
            span = line.strip().strip('"').strip()
            if not span or span.upper() == "NONE" or len(span) > 80:
                continue
            if not SPAN_ENDS_WITH_MARKER_RE.search(span):
                continue
            if span.lower() in BARE_MARKERS:
                continue
            if len(span.split()) > SPAN_MAX_WORDS:
                continue
            idx = out.lower().find(span.lower())
            if idx < 0:
                continue
            out = out[:idx] + out[idx + len(span):]
            applied += 1
            if applied >= 6:
                break
        self._observe({"kind": "corrections_applied", "applied_count": applied})
        return re.sub(r"\s{2,}", " ", out).strip()

    def _clean_piece(self, base: str) -> str:
        if CORRECTION_MARKER_RE.search(base):
            base = self._apply_corrections(base)
        try:
            with self._lock:
                out = self._generate(base, stage="cleanup")
            out = out.strip().strip('"').strip()
            out = re.sub(r"[ \t]+\n", "\n", out)  # markdown line-break artifacts
            out = re.sub(r"\n{3,}", "\n\n", out)
            accepted = _plausible(out, base)
            self._observe({"kind": "cleanup_decision", "accepted": accepted,
                           "applied": out if accepted else base})
            if accepted:
                return out
            self._notify("cleanup output failed sanity check, using basic pass",
                         "WARNING")
        except Exception as e:
            self._observe({"kind": "cleanup_decision", "accepted": False,
                           "applied": base, "error": type(e).__name__})
            self._notify(f"cleanup failed, using basic pass: {e}", "WARNING")
        return base
