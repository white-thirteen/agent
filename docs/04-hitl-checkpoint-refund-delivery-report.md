# 04 HITL、Checkpoint 与模拟退款：执行中记录

日期：2026-11-12。以下为初轮执行时的历史记录；其中等待迁移授权的判断已被文末后续裁决和执行结果取代。本文不代表 04 开发完成或阶段验收。

## 已完成和实际资源变化

- 工作起点 HEAD `50e4c55476e714ed1e6d692511d8d878108c399b`；保留已有用户和主 Agent 的工作区差异，未触碰主 Agent 协调文档，未提交或推送。
- 真实环境只读核对开发库 `agent_demo`/`agent_app` 和测试库 `agent_demo_test`/`agent_test` 身份、001–003 版本及 SHA-256，均匹配。开始时两库均无框架 Saver setup。
- 新增 `app/infrastructure/checkpoint.py` 的独立 autocommit Saver 池及 setup 版本检查、新增显式 `scripts/setup_checkpoint.py`；已在用户授权的开发库和测试库各执行 Saver setup，重复执行测试库 setup 成功。框架版本 langgraph 1.2.20、langgraph-checkpoint-postgres 3.2.0；setup 使用框架自带实现。应用 `app/main.py` 已改为独立 Saver 池与 PostgreSQL Saver，失败不降级内存；保留 Runtime→模型→Saver 池→业务池关闭顺序。`tests/test_resources.py` 同步对应的资源测试替身。
- `scripts/probe_04_checkpoint.py` 使用唯一测试 thread 和真实测试库 Saver，输出 `NESTED_INTERRUPT_NAMESPACE_OK`、`COMMAND_WRAPPER_REENTRY_AND_EXECUTE_NEXT_OK`、`NONE_REENTERS_EXECUTE_RECOVERY_CONTEXT_OK`；证实 sync 中断的真实 child namespace 和 ID、根 Command 的 wrapper 重入、异常后 child `next=execute_refund`，以及以当前 context 调根 `ainvoke(None)` 会重新进入该节点并传入 recovery。该纯节点探针不验证真实退款事务，也不构成完全退出并重启 Python 的验收。探针仅删除自己的 thread，随后检查三张 Saver 数据表无残留。另以真实 Saver 和现有 Supervisor 图执行一次受控澄清，确认项目 State 的 Saver 序列化及读取；该探针 thread 已删除。
- `python -m pytest tests/test_resources.py tests/test_application.py tests/test_demo_identity.py -q`：18 passed。`ruff check` 对本轮 Python 文件通过。尚未运行阶段完整回归或真实模型。

## 必须处理的 004 迁移问题

本人新增 `migrations/004_refund_approvals.sql` 并已将其应用于**专用测试库**；测试库业务迁移现为 001–004，开发库业务迁移仍为 001–003。004 创建退款/审批表及订单复合约束，未向这两张表插入业务数据。开发库尚未应用 004，应用的业务 schema 期望值仍是 3，故当前代码的 schema 检查不接受测试库 4；这是未完成的过渡状态。

实际验证发现，004 中 `approvals.subject_snapshot` 的 CHECK 以 JSON key 存在和 `->>` 值相等判断 task/workflow。PostgreSQL 对两个 JSON null 的比较结果是 SQL NULL，而 CHECK 不拒绝 NULL，因此可放行 task/workflow 同为 JSON null 的主体，不满足冻结 D04 对两者非空同值的数据库约束。已通过只读表达式探针确认 `CHECK_ACCEPTS_NULL_CONFIRMED`。这是本次实施引入的缺陷，不是已确认设计需要更改。

已应用的迁移和登记校验和必须保留；直接修改 004 或手动改写测试库的登记记录会破坏迁移不可变性。本轮明确授权的是业务迁移 004，建议批准一个**定向追加的 005 修正迁移**，对两库的 approvals 增加约束：两个 JSON 字段必须都是非空字符串，且相等；先完成受控测试，再分别将开发库推进 004、005 和测试库推进 005，保留 001–004 原样。可用的约束表达式为：

```sql
ALTER TABLE approvals ADD CONSTRAINT approvals_subject_task_ids_required CHECK (
    jsonb_typeof(subject_snapshot -> 'task_id') IS NOT DISTINCT FROM 'string'
    AND jsonb_typeof(subject_snapshot -> 'workflow_id') IS NOT DISTINCT FROM 'string'
    AND length(subject_snapshot ->> 'task_id') > 0
    AND subject_snapshot ->> 'task_id' = subject_snapshot ->> 'workflow_id'
);
```

