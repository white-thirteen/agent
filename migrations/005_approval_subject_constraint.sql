ALTER TABLE approvals ADD CONSTRAINT approvals_subject_task_ids_required CHECK (
    jsonb_typeof(subject_snapshot -> 'task_id') IS NOT DISTINCT FROM 'string'
    AND jsonb_typeof(subject_snapshot -> 'workflow_id') IS NOT DISTINCT FROM 'string'
    AND length(subject_snapshot ->> 'task_id') > 0
    AND subject_snapshot ->> 'task_id' = subject_snapshot ->> 'workflow_id'
);
