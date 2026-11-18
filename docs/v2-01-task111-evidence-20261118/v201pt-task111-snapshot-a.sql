SET search_path = probe111, public;
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT clock_timestamp() AS at, 'A_before' AS phase,
       count(*) FILTER (WHERE is_current) AS current_rows,
       count(*) FILTER (WHERE is_current AND document_id='doc-refund' AND document_version=1) AS v1_refund_current
FROM probe111.hybrid;
SELECT clock_timestamp() AS at, 'A_before_dense' AS phase, chunk_id, embedding <=> '[1,0,0]' AS distance
FROM probe111.hybrid WHERE is_current ORDER BY distance ASC, chunk_id ASC LIMIT 3;
SELECT clock_timestamp() AS at, 'A_before_sparse' AS phase, chunk_id, search_text <@> to_bm25query('退款','probe111_hybrid_bm25') AS score
FROM probe111.hybrid WHERE is_current AND search_text <@> to_bm25query('退款','probe111_hybrid_bm25') < 0
ORDER BY score ASC, chunk_id ASC LIMIT 3;
SELECT pg_sleep(3);
SELECT clock_timestamp() AS at, 'A_after_B_commit' AS phase,
       count(*) FILTER (WHERE is_current) AS current_rows,
       count(*) FILTER (WHERE is_current AND document_id='doc-refund' AND document_version=1) AS v1_refund_current
FROM probe111.hybrid;
SELECT clock_timestamp() AS at, 'A_after_dense' AS phase, chunk_id, embedding <=> '[1,0,0]' AS distance
FROM probe111.hybrid WHERE is_current ORDER BY distance ASC, chunk_id ASC LIMIT 3;
SELECT clock_timestamp() AS at, 'A_after_sparse' AS phase, chunk_id, search_text <@> to_bm25query('退款','probe111_hybrid_bm25') AS score
FROM probe111.hybrid WHERE is_current AND search_text <@> to_bm25query('退款','probe111_hybrid_bm25') < 0
ORDER BY score ASC, chunk_id ASC LIMIT 3;
COMMIT;
