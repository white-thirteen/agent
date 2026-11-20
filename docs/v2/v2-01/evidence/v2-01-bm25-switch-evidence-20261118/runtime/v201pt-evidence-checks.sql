SET search_path = evidence, public;
\echo CHINESE_QUERY
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY ON) SELECT id, content <@> to_bm25query('退款 银行卡','evidence_bm25') AS score FROM evidence.docs WHERE content <@> to_bm25query('退款 银行卡','evidence_bm25') < 0 ORDER BY score LIMIT 5;
SELECT id, content <@> to_bm25query('退款 银行卡','evidence_bm25') AS score FROM evidence.docs WHERE content <@> to_bm25query('退款 银行卡','evidence_bm25') < 0 ORDER BY score LIMIT 5;
\echo FILTERED_TOPK
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY ON) SELECT id FROM evidence.docs WHERE domain='after_sales_help' AND doc_version=1 ORDER BY content <@> to_bm25query('退款','evidence_bm25') LIMIT 3;
SELECT id FROM evidence.docs WHERE domain='after_sales_help' AND doc_version=1 ORDER BY content <@> to_bm25query('退款','evidence_bm25') LIMIT 3;
\echo TRANSACTION_ROLLBACK
SELECT count(*) AS before_tx FROM evidence.docs;
BEGIN;
INSERT INTO evidence.docs VALUES ('tx-insert','platform_help',1,'事务内新增文档');
UPDATE evidence.docs SET content='事务内修改正文' WHERE id='doc-refund';
DELETE FROM evidence.docs WHERE id='doc-account';
ROLLBACK;
SELECT count(*) AS after_tx FROM evidence.docs;
SELECT content AS refund_after_rollback FROM evidence.docs WHERE id='doc-refund';
\echo INCREMENTAL
INSERT INTO evidence.docs VALUES ('inc-1','platform_help',1,'增量测试文档 QZINCREMENTAL');
SELECT id, content <@> to_bm25query('QZINCREMENTAL','evidence_bm25') AS score FROM evidence.docs WHERE content <@> to_bm25query('QZINCREMENTAL','evidence_bm25') < 0;
UPDATE evidence.docs SET content='更新测试文档 QZUPDATED' WHERE id='inc-1';
SELECT id, content <@> to_bm25query('QZUPDATED','evidence_bm25') AS score FROM evidence.docs WHERE content <@> to_bm25query('QZUPDATED','evidence_bm25') < 0;
DELETE FROM evidence.docs WHERE id='inc-1';
SELECT count(*) AS after_delete FROM evidence.docs;
\echo PERSIST_BEFORE
SELECT count(*) AS docs_before_restart FROM evidence.docs;
