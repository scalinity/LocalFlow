"""Explicit file tags and exact filename/identifier resolution
(V2 M10, Spec S17 "developer mode").

A file tag is an explicit typed action — the spoken phrase ``attach
file <name>`` — separate from ``@filename`` text (S17). Resolution
prefers an exact match among the files the destination actually knows
(the open document, plus a strictly bounded name-only listing of its
directory when enabled); an ambiguous or unresolved reference never
invents a filename — the words stay literal with a retained review
suggestion.

Attachment status is honest by construction: a surface may claim a
file-chip attachment only after certified readback (the native trial);
every other surface gets the resolved literal filename plus an explicit
``attachment_created: False`` with the reason. No adapter pretends a
chip appeared.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Optional

# The bounded workspace listing: names only (no content reads, no
# stat-then-open chains), at most this many entries, this deep, hidden
# entries skipped. The listing exists so "attach file engine py" can
# resolve against the user's active project — never for indexing
# beyond it.
LISTING_DEPTH = 2
LISTING_CAP = 500

# Spoken separators inside a filename/path reference: the filename dot
# and the path slash ("engine dot py" → engine.py; "sub slash util dot
# py" → sub/util.py). Words without separators join directly — a
# multiword name is spoken with its dots, never guessed.
_SPOKEN_DOT = {"dot", "period"}
_SPOKEN_SLASH = {"slash"}


@dataclasses.dataclass(frozen=True)
class FileResolution:
    """Outcome of resolving one spoken file reference."""

    status: str                    # resolved | ambiguous | unresolved
    filename: Optional[str] = None
    candidates: tuple[str, ...] = ()
    matched_words: int = 0         # how many trailing spoken words the
                                   # reference consumed (the rest of the
                                   # utterance is prose and survives)
    reason: Optional[str] = None


def list_workspace_files(root, *, depth: int = LISTING_DEPTH,
                         cap: int = LISTING_CAP) -> tuple[str, ...]:
    """Bounded, name-only listing of one configured root (relative
    names). Errors degrade to whatever was collected — a listing
    failure must never fail a dictation."""
    root = pathlib.Path(root)
    names: list[str] = []

    def walk(dir_path: pathlib.Path, rel: str, level: int):
        if level > depth or len(names) >= cap:
            return
        try:
            entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if len(names) >= cap:
                return
            if entry.name.startswith("."):
                continue
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                walk(pathlib.Path(entry.path), child_rel, level + 1)
            else:
                names.append(child_rel)

    walk(root, "", 1)
    return tuple(names)


def spoken_to_name(words) -> str:
    """['engine', 'dot', 'py'] → 'engine.py'; ['sub', 'slash',
    'engine', 'dot', 'py'] → 'sub/engine.py'."""
    out = []
    for w in words:
        low = str(w).lower()
        if low in _SPOKEN_DOT:
            out.append(".")
        elif low in _SPOKEN_SLASH:
            out.append("/")
        else:
            out.append(w)
    joined = "".join(out)
    if not joined or joined[0] in "./":
        return " ".join(str(w) for w in words)  # a leading separator
        # is prose, not a name
    return joined


class FileTagResolver:
    """Resolves ``attach file <spoken>`` against the destination's
    known filenames. Exact match wins — progressively: the longest
    spoken word-prefix that exactly matches a known file (full relative
    path or basename) resolves, and only the words it consumed become
    the reference; trailing prose survives untouched. A basename
    matched by several files is ambiguous unless the full relative path
    was spoken; nothing is ever invented. Lookup structures are
    precomputed once (lowered full-path set + basename map) so a
    prefix walk costs O(k) set hits, not O(k·m) path constructions."""

    def __init__(self, known_files=(), *, document_name: Optional[str] = None):
        self.known_files = tuple(known_files)
        self.document_name = document_name
        self._by_full = {f.lower(): f for f in self.known_files}
        self._by_base: dict[str, tuple[str, ...]] = {}
        for f in self.known_files:
            self._by_base.setdefault(
                pathlib.Path(f).name.lower(), []).append(f)

    def _match(self, spoken: str) -> tuple[str, ...]:
        low = spoken.lower()
        # A full-path match and a basename match are BOTH candidates —
        # an exact path does not silently win over a same-basename file
        # (the ambiguity is the honest outcome; speaking the path
        # disambiguates).
        found: set[str] = set()
        exact = self._by_full.get(low)
        if exact is not None:
            found.add(exact)
        found.update(self._by_base.get(low, ()))
        return tuple(sorted(found))

    def resolve(self, spoken_words) -> FileResolution:
        if not spoken_words:
            return FileResolution("unresolved", reason="empty_reference")
        if self.document_name:
            doc_base = pathlib.Path(self.document_name).name.lower()
            # The open document resolves on any prefix that names it.
            for k in range(len(spoken_words), 0, -1):
                if spoken_to_name(spoken_words[:k]).lower() == doc_base:
                    return FileResolution(
                        "resolved", filename=self.document_name,
                        matched_words=k)
        for k in range(len(spoken_words), 0, -1):
            spoken = spoken_to_name(spoken_words[:k])
            matches = self._match(spoken)
            if len(matches) == 1:
                return FileResolution("resolved", filename=matches[0],
                                      matched_words=k)
            if len(matches) > 1:
                return FileResolution(
                    "ambiguous", candidates=matches, matched_words=k,
                    reason="duplicate_basename")
        return FileResolution("unresolved", reason="no_exact_match")


def attachment_plan(surface_id: Optional[str],
                    certified_surfaces=frozenset()) -> dict:
    """What the insertion does with a resolved file tag on this surface
    (S17/M10-AC04): a real file chip only on a certified surface (the
    native trial's readback-verified set); otherwise the literal
    filename lands as text and the limitation is explicit."""
    if surface_id is not None and surface_id in certified_surfaces:
        return {"method": "file_chip", "attachment_created": True,
                "surface": surface_id}
    return {
        "method": "literal_filename",
        "attachment_created": False,
        "surface": surface_id,
        "reason": "uncertified_file_chip_surface",
        "detail": "no certified adapter for this surface; the resolved"
                  " filename is inserted as text and no attachment was"
                  " created",
    }
