CREATE SCHEMA IF NOT EXISTS evidence;
DROP TABLE IF EXISTS evidence.docs CASCADE;
DROP TEXT SEARCH CONFIGURATION IF EXISTS public.chinese CASCADE;
CREATE TEXT SEARCH CONFIGURATION public.chinese (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION public.chinese ADD MAPPING FOR n, v, a, i, e, l WITH simple;
CREATE TABLE evidence.docs (id text PRIMARY KEY, domain text, doc_version int, content text);
INSERT INTO evidence.docs VALUES
('doc-refund', 'after_sales_help', 1, '模拟退款不会扣真实银行卡的钱，退款只改变本地模拟业务数据。'),
('doc-approval', 'after_sales_help', 1, '等待审批时聊天中的同意不能批准，审批由本地审批入口处理。'),
('doc-safety', 'after_sales_help', 1, '相同退款操作使用稳定操作编号，结果未知时先核对再重试。'),
('doc-account', 'platform_help', 1, '演示用户包括 dev-user 和 demo-user-b，不是真实生产登录。'),
('doc-stream', 'platform_help', 1, '聊天连接断开不会取消已受理任务，请查询原任务状态。'),
('other-high-1', 'other', 1, '退款 退款 退款 退款 退款 退款 退款 退款'),
('other-high-2', 'other', 1, '退款 退款 退款 退款 退款 退款 退款 退款');
CREATE INDEX evidence_bm25 ON evidence.docs USING bm25(content) WITH (text_config='public.chinese');
CREATE INDEX evidence_filter ON evidence.docs(domain, doc_version);
