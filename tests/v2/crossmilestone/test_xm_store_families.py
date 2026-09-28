"""MERGED-X01 — a current-schema store that lost one later relational
table (the cross-milestone remediation of 340c566; Audit C
CROSS-AUDIT-01, Audit B CROSS-AUDIT-05).

Each witness builds real dependent state through the supported services
on a synthetic store, closes it, copies it, removes exactly ONE table
from the copy (the synthetic corruption fixture — direct SQL corruption
is the threat model here, not a supported producer) and reopens the copy
through the real ``Store`` with a backup directory. The oracle is the
semantic consequence the lost table carried, read with plain SQL or the
witness's own records — never the production function under test:

  A  training_memberships  a family exposed for tuning must never
                           return to the blind holdout as unexposed
  B  profile_evidence      deleting a profile's supporting source must
                           not leave its private derived text current
  C  learning_vocabulary_  undo must never disable an entry the user
     deltas                edited after approval
  D  usage_facts           'delete usage' for a job must not leave that
                           job's words in a published daily aggregate

Refusing to open (a recoverable corruption report, the pre-repair
backup untouched) is a PASS for every witness: the store did not present
lost authority as a clean empty feature. Controls pin what must keep
working: a genuinely older store upgrades, a fresh store opens, an
intact current store reopens without repair.

``--matrix OUT`` additionally drops EVERY expected table, one at a time,
from a store populated through the services and records what the open
does (refused / recreated empty) with the dependent rows that survived —
the measured "current repair behavior" column of the schema-family
subledger (an inventory, not pass/fail).

Run:
  .venv/bin/python tests/v2/crossmilestone/test_xm_store_families.py \
      [--json OUT] [--matrix OUT] [NAME...]
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402
from xm_world import M, PRIVATE, drop_table, raw_rows  # noqa: E402

from localflow.v2 import ids  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.analytics import AnalyticsStore  # noqa: E402
from localflow.v2.curation.splits import SplitService  # noqa: E402
from localflow.v2.learning import LearningService  # noqa: E402
from localflow.v2.profile import ProfileService  # noqa: E402
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402

CASES = []
TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


class Reopened:
    """The copied store reopened through the real ``Store``: ``store``
    is None when the open refused (``refusal`` holds the message)."""

    def __init__(self, src_db, src_arts, table, workdir, also=()):
        self.dir = pathlib.Path(workdir) / f"copy-{table}"
        self.dir.mkdir()
        self.db = self.dir / "v2.db"
        shutil.copy2(src_db, self.db)
        for suffix in ("-wal", "-shm"):
            side = pathlib.Path(str(src_db) + suffix)
            if side.exists():
                shutil.copy2(side, pathlib.Path(str(self.db) + suffix))
        self.arts = self.dir / "arts"
        shutil.copytree(src_arts, self.arts)
        drop_table(self.db, table)
        for extra in also:
            drop_table(self.db, extra)
        self.bk = self.dir / "bk"
        self.events = []
        self.refusal = None
        self.store = None
        try:
            self.store = store_mod.Store(
                self.db, artifacts_dir=self.arts, backup_dir=self.bk,
                emit=lambda name, **kw: self.events.append((name, kw)))
        except RuntimeError as e:
            self.refusal = str(e)

    def backups(self):
        return sorted(p.name for p in self.bk.glob("*.db")) \
            if self.bk.exists() else []

    def close(self):
        if self.store is not None:
            self.store.close()


def closed_copy(w):
    """Close the world's store (so the file is quiescent) and return the
    file paths; the world's temp dir stays alive for the copies."""
    w.store.close()
    return w.tmp / "v2.db", w.store.artifacts_dir


def refused_cleanly(r):
    """A refusal is a pass only when it names corruption and the
    pre-repair backup exists."""
    return r.store is None and "corrupt" in (r.refusal or "") \
        and any(b.startswith("v2-pre-repair") for b in r.backups())


# =============================================================================
# A — training_memberships
# =============================================================================

