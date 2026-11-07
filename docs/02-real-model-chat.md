# 第二步：真实模型对话闭环

状态：待开发。本文是实施计划，文中的目标行为和 SSE 示例尚未实现。

## 1. 目标与范围

实现一条真实调用链：

```text
Apifox → Route → AgentService → AgentRuntime → LangGraph → 模型服务
                   ↑                 ↓
                   └──── 公共 SSE 事件 ┘
```

首版 Graph 使用 `START → ModelNode → END`。先使用一个通用 Agent 配置，
业务场景明确后再扩展类型和条件路由。

本步不实现工具循环、人工审批、工作流暂停恢复、数据库和跨请求消息记忆。
请求中的 workflow_id 暂时只用于关联，不据此声称已创建持久化工作流。

## 2. 开发前需要确定的配置

| 项目 | 配置或决策 |
| --- | --- |
| 模型供应商 | 确认是否支持当前 langchain-openai 适配器；不兼容时再选择对应适配包 |
| 模型名称 | `AGENT_MODEL_NAME`，使用供应商实际开放的名称 |
| API 地址 | `AGENT_MODEL_BASE_URL`，按供应商说明配置；支持默认地址时可以省略 |
| API Key | `AGENT_MODEL_API_KEY`，由本地环境变量或 `.env` 提供 |
| 调用策略 | 明确超时、重试上限、生成长度限制和是否支持流式输出 |

不要求用户把密钥发到聊天中。真实供应商尚未确定，不在文档中预填可调用模型。
如需新增配置字段，同步 Settings、`.env.example` 和运行说明。

## 3. 步骤一：定义 State 和首个 Agent 配置

修改 `app/graph/state.py`、`app/agents/types.py`，在 prompts 包内新增首个 Prompt 模块。

State 先包含 messages、agent_type 以及所需的 user_id、conversation_id、workflow_id、run_id。
每个字段说明来源、读取节点和更新方式：

- messages 使用安装版本支持的消息专用 Reducer，避免把完整历史反复追加。
- 标识与 agent_type 按本次运行初始化，其他字段按实际写入需求添加。
- system prompt 由模型节点组装，避免每次执行都把同一 Prompt 追加进消息历史。
- 不预先加入未使用的审批、工具结果和长期记忆状态。

确认 `add_messages`、消息类型和 StateGraph 的实际签名后实现，不照搬其他版本示例。

## 4. 步骤二：初始化模型与构建 Graph

修改 `app/graph/builder.py`、`app/main.py`，在 `app/graph/nodes` 下新增 ModelNode。
如供应商初始化逻辑需要独立模块，可放在 infrastructure；避免为单个构造调用增加多层包装。

- lifespan 中检查必要配置，创建模型客户端并编译一次 Graph。
- ModelNode 组装 Prompt 与消息，调用异步模型接口，将最终 AIMessage 写回 State。
- builder 接收模型等显式依赖，返回编译后的 Graph，不读取 HTTP 请求或修改全局用户状态。
- Graph 注入 Runtime，由 Runtime 决定执行时传入的初始状态和配置。
- 缺少模型配置时，HTTP 服务仍能启动，保留 `agent_ready=false` 和聊天 HTTP 503。
- 已提供配置但存在本地构建错误时，明确报告原因，不能静默当作成功启动的 Agent。
- `agent_ready=true` 仅表示本地执行组件已初始化，不承诺远程供应商一定可用。
- 不在启动时发送付费探测请求；可关闭的客户端资源在退出时释放。

配置形状可通过本地校验，密钥有效性和远程配额只能在真实调用中确认。

## 5. 步骤三：实现 Runtime 执行与流式事件

修改 `app/runtime/agent_runtime.py`、`app/services/agent_service.py`、
`app/streaming/events.py` 和 `app/streaming/formatter.py`。

Runtime 的同步入口先检查本地就绪状态，再返回异步事件迭代器，保证未就绪错误仍能在开流前返回。
请求级上下文经参数传入，不能存入共享 Runtime 的可变属性。

