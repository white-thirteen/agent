# V2 01 BM25 切换 QA 复测报告

**结论**：`REQUIRES_FIX`（Codex 独立验收；本文件为主 Agent 复测记录，修复后待 Codex 复验，不构成最终 ACCEPTED）  
**日期**：2026-11-18  
**对象**：pg_textsearch 1.5.1 + zhparser 2.4 + SCWS 1.2.3，PostgreSQL 17.12 / pgvector 0.8.7

## 通过项

| 类别 | 结果 |
| --- | --- |
| 安全构建 | 17.12 headers、PGXS/C 扩展，无 pgrx；源码/产物 SHA256 已记录 |
| 扩展加载 | pg_textsearch、zhparser、vector 同库正常 |
| 中文 | zhparser 索引/查询可用；词典安装要求已验证 |
| 事务 | 回滚后行数与正文不变 |
| 增量 | INSERT/UPDATE/DELETE 后索引可见性正确 |
| 重启 | 索引与查询结果持久化 |
| 过滤 TopK | 固定 7 篇顺序扫描与 BM25 索引扫描逐行一致（2 条有效候选，K=5 未补零分）；5000 Chunk 压力 Top10 通过 |
| 并发 | 固定夹具下未提交不可见（0），提交后可见（1）；不对历史异常作根因结论 |
| 质量对照 | 临时语料上 Jieba/zhparser Recall 0.8792/0.8625，MRR 均 0.9167；未冒充冻结语料结论 |

## 未纳入本轮

- Dense/RRF/BGE 端到端质量与 BGE 长度/资源检查。
- V2 固定语料、Chunk 级 0–3 标注、nDCG 正式值。
- 生产规模延迟、索引维护/compaction 长期开销。
- 外部独立 QA；本报告为隔离环境复测，未冒充第三方结论。

## 风险

- `dict.utf8.xdb`/`rules.utf8.ini` 缺失会导致静默空查询，部署必须校验。
- 负 BM25 分数只能用于升序排名，RRF 不得直接与余弦分数相加。
- 过滤查询可能走 B-tree 预过滤+独立评分，规模化性能需后续门禁。

## 裁决

BM25 切换本身未发现功能/安全阻塞，但 Codex 独立验收已判定 `REQUIRES_FIX`；本文件不再作为最终验收结论。修复项与证据见 [`v2-01-bm25-switch-qa-fix-report.md`](v2-01-bm25-switch-qa-fix-report.md)，待 Codex 复验。
