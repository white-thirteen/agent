-- Same-session inserts share the uuid5 candidate. Let the immediate composite
-- primary key resolve ON CONFLICT before checking global thread uniqueness.
ALTER TABLE sessions DROP CONSTRAINT sessions_thread_id_key;
ALTER TABLE sessions ADD CONSTRAINT sessions_thread_id_key
    UNIQUE (thread_id) DEFERRABLE INITIALLY DEFERRED;
