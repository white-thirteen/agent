SET search_path = evidence, public;
BEGIN;
UPDATE evidence.docs SET content='并发更新 QZCONCURRENT 退款' WHERE id='doc-refund';
SELECT clock_timestamp() AS write_started, txid_current() AS txid, pg_current_xact_id_if_assigned() AS xid;
SELECT pg_sleep(3);
COMMIT;
