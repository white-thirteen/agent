# V2 02 Task 2.2.2 首轮问题独立复测

结论：**PASS**。建议主 Agent 关闭 V202-222-QA-001 与 V202-222-QA-002；不代表阶段 ACCEPTED。首轮 FAIL 报告和原始探针均保留。

- **QA-002 / P2**：原始缺失基线历史探针原样重跑，原先能发布采纳的 Revision 如今在发布事务中抛出 `ValueError: Revision does not cover base history`。pytest 原始结果是 1 failed，这是旧探针仍期待错误行为的预期结果，并非测试通过；finally 清理断言执行。[原始输出](../evidence/v2-02-task222-qa-retest-original.txt)。独立运行当前真实 PG/Saver 定向测试，另验证旧版已发布的缺历史候选在采纳前被拒绝、合法增量和完整重摘要通过，以及基线为 PUBLISHED（回执丢失）时仍可采用。事务检查沿基线链校验同会话 Summary 及顺序覆盖；采纳检查复核并绑定 Checkpoint 的 Summary。
- **QA-001 / P2**：当前定向测试对真实 Graph 与 PostgresSaver 使用同一 Run 和采纳计划以 `Command(goto="supervisor")` 受控重放。复核测试断言及本轮实测：Saver 原始 channel_values 保留原引用、已卸载消息未返回、当前用户消息保留、预算增加；节点写入无重复 RemoveMessage，Revision 数量仍为 1，两次可信回执补记相同。此测试不构成对不确定任务自动恢复的授权。
- 额外重跑首轮无父摘要但完整覆盖旧历史的独立探针，**1 passed**，确认合法全量重摘要仍可发布并实际采纳。[输出](../evidence/v2-02-task222-qa-retest-full-summary.txt)。

## 实际命令与范围

项目 `.venv` 经 `docs/v2/v2-02/evidence/linux-pg-launcher.py` 执行 `pytest tests/test_context_revision_postgres.py tests/test_context_revision_runtime.py -q --tb=short`：**8 passed、0 skipped**，[原始输出](../evidence/v2-02-task222-qa-retest-targeted.txt)。独立原探针按原样以同一 launcher 执行，结果如上；两个探针与测试各自使用唯一用户、会话、thread 和 finally 精确清理。PostgreSQL、Saver、归档文件和 Graph 为真实组件；模型与摘要文本为受控替身，故障为边界注入。

未模拟真实断电或在途进程杀停，未验证真实模型摘要语义，也未重复首轮 82 项组合；任务后调度、Builder 与阶段完整门禁属于后续范围。未修改业务代码、原测试、冻结设计或正式数据库。
