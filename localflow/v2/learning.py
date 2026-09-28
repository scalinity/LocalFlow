"""Correction learning (V2 M14, Spec S22, S29.7–S29.9, contract
learning.md).

A LearningCandidate is one observed user correction offered back as a
scoped suggestion. Two producers (Spec S22):

- **Explicit "teach correction"** — the user states the corrected text
  for a dictated job; evidence_status ``explicit_intent_review``. The
  correction is compared against the exact final text the user saw (its
  artifact id and hash travel with the action) inside the same writer
  op that mints the candidate (m14-policy-r1 D13).
- **Reliable post-insertion observation** — the M08 bounded window's
  ``owned_range_edited`` rows (certified surfaces only; the window
  already guarantees target-bound attribution; its before/after
  artifacts must be that job's own observation artifacts) and the M12
  note-family edits joined through ``note_evidence_links``, attributed
  region by region (D14); evidence_status
  ``reliable_target_observation``. Intentional rewriting fails the
  classifier's reliability gate and never becomes a candidate.

Approval composes with the M05 approved-dictionary controls — it does
NOT bypass them: the check (candidate pending, evidence live), the plan
against the authoritative dictionary (M05's canonical identity), the M05
mutation and the candidate's approved mark happen in ONE writer op
(D12), with the exact vocabulary delta recorded so undo reverses only
that — disabling an entry the approval created while it is exactly as
approval left it, removing an alias it added while that alias is still
there, returning an alias it approved to unapproved — and refuses
rather than overwrite a later user edit. From then on the rule lives
under the same scope-precedence, masking, pin/disable and history rules
as every hand-added term. Unapproved, rejected and stale candidates
never touch pipeline output (M14-AC01): the normalize engine only ever
sees approved vocabulary entries, exactly as in M05.

Adverse counterexamples run inside the same approval op (E13): each
phrase is checked through the M05 sandbox over the effective
post-approval dictionary in the rule's own scope — a phrase the rule
would rewrite blocks the approval with the flip shown. No phrase means
"untested", never "safe" (D06); phrases and flips live in a
lease-governed artifact, the candidate row keeps only counts and ids.

Rejected candidates persist forever as suppression: the same alias →
canonical pair (alias lower-cased, canonical under M05's case identity)
observed again is recorded as ``suppressed`` — a rejected suggestion
never reappears (S11, D05).
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import time

from . import ids
from .curation import classify
from .curation import evidence as ev
from .store import (TRAINABLE_STATES, Store, conn_job_deleted,
                    grant_lease_row, insert_text_artifact_row)

CANDIDATE_STATUSES = ("pending", "approved", "rejected", "suppressed",
                      "dismissed", "stale")

_SOURCES = ("explicit_teach", "edit_observation", "note_revision")

# Example states whose observations may mint candidates.
_MINABLE_STATES = TRAINABLE_STATES

# ScopeContext field for each vocabulary scope kind (the counterexample
# sandbox filters for the rule's own scope).
_SCOPE_FIELDS = {"app": "app_bundle", "site": "site_origin",
                 "workspace": "workspace", "profile": "profile"}


class LearningService:
    """Candidate mining, suggestion review and approval composition over
    the single-writer store (one writer op per action)."""

    def __init__(self, store: Store, emit=None, vocabulary=None):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)
        self.vocabulary = vocabulary  # VocabularyStore; approval needs it

    # ---- explicit teaching -------------------------------------------------

    def teach_correction(self, job_id: str, corrected_text: str, *,
                         expected_final_artifact_id: str | None = None,
                         expected_final_sha256: str | None = None,
                         operation_id: str | None = None) -> dict:
        """The explicit user action (S29.2): state the corrected text
        for one dictated job. The minimal changed spans between the
        job's FINAL text — its applied output; a raw transcript is never
        substituted — and the correction become the candidate. With
        ``expected_final_artifact_id``/``expected_final_sha256`` (the
        rendered final the user corrected) a different, purged or
        changed final refuses as ``stale_final``. Read, compare and mint
        are ONE writer op. An unchanged or reliability-failing
        submission is refused with an honest reason — never a
        fabricated correction; a punctuation/spacing-only correction is
        recorded for review with no rule (D13)."""
        corrected = (corrected_text or "").strip()
        if not corrected:
            raise ValueError("corrected_text_required")

        def op(conn):
            try:
                done = ev.receipt_in(conn, operation_id, "teach", job_id)
            except ev.OperationReused as e:
                return {"refused": str(e)}
            if done is not None:
                return done
            if conn_job_deleted(conn, job_id):
                return {"refused": "job_deleted"}
            from .curation.review import stage_texts_for
            row = conn.execute(
                "SELECT example_id, state FROM training_examples WHERE"
                " job_id=? ORDER BY rowid DESC LIMIT 1",
                (job_id,)).fetchone()
            example_id = row[0] if row else None
            if row and row[1] not in _MINABLE_STATES:
                # Excluded, quarantined or expired evidence teaches
                # nothing (the observation producers apply the same
                # rule).
                return {"refused": f"example_{row[1]}"}
            env_row = conn.execute(
                "SELECT envelope_json FROM training_revisions WHERE"
                " example_id=? ORDER BY rowid DESC LIMIT 1",
                (example_id,)).fetchone() if example_id else None
            env = json.loads(env_row[0]) if env_row is not None else None
            job_attempt = (conn.execute(
                "SELECT attempt FROM jobs WHERE job_id=?",
                (job_id,)).fetchone() or (None,))[0]
            superseded = env is not None and \
                isinstance(env.get("attempt"), int) and \
                isinstance(job_attempt, int) and \
                env["attempt"] != job_attempt
            if superseded:
                # A retry ran without collection: the example describes
                # an earlier attempt, not the final History shows
                # (xm-policy-r1 D06). The current attempt's own text is
                # taught, bound to no example.
                env = None
                example_id = None
            if env is not None:
                final_aid = (env.get("artifact_ids")
                             or {}).get("applied_output")
            else:
                # No training example (collection off): the job's own
                # History artifacts are the text the user saw — of the
                # current attempt when the example was superseded.
                last = conn.execute(
                    "SELECT artifact_id FROM artifacts WHERE job_id=?"
                    " AND role='applied_output'"
                    + (" AND json_extract(meta_json, '$.attempt') = ?"
                       if superseded else "")
                    + " ORDER BY rowid DESC LIMIT 1",
                    (job_id, job_attempt) if superseded
                    else (job_id,)).fetchone()
                final_aid = last[0] if last else None
            final = ev.qualify(conn, final_aid, "applied_output",
                               job_id=job_id)
            if not final["ok"]:
                # The text the reviewer saw is gone: that is a stale
                # render (D13), not a job that never had a final.
                return {"refused": "stale_final"
                        if expected_final_artifact_id is not None
                        else "no_retained_final_text"}
            if expected_final_artifact_id is not None and \
                    final["artifact"]["id"] != expected_final_artifact_id:
                return {"refused": "stale_final"}
            final_text = final["artifact"]["text"]
            if expected_final_sha256 is not None and \
                    ids.sha256_text(final_text) != expected_final_sha256:
                return {"refused": "stale_final"}
            if corrected == final_text.strip():
                return {"refused": "unchanged_output"}
            regions = classify.changed_regions(final_text, corrected)
            if regions and not classify.is_correction_shaped(
                    regions, final_text):
                return {"refused": "not_target_bound_correction"}
            classification = classify.classify_observation(
                final_text, corrected,
                stage_texts=stage_texts_for(
                    conn, example_id, job_id,
                    attempt=job_attempt if superseded else None),
                evidence_status="explicit_intent_review")
            if not regions:
                # Same words, different punctuation/spacing/line breaks:
                # a formatting correction worth reviewing, never a rule.
                regions = classify.format_regions(final_text, corrected)
            out = self._mint_in_op(
                conn, example_id=example_id, job_id=job_id,
                source="explicit_teach", observation_id=None,
                before_aid=final["artifact"]["id"], before_text=final_text,
                after_text=corrected, regions=regions,
                evidence="explicit_intent_review",
                classification=classification)
            return ev.record_receipt_in(conn, operation_id, "teach",
                                        job_id, out)

        got = self.store.submit(op)
        if got.get("refused"):
            raise ValueError(got["refused"])
        self.emit("learning.candidate_created", level="INFO", job_id=job_id,
                  reason_code="explicit_teach", outcome="explicit_teach")
        return got

    # ---- observation mining (on demand/idle — S29.16) ----------------------

    def mine_observation_candidates(self, limit: int = 200) -> int:
        """Scan certified edit observations not yet mined and mint
        candidates for the reliable, correction-shaped ones — the M08
        external windows AND the M12 note-family edits (typed edits
        that touched a dictated region, joined through
        ``note_evidence_links``). Idempotent per observation; a job
        with multiple triggers yields ONE candidate (S29.9 dedup);
        rejected/suppressed pairs stay suppressed. Everything else is
        recorded as examined — mining never re-suggests what it
        already judged. Each observation is examined in its own short
        writer op, so dictation's store writes interleave with a long
        scan instead of queueing behind it (S29.16)."""
        rows = self.store.submit(lambda conn: conn.execute(
            "SELECT o.observation_id, o.job_id, o.before_artifact_id,"
            " o.after_artifact_id FROM insertion_observations o"
            " WHERE o.stop_reason='owned_range_edited' AND o.edited=1"
            " AND o.observation_id NOT IN (SELECT observation_id FROM"
            " learning_candidates WHERE observation_id IS NOT NULL)"
            " ORDER BY o.rowid DESC LIMIT ?", (limit,)).fetchall())

        def mine(conn, obs_id, job_id, before_aid, after_aid):
            if conn.execute(
                    "SELECT 1 FROM learning_candidates WHERE"
                    " observation_id=?", (obs_id,)).fetchone():
                return 0  # a concurrent scan examined it first
            return self._mine_one(conn, obs_id, job_id, before_aid,
                                  after_aid, source="edit_observation")
        n = 0
        for row in rows:
            n += self.store.submit(lambda conn, r=row: mine(conn, *r))
        n += self.store.submit(
            lambda conn: self._mine_note_candidates(conn, limit))
        if n:
            self.emit("learning.candidates_mined", level="INFO",
                      reason_code="observation_scan", detail=f"n={n}")
        return n

    def _mine_note_candidates(self, conn, limit) -> int:
        """M12 (S29.8, D14): typed note edits attributed REGION BY
        REGION. Consecutive revision pairs (append-only chain) give the
        before/after in the note's own unit (whitespace words). A
        changed region wholly inside one dictated span of job J (an
        insertion strictly inside it) is J's evidence; a region touching
        no dictated span is the user's own writing and is dropped; a
        region straddling a span boundary is ambiguous and dropped. A
        dictated span that M12's occurrence-safe rebase reports as
        ambiguous (repeated words whose surviving copy cannot be told)
        abstains the whole revision. Only when the attributable regions
        belong to exactly ONE dictation are those regions — and nothing
        else — classified and kept as its evidence; attribution stops
        where it becomes unreliable (S29.8)."""
        from . import notes as notes_mod
        mined_ids = {r[0] for r in conn.execute(
            "SELECT observation_id FROM learning_candidates WHERE"
            " observation_id IS NOT NULL").fetchall()}
        minted = 0
        by_note: dict[str, set] = {}
        for note_id, example_id, job_id in conn.execute(
                "SELECT note_id, example_id, job_id FROM"
                " note_evidence_links WHERE closed_utc IS NULL"
                " ORDER BY rowid DESC").fetchall():
            by_note.setdefault(note_id, set()).add((example_id, job_id))
        for note_id, links in list(by_note.items())[:limit]:
            revs = conn.execute(
                "SELECT revision_id, content_text, spans_json, origin"
                " FROM note_revisions WHERE note_id=? AND purged=0"
                " ORDER BY rowid", (note_id,)).fetchall()
            for prev, cur in zip(revs, revs[1:]):
                if cur[3] != "typed" or cur[0] in mined_ids:
                    continue
                if not prev[2]:
                    continue
                prev_text, cur_text = prev[1] or "", cur[1] or ""
                a, b = prev_text.split(), cur_text.split()
                spans = [s for s in json.loads(prev[2])
                         if len(s) >= 3 and s[2] == "dictated"]
                if not spans or a == b:
                    continue
                # M12's occurrence-safe rebase decides whether each
                # dictated span's words can be told apart after the edit.
                if any(any(e.get("reason") == "ambiguous" for e in
                           notes_mod.rebase_spans(prev_text, [s],
                                                  cur_text)[1])
                       for s in spans):
                    continue
                attributed = _attribute_note_regions(a, b, spans)
                if attributed is None:
                    continue
                span_job, keep = attributed
                if span_job is None:
                    if len(links) != 1:
                        continue  # unrecorded span among several
                    example_id, job_id = next(iter(links))
                else:
                    job_id = span_job
                    example_id = next(
                        (ex for ex, j in links if j == job_id), None)
                example_row = conn.execute(
                    "SELECT example_id FROM training_examples WHERE"
                    " job_id=? ORDER BY rowid DESC LIMIT 1",
                    (job_id,)).fetchone() if job_id else None
                ex_id = example_row[0] if example_row else example_id
                if not job_id and ex_id:
                    job_row = conn.execute(
                        "SELECT job_id FROM training_examples WHERE"
                        " example_id=?", (ex_id,)).fetchone()
                    job_id = job_row[0] if job_row else None
                if not job_id:
                    continue  # no dictation to attribute the edit to
                if conn_job_deleted(conn, job_id):
                    # M02 deletion barrier: a deleted dictation's content
                    # is never re-minted into evidence (and one deleted
                    # job must not fail the whole mining pass).
                    continue
                state = conn.execute(
                    "SELECT state FROM training_examples WHERE"
                    " example_id=?", (ex_id,)).fetchone() \
                    if ex_id else None
                if state and state[0] not in _MINABLE_STATES:
                    continue
                before_text = " ".join(a)
                after_text = " ".join(_apply_word_regions(a, b, keep))
                regions = classify.changed_regions(before_text, after_text)
                if not regions:
                    continue
                classification = classify.classify_observation(
                    before_text, after_text,
                    evidence_status="reliable_target_observation")
                if classification["edit_kind"] in ("user_rewrite",
                                                   "changed_intent"):
                    self._insert_row(
                        conn, ex_id, job_id, "note_revision",
                        cur[0], None, None, regions,
                        status="dismissed", classification=classification)
                    mined_ids.add(cur[0])
                    continue
                self._mint_in_op(
                    conn, example_id=ex_id, job_id=job_id,
                    source="note_revision", observation_id=cur[0],
                    before_aid=None, before_text=before_text,
                    after_text=after_text, regions=regions,
                    evidence="reliable_target_observation",
                    classification=classification)
                mined_ids.add(cur[0])
                minted += 1
        return minted

    def _mine_one(self, conn, obs_id, job_id, before_aid, after_aid,
                  source) -> int:
        if conn_job_deleted(conn, job_id):
            # A deleted dictation's observation is never re-minted into
            # evidence (M02 barrier), and nothing new is written for it.
            return 0
        before = ev.qualify(conn, before_aid, "observation_before",
                            job_id=job_id)
        after = ev.qualify(conn, after_aid, "observation_after",
                           job_id=job_id)
        if not (before["ok"] and after["ok"]):
            # Unavailable, foreign or wrong-role observation payloads are
            # never evidence of this job (M14-AUDIT-01); the examination
            # is recorded content-free so it is not repeated.
            reason = before["reason"] if not before["ok"] \
                else after["reason"]
            self._insert_row(conn, None, job_id, source, obs_id,
                             before_aid, after_aid, [],
                             status="stale",
                             classification={"abstained": True,
                                             "abstain_reason": reason})
            return 0
        before, after = before["artifact"]["text"], \
            after["artifact"]["text"]
        regions = classify.changed_regions(before, after)
        example_row = conn.execute(
            "SELECT example_id, state FROM training_examples WHERE"
            " job_id=? ORDER BY rowid DESC LIMIT 1", (job_id,)).fetchone()
        example_id = example_row[0] if example_row else None
        if example_row and example_row[1] not in _MINABLE_STATES:
            # An excluded/quarantined/expired dictation teaches nothing
            # (the note-family producer applies the same rule).
            self._insert_row(conn, example_id, job_id, source, obs_id,
                             before_aid, after_aid, regions,
                             status="dismissed",
                             classification={"abstained": True,
                                             "abstain_reason":
                                                 f"example_{example_row[1]}"})
            return 0
        # Stage attribution needs the retained raw/normalized/applied
        # texts (asr vs cleanup-regression origin — S29.7); without
        # them the axes honestly abstain and no rule is suggested.
        from .curation.review import stage_texts_for
        stage_texts = stage_texts_for(conn, example_id, job_id)
        classification = classify.classify_observation(
            before, after, stage_texts=stage_texts,
            evidence_status="reliable_target_observation")
        if not regions or classification["edit_kind"] in (
                "user_rewrite", "changed_intent"):
            # Not a transcription correction — record the examination
            # (idempotence) without a suggestion. Changed-intent stays a
            # review-visible classification, never an ASR candidate.
            self._insert_row(
                conn, example_id, job_id, source, obs_id, before_aid,
                after_aid, regions, status="dismissed",
                classification=classification)
            return 0
        self._mint_in_op(
            conn, example_id=example_id, job_id=job_id, source=source,
            observation_id=obs_id, before_aid=before_aid,
            before_text=before, after_text=after, regions=regions,
            evidence="reliable_target_observation",
            classification=classification)
        return 1

    def _mint_in_op(self, conn, *, example_id, job_id, source,
                    observation_id, before_aid, before_text, after_text,
                    regions, evidence, classification) -> dict:
        # A RULE suggestion is proposed only when the classifier says
        # the error originated in ASR with a confusable near-miss
        # ("clod"→"Claude"). Shape alone is not enough (a wrong-target
        # "gamma"→"delta" is ambiguous evidence, still reviewable,
        # never a one-click alias — E19.1 negatives), and neither is a
        # recognition-shaped fix to a CLEANUP regression: teaching the
        # alias would mask the cleanup bug instead of reviewing it
        # (S29.7 — classify cleanup regression, don't paper over it).
        suggestion = None
        if classification.get("edit_kind") == "recognition_error" \
                and classification.get("origin_stages") == ["asr"]:
            suggestion = _suggestion_from_regions(regions)
        alias, canonical = (suggestion["alias"], suggestion["canonical"]) \
            if suggestion else (None, None)
        # D05: the pair is compared under M05's rules (alias lower-cased,
        # canonical ASCII-case-insensitive), in every scope.
        suppressed = alias is not None and _pair_rejected(
            conn, alias, canonical, ("rejected", "suppressed"))
        now = ids.now_utc_iso()
        candidate_id = ids.new_id("cand")
        # The observed words live only in this lease-governed payload.
        # A note edit keeps just its changed regions (S22: minimal edit
        # ranges — the rest of the note is the user's own writing). An
        # explicit teach is reviewed evidence, retained until removed;
        # a machine-mined observation follows the unreviewed buffer, so
        # it never pins its job's evidence past the buffer (S29.14).
        payload = {"regions": regions} if source == "note_revision" \
            else {"before": before_text, "after": after_text,
                  "regions": regions}
        payload_artifact = insert_text_artifact_row(
            conn, artifact_id=ids.new_id("art"), job_id=job_id,
            stage="learning", role="candidate_observation",
            text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            kind="learning_json", retention_class="training",
            created_at_utc=now)
        grant_lease_row(
            conn, payload_artifact, "training",
            days=None if source == "explicit_teach"
            else self.store.retention_days["training_buffer"],
            granted_at_epoch=time.time())
        scope_kind, scope_value = _scope_from_context(
            conn, job_id, suggestion)
        conn.execute(
            "INSERT INTO learning_candidates(candidate_id, example_id,"
            " job_id, source, observation_id, before_artifact_id,"
            " after_artifact_id, changed_spans_json, proposed_alias,"
            " proposed_canonical, proposed_scope_kind,"
            " proposed_scope_value, status, classification_json,"
            " created_at_utc, updated_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (candidate_id, example_id, job_id, source, observation_id,
             before_aid, payload_artifact,
             _offsets(regions), alias, canonical,
             scope_kind, scope_value,
             "suppressed" if suppressed else "pending",
             json.dumps(_row_axes(classification), ensure_ascii=False,
                        sort_keys=True), now, now))
        return {"candidate_id": candidate_id, "status":
                "suppressed" if suppressed else "pending",
                "suggestion": suggestion,
                "classification": _row_axes(classification)}

    def _insert_row(self, conn, example_id, job_id, source, observation_id,
                    before_aid, after_aid, regions, status,
                    classification):
        now = ids.now_utc_iso()
        candidate_id = ids.new_id("cand")
        conn.execute(
            "INSERT INTO learning_candidates(candidate_id, example_id,"
            " job_id, source, observation_id, before_artifact_id,"
            " after_artifact_id, changed_spans_json, status,"
            " classification_json, created_at_utc, updated_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (candidate_id, example_id, job_id, source, observation_id,
             before_aid, after_aid,
             _offsets(regions), status,
             json.dumps(_row_axes(classification), ensure_ascii=False,
                        sort_keys=True), now, now))
        return candidate_id

    # ---- reads --------------------------------------------------------------

    def candidates(self, status: str | None = None,
                   limit: int = 300) -> list[dict]:
        def op(conn):
            sql = ("SELECT candidate_id, example_id, job_id, source,"
                   " observation_id, proposed_alias, proposed_canonical,"
                   " proposed_scope_kind, proposed_scope_value, status,"
                   " classification_json, rejection_reason,"
                   " vocabulary_entry_id, counterexample_json,"
                   " created_at_utc FROM learning_candidates")
            args = []
            if status:
                sql += " WHERE status=?"
                args.append(status)
            sql += " ORDER BY rowid DESC LIMIT ?"
            args.append(limit)
            out = []
            for row in conn.execute(sql, args).fetchall():
                out.append({
                    "candidate_id": row[0], "example_id": row[1],
                    "job_id": row[2], "source": row[3],
                    "observation_id": row[4], "alias": row[5],
                    "canonical": row[6], "scope_kind": row[7],
                    "scope_value": row[8], "status": row[9],
                    "classification": json.loads(row[10] or "{}"),
                    "rejection_reason": row[11],
                    "vocabulary_entry_id": row[12],
                    "counterexample_check": json.loads(row[13] or "null"),
                    "created_at_utc": row[14],
                })
            return out
        return self.store.submit(op)

    # ---- decisions ----------------------------------------------------------

    def approve(self, candidate_id: str, *, scope_kind: str | None = None,
                scope_value: str | None = None,
                counterexamples: tuple[str, ...] = (),
                operation_id: str | None = None) -> dict:
        """One-click approval (S22) as ONE writer op (D12): the candidate
        must still be pending with live evidence; adverse
        counterexamples run through the effective post-approval
        dictionary; the rule lands through the M05 store's validated
        operations under M05's canonical identity; the exact delta and
        the approved mark commit together. Returns {entry_id, action,
        flips, counterexample_check} — flips non-empty means the
        approval REFUSED (an alias that would rewrite a counterexample
        is never promoted silently). A repeat of a completed
        ``operation_id`` returns its receipt without a second effect."""
        if self.vocabulary is None:
            raise ValueError("vocabulary_store_required")
        phrases = tuple(p for p in counterexamples if isinstance(p, str)
                        and p.strip())
        vs = self.vocabulary

        def op(conn):
            try:
                done = ev.receipt_in(conn, operation_id, "approve",
                                   candidate_id)
            except ev.OperationReused as e:
                return {"refused": str(e)}
            if done is not None:
                return done
            row = conn.execute(
                "SELECT proposed_alias, proposed_canonical,"
                " proposed_scope_kind, proposed_scope_value, status,"
                " job_id, example_id, after_artifact_id FROM"
                " learning_candidates WHERE candidate_id=?",
                (candidate_id,)).fetchone()
            if row is None:
                return {"refused": "candidate_not_found"}
            (alias, canonical, def_kind, def_value, status, job_id,
             example_id, payload_aid) = row
            if status != "pending":
                return {"refused": f"not_pending:{status}"}
            if not alias or not canonical:
                return {"refused": "no_proposed_rule"}
            if _pair_rejected(conn, alias, canonical):
                return {"refused": "pair_rejected"}
            live = _evidence_live(conn, job_id, example_id, payload_aid)
            if live is not None:
                return {"refused": live}
            kind = scope_kind or def_kind
            value = scope_value if scope_kind else def_value
            if kind != "global" and value:
                from . import vocabulary as vocab_mod
                value = vocab_mod.canonical_scope_value(kind, value)
            else:
                value = None
            check = self._counterexample_check(
                conn, alias, canonical, kind, value, phrases)
            if check["flips"]:
                content_free = self._record_counterexamples(
                    conn, candidate_id, job_id, check)
                return {"blocked": True, "flips": check["flips"],
                        "counterexample_check": content_free}
            plan = self._plan_in(conn, candidate_id, alias, canonical,
                                 kind, value)
            if "refused" in plan:
                return plan
            entry = vs.entry_in(conn, plan["entry_id"])
            delta = {"entry_id": plan["entry_id"], "action": plan["action"],
                     "alias": alias,
                     "revision_after_approval": entry.revision
                     if entry is not None else None,
                     "undo_revision": None}
            now = ids.now_utc_iso()
            conn.execute(
                "INSERT OR REPLACE INTO learning_vocabulary_deltas("
                "candidate_id, delta_json, updated_at_utc) VALUES(?,?,?)",
                (candidate_id, json.dumps(delta, sort_keys=True), now))
            content_free = self._record_counterexamples(
                conn, candidate_id, job_id, check)
            conn.execute(
                "UPDATE learning_candidates SET status='approved',"
                " vocabulary_entry_id=?, vocabulary_action=?,"
                " decided_at_utc=?, counterexample_json=?,"
                " updated_at_utc=? WHERE candidate_id=? AND"
                " status='pending'",
                (plan["entry_id"], plan["action"], now,
                 json.dumps(content_free, sort_keys=True), now,
                 candidate_id))
            return ev.record_receipt_in(
                conn, operation_id, "approve", candidate_id,
                {"entry_id": plan["entry_id"], "action": plan["action"],
                 "flips": [], "counterexample_check": content_free})

        out = self.store.submit(op)
        if out.get("refused"):
            # Raised after the op (an in-op raise surfaces as a
            # RuntimeError — contracts/store.md).
            raise ValueError(out["refused"])
        if out.get("blocked"):
            self.emit("learning.approval_blocked", level="WARNING",
                      reason_code="counterexample_flip",
                      detail=f"n={len(out['flips'])}")
            return {"entry_id": None, "flips": out["flips"],
                    "counterexample_check": out["counterexample_check"]}
        self.emit("learning.candidate_approved", level="INFO",
                  reason_code=out["action"],
                  detail="scope=" + ("scoped" if (scope_kind or "")
                                     not in ("", "global") else "default"))
        return out

    def _plan_in(self, conn, candidate_id, alias, canonical, kind,
                 value) -> dict:
        """Decide and APPLY how the approved alias lands, inside the
        approval op, against the authoritative dictionary: ``created``
        (a new approved entry — or, on re-approval after undo, the same
        learned entry re-enabled while it is exactly as the undo left
        it), ``alias_added`` / ``alias_approved`` (on the user's existing
        active entry for this canonical and scope, M05 identity) or
        ``already_present``. An entry the user disabled or never
        approved is never re-activated by a learned alias
        (``existing_entry_not_active``)."""
        vs = self.vocabulary
        # The plan always starts from this candidate's identity and the
        # requested scope; an earlier approval's entry is reused only
        # while it still holds exactly that identity.
        eid = vs.find_in(conn, canonical, kind, value)
        entry = vs.entry_in(conn, eid) if eid else None
        prior = conn.execute(
            "SELECT delta_json FROM learning_vocabulary_deltas WHERE"
            " candidate_id=?", (candidate_id,)).fetchone()
        if prior is not None and entry is not None:
            d = json.loads(prior[0])
            if d["entry_id"] == entry.entry_id and \
                    d["action"] == "created" and not entry.enabled:
                if d.get("undo_revision") is None or \
                        entry.revision != d["undo_revision"]:
                    return {"refused": "existing_entry_not_active"}
                status, _det, _e = vs.update_entry_in(
                    conn, entry.entry_id, expected_revision=entry.revision,
                    enabled=True)
                if status != "ok":
                    return {"refused": f"vocabulary_{status}"}
                return {"entry_id": entry.entry_id, "action": "created"}
        if entry is None:
            status, eid = vs.add_entry_in(
                conn, canonical, [(alias, True)], scope_kind=kind,
                scope_value=value, origin="user", approved=True,
                entry_id=ids.new_id("vocab"))
            if status != "ok":
                return {"refused": f"vocabulary_{status}"}
            return {"entry_id": eid, "action": "created"}
        if not (entry.enabled and entry.approved):
            # Approving a learned alias never silently re-activates a
            # term the user disabled or has not approved.
            return {"refused": "existing_entry_not_active"}
        present = next((a for a in entry.aliases
                        if a.alias.lower() == alias.lower()), None)
        if present is not None and present.approved:
            return {"entry_id": entry.entry_id, "action": "already_present"}
        kept = [(a.alias, a.approved, a.language) for a in entry.aliases
                if a.alias.lower() != alias.lower()]
        kept.append((present.alias if present else alias, True,
                     present.language if present else None))
        status, _det, _e = vs.update_entry_in(
            conn, entry.entry_id, expected_revision=entry.revision,
            aliases=kept)
        if status != "ok":
            return {"refused": f"vocabulary_{status}"}
        return {"entry_id": entry.entry_id,
                "action": "alias_approved" if present else "alias_added"}

    def _counterexample_check(self, conn, alias, canonical, kind, value,
                              phrases) -> dict:
        """Each adverse phrase through the M05 sandbox over the
        EFFECTIVE post-approval dictionary (every current approved entry
        plus the proposed rule — merged into the user's existing entry
        when one holds this identity), filtered for the rule's own
        scope: would the approved rule rewrite it? No phrase is
        ``untested`` — never evidence of safety (D06)."""
        from . import vocabulary as vocab_mod
        vs = self.vocabulary
        revision = vs.revision_in(conn)
        if not phrases:
            return {"status": "untested", "tested": 0, "flips": [],
                    "snapshot_revision": revision,
                    "scope": [kind, value]}
        entries = [e for e in vs.entries_in(conn)
                   if e.enabled and e.approved]
        eid = vs.find_in(conn, canonical, kind, value)
        existing = next((e for e in entries if e.entry_id == eid), None)
        if existing is not None:
            rule_id = existing.entry_id
            preview = dataclasses.replace(
                existing, aliases=tuple(
                    a for a in existing.aliases
                    if a.alias.lower() != alias.lower())
                + (vocab_mod.Alias(alias=alias, approved=True),))
            active = [e for e in entries if e.entry_id != rule_id]
        else:
            rule_id = "cand-preview"
            preview = vocab_mod.VocabularyEntry(
                entry_id=rule_id, canonical=canonical, language="en",
                aliases=(vocab_mod.Alias(alias=alias, approved=True),),
                scope_kind=kind, scope_value=value, origin="user",
                approved=True, verification="explicit")
            active = list(entries)
        scope_ctx = vocab_mod.ScopeContext(
            **({_SCOPE_FIELDS[kind]: value} if kind in _SCOPE_FIELDS
               else {}))
        snapshot = vocab_mod.VocabularySnapshot(active + [preview],
                                                scope_ctx)
        flips = []
        for phrase in phrases:
            result = vocab_mod.sandbox_phrase(phrase, snapshot)
            for match in result.get("applied") or []:
                if match.get("rule_id") == rule_id and \
                        (match.get("before") or "").lower() == alias.lower():
                    flips.append({"phrase": phrase,
                                  "applied": result.get("output")})
                    break
        return {"status": "flips" if flips else "no_flips",
                "tested": len(phrases), "flips": flips,
                "snapshot_revision": revision, "scope": [kind, value]}

    def _record_counterexamples(self, conn, candidate_id, job_id,
                                check) -> dict:
        """Phrases and flips go into a lease-governed artifact of the
        candidate's job (removed with the job, its expiry or the
        candidate going stale); the row keeps only the content-free
        result (M14-AUDIT-15)."""
        content_free = {k: check[k] for k in ("status", "tested",
                                              "snapshot_revision", "scope")}
        content_free["flips"] = len(check["flips"])
        content_free["artifact_id"] = None
        # An attempt supersedes the previous one: its phrases are purged,
        # so one result per candidate exists and every removal path
        # (job, expiry, stale candidate, note deletion) reaches it.
        prev = conn.execute(
            "SELECT counterexample_json FROM learning_candidates WHERE"
            " candidate_id=?", (candidate_id,)).fetchone()
        try:
            prev_aid = (json.loads(prev[0]) or {}).get("artifact_id") \
                if prev and prev[0] else None
        except (ValueError, AttributeError):
            prev_aid = None
        if prev_aid:
            now = ids.now_utc_iso()
            conn.execute(
                "UPDATE artifact_leases SET revoked_at_utc=? WHERE"
                " artifact_id=? AND revoked_at_utc IS NULL", (now, prev_aid))
            conn.execute(
                "UPDATE artifacts SET content_text=NULL, content_path=NULL,"
                " purged=1 WHERE artifact_id=? AND role="
                "'counterexample_result'", (prev_aid,))
        if check["tested"]:
            aid = insert_text_artifact_row(
                conn, artifact_id=ids.new_id("art"), job_id=job_id,
                stage="learning", role="counterexample_result",
                text=json.dumps({"flips": check["flips"],
                                 "tested": check["tested"]},
                                ensure_ascii=False, sort_keys=True),
                kind="learning_json", retention_class="training",
                meta={"candidate_id": candidate_id},
                created_at_utc=ids.now_utc_iso())
            grant_lease_row(conn, aid, "training",
                            days=self.store.retention_days[
                                "training_buffer"],
                            granted_at_epoch=time.time())
            content_free["artifact_id"] = aid
        conn.execute(
            "UPDATE learning_candidates SET counterexample_json=?,"
            " updated_at_utc=? WHERE candidate_id=?",
            (json.dumps(content_free, sort_keys=True), ids.now_utc_iso(),
             candidate_id))
        return content_free

    def reject(self, candidate_id: str, reason: str = "user_rejected", *,
               operation_id: str | None = None) -> str:
        """Rejection persists forever and suppresses the same
        alias→canonical pair when observed again (S11, D05 — a rejected
        suggestion never reappears). A repeat of a completed
        ``operation_id`` returns its receipt."""
        from .store import safe_reason
        reason = safe_reason(reason)

        def op(conn):
            try:
                done = ev.receipt_in(conn, operation_id, "reject",
                                   candidate_id)
            except ev.OperationReused as e:
                return f"refused:{e}"
            if done is not None:
                return done["outcome"]
            row = conn.execute(
                "SELECT status, proposed_alias, proposed_canonical FROM"
                " learning_candidates WHERE candidate_id=?",
                (candidate_id,)).fetchone()
            if row is None:
                return "refused:candidate_not_found"
            if row[0] != "pending":
                return f"refused:not_pending:{row[0]}"
            now = ids.now_utc_iso()
            conn.execute(
                "UPDATE learning_candidates SET status='rejected',"
                " rejection_reason=?, decided_at_utc=?, updated_at_utc=?"
                " WHERE candidate_id=?", (reason, now, now, candidate_id))
            if row[1] and row[2]:
                # D05: other pending suggestions of the same pair are
                # suppressed with it — a rejected pair is never offered
                # again, whichever dictation proposed it.
                key = _pair_key(row[1], row[2])
                for sid, a, c in conn.execute(
                        "SELECT candidate_id, proposed_alias,"
                        " proposed_canonical FROM learning_candidates"
                        " WHERE status='pending' AND proposed_alias IS NOT"
                        " NULL AND proposed_canonical IS NOT NULL"
                        " AND candidate_id<>?", (candidate_id,)).fetchall():
                    if _pair_key(a, c) == key:
                        conn.execute(
                            "UPDATE learning_candidates SET"
                            " status='suppressed', updated_at_utc=? WHERE"
                            " candidate_id=?", (now, sid))
            ev.record_receipt_in(conn, operation_id, "reject",
                                 candidate_id, {"outcome": "rejected"})
            return "rejected"
        out = self.store.submit(op)
        if out.startswith("refused:"):
            # Raised after the op (an in-op raise surfaces as a
            # RuntimeError — contracts/store.md).
            raise ValueError(out[len("refused:"):])
        self.emit("learning.candidate_rejected", level="INFO",
                  reason_code=reason)
        return out

    def undo_approval(self, candidate_id: str, *,
                      operation_id: str | None = None) -> str:
        """Undo of an approval reverses exactly the recorded delta, in
        ONE writer op against the authoritative entry (D12): an entry it
        created is disabled while it is exactly as approval left it; an
        alias it added is removed while it is still there and approved;
        an alias it approved goes back to unapproved while still
        approved; ``already_present`` changed nothing to reverse. A
        later user edit is never overwritten: the undo refuses with
        ``user_modified_since_approval``. The candidate reverts to
        pending so re-approval is a fresh explicit choice."""
        vs = self.vocabulary

        def op(conn):
            try:
                done = ev.receipt_in(conn, operation_id, "undo", candidate_id)
            except ev.OperationReused as e:
                return {"refused": str(e)}
            if done is not None:
                return done
            row = conn.execute(
                "SELECT vocabulary_entry_id, status, vocabulary_action,"
                " proposed_alias, job_id, example_id, after_artifact_id"
                " FROM learning_candidates WHERE"
                " candidate_id=?", (candidate_id,)).fetchone()
            if row is None:
                return {"refused": "candidate_not_found"}
            entry_id, status, action, alias, job_id, example_id, \
                payload_aid = row
            if status != "approved" or not entry_id:
                return {"refused": f"not_approved:{status}"}
            drow = conn.execute(
                "SELECT delta_json FROM learning_vocabulary_deltas WHERE"
                " candidate_id=?", (candidate_id,)).fetchone()
            delta = json.loads(drow[0]) if drow else {
                "entry_id": entry_id, "action": action or "created",
                "alias": alias, "revision_after_approval": None,
                "undo_revision": None}
            entry = vs.entry_in(conn, delta["entry_id"])
            reversal = _undo_fields(entry, delta)
            if "refused" in reversal:
                return reversal
            if reversal.get("fields"):
                status, _det, after = vs.update_entry_in(
                    conn, entry.entry_id, expected_revision=entry.revision,
                    **reversal["fields"])
                if status != "ok":
                    return {"refused": f"vocabulary_{status}"}
                delta["undo_revision"] = after.revision
            now = ids.now_utc_iso()
            conn.execute(
                "INSERT OR REPLACE INTO learning_vocabulary_deltas("
                "candidate_id, delta_json, updated_at_utc) VALUES(?,?,?)",
                (candidate_id, json.dumps(delta, sort_keys=True), now))
            if _evidence_live(conn, job_id, example_id,
                              payload_aid) is None:
                conn.execute(
                    "UPDATE learning_candidates SET status='pending',"
                    " decided_at_utc=?, updated_at_utc=? WHERE"
                    " candidate_id=?", (now, now, candidate_id))
            else:
                # Its evidence died while the rule lived in the
                # dictionary: nothing returns to review — the candidate
                # goes stale with its terms cleared, as deletion leaves
                # every open candidate.
                conn.execute(
                    "UPDATE learning_candidates SET status='stale',"
                    " proposed_alias=NULL, proposed_canonical=NULL,"
                    " changed_spans_json='[]', decided_at_utc=?,"
                    " updated_at_utc=? WHERE candidate_id=?",
                    (now, now, candidate_id))
            return ev.record_receipt_in(
                conn, operation_id, "undo", candidate_id,
                {"outcome": "undone", "action": delta["action"]})

        out = self.store.submit(op)
        if out.get("refused"):
            raise ValueError(out["refused"])
        self.emit("learning.approval_undone", level="INFO",
                  reason_code=out.get("action") or "created")
        return out["outcome"]


def _undo_fields(entry, delta) -> dict:
    """The M05 field change that reverses exactly ``delta`` on the
    authoritative ``entry`` — or a refusal when the user changed what
    approval did (never an overwrite of a later edit)."""
    action = delta["action"]
    alias = (delta.get("alias") or "").lower()
    if entry is None or action == "already_present":
        return {"fields": None}  # nothing learned remains to reverse
    if action == "created":
        rev = delta.get("revision_after_approval")
        if rev is not None and entry.revision != rev:
            return {"refused": "user_modified_since_approval"}
        if rev is None and (
                [(a.alias.lower(), a.approved) for a in entry.aliases]
                != [(alias, True)] or not entry.enabled):
            return {"refused": "user_modified_since_approval"}
        return {"fields": {"enabled": False}}
    present = next((a for a in entry.aliases
                    if a.alias.lower() == alias), None)
    if present is None or not present.approved:
        return {"refused": "user_modified_since_approval"}
    if action == "alias_added":
        kept = [(a.alias, a.approved, a.language) for a in entry.aliases
                if a.alias.lower() != alias]
    else:  # alias_approved
        kept = [(a.alias, a.approved if a.alias.lower() != alias
                 else False, a.language) for a in entry.aliases]
    return {"fields": {"aliases": kept}}


def _evidence_live(conn, job_id, example_id, payload_aid) -> str | None:
    """None while the candidate's evidence is live (job not deleted,
    example trainable, governed payload retained), else a reason."""
    if conn_job_deleted(conn, job_id):
        return "evidence_deleted"
    if example_id:
        row = conn.execute(
            "SELECT state FROM training_examples WHERE example_id=?",
            (example_id,)).fetchone()
        if row is None or row[0] not in _MINABLE_STATES:
            return f"example_{row[0] if row else 'missing'}"
    if payload_aid:
        q = ev.qualify(conn, payload_aid, "candidate_observation",
                       job_id=job_id)
        if not q["ok"]:
            return "evidence_unavailable"
    return None


def _pair_key(alias, canonical):
    """D05's suppression identity: alias lower-cased, canonical under
    M05's ASCII case identity."""
    from .vocabulary_store import identity_key
    return (alias.lower(), identity_key(canonical, "global", None)[0])


