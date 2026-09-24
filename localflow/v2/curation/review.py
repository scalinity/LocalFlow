"""The M14 review layer: versioned correction labels, correction
grafts and the review queue (Spec S29.7/S29.9, E19.3).

Labels are per-example VERSIONED rows (``revision`` = prior label count
+ 1): a changed opinion appends, never rewrites. The human decision —
not the classifier — establishes truth; the classifier's axes are the
suggestion shown beside the diff.

Grafts: when review confirms specific regions as recognition errors,
``build_graft`` applies only those spans to the source text. The graft
reference is written as a lease-governed artifact with its coverage
mask; it stays weak/partial FOREVER (contracts/references.md) — it
never upgrades to full gold and never grants whole-utterance SFT
eligibility (M14-AC05).

The ASR promotion gate: an example is verified-ASR-trainable only with
an audio-reviewed verbatim reference AND no changed-intent / abstained
critical label. Wrong-target and changed-intent fixtures are structurally
refused here — the export layers consume this gate, never a parallel
one.
"""

from __future__ import annotations

import json
import time

from .. import ids
from ..store import (TRAINABLE_STATES, Store, grant_lease_row,
                     insert_text_artifact_row)
from ..store import conn_artifact_text as _conn_artifact_text
from ..training_data import _conn_latest, _conn_job_id
from . import classify

# Reviewer identities recorded on labels.
REVIEWER_USER = "hub_user"

# Edit kinds that permanently bar an example from verified ASR training
# (S29.7: a changed date is a new intent, never acoustic truth; an
# ambiguous/unresolved edit cannot certify speech).
_ASR_BLOCKING_KINDS = ("changed_intent", "ambiguous", "user_rewrite")


_JOB_STAGE_ROLES = (("raw", "raw_transcript"),
                    ("normalized", "normalized_text"),
                    ("applied", "applied_output"),
                    ("transform", "transform_output"))


def stage_texts_for(conn, example_id: str | None,
                    job_id: str | None = None) -> dict:
    """The retained raw/normalized/applied/transform texts the stage
    attribution compares against (absent stages stay missing — origin
    attribution then abstains). The envelope's ``normalization`` slot
    names the normalized-text artifact only when normalization changed
    the text; otherwise it names the edit ledger, and the normalized
    text IS the raw text. Without a training example (collection off),
    the job's own History artifacts supply the same stages."""
    env, _rev = _conn_latest(conn, example_id) if example_id \
        else (None, None)
    if env is None:
        out = {}
        for stage, role in _JOB_STAGE_ROLES:
            row = conn.execute(
                "SELECT content_text FROM artifacts WHERE job_id=? AND"
                " role=? AND purged=0 AND content_text IS NOT NULL"
                " ORDER BY rowid DESC LIMIT 1",
                (job_id, role)).fetchone() if job_id else None
            if row is not None:
                out[stage] = row[0]
        return out
    arts = env.get("artifact_ids") or {}
    out = {}
    for stage, key in (("raw", "source_text"),
                       ("applied", "applied_output"),
                       ("transform", "transform_output")):
        text = _conn_artifact_text(conn, arts.get(key))
        if text is not None:
            out[stage] = text
    norm_aid = arts.get("normalization")
    role = conn.execute(
        "SELECT role FROM artifacts WHERE artifact_id=?",
        (norm_aid,)).fetchone() if norm_aid else None
    if role and role[0] == "normalized_text":
        text = _conn_artifact_text(conn, norm_aid)
        if text is not None:
            out["normalized"] = text
    elif role and role[0] == "normalization_ledger" and "raw" in out:
        out["normalized"] = out["raw"]  # the stage changed nothing
    return out


