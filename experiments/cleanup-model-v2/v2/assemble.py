"""Family-separated data, engine-independent labels, exact runtime prompts."""
from __future__ import annotations

import bisect
import collections
import difflib
import json
import random
import re
from .common import *
from lfx import synth


def stable_tokens(text):
    return [(m.start(), m.end(), m.group().casefold())
            for m in re.finditer(r"\w+(?:['’]\w+)*", text)]


class Dedup:
    """Inverted shingle index avoids a quadratic full-corpus comparison."""
    def __init__(self):
        self.shingles, self.index, self.exact = [], collections.defaultdict(set), {}

    def add(self, text, label, check=True):
        key = " ".join(text.casefold().split())
        sh = synth.shingles(text)
        if check and key in self.exact:
            return self.exact[key]
        candidates = set()
        if check:
            for s in sh:
                candidates.update(self.index.get(s, ()))
            for idx in candidates:
                other, old_label = self.shingles[idx]
                if synth.jaccard(sh, other) >= 0.6:
                    return old_label
        idx = len(self.shingles)
        self.shingles.append((sh, label))
        self.exact[key] = label
        for s in sh:
            self.index[s].add(idx)
        return None


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
        # A cut must land on a retained token and not split a correction.
        # Otherwise retain the example for evaluation but abstain from training.
        if idx not in matches:
            raise ValueError("unaligned_window_boundary")
        cuts.append(dst[matches[idx]][0])
    cuts.append(len(target))
    if cuts != sorted(set(cuts)):
        raise ValueError("nonmonotonic_window_targets")
    return {(w.start, w.end): target[cuts[i]:cuts[i+1]].strip() for i, w in enumerate(windows)}


def capture(pair):
    """Supervise correct targets even when the delivered engine vetoes them.

    The engine itself renders every prompt, including read-only neighboring
    context. Targets for long cases are cut only at aligned retained tokens.
    Rejected labels remain in evaluation; they never get rewritten to pass.
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
        match = re.search(re.escape(line), pair["model_input"][cursor:], re.IGNORECASE)
        if match is None:
            raise ValueError("gold_offset_missing")
        start, end = cursor + match.start(), cursor + match.end()
        offsets.append([start, end]); cursor = end
    pair["gold_offsets"] = offsets
    windows = engine.plan_windows(pair["model_input"], protected)
    targets = window_targets(pair, windows)
    calls = []

    class CaptureEngine(engine.CleanupEngine):
        def _generate(self, payload, *, kind, window_range, input_text, corrections_pass=False,
                      observations=None, depth=0, parent_pass_id=None):
            if depth:
                raise ValueError("capture_retry_not_supervised")
            if corrections_pass:
                answer = "\n".join(g for g in pair.get("gold_lines", []) if g.lower() in input_text.lower()) or "NONE"
            else:
                answer = targets[tuple(window_range)]
            def reply(prompt, max_tokens):
                ntok = len(tok.encode(answer, add_special_tokens=False)) + 1
                if ntok + 1 > max_tokens:
                    raise ValueError("target_over_output_budget")
                calls.append({"role":"corrections" if corrections_pass else "main", "prompt":prompt,
                              "completion":answer,"max_tokens":max_tokens,"window":list(window_range)})
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
            hit = idx.add(p["model_input"] + " " + p["target"], split)
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
