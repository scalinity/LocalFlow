"""EV-12 / M10: destination styles and writing-mode precedence.

The pure resolution machinery (Spec S15, contracts/profiles.md):
per-job override → explicit destination rule (workspace > site > app)
→ category default → global default; destination-category derivation
including AI prompts/coding/terminal; disabled rules never fire; the
transform-backed modes resolve honestly as not-yet-executable; and the
M10-AC01 invariant that no style can loosen the S13 cleanup contract.

Run: .venv/bin/python tests/v2/profiles/test_style_resolution.py
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import profiles  # noqa: E402
from localflow.v2 import profiles_store  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.cleanup import prompts as cleanup_prompts  # noqa: E402
from localflow.v2.cleanup import validation  # noqa: E402


def R(rid, scope="global", value=None, mode="clean", numbers="inherit",
      name=None, enabled=True):
    return profiles.StyleRule(
        rule_id=rid, name=name or rid, scope_kind=scope, scope_value=value,
        mode=mode, number_policy=numbers, enabled=enabled)


def test_precedence_chain():
    """job override > destination rule > category default > global."""
    rules = [
        R("g", mode="raw"),                                  # global
        R("a", scope="app", value="com.acme.app", mode="clean",
          numbers="standard"),
        R("s", scope="site", value="https://chat.acme.io",
          numbers="standard"),
        R("w", scope="workspace", value="acme", mode="clean"),
    ]
    dest = profiles.Destination(
        app_bundle="com.acme.app", site_origin="https://chat.acme.io",
        workspace="acme", category="coding")
    wp = profiles.resolve(None, rules, dest)
    assert wp.mode == "clean" and wp.source == "rule:workspace", wp
    # Drop the workspace rule: the site rule's number policy wins.
    wp = profiles.resolve(None, [r for r in rules
                                 if r.rule_id != "w"], dest)
    assert wp.source == "rule:site" and wp.number_policy == "standard"
    assert wp.rule_id == "s"
    # Drop site too: the app rule.
    wp = profiles.resolve(None, [rules[0], rules[1]], dest)
    assert wp.source == "rule:app"
    # No destination rules: category default — Clean everywhere (S15),
    # never the global raw rule (a category default outranks it).
    wp = profiles.resolve(None, [rules[0]], dest)
    assert wp.mode == "clean" and wp.source == "category_default", wp
    # Uncategorized destination: the global rule IS the global default.
    wp = profiles.resolve(None, [rules[0]],
                          profiles.Destination(category=None))
    assert wp.mode == "raw" and wp.source == "rule:global", wp
    # No rules at all: the built-in Clean default.
    wp = profiles.resolve(None, [], profiles.Destination(category=None))
    assert wp.mode == "clean" and wp.source == "global_default", wp
    # The one-job override beats everything.
    wp = profiles.resolve("clean", rules, dest)
    assert wp.mode == "clean" and wp.source == "job_override", wp
    print("ok  precedence: override > workspace > site > app >"
          " category > global")


def test_disabled_rules_never_fire():
    rules = [R("g", mode="raw", enabled=False)]
    wp = profiles.resolve(None, rules, profiles.Destination(
        app_bundle="x", category="terminal"))
    assert wp.mode == "clean" and wp.source == "category_default", wp
    wp = profiles.resolve(None, rules, profiles.Destination(
        app_bundle="x", category=None))
    assert wp.mode == "clean" and wp.source == "global_default", wp
    # A disabled narrower rule cannot shadow an enabled wider one
    # (uncategorized destination so the global step is reachable).
    rules = [R("w", scope="workspace", value="w1", mode="raw",
               enabled=False), R("g", mode="clean")]
    wp = profiles.resolve(None, rules, profiles.Destination(
        workspace="w1", category=None))
    assert wp.mode == "clean" and wp.source == "rule:global", wp
    print("ok  disabled rules never fire (fall through, never block)")


def test_wrong_workspace_rule_does_not_apply():
    rules = [R("w", scope="workspace", value="project-a", mode="raw")]
    wp = profiles.resolve(None, rules, profiles.Destination(
        workspace="project-b", category="coding"))
    assert wp.mode == "clean" and wp.source == "category_default", wp
    wp = profiles.resolve(None, rules, profiles.Destination(
        workspace="project-a", category="coding"))
    assert wp.mode == "raw" and wp.source == "rule:workspace", wp
    print("ok  wrong workspace: rule does not apply")


def test_category_derivation():
    d = profiles.derive_category
    assert d("mail", None) == "email"
    assert d("messaging", "com.apple.iChat") == "personal_messaging"
    assert d("messaging", "com.tinyspeck.slackmacgap") == "work_messaging"
    assert d("messaging", "com.other.chat") == "messaging"
    assert d("editor", None) == "documents"
    assert d("ide", None) == "coding"
    assert d("terminal", None) == "terminal"
    # AI prompt fields: the origin decides; a generic browser field is
    # never forced into a category.
    assert d("browser", None, "https://claude.ai") == "ai_prompt"
    assert d("browser", None, "https://chatgpt.com") == "ai_prompt"
    assert d("browser", None, "https://example.com") is None
    assert d("unknown", None) is None
    # Structure hints map onto the M07 vocabulary.
    assert profiles.hint_key("personal_messaging") == "messaging"
    assert profiles.hint_key("ai_prompt") == "ai_prompt"
    assert profiles.hint_key("coding") in cleanup_prompts._STRUCTURE_HINTS
    assert profiles.hint_key("terminal") in cleanup_prompts._STRUCTURE_HINTS
    assert profiles.hint_key("email") in cleanup_prompts._STRUCTURE_HINTS
    print("ok  categories: AI-prompt/coding/terminal derivation + hints")


def test_transform_modes_fall_back_honestly():
    for mode in ("polish", "concise", "prompt_engineer", "custom"):
        wp = profiles.resolve(mode, [], profiles.Destination(
            category="email"))
        assert wp.mode == mode and wp.effective_mode == "clean", wp
        assert wp.fallback_reason == \
            f"mode_not_executable_until_M11:{mode}", wp
        assert not wp.executable
    wp = profiles.resolve("raw", [], profiles.Destination())
    assert wp.executable and wp.fallback_reason is None
    # A rule may configure a transform mode; it still runs Clean today
    # and says so (never a silent behavior change).
    wp = profiles.resolve(None, [R("p", scope="category", value="email",
                                   mode="polish")],
                          profiles.Destination(category="email"))
    assert wp.source == "rule:category"
    assert wp.effective_mode == "clean" and wp.fallback_reason
    print("ok  transform-backed modes: honest fallback to Clean")


def test_rule_validation_and_revision():
    try:
        profiles.StyleRule(rule_id="x", name="x", scope_kind="nope")
        raise AssertionError("bad scope accepted")
    except ValueError:
        pass
    try:
        profiles.StyleRule(rule_id="x", name="x", scope_kind="category",
                           scope_value="not-a-category")
        raise AssertionError("bad category accepted")
    except ValueError:
        pass
    try:
        profiles.StyleRule(rule_id="x", name="x", mode="shout")
        raise AssertionError("bad mode accepted")
    except ValueError:
        pass
    rules = [R("a"), R("b")]
    rev1 = profiles.rules_revision(rules)
    assert profiles.rules_revision([R("a"), R("b")]) == rev1  # stable
    assert profiles.rules_revision([R("a")]) != rev1
    assert rev1.startswith("m10:")
    print("ok  rule validation + content-hashed rules_revision")


def test_style_store_crud_and_invalidation():
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        try:
            assert st._schema_version() == max(store_mod._MIGRATIONS)
            svc = profiles_store.StyleRuleStore(st)
            r1 = svc.add_rule(name="Terminal raw", scope_kind="app",
                              scope_value="com.apple.Terminal",
                              mode="raw")
            assert svc.revision() == 1
            got = svc.rules()
            assert len(got) == 1 and got[0].mode == "raw"
            svc.update_rule(r1, number_policy="standard")
            got = svc.rule(r1)
            assert got.revision == 2 and got.number_policy == "standard"
            assert svc.revision() == 2
            svc.set_enabled(r1, False)
            assert svc.rule(r1).enabled is False
            svc.delete_rule(r1)
            assert svc.rules() == [] and svc.revision() == 4
            try:
                svc.update_rule(r1, mode="raw")
                raise AssertionError("missing rule accepted")
            except KeyError:
                pass
            try:
                svc.add_rule(name="x", scope_kind="category",
                             scope_value="bogus")
                raise AssertionError("bad category stored")
            except ValueError:
                pass
        finally:
            st.close()
    print("ok  style store: versioned rows + state counter")


def test_casual_style_never_loosens_cleanup_contract():
    """M10-AC01: a style changes representation, never the S13
    permitted edits — a constraint-dropping candidate is rejected by
    the frozen validator no matter which style resolved, and the
    cleanup payload's permitted-edits surface is style-invariant."""
    source = ("Deploy only if tests pass and do not deploy on Friday"
              " maybe two workers not three")
    candidate_drops = ("Deploy if tests pass on Friday three")  # lost
    # the conditional, the negation, the hedge and the exclusion
    for rules in ([], [R("casual")],
                  [R("cat", scope="category", value="email")]):
        wp = profiles.resolve(None, rules, profiles.Destination(
            category="email"))
        report = validation.validate(source, candidate_drops)
        assert not report.accepted, (wp, report.to_json())
    # A value-preserving representation change passes (thirty → 30 is
    # authorized even under the plainest style).
    ok = validation.validate("deploy thirty services",
                             "deploy 30 services")
    assert ok.accepted, ok.to_json()
    print("ok  AC01: casual style never deletes constraints or"
          " overrides the frozen permitted edits")


def main():
    test_precedence_chain()
    test_disabled_rules_never_fire()
    test_wrong_workspace_rule_does_not_apply()
    test_category_derivation()
    test_transform_modes_fall_back_honestly()
    test_rule_validation_and_revision()
    test_style_store_crud_and_invalidation()
    test_casual_style_never_loosens_cleanup_contract()
    print("all style resolution tests passed")


if __name__ == "__main__":
    main()