005 尚未创建或执行；未对数据库执行 DROP、清库、重建或修改其他用户数据。

## 尚未完成

4.1.1 的 Saver 资源及小探针已实现，但真实退款图、完全退出重启与故障窗口仍待验证；4.2.1 只有不合格的 004 初稿，领域事务尚未实现；4.2.2、4.1.2、4.3.1、4.3.2 均未实施。D04 第 15 节 24 项不能判为通过。尚无审批 API、可信绑定/repair、四类安全恢复、退款执行、真实模型验收或 05 接口交付。应先解决迁移不可变性与约束缺陷，再继续顺序实施；在此之前不应运行测试库普通应用或宣称 04 已完成。

## 后续实施记录（2026-11-12）

主 Agent 已裁定初轮 004 问题属于原 04 授权内的普通实现修正。上述初轮“等待批准”叙述仅作历史保留，不代表当前阻塞或新增需求。

- 原 001–004 文件及已登记校验和保留。新增 `migrations/005_approval_subject_constraint.sql`，在真实测试库通过临时表事务回滚验证，再核对两库身份/版本/校验和及测试库已有审批主体无不合格记录。开发库实际应用 004、005，测试库实际应用 005；两库业务 schema 为 1–5，`EXPECTED_SCHEMA_VERSION=5`。
- `tests/test_approval_constraints.py` 在专用测试库使用本次唯一 session/order/application，实际对 `approvals` 表验证缺键、JSON null、数字、布尔、数组、对象、空字符串和不相等主体均拒绝，非空同值字符串接受；所有业务数据随事务回滚。该测试与下述准备事务测试合计 2 passed。
- `scripts/seed_orders.py`、`scripts/verify_03_real.py` 和 `tests/test_order_postgres.py` 的 schema 检查由固定版本 3 改为当前集中版本；本轮未执行会更改既有种子状态的 `test_order_postgres.py` 真实库用例。
- 新增尚未接入应用的 `app/domain/refunds.py`，实现申请准备的业务身份/原调用摘要核对、本人订单锁、持久 Session/thread 校验及幂等 PENDING 登记，准备过程不退款。`tests/test_refund_preparation.py` 使用专用测试库唯一订单、用户、会话和申请，验证金额来自源订单、同原调用重入、跨用户拒绝及订单退款标记不变；结束精确删除自身行。退款执行、审批和并发/恢复闭环尚未实现，该代码不可视作完整 4.2.1。
- 在测试库使用应用实际 lifespan 检查模型资源、独立业务池和 Saver 池均就绪，退出后两池关闭；未调用真实模型。默认全量 `pytest -q`：134 passed、5 skipped，跳过项包括未显式启用的真实数据库用例；此前显式真实库定向约束、会话/迁移测试通过。本轮修改 Python 文件的 ruff check 和 format 检查通过。

当前仍未交付 04：退款执行事务/审批存取、原调用治理接线、Runtime 四类恢复与 repair-binding、Refund 中断子图，以及真实模型、完全退出重启和故障窗口验收均未实现或未验证。第 15 节 24 项门禁不能视为已通过。本记录不启动 05，不代表独立 QA 或用户验收。

## 第三轮执行记录（2026-11-12，继续实施中）

主 Agent 确认原 04 授权持续有效。本轮在已有 005/Saver 基础上继续实现，未提交或推送，也未进入 05。

