"""Correction learning (V2 M14, Spec S22, S29.7–S29.9, contract
learning.md).

A LearningCandidate is one observed user correction offered back as a
scoped suggestion. Two producers (Spec S22):

- **Explicit "teach correction"** — the user states the corrected text
  for a dictated job; evidence_status ``explicit_intent_review``.
- **Reliable post-insertion observation** — the M08 bounded window's
  ``owned_range_edited`` rows (certified surfaces only; the window
  already guarantees target-bound attribution) and the M12 note-family
  edits joined through ``note_evidence_links``; evidence_status
  ``reliable_target_observation``. Intentional rewriting fails the
  classifier's reliability gate and never becomes a candidate.

Approval composes with the M05 approved-dictionary controls — it does
NOT bypass them: an approval writes through ``VocabularyStore``
(origin ``user``; the candidate row's ``vocabulary_entry_id`` carries
the learning linkage). When the canonical term has no entry in the
chosen scope, approval creates one, approved; when the user's own
active entry already exists there, approval adds (or approves) the
alias on it. ``vocabulary_action`` records which, so undo reverses
exactly that — disabling an entry the approval created, removing an
alias it added — and never touches the rest of a hand-made entry.
From then on the rule lives under the same scope-precedence, masking,
pin/disable and history rules as every hand-added term. Unapproved,
rejected and stale candidates never touch pipeline output (M14-AC01):
the normalize engine only ever sees approved vocabulary entries,
exactly as in M05.

Adverse counterexamples run BEFORE an approval lands (E13): each
counterexample phrase is checked through the frozen snapshot sandbox,
filtered for the rule's own scope — an alias whose approved rule would
flip the counterexample blocks the approval with the flip shown, not a
silent promotion.

Rejected candidates persist forever as suppression: the same
(alias, canonical) pair observed again is recorded as ``suppressed`` —
a rejected suggestion never reappears (S11).
"""

from __future__ import annotations

import json
import time

from . import ids
from .curation import classify
from .store import (TRAINABLE_STATES, Store, grant_lease_row,
                    insert_text_artifact_row)
