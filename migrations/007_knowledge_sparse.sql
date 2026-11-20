-- Sparse preparation is independent of optional extension installation.
ALTER TABLE knowledge_chunks ADD COLUMN search_text text;

CREATE TABLE knowledge_index_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    sparse_profile text,
    index_name text,
    watermark bigint NOT NULL DEFAULT 1 CHECK (watermark > 0),
    ready boolean NOT NULL DEFAULT false,
    CHECK (NOT ready OR (sparse_profile IS NOT NULL AND index_name IS NOT NULL))
);
INSERT INTO knowledge_index_state(singleton) VALUES (true);
