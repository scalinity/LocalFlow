"""Public real-audio cases: selection, decoding, references and LocalFlow ASR.

``prepare`` (LocalAI venv) selects cases deterministically before any model
output exists, writes 16 kHz mono float WAVs and machine-derived references.
``asr`` (LocalFlow's own .venv) runs the production Parakeet path once:
``localflow.stt.Transcriber`` -> ``normalize`` -> ``protected_spans_for_cleanup``.
"""

from __future__ import annotations

import glob
import hashlib
import io
import re
import sys
import time
from pathlib import Path

from .common import ART, CONFIG, read_jsonl, sha256_text, utc_now, write_json, write_jsonl

AUDIO_DIR = ART / "audio"
CASES = ART / "real" / "cases.jsonl"
ASR_OUT = ART / "real" / "asr.jsonl"
SR = 16000

# Mirrors localflow.v2.cleanup.validation: required filler deletions and the
# optional phrase-initial interjector deletions.
FILLERS = {"um", "uh", "erm", "ehm", "hmm", "mhm"}
INTERJECTORS = {"oh", "well", "okay", "so"}
CORRECTION_EDIT_TERMS = {"i mean", "no wait", "no sorry", "actually", "no actually", "sorry", "scratch that"}


# ---------------------------------------------------------------- references

def lexical(text: str) -> list[str]:
    """Shared WER normalizer: casefold, hyphens to spaces, keep word-internal
    apostrophes, drop other punctuation."""
    text = text.casefold().replace("’", "'")
    text = re.sub(r"[-–—/]", " ", text)
    text = re.sub(r"[^\w\s']", " ", text)
    return [w.strip("'") for w in text.split() if w.strip("'")]


def _strip_braces(text: str, keep_types: set[str], optional_drop) -> tuple[str, str]:
    """Return (keep_version, drop_version) for {X ...} groups."""
    def repl(keep: bool):
        def f(m):
            kind, body = m.group(1), m.group(2).strip()
            word = re.sub(r"[^\w\s']", "", body).strip().lower()
            if kind == "F":
                if word in FILLERS:
                    return " "
                if word in INTERJECTORS:
                    return " " if not keep else f" {body} "
                return f" {body} "
            if kind in keep_types:
                if not keep and optional_drop(kind, word):
                    return " "
                return f" {body} "
            return f" {body} "
        return f
    pat = re.compile(r"\{([A-Z])\s+([^{}]*?)\}")
    return pat.sub(repl(True), text), pat.sub(repl(False), text)


def ds_references(annotated: str) -> dict:
    """Machine-derived LocalFlow-contract references from transcript_annotated.

    ref_keep: verbatim words minus pure fillers and non-speech.
    ref_drop: additionally drops phrase-initial interjectors (oh/well/okay/so,
    which the validator permits deleting) and reparanda whose restart carries
    an explicit correction editing term ({E I mean} etc.).
    Scoring takes the per-utterance minimum WER over both."""
    text = re.sub(r"<[^<>]*>", " ", annotated)          # non-speech events

    def restart_keep(m):
        return f" {m.group(1)} {m.group(2)} "

    def restart_drop(m):
        rep, repair = m.group(1), m.group(2)
        e = re.search(r"\{E\s+([^{}]*?)\}", repair)
        term = re.sub(r"[^\w\s]", "", e.group(1)).strip().lower() if e else ""
        if term in CORRECTION_EDIT_TERMS:
            return " " + re.sub(r"\{E\s+[^{}]*?\}", " ", repair, count=1) + " "
        if lexical(rep) and lexical(repair)[: len(lexical(rep))] == lexical(rep):
            return f" {repair} "                          # exact restart repetition
        return f" {rep} {repair} "

    restart = re.compile(r"\[\s*([^\[\]]*?)\s*\+\s*([^\[\]]*?)\s*\]")
    keep, drop = text, text
    for _ in range(3):                                    # nested restarts
        keep, drop = restart.sub(restart_keep, keep), restart.sub(restart_drop, drop)
    optional = lambda kind, word: kind == "D" and word in INTERJECTORS
    keep, _ = _strip_braces(keep, {"D", "C", "E", "A"}, optional)
    _, drop = _strip_braces(drop, {"D", "C", "E", "A"}, optional)
    clean = lambda t: re.sub(r"\s+", " ", re.sub(r"(?<!\w)--?(?!\w)", " ", t)).strip()
    return {"ref_keep": clean(keep), "ref_drop": clean(drop)}


# ---------------------------------------------------------------- prepare

def _decode(audio_bytes: bytes):
    import numpy as np
    import soundfile as sf
    data, rate = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=True)
    mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
    if rate != SR:
        import soxr
        mono = soxr.resample(mono, rate, SR, quality="HQ").astype(np.float32)
    return mono, rate


