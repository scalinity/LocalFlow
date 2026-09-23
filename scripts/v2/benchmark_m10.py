"""M10 benchmark: policy resolution + snippet matching on a 500-word
input, with adapter overhead reported separately (Spec S24 / M10
required benchmarks).

Measurements (all synthetic, no model calls, no network):

1. **Profile + snippet matching** — one ``normalize()`` pass over a
   500-word input under a fully populated M10 state (200 style rules,
   300 snippets with placeholders, a 50-skill manifest registry and a
   500-file resolver): p50/p95 over warm runs against the ≤25 ms P95
   budget. A plain-prose control (no triggers in the input) is
   measured beside it.
2. **Adapter overhead, separately** — the M10 per-job freeze costs the
   dictation path actually pays, measured apart from matching: style
   resolution over the rule set, snippet snapshot build, skill-registry
   construction, and the bounded workspace listing (500 files).

Usage: .venv/bin/python scripts/v2/benchmark_m10.py [out_dir]
"""

import json
import pathlib
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from localflow.v2 import profiles, snippets as snip_mod  # noqa: E402
from localflow.v2.developer import file_tags, skills  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot, NormalizationPolicy, normalize)

BUDGET_MS = 25.0
N_RULES = 200
N_SNIPPETS = 300
N_SKILLS = 50
N_FILES = 500
RUNS = 40

FILLER = ("alpha beta gamma delta epsilon zeta eta theta iota kappa"
          " lambda mu nu xi omicron pi rho sigma tau upsilon phi chi"
          " psi omega sample vector tensor matrix surface gradient"
          " token window buffer stream field table index cache page"
          " block frame layer node edge path graph tree list queue"
          " stack heap array").split()


def percentile(values, p):
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1,
                   int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


def letters(n: int) -> str:
    """Digits are not speakable trigger/alias tokens — a base-26
    letters-only ordinal keeps 300 unique triggers word-only."""
    out = ""
    while True:
        out = chr(97 + n % 26) + out
        n = n // 26 - 1
        if n < 0:
            return out


def build_state():
    rules = [profiles.StyleRule(
        rule_id=f"style-{i:04d}", name=f"rule {i}",
        scope_kind=("global" if i % 5 == 0 else
                    "app" if i % 5 == 1 else
                    "site" if i % 5 == 2 else
                    "workspace" if i % 5 == 3 else "category"),
        scope_value=(None if i % 5 == 0 else
                     f"com.example.app{i}" if i % 5 == 1 else
                     f"https://site{i}.example" if i % 5 == 2 else
                     f"workspace{i}" if i % 5 == 3 else
                     profiles.CATEGORIES[i % len(profiles.CATEGORIES)]),
        mode="raw" if i % 7 == 0 else "clean",
        number_policy="standard" if i % 11 == 0 else "inherit")
        for i in range(N_RULES)]
    snips = [snip_mod.Snippet(
        snippet_id=f"snip-{i:04d}",
        trigger=f"trigger {letters(i)} phrase",
        name=f"snippet {i}",
        content="Line one {{name}} and {{detail}}\nLine two fixed")
        for i in range(N_SNIPPETS)]
    skill_records = [skills.SkillRecord(
        name=f"skill-{i}", aliases=(f"alias {letters(i)}",),
        manifest_path=f"/synthetic/manifest-{i}.md",
        manifest_revision=f"{i:012x}")
        for i in range(N_SKILLS)]
    return rules, snips, skill_records


