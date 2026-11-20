SET search_path = evidence, public;
\echo DELETE_BEFORE
INSERT INTO evidence.docs VALUES ('del-1','after_sales_help',1,'删除测试 QZDELETE 退款');
SELECT count(*) AS before_delete, count(*) FILTER (WHERE content <@> to_bm25query('QZDELETE','evidence_bm25') < 0) AS qzdelete_hits
FROM evidence.docs WHERE id='del-1';
\echo DELETE_ROLLBACK
BEGIN;
DELETE FROM evidence.docs WHERE id='del-1';
SELECT count(*) AS inside_tx FROM evidence.docs WHERE id='del-1';
ROLLBACK;
SELECT count(*) AS after_rollback,
       count(*) FILTER (WHERE content <@> to_bm25query('QZDELETE','evidence_bm25') < 0) AS qzdelete_hits
FROM evidence.docs WHERE id='del-1';
\echo DELETE_COMMIT
DELETE FROM evidence.docs WHERE id='del-1';
SELECT count(*) AS after_delete,
       count(*) FILTER (WHERE content <@> to_bm25query('QZDELETE','evidence_bm25') < 0) AS qzdelete_hits
FROM evidence.docs WHERE id='del-1';
SELECT count(*) AS all_qzdelete_hits FROM evidence.docs WHERE content <@> to_bm25query('QZDELETE','evidence_bm25') < 0;
