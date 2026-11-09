# 03 Supervisor 主图与执行治理——详细架构设计

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**架构审核通过，补充修订供最终复核；待开发执行，未实现、未验收**。本版保留五个二级环节和全部三级任务编号，纳入最终审核要求。

整理日期：2026-11-08。配套：[完整开发执行计划](03-stage-execution-plan.md)、[02 数据设计](02-stage-detailed-design.md)、[01 正式协议](01-stage-detailed-design.md)、[整体路线图](../development-roadmap.md)。本轮只输出文档，不修改业务代码、不运行模型/数据库/业务测试。

## 1. 当前事实和依赖分层

现有 supervisor.py 已有 Prompt、结构化 RouteDecision、PendingTask 读取及实体合并，但通用澄清被固定 TaskType、只使用用户历史、无任务控制和预算。builder.py 已有固定主图和三个未就绪目标，内部硬编码 InMemorySaver。specialist.py 已有显式输入/结果映射。Runtime 在 HTTP 生成器中 await 整个 Graph，Service 只创建 Context/run，Route 直接订阅该生成器。公共事件仍为旧 event/data。

01 已批准但未完成代码：State 收敛、公共版本信封、终态矩阵。02 已批准并修订但未完成代码：Principal、SessionBinding、迁移/池、事务仓储、幂等、状态和查询。现有测试以契约和简化图为主，不能证明本稿能力。

可先独立开发：Supervisor 纯决定、主图装配、测试 Stub、预算算法和 Broker。必须等待 01/02 实际验收：身份/受理集成、持久任务、数据库快照、启动核对、HTTP 全链路。Mock 仓储通过不是集成完成。

## 2. 总体结构与接口

Route → AgentService → 可信上下文/WorkflowManager 事务受理 → ExecutionManager 独立任务 → AgentRuntime → 基础 Checkpointer/主图/Budget → 持久结果 → PublicEventProjector → StreamBroker → SSE。状态查询直接读取授权元数据与公开结果。

| 组件/建议文件 | 职责 |
| --- | --- |
| api/routes/agent.py | 请求、身份依赖、HTTP 类型与订阅清理，不启动 Graph |
| services/agent_service.py | 可信会话、幂等受理和首订阅协调，不拥有业务协程 |
| execution/models.py | 命令、任务和执行结果契约 |
| execution/manager.py | 单进程任务持有、领取、调度、启动核对与关闭 |
| runtime/agent_runtime.py | 一次 Graph 执行、上下文/State 装配和结果分类 |
| execution/budget.py | 持久累计预算、预留、结算与期限 |
| execution/broker.py | 有界独立订阅，不拥有执行任务 |
| streaming/projector.py | 内部结果到 01 公共协议的白名单投影 |
| infrastructure/checkpoint.py | 基础持久快照资源，应用生命周期管理 |

这些是模块职责，不要求再建立通用基类、动态插件或消息队列。

关键接口：AgentService.submit_chat → AdmissionResult；ExecutionManager.start/notify/shutdown；AgentRuntime.execute(context,command) → ExecutionOutcome；Broker.subscribe/publish/unsubscribe/close_run。WorkflowManager 管事务，Repository 只在传入连接上操作。

### 2.1 V1 部署拓扑（强制）

一个应用实例、一个 Uvicorn Worker、一个执行器进程；HTTP、ExecutionManager、StreamBroker 在同一应用进程，asyncio 任务不是独立子进程。生产不得使用多 worker；reload 仅开发期且按退出/启动核对处理，不能作为无缝恢复部署。多个会话可以在本进程受限并发，不等于多个执行器。

数据库实例锁只防止重复执行器，不提供跨进程 Broker。未来多 worker/多实例必须先设计跨进程事件分发、订阅路由、执行权和全局并发，不能只增加 workers 或以黏性会话代替；03 不实现该扩展。

## 3. 3.1 Supervisor 与澄清生命周期

### 3.1.1 架构与决定

保留 RouteDecision，增加内部 SupervisorDecision：action=dispatch|clarify|switch|abandon，route 可空。前三者必须有符合归属的 route；abandon 不携带执行路由。模型只提出建议，程序按可信状态校验允许动作。

流程：可信任务上下文 → 有限公共历史 → 受预算模型调用 → 结构校验 → 动作/任务关系校验 → State 增量或任务控制结果。上下文仅提供必要 task/goal/entities/missing，不反复把完整身份记录加入 Prompt。包含必要公开 AI 回复；不含工具、系统历史和内部推理。历史窗口和输入 Token 受限。

组件：上下文组装、结构化模型适配、纯决定校验、纯增量映射；Runtime 接收任务控制结果并持久收敛，Supervisor 不写库、不做订单/退款业务。

