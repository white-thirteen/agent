ALTER TABLE demo_orders ADD CONSTRAINT demo_orders_order_owner_unique UNIQUE (order_id, owner_id);

CREATE TABLE refund_requests (
    application_id uuid PRIMARY KEY,
    operation_id uuid NOT NULL UNIQUE,
    user_id text NOT NULL,
    conversation_id text NOT NULL,
    thread_id uuid NOT NULL,
    task_id text NOT NULL,
    workflow_id text NOT NULL CHECK (workflow_id = task_id),
    order_id text NOT NULL,
    call_id text NOT NULL,
    tool_name text NOT NULL,
    tool_version text NOT NULL,
    raw_args jsonb NOT NULL CHECK (jsonb_typeof(raw_args) = 'object'),
    canonical_args jsonb NOT NULL CHECK (jsonb_typeof(canonical_args) = 'object'),
    args_digest text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount > 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SUCCEEDED', 'REJECTED')),
    rejection_code text,
    execution_result jsonb,
    executed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (user_id, conversation_id) REFERENCES sessions (user_id, conversation_id),
    FOREIGN KEY (order_id, user_id) REFERENCES demo_orders (order_id, owner_id),
    UNIQUE (user_id, task_id),
    UNIQUE (thread_id, task_id, call_id),
    CHECK (
        (status = 'PENDING' AND rejection_code IS NULL AND execution_result IS NULL AND executed_at IS NULL)
        OR (status = 'REJECTED' AND rejection_code IS NOT NULL AND execution_result IS NULL AND executed_at IS NULL)
        OR (status = 'SUCCEEDED' AND rejection_code IS NULL AND execution_result IS NOT NULL
            AND jsonb_typeof(execution_result) = 'object' AND executed_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX refund_requests_order_succeeded ON refund_requests (order_id)
    WHERE status = 'SUCCEEDED';

CREATE TABLE approvals (
    approval_id uuid PRIMARY KEY,
    application_id uuid NOT NULL UNIQUE REFERENCES refund_requests (application_id),
    subject_snapshot jsonb NOT NULL CHECK (jsonb_typeof(subject_snapshot) = 'object'),
    subject_digest text NOT NULL,
    decision text NOT NULL DEFAULT 'PENDING' CHECK (decision IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
    approver_id text,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 minutes'),
    interrupt_id text,
    checkpoint_ns text,
    checkpoint_id text,
    CHECK (subject_snapshot ? 'task_id' AND subject_snapshot ? 'workflow_id'
        AND subject_snapshot->>'task_id' = subject_snapshot->>'workflow_id'),
    CHECK ((interrupt_id IS NULL AND checkpoint_ns IS NULL AND checkpoint_id IS NULL)
        OR (interrupt_id IS NOT NULL AND checkpoint_ns IS NOT NULL AND checkpoint_id IS NOT NULL)),
    CHECK ((decision = 'PENDING' AND approver_id IS NULL AND decided_at IS NULL)
        OR (decision <> 'PENDING' AND approver_id IS NOT NULL AND decided_at IS NOT NULL)),
    CHECK (expires_at = created_at + interval '30 minutes')
);
