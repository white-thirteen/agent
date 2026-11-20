# Task 2.3.2 fix02：DeepSeek 输出上限与摘要截断

关联 [修复任务](../v2-02-task232-fix02.md)。本记录为实施证据，不自行宣告质量或阶段验收。

`app/infrastructure/model.py` 只对 `api.deepseek.com` 选择 `DeepSeekChatOpenAI`，在 SDK 构造最终请求后将 `max_completion_tokens` 改为该服务 Chat Completions 所需的 `max_tokens`；其他 host 使用原 `ChatOpenAI`。未更换模型或依赖。`app/context/compaction.py` 的摘要桥先记录 Gateway 调用和实际 usage，再拒绝 `finish_reason=length`，沿已有 `CompactionError` 返回已用预算；普通聊天路径未改。

原真实异常及其不可追溯范围保留：[摘要请求上限256、供应商报告output333的资源实验](../../evidence/v2-02-task232-resource-runtime.json)。该轮没有保存实际请求/完整响应，不能断言它的 finish_reason 或 response usage details；已安装SDK的参数转换和[DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/)对字段的声明构成修复依据。

验证结果：

- 项目 `.venv` 受控 HTTP 使用真实 LangChain 请求构造，普通、结构化、运行内摘要及独立维护路径分别检查实际 wire 字段和输出限额；其他 provider 仍使用原字段。摘要 `length` 按 `CompactionError` 保留真实尝试和用量。`python -m pytest tests/test_deepseek_output_limits.py tests/test_context_contracts.py tests/test_model_gateway.py tests/test_resources.py -q --tb=short`：**30 passed**，1 条上游弃用警告，[输出](../../evidence/v2-02-task232-fix02-controlled-r3.txt)。
- `local-pg-launcher.py pytest tests/test_context_compaction_postgres.py -q --tb=short`：**1 passed**。真实隔离 PostgreSQL、实际文件及 LangMem，受控截断模型；Archive 保持 READY、维护 FAILED、无 Summary，消耗次数和输出用量不丢，[输出](../../evidence/v2-02-task232-fix02-local-pg.txt)。
- 一个真实低限额请求使用真实独立维护所有者及持久预算：wire `max_tokens=8` 且没有 `max_completion_tokens`，实际返回模型 `deepseek-flash`、completion 8、finish_reason `length`、尝试及持久预留均1；只保存脱敏字段与 usage，临时 schema 清理通过。[原始回执](../../evidence/v2-02-task232-fix02-limit.json)。这验证该次实际低限额，不推导所有模型/协议的能力。
- 隔离 Linux SSH 隧道曾掉线，重跑前只读 guard 未通过，[失败输出](../../evidence/v2-02-task232-fix02-controlled-r2.txt)保留；主 Agent 仅恢复本轮隧道后继续，未操作正式环境。
- 输出参数修复后，八个冻结语义场景完整真实复测一次；[r5 原始文本和用量](../../evidence/v2-02-task232-quality-r5-raw.jsonl)中八次调用均返回、output均不超过各自1024限额。语义仍交独立 QA：首例“当前没有已完成的查询”和伪审批例“explicit negation of approval”等可能超出源内容，不能以 r4 或覆盖 ID 判质量通过。前四轮原始输出与失败均保留。
- [资源实验修复后重测](../../evidence/v2-02-task232-resource-runtime-r2.json)为真实 Runtime 正式 Task/Run 同一实验节点中的3次真实调用。为完整处理长历史，将摘要上限由原异常轮256调整为512，普通请求输出预留仍512；v4摘要 input6091/output367，耗时4.30秒，未触发 length。相同当前问题、模型、节点和预留下，24条原文与摘要各一次消费的真实 provider input 为 **6958→502**；摘要一次性调用成本独立计入，不将输入减少直接称整体成本下降。模型输入本地估算分别3394与257；隔离PG/Saver数据精确清理，快照通过。
- 本次涉及文件 Ruff check 和格式检查通过。由于模型基础设施发生改变，修复前的完整 **287 passed** 不能代替修复后完整门禁；该门禁等待当前独立质量审查及后续必要代码稳定后执行。