@case("MERGED-X01/A training_memberships")
def x01a_lost_memberships_never_return_exposed_family_to_holdout():
    with M.MWorld() as w:
        w.families(12, asr=True, frozen=2)
        w.splits.assign()
        frozen = [r[0] for r in w.rows(
            "SELECT DISTINCT family_id FROM training_memberships WHERE"
            " partition='frozen_test'")]
        assert frozen, "fixture: no frozen_test family"
        fam = sorted(frozen)[0]
        w.splits.mark_exposed([fam], "inspected_during_tuning")
        # The witness's own record of what was exposed (independent of
        # the table that will be lost).
        assert w.one("SELECT COUNT(*) FROM training_memberships WHERE"
                     " family_id=? AND exposed=1", (fam,))[0] > 0
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "training_memberships", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                SplitService(r.store).assign()
                got = X.rows(r.store,
                             "SELECT partition, exposed FROM"
                             " training_memberships WHERE family_id=?",
                             (fam,))
                assert got, "family vanished from the new assignment"
                assert not any(p == "frozen_test" and not e
                               for p, e in got), (
                    f"exposed family {fam} returned to the blind holdout"
                    f" as unexposed after the repair: {sorted(set(got))}")
            finally:
                r.close()


# =============================================================================
# B — profile_evidence
# =============================================================================

@case("MERGED-X01/B profile_evidence")
def x01b_lost_profile_evidence_never_keeps_dead_private_text():
    with M.MWorld(min_words=10) as w:
        jobs = [w.job(f"{PRIVATE.lower()} zephyr orchard notes {i}"
                      f" alpha beta gamma delta")
                for i in range(12)]
        snap = w.profile.compute()
        assert PRIVATE.lower() in json.dumps(snap["measured"]), \
            "fixture: canary phrase not in the profile"
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "profile_evidence", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                for j in jobs:  # the supported deletion of every source
                    r.store.delete_everywhere("job", j["job_id"])
                cur = ProfileService(r.store).current()
                blob = json.dumps(cur or {})
                leaked = [t for t in X.rows(
                    r.store, "SELECT measured_json || cards_json FROM"
                    " profile_snapshots") if PRIVATE.lower() in t[0]]
                assert PRIVATE.lower() not in blob and not leaked, (
                    "a deleted source's private phrase is still current"
                    f" profile content (state={(cur or {}).get('state')},"
                    f" rows_with_canary={len(leaked)})")
            finally:
                r.close()


# =============================================================================
# C — learning_vocabulary_deltas
# =============================================================================

@case("MERGED-X01/C learning_vocabulary_deltas")
def x01c_lost_deltas_never_let_undo_destroy_a_user_edit():
    with M.MWorld() as w:
        j = w.job(TEACH_RAW)
        cid = w.learning.teach_correction(j["job_id"],
                                          TEACH_FIX)["candidate_id"]
        out = w.learning.approve(cid)
        assert out.get("action") == "created", out
        eid = out["entry_id"]
        e = w.vocab.entry(eid)
        # The user renames the learned entry under normal revision
        # authority; the single approved alias is left as it was.
        w.vocab.update_entry(eid, expected_revision=e.revision,
                             canonical="module-user-edit")
        assert w.one("SELECT COUNT(*) FROM learning_vocabulary_deltas"
                     " WHERE candidate_id=?", (cid,))[0] == 1
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "learning_vocabulary_deltas", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                vs = VocabularyStore(r.store)
                try:
                    LearningService(r.store, vocabulary=vs) \
                        .undo_approval(cid)
                except ValueError:
                    pass  # a refusal keeps the user's edit
                row = X.one(r.store, "SELECT canonical, enabled FROM"
                            " vocabulary_entries WHERE entry_id=?", (eid,))
                assert row == ("module-user-edit", 1), (
                    "undo without its recorded delta disabled or changed"
                    f" the user-edited entry: {row}")
            finally:
                r.close()


# =============================================================================
# D — usage_facts
# =============================================================================

