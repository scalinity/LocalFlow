#!/usr/bin/env python3
"""M14 benchmark: curation, profile and export cost at personal scale,
kept apart from dictation latency — work validity first, then timing.

Builds a synthetic store in a temp dir with producer-shaped rows (the
collector's artifact roles, M08 observation roles, M12 notes through
the real NoteStore): 10,000 live examples, 10,000 usage facts, 1,000
genuinely changed edit observations plus unchanged controls, 200 notes
with a typed correction inside a dictated span, and 400 retained
10-second float32 WAVs (~256 MB) with audio-reviewed verbatim
references. Every count the run depends on is known BY CONSTRUCTION
here — never read back from the component under test.

1. Validity (M14-AUDIT-28): each component runs and its effect is
   recounted independently — candidates minted per changed observation
   and none for unchanged ones, note candidates, the profile's eligible
   examples and words, the sampling ledger against an independent seeded
   draw, the family→partition map against an independent hash, exported
   rows, the audio bytes actually on disk, and the offline validator. A
   non-crashing no-op component (``--noop``) makes the run INVALID
   before any timing is reported.
2. Timing, only when valid: wall time per component (repeated where the
   component is repeatable; p50/p95/p99 over the samples), throughput,
   Python peak memory (separate traced runs), and two writer measures
   kept distinct: the time a concurrent dictation-shaped write WAITS
   (continuous probes overlapping every component) and the time each of
   the component's own ops HOLDS the single writer.

Committed output carries timings/sizes/counts only (synthetic content in
a temp dir, never committed). Run alone — no test sweep or other
benchmark at the same time:
    .venv/bin/python scripts/v2/benchmark_m14.py [--out DIR]
        [--scale small|full] [--noop COMPONENT] [--validate-only]
"""

import argparse
import hashlib
import json
import os
import pathlib
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from localflow.v2 import ids, learning, profile, store as store_mod  # noqa: E402
from localflow.v2.curation import (  # noqa: E402
    export as export_mod, review, sampling, splits)
from localflow.v2.store import (  # noqa: E402
    grant_lease_row, insert_text_artifact_row)

RATE = 16_000
COMPONENTS = ("mining", "note_mining", "profile", "sampling", "splits",
              "export")
WORDS = ("ship", "the", "report", "review", "notes", "weekly", "summary",
         "deploy", "branch", "draft", "team", "plan", "check", "update",
         "docs", "build", "later", "today", "message", "client")
SAMPLE_SEED = sampling.DEFAULT_SEED
SPLIT_SEED = splits.DEFAULT_SEED

EXIT_OK, EXIT_INVALID = 0, 3


class Invalid(Exception):
    """The run did not do the work it claims — no timing is reported."""


def sizes(scale):
    if scale == "small":
        return {"examples": 300, "audio": 20, "audio_seconds": 1.0,
                "observations": 60, "unchanged_observations": 6,
                "notes": 12}
    return {"examples": 10_000, "audio": 400, "audio_seconds": 10.0,
            "observations": 1_000, "unchanged_observations": 100,
            "notes": 200}


def utterance(i):
    """A distinct synthetic utterance (verbatim repeats are excluded
    from the profile, so every example is distinct by construction)."""
    n = 12 + (i * 7) % 30
    return " ".join(WORDS[(i * 3 + k * 5) % len(WORDS)]
                    for k in range(n)) + f" item {i}"


def pct(samples, q):
    ordered = sorted(samples)
    if not ordered:
        return None
    k = max(0, min(len(ordered) - 1,
                   int(round(q / 100.0 * len(ordered))) - 1))
    return round(ordered[k], 2)


def stats(samples):
    return {"n": len(samples), "p50_ms": pct(samples, 50),
            "p95_ms": pct(samples, 95), "p99_ms": pct(samples, 99),
            "max_ms": round(max(samples), 2) if samples else None}


# ---- the synthetic world (every expectation recorded here) ----------------


