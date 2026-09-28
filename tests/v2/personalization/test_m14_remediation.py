"""M14 remediation suite (2026-09-28 read-only audit at 1e351d7).

At least one fail-first regression per audit finding plus preservation
controls for the protections the audit verified strong. Every case
drives a real production surface (the store writer, the M14 services,
the M05 vocabulary store, the export builder and validator, the real
coordinator and Hub headless) and grades it against an independent
expectation — literal values, raw rows, file bytes or the world's own
counts, never the production helper under test. Ordering at seams is
decided by op hooks and latches (``m14_world``), never sleeps.

The same file runs on the audited base (copied into a detached base
worktree) and on the repaired tree. A case that needs a surface the
repair adds degrades to the base's nearest path where one exists (so
the base reproduces the BEHAVIOR), else reports ERROR — never PASS.

Run:
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/personalization/test_m14_remediation.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import m14_world as W  # noqa: E402
from m14_world import (A_CANARY, APP, B_CANARY, PRIVATE_CANARY,  # noqa: E402
                       TYPED_CANARY, MWorld, accepts, after_each_op,
                       patched, read_jsonl, sha256_file, wav_frames)

from localflow.v2 import ids  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402

ROOT = W.ROOT
CASES = []
ALL_VIEWS = ("asr_supervised", "asr_span_graft_weak", "cleanup_supervised",
             "transform_supervised", "preference_pairs")


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


def refused(fn, *a, **kw):
    """(True, message) when the call raised, else (False, result)."""
    try:
        return False, fn(*a, **kw)
    except Exception as e:  # noqa: BLE001 — refusal of any typed kind
        return True, f"{type(e).__name__}: {e}"


def export_or_refusal(w, dest, views, **kw):
    try:
        return w.export(dest, views, **kw), None
    except export_mod.ExportError as e:
        return None, str(e)


def export_records(w, dest):
    root = w.tmp / dest
    return (read_jsonl(root / "examples.jsonl"),
            read_jsonl(root / "references.jsonl"),
            read_jsonl(root / "preferences.jsonl"))


def asr_ids(examples):
    return {e["example_id"] for e in examples
            if e.get("task_kind") == "asr_supervised"}


def db_text_dump(w):
    """Every text value in every table (the canary scan's haystack)."""
    out = []
    for (table,) in w.rows("SELECT name FROM sqlite_master WHERE"
                           " type='table'"):
        for row in w.rows(f"SELECT * FROM {table}"):
            for v in row:
                if isinstance(v, str):
                    out.append((table, v))
    return out


# =============================================================================
# Phase A — evidence authority and filesystem boundaries
# =============================================================================

@case("M14-AUDIT-01")
def f01_foreign_audio_is_not_asr_evidence():
    with MWorld() as w:
        a = w.ready_asr(f"alpha witness {A_CANARY}", freq=300.0)
        b = w.ready_asr(f"beta witness {B_CANARY}", freq=700.0)
        w.families(10, asr=True)
        assert w.review.verified_asr_eligible(a["example_id"])["eligible"]
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("original_audio", b["audio_aid"]))
        gate = w.review.verified_asr_eligible(a["example_id"])
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("asr_supervised",))
        leaked = []
        if out is not None:
            exs, _refs, _p = export_records(w, "ds")
            b_frames = wav_frames(w.store.artifacts_dir
                                  / f"{b['audio_aid']}.wav")
            for e in exs:
                if e["example_id"] == a["example_id"]:
                    leaked.append("A exported")
                    if wav_frames(w.tmp / "ds" / e["audio"]) == b_frames:
                        leaked.append("A carries B's audio bytes")
            assert b["example_id"] in asr_ids(exs), "B control lost"
        assert not gate["eligible"] and not leaked, (gate, leaked, err)


@case("M14-AUDIT-01")
def f01_wrong_role_own_audio_is_not_asr_evidence():
    with MWorld() as w:
        a = w.ready_asr()
        other = w.store.write_audio_artifact(
            job_id=a["job_id"], stage="capture", samples=W.tone(440.0),
            sample_rate=W.RATE, role="debug_audio")
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("original_audio", other))
        gate = w.review.verified_asr_eligible(a["example_id"])
        assert not gate["eligible"], gate


@case("M14-AUDIT-01")
def f01_foreign_verbatim_reference_is_refused():
    with MWorld() as w:
        a = w.ready_asr()
        b = w.ready_asr(f"bravo reference {B_CANARY}")
        b_ref = w.envelope(b["example_id"])["annotations"][0]["artifact_id"]

        def swap(env):
            env["annotations"][0]["artifact_id"] = b_ref
        w.rewrite_envelope(a["example_id"], swap)
        w.families(10, asr=True)
        w.splits.assign()
        gate = w.review.verified_asr_eligible(a["example_id"])
        out, err = export_or_refusal(w, "ds", ("asr_supervised",))
        foreign = []
        if out is not None:
            _e, refs, _p = export_records(w, "ds")
            foreign = [r for r in refs if r["example_id"] == a["example_id"]
                       and B_CANARY in (r.get("text") or "")]
        assert not gate["eligible"] and not foreign, (gate, foreign, err)


@case("M14-AUDIT-01")
def f01_foreign_or_wrong_stage_cleanup_source_is_refused():
    with MWorld() as w:
        a = w.ready_cleanup(f"cleanup alpha {A_CANARY}")
        b = w.ready_cleanup(f"cleanup bravo {B_CANARY}")
        c = w.ready_cleanup("cleanup charlie text")
        w.families(10)
        # A: source_text names B's raw transcript (foreign job).
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", b["raw_aid"]))
        # C: source_text names C's OWN applied output (wrong stage).
        w.rewrite_envelope(c["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", c["applied_aid"]))
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("cleanup_supervised",))
        assert out is not None, err
        exs, _r, _p = export_records(w, "ds")
        got = {e["example_id"] for e in exs
               if e["task_kind"] == "cleanup_supervised"}
        ready = w.training.readiness()["readiness_metrics"][
            "task_eligibility"]["cleanup_supervised"]
        assert b["example_id"] in got, "intact control B lost"
        problems = [n for n, x in (("A foreign", a), ("C wrong stage", c))
                    if x["example_id"] in got]
        assert not problems and ready["count"] == len(got), (
            problems, ready, sorted(got))


@case("M14-AUDIT-01")
def f01_profile_reads_only_own_raw_speech():
    with MWorld(min_words=10) as w:
        a = w.job(f"alpha speaks {A_CANARY} {A_CANARY}", audio=False)
        b = w.job(f"bravo speaks {B_CANARY} {B_CANARY} with more words",
                  audio=False)
        # A job with no training example: its raw text is not speech
        # evidence of A (distinct text, so dedup cannot mask a read).
        c = w.job("charlie foreign words never spoken by alpha at all",
                  audio=False, example=False)
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", c["raw_aid"]))
        snap = w.profile.compute()
        m = snap["measured"]
        # Only B's own speech is eligible (A's pointer is foreign).
        assert (m["eligible_examples"], m["eligible_words"]) == (
            1, len(b["raw"].split())), (m["eligible_examples"],
                                        m["eligible_words"])


@case("M14-AUDIT-01")
def f01_observation_payload_of_another_job_is_refused():
    with MWorld() as w:
        a = w.job("please check the modul today")
        b = w.job("unrelated bravo dictation words")
        w.observation(a["job_id"], "please check the modul today",
                      "please check the module today",
                      before_job=b["job_id"], after_job=b["job_id"])
        w.learning.mine_observation_candidates()
        live = w.rows("SELECT status FROM learning_candidates WHERE"
                      " status='pending'")
        assert not live, live


