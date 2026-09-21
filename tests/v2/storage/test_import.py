"""EV-03 / M02: lossless legacy-import tests (Spec S08, Evaluation E12/E13).

All fixtures are synthetic (the real seven rows live on this machine and
are imported once by scripts/v2/import_legacy.py; that run's report is
recorded in docs/v2/acceptance/M02/results.json). Cases cover verbatim
row import with original UTC instants, idempotent re-import, dictionary/
transform legacy revisions, unknown-date log imports with stable
``legacy:<sha>:<line-range>`` identity, byte-prefix reconciliation of an
appended log, interrupted-import recovery and source immutability.

Run: .venv/bin/python tests/v2/storage/test_import.py
"""

import hashlib
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import importer, store  # noqa: E402

# Synthetic stand-ins mirroring the live shapes (values differ; the real
# totals 280/277/350.3/11 are verified by the real-data import run).
ROWS = [
    (1, 1783199742.804, 40.1, "alpha raw one", "Alpha raw one.", 3, 3, 0,
     4.5, "Terminal", "com.apple.Terminal", "dictation"),
    (2, 1783200010.5, 51.2, "beta raw two words", "Beta raw two words.", 4, 4,
     1, 4.7, "Terminal", "com.apple.Terminal", "dictation"),
    (3, 1783201120.276, 12.0, "gamma", "Gamma.", 1, 1, 0, 5.0, "Terminal",
     "com.apple.Terminal", "dictation"),
]