### 3.1.2 澄清与任务控制

| 情况 | 处理 |
| --- | --- |
| 未知意图 | 通用澄清，正常结束本 run |
| 通用澄清后明确业务 | 允许确定目标/Task，保留当前意图 task_id |
| 业务缺字段 | 保留 Task/goal/task_id，合并候选实体 |
| 仍不足 | 更新问题，保留原目标 |
| 明确放弃 | 输出 abandon，由 Runtime 安全结束目标 |
| 明确切换 | 仅可信允许的待补状态；新 task_id，清理旧结果和候选，预算不重置 |
| 审批/暂停/核对 | 普通请求受理前拒绝，不交模型决定 resume |
| 模型擅改目标 | 拒绝候选，不静默执行 |

切换未执行目标可保留逻辑 workflow，但原任务必须没有未解决副作用/审批关联。允许范围来自可信生命周期，不由模型自报；未来副作用存在时不能通过聊天清约束。

结构错误最多一次纠正重试，每次尝试计预算；重试输入不携带原始敏感异常。仍非法则安全失败。SDK 重试关闭或纳入同一机制，不能双重重试。

### 3.1.3 三级任务

| 任务 | 具体步骤、文件 | 依赖与验收 |
| --- | --- | --- |
| 3.1.1 决定与上下文 | contracts.py 加 action 组合；Prompt 与公开上下文筛选 | 01 契约；身份/任意节点不可注入 |
| 3.1.2 澄清续接 | Supervisor/转换函数区分两类 pending，合并实体 | 上项；实际节点两轮续接正确 |
| 3.1.3 切换与放弃 | 纯动作校验、task 更新、控制结果 | 上项；受限状态拒绝，旧目标不残留 |
| 3.1.4 模型失败治理 | 可注入调用入口、有界纠正 | 模型适配契约；非法不进入专业图 |
| 3.1.5 集成验收 | 实际节点+可控模型，随后真实模型 | 前四项及 3.4 接线；重试、计量和目标保护通过 |

## 4. 3.2 主图公共节点与专业接入边界

### 4.1 拓扑和职责

START→Supervisor；clarify→Clarification→Response；abandon→控制结果→Response；dispatch/switch→固定专业 wrapper；needs_input→Clarification，其余可展示结果→Aggregator→Response→END。专业失败交 Runtime。无循环 Supervisor 协调或并行多 Agent。

builder 接受 model_call、specialist_graphs、checkpointer；资源由启动阶段创建，图编译一次。节点内不建池、模型或新 thread。专业配置传播按本地安装版本做实际验证，不凭隐式上下文假设恢复可用。

公共节点轻量包装仅做预算/安全点检查和日志，不统一吞异常、自动重试节点或深拷贝 State。wrapper 沿用现有四个显式映射接口，不复制整个子图。Clarification/Aggregator 确定公开文本，Response 是唯一公开 AI 消息写入点。图内不生成公共 done。

未注入专业能力明确不可用。Stub 只放测试或明确验收装配；各专业路径提供契约合法、标明测试的结果/来源，可以注入 needs_input/rejected/failed/安全中断。生产默认不可装入 Stub，不计业务完成。

### 4.2 三级任务

| 任务 | 步骤与文件 | 完成标准 |
| --- | --- | --- |
| 3.2.1 依赖注入 | builder 移出固定 Saver，注入模型入口和专业图 | 一次编译，未知专业名称拒绝 |
| 3.2.2 公共/控制出口 | router、nodes 增控制与唯一回复出口 | 正常公开文本只走 Response |
| 3.2.3 专业契约 | wrapper/config 传播及关联校验 | 错结果拒绝，私有历史隔离 |
| 3.2.4 Stub 路径 | 测试目录可控子图 | 有限路由、补输入、拒绝/失败可复核 |
| 3.2.5 实际装配验收 | 调用实际 builder，不重手写等价图 | 缺能力安全失败，生产配置不误装 Stub |

依赖 3.1 契约，Stub 可先并行准备；最终装配串行。

## 5. 3.3 Runtime 与独立执行生命周期

### 5.1 数据、调用与原子受理

ExecutionTask 与 run 一一对应：run_id、state(queued/claimed/finished/reconciling)、input_payload、payload_schema_version、owner_instance_id、executor_epoch、claim_token、创建/领取/结束时间和 payload 清理时间。任务状态表示调度，不代替 Run/Workflow。input 只存可重建命令和关联，不存令牌/连接/客户端。

排队授权须有有效性约束和重新核验入口。执行前核对当前调用方允许范围、授权有效期和资源归属；过期不凭旧载荷恢复权限。具体授权有效期须与 2.2 接线确认。

