-- Context summaries and durable, separately owned maintenance attempts.
CREATE TABLE context_summary (
    user_id text NOT NULL, conversation_id text NOT NULL, summary_id text NOT NULL,
    version integer NOT NULL CHECK (version > 0), text text NOT NULL,
    archive_refs text[] NOT NULL, message_ids text[] NOT NULL,
    parent_summary_id text, input_hash text NOT NULL, source_checkpoint_id text NOT NULL,
    policy_version text NOT NULL, model_version text NOT NULL, prompt_version text NOT NULL,
    PRIMARY KEY (user_id, conversation_id, summary_id),
    UNIQUE (user_id, conversation_id, input_hash, version, source_checkpoint_id,
            policy_version, model_version, prompt_version),
    FOREIGN KEY (user_id, conversation_id, parent_summary_id)
        REFERENCES context_summary(user_id, conversation_id, summary_id)
);
CREATE TABLE context_maintenance (
    maintenance_id text PRIMARY KEY, user_id text NOT NULL, conversation_id text NOT NULL,
    source_task_id text NOT NULL, source_run_id text NOT NULL, source_checkpoint_id text NOT NULL,
    message_ids text[] NOT NULL, content_hash text NOT NULL, policy_version text NOT NULL,
    budget_version text NOT NULL, max_input_tokens integer NOT NULL CHECK (max_input_tokens > 0),
    max_output_tokens integer NOT NULL CHECK (max_output_tokens > 0),
    archive_refs text[] NOT NULL, deadline_at timestamptz NOT NULL,
    reserved_attempts integer NOT NULL DEFAULT 0 CHECK (reserved_attempts BETWEEN 0 AND 2),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN
        ('PENDING','RUNNING','SUCCEEDED','FAILED','EXHAUSTED','INTERRUPTED')),
    summary_id text, revision integer, claim_id text,
    UNIQUE (user_id, conversation_id, content_hash, policy_version),
    FOREIGN KEY (user_id, conversation_id, summary_id)
        REFERENCES context_summary(user_id, conversation_id, summary_id)
);
CREATE TABLE context_maintenance_attempt (
    attempt_id text PRIMARY KEY, maintenance_id text NOT NULL REFERENCES context_maintenance,
    claim_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('RESERVED','RECORDED','INTERRUPTED')),
    input_tokens integer, output_tokens integer, total_tokens integer,
    usage_status text NOT NULL DEFAULT 'unknown' CHECK (usage_status IN ('known','estimated','unknown')),
    estimation_method text,
    CHECK (usage_status <> 'known' OR (input_tokens IS NOT NULL AND output_tokens IS NOT NULL AND total_tokens IS NOT NULL))
);

