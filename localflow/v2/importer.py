"""Lossless import of legacy user data into the V2 store (Spec S08, M02-AC02/03).

Sources: the live ``stats.db`` (7 analytics rows with real UTC instants),
``dictionary.json`` (7 terms), ``transforms.json`` (2 definitions) and the
append-only legacy text log. Nothing is rebuilt or transformed: rows are
copied verbatim, JSON definitions become immutable legacy-revision
artifacts, and log pairs import as unknown-date historical artifacts with
identity ``legacy:<source-sha>:<line-range>`` (contracts/jobs.md).

stats.db is imported from a verified SQLite-backup copy, never from the
live file. The legacy log import reconciles appended versions by verifying
previous source hashes as byte prefixes of the new content, so a re-import
adds zero rows and a grown log imports only its new pairs.
"""

import hashlib
import json
import pathlib
import sqlite3
import sys

from . import ids

KIND_STATS = "stats_db"
KIND_DICT = "dictionary_json"
KIND_TRANSFORMS = "transforms_json"
KIND_LOG = "legacy_log"


def _parser():
    """The M01 E02 parser. Imported lazily: the parser lives in scripts/
    (not bundled into the app), and only the import CLI/tests — never the
    running app — reach this path."""
    import importlib

    root = pathlib.Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module("scripts.v2.parse_legacy_log")