def main():
    out_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    tmp_ctx = tempfile.TemporaryDirectory()
    rules, snips, skill_records = build_state()
    try:
        # The adapter-side inputs: a populated listing for the resolver.
        root = pathlib.Path(tmp_ctx.name)
        for i in range(N_FILES):
            p = root / f"dir{i % 20}" / f"file{i:04d}.py"
            p.parent.mkdir(exist_ok=True)
            p.write_text("x", encoding="utf-8")
        files = file_tags.list_workspace_files(root)
        resolver = file_tags.FileTagResolver(
            files, document_name="dir0/file0000.py")
        registry = skills.SkillRegistry(skill_records)
        snapshot = snip_mod.SnippetSnapshot(snips)
        policy = NormalizationPolicy(
            registered_skills=dict(registry.policy_skills))
        ctx = ContextSnapshot(snippets=snapshot, file_resolver=resolver)
        dest = profiles.Destination(
            app_bundle="com.example.app1",
            site_origin="https://site2.example", workspace="workspace3",
            category="coding")

        # A 500-word input that fires snippet, skill and file-tag
        # grammars plus ordinary prose; and a plain-prose control.
        words = []
        while len(words) < 494:
            words.append(FILLER[len(words) % len(FILLER)])
        hit_input = " ".join(
            words[:100] + [f"trigger {letters(17)} phrase comma"
                           " Danny"]
            + words[100:200] + [f"slash alias {letters(9)}"]
            + words[200:300] + ["attach file dir0 slash file zero zero"
                                " zero zero dot py"]
            + words[300:])
        assert len(hit_input.split()) <= 520
        plain_input = " ".join(FILLER[i % len(FILLER)]
                               for i in range(500))

        # 1. Matching (budget path).
        matching = {}
        for label, text in (("hits", hit_input),
                            ("plain_500", plain_input)):
            # Warm caches first.
            for _ in range(5):
                normalize(text, policy, ctx)
            samples = []
            for _ in range(RUNS):
                t0 = time.perf_counter()
                normalize(text, policy, ctx)
                samples.append((time.perf_counter() - t0) * 1000.0)
            matching[label] = {
                "p50_ms": round(statistics.median(samples), 3),
                "p95_ms": round(percentile(samples, 95), 3),
                "max_ms": round(max(samples), 3),
                "runs": len(samples),
            }
            matching[label]["within_budget"] = \
                matching[label]["p95_ms"] <= BUDGET_MS

        # 2. Adapter overhead, separately (per-job freeze costs).
        adapter = {}
        for label, fn in (
                ("style_resolve_200_rules", lambda: profiles.resolve(
                    None, rules, dest)),
                ("snippet_snapshot_300", lambda: snip_mod.SnippetSnapshot(
                    snips)),
                ("skill_registry_50", lambda: skills.SkillRegistry(
                    skill_records)),
                ("workspace_listing_500_files", lambda:
                    file_tags.list_workspace_files(root)),
                ("file_resolve_hit", lambda: resolver.resolve(
                    ["dir0", "slash", "file", "zero", "zero", "zero",
                     "zero", "dot", "py"]))):
            for _ in range(3):
                fn()
            samples = []
            for _ in range(RUNS):
                t0 = time.perf_counter()
                fn()
                samples.append((time.perf_counter() - t0) * 1000.0)
            adapter[label] = {
                "p50_ms": round(statistics.median(samples), 3),
                "p95_ms": round(percentile(samples, 95), 3),
            }

        result = {
            "benchmark": "m10",
            "budget_ms": BUDGET_MS,
            "policy_snippet_matching": matching,
            "adapter_overhead_separate": adapter,
            "environment": {
                "python": sys.version.split()[0],
                "machine": "reference Mac (Apple M5 Pro 48GB)",
                "synthetic_state": {
                    "style_rules": N_RULES, "snippets": N_SNIPPETS,
                    "manifest_skills": N_SKILLS,
                    "workspace_files": len(files)},
            },
        }
        verbatim = json.dumps(result, indent=1, sort_keys=True)
        print(verbatim)
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "m10.json").write_text(verbatim + "\n",
                                              encoding="utf-8")
            print(f"\nwrote {out_dir / 'm10.json'}")
    finally:
        tmp_ctx.cleanup()


if __name__ == "__main__":
    main()
