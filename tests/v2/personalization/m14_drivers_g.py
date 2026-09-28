"""M14 corpus drivers, group g: Your Voice profile cards, profile
invalidation, M13 usage redaction, the idle profile pass and privacy.

Categories covered (frozen corpus tests/v2/personalization/
m14_audit_corpus.json):

- profile_cards (LF-M14-C184..C189)
- profile_invalidation (LF-M14-C190..C196, probes S023, S024, S034)
- m13_usage_redaction (LF-M14-C197..C204, probe S025, relation MR009)
- idle_profile_pass (LF-M14-C205..C210, probes S026, S027, relation
  MR012)
- privacy (LF-M14-C220..C226)
- relations MR004 (evidence-deletion monotonicity) and MR008 (profile
  floor)

Every driver builds a fresh synthetic ``MWorld`` (temp store, fixed
clock, ``com.synthetic.*`` apps), runs the real production services
(ProfileService, AnalyticsStore, LearningService, ReviewService,
TrainingDataService, DatasetExporter, the lifecycle AppDelegate) and
grades against its own bookkeeping — the texts, word counts, labels,
applied rules and usage facts it wrote, raw SQL rows and file bytes —
never the production reducer under test. Mid-compute interleavings use
a patched ``ProfileService._read_candidates`` (records that a text
chunk was read) plus ``after_each_op`` (the action runs in the caller
thread between writer ops), so no writer op ever waits on another. The
idle "zero transcript reads" oracle is an SQLite trace callback on the
store's writer connection counting SELECTs of artifact content, proven
live in a changed pass before a zero is trusted.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import m14_world as W  # noqa: E402
from m14_world import (APP, PRIVATE_CANARY, MWorld, accepts,  # noqa: E402
                       after_each_op, patched, read_jsonl, wav_frames)
from m14_drivers_common import check, drives, invalid  # noqa: E402

from localflow.v2 import analytics as analytics_mod  # noqa: E402
from localflow.v2 import profile as profile_mod  # noqa: E402
from localflow.v2.store import TRAINABLE_STATES  # noqa: E402

ROOT = W.ROOT
PHRASE = f"zephyr {PRIVATE_CANARY.lower()}"
PHRASE2 = "quillon marrow"
FLOOR_WORDS = 2000


# =============================================================================
# fixture bookkeeping (the independent side)
# =============================================================================

class Cohort:
    """Synthetic eligible speech whose every countable fact is recorded
    here as it is written: text, word count, applied rules, labels,
    self-correction counts. ``gone`` holds examples the driver removed
    from eligibility (deleted, purged, excluded, background)."""

    def __init__(self, w):
        self.w = w
        self.info = {}      # example_id -> dict
        self.order = []
        self.terms = {}     # entry_id -> canonical
        self.gone = set()

    def add(self, i, n_words, *, phrases=(), rules=(), counts=None,
            prefix="t"):
        words = [f"{prefix}{i}q{k}" for k in range(n_words)]
        pos = 3
        for ph in phrases:
            parts = ph.split()
            words[pos:pos + len(parts)] = parts
            pos += len(parts) + 3
        text = " ".join(words)
        j = self.w.job(text, audio=False, applied_rule_ids=list(rules),
                       cleanup_counts=counts)
        ex = j["example_id"]
        self.info[ex] = {"i": i, "job": j, "text": text,
                         "words": len(text.split()), "rules": list(rules),
                         "phrases": list(phrases), "label": None,
                         "counts": counts}
        self.order.append(ex)
        return ex

    def ex(self, i):
        return self.order[i]

    def label(self, i, kind, **kw):
        ex = self.ex(i)
        self.w.review.record_label(ex, edit_kind=kind, **kw)
        self.info[ex]["label"] = None if kw.get("abstained") else kind
        return ex

    @property
    def eligible(self):
        return [e for e in self.order if e not in self.gone]

    def words(self):
        return sum(self.info[e]["words"] for e in self.eligible)


def cohort(w, n=11, base=200, *, phrase_at=(0, 1), terms_at=(2, 3, 4),
           labels=None, counts=None, prefix="t", term="Terraform"):
    """``n`` eligible dictations of ``base + i`` distinct words; PHRASE
    planted in ``phrase_at``; one approved dictionary term applied in
    ``terms_at``; ``labels`` {i: kind}; ``counts`` {i: corrections}."""
    c = Cohort(w)
    eid = None
    if terms_at:
        eid = w.vocab.add_entry(term, [(term.lower() + "x", True)],
                                approved=True)
        w.vocab.record_hits([eid])
        c.terms[eid] = term
    for i in range(n):
        c.add(i, base + i, phrases=(PHRASE,) if i in phrase_at else (),
              rules=[eid] if eid and i in terms_at else (),
              counts=(counts or {}).get(i), prefix=prefix)
    for i, kind in (labels or {}).items():
        c.label(i, kind)
    c.term_id = eid
    return c


def tech_terms(m):
    """{term: entry} from measured.technical_terms; a bare string entry
    (no cited support) maps to an entry with no dictations or ids."""
    out = {}
    for t in m.get("technical_terms") or []:
        if isinstance(t, dict):
            out[t.get("term")] = t
        else:
            out[t] = {"term": t, "dictations": None, "example_ids": []}
    return out


def card_problems(snap, c, *, min_words=FLOOR_WORDS, active_terms=None):
    """The independent card/measured oracle: every claim follows its own
    live support in the cohort's bookkeeping. Returns problem codes."""
    probs = []
    if snap is None:
        return ["no_snapshot"]
    m = snap.get("measured") or {}
    cards = snap.get("cards") or []
    elig = c.eligible
    lengths = {e: c.info[e]["words"] for e in elig}
    if m.get("eligible_examples") != len(elig):
        probs.append("eligible_examples")
    if m.get("eligible_words") != sum(lengths.values()):
        probs.append("eligible_words")
    # Phrases: only planted phrases, each citing exactly the eligible
    # examples that carry it.
    planted = {}
    for e in elig:
        for ph in c.info[e]["phrases"]:
            planted.setdefault(ph, []).append(e)
    want = {ph: sorted(es) for ph, es in planted.items() if len(es) >= 2}
    got = {p["phrase"]: p for p in m.get("frequent_phrases") or []}
    if set(got) != set(want):
        probs.append("phrase_set")
    for ph, p in got.items():
        if ph in want and (p.get("count") != len(want[ph])
                           or sorted(p.get("example_ids") or [])
                           != want[ph][:5]):
            probs.append(f"phrase_support:{ph[:6]}")
    # Technical terms: approved rules applied in eligible speech.
    terms = active_terms if active_terms is not None else c.terms
    want_t = {}
    for e in elig:
        for rid in c.info[e]["rules"]:
            if rid in terms:
                want_t.setdefault(terms[rid], []).append(e)
    got_t = tech_terms(m)
    if set(got_t) != set(want_t):
        probs.append("technical_set")
    for term, t in got_t.items():
        exs = sorted(want_t.get(term, []))
        if t.get("dictations") != len(exs) or \
                sorted(t.get("example_ids") or []) != exs[:5]:
            probs.append(f"technical_support:{term}")
    # Labels.
    kinds = {}
    for e in elig:
        k = c.info[e]["label"]
        if k:
            kinds.setdefault(k, []).append(e)
    if (m.get("corrections_by_kind") or {}) != {
            k: len(v) for k, v in kinds.items()}:
        probs.append("corrections_by_kind")
    # Cards.
    enough = sum(lengths.values()) >= min_words and len(elig) >= 10
    ids_ = {card.get("card_id") for card in cards}
    if not enough:
        if cards:
            probs.append("card_below_floor")
        return probs
    expect = {"style-length"}
    if kinds:
        expect.add("correction-focus")
    if want_t:
        expect.add("technical-vocabulary")
    if ids_ != expect:
        probs.append(f"card_set:{sorted(ids_)}")
    for card in cards:
        cid = card.get("card_id")
        ev = list(card.get("evidence_example_ids") or [])
        if not ev or any(e not in lengths for e in ev):
            probs.append(f"{cid}:cites_ineligible")
            continue
        if cid == "style-length":
            med = statistics.median(lengths.values())
            if f"{med:g}" not in card.get("statement", ""):
                probs.append("style-length:median")
            dist = {e: abs(lengths[e] - med) for e in lengths}
            uncited = [dist[e] for e in lengths if e not in ev]
            if len(ev) != min(5, len(lengths)) or (
                    uncited and max(dist[e] for e in ev) > min(uncited)):
                probs.append("style-length:not_nearest")
        elif cid == "correction-focus":
            top = max(sorted(kinds), key=lambda k: len(kinds[k]))
            if sorted(ev) != sorted(kinds[top])[:5] or \
                    top.replace("_", " ") not in card.get("title", ""):
                probs.append("correction-focus:support")
        elif cid == "technical-vocabulary":
            applied = sorted({e for es in want_t.values() for e in es})
            if sorted(ev) != applied[:5]:
                probs.append("technical-vocabulary:support")
        else:
            probs.append(f"unexplained_card:{cid}")
    return probs


# =============================================================================
# seams and instruments
# =============================================================================

@contextlib.contextmanager
def after_read(w, action):
    """Run ``action()`` once, in the caller thread, right after the
    first profile text-chunk read op returns (between writer ops — the
    read has happened, the publishing op has not). ``state['reads']``
    counts chunk reads (a restart reads again)."""
    state = {"reads": 0, "fired": 0}

    def wrap(original):
        def read(self, conn, example_ids):
            out = original(self, conn, example_ids)
            state["reads"] += 1
            return out
        return read

    def hook():
        if state["reads"] and not state["fired"]:
            state["fired"] += 1
            action()
    with patched(profile_mod.ProfileService, "_read_candidates", wrap), \
            after_each_op(w.store, hook):
        yield state


class ContentReads:
    """Independent transcript-read counter: an SQLite trace callback on
    the store's writer connection counts every executed SELECT that
    reads artifact content (content_text / content_path)."""

    def __init__(self, w):
        self.w = w
        self.n = 0

    def _cb(self, stmt):
        s = stmt.lstrip().lower()
        if s.startswith("select") and ("content_text" in s
                                       or "content_path" in s):
            self.n += 1

    def __enter__(self):
        self.w.store.submit(lambda c: c.set_trace_callback(self._cb))
        return self

    def __exit__(self, *exc):
        self.w.store.submit(lambda c: c.set_trace_callback(None))

    def take(self):
        self.w.store.sync()
        n, self.n = self.n, 0
        return n


