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


_EXCL = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW


def _create_exclusive(directory: pathlib.Path, name: str, data: bytes):
    """Create ``directory/name`` only if nothing (not even a dangling
    symlink) is there, 0600, and write ``data``. Returns the path, or
    None when the name is taken. A file this call created and could not
    finish is removed before the error propagates."""
    target = directory / name
    try:
        fd = os.open(target, _EXCL, 0o600)
    except FileExistsError:
        return None
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    except BaseException:
        os.close(fd)
        try:
            os.unlink(target)
        except OSError:
            pass
        raise
    os.close(fd)
    return target


def _publish_copy(directory, stem, index, ext, data):
    """An attachment copy under the first FREE name of
    ``stem-NN.ext``, ``stem-NN-2.ext``, … — an existing file is never
    replaced (it was not part of what the user chose to overwrite)."""
    for k in range(1, 1000):
        suffix = "" if k == 1 else f"-{k}"
        name = f"{stem}-{index:02d}{suffix}.{ext}"
        made = _create_exclusive(directory, name, data)
        if made is not None:
            return made
    raise FileExistsError("no free attachment name")


def write_export(path, note, store, fmt: str) -> dict:
    """Write one export. ``note`` is an ``open_note`` payload. Returns an
    honest report; ``ok: False`` leaves the source note exactly as it
    was (exports never mutate notes) AND every file that existed in the
    destination before the export byte-identical (M12-AUDIT-02).

    Publication (the D06 policy): the chosen file is the one the user
    approved replacing (the save panel asked); it is written as a
    private temporary file beside it and moved into place last, with
    one atomic rename — a destination symlink is replaced as a link,
    never written through. Attachment copies (Markdown) are created
    exclusively under free names: a pre-existing sibling is never
    overwritten. Only attachments the note's content references are
    exported (a live attachment with no marker is counted as
    ``unreferenced_attachments``, not copied). Any failure removes
    exactly the files this export created; nothing else is touched."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown export format {fmt!r}")
    path = pathlib.Path(path)
    parent = path.parent
    rev = note.get("revision") or {}
    content = rev.get("content") or ""
    atts = {a["attachment_id"]: a for a in note.get("attachments") or []}
    referenced = list(dict.fromkeys(
        a for a in (m[1] for m in _ATTACHMENT_RE.findall(content))
        if a in atts))
    created = []
    staged = None

    def fail(reason):
        for p in created:
            try:
                os.unlink(p)
            except OSError:
                pass
        if staged is not None:
            try:
                os.unlink(staged)
            except OSError:
                pass
        return {"ok": False, "reason": reason, "path": str(path),
                "bytes": 0, "unsupported": [], "attachments_copied": 0}

    try:
        parent.mkdir(parents=True, exist_ok=True)
        if fmt == "markdown":
            stem = _slug(path.stem, "note")
            available = {}
            total = 0
            for i, att_id in enumerate(referenced, start=1):
                payload = store.attachment_payload(att_id)
                if payload is None:
                    continue  # reported as unsupported by the renderer
                made = _publish_copy(parent, stem, i, _ext_of(atts[att_id]),
                                     payload)
                created.append(made)
                available[att_id] = made.name
                total += len(payload)
            text, unsupported = _render_markdown(content, available)
            body = (text + "\n").encode("utf-8")
        else:
            names = {a: atts[a].get("filename") for a in atts}
            text, unsupported = _render_plain(content, names)
            body = (text + "\n").encode("utf-8")
            total = 0
        for k in range(1000):
            tmp_name = f".{_slug(path.name, 'export')}.lf-{os.getpid()}-{k}"
            staged = _create_exclusive(parent, tmp_name, body)
            if staged is not None:
                break
        else:
            return fail("FileExistsError")
        os.replace(staged, path)
        staged = None
    except OSError as e:
        return fail(type(e).__name__)
    except Exception as e:  # a payload read that raised (store closing…)
        return fail(type(e).__name__)
    return {"ok": True, "path": str(path),
            "bytes": len(body) + total,
            "unsupported": unsupported,
            "attachments_copied": len(created),
            "unreferenced_attachments": len(atts) - len(referenced)}


def _ext_of(att) -> str:
    filename = att.get("filename") or ""
    if "." in filename:
        return _SLUG_RE.sub("", filename.rsplit(".", 1)[1].lower())[:8] \
            or "img"
    return "img"
