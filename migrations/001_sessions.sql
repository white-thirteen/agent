CREATE TABLE sessions (
    user_id text NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    conversation_id text NOT NULL CHECK (char_length(conversation_id) BETWEEN 1 AND 128),
    thread_id uuid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, conversation_id)
);