@case("MERGED-X01/D usage_facts")
def x01d_lost_usage_facts_never_keep_deleted_usage_in_aggregates():
    with M.MWorld() as w:
        an = AnalyticsStore(w.store, reporting_timezone="UTC")
        target = w.job("usage witness words one two three")
        other = w.job("unrelated usage words")
        day_at = "2026-09-27T10:00:00.000000Z"
        for j, words in ((target, 5), (other, 3)):
            an.record_dictation_fact(
                job_id=j["job_id"], activity_at_utc=day_at,
                timezone="UTC", utc_offset_minutes=0, final_words=words,
                raw_words=words, insertion_outcome="confirmed",
                app_name="Synthetic Editor", app_bundle=M.APP)
        before = w.rows("SELECT day_local, dictations FROM"
                        " daily_aggregates")
        assert before and before[0][1] == 2, f"fixture: {before}"
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "usage_facts", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                an2 = AnalyticsStore(r.store, reporting_timezone="UTC")
                an2.ensure_current()  # the launch drift check
                an2.delete_usage_for_job(target["job_id"])
                agg = X.rows(r.store, "SELECT day_local, dictations FROM"
                             " daily_aggregates")
                assert not any(n >= 2 for _d, n in agg), (
                    "the deleted job's usage still counts in a published"
                    f" daily aggregate: {agg}")
            finally:
                r.close()


# =============================================================================
# E..J — every other later family with authority or user-authored content
# (the full tracked inventory, schema_family_subledger.json)
# =============================================================================

@case("MERGED-X01/E learning_candidates")
def x01e_lost_candidates_never_forget_a_permanent_rejection():
    with M.MWorld() as w:
        j = w.job(TEACH_RAW)
        cid = w.learning.teach_correction(j["job_id"],
                                          TEACH_FIX)["candidate_id"]
        w.learning.reject(cid)
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "learning_candidates", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                ls = LearningService(r.store,
                                     vocabulary=VocabularyStore(r.store))
                # The same correction taught again on a new dictation.
                s = r.store
                job2, fam2 = s.create_job()
                aid = s.write_text_artifact(
                    job_id=job2, stage="cleanup", role="applied_output",
                    text=TEACH_RAW, retention_class="training")
                s.grant_lease(aid, "training", days=30)
                ex = s.upsert_example(job_id=job2, family_id=fam2,
                                      consent_revision_id=
                                      s.current_consent_id())
                s.append_revision(ex, {
                    "example_id": ex, "job_id": job2, "family_id": fam2,
                    "origin": "live_capture",
                    "artifact_ids": {"applied_output": aid},
                    "outcome": {}, "annotations": [],
                    "missing_reasons": {}})
                cid2 = ls.teach_correction(job2, TEACH_FIX)["candidate_id"]
                status = X.one(s, "SELECT status FROM learning_candidates"
                               " WHERE candidate_id=?", (cid2,))[0]
                try:
                    approved = ls.approve(cid2).get("entry_id")
                except ValueError:
                    approved = None
                assert status != "pending" and not approved, (
                    "a permanently rejected correction was proposed again"
                    f" (status={status}) and approval landed a rule"
                    f" ({bool(approved)})")
            finally:
                r.close()


@case("MERGED-X01/F correction_labels")
def x01f_lost_labels_never_readmit_background_speech():
    with M.MWorld(min_words=10) as w:
        for i in range(11):
            w.job(f"ordinary speech words {i} alpha beta gamma")
        bg = w.job("backgroundcanary television dialogue words")
        w.review.record_label(bg["example_id"], edit_kind="unknown",
                              domains=["background_speech"])
        snap = w.profile.compute()
        assert snap["measured"]["excluded"]["background_speech"] == 1, \
            f"fixture: {snap['measured']['excluded']}"
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "correction_labels", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                out = ProfileService(r.store, min_words=10).compute()
                used = {x for (x,) in X.rows(
                    r.store, "SELECT example_id FROM profile_evidence"
                    " WHERE snapshot_id=? AND role='measured'",
                    (out["snapshot_id"],))}
                assert bg["example_id"] not in used, (
                    "speech the user labeled background speech is counted"
                    " as their own again after the repair")
            finally:
                r.close()


def _normalize(store, text):
    from localflow.v2 import vocabulary as vocab_mod
    snap = vocab_mod.VocabularySnapshot(VocabularyStore(store).entries(),
                                        vocab_mod.ScopeContext())
    return vocab_mod.sandbox_phrase(text, snap).get("output")