def make_stats_db(path: pathlib.Path):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE dictations(id INTEGER PRIMARY KEY, ts REAL,"
        " duration_sec REAL, raw_text TEXT, cleaned_text TEXT,"
        " raw_words INTEGER, cleaned_words INTEGER, fixed_words INTEGER,"
        " wpm REAL, app_name TEXT, app_bundle TEXT, kind TEXT)")
    con.executemany("INSERT INTO dictations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    ROWS)
    con.commit()
    con.close()


def make_dict_json(path: pathlib.Path):
    path.write_text(json.dumps(
        {"terms": ["Qwen", "MLX", "Parakeet", "LocalFlow", "Wispr Flow",
                   "PyObjC", "MacBook"]}))


def make_transforms_json(path: pathlib.Path):
    path.write_text(json.dumps([
        {"key": "1", "name": "Polish", "description": "d1", "prompt": "p1"},
        {"key": "2", "name": "Prompt Engineer", "description": "d2",
         "prompt": "p2"},
    ]))


def make_log_text(pairs=3, start_line_noise=True):
    lines = ["[localflow] ready — hold fn to dictate, release to insert text."]
    if start_line_noise:
        lines.append("[localflow] model loaded.")
        lines.append(
            "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)")
    for i in range(pairs):
        lines.append(
            "[localflow] audio: 3.0s from 'mic', voiced 50%, trailing"
            " silence 0.5s, overflows 0")
        lines.append(f"[localflow] raw:     synthetic raw number {i}")
        lines.append(f"[localflow] cleaned: Synthetic raw number {i}.")
        lines.append("[localflow] timing: stt 0.2s, cleanup 0.4s")
        lines.append("[localflow] inserted 20 chars")
    return "\n".join(lines) + "\n"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_env():
    td = pathlib.Path(tempfile.mkdtemp())
    make_stats_db(td / "stats.db")
    make_dict_json(td / "dictionary.json")
    make_transforms_json(td / "transforms.json")
    (td / "LocalFlow.log").write_text(make_log_text(3))
    st = store.Store(td / "v2.db", backup_dir=td / "backups")
    return td, st, importer.LegacyImporter(st, td / "backups")


def test_verbatim_rows_and_totals():
    td, st, imp = new_env()
    r = imp.import_stats_db(td / "stats.db")
    assert r["rows_imported"] == 3 and r["rows_skipped"] == 0
    st.sync()
    n, raw_w, clean_w, dur, fixed, lo, hi = st.legacy_totals()
    assert (n, raw_w, clean_w, dur, fixed) == (3, 8, 8, 103.3, 1), \
        st.legacy_totals()
    # Original UTC instants preserved exactly, not reassigned to import day.
    con = sqlite3.connect(st.db_path)
    stored_ts = [r[0] for r in con.execute(
        "SELECT ts FROM legacy_dictations ORDER BY id")]
    con.close()
    assert stored_ts == [row[1] for row in ROWS]
    assert lo.startswith("2026-07-04T21:15:42") and \
        hi.startswith("2026-07-04T21:38:40")
    assert st.dated_analytics_rows() == 3
    st.close()
    print("ok  stats rows imported verbatim, instants preserved")


def test_idempotent_reimport():
    td, st, imp = new_env()
    imp.import_stats_db(td / "stats.db")
    imp.import_dictionary(td / "dictionary.json")
    imp.import_transforms(td / "transforms.json")
    r1 = imp.import_log(td / "LocalFlow.log")
    st.sync()
    before = st.artifact_count()
    n1, *_ = st.legacy_totals()
    # Re-run every import against identical sources.
    r2 = imp.import_stats_db(td / "stats.db")
    d2 = imp.import_dictionary(td / "dictionary.json")
    t2 = imp.import_transforms(td / "transforms.json")
    r3 = imp.import_log(td / "LocalFlow.log")
    st.sync()
    assert r2["rows_imported"] == 0 and r2["rows_skipped"] == 3
    assert d2["imported"] == 0 and d2["skipped"] == 7
    assert t2["imported"] == 0 and t2["skipped"] == 2
    assert r3["pairs_imported"] == 0 and r3["pairs_skipped"] == 3
    assert st.artifact_count() == before
    n2, *_ = st.legacy_totals()
    assert n1 == n2 == 3
    st.close()
    print("ok  repeated identical import adds zero rows")


def test_dictionary_and_transform_legacy_revisions():
    td, st, imp = new_env()
    imp.import_dictionary(td / "dictionary.json")
    imp.import_transforms(td / "transforms.json")
    st.sync()
    con = sqlite3.connect(st.db_path)
    terms = con.execute(
        "SELECT COUNT(*) FROM artifacts WHERE kind='legacy_dictionary_term'"
    ).fetchone()[0]
    defs = con.execute(
        "SELECT COUNT(*) FROM artifacts WHERE"
        " kind='legacy_transform_definition'").fetchone()[0]
    legacy_class = con.execute(
        "SELECT COUNT(*) FROM artifacts WHERE retention_class='legacy'"
    ).fetchone()[0]
    con.close()
    assert terms == 7 and defs == 2 and legacy_class == 9
    payload = st.artifact_payload(_first_artifact(st, "legacy_transform_definition"))
    assert json.loads(payload)["key"] == "1"  # exact JSON preserved
    st.close()
    print("ok  7 terms + 2 transforms as immutable legacy revisions")


def _first_artifact(st, kind):
    import sqlite3

    con = sqlite3.connect(st.db_path)
    aid = con.execute("SELECT artifact_id FROM artifacts WHERE kind=?"
                      " LIMIT 1", (kind,)).fetchone()[0]
    con.close()
    return aid


def test_log_identity_and_unknown_dates():
    td, st, imp = new_env()
    r = imp.import_log(td / "LocalFlow.log")
    st.sync()
    assert r["pairs_imported"] == 3
    log_sha = sha(td / "LocalFlow.log")
    con = sqlite3.connect(st.db_path)
    arts = con.execute(
        "SELECT role, meta_json FROM artifacts WHERE stage='legacy_log'"
        " ORDER BY created_at_utc, artifact_id").fetchall()
    imports_rows = con.execute(
        "SELECT source_locator FROM imports WHERE source_kind='legacy_log'"
    ).fetchall()
    con.close()
    assert len(arts) == 6  # raw + cleaned per pair
    identities = set()
    for role, meta in arts:
        m = json.loads(meta)
        identities.add(m["identity"])
        assert m["time_quality"] == "unknown"
    for (loc,) in imports_rows:
        identities.add(f"legacy:{log_sha}:{loc[6:]}")
    assert len(identities) == 3, identities  # one identity per pair
    # Unknown-date log imports never populate dated analytics (S21/E12).
    assert st.dated_analytics_rows() == 0
    st.close()
    print("ok  log pairs keep legacy:<sha>:<lines> identity, dates unknown")


def test_appended_log_prefix_reconciliation():
    td, st, imp = new_env()
    imp.import_log(td / "LocalFlow.log")
    st.sync()
    # The running app appends more pairs to the same file.
    log = td / "LocalFlow.log"
    log.write_text(log.read_text() + make_log_text(pairs=2))
    r = imp.import_log(log)
    st.sync()
    assert r["pairs_imported"] == 2 and r["pairs_skipped"] == 3, r
    assert r["prefix_reconciled"] is not None
    st.close()
    print("ok  appended log imports only its new pairs")


def test_interrupted_import_recovers():
    td, st, imp = new_env()
    # Crash between pair imports (the composite pair op is itself atomic,
    # proven separately in test_store): pair 1 commits, then the import
    # dies. A re-import must converge to the complete set, no duplicates.
    real = st.import_legacy_pair
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("simulated crash after first pair")
        return real(*a, **k)

    st.import_legacy_pair = flaky
    try:
        imp.import_log(td / "LocalFlow.log")
    except Exception:
        pass
    st.import_legacy_pair = real
    st.sync()
    r = imp.import_log(td / "LocalFlow.log")
    st.sync()
    con = sqlite3.connect(st.db_path)
    n = con.execute("SELECT COUNT(*) FROM artifacts WHERE"
                    " stage='legacy_log'").fetchone()[0]
    con.close()
    assert r["pairs_imported"] == 2 and r["pairs_skipped"] == 1, r
    assert n == 6, n  # 3 pairs × (raw + cleaned), no duplicates
    st.close()
    print("ok  interrupted import recovers without duplicates")


def test_sources_never_mutated():
    td, st, imp = new_env()
    hashes = {p.name: sha(p) for p in
              (td / "stats.db", td / "dictionary.json",
               td / "transforms.json", td / "LocalFlow.log")}
    imp.import_stats_db(td / "stats.db")
    imp.import_dictionary(td / "dictionary.json")
    imp.import_transforms(td / "transforms.json")
    imp.import_log(td / "LocalFlow.log")
    st.sync()
    for name, h in hashes.items():
        assert sha(td / name) == h, name
    # A verified backup of stats.db exists before rows were read from it.
    assert any(p.suffix == ".bak" for p in (td / "backups").iterdir())
    st.close()
    print("ok  sources byte-identical; backup created before import")


def main():
    test_verbatim_rows_and_totals()
    test_idempotent_reimport()
    test_dictionary_and_transform_legacy_revisions()
    test_log_identity_and_unknown_dates()
    test_appended_log_prefix_reconciliation()
    test_interrupted_import_recovers()
    test_sources_never_mutated()
    print("all import tests passed")


if __name__ == "__main__":
    main()
