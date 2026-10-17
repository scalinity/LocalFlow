"""Fresh read, recreated-disfluent and spontaneous meeting recordings."""
from __future__ import annotations

import argparse
import collections
import hashlib
import re
from .common import *

RUN = ART / "refinement"


def prepare(count=100, *, retained=(), extra_exclusions=()):
    import pyarrow.parquet as pq
    import soundfile as sf
    from lfx.audio import _decode, ds_references, SR, lexical, FILLERS
    destination = RUN / "audio-cases.jsonl"
    if destination.exists():
        return {"already_selected": len(read_jsonl(destination))}
    old_paths = [OLD_ART / "real/cases.jsonl", ART / "real/cases.jsonl",
                 ART / "remediation/audio-cases.jsonl"]
    old = [c for p in old_paths for c in read_jsonl(p)] + list(retained) + list(extra_exclusions)
    hashes = {c["audio_sha256"] for c in old}
    sentence_ids = {c["provenance"].get("sentence_id") for c in old if c["source"] == "fleurs"}
    references = set()
    for c in old:
        for text in [c.get("verbatim_reference", ""), c.get("lexical_reference", ""),
                     *c.get("contract_refs", {}).values()]:
            if text:
                references.add(" ".join(lexical(text)))
    downloads = read_json(RUN / "audio-downloads.json")
    if not downloads:
        raise RuntimeError("Pinned audio sources have not been downloaded")
    files = [r for r in downloads["files"] if r["filename"].endswith(".parquet")]
    candidates = collections.defaultdict(list)
    for record in files:
        path = Path(record["path"])
        if file_sha256(path) != record["sha256"]:
            raise RuntimeError("Downloaded source changed")
        pf = pq.ParquetFile(path)
        names = [n for n in pf.schema_arrow.names if n != "audio"]
        for i, row in enumerate(pf.read(columns=names).to_pylist()):
            dataset = record["dataset"]
            text = row["transcription"] if dataset == "fleurs" else row["transcript_a"] if dataset == "disfluencyspeech" else row["text"]
            normalized = " ".join(lexical(text))
            if normalized in references or len(normalized.split()) < 12:
                continue
            if dataset == "fleurs" and row["id"] in sentence_ids:
                continue
            key = f"{dataset}:{record['filename']}:{i}"
            candidates[dataset].append((sha256_text("refinement-audio:" + key), record, i, row))
    selected, discarded = list(retained), collections.Counter()
    for dataset in ("fleurs", "disfluencyspeech", "ami"):
        needed = count - sum(c["source"] == dataset for c in retained)
        if needed < 0:
            raise ValueError("Retained clips exceed the requested source count")
        if needed == 0:
            continue
        chosen = []
        # Decode in file batches, then restore deterministic selection order.
        ordered = sorted(candidates[dataset], key=lambda r: r[0])
        cache = {}
        for order, record, index, row in ordered:
            transcript = row["transcription"] if dataset == "fleurs" else row["transcript_a"] if dataset == "disfluencyspeech" else row["text"]
            reference_key = " ".join(lexical(transcript))
            if reference_key in references:
                discarded["duplicate_reference"] += 1
                continue
            path = Path(record["path"])
            if path not in cache:
                cache[path] = pq.read_table(path, columns=["audio"])["audio"]
            mono, rate = _decode(cache[path][index].as_py()["bytes"])
            digest = hashlib.sha256(mono.tobytes()).hexdigest()
            if digest in hashes:
                discarded["duplicate_audio"] += 1
                continue
            if dataset == "fleurs" and row["id"] in sentence_ids:
                discarded["duplicate_sentence_family"] += 1
                continue
            cid = f"v4-{dataset}-" + sha256_text(record["filename"] + ":" + str(index))[:12]
            provenance = {"repo": record["repo"], "revision": record["revision"],
                          "file": record["filename"], "row": index,
                          "split": "test" if dataset == "ami" else "train",
                          "license": "Apache-2.0" if dataset == "disfluencyspeech" else "CC-BY-4.0"}
            case = {"case_id": cid, "family_id": cid, "source": dataset,
                    "split": "test", "origin": "real_audio", "provenance": provenance}
            if dataset == "fleurs":
                case.update(category="read_speech", lexical_reference=row["transcription"],
                            raw_transcription=row["raw_transcription"], reference_kind="fleurs_normalized_transcription")
                provenance["sentence_id"] = row["id"]
                sentence_ids.add(row["id"])
            elif dataset == "disfluencyspeech":
                case.update(category="studio_recreated_disfluency", verbatim_reference=row["transcript_a"],
                            contract_refs=ds_references(row["transcript_annotated"]),
                            reference_kind="machine_derived_contract_reference")
            else:
                # This reference removes only explicit pure fillers. No guessed
                # correction, grammatical rewrite or reference polishing.
                words = [w for w in row["text"].split() if re.sub(r"[^\w]", "", w).casefold() not in FILLERS]
                case.update(category="spontaneous_meeting", verbatim_reference=row["text"],
                            contract_refs={"ref_keep": row["text"], "ref_drop": " ".join(words)},
                            reference_kind="ami_verbatim_and_pure_filler_removed")
                provenance.update({k: row[k] for k in ("meeting_id", "audio_id", "speaker_id", "microphone_id", "begin_time", "end_time")})
                case["family_id"] = "ami-" + row["meeting_id"]
            out = RUN / "audio" / (cid + ".wav")
            out.parent.mkdir(parents=True, exist_ok=True)
            sf.write(out, mono, SR, subtype="FLOAT")
            case.update(audio_path=str(out.relative_to(ART)), source_rate=rate,
                        duration_s=len(mono) / SR, audio_sha256=digest)
            chosen.append(case)
            hashes.add(digest)
            references.add(reference_key)
            if len(chosen) == needed:
                break
        if len(chosen) != needed:
            raise RuntimeError(f"Only {len(chosen)} eligible {dataset} clips, expected {needed}")
        selected.extend(chosen)
    write_jsonl(destination, selected)
    receipt = {"created": utc_now(), "selected": len(selected), "sha256": file_sha256(destination),
               "counts": dict(collections.Counter(c["category"] for c in selected)),
               "duration_s": sum(c["duration_s"] for c in selected), "discarded": dict(discarded),
               "old_audio_cases_excluded": len(old),
               "retained_unexposed_clips": len(retained),
               "additional_exposed_clips_excluded": len(extra_exclusions),
               "ami_meetings": sorted({c["provenance"]["meeting_id"] for c in selected if c["source"] == "ami"}),
               "source_files": {r["filename"]: r["sha256"] for r in files},
               "continuous_long_form": "NOT_AVAILABLE: released utterance segments; no concatenation claimed as continuous audio",
               "limitations": "New experiment recordings; pretrained-model exposure and unseen speakers unverified. DisfluencySpeech is a single-speaker studio recreation. AMI includes elicited role-play meetings; references are not manually reviewed cleanup targets."}
    write_json(RUN / "audio-selection.json", receipt)
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["prepare", "asr"])
    args = p.parse_args()
    if args.stage == "prepare":
        result = prepare()
    else:
        from .remediation import asr_audio
        result = asr_audio(RUN)
    print(__import__("json").dumps(result))
