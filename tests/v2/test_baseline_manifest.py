"""M01: baseline manifest and privacy invariants (EV-01).

Checks the manifest holds the required provenance fields with honest
nulls, and that no private-bearing file types or known private content
appear under docs/ or tests/.

Run: .venv/bin/python tests/v2/test_baseline_manifest.py
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
MANIFEST = ROOT / "docs/v2/baseline/manifest.json"

PRIVATE_EXTENSIONS = {".db", ".wav", ".mp3", ".flac", ".m4a", ".log", ".sqlite"}
# Transcript-content markers: the legacy log's own record prefixes. Their
# presence under docs/ means real (or copied) log content, whatever the
# filename. tests/v2 fixtures are exempt — their [localflow] strings are
# synthetic by construction.
TRANSCRIPT_MARKERS = (b"[localflow] raw:", b"[localflow] cleaned:")


def test_manifest_provenance_fields():
    # These assertions pin THIS machine's current baseline (installed app
    # present, com.danny.localflow, Apple Silicon). If the deployment
    # changes deliberately, regenerate the manifest and update these
    # expectations together.
    m = json.loads(MANIFEST.read_text())
    assert m["milestone"] == "M01"
    g = m["git"]
    assert g["head_commit"] and len(g["head_commit"]) >= 40
    assert isinstance(g["clean_tree"], bool)
    assert "dirty_entries" in g
    b = m["installed_bundle"]
    assert b["installed"] is True
    assert b["identity"]["CFBundleIdentifier"] == "com.danny.localflow"
    assert b["embedded_code_matches_git_head"] is True
    c = m["effective_configuration"]["effective"]
    assert c["source"] and c["path"] and c["content"]
    assert m["models"]["asr"]["configured_id"].endswith("parakeet-tdt-0.6b-v3")
    assert m["models"]["cleanup"]["configured_id"].endswith(
        "Qwen3-4B-Instruct-2507-4bit")
    for role in ("asr", "cleanup"):
        entry = m["models"][role]
        assert entry["cached"] is True and entry["revision"], role
        assert entry["weights_sha256"], role
    assert m["runtime"]["packages"]["mlx"]
    assert m["runtime"]["chip"].startswith("Apple")
    d = m["data"]["application_support"]
    for key in ("stats_db", "dictionary", "transforms"):
        assert d[key]["exists"] and d[key]["matches_historical"] is True, key
    assert m["data"]["log"]["live_extends_historical_prefix"] is True
    # Deleted local functionality is inventoried, not assumed absent.
    mods = m["locally_newer_functionality_absent_from_git"]["modules"]
    stems = {pathlib.Path(x["module"]).stem for x in mods}
    assert {"stats", "transforms", "profile"} <= stems
    # Unresolved facts carry reasons.
    for u in m["unresolved"]:
        assert u["status"] == "unresolved" and u["reason"]
    print("ok  baseline manifest provenance fields")


def test_no_private_files_in_repo_docs_or_tests():
    offenders = []
    for base in (ROOT / "docs", ROOT / "tests"):
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in PRIVATE_EXTENSIONS:
                offenders.append(str(p))
    assert not offenders, offenders
    # Extension checks alone miss extensionless copies (e.g. a log saved as
    # ".full" or ".historical-prefix"); scan docs/ for the log's own record
    # prefixes so transcript content cannot leak regardless of filename.
    for p in (ROOT / "docs").rglob("*"):
        if p.is_file():
            blob = p.read_bytes()
            for marker in TRANSCRIPT_MARKERS:
                assert marker not in blob, (p, marker)
    # The reconciliation report must not embed transcript payloads.
    blob = (ROOT / "docs/v2/baseline/legacy-log-reconciliation.json").read_text()
    for key in ('"_raw"', '"_cleaned"', '"raw_text"', '"cleaned_text"'):
        assert key not in blob, key
    print("ok  no private-bearing files under docs/ or tests/")


def test_fixture_manifest_reserved_only():
    fm = json.loads((ROOT / "tests/v2/fixtures/manifest.json").read_text())
    assert fm["test_manifest_reservation"]["families_assigned"] == 0
    allowed = {"reserved", "partial", "complete"}
    for fam in fm["families"]:
        assert fam["status"] in allowed, fam["family"]
        assert fam["planned_count"] > 0 and fam["owner_milestone"]
        if fam["status"] != "reserved":
            # A family with created fixtures must carry one or more
            # <milestone>_created blocks; every count inside them is
            # positive and auditable — never silent (M04 first
            # exercised this for its two strata).
            created = {k: v for k, v in fam.items()
                       if k.endswith("_created")}
            assert created, fam["family"]
            for key, block in created.items():
                assert isinstance(block, dict), (fam["family"], key)
                counted = {k: v for k, v in block.items()
                           if isinstance(v, int)}
                assert counted, (fam["family"], key)
                for name, val in counted.items():
                    assert val > 0, (fam["family"], key, name)
    total = sum(f["planned_count"] for f in fm["families"])
    assert total == 320 + 60 + 80 + 60 + 20 + 100 + 30 + 32 + 24, total
    print(f"ok  fixture families honest ({total} planned; created strata "
          f"carry owners and counts)")


if __name__ == "__main__":
    test_manifest_provenance_fields()
    test_no_private_files_in_repo_docs_or_tests()
    test_fixture_manifest_reserved_only()
    print("all baseline manifest tests passed")
