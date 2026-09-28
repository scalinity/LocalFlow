"""M14 corpus drivers, group d: review sampling, preference pairs,
family splits and exposed test families.

Binds the frozen corpus entries
- cases LF-M14-C101..C108 (sampling), C109..C117 (preferences),
  C118..C125 (family_splits), C126..C131 (exposed_test_families);
- stateful probes LF-M14-S014 (sampling refresh vs exclusion), S015
  (preference display order swapped), S016 (latest preference changes),
  S017 (nine versus ten families), S018 (exposed frozen family through
  the next version);
- metamorphic relations LF-M14-MR006 (family permutation), MR007
  (exposure forward-only), MR011 (display permutation).

Oracles are independent of the functions under test: sampling
membership is recomputed from the published rule (contracts/learning.md:
seeded Bernoulli ``sha256(seed:example_id) < percent/100``; enriched
strata record a null probability; one inclusion per example per policy;
late triggers add exactly one decision), family partitions from the
published split rule (contracts/dataset_exports.md:
``sha256(seed:family_id)`` into 80/10/10, floor of 10 live families,
exposure forward-only; ``m14_world.family_bucket``), and preference
outcomes from the literal texts the driver wrote and the pair the Hub
actually rendered on screen. Stored state is read with raw SQL and
exported packages are read from their files.

Display-order / A-B entries (C112, S015, MR011) drive the real
HubController headless (``test_m14_remediation._hub_env``) under the
isolating runner; the other preference entries grade the writer
(``ReviewService.record_pair_judgment``) and the export package.
"""

from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import m14_world as W  # noqa: E402
from m14_drivers_common import check, drives, invalid, result  # noqa: E402
from m14_world import (A_CANARY, B_CANARY, RATE, Latch,  # noqa: E402
                       MWorld, accepts, family_bucket, frozen_family_id,
                       patched, read_jsonl)

from localflow.v2 import ids  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402

# Published constants (contracts/learning.md, dataset_exports.md) —
# written here literally, never read from the modules under test.
SAMPLING_POLICY = "m14_review_sampling_v1"
SAMPLING_SEED = "localflow-m14-review-v1"
TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"
EPS = 1e-12


# =============================================================================
# shared helpers (independent side)
# =============================================================================


def _draw(seed, key) -> float:
    """The contract's seeded draw, recomputed here."""
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(2 ** 64)


def _prob_eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < EPS


def _long_capture():
    # The default producer envelope records 1.0 s (a short-utterance
    # hard trigger); base-stream fixtures record a long capture.
    return {"capture": {"duration_sec": 10.0, "sample_rate": RATE}}


def base_job(w, text, *, dur=10.0, mutate=None, language=None, **kw):
    extra = {"capture": {"duration_sec": dur, "sample_rate": RATE}}
    if language:
        extra["recognition"] = {"language": language,
                                "model_id": "synth-asr"}
    j = w.job(text, extra_env=extra, **kw)
    if mutate is not None:
        w.rewrite_envelope(j["example_id"], mutate)
    return j


def decisions(w, policy=SAMPLING_POLICY):
    rows = w.rows(
        "SELECT decision_id, example_id, stratum, inclusion_reason,"
        " inclusion_probability, seed FROM sampling_decisions WHERE"
        " policy=? ORDER BY rowid", (policy,))
    return [dict(zip(("decision_id", "example_id", "stratum", "reason",
                      "probability", "seed"), r)) for r in rows]


def by_example(rows):
    out = collections.defaultdict(list)
    for r in rows:
        out[r["example_id"]].append(r)
    return out


def expected_base(ex_id, pct):
    p = pct / 100.0
    return ("representative", p) if _draw(SAMPLING_SEED, ex_id) < p \
        else ("not_included", p)


def states(w):
    return dict(w.rows("SELECT example_id, state FROM training_examples"))


def export_try(w, dest, views, **kw):
    try:
        return w.export(dest, views, **kw), None
    except export_mod.ExportError as e:
        return None, str(e)


def package(root):
    root = pathlib.Path(root)
    return (read_jsonl(root / "examples.jsonl"),
            read_jsonl(root / "preferences.jsonl"),
            json.loads((root / "dataset_manifest.json").read_text()))


def chosen_of(pref):
    for c in pref.get("candidates") or ():
        if pref.get("chosen") is not None and c.get("slot") == \
                pref["chosen"]:
            return c
    return None


def judge_pair(w, task_key, a, b, judgment, op=None):
    fn = w.review.record_pair_judgment
    kw = {"operation_id": op} if op and accepts(fn, "operation_id") else {}
    return fn(w.tf_store(), task_key, a, b, judgment, **kw)


def pair_rows(store_or_w, task_key):
    sql = ("SELECT candidate_id, candidate_b_id, judgment FROM"
           " preference_observations WHERE task_key=? ORDER BY rowid")
    if isinstance(store_or_w, MWorld):
        return [tuple(r) for r in store_or_w.rows(sql, (task_key,))]
    return [tuple(r) for r in store_or_w.submit(
        lambda c: c.execute(sql, (task_key,)).fetchall())]


def refused(fn, *a, **kw):
    try:
        return False, fn(*a, **kw)
    except Exception as e:  # noqa: BLE001 — any typed refusal
        return True, type(e).__name__


def task_with(store, source, outputs, *, instructions, transform_id,
              examples_revision=None):
    """A task shaped like m14_world.transform_task but with its own
    instruction set / examples revision (a different conditional input
    is a different task, S29.10)."""
    from localflow.v2 import store as store_mod
    src_sha = ids.sha256_text(source)
    ins_sha = ids.sha256_text(instructions)
    task_key = ids.sha256_text(json.dumps(
        ["polish", src_sha, ins_sha, examples_revision]))
    now = ids.now_utc_iso()
    cands = []

    def op(c):
        c.execute(
            "INSERT OR IGNORE INTO transform_revisions(transform_id,"
            " revision, definition_json, created_at_utc) VALUES(?,?,?,?)",
            (transform_id, 1, json.dumps(
                {"transform_id": transform_id, "revision": 1,
                 "instructions": instructions, "examples": []}), now))
        for i, text in enumerate(outputs):
            cid = ids.new_id("tcand")
            src = store_mod.insert_text_artifact_row(
                c, artifact_id=ids.new_id("art"), job_id=None,
                stage="transform", role="transform_source", text=source,
                retention_class="training",
                meta={"task_key": task_key, "source_kind": "selection"},
                created_at_utc=now)
            out = store_mod.insert_text_artifact_row(
                c, artifact_id=ids.new_id("art"), job_id=None,
                stage="transform", role="transform_output", text=text,
                retention_class="training",
                meta={"task_key": task_key, "path": "applied"},
                created_at_utc=now)
            c.execute(
                "INSERT INTO transform_candidates(candidate_id, task_key,"
                " task_kind, transform_id, transform_revision,"
                " prompt_revision, source_sha256, instructions_sha256,"
                " examples_revision, source_artifact_id,"
                " output_artifact_id, path, display_order, model_id,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, task_key, "transform_selection", transform_id, 1,
                 "r1", src_sha, ins_sha, examples_revision, src, out,
                 "applied", i, "qwen-synth", now))
            cands.append({"candidate_id": cid, "source_aid": src,
                          "output_aid": out, "text": text})
    store.submit(op)
    return {"task_key": task_key, "candidates": cands, "source": source}


def pmap(w, version):
    """{family: sorted partitions} and {family: exposed flags} of one
    version, straight from training_memberships."""
    parts = collections.defaultdict(set)
    exposed = collections.defaultdict(set)
    for fam, part, exp in w.rows(
            "SELECT family_id, partition, exposed FROM"
            " training_memberships WHERE assignment_version=?",
            (version,)):
        parts[fam].add(part)
        exposed[fam].add(int(exp))
    return ({f: sorted(p) for f, p in parts.items()},
            {f: sorted(e) for f, e in exposed.items()})


def versions(w):
    return w.one("SELECT COUNT(*) FROM split_assignments")[0]


def fams_of(jobs):
    return [j["family_id"] for j in jobs]


def blind_claims(examples, fam):
    return [e for e in examples if e.get("family_id") == fam
            and e.get("split") == "frozen_test" and not e.get("exposed")]


# =============================================================================
# sampling (C101–C108, S014)
# =============================================================================


@drives("LF-M14-C101")
def c101_positive_base_stream(entry):
    pct = 30.0
    with MWorld() as w:
        exs = [base_job(w, f"base stream utterance {i}")["example_id"]
               for i in range(40)]
        out = w.sampling.refresh(percent=pct)
        rows = decisions(w)
        per = by_example(rows)
        expected = {e: expected_base(e, pct) for e in exs}
        got = {e: (r[0]["stratum"], r[0]["probability"])
               for e, r in per.items() if len(r) == 1}
        n_rep = sum(1 for s, _p in expected.values()
                    if s == "representative")
        if n_rep in (0, len(exs)):
            return invalid("fixture drew a degenerate sample",
                           {"representative": n_rep})
        st = states(w)
        conds = {
            "one_decision_per_example": set(per) == set(exs)
            and all(len(v) == 1 for v in per.values()),
            "strata_follow_published_draw": all(
                got.get(e, (None,))[0] == s for e, (s, _p) in
                expected.items()),
            "base_probability_honest": all(
                _prob_eq(got.get(e, (None, None))[1], p)
                for e, (_s, p) in expected.items()),
            "seed_recorded": all(r["seed"] == SAMPLING_SEED for r in rows),
            "included_move_to_review": all(
                st[e] == ("review_candidate" if s == "representative"
                          else "captured_unreviewed")
                for e, (s, _p) in expected.items()),
            "population_reported": out.get("population") == len(exs),
        }
        return check(conds, {"examples": len(exs), "representative": n_rep,
                             "rows": len(rows),
                             "reasons": sorted({r["reason"] for r in rows})},
                     witness="SamplingService.refresh over 40 long-capture"
                             " examples at 30%; draw recomputed from"
                             " sha256(seed:example_id)")


