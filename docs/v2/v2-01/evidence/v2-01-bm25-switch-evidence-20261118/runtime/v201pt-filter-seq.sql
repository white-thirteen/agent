SET search_path = evidence, public;
DROP INDEX IF EXISTS evidence.evidence_filter;
\echo SEQ_PLAN
SET enable_seqscan = on;
SET enable_indexscan = off;
SET enable_bitmapscan = off;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY ON)
SELECT row_number() OVER (ORDER BY score ASC, id ASC) AS rank, id, score
FROM (
  SELECT id, content <@> to_bm25query('退款','evidence_bm25') AS score
  FROM evidence.docs
  WHERE domain = 'after_sales_help' AND doc_version = 1
    AND content <@> to_bm25query('退款','evidence_bm25') < 0
) q
ORDER BY score ASC, id ASC
LIMIT 5;
\echo SEQ_ROWS
SELECT row_number() OVER (ORDER BY score ASC, id ASC) AS rank, id, score
FROM (
  SELECT id, content <@> to_bm25query('退款','evidence_bm25') AS score
  FROM evidence.docs
  WHERE domain = 'after_sales_help' AND doc_version = 1
    AND content <@> to_bm25query('退款','evidence_bm25') < 0
) q
ORDER BY score ASC, id ASC
LIMIT 5;
