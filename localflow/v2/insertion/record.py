"""Insertion/observation persistence (store schema v4, M08).

All writes go through ``Store.submit`` — the sanctioned writer-thread
entry point for same-package domain layers (contracts/store.md), so
the single-writer discipline holds. Content-bearing payloads
(before/after owned-range texts) are separate lease-governed
artifacts; these rows carry ids, ranges, counts and reasons only.
"""

from __future__ import annotations

import json

from .. import ids


def record_insertion(store, result) -> str:
    """Insert one insertion-transaction row (idempotent by primary key)."""
    now = ids.now_utc_iso()

    def op(conn):
        conn.execute(
            "INSERT OR REPLACE INTO insertions(insertion_id, job_id,"
            " attempt, target_snapshot_id, context_snapshot_id, method,"
            " state, reason_code, verification_json, owned_start,"
            " owned_end, inserted_chars, clipboard_json, created_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (result.insertion_id, result.job_id, result.attempt,
             result.target_snapshot_id, result.context_snapshot_id,
             result.method, result.state, result.reason_code,
             json.dumps(result.verification, ensure_ascii=False),
             result.owned_start, result.owned_end, result.inserted_chars,
             json.dumps(result.clipboard, ensure_ascii=False,
                        default=str),
             now))
        return result.insertion_id
    store.submit(op)
    return result.insertion_id


def open_observation(store, insertion_id: str, job_id) -> str:
    observation_id = ids.new_id("obs")
    now = ids.now_utc_iso()

    def op(conn):
        conn.execute(
            "INSERT INTO insertion_observations(observation_id,"
            " insertion_id, job_id, started_at_utc) VALUES(?,?,?,?)",
            (observation_id, insertion_id, job_id, now))
        return observation_id
    store.submit(op)
    return observation_id


def close_observation(store, observation_id: str, *, stop_reason: str,
                      edited: bool, reanchors: int, ticks: int,
                      before_artifact_id=None, after_artifact_id=None,
                      meta: dict | None = None):
    now = ids.now_utc_iso()

    def op(conn):
        conn.execute(
            "UPDATE insertion_observations SET stopped_at_utc=?,"
            " stop_reason=?, edited=?, reanchors=?, ticks=?,"
            " before_artifact_id=?, after_artifact_id=?, meta_json=?"
            " WHERE observation_id=?",
            (now, stop_reason, 1 if edited else 0, int(reanchors),
             int(ticks), before_artifact_id, after_artifact_id,
             json.dumps(meta or {}, ensure_ascii=False), observation_id))
    store.submit(op)
