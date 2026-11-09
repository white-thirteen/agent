# 01 工程基线与核心协议收敛——阶段详细执行设计

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**审核通过，待开发执行**。

定稿日期：2026-11-08。范围：整体路线图的 1.1、1.2、1.3。九阶段、34 环节及既定架构不变。

本文件固化已通过架构审核的设计，纳入最终四项补充。设计通过不代表代码已实现、测试已运行或阶段已验收。本轮只更新文档，未执行开发、安装依赖、启动数据库或调用模型。

## 1. 阶段目标、起点与边界

交付可追溯工程基线、统一标识和 State 契约、显式父子映射、版本化公共事件、安全错误协议，以及当前输出点的最小迁移。

当前已有 HTTP 骨架、配置、Service/Runtime、主图、基础 State、路由及专业输入输出契约、SSE 编码。专业子图、可信认证、数据库、独立任务、审批恢复、RAG 和长期记忆尚未实现。已有实现优先复用；历史测试结果不替代本次执行验收。

本阶段不实现 02 的认证和仓储、03 的 Supervisor 决策完善和执行治理、06 的审批恢复，不提前开放业务副作用。依据为实际代码、[整体路线图](../development-roadmap.md)、[开发规范](../../AGENTS.md)及[当前 Graph 协议](../graph-protocol.md)。

## 2. 1.1 工程与架构基线确认

完整复用 [1.1 详细执行方案](01-1-engineering-and-architecture-baseline-plan.md)，作为本阶段的附属执行说明，不扩大职责。该环节设计已认可，开发与验收尚未执行。

| 任务 | 主要工作与交付 | 完成标准 |
| --- | --- | --- |
| 1.1.1 现有成果核验 | 核对工作区增量、能力及文件证据，产出成果台账 | 区分完成程度与验证状态，保留已有修改 |
| 1.1.2 工程环境检查 | 核对项目解释器、依赖和工具，形成环境记录 | 约定环境一致，依赖检查通过 |
| 1.1.3 架构边界核验 | 核对调用链和责任，登记后续归属 | 当前事实、目标约束与缺口分开记录 |
| 1.1.4 运行与测试基线验证 | 复用既有测试，限定修正工程格式问题 | 当前检查通过，未降低规则或假报业务可用 |
| 1.1.5 问题分类与优先级评估 | 按缺陷、工程、文档、未实现和待定决策分类 | 每项有责任环节、门禁和完成证据 |
| 1.1.6 开发基线固化 | 汇总验证、问题及工作区身份，更新入口 | 源码与验证可追溯，未提交内容的复现限制明确 |

顺序沿用原方案。1.1 的基线是 1.2 开发前起点；后续修改形成独立验证记录，不覆盖起点证据。通用澄清续接缺陷归 3.1，不能借本阶段检查通过宣称已修复。

## 3. 1.2 State 与跨图契约收敛

### 3.1 现状与范围

复用 app/graph/contracts.py、state.py、transfers.py、router.py 和 app/agents/types.py。已有 Agent/Task、ExecutionContext、RouteDecision、PendingTask、SpecialistInput/Result、SourceReference、消息 Reducer、轮次初始化和关联校验。

本环节核对并补齐字段权威、生命周期、边界校验和说明，不另建 State 或业务模型，不加入预算、支付、审批的空槽位。身份可信性、具体业务必填条件和执行权限不由结构校验代替。

### 3.2 标识和上下文

| 标识 | 来源、含义与生命周期 |
| --- | --- |
| user_id | 开发期模拟输入；2.2 后由可信身份上下文提供；模型和子图不能覆盖 |
| conversation_id | 逻辑会话；2.2 校验归属；可以包含多个顺序 workflow 和 run |
| workflow_id | 当前逻辑工作流关联；请求值不证明创建成功或归属；2.3 登记与校验 |
| run_id | Service 为一次执行创建；恢复使用新 run，旧值不能成为新执行权威 |
| task_id | 服务端生成的目标关联；同目标补信息保留；不充当幂等键 |
| thread_id | 服务端定位已验证会话的 Checkpoint；不接受聊天直接指定，不交给模型 |

ExecutionContext 保留用户、会话、workflow、run 四字段。thread 保留在 Runtime 执行配置，不重复加入各级 State 和专业结果。AgentContext 承载入口消息及关联，ExecutionContext 承载内部关联，两者显式构造转换，不增加继承层次。

### 3.3 字段权威与更新方式