@drives("LF-M14-C102")
def c102_explicit(entry):
    pct = 10.0
    with MWorld() as w:
        base = [base_job(w, f"populated stratum words {i}")["example_id"]
                for i in range(12)]
        marked = base_job(w, "explicitly marked incorrect words")
        w.training.mark_intended(marked["example_id"], False)
        taught = base_job(w, TEACH_RAW)
        teach = w.learning.teach_correction(taught["job_id"], TEACH_FIX)
        first = w.sampling.refresh(percent=pct)
        n1 = len(decisions(w))
        second = w.sampling.refresh(percent=pct)
        rows = decisions(w)
        per = by_example(rows)

        def one(ex, reason):
            r = per.get(ex) or []
            return (len(r) == 1 and r[0]["stratum"] == "explicit"
                    and r[0]["probability"] is None
                    and reason in (r[0]["reason"] or "").split(";"))
        conds = {
            "incorrect_mark_selected_once_null_p": one(
                marked["example_id"], "explicit_incorrect"),
            "teach_selected_once_null_p": one(
                taught["example_id"], "correction_candidate"),
            "base_companions_keep_known_p": all(
                len(per.get(e) or []) == 1 and _prob_eq(
                    per[e][0]["probability"], pct / 100.0) for e in base),
            "second_refresh_ran_and_added_nothing": second.get(
                "population") == 0 and len(rows) == n1,
        }
        return check(conds, {
            "marked": [(r["stratum"], r["reason"], r["probability"])
                       for r in per.get(marked["example_id"], [])],
            "taught": [(r["stratum"], r["reason"], r["probability"])
                       for r in per.get(taught["example_id"], [])],
            "teach_candidate": bool(teach.get("candidate_id")),
            "first_population": first.get("population")},
            witness="mark_intended(False) and teach_correction, then two"
                    " refreshes (second proves one decision per example)")


_HARD = {
    "retry": dict(mutate=lambda e: e.update(attempt=2)),
    "cleanup_fallback": dict(mutate=lambda e: e["cleanup"].update(
        fallback_reason="model_timeout")),
    "validator_rejection": dict(mutate=lambda e: e["cleanup"].update(
        v2={"validation": {"length_ok": False}})),
    "short_utterance": dict(dur=1.0),
    "capture_discontinuity": dict(mutate=lambda e: e["capture"].update(
        journal_dropped_blocks=3)),
    "transform_needs_review": dict(mutate=lambda e: e.update(
        transform={"path": "needs_review"})),
}


@drives("LF-M14-C103")
def c103_hard_trigger(entry):
    pct = 10.0
    with MWorld() as w:
        hard = {}
        for reason, kw in _HARD.items():
            j = base_job(w, f"hard trigger {reason} words", **kw)
            hard[j["example_id"]] = {reason}
        multi = base_job(w, "retry and short words", dur=1.0,
                         mutate=lambda e: e.update(attempt=2))
        hard[multi["example_id"]] = {"retry", "short_utterance"}
        negs = [base_job(w, f"plain base negative {i}")["example_id"]
                for i in range(10)]
        w.sampling.refresh(percent=pct)
        per = by_example(decisions(w))
        bad = {}
        for ex, want in hard.items():
            r = per.get(ex) or []
            ok = (len(r) == 1 and r[0]["stratum"] == "hard_trigger"
                  and r[0]["probability"] is None
                  and set((r[0]["reason"] or "").split(";")) == want)
            if not ok:
                bad[",".join(sorted(want))] = [
                    (x["stratum"], x["reason"], x["probability"])
                    for x in r]
        conds = {
            "hard_rows_reason_and_null_p": not bad,
            "base_negatives_known_p": all(
                len(per.get(e) or []) == 1
                and (per[e][0]["stratum"], ) == (expected_base(e, pct)[0],)
                and _prob_eq(per[e][0]["probability"], pct / 100.0)
                for e in negs),
        }
        return check(conds, {"hard": len(hard), "mismatched": bad},
                     witness="one example per hard trigger (+ one with two"
                             " triggers) and ten long-capture negatives")


@drives("LF-M14-C104")
def c104_supplemental(entry):
    pct = 10.0
    with MWorld() as w:
        multi = [base_job(w, f"mehrsprachige worte {i}",
                          language="de")["example_id"] for i in range(30)]
        eng = [base_job(w, f"english base words {i}")["example_id"]
               for i in range(10)]
        w.sampling.refresh(percent=pct)
        per = by_example(decisions(w))
        want_supp = [e for e in multi
                     if _draw(SAMPLING_SEED, e) >= pct / 100.0]
        if not want_supp:
            return invalid("no multilingual example outside the draw")
        conds = {
            "supplemental_recorded_enriched": all(
                len(per.get(e) or []) == 1
                and per[e][0]["stratum"] == "supplemental"
                and per[e][0]["probability"] is None for e in want_supp),
            "drawn_multilingual_stay_representative": all(
                per[e][0]["stratum"] == "representative"
                and _prob_eq(per[e][0]["probability"], pct / 100.0)
                for e in multi if e not in want_supp),
            "english_not_supplemented": all(
                len(per.get(e) or []) == 1
                and per[e][0]["stratum"] == expected_base(e, pct)[0]
                for e in eng),
        }
        return check(conds, {"supplemental_expected": len(want_supp),
                             "supplemental_rows": sum(
                                 1 for v in per.values()
                                 if v[0]["stratum"] == "supplemental")},
                     witness="30 language=de examples at 10%: the non-drawn"
                             " ones are the supplemental pool")


@drives("LF-M14-C105")
def c105_late_trigger(entry):
    pct = 50.0
    with MWorld() as w:
        exs = [base_job(w, f"late trigger base {i}")["example_id"]
               for i in range(16)]
        w.sampling.refresh(percent=pct)
        before = decisions(w)
        exp = {e: expected_base(e, pct)[0] for e in exs}
        excluded = [e for e in exs if exp[e] == "not_included"]
        drawn = [e for e in exs if exp[e] == "representative"]
        if len(excluded) < 2 or not drawn:
            return invalid("fixture lacks not-included/drawn examples")
        late_mark, late_retry, rep = excluded[0], excluded[1], drawn[0]
        w.training.mark_intended(late_mark, False)
        w.rewrite_envelope(late_retry, lambda e: e.update(attempt=2))
        w.training.mark_intended(rep, False)
        out = w.sampling.refresh(percent=pct)
        after = decisions(w)
        w.sampling.refresh(percent=pct)
        final = decisions(w)
        new = [r for r in after if r["decision_id"] not in
               {b["decision_id"] for b in before}]
        by_new = by_example(new)
        conds = {
            "one_late_explicit": [(r["stratum"], r["reason"],
                                   r["probability"])
                                  for r in by_new.get(late_mark, [])]
            == [("explicit", "late_trigger:explicit_incorrect", None)],
            "one_late_hard": [(r["stratum"], r["reason"], r["probability"])
                              for r in by_new.get(late_retry, [])]
            == [("hard_trigger", "late_trigger:retry", None)],
            "already_included_not_duplicated": rep not in by_new,
            "no_other_new_rows": set(by_new) <= {late_mark, late_retry},
            "base_rows_not_redrawn": [
                (r["decision_id"], r["stratum"], r["probability"])
                for r in after[:len(before)]] == [
                (r["decision_id"], r["stratum"], r["probability"])
                for r in before],
            "third_refresh_adds_nothing": len(final) == len(after),
            "refresh_reported_late": out.get("late_inclusions") == 2,
        }
        return check(conds, {"new_rows": len(new),
                             "late_reported": out.get("late_inclusions")},
                     witness="not_included draws later gain an incorrect"
                             " mark / a retry; a drawn example gains a mark")


@drives("LF-M14-C106")
def c106_determinism(entry):
    pct = 30.0
    planned = [f"ex-synth-d106-{i:03d}" for i in range(30)]

    def build(order):
        w = MWorld()
        slot = {}

        def factory(orig):
            def upsert(**kw):
                kw["example_id"] = slot["next"]
                return orig(**kw)
            return upsert
        with patched(w.store, "upsert_example", factory):
            for i in order:
                slot["next"] = planned[i]
                base_job(w, f"determinism utterance {i}")
        out = w.sampling.refresh(percent=pct)
        rows = {r["example_id"]: (r["stratum"], r["probability"])
                for r in decisions(w)}
        return w, out, rows
    wa, outa, ra = build(range(30))
    try:
        wb, outb, rb = build(reversed(range(30)))
    except Exception:
        wa.close()
        raise
    try:
        expected = {e: expected_base(e, pct) for e in planned}
        if set(ra) != set(planned):
            return invalid("planned example ids were not used",
                           {"ids": len(ra)})
        conds = {
            "stores_agree": ra == rb,
            "membership_follows_policy": all(
                ra[e][0] == s and _prob_eq(ra[e][1], p)
                for e, (s, p) in expected.items()),
            "population_hash_equal": outa.get("population_hash")
            == outb.get("population_hash"),
        }
        return check(conds, {"representative": sum(
            1 for s, _p in ra.values() if s == "representative")},
            witness="two stores, same 30 example ids inserted in"
                    " forward vs reversed order, same seed/policy")
    finally:
        wa.close()
        wb.close()