@case("M14-AUDIT-02")
def f02_unowned_staging_directory_is_never_removed():
    with MWorld() as w:
        w.families(10, asr=True)
        w.splits.assign()
        sentinel_dir = w.tmp / ".ds.building" / "nested"
        sentinel_dir.mkdir(parents=True)
        sentinel = sentinel_dir / "UNRELATED_KEEP"
        sentinel.write_bytes(b"keep-these-bytes-\x00\x01\x02")
        # With consent disabled (a refused export) and then enabled.
        w.store.append_consent("disabled")
        export_or_refusal(w, "ds", ("asr_supervised",))
        survived_refusal = sentinel.is_file() and \
            sentinel.read_bytes() == b"keep-these-bytes-\x00\x01\x02"
        w.store.append_consent("enabled")
        out, err = export_or_refusal(w, "ds", ("asr_supervised",))
        survived = sentinel.is_file() and \
            sentinel.read_bytes() == b"keep-these-bytes-\x00\x01\x02"
        assert survived_refusal and survived, (survived_refusal, survived,
                                               err)


@case("M14-AUDIT-03")
def f03_purged_artifact_mid_compute_is_not_published():
    with MWorld() as w:
        phrase = f"{PRIVATE_CANARY.lower()} zephyr"
        jobs = []
        for i in range(10):
            words = [f"w{i}x{k}" for k in range(198)]
            if i < 2:
                words[5:7] = phrase.split()
            jobs.append(w.job(" ".join(words), audio=False))
        target = jobs[0]
        seam = {"reached": 0}
        orig = type(w.profile)._read_candidates

        def wrap(original):
            def read(self, conn, example_ids):
                out = original(self, conn, example_ids)
                if target["example_id"] in example_ids \
                        and not seam["reached"]:
                    seam["reached"] += 1
                    # Inside the writer: queue the purge (never wait on
                    # the writer from the writer) — it commits right
                    # after this read op.
                    w.store._submit(lambda: (
                        w.store._purge_artifact(target["raw_aid"],
                                                reason="retention"),
                        setattr(w.store, "_purge_pending", True)))
                return out
            return read
        with patched(type(w.profile), "_read_candidates", wrap):
            w.profile.compute()
        assert orig is type(w.profile)._read_candidates
        assert seam["reached"], "seam never reached"
        cur = w.profile.current()
        blob = json.dumps(cur)
        assert PRIVATE_CANARY.lower() not in blob, (
            cur["state"], [p["phrase"] for p in
                           cur["measured"].get("frequent_phrases") or []])


@case("M14-AUDIT-03")
def f03_purge_after_publication_invalidates_current():
    with MWorld() as w:
        phrase = f"{PRIVATE_CANARY.lower()} zephyr"
        jobs = []
        for i in range(10):
            words = [f"v{i}y{k}" for k in range(198)]
            if i < 2:
                words[3:5] = phrase.split()
            jobs.append(w.job(" ".join(words), audio=False))
        snap = w.profile.compute()
        assert any(p["phrase"] == phrase
                   for p in snap["measured"]["frequent_phrases"])
        w.purge(jobs[0]["raw_aid"])  # the example stays trainable
        cur = w.profile.current()
        assert PRIVATE_CANARY.lower() not in json.dumps(cur), cur["state"]


@case("M14-AUDIT-04")
def f04_new_export_from_old_version_cannot_reclaim_blindness():
    with MWorld() as w:
        w.families(30, asr=True, frozen=3)
        v1 = w.splits.assign()["assignment_version"]
        frozen = [r[0] for r in w.rows(
            "SELECT DISTINCT family_id FROM training_memberships WHERE"
            " assignment_version=? AND partition='frozen_test'", (v1,))]
        assert frozen, "fixture has no frozen family"
        w.splits.mark_exposed([frozen[0]], "inspected_during_tuning")
        out, err = export_or_refusal(w, "ds", ("asr_supervised",),
                                     partitions=("frozen_test",),
                                     assignment_version=v1)
        if out is None:
            return  # refused: no fresh blind claim
        exs, _r, _p = export_records(w, "ds")
        fams = {e["example_id"]: e for e in exs}
        claims = [e for e in fams.values()
                  if e["family_id"] == frozen[0]
                  and e.get("split") == "frozen_test"
                  and not e.get("exposed")]
        assert not claims, f"{len(claims)} fresh unexposed frozen claims"


@case("M14-AUDIT-05")
def f05_outside_audio_path_is_never_read():
    with MWorld() as w:
        a = w.ready_asr()
        w.families(10, asr=True)
        outside = w.tmp / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel.wav"
        store_mod.write_wav_f32(sentinel, W.tone(911.0), W.RATE)
        digest = sha256_file(sentinel)
        link = w.store.artifacts_dir / "link-to-outside.wav"
        os.symlink(sentinel, link)
        leaks = []
        for variant in (str(sentinel), "../outside/sentinel.wav",
                        "link-to-outside.wav"):
            w.store.submit(lambda c, v=variant: c.execute(
                "UPDATE artifacts SET content_path=?, sha256=? WHERE"
                " artifact_id=?", (v, digest, a["audio_aid"])))
            w.splits.assign()
            dest = f"ds-{len(leaks)}-{abs(hash(variant)) % 997}"
            out, _err = export_or_refusal(w, dest, ("asr_supervised",))
            if out is not None:
                for f in (w.tmp / dest / "artifacts").glob("*"):
                    if sha256_file(f) == digest:
                        leaks.append(variant)
        assert not leaks, leaks


@case("M14-AUDIT-06")
def f06_purge_serialized_before_publication_is_not_published():
    with MWorld() as w:
        a = w.ready_asr()
        w.families(10, asr=True)
        w.splits.assign()
        state = {"hook": 0, "purged_before_publish": False}
        real_rename = os.rename

        def rename(src, dst, *rest, **kw):
            if ".building" in str(src) and not state["hook"]:
                state["hook"] += 1
                in_writer = threading.current_thread().name == \
                    "localflow-v2-store"

                def purge():
                    w.store._purge_artifact(a["audio_aid"],
                                            reason="retention")
                    w.store._purge_pending = True
                if in_writer:
                    # Publication is inside a writer op: a purge can
                    # only serialize after it.
                    w.store._submit(purge)
                else:
                    w.store._submit(purge, wait=True)
                    state["purged_before_publish"] = True
            return real_rename(src, dst, *rest, **kw)
        os.rename = rename
        try:
            out, err = export_or_refusal(w, "ds", ("asr_supervised",))
        finally:
            os.rename = real_rename
        w.store.sync()
        assert state["hook"], "publication seam never reached"
        assert not (out is not None and state["purged_before_publish"]), (
            "a completed export contains a source purged before its"
            " publication")


@case("M14-AUDIT-06")
def f06_consent_revoked_before_publication_is_not_published():
    with MWorld() as w:
        w.families(10, asr=True)
        w.splits.assign()
        state = {"hook": 0, "revoked_before_publish": False}
        real_rename = os.rename

        def rename(src, dst, *rest, **kw):
            if ".building" in str(src) and not state["hook"]:
                state["hook"] += 1
                if threading.current_thread().name == "localflow-v2-store":
                    w.store.append_consent("disabled")  # queued after
                else:
                    w.store.append_consent("disabled")
                    w.store.sync()
                    state["revoked_before_publish"] = True
            return real_rename(src, dst, *rest, **kw)
        os.rename = rename
        try:
            out, _err = export_or_refusal(w, "ds", ("asr_supervised",))
        finally:
            os.rename = real_rename
        w.store.sync()
        assert state["hook"], "publication seam never reached"
        assert not (out is not None and state["revoked_before_publish"])


@case("M14-AUDIT-07")
def f07_self_consistent_semantic_tamper_is_rejected():
    with MWorld() as w:
        w.families(10, asr=True)
        t = w.transform_task(f"draft source {A_CANARY}",
                             [f"Draft A {A_CANARY}.", f"Draft B {B_CANARY}."])
        w.judge(t, t["candidates"][0]["candidate_id"],
                t["candidates"][1]["candidate_id"], "prefer_b")
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ALL_VIEWS)
        assert out is not None, err
        root = w.tmp / "ds"
        assert export_mod.validate_dataset(root)["valid"]
        prefs = read_jsonl(root / "preferences.jsonl")
        # The rewrite helper is itself consistent: an unchanged rewrite
        # still validates (so a rejection below is semantic).
        _rewrite_consistently(root, preferences=prefs)
        assert export_mod.validate_dataset(root)["valid"], \
            "consistent rewrite helper broke validity"
        # Tamper: chosen slot contradicts the judgment; every checksum
        # and the fingerprint are recomputed consistently.
        prefs[0]["chosen"] = "a"
        _rewrite_consistently(root, preferences=prefs)
        report = export_mod.validate_dataset(root)
        assert not report["valid"], "chosen/judgment mismatch accepted"