def build(s, tmp, sz):
    """Producer-shaped rows; returns the independent expectations."""
    now = "2026-09-20T10:00:00.000Z"
    s.append_consent("enabled", note="m14-benchmark")
    consent = s.current_consent_id()
    n, n_audio = sz["examples"], sz["audio"]
    n_obs, n_same, n_notes = (sz["observations"],
                              sz["unchanged_observations"], sz["notes"])
    samples = (np.sin(np.arange(int(sz["audio_seconds"] * RATE)) / 40.0)
               * 0.01).astype("<f4")
    audio = {}
    for i in range(n_audio):
        name = f"art-baud-{i:05d}.wav"
        path = s.artifacts_dir / name
        store_mod.write_wav_f32(path, samples, RATE)
        with open(path, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        audio[i] = (f"art-baud-{i:05d}", name, digest, path.stat().st_size)
    obs_lo, obs_hi = n_audio, n_audio + n_obs + n_same
    note_lo, note_hi = obs_hi, obs_hi + n_notes
    texts = {}
    for i in range(n):
        text = utterance(i)
        if obs_lo <= i < note_hi:
            text += " modul"  # the wrong form a later edit corrects
        texts[i] = text

    def op(conn):
        for i in range(n):
            ex, job, fam = f"ex-b{i:05d}", f"job-b{i:05d}", f"fam-b{i:05d}"
            text = texts[i]
            conn.execute(
                "INSERT INTO jobs(job_id, kind, family_id, attempt,"
                " time_quality, state, created_at_utc, updated_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (job, "dictation", fam, 2 if i % 50 == 0 else 1, "known",
                 "confirmed", now, now))
            raw = insert_text_artifact_row(
                conn, artifact_id=f"art-braw-{i:05d}", job_id=job,
                stage="asr", role="raw_transcript", text=text,
                retention_class="training", created_at_utc=now)
            app = insert_text_artifact_row(
                conn, artifact_id=f"art-bapp-{i:05d}", job_id=job,
                stage="cleanup", role="applied_output",
                text=text.capitalize() + ".", parent_artifact_id=raw,
                retention_class="training", created_at_utc=now)
            env = {"example_id": ex, "job_id": job, "family_id": fam,
                   "origin": "live_capture", "time_quality": "known",
                   "consent_revision_id": consent,
                   "captured_at_utc":
                       f"2026-0{3 + i % 6}-1{i % 10}T1{i % 10}:00:00.000Z",
                   "attempt": 2 if i % 50 == 0 else 1,
                   "artifact_ids": {"source_text": raw,
                                    "applied_output": app},
                   "capture": {"duration_sec": 2.0 if i % 40 == 0
                               else 9.0},
                   "recognition": {"language": "es" if i % 97 == 0
                                   else "en"},
                   "cleanup": {"passes": []},
                   "outcome": {"correctness": "unreviewed"},
                   "annotations": [], "missing_reasons": {}}
            if i < n_audio:
                aid, name, digest, size = audio[i]
                conn.execute(
                    "INSERT INTO artifacts(artifact_id, job_id, stage,"
                    " parent_artifact_id, kind, role, content_path,"
                    " content_text, sha256, bytes, meta_json,"
                    " retention_class, purged, created_at_utc)"
                    " VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,0,?)",
                    (aid, job, "capture", None, "audio_wav_f32",
                     "original_audio", name, digest, size,
                     json.dumps({"synthetic": True,
                                 "duration_sec": sz["audio_seconds"]}),
                     "training", now))
                grant_lease_row(conn, aid, "training", days=None,
                                granted_at_epoch=0.0)
                vref = insert_text_artifact_row(
                    conn, artifact_id=f"art-bvref-{i:05d}", job_id=job,
                    stage="review", role="verbatim_reference", text=text,
                    retention_class="training", created_at_utc=now)
                env["artifact_ids"]["original_audio"] = aid
                env["annotations"].append({
                    "annotation_id": f"ann-b{i:05d}",
                    "kind": "verbatim_reference", "coverage": "full",
                    "listened_audio": True, "artifact_id": vref,
                    "text_sha256": ids.sha256_text(text)})
                env["outcome"] = {
                    "correctness": "correct",
                    "correctness_provenance":
                        "user_explicit_intended_writing"}
            rev = f"rev-b{i:05d}"
            env["revision_id"] = rev
            payload = json.dumps(env, sort_keys=True)
            conn.execute(
                "INSERT INTO training_examples(example_id, job_id,"
                " family_id, consent_revision_id, collection_policy,"
                " state, latest_revision_id, created_at_utc,"
                " updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (ex, job, fam, consent, "m14_benchmark",
                 "annotated" if i < n_audio else "captured_unreviewed",
                 rev, now, now))
            conn.execute(
                "INSERT INTO training_revisions(revision_id, example_id,"
                " parent_revision_id, created_at_utc, envelope_json,"
                " content_sha256) VALUES(?,?,?,?,?,?)",
                (rev, ex, None, now, payload, ids.sha256_text(payload)))
            conn.execute(
                "INSERT INTO usage_facts(fact_id, kind, job_id,"
                " activity_at_utc, utc_offset_minutes, day_local,"
                " reporting_timezone, algorithm_version, raw_words,"
                " final_words, app_name, mode, created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"fact-b{i:05d}", "dictation", job,
                 f"2026-0{3 + i % 6}-1{i % 10}T1{i % 10}:00:00.000000Z",
                 -420, f"2026-0{3 + i % 6}-1{i % 10}", "UTC", 1,
                 len(text.split()), len(text.split()),
                 f"Synth App {i % 4}", "clean", now))
            if obs_lo <= i < obs_hi:
                before = text.capitalize() + "."
                changed = i < obs_lo + n_obs
                after = before.replace("modul", "module") if changed \
                    else before
                for suffix, role, body in (
                        ("b", "observation_before_range", before),
                        ("a", "observation_after_range", after)):
                    insert_text_artifact_row(
                        conn, artifact_id=f"art-bobs{suffix}-{i:05d}",
                        job_id=job, stage="insertion", role=role,
                        text=body, retention_class="training",
                        meta={"range_units": "utf16_host"},
                        created_at_utc=now)
                conn.execute(
                    "INSERT INTO insertion_observations(observation_id,"
                    " insertion_id, job_id, started_at_utc,"
                    " stopped_at_utc, stop_reason, edited, reanchors,"
                    " ticks, before_artifact_id, after_artifact_id,"
                    " meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"obs-b{i:05d}", f"ins-b{i:05d}", job, now, now,
                     "owned_range_edited", 1, 0, 3,
                     f"art-bobsb-{i:05d}", f"art-bobsa-{i:05d}", "{}"))
    s.submit(op, timeout=900)
    # Notes through the real M12 NoteStore: a dictated arrival span per
    # job, then one typed correction inside it.
    from localflow.v2 import notes as notes_mod
    ns = notes_mod.NoteStore(s)
    for i in range(note_lo, note_hi):
        job, ex = f"job-b{i:05d}", f"ex-b{i:05d}"
        nid = ns.create_note(texts[i], origin=notes_mod.ORIGIN_DICTATED,
                             source_job_id=job)["note_id"]
        s.submit(lambda c, nid=nid, ex=ex, job=job: c.execute(
            "INSERT INTO note_evidence_links(note_id, example_id, job_id,"
            " first_seen_utc) VALUES(?,?,?,?)", (nid, ex, job, now)))
        ns.append_revision(nid, texts[i].replace("modul", "module"),
                           origin=notes_mod.ORIGIN_TYPED,
                           trigger=notes_mod.TRIGGER_AUTOSAVE)
    # ---- expectations (independent of the components) ----
    mined_examples = {f"ex-b{i:05d}" for i in range(obs_lo, obs_lo + n_obs)}
    note_examples = {f"ex-b{i:05d}" for i in range(note_lo, note_hi)}
    triggered = {f"ex-b{i:05d}" for i in range(n)
                 if i % 50 == 0 or i % 40 == 0} \
        | mined_examples | note_examples
    p = sampling.DEFAULT_PERCENT / 100.0
    representative = set()
    for i in range(n):
        ex = f"ex-b{i:05d}"
        if ex in triggered:
            continue
        digest = hashlib.sha256(f"{SAMPLE_SEED}:{ex}".encode()).digest()
        if int.from_bytes(digest[:8], "big") / float(2 ** 64) < p:
            representative.add(ex)
    partitions = {}
    for i in range(n):
        fam = f"fam-b{i:05d}"
        digest = hashlib.sha256(f"{SPLIT_SEED}:{fam}".encode()).digest()
        draw = int.from_bytes(digest[:8], "big") / float(2 ** 64)
        partitions[fam] = ("train" if draw < 0.8 else "validation"
                           if draw < 0.9 else "frozen_test")
    return {
        "examples": n, "audio": n_audio,
        "audio_bytes": sum(a[3] for a in audio.values()),
        "changed_observations": n_obs,
        "unchanged_observations": n_same,
        "note_edits": n_notes,
        "eligible_examples": n,
        "eligible_words": sum(len(t.split()) for t in texts.values()),
        "representative": representative,
        "sampling_population": n,
        "partitions": partitions,
        "export_asr_rows": n_audio, "export_cleanup_rows": n_audio,
    }


