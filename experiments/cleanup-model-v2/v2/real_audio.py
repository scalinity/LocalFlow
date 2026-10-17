"""Unexposed public recordings through LocalFlow's actual Parakeet pipeline."""
from __future__ import annotations

import hashlib
import json
from .common import *


def prepare():
    import pyarrow.parquet as pq
    import soundfile as sf
    from lfx.audio import _decode, ds_references, SR
    destination = ART / "real/cases.jsonl"
    if destination.exists():
        print("Public audio selection already exists"); return
    old = read_jsonl(OLD_ART / "real/cases.jsonl")
    old_hashes = {c["audio_sha256"] for c in old}
    old_fleurs_ids = {c["provenance"].get("sentence_id") for c in old if c["source"] == "fleurs"}
    dsfile = next((OLD_ART / "data/amaai-lab__DisfluencySpeech/data").glob("validation-*.parquet"))
    dsrows = pq.read_table(dsfile).to_pylist()
    rows, duplicates = [], 0

    def save_audio(row, raw_audio):
        nonlocal duplicates
        mono, rate = _decode(raw_audio["bytes"])
        digest = hashlib.sha256(mono.tobytes()).hexdigest()
        if digest in old_hashes:
            duplicates += 1; return
        path = ART / "audio" / (row["case_id"] + ".wav")
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, mono, SR, subtype="FLOAT")
        row.update(audio_path=str(path.relative_to(ART)), source_rate=rate,
                   duration_s=len(mono)/SR, audio_sha256=digest, origin="real_audio")
        rows.append(row)

    # Rows 0:60 were exposed as style examples during the original experiment.
    for i in range(60, len(dsrows)):
        r = dsrows[i]
        cid = f"v2-ds-val-{i:04d}"
        row = {"case_id": cid, "family_id": cid, "source": "disfluencyspeech",
               "split": "validation" if i < 100 else "test", "category": "conversational_disfluent",
               "verbatim_reference": r["transcript_a"], "contract_refs": ds_references(r["transcript_annotated"]),
               "reference_kind": "machine_derived_contract_reference",
               "provenance": {**CONFIG["datasets"]["disfluencyspeech"], "split": "validation", "row": i}}
        save_audio(row, r["audio"])
    flfile = next((OLD_ART / "data/google__fleurs/parquet-data/en_us").glob("test-*.parquet"))
    flrows = pq.read_table(flfile).to_pylist()
    chosen = {}
    for i, r in enumerate(flrows):
        if r["id"] in old_fleurs_ids:
            continue
        key = hashlib.sha256(r["path"].encode()).hexdigest()
        if r["id"] not in chosen or key < chosen[r["id"]][0]:
            chosen[r["id"]] = (key, i)
    ordered = sorted(chosen, key=lambda sid: hashlib.sha256(f"v2:{sid}".encode()).hexdigest())
    for j, sid in enumerate(ordered[:140]):
        i = chosen[sid][1]; r = flrows[i]; cid = f"v2-fleurs-{sid}"
        row = {"case_id": cid, "family_id": cid, "source": "fleurs",
               "split": "validation" if j < 30 else "test", "category": "read_speech",
               "lexical_reference": r["transcription"], "raw_transcription": r["raw_transcription"],
               "reference_kind": "fleurs_normalized_transcription",
               "provenance": {**CONFIG["datasets"]["fleurs"], "split": "test", "row": i, "sentence_id": sid}}
        save_audio(row, r["audio"])
    write_jsonl(destination, rows)
    write_json(ART / "real/selection.json", {
        "selected_at": utc_now(), "n": len(rows), "duplicate_audio_excluded": duplicates,
        "source_files": {str(p.relative_to(OLD_ART)): file_sha256(p) for p in (dsfile, flfile)},
        "counts": {s: sum(c["split"] == s for c in rows) for s in ("test", "validation")},
        "method": "Unused DS validation rows 60 onward; FLEURS sentence ids absent from original benchmark, one recording per sentence, deterministic hash order.",
        "limitations": "Fresh recordings and sentence families, not a claim of unseen speakers. These clips do not constitute continuous long-form speech."})
    print(json.dumps({"selected":len(rows), "test":sum(c['split']=='test' for c in rows)}))


def finalize():
    from localflow.v2.normalize import normalize, NormalizationPolicy, ContextSnapshot
    from localflow.v2.cleanup import protected_spans_for_cleanup
    cases = read_jsonl(ART / "real/cases.jsonl")
    asr = {c["case_id"]: c for c in read_jsonl(ART / "real/asr.jsonl")}
    complete = []
    for c in cases:
        a = asr.get(c["case_id"], {})
        if a.get("status") != "ok":
            continue
        complete.append({**c, "raw_input": a["raw_asr"], "model_input": a["normalized"],
                         "protected_spans": a["protected_spans"], "asr_ms": a["asr_ms"],
                         "normalization_changed": a["normalization_changed"]})
    for split in ("test", "validation"):
        dest = ART / "dataset" / f"real_{split}.jsonl"
        if dest.exists():
            raise RuntimeError("Real evaluation set already finalized")
        write_jsonl(dest, [c for c in complete if c["split"] == split])
    write_json(ART / "real/freeze.json", {"time":utc_now(), "n":len(complete),
               "files":{s:file_sha256(ART/"dataset"/f"real_{s}.jsonl") for s in ("test","validation")},
               "excluded":len(cases)-len(complete), "candidate_evaluation_started":False})
    print(json.dumps({"complete":len(complete), "excluded":len(cases)-len(complete)}))


if __name__ == "__main__":
    import sys
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "asr":
        from lfx.audio import asr
        print(asr())
    else:
        finalize()
