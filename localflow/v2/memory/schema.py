"""Additive SQL registered by the application Store's versioned migration.

Importing or constructing MemoryStore never changes the schema.
"""

MEMORY_MIGRATIONS = [
    """CREATE TABLE IF NOT EXISTS memory_projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, root TEXT NOT NULL UNIQUE,
        revision INTEGER NOT NULL, created_at REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS memory_roots (
        project_id TEXT NOT NULL REFERENCES memory_projects(id),
        root TEXT PRIMARY KEY)""",
    """CREATE TABLE IF NOT EXISTS memory_state (key TEXT PRIMARY KEY, value INTEGER NOT NULL)""",
    "INSERT OR IGNORE INTO memory_state VALUES ('revocation', 0), ('learning', 0)",
    """CREATE TABLE IF NOT EXISTS memory_sources (
        id TEXT PRIMARY KEY, revision INTEGER NOT NULL, text TEXT NOT NULL,
        content_hash TEXT NOT NULL, project_id TEXT, status TEXT NOT NULL,
        expires_at REAL, data TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS memory_records (
        id TEXT PRIMARY KEY, revision INTEGER NOT NULL, kind TEXT NOT NULL,
        scope_id TEXT, subject TEXT NOT NULL, predicate TEXT NOT NULL,
        text TEXT NOT NULL, status TEXT NOT NULL, valid_until REAL,
        updated_at REAL NOT NULL, data TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS memory_scope ON memory_records(scope_id, status)",
    """CREATE TABLE IF NOT EXISTS memory_evidence (
        memory_id TEXT NOT NULL REFERENCES memory_records(id) ON DELETE CASCADE,
        source_id TEXT NOT NULL REFERENCES memory_sources(id),
        source_revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
        span_start INTEGER NOT NULL, span_end INTEGER NOT NULL,
        PRIMARY KEY(memory_id, source_id))""",
    "CREATE INDEX IF NOT EXISTS memory_source_links ON memory_evidence(source_id)",
    """CREATE TABLE IF NOT EXISTS memory_revisions (
        memory_id TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL,
        PRIMARY KEY(memory_id, revision))""",
    """CREATE TABLE IF NOT EXISTS memory_suppressed (
        source_id TEXT NOT NULL, content_hash TEXT NOT NULL,
        PRIMARY KEY(source_id, content_hash))""",
    """CREATE TABLE IF NOT EXISTS memory_exclusions (
        kind TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(kind, value))""",
    """CREATE TABLE IF NOT EXISTS memory_dirty (
        source_id TEXT PRIMARY KEY, source_revision INTEGER NOT NULL,
        revocation INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS memory_vectors (
        memory_id TEXT PRIMARY KEY REFERENCES memory_records(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL, implementation TEXT NOT NULL, vector BLOB NOT NULL)""",
    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(memory_id UNINDEXED, text, tokenize='porter unicode61')",
]