# ---- writer instrumentation --------------------------------------------------


class WriterMeter:
    """Records how long each op HOLDS the single writer (measured inside
    the writer thread), tagging probe ops apart from component ops."""

    def __init__(self, store):
        self.store = store
        self.holds = []  # (start_monotonic, ms, is_probe)
        self._lock = threading.Lock()
        self._real = store._submit

        def submit(fn, wait=False, timeout=15.0):
            probe = getattr(fn, "_probe", False)

            def timed():
                t = time.monotonic()
                try:
                    return fn()
                finally:
                    with self._lock:
                        self.holds.append(
                            (t, (time.monotonic() - t) * 1000.0, probe))
            return self._real(timed, wait=wait, timeout=timeout)
        store._submit = submit

    def component_holds(self, t0, t1):
        with self._lock:
            return [ms for t, ms, probe in self.holds
                    if not probe and t0 <= t <= t1]


def _probe_write(s):
    """One dictation-shaped store write (artifact row + lease), timed
    from submit to commit: the wait a dictation would see."""
    now = ids.now_utc_iso()
    aid = ids.new_id("art")

    def fn(conn):
        insert_text_artifact_row(
            conn, artifact_id=aid, job_id="job-probe", stage="asr",
            role="raw_transcript", text="probe dictation text",
            retention_class="history", created_at_utc=now)
        grant_lease_row(conn, aid, "history", days=30,
                        granted_at_epoch=time.time())
    t = time.monotonic()
    s._submit(_tag(lambda: fn(s._db)), wait=True, timeout=900)
    return (time.monotonic() - t) * 1000.0


