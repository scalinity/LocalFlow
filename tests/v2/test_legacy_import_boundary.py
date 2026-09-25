"""M01 remediation: parser -> importer boundary (M01-AUDIT-07/08).

Drives localflow/v2/importer.py::LegacyImporter.import_log with synthetic
logs to prove, through the importer-facing interface:

- an incomplete end-of-file tail is not imported; once the log grows and
  the pair completes, the completed content is imported exactly once and
  a further re-import adds nothing;
- a store written by the pre-remediation importer (which stored the
  truncated tail) gets the completed pair once, linked to the old identity,
  while the old artifact stays immutable;
- stored payloads are the exact bytes (indentation, blank lines, trailing
  whitespace) with the derivation recorded, and identities keep the
  frozen ``legacy:<source-sha>:<raw_line>-<cleaned_line>`` form with
  unknown dates.

Expected strings are written by hand. Needs numpy (the V2 store imports
it); run with the project interpreter:

Run: .venv/bin/python tests/v2/test_legacy_import_boundary.py
"""

import hashlib
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from localflow.v2 import importer, store  # noqa: E402

HEAD = ("[localflow] ready — hold fn to dictate, release to insert text.\n"
        "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n")
TAIL = HEAD + ("[localflow] raw:     alpha beta\n"
               "gamma\n"
               "[localflow] cleaned: Alpha beta\n")
REST = ("gamma delta.\n"
        "[localflow] timing: stt 0.1s, cleanup 0.2s\n"
        "[localflow] inserted 20 chars\n")


def env():
    td = pathlib.Path(tempfile.mkdtemp())
    st = store.Store(td / "v2.db", backup_dir=td / "backups")
    return td, st, importer.LegacyImporter(st, td / "backups")


def legacy_rows(st):
    st.sync()
    con = sqlite3.connect(st.db_path)
    rows = con.execute(
        "SELECT role, content_text, meta_json FROM artifacts"
        " WHERE stage='legacy_log' ORDER BY created_at_utc, artifact_id"
    ).fetchall()
    con.close()
    return [(r, t, json.loads(m)) for r, t, m in rows]


def test_incomplete_tail_then_completion_imports_once():
    td, st, imp = env()
    log = td / "LocalFlow.log"
    log.write_text(TAIL)
    r1 = imp.import_log(log)
    assert r1["pairs_imported"] == 0 and r1["pairs_deferred_incomplete"] == 1, r1
    assert legacy_rows(st) == []
    log.write_text(TAIL + REST)  # the app finished writing
    r2 = imp.import_log(log)
    assert r2["pairs_imported"] == 1 and r2["pairs_deferred_incomplete"] == 0, r2
    assert r2["prefix_reconciled"] is not None
    rows = legacy_rows(st)
    cleaned = [t for role, t, _ in rows if role == "cleaned_transcript"]
    assert cleaned == ["Alpha beta\ngamma delta."], cleaned
    r3 = imp.import_log(log)
    assert r3["pairs_imported"] == 0 and r3["pairs_skipped"] == 1, r3
    assert len(legacy_rows(st)) == 2  # one raw + one cleaned, exactly once
    st.close()
    print("ok  incomplete EOF tail deferred; completed content imported once")


def test_pre_remediation_partial_tail_is_completed_not_lost():
    td, st, imp = env()
    log = td / "LocalFlow.log"
    log.write_text(TAIL)
    data = log.read_bytes()
    old_sha = hashlib.sha256(data).hexdigest()
    # What the pre-remediation importer stored: the truncated tail pair.
    st.import_legacy_pair(
        raw_text="alpha beta\ngamma", cleaned_text="Alpha beta",
        raw_meta={"identity": f"legacy:{old_sha}:3-5", "time_quality": "unknown"},
        cleaned_meta={"identity": f"legacy:{old_sha}:3-5",
                      "time_quality": "unknown"},
        source_kind=importer.KIND_LOG, source_sha=old_sha, locator="lines:3-5")
    st.record_import_run(importer.KIND_LOG, old_sha, len(data), log, 1, 0)
    st.sync()
    log.write_text(TAIL + REST)
    r = imp.import_log(log)
    assert r["pairs_imported"] == 1 and r["prior_partial_tails_completed"] == 1, r
    rows = legacy_rows(st)
    cleaned = [(t, m) for role, t, m in rows if role == "cleaned_transcript"]
    assert [t for t, _ in cleaned] == ["Alpha beta", "Alpha beta\ngamma delta."]
    new_meta = cleaned[1][1]
    assert new_meta["completes_prior_partial_identity"] == f"legacy:{old_sha}:3-5"
    new_sha = hashlib.sha256(log.read_bytes()).hexdigest()
    assert new_meta["identity"] == f"legacy:{new_sha}:3-5"
    assert imp.import_log(log)["pairs_imported"] == 0
    st.close()
    print("ok  pre-remediation truncated tail kept immutable; completion linked")


