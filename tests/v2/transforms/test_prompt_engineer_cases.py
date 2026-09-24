"""EV-13 / M11 (model-backed): the Prompt Engineer acceptance cases.

Every case runs through the REAL cleanup model (the same ModelRunner
the worker loads) under the builtin:prompt_engineer contract, and the
result is judged by ``judge`` — an oracle that is independent of the
production gate in ``localflow/v2/transforms/atoms.py``. Fixture
version 2 (``fixtures_prompt_engineer_v2.json``) encodes each
requirement as a relation that must hold inside ONE output segment
(polarity, conditions, order, scope, counts bound to their noun,
questions, hedges) instead of v1's any-of substrings, and names the
source clause it protects so a review can be checked for surfacing the
actual loss.

Verdicts (reported separately, never merged):
  applied                   applied, every relation holds
  applied_semantic_failure  applied although a relation is broken
  review_addresses_loss     needs_review, and the kept excerpts name
                            every broken relation's clause
  review_misdirected        needs_review, but a broken relation's
                            clause is not among the kept excerpts
  review_no_loss            needs_review with no broken relation
                            (safe; lost usefulness only)
  fallback                  generation failed / hit the limit; the
                            original was kept — NEVER counted applied
  error                     the harness itself raised

The run fails on any applied_semantic_failure, review_misdirected or
error, and on any fallback unless ``--allow-fallback`` is given.
Latency statistics cover every case, failures included.

Run: .venv/bin/python tests/v2/transforms/test_prompt_engineer_cases.py
     [--limit N] [--split dev|validation|regression|held-out]
     [--allow-fallback] [--json OUT.json]
"""

import json
import pathlib
import re
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import ModelRunner  # noqa: E402
from localflow.v2 import transforms as tf  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures_prompt_engineer_v2.json"
MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
EXPECTED_SPLITS = {"dev": 15, "validation": 5, "regression": 10,
                   "held-out": 10}

VERDICTS = ("applied", "applied_semantic_failure", "review_addresses_loss",
            "review_misdirected", "review_no_loss", "fallback", "error")
FAILING = ("applied_semantic_failure", "review_misdirected", "error")

# ---------------------------------------------------------------------------
# The oracle. Deliberately simple and separate from the production gate:
# its own normalization, segmentation and cue lists.
# ---------------------------------------------------------------------------

_NEG = re.compile(
    r"\b(?:not|no|never|without|nothing|none|avoid|avoiding|exclude|"
    r"excluding|excluded|omit|omitting|skip|neither|nor)\b|n't\b|"
    r"\bout of scope\b|\brather than\b|\binstead of\b")
_HEDGE = re.compile(
    r"\b(?:maybe|optional|optionally|might|may|could|consider|possibly|"
    r"perhaps|ideally|preferably|prefer|if possible|if available|"
    r"if they exist|if any|if present|where available|when available|"
    r"if (?:it|that|this) helps|if helpful|if useful|try to|"
    r"when possible|where possible|nice to have)\b")
_COND = re.compile(
    r"\b(?:if|unless|only if|only after|after|once|until|when|whenever|"
    r"provided|as long as|in case|wait for|pending|before)\b")
_QUESTION = re.compile(
    r"\?|\b(?:whether|ask|asks|asking|inquire|why|how|what|which|who|"
    r"whom|where|when)\b")
_IMPLEMENT = ("implement", "apply the fix", "write the code",
              "make the change", "deploy", "open a pull request",
              "commit the", "merge the")
_STOP = frozenset("""a an the and or but to of in on for with at by from as
is are be it its this that these those i me my we our you your they them
their do does did not no any all some so if then than into about""".split())


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = (t.replace("’", "'").replace("‘", "'").replace("“", '"')
         .replace("”", '"').replace("‑", "-").replace("–", "-")
         .replace("—", "-"))
    t = re.sub(r"(?<=\w)-(?=\w)", " ", t)
    return re.sub(r"[ \t]+", " ", t)