#### ExecutionTask.input_payload 存储契约

- 使用版本化、有界 Schema，payload_schema_version=1；字段为命令类别、必要用户消息、会话/workflow/task 关联和授权引用。表中已有字段可引用，不重复复制整份身份、State、历史、Prompt、工具结果或 Checkpoint。消息长度遵循 01，JSON 总尺寸设有配置上限。
- 可信 user_id/client_id 从 Principal 写入表，不从 payload 反推权限；不保存 Bearer、API Key、Cookie、连接串或模型客户端。只存授权标识、签发/失效时间、范围快照及来源版本，快照仅供核对，不是恢复授权。
- 消息可能含个人信息，按敏感数据保护：传输保护、最小数据库权限、存储/备份加密、日志仅关联 ID 和安全码，不打印 payload。任意自由文本不能宣称已经靠关键词过滤完成脱敏。
- V1 建议终结且无需核对的任务 payload 保留 7 天后清除；queued/claimed/reconciling/等待审批或暂停的数据不按终结 TTL 清除。长期未解决项进入人工核对清单，不无限无声保留。实际期限可配置，清理需保留任务元数据、幂等摘要及依法允许的最小结果。
- 清理任务由应用内有界维护步骤执行，清理不触发执行、改状态或删除幂等键；Checkpoint 和公开结果的保留分别管理，不能把 payload TTL 当全局删除。
- 未知 Schema 版本、超限/损坏、过期/撤销授权均禁止执行，记录安全失败或核对原因；不猜测转换。调用前按当前配置重新确认调用方仍有效、权限不扩张、会话和资源归属；无法核验动态用户权限时拒绝，不能沿用旧快照兜底。V1 排队授权有效期默认建议 5 分钟且可配置，既有有效期更短时取较早值。

单事务：校验身份、活动槽位及幂等 → 写 workflow/run、current_run/version → 写任务输入 → 关联预算 → 提交。提交后 notify 只是加速，queued 扫描保证通知丢失不丢任务。通知失败不能撤销已受理事实。

领取：原子 claim/token → thread 锁 → 核对 current_run/授权/预算 → 读取快照 → 初始化本轮 State → Graph → 持久收敛 → 公开终态 → 释放。运行更新同时校验当前 run、owner/token、version，旧任务不能覆盖新状态。

首版仅单执行器进程。采用数据库持有的实例互斥防重复实例领取；丢失实例锁连接即停止受理/推进并隔离不确定任务。该约束不是未来外部副作用 fencing 或业务幂等的替代。

#### 实例执行权、原子领取与迟到拒绝

1. 启动生成随机 owner_instance_id（每次启动新 UUID），使用专用、非连接池借用的 PostgreSQL 会话获取 pg_try_advisory_lock(:executor_lock_key)。key 为该应用/数据库命名空间固定配置的 bigint，禁止用进程随机 hash。连接使用自动提交，锁持有整个执行器生命周期；失败则实例不开放业务和领取，不悄悄成为第二个 HTTP/Broker 实例。
2. 03 迁移增加单行 executor_guard：固定 key、owner_instance_id、单调递增 epoch。取得 advisory lock 后，以排他行锁更新 owner/epoch，完成启动核对后才启用受理。正常查询此专用会话存活；不能自动重连后假定仍持锁。同 owner 不热恢复执行权，失权后关闭实例，重新启动用新 owner/epoch。
3. 领取使用一条事务内 SELECT ... FOR UPDATE SKIP LOCKED 的候选查询，或等效条件 UPDATE：只选 queued 且对应 run=queued、workflow.current_run_id 匹配的任务；UPDATE 为 claimed，写 owner、epoch、新随机 claim_token 和领取时间并 RETURNING。run 到 running 的转换在同一事务核验并更新；workflow.running 仅代表已受理。全局并发名额取得后才领取，避免大量 claimed 等待。
4. owner 标识实例，claim_token 标识这一次领取，epoch 标识当前执行权。token 不是凭据，内部不公开。任务结果、预算写入、run/workflow 更新必须在同一短事务锁定 guard 共享行、核对 owner/epoch，再核对任务 owner/epoch/token、current_run/version。零行更新表示失权/陈旧，不重试成无条件写。
5. Checkpointer 写入也经过执行权门禁：在保存快照/待写入数据前取得 guard 共享行锁，确认 owner/epoch，并覆盖该次 Saver 写入完成；接管更新 epoch 需要排他行锁，故旧写入只能在接管前结束，接管后旧 owner 不能开始新写。该门禁封装在 checkpoint 资源适配器，不假定原生 Saver 自带 fencing。锁作用域仅覆盖数据库写，不跨模型或网络业务调用；所需连接独立配置，避免单连接池自锁。
6. 专用锁连接断开或检查失败时，立即设置 lost_authority：关闭受理、停止领取/模型/工具下一调用和公开成功发布，取消本地任务并等待有界收敛。不能保证冻结正在等待的外部请求；不明确其结果，不宣称取消成功。数据库不可达时不能假装已标 reconciling，由下一合法实例核对；旧实例恢复网络后仍因 epoch/token 拒绝写入。
7. 新实例取得锁并更新 epoch 后，扫描 owner/epoch 不属于当前实例的 claimed 或 run.running 记录，以条件事务将 task/run/workflow 标 reconciling，保留旧领取审计信息并撤销推进权。queued 未领取任务保留后续调度；已有终态不覆盖。不能只因时间久、HTTP 断开或心跳延迟就接管正在工作的任务。

