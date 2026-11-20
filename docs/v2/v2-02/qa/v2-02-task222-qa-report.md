# V2 02 Task 2.2.2 独立 QA

结论：FAIL（发现 P2 范围关联缺陷及验收证据缺口）。不代表阶段验收。

## V202-222-QA-001 / P2：节点重放未取得直接验证证据

冻结验证矩阵列有“节点重放”。`tests/test_context_revision_postgres.py::test_real_revision_adoption_and_receipt_recovery` 覆盖提交前与提交后 Saver 故障、回执补记、范围外追加、STALE 和第二次增量；提交失败后线程进入 `_uncertain`，该测试并未让原 Supervisor 节点对同一采纳计划实际重放，也未对重放后原始 Saver channel_values 和 Revision 回执做断言。实施记录与其所引原始输出未提供此场景的独立直接结果。源码检查不能代替该门禁；请 Implementer 补充真实 Saver 重放验证及其幂等/安全结果，再交独立复测。

## 实际验证

- `python docs/v2/v2-02/evidence/linux-pg-launcher.py pytest tests/test_context_revision_postgres.py tests/test_context_revision_runtime.py tests/test_runtime.py tests/test_graph_state.py tests/test_graph_protocol.py tests/test_refund_checkpoint.py tests/test_refund_full_controlled.py tests/test_refund_executor.py -q --tb=short`：82 passed，0 skipped；项目 `.venv`，隔离 Linux PostgreSQL 与真实 Saver、文件；模型为受控替身，故障在边界注入。[原始输出](../evidence/v2-02-task222-qa-run.txt)。原测试包含唯一身份与 thread，以及 finally 精确清理和清理后断言。
- 单独修改副本使第二次 Summary 的 parent_summary_id 为 None，真实 PostgreSQL/Saver 仍通过：[探针](../evidence/test_qa222_missing_parent.py)、[输出](../evidence/v2-02-task222-qa-parent.txt)，1 passed。允许无父摘要对全部 Archive 重新总结，单凭该结果不能判定缺陷；本探针使用受控 Summary，不证明真实模型实际完整覆盖。
- 阅读 Revision 发布/关联、Checkpoint 原始读取、采纳计划、Supervisor 更新、受理门禁与回执代码，核对既有实施报告及 2.2.1 主复核。没有修改既有业务代码、测试或正式数据库。

## 遗留范围

未直接执行同一采纳计划的节点重放；未模拟真实断电/在途进程杀停。摘要质量、维护调度、Builder、偏好入口及完整阶段门禁属于后续范围。无付费模型调用；真实模型摘要语义未由本轮验证。源码中的父摘要可选关联及第二次增量可用性已检查，但独立回归没有穷举所有错误关联和并发时序。

## V202-222-QA-002 / P2：增量 Revision 可丢失已卸载历史的摘要覆盖

在 [Repository 发布检查](../../../../app/context/repository.py:626) 中，新 Summary 只需与新 Revision 的消息范围尾缀匹配；[采纳检查](../../../../app/context/manager.py:488) 校验 base revision 与当前热消息，却未证明新 Summary 同时覆盖 base 已卸载的历史。独立探针在真实隔离 PG/Saver 上先采纳 revision 1；随后构造 revision 2，其 base_revision=1，但 Summary 仅覆盖新 archive2、parent_summary_id=None，完全不含 revision 1 已卸载的 archive 和消息。该 Revision 仍成功发布并由下一 Run 实际采纳为 APPLIED，Checkpoint 原有 ContextRef 被新引用替换；新 Summary 的范围缺失旧历史。原 Archive 和旧 Checkpoint 仍保留，但新会话版本不能通过其引用恢复这部分摘要。

复现命令：`python docs/v2/v2-02/evidence/linux-pg-launcher.py pytest docs/v2/v2-02/evidence/test_qa222_missing_history.py -q --tb=short`；项目 `.venv`，结果 1 passed；[探针](../evidence/test_qa222_missing_history.py)、[原始输出](../evidence/v2-02-task222-qa-missing-history.txt)。该探针沿用既有唯一身份及清理断言。模型与 Summary 文本为受控替身，PG、Saver、文件及采纳流程真实；结论针对可观察的关联和范围，不声称已运行真实摘要模型。parent_summary_id=None 本身合法，问题是完整重摘要缺少 base 已卸载范围仍被采纳；增量使用 parent 时同样需要保证整体覆盖。