def _term_re(term: str):
    t = _norm(term)
    left = r"(?<![a-z0-9])" if t[:1].isalnum() else ""
    body = re.escape(t)
    if not t[-1:].isalnum():
        right = ""
    elif re.search(r"\d", t):
        right = r"(?![a-z0-9]|\.\d)"
    elif len(t) <= 3:
        right = r"(?:s|es)?(?![a-z0-9])"
    else:
        right = ""          # longer terms are stems/prefixes
    return re.compile(left + body + right)


def _find(term, seg):
    return [m.start() for m in _term_re(term).finditer(seg)]


def _segments(output: str) -> list:
    out = []
    for line in _norm(output).split("\n"):
        for piece in re.split(r"(?<=[.!?;])\s+", line):
            if piece.strip():
                out.append(piece.strip())
    return out


def _group_hits(group, seg):
    return sorted(p for term in group for p in _find(term, seg))


def _cue_near(cue_re, seg, positions, trailing):
    cues = [m.start() for m in cue_re.finditer(seg)]
    for p in positions:
        for c in cues:
            if (c <= p and p - c <= 80) or (trailing and c > p
                                             and c - p <= 80):
                return True
    return False


def _relation_holds(rel, output: str) -> bool:
    kind = rel["type"]
    if kind == "any":
        return any(_relation_holds(opt, output) for opt in rel["options"])
    if kind == "count":
        low = _norm(output)
        n = sum(len(_find(t, low)) for t in rel["terms"])
        return n >= rel["min"]
    if kind == "order":
        low = _norm(output)
        firsts = [p for t in rel["first"] for p in _find(t, low)]
        thens = [p for t in rel["then"] for p in _find(t, low)]
        return bool(firsts and thens) and min(firsts) < max(thens) \
            and min(firsts) <= min(thens)
    for seg in _segments(output):
        hits = [_group_hits(g, seg) for g in rel["groups"]]
        if not all(hits):
            continue
        if kind == "together":
            return True
        if kind == "negated":
            if all(_cue_near(_NEG, seg, h, rel.get("trailing", False))
                   for h in hits):
                return True
            continue
        if kind == "question" and _QUESTION.search(seg):
            return True
        if kind == "hedged" and _HEDGE.search(seg):
            return True
        if kind == "conditional" and _COND.search(seg):
            return True
    return False


def _negated_at(seg: str, pos: int) -> bool:
    return any(0 <= pos - m.start() <= 60 for m in _NEG.finditer(seg))


def _unnegated(text: str, output: str) -> bool:
    for seg in _segments(output):
        for p in _find(text, seg):
            if not _negated_at(seg, p):
                return True
    return False


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9_./-]*", _norm(text))
            if len(w) >= 3 and w not in _STOP}


def _addresses(clause: str, excerpts) -> bool:
    """A kept excerpt names the lost clause: it contains the clause,
    sits inside it, or shares at least half its content words."""
    want = _words(clause)
    for ex in excerpts:
        e, c = _norm(ex), _norm(clause)
        if c and (c in e or (e and e in c and len(_words(e)) >= 2)):
            return True
        if want and len(want & _words(ex)) * 2 >= len(want):
            return True
    return False


def judge(case, output, path, review_excerpts=()):
    """Independent verdict for one Prompt Engineer result."""
    broken = [r for r in case.get("relations", [])
              if not _relation_holds(r, output)]
    added = [f["text"] for f in case.get("forbid", [])
             if (_unnegated(f["text"], output) if f.get("unless_negated")
                 else bool(_find(f["text"], _norm(output))))]
    intent_escalated = []
    if case.get("intent") in ("diagnosis", "advice", "review"):
        src = _norm(case["source"])
        intent_escalated = [m for m in _IMPLEMENT
                            if not _find(m, src) and _unnegated(m, output)]
    failures = ([r["id"] for r in broken] + [f"added:{a}" for a in added]
                + [f"intent:{m}" for m in intent_escalated])
    if path == tf.PATH_FALLBACK_ORIGINAL:
        verdict = "fallback"
    elif path == tf.PATH_APPLIED:
        verdict = "applied_semantic_failure" if failures else "applied"
    elif path == tf.PATH_NEEDS_REVIEW:
        if not failures:
            verdict = "review_no_loss"
        else:
            ok = all(_addresses(r.get("clause", ""), review_excerpts)
                     for r in broken)
            ok = ok and all(_addresses(a, review_excerpts)
                            for a in added + intent_escalated)
            verdict = "review_addresses_loss" if ok else "review_misdirected"
    else:
        verdict = "error"
    return {"verdict": verdict, "failures": failures}


