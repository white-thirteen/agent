# V2 02 Task 2.2.2 主复核

2026-11-19：**VERIFIED**，非人工 ACCEPTED。主 Agent 依据[首轮独立 QA](qa/v2-02-task222-qa-report.md)、[修复记录](fixes/records/v2-02-task222-fix01-report.md)、[独立复测](qa/v2-02-task222-retest-report.md)和相关源码，关闭`V202-222-QA-001 / P2`与`V202-222-QA-002 / P2`，允许进入2.3.1。

- Revision发布事务及采纳前都核对基线已卸载历史的完整覆盖；只覆盖新增范围的摘要不能替换原会话摘要。完整重做摘要可没有parent，合法增量和实际已采纳但回执尚失的PUBLISHED基线仍受支持。
- Supervisor原节点同一次状态更新提交ContextRef、RemoveMessage和热消息元数据，无新节点。重复计划核对既有版本和已移除范围，不重复移除，也不清零用量。
- Runtime受理前只读；STALE/APPLIED回执在受理后安全边界处理。`Graph.aget_state`可能叠加pending writes，实际采纳依据为正式Saver `aget_tuple`读取的完整Checkpoint，而非叠加视图。补回执不执行Graph、不解除uncertain。
- 旧ref保留固定版本，无ref不套最新摘要。暂停、审批、澄清和恢复模式保留既有门禁；未将摘要作为业务事实。

首轮独立真实PG/Saver、Runtime/Graph与退款组合82 passed/0 skipped；修复后独立定向8 passed/0 skipped，合法无父全量摘要独立探针1 passed。原接受缺历史的探针原样重跑为预期失败，证明发布已拒绝，保留原始输出，不计作普通回归失败或修改原断言。当前无未关闭本Task问题。

真实断电、在途进程终止、维护执行器、完整Builder与偏好迁移及摘要语义质量仍待后续Task。schema10仅应用于本轮隔离Linux双库，正式数据库未改；新代码正式部署需另行专项迁移授权。未提交或推送Git。
