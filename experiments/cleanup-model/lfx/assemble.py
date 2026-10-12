"""Dedup, verification filtering, final split files and the test freeze."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from .common import ART, CONFIG, REPO_ROOT, EXP_DIR, file_sha256, read_json, read_jsonl, sha256_json, \
    sha256_text, utc_now, write_json, write_jsonl
from .synth import jaccard, shingles

DATA = ART / "dataset"
FROZEN = ART / "frozen"


def production_examples() -> list[str]:
    from localflow.v2.cleanup import prompts
    from localflow.v2.cleanup.engine import CORRECTIONS_EXAMPLES
    return [a for a, _ in prompts.EXAMPLES] + [b for _, b in prompts.EXAMPLES] + [a for a, _ in CORRECTIONS_EXAMPLES]


def fixture_texts() -> list[str]:
    out = []
    for name in ("fixtures_fidelity.json", "fixtures_literal.json"):
        data = json.loads((REPO_ROOT / "tests/v2/fidelity" / name).read_text())
        out += [c["input"] for c in data["cases"]]
    return out


def dedup(pairs_by_split: dict[str, list[dict]]) -> tuple[dict, Counter]:
    """Exact and near-duplicate removal at family level. Order of authority:
    test > validation > train (later splits lose near-duplicates), and every
    family is checked against production prompt examples and the LocalFlow
    fixture slice."""
    th = CONFIG["targets"]["dedup_jaccard"]
    reserved = [shingles(t) for t in production_examples() + fixture_texts()]
    kept_sh: list[tuple[str, set]] = []
    dropped = Counter()
    out = {}
    for split in ("test", "validation", "train"):
        fams = defaultdict(list)
        for p in pairs_by_split.get(split, []):
            fams[p["family_id"]].append(p)
        keep = []
        seen_exact = set()
        for fid, group in fams.items():
            base = next((p for p in group if p["variant"] == "base"), group[0])
            text = base["model_input"]
            key = sha256_text(" ".join(text.casefold().split()))
            sh = shingles(text) | shingles(base["target"])
            if key in seen_exact:
                dropped[f"{split}:exact_duplicate"] += 1
                continue
            if any(jaccard(sh, r) >= th for r in reserved):
                dropped[f"{split}:near_prompt_or_fixture"] += 1
                continue
            hit = next((s for s, other in kept_sh if jaccard(sh, other) >= th), None)
            if hit is not None:
                dropped[f"{split}:near_duplicate_of_{hit}"] += 1
                continue
            seen_exact.add(key)
            kept_sh.append((split, sh))
            keep.extend(group)
        out[split] = keep
    return out, dropped


def apply_verdicts(pairs: list[dict], verdicts: dict, require_verified: bool) -> tuple[list[dict], Counter]:
    """Families inherit their base pair's verdict (variants are deterministic
    transforms of a verified base)."""
    fam_verdict = {}
    for p in pairs:
        v = verdicts.get(p["pair_id"])
        if v is not None and p["variant"] == "base":
            fam_verdict[p["family_id"]] = v
    kept, dropped = [], Counter()
    for p in pairs:
        v = fam_verdict.get(p["family_id"])
        p["verification"] = v["verdict"] if v else "NOT_SAMPLED"
        p["verification_reasons"] = v["reasons"] if v else []
        if v and v["verdict"] == "FAIL":
            dropped["verifier_fail"] += 1
            continue
        if require_verified and (not v or v["verdict"] != "PASS"):
            dropped["not_verified"] += 1
            continue
        kept.append(p)
    return kept, dropped


def freeze(test_pairs: list[dict], extras: dict) -> dict:
    """Freeze test cases, references, metric code and decision rules."""
    FROZEN.mkdir(parents=True, exist_ok=True)
    if (FROZEN / "freeze.json").exists():
        raise RuntimeError("freeze.json already exists; the test set is frozen")
    write_jsonl(FROZEN / "test_synthetic.jsonl", test_pairs)
    files = {"test_synthetic.jsonl": file_sha256(FROZEN / "test_synthetic.jsonl")}
    for name, rows in extras.items():
        write_jsonl(FROZEN / name, rows)
        files[name] = file_sha256(FROZEN / name)
    code = {f: file_sha256(EXP_DIR / "lfx" / f) for f in ("score.py", "audio.py", "synth.py")}
    rules = CONFIG["rules"]
    rec = {"frozen": utc_now(), "files": files, "metric_code_sha256": code, "rules": rules,
           "rules_sha256": sha256_json(rules), "config_sha256": file_sha256(EXP_DIR / "config.yaml"),
           "counts": {"test_synthetic": len(test_pairs), **{k: len(v) for k, v in extras.items()}},
           "note": "No candidate model output existed when this file was written."}
    write_json(FROZEN / "freeze.json", rec)
    return rec


# ---------------------------------------------------------------- frozen evaluation slices

def real_cases() -> list[dict]:
    """Real-audio cases: model input is the LocalFlow-normalized Parakeet text."""
    asr = {r["case_id"]: r for r in read_jsonl(ART / "real" / "asr.jsonl")}
    out = []
    for c in read_jsonl(ART / "real" / "cases.jsonl"):
        a = asr.get(c["case_id"], {})
        row = {k: c[k] for k in ("case_id", "family_id", "source", "origin", "category", "split", "duration_s",
                                 "reference_kind", "provenance")}
        row.update({"raw_asr": a.get("raw_asr"), "model_input": a.get("normalized") or "",
                    "protected_spans": a.get("protected_spans", []), "asr_status": a.get("status"),
                    "normalization_changed": a.get("normalization_changed"), "destination_profile": None,
                    "is_noop": None})
        for k in ("lexical_reference", "raw_transcription", "verbatim_reference", "contract_refs", "transcript_c",
                  "transcript_annotated"):
            if k in c:
                row[k] = c[k]
        out.append(row)
    return out


def fixture_cases() -> list[dict]:
    """LocalFlow's hand-written fidelity/literal fixtures, fed exactly as
    tests/v2/fidelity feeds them (raw input, protected needles located)."""
    out = []
    for name in ("fixtures_fidelity.json", "fixtures_literal.json"):
        data = json.loads((REPO_ROOT / "tests/v2/fidelity" / name).read_text())
        for c in data["cases"]:
            spans = []
            for needle in c.get("protected", []):
                i = c["input"].find(needle)
                if i >= 0:
                    spans.append([i, i + len(needle), "literal"])
            out.append({"case_id": c["case_id"], "family_id": c.get("family_id", c["case_id"]),
                        "source": "localflow_fixtures", "origin": "hand_written_fixture", "category": ",".join(c.get("tags", [])),
                        "model_input": c["input"], "protected_spans": spans,
                        "destination_profile": c.get("destination_profile"), "expect": c.get("expect", []),
                        "forbid": c.get("forbid", []), "forbid_on_fallback": c.get("forbid_on_fallback", []),
                        "fixture_file": name, "is_noop": None})
    return out


def longform_cases(test_pairs: list[dict], n: int = 40, seed: int = 41) -> list[dict]:
    """Multi-window dictations (>200 words) made by joining test families.
    Scored on facts, ending, omissions and additions only."""
    from localflow.v2.cleanup import protected_spans_for_cleanup
    from .synth import normalize_text
    rng = random.Random(seed)
    base = [p for p in test_pairs if p["variant"] == "base" and not p.get("vocabulary_pairs")
            and "\n" not in p["target"] and len(p["model_input"].split()) >= 40]
    rng.shuffle(base)
    out, i = [], 0
    while len(out) < n and i < len(base):
        group, words_n = [], 0
        while words_n <= 215 and i < len(base):
            group.append(base[i])
            words_n += len(base[i]["model_input"].split())
            i += 1
        if words_n <= 215:
            break
        raw = " ".join(p["raw_input"] for p in group)
        norm = normalize_text(raw)
        try:
            spans = protected_spans_for_cleanup(raw, norm.text, norm.protected, norm.edits)
        except ValueError:
            continue
        lines, offsets, cursor, low = [], [], 0, norm.text.lower()
        for p in group:
            for line in p["gold_lines"]:
                j = low.find(line.lower(), cursor)
                if j >= 0:
                    lines.append(line)
                    offsets.append([j, j + len(line)])
                    cursor = j + len(line)
        out.append({"case_id": f"long-{len(out):03d}", "family_id": "+".join(p["family_id"] for p in group),
                    "source": "synthetic_longform", "origin": "synthetic", "category": "long_form_multi_window",
                    "model_input": norm.text, "raw_input": raw, "protected_spans": [list(s) for s in spans],
                    "target": " ".join(p["target"] for p in group),
                    "critical_facts": [f for p in group for f in p["critical_facts"]],
                    "obsolete_values": [o for p in group for o in p["obsolete_values"]],
                    "gold_lines": lines, "gold_offsets": offsets, "destination_profile": None, "is_noop": False,
                    "word_count": len(norm.text.split()), "parts": [p["pair_id"] for p in group]})
    return out


# ---------------------------------------------------------------- stage entry points

def _wave_pairs(wave: str) -> list[dict]:
    return [p for p in read_jsonl(ART / "pairs" / f"{wave}.jsonl") if p["accepted_gates"]]


def _verdicts(name: str) -> dict:
    from .datagen import verdicts
    return verdicts(name) if (ART / "claude" / name / "outcomes.json").exists() else {}


def freeze_eval() -> dict:
    """Freeze the synthetic test set (verified PASS only), the validation set,
    the real-audio / fixture / long-form slices and the decision rules —
    before any candidate output on them exists."""
    from .score import mde
    if (FROZEN / "freeze.json").exists():
        return read_json(FROZEN / "freeze.json")
    test, d_test = apply_verdicts(_wave_pairs("gen-test"), _verdicts("ver-test"), require_verified=True)
    val, d_val = apply_verdicts(_wave_pairs("gen-validation"), _verdicts("ver-validation"), require_verified=True)
    kept, d_dup = dedup({"test": test, "validation": val})
    test, val = kept["test"], kept["validation"]
    cap = CONFIG["targets"]["test_synthetic_max"]
    if len(test) > cap:
        fams = sorted({p["family_id"] for p in test}, key=lambda f: sha256_text(f))
        keep_f, n = set(), 0
        for f in fams:
            size = sum(1 for p in test if p["family_id"] == f)
            if n + size > cap:
                continue
            keep_f.add(f)
            n += size
        test = [p for p in test if p["family_id"] in keep_f]
    for p in test + val:
        p["case_id"] = p["pair_id"]
        p["source"] = "synthetic"
        p["origin"] = "synthetic_product_autogenerated"
    DATA.mkdir(parents=True, exist_ok=True)
    write_jsonl(DATA / "validation.jsonl", val)
    # Minimum detectable effect from pilot-dev base rates (A on 60 pilot train pairs).
    n_repair = sum(1 for p in test if not p["is_noop"])
    power = {"basis": "A on pilot train pairs (dev): model-only damage 0.15, repair success 0.48",
             "mde_damage_pp_unpaired": round(100 * mde(0.15, len(test)), 2),
             "mde_repair_pp_unpaired": round(100 * mde(0.48, n_repair), 2),
             "note": "Unpaired approximation; the paired family bootstrap used for decisions is tighter. "
                     "Synthetic test grown to the planned maximum (~500) for this reason."}
    extras = {"real_audio.jsonl": real_cases(), "fixtures.jsonl": fixture_cases(),
              "longform.jsonl": longform_cases(test)}
    rec = freeze(test, extras)
    rec["power"] = power
    rec["dropped"] = {"test": dict(d_test), "validation": dict(d_val), "dedup": dict(d_dup)}
    rec["validation_pairs"] = len(val)
    write_json(FROZEN / "freeze.json", rec)
    return rec


def added_words(p: dict) -> list[str]:
    """Words in the gold target that the speaker never said (number words and
    digits compare equal; vocabulary canonicals are authorized). LocalFlow's
    validator tolerates some additions (e.g. a leading "Please"), so training
    data gets this deterministic check as well."""
    from .score import lex
    canon = Counter(w for _, c in p.get("vocabulary_pairs") or [] for w in lex(c))
    return list((Counter(lex(p["target"])) - Counter(lex(p["model_input"])) - canon).elements())


def finalize_train() -> dict:
    """Train pairs: verifier FAILs dropped (unsampled pairs kept, labelled),
    deduplicated against the frozen test/validation families; captures for
    the kept pairs only."""
    test = read_jsonl(FROZEN / "test_synthetic.jsonl")
    val = read_jsonl(DATA / "validation.jsonl")
    train_all = _wave_pairs("gen-pilot") + _wave_pairs("gen-train")
    verdicts = {**_verdicts("ver-pilot"), **_verdicts("ver-train"), **_verdicts("ver-train-rest")}
    train, d_ver = apply_verdicts(train_all, verdicts, require_verified=False)
    adders = {p["family_id"] for p in train if added_words(p)}
    d_ver["target_adds_words"] = sum(1 for p in train if p["family_id"] in adders)
    train = [p for p in train if p["family_id"] not in adders]
    kept, d_dup = dedup({"test": test, "validation": val, "train": train})
    train = kept["train"]
    write_jsonl(DATA / "train.jsonl", train)
    ids = {p["pair_id"] for p in train}
    val_ids = {p["pair_id"] for p in val}
    caps_train, caps_val = [], []
    for wave in ("gen-pilot", "gen-train", "gen-validation"):
        for c in read_jsonl(ART / "captures" / f"{wave}.jsonl"):
            if c["pair_id"] in ids:
                caps_train.append(c)
            elif c["pair_id"] in val_ids:
                caps_val.append(c)
    write_jsonl(DATA / "train_captures.jsonl", caps_train)
    write_jsonl(DATA / "validation_captures.jsonl", caps_val)
    stats = {"assembled": utc_now(), "train_pairs": len(train), "train_families": len({p["family_id"] for p in train}),
             "train_noop": sum(p["is_noop"] for p in train),
             "train_by_variant": dict(Counter(p["variant"] for p in train)),
             "train_by_category": dict(Counter(p["category"] for p in train)),
             "train_verification": dict(Counter(p["verification"] for p in train)),
             "validation_pairs": len(val), "test_pairs": len(test),
             "dropped": {"verifier": dict(d_ver), "dedup": dict(d_dup)},
             "captures": {"train": len(caps_train), "validation": len(caps_val)}}
    write_json(DATA / "stats.json", stats)
    return stats
