# 第一步：开发环境与项目骨架

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：原环境与 HTTP 骨架已完成；电商多 Agent 方案的基础设施增补尚待实施。
第 1～8 节保留 2026-11-07 的搭建记录，第 9 节记录新方案评估。
当前实现以实际代码和验证记录为准，后续阶段见 [整体执行路线图](../development-roadmap.md)。

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

预留业务模块不包含实现。具体职责和依赖方向见 [根目录开发规范](../../AGENTS.md)。

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

本节为历史搭建记录；当前执行顺序见 [整体执行路线图](../development-roadmap.md)。

## 9. 电商多 Agent 新方案下需要补充什么

### 9.1 可以保留的基础

Python 3.13.7、现有依赖、FastAPI 生命周期和 Route/Service/Runtime 分层适合继续扩展，
不需要重建项目或重装全部依赖。当前没有业务图和数据库映射，调整设计不会涉及既有业务数据迁移。
01 的原始验收只证明 HTTP 和 SSE 基础边界可用，不证明电商基础设施已齐备。

### 9.2 补充清单及接入时点

| 补充内容 | 当前缺口 | 实施时点 |
| --- | --- | --- |
| 多层 Graph 组织 | 只有简单 State 和空 builder；没有主图/专业/业务子图 | 02.1/02.2 |
| 领域服务层 | 尚无订单、售后、支付服务或业务数据 | 工具与订单查询开发之前 |
| 执行与订阅分离 | 当前仅是 HTTP 迭代器接 Runtime，未具备独立执行任务 | 02.3，任何业务写操作之前 |
| PostgreSQL 开发环境 | 仅有驱动，没有 Compose、数据库、Schema 和连接池生命周期 | 03 基础设施阶段 |
| Checkpointer 与工作流元数据 | 尚无配置、初始化、会话映射、活动工作流约束及恢复核对 | 审批业务之前；会话连续性接入时同步落实 |
| 工具策略与 Domain Service 校验 | 只有占位文件，没有权限/预算/幂等执行链 | 首个业务工具之前 |
| 审批入口 | 暂无审批路由和可信审批角色上下文 | 退款业务之前 |
| SSE 协议扩展 | 无暂停/恢复事件，缺业务关联及时间戳信封 | 02.3；同步迁移 Schema、Formatter 和测试 |
| 知识库 Pipeline/VectorStore | 目录、集成包、Embedding 与索引尚无 | KnowledgeAgent RAG 之前 |
| 长期记忆 Store | 已装相关扩展但无存储或读写策略 | 业务闭环后按需接入 |

本轮只记录这些补充项，没有创建新业务目录、安装向量依赖、生成 Compose 或启动数据库。
当前架构约束、环节划分与依赖顺序见 [整体执行路线图](../development-roadmap.md)。

### 9.3 后续环境补充的验收方式

- Compose 能在干净机器启动固定版本数据库，健康检查和持久卷有效；测试库与开发数据隔离。
- 连接池、Checkpointer 和 Store 有明确 startup/setup/close，不能在每次 HTTP 请求重复建表。
- 业务 Schema 与 LangGraph Schema 的初始化和升级可重复执行，不能依赖手工点击创建。
- 关键配置有缺省/缺失行为和示例，凭据不提交；向量维度与 Embedding 模型一致。
- 新增基础设施不破坏无模型/数据库配置时现有 HTTP 开发启动方式；业务能力按实际依赖报告未就绪。
- 这些验收尚未执行；第 8 节的历史通过结果不能用于声称新增环境已经完成。