def _refresh_with(w, action, *, when, pct=10.0):
    """Run refresh with ``action`` serialized immediately BEFORE the
    refresh writer op is admitted (``when='before'``) or right after it
    commits (``'after'``). The action runs in the caller thread between
    writer ops (never inside one)."""
    latch = Latch("m14_s014_authority_boundary", block=False)
    original = w.store.submit

    def submit(fn, wait=True, timeout=15.0):
        is_refresh = "SamplingService.refresh" in getattr(
            fn, "__qualname__", "")
        if is_refresh and when == "before" and not latch.hits:
            latch.hit()
            action()
        out = original(fn, wait=wait, timeout=timeout)
        if is_refresh and when == "after" and not latch.hits:
            latch.hit()
            action()
        return out
    w.store.submit = submit
    try:
        w.sampling.refresh(percent=pct)
    finally:
        w.store.submit = original
    return latch


def _exclusion_world(mode, when):
    """Twelve base examples plus X (a short utterance: a hard trigger,
    so a live X is always included). Returns observed facts."""
    w = MWorld()
    try:
        for i in range(12):
            base_job(w, f"exclusion base {i}")
        x = base_job(w, "exclusion target words", dur=1.0)
        ex = x["example_id"]

        def act():
            if mode == "exclude":
                w.training.exclude(ex, True)
            else:
                w.training.delete_everywhere(ex)
        latch = _refresh_with(w, act if mode else (lambda: None),
                              when=when)
        rows = by_example(decisions(w))
        queue = {r.get("example_id") for r in w.review.queue()}
        st = w.one("SELECT state FROM training_examples WHERE"
                   " example_id=?", (ex,))
        return {"reached": latch.hits, "x_rows": [
            (r["stratum"], r["probability"]) for r in rows.get(ex, [])],
            "others": sum(1 for k in rows if k != ex),
            "x_state": st[0] if st else None, "x_in_queue": ex in queue}
    finally:
        w.close()


@drives("LF-M14-C107")
def c107_exclusion_commit(entry):
    control = _exclusion_world(None, "before")
    obs = {"control": control}
    for mode in ("exclude", "delete"):
        obs[mode] = _exclusion_world(mode, "before")
        obs[mode + "_after"] = _exclusion_world(mode, "after")
    if not all(obs[k]["reached"] for k in obs):
        return invalid("admission seam not reached", obs)
    conds = {
        "control_includes_live_x": control["x_rows"] == [
            ("hard_trigger", None)] and control["x_in_queue"],
        "excluded_before_admission_not_member":
            obs["exclude"]["x_rows"] == [] and
            obs["exclude"]["x_state"] == "excluded",
        "deleted_before_admission_not_member":
            obs["delete"]["x_rows"] == [],
        "others_still_decided": all(obs[k]["others"] == 12 for k in obs),
        "later_exclusion_leaves_queue": not obs["exclude_after"][
            "x_in_queue"] and obs["exclude_after"]["x_state"] == "excluded",
        "later_delete_leaves_queue": not obs["delete_after"]["x_in_queue"],
    }
    return check(conds, obs, witness="submit seam: exclusion/deletion"
                 " committed as its own writer op right before (and, as"
                 " the alternate order, right after) the refresh op")


@drives("LF-M14-S014")
def s014_refresh_with_exclusion(entry):
    control = _exclusion_world(None, "before")
    before = _exclusion_world("exclude", "before")
    after = _exclusion_world("exclude", "after")
    obs = {"control": control, "exclude_first": before,
           "refresh_first": after}
    if not (control["reached"] and before["reached"] and after["reached"]):
        return invalid("barrier m14_s014_authority_boundary never fired",
                       obs, reached=False)
    conds = {
        "control_member_and_queued": control["x_rows"] == [
            ("hard_trigger", None)] and control["x_in_queue"],
        "exclude_first_no_membership": before["x_rows"] == []
        and not before["x_in_queue"],
        "refresh_first_decision_then_leaves_queue": after["x_rows"] == [
            ("hard_trigger", None)] and not after["x_in_queue"]
        and after["x_state"] == "excluded",
    }
    return check(conds, obs, reached=True,
                 witness="latch before refresh writer admission; exclude"
                         " commits first; alternate order refresh-first")


@drives("LF-M14-C108")
def c108_population_change(entry):
    pct = 50.0
    with MWorld() as w:
        exs = [base_job(w, f"population base {i}")["example_id"]
               for i in range(12)]
        w.sampling.refresh(percent=pct)
        before = decisions(w)
        gone = exs[0]
        w.store.set_example_state(gone, "expired")
        added = base_job(w, "population newcomer words")["example_id"]
        out = w.sampling.refresh(percent=pct)
        after = decisions(w)
        cov = w.sampling.coverage()
        new = after[len(before):]
        live = w.one("SELECT COUNT(*) FROM training_examples WHERE state"
                     " IN ('captured_unreviewed','review_candidate',"
                     "'annotated','ambiguous','quarantined_sensitive')")[0]
        s, p = expected_base(added, pct)
        conds = {
            "existing_rows_unchanged": [tuple(r.values()) for r in
                                        after[:len(before)]]
            == [tuple(r.values()) for r in before],
            "newcomer_one_decision": [(r["example_id"], r["stratum"])
                                      for r in new] == [(added, s)]
            and _prob_eq(new[0]["probability"], p),
            "expired_not_redecided": all(r["example_id"] != gone
                                         for r in new),
            "refresh_counts_honest": out.get("population") == 1
            and sum((out.get("included") or {}).values()) == 1,
            "coverage_counts_honest": cov.get("decisions_total") == 13
            and cov.get("live_examples") == live == 12,
        }
        return check(conds, {"new": len(new), "coverage": {
            k: cov.get(k) for k in ("decisions_total", "live_examples",
                                    "one_inclusion_per_example")}},
            witness="refresh; expire one decided example; add one;"
                    " refresh again (stability per 'drawn at most once')")


# =============================================================================
# preferences (C109–C117, S015, S016, MR011)
# =============================================================================

A_TEXT = f"Alpha polished output {A_CANARY}."
B_TEXT = f"Bravo polished output {B_CANARY}."


def _pair_export(w, dest="ds", **kw):
    w.splits.assign()
    out, err = export_try(w, dest, ("preference_pairs",), **kw)
    if out is None:
        return None, err
    _e, prefs, manifest = package(w.tmp / dest)
    return {"prefs": prefs, "manifest": manifest}, None


def _one_pref(pkg, task_key):
    rows = [p for p in pkg["prefs"] if p.get("task_key") == task_key]
    return rows[0] if len(rows) == 1 else None


def _prefer(entry, judgment, want_slot, want_text, other_text):
    with MWorld() as w:
        t = w.transform_task(f"compare source {entry['id']}",
                             [A_TEXT, B_TEXT])
        a, b = (c["candidate_id"] for c in t["candidates"])
        pane = [p for p in w.review.preference_pairs()
                if p["task_key"] == t["task_key"]]
        judge_pair(w, t["task_key"], a, b, judgment,
                   op=f"op-d-{entry['id']}")
        stored = pair_rows(w, t["task_key"])
        pkg, err = _pair_export(w)
        if pkg is None:
            return check({"export_built": False}, {"error": err})
        pref = _one_pref(pkg, t["task_key"])
        ch = chosen_of(pref) if pref else None
        want_id = a if want_slot == "a" else b
        conds = {
            "pane_shows_source_and_both": bool(pane) and pane[0].get(
                "source_text") == t["source"] and sorted(
                c.get("text") or "" for c in pane[0]["candidates"])
            == sorted([A_TEXT, B_TEXT]),
            "stored_as_judged": stored == [(a, b, judgment)],
            "exported_once": pref is not None,
            "chosen_slot": bool(pref) and pref.get("chosen") == want_slot,
            "chosen_identity": bool(ch) and ch.get("candidate_id")
            == want_id,
            "chosen_exact_text": bool(ch) and ch.get("output_text")
            == want_text,
            "other_text_kept": bool(pref) and other_text in [
                c.get("output_text") for c in pref["candidates"]],
            "input_travels": bool(pref) and pref.get("input_text")
            == t["source"],
        }
        return check(conds, {"judgment": judgment,
                             "chosen": pref and pref.get("chosen")},
                     witness="ReviewService.record_pair_judgment →"
                             " preference_pairs export (service-level"
                             " pane: ReviewService.preference_pairs)")


@drives("LF-M14-C109")
def c109_prefer_a(entry):
    return _prefer(entry, "prefer_a", "a", A_TEXT, B_TEXT)


@drives("LF-M14-C110")
def c110_prefer_b(entry):
    return _prefer(entry, "prefer_b", "b", B_TEXT, A_TEXT)


@drives("LF-M14-C111")
def c111_neutral(entry):
    with MWorld() as w:
        tasks = {}
        for j in ("tie", "neither", "uncertain", "prefer_a"):
            t = w.transform_task(f"neutral source {j}", [A_TEXT, B_TEXT])
            a, b = (c["candidate_id"] for c in t["candidates"])
            judge_pair(w, t["task_key"], a, b, j)
            tasks[j] = (t, a, b)
        pkg, err = _pair_export(w)
        if pkg is None:
            return check({"export_built": False}, {"error": err})
        obs, conds = {}, {}
        for j, (t, a, b) in tasks.items():
            pref = _one_pref(pkg, t["task_key"])
            stored = pair_rows(w, t["task_key"])
            obs[j] = pref and (pref.get("judgment"), pref.get("chosen"))
            texts = sorted(c.get("output_text") for c in
                           (pref or {}).get("candidates") or ())
            if j == "prefer_a":
                ch = chosen_of(pref) if pref else None
                conds["control_prefer_a_chosen"] = bool(ch) and \
                    ch.get("output_text") == A_TEXT
                continue
            conds[f"{j}_no_winner"] = bool(pref) and \
                pref.get("chosen") is None and chosen_of(pref) is None
            conds[f"{j}_representation_kept"] = bool(pref) and \
                pref.get("judgment") == j and stored == [(a, b, j)] \
                and texts == sorted([A_TEXT, B_TEXT])
        return check(conds, obs, witness="tie/neither/uncertain each on"
                     " its own task, prefer_a control, one export")


