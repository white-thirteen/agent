# 当前架构与开发边界

开发规范见 [AGENTS.md](../AGENTS.md)。已完成的搭建步骤见
[第一步：开发环境与项目骨架](01-environment-and-scaffold.md)，下一阶段的实施细节见
[第二步：真实模型对话闭环](02-real-model-chat.md)。

## 已实现

- `app/main.py`：应用工厂、生命周期、服务实例和存活检查。
- `app/core`：环境配置、日志和统一的未就绪错误。
- `app/api`：参数校验、HTTP 接口、依赖注入；不包含 Graph 执行逻辑。
- `app/services`：为每次请求创建不可变上下文及独立 `run_id`，适配运行时事件。
- `app/runtime`：执行边界，目前明确拒绝未实现的 Agent 请求。
- `app/streaming`：公共事件信封及 JSON 序列化，SSE 帧由 sse-starlette 生成。

调用方向：Route → Service → Runtime → Graph（待实现）。Runtime 不依赖 HTTP Schema，
单例 Service 和 Runtime 不保存用户的可变执行状态。Graph 将在应用启动时编译一次。

当前 `agent_ready` 固定为 false，`POST /agent/chat` 在发送 SSE 响应头之前返回 HTTP 503。
没有模拟模型输出，也没有注册空的暂停、恢复或查询接口。

## 预留模块

`graph`、`agents`、`tools`、`workflows`、`memory`、`infrastructure` 已建包和职责说明，
尚未实现对应业务。不要将这些文件的存在理解为能力已经完成。

计划使用 PostgreSQL 驱动和 LangGraph PostgreSQL 扩展，数据库资源由应用生命周期管理。
Checkpoint 保存 Graph 执行快照，Store 保存跨会话记忆，Workflow Repository 保存业务元数据；
这三种职责独立。当前没有创建数据库连接或表。

## 下一阶段：真实模型对话闭环

第一步确认模型供应商、模型名、Base URL 及密钥配置；密钥只放本机 `.env`。

开发顺序：

1. 实现 `AgentState`，使用消息专用 Reducer，明确每次运行字段的覆盖策略。
2. 定义首个通用 Agent 配置和 Prompt；业务场景明确前不引入复杂分类路由。
3. 实现异步 ModelNode 和最小 Graph：START → ModelNode → END。
4. 在应用启动时初始化模型、构建 Graph，注入 Runtime；配置缺失时保留未就绪状态。
5. 将真实文本增量映射为 `token`，补齐状态、完成及流式错误事件。
6. 验证 Apifox SSE、两次独立请求、模型错误和连接断开后的资源清理。

验收结果是一次真实请求能够通过 Route → Service → Runtime → Graph → LLM 并返回 SSE，
且不同用户请求互不串线。该阶段先验证单次执行，不声称具备跨请求对话记忆。

之后再依次实现工具循环与治理、持久化和工作流审批、跨会话长期记忆。
`thread_id` 及 workflow 映射、同一会话并发约束和重启恢复需要在持久化阶段一起验证。
