"""EV-21 splits (V2 M14, S29.11): versioned family assignment,
exposure handling, tags independent of partitions, the minimum-family
honesty floor and the contamination checks (M14-AC08).

Run: .venv/bin/python tests/v2/training/test_splits.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.curation import splits  # noqa: E402


def make_store(tmp):
    return store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups")


def add_example(s, i, family):
    job, fam = s.create_job(family_id=family)
    raw = s.write_text_artifact(
        job_id=job, stage="asr", role="raw_transcript",
        text=f"synthetic split utterance {i}",
        retention_class="training")
    ex = s.upsert_example(job_id=job, family_id=fam)
    s.append_revision(ex, {
        "example_id": ex, "job_id": job, "family_id": fam,
        "artifact_ids": {"source_text": raw}, "outcome": {},
        "annotations": [], "missing_reasons": {}})
    return ex


def test_versioned_assignment_and_leakage():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            for i in range(12):
                add_example(s, i, f"fam-a{i:02d}")
            sp = splits.SplitService(s, emit=lambda *a, **k: None)
            a1 = sp.assign()
            assert a1["assignment_version"] == 1
            assert sum(a1["assigned"].values()) == 12
            assert not a1["unassigned_reason"]
            # Retries share the family (M02): both members follow the
            # family's partition.
            add_example(s, 99, "fam-a00")
            a2 = sp.assign()
            assert a2["assignment_version"] == 2
            parts = s.submit(lambda c: c.execute(
                "SELECT DISTINCT partition FROM"
                " training_memberships WHERE family_id='fam-a00' AND"
                " assignment_version=2").fetchall())
            assert len(parts) == 1, parts
            # Injected leakage (a rogue second membership putting the
            # family in two partitions within one version) is DETECTED
            # by the contamination check.
            s.submit(lambda c: c.execute(
                "INSERT INTO training_memberships(example_id, family_id,"
                " assignment_version, partition, exposed, created_at_utc)"
                " VALUES('ex-rogue', 'fam-a01', 2, 'train', 0,"
                " '2026-09-23T00:00:00.000Z')"))
            cont = sp.contamination()
            assert cont["families_spanning_partitions"] == 1, cont
            print("ok  versioned assignment; family-owned partitions;"
                  " injected leakage detected")
        finally:
            s.close()


def test_exposure_moves_forward_only():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            for i in range(12):
                add_example(s, i, f"fam-b{i:02d}")
            sp = splits.SplitService(s, emit=lambda *a, **k: None)
            sp.assign()
            frozen = [f["family_id"] for f in sp.family_report()
                      if f["partition"] == "frozen_test"]
            assert frozen
            mark = sp.mark_exposed([frozen[0]],
                                   "inspected_during_tuning")
            # Old version untouched; new version moved + tagged.
            old = s.submit(lambda c: c.execute(
                "SELECT DISTINCT partition FROM"
                " training_memberships WHERE family_id=? AND"
                " assignment_version=?",
                (frozen[0], mark["assignment_version"] - 1)).fetchall())
            assert old[0][0] == "frozen_test"
            new = s.submit(lambda c: c.execute(
                "SELECT DISTINCT partition, exposed FROM"
                " training_memberships WHERE family_id=? AND"
                " assignment_version=?",
                (frozen[0], mark["assignment_version"])).fetchall())
            assert new[0] == ("train", 1)
            tagged = s.submit(lambda c: c.execute(
                "SELECT COUNT(*) FROM example_tags WHERE"
                " tag='regression'").fetchone()[0])
            assert tagged >= 1
            cont = sp.contamination()
            assert cont["exposed_frozen_families"] == 0
            # A later re-assignment (new families arriving) must not
            # hash the exposed family straight back into frozen_test.
            add_example(s, 50, "fam-b50")
            again = sp.assign()
            back = s.submit(lambda c: c.execute(
                "SELECT DISTINCT partition, exposed FROM"
                " training_memberships WHERE family_id=? AND"
                " assignment_version=?",
                (frozen[0], again["assignment_version"])).fetchall())
            assert back == [("train", 1)], back
            assert sp.contamination()["exposed_frozen_families"] == 0
            # A family with no live members for one version keeps its
            # exposure when its members return (exposure is permanent).
            members = s.submit(lambda c: [r[0] for r in c.execute(
                "SELECT example_id FROM training_examples WHERE"
                " family_id=?", (frozen[0],)).fetchall()])
            for ex in members:
                s.set_example_state(ex, "excluded")
            sp.assign()  # the family is absent from this version
            for ex in members:
                s.set_example_state(ex, "captured_unreviewed")
            returned = sp.assign()
            back = s.submit(lambda c: c.execute(
                "SELECT DISTINCT partition, exposed FROM"
                " training_memberships WHERE family_id=? AND"
                " assignment_version=?",
                (frozen[0], returned["assignment_version"])).fetchall())
            assert back == [("train", 1)], back
            try:
                sp.mark_exposed(["fam-does-not-exist"], "typo")
                raise AssertionError("unknown family reported exposed")
            except ValueError as e:
                assert "unknown_family" in str(e)
            print("ok  exposure: new version only, old manifests keep"
                  " their truth, regression tag applied, re-assignment"
                  " keeps exposed families out of the holdout")
        finally:
            s.close()


def test_tags_never_change_partition():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            ex = add_example(s, 0, "fam-c00")
            sp = splits.SplitService(s, emit=lambda *a, **k: None)
            sp.assign()
            before = sp.membership(ex)
            for tag in splits.TAGS:
                sp.set_tag(ex, tag, True)
            after = sp.membership(ex)
            assert after["partition"] == before["partition"]
            assert set(after["tags"]) == set(splits.TAGS)
            sp.set_tag(ex, "regression", False)
            assert "regression" not in sp.membership(ex)["tags"]
            try:
                sp.set_tag(ex, "not_a_tag")
                raise AssertionError("invalid tag accepted")
            except ValueError:
                pass
            print("ok  tags are independent of partitions (AC08)")
        finally:
            s.close()


def test_minimum_family_floor_and_late_hints():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            for i in range(3):
                add_example(s, i, f"fam-d{i:02d}")
            sp = splits.SplitService(s, emit=lambda *a, **k: None)
            a = sp.assign()
            assert a["assigned"]["unassigned"] == 3
            assert "insufficient_families" in a["unassigned_reason"]
            # A hint-set artifact written after revision 1 and
            # referenced by a later revision is caught (S29.11: no
            # retroactive original hints). The fixture backdates the
            # example's capture so the ordering is unambiguous.
            ex = add_example(s, 9, "fam-d90")
            late = s.write_text_artifact(
                job_id="late", stage="pre_decode", role="hint_set",
                text="{}", kind="hint_set_json",
                retention_class="training")
            s.submit(lambda c: c.execute(
                "UPDATE artifacts SET created_at_utc="
                "'2027-01-01T00:00:00.000Z' WHERE artifact_id=?",
                (late,)))
            env = s.latest_revision(ex) or {}
            env["context"] = {"artifact_ids": {"hint_set": late}}
            env["revision_id"] = None
            s.append_revision(ex, env)
            cont = sp.contamination()
            assert cont["hint_sets_after_capture"] >= 1
            print("ok  minimum-family honesty floor; late hint"
                  " artifacts detected as contamination")
        finally:
            s.close()


if __name__ == "__main__":
    test_versioned_assignment_and_leakage()
    test_exposure_moves_forward_only()
    test_tags_never_change_partition()
    test_minimum_family_floor_and_late_hints()
    print("all splits tests passed")
