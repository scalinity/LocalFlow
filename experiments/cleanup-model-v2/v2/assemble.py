"""Family-separated data, engine-independent labels, exact runtime prompts."""
from __future__ import annotations

import bisect
import collections
import difflib
import json
import random
import re
from .common import *
from .strict_score import STUTTER_WORDS, correction_anchor
from lfx import synth


def stable_tokens(text):
    return [(m.start(), m.end(), m.group().casefold())
            for m in re.finditer(r"\w+(?:['’]\w+)*", text)]


def removes_created_repeat(window, corrected, answer, adjacent=str.isspace):
    """A correction deletion left a non-stutter word twice in a row and the answer drops one."""
    def repeats(text):
        tokens = stable_tokens(text)
        return collections.Counter(b[2] for a, b in zip(tokens, tokens[1:])
                                   if a[2] == b[2] and adjacent(text[a[1]:b[0]]))
    counts = lambda text: collections.Counter(t[2] for t in stable_tokens(text))
    return any(word not in STUTTER_WORDS and counts(answer)[word] < counts(corrected)[word]
               for word in repeats(corrected) - repeats(window))


class Dedup:
    """Inverted shingle index avoids a quadratic full-corpus comparison."""
    def __init__(self):
        self.shingles, self.index, self.exact = [], collections.defaultdict(set), {}

    def check(self, text):
        """The label of an indexed exact or near duplicate, without indexing text."""
        key = " ".join(text.casefold().split())
        if key in self.exact:
            return self.exact[key]
        sh = synth.shingles(text)
        for idx in sorted({i for s in sh for i in self.index.get(s, ())}):
            other, old_label = self.shingles[idx]
            if synth.jaccard(sh, other) >= 0.6:
                return old_label
        return None

    def add(self, text, label, check=True):
        if check:
            hit = self.check(text)
            if hit:
                return hit
        key = " ".join(text.casefold().split())
        sh = synth.shingles(text)
        idx = len(self.shingles)
        self.shingles.append((sh, label))
        self.exact[key] = label
        for s in sh:
            self.index[s].add(idx)
        return None


def admit(idx, pair, label):
    """Check a pair's input, target and their concatenation, then index all three.

    Checking before indexing keeps a pair from matching its own similar target.
    """
    texts = (pair["model_input"], pair["target"], pair["model_input"] + " " + pair["target"])
    hit = next((h for h in map(idx.check, texts) if h), None)
    if hit is None:
        for text in texts:
            idx.add(text, label, check=False)
    return hit


def window_targets(pair, windows):
    source, target = pair["model_input"], pair["target"]
    if len(windows) == 1:
        return {(windows[0].start, windows[0].end): target}
    src, dst = stable_tokens(source), stable_tokens(target)
    matches = {}
    for block in difflib.SequenceMatcher(None, [t[2] for t in src], [t[2] for t in dst], autojunk=False).get_matching_blocks():
        for n in range(block.size):
            matches[block.a + n] = block.b + n
    cuts = [0]
    starts = [t[0] for t in src]
    for w in windows[1:]:
        idx = bisect.bisect_left(starts, w.start)
        # A cut must sit inside an unchanged run, so neither window owns an
        # edit made across the seam, and no opening marker (list dash, heading,
        # quote) may sit before the cut token on either side, or the previous
        # window's target would carry it. Otherwise retain the example for
        # evaluation but abstain from training.
        if idx not in matches or matches.get(idx - 1) != matches[idx] - 1:
            raise ValueError("unaligned_window_boundary")
        cut = dst[matches[idx]][0]
        if source[w.start:starts[idx]].strip() or not re.fullmatch(r"[^\w\s]*\s+", target[dst[matches[idx] - 1][1]:cut]):
            raise ValueError("unaligned_window_boundary")
        cuts.append(cut)
    cuts.append(len(target))
    if cuts != sorted(set(cuts)):
        raise ValueError("nonmonotonic_window_targets")
    return {(w.start, w.end): target[cuts[i]:cuts[i+1]].strip() for i, w in enumerate(windows)}


# Why a call's prompt and target agree; any other reason drops the call.
AGREEMENTS = {"gold_lines_applied_by_engine", "input_is_label_pre_cleanup"}