advisory 会话锁和 guard 的职责不同：前者唯一合法执行器，后者串行化权力切换与旧写入。该最小数据库门禁用于本 V1，不是分布式调度系统；外部副作用仍依赖 4.3/业务幂等和 6.1 核对。

### 5.2 受理和 thread 约束

数据库活动约束与运行锁分开。按持久 thread 管理进程锁，新轮次、续接、控制、重试和未来恢复统一入口；锁内不长期持数据库事务。无持有者/等待者时清理锁条目。不同会话可并发，受全局执行并发限制。

waiting_input/approval、paused、reconciling 均占会话槽位。普通聊天不能替代审批恢复。新目标/续接命令必须明确，不能因未知 workflow ID 自动创建。02 的最终 ID 与请求提议区别在接线前确定（见第 9 节），不能隐式改 01 必填字段。

#### Runtime 跨 Run State 初始化（3.3.4）

增加纯函数 prepare_run_input(context, binding, snapshot_values, transition, new_task_id) → State 增量。context/binding/transition 由服务和仓储提供；transition 区分 new_workflow、new_task、clarification，不取模型自报值；task ID 由调用方生成以保持纯函数可测。函数不查库、不生成 ID、不写 Checkpoint、不修改传入快照。Runtime 另行构造 configurable.thread_id，thread 不成为模型可写 State 字段。

调用前在 thread 锁内核对 snapshot 的用户/会话与绑定、metadata 的前序 run 和快照所属 run；快照 next/interrupt 表示未完成时不得作为普通新轮次继续。快照与持久元数据不一致进入核对，不静默舍弃。

| 场景 | 输入增量与保留规则 |
| --- | --- |
| 同 thread 新 Workflow | 仅在前序 workflow 已明确终结且无中断时允许；保留公共 messages，通过 Reducer 仅追加本次 HumanMessage；覆盖可信 workflow/run；新 task；pending、route、specialist_result、final_answer、sources 及任务镜像清空 |
| 同 Workflow 新目标 | 经可信切换授权后新 task；不继承旧候选实体/私有子图状态，保留公共历史及 workflow 预算，run 使用当前值 |
| 同 Workflow 澄清新 Run | 从快照取合法 PendingTask，核验用户/会话/workflow；保留 task/目标/候选，使用新 run；清空旧决定、结果、答案和来源；不得重置预算 |
| 审批/暂停/核对 | 03 普通输入拒绝，不调用 create_turn_state 假 resume；6.1 以后单独实现恢复准备，刷新当前 run 且保留私有操作、审批、预算与记录 |

可信 user/conversation/workflow/run 始终由当前上下文覆盖；不复制整个旧 State，不由 entities 覆盖身份。专业状态按每次调用初始化，不复用旧子图私有消息；保留父图公共历史但不重复提交整份历史。Response 消息 ID 使用当前 run，不能将旧 assistant 结果当本次输出。

测试至少包含：同 thread 顺序两个 workflow 无串参；合法澄清 task 保留且 run 更新；旧来源/答案清零；历史恰好追加；快照跨用户/会话、PendingTask 错 workflow、前序 run 不匹配、中断未处理均拒绝；输入快照未被原地修改。实际审批 resume 不计入 03 验收。

### 5.3 Checkpoint 与恢复等级

03 负责 PostgreSQL 基础 Checkpointer：生命周期管理、builder 注入、持久 thread、普通轮次/澄清的父图快照及执行权写入门禁。6.1 不重复基础接入，重点复杂 Interrupt、审批 resume、崩溃窗口核对和跨进程重启后的安全恢复；跨进程恢复不表示支持多个执行器同时运行。当前自行计算 thread 的逻辑由持久绑定替代，不对开发内存历史自动迁移。