@case("MERGED-X01/G vocabulary family (M05-AUDIT-18)", kind="control")
def c_torn_dictionary_stays_detectable_after_repair():
    """The vocabulary family is M05's to govern (M05-AUDIT-18): the Store
    repairs it and the dictionary's own integrity report tells a torn
    dictionary from a healthy one — the app turns the vocabulary off on
    vanished entries and warns on lost aliases (the product-level half is
    test_xm_remediation.c_app_refuses_a_torn_dictionary). Measured: lost
    entries and lost aliases are both detected after the repair."""
    for table, key in (("vocabulary_entries", "vanished_entries"),
                       ("vocabulary_aliases", "entries_missing_aliases")):
        with M.MWorld() as w:
            w.vocab.add_entry("Orion SDK", [("orion s d k", True)],
                              approved=True)
            db, arts = closed_copy(w)
            with tempfile.TemporaryDirectory() as td:
                r = Reopened(db, arts, table, td)
                try:
                    assert r.store is not None, r.refusal
                    rep = VocabularyStore(r.store).integrity_report()
                    assert rep[key] >= 1, (table, rep)
                finally:
                    r.close()


@case("MERGED-X01/H transforms")
def x01h_lost_transform_rows_never_drop_a_user_definition():
    from localflow.v2.transforms_store import TransformStore
    with M.MWorld() as w:
        tfs = TransformStore(w.store)
        tfs.seed_built_ins()
        t = tfs.add_transform(name="User custom", mode="custom",
                              prompt="Rewrite as a numbered list.")
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "transforms", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                t2 = TransformStore(r.store)
                t2.seed_built_ins()
                have = {d.transform_id for d in t2.definitions()}
                assert t.transform_id in have, (
                    "the user's custom transform vanished while its"
                    " preserved revisions survive")
            finally:
                r.close()


@case("MERGED-X01/H transform_revisions")
def x01h2_lost_revisions_never_present_history_as_none():
    from localflow.v2.transforms_store import TransformStore
    with M.MWorld() as w:
        tfs = TransformStore(w.store)
        t = tfs.add_transform(name="User custom", mode="custom",
                              prompt="first instruction")
        tfs.update_transform(t.transform_id, prompt="second instruction")
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "transform_revisions", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                revs = TransformStore(r.store).revisions_of(t.transform_id)
                assert len(revs) == 2, (
                    "preserved transform definitions were erased and the"
                    f" history reads as {len(revs)} revision(s)")
            finally:
                r.close()


@case("MERGED-X01/I snippets")
def x01i_lost_snippets_are_not_an_empty_registry():
    from localflow.v2.snippets_store import SnippetStore
    with M.MWorld() as w:
        SnippetStore(w.store).add_snippet(trigger="insert my signature",
                                          name="sig",
                                          content="Synthetic Signature")
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "snippets", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                got = SnippetStore(r.store).snippets()
                assert got, "the user's snippets silently became empty"
            finally:
                r.close()


@case("MERGED-X01/J split_assignments")
def x01j_lost_assignments_keep_the_assignment_history():
    with M.MWorld() as w:
        w.families(12, asr=True)
        w.splits.assign()
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "split_assignments", td)
            try:
                if refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                sv = SplitService(r.store)
                try:
                    out = sv.assign()
                    err = None
                except Exception as e:  # noqa: BLE001
                    out, err = None, f"{type(e).__name__}: {e}"
                assert err is None and out["assignment_version"] == 2, (
                    "after the repair the assignment history reads as"
                    f" empty and the next assignment {err or out}")
            finally:
                r.close()


# ---- family siblings: each table's own dependent-state witness ---------------

def lost(table, build, check, refusal_passes=True):
    """Build real state with ``build(w)``, lose ``table`` in a copy and
    reopen; ``check(store, ctx)`` asserts the semantic consequence (a
    clean refusal passes unless ``refusal_passes`` is False: a derivable
    table must open and be rebuilt)."""
    with M.MWorld() as w:
        ctx = build(w)
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, table, td)
            try:
                if refusal_passes and refused_cleanly(r):
                    return
                assert r.store is not None, f"open failed: {r.refusal}"
                check(r.store, ctx)
            finally:
                r.close()


@case("MERGED-X01/H transform_meta")
def x01h3_lost_transform_registry_revision_never_restarts():
    from localflow.v2.transforms_store import TransformStore

    def build(w):
        tfs = TransformStore(w.store)
        tfs.seed_built_ins()
        tfs.add_transform(name="A", mode="custom", prompt="a")
        return {"rev": tfs.revision()}

    def check(store, ctx):
        tfs = TransformStore(store)
        tfs.add_transform(name="B", mode="custom", prompt="b")
        assert tfs.revision() > ctx["rev"], (
            f"the transform registry revision restarted at"
            f" {tfs.revision()} (was {ctx['rev']})")
    lost("transform_meta", build, check)


