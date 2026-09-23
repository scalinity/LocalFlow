"""EV-14 / M12-AC03: portable export (Spec S20).

Markdown/plain through the M07 document_nodes renderer: supported
structure (headings, paragraphs, ordered/bulleted lists, fenced code,
links) preserved; unsupported elements REPORTED (images in plain
text); a failed export retains the source note untouched; a
structure round trip through the renderer is stable; the export
operates fully offline.

Run: .venv/bin/python tests/v2/notes/test_note_export.py
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.cleanup import document_nodes  # noqa: E402
from localflow.v2.note_export import write_export  # noqa: E402
from localflow.v2.notes import NoteStore  # noqa: E402

CONTENT = (
    "# Café Notes — résumé ✓\n"
    "\n"
    "A paragraph with a [link](https://example.com/a?b=1) and mixed"
    " 日本語 text.\n"
    "\n"
    "- first bullet\n"
    "- second bullet\n"
    "\n"
    "1. step one\n"
    "2. step two\n"
    "\n"
    "```\n"
    "def f():\n"
    "    return 'hi'\n"
    "```\n"
)


def make_note(tmp, content=CONTENT):
    s = store_mod.Store(tmp / "v2.db", backup_dir=None)
    ns = NoteStore(s)
    out = ns.create_note(content)
    return s, ns, out


def test_markdown_structure_round_trip():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s, ns, out = make_note(tmp)
        try:
            report = write_export(tmp / "note.md", ns.open_note(
                out["note_id"]), ns, "markdown")
            assert report["ok"] and report["unsupported"] == []
            text = (tmp / "note.md").read_text()
            # Supported structure survives verbatim through the
            # renderer: lists keep canonical markers, code stays
            # fenced, the link and unicode ride untouched.
            assert "# Café Notes — résumé ✓" in text
            assert "[link](https://example.com/a?b=1)" in text
            assert "- first bullet" in text and "- second bullet" in text
            assert "1. step one" in text and "2. step two" in text
            assert "```" in text and "def f():" in text
            # Round trip: the exported markdown parses to the same
            # structure facts as the source (renderer stability).
            src = document_nodes.structure_facts(document_nodes.parse(
                CONTENT))
            got = document_nodes.structure_facts(document_nodes.parse(
                text))
            assert src == got, f"structure drift: {src} != {got}"
        finally:
            s.close()
    print("ok  AC03: markdown preserves structure; renderer round trip")


def test_plain_text_and_unsupported_reporting():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = store_mod.Store(tmp / "v2.db", backup_dir=None)
        try:
            ns = NoteStore(s)
            out = ns.create_note(CONTENT)
            att = ns.add_attachment(out["note_id"], b"PNGDATA",
                                    "image/png", "screenshot.png")
            ns.append_revision(
                out["note_id"],
                CONTENT + f"\n![shot](attachment:{att['attachment_id']})\n",
                origin="attachment", trigger="explicit")
            note = ns.open_note(out["note_id"])
            # Plain text: images are unsupported and REPORTED (never
            # silently dropped — the marker stays in the output).
            r = write_export(tmp / "note.txt", note, ns, "plain")
            assert r["ok"]
            kinds = [(u["kind"], u["attachment_id"])
                     for u in r["unsupported"]]
            assert kinds == [("attachment", att["attachment_id"])], kinds
            body = (tmp / "note.txt").read_text()
            assert f"attachment:{att['attachment_id']}" in body, \
                "unsupported element silently dropped"
            assert "    def f():" in body  # code indented, not fenced
            assert "Café Notes — résumé ✓" in body  # heading as text
            # AC03's plain half: list structure and links survive too.
            assert "- first bullet" in body and "1. step one" in body
            assert "[link](https://example.com/a?b=1)" in body
            # Markdown: the payload copies beside the file (portable)
            # and the marker names the copy.
            r2 = write_export(tmp / "out" / "note.md", note, ns,
                              "markdown")
            assert r2["ok"] and r2["attachments_copied"] == 1 \
                and r2["unsupported"] == []
            exported = (tmp / "out" / "note.md").read_text()
            assert "](note-01.png)" in exported
            assert (tmp / "out" / "note-01.png").read_bytes() == \
                b"PNGDATA"
            # A purged attachment reports honestly in markdown too.
            ns.delete_attachment(att["attachment_id"])
            note2 = ns.open_note(out["note_id"])
            r3 = write_export(tmp / "out2.md", note2, ns, "markdown")
            assert r3["ok"] and len(r3["unsupported"]) == 1 and \
                r3["unsupported"][0]["detail"] == "payload_missing"
            body3 = (tmp / "out2.md").read_text()
            assert f"attachment:{att['attachment_id']}" in body3
        finally:
            s.close()
    print("ok  AC03: unsupported elements reported, never dropped")


def test_failed_export_retains_source_note():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s, ns, out = make_note(tmp)
        try:
            # An unwritable destination: the export reports the failure
            # and the note is byte-identical (export never mutates).
            before = ns.open_note(out["note_id"])
            r = write_export("/dev/null/nope/x.md", before, ns,
                             "markdown")
            assert r["ok"] is False and r["reason"]
            after = ns.open_note(out["note_id"])
            assert after["revision"]["content"] == \
                before["revision"]["content"]
            assert after["current_revision_id"] == \
                before["current_revision_id"]
            # Unknown format refuses loudly.
            try:
                write_export(tmp / "x.html", before, ns, "html")
                raise AssertionError("unknown format accepted")
            except ValueError:
                pass
        finally:
            s.close()
    print("ok  failed export retains the source note; formats gated")


def test_offline_export_and_content_operations():
    """M12-AC04 (automated half): create/search/export all function with
    networking disabled — the note path is pure local disk + SQLite."""
    import socket

    class _NoNetwork(Exception):
        pass

    def _blocked(*a, **k):
        raise _NoNetwork()

    socket.socket = _blocked
    socket.create_connection = _blocked
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            s, ns, out = make_note(tmp)
            try:
                assert len(ns.search("日本語")) == 1
                assert len(ns.notes()) == 1
                r = write_export(tmp / "n.md", ns.open_note(
                    out["note_id"]), ns, "markdown")
                assert r["ok"] and r["bytes"] > 0
            finally:
                s.close()
    finally:
        import importlib
        importlib.reload(socket)
    print("ok  AC04: content/search/export with sockets disabled")


if __name__ == "__main__":
    test_markdown_structure_round_trip()
    test_plain_text_and_unsupported_reporting()
    test_failed_export_retains_source_note()
    test_offline_export_and_content_operations()
    print("all note export tests passed")