def _old_importer_stores(st, text, pairs, log):
    """Simulate a pre-remediation importer run: stored every listed pair
    (truncated tails included) under this text's sha, then its run row."""
    data = text.encode()
    sha = hashlib.sha256(data).hexdigest()
    for raw_line, cleaned_line, raw, cleaned in pairs:
        loc = f"lines:{raw_line}-{cleaned_line}"
        st.import_legacy_pair(
            raw_text=raw, cleaned_text=cleaned,
            raw_meta={"identity": f"legacy:{sha}:{loc[6:]}", "time_quality": "unknown"},
            cleaned_meta={"identity": f"legacy:{sha}:{loc[6:]}",
                          "time_quality": "unknown"},
            source_kind=importer.KIND_LOG, source_sha=sha, locator=loc)
    st.record_import_run(importer.KIND_LOG, sha, len(data), log,
                         len(pairs), 0)
    st.sync()
    return sha


def test_partial_tail_then_old_skip_then_new_import_completes_it():
    # Old importer: tail stored truncated; old importer again on the
    # completed log skipped it by coordinates (never storing it complete);
    # the new importer must still import the completed content once.
    td, st, imp = env()
    log = td / "LocalFlow.log"
    old_sha = _old_importer_stores(st, TAIL, [(3, 5, "alpha beta\ngamma", "Alpha beta")], log)
    _old_importer_stores(st, TAIL + REST, [], log)  # skipped by coordinates
    log.write_text(TAIL + REST)
    r = imp.import_log(log)
    assert r["pairs_imported"] == 1 and r["prior_partial_tails_completed"] == 1, r
    cleaned = [(t, m) for role, t, m in legacy_rows(st) if role == "cleaned_transcript"]
    assert [t for t, _ in cleaned] == ["Alpha beta", "Alpha beta\ngamma delta."]
    assert cleaned[1][1]["completes_prior_partial_identity"] == f"legacy:{old_sha}:3-5"
    assert imp.import_log(log)["pairs_imported"] == 0
    st.close()
    print("ok  completion found although a later old run skipped it by coordinates")


def test_partial_linked_across_an_intermediate_growing_prefix():
    # Old importer stored the tail; the new importer then saw a still-
    # growing prefix (deferred); the final import must link to the OLD
    # prefix's identity, not the intermediate one.
    td, st, imp = env()
    log = td / "LocalFlow.log"
    old_sha = _old_importer_stores(st, TAIL, [(3, 5, "alpha beta\ngamma", "Alpha beta")], log)
    log.write_text(TAIL + "gamma")
    mid = imp.import_log(log)
    assert mid["pairs_imported"] == 0 and mid["pairs_deferred_incomplete"] == 1, mid
    assert mid["prior_partial_tails_completed"] == 0, mid
    log.write_text(TAIL + REST)
    r = imp.import_log(log)
    assert r["pairs_imported"] == 1 and r["prior_partial_tails_completed"] == 1, r
    cleaned = [m for role, t, m in legacy_rows(st) if role == "cleaned_transcript"]
    assert cleaned[-1]["completes_prior_partial_identity"] == f"legacy:{old_sha}:3-5"
    st.close()
    print("ok  partial linked to the run that stored it, across growing prefixes")


def test_exact_payloads_reach_the_store():
    td, st, imp = env()
    log = td / "LocalFlow.log"
    log.write_text(HEAD
                   + "[localflow] raw:     def f():\n"
                   + "    return 1  \n"
                   + "\n"
                   + "end  \n"
                   + "[localflow] cleaned:   Kept.\t\n"
                   + "[localflow] timing: stt 0.1s, cleanup 0.1s\n"
                   + "[localflow] inserted 9 chars\n")
    imp.import_log(log)
    rows = {role: (t, m) for role, t, m in legacy_rows(st)}
    raw, raw_meta = rows["raw_transcript"]
    cleaned, meta = rows["cleaned_transcript"]
    assert raw == "def f():\n    return 1  \n\nend  "
    assert cleaned == "  Kept.\t"
    sha = hashlib.sha256(log.read_bytes()).hexdigest()
    assert meta["identity"] == f"legacy:{sha}:3-7"
    assert meta["time_quality"] == "unknown"
    assert meta["payload_derivation"] == "e02-exact-payload-v2"
    assert raw_meta["physical_line_span"] == [3, 6]
    assert meta["timing"] == {"stt": 0.1, "cleanup": 0.1}
    st.close()
    print("ok  exact payload bytes stored with derivation; identity unchanged")


def test_repeated_identical_utterances_import_as_distinct_identities():
    td, st, imp = env()
    rec = ("[localflow] raw:     same words\n"
           "[localflow] cleaned: Same words.\n"
           "[localflow] timing: stt 0.1s, cleanup 0.1s\n"
           "[localflow] inserted 11 chars\n")
    log = td / "LocalFlow.log"
    log.write_text(HEAD + rec + rec)
    r = imp.import_log(log)
    assert r["pairs_imported"] == 2
    ids = {m["identity"] for _, _, m in legacy_rows(st)}
    sha = hashlib.sha256(log.read_bytes()).hexdigest()
    assert ids == {f"legacy:{sha}:3-4", f"legacy:{sha}:7-8"}, ids
    st.close()
    print("ok  identical utterances -> distinct legacy identities")


if __name__ == "__main__":
    test_incomplete_tail_then_completion_imports_once()
    test_pre_remediation_partial_tail_is_completed_not_lost()
    test_partial_tail_then_old_skip_then_new_import_completes_it()
    test_partial_linked_across_an_intermediate_growing_prefix()
    test_exact_payloads_reach_the_store()
    test_repeated_identical_utterances_import_as_distinct_identities()
    print("all legacy import boundary tests passed (6)")
