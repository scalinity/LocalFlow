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
from .store import grant_lease_row, insert_text_artifact_row

EXAMPLE_STATES = ("captured_unreviewed", "review_candidate", "annotated",
                  "ambiguous", "quarantined_sensitive", "excluded",
                  "expired", "deleted")

# Annotation payload artifacts carry their own never-expiring training
# leases (reviewed evidence is retained until explicitly removed,
# S29.14) — they are NOT user pins, and pin/unpin must never revoke
# them. Both operations scope to artifacts outside these roles.
_ANNOTATION_ROLES = ("verbatim_reference", "span_correction")


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
    revision_id = ids.new_id("rev")
    env = dict(env)
    env["revision_id"] = revision_id
    env["parent_revision_id"] = parent_revision_id
    payload = json.dumps(env, ensure_ascii=False, sort_keys=True)
    now = ids.now_utc_iso()
    conn.execute(
        "INSERT INTO training_revisions(revision_id, example_id,"
        " parent_revision_id, created_at_utc, envelope_json,"
        " content_sha256) VALUES(?,?,?,?,?,?)",
        (revision_id, example_id, parent_revision_id, now, payload,
         ids.sha256_text(payload)))
    conn.execute(
        "UPDATE training_examples SET latest_revision_id=?,"
        " updated_at_utc=? WHERE example_id=?",
        (revision_id, now, example_id))
    return revision_id


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
            env, rev = _conn_latest(conn, example_id)
            if env is None:
                raise ValueError(f"no revision for example {example_id}")
            outcome = dict(env.get("outcome") or {})
            outcome["correctness"] = "correct" if correct else "incorrect"
            outcome["correctness_provenance"] = \
                "user_explicit_intended_writing"
            env["outcome"] = outcome
            new_rev = _conn_append_revision(conn, example_id, env, rev)
            conn.execute(
                "UPDATE training_examples SET state='annotated',"
                " updated_at_utc=? WHERE example_id=? AND state NOT IN"
                " ('deleted','expired','quarantined_sensitive')",
                (ids.now_utc_iso(), example_id))
            return new_rev
        out = self.store.submit(op)
        self.emit("training.annotation_recorded", level="INFO",
                  reason_code="mark_intended",
                  outcome="correct" if correct else "incorrect")
        return out

    def set_verbatim(self, example_id, text: str, *,
                     listened_audio: bool) -> str:
        """Audio-reviewed verbatim reference (S29.6 object 1). The exact
        words live in a lease-governed artifact; the envelope entry is
        content-free. Refuses to save without listening (E14)."""
        if not text:
            raise ValueError("verbatim text required")
        if not listened_audio:
            raise ValueError("listen_before_verbatim")

        def op(conn):
            env, rev = _conn_latest(conn, example_id)
            if env is None:
                raise ValueError(f"no revision for example {example_id}")
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
                "annotation_id": ids.new_id("ann"),
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
                " ('deleted','expired','quarantined_sensitive')",
                (ids.now_utc_iso(), example_id))
            return annotation["annotation_id"], new_rev
        ann_id, _rev = self.store.submit(op)
        self.emit("training.annotation_recorded", level="INFO",
                  reason_code="verbatim_reference")
        return ann_id

    def add_span_correction(self, example_id, stage: str,
                            start: int, end: int,
                            corrected_text: str) -> str:
        """A reviewed local change with explicit coverage (S29.6 object
        3). Offsets are zero-based half-open Unicode code points into
        the stage's exact immutable text (S29.4). Verifies ONLY the span:
        the envelope's whole-example correctness is untouched (AC05) and
        the annotation stays ``coverage: partial`` forever."""
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

        text = self.store.submit(span_op)
        if not (0 <= start < end <= len(text)):
            raise ValueError(
                f"span [{start},{end}) out of range for {len(text)}"
                " code points")

        def op(conn):
            env, rev = _conn_latest(conn, example_id)
            if env is None:
                raise ValueError(f"no revision for example {example_id}")
            stage_aid = (env.get("artifact_ids") or {}).get(stage)
            arow = conn.execute(
                "SELECT content_text, purged FROM artifacts WHERE"
                " artifact_id=?", (stage_aid,)).fetchone() \
                if stage_aid else None
            if arow is None or arow[1] or arow[0] is None:
                raise ValueError(
                    f"stage {stage} unavailable — cannot annotate")
            text = arow[0]
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
                "annotation_id": ids.new_id("ann"),
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
                " ('deleted','expired','quarantined_sensitive')",
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
        state its annotations justify (S29.2). Restoring never
        resurrects an expired, quarantined or deleted example — those
        states mean something else (retention passed / content flagged /
        purged) and a plain include click must not silently re-eligible
        purged content."""
        def op(conn):
            row = conn.execute(
                "SELECT state FROM training_examples WHERE example_id=?",
                (example_id,)).fetchone()
            if row is None:
                raise ValueError("example not found")
            current = row[0]
            if excluded:
                new = "excluded"
            elif current in ("deleted", "expired", "quarantined_sensitive"):
                return current  # restore refused: not merely excluded
            else:
                env, _rev = _conn_latest(conn, example_id)
                new = ("annotated" if (env or {}).get("annotations")
                       else "captured_unreviewed")
            conn.execute(
                "UPDATE training_examples SET state=?, updated_at_utc=?"
                " WHERE example_id=?",
                (new, ids.now_utc_iso(), example_id))
            return new
        new = self.store.submit(op)
        if new == "excluded":
            self.emit("training.example_excluded", level="INFO",
                      reason_code="user_action")
        elif new != "excluded":
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
            verbatim = intended = spans = 0
            verified_correct = verified_incorrect = 0
            unreviewed_outcomes = unobserved_outcomes = 0
            audio_count = 0
            audio_referenced = 0
            audio_seconds = 0.0
            complete_examples = 0
            live_examples = 0
            training_bytes = 0
            families = set()
            sessions = set()
            live_example_states = ("captured_unreviewed",
                                   "review_candidate", "annotated",
                                   "ambiguous", "quarantined_sensitive")
            latest = conn.execute(
                "SELECT example_id, envelope_json FROM"
                " training_revisions WHERE rowid IN (SELECT MAX(rowid)"
                " FROM training_revisions GROUP BY example_id)").fetchall()
            state_rows = dict(conn.execute(
                "SELECT example_id, state FROM training_examples"
            ).fetchall())
            for _ex_id, payload in latest:
                env = json.loads(payload)
                if env.get("family_id"):
                    families.add(env["family_id"])
                if env.get("session_id"):
                    sessions.add(env["session_id"])
                if state_rows.get(_ex_id) in live_example_states:
                    live_examples += 1
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
                if audio_id:
                    # Join denominator: every envelope that NAMES an
                    # audio artifact — resolvable or not — so a dangling
                    # id can actually surface (never a tautological
                    # 100%).
                    audio_referenced += 1
                    arow = conn.execute(
                        "SELECT purged, meta_json FROM artifacts"
                        " WHERE artifact_id=?", (audio_id,)).fetchone()
                    if arow and not arow[0]:
                        audio_count += 1
                        audio_ok = True
                        try:
                            audio_seconds += float(
                                json.loads(arow[1] or "{}").get(
                                    "duration_sec") or 0.0)
                        except (ValueError, TypeError):
                            pass
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
            # Task eligibility (S29.12's minimum evidence, each with its
            # own definition — reported separately, never merged).
            task_eligibility = {
                "asr_supervised": {
                    "count": verbatim,
                    "definition": "retained audio + audio-reviewed"
                                  " verbatim reference",
                },
                "cleanup_supervised": {
                    "count": intended,
                    "definition": "exact stage input retained + explicit"
                                  " intended-writing mark",
                },
                "transform_supervised": {
                    "count": conn.execute(
                        "SELECT COUNT(DISTINCT task_key) FROM"
                        " transform_candidates").fetchone()[0],
                    "definition": "distinct transform tasks with retained"
                                  " candidates (reviewed targets are"
                                  " M14's review queue)",
                },
                "preference_pairs": {
                    "count": conn.execute(
                        "SELECT COUNT(DISTINCT task_key) FROM"
                        " preference_observations WHERE judgment IN"
                        " ('prefer_a','prefer_b','tie','neither')"
                    ).fetchone()[0],
                    "definition": "distinct tasks with an explicit"
                                  " comparable judgment",
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
                    "excluded": excluded,
                    "note": "counts, not rates — no population error"
                            " rate is derivable without a sampling"
                            " design (S29.9)",
                },
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
                        "definition": "envelopes naming an original_audio"
                                      " id whose artifact row resolves"
                                      " unpurged — a dangling id lowers"
                                      " this",
                    },
                    "verbatim_reference_coverage": {
                        "examples": verbatim,
                        "denominator": audio_count,
                        "seconds_note": "per-span reviewed seconds are"
                                        " not tracked yet; example-level"
                                        " coverage only",
                    },
                    "task_eligibility": task_eligibility,
                    "diversity": {
                        "unique_families": len(families),
                        "unique_sessions": len(sessions),
                        "scope": "single-speaker personalization"
                                 " (S29.11)",
                    },
                    "retention_health": {
                        "storage_bytes": training_bytes,
                        "retained_audio_examples": audio_count,
                        "nearing_expiry": None,
                        "nearing_expiry_note": "per-example expiry"
                                               " countdowns arrive with"
                                               " the M14 review queues —"
                                               " uncomputed is null,"
                                               " never a fake zero",
                        "excluded": excluded,
                        "quarantined": quarantined,
                        "deleted": deleted,
                        "expired": expired,
                    },
                    "not_available": {
                        "split_contamination": "not_available_until_m14",
                        "comparator_coverage": "not_available_until_m15",
                        "export_integrity": "not_available_until_m14",
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
