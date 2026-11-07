# 第一步：开发环境与项目骨架

状态：已完成。本文记录 2026-11-07 的搭建结果，后续变化以实际代码和架构文档为准。

## 1. 本步目标

建立能够启动、检查和继续开发的 Python 后端工程，打通 HTTP 到 Runtime 的调用边界。
本步不要求模型、数据库或 Java 服务可用。

完成的基础链路：

```text
HTTP 请求 → 参数校验 → AgentService → AgentRuntime
                                         └─ 当前返回 agent_not_ready

后续 Runtime 事件 → StreamEvent → JSON 数据字段 → SSE 响应
```

## 2. 环境准备与依赖安装

项目使用 Windows / PowerShell，Python 解释器为 `.venv/Scripts/python.exe`，版本为 3.13.7。
准备阶段检查过 Python 3.15，在仅使用预编译包的安装检查中，
`uvicorn[standard]` 的 PyYAML 依赖无可用包，因此采用本机已有的 Python 3.13。

当前依赖已安装。需要在新的开发环境重建时，在项目根目录执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

仅在新建或有意重建环境时执行第一行，不要用它覆盖正在使用的环境。
`requirements.in` 是直接依赖清单，`requirements.txt` 是当前已验证环境的固定版本快照。

| 用途 | 直接依赖 |
| --- | --- |
| Web 与 SSE | fastapi、uvicorn[standard]、sse-starlette |
| Agent 与模型适配 | langchain、langgraph、langchain-openai |
| 配置 | pydantic-settings |
| 持久化驱动 | psycopg[binary,pool]、langgraph-checkpoint-postgres |
| HTTP 调用及测试 | httpx |
| 测试及代码检查 | pytest、pytest-asyncio、ruff |

安装数据库驱动不代表 PostgreSQL 服务已经配置；安装模型适配器也不代表真实模型可调用。

## 3. 建立模块骨架

- `api/routes` 与 `api/schemas`：HTTP 接口、依赖注入与请求模型。
- `core`：配置、日志和领域错误到 HTTP 响应的基础边界。
- `services`、`runtime`：创建运行上下文及执行入口。
- `streaming`：公共事件信封、JSON 数据序列化，交给 sse-starlette 生成帧。
- `graph`、`agents`、`tools`、`workflows`、`memory`、`infrastructure`：创建包及职责说明。
- `tests`、`docs`：行为验证和设计记录。

预留业务模块不包含实现。具体职责和依赖方向见 [根目录开发规范](../AGENTS.md)。

## 4. 配置与生命周期

`app/core/config.py` 使用 `AGENT_` 前缀，从环境变量和项目根目录 `.env` 读取配置。
模型密钥及数据库连接配置使用 SecretStr，避免在普通对象展示中暴露；仍不能主动记录其原文。

首次需要本地配置时，在不存在 `.env` 的情况下复制示例：

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

当前应用使用默认配置即可启动。模型和数据库字段是预留项，仅填写这些字段不会开启 Agent。

`create_app()` 创建 FastAPI；lifespan 启动时配置日志并创建 Runtime 和 Service。
当前没有数据库或模型连接需要关闭；后续引入资源时，统一在 lifespan 初始化和释放。

## 5. HTTP、Service 与 Runtime

| 接口 | 当前结果 |
| --- | --- |
| `GET /health` | HTTP 200，`status=ok`，`agent_ready=false` |
| `GET /docs` | Swagger 接口文档 |
| `GET /openapi.json` | OpenAPI 定义 |
| `POST /agent/chat`，合法参数 | HTTP 503，`error.code=agent_not_ready` |
| `POST /agent/chat`，非法参数 | HTTP 422 |

请求需要 user_id、conversation_id、workflow_id 和 message。
标识字段长度为 1～128，message 长度为 1～32000，纯空白内容及额外字段会被拒绝。
这些标识目前仅作为开发上下文，不代表已完成身份认证、工作流创建或归属校验。

Service 每次创建不可变 AgentContext 和独立 run_id，不将用户信息保存到单例属性中。
Runtime 当前在创建 SSE 响应前抛出 AgentNotReadyError，由应用转换为 HTTP 503。
工作流查询、暂停和恢复接口尚未注册。

## 6. SSE 基础设施

StreamEvent 限定公共事件名并携带 data 字典。Formatter 使用 JSON 编码，
保留中文并转义消息中的换行，再由 EventSourceResponse 负责 SSE 格式与心跳。

当前测试通过 Runtime 替身验证 `token` 和 `done` 帧，不会在实际应用中生成测试回复。
真实模型事件映射、开流后的错误协议及断开清理在下一阶段实现。

## 7. 本地启动与人工检查

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000/health> 和 <http://127.0.0.1:8000/docs>。
向 `/agent/chat` 提交以下 JSON，当前预期为 HTTP 503：

```json
{
  "user_id": "dev-user",
  "conversation_id": "conversation-1",
  "workflow_id": "workflow-1",
  "message": "你好"
}
```

## 8. 已完成验证与边界

骨架交付时已执行 pip check、pytest、Ruff 检查和格式检查，结果均通过。
pytest 共 7 项：健康检查与 OpenAPI、未就绪响应、3 种非法消息、
额外字段拒绝，以及 SSE 内容保真和两次请求的运行上下文隔离。
这组隔离验证是顺序请求，不作为并发安全验证的替代。

另已启动真实 Uvicorn 进程，检查健康接口、文档、OpenAPI 和未就绪响应，完成后关闭验证进程。
未调用真实模型、未连接 PostgreSQL、未验证持久化或应用重启后的执行恢复。

下一步见 [第二步：真实模型对话闭环](02-real-model-chat.md)。
