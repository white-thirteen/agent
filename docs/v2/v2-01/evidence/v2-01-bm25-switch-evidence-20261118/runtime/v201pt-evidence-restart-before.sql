SET search_path = evidence, public;
SELECT count(*) AS docs_before_restart FROM docs;
SELECT id FROM docs WHERE domain='after_sales_help' AND doc_version=1 ORDER BY content <@> to_bm25query('退款','evidence_bm25') LIMIT 1;
