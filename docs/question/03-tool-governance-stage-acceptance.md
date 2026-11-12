# 03 工具治理与模拟订单查询技术验收报告

日期：2026-11-12。**主Agent技术验收通过，用户已明确同意03正式验收，状态为ACCEPTED；03已以62b5eb2完成交付归档和远端核验，04未启动。** 已完成既定六Task、独立QA、两项问题裁决、修复及独立回归。没有新增规划或改变冻结D03。

## 1. 前置归档与验收依据

01、02均为ACCEPTED。02正式归档为 `94cf205a734c305a6919a34cfeacc3e717d4856f`，提交说明 `Complete Phase 02 - AgentRuntime and Supervisor`，分支 `real-model-chat`。68项阶段交付已推送至origin，2026-11-12再次核验远端分支指向同一提交；原六项暂缓/独立内容保留。

本阶段依据冻结[D03](../03-tool-governance-detailed-design.md)、[原Task执行任务](../03-tool-governance-execution-task.md)、[开发交付](../03-tool-governance-delivery-report.md)、[独立QA](03-tool-governance-qa-report.md)、[修复报告](../resume/record/03-tool-governance-fix-report.md)和[独立回归](03-tool-governance-regression-report.md)判断。完整裁决及调度过程见[主Agent协调记录](03-tool-governance-main-review.md)。Bridge维护是独立工具工作，其92项测试不计入业务验证。

## 2. 六Task及交付

| Task | 最终交付 | 结果 |
| --- | --- | --- |
| 3.1.1 Metadata/Registry | 唯一工具定义、完整元数据、重名拒绝、启动冻结、过滤发现视图 | 通过 |
| 3.1.2 过滤与模型绑定 | Agent/scope和可信查询目标交集，get/list单工具及完整Schema实际绑定 | 通过 |
| 3.2.1 Policy/Executor | 三态策略、统一执行入口、最小业务上下文、每尝试计数、有限安全重试与超时取消 | 通过 |
| 3.2.2 工具消息与治理 | 原生调用批次预检、串行截断、逐call闭合、私有快照和可信origin/run_id | 通过 |
| 3.3.1 最小模拟订单事实 | 003迁移、双用户五订单、精确金额、owner SQL及领域复核、幂等种子和独立数据异常 | 通过 |
| 3.3.2 OrderAgent查询 | 七节点查询闭环、事实摘要、主图/Runtime/HTTP接线、澄清与预算继承 | 通过 |

开发报告记录两库001–003迁移及显式种子初始化。独立QA和回归只用专用测试库，核验身份/版本/checksum、五订单及完整行集；不把源码或种子文件存在当作真实环境证据。

## 3. D03第13.2节验收矩阵

| 门禁 | 独立证据与判断 |
| --- | --- |
| Registry与Schema | 注册/冻结/过滤测试，实际ChatOpenAI请求完整Schema与并发绑定隔离通过 |
| 曝光与执行分离 | 未知、禁用、未允许、越权及错误参数均在handler前拒绝，零尝试 |
| Order任务范围 | get/list互换工具、改订单ID或扩大分页均拒绝，不扩大可信目标 |
| handler边界 | typed args一次验证；业务上下文仅user/task/run，数据层干净导入无工具/Graph/Runtime |
| 身份与owner | 参数注入拒绝，真实PG跨用户与不存在统一不可访问；SQL及Service双重归属核验 |
| Policy三态 | ALLOW才执行；DENY及审批未接入均零handler，无聊天审批或伪等待 |
| 尝试与限制 | 成功/失败/只读重试先计数；拒绝/未执行零计数，跨Run累计及耗尽阻断通过 |
| 批次与消息 | 重复/缺ID/超限/invalid calls整批零执行；可关联调用经Policy、失败后闭合，保留原call |
| 超时/取消/重进 | 超时不重试、取消停止后续；真实task.cancel传播；observe重进无handler/计数，Reducer配对稳定 |
| 表与种子 | 真PG精度/约束/时区、固定五样本、种子保留状态、完整行集和迁移checksum核验通过 |
| 订单结果 | 真PG get/list/隔离/空页，真实池关闭及受控SQL故障分类；ToolMessage/facts/固定摘要一致 |
| 专业主图 | 缺参同Task新Run及预算，唯一Response/图内run_finish，正式lifespan/HTTP/TCP断开后仍执行并释放资源 |
| 真实模型+PG | 独立DeepSeek/deepseek-flash get/list各2次模型、1次工具，原生调用/消息及源行事实一致；修复后证据适用性已核验 |
| 后继未实现 | Refund/Knowledge仍capability_unavailable；未实现或宣称审批/退款/持久恢复/RAG/Store |

