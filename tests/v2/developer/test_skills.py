"""EV-12 / M10: skill manifest discovery and the frozen registry
(Spec S17 "developer mode", contracts/profiles.md).

Discovery reads only explicitly configured paths — JSON manifests and
``<skill>/SKILL.md`` directories, frontmatter identity only, nothing
executed; workspace manifests are workspace-scoped and drop when the
workspace changes (the stale invalidation); collisions with dictionary
skills mask the alias; the frozen registry feeds the M04 layer-3 skill
grammar (AC03: registered /skills render exactly; unknown skills
invoke nothing).

Run: .venv/bin/python tests/v2/developer/test_skills.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.developer import skills  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot, NormalizationPolicy, normalize)


def make_skill_dir(root, name, frontmatter, body="instructions body"):
    d = pathlib.Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n{body}\n",
                                encoding="utf-8")
    return d


def test_discovery_reads_identity_only():
    with tempfile.TemporaryDirectory() as td:
        make_skill_dir(td, "brainstorm",
                       "name: brainstorm\naliases: idea storm, big idea")
        make_skill_dir(td, "code-review", "name: code-review")
        # A non-skill directory and a non-SKILL.md file are ignored.
        (pathlib.Path(td) / "notes").mkdir()
        (pathlib.Path(td) / "loose.md").write_text("x", encoding="utf-8")
        records = skills.discover([pathlib.Path(td)])
        assert [r.name for r in records] == ["brainstorm", "code-review"]
        b = records[0]
        assert b.aliases == ("idea storm", "big idea")
        assert b.source == "manifest" and b.manifest_revision
        # The registry exposes only identity: the SKILL.md body is
        # never part of any record or the registry JSON.
        reg = skills.SkillRegistry(records)
        assert "instructions body" not in json.dumps(reg.to_json())
        print("ok  discovery: frontmatter identity only, extras ignored")


def test_json_manifest_and_errors_degrade():
    with tempfile.TemporaryDirectory() as td:
        mf = pathlib.Path(td) / "manifest.json"
        mf.write_text(json.dumps(
            {"skills": [{"name": "deploy", "aliases": ["ship it"]}]}),
            encoding="utf-8")
        bad = pathlib.Path(td) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        records = skills.discover([mf, bad, pathlib.Path(td) / "missing"])
        assert [r.name for r in records] == ["deploy"]
        for bad_name in ("two words", ""):
            try:
                skills.SkillRecord(name=bad_name)
                raise AssertionError(f"name {bad_name!r} accepted")
            except ValueError:
                pass
        print("ok  JSON manifests; one bad source never aborts the rest")


def test_workspace_scoping_and_stale_invalidation():
    with tempfile.TemporaryDirectory() as td:
        ws_a = pathlib.Path(td) / "a"
        ws_b = pathlib.Path(td) / "b"
        make_skill_dir(ws_a, "ws-skill", "name: ws-skill")
        make_skill_dir(ws_b, "other-skill", "name: other-skill")
        recs_a = skills.discover([], [ws_a], "project-a")
        assert recs_a[0].scope == "workspace:project-a"
        recs_b = skills.discover([], [ws_b], "project-b")
        assert recs_b[0].scope == "workspace:project-b"
        assert recs_b[0].name == "other-skill"
        # The workspace change invalidates: the registry built from B's
        # records carries no A skill, and the stale flag records the
        # switch (the app rebuilds from the job's own workspace).
        reg = skills.SkillRegistry(recs_b, stale_workspace=True)
        assert reg.stale_workspace
        assert "ws-skill" not in reg.policy_skills
        assert reg.to_json()["stale_workspace"] is True
        # records_revision distinguishes the two manifest sets.
        assert skills.records_revision(recs_a) != skills.records_revision(
            recs_b)
        print("ok  workspace skills scoped + stale invalidation")


def test_dictionary_merge_and_collision_masking():
    with tempfile.TemporaryDirectory() as td:
        make_skill_dir(td, "brainstorm", "name: brainstorm")
        records = skills.discover([pathlib.Path(td)])
        reg = skills.SkillRegistry(
            records, {"code review": "code-review",
                      "brainstorm": "different-name"})
        # Same alias, two names → masked (unregistered), recorded.
        assert "brainstorm" not in reg.policy_skills
        assert reg.conflicts == ({
            "alias": "brainstorm",
            "names": ["brainstorm", "different-name"],
            "reason": "ambiguous_skill_alias"},)
        assert reg.policy_skills["code review"] == "code-review"
        assert reg.to_json()["dictionary_skill_aliases"] == 1
        print("ok  dictionary merge: collisions mask, never order")


def test_registered_skills_render_exactly_unknown_invoke_nothing():
    """AC03 through the M04 grammar: a manifest-sourced skill renders
    its exact token; an unknown skill stays literal with a retained
    review suggestion and invokes nothing."""
    with tempfile.TemporaryDirectory() as td:
        make_skill_dir(td, "code-review",
                       "name: code-review\naliases: review pass")
        reg = skills.SkillRegistry(skills.discover([pathlib.Path(td)]))
        pol = NormalizationPolicy(
            registered_skills=dict(reg.policy_skills))
        assert normalize("slash code review now", pol, None).text \
            == "/code-review now"
        assert normalize("slash review pass it", pol, None).text \
            == "/code-review it"
        res = normalize("slash unknown thing", pol, None)
        assert res.text == "slash unknown thing", res.text
        assert res.rejected and res.rejected[0].reason == "unknown_skill"
        # A multiword alias maps to the exact hyphenated name.
        assert reg.policy_skills["code review"] == "code-review"
        print("ok  AC03: exact render; unknown stays literal")


def test_manifest_edit_refreshes_registry():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        make_skill_dir(root, "brainstorm", "name: brainstorm")
        r1 = skills.discover([root])
        rev1 = skills.records_revision(r1)
        # Edit the manifest (new alias): the revision changes and the
        # next discovery picks it up — the refresh path.
        (root / "brainstorm" / "SKILL.md").write_text(
            "---\nname: brainstorm\naliases: idea storm\n---\nbody\n",
            encoding="utf-8")
        r2 = skills.discover([root])
        assert skills.records_revision(r2) != rev1
        assert r2[0].aliases == ("idea storm",)
        print("ok  manifest edit refreshes aliases + revision")


def main():
    test_discovery_reads_identity_only()
    test_json_manifest_and_errors_degrade()
    test_workspace_scoping_and_stale_invalidation()
    test_dictionary_merge_and_collision_masking()
    test_registered_skills_render_exactly_unknown_invoke_nothing()
    test_manifest_edit_refreshes_registry()
    print("all skill registry tests passed")


if __name__ == "__main__":
    main()