def _tag(fn):
    fn._probe = True
    return fn


def run_with_probes(s, meter, fn, *, every_s=0.005):
    """Run ``fn`` on a thread while dictation-shaped probes are submitted
    continuously (one every ``every_s`` after the previous completes).
    Returns (result, wall_ms, probe waits, component writer holds)."""
    done = {}

    def run():
        t = time.monotonic()
        done["t0"] = t
        done["out"] = fn()
        done["t1"] = time.monotonic()
        done["ms"] = (done["t1"] - t) * 1000.0
    th = threading.Thread(target=run)
    th.start()
    waits = []
    while th.is_alive():
        time.sleep(every_s)
        waits.append(_probe_write(s))
    th.join()
    return (done["out"], done["ms"], waits,
            meter.component_holds(done["t0"], done["t1"]))


# ---- validity (independent recounts) ------------------------------------------


def _q(s, sql, args=()):
    return s._submit(lambda: s._db.execute(sql, args).fetchall(),
                     wait=True, timeout=900)


def check(cond, what, reasons):
    if not cond:
        reasons.append(what)


def components(s, tmp, noop=None):
    """The components, each replaceable by a non-crashing no-op."""
    emit = lambda *a, **k: None  # noqa: E731
    ls = learning.LearningService(s, emit=emit)
    ps = profile.ProfileService(s, emit=emit)
    sm = sampling.SamplingService(s, emit=emit)
    sp = splits.SplitService(s, emit=emit)
    ex = export_mod.DatasetExporter(s, emit=emit)

    def mine_observations_only():
        # mine_observation_candidates also runs the note pass; the
        # benchmark measures and validates the two apart, so a no-op in
        # either is visible on its own.
        ls._mine_note_candidates = lambda conn, limit: 0
        try:
            return ls.mine_observation_candidates(limit=10 ** 6)
        finally:
            del ls._mine_note_candidates
    comp = {
        "mining": mine_observations_only,
        "note_mining": lambda: s.submit(
            lambda conn: ls._mine_note_candidates(conn, 10 ** 6),
            timeout=900),
        "profile": ps.compute,
        "sampling": sm.refresh,
        "splits": sp.assign,
        "export": lambda: ex.build(tmp / "dataset", task_views=(
            "asr_supervised", "cleanup_supervised")),
    }
    fake = {"mining": lambda: 0, "note_mining": lambda: 0,
            "profile": lambda: {"measured": {"eligible_examples": 0,
                                             "eligible_words": 0}},
            "sampling": lambda: {"population": 0},
            "splits": lambda: {"assignment_version": 1},
            "export": lambda: {"state": "complete", "counts": {}}}
    if noop is not None:
        if noop not in comp:
            raise ValueError(f"unknown component {noop!r}")
        comp[noop] = fake[noop]
    return comp, {"ls": ls, "ps": ps, "sm": sm, "sp": sp, "ex": ex}