def _pair_rejected(conn, alias, canonical, statuses=("rejected",)) -> bool:
    """Whether a row in ``statuses`` holds this pair under D05's key."""
    key = _pair_key(alias, canonical)
    marks = ",".join("?" * len(statuses))
    return any(_pair_key(a, c) == key for a, c in conn.execute(
        "SELECT proposed_alias, proposed_canonical FROM learning_candidates"
        f" WHERE status IN ({marks}) AND proposed_alias IS NOT NULL"
        " AND proposed_canonical IS NOT NULL", statuses).fetchall())


def _attribute_note_regions(a, b, spans):
    """(job, regions) for a typed revision's changed whitespace-word
    regions (D14), or None when nothing is attributable to exactly one
    dictation. Regions are SequenceMatcher opcodes over the note's own
    words; ``job`` may be None for a span written before spans carried
    their dictation."""
    keep = []
    jobs = set()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        inside, touching = [], []
        for s in spans:
            start, end = int(s[0]), int(s[1])
            job = s[3] if len(s) > 3 else None
            if i1 == i2:  # a pure insertion between words
                if start < i1 < end:
                    inside.append(job)
                if start <= i1 <= end:
                    touching.append(job)
            else:
                if start <= i1 and i2 <= end:
                    inside.append(job)
                if i1 < end and start < i2:
                    touching.append(job)
        if not touching:
            continue  # the user's own writing
        if len(inside) != 1 or len(touching) != 1:
            continue  # straddles a boundary or two dictations
        jobs.add(inside[0])
        keep.append((i1, i2, j1, j2))
    if len(jobs) != 1 or not keep:
        return None
    return next(iter(jobs)), keep


