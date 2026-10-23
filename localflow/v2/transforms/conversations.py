"""Local prompt sessions and append-only canonical revisions.

All database access goes through the existing Store writer. Session version
numbers are monotonic even when the canonical pointer moves backwards, so a
revert cannot accidentally admit an old in-flight completion.
"""

from __future__ import annotations

import hashlib
import json

from .. import ids


INTELLIGENCE_MIGRATIONS = tuple(statement.strip() for statement in """
CREATE TABLE IF NOT EXISTS prompt_sessions (
 session_id TEXT PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL,
 source TEXT NOT NULL, definition_json TEXT NOT NULL, policy_json TEXT NOT NULL,
 revision INTEGER NOT NULL, canonical_revision INTEGER NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prompt_revisions (
 session_id TEXT NOT NULL REFERENCES prompt_sessions(session_id),
 revision_id INTEGER NOT NULL, parent_revision INTEGER, base_version INTEGER,
 prompt TEXT NOT NULL, instruction TEXT NOT NULL, commentary TEXT NOT NULL,
 context_json TEXT NOT NULL, result_json TEXT NOT NULL, kind TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(session_id, revision_id));
CREATE TABLE IF NOT EXISTS intelligence_jobs (
 job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, target_id TEXT,
 status TEXT NOT NULL, phase TEXT NOT NULL, sequence INTEGER NOT NULL,
 manifest_json TEXT NOT NULL, events_json TEXT NOT NULL,
 result_json TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transform_authoring (
 draft_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
 intention TEXT NOT NULL, policy_json TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transform_authoring_revisions (
 draft_id TEXT NOT NULL REFERENCES transform_authoring(draft_id),
 revision INTEGER NOT NULL, definition_json TEXT NOT NULL,
 instruction TEXT NOT NULL, tests_json TEXT NOT NULL,
 context_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(draft_id, revision));
CREATE TABLE IF NOT EXISTS intelligence_suggestions (
 suggestion_id TEXT PRIMARY KEY, candidate_json TEXT NOT NULL,
 evidence_json TEXT NOT NULL, status TEXT NOT NULL, cooldown_until REAL,
 updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS intelligence_saves (
 operation_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL,
 draft_revision INTEGER NOT NULL, transform_id TEXT NOT NULL UNIQUE,
 request_fingerprint TEXT NOT NULL);
""".split(";") if statement.strip())


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def submit(store, operation):
    """Preserve domain refusals across Store's content-free exception wrapper."""
    try:
        return store.submit(operation)
    except RuntimeError as exc:
        if str(exc).startswith("ValueError: "):
            raise ValueError(str(exc)[12:]) from exc
        raise