| 字段 | 写入方及更新方式 |
| --- | --- |
| messages | 用户轮次工厂、Response；add_messages 增量，相同 ID 替换 |
| user/conversation/workflow/run | 当前执行入口；子图只读，恢复时以本次上下文为准 |
| task_id | 新目标创建，原目标续接保留；受控任务切换另行更新 |
| agent_type/task_type/task_goal/route_decision | Supervisor 经转换函数写入；决定为权威，镜像必须一致 |
| pending_task | 路由或结果转换函数；待补时保留，解决或明确结束时清除 |
| specialist_result/final_answer/sources | 新轮次先清空；当前结果覆盖，来源不跨轮累加 |

create_turn_state(context, message, pending_task=...) 只校验关联、创建当前用户消息增量和轮次字段，不读取历史、认证、访问数据库或执行审批恢复。除了消息字段，其余按契约覆盖，不为以后并行添加通用合并器。

### 3.4 同一 thread 的轮次、结束与恢复契约（最终补充）

| 场景 | 保留 | 新建或清理 | 禁止行为 |
| --- | --- | --- | --- |
| 普通新轮次、新目标 | 公共消息历史、可信用户/会话/thread | 新 run；新 task；workflow 由已校验关联提供；清空旧路由、结果、答案、来源和无效待补项 | 不能因复用 thread 沿用旧 workflow 结果或旧 run |
| 同目标澄清续接 | 用户/会话/thread/workflow、task、目标和已知候选实体 | 新 run、新用户消息；重置本轮决定、结果、答案和来源 | 不重建目标，不把补信息当审批，不忽略 PendingTask 关联冲突 |
| 任务完成或业务拒绝 | 公共历史与本轮最终结果作为已结束快照 | 清除 pending；下次新目标重新初始化临时字段 | 不删除历史，不将本轮来源/实体作为下一目标的默认参数 |
| 等待审批 | 原 workflow/thread/task、私有业务状态、操作与审批关联、已消费预算 | 当前流以 waiting_approval 结束 | 普通聊天不能变成 resume；不进入完成汇总，不清空恢复所需业务状态 |
| 审批恢复 | 原可信用户/会话/workflow/thread/task、业务操作、预算及执行记录 | 新 run；对执行和返回关联刷新为当前上下文；只在恢复边界清理旧公开结果/答案/来源 | 不调用普通轮次工厂重建任务，不追加伪造用户消息，不信任旧私有 request.run_id |

通用 CLARIFICATION 表示尚未确定业务，后续允许确定实际任务与目标并保留本次意图的 task_id；已明确的业务缺字段则保留原业务目标。显式放弃或独立换目标须走受控切换并建立新任务关联。该决策流程在 3.1 实现。

1.2 负责上述契约和可纯验证的关联约束。3.3 实现基础 Checkpoint、互斥、上下文装配，6.1 实现持久化中断和实际恢复刷新时序。恢复状态不得整份重置或整份回灌；旧 run 结果不得作为新 run 接受。审批恢复相关用例在 01 中只校验契约，不伪造已具备恢复能力。

### 3.5 路由、输入与结果

RouteDecision 保留固定 Agent/Task 映射、澄清字段完整性、未知字段拒绝及镜像一致性校验。未知意图走澄清；格式非法拒绝，不静默转成可执行业务。具体订单必填参数和规则归业务环节。

| 接口 | 职责 |
| --- | --- |
| apply_route_decision | 返回路由增量，建立待补任务，清理旧结果；不原地改 State |
| build_specialist_input | 从已验证路由构造专业请求，仅复制上下文和公开历史 |
| create_specialist_state | 每次调用独立私有状态，不共享可变消息和实体 |
| apply_specialist_result | 核验 workflow/run/task/Agent/Task，白名单回传，不合并整个子图 |

公开历史仅取 HumanMessage 与无工具调用的公开 AIMessage；过滤 SystemMessage、ToolMessage、工具调用及内部附加元数据。entities 只是候选参数，不能覆盖 context。JSON 字段不放连接、客户端或凭据。复制和校验集中在跨图边界，不逐层增加深拷贝。

| SpecialistResult 状态 | 结构要求 |
| --- | --- |
| completed | 业务有 facts；取消有 operation_id；退款另有 approval_id；知识回答有来源 |
| needs_input | 缺失字段和问题齐全，保留原目标 |
| rejected | 明确业务拒绝，不作为程序异常 |
| failed | 有稳定错误码和安全信息 |

结构完整不证明真实执行、审批有效或来源可信；对应服务核对。等待审批不是新增的伪完成专业结果，未来通过 interrupt 和执行状态表达。

### 3.6 异常与兼容

