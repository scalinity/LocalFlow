"""M01-AC03/AC04: registry traceability tests.

Re-derives requirements and suites from the canonical Markdown (Spec S05,
Evaluation E08) and cross-checks docs/v2/registry.json against them, so a
stale or hand-edited count cannot pass.

Run: .venv/bin/python tests/v2/test_registry.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from scripts.v2.build_registry import eval_suites, spec_requirements  # noqa: E402

REGISTRY = (pathlib.Path(__file__).resolve().parent.parent.parent
            / "docs/v2/registry.json")


def test_registry_matches_canonical_docs():
    reg = json.loads(REGISTRY.read_text())
    spec = spec_requirements()
    suites = eval_suites()

    reg_reqs = {r["id"] for r in reg["requirements"]}
    assert reg_reqs == set(spec), (
        f"registry/spec drift: {reg_reqs ^ set(spec)}")
    assert {s["id"] for s in reg["suites"]} == set(suites), "registry/eval drift"

    # Every current requirement has at least one suite and an owner milestone.
    for r in reg["requirements"]:
        assert r["suites"], f"{r['id']} has no suite"
        assert r["owner_milestones"].strip(), f"{r['id']} has no owner"

    # Owner milestones agree with the Spec register text.
    for r in reg["requirements"]:
        assert r["owner_milestones"] == spec[r["id"]]["owner_milestones"], r["id"]

    # Suite membership agrees with the Evaluation catalog.
    for s in reg["suites"]:
        assert sorted(s["requirements"]) == sorted(suites[s["id"]]["requirements"]), s["id"]

    assert reg["counts"]["requirements"] == len(spec)
    assert reg["counts"]["suites"] == len(suites)
    assert not reg["counts"]["requirements_without_suite"]
    assert not reg["problems"]
    print(f"ok  registry: {len(spec)} requirements, {len(suites)} suites, "
          f"all owned and covered")


def test_early_collection_producers_have_owners():
    reg = {r["id"]: r for r in json.loads(REGISTRY.read_text())["requirements"]}
    # M01-AC04: early collection/outcome producers have explicit owners.
    assert "M02" in reg["LF-R30"]["owner_milestones"], "training evidence not M02-first"
    for rid in ("LF-R29", "LF-R31", "LF-R32", "LF-R33"):
        assert reg[rid]["owner_milestones"], f"{rid} unowned"
    print("ok  early collection/outcome producers owned")


if __name__ == "__main__":
    test_registry_matches_canonical_docs()
    test_early_collection_producers_have_owners()
    print("all registry tests passed")