# ---------------------------------------------------------------------------
# The model run.
# ---------------------------------------------------------------------------

def load_cases():
    doc = json.loads(FIXTURES.read_text())
    return doc, doc["cases"]


def run_case(runner, defn, case):
    t0 = time.monotonic()
    try:
        job = tf.job_for_definition(defn, case["source"],
                                    source_kind="selection")
        res = tf.run_transform(job, runner.generate_fn(), runner.render)
    except Exception as e:
        return None, {"verdict": "error",
                      "failures": [f"harness:{type(e).__name__}"]}, \
            (time.monotonic() - t0) * 1000.0
    j = judge(case, res.output, res.path, res.review_excerpts)
    return res, j, (time.monotonic() - t0) * 1000.0


def _latency(values):
    if not values:
        return {}
    s = sorted(values)
    return {"n": len(s), "mean_ms": round(statistics.mean(s), 1),
            "p50_ms": round(s[len(s) // 2], 1),
            "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))], 1),
            "max_ms": round(s[-1], 1)}


def main():
    args = sys.argv[1:]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args \
        else None
    split = args[args.index("--split") + 1] if "--split" in args else None
    out_json = args[args.index("--json") + 1] if "--json" in args else None
    allow_fallback = "--allow-fallback" in args

    doc, all_cases = load_cases()
    counts = {}
    for c in all_cases:
        counts[c["split"]] = counts.get(c["split"], 0) + 1
    assert counts == EXPECTED_SPLITS, counts
    cases = [c for c in all_cases if not split or c["split"] == split]
    if limit:
        cases = cases[:limit]

    print(f"loading {MODEL} …")
    t0 = time.monotonic()
    runner = ModelRunner(MODEL)
    runner.load()
    print(f"model ready in {time.monotonic() - t0:.1f}s")

    defn = next(d for d in tf.built_ins()
                if d.transform_id == "builtin:prompt_engineer")
    tally = {v: 0 for v in VERDICTS}
    by_split = {}
    latencies = []
    records = []
    for case in cases:
        res, j, wall_ms = run_case(runner, defn, case)
        v = j["verdict"]
        tally[v] += 1
        by_split.setdefault(case["split"], {k: 0 for k in VERDICTS})[v] += 1
        dur = res.duration_ms if res is not None else wall_ms
        latencies.append(dur)
        records.append({
            "case_id": case["case_id"], "split": case["split"],
            "blind": bool(case.get("blind")), "verdict": v,
            "path": res.path if res is not None else None,
            "reason": res.reason if res is not None else None,
            "failures": j["failures"], "duration_ms": dur,
            "review_excerpts": list(res.review_excerpts)
            if res is not None else []})
        tag = "FAIL" if v in FAILING or (v == "fallback"
                                         and not allow_fallback) else "ok  "
        detail = f" failures={j['failures']}" if j["failures"] else ""
        print(f"{tag} {case['case_id']} [{case['split']}] {v}"
              f" ({dur:.0f} ms){detail}")

    summary = {"total": len(cases), "verdicts": tally,
               "by_split": by_split, "latency_all_cases": _latency(latencies),
               "allow_fallback": allow_fallback,
               "fixtures": doc["schema"], "model": MODEL}
    print(json.dumps(summary, indent=1))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps(
            {"summary": summary, "cases": records}, indent=1,
            ensure_ascii=False))
    bad = sum(tally[v] for v in FAILING)
    if not allow_fallback:
        bad += tally["fallback"]
    assert bad == 0, f"{bad} failing Prompt Engineer cases: {tally}"
    print("prompt engineer cases passed: zero semantic failures, zero"
          " misdirected reviews, zero errors"
          + ("" if allow_fallback else ", zero fallbacks"))


if __name__ == "__main__":
    main()
