# V2 01 Task 1.2.1 独立 QA

结论：**FAIL**。发现 V201-121-QA-001，交原 Implementer 修复后独立复测。本报告只覆盖 Task 1.2.1，不代表阶段验收。

## V201-121-QA-001 / P2：数据库阶段没有执行合计 5 秒期限

冻结设计 §4.3 给出双路数据库阶段合计 5 秒及集中配置要求。[repository.py](../../../../app/knowledge/repository.py) 中 `hybrid_candidates` 设置的 `statement_timeout = '5s'` 是逐条 SQL 期限；[retriever.py](../../../../app/knowledge/retriever.py) 的 15 秒外层期限涵盖 Embedding 和数据库整个调用，无法保证数据库阶段合计 5 秒。检查环境、完整性、Profile 和两路查询分别执行，累计等待可能超过设计上限。

真实 PostgreSQL 复现：在专用隔离库通过数据库名、用户、数据库标记及空知识表断言后建表，包装 readiness 检查，在同一个实际只读事务内顺序执行两次 `pg_sleep(2.7)`，每次小于单语句 5 秒；经实际 `HybridCandidateRetriever.search` 执行得到 `AGGREGATE_TIMEOUT_REPRO elapsed=5.82s status=empty`，未发生超时。探针为 `.git/task121-qa-timeout-probe.py`，使用项目 `.venv`，执行后精确删除本次创建的三个知识表。延迟为受控注入，PostgreSQL 和业务查询路径真实；它证明合计期限缺失，不是性能测量。

## 实际验证

- 守卫脚本 `.git/task121-local-validation.py hybrid -q tests/test_hybrid_task121_postgres.py`：标记 `TASK121_ISOLATED_DB_GUARD_PASS`，**1 passed**。真实 PG17.12、vector、pg_textsearch、zhparser；验证权限、空结果、过滤、版本、水位、索引不可用和 Profile 错误。并发测试证明行及水位的 MVCC 快照可见性；不证明 pg_textsearch 统计分数或排名在并发写入时快照稳定。
- `.venv` 的 `pytest -q tests/test_hybrid_task121.py`：**1 passed**，验证 RRF 按排名融合、分数独立、来源身份和稳定同分排序。
- 源码核对：两路在同一连接只读 REPEATABLE READ 中读取，绑定查询文本、相同 profile/domain/版本连接条件均在 LIMIT 前；异常映射不转换成空结果；Embedding 在事务前执行。候选组件未接入 Graph/BGE，现有来源复核方法继续可用。
- 主 Agent 并行执行的 V1 knowledge/Graph 向量回归报告为 **23 passed**；不是本 QA 独立运行的结果。

## 遗留范围

本任务未验收真实 BGE、Graph 混合接线或完整质量门禁。BM25 并发统计漂移仍属已知限制；当前行快照测试不能推导统计或排序一致。Embedding 使用受控替身，未执行付费调用或正式库操作。其余项目门禁依阶段要求保留。
