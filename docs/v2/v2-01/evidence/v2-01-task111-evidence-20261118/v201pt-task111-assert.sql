SET search_path = probe111, public;
CREATE OR REPLACE FUNCTION probe111.assert_hit(p_name text, p_q text, p_expected text)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE top_id text; top_score double precision;
BEGIN
  EXECUTE 'SELECT id, content <@> to_bm25query($1, $2) AS score
           FROM probe111.docs
           WHERE content <@> to_bm25query($1, $2) < 0
           ORDER BY score ASC, id ASC
           LIMIT 1'
    INTO top_id, top_score
    USING p_q, 'probe111_docs_bm25';
  IF top_id IS DISTINCT FROM p_expected THEN
    RAISE EXCEPTION 'case % expected %, got %', p_name, p_expected, top_id;
  END IF;
  RETURN format('%s|PASS|%s|%s', p_name, top_id, top_score);
END $$;
\echo ASSERTIONS
SELECT probe111.assert_hit('chinese', '退款 银行卡', 'zh-refund');
SELECT probe111.assert_hit('english', 'stream disconnects accepted task', 'en-stream');
SELECT probe111.assert_hit('mixed', '退款 approval endpoint', 'mixed-approval');
\echo TRUSTED_INDEX
SELECT to_regclass('probe111.probe111_docs_bm25') AS valid_index,
       to_regclass('probe111.probe111_docs_bm25; DROP TABLE probe111.docs') AS invalid_index;
\echo INVALID_INDEX_REJECTED
\set ON_ERROR_STOP off
SELECT id FROM probe111.docs
WHERE content <@> to_bm25query('退款', 'probe111_docs_bm25; DROP TABLE probe111.docs') < 0;
\set ON_ERROR_STOP on
SELECT count(*) AS docs_after_invalid_index FROM probe111.docs;