# ---- Hub-driven pair judgments (C112, S015, MR011) ---------------------------

_PAIR_LINE = re.compile(r"^([AB]) \[(\S+) \S order (-?\d+)\]: (.*)$")


def _rendered_pair(hub):
    """The pair the Hub shows (slot → candidate id, order, text), parsed
    from the on-screen review text — the visible truth."""
    text = str(hub.review_text.string())
    if "— compare" not in text:
        return None
    slots = {}
    for line in text.split("— compare", 1)[1].splitlines():
        m = _PAIR_LINE.match(line.strip())
        if m:
            slots[m.group(1)] = {"cid": m.group(2),
                                 "order": int(m.group(3)),
                                 "text": m.group(4)}
    return slots if set(slots) == {"A", "B"} else None


def _swap_display(store, c0, c1):
    def op(c):
        d = dict(c.execute(
            "SELECT candidate_id, display_order FROM transform_candidates"
            " WHERE candidate_id IN (?,?)", (c0, c1)).fetchall())
        c.execute("UPDATE transform_candidates SET display_order=? WHERE"
                  " candidate_id=?", (d[c1], c0))
        c.execute("UPDATE transform_candidates SET display_order=? WHERE"
                  " candidate_id=?", (d[c0], c1))
    store.submit(op)


def _ensure_consent(store):
    row = store.submit(lambda c: c.execute(
        "SELECT state FROM consent_revisions ORDER BY rowid DESC"
        " LIMIT 1").fetchone())
    if not row or row[0] != "enabled":
        store.append_consent("enabled", note="m14-driver-d")


def hub_pair(*, display, click, swap=None, texts=(A_TEXT, B_TEXT),
             source=f"hub shared source {A_CANARY}"):
    """One Harness + real HubController: create a two-candidate task,
    render the review tab, optionally swap display order (``swap``:
    'before_render' | 'rerender' | 'stale'), click the pair button for
    slot ``click`` and export. Returns observed facts."""
    import test_m14_remediation as R
    Harness, MainQueue = R._hub_env()
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = R._make_hub(h)
            if not mq.drain(hub.state, 60):
                raise RuntimeError("hub never settled")
            store = h.d.store
            t = W.transform_task(store, source, list(texts),
                                 display=list(display))
            c0, c1 = (c["candidate_id"] for c in t["candidates"])
            if swap == "before_render":
                _swap_display(store, c0, c1)
            R._review_tab(hub, mq)
            first = _rendered_pair(hub)
            if swap in ("rerender", "stale"):
                _swap_display(store, c0, c1)
                if swap == "rerender":
                    hub.state.select_training_tab("review")
                    mq.drain(hub.state, 60)
            shown = _rendered_pair(hub)
            (hub.reviewPairA_ if click == "A" else hub.reviewPairB_)(None)
            mq.drain(hub.state, 60)
            stored = pair_rows(store, t["task_key"])
            _ensure_consent(store)
            h.d._splits.assign()
            dest = h.tmp / "ds-d"
            try:
                h.d._exporter.build(dest, task_views=("preference_pairs",))
                prefs = read_jsonl(dest / "preferences.jsonl")
                err = None
            except export_mod.ExportError as e:
                prefs, err = [], str(e)
            pref = next((p for p in prefs
                         if p.get("task_key") == t["task_key"]), None)
            ch = chosen_of(pref) if pref else None
            text_of = {c0: texts[0], c1: texts[1]}
            return {"c0": c0, "c1": c1, "first": first, "shown": shown,
                    "stored": stored, "export_error": err,
                    "chosen_id": ch and ch.get("candidate_id"),
                    "chosen_text": ch and ch.get("output_text"),
                    "text_of": text_of}
    finally:
        h.close()


def _slot_ids(r):
    s = r.get("shown")
    return (s["A"]["cid"], s["B"]["cid"]) if s else None


def _hub_obs(r):
    """Content-free summary: which fixture candidate sat in each slot,
    what was stored and chosen."""
    idx = {r["c0"]: "c0", r["c1"]: "c1"}
    first, shown = r.get("first"), r.get("shown")
    return {"first": first and [idx.get(first[s]["cid"]) for s in "AB"],
            "shown": shown and [idx.get(shown[s]["cid"]) for s in "AB"],
            "stored": [(idx.get(a), idx.get(b), j)
                       for a, b, j in r["stored"]],
            "chosen": idx.get(r["chosen_id"]),
            "export_error": r["export_error"]}


def _visible_choice_holds(r, click):
    """The stored/exported choice is the candidate VISIBLE in the
    clicked slot at click time (parsed from the screen)."""
    shown = r.get("shown")
    if not shown:
        return {"pair_rendered": False}
    left, right = shown["A"]["cid"], shown["B"]["cid"]
    vis = left if click == "A" else right
    want = (left, right, "prefer_a" if click == "A" else "prefer_b")
    return {"pair_rendered": True,
            "rendered_texts_are_the_candidates": {
                shown["A"]["text"], shown["B"]["text"]}
            == set(r["text_of"].values()),
            "stored_rendered_pair_in_slot_order": r["stored"] == [want],
            "exported_choice_is_visible_candidate":
                r["chosen_id"] == vis,
            "exported_text_is_visible_text":
                r["chosen_text"] == r["text_of"].get(vis)
                == shown[click]["text"]}


@drives("LF-M14-C112")
def c112_swapped_display(entry):
    control = hub_pair(display=(0, 1), click="B")
    swapped = hub_pair(display=(1, 0), click="B")
    obs = {"control": _hub_obs(control), "swapped": _hub_obs(swapped)}
    if not (control["shown"] and swapped["shown"]):
        return check({"pair_rendered": False}, obs)
    conds = {f"control_{k}": v for k, v in
             _visible_choice_holds(control, "B").items()}
    conds.update({f"swapped_{k}": v for k, v in
                  _visible_choice_holds(swapped, "B").items()})
    conds["display_actually_swapped"] = _slot_ids(control) == (
        control["c0"], control["c1"]) and _slot_ids(swapped) == (
        swapped["c1"], swapped["c0"])
    conds["swap_changes_chosen_identity"] = (
        control["chosen_text"] == B_TEXT and swapped["chosen_text"]
        == A_TEXT)
    return check(conds, obs, witness="HubController headless: review tab"
                 " rendered, reviewPairB_ clicked, preference_pairs export")


@drives("LF-M14-S015")
def s015_display_swapped_after_render(entry):
    runs = {"no_swap": hub_pair(display=(0, 1), click="B"),
            "swap_rerender": hub_pair(display=(0, 1), click="B",
                                      swap="rerender"),
            "swap_stale_screen": hub_pair(display=(0, 1), click="B",
                                          swap="stale"),
            "swap_before_render": hub_pair(display=(0, 1), click="B",
                                           swap="before_render")}
    obs = {k: _hub_obs(r) for k, r in runs.items()}
    if not all(r["first"] for r in runs.values()):
        # The Hub never showed a comparison with A/B ids: the product
        # offered nothing visible to judge (graded, not a missed seam).
        return check({"pair_rendered_with_ids": False}, obs,
                     reached=False, witness="HubController review tab"
                     " rendered no A/B comparison")
    rr = runs["swap_rerender"]
    if _slot_ids(rr) != (rr["c1"], rr["c0"]):
        return invalid("swap was not re-rendered", obs, reached=True)
    conds = {}
    for k, r in runs.items():
        conds.update({f"{k}_{c}": v for c, v in
                      _visible_choice_holds(r, "B").items()})
    st = runs["swap_stale_screen"]
    conds["stale_screen_judges_what_is_shown"] = st["chosen_id"] == st["c1"]
    conds["rerender_judges_new_right"] = rr["chosen_id"] == rr["c0"]
    return check(conds, obs, reached=True,
                 witness="render (latch) → swap display_order → re-render"
                         " or not → click visible right (B); plus no-swap"
                         " control and swap-before-render order")


@drives("LF-M14-MR011")
def mr011_display_permutation(entry):
    plain = hub_pair(display=(0, 1), click="A")      # c0 shown left
    permuted = hub_pair(display=(1, 0), click="B")   # c0 shown right
    obs = {"plain": _hub_obs(plain), "permuted": _hub_obs(permuted)}
    if not (plain["shown"] and permuted["shown"]):
        return check({"pair_rendered": False}, obs)
    if _slot_ids(plain)[0] != plain["c0"] or \
            _slot_ids(permuted)[1] != permuted["c0"]:
        return invalid("the display permutation was not rendered", obs)
    conds = {
        "same_identity_chosen": obs["plain"]["chosen"] == "c0"
        == obs["permuted"]["chosen"],
        "exported_preferred_output_identical":
            plain["chosen_text"] == permuted["chosen_text"] == A_TEXT,
    }
    return check(conds, obs, witness="HubController: same candidate chosen"
                 " from the left (prefer A) and, sides swapped, from the"
                 " right (prefer B)")


