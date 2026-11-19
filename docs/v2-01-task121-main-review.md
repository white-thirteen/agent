# V2 01 · Task 1.2.1 主复核

**Task 1.2.1 = ACCEPTED（2026-11-19）。** 用户授权正式验收及归档，详见[阶段验收](v2-01-stage-acceptance.md#task-121-densebm25-与-rrf)。以下为当时的技术验收记录。

**VERIFIED。** 在真实隔离 PostgreSQL 上完成同快照 Dense/BM25 召回、候选去重、RRF 与受控超时验证。主复核关闭 V201-121-QA-001 / P2。用户已授权继续 V2 01 开发，Git 归档授权待定。

- [实现报告](v2-01-task121-implementation-report.md)记录权威版本与相同领域/Profile 过滤、候选身份和一基排名、RRF 等权融合以及事务外 Embedding。
- [初次独立 QA](question/v2-01-task121-qa-report.md)在真实数据库中复现两条各 2.7 秒语句超过双路 5 秒预算。修复使同一 5 秒期限制约连接池获取、就绪检查和同快照两路 SQL；[原 QA 独立复测](question/v2-01-task121-retest-report.md)通过 2 项，零跳过，覆盖超时后事务及连接池可复用。
- 主复核使用独立仅启用 pgvector 的数据库应用 001–007，执行 `tests/test_knowledge_postgres.py tests/test_knowledge_graph.py`，23 passed，耗时 9.84 秒。Hybrid 专用测试库、角色、注释标记与 V1 回归隔离，正式数据库未连接。
- MVCC 验证覆盖权威行、版本、来源及水位，可见的 BM25 全局统计分数和并发排序稳定性仍沿用 1.1.1 的边界。RRF 已验证，真实模型与公开 Graph 接线另由后续任务验证。

复用固定候选镜像 `sha256:748b51b8d45a51bc517424a9cd78aab4c8d268fe2155cca018b66f84c361ce85`。本轮专属临时容器和卷已清理，标签复查为空；正式容器身份、启动时间与健康状态前后一致。无 Git 提交或推送。
