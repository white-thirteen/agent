SET search_path = evidence, public;
DROP INDEX IF EXISTS evidence.evidence_filter;
SET enable_seqscan = off;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY ON) SELECT id FROM evidence.docs WHERE domain='after_sales_help' AND doc_version=1 ORDER BY content <@> to_bm25query('退款','evidence_bm25') LIMIT 3;
SELECT id FROM evidence.docs WHERE domain='after_sales_help' AND doc_version=1 ORDER BY content <@> to_bm25query('退款','evidence_bm25') LIMIT 3;
CREATE INDEX evidence_filter ON evidence.docs(domain, doc_version);