@drives("LF-M14-C113")
def c113_cross_task(entry):
    obs = {}
    with MWorld() as w:
        base = w.transform_task("cross task shared source",
                                [A_TEXT, B_TEXT])
        other_src = w.transform_task("cross task other source",
                                     ["Other one.", "Other two."])
        other_ins = task_with(w.store, "cross task shared source",
                              ["Ins one.", "Ins two."],
                              instructions="Rewrite formally (synthetic).",
                              transform_id="custom:synthetic-formal")
        other_ex = task_with(w.store, "cross task shared source",
                             ["Ex one.", "Ex two."],
                             instructions="Polish the synthetic draft.",
                             transform_id="custom:synthetic-examples",
                             examples_revision=7)
        a = base["candidates"][0]["candidate_id"]
        attempts = {
            "source": (base["task_key"], other_src),
            "instructions": (base["task_key"], other_ins),
            "examples_revision": (base["task_key"], other_ex),
            "foreign_key": (other_src["task_key"], other_src),
        }
        writer = {}
        for name, (key, other) in attempts.items():
            was, _ = refused(judge_pair, w, key, a,
                             other["candidates"][0]["candidate_id"],
                             "prefer_a")
            writer[name] = was
        written = w.one("SELECT COUNT(*) FROM preference_observations")[0]
        judge_pair(w, base["task_key"], a,
                   base["candidates"][1]["candidate_id"], "prefer_a")
        pkg, err = _pair_export(w)
        pref = _one_pref(pkg, base["task_key"]) if pkg else None
        obs["writer_refused"] = writer
        obs["rows_after_refusals"] = written
        obs["positive_export"] = err or "built"
    with MWorld() as w2:
        base = w2.transform_task("forged pair source", [A_TEXT, B_TEXT])
        other = w2.transform_task("forged pair other source",
                                  ["Forged one.", "Forged two."])
        w2.store.submit(lambda c: c.execute(
            "INSERT INTO preference_observations(observation_id, task_key,"
            " candidate_id, candidate_b_id, judgment, provenance,"
            " created_at_utc) VALUES(?,?,?,?,?,?,?)",
            (ids.new_id("pref"), base["task_key"],
             base["candidates"][0]["candidate_id"],
             other["candidates"][0]["candidate_id"], "prefer_a",
             "m14_pair_review", ids.now_utc_iso())))
        pkg2, err2 = _pair_export(w2)
        leaked = bool(pkg2) and any(
            p.get("task_key") == base["task_key"] for p in pkg2["prefs"])
        obs["forged_row_export"] = "refused" if pkg2 is None else (
            "leaked" if leaked else "excluded")
    conds = {
        "writer_refuses_every_variant": all(writer.values()),
        "refusals_write_nothing": written == 0,
        "same_task_positive_exported": bool(pref)
        and (chosen_of(pref) or {}).get("output_text") == A_TEXT,
        "export_refuses_cross_task_row": pkg2 is None or not leaked,
    }
    return check(conds, obs, witness="record_pair_judgment across source /"
                 " instructions / examples-revision / foreign task key;"
                 " forged cross-task observation row through export")


@drives("LF-M14-C114")
def c114_latest_sequence(entry):
    with MWorld() as w:
        t = w.transform_task("latest sequence source", [A_TEXT, B_TEXT])
        a, b = (c["candidate_id"] for c in t["candidates"])
        for x, y, j in ((a, b, "prefer_a"), (a, b, "prefer_b"),
                        (b, a, "tie"), (a, b, "prefer_a")):
            judge_pair(w, t["task_key"], x, y, j)
        # Same sequence, the final "A" recorded with slots reversed.
        r = w.transform_task("latest sequence reversed", [A_TEXT, B_TEXT])
        ra, rb = (c["candidate_id"] for c in r["candidates"])
        for x, y, j in ((ra, rb, "prefer_a"), (ra, rb, "prefer_b"),
                        (rb, ra, "tie"), (rb, ra, "prefer_b")):
            judge_pair(w, r["task_key"], x, y, j)
        pkg, err = _pair_export(w)
        if pkg is None:
            return check({"export_built": False}, {"error": err})
        p1, p2 = _one_pref(pkg, t["task_key"]), _one_pref(pkg, r["task_key"])
        c1 = chosen_of(p1) if p1 else None
        c2 = chosen_of(p2) if p2 else None
        conds = {
            "latest_used": bool(c1) and c1.get("candidate_id") == a
            and c1.get("output_text") == A_TEXT,
            "latest_used_reversed_slots": bool(c2)
            and c2.get("candidate_id") == ra
            and c2.get("output_text") == A_TEXT,
            "history_retained": [j for _x, _y, j in pair_rows(
                w, t["task_key"])] == ["prefer_a", "prefer_b", "tie",
                                       "prefer_a"],
            "one_export_row_per_pair": len(pkg["prefs"]) == 2,
        }
        return check(conds, {"judgments": [p1 and p1.get("judgment"),
                                           p2 and p2.get("judgment")]},
                     witness="A→B→tie→A on one unordered pair (twice, the"
                             " last with slots reversed) → export")


@drives("LF-M14-S016")
def s016_latest_changes(entry):
    with MWorld() as w:
        t = w.transform_task("changing mind source", [A_TEXT, B_TEXT])
        a, b = (c["candidate_id"] for c in t["candidates"])
        w.splits.assign()
        steps = (("prefer_a", A_TEXT), ("prefer_b", B_TEXT), ("tie", None),
                 ("prefer_a", A_TEXT))
        seen, conds = [], {}
        latch = Latch("m14_s016_authority_boundary", block=False)
        for i, (j, want) in enumerate(steps):
            judge_pair(w, t["task_key"], a, b, j)
            if i == 0:
                latch.hit()  # after the A judgment commits
            out, err = export_try(w, f"ds{i}", ("preference_pairs",))
            if out is None:
                return check({f"export_{i}_built": False}, {"error": err})
            _e, prefs, _m = package(w.tmp / f"ds{i}")
            pref = _one_pref({"prefs": prefs}, t["task_key"])
            ch = chosen_of(pref) if pref else None
            seen.append(pref and (pref.get("judgment"), pref.get("chosen")))
            conds[f"step{i}_{j}_current"] = bool(pref) and \
                pref.get("judgment") == j and \
                (ch.get("output_text") if ch else None) == want
            conds[f"step{i}_history_{i + 1}"] = len(
                pair_rows(w, t["task_key"])) == i + 1
        if not latch.hits:
            return invalid("barrier never reached", seen, reached=False)
        return check(conds, seen, reached=True,
                     witness="latch after the A judgment; B, tie, A saved"
                             " with an export after each")


@drives("LF-M14-C115")
def c115_source_output_purge(entry):
    obs, conds = {}, {}
    for variant in ("source", "out_a", "out_b"):
        with MWorld() as w:
            hit = w.transform_task(f"purge {variant} source",
                                   [A_TEXT, B_TEXT])
            keep = w.transform_task(f"unrelated {variant} source",
                                    [A_TEXT, B_TEXT])
            for t in (hit, keep):
                judge_pair(w, t["task_key"],
                           t["candidates"][0]["candidate_id"],
                           t["candidates"][1]["candidate_id"], "prefer_a")
            if variant == "source":
                for c in hit["candidates"]:
                    w.purge(c["source_aid"])
            else:
                w.purge(hit["candidates"][0 if variant == "out_a"
                                          else 1]["output_aid"])
            pkg, err = _pair_export(w)
            if pkg is None:
                obs[variant] = {"error": err}
                conds[f"{variant}_export_built"] = False
                continue
            kept = _one_pref(pkg, keep["task_key"])
            excl = [e for e in pkg["manifest"].get("excluded") or ()
                    if e.get("task_key") == hit["task_key"]]
            obs[variant] = {"excluded": [e.get("reason") for e in excl]}
            conds[f"{variant}_affected_not_exported"] = all(
                p.get("task_key") != hit["task_key"] for p in pkg["prefs"])
            conds[f"{variant}_affected_listed_incomplete"] = bool(excl)
            conds[f"{variant}_unrelated_remains"] = bool(kept) and (
                chosen_of(kept) or {}).get("output_text") == A_TEXT
    return check(conds, obs, witness="purge through Store._purge_artifact"
                 " in three stores; preference_pairs export")


def _corrupt(w, t, variant):
    b = t["candidates"][1]
    if variant == "source_digest":
        w.store.submit(lambda c: c.execute(
            "UPDATE transform_candidates SET source_sha256=? WHERE"
            " candidate_id=?", (ids.sha256_text("another source"),
                                b["candidate_id"])))
    elif variant == "instructions_digest":
        w.store.submit(lambda c: c.execute(
            "UPDATE transform_candidates SET instructions_sha256=? WHERE"
            " candidate_id=?", (ids.sha256_text("other instructions"),
                                b["candidate_id"])))
    elif variant == "output_role":
        w.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET role='transform_prompt' WHERE"
            " artifact_id=?", (b["output_aid"],)))
    elif variant == "source_role":
        w.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET role='transform_output' WHERE"
            " artifact_id=?", (b["source_aid"],)))


@drives("LF-M14-C116")
def c116_task_key_corruption(entry):
    obs, conds = {}, {}
    for variant in (None, "source_digest", "instructions_digest",
                    "output_role", "source_role"):
        name = variant or "control"
        with MWorld() as w:
            t = w.transform_task(f"corruption {name} source",
                                 [A_TEXT, B_TEXT])
            _corrupt(w, t, variant)
            was, _ = refused(judge_pair, w, t["task_key"],
                             t["candidates"][0]["candidate_id"],
                             t["candidates"][1]["candidate_id"],
                             "prefer_b")
            pkg, err = _pair_export(w)
            pref = _one_pref(pkg, t["task_key"]) if pkg else None
            obs[name] = {"writer_refused": was,
                         "export": "refused" if pkg is None else (
                             "exported" if pref else "excluded")}
            if variant is None:
                conds["control_exported_b"] = bool(pref) and (
                    chosen_of(pref) or {}).get("output_text") == B_TEXT
            else:
                conds[f"{name}_no_comparable_pair"] = pref is None
    return check(conds, obs, witness="same stored task key; candidate B's"
                 " source/instructions digest or artifact role corrupted"
                 " before the judgment; preference_pairs export")


