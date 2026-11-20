CREATE EXTENSION IF NOT EXISTS pg_textsearch;
CREATE EXTENSION IF NOT EXISTS zhparser;
CREATE EXTENSION IF NOT EXISTS vector;
DROP SCHEMA IF EXISTS probe111 CASCADE;
CREATE SCHEMA probe111;
DROP TEXT SEARCH CONFIGURATION IF EXISTS public.chinese CASCADE;
CREATE TEXT SEARCH CONFIGURATION public.chinese (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION public.chinese ADD MAPPING FOR n, v, a, i, e, l WITH simple;

CREATE TABLE probe111.docs (id text PRIMARY KEY, lang text, content text);
INSERT INTO probe111.docs VALUES
('zh-refund','zh','模拟退款不会扣真实银行卡的钱，退款只改变本地模拟数据。'),
('en-stream','en','The stream disconnects but the accepted task continues; query the original task status.'),
('mixed-approval','mixed','退款 approval 由本地 approval endpoint 处理，聊天中的同意不能批准。');
CREATE INDEX probe111_docs_bm25 ON probe111.docs USING bm25(content) WITH (text_config='public.chinese');

CREATE TABLE probe111.hybrid (
  chunk_id text PRIMARY KEY,
  document_id text NOT NULL,
  document_version int NOT NULL,
  search_text text NOT NULL,
  embedding vector(3) NOT NULL,
  is_current boolean NOT NULL
);
INSERT INTO probe111.hybrid VALUES
('v1-refund','doc-refund',1,'退款安全说明 不扣真实银行卡','[1,0,0]',true),
('v1-stream','doc-stream',1,'stream disconnects accepted task continues','[0,1,0]',true);
CREATE INDEX probe111_hybrid_bm25 ON probe111.hybrid USING bm25(search_text) WITH (text_config='public.chinese');
CREATE INDEX probe111_hybrid_current ON probe111.hybrid(is_current, document_id, document_version);

CREATE TABLE probe111.maint (id int PRIMARY KEY, content text, embedding vector(3));
INSERT INTO probe111.maint
SELECT g, '维护测试 退款 安全 第 ' || g || ' 条', '[1,0,0]' FROM generate_series(1, 5000) g;
CREATE INDEX probe111_maint_bm25 ON probe111.maint USING bm25(content) WITH (text_config='public.chinese');
ANALYZE probe111.maint;
