"""Document representation and renderer for cleanup V2 (M07, Spec S13).

A cleanup output is parsed into paragraphs, list groups and code blocks;
the renderer — not the model — controls numbering and separators (S13:
"A model may propose structure, but the renderer controls numbering and
separators"). Offsets are never needed here; the document is a
rendering/validation view, while window ownership uses the engine's
zero-based half-open code-point source ranges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*```")


@dataclass
class Paragraph:
    lines: list[str] = field(default_factory=list)

    def render(self) -> str:
        return "\n".join(self.lines)


@dataclass
class ListGroup:
    ordered: bool
    start: int = 1
    items: list[str] = field(default_factory=list)

    def render(self, start: int | None = None) -> str:
        n = self.start if start is None else start
        out = []
        for item in self.items:
            if self.ordered:
                out.append(f"{n}. {item}")
                n += 1
            else:
                out.append(f"- {item}")
        return "\n".join(out)


@dataclass
class CodeBlock:
    lines: list[str] = field(default_factory=list)

    def render(self) -> str:
        return "```\n" + "\n".join(self.lines) + "\n```"


@dataclass
class Document:
    nodes: list = field(default_factory=list)

    def render(self) -> str:
        """Plain-text rendering with canonical numbering/separators:
        one blank line between blocks, none between list items."""
        parts = []
        for node in self.nodes:
            if isinstance(node, ListGroup):
                parts.append(node.render())
                continue
            text = node.render()
            if not text:
                continue
            if parts:
                parts.append("")   # blank line between blocks
            parts.append(text)
        return "\n".join(parts).strip()


def parse(text: str) -> Document:
    """Parse markdown-shaped text (the M04 block commands already emit
    blank lines, '- ' bullets, '# ' headings and ``` fences; a cleanup
    proposal may emit numbered/bulleted lists) into a Document."""
    doc = Document()
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if _FENCE_RE.match(line):
            block: CodeBlock = CodeBlock()
            i += 1
            while i < len(lines) and not _FENCE_RE.match(lines[i]):
                block.lines.append(lines[i])
                i += 1
            i += 1              # closing fence
            doc.nodes.append(block)
            continue
        m_bullet = _BULLET_RE.match(line)
        m_ordered = _ORDERED_RE.match(line)
        if m_bullet or m_ordered:
            group = ListGroup(ordered=bool(m_ordered),
                              start=int(m_ordered.group(1)) if m_ordered else 1)
            while i < len(lines):
                mb = _BULLET_RE.match(lines[i])
                mo = _ORDERED_RE.match(lines[i])
                if mb and not group.ordered:
                    group.items.append(mb.group(1).strip())
                elif mo and group.ordered:
                    group.items.append(mo.group(2).strip())
                elif not lines[i].strip() and i + 1 < len(lines) and (
                        _BULLET_RE.match(lines[i + 1])
                        or _ORDERED_RE.match(lines[i + 1])):
                    i += 1       # blank line inside a list group
                    continue
                else:
                    break
                i += 1
            doc.nodes.append(group)
            continue
        if not line.strip():
            i += 1
            continue
        para: Paragraph = Paragraph()
        while i < len(lines) and lines[i].strip() \
                and not _BULLET_RE.match(lines[i]) \
                and not _ORDERED_RE.match(lines[i]) \
                and not _FENCE_RE.match(lines[i]):
            para.lines.append(lines[i])
            i += 1
        doc.nodes.append(para)
    return doc


def renumber(doc: Document, *, continue_groups: bool = True) -> Document:
    """Enforce contiguous numbering per ordered list group. When
    ``continue_groups`` is set, adjacent ordered groups (a list split
    across window seams) are numbered as one run; any intervening block
    restarts numbering at the group's own declared start."""
    out = Document()
    n = None
    for node in doc.nodes:
        if isinstance(node, ListGroup) and node.ordered:
            start = n if (n is not None and continue_groups) else node.start
            out.nodes.append(ListGroup(ordered=True, start=start,
                                       items=list(node.items)))
            n = start + len(node.items)
        else:
            out.nodes.append(node)
            n = None
    return out


def continue_list_number(doc: Document) -> int | None:
    """The next number if the document ends inside an ordered list group
    (windows split mid-list continue numbering across the seam)."""
    if not doc.nodes:
        return None
    last = doc.nodes[-1]
    if isinstance(last, ListGroup) and last.ordered:
        return last.start + len(last.items)
    return None


def structure_facts(doc: Document) -> dict:
    """Content-free structure summary for validation/evidence."""
    return {
        "paragraphs": sum(isinstance(n, Paragraph) for n in doc.nodes),
        "code_blocks": sum(isinstance(n, CodeBlock) for n in doc.nodes),
        "list_groups": [
            {"ordered": g.ordered, "start": g.start, "items": len(g.items)}
            for g in doc.nodes if isinstance(g, ListGroup)
        ],
    }
