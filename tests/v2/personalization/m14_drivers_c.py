"""M14 corpus drivers, group c: approval, undo, counterexamples and
suppression.

Binds cases LF-M14-C073..C100 (approval C073-C080, undo C081-C087,
counterexamples C088-C094, suppression C095-C100), stateful probes
LF-M14-S005, S006, S007, S029, S031 and metamorphic relations
LF-M14-MR001, MR002, MR013.

Every approval/undo effect is graded through the REAL M05 snapshot and
sandbox (``VocabularySnapshot`` + ``sandbox_phrase`` under an explicit
``ScopeContext``) and raw vocabulary rows; expected texts, scope values,
aliases and counts are literals this module wrote into its fixtures —
never the output of the production function under test. Policy-bound
entries are graded under m14-policy-r1 D05 (global pair suppression),
D06 (counterexample population, "untested" when empty) and D12 (single
writer approval/undo with recorded deltas and operation receipts).

Seams: op hooks between writer ops (``after_each_op``) reproduce the
audited base's multi-op windows; on the repaired tree, where approval
and undo are one writer op, the read-then-write window is reached
INSIDE that op by wrapping ``VocabularyStore.entry_in`` and applying the
interleaved user edit through M05's own composable ``update_entry_in``
on the writer connection (a model of a concurrent writer — the edit
commits with the op). A seam that cannot exist in production (plan and
effect in one op) is graded ``structural`` with the op count as witness,
together with both alternate serializations.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from m14_world import (APP, PRIVATE_CANARY, MWorld, accepts,  # noqa: E402
                       after_each_op, patched)
from m14_drivers_common import check, drives, invalid  # noqa: E402

RAW = "please check the modul today"
FIX = "please check the module today"
OTHER_APP = "com.synthetic.other"
SITE = "https://docs.synthetic.example"
OTHER_SITE = "https://other.synthetic.example"
ADVERSE = "keep the modul here"
D05 = "m14-policy-r1:D05"
D06 = "m14-policy-r1:D06"
D12 = "m14-policy-r1:D12"


# ---- helpers (independent readers; production only where driven) ----------


def refused(fn, *a, **kw):
    """(True, message) when the call raised, else (False, result)."""
    try:
        return False, fn(*a, **kw)
    except Exception as e:  # noqa: BLE001 — a refusal of any typed kind
        return True, f"{type(e).__name__}: {e}"


def opk(fn, **kw):
    """Only the keyword arguments ``fn`` accepts (base compatibility)."""
    return {k: v for k, v in kw.items() if accepts(fn, k)}


def teach(w, raw=RAW, fix=FIX, app=APP):
    j = w.job(raw, app=app)
    out = w.learning.teach_correction(j["job_id"], fix)
    return j, out["candidate_id"]


def has_table(w, name):
    return w.one("SELECT 1 FROM sqlite_master WHERE type='table' AND"
                 " name=?", (name,)) is not None


def delta(w, cid):
    if not has_table(w, "learning_vocabulary_deltas"):
        return None
    row = w.one("SELECT delta_json FROM learning_vocabulary_deltas WHERE"
                " candidate_id=?", (cid,))
    return json.loads(row[0]) if row else None


def n_deltas(w):
    if not has_table(w, "learning_vocabulary_deltas"):
        return None
    return w.one("SELECT COUNT(*) FROM learning_vocabulary_deltas")[0]


def receipts(w, kind=None):
    if not has_table(w, "m14_operation_receipts"):
        return None
    if kind:
        return w.rows("SELECT operation_id, target_id, receipt_json FROM"
                      " m14_operation_receipts WHERE kind=?", (kind,))
    return w.rows("SELECT operation_id, kind, target_id FROM"
                  " m14_operation_receipts")


def norm(w, text, **ctx):
    """The real M05 snapshot/sandbox output under an explicit context."""
    from localflow.v2 import vocabulary as vocab_mod
    snap = vocab_mod.VocabularySnapshot(w.vocab.entries(),
                                        vocab_mod.ScopeContext(**ctx))
    return vocab_mod.sandbox_phrase(text, snap).get("output")


def raw_vocab(w):
    """Byte-level raw rows of the dictionary (entries and aliases)."""
    ents = {r[0]: r for r in w.rows(
        "SELECT * FROM vocabulary_entries ORDER BY entry_id")}
    als = {}
    for r in w.rows("SELECT * FROM vocabulary_aliases ORDER BY entry_id,"
                    " alias"):
        als.setdefault(r[0], []).append(r)
    return ents, als


def history(w, eid=None):
    if eid is None:
        return w.rows("SELECT * FROM vocabulary_history ORDER BY rowid")
    return w.rows("SELECT * FROM vocabulary_history WHERE entry_id=?"
                  " ORDER BY rowid", (eid,))


def aliases_of(w, eid):
    e = w.entries().get(eid)
    return {a: ok for a, ok in e[6]} if e else None


def active_rules(w, alias="modul"):
    """Enabled+approved entries holding ``alias`` approved (raw rows)."""
    return {eid: e for eid, e in w.entries().items()
            if e[3] and e[4] and any(a.lower() == alias and ok
                                     for a, ok in e[6])}


def status_of(w, cid):
    return w.one("SELECT status FROM learning_candidates WHERE"
                 " candidate_id=?", (cid,))[0]


def ce_json(w, cid):
    raw = w.candidate(cid)["counterexamples"]
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw


def sem(entries):
    """Semantic dictionary state without ids/revisions."""
    return sorted((c, sk, sv, en, ap, tuple(sorted(al)))
                  for c, sk, sv, en, ap, _rev, al in entries.values())


def user_entry(w, canonical="module", aliases=(("moduul", True),),
               scope_kind="app", scope_value=APP, enabled=True,
               approved=True):
    return w.vocab.add_entry(canonical, list(aliases),
                             scope_kind=scope_kind,
                             scope_value=scope_value if scope_kind !=
                             "global" else None,
                             enabled=enabled, approved=approved)


def add_user_alias(w, eid, alias):
    cur = w.vocab.entry(eid)
    w.vocab.update_entry(eid, aliases=[(a.alias, a.approved)
                                       for a in cur.aliases]
                         + [(alias, True)])


def db_text_hits(w, needle):
    hits = []
    for (table,) in w.rows("SELECT name FROM sqlite_master WHERE"
                           " type='table'"):
        for row in w.rows(f"SELECT * FROM {table}"):
            if any(isinstance(v, str) and needle in v for v in row):
                hits.append(table)
    return sorted(set(hits))


def file_hits(w, needle):
    out = []
    for p in w.tmp.rglob("*"):
        if p.is_file() and p.suffix not in (".db", ".db-wal", ".db-shm") \
                and not p.name.startswith("v2.db"):
            try:
                if needle.encode() in p.read_bytes():
                    out.append(p.name)
            except OSError:
                pass
    return out


def observe_and_mine(w, before, after, app=APP):
    j = w.job(before, app=app)
    w.observation(j["job_id"], before, after)
    w.learning.mine_observation_candidates()
    return j, w.rows("SELECT status, proposed_alias, proposed_canonical,"
                     " proposed_scope_kind, proposed_scope_value FROM"
                     " learning_candidates WHERE job_id=?", (j["job_id"],))


@contextlib.contextmanager
def entry_read_seam(w, target_eid, alias, state):
    """In-op seam (repaired tree): the FIRST ``entry_in`` read of
    ``target_eid`` while armed is followed, on the same writer
    connection, by the user's M05 edit adding ``alias``; the read
    returns the pre-edit entry (the read happened before the edit)."""
    if not hasattr(w.vocab, "entry_in"):
        yield
        return

    def factory(original):
        def entry_in(db, entry_id):
            got = original(db, entry_id)
            if state.get("armed") and not state.get("edited") \
                    and entry_id == target_eid and got is not None:
                st, _d, _e = w.vocab.update_entry_in(
                    db, entry_id, aliases=[(a.alias, a.approved)
                                           for a in got.aliases]
                    + [(alias, True)])
                state["edited"] = st == "ok"
                state["seam"] = "in_op_entry_in"
            return got
        return entry_in
    with patched(w.vocab, "entry_in", factory):
        yield


@contextlib.contextmanager
def between_ops_seam(w, at_op, action, state):
    """Base seam: after the ``at_op``-th waited writer op of the call."""
    def hook():
        state["ops"] = state.get("ops", 0) + 1
        if state.get("armed") and not state.get("edited") \
                and state["ops"] == at_op:
            action()
            state["edited"] = True
            state["seam"] = f"between_ops_after_op_{at_op}"
    with after_each_op(w.store, hook):
        yield


# ============================================================================
# approval
# ============================================================================

@drives("LF-M14-C073")
def c073_positive_new_entry(entry):
    with MWorld() as w:
        _j, cid = teach(w)
        safe = ("the modular plan works", "a model for the modulation")
        before_out = norm(w, RAW, app_bundle=APP)
        before_entries = len(w.entries())
        before_deltas = n_deltas(w)
        out = w.learning.approve(cid, counterexamples=safe,
                                 **opk(w.learning.approve,
                                       operation_id="op-c073"))
        ents = w.entries()
        d = delta(w, cid)
        ce = ce_json(w, cid)
        e = ents.get(out.get("entry_id"))
        obs = {"before": before_out == RAW, "entries": [before_entries,
                                                        len(ents)],
               "deltas": [before_deltas, n_deltas(w)],
               "action": out.get("action"),
               "delta_action": d and d.get("action"),
               "entry": e and list(e[:5]) + [e[6]],
               "ce": ce}
        return check({
            "pipeline_unchanged_before": before_out == RAW,
            "no_entry_before": before_entries == 0,
            "one_entry_after": len(ents) == 1 and e is not None,
            "entry_is_narrow": e is not None and e[:5] == (
                "module", "app", "com.synthetic.editor", True, True)
            and e[6] == [("modul", True)],
            "exactly_one_recorded_delta": n_deltas(w) == 1
            and d is not None and d.get("entry_id") == out.get("entry_id")
            and d.get("action") == "created" and d.get("alias") == "modul",
            "population_recorded": isinstance(ce, dict)
            and ce.get("tested") == 2 and ce.get("flips") == 0,
            "pipeline_changes_after": norm(w, RAW, app_bundle=APP) == FIX,
            "other_app_unchanged": norm(w, RAW, app_bundle=OTHER_APP) == RAW,
        }, obs, witness="LearningService.approve -> created; M05 snapshot"
           " before/after; learning_vocabulary_deltas row count")


@drives("LF-M14-C074")
def c074_preapproval_control(entry):
    with MWorld(min_words=5) as w:
        _j1, pend = teach(w)
        _j2, rej = teach(w, "send the kubernetis config now",
                         "send the kubernetes config now")
        w.learning.reject(rej)
        sampled = w.sampling.refresh(percent=100.0)
        prof = w.profile.compute()
        texts = (RAW, "send the kubernetis config now")
        ctxs = ({}, {"app_bundle": APP})
        outs = {(t, json.dumps(c)): norm(w, t, **c)
                for t in texts for c in ctxs}
        vocab_rows = w.one("SELECT COUNT(*) FROM vocabulary_entries")[0]
        statuses = [status_of(w, pend), status_of(w, rej)]
        # Positive companion: the explicit approval is what changes it.
        w.learning.approve(pend)
        after = norm(w, RAW, app_bundle=APP)
        after_rej = norm(w, texts[1], app_bundle=APP)
        return check({
            "states_as_built": statuses == ["pending", "rejected"],
            "baseline_everywhere": all(v == t for (t, _c), v in
                                       outs.items()),
            "no_vocabulary_rows": vocab_rows == 0,
            "approval_changes_output": after == FIX,
            "rejected_never_applies": after_rej == texts[1],
        }, {"statuses": statuses, "vocab_rows": vocab_rows,
            "sampled": bool(sampled), "profile": bool(prof),
            "after": after == FIX},
            witness="pending+rejected candidates after sampling.refresh and"
                    " profile.compute; M05 snapshot equals raw text;"
                    " service-level (normalize engine the coordinator uses)")


@drives("LF-M14-C075")
def c075_existing_user_entry(entry):
    with MWorld() as w:
        eid = user_entry(w)
        h_before = history(w, eid)
        _j, cid = teach(w)
        out = w.learning.approve(cid)
        ents = w.entries()
        h_after = history(w, eid)
        e = ents.get(eid)
        return check({
            "composed_into_user_entry": out.get("entry_id") == eid
            and out.get("action") == "alias_added",
            "one_entry": len(ents) == 1,
            "aliases": e is not None and sorted(e[6]) == [
                ("modul", True), ("moduul", True)],
            "ownership_kept": w.one("SELECT origin FROM vocabulary_entries"
                                    " WHERE entry_id=?", (eid,))[0]
            == "user",
            "history_retained": h_after[:len(h_before)] == h_before
            and len(h_after) == len(h_before) + 1,
            "user_alias_effective": norm(w, "the moduul today",
                                         app_bundle=APP)
            == "the module today",
            "learned_alias_effective": norm(w, RAW, app_bundle=APP) == FIX,
        }, {"action": out.get("action"), "entries": len(ents),
            "aliases": e and e[6], "history": [len(h_before),
                                               len(h_after)]},
            witness="approve composes alias_added onto user entry;"
                    " vocabulary_history prefix preserved")


def _already_present(w, pre_aliases):
    eid = user_entry(w, aliases=pre_aliases)
    _j, cid = teach(w)
    before = raw_vocab(w)
    out = w.learning.approve(cid)
    after_approve = raw_vocab(w)
    return eid, cid, out, before, after_approve


@drives("LF-M14-C076")
def c076_preexisting_alias(entry):
    with MWorld() as w:
        eid, cid, out, before, after_approve = _already_present(
            w, (("modul", True),))
        st_approved = status_of(w, cid)
        u_ref, u_out = refused(w.learning.undo_approval, cid)
        after_undo = raw_vocab(w)
        return check({
            "approval_ran": st_approved == "approved"
            and out.get("entry_id") == eid,
            "already_present": out.get("action") == "already_present",
            "no_duplicate_entry_or_alias": after_approve == before,
            "undo_ran": not u_ref and status_of(w, cid) == "pending",
            "undo_left_user_config": after_undo == before,
            "user_alias_effective": norm(w, RAW, app_bundle=APP) == FIX,
        }, {"action": out.get("action"), "undo": u_out,
            "rows_equal": [after_approve == before, after_undo == before]},
            witness="approve -> already_present; undo_approval; raw rows"
                    " byte-equal")


@drives("LF-M14-C077")
def c077_disabled_entry(entry):
    with MWorld() as w:
        eid = user_entry(w, enabled=False)
        _j, cid = teach(w)
        before = raw_vocab(w)
        ref, msg = refused(w.learning.approve, cid)
        after = raw_vocab(w)
        disabled_ok = ref and after == before \
            and status_of(w, cid) == "pending" \
            and norm(w, RAW, app_bundle=APP) == RAW \
            and norm(w, "the moduul today", app_bundle=APP) \
            == "the moduul today"
    with MWorld() as w2:  # same-shape eligible companion
        eid2 = user_entry(w2, enabled=True)
        _j, cid2 = teach(w2)
        out2 = w2.learning.approve(cid2)
        companion = out2.get("entry_id") == eid2 \
            and out2.get("action") == "alias_added" \
            and norm(w2, RAW, app_bundle=APP) == FIX
    return check({"disabled_not_enabled": disabled_ok,
                  "enabled_companion_composes": companion},
                 {"refused": msg if ref else None,
                  "companion_action": out2.get("action")},
                 witness="approve refuses existing_entry_not_active;"
                         " enabled twin -> alias_added")


def _scope_variant(pre_kind, pre_value, approve_kind, approve_value,
                   job_app=APP):
    with MWorld() as w:
        eid = user_entry(w, scope_kind=pre_kind, scope_value=pre_value)
        _j, cid = teach(w, app=job_app)
        kw = {} if approve_kind is None else {
            "scope_kind": approve_kind, "scope_value": approve_value}
        ref, out = refused(w.learning.approve, cid, **kw)
        ents = w.entries()
        return {"eid": eid, "refused": out if ref else None,
                "action": None if ref else out.get("action"),
                "into_existing": (not ref) and out.get("entry_id") == eid,
                "entries": sorted((e[1], e[2], tuple(sorted(e[6])))
                                  for e in ents.values()),
                "n": len(ents)}


@drives("LF-M14-C078")
def c078_equivalent_scope(entry):
    app = _scope_variant("app", APP, None, None,
                         job_app="  COM.Synthetic.Editor ")
    site = _scope_variant("site", SITE, "site",
                          "HTTPS://Docs.Synthetic.Example/")
    ws_pad = _scope_variant("workspace", "Alpha", "workspace", " Alpha ")
    ws_case = _scope_variant("workspace", "Alpha", "workspace", "alpha")
    pr_case = _scope_variant("profile", "Work", "profile", "work")
    return check({
        "app_case_padding_composes": app["into_existing"]
        and app["action"] == "alias_added" and app["n"] == 1
        and app["entries"] == [("app", "com.synthetic.editor",
                                (("modul", True), ("moduul", True)))],
        "site_equivalent_composes": site["into_existing"]
        and site["n"] == 1 and site["entries"][0][1] == SITE,
        "workspace_padding_composes": ws_pad["into_existing"]
        and ws_pad["n"] == 1,
        "workspace_case_is_distinct": not ws_case["into_existing"]
        and ws_case["action"] == "created" and ws_case["n"] == 2
        and ("workspace", "alpha", (("modul", True),))
        in ws_case["entries"],
        "profile_case_is_distinct": not pr_case["into_existing"]
        and pr_case["action"] == "created" and pr_case["n"] == 2,
        "never_broadened": all(k != "global" for v in (
            app, site, ws_pad, ws_case, pr_case)
            for k, _sv, _a in v["entries"]),
    }, {k: {"action": v["action"], "n": v["n"], "refused": v["refused"]}
        for k, v in (("app", app), ("site", site), ("ws_pad", ws_pad),
                     ("ws_case", ws_case), ("profile_case", pr_case))},
        witness="approve under case/padding-equivalent app/site keys"
                " composes; exact workspace/profile keys stay distinct")


def _revocation_run(kind):
    """One revocation kind through the between-ops seam (base window)
    plus both alternate serializations. Returns a grading dict."""
    out = {"kind": kind}
    with MWorld() as w:
        j, cid = teach(w)
        state = {"ops": 0, "fired": False}

        def revoke():
            if kind == "reject":
                refused(w.learning.reject, cid)
            else:
                w.store.delete_everywhere("job", j["job_id"])

        def hook():
            state["ops"] += 1
            if state["fired"]:
                return
            row = w.one("SELECT status, vocabulary_entry_id FROM"
                        " learning_candidates WHERE candidate_id=?",
                        (cid,))
            if row and row[0] == "pending" and row[1]:
                state["fired"] = True   # plan committed, effect pending
                revoke()
        akw = opk(w.learning.approve, operation_id=f"op-rev-{kind}")
        with after_each_op(w.store, hook):
            a_ref, a_out = refused(w.learning.approve, cid, **akw)
        out["seam_fired"] = state["fired"]
        out["approve_ops"] = state["ops"]
        if not state["fired"]:
            revoke()   # the revocation serialized AFTER the approval
        st = status_of(w, cid)
        rules = active_rules(w)
        out["status"] = st
        out["rules"] = len(rules)
        out["coherent"] = bool(rules) == (st == "approved")
        rc = receipts(w, "approve")
        if rc is not None and akw:
            out["receipt_ok"] = (not a_ref) and len(rc) == 1 \
                and rc[0][1] == cid and json.loads(rc[0][2]).get(
                    "entry_id") in rules
        else:
            out["receipt_ok"] = None
    with MWorld() as w:     # the revocation serialized BEFORE approval
        j, cid = teach(w)
        if kind == "reject":
            w.learning.reject(cid)
        else:
            w.store.delete_everywhere("job", j["job_id"])
        b_ref, b_msg = refused(w.learning.approve, cid)
        out["before_refused"] = b_ref
        out["before_no_rule"] = not active_rules(w) \
            and w.one("SELECT COUNT(*) FROM vocabulary_entries")[0] == 0
    with MWorld() as w:     # no revocation: the approval lands
        _j, cid = teach(w)
        w.learning.approve(cid)
        out["control_rule"] = len(active_rules(w)) == 1 \
            and status_of(w, cid) == "approved"
    return out


def _revocation_grade(entry_id):
    runs = [_revocation_run("reject"), _revocation_run("delete")]
    fired = any(r["seam_fired"] for r in runs)
    conds = {}
    for r in runs:
        k = r["kind"]
        conds[f"{k}_no_orphan_rule"] = r["coherent"]
        conds[f"{k}_first_refused_without_rule"] = r["before_refused"] \
            and r["before_no_rule"]
        conds[f"{k}_control_lands"] = r["control_rule"]
        if r["receipt_ok"] is not None:
            conds[f"{k}_coherent_receipt"] = r["receipt_ok"]
    if not fired and not all(r["approve_ops"] == 1 for r in runs):
        return invalid("between-ops seam never fired although approval"
                       " took more than one writer op", runs)
    witness = ("between-ops seam fired after the plan op" if fired else
               "approval is ONE writer op (op count 1): no plan/effect"
               " window exists; both serializations graded")
    return check(conds, runs, witness=witness,
                 grading="semantic" if fired else "structural")


@drives("LF-M14-C079", "LF-M14-S029")
def c079_s029_revocation_between_phases(entry):
    return _revocation_grade(entry["id"])


def _timeout_run(inject):
    with MWorld() as w:
        _j, cid = teach(w)
        akw = opk(w.learning.approve, operation_id="op-approve-s006")
        state = {"injected": False, "rev_at_commit": None}
        orig = w.store.submit

        def learned_now():
            return orig(lambda c: c.execute(
                "SELECT e.entry_id, e.revision FROM vocabulary_entries e"
                " JOIN vocabulary_aliases a ON a.entry_id=e.entry_id"
                " WHERE a.alias='modul' AND a.approved=1 AND"
                " e.enabled=1").fetchall())

        def submit(fn, wait=True, timeout=15.0):
            got = orig(fn, wait=wait, timeout=timeout)
            if inject and wait and not state["injected"]:
                now = learned_now()
                if now:
                    state["injected"] = True
                    state["rev_at_commit"] = now[0][1]
                    raise TimeoutError("store writer did not respond")
            return got
        w.store.submit = submit
        try:
            first_ref, first = refused(w.learning.approve, cid, **akw)
        finally:
            w.store.submit = orig
        after_first = w.entries()
        retry_ref, retry = refused(w.learning.approve, cid, **akw)
        ents = w.entries()
        rules = active_rules(w)
        eid = next(iter(rules), None)
        return {
            "injected": state["injected"],
            "first_timed_out": first_ref and "TimeoutError" in str(first),
            "first": None if first_ref else first.get("entry_id"),
            "retry_refused": retry if retry_ref else None,
            "retry_entry": None if retry_ref else retry.get("entry_id"),
            "one_entry": len(ents) == 1 and len(rules) == 1,
            "no_extra_effect": ents == after_first if inject else True,
            "rev_at_commit": state["rev_at_commit"],
            "rev_final": ents[eid][5] if eid else None,
            "alias_once": eid is not None and [a for a, _ in ents[eid][6]]
            == ["modul"],
            "status": status_of(w, cid), "eid": eid,
            "deltas": n_deltas(w),
            "receipts": None if receipts(w) is None else len(receipts(w)),
            "op_id": bool(akw),
            "effective": norm(w, RAW, app_bundle=APP) == FIX,
        }


@drives("LF-M14-C080", "LF-M14-S006")
def c080_s006_unknown_after_effect(entry):
    seam = _timeout_run(True)
    control = _timeout_run(False)
    if not seam["injected"]:
        return invalid("timeout seam never reached (no committed learned"
                       " alias observed after any writer op)", seam)
    return check({
        "caller_saw_timeout": seam["first_timed_out"],
        "retry_reconciles": seam["retry_refused"] is None
        and seam["retry_entry"] == seam["eid"],
        "one_logical_effect": seam["one_entry"] and seam["alias_once"]
        and seam["no_extra_effect"]
        and seam["rev_final"] == seam["rev_at_commit"],
        "candidate_approved": seam["status"] == "approved",
        "one_delta_one_receipt": seam["deltas"] == 1
        and (seam["receipts"] == 1 if seam["op_id"] else True),
        "effective": seam["effective"],
        # Control: no lost reply — one effect; a repeat either returns
        # the same receipt or refuses, never a second effect.
        "control_one_effect": control["one_entry"]
        and control["alias_once"] and control["status"] == "approved"
        and (control["retry_refused"] is not None
             or control["retry_entry"] == control["eid"]),
    }, {"seam": seam, "control": control},
        witness="store.submit returns TimeoutError after the op that"
                " committed the learned alias; retry with the same"
                " operation_id", grading="decision", decision=D12)


# ============================================================================
# undo
# ============================================================================

@drives("LF-M14-C081")
def c081_positive_created(entry):
    with MWorld() as w:
        other = w.vocab.add_entry("Kubernetes", [("cube earnest", True)],
                                  approved=True)
        _j, cid = teach(w)
        out = w.learning.approve(cid)
        eid = out.get("entry_id")
        rev_after = w.entries()[eid][5]
        other_before = raw_vocab(w)[0][other], raw_vocab(w)[1][other]
        u_ref, u_msg = refused(w.learning.undo_approval, cid)
        e = w.entries()[eid]
        d = delta(w, cid)
        other_after = raw_vocab(w)[0][other], raw_vocab(w)[1][other]
        return check({
            "undo_ran": not u_ref and status_of(w, cid) == "pending",
            "entry_disabled_only": e[3] is False and e[4] is True
            and e[6] == [("modul", True)] and e[5] == rev_after + 1,
            "pipeline_reverted": norm(w, RAW, app_bundle=APP) == RAW,
            "unrelated_entry_untouched": other_after == other_before
            and norm(w, "deploy cube earnest now")
            == "deploy Kubernetes now",
            "delta_records_undo": d is None or
            d.get("undo_revision") == rev_after + 1,
        }, {"undo": u_msg, "entry": list(e[:6]), "delta": d},
            witness="approve created -> undo_approval disables exactly the"
                    " created entry")


def _user_edit_then_undo(edit_first):
    with MWorld() as w:
        _j, cid = teach(w)
        eid = w.learning.approve(cid)["entry_id"]

        def user_edit():
            cur = w.vocab.entry(eid)
            w.vocab.update_entry(eid, canonical="modules",
                                 aliases=[(a.alias, a.approved)
                                          for a in cur.aliases]
                                 + [("moduel", True)])
        if edit_first:
            user_edit()
        u_ref, u_msg = refused(w.learning.undo_approval, cid)
        if not edit_first:
            user_edit()
        e = w.entries()[eid]
        return {"undo_refused": u_msg if u_ref else None,
                "enabled": e[3], "canonical": e[0],
                "aliases": sorted(e[6]),
                "user_alias_out": norm(w, "the moduel today",
                                       app_bundle=APP),
                "learned_out": norm(w, RAW, app_bundle=APP),
                "status": status_of(w, cid)}


def _undo_control():
    with MWorld() as w:
        _j, cid = teach(w)
        eid = w.learning.approve(cid)["entry_id"]
        u_ref, _m = refused(w.learning.undo_approval, cid)
        e = w.entries()[eid]
        return (not u_ref) and e[3] is False \
            and norm(w, RAW, app_bundle=APP) == RAW


@drives("LF-M14-C082", "LF-M14-S007")
def c082_s007_created_then_user_edit(entry):
    seam = _user_edit_then_undo(True)
    alt = _user_edit_then_undo(False)
    control = _undo_control()
    return check({
        "user_edits_preserved_or_refused": seam["enabled"] is True
        and seam["canonical"] == "modules"
        and ("moduel", True) in seam["aliases"]
        and seam["user_alias_out"] == "the modules today",
        "stale_reversal_refused": seam["undo_refused"] is not None
        and "user_modified_since_approval" in seam["undo_refused"],
        "alternate_order_keeps_user_edit": alt["undo_refused"] is None
        and alt["canonical"] == "modules"
        and ("moduel", True) in alt["aliases"],
        "control_undo_reverts": control,
    }, {"seam": seam, "alt": alt, "control": control},
        witness="approve created; user edits canonical+alias after"
                " completion; undo_approval", grading="decision",
        decision=D12)


@drives("LF-M14-C083")
def c083_alias_added_then_user_alias(entry):
    with MWorld() as w:
        eid = user_entry(w)
        _j, cid = teach(w)
        out = w.learning.approve(cid)
        add_user_alias(w, eid, "modyul")
        u_ref, u_msg = refused(w.learning.undo_approval, cid)
        al = aliases_of(w, eid)
        return check({
            "alias_added": out.get("action") == "alias_added",
            "undo_ran": not u_ref,
            "only_learned_removed": al == {"moduul": True, "modyul": True},
            "learned_not_effective": norm(w, RAW, app_bundle=APP) == RAW,
            "user_aliases_effective": norm(w, "the modyul today",
                                           app_bundle=APP)
            == "the module today" and norm(w, "the moduul today",
                                           app_bundle=APP)
            == "the module today",
        }, {"action": out.get("action"), "undo": u_msg, "aliases": al},
            witness="approve alias_added; user adds alias; undo removes"
                    " only the learned alias")


def _concurrent_undo(mode):
    """mode: 'seam' (user alias lands after undo reads the entry),
    'before' (user alias before undo), 'none' (no user action)."""
    with MWorld() as w:
        eid = user_entry(w)
        _j, cid = teach(w)
        out = w.learning.approve(cid)
        state = {}
        if mode == "before":
            add_user_alias(w, eid, "modyul")
        with contextlib.ExitStack() as stack:
            if mode == "seam":
                stack.enter_context(entry_read_seam(w, eid, "modyul",
                                                    state))
                stack.enter_context(between_ops_seam(
                    w, 2, lambda: add_user_alias(w, eid, "modyul"),
                    state))
                state["armed"] = True
            first_ref, first = refused(w.learning.undo_approval, cid)
            state["armed"] = False
        retry = None
        if first_ref and mode == "seam":
            r_ref, r = refused(w.learning.undo_approval, cid)
            retry = r if r_ref else "ok"
        return {"action": out.get("action"), "seam": state.get("seam"),
                "edited": state.get("edited", mode == "before"),
                "first": first if first_ref else "ok", "retry": retry,
                "aliases": aliases_of(w, eid),
                "modyul_out": norm(w, "the modyul today", app_bundle=APP),
                "modul_out": norm(w, RAW, app_bundle=APP)}


@drives("LF-M14-C084", "LF-M14-S031")
def c084_s031_concurrent_alias_during_undo(entry):
    seam = _concurrent_undo("seam")
    before = _concurrent_undo("before")
    none = _concurrent_undo("none")
    if not seam["edited"]:
        return invalid("undo read/update seam never reached", seam)
    final_ok = {"moduul": True, "modyul": True}
    return check({
        "no_lost_user_alias": seam["aliases"] is not None
        and seam["aliases"].get("modyul") is True
        and seam["aliases"].get("moduul") is True
        and seam["modyul_out"] == "the module today",
        "cas_refusal_or_merge": seam["first"] == "ok"
        or "stale" in seam["first"]
        or "user_modified_since_approval" in seam["first"],
        "reconciled_to_narrow_delta": seam["aliases"] == final_ok
        and seam["modul_out"] == RAW,
        "control_before_order": before["first"] == "ok"
        and before["aliases"] == final_ok,
        "control_no_action": none["first"] == "ok"
        and none["aliases"] == {"moduul": True},
    }, {"seam": seam, "before": before, "none": none},
        witness=f"seam {seam['seam']}: user M05 alias edit between undo's"
                " entry read and its update; retry undo after CAS refusal")


@drives("LF-M14-C085")
def c085_preexisting_approved_alias(entry):
    # (a) approved user alias (case variant) -> already_present; user adds
    # another alias afterwards; undo must leave all user configuration.
    with MWorld() as w:
        eid, cid, out, before, _aa = _already_present(
            w, (("Modul", True),))
        add_user_alias(w, eid, "moduel")
        mid = raw_vocab(w)
        u_ref, u_msg = refused(w.learning.undo_approval, cid)
        a = {"action": out.get("action"), "undo": u_msg if u_ref else "ok",
             "unchanged": raw_vocab(w) == mid,
             "enabled": w.entries()[eid][3],
             "effective": norm(w, RAW, app_bundle=APP) == FIX}
    # (b) unapproved user alias -> alias_approved; undo returns it to
    # unapproved but never deletes the user's row or the entry.
    with MWorld() as w:
        eid = user_entry(w, aliases=(("moduul", True), ("modul", False)))
        _j, cid = teach(w)
        out = w.learning.approve(cid)
        approved_mid = aliases_of(w, eid)
        u_ref, u_msg = refused(w.learning.undo_approval, cid)
        b = {"action": out.get("action"), "undo": u_msg if u_ref else "ok",
             "mid": approved_mid, "after": aliases_of(w, eid),
             "enabled": w.entries()[eid][3]}
    return check({
        "a_already_present": a["action"] == "already_present",
        "a_undo_ran_and_changed_nothing": a["undo"] == "ok"
        and a["unchanged"] and a["enabled"] is True and a["effective"],
        "b_alias_approved_then_restored": b["action"] == "alias_approved"
        and b["mid"] == {"moduul": True, "modul": True}
        and b["undo"] == "ok"
        and b["after"] == {"moduul": True, "modul": False}
        and b["enabled"] is True,
    }, {"a": a, "b": b},
        witness="already_present and alias_approved deltas undone")


def _undo_reapprove(with_user_entry):
    with MWorld() as w:
        eid0 = user_entry(w) if with_user_entry else None
        _j, cid = teach(w)
        first = w.learning.approve(cid)
        s1 = w.entries()
        h1 = history(w)
        w.learning.undo_approval(cid)
        s2 = w.entries()
        again = w.learning.approve(cid)
        s3 = w.entries()
        h3 = history(w)
        eid = first.get("entry_id")
        return {"eid0": eid0, "first": first.get("action"),
                "again": again.get("action"),
                "same_entry": again.get("entry_id") == eid,
                "sem_equal": sem(s1) == sem(s3),
                "undo_changed": sem(s2) != sem(s1),
                "n": [len(s1), len(s3)],
                "aliases": s3[eid][6],
                "dup_alias": len({a.lower() for a, _ in s3[eid][6]})
                != len(s3[eid][6]),
                "history_append_only": h3[:len(h1)] == h1
                and len(h3) > len(h1),
                "deltas": n_deltas(w),
                "effective": norm(w, RAW, app_bundle=APP) == FIX}


@drives("LF-M14-C086")
def c086_undo_reapprove(entry):
    c = _undo_reapprove(False)
    a = _undo_reapprove(True)
    return check({
        "created_same_config": c["first"] == "created"
        and c["again"] == "created" and c["same_entry"] and c["sem_equal"]
        and c["n"] == [1, 1] and c["aliases"] == [("modul", True)],
        "alias_same_config": a["first"] == "alias_added"
        and a["again"] == "alias_added" and a["same_entry"]
        and a["sem_equal"] and a["n"] == [1, 1]
        and sorted(a["aliases"]) == [("modul", True), ("moduul", True)],
        "no_duplicate_aliases": not c["dup_alias"] and not a["dup_alias"],
        "effective": c["effective"] and a["effective"],
        "undo_took_effect": c["undo_changed"] and a["undo_changed"],
    }, {"created": c, "alias": a},
        witness="approve -> undo -> approve for created and alias_added")


@drives("LF-M14-C087")
def c087_manual_disable_before_reapprove(entry):
    # (a) approve -> undo -> user re-enables then disables -> reapprove.
    with MWorld() as w:
        _j, cid = teach(w)
        eid = w.learning.approve(cid)["entry_id"]
        w.learning.undo_approval(cid)
        w.vocab.set_enabled(eid, True)
        w.vocab.set_enabled(eid, False)
        ref_a, msg_a = refused(w.learning.approve, cid)
        a = {"refused": msg_a if ref_a else None,
             "enabled": w.entries()[eid][3],
             "out": norm(w, RAW, app_bundle=APP)}
    # (b) approve -> user disables the learned entry -> undo -> retry.
    with MWorld() as w:
        _j, cid = teach(w)
        eid = w.learning.approve(cid)["entry_id"]
        w.vocab.set_enabled(eid, False)
        u_ref, u_msg = refused(w.learning.undo_approval, cid)
        r_ref, r_msg = refused(w.learning.approve, cid)
        b = {"undo": u_msg if u_ref else "ok",
             "retry": r_msg if r_ref else "ok",
             "enabled": w.entries()[eid][3],
             "out": norm(w, RAW, app_bundle=APP)}
    # companion: untouched undo -> reapprove re-enables.
    with MWorld() as w:
        _j, cid = teach(w)
        eid = w.learning.approve(cid)["entry_id"]
        w.learning.undo_approval(cid)
        c_ref, c_msg = refused(w.learning.approve, cid)
        c = {"refused": c_msg if c_ref else None,
             "enabled": w.entries()[eid][3],
             "out": norm(w, RAW, app_bundle=APP)}
    return check({
        "a_no_covert_reactivation": a["refused"] is not None
        and "existing_entry_not_active" in a["refused"]
        and a["enabled"] is False and a["out"] == RAW,
        "b_no_covert_reactivation": b["enabled"] is False
        and b["out"] == RAW,
        "companion_reapprove_reenables": c["refused"] is None
        and c["enabled"] is True and c["out"] == FIX,
    }, {"a": a, "b": b, "companion": c},
        witness="user disable/edit of the learned entry before a later"
                " approval; untouched twin re-enables", grading="decision",
        decision=D12)


# ============================================================================
# counterexamples
# ============================================================================

@drives("LF-M14-C088")
def c088_positive_actual_flip(entry):
    with MWorld() as w:
        _j, cid = teach(w)
        out = w.learning.approve(cid, counterexamples=(ADVERSE,))
        blocked = {"entry_id": out.get("entry_id"),
                   "flips": len(out.get("flips") or []),
                   "entries": len(w.entries()),
                   "status": status_of(w, cid),
                   "out": norm(w, RAW, app_bundle=APP)}
    with MWorld() as w:
        _j, cid = teach(w)
        out2 = w.learning.approve(cid,
                                  counterexamples=("keep the model here",))
        comp = {"entry_id": bool(out2.get("entry_id")),
                "flips": len(out2.get("flips") or []),
                "out": norm(w, RAW, app_bundle=APP)}
    return check({
        "refused_on_flip": blocked["entry_id"] is None
        and blocked["flips"] == 1,
        "no_rule_landed": blocked["entries"] == 0
        and blocked["status"] == "pending" and blocked["out"] == RAW,
        "companion_approves": comp["entry_id"] and comp["flips"] == 0
        and comp["out"] == FIX,
    }, {"blocked": blocked, "companion": comp},
        witness="approve(counterexamples) with an in-scope alias boundary"
                " phrase vs a non-matching twin")


@drives("LF-M14-C089")
def c089_safe_populated(entry):
    safe = ("the modular plan works", "a model for the modulation")
    with MWorld() as w:
        _j, cid = teach(w)
        out = w.learning.approve(cid, counterexamples=safe)
        ce = ce_json(w, cid)
        aid = ce.get("artifact_id") if isinstance(ce, dict) else None
        art = w.artifact_row(aid) if aid else None
        body = json.loads(art[3]) if art and art[3] else None
        return check({
            "approved": bool(out.get("entry_id")),
            "population_recorded": isinstance(ce, dict)
            and ce.get("tested") == 2 and ce.get("flips") == 0,
            "status_is_no_flips_not_safe": isinstance(ce, dict)
            and ce.get("status") == "no_flips",
            "population_in_governed_artifact": body is not None
            and body.get("tested") == 2 and body.get("flips") == []
            and art[1] == "counterexample_result",
            "phrases_really_unaffected": all(
                norm(w, p, app_bundle=APP) == p for p in safe),
            "rule_active": norm(w, RAW, app_bundle=APP) == FIX,
        }, {"ce": ce, "artifact_role": art and art[1]},
            witness="approve with 2 phrases without the alias token;"
                    " content-free row + governed artifact")


@drives("LF-M14-C090")
def c090_empty(entry):
    with MWorld() as w:
        _j, cid = teach(w)
        out = w.learning.approve(cid)
        ce = ce_json(w, cid)
        return check({
            "explicit_approval_proceeds": bool(out.get("entry_id"))
            and status_of(w, cid) == "approved",
            "untested_not_safe": isinstance(ce, dict)
            and ce.get("status") == "untested" and ce.get("tested") == 0,
            "no_artifact_for_no_population": isinstance(ce, dict)
            and ce.get("artifact_id") is None,
            "rule_active": norm(w, RAW, app_bundle=APP) == FIX,
        }, {"ce": ce}, witness="approve with no counterexamples",
            grading="decision", decision=D06)


def _ce_scope(pre, approve_kw, phrase=ADVERSE):
    """pre: (canonical, alias, scope_kind, scope_value) user entry."""
    with MWorld() as w:
        if pre:
            user_entry(w, canonical=pre[0], aliases=((pre[1], True),),
                       scope_kind=pre[2], scope_value=pre[3])
        _j, cid = teach(w)
        out = w.learning.approve(cid, counterexamples=(phrase,),
                                 **approve_kw)
        ce = ce_json(w, cid)
        flips = len(out.get("flips") or [])
        if flips:   # the explicit choice anyway, to read the real effect
            w.learning.approve(cid, **approve_kw)
        return {"flips": flips, "scope": ce.get("scope")
                if isinstance(ce, dict) else None, "w_out": {
                    k: norm(w, phrase, **ctx) for k, ctx in (
                        ("app", {"app_bundle": APP}),
                        ("other_app", {"app_bundle": OTHER_APP}),
                        ("site", {"site_origin": SITE}),
                        ("other_site", {"site_origin": OTHER_SITE}))}}


@drives("LF-M14-C091")
def c091_scope_app_site(entry):
    moved = "keep the module here"
    a_out = _ce_scope(("modal", "modul", "app", OTHER_APP), {})
    a_in = _ce_scope(("modal", "modul", "app", APP), {})
    s_kw = {"scope_kind": "site", "scope_value": SITE}
    s_out = _ce_scope(("modal", "modul", "site", OTHER_SITE), s_kw)
    s_in = _ce_scope(("modal", "modul", "site", SITE), s_kw)
    return check({
        "app_out_of_scope_entry_ignored": a_out["flips"] == 1
        and a_out["scope"] == ["app", "com.synthetic.editor"]
        and a_out["w_out"]["app"] == moved
        and a_out["w_out"]["other_app"] == "keep the modal here",
        "app_in_scope_entry_counts": a_in["flips"] == 0
        and a_in["w_out"]["app"] != moved,
        "site_out_of_scope_entry_ignored": s_out["flips"] == 1
        and s_out["scope"] == ["site", SITE]
        and s_out["w_out"]["site"] == moved
        and s_out["w_out"]["other_site"] == "keep the modal here"
        and s_out["w_out"]["app"] == ADVERSE,
        "site_in_scope_entry_counts": s_in["flips"] == 0
        and s_in["w_out"]["site"] != moved,
    }, {"app_out": a_out, "app_in": a_in, "site_out": s_out,
        "site_in": s_in},
        witness="counterexample check vs real post-approval snapshot in"
                " matching/nonmatching app and site contexts")


@drives("LF-M14-C092")
def c092_scope_workspace_profile(entry):
    res = {}
    for kind, key, other, field in (("workspace", "Alpha", "alpha",
                                     "workspace"),
                                    ("profile", "Work", "work", "profile")):
        with MWorld() as w:
            w.vocab.add_entry("modal", [("modul", True)], approved=True)
            _j, cid = teach(w)
            kw = {"scope_kind": kind, "scope_value": key}
            out = w.learning.approve(cid, counterexamples=(ADVERSE,), **kw)
            ce = ce_json(w, cid)
            w.learning.approve(cid, **kw)
            res[kind] = {
                "flips": len(out.get("flips") or []),
                "scope": ce.get("scope") if isinstance(ce, dict) else None,
                "in": norm(w, ADVERSE, **{field: key}),
                "other": norm(w, ADVERSE, **{field: other}),
                "none": norm(w, ADVERSE)}
    ok = {}
    for kind, key in (("workspace", "Alpha"), ("profile", "Work")):
        r = res[kind]
        ok[f"{kind}_flip_in_exact_scope"] = r["flips"] == 1 \
            and r["scope"] == [kind, key]
        ok[f"{kind}_masks_broader_entry"] = r["in"] == \
            "keep the module here"
        ok[f"{kind}_exact_key_other_spelling_global"] = r["other"] == \
            "keep the modal here" and r["none"] == "keep the modal here"
    return check(ok, res, witness="global 'modal' entry masked by the"
                 " workspace/profile rule only in the exact key")


@drives("LF-M14-C093")
def c093_composition(entry):
    longer = "we open modul today again"
    plain = "the modul broke"
    with MWorld() as w:    # (a) a longer existing alias consumes the phrase
        w.vocab.add_entry("Moodle Today", [("modul today", True)],
                          approved=True)
        _j, cid = teach(w)
        rev = int(w.one("SELECT value FROM vocabulary_meta WHERE"
                        " key='revision'")[0])
        out = w.learning.approve(cid, counterexamples=(longer,))
        ce = ce_json(w, cid)
        a = {"flips": len(out.get("flips") or []),
             "approved": bool(out.get("entry_id")),
             "rev": [rev, ce.get("snapshot_revision")
                     if isinstance(ce, dict) else None],
             "longer": norm(w, longer, app_bundle=APP),
             "plain": norm(w, plain, app_bundle=APP)}
    with MWorld() as w:    # (b) same dictionary, a phrase that does flip
        w.vocab.add_entry("Moodle Today", [("modul today", True)],
                          approved=True)
        _j, cid = teach(w)
        out = w.learning.approve(cid, counterexamples=(longer, plain))
        b = {"flips": [f.get("phrase") for f in out.get("flips") or []],
             "entries": len(w.entries())}
    with MWorld() as w:    # (c) merged into the user's existing identity
        eid = user_entry(w)
        _j, cid = teach(w)
        rows = raw_vocab(w)
        out = w.learning.approve(cid, counterexamples=(plain,))
        c = {"flips": len(out.get("flips") or []),
             "unchanged": raw_vocab(w) == rows,
             "aliases": aliases_of(w, eid)}
    return check({
        "effective_snapshot_no_vacuous_flip": a["flips"] == 0
        and a["approved"],
        "prediction_matches_real_snapshot": a["longer"]
        == "we open Moodle Today again"
        and a["plain"] == "the module broke",
        "snapshot_revision_recorded": a["rev"][0] == a["rev"][1],
        "population_still_detects_flip": b["flips"] == [plain]
        and b["entries"] == 1,
        "merged_identity_checked": c["flips"] == 1 and c["unchanged"]
        and c["aliases"] == {"moduul": True},
    }, {"a": a, "b": b, "c": c},
        witness="counterexample check over existing longer alias and"
                " merged user identity")


@drives("LF-M14-C094")
def c094_private_phrase_deletion(entry):
    phrase = f"keep the modul named {PRIVATE_CANARY} here"
    with MWorld() as w:
        j, cid = teach(w)
        out = w.learning.approve(cid, counterexamples=(phrase,))
        row = w.one("SELECT * FROM learning_candidates WHERE"
                    " candidate_id=?", (cid,))
        in_row = sum(1 for v in row if isinstance(v, str)
                     and PRIVATE_CANARY in v)
        in_events = PRIVATE_CANARY in json.dumps(w.events, default=str)
        governed = w.rows(
            "SELECT a.artifact_id, a.job_id FROM artifacts a WHERE"
            " a.role='counterexample_result' AND a.purged=0")
        governed_has = [aid for aid, _job in governed
                        if PRIVATE_CANARY in (w.artifact_row(aid)[3] or "")]
        leased = [w.one("SELECT COUNT(*) FROM artifact_leases WHERE"
                        " artifact_id=? AND expires_at_utc IS NOT NULL AND"
                        " revoked_at_utc IS NULL", (aid,))[0]
                  for aid in governed_has]
        w.store.delete_everywhere("job", j["job_id"])
        remaining = db_text_hits(w, PRIVATE_CANARY)
        files = file_hits(w, PRIVATE_CANARY)
        return check({
            "flip_recorded": len(out.get("flips") or []) == 1,
            "phrase_only_in_governed_artifact": len(governed_has) == 1
            and all(job == j["job_id"] for _a, job in governed)
            and leased == [1],
            "row_content_free": in_row == 0,
            "events_content_free": not in_events,
            "gone_after_deletion": not remaining and not files,
        }, {"governed": len(governed_has), "in_row": in_row,
            "in_events": in_events, "remaining_tables": remaining,
            "files": len(files)},
            witness="blocked approval with a canary phrase, then"
                    " delete_everywhere(job)")


# ============================================================================
# suppression
# ============================================================================

def _rejected_world(w):
    _j, cid = teach(w)
    w.learning.reject(cid)
    return cid


@drives("LF-M14-C095")
def c095_positive_new_pair(entry):
    with MWorld() as w:
        _rejected_world(w)
        _j, diff = observe_and_mine(w, RAW, "please check the modal today")
        _j, new = observe_and_mine(w, "send the kubernetis config now",
                                   "send the kubernetes config now")
        _j, same = observe_and_mine(w, RAW, FIX)
        return check({
            "different_canonical_pending": [r[:3] for r in diff]
            == [("pending", "modul", "modal")],
            "new_pair_pending": [r[:3] for r in new]
            == [("pending", "kubernetis", "kubernetes")],
            "suppression_active_companion": [r[0] for r in same]
            == ["suppressed"],
        }, {"diff": diff, "new": new, "same": same},
            witness="reject modul->module then mine unrelated pairs")


@drives("LF-M14-C096")
def c096_same_exact_pair(entry):
    with MWorld() as w:
        _j, first = observe_and_mine(w, RAW, FIX)
        (cid,) = w.one("SELECT candidate_id FROM learning_candidates WHERE"
                       " status='pending'")
        w.learning.reject(cid)
        repeats = [observe_and_mine(w, RAW, FIX)[1] for _ in range(6)]
        pending = w.learning.candidates(status="pending")
        return check({
            "fixture_mineable": [r[0] for r in first] == ["pending"],
            "all_repeats_suppressed": [r[0] for rs in repeats for r in rs]
            == ["suppressed"] * 6,
            "no_pending_reappearance": pending == [] and w.one(
                "SELECT COUNT(*) FROM learning_candidates WHERE"
                " status='pending'")[0] == 0,
        }, {"first": first, "repeats": [r[0][0] if r else None
                                        for r in repeats]},
            witness="mined pair rejected then observed 6 more times")


@drives("LF-M14-C097")
def c097_case_equivalent(entry):
    variants = (("please check the Modul today",
                 "please check the Module today"),
                ("please check the MODUL today",
                 "please check the MODULE today"),
                (RAW, "please check the MODULE today"),
                ("please check the Modul today", FIX))
    with MWorld() as w:
        _rejected_world(w)
        got = [observe_and_mine(w, b, a)[1] for b, a in variants]
        _j, comp = observe_and_mine(w, RAW, "please check the modal today")
        return check({
            "case_variants_suppressed": [r[0][0] if r else None
                                         for r in got]
            == ["suppressed"] * 4,
            "variants_really_proposed": all(r and r[0][1] for r in got),
            "different_canonical_companion_pending": [r[0] for r in comp]
            == ["pending"],
        }, {"variants": [r[0][:3] if r else None for r in got],
            "companion": comp},
            witness="reject modul->module; mine case variants",
            grading="decision", decision=D05)


@drives("LF-M14-C098")
def c098_different_scope(entry):
    with MWorld() as w:
        _rejected_world(w)
        _j, other = observe_and_mine(w, RAW, FIX, app=OTHER_APP)
        _j, comp = observe_and_mine(w, "send the kubernetis config now",
                                    "send the kubernetes config now",
                                    app=OTHER_APP)
        return check({
            "other_scope_really_other": other and other[0][3:] == (
                "app", OTHER_APP),
            "global_suppression": [r[0] for r in other] == ["suppressed"],
            "companion_pending_in_other_scope": [r[0] for r in comp]
            == ["pending"],
        }, {"other": other, "comp": comp},
            witness="rejected in com.synthetic.editor; same pair mined in"
                    " com.synthetic.other", grading="decision",
            decision=D05)


@drives("LF-M14-C099")
def c099_different_canonical(entry):
    with MWorld() as w:
        _rejected_world(w)
        _j, diff = observe_and_mine(w, RAW, "please check the modal today")
        _j, same = observe_and_mine(w, RAW, FIX)
        cid = w.one("SELECT candidate_id FROM learning_candidates WHERE"
                    " status='pending'")[0]
        out = w.learning.approve(cid)
        return check({
            "different_canonical_pending": [r[:3] for r in diff]
            == [("pending", "modul", "modal")],
            "exact_pair_still_suppressed": [r[0] for r in same]
            == ["suppressed"],
            "different_canonical_approvable": out.get("action")
            == "created"
            and norm(w, RAW, app_bundle=APP)
            == "please check the modal today",
        }, {"diff": diff, "same": same, "action": out.get("action")},
            witness="reject modul->module; mine modul->modal")


@drives("LF-M14-C100")
def c100_pair_only_privacy(entry):
    obs_canary = "OBSERVED_CANARY_83"
    before = f"please check the modul today for {obs_canary}"
    after = f"please check the module today for {obs_canary}"
    with MWorld() as w:
        j, rows = observe_and_mine(w, before, after)
        (cid,) = w.one("SELECT candidate_id FROM learning_candidates WHERE"
                       " job_id=? AND status='pending'", (j["job_id"],))
        blocked = w.learning.approve(
            cid, counterexamples=(f"keep the modul named"
                                  f" {PRIVATE_CANARY} here",))
        present_before = (db_text_hits(w, obs_canary),
                          db_text_hits(w, PRIVATE_CANARY))
        w.learning.reject(cid)
        w.store.delete_everywhere("job", j["job_id"])
        pref = w.one("SELECT status, proposed_alias, proposed_canonical"
                     " FROM learning_candidates WHERE candidate_id=?",
                     (cid,))
        gone = (db_text_hits(w, obs_canary), db_text_hits(w, PRIVATE_CANARY),
                file_hits(w, obs_canary), file_hits(w, PRIVATE_CANARY))
        _j2, again = observe_and_mine(w, RAW, FIX)
        return check({
            "fixture_had_text": bool(present_before[0])
            and bool(present_before[1])
            and len(blocked.get("flips") or []) == 1,
            "pair_preference_retained": pref == ("rejected", "modul",
                                                 "module"),
            "no_observation_or_counterexample_text": not any(gone),
            "preference_still_suppresses": [r[0] for r in again]
            == ["suppressed"],
        }, {"pref": pref, "remaining": gone,
            "before": present_before},
            witness="mined observation + blocked counterexample, reject,"
                    " delete_everywhere(job), mine again",
            grading="decision", decision=D05)


# ============================================================================
# stateful probes (S005; S006/S007/S029/S031 share case scenarios above)
# ============================================================================

def _approve_against_user_entry(mode):
    with MWorld() as w:
        eid = user_entry(w)
        _j, cid = teach(w)
        state = {}
        if mode == "before":
            add_user_alias(w, eid, "modyul")
        with contextlib.ExitStack() as stack:
            if mode == "seam":
                stack.enter_context(entry_read_seam(w, eid, "modyul",
                                                    state))
                stack.enter_context(between_ops_seam(
                    w, 2, lambda: add_user_alias(w, eid, "modyul"),
                    state))
                state["armed"] = True
            f_ref, first = refused(w.learning.approve, cid)
            state["armed"] = False
        retry = None
        if f_ref and mode == "seam":
            r_ref, r = refused(w.learning.approve, cid)
            retry = r if r_ref else r.get("action")
        d = delta(w, cid)
        ents = w.entries()
        u_ref, u_msg = refused(w.learning.undo_approval, cid)
        return {"seam": state.get("seam"),
                "edited": state.get("edited", mode == "before"),
                "first": first if f_ref else first.get("action"),
                "retry": retry, "n": len(ents),
                "aliases": aliases_of(w, eid) if u_ref else None,
                "after_approve": {a: ok for a, ok in ents[eid][6]},
                "delta": d and [d.get("action"), d.get("alias")],
                "undo": u_msg if u_ref else "ok",
                "after_undo": aliases_of(w, eid)}


@drives("LF-M14-S005")
def s005_approval_against_existing_user_entry(entry):
    seam = _approve_against_user_entry("seam")
    none = _approve_against_user_entry("none")
    before = _approve_against_user_entry("before")
    if not seam["edited"]:
        return invalid("approval plan-read seam never reached", seam)
    three = {"moduul": True, "modyul": True, "modul": True}
    return check({
        "narrow_alias_delta_after_seam": seam["after_approve"] == three
        and seam["n"] == 1
        and (seam["delta"] is None
             or seam["delta"] == ["alias_added", "modul"]),
        "cas_or_merge": seam["first"] == "alias_added"
        or (("stale" in str(seam["first"]))
            and seam["retry"] == "alias_added"),
        "undo_reverses_only_learned": seam["undo"] == "ok"
        and seam["after_undo"] == {"moduul": True, "modyul": True},
        "control_no_action": none["first"] == "alias_added"
        and none["after_approve"] == {"moduul": True, "modul": True}
        and none["after_undo"] == {"moduul": True},
        "control_user_edit_first": before["first"] == "alias_added"
        and before["after_approve"] == three
        and before["after_undo"] == {"moduul": True, "modyul": True},
    }, {"seam": seam, "none": none, "before": before},
        witness=f"seam {seam['seam']}: user M05 alias edit after the"
                " approval plan read the existing entry")


# ============================================================================
# metamorphic relations
# ============================================================================

@drives("LF-M14-MR001")
def mr001_approval_locality(entry):
    texts = (RAW, "deploy cube earnest now", "run terra form plan",
             "send caf ka event")
    ctxs = {"none": {}, "app": {"app_bundle": APP},
            "other_app": {"app_bundle": OTHER_APP},
            "ws": {"workspace": "Alpha"}}
    with MWorld() as w:
        w.vocab.add_entry("Kubernetes", [("cube earnest", True)],
                          approved=True)
        user_entry(w, canonical="module", aliases=(("modul", True),),
                   scope_kind="app", scope_value=OTHER_APP)
        user_entry(w, canonical="Terraform", aliases=(("terra form",
                                                        True),),
                   scope_kind="workspace", scope_value="Alpha")
        user_entry(w, canonical="Kafka", aliases=(("caf ka", True),))
        _j, cid = teach(w)
        e0, a0 = raw_vocab(w)
        out0 = {(t, k): norm(w, t, **c) for t in texts
                for k, c in ctxs.items()}
        res = w.learning.approve(cid)
        e1, a1 = raw_vocab(w)
        out1 = {(t, k): norm(w, t, **c) for t in texts
                for k, c in ctxs.items()}
        d = delta(w, cid)
        eid = res.get("entry_id")
        changed = sorted(k for k in out0 if out0[k] != out1[k])
        return check({
            "only_delta_entry_new": set(e1) - set(e0) == {eid}
            and (d is None or d.get("entry_id") == eid),
            "unrelated_entries_byte_equal": all(e1[k] == e0[k] for k in e0)
            and all(a1.get(k) == a0.get(k) for k in e0),
            "only_dependent_output_changed": changed == [(RAW, "app")]
            and out1[(RAW, "app")] == FIX,
        }, {"changed": changed, "entries": [len(e0), len(e1)]},
            witness="4 unrelated entries in 4 scopes; 16 text x context"
                    " outputs before/after approve")


@drives("LF-M14-MR002")
def mr002_undo_and_reapproval(entry):
    c = _undo_reapprove(False)
    a = _undo_reapprove(True)
    return check({
        "created_returns_to_same_state": c["sem_equal"] and c["same_entry"]
        and c["n"] == [1, 1] and not c["dup_alias"],
        "alias_returns_to_same_state": a["sem_equal"] and a["same_entry"]
        and a["n"] == [1, 1] and not a["dup_alias"],
        "history_append_only": c["history_append_only"]
        and a["history_append_only"],
        "undo_really_ran": c["undo_changed"] and a["undo_changed"],
    }, {"created": c, "alias": a},
        witness="approve -> undo -> approve; vocabulary_history prefix")


def _mr013_world(kind, pre_value, approve_value=None, job_app=APP):
    with MWorld() as w:
        user_entry(w, scope_kind=kind, scope_value=pre_value)
        _j, cid = teach(w, app=job_app)
        kw = {} if approve_value is None else {
            "scope_kind": kind, "scope_value": approve_value}
        ref, out = refused(w.learning.approve, cid, **kw)
        ctxs = (("app", {"app_bundle": APP}),
                ("app_upper", {"app_bundle": "COM.SYNTHETIC.EDITOR"}),
                ("other_app", {"app_bundle": OTHER_APP}),
                ("site", {"site_origin": SITE}),
                ("site_upper", {"site_origin": "HTTPS://DOCS.synthetic"
                                               ".example/"}),
                ("ws", {"workspace": "Alpha"}),
                ("ws_lower", {"workspace": "alpha"}))
        return {"action": f"refused:{out}" if ref else out.get("action"),
                "sem": sem(w.entries()),
                "outs": {f"{name}|{t}": norm(w, t, **c) for name, c in ctxs
                         for t in (RAW, "the moduul today")}}


@drives("LF-M14-MR013")
def mr013_canonical_scope_equivalence(entry):
    app_a = _mr013_world("app", APP)
    app_b = _mr013_world("app", APP, job_app="  COM.Synthetic.EDITOR  ")
    site_a = _mr013_world("site", SITE, SITE)
    site_b = _mr013_world("site", SITE, "HTTPS://Docs.Synthetic.Example/")
    ws_a = _mr013_world("workspace", "Alpha", "Alpha")
    ws_b = _mr013_world("workspace", "Alpha", "alpha")
    return check({
        "app_equivalent_identical": app_a == app_b
        and app_a["action"] == "alias_added",
        "site_equivalent_identical": site_a == site_b
        and site_a["action"] == "alias_added",
        "workspace_exact_distinct": ws_a["action"] == "alias_added"
        and ws_b["action"] == "created" and ws_a["sem"] != ws_b["sem"]
        and ws_a["outs"] != ws_b["outs"],
    }, {"app": [app_a["action"], app_b["action"], app_a == app_b],
        "site": [site_a["action"], site_b["action"], site_a == site_b],
        "ws": [ws_a["action"], ws_b["action"]]},
        witness="paired worlds differing only in scope key spelling")