def validate(s, tmp, expect, comp, services):
    """Run every component once and recount its effect independently.
    A component that raises is recorded as a reason (INVALID), never a
    crash of the benchmark."""
    reasons = []
    work = {}
    raw = dict(comp)

    def guarded(name):
        def call():
            try:
                return raw[name]()
            except Exception as e:  # noqa: BLE001
                reasons.append(f"{name}: raised {type(e).__name__}")
                return None
        return call
    comp = {name: guarded(name) for name in raw}
    # The declared population, recounted from the store itself.
    rows = _q(s, "SELECT COUNT(*) FROM training_examples")[0][0]
    audio = _q(s, "SELECT COUNT(*) FROM artifacts WHERE"
                  " role='original_audio' AND purged=0")[0][0]
    work["store"] = {"example_rows": rows, "audio_artifacts": audio,
                     "expected_examples": expect["examples"],
                     "expected_audio": expect["audio"]}
    check(rows == expect["examples"] and audio == expect["audio"],
          "store: rows != declared population", reasons)
    comp["mining"]()
    rows = _q(s, "SELECT status, COUNT(*) FROM learning_candidates WHERE"
                 " source='edit_observation' GROUP BY status")
    got = dict(rows)
    work["mining"] = {"candidates": got.get("pending", 0),
                      "dismissed": got.get("dismissed", 0),
                      "expected_candidates": expect["changed_observations"],
                      "expected_dismissed":
                          expect["unchanged_observations"]}
    check(got.get("pending", 0) == expect["changed_observations"],
          "mining: pending candidates != changed observations", reasons)
    check(got.get("dismissed", 0) == expect["unchanged_observations"],
          "mining: dismissed != unchanged observations", reasons)
    comp["note_mining"]()
    notes_minted = _q(s, "SELECT COUNT(*) FROM learning_candidates WHERE"
                         " source='note_revision'")[0][0]
    work["note_mining"] = {"candidates": notes_minted,
                           "expected": expect["note_edits"]}
    check(notes_minted == expect["note_edits"],
          "note mining: candidates != typed corrections", reasons)
    snap = comp["profile"]()
    m = (snap or {}).get("measured") or {}
    stored = _q(s, "SELECT COUNT(*) FROM profile_snapshots")[0][0]
    work["profile"] = {"eligible_examples": m.get("eligible_examples"),
                       "eligible_words": m.get("eligible_words"),
                       "snapshots_written": stored,
                       "expected_examples": expect["eligible_examples"],
                       "expected_words": expect["eligible_words"]}
    check(m.get("eligible_examples") == expect["eligible_examples"] and
          m.get("eligible_words") == expect["eligible_words"],
          "profile: eligible cohort != independent count", reasons)
    check(stored == 1, "profile: no snapshot written", reasons)
    comp["sampling"]()
    decided = _q(s, "SELECT example_id, stratum FROM sampling_decisions")
    rep = {ex for ex, st in decided if st == "representative"}
    work["sampling"] = {"decisions": len(decided),
                        "representative": len(rep),
                        "expected_decisions": expect["sampling_population"],
                        "expected_representative":
                            len(expect["representative"])}
    check(len(decided) == expect["sampling_population"],
          "sampling: decisions != population", reasons)
    check(rep == expect["representative"],
          "sampling: representative set != independent seeded draw",
          reasons)
    comp["splits"]()
    members = _q(s, "SELECT family_id, partition FROM training_memberships"
                    " WHERE assignment_version=1")
    got_map = dict(members)
    work["splits"] = {"memberships": len(members),
                      "expected": len(expect["partitions"])}
    check(len(members) == len(expect["partitions"]) and
          got_map == expect["partitions"],
          "splits: family map != independent hash", reasons)
    comp["export"]()
    dest = tmp / "dataset"
    exported = []
    if (dest / "examples.jsonl").is_file():
        exported = [json.loads(line) for line in
                    (dest / "examples.jsonl").read_text().splitlines()
                    if line.strip()]
    audio_on_disk = sum(p.stat().st_size for p in
                        (dest / "artifacts").glob("*.wav")) \
        if (dest / "artifacts").is_dir() else 0
    kinds = {k: sum(1 for e in exported if e.get("task_kind") == k)
             for k in ("asr_supervised", "cleanup_supervised")}
    report = export_mod.validate_dataset(dest) if dest.is_dir() \
        else {"valid": False}
    work["export"] = {**kinds, "audio_bytes_on_disk": audio_on_disk,
                      "expected_asr": expect["export_asr_rows"],
                      "expected_cleanup": expect["export_cleanup_rows"],
                      "expected_audio_bytes": expect["audio_bytes"],
                      "validator_valid": report.get("valid")}
    check(kinds["asr_supervised"] == expect["export_asr_rows"] and
          kinds["cleanup_supervised"] == expect["export_cleanup_rows"],
          "export: rows != independently eligible examples", reasons)
    check(audio_on_disk == expect["audio_bytes"],
          "export: audio bytes on disk != retained audio", reasons)
    check(bool(report.get("valid")), "export: offline validation failed",
          reasons)
    return {"valid": not reasons, "reasons": reasons, "work": work}


