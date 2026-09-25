"""M01: frozen baseline record, privacy invariants and fixture inventory
(EV-01).

- test_historical_manifest_record_is_frozen: the committed 2026-09-21
  baseline document is intact (a HISTORICAL record — producer correctness
  lives in test_baseline_manifest_producers.py).
- Privacy scan (M01 remediation, M01-AUDIT-14): every tracked and
  untracked non-ignored path in the repository is scanned — not only
  docs/ and tests/ — by extension, by content signature (SQLite, WAV,
  FLAC, MP3/ID3, MP4/M4A, whatever the filename), for legacy-log record
  markers and for transcript-bearing JSON keys. Files whose synthetic
  markers are intentional are listed explicitly with a reason. Synthetic
  canaries prove each rule fires.
- Fixture inventory (M01-AUDIT-16): every *_created block is reconciled
  against the actual files — existence, synthetic origin, unique case IDs
  and exact counts — and every fixture file in tests/v2 must be declared.

Run: .venv/bin/python tests/v2/test_baseline_manifest.py
"""

import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
MANIFEST = ROOT / "docs/v2/baseline/manifest.json"

PRIVATE_EXTENSIONS = {".db", ".wav", ".mp3", ".flac", ".m4a", ".log", ".sqlite",
                      ".sqlite3", ".db-wal", ".db-shm", ".db-journal"}
# Transcript-content markers: the legacy log's own record prefixes.
TRANSCRIPT_MARKERS = (b"[localflow] raw:", b"[localflow] cleaned:")
# JSON keys that carry transcript payloads in this project's own records.
TRANSCRIPT_KEYS = {"raw_text", "cleaned_text", "_raw", "_cleaned",
                   "_raw_exact", "_cleaned_exact", "transcript"}
# Explicit exceptions: files whose [localflow] record strings are synthetic
# by construction (parser framing docs and hand-written test logs).
SYNTHETIC_MARKER_FILES = {
    "scripts/v2/parse_legacy_log.py": "documents the app's own print framing",
    "tests/v2/test_legacy_parser.py": "hand-written synthetic log lines",
    "tests/v2/test_legacy_import_boundary.py": "hand-written synthetic log lines",
    "tests/v2/storage/test_import.py": "generated synthetic log lines",
    "tests/v2/logging/test_event_writer.py": "impersonation-attempt fixture",
    "tests/v2/test_baseline_manifest.py": "marker constants and canaries",
    "docs/v2/acceptance/M01/remediation/repro_inherited.py":
        "synthetic reproduction inputs for the M01 audit findings",
    "docs/v2/acceptance/M01/remediation/diff_parsers.py":
        "simulated legacy logs for the parser neutrality check",
}


def content_signature(head: bytes):
    if head.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:3] == b"ID3":
        return "mp3"
    if head[4:8] == b"ftyp":
        return "mp4/m4a"
    return None


def _json_transcript_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in TRANSCRIPT_KEYS and isinstance(v, str) and v.strip():
                yield k
            yield from _json_transcript_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _json_transcript_keys(v)


def scan_population(root: pathlib.Path):
    """Tracked + untracked non-ignored files (what could be committed)."""
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached",
                        "--others", "--exclude-standard"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # Not a Git checkout: scan everything except VCS/venv internals.
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                      if p.is_file() and not {".git", ".venv"} & set(
                          p.relative_to(root).parts))
    return sorted(p for p in r.stdout.split("\0") if p)


def privacy_offenders(root: pathlib.Path, paths=None, exceptions=None):
    exceptions = SYNTHETIC_MARKER_FILES if exceptions is None else exceptions
    offenders = []
    for rel in (scan_population(root) if paths is None else paths):
        p = root / rel
        if not p.is_file() or p.is_symlink():
            continue
        if any(rel.lower().endswith(ext) for ext in PRIVATE_EXTENSIONS):
            offenders.append((rel, "private extension"))
        blob = p.read_bytes()
        sig = content_signature(blob[:16])
        if sig:
            offenders.append((rel, f"{sig} content signature"))
        if rel not in exceptions and any(m in blob for m in TRANSCRIPT_MARKERS):
            offenders.append((rel, "legacy log record marker"))
        if rel.endswith(".json"):
            try:
                keys = sorted(set(_json_transcript_keys(json.loads(blob))))
            except (ValueError, UnicodeDecodeError):
                keys = []
            if keys:
                offenders.append((rel, f"transcript keys {keys}"))
    return offenders


