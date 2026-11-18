SET search_path = probe111, public;
BEGIN;
INSERT INTO probe111.hybrid (chunk_id, document_id, document_version, search_text, embedding, is_current)
VALUES ('v2-refund','doc-refund',2,'退款安全说明 第二版','[1,0,0]',true);
UPDATE probe111.hybrid SET is_current=false
WHERE document_id='doc-refund' AND document_version=1;
SELECT clock_timestamp() AS at, 'B_commit' AS phase, chunk_id, document_version, is_current
FROM probe111.hybrid WHERE document_id='doc-refund' ORDER BY document_version;
COMMIT;
