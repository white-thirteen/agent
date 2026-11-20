# Task6.3.1 独立QA

2026-11-15最新分工：用户自行导入Postman后明确确认完成并提供截图，六组请求(1/6/2/6/2/9，共26)和12个模块变量可见；随后授权继续后续实现。采用该用户回执作为实际导入证据，禁止再次控制Apifox/Computer Use。独立QA检查材料/真实功能与必要实际HTTP/SSE，客户端后置脚本运行及SSE界面效果如未实测必须单独注明，不从导入截图推导全部场景已执行。判断明确产品/材料缺陷与该客户端验证剩余项，不伪造GUI结果；后续632可承接该项跟踪，06最终验收仍需真实证据及用户确认。

后继准备，仅主Agent明确派发、Implementer停止后开始。读AGENTS/STATE、docs/v1/v1-06/06-demo-execution-task.md、D06第8～9节/Task6.3.1、实际集合/演示说明/交付。你作为独立操作者按导出材料实际验证，不改业务或替Implementer修复；仅写独立报告和必要复现证据，不Git/Bridge/另派Agent/SSH/PG重启/下一Task。

确认集合确可导入已安装Apifox、变量与SSE实际可用，不能只解析JSON或用httpx替代GUI证据。GUI操作先按computer-use可用技能读取SKILL.md并遵守规定工具。只用本地127.0.0.1测试服务、无秘密变量模板，不截图/导出.env、Chat/DB/SSH密钥；不覆盖用户已有集合或配置。接口分组/请求Schema/动态关联与实际API一致，无管理key/Header/客户端伪造Actor。

按说明独立复跑必要演示：订单事实、退款原中断的完整自有FastAPI进程重启后决定+独立resume、唯一业务结果、不同订单拒绝分支、RAG真实来源、跨会话/重启Memory及A/B隔离/修改删除。可按风险明确复用未变6.2故障/真实模型证据，独立操作步骤必须实际执行，不能把原文重新退款请求当resume。演示身份选择不是真实认证，production本地审批不可用。

项目.venv、test库agent_demo_test/agent_test、UUID自有数据、全部public完整行集及列定义/迁移checksum保护和按FK精确清理。新场景不得seed/改固定五订单，不能为演示重置历史成功数据。保护.env/006/旧证据/角色/冻结设计/六项暂缓变更。测试进程Settings test/UUID/EmbeddingTrue允许，不改真实配置。只控制自己创建且记录PID/命令的服务进程，单Qwen实例，结束确认退出/连接归零，不杀用户进程。

交docs/v1/v1-06/qa/06-demo-qa-report.md：PASS/FAIL、沿06-QA最大号续号/严重度/位置复现、实际导入/变量/SSE/操作证据、实际与复用/未验、清理及遗留。GUI/模型/资源不可用标BLOCKED，不降低冻结门禁。FAIL交原Implementer后独立复测，保留旧记录。完成停止，阶段验收仍由主Agent和用户决定。