@case("M14-AUDIT-07")
def f07_preference_input_reconstructs_from_the_package():
    with MWorld() as w:
        w.families(10, asr=True)
        t = w.transform_task(f"reconstruct me {A_CANARY}",
                             ["Output one.", "Output two."])
        w.judge(t, t["candidates"][0]["candidate_id"],
                t["candidates"][1]["candidate_id"], "prefer_a")
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("preference_pairs",))
        assert out is not None, err
        moved = w.tmp / "moved"
        shutil.move(str(w.tmp / "ds"), moved)
        prefs = read_jsonl(moved / "preferences.jsonl")
        text = json.dumps(prefs)
        # The conditional input itself (not only its hash) travels.
        assert t["source"] in text, "task input absent from the package"


def _rewrite_consistently(root, *, examples=None, references=None,
                          preferences=None):
    root = pathlib.Path(root)
    for name, rows in (("examples.jsonl", examples),
                       ("references.jsonl", references),
                       ("preferences.jsonl", preferences)):
        if rows is not None:
            (root / name).write_text("".join(
                json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                for r in rows), encoding="utf-8")
    ex = read_jsonl(root / "examples.jsonl")
    refs = read_jsonl(root / "references.jsonl")
    prefs = read_jsonl(root / "preferences.jsonl")
    manifest = json.loads((root / "dataset_manifest.json").read_text())
    semantic = {n: sorted(r, key=lambda e: json.dumps(e, sort_keys=True))
                for n, r in (("examples", ex), ("references", refs),
                             ("preferences", prefs))}
    manifest["content_fingerprint"] = export_mod._fingerprint(semantic)
    (root / "dataset_manifest.json").write_text(json.dumps(
        manifest, ensure_ascii=False, indent=1, sort_keys=True))
    export_mod._write_sums(root)


@case("M14-AUDIT-08")
def f08_purged_task_source_makes_pair_ineligible():
    with MWorld() as w:
        w.families(10, asr=True)
        dead = w.transform_task("dead source text", ["Dead A.", "Dead B."])
        live = w.transform_task("live source text",
                                [f"Live A {A_CANARY}.",
                                 f"Live B {B_CANARY}."])
        for t in (dead, live):
            w.judge(t, t["candidates"][0]["candidate_id"],
                    t["candidates"][1]["candidate_id"], "prefer_b")
        for c in dead["candidates"]:
            w.purge(c["source_aid"])
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("preference_pairs",))
        assert out is not None, err
        _e, _r, prefs = export_records(w, "ds")
        keys = {p["task_key"] for p in prefs}
        assert live["task_key"] in keys, "live control lost"
        chosen = [c for p in prefs if p["task_key"] == live["task_key"]
                  for c in p["candidates"] if c["slot"] == p["chosen"]]
        assert chosen and B_CANARY in chosen[0]["output_text"]
        assert dead["task_key"] not in keys, "purged-input pair exported"


@case("control:selected-purge-before-fence")
def c_selected_purge_before_fence_aborts():
    with MWorld() as w:
        a = w.ready_asr()
        w.families(10, asr=True)
        w.splits.assign()
        state = {"n": 0}

        def wrap(original):
            def sha(path):
                state["n"] += 1
                if state["n"] == 1:
                    w.purge(a["audio_aid"])
                return original(path)
            return sha
        with patched(export_mod, "_sha256_file", wrap):
            out, err = export_or_refusal(w, "ds", ("asr_supervised",))
        assert state["n"], "seam never reached"
        assert out is None and not (w.tmp / "ds").exists(), (out, err)


@case("control:unrelated-deletion-completes")
def c_unrelated_deletion_does_not_abort():
    with MWorld() as w:
        w.families(10, asr=True)
        other = w.job("unrelated deletion target", audio=False,
                      example=False)
        w.splits.assign()
        state = {"n": 0}

        def wrap(original):
            def sha(path):
                state["n"] += 1
                if state["n"] == 1:
                    w.store.delete_everywhere("job", other["job_id"])
                return original(path)
            return sha
        with patched(export_mod, "_sha256_file", wrap):
            out, err = export_or_refusal(w, "ds", ("asr_supervised",))
        assert state["n"] and out is not None and \
            out["state"] == "complete", err


# =============================================================================
# Phase B — explicit human authority and reversibility
# =============================================================================

TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"


def taught(w, *, app=APP, example=True):
    j = w.job(TEACH_RAW, app=app, example=example)
    out = w.learning.teach_correction(j["job_id"], TEACH_FIX)
    return j, out["candidate_id"]


def learned_entries(w, alias="modul"):
    return {eid: e for eid, e in w.entries().items()
            if any(a.lower() == alias and ok for a, ok in e[6])}


@case("M14-AUDIT-09")
def f09_deletion_between_plan_and_effect_leaves_no_orphan_rule():
    with MWorld() as w:
        j, cid = taught(w)
        state = {"fired": False}

        def hook():
            if state["fired"]:
                return
            row = w.one("SELECT status, vocabulary_entry_id FROM"
                        " learning_candidates WHERE candidate_id=?",
                        (cid,))
            if row and row[0] == "pending" and row[1]:
                state["fired"] = True  # plan committed, effect pending
                w.store.delete_everywhere("job", j["job_id"])
        with after_each_op(w.store, hook):
            refused(w.learning.approve, cid)
        if not state["fired"]:
            # Approval committed as one op: a deletion now follows it
            # (the documented policy — an approved rule lives on).
            w.store.delete_everywhere("job", j["job_id"])
        c = w.candidate(cid)
        rules = {eid: e for eid, e in learned_entries(w).items() if e[3]}
        assert not (rules and c["status"] != "approved"), (
            f"orphan rule: {len(rules)} active learned entries while the"
            f" candidate is {c['status']}")


@case("M14-AUDIT-09")
def f09_rejection_between_plan_and_effect_leaves_no_orphan_rule():
    with MWorld() as w:
        _j, cid = taught(w)
        state = {"fired": False}

        def hook():
            if state["fired"]:
                return
            row = w.one("SELECT status, vocabulary_entry_id FROM"
                        " learning_candidates WHERE candidate_id=?",
                        (cid,))
            if row and row[0] == "pending" and row[1]:
                state["fired"] = True
                refused(w.learning.reject, cid)
        with after_each_op(w.store, hook):
            refused(w.learning.approve, cid)
        c = w.candidate(cid)
        rules = {eid: e for eid, e in learned_entries(w).items() if e[3]}
        assert not (rules and c["status"] != "approved"), (
            f"orphan rule while candidate {c['status']}")


@case("M14-AUDIT-10")
def f10_undo_keeps_later_user_edits_of_a_created_entry():
    with MWorld() as w:
        _j, cid = taught(w)
        out = w.learning.approve(cid)
        eid = out["entry_id"]
        entry = w.vocab.entry(eid)
        # The user adds their own alias to the learned entry.
        w.vocab.update_entry(eid, aliases=[(a.alias, a.approved)
                                           for a in entry.aliases]
                             + [("moduel", True)])
        refused(w.learning.undo_approval, cid)
        got = w.normalize("please check the moduel now", app=APP)
        assert got == "please check the module now", (
            f"user alias no longer effective after undo: {got!r}")


