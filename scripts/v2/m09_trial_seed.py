"""Seed a SANDBOX home with synthetic data for the M09 manual checks
(docs/v2/VERIFICATION.html → M09-V001..V007).

Writes, under ``<home>/Library/Application Support/LocalFlow`` and
``<home>/Library/Logs/LocalFlow``: dated History jobs across apps and
modes (one with a transform proposal that was NOT applied), jobs whose
original audio is synthetic speech from macOS ``say`` (for Replay),
legacy analytics rows and Undated legacy log pairs, Training examples
in the states the review surface must handle, and a diagnostics log
over two writer streams carrying deliberately private-looking fields
that the redacted export must omit. Every string is synthetic.

It refuses to run against the real home folder or a store that already
holds jobs — it only ever fills a fresh sandbox.

    .venv/bin/python scripts/v2/m09_trial_seed.py --home "$SANDBOX09"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import pwd
import os
import subprocess
import sys
import tempfile
import uuid
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

APPS = (("TextEdit", "com.apple.TextEdit"), ("Safari", "com.apple.Safari"),
        ("Mail", "com.apple.mail"), ("Notes", "com.apple.Notes"))
MODES = ("llm", "basic", "raw", "llm_partial")
SENTENCES = (
    "the quarterly planning notes are ready for review",
    "please move the design sync to thursday afternoon",
    "remember to water the plants before the weekend",
    "the draft needs one more pass on the introduction",
    "call the library about the overdue book",
    "add oat milk and lemons to the shopping list",
    "the build finished and every check passed",
    "send the slides to the group after lunch",
    "book a table for four on friday evening",
    "the train leaves at seven fifteen tomorrow",
    "rename the folder to archive before sharing",
    "check the tyre pressure before the long drive")


def iso(t: dt.datetime) -> str:
    t = t.astimezone(dt.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def speech(text: str) -> np.ndarray:
    """Synthetic speech: macOS ``say`` → 16 kHz mono float32."""
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "s.wav"
        subprocess.run(["say", "-o", str(path), "--file-format=WAVE",
                        "--data-format=LEI16@16000", text], check=True)
        with wave.open(str(path)) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), "<i2")
    return (pcm.astype(np.float32) / 32768.0).copy()


def job(store, text, when, *, app=None, mode="llm", audio=False,
        cleaned=None, retention="history"):
    job_id, fam = store.create_job(captured_at_utc=iso(when),
                                   time_quality="known",
                                   state="insertion_confirmed")
    raw = store.write_text_artifact(job_id=job_id, stage="asr",
                                    role="raw_transcript", text=text,
                                    retention_class=retention)
    applied = store.write_text_artifact(
        job_id=job_id, stage="cleanup", role="applied_output",
        text=cleaned or (text[0].upper() + text[1:] + "."),
        retention_class=retention, parent_artifact_id=raw,
        meta={"cleanup_path": mode})
    audio_id = store.write_audio_artifact(
        job_id=job_id, stage="capture", samples=speech(text),
        sample_rate=16000) if audio else None
    if app:
        store.set_job_target(job_id, *app)
    return job_id, fam, raw, applied, audio_id


def example(store, text, when, *, state=None, transform=None):
    """A Training example over a job with speech audio; ``transform``
    = (proposal text, path, reason) records a proposal NOT applied."""
    job_id, fam, raw, applied, audio_id = job(
        store, text, when, audio=True, retention="training")
    ex = store.upsert_example(job_id=job_id, family_id=fam)
    env = {"training_schema_version": 1, "example_id": ex,
           "job_id": job_id, "family_id": fam, "attempt": 1,
           "origin": "live_capture", "task_kind": "dictation",
           "captured_at_utc": iso(when), "time_quality": "known",
           "artifact_ids": {"source_text": raw, "applied_output": applied,
                            "original_audio": audio_id},
           "missing_reasons": {}, "annotations": [],
           "outcome": {"insertion": "confirmed",
                       "correctness": "unreviewed"},
           "state": "captured_unreviewed"}
    if transform is not None:
        proposal, path, reason = transform
        out = store.write_text_artifact(
            job_id=job_id, stage="transform", role="transform_output",
            text=proposal, retention_class="training",
            parent_artifact_id=applied, meta={"path": path})
        env["transform"] = {"artifact_ids": {"output": out}, "path": path,
                            "reason": reason, "applied": False}
    store.append_revision(ex, env)
    if state is not None:
        store.set_example_state(ex, state)
    return ex, job_id


def events(log_dir: pathlib.Path, now: dt.datetime, job_ids):
    """Two writer streams interleaved by time, one job's timeline, three
    levels, and fields the typed export must drop."""
    records = []
    for stream, (boot, pid) in enumerate((("a", 4101), ("b", 4202))):
        for seq in range(1, 16):
            t = now - dt.timedelta(minutes=90 - seq * 5 - stream * 2)
            jid = job_ids[seq % len(job_ids)]
            level = "ERROR" if seq % 7 == 0 else (
                "WARNING" if seq % 5 == 0 else "INFO")
            rec = {"schema_version": 2,
                   "event_id": "evt-" + uuid.uuid4().hex,
                   "timestamp_utc": iso(t), "boot_id": "boot-" + boot * 32,
                   "session_id": "session-" + boot * 32, "process_id": pid,
                   "worker_generation": 1, "sequence": seq,
                   "job_id": jid, "attempt": 1,
                   "stage": ("asr", "cleaning", "insertion")[seq % 3],
                   "event": "stage.completed", "level": level,
                   "outcome": "ok" if level == "INFO" else "degraded",
                   "reason_code": None if level == "INFO" else
                   "SyntheticTrialCondition", "duration_ms": 12.5 * seq,
                   "model_id": "mlx-community/synthetic-model"}
            if seq == 3:
                # Must never reach a redacted export.
                rec["private_text"] = "synthetic private sentence"
                rec["detail"] = {"note": "synthetic nested detail"}
                rec["model_id"] = "/Users/example/models/private-model"
            records.append(rec)
    log_dir.mkdir(parents=True, exist_ok=True)
    day = now.astimezone(dt.timezone.utc).strftime("%Y-%m-%d")
    path = log_dir / f"events-{day}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        f.write("not json — a malformed line the view skips and counts\n")
        f.write("[\"a non-object line\"]\n")
    return path, len(records)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True,
                    help="the sandbox home folder the dev app runs with")
    args = ap.parse_args(argv)
    home = pathlib.Path(args.home).expanduser().resolve()
    real = pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    if home == real:
        raise SystemExit(f"refusing: {home} is the real home folder; use"
                         " a sandbox folder")
    support = home / "Library" / "Application Support" / "LocalFlow"
    support.mkdir(parents=True, exist_ok=True)
    db = support / "v2.db"
    os.environ["HOME"] = str(home)  # everything below resolves inside it
    from localflow.v2 import store as store_mod
    store = store_mod.Store(db, artifacts_dir=support / "v2-artifacts",
                            backup_dir=support / "v2-evidence" / "backups")
    try:
        if store.submit(lambda c: c.execute(
                "SELECT count(*) FROM jobs").fetchone()[0]):
            raise SystemExit(f"refusing: {db} already holds jobs; seed a"
                             " fresh sandbox only")
        now = dt.datetime.now(dt.timezone.utc)
        ids = []
        for i, text in enumerate(SENTENCES):
            when = now - dt.timedelta(days=i % 9, hours=i)
            ids.append(job(store, text, when, app=APPS[i % len(APPS)],
                           mode=MODES[i % len(MODES)], audio=i < 3)[0])
        for i in range(4):
            store.insert_legacy_dictation({
                "id": 9000 + i,
                "ts": (now - dt.timedelta(days=12 + i)).timestamp(),
                "duration_sec": 2.0,
                "raw_text": f"imported older dictation number {i + 1}",
                "cleaned_text": f"Imported older dictation number {i + 1}.",
                "raw_words": 4, "cleaned_words": 4, "fixed_words": 0,
                "wpm": 0.0, "app_name": APPS[i % len(APPS)][0],
                "app_bundle": None, "kind": "dictation"},
                "sha-m09-trial")
        for i in range(2):
            store.import_legacy_pair(
                raw_text=f"undated log line {i + 1} raw",
                cleaned_text=f"Undated log line {i + 1}, cleaned.",
                raw_meta={}, cleaned_meta={}, source_kind="legacy_log",
                source_sha="sha-m09-trial-log",
                locator=f"log:m09-trial:{i}")
        seeded = {
            "A_replay_then_select_B": example(
                store, "alpha example for listening first",
                now - dt.timedelta(hours=2)),
            "B_verbatim_target": example(
                store, "bravo example for the verbatim reference",
                now - dt.timedelta(hours=3)),
            "C_span_correction": example(
                store, "charlie example with one wrong word",
                now - dt.timedelta(hours=4),
                transform=("Charlie example, rewritten as a formal note.",
                           "needs_review", "requirement_coverage_uncertain")),
            "D_quarantined": example(
                store, "delta example flagged as sensitive",
                now - dt.timedelta(hours=5), state="quarantined_sensitive"),
            "E_excluded": example(
                store, "echo example excluded by the user",
                now - dt.timedelta(hours=6), state="excluded"),
        }
        store.sync()
        log, n = events(home / "Library" / "Logs" / "LocalFlow", now,
                        ids[:4])
    finally:
        store.close()
    print(json.dumps({"store": str(db), "history_jobs": len(ids),
                      "jobs_with_speech_audio": 3, "legacy_rows": 4,
                      "legacy_log_pairs": 2,
                      "training_examples": {k: v[0] for k, v in
                                            seeded.items()},
                      "events_file": str(log), "events": n}, indent=1))


if __name__ == "__main__":
    main()
