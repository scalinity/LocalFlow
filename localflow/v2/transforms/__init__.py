"""Transforms and the requirement-preserving Prompt Engineer (V2 M11).

The S16 package: versioned definitions (``definitions``), prompt
contracts (``prompts``), requirement atoms and the coverage map
(``atoms``), the execution engine with task identity and retry
semantics (``engine``), the Claude models and request (``claude``,
ADR-0002), and the diff surfaces (``diffview``).
Persistence lives in ``localflow.v2.transforms_store`` (schema v7).
"""

from . import atoms, claude, definitions, diffview, engine, prompts
from .definitions import (TransformDefinition, TransformSnapshot,
                          UnavailableTransforms,
                          built_ins, definitions_revision,
                          from_legacy_json, shortcut_conflicts)
from .engine import (PATH_APPLIED, PATH_FALLBACK_ORIGINAL,
                     PATH_NEEDS_REVIEW, PATH_NO_CHANGES, TransformJob,
                     TransformResult,
                     changed_source, job_for_definition, retry_original,
                     run_transform, transform_of_result)

__all__ = [
    "atoms", "claude", "definitions", "diffview", "engine", "prompts",
    "TransformDefinition", "TransformSnapshot", "UnavailableTransforms",
    "built_ins",
    "definitions_revision", "from_legacy_json", "shortcut_conflicts",
    "PATH_APPLIED", "PATH_FALLBACK_ORIGINAL", "PATH_NEEDS_REVIEW",
    "PATH_NO_CHANGES",
    "TransformJob", "TransformResult", "changed_source",
    "job_for_definition", "retry_original", "run_transform",
    "transform_of_result",
]
