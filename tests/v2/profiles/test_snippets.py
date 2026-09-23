"""EV-12 / M10: snippets — exact content, placeholders, collisions,
rich payloads and protection (Spec S17, contracts/profiles.md).

Covers M10-AC02 (exact stored content unless rewriting was explicitly
configured), the literal-escape precedence, snippet/skill same-layer
ambiguity, snippet-over-vocabulary composition by spans, duplicate
trigger masking, disabled snippets, protection spans for later stages,
and the versioned store (incl. the rich/RTF payload round trip).

Run: .venv/bin/python tests/v2/profiles/test_snippets.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import snippets as snip  # noqa: E402
from localflow.v2 import snippets_store  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import vocabulary as vocab  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot, NormalizationPolicy, normalize)

POLICY = NormalizationPolicy()


def N(sid, trigger, content, **kw):
    return snip.Snippet(snippet_id=sid, trigger=trigger,
                        name=kw.pop("name", sid), content=content, **kw)


def norm(text, snapshot, **ctx_kw):
    return normalize(text, POLICY,
                     ContextSnapshot(snippets=snapshot, **ctx_kw))


def test_exact_stored_content_and_placeholders():
    """AC02: the expansion is byte-for-byte the stored content with
    utterance-supplied slot values; defaults apply when the utterance
    supplies nothing."""
    s = N("s1", "sign off", "Best,\n{{name}}\nLocalFlow",
          kind="signature")
    snap = snip.SnippetSnapshot([s])
    res = norm("please sign off comma Danny", snap)
    assert "Best,\nDanny\nLocalFlow" in res.text, res.text
    # Two slots, spoken casing preserved, separator-split.
    s2 = N("s2", "sign off", "{{a}} | {{b}}")
    res = norm("sign off comma Danny comma LocalFlow Inc",
               snip.SnippetSnapshot([s2]))
    assert res.text == "Danny | LocalFlow Inc", res.text
    # The SPACED declared form substitutes too (review W1: the
    # declaration regex and the substitution must agree).
    s_spaced = N("s4", "sign off", "Hi {{ name }}, thanks")
    res = norm("sign off comma Danny",
               snip.SnippetSnapshot([s_spaced]))
    assert res.text == "Hi Danny, thanks", repr(res.text)
    # No continuation: the empty value applies.
    res = norm("sign off", snip.SnippetSnapshot([s2]))
    assert res.text == " | ", repr(res.text)
    res = norm("sign off", snip.SnippetSnapshot(
        [N("s3", "sign off", "x{{a}}y")]))
    assert res.text == "xy"
    # Multi-line code snippets keep their newlines exactly (the
    # terminal multiline guard downstream composes unchanged).
    code = N("s4", "main block", "def main():\n    pass\n",
             kind="code")
    res = norm("insert main block now", snip.SnippetSnapshot([code]))
    assert "def main():\n    pass\n" in res.text
    # The expansion ledger carries the snippet id, not content.
    edit = [e for e in res.edits if e.cls == "snippet"][0]
    assert edit.rule_id == "s4" and edit.layer == 3
    print("ok  AC02: exact stored content + utterance-filled slots")


def test_slot_caps_and_separator_bounds():
    s = N("s1", "sign off", "{{a}}")
    snap = snip.SnippetSnapshot([s])
    # A very long continuation reads as prose: no expansion at all
    # (slot values are spoken WORD tokens; the bound is documented).
    filler = ("alpha beta gamma delta epsilon zeta eta theta iota"
              " kappa lambda mu nu xi omicron pi rho sigma tau upsilon"
              " phi chi psi omega then some more words here").split()
    assert len(filler) > 24
    long_prose = "sign off " + " ".join(filler)
    res = norm(long_prose, snap)
    assert res.text == long_prose, res.text
    assert not any(e.cls == "snippet" for e in res.edits)
    # Split behavior: leading separator is the delimiter; surplus
    # words join the last slot (documented).
    assert snip.split_slots(["comma", "a", "comma", "b", "c"], 2) \
        == ["a", "b c"]
    assert snip.split_slots([], 1) == [""]
    assert snip.split_slots(["a"], 0) == []
    print("ok  slot bounds: long continuation stays literal")


def test_literal_escape_and_quotes_win():
    s = N("s1", "sign off", "Best")
    snap = snip.SnippetSnapshot([s])
    res = norm("write the phrase sign off alone", snap)
    assert "sign off" in res.text and "Best\n" not in res.text
    # A quoted trigger is content, not intent.
    res = norm('"sign off" is a phrase', snap)
    assert '"sign off"' in res.text and "Best" not in res.text
    # The escape zone blocks everything, including slot consumption.
    s2 = N("s2", "addr", "one main street")
    res = norm("write the phrase addr now",
               snip.SnippetSnapshot([s2]))
    assert "addr" in res.text and "one main street" not in res.text
    print("ok  literal escape and quote zones outrank snippet intent")


def test_skill_collision_is_ambiguous_vocabulary_loses():
    # Skills fire via the "slash" prefix (M04): "slash code review" is
    # skill intent and the LONGER layer-3 span wins over a snippet
    # trigger inside it; the bare trigger stays the snippet's.
    skill_policy = NormalizationPolicy(
        registered_skills={"code review": "code-review"})
    snap = snip.SnippetSnapshot(
        [N("s1", "code review", "my review template")])
    res = normalize("slash code review today", skill_policy,
                    ContextSnapshot(snippets=snap))
    assert res.text == "/code-review today", res.text
    assert ("snippet", "overlap_conflict") in {
        (r.cls, r.reason) for r in res.rejected}
    res = normalize("run code review today", skill_policy,
                    ContextSnapshot(snippets=snap))
    assert res.text == "run my review template today", res.text
    # A trigger that ITSELF starts with "slash" collides with the skill
    # span exactly: same span, same layer, different outputs — both
    # stay literal (the engine's ambiguity rule, never insertion order).
    snap2 = snip.SnippetSnapshot(
        [N("s2", "slash brainstorm", "my template")])
    skill_policy2 = NormalizationPolicy(
        registered_skills={"brainstorm": "brainstorm"})
    res = normalize("slash brainstorm now", skill_policy2,
                    ContextSnapshot(snippets=snap2))
    assert "my template" not in res.text and \
        "/brainstorm" not in res.text, res.text
    reasons = {(r.cls, r.reason) for r in res.rejected}
    assert ("snippet", "ambiguous_same_span") in reasons, reasons
    assert ("skill", "ambiguous_same_span") in reasons, reasons
    # Layer 5 vocabulary never beats a snippet trigger on the same span.
    entry = vocab.VocabularyEntry(
        entry_id="v1", canonical="Status Page", approved=True,
        aliases=(vocab.Alias(alias="status page"),))
    vsnap = vocab.VocabularySnapshot([entry])
    snap3 = snip.SnippetSnapshot(
        [N("s3", "status page", "https://status.example.net",
           kind="url")])
    res = norm("check the status page now",
               snap3, vocabulary=vsnap)
    assert "https://status.example.net" in res.text, res.text
    print("ok  collisions: slash-prefix disambiguates, exact overlap is"
          " ambiguous, vocabulary loses")


def test_duplicate_trigger_masks_and_disabled_never_fires():
    snap = snip.SnippetSnapshot([
        N("a", "sign off", "A"), N("b", "sign off", "B")])
    assert snap.conflicts and \
        snap.conflicts[0]["reason"] == "duplicate_trigger"
    res = norm("sign off", snap)
    assert res.text == "sign off"  # both stay literal
    # Disabled snippets never match (a disabled rule cannot fire).
    snap2 = snip.SnippetSnapshot([N("a", "sign off", "A", enabled=False)])
    assert "sign off" not in snap2.index
    res = norm("sign off", snap2)
    assert res.text == "sign off"
    print("ok  duplicate triggers mask; disabled snippets never fire")


def test_protection_spans_for_later_stages():
    s = N("s1", "sign off", "Best, {{name}}")
    snap = snip.SnippetSnapshot([s])
    res = norm("sign off comma Danny", snap)
    spans = snip.protected_output_spans(res, snap)
    assert len(spans) == 1
    assert res.text[spans[0][0]:spans[0][1]] == "Best, Danny"
    # allow_rewrite explicitly configured → NOT protected (AC02's
    # "unless rewriting was explicitly configured").
    s2 = N("s2", "sign off", "Best, {{name}}", allow_rewrite=True)
    snap2 = snip.SnippetSnapshot([s2])
    res2 = norm("sign off comma Danny", snap2)
    assert snip.protected_output_spans(res2, snap2) == []
    print("ok  protected output spans; allow_rewrite is explicit")


def test_snippet_validation_and_url_kind():
    for bad in ("", "has digits 2", "punct!"):
        try:
            snip.validate_trigger(bad)
            raise AssertionError(f"trigger {bad!r} accepted")
        except ValueError:
            pass
    # Whitespace normalizes (a double space is a formatting artifact,
    # not a different trigger).
    assert snip.validate_trigger("two  spaces") == "two spaces"
    try:
        N("u", "the site", "not a url {{x}}", kind="url")
        raise AssertionError("url with placeholder accepted")
    except ValueError:
        pass
    try:
        N("u", "the site", "two tokens", kind="url")
        raise AssertionError("multi-token url accepted")
    except ValueError:
        pass
    url = N("u", "the site", "https://example.net/pricing", kind="url")
    res = norm("see the site for prices", snip.SnippetSnapshot([url]))
    assert "https://example.net/pricing" in res.text
    print("ok  trigger/content validation incl. url kind")


def test_store_roundtrip_versions_and_rich_payload():
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        try:
            svc = snippets_store.SnippetStore(st)
            sid = svc.add_snippet(
                trigger="sign off", name="Sign-off",
                content="Best,\n{{name}}", kind="rich",
                content_rtf="{\\rtf1\\b best}")
            assert svc.revision() == 1
            got = svc.snippet(sid)
            assert got.content_rtf == "{\\rtf1\\b best}"
            assert got.revision == 1
            svc.update_snippet(sid, content="Regards,\n{{name}}")
            got = svc.snippet(sid)
            assert got.revision == 2 and got.content == "Regards,\n{{name}}"
            assert svc.revision() == 2
            # The NOCASE trigger index + caller-thread probe reject a
            # duplicate trigger (both would stay literal at match time).
            try:
                svc.add_snippet(trigger="Sign Off", name="x", content="y")
                raise AssertionError("duplicate trigger accepted")
            except ValueError:
                pass
            sid2 = svc.add_snippet(trigger="other one", name="y2",
                                   content="z")
            try:
                svc.update_snippet(sid2, trigger="sign off")
                raise AssertionError("duplicate trigger via update")
            except ValueError:
                pass
            # Re-casing your OWN trigger is a rename, not a duplicate.
            svc.update_snippet(sid, trigger="Sign Off")
            assert svc.snippet(sid).trigger == "Sign Off"
            assert svc.revision() == 4  # two adds + two edits
            # Usage hits never bump the state counter (statistics, not
            # matching state — the vocabulary discipline).
            assert svc.record_hits([sid, sid]) == 1
            assert svc.revision() == 4
            # JSON round trip: idempotent, usage never fabricated.
            doc_path = pathlib.Path(td) / "snippets.json"
            doc_path.write_text(json.dumps(svc.export_json()),
                                encoding="utf-8")
            out = svc.import_json(doc_path)
            assert out == {"created": 0, "updated": 0, "unchanged": 2}, out

            def usage(db, sid=sid):
                row = db.execute(
                    "SELECT usage_count FROM snippets WHERE snippet_id=?",
                    (sid,)).fetchone()
                return row[0]
            assert st.submit(usage) == 1  # untouched by import
            svc.delete_snippet(sid)
            svc.delete_snippet(sid2)
            assert svc.snippets() == []
        finally:
            st.close()
    print("ok  snippet store: versions, rich payload, trigger index,"
          " usage, idempotent import")


def test_conflict_preview_against_dictionary_and_skills():
    term = vocab.VocabularyEntry(
        entry_id="v1", canonical="Status Page", approved=True,
        aliases=(vocab.Alias(alias="status page"),))
    skill = vocab.VocabularyEntry(
        entry_id="k1", canonical="code-review", kind="skill",
        approved=True, scope_kind="global",
        aliases=(vocab.Alias(alias="code review"),))
    cand = N("c1", "status page", "https://status.example.net")
    out = snip.preview_conflicts(cand, [], [term, skill])
    kinds = {c["kind"] for c in out}
    assert "snippet_wins" in kinds
    cand2 = N("c2", "code review", "template")
    out = snip.preview_conflicts(cand2, [], [term, skill])
    kinds = {c["kind"] for c in out}
    assert "ambiguous_with_skill" in kinds
    # Manifest skill aliases preview too.
    out = snip.preview_conflicts(
        N("c3", "idea storm", "x"), [], [], ["idea storm"])
    assert any(c["kind"] == "ambiguous_with_skill" for c in out)
    print("ok  collision preview: skills ambiguous, terms lose")


def main():
    test_exact_stored_content_and_placeholders()
    test_slot_caps_and_separator_bounds()
    test_literal_escape_and_quotes_win()
    test_skill_collision_is_ambiguous_vocabulary_loses()
    test_duplicate_trigger_masks_and_disabled_never_fires()
    test_protection_spans_for_later_stages()
    test_snippet_validation_and_url_kind()
    test_store_roundtrip_versions_and_rich_payload()
    test_conflict_preview_against_dictionary_and_skills()
    print("all snippet tests passed")


if __name__ == "__main__":
    main()
