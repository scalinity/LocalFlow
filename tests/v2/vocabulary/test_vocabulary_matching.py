"""EV-07 / M05: scoped vocabulary matching over the 40 owning fixtures.

Covers M05-AC02 (all fixtures exact, including the cloud/Claude
mixed-context counterexamples SEED-13/14), AC04 (every applied edit
attributable to an approved rule id; suggested entries never apply),
the E09 negative-control corpus (ordinary prose under a loaded
dictionary), M04 regression (numerical/literal protection intact with
vocabulary active) and the dictionary-skill wiring that closes M04's
inert unknown-skill suggestions.

Run: .venv/bin/python tests/v2/vocabulary/test_vocabulary_matching.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)
from localflow.v2.vocabulary import (  # noqa: E402
    Alias,
    ScopeContext,
    VocabularyEntry,
    VocabularySnapshot,
    preview_entry_conflicts,
    sandbox_phrase,
)

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = json.loads((HERE / "fixtures_vocabulary.json").read_text())
LEGACY_TERMS = ["Qwen", "MLX", "Parakeet", "LocalFlow", "Wispr Flow",
                "PyObjC", "MacBook"]


def _entry_from_fixture(d: dict) -> VocabularyEntry:
    scope = d.get("scope", ["global", None])
    return VocabularyEntry(
        entry_id=d.get("entry_id", "vocab-fixture-" + d["canonical"]),
        canonical=d["canonical"], kind=d.get("kind", "term"),
        scope_kind=scope[0], scope_value=scope[1],
        origin=d.get("origin", "user"),
        enabled=d.get("enabled", True),
        approved=d.get("approved", True),
        verification=d.get("verification", "explicit"),
        aliases=tuple(Alias(alias=a["alias"], approved=a.get(
            "approved", True)) for a in d.get("aliases", [])))


def _snapshot_for(case: dict, extra_entries=()) -> VocabularySnapshot:
    entries = [_entry_from_fixture(d) for d in case["entries"]]
    entries.extend(extra_entries)
    return VocabularySnapshot(
        entries, ScopeContext(**case.get("scope", {})))


def _run(case: dict, extra_entries=()):
    snap = _snapshot_for(case, extra_entries)
    pol = NormalizationPolicy(registered_skills=dict(snap.skills))
    return normalize(case["input_text"], pol,
                     ContextSnapshot(vocabulary=snap)), snap, pol


def NormalisationPolicy_with_other_skill():
    """A policy with one unrelated registration, so the skills grammar is
    active and unknown skill words surface their review suggestion."""
    return NormalizationPolicy(registered_skills={"deploy": "deploy"})


def test_fixture_counts():
    cases = FIXTURES["cases"]
    assert len(cases) == 40, \
        f"expected exactly 40 vocabulary fixtures, got {len(cases)}"
    ids = [c["case_id"] for c in cases]
    assert len(set(ids)) == 40, "duplicate case ids"
    n_neg = sum(1 for c in cases if "negative_control" in c.get("tags", []))
    print(f"ok  fixture set: exactly 40 unique vocabulary cases"
          f" ({n_neg} negative controls)")


def test_all_fixtures_exact():
    failures = []
    for case in FIXTURES["cases"]:
        res, _, _ = _run(case)
        if res.text != case["expected_text"]:
            failures.append((case["case_id"], case["input_text"],
                             res.text, case["expected_text"]))
    assert not failures, failures
    print("ok  all 40 vocabulary fixtures exact (M05-AC02)")


def test_cloud_claude_mixed_context():
    """SEED-13/SEED-14 as owning fixtures: only the in-scope alias span
    changes; ordinary 'cloud' words never become Claude."""
    res, _, _ = _run(next(c for c in FIXTURES["cases"]
                          if c["case_id"] == "LF-VOC-038"))
    assert res.text == "Use Claude Code for cloud deployment"
    edits = [e for e in res.edits if e.cls == "vocabulary"]
    assert len(edits) == 1 and edits[0].input_text == "Clod Code"
    res2, _, _ = _run(next(c for c in FIXTURES["cases"]
                           if c["case_id"] == "LF-VOC-030"))
    assert res2.text == (
        "there is a cloud above us and the cloud deployment is ready")
    assert not [e for e in res2.edits if e.cls == "vocabulary"]
    print("ok  mixed cloud/Claude counterexamples hold (SEED-13/14)")


def test_applied_edits_attributable_to_approved_rules():
    """M05-AC04: every applied vocabulary edit carries the approving
    entry's id and its verification label; rejected/suggested proposals
    never produce edits or rule ids."""
    for case in FIXTURES["cases"]:
        res, snap, _ = _run(case)
        for e in res.edits:
            if e.cls != "vocabulary":
                continue
            assert e.rule_id and e.rule_id in {
                en.entry_id for en in snap.entries}, (case["case_id"], e)
            entry = next(en for en in snap.entries
                         if en.entry_id == e.rule_id)
            assert entry.approved and entry.enabled, case["case_id"]
            assert e.reason == entry.verification, case["case_id"]
    # A suggested (unapproved) entry never applies even in scope.
    res, _, _ = _run(next(c for c in FIXTURES["cases"]
                          if c["case_id"] == "LF-VOC-023"))
    assert not [e for e in res.edits if e.cls == "vocabulary"]
    print("ok  every applied edit attributable to an approved rule"
          " (AC04); suggested entries never apply")


def test_idempotence_with_vocabulary():
    failures = []
    corners = 0
    for case in FIXTURES["cases"]:
        if case.get("idempotence_expected") is False:
            # The documented M04 escape corner: an escape whose object
            # is an alias word re-matches on a second full pass; the
            # pipeline only ever normalizes raw ASR output.
            corners += 1
            continue
        res, _, pol = _run(case)
        snap = _snapshot_for(case)
        second = normalize(res.text, pol, ContextSnapshot(vocabulary=snap))
        if second.text != res.text or second.edits:
            failures.append((case["case_id"], res.text, second.text))
    assert not failures, failures
    print(f"ok  vocabulary normalization idempotent"
          f" ({corners} documented escape corner excluded, reported)")


def test_conflicts_surfaced_not_resolved_by_order():
    """Same-alias/same-scope collisions mask (never picked by order);
    scope precedence decides cross-scope; the sandbox and conflict
    preview surface both."""
    case = next(c for c in FIXTURES["cases"]
                if c["case_id"] == "LF-VOC-035")
    res, snap, _ = _run(case)
    assert not [e for e in res.edits if e.cls == "vocabulary"]
    conflicts = [c for c in snap.conflicts
                 if c["reason"] == "same_scope_alias_conflict"]
    assert conflicts and conflicts[0]["alias"] == "clod code"
    assert len(conflicts[0]["entries"]) == 2
    # Narrower scope wins where both apply (LF-VOC-036).
    case36 = next(c for c in FIXTURES["cases"]
                  if c["case_id"] == "LF-VOC-036")
    res36, _, _ = _run(case36)
    edit36 = [e for e in res36.edits if e.cls == "vocabulary"]
    assert edit36 and edit36[0].output_text == "Claude"
    # Conflict preview names both kinds before an edit is committed.
    cand = _entry_from_fixture(
        {"canonical": "Cloud Code", "scope": ["profile", "coding"],
         "aliases": [{"alias": "clod code", "approved": True}]})
    existing = [_entry_from_fixture(
        {"canonical": "Claude Code", "scope": ["profile", "coding"],
         "aliases": [{"alias": "clod code", "approved": True}]})]
    kinds = {c["kind"] for c in
             preview_entry_conflicts(cand, existing)}
    assert "same_scope_mask" in kinds
    print("ok  conflicts masked/decided deterministically and surfaced")


def test_dictionary_skills_close_m04_unknown_skill_gap():
    """A dictionary-scoped skill entry feeds registered_skills (M04's
    inert review suggestion now converts); an unknown skill still stays
    literal with a retained suggestion."""
    case = next(c for c in FIXTURES["cases"]
                if c["case_id"] == "LF-VOC-032")
    res, snap, _ = _run(case)
    assert res.text == "/brainstorm the pricing page"
    assert dict(snap.skills) == {"brainstorm": "brainstorm"}
    pol = NormalisationPolicy_with_other_skill()
    res2 = normalize("slash brainstorm the pricing page", pol)
    assert res2.text == "slash brainstorm the pricing page"
    assert any(r.reason == "unknown_skill" for r in res2.rejected)
    print("ok  dictionary skills register; unknown skills stay literal")


def test_skill_outranks_vocabulary_on_shared_alias():
    """Layer 3 (registered skill intent) outranks layer 5 vocabulary on
    the same span; the losing proposal is retained as rejected."""
    case = next(c for c in FIXTURES["cases"]
                if c["case_id"] == "LF-VOC-031")
    res, _, _ = _run(case)
    assert res.text == "/code-review"
    losers = [r for r in res.rejected if r.cls == "vocabulary"
              and r.reason in ("overlap_conflict", "ambiguous_same_span")]
    assert losers, "the vocabulary loser must be retained, not dropped"
    print("ok  skill intent outranks vocabulary; loser retained")


def test_negative_control_corpus():
    """E09: 120 ordinary non-command/ambiguous phrases under a loaded,
    fully-approved dictionary (legacy seven + risky phonetic aliases)
    produce zero vocabulary-class edits. The generator self-checks that
    no alias/canonical appears as a whole word, so a pass is real."""
    import random
    risky = [
        VocabularyEntry(entry_id="neg-claude", canonical="Claude",
                        aliases=(Alias("clod"),), approved=True),
        VocabularyEntry(entry_id="neg-claude-code", canonical="Claude Code",
                        aliases=(Alias("clod code"),), approved=True),
        VocabularyEntry(entry_id="neg-sequel", canonical="Sequel",
                        aliases=(Alias("sequal"),), approved=True),
        VocabularyEntry(entry_id="neg-docker", canonical="Docker",
                        aliases=(Alias("doc cur"),), approved=True),
    ]
    legacy = [VocabularyEntry(entry_id=f"neg-{t.lower().replace(' ', '-')}",
                              canonical=t, approved=True)
              for t in LEGACY_TERMS]
    snap = VocabularySnapshot(legacy + risky)
    banned = {w.lower() for e in snap.entries
              for w in [e.canonical] + [a.alias for a in e.aliases]}
    banned |= {"mlxs", "clod", "code"}  # 'code' inside banned multiword
    rng = random.Random(20260922)
    subjects = ["the team", "my neighbor", "the intern", "a loud crowd",
                "the old printer", "everyone"]
    verbs = ["discussed", "mentioned", "criticized", "photographed",
             "remembered", "sketched"]
    objects = ["a cloud formation", "the quarterly budget",
               "a clawed branch", "a crowded market", "the period lamp",
               "a slash of light", "the first draft", "one of the reasons",
               "a queen anne house", "the mac book shop",
               "a whisper of wind", "the para kite festival"]
    tails = ["yesterday", "in the meeting", "before lunch",
             "without hesitation", "last friday", "again"]
    phrases = []
    for i in range(120):
        s = f"{rng.choice(subjects)} {rng.choice(verbs)} " \
            f"{rng.choice(objects)} {rng.choice(tails)}"
        words = {w.strip(".,!?;:").lower() for w in s.split()}
        assert not (words & banned), (s, words & banned)
        phrases.append(s)
    pol = NormalizationPolicy(profile="standard",
                              registered_skills=dict(snap.skills))
    vocab_edits = 0
    for s in phrases:
        res = normalize(s, pol, ContextSnapshot(vocabulary=snap))
        vocab_edits += sum(1 for e in res.edits
                           if e.cls == "vocabulary")
    assert vocab_edits == 0, \
        f"{vocab_edits} false vocabulary triggers in 120 controls"
    print("ok  120/120 ordinary phrases: zero false vocabulary triggers"
          " (denominator reported exactly)")


def test_m04_protection_regression_with_vocabulary_active():
    """Regression requirement: numerical/literal protection from M04
    still passes with a loaded dictionary; URLs and prose untouched."""
    case = next(c for c in FIXTURES["cases"]
                if c["case_id"] == "LF-VOC-028")
    res, _, _ = _run(case)
    assert res.text == "visit https://mlx.example.com/docs"
    snap = _snapshot_for(case)
    pol = NormalizationPolicy(registered_skills=dict(snap.skills))
    res2 = normalize("twelve percent of the cloud budget stays",
                     pol, ContextSnapshot(vocabulary=snap))
    assert res2.text == "12% of the cloud budget stays"
    res3 = normalize("write the words twelve thousand",
                     pol, ContextSnapshot(vocabulary=snap))
    assert res3.text == "twelve thousand"
    print("ok  M04 numeric/literal/URL protection intact (regression)")


def test_sandbox_reports_suggestions_and_conflicts():
    """The phrase sandbox shows applied (approved) matches, what a
    suggested entry WOULD do if approved, and masked conflicts — the
    'suggest Claude visibly' surface (task 3). Out-of-scope suggestions
    are labeled so the panel never advertises a rewrite that cannot
    fire until the scope context applies (review DB1-W3)."""
    suggested = VocabularyEntry(
        entry_id="sb-suggested", canonical="Claude Code",
        scope_kind="profile", scope_value="coding",
        origin="suggested", approved=False, verification="suggested",
        aliases=(Alias("clod code"),))
    in_scope_snap = VocabularySnapshot([suggested],
                                       ScopeContext(profile="coding"))
    out = sandbox_phrase("fix it with clod code now", in_scope_snap)
    assert out["output"] == "fix it with clod code now"
    assert not out["applied"]
    assert out["suggestions"] and \
        out["suggestions"][0]["canonical"] == "Claude Code"
    assert out["suggestions"][0]["in_scope"] is True
    # Same entry under a context its scope does not match: still
    # visible, but labeled inactive rather than silently advertised.
    out_ctx = sandbox_phrase(
        "fix it with clod code now", VocabularySnapshot([suggested]))
    assert out_ctx["suggestions"] and \
        out_ctx["suggestions"][0]["in_scope"] is False
    assert out_ctx["output"] == "fix it with clod code now"
    # Suggestions never appear for quoted literals (the engine tokenizer
    # does not treat quote-attached tokens as words — review DB1-S5).
    out_q = sandbox_phrase('say "clod code" out loud', in_scope_snap)
    assert not out_q["suggestions"]
    print("ok  sandbox surfaces suggestions (scope-labeled) without"
          " applying them")


def test_preview_entry_conflicts_all_kinds():
    """All four conflict-preview kinds (review CA1-W5): same-scope
    mask, scope precedence, duplicate canonical and skill collision."""
    def cand(canonical, aliases, scope=("global", None), tag=""):
        return VocabularyEntry(
            entry_id="pv-" + tag + canonical.lower().replace(" ", "-"),
            canonical=canonical,
            scope_kind=scope[0], scope_value=scope[1], approved=True,
            aliases=tuple(Alias(a) for a in aliases))

    existing = [
        cand("Claude Code", ["clod code"], ("profile", "coding"),
             tag="a-"),
        cand("Deploy Service", ["deploy service"]),
        VocabularyEntry(
            entry_id="pv-deploy-skill", canonical="deploy-service",
            kind="skill", approved=True,
            aliases=(Alias("deploy service"),)),
    ]
    # 1. same_scope_mask: identical alias + scope, different canonical.
    kinds = {c["kind"] for c in preview_entry_conflicts(
        cand("Cloud Code", ["clod code"], ("profile", "coding")),
        existing)}
    assert "same_scope_mask" in kinds
    # 2. scope_precedence: overlapping alias in a different scope.
    kinds = {c["kind"] for c in preview_entry_conflicts(
        cand("Claude Coder", ["clod code"]), existing)}
    assert "scope_precedence" in kinds
    # 3. duplicate_canonical: same canonical spelling (any scope).
    kinds = {c["kind"] for c in preview_entry_conflicts(
        cand("Claude Code", ["x code"], ("workspace", "w"), tag="b-"),
        existing)}
    assert "duplicate_canonical" in kinds
    # 4. skill_wins: an alias colliding with a registered skill.
    kinds = {c["kind"] for c in preview_entry_conflicts(
        cand("Ship It", ["deploy service"]), existing)}
    assert "skill_wins" in kinds
    print("ok  conflict preview names all four collision kinds")


if __name__ == "__main__":
    test_fixture_counts()
    test_all_fixtures_exact()
    test_cloud_claude_mixed_context()
    test_applied_edits_attributable_to_approved_rules()
    test_idempotence_with_vocabulary()
    test_conflicts_surfaced_not_resolved_by_order()
    test_dictionary_skills_close_m04_unknown_skill_gap()
    test_skill_outranks_vocabulary_on_shared_alias()
    test_negative_control_corpus()
    test_m04_protection_regression_with_vocabulary_active()
    test_sandbox_reports_suggestions_and_conflicts()
    test_preview_entry_conflicts_all_kinds()
    print("all vocabulary matching tests passed")
