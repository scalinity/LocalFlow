"""Word/block diff rendering for the transform preview (V2 M11, S16).

An intelligible diff is the review surface: word-level operations for
prose transforms, block-level hunks for reorganizations. Pure
``difflib`` over tokens — deterministic, model-free, testable.
"""

from __future__ import annotations

import difflib
import re

_TOKEN_RE = re.compile(r"\S+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def word_diff(source: str, output: str) -> list[dict]:
    """Word-level operations between two revisions:
    ``[{"op": "equal"|"delete"|"insert"|"replace",
        "source_text", "output_text"} ...]`` in document order."""
    src = _tokens(source)
    out = _tokens(output)
    sm = difflib.SequenceMatcher(a=src, b=out, autojunk=False)
    ops = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append({"op": "equal", "source_text": " ".join(src[i1:i2]),
                        "output_text": " ".join(out[j1:j2])})
        elif tag == "delete":
            ops.append({"op": "delete",
                        "source_text": " ".join(src[i1:i2]),
                        "output_text": ""})
        elif tag == "insert":
            ops.append({"op": "insert", "source_text": "",
                        "output_text": " ".join(out[j1:j2])})
        else:
            ops.append({"op": "replace",
                        "source_text": " ".join(src[i1:i2]),
                        "output_text": " ".join(out[j1:j2])})
    return ops


def block_diff(source: str, output: str, context: int = 1) -> str:
    """A compact unified block diff (line/paragraph granularity)."""
    a = source.splitlines() or [""]
    b = output.splitlines() or [""]
    diff = difflib.unified_diff(
        a, b, fromfile="source", tofile="transformed",
        lineterm="", n=context)
    return "\n".join(list(diff)[2:]) or "(no changes)"


def diff_stats(source: str, output: str) -> dict:
    """Content-free summary for evidence and the preview header."""
    ops = word_diff(source, output)
    kept = sum(len(o["source_text"].split())
               for o in ops if o["op"] == "equal")
    del_words = sum(len(o["source_text"].split())
                    for o in ops if o["op"] in ("delete", "replace"))
    ins_words = sum(len(o["output_text"].split())
                    for o in ops if o["op"] in ("insert", "replace"))
    return {"source_words": len(source.split()),
            "output_words": len(output.split()),
            "kept_words": kept, "deleted_words": del_words,
            "inserted_words": ins_words}


def render_word_diff(source: str, output: str,
                     marker: tuple = ("[-", "-]", "[+", "+]")) -> str:
    """A one-line readable rendering (delete marked, insert marked)."""
    parts = []
    for op in word_diff(source, output):
        if op["op"] == "equal":
            parts.append(op["source_text"])
        elif op["op"] == "delete":
            parts.append(f"{marker[0]}{op['source_text']}{marker[1]}")
        elif op["op"] == "insert":
            parts.append(f"{marker[2]}{op['output_text']}{marker[3]}")
        else:
            parts.append(
                f"{marker[0]}{op['source_text']}{marker[1]}"
                f"{marker[2]}{op['output_text']}{marker[3]}")
    return " ".join(parts)
