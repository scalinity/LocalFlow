"""The developer-surface compatibility registry (V2 M10, Spec S17/E10).

Compatibility is declared per surface — a named text-entry surface
(Claude Code / Codex terminal prompts, IDE chat fields, terminals) —
never per application name alone, and never claimed before the native
trial certifies it. Every row starts ``uncertified``; the enforcement
points live where they already exist:

- Terminal multiline paste safety: ``localflow.v2.insertion``
  (the serialized queue's copy-only offer for multi-line text on an
  uncertified bracketed-paste surface — no synthetic Return, literal
  text never degraded to avoid a collapsed visual block, E10).
- File chips: ``developer.file_tags.attachment_plan`` (literal
  filename + explicit no-attachment reason until a surface is
  certified by readback).

This module is the single declarative table the Hub and the contract
render from; it does not gate anything by itself.
"""

from __future__ import annotations

from ..insertion import service as insertion_service

# surface_id → {kind, app hints, what is certified}. status fields are
# derived (certified_* vs the live certified sets) so the table can
# never drift from the enforcement sets.
SURFACE_REGISTRY = {
    "claude_code_terminal": {
        "kind": "terminal",
        "surfaces": "Claude Code interactive prompt (terminal)",
    },
    "codex_cli": {
        "kind": "terminal",
        "surfaces": "Codex CLI prompt (terminal)",
    },
    "apple_terminal": {
        "kind": "terminal",
        "surfaces": "Terminal.app",
    },
    "iterm2": {
        "kind": "terminal",
        "surfaces": "iTerm2",
    },
    "ghostty": {
        "kind": "terminal",
        "surfaces": "Ghostty",
    },
    "warp": {
        "kind": "terminal",
        "surfaces": "Warp",
    },
    "cursor_chat": {
        "kind": "ide_chat",
        "surfaces": "Cursor chat/composer field",
    },
    "windsurf_chat": {
        "kind": "ide_chat",
        "surfaces": "Windsurf chat field",
    },
    "vscode_chat": {
        "kind": "ide_chat",
        "surfaces": "VS Code chat field",
    },
    "xcode_editor": {
        "kind": "ide_editor",
        "surfaces": "Xcode source editor",
    },
}

# Surfaces certified for file-chip attachments (verified by readback
# in the native trial). Empty until then — an attachment is called
# attached only after certified readback (M10-AC04).
CERTIFIED_FILE_CHIP_SURFACES: frozenset[str] = frozenset()


def certified_bracketed_surfaces() -> frozenset:
    """The live bracketed-paste certified set (one enforcement point:
    the M08 insertion guard's own set, read as a live attribute so a
    future certification rebinding cannot leave this table stale)."""
    return frozenset(insertion_service.CERTIFIED_BRACKETED_SURFACES)


def certified_file_chip_surfaces() -> frozenset:
    return frozenset(CERTIFIED_FILE_CHIP_SURFACES)


def compatibility_table() -> list[dict]:
    """One row per declared surface: kind, bracketed-paste status and
    file-chip status, each derived from the live enforcement sets."""
    bracketed = certified_bracketed_surfaces()
    chips = certified_file_chip_surfaces()
    rows = []
    for surface_id, spec in sorted(SURFACE_REGISTRY.items()):
        rows.append({
            "surface_id": surface_id,
            "kind": spec["kind"],
            "surfaces": spec["surfaces"],
            "bracketed_paste": (
                "certified" if surface_id in bracketed else "uncertified"),
            "file_chip": (
                "certified" if surface_id in chips else "uncertified"),
            "multiline_behavior": (
                "paste" if surface_id in bracketed
                else "copy_only_multiline"),
        })
    return rows
