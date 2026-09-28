"""The M14 review layer: versioned correction labels, correction
grafts and the review queue (Spec S29.7/S29.9, E19.3).

Labels are per-example VERSIONED rows (``revision`` = prior label count
+ 1): a changed opinion appends, never rewrites. The human decision —
not the classifier — establishes truth; the classifier's axes are the
suggestion shown beside the diff. The EFFECTIVE judgment of an example
is its latest revision, and an abstained latest revision means the
example is unresolved (m14-policy-r1 D01) — the queue, the ASR gate,
readiness and Your Voice all read it through ``effective_judgment_in``.

Grafts: when review confirms specific regions as recognition errors,
``build_graft`` applies only those spans to the source text the
reviewer saw — the label names that source artifact and its hash, and
a different current source refuses the save (D13). The graft reference
is written as a lease-governed artifact with its coverage mask; it
stays weak/partial FOREVER (contracts/references.md) — it never
upgrades to full gold and never grants whole-utterance SFT eligibility
(M14-AC05).

The ASR promotion gate: an example is verified-ASR-trainable only with
an audio-reviewed verbatim reference and original audio that are both
this example's own (the evidence resolver checks job, role, payload and
digest — M14-AUDIT-01), and no ASR blocker: changed_intent in any
revision (permanent), ambiguous/user_rewrite while unresolved. The
export and readiness consume this gate, never a parallel one.
"""

from __future__ import annotations

import json
import time

from .. import ids
from ..store import (TRAINABLE_STATES, Store, grant_lease_row,
                     insert_text_artifact_row)
from ..training_data import _conn_latest, _conn_job_id
from . import classify
from . import evidence as ev

# Reviewer identities recorded on labels.
REVIEWER_USER = "hub_user"

# Edit kinds that bar an example from verified ASR training (S29.7,
# m14-policy-r1 D01): a changed intent is never acoustic truth, in any
# revision; an ambiguous/rewrite edit cannot certify speech until a
# later explicit judgment resolves it.
_ASR_PERMANENT_BLOCKERS = ("changed_intent",)
_ASR_RESOLVABLE_BLOCKERS = ("ambiguous", "user_rewrite")
_ASR_BLOCKING_KINDS = _ASR_PERMANENT_BLOCKERS + _ASR_RESOLVABLE_BLOCKERS


# Job-only (collection off) stage resolution: the job's own History
# artifacts, one slot per stage.
_JOB_STAGE_SLOTS = (("raw", "raw_transcript", "source_text"),
                    ("applied", "applied_output", "applied_output"),
                    ("transform", "transform_output", "transform_output"))


def _latest_job_artifact(conn, job_id, role):
    row = conn.execute(
        "SELECT artifact_id FROM artifacts WHERE job_id=? AND role=? AND"
        " purged=0 ORDER BY rowid DESC LIMIT 1",
        (job_id, role)).fetchone() if job_id else None
    return row[0] if row else None


def stage_texts_for(conn, example_id: str | None,
                    job_id: str | None = None) -> dict:
    """The retained raw/normalized/applied/transform texts the stage
    attribution compares against — each admitted through the evidence
    resolver as this job's own artifact with its producer role (a
    foreign or wrong-stage id is absent, never read). Absent stages stay
    missing — origin attribution then abstains. The envelope's
    ``normalization`` slot names the normalized-text artifact only when
    normalization changed the text; otherwise it names the edit ledger,
    and the normalized text IS the raw text. Without a training example
    (collection off), the job's own History artifacts supply the same
    stages."""
    env, _rev = _conn_latest(conn, example_id) if example_id \
        else (None, None)
    if env is None:
        out = {}
        for stage, role, slot in _JOB_STAGE_SLOTS:
            q = ev.qualify(conn, _latest_job_artifact(conn, job_id, role),
                           slot, job_id=job_id) if job_id else None
            if q and q["ok"]:
                out[stage] = q["artifact"]["text"]
        return out
    # The owner is the example row's job — never what an envelope claims.
    owner = _conn_job_id(conn, example_id)
    arts = env.get("artifact_ids") or {}
    transform_out = arts.get("transform_output") or (
        ((env.get("transform") or {}).get("artifact_ids") or {})
        .get("output"))
    out = {}
    for stage, aid, slot in (("raw", arts.get("source_text"), "source_text"),
                             ("applied", arts.get("applied_output"),
                              "applied_output"),
                             ("transform", transform_out,
                              "transform_output")):
        q = ev.qualify(conn, aid, slot, job_id=owner) if aid else None
        if q and q["ok"]:
            out[stage] = q["artifact"]["text"]
    norm_aid = arts.get("normalization")
    q = ev.qualify(conn, norm_aid, "normalization", job_id=owner) \
        if norm_aid else None
    if q and q["ok"]:
        if q["artifact"]["role"] == "normalized_text":
            out["normalized"] = q["artifact"]["text"]
        elif "raw" in out:
            out["normalized"] = out["raw"]  # the stage changed nothing
    return out


