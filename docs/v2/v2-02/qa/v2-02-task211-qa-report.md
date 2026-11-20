# V2 02 Task 2.1.1 独立 QA

结论：**FAIL**。两项 P2 交原 Implementer 修复并独立复测；不代表后续 Task 或阶段验收。

## V202-211-QA-001 / P2：完整消息列表无法增量摘要

位置：`app/context/compaction.py` 中 `max_tokens_before_summary=count`。LangMem 0.0.30 根据 last_summarized_message_id 跳过已摘要消息，适配器的 count 却包含这些旧消息。

独立复现：先摘要 Human ID 1，再以 running_summary 和完整列表 `[ID 1, ID 2]` 调用，抛 `ValueError: LangMem did not summarize the entire range`，没有模型调用；仅传 `[ID 2]` 正常返回覆盖 `{1,2}`，重放 `[ID 1]` 无新调用。完整列表是 LangMem 支持的输入，当前适配器并未限定只能传增量范围。

## V202-211-QA-002 / P2：调用后覆盖检查失败丢失预算及用量

位置：`app/context/compaction.py` 的 LangMem 返回后覆盖检查。输入 `[SystemMessage(content='', id='s'), HumanMessage(content='hello', id='h')]`，内容长度计数器，初始 Task 尝试 0。LangMem 排除首条 SystemMessage，Gateway 受控模型实际调用 1 次，返回 known input 10/output 2/total 12；随后覆盖检查抛裸 ValueError，异常不含 model_usage 或 usage，调用方无法回收本次消耗。此输入不属于设计中的常规公开归档范围，但适配器当前接受后才调用模型。须在调用前拒绝不支持范围，并保证支持范围内调用后失败仍可回收已消耗快照。QA-001 本身未发模型调用，不能用其证明预算丢失。

复现脚本及输出：[probe.py](../evidence/v2-02-task211-qa/probe.py)、[result.txt](../evidence/v2-02-task211-qa/result.txt)。调用真实 LangMem，模型为受控替身。

## 实际核验

- `.venv` 定向 pytest：`tests/test_context_contracts.py tests/test_model_gateway.py tests/test_memory_manage.py tests/test_memory_reader.py tests/test_config.py -q`，38 passed，1 条 trustcall 上游弃用警告。
- `pip check` 无冲突；定向 Ruff check 通过，format 检查 7 文件通过。requirements diff 原有解析版本未升级，新增 LangMem 及五项传递依赖。
- 只读检查 LangMem 安装源码、身份和契约、维护 Gateway、配置、旧来源及实施证据。身份编码不授予权限，后续仓储仍须按独立身份列核验；维护持久预算目前仅接口。
- 实施者真实调用记录为一次合成输入、input 19/output 37；本 QA 未重复付费调用。4096/128 为探针参数，不证明真实满窗口；主 Agent 新的模型能力回执为能力元数据，不替代满窗口验证。维护尚未装配。
- 持久预留原子性、重启不重置、文件/PG、Checkpoint、完整关联及后续执行接线属于后续任务，未在本次验证；未访问正式数据库。
