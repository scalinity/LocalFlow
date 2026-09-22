"""Cleanup V2 (M07, Spec S13–S14): faithful cleanup and
document-aware formatting.

Public surface:
- ``CleanupEngine`` — the V2 engine (windowing, corrections with exact
  offsets, validation, fallback ladder, output-limit recovery).
- ``ModelRunner`` — the worker-side mlx model runner (explicit greedy
  sampling, template revision, output-limit detection).
- ``prompts`` / ``validation`` / ``document_nodes`` / ``engine`` — the
  submodules (contract, validator, renderer).

V1 (``localflow.cleanup.TranscriptCleaner``) stays intact as the
ablation control and selectable fallback implementation.
"""

from . import prompts  # noqa: F401
from .engine import (  # noqa: F401
    CleanupEngine,
    CleanupResult,
    Window,
    plan_windows,
    protected_spans_for_cleanup,
)
from .model import ModelRunner, render_messages  # noqa: F401
from .validation import validate  # noqa: F401