def verified_asr_eligible_in(conn, example_id: str) -> dict:
    """The ASR promotion gate INSIDE a writer op (S29.6/M14-AC05):
    True eligibility for VERIFIED ASR training needs an audio-reviewed
    verbatim reference, a live state, retained audio — and no label
    revision whose edit_kind bars ASR use (changed_intent forever;
    ambiguous/user_rewrite while unresolved). A span graft alone NEVER
    satisfies this: partial stays partial."""
    from ..training_data import _conn_latest
    env, _rev = _conn_latest(conn, example_id)
    if env is None:
        return {"eligible": False, "reason": "no_example"}
    state_row = conn.execute(
        "SELECT state FROM training_examples WHERE example_id=?",
        (example_id,)).fetchone()
    state = state_row[0] if state_row else "deleted"
    if state in ("excluded", "quarantined_sensitive", "deleted",
                 "expired"):
        return {"eligible": False, "reason": f"state_{state}"}
    blocking = conn.execute(
        "SELECT edit_kind FROM correction_labels WHERE"
        " example_id=? AND edit_kind IN ({})".format(
            ",".join("?" * len(_ASR_BLOCKING_KINDS))),
        (example_id, *_ASR_BLOCKING_KINDS)).fetchall()
    if blocking:
        return {"eligible": False,
                "reason": f"blocking_label_{blocking[0][0]}"}
    verbatim = any(
        a.get("kind") == "verbatim_reference"
        and a.get("listened_audio")
        for a in (env.get("annotations") or []))
    if not verbatim:
        return {"eligible": False, "reason": "no_audio_reviewed_verbatim"}
    audio = (env.get("artifact_ids") or {}).get("original_audio")
    if not audio:
        return {"eligible": False, "reason": "no_retained_audio"}
    arow = conn.execute(
        "SELECT purged FROM artifacts WHERE artifact_id=?",
        (audio,)).fetchone()
    if arow is None or arow[0]:
        return {"eligible": False, "reason": "audio_unavailable"}
    return {"eligible": True, "reason": None}