def _iter_pairs(text):
    """E02 pairing protocol from the M01 parser."""
    return _parser().iter_pairs(text)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def backup_sqlite(src: pathlib.Path, dst_dir: pathlib.Path) -> pathlib.Path:
    """Consistent snapshot via the SQLite backup API (Spec S08 [T01])."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{src.name}.{ids.new_id('backup')[:14]}.bak"
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dst)
        try:
            con.backup(target)
        finally:
            target.close()
    finally:
        con.close()
    return dst


class LegacyImporter:
    def __init__(self, store, backup_dir):
        self.store = store
        self.backup_dir = pathlib.Path(backup_dir)

    # ---- stats.db ------------------------------------------------------

    def import_stats_db(self, path) -> dict:
        path = pathlib.Path(path)
        backup = backup_sqlite(path, self.backup_dir)
        # Identity follows the bytes actually read (the verified backup), so
        # a concurrent mutation of the live file cannot desync hash and rows.
        backup_bytes = backup.read_bytes()
        data_hash = sha256_bytes(backup_bytes)
        con = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
        imported = skipped = 0
        try:
            rows = [dict(zip(
                ("id", "ts", "duration_sec", "raw_text", "cleaned_text",
                 "raw_words", "cleaned_words", "fixed_words", "wpm",
                 "app_name", "app_bundle", "kind"), r))
                for r in con.execute(
                    "SELECT id, ts, duration_sec, raw_text, cleaned_text,"
                    " raw_words, cleaned_words, fixed_words, wpm, app_name,"
                    " app_bundle, kind FROM dictations ORDER BY id")]
        finally:
            con.close()
        for row in rows:
            locator = f"row:{row['id']}"
            if self.store.has_import(KIND_STATS, data_hash, locator):
                skipped += 1
                continue
            self.store.insert_legacy_dictation(row, data_hash)
            self.store.record_import(KIND_STATS, data_hash, locator,
                                     f"legacy_dictations:{row['id']}",
                                     time_quality="known")
            imported += 1
        self.store.sync()
        self.store.record_import_run(
            KIND_STATS, data_hash, path.stat().st_size, path,
            imported, skipped, note=f"from verified backup {backup.name}")
        return {"source": str(path), "sha256": data_hash,
                "rows_imported": imported, "rows_skipped": skipped,
                "backup": str(backup)}

    # ---- dictionary / transforms ----------------------------------------

    def import_dictionary(self, path) -> dict:
        path = pathlib.Path(path)
        data = path.read_bytes()
        data_hash = sha256_bytes(data)
        terms = json.loads(data.decode("utf-8")).get("terms", [])
        # Identity is whole-file-hash keyed: editing the source later
        # re-imports every term as a new legacy revision rather than
        # replacing the old ones (append-only by design, Spec S08).
        imported = skipped = 0
        for term in terms:
            locator = f"term:{ids.sha256_text(term)[:16]}"
            if self.store.import_legacy_text(
                    text=term, role="legacy_dictionary_term",
                    kind="legacy_dictionary_term", retention_class="legacy",
                    meta=None, source_kind=KIND_DICT, source_sha=data_hash,
                    locator=locator, time_quality="unknown") is None:
                skipped += 1
            else:
                imported += 1
        self.store.sync()
        self.store.record_import_run(KIND_DICT, data_hash, len(data), path,
                                     imported, skipped)
        return {"source": str(path), "sha256": data_hash, "terms": len(terms),
                "imported": imported, "skipped": skipped}

    def import_transforms(self, path) -> dict:
        path = pathlib.Path(path)
        data = path.read_bytes()
        data_hash = sha256_bytes(data)
        defs = json.loads(data.decode("utf-8"))
        imported = skipped = 0
        for d in defs:
            locator = f"transform:{d.get('key')}"
            if self.store.import_legacy_text(
                    text=json.dumps(d, ensure_ascii=False, indent=1),
                    role="legacy_transform_definition",
                    kind="legacy_transform_definition",
                    retention_class="legacy", meta=None,
                    source_kind=KIND_TRANSFORMS, source_sha=data_hash,
                    locator=locator, time_quality="unknown") is None:
                skipped += 1
            else:
                imported += 1
        self.store.sync()
        self.store.record_import_run(KIND_TRANSFORMS, data_hash, len(data),
                                     path, imported, skipped)
        return {"source": str(path), "sha256": data_hash,
                "definitions": len(defs), "imported": imported,
                "skipped": skipped}

    # ---- legacy text log ---------------------------------------------------

    def import_log(self, path) -> dict:
        """Import raw/cleaned pairs as unknown-date historical artifacts.
        Idempotent per source hash; an appended log reconciles by verified
        byte prefix and imports only its new pairs (Spec S08)."""
        path = pathlib.Path(path)
        data = path.read_bytes()  # single read of an append-only file
        data_hash = sha256_bytes(data)
        parser = _parser()
        text, decode = parser.decode_log_bytes(data)

        # M01 remediation (M01-AUDIT-07): every earlier import run whose
        # bytes are a verified prefix of this file is consulted (not only
        # the longest). A pair counts as already imported only when some
        # run stored it while it was COMPLETE in that run's bytes; a pair
        # a run stored while it was still an end-of-file tail (only the
        # pre-remediation importer did that) is imported again from the
        # completed bytes and records which identity it completes — the
        # old artifact stays immutable.
        prefix_runs = sorted(
            ((sha, n) for sha, n in self.store.import_run_bytes(KIND_LOG).items()
             if n <= len(data) and sha256_bytes(data[:n]) == sha),
            key=lambda kv: kv[1])
        prefix_sha = prefix_runs[-1][0] if prefix_runs else None
        skip_pairs = set()
        prior_partial = {}
        for prev_sha, prev_len in prefix_runs:
            prefix_text, _ = parser.decode_log_bytes(data[:prev_len])
            for p in _iter_pairs(prefix_text):
                key = (p["raw_line"], p["cleaned_line"])
                if not self.store.has_import(
                        KIND_LOG, prev_sha, f"lines:{key[0]}-{key[1]}"):
                    continue
                if p.get("complete", True):
                    skip_pairs.add(key)
                else:
                    prior_partial.setdefault(
                        key, f"legacy:{prev_sha}:{key[0]}-{key[1]}")

        imported = skipped = deferred = completed_partials = 0
        for pair in _iter_pairs(text):
            line_range = f"{pair['raw_line']}-{pair['cleaned_line']}"
            locator = f"lines:{line_range}"
            key = (pair["raw_line"], pair["cleaned_line"])
            if key in skip_pairs:
                skipped += 1
                continue
            if not pair.get("complete", True):
                # Still-growing tail: imported once it is complete.
                deferred += 1
                continue
            identity = f"legacy:{data_hash}:{line_range}"
            base_meta = {
                "identity": identity,
                "segment": pair["segment"],
                "cleanup_state": pair["cleanup_state"],
                "time_quality": "unknown",
                "payload_derivation": pair.get("payload_derivation"),
            }
            if pair.get("decode_uncertain"):
                base_meta["decode_uncertain"] = True
            if key in prior_partial:
                base_meta["completes_prior_partial_identity"] = \
                    prior_partial[key]
            # Candidate audio association from the E02 heuristic;
            # explicitly unverified — never a claimed join.
            result = self.store.import_legacy_pair(
                raw_text=pair.get("_raw_exact", pair["_raw"]),
                cleaned_text=pair.get("_cleaned_exact", pair["_cleaned"]),
                raw_meta={**base_meta, "physical_lines": [pair["raw_line"]],
                          "physical_line_span": pair.get("raw_lines"),
                          "framing": (pair.get("framing") or {}).get("raw")},
                cleaned_meta={
                    **base_meta, "physical_lines": [pair["cleaned_line"]],
                    "physical_line_span": pair.get("cleaned_lines"),
                    "framing": (pair.get("framing") or {}).get("cleaned"),
                    "timing": pair["timing"],
                    "inserted_chars": pair["inserted_chars"],
                    "candidate_audio_line_unverified":
                        (pair.get("audio") or {}).get("line")},
                source_kind=KIND_LOG, source_sha=data_hash, locator=locator)
            if result is None:
                skipped += 1
            else:
                imported += 1
                if key in prior_partial:
                    completed_partials += 1
        self.store.sync()
        self.store.record_import_run(
            KIND_LOG, data_hash, len(data), path, imported, skipped,
            note=f"prefix_reconciled={prefix_sha or 'none'};"
                 f" deferred_incomplete={deferred};"
                 f" payload_derivation={parser.PAYLOAD_DERIVATION};"
                 f" decode_replaced={decode['replaced_sequences']}")
        return {"source": str(path), "sha256": data_hash,
                "bytes": len(data), "pairs_imported": imported,
                "pairs_skipped": skipped,
                "pairs_deferred_incomplete": deferred,
                "prior_partial_tails_completed": completed_partials,
                "decode": decode,
                "payload_derivation": parser.PAYLOAD_DERIVATION,
                "prefix_reconciled": prefix_sha or None}
