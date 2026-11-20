# V2 01 · Task 1.2.1 实现报告

本 Task 交付未接入 Graph/工具的混合候选召回；后续重排及公开结果契约未实施。`HybridCandidateRetriever` 在权限和查询校验后先获取 Query Embedding，然后调用 Repository；Repository 在同一只读 REPEATABLE READ 事务中检查 Sparse Profile、环境、完整性、索引与水位，检查 Embedding Profile，顺序执行 Dense 和参数化 BM25。两路在 Top10 前应用同一领域、Embedding Profile、当前文档版本条件；知识读取权限在执行查询前校验。BM25 排除零分，负值升序；同分按完整来源身份排序。数据库错误/超时与合法空结果区分，不降级。

`fusion.py` 以完整来源四元组去重，按两路一基排名等权 RRF（k=60）及来源身份稳定排序，保留各路分数、排名和水位；只取融合 Top10。原 V1 Dense 路径保持原行为。此候选接口未声明最终 `HybridSearchResult` 或重排得分，不触发模型在事务内执行。

## 验证

- 项目 `.venv`：`python -m pytest -q tests/test_hybrid_task121.py tests/test_knowledge.py`：8 passed；受控测试覆盖来源身份、等分稳定排序、分数隔离与 V1 知识测试。
- 专用隔离库 `agent_hybrid_task121_test` / `agent_hybrid_task121`，测试前校验数据库注释 `codex-task121-9db5` 及知识表不存在，运行 `python -m pytest -q tests/test_hybrid_task121_postgres.py`：1 passed。真实 PostgreSQL、pgvector、pg_textsearch、zhparser；验证空库与权限、超过 Top10 的其他领域不挤占、两路命中、无词项、Profile 错误、索引未就绪、版本替换与旧引用失效。受控并发在快照建立后提交更新，验证旧水位与旧版本一致、后续事务看到新版本及新水位。测试精确删除本次创建的三个知识表及其索引。
- `.venv` 的 `ruff check` 和 `ruff format --check` 针对本 Task 修改的四个知识模块及两个测试文件通过。

并发测试验证 MVCC 可见来源和水位，不声称 pg_textsearch 的 BM25 统计分数在并发写入下保持快照一致；扩展统计漂移限制沿用 1.1.1 证据。Embedding 使用受控替身，BGE、Graph/工具接线、真实模型和质量验收未在本 Task 实施或验证。独立 QA 及主复核待进行。

## V201-121-QA-001 修复与验证

数据库阶段以 `HYBRID_DATABASE_TIMEOUT_SECONDS = 5` 集中定义期限；`asyncio.timeout` 覆盖连接池等待、只读事务、就绪检查和两路 SQL，事务内 `statement_timeout` 使用同一数值。超时、连接池等待超时及 SQL 取消统一映射为 `retrieval_timeout`，其他数据库故障保留原错误映射。V1 路径及应用接线未修改。BM25 查询传入固定 `public.knowledge_chunks_bm25_idx`，与 readiness 核验的 schema 一致；真实扩展查询验证了限定名称可用。

执行 `.\.venv\Scripts\python.exe -B .git/task121-local-validation.py hybrid -q tests/test_hybrid_task121_postgres.py tests/test_hybrid_task121.py`，数据库标记守卫通过，**2 passed**。真实隔离 PG 中受控注入两次 `pg_sleep(2.7)`，验证合计期限返回 `retrieval_timeout`；随后借出全部三个连接核验事务均为空闲且可查询，并成功执行后续检索。另占满连接池，验证获取连接等待受同一总期限约束且释放后仍可检索。测试断言两种受控超时耗时在 4.5 至 7 秒区间；不作为性能测量。该测试继续覆盖原快照和 BM25 实际查询，测试对象精确清理。定向 `ruff check` 与 `ruff format --check` 均通过。修复待独立 QA 复测。
