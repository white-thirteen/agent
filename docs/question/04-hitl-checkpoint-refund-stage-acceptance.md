# 04 HITL、持久Checkpoint与模拟退款技术验收

日期：2026-11-13。分支 `real-model-chat`，HEAD `50e4c55476e714ed1e6d692511d8d878108c399b`，验收对象包括当前未提交工作区。**主Agent技术验收通过，用户已正式验收04，阶段ACCEPTED；用户已授权本轮Git提交并推送；05等待角色配置，不启动。** 提交/推送依据本轮用户新指令，正式验收本身不授予下一阶段开发权限。

## 用户正式验收记录

2026-11-13，用户明确指令“将04正式验收”，确认本阶段正式验收通过。状态由VERIFIED更新为ACCEPTED；六Task、独立QA、两轮修复与复测及既有遗留决定均按下文证据保留。本轮只更新验收状态和导航，不重复测试、不修改业务代码或数据库，不暂存、提交或推送Git，不启动05。

## 范围与依据

沿冻结[D04](../04-hitl-checkpoint-refund-detailed-design.md)和原六Task执行，未改变Task划分或冻结设计。主Agent复核Implementer交付、实际生产调用/关键测试源码与安全JSON，再以独立QA及修后复测裁决；主Agent没有把开发自测冒称自己重跑的结果。通过原生Multi-Agent串行开发→QA→原Implementer修复→独立复测，未使用Session Bridge。

| Task | 技术结论与证据 |
| --- | --- |
| 4.1.1 PG Saver装配 | 通过。正式生命周期、独立Saver池及严格Serializer、sync边界与真实嵌套快照已验证；无内存降级。 |
| 4.2.1 模拟退款事实 | 通过。真实PG归属/资格/金额、原操作幂等及订单/申请事务结果；测试精确清理并核对原事实。 |
| 4.2.2 审批存取与身份 | 通过。本地服务端Actor、决定/恢复分离、期限/并发/同决定幂等、完整只读视图及普通输入隔离。 |
| 4.1.2 安全Resume入口 | 通过。原thread/Task、四类恢复、当前run/context和累计用量、绑定修复及审计关联/锁后再检。 |
| 4.3.1 RefundAgent中断链 | 通过。正式主/专业图、真实interrupt、原ToolCall/ToolMessage、安全工具统一执行与拒绝闭合。 |
| 4.3.2 重启及重放验收 | 通过。真实uvicorn/TCP旧进程退出后按原审批恢复；SQL提交后next=execute_refund及compose安全后段恢复零退款写handler；未执行新标记sync后再检；未知安全拒绝。 |

## 问题闭环及质量门禁

- **04-QA-001～006关闭**：[首轮独立复测](04-hitl-checkpoint-refund-fix-01-regression-report.md)按原11场景、必要补测与源码核对通过；原QA及修复记录保留。
- **04-QA-007关闭**：[阶段QA](04-hitl-checkpoint-refund-restart-qa-report.md)真实复现已决定空绑定、不存在审计checkpoint及CAS前主体变化三项缺口；[第二轮修复](../resume/record/04-hitl-checkpoint-refund-fix-02-report.md)增加精确审计读取与锁后期望主体/决定再检，原三字段工具绑定快照保持。
- [第二轮独立复测](04-hitl-checkpoint-refund-fix-02-regression-report.md)原A/B/C均409、零新Run/Graph；正常repair跨进程恢复通过，原调用执行一次。新增真实PG测试及定向审计ID差异用例2 passed/0 skipped，原24矩阵#3/#4/#10/#14缺口闭环；213项保护摘要无变化。
- 最终实现版本完整真实库回归由Implementer执行：**165 passed、0 failed、0 skipped（61.78s）**；全仓Ruff代码检查通过，121个Python文件格式检查通过。独立QA按风险复测，未无收益重复全量或付费模型；来源和实际命令分别列在报告。
- [4.3.2交付](../04-hitl-checkpoint-refund-restart-report.md)的真实PG/独立进程、uvicorn/TCP、SQL/Checkpoint故障、DeepSeek原生调用闭环证据按适用范围保留。恢复实测为根Command或None、原wrapper子None，当前可信recovery在原namespace被原节点消费；零写保护来自核对/守卫，而非假定None会跳过节点。

原24项矩阵以阶段QA分层证据和本轮四项补验共同支持，不把所有场景都写成本轮重新独立实测。修复未改变Prompt、工具schema或供应商调用协议，真实模型证据沿用且未重复付费。

## 数据保护、限制和交接

真实验证只用专用agent_demo_test/agent_test，在线核对001～005及登记checksum。唯一数据、业务全行集/迁移/固定五订单前后核对、Saver自身线程精确删除均有记录；未重建资源、改迁移、换密或访问应用库。完整回归既有seed幂等用例的窄例外保留原断言并恢复固定事实，不用于重置退款数据。

没有未关闭的04实现/验收阻塞。明确限制保留：单独Saver写失败可能留下未识别快照，或标记未sync而无可信窗口时，自动恢复409并要求核对；不承诺任意Python崩溃、多实例互斥、全局Exactly Once或持久SSE重放。业务成功事实仍以数据库查询为准。Demo凭据暴露/密码复用与P3-01六份Markdown格式遗留沿既有用户决定保留。

原生通用子Agent调用与角色职责已实际验证；项目`.codex`自定义角色配置仍缺失，不能声称已加载Implementer/QA配置，不属于04业务通过声明。05/06未开始。

最新交接见[STATE](../STATE.md)。本阶段正式验收已完成；用户已授权本轮Git提交并推送，归档进行中。下一Task **5.1.1 导入与向量资源**等待用户设置角色配置及后续指令，本轮不启动05。
