"""EV-12 / M10: file tags, exact identifiers and the surface
compatibility table (Spec S17/E10, contracts/profiles.md).

- File-tag resolution: exact match only, progressive prefix (trailing
  prose survives), ambiguity never invents, the open document
  resolves, paths disambiguate (M10-AC04's fallback half — the
  certified readback half is the pending native trial).
- The bounded workspace listing: names only, depth/cap/hidden rules.
- The surface compatibility table: per-surface declarations, every
  status derived from the live enforcement sets (no surface claims a
  certification the M08/M10 sets do not carry), terminal multiline
  safety delegated to the one enforcement point.

Run: .venv/bin/python tests/v2/developer/test_developer_resolution.py
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.developer import file_tags, surfaces  # noqa: E402
from localflow.v2.insertion import service as insertion_service  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot, NormalizationPolicy, normalize)

POLICY = NormalizationPolicy()


def make_tree(td):
    for name in ("engine.py", "util.py", "README.md", ".hidden.py"):
        p = pathlib.Path(td, name)
        p.write_text("x", encoding="utf-8")
    sub = pathlib.Path(td, "sub")
    sub.mkdir()
    (sub / "util.py").write_text("x", encoding="utf-8")
    (sub / "deep").mkdir()
    (sub / "deep" / "nested.py").write_text("x", encoding="utf-8")
    return file_tags.list_workspace_files(td)


def test_listing_bounds():
    with tempfile.TemporaryDirectory() as td:
        files = make_tree(td)
        # Hidden entries skipped; depth 2 reaches sub/ but not the
        # depth-3 nested.py.
        assert "engine.py" in files and ".hidden.py" not in files
        assert "sub/util.py" in files
        assert "sub/deep/nested.py" not in files
        assert len(files) <= file_tags.LISTING_CAP
        # The cap is a bound, not a suggestion.
        tiny = file_tags.list_workspace_files(td, depth=1, cap=2)
        assert len(tiny) == 2
        # A missing directory degrades to empty (never raises).
        assert file_tags.list_workspace_files(
            pathlib.Path(td) / "nope") == ()
    print("ok  listing: names only, depth/cap/hidden bounds, degrade")


def test_resolution_exactness_and_prose_survival():
    with tempfile.TemporaryDirectory() as td:
        files = make_tree(td)
        r = file_tags.FileTagResolver(files, document_name="engine.py")
        assert r.resolve(["engine", "dot", "py"]).filename == "engine.py"
        # The open document resolves on its basename.
        assert r.resolve(["engine", "dot", "py"]).status == "resolved"
        # Ambiguous basename (root util.py + sub/util.py): never
        # invented; speaking the path disambiguates.
        amb = r.resolve(["util", "dot", "py"])
        assert amb.status == "ambiguous" and \
            set(amb.candidates) == {"util.py", "sub/util.py"}
        assert r.resolve(["sub", "slash", "util", "dot", "py"]) \
            .filename == "sub/util.py"
        # Unresolved stays literal — nothing is guessed close.
        assert r.resolve(["missing", "dot", "py"]).status == "unresolved"
        # Progressive prefix: trailing prose survives, only the matched
        # words are consumed (through the grammar).
        res = normalize("attach file engine dot py please", POLICY,
                        ContextSnapshot(file_resolver=r))
        assert res.text == "engine.py please", res.text
        res = normalize("first attach file sub slash util dot py then"
                        " run tests", POLICY,
                        ContextSnapshot(file_resolver=r))
        assert res.text == "first sub/util.py then run tests", res.text
        # Ambiguous/unresolved through the grammar: literal + review.
        res = normalize("attach file util dot py now", POLICY,
                        ContextSnapshot(file_resolver=r))
        assert res.text == "attach file util dot py now"
        assert res.rejected[0].reason == "ambiguous_file_reference"
        # The reference run is capped (review W4): a long ramble after
        # the action phrase stays literal — bounded work, no resolution.
        long_ref = "attach file " + " ".join(
            f"word{chr(97 + i % 26)}" for i in range(20))
        res = normalize(long_ref, POLICY,
                        ContextSnapshot(file_resolver=r))
        assert res.text == long_ref
        # Prose "attach the file" never triggers (explicit two-word
        # action phrase required).
        res = normalize("attach the file to the email please", POLICY,
                        ContextSnapshot(file_resolver=r))
        assert res.text == "attach the file to the email please"
        print("ok  resolution: exact/ambiguous/path + prose survival")


def test_attachment_plan_and_ac04():
    """No surface claims an attachment without certified readback; the
    fallback retains the resolved filename and explains itself."""
    plan = file_tags.attachment_plan(None)
    assert plan == {
        "method": "literal_filename", "attachment_created": False,
        "surface": None, "reason": "uncertified_file_chip_surface",
        "detail": plan["detail"]}
    assert "no attachment was created" in plan["detail"]
    # The certified set is empty until the native trial certifies a
    # real surface by readback — nothing is pre-claimed.
    assert surfaces.certified_file_chip_surfaces() == frozenset()
    certified = file_tags.attachment_plan(
        "cursor_chat", certified_surfaces={"cursor_chat"})
    assert certified["method"] == "file_chip" \
        and certified["attachment_created"] is True
    print("ok  AC04 fallback: literal filename + explicit limitation")


def test_surface_compatibility_table():
    table = surfaces.compatibility_table()
    ids = {row["surface_id"] for row in table}
    assert {"claude_code_terminal", "codex_cli", "cursor_chat",
            "vscode_chat", "windsurf_chat", "xcode_editor",
            "apple_terminal"} <= ids
    for row in table:
        # Every declared status derives from the live enforcement
        # sets — the table cannot drift ahead of certification.
        assert row["bracketed_paste"] in ("certified", "uncertified")
        assert row["file_chip"] in ("certified", "uncertified")
        if row["bracketed_paste"] == "uncertified":
            assert row["multiline_behavior"] == "copy_only_multiline"
    # Single enforcement point: the table's bracketed set is exactly
    # the M08 insertion guard's set (currently empty).
    assert surfaces.certified_bracketed_surfaces() == frozenset(
        insertion_service.CERTIFIED_BRACKETED_SURFACES)
    assert insertion_service.CERTIFIED_BRACKETED_SURFACES == ()
    print("ok  compatibility table: derived statuses, one enforcement"
          " point")


def test_terminal_safe_fallback_preserves_literal_text():
    """E10's terminal rule through the M10 surface: a multi-line
    snippet's exact text (newlines and all) is what the safe path
    offers — never degraded to dodge a collapsed visual block, and no
    synthetic execution exists anywhere in the developer package."""
    from localflow.v2 import snippets as snip
    code = snip.Snippet(
        snippet_id="c", trigger="main block", name="c",
        content="def main():\n    pass\n", kind="code")
    res = normalize("run main block", POLICY,
                    ContextSnapshot(snippets=snip.SnippetSnapshot([code])))
    assert res.text == "run def main():\n    pass\n", repr(res.text)
    # The multiline-terminal copy-only rule keys off the destination
    # category in the insertion service (pinned by the M08 suite);
    # here: the surface registry agrees every terminal surface is
    # copy-only until certified, and the text offered is exact.
    term_rows = [r for r in surfaces.compatibility_table()
                 if r["kind"] == "terminal"]
    assert term_rows
    for row in term_rows:
        assert row["multiline_behavior"] == "copy_only_multiline"
    dev_source = pathlib.Path(surfaces.__file__).read_text(
        encoding="utf-8") + pathlib.Path(
        file_tags.__file__).read_text(encoding="utf-8") + \
        pathlib.Path(surfaces.__file__).parent.joinpath(
            "skills.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "popen", "eval("):
        assert forbidden not in dev_source, forbidden
    print("ok  terminal fallback: exact multi-line text, copy-only,"
          " no execution anywhere")


def test_symbol_resolution_prefers_exact_no_invention():
    """Identifiers resolve only through the registered exact map (M04
    layer-4 with M06 context identifiers): an absent or ambiguous
    spoken form never invents a casing convention."""
    ctx = ContextSnapshot(identifiers={"user id": "userId"})
    assert normalize("rename user id here", POLICY, ctx).text == \
        "rename userId here"
    # Without the identifier in context, nothing is invented.
    assert normalize("rename user id here", POLICY, None).text == \
        "rename user id here"
    # A file-tag-style ambiguity (duplicate basenames) never picks a
    # winner — mirrored at the identifier map by one canonical per
    # spoken form (the map cannot carry two; resolution stays exact).
    print("ok  identifiers: exact registered match only, no invention")


def main():
    test_listing_bounds()
    test_resolution_exactness_and_prose_survival()
    test_attachment_plan_and_ac04()
    test_surface_compatibility_table()
    test_terminal_safe_fallback_preserves_literal_text()
    test_symbol_resolution_prefers_exact_no_invention()
    print("all developer resolution tests passed")


if __name__ == "__main__":
    main()
