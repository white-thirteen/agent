# Graph 字段、跨图协议与路由使用说明

> 适用范围：本文是**当前代码实现参考**，不是新Demo的目标架构或开发路线图。代码本轮未变，因此旧Agent角色/必填workflow等仍按下文描述；[项目定位文档](agent-engine-demo-plan.md)是架构及V1范围权威，[六阶段路线图](development-roadmap.md)是唯一有效V1路线。阶段迁移保留显式父子映射、关联校验和消息隔离，不据本文推断HITL、Store或RAG已实现。

状态：以下契约、基础 State、转换函数、Supervisor、澄清、专业 wrapper、汇总、回复节点及主图 builder 已实现。
模型配置完整时应用会装配主图；Runtime 通过 `create_turn_state` 初始化 Context。订单、售后、知识专业子图尚未实现，未注入的分支会以安全错误事件结束。
Checkpointer 当前使用进程内 `InMemorySaver`，应用重启会丢失快照；未引入 Store。
本文描述内部图协议，未修改 HTTP 请求格式或 SSE 协议。

## 1. 文件与依赖方向

| 文件 | 内容 |
| --- | --- |
| `app/graph/contracts.py` | ExecutionContext、RouteDecision、PendingTask、SpecialistInput/Result、SourceReference 等可校验模型 |
| `app/graph/state.py` | AgentState、SpecialistState、节点更新类型、create_turn_state |
| `app/graph/router.py` | validated_route、route_after_supervisor、route_after_specialist，只有有限分支选择，无业务执行 |
| `app/graph/transfers.py` | Supervisor 决定入状态、父图输入映射、子图初始化及结果回传 |
| `app/graph/builder.py` | 主图节点注册、条件边连接及进程内 Checkpointer |
| `app/graph/nodes/supervisor.py` | 结构化路由、待补任务续接及决定映射 |
| `app/graph/nodes/clarification.py` | 使用待补任务或路由决定中的问题生成澄清回复 |
| `app/graph/nodes/specialist.py` | 父 State 到专业子图的白名单 wrapper 和结果映射 |
| `app/graph/nodes/result_aggregator.py` | 将已校验的专业结果摘要交给回复节点，不再调用模型 |
| `app/graph/nodes/response.py` | 将唯一用户可见回复写入公共消息历史 |

