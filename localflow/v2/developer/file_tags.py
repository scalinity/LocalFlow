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
# The WORK bound (M10-AUDIT-22): directory entries examined across the
# whole walk. A directory is read lazily and the walk stops at this
# budget; the listing then says it was truncated. Deterministic for an
# unchanged tree (each directory's admitted entries are sorted).
LISTING_VISIT_BUDGET = 2000

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)

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


@dataclasses.dataclass(frozen=True)
class ListingResult:
    """Names plus the work actually done (entries examined) and whether
    a bound cut the listing short — reported separately from the result
    count, which alone is no work bound."""

    names: tuple
    visited: int
    truncated: bool
    reason: Optional[str] = None


def list_workspace_files_bounded(root, *, depth: int = LISTING_DEPTH,
                                 cap: int = LISTING_CAP,
                                 budget: int = LISTING_VISIT_BUDGET
                                 ) -> ListingResult:
    """Bounded, name-only listing of one root (relative names). The walk
    is descriptor-relative and never follows a link: each subdirectory
    is opened ``O_NOFOLLOW`` relative to its parent, so a child swapped
    for a link after it was listed is refused, not descended (C214).
    Nothing is opened for reading content. Errors degrade to whatever
    was collected — a listing failure must never fail a dictation."""
    names: list[str] = []
    state = {"visited": 0, "truncated": False, "reason": None}

    def stop(reason):
        state["truncated"] = True
        state["reason"] = state["reason"] or reason

    def walk(fd: int, rel: str, level: int):
        if level > depth:
            return
        batch = []
        try:
            with os.scandir(fd) as it:
                while True:
                    if state["visited"] >= budget:
                        # Conservative: at the budget the listing says
                        # it may be incomplete (reading one more entry
                        # to find out would exceed the budget).
                        stop("visit_budget_reached")
                        break
                    entry = next(it, None)
                    if entry is None:
                        break
                    state["visited"] += 1
                    if entry.name.startswith("."):
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    batch.append((entry.name, is_dir))
        except OSError:
            stop("unreadable_directory")
            return
        batch.sort()
        for name, is_dir in batch:
            if len(names) >= cap:
                stop("name_cap")
                return
            child_rel = f"{rel}/{name}" if rel else name
            if not is_dir:
                names.append(child_rel)
                continue
            if level + 1 > depth:
                continue
            try:
                cfd = os.open(name, os.O_RDONLY | _O_DIRECTORY
                              | _O_NOFOLLOW | _O_CLOEXEC, dir_fd=fd)
            except OSError:
                continue   # vanished, or replaced by a link: not walked
            try:
                walk(cfd, child_rel, level + 1)
            finally:
                os.close(cfd)

    try:
        root_fd = os.open(os.fspath(root), os.O_RDONLY | _O_DIRECTORY
                          | _O_CLOEXEC)
    except (OSError, TypeError):
        return ListingResult((), 0, True, "unreadable_root")
    try:
        walk(root_fd, "", 1)
    finally:
        os.close(root_fd)
    return ListingResult(tuple(names), state["visited"], state["truncated"],
                         state["reason"])


def list_workspace_files(root, *, depth: int = LISTING_DEPTH,
                         cap: int = LISTING_CAP) -> tuple[str, ...]:
    """The names of ``list_workspace_files_bounded`` (historical
    signature)."""
    return list_workspace_files_bounded(root, depth=depth, cap=cap).names


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
        """Longest spoken prefix first; at each length the COMPLETE
        candidate set — every known file plus the open document —
        decides (M10-AUDIT-16): one candidate resolves, several are
        ambiguous. The open document is a candidate like any other; it
        never breaks a tie or manufactures uniqueness."""
        if not spoken_words:
            return FileResolution("unresolved", reason="empty_reference")
        doc = self.document_name
        doc_full = doc.lower() if doc else None
        doc_base = pathlib.Path(doc).name.lower() if doc else None
        for k in range(len(spoken_words), 0, -1):
            spoken = spoken_to_name(spoken_words[:k])
            low = spoken.lower()
            found = set(self._match(spoken))
            if doc is not None and low in (doc_full, doc_base):
                # The open document names itself; a listed copy of the
                # same file (its basename at the listing root) is the
                # same candidate, not a second one.
                if not any(f.lower() in (doc_full, doc_base)
                           and "/" not in f for f in found):
                    found.add(doc)
            matches = tuple(sorted(found))
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