@drives("LF-M14-C117")
def c117_single_accept_history(entry):
    with MWorld() as w:
        seqs = {"accept_undo": ("accept", "undo"),
                "accept_reject": ("accept", "reject"),
                "reject_accept": ("reject", "accept"),
                "applied_only": (),
                "accept": ("accept",)}
        cands = {}
        for name, seq in seqs.items():
            t = w.transform_task(f"single {name} source",
                                 [f"Single {name} output."])
            cid = t["candidates"][0]["candidate_id"]
            for j in seq:
                w.accept(t, cid, j)
            cands[name] = cid
        w.splits.assign()
        out, err = export_try(w, "ds", ("transform_supervised",))
        if out is None:
            return check({"export_built": False}, {"error": err})
        exs, _p, _m = package(w.tmp / "ds")
        # Identified by the literal output text each variant wrote (and
        # by candidate id where the record carries one).
        by_text = {f"Single {name} output.": name for name in seqs}
        got = set()
        for e in exs:
            if e.get("task_kind") != "transform_supervised":
                continue
            name = by_text.get(e.get("output_text"), "?")
            if e.get("candidate_id") not in (None, cands.get(name)):
                name = "?"
            got.add(name)
        want = {"accept_undo", "reject_accept", "accept"}
        return result(
            "PASS" if got == want else "FAIL",
            {"exported": sorted(got)},
            grading="decision", decision="m14-policy-r1:D07",
            witness="accept/undo/reject sequences on single candidates;"
                    " transform_supervised export",
            note=None if got == want else "target set differs from D07")


# =============================================================================
# family splits (C118–C125, S017, MR006)
# =============================================================================


@drives("LF-M14-C118")
def c118_positive_ten(entry):
    with MWorld() as w:
        fams = fams_of(w.families(10, asr=True))
        out = w.splits.assign()
        v = out["assignment_version"]
        parts, _e = pmap(w, v)
        row = w.one("SELECT family_count FROM split_assignments WHERE"
                    " assignment_version=?", (v,))
        conds = {
            "ten_families_counted": len(set(fams)) == 10 and row[0] == 10,
            "assignment_permitted": all(p != ["unassigned"]
                                        for p in parts.values()),
            "one_partition_per_family": all(len(p) == 1
                                            for p in parts.values()),
            "partition_is_published_hash": all(
                parts.get(f) == [family_bucket(f)] for f in fams),
        }
        return check(conds, {"partitions": collections.Counter(
            p[0] for p in parts.values())}, witness="families(10,"
            " asr=True) → SplitService.assign; recount by family_bucket")


def _nine_families(w, per=3):
    fams = []
    for i in range(9):
        j = w.job(f"nine floor family {i} first")
        fams.append(j["family_id"])
        for k in range(per - 1):
            w.job(f"nine floor family {i} member {k}",
                  family=j["family_id"])
    return fams


@drives("LF-M14-C119")
def c119_nine_floor(entry):
    with MWorld() as w:
        fams = _nine_families(w)
        out = w.splits.assign()
        v = out["assignment_version"]
        parts, _e = pmap(w, v)
        members = w.one("SELECT COUNT(*) FROM training_memberships WHERE"
                        " assignment_version=?", (v,))[0]
        tenth = w.job("tenth independent family")
        out2 = w.splits.assign()
        parts2, _e2 = pmap(w, out2["assignment_version"])
        conds = {
            "nine_not_27_counted": out.get("families") == 9
            and members == 27,
            "no_invented_assignment": set(parts) == set(fams) and all(
                p == ["unassigned"] for p in parts.values()),
            "honest_reason": "insufficient" in str(
                out.get("unassigned_reason")),
            "tenth_family_positive": all(
                parts2.get(f) == [family_bucket(f)]
                for f in fams + [tenth["family_id"]]),
        }
        return check(conds, {"families": out.get("families"),
                             "examples": members,
                             "reason": out.get("unassigned_reason")},
                     witness="9 families x 3 examples → assign; then a"
                             " tenth family → assign")


@drives("LF-M14-S017")
def s017_nine_versus_ten(entry):
    with MWorld() as w:
        fams = _nine_families(w, per=2)
        v1 = w.splits.assign()
        latch = Latch("m14_s017_authority_boundary", block=False)
        p1, _ = pmap(w, v1["assignment_version"])
        if any(p != ["unassigned"] for p in p1.values()):
            return check({"nine_family_floor_refused": False},
                         {"families": v1.get("families")})
        latch.hit()  # after the nine-family floor refusal
        # Not independent: one more example of an existing family.
        w.job("extra member of family zero", family=fams[0])
        v2 = w.splits.assign()
        p2, _ = pmap(w, v2["assignment_version"])
        # Genuinely independent: a new family.
        new = w.job("genuinely independent tenth family")
        v3 = w.splits.assign()
        p3, _ = pmap(w, v3["assignment_version"])
    with MWorld() as w2:  # alternate order: family first, then example
        fams2 = _nine_families(w2, per=2)
        new2 = w2.job("independent tenth family first")
        w2.job("extra member after", family=fams2[0])
        v4 = w2.splits.assign()
        p4, _ = pmap(w2, v4["assignment_version"])
    conds = {
        "extra_example_not_a_family": v2.get("families") == 9 and all(
            p == ["unassigned"] for p in p2.values()),
        "ten_families_assigned": v3.get("families") == 10 and all(
            p3.get(f) == [family_bucket(f)]
            for f in fams + [new["family_id"]]),
        "alternate_order_assigned": all(
            p4.get(f) == [family_bucket(f)]
            for f in fams2 + [new2["family_id"]]),
    }
    return check(conds, {"families": [v1.get("families"), v2.get(
        "families"), v3.get("families"), v4.get("families")]},
        reached=bool(latch.hits), witness="latch after the nine-family"
        " refusal; extra member (not independent) then a new family")


@drives("LF-M14-C120", "LF-M14-MR006")
def c120_permutation(entry):
    fam_ids = [f"fam-synth-perm-{k}" for k in range(12)] + \
        [frozen_family_id(0), frozen_family_id(1)]

    def build(order):
        w = MWorld()
        for i in order:
            w.job(f"permutation family {i} first", family=fam_ids[i])
            w.job(f"permutation family {i} second", family=fam_ids[i])
        v = w.splits.assign()["assignment_version"]
        parts, _ = pmap(w, v)
        w.close()
        return parts
    fwd = build(range(len(fam_ids)))
    rev = build(reversed(range(len(fam_ids))))
    expected = {f: [family_bucket(f)] for f in fam_ids}
    kinds = {p[0] for p in expected.values()}
    if len(kinds) < 2:
        return invalid("degenerate family fixture")
    conds = {"maps_identical": fwd == rev,
             "map_is_published_hash": fwd == expected}
    return check(conds, {"partitions": sorted(kinds)},
                 witness="two stores; same 14 family ids (2 frozen by"
                         " hash) inserted forward vs reversed")


@drives("LF-M14-C121")
def c121_related_variants(entry):
    with MWorld() as w:
        fixture = w.families(11, asr=True, frozen=1)
        frozen_fam = fixture[0]["family_id"]
        train_fam = next(j["family_id"] for j in fixture[1:]
                         if family_bucket(j["family_id"]) == "train")
        crop = w.ready_asr(family=frozen_fam)            # crop variant
        w.rewrite_envelope(fixture[0]["example_id"],     # retry
                           lambda e: e.update(attempt=2))
        near = w.ready_asr(family=train_fam)              # near-duplicate
        t = w.transform_task("related variant task", [A_TEXT, B_TEXT])
        judge_pair(w, t["task_key"], t["candidates"][0]["candidate_id"],
                   t["candidates"][1]["candidate_id"], "prefer_a")
        w.accept(t, t["candidates"][0]["candidate_id"])
        v = w.splits.assign()["assignment_version"]
        spanning = w.rows(
            "SELECT family_id FROM training_memberships WHERE"
            " assignment_version=? GROUP BY family_id HAVING"
            " COUNT(DISTINCT partition) > 1", (v,))
        parts, _ = pmap(w, v)
        members = w.one("SELECT COUNT(*) FROM training_memberships WHERE"
                        " assignment_version=? AND family_id=?",
                        (v, frozen_fam))[0]
        out, err = export_try(w, "ds", ("asr_supervised",
                                        "transform_supervised",
                                        "preference_pairs"))
        if out is None:
            return check({"export_built": False}, {"error": err})
        exs, prefs, _m = package(w.tmp / "ds")
        split_by_fam = collections.defaultdict(set)
        for e in exs:
            if e.get("family_id"):
                split_by_fam[e["family_id"]].add(e.get("split"))
        task_rows = [e for e in exs if e.get("task_key")] + prefs
        conds = {
            "variants_share_family": crop["family_id"] == frozen_fam
            and near["family_id"] == train_fam and members == 2,
            "no_family_spans_in_store": spanning == [],
            "family_partition_is_hash": parts.get(frozen_fam)
            == ["frozen_test"] and parts.get(train_fam) == ["train"],
            "no_family_spans_in_export": all(
                len(s) == 1 for s in split_by_fam.values())
            and split_by_fam.get(frozen_fam) == {"frozen_test"},
            "task_rows_unpartitioned": bool(task_rows) and all(
                r.get("split") == "unpartitioned" for r in task_rows),
        }
        return check(conds, {"families": len(parts),
                             "exported_families": len(split_by_fam),
                             "task_rows": len(task_rows)},
                     witness="crop + retry of a frozen family, near-dup of"
                             " a train family, task-keyed variants")