def test_historical_manifest_record_is_frozen():
    # FROZEN HISTORICAL DOCUMENT CHECK (M01 remediation, M01-AUDIT-15).
    # These assertions pin the September 21 observations recorded in
    # docs/v2/baseline/manifest.json (schema 1). They verify that the
    # committed historical record is intact — NOT that any machine is in
    # this state today, and NOT that the generator is correct. Producer
    # correctness is tested independently with synthetic fixtures in
    # tests/v2/test_baseline_manifest_producers.py; current-state runs
    # are written to docs/v2/baseline/runs/<run-id>/ and never here.
    m = json.loads(MANIFEST.read_text())
    assert m["schema_version"] == 1
    assert m["generated_utc"].startswith("2026-09-21"), m["generated_utc"]
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
    print("ok  frozen 2026-09-21 baseline record intact (historical, not current)")


def test_no_private_files_in_repository():
    population = scan_population(ROOT)
    # The population reaches beyond docs/ and tests/.
    assert any(p.startswith("scripts/") for p in population)
    assert any(p.startswith("localflow/") for p in population)
    assert "README.md" in population
    offenders = privacy_offenders(ROOT)
    assert not offenders, offenders
    missing = [p for p in SYNTHETIC_MARKER_FILES
               if not (ROOT / p).exists()]
    assert not missing, f"stale privacy exceptions: {missing}"
    # The reconciliation report must not embed transcript payloads.
    blob = (ROOT / "docs/v2/baseline/legacy-log-reconciliation.json").read_text()
    for key in ('"_raw"', '"_cleaned"', '"raw_text"', '"cleaned_text"'):
        assert key not in blob, key
    print(f"ok  privacy scan clean over {len(population)} repository paths")


def test_privacy_scan_catches_synthetic_canaries():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "docs").mkdir()
        (root / "scripts").mkdir()
        (root / "tests").mkdir()
        # ordinary JSON carrying a transcript field
        (root / "docs" / "rows.json").write_text(
            json.dumps({"rows": [{"raw_text": "CANARY synthetic words"}]}))
        # a renamed SQLite database
        con = sqlite3.connect(root / "tests" / "canary.bin")
        con.execute("CREATE TABLE canary (x)")
        con.commit()
        con.close()
        # a renamed WAV outside docs/tests
        (root / "scripts" / "clip.dat").write_bytes(
            b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 24)
        # copied log content at the repository root
        (root / "notes.txt").write_text("[localflow] raw:     CANARY\n")
        # an explicitly excepted synthetic file is allowed
        (root / "scripts" / "synthetic.py").write_text(
            "X = '[localflow] raw:     synthetic'\n")
        # a private extension
        (root / "stats.sqlite3").write_bytes(b"x")
        got = dict(privacy_offenders(
            root, exceptions={"scripts/synthetic.py": "synthetic"}))
        assert got == {
            "docs/rows.json": "transcript keys ['raw_text']",
            "tests/canary.bin": "sqlite content signature",
            "scripts/clip.dat": "wav content signature",
            "notes.txt": "legacy log record marker",
            "stats.sqlite3": "private extension",
        }, got
    print("ok  privacy canaries: JSON field, renamed SQLite/WAV, root log, extension")