- `app/domain/refunds.py` 增加 `check_eligibility`、`prepare_application`、`execute_original`、`get_operation`、`reject_application`。准备申请先核对已有同一原申请，已成功原 operation 可重放复用；执行按订单→申请→审批锁序，再核对可信主体、Session/thread、原调用摘要、审批主体及锁后数据库时间，并在同一事务更新模拟订单和申请。结果核对等待订单锁以避免将并发中的操作误认未执行。此服务尚未接入正式 Refund Graph/Executor，不能单凭领域测试将 Task 4.2.1 判为整体完成。
- `app/workflows/approvals.py` 增加本地审计 Actor/Provider、审批主体登记、绑定 CAS、决定/幂等重交、查询及已批准主体校验。`app/api/routes/approvals.py` 增加八字段只读视图和决定接口；`app/main.py` 仅在 development/test 注册该 Router 和本地 Actor，并限制为回环连接。production 不注册。审批决定不自动 resume。当前 Runtime 还没有恢复判定，因此 `can_resume` 暂时为 false，不能将 4.2.2 接口整体标记完成；后续必须用真实快照与 Runtime 状态计算，不能维持此临时值。
- `app/tools/implementations/refunds.py` 添加退款工具及 node-only 工具定义/薄适配；因可信审批 Policy/Executor 路径尚未实现，这些定义**没有注册到应用**，不会作为已完成能力暴露。ToolPolicy、尝试标记与 Runtime 恢复仍需接线和完整验证。
- 真实测试库执行 `tests/test_refund_preparation.py` 和 `tests/test_refund_transactions.py`：使用本轮唯一用户/订单/会话/申请/审批并精确清理；验证原申请幂等、跨用户拒绝、未支付/批准后资格变化、拒绝、PENDING 惰性过期、APPROVED 过期保持决定、同决定幂等、相反决定竞争、同/不同 operation 并发、已成功操作过期后只读复用、查询等待事务锁，以及订单更新后注入故障时事务回滚。锁等待期间过期的测试确认决定和退款执行须在取得行锁后重新读取数据库时间。绑定所用 interrupt 值为受控测试值，不是完整 Graph 中断验收。
- 显式测试库调用 `pytest -q tests/test_refund_preparation.py tests/test_refund_transactions.py tests/test_approval_routes.py tests/test_refund_tools.py`：5 passed；后两项分别为受控 Router 和工具定义测试，不冒充真实模型或真实中断。`pytest -q tests/test_resources.py tests/test_application.py tests/test_approval_routes.py tests/test_refund_tools.py` 在追加适配器错误分类测试之前为 13 passed。相关文件 ruff check 通过。完整真实库阶段回归尚未执行。

后续必须继续：统一 Policy/Executor 的可信审批复检、节点工具来源限制和两步 attempt；Runtime 四类 resume/repair-binding、动态 `can_resume`、当前上下文及保守预算；Refund 七节设计的中断和安全重入图、SSE 事件；完全退出 Python 重启、SQL 成功而 checkpoint 失败的零重复写、真实模型及 D04 24 项完整门禁。4.2.1、4.2.2 仍有上述接线/综合验收，4.1.2、4.3.1、4.3.2 未完成；本轮不是 04 完成交付或独立 QA。

## 第四轮执行记录（2026-11-12，继续实施中）

本轮实现统一工具治理的部分接线，并保持 Refund 工具未注册到应用；没有启动独立 QA、付费模型、05 或 Git 操作。

- `app/tools/policy.py` 增加 Refund 固定 node/Task/工具白名单；模型来源只允许原生 `refund_order`，普通 Agent/scope/Schema/目标/预算检查仍先执行。持久审批核验结果必须匹配主体、调用、规范参数、申请、operation、thread 和摘要，才允许高风险原调用。
- `app/tools/models.py` 与 `app/tools/executor.py` 增加 `PreparedToolAttempt`、可信退款业务上下文及中断绑定、`assess`、`prepare_attempt`、`execute_prepared`。准备零 Handler 尝试；执行前重新读取审批并复核 Policy，使用已验证参数快照恢复类型，更新累计尝试次数，原标记同 Run 不能重复消费。node 来源仅将必要业务关联投影给 Handler，不携带预算或策略对象。退款仍未注册进应用。跨节点的 `execution_context`/`business_context` 可选路径目前明确拒绝，D05 对应配对尚未实现；不可宣称完整跨阶段 Executor 契约已交付。
- `app/runtime/context.py` 增加运行时 `execution_mode` 与 `RefundRecoveryContext`；`app/graph/nodes/specialist.py` 在 Refund 恢复模式传递当前 context、以已有子图 `None` 输入重入，并按当前 Run 映射结果。新增受控 wrapper 测试只验证该边界，不代表 Runtime 已实现真实恢复或已由真实 Refund Graph 验收。
- 专用 PostgreSQL 测试库中的 `tests/test_refund_transactions.py` 通过真实 ApprovalService、Policy、Executor、原退款工具和真实事务竞争同一订单；检查审批过期/权限不足在 Handler 前零尝试、成功和业务拒绝各实际计次一次，原 operation 重放复用；该测试使用唯一数据并清理。绑定使用受控测试引用，不是真实 Graph interrupt。`tests/test_refund_executor.py` 另以受控审批替身检查策略拒绝、批准复检、原标记不可重复执行及固定 node 来源，替身不作为真实审批验收。
- 在确认专用测试库身份后执行 `pytest -q tests/test_refund_executor.py tests/test_refund_transactions.py tests/test_tool_governance.py tests/test_order_graph.py tests/test_graph_protocol.py tests/test_runtime.py`：75 passed。相关变更文件 ruff check/format 通过。LangGraph 当前安装的 JsonPlusSerializer 可往返尝试标记和原调用；当前库对项目自定义类型有既有反序列化 allowlist 提醒，尚未以持久业务图跨进程完整恢复验收。

