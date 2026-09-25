"""Training-evidence capture (Spec S29.1-S29.4, contract training_evidence.md).

Collection is a one-time, persistent, opt-in choice: the store starts with
no consent revision, which reads as disabled, so merely installing or
importing never enables capture. While enabled, ordinary dictations are
captured without per-utterance prompts; while paused or disabled, no
training payload is created at all and dictation is unaffected (M02-AC07).

The collector subscribes to stages the existing pipeline already performs —
it never triggers extra model calls (S29.16). It retains actual stage
inputs (exact rendered prompts, not just hashes), the original float32
audio, raw/proposed/applied text artifacts, and joins them under stable
job/family/example/revision IDs. Fields the current pipeline cannot honestly
supply carry reasons from the controlled vocabulary, never guesses.
"""

import json
import re
import threading

from . import ids

CONSENT_STATES = ("disabled", "enabled", "paused")

# Controlled missing-field vocabulary (contracts/artifacts.md).
R_UNSUPPORTED = "unsupported_by_adapter"
R_NOT_CAPTURED = "not_captured_at_stage"
R_CONSENT = "consent_disabled"
R_DELETED = "source_deleted"
R_UNRELIABLE = "unreliable_target"
R_NOT_APPLICABLE = "not_applicable"

# Envelope value policy for normalization edits (M04): only typed
# numbers and date/time forms ride in the envelope. String-valued
# command classes (skill tokens, paths, emails, domains, identifiers,
# codes, phones, IPs, versions, dotfiles) carry transcript-derived
# strings — those stay in the lease-governed ledger artifact (S29.14
# retention hygiene).
_VALUE_SAFE_CLASSES = frozenset({
    "integer", "anchored_integer", "unit_number", "decimal", "percent",
    "percentage_points", "currency", "time", "date", "port", "dimension",
})


def _envelope_value(edit):
    if edit.cls not in _VALUE_SAFE_CLASSES or edit.value is None:
        return None
    return str(edit.value)

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
]


def scan_secrets(text: str) -> list[str]:
    """Local, deliberately conservative secret detection (S29.14): a hit
    quarantines the example and excludes it from training/export; it never
    logs or copies the secret itself."""
    found = []
    for pat in SECRET_PATTERNS:
        if pat.search(text or ""):
            found.append(pat.pattern.split("\\b")[-1][:24] or "pattern")
    return found


def _ranges_within(ranges, sample_count) -> bool:
    """Decode ranges are half-open original-sample bounds inside the
    retained audio: [[start, end], …] with 0 <= start < end <= count."""
    if ranges is None or sample_count is None:
        return True
    if not isinstance(ranges, list):
        return False
    for r in ranges:
        if not (isinstance(r, (list, tuple)) and len(r) == 2
                and all(isinstance(v, int) and not isinstance(v, bool)
                        for v in r)
                and 0 <= r[0] < r[1] <= sample_count):
            return False
    return True