def snapshots(w):
    return w.one("SELECT COUNT(*) FROM profile_snapshots")[0]


def snap_row(w, sid):
    r = w.one("SELECT state, invalidated_reason, measured_json, cards_json,"
              " algorithm_version FROM profile_snapshots WHERE"
              " snapshot_id=?", (sid,))
    return None if r is None else {
        "state": r[0], "reason": r[1], "measured": json.loads(r[2] or "{}"),
        "cards": json.loads(r[3] or "[]"), "algorithm_version": r[4]}


def all_snap_rows(w):
    return [(r[0], json.loads(r[1] or "{}"), r[2]) for r in w.rows(
        "SELECT snapshot_id, measured_json, state FROM profile_snapshots"
        " ORDER BY rowid")]


def evidence_ids(w, sid, role=None):
    sql = ("SELECT DISTINCT example_id FROM profile_evidence WHERE"
           " snapshot_id=? AND included=1")
    args = [sid]
    if role:
        sql += " AND role=?"
        args.append(role)
    return {r[0] for r in w.rows(sql, tuple(args))}


def latest_id(w):
    r = w.one("SELECT snapshot_id FROM profile_snapshots ORDER BY rowid"
              " DESC LIMIT 1")
    return r[0] if r else None


def usage(w):
    return analytics_mod.AnalyticsStore(w.store, emit=w._emit,
                                        now_fn=w.clock,
                                        reporting_timezone="UTC")


