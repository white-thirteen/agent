# V2 02 Task 2.3.1 修复记录：V202-231-QA-001 / P2

关联 [QA 首轮报告](../../qa/v2-02-task231-qa-report.md) 和 [fix01 修复任务](../v2-02-task231-fix01.md)。本记录交原 QA 独立复测；问题是否关闭由主 Agent 决定。

`app/context/maintenance.py` 的 `_repair_published_receipt` 在发布流程或源消息前缀核验之前，只对 `SUCCEEDED` 且缺少关联回执的工作检查已有 Revision。它核对用户/会话、固定来源 Checkpoint、基线版本、消息范围和内容、Archive 引用、Summary、输入哈希、策略及模型/Prompt 版本，并读取 Archive 验证完整性。仅当对应 Revision 为 `PUBLISHED` 或 `APPLIED` 且所有关联一致时，以条件更新幂等补记该工作的 revision；不会更改 Revision 状态、运行 Graph、重新调用模型或重置预算。已有回执直接返回，源 Checkpoint 或策略不一致时不补记。原发布路径同样只给 PUBLISHED/APPLIED Revision 登记回执，避免将 STALE 当成发布成功。

`tests/test_context_maintenance_runtime_postgres.py` 在真实隔离 PostgreSQL、真实 Saver 和文件、受控摘要模型上扩展验证：

- Revision 尚未采纳时，模拟发布后回执丢失并将原持久期限设为过期；补记后仍为 PUBLISHED，Graph Checkpoint 不变。
- 通过真实新请求及 Graph 采纳 Revision 后再次模拟回执丢失；补记和重复调用均保持 APPLIED、Graph Checkpoint/值不变、模型调用数不变、尝试记录及过期期限不变。
- Archive 哈希不一致或 Revision 策略不一致时不错误补记；恢复原证据后可重试。恢复扫描不再选中已补记工作，原有有限扫描和预算恢复用例继续通过。

进程中断通过持久数据库回执置空模拟；Graph 采纳使用真实新请求，未声称执行真正的进程重启。测试自身先核对 `127.0.0.1:56431`、`agent_demo_test/agent_test`、PG 170012 和专用数据库 comment；使用唯一身份、会话和 thread，在 finally 精确清理并核对专属记录和 Saver thread。测试与其他写探针/全库快照串行执行。

实际命令：

```powershell
.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/linux-pg-launcher.py pytest tests/test_context_maintenance_runtime_postgres.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_context_revision_runtime.py tests/test_context_maintenance_shutdown.py -q --tb=short
.\.venv\Scripts\python.exe -m ruff check app/context/maintenance.py tests/test_context_maintenance_runtime_postgres.py
```

结果：真实隔离定向测试 **2 passed**，有 1 条第三方 LangGraph 弃用警告；[原始输出](../../evidence/v2-02-task231-fix01-pg-pytest.txt)。受控运行/关闭测试 **4 passed**，1 条同类第三方警告；Ruff 通过。原 QA FAIL 报告和探针未更改，探针中针对旧缺陷的队列出现两次断言仍是首轮复现，不作为修复后预期。

Gateway 输出预算另核对现有实际调用：普通业务节点不传 `max_output_tokens`，实际绑定上限与 Builder 的配置预留一致；唯一显式覆盖来自 LangMem 摘要桥接，该内部预检路径以同一摘要输出上限检查并绑定调用，Manager 同时检查模型配置限额。本次没有为假设性额外调用改动 Gateway。

未修改 `011`、冻结设计、正式数据库、`.env` 或 Git；未重跑完整 119 项受控组合、真实模型质量或阶段完整回归。待原 QA 独立复测本修复，不自行关闭 V202-231-QA-001。
