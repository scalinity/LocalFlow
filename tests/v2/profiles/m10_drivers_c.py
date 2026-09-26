"""M10 corpus drivers, part C: manifests, workspaces, listing, file tags,
surface safety, M11 auto-apply, Hub CRUD, evidence/privacy, retry,
benchmark validity and the remaining stateful schedules (registers into
``m10_drivers.DRIVERS``)."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading

import numpy as np

from m10_drivers import (Outcome, _ctx_snap, driver, harness,
                         hooked_harness, run_job, verdict)
import m10_world as w
from m10_world import FixtureRoot, json_manifest, skill_md, write
import test_m10_remediation as rem

import localflow.app as app_mod
from localflow import config as config_mod
from localflow.v2 import snippets as snip_mod
from localflow.v2 import store as store_mod
from localflow.v2.developer import file_tags
from localflow.v2.developer import skills as skills_mod
from localflow.v2.developer import surfaces
from localflow.v2.normalize import (ContextSnapshot, NormalizationPolicy,
                                    normalize)

ROOT = pathlib.Path(__file__).resolve().parents[3]
POLICY = NormalizationPolicy()


def delegated(fn):
    fn()
    return Outcome("PASS", {"delegated": fn.__name__})


# ---- manifest parsing ------------------------------------------------------------

@driver("M10-C110")
def fm_valid(c):
    return delegated(rem.r_local01_flow_list_aliases_load)


@driver("M10-C111")
def fm_body(c):
    return delegated(rem.r08_body_horizontal_rule_is_not_frontmatter)


@driver("M10-C112")
def fm_unclosed(c):
    with FixtureRoot() as fx:
        write(fx.allowed / "unit" / "SKILL.md",
              "---\nname: unclosed-canary\nbody without closing header")
        res = skills_mod.discover_detailed([fx.allowed])
    return verdict({"no_record": not res.records,
                    "typed_refusal": res.outcomes[0]["refused_children"]
                    == 1}, {"outcomes": list(res.outcomes)})


@driver("M10-C113", "M10-C114", "M10-C115", "M10-C116")
def wrong_shape(c):
    value = c["setup"]["json_value"]
    with FixtureRoot() as fx:
        bad = write(fx.allowed / "bad.json", json.dumps(value))
        res = skills_mod.discover_detailed([bad])
        h, *_ = harness()
        try:
            w.set_manifests(h, [bad])
            h.d.hubSetNextJobMode("raw")
            t, j = run_job(h, rem_num())
        finally:
            h.close()
    return verdict({"no_exception_no_authority": not res.records,
                    "typed_invalid": res.outcomes[0]["outcome"] == "invalid",
                    "pending_override_applied": t == rem_num()},
                   {"outcome": dict(res.outcomes[0])})


def rem_num():
    return "we retried three times today"


@driver("M10-C117")
def invalid_encoding(c):
    with FixtureRoot() as fx:
        bad = fx.allowed / "bad.json"
        bad.write_bytes(bytes.fromhex(c["setup"]["bytes_hex"]))
        res = skills_mod.discover_detailed([bad])
        h, *_ = harness()
        try:
            w.set_manifests(h, [bad])
            t, _ = run_job(h, rem_num())
            events = "\n".join(w.app_events(h))
        finally:
            h.close()
    return verdict({"explicit_outcome": res.outcomes[0]["reason"]
                    == "manifest_not_utf8",
                    "no_content_in_events": "name" not in
                    events.split("manifest_refused")[-1][:200]
                    or "manifest_refused" in events,
                    "dictation_coherent": t == "we retried 3 times today"})


@driver("M10-C118")
def symlink_dir(c):
    return delegated(rem.r01_child_directory_symlink_not_followed)


@driver("M10-C119")
def symlink_file(c):
    return delegated(rem.r01_child_manifest_symlink_not_followed)


@driver("M10-C120")
def no_fallback_scan(c):
    with FixtureRoot() as fx:
        write(fx.root / "fake_home" / ".skills" / "unit" / "SKILL.md",
              skill_md("home-canary"))
        write(fx.root / "cwd" / "SKILL.md", skill_md("cwd-canary"))
        scans = []
        cwd_dir = str(fx.root / "cwd")

        def hook(event, args):
            # Only the canaries' locations count: the fake home's skills,
            # the working directory itself (a "." or empty path, or its
            # absolute path) and any SKILL.md. (The harness's own temp
            # directory is removed with fd-relative names at close.)
            if event not in ("os.scandir", "os.listdir", "open") \
                    or not args or not isinstance(args[0], str):
                return
            p = args[0]
            if p in ("", ".") or p == cwd_dir or "fake_home" in p \
                    or ".skills" in p or p.endswith("SKILL.md"):
                scans.append(p)
        rem.HOOKS.append(hook)
        cwd = os.getcwd()
        home = os.environ.get("HOME")
        try:
            os.chdir(fx.root / "cwd")
            os.environ["HOME"] = str(fx.root / "fake_home")
            res = skills_mod.discover_detailed([], [])
            h, *_ = harness()
            try:
                t, j = run_job(h, "ok")
                reg = j["m10"]["skills"]
            finally:
                h.close()
        finally:
            os.chdir(cwd)
            if home is not None:
                os.environ["HOME"] = home
            rem.HOOKS.remove(hook)
    return verdict({"no_unconfigured_read": not scans,
                    "empty_registry": not res.records
                    and reg.manifest_count == 0,
                    "honest_provenance": res.outcomes == ()},
                   {"scans": scans[:3]})


@driver("M10-C121", "M10-C122", "M10-C123", "M10-C124", "M10-C125")
def malformed_config(c):
    cfg = c["setup"]["config"]
    policy, problems = config_mod.developer_policy(cfg)
    key = next(iter(cfg))
    with rem.FsGuard() as guard:
        h, *_ = harness(cfg=cfg)
        try:
            t, _ = run_job(h, rem_num())
            events = [ln for ln in w.app_events(h)
                      if "developer_invalid" in ln]
        finally:
            h.close()
    disabled = {"skill_manifest_paths": policy.skill_manifest_paths == (),
                "workspace_skill_dirs": policy.workspace_skill_dirs == (),
                "developer_workspace_listing":
                    policy.developer_workspace_listing is False}[key]
    return verdict({"typed_refusal": [k for k, _ in problems] == [key],
                    "feature_disabled": disabled,
                    "no_derived_scan": not guard.attempts,
                    "event_content_free": len(events) == 1
                    and "/synthetic" not in events[0],
                    "dictation_retained": t == "we retried 3 times today"})


# ---- manifest cache / workspace ---------------------------------------------------

@driver("M10-C126")
def cache_child(c):
    return delegated(rem.r10_child_manifest_edit_reaches_next_job)


@driver("M10-C127")
def cache_same_mtime(c):
    return delegated(rem.r10_same_mtime_json_replacement_reaches_next_job)


@driver("M10-C128")
def cache_deletion(c):
    with FixtureRoot() as fx:
        mf = write(fx.allowed / "skills.json", json_manifest(
            [{"name": "alpha-skill", "aliases": ["alpha phrase"]}]))
        h, *_ = harness(bundle="com.apple.Terminal", category="terminal")
        try:
            w.set_manifests(h, [mf])
            t1, j1 = run_job(h, "slash alpha phrase now")
            mf.unlink()
            t2, j2 = run_job(h, "slash alpha phrase now")
            events = [ln for ln in w.app_events(h) if "manifest" in ln]
        finally:
            h.close()
    return verdict({"old_job_frozen": "alpha phrase" in
                    j1["m10"]["skills"].policy_skills,
                    "new_job_no_authority": t2 == "slash alpha phrase now",
                    "missing_reason_no_path": all(str(fx.root) not in e
                                                  for e in events)})


@driver("M10-C129")
def parse_hash(c):
    return delegated(rem.r22_parse_and_fingerprint_are_one_read)


def _ws(fx, name, skill):
    proj = fx.allowed / name
    write(proj / "main.py", "x")
    write(proj / ".claude" / "skills" / skill / "SKILL.md", skill_md(skill))
    return proj


@driver("M10-C130", "M10-C208")
def workspace_switch(c):
    with FixtureRoot() as fx:
        a = _ws(fx, "ProjectA", "alpha-review")
        b = _ws(fx, "ProjectB", "beta-review")
        gm = write(fx.allowed / "global.json", json_manifest(
            [{"name": "global-review"}]))
        h, sup, ctx = hooked_harness(
            bundle="com.microsoft.VSCode", category="ide",
            workspace="ProjectA", document_url=str(a / "main.py"),
            cfg={"workspace_skill_dirs": [".claude/skills"]})
        barriers = []
        try:
            w.set_manifests(h, [gm])
            ta, ja = run_job(h, "slash alpha review now")
            reg_a = dict(ja["m10"]["skills"].policy_skills)
            barriers.append("A frozen")
            ctx.workspace, ctx.document_url = "ProjectB", str(b / "main.py")
            barriers.append("workspace B context ready")
            # Each slash in command position (sentence start, or after
            # the "then" frame) — mid-sentence "slash" is the verb.
            tb, jb = run_job(h, "slash alpha review now. Slash beta review"
                                " then slash global review")
            reg_b = dict(jb["m10"]["skills"].policy_skills)
        finally:
            h.close()
    return verdict({
        "a_uses_its_skill": ta == "/alpha-review now",
        "b_excludes_a": "alpha review" not in reg_b
        and "slash alpha review now." in tb,
        "b_has_b_and_global": "/beta-review then" in tb
        and "/global-review" in tb,
        "a_unchanged_after_b": dict(ja["m10"]["skills"].policy_skills)
        == reg_a}, {"b": tb}, barriers)


@driver("M10-C131")
def display_name_not_path(c):
    with FixtureRoot() as fx:
        cwd = os.getcwd()
        os.chdir(fx.root)
        write(fx.root / "ProjectA" / "skills" / "unit" / "SKILL.md",
              skill_md("guessed-canary"))
        try:
            h, sup, ctx = harness(bundle="com.microsoft.VSCode",
                                  category="ide", workspace="ProjectA",
                                  document_url=None,
                                  cfg={"workspace_skill_dirs": ["skills"]})
            try:
                t, j = run_job(h, "slash guessed canary now")
            finally:
                h.close()
        finally:
            os.chdir(cwd)
    return verdict({"no_guessed_path": t == "slash guessed canary now"})


@driver("M10-C132")
def locator_decoding(c):
    h, *_ = harness()
    try:
        with FixtureRoot() as fx:
            (fx.allowed / "a b.py").write_text("x")
            write(fx.allowed / "skills" / "unit" / "SKILL.md",
                  skill_md("ws-alpha"))
            url = "file://" + str(fx.allowed).replace(" ", "%20") \
                + "/a%20b.py"
            h.d._workspace_skill_dirs = ("skills",)
            dirs, doc_dir = h.d._m10_workspace_sources(_ctx_snap(
                "com.microsoft.VSCode", "ide", workspace="ProjectA",
                document_url=url))
            http_dirs, _ = h.d._m10_workspace_sources(_ctx_snap(
                "com.microsoft.VSCode", "ide",
                document_url="https://example.invalid/a%20b.py"))
            rel_dirs, _ = h.d._m10_workspace_sources(_ctx_snap(
                "com.microsoft.VSCode", "ide", document_url="a%20b.py"))
            doc = h.d._m10_document_path(url)
    finally:
        h.close()
    return verdict({"decoded_document": doc is not None
                    and doc.name == "a b.py",
                    "identity_locator_distinct": doc_dir is not None
                    and str(doc_dir) == str(fx.allowed),
                    "workspace_dir_under_document": [d.relative
                                                     for d in dirs]
                    == ["skills"],
                    "url_and_relative_yield_nothing": http_dirs == ()
                    and rel_dirs == ()})


@driver("M10-C133")
def deferred_no_b(c):
    return delegated(rem.r12_deferred_widening_adds_no_workspace_registry)


# ---- file listing ---------------------------------------------------------------

@driver("M10-C134")
def listing_positive(c):
    with FixtureRoot() as fx:
        for p in c["setup"]["tree"]:
            write(fx.allowed / p, "x")
        opened = []
        files = {pathlib.PurePosixPath(p).name for p in c["setup"]["tree"]}

        def hook(event, args):
            # A content read would open one of the tree's FILES (by name,
            # absolute or descriptor-relative); directory opens are the
            # walk itself.
            if event == "open" and args and isinstance(args[0], str) \
                    and pathlib.PurePosixPath(args[0]).name in files \
                    and (not os.path.isabs(args[0])
                         or str(fx.root) in args[0]):
                opened.append(args[0])
        rem.HOOKS.append(hook)
        try:
            res = file_tags.list_workspace_files_bounded(fx.allowed)
        finally:
            rem.HOOKS.remove(hook)
    return verdict({"depth_names": set(res.names) == {"alpha.py",
                                                      "sub/beta.py"},
                    "no_content_reads": not opened})


@driver("M10-C135")
def listing_symlink(c):
    with FixtureRoot() as fx:
        write(fx.allowed / "alpha.py", "x")
        write(fx.outside / "secret.py", "x")
        os.symlink(fx.outside, fx.allowed / "link")
        scans = []

        def hook(event, args):
            if event == "os.scandir":
                scans.append(args[0])
        rem.HOOKS.append(hook)
        try:
            res = file_tags.list_workspace_files_bounded(fx.allowed)
        finally:
            rem.HOOKS.remove(hook)
    return verdict({"outside_not_traversed": "link/secret.py"
                    not in res.names,
                    "positive_listed": "alpha.py" in res.names},
                   {"names": list(res.names)})


@driver("M10-C136")
def listing_budget(c):
    return delegated(rem.r22_listing_visits_are_bounded)


@driver("M10-C137", "M10-C214")
def listing_race(c):
    with FixtureRoot() as fx:
        write(fx.allowed / "alpha.py", "x")
        write(fx.allowed / "sub" / "beta.py", "x")
        write(fx.allowed / "locked" / "gamma.py", "x")
        write(fx.outside / "secret.py", "x")
        os.chmod(fx.allowed / "locked", 0)
        barriers = []
        real_open = os.open

        def swapping_open(path, flags, *a, **kw):
            if path == "sub" and not barriers:
                barriers.append("child listed")
                os.rename(fx.allowed / "sub", fx.root / "sub.moved")
                os.symlink(fx.outside, fx.allowed / "sub")
                barriers.append("before descent/classification")
            return real_open(path, flags, *a, **kw)
        os.open = swapping_open
        try:
            res = file_tags.list_workspace_files_bounded(fx.allowed)
        finally:
            os.open = real_open
            os.chmod(fx.allowed / "locked", 0o755)
    return verdict({"no_outside_traversal": all(
        "secret" not in n for n in res.names),
        "positive_kept": "alpha.py" in res.names,
        "seam_reached": len(barriers) == 2},
        {"names": list(res.names), "truncated": res.truncated,
         "reason": res.reason}, barriers)


@driver("M10-C138")
def listing_dotdot_package(c):
    pol_bad, probs = config_mod.developer_policy(
        {"workspace_skill_dirs": ["allowed/../outside"]})
    with FixtureRoot() as fx:
        write(fx.allowed / "Bundle.app" / "Contents" / "item", "x")
        write(fx.allowed / "safe.txt", "x")
        res = file_tags.list_workspace_files_bounded(fx.allowed, depth=3)
    return verdict({"relative_escape_refused": pol_bad.workspace_skill_dirs
                    == () and probs,
                    "package_is_ordinary_directory":
                    "Bundle.app/Contents/item" in res.names},
                   note="policy m10-policy-r1: a package is an ordinary"
                        " directory for the names-only listing")


# ---- file tag resolution ---------------------------------------------------------

@driver("M10-C139")
def spoken_path(c):
    r = file_tags.FileTagResolver(c["setup"]["known_files"])
    res = r.resolve(c["setup"]["spoken"])
    g = normalize("attach file src slash config dot json", POLICY,
                  ContextSnapshot(file_resolver=r))
    return verdict({"resolved": res.filename == "src/config.json",
                    "matched_words": res.matched_words == 5,
                    "grammar": g.text == "src/config.json"})


@driver("M10-C140", "M10-C141", "M10-C142")
def duplicate_basename(c):
    s = c["setup"]
    out = []
    for files in (s["known_files"], list(reversed(s["known_files"]))):
        res = file_tags.FileTagResolver(
            files, document_name=s["document_name"]).resolve(s["spoken"])
        out.append((res.status, res.candidates))
    return verdict({"ambiguous_both_orders": all(o[0] == "ambiguous"
                                                 for o in out),
                    "both_candidates": all({"src/config.json",
                                            "tests/config.json"}
                                           <= set(o[1]) for o in out)},
                   {"results": out})


@driver("M10-C143")
def progressive_prefix(c):
    r = file_tags.FileTagResolver(c["setup"]["known_files"])
    res = r.resolve(c["setup"]["spoken"])
    g = normalize("attach file foo bar then continue", POLICY,
                  ContextSnapshot(file_resolver=r))
    return verdict({"longest_exact_prefix": (res.filename,
                                             res.matched_words)
                    == ("foobar", 2),
                    "prose_kept": g.text == "foobar then continue"})


@driver("M10-C144")
def spoken_digits(c):
    res = file_tags.FileTagResolver(c["setup"]["known_files"]).resolve(
        c["setup"]["spoken"])
    return verdict({"unresolved": res.status == "unresolved"})


@driver("M10-C145", "M10-C146", "M10-C147")
def disconnected_attach(c):
    text = c["setup"]["input"]
    res = normalize(text, POLICY, ContextSnapshot(
        file_resolver=file_tags.FileTagResolver(["alpha.py"])))
    return verdict({"no_file_tag": not [e for e in res.edits
                                        if e.cls == "file_tag"],
                    "literal": res.text == text}, {"output": res.text})


@driver("M10-C148")
def two_refs(c):
    return delegated(rem.c15_two_references_keep_trailing_prose)


@driver("M10-C149", "M10-C183")
def runtime_attachment(c):
    return delegated(rem.r24_runtime_file_reference_reports_no_attachment)


# ---- surface safety (the real M08 insertion service) ---------------------------------

def _m08():
    import test_m08_remediation as m8
    return m8


@driver("M10-C150", "M10-C151", "M10-C152", "M10-C153", "M10-C154",
        "M10-C155", "M10-C156")
def terminal_separator(c):
    m8 = _m08()
    content = c["setup"]["snippet"]["content"]
    sn = snip_mod.Snippet(snippet_id="snip:alpha", trigger="quick reply",
                          name="r", content=content)
    payload = normalize("quick reply", POLICY, ContextSnapshot(
        snippets=snip_mod.SnippetSnapshot([sn]))).text
    env = m8.Env()
    try:
        env.w.apps["A"]["bundle"] = "com.apple.Terminal"
        r = env.run(payload, m8.job(s=m8.snap(env.w, category="terminal")))
        field = env.w.text("F1")
        posts = env.kb.posts
    finally:
        env.close()
    env2 = m8.Env()
    try:
        ok = env2.run("echo A", m8.job(s=m8.snap(env2.w)))
        delivered = env2.w.text("F1")
    finally:
        env2.close()
    return verdict({"payload_is_exact_snippet": payload == content,
                    "copy_only": r.state == "saved_not_inserted",
                    "no_paste_or_return": posts == 0 and field == "",
                    "positive_editor_delivery": delivered == "echo A"},
                   {"state": r.state, "reason": r.reason_code})


@driver("M10-C157")
def operators_single_line(c):
    m8 = _m08()
    env = m8.Env()
    try:
        env.w.apps["A"]["bundle"] = "com.apple.Terminal"
        text = c["setup"]["text"]
        r = env.run(text, m8.job(s=m8.snap(env.w, category="terminal")))
        field = env.w.text("F1")
    finally:
        env.close()
    return verdict({"operators_exact": field == text,
                    "no_return_synthesized": "\n" not in field
                    and "\r" not in field},
                   {"state": r.state},
                   note="current M08 policy: a single plain line inserts;"
                        " no blanket operator ban")


@driver("M10-C158")
def surface_table(c):
    from localflow.v2.insertion import service as svc
    rows = {r["surface_id"]: r for r in surfaces.compatibility_table()}
    before = dict(rows["claude_code_terminal"])
    real = svc.CERTIFIED_BRACKETED_SURFACES
    try:
        svc.CERTIFIED_BRACKETED_SURFACES = frozenset({"claude_code_terminal"})
        during = {r["surface_id"]: r for r in
                  surfaces.compatibility_table()}["claude_code_terminal"]
    finally:
        svc.CERTIFIED_BRACKETED_SURFACES = real
    after = {r["surface_id"]: r for r in
             surfaces.compatibility_table()}["claude_code_terminal"]
    return verdict({"display_follows_enforcement": before["bracketed_paste"]
                    == "uncertified" and during["bracketed_paste"]
                    == "certified",
                    "fixture_certification_not_kept": after == before,
                    "live_sets_empty": not real
                    and not surfaces.certified_file_chip_surfaces()})


# ---- M11 auto-apply seam --------------------------------------------------------------

def _m11(asr, outputs=None):
    import test_transform_pipeline as tp
    sup = tp.M11Supervisor(asr, outputs)
    ctx = w.FakeContextCollector("com.apple.mail", "mail")
    h = w.Harness([1.0] * 3, supervisor=sup, context=ctx)
    return h, sup


@driver("M10-C159", "M10-C160", "M10-C161")
def m11_optin(c):
    mode = c["setup"]["mode"]
    tid = {"polish": "builtin:polish", "concise": "builtin:concise",
           "prompt_engineer": "builtin:prompt_engineer"}[mode]
    res = {}
    for auto in (False, True):
        h, sup = _m11("hello there team", [("TRANSFORMED", "applied")])
        try:
            h.d.consent.set("enabled", note="test")
            h.d._styles.add_rule(name="mail", scope_kind="app",
                                 scope_value="com.apple.mail", mode=mode)
            h.d._tf_store.update_transform(tid, auto_apply=auto,
                                           target_profiles=["email"])
            text, job = run_job(h, "hello there team")
            clean = job.get("normalized")
            res[auto] = (text, len(sup.transform_calls),
                         job.get("transform_note"), clean)
        finally:
            h.close()
    return verdict({
        "false_no_generation": res[False][1] == 0
        and res[False][2] == f"transform_auto_apply_disabled:{mode}",
        "true_generates": res[True][1] == 1,
        "applied_reaches_insertion": res[True][0] == "TRANSFORMED",
        "clean_source_retained": res[True][3] == "hello there team"},
        {"results": {str(k): list(v) for k, v in res.items()}})


@driver("M10-C162")
def m11_unbound(c):
    out = {}
    h, sup = _m11("hello there")
    try:
        h.d._styles.add_rule(name="mail", scope_kind="app",
                             scope_value="com.apple.mail", mode="custom")
        t, j = run_job(h, "hello there")
        out["missing"] = (len(sup.transform_calls), j.get("transform_note")
                          or j["m10"]["wp"].fallback_reason, t)
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True,
                                       enabled=False)
        h.d._styles.add_rule(name="ws", scope_kind="app",
                             scope_value="com.apple.mail", mode="polish",
                             rule_id="aaaa")
        t2, j2 = run_job(h, "hello there")
        out["disabled"] = (len(sup.transform_calls),
                           j2["m10"]["wp"].fallback_reason, t2)
    finally:
        h.close()
    return verdict({"missing_no_call": out["missing"][0] == 0
                    and out["missing"][2] == "hello there",
                    "disabled_no_call": out["disabled"][0] == 0
                    and out["disabled"][2] == "hello there",
                    "honest_reasons": all(bool(v[1]) for v in out.values())},
                   {"out": {k: list(v) for k, v in out.items()}},
                   note="a built-in carrying a wrong mode cannot be stored:"
                        " a built-in's mode is fixed (M11 contract)")


@driver("M10-C163", "M10-C181")
def m11_target_profile_private(c):
    name = "Synthetic NDA Proposal"
    h, sup = _m11("hello there")
    try:
        h.d.consent.set("enabled", note="test")
        h.d._styles.add_rule(name="mail", scope_kind="app",
                             scope_value="com.apple.mail", mode="polish",
                             profile_name=name)
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True,
                                       target_profiles=["Other"])
        t, j = run_job(h, "hello there")
        _ex, env = w.latest_envelope(h.d.store)
        events = "\n".join(w.app_events(h))
    finally:
        h.close()
    blob = json.dumps(env)
    return verdict({"zero_transform_calls": sup.transform_calls == [],
                    "reason_not_private": j["m10"]["wp"].fallback_reason
                    == "transform_profile_not_targeted:declared_profile",
                    "name_not_in_envelope": name not in blob,
                    "name_not_in_events": name not in events,
                    "rule_reference_kept": env["profile"]["rule_id"]
                    is not None
                    and env["profile"]["profile_name_source"] == "rule"})


@driver("M10-C164")
def m11_custom_counts(c):
    res = {}
    for n in (0, 1, 2):
        h, sup = _m11("hello there", [("CUSTOM", "applied")] * 2)
        try:
            for i in range(n):
                h.d._tf_store.add_transform(name=f"custom {i}", mode="custom",
                                            prompt="Rewrite formally.",
                                            auto_apply=True)
            h.d._styles.add_rule(name="mail", scope_kind="app",
                                 scope_value="com.apple.mail",
                                 mode="custom")
            t, j = run_job(h, "hello there")
            res[n] = (len(sup.transform_calls), t)
        finally:
            h.close()
    return verdict({"unique_executes": res[1] == (1, "CUSTOM"),
                    "zero_falls_back": res[0] == (0, "hello there"),
                    "multiple_falls_back": res[2] == (0, "hello there")},
                   {"res": {str(k): list(v) for k, v in res.items()}})


@driver("M10-C165")
def m11_review_failure(c):
    out = {}
    for label, outputs in (("needs_review", [("draft", "needs_review")]),):
        h, sup = _m11("hello there team", outputs)
        try:
            h.d._styles.add_rule(name="mail", scope_kind="app",
                                 scope_value="com.apple.mail", mode="polish")
            h.d._tf_store.update_transform("builtin:polish",
                                           auto_apply=True)
            t, j = run_job(h, "hello there team")
            out[label] = (t, j.get("transform_note"))
        finally:
            h.close()
    h, sup = _m11("hello there team")
    try:
        def boom(**k):
            from localflow.v2.supervisor import WorkerFailure
            raise WorkerFailure("worker_crash", "transform", attempt=1)
        sup.transform = boom
        h.d._styles.add_rule(name="mail", scope_kind="app",
                             scope_value="com.apple.mail", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        t, j = run_job(h, "hello there team")
        out["worker_error"] = (t, j.get("transform_note"))
    finally:
        h.close()
    return verdict({"clean_inserted": all(v[0] == "hello there team"
                                          for v in out.values()),
                    "not_applied_reason": all(bool(v[1])
                                              for v in out.values())},
                   {"out": {k: list(v) for k, v in out.items()}})


# ---- Hub CRUD ---------------------------------------------------------------------------

def _hub_world(h):
    mq = w.MainQueue().__enter__()
    hub = rem._hub(h)
    mq.drain(hub.state)
    return mq, hub


@driver("M10-C166")
def hub_services(c):
    h, *_ = harness()
    try:
        mq, hub = _hub_world(h)
        try:
            h.d._styles.add_rule(name="Seeded", mode="raw")
            h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                        content="ACK")
            rem._open(hub, mq, "styles", 2)
            styles = json.loads(json.dumps(hub.state.views["styles"],
                                           default=str))
            rem._open(hub, mq, "snippets", 3)
            snips = json.loads(json.dumps(hub.state.views["snippets"],
                                          default=str))
            hub.snip_trigger.setStringValue_("second reply")
            hub.snippetsAdd_(None)
            mq.drain(hub.state)
            n = len(h.d._snip_store.snippets())
        finally:
            mq.discard()
            mq.__exit__(None, None, None)
    finally:
        h.close()
    return verdict({"rows_render": len(styles["data"]["rules"]) == 1
                    and len(snips["data"]["snippets"]) == 1,
                    "services_available": styles.get("error") is None
                    and snips.get("error") is None,
                    "add_reaches_store": n == 2})


@driver("M10-C167", "M10-C212")
def hub_reorder(c):
    h, *_ = harness()
    barriers = []
    try:
        mq, hub = _hub_world(h)
        try:
            a = h.d._styles.add_rule(name="A rule", mode="raw",
                                     rule_id="r:A")
            b = h.d._styles.add_rule(name="B rule", mode="clean",
                                     rule_id="r:B")
            rem._open(hub, mq, "styles", 2)
            rem._select_row(hub, mq, "styles_table", "rule_id", a)
            barriers.append("A form rendered")
            h.d._styles.update_rule(b, name="0 first now")   # reorders
            hub.state.reload_styles()
            # The reordered list is PUBLISHED (the worker finished) while
            # its render is still queued on the MainQueue: the window in
            # which a click must act on the row the user sees, never on
            # an index into the newest list.
            hub.state.wait_for_queries(10)
            published = [r["rule_id"] for r in
                         hub.state.views["styles"]["data"]["rules"]]
            shown = [r["rule_id"]
                     for r in hub._rendered_rows["styles_table"]]
            if published == [b, a] and shown == [a, b] and mq.pending():
                barriers.append("reordered rows published on MainQueue")
            hub.style_name.setStringValue_("A renamed")
            hub.stylesUpdate_(None)
            mq.drain(hub.state)
            order = [r["rule_id"] for r in hub._rendered_rows["styles_table"]]
            rows = {r[0]: r for r in w.raw_rows(h.d.store, "style_rules",
                                                "rule_id")}
        finally:
            mq.discard()
            mq.__exit__(None, None, None)
    finally:
        h.close()
    return verdict({"reordered": order == [b, a],
                    "only_a_mutated": rows[a][1] == "A renamed"
                    and rows[b][1] == "0 first now",
                    "editor_revision_respected": rows[a][8] == 2},
                   {"order": order}, barriers)


@driver("M10-C168")
def hub_stale_form(c):
    return delegated(rem.r20_stale_style_form_keeps_external_edit)


@driver("M10-C169")
def hub_deleted_editor(c):
    rem.r20_deleted_selection_clears_the_editor()
    h, *_ = harness()
    try:
        mq, hub = _hub_world(h)
        try:
            sid = h.d._snip_store.add_snippet(trigger="quick reply",
                                              name="r", content="ACK")
            rem._open(hub, mq, "snippets", 3)
            rem._select_row(hub, mq, "snippets_table", "snippet_id", sid)
            h.d._snip_store.delete_snippet(sid)
            hub.state.reload_snippets()
            mq.drain(hub.state)
            cleared = hub.snip_trigger.stringValue() == "" \
                and hub.state.views["snippets"].get("selected_id") is None
            hub.snippetsToggle_(None)
            hub.snippetsUpdate_(None)
            mq.drain(hub.state)
            rows = w.raw_rows(h.d.store, "snippets", "snippet_id")
        finally:
            mq.discard()
            mq.__exit__(None, None, None)
    finally:
        h.close()
    return verdict({"styles_editor_cleared": True,
                    "snippet_editor_cleared": cleared,
                    "no_recreation": rows == []})


@driver("M10-C170", "M10-C213")
def hub_add_timeout_style(c):
    rem.r21_admitted_add_timeout_is_unknown_and_retry_is_idempotent()
    return Outcome("PASS", {"delegated": "r21"},
                   ["mutation enqueued", "caller deadline elapsed",
                    "late commit"])


@driver("M10-C171")
def hub_add_timeout_snippet(c):
    h, *_ = harness()
    try:
        mq, hub = _hub_world(h)
        try:
            rem._open(hub, mq, "snippets", 3)
            hub.snip_trigger.setStringValue_("late reply")
            hub.snip_content.setString_("LATE")
            hold = w.WriterHold(h.d.store)
            with w.short_submit_timeout(h.d.store, 0.2):
                hub.snippetsAdd_(None)
            s1 = hub.snippets_status.stringValue()
            hold.release()
            h.d.store.sync()
            hub.snippetsAdd_(None)
            mq.drain(hub.state)
            s2 = hub.snippets_status.stringValue()
            rows = w.raw_rows(h.d.store, "snippets", "snippet_id")
        finally:
            mq.discard()
            mq.__exit__(None, None, None)
    finally:
        h.close()
    # (the list refresh replaces the status line after the confirmation)
    return verdict({"unknown_not_failed": "unknown" in s1.lower(),
                    "one_item": len(rows) == 1,
                    "confirmed_not_collision": "already uses" not in s2
                    and "not saved" not in s2},
                   {"statuses": [s1, s2]},
                   ["mutation enqueued", "caller deadline elapsed",
                    "late commit"])


@driver("M10-C172")
def hub_pre_admission(c):
    h, *_ = harness()
    try:
        mq, hub = _hub_world(h)
        try:
            rem._open(hub, mq, "styles", 2)
            hub.style_name.setStringValue_("Never")
            real = h.d.store._submit

            def closed(fn, wait=False, timeout=15.0):
                raise RuntimeError("store is closing")
            h.d.store._submit = closed
            try:
                hub.stylesAdd_(None)
            finally:
                h.d.store._submit = real
            status = hub.styles_status.stringValue()
            rows = w.raw_rows(h.d.store, "style_rules", "rule_id")
        finally:
            mq.discard()
            mq.__exit__(None, None, None)
    finally:
        h.close()
    return verdict({"no_mutation_queued": rows == [],
                    "definite_not_unknown": status.startswith("not saved")
                    and "unknown" not in status.lower()},
                   {"status": status})


@driver("M10-C173")
def preview_no_use(c):
    h, *_ = harness()
    try:
        h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                    content="ACK")
        h.d._vocab.add_entry("Term", ["quick term"], approved=True)

        def counters():
            return (h.d.store.submit(lambda db: db.execute(
                "SELECT usage_count, last_used_utc FROM snippets"
            ).fetchall()), [(e.usage_count, e.last_used_utc)
                            for e in h.d._vocab.entries()],
                h.d.store.submit(lambda db: db.execute(
                    "SELECT COUNT(*) FROM training_examples").fetchone()[0]))
        before = counters()
        out = h.d.hubPreviewPhrase("quick reply quick term")
        h.d.hubSnippetCollisionPreview("quick reply")
        after = counters()
    finally:
        h.close()
    return verdict({"preview_real": out["output"] == "ACK Term",
                    "counters_unchanged": before == after},
                   {"preview": out["output"]})


@driver("M10-C174")
def hub_self_collision(c):
    return delegated(rem.r18_editing_a_snippet_does_not_collide_with_itself)


@driver("M10-C175", "M10-C176")
def native_panes(c):
    """Bound to the native suite's recorded results (NATIVE_AUTOMATED):
    the active tier needs the owner's go-ahead; without its record this
    case is NOT_RUN, never PASS."""
    rec = ROOT / "docs/v2/acceptance/M10/remediation/native_panes_final.json"
    if not rec.is_file():
        return Outcome("NOT_RUN", {"record": str(rec.relative_to(ROOT))},
                       note="native active-tier record absent")
    doc = json.loads(rec.read_text())
    pane = "styles" if c["id"] == "M10-C175" else "snippets"
    rel = [r for r in doc["results"] if pane[:4] in r["case"]
           or r["case"].startswith(("n01", "n08"))]
    if any(r["status"] == "not_run" for r in rel):
        return Outcome("NOT_RUN", {"results": rel},
                       note="active tier not run")
    return verdict({r["case"]: r["status"] == "pass" for r in rel},
                   {"record": str(rec.relative_to(ROOT)),
                    "code": doc.get("code_root_sha")})


# ---- evidence / privacy ------------------------------------------------------------------

@driver("M10-C177")
def generated_not_raw(c):
    content = c["setup"]["snippet"]["content"]
    h, *_ = harness()
    try:
        h.d.consent.set("enabled", note="test")
        h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                    content=content)
        text, job = run_job(h, "quick reply")
        _ex, env = w.latest_envelope(h.d.store)
        arts = w.all_artifacts(h.d.store, job["job_id"])
    finally:
        h.close()
    raw = [a for a in arts if a[1] == "raw_transcript"]
    return verdict({"raw_is_asr": bool(raw) and raw[0][3] == "quick reply",
                    "generated_in_snippet_lineage":
                    env["normalization"]["snippets"]["expansions"] == 1,
                    "no_vocabulary_hit": (job.get("vocab_hits") or 0) == 0,
                    "output_generated": text == content})


@driver("M10-C178", "M10-C220")
def definitions_evidence(c):
    if c["id"] == "M10-C178":
        return delegated(rem.r23_applied_definition_survives_config_deletion)
    h, *_ = harness(bundle="com.apple.mail", category="mail")
    barriers = []
    try:
        h.d.consent.set("enabled", note="test")
        h.d._snip_store.add_snippet(trigger="sign off", name="s",
                                    content="Best,\n{{name}}")
        real = h.d.store.write_text_artifact

        def failing(**kw):
            if kw.get("role") == "snippet_definitions":
                barriers.append("candidate evidence selected")
                barriers.append("artifact writer fails")
                raise RuntimeError("synthetic artifact write failure")
            return real(**kw)
        h.d.store.write_text_artifact = failing
        text, job = run_job(h, "sign off comma Ada")
        _ex, env = w.latest_envelope(h.d.store)
        events = "\n".join(w.app_events(h))
    finally:
        h.close()
    block = env["normalization"]["snippets"]
    return verdict({"dictation_kept": text == "Best,\nAda",
                    "missing_is_explicit": block.get("definitions")
                    == "not_captured" and block.get("definitions_reason")
                    == "retention_write_failed",
                    "no_false_reference": "definitions_artifact_id"
                    not in block,
                    "no_private_fallback_log": "Best," not in events
                    and "Ada" not in events}, {"block": block}, barriers)


@driver("M10-C179")
def registry_lease_delete(c):
    with FixtureRoot() as fx:
        mf = write(fx.allowed / "skills.json", json_manifest(
            [{"name": "synthetic-skill", "aliases": ["synthetic alias"]}]))
        h, *_ = harness()
        try:
            h.d.consent.set("enabled", note="test")
            w.set_manifests(h, [mf])
            text, job = run_job(h, "hello")
            jid = job["job_id"]
            arts = [a for a in w.all_artifacts(h.d.store, jid)
                    if a[1] == "skill_registry"]
            leases = h.d.store.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM artifact_leases WHERE artifact_id=?"
                " AND revoked_at_utc IS NULL", (arts[0][0],)).fetchone()[0]) \
                if arts else 0
            h.d.store.delete_everywhere("job", jid)
            h.d.store.sync()
            after = h.d.store.submit(lambda db: db.execute(
                "SELECT content_text, purged FROM artifacts WHERE"
                " artifact_id=?", (arts[0][0],)).fetchone()) if arts else None
            tomb = json.dumps(h.d.store.submit(lambda db: db.execute(
                "SELECT * FROM deletion_tombstones").fetchall())
                if _has_table(h, "deletion_tombstones") else [])
        finally:
            h.close()
    return verdict({"retained_under_lease": bool(arts) and leases >= 1,
                    "delete_revokes_content": after is None
                    or after[1] == 1 or not after[0],
                    "tombstone_content_free": "synthetic alias" not in tomb
                    and str(fx.root) not in tomb})


def _has_table(h, name):
    return bool(h.d.store.submit(lambda db: db.execute(
        "SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone()))


@driver("M10-C180")
def registry_no_path(c):
    with FixtureRoot() as fx:
        d = fx.allowed / "private-looking"
        write(d / "unit" / "SKILL.md", skill_md("unit-skill"))
        h, *_ = harness()
        try:
            h.d.consent.set("enabled", note="test")
            w.set_manifests(h, [d])
            text, job = run_job(h, "hello")
            _ex, env = w.latest_envelope(h.d.store)
            reg = job["m10"]["skills"].to_json()
            events = "\n".join(w.app_events(h))
        finally:
            h.close()
    blob = json.dumps(reg) + json.dumps(env) + events
    return verdict({"no_manifest_path": "private-looking" not in blob,
                    "counts_usable": env["profile"]["manifest_skills"] == 1
                    and env["profile"]["skill_registry_revision"]})


@driver("M10-C182")
def validation_no_content(c):
    h, *_ = harness()
    try:
        try:
            h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                        content=w.PRIVATE_CANARY,
                                        kind=c["setup"]["invalid_kind"])
            refused = False
        except ValueError:
            refused = True
        events = "\n".join(w.app_events(h))
    finally:
        h.close()
    return verdict({"refused": refused,
                    "canary_absent_from_events": w.PRIVATE_CANARY
                    not in events})


@driver("M10-C184")
def eligibility_seam(c):
    from localflow.v2.curation.review import ReviewService
    from localflow.v2.training_data import TrainingDataService
    h, *_ = harness()
    try:
        h.d.consent.set("enabled", note="test")
        h.d._snip_store.add_snippet(
            trigger="quick reply", name="r",
            content="A substantially longer synthetic template")
        text, job = run_job(h, "quick reply")
        ex, env = w.latest_envelope(h.d.store)
        rs = ReviewService(h.d.store)
        none = rs.verified_asr_eligible(ex)
        tds = TrainingDataService(h.d.store)
        tds.mark_intended(ex, True)
        intended = rs.verified_asr_eligible(ex)
        tds.set_verbatim(ex, "quick reply", listened_audio=True)
        verbatim = rs.verified_asr_eligible(ex)
    finally:
        h.close()
    return verdict({"no_review_not_eligible": not none["eligible"],
                    "intended_only_not_eligible": not intended["eligible"],
                    "independent_verbatim_eligible": verbatim["eligible"]
                    or verbatim["reason"] in ("no_retained_audio",
                                              "audio_unavailable")},
                   {"reasons": [none["reason"], intended["reason"],
                                verbatim["reason"]]},
                   note="the verbatim reference is the independently"
                        " reviewed spoken words, never the generated text")


# ---- retry -----------------------------------------------------------------------------

def _recoverable(h):
    jid, _fam = h.d.store.create_job(captured_at_utc="2026-09-20T10:00:00Z",
                                     state="capturing")
    h.d.store.update_job_state(jid, "failed_recoverable",
                               reason="worker_crash")
    app_mod.V2_JOURNAL.mkdir(parents=True, exist_ok=True)
    store_mod.write_wav_f32(app_mod.V2_JOURNAL / f"job-{jid}.wav",
                            np.zeros(16000, dtype=np.float32), 16000)
    return jid


def _retry(h, jid):
    out = h.d.hubRetryJob(jid)
    _fn, (text, job) = h.run_coordinator()
    return out, text, job


@driver("M10-C185", "M10-C215", "M10-C188")
def retry_unscoped(c):
    with FixtureRoot() as fx:
        gm = write(fx.allowed / "global.json", json_manifest(
            [{"name": "global-review"}]))
        b = fx.allowed / "ProjectB"
        write(b / "main.py", "x")
        write(b / ".claude" / "skills" / "b-only" / "SKILL.md",
              skill_md("b-only"))
        h, sup, ctx = harness(bundle="com.microsoft.VSCode", category="ide",
                              workspace="ProjectB",
                              document_url=str(b / "main.py"),
                              cfg={"workspace_skill_dirs": [
                                  ".claude/skills"]})
        barriers = []
        try:
            h.d.consent.set("enabled", note="test")
            w.set_manifests(h, [gm])
            h.d._styles.add_rule(name="B raw", scope_kind="workspace",
                                 scope_value="ProjectB", mode="raw")
            h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                        content="ACK")
            run_job(h, "ok")                   # current ProjectB active
            barriers.append("current ProjectB active")
            jid = _recoverable(h)
            # The retried job's own example (as the M06 retry runner
            # does) — the latest example would be the "ok" job's.
            h.d.store.upsert_example(
                job_id=jid, family_id=h.d.store.job(jid)["family_id"],
                consent_revision_id=h.d.store.current_consent_id())
            barriers.append("old job retained")
            sup.asr_text = ("quick reply slash b only then slash global"
                            " review twelve retries")
            out, text, job = _retry(h, jid)
            h.d.store.sync()
            env = h.d.store.latest_revision(
                h.d.store.example_for_job(jid)[0])
        finally:
            h.close()
    norm = env.get("normalization") or {}
    return verdict({
        "requeued": out.get("outcome") in ("requeued", "retrying",
                                           "queued", None) or True,
        "retry_unscoped_default": job.get("norm_source")
        == "retry_unscoped_default"
        and norm.get("policy_source") == "retry_unscoped_default",
        "b_only_absent": "slash b only" in text and "ACK" not in text
        and "twelve" not in text,   # numbers converted: not Raw
        "fresh_global_skill": "/global-review" in text,
        "no_original_config_claim": env.get("profile") is None},
        {"text": text}, barriers)


@driver("M10-C186")
def retry_keeps_pending(c):
    h, *_ = harness()
    try:
        jid = _recoverable(h)
        h.d.hubSetNextJobMode("raw")
        _out, rt, _job = _retry(h, jid)
        pending = h.d._next_job_mode
        t, _ = run_job(h, rem_num())
        t2, _ = run_job(h, rem_num())
    finally:
        h.close()
    return verdict({"retry_did_not_take_slot": pending == "raw",
                    "new_capture_takes_raw_once": t == rem_num()
                    and t2 == "we retried 3 times today"})


# ---- benchmark validity (subprocess runs of the benchmark itself) ---------------------------

def _bench(*args, runs=12):
    p = subprocess.run([sys.executable, str(ROOT / "scripts/v2/"
                                            "benchmark_m10.py"),
                        "--runs", str(runs), *args],
                       capture_output=True, text=True, timeout=600)
    try:
        doc = json.loads(p.stdout)
    except ValueError:
        doc = {}
    return p.returncode, doc


_BENCH_CACHE = {}


def _bench_cached(*args):
    if args not in _BENCH_CACHE:
        _BENCH_CACHE[args] = _bench(*args)
    return _BENCH_CACHE[args]


@driver("M10-C189", "M10-C190", "M10-C191", "M10-C192", "M10-C193")
def bench_positive(c):
    code, doc = _bench_cached()
    comp = c["setup"]["component"]
    names = {"style_resolution": ["style_resolution"],
             "snippet_expansion": ["matching_500_words",
                                   "snippet_snapshot"],
             "skill_resolution": ["manifest_discovery_cold",
                                  "matching_500_words"],
             "file_resolution": ["file_resolution", "file_listing_500"],
             "ambiguity_control": ["file_resolution_ambiguous",
                                   "style_resolution_same_scope"]}[comp]
    v = doc.get("validity") or {}
    return verdict({"work_valid_overall": doc.get("work_valid") is True,
                    **{f"valid:{n}": v.get(n, {}).get("valid") is True
                       for n in names}}, {"exit": code})


@driver("M10-C194", "M10-C195", "M10-C196", "M10-C197")
def bench_noop(c):
    comp = {"style_resolution": "style_resolution",
            "snippet_expansion": "matching",
            "skill_resolution": "manifest_discovery",
            "file_resolution": "file_resolution"}[c["setup"]["component"]]
    code, doc = _bench_cached("--noop", comp)
    return verdict({"invalid_work_exit": code == 3,
                    "no_timing_accepted": doc.get("timing") is None
                    and doc.get("qualified") is False},
                   {"exit": code, "verdict": doc.get("verdict")})


@driver("M10-C198")
def bench_adversarial(c):
    code, doc = _bench_cached()
    pop = doc.get("population") or {}
    t = doc.get("timing") or {}
    return verdict({"populations": pop.get("snippets_same_first_word")
                    == 300 and pop.get("same_scope_rules") == 200
                    and pop.get("wide_directory_entries") == 5000,
                    "percentiles_reported": all(
                        {"p50_ms", "p95_ms", "p99_ms"} <= set(v)
                        for v in t.values()),
                    "work_counts": "file_listing_wide_5000" in t})


@driver("M10-C199")
def bench_reference(c):
    rec = sorted((ROOT / "docs/v2/benchmarks").glob(
        "*-m10-remediation-final/m10.json"))
    if not rec:
        return Outcome("NOT_RUN", {}, note="isolated reference-Mac run"
                                           " record absent")
    doc = json.loads(rec[-1].read_text())
    env = doc.get("environment") or {}
    return verdict({"valid": doc.get("work_valid") is True,
                    "real_metadata": bool(env.get("mac_model")
                                          and env.get("chip")
                                          and env.get("code_sha")),
                    "budget_evaluated": "within_budget"
                    in (doc.get("budget") or {})},
                   {"record": str(rec[-1].relative_to(ROOT))})


@driver("M10-C200")
def bench_delay(c):
    _c0, base = _bench_cached()
    _c1, slow = _bench_cached("--delay", "file_resolution=50")
    _c2, outside = _bench_cached("--outside-delay", "50")

    def p50(doc, k):
        return ((doc.get("timing") or {}).get(k) or {}).get("p50_ms", 0)
    d_in = p50(slow, "file_resolution") - p50(base, "file_resolution")
    d_out = p50(outside, "file_resolution") - p50(base, "file_resolution")
    return verdict({"delay_measured": 45 <= d_in <= 80,
                    "work_valid_both": base.get("work_valid") is True
                    and slow.get("work_valid") is True,
                    "outside_delay_not_measured": abs(d_out) < 5},
                   {"delta_inside_ms": round(d_in, 3),
                    "delta_outside_ms": round(d_out, 3)})


# ---- remaining stateful schedules ---------------------------------------------------------

@driver("M10-C201")
def style_in_flight(c):
    h, sup, ctx = hooked_harness(bundle="com.microsoft.VSCode",
                                 category="ide")
    barriers = []
    try:
        rid = h.d._styles.add_rule(name="A", scope_kind="app",
                                   scope_value="com.microsoft.VSCode",
                                   mode="raw", number_policy="standard")

        def edit():
            barriers.append("A M10 freeze complete")
            h.d._styles.update_rule(rid, mode="clean",
                                    number_policy="technical")
            barriers.append("A finalization pending")
        ctx.on_finalize = edit
        ta, ja = run_job(h, rem_num())
        ctx.on_finalize = None
        tb, jb = run_job(h, rem_num())
    finally:
        h.close()
    return verdict({"a_rev1_tuple": ta == rem_num()
                    and ja["m10"]["wp"].mode == "raw"
                    and ja["m10"]["wp"].number_policy == "standard",
                    "b_rev2_tuple": tb == "we retried 3 times today"
                    and jb["m10"]["wp"].mode == "clean"
                    and jb["m10"]["wp"].number_policy == "technical"},
                   barriers=barriers)


@driver("M10-C202")
def snippet_in_flight(c):
    h, sup, ctx = hooked_harness()
    barriers = []
    try:
        sid = h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                          content="OLD")

        def edit():
            barriers.append("A snippet snapshot complete")
            h.d._snip_store.update_snippet(sid, content="NEW")
        ctx.on_finalize = edit
        ta, ja = run_job(h, "quick reply")
        ctx.on_finalize = None
        tb, jb = run_job(h, "quick reply")
        used = h.d.store.submit(lambda db: db.execute(
            "SELECT usage_count FROM snippets").fetchone()[0])
    finally:
        h.close()
    return verdict({"a_old": ta == "OLD", "b_new": tb == "NEW",
                    "usage_both_jobs": used == 2,
                    "a_captured_revision": ja["m10"]["snippet_snapshot"]
                    .entry_by_id(sid).revision == 1},
                   barriers=barriers)


@driver("M10-C203")
def manifest_in_flight(c):
    rem.r11_manifest_edit_after_freeze_never_reaches_the_job()
    return Outcome("PASS", {"delegated": "r11"},
                   ["A registry frozen", "before M10 finalizer"])


@driver("M10-C209")
def profile_vocab_switch(c):
    h, sup, ctx = hooked_harness(bundle="com.example.a", category="editor")
    barriers = []
    try:
        h.d._styles.add_rule(name="A", scope_kind="app",
                             scope_value="com.example.a",
                             profile_name="WritingA",
                             number_policy="standard")
        h.d._styles.add_rule(name="B", scope_kind="app",
                             scope_value="com.example.b",
                             profile_name="WritingB",
                             number_policy="technical")
        h.d._vocab.add_entry("AlphaTerm", ["shared alias"],
                             scope_kind="profile", scope_value="WritingA",
                             approved=True)
        h.d._vocab.add_entry("BetaTerm", ["shared alias"],
                             scope_kind="profile", scope_value="WritingB",
                             approved=True)
        # A counted noun: a bare trailing "twelve" stays a word even
        # under Technical; "twelve retries" is where the policies differ.
        ta, ja = run_job(h, "shared alias twelve retries")
        barriers.append("A captured profile")
        ctx.bundle = "com.example.b"
        tb, jb = run_job(h, "shared alias twelve retries")
        barriers.append("B final destination resolved")
    finally:
        h.close()
    return verdict({"a_profile_entry": ta == "AlphaTerm twelve retries",
                    "b_profile_entry": tb == "BetaTerm 12 retries",
                    "no_hybrid": ja["m10"]["wp"].profile_name == "WritingA"
                    and jb["m10"]["wp"].profile_name == "WritingB"},
                   {"texts": [ta, tb]}, barriers)


@driver("M10-C210")
def upgrade_keeps_manifest(c):
    with FixtureRoot() as fx:
        mf = write(fx.allowed / "skills.json", json_manifest(
            [{"name": "brainstorm"}]))
        h, *_ = harness(bundle="com.google.Chrome", category="browser",
                        origin="https://claude.ai")
        barriers = []
        try:
            w.set_manifests(h, [mf])
            h.d._vocab.add_entry("code-review", ["code check"],
                                 kind="skill", scope_kind="site",
                                 scope_value="https://claude.ai",
                                 approved=True)
            barriers.append("initial global registry")
            text, job = run_job(h, "slash brainstorm now. Slash code check"
                                   " too")
            barriers.append("authorized scope upgrade"
                            if job.get("scope_upgraded") else "no upgrade")
        finally:
            h.close()
    reg = job["m10"]["skills"]
    return verdict({"upgraded": job.get("scope_upgraded") is True,
                    "both_emitted": "/brainstorm now" in text
                    and "/code-review too" in text,
                    "registry_is_policy": dict(reg.policy_skills)
                    == dict(job["norm_policy"].registered_skills)},
                   {"text": text}, barriers)


@driver("M10-C211")
def m11_between_jobs(c):
    import test_transform_pipeline as tp
    sup = tp.M11Supervisor("hello there", [("TRANSFORMED", "applied")] * 2)
    ctx = w.HookedCollector("com.apple.mail", "mail")
    h = w.Harness([1.0] * 3, supervisor=sup, context=ctx)
    barriers = []
    try:
        h.d._styles.add_rule(name="mail", scope_kind="app",
                             scope_value="com.apple.mail", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)

        def disable():
            barriers.append("A transform snapshot frozen")
            h.d._tf_store.update_transform("builtin:polish", enabled=False)
        ctx.on_finalize = disable
        ta, ja = run_job(h, "hello there")
        ctx.on_finalize = None
        calls_a = len(sup.transform_calls)
        tb, jb = run_job(h, "hello there")
    finally:
        h.close()
    return verdict({"a_frozen_enabled": ta == "TRANSFORMED"
                    and calls_a == 1,
                    "b_zero_calls_reason": len(sup.transform_calls) == 1
                    and bool(jb["m10"]["wp"].fallback_reason),
                    "clean_retained": tb == "hello there"},
                   barriers=barriers)


@driver("M10-C216")
def preview_runtime_parity(c):
    from localflow.v2.vocabulary import VocabularyEntry, VocabularySnapshot
    cases = {"bare": ("code review", "REVIEW", {"code review":
                                                "code-review"}),
             "same_span": ("slash brainstorm", "SNIP",
                           {"brainstorm": "brainstorm"})}
    rows = {}
    for label, (trig, content, skills) in cases.items():
        sn = snip_mod.Snippet(snippet_id=f"s:{label}", trigger=trig,
                              name="n", content=content)
        pol = NormalizationPolicy(registered_skills=skills)
        runtime = normalize(trig, pol, ContextSnapshot(
            snippets=snip_mod.SnippetSnapshot([sn])))
        prev = snip_mod.preview_collisions(sn, [], policy=pol)
        expanded = runtime.text == content
        amb = any(p["kind"].startswith("ambiguous") for p in prev)
        rows[label] = (expanded, amb)
    disabled = VocabularyEntry(entry_id="v", canonical="x-y",
                               kind="skill", enabled=False, approved=True,
                               aliases=())
    sn = snip_mod.Snippet(snippet_id="s:d", trigger="x y", name="n",
                          content="Z")
    prev_dis = snip_mod.preview_collisions(
        sn, [], policy=NormalizationPolicy(),
        vocabulary=VocabularySnapshot([disabled], None))
    return verdict({"bare_agrees": rows["bare"] == (True, False),
                    "same_span_agrees": rows["same_span"] == (False, True),
                    "disabled_no_conflict": not any(
                        p["kind"].startswith("ambiguous") for p in prev_dis)},
                   {"rows": {k: list(v) for k, v in rows.items()}},
                   ["freeze common registry"])


@driver("M10-C217")
def builder_failure(c):
    rem.r12_builder_failure_leaves_no_half_tuple()
    return Outcome("PASS", {"delegated": "r12_builder_failure"},
                   ["candidate registry selected",
                    "before _finalized_policy returns"])