class ReviewService:
    """Classification review, label persistence and graft writing over
    the single-writer store."""

    def __init__(self, store: Store, emit=None):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)

    # ---- the queue ----------------------------------------------------------

    def queue(self, limit: int = 200) -> list[dict]:
        """What review owes attention to, priority-ordered:
        (1) live examples with an observed edit (an S29.8 window that
        stopped owned_range_edited, or a mined learning candidate)
        whose latest classification is still machine-suggested;
        (2) pending learning candidates — each row carries its
        ``candidate_id`` (a teach with collection off has no example and
        is keyed by its candidate). Suppressed pairs never reappear: a
        rejected suggestion stays gone (S11). Unlabeled sampled examples
        (the M14-B stream) join the same queue with their stratum. One
        row per example — repeated triggers never mint duplicates
        (S29.9)."""
        def op(conn):
            rows = []
            seen = set()
            for row in conn.execute(
                    "SELECT candidate_id, example_id, job_id, source,"
                    " status, classification_json, proposed_alias,"
                    " proposed_canonical FROM learning_candidates"
                    " WHERE status='pending' ORDER BY rowid DESC LIMIT ?",
                    (limit,)).fetchall():
                cand_id, ex_id = row[0], row[1]
                key = ex_id or cand_id
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "candidate_id": cand_id,
                    "example_id": ex_id, "job_id": row[2],
                    "kind": "learning_candidate", "source": row[3],
                    "candidate_status": row[4],
                    "suggestion": ({"alias": row[6], "canonical": row[7]}
                                   if row[6] else None),
                    "classification": json.loads(row[5] or "{}"),
                    "labeled": self._labeled(conn, ex_id)
                    if ex_id else False,
                })
            for ex_id, job_id, st in conn.execute(
                    "SELECT example_id, job_id, state FROM"
                    " training_examples WHERE state='review_candidate'"
                    " ORDER BY rowid DESC LIMIT ?",
                    (limit,)).fetchall():
                if ex_id in seen:
                    continue
                seen.add(ex_id)
                rows.append({
                    "candidate_id": None,
                    "example_id": ex_id, "job_id": job_id,
                    "kind": "sampled_example", "source": "sampling",
                    "candidate_status": st, "suggestion": None,
                    "classification": self._suggested_axes(conn, ex_id),
                    "labeled": self._labeled(conn, ex_id),
                })
            return rows[:limit]
        return self.store.submit(op)

    def _labeled(self, conn, example_id) -> bool:
        return conn.execute(
            "SELECT 1 FROM correction_labels WHERE example_id=? AND"
            " abstained=0 LIMIT 1", (example_id,)).fetchone() is not None

    def _suggested_axes(self, conn, example_id) -> dict:
        """Machine-suggested axes for an example with an observation:
        the classifier over the observed edit, evidence_status
        heuristic_candidate — visibly unverified until review."""
        obs = conn.execute(
            "SELECT b.content_text, a.content_text FROM"
            " insertion_observations o JOIN artifacts b ON"
            " b.artifact_id=o.before_artifact_id JOIN artifacts a ON"
            " a.artifact_id=o.after_artifact_id WHERE o.job_id=("
            " SELECT job_id FROM training_examples WHERE example_id=?)"
            " AND o.edited=1 ORDER BY o.rowid DESC LIMIT 1",
            (example_id,)).fetchone()
        if obs is None or obs[0] is None or obs[1] is None:
            return {}
        return classify.classify_observation(
            obs[0], obs[1],
            stage_texts=stage_texts_for(conn, example_id),
            evidence_status="heuristic_candidate")

    # ---- labels (versioned, append-only per example) ------------------------

    def record_label(self, example_id: str, *, edit_kind: str,
                     origin_stages=(), domains=(), pipeline_effect="unknown",
                     evidence_status="explicit_intent_review",
                     reviewer=REVIEWER_USER, abstained=False,
                     confirmed_spans=None, notes=None) -> dict:
        """Append one reviewed label revision. ``confirmed_spans`` are
        the reviewed regions accepted as recognition corrections — the
        graft inputs; their artifact is lease-governed and the label
        row carries the coverage mask. Everything is ONE writer op:
        label row + graft artifact + example state move together."""
        if edit_kind not in classify.AXIS_EDIT_KINDS:
            raise ValueError(f"unknown edit_kind {edit_kind!r}")
        for stage in origin_stages:
            if stage not in classify.AXIS_ORIGIN_STAGES:
                raise ValueError(f"unknown origin stage {stage!r}")
        for domain in domains:
            if domain not in classify.AXIS_DOMAINS:
                raise ValueError(f"unknown domain {domain!r}")
        if pipeline_effect not in classify.AXIS_EFFECTS:
            raise ValueError(f"unknown pipeline_effect {pipeline_effect!r}")
        if evidence_status not in classify.AXIS_EVIDENCE:
            raise ValueError(
                f"unknown evidence_status {evidence_status!r}")

        def op(conn):
            env, _rev = _conn_latest(conn, example_id)
            if env is None:
                return {"refused": f"no_example:{example_id}"}
            state = conn.execute(
                "SELECT state FROM training_examples WHERE example_id=?",
                (example_id,)).fetchone()
            if state is None or state[0] not in TRAINABLE_STATES:
                # A label never lands on deleted, expired, excluded or
                # quarantined evidence — the state move below would
                # otherwise hand it back to export and the ASR gate.
                return {"refused": "example_not_reviewable:"
                                   f"{state[0] if state else 'missing'}"}
            job_id = _conn_job_id(conn, example_id)
            revision = 1 + (conn.execute(
                "SELECT COUNT(*) FROM correction_labels WHERE"
                " example_id=?", (example_id,)).fetchone()[0])
            graft_artifact = None
            if confirmed_spans:
                source = _conn_artifact_text(
                    conn, (env.get("artifact_ids") or {}).get(
                        "source_text"))
                if source is None:
                    return {"refused": "no_retained_source_text"}
                # Spans must index the raw source text the graft is
                # applied to — offsets into the cleaned/observed text
                # would splice the correction into the wrong place.
                for span in confirmed_spans:
                    if not 0 <= span["start"] <= span["end"] \
                            <= len(source) or classify.words_of(
                                source[span["start"]:span["end"]]) \
                            != list(span["before_words"]):
                        return {"refused": "span_not_in_source_text"}
                graft = classify.build_graft(source, confirmed_spans)
                if graft is None:
                    return {"refused": "overlapping_confirmed_spans"}
                now = ids.now_utc_iso()
                graft_artifact = insert_text_artifact_row(
                    conn, artifact_id=ids.new_id("art"), job_id=job_id,
                    stage="review", role="span_graft",
                    text=json.dumps(graft, ensure_ascii=False,
                                    sort_keys=True),
                    kind="graft_json", retention_class="training",
                    parent_artifact_id=(env.get("artifact_ids") or {}).get(
                        "source_text"),
                    meta={"example_id": example_id,
                          "coverage_spans": len(graft["coverage"])},
                    created_at_utc=now)
                grant_lease_row(conn, graft_artifact, "training",
                                days=None, granted_at_epoch=time.time())
            now = ids.now_utc_iso()
            label_id = ids.new_id("lbl")
            conn.execute(
                "INSERT INTO correction_labels(label_id, example_id,"
                " revision, origin_stages_json, edit_kind, domains_json,"
                " pipeline_effect, evidence_status, reviewer, abstained,"
                " graft_artifact_id, notes, created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (label_id, example_id, revision,
                 json.dumps(sorted(set(origin_stages))),
                 edit_kind, json.dumps(sorted(set(domains))),
                 pipeline_effect, evidence_status, reviewer,
                 1 if abstained else 0, graft_artifact, notes, now))
            if not abstained:
                conn.execute(
                    "UPDATE training_examples SET state='annotated',"
                    " updated_at_utc=? WHERE example_id=?",
                    (now, example_id))
            return {"label_id": label_id, "revision": revision,
                    "graft_artifact_id": graft_artifact}
        out = self.store.submit(op)
        if out.get("refused"):
            # Raised after the op: an in-op raise surfaces wrapped as a
            # RuntimeError (contracts/store.md).
            raise ValueError(out["refused"])
        self.emit("training.label_recorded", level="INFO",
                  reason_code=edit_kind, outcome="abstained"
                  if abstained else "reviewed")
        return out

    def labels(self, example_id: str) -> list[dict]:
        def op(conn):
            rows = conn.execute(
                "SELECT label_id, revision, origin_stages_json,"
                " edit_kind, domains_json, pipeline_effect,"
                " evidence_status, reviewer, abstained,"
                " graft_artifact_id, notes, created_at_utc FROM"
                " correction_labels WHERE example_id=? ORDER BY revision",
                (example_id,)).fetchall()
            return [{
                "label_id": r[0], "revision": r[1],
                "origin_stages": json.loads(r[2]),
                "edit_kind": r[3], "domains": json.loads(r[4]),
                "pipeline_effect": r[5], "evidence_status": r[6],
                "reviewer": r[7], "abstained": bool(r[8]),
                "graft_artifact_id": r[9], "notes": r[10],
                "created_at_utc": r[11],
            } for r in rows]
        return self.store.submit(op)

    # ---- the ASR promotion gate (M14-AC05) -----------------------------------

    def verified_asr_eligible(self, example_id: str) -> dict:
        """See ``verified_asr_eligible_in`` (the connection-level
        helper the export layer shares — one gate, never two)."""
        return self.store.submit(
            lambda conn: verified_asr_eligible_in(conn, example_id))

    # ---- coverage (readiness inputs, E19.4) ----------------------------------

    def label_coverage(self) -> dict:
        """Per-kind label counts, abstention and confusion between
        recognition error and changed intent — counts with
        denominators, never rates over a population."""
        def op(conn):
            by_kind = {}
            for kind, n in conn.execute(
                    "SELECT edit_kind, COUNT(*) FROM correction_labels"
                    " GROUP BY edit_kind").fetchall():
                by_kind[kind] = n
            total = sum(by_kind.values())
            abstained = conn.execute(
                "SELECT COUNT(*) FROM correction_labels WHERE"
                " abstained=1").fetchone()[0]
            recast = conn.execute(
                "SELECT COUNT(*) FROM correction_labels WHERE"
                " edit_kind='recognition_error' AND"
                " EXISTS (SELECT 1 FROM correction_labels other WHERE"
                " other.example_id=correction_labels.example_id AND"
                " other.revision < correction_labels.revision AND"
                " other.edit_kind='changed_intent')").fetchone()[0]
            return {
                "labels_total": total,
                "by_edit_kind": by_kind,
                "abstained": abstained,
                "abstention_note": "uncertain labels / reviewed"
                                   " candidates, with stage/class"
                                   " coverage (E19.4)",
                "recognition_after_changed_intent_revisions": recast,
            }
        return self.store.submit(op)

    # ---- same-input preference pairs (S29.10 / M14-B task 8) ------------------

    _COMPARABLE = ("prefer_a", "prefer_b", "tie", "neither", "uncertain")

    def preference_pairs(self, limit: int = 100) -> list[dict]:
        """Same-task candidate pairs awaiting an explicit comparable
        judgment. Only tasks with ≥ 2 retained candidates appear; the
        M11 store already refused cross-task judgments at write time,
        so every pair here shares its task key by construction. A pair
        with no judgment yet is UNREVIEWED — display order is recorded
        on the candidates, and the last-applied candidate is never a
        winner (S29.10)."""
        def op(conn):
            tasks = [r[0] for r in conn.execute(
                "SELECT task_key FROM transform_candidates GROUP BY"
                " task_key HAVING COUNT(*) >= 2 ORDER BY MAX(rowid)"
                " DESC LIMIT ?", (limit,)).fetchall()]
            out = []
            for task_key in tasks:
                candidates = conn.execute(
                    "SELECT candidate_id, transform_id, path,"
                    " display_order, source_artifact_id,"
                    " output_artifact_id FROM transform_candidates"
                    " WHERE task_key=? ORDER BY display_order,"
                    " created_at_utc", (task_key,)).fetchall()
                judgments = conn.execute(
                    "SELECT judgment, candidate_id, candidate_b_id FROM"
                    " preference_observations WHERE task_key=? ORDER BY"
                    " rowid", (task_key,)).fetchall()
                comparable = [j for j in judgments
                              if j[0] in ("prefer_a", "prefer_b", "tie",
                                          "neither", "uncertain")]
                out.append({
                    "task_key": task_key,
                    "candidates": [
                        {"candidate_id": c[0], "transform_id": c[1],
                         "path": c[2], "display_order": c[3],
                         "source_artifact_id": c[4],
                         "output_artifact_id": c[5]}
                        for c in candidates],
                    "judgment_count": len(judgments),
                    "comparable_judgment": (
                        comparable[-1][0] if comparable else None),
                })
            return out
        return self.store.submit(op)

    def record_pair_judgment(self, transforms_store, task_key: str,
                             candidate_a: str, candidate_b: str,
                             judgment: str, reason_code=None) -> str:
        """Record one explicit A/B/tie/neither/uncertain judgment on a
        same-task pair through the M11 store (its write-time same-task
        invariant is the enforcement; a judgment across task keys
        refuses there). The pair is stored in the order given —
        ``candidate_id`` is A, ``candidate_b_id`` is B — so
        ``prefer_a``/``prefer_b`` name the winner by slot, the reading
        the exporter applies. accept/reject/undo are NOT comparable
        judgments (they stay single-candidate observations)."""
        if judgment not in self._COMPARABLE:
            raise ValueError(
                f"judgment must be one of {self._COMPARABLE}")
        return transforms_store.record_observation(
            task_key=task_key, candidate_id=candidate_a,
            candidate_b_id=candidate_b, judgment=judgment,
            provenance="m14_pair_review", reason_code=reason_code)
