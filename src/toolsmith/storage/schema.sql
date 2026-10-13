CREATE TABLE collection (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    identity TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE item (
    id TEXT PRIMARY KEY,
    latest_version TEXT REFERENCES text_version(id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE text_version (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES item(id),
    title TEXT NOT NULL,
    method TEXT NOT NULL,
    source_url TEXT,
    published_at TEXT,
    observed_at TEXT,
    recorded_at TEXT NOT NULL,
    content_bytes INTEGER NOT NULL CHECK (content_bytes >= 0)
);
CREATE INDEX text_version_item ON text_version(item_id, recorded_at, id);
CREATE TABLE part (
    id INTEGER PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES text_version(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    label TEXT NOT NULL,
    physical_page INTEGER CHECK (physical_page > 0),
    text TEXT NOT NULL,
    text_digest TEXT NOT NULL,
    has_text INTEGER NOT NULL CHECK (has_text IN (0, 1)),
    warnings TEXT NOT NULL,
    UNIQUE (version_id, ordinal)
);
CREATE INDEX part_version ON part(version_id, ordinal);
CREATE TABLE chunk (
    id INTEGER PRIMARY KEY,
    part_id INTEGER NOT NULL REFERENCES part(id),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    text TEXT NOT NULL,
    UNIQUE (part_id, start_offset, end_offset)
);
CREATE INDEX chunk_part ON chunk(part_id, start_offset);
CREATE VIRTUAL TABLE chunk_search USING fts5(text, title, tokenize = 'unicode61');
CREATE TABLE blob (
    id TEXT PRIMARY KEY,
    size INTEGER NOT NULL CHECK (size >= 0)
);
CREATE TABLE file_version (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    blob_id TEXT NOT NULL REFERENCES blob(id),
    source_url TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX file_version_blob ON file_version(blob_id);
CREATE TABLE operation (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('http', 'text', 'file')),
    request_hash TEXT NOT NULL,
    request_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    result_json TEXT,
    failure_json TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0 CHECK (requests >= 0)
);
