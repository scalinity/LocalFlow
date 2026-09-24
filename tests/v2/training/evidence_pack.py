"""The 100-record synthetic training-evidence fixture pack plus 40
attribution negatives (V2 M14, E19.1).

Category allocation (E19.1's minimums, defining the pack — never
population prevalence):

- 20 fully reviewed successes (retained audio + audio-reviewed
  verbatim + intended-correct mark)
- 20 recognition/representation corrections (edit observations with
  single clean spans; half carry cleanup-regression provenance)
- 20 mixed-edit / changed-intent cases
- 10 cleanup/transform regressions
- 10 uncertain/unobserved outcomes
- 10 sensitive / excluded / deleted cases
- 10 crop / retry / duplicate-family cases

All content is synthetic (docs.example.com hosts, Synth App names,
made-up utterances shaped like personal dictation). Family ids group
retries/duplicates deliberately so split and dedup tests have real
families to catch. ``build_pack(store)`` creates everything through
the REAL store/collector-adjacent APIs and returns a manifest with
per-category example ids and the ground truth the classification and
promotion assertions measure against.

The 40 negatives (``NEGATIVES``) are wrong-target attribution,
unrelated pasted text, no-edit acceptance inference and
different-input preference pairings — cases that must NEVER mint a
learning candidate or be promoted into verified ASR training
(M14-AC05); ``build_negatives(store)`` materializes their store-side
shapes for the refusal assertions.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import ids, training_data  # noqa: E402
from localflow.v2.store import (  # noqa: E402
    grant_lease_row, insert_text_artifact_row)

NOW = "2026-09-20T10:00:00.000Z"


def _env(ex_id, job_id, family_id, raw_aid, applied_aid, **extra):
    env = {
        "training_schema_version": 1, "example_id": ex_id,
        "revision_id": None, "job_id": job_id, "family_id": family_id,
        "origin": "live_capture", "task_kind": "dictation",
        "captured_at_utc": NOW, "time_quality": "known",
        "attempt": 1, "artifact_ids": {
            "source_text": raw_aid, "applied_output": applied_aid},
        "capture": {"duration_sec": 9.0, "sample_rate": 16000},
        "recognition": {"language": "en", "model_id": "synth-asr"},
        "outcome": {"insertion": "confirmed", "correctness":
                    "unreviewed"},
        "annotations": [], "missing_reasons": {},
        "state": "captured_unreviewed", "deletion_epoch": 0,
    }
    env.update(extra)
    return env


def _add_example(store, *, text_raw, text_applied, family, job_seq,
                 state="captured_unreviewed", audio=False, **extra):
    """One example with retained raw/applied artifacts (synthetic
    audio optional per caller, named in the envelope when present)."""
    import numpy as np
    from localflow.v2 import store as store_mod
    job_id = f"job-synth-{job_seq:03d}"
    ex_id = f"ex-synth-{job_seq:03d}"
    now = NOW
    audio_aid = None
    if audio:
        rate = 16000
        samples = np.zeros(int(2.0 * rate), dtype="<f4")
        path = store.artifacts_dir / f"art-aud-{job_seq:03d}.wav"
        store_mod.write_wav_f32(path, samples, rate)

        def audio_op(conn):
            nonlocal audio_aid
            audio_aid = f"art-aud-{job_seq:03d}"
            conn.execute(
                "INSERT INTO artifacts(artifact_id, job_id, stage,"
                " parent_artifact_id, kind, role, content_path,"
                " content_text, sha256, bytes, meta_json,"
                " retention_class, purged, created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,0,?)",
                (audio_aid, job_id, "capture", None, "audio_wav_f32",
                 "original_audio", f"art-aud-{job_seq:03d}.wav",
                 ids.sha256_bytes(path.read_bytes()),
                 path.stat().st_size,
                 json.dumps({"format": "wav_ieee_float32",
                             "dtype": "float32", "sample_rate": rate,
                             "channels": 1,
                             "sample_count": int(samples.size),
                             "duration_sec": 2.0, "lossless": True,
                             "synthetic": True}),
                 "training", now))
            grant_lease_row(conn, audio_aid, "training", days=None,
                            granted_at_epoch=0.0)
        store.submit(audio_op)

    def op(conn):
        insert_text_artifact_row(
            conn, artifact_id=f"art-raw-{job_seq:03d}", job_id=job_id,
            stage="asr", role="raw_transcript", text=text_raw,
            retention_class="training", created_at_utc=now)
        insert_text_artifact_row(
            conn, artifact_id=f"art-app-{job_seq:03d}", job_id=job_id,
            stage="cleanup", role="applied_output", text=text_applied,
            retention_class="training",
            parent_artifact_id=f"art-raw-{job_seq:03d}",
            created_at_utc=now)
        conn.execute(
            "INSERT OR IGNORE INTO training_examples(example_id,"
            " job_id, family_id, consent_revision_id,"
            " collection_policy, state, created_at_utc, updated_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (ex_id, job_id, family, "consent-synth", "m14_fixture",
             state, now, now))
    store.submit(op)
    env = _env(ex_id, job_id, family, f"art-raw-{job_seq:03d}",
               f"art-app-{job_seq:03d}", **extra)
    if audio_aid:
        env["artifact_ids"]["original_audio"] = audio_aid
    store.append_revision(ex_id, env)
    return ex_id, job_id, env


def _annotate(store, ex_id, *, verbatim=None, intended=None):
    svc = training_data.TrainingDataService(store)
    if verbatim is not None:
        svc.set_verbatim(ex_id, verbatim, listened_audio=True)
    if intended is not None:
        svc.mark_intended(ex_id, intended)


def _edit_observation(store, job_seq, before, after):
    """A certified S29.8 window row with before/after artifacts."""
    now = NOW

    def op(conn):
        for suffix, text in (("b", before), ("a", after)):
            insert_text_artifact_row(
                conn, artifact_id=f"art-obs{suffix}-{job_seq:03d}",
                job_id=f"job-synth-{job_seq:03d}", stage="insertion",
                role=f"observed_{suffix}", text=text,
                retention_class="training", created_at_utc=now)
        conn.execute(
            "INSERT INTO insertion_observations(observation_id,"
            " insertion_id, job_id, started_at_utc, stopped_at_utc,"
            " stop_reason, edited, reanchors, ticks,"
            " before_artifact_id, after_artifact_id, meta_json)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"obs-synth-{job_seq:03d}", f"ins-synth-{job_seq:03d}",
             f"job-synth-{job_seq:03d}", now, now,
             "owned_range_edited", 1, 0, 5,
             f"art-obsb-{job_seq:03d}", f"art-obsa-{job_seq:03d}",
             "{}"))
    store.submit(op)


def build_pack(store) -> dict:
    """Create the 100-record pack; returns ids + ground truth."""
    truth = {}
    ids_by_cat = {k: [] for k in (
        "reviewed_success", "recognition_correction",
        "mixed_changed_intent", "regression", "uncertain",
        "sensitive_excluded", "duplicate_family")}
    seq = 0

    def synth_text(i, kind):
        if kind == "success":
            return (f"deploy the service to staging env {i}",
                    f"Deploy the service to staging env {i}.")
        if kind == "recognition":
            return (f"ship the clod code branch {i}",
                    f"Ship the clod code branch {i}")
        if kind == "representation":
            # Word labels, never digit indices — a "batch 12" label
            # would collide with the corrected "12%" token and trip
            # the classifier's honest both-forms abstention.
            return (f"about twelve percent of series {chr(97 + i % 20)}",
                    f"About twelve percent of series {chr(97 + i % 20)}")
        if kind == "mixed":
            return (f"send the cloud report on friday {i}",
                    f"Send the cloud report on friday {i}")
        if kind == "regression":
            return (f"fix the pipeline config {i}",
                    f"Fix the pipeline config {i}")
        if kind == "uncertain":
            return (f"maybe try the other approach {i}",
                    f"Maybe try the other approach {i}.")
        if kind == "sensitive":
            return (f"key sk-{'a' * 30}{i}", f"key sk-{'a' * 30}{i}")
        return (f"retry the flaky build {i}",
                f"Retry the flaky build {i}")

    # 20 reviewed successes: audio + verbatim + intended-correct.
    for i in range(20):
        seq += 1
        raw, applied = synth_text(i, "success")
        ex, job, env = _add_example(store, text_raw=raw,
                                    text_applied=applied,
                                    family=f"fam-synth-{seq:03d}",
                                    job_seq=seq, audio=True)
        _annotate(store, ex, verbatim=raw, intended=True)
        truth[ex] = {"category": "reviewed_success",
                     "expect_asr": True,
                     "audio": env["artifact_ids"]["original_audio"]}
        ids_by_cat["reviewed_success"].append(ex)
    # 20 recognition/representation corrections (10 each) with edit
    # observations; half are cleanup regressions (raw correct).
    for i in range(20):
        seq += 1
        kind = "recognition" if i < 10 else "representation"
        raw, applied = synth_text(i, kind)
        if i % 2 == 1:  # regression variant: raw carries the right form
            raw = raw.replace("clod", "Claude") \
                if kind == "recognition" else raw
            applied = applied.replace("Claude", "Clod") \
                if kind == "recognition" else applied
        ex, job, env = _add_example(store, text_raw=raw,
                                    text_applied=applied,
                                    family=f"fam-synth-{seq:03d}",
                                    job_seq=seq, audio=True)
        corrected = applied.replace("clod", "Claude") \
            if kind == "recognition" else \
            applied.replace("twelve percent", "12%")
        _edit_observation(store, seq, applied, corrected)
        _annotate(store, ex, verbatim=raw)
        truth[ex] = {
            "category": "recognition_correction",
            "subkind": kind, "regression": i % 2 == 1,
            "expect_asr": True,
            "audio": env["artifact_ids"]["original_audio"],
            "expect_edit_kind": ("recognition_error"
                                 if kind == "recognition"
                                 else "representation_error")}
        ids_by_cat["recognition_correction"].append(ex)
    # 20 mixed edits / changed-intent cases (never verified ASR).
    for i in range(20):
        seq += 1
        raw, applied = synth_text(i, "mixed")
        ex, job, env = _add_example(store, text_raw=raw,
                                    text_applied=applied,
                                    family=f"fam-synth-{seq:03d}",
                                    job_seq=seq, audio=True)
        corrected = applied.replace("cloud", "Claude") \
            .replace("friday", "Monday")
        _edit_observation(store, seq, applied, corrected)
        _annotate(store, ex, verbatim=raw)
        truth[ex] = {"category": "mixed_changed_intent",
                     "expect_asr": False,
                     "audio": env["artifact_ids"]["original_audio"],
                     "expect_edit_kind": "changed_intent"}
        ids_by_cat["mixed_changed_intent"].append(ex)
    # 10 cleanup/transform regressions (no verbatim — not ASR
    # candidates; label review classifies the regression).
    for i in range(10):
        seq += 1
        raw, applied = synth_text(i, "regression")
        raw = raw.replace("pipeline", "Pipeline").replace(
            "config", "Config")  # raw had it right
        ex, job, env = _add_example(
            store, text_raw=raw, text_applied=applied,
            family=f"fam-synth-{seq:03d}", job_seq=seq,
            cleanup={"applied_path": "basic",
                     "fallback_reason": "model_refusal"})
        truth[ex] = {"category": "regression", "expect_asr": False}
        ids_by_cat["regression"].append(ex)
    # 10 uncertain/unobserved outcomes.
    for i in range(10):
        seq += 1
        raw, applied = synth_text(i, "uncertain")
        ex, job, env = _add_example(
            store, text_raw=raw, text_applied=applied,
            family=f"fam-synth-{seq:03d}", job_seq=seq,
            outcome={"insertion": "posted_unverified",
                     "correctness": "unreviewed"})
        truth[ex] = {"category": "uncertain", "expect_asr": False}
        ids_by_cat["uncertain"].append(ex)
    # 10 sensitive / excluded / deleted.
    for i in range(10):
        seq += 1
        raw, applied = synth_text(i, "sensitive")
        ex, job, env = _add_example(
            store, text_raw=raw, text_applied=applied,
            family=f"fam-synth-{seq:03d}", job_seq=seq,
            state="quarantined_sensitive" if i < 3 else
            ("excluded" if i < 7 else "captured_unreviewed"))
        truth[ex] = {"category": "sensitive_excluded",
                     "expect_asr": False}
        ids_by_cat["sensitive_excluded"].append(ex)
    # 10 crop/retry/duplicate-family (5 families with 2 members).
    for i in range(10):
        seq += 1
        raw, applied = synth_text(i, "duplicate")
        fam = f"fam-dup-{i % 5:03d}"
        ex, job, env = _add_example(
            store, text_raw=raw, text_applied=applied, family=fam,
            job_seq=seq, attempt=2 if i % 2 else 1)
        truth[ex] = {"category": "duplicate_family",
                     "expect_asr": False, "family": fam}
        ids_by_cat["duplicate_family"].append(ex)
    return {"examples": truth, "by_category": ids_by_cat}


# The 40 attribution negatives (E19.1): store-shaped cases that must
# never mint a candidate or promote. Each entry: (name, kind, payload).
NEGATIVES = [
    # 10 wrong-target attribution: the edit belongs to another job's
    # field/region (before/after never intersect the job's own text).
    *(("wrong_target", "foreign_edit", {
        "job_text": "alpha beta gamma", "before": "alpha beta gamma",
        "after": "alpha beta delta",
        "foreign": "delta"}) for _ in range(10)),
    # 10 unrelated pasted text: the after-text is a wholesale paste,
    # not an edit of the inserted region.
    *(("unrelated_paste", "wholesale_replace", {
        "job_text": "quarterly numbers follow",
        "before": "quarterly numbers follow",
        "after": "paste from elsewhere entirely about other topics"})
      for _ in range(10)),
    # 10 no-edit acceptance inference: unchanged output must never
    # become a correctness label or candidate.
    *(("no_edit_inference", "unchanged", {
        "job_text": "identical text", "before": "identical text",
        "after": "identical text"}) for _ in range(10)),
    # 10 different-input preference pairings (refused at write time by
    # the M11 store; the assertion re-proves it through the pair API).
    *(("different_input_pair", "cross_task", {
        "task_a": "task-aaa", "task_b": "task-bbb"})
      for _ in range(10)),
]


def build_negatives(store) -> list[dict]:
    """Materialize the negatives' store shapes: for the edit-shaped
    ones, insertion observations whose before text is NOT the job's
    final text (the wrong-target/unrelated-paste shapes). Returns the
    per-negative context for assertions."""
    out = []
    seq = 900
    for name, kind, payload in NEGATIVES:
        seq += 1
        if kind == "cross_task":
            out.append({"name": name, "kind": kind, **payload})
            continue
        raw, applied = payload["job_text"], payload["job_text"]
        ex, job, env = _add_example(
            store, text_raw=raw, text_applied=applied,
            family=f"fam-neg-{seq:03d}", job_seq=seq)
        _edit_observation(store, seq, payload["before"],
                          payload["after"])
        out.append({"name": name, "kind": kind, "example_id": ex,
                    "job_id": job, **payload})
    return out
