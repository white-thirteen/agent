CREATE TABLE context_revision (
    user_id text NOT NULL, conversation_id text NOT NULL,
    revision integer NOT NULL CHECK (revision > 0), base_revision integer,
    source_checkpoint_id text NOT NULL, message_ids text[] NOT NULL,
    content_hash text NOT NULL, archive_refs text[] NOT NULL, summary_id text NOT NULL,
    policy_version text NOT NULL, model_version text NOT NULL, prompt_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('PREPARING','PUBLISHED','APPLIED','STALE')),
    applied_checkpoint_id text,
    PRIMARY KEY (user_id, conversation_id, revision),
    FOREIGN KEY (user_id, conversation_id, summary_id)
        REFERENCES context_summary(user_id, conversation_id, summary_id),
    FOREIGN KEY (user_id, conversation_id, base_revision)
        REFERENCES context_revision(user_id, conversation_id, revision),
    CHECK ((status = 'APPLIED') = (applied_checkpoint_id IS NOT NULL))
);