def run_validity(scale="small", noop=None):
    """Build a world at ``scale``, run each component once and recount
    its work independently. A no-op component must make it invalid."""
    sz = sizes(scale)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = store_mod.Store(tmp / "v2.db", artifacts_dir=tmp / "art",
                            backup_dir=tmp / "backups")
        try:
            expect = build(s, tmp, sz)
            comp, services = components(s, tmp, noop=noop)
            out = validate(s, tmp, expect, comp, services)
        finally:
            s.close()
    out["scale"] = scale
    out["noop"] = noop
    return out


# ---- timing (only after validity) ---------------------------------------------


def timing(s, tmp, meter, comp, services, sz):
    res = {}
    ps, sm, sp, ex = (services["ps"], services["sm"], services["sp"],
                      services["ex"])

    def record(name, reps, fn, *, one_shot=False):
        walls, waits, holds = [], [], []
        out = None
        for _ in range(reps):
            out, ms, w, h = run_with_probes(s, meter, fn)
            walls.append(ms)
            waits += w
            holds += h
        res[name] = {"wall": stats(walls), "probe_wait": stats(waits),
                     "writer_hold": stats(holds),
                     "writer_ops": len(holds), "one_shot": one_shot}
        return out

    # One-shot work (it consumes its input): measured once, validated
    # separately above on an identical world.
    record("mining_observations", 1, comp["mining"], one_shot=True)
    record("note_mining", 1, comp["note_mining"], one_shot=True)
    record("profile_compute", 5, ps.compute)
    record("profile_idle_unchanged", 7,
           lambda: ps.compute(only_if_changed=True))
    policies = iter(f"bench-policy-{k}" for k in range(100))
    record("sampling_refresh", 5, lambda: sm.refresh(policy=next(policies)))
    record("review_queue", 10, review.ReviewService(s).queue)
    record("split_assign", 5, sp.assign)
    record("contamination_check", 10, sp.contamination)
    dests = iter(tmp / f"dataset-t{k}" for k in range(100))
    views = ("asr_supervised", "cleanup_supervised")
    record("export_asr_cleanup", 3,
           lambda: ex.build(next(dests), task_views=views))
    last = sorted(tmp.glob("dataset-t*"))[-1]
    exported_bytes = sum(p.stat().st_size for p in last.rglob("*")
                         if p.is_file())
    wall_s = res["export_asr_cleanup"]["wall"]["p50_ms"] / 1000.0
    res["export_asr_cleanup"]["dataset_bytes"] = exported_bytes
    res["export_asr_cleanup"]["throughput_mb_per_s"] = round(
        exported_bytes / 1e6 / wall_s, 1) if wall_s else None
    walls = []
    for _ in range(3):
        t = time.monotonic()
        report = export_mod.validate_dataset(last)
        walls.append((time.monotonic() - t) * 1000.0)
    res["validate"] = {"wall": stats(walls), "valid": report["valid"]}
    # Python peak memory, from separate traced runs (tracemalloc slows
    # the run several-fold, so timings never come from these).
    for name, fn in (("profile_compute", ps.compute),
                     ("export_asr_cleanup",
                      lambda: ex.build(tmp / "dataset-mem",
                                       task_views=views)),
                     ("export_text_only_control",
                      lambda: ex.build(tmp / "dataset-text",
                                       task_views=("cleanup_supervised",))),
                     ("validate", lambda: export_mod.validate_dataset(last))):
        tracemalloc.start()
        tracemalloc.reset_peak()
        fn()
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        res.setdefault(name, {})["python_peak_mb"] = round(peak / 1e6, 1)
    return res


