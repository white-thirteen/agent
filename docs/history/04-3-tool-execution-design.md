# 4.3 Tool Policy 与统一执行入口——详细设计及三级执行任务（待审核）

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**设计待审核，未开发执行、未测试验收**。编制日期：2026-11-08。

依据：[04 统一计划/一致性审核](04-stage-execution-plan.md)、[4.1](04-1-order-service-design.md)、[Registry](04-2-tool-registry-design.md)、[OrderAgent](04-4-order-agent-design.md)、[03 架构](03-stage-detailed-design.md)。只定义未来实现，不创建 Python/表、不执行迁移/测试/模型调用。

## 1. 目标与职责

所有模型工具调用和以后确定性副作用调用经过统一 Executor。Policy 作安全判断，Executor 校验/调用/计量/封装，ApprovalManager（06）管理审批事实，DomainService 做资源和业务规则。

| 组件 | 负责 | 不负责 |
| --- | --- | --- |
| ToolExecutePolicy | 可信身份、Agent/Task、当前披露集合、scope、风险、执行权、审批证据等，返回三态 | 不执行 handler，不创建批准，不自行生成预算计数 |
| ToolExecutor | 参数 Schema、Policy 调用、统一预算预留/结算、超时、允许重试、结果校验 | 不提升权限、不替用户批准、不直接越过 Domain 查询 |
| ApprovalManager | 未来具体操作与参数快照、审批人/中断关联和幂等决定 | 04 不实现，不直接执行支付 |
| OrderService | orders:read、owner 查询、领域事实 | 不依赖 ToolRegistry/Graph |

当前活跃工具均查询或发现，不建设支付幂等账本、审批表或通用外部执行平台。对于未具备治理基础的副作用定义，即使错误注册也必须 DENY(capability_not_ready)。

## 2. 核心结构和接口

ToolCallRequest：call_id、name、arguments（有限 JSON）、registry_revision、task/run 关联。call_id 来源模型适配，执行上下文/身份单独传入，不能由 arguments 覆盖。

ToolExecutionContext：当前 Principal、Agent/Task、workflow/run/task、owner/epoch/claim、deadline、RegistrySnapshot、current_execution_set、已验证 Schema 摘要。它由 Runtime/专业 wrapper 的可信运行上下文提供，不放模型可修改的业务 entities；State 中只有引用，重新执行必须重验。

PolicyDecision：ALLOW / DENY / REQUIRE_APPROVAL，稳定 reason_code；审批要求只描述所需具体证据，不生成“已批准”。PolicyContext 包含已规范化参数摘要，以便未来审批与调用绑定。

ToolResultEnvelope：call_id、tool_name、tool_version、status、data、error。status= succeeded/rejected/invalid_arguments/failed/approval_required；data 为对应 result_model 验证后的 JSON，金额为两位字符串、时间 UTC。error 为安全 code/message/允许公开的字段问题。禁止 raw_exception、DSN、Principal、Repo、callable。

ToolExecutionOutcome：上述 envelope、可信 DisclosureDelta（可空）、内部审计/计量信息。仅 envelope 的有界投影可进入私有 ToolMessage；Delta 是可信 side-channel，不从模型内容反解。

接口：

```text
Policy.evaluate(context,definition,validated_args,approval_evidence) -> PolicyDecision
Executor.execute(call,context) -> ToolExecutionOutcome
OrdersHandlers.get_detail(args,context) -> OrderDetail JSON
OrdersHandlers.list_orders(args,context) -> OrderPage JSON
OrdersHandlers.get_logistics(args,context) -> LogisticsView JSON
```

Policy 不长持事务。执行前验证当前 owner/epoch/claim 和权限，预算 reservation 由 03 统一机制原子记录；不能把先 check 后 reserve 当成并发预算保证。

## 3. 参数校验与权限顺序

