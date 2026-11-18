SET search_path = evidence, public;
SELECT clock_timestamp() AS read_at, count(*) AS qz_matches
FROM evidence.docs
WHERE content <@> to_bm25query('QZCONCURRENT','evidence_bm25') < 0;