| 03 能力 | 6.1/6.3 能力 |
| --- | --- |
| 普通快照和澄清续接 | 嵌套 interrupt 完整恢复 |
| 未领取 queued 重启调度原 run | 审批决定驱动新 run resume |
| 旧 running 崩溃识别与隔离 | 审批/快照提交窗口核对 |
| 安全中断识别并 paused | 外部副作用重放安全与恢复预算验收 |

03 不自动重放崩溃时运行的 Graph。启动：queued→调度；旧实例 claimed/running→任务、run、workflow reconciling；已结束不再执行；快照完成但元数据未提交→核对，不凭 final_answer 自动认定成功。

03 可识别真实受控图 interrupt 并持久暂停，但不提供审批 resume。Stub 验证中断识别，不提供生产伪审批。无真实审批记录不发 approval_required。实际恢复刷新时序留 6.1。

### 5.4 异常与关闭

优雅关闭：停止受理/领取→queued 保留→运行任务在期限内收敛→超时取消本地执行→不确定任务转 reconciling→关闭订阅、模型与数据库。取消协程不证明外部操作撤销，不无条件标 cancelled。

先持久结果再发布业务终态。保存失败时不发假成功，可输出 state_unconfirmed 安全错误、done(failed)，保留核对；流 failed 不证明业务未执行。数据库事务不跨 Graph、模型、Checkpoint 或业务 HTTP。

ExecutionOutcome 内部分 answered/needs_input/rejected/abandoned/paused/failed/state_unconfirmed，不直接序列化到 SSE。统一由结果收敛和投影处理。

### 5.5 三级任务

| 任务 | 实现步骤/模块 | 依赖与验收 |
| --- | --- | --- |
| 3.3.1 执行契约 | execution/models、Runtime Outcome、仓储接口 | 02 修订；状态与关联无歧义 |
| 3.3.2 原子持久任务 | 新迁移、Service、WorkflowManager 共享事务 | 02 实际验收；回滚无半受理，丢通知可扫描 |
| 3.3.3 独立管理 | manager 领取/并发/任务持有 | 上项；重复通知不重领，HTTP 退出不删任务 |
| 3.3.4 thread/快照 | Runtime、prepare_run_input、builder、checkpoint 权力门禁 | 主图和 02；新 workflow/续接不串 run，历史增量正确，同 thread 串行 |
| 3.3.5 故障/关闭 | 专用会话 advisory lock、guard epoch、claim、启动扫描和关闭 | 上项；失权即停，旧元数据/预算/快照写拒绝；queued 继续、running 核对 |
| 3.3.6 生命周期验收 | 真实数据库、实际图、可控模型/专业图 | 前五项；受理、状态、暂停、故障窗口完整 |

## 6. 3.4 执行预算与超时治理

当前无预算能力。累计预算属于 workflow；单次期限和调用超时属于 run/调用。澄清、新 run、重试、同 workflow 任务切换继承消费，新 workflow 才初始化；未来审批恢复不能赠送额度。

WorkflowBudget：limits、模型尝试数、工具尝试数、known_tokens、token_usage_unknown、已收费执行时长、version。另有调用预留记录，保留未结算状态；不能只在进程内计量。RunBudgetContext 保存本次起点和剩余期限，进程内用单调时钟，持久记录用时间戳和已收费时长。

接口：before_model_call/after_model_call、before_tool_call/after_tool_call、remaining_deadline。调用前原子检查/预留；每次实际尝试计数，包括纠正和安全重试。SDK 自动重试关闭或统一记账，Graph recursion_limit 只是额外保护。

### 6.1 统一 ModelCallGateway

增加 execution/model_gateway.py（或等效同职责实现）：invoke(call_context, model_request) → ModelCallResult。call_context 含可信 workflow/run、执行权、调用用途和期限，不由模型生成。请求可以指定允许的结构化 Schema；返回结构化结果及 UsageRecord。

固定调用链：核验执行权/预算→持久预留→应用超时/输出上限→调用绑定模型→记录精确/估算/未知用量→结算/保留未确认预留→返回。Supervisor 和以后每个 Specialist 的模型调用均注入 Gateway，不把原始模型客户端直接交给节点；Prompt/Schema 适配不能绕过入口。纠正和重试每次重新进入 Gateway，SDK 内部隐式重试关闭，避免无法计量。

工具统一 reserve_tool_call/settle_tool_call 接口返回 reservation_id，检查并预留次数/期限，结算实际结果及未知状态；03 用受控工具测试，真正 ToolExecutor 在 4.3 接入，不在 03 建业务工具或执行器。

### 6.2 Token 质量与限制语义