仍未完成：正式应用退款工具注册与完整任务/Policy 集成、原 Runtime 的四类 resume/repair-binding/动态 `can_resume` 和保守预算、Refund 完整中断/安全重入图与 SSE、真实 Python 完全退出重启、SQL 成功但 checkpoint 失败窗口的零重复写、真实模型及 D04 24 项矩阵。当前不应将 04 或全部 4.1.2/4.3.1/4.3.2 标为完成；下一轮继续原授权范围。

## 第五轮执行记录（2026-11-12，继续实施中）

- 核实已安装 `JsonPlusSerializer` 的 `allowed_msgpack_modules` 和 `AsyncPostgresSaver(..., serde=...)` 签名。`app/infrastructure/checkpoint.py` 增加项目实际 State/消息/尝试标记所需的明确类型白名单，`app/main.py` 将其用于正式 PG Saver；`tests/test_checkpoint_serializer.py` 验证必要类型往返和未知类型不被构造。未升级依赖或启用 pickle。
- 显式运行 `python -m scripts.probe_04_cross_process`：第一个 Python 进程使用真实专用 PG 保存嵌套中断并完全退出；第二进程以相同严格白名单重建图，恢复 `ExecutionContext`、`PreparedToolAttempt`、`ParsedToolCall`、真实 child namespace/interrupt ID，并通过根 Command 恢复。输出 `PROCESS_ONE_INTERRUPT_SAVED`、`PROCESS_TWO_STRICT_TYPES_AND_RESUME_OK`；独立清理进程删除本次唯一 thread 并检查三张 Saver 数据表无残留，输出 `PROBE_THREAD_CLEANED`。这是受控测试图，**不是退款业务端到端重启验收**。另用真实 Saver 和已编译 Supervisor 图验证严格序列化下同 Task 澄清续接与累计模型次数；该唯一 thread 已清理。
- `app/domain/refunds.py` 修正原 operation 成功后的重放核对：在复用结果前仍锁定和核对原审批记录、固定主体及绑定；批准过期不改变已提交的模拟退款事实。真实 PG 测试覆盖成功后原审批过期可复用，而错误或缺失审批引用被拒绝。仅按 user/operation 读取的 `get_operation` 仍沿 D04 只读核对接口执行。
- `pytest -q tests/test_resources.py tests/test_graph_protocol.py`：44 passed；`pytest -q tests/test_checkpoint_serializer.py`：1 passed。显式专用测试库执行 `tests/test_refund_transactions.py tests/test_refund_executor.py tests/test_approval_routes.py tests/test_resources.py`：8 passed。目标文件 ruff check 和 format 通过；再次核验测试库身份及 001–005 已登记 checksum 均匹配。

本轮 **未完成 4.1.2、4.3.1 或 4.3.2**：原 Runtime 四类 resume/repair-binding/动态 `can_resume`、正式 Refund Graph/Registry/SSE 接线、退款 SQL 成功而结果 checkpoint 失败的真实重启与零重复写、真实模型和 24 项矩阵仍待实现或验证。当前控制面 `can_resume` 仍为临时 false，退款工具仍未注册。不得将受控图跨进程探针描述成完整退款恢复，也不得将此记录视为阶段交付或独立 QA。

## 第六轮执行记录（2026-11-12，继续实施中）

