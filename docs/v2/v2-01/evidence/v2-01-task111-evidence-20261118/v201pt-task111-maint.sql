SET search_path = probe111, public;
\set ON_ERROR_STOP off
\echo BASELINE
SELECT count(*) AS rows, md5(string_agg(id::text || '|' || content, ',' ORDER BY id)) AS checksum FROM probe111.maint;
SELECT id, content <@> to_bm25query('退款','probe111_maint_bm25') AS score
FROM probe111.maint
WHERE content <@> to_bm25query('退款','probe111_maint_bm25') < 0
ORDER BY score ASC, id ASC LIMIT 3;
EXPLAIN (COSTS OFF) SELECT id FROM probe111.maint ORDER BY content <@> to_bm25query('退款','probe111_maint_bm25') LIMIT 3;
\echo FAILED_REINDEX
SET statement_timeout = '1ms';
REINDEX INDEX probe111.probe111_maint_bm25;
RESET statement_timeout;
\echo AFTER_FAILED_REINDEX
SELECT indisvalid FROM pg_index WHERE indexrelid = 'probe111.probe111_maint_bm25'::regclass;
SELECT count(*) AS rows, md5(string_agg(id::text || '|' || content, ',' ORDER BY id)) AS checksum FROM probe111.maint;
SELECT id, content <@> to_bm25query('退款','probe111_maint_bm25') AS score
FROM probe111.maint
WHERE content <@> to_bm25query('退款','probe111_maint_bm25') < 0
ORDER BY score ASC, id ASC LIMIT 3;
\echo RETRY_REINDEX
REINDEX INDEX probe111.probe111_maint_bm25;
\echo AFTER_RETRY
SELECT indisvalid FROM pg_index WHERE indexrelid = 'probe111.probe111_maint_bm25'::regclass;
SELECT count(*) AS rows, md5(string_agg(id::text || '|' || content, ',' ORDER BY id)) AS checksum FROM probe111.maint;
SELECT id, content <@> to_bm25query('退款','probe111_maint_bm25') AS score
FROM probe111.maint
WHERE content <@> to_bm25query('退款','probe111_maint_bm25') < 0
ORDER BY score ASC, id ASC LIMIT 3;
\echo DENSE_ONLY_FALLBACK
ALTER INDEX probe111.probe111_maint_bm25 RENAME TO probe111_maint_bm25_disabled;
SELECT count(*) AS rows, md5(string_agg(id::text || '|' || content, ',' ORDER BY id)) AS checksum FROM probe111.maint;
SELECT id, embedding <=> '[1,0,0]' AS distance
FROM probe111.maint ORDER BY distance ASC, id ASC LIMIT 5;
ALTER INDEX probe111.probe111_maint_bm25_disabled RENAME TO probe111_maint_bm25;
\echo RESTORED
SELECT count(*) AS rows, md5(string_agg(id::text || '|' || content, ',' ORDER BY id)) AS checksum FROM probe111.maint;
SELECT id, content <@> to_bm25query('退款','probe111_maint_bm25') AS score
FROM probe111.maint
WHERE content <@> to_bm25query('退款','probe111_maint_bm25') < 0
ORDER BY score ASC, id ASC LIMIT 3;