def effective_judgment_in(conn, example_id) -> dict:
    """The one effective-judgment reducer (m14-policy-r1 D01).

    ``effective`` is the latest revision when it is not abstained, else
    None (``unresolved`` — the reviewer's current opinion is
    uncertainty). ``asr_block`` names the blocking kind that bars
    verified ASR use: changed_intent in ANY revision (permanent), or
    ambiguous/user_rewrite in any revision unless the effective
    judgment exists and is itself non-blocking (an explicit resolution).
    Abstention never resolves a blocker."""
    rows = conn.execute(
        "SELECT revision, edit_kind, abstained, domains_json FROM"
        " correction_labels WHERE example_id=? ORDER BY revision",
        (example_id,)).fetchall()
    latest = rows[-1] if rows else None
    effective = None
    if latest is not None and not latest[2]:
        effective = {"revision": latest[0], "edit_kind": latest[1],
                     "domains": json.loads(latest[3] or "[]")}
    history = [r[1] for r in rows]
    block = None
    if any(k in _ASR_PERMANENT_BLOCKERS for k in history):
        block = "changed_intent"
    else:
        pending = [k for k in history if k in _ASR_RESOLVABLE_BLOCKERS]
        resolved = effective is not None \
            and effective["edit_kind"] not in _ASR_BLOCKING_KINDS
        if pending and not resolved:
            block = pending[-1]
    return {"effective": effective, "revisions": len(rows),
            "unresolved": latest is not None and effective is None,
            "asr_block": block}