from .store import conn_artifact_text as _conn_artifact_text

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

    def teach_correction(self, job_id: str, corrected_text: str) -> dict:
        """The explicit user action (S29.2): state the corrected text
        for one dictated job. The minimal changed spans between the
        job's FINAL text and the correction become the candidate; an
        unchanged or reliability-failing submission is refused with an
        honest reason — never a fabricated correction."""
        corrected = (corrected_text or "").strip()
        if not corrected:
            raise ValueError("corrected_text_required")

        def read(conn):
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
            env = json.loads(env_row[0]) if env_row else None
            arts = (env or {}).get("artifact_ids") or {}
            final_aid = arts.get("applied_output") or arts.get(
                "source_text")
            if env is None:
                # No training example (collection off): the job's own
                # History artifacts are the text the user saw.
                job_row = conn.execute(
                    "SELECT artifact_id FROM artifacts WHERE job_id=?"
                    " AND role IN ('applied_output','raw_transcript')"
                    " AND purged=0 ORDER BY role='applied_output' DESC,"
                    " rowid DESC LIMIT 1", (job_id,)).fetchone()
                final_aid = job_row[0] if job_row else None
            final_text = _conn_artifact_text(conn, final_aid)
            return {"example_id": example_id, "final_aid": final_aid,
                    "final_text": final_text,
                    "stage_texts": stage_texts_for(conn, example_id,
                                                   job_id)}

        got = self.store.submit(read)
        if got.get("refused"):
            raise ValueError(got["refused"])
        example_id, final_aid, final_text, stage_texts = (
            got["example_id"], got["final_aid"], got["final_text"],
            got["stage_texts"])
        if final_text is None:
            raise ValueError("no_retained_final_text")
        regions = classify.changed_regions(final_text, corrected)
        if not regions:
            raise ValueError("unchanged_output")
        if not classify.is_correction_shaped(regions, final_text):
            raise ValueError("not_target_bound_correction")
        classification = classify.classify_observation(
            final_text, corrected, stage_texts=stage_texts,
            evidence_status="explicit_intent_review")
        return self._mint(
            example_id=example_id, job_id=job_id, source="explicit_teach",
            observation_id=None, before_aid=final_aid,
            before_text=final_text, after_text=corrected, regions=regions,
            evidence="explicit_intent_review",
            classification=classification)

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
        """M12 (S29.8): typed note edits that touched an attributed
        dictation span are reliable local observations of that
        dictated text. Consecutive revision pairs (append-only chain)
        give the before/after; the changed word range must intersect a
        surviving ``dictated`` span — edits elsewhere in the note are
        the user's own writing, never evidence about the dictation.
        Spans record word ranges, not which dictation they came from,
        so a note holding more than one linked dictation cannot
        attribute an edit to a single job: such notes are skipped
        (attribution stops where it becomes unreliable, S29.8)."""
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
            if len(links) != 1:
                continue
            example_id, job_id = next(iter(links))
            revs = conn.execute(
                "SELECT revision_id, content_text, spans_json, origin"
                " FROM note_revisions WHERE note_id=? AND purged=0"
                " ORDER BY rowid", (note_id,)).fetchall()
            for prev, cur in zip(revs, revs[1:]):
                if cur[3] != "typed" or cur[0] in mined_ids:
                    continue
                if not prev[2]:
                    continue
                prev_words = (prev[1] or "").split()
                cur_words = (cur[1] or "").split()
                regions = classify.changed_regions(
                    " ".join(prev_words), " ".join(cur_words))
                if not regions:
                    continue
                dictated = [tuple(s[:3]) for s in json.loads(prev[2])
                            if len(s) >= 3 and s[2] == "dictated"]
                if not dictated:
                    continue
                # Word-index the changed regions against the span
                # offsets: a region covers word positions; compare by
                # reconstructing the region's word range from the
                # before-text word list.
                hit = False
                before_joined = " ".join(prev_words)
                for region in regions:
                    # Region spans are code-point offsets into the
                    # joined before text; note spans are whitespace-word
                    # indices, so both ends count whitespace words.
                    w1 = len(before_joined[:region["start"]].split())
                    w2 = len(before_joined[:region["end"]].split())
                    for s, e, _origin in dictated:
                        if w1 < e and s < w2:
                            hit = True
                            break
                    if hit:
                        break
                if not hit:
                    continue
                example_row = conn.execute(
                    "SELECT example_id FROM training_examples WHERE"
                    " job_id=? ORDER BY rowid DESC LIMIT 1",
                    (job_id,)).fetchone() if job_id else None
                ex_id = example_row[0] if example_row else example_id
                if not job_id:
                    job_row = conn.execute(
                        "SELECT job_id FROM training_examples WHERE"
                        " example_id=?", (ex_id,)).fetchone()
                    job_id = job_row[0] if job_row else None
                if not job_id:
                    continue  # no dictation to attribute the edit to
                state = conn.execute(
                    "SELECT state FROM training_examples WHERE"
                    " example_id=?", (ex_id,)).fetchone() \
                    if ex_id else None
                if state and state[0] not in _MINABLE_STATES:
                    continue
                before_text = " ".join(prev_words)
                after_text = " ".join(cur_words)
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
        before = _conn_artifact_text(conn, before_aid)
        after = _conn_artifact_text(conn, after_aid)
        if before is None or after is None:
            self._insert_row(conn, None, job_id, source, obs_id,
                             before_aid, after_aid, [],
                             status="stale",
                             classification={"abstained": True,
                                             "abstain_reason":
                                                 "artifacts_unavailable"})
            return 0
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

    def _mint(self, *, example_id, job_id, source, observation_id,
              before_aid, before_text, after_text, regions, evidence,
              classification=None):
        def op(conn):
            axes = classification
            if axes is None:
                axes = classify.classify_observation(
                    before_text, after_text, evidence_status=evidence)
            return self._mint_in_op(
                conn, example_id=example_id, job_id=job_id, source=source,
                observation_id=observation_id, before_aid=before_aid,
                before_text=before_text, after_text=after_text,
                regions=regions, evidence=evidence,
                classification=axes)
        out = self.store.submit(op)
        self.emit("learning.candidate_created", level="INFO", job_id=job_id,
                  reason_code=source, outcome=source)
        return out

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
        suppressed = False
        if alias is not None:
            suppressed = conn.execute(
                "SELECT 1 FROM learning_candidates WHERE proposed_alias=?"
                " AND proposed_canonical=? AND status IN"
                " ('rejected','suppressed') LIMIT 1",
                (alias, canonical)).fetchone() is not None
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
                "classification": classification}

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
                    "counterexamples": json.loads(row[13] or "null"),
                    "created_at_utc": row[14],
                })
            return out
        return self.store.submit(op)

    # ---- decisions ----------------------------------------------------------

    def approve(self, candidate_id: str, *, scope_kind: str | None = None,
                scope_value: str | None = None,
                counterexamples: tuple[str, ...] = ()) -> dict:
        """One-click approval (S22): the rule lands through the M05
        store after adverse counterexamples pass. Returns
        {entry_id, flips:[...]} — flips non-empty means the approval
        REFUSED (an alias that would rewrite a counterexample is never
        promoted silently)."""
        if self.vocabulary is None:
            raise ValueError("vocabulary_store_required")

        def read(conn):
            return conn.execute(
                "SELECT proposed_alias, proposed_canonical,"
                " proposed_scope_kind, proposed_scope_value, status,"
                " vocabulary_entry_id, vocabulary_action FROM"
                " learning_candidates WHERE candidate_id=?",
                (candidate_id,)).fetchone()
        row = self.store.submit(read)
        if row is None:
            raise ValueError("candidate_not_found")
        (alias, canonical, def_kind, def_value, status, prior_entry,
         prior_action) = row
        if status != "pending":
            raise ValueError(f"not_pending:{status}")
        if not alias or not canonical:
            raise ValueError("no_proposed_rule")
        kind = scope_kind or def_kind
        value = scope_value if scope_kind else def_value
        flips = self._counterexample_flips(alias, canonical, kind, value,
                                           counterexamples)
        if flips:
            def refuse(conn):
                conn.execute(
                    "UPDATE learning_candidates SET counterexample_json=?,"
                    " updated_at_utc=? WHERE candidate_id=?",
                    (json.dumps(flips), ids.now_utc_iso(), candidate_id))
            self.store.submit(refuse)
            self.emit("learning.approval_blocked", level="WARNING",
                      reason_code="counterexample_flip",
                      detail=f"n={len(flips)}")
            return {"entry_id": None, "flips": flips}
        entry_id, action = self._plan_rule(
            alias, canonical, kind, value, prior_entry, prior_action)

        # The plan is recorded BEFORE the vocabulary store is touched: a
        # crash between the two leaves the candidate pending with its
        # entry id and action, so a retry completes the same plan and
        # undo can still reverse exactly what was done.
        def plan(conn):
            return conn.execute(
                "UPDATE learning_candidates SET vocabulary_entry_id=?,"
                " vocabulary_action=?, updated_at_utc=? WHERE"
                " candidate_id=? AND status='pending'",
                (entry_id, action, ids.now_utc_iso(),
                 candidate_id)).rowcount
        if not self.store.submit(plan):
            raise ValueError("not_pending")
        self._execute_rule(entry_id, action, alias, canonical, kind,
                           value)

        def mark(conn):
            now = ids.now_utc_iso()
            return conn.execute(
                "UPDATE learning_candidates SET status='approved',"
                " decided_at_utc=?, counterexample_json=?,"
                " updated_at_utc=? WHERE candidate_id=? AND"
                " status='pending'",
                (now, json.dumps(flips), now, candidate_id)).rowcount
        if not self.store.submit(mark):
            raise ValueError("not_pending")
        self.emit("learning.candidate_approved", level="INFO",
                  reason_code=action,
                  detail=f"scope={kind}:{value or '-'}")
        return {"entry_id": entry_id, "flips": [], "action": action}

    def _plan_rule(self, alias, canonical, kind, value, prior_entry,
                   prior_action) -> tuple[str, str]:
        """Decide how the approved alias lands and say what will change:
        ``created`` (a new approved entry, its id minted here),
        ``alias_added`` / ``alias_approved`` (on the user's existing
        active entry for this canonical and scope) or
        ``already_present``. A candidate that already carries a plan —
        a re-approval after undo, or a retry after an interrupted
        approval — keeps it."""
        vs = self.vocabulary
        if prior_entry and prior_action in (None, "created"):
            return prior_entry, "created"
        if prior_entry and prior_action in ("alias_added",
                                            "alias_approved") \
                and vs.entry(prior_entry) is not None:
            return prior_entry, prior_action
        existing = next(
            (e for e in vs.entries()
             if e.canonical.lower() == canonical.lower()
             and e.scope_kind == kind
             and (e.scope_value or None) == (value or None)), None)
        if existing is None:
            return ids.new_id("vocab"), "created"
        if not (existing.enabled and existing.approved):
            # Approving a learned alias never silently re-activates a
            # term the user disabled or has not approved.
            raise ValueError("existing_entry_not_active")
        present = next((a for a in existing.aliases
                        if a.alias.lower() == alias.lower()), None)
        if present is not None and present.approved:
            return existing.entry_id, "already_present"
        return existing.entry_id, ("alias_approved" if present
                                   else "alias_added")

    def _execute_rule(self, entry_id, action, alias, canonical, kind,
                      value):
        """Apply a plan through the vocabulary store — idempotent, so a
        retried approval converges on the same entry."""
        vs = self.vocabulary
        entry = vs.entry(entry_id)
        if action == "created":
            if entry is None:
                vs.add_entry(canonical, [(alias, True)], scope_kind=kind,
                             scope_value=value, origin="user",
                             approved=True, entry_id=entry_id)
            else:
                vs.update_entry(entry_id, enabled=True,
                                aliases=_with_alias(entry, alias))
        elif action in ("alias_added", "alias_approved"):
            if entry is None or not (entry.enabled and entry.approved):
                raise ValueError("existing_entry_not_active")
            vs.update_entry(entry_id, aliases=_with_alias(entry, alias))

    def _counterexample_flips(self, alias, canonical, kind, value,
                              counterexamples) -> list[dict]:
        """Each adverse phrase through the frozen sandbox: would the
        approved rule rewrite it? A flip blocks approval (E13). The
        snapshot is filtered for the rule's own scope — an app-scoped
        rule is tested where it would actually fire."""
        if not alias or not canonical or not counterexamples:
            return []
        from . import vocabulary as vocab_mod
        entry = vocab_mod.VocabularyEntry(
            entry_id="cand-preview", canonical=canonical, language="en",
            aliases=(vocab_mod.Alias(alias=alias, approved=True),),
            scope_kind=kind, scope_value=value, origin="user",
            approved=True, verification="explicit")
        scope_ctx = vocab_mod.ScopeContext(
            **({_SCOPE_FIELDS[kind]: value} if kind in _SCOPE_FIELDS
               else {}))
        snapshot = vocab_mod.VocabularySnapshot([entry], scope_ctx)
        flips = []
        for phrase in counterexamples:
            result = vocab_mod.sandbox_phrase(phrase, snapshot)
            for match in result.get("applied") or []:
                if match.get("rule_id") == entry.entry_id:
                    flips.append({"phrase": phrase,
                                  "applied": match.get("after")})
        return flips

    def reject(self, candidate_id: str, reason: str = "user_rejected") -> str:
        """Rejection persists forever and suppresses the same
        alias→canonical pair when observed again (S11 — a rejected
        suggestion never reappears)."""

        def op(conn):
            row = conn.execute(
                "SELECT status FROM learning_candidates WHERE"
                " candidate_id=?", (candidate_id,)).fetchone()
            if row is None:
                return "refused:candidate_not_found"
            if row[0] != "pending":
                return f"refused:not_pending:{row[0]}"
            now = ids.now_utc_iso()
            conn.execute(
                "UPDATE learning_candidates SET status='rejected',"
                " rejection_reason=?, decided_at_utc=?, updated_at_utc=?"
                " WHERE candidate_id=?", (reason, now, now, candidate_id))
            return "rejected"
        out = self.store.submit(op)
        if out.startswith("refused:"):
            # Raised after the op (an in-op raise surfaces as a
            # RuntimeError — contracts/store.md).
            raise ValueError(out[len("refused:"):])
        self.emit("learning.candidate_rejected", level="INFO",
                  reason_code=reason)
        return out

    def undo_approval(self, candidate_id: str) -> str:
        """Undo of an approval reverses exactly what the approval did,
        through the vocabulary store (versioned history survives): an
        entry it created is disabled, an alias it added is removed, an
        alias it approved goes back to unapproved; a user's own entry
        is otherwise untouched. The candidate reverts to pending so
        re-approval is a fresh explicit choice."""
        def read(conn):
            return conn.execute(
                "SELECT vocabulary_entry_id, status, vocabulary_action,"
                " proposed_alias FROM learning_candidates WHERE"
                " candidate_id=?", (candidate_id,)).fetchone()
        row = self.store.submit(read)
        if row is None:
            raise ValueError("candidate_not_found")
        entry_id, status, action, alias = row
        if status != "approved" or not entry_id:
            raise ValueError(f"not_approved:{status}")
        entry = self.vocabulary.entry(entry_id)
        if entry is not None:
            if action in (None, "created"):
                self.vocabulary.set_enabled(entry_id, False)
            elif action in ("alias_added", "alias_approved"):
                kept = [(a.alias, a.approved) for a in entry.aliases
                        if a.alias.lower() != alias.lower()]
                if action == "alias_approved":
                    kept.append((alias, False))
                self.vocabulary.update_entry(entry_id, aliases=kept)

        def mark(conn):
            now = ids.now_utc_iso()
            conn.execute(
                "UPDATE learning_candidates SET status='pending',"
                " decided_at_utc=?, updated_at_utc=? WHERE"
                " candidate_id=?", (now, now, candidate_id))
        self.store.submit(mark)
        self.emit("learning.approval_undone", level="INFO",
                  reason_code=action or "created")
        return "undone"


def _with_alias(entry, alias: str) -> list[tuple[str, bool]]:
    """The entry's aliases with ``alias`` present and approved."""
    out = [(a.alias, a.approved) for a in entry.aliases
           if a.alias.lower() != alias.lower()]
    out.append((alias, True))
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