字段错误沿用 Pydantic ValidationError；关联冲突沿用 GraphProtocolError。拒绝陈旧结果与不匹配 PendingTask，不悄悄改成新目标。保留现有字段和函数形态；没有持久数据迁移时不开发迁移框架。未来修改持久 State 需单独记录版本策略。

### 3.7 三级任务

| 任务 | 工作、文件与交付 | 依赖 | 完成标准 |
| --- | --- | --- | --- |
| 1.2.1 标识与上下文契约核对 | contracts.py、入口 Context；核对 ID 来源和显式转换 | 1.1 | 标识不混用，身份不来自模型；上下文约定完整 |
| 1.2.2 State 生命周期收敛 | state.py；核对初始化、写入方、轮次清理和四类轮次/恢复契约 | 1.2.1 | 消息增量正确，待补关联受检，旧 run 临时字段不串轮 |
| 1.2.3 路由与待补任务契约收敛 | contracts.py、router.py、路由映射；明确通用与业务澄清语义 | 1.2.1、1.2.2 | 非法组合和镜像冲突被拒绝；不提前修 Supervisor |
| 1.2.4 父子输入输出边界收敛 | transfers.py、contracts.py、wrapper；核对消息、数据隔离和结果关联 | 1.2.2、1.2.3 | 子图不能覆盖身份、污染历史或回传陈旧结果 |
| 1.2.5 契约集成验收与说明更新 | 现有 Graph 测试、graph-protocol.md；受控实际父子图验证 | 前四项 | 契约行为可复核；文档区分当前实现与未来恢复 |

顺序为上述依赖顺序，测试随任务补齐。复用既有测试，重点验证新轮次重置、同目标 task 保留、关联拒绝、可变数据隔离、needs_input 与完成清理、私有历史过滤。审批恢复只验契约，实际机制由后续验收。

## 4. 1.3 对外请求与事件协议收敛

### 4.1 现状和范围

已有 ChatRequest 四字段、长度和额外字段限制、开流前未就绪 503、event/data、JSON Formatter 和 SSE 心跳。当前缺少完整信封、分事件负载、统一安全校验错误、来源呈现和暂停恢复类型。

本环节交付协议与现有输出位置的最小迁移，不实现认证仓储、受理任务、真实 Token 增量、订阅、重连、重放或审批接口。后续 3.5 复用本协议实现完整事件和订阅机制。

### 4.2 请求及身份边界

保留 POST /agent/chat 和 user_id、conversation_id、workflow_id、message。ID 去首尾空白后非空且最多 128 字符；message 非空且最多 32000 字符；不要求 UUID。拒绝额外字段，包括 run/thread/task、权限、审批、任意历史、模型和工具配置。

开发期 Apifox 自报 user_id **只用于受控模拟环境，不构成可信身份认证**。不能把会话字段或结构校验当权限证明。生产身份、调用方认证和权限验证归 2.2；workflow 值只是关联提议，2.3 登记并核验归属。受理幂等由 2.3 定义，本阶段不接受被忽略的假幂等参数。

### 4.3 版本 1 事件信封与编码

统一字段：schema_version="1"、event_type、conversation_id、workflow_id、run_id、timestamp、payload。timestamp 为服务端带时区时间，统一输出 UTC ISO 8601。ID 来自当前入口上下文，不从模型或专业结果猜测。不暴露 user_id、thread_id、Checkpoint namespace 或完整 task。

SSE event 与 event_type 一致；data 序列化整个信封，不再只编码 payload。继续保留中文、转义换行，禁止 NaN 和非 JSON 对象。心跳是传输注释，本阶段不发送 SSE id，不暗示 Last-Event-ID 重放。

| 事件 | 最小公开负载和约束 |
| --- | --- |
| status | phase 为有限公开值；当前只允许真实 started，不伪称持久受理 |
| token | content；只发送用户可见回复；当前可整段，未来可分块 |
| tool_start | call_id、公开工具名称；不含原始参数 |
| tool_end | call_id、结果状态、可选安全摘要；不含原始结果 |
| approval_required | approval_id、operation_id、安全摘要；必须有真实记录及中断 |
| workflow_paused | reason_code、安全说明；必须到达安全暂停点 |
| workflow_resumed | reason_code、可选 previous_run_id；使用新 run 信封 |
| error | 稳定 code、安全 message，不透传异常和原模型内容 |
| done | run_status、outcome、sources；只通知当前执行流终态 |

以有限模型和对应 payload 校验，不增加动态注册框架。未来工具/审批/暂停事件当前只定义和测试，未接入能力不输出假事件。金额和有效期等字段随相应业务设计扩展。

### 4.4 done、业务结果与 Workflow 的映射（最终补充）