@case("MERGED-X01/H transform_candidates")
def x01h4_lost_candidates_never_orphan_recorded_judgments():
    def build(w):
        task = w.transform_task("candidate source text", ["one", "two"])
        cands = [c if isinstance(c, str) else c["candidate_id"]
                 for c in (task.get("candidates")
                           or task.get("candidate_ids") or [])]
        assert len(cands) >= 2, f"fixture: {task}"
        w.judge(task, cands[0], cands[1], "prefer_a")
        return {"task": task["task_key"]}

    def check(store, ctx):
        judged = X.rows(store, "SELECT candidate_id FROM"
                        " preference_observations WHERE task_key=?",
                        (ctx["task"],))
        have = X.rows(store, "SELECT candidate_id FROM transform_candidates"
                      " WHERE task_key=?", (ctx["task"],))
        assert not judged or have, (
            "recorded same-task judgments survive while every candidate"
            " they judged is gone (the task reads as never run)")
    lost("transform_candidates", build, check)


@case("MERGED-X01/I style_rules")
def x01i2_lost_style_rules_are_not_an_empty_registry():
    from localflow.v2.profiles_store import StyleRuleStore

    def build(w):
        StyleRuleStore(w.store).add_rule(name="formal in mail",
                                         scope_kind="app",
                                         scope_value="com.synthetic.mail",
                                         mode="clean")

    def check(store, _ctx):
        assert StyleRuleStore(store).rules(), \
            "the user's style rules silently became empty"
    lost("style_rules", build, check)


@case("MERGED-X01/I profiles_meta")
def x01i3_lost_profile_registry_revision_never_restarts():
    from localflow.v2.snippets_store import SnippetStore

    def build(w):
        s = SnippetStore(w.store)
        s.add_snippet(trigger="insert sig one", name="a", content="A")
        s.add_snippet(trigger="insert sig two", name="b", content="B")
        return {"rev": s.revision()}

    def check(store, ctx):
        s = SnippetStore(store)
        s.add_snippet(trigger="insert sig three", name="c", content="C")
        assert s.revision() > ctx["rev"], (
            f"the snippet registry revision restarted at {s.revision()}"
            f" (was {ctx['rev']})")
    lost("profiles_meta", build, check)


@case("MERGED-X01/D daily_aggregates")
def x01d2_lost_aggregates_never_hide_recorded_usage():
    def build(w):
        an = AnalyticsStore(w.store, reporting_timezone="UTC")
        j = w.job("aggregate witness words")
        an.record_dictation_fact(
            job_id=j["job_id"],
            activity_at_utc="2026-09-27T10:00:00.000000Z", timezone="UTC",
            utc_offset_minutes=0, final_words=5, raw_words=5,
            insertion_outcome="confirmed")

    def check(store, _ctx):
        an = AnalyticsStore(store, reporting_timezone="UTC")
        an.ensure_current()  # the launch drift check
        agg = X.rows(store, "SELECT day_local, dictations FROM"
                     " daily_aggregates")
        assert agg == [("2026-09-27", 1)], (
            "recorded usage read as a day with no dictations in Insights"
            f" after the repair: {agg}")
    # Derivable (xm-policy-r1 D01, review RV-07): the store opens and the
    # launch check rebuilds it — refusing would stop dictation over a
    # table usage_facts can recompute.
    lost("daily_aggregates", build, check, refusal_passes=False)


@case("MERGED-X01/A (review RV-06: schema_meta lost with a family table)")
def x01k_lost_version_stamp_never_bypasses_family_integrity():
    with M.MWorld() as w:
        w.families(12, asr=True, frozen=2)
        w.splits.assign()
        assert w.one("SELECT COUNT(*) FROM training_memberships")[0], \
            "fixture: no memberships"
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "training_memberships", td,
                         also=("schema_meta",))
            try:
                recreated = r.store is not None and X.rows(
                    r.store, "SELECT COUNT(*) FROM training_memberships"
                    )[0][0] == 0
                assert refused_cleanly(r), (
                    "a store that lost its version stamp and"
                    " training_memberships opened"
                    f" (memberships recreated empty={recreated},"
                    f" backups={r.backups()}, refusal={r.refusal!r})")
            finally:
                r.close()


