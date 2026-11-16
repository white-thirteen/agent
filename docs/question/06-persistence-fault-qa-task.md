# Task6.2.1 独立QA

仅主Agent明确派发且对应Implementer停止后执行。读AGENTS/STATE、docs/06-persistence-fault-execution-task.md、D06第6节/Task6.2.1及实际交付；按现有恢复架构独立验收，不重做04或另建恢复平台。默认只读业务/既有测试/配置/证据，仅写独立报告与必要探针，不代修、不另派Agent、不Git/SSH/PG重启/下一Task。

重点独立核完整FastAPI进程真正退出、新进程读取原PG Saver并恢复原interrupt/call/op；不能以同进程Runtime重建替代。新Run/原Task及累计预算、原child namespace/ToolCall/ToolMessage、审批Actor与规范参数持久一致。四类分类正确：interrupt/Gate后受核验推进，正常END零新Run/Graph/退款工具，未知不盲重放。父最后checkpoint仍running不单独判错，实际child interrupt与Runtime公共投影为准。

检查批准/拒绝/重复/相反/并发/过期及repair-binding真实事实。业务已提交后快照失败，原operation确认成功时退款写尝试和第二次变更均零；确认未开始再执行需可信准备边界/原批准期限/预算/Domain；unknown保持并停止。复用未变04证据必须标明来源，本轮完整装配/进程恢复需实际验证。受控Chat与真实PG区分，不能虚构付费模型或实际TCP。

根据实现风险执行必要定向及真实PG验证，独立检查清理/全public完整行集与列定义/001～006checksum和身份。只用test库UUID自有数据，禁新seed/固定五订单修改，完整旧seed幂等窄例外按AGENTS不得deselect。保护.env/006/冻结设计/旧证据/角色/六项暂缓差异，确认所有自行创建的验证进程关闭，不能杀用户进程。未变化完整门禁可明确出处复用，业务修改后必须最终版本完整通过。独立QA行为只读不等于额外权限隔离。

交docs/question/06-persistence-fault-qa-report.md：PASS/FAIL、沿06-QA最大号续号及严重度、位置/复现、实际测试与复用/未验、精确清理及遗留风险。FAIL交主Agent退原Implementer，复测保留旧报告，不以Task通过替代阶段验收。