UsageRecord 区分 exact（供应商精确报告）、estimated（保守估算，记录方法/版本/余量）、unknown（无可信计量，值为空，不是零）。预留和实际观测分别保存，预算账户按不可低估风险的收费规则更新，不能把已预留和实际结算重复相加。

exact 可对已结算用量准确累计；estimated 只能承诺按估算阈值治理，不能称绝对 Token 硬上限。即使 exact，供应商计量返回前的单次调用也受预留误差影响，严格上限须有已验证的计量/输出约束。unknown 标记不确定且保留保守收费，不自动返还；无法建立足够安全的估算时停止后续调用。报告同时给 known/estimated/unknown，不混称精确总量。

限制包括模型次数、工具次数、Token、主动执行总时长、单模型/工具超时和重试次数。等待用户/审批不计主动执行时长，另有 workflow 有效期限。每次调用超时取自身上限与剩余期限较小值。默认数值作为待审核配置与真实联调参数，不声称未经验证的默认值已成立。

Token 优先供应商 usage，缺失按上述质量记录估算或未知，不能零计。超时/崩溃未结算预留不自动退还；Gateway 必须对结构化解析失败也记录已发生调用。预算耗尽先阻断后续副作用，已发生操作不能改写为未执行。

| 任务 | 步骤与文件 | 完成标准 |
| --- | --- | --- |
| 3.4.1 模型与持久记录 | budget.py、迁移、config | workflow 归属，跨 run 不重置 |
| 3.4.2 检查/预留/结算 | 原子计量、未知和未结算状态 | 并发不超发，未知不零计 |
| 3.4.3 模型治理 | ModelCallGateway、Supervisor/未来 Specialist 注入、超时/重试 | 无模型旁路；解析失败也结算；精确/估算/未知区分 |
| 3.4.4 工具治理接口 | 给 4.3 的预算入口，以受控工具测试 | 不提前实现 Executor，调用契约可用 |
| 3.4.5 跨 run/故障验收 | 数据库/超时/重启预留测试 | 续接重试不赠额度，未结算不自动返还 |

## 7. 3.5 SSE 订阅与公共事件适配

### 7.1 架构与生命周期

执行任务→Projector→Broker→独立有界订阅→SSE。不得直接转发 LangGraph 全量消息/事件。订阅只持有队列，不持有业务任务。

Broker.subscribe(run_id)、publish、close_run、unsubscribe。每订阅独立队列；publish 不等待慢客户端。溢出结束该订阅，提示状态查询，不修改业务状态或制造业务 done。断开 finally 只清理订阅。run 结束后清理无需保留的资源。

首次受理的订阅注册与调度由应用协调，避免正常首连接未注册即丢终态；可使用同一短期调度协调区，不能在数据库事务里等 SSE。受理后客户端取消也不删除任务，扫描入口仍负责推进。须测试注册/结束竞争。

### 7.2 重连、幂等与协议待决

首次新受理 HTTP 200、Content-Type: text/event-stream；幂等重复且相同命令 HTTP 200、Content-Type: application/json，返回 schema_version=1、disposition=existing、conversation_id、workflow_id、run_id、status_url 和 events_url（可空）；不含凭据/thread，不重新执行。相同 key 不同命令仍 409 JSON。此项随本轮协议补充明确，303 不采用，不能自动重定向。

OpenAPI 在同一 POST /agent/chat 的 responses.200.content 同时列 text/event-stream（01 完整信封流）和 application/json（ExistingRunResponse 模型），错误仍为 JSON；客户端按 Content-Type 分支，不因 200 就当作 SSE。Idempotency-Key 必填且进入文档；首次 200 不是业务成功。重连 GET 的 200 也说明 SSE/终态 JSON 两类，测试覆盖两种媒体类型。

首版无持久事件重放、不发 SSE id。重连先授权：活跃 run 可订阅后续，终态 run 查持久结果，不伪造原 Token 流。状态查询需有允许公开的最终文本与来源，否则断开后无法拿结果；终态事务保存最小公开投影，不存私有历史。

#### 先注册、后查持久状态的重连算法

1. 验证 Principal 对 run 的查询权，取得可信关联（这一步可读取归属，但不是决定是否结束的最终状态检查）。
2. 先在 Broker 注册订阅并缓冲后续事件，再从主库重新读取持久 run 状态/公开结果；不能先查 running 再订阅。
3. 若已终结或 reconciling，发响应头前注销临时订阅，返回 200 application/json 的状态/结果快照，明确 stream_available=false，不回放旧 token/error/done。即使队列刚收到终态，也不再另开 SSE。
4. 若仍 queued/running，返回 200 SSE 并消费已注册队列；注册到读取之间完成的事件已在队列。执行完成先提交状态再发布终态；终态提交在第 2 步前可由查询发现，在其后由订阅接收。
5. subscription 有一次终态标志，队列消费到 done 后关闭；Broker.close/完成通知若因故未附终态，订阅收敛入口再读持久状态，按 01 安全结束当前流，不重新执行。不得丢掉已排队 done 后再生成第二个。进程崩溃或断开仍不保证送达。
6. 队列溢出则解除订阅、关闭连接并提示状态查询（能发送时发送安全说明），不补业务 done。心跳仅连接保活，不作为运行状态。临时订阅在所有异常/JSON 分支都释放。

