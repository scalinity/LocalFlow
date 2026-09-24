"""M01-AC03/AC04: registry traceability tests.

Re-derives requirements and suites from the canonical Markdown (Spec S05,
Evaluation E08) and cross-checks docs/v2/registry.json against them, so a
stale or hand-edited count cannot pass. Since the M01 remediation
(M01-AUDIT-10) the cross-check covers BOTH edge directions exactly
(suite -> requirements and requirement -> suites), and synthetic catalogs
prove that empty/missing catalogs, duplicate IDs, malformed rows and
unknown edges are reported as problems.

Nuance kept from the inherited suite: an entirely empty registry would
agree with an entirely empty derivation, which is why the derivation now
reports empty catalogs as problems AND test_early_collection_producers
requires the specific early-producer IDs to exist.

Run: .venv/bin/python tests/v2/test_registry.py
"""

import contextlib
import io
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

import scripts.v2.build_registry as br  # noqa: E402
from scripts.v2.build_registry import eval_suites, spec_requirements  # noqa: E402

REGISTRY = (pathlib.Path(__file__).resolve().parent.parent.parent
            / "docs/v2/registry.json")


def registry_problems(reg, spec, suites):
    """Independent consistency check of a registry document against the
    parsed catalogs (does not reuse build_registry's edge computation)."""
    bad = []
    reg_reqs = {r["id"]: r for r in reg["requirements"]}
    reg_suites = {s["id"]: s for s in reg["suites"]}
    if len(reg_reqs) != len(reg["requirements"]):
        bad.append("duplicate requirement IDs in registry")
    if len(reg_suites) != len(reg["suites"]):
        bad.append("duplicate suite IDs in registry")
    if set(reg_reqs) != set(spec):
        bad.append(f"registry/spec drift: {sorted(set(reg_reqs) ^ set(spec))}")
    if set(reg_suites) != set(suites):
        bad.append(f"registry/eval drift: {sorted(set(reg_suites) ^ set(suites))}")
    for sid, s in reg_suites.items():
        if sid in suites and sorted(s["requirements"]) != \
                sorted(suites[sid]["requirements"]):
            bad.append(f"{sid} forward edges differ from E08")
        for rid in s["requirements"]:
            if rid not in reg_reqs:
                bad.append(f"{sid} -> unknown {rid}")
    for rid, r in reg_reqs.items():
        expected = sorted(sid for sid, s in suites.items()
                          if rid in s["requirements"])
        if sorted(r["suites"]) != expected:
            bad.append(f"{rid} reverse edges {sorted(r['suites'])} != {expected}")
        if not r["suites"]:
            bad.append(f"{rid} has no suite")
        if not r["owner_milestones"].strip():
            bad.append(f"{rid} has no owner")
        if rid in spec and r["owner_milestones"] != spec[rid]["owner_milestones"]:
            bad.append(f"{rid} owner drift")
    if reg["counts"]["requirements"] != len(spec) or \
            reg["counts"]["suites"] != len(suites):
        bad.append("counts drift")
    if reg["counts"]["requirements_without_suite"] or reg["problems"]:
        bad.append("registry records problems")
    return bad


def test_registry_matches_canonical_docs():
    reg = json.loads(REGISTRY.read_text())
    problems = []
    spec = spec_requirements(problems=problems)
    suites = eval_suites(problems=problems)
    assert not problems, problems
    assert spec and suites, "canonical catalogs parsed empty"
    bad = registry_problems(reg, spec, suites)
    assert not bad, bad
    print(f"ok  registry: {len(spec)} requirements, {len(suites)} suites, "
          f"forward and reverse edges exact")


def test_early_collection_producers_have_owners():
    reg = {r["id"]: r for r in json.loads(REGISTRY.read_text())["requirements"]}
    # M01-AC04: early collection/outcome producers have explicit owners.
    for rid in ("LF-R29", "LF-R30", "LF-R31", "LF-R32", "LF-R33"):
        assert rid in reg, f"{rid} missing from the registry"
    assert "M02" in reg["LF-R30"]["owner_milestones"], "training evidence not M02-first"
    for rid in ("LF-R29", "LF-R31", "LF-R32", "LF-R33"):
        assert reg[rid]["owner_milestones"], f"{rid} unowned"
    print("ok  early collection/outcome producers owned")