@drives("LF-M14-C122")
def c122_family_corruption(entry):
    with MWorld() as w:
        fixture = w.families(12, asr=True)
        for j in list(fixture):
            w.ready_asr(family=j["family_id"])
        v = w.splits.assign()["assignment_version"]
        ok, err0 = export_try(w, "ds0", ("asr_supervised",))
        target = next(j["family_id"] for j in fixture
                      if family_bucket(j["family_id"]) == "train")
        victim = w.rows("SELECT example_id FROM training_memberships"
                        " WHERE assignment_version=? AND family_id=?"
                        " ORDER BY example_id", (v, target))[0][0]
        w.store.submit(lambda c: c.execute(
            "UPDATE training_memberships SET partition='validation' WHERE"
            " assignment_version=? AND example_id=?", (v, victim)))
        recount = [r[0] for r in w.rows(
            "SELECT family_id FROM training_memberships WHERE"
            " assignment_version=? GROUP BY family_id HAVING"
            " COUNT(DISTINCT partition) > 1", (v,))]
        cont = w.splits.contamination()
        out, err = export_try(w, "ds1", ("asr_supervised",))
        conds = {
            "positive_export_before_corruption": ok is not None,
            "independent_recount_sees_leak": recount == [target],
            "contamination_reports_leak": (cont.get(
                "families_spanning_partitions") or 0) >= 1,
            "export_rejects_leak": out is None
            and "leak" in (err or "").lower(),
            "nothing_published": not (w.tmp / "ds1").exists(),
        }
        return check(conds, {"spanning": cont.get(
            "families_spanning_partitions"), "refused": out is None},
            witness="one member of a train family rewritten to validation"
                    " in the same version")


@drives("LF-M14-C123")
def c123_tags_not_partitions(entry):
    with MWorld() as w:
        fixture = w.families(12, frozen=2)
        v1 = w.splits.assign()["assignment_version"]
        rows1 = sorted(w.rows("SELECT example_id, family_id, partition,"
                              " exposed FROM training_memberships WHERE"
                              " assignment_version=?", (v1,)))
        for j in fixture:
            w.splits.set_tag(j["example_id"], "hard_example")
            w.splits.set_tag(j["example_id"], "short_command")
        w.sampling.refresh(percent=50.0)
        tags = w.one("SELECT COUNT(*) FROM example_tags")[0]
        decided = w.one("SELECT COUNT(*) FROM sampling_decisions")[0]
        n_versions = versions(w)
        rows1b = sorted(w.rows("SELECT example_id, family_id, partition,"
                               " exposed FROM training_memberships WHERE"
                               " assignment_version=?", (v1,)))
        v2 = w.splits.assign()["assignment_version"]
        rows2 = sorted(w.rows("SELECT example_id, family_id, partition,"
                              " exposed FROM training_memberships WHERE"
                              " assignment_version=?", (v2,)))
        frozen = [j["family_id"] for j in fixture[:2]]
        conds = {
            "tags_and_sampling_recorded": tags == 24 and decided == 12,
            "tagging_mints_no_version": n_versions == 1,
            "current_rows_untouched": rows1b == rows1,
            "next_version_same_partitions": rows2 == rows1,
            "tagged_frozen_stays_frozen": all(
                pmap(w, v2)[0].get(f) == ["frozen_test"] for f in frozen),
        }
        return check(conds, {"tags": tags, "decisions": decided},
                     witness="set_tag x2 per example + sampling refresh"
                             " between two assignments")


@drives("LF-M14-C124")
def c124_unknown_assign_retry(entry):
    with MWorld() as w:
        w.families(10)
        fn = w.splits.assign
        has_op = accepts(fn, "operation_id")
        kw = {"operation_id": "op-d-assign-1"} if has_op else {}
        original = w.store.submit
        fired = []

        def submit(f, wait=True, timeout=15.0):
            out = original(f, wait=wait, timeout=timeout)
            if "SplitService.assign" in getattr(f, "__qualname__", "") \
                    and not fired:
                fired.append(True)
                raise TimeoutError("synthetic: admitted, outcome unknown")
            return out
        w.store.submit = submit
        try:
            timed_out, _ = refused(fn, **kw)
        finally:
            w.store.submit = original
        if not fired:
            return invalid("assign writer op never admitted")
        committed = versions(w)
        retry = fn(**kw)
        after_retry = versions(w)
        kw2 = {"operation_id": "op-d-assign-2"} if has_op else {}
        fresh = fn(**kw2)
        conds = {
            "first_attempt_committed_but_unknown": timed_out
            and committed == 1,
            "retry_one_version": after_retry == 1
            and retry.get("assignment_version") == 1,
            "new_logical_action_mints": fresh.get("assignment_version")
            == 2 and versions(w) == 2,
        }
        return check(conds, {"operation_id_supported": has_op,
                             "versions": [committed, after_retry,
                                          versions(w)]},
                     witness="submit seam raises TimeoutError after the"
                             " assign op commits; same operation id retried")


@drives("LF-M14-C125")
def c125_task_rows(entry):
    with MWorld() as w:
        w.families(30, asr=True, frozen=3)
        t = w.transform_task("task row source", [A_TEXT, B_TEXT])
        a, b = (c["candidate_id"] for c in t["candidates"])
        judge_pair(w, t["task_key"], a, b, "prefer_a")
        w.accept(t, a)
        w.splits.assign()
        views = ("asr_supervised", "transform_supervised",
                 "preference_pairs")
        full, err = export_try(w, "ds_all", views)
        hold, err2 = export_try(w, "ds_hold", views,
                                partitions=("validation", "frozen_test"))
        if full is None or hold is None:
            return check({"exports_built": False},
                         {"errors": [err, err2]})
        exs, prefs, man = package(w.tmp / "ds_all")
        hexs, hprefs, hman = package(w.tmp / "ds_hold")
        task_rows = [e for e in exs if e.get("task_key")] + prefs
        excl = {(e.get("candidate_id") or e.get("task_key"),
                 e.get("reason")) for e in hman.get("excluded") or ()}
        scope = (man.get("partition_scope") or {}).get("unpartitioned")
        ok = {
            "task_rows_exported_with_train": len(task_rows) == 2,
            "explicitly_unpartitioned": all(
                r.get("split") == "unpartitioned"
                and r.get("holdout_qualified") is False
                and not r.get("family_id") for r in task_rows),
            "manifest_names_scope": sorted(scope or []) == [
                "preference_pairs", "transform_supervised"],
            "holdout_package_has_none": not [
                e for e in hexs if e.get("task_key")] and not hprefs,
            "holdout_lists_them_excluded": {
                (a, "task_keyed_unpartitioned"),
                (t["task_key"], "task_keyed_unpartitioned")} <= excl,
        }
        failed = [k for k, v in ok.items() if not v]
        return result("FAIL" if failed else "PASS",
                      {"task_rows": len(task_rows),
                       "holdout_excluded": len(excl)},
                      grading="decision", decision="m14-policy-r1:D02",
                      note=("failed: " + ", ".join(failed)) if failed
                      else None,
                      witness="export all partitions vs validation+"
                              "frozen_test only")


# =============================================================================
# exposed test families (C126–C131, S018, MR007)
# =============================================================================


def _exposure_world(n=30, frozen=3):
    w = MWorld()
    fixture = w.families(n, asr=True, frozen=frozen)
    fams = fams_of(fixture)
    return w, fams, [f for f in fams if family_bucket(f) == "frozen_test"]


@drives("LF-M14-C126")
def c126_positive_blind(entry):
    w, fams, frozen = _exposure_world()
    try:
        v1 = w.splits.assign()["assignment_version"]
        out, err = export_try(w, "ds", ("asr_supervised",),
                              partitions=("frozen_test",))
        if out is None:
            return check({"blind_export_built": False}, {"error": err})
        exs, _p, man = package(w.tmp / "ds")
        got = {e["family_id"] for e in exs}
        w.splits.mark_exposed([frozen[0]], "inspected_during_tuning")
        out2, err2 = export_try(w, "ds2", ("asr_supervised",),
                                partitions=("frozen_test",))
        exs2, _p2, man2 = package(w.tmp / "ds2") if out2 else ([], [], {})
        conds = {
            "blind_families_exact": got == set(frozen),
            "blind_rows_unexposed_frozen": bool(exs) and all(
                e.get("split") == "frozen_test" and e.get("exposed")
                is False for e in exs),
            "exposure_evidence_complete": man.get("assignment_version")
            == v1 and man.get("exposure_checked_through_version") == v1,
            "after_exposure_no_blind_claim": out2 is not None
            and not blind_claims(exs2, frozen[0])
            and {e["family_id"] for e in exs2} == set(frozen[1:])
            and man2.get("exposure_checked_through_version") == 2,
        }
        return check(conds, {"frozen_families": len(frozen),
                             "exported": len(got)},
                     witness="families(30, frozen=3) → assign → frozen_test"
                             " export; then expose one → export again")
    finally:
        w.close()


@drives("LF-M14-C127")
def c127_next_version(entry):
    w, fams, frozen = _exposure_world()
    try:
        w.splits.assign()
        w.splits.mark_exposed([frozen[0]], "inspected_during_tuning")
        new = [w.ready_asr(family=frozen_family_id(10 + i))["family_id"]
               for i in range(2)] + [w.ready_asr()["family_id"]]
        v3 = w.splits.assign()["assignment_version"]
        parts, exp = pmap(w, v3)
        conds = {
            "exposed_stays_non_frozen": parts.get(frozen[0]) == ["train"]
            and exp.get(frozen[0]) == [1],
            "unexposed_frozen_still_frozen": all(
                parts.get(f) == ["frozen_test"] and exp.get(f) == [0]
                for f in frozen[1:]),
            "new_families_by_hash": all(parts.get(f) == [family_bucket(f)]
                                        for f in new),
        }
        return check(conds, {"version": v3}, witness="assign, expose,"
                     " add 3 families (2 frozen by hash), assign again")
    finally:
        w.close()