def blob(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def phrase_in(snap) -> bool:
    return PRIVATE_CANARY.lower() in blob(snap)


USAGE_FIELDS = ("app_usage", "hour_histogram", "hours_unknown", "modes",
                "requested_transforms", "dictionary_hit_examples")


def usage_empty(m) -> bool:
    """No usage-derived value survives: every field is redacted/absent
    or an empty/zero reduction."""
    for k in USAGE_FIELDS:
        v = m.get(k)
        if v in (None, {}, [], 0):
            continue
        if k == "hour_histogram" and isinstance(v, list) and not any(v):
            continue
        if k == "requested_transforms" and isinstance(v, dict) and \
                not any(v.values()):
            continue
        return False
    return True


# =============================================================================
# profile_cards
# =============================================================================

def _cards_world():
    w = MWorld()
    c = cohort(w, labels={5: "recognition_error", 6: "recognition_error",
                          7: "recognition_error", 8: "style_preference"},
               counts={9: {"applied": 2}, 10: {"applied": 0}})
    return w, c


@drives("LF-M14-C184")
def c184_cards_follow_live_support(entry):
    w, c = _cards_world()
    with w:
        snap = w.profile.compute()
        probs = card_problems(snap, c)
        sc = snap["measured"].get("self_corrections") or {}
        ids_ = sorted(card["card_id"] for card in snap["cards"])
        cited = {e for card in snap["cards"]
                 for e in card["evidence_example_ids"]}
        rows = evidence_ids(w, snap["snapshot_id"], "card_example")
        return check({
            "oracle_holds": not probs,
            "three_cards": ids_ == ["correction-focus", "style-length",
                                    "technical-vocabulary"],
            "self_corrections_known_only": (sc.get("dictations_with"),
                                            sc.get("applied"),
                                            sc.get("denominator"))
            == (1, 2, 2),
            "evidence_rows_match_cards": rows == cited,
        }, {"problems": probs, "cards": ids_, "words": c.words()},
            witness="ProfileService.compute over an 11-dictation above-floor"
                    " cohort; oracle recounts from the driver's texts,"
                    " labels, applied rules and cleanup counts")


@drives("LF-M14-C185")
def c185_arbitrary_citation_fails_oracle(entry):
    w, c = _cards_world()
    with w:
        snap = w.profile.compute()
        clean = card_problems(snap, c)
        # An unrelated eligible example: no term, no label, no phrase,
        # and far from the median length.
        unrelated = c.ex(10)
        sid = snap["snapshot_id"]
        cards = json.loads(w.one("SELECT cards_json FROM profile_snapshots"
                                 " WHERE snapshot_id=?", (sid,))[0])
        tech = next(k for k in cards
                    if k["card_id"] == "technical-vocabulary")
        tech["evidence_example_ids"] = [unrelated] + \
            tech["evidence_example_ids"][1:]
        w.store.submit(lambda conn: conn.execute(
            "UPDATE profile_snapshots SET cards_json=? WHERE snapshot_id=?",
            (json.dumps(cards), sid)))
        served = w.profile.current()
        tampered = card_problems(served, c)
        return check({
            "untampered_passes": not clean,
            "tampered_card_served": served is not None and any(
                unrelated in k["evidence_example_ids"]
                for k in served["cards"]),
            "oracle_rejects_arbitrary_citation":
                "technical-vocabulary:support" in tampered,
        }, {"clean": clean, "tampered": tampered},
            witness="stored technical-vocabulary citation replaced with an"
                    " unrelated eligible example; current() read back;"
                    " independent oracle graded both")


@drives("LF-M14-C186")
def c186_unused_term_is_not_a_speech_claim(entry):
    with MWorld() as w:
        c = cohort(w)  # Terraform applied in 2,3,4 (positive companion)
        ghost = w.vocab.add_entry("Kafkaesque", [("kafka esk", True)],
                                  approved=True)
        w.vocab.record_hits([ghost])
        w.vocab.record_hits([ghost])
        # Applied only in an INELIGIBLE (excluded) dictation.
        x = c.add(99, 30, rules=[ghost], prefix="g")
        w.training.exclude(x)
        c.gone.add(x)
        snap = w.profile.compute()
        m = snap["measured"]
        terms = list(tech_terms(m))
        tech_card = [k for k in snap["cards"]
                     if k["card_id"] == "technical-vocabulary"]
        ghost_cited = x in blob(snap["cards"]) or x in blob(
            m.get("technical_terms"))
        probs = card_problems(snap, c)
        return check({
            "ghost_not_technical": "Kafkaesque" not in terms,
            "ghost_not_in_any_card": "Kafkaesque" not in blob(snap["cards"]),
            "no_ineligible_citation": not ghost_cited,
            "ghost_only_in_labeled_counter_list":
                "Kafkaesque" in (m.get("dictionary_terms_with_recorded_use")
                                 or [])
                and "not evidence" in (m.get("dictionary_terms_source")
                                       or ""),
            "companion_term_cited": terms == ["Terraform"]
                and len(tech_card) == 1,
            "oracle_holds": not probs,
        }, {"terms": terms, "problems": probs},
            witness="approved term with recorded dictionary use applied only"
                    " in an excluded dictation vs. a term applied in"
                    " eligible speech (D04)")


@drives("LF-M14-C187")
def c187_delete_one_support(entry):
    with MWorld() as w:
        c = cohort(w, labels={5: "recognition_error"})
        s1 = w.profile.compute()
        x = c.ex(2)  # cited by the technical card; unlabeled, no phrase
        cited_before = x in s1["cards"][0]["evidence_example_ids"] or any(
            x in k["evidence_example_ids"] for k in s1["cards"])
        w.training.delete_everywhere(x)
        c.gone.add(x)
        cur = w.profile.current()
        s2 = w.profile.compute()
        probs = card_problems(s2, c)
        m1, m2 = s1["measured"], s2["measured"]
        tech2 = tech_terms(m2)
        return check({
            "fixture_cited": cited_before,
            "s1_invalidated": cur["snapshot_id"] == s1["snapshot_id"]
                and cur["state"] == "invalidated"
                and cur["invalidated_reason"] == "source_deleted"
                and cur["cards"] == [],
            "s2_oracle_holds": not probs,
            "s2_never_cites_deleted": x not in blob(s2),
            "technical_decremented":
                tech2.get("Terraform", {}).get("dictations") == 2,
            "unaffected_stay": m2["corrections_by_kind"]
                == m1["corrections_by_kind"]
                and [p["phrase"] for p in m2["frequent_phrases"]]
                == [p["phrase"] for p in m1["frequent_phrases"]],
        }, {"problems": probs, "s2_words": m2.get("eligible_words"),
            "expected_words": c.words()},
            witness="delete_everywhere of one technical-card support; S1"
                    " current() scrubbed; recompute graded by recount")


@drives("LF-M14-C188")
def c188_exclude_support(entry):
    with MWorld() as w:
        c = cohort(w)
        s1 = w.profile.compute()
        x = c.ex(3)
        was_cited = any(x in k["evidence_example_ids"] for k in s1["cards"])
        w.profile.exclude_evidence(s1["snapshot_id"], x)
        state_after = w.one("SELECT state FROM training_examples WHERE"
                            " example_id=?", (x,))[0]
        c.gone.add(x)
        cur = w.profile.current()
        s2 = w.profile.compute()
        probs = card_problems(s2, c)
        return check({
            "fixture_cited": was_cited,
            "training_example_kept": state_after in TRAINABLE_STATES,
            "s1_not_current": cur["snapshot_id"] != s1["snapshot_id"]
                or cur["state"] != "current",
            "s2_no_excluded_evidence": x not in evidence_ids(
                w, s2["snapshot_id"]) and x not in blob(s2["cards"]),
            "s2_counts_exclusion":
                (s2["measured"].get("excluded") or {}).get("user_excluded")
                == 1,
            "s2_oracle_holds": not probs,
        }, {"problems": probs, "example_state": state_after},
            witness="ProfileService.exclude_evidence then recompute; the"
                    " training example stays trainable")


@drives("LF-M14-C189")
def c189_small_cohort_no_cards(entry):
    with MWorld() as w:
        c = cohort(w, n=4, base=30, phrase_at=(0, 1), terms_at=(0, 1, 2),
                   labels={0: "recognition_error", 1: "recognition_error",
                           2: "recognition_error", 3: "recognition_error"},
                   counts={0: {"applied": 1}})
        a = usage(w)
        for i, ex in enumerate(c.order):
            a.record_dictation_fact(
                job_id=c.info[ex]["job"]["job_id"],
                activity_at_utc=f"2026-09-2{i}T1{i}:00:00.000Z",
                utc_offset_minutes=0, app_name="Synthetic Editor",
                app_bundle=APP, mode="default", dictionary_hits=1)
        low = w.profile.compute()
        low_probs = card_problems(low, c)
        low_rows = evidence_ids(w, low["snapshot_id"], "card_example")
        # Positive companion: the same world crosses the floor.
        for i in range(4, 12):
            c.add(i, 250, prefix="u")
        high = w.profile.compute()
        high_probs = card_problems(high, c)
        return check({
            "no_cards_below_floor": low["cards"] == [] and not low_rows,
            "honest_note": bool(low.get("interpretive_note")
                                or low["measured"].get("interpretive_note")),
            "measured_totals_kept": not low_probs,
            "companion_cards_appear": bool(high["cards"])
                and not high_probs,
        }, {"low_words": low["measured"]["eligible_words"],
            "high_cards": [k["card_id"] for k in high["cards"]],
            "problems": low_probs + high_probs},
            witness="4 dictations/129 words with labels, rules, counts and"
                    " usage facts; then 12 dictations above the floor")


# =============================================================================
# profile_invalidation
# =============================================================================

@drives("LF-M14-C190")
def c190_new_speech_one_snapshot(entry):
    with MWorld() as w:
        c = cohort(w, terms_at=())
        w.profile.compute()
        n0 = snapshots(w)
        new = c.add(50, 180, phrases=(PHRASE2,), prefix="n")
        c.add(51, 181, phrases=(PHRASE2,), prefix="n")
        out = w.profile.compute(only_if_changed=True)
        n1 = snapshots(w)
        again = w.profile.compute(only_if_changed=True)
        sid = latest_id(w)
        cur = w.profile.current()
        probs = card_problems(cur, c)
        return check({
            "one_new_snapshot": not out.get("skipped") and n1 == n0 + 1
                and again.get("skipped") and snapshots(w) == n1,
            "current_is_new": cur["state"] == "current"
                and cur["snapshot_id"] == sid,
            "evidence_is_exact_live_set":
                evidence_ids(w, sid, "measured") == set(c.eligible),
            "new_support_cited": new in evidence_ids(w, sid),
            "oracle_holds": not probs,
        }, {"snapshots": [n0, n1], "problems": probs},
            witness="two new eligible dictations, idle compute twice")


def _mid_compute(action_kind, *, interleave=True, before=False):
    """Shared S023/S024 scenario: PHRASE in examples 0 and 1; the action
    removes example 0 (delete_everywhere or raw-artifact purge) after
    its text chunk was read and before the publishing op."""
    w = MWorld()
    c = cohort(w, terms_at=())
    target = c.info[c.ex(0)]

    def act():
        if action_kind == "delete":
            w.training.delete_everywhere(c.ex(0))
        else:
            w.purge(target["job"]["raw_aid"])
    if before:
        act()
        snap = w.profile.compute()
        state = {"reads": None, "fired": 1}
    elif interleave:
        with after_read(w, act) as state:
            snap = w.profile.compute()
    else:
        with after_read(w, lambda: None) as state:
            snap = w.profile.compute()
    return w, c, snap, state


def _probe_s023_s024(kind, eid):
    w, c, snap, st = _mid_compute(kind)
    with w:
        c.gone.add(c.ex(0))
        cur = w.profile.current()
        ex_state = w.one("SELECT state FROM training_examples WHERE"
                         " example_id=?", (c.ex(0),))[0]
        cur_probs = card_problems(cur, c)
        leaked = [sid for sid, m, _s in all_snap_rows(w)
                  if PRIVATE_CANARY.lower() in blob(m)]
        interleaved = {"published_without_target": c.ex(0) not in
                       evidence_ids(w, cur["snapshot_id"]),
                       "no_canary_anywhere": not leaked and not phrase_in(cur),
                       "oracle_holds": not cur_probs,
                       "restarted": st["reads"] >= 2}
    wc, cc, csnap, cst = _mid_compute(kind, interleave=False)
    with wc:
        control = {"control_seam_reached": cst["reads"] >= 1,
                   "control_includes_target": phrase_in(csnap)
                   and not card_problems(csnap, cc)}
    wa, ca, asnap, _ = _mid_compute(kind, before=True)
    with wa:
        ca.gone.add(ca.ex(0))
        alt = {"alternate_order_same": not phrase_in(asnap)
               and not card_problems(asnap, ca)}
    if not st["fired"]:
        return invalid("mid-compute seam never reached",
                       {"reads": st["reads"]})
    obs = {"reads": st["reads"], "example_state": ex_state,
           "problems": cur_probs}
    conds = {**interleaved, **control, **alt}
    if kind == "purge":
        conds["example_row_still_live"] = ex_state in TRAINABLE_STATES
    return check(conds, obs, witness=f"{eid}: {kind} queued between the"
                 " text-chunk read op and the publishing op (after_each_op);"
                 " control without the action; alternate order (action"
                 " first)", reached=True)


@drives("LF-M14-C191", "LF-M14-S023")
def c191_delete_mid_compute(entry):
    return _probe_s023_s024("delete", entry["id"])


@drives("LF-M14-C192", "LF-M14-S024")
def c192_purge_mid_compute(entry):
    return _probe_s023_s024("purge", entry["id"])


@drives("LF-M14-C193")
def c193_label_mid_compute(entry):
    out = {}
    # Variant 1: latest label moves to background speech at the barrier.
    with MWorld() as w:
        c = cohort(w, terms_at=())
        with after_read(w, lambda: w.review.record_label(
                c.ex(0), edit_kind="ambiguous",
                domains=("background_speech",))) as st:
            snap = w.profile.compute()
        c.gone.add(c.ex(0))
        c.info[c.ex(0)]["label"] = "ambiguous"
        out["bg_fired"] = bool(st["fired"])
        out["bg_excluded"] = (snap["measured"].get("excluded") or {}).get(
            "background_speech") == 1
        out["bg_no_phrase"] = not phrase_in(snap)
        out["bg_oracle"] = not card_problems(snap, c)
        out["bg_restarted"] = st["reads"] >= 2
    # Variant 2: a reviewed label is withdrawn (abstained = ambiguous
    # effective state) at the barrier.
    with MWorld() as w:
        c = cohort(w, terms_at=(), labels={5: "recognition_error",
                              6: "recognition_error"})
        with after_read(w, lambda: c.label(5, "ambiguous",
                                           abstained=True)) as st:
            snap = w.profile.compute()
        out["ab_fired"] = bool(st["fired"])
        out["ab_kinds"] = snap["measured"].get("corrections_by_kind") == {
            "recognition_error": 1}
        out["ab_oracle"] = not card_problems(snap, c)
    # Positive companion: no label change keeps the example's speech.
    with MWorld() as w:
        c = cohort(w, terms_at=())
        with after_read(w, lambda: None) as st:
            snap = w.profile.compute()
        out["control_phrase_kept"] = phrase_in(snap) and \
            not card_problems(snap, c)
    if not (out["bg_fired"] and out["ab_fired"]):
        return invalid("label seam never reached", out)
    return check({k: v for k, v in out.items() if k not in (
        "bg_fired", "ab_fired")}, out, witness="record_label between the"
        " chunk read and the publishing op: background_speech domain and"
        " an abstained latest revision", reached=True)


@drives("LF-M14-C194")
def c194_exclude_mid_compute(entry):
    out = {}
    # Variant A: training exclusion (state -> excluded) at the barrier.
    with MWorld() as w:
        c = cohort(w, terms_at=())
        with after_read(w, lambda: w.training.exclude(c.ex(0))) as st:
            snap = w.profile.compute()
        c.gone.add(c.ex(0))
        out["a_fired"] = bool(st["fired"])
        out["a_not_published"] = c.ex(0) not in evidence_ids(
            w, snap["snapshot_id"]) and not phrase_in(snap)
        out["a_oracle"] = not card_problems(snap, c)
    # Variant B: durable Your Voice exclusion through the current
    # snapshot at the barrier.
    with MWorld() as w:
        c = cohort(w, terms_at=())
        s1 = w.profile.compute()
        with after_read(w, lambda: w.profile.exclude_evidence(
                s1["snapshot_id"], c.ex(0))) as st:
            snap = w.profile.compute()
        c.gone.add(c.ex(0))
        out["b_fired"] = bool(st["fired"])
        out["b_not_published"] = c.ex(0) not in evidence_ids(
            w, snap["snapshot_id"]) and not phrase_in(snap)
        out["b_oracle"] = not card_problems(snap, c)
        out["b_restarted"] = st["reads"] >= 2
    # Positive companion.
    with MWorld() as w:
        c = cohort(w, terms_at=())
        with after_read(w, lambda: None):
            snap = w.profile.compute()
        out["control_included"] = c.ex(0) in evidence_ids(
            w, snap["snapshot_id"]) and phrase_in(snap)
    if not (out["a_fired"] and out["b_fired"]):
        return invalid("exclusion seam never reached", out)
    return check({k: v for k, v in out.items() if not k.endswith(
        "_fired")}, out, witness="training exclusion and profile evidence"
        " exclusion between chunk read and publication", reached=True)


@drives("LF-M14-C195", "LF-M14-S034")
def c195_old_snapshot_exclusion(entry):
    with MWorld() as w:
        c = cohort(w, terms_at=())
        s1 = w.profile.compute()          # rendered S1
        c.add(60, 150, prefix="z")        # a change so S2 is a new record
        s2 = w.profile.compute()          # S2 from the same support
        x = c.ex(0)
        same_support = x in evidence_ids(w, s1["snapshot_id"]) and \
            x in evidence_ids(w, s2["snapshot_id"])
        refused = None
        try:
            w.profile.exclude_evidence(s1["snapshot_id"], x)
        except ValueError as e:
            refused = str(e)
        s2_row = snap_row(w, s2["snapshot_id"])
        cur = w.profile.current()
        c.gone.add(x)
        s3 = w.profile.compute()
        durable = (s2_row["state"] == "invalidated"
                   and (cur["state"] != "current"
                        or x not in evidence_ids(w, cur["snapshot_id"])))
        conds = {
            "fixture_same_support": same_support,
            "s2_retired_or_refused": durable or refused is not None,
            "s3_excludes": x not in evidence_ids(w, s3["snapshot_id"])
                and not phrase_in(s3) if refused is None else True,
            "s3_oracle": not card_problems(s3, c) if refused is None
            else True,
        }
    # Positive companion: exclusion through the CURRENT snapshot.
    with MWorld() as w:
        c = cohort(w, terms_at=())
        s = w.profile.compute()
        w.profile.exclude_evidence(s["snapshot_id"], c.ex(0))
        c.gone.add(c.ex(0))
        again = w.profile.compute()
        conds["companion_current_exclusion"] = snap_row(
            w, s["snapshot_id"])["state"] == "invalidated" and \
            not card_problems(again, c)
    return check(conds, {"s2_state": s2_row["state"], "refused": refused},
                 witness="exclude_evidence(S1, x) after S2 published from"
                         " the same support", reached=True)


@drives("LF-M14-C196")
def c196_secondary_signature_cannot_absorb(entry):
    with MWorld() as w:
        c = cohort(w)
        spare = w.job("unrelated metadata only job words", audio=False,
                      example=False)
        w.profile.compute()
        n0 = snapshots(w)
        with ContentReads(w) as reads:
            # Metadata-only move (an unrelated purge): the evidence is
            # unchanged, so the pass may skip and remember the metadata.
            w.purge(spare["raw_aid"])
            meta = w.profile.compute(only_if_changed=True)
            reads.take()
            quiet = w.profile.compute(only_if_changed=True)
            quiet_reads = reads.take()
            before = w.one("SELECT COUNT(*), TOTAL(usage_count) FROM"
                           " vocabulary_entries WHERE approved=1 AND"
                           " enabled=1")
            w.vocab.update_entry(c.term_id, canonical="Terraform Cloud")
            after = w.one("SELECT COUNT(*), TOTAL(usage_count) FROM"
                          " vocabulary_entries WHERE approved=1 AND"
                          " enabled=1")
            changed = w.profile.compute(only_if_changed=True)
            n1 = snapshots(w)
        cur = w.profile.current()
        probs = card_problems(cur, c, active_terms={
            c.term_id: "Terraform Cloud"})
        return check({
            "metadata_move_skipped": bool(meta.get("skipped"))
                and bool(quiet.get("skipped")),
            "remembered_metadata_no_reads": quiet_reads == 0,
            "counters_constant": tuple(before) == tuple(after),
            "canonical_edit_recomputed": not changed.get("skipped")
                and n1 == n0 + 1,
            "output_follows_edit": not probs,
        }, {"snapshots": [n0, n1], "problems": probs,
            "quiet_reads": quiet_reads},
            witness="unrelated purge (fast signature moves, evidence"
                    " signature equal) vs. canonical edit with constant"
                    " entry count and usage totals")


# =============================================================================
# m13_usage_redaction
# =============================================================================

def _usage_world(n=3):
    w = MWorld(min_words=10)
    c = cohort(w, n=n, base=20, phrase_at=(0, 1), terms_at=(0, 1))
    a = usage(w)
    jobs = [c.info[e]["job"]["job_id"] for e in c.order]
    return w, c, a, jobs


def _write_facts(a, jobs):
    """Fixed facts; the expected reductions are authored literally."""
    a.record_dictation_fact(job_id=jobs[0],
                            activity_at_utc="2026-09-26T15:30:00.000Z",
                            utc_offset_minutes=-240, app_name="Alpha App",
                            app_bundle="com.synthetic.alpha", mode="email",
                            dictionary_hits=2)
    a.record_dictation_fact(job_id=jobs[1],
                            activity_at_utc="2026-09-26T16:05:00.000Z",
                            utc_offset_minutes=0, app_name="Alpha App",
                            app_bundle="com.synthetic.alpha", mode="code")
    a.record_dictation_fact(job_id=jobs[2],
                            activity_at_utc="2026-09-27T01:00:00.000Z",
                            utc_offset_minutes=120, app_name="Beta App",
                            app_bundle="com.synthetic.beta", mode="email",
                            transform_id="builtin:polish")
    for tid in ("builtin:polish", "builtin:polish", "builtin:shorten"):
        a.record_transform_fact(transform_id=tid, task_key="synthetic-task",
                                path="applied", source_kind="selection",
                                source_words=5, output_words=4,
                                activity_at_utc="2026-09-27T09:00:00.000Z")


EXPECTED_USAGE = {
    "app_usage": {"Alpha App": 2, "Beta App": 1},
    "modes": {"email": 2, "code": 1},
    "hours": {11: 1, 16: 1, 3: 1},
    "hours_unknown": 0,
    "requested_transforms": {"explicit": {"builtin:polish": 2,
                                          "builtin:shorten": 1},
                             "auto_applied": {"builtin:polish": 1}},
    "dictionary_hit_examples": 1,
}


def _hist(hours):
    h = [0] * 24
    for k, v in hours.items():
        h[k] = v
    return h


def usage_matches(m, exp=EXPECTED_USAGE):
    return {
        "app_usage": m.get("app_usage") == exp["app_usage"],
        "modes": m.get("modes") == exp["modes"],
        "hours": m.get("hour_histogram") == _hist(exp["hours"]),
        "hours_unknown": m.get("hours_unknown") == exp["hours_unknown"],
        "requested": m.get("requested_transforms")
        == exp["requested_transforms"],
        "dictionary_hits": m.get("dictionary_hit_examples")
        == exp["dictionary_hit_examples"],
    }


@drives("LF-M14-C197")
def c197_usage_fields_match_reducer(entry):
    w, c, a, jobs = _usage_world()
    with w:
        _write_facts(a, jobs)
        snap = w.profile.compute()
        m = snap["measured"]
        res = usage_matches(m)
        return check(res, {k: m.get(k) for k in ("app_usage", "modes",
                                                 "hours_unknown")},
                     witness="3 dictation facts (offsets -240/0/+120), 3"
                             " explicit transform facts; literal expected"
                             " reductions")


def _speech(m):
    return {k: m.get(k) for k in (
        "eligible_examples", "eligible_words", "frequent_phrases",
        "technical_terms", "corrections_by_kind", "self_corrections",
        "dictionary_terms_with_recorded_use")}


@drives("LF-M14-C198")
def c198_delete_all_redacts_in_one_op(entry):
    w, c, a, jobs = _usage_world()
    with w:
        _write_facts(a, jobs)
        s1 = w.profile.compute()
        c.add(9, 25, prefix="s")  # a change so S2 is a new record
        s2 = w.profile.compute()
        pre = {sid: _speech(m) for sid, m, _s in all_snap_rows(w)}
        cards_pre = {r[0]: r[1] for r in w.rows(
            "SELECT snapshot_id, cards_json FROM profile_snapshots")}
        seen = []

        def hook():
            facts = w.one("SELECT COUNT(*) FROM usage_facts")[0]
            carrying = sum(1 for _sid, m, _s in all_snap_rows(w)
                           if not usage_empty(m))
            seen.append((facts, carrying))
        with after_each_op(w.store, hook):
            out = a.delete_all_usage()
        rows = all_snap_rows(w)
        post = {sid: _speech(m) for sid, m, _s in rows}
        cards_post = {r[0]: r[1] for r in w.rows(
            "SELECT snapshot_id, cards_json FROM profile_snapshots")}
        return check({
            "fixture_copies_present": not usage_empty(s1["measured"])
                and not usage_empty(s2["measured"]),
            "one_op": len(seen) == 1,
            "same_op_redaction": seen == [(0, 0)],
            "every_snapshot_redacted": all(
                usage_empty(m) and (m.get("usage_redacted") or {}).get(
                    "reason") == "usage_deleted" for _sid, m, _s in rows),
            "speech_fields_retained": pre == post
                and cards_pre == cards_post,
            "facts_deleted": out.get("facts_deleted") == 6,
        }, {"ops": seen, "snapshots": len(rows)},
            witness="delete_all_usage with a historical and a current"
                    " snapshot; after_each_op observed the committed state")


@drives("LF-M14-C199")
def c199_expiry(entry):
    w, c, a, jobs = _usage_world(n=5)
    with w:
        w.store.retention_days["usage"] = 3
        old = [("2026-09-20T08:00:00.000Z", "Old App")] * 2
        new = [("2026-09-28T10:00:00.000Z", "New App")] * 3
        for job, (at, app) in zip(jobs, old + new):
            a.record_dictation_fact(job_id=job, activity_at_utc=at,
                                    utc_offset_minutes=0, app_name=app,
                                    mode="default" if app == "New App"
                                    else "legacy")
        s1 = w.profile.compute()
        out = a.expire_usage()
        rows = all_snap_rows(w)
        stale = [sid for sid, m, _s in rows
                 if "Old App" in blob({k: m.get(k) for k in USAGE_FIELDS})
                 or "legacy" in blob(m.get("modes"))]
        again = w.profile.compute(only_if_changed=True)
        m = w.profile.current()["measured"]
        return check({
            "fixture_old_present": s1["measured"].get("app_usage")
                == {"Old App": 2, "New App": 3},
            "expired_subset": out.get("facts_removed") == 2,
            "no_removed_value_current": not stale,
            "recompute_not_skipped": not again.get("skipped"),
            "remaining_support_only": m.get("app_usage") == {"New App": 3}
                and m.get("modes") == {"default": 3}
                and m.get("hour_histogram") == _hist({10: 3}),
        }, {"stale": len(stale), "app_usage": m.get("app_usage")},
            witness="usage retention 3 days at the fixed clock; 2 of 5"
                    " facts older than the cutoff")


def _legacy_launch(with_facts):
    w, c, a, jobs = _usage_world()
    _write_facts(a, jobs)
    s1 = w.profile.compute()
    if not with_facts:
        # A deletion from before copies were redacted: facts gone, the
        # snapshot still carries copies.
        w.store.submit(lambda conn: conn.execute("DELETE FROM usage_facts"))
    fresh = usage(w)
    fresh.ensure_current()
    m = snap_row(w, s1["snapshot_id"])["measured"]
    return w, m


@drives("LF-M14-C200")
def c200_launch_redaction(entry):
    w, m = _legacy_launch(False)
    with w:
        legacy = {"redacted_at_launch": usage_empty(m),
                  "speech_kept": m.get("eligible_words") == 60 + 3}
    wc, mc = _legacy_launch(True)
    with wc:
        control = {"companion_kept_with_facts":
                   all(usage_matches(mc).values())}
    return check({**legacy, **control}, {"legacy_app_usage":
                                         m.get("app_usage")},
                 witness="AnalyticsStore.ensure_current (launch check) with"
                         " a snapshot and no usage facts vs. facts present")


def _hours_world(facts):
    w, c, a, jobs = _usage_world(n=len(facts))
    for job, (at, off) in zip(jobs, facts):
        a.record_dictation_fact(job_id=job, activity_at_utc=at,
                                utc_offset_minutes=off,
                                app_name="Synthetic Editor")
    err = None
    try:
        m = w.profile.compute()["measured"]
    except Exception as e:  # noqa: BLE001
        m, err = {}, type(e).__name__
    w.close()
    return m.get("hour_histogram") or [0] * 24, m.get("hours_unknown"), err


@drives("LF-M14-C201")
def c201_local_hours(entry):
    # Recorded offsets (positive, negative, a US DST transition pair),
    # a missing offset and out-of-range offsets (beyond +/-14:00).
    hist, unknown, err = _hours_world([
        ("2026-09-26T15:30:00.000Z", 330),    # +05:30 -> 21
        ("2026-09-26T03:10:00.000Z", -300),   # -05:00 -> 22 (prev day)
        ("2026-09-26T09:00:00.000Z", None),   # missing -> unknown
        ("2026-03-08T06:30:00.000Z", -300),   # before US DST -> 01
        ("2026-03-08T07:30:00.000Z", -240),   # after US DST -> 03
        ("2026-09-26T10:00:00.000Z", 1500),   # out of range
        ("2026-09-26T13:00:00.000Z", -1500),  # out of range
    ])
    # A non-numeric recorded offset beside one valid fact: no local hour
    # can be derived from it, so it can only be unknown.
    hist2, unknown2, err2 = _hours_world([
        ("2026-09-26T15:30:00.000Z", 330),
        ("2026-09-26T16:00:00.000Z", "bogus"),
    ])
    conds = {
        "compute_ok": err is None,
        "recorded_offsets_bucketed_local": all(hist[h] == 1
                                               for h in (21, 22, 1, 3)),
        "missing_unknown_not_utc": hist[9] == 0,
        # Out-of-range offsets: never their UTC hour (10, 13).
        "out_of_range_not_utc": hist[10] == 0 and hist[13] == 0,
        "non_numeric_compute_ok": err2 is None,
        "non_numeric_is_unknown": err2 is None and hist2[16] == 0
            and hist2[21] == 1 and unknown2 == 1,
    }
    return check(conds, {
        "hist_nonzero": {i: v for i, v in enumerate(hist) if v},
        "hours_unknown": unknown, "non_numeric_error": err2,
        "non_numeric_unknown": unknown2,
        "out_of_range_observation": "bucketed arithmetically (ungraded:"
        " no adopted decision defines out-of-range offsets)"
        if hist[11] or hist[23] else "not bucketed"},
        witness="+330/-300/missing/DST pair/out-of-range offsets; then a"
                " non-numeric recorded offset; literal local hours")


@drives("LF-M14-C202")
def c202_self_corrections(entry):
    with MWorld(min_words=10) as w:
        c = cohort(w, n=5, base=15, phrase_at=(), terms_at=(),
                   counts={0: {"applied": 0}, 1: {"applied": 2},
                           2: {"applied": 1}})
        snap = w.profile.compute()
        sc = snap["measured"].get("self_corrections") or {}
        return check({
            "denominator_known_only": sc.get("denominator") == 3,
            "with_count": sc.get("dictations_with") == 2,
            "applied_total": sc.get("applied") == 3,
            "oracle": not card_problems(snap, c, min_words=10),
        }, {k: sc.get(k) for k in ("denominator", "dictations_with",
                                   "applied")},
            witness="known zero, two known positives, two unrecorded")


@drives("LF-M14-C203")
def c203_transform_counts(entry):
    w, c, a, jobs = _usage_world()
    with w:
        for job in jobs[:2]:
            a.record_dictation_fact(
                job_id=job, activity_at_utc="2026-09-26T12:00:00.000Z",
                utc_offset_minutes=0, transform_id="builtin:polish")
        a.record_transform_fact(transform_id="builtin:polish",
                                task_key="t1", path="applied",
                                source_kind="selection",
                                activity_at_utc="2026-09-26T13:00:00.000Z")
        a.record_transform_fact(transform_id="builtin:list",
                                task_key="t2", path="applied",
                                source_kind="note",
                                activity_at_utc="2026-09-26T14:00:00.000Z")
        m = w.profile.compute()["measured"]
        rt = m.get("requested_transforms") or {}
        return check({
            "explicit": rt.get("explicit") == {"builtin:polish": 1,
                                               "builtin:list": 1},
            "auto_applied": rt.get("auto_applied") == {"builtin:polish": 2},
            "no_double_count": sum((rt.get("explicit") or {}).values())
                + sum((rt.get("auto_applied") or {}).values()) == 4,
        }, rt, witness="2 auto-applied dictation transforms + 2 explicit"
                       " transform facts")


@drives("LF-M14-C204")
def c204_independent_vocab_counter(entry):
    w, c, a, jobs = _usage_world()
    with w:
        _write_facts(a, jobs)
        counters0 = w.rows("SELECT entry_id, usage_count FROM"
                           " vocabulary_entries ORDER BY entry_id")
        s1 = w.profile.compute()
        a.delete_all_usage()
        r1 = snap_row(w, s1["snapshot_id"])["measured"]
        counters1 = w.rows("SELECT entry_id, usage_count FROM"
                           " vocabulary_entries ORDER BY entry_id")
        s2 = w.profile.compute()
        m2 = s2["measured"]
        terms2 = {k: t.get("dictations") for k, t in
                  tech_terms(m2).items()}
        return check({
            "fixture_counter": bool(counters0) and counters0[0][1] > 0
                and s1["measured"].get("dictionary_hit_examples") == 1,
            "usage_copy_redacted": r1.get("dictionary_hit_examples") is None,
            "counters_not_reset": counters0 == counters1,
            "counter_list_kept_and_labeled":
                r1.get("dictionary_terms_with_recorded_use") == ["Terraform"]
                and m2.get("dictionary_terms_with_recorded_use")
                == ["Terraform"]
                and "not cleared by Delete Usage" in (
                    m2.get("dictionary_terms_source") or ""),
            "speech_terms_own_lineage": terms2 == {"Terraform": 2}
                and "eligible" in (m2.get("technical_terms_source") or ""),
            "recomputed_hits_zero": m2.get("dictionary_hit_examples") == 0,
        }, {"terms": terms2}, witness="Delete Usage with an approved term"
            " carrying recorded use (D04)")


@drives("LF-M14-S025")
def s025_usage_deletion_with_profile(entry):
    # Interleaved: Delete Usage after the profile's evidence read, before
    # the publishing op that copies usage.
    w, c, a, jobs = _usage_world()
    with w:
        _write_facts(a, jobs)
        with after_read(w, lambda: a.delete_all_usage()) as st:
            snap = w.profile.compute()
        inter = {"interleaved_no_deleted_copy": usage_empty(
            snap_row(w, snap["snapshot_id"])["measured"]),
            "interleaved_counter_list_kept":
                snap["measured"].get("dictionary_terms_with_recorded_use")
                == ["Terraform"]}
        fired = st["fired"]
    # Control: no deletion keeps the literal usage fields.
    w, c, a, jobs = _usage_world()
    with w:
        _write_facts(a, jobs)
        with after_read(w, lambda: None):
            snap = w.profile.compute()
        ctrl = {"control_usage_present": all(usage_matches(
            snap["measured"]).values())}
    # Alternate order: deletion after publication redacts the copies.
    w, c, a, jobs = _usage_world()
    with w:
        _write_facts(a, jobs)
        snap = w.profile.compute()
        before = _speech(snap["measured"])
        a.delete_all_usage()
        m = snap_row(w, snap["snapshot_id"])["measured"]
        alt = {"after_publication_redacted": usage_empty(m)
               and (m.get("usage_redacted") or {}).get("reason")
               == "usage_deleted",
               "speech_follows_own_lineage": _speech(m) == before}
    if not fired:
        return invalid("usage-deletion seam never reached")
    return check({**inter, **ctrl, **alt}, None,
                 witness="delete_all_usage between the chunk read and the"
                         " publishing op; control; post-publication order",
                 reached=True)


@drives("LF-M14-MR009")
def mr009_usage_redaction_monotone(entry):
    w, c, a, jobs = _usage_world(n=4)
    with w:
        _write_facts(a, jobs)
        a.record_dictation_fact(job_id=jobs[3],
                                activity_at_utc="2026-09-20T05:00:00.000Z",
                                utc_offset_minutes=60, app_name="Gamma App",
                                mode="notes")
        s1 = w.profile.compute()["measured"]
        a.delete_usage_for_job(jobs[1])            # Alpha App, code, 16h
        s2 = w.profile.compute(only_if_changed=True)
        s2m = w.profile.current()["measured"]
        w.store.retention_days["usage"] = 5
        a.expire_usage()                           # Gamma App (09-20)
        w.profile.compute(only_if_changed=True)
        s3m = w.profile.current()["measured"]

        def sub(small, big):
            return all(k in big and v <= big[k] for k, v in
                       (small or {}).items())
        return check({
            "delete_recomputed": not s2.get("skipped"),
            "delete_exact_loss": s2m.get("app_usage") == {"Alpha App": 1,
                                                          "Beta App": 1,
                                                          "Gamma App": 1}
                and s2m.get("modes") == {"email": 2, "notes": 1}
                and (s2m.get("hour_histogram") or [0] * 24)[16] == 0,
            "never_invents": sub(s2m.get("app_usage"), s1.get("app_usage"))
                and sub(s3m.get("app_usage"), s2m.get("app_usage"))
                and sub(s2m.get("modes"), s1.get("modes"))
                and sub(s3m.get("modes"), s2m.get("modes"))
                and all(x <= y for x, y in zip(
                    s3m.get("hour_histogram") or [], s2m.get(
                        "hour_histogram") or [])),
            "expiry_exact_loss": s3m.get("app_usage") == {"Alpha App": 1,
                                                          "Beta App": 1},
            "speech_own_lineage": _speech(s1) == _speech(s2m)
                == _speech(s3m),
        }, {"s3_apps": s3m.get("app_usage")},
            witness="per-job usage deletion then 5-day expiry; speech"
                    " untouched")


# =============================================================================
# idle_profile_pass
# =============================================================================

@drives("LF-M14-C205")
def c205_one_change_one_snapshot(entry):
    with MWorld() as w:
        c = cohort(w, terms_at=())
        w.profile.compute()
        n0 = snapshots(w)
        new = c.add(70, 160, prefix="i")
        outs = [w.profile.compute(only_if_changed=True) for _ in range(3)]
        n1 = snapshots(w)
        sid = latest_id(w)
        return check({
            "exactly_one": n1 == n0 + 1
                and [bool(o.get("skipped")) for o in outs]
                == [False, True, True],
            "new_is_current": snap_row(w, sid)["state"] == "current"
                and new in evidence_ids(w, sid),
            "oracle": not card_problems(w.profile.current(), c),
        }, {"snapshots": [n0, n1]}, witness="one new dictation; three idle"
            " ticks")


@drives("LF-M14-C206", "LF-M14-S026")
def c206_unchanged_idle_no_reads(entry):
    with MWorld() as w:
        c = cohort(w)
        with ContentReads(w) as reads:
            w.profile.compute()
            first_reads = reads.take()
            n0 = snapshots(w)
            idle = [w.profile.compute(only_if_changed=True)
                    for _ in range(3)]
            idle_reads = reads.take()
            n1 = snapshots(w)
            # Positive control: the counter sees reads in a changed pass.
            c.add(80, 150, prefix="k")
            changed = w.profile.compute(only_if_changed=True)
            changed_reads = reads.take()
        if not (first_reads and changed_reads):
            return invalid("read counter never observed a content read",
                           {"first": first_reads,
                            "changed": changed_reads})
        return check({
            "zero_reads_unchanged": idle_reads == 0,
            "zero_new_snapshots": n1 == n0
                and all(o.get("skipped") for o in idle),
            "changed_pass_computed": not changed.get("skipped"),
        }, {"first_reads": first_reads, "idle_reads": idle_reads,
            "changed_reads": changed_reads},
            witness="SQLite trace counter on the writer connection;"
                    " proven live on the first and a changed pass",
            reached=True)


def _same_count_label_change(w, ex, kind):
    def op(conn):
        n0 = conn.execute("SELECT COUNT(*) FROM correction_labels"
                          ).fetchone()[0]
        conn.execute(
            "UPDATE correction_labels SET edit_kind=? WHERE example_id=?"
            " AND revision=(SELECT MAX(revision) FROM correction_labels"
            " WHERE example_id=?)", (kind, ex, ex))
        return n0, conn.execute("SELECT COUNT(*) FROM correction_labels"
                                ).fetchone()[0]
    return w.store.submit(op)


@drives("LF-M14-C207")
def c207_same_count_label_revision(entry):
    with MWorld() as w:
        c = cohort(w, terms_at=(), labels={5: "recognition_error",
                                           6: "recognition_error",
                                           7: "style_preference"})
        w.profile.compute()
        skip0 = w.profile.compute(only_if_changed=True)
        n0 = snapshots(w)
        counts = _same_count_label_change(w, c.ex(7), "recognition_error")
        c.info[c.ex(7)]["label"] = "recognition_error"
        out = w.profile.compute(only_if_changed=True)
        cur = w.profile.current()
        return check({
            "control_skip": bool(skip0.get("skipped")),
            "row_count_constant": counts[0] == counts[1],
            "noticed": not out.get("skipped") and snapshots(w) == n0 + 1,
            "output_changed": cur["measured"]["corrections_by_kind"]
                == {"recognition_error": 3},
            "oracle": not card_problems(cur, c),
        }, {"label_rows": counts}, witness="controlled in-place edit of the"
            " latest label row (count held constant)")


@drives("LF-M14-S027")
def s027_label_change_at_signature(entry):
    out = {}
    with MWorld() as w:
        c = cohort(w, terms_at=(), labels={5: "recognition_error",
                                           6: "style_preference"})
        s1 = w.profile.compute()
        sig_captured = bool(s1["measured"].get("input_signature"))
        c.add(90, 170, prefix="m")  # a change so the idle pass reads
        box = {}
        with after_read(w, lambda: box.setdefault(
                "counts", _same_count_label_change(
                    w, c.ex(6), "recognition_error"))) as st:
            got = w.profile.compute(only_if_changed=True)
        c.info[c.ex(6)]["label"] = "recognition_error"
        out["fired"] = bool(st["fired"])
        out["count_constant"] = box.get("counts", (0, 1))[0] == \
            box.get("counts", (0, 1))[1]
        out["no_stale_publication"] = (got.get("measured") or {}).get(
            "corrections_by_kind") == {"recognition_error": 2}
        out["oracle"] = not card_problems(w.profile.current(), c)
        # Between snapshots: after the signature is recorded, a further
        # same-count change must be noticed by the next idle tick.
        _same_count_label_change(w, c.ex(6), "style_preference")
        c.info[c.ex(6)]["label"] = "style_preference"
        nxt = w.profile.compute(only_if_changed=True)
        out["noticed_between"] = not nxt.get("skipped") and \
            w.profile.current()["measured"]["corrections_by_kind"] == {
                "recognition_error": 1, "style_preference": 1}
    with MWorld() as w:
        c = cohort(w, terms_at=(), labels={5: "recognition_error",
                                           6: "style_preference"})
        w.profile.compute()
        ctl = w.profile.compute(only_if_changed=True)
        out["control_skip"] = bool(ctl.get("skipped"))
    if not (out["fired"] and sig_captured):
        return invalid("signature seam never reached", out)
    return check({k: v for k, v in out.items() if k != "fired"}, out,
                 witness="same-count latest-label edit between the chunk"
                         " read and publication, then between snapshots",
                 reached=True)


@drives("LF-M14-C208")
def c208_canonical_once(entry):
    with MWorld() as w:
        c = cohort(w)
        w.profile.compute()
        n0 = snapshots(w)
        before = w.one("SELECT COUNT(*), TOTAL(usage_count) FROM"
                       " vocabulary_entries")
        w.vocab.update_entry(c.term_id, canonical="Terraform Enterprise")
        after = w.one("SELECT COUNT(*), TOTAL(usage_count) FROM"
                      " vocabulary_entries")
        outs = [w.profile.compute(only_if_changed=True) for _ in range(3)]
        cur = w.profile.current()
        terms = list(tech_terms(cur["measured"]))
        return check({
            "counters_constant": tuple(before) == tuple(after),
            "exactly_once": [bool(o.get("skipped")) for o in outs]
                == [False, True, True] and snapshots(w) == n0 + 1,
            "term_output_updated": terms == ["Terraform Enterprise"],
            "oracle": not card_problems(cur, c, active_terms={
                c.term_id: "Terraform Enterprise"}),
        }, {"terms": terms}, witness="update_entry canonical; three idle"
            " ticks")


@drives("LF-M14-C209")
def c209_busy_yield(entry):
    import threading as _threading

    from test_m14_remediation import _hub_env
    Harness, _mq = _hub_env()
    import localflow.app as app_mod

    class SyncThreading:
        """``threading`` for app.py during one tick: Thread.start runs
        the target inline, so the tick is deterministic."""

        def __getattr__(self, name):
            return getattr(_threading, name)

        class Thread:
            def __init__(self, target=None, daemon=None, name=None,
                         args=(), kwargs=None):
                self._t, self._a, self._k = target, args, kwargs or {}

            def start(self):
                self._t(*self._a, **self._k)

    h = Harness(durations=[1.0])
    try:
        d = h.d
        if d._profile is None:
            return invalid("no profile service wired in the harness")
        calls = []
        real = d._profile.compute

        def counting(**kw):
            calls.append(dict(kw))
            return real(**kw)
        d._profile.compute = counting

        def tick():
            with patched(app_mod, "threading", lambda o: SyncThreading()):
                d.profileIdlePass_(None)
            return len(calls)
        n_snap = lambda: d.store.submit(lambda c: c.execute(  # noqa: E731
            "SELECT COUNT(*) FROM profile_snapshots").fetchone()[0])
        seen = {}
        h.press()
        seen["recording"] = (d.state, tick())
        h.release()
        seen["processing"] = (d._pending, tick())
        fn, args = h.run_coordinator()
        seen["finishing"] = (d._pending, tick())
        fn(*args)
        d.store.sync()
        snaps_busy = n_snap()
        seen["idle"] = (d._pending, d.state, tick())
        d._injecting = True
        seen["injecting"] = tick()
        d._injecting = False
        d._insertion.busy = True
        seen["insertion_busy"] = tick()
        d._insertion.busy = False
        seen["idle_again"] = tick()
        return check({
            "reached_recording": seen["recording"][0] == "recording",
            "reached_processing": seen["processing"][0] > 0,
            "yield_recording": seen["recording"][1] == 0,
            "yield_processing": seen["processing"][1] == 0
                and seen["finishing"][1] == 0,
            "no_snapshot_while_busy": snaps_busy == 0,
            "idle_runs_once_only_if_changed": seen["idle"][2] == 1
                and calls[0] == {"only_if_changed": True},
            "yield_injecting_and_insertion": seen["injecting"] == 1
                and seen["insertion_busy"] == 1,
            "idle_again_runs": seen["idle_again"] == 2,
        }, {k: list(v) if isinstance(v, tuple) else v
            for k, v in seen.items()},
            witness="real AppDelegate.profileIdlePass_ through the lifecycle"
                    " Harness (press/release/_worker/finish); no idle mining"
                    " path exists (mining is the Hub's explicit action)")
    finally:
        h.close()


@drives("LF-M14-C210")
def c210_threshold_or_algorithm_change(entry):
    with MWorld() as w:
        c = cohort(w, base=150, terms_at=())  # 1705 words
        s1 = w.profile.compute()
        ctl = w.profile.compute(only_if_changed=True)
        n0 = snapshots(w)
        lower = profile_mod.ProfileService(w.store, emit=w._emit,
                                           min_words=1500)
        t = lower.compute(only_if_changed=True)
        t_row = snap_row(w, latest_id(w))
        with patched(profile_mod, "ALGORITHM_VERSION", lambda o: o + 1):
            v = lower.compute(only_if_changed=True)
            v_row = snap_row(w, latest_id(w))
            v2 = lower.compute(only_if_changed=True)
        return check({
            "control_skip": bool(ctl.get("skipped")),
            "fixture_below_floor": s1["cards"] == [],
            "threshold_requalifies": not t.get("skipped")
                and t_row["measured"].get("min_words_threshold") == 1500
                and bool(t_row["cards"])
                and not card_problems(t, c, min_words=1500),
            "algorithm_recomputes": not v.get("skipped")
                and v_row["algorithm_version"]
                == profile_mod.ALGORITHM_VERSION + 1,
            "then_stable": bool(v2.get("skipped")),
            "snapshot_count": snapshots(w) == n0 + 2,
        }, {"cards_after": [k["card_id"] for k in t_row["cards"]]},
            witness="ProfileService(min_words=1500) over the same store;"
                    " ALGORITHM_VERSION bumped by patch")


@drives("LF-M14-MR012")
def mr012_idle_idempotence(entry):
    with MWorld() as w:
        c = cohort(w)
        with ContentReads(w) as reads:
            w.profile.compute()
            proof = reads.take()
            n0 = snapshots(w)
            quiet = [w.profile.compute(only_if_changed=True)
                     for _ in range(3)]
            quiet_reads = reads.take()
            c.add(95, 140, prefix="r")
            first = w.profile.compute(only_if_changed=True)
            first_reads = reads.take()
            rest = [w.profile.compute(only_if_changed=True)
                    for _ in range(3)]
            rest_reads = reads.take()
        if not (proof and first_reads):
            return invalid("read counter never live", {"proof": proof})
        return check({
            "no_reads_unchanged": quiet_reads == 0 and rest_reads == 0,
            "no_churn": all(o.get("skipped") for o in quiet + rest),
            "one_refresh": not first.get("skipped")
                and snapshots(w) == n0 + 1,
        }, {"reads": [proof, quiet_reads, first_reads, rest_reads]},
            witness="3 unchanged ticks, one change, 3 more ticks;"
                    " SQLite trace read counter", reached=True)


# =============================================================================
# relations MR004, MR008
# =============================================================================

@drives("LF-M14-MR004")
def mr004_deletion_monotonicity(entry):
    out = {}
    with MWorld() as w:
        c = cohort(w, n=12, phrase_at=(0, 1, 2), terms_at=(0, 3, 4),
                   labels={0: "recognition_error", 5: "recognition_error",
                           6: "recognition_error"})
        s1 = w.profile.compute()
        x = c.ex(0)
        w.training.delete_everywhere(x)
        c.gone.add(x)
        s2 = w.profile.compute()

        def supports(s):
            m = s["measured"]
            d = {("p", p["phrase"]): set(p["example_ids"])
                 for p in m["frequent_phrases"]}
            d.update({("t", k): set(t.get("example_ids") or [])
                      for k, t in tech_terms(m).items()})
            d.update({("c", k["card_id"]): set(k["evidence_example_ids"])
                      for k in s["cards"]})
            return d
        a, b = supports(s1), supports(s2)
        out["no_new_claim"] = set(b) <= set(a)
        out["support_shrinks"] = all(b[k] <= a[k] | set(c.eligible)
                                     and x not in b[k] for k in b)
        out["exact_decrease"] = (
            [t.get("dictations") for t in
             tech_terms(s2["measured"]).values()] == [2]
            and s2["measured"]["corrections_by_kind"] == {
                "recognition_error": 2}
            and [p["count"] for p in s2["measured"]["frequent_phrases"]]
            == [2])
        out["oracle"] = not card_problems(s2, c)
    with MWorld() as w:
        fams = w.families(10, asr=True)
        w.splits.assign()
        w.export("d1", ("asr_supervised",))
        e1 = {e["example_id"] for e in read_jsonl(w.tmp / "d1"
                                                  / "examples.jsonl")}
        gone = fams[0]["example_id"]
        w.training.delete_everywhere(gone)
        w.export("d2", ("asr_supervised",))
        e2 = {e["example_id"] for e in read_jsonl(w.tmp / "d2"
                                                  / "examples.jsonl")}
        out["task_support_shrinks"] = gone in e1 and e2 == e1 - {gone}
    return check(out, None, witness="delete one example supporting a"
                 " phrase, term, label and card; ASR export before/after"
                 " deleting one family")


@drives("LF-M14-MR008")
def mr008_profile_floor(entry):
    out = {}
    with MWorld() as w:   # words above, dictations below
        c = Cohort(w)
        for i in range(5):
            c.add(i, 450)
        s = w.profile.compute()
        out["words_only_no_cards"] = s["cards"] == [] and \
            not card_problems(s, c)
    with MWorld() as w:   # dictations above, words below
        c = Cohort(w)
        for i in range(12):
            c.add(i, 20)
        s = w.profile.compute()
        out["dictations_only_no_cards"] = s["cards"] == [] and \
            not card_problems(s, c)
        # Cross both.
        for i in range(12, 22):
            c.add(i, 200, prefix="b")
        s = w.profile.compute()
        out["both_cards_supported"] = bool(s["cards"]) and \
            not card_problems(s, c)
        # Remove support below the dictation floor.
        for e in list(c.eligible)[:13]:
            w.training.delete_everywhere(e)
            c.gone.add(e)
        cur = w.profile.current()
        out["removed_support_invalidated"] = cur["state"] == \
            "invalidated" and cur["cards"] == []
        s = w.profile.compute()
        out["below_again_no_cards"] = s["cards"] == [] and \
            not card_problems(s, c)
        out["raw_counts_measured"] = s["measured"]["eligible_words"] == \
            c.words()
    return check(out, None, witness="5x450 words; 12x20 words; +10x200;"
                 " then delete 13 examples")


# =============================================================================
# privacy
# =============================================================================

CTX = "ctxcanaryqv"
CE = "counterexcanaryqv"
NOTE = "notecanaryqv"
LBLNOTE = "labelnotecanaryqv"
APPC = "appcanaryqv"
TR = "transcriptcanaryqv"
PAIRC = "paircanaryqv"
CANARIES = (CTX, CE, NOTE, LBLNOTE, APPC, TR, PAIRC,
            PRIVATE_CANARY.lower())


def _exercise_producers(w):
    """Run every M14 event producer over canary-bearing synthetic data.
    Returns names of the producer calls made."""
    from localflow.v2.notes import NoteStore
    done = []
    j = w.job(f"{CTX} please check the modul today")
    cid = w.learning.teach_correction(
        j["job_id"], f"{CTX} please check the module today")["candidate_id"]
    done.append("teach")
    w.learning.approve(cid, counterexamples=(
        f"keep the modul named {CE} here",))
    w.learning.approve(cid)
    done.append("approve")
    if accepts(w.learning.undo_approval, "operation_id"):
        w.learning.undo_approval(cid, operation_id="op-undo-g")
    else:
        w.learning.undo_approval(cid)
    done.append("undo")
    j2 = w.job(f"{TR} open the dashbord now")
    w.observation(j2["job_id"], f"{TR} open the dashbord now",
                  f"{TR} open the dashboard now")
    w.learning.mine_observation_candidates()
    done.append("mine")
    for cand in w.rows("SELECT candidate_id FROM learning_candidates WHERE"
                       " status='pending'"):
        w.learning.reject(cand[0])
        done.append("reject")
    notes = NoteStore(w.store)
    nid = notes.create_note(f"note body {NOTE} words")["note_id"]
    done.append("note")
    c = cohort(w)
    w.review.record_label(c.ex(5), edit_kind="recognition_error",
                          notes=f"reviewer says {LBLNOTE}")
    done.append("label")
    snap = w.profile.compute()
    w.profile.exclude_evidence(snap["snapshot_id"], c.ex(3))
    w.profile.compute()
    done.append("profile")
    t = w.transform_task(f"source {PAIRC}", [f"A {PAIRC}", f"B {PAIRC}"])
    w.review.record_pair_judgment(
        w.tf_store(), t["task_key"], t["candidates"][0]["candidate_id"],
        t["candidates"][1]["candidate_id"], "prefer_a")
    done.append("pair")
    a = usage(w)
    a.record_dictation_fact(job_id=j["job_id"],
                            activity_at_utc="2026-09-26T10:00:00.000Z",
                            utc_offset_minutes=0, app_name=f"App {APPC}",
                            app_bundle=f"com.synthetic.{APPC}")
    w.families(10, asr=True)
    w.splits.assign()
    w.sampling.refresh()
    w.export("ds", ("asr_supervised",))
    done.append("export")
    a.delete_usage_for_job(j["job_id"])
    w.training.delete_everywhere(c.ex(0))
    done.append("delete")
    return done, nid


@drives("LF-M14-C220")
def c220_content_free_events(entry):
    with MWorld() as w:
        done, _nid = _exercise_producers(w)
        names = sorted({n for n, _kw in w.events})
        leaks = sorted({can for can in CANARIES for n, kw in w.events
                        if can in blob(kw).lower() or can in n.lower()})
        present = sorted({can for can in CANARIES
                          for _t, v in _dump(w) if can in v.lower()})
        prefixes = {n.split(".")[0] for n in names}
        return check({
            "no_canary_in_events": not leaks,
            "producers_emitted": {"learning", "profile", "training"}
                <= prefixes and len(w.events) >= 10,
            "canaries_were_live": {CTX, NOTE, LBLNOTE, TR, PAIRC,
                                   PRIVATE_CANARY.lower()} <= set(present),
        }, {"leaks": leaks, "event_names": names[:40],
            "canaries_in_store": present, "calls": done},
            witness="teach/approve/undo/mine/reject/label/profile/pair/"
                    "usage/split/sample/export/delete over canary data")


def _dump(w):
    out = []
    for (table,) in w.rows("SELECT name FROM sqlite_master WHERE"
                           " type='table'"):
        cols = [r[1] for r in w.rows(f"PRAGMA table_info({table})")]
        for row in w.rows(f"SELECT * FROM {table}"):
            for col, v in zip(cols, row):
                if isinstance(v, str):
                    out.append((f"{table}.{col}", v))
    return out


@drives("LF-M14-C221")
def c221_candidate_rows_metadata_only(entry):
    with MWorld() as w:
        j = w.job(f"{CTX} please check the modul today")
        cid = w.learning.teach_correction(
            j["job_id"], f"{CTX} please check the module today")[
            "candidate_id"]
        ce = w.learning.approve(cid, counterexamples=(
            f"keep the modul named {CE} here",))
        j2 = w.job(f"{TR} please check the modul again")
        w.observation(j2["job_id"], f"{TR} please check the modul again",
                      f"{TR} please check the module again")
        w.learning.mine_observation_candidates()
        cells = _dump(w)
        outside = sorted({col for col, v in cells
                          for can in (CTX, CE, TR) if can in v.lower()
                          and col != "artifacts.content_text"})
        governed = {can for col, v in cells for can in (CTX, CE, TR)
                    if can in v.lower() and col == "artifacts.content_text"}
        cand = w.candidate(cid)
        ce_json = json.loads(cand["counterexamples"] or "null")
        return check({
            "flip_exercised": bool(ce.get("flips")),
            "canaries_only_in_governed_artifacts": not outside,
            "canaries_live_in_artifacts": governed == {CTX, CE, TR},
            "term_metadata_present": (cand["alias"], cand["canonical"])
                == ("modul", "module"),
            "counterexample_json_content_free":
                isinstance(ce_json, dict) and CE not in blob(ce_json)
                and "modul named" not in blob(ce_json),
        }, {"outside_columns": outside,
            "counterexample_keys": sorted(ce_json) if isinstance(
                ce_json, dict) else None},
            witness="every text column of every table scanned; content"
                    " allowed only in artifacts.content_text")


@drives("LF-M14-C222")
def c222_delete_derived(entry):
    from localflow.v2.notes import NoteStore
    w = MWorld()
    with w:
        extra = cohort(w, n=11, prefix="p", terms_at=())
        a = usage(w)
        jobs = [extra.info[e]["job"]["job_id"] for e in extra.order[:3]]
        _write_facts(a, jobs)
        notes = NoteStore(w.store)
        nid = notes.create_note(f"a note holding {NOTE}")["note_id"]
        s1 = w.profile.compute()
        had = phrase_in(s1) and bool(s1["cards"])
        # Delete source speech (a phrase and card support), the note and
        # selected usage (one job).
        w.training.delete_everywhere(extra.ex(0))
        extra.gone.add(extra.ex(0))
        notes.delete_note(nid)
        a.delete_usage_for_job(jobs[0])
        cur = w.profile.current()
        rows = all_snap_rows(w)
        stale_phrase = [sid for sid, m, _s in rows if phrase_in(m)]
        stale_cards = w.rows(
            "SELECT s.snapshot_id FROM profile_snapshots s JOIN"
            " profile_evidence pe ON pe.snapshot_id=s.snapshot_id WHERE"
            " s.state='current' AND pe.example_id=? AND s.cards_json!='[]'",
            (extra.ex(0),))
        note_left = [col for col, v in _dump(w) if NOTE in v.lower()]
        s2 = w.profile.compute()
        m2 = s2["measured"]
        return check({
            "fixture_phrase_and_cards": had,
            "no_stale_phrase": not stale_phrase and not phrase_in(cur),
            "no_unsupported_current_card": not stale_cards,
            "note_content_gone": not note_left,
            "usage_copies_redacted": all(usage_empty(m)
                                         for _sid, m, _s in rows),
            "recompute_remaining": m2.get("app_usage") == {
                "Alpha App": 1, "Beta App": 1} and not phrase_in(s2)
                and not card_problems(s2, extra),
        }, {"note_columns": note_left, "stale": len(stale_phrase)},
            witness="delete_everywhere + delete_note + delete_usage_for_job"
                    " with a current snapshot")


PRIVATE_PATH = re.compile(r"/Users/|/private/var|/var/folders|scratchpad/"
                          r"|/home/[a-z]|/tmp/")


@drives("LF-M14-C223")
def c223_explicit_local_export(entry):
    with MWorld() as w, capability_traps() as traps:
        fams = w.families(10, asr=True)
        w.splits.assign()
        before = sorted(p.name for p in w.tmp.iterdir())
        out = w.export("ds", ("asr_supervised",))
        after = sorted(p.name for p in w.tmp.iterdir())
        root = w.tmp / "ds"
        readme = (root / "README.md").read_text()
        exs = read_jsonl(root / "examples.jsonl")
        mine = {e["example_id"]: e for e in exs}
        f0 = fams[0]
        audio_ok = f0["example_id"] in mine and wav_frames(
            root / mine[f0["example_id"]]["audio"]) == wav_frames(
            w.store.artifacts_dir / f"{f0['audio_aid']}.wav")
        refs = read_jsonl(root / "references.jsonl")
        text_ok = any(r.get("example_id") == f0["example_id"]
                      and f0["raw"] in blob(r) for r in refs)
        return check({
            "only_destination_created": set(after) - set(before) == {"ds"},
            "disclosed_local_personal": "personal dataset export" in readme
                and "provider upload is a separate explicit decision"
                in readme,
            "permitted_audio_and_text": audio_ok and text_ok
                and len(exs) == 10,
            "no_network_or_mic": not traps,
            "manifest_present": (root / "dataset_manifest.json").is_file(),
        }, {"new_entries": sorted(set(after) - set(before)),
            "records": len(exs), "trap_hits": traps,
            "state": (out or {}).get("state")},
            witness="DatasetExporter.build into a user-chosen temp folder"
                    " under socket/audio-input traps")


@drives("LF-M14-C224")
def c224_no_private_paths(entry):
    import pathlib as _p
    tmp_root = tempfile.gettempdir()
    with MWorld(artifacts="HOMECANARY_arts") as w:
        w.families(10, asr=True)
        w.splits.assign()
        dest = w.tmp / "SESSIONCANARY_dir" / "ds"
        dest.parent.mkdir()
        w.export(dest, ("asr_supervised",))
        texts = {n: (dest / n).read_text() for n in
                 ("README.md", "dataset_manifest.json")}
        needles = [str(w.tmp), str(_p.Path.home()), str(ROOT), tmp_root,
                   "HOMECANARY", "SESSIONCANARY"]
        leaks = sorted({n for n, t in texts.items() for s in needles
                        if s and s in t}
                       | {n for n, t in texts.items()
                          if PRIVATE_PATH.search(t)})
        leaks = list(leaks)
        # Runtime refusals: a destination inside managed data, and an
        # export with collection consent withdrawn.
        n_ev = len(w.events)
        refused, messages = [], []
        for where, prep in ((w.store.artifacts_dir / "SESSIONCANARY_in",
                             None),
                            (w.tmp / "SESSIONCANARY_2" / "ds",
                             lambda: w.store.append_consent("disabled"))):
            if prep:
                prep()
            try:
                w.export(where, ("asr_supervised",))
            except Exception as e:  # noqa: BLE001
                refused.append(type(e).__name__)
                messages.append(str(e))
                continue
            # Not refused: its dataset documents are scanned as well.
            for n in ("README.md", "dataset_manifest.json"):
                t = (where / n).read_text()
                if PRIVATE_PATH.search(t) or any(s in t for s in needles):
                    leaks.append(f"{where.name}/{n}")
        refused = refused or None
        ev_names = sorted({n for n, _kw in w.events[n_ev:]})
        ev_leaks = [n for n, kw in w.events[n_ev:]
                    if any(s in blob(kw) for s in needles)
                    or PRIVATE_PATH.search(blob(kw))]
    committed = []
    files = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "docs/v2/acceptance/M14",
         "docs/v2/handoffs/M14.md"], capture_output=True, text=True
    ).stdout.split()
    for rel in files:
        p = ROOT / rel
        if p.is_file() and PRIVATE_PATH.search(p.read_text(errors="replace")):
            committed.append(rel)
    return check({
        "dataset_docs_clean": not leaks,
        "refusal_reached": refused is not None,
        "refusal_events_clean": not ev_leaks,
        "refusal_messages_path_free": not any(
            PRIVATE_PATH.search(m) or any(s in m for s in needles)
            for m in messages),
        "committed_evidence_clean": not committed and bool(files),
    }, {"leaks": leaks, "event_leaks": len(ev_leaks),
        "refusal_events": ev_names,
        "committed_hits": committed, "files_scanned": len(files),
        "refusal": refused},
        witness="canary directory names in artifact and destination paths;"
                " README/manifest/events/committed M14 evidence scanned")