def runtime_versions() -> dict:
    """Best-effort local runtime manifest; missing packages stay absent."""
    import importlib.metadata as md
    out = {"python": __import__("sys").version.split()[0]}
    for pkg in ("mlx", "mlx-lm", "parakeet-mlx", "transformers", "numpy",
                "sounddevice"):
        try:
            out[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            continue
    return out


class ConsentSnapshot:
    """One coherent collection-consent decision: a state and the id of
    the revision that state came from, read together (M02-AUDIT-06).
    ``point`` records WHERE it was taken — ``ptt_down`` (the capture
    boundary the contract names), ``job_started`` (a caller without a
    capture boundary, e.g. tests/benchmarks) or
    ``retry_original_capture`` (a retry reusing the original capture's
    permission)."""

    __slots__ = ("state", "revision_id", "point")

    def __init__(self, state, revision_id, point):
        self.state = state if state in CONSENT_STATES else "disabled"
        self.revision_id = revision_id if self.state == "enabled" else None
        self.point = point

    @property
    def collecting(self) -> bool:
        return self.state == "enabled" and self.revision_id is not None


class ConsentManager:
    """The four distinct consent states of S29.2 begin with one here:
    collection itself. Enable/pause/disable append auditable revisions.

    Pause semantics (M02 remediation, documented in
    contracts/training_evidence.md): collection consent is a CAPTURE-TIME
    snapshot. The decision in force at push-to-talk DOWN governs that
    capture's evidence; a later enable never retroactively authorizes
    audio that started while collection was off, and a pause/disable
    after capture start does not revoke an already-authorized in-flight
    capture. Delete-everywhere is the separate, immediate barrier."""

    def __init__(self, store, emit):
        self.store = store
        self.emit = emit
        self._lock = threading.Lock()
        self._cached = None

    def state(self) -> str:
        s = self.store.consent_state()
        return s if s in CONSENT_STATES else "disabled"

    def revision_id(self):
        return self.store.current_consent_id()

    def snapshot_now(self, point="job_started") -> ConsentSnapshot:
        """Atomic (state, revision) from ONE store read."""
        state, cid = self.store.consent_snapshot()
        snap = ConsentSnapshot(state, cid, point)
        with self._lock:
            self._cached = (snap.state, cid)
        return snap

    def capture_snapshot(self) -> ConsentSnapshot:
        """Non-blocking snapshot for the push-to-talk-down boundary (main
        thread): this process's consent writes all go through ``set``,
        which updates the cached pair atomically; the first call reads
        the store once."""
        with self._lock:
            cached = self._cached
        if cached is None:
            return self.snapshot_now(point="ptt_down")
        return ConsentSnapshot(cached[0], cached[1], "ptt_down")

    def set(self, new_state: str, note=None) -> str:
        if new_state not in CONSENT_STATES:
            raise ValueError(f"unknown consent state {new_state!r}")
        cid = self.store.append_consent(new_state, note=note)
        # The cache follows the COMMITTED store, never the request: a
        # failed consent write must not leave the capture boundary
        # believing in a revision that does not exist.
        snap = self.snapshot_now(point="consent_set")
        if snap.state != new_state or (
                new_state == "enabled" and snap.revision_id != cid):
            self.emit("training.collection_state", level="ERROR",
                      outcome="not_recorded", reason_code="consent_write_failed")
            return None
        self.emit("training.collection_state", level="INFO",
                  outcome=new_state, reason_code="consent_revision")
        return cid


class CaptureContext:
    """Per-job collector state (worker-thread only in the V1 pipeline)."""

    def __init__(self, job_id, family_id, *, captured_at_utc, timezone,
                 utc_offset_minutes, consent_revision_id, policy,
                 attempt=1, worker_generation=None, time_quality="known"):
        self.job_id = job_id
        self.family_id = family_id
        self.captured_at_utc = captured_at_utc
        # M03-AUDIT-09: a recovered capture keeps ITS capture instant and
        # quality ("unknown" with a null instant when the original was
        # never recorded) — never the retry's clock.
        self.time_quality = time_quality if captured_at_utc else "unknown"
        self.timezone = timezone
        self.utc_offset_minutes = utc_offset_minutes
        self.consent_revision_id = consent_revision_id
        self.consent_point = None  # where the consent snapshot was taken
        self.policy = policy  # pipeline/config provenance snapshot
        self.collecting = policy is not None
        self.attempt = attempt
        self.worker_generation = worker_generation
        # Stage-specific worker generations (M02-AUDIT-09): the ASR and
        # cleanup results may come from different worker generations
        # after a retry; neither is relabeled as the other's.
        self.stage_generations = {}
        self.publish = None  # publish_example acknowledgment
        self.publish_attempted = False
        self.audio_artifact = None
        self.audio_sample_count = None  # samples in the original artifact
        self.audio_write_failed = False  # M03: consent was on but the
        # payload write failed — a different missing reason than consent
        self.capture_meta = {}
        self.decode_ranges = None      # M03: original-sample model-input map
        self.cleanup_path = None       # M03: actual path (never a mislabel)
        self.cleanup_fallback_reason = None
        # M07 (S29.4 cleanup family): the V2 metadata block (prompt
        # version/revision, sampling, termination, window ownership,
        # validation summary, fallback lineage) — content-free — plus
        # the permitted-context payload, retained as a lease-governed
        # artifact (its vocabulary/protected texts are content-bearing).
        self.cleanup_v2 = None
        self.cleanup_context_payload = None
        self.cleanup_context_artifact = None
        # M04 (S29.4 normalization family): typed edits + ledger replay
        self.normalization = None
        self.normalization_missing_reason = None  # M04-AUDIT-16
        self.norm_text_artifact = None
        self.norm_ledger_artifact = None
        # M05 (S30.1/S29.4 context family): the frozen pre-decode hint
        # set — offered/accepted/ignored with omission reasons, stored
        # before recognition so no later correction can relabel it.
        self.context_hints = None
        self.hint_set_artifact = None
        # M06 (S12/S29.4 context family): the bounded destination-
        # context snapshot (pre-decode + optional downstream revision).
        # Transient use and retention are separate: with retention off
        # the payload is never written and the envelope says so.
        self.context_destination = None
        self.context_downstream = None
        self.context_retention_disabled = False
        # M10 (S15/S17/S29.4): the resolved writing profile + the
        # frozen pre-decode developer registries (skill manifests).
        self.profile = None
        self.skill_registry_artifact = None
        # M11 (S16/S29.4 transform family): the dictation transform's
        # content-free block + its lease-governed input/output/prompt
        # artifacts (the transform's source is the cleanup family's
        # applied output — parent chain keeps the lineage), plus the
        # honest gate reason when a requested transform did not run.
        self.transform_block = None
        self.transform_gate_reason = None
        self.transform_artifacts = {}
        self.raw_artifact = None
        self.raw_text = None
        self.applied_artifact = None
        self.applied_text = None
        self.cleanup_observations = []
        self.cleanup_artifacts = {}   # role -> artifact_id
        self._prompt_cache = {}       # sha -> artifact_id (immutable dedupe)
        self.example_id = None
        self.revision_1 = None
        self.secret_hits = []
        self.quarantined = False


class EvidenceCollector:
    """Live hooks around the existing ASR/cleanup pipeline (M02 task 7-8)."""

    def __init__(self, store, emit, consent, pipeline_info,
                 retain_context=True):
        self.store = store
        self.emit = emit
        self.consent = consent
        self.pipeline_info = pipeline_info  # callable -> provenance dict
        # M06 (S12): independent training-context retention — transient
        # context use never implies retaining snapshot payloads.
        self.retain_context = bool(retain_context)
        self._current = None

    # ---- job lifecycle ---------------------------------------------------

    def job_started(self, job_id, family_id, *, captured_at_utc, timezone,
                    utc_offset_minutes, attempt=1, consent_snapshot=None,
                    time_quality="known"):
        """Build the job's evidence context from ONE coherent consent
        decision. The app passes the snapshot it took at push-to-talk
        DOWN (``ConsentManager.capture_snapshot``) — the capture boundary
        ``consent_revision_id`` is defined against — so a later consent
        change never retroactively adds or removes this job's evidence
        (M02-AUDIT-06). Without one, an atomic snapshot is read now.
        Does NOT bind the observation sink — the worker thread does that
        via bind_current, so a newer job starting on the main thread can
        never steal this job's cleaner observations while it is still
        processing."""
        snap = consent_snapshot if consent_snapshot is not None \
            else self.consent.snapshot_now()
        if snap.collecting:
            consent_id = snap.revision_id
            policy = dict(self.pipeline_info() or {})
        else:
            consent_id = None
            policy = None
        ctx = CaptureContext(
            job_id, family_id, captured_at_utc=captured_at_utc,
            timezone=timezone, utc_offset_minutes=utc_offset_minutes,
            consent_revision_id=consent_id, policy=policy, attempt=attempt,
            time_quality=time_quality)
        ctx.consent_point = snap.point
        return ctx

    def retry_snapshot(self, job_id) -> ConsentSnapshot:
        """Consent for re-processing an OLD capture (the recovery retry):
        the original capture's permission, never the current one attached
        retroactively. Collects only when the original capture was
        collected (its example carries the capture-time revision) AND
        collection is enabled now — a retry started while paused or
        disabled creates no new payload."""
        try:
            row = self.store.submit(lambda db: db.execute(
                "SELECT consent_revision_id FROM training_examples WHERE"
                " job_id=? AND consent_revision_id IS NOT NULL AND"
                " state != 'deleted' ORDER BY rowid LIMIT 1",
                (job_id,)).fetchone())
        except Exception:
            row = None
        now = self.consent.capture_snapshot()
        if row and now.collecting:
            return ConsentSnapshot("enabled", row[0],
                                   "retry_original_capture")
        return ConsentSnapshot("disabled", None, "retry_original_capture")

    def note_attempt(self, ctx, attempt, *, stage=None, worker_generation=None):
        """The app's retry transition, propagated to the evidence context
        (M02-AUDIT-09): the envelope's attempt is the attempt whose
        results it records; a stage's worker generation is recorded for
        that stage only."""
        if ctx is None:
            return
        if attempt is not None:
            ctx.attempt = int(attempt)
        if stage and worker_generation is not None:
            ctx.stage_generations[stage] = worker_generation

    def bind_current(self, ctx):
        """Bind the cleaner-observation sink to this job. Called on the
        (single, FIFO) inference worker thread immediately before the job's
        cleanup pass; cleared after the job completes so stray observations
        (e.g. a model-load warmup) attach to nothing."""
        self._current = ctx

    def clear_current(self):
        self._current = None

    def on_audio(self, ctx, samples, sample_rate, recorder_stats):
        """Attach the completed audio buffer before model execution. A
        store/disk failure is recorded on the context (audio_write_failed)
        and swallowed: evidence capture must never fail the dictation, and
        the envelope reports the write failure honestly instead of
        mislabeling it as consent-disabled."""
        if not ctx.collecting:
            return None
        stats = dict(ctx.capture_meta.get("capture") or {})
        stats.update({k: v for k, v in (recorder_stats or {}).items()
                      if v is not None})
        try:
            art = self.store.write_audio_artifact(
                job_id=ctx.job_id, stage="capture", samples=samples,
                sample_rate=sample_rate, role="original_audio",
                retention_class="training",
                meta={"device": stats.get("device"),
                      "overflow_blocks": stats.get("overflow_blocks"),
                      "voiced_pct": stats.get("voiced_pct"),
                      "trailing_silence_sec": stats.get(
                          "trailing_silence_sec")})
        except Exception:
            ctx.audio_write_failed = True
            return None
        ctx.audio_artifact = art
        ctx.audio_sample_count = int(getattr(samples, "size", len(samples)))
        self.store.grant_lease(art, "training",
                               days=self.store.retention_days["training_buffer"])
        self.store.grant_lease(art, "history",
                               days=self.store.retention_days["audio_success"])
        self.store.set_job_audio(ctx.job_id, art)
        return art

    def on_asr_result(self, ctx, raw_text, *, model_id, model_revision,
                      stage_duration_ms, worker_generation=None,
                      decode_ranges=None, capabilities=None,
                      hint_disposition=None):
        if not ctx.collecting:
            return
        ctx.raw_text = raw_text
        ctx.worker_generation = worker_generation
        if worker_generation is not None:
            ctx.stage_generations["asr"] = worker_generation
        ctx.decode_ranges = decode_ranges
        if raw_text is not None:
            # An empty ASR output is a real observation; record it verbatim.
            ctx.raw_artifact = self.store.write_text_artifact(
                job_id=ctx.job_id, stage="asr", role="raw_transcript",
                text=raw_text, retention_class="training")
            self.store.grant_lease(
                ctx.raw_artifact, "training",
                days=self.store.retention_days["training_buffer"])
        from ..stt import Transcriber
        ctx.capture_meta["recognition"] = {
            "model_id": model_id, "model_revision": model_revision,
            "worker_generation": worker_generation,
            "runtime": runtime_versions(),
            "decode": {"chunk_sec": Transcriber.CHUNK_SEC,
                       "overlap_sec": Transcriber.OVERLAP_SEC,
                       "method": "logmel_direct"},
            "decode_ranges": decode_ranges,
            "capabilities": capabilities,
            "hint_disposition": hint_disposition,
            "stage_duration_ms": stage_duration_ms,
        }

    def on_hint_set(self, ctx, hint_set, disposition):
        """M05 (S30.1/S29.4 context family): retain the frozen pre-decode
        hint set as a lease-governed artifact and record the offered/
        accepted/ignored disposition in the envelope. Called BEFORE
        recognition so the stored set is what was actually offered — a
        dictionary corrected after the fact is never rewritten into
        "original hints" (S29.11). A store failure is swallowed."""
        if not ctx.collecting or hint_set is None or ctx.example_id:
            return
        try:
            ctx.hint_set_artifact = self.store.write_text_artifact(
                job_id=ctx.job_id, stage="pre_decode",
                role="hint_set", kind="hint_set_json",
                retention_class="training",
                text=json.dumps(hint_set.to_json(), ensure_ascii=False,
                                sort_keys=True),
                meta={"hint_set_id": hint_set.hint_set_id,
                      "selector_revision": hint_set.selector_revision,
                      "terms": len(hint_set.terms),
                      "omitted": len(hint_set.omitted)})
            self.store.grant_lease(
                ctx.hint_set_artifact, "training",
                days=self.store.retention_days["training_buffer"])
        except Exception as e:
            # The envelope degrades honestly (context stays in
            # missing_reasons), but the degradation must be observable —
            # the app's surrounding guard cannot fire through this
            # swallow, so the event comes from here.
            self.emit("training.capture_failed", level="ERROR",
                      job_id=ctx.job_id, reason_code=type(e).__name__,
                      outcome="hint_set_not_retained")
            return
        ctx.context_hints = {
            "hint_set_id": hint_set.hint_set_id,
            "selector_revision": hint_set.selector_revision,
            "vocabulary_revision": hint_set.vocabulary_revision,
            "offered_terms": len(hint_set.terms),
            "omitted_terms": len(hint_set.omitted),
            "omission_reasons": sorted({o["reason"]
                                        for o in hint_set.omitted}),
            "disposition": disposition,
            "artifact_ids": {"hint_set": ctx.hint_set_artifact},
        }

    def on_context_snapshot(self, ctx, snapshot, *, downstream=None):
        """M06 (S12/S29.4): record the bounded destination-context
        snapshot. The pre-decode call happens BEFORE recognition (with
        the finalize that cut it), so late providers cannot leak into
        the retained pre-decode payload (M06-AC05); a downstream
        revision is stored separately and marked by stage. Retention is
        the independent ``training_retain_context`` choice: when false,
        no payload artifact is written even with collection enabled and
        the envelope records the redaction (replay inputs stay honestly
        incomplete). Store failures are swallowed — evidence must never
        fail the dictation."""
        if not ctx.collecting or snapshot is None or ctx.example_id:
            return
        block = snapshot.to_envelope_block()
        if downstream:
            ctx.context_downstream = block
        else:
            ctx.context_destination = block
        if not self.retain_context:
            ctx.context_retention_disabled = True
            block["retained"] = False
            block["retention_reason"] = "training_context_retention_disabled"
            return
        try:
            art = self.store.write_text_artifact(
                job_id=ctx.job_id,
                stage="downstream_context" if downstream
                else "pre_decode_context",
                role="context_snapshot",
                kind="context_snapshot_json",
                retention_class="training",
                text=json.dumps(snapshot.to_json(), ensure_ascii=False,
                                sort_keys=True),
                meta={"context_snapshot_id": snapshot.context_snapshot_id,
                      "stage": snapshot.stage,
                      "partial": snapshot.partial,
                      "target_snapshot_id":
                          snapshot.target.target_snapshot_id})
            self.store.grant_lease(
                art, "training",
                days=self.store.retention_days["training_buffer"])
        except Exception as e:
            self.emit("training.capture_failed", level="ERROR",
                      job_id=ctx.job_id, reason_code=type(e).__name__,
                      outcome="context_snapshot_not_retained")
            block["retained"] = False
            block["retention_reason"] = "retention_write_failed"
            return
        block["retained"] = True
        block["artifact_id"] = art
        # (the artifact id lives in the envelope's destination block —
        # no duplicate bookkeeping on the context)

    def on_writing_profile(self, ctx, profile, skill_registry=None):
        """M10 (S15/S17/S29.4): retain the resolved writing profile
        (content-free block: mode, source rule id, category, revisions,
        fallback reason) and the frozen pre-decode skill registry as a
        lease-governed artifact — skill names and manifest paths are
        the user's local configuration, not envelope content. Called
        BEFORE recognition so a later rule/skill edit can never
        relabel what this job actually ran under. Store failures are
        swallowed: evidence must never fail the dictation."""
        if not ctx.collecting or profile is None or ctx.example_id:
            return
        block = dict(profile)
        if skill_registry is not None:
            reg = skill_registry.to_json()
            block["skill_registry_revision"] = reg["revision"]
            block["manifest_skills"] = reg["manifest_skills"]
            block["dictionary_skill_aliases"] = reg[
                "dictionary_skill_aliases"]
            block["skill_alias_conflicts"] = len(reg["conflicts"])
            block["stale_workspace"] = reg["stale_workspace"]
            try:
                art = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="pre_decode",
                    role="skill_registry", kind="skill_registry_json",
                    retention_class="training",
                    text=json.dumps(reg, ensure_ascii=False,
                                    sort_keys=True),
                    meta={"revision": reg["revision"],
                          "manifest_skills": reg["manifest_skills"]})
                self.store.grant_lease(
                    art, "training",
                    days=self.store.retention_days["training_buffer"])
                ctx.skill_registry_artifact = art
                block["skill_registry_artifact_id"] = art
            except Exception as e:
                self.emit("training.capture_failed", level="ERROR",
                          job_id=ctx.job_id, reason_code=type(e).__name__,
                          outcome="skill_registry_not_retained")
        ctx.profile = block

    def on_cleaner_observation(self, obs: dict):
        """Sink for TranscriptCleaner.observer — exact model inputs/outputs."""
        ctx = self._current
        if ctx is None or not ctx.collecting:
            return
        ctx.cleanup_observations.append(obs)

    def on_normalization_result(self, ctx, result, source_text=None,
                                policy=None, context=None,
                                policy_source=None):
        """M04 (S29.4): retain the normalized text and the full typed edit
        ledger (accepted AND rejected proposals) as store artifacts, and
        keep the content-free summary for the envelope. The envelope
        carries spans/values/ops/counts — never transcript payloads that
        outlive retention; replay pulls the text from these artifacts.

        A store failure never fails the stage (dictation continues with
        the normalized text), but it is never silent either
        (M04-AUDIT-16): the failing publication step is emitted as a
        content-free ``training.capture_failed`` event, the envelope's
        normalization slot carries the distinct missing reason
        ``retention_write_failed`` (the stage RAN; its evidence was not
        retained — not "not captured"), and no partial artifact
        reference survives into the envelope, so nothing downstream
        treats a half-published ledger as replayable."""
        if not ctx.collecting or result is None or ctx.example_id:
            return
        step = "normalized_text_write"
        try:
            src = source_text if source_text is not None else ""
            if result.text != src:
                ctx.norm_text_artifact = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="normalization",
                    role="normalized_text", text=result.text,
                    retention_class="training",
                    parent_artifact_id=ctx.raw_artifact,
                    meta={"policy_revision": result.policy_revision})
                step = "normalized_text_lease"
                self.store.grant_lease(
                    ctx.norm_text_artifact, "training",
                    days=self.store.retention_days["training_buffer"])
            step = "ledger_write"
            ctx.norm_ledger_artifact = self.store.write_text_artifact(
                job_id=ctx.job_id, stage="normalization",
                role="normalization_ledger",
                text=json.dumps(result.to_json(), ensure_ascii=False,
                                sort_keys=True),
                kind="ledger_json", retention_class="training",
                parent_artifact_id=ctx.raw_artifact,
                meta={"policy_revision": result.policy_revision,
                      "edits": len(result.edits),
                      "rejected": len(result.rejected)})
            step = "ledger_lease"
            self.store.grant_lease(
                ctx.norm_ledger_artifact, "training",
                days=self.store.retention_days["training_buffer"])
        except Exception as e:
            # A normalized-text artifact that was fully published
            # (written AND leased) before the failure stays referenced —
            # it is what cleanup read, so it remains cleanup's parent and
            # the envelope's normalization artifact (review R16). A
            # half-published artifact (write without lease) and the
            # ledger are dropped from the envelope: nothing references
            # evidence that was not completely retained. Everything the
            # job wrote is still governed by the job's retention and
            # delete-everywhere (job-keyed, M02).
            if step not in ("ledger_write", "ledger_lease"):
                ctx.norm_text_artifact = None
            ctx.norm_ledger_artifact = None
            ctx.normalization_missing_reason = "retention_write_failed"
            self.emit("training.capture_failed", level="ERROR",
                      job_id=ctx.job_id, reason_code=type(e).__name__,
                      stage="normalization", detail=step,
                      outcome="normalization_not_retained")
            return
        # Idempotence evaluated at capture time when the policy object is
        # available (S29.4: "idempotence result when evaluated") — the
        # honest bool, including the documented escape corner. The second
        # pass uses the SAME context as the first; a failed evaluation is
        # null-with-reason, never a guessed false.
        idem_reason = "not_evaluated"
        if policy is not None:
            try:
                result.is_idempotent(policy, context)
                idem_reason = None
            except Exception:
                idem_reason = "evaluation_failed"
        # M05: vocabulary provenance — which snapshot revision the job
        # retained (AC03) and which approved rules produced edits (AC04
        # attribution). rule ids are opaque entry ids, not content.
        vocabulary_block = None
        vocab_snapshot = getattr(context, "vocabulary", None) \
            if context is not None else None
        if vocab_snapshot is not None:
            vocabulary_block = {
                "revision": getattr(vocab_snapshot, "revision", None),
                "applied_rule_ids": [
                    e.rule_id for e in result.edits
                    if e.cls == "vocabulary" and e.rule_id],
            }
        # M10: snippet-expansion provenance — which rules expanded and
        # how many generated spans the applied text carries. Generated
        # text is never an acoustic reference (M10-AC05); the counts
        # and opaque ids travel, the content stays in the ledger
        # artifact's spans.
        snippet_rule_ids = sorted({e.rule_id for e in result.edits
                                   if e.cls == "snippet" and e.rule_id})
        snippet_block = None
        if snippet_rule_ids:
            snippet_snapshot = getattr(context, "snippets", None) \
                if context is not None else None
            snippet_block = {
                "registry_revision": getattr(
                    snippet_snapshot, "revision", None)
                if snippet_snapshot is not None else None,
                "expansions": sum(1 for e in result.edits
                                  if e.cls == "snippet"),
                "rule_ids": snippet_rule_ids,
            }
        # Envelope values: typed numbers/dates only. String-valued
        # command classes (emails, paths, skill tokens, codes…) carry
        # transcript-derived text in their value; those strings live in
        # the lease-governed ledger artifact, never in the envelope
        # (retention hygiene, S29.14).
        ctx.normalization = {
            "policy_revision": result.policy_revision,
            "vocabulary": vocabulary_block,
            "snippets": snippet_block,
            "edits_count": len(result.edits),
            "rejected_count": len(result.rejected),
            "protected_count": len(result.protected),
            "number_word_to_digit_count": result.number_word_to_digit_count,
            "idempotent": result.idempotence,
            **({"idempotent_reason": idem_reason}
               if idem_reason else {}),
            # Which snapshot produced the edits: the job's own captured
            # policy, or a clearly identified new snapshot for a job
            # that captured none (a retry of retained audio).
            **({"policy_source": policy_source} if policy_source else {}),
            "class_counts": result.class_counts(),
            # Per-edit typed evidence: ops, values, units and exact
            # source/output spans — the strings live in the ledger
            # artifact, not the envelope (retention hygiene, S29.14).
            "edits": [
                {"cls": e.cls, "op": e.op,
                 "input_span": e.input_span.as_pair(),
                 "output_span": e.output_span.as_pair(),
                 "value": (_envelope_value(e)),
                 "unit": e.unit, "layer": e.layer,
                 "reason": e.reason}
                for e in result.edits
            ],
            "rejected": [
                {"cls": r.cls, "op": r.op, "span": r.span.as_pair(),
                 "reason": r.reason,
                 "unit": r.unit}
                for r in result.rejected
            ],
            "protected": [p.to_json() for p in result.protected],
            "artifact_ids": {
                "normalized_text": ctx.norm_text_artifact,
                "ledger": ctx.norm_ledger_artifact,
            },
        }

    def on_cleanup_result(self, ctx, applied_text, *, path=None,
                          fallback_reason=None, v2=None,
                          cleanup_context=None):
        if not ctx.collecting:
            return
        ctx.applied_text = applied_text
        ctx.cleanup_path = path
        ctx.cleanup_fallback_reason = fallback_reason
        # M07 (S29.4 cleanup family): exact permitted context and the V2
        # metadata ride as lease-governed artifacts / content-free blocks.
        # A store failure is swallowed — evidence must never fail the
        # dictation — and the block simply degrades honestly.
        if cleanup_context is not None:
            ctx.cleanup_context_payload = cleanup_context
            try:
                art = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="cleanup",
                    role="cleanup_context", kind="cleanup_context_json",
                    text=json.dumps(cleanup_context, ensure_ascii=False,
                                    sort_keys=True),
                    retention_class="training",
                    parent_artifact_id=ctx.norm_text_artifact
                    or ctx.raw_artifact)
                self.store.grant_lease(
                    art, "training",
                    days=self.store.retention_days["training_buffer"])
                ctx.cleanup_context_artifact = art
            except Exception:
                ctx.cleanup_context_artifact = None
        ctx.cleanup_v2 = v2
        if applied_text is not None:
            ctx.applied_artifact = self.store.write_text_artifact(
                job_id=ctx.job_id, stage="cleanup", role="applied_output",
                text=applied_text, retention_class="training",
                parent_artifact_id=ctx.raw_artifact,
                meta={"cleanup_path": path,
                      "fallback_reason": fallback_reason})
            self.store.grant_lease(
                ctx.applied_artifact, "training",
                days=self.store.retention_days["training_buffer"])

    def note_transform_gate(self, ctx, reason: str):
        """M11: the honest reason a requested transform did not run
        (auto-apply off, unbound, untargeted, cleanup off, uncertain
        coverage) — rides the envelope's transform slot when no block
        exists (never a silent Clean)."""
        if not ctx.collecting or ctx.example_id:
            return
        if ctx.transform_block is None:
            ctx.transform_gate_reason = reason

    def on_transform_result(self, ctx, result, *, applied: bool):
        """M11 (S16/S29.4 transform family): retain the transform's
        exact input/output/prompt as lease-governed artifacts and fill
        the envelope's content-free ``transform`` block — transform id
        and revision, prompt revision, task key, path, coverage counts.
        The dictation path records no preference (S29.10: an automatic
        application is not a judgment); explicit accept/reject/tie/undo
        observations ride the transforms store's selection path."""
        if not ctx.collecting or ctx.example_id:
            return
        try:
            art_ids = {}
            days = self.store.retention_days["training_buffer"]
            if result.prompt:
                art_ids["prompt"] = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="transform",
                    role="transform_prompt", text=result.prompt,
                    kind="model_input", retention_class="training",
                    parent_artifact_id=ctx.applied_artifact,
                    meta={"transform_id": result.job.transform_id,
                          "prompt_revision": result.job.prompt_revision})
                self.store.grant_lease(art_ids["prompt"], "training",
                                       days=days)
            art_ids["output"] = self.store.write_text_artifact(
                job_id=ctx.job_id, stage="transform",
                role="transform_output", text=result.output,
                retention_class="training",
                parent_artifact_id=ctx.applied_artifact,
                meta={"transform_id": result.job.transform_id,
                      "path": result.path})
            self.store.grant_lease(art_ids["output"], "training",
                                   days=days)
            ctx.transform_artifacts = art_ids
        except Exception:
            ctx.transform_artifacts = {}
        ctx.transform_block = {
            "transform_id": result.job.transform_id,
            "transform_revision": result.job.transform_revision,
            "prompt_revision": result.job.prompt_revision,
            "mode": result.job.mode,
            "task_key": result.job.task_key(),
            "path": result.path,
            "reason": result.reason,
            "applied": bool(applied),
            "output_tokens": result.output_tokens,
            "duration_ms": result.duration_ms,
            "coverage": result.coverage_summary,
            "source_stage": "cleanup_applied_output",
            "artifact_ids": dict(ctx.transform_artifacts),
        }

    def finalize(self, ctx):
        """After cleanup: mint the example and revision 1 with the full
        field-family envelope and honest missing reasons."""
        if not ctx.collecting or ctx.example_id or ctx.publish_attempted:
            return None
        ctx.secret_hits = scan_secrets(ctx.raw_text or "") \
            + scan_secrets(ctx.applied_text or "")
        # Exact cleanup inputs: one text artifact per distinct rendered
        # prompt (immutable dedupe by hash). Decision records carry no
        # prompt of their own and never mint input artifacts; their applied
        # text is referenced by hash only — the envelope must not embed
        # transcript payloads that outlive retention (S29.14).
        cleanup_detail = {"passes": []}
        for obs in ctx.cleanup_observations:
            prompt = obs.get("prompt")
            if not prompt:
                continue  # corrections_applied / cleanup_decision records
            sha = ids.sha256_text(prompt)
            prompt_art = ctx._prompt_cache.get(sha)
            if prompt_art is None:
                prompt_art = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="cleanup",
                    role=f"cleanup_input_{obs.get('kind', 'pass')}",
                    text=prompt, kind="model_input",
                    retention_class="training",
                    meta={"system_prompt_sha256": ids.sha256_text(
                              obs.get("system_prompt") or ""),
                          "kind": obs.get("kind"),
                          "max_tokens": obs.get("max_tokens"),
                          "input_text_sha256": ids.sha256_text(
                              obs.get("input") or "")})
                self.store.grant_lease(
                    prompt_art, "training",
                    days=self.store.retention_days["training_buffer"])
                ctx._prompt_cache[sha] = prompt_art
            proposal_art = None
            if obs.get("output") is not None:
                proposal_art = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="cleanup",
                    role="cleanup_proposal" if obs.get("accepted") is not False
                    else "cleanup_rejected_proposal",
                    text=obs["output"], retention_class="training",
                    parent_artifact_id=prompt_art)
                self.store.grant_lease(
                    proposal_art, "training",
                    days=self.store.retention_days["training_buffer"])
            obs["_proposal_artifact_id"] = proposal_art
            obs["_prompt_artifact_id"] = prompt_art
            cleanup_detail["passes"].append({
                "kind": obs.get("kind"),
                "input_sha256": ids.sha256_text(obs.get("input") or ""),
                "prompt_artifact_id": prompt_art,
                "proposal_artifact_id": proposal_art,
                "accepted": obs.get("accepted"),
                "applied_sha256": (ids.sha256_text(obs["applied"])
                                   if obs.get("applied") is not None else None),
                # M07 remediation (decision schema m07-decisions-2):
                # content-free pass identity, range and termination.
                # Absent keys on older records mean "not captured".
                "pass_id": obs.get("pass_id"),
                "parent_pass_id": obs.get("parent_pass_id"),
                "depth": obs.get("depth"),
                "window_range": obs.get("window_range"),
                "max_tokens": obs.get("max_tokens"),
                "output_tokens": obs.get("output_tokens"),
                "limit_hit": obs.get("limit_hit"),
                "status": obs.get("status"),
            })
        decisions = [o for o in ctx.cleanup_observations
                     if o.get("kind") == "cleanup_decision"]
        decision = decisions[-1] if decisions else None
        if decision is not None:
            cleanup_detail["decision"] = {
                "accepted": decision.get("accepted"),
                "applied_sha256": (
                    ids.sha256_text(decision["applied"])
                    if decision.get("applied") is not None else None),
                "error": decision.get("error"),
            }
            # Every window/retry decision, content-free (the last one
            # above stays for older readers).
            cleanup_detail["decisions"] = [{
                "pass_id": d.get("pass_id"),
                "stage": d.get("stage"),
                "depth": d.get("depth"),
                "window_range": d.get("window_range"),
                "accepted": d.get("accepted"),
                "status": d.get("status"),
                "failed_components": [
                    c["name"] for c in
                    (d.get("validation") or {}).get("components", [])
                    if c.get("kind") == "deterministic"
                    and c.get("status") == "fail"],
                "applied_sha256": (ids.sha256_text(d["applied"])
                                   if d.get("applied") is not None
                                   else None),
            } for d in decisions]
        # The complete decision manifest — every pass, correction
        # proposal and validation report with its findings, and each
        # candidate's provisional/selected/rolled-back status — is
        # content-bearing, so it is a lease-governed artifact referenced
        # from the envelope, never envelope content (S29.14). Prompts and
        # outputs are referenced by their own artifact ids, not copied.
        manifest_art = None
        if any("pass_id" in o for o in ctx.cleanup_observations):
            manifest = {
                "schema": (ctx.cleanup_v2 or {}).get("decision_schema"),
                "records": [
                    {k: v for k, v in o.items()
                     if k not in ("prompt", "system_prompt", "input",
                                  "output")
                     and not k.startswith("_")}
                    | ({"input_sha256": ids.sha256_text(o["input"])}
                       if o.get("input") is not None else {})
                    | ({"prompt_artifact_id": o["_prompt_artifact_id"],
                        "proposal_artifact_id":
                            o.get("_proposal_artifact_id")}
                       if o.get("_prompt_artifact_id") else {})
                    for o in ctx.cleanup_observations],
            }
            try:
                manifest_art = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="cleanup",
                    role="cleanup_decisions", kind="cleanup_decisions_json",
                    text=json.dumps(manifest, ensure_ascii=False,
                                    sort_keys=True, default=str),
                    retention_class="training",
                    parent_artifact_id=ctx.norm_text_artifact
                    or ctx.raw_artifact)
                self.store.grant_lease(
                    manifest_art, "training",
                    days=self.store.retention_days["training_buffer"])
            except Exception:
                manifest_art = None
        # M03-AC04: which path actually produced the applied text — an
        # llm-mode fallback to basic is recorded as basic, never "llm".
        cleanup_detail["applied_path"] = ctx.cleanup_path
        cleanup_detail["fallback_reason"] = ctx.cleanup_fallback_reason
        # M07 (S29.4 cleanup family, EV-19): the V2 block — prompt
        # version/revision, sampling, termination, window source-range
        # ownership (normalized-text coordinates joined to raw through
        # the normalization ledger's input/output spans), validation
        # component outcomes and fallback lineage. Content-free: the
        # permitted-context payload and every prompt/proposal live in
        # lease-governed artifacts. A validator outcome here is a mining
        # signal only — outcome.correctness stays unreviewed and no
        # preference is implied (M07-AC06).
        if ctx.cleanup_v2 is not None:
            v2 = dict(ctx.cleanup_v2)
            v2["context_artifact_id"] = ctx.cleanup_context_artifact
            v2["context_retained"] = ctx.cleanup_context_artifact is not None
            v2["decisions_artifact_id"] = manifest_art
            v2["decisions_retained"] = manifest_art is not None
            payload = ctx.cleanup_context_payload
            if payload is not None:
                v2["context_terms"] = len(
                    payload.get("relevant_vocabulary") or [])
                v2["context_protected_spans"] = len(
                    payload.get("protected_span_texts") or [])
                v2["context_vocabulary_pairs"] = len(
                    payload.get("vocabulary_pairs") or [])
            cleanup_detail["v2"] = v2

        envelope = self._envelope(ctx, cleanup_detail)
        return self._publish(ctx, envelope, "capture_complete")

    def _publish(self, ctx, envelope, reason_code):
        """ONE acknowledged publication op (M02-AUDIT-03/05): the example
        is visible for the first time in its final initial state
        (quarantined when the scanner flagged it), its revision 1 and
        pointer commit together, and uncommitted artifact references are
        reported instead of claimed. Events follow the COMMIT, never the
        enqueue. A publish failure never fails the dictation — it is an
        explicit ``training.capture_failed`` event. A caller timeout is
        not a cancellation: the pre-allocated example id stays on the
        context (``publish`` = None) so a late commit is still joinable,
        and the event says the publication is unacknowledged."""
        if ctx.publish_attempted:
            return ctx.example_id
        ctx.publish_attempted = True
        ctx.quarantined = bool(ctx.secret_hits)
        example_id = ids.new_id("ex")
        envelope["example_id"] = example_id
        try:
            ack = self.store.publish_example(
                job_id=ctx.job_id, family_id=ctx.family_id,
                envelope=envelope,
                consent_revision_id=ctx.consent_revision_id,
                collection_policy="m02_live_capture",
                quarantined=ctx.quarantined, example_id=example_id)
        except TimeoutError:
            ctx.example_id = example_id
            self.emit("training.capture_failed", level="ERROR",
                      job_id=ctx.job_id, reason_code="TimeoutError",
                      outcome="publish_unacknowledged")
            return None
        except Exception as e:
            deleted = "JobDeletedError" in str(e)
            self.emit("training.capture_failed",
                      level="INFO" if deleted else "ERROR",
                      job_id=ctx.job_id,
                      reason_code=("job_deleted" if deleted
                                   else type(e).__name__),
                      outcome="publish_refused" if deleted
                      else "publish_failed")
            return None
        ctx.publish = ack
        ctx.example_id = ack["example_id"]
        ctx.revision_1 = ack["revision_id"]
        if ctx.quarantined:
            self.emit("training.secret_quarantined", level="WARNING",
                      job_id=ctx.job_id, reason_code="suspected_credential",
                      detail=f"patterns={len(ctx.secret_hits)}")
        complete = ack["complete"]
        self.emit("training.revision_saved",
                  level="INFO" if complete else "WARNING",
                  job_id=ctx.job_id, attempt=ctx.attempt,
                  reason_code=(reason_code if complete
                               else "capture_incomplete"),
                  outcome="committed",
                  detail=(None if complete else
                          f"uncommitted={len(ack['uncommitted'])}"),
                  artifact_ids=[
                      envelope["artifact_ids"][k]
                      for k in ("original_audio", "source_text",
                                "applied_output")
                      if envelope["artifact_ids"].get(k)
                      and f"artifact_ids.{k}" not in ack["uncommitted"]])
        return ctx.example_id

    def on_insertion(self, ctx, posted: bool, chars: int):
        """Legacy outcome entry (V1 baseline semantic, pinned by the M02
        suite): ``posted=True`` records the honest posted_unverified with
        outcome_observation not_captured_at_stage; ``posted=False``
        records not_attempted. Real M08 transactions go through
        ``on_insertion_result``."""
        if not ctx.collecting or not ctx.example_id:
            return

        def mutate(envelope):
            envelope.setdefault("artifact_ids", {})
            outcome = dict(envelope.get("outcome") or {})
            # A human judgment recorded meanwhile survives (M02-AUDIT-08).
            outcome.update({
                "insertion": "posted_unverified" if posted
                else "not_attempted",
                "inserted_chars": chars if posted else 0,
            })
            outcome.setdefault("correctness", "unreviewed")
            envelope["outcome"] = outcome
            envelope["missing_reasons"] = dict(
                envelope.get("missing_reasons") or {})
            envelope["missing_reasons"]["outcome_observation"] = \
                R_NOT_CAPTURED
            return envelope
        return self._update_outcome(ctx, mutate)

    def _update_outcome(self, ctx, mutate):
        """Outcome revisions extend the CURRENT latest revision in one
        writer op (read, modify, append, pointer) — an annotation that
        landed meanwhile is kept and the parent is the revision actually
        extended (M02-AUDIT-08). A deleted example refuses the write
        (M02-AUDIT-01). Failures never fail the dictation; they are
        reported."""
        try:
            return self.store.update_latest_revision(ctx.example_id, mutate)
        except Exception as e:
            deleted = "JobDeletedError" in str(e)
            self.emit("training.capture_failed",
                      level="INFO" if deleted else "ERROR",
                      job_id=ctx.job_id,
                      reason_code=("job_deleted" if deleted
                                   else type(e).__name__),
                      outcome="outcome_revision_refused" if deleted
                      else "outcome_revision_failed")
            return None

    def on_insertion_result(self, ctx, result, observation=None):
        """M08 outcome revision (Spec S18/S29.8): the real insertion
        state machine plus the bounded observation's content-free
        summary. Posted/confirmed/unknown stays independent of
        correctness — ``correctness`` is untouched here and no-edit
        intervals never become verified positives (M08-AC06). The
        observation's before/after texts live in lease-governed
        artifacts referenced by id, never in the envelope."""
        if not ctx.collecting or not ctx.example_id:
            return
        block = result.to_envelope_block()
        obs_block = (self._observation_block(observation.get("observer"))
                     if observation is not None else None)

        def mutate(envelope):
            envelope.setdefault("artifact_ids", {})
            outcome = dict(envelope.get("outcome") or {})
            outcome["correctness"] = outcome.get("correctness",
                                                 "unreviewed")
            outcome.update(block)
            missing = dict(envelope.get("missing_reasons") or {})
            if obs_block is not None:
                # An S29.8 window is running on a certified surface: the
                # insert-time block is interim (stop_reason fills in when
                # the window closes — its own revision).
                outcome["observation"] = obs_block
                missing.pop("outcome_observation", None)
            elif result.state == "confirmed":
                # Confirmed but no window (outcome_observation_sec = 0):
                # observation is off by configuration, not unreliable.
                outcome["observation"] = {"status": "observation_disabled"}
                missing["outcome_observation"] = R_NOT_APPLICABLE
            elif result.state == "posted_unverified":
                # An unobserved insert on an uncertified surface: it never
                # proved its AX reads self-consistent (S29.8's
                # outcome_observation_unavailable).
                outcome["observation"] = {
                    "status": "outcome_observation_unavailable"}
                missing["outcome_observation"] = R_UNRELIABLE
            else:
                missing.pop("outcome_observation", None)
            envelope["outcome"] = outcome
            envelope["missing_reasons"] = missing
            return envelope
        return self._update_outcome(ctx, mutate)

    def on_observation_closed(self, ctx, result, observer):
        """The bounded S29.8 window ended: append the observation
        outcome as its own revision (the observation outlives the
        insert transaction by up to the window)."""
        if not ctx.collecting or not ctx.example_id:
            return
        obs_block = self._observation_block(observer)

        def mutate(envelope):
            outcome = dict(envelope.get("outcome") or {})
            outcome["observation"] = obs_block
            missing = dict(envelope.get("missing_reasons") or {})
            if obs_block.get("recorded"):
                missing.pop("outcome_observation", None)
            envelope["outcome"] = outcome
            envelope["missing_reasons"] = missing
            return envelope
        return self._update_outcome(ctx, mutate)

    # ---- M12: the Scratchpad note family (S20/S29.8) --------------------

    _NOTE_STATES_SKIP = ("deleted", "expired", "quarantined_sensitive")
    _NOTE_OBSERVATIONS_MAX = 32

    def on_note_revision(self, event: dict):
        """M12 (S20): one Scratchpad revision observation, appended to
        the affected examples' envelopes — content-free (ids, origins,
        counts; never note text). A revision event is a reliable LOCAL
        observation (S29.8 ``reliable_target_observation``), never an
        ASR example: no new example is minted, no verbatim/correctness
        label is granted, and typed additions are recorded as typed —
        never as dictated speech (M12-AC05). Affected examples: the
        arrival's source job (dictated/transform revisions) plus every
        open ``note_evidence_links`` example (typed edits/restores
        observed against regions that earlier carried their dictation).
        Requires collection consent, like every producer here."""
        try:
            self._on_note_revision(event)
        except Exception as e:
            self.emit("training.note_capture_failed", level="WARNING",
                      reason_code=type(e).__name__)

    def _on_note_revision(self, event: dict):
        if self.consent.state() != "enabled":
            return
        note_id = event.get("note_id")
        if not note_id:
            return
        from . import training_data as td  # the shared writer-op helpers
        # (imported here: training_data reads training at module doc
        # level only — no cycle).

        def op(db):
            targets = {}
            if event.get("source_job_id"):
                row = db.execute(
                    "SELECT example_id, state FROM training_examples"
                    " WHERE job_id=? ORDER BY rowid DESC LIMIT 1",
                    (event["source_job_id"],)).fetchone()
                if row is not None and row[1] not in self._NOTE_STATES_SKIP:
                    targets[row[0]] = row[1]
            stale = []
            for ex_id, state in db.execute(
                    "SELECT e.example_id, e.state FROM note_evidence_links l"
                    " JOIN training_examples e ON e.example_id = l.example_id"
                    " WHERE l.note_id=? AND l.closed_utc IS NULL",
                    (note_id,)).fetchall():
                if state not in self._NOTE_STATES_SKIP:
                    targets[ex_id] = state
                else:
                    stale.append(ex_id)
            now = ids.now_utc_iso()
            # Links whose example was deleted/expired elsewhere close —
            # they must not accumulate as forever-open references.
            for ex_id in stale:
                db.execute(
                    "UPDATE note_evidence_links SET closed_utc=?,"
                    " close_reason='example_unavailable' WHERE note_id=?"
                    " AND example_id=? AND closed_utc IS NULL",
                    (now, note_id, ex_id))
            if not targets:
                return 0
            observation = {
                "kind": event.get("kind"),
                "note_id": note_id,
                "note_revision_id": event.get("revision_id"),
                "origin": event.get("origin"),
                "trigger": event.get("trigger"),
                "source_job_id": event.get("source_job_id"),
                "task_key": event.get("task_key"),
                "transform_id": event.get("transform_id"),
                "transform_revision": event.get("transform_revision"),
                "restore_of": event.get("restore_of"),
                "word_count": event.get("word_count"),
                "edited_spans": event.get("edited_spans") or [],
                "asr_example": False,
                "evidence_status": "reliable_target_observation",
            }
            appended = 0
            for ex_id in targets:
                env, parent_rev = td._conn_latest(db, ex_id)
                if env is None:
                    continue
                notes = list(env.get("notes") or [])
                notes.append(dict(observation, observed_at_utc=now))
                env["notes"] = notes[-self._NOTE_OBSERVATIONS_MAX:]
                td._conn_append_revision(db, ex_id, env, parent_rev)
                db.execute(
                    "INSERT OR IGNORE INTO note_evidence_links(note_id,"
                    " example_id, job_id, first_seen_utc) VALUES(?,?,?,?)",
                    (note_id, ex_id, event.get("source_job_id"), now))
                appended += 1
            return appended
        n = self.store.submit(op)
        if n:
            self.emit("training.note_revision_recorded", level="INFO",
                      reason_code=event.get("kind"),
                      detail=f"origin={event.get('origin')}"
                             f" examples={n}")

    def on_note_deleted(self, payload: dict):
        """M12 (S20/S29.14): note deletion closes its evidence
        references — one final content-free ``note_deleted`` observation
        per linked example (the links themselves were closed inside the
        deletion op). Mined note text is purged with the note; the
        observations remain as the content-free record."""
        try:
            closed = payload.get("closed_examples") or []
            if not closed or self.consent.state() != "enabled":
                return
            from . import training_data as td

            def op(db):
                now = ids.now_utc_iso()
                appended = 0
                for item in closed:
                    ex_id = item.get("example_id")
                    env, parent_rev = td._conn_latest(db, ex_id)
                    if env is None:
                        continue
                    notes = list(env.get("notes") or [])
                    notes.append({
                        "kind": "note_deleted",
                        "note_id": payload.get("note_id"),
                        "asr_example": False,
                        "observed_at_utc": now,
                    })
                    env["notes"] = notes[-self._NOTE_OBSERVATIONS_MAX:]
                    td._conn_append_revision(db, ex_id, env, parent_rev)
                    appended += 1
                return appended
            n = self.store.submit(op)
            if n:
                self.emit("training.note_deleted_recorded", level="INFO",
                          detail=f"examples={n}")
        except Exception as e:
            self.emit("training.note_capture_failed", level="WARNING",
                      reason_code=type(e).__name__)

    @staticmethod
    def _observation_block(observer) -> dict:
        """Content-free observation summary (ids/counts/reasons/ranges
        only; before/after texts are lease-governed artifacts)."""
        if observer is None:
            return {"status": "outcome_observation_unavailable"}
        return {
            "status": "observed",
            "recorded": True,
            "observation_id": observer.observation_id,
            "stop_reason": observer.stop_reason,
            "edited": observer.edited,
            "reanchors": observer.reanchors,
            "ticks": observer.ticks,
            "undo_candidate": observer.undo_candidate,
            "before_artifact_id": observer.before_artifact,
            "after_artifact_id": observer.after_artifact,
            "no_edit_observed": (observer.stop_reason == "window_elapsed"
                                 and not observer.edited),
        }

    def on_failure(self, ctx, error_kind):
        """Pipeline exception before finalize: record what was captured with
        an explicit failure reason (content-free — exception type only)."""
        if not ctx.collecting or ctx.example_id:
            return
        if ctx.publish_attempted:
            return
        ctx.secret_hits = scan_secrets(ctx.raw_text or "") \
            + scan_secrets(ctx.applied_text or "")
        envelope = self._envelope(ctx, {"passes": [], "pipeline_error":
                                        error_kind})
        envelope["outcome"] = {"insertion": "not_attempted",
                               "correctness": "unreviewed",
                               "pipeline_error": error_kind}
        self._publish(ctx, envelope, "capture_failed_pipeline")

    # ---- explicit user actions (minimal M02 surface) ----------------------

    def exclude_last(self):
        row = self.store.latest_example()
        if not row:
            return None
        ex_id, _job_id, state = row
        if state == "deleted":
            return None
        self.store.set_example_state(ex_id, "excluded")
        self.emit("training.example_excluded", level="INFO",
                  job_id=_job_id, reason_code="user_exclude")
        return ex_id

    def mark_last_correct(self):
        row = self.store.latest_example()
        if not row:
            return None
        ex_id, job_id, state = row
        if state in ("deleted", "expired"):
            return None
        # M02-AUDIT-16: the menu's "correct" is an intended-writing
        # judgment (the user did not audio-review anything) — routed
        # through the same op as the Hub's Mark Intended: provenance
        # user_explicit_intended_writing, reviewed lifecycle (retained
        # until removed). Earlier user_explicit revisions stay as they
        # were recorded; nothing is bulk-upgraded.
        from . import training_data as td
        try:
            rev = self.store.submit(
                lambda db: td.conn_mark_intended(db, ex_id, True))
        except Exception as e:
            self.emit("training.capture_failed", level="WARNING",
                      job_id=job_id, reason_code=type(e).__name__,
                      outcome="annotation_not_recorded")
            return None
        self.emit("training.annotation_recorded", level="INFO", job_id=job_id,
                  reason_code="mark_correct")
        return rev

    # ---- envelope ---------------------------------------------------------

    def _envelope(self, ctx, cleanup_detail) -> dict:
        policy = ctx.policy or {}
        artifact_ids = {
            "original_audio": ctx.audio_artifact,
            "source_text": ctx.raw_artifact,
            # The cleanup proposal is the main pass over the post-corrections
            # input; the corrections pass has its own artifact in
            # cleanup.passes (both used to share this join ambiguously). A
            # rejected proposal stays in passes with its rejected role.
            # With pass status recorded, only a SELECTED whole-window
            # candidate is the cleanup proposal (a truncated, rolled-back
            # or half-window retry candidate never is).
            "cleanup_proposal": next(
                (p["proposal_artifact_id"] for p in cleanup_detail["passes"]
                 if p.get("kind") == "cleanup"
                 and p.get("accepted") is not False
                 and p.get("status") in (None, "selected")
                 and not p.get("depth")
                 and p.get("proposal_artifact_id")), None),
            "applied_output": ctx.applied_artifact,
        }
        from . import capabilities as caps
        manifest = caps.asr_capability_manifest(
            (policy.get("models") or {}).get("asr"),
            model_revision=(policy.get("models") or {}).get("asr_revision"),
            runtime=(policy.get("runtime") or {}))
        missing = {
            "normalization": R_NOT_CAPTURED,        # M04 when stage skipped
            "context": R_NOT_CAPTURED,              # M06
            "asr_word_timestamps": caps.missing_reason_for(
                "word_timestamps", manifest),
            "asr_confidence": caps.missing_reason_for(
                "word_confidence", manifest),
            "asr_n_best": caps.missing_reason_for("n_best", manifest),
            "asr_token_logprobs": caps.missing_reason_for(
                "token_log_probs", manifest),
            "transform": R_NOT_APPLICABLE,
        }
        # M11 (S16): the transform slot is real. No transform requested
        # (raw/clean mode) ⇒ honestly not applicable; requested and a
        # block exists ⇒ the block carries it; requested without a
        # block ⇒ the recorded reason (auto-apply off, unbound mode, or
        # a store failure — never a silent Clean).
        transform_block = ctx.transform_block
        if transform_block is not None:
            del missing["transform"]
        elif (ctx.profile or {}).get("mode") in (
                "polish", "concise", "prompt_engineer", "custom"):
            missing["transform"] = (
                ctx.transform_gate_reason
                or (ctx.profile or {}).get("fallback_reason")
                or "transform_not_run")
        if ctx.audio_artifact is None:
            missing["original_audio"] = (
                R_NOT_CAPTURED if ctx.audio_write_failed else R_CONSENT)
        # M03 (S29.5/M03-AC05): model-input ranges map to the parent audio
        # in original samples, or the join is reported as a discontinuity.
        capture = dict(ctx.capture_meta.get("capture", {}))
        discontinuities = []
        if capture.get("journal_dropped_blocks") \
                and not capture.get("journal_gaps"):
            # (Positioned gaps below supersede the unpositioned count —
            # the same loss is never reported twice; review R8.)
            discontinuities.append(
                {"kind": "journal_queue_drop",
                 "blocks": capture.get("journal_dropped_blocks"),
                 "sample_span": "unknown_between_complete_blocks",
                 "source": "capture_journal"})
        if capture.get("device_discontinuity"):
            discontinuities.append(dict(capture["device_discontinuity"]))
        if capture.get("incomplete_tail"):
            discontinuities.append(
                {"kind": "incomplete_tail",
                 "torn_bytes": capture.get("journal_torn_bytes"),
                 "journal_status": capture.get("journal_status")})
        # M03-AUDIT-08/09: recovered audio names each gap at its ORIGINAL
        # sample position (journal v2), or says the timeline could not be
        # verified (journal v1) — never an assumed-continuous splice.
        for gap in capture.get("journal_gaps") or []:
            discontinuities.append(
                {"kind": "journal_gap", "source": "capture_journal",
                 "at_sample": gap.get("at_sample"),
                 "missing_samples": gap.get("missing_samples"),
                 "recovered_offset": gap.get("recovered_offset")})
        if capture.get("audio_source") == "journal_reconstruction" \
                and capture.get("journal_status") == "unfinalized":
            # A clean record-boundary EOF: whether capture continued past
            # it is unknown — stated, not assumed either way.
            discontinuities.append(
                {"kind": "capture_end_unknown",
                 "reason": "journal_not_finalized"})
        if capture.get("audio_source") == "journal_reconstruction" \
                and capture.get("positions_known") is False:
            discontinuities.append(
                {"kind": "timeline_unverified",
                 "reason": "journal_v1_no_positions"})
        if capture.get("wav_declared_samples") is not None \
                and capture.get("wav_available_samples") is not None \
                and capture["wav_available_samples"] \
                < capture["wav_declared_samples"]:
            discontinuities.append(
                {"kind": "truncated_wav",
                 "declared_samples": capture["wav_declared_samples"],
                 "available_samples": capture["wav_available_samples"]})
        ranges_ok = _ranges_within(ctx.decode_ranges,
                                   ctx.audio_sample_count)
        if ctx.decode_ranges is not None and not ranges_ok:
            # M03 test gap 20: an out-of-bounds or malformed model-input
            # range is refused here, in production, not only in a test.
            recog = ctx.capture_meta.setdefault("recognition", {})
            recog["decode_ranges_rejected"] = "out_of_bounds_or_malformed"
        if ctx.decode_ranges is not None and ctx.audio_artifact is not None \
                and ranges_ok:
            audio_preparation = {
                "source": "original_audio",
                "artifact_id": ctx.audio_artifact,
                "sample_rate": capture.get("sample_rate"),
                "resampling": "none",
                "decode_ranges": ctx.decode_ranges,
                "range_units": "original_samples_half_open",
                "discontinuities": discontinuities,
            }
        else:
            audio_preparation = None
            missing["audio_preparation"] = R_NOT_CAPTURED
        # M04 (S29.4): the normalization family exists exactly when the
        # stage ran; otherwise the honest missing reason stays.
        normalization = ctx.normalization
        if normalization is None and getattr(
                ctx, "normalization_missing_reason", None):
            # The stage ran but its evidence was not retained
            # (M04-AUDIT-16) — distinct from a skipped stage. A fully
            # published normalized text stays addressable (review R16).
            missing["normalization"] = ctx.normalization_missing_reason
            if ctx.norm_text_artifact is not None:
                artifact_ids["normalization"] = ctx.norm_text_artifact
        if normalization is not None:
            del missing["normalization"]
            artifact_ids["normalization"] = (
                ctx.norm_text_artifact or ctx.norm_ledger_artifact)
        if ctx.skill_registry_artifact is not None:
            artifact_ids["skill_registry"] = ctx.skill_registry_artifact
        # M05/M06 (S29.4 context family): the block exists when either
        # the frozen pre-decode hint set (M05) or the bounded
        # destination-context snapshot (M06) was captured; the absent
        # half carries its honest reason inside the block.
        context_block = None
        if ctx.context_hints is not None \
                or ctx.context_destination is not None:
            del missing["context"]
            context_block = dict(ctx.context_hints or {})
            if ctx.context_hints is None:
                context_block["hint_set"] = None
                context_block["hint_set_missing_reason"] = R_NOT_CAPTURED
            # The absent destination half carries its honest reason too:
            # context disabled, capture failure or no collection — a
            # replay consumer can distinguish "never read" from "read
            # but not retained".
            if ctx.context_destination is not None:
                context_block["destination"] = ctx.context_destination
                if ctx.context_downstream is not None:
                    context_block["downstream"] = ctx.context_downstream
            elif ctx.collecting:
                context_block["destination"] = None
                context_block["destination_missing_reason"] = (
                    "context_disabled_or_capture_failed")
            # Retention was declined or failed: replay inputs stay
            # honestly incomplete instead of silently missing.
            if ctx.context_destination is not None \
                    and not ctx.context_destination.get("retained", False):
                missing["context_snapshot_payload"] = (
                    R_CONSENT if ctx.context_retention_disabled
                    else R_NOT_CAPTURED)
        env = {
            "training_schema_version": 1,
            "example_id": ctx.example_id,
            "revision_id": None,
            "job_id": ctx.job_id,
            "family_id": ctx.family_id,
            "attempt": ctx.attempt,
            "worker_generation": ctx.worker_generation,
            "stage_generations": dict(ctx.stage_generations),
            "origin": "live_capture",
            "task_kind": "dictation",
            "captured_at_utc": ctx.captured_at_utc,
            "time_quality": ctx.time_quality,
            "timezone": ctx.timezone,
            "utc_offset_minutes": ctx.utc_offset_minutes,
            "consent_revision_id": ctx.consent_revision_id,
            "consent_snapshot_point": ctx.consent_point,
            "capture": capture,
            "audio_preparation": audio_preparation,
            "recognition": dict(ctx.capture_meta.get("recognition", {})),
            "normalization": normalization,
            "context": context_block,
            "profile": ctx.profile,
            "cleanup": cleanup_detail,
            "transform": transform_block,
            "artifact_ids": artifact_ids,
            "missing_reasons": missing,
            "outcome": {"insertion": "not_attempted",
                        "correctness": "unreviewed"},
            "annotations": [],
            "preferences": [],
            "state": "captured_unreviewed",
            "collection_policy": policy,
            "deletion_epoch": 0,
        }
        return env

    def attach_capture_meta(self, ctx, recorder_stats, sample_rate):
        if not ctx.collecting:
            return
        ctx.capture_meta["capture"] = {
            "device": (recorder_stats or {}).get("device"),
            "sample_rate": int(sample_rate),
            "duration_sec": (recorder_stats or {}).get("duration_sec"),
            "voiced_pct": (recorder_stats or {}).get("voiced_pct"),
            "trailing_silence_sec": (recorder_stats or {}).get(
                "trailing_silence_sec"),
            "overflow_blocks": (recorder_stats or {}).get("overflow_blocks"),
            "journal_dropped_blocks": (recorder_stats or {}).get(
                "journal_dropped_blocks"),
            "incomplete_tail": (recorder_stats or {}).get("incomplete_tail"),
            "device_discontinuity": (recorder_stats or {}).get(
                "device_discontinuity"),
            "audio_format": "wav_ieee_float32",
        }
        # M03 capture provenance (content-free): which audio this job's
        # evidence describes — the live in-memory capture or a recovered
        # source — and what is known about its completeness.
        stats = recorder_stats or {}
        for key in ("audio_source", "journal_status", "journal_version",
                    "journal_integrity", "journal_gaps", "positions_known",
                    "journal_torn_bytes", "wav_declared_samples",
                    "wav_available_samples", "stream_teardown_error",
                    "crash_journal", "capture_journal", "recovered",
                    "capture_complete"):
            if stats.get(key) is not None:
                ctx.capture_meta["capture"][key] = stats[key]
