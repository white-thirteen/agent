SET search_path = probe111, public;
SET enable_seqscan = off;
\echo PREPARED_QUERY
PREPARE bm25_case(text, text) AS
SELECT id, content <@> to_bm25query($1, $2) AS score
FROM probe111.docs
WHERE content <@> to_bm25query($1, $2) < 0
ORDER BY score ASC, id ASC
LIMIT 5;
\echo CHINESE
EXECUTE bm25_case('退款 银行卡', 'probe111_docs_bm25');
\echo ENGLISH
EXECUTE bm25_case('stream disconnects accepted task', 'probe111_docs_bm25');
\echo MIXED
EXECUTE bm25_case('退款 approval endpoint', 'probe111_docs_bm25');
\echo PREPARED_PLAN
EXPLAIN (COSTS OFF) EXECUTE bm25_case('退款 银行卡', 'probe111_docs_bm25');
\echo INDEX_RESOLUTION
SELECT to_regclass('probe111.probe111_docs_bm25') AS trusted_index,
       to_regclass('probe111.probe111_docs_bm25; DROP TABLE probe111.docs') AS injected_index;
\echo INVALID_INDEX_REJECTED
\set ON_ERROR_STOP off
SELECT id FROM probe111.docs
WHERE content <@> to_bm25query('退款', 'probe111_docs_bm25; DROP TABLE probe111.docs') < 0;
\set ON_ERROR_STOP on
SELECT count(*) AS docs_after_invalid_index FROM probe111.docs;