def test_fabricated_reverse_edge_is_rejected():
    reg = json.loads(REGISTRY.read_text())
    spec, suites = spec_requirements(), eval_suites()
    first = reg["requirements"][0]
    other = next(s["id"] for s in reg["suites"] if s["id"] not in first["suites"])
    first["suites"] = sorted(first["suites"] + [other])
    bad = registry_problems(reg, spec, suites)
    assert any("reverse edges" in b for b in bad), bad
    reg2 = json.loads(REGISTRY.read_text())
    reg2["suites"][0]["requirements"].append("LF-R99")
    assert any("unknown LF-R99" in b or "forward" in b
               for b in registry_problems(reg2, spec, suites))
    print("ok  fabricated reverse edge / unknown forward edge rejected")


def _catalogs(td, spec_body, eval_body):
    spec = pathlib.Path(td) / "spec.md"
    ev = pathlib.Path(td) / "eval.md"
    spec.write_text(spec_body)
    ev.write_text(eval_body)
    return spec, ev


def test_structural_catalog_problems_are_reported():
    good_eval = "## E08. C\n| EV-01 Name | kind | LF-R01 |\n## E09. x\n"
    good_spec = "## S05. R\n| LF-R01 | requirement | M01 |\n## S06. x\n"
    cases = {
        "empty catalogs": ("# nothing\n", "# nothing\n",
                           ["section not found"]),
        "empty sections": ("## S05. R\n## S06. x\n", "## E08. C\n## E09. x\n",
                           ["register is empty", "catalog is empty"]),
        "duplicate id": (good_spec.replace(
            "## S06", "| LF-R01 | other | M02 |\n## S06"), good_eval,
            ["duplicate requirement row LF-R01"]),
        "malformed row": (good_spec.replace(
            "## S06", "| LF-R0x | bad | M01 |\n## S06"), good_eval,
            ["malformed S05 row"]),
        "empty owner": ("## S05. R\n| LF-R01 | requirement |  |\n## S06. x\n",
                        good_eval, ["empty requirement or owner"]),
        "unknown edge": (good_spec, good_eval.replace(
            "LF-R01 |", "LF-R01, LF-R02 |"), ["references unknown LF-R02"]),
        "suite without requirements": (good_spec, good_eval.replace(
            "## E09", "| EV-02 Other | kind | none |\n## E09"),
            ["EV-02 lists no requirements"]),
        "requirement without suite": (good_spec.replace(
            "## S06", "| LF-R02 | two | M02 |\n## S06"), good_eval,
            ["LF-R02 has no evaluation suite"]),
    }
    with tempfile.TemporaryDirectory() as td:
        for name, (spec_body, eval_body, wants) in cases.items():
            spec, ev = _catalogs(td, spec_body, eval_body)
            *_, problems = br.derive(spec, ev)
            for want in wants:
                assert any(want in p for p in problems), (name, want, problems)
        spec, ev = _catalogs(td, good_spec, good_eval)
        *_, problems = br.derive(spec, ev)
        assert problems == [], problems
        *_, problems = br.derive(pathlib.Path(td) / "absent.md", ev)
        assert any("unreadable" in p for p in problems), problems
    print(f"ok  {len(cases) + 1} structural catalog defects reported as problems")


def test_builder_exits_nonzero_on_problems():
    with tempfile.TemporaryDirectory() as td:
        spec, ev = _catalogs(td, "# nothing\n", "# nothing\n")
        saved = (br.SPEC, br.EVAL)
        br.SPEC, br.EVAL = spec, ev
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                rc = br.main(["--output", str(pathlib.Path(td) / "reg.json")])
        finally:
            br.SPEC, br.EVAL = saved
        assert rc == 1, rc
    print("ok  empty catalogs -> builder exit 1")


if __name__ == "__main__":
    test_registry_matches_canonical_docs()
    test_early_collection_producers_have_owners()
    test_fabricated_reverse_edge_is_rejected()
    test_structural_catalog_problems_are_reported()
    test_builder_exits_nonzero_on_problems()
    print("all registry tests passed (5)")