@drives("LF-M14-C128")
def c128_absent_version(entry):
    w, fams, frozen = _exposure_world()
    try:
        w.splits.assign()
        w.splits.mark_exposed([frozen[0]], "inspected_during_tuning")
        members = {f: [r[0] for r in w.rows(
            "SELECT example_id FROM training_examples WHERE family_id=?",
            (f,))] for f in frozen[:2]}
        for exs in members.values():
            for ex in exs:
                w.training.exclude(ex, True)
        v3 = w.splits.assign()["assignment_version"]
        p3, _ = pmap(w, v3)
        for exs in members.values():
            for ex in exs:
                w.training.exclude(ex, False)
        v4 = w.splits.assign()["assignment_version"]
        p4, e4 = pmap(w, v4)
        out, err = export_try(w, "ds", ("asr_supervised",))
        exs_out = package(w.tmp / "ds")[0] if out else []
        conds = {
            "absent_for_a_version": frozen[0] not in p3
            and frozen[1] not in p3,
            "exposure_remembered": p4.get(frozen[0]) == ["train"]
            and e4.get(frozen[0]) == [1],
            "control_unexposed_returns_frozen": p4.get(frozen[1])
            == ["frozen_test"] and e4.get(frozen[1]) == [0],
            "export_honest": out is not None and not blind_claims(
                exs_out, frozen[0]) and any(
                e.get("family_id") == frozen[0] and e.get("exposed")
                for e in exs_out),
        }
        return check(conds, {"versions": [v3, v4]}, witness="expose;"
                     " exclude all members (and a control frozen family);"
                     " assign; restore; assign")
    finally:
        w.close()


@drives("LF-M14-C129")
def c129_old_version_export(entry):
    w, fams, frozen = _exposure_world()
    try:
        v1 = w.splits.assign()["assignment_version"]
        pre, err0 = export_try(w, "ds_pre", ("asr_supervised",),
                               partitions=("frozen_test",),
                               assignment_version=v1)
        pre_claims = blind_claims(package(w.tmp / "ds_pre")[0],
                                  frozen[0]) if pre else []
        w.splits.mark_exposed([frozen[0]], "inspected_during_tuning")
        obs, conds = {"pre_exposure_claims": len(pre_claims)}, {}
        conds["pre_exposure_blind_export_positive"] = bool(pre_claims)
        for name, parts in (("frozen_only", ("frozen_test",)),
                            ("all", ("train", "validation",
                                     "frozen_test"))):
            out, err = export_try(w, f"ds_{name}", ("asr_supervised",),
                                  partitions=parts, assignment_version=v1)
            claims = blind_claims(package(w.tmp / f"ds_{name}")[0],
                                  frozen[0]) if out else []
            obs[name] = "refused" if out is None else \
                f"built:{len(claims)} claims"
            conds[f"{name}_no_fresh_blind_claim"] = not claims
        return check(conds, obs, witness="NEW export selecting v1 after"
                     " the family was exposed in v2 (D10 all-history join)")
    finally:
        w.close()


@drives("LF-M14-C130")
def c130_exposed_development(entry):
    w, fams, frozen = _exposure_world()
    try:
        w.splits.assign()
        w.splits.mark_exposed([frozen[0]], "inspected_during_tuning")
        out, err = export_try(w, "ds", ("asr_supervised",),
                              partitions=("train",))
        if out is None:
            return check({"export_allowed": False}, {"error": err})
        exs = package(w.tmp / "ds")[0]
        mine = [e for e in exs if e.get("family_id") == frozen[0]]
        others = [e for e in exs if e.get("family_id") != frozen[0]]
        conds = {
            "export_allowed": True,
            "exposed_family_exported": bool(mine),
            "honest_exposed_flag": all(e.get("exposed") is True
                                       and e.get("split") == "train"
                                       for e in mine),
            "unexposed_train_flag_false": bool(others) and all(
                e.get("exposed") is False for e in others),
        }
        return check(conds, {"exposed_rows": len(mine),
                             "other_rows": len(others)},
                     witness="expose frozen family (now train) → export"
                             " train")
    finally:
        w.close()


@drives("LF-M14-C131")
def c131_unknown_family(entry):
    with MWorld() as w:
        fixture = w.families(12, frozen=1)
        frozen = fixture[0]["family_id"]
        pre, _ = refused(w.splits.mark_exposed, ["fam-synth-never"],
                         "inspected")
        pre_versions = versions(w)
        v1 = w.splits.assign()["assignment_version"]
        snap = sorted(w.rows("SELECT * FROM training_memberships"))
        unknown, _ = refused(w.splits.mark_exposed,
                             ["fam-synth-never-assigned"], "inspected")
        train_known = next(j["family_id"] for j in fixture[1:]
                           if family_bucket(j["family_id"]) == "train")
        mixed, _ = refused(w.splits.mark_exposed,
                           [train_known, "fam-synth-never-assigned"],
                           "inspected")
        unchanged = sorted(w.rows("SELECT * FROM training_memberships")) \
            == snap and versions(w) == 1 and w.one(
            "SELECT COUNT(*) FROM example_tags")[0] == 0
        ok = w.splits.mark_exposed([frozen], "inspected_during_tuning")
        parts, exp = pmap(w, ok["assignment_version"])
        conds = {
            "refused_before_any_assignment": pre and pre_versions == 0,
            "unknown_refused": unknown,
            "mixed_refused_whole": mixed,
            "no_fabrication_or_reset": unchanged and pmap(w, v1)[0].get(
                frozen) == ["frozen_test"],
            "known_family_positive": parts.get(frozen) == ["train"]
            and exp.get(frozen) == [1] and versions(w) == 2,
        }
        return check(conds, {"versions": versions(w)},
                     witness="mark_exposed on never-assigned ids (before"
                             " and after assign, alone and mixed); known"
                             " frozen family as the positive")


def _s018_world(expose, order):
    w, fams, frozen = _exposure_world()
    try:
        v1 = w.splits.assign()["assignment_version"]
        latch = Latch("m14_s018_authority_boundary", block=False)

        def add_and_assign():
            w.ready_asr(family=frozen_family_id(20))
            w.ready_asr()
            return w.splits.assign()["assignment_version"]
        if order == "expose_first":
            if expose:
                w.splits.mark_exposed([frozen[0]], "inspected")
            latch.hit()
            add_and_assign()
        else:
            add_and_assign()
            if expose:
                w.splits.mark_exposed([frozen[0]], "inspected")
            latch.hit()
        last = w.splits.current_version()
        parts, exp = pmap(w, last)
        new_frozen = frozen_family_id(20)
        out, err = export_try(w, "ds_old", ("asr_supervised",),
                              partitions=("frozen_test",),
                              assignment_version=v1)
        claims = blind_claims(package(w.tmp / "ds_old")[0],
                              frozen[0]) if out else []
        return {"reached": latch.hits, "latest": parts.get(frozen[0]),
                "latest_exposed": exp.get(frozen[0]),
                "new_frozen": parts.get(new_frozen),
                "old_export": "refused" if out is None else "built",
                "old_claims": len(claims)}
    finally:
        w.close()


@drives("LF-M14-S018")
def s018_exposed_through_next_version(entry):
    runs = {"exposed": _s018_world(True, "expose_first"),
            "exposed_alt_order": _s018_world(True, "assign_first"),
            "control": _s018_world(False, "expose_first")}
    if not all(r["reached"] for r in runs.values()):
        return invalid("barrier never reached", runs, reached=False)
    e, alt, c = runs["exposed"], runs["exposed_alt_order"], runs["control"]
    conds = {
        "exposed_never_frozen": e["latest"] == ["train"]
        and e["latest_exposed"] == [1],
        "alt_order_never_frozen": alt["latest"] == ["train"]
        and alt["latest_exposed"] == [1],
        "old_version_export_no_blind_claim": e["old_claims"] == 0
        and alt["old_claims"] == 0,
        "replenished_with_new_family": e["new_frozen"] == ["frozen_test"],
        "control_stays_frozen_and_blind": c["latest"] == ["frozen_test"]
        and c["old_export"] == "built" and c["old_claims"] > 0,
    }
    return check(conds, runs, reached=True, witness="latch after exposure;"
                 " add families + assign; NEW export of v1 frozen_test;"
                 " alternate order and unexposed control")


@drives("LF-M14-MR007")
def mr007_exposure_forward_only(entry):
    def run(expose):
        w, fams, frozen = _exposure_world()
        try:
            f = frozen[0]
            w.splits.assign()
            if expose:
                w.splits.mark_exposed([f], "inspected")
            w.splits.assign()
            w.ready_asr(family=frozen_family_id(30))
            w.splits.assign()
            last = w.splits.current_version()
            member_claims = w.rows(
                "SELECT assignment_version FROM training_memberships"
                " WHERE family_id=? AND partition='frozen_test' AND"
                " exposed=0 AND assignment_version>=2", (f,))
            export_claims = {}
            for v in range(1, last + 1):
                for name, parts in (("frozen", ("frozen_test",)),
                                    ("all", ("train", "validation",
                                             "frozen_test"))):
                    dest = f"ds_v{v}_{name}"
                    out, _err = export_try(w, dest, ("asr_supervised",),
                                           partitions=parts,
                                           assignment_version=v)
                    export_claims[dest] = len(blind_claims(
                        package(w.tmp / dest)[0], f)) if out else "refused"
            return {"membership_claims": len(member_claims),
                    "export_claims": export_claims}
        finally:
            w.close()
    exposed, twin = run(True), run(False)
    claims = [v for v in exposed["export_claims"].values()
              if v != "refused" and v > 0]
    twin_claims = [v for v in twin["export_claims"].values()
                   if v != "refused" and v > 0]
    if not twin_claims:
        return invalid("unexposed twin never claims the family blind —"
                       " the relation would be vacuous",
                       {"exposed": exposed, "twin": twin})
    conds = {"no_later_membership_claim": exposed["membership_claims"] == 0,
             "no_new_export_claim": not claims}
    return check(conds, {"exposed": exposed, "twin": twin},
                 witness="expose then two later assignments and NEW exports"
                         " from every version; unexposed twin as the"
                         " non-vacuity control")