1. 验证调用外壳、call_id 唯一性、名字/arguments 大小和当前执行关联。
2. 按快照查定义并校验 revision；未启用、未知、不可见工具均用安全不可执行错误。先做身份/Agent/Task/scope/集合粗检，不对未授权工具泄漏详细参数 Schema。
3. 用注册 args_model 严格验证完整参数，拒绝额外字段，JSON 非有限数和身份注入；不从字符串猜测金额/订单号或替模型补订单事实。
4. Policy 使用规范化参数进行最终决策；当审批要求存在时绑定 tool/version、workflow/task、参数摘要和操作，不使用通用 approved=true。
5. ALLOW 后调用 03 reserve_tool_call；预算/失权失败不执行。执行前必要的当前性检查不替代 Domain 所有权检查。
6. handler 只调用 Service，结果以 result_model 校验并安全投影；结算预算和审计后返回。

参数 Schema 校验负责结构，OrderService 负责领域输入及跨字段规则，允许直接领域调用仍校验，不为消除重复把 Service 外部边界删掉；内部 Repo 不重复所有验证。

## 4. 三态策略、风险和审批边界

| 判断 | Executor 行为 |
| --- | --- |
| DENY | 不调用 handler、不预留业务执行次数；返回 rejected 和安全码；模型循环本身仍受模型/总期限限制 |
| REQUIRE_APPROVAL | 不调用 handler；04 无 ApprovalManager 时返回 failed(code=approval_unavailable)，不能创建假审批或等待状态 |
| ALLOW | 原子预留后执行，成功/失败都按尝试结算 |

LOW/MEDIUM/HIGH/CRITICAL 是服务端风险分类，不能单凭 risk=LOW 自动放行；仍检查所有上下文条件。查询 MEDIUM、无需审批，但 orders:read 缺失必须拒绝。未来 HIGH/CRITICAL 的审批策略由业务/06 确认；工具显式 approval_required 永远不能因低风险绕过。

04 可用契约测试验证 REQUIRE_APPROVAL，但应用不会发 approval_required SSE。只有 06 的真实记录和 interrupt 成立后才能返回业务等待；该扩展复用 Executor，不新建旁路执行器。

## 5. 超时、重试、预算与执行权

- 复用 03 reserve_tool_call/settle_tool_call，传 workflow/run/call/attempt 和执行权；每次实际 handler 尝试计工具次数。discover_tools 也是一次工具调用，不另设免费循环。
- 有效超时=min(metadata.timeout、工具配置上限、run 剩余期限)。SQL statement_timeout 属 4.1 读适配配置，上层取消仍需等待连接回滚/释放，不只丢弃 await。
- V1 只对只读且 idempotent/retry_safe 的明确瞬态连接错误最多一次重试（总 attempts 默认2）。参数/权限/不存在/数据不一致/超限/预算失败不重试；执行超时默认不自动重试，避免后台请求未结束叠加。
- 每次重试重新检查权限、执行权和剩余预算，生成新 reservation；ToolCall 的 call_id 不变，内部 attempt_no 增加；不能让 SDK/handler 再隐式重试。
- future side_effect=true 不能套用只读重试；必须先有稳定操作幂等与结果核对，未知结果不重发。
- 错误的未执行调用不消费“实际工具尝试”额度，但不能无限免费：4.4 有模型轮次、每批调用数和错误纠正上限；模型网关费用照常计。
- owner/epoch 丢失立即停止下一工具调用，不能由 Executor 通过旧 context 恢复权限。审计/预算写入按 03 guard/claim/version；共享模型/工具服务不保存用户可变状态。

## 6. ToolCall / ToolMessage 与标准结果

工具执行核心不依赖 LangGraph。4.4 的消息适配层负责把 outcome 转成 ToolMessage(content=安全 JSON,tool_call_id=原 call_id)。未来开发按实际安装版本核对构造签名；不假设第三方 ToolNode 自带本项目 Policy。