def cleanup_agreement(source, offsets, window_range, input_text, answer, vocabulary_pairs=()):
    """Whether a cleanup call's prompt and target agree, as a reason.

    They agree when the engine's input is the label's pre-cleanup text for the
    window (the source window with its gold deletions applied) and the target
    uses no word those deletions took out, which a detail the engine did not
    retain would otherwise put back, and rewrites no dictated word in a way a
    permitted conversion does not explain (label_defects.unexplained_rewrites):
    the engine's validation no longer vetoes such a target once the row is vetoed.
    """
    from .label_defects import remove_spans, unexplained_rewrites
    start, end = window_range
    spans = [(s - start, e - start) for s, e in offsets if start <= s and e <= end]
    if remove_spans(input_text, []) != remove_spans(source[start:end], spans):
        return "input_is_not_label_pre_cleanup"
    # Fold the curly apostrophe as the label rules do, so a deleted "don’t" written back as "don't" counts.
    counts = lambda text: collections.Counter(t[2].replace("’", "'") for t in stable_tokens(text))
    given, removed = counts(input_text), counts(source[start:end]) - counts(input_text)
    if any(n > given[word] for word, n in counts(answer).items() if removed[word]):
        return "target_uses_deleted_words"
    # Removing "200 megabytes, sorry" from "past 200 megabytes, sorry, past 300" leaves the
    # comma between the two "past"; collapsing them is the created repeat capture refuses.
    if removes_created_repeat(source[start:end], input_text, answer, adjacent=lambda gap: not re.search(r"\w", gap)):
        return "target_drops_created_repeat"
    if unexplained_rewrites(input_text, answer, vocabulary_pairs):
        return "target_rewrites_dictated_words"
    return "input_is_label_pre_cleanup"


def capture(pair, *, consistent_only=False):
    """Supervise correct targets even when the delivered engine vetoes them.

    The engine itself renders every prompt, including read-only neighboring
    context. Targets for long cases are cut only at aligned retained tokens.
    Rejected labels remain in evaluation; they never get rewritten to pass.
    With consistent_only, a row the engine does not deliver exactly keeps only
    the calls whose prompt and target agree: the cleanup calls cleanup_agreement
    accepts, and a window's corrections-pass call (the source window answered
    with its gold lines) where the engine applied exactly those lines.
    engine_oracle.supervision records each call.
    """
    from localflow.v2.cleanup import engine, protected_spans_for_cleanup
    from lfx.capture import tokenizer, render_with
    tok = tokenizer("qwen35")
    norm = synth.normalize_text(pair["raw_input"])
    if norm.text != pair["model_input"]:
        raise ValueError("normalization_mismatch")
    protected = protected_spans_for_cleanup(pair["raw_input"], norm.text, norm.protected, norm.edits)
    pair["protected_spans"] = [list(p) for p in protected]
    offsets, cursor = [], 0
    for line in pair.get("gold_lines", []):
        try:
            start, end = correction_anchor(pair["model_input"], line, cursor)
        except ValueError as exc:
            raise ValueError("gold_offset_" + str(exc)) from None
        offsets.append([start, end]); cursor = end
    pair["gold_offsets"] = offsets
    if pair["split"] == "train":
        # Every capture path that produces TRAIN supervision applies this rule.
        from .refinement import training_label_conflict
        conflict = training_label_conflict(pair)
        if conflict:
            raise ValueError(conflict["reason"])
    windows = engine.plan_windows(pair["model_input"], protected)
    targets = window_targets(pair, windows)
    calls, agreements = [], []

    class CaptureEngine(engine.CleanupEngine):
        def _generate(self, payload, *, kind, window_range, input_text, corrections_pass=False,
                      observations=None, depth=0, parent_pass_id=None):
            if depth:
                raise ValueError("capture_retry_not_supervised")
            if corrections_pass:
                answer = "\n".join(g for g, (s, e) in zip(pair.get("gold_lines", []), offsets)
                                   if window_range[0] <= s and e <= window_range[1]) or "NONE"
            else:
                answer = targets.get(tuple(window_range))
                if answer is None:
                    raise ValueError("window_plan_mismatch")
                # Supervision must not teach deleting a meaningful word that
                # repeats only because a correction span was removed before it.
                if removes_created_repeat(pair["model_input"][window_range[0]:window_range[1]], input_text, answer):
                    raise ValueError("correction_created_repeat")
            agreement = (None if corrections_pass else
                         cleanup_agreement(pair["model_input"], offsets, window_range, input_text, answer,
                                           pair.get("vocabulary_pairs")))
            def reply(prompt, max_tokens):
                ntok = len(tok.encode(answer, add_special_tokens=False)) + 1
                if ntok + 1 > max_tokens:
                    raise ValueError("target_over_output_budget")
                calls.append({"role":"corrections" if corrections_pass else "main", "prompt":prompt,
                              "completion":answer,"max_tokens":max_tokens,"window":list(window_range)})
                agreements.append(agreement)
                return {"text":answer,"output_tokens":ntok,"limit_hit":False,"prompt":prompt}
            self._generate_fn = reply
            return super()._generate(payload, kind=kind, window_range=window_range, input_text=input_text,
                      corrections_pass=corrections_pass, observations=observations, depth=depth, parent_pass_id=parent_pass_id)

    result = CaptureEngine(None, render_fn=render_with(tok)).clean(pair["model_input"],
                 destination_profile=pair.get("destination_profile"), protected_spans=protected,
                 relevant_vocabulary=pair.get("relevant_vocabulary", []),
                 vocabulary_pairs=tuple(tuple(v) for v in pair.get("vocabulary_pairs", [])))
    pair["engine_oracle"] = {"path":result.path, "exact":result.text == pair["target"],
                             "delivered":result.text,"fallback_reason":result.fallback_reason,
                             "windows":len(windows)}
    if consistent_only and not pair["engine_oracle"]["exact"]:
        # A corrections call agrees only where the engine applied exactly that window's
        # gold deletions, which its cleanup input then shows (cleanup_agreement checks the
        # input first): a gold line the engine rejects would teach a line the parser refuses.
        applied = {tuple(c["window"]) for c, why in zip(calls, agreements)
                   if c["role"] == "main" and why != "input_is_not_label_pre_cleanup"}
        agreements = [why if c["role"] == "main" else "gold_lines_applied_by_engine"
                      if tuple(c["window"]) in applied else "gold_lines_not_applied_by_engine"
                      for c, why in zip(calls, agreements)]
        pair["engine_oracle"]["supervision"] = [
            {"role":c["role"], "window":c["window"], "kept":why in AGREEMENTS, "why":why}
            for c, why in zip(calls, agreements)]
        calls = [c for c, why in zip(calls, agreements) if why in AGREEMENTS]
    return {"pair_id":pair["pair_id"],"family_id":pair["family_id"],"split":pair["split"],"calls":calls}


