"""M10 benchmark: style/snippet/skill/file work on the reference Mac,
measured only after every measured component is proven to have done its
work (M10-AUDIT-25).

Components (each timed separately; all synthetic, no model, no network):

- ``style_resolution`` — ``profiles.resolve`` over 200 mixed-scope rules
  (and a 200-rule same-scope cohort: the equal-authority tie path);
- ``snippet_snapshot`` — building the frozen registry of 300 snippets
  whose triggers all share their first word (the adversarial prefix);
- ``matching`` — one ``normalize()`` pass over a 500-word input carrying
  a slot snippet, an explicit slash skill and a file tag, under the full
  M10 state; beside it the same input and policy WITHOUT the M10
  registries (the M10 contribution is the difference) and a plain-prose
  control;
- ``manifest_discovery`` — cold discovery of 50 skill directories plus a
  JSON manifest (every byte read), and the warm fingerprint check the
  coordinator runs per job instead;
- ``file_listing`` — the bounded listing of a 500-file tree, and of a
  5,000-entry directory (the visit budget);
- ``file_resolution`` — a unique filename, and a duplicate basename;
- ``combined`` — the per-job M10 work a warm dictation pays
  (style resolve, fingerprint, registry build, listing, resolver build,
  M10-populated matching) and a cold first job (snapshot build and
  discovery included).

Work validity (independent oracles, written here from the fixture design
— never computed by the code under test): the resolved rule id, the
exact expansion text, the exact skill token, the exact filename, the
ambiguity of the duplicate basename, the discovered name set, the listing
count. Any failure exits 3 (INVALID WORK) before a timing is accepted.
Exit 0: valid and within budget; exit 2: valid, budget missed.

Test switches (the benchmark mutation check uses them):
  --noop COMPONENT      replace one component with a do-nothing stand-in
  --delay COMPONENT=MS  sleep inside that component's timed region
  --outside-delay MS    sleep OUTSIDE every timed region (must not move
                        any measured latency)

Usage: .venv/bin/python scripts/v2/benchmark_m10.py [--out DIR] [...]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from localflow.v2 import profiles, snippets as snip_mod  # noqa: E402
from localflow.v2.developer import file_tags, skills  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot, NormalizationPolicy, normalize)

BUDGET_MATCHING_P95_MS = 25.0
N_RULES = 200
N_SNIPPETS = 300
N_SKILLS = 50
N_FILES = 498             # + the duplicate-basename pair = the 500 cap
N_WIDE = 5000
N_DECOYS = 50             # same-first-word decoys in the adversarial input
RUNS = 200
WARM = 10

FILLER = ("alpha beta gamma delta epsilon zeta eta theta iota kappa"
          " lambda mu nu xi omicron pi rho sigma tau upsilon phi chi"
          " psi omega sample vector tensor matrix surface gradient"
          " token window buffer stream field table index cache page"
          " block frame layer node edge path graph tree list queue"
          " stack heap array").split()


def letters(n: int) -> str:
    """Base-26 letter ordinal: digits are not speakable word tokens."""
    out = ""
    while True:
        out = chr(97 + n % 26) + out
        n = n // 26 - 1
        if n < 0:
            return out


def pct(values, p):
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1,
                   int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


# ---- population (the independent oracle is built from this design) ------

HIT_SNIPPET = 17           # "trigger r phrase" → the slot snippet
HIT_SKILL = 9              # "alias j" → /skill-9
HIT_FILE_INDEX = 40        # "dira/fao.py", spoken "fao dot py"
WORKSPACE_WINNER = "style-0003"   # the only workspace rule for workspace3


def build_rules():
    return [profiles.StyleRule(
        rule_id=f"style-{i:04d}", name=f"rule {i}",
        scope_kind=("global" if i % 5 == 0 else "app" if i % 5 == 1 else
                    "site" if i % 5 == 2 else "workspace" if i % 5 == 3
                    else "category"),
        scope_value=(None if i % 5 == 0 else
                     f"com.example.app{i}" if i % 5 == 1 else
                     f"https://site{i}.example" if i % 5 == 2 else
                     f"workspace{i}" if i % 5 == 3 else
                     profiles.CATEGORIES[i % len(profiles.CATEGORIES)]),
        mode="raw" if i % 7 == 0 else "clean",
        number_policy="standard" if i % 11 == 0 else "inherit")
        for i in range(N_RULES)]


def build_same_scope_rules():
    return [profiles.StyleRule(
        rule_id=f"same-{i:04d}", name=f"same {i}", scope_kind="app",
        scope_value="com.example.same", mode="clean")
        for i in range(N_RULES)]


def build_snippets():
    return [snip_mod.Snippet(
        snippet_id=f"snip-{i:04d}", trigger=f"trigger {letters(i)} phrase",
        name=f"snippet {i}",
        content="Line one {{name}} and {{detail}}\nLine two fixed")
        for i in range(N_SNIPPETS)]


def expected_expansion():
    # The slot snippet is followed by "comma Ada comma Lin." — a
    # sentence end bounds the continuation (well under the 24-word cap).
    return "Line one Ada and Lin\nLine two fixed"


def build_files(root: pathlib.Path):
    names = []
    for i in range(N_FILES):
        d = root / f"dir{letters(i % 20)}"
        d.mkdir(exist_ok=True)
        name = f"f{letters(i)}.py"
        (d / name).write_text("x", encoding="utf-8")
        names.append(f"dir{letters(i % 20)}/{name}")
    # One duplicate basename pair for the ambiguity control.
    (root / "dira" / "dup.json").write_text("x", encoding="utf-8")
    (root / "dirb" / "dup.json").write_text("x", encoding="utf-8")
    return names


def build_skill_tree(root: pathlib.Path):
    skills_dir = root / "skills"
    for i in range(N_SKILLS):
        d = skills_dir / f"skill-{i}"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: skill-{i}\naliases: alias {letters(i)}\n---\n"
            + "body line\n" * 40, encoding="utf-8")
    manifest = root / "extra.json"
    manifest.write_text(json.dumps({"skills": [
        {"name": "json-skill", "aliases": ["json alias"]}]}),
        encoding="utf-8")
    return skills_dir, manifest


def hit_input(file_spoken, decoys=0):
    """500 words: a slot snippet bounded by its sentence end (far below
    the 24-word continuation cap), a slash skill at the START of a
    sentence (its command position — mid-sentence "slash" is the
    ordinary verb and stays literal) and a file tag with a letters-only
    name (spoken digits are not a filename form). ``decoys`` filler
    words become "trigger" — the first word of all 300 snippets,
    opening none of them — so each walks the whole first-word bucket:
    the prefix-sensitive matching cost, with the word count unchanged."""
    words = [FILLER[i % len(FILLER)] for i in range(483)]   # 500 in all
    for k in range(decoys):
        words[5 + 9 * k] = "trigger"
    words[299] += "."
    parts = (words[:150]
             + [f"trigger {letters(HIT_SNIPPET)} phrase comma Ada comma"
                f" Lin."]
             + words[150:300]
             + [f"Slash alias {letters(HIT_SKILL)} now."]
             + words[300:420]
             + [f"attach file {file_spoken} now."]
             + words[420:])
    return " ".join(parts)


# ---- measurement -------------------------------------------------------------

def measure(fn, runs, delay_s=0.0, outside_s=0.0):
    for _ in range(WARM):
        fn()
    samples = []
    for _ in range(runs):
        if outside_s:
            time.sleep(outside_s)
        t0 = time.perf_counter()
        fn()
        if delay_s:
            time.sleep(delay_s)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return {"p50_ms": round(pct(samples, 50), 4),
            "p95_ms": round(pct(samples, 95), 4),
            "p99_ms": round(pct(samples, 99), 4),
            "max_ms": round(max(samples), 4), "runs": len(samples)}


def environment(argv):
    def sh(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:
            return None
    power = sh("pmset", "-g", "batt") or ""
    sha = sh("git", "-C", str(ROOT), "rev-parse", "HEAD")
    dirty = sh("git", "-C", str(ROOT), "status", "--porcelain",
               "--untracked-files=no")
    prod_dirty = sh("git", "-C", str(ROOT), "status", "--porcelain",
                    "--untracked-files=no", "--", "localflow")
    mem = sh("sysctl", "-n", "hw.memsize")
    # The interpreter relative to the repository (or its name alone): a
    # committed record never carries the home folder's path.
    exe = pathlib.Path(sys.executable)
    try:
        exe_label = str(exe.relative_to(ROOT))
    except ValueError:
        exe_label = exe.name
    return {
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"),
        "code_sha": sha, "tracked_files_modified": bool(dirty),
        "production_tree_modified": bool(prod_dirty),
        "mac_model": sh("sysctl", "-n", "hw.model"),
        "chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "cores": os.cpu_count(),
        "memory_gib": round(int(mem) / 2 ** 30, 1) if mem else None,
        "macos": f"{platform.mac_ver()[0]} ({sh('sw_vers', '-buildVersion')})",
        "python": sys.version.split()[0], "executable": exe_label,
        "power_source": (power.splitlines()[0].split("'")[1]
                         if "'" in power else None),
        "load_avg_1_5_15": [round(x, 2) for x in os.getloadavg()],
        "command": " ".join([pathlib.Path(sys.executable).name,
                             "scripts/v2/benchmark_m10.py", *argv]),
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--noop", default=None)
    ap.add_argument("--delay", default=None)
    ap.add_argument("--outside-delay", type=float, default=0.0)
    ap.add_argument("--runs", type=int, default=RUNS)
    args = ap.parse_args(argv)
    noop = args.noop
    delay_comp, delay_s = None, 0.0
    if args.delay:
        delay_comp, ms = args.delay.split("=")
        delay_s = float(ms) / 1000.0
    outside_s = args.outside_delay / 1000.0

    def d(comp):
        return delay_s if comp == delay_comp else 0.0

    tmp = tempfile.TemporaryDirectory(prefix="lf-m10-bench-")
    root = pathlib.Path(tmp.name)
    validity = {}
    try:
        rules = build_rules()
        same = build_same_scope_rules()
        snippets = build_snippets()
        files_root = root / "ws"
        files_root.mkdir()
        file_names = build_files(files_root)
        skills_dir, manifest = build_skill_tree(root)
        wide = root / "wide"
        wide.mkdir()
        for i in range(N_WIDE):
            (wide / f"w{letters(i)}.txt").write_bytes(b"")
        target_file = file_names[HIT_FILE_INDEX]
        target_base = target_file.split("/")[1]
        file_spoken = f"{target_base[:-3]} dot py"
        dest = profiles.Destination(
            app_bundle="com.example.app1",
            site_origin="https://site2.example", workspace="workspace3",
            category="coding")
        same_dest = profiles.Destination(app_bundle="com.example.same")

        # Components (each replaceable by a no-op for the mutation check).
        def c_style():
            return profiles.resolve(None, rules, dest)

        def c_style_same():
            return profiles.resolve(None, same, same_dest)

        def c_snapshot():
            return snip_mod.SnippetSnapshot(snippets)

        def c_discover():
            return skills.discover_detailed([skills_dir, manifest])

        def c_fingerprint():
            return skills.fingerprint([skills_dir, manifest])

        def c_listing():
            return file_tags.list_workspace_files_bounded(files_root)

        def c_listing_wide():
            return file_tags.list_workspace_files_bounded(wide)

        listing = c_listing()
        resolver = file_tags.FileTagResolver(listing.names)

        def c_resolve():
            return resolver.resolve(file_spoken.split())

        def c_resolve_dup():
            return resolver.resolve(["dup", "dot", "json"])

        disc = c_discover()
        registry = skills.SkillRegistry(disc.records)
        snapshot = c_snapshot()
        policy = NormalizationPolicy(
            registered_skills=dict(registry.policy_skills))
        ctx = ContextSnapshot(snippets=snapshot, file_resolver=resolver)
        text = hit_input(file_spoken)
        text_prefix = hit_input(file_spoken, decoys=N_DECOYS)
        plain = " ".join(FILLER[i % len(FILLER)] for i in range(500))
        bare_policy = NormalizationPolicy()

        def c_match():
            return normalize(text, policy, ctx)

        def c_match_same_prefix():
            return normalize(text_prefix, policy, ctx)

        def c_match_without_m10():
            return normalize(text, bare_policy, ContextSnapshot())

        def c_match_plain():
            return normalize(plain, policy, ctx)

        components = {
            "style_resolution": c_style,
            "style_resolution_same_scope": c_style_same,
            "snippet_snapshot": c_snapshot,
            "manifest_discovery_cold": c_discover,
            "manifest_fingerprint_warm": c_fingerprint,
            "file_listing_500": c_listing,
            "file_listing_wide_5000": c_listing_wide,
            "file_resolution": c_resolve,
            "file_resolution_ambiguous": c_resolve_dup,
            "matching_500_words": c_match,
            "matching_500_words_same_prefix": c_match_same_prefix,
            "matching_500_words_without_m10": c_match_without_m10,
            "matching_plain_500": c_match_plain,
        }
        if noop:
            family = [k for k in components if k.startswith(noop)]
            if not family:
                raise SystemExit(f"unknown component: {noop}")
            for k in family:
                components[k] = (lambda: None)

        # ---- work validity (independent oracles) ------------------------
        def check(name, cond, detail):
            validity[name] = {"valid": bool(cond), "detail": detail}

        wp = components["style_resolution"]()
        check("style_resolution", getattr(wp, "rule_id", None)
              == WORKSPACE_WINNER,
              f"winner {getattr(wp, 'rule_id', None)} (expected"
              f" {WORKSPACE_WINNER}: the one workspace rule)")
        wps = components["style_resolution_same_scope"]()
        check("style_resolution_same_scope",
              getattr(wps, "rule_id", None) == "same-0000"
              and len(getattr(wps, "equal_authority_rule_ids", ()))
              == N_RULES - 1,
              f"winner {getattr(wps, 'rule_id', None)}, ties"
              f" {len(getattr(wps, 'equal_authority_rule_ids', ()))}")
        snap = components["snippet_snapshot"]()
        check("snippet_snapshot", snap is not None
              and len(getattr(snap, "index", {})) == N_SNIPPETS
              and len(snap.by_first_word().get("trigger", ()))
              == N_SNIPPETS,
              f"{len(getattr(snap, 'index', {}) or {})} triggers indexed,"
              " all sharing the first word")
        dd = components["manifest_discovery_cold"]()
        names = sorted(r.name for r in getattr(dd, "records", ()))
        want = sorted([f"skill-{i}" for i in range(N_SKILLS)]
                      + ["json-skill"])
        check("manifest_discovery_cold", names == want,
              f"{len(names)} records (expected {len(want)})")
        fp = components["manifest_fingerprint_warm"]()
        check("manifest_fingerprint_warm", fp == disc.fingerprint,
              "fingerprint equals the discovery's (the warm cache hit)")
        lst = components["file_listing_500"]()
        check("file_listing_500", lst is not None
              and len(lst.names) == N_FILES + 2
              and target_file in lst.names,
              f"{len(getattr(lst, 'names', ()))} names,"
              f" visited {getattr(lst, 'visited', None)}")
        wide_l = components["file_listing_wide_5000"]()
        check("file_listing_wide_5000", wide_l is not None
              and len(wide_l.names) == file_tags.LISTING_CAP
              and wide_l.visited <= file_tags.LISTING_VISIT_BUDGET
              and wide_l.truncated,
              f"{len(getattr(wide_l, 'names', ()))} names, visited"
              f" {getattr(wide_l, 'visited', None)} (budget"
              f" {file_tags.LISTING_VISIT_BUDGET})")
        res = components["file_resolution"]()
        check("file_resolution", getattr(res, "filename", None)
              == target_file, f"resolved {getattr(res, 'filename', None)}")
        amb = components["file_resolution_ambiguous"]()
        check("file_resolution_ambiguous",
              getattr(amb, "status", None) == "ambiguous"
              and len(getattr(amb, "candidates", ())) == 2,
              f"status {getattr(amb, 'status', None)}")
        m = components["matching_500_words"]()
        out = getattr(m, "text", "") or ""
        cls = {e.cls for e in getattr(m, "edits", ())}
        check("matching_500_words",
              expected_expansion() in out
              and f"/skill-{HIT_SKILL} now." in out
              and f"{target_file} now." in out
              and {"snippet", "skill", "file_tag"} <= cls,
              f"edit classes {sorted(cls)}")
        ms = components["matching_500_words_same_prefix"]()
        out_s = getattr(ms, "text", "") or ""
        n_exp = sum(1 for e in getattr(ms, "edits", ())
                    if e.cls == "snippet")
        n_lit = out_s.split().count("trigger")
        check("matching_500_words_same_prefix",
              n_exp == 1 and expected_expansion() in out_s
              and n_lit == N_DECOYS,
              f"{n_exp} expansion(s), {n_lit} decoys kept literal"
              f" (expected 1 and {N_DECOYS})")
        m0 = components["matching_500_words_without_m10"]()
        check("matching_500_words_without_m10",
              m0 is not None and not ({"snippet", "skill", "file_tag"}
                                      & {e.cls for e in m0.edits}),
              "same input, no M10 registries: no M10 edits")
        mp = components["matching_plain_500"]()
        check("matching_plain_500",
              mp is not None and mp.text == plain,
              "plain prose control unchanged")

        work_valid = all(v["valid"] for v in validity.values())
        result = {
            "benchmark": "m10", "schema_version": 2,
            "environment": environment(argv),
            "population": {"style_rules": N_RULES,
                           "same_scope_rules": N_RULES,
                           "snippets_same_first_word": N_SNIPPETS,
                           "skill_dirs": N_SKILLS, "json_manifests": 1,
                           "workspace_files": N_FILES + 2,
                           "wide_directory_entries": N_WIDE,
                           "input_words": len(text.split()),
                           "same_prefix_input_words":
                               len(text_prefix.split()),
                           "same_prefix_decoys": N_DECOYS},
            "validity": validity, "work_valid": work_valid,
            "switches": {"noop": noop, "delay": args.delay,
                         "outside_delay_ms": args.outside_delay},
        }
        if not work_valid:
            result["timing"] = None
            result["qualified"] = False
            result["verdict"] = "INVALID_WORK"
            _emit(result, args.out)
            return 3

        timing = {}
        for name, fn in components.items():
            timing[name] = measure(fn, args.runs if "matching" in name
                                   or "style" in name or "resolution" in name
                                   else max(40, args.runs // 5),
                                   d(name), outside_s)
        m10_delta = round(timing["matching_500_words"]["p95_ms"]
                          - timing["matching_500_words_without_m10"]
                          ["p95_ms"], 4)

        # Combined per-job M10 work: warm (caches valid) and cold.
        def job_warm():
            components["style_resolution"]()
            components["manifest_fingerprint_warm"]()
            skills.SkillRegistry(disc.records)
            file_tags.FileTagResolver(components["file_listing_500"]()
                                      .names)
            components["matching_500_words"]()

        def job_cold():
            components["style_resolution"]()
            components["snippet_snapshot"]()
            skills.SkillRegistry(
                components["manifest_discovery_cold"]().records)
            file_tags.FileTagResolver(components["file_listing_500"]()
                                      .names)
            components["matching_500_words"]()
        timing["combined_job_warm"] = measure(job_warm, max(40,
                                                            args.runs // 4),
                                              0.0, outside_s)
        timing["combined_job_cold"] = measure(job_cold, max(40,
                                                            args.runs // 4),
                                              0.0, outside_s)
        budgeted = ("matching_500_words", "matching_500_words_same_prefix")
        within = all(timing[k]["p95_ms"] <= BUDGET_MATCHING_P95_MS
                     for k in budgeted)
        result.update({
            "timing": timing,
            "m10_matching_contribution_p95_ms": m10_delta,
            "budget": {"matching_500_words_p95_ms": BUDGET_MATCHING_P95_MS,
                       "budgeted_components": list(budgeted),
                       "within_budget": within,
                       "note": "the budget applies to the M10-populated"
                               " normalization pass (policy/snippet"
                               " matching) on the ordinary and the"
                               " adversarial same-first-word input;"
                               " adapter work (listing, discovery,"
                               " registry) is reported separately and in"
                               " the combined job"},
            "qualified": within,
            "verdict": "VALID_WITHIN_BUDGET" if within
            else "VALID_BUDGET_MISSED",
        })
        _emit(result, args.out)
        return 0 if within else 2
    finally:
        tmp.cleanup()


def _emit(result, out):
    text = json.dumps(result, indent=1, sort_keys=True)
    print(text)
    if out:
        p = pathlib.Path(out)
        p.mkdir(parents=True, exist_ok=True)
        (p / "m10.json").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