逐项测试名称、实际命令、解释器和外部产物见两份独立报告。正式HTTP/TCP采用受控模型、真实PG和正式装配；真实供应商专项覆盖专业图，未宣称真实模型全HTTP端到端验证。该证据组合满足D03，不把未执行的组合场景说成通过。

## 4. 问题闭环与独立性

| 问题 | 裁决及修复 | 独立回归与主Agent决定 |
| --- | --- | --- |
| 03-QA-001 / P2 | 真实03分层偏差；领域定义读取故障，工具适配转换既有治理异常 | 干净进程无上层依赖；get/list安全重试、不可重试、编程错误、取消及真实查询保持。**关闭** |
| 03-QA-002 / P3 | 真实03私有记录偏差；保存可信origin/run_id，不取模型候选 | 不同Run、伪造候选拒绝、原调用及结果关联、observe重进和公开隔离通过。**关闭** |

主Agent检查修复前后仅三个实现和两份测试共五个受控文件变化；独立回归前后108文件摘要一致，原六项暂缓内容及删除状态一致。未发现新增需编号问题。

独立补测初次取消夹具直接抛CancelledError，安装LangGraph在未真正取消Task时按契约转换为NodeCancelledError。主Agent核对本地框架对应处理，认可其为夹具预期偏差；保留失败证据，仅调整外部刺激为真实task.cancel后两项复测通过，未降低产品标准或隐藏失败。

## 5. 实际验证结果

- 首次独立QA：完整专用真实库 **130 passed，0 failed，0 skipped**，外部 **16项通过**；显式真实模型+PG专项通过。
- 修复开发自测：受影响专用真实库 **58项通过**，用于交付核对，不代替独立QA。
- 最终独立回归：完整专用真实库 **137 passed，0 failed，0 skipped**；原16场景及新增11场景共 **27个不同外部场景取得通过证据**。外部合并初次25 passed/2 failed，修正夹具后仅复跑两项2 passed，未声称最终文件一次27全绿。
- 执行代码101文件format及对应lint通过；全仓format因原六份Markdown示例仍退出1，明确保留P3-01。
- 测试库前后均0 Session、5订单，完整行集及完整迁移记录摘要一致，测试数据回滚/精确恢复。回归无成功新迁移、无应用库测试、无基础设施重建。
- 最终修复只涉及异常转换及私有关联，未改变Schema、健康SQL/事实、模型配置或公共协议；原独立真实模型证据继续适用，修复回归付费调用0次。

## 6. 遗留、后继影响与Git状态

没有未关闭的03阻塞问题。P3-01原六份Markdown代码示例format、RISK-02-CRED历史暴露及三角色配置密码复用按既有用户决定保留，暂缓换密，后续输出继续脱敏。单进程执行、内存Checkpointer、无事件重放及演示身份边界仍是已声明限制。

04可按冻结设计复用Registry/Policy/Executor、get_order、稳定调用消息、最小业务关联及当前订单表；必须另行实现可信审批、持久恢复、退款事务与幂等。03记录不是审批凭据或持久副作用幂等表，不能据本阶段测试推导04能力已成立。

03交付提交62b5eb2c1d946d2b334b3f3a2bad6e748e5d0579，说明Complete Phase 03 - Tool Governance and Simulated Order Query，分支real-model-chat。45项已成功推送并核验origin指向同一提交，提交快照409处本地文件/标题引用通过。原六项暂缓内容及缺失状态不变；本回执作为后续文档记录保存，04启动仍待后续任务指令。

**用户已同意03正式验收并授权提交，归档完成后停止。本轮同时授权将适合的工程纪律提示合并到既有AGENTS.md，已保留冻结治理和必要审计边界。**