def assemble():
    from lfx.assemble import production_examples, fixture_texts
    existing = read_json(ART / "dataset/freeze.json")
    idx = Dedup()
    # Existing tests are exclusion material only, never examples for generation
    # or supervision. Original train/validation also excluded from new families.
    for split in ("test", "validation", "train"):
        path = OLD_ART / ("frozen/test_synthetic.jsonl" if split == "test" else f"dataset/{split}.jsonl")
        for p in read_jsonl(path):
            idx.add(p["model_input"], "original_"+split, check=False)
            idx.add(p["target"], "original_"+split, check=False)
    for t in production_examples() + fixture_texts():
        idx.add(t, "prompt_or_fixture", check=False)
    grouped = collections.defaultdict(list)
    for f in sorted((ART / "accepted").glob("*.jsonl")):
        for p in read_jsonl(f):
            grouped[p["split"]].append(p)
    stats = {"created":utc_now(),"splits":{},"rejected":collections.Counter()}
    captured = []
    for split in ("test", "validation", "train"):
        kept, caps = [], []
        for p in sorted(grouped[split], key=lambda p:p["family_id"]):
            hit = admit(idx, p, split)
            if hit:
                stats["rejected"][split+":duplicate:"+hit] += 1; continue
            try:
                cap = capture(p)
            except (ValueError, RuntimeError) as exc:
                p["capture_error"] = str(exc)
                stats["rejected"][split+":capture:"+str(exc)] += 1
                cap = None
            # Correct but unreachable/multiwindow cases stay in evaluation.
            # Training counts state exactly how many produced supervision.
            kept.append(p)
            if cap:
                caps.append(cap)
        if split in ("test", "validation") and existing:
            current = ART / "dataset" / f"{split}.jsonl"
            # Frozen split files are never regenerated or silently updated.
            frozen_ids = [p["case_id"] for p in read_jsonl(current)]
            if frozen_ids != [p["case_id"] for p in kept]:
                raise RuntimeError("Frozen split membership changed")
        else:
            write_jsonl(ART / "dataset" / f"{split}.jsonl", kept)
            write_jsonl(ART / "dataset" / f"{split}_captures.jsonl", caps)
        stats["splits"][split] = {"accepted":len(kept), "captured_families":len(caps),
                                 "calls":sum(len(c["calls"]) for c in caps),
                                 "by_category":dict(collections.Counter(p["category"] for p in kept)),
                                 "noops":sum(p["is_noop"] for p in kept),
                                 "long_over_200":sum(len(p["model_input"].split())>200 for p in kept),
                                 "oracle_exact":sum(p.get("engine_oracle",{}).get("exact",False) for p in kept),
                                 "oracle_fallback":sum(p.get("engine_oracle",{}).get("path")!="llm" for p in kept)}
    write_json(ART / "dataset/stats.json", stats)
    if not existing and stats["splits"]["test"]["accepted"] and stats["splits"]["validation"]["accepted"]:
        write_json(ART / "dataset/freeze.json", {"frozen_at":utc_now(),
                   "files":{s:file_sha256(ART/"dataset"/f"{s}.jsonl") for s in ("test","validation")},
                   "scenario_assignment":"domain and situation hashed before generation; distinct test, validation and train scenarios",
                   "labels":"Sonnet 5.5 generated, Opus 5.5 independently checked; not human reviewed",
                   "candidate_outputs_existed":False})
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    assemble()
