# V2 01 Task 1.3.1 实施记录

- 应用默认 Dense；显式 `AGENT_KNOWLEDGE_RETRIEVAL_MODE=hybrid` 时检查 Sparse 就绪，加载固定 BGE，并将现有 Hybrid 候选、重排和完整证据预算接入八节点知识图。启动失败时知识能力不可用，其他资源继续启动；退出时按生命周期关闭模型。
- Hybrid 搜索工具版本 2，输出 HybridSearchResult；Graph 校验工具版本、模式、Profile、查询、候选和证据关联及正文哈希。重放仍经 Policy，来源校验重放重新访问当前来源，避免发布失效草稿。Dense 保持版本 1；检索继续经 Policy/Executor，身份来自可信上下文。
- Hybrid 总期限默认 30 秒，Embedding 默认 8 秒，数据库阶段 5 秒，BGE 默认 15 秒，工具期限同检索总期限；Runtime 剩余期限仍生效。证据只装入完整 Chunk，全部超预算明确失败。
- 控制模型和组件：`.\.venv\Scripts\python.exe -m pytest tests/test_hybrid_task131.py tests/test_knowledge_graph.py tests/test_knowledge.py tests/test_hybrid_task121.py tests/test_reranker_task122.py -q`：32 passed。定向 Ruff 检查通过。
- 隔离真实 PostgreSQL：`.\.venv\Scripts\python.exe -B .git/task131-local-validation.py pytest -q tests/test_hybrid_task131_postgres.py`：1 passed。数据库名、用户、地址和专用 comment 经测试核验；写入唯一测试文档并经 Repository 精确清理。Embedding、BGE 与 LLM 为受控替身，此项不代表真实模型证据。首次运行因 Windows Proactor 不兼容 psycopg 失败；改用项目 `run_async` Selector 后通过。
- 真实 Qwen+BGE 应用启动及调用由主 Agent 在另一隔离库验证；本记录不声称该验证通过。本 Task 尚待独立 QA 与主复核，未进入 1.3.2。
