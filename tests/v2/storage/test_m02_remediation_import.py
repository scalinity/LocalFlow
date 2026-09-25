"""M02 remediation regressions: interrupted log import followed by source
growth, and stats-row identity/acknowledgment (M02-AUDIT-10/11).

Expected payloads and identities are written by hand; the accepted M01
behavior (exact text, all verified prefixes, deferred tails, repeated
identical utterances as distinct identities) is asserted alongside.

Run: .venv/bin/python tests/v2/storage/test_m02_remediation_import.py
"""

import hashlib
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import importer, store  # noqa: E402

HEAD = "[localflow] ready — hold fn to dictate, release to insert text.\n"


def record(raw, cleaned):
    return ("[localflow] audio: 3.0s from 'mic', voiced 50%, trailing"
            " silence 0.5s, overflows 0\n"
            f"[localflow] raw:     {raw}\n"
            f"[localflow] cleaned: {cleaned}\n"
            "[localflow] timing: stt 0.2s, cleanup 0.4s\n"
            "[localflow] inserted 20 chars\n")


def env():
    td = pathlib.Path(tempfile.mkdtemp())
    st = store.Store(td / "v2.db", backup_dir=td / "bk")
    return td, st, importer.LegacyImporter(st, td / "bk")


def pairs(st):
    st.sync()
    con = sqlite3.connect(st.db_path)
    out = con.execute(
        "SELECT a.content_text, c.content_text, c.meta_json FROM artifacts c"
        " JOIN artifacts a ON a.artifact_id = c.parent_artifact_id WHERE"
        " c.role='cleaned_transcript' AND c.stage='legacy_log' ORDER BY"
        " c.rowid").fetchall()
    con.close()
    return [(r, c, json.loads(m)["identity"]) for r, c, m in out]


def interrupt_after(st, n_ok):
    real = st.import_legacy_pair
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] > n_ok:
            raise RuntimeError("simulated crash")
        return real(*a, **k)
    st.import_legacy_pair = flaky
    return lambda: setattr(st, "import_legacy_pair", real)


def test_interrupted_import_then_growth_imports_each_pair_once():
    td, st, imp = env()
    log = td / "LocalFlow.log"
    # Two identical utterances (distinct occurrences) plus one other.
    v1 = HEAD + record("same words", "Same words.") \
        + record("same words", "Same words.") + record("other", "Other.")
    log.write_bytes(v1.encode())
    sha1 = hashlib.sha256(v1.encode()).hexdigest()
    restore = interrupt_after(st, 1)
    try:
        imp.import_log(log)
        raise AssertionError("expected simulated crash")
    except RuntimeError:
        pass
    restore()
    # The run's snapshot was recorded before its first pair committed.
    con = sqlite3.connect(st.db_path)
    runs = con.execute("SELECT source_sha256, source_bytes, note FROM"
                       " import_runs").fetchall()
    con.close()
    assert runs == [(sha1, len(v1.encode()), "status=started")], runs
    # The source grows before the rerun.
    v2 = v1 + record("  spaced   tail  ", "Spaced tail.")
    log.write_bytes(v2.encode())
    sha2 = hashlib.sha256(v2.encode()).hexdigest()
    r = imp.import_log(log)
    assert r["prefix_reconciled"] == sha1, r
    assert r["pairs_imported"] == 3 and r["pairs_skipped"] == 1, r
    got = pairs(st)
    assert got == [
        ("same words", "Same words.", f"legacy:{sha1}:3-4"),
        ("same words", "Same words.", f"legacy:{sha2}:8-9"),
        ("other", "Other.", f"legacy:{sha2}:13-14"),
        ("  spaced   tail  ", "Spaced tail.", f"legacy:{sha2}:18-19"),
    ], got
    # Re-running the grown source adds nothing.
    r2 = imp.import_log(log)
    assert r2["pairs_imported"] == 0 and len(pairs(st)) == 4
    con = sqlite3.connect(st.db_path)
    notes = [n for (n,) in con.execute(
        "SELECT note FROM import_runs ORDER BY rowid")]
    con.close()
    assert notes[0] == "status=started"  # the interrupted run, honestly
    assert all(n.startswith("status=completed") for n in notes[1:])
    st.close()
    print("ok  10 interrupted import + source growth: each occurrence once,"
          " exact text, identical utterances distinct, original identity"
          " kept for the committed pair")


def test_interrupted_twice_across_multiple_prefixes():
    td, st, imp = env()
    log = td / "LocalFlow.log"
    body = HEAD + record("one", "One.") + record("two", "Two.")
    log.write_bytes(body.encode())
    restore = interrupt_after(st, 1)
    try:
        imp.import_log(log)
    except RuntimeError:
        pass
    restore()
    body += record("three", "Three.")
    log.write_bytes(body.encode())
    restore = interrupt_after(st, 1)  # commits "two", crashes on "three"
    try:
        imp.import_log(log)
    except RuntimeError:
        pass
    restore()
    body += record("four", "Four.")
    log.write_bytes(body.encode())
    imp.import_log(log)
    texts = [p[0] for p in pairs(st)]
    assert texts == ["one", "two", "three", "four"], texts
    st.close()
    print("ok  10 two interrupted runs over growing prefixes converge with"
          " no duplicates")


