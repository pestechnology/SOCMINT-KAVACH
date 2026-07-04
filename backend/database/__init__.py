"""
backend/database/__init__.py — SQLite layer (stdlib sqlite3, no ORM).

Exposes:
    init_db()  -> creates the 6 tables + indexes (idempotent)
    get_db()   -> sqlite3.Connection with row_factory = sqlite3.Row

Schema is exactly Section 6.2 of the Master Architecture:
    users, cases, entities, clusters, audit_ledger, artifacts
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'investigator',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    seeds_json TEXT NOT NULL,
    minor_involved INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    country_filter TEXT DEFAULT 'ALL',
    case_context TEXT DEFAULT '',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    type TEXT,
    value TEXT,
    platform TEXT,
    confidence REAL,
    metadata_json TEXT,
    source_url TEXT,
    data_mode TEXT,
    sha256 TEXT,
    created_at TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS clusters (
    cluster_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    entity_ids_json TEXT NOT NULL,
    confidence_score REAL,
    tier TEXT,
    explanation TEXT,
    signals_json TEXT,
    created_at TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS audit_ledger (
    ledger_id TEXT PRIMARY KEY,
    case_id TEXT,
    action TEXT,
    search_id TEXT,
    input_hash TEXT,
    output_hash TEXT,
    previous_hash TEXT,
    chain_hash TEXT,
    actor TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    case_id TEXT,
    entity_id TEXT,
    artifact_type TEXT,
    file_path TEXT,
    sha256 TEXT,
    captured_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_entities_case ON entities(case_id);
CREATE INDEX IF NOT EXISTS idx_entities_value ON entities(value);
CREATE INDEX IF NOT EXISTS idx_clusters_case ON clusters(case_id);
CREATE INDEX IF NOT EXISTS idx_ledger_case ON audit_ledger(case_id);
"""


def get_db() -> sqlite3.Connection:
    """Return a connection with Row factory, FKs, and a busy timeout.

    busy_timeout makes concurrent access (the background orchestrator writing
    while the frontend polls results) wait-and-retry instead of immediately
    raising 'database is locked'. timeout= covers the Python-side lock wait too.
    """
    conn = sqlite3.connect(config.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 10000;")  # 10s wait on a locked DB
    return conn


def init_db() -> None:
    """Create all tables and indexes. Safe to call repeatedly."""
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        # WAL lets readers (polling) and a writer (orchestrator) proceed concurrently.
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript(_SCHEMA)
        # Migration: older DBs predate the audit_ledger.chain_hash column (which
        # seals each row — including the last — against silent tampering). Add it
        # if absent. CREATE TABLE IF NOT EXISTS never alters an existing table.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_ledger)").fetchall()]
        if "chain_hash" not in cols:
            conn.execute("ALTER TABLE audit_ledger ADD COLUMN chain_hash TEXT")
        cols_cases = [r[1] for r in conn.execute("PRAGMA table_info(cases)").fetchall()]
        if "country_filter" not in cols_cases:
            conn.execute("ALTER TABLE cases ADD COLUMN country_filter TEXT DEFAULT 'ALL'")
        if "case_context" not in cols_cases:
            conn.execute("ALTER TABLE cases ADD COLUMN case_context TEXT DEFAULT ''")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"OK - initialised {config.DB_PATH}")
