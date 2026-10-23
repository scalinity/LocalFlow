"""The transform execution engine (V2 M11, Spec S16/S29.10, ADR-0002).

``TransformJob`` captures the immutable source revision and every
input that defines the task; ``run_transform`` renders the request,
runs one Claude generation and validates the result. Retry semantics
are explicit (S16 task 7): retry-original is the SAME task (a
preference candidate may join it); transform-of-result and any changed
source/instructions/examples are DIFFERENT tasks — never preference
pairs (S29.10). The serving model and reasoning level are not part of
the task: switching models keeps outputs comparable candidates.

Validation (``VALIDATOR_REVISION``) never silently discards an
uncertain requirement. Every kind guards quoted spans, links, paths and
identifiers verbatim; a lost one degrades the result to
``needs_review`` with the original span kept for review. Prompt
Engineer also returns S16's requirement map: each draft span with the
output span that carries it. A cited span the output does not contain,
or a requirement Claude marks uncertain, is a review issue. An output
that equals its source is its own outcome, ``no_changes``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import time
import copy
from typing import Callable, Optional

from . import atoms as tf_atoms
from . import claude as tf_claude
from . import diffview
from . import prompts as tf_prompts
from . import quality
from .definitions import TransformDefinition

VALIDATOR_REVISION = "independent-gate-4"
SOURCE_CHAR_LIMIT = 12000   # an oversized selection refuses honestly

PATH_APPLIED = "applied"             # validated, may auto-apply/accept
PATH_NEEDS_REVIEW = "needs_review"  # uncertain coverage — review only
PATH_FALLBACK_ORIGINAL = "fallback_original"  # no usable result
PATH_NO_CHANGES = "no_changes"       # the output equals the source


@dataclasses.dataclass(frozen=True)
class TransformJob:
    """One immutable transform request (Spec S16's TransformJob)."""

    transform_id: str
    transform_revision: int
    prompt_revision: str
    mode: str
    source: str                      # the frozen source revision
    source_kind: str = "dictation"   # dictation | selection | result
    instructions: str = ""           # the custom instruction actually used
    examples_revision: str = ""
    examples: tuple = ()             # (before, after) writing samples
    locale: str = "en-US"
    parent_job_id: Optional[str] = None   # dictation attribution
    selection: Optional[tuple] = None     # (start, end) in the source
    context_pack: Optional[dict] = None
    depth: str = "auto"
    followup: str = ""
    constraints: tuple = ()
    _context_identity: str = dataclasses.field(default="", init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "context_pack", copy.deepcopy(self.context_pack))
        object.__setattr__(self, "_context_identity", quality.fingerprint(self.context_pack))
        if len(self.source) > SOURCE_CHAR_LIMIT:
            raise ValueError(
                f"transform source exceeds {SOURCE_CHAR_LIMIT} chars"
                " (refused honestly, not truncated)")

    def task_key(self) -> str:
        """S29.10/S16 task identity: mode, source revision, custom
        instructions, examples and the prompt revision (the contract
        revision IS the built-in instruction surface — candidates
        generated under different prompt revisions are different
        tasks, so an edited contract never pairs with the old one).
        Same key ⇒ genuinely comparable; any difference ⇒ a different
        task, never a preference pair."""
        if quality.fingerprint(self.context_pack) != self._context_identity:
            raise ValueError("frozen context changed; create a new task")
        h = hashlib.sha256()
        for part in (self.mode, self.source, self.instructions,
                     self.examples_revision, self.prompt_revision,
                     self.locale, quality.fingerprint(self.context_pack),
                     self.depth, self.followup, json.dumps(self.constraints)):
            h.update(part.encode("utf-8"))
            h.update(b"\0")
        return f"ttask:{h.hexdigest()[:24]}"

    def task_manifest(self) -> dict:
        """Content-free manifest for evidence rows (hashes/ids only)."""
        return {
            "task_key": self.task_key(),
            "mode": self.mode,
            "source_kind": self.source_kind,
            "source_sha256": hashlib.sha256(
                self.source.encode("utf-8")).hexdigest(),
            "instructions_sha256": hashlib.sha256(
                self.instructions.encode("utf-8")).hexdigest(),
            "examples_revision": self.examples_revision,
            "transform_id": self.transform_id,
            "transform_revision": self.transform_revision,
            "prompt_revision": self.prompt_revision,
            "parent_job_id": self.parent_job_id,
            "context_fingerprint": quality.fingerprint(self.context_pack),
            "compiler_revision": tf_prompts.COMPILER_REVISION,
            "quality_revision": quality.REVISION,
        }


def retry_original(job: TransformJob) -> TransformJob:
    """Re-run the SAME task (same source revision and instructions):
    a fresh attempt joins the same task_key — a valid preference
    candidate (S29.10)."""
    return job


def transform_of_result(job: TransformJob, output: str) -> TransformJob:
    """Transform-the-result: the previous OUTPUT becomes the source —
    a different task by construction (never a preference pair with the
    original run; S16 task 7)."""
    return dataclasses.replace(
        job, source=output, source_kind="result",
        selection=None, parent_job_id=job.parent_job_id)


def changed_source(job: TransformJob, source: str,
                   instructions: Optional[str] = None) -> TransformJob:
    """A retry over changed source or instructions: a different task
    (different task_key by construction — never exported as a
    same-input preference pair, M11-AC05)."""
    return dataclasses.replace(
        job, source=source, instructions=(
            job.instructions if instructions is None else instructions),
        selection=None)


@dataclasses.dataclass(frozen=True)
class TransformResult:
    job: TransformJob
    output: str
    path: str                      # PATH_*
    reason: Optional[str] = None   # fallback/review reason code
    coverage: tuple = ()           # literals + the requirement map
    coverage_summary: Optional[dict] = None
    diff_stats: Optional[dict] = None
    review_excerpts: tuple = ()    # original clauses kept for review
    output_tokens: int = 0
    limit_hit: bool = False
    duration_ms: float = 0.0
    template_revision: Optional[str] = None
    prompt: str = ""               # exact request (evidence only)
    validator_revision: Optional[str] = None  # the gate that decided
    model: Optional[str] = None    # the model that served (message.model)
    reasoning: Optional[str] = None  # the reasoning level it ran at
    input_tokens: int = 0
    blocking_issues: tuple = ()
    metadata: Optional[dict] = None
    attempts: tuple = ()

    @property
    def served_model_id(self) -> Optional[str]:
        return tf_claude.served_label(self.model, self.reasoning)

    def to_json(self) -> dict:
        def total(key):
            return sum(a[key] for a in self.attempts) if self.attempts and all(
                a.get(key) is not None for a in self.attempts) else None
        cost = (sum(tf_claude.cost_usd(a["model"], a["input_tokens"], a["output_tokens"])
                    for a in self.attempts) if self.attempts and all(
                        a.get("model") in tf_claude.MODELS and a.get("input_tokens") is not None
                        and a.get("output_tokens") is not None for a in self.attempts) else None)
        return {
            "path": self.path, "reason": self.reason,
            "validator_revision": self.validator_revision,
            "task_key": self.job.task_key() if self.job else None,
            "transform_id": self.job.transform_id if self.job else None,
            "transform_revision": (self.job.transform_revision
                                   if self.job else None),
            "prompt_revision": (self.job.prompt_revision
                                if self.job else None),
            "coverage": self.coverage_summary,
            "review_issues": len(self.review_excerpts),
            "output_tokens": self.output_tokens,
            "input_tokens": self.input_tokens,
            "limit_hit": self.limit_hit,
            "duration_ms": self.duration_ms,
            "template_revision": self.template_revision,
            "model": self.model, "reasoning": self.reasoning,
            "blocking_issues": list(self.blocking_issues),
            "metadata": self.metadata,
            "attempts": list(self.attempts),
            "total_input_tokens": total("input_tokens"),
            "total_output_tokens": total("output_tokens"),
            "cost_usd": cost,
            "diff": self.diff_stats,
            "output_sha256": hashlib.sha256(
                self.output.encode("utf-8")).hexdigest(),
        }


def validate_common(source: str, output: str) -> list[dict]:
    """The every-kind fidelity guard: quoted/backtick/fenced spans,
    URLs, paths and identifiers carry verbatim (an authorized rephrase
    never rewrites an identifier), and an empty output is never a
    result."""
    issues = []
    if not output.strip():
        issues.append({"kind": "empty_output", "excerpt": ""})
    for cov in _literal_coverage(source, output):
        if cov.status != "covered":
            issues.append({"kind": cov.atom.kind, "excerpt": cov.atom.excerpt})
    return issues


def _literal_coverage(source: str, output: str) -> list[tf_atoms.Coverage]:
    return [tf_atoms.cover(a, output)
            for a in tf_atoms.extract_atoms(source, mode="custom")]


_MARKUP = re.compile(r"[*_`#>]+")
_EDGE = " \t\n.,:;!?\"'“”‘’()[]-–—•"


def _norm(text: str) -> str:
    """Comparison form for a cited span: markdown marks dropped,
    whitespace collapsed, case folded, edge punctuation trimmed."""
    return " ".join(_MARKUP.sub("", text).split()).casefold().strip(_EDGE)


def _locate(span: str, text: str):
    """(start, end) of span in text, or (None, None) when it is present
    only up to markup/case/spacing; None when it is absent."""
    if not _norm(span):
        return None
    i = text.find(span.strip())
    if i >= 0:
        return i, i + len(span.strip())
    return (None, None) if _norm(span) in _norm(text) else None


def _map_coverage(source, output, requirements, uncertain):
    """S16's requirement map as Claude reported it, verified span by
    span: the draft span must be in the draft and the output span in
    the output, or the requirement is a review issue."""
    out = []
    for req in requirements:
        src, dst = req["source"], req["output"]
        s_at = _locate(src, source)
        o_at = _locate(dst, output)
        status, why = "covered", "model_map"
        if s_at is None:
            status, why = "uncertain", "source_span_not_found"
        elif o_at is None:
            status, why = "missing", "output_span_not_found"
        atom = tf_atoms.Atom(tf_atoms.REQUIREMENT, src.strip(), (dst.strip(),),
                             *(s_at if s_at and s_at[0] is not None
                               else (0, 0)))
        o_start, o_end = o_at if o_at else (None, None)
        out.append(tf_atoms.Coverage(atom, status, o_start, o_end, why))
    for span in uncertain:
        if not span.strip():
            continue
        s_at = _locate(span, source)
        atom = tf_atoms.Atom(tf_atoms.REQUIREMENT, span.strip(), (),
                             *(s_at if s_at and s_at[0] is not None
                               else (0, 0)))
        out.append(tf_atoms.Coverage(atom, "uncertain", None, None,
                                     "model_uncertain"))
    return out


def _parse_prompt_engineer(text: str):
    obj = json.loads(text)
    prompt = obj["prompt"]
    reqs = obj["requirements"]
    unc = obj["uncertain"]
    if not isinstance(prompt, str) or not isinstance(reqs, list) \
            or not isinstance(unc, list) \
            or not all(isinstance(r, dict) and isinstance(r.get("source"), str)
                       and isinstance(r.get("output"), str) for r in reqs) \
            or not all(isinstance(u, str) for u in unc):
        raise ValueError("prompt engineer output does not match its schema")
    return prompt, reqs, unc


def _dedupe(items) -> tuple:
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return tuple(out)


def _summary(coverage) -> dict:
    summary = tf_atoms.coverage_summary(coverage)
    summary["validator_revision"] = VALIDATOR_REVISION
    return summary


def run_transform(job: TransformJob, generate: Callable, *,
                  model: Optional[str] = None,
                  reasoning: Optional[str] = None, verify=None,
                  context_current=None, cancelled=None,
                  allow_repair=True) -> TransformResult:
    """Execute one transform job. ``generate(system, messages, schema)
    -> {"text", "model", "reasoning", "input_tokens", "output_tokens"}``
    is the Claude call (``claude.call``); it raises
    ``claude.TransformUnavailable`` when there is no usable answer; the
    text is the structured answer (``{"text"}``, or Prompt Engineer's
    prompt and requirement map). The
    result's path decides application: validated → ``applied``; a lost
    literal or an unverified requirement → ``needs_review`` (original
    spans kept, nothing auto-applied); unchanged → ``no_changes``; no
    answer → ``fallback_original`` with the reason."""
    system, messages = tf_prompts.build_request(
        job.mode, job.source, custom_instruction=job.instructions,
        examples=job.examples, context_pack=job.context_pack,
        depth=job.depth, followup=job.followup, constraints=job.constraints)
    job.task_key()  # refuses mutated context before any provider call
    schema = tf_prompts.schema_for(job.mode)
    prompt = json.dumps({"model": model, "reasoning": reasoning,
                         "system": system, "messages": messages, "schema": schema},
                        ensure_ascii=False)
    t0 = time.monotonic()

    def fallback(reason, gen=None):
        gen = gen or {}
        return TransformResult(
            job=job, output=job.source, path=PATH_FALLBACK_ORIGINAL,
            reason=reason, prompt=prompt,
            output_tokens=gen.get("output_tokens") or 0,
            input_tokens=gen.get("input_tokens") or 0,
            model=gen.get("model"), reasoning=gen.get("reasoning", reasoning),
            duration_ms=round((time.monotonic() - t0) * 1000.0, 1),
            validator_revision=VALIDATOR_REVISION)
    try:
        gen = generate(system, messages, schema)
    except tf_claude.TransformUnavailable as e:
        return fallback(f"transform_unavailable:{e.code}",
                        e.usage or ({"model": e.model} if e.model else None))
    except Exception as e:
        return fallback(f"transform_engine_failed:{type(e).__name__}")
    map_cov = []
    metadata = {}
    try:
        if job.mode == "prompt_engineer":
            text, reqs, unc = _parse_prompt_engineer(gen.get("text") or "")
            metadata = json.loads(gen["text"])
            map_cov = _map_coverage(job.source, text, reqs, unc)
        else:
            text = json.loads(gen.get("text") or "")["text"]
            if not isinstance(text, str):
                raise ValueError("text is not a string")
    except (ValueError, KeyError, TypeError):
        return fallback("transform_unavailable:output_invalid", gen)
    output = text  # code/Markdown edge whitespace can be significant
    if not output:
        return fallback("empty_output", gen)
    if any(tag in output and tag not in job.source
           for tag in ("<draft>", "</draft>")):
        # The request's own framing in the answer: a reply that echoed
        # the draft or thought aloud, never pasted over a selection.
        return fallback("transform_unavailable:output_invalid", gen)
    coverage = tuple(_literal_coverage(job.source, output) + map_cov)
    excerpts = _dedupe(c.atom.excerpt for c in coverage if c.review_issue)
    blocking = list(quality.grounding_issues(metadata, job.context_pack))
    attempts = [{"role": "generation", "model": gen.get("model"),
                 "reasoning": gen.get("reasoning", reasoning),
                 "input_tokens": gen.get("input_tokens"),
                 "output_tokens": gen.get("output_tokens"),
                 "latency_ms": gen.get("latency_ms"),
                 "cache_read_input_tokens": gen.get("cache_read_input_tokens"),
                 "cache_creation_input_tokens": gen.get("cache_creation_input_tokens")}]
    independently_checked = False
    if output != job.source and verify is not None:
        try:
            checked = verify(*quality.verification_request(job, output, metadata))
            issues = quality.read_verdict(checked["text"])
            blocking.extend(i["message"] for i in issues)
            independently_checked = True
            attempts.append({"role": "verification", "model": checked.get("model"),
                "reasoning": checked.get("reasoning"), "input_tokens": checked.get("input_tokens"),
                "output_tokens": checked.get("output_tokens"), "latency_ms": checked.get("latency_ms"),
                "cache_read_input_tokens": checked.get("cache_read_input_tokens"),
                "cache_creation_input_tokens": checked.get("cache_creation_input_tokens")})
        except Exception as e:
            blocking.append("Independent verification unavailable: " + type(e).__name__)
    elif output != job.source and job.mode == "prompt_engineer":
        blocking.append("Independent semantic verification has not run")
    if cancelled and cancelled():
        return fallback("transform_unavailable:cancelled", gen)
    if context_current and not context_current(job.context_pack):
        return fallback("transform_unavailable:context_revoked", gen)
    literal_loss = [c.atom.excerpt for c in _literal_coverage(job.source, output) if c.review_issue]
    blocking.extend("Protected literal missing: " + span for span in literal_loss)
    if blocking and allow_repair and verify is not None:
        # One targeted repair, under the same semantic task/context identity.
        # Publication still checks revocation and cancellation after the call.
        try:
            repair_messages = [*messages, {"role": "assistant", "content": gen["text"]},
                {"role": "user", "content": json.dumps({"repair_issues": blocking,
                    "instruction": "Return the complete corrected transformation, preserving the original source requirements and eligible context."}, ensure_ascii=False)}]
            repaired = generate(system, repair_messages, schema)
            result = run_transform(job, lambda *_: repaired, model=model,
                reasoning=reasoning, verify=verify, context_current=context_current,
                cancelled=cancelled, allow_repair=False)
            return dataclasses.replace(result,
                attempts=tuple(attempts) + tuple({**a, "role": "repair"
                    if a["role"] == "generation" else a["role"]}
                    for a in result.attempts),
                duration_ms=round((time.monotonic()-t0)*1000, 1))
        except Exception as e:
            blocking.append("Targeted repair unavailable: " + type(e).__name__)
    if independently_checked:
        # Citations stay inspectable. They cannot certify completeness or
        # create a warning merely because a faithful paraphrase lacks an
        # exact citation. The all-source pass and literal checks decide.
        excerpts = _dedupe(c.atom.excerpt for c in _literal_coverage(job.source, output)
                           if c.review_issue)
    if blocking:
        excerpts = _dedupe((*excerpts, *blocking))
    if excerpts:
        path, reason = PATH_NEEDS_REVIEW, "requirement_coverage_uncertain"
    elif output == job.source:
        path, reason = PATH_NO_CHANGES, "no_changes"
    else:
        path, reason = PATH_APPLIED, None
    return TransformResult(
        job=job, output=output, path=path, reason=reason,
        coverage=coverage, coverage_summary=_summary(coverage),
        review_excerpts=excerpts,
        output_tokens=gen.get("output_tokens") or 0,
        input_tokens=gen.get("input_tokens") or 0,
        model=gen.get("model"), reasoning=gen.get("reasoning", reasoning),
        prompt=prompt,
        duration_ms=round((time.monotonic() - t0) * 1000.0, 1),
        diff_stats=diffview.diff_stats(job.source, output),
        validator_revision=VALIDATOR_REVISION, blocking_issues=tuple(blocking),
        metadata={k: metadata.get(k, []) for k in ("enrichments", "used_context", "warnings")},
        attempts=tuple(attempts))


def job_for_definition(defn: TransformDefinition, source: str, *,
                       source_kind: str = "selection",
                       parent_job_id: Optional[str] = None,
                       selection: Optional[tuple] = None,
                       locale: str = "en-US", context_pack=None,
                       depth="auto", followup="", constraints=()) -> TransformJob:
    """Build the TransformJob a definition executes under (the
    definition's revision + prompt revision frozen at request time)."""
    return TransformJob(
        transform_id=defn.transform_id,
        transform_revision=defn.revision,
        prompt_revision=defn.prompt_revision,
        mode=defn.mode, source=source, source_kind=source_kind,
        instructions=defn.prompt if defn.mode == "custom" else "",
        examples_revision=(defn.prompt_revision
                           if defn.examples else ""),
        examples=tuple(defn.examples), locale=locale,
        parent_job_id=parent_job_id, selection=selection,
        context_pack=context_pack, depth=depth, followup=followup,
        constraints=tuple(constraints))


def result_json_for_store(result: TransformResult) -> str:
    """The lease-governed artifact payload (content-bearing)."""
    return json.dumps(
        {"manifest": result.job.task_manifest(),
         "output": result.output,
         "coverage": [c.to_json() for c in result.coverage],
         "attempts": list(result.attempts),
         "blocking_issues": list(result.blocking_issues),
         "review_excerpts": list(result.review_excerpts)},
        ensure_ascii=False, sort_keys=True)


def decision_json(result: TransformResult) -> str:
    """The transform decision record (content-bearing, lease-governed):
    what the gate decided and why — path, reason, validator revision,
    the serving model and reasoning level, the full coverage map and the
    review excerpts the user was shown. Retained beside the output so
    automated review status and a later human judgment stay
    distinguishable."""
    return json.dumps(
        {"path": result.path, "reason": result.reason,
         "validator_revision": result.validator_revision,
         "model": result.model, "reasoning": result.reasoning,
         "task_key": result.job.task_key() if result.job else None,
         "coverage_summary": result.coverage_summary,
         "coverage": [c.to_json() for c in result.coverage],
         "attempts": list(result.attempts),
         "blocking_issues": list(result.blocking_issues),
         "review_excerpts": list(result.review_excerpts)},
        ensure_ascii=False, sort_keys=True)


def message_for(result: TransformResult) -> dict:
    """The reply shape ``Supervisor.transform`` returns (the app's
    ``result_from_message`` rebuilds the result from it)."""
    return {"result": result.to_json(), "output": result.output,
            "coverage": [c.to_json() for c in result.coverage],
            "review_excerpts": list(result.review_excerpts),
            "task_manifest": result.job.task_manifest(),
            # Content-bearing: the exact request rides the reply only so
            # the app can retain it as a lease-governed artifact.
            "prompt": result.prompt}


def result_from_message(job: TransformJob, msg: dict) -> TransformResult:
    """Rebuild a TransformResult from its reply message."""
    coverage = tuple(
        tf_atoms.Coverage(
            atom=tf_atoms.Atom(
                kind=c.get("kind", ""),
                excerpt=c.get("kept_excerpt", ""),
                anchors=tuple(c.get("anchors", ())),
                start=c.get("source_start", 0),
                end=c.get("source_end", 0),
                ops=tuple(c.get("ops", ()))),
            status=c.get("status", "missing"),
            output_start=c.get("output_start"),
            output_end=c.get("output_end"),
            evidence=c.get("evidence", ""))
        for c in msg.get("coverage") or [])
    meta = msg.get("result") or {}
    return TransformResult(
        job=job, output=msg.get("output") or job.source,
        path=meta.get("path", PATH_FALLBACK_ORIGINAL),
        reason=meta.get("reason"),
        coverage=coverage,
        coverage_summary=meta.get("coverage"),
        diff_stats=meta.get("diff"),
        review_excerpts=tuple(msg.get("review_excerpts") or ()),
        output_tokens=meta.get("output_tokens", 0),
        input_tokens=meta.get("input_tokens", 0),
        limit_hit=bool(meta.get("limit_hit")),
        duration_ms=meta.get("duration_ms", 0.0),
        prompt=msg.get("prompt") or "",
        validator_revision=meta.get("validator_revision"),
        model=meta.get("model"), reasoning=meta.get("reasoning"),
        blocking_issues=tuple(meta.get("blocking_issues") or ()),
        metadata=meta.get("metadata"), attempts=tuple(meta.get("attempts") or ()))