def _apply_word_regions(a, b, keep):
    """``a`` with only the kept opcode regions replaced by ``b``'s words
    (every other change is left out of the evidence)."""
    out = []
    cursor = 0
    for i1, i2, j1, j2 in sorted(keep):
        out.extend(a[cursor:i1])
        out.extend(b[j1:j2])
        cursor = i2
    out.extend(a[cursor:])
    return out


def _offsets(regions: list[dict]) -> str:
    """The row's changed spans: code-point offsets only — the words live
    in the lease-governed payload, so the row outlives nothing."""
    return json.dumps([{"start": r["start"], "end": r["end"]}
                       for r in regions])


def _row_axes(classification: dict) -> dict:
    """The classification as stored on the row: axes without the
    region words (they belong to the payload)."""
    return {k: v for k, v in classification.items() if k != "regions"}


def _suggestion_from_regions(regions: list[dict]) -> dict | None:
    """The proposed rule: exactly one clean recognition-shaped region
    (single- or two-word before/after). Mixed or multi-region edits get
    NO auto-suggested rule — their spans go to review, not to a
    one-click alias (S22: minimal edit ranges, never a general
    keylogger; S29.7: grafts only reviewed spans)."""
    clean = [r for r in regions
             if 1 <= len(r["before_words"]) <= 2
             and 1 <= len(r["after_words"]) <= 2]
    if len(regions) == 1 and len(clean) == 1:
        r = regions[0]
        return {
            "alias": " ".join(r["before_words"]),
            "canonical": " ".join(r["after_words"]),
        }
    return None


def _scope_from_context(conn, job_id, suggestion) -> tuple[str, str | None]:
    """Propose the narrowest scope the observation supports: the job's
    destination app when one was recorded, else global — and a global
    LITERAL misspelling replacement still needs the explicit approval
    choice (S11); the proposal never widens silently."""
    if not suggestion:
        return "global", None
    row = conn.execute(
        "SELECT app_bundle FROM job_targets WHERE job_id=?",
        (job_id,)).fetchone() if job_id else None
    if row and row[0]:
        return "app", row[0]
    return "global", None
