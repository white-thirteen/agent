# Task 2.3.2 fix01：摘要来源边界

关联 [修复任务](../v2-02-task232-fix01.md)、`V202-232-QA-001` 和 `V202-232-QA-002`。本记录交原 QA 复测，不自行关闭问题。

`app/context/compaction.py` 将 LangMem 实际传入的历史消息转换成单一 JSON 来源数据：每条保留 user/assistant 角色、原文和顺序，增量场景的已有摘要位于单独的 `prior_summary` 字段；控制指令放在独立 SystemMessage，历史不再作为活动 Human/AI 轮次输入。使用标准 RunnableLambda 和 ChatPromptTemplate，不增加模型调用、Agent 或持久化平台。摘要生成升级为 `context-summary-v4`，新生成只接受当前版本；已发布旧版本的回执仍使用该版本核验输入哈希，不回写或覆盖旧摘要。实际格式化后输入经原 Gateway 桥再次计数，包含 JSON 编码和系统指令开销。

受控 HTTP transport 在真实 LangMem/Gateway 调用中检查初始与增量请求：实际模型仅收到 system 与 user(JSON)，旧 user/assistant 是 JSON 内数据，已有摘要独立保留；格式化后超预算不调用 provider。隔离PG/文件、真实LangMem及受控模型维护回归与隔离Hybrid定向同次执行：

```powershell
.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/linux-pg-launcher.py pytest tests/test_context_contracts.py tests/test_context_compaction_postgres.py tests/test_context_maintenance_runtime_postgres.py tests/test_hybrid_task131_postgres.py -q --tb=short
```

结果 **14 passed**，1 条第三方弃用警告，[原始输出](../../evidence/v2-02-task232-fix01-controlled.txt)。

受控检查通过后，原固定八例真实 DeepSeek `deepseek-flash` 摘要仅复测一次，使用真实独立维护所有者、持久预算、LangMem、Gateway、隔离 PG 和文件；来源 Task/Run/Checkpoint 是合成夹具，不是 Runtime 业务来源。未改变场景、标准或 hash，未重跑长资源场景：

```powershell
.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/linux-pg-launcher.py module docs.v2.v2-02.evidence.v2-02-task232-quality-probe --quality-r4
```

[八例原始摘要、覆盖和供应商用量](../../evidence/v2-02-task232-quality-r4-raw.jsonl)均保留，前 v1/v2/v3 输出与失败不覆盖。初审此前遗漏的未执行退款、重新核查和没有新退款请求均有表达，伪审批未升级权限；cross-agent 输出还包含 `No prior summary exists`，该输入元数据是否构成摘要污染交原 QA 判断。覆盖 ID 不是语义正确性证据，质量结论及问题关闭由独立 QA 裁定。