同一模型批的 ToolCall 串行处理，每个可识别、唯一 ID 的调用恰好一个 ToolMessage，包括拒绝、无权限、参数错误和执行失败；该批全部配对后才允许再调用模型。不可识别/重复 ID 的消息视为模型协议错误，不构造孤立结果、不继续带未配对历史调用。

已经有结果的相同 (run_id,task_id,call_id) 和相同规范化调用只复用私有观察，不再调 Service或消费工具预算；同 ID 不同参数/名字则协议错误。这个机制仅用于当前只读模型回合的消息去重，不是支付幂等，也不承诺跨崩溃 exactly-once。03 的旧 running 仍转核对，不自动重放。

一次返回的原生工具调用可以是多个，当前允许最多4个且串行。当前批执行集合在模型调用前冻结；首次 discovery 与业务混在一批时不能追认新工具权限，业务返回未披露拒绝。

ToolMessage 为私有上下文，不透传 SSE。执行结果 data 保留 typed 权威事实；模型投影有界，订单详细可显示前10条商品和完整条目数量，并显式 projection_truncated，权威数据不能被摘要替换。单份规范 JSON 最大128KiB建议上限，超过则 result_too_large 安全失败，不把截断 JSON 当合法结果。不得对未查询数据标成功。

错误映射：OrderNotFound→rejected/order_not_found（不存在/他人相同）；OrderPermissionDenied→rejected/permission_denied；InvalidOrderQuery→invalid_arguments；数据库不可用/超时/数据不一致→failed 安全码。不生成“没有订单”的假成功。编程错误不转业务拒绝，交 Runtime 安全失败；异常原文只在符合安全要求的内部诊断，不进入消息或公开日志。

SSE tool_start/tool_end 只由可信执行事件投影：通过授权/预留并开始调用才发 start，完成尝试后发 end；不公开参数和 data。Policy 拒绝可留内部审计，不强造已执行 start/end。Retry 对外一次逻辑调用，内部 attempt 单独计量，避免客户把重复尝试误认多项业务。

## 7. 文件、数据库和 State

计划文件：tools/models.py（共享契约）、policy.py、executor.py、implementations/orders.py、discovery.py（4.2拥有）、graph/specialists/order/tool_messages.py（4.4拥有）。测试 test_tool_policy.py、test_tool_executor.py。

04 不增加工具注册表或支付调用账本。审计/预算复用 03 已有接口与保留策略；当前工具观察放专业私有 State。未来 05/06 在业务副作用之前建立必要操作记录，不把 model call_id 或 run_id 当稳定退款幂等键。

## 8. 三级任务

### 4.3.1 执行与结果契约
- 目标/功能：统一可信 context、调用、三态和 outcome。
- 步骤：复用 Registry 版本→定义 call/context/decision/result→固定安全码和 JSON 边界→定义 disclosure side-channel。
- 文件/接口：tools/models.py；ToolCallRequest、ToolExecutionContext、ToolResultEnvelope。
- 前置：4.2.1、01/03 契约；后继：4.3.2～4.3.6、4.4.1。
- 未来测试：关联不匹配、结果非 JSON、身份混入 arguments、同 ID 变参。
- 完成/交付：一套共享契约和样例，无 Graph 类型或数据库对象泄漏。

### 4.3.2 Policy 三态判断
- 目标/功能：统一授权而不执行。
- 步骤：身份/Agent/Task/集合/scope粗检→规范参数后风险/审批判断→执行权当前性检查→安全决定码。
- 文件/接口：tools/policy.py；evaluate。
- 前置：4.2 Registry/披露、4.3.1；后继：4.3.3/4.3.5。
- 未来测试：每项关键拒绝、ALL scopes、审批证据错参/错操作、只读与副作用门禁。
- 完成/交付：无 Policy 直接调用 handler 或创建审批；业务归属仍留 Domain。