contracts 不依赖 HTTP 或 Runtime；state 引用契约，router 读取 state，transfers 组合这些边界。
GraphContract 禁止额外字段、启用实例重新校验并冻结属性赋值。
冻结不是深层不可变，dict/list 仍可能修改，因此转换边界重新校验并深拷贝嵌套数据。
配置语义可参见 [Pydantic 配置说明](https://docs.pydantic.dev/latest/api/config/)。

## 2. 主图 AgentState

| 字段 | 类型 | 来源与更新规则 |
| --- | --- | --- |
| messages | list[AnyMessage] + add_messages | 只放公共历史，节点返回新消息增量；相同 ID 替换，不按内容去重 |
| user_id/conversation_id/workflow_id | str | 调用方提供的可信上下文；子图回传不能修改 |
| run_id | str | 本轮运行标识；恢复时仍以 Runtime 当前执行上下文为权威 |
| task_id | str | 服务端生成的任务关联；普通澄清续接保留同一 task_id |
| agent_type | AgentType | 初始 SUPERVISOR；有决定后镜像目标任务归属，不表示每个时刻正在执行的节点身份 |
| task_type/task_goal | TaskType 或 None / str 或 None | 初始未知或来自待补任务；Supervisor 决定后覆盖 |
| route_decision | RouteDecision 或 None | 本轮结构化路由决定，新一轮清空 |
| pending_task | PendingTask 或 None | 保存待补任务的原目标、实体、缺失字段和问题，直到解决或明确结束 |
| specialist_result | SpecialistResult 或 None | 本轮专业执行结果，下一轮清空 |
| final_answer | str 或 None | 最终回复节点填写，下一轮清空 |
| sources | list[SourceReference] | 本轮允许展示的来源，默认覆盖，下一轮清空 |

除了 messages，其他通道均为默认覆盖。TypedDict 不做运行时完整校验，节点应使用下面的转换函数。
task_id 与 workflow_id/run_id 不混用：一个业务目标可以经过多次澄清 run，审批恢复也可能创建新 run。

### 创建普通新轮次

```python
from app.graph.contracts import ExecutionContext
from app.graph.state import create_turn_state

context = ExecutionContext(
    user_id="user-1",
    conversation_id="conversation-1",
    workflow_id="workflow-1",
    run_id="run-1",
)
turn = create_turn_state(context, "帮我取消订单")
```

create_turn_state 只创建本轮用户消息增量和初始化字段，不加载历史，不认证用户，不访问数据库。
Runtime 从当前会话 Checkpoint 读取待补任务并通过 pending_task 参数传入：

```python
turn = create_turn_state(context, "订单号是 order-1", pending_task=stored_pending_task)
```

该示例中的 stored_pending_task 由调用方从已校验会话读取，不是用户任意指定的记录。
用户/会话/工作流不匹配会被拒绝。未传入待补任务会创建新 task_id，不能以此代替澄清续接。
审批 resume 使用恢复命令和原快照，不能调用 create_turn_state 来重新开始。

## 3. Supervisor 的 RouteDecision

必填 agent_type、task_type、task_goal；可选 entities、needs_clarification、missing_fields、clarification_question。
模型输出不能携带顶层用户身份、权限或任意节点名称，实体只是待业务校验的候选参数。

规则：

- agent_type 必须等于 task_type.target_agent，错误组合拒绝，不静默修正。
- CLARIFICATION 必须 needs_clarification=true；任何需要澄清的决定都必须有缺失字段和问题。
- 不需要澄清时不能同时携带未解决的缺失字段或问题；缺失字段不可重复。
- 已知是取消订单但缺订单号时，保留 ORDER_CANCEL / ORDER，设置 needs_clarification=true。
  路由到 clarification 节点，同时保留原业务目标，而不是把它改成未知任务。
- 未知意图使用 CLARIFICATION / SUPERVISOR，并明确缺失信息；格式非法的模型响应直接验证失败，不能执行副作用。

```python
from app.agents.types import AgentType, TaskType
from app.graph.contracts import RouteDecision

decision = RouteDecision(
    agent_type=AgentType.ORDER,
    task_type=TaskType.ORDER_CANCEL,
    task_goal="取消用户指定的订单",
    needs_clarification=True,
    missing_fields=["order_id"],
    clarification_question="请提供要取消的订单号。",
)
```

SupervisorNode 获取并校验模型输出后，返回 apply_route_decision(state, decision)。
这个函数返回增量更新，不原地修改 State，同时清除旧结果、旧来源和旧 final_answer。

## 4. 主图条件边

```python
from app.graph.router import route_after_supervisor

builder.add_conditional_edges("supervisor", route_after_supervisor)
```

builder 注册 supervisor、clarification、result_aggregator、response 和三个专业目标节点。
函数的 Literal 返回类型限制分支集合；它不调用模型、工具、数据库或子图。
任何 needs_clarification=true 的任务都进入 clarification，其余分别进入对应专业节点。
缺少决定、决定非法或与 State 中镜像字段冲突会抛错；不能直接修改 task_type 后继续用旧决定路由。
应让 SupervisorNode 统一返回 apply_route_decision 的结果。

条件边读取上一个节点返回并合并后的状态，节点与条件边职责可参见
[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)。

专业 wrapper 返回后，`route_after_specialist` 将 needs_input 结果送回 clarification，
其余结果交给 ResultAggregator，再统一进入 ResponseNode。

## 5. 专业输入与私有 State

SpecialistInput 包含 context、task_id、agent_type、task_type、task_goal、entities 和 messages。
context 的四个 ID 只从主图白名单字段构建，不会与 entities 合并；实体不能覆盖调用身份。
所有业务权限和归属仍要由实际服务验证，ExecutionContext 只是结构校验，不是认证结果。

build_specialist_input(state) 只接受可执行专业任务，澄清任务不能进入专业子图。
它从主图历史选择 HumanMessage 和无工具调用的最终 AIMessage，去掉 SystemMessage、ToolMessage、
工具调用消息及附加元数据；重新构造公共消息，复制实体，避免共享可变对象。

SpecialistState 的基础字段为 request、私有 messages、selected_tools 和 result。
create_specialist_state(request) 每次构建独立私有状态；专业子图可在自己的 state.py 扩展必要业务字段。
工具调用与 ToolMessage 可以在这个私有 messages 中配对，不回传全部历史给父图。
selected_tools 当前只是状态槽位，没有实现工具发现、授权或执行。

主图通过 `make_specialist_node(subgraph)` 创建 wrapper。它内部调用以下输入/结果映射函数：

```python
from app.graph.nodes.specialist import make_specialist_node

order_node = make_specialist_node(compiled_order_subgraph)
```

当前 builder 接受 `specialists={"order": ..., "after_sales": ..., "knowledge": ...}` 注入编译图；未注入的目标保持未就绪并明确失败。
此 wrapper 不创建业务节点，也不包含副作用或审批逻辑。
后续接入持久化时还需验证配置传播、中断恢复和当前 run 上下文的刷新，不能从示例推断已经支持恢复。

## 6. 专业结果与回传

SpecialistResult 必填 workflow_id、run_id、task_id、agent_type、task_type、status、summary。
可携带结构化 facts、候选 entities、sources、缺失字段与问题、operation_id、approval_id、error。
对象 JSON 字段限制为 JSON 值，不能放连接对象、模型客户端或完整子图 State。

| status | 约束 |
| --- | --- |
| completed | 订单/售后结果必须有结构化 facts；取消/退款还需要 operation_id，退款还需要 approval_id |
| needs_input | 必须携带 missing_fields 和 clarification_question；保留原任务类型 |
| rejected | summary 解释业务拒绝，不作为程序错误，不携带 error |
| failed | 必须有包含稳定 code 和安全 message 的 error |

完成的 KNOWLEDGE_QA 必须携带来源；SourceReference 包括 document_id、document_version、chunk_id、title 和可选 uri。
引用存在只能证明结构完整，真实性、访问权限、审批有效性和业务执行结果仍须由服务查询核对。
waiting_approval 不属于结果状态：等待审批通过 interrupt 暴露，不能返回一个伪装完成的结果。

apply_specialist_result 检查 workflow、run、task、Agent 和 TaskType 是否对应当前调用。
即使任务相同，也拒绝其他 run 的陈旧结果。未来 resume 结果要使用 Runtime 当前执行上下文，
不能直接把旧快照 request 中的 run_id 当作当前值；这一刷新流程尚待 Runtime 恢复阶段实施。

回传只更新 specialist_result、pending_task、sources、final_answer（置空待最终节点生成）。
不更新身份、消息或路由字段。needs_input 时将候选实体进展合并进 PendingTask，保留原目标和任务 ID。
ClarificationNode 或 ResultAggregator 负责确定 final_answer；ResponseNode 将唯一可展示的 AIMessage 增量写入公共 messages。

## 7. 异常、验证与未实现范围

字段和模型规则错误抛出 Pydantic ValidationError；状态关联错误抛出 GraphProtocolError。
它们是内部错误，后续由 Runtime 转换为安全事件，不能直接把原始错误或输入返回给用户。
Runtime 将 Graph 错误记入服务端日志，并转换为不含内部异常细节的 SSE error 事件。
本次尚未实现权限策略、业务订单状态、预算计数、数据库 Checkpoint 或审批恢复。
预算和订单/退款阶段字段应在对应治理与业务子图接入时扩展，不能把 State 槽位误认为已有执行能力。
HTTP 路由和 SSE 信封也保持原状，不把内部契约当作对外 API。