**done 只代表当前执行流的终态通知，不代表整个 Workflow 完成。等待审批可以结束当前流，之后通过新 run 在原 Workflow/thread/task 上恢复。**

| 情况 | 公开事件顺序 | run_status | outcome | 业务含义 |
| --- | --- | --- | --- | --- |
| 正常回答或专业完成 | token → done | completed | answered | 业务终态仍由仓储/领域结果确定 |
| 缺少用户输入 | token(澄清) → done | completed | needs_input | 保留待补目标，下一轮新 run 续接 |
| 业务拒绝 | token(安全拒绝说明) → done | completed | rejected | 不输出程序 error；该目标业务拒绝 |
| 执行异常 | error → done | failed | 空 | 不据此断言外部副作用未发生 |
| 等待审批 | approval_required → done | waiting_approval | 空 | Workflow 保持等待，未来可信恢复 |
| 安全暂停 | workflow_paused → done | paused | 空 | 保留安全恢复状态 |
| 确认取消本次执行 | 必要状态说明 → done | cancelled | 空 | 不等于撤销已完成外部操作 |

表中可前置真实 status。run_status 限定为表中五值；outcome 为 answered/needs_input/rejected/空，按表校验，不接受 failed+answered 等矛盾组合。sources 默认空，复用 SourceReference 核心字段；公开链接限 HTTP/HTTPS，不安全 URI 省略，真实性和访问权由检索链保证。

不加入虚构 workflow_status；WorkflowRepository 后续维护业务状态。正常连接、进程存活且可控结束的路径必须**恰好一次 done，之后无应用事件**。各出口汇聚到一个终态输出责任位置，避免分支和 finally 重复发送。断开或崩溃不保证送达，不能把未收到 done 当成业务未执行。

### 4.5 最小接线与错误

保留当前 Runtime 运行方式：当前 AgentContext → started → 原 Graph 执行 → final_answer 的 token → 当前结果投影的 done；异常 → 安全 error → failed done。待补映射 needs_input，专业 completed/rejected 分别映射 answered/rejected；无合法公开结果按失败。关联 ID 始终用当前 Context。

1.2 已校验内部结果，公开投影不另建业务校验；来源放入 done，完整引用排版归 7.4。现有 HTTP 迭代器仍持有执行，不宣称断开继续执行，缺口归 3.3/3.5。

HTTP 错误保留 error.code/message，可附带已知会话/workflow/run，未知不伪造。422 为请求错误，503 为未就绪，500 为开流前通用服务异常；401/403 归 2.2、404 归对应资源、409 归状态冲突后续接入。校验错误只返回安全字段路径、稳定类别和模板说明，不返回含 input 的完整异常对象或原输入。

头发出后使用 error 事件，不再改 HTTP 状态。本阶段仅实现已有请求、就绪等前置处理；认证、冲突和审批检查随相应能力落地。

### 4.6 兼容与扩展

请求路径和四字段保持；SSE 明确迁移到版本 1，旧负载改为完整信封，旧 status 改为 run_status/outcome，同次更新测试和消费示例，不长期双写。执行前核实外部消费者，有依赖时明确迁移安排。兼容新增可选字段；删除、语义或状态组合的破坏性变更须显式版本变化。

### 4.7 三级任务与验收

| 任务 | 工作、文件与交付 | 依赖 | 完成标准 |
| --- | --- | --- | --- |
| 1.3.1 聊天请求与错误契约 | chat.py、公共错误 Schema、main.py、core/errors.py；保留字段并统一安全错误 | 1.2 | 无原值泄漏，不提前实现认证；模拟身份限制明确 |
| 1.3.2 公共事件信封与负载模型 | streaming/events.py；版本、上下文、时间、九事件和终态组合 | 1.3.1 | 缺字段、错类型、无时区和矛盾终态被拒绝 |
| 1.3.3 JSON 与 SSE 编码迁移 | streaming/formatter.py；编码整个信封 | 1.3.2 | event 一致、中文换行正确、不生成重放 ID |
| 1.3.4 现有输出点最小接线 | runtime、service 现有输出；Context、开始、结果、失败投影 | 前三项 | 可控结束一次 done；缺输入/拒绝/异常不混报；未改独立任务机制 |
| 1.3.5 公共协议验收与消费示例 | HTTP/事件测试、OpenAPI、README、公共协议说明 | 前四项 | HTTP/SSE 与示例一致，无外部调用，不假报审批恢复已实现 |

顺序依表，测试随任务补齐。验证请求边界、安全错误、ID 一致、时间和 JSON 往返、终态矩阵、恰好一次 done、私有数据过滤和来源保留。使用受控依赖，未来事件只做契约验证。

