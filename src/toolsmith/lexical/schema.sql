CREATE TABLE lexical_document (
    reference TEXT PRIMARY KEY,
    text_digest TEXT NOT NULL,
    title TEXT NOT NULL,
    characters INTEGER NOT NULL CHECK (characters >= 0),
    chunks INTEGER NOT NULL CHECK (chunks >= 0)
) STRICT;
CREATE TABLE lexical_chunk (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL REFERENCES lexical_document(reference) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    text TEXT NOT NULL,
    text_digest TEXT NOT NULL,
    UNIQUE(reference, ordinal)
) STRICT;
CREATE VIRTUAL TABLE lexical_search USING fts5(text, title, tokenize='unicode61');