# ---- recreate-safe classifications, measured -------------------------------

@case("MERGED-X01 recreate-safe: preference_observations", kind="control")
def c_lost_judgments_only_shrink_exports():
    """No surviving row distinguishes lost judgments from never-judged
    candidates; the consequence must be fail-closed (fewer exported
    targets), never a wrong one."""
    with M.MWorld() as w:
        w.families(12, asr=True)
        w.splits.assign()
        task = w.transform_task("safe source text", ["one", "two"])
        cands = [c if isinstance(c, str) else c["candidate_id"]
                 for c in (task.get("candidates")
                           or task.get("candidate_ids") or [])]
        w.accept(task, cands[0])
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "preference_observations", td)
            try:
                assert r.store is not None, r.refusal
                from localflow.v2.curation.export import DatasetExporter
                out = DatasetExporter(r.store).build(
                    pathlib.Path(td) / "ds",
                    task_views=("transform_supervised",))
                assert out["counts"]["examples"] == 0, out["counts"]
            finally:
                r.close()


@case("MERGED-X01 recreate-safe: sampling_decisions", kind="control")
def c_lost_sampling_decisions_redraw_identically():
    from localflow.v2.curation.sampling import SamplingService
    with M.MWorld() as w:
        for i in range(30):
            w.job(f"sampling words {i} alpha beta")
        w.sampling.refresh()
        before = sorted(w.rows("SELECT example_id, inclusion_reason FROM"
                               " sampling_decisions"))
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "sampling_decisions", td)
            try:
                assert r.store is not None, r.refusal
                SamplingService(r.store).refresh()
                after = sorted(X.rows(r.store, "SELECT example_id,"
                                      " inclusion_reason FROM"
                                      " sampling_decisions"))
                assert before and after == before, (
                    f"the seeded re-draw differs: {len(before)} decisions"
                    f" before, {len(after)} after")
            finally:
                r.close()


# =============================================================================
# controls
# =============================================================================

def _old_schema_store(path, version):
    """A genuinely older store: the real migrations up to ``version``."""
    saved = store_mod._MIGRATIONS
    store_mod._MIGRATIONS = {k: v for k, v in saved.items() if k <= version}
    try:
        s = store_mod.Store(path, artifacts_dir=path.parent / "arts")
    finally:
        store_mod._MIGRATIONS = saved
    return s


@case("MERGED-X01 control", kind="control")
def c_genuinely_older_store_upgrades_with_backup():
    for version in (9, 12):
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "v2.db"
            s = _old_schema_store(db, version)
            job, fam = s.create_job()
            if version >= 10:
                # A legacy approval from before recorded deltas existed.
                s.submit(lambda c: c.execute(
                    "INSERT INTO learning_candidates(candidate_id, job_id,"
                    " source, status, created_at_utc, updated_at_utc)"
                    " VALUES('cand-legacy', ?, 'teach', 'approved',"
                    " '2026-09-20T00:00:00Z', '2026-09-20T00:00:00Z')",
                    (job,)))
            s.close()
            assert raw_rows(db, "SELECT value FROM schema_meta WHERE"
                            " key='schema_version'") == [(str(version),)]
            s2 = store_mod.Store(db, artifacts_dir=db.parent / "arts",
                                 backup_dir=db.parent / "bk")
            try:
                v = X.one(s2, "SELECT value FROM schema_meta WHERE"
                          " key='schema_version'")[0]
                assert v == str(max(store_mod._MIGRATIONS)), v
                assert any(p.name.startswith("v2-pre-migrate")
                           for p in (db.parent / "bk").glob("*.db"))
            finally:
                s2.close()


