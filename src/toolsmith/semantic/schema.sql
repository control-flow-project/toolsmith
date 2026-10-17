CREATE TABLE embedding_profile (
    id TEXT PRIMARY KEY,
    definition TEXT NOT NULL
);
CREATE TABLE embedding_document (
    reference TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES embedding_profile(id),
    text_digest TEXT NOT NULL,
    characters INTEGER NOT NULL CHECK (characters > 0),
    chunks INTEGER NOT NULL CHECK (chunks > 0 AND chunks <= 20000),
    indexed_at TEXT NOT NULL
);
CREATE TABLE embedding_chunk (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL REFERENCES embedding_document(reference) ON DELETE CASCADE ON UPDATE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    text_digest TEXT NOT NULL,
    UNIQUE (reference, ordinal)
);
CREATE VIRTUAL TABLE embedding_vector USING vec1(vector, chunk_id);
INSERT INTO embedding_vector(cmd,arg) VALUES ('rebuild','{"index":"flat","distance":"cos"}');