@drives("LF-M14-C225")
def c225_forward_redaction(entry):
    rel = "docs/v2/acceptance/M14/results.json"

    def git(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a],
                              capture_output=True, text=True)
    revs = git("log", "--format=%H", "--", rel).stdout.split()
    historical = None
    for sha in revs:
        body = git("show", f"{sha}:{rel}").stdout
        if "/Users/" in body:
            historical = (sha, body)
            break
    current = (ROOT / rel).read_text()
    if historical is None:
        return invalid("no historical version with an absolute path",
                       {"versions": len(revs)})
    sha, old = historical
    ancestor = git("merge-base", "--is-ancestor", sha, "HEAD").returncode \
        == 0
    old_j = json.loads(old)
    new_j = json.loads(current)
    new_j.pop("privacy_redactions", None)
    home = re.search(r"/Users/[^/\"\s]+/[^\"\s]*LocalFlow", old)
    restored = json.loads(current.replace("<repo>", home.group(0))
                          if home else current)
    restored.pop("privacy_redactions", None)
    return check({
        "current_redacted": not PRIVATE_PATH.search(current),
        "meanings_unchanged": restored == old_j,
        "history_not_rewritten": ancestor and bool(git(
            "cat-file", "-e", f"{sha}:{rel}").returncode == 0),
        "redaction_recorded": bool(json.loads(current).get(
            "privacy_redactions")),
    }, {"historical": sha[:12]}, witness="git history of results.json:"
        " old version restored from <repo> placeholder equals current")


