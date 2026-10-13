"""Fresh comparison inputs kept separate from all earlier experiment results."""
from __future__ import annotations

import argparse
import collections
import hashlib
import re
import time
from .common import *

RUN = ART / "remediation"


def prepare_audio(count=100):
    """Select unused sentence families before any candidate sees the clips."""
    import pyarrow.parquet as pq
    import soundfile as sf
    from lfx.audio import _decode, SR
    destination = RUN / "audio-cases.jsonl"
    if destination.exists():
        return {"already_selected": len(read_jsonl(destination))}
    previous = read_jsonl(OLD_ART / "real/cases.jsonl") + read_jsonl(ART / "real/cases.jsonl")
    hashes = {c["audio_sha256"] for c in previous}
    ids = {c["provenance"].get("sentence_id") for c in previous if c["source"] == "fleurs"}
    source = next((RUN / "data/google__fleurs/parquet-data/en_us").glob("validation-*.parquet"))
    rows = pq.read_table(source).to_pylist()
    chosen = {}
    for i, row in enumerate(rows):
        sid = row["id"]
        if sid in ids:
            continue
        key = sha256_text(row["path"])
        if sid not in chosen or key < chosen[sid][0]:
            chosen[sid] = (key, i)
    selected, duplicate_audio = [], 0
    for sid in sorted(chosen, key=lambda sid: sha256_text(f"remediation:{sid}")):
        i = chosen[sid][1]
        row = rows[i]
        mono, rate = _decode(row["audio"]["bytes"])
        digest = hashlib.sha256(mono.tobytes()).hexdigest()
        if digest in hashes:
            duplicate_audio += 1
            continue
        cid = f"v3-fleurs-{sid}"
        path = RUN / "audio" / (cid + ".wav")
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, mono, SR, subtype="FLOAT")
        hashes.add(digest)
        selected.append({
            "case_id": cid, "family_id": cid, "source": "fleurs", "split": "test",
            "origin": "real_audio", "category": "read_speech",
            "lexical_reference": row["transcription"], "raw_transcription": row["raw_transcription"],
            "reference_kind": "fleurs_normalized_transcription",
            "audio_path": str(path.relative_to(ART)), "source_rate": rate,
            "duration_s": len(mono) / SR, "audio_sha256": digest,
            "provenance": {**CONFIG["datasets"]["fleurs"], "split": "validation", "row": i, "sentence_id": sid}})
        if len(selected) == count:
            break
    if len(selected) != count:
        raise RuntimeError(f"Only {len(selected)} unused audio families available")
    write_jsonl(destination, selected)
    receipt = {"created": utc_now(), "selected": len(selected), "available_families": len(chosen),
               "old_sentence_families_excluded": len(ids), "duplicate_audio_excluded": duplicate_audio,
               "source_sha256": file_sha256(source), "selection_sha256": file_sha256(destination),
               "limitations": "Read speech only; new recordings and sentence families, not proven unseen speakers or continuous long-form speech."}
    write_json(RUN / "audio-selection.json", receipt)
    return receipt


def asr_audio():
    """Run the production Parakeet wrapper once, preserving the raw transcript."""
    import soundfile as sf
    from huggingface_hub import snapshot_download
    from localflow.stt import Transcriber
    from localflow.v2.normalize import normalize, NormalizationPolicy, ContextSnapshot
    from localflow.v2.cleanup import protected_spans_for_cleanup
    destination = RUN / "audio-asr.jsonl"
    records = read_jsonl(destination)
    done = {r["case_id"] for r in records}
    cfg = CONFIG["models"]["asr"]
    transcriber = Transcriber(snapshot_download(cfg["repository_id"], revision=cfg["revision"], local_files_only=True))
    transcriber.load()
    policy = NormalizationPolicy()
    for case in read_jsonl(RUN / "audio-cases.jsonl"):
        if case["case_id"] in done:
            continue
        samples, rate = sf.read(str(ART / case["audio_path"]), dtype="float32", always_2d=True)
        assert rate == 16000 and samples.shape[1] == 1
        start = time.perf_counter()
        raw = transcriber.transcribe(samples[:, 0])
        elapsed = (time.perf_counter() - start) * 1000
        if not raw.strip():
            raise RuntimeError("Empty recognizer output: " + case["case_id"])
        norm = normalize(raw, policy, ContextSnapshot())
        protected = protected_spans_for_cleanup(raw, norm.text, norm.protected, norm.edits)
        records.append({**case, "raw_input": raw, "model_input": norm.text,
                        "protected_spans": [list(s) for s in protected], "asr_ms": elapsed,
                        "normalization_changed": raw != norm.text, "policy_revision": policy.policy_revision,
                        "asr_model": cfg})
        write_jsonl(destination, records)
        if len(records) % 20 == 0:
            print("Transcribed", len(records), flush=True)
    return {"transcribed": len(records)}