- 新增 `app/runtime/refund_checkpoint.py`，对父/子快照、可信申请主体、原生 AIMessage/ToolCall、规范参数、thread/namespace、真实 interrupt 和安全后段节点进行保守核验；不匹配、额外活动节点、未知形态均归为 unknown。`AgentRuntime._inspect_refund_checkpoint` 使用 `aget_state(..., subgraphs=True)`，并支持框架返回子配置时继续读取子快照。当前分类依赖未来 RefundState 与测试契约一致，尚未通过正式退款子图验证。
- 原 `AgentRuntime` 增加 `repair_approval_binding`：使用同一 thread 门禁，锁内重读审批/申请及最新嵌套快照，仅针对唯一真实 pending interrupt 补绑；已有一致绑定幂等返回，不新建 Run、不运行 Graph。`app/api/routes/approvals.py` 接入严格空对象的本地 `repair-binding`，客户端不可传 interrupt/namespace。`tests/test_refund_checkpoint.py` 使用受控快照与审批替身验证补绑、重复、忙碌、主体/调用/namespace/interrupt 错误和安全后段分类；**不是正式退款图的真实 PG 补绑验收**。
- `ApprovalService.prepare_resume` 增加锁后数据库时间、原绑定及主体再检：有效 PENDING 不可推进，过期 PENDING 在事务内转 EXPIRED，已有决定保持。已为真实 PG 场景补充测试，但本轮测试库连接在建池时超时，测试失败发生在建池、尚未插入业务数据；之后安全探针显示 TCP 可达但数据库连接超时。故该新增事务的真实库验证**未通过/未完成**，不得以受控替身当作验收。
- `app/streaming/events.py` 增加 `workflow_paused` 和 `workflow_resumed` 安全字段白名单；受控测试确认不会发布原参数和 checkpoint namespace。Runtime 尚未在真实暂停/恢复点发布事件。
- 针对本轮真实连接失败发现的建池阶段后台日志边界，`app/infrastructure/postgres.py` 和 `checkpoint.py` 在打开池前安装安全过滤器；新增定向测试。失败时 pytest 捕获过驱动连接失败原始诊断，未包含密码或完整连接 URL；过滤修复后不应再输出驱动原文。
- `pytest -q tests/test_refund_checkpoint.py tests/test_approval_routes.py tests/test_runtime.py tests/test_graph_protocol.py tests/test_tool_governance.py tests/test_application.py tests/test_resources.py`：86 passed；随后新增的安全过滤器定向 `tests/test_resources.py`：5 passed。相关代码 ruff check/format 通过。上述测试为受控回归，不代表真实数据库恢复验收。

仍未完成：`AgentRuntime.resume_approval` 的四类受理与实际执行、动态 `can_resume`、真实等待绑定及 SSE 发布、正式 Refund Graph 和工具注册、保守预算结算、完整进程退出重启的退款恢复、SQL 成功/Checkpoint 失败零重复写、真实模型及 24 项门禁。当前 `can_resume` 仍为 false，退款图仍是不可用骨架。04 不应标为完成；测试库连接恢复后需按唯一数据和精确清理规则重跑新增真实 PG 场景。

## 第七轮执行记录（2026-11-12，继续实施中）

- 在现有 `AgentRuntime` 中增加 `resume_approval` 的受控入口：使用原 thread 门禁和审批/申请重读，区分当前真实 pending、允许的 Gate 后节点、已结束结果及 unknown；pending 仅用真实 interrupt ID 构造根 `Command(resume=...)`，后段使用当前 `RefundRecoveryContext` 和根 `None` 续跑，已结束不创建新 Run。恢复记录继承 child 用量，对已保存的可能执行标记保守补计工具次数和单次时间并标记 `usage_complete=false`，缺少可证明的执行标记/不匹配主体时拒绝。相同 Task 的活动恢复返回现有 Run，不创建第二个执行。
- Runtime 在 Graph 返回真实中断时读取并核验实际子快照、完成绑定后发布 `workflow_paused`、waiting 状态和 done；恢复受理后发布 `workflow_resumed`。失败走不确定状态，不从图外写伪造结果。`can_resume_approval` 按当前绑定、快照、决定、线程占用、操作和预算进行只读判断，管理 Router 增加显式 `resume` 入口及动态视图。**当前生产装配尚未注入退款服务和 scope resolver，正式 Refund Graph 仍为骨架，因此这些恢复入口在当前应用中不可用，视图仍不会返回可恢复**；不得称应用闭环已完成。
- 受控测试覆盖 pending Command、新 Run 关联、已成功后段携带可信事实、缺少证明的未知结果拒绝、持久标记保守计数、已结束不新建 Run、并发重复恢复不新建第二任务，以及绑定完成后才发布暂停事件。所用 Graph、审批与操作结果为替身，没有证明真实 SQL/Checkpoint 副作用窗口。
- `ApprovalService.decide/prepare_resume` 将数据库时间读取放到锁定、主体和绑定检查之后再执行；用户要求的真实库并发/到期验证本轮仍受测试库连接超时阻塞。只做一次脱敏身份探针，结果为 `ConnectionTimeout`，未重建或修改资源。
- `pytest -q tests/test_refund_checkpoint.py tests/test_runtime.py tests/test_approval_routes.py tests/test_graph_protocol.py tests/test_tool_governance.py tests/test_application.py`：83 passed；随后新增重复恢复测试，`pytest -q tests/test_refund_checkpoint.py`：10 passed。受影响文件 ruff check/format 通过。测试均为受控替身，不替代 PG、完整进程重启或真实模型门禁。

