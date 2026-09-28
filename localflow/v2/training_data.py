"""Models → Training Data inspector (V2 M09, Spec S29.15/S29.6,
contract hub.md).

A functional inspector over already-collected records: replay inputs,
stage comparisons, completeness/retention display, explicit
mark-correct/incorrect, span correction, pin/exclude and
delete-everywhere — with no training engine, provider account or
placeholder control anywhere (M09-AC06). M14 adds mining, classified
review, splits and export on top of the same surface.

Annotation semantics (S29.6, M09-AC05):

- **Intended-writing mark** — an explicit whole-example judgment
  (``mark_intended``): the user asserts the final text was / was not
  what they meant. It is *not* acoustic truth and never creates a
  verbatim reference.
- **Verbatim reference** — audio-reviewed words (``set_verbatim``).
  The service refuses to save one unless ``listened_audio`` is true
  (E14: listen before assigning verbatim references); the Hub gates the
  control on actual replay.
- **Span correction** — a reviewed local change with explicit coverage
  (``add_span_correction``). It verifies that span only: the envelope's
  whole-example ``outcome.correctness`` is left untouched (correcting
  one token does not verify the entire recording), and the annotation
  carries ``coverage: "partial"`` forever — it never upgrades to full
  gold (contracts/references.md).

Every mutation is ONE store op on the writer thread (direct SQL against
the connection, the ``vocabulary_store`` pattern — never a nested
``Store`` call, which would deadlock the writer): annotation payload,
artifact row and revision append commit atomically. Payload text
(verbatim text, correction payloads) lives in lease-governed store
artifacts referenced by id from content-free envelope entries (S29.14).
"""

from __future__ import annotations

import json
import time

from . import ids
from .store import (TRAINABLE_STATES, conn_append_revision,
                    grant_lease_row, insert_text_artifact_row)

EXAMPLE_STATES = ("captured_unreviewed", "review_candidate", "annotated",
                  "ambiguous", "quarantined_sensitive", "excluded",
                  "expired", "deleted")

# Annotation payload artifacts carry their own never-expiring training
# leases (reviewed evidence is retained until explicitly removed,
# S29.14) — they are NOT user pins, and pin/unpin must never revoke
# them. Both operations scope to artifacts outside these roles.
_ANNOTATION_ROLES = ("verbatim_reference", "span_correction")

# States no review may write to (the learning contract's non-reviewable
# set): purged, content-flagged, past retention, or excluded by the
# user. An annotation is a label, never a Restore.
NON_REVIEWABLE_STATES = ("deleted", "expired", "quarantined_sensitive",
                         "excluded")


def conn_assert_reviewable(conn, example_id):
    """The one writer-time reviewability predicate, checked INSIDE the
    annotation op before any artifact/lease/revision is written."""
    row = conn.execute(
        "SELECT state FROM training_examples WHERE example_id=?",
        (example_id,)).fetchone()
    if row is None:
        raise ValueError(f"no example {example_id}")
    if row[0] in NON_REVIEWABLE_STATES:
        raise ValueError(f"example_not_reviewable: {row[0]}")


def _existing_annotation(env, annotation_id):
    if not annotation_id:
        return None
    return next((a for a in env.get("annotations") or []
                 if a.get("annotation_id") == annotation_id), None)


def _conn_grant_lease(conn, artifact_id, holder, days=None):
    return grant_lease_row(conn, artifact_id, holder, days=days,
                           granted_at_epoch=time.time())


def _conn_write_text_artifact(conn, *, job_id, stage, role, text,
                              kind="text", retention_class="training",
                              parent_artifact_id=None, meta=None):
    """``Store.write_text_artifact`` as inline SQL for use INSIDE a
    writer-thread op (same columns, same immutability — the shared
    ``insert_text_artifact_row`` keeps the two from drifting)."""
    artifact_id = ids.new_id("art")
    insert_text_artifact_row(
        conn, artifact_id=artifact_id, job_id=job_id, stage=stage,
        role=role, text=text, kind=kind,
        retention_class=retention_class,
        parent_artifact_id=parent_artifact_id, meta=meta,
        created_at_utc=ids.now_utc_iso())
    return artifact_id


def _conn_append_revision(conn, example_id, env, parent_revision_id):
    # M02 remediation: the store's one guarded append (refuses a deleted
    # example or job — no late annotation recreates deleted evidence).
    return conn_append_revision(conn, example_id, env, parent_revision_id)


def conn_mark_intended(conn, example_id, correct: bool):
    """The ONE intended-writing judgment op (M02-AUDIT-16): the Hub's
    Mark Intended and the menu's legacy "Mark Last Dictation Correct"
    both land here — same provenance
    (``user_explicit_intended_writing``: the user judged the output as
    the writing they intended, never an acoustic/verbatim claim) and the
    same reviewed lifecycle (``annotated``, retained until removed). An
    excluded, expired, quarantined or deleted example refuses the mark
    (``ValueError``) and keeps its state: a mark never silently
    re-includes evidence the user excluded."""
    conn_assert_reviewable(conn, example_id)
    env, rev = _conn_latest(conn, example_id)
    if env is None:
        raise ValueError(f"no revision for example {example_id}")
    outcome = dict(env.get("outcome") or {})
    outcome["correctness"] = "correct" if correct else "incorrect"
    outcome["correctness_provenance"] = "user_explicit_intended_writing"
    env["outcome"] = outcome
    new_rev = _conn_append_revision(conn, example_id, env, rev)
    conn.execute(
        "UPDATE training_examples SET state='annotated',"
        " updated_at_utc=? WHERE example_id=? AND state NOT IN"
        " ('deleted','expired','quarantined_sensitive','excluded')",
        (ids.now_utc_iso(), example_id))
    return new_rev


