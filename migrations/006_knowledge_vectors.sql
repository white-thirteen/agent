CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE knowledge_documents (
    document_id text PRIMARY KEY,
    document_version text NOT NULL,
    content_hash text NOT NULL,
    domain text NOT NULL CHECK (domain IN ('platform_help', 'after_sales_help')),
    source_title text NOT NULL,
    public_source_key text NOT NULL,
    embedding_profile text NOT NULL,
    chunk_count integer NOT NULL CHECK (chunk_count > 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, document_version)
);
CREATE INDEX knowledge_documents_domain_idx ON knowledge_documents(domain);

CREATE TABLE knowledge_chunks (
    chunk_id text PRIMARY KEY,
    document_id text NOT NULL,
    document_version text NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    section text,
    page integer CHECK (page IS NULL),
    line_start integer NOT NULL CHECK (line_start > 0),
    line_end integer NOT NULL CHECK (line_end >= line_start),
    content text NOT NULL,
    content_hash text NOT NULL,
    token_count integer NOT NULL CHECK (token_count > 0 AND token_count <= 500),
    embedding vector(1024) NOT NULL,
    FOREIGN KEY (document_id, document_version)
        REFERENCES knowledge_documents(document_id, document_version),
    UNIQUE (document_id, ordinal)
);
CREATE INDEX knowledge_chunks_document_idx ON knowledge_chunks(document_id, document_version);
