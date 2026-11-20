# V2 02 Task 2.1.1 首轮修复独立复测

结论：**PASS**。建议主 Agent 关闭 V202-211-QA-001、V202-211-QA-002；这不是阶段验收。

- **QA-001**：重新运行首轮独立探针，真实 LangMem 配合受控模型，完整 `[1,2]` 及仅新增 `[2]` 都得到覆盖 `[1,2]`，各增加一次调用；重放 `[1]` 不调用且保留旧摘要。
- **QA-002**：原 SystemMessage 场景在模型调用前拒绝，调用次数 0。另独立注入调用后覆盖结果损坏：真实 LangMem 与受控模型实际完成一次调用后替换返回结果，初始尝试 3，异常 `CompactionError` 返回尝试 4；known 用量 total 12，unknown 保持 total None，保留原 ValueError 原因。此为故障注入，不声称自然运行发生该错误。
- 复跑 `.venv` 定向 pytest：42 passed，1 条 trustcall 上游弃用警告；Ruff check 通过，format 2 文件通过。无依赖修改，沿用首轮 pip check。

原失败证据未覆盖。复测输出见 [retest-result.txt](../evidence/v2-02-task211-qa/retest-result.txt)；故障注入见 [retest-fault-probe.py](../evidence/v2-02-task211-qa/retest-fault-probe.py)、[retest-fault-result.txt](../evidence/v2-02-task211-qa/retest-fault-result.txt)。本次未调用真实模型或数据库；持久预算、重启、仓储及后续接线仍由后续 Task 实测。
