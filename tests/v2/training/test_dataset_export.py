"""EV-21 split and export qualification (V2 M14, S29.13/E19.5): the
portable export round trip (build → move to an empty directory →
validate offline with the store closed), determinism (identical
revisions ⇒ identical content fingerprint), and the negative battery —
wrong hash, missing original, changed source prompt, different-task
preference, partial graft mislabeled gold, split leakage, revoked
permission mid-export, cancellation, unsafe paths and unsupported
schema.

The round-trip pack meets E19.5's minimum: ≥10 audio/reference
examples, ≥10 reviewed cleanup examples, ≥5 explicit preference pairs,
including short-command, numeric, mixed-edit, EN/ES, rejected-proposal
and audio-deleted text-only cases.

Run: .venv/bin/python tests/v2/training/test_dataset_export.py
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from evidence_pack import build_pack  # noqa: E402
from localflow.v2 import store as store_mod, training_data  # noqa: E402
from localflow.v2.curation import splits as splits_mod  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402
from localflow.v2.curation import review as review_mod  # noqa: E402


def make_store(tmp):
    return store_mod.Store(tmp / "v2.db",
                           backup_dir=tmp / "backups")


def prepare(s):
    """Pack + splits so every view has real material, plus preference
    pairs through the M11-compatible tables."""
    s.append_consent("enabled", note="m14-fixture")
    pack = build_pack(s)
    sp = splits_mod.SplitService(s, emit=lambda *a, **k: None)
    # 100 examples over ~95 families exceeds the floor.
    sp.assign()
    # Preference pairs: two same-task candidates + comparable
    # judgments (built through the M11-compatible rows).
    now = "2026-09-22T09:00:00.000Z"

    def pair_op(conn):
        # The frozen definition revision every M11 candidate names —
        # the transform view exports it so the task reconstructs.
        conn.execute(
            "INSERT OR IGNORE INTO transform_revisions(transform_id,"
            " revision, definition_json, created_at_utc)"
            " VALUES('builtin:polish', 1, ?, ?)",
            (json.dumps({"transform_id": "builtin:polish",
                         "revision": 1,
                         "instructions": "Polish the synthetic draft.",
                         "examples": []}), now))
        for p in range(6):
            task = f"task-synth-{p}"
            for slot in range(2):
                aid_src = f"art-prefsrc-{p}-{slot}"
                aid_out = f"art-prefout-{p}-{slot}"
                from localflow.v2.store import \
                    insert_text_artifact_row
                insert_text_artifact_row(
                    conn, artifact_id=aid_src, job_id=f"job-pref-{p}",
                    stage="transform", role="transform_prompt",
                    text=f"polish this draft {p}", retention_class=
                    "training", created_at_utc=now)
                insert_text_artifact_row(
                    conn, artifact_id=aid_out, job_id=f"job-pref-{p}",
                    stage="transform", role="transform_output",
                    text=f"Polished draft {p}, candidate {slot}"
                         f" output.", retention_class="training",
                    created_at_utc=now)
                conn.execute(
                    "INSERT INTO transform_candidates(candidate_id,"
                    " task_key, task_kind, transform_id,"
                    " transform_revision, prompt_revision,"
                    " source_sha256, instructions_sha256,"
                    " examples_revision, source_artifact_id,"
                    " output_artifact_id, path, display_order,"
                    " model_id, created_at_utc) VALUES"
                    " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"cand-pref-{p}-{slot}", task, "transform_note",
                     "builtin:polish", 1, "r1", f"sha-src-{p}",
                     f"sha-ins-{p}", None, aid_src, aid_out,
                     "applied", slot, "qwen-synth", now))
            judgment = ("prefer_a" if p % 2 == 0 else "tie")
            conn.execute(
                "INSERT INTO preference_observations(observation_id,"
                " task_key, candidate_id, candidate_b_id, judgment,"
                " provenance, reason_code, source_event_id,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (f"pref-obs-{p}", task, f"cand-pref-{p}-0",
                 f"cand-pref-{p}-1", judgment, "m14_pair_review",
                 None, None, now))
    s.submit(pair_op)
    # A transform-supervised row: an accept judgment over one task.
    s.submit(lambda conn: conn.execute(
        "INSERT INTO preference_observations(observation_id, task_key,"
        " candidate_id, candidate_b_id, judgment, provenance,"
        " reason_code, source_event_id, created_at_utc)"
        " VALUES('pref-accept-1', 'task-synth-0', 'cand-pref-0-0',"
        " NULL, 'accept', 'user_action', NULL, NULL, ?)", (now,)))
    # Graft one mixed-edit example so the weak view has material.
    rs = review_mod.ReviewService(s, emit=lambda *a, **k: None)
    mixed = pack["by_category"]["mixed_changed_intent"][0]
    from localflow.v2.curation import classify
    regions = classify.changed_regions(
        "send the cloud report on friday",
        "send the Claude report on Monday")
    rs.record_label(
        mixed, edit_kind="changed_intent",
        origin_stages=("asr", "user_intent"),
        evidence_status="explicit_intent_review",
        confirmed_spans=[regions[0]])  # the reviewed cloud→Claude span
    return pack, sp


def test_round_trip_and_determinism():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack, sp = prepare(s)
            dest1 = tmp / "dataset-a"
            dest2 = tmp / "dataset-b"
            views = ("asr_supervised", "asr_span_graft_weak",
                     "cleanup_supervised", "transform_supervised",
                     "preference_pairs")
            ex = export_mod.DatasetExporter(s, emit=lambda *a, **k: None)
            out1 = ex.build(dest1, task_views=views)
            assert out1["state"] == "complete"
            out2 = ex.build(dest2, task_views=views)
            assert out1["fingerprint"] == out2["fingerprint"]
            counts = json.loads(json.dumps(out1["counts"]))
            assert counts["asr_supervised"] >= 20
            assert counts["cleanup_supervised"] >= 20
            assert counts["preference_pairs"] >= 5
            assert counts["asr_span_graft_weak"] >= 1
            assert counts["transform_supervised"] >= 1
            # Validate offline: store CLOSED, foreign cwd, no network.
            s.close()
            moved = tmp / "moved"
            os.rename(dest1, moved)
            proc = subprocess.run(
                [str(pathlib.Path(__file__).resolve().parents[3]
                     / ".venv/bin/python"),
                 str(pathlib.Path(__file__).resolve().parents[3]
                     / "scripts/v2/validate_dataset.py"), str(moved)],
                capture_output=True, text=True, timeout=120,
                cwd=tempfile.mkdtemp())
            assert "valid: True" in proc.stdout, proc.stdout + proc.stderr
            print("ok  round trip: deterministic fingerprint; offline"
                  " validation from an empty cwd with the store closed")
        finally:
            try:
                s.close()
            except Exception:
                pass


def test_negative_battery():
    now = "2026-09-22T09:00:00.000Z"
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack, sp = prepare(s)
            ex = export_mod.DatasetExporter(s, emit=lambda *a, **k: None)
            views = ("asr_supervised", "asr_span_graft_weak",
                     "cleanup_supervised", "preference_pairs")
            dest = tmp / "ds"
            ex.build(dest, task_views=views)
            # (a) tamper → validator catches the wrong hash.
            target = dest / "examples.jsonl"
            lines = target.read_text().splitlines()
            first = json.loads(lines[0])
            first["tampered"] = True
            lines[0] = json.dumps(first, sort_keys=True)
            target.write_text("\n".join(lines) + "\n")
            report = export_mod.validate_dataset(dest)
            assert not report["valid"]
            assert any("hash mismatch" in i or "fingerprint" in i
                       for i in report["issues"]), report["issues"]
            # (b) unsupported schema version refused by the validator.
            manifest_path = dest / "dataset_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["export_schema_version"] = 99
            manifest_path.write_text(json.dumps(manifest))
            report = export_mod.validate_dataset(dest)
            assert any("unsupported" in i for i in report["issues"])
            # (c) unsafe path in the sums file refused.
            dest2 = tmp / "ds2"
            ex.build(dest2, task_views=views)
            sums = dest2 / "SHA256SUMS.txt"
            sums.write_text(
                "0" * 64 + "  ../outside/secret.txt\n"
                + sums.read_text())
            report = export_mod.validate_dataset(dest2)
            assert any("unsafe path" in i for i in report["issues"])
            # (d) missing original audio: purge one → excluded rows
            # carry the content-free reason, the export still completes
            # without the broken example.
            asr_ex = pack["by_category"]["reviewed_success"][0]
            job = s.submit(lambda c: c.execute(
                "SELECT job_id FROM training_examples WHERE"
                " example_id=?", (asr_ex,)).fetchone()[0])
            s.delete_everywhere("example", asr_ex,
                                reason="test_removal")
            dest3 = tmp / "ds3"
            out3 = ex.build(dest3, task_views=views)
            assert out3["state"] == "complete"
            assert out3["counts"]["asr_supervised"] \
                >= 20 - 1
            manifest3 = json.loads(
                (dest3 / "dataset_manifest.json").read_text())
            reasons = [e["reason"] for e in manifest3["excluded"]]
            assert any("revisions_absent" in r or "state_deleted" in r
                       for r in reasons), reasons
            # (e) revoked mid-export: consent flips to paused INSIDE
            # the build's snapshot op (a concurrent user action); the
            # finalize recheck sees it and aborts with nothing left.
            dest4 = tmp / "ds4"
            real_select = ex._select

            def select_then_revoke(conn, *a, **k):
                out = real_select(conn, *a, **k)
                conn.execute(
                    "INSERT INTO consent_revisions(consent_revision_id,"
                    " state, policy_json, created_at_utc, note)"
                    " VALUES('consent-revoked-mid', 'paused', '{}', ?,"
                    " 'mid-export revocation')", (now,))
                return out
            ex._select = select_then_revoke
            try:
                try:
                    ex.build(dest4, task_views=views)
                    raise AssertionError("revoked export completed")
                except export_mod.ExportError as e:
                    assert "consent" in str(e) or "revoked" in str(e), e
                assert not dest4.exists()
            finally:
                ex._select = real_select
            # (f) different-task preference: a rogue cross-task pair is
            # refused at export (the store refuses at write; here the
            # re-verification catches a planted mismatch).
            s.submit(lambda c: c.execute(
                "UPDATE transform_candidates SET source_sha256="
                "'sha-different' WHERE candidate_id='cand-pref-0-1'"))
            try:
                ex.build(tmp / "ds5", task_views=views)
                raise AssertionError("cross-input pair exported")
            except export_mod.ExportError as e:
                assert "preference pair refuses" in str(e)
            # (g) split leakage: a rogue second membership → refuse.
            version = sp.current_version()
            fam = s.submit(lambda c: c.execute(
                "SELECT family_id FROM training_memberships WHERE"
                " assignment_version=? LIMIT 1", (version,)).fetchone())[0]
            part = s.submit(lambda c: c.execute(
                "SELECT DISTINCT partition FROM training_memberships"
                " WHERE family_id=? AND assignment_version=?",
                (fam, version)).fetchall())
            if len(part) == 1:
                other = "train" if part[0][0] != "train" \
                    else "validation"
                s.submit(lambda c: c.execute(
                    "INSERT INTO training_memberships(example_id,"
                    " family_id, assignment_version, partition,"
                    " exposed, created_at_utc) VALUES('ex-rogue2', ?,"
                    " ?, ?, 0, '2026-09-23T00:00:00.000Z')",
                    (fam, version, other)))
                try:
                    ex.build(tmp / "ds6", task_views=views)
                    raise AssertionError("leaky export completed")
                except export_mod.ExportError as e:
                    assert "split leakage" in str(e)
                s.submit(lambda c: c.execute(
                    "DELETE FROM training_memberships WHERE"
                    " example_id='ex-rogue2'"))
            # (h) partial graft mislabeled gold: a graft payload whose
            # coverage_kind is tampered to full refuses.
            s.submit(lambda c: c.execute(
                "UPDATE artifacts SET content_text=? WHERE"
                " role='span_graft' AND content_text LIKE"
                " '%partial%'",
                (json.dumps({"grafted_text": "x", "coverage": [],
                             "coverage_kind": "full"}),)))
            try:
                ex.build(tmp / "ds7", task_views=("asr_supervised",
                                                  "asr_span_graft_weak"))
                raise AssertionError("graft exported as gold")
            except export_mod.ExportError as e:
                assert "partial graft" in str(e).lower()
            print("ok  negatives: tamper, unsafe path, schema,"
                  " missing original, revoked mid-export, cross-task"
                  " pair, split leakage, graft-as-gold — all refused")
        finally:
            try:
                s.close()
            except Exception:
                pass


def test_audio_deleted_text_only_case():
    """E19.5's audio-deleted text-only case: purging the audio drops
    the example from ASR views while cleanup views keep it."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack, sp = prepare(s)
            ex = export_mod.DatasetExporter(s, emit=lambda *a, **k: None)
            before = ex.build(tmp / "a", task_views=(
                "asr_supervised", "cleanup_supervised"))
            n_asr = before["counts"]["asr_supervised"]
            # Purge one example's audio payload (retention pass
            # semantics, applied directly).
            target = pack["by_category"]["reviewed_success"][5]
            audio = s.submit(lambda c: c.execute(
                "SELECT artifact_id FROM artifacts WHERE"
                " content_path LIKE 'art-aud%' AND job_id=("
                "SELECT job_id FROM training_examples WHERE"
                " example_id=?)", (target,)).fetchone())
            s.submit(lambda c: c.execute(
                "UPDATE artifacts SET purged=1, content_path=NULL,"
                " content_text=NULL WHERE artifact_id=?",
                (audio[0],)))
            after = ex.build(tmp / "b", task_views=(
                "asr_supervised", "cleanup_supervised"))
            assert after["counts"]["asr_supervised"] == n_asr - 1
            assert after["counts"]["cleanup_supervised"] == \
                before["counts"]["cleanup_supervised"]
            print("ok  audio-deleted text-only case: ASR eligibility"
                  " downgrades, cleanup keeps the text-only example")
        finally:
            s.close()