# Independent reconciliation table: every integer in a *_created block is
# either backed by a file and a counting rule, or explicitly not file-backed
# with a reason. A new count that is in neither list fails the test.
CREATED_COUNTS = {
    ("curated_deterministic_semantic", "m04_created", "numbers_units_dates"):
        ("tests/v2/normalization/fixtures_numeric.json", "cases"),
    ("curated_deterministic_semantic", "m04_created", "syntax_paths_skills"):
        ("tests/v2/normalization/fixtures_syntax.json", "cases"),
    ("curated_deterministic_semantic", "m04_created",
     "short_command_text_counterparts"):
        ("tests/v2/normalization/short_command_corpus.json", "cases"),
    ("curated_deterministic_semantic", "m05_created", "vocabulary"):
        ("tests/v2/vocabulary/fixtures_vocabulary.json", "cases"),
    ("curated_deterministic_semantic", "m07_created", "fidelity"):
        ("tests/v2/fidelity/fixtures_fidelity.json", "cases"),
    ("curated_deterministic_semantic", "m07_created", "structure"):
        ("tests/v2/structure/fixtures_structure.json", "cases"),
    ("curated_deterministic_semantic", "m07_created", "literal_quoted_commands"):
        ("tests/v2/fidelity/fixtures_literal.json", "cases"),
    ("context_target_scenarios", "m06_created", "scenarios"):
        ("tests/v2/context/fixtures_context_targets.json", "scenarios"),
    ("context_target_scenarios", "m06_created", "adversarial_trees"):
        ("tests/v2/context/fixtures_context_targets.json", "adversarial"),
    ("hint_discrimination_matrix", "m05_created", "labeled_bases"):
        ("tests/v2/vocabulary/fixtures_hint_matrix.json", "targets*templates"),
    ("prompt_engineer_cases", "m11_created", "cases"):
        ("tests/v2/transforms/fixtures_prompt_engineer.json", "cases"),
    ("prompt_engineer_cases", "m11_created", "dev"):
        ("tests/v2/transforms/fixtures_prompt_engineer.json", "split=dev"),
    ("prompt_engineer_cases", "m11_created", "validation"):
        ("tests/v2/transforms/fixtures_prompt_engineer.json", "split=validation"),
    ("prompt_engineer_cases", "m11_created", "held_out"):
        ("tests/v2/transforms/fixtures_prompt_engineer.json", "split=held-out"),
}
NOT_FILE_BACKED = {
    ("curated_deterministic_semantic", "m05_created",
     "negative_control_corpus_generated"): "generated inside the M05 suite",
    ("hint_discrimination_matrix", "m05_created", "conditions_per_base"):
        "a per-base parameter, not a case count",
}


def _cases(doc, rule):
    if rule == "targets*templates":
        return None, len(doc["targets"]) * len(doc["templates"])
    if rule.startswith("split="):
        items = [c for c in doc["cases"] if c.get("split") == rule[6:]]
        return items, len(items)
    items = doc[rule]
    return items, len(items)


def _case_id(c):
    return c.get("case_id") or c.get("id") or c.get("target_id")


