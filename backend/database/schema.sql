-- VERTEX schema v1 — six tables, zero ORM.
-- Idempotent: every statement uses IF NOT EXISTS.
-- Reset: rm vertex.db

CREATE TABLE IF NOT EXISTS users (
    user_id     TEXT PRIMARY KEY,
    username    TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role        TEXT DEFAULT 'investigator',
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    case_id         TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    seeds_json      TEXT NOT NULL,
    minor_involved  INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'pending',
    created_at      TEXT,
    updated_at      TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id       TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL,
    type            TEXT,
    value           TEXT,
    platform        TEXT,
    confidence      REAL,
    metadata_json   TEXT,
    source_url      TEXT,
    data_mode       TEXT,
    sha256          TEXT,
    created_at      TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS clusters (
    cluster_id          TEXT PRIMARY KEY,
    case_id             TEXT NOT NULL,
    entity_ids_json     TEXT NOT NULL,
    confidence_score    REAL,
    tier                TEXT,
    explanation         TEXT,
    signals_json        TEXT,
    created_at          TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS audit_ledger (
    ledger_id       TEXT PRIMARY KEY,
    case_id         TEXT,
    action          TEXT,
    search_id       TEXT,
    input_hash      TEXT,
    output_hash     TEXT,
    previous_hash   TEXT,
    actor           TEXT,
    timestamp       TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id     TEXT PRIMARY KEY,
    case_id         TEXT,
    entity_id       TEXT,
    artifact_type   TEXT,
    file_path       TEXT,
    sha256          TEXT,
    captured_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_entities_case  ON entities(case_id);
CREATE INDEX IF NOT EXISTS idx_entities_value ON entities(value);
CREATE INDEX IF NOT EXISTS idx_clusters_case  ON clusters(case_id);
CREATE INDEX IF NOT EXISTS idx_ledger_case    ON audit_ledger(case_id);

CREATE TABLE IF NOT EXISTS scraper_cache (
    cache_key TEXT PRIMARY KEY,
    scraper_name TEXT,
    query TEXT,
    response_json TEXT,
    cached_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_scraper_cache_lookup ON scraper_cache(scraper_name, query);

