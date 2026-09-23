"""The transform execution engine (V2 M11, Spec S16/S29.10).

``TransformJob`` captures the immutable source revision and every
input that defines the task; ``run_transform`` renders the prompt,
runs one bounded local generation and validates the result. Retry
semantics are explicit (S16 task 7): retry-original is the SAME task
(a preference candidate may join it); transform-of-result and any
changed source/instructions/examples are DIFFERENT tasks — never
preference pairs (S29.10).

Validation never silently discards an uncertain requirement: the
Prompt Engineer's atom map degrades the result to ``needs_review``
(original clauses surfaced, never applied automatically), and every
kind guards quoted spans, links and technical tokens verbatim.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Callable, Optional

from . import atoms as tf_atoms
from . import diffview
from . import prompts as tf_prompts
from .definitions import TransformDefinition

# Output budget: a reorganization needs more room than faithful
# cleanup but stays bounded (recorded in the result's sampling rule).
MAX_TOKENS_RULE = "min(words*4+128, 4096)"
SOURCE_CHAR_LIMIT = 12000   # an oversized selection refuses honestly

PATH_APPLIED = "applied"             # validated, may auto-apply/accept
PATH_NEEDS_REVIEW = "needs_review"  # uncertain coverage — review only
PATH_FALLBACK_ORIGINAL = "fallback_original"  # generation failed/limit


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

    def __post_init__(self):
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
        h = hashlib.sha256()
        for part in (self.mode, self.source, self.instructions,
                     self.examples_revision, self.prompt_revision,
                     self.locale):
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
    coverage: tuple = ()           # prompt_engineer: the atom map
    coverage_summary: Optional[dict] = None
    diff_stats: Optional[dict] = None
    review_excerpts: tuple = ()    # original clauses kept for review
    output_tokens: int = 0
    limit_hit: bool = False
    duration_ms: float = 0.0
    template_revision: Optional[str] = None
    prompt: str = ""               # exact rendered prompt (evidence only)

    def to_json(self) -> dict:
        return {
            "path": self.path, "reason": self.reason,
            "task_key": self.job.task_key() if self.job else None,
            "transform_id": self.job.transform_id if self.job else None,
            "transform_revision": (self.job.transform_revision
                                   if self.job else None),
            "prompt_revision": (self.job.prompt_revision
                                if self.job else None),
            "coverage": self.coverage_summary,
            "review_issues": len(self.review_excerpts),
            "output_tokens": self.output_tokens,
            "limit_hit": self.limit_hit,
            "duration_ms": self.duration_ms,
            "template_revision": self.template_revision,
            "diff": self.diff_stats,
            "output_sha256": hashlib.sha256(
                self.output.encode("utf-8")).hexdigest(),
        }


def _max_tokens(source: str) -> int:
    return min(len(source.split()) * 4 + 128, 4096)


def _strip_think(text: str) -> str:
    if "</think>" in text:
        return text.split("</think>", 1)[1].strip()
    return text.strip()


def _exact_carry_atoms(source: str) -> list[tf_atoms.Atom]:
    return [a for a in tf_atoms.extract_atoms(source)
            if a.kind in (tf_atoms.QUOTED, tf_atoms.LINK)]


def validate_common(source: str, output: str) -> list[dict]:
    """The every-kind fidelity guard: quoted spans, URLs and technical
    tokens carry verbatim (an authorized rephrase never rewrites an
    identifier), and an empty output is never a result."""
    issues = []
    if not output.strip():
        issues.append({"kind": "empty_output", "excerpt": ""})
    for atom in _exact_carry_atoms(source):
        cov = tf_atoms.cover(atom, output)
        if cov.status != "covered":
            issues.append({"kind": atom.kind, "excerpt": atom.excerpt})
    return issues


def run_transform(job: TransformJob, generate: Callable,
                  render: Optional[Callable] = None
                  ) -> TransformResult:
    """Execute one transform job locally. ``generate(prompt,
    max_tokens) -> {"text", "output_tokens", "limit_hit"}`` is the
    worker's model function (the same ModelRunner the cleanup engine
    uses); ``render`` applies the tokenizer's chat template when
    present. The result's path decides application: validated →
    ``applied``; uncertain requirements → ``needs_review`` (original
    clauses kept, nothing auto-applied); generation failure/limit →
    ``fallback_original``."""
    import time
    messages = tf_prompts.build_messages(
        job.mode, job.source, locale=job.locale,
        custom_instruction=job.instructions, examples=job.examples)
    if render is not None:
        prompt = render(messages)
    else:
        from ..cleanup.model import render_messages
        prompt = render_messages(messages)
    budget = _max_tokens(job.source)
    t0 = time.monotonic()
    try:
        gen = generate(prompt, budget)
    except Exception as e:
        return TransformResult(
            job=job, output=job.source, path=PATH_FALLBACK_ORIGINAL,
            reason=f"transform_engine_failed:{type(e).__name__}",
            review_excerpts=(), prompt=prompt,
            duration_ms=round((time.monotonic() - t0) * 1000.0, 1))
    output = _strip_think(gen.get("text") or "")
    limit = bool(gen.get("limit_hit"))
    duration_ms = round((time.monotonic() - t0) * 1000.0, 1)
    if limit and output:
        return TransformResult(
            job=job, output=job.source, path=PATH_FALLBACK_ORIGINAL,
            reason="output_limit", output_tokens=gen.get(
                "output_tokens", 0), limit_hit=True, prompt=prompt,
            duration_ms=duration_ms)
    if not output.strip():
        return TransformResult(
            job=job, output=job.source, path=PATH_FALLBACK_ORIGINAL,
            reason="empty_output", output_tokens=gen.get(
                "output_tokens", 0), prompt=prompt,
            duration_ms=duration_ms)

    issues = validate_common(job.source, output)
    coverage: tuple = ()
    summary = None
    if job.mode == "prompt_engineer":
        coverage = tuple(tf_atoms.coverage_map(job.source, output))
        summary = tf_atoms.coverage_summary(list(coverage))
        for c in coverage:
            if c.review_issue:
                issues.append({"kind": c.atom.kind,
                               "excerpt": c.atom.excerpt})
    excerpts = tuple(i["excerpt"] for i in issues if i["excerpt"])
    diff = diffview.diff_stats(job.source, output)
    if issues:
        return TransformResult(
            job=job, output=output, path=PATH_NEEDS_REVIEW,
            reason="requirement_coverage_uncertain",
            coverage=coverage, coverage_summary=summary,
            review_excerpts=excerpts,
            output_tokens=gen.get("output_tokens", 0), prompt=prompt,
            duration_ms=duration_ms, diff_stats=diff)
    return TransformResult(
        job=job, output=output, path=PATH_APPLIED,
        coverage=coverage, coverage_summary=summary,
        output_tokens=gen.get("output_tokens", 0), prompt=prompt,
        duration_ms=duration_ms, diff_stats=diff)


def job_for_definition(defn: TransformDefinition, source: str, *,
                       source_kind: str = "selection",
                       parent_job_id: Optional[str] = None,
                       selection: Optional[tuple] = None,
                       locale: str = "en-US") -> TransformJob:
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
        parent_job_id=parent_job_id, selection=selection)


def result_json_for_store(result: TransformResult) -> str:
    """The lease-governed artifact payload (content-bearing)."""
    return json.dumps(
        {"manifest": result.job.task_manifest(),
         "output": result.output,
         "coverage": [c.to_json() for c in result.coverage],
         "review_excerpts": list(result.review_excerpts)},
        ensure_ascii=False, sort_keys=True)