这保证正常竞争窗口不漏结束，但不提供连接注册前的历史 token；正文和来源通过持久结果查询获取。Last-Event-ID 不能悄悄接受并假称已恢复位置，V1 返回明确不支持重放的 409 JSON 和查询地址；客户端使用不带重放游标的新订阅。不同连接各自收到的结束通知不代表整个事件流被持久重播。

### 7.3 终态和安全

严格复用 01 信封：schema_version=1、event_type、conversation/workflow/run、UTC timestamp、payload。当前 Context 提供 ID，心跳不是业务事件。

| 结果 | 事件及终态 |
| --- | --- |
| answered | token→done(completed,answered) |
| needs_input | 澄清 token→done(completed,needs_input) |
| rejected | 安全拒绝 token→done(completed,rejected)，不发 error |
| exception/state_unconfirmed | error→done(failed,空) |
| safe pause | workflow_paused→done(paused,空) |
| waiting approval | 未来真实审批接入后 approval_required→done(waiting_approval,空) |

reconciling 不加 SSE 状态，由安全错误和 failed 结束流，查询给真实数据库状态。执行收敛层是唯一终态发布者，Broker 不补第二个 done。正常持续订阅恰好一个 done，之后无应用事件；断开、溢出、崩溃不保证送达。done 不等于 workflow 完成。

#### reconciling 的四层语义

| 层次 | 状态未确认时的含义 |
| --- | --- |
| 当前连接执行流 | error(code=state_unconfirmed,安全 message)→done(run_status=failed,outcome=null)；只结束本流 |
| Run 数据库状态 | reconciling（能提交时）；数据库不可达则保留最后已确认状态并由启动核对处理，不能伪称已落库 |
| Workflow 业务状态 | reconciling，继续占活动槽位，不因发送 done 变 failed/completed |
| 外部副作用 | 尚未确认；不得解释为未执行、已失败、已取消或可以重复支付 |

查询返回持久 run/workflow 的各自状态与确认信息；不把其 reconciling 填入 01 公共 run_status。state_unconfirmed 是安全错误码，不是业务失败结论。普通确定异常与结果未知分别记录，预算和旧操作记录不清零。

仅公开 Response 文本、安全来源、白名单进度与错误模板；禁止推理、SystemMessage、参数/原结果、快照、凭据、原异常。03 的流式指事件/订阅生命周期；Supervisor 结构化路由不流给用户。最终文本可以单块，不能伪称逐 Token 模型生成。

| 任务 | 实现步骤与文件 | 完成标准 |
| --- | --- | --- |
| 3.5.1 事件投影 | streaming/projector.py、01 模型 | 白名单、当前 ID、矩阵正确 |
| 3.5.2 Broker | execution/broker.py，有界队列和资源清理 | 慢/溢出/断开不拖业务 |
| 3.5.3 HTTP 接线 | Route、Service、订阅生成器 | 首注册竞争处理，断开仍执行 |
| 3.5.4 重连/重复/查询 | 先注册后查状态、200 双媒体类型、结果存储和 OpenAPI | 注册/完成窗口无漏终态；重复 JSON、不重执行；无持久重放 |
| 3.5.5 协议与安全验收 | HTTP+实际独立任务测试 | 一次 done、过滤及释放通过 |

## 8. 总体验收与集成门禁

必须 01/02 相应代码验收后才能宣布 03 集成完成。真实模型必须进入 HTTP→可信上下文→PG 受理→独立任务→Supervisor→实际图→验收 Stub→持久快照/预算→SSE→查询链路。默认测试使用可控模型；真实调用显式配置、单独运行，记录模型和用量。

覆盖：三专业目标、两类澄清、切换/放弃、模型非法/超时、预算耗尽、拒绝/失败/暂停、同会话冲突、跨用户、断开/慢消费者/重连、丢通知/重启/迟到结果、一次 done。暂停用实际受控图中断；审批等待仅协议测试，完整 resume 不假报已验收。