### 4.3.3 统一 Executor 与发现接线
- 目标/功能：每个调用都真正经过 Policy 和参数校验。
- 步骤：查快照→粗检→args_model→最终 Policy→budget reserve→调用→result_model→settle→outcome；接 discover handler 并输出可信 Delta。
- 文件/接口：tools/executor.py、discovery.py 装配；execute。
- 前置：4.3.1/4.3.2、4.2.4、03 实际预算接口；后继：4.3.4～4.3.7、4.4.3。
- 未来测试：未披露/未知/非法参数不调 handler，发现 Delta 与模型绑定一致。
- 完成/交付：唯一入口，无直接业务调用旁路，预算失败不推进。

### 4.3.4 订单薄适配器
- 目标/功能：将三个只读定义连接到 4.1 Service。
- 步骤：从 context 取 Principal→将 args 映射到领域 query→调用三方法→Decimal/时间 JSON 投影→异常安全映射。
- 文件/接口：tools/implementations/orders.py；get_detail/list_orders/get_logistics。
- 前置：4.1.4、4.2.5、4.3.3；后继：4.3.7、4.4 工具循环。
- 未来测试：真实 PG 同一用户/跨用户/无订单/未发货/分页结果与 Service 一致。
- 完成/交付：适配器无 SQL、无 Repo、无自建身份，数据不被模型重算。

### 4.3.5 超时、重试与预算
- 目标/功能：工具治理接 03，不建设第二套预算。
- 步骤：有效期限→逐尝试 reservation→已知瞬态重试→超时取消/回滚→执行权丢失→未结算保留。
- 文件/接口：executor.py、03 reserve/settle 适配；不改基础 Budget 的归属。
- 前置：4.3.3、03 已验收；后继：4.3.7、4.4.6。
- 未来测试：attempt计数、超时释放、重试耗尽/丢权、拒绝不执行；未知副作用不重试。
- 完成/交付：无隐藏重试、跨 run 不赠额度、工具超时与总期限一致。

### 4.3.6 消息关联与公开事件边界
- 目标/功能：执行结果可被正确配对且不外泄。
- 步骤：定义纯消息投影契约→批次顺序/ID检查→错误结果配对→限量数据投影→内部工具事件白名单；实际消息节点归 4.4。
- 文件/接口：结果模型/事件适配约定；4.4 tool_messages.py 的接口测试。
- 前置：4.3.1/4.3.3；后继：4.4.3/4.4.5。
- 未来测试：重复/缺失ID、业务与发现混批、失败配对、敏感内容过滤。
- 完成/交付：调用结果一一对应，无原始工具消息透传用户。

### 4.3.7 统一入口集成验收
- 目标/功能：证明 Model ToolCall 到数据库事实的安全执行链。
- 步骤：Registry→Executor→订单适配→Service→真实 PG；注入拒绝/超时/错误；核对预算和审计；审批仅契约测试。
- 文件/接口：tests/test_tool_executor.py、integration/test_order_tools.py。
- 前置：前六项及 4.1 真实 DB 验收；后继：4.4 最终集成。
- 未来测试：权限/参数/结果/重试/配对/数据库隔离矩阵；不靠 Mock Repo 宣布通过。
- 完成/交付：集成记录，明确未实现审批/取消能力；默认测试无付费模型。

## 9. 顺序、验收与待确认

4.3.1→4.3.2→4.3.3；之后4.3.4/4.3.5/4.3.6可独立准备，4.3.7统一收敛。共享executor文件修改串行。集成依赖01/02/03实际交付，不能只按设计认可跳过。

验收：所有调用统一入口、每次重新授权、参数/结果受约束、审批无伪批准、预算统一、只读可控重试、私有消息配对和数据库事实核对。ToolMessage/专业State由4.4落地，不能在Executor再建Graph循环。

待确认：三态在04无审批时明确失败、只读最多一次瞬态重试、每批4调用/128KiB结果、审计与投影限额。批准前不执行未来测试。
