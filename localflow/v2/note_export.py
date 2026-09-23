"""Portable note export (V2 M12, Spec S20).

Markdown and plain-text export through the M07 ``document_nodes``
renderer — the renderer, not a model, controls numbering and
separators. Supported structure (headings, paragraphs, ordered/bulleted
lists, fenced code, links) is preserved verbatim; unsupported elements
are REPORTED, never silently dropped (the M12 stop condition). Local
image attachments are the one rich element: Markdown export copies
their payloads next to the file (portable); plain-text export reports
them as unsupported.

An export failure retains the source note untouched — export is a
read-only projection; nothing about a failed write can damage the note.
"""

from __future__ import annotations

import os
import pathlib
import re

from .cleanup import document_nodes
from .notes import _ATTACHMENT_RE

FORMATS = ("markdown", "plain")

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(name: str, fallback: str) -> str:
    s = _SLUG_RE.sub("-", (name or "").strip()).strip("-.")
    return s[:48] or fallback


def _render_markdown(content: str, attachments: dict) -> tuple[str, list]:
    """``attachments`` maps attachment id → filename (present ones).
    Missing/purged ids stay verbatim in the output and are reported."""
    unsupported = []
    doc = document_nodes.parse(content)
    out = doc.render()
    # Attachment markers reference the managed store; a portable export
    # names the copied file instead. A missing payload keeps the marker
    # and is reported — never a silent drop.
    def sub(m):
        alt, att_id = m.group(1), m.group(2)
        if att_id in attachments:
            return f"![{alt or 'image'}]({attachments[att_id]})"
        unsupported.append({"kind": "attachment", "attachment_id": att_id,
                            "detail": "payload_missing"})
        return m.group(0)
    return _ATTACHMENT_RE.sub(sub, out), unsupported


def _render_plain(content: str, attachment_names: dict) -> tuple[str, list]:
    """Plain text keeps paragraph/list/code structure (code indented,
    headings as text lines); image attachments are reported as
    unsupported elements."""
    unsupported = []
    parts = []
    for node in document_nodes.parse(content).nodes:
        if isinstance(node, document_nodes.CodeBlock):
            parts.append("\n".join("    " + ln if ln.strip() else ""
                                   for ln in node.lines))
        elif isinstance(node, document_nodes.ListGroup):
            parts.append(node.render())
        else:
            text = node.render()
            if text:
                parts.append("\n".join(
                    ln.lstrip("#").strip() for ln in text.splitlines()))
    out = "\n\n".join(p for p in parts if p is not None).strip()
    for _alt, att_id in _ATTACHMENT_RE.findall(content):
        unsupported.append({
            "kind": "attachment", "attachment_id": att_id,
            "detail": "image_attachments_unsupported_in_plain_text",
            "filename": attachment_names.get(att_id)})
    return out, unsupported


def write_export(path, note, store, fmt: str) -> dict:
    """Write one export file. ``note`` is an ``open_note`` payload.
    Returns an honest report; ``ok: False`` leaves the source note
    exactly as it was (exports never mutate notes)."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown export format {fmt!r}")
    path = pathlib.Path(path)
    rev = note.get("revision") or {}
    content = rev.get("content") or ""
    if fmt == "markdown":
        # Copy attachment payloads beside the export (portable), named
        # after the export stem with an index.
        available = {}
        copies = []
        stem = _slug(path.stem, "note")
        for i, att in enumerate(note.get("attachments") or [], start=1):
            payload = store.attachment_payload(att["attachment_id"])
            if payload is None:
                continue  # reported as unsupported by the renderer
            ext = _ext_of(att)
            name = f"{stem}-{i:02d}.{ext}"
            available[att["attachment_id"]] = name
            copies.append((name, payload))
        text, unsupported = _render_markdown(content, available)
        text += "\n"
        to_write = [(path, text.encode("utf-8"))] + [
            (path.parent / name, payload) for name, payload in copies]
    else:
        names = {a["attachment_id"]: a.get("filename")
                 for a in note.get("attachments") or []}
        text, unsupported = _render_plain(content, names)
        to_write = [(path, (text + "\n").encode("utf-8"))]
    written = []
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        for dest, payload in to_write:
            with open(dest, "wb") as f:
                f.write(payload)
            os.chmod(dest, 0o600)
            written.append(dest)
    except OSError as e:
        # A partial export leaves no half-written set behind — and the
        # SOURCE NOTE was never touched (exports never mutate notes).
        for dest in written:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
        return {"ok": False, "reason": type(e).__name__, "path": str(path),
                "bytes": 0, "unsupported": [], "attachments_copied": 0}
    return {"ok": True, "path": str(path),
            "bytes": sum(len(p) for _, p in to_write),
            "unsupported": unsupported,
            "attachments_copied": len(to_write) - 1}


def _ext_of(att) -> str:
    filename = att.get("filename") or ""
    if "." in filename:
        return _SLUG_RE.sub("", filename.rsplit(".", 1)[1].lower())[:8] \
            or "img"
    return "img"