@case("M14-AUDIT-10")
def f10_concurrent_user_alias_survives_alias_undo():
    with MWorld() as w:
        eid = w.vocab.add_entry("module", [("moduul", True)],
                                scope_kind="app", scope_value=APP,
                                approved=True)
        _j, cid = taught(w)
        out = w.learning.approve(cid)
        assert out.get("action") == "alias_added", out
        ops = {"n": 0, "edited": False}

        def user_edit():
            cur = w.vocab.entry(eid)
            w.vocab.update_entry(eid, aliases=[(a.alias, a.approved)
                                               for a in cur.aliases]
                                 + [("modyul", True)])
            ops["edited"] = True

        def hook():
            ops["n"] += 1
            # Between undo's second and third op: after it has read the
            # entry, before it writes (the base's read/update window).
            if ops["n"] == 2 and not ops["edited"]:
                user_edit()
        with after_each_op(w.store, hook):
            refused(w.learning.undo_approval, cid)
        if not ops["edited"]:
            # Undo was one op: the user's edit can only follow it.
            user_edit()
        aliases = {a.lower() for a, ok in w.entries()[eid][6] if ok}
        assert "modyul" in aliases and "moduul" in aliases, aliases


@case("M14-AUDIT-11")
def f11_teach_refuses_a_final_newer_than_the_rendered_one():
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        f1 = j["applied_aid"]
        f1_text = j["applied"]
        f2 = w.store.write_text_artifact(
            job_id=j["job_id"], stage="cleanup", role="applied_output",
            text="please check the modal today again",
            retention_class="training", parent_artifact_id=j["raw_aid"])
        w.rewrite_envelope(j["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("applied_output", f2))
        kw = {}
        if accepts(w.learning.teach_correction,
                   "expected_final_artifact_id"):
            kw = {"expected_final_artifact_id": f1,
                  "expected_final_sha256": ids.sha256_text(f1_text)}
        was_refused, out = refused(w.learning.teach_correction,
                                   j["job_id"], TEACH_FIX, **kw)
        if was_refused:
            return
        before = (w.payload(out["candidate_id"]) or {}).get("before")
        assert before == f1_text, (
            f"taught against a text the reviewer never saw: {before!r}")


@case("M14-AUDIT-11")
def f11_teach_never_substitutes_raw_for_a_missing_final():
    with MWorld() as w:
        j = w.job(TEACH_RAW, "Please check the modul today.",
                  example=False)
        w.purge(j["applied_aid"])
        was_refused, out = refused(w.learning.teach_correction,
                                   j["job_id"],
                                   "Please check the module today.")
        assert was_refused, (
            "teach compared against the raw transcript in place of the"
            " purged final", (w.payload(out["candidate_id"]) or {}).get(
                "before"))


@case("M14-AUDIT-12")
def f12_graft_refuses_a_changed_source_with_the_same_substring():
    from localflow.v2.curation import classify
    with MWorld() as w:
        j = w.job("send the cloud report on friday")
        s1 = j["raw_aid"]
        spans = classify.changed_regions(j["raw"],
                                         "send the Claude report on friday")
        s2 = w.store.write_text_artifact(
            job_id=j["job_id"], stage="asr", role="raw_transcript",
            text="send the cloud memo to sunday", retention_class="training")
        w.rewrite_envelope(j["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", s2))
        kw = {}
        if accepts(w.review.record_label, "expected_source_artifact_id"):
            kw = {"expected_source_artifact_id": s1,
                  "expected_source_sha256": ids.sha256_text(j["raw"])}
        was_refused, _ = refused(
            w.review.record_label, j["example_id"],
            edit_kind="recognition_error", origin_stages=("asr",),
            confirmed_spans=[spans[0]], **kw)
        assert was_refused, "graft saved against a source nobody reviewed"


@case("M14-AUDIT-12")
def f12_graft_span_offsets_are_strict_integers():
    with MWorld() as w:
        j = w.job("a cloud report on friday")
        bad = {"start": True, "end": 7, "before_words": ["cloud"],
               "after_words": ["Claude"]}
        # start=True slices [1:7] (" cloud") and passes a word check —
        # a bool is still not an offset.
        was_refused, _ = refused(
            w.review.record_label, j["example_id"],
            edit_kind="recognition_error", confirmed_spans=[bad])
        grafts = w.rows("SELECT COUNT(*) FROM artifacts WHERE"
                        " role='span_graft'")[0][0]
        assert was_refused and grafts == 0, (was_refused, grafts)


@case("M14-AUDIT-13")
def f13_typed_only_region_is_not_dictation_evidence():
    from localflow.v2 import notes as notes_mod
    with MWorld() as w:
        ns = notes_mod.NoteStore(w.store)
        a = w.job("alpha checks the modul today")
        nid = ns.create_note(a["raw"], origin=notes_mod.ORIGIN_DICTATED,
                             source_job_id=a["job_id"])["note_id"]
        ns.append_revision(nid, f"{a['raw']} and {TYPED_CANARY} words",
                           origin=notes_mod.ORIGIN_TYPED,
                           trigger=notes_mod.TRIGGER_AUTOSAVE)
        w.store.submit(lambda c: c.execute(
            "INSERT INTO note_evidence_links(note_id, example_id, job_id,"
            " first_seen_utc) VALUES(?,?,?,?)",
            (nid, a["example_id"], a["job_id"], ids.now_utc_iso())))
        # One typed revision: a correction inside A's dictated words AND
        # an unrelated change to the user's own typed words.
        ns.append_revision(
            nid, f"alpha checks the module today and {TYPED_CANARY}x"
                 " words", origin=notes_mod.ORIGIN_TYPED,
            trigger=notes_mod.TRIGGER_AUTOSAVE)
        w.learning.mine_observation_candidates()
        leaks = []
        for (cid,) in w.rows("SELECT candidate_id FROM learning_candidates"
                             " WHERE source='note_revision'"):
            payload = json.dumps(w.payload(cid) or {})
            if TYPED_CANARY in payload:
                leaks.append(cid)
        assert not leaks, "typed-only words kept as dictation evidence"


@case("M14-AUDIT-15")
def f15_counterexample_phrase_is_not_candidate_metadata():
    with MWorld() as w:
        j, cid = taught(w)
        phrase = f"keep the modul named {PRIVATE_CANARY} here"
        out = w.learning.approve(cid, counterexamples=(phrase,))
        assert out.get("flips"), "fixture: the phrase must flip"
        row = w.one("SELECT * FROM learning_candidates WHERE"
                    " candidate_id=?", (cid,))
        in_row = [v for v in row if isinstance(v, str)
                  and PRIVATE_CANARY in v]
        w.store.delete_everywhere("job", j["job_id"])
        remaining = [t for t, v in db_text_dump(w) if PRIVATE_CANARY in v]
        assert not in_row and not remaining, (len(in_row), remaining)


@case("M14-AUDIT-17")
def f17_label_retry_with_one_operation_is_one_revision():
    with MWorld() as w:
        j = w.job("label retry target words")
        kw = {"operation_id": "op-label-fixed"} if accepts(
            w.review.record_label, "operation_id") else {}
        w.review.record_label(j["example_id"], edit_kind="recognition_error",
                              **kw)
        refused(w.review.record_label, j["example_id"],
                edit_kind="recognition_error", **kw)
        n = w.one("SELECT COUNT(*) FROM correction_labels WHERE"
                  " example_id=?", (j["example_id"],))[0]
        assert n == 1, f"{n} revisions for one logical save"


@case("M14-AUDIT-17")
def f17_split_retry_with_one_operation_is_one_version():
    with MWorld() as w:
        w.families(10)
        kw = {"operation_id": "op-assign-fixed"} if accepts(
            w.splits.assign, "operation_id") else {}
        w.splits.assign(**kw)
        w.splits.assign(**kw)
        n = w.one("SELECT COUNT(*) FROM split_assignments")[0]
        assert n == 1, f"{n} versions for one logical assignment"


@case("M14-AUDIT-17")
def f17_approval_retry_after_unknown_outcome_reconciles():
    with MWorld() as w:
        _j, cid = taught(w)
        kw = {"operation_id": "op-approve-fixed"} if accepts(
            w.learning.approve, "operation_id") else {}
        first = w.learning.approve(cid, **kw)
        before = w.entries()
        was_refused, second = refused(w.learning.approve, cid, **kw)
        assert not was_refused, f"retry reported failure: {second}"
        assert w.entries() == before and \
            second.get("entry_id") == first.get("entry_id"), second


@case("M14-AUDIT-24")
def f24_unpin_keeps_review_retention_leases():
    from localflow.v2.curation import classify
    with MWorld() as w:
        j, cid = taught(w)
        g = w.job("send the cloud report on friday")
        spans = classify.changed_regions(g["raw"],
                                         "send the Claude report on friday")
        kw = {}
        if accepts(w.review.record_label, "expected_source_artifact_id"):
            kw = {"expected_source_artifact_id": g["raw_aid"],
                  "expected_source_sha256": ids.sha256_text(g["raw"])}
        lab = w.review.record_label(g["example_id"],
                                    edit_kind="recognition_error",
                                    confirmed_spans=[spans[0]], **kw)
        teach_payload = w.candidate(cid)["payload_aid"]
        graft = lab["graft_artifact_id"]
        for ex in (j["example_id"], g["example_id"]):
            w.training.pin(ex, True)
            w.training.pin(ex, False)
        live = {aid: w.one(
            "SELECT COUNT(*) FROM artifact_leases WHERE artifact_id=? AND"
            " expires_at_utc IS NULL AND revoked_at_utc IS NULL",
            (aid,))[0] for aid in (teach_payload, graft)}
        assert all(live.values()), f"review leases revoked by unpin: {live}"


@case("M14-AUDIT-24")
def f24_pin_never_makes_a_machine_suggestion_permanent():
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        w.observation(j["job_id"], TEACH_RAW, TEACH_FIX)
        w.learning.mine_observation_candidates()
        (cid,) = w.one("SELECT candidate_id FROM learning_candidates"
                       " WHERE status='pending'")
        payload = w.candidate(cid)["payload_aid"]
        w.training.pin(j["example_id"], True)
        forever = w.one("SELECT COUNT(*) FROM artifact_leases WHERE"
                        " artifact_id=? AND expires_at_utc IS NULL AND"
                        " revoked_at_utc IS NULL", (payload,))[0]
        assert forever == 0, "pin made a pending machine payload permanent"


# =============================================================================
# Phase C — qualified datasets and truthful interpretation
# =============================================================================

@case("M14-AUDIT-14")
def f14_readiness_matches_export_membership():
    with MWorld() as w:
        w.families(10, asr=True)
        w.ready_cleanup("cleanup correct witness")
        w.ready_cleanup("cleanup incorrect witness", correct=False)
        blocked = w.ready_asr("blocked asr witness")
        w.review.record_label(blocked["example_id"],
                              edit_kind="changed_intent",
                              origin_stages=("user_intent",))
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("asr_supervised",
                                               "cleanup_supervised"))
        assert out is not None, err
        exs, _r, _p = export_records(w, "ds")
        counts = {k: sum(1 for e in exs if e["task_kind"] == k)
                  for k in ("asr_supervised", "cleanup_supervised")}
        te = w.training.readiness()["readiness_metrics"]["task_eligibility"]
        ready = {k: te[k]["count"] for k in counts}
        assert ready == counts, f"readiness {ready} vs export {counts}"


@case("M14-AUDIT-19")
def f19_later_abstention_returns_item_to_unresolved():
    with MWorld() as w:
        j, cid = taught(w)
        w.review.record_label(j["example_id"], edit_kind="recognition_error")
        w.review.record_label(j["example_id"], edit_kind="unknown",
                              abstained=True)
        row = next(r for r in w.review.queue()
                   if r.get("candidate_id") == cid)
        assert row["labeled"] is False, "stale resolution shown"


@case("M14-AUDIT-20")
def f20_punctuation_only_teach_is_a_review_record():
    with MWorld() as w:
        j = w.job("Wait here.")
        was_refused, out = refused(w.learning.teach_correction,
                                   j["job_id"], "Wait here!")
        assert not was_refused, out
        c = w.candidate(out["candidate_id"])
        axes = json.loads(c["classification"])
        assert c["alias"] is None and axes.get("edit_kind") == \
            "punctuation_or_structure", (c["alias"], axes.get("edit_kind"))
        # The true unchanged negative still refuses.
        assert refused(w.learning.teach_correction, j["job_id"],
                       "Wait here.")[0]


@case("M14-AUDIT-21")
def f21_directional_antonym_is_not_a_recognition_suggestion():
    with MWorld() as w:
        raw = "Please increase the output level today"
        j = w.job(raw)
        w.observation(j["job_id"], raw,
                      "Please decrease the output level today")
        w.learning.mine_observation_candidates()
        rows = w.rows("SELECT proposed_alias, classification_json FROM"
                      " learning_candidates")
        suggested = [r[0] for r in rows if r[0]]
        kinds = [json.loads(r[1]).get("edit_kind") for r in rows]
        assert not suggested and "recognition_error" not in kinds, (
            suggested, kinds)


@case("control:spelling-correction-still-suggested")
def c_real_spelling_correction_is_suggested():
    with MWorld() as w:
        j = w.job(TEACH_RAW)
        w.observation(j["job_id"], TEACH_RAW, TEACH_FIX)
        w.learning.mine_observation_candidates()
        rows = w.rows("SELECT proposed_alias, proposed_canonical FROM"
                      " learning_candidates WHERE status='pending'")
        assert rows == [("modul", "module")], rows


@case("M14-AUDIT-22")
def f22_equivalent_app_scope_composes_with_existing_entry():
    with MWorld() as w:
        eid = w.vocab.add_entry("module", [("moduul", True)],
                                scope_kind="app", scope_value=APP,
                                approved=True)
        _j, cid = taught(w, app="  COM.Synthetic.Editor ")
        was_refused, out = refused(w.learning.approve, cid)
        entries = w.entries()
        assert not was_refused, out
        assert len(entries) == 1 and ("modul", True) in entries[eid][6], \
            entries
        assert w.normalize("check the modul now", app=APP) == \
            "check the module now"


@case("M14-AUDIT-23")
def f23_used_term_canonical_edit_refreshes_the_profile_once():
    with MWorld(min_words=5) as w:
        eid = w.vocab.add_entry("Kubernetes", [("cube earnest", True)],
                                approved=True)
        w.vocab.record_hits([eid])
        for i in range(3):
            w.job(f"deploy to the Kubernetes cluster number {i} now",
                  audio=False, applied_rule_ids=[eid])
        w.profile.compute()
        w.vocab.update_entry(eid, canonical="Kubernetes Engine")
        first = w.profile.compute(only_if_changed=True)
        terms = json.dumps(w.profile.current()["measured"]
                           .get("technical_terms"))
        second = w.profile.compute(only_if_changed=True)
        assert not first.get("skipped") and "Kubernetes Engine" in terms, (
            first.get("skipped"), terms)
        assert second.get("skipped"), "unchanged tick wrote a snapshot"


@case("M14-AUDIT-25")
def f25_export_cli_accepts_an_explicit_db_path():
    w = MWorld(artifacts="v2-artifacts")
    try:
        w.families(10, asr=True)
        w.splits.assign()
        w.store.close()
        env = dict(os.environ, HOME=str(w.tmp / "home"))
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts/v2/export_dataset.py"),
             str(w.tmp / "cli-ds"), "--db", str(w.tmp / "v2.db"),
             "--views", "asr_supervised"], capture_output=True,
            text=True, env=env, cwd=str(w.tmp), timeout=120)
        assert p.returncode == 0 and "export complete" in p.stdout, (
            p.returncode, (p.stdout + p.stderr)[-400:])
        assert not (w.tmp / "home").exists(), "the default live path used"
    finally:
        w.closed = True
        w._tmp.cleanup()


