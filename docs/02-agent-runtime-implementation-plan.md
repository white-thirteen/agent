# 02 AgentRuntime 实施计划

编制日期为 2026-11-10。代码参照 HEAD `cf3e763`，01 已 ACCEPTED。本文件供主会话安排既定 02 阶段的执行、测试和修复，本轮仅完成规划与只读核查。

## 1. 依据、授权和范围

依据 [AGENTS.md](../AGENTS.md)、[README](../README.md)、[02 整阶段执行任务](02-agent-runtime-execution-task.md)、[项目定位](agent-engine-demo-plan.md)、[唯一开发路线图](development-roadmap.md)、[D01 交付报告](01-foundation-detailed-design.md#01-正式开发交付报告2026-11-09) 及 [D02 完整详细设计](02-agent-runtime-detailed-design.md)。已完整阅读 D02，包括第 3～7 节、六 Task 和第 11.2 节验收矩阵。

本次用户授权允许主会话通过 Bridge 串行协调 02 的规划、执行、测试和修复，覆盖旧文档中的人工转交、待授权描述。本规划角色仅写本文件。实施、独立 QA、主会话复核和用户验收继续分别记录。

保留六阶段、18 环节、36 Task。02 仍为三个二级环节、六 Task，实施顺序为

```text
01 ACCEPTED
  → 2.1.1 类型/State 适配 Demo
  → 2.1.2 Supervisor 与澄清
  → 2.2.1 主图与专业接入
  → 2.2.2 公共结果与骨架验证
  → 2.3.1 独立执行与互斥
  → 2.3.2 SSE 和状态语义
  → 02 阶段验证、独立 QA、修复与主会话复核
  → 用户验收
```

同一 Task 内允许按依赖完成接口、调用方和必要验证。跨 Task 的契约先定义，具体实现归所属 Task，不将先后依赖拆成额外 Task。

03 工具与订单业务、04 PostgreSQL Checkpointer/HITL/退款恢复、05 RAG/Store、06 完整演示集成保持原归属。02 三专业图统一交付 `capability_unavailable` 骨架。MEMORY_MANAGE 仅接合法类型、路由和结果边界，V1 实际命令图及 MemoryManager 属 05，MemoryWriter 属 V2。

## 2. 定向核查结果与 01 复用入口

### 2.1 当前代码与目标之间的必要改动

| 当前入口 | 已有能力 | 02 处理 |
| --- | --- | --- |
| `runtime/context.py` | 唯一 DemoIdentity、DemoContext、SubmitOptions；候选 run_id | 保持三者原职责，增加实际执行上下文，避免重复定义 |
| `api/schemas/chat.py` | 已有最终 ChatRequest、extra forbid、UUID request_id 和标识 NUL 校验 | 保留；新增 status/events 的最小请求体，复用标识约束 |
| `api/dependencies.py` | development/test 名单和服务端普通 scopes，含 memory read/write | 直接复用；演示身份允许选择，权限和领域归属仍由服务端校验 |
| `SessionRepository` | 持久 get/get_or_create 和稳定 thread 绑定 | chat 准备用 get_or_create；状态查询/附流用 get，不因查询创建 session |
| `AgentService.prepare_chat()` | 返回 DemoContext、SubmitOptions | 保留签名与 session 准备，显式转交二者到 Runtime |
| `ModelGateway` | invoke/invoke_structured、不可变成功/失败用量、单次超时及有限网络重试 | Supervisor 改用此入口；收集成功和 ModelCallError 两侧的新快照 |
| `RunLimits` / `RunUsage` | 已在 `runtime/agent_runtime.py` 定义 | 保留唯一类型及默认设置；按模块依赖需要迁到 models 并从旧入口重导出，保持 01 调用方兼容 |
| `AgentRuntime.stream()` | Graph 执行目前依附 async generator；旧 AgentContext、临时计算 thread | 迁移为 submit、独立 task、结果查询和订阅；使用已持久绑定 thread |
| `create_turn_state()` | 旧实现自行生成 task_id，按 pending 是否存在判定续接 | 移除其 ID 生成权，改为显式 new/continue 和可信已存任务输入 |
| Supervisor | 当前直接绑定模型，所有 Human 都进入上下文，强制 pending 类型不变 | 统一 Gateway；仅当前任务最近 12 条允许消息；修复通用澄清无法转具体业务 |
| 主图和 transfers | 已有条件边、白名单父子映射、公共/私有消息分离 | 定向迁移角色和结果契约，补真实三骨架及图内 run_finish |
| SSE formatter | event/data、中文 JSON、安全 JSON 数值序列化 | 复用编码，增加 Runtime 白名单投影与请求级订阅所有权 |
| lifespan | AsyncExitStack 管理池和模型客户端；启动编译旧图 | 注入 Gateway、Saver、专业图、Runtime；Runtime shutdown 后再关模型及池 |

01 的 PostgreSQL schema 版本 2、已批准的 002 延迟唯一约束、双库隔离、连接池和 Windows Selector loop 保留。02 不需要新增表或数据库迁移。现有 `/agent/chat` 准备成功后返回 503 的停止点在 2.3 接线时替换。

工作区已有文档差异、旧文档删除、未跟踪 `app/agents/prompts/general.py` 和独立 Bridge 文档均保留。Bridge 维护不进入本计划的业务改动。P3-01 格式遗留只随实际修改模块处理，交付说明仍需区分已有与新增检查问题。

### 2.2 实际安装 API 核对

本轮仅导入库、读取签名与源码，未编译运行验证图、运行测试或访问外部服务。

| 组件 | 实际版本/接口证据 | 实施使用方式 |
| --- | --- | --- |
| LangGraph | 1.2.20；StateGraph 接受 context_schema；ainvoke 接受 context、durability；aget_state 接受 subgraphs | 节点通过 `Runtime[RunExecutionContext]` 取得当次上下文；普通调用显式传 context |
| Checkpoint | langgraph-checkpoint 4.3.1；InMemorySaver 有 aget_tuple | 显式注入一个应用级 InMemorySaver；不把进程内快照描述为重启恢复 |
| Graph durability | 当前 astream 文档默认 async，支持 sync | 普通执行建议显式 `durability="sync"`，等待 run_finish 最终快照成功后公开结果；04 的 PG 恢复另行验证 |
| FastAPI / Starlette | 0.162.0 / 1.10.0；APIRoute.handle 包住 ASGI app 调用；add_api_route 有 route_class_override | 仅两个 SSE 路由使用小型 APIRoute guard，覆盖 handler 与完整响应调用 |
| sse-starlette | 3.6.0；响应头发送在首次 body 迭代之前；断开监听在响应任务组中 | guard 外层 finally 为首次迭代前清理兜底；复用 SSE 库接收 disconnect，不再竞争读取 receive |
| Python asyncio | Timeout 提供 reschedule(when) | 主动期冻结时可解除主动执行期限，避免把最终提交和编码开销继续算入主动预算 |
| LangChain Core | 1.7.6；现有 Gateway 用 function_calling、include_raw | 保留原生结构化调用方式及 SDK max_retries=0，网络重试只由 Gateway 计数 |

API 存在和静态调用形式已经核对。上下文跨 wrapper 传播、快照提交失败、路由 guard 的真实断开行为仍需执行角色按第 7 节验证，不能以签名核对代替运行证据。

## 3. 冻结契约与实现选择

### 3.1 必须保持的契约

- task_id 仅由 Runtime 在新任务受理时创建，workflow_id 同值兼容；续接澄清保持 task，改变 run。Service 只提供候选 run_id。
- 同一逻辑任务累计 ModelCallUsage 与 RunUsage。模型尝试包括失败、网络重试和一次结构纠正。等待用户不计主动时间。
- CLARIFICATION 待补任务可转具体任务；已明确业务目标的续接保留目标。显式 new_task 只在 D02 允许的边界生效。
- 普通完成、needs_input、rejected、受控 failed 全部由图内 run_finish 结算后到 END。图后 Runtime 收敛 RunRecord 和事件，不二次常规 update_state。
- 真实 interrupt 是 04 的独立控制流。02 不实现审批或 resume，不将未来中断转普通失败/needs_input。
- 单进程单 worker，同 thread 快速冲突、跨 thread 最多 8 活动 Run。执行 task 的生命周期独立于 SSE。
- 单 Run 单订阅、队列 64、终态记录 1800 秒/最多 100 条、关闭等待 5 秒。活动 Run 和不确定 thread 阻塞分别管理。
- request_id 可选，按 user/conversation/id 和 message/input_mode 指纹进行进程内去重；不承担 operation_id 的业务幂等职责。
- 仅发布受控 status/token/error/done，最终回复必须在 run_finish 快照成功后公开。token 可以一次承载完整文本。

### 3.2 可由执行角色完成的常规选择

1. 采用 `runtime/models.py` 存放 Run DTO、状态与原 RunLimits/RunUsage 的唯一定义，原导入位置保留必要重导出；ModelCall 类型保持在现有 gateway。ExecutionContext 复用现有 Pydantic 契约，补 task_id 及同值校验，避免再建同名数据模型。
2. RunExecutionContext 和 RunScope 之间用类型前向引用控制模块依赖。2.1/2.2 节点按契约调用 scope，提前验证时只用测试内轻量替身；2.3.1 实现真实 scope，不创建运行时占位预算服务。
3. thread 门禁可用单事件循环内同步占用/释放的 owner token 实现。D02 允许等价门禁，该选择可以在第一个 await 前明确取得所有权，并保持忙时立即拒绝。
4. 记录保留采用按结束时间排序的终态记录和惰性淘汰；request_id 索引跟随 Run 删除。使用单调时间判 TTL，公开开始/结束时间另行投影。
5. SSE guard 放 `streaming/response.py`，通过 `route_class_override` 只应用到 chat/events。request scope 仅传递本请求 owner，业务状态仍由 Runtime 持有。
6. 关闭订阅和正常发布结束分别处理。正常发布将最终事件和 done 留给消费者排空；异常 close 清队列并唤醒。消费完成再调用幂等 close，避免刚入队的 done 被立即清掉。
7. run_finish 冻结主动时钟时同步解除该 Run 的主动期限定时器，例如使用 Runtime 提供的轻量回调调用 Timeout.reschedule(None)。最终提交失败仍标 uncertain；应用退出仍能取消未完成收尾。

这些选择保持现有接口的职责和 D02 预算/SSE 语义，执行角色可在同等简单且满足验收的方案内调整，并记录实际选择。

## 4. 六 Task 的实施安排

### 4.1 Task 2.1.1 类型/State 适配 Demo

**前置与交付**

依赖 01。交付纯类型、状态和映射，为 2.1.2、2.2 及 2.3 提供共同契约。

**按顺序实施**

1. 在 `agents/types.py` 把 AFTER_SALES/REFUND_REQUEST 迁移到 REFUND/REFUND_APPLY，移除可执行 ORDER_CANCEL，正式加入 MEMORY_MANAGE。同步现有 Prompt、router 和合法 Agent/Task 组合，不保留旧角色别名。
2. 在 `graph/contracts.py` 补 ExecutionContext.task_id、task/workflow 同值关系、TaskStatus、SupervisorOutput、PendingTask 的可信当前任务关联。保留原关联校验和 extra forbid。
3. 按 D02 区分 QA 与 MEMORY_MANAGE 结果。QA completed 要求 sources 与 approved_answer，记忆 completed 要求实际业务结果、sources 为空；退款 completed 保留 operation/approval 要求。02 正式骨架均返回 failed。
4. 在 `graph/state.py` 增加 task_status、task_message_ids、error、两类用量；消息保持 add_messages，其他任务槽和预算完整快照覆盖。
5. 修改 `create_turn_state(context, message, *, task_mode, saved_task)`。new 清任务槽并初始化用量；continue 核验并继承原任务、消息 ID、PendingTask 和预算。每 Run 清理临时结果、追加稳定 ID 的本轮 Human。此函数不生成任何正式 Task ID。
6. 调整 transfers 与 router 的白名单和关联；专业输入只包含当前任务允许的消息和领域候选，可信身份、task/run 不来自 entities。
7. 为后续 Runtime 定义 RunStatus、RunHandle、RunView、TaskView 所需纯 DTO；活资源留在内部 RunRecord。按需迁移 RunLimits/RunUsage 单一定义，保持 01 默认值和类身份。

**文件与验证安排**

修改 `agents/types.py`、`graph/contracts.py`、`state.py`、`transfers.py`、`router.py`，必要时新增 `runtime/models.py` 并最小调整旧导入。更新既有 `test_agent_types.py`、`test_graph_state.py`、`test_graph_protocol.py` 中受影响行为，重点验证新/续任务差异、当前任务消息范围和非法关联。旧代码取消任务成功等断言按批准的新范围迁移。

### 4.2 Task 2.1.2 Supervisor 与澄清

**前置与交付**

依赖 2.1.1。交付 Gateway 驱动的受控路由、两类澄清和 unsupported 路径。

**按顺序实施**

1. 保留 `make_supervisor_node` 的注入模式，把旧 `make_structured_predictor(model)` 迁移为 Gateway 调用适配。传入 ModelCallContext 和当次 RunScope.model_usage，不再从节点直接调用底层模型。
2. 从 task_message_ids 筛选当前任务最近最多 12 条公开 Human/最终 AI。固定系统职责及 PendingTask 单独构造；剔除 Tool/System 历史、带 tool_calls 的 AI 和多余 metadata。
3. 对未知目标保存 CLARIFICATION PendingTask；补充信息识别为具体任务时保留 task/workflow、继承用量并更新目标。移除旧代码“所有 pending 均强制原 TaskType”的规则。
4. 对已具体化目标只补实体，保留 task_type/task_goal。用户隐式改目标时继续原目标澄清并提示显式 new_task，不让模型刷新任务预算。
5. 接受 `SupervisorOutput(kind, decision)`。新/通用任务的 unsupported 生成固定能力边界回复并 rejected；具体 pending 下的 unsupported 保留原目标和 needs_input。条件边仅按程序校验后的有限目标路由。
6. Gateway 成功和 ModelCallError 均先 adopt_model_usage。仅 model_output_invalid 或路由结构校验失败允许一次显式纠正；网络故障由 Gateway 处理，不再增加 Supervisor 网络重试。第二次结构失败转安全 error 更新，交由普通 run_finish 结算。
7. 调整 clarification 节点，使持久 PendingTask、问题文本和最终 task_status 一致，不把审批等待映射为澄清。

**文件与验证安排**

修改 `graph/nodes/supervisor.py`、`clarification.py`、`agents/prompts/supervisor.py`、transfers/router。用可控模型经真实 Gateway 验证未知→具体、具体缺参、unsupported 两种边界和纠正上限；不读取或改动未授权的 general.py。与真实 Runtime 的跨 Run 验证在 2.3 接好后补齐。

### 4.3 Task 2.2.1 主图与专业接入

**前置与交付**

依赖 2.1。交付启动时编译一次的主图、三个专业骨架和显式 wrapper。

**按顺序实施**

1. 修改 builder，显式接收应用级 Gateway、Saver 和三个专业图；使用 context_schema。应用启动统一编译，生产装配不能注入测试成功替身。
2. 分别新增 `graph/specialists/order/builder.py`、`refund/builder.py`、`knowledge/builder.py`。每图采用 `START → check_contract → capability_unavailable → map_result → END`，契约错误走安全错误映射或在可信边界拒绝。
3. 合法请求包括缺少未来业务参数的输入，均返回 `failed + capability_unavailable`。不创建目标业务节点、工具平台、退款 Gate 或 Retriever 占位实现。
4. wrapper 取得当前 RunExecutionContext，白名单构造 SpecialistInput 和新私有 State。显式传递当前 context；保留 LangGraph 当前调用配置的父子关联，不自行生成子 thread/namespace。
5. 子图普通返回后仅提取 result 和可信预算快照，核验任务、workflow、当前 run、角色及任务组合。owner/session 通过可信 context 与原 request 核对，不能从子图结果重新取得权限。子图较小或模型提供的用量不得覆盖 RunScope。
6. KNOWLEDGE_QA 和 MEMORY_MANAGE 在 02 进入同一 Knowledge 不可用骨架；保留 05 按任务分支的契约，实际记忆命令图留 05。
7. `main.py` 改为使用现有 model_resources 返回的 Gateway，显式注入 InMemorySaver 和三个专业图。资源不就绪时保留 01 的安全 readiness 行为。

**文件与验证安排**

修改 `graph/builder.py`、`nodes/specialist.py`、transfers 和 `main.py`；新增三个最小 builder。通过实际编译图验证四种专业任务入口及 unavailable、关联拒绝和 context 传递。目标业务拓扑已在 D02，实施只需引用，避免生成未执行的业务函数。

### 4.4 Task 2.2.2 公共结果与骨架验证

**前置与交付**

依赖 2.2.1。交付唯一公共回复、图内普通结算和安全结果汇总。

**按顺序实施**

1. 调整 result_aggregator，让 completed/rejected 使用已校验事实/批准正文；needs_input 走 clarification；failed 进入结构化错误出口，不靠异常跳过普通结算。
2. Response 只追加批准公开文本，使用稳定 `assistant:{run_id}` ID，并维护当前任务 task_message_ids。无允许文本的失败路径只产生 error，不伪造 AI 成功回复。
3. 新增 `graph/nodes/run_finish.py`，核验关联与结果状态，调用当次 scope.finish_active_period，返回 task_status、model_call_usage、run_usage 和必要任务槽清理更新。
4. 把所有普通分支连接到 run_finish，再到 END。run_finish 不自行调用 Graph 写接口，不产生第二次 END 后更新。
5. 图普通调用使用 sync durability。最终公开事件仍由 2.3 Runtime 在成功返回后发布，专业 map_result、Response 和 run_finish 不提前发最终 token/done。
6. 对意外编程异常保留异常传播到 Runtime 的边界。未来真实中断必须保留 LangGraph 控制流，wrapper 不使用吞掉中断的宽泛异常转换。
7. 将原图协议测试迁移到新契约。受控成功子图仅在测试中用于证明结果校验/唯一回复，应用始终装配 unavailable 骨架。

**文件与验证安排**

修改 aggregator、response、router、builder、contracts，新增 run_finish。复用图协议测试，通过 Saver 的可观察最终 values 和写入观测确认预算结算；监视普通路径没有 aupdate_state。受控 scope 仅是本 Task 的测试依赖，2.3 再用真实 RunScope 重验累计时间。

### 4.5 Task 2.3.1 独立执行与互斥

**前置与交付**

依赖 2.2.2 及 01 准备接口。交付真实 Runtime 受理、独立执行、任务预算、thread 门禁、Run 内存查询和最小订阅基础。

**按顺序实施**

1. 在 `runtime/run_scope.py` 实现 D02 的 model_usage/adopt_model_usage、run_usage/adopt_tool_usage、remaining_active_seconds、finish_active_period、emit_status。继承任务可信基线，主动时间用单调时钟，工具快照只更新工具计数。
2. 在 Runtime 实现 submit/get_run/subscribe/get_state/shutdown 和内部 _execute，替换旧 AgentContext/stream 业务入口。Service.prepare_chat 保留，新增 submit_chat，stream_chat 改为消费 RunHandle 的订阅。
3. 按第 5 节顺序实现请求去重、thread 门禁、容量占位、快照读取、状态迁移和无 await 受理登记。仅 Runtime 新建 task_id；候选 run_id 仅受理成功后有效。
4. 实现 RunRecord、RunView、TaskView。终态 RunView 固定保存该 Run 结束时的累计快照，后续 Task 不修改它。当前 Task 权威来自 Graph 快照和活动运行视图。
5. 实现 RuntimeEvent、单订阅队列和 owner 的最低必要能力。队列先于执行 task 创建，owner 为 None 的内部提交不创建无主队列。详细 HTTP guard 在 2.3.2 接线。
6. 图前开始主动期限；受控预算不足通过图的安全失败分支完成结算，零次新模型/工具尝试。意外异常、取消、终结或快照失败保留本地已知用量，标记 usage_complete=false/uncertain，不再常规回写或自动重放图。
7. 实现终态 TTL/容量惰性淘汰和 request_id 联动删除；保留独立 uncertain thread 阻塞。Run 过期不解锁不确定任务。
8. lifespan 在模型/池回收前调用 Runtime.shutdown。先停止受理，等待最多 5 秒，再取消并 await 执行任务清理，随后关闭外部资源。快照读取中的未受理请求在返回后重查 stopping，避免关闭后新登记任务。

**文件与验证安排**

修改 `runtime/agent_runtime.py`、`runtime/context.py`、`services/agent_service.py`、`main.py`、`core/errors.py`；新增 models/run_scope 和 `streaming/subscription.py`。配置只为真实使用的设置增加集中项，保留 01 默认模型/执行限制。用少量阻塞点验证同 thread 排他、跨 thread 容量、预受理取消与已受理继续、累计预算、过期清理和关闭顺序。

### 4.6 Task 2.3.2 SSE 和状态语义

**前置与交付**

依赖 2.3.1 和 2.2.2。交付完整 HTTP 提交、只读结果查询、重新订阅、安全 SSE 和请求清理。

**按顺序实施**

1. 在仅 SSE 路由使用的 ASGI guard 中建立 SubscriptionOwner，并通过 request scope 交给 Route。guard 包住 handler、响应构造与完整 ASGI response 调用，finally 同步 close，不新增 receive 监听器。
2. chat Route 唯一解析现有 ChatRequest，解析 DemoIdentity 后调用 prepare_chat、submit_chat，成功才返回 EventSourceResponse。删除该入口已失效的准备后固定 503，保留真正未就绪时的 JSON 503。
3. 新增 `POST /agent/runs/{run_id}/status` 和 `/events`，请求体只有 user_id/conversation_id，使用已有 SessionRepository.get 核对持久绑定；未知、过期、其他用户/会话统一 404。events 与 chat 使用同一 owner/guard。
4. RuntimeEvent 按事件类型白名单转既有 StreamEvent，公共关联含 run/task/workflow/sequence，不序列化 RunRecord/State。只从 Graph 成功结算结果发最终文本，允许整段 token。
5. 原子安装重订阅快照和队列，运行中只发未来事件，终态仅发结果快照及该订阅 done。非空 Last-Event-ID 在开流前拒绝。
6. 覆盖消费正常结束、队列溢出、迭代前退出、响应构造/响应头异常和消费断开。close 仅解绑匹配的 subscription_id、清队列和唤醒，不取消执行或释放 thread 门禁。
7. 开流前按 D02 使用固定 HTTP 错误；开流后仅用安全事件。subscription_exists 带原 Run 状态查询入口，现有执行保持不变。
8. 同步未来实际行为到 README、D02 实施记录、Graph 协议及 OpenAPI 描述。完成阶段验证后整理交付报告，交主会话协调独立 QA 和必要修复。

**文件与验证安排**

修改 `api/routes/agent.py`、`api/schemas/chat.py`、Service、events/formatter；新增必要 `streaming/response.py`。扩展既有应用和资源测试，新增聚焦 Runtime/订阅生命周期的测试文件即可。实际连接断开与迭代前 ASGI 退出使用不同验证方式，见第 7 节。

## 5. 关键执行算法与资源所有权

### 5.1 submit、request_id 与门禁

1. 同步清理到期终态记录，检查 Runtime stopping、可信 owner/session 和已接受请求索引。request_id 命中时先核对指纹，直接走原 Run 的只读/订阅路径，不占容量、不生成有效新 Run。
2. 没有命中时同步 try-claim thread 门禁，再为待受理占一个容量名额，随后才 await 读取 Graph 快照。容量包括已占位的受理过程，防止多个 thread 同时读快照后超过 8。
3. 同 thread 正在受理且 request_id 还未登记时立即 thread_busy，客户端可用同 request_id 再试。已有成功受理索引的重复请求按第 1 步处理，避免被活动 thread 门禁错误挡成第二次执行。
4. 快照读取成功后验证 owner、任务槽、pending、next/异常标记与用量；读取失败不是无任务。再次检查 stopping。门禁内按 D02 状态表选择 new/continue 或拒绝。
5. 对 new_task 替换安全澄清目标，旧目标按 superseded 结束语义处理，新任务只占现有当前任务槽；不增加通用 TaskRepository，不改写已结束 RunView。续接使用原任务 ID、PendingTask 和累计预算。
6. 最后无 await 区登记 RunRecord、request_id、初始订阅、owner.adopt，并 create_task、保存强引用和转交门禁释放责任。成功后返回 RunHandle。
7. 受理前取消/错误由 submit 回滚自己持有的占位和订阅。受理后请求 finally 仅关闭订阅，_execute 的 finally 持 token 释放门禁及活动容量。旧 token 不得释放后来占用的新门禁。

request_id 键为 `(user_id, conversation_id, request_id)`，指纹为校验后的 message/input_mode。相同键不同指纹返回 request_id_conflict。相同指纹复用原 Run，无当前订阅可附流，有订阅返回 subscription_exists。缺省 ID 时相同文本也可能是新输入，不做文本去重。

终态保留窗口从 Run 结束计算，1800 秒、最多 100 条，容量淘汰选择最旧终态。删除 Run 同步删除其去重索引并关闭残留订阅；活动 Run 不按 TTL 删除。进程重启后这些映射消失，不能据此判断未来退款/Memory 是否执行，业务幂等留原 operation_id。

### 5.2 生命周期与不确定状态

| 当前可信状态 | 普通输入处理 |
| --- | --- |
| 无任务、completed/rejected/superseded | 新 task、新 run、初始零用量 |
| needs_input + auto | 同 task、新 run、继承用量和待补目标 |
| needs_input + new_task，原目标无副作用 | 旧目标 superseded，新 task |
| 运行中 | thread_busy；已接受 request_id 的重复读取除外 |
| waiting_approval/paused | task_blocked；02 不提供真实产生此状态的业务 |
| failed + auto | explicit_new_task_required |
| failed + new_task，已确认安全终态 | 新 task；存在 next/未知状态时仍拒绝 |
| 快照读取失败、未完成节点、结算提交失败 | state_unavailable/execution_uncertain，禁止用普通输入重放或归零 |

Runtime 的 uncertain thread 标记独立于可淘汰 Run 缓存。02 没有解除任意不确定现场的公共接口，也不承诺标记跨重启持久；04 后由 PG Checkpoint 和业务事实接管。

### 5.3 预算与 run_finish

可信任务快照 → 创建本 Run 的 RunScope → 开始主动时钟 → 节点串行调用 Gateway → 每次成功/错误 adopt 模型快照 → 受控结果/错误 → Response 或错误出口 → run_finish 冻结时钟并返回最终 State → END/快照提交成功 → Runtime finalize → 最终事件 → 释放门禁。

关键约束如下。

- 模型结构纠正最多一次，仍受任务 max_attempts 限制。max_retries 是单次 Gateway 调用的网络重试上限，两者不合并计算。
- 新 run_id、重新订阅和输入澄清均不重置用量。只在真正新 task 时初始化零值。
- 正常 run_finish 返回覆盖式快照，freeze 幂等；最终快照/事件/资源释放的收尾时间排除在主动执行预算外，主动期限也应随 freeze 停止。
- 运行异常、主动期限取消或 Saver 写失败时，保留能确认的最新本地用量及不完整标记。Gateway 在取消时尚未返回的尝试不能伪装为精确零值。
- 02 无真实 Executor，不增加假的工具调用。可用可信种子快照证明跨 Run 工具计数继承，03 再验证真实 handler 前检查和递增。
- 02 不跑真实 interrupt。04 的 Gate 暂停与恢复沿其独立协议接入，不能经过普通 run_finish 清掉 pending interrupt。

### 5.4 SSE owner、队列与 finalize

| 对象/资源 | 创建和持有 | 唯一清理责任 |
| --- | --- | --- |
| thread 门禁/容量占位 | submit 同步取得，受理后转交执行 task | 未受理由 submit，已受理由 _execute finally 释放 |
| 业务 asyncio.Task | Runtime 创建并保留强引用 | 正常执行或 Runtime shutdown；订阅断开不 cancel |
| SubscriptionOwner | 请求 ASGI guard 在 submit/subscribe 前创建 | guard finally 必调 close；其他清理可重复调用 |
| EventSubscription/队列 | Runtime 登记到 RunRecord 和 owner | 同一幂等 close，按 subscription_id 匹配解绑 |
| RunRecord 终态 | Runtime finalize 一次确定 | TTL/容量惰性清理；执行对象完成后释放强引用 |
| pool/model/Saver | 应用级资源 | Runtime shutdown 完成后由 lifespan 回收依赖 |

发布使用 put_nowait。队列满时同步 detach、清队列并发关闭信号，唤醒消费者，业务继续。无订阅时不缓存事件。正常 done 入队后由消费者完成排空，再释放订阅；正常 finalize 不立即 abort-close 清掉尚未消费的结果。

重新订阅在同事件循环无 await 地生成安全快照、安装当前队列并 owner.adopt，避免快照与队列安装之间漏终态。旧 owner 的晚到 close 只能匹配旧 subscription_id。终态重新订阅仅快照加 done，不再发旧 token，不重新执行图。序号可跳跃，不设置可重放的 SSE event id。

## 6. 模块接口和后续交接

| 模块 | 实施后的接口重点 | 后继阶段 |
| --- | --- | --- |
| Route/Service | ChatRequest 唯一解析；prepare_chat 原签名；submit_chat(context, options, owner)；stream_chat(handle) | 04 管理恢复独立入口，普通聊天无审批权 |
| Runtime | submit、get_run、subscribe、get_state、shutdown；内部 _execute；无 HTTP Schema 依赖 | 04 在同门禁/context 中接安全恢复 |
| Graph | ExecutionContext、RunExecutionContext、new/continue 输入、父子白名单、run_finish | 03/04/05 替换各自 unavailable 骨架 |
| Gateway/RunScope | ModelCallResult/Error 新快照交接；任务累计模型及主动时间；可信工具快照接收 | 03 Executor 复用 scope 计数；04 跨恢复继承 |
| streaming | RuntimeEvent → StreamEvent → formatter；owner/subscription/guard | 03 工具安全事件、04 paused/resumed、05 验证来源 |
| memory | 02 仅 MEMORY_MANAGE 路由/结果契约 | 05 Reader/Manager/显式命令，不依赖 V2 Writer |

公共路径冻结为 chat、status、events 三个 POST。status/events 使用最小 JSON body，不接受 user_id Header/Query；公共 ChatRequest 旧 workflow_id 已在 01 拒绝，02 继续保持。内部 workflow_id 直接取 task_id。

health/README 需要在实施时清楚说明 Runtime 可执行和 `checkpoint_backend=memory`，保留无模型/无 DB 安全存活检查。初始化成功仅说明资源可用，不能表述为模型网络、业务工具或跨重启恢复已经验收。

## 7. D02 第 11.2 节逐条验收安排

以下为执行阶段验证方法，本轮均未执行。复用现有测试，新增文件集中在 Runtime/订阅的现有覆盖缺口，不用测试数量作为交付目标。

| D02 场景 | 对应 Task | 验证方法与必须保留的观察结果 |
| --- | --- | --- |
| 通用澄清→具体业务 | 2.1.2、2.3.1 | 可控模型先输出 CLARIFICATION，再输出 ORDER_QUERY，经真实主图/Runtime 两次 submit。断言同 task/workflow、新 run、模型次数累计、允许进入 Order 骨架且返回 unavailable；上下文只包含当前任务允许消息 |
| 具体缺参/显式换目标 | 2.1.1、2.1.2、2.3.1 | 已具体 pending 收到补实体、隐式改目标、unsupported、显式 new_task。观察保原目标或合法 superseded，只有新任务归零并清旧结果；failed/暂停/不确定边界不被 new_task 绕过 |
| 不支持取消/非法模型输出 | 2.1.2、2.2.2 | 取消请求走固定 unsupported 且不调用专业；注入越界 Agent/Task、模型结构错误，最多一次纠正，累计尝试受 Gateway 限制，最终安全 failed，不出现业务调用/内部异常原文 |
| 目标图与三专业骨架 | 2.2.1、2.2.2 | 阅读 D02 目标图作为交接，运行实际三个编译骨架。订单、退款、知识、记忆合法输入和缺业务参数均 unavailable，无业务副作用/来源/审批等待。确认应用注入的是三个实际骨架，测试成功替身只存在测试中 |
| 父子图隔离 | 2.1.1、2.2.1、2.2.2 | 受控子图返回错 task/run/角色及私有 ToolMessage；验证错关联被拒绝、私有历史不进入父 messages/公开事件。测试 QA 缺来源/approved_answer 拒绝、记忆 sources 必须为空；可信用量不被子图较小值覆盖 |
| 预算 | 2.1.2、2.2.2、2.3.1 | 经真实 Gateway 替身触发网络重试、结构纠正和失败，核对累计模型次数；可控单调时钟验证两个 Run 的主动时间累计且两 Run 之间等待不增加。用非零可信工具快照验证继承，预算耗尽模型不再启动；取消中未返用量明确 incomplete |
| 普通结算与中断边界 | 2.2.2、2.3.1 | 编译图覆盖完成/澄清/拒绝/受控失败，观测 run_finish 冻结次数、Saver 最终值和事件时序；让最终 Saver 提交阻塞/失败，提交前没有最终 token/done，失败不假成功。普通路径 aupdate_state 调用为零。真实 interrupt 验证归 04，仅检查边界未被宽泛捕获设计破坏 |
| 同 thread/不同会话 | 2.3.1 | 模型/快照读取受控阻塞，第一个执行未释放时第二请求快速 thread_busy；不同 thread 到达各自阻塞点证明并发。8 个活动/受理占位时第 9 个 runtime_busy，不产生 task/订阅泄漏；预受理取消释放门禁，执行结束后可再次使用同 thread |
| 重复请求 | 2.3.1、2.3.2 | 同 key/指纹复用原 Run且模型调用不增加，有订阅时 subscription_exists，断开后可附流；改 message/input_mode 返回 conflict。缺省 ID 不按文本去重。可控时钟及少量缩小保留参数验证 TTL/容量联动清索引，新 Runtime 不承诺旧索引存在；uncertain 阻塞不被淘汰清掉 |
| 断开/慢队列 | 2.3.1、2.3.2 | ① ASGI 控制发送响应头前的阻塞/失败，使业务已接受但迭代器从未开始，请求退出后观察 owner 已关闭、当前订阅为空、task 未取消，立即再订阅成功。② 覆盖 Route 响应构造异常和头发送异常。③ 至少一次实际本机 HTTP socket 客户端取消/断开，保持可控模型执行阻塞，断开后释放模型，再查询最终结果。④ 小队列溢出唤醒消费方、不阻塞业务；旧 owner 晚清理不关新订阅 |
| 重订阅/结束 | 2.3.2 | 运行中断开再订阅，首个事件为当前快照，仅后续事件；终态订阅只有结果快照和一个 done，原图调用数不增加。正常可消费流 done 恰一次，needs_input 的 done 不标 Task completed。非空 Last-Event-ID 开流前 409，无持久 SSE id/replay 承诺 |
| 异常/预算结算失败 | 2.2.2、2.3.1 | 注入 snapshot 读取失败、图意外异常、run_finish/Saver 失败、主动超时；核对安全 error、usage_complete 和 uncertain。后续 auto/new_task 不把不可信快照当空任务，Run TTL 后仍阻塞。故障处理不调用普通 Graph 输入重放、不二次补写假终态 |
| 关闭/隔离 | 2.3.1、2.3.2 | 注入可结束及挂起执行，观察拒绝新受理、5 秒边界、取消 await、门禁/订阅释放及模型/池最后关闭。跨演示用户及跨 conversation 查询同 Run 统一 404，production 拒绝 DemoIdentity。复用 01 隔离用例，不重复建库/重跑整套 PG 基础设施验收 |

### 7.1 证据和回归顺序

1. 每个 Task 完成后运行受影响的现有用例和必要的新风险用例，记录实际命令、结果及遗留。规划文件中的方法不标为已通过。
2. 2.2 用真实编译图配受控 Gateway/子图；2.3 接真实 Runtime 后再验证跨 Run 和 HTTP 行为，避免只测直通包装。
3. ASGI 迭代前断开采用发送边界的可控阻塞及请求退出，记录迭代器确实从未进入。实际 HTTP 断开独立记录连接取消和后续结果查询，不能用 generator.close 或缓冲型 TestClient 流结果代替。
4. 阶段公共协议变更完成后做一次必要完整回归和 Ruff 检查。沿用项目 .venv，数据库相关既有测试需要时只使用现有测试库；不重建开发库、重跑迁移或扩展环境。依赖无变化时无需为了形式重复安装或解析依赖。
5. 真实模型验证按执行授权和必要性单独记录，用当前已配置 provider。默认自动测试使用可控模型，不将付费网络请求加入默认套件。02 不声称 unavailable 骨架已经完成订单/退款/RAG 业务联调。
6. 独立 QA 由主会话安排，本规划和实施自测均不能替代。执行交付写 `docs/02-agent-runtime-delivery-report.md`，逐项关联本矩阵、运行证据、未实现能力和遗留归属；修复提示词及修复记录依 AGENTS 规范分别保存。

## 8. 风险、冲突分类与主会话裁决边界

| 风险或差异 | 分类与处理 |
| --- | --- |
| D02 历史段落仍有待冻结/待授权文字，其他定位文档保留旧状态 | 当前用户授权与 01 ACCEPTED 为准。这是状态记录差异，本计划不改历史文档、不作为暂停实施的设计冲突 |
| 当前代码仍是旧角色、生成器 Runtime、图内 UUID 和通用澄清类型锁定 | 既定 02 的迁移内容，按六 Task 实施，不重新请求架构批准 |
| RunScope 真实实现归 2.3，而 Supervisor/run_finish 更早引用其契约 | 先定义上下文/接口并用测试内替身验证，后接真实实现，不新增 Task 或运行时占位平台 |
| 活动 Run 的 request_id 命中与 thread_busy 的检查先后 | 按第 5.1 节把已接受索引读取作为例外；新执行仍须门禁。属于满足 D02 的实现顺序选择 |
| 正常 done 刚入队就 close、或主动期限在 freeze 后仍触发 | 分别采用正常排空与异常关闭、freeze 解除主动期限，并纳入时序验证；不增加事件平台或预算器 |
| FastAPI 路由优化、SSE 取消、父子 context 和 sync 提交的实际行为 | API 已静态核对，实施必须取得第 7 节运行证据；验证失败先最小修复适配，不直接更换架构/依赖 |
| 02 内存快照丢失或进程取消造成计数不完整 | 保持明确限制和 uncertain 语义；跨重启持久恢复归 04，不为 02 引入新表/恢复扫描 |
| 共享工作区已有修改和未跟踪文件 | 只触及授权业务文件的必要区域，不归档他人差异、不把 Bridge 文件纳入阶段业务交付 |

**当前未发现必须重开冻结设计、需要主 Agent 先作架构裁决的冲突。** 上述实现选择可直接纳入执行安排。

后续只有出现以下实际不相容证据时，才提交主会话裁决并暂停受影响部分。

- 实际版本不能在既定父子图/context 及正常结算契约下工作，最小适配仍需修改冻结公共接口。
- 满足验收必须引入新持久化对象、升级依赖或改变已批准的预算/状态/HTTP 语义。
- 发现共享修改与本次必要改动相互覆盖，无法在保留现有修改的前提下完成局部合并。

提交时列出冲突文档/代码位置、实际证据、影响 Task 和最小建议，由主会话处理；规划和执行角色均不自行扩大 V1。

## 9. 本轮产出与停止点

本轮仅新增本实施计划。已完成文档和相关代码只读核查、当前 HEAD/工作区差异确认及本地已安装 API 的签名/源码检查。没有修改业务代码、配置、依赖或数据库，没有执行测试、独立 QA、服务启动、迁移、模型联调、Bridge 调用、Commit 或 Push。

推荐主会话将本计划连同执行任务交执行角色，从 2.1.1 开始按依赖连续完成六 Task，随后协调验证、独立 QA 和修复。阶段 ACCEPTED、进入 03 以及正式 Git 归档均依用户授权处理。本规划到此停止。
