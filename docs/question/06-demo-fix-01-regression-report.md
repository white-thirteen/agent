# Task6.3.1 / 06-QA-001 独立复测

2026-11-15；结论：**PASS。06-QA-001/P2 独立复测通过，Task6.3.1 整体技术 QA PASS**，交主 Agent 复核关闭问题。初始[FAIL报告](06-demo-qa-report.md)、[原缺陷探针](06-demo-qa-probe.py)和[原真实复现](06-demo-qa-reprepare-evidence.json)原样保留。本结论不代替06正式阶段验收或Git归档授权。

依据[独立复测任务](06-demo-fix-01-regression-task.md)、[修复任务](../resume/06-demo-fix-01-task.md)、[Implementer修复记录](../resume/record/06-demo-fix-01-report.md)，独立阅读当前 `scripts/demo_session.py`、`tests/test_demo_session.py`、真实KnowledgeRepository事务及更新后的演示说明。未修改产品、既有测试、配置或旧证据，未代修。

## 修复与实际复测

`scripts/demo_session.py:197` 在进入prepare的try/cleanup作用域**之前**用 `mkdir(..., exist_ok=False)` 获取新目录。既有目录直接抛FileExistsError，既不调用prepare，也不读取旧manifest/基线或触发cleanup；新目录由当前调用拥有后，原部分失败精确清理仍保留。修复范围与问题根因一致，无新增恢复平台。

使用项目 `.venv`，独立显式执行：

```powershell
$env:AGENT_VERIFY_DEMO_QWEN='1'
$env:AGENT_DEMO_FIX_EVIDENCE='D:/py/agent-project/agent/docs/question/06-demo-fix-01-qa-real-evidence-20261115.json'
.\.venv\Scripts\python.exe -m pytest tests/test_demo_session.py -q
.\.venv\Scripts\python.exe -m ruff check scripts/demo_session.py tests/test_demo_session.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/demo_session.py tests/test_demo_session.py
```

实际结果：**3 passed / 0 failed / 0 skipped，71.06秒**；Ruff check通过、2文件格式通过。两受控CLI测试分别证明既有目录完全不进入准备/清理，以及新目录部分失败仍执行本轮清理并传播原错误。真实测试已显式启用，未将默认skip算通过。

真实回归由QA独立执行，新UUID目录/用户/订单/语料，原本地 Qwen CPU/1024 与真实 agent_demo_test/agent_test，无付费Chat：

- 首次正式CLI prepare成功，实际查询到两个自有订单及1024维chunk；随后真实创建本轮用户session/profile。重复同folder调用正式CLI退出1/FileExistsError，**整个public完整行集/列定义、目录全部文件字节完全相同**，故原订单、向量、manifest、保护基线、session/profile均保持。未仅比较计数或使用替身断言。
- 对另一全新目录，正式prepare完成真实Qwen计算，调用原 `KnowledgeRepository.replace`，在其真实事务提交返回后注入RuntimeError。仅故障点受控，Embedding、SQL发布、清理和全表比较均执行原实现。当前调用自动cleanup写出失败回执、传播原错误；最终全部public回到首次准备前状态，证明未通过移除异常清理来绕过问题。
- 两场结束精确清理；独立再读新JSON并断言 `protected_before == protected_after == 原QA缺陷复现清理后的protected_after`。001～006在线checksum、13张public原行集/列定义和固定五订单保持。没有seed或扩大清理。

[本轮独立真实证据](06-demo-fix-01-qa-real-evidence-20261115.json)、[独立最终审计](06-demo-fix-01-qa-final-audit-20261115.json)。本轮没有使用或覆盖Implementer自测JSON。

最终审计核 `.env`、006、Implementer/QA角色、初始FAIL报告/探针/JSON SHA256与本轮记录值相同。顺序子进程均已返回，观测的QA launcher/worker PID 49452、53184、31324、1876最终均不存在；没有启动FastAPI服务或停止其他进程，没有并行Qwen实例。未执行Git、Bridge、SSH、PG/容器重启、GUI、另派Agent或下一Task。

## Task6.3.1 整体裁决与剩余项

初始独立QA通过的[11端点/26请求/12变量与15受控脚本分支证据](06-demo-qa-contract-evidence.json)继续有效；本次修复没有修改集合或API。真实三段退款完整进程重启/原approval独立resume/唯一业务结果、真实Chat/RAG来源、Memory重启隔离与CRUD，以及前序独立恢复和225项完整PG门禁的出处沿[初始报告](06-demo-qa-report.md)“实际导入、复用与未验”节，明确为复用，本轮没有再次付费或机械重跑全量。此前唯一阻塞06-QA-001现已独立复测通过，无新增问题编号。

实际导入采用用户手动完成并提供截图的回执，六组26请求和12模块变量可见；本轮遵守禁止GUI操作分工。**Apifox后置脚本真实执行、变量实际回填和SSE客户端界面效果仍未实测**，不从导入截图、Node受控运行或HTTP证据推导GUI全场景PASS。材料具有人工复制原关联的操作路径，未发现该剩余项对应的明确材料缺陷；交主Agent后续交付材料跟踪，06最终验收仍由用户确认。

完成停止，建议主 Agent 复核关闭06-QA-001并确认Task6.3.1技术交付；未自行进入6.3.2或宣布阶段ACCEPTED。