## 5. 阶段整体审核与统一验收

执行顺序：1.1 验收 → 1.2 契约验收 → 1.3 协议验收 → 01 总体验收。环节内独立准备可并行，相同文件修改串行，不要求子 Agent。

| 交界 | 统一方案 |
| --- | --- |
| 内部与公开标识 | 请求关联经入口进入 Context，再到 State/专业请求；公开事件只取当前 Context |
| task 与 thread | 内部任务和快照标识不作为公共请求授权；同 thread 复用不代表旧任务继承 |
| 1.2 与 3.1 | 契约与 Supervisor 决策分开；已知通用澄清缺陷仍由 3.1 修复 |
| 1.3 与 3.5 | 当前格式迁移与完整事件订阅机制分开 |
| 2.2/2.3 | 接入可信身份、归属和持久元数据；不把用户自报 ID 或 State 当权威 |
| 3.3/6.1 | 契约先行，实际 Checkpoint、互斥、上下文刷新、审批恢复按后续环节实现 |
| run 与 Workflow | 当前流终态与业务状态分开；等待审批之后新 run 恢复同一 Workflow |

统一验收：

- 1.1 起点和版本限制可追溯；原有工作区成果保留。
- 每项任务有实现或现有实现满足要求的证据，内部/公开 ID 无混用。
- State 初始化、同目标续接、完成清理、陈旧结果拒绝、父子隔离通过必要测试；恢复契约完整，实际恢复不误报已实现。
- HTTP/SSE 符合协议，错误和消息不泄漏敏感内容。
- 实际编译主图配合受控依赖验证澄清、专业结果、失败；终态矩阵契约测试覆盖等待审批等未来类型，可控结束恰好一次 done。
- 完整测试和代码检查通过；依赖变更时检查依赖；不把真实模型、数据库、并发或审批恢复写成已验收。
- 文档区分当前行为、已批准设计与后续能力；没有提前开发 02、03、06。

## 6. 审核与本轮文档变更记录

| 事项 | 记录 |
| --- | --- |
| 架构审核 | 用户认可 1.1/1.2/1.3 的任务、方案、顺序和职责；状态为审核通过，待开发执行 |
| 最终补充一 | done 仅当前流终态；等待审批后新 run 恢复同一 Workflow，见 4.4 |
| 最终补充二 | 同 thread 的新轮次、澄清、完成和审批恢复 State 契约，见 3.4；机制归 3.3/6.1 |
| 最终补充三 | 拒绝、缺输入、异常、审批等待与 SSE 的统一映射和一次 done，见 4.4/4.7 |
| 最终补充四 | Apifox user_id 仅受控模拟，不构成认证，正式验证归 2.2，见 4.2 |
| 本轮输出 | 新增本正式阶段文档；同步 1.1 附属方案状态、README 导航、路线图设计/执行方式和设计状态 |
| 本轮未执行 | 业务代码修改、开发任务、数据库操作、模型调用、业务测试；没有阶段实现或验收通过记录 |
| 下一阶段 | 02 完整设计先在会话输出待审核稿；未审核前不视为正式开发规范 |

后续开发会话按二级环节逐项执行并登记实际变更和验证。设计状态与实现、测试、联调状态分别记录。

## 7. 03 架构最终补充的协议同步（2026-11-08）

本节记录后续已审核架构的接口衔接，不改变原有信封和 run_status 枚举，不表示 01/03 代码已实现。

- POST /agent/chat 首次受理 200 text/event-stream；相同幂等命令重复受理 200 application/json 的 ExistingRunResponse（schema_version=1、disposition=existing、conversation/workflow/run、status_url、可空 events_url），不采用 303，不重执行。OpenAPI 同一 200 同时声明两种媒体类型，客户端按 Content-Type 解析；冲突 409 JSON。
- 重连先授权、注册订阅，再重新读主库状态。发头前已结束则释放订阅返回状态/结果 JSON；仍活动则 SSE 接收注册后的事件。无持久重放、不发 SSE id，带 Last-Event-ID 的重放请求明确 409 和查询地址。
- 数据库 Run/Workflow reconciling 使用 error(code=state_unconfirmed)→done(run_status=failed,outcome=null) 结束当前流；查询仍给数据库真实状态。该 failed 不是业务失败，不证明外部操作未发生，不释放活动槽位。
- 可控结束一次 done；订阅注册与完成的竞争、JSON 分支清理和终态去重按 [03 架构](03-stage-detailed-design.md)第 7 节验收。01 定义契约，实际 Broker/受理接线归 03。