def _conn_latest(conn, example_id):
    row = conn.execute(
        "SELECT envelope_json, revision_id FROM training_revisions WHERE"
        " example_id=? ORDER BY rowid DESC LIMIT 1",
        (example_id,)).fetchone()
    if row is None:
        return None, None
    return json.loads(row[0]), row[1]


def _conn_job_id(conn, example_id):
    row = conn.execute(
        "SELECT job_id FROM training_examples WHERE example_id=?",
        (example_id,)).fetchone()
    return row[0] if row else None


class TrainingDataService:
    """Reads and annotation writes through the store's writer thread
    (``Store.submit`` — the sanctioned domain-layer entry point)."""

    def __init__(self, store, emit=None):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)

    # ---- listing ----------------------------------------------------------

    def examples(self, text=None, state=None, limit=300) -> list[dict]:
        """Examples newest-first with a completeness summary. ``text``
        matches the example's retained raw/applied artifact text (a
        content query over private data — the Hub runs it locally)."""
        def op(conn):
            rows = conn.execute(
                "SELECT example_id, state, created_at_utc FROM"
                " training_examples WHERE state != 'deleted'"
                " ORDER BY rowid DESC").fetchall()
            out = []
            for ex_id, st, created in rows:
                if limit and len(out) >= limit:
                    break
                if state is not None and st != state:
                    continue
                env, _rev = _conn_latest(conn, ex_id)
                if env is None:
                    continue
                if text:
                    needle = text.lower()
                    raw = self._text_of(conn, env, "source_text")
                    applied = self._text_of(conn, env, "applied_output")
                    if (needle not in (raw or "").lower()
                            and needle not in (applied or "").lower()):
                        continue
                out.append(self._summary_row(conn, ex_id, st, created, env))
            return out
        return self.store.submit(op)

    def _summary_row(self, conn, ex_id, state, created, env):
        job_id = env.get("job_id")
        audio_id = (env.get("artifact_ids") or {}).get("original_audio")
        audio = self._audio_state(conn, audio_id)
        outcome = env.get("outcome") or {}
        annotations = env.get("annotations") or []
        fams = [key for key in ("capture", "audio_preparation",
                                "recognition", "normalization", "context",
                                "cleanup") if env.get(key)]
        return {
            "example_id": ex_id, "job_id": job_id, "state": state,
            "created_at_utc": created,
            "captured_at_utc": env.get("captured_at_utc"),
            "time_quality": env.get("time_quality"),
            "attempt": env.get("attempt"),
            "families": fams,
            "missing_reasons": env.get("missing_reasons") or {},
            "audio": audio,
            "correctness": outcome.get("correctness", "unreviewed"),
            "insertion": outcome.get("insertion"),
            "annotations": [
                {"kind": a.get("kind"),
                 "coverage": a.get("coverage"),
                 "listened_audio": a.get("listened_audio")}
                for a in annotations],
            "pinned": self._is_pinned(conn, job_id),
        }

    def _text_of(self, conn, env, key) -> str | None:
        aid = (env.get("artifact_ids") or {}).get(key)
        if not aid:
            return None
        row = conn.execute(
            "SELECT content_text, purged FROM artifacts WHERE"
            " artifact_id=?", (aid,)).fetchone()
        if row is None or row[1] or row[0] is None:
            return None
        return row[0]

    def _audio_state(self, conn, artifact_id):
        if not artifact_id:
            return {"available": False, "reason": "no_audio_artifact"}
        row = conn.execute(
            "SELECT purged, content_path FROM artifacts WHERE"
            " artifact_id=?", (artifact_id,)).fetchone()
        if row is None:
            return {"available": False, "reason": "artifact_missing"}
        purged, cpath = row
        if purged:
            return {"available": False, "reason": "purged"}
        if not cpath:
            return {"available": False, "reason": "payload_missing"}
        return {"available": True, "artifact_id": artifact_id}

    def _is_pinned(self, conn, job_id) -> bool:
        """True only for USER pins: a never-expiring training lease on a
        non-annotation artifact. Annotation payloads carry their own
        retention leases (reviewed evidence is retained, S29.14) — those
        protect against expiry but are not pins, and reporting them as
        such would let an unpin click revoke annotation retention."""
        if not job_id:
            return False
        marks = ",".join("?" * len(_ANNOTATION_ROLES))
        return conn.execute(
            "SELECT 1 FROM artifact_leases l JOIN artifacts a ON"
            " a.artifact_id = l.artifact_id WHERE a.job_id=? AND"
            " l.holder='training' AND l.revoked_at_utc IS NULL AND"
            f" l.expires_at_utc IS NULL AND a.role NOT IN ({marks})"
            " LIMIT 1", (job_id, *_ANNOTATION_ROLES)).fetchone() is not None

    # ---- detail -----------------------------------------------------------

    def example_detail(self, example_id) -> dict | None:
        """Everything the inspector shows for one example: the envelope's
        stage comparison inputs (resolved from retained artifacts),
        completeness/retention state, annotation history and revision
        chain. Purged stages say so; secure-field context shows its
        omission reason and never any field content (the M06 capture
        guarantee carried through display)."""
        def op(conn):
            row = conn.execute(
                "SELECT state, created_at_utc FROM training_examples"
                " WHERE example_id=?", (example_id,)).fetchone()
            if row is None:
                return None
            state, created = row
            env, _rev = _conn_latest(conn, example_id)
            if env is None:
                return None
            arts = env.get("artifact_ids") or {}
            stages = []
            for key, label in (("source_text", "Source (raw)"),
                               ("normalization", "Normalized"),
                               ("applied_output", "Applied (cleaned)")):
                aid = arts.get(key)
                if not aid:
                    stages.append({"stage": key, "label": label,
                                   "available": False,
                                   "reason": (env.get("missing_reasons")
                                              or {}).get(
                                                  key, "not_captured")})
                    continue
                arow = conn.execute(
                    "SELECT content_text, purged FROM artifacts"
                    " WHERE artifact_id=?", (aid,)).fetchone()
                if arow is None:
                    stages.append({"stage": key, "label": label,
                                   "available": False,
                                   "reason": "artifact_missing"})
                elif arow[1]:
                    stages.append({"stage": key, "label": label,
                                   "available": False, "reason": "purged",
                                   "artifact_id": aid})
                else:
                    stages.append({"stage": key, "label": label,
                                   "available": True, "artifact_id": aid,
                                   "text": arow[0], "purged": False})
            revisions = conn.execute(
                "SELECT revision_id, parent_revision_id, created_at_utc"
                " FROM training_revisions WHERE example_id=? ORDER BY"
                " rowid", (example_id,)).fetchall()
            detail = self._summary_row(conn, example_id, state, created,
                                       env)
            detail.update({
                "stages": stages,
                "annotations": env.get("annotations") or [],
                "outcome": env.get("outcome") or {},
                "capture": env.get("capture") or {},
                "cleanup_path": (env.get("cleanup") or {}).get(
                    "applied_path"),
                "context_block": self._context_display(env),
                "revision_chain": [
                    {"revision_id": r, "parent_revision_id": p,
                     "created_at_utc": c} for r, p, c in revisions],
            })
            return detail
        return self.store.submit(op)

    @staticmethod
    def _context_display(env):
        """Content-free context summary: ids, flags, counts, omission
        reasons. Secure/denied fields were never captured (M06); the
        display can only ever show the recorded omission reason."""
        ctx = env.get("context")
        if ctx is None:
            return {"present": False,
                    "reason": (env.get("missing_reasons") or {}).get(
                        "context", "not_captured")}
        block = {"present": True}
        dest = ctx.get("destination")
        if dest is None:
            block["destination"] = None
            block["destination_reason"] = ctx.get(
                "destination_missing_reason",
                "context_disabled_or_capture_failed")
        else:
            block["destination"] = {
                k: dest.get(k) for k in ("app_bundle", "app_name",
                                         "category", "partial",
                                         "field_classification",
                                         "field_omission_reason",
                                         "retained")
                if k in dest}
            if dest.get("retained") is False:
                block["destination"]["retention_reason"] = dest.get(
                    "retention_reason")
        if ctx.get("hint_set") is None and "hint_set" in ctx:
            block["hint_set"] = None
            block["hint_set_reason"] = ctx.get("hint_set_missing_reason",
                                               "not_captured")
        return block

    # ---- annotations (one atomic op each; AC05) ---------------------------

    def mark_intended(self, example_id, correct: bool) -> str:
        """Whole-example explicit judgment on the intended writing.
        Stored separately from verbatim (S29.6): provenance says
        intention-only. Never flips a verbatim reference."""

        def op(conn):
            return conn_mark_intended(conn, example_id, correct)
        out = self.store.submit(op)
        self.emit("training.annotation_recorded", level="INFO",
                  reason_code="mark_intended",
                  outcome="correct" if correct else "incorrect")
        return out

    def set_verbatim(self, example_id, text: str, *,
                     listened_audio: bool, annotation_id=None) -> str:
        """Audio-reviewed verbatim reference (S29.6 object 1). The exact
        words live in a lease-governed artifact; the envelope entry is
        content-free. Refuses to save without listening (E14) and on a
        non-reviewable example. ``annotation_id`` is the caller's stable
        operation identity: a retry of an op that already committed
        (e.g. after the caller's wait timed out) writes nothing."""
        if not text:
            raise ValueError("verbatim text required")
        if not listened_audio:
            raise ValueError("listen_before_verbatim")

        def op(conn):
            conn_assert_reviewable(conn, example_id)
            env, rev = _conn_latest(conn, example_id)
            if env is None:
                raise ValueError(f"no revision for example {example_id}")
            done = _existing_annotation(env, annotation_id)
            if done is not None:
                return done["annotation_id"], rev
            job_id = _conn_job_id(conn, example_id)
            art_id = _conn_write_text_artifact(
                conn, job_id=job_id, stage="review",
                role="verbatim_reference", text=text,
                parent_artifact_id=(env.get("artifact_ids") or {}).get(
                    "source_text"),
                meta={"example_id": example_id,
                      "origin": "audio_reviewed"})
            _conn_grant_lease(conn, art_id, "training", days=None)
            annotation = {
                "annotation_id": annotation_id or ids.new_id("ann"),
                "kind": "verbatim_reference",
                "coverage": "full",
                "listened_audio": True,
                "artifact_id": art_id,
                "text_sha256": ids.sha256_text(text),
                "created_at_utc": ids.now_utc_iso(),
                "source": "hub_manual",
            }
            # A verbatim reference is its own object: it never flips the
            # intended-writing correctness field.
            env.setdefault("annotations", []).append(annotation)
            new_rev = _conn_append_revision(conn, example_id, env, rev)
            conn.execute(
                "UPDATE training_examples SET state='annotated',"
                " updated_at_utc=? WHERE example_id=? AND state NOT IN"
                " ('deleted','expired','quarantined_sensitive','excluded')",
                (ids.now_utc_iso(), example_id))
            return annotation["annotation_id"], new_rev
        ann_id, _rev = self.store.submit(op)
        self.emit("training.annotation_recorded", level="INFO",
                  reason_code="verbatim_reference")
        return ann_id

    def add_span_correction(self, example_id, stage: str,
                            start: int, end: int,
                            corrected_text: str, *,
                            expected_artifact_id=None,
                            expected_sha256=None,
                            annotation_id=None) -> str:
        """A reviewed local change with explicit coverage (S29.6 object
        3). Offsets are zero-based half-open Unicode code points into
        the stage's exact immutable text (S29.4). Verifies ONLY the span:
        the envelope's whole-example correctness is untouched (AC05) and
        the annotation stays ``coverage: partial`` forever.

        ``expected_artifact_id``/``expected_sha256`` name the exact stage
        text the user reviewed; inside the writer op the example's
        current stage must still be that artifact (and text), else the
        save refuses as stale — offsets are never reinterpreted against
        a different text. A later revision that leaves the reviewed
        artifact in place does not refuse."""
        if stage not in ("source_text", "applied_output"):
            raise ValueError(f"unknown stage {stage!r}")

        def span_op(conn):
            row = conn.execute(
                "SELECT a.content_text FROM training_revisions r JOIN"
                " artifacts a ON a.artifact_id = json_extract("
                "r.envelope_json, '$.artifact_ids." + stage + "')"
                " WHERE r.example_id=? ORDER BY r.rowid DESC LIMIT 1",
                (example_id,)).fetchone()
            if row is None:
                raise ValueError(f"stage {stage} unavailable")
            return row[0] or ""

        try:
            text = self.store.submit(span_op)
        except TimeoutError:
            # Nothing was submitted yet: a definite "not saved", not an
            # unknown outcome.
            raise ValueError("store_busy: the span was not saved — try"
                             " again") from None
        if not (0 <= start < end <= len(text)):
            raise ValueError(
                f"span [{start},{end}) out of range for {len(text)}"
                " code points")

        def op(conn):
            conn_assert_reviewable(conn, example_id)
            env, rev = _conn_latest(conn, example_id)
            if env is None:
                raise ValueError(f"no revision for example {example_id}")
            done = _existing_annotation(env, annotation_id)
            if done is not None:
                return done["annotation_id"], rev
            stage_aid = (env.get("artifact_ids") or {}).get(stage)
            if expected_artifact_id is not None and \
                    stage_aid != expected_artifact_id:
                raise ValueError(
                    "stale_source: the reviewed text changed — reload"
                    " the example before correcting")
            arow = conn.execute(
                "SELECT content_text, purged FROM artifacts WHERE"
                " artifact_id=?", (stage_aid,)).fetchone() \
                if stage_aid else None
            if arow is None or arow[1] or arow[0] is None:
                raise ValueError(
                    f"stage {stage} unavailable — cannot annotate")
            text = arow[0]
            if expected_sha256 is not None and \
                    ids.sha256_text(text) != expected_sha256:
                raise ValueError(
                    "stale_source: the reviewed text changed — reload"
                    " the example before correcting")
            if not (0 <= start < end <= len(text)):
                raise ValueError(
                    f"span [{start},{end}) out of range for {len(text)}"
                    " code points")
            original = text[start:end]
            job_id = _conn_job_id(conn, example_id)
            art_id = _conn_write_text_artifact(
                conn, job_id=job_id, stage="review",
                role="span_correction", kind="span_correction_json",
                text=json.dumps({"stage": stage, "start": start,
                                 "end": end, "original": original,
                                 "corrected": corrected_text},
                                ensure_ascii=False, sort_keys=True),
                parent_artifact_id=stage_aid,
                meta={"example_id": example_id, "stage": stage,
                      "start": start, "end": end})
            _conn_grant_lease(conn, art_id, "training", days=None)
            annotation = {
                "annotation_id": annotation_id or ids.new_id("ann"),
                "kind": "span_correction",
                "stage": stage,
                "span": [start, end],
                "coverage": "partial",
                # Span review need not be audio-reviewed; partial by
                # design — it never upgrades to full gold.
                "listened_audio": None,
                "artifact_id": art_id,
                "created_at_utc": ids.now_utc_iso(),
                "source": "hub_manual",
            }
            # AC05: correcting one token does not verify the whole
            # recording — outcome.correctness stays whatever it was.
            env.setdefault("annotations", []).append(annotation)
            new_rev = _conn_append_revision(conn, example_id, env, rev)
            conn.execute(
                "UPDATE training_examples SET state='annotated',"
                " updated_at_utc=? WHERE example_id=? AND state NOT IN"
                " ('deleted','expired','quarantined_sensitive','excluded')",
                (ids.now_utc_iso(), example_id))
            return annotation["annotation_id"], new_rev
        ann_id, _rev = self.store.submit(op)
        self.emit("training.annotation_recorded", level="INFO",
                  reason_code="span_correction", outcome="partial")
        return ann_id

    # ---- retention controls (S29.2/S29.14) --------------------------------

    def pin(self, example_id, pinned: bool = True) -> bool:
        """A pinned training lease (no expiry) on the example's job
        artifacts — pinned examples are never silently evicted
        (S29.14). Annotation payload artifacts are scoped out in BOTH
        directions: pin never double-leases them (they already carry
        review-retention leases) and unpin never revokes them."""
        def op(conn):
            job_id = _conn_job_id(conn, example_id)
            if job_id is None:
                raise ValueError("example not found")
            now = ids.now_utc_iso()
            marks = ",".join("?" * len(_ANNOTATION_ROLES))
            if pinned:
                for (aid,) in conn.execute(
                        "SELECT artifact_id FROM artifacts WHERE job_id=?"
                        " AND purged=0 AND role NOT IN"
                        f" ({marks})", (job_id, *_ANNOTATION_ROLES)).fetchall():
                    have = conn.execute(
                        "SELECT 1 FROM artifact_leases WHERE"
                        " artifact_id=? AND holder='training' AND"
                        " revoked_at_utc IS NULL AND expires_at_utc IS"
                        " NULL", (aid,)).fetchone()
                    if not have:
                        _conn_grant_lease(conn, aid, "training", days=None)
            else:
                conn.execute(
                    "UPDATE artifact_leases SET revoked_at_utc=? WHERE"
                    " holder='training' AND revoked_at_utc IS NULL AND"
                    " expires_at_utc IS NULL AND artifact_id IN (SELECT"
                    " artifact_id FROM artifacts WHERE job_id=? AND role"
                    f" NOT IN ({marks}))",
                    (now, job_id, *_ANNOTATION_ROLES))
            return True
        out = self.store.submit(op)
        self.emit("training.retention_lease_changed", level="INFO",
                  outcome="pinned" if pinned else "unpinned",
                  reason_code="hub_manual")
        return out

    def exclude(self, example_id, excluded: bool = True) -> str:
        """Exclude from training eligibility, or restore to the review
        state its annotations justify (S29.2). Neither direction touches
        an expired, quarantined or deleted example — those states mean
        something else (retention passed / content flagged / purged):
        excluding one would overwrite the restriction with 'excluded',
        and a later include would then re-eligible it. Both return the
        unchanged state (the caller shows the refusal)."""
        def op(conn):
            row = conn.execute(
                "SELECT state FROM training_examples WHERE example_id=?",
                (example_id,)).fetchone()
            if row is None:
                raise ValueError("example not found")
            current = row[0]
            if current in ("deleted", "expired", "quarantined_sensitive"):
                # delete-everywhere is final (M02-AUDIT-01); expiry and
                # quarantine stay authoritative through both directions.
                return current, False
            if excluded:
                new = "excluded"
            else:
                env, _rev = _conn_latest(conn, example_id)
                new = ("annotated" if (env or {}).get("annotations")
                       else "captured_unreviewed")
            conn.execute(
                "UPDATE training_examples SET state=?, updated_at_utc=?"
                " WHERE example_id=?",
                (new, ids.now_utc_iso(), example_id))
            return new, True
        new, changed = self.store.submit(op)
        if changed and new == "excluded":
            self.emit("training.example_excluded", level="INFO",
                      reason_code="user_action")
        elif changed:
            self.emit("training.example_included", level="INFO",
                      reason_code="user_restore")
        return new

    def delete_everywhere(self, example_id) -> dict:
        """S29.14 delete-everywhere for one example: revokes every lease,
        purges payloads, invalidates downstream eligibility, leaves only
        a content-free tombstone. Deletion overrides immutability."""
        out = self.store.delete_everywhere("example", example_id,
                                           reason="user_request")
        self.emit("training.deleted_everywhere", level="INFO",
                  reason_code="hub_manual")
        return out

    # ---- readiness (S29.15) ----------------------------------------------

    def readiness(self, consent_state: str | None = None) -> dict:
        """Honest readiness counts, separating infrastructure ready /
        dataset coverage / observed model improvement. Nothing is
        fabricated to populate a screen: every number is a store fact,
        and 'observed model improvement' stays explicitly post-V2.

        M13 adds the E19.4-style aggregates (task 6): each with its
        denominator, the outcome classes kept DISTINCT (unreviewed /
        verified positive / verified failure / unobserved / excluded —
        M13-AC05), and no correctness ever inferred from absence of
        edits. Counts are counts: a verified-failure tally is never
        divided into a population error rate (hard-mined samples are
        not population WER, and no mining exists until M14)."""
        def op(conn):
            by_state = {}
            for st, n in conn.execute(
                    "SELECT state, COUNT(*) FROM training_examples GROUP"
                    " BY state").fetchall():
                by_state[st] = n
            # m13-policy-r1 D12: ONE population behind every number. The
            # outcome classes partition live + excluded examples,
            # exclusion first (an excluded example is only 'excluded');
            # deleted/expired/quarantined are storage states, never
            # readiness classes. Completeness, join coverage, reviewed
            # seconds and task eligibility all count live examples only,
            # and a task counts an example only while its exact inputs
            # are retained (reasons are counted for the rest).
            verbatim = intended = spans = 0
            verified_correct = verified_incorrect = 0
            unreviewed_outcomes = unobserved_outcomes = 0
            excluded_class = 0
            audio_count = 0
            audio_referenced = 0
            audio_seconds = 0.0
            verbatim_seconds = 0.0
            complete_examples = 0
            live_examples = 0
            asr_eligible = cleanup_eligible = 0
            asr_reasons: dict = {}
            cleanup_reasons: dict = {}
            training_bytes = 0
            families = set()
            sessions = set()
            # Readiness counts TRAINABLE examples: quarantined content is
            # retained (a storage state) but never feeds a readiness class
            # or a task (M13 D12, corpus C216).
            live_example_states = TRAINABLE_STATES
            latest = conn.execute(
                "SELECT example_id, envelope_json FROM"
                " training_revisions WHERE rowid IN (SELECT MAX(rowid)"
                " FROM training_revisions GROUP BY example_id)").fetchall()
            state_rows = dict(conn.execute(
                "SELECT example_id, state FROM training_examples"
            ).fetchall())
            job_rows = dict(conn.execute(
                "SELECT example_id, job_id FROM training_examples"
            ).fetchall())

            def retained_text(artifact_id) -> bool:
                if not artifact_id:
                    return False
                row = conn.execute(
                    "SELECT purged FROM artifacts WHERE artifact_id=?",
                    (artifact_id,)).fetchone()
                return row is not None and not row[0]

            def bump(reasons, key):
                reasons[key] = reasons.get(key, 0) + 1

            for _ex_id, payload in latest:
                state = state_rows.get(_ex_id)
                if state == "excluded":
                    excluded_class += 1
                    continue
                if state not in live_example_states:
                    continue
                env = json.loads(payload)
                live_examples += 1
                if env.get("family_id"):
                    families.add(env["family_id"])
                if env.get("session_id"):
                    sessions.add(env["session_id"])
                anns = env.get("annotations") or []
                has_verbatim = any(
                    a.get("kind") == "verbatim_reference"
                    and a.get("listened_audio") for a in anns)
                has_span = any(a.get("kind") == "span_correction"
                               for a in anns)
                if has_verbatim:
                    verbatim += 1
                if has_span:
                    spans += 1
                outcome = env.get("outcome") or {}
                correctness = outcome.get("correctness")
                if correctness == "correct":
                    intended += 1
                    verified_correct += 1
                elif correctness == "incorrect":
                    intended += 1
                    verified_incorrect += 1
                elif outcome.get("observation", {}).get("status") == \
                        "observed":
                    # An observed edit window closed without a label:
                    # an observation, never a verdict (S29.8).
                    unobserved_outcomes += 1
                else:
                    unreviewed_outcomes += 1
                arts = env.get("artifact_ids") or {}
                missing = env.get("missing_reasons") or {}
                audio_id = arts.get("original_audio")
                audio_ok = False
                clip = 0.0
                if audio_id:
                    # Join denominator: every live envelope that NAMES
                    # an audio artifact — resolvable or not — so a
                    # dangling id can actually surface (never a
                    # tautological 100%). An exact join is an unpurged
                    # original_audio row owned by the SAME job; another
                    # job's or another kind's row is not linkage.
                    audio_referenced += 1
                    arow = conn.execute(
                        "SELECT purged, meta_json, job_id, role FROM"
                        " artifacts WHERE artifact_id=?",
                        (audio_id,)).fetchone()
                    owner = env.get("job_id") or job_rows.get(_ex_id)
                    if arow and not arow[0] and arow[2] == owner \
                            and arow[3] == "original_audio":
                        audio_count += 1
                        audio_ok = True
                        try:
                            clip = float(json.loads(arow[1] or "{}").get(
                                "duration_sec") or 0.0)
                        except (ValueError, TypeError):
                            clip = 0.0
                        audio_seconds += clip
                if has_verbatim:
                    if audio_ok:
                        asr_eligible += 1
                        # A verbatim reference covers the whole clip
                        # (coverage "full"); partial span corrections
                        # add no reviewed seconds.
                        verbatim_seconds += clip
                    else:
                        bump(asr_reasons, "audio_not_retained")
                if correctness in ("correct", "incorrect"):
                    if retained_text(arts.get("source_text")):
                        cleanup_eligible += 1
                    else:
                        bump(cleanup_reasons, "source_text_not_retained")
                source_ok = bool(arts.get("source_text")) or \
                    "source_text" in missing
                applied_ok = bool(arts.get("applied_output")) or \
                    "applied_output" in missing
                if audio_ok and source_ok and applied_ok:
                    complete_examples += 1
            for (nbytes,) in conn.execute(
                    "SELECT bytes FROM artifacts WHERE purged=0 AND"
                    " retention_class='training'").fetchall():
                training_bytes += nbytes or 0
            excluded = by_state.get("excluded", 0)
            quarantined = by_state.get("quarantined_sensitive", 0)
            deleted = by_state.get("deleted", 0)
            expired = by_state.get("expired", 0)
            # M14: real split-contamination and export-integrity
            # aggregates (computed inline — a nested service call would
            # deadlock the writer) and the per-example expiry
            # countdowns the M13 note promised.
            split_version = conn.execute(
                "SELECT COALESCE(MAX(assignment_version), 0) FROM"
                " split_assignments").fetchone()[0]
            if split_version:
                spanning = conn.execute(
                    "SELECT COUNT(*) FROM (SELECT family_id FROM"
                    " training_memberships WHERE assignment_version=?"
                    " GROUP BY family_id HAVING COUNT(DISTINCT"
                    " partition) > 1)", (split_version,)).fetchone()[0]
                exposed_frozen = conn.execute(
                    "SELECT COUNT(DISTINCT family_id) FROM"
                    " training_memberships WHERE assignment_version=?"
                    " AND exposed=1 AND partition='frozen_test'",
                    (split_version,)).fetchone()[0]
                split_contamination = {
                    "assignment_version": split_version,
                    "families_spanning_partitions": spanning,
                    "exposed_frozen_families": exposed_frozen,
                    "definition": "families spanning partitions within"
                                  " one version and exposed families"
                                  " still frozen (S29.11)",
                }
            else:
                split_contamination = "not_available_no_assignment"
            export_row = conn.execute(
                "SELECT state, examples_count, excluded_count,"
                " fingerprint, finalized_at_utc FROM export_manifests"
                " ORDER BY rowid DESC LIMIT 1").fetchone()
            if export_row:
                export_integrity = {
                    "last_state": export_row[0],
                    "last_examples": export_row[1],
                    "last_excluded": export_row[2],
                    "last_fingerprint": export_row[3],
                    "finalized_at_utc": export_row[4],
                    "note": "hash/lineage validation of the written"
                            " files runs in the standalone validator"
                            " (scripts/v2/validate_dataset.py)",
                }
            else:
                export_integrity = "not_available_no_export"
            # Nearing expiry (D12): live examples holding a RETAINED,
            # training-held artifact whose protection — the latest
            # unrevoked lease end; any never-expiring lease is a pin —
            # ends inside the future window (now, now + 3 days]. Already
            # expired, purged and pinned artifacts are not "nearing".
            now_t = self.store.now_fn()
            now_iso = ids.now_utc_iso(now_t)
            cutoff_iso = ids.now_utc_iso(now_t + 3 * 86400)
            placeholders = ",".join("?" * len(live_example_states))
            nearing = conn.execute(
                "SELECT COUNT(DISTINCT e.example_id) FROM"
                " training_examples e JOIN artifacts a ON"
                " a.job_id=e.job_id AND a.purged=0 WHERE e.state IN"
                f" ({placeholders}) AND EXISTS (SELECT 1 FROM"
                " artifact_leases l WHERE l.artifact_id=a.artifact_id"
                " AND l.holder='training' AND l.revoked_at_utc IS NULL)"
                " AND NOT EXISTS (SELECT 1 FROM artifact_leases l WHERE"
                " l.artifact_id=a.artifact_id AND l.revoked_at_utc IS"
                " NULL AND l.expires_at_utc IS NULL) AND (SELECT"
                " MAX(l.expires_at_utc) FROM artifact_leases l WHERE"
                " l.artifact_id=a.artifact_id AND l.revoked_at_utc IS"
                " NULL) > ? AND (SELECT MAX(l.expires_at_utc) FROM"
                " artifact_leases l WHERE l.artifact_id=a.artifact_id AND"
                " l.revoked_at_utc IS NULL) <= ?",
                (*live_example_states, now_iso, cutoff_iso)).fetchone()[0]
            # Task eligibility (S29.12's minimum evidence, each with its
            # own definition — reported separately, never merged): a
            # record counts only while its exact inputs are retained;
            # records left out are counted by reason.
            task_keys = conn.execute(
                "SELECT COUNT(DISTINCT task_key) FROM"
                " transform_candidates").fetchone()[0]
            transform_ok = conn.execute(
                "SELECT COUNT(DISTINCT c.task_key) FROM"
                " transform_candidates c JOIN artifacts s ON"
                " s.artifact_id=c.source_artifact_id AND s.purged=0"
                " JOIN artifacts o ON o.artifact_id=c.output_artifact_id"
                " AND o.purged=0").fetchone()[0]
            judged = conn.execute(
                "SELECT COUNT(DISTINCT task_key) FROM"
                " preference_observations WHERE judgment IN"
                " ('prefer_a','prefer_b','tie','neither')").fetchone()[0]
            pairs_ok = conn.execute(
                "SELECT COUNT(DISTINCT p.task_key) FROM"
                " preference_observations p JOIN transform_candidates a"
                " ON a.candidate_id=p.candidate_id AND"
                " a.task_key=p.task_key JOIN transform_candidates b ON"
                " b.candidate_id=p.candidate_b_id AND"
                " b.task_key=p.task_key JOIN artifacts sa ON"
                " sa.artifact_id=a.source_artifact_id AND sa.purged=0"
                " JOIN artifacts oa ON oa.artifact_id=a.output_artifact_id"
                " AND oa.purged=0 JOIN artifacts ob ON"
                " ob.artifact_id=b.output_artifact_id AND ob.purged=0"
                " WHERE p.judgment IN"
                " ('prefer_a','prefer_b','tie','neither')").fetchone()[0]
            task_eligibility = {
                "asr_supervised": {
                    "count": asr_eligible,
                    "excluded": asr_reasons,
                    "definition": "live examples with an audio-reviewed"
                                  " verbatim reference and their own"
                                  " retained original audio",
                },
                "cleanup_supervised": {
                    "count": cleanup_eligible,
                    "excluded": cleanup_reasons,
                    "definition": "live examples with an explicit"
                                  " intended-writing mark and their"
                                  " exact stage input retained",
                },
                "transform_supervised": {
                    "count": transform_ok,
                    "excluded": ({"candidate_payload_not_retained":
                                  task_keys - transform_ok}
                                 if task_keys > transform_ok else {}),
                    "definition": "distinct transform tasks with a"
                                  " candidate whose source and output"
                                  " are retained (reviewed targets are"
                                  " M14's review queue)",
                },
                "preference_pairs": {
                    "count": pairs_ok,
                    "excluded": ({"pair_not_same_task_or_not_retained":
                                  judged - pairs_ok}
                                 if judged > pairs_ok else {}),
                    "definition": "distinct tasks with an explicit"
                                  " comparable judgment between two"
                                  " retained candidates of that task",
                },
            }
            return {
                "examples_by_state": by_state,
                # The inspector itself is the functional M09 deliverable
                # (S29.15); the readiness triad stays explicit.
                "infrastructure_ready": True,
                "dataset_coverage": {
                    "retained_audio_examples": audio_count,
                    "retained_audio_seconds": round(audio_seconds, 1),
                    "verbatim_reviewed_examples": verbatim,
                    "intended_writing_marked": intended,
                    "span_annotations": spans,
                    "unreviewed_outcomes": unreviewed_outcomes,
                    "explicitly_correct": verified_correct,
                },
                # M13-AC05: the five outcome classes stay distinct —
                # counts only, never rates over a population.
                "outcome_balance": {
                    "unreviewed": unreviewed_outcomes,
                    "verified_positive": verified_correct,
                    "verified_failure": verified_incorrect,
                    "unobserved": unobserved_outcomes,
                    "excluded": excluded_class,
                    "population": live_examples + excluded_class,
                    "partition": "live and excluded examples; an"
                                 " excluded example is only excluded"
                                 " (exclusion first) — the classes add"
                                 " up to the population",
                    "note": "counts, not rates — no population error"
                            " rate is derivable without a sampling"
                            " design (S29.9)",
                },
                "readiness_definition_revision": "m13-r1",
                "readiness_metrics": {
                    "capture_completeness": {
                        "complete": complete_examples,
                        "denominator": live_examples,
                        "definition": "live (non-excluded/deleted/"
                                      "expired) examples whose required"
                                      " families are present or carry an"
                                      " explicit missing reason",
                    },
                    "exact_audio_join_coverage": {
                        "joined": audio_count,
                        "denominator": audio_referenced,
                        "definition": "live envelopes naming an"
                                      " original_audio id whose artifact"
                                      " row resolves unpurged, as"
                                      " original_audio of the same job —"
                                      " a dangling, foreign or wrong-kind"
                                      " id lowers this",
                    },
                    "verbatim_reference_coverage": {
                        "examples": asr_eligible,
                        "references_without_audio": verbatim - asr_eligible,
                        "denominator": audio_count,
                        "reviewed_seconds": round(verbatim_seconds, 1),
                        "retained_seconds": round(audio_seconds, 1),
                        "seconds_definition": "audio-reviewed verbatim"
                                              " references cover their"
                                              " whole retained clip;"
                                              " span corrections are"
                                              " text offsets with no"
                                              " audio alignment (S29.5)"
                                              " and add no reviewed"
                                              " seconds",
                    },
                    "task_eligibility": task_eligibility,
                    "split_contamination": split_contamination,
                    "export_integrity": export_integrity,
                    "diversity": {
                        "unique_families": len(families),
                        "unique_sessions": len(sessions),
                        "scope": "single-speaker personalization"
                                 " (S29.11)",
                    },
                    "retention_health": {
                        "storage_bytes": training_bytes,
                        "retained_audio_examples": audio_count,
                        "nearing_expiry": nearing,
                        "nearing_expiry_note": "live examples with a"
                                               " training lease expiring"
                                               " within 3 days",
                        "excluded": excluded,
                        "quarantined": quarantined,
                        "deleted": deleted,
                        "expired": expired,
                    },
                    "not_available": {
                        "comparator_coverage":
                            "not_available_until_m15",
                        "population_wer": "no_references_no_population"
                                          "_claims",
                    },
                },
                "observed_model_improvement": None,
                "observed_model_improvement_reason": "post_v2_training_only",
                "storage_bytes": training_bytes,
                "consent_state": consent_state,
            }
        return self.store.submit(op)