def prepare() -> dict:
    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf
    if CASES.exists():
        return {"skipped": True, "cases": len(read_jsonl(CASES))}
    data_dir = ART / "data"
    cases, problems = [], []

    ds_cfg = CONFIG["datasets"]["disfluencyspeech"]
    ds_file = glob.glob(str(data_dir / "amaai-lab__DisfluencySpeech/data/test-*.parquet"))[0]
    table = pq.read_table(ds_file)
    for i, row in enumerate(table.to_pylist()[: CONFIG["targets"]["disfluencyspeech_cases"]]):
        cid = f"ds-test-{i:04d}"
        try:
            mono, rate = _decode(row["audio"]["bytes"])
            path = AUDIO_DIR / "disfluencyspeech" / f"{cid}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(path, mono, SR, subtype="FLOAT")
            refs = ds_references(row["transcript_annotated"])
            cases.append({
                "case_id": cid, "source": "disfluencyspeech", "split": "test",
                "origin": "real_audio", "family_id": cid, "category": "conversational_disfluent",
                "audio_path": str(path.relative_to(ART)), "source_rate": rate,
                "duration_s": round(len(mono) / SR, 3),
                "audio_sha256": hashlib.sha256(mono.tobytes()).hexdigest(),
                "transcript_annotated": row["transcript_annotated"],
                "verbatim_reference": row["transcript_a"],
                "transcript_c": row["transcript_c"],
                "contract_refs": refs,
                "reference_kind": "machine_derived_contract_reference",
                "provenance": {"repo": ds_cfg["repo"], "revision": ds_cfg["revision"],
                               "split": "test", "row": i, "license": ds_cfg["license"]}})
        except Exception as exc:
            problems.append({"case_id": cid, "stage": "decode", "error": f"{type(exc).__name__}: {exc}"})

    fl_cfg = CONFIG["datasets"]["fleurs"]
    fl_file = glob.glob(str(data_dir / "google__fleurs/parquet-data/en_us/test-*.parquet"))[0]
    table = pq.read_table(fl_file)
    rows = table.to_pylist()
    by_sentence: dict = {}
    for idx, r in enumerate(rows):
        key = hashlib.sha256(r["path"].encode()).hexdigest()
        cur = by_sentence.get(r["id"])
        if cur is None or key < cur[0]:
            by_sentence[r["id"]] = (key, idx)
    chosen = sorted(by_sentence, key=lambda sid: hashlib.sha256(str(sid).encode()).hexdigest())
    for sid in chosen[: CONFIG["targets"]["fleurs_cases"]]:
        idx = by_sentence[sid][1]
        r = rows[idx]
        cid = f"fleurs-{sid}"
        try:
            mono, rate = _decode(r["audio"]["bytes"])
            path = AUDIO_DIR / "fleurs" / f"{cid}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(path, mono, SR, subtype="FLOAT")
            cases.append({
                "case_id": cid, "source": "fleurs", "split": "test", "origin": "real_audio",
                "family_id": cid, "category": "read_speech",
                "audio_path": str(path.relative_to(ART)), "source_rate": rate,
                "duration_s": round(len(mono) / SR, 3),
                "audio_sha256": hashlib.sha256(mono.tobytes()).hexdigest(),
                "lexical_reference": r["transcription"],
                "raw_transcription": r["raw_transcription"],
                "reference_kind": "fleurs_normalized_transcription",
                "speaker_gender": r.get("gender"),
                "provenance": {"repo": fl_cfg["repo"], "revision": fl_cfg["revision"],
                               "config": "en_us", "split": "test", "row": idx,
                               "sentence_id": sid, "license": fl_cfg["license"]}})
        except Exception as exc:
            problems.append({"case_id": cid, "stage": "decode", "error": f"{type(exc).__name__}: {exc}"})

    write_jsonl(CASES, cases)
    write_json(ART / "real" / "prepare_report.json", {
        "created": utc_now(), "cases": len(cases), "problems": problems,
        "selection": {"disfluencyspeech": "all test rows in parquet order (first 250)",
                      "fleurs": "one utterance per sentence id (min sha256 of path), ids ordered by "
                                "sha256(id), first 250 of %d unique" % len(by_sentence)},
        "fleurs_test_rows": len(rows), "fleurs_unique_sentences": len(by_sentence)})
    return {"cases": len(cases), "problems": len(problems)}


# ---------------------------------------------------------------- asr (LocalFlow .venv)

