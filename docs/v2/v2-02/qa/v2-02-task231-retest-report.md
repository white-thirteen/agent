# V2 02 Task 2.3.1 独立 QA 复测

结论：**PASS**。V202-231-QA-001 / P2 已完成修复复测，建议主 Agent 关闭；本结论不代表阶段验收。

独立复测探针 [test_qa231_retest.py](../evidence/test_qa231_retest.py) 基于当前真实组件测试，额外检查 Revision 的来源 Checkpoint、消息覆盖和维护记录 Archive 覆盖不匹配时均拒绝补回执。使用独立身份及 thread、真实隔离 PG/Saver/文件和受控摘要模型；通过实际新请求执行 Graph 采纳。发布后回执丢失以数据库置空模拟，没有声称真实进程重启。测试 finally 精确清理并核验关联数据和 Saver thread。

验证了采纳前过期工作补记后 Revision 仍为 PUBLISHED；真实新请求采纳后补记及重复执行保持 APPLIED、Graph Checkpoint 和值不变，模型调用、attempt 与期限不变。Archive 损坏、策略不匹配以及额外来源/覆盖不匹配均不补关联；恢复正确来源后可补记，有限恢复扫描转向后续有效工作。补关联没有将 PUBLISHED 冒充 APPLIED。

实际串行命令及输出：

```text
.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/linux-pg-launcher.py pytest docs/v2/v2-02/evidence/test_qa231_retest.py -q --tb=short
2 passed, 1 warning in 16.31s

.\.venv\Scripts\python.exe -m pytest tests/test_context_revision_runtime.py tests/test_context_maintenance_shutdown.py -q --tb=short
4 passed, 1 warning in 2.48s
```

警告均为第三方 LangGraph 弃用警告。未并发运行任何写探针与全库快照；首轮组合 14 passed / 1 failed 和清理后该文件独立 3 passed 的事实保留在 [首轮报告](v2-02-task231-qa-report.md)，该次失败为探针并发干扰，非应用缺陷。

源码核对 Gateway：普通业务节点实际调用不传输出覆盖，Builder 预留与绑定限额一致；唯一显式覆盖为摘要桥接，先按摘要输入限额检查，调用时绑定摘要输出限额。未将不可达的一般接口假设列为新问题。

真实模型质量、付费调用、完整阶段回归和客户端 UI 本轮未执行，继续按原授权留待后续阶段验证；不以受控模型代替真实模型结果。