def bounded_text(value, limit=12000, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise ValueError("invalid_text")
    if not empty and not value.strip():
        raise ValueError("empty_text")
    return value


class PromptSessions:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _read(db, session_id):
        row = db.execute(
            "SELECT session_id,source,definition_json,policy_json,revision,"
            "canonical_revision FROM prompt_sessions WHERE session_id=?",
            (session_id,)).fetchone()
        if row is None:
            raise ValueError("session_not_found")
        revisions = []
        for rev in db.execute(
                "SELECT revision_id,parent_revision,base_version,prompt,"
                "instruction,commentary,context_json,result_json,kind,created_at"
                " FROM prompt_revisions WHERE session_id=? ORDER BY revision_id",
                (session_id,)):
            revisions.append(dict(zip(
                ("revision_id", "parent_revision", "base_version", "prompt",
                 "instruction", "commentary", "context", "result", "kind",
                 "created_at"), rev)))
        for rev in revisions:
            rev["context"] = json.loads(rev["context"])
            rev["result"] = json.loads(rev["result"])
        current = next(r for r in revisions if r["revision_id"] == row[5])
        return {"id": row[0], "session_id": row[0], "source": row[1],
                "definition": json.loads(row[2]), "policy": json.loads(row[3]),
                "revision": row[4], "canonical_revision": row[5],
                "prompt": current["prompt"], "revisions": revisions}

    def create(self, source, definition, policy, operation_id):
        bounded_text(source)
        bounded_text(operation_id, 100)
        session_id = "ps:" + fingerprint(operation_id)[:32]
        now = ids.now_utc_iso()

        def op(db):
            have = db.execute("SELECT session_id FROM prompt_sessions WHERE"
                              " operation_id=?", (operation_id,)).fetchone()
            if have:
                old = self._read(db, have[0])
                if (old["source"] != source or old["definition"] != definition
                        or old["policy"] != policy):
                    raise ValueError("operation_id_in_use")
                return old
            db.execute("INSERT INTO prompt_sessions VALUES(?,?,?,?,?,1,1,?,?)",
                       (session_id, operation_id, source, encode(definition),
                        encode(policy), now, now))
            db.execute("INSERT INTO prompt_revisions VALUES(?,1,NULL,0,?,'','',"
                       "'{}','{}','source',?)", (session_id, source, now))
            return self._read(db, session_id)
        return submit(self.store, op)

    def read(self, session_id):
        return submit(self.store, lambda db: self._read(db, session_id))

    def list(self):
        return submit(self.store, lambda db: [
            {"session_id": r[0], "id": r[0], "revision": r[1],
             "canonical_revision": r[2], "updated_at": r[3], "source": r[4]}
            for r in db.execute("SELECT session_id,revision,canonical_revision,"
                                "updated_at,substr(source,1,100) FROM prompt_sessions"
                                " ORDER BY updated_at DESC LIMIT 100")])

    def set_policy(self, session_id, expected_revision, policy):
        def op(db):
            session = self._read(db, session_id)
            if session["revision"] != expected_revision:
                raise ValueError("stale_revision")
            db.execute("UPDATE prompt_sessions SET policy_json=?,revision=revision+1,"
                       "updated_at=? WHERE session_id=?", (encode(policy),
                       ids.now_utc_iso(), session_id))
            return self._read(db, session_id)
        return submit(self.store, op)

    def clear(self, session_id, expected_revision):
        def op(db):
            if self._read(db, session_id)["revision"] != expected_revision:
                raise ValueError("stale_revision")
            db.execute("DELETE FROM prompt_revisions WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM prompt_sessions WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM intelligence_jobs WHERE target_id=?", (session_id,))
            return {"cleared": True}
        return submit(self.store, op)

    def append(self, session_id, expected_revision, prompt, *,
               base_revision=None, instruction="", commentary="", context=None,
               result=None, kind="manual", keep_alternative=False, validate=None):
        bounded_text(prompt)
        bounded_text(instruction, 8000, empty=True)
        bounded_text(commentary, 4000, empty=True)

        def op(db):
            session = self._read(db, session_id)
            # Validation and publication share the writer transaction with
            # source deletion; no read/check/write gap can restore evidence.
            if validate is not None and not validate(db, context or {}):
                raise ValueError("context_revoked")
            current = session["revision"] == expected_revision
            if not current and not keep_alternative:
                raise ValueError("stale_revision")
            parent = (session["canonical_revision"] if base_revision is None
                      else base_revision)
            if parent not in {r["revision_id"] for r in session["revisions"]}:
                raise ValueError("revision_not_found")
            revision = session["revisions"][-1]["revision_id"] + 1
            now = ids.now_utc_iso()
            db.execute("INSERT INTO prompt_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (session_id, revision, parent, expected_revision, prompt,
                        instruction, commentary, encode(context or {}),
                        encode(result or {}), kind, now))
            if current:
                db.execute("UPDATE prompt_sessions SET revision=revision+1,"
                           "canonical_revision=?,updated_at=? WHERE session_id=?",
                           (revision, now, session_id))
            return {"session": self._read(db, session_id),
                    "revision_id": revision, "published": current,
                    "superseded": not current}
        return submit(self.store, op)

    def select(self, session_id, expected_revision, revision_id, *, validate=None):
        def op(db):
            session = self._read(db, session_id)
            if session["revision"] != expected_revision:
                raise ValueError("stale_revision")
            if revision_id not in {r["revision_id"] for r in session["revisions"]}:
                raise ValueError("revision_not_found")
            selected = next(r for r in session["revisions"]
                            if r["revision_id"] == revision_id)
            if validate is not None and not validate(db, selected["context"]):
                raise ValueError("context_revoked")
            db.execute("UPDATE prompt_sessions SET canonical_revision=?,"
                       "revision=revision+1,updated_at=? WHERE session_id=?",
                       (revision_id, ids.now_utc_iso(), session_id))
            return self._read(db, session_id)
        return submit(self.store, op)

    @staticmethod
    def instructions(session):
        """Explicit user edits on the selected branch; no assistant summaries."""
        by_id = {r["revision_id"]: r for r in session["revisions"]}
        instructions = []
        current = by_id[session["canonical_revision"]]
        while current:
            if current["instruction"]:
                instructions.append(current["instruction"])
            current = by_id.get(current["parent_revision"])
        return tuple(reversed(instructions))