def asr() -> dict:
    """Run once in LocalFlow's production .venv."""
    import numpy as np
    import soundfile as sf
    from localflow.stt import Transcriber
    from localflow.v2.normalize import normalize, NormalizationPolicy, ContextSnapshot
    from localflow.v2.cleanup import protected_spans_for_cleanup
    from localflow.v2.cleanup.engine import _has_correction_marker
    done = {r["case_id"]: r for r in read_jsonl(ASR_OUT)}
    cases = read_jsonl(CASES)
    asr_cfg = CONFIG["models"]["asr"]
    from huggingface_hub import snapshot_download
    path = snapshot_download(asr_cfg["repository_id"], revision=asr_cfg["revision"], local_files_only=True)
    t = Transcriber(path)
    t.load()
    policy = NormalizationPolicy()
    out = list(done.values())
    for c in cases:
        if c["case_id"] in done:
            continue
        row = {"case_id": c["case_id"]}
        try:
            samples, rate = sf.read(str(ART / c["audio_path"]), dtype="float32", always_2d=True)
            assert rate == SR and samples.shape[1] == 1, "audio format mismatch"
            t0 = time.perf_counter()
            raw = t.transcribe(samples[:, 0])
            row["asr_ms"] = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            norm = normalize(raw, policy, ContextSnapshot())
            row["normalize_ms"] = (time.perf_counter() - t0) * 1000
            spans = protected_spans_for_cleanup(raw, norm.text, norm.protected, norm.edits)
            row.update(raw_asr=raw, normalized=norm.text, protected_spans=[list(s) for s in spans],
                       normalization_changed=norm.text != raw,
                       normalization_edits=[[e.input_span.start, e.input_span.end, e.output_text]
                                            for e in norm.edits],
                       policy_revision=policy.policy_revision,
                       corrections_trigger=_has_correction_marker(norm.text),
                       status="ok" if raw.strip() else "empty_asr")
        except Exception as exc:
            row.update(status="error", error=f"{type(exc).__name__}: {exc}"[:300])
        out.append(row)
        if len(out) % 50 == 0:
            write_jsonl(ASR_OUT, out)
    write_jsonl(ASR_OUT, out)
    import mlx.core as mx
    write_json(ART / "real" / "asr_report.json", {
        "created": utc_now(), "asr": asr_cfg, "python": sys.version.split()[0],
        "runtime": {"mlx": mx.__version__}, "rows": len(out),
        "status_counts": {s: sum(1 for r in out if r.get("status") == s) for s in {r.get("status") for r in out}}})
    return {"rows": len(out)}


if __name__ == "__main__" and sys.argv[1] in ("prepare", "asr"):
    {"prepare": prepare, "asr": asr}[sys.argv[1]]()


def style_decode(n_rows: int = 60) -> None:
    """LocalAI venv: DisfluencySpeech *validation* clips -> 16 kHz WAVs."""
    import glob as _g
    import pyarrow.parquet as pq
    import soundfile as sf
    f = _g.glob(str(ART / "data/amaai-lab__DisfluencySpeech/data/validation-*.parquet"))[0]
    out = AUDIO_DIR / "style"
    out.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(pq.read_table(f).slice(0, n_rows).to_pylist()):
        mono, _ = _decode(r["audio"]["bytes"])
        sf.write(out / f"val-{i:03d}.wav", mono, SR, subtype="FLOAT")


def style_exemplars(keep: int = 12) -> dict:
    """LocalFlow venv: Parakeet transcripts of the validation clips, used only
    to show the data generator what real ASR formatting looks like."""
    import soundfile as sf
    from localflow.stt import Transcriber
    from huggingface_hub import snapshot_download
    out_path = ART / "real" / "style_exemplars.json"
    if out_path.exists():
        return {"skipped": True}
    asr_cfg = CONFIG["models"]["asr"]
    t = Transcriber(snapshot_download(asr_cfg["repository_id"], revision=asr_cfg["revision"],
                                      local_files_only=True))
    t.load()
    texts = []
    for wav in sorted((AUDIO_DIR / "style").glob("*.wav")):
        samples, _ = sf.read(str(wav), dtype="float32")
        text = t.transcribe(samples).strip()
        if 8 <= len(text.split()) <= 45:
            texts.append(text)
    disfluent = [x for x in texts if re.search(r"\b(uh|um)\b", x, re.I)]
    plain = [x for x in texts if x not in disfluent]
    chosen = (disfluent[: keep // 2] + plain)[:keep]
    write_json(out_path, {"source": "amaai-lab/DisfluencySpeech validation split (never test)",
                          "exemplars": chosen})
    return {"exemplars": len(chosen)}


if __name__ == "__main__" and sys.argv[1] in ("style_decode", "style"):
    {"style_decode": style_decode, "style": style_exemplars}[sys.argv[1]]()
