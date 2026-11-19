# V2 01 Task 1.3.1 独立 QA

结论：**PASS**。未发现当前 Task 的编号问题；阶段质量验收和主 Agent 复核仍待进行。

- 独立检查八节点及 Policy/Executor 接线：默认 Dense 工具版本 1、15 秒；显式 Hybrid 版本 2，工具期限与配置的检索总期限一致。Hybrid 结果按版本、模式、Embedding/Sparse/Retrieval Profile、查询指纹、候选与证据关联和内容摘要校验；旧工具版本重放被拒绝。
- 受控 Graph 用例实际验证搜索结果经当前 Policy 重放，重放来源校验时再次调用当前来源；来源变化返回 `source_changed` 且不发布草稿。现有正式 Runtime 只支持退款任务恢复，知识任务无正式 resume；因此此证据是节点重放，不称为知识 Task 跨进程恢复。
- 真实隔离 PostgreSQL 定向命令：`.\.venv\Scripts\python.exe -B .git/task131-local-validation.py pytest -q tests/test_hybrid_task131_postgres.py tests/test_hybrid_task131.py tests/test_knowledge_graph.py`，保护检查 `TASK131_ISOLATED_DB_GUARD_PASS`，**23 passed / 0 failed / 0 skipped**。真实库用唯一文档并通过 Repository 精确清理；Embedding、BGE 和 LLM 使用受控替身，不称作真实模型 Graph 验证。
- 独立执行受控生命周期故障探针：Sparse 就绪后模拟 BGE 初始化抛出 `KnowledgeError`，应用状态为 knowledge unavailable、无检索器，数据库和 Embedding 状态仍 ready；退出时 BGE、Embedding、池均关闭。首次探针因测试 DSN 缺 user 而未进入应用，修正夹具后通过；以上是替身故障注入。
- 主 Agent 另行完成独立 DEV 库真实模型应用烟测，已查看其 `.git/task131-real-smoke.json` 回执：Qwen/BGE 初始化 25.218 秒，健康状态就绪、工具版本 2，两次真实检索及当前来源校验分别 8.015 秒和 1.858 秒，正常关闭；未调用付费 API。此项是检索和来源烟测，不是完整真实 LLM Graph 或质量评测。

遗留：完整冻结语料质量、真实业务和 V1 兼容性属于 Task 1.3.2；上述证据不替代该阶段门禁。未使用正式数据库或运行真实模型并发任务，未修改业务代码或既有测试。