@case("GATE-G04 every historical schema", kind="control")
def c_every_historical_schema_upgrades_with_an_exact_backup():
    """A real store at each schema 1..12 (the real migrations up to it,
    with a job row) upgrades to the current version through the same
    open that now refuses damaged current stores: never refused, never
    'repaired', and its pre-migrate backup holds exactly the pre-upgrade
    rows (read back independently)."""
    target = max(store_mod._MIGRATIONS)
    for version in range(1, target):
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "v2.db"
            s = _old_schema_store(db, version)
            s.create_job()
            s.close()
            before = raw_rows(db, "SELECT job_id, state FROM jobs")
            events = []
            s2 = store_mod.Store(db, artifacts_dir=db.parent / "arts",
                                 backup_dir=db.parent / "bk",
                                 emit=lambda n, **k: events.append(n))
            try:
                v = X.one(s2, "SELECT value FROM schema_meta WHERE"
                          " key='schema_version'")[0]
            finally:
                s2.close()
            assert v == str(target), (version, v)
            assert "store.schema_corrupt" not in events and \
                "store.schema_repaired" not in events, (version, events)
            backups = sorted((db.parent / "bk").glob("v2-pre-migrate*.db"))
            assert len(backups) == 1, (version, backups)
            assert raw_rows(backups[0], "SELECT value FROM schema_meta"
                            " WHERE key='schema_version'") == \
                [(str(version),)], version
            assert raw_rows(backups[0], "SELECT job_id, state FROM jobs") \
                == before, version


@case("MERGED-X01 control (review RV-06: only the version stamp lost)",
      kind="control")
def c_lost_version_stamp_alone_reopens_with_a_backup():
    with M.MWorld() as w:
        w.families(12, asr=True)
        w.splits.assign()
        before = w.one("SELECT COUNT(*) FROM training_memberships")[0]
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            r = Reopened(db, arts, "schema_meta", td)
            try:
                assert r.store is not None, f"refused: {r.refusal}"
                assert X.rows(r.store, "SELECT COUNT(*) FROM"
                              " training_memberships")[0][0] == before
                assert r.store._schema_version() == max(
                    store_mod._MIGRATIONS)
                assert any(b.startswith("v2-pre-repair")
                           for b in r.backups()), r.backups()
            finally:
                r.close()


@case("MERGED-X01 control", kind="control")
def c_fresh_store_opens_empty():
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        s = store_mod.Store(db, artifacts_dir=db.parent / "arts",
                            backup_dir=db.parent / "bk")
        try:
            assert X.one(s, "SELECT COUNT(*) FROM jobs")[0] == 0
        finally:
            s.close()


@case("MERGED-X01 control", kind="control")
def c_intact_current_store_reopens_without_repair():
    with M.MWorld(min_words=10) as w:
        for i in range(12):
            w.job(f"intact reopen words {i} alpha beta")
        w.families(12, asr=True)
        w.splits.assign()
        w.profile.compute()
        j = w.job(TEACH_RAW)
        cid = w.learning.teach_correction(j["job_id"],
                                          TEACH_FIX)["candidate_id"]
        w.learning.approve(cid)
        db, arts = closed_copy(w)
        events = []
        s = store_mod.Store(db, artifacts_dir=arts,
                            backup_dir=db.parent / "bk2",
                            emit=lambda n, **k: events.append(n))
        try:
            assert "store.schema_repaired" not in events, events
            assert "store.schema_corrupt" not in events, events
        finally:
            s.close()


# =============================================================================
# the per-table matrix (inventory)
# =============================================================================

