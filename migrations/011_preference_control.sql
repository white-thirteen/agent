CREATE TABLE preference_command_receipt (
    user_id text NOT NULL,
    operation_id text NOT NULL,
    command_id text NOT NULL UNIQUE,
    command_digest text NOT NULL,
    command jsonb NOT NULL,
    expected_revision integer NOT NULL CHECK (expected_revision >= 0),
    status text NOT NULL CHECK (status IN ('PREPARED', 'EXECUTING', 'APPLIED', 'CONFLICT', 'UNKNOWN')),
    result jsonb,
    PRIMARY KEY (user_id, operation_id)
);

CREATE UNIQUE INDEX preference_one_unresolved_per_user ON preference_command_receipt (user_id)
    WHERE status IN ('PREPARED', 'EXECUTING', 'UNKNOWN');