@case("M14-AUDIT-26")
def f26_m14_evidence_carries_no_private_paths():
    import re
    pat = re.compile(r"/Users/|/private/var|/var/folders|scratchpad/"
                     r"|/home/[a-z]")
    hits = []
    for rel in ("docs/v2/acceptance/M14/results.json",
                "docs/v2/handoffs/M14.md"):
        p = ROOT / rel
        if p.is_file():
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if pat.search(line):
                    hits.append(f"{rel}:{n}")
    assert not hits, hits[:8]


@case("M14-AUDIT-30")
def d01_resolved_ambiguity_no_longer_blocks_asr():
    with MWorld() as w:
        j = w.ready_asr()
        w.review.record_label(j["example_id"], edit_kind="ambiguous",
                              abstained=True)
        w.review.record_label(j["example_id"], edit_kind="ambiguous")
        assert not w.review.verified_asr_eligible(
            j["example_id"])["eligible"]
        w.review.record_label(j["example_id"],
                              edit_kind="recognition_error",
                              origin_stages=("asr",))
        gate = w.review.verified_asr_eligible(j["example_id"])
        assert gate["eligible"], gate


@case("control:changed-intent-permanent")
def c_changed_intent_blocks_asr_forever():
    with MWorld() as w:
        j = w.ready_asr()
        w.review.record_label(j["example_id"], edit_kind="changed_intent")
        w.review.record_label(j["example_id"],
                              edit_kind="recognition_error")
        assert not w.review.verified_asr_eligible(
            j["example_id"])["eligible"]