def _read_jsonl(path):
    return [json.loads(line) for line in
            path.read_text().splitlines() if line.strip()]


def test_export_safety_and_semantics():
    """The destination is never a user folder; a prefer_b judgment
    exports B as chosen and the latest judgment supersedes; the sums
    file must cover every file; cleanup rows carry the exact stage
    input and say honestly when no model prompt was recorded; exposed
    development families export (flagged) while an exposed family
    left in frozen_test, a stale family assignment and a damaged audio
    payload all refuse."""
    from localflow.v2.transforms_store import TransformStore
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack, sp = prepare(s)
            ex = export_mod.DatasetExporter(s, emit=lambda *a, **k: None)
            views = ("asr_supervised", "cleanup_supervised",
                     "transform_supervised", "preference_pairs")
            # (1) a folder of the user's own files is never replaced.
            own = tmp / "my-folder"
            own.mkdir()
            (own / "keep.txt").write_text("the user's file")
            try:
                ex.build(own, task_views=views)
                raise AssertionError("export replaced a user folder")
            except export_mod.ExportError as e:
                assert "destination exists" in str(e)
            assert (own / "keep.txt").read_text() == "the user's file"
            # A previous export at the same path IS replaceable.
            dest = tmp / "ds"
            ex.build(dest, task_views=views)
            ex.build(dest, task_views=views)
            # (2) prefer_b through the review layer: B is chosen; the
            # latest judgment supersedes the fixture's earlier tie.
            rs = review_mod.ReviewService(s, emit=lambda *a, **k: None)
            rs.record_pair_judgment(TransformStore(s), "task-synth-1",
                                    "cand-pref-1-0", "cand-pref-1-1",
                                    "prefer_b")
            dest_p = tmp / "ds-pref"
            ex.build(dest_p, task_views=("preference_pairs",))
            prefs = {p["task_key"]: p
                     for p in _read_jsonl(dest_p / "preferences.jsonl")}
            row = prefs["task-synth-1"]
            assert row["judgment"] == "prefer_b" and \
                row["chosen"] == "b", row
            chosen = next(c for c in row["candidates"]
                          if c["slot"] == row["chosen"])
            assert chosen["output_text"] == \
                "Polished draft 1, candidate 1 output.", chosen
            assert all("display_order" in c for c in row["candidates"])
            # (3) the sums file must be complete.
            (dest_p / "artifacts" / "planted.wav").write_bytes(b"x")
            report = export_mod.validate_dataset(dest_p)
            assert any("not in SHA256SUMS" in i
                       for i in report["issues"]), report
            (dest_p / "artifacts" / "planted.wav").unlink()
            sums = dest_p / "SHA256SUMS.txt"
            sums.write_text("".join(
                line + "\n" for line in sums.read_text().splitlines()
                if not line.endswith("dataset_manifest.json")))
            report = export_mod.validate_dataset(dest_p)
            assert any("not in SHA256SUMS: dataset_manifest.json" in i
                       or "does not cover dataset_manifest.json" in i
                       for i in report["issues"]), report
            # (4) cleanup rows: exact stage input + honest prompt gap;
            # transform rows carry their frozen definition.
            rows = _read_jsonl(dest / "examples.jsonl")
            cleanup = [r for r in rows
                       if r["task_kind"] == "cleanup_supervised"]
            assert cleanup and all(
                r["input_text"] and r["model_inputs"] == [] and
                r["model_inputs_missing_reason"] ==
                "no_model_pass_recorded" for r in cleanup), cleanup[0]
            tf_rows = [r for r in rows
                       if r["task_kind"] == "transform_supervised"]
            assert tf_rows and tf_rows[0]["transform_definition"][
                "instructions"] == "Polish the synthetic draft."
            manifest = json.loads(
                (dest / "dataset_manifest.json").read_text())
            assert manifest["deletion_epoch"] == 0
            assert all("deletion_epoch" not in r for r in rows)
            # (5) an exposed development family exports, flagged.
            frozen = [f["family_id"] for f in sp.family_report(
                limit=1000) if f["partition"] == "frozen_test"]
            assert len(frozen) >= 2, frozen
            sp.mark_exposed([frozen[0]], "inspected_during_tuning")
            out = ex.build(tmp / "ds-exposed", task_views=views)
            manifest = json.loads(
                (tmp / "ds-exposed" / "dataset_manifest.json")
                .read_text())
            assert not [e for e in manifest["excluded"]
                        if e["reason"] == "family_exposed"]
            assert out["state"] == "complete"
            # ...but an exposed family still in frozen_test refuses.
            v = sp.current_version()
            s.submit(lambda c: c.execute(
                "UPDATE training_memberships SET exposed=1 WHERE"
                " assignment_version=? AND family_id=?",
                (v, frozen[1])))
            try:
                ex.build(tmp / "ds-leak", task_views=views)
                raise AssertionError("exposed frozen family exported")
            except export_mod.ExportError as e:
                assert "exposed family" in str(e)
            s.submit(lambda c: c.execute(
                "UPDATE training_memberships SET exposed=0 WHERE"
                " assignment_version=? AND family_id=?",
                (v, frozen[1])))
            # (6) stale family assignment refuses.
            victim = pack["by_category"]["reviewed_success"][1]
            s.submit(lambda c: c.execute(
                "UPDATE training_memberships SET family_id='fam-stale'"
                " WHERE assignment_version=? AND example_id=?",
                (v, victim)))
            try:
                ex.build(tmp / "ds-stale", task_views=views)
                raise AssertionError("stale family assignment exported")
            except export_mod.ExportError as e:
                assert "stale family assignment" in str(e)
            s.submit(lambda c: c.execute(
                "UPDATE training_memberships SET family_id=(SELECT"
                " family_id FROM training_examples WHERE example_id=?)"
                " WHERE assignment_version=? AND example_id=?",
                (victim, v, victim)))
            # (7) a damaged audio payload refuses (hash ≠ capture).
            path = s.submit(lambda c: c.execute(
                "SELECT content_path FROM artifacts WHERE"
                " role='original_audio' AND purged=0 LIMIT 1"
            ).fetchone())[0]
            with open(s.artifacts_dir / path, "r+b") as f:
                f.seek(-4, 2)
                f.write(b"\x01\x02\x03\x04")
            try:
                ex.build(tmp / "ds-damaged",
                         task_views=("asr_supervised",))
                raise AssertionError("damaged audio exported")
            except export_mod.ExportError as e:
                assert "hash mismatch" in str(e)
            assert not (tmp / "ds-damaged").exists()
            print("ok  export safety: user folders never replaced;"
                  " prefer_b exports B and the latest judgment wins;"
                  " sums completeness; exact cleanup input; exposed"
                  " development families export while exposed-frozen,"
                  " stale-family and damaged-audio builds refuse")
        finally:
            try:
                s.close()
            except Exception:
                pass