生产配置没有 Stub；订单取消/退款/RAG 不计完成。queued 重启可领取、running 转核对而不盲重放。所有调用受预算，终态可查询，持久状态和事件不相互冒充。集成计划见配套文件。

## 9. 一致性审核、同步事项与修订记录

整体架构、五环节、全部三级任务和九步顺序已获认可。本版按最终要求补齐部署、执行权、State、Checkpoint 边界、Gateway/用量质量、四层状态、订阅竞争、HTTP 媒体类型和载荷治理，供最终复核。没有发现需要推翻架构或改变顺序的新冲突。

### 9.1 接口与事务一致性检查

- 单进程 Broker 与单实例单 worker 拓扑一致；数据库锁不误称跨进程订阅支持。
- 受理事务写元数据/任务/预算关联；执行 claim 原子更新；模型不在数据库事务内；快照写入仅用短期 guard 门禁，不伪称与业务结果共享事务。
- prepare_run_input 只返回消息增量和当前可信字段，thread 在配置，未知中断不走普通输入；模型不能覆盖身份。
- 当前 run/claim/epoch/version 共同保护旧写入；启动只核对旧 claimed/running，不重放任意已运行节点。
- Gateway 是所有模型统一入口；工具在 4.3 接统一预留/结算；估算阈值不是绝对硬上限。
- 重复受理 JSON、重连先订阅后检查、持久结果查询共同覆盖首次/重连/结束竞争，不假称持久重放。
- 流 failed、数据库 reconciling、workflow 占槽和副作用未知明确分开，可控流恰好一次 done。

### 9.2 需同步的原阶段与后续阶段

| 阶段 | 同步内容与责任 |
| --- | --- |
| 01/1.3 | 同 POST 200 的 SSE/JSON OpenAPI，state_unconfirmed 四层解释；信封与 run_status 枚举不变 |
| 02/2.2 | Principal 的排队授权有效性、当前验证来源；不把快照当永久权限 |
| 02/2.3 | 200 JSON 重复受理替代待决 303，持久公开结果；03 新增 executor_guard/claim/任务与预算迁移，02 不提前建执行器 |
| 03/3.3 | PG 基础接入、State 工厂、单 worker 部署及执行权门禁 |
| 04/4.3 | ToolExecutor 只接统一工具预算接口；副作用幂等不由 epoch 替代 |
| 06/6.1 | 不重复建 Saver；复杂 Interrupt、审批恢复、崩溃提交窗口核对及跨进程安全恢复；仍遵守单执行器约束 |

上述协议和路线图交界已随本版同步文件；具体实现均待开发。01 原审核记录作为历史保留，以补充节说明变化，不改写过去验收事实。

### 9.3 保留的实施前确认项

既有新建 workflow 的 HTTP 命令表达仍是接线门禁：01 的必填 workflow_id 不能被静默改为可选；新建提议/已有引用须明确，hash 不含服务端后生成 ID。此项此前已登记，不因本轮补充自动定案；公开受理接线前须给出单一协议并确认。预算默认限额、payload/授权期限等部署参数需在开发准备中明确配置并验证，不能隐式使用 SDK 默认值。本节不新增架构分支，也不意味着所有公开接线可以跳过门禁。

## 10. 补充验收矩阵

| 风险 | 必须验证的结果（均为后续开发验收，不是本轮已运行） |
| --- | --- |
| 部署与执行权 | 第二实例拒绝业务；专用连接断开即停止；旧 epoch/token 的元数据/预算/快照写拒绝 |
| 领取 | 并发扫描一次 claim；领取/Run 更新一起回滚；旧实例遗留记录精确识别，不因正常等待误接管 |
| State | 新 workflow 清旧任务、澄清保 task 换 run、公共历史不重复、快照关联冲突/中断拒绝、输入不被修改 |
| Gateway | Supervisor/受控 Specialist 均无旁路；格式失败仍计量；重试不双重；精确/估算/未知分别报告 |
| 载荷 | Schema/尺寸/权限过期拒绝；日志不含消息凭据；终结 TTL 清 payload 而不删幂等，未解决项不误清 |
| 重连竞争 | 完成发生在注册前、注册后查询前、查询后及终态发布前均可收敛；临时订阅全部释放 |
| HTTP | 首次 SSE/重复 JSON/冲突 JSON 与 OpenAPI 一致，终态重连 JSON；无游标重放假承诺 |
| 核对 | error(state_unconfirmed)+done(failed) 不把 Run/Workflow 变成业务失败，不宣称副作用未发生 |

本轮仅修订 Markdown 和导航，未修改业务代码、未执行业务/数据库/真实模型测试。修订文档及配套计划作为开发准备依据，开发仍按二级环节授权并满足 01/02 实际验收及本节门禁。