@contextlib.contextmanager
def capability_traps():
    """Make socket connects/resolution and audio-input APIs raise;
    yields the list of trap hits."""
    import http.client
    import socket
    import urllib.request
    hits = []

    def trap(name):
        def f(*a, **k):
            hits.append(name)
            raise PermissionError(f"capability trap: {name}")
        return f
    targets = [(socket.socket, "connect"), (socket.socket, "connect_ex"),
               (socket.socket, "sendto"), (socket, "create_connection"),
               (socket, "getaddrinfo"), (http.client.HTTPConnection,
                                         "connect"),
               (urllib.request, "urlopen")]
    try:
        import sounddevice as sd
        targets += [(sd, n) for n in ("InputStream", "RawInputStream",
                                      "Stream", "rec", "playrec")]
    except Exception:  # noqa: BLE001 — no audio stack: nothing to trap
        pass
    try:
        from localflow import audio as audio_mod
        targets.append((audio_mod.Recorder, "start"))
    except Exception:  # noqa: BLE001
        pass
    with contextlib.ExitStack() as stack:
        for obj, name in targets:
            stack.enter_context(patched(
                obj, name, lambda o, n=f"{getattr(obj, '__name__', obj)}"
                f".{name}": trap(n)))
        yield hits


@drives("LF-M14-C226")
def c226_network_mic_traps(entry):
    import socket
    with capability_traps() as hits:
        # Trap self-check: the traps are live.
        probes = []
        for fn in (lambda: socket.create_connection(("127.0.0.1", 9)),
                   lambda: __import__("sounddevice").InputStream()):
            try:
                fn()
                probes.append(False)
            except PermissionError:
                probes.append(True)
        armed = all(probes) and len(hits) == 2
        hits.clear()
        with MWorld() as w:
            done, _nid = _exercise_producers(w)
            cand = w.one("SELECT COUNT(*) FROM learning_candidates")[0]
            snaps = snapshots(w)
            recs = len(read_jsonl(w.tmp / "ds" / "examples.jsonl"))
        worked = cand >= 1 and snaps >= 2 and recs >= 10
        seen = list(hits)
    if not armed:
        return invalid("capability traps not live", {"probes": probes})
    return check({"no_network_or_microphone": not seen,
                  "services_did_real_work": worked},
                 {"trap_hits": seen, "candidates": cand, "snapshots": snaps,
                  "exported": recs, "calls": len(done)},
                 witness="socket/http/urllib/sounddevice/Recorder.start"
                         " trapped (proven live) while learning, review,"
                         " profile, usage, splits, sampling and export ran",
                 reached=True)