def test_export_hardening():
    """An earlier export the user added files to is never replaced;
    the validator reports hostile structure (non-object manifest or
    rows, non-string or traversal audio, symlinks) instead of raising;
    a consent refusal is recorded; a non-folder staging path refuses;
    an unexpected failure leaves no staging and a failed record."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack, sp = prepare(s)
            ex = export_mod.DatasetExporter(s, emit=lambda *a, **k: None)
            views = ("cleanup_supervised",)
            dest = tmp / "ds"
            ex.build(dest, task_views=views)
            (dest / "my-training-script.py").write_text("keep me")
            try:
                ex.build(dest, task_views=views)
                raise AssertionError("replaced an export holding"
                                     " user files")
            except export_mod.ExportError as e:
                assert "destination exists" in str(e)
            assert (dest / "my-training-script.py").exists()
            (dest / "my-training-script.py").unlink()
            # Hostile structure → issues, never an exception.
            bad = tmp / "hostile"
            ex.build(bad, task_views=views)
            manifest = bad / "dataset_manifest.json"
            original = manifest.read_text()
            manifest.write_text("[1, 2, 3]")
            r = export_mod.validate_dataset(bad)
            assert not r["valid"] and \
                "manifest is not an object" in r["issues"], r
            manifest.write_text(original)
            examples = bad / "examples.jsonl"
            rows = examples.read_text()
            examples.write_text(rows + "42\n"
                                + json.dumps({"task_kind": "asr_supervised",
                                              "audio": 7}) + "\n"
                                + json.dumps({"task_kind": "asr_supervised",
                                              "audio": "../../etc/x"})
                                + "\n")
            r = export_mod.validate_dataset(bad)
            assert any("is not an object" in i for i in r["issues"])
            assert "unsafe audio path" in r["issues"], r
            examples.write_text(rows)
            os.symlink("/etc/hosts", bad / "artifacts" / "link.wav")
            r = export_mod.validate_dataset(bad)
            assert any("symlink in dataset" in i for i in r["issues"])
            # A consent refusal is recorded like every other refusal.
            s.append_consent("paused", note="fixture")
            try:
                ex.build(tmp / "ds-consent", task_views=views)
                raise AssertionError("built without consent")
            except export_mod.ExportError:
                pass
            last = ex.last_export()
            assert last["state"] == "failed" and \
                last["error"] == "consent_not_enabled", last
            s.append_consent("enabled", note="fixture")
            # A staging path that is not a leftover build folder.
            (tmp / ".ds-staged.building").write_text("not a folder")
            try:
                ex.build(tmp / "ds-staged", task_views=views)
                raise AssertionError("built over a non-folder staging")
            except export_mod.ExportError as e:
                assert "staging path" in str(e)
            # An unexpected failure mid-build: no staging, failed row.
            real_sums = export_mod._write_sums

            def broken_sums(root):
                raise KeyError("simulated")
            export_mod._write_sums = broken_sums
            try:
                try:
                    ex.build(tmp / "ds-broken", task_views=views)
                    raise AssertionError("broken build completed")
                except export_mod.ExportError as e:
                    assert "KeyError" in str(e)
            finally:
                export_mod._write_sums = real_sums
            assert not (tmp / ".ds-broken.building").exists()
            assert not (tmp / "ds-broken").exists()
            assert ex.last_export()["error"] == "KeyError"
            print("ok  export hardening: user-extended exports kept;"
                  " hostile datasets reported not raised; symlinks"
                  " flagged; consent refusal recorded; staging safe")
        finally:
            try:
                s.close()
            except Exception:
                pass


def test_finalize_recheck_is_about_the_selection():
    """A deletion elsewhere in the store during a build does not abort
    it; a purge (retention or deletion) of an artifact the build
    exported does — the recheck is about this dataset's inputs."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            pack, sp = prepare(s)
            ex = export_mod.DatasetExporter(s, emit=lambda *a, **k: None)
            real_sums = export_mod._write_sums
            unrelated = pack["by_category"]["uncertain"][0]

            def sums_then_delete_unrelated(root):
                s.delete_everywhere("example", unrelated,
                                    reason="user_request")
                real_sums(root)
            export_mod._write_sums = sums_then_delete_unrelated
            try:
                out = ex.build(tmp / "ds-a",
                               task_views=("cleanup_supervised",))
            finally:
                export_mod._write_sums = real_sums
            assert out["state"] == "complete"
            rows = _read_jsonl(tmp / "ds-a" / "examples.jsonl")
            assert unrelated not in {r["example_id"] for r in rows}
            victim = rows[0]["example_id"]
            applied = s.submit(lambda c: c.execute(
                "SELECT json_extract(envelope_json,"
                " '$.artifact_ids.applied_output') FROM"
                " training_revisions WHERE example_id=? ORDER BY rowid"
                " DESC LIMIT 1", (victim,)).fetchone()[0])

            def sums_then_purge_input(root):
                s.submit(lambda c: c.execute(
                    "UPDATE artifacts SET purged=1, content_text=NULL"
                    " WHERE artifact_id=?", (applied,)))
                real_sums(root)
            export_mod._write_sums = sums_then_purge_input
            try:
                ex.build(tmp / "ds-b", task_views=("cleanup_supervised",))
                raise AssertionError("an export completed after one of"
                                     " its inputs was purged")
            except export_mod.ExportError as e:
                assert "aborted" in str(e)
            finally:
                export_mod._write_sums = real_sums
            assert not (tmp / "ds-b").exists()
            print("ok  finalize recheck: unrelated deletions do not abort;"
                  " a purged exported input does")
        finally:
            try:
                s.close()
            except Exception:
                pass


if __name__ == "__main__":
    test_finalize_recheck_is_about_the_selection()
    test_export_hardening()
    test_round_trip_and_determinism()
    test_negative_battery()
    test_audio_deleted_text_only_case()
    test_export_safety_and_semantics()
    print("all dataset export tests passed")