@case("LOCAL-M14-03")
def l03_vanished_audio_file_fails_the_gate_not_the_export():
    with MWorld() as w:
        w.families(10, asr=True)
        gone = w.ready_asr("vanished audio witness")
        (w.store.artifacts_dir
         / w.artifact_row(gone["audio_aid"])[4]).unlink()
        gate = w.review.verified_asr_eligible(gone["example_id"])
        assert not gate["eligible"], gate
        te = w.training.readiness()["readiness_metrics"]["task_eligibility"]
        assert te["asr_supervised"]["count"] == 10, te["asr_supervised"]
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("asr_supervised",))
        assert out is not None, err
        exs, _r, _p = export_records(w, "ds")
        assert len(exs) == 10, len(exs)
        assert gone["example_id"] not in {e["example_id"] for e in exs}


@case("LOCAL-M14-04")
def l04_audio_artifact_id_never_names_a_path_outside_the_export():
    with MWorld() as w:
        w.families(10, asr=True)
        bad = w.ready_asr("escaping id witness")
        old = w.envelope(bad["example_id"])["artifact_ids"]["original_audio"]

        def clone(conn):
            cols = [r[1] for r in conn.execute("PRAGMA table_info(artifacts)")]
            pick = ", ".join("?" if c == "artifact_id" else c for c in cols)
            conn.execute(f"INSERT INTO artifacts ({', '.join(cols)})"
                         f" SELECT {pick} FROM artifacts WHERE artifact_id=?",
                         ("../../escape-id", old))
        w.store.submit(clone)
        w.rewrite_envelope(bad["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("original_audio", "../../escape-id"))
        w.splits.assign()
        out, err = export_or_refusal(w, "out/deep/ds", ("asr_supervised",))
        assert out is not None, err
        assert not (w.tmp / "out" / "escape-id.wav").exists()
        assert not (w.tmp / "escape-id.wav").exists()
        report = export_mod.validate_dataset(w.tmp / "out/deep/ds")
        assert report["valid"], report["issues"]
        assert report["counts"]["asr_supervised"] == 10, report["counts"]


@case("LOCAL-M14-05")
def l05_validator_reports_wrongly_typed_fields():
    with MWorld() as w:
        w.families(10, asr=True)
        w.splits.assign()
        w.export("ds", ("asr_supervised",))
        path = w.tmp / "ds" / "examples.jsonl"
        rows = read_jsonl(path)
        for field, bad in (("example_id", {"nested": 1}),
                           ("task_kind", ["asr_supervised"]),
                           ("family_id", ["f"])):
            tampered = [dict(rows[0], **{field: bad})] + rows[1:]
            path.write_text("".join(json.dumps(r) + "\n" for r in tampered))
            report = export_mod.validate_dataset(w.tmp / "ds")
            assert not report["valid"], field


@case("LOCAL-M14-06")
def l06_validator_never_reads_through_a_linked_directory():
    with MWorld() as w:
        w.families(10, asr=True)
        w.splits.assign()
        w.export("ds", ("asr_supervised",))
        outside = w.tmp / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel.wav"
        sentinel.write_bytes(b"outside bytes")
        (w.tmp / "ds" / "extra").symlink_to(outside)
        sums = w.tmp / "ds" / "SHA256SUMS.txt"
        sums.write_text(sums.read_text()
                        + f"{sha256_file(sentinel)}  extra/sentinel.wav\n")
        opened = []

        def hook(event, args):
            if event == "open" and args and "sentinel" in str(args[0]):
                opened.append(event)
        sys.addaudithook(hook)
        report = export_mod.validate_dataset(w.tmp / "ds")
        assert not report["valid"]
        assert not opened, "validator opened a file outside the dataset"


@case("LOCAL-M14-07")
def l07_corrupt_utc_offset_is_an_unknown_hour():
    from localflow.v2 import analytics as analytics_mod
    with MWorld(min_words=10) as w:
        a = analytics_mod.AnalyticsStore(w.store, emit=w._emit,
                                         now_fn=w.clock,
                                         reporting_timezone="UTC")
        good = w.job("an eligible dictation with a known local hour")
        bad = w.job("an eligible dictation with a corrupt offset")
        a.record_dictation_fact(job_id=good["job_id"],
                                activity_at_utc="2026-09-26T16:00:00.000Z",
                                utc_offset_minutes=330)
        a.record_dictation_fact(job_id=bad["job_id"],
                                activity_at_utc="2026-09-26T16:00:00.000Z",
                                utc_offset_minutes="bogus")
        measured = w.profile.compute()["measured"]
        assert measured["hours_unknown"] == 1, measured["hours_unknown"]
        assert measured["hour_histogram"][21] == 1, measured["hour_histogram"]


@case("M14-AUDIT-31")
def d02_task_rows_never_ride_into_a_holdout_export():
    with MWorld() as w:
        w.families(30, asr=True, frozen=3)
        t = w.transform_task("holdout source", ["H one.", "H two."])
        w.judge(t, t["candidates"][0]["candidate_id"],
                t["candidates"][1]["candidate_id"], "prefer_a")
        w.accept(t, t["candidates"][0]["candidate_id"])
        w.splits.assign()
        out, err = export_or_refusal(
            w, "ds", ("preference_pairs", "transform_supervised",
                      "asr_supervised"), partitions=("frozen_test",))
        assert out is not None, err
        exs, _r, prefs = export_records(w, "ds")
        task_rows = [e for e in exs if e.get("task_key")] + prefs
        assert not task_rows, f"{len(task_rows)} unpartitioned task rows"


@case("M14-AUDIT-32")
def d03_cleanup_without_exact_prompts_is_labeled_text_pair():
    with MWorld() as w:
        w.families(10, asr=True)
        full = w.ready_cleanup("cleanup with prompt")
        bare = w.ready_cleanup("cleanup without prompt", prompts=0)
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("cleanup_supervised",))
        assert out is not None, err
        exs, _r, _p = export_records(w, "ds")
        tiers = {e["example_id"]: e.get("qualification_tier") for e in exs}
        assert tiers.get(full["example_id"]) == "model_task_complete" and \
            tiers.get(bare["example_id"]) == "text_pair_only", tiers


@case("M14-AUDIT-33")
def d04_technical_terms_cite_eligible_speech_only():
    with MWorld(min_words=5) as w:
        used = w.vocab.add_entry("Terraform", [("terra form", True)],
                                 approved=True)
        elsewhere = w.vocab.add_entry("Kafka", [("kafkah", True)],
                                      approved=True)
        w.vocab.record_hits([used, elsewhere])
        for i in range(3):
            w.job(f"apply the Terraform plan for stage {i}",
                  audio=False, applied_rule_ids=[used])
        snap = w.profile.compute()
        terms = json.dumps(snap["measured"].get("technical_terms"))
        assert "Terraform" in terms and "Kafka" not in terms, terms


@case("M14-AUDIT-34")
def d05_case_variant_of_rejected_pair_stays_suppressed():
    with MWorld() as w:
        _j, cid = taught(w)
        w.learning.reject(cid)
        j2 = w.job("please check the Modul today")
        w.observation(j2["job_id"], "please check the Modul today",
                      "please check the module today")
        w.learning.mine_observation_candidates()
        pending = w.rows("SELECT proposed_alias FROM learning_candidates"
                         " WHERE status='pending'")
        assert not pending, pending


@case("M14-AUDIT-35")
def d06_approval_without_counterexamples_is_recorded_untested():
    with MWorld() as w:
        _j, cid = taught(w)
        w.learning.approve(cid)
        raw = w.candidate(cid)["counterexamples"]
        got = json.loads(raw) if raw else None
        assert isinstance(got, dict) and got.get("status") == "untested" \
            and got.get("tested") == 0, got


@case("M14-AUDIT-36")
def d07_accept_then_reject_is_not_a_supervised_target():
    with MWorld() as w:
        w.families(10, asr=True)
        t = w.transform_task("single candidate source", ["Single out."])
        cand = t["candidates"][0]["candidate_id"]
        w.accept(t, cand, "accept")
        w.accept(t, cand, "reject")
        w.splits.assign()
        out, err = export_or_refusal(w, "ds", ("transform_supervised",))
        assert out is not None, err
        exs, _r, _p = export_records(w, "ds")
        assert not [e for e in exs
                    if e["task_kind"] == "transform_supervised"], \
            "a rejected target exported as supervised"


# =============================================================================
# Phase D — independent oracles (test gaps)
# =============================================================================

@case("M14-AUDIT-28")
def f28_benchmark_rejects_a_noop_component():
    sys.path.insert(0, str(ROOT / "scripts/v2"))
    import importlib
    bench = importlib.import_module("benchmark_m14")
    assert hasattr(bench, "run_validity"), \
        "no independent validity gate in the benchmark"
    good = bench.run_validity(scale="small")
    bad = bench.run_validity(scale="small", noop="mining")
    assert good["valid"] and not bad["valid"], (good.get("reasons"),
                                                bad.get("reasons"))


@case("M14-AUDIT-29")
def f29_caller_inventory_covers_every_tracked_caller():
    inv_path = ROOT / "docs/v2/acceptance/M14/remediation/" \
        "caller_inventory.json"
    assert inv_path.is_file(), "no caller inventory"
    inv = json.loads(inv_path.read_text())
    listed = {c["file"] for c in inv.get("callers", [])}
    pattern = ("LearningService|ReviewService|SamplingService|SplitService"
               "|ProfileService|DatasetExporter|verified_asr_eligible_in"
               "|stage_texts_for|teach_correction|undo_approval")
    p = subprocess.run(["git", "-C", str(ROOT), "grep", "-l", "-E",
                        pattern, "--", "localflow", "scripts"],
                       capture_output=True, text=True)
    missing = sorted(set(p.stdout.split()) - listed)
    assert not missing, missing


# =============================================================================
# Hub / coordinator cases (the real app wiring, AppKit headless)
# =============================================================================

def _hub_env():
    for p in (HERE.parents[1] / "ui", HERE.parents[1] / "lifecycle"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from AppKit import NSApplication
    NSApplication.sharedApplication().setActivationPolicy_(1)
    from test_lifecycle import Harness
    from m09_world import MainQueue
    return Harness, MainQueue


def _make_hub(h):
    from localflow.v2.history_queries import HistoryQueryService
    from localflow.v2.training_data import TrainingDataService
    from localflow.v2.ui import HubController, ReplayService
    d = h.d
    return HubController.alloc().initWithSpec_({
        "store": d.store,
        "history_service": HistoryQueryService(d.store),
        "training_service": TrainingDataService(d.store),
        "diagnostics_provider": d._hub_diagnostics_spec,
        "coordinator": d, "replay": ReplayService(
            sound_factory=lambda b: None),
        "capabilities": d._capability_manifest,
        "styles_service": d._styles, "snippets_service": d._snip_store,
        "transforms_service": d._tf_store,
        "insights_service": d._insights,
        "learning_service": d._learning, "review_service": d._review,
        "sampling_service": d._sampling, "splits_service": d._splits,
        "profile_service": d._profile, "export_service": d._exporter,
        "transforms_store": d._tf_store})


def _review_tab(hub, mq):
    from localflow.v2.ui.state import VIEWS
    hub._select_view_index(VIEWS.index("models"))
    hub.state.select_models_subview("training")
    assert mq.drain(hub.state, 60)
    hub.state.select_training_tab("review")
    assert mq.drain(hub.state, 60)


@case("M14-AUDIT-16")
def f16_pair_judgment_binds_to_the_rendered_pair():
    Harness, MainQueue = _hub_env()
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = _make_hub(h)
            assert mq.drain(hub.state, 60)
            t = W.transform_task(h.d.store, f"shared source {A_CANARY}",
                                 [f"Output alpha {A_CANARY}",
                                  f"Output bravo {B_CANARY}"])
            a, b = (c["candidate_id"] for c in t["candidates"])
            _review_tab(hub, mq)
            shown = hub.review_text.string()
            visible = all(s in shown for s in (
                t["source"], t["candidates"][0]["text"],
                t["candidates"][1]["text"]))
            # A new candidate arrives AFTER render, sorting first.
            W.transform_task(h.d.store, f"shared source {A_CANARY}",
                             ["Late candidate"], display=[-1])
            if hasattr(hub, "review_pair_task"):
                hub.review_pair_task.setStringValue_(t["task_key"])
            hub.reviewPairB_(None)
            assert mq.drain(hub.state, 60)
            rows = h.d.store.submit(lambda c: c.execute(
                "SELECT candidate_id, candidate_b_id, judgment FROM"
                " preference_observations WHERE task_key=? ORDER BY"
                " rowid", (t["task_key"],)).fetchall())
            assert visible, "the compared texts were never shown"
            assert rows in ([], [(a, b, "prefer_b")]), rows
    finally:
        h.close()


@case("M14-AUDIT-18")
def f18_job_only_teach_is_actionable_in_review():
    Harness, MainQueue = _hub_env()
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = _make_hub(h)
            assert mq.drain(hub.state, 60)
            s = h.d.store
            job, _fam = s.create_job()
            s.write_text_artifact(job_id=job, stage="asr",
                                  role="raw_transcript", text=TEACH_RAW,
                                  retention_class="history")
            s.write_text_artifact(job_id=job, stage="cleanup",
                                  role="applied_output", text=TEACH_RAW,
                                  retention_class="history")
            s.set_job_target(job, "Synthetic Editor", APP)
            cid = h.d._learning.teach_correction(job, TEACH_FIX)[
                "candidate_id"]
            _review_tab(hub, mq)
            popup = getattr(hub, "review_candidate_popup", None)
            if popup is not None:
                menu = popup.menu()
                idx = next((i for i in range(menu.numberOfItems())
                            if menu.itemAtIndex_(i).representedObject()
                            == cid), -1)
                assert idx >= 0, "job-only candidate not offered"
                popup.selectItemAtIndex_(idx)
            hub.reviewApprove_(None)
            assert mq.drain(hub.state, 60)
            status = s.submit(lambda c: c.execute(
                "SELECT status, example_id FROM learning_candidates WHERE"
                " candidate_id=?", (cid,)).fetchone())
            examples = s.submit(lambda c: c.execute(
                "SELECT COUNT(*) FROM training_examples").fetchone()[0])
            assert status == ("approved", None) and examples == 0, (
                status, examples)
    finally:
        h.close()


@case("M14-AUDIT-11")
def f11_history_teach_passes_the_rendered_final_identity():
    Harness, MainQueue = _hub_env()
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = _make_hub(h)
            assert mq.drain(hub.state, 60)
            learning = h.d._learning
            seen = {}
            orig = learning.teach_correction

            def spy(job_id, corrected, **kw):
                seen.update(kw)
                return orig(job_id, corrected, **kw)
            learning.teach_correction = spy
            s = h.d.store
            job, _fam = s.create_job()
            s.write_text_artifact(job_id=job, stage="asr",
                                  role="raw_transcript", text=TEACH_RAW,
                                  retention_class="history")
            f1 = s.write_text_artifact(job_id=job, stage="cleanup",
                                       role="applied_output",
                                       text=TEACH_RAW,
                                       retention_class="history")
            s.update_job_state(job, "confirmed")
            from localflow.v2.ui.state import VIEWS
            hub._select_view_index(VIEWS.index("history"))
            assert mq.drain(hub.state, 60)
            hub.state.select_history_row("job", job)
            assert mq.drain(hub.state, 60)
            hub.teach_field.setStringValue_(TEACH_FIX)
            hub.historyTeach_(None)
            assert seen.get("expected_final_artifact_id") == f1 and \
                seen.get("expected_final_sha256") == \
                ids.sha256_text(TEACH_RAW), seen
    finally:
        h.close()


@case("M14-AUDIT-27")
def f27_profile_never_reaches_the_real_coordinator_pipeline():
    Harness, _MainQueue = _hub_env()
    from test_lifecycle import FakeSupervisor

    class Recording(FakeSupervisor):
        def __init__(self):
            super().__init__()
            self.clean_inputs = []

        def clean(self, *, job_id, attempt, raw_text, **ctx):
            self.clean_inputs.append(json.dumps(
                {"raw_text": raw_text, **ctx}, sort_keys=True,
                default=str))
            return super().clean(job_id=job_id, attempt=attempt,
                                 raw_text=raw_text, **ctx)
    sup = Recording()
    h = Harness(durations=[1.0, 1.0], cfg={"profile_min_words": 10},
                supervisor=sup)
    try:
        def dictate():
            h.press()
            h.release()
            h.run_coordinator()
        dictate()
        # A current profile snapshot carrying a distinctive phrase.
        s = h.d.store
        for i in range(12):
            job, fam = s.create_job()
            aid = s.write_text_artifact(
                job_id=job, stage="asr", role="raw_transcript",
                text=f"{PRIVATE_CANARY.lower()} zephyr words {i}",
                retention_class="training")
            ex = s.upsert_example(job_id=job, family_id=fam)
            s.append_revision(ex, {
                "example_id": ex, "job_id": job, "family_id": fam,
                "origin": "live_capture", "artifact_ids": {
                    "source_text": aid}, "outcome": {},
                "annotations": [], "missing_reasons": {}})
        snap = h.d._profile.compute()
        assert snap["measured"]["frequent_phrases"], "fixture: no phrase"
        dictate()
        assert len(sup.clean_inputs) == 2, len(sup.clean_inputs)
        first, second = (json.loads(x) for x in sup.clean_inputs)
        assert PRIVATE_CANARY.lower() not in json.dumps(second)
        # Every permitted-context field the coordinator hands cleanup is
        # identical with and without a current profile (the raw text is
        # per-job and differs by construction).
        first.pop("raw_text")
        second.pop("raw_text")
        assert first and first == second, (first, second)
    finally:
        h.close()


# =============================================================================
# preservation controls (strengths the audit verified)
# =============================================================================

@case("control:pending-never-changes-output")
def c_pending_candidates_never_reach_normalization():
    with MWorld() as w:
        _j, cid = taught(w)
        assert w.normalize(TEACH_RAW, app=APP) == TEACH_RAW
        w.learning.approve(cid)
        assert w.normalize(TEACH_RAW, app=APP) == TEACH_FIX


@case("control:prefer-b-maps-to-b")
def c_prefer_b_exports_b():
    with MWorld() as w:
        w.families(10, asr=True)
        t = w.transform_task("pair control source",
                             [f"left {A_CANARY}", f"right {B_CANARY}"])
        w.judge(t, t["candidates"][0]["candidate_id"],
                t["candidates"][1]["candidate_id"], "prefer_b")
        w.splits.assign()
        w.export("ds", ("preference_pairs",))
        _e, _r, prefs = export_records(w, "ds")
        chosen = [c["output_text"] for p in prefs for c in p["candidates"]
                  if c["slot"] == p["chosen"]]
        assert chosen and B_CANARY in chosen[0], chosen


@case("control:label-refuses-restricted")
def c_label_refuses_restricted_states():
    with MWorld() as w:
        for st in ("excluded", "expired", "quarantined_sensitive"):
            j = w.job(f"restricted {st} words")
            w.set_state(j["example_id"], st)
            assert refused(w.review.record_label, j["example_id"],
                           edit_kind="recognition_error")[0], st
        assert w.one("SELECT COUNT(*) FROM correction_labels")[0] == 0


@case("control:assign-preserves-exposure")
def c_next_assignment_keeps_exposed_family_out_of_frozen():
    with MWorld() as w:
        w.families(30, frozen=3)
        v1 = w.splits.assign()["assignment_version"]
        frozen = w.rows("SELECT DISTINCT family_id FROM training_memberships"
                        " WHERE assignment_version=? AND"
                        " partition='frozen_test'", (v1,))[0][0]
        w.splits.mark_exposed([frozen], "inspected_during_tuning")
        v3 = w.splits.assign()["assignment_version"]
        parts = w.rows("SELECT DISTINCT partition, exposed FROM"
                       " training_memberships WHERE assignment_version=?"
                       " AND family_id=?", (v3, frozen))
        assert parts == [("train", 1)], parts


@case("control:idle-unchanged-writes-nothing")
def c_unchanged_idle_pass_adds_no_snapshot():
    with MWorld(min_words=5) as w:
        for i in range(3):
            w.job(f"idle profile words number {i}", audio=False)
        w.profile.compute()
        n = w.one("SELECT COUNT(*) FROM profile_snapshots")[0]
        out = w.profile.compute(only_if_changed=True)
        assert out.get("skipped") and \
            w.one("SELECT COUNT(*) FROM profile_snapshots")[0] == n


@case("control:delete-reaches-job-keyed-candidates")
def c_delete_reaches_job_only_candidates():
    with MWorld() as w:
        j, cid = taught(w, example=False)
        w.store.delete_everywhere("job", j["job_id"])
        c = w.candidate(cid)
        assert c["status"] == "stale" and w.payload(cid) is None, c


# =============================================================================
# runner
# =============================================================================

def redact(text):
    """Evidence carries repository-relative names only: the checkout,
    temp roots, home and any scratch path become placeholders."""
    import re
    import tempfile
    if not text:
        return text
    tmp = tempfile.gettempdir()
    for real, mark in ((str(ROOT), "<repo>"),
                       ("/private" + tmp, "<tmp>"), (tmp, "<tmp>"),
                       (str(pathlib.Path.home()), "<home>")):
        text = text.replace(real, mark)
    text = re.sub(r"[^\s'\"()]*scratchpad/[^\s'\"()]*", "<scratch>", text)
    return re.sub(r"/private/var/folders/[^\s'\"()]*|/var/folders/"
                  r"[^\s'\"()]*", "<tmp>", text)


def main(argv):
    out_path = None
    if "--json" in argv:
        i = argv.index("--json")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    names = set(argv)
    results = []
    for fn in CASES:
        if names and fn.__name__ not in names:
            continue
        t0 = time.monotonic()
        try:
            fn()
            status, detail = "PASS", None
        except AssertionError as e:
            status, detail = "FAIL", (str(e) or "assertion")[:600]
        except Exception as e:  # noqa: BLE001
            status = "ERROR"
            tb = traceback.format_exc()
            tb = tb.replace(str(ROOT), "<repo>")
            detail = (f"{type(e).__name__}: {e}"[:300] + " | "
                      + tb[-1200:])
        detail = redact(detail)
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "kind": fn.kind, "status": status,
                        "detail": detail,
                        "seconds": round(time.monotonic() - t0, 2)})
        print(f"{status:5}  {fn.__name__}  [{fn.finding}]"
              + (f"  — {detail.splitlines()[0][:160]}" if detail else ""))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("m14 remediation:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/personalization/test_m14_remediation.py",
            "code": W.code_stamp(
                "tests/v2/personalization/test_m14_remediation.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
