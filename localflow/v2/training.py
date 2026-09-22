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


class ConsentManager:
    """The four distinct consent states of S29.2 begin with one here:
    collection itself. Enable/pause/disable append auditable revisions."""

    def __init__(self, store, emit):
        self.store = store
        self.emit = emit

    def state(self) -> str:
        s = self.store.consent_state()
        return s if s in CONSENT_STATES else "disabled"

    def revision_id(self):
        return self.store.current_consent_id()

    def set(self, new_state: str, note=None) -> str:
        if new_state not in CONSENT_STATES:
            raise ValueError(f"unknown consent state {new_state!r}")
        cid = self.store.append_consent(new_state, note=note)
        self.emit("training.collection_state", level="INFO",
                  outcome=new_state, reason_code="consent_revision")
        return cid


class CaptureContext:
    """Per-job collector state (worker-thread only in the V1 pipeline)."""

    def __init__(self, job_id, family_id, *, captured_at_utc, timezone,
                 utc_offset_minutes, consent_revision_id, policy,
                 attempt=1, worker_generation=None):
        self.job_id = job_id
        self.family_id = family_id
        self.captured_at_utc = captured_at_utc
        self.timezone = timezone
        self.utc_offset_minutes = utc_offset_minutes
        self.consent_revision_id = consent_revision_id
        self.policy = policy  # pipeline/config provenance snapshot
        self.collecting = policy is not None
        self.attempt = attempt
        self.worker_generation = worker_generation
        self.audio_artifact = None
        self.audio_write_failed = False  # M03: consent was on but the
        # payload write failed — a different missing reason than consent
        self.capture_meta = {}
        self.decode_ranges = None      # M03: original-sample model-input map
        self.cleanup_path = None       # M03: actual path (never a mislabel)
        self.cleanup_fallback_reason = None
        # M04 (S29.4 normalization family): typed edits + ledger replay
        self.normalization = None
        self.norm_text_artifact = None
        self.norm_ledger_artifact = None
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

    def __init__(self, store, emit, consent, pipeline_info):
        self.store = store
        self.emit = emit
        self.consent = consent
        self.pipeline_info = pipeline_info  # callable -> provenance dict
        self._current = None

    # ---- job lifecycle ---------------------------------------------------

    def job_started(self, job_id, family_id, *, captured_at_utc, timezone,
                    utc_offset_minutes, attempt=1):
        """Snapshot consent at capture time; a mid-job consent change never
        retroactively adds or removes this job's evidence. Does NOT bind the
        observation sink — the worker thread does that via bind_current, so
        a newer job starting on the main thread can never steal this job's
        cleaner observations while it is still processing."""
        state = self.consent.state()
        if state == "enabled":
            consent_id = self.consent.revision_id()
            policy = dict(self.pipeline_info() or {})
        else:
            consent_id = None
            policy = None
        ctx = CaptureContext(
            job_id, family_id, captured_at_utc=captured_at_utc,
            timezone=timezone, utc_offset_minutes=utc_offset_minutes,
            consent_revision_id=consent_id, policy=policy, attempt=attempt)
        return ctx

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

    def on_cleaner_observation(self, obs: dict):
        """Sink for TranscriptCleaner.observer — exact model inputs/outputs."""
        ctx = self._current
        if ctx is None or not ctx.collecting:
            return
        ctx.cleanup_observations.append(obs)

    def on_normalization_result(self, ctx, result, source_text=None,
                                policy=None, context=None):
        """M04 (S29.4): retain the normalized text and the full typed edit
        ledger (accepted AND rejected proposals) as store artifacts, and
        keep the content-free summary for the envelope. The envelope
        carries spans/values/ops/counts — never transcript payloads that
        outlive retention; replay pulls the text from these artifacts.
        A store failure is swallowed: evidence must never fail the stage."""
        if not ctx.collecting or result is None or ctx.example_id:
            return
        try:
            src = source_text if source_text is not None else ""
            if result.text != src:
                ctx.norm_text_artifact = self.store.write_text_artifact(
                    job_id=ctx.job_id, stage="normalization",
                    role="normalized_text", text=result.text,
                    retention_class="training",
                    parent_artifact_id=ctx.raw_artifact,
                    meta={"policy_revision": result.policy_revision})
                self.store.grant_lease(
                    ctx.norm_text_artifact, "training",
                    days=self.store.retention_days["training_buffer"])
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
            self.store.grant_lease(
                ctx.norm_ledger_artifact, "training",
                days=self.store.retention_days["training_buffer"])
        except Exception:
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
        # Envelope values: typed numbers/dates only. String-valued
        # command classes (emails, paths, skill tokens, codes…) carry
        # transcript-derived text in their value; those strings live in
        # the lease-governed ledger artifact, never in the envelope
        # (retention hygiene, S29.14).
        ctx.normalization = {
            "policy_revision": result.policy_revision,
            "edits_count": len(result.edits),
            "rejected_count": len(result.rejected),
            "protected_count": len(result.protected),
            "number_word_to_digit_count": result.number_word_to_digit_count,
            "idempotent": result.idempotence,
            **({"idempotent_reason": idem_reason}
               if idem_reason else {}),
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
                          fallback_reason=None):
        if not ctx.collecting:
            return
        ctx.applied_text = applied_text
        ctx.cleanup_path = path
        ctx.cleanup_fallback_reason = fallback_reason
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

    def finalize(self, ctx):
        """After cleanup: mint the example and revision 1 with the full
        field-family envelope and honest missing reasons."""
        if not ctx.collecting or ctx.example_id:
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
            cleanup_detail["passes"].append({
                "kind": obs.get("kind"),
                "input_sha256": ids.sha256_text(obs.get("input") or ""),
                "prompt_artifact_id": prompt_art,
                "proposal_artifact_id": proposal_art,
                "accepted": obs.get("accepted"),
                "applied_sha256": (ids.sha256_text(obs["applied"])
                                   if obs.get("applied") is not None else None),
            })
        decision = next((o for o in reversed(ctx.cleanup_observations)
                         if o.get("kind") == "cleanup_decision"), None)
        if decision is not None:
            cleanup_detail["decision"] = {
                "accepted": decision.get("accepted"),
                "applied_sha256": (
                    ids.sha256_text(decision["applied"])
                    if decision.get("applied") is not None else None),
                "error": decision.get("error"),
            }
        # M03-AC04: which path actually produced the applied text — an
        # llm-mode fallback to basic is recorded as basic, never "llm".
        cleanup_detail["applied_path"] = ctx.cleanup_path
        cleanup_detail["fallback_reason"] = ctx.cleanup_fallback_reason

        ctx.example_id = self.store.upsert_example(
            job_id=ctx.job_id, family_id=ctx.family_id,
            consent_revision_id=ctx.consent_revision_id,
            collection_policy="m02_live_capture")
        envelope = self._envelope(ctx, cleanup_detail)
        ctx.revision_1 = self.store.append_revision(ctx.example_id, envelope)
        if ctx.secret_hits:
            ctx.quarantined = True
            self.store.set_example_state(ctx.example_id, "quarantined_sensitive")
            self.emit("training.secret_quarantined", level="WARNING",
                      job_id=ctx.job_id, reason_code="suspected_credential",
                      detail=f"patterns={len(ctx.secret_hits)}")
        self.emit("training.revision_saved", level="INFO", job_id=ctx.job_id,
                  reason_code="capture_complete",
                  artifact_ids=[a for a in (ctx.audio_artifact,
                                            ctx.raw_artifact,
                                            ctx.applied_artifact) if a])
        return ctx.example_id

    def on_insertion(self, ctx, posted: bool, chars: int):
        """Outcome revision: V1 posts Cmd+V and cannot observe the target,
        so success is recorded as posted_unverified (contracts/targets.md)."""
        if not ctx.collecting or not ctx.example_id:
            return
        envelope = self.store.latest_revision(ctx.example_id) or {}
        envelope.setdefault("artifact_ids", {})
        envelope["outcome"] = {
            "insertion": "posted_unverified" if posted else "not_attempted",
            "inserted_chars": chars if posted else 0,
            "correctness": "unreviewed",
        }
        envelope["missing_reasons"] = dict(envelope.get("missing_reasons") or {})
        envelope["missing_reasons"]["outcome_observation"] = R_NOT_CAPTURED
        envelope["revision_id"] = None  # append a fresh revision
        self.store.append_revision(ctx.example_id, envelope,
                                   parent_revision_id=ctx.revision_1)

    def on_failure(self, ctx, error_kind):
        """Pipeline exception before finalize: record what was captured with
        an explicit failure reason (content-free — exception type only)."""
        if not ctx.collecting or ctx.example_id:
            return
        ctx.secret_hits = scan_secrets(ctx.raw_text or "") \
            + scan_secrets(ctx.applied_text or "")
        ctx.example_id = self.store.upsert_example(
            job_id=ctx.job_id, family_id=ctx.family_id,
            consent_revision_id=ctx.consent_revision_id,
            collection_policy="m02_live_capture")
        envelope = self._envelope(ctx, {"passes": [], "pipeline_error":
                                        error_kind})
        envelope["outcome"] = {"insertion": "not_attempted",
                               "correctness": "unreviewed",
                               "pipeline_error": error_kind}
        ctx.revision_1 = self.store.append_revision(ctx.example_id, envelope)
        if ctx.secret_hits:
            ctx.quarantined = True
            self.store.set_example_state(ctx.example_id,
                                         "quarantined_sensitive")
            self.emit("training.secret_quarantined", level="WARNING",
                      job_id=ctx.job_id, reason_code="suspected_credential",
                      detail=f"patterns={len(ctx.secret_hits)}")
        self.emit("training.revision_saved", level="INFO", job_id=ctx.job_id,
                  reason_code="capture_failed_pipeline")

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
        envelope = self.store.latest_revision(ex_id)
        if not envelope:
            return None
        outcome = dict(envelope.get("outcome") or {})
        outcome["correctness"] = "correct"
        outcome["correctness_provenance"] = "user_explicit"
        envelope["outcome"] = outcome
        envelope["revision_id"] = None
        rev = self.store.append_revision(ex_id, envelope)
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
            "cleanup_proposal": next(
                (p["proposal_artifact_id"] for p in cleanup_detail["passes"]
                 if p.get("kind") == "cleanup"
                 and p.get("accepted") is not False
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
        if ctx.audio_artifact is None:
            missing["original_audio"] = (
                R_NOT_CAPTURED if ctx.audio_write_failed else R_CONSENT)
        # M03 (S29.5/M03-AC05): model-input ranges map to the parent audio
        # in original samples, or the join is reported as a discontinuity.
        capture = dict(ctx.capture_meta.get("capture", {}))
        discontinuities = []
        if capture.get("journal_dropped_blocks"):
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
                 "torn_bytes": capture.get("journal_torn_bytes")})
        if ctx.decode_ranges is not None and ctx.audio_artifact is not None:
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
        if normalization is not None:
            del missing["normalization"]
            artifact_ids["normalization"] = (
                ctx.norm_text_artifact or ctx.norm_ledger_artifact)
        env = {
            "training_schema_version": 1,
            "example_id": ctx.example_id,
            "revision_id": None,
            "job_id": ctx.job_id,
            "family_id": ctx.family_id,
            "attempt": ctx.attempt,
            "worker_generation": ctx.worker_generation,
            "origin": "live_capture",
            "task_kind": "dictation",
            "captured_at_utc": ctx.captured_at_utc,
            "time_quality": "known",
            "timezone": ctx.timezone,
            "utc_offset_minutes": ctx.utc_offset_minutes,
            "consent_revision_id": ctx.consent_revision_id,
            "capture": capture,
            "audio_preparation": audio_preparation,
            "recognition": dict(ctx.capture_meta.get("recognition", {})),
            "normalization": normalization,
            "cleanup": cleanup_detail,
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