def environment():
    def sh(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:
            return None
    head = sh("git", "-C", str(ROOT), "rev-parse", "HEAD")
    dirty = sh("git", "-C", str(ROOT), "status", "--porcelain",
               "--untracked-files=no", "--", "localflow", "scripts")
    try:
        import objc
        pyobjc = objc.__version__
    except Exception:
        pyobjc = None
    return {"code_sha": head, "tree_modified": bool(dirty),
            "mac_model": sh("sysctl", "-n", "hw.model"),
            "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string"),
            "memory_bytes": int(sh("sysctl", "-n", "hw.memsize") or 0),
            "macos": f"{platform.mac_ver()[0]}"
                     f" ({sh('sw_vers', '-buildVersion')})",
            "python": sys.version.split()[0], "pyobjc": pyobjc,
            "sqlite": sqlite3.sqlite_version,
            "power": (sh("pmset", "-g", "batt") or "").splitlines()[0:1],
            "load_average": list(os.getloadavg())}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--scale", choices=("small", "full"), default="full")
    ap.add_argument("--noop", choices=COMPONENTS)
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args(argv)
    sz = sizes(args.scale)
    env_before = environment()
    t_build = time.monotonic()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        # Validity on its own world: every component's work recounted.
        v = tmp / "validity"
        v.mkdir()
        s = store_mod.Store(v / "v2.db", artifacts_dir=v / "art",
                            backup_dir=v / "backups")
        try:
            expect = build(s, v, sz)
            comp, services = components(s, v, noop=args.noop)
            validity = validate(s, v, expect, comp, services)
        finally:
            s.close()
        print(f"validity: {'valid' if validity['valid'] else 'INVALID'}"
              f" {validity['reasons']}", flush=True)
        results = None
        if validity["valid"] and not args.validate_only:
            t = tmp / "timing"
            t.mkdir()
            s = store_mod.Store(t / "v2.db", artifacts_dir=t / "art",
                                backup_dir=t / "backups")
            try:
                build(s, t, sz)
                meter = WriterMeter(s)
                comp, services = components(s, t)
                cold = time.monotonic()
                results = timing(s, t, meter, comp, services, sz)
                results["timed_seconds"] = round(time.monotonic() - cold, 1)
            finally:
                s.close()
    payload = {
        "milestone": "M14", "tool": "scripts/v2/benchmark_m14.py",
        "status": "valid" if validity["valid"] else "INVALID",
        "scale": args.scale, "sizes": sz, "noop": args.noop,
        "validity": {k: v for k, v in validity.items()},
        "results": results,
        "build_and_run_seconds": round(time.monotonic() - t_build, 1),
        "definitions": {
            "wall": "one component call, wall clock (p50/p95/p99 over"
                    " its repetitions; one_shot components run once)",
            "probe_wait": "submit→commit of a dictation-shaped write"
                          " (artifact row + lease) submitted"
                          " continuously while the component runs",
            "writer_hold": "time each of the component's own ops"
                           " occupied the single writer, measured inside"
                           " the writer thread",
            "warm_state": "a freshly built store per run; each timed"
                          " component follows the one before it (no"
                          " process restart between components)"},
        "environment": env_before,
        "environment_after": environment()}
    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "m14.json").write_text(json.dumps(
            payload, indent=1, sort_keys=True, default=sorted) + "\n")
        print(f"wrote {out / 'm14.json'}")
    if results:
        for name, r in results.items():
            if isinstance(r, dict) and "wall" in r:
                print(f"{name}: wall {r['wall']} · probe wait"
                      f" {r.get('probe_wait')} · hold {r.get('writer_hold')}")
    return EXIT_OK if validity["valid"] else EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