def populate(w):
    """Real dependent rows in as many families as the services write."""
    from localflow.v2.notes import NoteStore
    from localflow.v2.profiles_store import StyleRuleStore
    from localflow.v2.snippets_store import SnippetStore
    w.profile.min_words = 10
    fams = w.families(12, asr=True, frozen=2)
    for i in range(10):
        w.job(f"{PRIVATE.lower()} matrix words {i} alpha beta")
    w.splits.assign()
    frozen = [r[0] for r in w.rows(
        "SELECT DISTINCT family_id FROM training_memberships WHERE"
        " partition='frozen_test'")]
    w.splits.mark_exposed(frozen[:1], "inspected_during_tuning")
    w.splits.set_tag(fams[0]["example_id"], "regression")
    w.review.record_label(fams[1]["example_id"], edit_kind="recognition_error",
                          origin_stages=["asr"])
    w.sampling.refresh()
    w.profile.compute()
    j = w.job(TEACH_RAW)
    cid = w.learning.teach_correction(
        j["job_id"], TEACH_FIX, operation_id="op-teach")["candidate_id"]
    w.learning.approve(cid, operation_id="op-approve")
    w.vocab.add_entry("Orion SDK", [("orion s d k", True)], approved=True)
    tfs = w.tf_store()
    tfs.seed_built_ins()
    tfs.add_transform(name="Matrix custom", mode="custom",
                      prompt="Rewrite as a list.")
    task = w.transform_task("matrix source text", ["out one", "out two"])
    cands = task.get("candidates") or task.get("candidate_ids") or []
    if len(cands) >= 2:
        cand_ids = [c if isinstance(c, str) else c["candidate_id"]
                    for c in cands]
        w.judge(task, cand_ids[0], cand_ids[1], "prefer_a")
    w.observation(fams[2]["job_id"], "before text", "after text")
    NoteStore(w.store).create_note("matrix note text")
    StyleRuleStore(w.store).add_rule(name="matrix rule")
    SnippetStore(w.store).add_snippet(trigger="matrix sig", name="sig",
                                      content="Matrix signature")
    an = AnalyticsStore(w.store, reporting_timezone="UTC")
    an.record_dictation_fact(
        job_id=fams[3]["job_id"],
        activity_at_utc="2026-09-27T10:00:00.000000Z", timezone="UTC",
        utc_offset_minutes=0, final_words=4, raw_words=4,
        insertion_outcome="confirmed")
    try:
        w.export(w.tmp / "matrix-export", ("asr_supervised",))
    except Exception:  # noqa: BLE001 — the manifest row is recorded either way
        pass
    w.store.delete_everywhere("job", fams[4]["job_id"])
    w.store.sync()


def matrix(out_path):
    tables = None
    results = []
    with M.MWorld() as w:
        populate(w)
        counts = {t: w.one(f"SELECT COUNT(*) FROM {t}")[0] for (t,) in
                  w.rows("SELECT name FROM sqlite_master WHERE"
                         " type='table' AND name NOT LIKE 'sqlite_%'"
                         " ORDER BY name")}
        tables = sorted(counts)
        db, arts = closed_copy(w)
        with tempfile.TemporaryDirectory() as td:
            for t in tables:
                r = Reopened(db, arts, t, td)
                try:
                    results.append({
                        "table": t, "rows_before": counts[t],
                        "open": ("refused" if r.store is None
                                 else "recreated_empty"),
                        "refusal": (r.refusal or "")[:200] or None,
                        "pre_repair_backup": any(
                            b.startswith("v2-pre-repair")
                            for b in r.backups()),
                        "events": sorted({n for n, _k in r.events})})
                finally:
                    r.close()
    pathlib.Path(out_path).write_text(json.dumps({
        "kind": "xm_schema_family_open_matrix",
        "code": X.code_stamp(
            "tests/v2/crossmilestone/test_xm_store_families.py"),
        "tables": len(tables), "results": results}, indent=1))
    for r in results:
        print(f"{r['open']:16} rows={r['rows_before']:<4} {r['table']}")


# =============================================================================
# runner
# =============================================================================

def main(argv):
    out_path = matrix_path = None
    for flag in ("--json", "--matrix"):
        if flag in argv:
            i = argv.index(flag)
            if flag == "--json":
                out_path = argv[i + 1]
            else:
                matrix_path = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    if matrix_path:
        matrix(matrix_path)
        return 0
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
            detail = (f"{type(e).__name__}: {e}"[:300] + " | "
                      + traceback.format_exc()[-1200:])
        detail = M_redact(detail)
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "kind": fn.kind, "status": status,
                        "detail": detail,
                        "seconds": round(time.monotonic() - t0, 2)})
        print(f"{status:5}  {fn.__name__}  [{fn.finding}]"
              + (f"  — {detail.splitlines()[0][:160]}" if detail else ""))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("xm store families:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_store_families.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_store_families.py"),
            "counts": counts, "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


def M_redact(text):
    import re
    if not text:
        return text
    tmp = tempfile.gettempdir()
    for real, mark in ((str(X.ROOT), "<repo>"), ("/private" + tmp, "<tmp>"),
                       (tmp, "<tmp>"), (str(pathlib.Path.home()), "<home>")):
        text = text.replace(real, mark)
    text = re.sub(r"[^\s'\"()]*scratchpad/[^\s'\"()]*", "<scratch>", text)
    return re.sub(r"/private/var/folders/[^\s'\"()]*|/var/folders/"
                  r"[^\s'\"()]*", "<tmp>", text)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