def stats_db(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE dictations(id INTEGER PRIMARY KEY, ts REAL,"
                " duration_sec REAL, raw_text TEXT, cleaned_text TEXT,"
                " raw_words INTEGER, cleaned_words INTEGER, fixed_words"
                " INTEGER, wpm REAL, app_name TEXT, app_bundle TEXT,"
                " kind TEXT)")
    con.executemany("INSERT INTO dictations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    rows)
    con.commit()
    con.close()


ROW_A = (1, 1783199742.804, 40.1, "alpha", "Alpha.", 1, 1, 0, 1.5, "T", "t",
         "dictation")
ROW_B = (1, 1783299742.5, 12.0, "different", "Different.", 1, 1, 1, 5.0,
         "T", "t", "dictation")
ROW_C = (2, 1783200010.5, 51.2, "beta", "Beta.", 1, 1, 0, 1.2, "T", "t",
         "dictation")


def test_stats_id_conflict_preserved_and_reported():
    td, st, imp = env()
    stats_db(td / "a.db", [ROW_A, ROW_C])
    stats_db(td / "b.db", [ROW_B])
    stats_db(td / "c.db", [ROW_A])  # the same entity again
    ra = imp.import_stats_db(td / "a.db")
    rb = imp.import_stats_db(td / "b.db")
    rc = imp.import_stats_db(td / "c.db")
    assert (ra["rows_imported"], ra["rows_conflicted"]) == (2, 0)
    assert (rb["rows_imported"], rb["rows_conflicted"]) == (0, 1), rb
    assert (rc["rows_imported"], rc["rows_identical_duplicate"]) == (0, 1)
    con = sqlite3.connect(st.db_path)
    # Legacy totals keep the first source's rows only (no silent swap).
    assert con.execute("SELECT id, raw_text FROM legacy_dictations ORDER BY"
                       " id").fetchall() == [(1, "alpha"), (2, "beta")]
    conflict = con.execute(
        "SELECT content_text, meta_json, retention_class FROM artifacts"
        " WHERE kind='legacy_stats_row_conflict'").fetchall()
    assert len(conflict) == 1
    payload = json.loads(conflict[0][0])
    assert payload["raw_text"] == "different" and payload["ts"] == ROW_B[1]
    assert json.loads(conflict[0][1])["conflicts_with_legacy_id"] == 1
    assert conflict[0][2] == "legacy"
    booked = con.execute("SELECT imported_id FROM imports WHERE"
                         " source_kind='stats_db' ORDER BY rowid").fetchall()
    con.close()
    assert [b[0].split(":")[0].split("-")[0] for b in booked] == \
        ["legacy_dictations", "legacy_dictations", "art",
         "legacy_dictations"]
    # Rerun is idempotent for every source.
    for p in ("a.db", "b.db", "c.db"):
        r = imp.import_stats_db(td / p)
        assert r["rows_imported"] == r["rows_conflicted"] == 0
    # Legacy prune never removes the preserved conflict row.
    st.prune(now=1e10)
    assert st.verify()["ok"]
    st.close()
    print("ok  11 same id/different content preserved as a legacy conflict"
          " artifact and reported; identical duplicate recognized; totals"
          " unchanged")


def test_stats_row_and_bookkeeping_are_one_op():
    td, st, imp = env()
    stats_db(td / "a.db", [ROW_A, ROW_C])
    real = store.Store.import_legacy_stats_row
    calls = {"n": 0}

    def failing(self, row, sha, locator):
        calls["n"] += 1
        if row["id"] == 2:
            def op():
                self._db.execute(
                    "INSERT INTO imports(source_kind, source_sha256,"
                    " source_locator, imported_id, imported_at_utc)"
                    " VALUES('stats_db',?,?,'x','t')", (sha, locator))
                raise sqlite3.OperationalError("injected row failure")
            return self._submit(op, wait=True)
        return real(self, row, sha, locator)
    store.Store.import_legacy_stats_row = failing
    try:
        try:
            imp.import_stats_db(td / "a.db")
            raise AssertionError("failure must surface")
        except RuntimeError:
            pass
    finally:
        store.Store.import_legacy_stats_row = real
    con = sqlite3.connect(st.db_path)
    booked = con.execute("SELECT source_locator FROM imports").fetchall()
    con.close()
    assert booked == [("row:1",)], booked  # no bookkeeping without data
    r = imp.import_stats_db(td / "a.db")
    assert r["rows_imported"] == 1 and r["rows_skipped"] == 1
    assert st.legacy_totals()[0] == 2
    st.close()
    print("ok  11 a failed row op rolls back its bookkeeping; rerun repairs")


def main():
    tests = [test_interrupted_import_then_growth_imports_each_pair_once,
             test_interrupted_twice_across_multiple_prefixes,
             test_stats_id_conflict_preserved_and_reported,
             test_stats_row_and_bookkeeping_are_one_op]
    for t in tests:
        t()
    print(f"all m02 remediation import tests passed ({len(tests)})")


if __name__ == "__main__":
    main()
