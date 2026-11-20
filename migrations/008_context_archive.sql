-- Archive metadata only; Summary and Revision belong to subsequent tasks.
CREATE TABLE context_archive (
    user_id text NOT NULL,
    conversation_id text NOT NULL,
    segment_id text NOT NULL,
    archive_ref text NOT NULL,
    message_ids text[] NOT NULL,
    task_ids text[] NOT NULL,
    content_hash text NOT NULL,
    source_checkpoint_id text NOT NULL,
    relative_path text NOT NULL,
    file_hash text,
    status text NOT NULL CHECK (status IN ('PREPARING', 'READY')),
    ordinal bigint GENERATED ALWAYS AS IDENTITY,
    PRIMARY KEY (user_id, conversation_id, segment_id),
    UNIQUE (user_id, conversation_id, archive_ref),
    CHECK (status <> 'READY' OR file_hash IS NOT NULL)
);
CREATE INDEX context_archive_session_order ON context_archive (user_id, conversation_id, ordinal DESC);
