SET search_path = probe111, public;
SELECT clock_timestamp() AS at, 'C_new_snapshot' AS phase,
       count(*) FILTER (WHERE is_current) AS current_rows,
       count(*) FILTER (WHERE is_current AND document_version=1) AS v1_current,
       count(*) FILTER (WHERE is_current AND document_version=2) AS v2_current
FROM probe111.hybrid;
SELECT clock_timestamp() AS at, 'C_dense' AS phase, chunk_id, document_version, embedding <=> '[1,0,0]' AS distance
FROM probe111.hybrid WHERE is_current ORDER BY distance ASC, chunk_id ASC LIMIT 3;
SELECT clock_timestamp() AS at, 'C_sparse' AS phase, chunk_id, document_version, search_text <@> to_bm25query('退款','probe111_hybrid_bm25') AS score
FROM probe111.hybrid WHERE is_current AND search_text <@> to_bm25query('退款','probe111_hybrid_bm25') < 0
ORDER BY score ASC, chunk_id ASC LIMIT 3;
SELECT chunk_id, is_current FROM probe111.hybrid WHERE chunk_id='v1-refund';
