# 04 Task 4.3.2 原生 Implementer 工作单元

日期：2026-11-13。用户已批准继续04；六项修复经独立复测和主Agent复核关闭，证据见 `question/04-hitl-checkpoint-refund-fix-01-regression-report.md`。本工作单元只实施冻结 Task **4.3.2 重启及重放验收**，按D04第13节该Task、第9节恢复语义及第15节24项矩阵执行，不重新设计或进入05。

## 范围与验收

- 复用当前正式退款图、父wrapper、Runtime、Policy/Executor、ApprovalService/MockRefundService、SessionRepository、严格Serializer和真实AsyncPostgresSaver。已有纯图probe不是退款业务验收。用独立进程运行正式应用拓扑，受控模型固定路由及原生call；waiting后完全退出原Python进程，再以相同拓扑在新进程按原审批/引用恢复，不能再次提交退款文本或换Task。核对原thread/task/call/args/digest/operation/审批、新run、累计用量及真实源表。
- 在真实SQL事务成功但回复/Checkpoint失败窗口验证 `next=execute_refund` 和其他安全后段；记录实际根/子调用、namespace、重入节点、当前context和成功事实复用。恢复时退款写handler尝试为零，原operation/ToolMessage不重复。同步标记失败时零写；确认未执行必须当前审批/权限/资格/预算再检、新标记sync；未知拒绝盲重发。故障注入仅在测试边界，不加生产开关，不用Command(goto)/图外注入批准状态绕过正式流程。
- 将第15节24项逐项映射至已有可信证据和本次实际测试，优先补缺少的真实PG/恢复/repair/并发/期限证据，不机械重复已有测试。明确受控模型、真实PG、完整进程和真实模型的不同证据层。阶段整合做一次完整真实库回归及Ruff质量检查，默认测试不付费。最后少量独立显式真实模型+测试库联调，沿现有provider/model；不打印秘密或模型内部原文。配置缺失或环境不可用时完成可独立推进部分并准确报告，不能用skip标通过或擅自重建环境。

## 保护与交付

先读AGENTS、本任务及D04对应小节，按需查现有交付/修复报告和代码，避免通读历史。当前HEAD为50e4c55，工作区原修改/删除/未跟踪文件保留；冻结设计、历史QA/修复证据、主Agent协调记录不可覆盖。不得调用Bridge/其他会话或派生Agent，不Commit/Push，不自行转下一Task。

测试仅用既有专用 `agent_demo_test/agent_test`，先validate_test_target及在线身份/001～005摘要核对。设置唯一用户/订单/session/operation/thread，测试前后核对业务表全行集/迁移摘要及Saver自身线程，按外键及Saver线程接口精确清理，只删除本单元记录；保留固定五订单和他人数据。不seed、不改迁移字节或校验和、不换密、不动应用库/基础设施。使用项目.venv与Windows selector runner；凭据只在进程内，输出安全类别摘要。

允许为实际测试发现的问题做本Task内必要最小修复，记录根因和影响；不得预先改动无证据的问题、增加编排平台或扩大业务。修复需独立QA复核。独立QA在Implementer交付后串行执行。

交付 `docs/04-hitl-checkpoint-refund-restart-report.md`，列实际文件、命令/通过失败跳过、24项证据索引、实际框架调用/重入、真实PG及进程证据、清理/前后核对、真实模型结果、未验项与限制。README只更新必要导航，不改冻结正文。完成回报并停止，主Agent决定是否交独立QA；不自行标VERIFIED/ACCEPTED。

## 既有完整门禁的窄例外

主Agent实际审查 `tests/test_order_postgres.py` 和 `scripts/seed_orders.py` 后，明确允许一次既有订单seed幂等测试：其seed使用 `ON CONFLICT DO NOTHING`，不覆盖既有订单状态，用例通过临时改变a-001的is_refunded并finally恢复原值来验证这一性质。该例外只用于保留完整质量门禁，不允许新增场景用seed重置退款事实。执行前保存并核对固定五订单完整事实，禁止并行数据库测试，执行后核对全部业务行集/迁移/Saver数据与原状一致；异常先按已保存事实核对，不重seed或覆盖未知差异。不deselect该项、不改断言或Mock核心行为。其余保护要求不变。