剩余关键工作：正式 RefundState/完整节点及同一 Registry/Policy/Executor 的应用注册；主 Runtime/服务依赖与 scope resolver 的正式装配；真实 pause/repair/resume 和四类状态联调；严格确认后段 PENDING 的未执行证据、原节点 guard 和新标记同步；真实 PostgreSQL 事务/进程重启、提交后 Checkpoint 失败零重复写、真实模型及 D04 24 项矩阵。04 尚未完成，不可开始独立阶段 QA 或 05。

## 第八轮执行记录（2026-11-12，继续实施中）

本记录描述本轮实际实现与受控验证，前述各轮保留历史语境。04 仍为 IN_PROGRESS，不代表独立 QA 或阶段验收。

- `app/graph/specialists/refund/builder.py` 将退款骨架替换为编译的 RefundState 子图：订单/资格检查、原生单工具调用、申请与审批登记、同步等待和真实 interrupt Gate、决定后资格复检、当前 Run 写尝试标记、执行及只读核对、原 call 的 ToolMessage、固定事实结果和父图映射。退款及 node-only 业务工具使用已有 Registry/Policy/Executor；原模型调用、Task 和 operation 关联保留。安全后段消费当前恢复上下文，核对已成功事实；确认未执行路径复检资格并建立当前 Run 的新尝试标记；结果无法判定时保留核对节点并使 Runtime 进入不确定状态。
- `app/main.py` 将真实退款领域服务、审批服务、四个 node-only 工具及 `refund_order` 注册到唯一冻结 Registry 和 Executor，向原 Runtime 注入退款服务及普通演示用户 scope resolver；production 仍不注册本地审批 Router/Actor。`app/infrastructure/checkpoint.py` 增加实际持久状态 `ToolExecutionResult` 的显式 Serializer 白名单及往返测试。
- `tests/test_refund_full_controlled.py` 使用真实编译的主图/退款子图、统一执行器、正式 AgentService/HTTP Router、InMemorySaver 和受控模型/订单/退款/审批替身，覆盖 HTTP SSE 暂停、决定与显式恢复；批准后原 operation 执行一次，拒绝零退款写；注入写结果不可用后核对成功复用事实，以及未知时停留核对节点、随后可核对成功并通过原调用恢复且不增加写尝试。检查 SSE 不暴露原工具调用或内部候选摘要。替身不证明真实 PG 事务、持久化、完全退出重启或真实模型行为。
- 原 02/03 受控测试需要构造未关联退款的骨架；`tests/refund_skeleton.py` 保留仅测试用的旧骨架，`tests/runtime_support.py`、`tests/test_graph_protocol.py`、`tests/test_order_graph.py` 的旧隔离夹具改为显式引用该测试替身，正式应用不使用它。`README.md` 补充当前 04 实施及验证状态。
- 默认全量 ` .\.venv\Scripts\python.exe -m pytest -q --tb=short`：156 passed、6 skipped（在最后增加同一未知结果受控用例的后续恢复断言之前执行）；随后 ` .\.venv\Scripts\python.exe -m pytest tests/test_refund_full_controlled.py -q --tb=short`：4 passed，包含新增断言。受影响文件的 `ruff check` 和 `ruff format --check` 通过（最终受控测试添加断言后尚须复核格式）。
- 按授权仅对测试目标做一次脱敏连接探针，结果 `TEST_DATABASE_CONNECTION_FAILED`；没有使用 Mock 替代真实资源验收，没有重建资源、更改密码、写入或清理数据库，也没有调用真实模型。

本轮不能宣称 4.3.1 已完整验收：真实 PostgreSQL Serializer/审批/原调用及完整故障路径、真实多进程退出与重启、SQL 提交而 checkpoint 失败且 next=execute_refund 的零重复写、全部白名单位置与未执行复检、预算耗尽/过期等综合门禁、真实模型和 D04 第 15 节 24 项整体矩阵仍需实际运行并记录。4.1.2 的真实环境四类恢复及 repair-binding、4.3.2 故障和阶段验收同样未完成；不可进入 05。真实库恢复后必须继续使用原授权专用库、唯一测试数据与精确清理，不能用本轮受控结果代替真实证据。
- 最终新增恢复断言后，`ruff check tests/test_refund_full_controlled.py` 与 `ruff format --check tests/test_refund_full_controlled.py` 再次通过。
