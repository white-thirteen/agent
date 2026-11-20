# Task 1.3.2 前三局部重排实现记录

按已批准方案，Hybrid 检索仍对全部 RRF 候选调用一次现有 BGE，原有完整输入预检、异步工作线程、超时及错误语义保持；最终只按 raw logit 降序排列 RRF 前三，同分按完整来源身份升序，第 4 名起保持 RRF 顺序。候选诊断和 Evidence 的 retrieval_score 仍保留对应原始 logit，不能把该分数视为全结果的排序键。

`RetrievalProfile.reranker_order` 为 `rrf-top3-bge-local-v1`；旧配置序列化身份缺少此字段，Graph 现有 profile 校验拒绝旧缓存。`local_rerank_order(scores, identities)` 是纯函数，输入按 RRF 顺序，返回对应原索引，供运行时及对照复用。V1 Dense 和融合、模型实现未修改。

受控验证（项目 .venv）：

- `python -m ruff check app/knowledge/retriever.py app/knowledge/models.py tests/test_task132_local_rerank.py`：通过。
- `python -m pytest -q tests/test_task132_local_rerank.py tests/test_reranker_task122.py tests/test_hybrid_task131.py tests/test_hybrid_task121.py`：8 passed。覆盖前三以外候选不能挤入前三、原始分数及并列、短候选集合、第四候选超长导致整次失败、整体 deadline、旧 profile Graph 回放拒绝、默认 Dense 及既有 BGE 容量与预检。
- 首次运行 7 passed、1 failed：新增测试夹具的第四项正文未设为标记值，修正夹具后上述复测通过。

本次未运行真实模型、数据库、网关、质量对照或完整回归；由主 Agent 组织后续验证和独立 QA。本记录不改变既有质量失败回执或阶段验收状态。