def fixture_inventory_problems(fm, root):
    problems = []
    assert fm["test_manifest_reservation"]["families_assigned"] == 0
    allowed = {"reserved", "partial", "complete"}
    declared_files = set()
    for fam in fm["families"]:
        name = fam["family"]
        if fam["status"] not in allowed:
            problems.append(f"{name}: status {fam['status']!r}")
        if not (fam["planned_count"] > 0 and fam["owner_milestone"]):
            problems.append(f"{name}: planned count/owner missing")
        created = {k: v for k, v in fam.items() if k.endswith("_created")}
        if fam["status"] == "reserved" and created:
            problems.append(f"{name}: reserved but has created blocks")
        if fam["status"] != "reserved" and not created:
            problems.append(f"{name}: {fam['status']} without created blocks")
        for block_name, block in created.items():
            if not isinstance(block, dict):
                problems.append(f"{name}.{block_name}: not an object")
                continue
            for f in block.get("fixture_files", []):
                declared_files.add(f)
                if not (root / f).is_file():
                    problems.append(f"{name}.{block_name}: missing file {f}")
            for key, val in block.items():
                if not isinstance(val, int) or isinstance(val, bool):
                    continue
                ident = (name, block_name, key)
                if val <= 0:
                    problems.append(f"{ident}: non-positive count {val}")
                if ident in NOT_FILE_BACKED:
                    continue
                if ident not in CREATED_COUNTS:
                    problems.append(f"{ident}: count not reconciled to a file")
                    continue
                path, rule = CREATED_COUNTS[ident]
                if path not in block.get("fixture_files", []):
                    problems.append(f"{ident}: {path} not declared in the block")
                if not (root / path).is_file():
                    continue
                doc = json.loads((root / path).read_text())
                origin = doc.get("origin") or (
                    "synthetic" if "synthetic" in doc.get("note", "").lower()
                    else None)
                if origin != "synthetic":
                    problems.append(f"{path}: origin not synthetic ({origin})")
                items, actual = _cases(doc, rule)
                if actual != val:
                    problems.append(f"{ident}: declared {val}, file has {actual}")
                if items is not None:
                    ids = [_case_id(c) for c in items]
                    if not all(ids):
                        problems.append(f"{path}: case without an ID")
                    elif len(set(ids)) != len(ids):
                        problems.append(f"{path}: duplicate case IDs")
        if fam["status"] == "complete":
            total = 0
            for (fam_name, block_name, key), (_, rule) in CREATED_COUNTS.items():
                if fam_name == name and rule == "cases":
                    total += fam.get(block_name, {}).get(key, 0)
            if total != fam["planned_count"]:
                problems.append(f"{name}: complete but {total} != planned "
                                f"{fam['planned_count']}")
    # Every fixture file present in tests/v2 must be declared somewhere.
    present = {p.relative_to(root).as_posix()
               for pat in ("fixtures_*.json", "*_corpus.json")
               for p in (root / "tests" / "v2").rglob(pat)}
    for f in sorted(present - declared_files):
        problems.append(f"undeclared fixture file {f}")
    return problems


def test_fixture_inventory_reconciles_with_files():
    fm = json.loads((ROOT / "tests/v2/fixtures/manifest.json").read_text())
    problems = fixture_inventory_problems(fm, ROOT)
    assert not problems, problems
    total = sum(f["planned_count"] for f in fm["families"])
    assert total == 320 + 60 + 80 + 60 + 20 + 100 + 30 + 32 + 24 + 40, total
    reserved = [f["family"] for f in fm["families"] if f["status"] == "reserved"]
    print(f"ok  fixture inventory reconciled with files ({total} planned; "
          f"{len(reserved)} families still reserved)")


def test_fixture_inventory_rejects_inconsistencies():
    import copy
    fm = json.loads((ROOT / "tests/v2/fixtures/manifest.json").read_text())
    fam0 = next(f for f in fm["families"]
                if f["family"] == "curated_deterministic_semantic")
    mutations = {
        "missing file": lambda m: m["families"][0]["m04_created"][
            "fixture_files"].append("tests/v2/does_not_exist.json"),
        "inflated count": lambda m: m["families"][0]["m04_created"].__setitem__(
            "numbers_units_dates", 999),
        "unreconciled count": lambda m: m["families"][0]["m04_created"]
            .__setitem__("invented_stratum", 5),
        "reserved with blocks": lambda m: m["families"][0].__setitem__(
            "status", "reserved"),
        "undeclared file": lambda m: m["families"][0]["m04_created"][
            "fixture_files"].remove(
                "tests/v2/normalization/short_command_corpus.json"),
    }
    assert fm["families"][0] is fam0 or fm["families"][0]["family"] == fam0["family"]
    for name, mutate in mutations.items():
        m = copy.deepcopy(fm)
        mutate(m)
        assert fixture_inventory_problems(m, ROOT), name
    print(f"ok  {len(mutations)} inventory inconsistencies rejected")


if __name__ == "__main__":
    test_historical_manifest_record_is_frozen()
    test_no_private_files_in_repository()
    test_privacy_scan_catches_synthetic_canaries()
    test_fixture_inventory_reconciles_with_files()
    test_fixture_inventory_rejects_inconsistencies()
    print("all baseline manifest tests passed (5)")
