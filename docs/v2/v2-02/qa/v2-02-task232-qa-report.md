# V2 02 Task 2.3.2 正式独立 QA

**结论：PASS（当前 Task 技术 QA）**。本次未发现新的需修复编号问题。V202-232-QA-001、002、003 的修复复测通过，建议主 Agent 审核关闭；历史失败、r1–r5 原始输出与独立报告均保留。此结论不代表阶段 VERIFIED、用户 ACCEPTED 或 Git 授权。

## 独立验证

项目 `.venv`，通过 [linux-pg-launcher.py](../evidence/linux-pg-launcher.py) 的四库只读身份/版本/标记 guard，串行执行：

```powershell
.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/linux-pg-launcher.py pytest tests/test_context_migration.py tests/test_context_migration_postgres.py tests/test_context_compaction_postgres.py tests/test_context_revision_postgres.py tests/test_context_maintenance_runtime_postgres.py tests/test_context_revision_runtime.py tests/test_context_run_compaction_postgres.py tests/test_context_contracts.py tests/test_deepseek_output_limits.py tests/test_preference_cutover.py tests/test_preference_control_postgres.py -q --tb=short
```

**38 passed，0 failed，0 skipped，1 条上游弃用警告，58.11 秒**。真实隔离 PG/Saver/Store/文件配合受控模型和 HTTP transport；没有真实付费调用。实际测试使用唯一 thread、用户及 schema，finally 精确删除，并断言 schema 不存在、Saver thread 不存在、关联行及偏好 profile/receipt 清空；上述断言随测试通过。本轮没有独立做全库前后快照，不能把测试清理断言称为全库快照。未运行完整 290 项及额外质量/资源付费调用。

- [migration.py](../../../../app/context/migration.py) 从同会话 Saver 最近 Task 快照核验 owner、Task/workflow、终态及消息 ID 和内容；冲突、未证明者不猜测，保留原文并标 incomplete，未知 Run 为 None。[Runtime 新 Task 接线](../../../../app/runtime/agent_runtime.py:754)只在安全终态和 new 模式触发，恢复路径不触发。真实 Saver 测试验证可证明关联、未知文本保留、重复恢复和旧 Checkpoint 内容不变；活动/未知及冲突使用受控状态测试。
- 真实 PG 的 [compaction 测试](../../../../tests/test_context_compaction_postgres.py) 在受控模型调用开始且持久预留后真正 kill 独立进程，另启进程核查预留与 unknown 未记零、剩余额度及耗尽；不是外部模型在途或机器断电。真实 Revision/Saver 测试检查部分发布、采纳回执恢复、旧引用、重放及用户隔离；运行内压缩和任务后维护定向通过。维护 claim 竞争与执行互斥复用 [前序独立 QA](v2-02-task221-qa-report.md)、[采纳复测](v2-02-task222-retest-report.md)及 [来源回执复测](v2-02-task231-retest-report.md)，不能把组件竞争单独当成机器断电证明。
- [DeepSeek 适配](../../../../app/infrastructure/model.py)只对官方 host 映射最终 `max_tokens`；定向真实 SDK/受控 transport 分别核验普通、结构化、运行内与维护请求字段和温度，其他 provider 保持原行为。摘要编码后计预算；截断先保存尝试/usage，再失败。隔离 PG/文件与受控 length 测试验证 Archive READY、维护 FAILED、无 Summary；不把它称为真实服务端截断发布测试。真实 [低限额回执](../evidence/v2-02-task232-fix02-limit.json)记录一次 wire max_tokens=8、output=8、length、持久预留1、schema 清理，实际服务请求与受控故障路径分别成立。
- [fix03 独立逐例报告](v2-02-task232-summary-quality-fix03-retest.md)核对 v5 r6 八例每个事实、否定与新增项：QA-001 的三项遗漏、QA-002 指令混入及 QA-003 沉默推断均未复现。JSON 中保留来源角色和 prior_summary；摘要 temperature=0 是请求策略，不保证供应商确定性或语义保真。真实生成使用维护预算、隔离 PG、文件、LangMem、Gateway、DeepSeek；Task/Run/Checkpoint 来源为合成夹具，不能冒充 Runtime 业务来源。
- 偏好真实 Store/PG 与无模型 HTTP 测试覆盖 CRUD、版本冲突、重放、权限、UNKNOWN 阻塞与恢复；旧 Memory 活动状态和不明输入阻止切换。前序独立报告与本次测试共同覆盖旧引用、单会话安全边界；没有把旧代码的未覆盖路径推断为真实通过。

## 交付原始证据核对

- [最终完整回归日志](../evidence/v2-02-task232-full-regression-r3.log)显示 **290 passed**，对应 [结构化回执](../evidence/v2-02-task232-full-regression-r3.json) `pytest_exit=0`、passed=290、failed=0、skipped=0、real_qwen_enabled=true、paid_chat_calls=0；日志为 `-q` 聚合结果，不能逐项从日志直接识别每条测试。源码中原 seed 例外未被改写，`finally` 恢复实际原值；回执声明保护快照通过，唯一水位 36→47 与预审计 +11 一致。该门禁包含 V1/V2 01 回归，非本次独立重新跑 290 项。保护判断对水位采用预期增量，不能称所有行字节完全不变。
- [真实 Runtime 回执](../evidence/v2-02-task232-runtime-probe.json)记载真实模型 OrderAgent 查询唯一订单，PG 结果 12.34 CNY/paid/未退款；下一 Task 注入之前两条公开消息，关闭重启后 thread 绑定及待澄清 Task 不变。无历史会话因知识能力关闭返回 capability_unavailable，不是成功知识问答，也不能用于同节点资源比较。
- [真实 Qwen/BGE/Hybrid 组件回执](../evidence/v2-02-task232-real-hybrid-r2.json)记载六篇导入、两个原 query 返回 found、Evidence 校验 valid，六篇精确删除，保护检查通过，水位24→36。它是组件直接检索；当前 Query/Evidence Graph 接线由真实 PG/受控模型回归覆盖，不宣称真实外部模型 Knowledge Graph 闭环。[Qwen 额外故障回执](../evidence/v2-02-task232-qwen-evidence-r3.json)保留实际 Qwen 后的受控故障及清理记录，退出码1是预期故障，不是正常路径通过。
- [v5 资源回执](../evidence/v2-02-task232-resource-runtime-r3.json)记载同一 Runtime Task/Run 内三次调用、同节点/问题/模型/schema/输出预留下，消费者供应商 input 6958→225；本地估算 3394→154。生成摘要额外实际 input 6121、output 136，耗时约1.70秒，三次模型尝试均计预算；不能把消费者节省等同总成本净收益。归档 30,510 字节来自旧 v1 实验，非 v5 重测。r5 质量失败、旧资源超限与首次完整回归失败保留，不被本次结果抹去。

遗留：真实外部模型 Knowledge Graph 回答、机器断电、客户端 Postman 脚本/UI 均未实测；模型生成可能对其他或增量历史遗漏/误述，摘要始终低信任且不能授予审批/权限或代替当前事实。测试 transport、受控模型、故障注入和真实组件边界如上；用户数据、正式库、`.env`、业务代码和既有测试未由本 QA 修改，未进行 Git 或 Bridge 操作。