def assemble_synthetic(split):
    """Use independent label acceptance, never candidate reachability, to select."""
    from .assemble import Dedup
    from lfx.assemble import production_examples, fixture_texts
    from lfx.synth import normalize_text
    from localflow.v2.cleanup import protected_spans_for_cleanup
    if split not in ("validation", "test"):
        raise ValueError(split)
    destination = RUN / f"synthetic-{split}.jsonl"
    if destination.exists():
        return {"already_assembled": len(read_jsonl(destination))}
    idx = Dedup()
    exclusion_files = [
        OLD_ART / "dataset/train.jsonl", OLD_ART / "dataset/validation.jsonl",
        OLD_ART / "frozen/test_synthetic.jsonl", OLD_ART / "frozen/fixtures.jsonl",
        OLD_ART / "frozen/longform.jsonl",
        *[ART / "dataset" / f"{s}.jsonl" for s in ("train", "validation", "test")],
    ]
    if split == "test":
        # All returned development pairs count as exposed, even rejected labels.
        exclusion_files.append(ART / "pairs/remediation-dev.jsonl")
    for path in exclusion_files:
        for p in read_jsonl(path):
            source = p.get("model_input", p.get("raw_input", ""))
            target = p.get("target", "")
            for text in (source, target, source + " " + target):
                if text.strip():
                    idx.add(text, str(path.relative_to(ART if path.is_relative_to(ART) else OLD_ART)), check=False)
    for text in production_examples() + fixture_texts():
        idx.add(text, "prompt_or_fixture", check=False)
    name = "remediation-dev" if split == "validation" else "remediation-heldout"
    pairs = read_jsonl(ART / "accepted" / f"{name}.jsonl")
    if not pairs:
        raise RuntimeError("Independent verification has not produced accepted labels")
    kept, excluded = [], []
    for pair in sorted(pairs, key=lambda p: p["family_id"]):
        hit = idx.add(pair["model_input"] + " " + pair["target"], pair["family_id"])
        if hit:
            excluded.append({"case_id": pair["case_id"], "reason": "duplicate", "matched": hit})
            continue
        norm = normalize_text(pair["raw_input"])
        if norm.text != pair["model_input"]:
            raise RuntimeError("Frozen label normalization changed")
        pair["protected_spans"] = [list(p) for p in protected_spans_for_cleanup(
            pair["raw_input"], norm.text, norm.protected, norm.edits)]
        offsets, cursor = [], 0
        for line in pair.get("gold_lines", []):
            match = re.search(re.escape(line), pair["model_input"][cursor:], re.IGNORECASE)
            if match is None:
                raise RuntimeError("Missing independently checked correction span")
            start, end = cursor + match.start(), cursor + match.end()
            offsets.append([start, end])
            cursor = end
        pair["gold_offsets"] = offsets
        kept.append(pair)
    write_jsonl(destination, kept)
    write_json(RUN / f"synthetic-{split}-selection.json", {
        "created": utc_now(), "independently_accepted": len(pairs), "kept": len(kept),
        "excluded": excluded, "sha256": file_sha256(destination),
        "categories": dict(collections.Counter(p["category"] for p in kept)),
        "noops": sum(p["is_noop"] for p in kept),
        "method": "Exact and 5-token-shingle Jaccard 0.6 exclusions against earlier datasets, prompts, fixtures and fresh development pairs; no model-based selection."})
    return {"kept": len(kept), "excluded": len(excluded)}


def freeze_final():
    destination = RUN / "final-cases.jsonl"
    receipt_path = RUN / "freeze.json"
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        assert file_sha256(destination) == receipt["cases_sha256"]
        return receipt
    if any((ART / "eval").glob("fresh-*.jsonl")):
        raise RuntimeError("Fresh evaluation already started before the freeze")
    synthetic = read_jsonl(RUN / "synthetic-test.jsonl")
    audio = read_jsonl(RUN / "audio-asr.jsonl")
    if not synthetic or len(audio) != len(read_jsonl(RUN / "audio-cases.jsonl")):
        raise RuntimeError("Fresh synthetic labels or audio transcripts are incomplete")
    cases = synthetic + audio
    assert len({c["case_id"] for c in cases}) == len(cases)
    write_jsonl(destination, cases)
    receipt = {"created": utc_now(), "cases_sha256": file_sha256(destination),
               "synthetic": len(synthetic), "audio": len(audio),
               "candidate_outputs_existed": False,
               "source_hashes": {n: file_sha256(ROOT / "localflow/v2/cleanup" / n)
                                 for n in ("engine.py", "validation.py", "prompts.py", "document_nodes.py")},
               "labels": "Synthetic Sonnet generation and independent Opus verification; audio corpus references. No human reference adjudication."}
    write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare-audio", "asr", "validation", "test", "freeze"))
    args = parser.parse_args()
    action = {"prepare-audio": prepare_audio, "asr": asr_audio, "freeze": freeze_final}.get(args.action)
    print(action() if action else assemble_synthetic(args.action))