根据安装版本选择并验证 Graph 流式接口。只转换目标 ModelNode 的文本增量，
过滤空块与内部元数据；最终 AIMessage 不再重复输出成 token。

建议固定本步事件负载：

| 事件 | 本步含义与字段 |
| --- | --- |
| `status` | 开始执行；包含 `status=running` 和关联标识 |
| `token` | 文本增量；包含 `content` 和关联标识 |
| `error` | 已开流后的执行失败；包含稳定 code、安全 message 和关联标识 |
| `done` | 该次执行终止；包含 `status=completed` 或 `failed` 和关联标识 |

关联标识至少包含 run_id、conversation_id、workflow_id。
这些 status 是本次执行的事件状态，本步不持久化工作流生命周期。
正常连接下成功流只发送一次 done；失败流按 error → done(failed) 结束，不再发送完成状态。
客户端已经断开时不保证能送达终止事件。

以下为计划中的成功帧示例，实际模型可能采用不同的文本分块方式：

```text
event: token
data: {"run_id":"run-1","conversation_id":"conversation-1","workflow_id":"workflow-1","content":"你好"}

event: done
data: {"run_id":"run-1","conversation_id":"conversation-1","workflow_id":"workflow-1","status":"completed"}

```

HTTP Schema、Runtime 事件模型和文档同时更新，LangGraph 内部对象不直接序列化给调用方。

## 6. 步骤四：错误、取消和日志

- 请求校验和本地未就绪问题发生在开流前，保留 HTTP 422/503。
- 开流后供应商拒绝、超时、限流或内部失败映射为稳定错误码，保留已发送文本并明确失败终止。
- 对外消息不包含 API Key、数据库连接串、原始响应凭据或堆栈；详细原因写入受控日志。
- 日志包含 user_id、conversation_id、workflow_id、run_id、执行耗时及可获得的 Token 用量。
  流式供应商未返回用量时记录未知，不伪造数值。
- 连接断开时让取消沿调用链传播，关闭异步迭代器及底层可关闭资源。
  不能吞掉取消异常后继续生成；不承诺已经提交给供应商的请求一定不计费。
- 检查实际 SDK 与 Graph 对取消的支持，并用测试验证清理，不能只依赖 SSE 心跳推断完成。

## 7. 步骤五：自动验证与 Apifox 联调

默认测试使用可控模型替身，不需要联网或真实密钥。至少覆盖：

1. 缺少配置仍可启动，对话返回 HTTP 503。
2. 真实 Graph 配合可控模型产生正确最终消息与 SSE 增量，最终结果没有重复输出。
3. 两个并发请求使用不同 run_id，用户上下文和文本没有交叉。
4. 供应商异常、部分文本之后失败、超时的终止事件符合协议。
5. 取消请求后生成器和可关闭资源执行清理。

按开发规范执行依赖、测试及代码检查，再显式使用真实配置做一次人工联调：

1. 启动 Uvicorn，确认 `/health` 中 agent_ready 为 true。
2. Apifox 使用 `POST /agent/chat`，请求体沿用第一步文档，Accept 设置为 `text/event-stream`。
3. 确认增量逐步到达，并以唯一 done(completed) 结束。
4. 换用户与会话再请求一次，确认没有历史消息混入。
5. 另行验证错误配置和中断连接，核对日志关联及清理行为。

自动测试和真实模型验证分别记录；缺少真实配置时明确标记人工联调未完成。

## 8. 完成标准与后续安排

- 从 HTTP 到真实模型的执行闭环可用，使用应用启动时编译的 Graph。
- SSE 增量、终止和错误行为有明确协议及测试。
- 并发上下文隔离与断开清理有实际验证。
- 更新 README、architecture、配置示例和本阶段记录，写明供应商兼容性及验证限制。

完成后进入工具循环与治理，再实现 Checkpointer、工作流与审批、Store 和长期记忆。
本阶段未接入 Checkpointer，因此复用 conversation_id 不会自动获得跨请求对话历史。