def verified_asr_eligible_in(conn, example_id: str,
                             artifacts_dir=None) -> dict:
    """The ASR promotion gate INSIDE a writer op (S29.6/M14-AC05):
    True eligibility for VERIFIED ASR training needs a live state, no
    ASR blocker under the effective-judgment policy, an audio-reviewed
    verbatim reference and original audio — each this example's OWN
    retained artifact with its producer role and matching digest. A
    span graft alone NEVER satisfies this: partial stays partial. The
    admitted reference and audio ride along for the exporter."""
    env, _rev = _conn_latest(conn, example_id)
    if env is None:
        return {"eligible": False, "reason": "no_example"}
    state_row = conn.execute(
        "SELECT state, job_id FROM training_examples WHERE example_id=?",
        (example_id,)).fetchone()
    state = state_row[0] if state_row else "deleted"
    if state not in TRAINABLE_STATES:
        return {"eligible": False, "reason": f"state_{state}"}
    job_id = state_row[1]
    judgment = effective_judgment_in(conn, example_id)
    if judgment["asr_block"]:
        return {"eligible": False,
                "reason": f"blocking_label_{judgment['asr_block']}"}
    verbatim = [a for a in (env.get("annotations") or [])
                if a.get("kind") == "verbatim_reference"
                and a.get("listened_audio") is True]
    if not verbatim:
        return {"eligible": False, "reason": "no_audio_reviewed_verbatim"}
    annotation = verbatim[-1]  # the latest review supersedes earlier ones
    ref = ev.qualify(conn, annotation.get("artifact_id"),
                     "verbatim_reference", job_id=job_id)
    if not ref["ok"]:
        return {"eligible": False, "reason": ref["reason"]}
    if annotation.get("text_sha256") and ids.sha256_text(
            ref["artifact"]["text"]) != annotation["text_sha256"]:
        return {"eligible": False,
                "reason": "verbatim_reference_digest_mismatch"}
    audio_aid = (env.get("artifact_ids") or {}).get("original_audio")
    if not audio_aid:
        return {"eligible": False, "reason": "no_retained_audio"}
    audio = ev.qualify(conn, audio_aid, "original_audio", job_id=job_id,
                       artifacts_dir=artifacts_dir)
    if not audio["ok"]:
        return {"eligible": False, "reason": audio["reason"]}
    return {"eligible": True, "reason": None, "job_id": job_id,
            "annotation": annotation, "reference": ref["artifact"],
            "audio": audio["artifact"]}


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
        (S29.9). ``labeled`` means an effective judgment exists (D01)."""
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
        return effective_judgment_in(conn, example_id)["effective"] \
            is not None

    def _suggested_axes(self, conn, example_id) -> dict:
        """Machine-suggested axes for an example with an observation:
        the classifier over the observed edit, evidence_status
        heuristic_candidate — visibly unverified until review. The
        observation's before/after must be this job's own observation
        artifacts."""
        job_id = _conn_job_id(conn, example_id)
        obs = conn.execute(
            "SELECT before_artifact_id, after_artifact_id FROM"
            " insertion_observations WHERE job_id=? AND edited=1 ORDER BY"
            " rowid DESC LIMIT 1", (job_id,)).fetchone() if job_id \
            else None
        if obs is None:
            return {}
        before = ev.qualify(conn, obs[0], "observation_before",
                            job_id=job_id)
        after = ev.qualify(conn, obs[1], "observation_after",
                           job_id=job_id)
        if not (before["ok"] and after["ok"]):
            return {}
        return classify.classify_observation(
            before["artifact"]["text"], after["artifact"]["text"],
            stage_texts=stage_texts_for(conn, example_id),
            evidence_status="heuristic_candidate")

    # ---- labels (versioned, append-only per example) ------------------------

    def record_label(self, example_id: str, *, edit_kind: str,
                     origin_stages=(), domains=(), pipeline_effect="unknown",
                     evidence_status="explicit_intent_review",
                     reviewer=REVIEWER_USER, abstained=False,
                     confirmed_spans=None, notes=None,
                     expected_source_artifact_id=None,
                     expected_source_sha256=None,
                     operation_id=None) -> dict:
        """Append one reviewed label revision. ``confirmed_spans`` are
        the reviewed regions accepted as recognition corrections — the
        graft inputs, as code-point offsets into the exact source text
        the reviewer saw: ``expected_source_artifact_id`` /
        ``expected_source_sha256`` name it, and a different current
        source refuses as ``stale_source`` (D13). The graft artifact is
        lease-governed and the label row carries the coverage mask.
        Everything is ONE writer op: label row + graft artifact + example
        state + the operation receipt move together; a retry of the same
        ``operation_id`` returns the recorded receipt and writes nothing
        (M14-AUDIT-17)."""
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
        spans = _admit_spans(confirmed_spans)

        def op(conn):
            try:
                done = ev.receipt_in(conn, operation_id, "label", example_id)
            except ev.OperationReused as e:
                return {"refused": str(e)}
            if done is not None:
                return done
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
            if spans:
                src = ev.qualify(conn, (env.get("artifact_ids") or {}).get(
                    "source_text"), "source_text", job_id=job_id)
                if not src["ok"]:
                    return {"refused": "no_retained_source_text"}
                source = src["artifact"]["text"]
                if expected_source_artifact_id is not None and \
                        src["artifact"]["id"] != expected_source_artifact_id:
                    return {"refused": "stale_source"}
                if expected_source_sha256 is not None and \
                        ids.sha256_text(source) != expected_source_sha256:
                    return {"refused": "stale_source"}
                # Spans must index the raw source text the graft is
                # applied to — offsets into the cleaned/observed text
                # would splice the correction into the wrong place.
                for span in spans:
                    if span["end"] > len(source) or classify.words_of(
                            source[span["start"]:span["end"]]) \
                            != list(span["before_words"]):
                        return {"refused": "span_not_in_source_text"}
                graft = classify.build_graft(source, spans)
                if graft is None:
                    return {"refused": "overlapping_confirmed_spans"}
                graft["source_artifact_id"] = src["artifact"]["id"]
                graft["source_sha256"] = ids.sha256_text(source)
                now = ids.now_utc_iso()
                graft_artifact = insert_text_artifact_row(
                    conn, artifact_id=ids.new_id("art"), job_id=job_id,
                    stage="review", role="span_graft",
                    text=json.dumps(graft, ensure_ascii=False,
                                    sort_keys=True),
                    kind="graft_json", retention_class="training",
                    parent_artifact_id=src["artifact"]["id"],
                    meta={"example_id": example_id,
                          "coverage_spans": len(graft["coverage"]),
                          "source_sha256": graft["source_sha256"]},
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
            return ev.record_receipt_in(
                conn, operation_id, "label", example_id,
                {"label_id": label_id, "revision": revision,
                 "graft_artifact_id": graft_artifact})
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
        out = self.store.submit(
            lambda conn: verified_asr_eligible_in(
                conn, example_id, self.store.artifacts_dir))
        return {"eligible": out["eligible"], "reason": out["reason"]}

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

    _COMPARABLE = ev.COMPARABLE

    def preference_pairs(self, limit: int = 100) -> list[dict]:
        """Same-task candidate pairs awaiting an explicit comparable
        judgment. Only tasks with ≥ 2 retained candidates appear; the
        M11 store already refused cross-task judgments at write time,
        so every pair here shares its task key by construction. A pair
        with no judgment yet is UNREVIEWED — display order is recorded
        on the candidates, and the last-applied candidate is never a
        winner (S29.10). Each task carries its retained source text and
        every candidate's output text (resolved through the evidence
        resolver; ``None`` when not retained) — the pane shows exactly
        what is judged (m14-policy-r1 D15)."""
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
                    " output_artifact_id, source_sha256 FROM"
                    " transform_candidates WHERE task_key=? ORDER BY"
                    " display_order, created_at_utc, candidate_id",
                    (task_key,)).fetchall()
                judgments = conn.execute(
                    "SELECT judgment, candidate_id, candidate_b_id FROM"
                    " preference_observations WHERE task_key=? ORDER BY"
                    " rowid", (task_key,)).fetchall()
                comparable = [j for j in judgments
                              if j[0] in self._COMPARABLE]
                source_text = None
                rendered = []
                for c in candidates:
                    src = ev.qualify(conn, c[4], "transform_source",
                                     task_key=task_key)
                    if source_text is None and src["ok"] and \
                            ids.sha256_text(src["artifact"]["text"]) \
                            == c[6]:
                        source_text = src["artifact"]["text"]
                    outq = ev.qualify(conn, c[5], "transform_output",
                                      task_key=task_key)
                    rendered.append(
                        {"candidate_id": c[0], "transform_id": c[1],
                         "path": c[2], "display_order": c[3],
                         "source_artifact_id": c[4],
                         "output_artifact_id": c[5],
                         "text": outq["artifact"]["text"]
                         if outq["ok"] else None})
                out.append({
                    "task_key": task_key,
                    "source_text": source_text,
                    "candidates": rendered,
                    "judgment_count": len(judgments),
                    "comparable_judgment": (
                        comparable[-1][0] if comparable else None),
                })
            return out
        return self.store.submit(op)

    def record_pair_judgment(self, transforms_store, task_key: str,
                             candidate_a: str, candidate_b: str,
                             judgment: str, reason_code=None,
                             operation_id=None) -> str:
        """Record one explicit A/B/tie/neither/uncertain judgment on a
        same-task pair (the M11 write-time same-task invariant is the
        enforcement; a judgment across task keys refuses). The pair is
        stored in the order given — ``candidate_id`` is A,
        ``candidate_b_id`` is B — so ``prefer_a``/``prefer_b`` name the
        winner by slot, the reading the exporter applies. A retry of the
        same ``operation_id`` returns the recorded observation id and
        writes nothing. accept/reject/undo are NOT comparable judgments
        (they stay single-candidate observations)."""
        from ..transforms_store import conn_record_observation
        if judgment not in self._COMPARABLE:
            raise ValueError(
                f"judgment must be one of {self._COMPARABLE}")

        def op(conn):
            try:
                done = ev.receipt_in(conn, operation_id, "pair_judgment",
                                   task_key)
            except ev.OperationReused as e:
                return {"refused": str(e)}
            if done is not None:
                return done
            try:
                obs = conn_record_observation(
                    conn, task_key=task_key, candidate_id=candidate_a,
                    candidate_b_id=candidate_b, judgment=judgment,
                    provenance="m14_pair_review", reason_code=reason_code)
            except ValueError as e:
                return {"refused": str(e)}
            return ev.record_receipt_in(
                conn, operation_id, "pair_judgment", task_key,
                {"observation_id": obs})
        target = transforms_store.store if transforms_store is not None \
            else self.store
        out = target.submit(op)
        if out.get("refused"):
            raise ValueError(out["refused"])
        return out["observation_id"]


def _admit_spans(spans):
    """Strict primitive admission of confirmed spans (D13): a list of
    objects whose start/end are non-negative ints (never bool/float/
    str) with start <= end, and whose before/after words are lists of
    strings. Anything else refuses before any write."""
    if spans is None:
        return None
    if not isinstance(spans, (list, tuple)):
        raise ValueError("confirmed_spans_not_a_list")
    out = []
    for span in spans:
        if not isinstance(span, dict):
            raise ValueError("confirmed_span_not_an_object")
        start, end = span.get("start"), span.get("end")
        for v in (start, end):
            if type(v) is not int or v < 0:
                raise ValueError("confirmed_span_offset_not_a_code_point")
        if start > end:
            raise ValueError("confirmed_span_reversed")
        for key in ("before_words", "after_words"):
            words = span.get(key)
            if not isinstance(words, (list, tuple)) or not all(
                    isinstance(w, str) for w in words):
                raise ValueError("confirmed_span_words_invalid")
        out.append({"start": start, "end": end,
                    "before_words": list(span["before_words"]),
                    "after_words": list(span["after_words"])})
    return out
