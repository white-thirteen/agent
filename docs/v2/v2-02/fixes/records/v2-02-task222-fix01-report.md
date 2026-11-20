# V2 02 Task 2.2.2 首轮 QA 定向修复记录

关联 [修复提示](../v2-02-task222-fix01.md) 与 [独立 QA](../../qa/v2-02-task222-qa-report.md)。本记录交原 QA 复验，问题未由 Implementer 自行关闭。

- **V202-222-QA-002 / P2**：`app/context/repository.py` 在 Revision 发布事务中锁定并核验同会话基线 Revision 及其 Summary，要求新 Summary 的 Archive 和消息范围按序覆盖基线的完整范围。沿基线链逐级检查以拒绝旧版本已经遗漏祖先历史的情况；基线可以是 PUBLISHED 或 APPLIED，避免将丢失回执误认未采纳。`app/context/manager.py` 在采纳前独立重新核验覆盖关系，并核对来源和当前 Checkpoint 引用的 Summary 与基线一致。完整 Archive 重摘要的 `parent_summary_id=None` 合法，有父摘要的增量同样合法。
- **V202-222-QA-001 / P2**：`app/graph/nodes/supervisor.py` 收到同一计划且 Checkpoint 已绑定该版本时，验证对应引用及已移除消息/元数据后不重复返回 RemoveMessage，继续执行节点；不一致仍报错。现有测试通过真实 Saver 的原图以 `Command(goto="supervisor")` 重放该次 Run 的同一个执行上下文和采纳计划；这仅是受控节点重放，不作为不确定业务任务的自动恢复授权。

## 实测

- 项目 `.venv`：`python docs/v2/v2-02/evidence/linux-pg-launcher.py pytest tests/test_context_revision_postgres.py tests/test_context_revision_runtime.py -q --tb=short`，**8 passed**，[原始输出](../../evidence/v2-02-task222-fix01/regression-final.txt)。Linux 专用 PG、PostgresSaver、文件真实；模型与摘要文本受控。测试在写入前检查端口、库、角色、版本及 marker，以唯一用户/会话/thread 创建数据，finally 精确删除并验证清理。
- QA-002 的无父摘要且仅含新增 Archive 的复现现被发布事务拒绝且无 Revision 行；测试在专用唯一身份下构造旧实现留下的 PUBLISHED 候选，采纳前再次拒绝。另验证覆盖完整历史的无父摘要重做与有父摘要增量均可发布及通过采纳核验，并验证基线回执丢失而仍为 PUBLISHED 时仍允许。无父摘要完整重做进一步通过真实 Graph 采纳。
- QA-001 对同一计划实际重放后，检查 Saver 原始 `channel_values` 中引用仍为原版本、原已归档消息未出现、当前任务用户消息保留、模型尝试数增加而非清零；检查节点写入无 RemoveMessage，Revision 数仍为1，回执补记后再次补记结果不变。不是仅检查 Graph 的 pending-writes 叠加视图。
- `python -m ruff check app/context/repository.py app/context/manager.py app/graph/nodes/supervisor.py tests/test_context_revision_postgres.py` 通过；`python -m ruff format --check` 对上述文件通过。

未改已应用的 010、冻结设计或正式数据库；未提交或推送。真实断电、真实在途进程被杀及真实摘要语义不属于本次受控修复验证。
