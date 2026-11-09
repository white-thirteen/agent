# 01 基础工程与运行环境：完整详细设计

D01及六阶段详细设计已获最终确认，实施待独立授权。依据为README和AGENTS的“逻辑设计阶段正式收尾记录”。本文接口及验收均为未来实施标准。

初版日期为2026-11-08，最近修订日期为2026-11-09。依据：[项目定位与 V1 范围](agent-engine-demo-plan.md)、[六阶段路线图](development-roadmap.md)、[开发规范](../AGENTS.md)。本文细化新 01 阶段，不替代整体路线图，也不采用历史阶段的审核状态。

历史轮次说明（保留追溯，当前状态以页首和末尾最新记录为准）。本轮仅修订本文件中模型/运行预算、管理认证延期、演示身份环境边界及请求解析/关联标识四项内容，不重新审核整体方案或检查开发进度。未修改其他文档、业务代码、依赖、配置或数据库，未执行测试、代码检查、迁移、容器操作或模型联调。下文 API、DDL、参数和命令均为未来设计，不表示已经实现。

阅读导航：[阶段边界](#1-阶段目标与边界) → [统一方案与接口](#3-共用技术方案) → [1.1 工程与配置](#4-11-工程与配置) → [1.2 PostgreSQL](#5-12-postgresql) → [1.3 模型与身份](#6-13-模型与身份) → [依赖与顺序](#7-依赖关系与推荐开发顺序) → [交付与验收](#8-阶段整体交付物与验收标准未来执行) → [02 衔接](#9-与-02-agentruntime-阶段的衔接) → [决策分类与确认状态](#10-技术决策分类与确认状态)。

## 1. 阶段目标与边界

交付一个可复现、资源生命周期明确的单 FastAPI 工程：无外部配置能检查 HTTP 存活；配置后能连接真实 PostgreSQL 和一个真实聊天模型；受控演示身份可稳定绑定会话线程，为 02 的 Runtime 和 04 的持久恢复提供基础。

沿用路线图的 3 个二级环节、6 个三级 Task，不另建平行任务体系。六阶段设计已获最终确认，实际开发仍待独立授权；本阶段设计修订不授权任何 Task 实施。届时按用户确认的 Task 顺序与范围执行，并记录结果和遗留项。

| 二级环节 | Task | 本阶段交付 | 明确后继边界 |
| --- | --- | --- | --- |
| 1.1 复用工程与配置收敛 | 1.1.1、1.1.2 | 事实基线、配置、存活/资源状态、启动说明 | 不调整路由决策与专业角色 |
| 1.2 PostgreSQL 资源与最小迁移 | 1.2.1、1.2.2 | Compose、独立测试库、迁移、池、sessions 仓储 | 不创建订单/退款/审批/向量表，不接持久 Saver/Store |
| 1.3 模型入口与演示身份 | 1.3.1、1.3.2 | ModelGateway、模型调用限制、Run 预算契约、DemoContext、普通演示身份与用户隔离 | 02 落实 Runtime 预算与网关接线；03 Executor 统计工具次数；04提供本地审批Actor和入口，真实认证延期 |

01负责最终请求Schema、身份、session和准备接口，不创建正式Task或调用旧Graph。02实施旧Graph执行侧迁移、AfterSales到Refund、Task生命周期、SSE与互斥。订单、退款、持久恢复、RAG和Store按后继阶段接入。

01负责普通DemoIdentity、演示用户及会话准备。V1管理员认证正式延期，01和04均不实现管理key/Header/compare_digest或RBAC。04仅提供本地审批ActorProvider审计接入，development/test回环演示，production禁用，普通chat不能提交审批决定。未来真实认证沿04的ActorProvider边界扩展。

## 2. 既有代码事实与复用决定

以下沿用上一轮定向静态阅读结果，不是本轮运行验证或最新开发进度审计。已有工作区修改与历史文档移动全部保留；未来实施只核对授权 Task 涉及的增量，不重置工作区。

| 当前事实 | 证据 | 01 处理 |
| --- | --- | --- |
| Python 基线 3.13.7；已有固定依赖和 Ruff/pytest 配置 | `.venv/pyvenv.cfg`、`requirements.in/txt`、`pyproject.toml` | 沿用 `.venv`，不重建框架、不批量升级依赖 |
| FastAPI factory/lifespan 装配 Service/Runtime，模型齐全时编译图 | `app/main.py` | 保留装配点，增加基础资源生命周期 |
| `SecretStr` 已用于模型密钥和数据库 URL | `app/core/config.py` | 扩展最小设置，避免秘密与原始配置错误回显 |
| `.env.example` 将模型项标为未消费，但代码已消费 | `.env.example`、`app/main.py` | 1.1.2 修正文案并区分当前生效与后续设置 |
| HTTP 开流前检查 graph 是否存在；该判断不检测真实模型 | `api/routes/agent.py`、`runtime/agent_runtime.py` | 保留安全错误边界，拆开配置/初始化与连通验证含义 |
| 当前模型直接由 lifespan 创建，Supervisor 内直接 `ainvoke` | `main.py`、`graph/nodes/supervisor.py` | 1.3.1 提供统一入口；02 完成节点迁移，不伪称本阶段全链路已治理 |
| Runtime 以 user/conversation 的 uuid5 计算 thread，Saver 在 builder 内创建 | `runtime/agent_runtime.py`、`graph/builder.py` | 1.2/1.3 接入持久会话绑定；保留内存 Saver，04 再迁移持久快照 |
| `AgentContext` 已是不可变逐 run 对象；Service 生成 run_id | `runtime/agent_runtime.py`、`services/agent_service.py` | 演进为 DemoContext，沿用 run_id 所属层，不保留两套等义上下文 |
| ChatRequest 必填 user/conversation/workflow/message | `api/schemas/chat.py` | 旧字段仅作既有事实记录；01定义最终请求与准备接口，02接通正式Task后的Graph执行，旧workflow字段422 |
| PostgreSQL、Checkpoint、Store 均仅占位；未发现 Compose/迁移/session 实现 | `app/infrastructure/`、仓库文件清单 | 只实现当前所需的池、迁移与会话仓储 |
| HTTP、类型、State、Graph 协议已有测试 | `tests/` | 后续复用受影响用例，按风险补最少测试；本轮不运行 |

上一轮已定向阅读 [Graph 协议](graph-protocol.md)、builder、Supervisor 与 Runtime；本轮据此明确衔接，不重复读取实现，不沿用其中旧角色和 workflow 字段作为未来目标设计。

本地依赖清单含 `langchain-openai==1.7.4`、`psycopg==3.3.8`、`psycopg-pool==3.3.3`。静态源码可见异步池的 `open/wait/close`，以及聊天模型的 `bind_tools`、`with_structured_output`、timeout/max_retries 设置。这里只确认接口存在；具体组合仍需实施时用项目解释器验证，不据此宣称兼容性或真实连通通过。

## 3. 共用技术方案

### 3.1 生命周期与就绪语义

继续采用 `Route → Service → Runtime → Graph`。池、模型客户端和 Graph 在 lifespan 创建/关闭，请求只传不可变关联上下文；连接对象、网关和池不进入可持久化 State。

01启动顺序为配置校验 → 数据库池及版本检查 → 模型客户端/网关 → 会话仓储与Service准备接口 → HTTP存活及准备层就绪。旧Graph的正式执行接线由02在Task关联完成后启用，01不以资源就绪宣称chat执行已验收。退出反序释放，部分初始化失败清理已有资源，启动不默认探测模型网络。

| 情况 | 计划行为 |
| --- | --- |
| 无数据库、无模型配置 | HTTP 与 `/docs`、`/health` 可用；chat 在开流前 503 |
| 模型配置完整、数据库未配置或未就绪 | 允许创建模型客户端/图，显式模型连通检查可独立执行；接入演示身份后 chat 因缺少持久会话绑定而 503，不退回静默内存绑定 |
| 数据库配置存在但连接失败、迁移缺失 | 有界等待后标记数据库未就绪，释放失败池，HTTP 保持存活；依赖数据库的请求开流前 503；修复并显式迁移后重启，不启动后台无限重连服务 |
| 数据库可用、模型未配置 | 会话资源可初始化，chat 仍 503；不返回模型替身 |
| `app_env=production` | 禁止启用演示身份，chat 开流前拒绝；仅保留 HTTP 存活与资源状态，不自动改用未实现的真实认证 |
| 配置值格式非法 | 使用隐藏输入值的安全配置错误停止启动，不吞掉编程错误，也不输出密钥/DSN |
| 模型凭据错误或网络失败 | 初始化标记不代表连通；显式检查报告安全错误，实际图调用仍由执行边界处理 |

保留 `/health` 的 `status/service/agent_ready` 字段，增加最少资源状态：`database_status` 为 `not_configured/unavailable/ready`，`model_status` 为 `not_configured/initialized`。`agent_ready` 在 1.3.2 接线后表示环境允许演示身份，且当前聊天入口所需的图和持久会话资源均已初始化；production 恒为 false。它不代表真实模型请求成功，也不代表三个专业 Agent 就绪。1.1.2 先记录现有 graph 判断，后续接线时同步改变说明与相关测试。

数据库 `ready` 只在实际连接和本阶段迁移版本检查通过后设置；启动状态不是持续健康探测，运行中连接失败仍需转换为安全请求错误。真实模型检查单独记录供应商、模型、时间、结果，不在 health 请求里产生费用，不公开 URL、用户列表或密钥。不新增整套监控服务。

### 3.2 设置提案

所有设置集中在 `app/core/config.py`，环境变量使用 `AGENT_` 前缀；下表数值是本设计建议默认值，尚未应用。

| 设置字段 | 建议值/约束 | 职责 |
| --- | --- | --- |
| `app_name` | `Agent Engine Demo` | 与项目定位一致 |
| `model_name/model_base_url/model_api_key` | 继续已有字段；API key 为 SecretStr；不设虚构模型名 | 沿用现有 OpenAI 兼容适配；具体供应商/模型在真实联调前确认 |
| `database_url` | 可选 SecretStr | 开发业务库；不记录原文 |
| `test_database_url` | 可选 SecretStr；真实 PG 用例显式提供 | 独立测试库，不从开发 URL 自动推导 |
| `database_pool_min_size/max_size` | 1 / 5 | 单 worker 小连接池；校验上下界 |
| `database_connect_timeout_seconds` | 5 秒 | 单次连接/池获取等待限制 |
| `database_startup_timeout_seconds` | 10 秒 | 总启动等候上限 |
| `model_timeout_seconds` | 30 秒 | ModelCallLimits 的单次模型尝试超时 |
| `model_max_attempts` | 8 | ModelCallLimits 的同一逻辑任务累计模型尝试次数上限，含失败与重试 |
| `model_max_retries` | 1 | ModelCallLimits 的单次 Gateway 调用额外重试上限，仍受任务累计模型尝试次数限制 |
| `run_timeout_seconds` | 120 秒 | RunLimits 的同一逻辑任务累计主动执行时长，02 由 Runtime 管理，非 Gateway 配置 |
| `run_max_tool_calls` | 12 | RunLimits 的同一逻辑任务累计工具次数上限，03 由 ToolExecutor 检查并统计，Runtime 汇总 |
| `app_env` | 保留 development/test/production | 仅 development/test 允许演示身份，production 禁用，无绕过开关 |
| `demo_user_ids` | `['dev-user', 'demo-user-b']`，环境示例使用 JSON 数组 | 固定受控身份集合；不含审批权限 |

类型约定：名称/base URL 为 `str | None`，模型密钥/数据库 URL 为 `SecretStr | None`；池大小/次数/重试为 int，超时为 float，演示名单为 `tuple[str, ...]`。超时与次数必须大于零，重试可为零，池满足 `1 <= min_size <= max_size`，名单去空、去重后不得为空。保留现有 app_env/debug/log_level；环境变量名由字段名大写并加 `AGENT_` 构成。base URL 只接受 HTTP(S) 且不含 userinfo/查询秘密；不把整段 URL 当日志标签。

Settings 只负责解析以上两组配置：构造 ModelGateway 时只传 ModelCallLimits，02 构造 Runtime 时才传 RunLimits。工具次数与运行时长不进入 Gateway 的构造参数、调用参数或返回值。01 只定义 RunLimits/RunUsage 的数据契约，不提前实现 Runtime 预算调度。演示名单只用于 development/test 受控模拟，不是真实认证，不能直接作为公网部署身份验证方案；不引入 JWT、OAuth 或完整 RBAC。

本阶段不配置 Embedding 维度、检索阈值、退款规则或审批超时；按 04/05 的实际设计补充。无需删除当前依赖，不为目录整齐引入 ORM、Alembic、任务队列或新 provider SDK。

### 3.3 PostgreSQL 与迁移

提出使用 PostgreSQL 17 主版本作为本地基线；实施时固定验证过的镜像 tag/digest，记录实际 `server_version`，不使用 `latest`。这是待审核选型，不是已拉取或已验证版本。pgvector 扩展/镜像的具体版本在 05 评估，本阶段不创建向量表；届时保持 PostgreSQL 主版本与数据卷升级约束，不直接拿不同主版本复用旧卷。

一个 PostgreSQL 服务、两个独立库：`agent_demo` 与 `agent_demo_test`，仅绑定 `127.0.0.1`，具名数据卷持久保存，Compose healthcheck 用数据库自身就绪检查。端口/账号/密码由本地环境注入，仓库只有占位说明。FastAPI 在 Windows 本机运行；数据库容器不扩展为微服务架构。

提供显式初始化脚本，为首次和已有数据卷幂等创建两个库；不只依赖容器首次启动的 init 目录。创建库与表迁移分开，普通应用启动不创建数据库、不自动迁移。允许本地初始化使用高权限凭据，日常应用使用专用非超级用户；不实现复杂角色/RLS 平台。数据库用户的初始化凭据和应用 DSN 不输出到日志。

建议文件：`compose.yaml`、`scripts/init_databases.py`、`scripts/migrate.py`、`migrations/001_sessions.sql`、`app/infrastructure/postgres.py`、`app/infrastructure/sessions.py`。脚本均从项目根目录使用 `.venv` 解释器执行。

迁移机制保持小而显式：

1. 编号 SQL 按序执行，`schema_migrations(version, checksum, applied_at)` 记录成功版本；首个迁移创建 sessions。已应用文件不得修改，修正用新编号。
2. 每份 SQL 与版本登记在同一事务中，失败回滚；重跑已完成版本无副作用，checksum 改变或数据库含未知更高版本时拒绝继续。用一个事务级数据库锁串行化迁移入口。
3. 只支持当前所需的事务性 DDL，不做通用迁移框架、自动降级或破坏性清库。未来库自带的 Saver/Store setup 在 04/05 单独管理，不冒充业务迁移。
4. 测试模式要求显式测试 URL，并核对实际目标库名为 `agent_demo_test`，拒绝开发库；测试不执行 DROP DATABASE/清卷。按用例回滚或只清理本次创建的数据。

sessions 最小 DDL 契约如下，SQL 只作为设计示意，授权 Task 中才写入迁移文件并执行：

| 字段/约束 | 方案 |
| --- | --- |
| `user_id` | text，非空，长度 1–128，与 API 标识约束一致 |
| `conversation_id` | text，非空，长度 1–128 |
| `thread_id` | UUID，非空，全局唯一 |
| `created_at` | timestamptz，服务端默认时间 |
| 主键 | `(user_id, conversation_id)` |

```sql
CREATE TABLE sessions (
    user_id text NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    conversation_id text NOT NULL
        CHECK (char_length(conversation_id) BETWEEN 1 AND 128),
    thread_id uuid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, conversation_id)
);
```

同一会话字符串可由两个受控用户分别使用，各有自己的 thread；所有仓储查询必须带 user_id。thread 由服务端生成，不接受 HTTP 或模型指定。首次采用现有 `[user_id, conversation_id]` JSON→uuid5 算法作为候选 thread 并保存，避免无必要改变现有进程内线程；之后以数据库已存值为准，Runtime 不再自行计算。并发创建通过主键冲突处理后读取既有绑定，唯一约束保证结果一致。

不增加 workflows/users/active-run 表、updated_at 触碰逻辑或消息副本。会话绑定不是 Checkpoint；01 重启后绑定存在不代表图历史存在。

### 3.4 职责归属与阶段内接口

三个二级环节按“契约 → 资源实现 → 请求接线”分工，避免各建一套配置、上下文或资源管理器。

| 能力 | 定义/实现负责方 | 使用方 | 不承担的职责 |
| --- | --- | --- | --- |
| Settings、错误码、health 语义 | 1.1.2 | 1.2/1.3 和 main | 不负责建库、模型探测、业务决策 |
| Compose、建库、应用迁移 | 1.2.1 | 开发者显式运行；启动只读版本 | 不由 lifespan 自动执行 DDL |
| 异步池、SessionRepository | 1.2.2 | lifespan、Service | 不验证 HTTP 身份，不创建 run，不拥有 Graph |
| ModelGateway、模型客户端、ModelCallLimits/ModelCallUsage | 1.3.1 | 02 Supervisor、03 专业图 | 不管理 Run 时长/工具次数，不过滤权限或执行 handler |
| RunLimits/RunUsage 契约 | 1.3.1 定义；02 Runtime 使用；03 Executor 更新工具次数 | Runtime、ToolExecutor | 不增加全局可变计数器或并发预算服务 |
| DemoIdentity、DemoContext | 1.3.2 | API、Service、Runtime | 只用于 development/test，不实现管理认证或赋予审批权限 |
| 应用装配与释放 | main/lifespan；各 Task 增量接线 | API 与 Service | 不再新增一套 DI 容器或通用资源平台 |

跨模块使用具体小类和函数；不为单个实现引入 Repository/Gateway 抽象基类、插件接口或通用工厂注册表。测试通过注入受控对象实现替换，不将替身接入正式运行模式。

### 3.5 统一数据结构与函数签名

以下为接口设计，不是待直接粘贴的完整实现。配置输入用现有 Pydantic Settings；上下文使用 frozen dataclass；用量快照用可 JSON 序列化的普通字段。相同字段不在每层重复转换和深拷贝。

```python
# app/infrastructure/sessions.py
@dataclass(frozen=True, slots=True)
class SessionBinding:
    user_id: str
    conversation_id: str
    thread_id: UUID
    created_at: datetime

class SessionRepository:
    def __init__(self, pool: AsyncConnectionPool): ...
    async def get(self, *, user_id: str,
                  conversation_id: str) -> SessionBinding | None: ...
    async def get_or_create(self, *, user_id: str,
                            conversation_id: str) -> SessionBinding: ...

# app/runtime/context.py
@dataclass(frozen=True, slots=True)
class DemoIdentity:
    user_id: str
    permission_scopes: frozenset[str]

@dataclass(frozen=True, slots=True)
class DemoContext:
    user_id: str
    conversation_id: str
    thread_id: str
    run_id: str            # Service准备的候选值，02受理新执行后才成为有效Run
    message: str
    permission_scopes: frozenset[str]

@dataclass(frozen=True, slots=True)
class SubmitOptions:
    input_mode: Literal['auto', 'new_task'] = 'auto'
    request_id: UUID | None = None

# app/services/agent_service.py
class AgentService:
    def __init__(self, runtime: AgentRuntime,
                 sessions: SessionRepository | None): ...
    async def prepare_chat(self, *, identity: DemoIdentity,
                           conversation_id: str,
                           message: str, input_mode: Literal['auto', 'new_task'] = 'auto',
                            request_id: UUID | None = None
                            ) -> tuple[DemoContext, SubmitOptions]: ...
    async def submit_chat(self, context: DemoContext, *, options: SubmitOptions,
                          subscription_owner: SubscriptionOwner) -> RunHandle: ...
    def stream_chat(self, handle: RunHandle
                    ) -> AsyncIterator[dict[str, str]]: ...
```

`prepare_chat` 只准备数据，先检查基础资源、读取 session，再返回 DemoContext 与 SubmitOptions 二元组。DemoContext 保存身份、会话、权限、消息及候选 run_id，不保存 input_mode/request_id，也不包含尚未创建的 task_id/workflow_id。SubmitOptions 由 Service 根据已校验参数构造，定义唯一放在 app/runtime/context.py，02 直接复用。候选 run_id 不代表执行已经受理。

submit_chat/stream_chat 的签名是交给 02 的最终接线契约，01 不实施执行入口。02 中 submit_chat 显式转调 Runtime.submit(context, options=options, subscription_owner=subscription_owner)，stream_chat 只消费已受理 RunHandle 的订阅并格式化事件。Route 的请求级 SubscriptionOwner 沿 02 规则负责异常清理。01 仅验收准备层，不把上下文直接送入旧 Graph，不新建正式 Task 或临时 workflow。

```python
# app/runtime/model_gateway.py
@dataclass(frozen=True, slots=True)
class ModelCallLimits:
    max_attempts: int       # 同一逻辑任务累计，包含重试
    timeout_seconds: float
    max_retries: int        # 单次 Gateway 调用的额外重试次数

@dataclass(frozen=True, slots=True)
class ModelCallUsage:
    model_attempts: int = 0  # 归属 task_id；仅创建全新逻辑任务时初始化为零

# app/runtime/agent_runtime.py（01 只定义数据契约，02 落实执行预算）
# 这两个结构不传给 Gateway，不为它们另建预算管理包。
@dataclass(frozen=True, slots=True)
class RunLimits:
    active_timeout_seconds: float  # 同一逻辑任务生命周期内累计
    max_tool_calls: int            # 同一逻辑任务生命周期内累计

@dataclass(frozen=True, slots=True)
class RunUsage:
    # 归属 task_id；跨 run_id 继承，不能按执行次数重新初始化
    tool_calls: int = 0
    active_elapsed_ms: int = 0

# app/runtime/model_gateway.py（续）
@dataclass(frozen=True, slots=True)
class ModelCallContext:
    run_id: str   # 一次具体执行；每次恢复可以产生新值
    task_id: str  # 逻辑任务；暂停、澄清、审批与恢复期间稳定
    agent_type: AgentType

@dataclass(frozen=True, slots=True)
class UsageReport:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    status: Literal['known', 'estimated', 'unknown']
    estimation_method: str | None = None

@dataclass(frozen=True, slots=True)
class ModelCallResult:
    message: AIMessage            # 保留原生 tool_calls、call_id
    parsed: BaseModel | None      # 普通调用为 None
    usage: UsageReport
    model_usage: ModelCallUsage

class ModelGateway:
    def __init__(self, model, limits: ModelCallLimits): ...
    async def invoke(self, messages, *, context: ModelCallContext,
                     model_usage: ModelCallUsage,
                     tools: Sequence[BaseTool | dict] = ()) -> ModelCallResult: ...
    async def invoke_structured(self, messages, *, schema: type[BaseModel],
                                context: ModelCallContext,
                                model_usage: ModelCallUsage) -> ModelCallResult: ...

class ModelCallError(RuntimeError):
    code: str
    model_usage: ModelCallUsage
    usage: UsageReport
```

预算生命周期统一按以下规则解释；ModelCallLimits/RunLimits 的名称区分执行职责，不表示按 run_id 重置额度：

| 标识/预算 | 生命周期与累计规则 |
| --- | --- |
| `task_id` | 标识一个逻辑任务，在暂停、澄清、人工审批和恢复期间保持稳定 |
| `run_id` | 标识一次具体执行，每次恢复可以产生新的 run_id，但不因此创建新逻辑任务 |
| `ModelCallUsage`、`RunUsage` | 均属于 task_id 对应的逻辑任务，由任务 State 关联；run_id 改变不能清零 |
| `ModelCallLimits.max_attempts` | 限制同一逻辑任务累计模型尝试次数，失败尝试与重试均计入 |
| `ModelCallLimits.max_retries` | 只限制单次 invoke/invoke_structured 调用的额外重试次数；重试也消耗任务累计 max_attempts |
| `RunLimits.active_timeout_seconds`、`max_tool_calls` | 限制同一逻辑任务生命周期内累计主动执行时长与工具次数，不能为每个新 Run 发放完整额度 |
| 非主动执行时间 | 队列等待、用户等待、澄清等待、审批等待及暂停期间不计入主动执行预算；模型请求和自动重试等待属于主动执行 |
| 初始化 | 只有创建全新的逻辑任务，才将两类用量初始化为零；续接或恢复从原任务快照继承 |

网关没有全局可变计数器：调用方传入同一逻辑任务的 ModelCallUsage，网关局部累积模型尝试次数，成功通过 ModelCallResult.model_usage 返回新快照；可预期模型错误通过 ModelCallError.model_usage 携带最新模型计数，usage 字段仍只表示 Token 报告，不包含原始 prompt、请求/响应或 provider 异常字符串。意外编程错误正常传播。02 的图调用节点负责将成功/失败的模型快照写回任务 State；Runtime 在本次 Run 更新任务所属的 RunUsage，累计该任务各次执行的主动时长。01 只定义这些契约，不新增任务 State 字段。取消继续传播，不承诺取消/进程崩溃瞬间用量精确持久化。

ToolExecutor 在 03 接收 RunLimits/RunUsage，在真正尝试执行工具前检查并递增 tool_calls，结果和可预期失败携带新快照，由 Runtime/调用节点收集；模型只生成 ToolCall 不增加该计数。Gateway 不读取或更新工具次数，不承担 Run 计时。02/03 用字段字典保存两类不可变快照，不把客户端、连接或锁写进 Checkpoint。

V1 明确要求同一 Run 内模型调用串行，工具调用也串行：前一次结果/错误的快照先被接收，再发下一次调用；不对同一份快照并发调用 Gateway。不同逻辑任务可按现有用户/会话隔离规则并发，同一逻辑任务各次 Run 顺序继承快照，无需全局锁、原子计数服务或并发预算预留系统。02 的 Runtime 在每次 Run 的主动执行区间统一计时，累计到同一任务的 RunUsage，覆盖模型请求、模型重试等待、工具及其他节点，避免 Gateway 重复计时；非主动执行等待不计入。Runtime 根据任务累计剩余额度在外层限制本次执行并传播取消，Gateway 只处理其单次尝试超时与有限重试。

RunLimits 由 Runtime 在每次具体执行中落实，额度归属于逻辑任务，不是独立的持久化 Run 实体或按 Run 重新发放的预算。02/04 接线时按稳定 task_id 读取任务快照，继承 ModelCallUsage/RunUsage；主动时间余额（秒）为 active_timeout_seconds 减去任务累计 active_elapsed_ms / 1000，工具次数余额为 max_tool_calls 减去任务累计 tool_calls。新 run_id、暂停、澄清、审批或恢复均不能重新初始化；只有全新逻辑任务从零开始。01 不实现这段持久续接，也不添加 Run/Workflow 数据表。

02 的 Runtime 构造接口据此接收 `AgentRuntime(graph, *, run_limits: RunLimits)`；ModelCallLimits 仅注入 Gateway。03 的 ToolExecutor 执行入口接收当前 RunLimits/RunUsage 并返回更新后的工具计数快照，不从全局对象读取计数；具体工具结果契约由 03 设计。01 不提前把这些执行参数接入现有图。

```python
# app/infrastructure/postgres.py
async def open_pool(settings: Settings) -> AsyncConnectionPool: ...
async def check_schema_version(pool: AsyncConnectionPool) -> None: ...
# 失败以安全资源错误上抛；main 将可预期资源失败转为 unavailable。
# 使用连接池自身 close，不另包一层只作转发的 close_pool。

# app/infrastructure/model.py
@asynccontextmanager
async def model_resources(settings: Settings):
    # yield 同一模型客户端与 ModelGateway；退出关闭自己创建的 HTTP 资源。
    ...

# app/api/dependencies.py
def resolve_demo_identity(*, user_id: str, settings: Settings) -> DemoIdentity: ...
# 普通辅助函数，不注册为 Depends，不声明 ChatRequest，不读取原始 JSON。
# 先检查 app_env，再检查受控名单；只接收已校验的 body.user_id。

# app/api/routes/agent.py（省略原有 Service 注入的 Annotated 写法）
async def chat(body: ChatRequest, request: Request,
               service: AgentService) -> EventSourceResponse:
    identity = resolve_demo_identity(
        user_id=body.user_id, settings=request.app.state.settings,
    )
    context, options = await service.prepare_chat(
        identity=identity, conversation_id=body.conversation_id,
        message=body.message, input_mode=body.input_mode, request_id=body.request_id,
    )
    # 以下执行接线由02实施，owner由02请求级ASGI guard预先建立。
    handle = await service.submit_chat(
        context, options=options, subscription_owner=request.state.subscription_owner,
    )
    return EventSourceResponse(service.stream_chat(handle))
```

最终请求由Route唯一解析ChatRequest，必填user_id/conversation_id/message，可选input_mode=auto|new_task（默认auto）、request_id=UUID|null。extra=forbid，客户端workflow_id返回422。普通辅助函数仅取已校验user_id，身份/session准备后才交Runtime。01负责身份与准备接口，02负责可选Task控制字段的受理语义。

task_id是逻辑任务的权威标识，正式生成者唯一为02 AgentRuntime。Runtime在thread门禁内新建Task时生成task_id，并令内部workflow_id=task_id。续接、澄清、审批和恢复加载原task_id，不重新生成或覆盖。两者保存于Task State并显式传递，业务申请/审批记录沿此关联保存。01与Service不生成task_id或workflow_id，不建立第二套临时任务。旧Graph兼容字段由Runtime创建或加载正式Task后映射到ExecutionContext，未关联正式Task的DemoContext不能直接送图。Service准备候选run_id与session/thread，Runtime接受新执行时关联到Task，去重命中则复用原Run，恢复生成新run并继承用量。

配置没有数据库 URL 时 lifespan 不调用 open_pool；没有完整模型配置时不进入 model_resources。资源状态可使用 main 内的少量明确字段，无需新增 AppResourceManager。HTTP 错误沿用现有 `{"error":{"code":...,"message":...}}` 结构；业务错误不放进 health。

### 3.6 请求衔接、身份与错误契约

01准备层与02正式执行的交接链路如下。完整HTTP执行验收归02。

```text
Route 唯一一次 ChatRequest 解析校验
  → 普通辅助函数检查 development/test 环境及受控 user_id → DemoIdentity
  → await Service.prepare_chat
      → 检查基础资源/session
      → SessionRepository.get_or_create(user, conversation)
      → 候选 run_id + 保存的 thread/服务端scope → DemoContext
      → 已校验 input_mode/request_id → SubmitOptions
  → 01准备层交付边界，不执行Graph
  → 02 Service.submit_chat(context, options, owner)
  → Runtime门禁内去重/新建或续接正式Task，创建或复用Run
  → ExecutionContext绑定 task_id 与同值workflow_id → Graph
  → EventSourceResponse(Service.stream_chat(handle))
```

ModelGateway 与数据库可独立验证，不相互持有对方；身份不经过 LLM 判定。模型调用只接收必要的调用关联，不默认接收 DemoContext 的全部身份/权限/消息对象。02 接入网关时，由图节点根据当前任务生成 ModelCallContext；03 调工具时才把受控身份与 scope 传给执行器。

| 边界 | 状态/code | 对外行为 |
| --- | --- | --- |
| ChatRequest 格式非法、额外 thread/scope 字段 | 422，沿用输入校验 | 不访问 session，不启动 SSE |
| production 环境请求演示聊天 | 503 / `demo_identity_disabled` | 不创建 DemoIdentity、不访问 session，不接受白名单绕过 |
| user_id 不在演示名单 | 403 / `demo_user_not_allowed` | 不暴露其他用户或名单详情 |
| 图/模型配置不完整或会话资源不可用 | 503 / `agent_not_ready` | 保留现有错误码，安全说明资源未就绪 |
| 准备期间真实 DB 操作失败 | 503 / `session_unavailable` | 不退回内存绑定，不输出 DSN/SQL 原始错误 |
| 开流后的现有 Graph 故障 | 现有 error/done | 01 不迁移事件协议，02 再统一语义 |

依赖库连接失败、超时和迁移版本不匹配是可预期资源错误；TypeError、名称错误等编程错误不应被统一捕获为“数据库不可用”。日志使用明确错误类别和关联 ID，不直接记录模型/连接异常全文。01 新增边界对自身负责，既有 Runtime 全量日志清理随 02 的调用迁移处理并注明遗留。

### 3.7 统一文件规划

下表是未来文件计划，不是本轮创建清单。公共文件按职责增量修改，避免多个 Task 维护相同能力。

| 文件 | 新增/修改 | 所属 Task 与职责 |
| --- | --- | --- |
| `README.md` | 修改 | 1.1.1 基线；其余 Task 同步实际启动/配置/验收说明 |
| `app/core/config.py`、`.env.example` | 修改 | 1.1.2 定义所有 01 设置与安全示例；后续实现按已定义设置消费 |
| `app/core/errors.py` | 修改 | 1.1.2 定义最少公共资源/身份错误；1.2/1.3 使用，不建错误码平台 |
| `app/core/logging.py` | 必要时修改 | 1.1.2 只改基础日志的实际安全问题，不引入追踪系统 |
| `app/main.py` | 修改 | 1.1.2 health 契约；1.2.2 池/仓储；1.3.1 模型资源；1.3.2 最终接线 |
| `compose.yaml` | 新增 | 1.2.1 单 PG、localhost、持久卷、healthcheck |
| `scripts/init_databases.py` | 新增 | 1.2.1 显式幂等建库/专用用户授权 |
| `scripts/migrate.py` | 新增 | 1.2.1 编号迁移入口与版本管理；不拆通用 migration 包 |
| `migrations/001_sessions.sql` | 新增 | 1.2.1 sessions 的 DDL；版本表由迁移器 bootstrap 管理 |
| `app/infrastructure/postgres.py` | 实现现有占位 | 1.2.1 连接设置/期望版本常量；1.2.2 池和只读版本核对 |
| `app/infrastructure/sessions.py` | 新增 | 1.2.2 最小数据结构和参数化 SQL 仓储 |
| `app/infrastructure/model.py` | 新增 | 1.3.1 单一模型创建与自有 HTTP 客户端关闭 |
| `app/runtime/model_gateway.py` | 新增 | 1.3.1 ModelCallLimits/ModelCallUsage、模型接口、结果和安全模型错误 |
| `app/runtime/context.py` | 新增 | 1.3.2唯一DemoIdentity/DemoContext/SubmitOptions定义；02迁移旧执行上下文消费方，无管理上下文 |
| `app/api/dependencies.py` | 修改 | 1.3.2 环境/白名单身份辅助函数与现有 Service 注入；不声明请求体、不做管理认证 |
| `app/api/routes/agent.py` | 修改 | 1.3.2唯一请求解析和准备接口；02正式提交Runtime并接SSE |
| `app/services/agent_service.py` | 修改 | 1.3.2 prepare_chat返回context/options，02落实submit_chat及stream_chat(handle) |
| `app/runtime/agent_runtime.py` | 修改 | 01仅定义RunLimits/RunUsage契约，02落实thread使用、正式Task、执行上下文及预算 |
| `scripts/check_model.py` | 新增 | 1.3.1 显式单次文本/结构化联调，不在启动/default tests 中自动运行 |
| `tests/test_application.py` | 按需修改 | 复用既有 HTTP/SSE/请求隔离验证 |
| `tests/test_postgres.py` | 按需新增 | 1.2 真实库迁移/绑定/释放风险，用少量场景组织 |
| `tests/test_model_gateway.py` | 按需新增 | 1.3.1 可控模型验证计数、超时、重试、用量 |
| `tests/test_demo_identity.py` | 按需新增 | 1.3.2 环境禁用、受控普通用户与隔离；无管理认证测试 |
| `docs/01-foundation-detailed-design.md` | 更新 | 完成每个授权 Task 后记录实现/验证/遗留；本轮只完善设计 |
| `docs/development-roadmap.md` | 更新 | 阶段设计状态与完成事实；不重写任务结构 |

不新建 `app/execution`、`app/domain`、`app/knowledge`，不实现 tools/workflows/memory/checkpoint/store 占位。本阶段不需要改 `graph/state/contracts/transfers`；若实现发现必须改协议，先说明真实边界问题，不顺带扩大重构。

### 3.8 数据库初始化与脚本契约补充

建库脚本只在显式调用时使用 `AGENT_DATABASE_ADMIN_URL`（SecretStr，脚本局部配置，不由 Web 应用读取）；目标开发/测试 URL 来自 3.2 的两项设置。Compose 的 bootstrap 账号密码由本地环境提供。开发库 owner 为 `agent_app`，测试库 owner 为 `agent_test`，两者为非超级用户且不是 CREATEDB/CREATEROLE；密码取相应目标 DSN，初始化前校验两个 DSN 的 host/port 和库名符合本地 Compose 目标，不允许任意远端目标。用户标识和库标识用驱动 Identifier 安全构造，不拼接未转义 SQL。角色已存在不自动重置密码，已存在库不擅自改变 owner；不一致明确报错，由开发者修正显式配置。

这是本地 Demo 最少权限划分，运行和应用迁移可使用同一专用 owner；不另建完整 migrator/reader/writer 角色体系。测试执行前除库名核对外，确认目标与开发连接不是同一实际库，且只操作测试命名的数据。无需主动撤销现有实例全部权限，也不访问用户无关库。

| 脚本入口 | 数据来源与副作用 | 成功/失败契约 |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe -m scripts.init_databases` | 显式 admin URL；创建固定两个库/两个专用用户 | 已存在且一致则成功；失败非零退出，不修改已有数据、不自动删库 |
| `.\.venv\Scripts\python.exe -m scripts.migrate --target development` | `database_url`；只执行仓库编号 SQL | 完成/无待迁移均退出 0；失败非零、当前迁移回滚 |
| `.\.venv\Scripts\python.exe -m scripts.migrate --target test` | `test_database_url`；强制测试库检查 | 没有 URL 或库名错误即拒绝，不回落 development |
| `.\.venv\Scripts\python.exe -m scripts.check_model` | 模型设置；固定无隐私文本和 RouteDecision 输出 | 两种能力分别报告；任一未通过则非零，不输出密钥/原始错误 |

脚本统一从项目根目录以 `python -m scripts.<module>` 运行，不修改 sys.path、不额外安装项目包，未来实施时验证该入口并同步 README。脚本级 admin URL 属初始化输入，不能复用为应用 database_url。以上只定义未来命令，本轮未执行。

## 4. 1.1 工程与配置

二级环节目标：复用 FastAPI 与分层工程，确定后续资源、身份、错误与运行方式的统一契约。1.1.1 处理事实与复用边界，1.1.2 处理设置和基础入口，不提前接数据库或开发模型网关。

### Task 1.1.1 工程复用与事实基线

#### 1. 设计目标

建立可供后续开发引用的最小工程基线，解决“规划被误认为实现、旧方案被当成新要求、已有代码被重复建设”的问题。沿用已有分层与主图，只处理实际阻碍基础工程运行的问题，不把本 Task 变成全仓审计或格式化。

#### 2. 职责划分

| 模块 | 职责 |
| --- | --- |
| README 与阶段文档 | 描述当前已有能力、运行入口、01 目标与未实现清单 |
| main/core | 保持 factory、lifespan、设置和日志的现有职责；确有问题才最小修复 |
| api/services/runtime/graph | 保持主调用方向；作为后续接线边界，不在本 Task 重构 |
| 依赖与项目工具配置 | 沿用 Python 3.13.7、直接/固定依赖清单与现有检查规则 |

#### 3. 技术方案

使用既有 `.venv`、FastAPI、LangChain/LangGraph 和测试基础。只将“已有可用实现”“占位职责”“后续迁移”分开记录；不新增架构扫描工具、能力注册表或第二份事实台账。已有用户修改以工作区内容为准，不依据旧 Git 提交覆盖它们。

#### 4. 执行步骤

1. 获得该 Task 授权后，仅核对本设计第 2 节涉及文件的增量和目录规则，确认实际运行入口与依赖版本来源。
2. 确认 Route→Service→Runtime→Graph、应用级装配与请求上下文的现有实现位置，列出复用点。
3. 对照新 V1 更新 README 的项目定位、已有能力和待实现说明，保留当前 API 示例，不提前改成未来输入。
4. 如存在阻碍基础启动的真实问题，局部修复并说明影响；不为“清理”修改枚举、专业图、State 或迁移旧目录。
5. 整理 `.venv` 重建、单 worker 启动和 development reload 说明；重启恢复演示未来必须使用无 reload 进程。
6. 实施时按实际改动选择已有验证；记录结果和转给 1.1.2/后续阶段的问题。

#### 5. 接口与数据结构

保留 `create_app(settings: Settings | None = None) -> FastAPI`、现有 `/health`、`POST /agent/chat` 和 ChatRequest；本 Task 不新增数据结构。`.venv` 是唯一项目解释器入口，`requirements.in` 仍维护直接依赖，`requirements.txt` 仍记录已验证固定版本，`pyproject.toml` 继续集中现有工具规则。

README 的能力记录统一使用“当前实现 / 计划变更 / 验证状态”三种事实，不以目录或枚举存在推断能力实现。

#### 6. 文件规划

- 修改 `README.md` 和本阶段文档：保存基线与后继责任。
- 仅确有问题时修改 `app/main.py`、`app/core/config.py`、`app/core/logging.py`、`pyproject.toml`；不得凭规划重写它们。
- 不新增生产模块或审计文件；不改变依赖，除非实际问题要求且单独说明。

#### 7. 前置依赖

项目定位、六阶段路线图与该 Task 执行授权。依赖既有 FastAPI 骨架，不依赖 PG、模型凭据或历史设计；本轮不执行上述开发步骤。

#### 8. 交付物与验收标准

交付当前工程基线、复用决定和实际问题归属。未来验收以 README 启动说明与当前代码相符、无模型时 HTTP 可存活且 chat 503 为准。若修改代码，复用相关 HTTP/参数测试；若仅文档调整，核对事实和链接即可。不得将原有功能重新计为本 Task 新增成果。

### Task 1.1.2 Demo 设置与运行入口

#### 1. 设计目标

解决配置说明滞后、资源就绪含义不清和错误可能回显秘密的问题，为 1.2/1.3 提供唯一配置源和公共错误边界。保持无外部配置可启动 HTTP。

#### 2. 职责划分

| 模块 | 职责 |
| --- | --- |
| core/config | 解析外部设置、隐藏秘密、检查配置值的必要约束 |
| core/errors | 定义最少安全错误及稳定 code；不包含 HTTP 依赖 |
| main | 装配基础服务、注册 HTTP 错误转换和 health；资源实现留给后续 Task |
| .env.example/README | 说明字段、启用条件与启动方式，不存真实秘密 |

#### 3. 技术方案

沿用 BaseSettings/SecretStr，不引入另一配置库。缺少可选资源配置属于 not_configured；有值但格式非法属于配置错误，不能静默当作未配置。Settings 使用隐藏输入值的错误配置，启动日志只列安全字段名/错误类别，不直接打印原始 ValidationError 数据。仅 SecretStr 脱敏不能保证所有第三方日志安全。

采用 3.1 的 health 契约，不增加动态模型探测或庞大 readiness 平台。1.1.2 先定义资源状态和错误结构，database ready 由 1.2.2 实际检查后提供；1.3.2 最终改变 agent_ready 对持久 session 的依赖。每个中间交付须说明已接线范围。

#### 4. 执行步骤

1. 按 3.2 增加 Settings 字段，分开模型调用与 Run 预算配置，校验正数、池 min≤max、重试非负、演示用户去空/去重等实际外部边界；明确 app_env 仅 development/test 允许演示身份，不逐层校验已可信内部值。
2. 提供 model/database 配置完整性的简单判断；模型只提供部分配置时标 not_configured 并安全说明缺少字段名。
3. 定义 health 的 resource status 与 `agent_ready` 含义，保留旧字段并增加状态字段；此时不伪造实际连接结果。
4. 在 core/errors 和 main 增加资源/身份安全错误到 HTTP 的最少映射，沿用现有 error 信封；不将 Runtime 绑定到 HTTP Schema。
5. 更新 `.env.example`，修正“模型未消费”的旧说明，标注Run预算等待02、工具次数统计等待03。01的SecretStr用于模型及数据库秘密；V1管理认证已延期，04只接入本地审批审计Actor，不增加管理密钥。
6. 修改项目默认名称与本地单 worker 说明，标明演示身份限 development/test、不可用作公网认证，保留真实 `.env`；不打印 Settings，不将模型 key 作为命令行明文参数。
7. 未来开发时复用现有无资源启动/503 用例，按风险验证非法配置秘密不回显，并记录接线到后继 Task 的状态。

#### 5. 接口与数据结构

完整配置采用 3.2 表，分别映射 ModelCallLimits 与 RunLimits；健康数据采用 3.1。错误类建议保留现有 `AgentNotReadyError`，增加 `SessionUnavailableError`、`DemoUserNotAllowedError`、`DemoIdentityDisabledError`，各自只承载安全固定消息；若使用一个小的安全错误基类，只承载 code/message，不构建通用错误目录系统。01 不定义管理认证错误。

PG 连接/迁移错误与模型错误在各实现模块转换为安全类别，HTTP 仅处理需要对外暴露的类别。框架入参校验继续使用现有 422，不改全部 HTTP 协议。

#### 6. 文件规划

修改 `app/core/config.py`、`app/core/errors.py`、`app/main.py`、`.env.example`、`README.md`；日志确有问题才改 `app/core/logging.py`；复用 `tests/test_application.py`。不创建 `.env`、更改真实凭据或提前提供业务路由。

#### 7. 前置依赖

依赖 1.1.1 的基线和现有配置/生命周期。无需数据库、模型连通；新增设置的实际资源消费依赖 1.2.2、1.3.1、1.3.2。

#### 8. 交付物与验收标准

交付 Settings、两组预算配置、配置示例、安全错误与 health 文档。未来必须证明无配置时 health/docs 可访问、chat 在开流前 503；部分配置不假就绪；production 的演示入口禁用且 agent_ready=false；格式非法错误不包含秘密；示例与代码一致。该 Task 完成不表示 PG 或模型通过联调。

## 5. 1.2 PostgreSQL

二级环节目标：建立可重复本地数据库环境与最少应用数据。1.2.1 管理数据库初始化和 DDL，1.2.2 管理运行时连接池与 session SQL；身份校验和 Graph 接线由 1.3.2 完成。

### Task 1.2.1 数据库与迁移入口

#### 1. 设计目标

解决数据库只有驱动和占位、无法从空环境复现的问题。提供单 PG、独立测试库及显式迁移，不把未来业务表一次建齐，也不让应用启动承担建库/升级副作用。

#### 2. 职责划分

| 模块 | 职责 |
| --- | --- |
| Compose | 一个 PG 服务的版本、端口、数据卷和健康检查 |
| init_databases 脚本 | 显式建两个库/专用用户，处理已存在一致资源 |
| migrate 脚本/SQL | 应用 schema 版本、编号事务迁移与重跑检查 |
| infrastructure/postgres | 最小连接设置、期望应用 schema 版本，供脚本与运行时复用 |
| 应用 lifespan | 本 Task 不自动建库/迁移；1.2.2 只读版本 |

#### 3. 技术方案

采用 3.3、3.8 的 PostgreSQL 17 单容器双库与非超级用户方案，不引入 ORM/Alembic。bootstrap 是显式管理操作：CREATE DATABASE 不放在普通事务迁移中，按库分别幂等创建；已有资源不擅自改 owner/密码。

应用迁移器只管理仓库编号 SQL：bootstrap 版本表时先取得固定事务级 advisory lock，在锁内创建版本表并核对已完成版本。每份迁移再次在事务与同一锁内重新读取版本、校验 checksum、执行 SQL、登记版本；当前文件失败整体回滚，先前已提交迁移保留。这样同时启动两个迁移命令也不会执行同一版本两次，不要求跨全部迁移的长事务。版本号从文件名读取、checksum 采用 SHA-256；迁移 SQL 不自行 COMMIT/ROLLBACK。

`schema_migrations`：`version integer primary key`、`checksum text not null`、`applied_at timestamptz not null default now()`。只做升序编号应用，不提供 down/reset/自动补历史版本。业务脚本维护 versions，运行时只核对所需版本，不重复实现文件扫描/执行逻辑。

#### 4. 执行步骤

1. 授权后确认本机 Docker/Compose 与 Windows 访问方式，固定验证过的 PG 17 镜像 tag/digest；记录真实版本，不先写“数据库已就绪”。
2. 添加 `compose.yaml`，单服务映射 localhost 端口与持久卷，healthcheck 不泄漏密码；README 说明停止容器保留数据。
3. 添加显式 bootstrap 脚本，校验固定目标，使用管理连接逐项创建用户和库；已存在一致则跳过，不一致安全失败；不提供删库重建路径。
4. 实现迁移脚本的目标选择、锁、版本表 bootstrap、SHA-256 和每份迁移事务；脚本错误以非零状态退出。
5. 添加 `001_sessions.sql`，落地联合主键、thread 唯一、长度与时间约束；不添加订单/审批/向量表。
6. 将期望版本常量放在 infrastructure/postgres，供 1.2.2 只读核对；新增迁移时同步更新该常量，不从 Web 启动自动运行脚本。
7. 更新初始化/迁移说明，明确开发与测试 URL 的选择；未来真实 PG 验证重跑、失败回滚和测试目标保护，记录结论。

#### 5. 接口与数据结构

脚本入口采用 3.8；脚本内部使用简单函数即可：

```python
async def initialize_databases(admin_url: SecretStr, *,
                               development_url: SecretStr,
                               test_url: SecretStr) -> None: ...
async def apply_migrations(database_url: SecretStr, *,
                           target: Literal['development', 'test']) -> list[int]: ...
```

返回本次实际新增的版本号列表，空列表表示无待迁移，不新增复杂报告 DTO。所有 SQL/驱动异常由入口输出安全类别和版本号，失败返回非零；不要打印 URL 或拼接 SQL。sessions 表定义严格采用 3.3，不依赖未来 DemoIdentity，也不保存 scope。

#### 6. 文件规划

新增 `compose.yaml`、`scripts/init_databases.py`、`scripts/migrate.py`、`migrations/001_sessions.sql`；实现 `app/infrastructure/postgres.py` 的最少连接/版本定义。更新 README、阶段记录；按风险新增 `tests/test_postgres.py` 的迁移场景，不建设通用迁移测试框架。

#### 7. 前置依赖

依赖 1.1.1、1.1.2，运行环境需要未来显式准备的 Docker/Compose 与本地环境凭据。不依赖业务 Domain、ToolRegistry 或 04 Saver；1.2.2 依赖本 Task 的库和应用迁移。

#### 8. 交付物与验收标准

交付可复现 PG 环境、bootstrap、迁移入口、sessions DDL 与说明。未来必须以真实 PG 验证两个库分别存在且不相同、服务版本被固定、迁移重跑不新增记录、失败当前迁移回滚且未登记、已应用文件被改后拒绝、错误目标不执行。测试用临时迁移目录/临时编号，不修改正式已应用 SQL；清理仅涉及本用例数据，不删库或卷。安装驱动、Compose 配置存在或 healthcheck 配置存在不能替代真实连接证据。

### Task 1.2.2 连接与会话绑定

#### 1. 设计目标

解决连接资源没有应用级管理、会话线程只靠进程内推算的问题。为 Service 提供按用户隔离、并发一致且重启后可读取的绑定，不实现工作流调度或 Checkpoint。

#### 2. 职责划分

| 模块 | 职责 |
| --- | --- |
| infrastructure/postgres | 有界开启异步池、读取实际库与迁移版本、资源错误分类 |
| infrastructure/sessions | SessionBinding、参数化 get/get_or_create 和事务 |
| main/lifespan | 开启/注入/关闭池，失败时释放并设置资源状态 |
| Service | 1.3.2 调用仓储；本 Task 不把 DB 操作塞入 Route |

#### 3. 技术方案

使用现有 `psycopg_pool.AsyncConnectionPool(open=False)`，启动有界 open/wait，池获取/连接各有 timeout；应用使用小池 1–5，失败不无限等待。Windows 事件循环兼容性在未来真实启动时依据实际版本处理，不现在凭经验换解释器。只捕获可预期连接/版本失败，未知编程错误正常使启动失败。

仓储 `get_or_create` 使用 READ COMMITTED 下两条语句：事务中 `INSERT ... ON CONFLICT (user_id, conversation_id) DO NOTHING`，随后按联合键 SELECT；并发冲突在唯一约束上等待，后续 SELECT 读取已提交行。不用单条 CTE 拼接“插入或读取”以避免快照可见性歧义，也不为并发创建增加应用锁。唯一约束冲突若不是该联合键应正常暴露，不能吞掉后悄悄换用户/thread。

首次候选 thread 沿用原 uuid5 算法的命名空间与 JSON 编码；算法放在 session 实现一处。数据库已存值永远优先；Runtime 不再自行推算。候选算法只是兼容工程选择，不构成不可更改的公开 ID 协议。

#### 4. 执行步骤

1. 实现 3.5 的 open_pool 与 schema 检查，先连接真实目标再核对迁移版本；缺迁移返回安全未就绪，不执行 DDL。
2. 在 lifespan 中管理池，确保 open/wait/检查任一步失败都 close；成功后退出也 close。数据库配置缺省不创建池。
3. 添加 SessionBinding 和带 owner 条件的 get；UUID/时间从数据库结果映射一次，内部调用不重复校验 API 约束。
4. 添加 get_or_create 的两语句事务与候选 thread 生成；不接受显式 thread_id，也不提供无 user_id 的任意查询接口。
5. main 注入 SessionRepository 与 database_status；基础连接失败时 HTTP 存活、chat 后续按资源状态拒绝。运行中仓储连接异常安全上抛，不返回假绑定。
6. 未来在独立测试库验证同键重复/并发、跨用户同名会话、关闭释放和重开读取；交付给 1.3.2 接线。

#### 5. 接口与数据结构

采用 3.5 的 SessionBinding 与 SessionRepository；所有方法 async，只返回绑定/None，不返回裸 cursor 或连接。`get` 缺行不创建；`get_or_create` 只创建绑定，不创建用户、workflow、run 或消息。

迁移检查要求版本与当前应用期望一致；缺版本表、低于期望或未知更高版本都标未就绪，避免旧应用误用新 schema。不在每次仓储查询重复做迁移检查。pool ready 是启动时事实，运行中故障依靠请求错误处理，不新增持续探测线程。

#### 6. 文件规划

实现 `app/infrastructure/postgres.py` 的池与检查；新增 `app/infrastructure/sessions.py`；修改 `app/main.py` 的生命周期/资源状态；更新 README 和 PG 用例。不修改 04 checkpoint.py、05 store.py 或 Graph State。

#### 7. 前置依赖

依赖 1.2.1 的真实库和迁移、1.1.2 的设置与错误。API 身份/当前 run 不属于本 Task 前置；因此与 1.3.2 不形成循环。

#### 8. 交付物与验收标准

交付池与 session 仓储、资源生命周期接线。未来真实 PG 证明：同用户会话重复/并发同一 thread；不同用户同名会话不同 thread；get 不创建；重新建立连接/重新启动进程后原绑定可读；部分启动失败和正常退出无残留池。缺真实测试环境时仅记录未验证，不用 Mock 或跳过用例作为验收通过。绑定重启稳定不等于图快照持久，线程输入互斥在 02 验收。

## 6. 1.3 模型与身份

二级环节目标为提供共享模型入口、普通演示身份、持久session及Service准备接口。网关不依赖DB，1.3.2组合会话仓储和可信上下文。正式Task及旧Graph执行接线交02，不在01承担Supervisor迁移或正式任务创建。

### Task 1.3.1 统一模型调用

#### 1. 设计目标

解决直接模型调用缺少统一超时、次数、重试和用量口径的问题，为 02/03 提供可复用的单一入口。保留 LangChain 原生 AIMessage/ToolCall，不建设 provider 路由平台或 Token 成本账本。

#### 2. 职责划分

| 模块 | 职责 |
| --- | --- |
| infrastructure/model | 创建一个 ChatOpenAI 和自有异步 HTTP 资源，lifespan 退出关闭 |
| runtime/model_gateway | 普通/工具绑定/结构化调用、模型尝试次数/单次超时/有限重试、UsageReport、安全模型错误 |
| runtime/agent_runtime | 01 只定义 RunLimits/RunUsage；02 才落实整体执行预算，03 接 Executor 的工具计数 |
| main | 注入共享模型资源和网关；01 旧图可临时使用同一底层 model |
| scripts/check_model | 显式无业务模型联调，按能力报告结果 |
| 02/03 图节点 | 后继正式调用网关、持有任务用量快照；不由网关拥有 State |

#### 3. 技术方案

沿用 `langchain-openai` 的 ChatOpenAI，默认以现有兼容入口为基础，不凭空指定真实模型。Gateway 接受共享模型，在每次调用上用派生 binding 绑定 tools/schema，不对单例模型做原地可变绑定，避免不同 Agent 的工具集合污染。普通工具调用保留 AIMessage，结构化调用使用 `include_raw=True` 取得原始响应与解析结果；具体 provider 支持的 method 在显式联调前确认，不做失败后偷偷切换模式。

SDK 设 `max_retries=0`，所有额外尝试由 Gateway 控制。每次尝试前检查同一逻辑任务在 ModelCallLimits.max_attempts 下的剩余次数，再递增 ModelCallUsage 并按单次 timeout await；单次 Gateway 调用按 max_retries 最多额外重试一次明确瞬时错误，重试仍计入任务累计尝试次数。认证、参数、解析失败不自动重试。02 Runtime 按任务累计剩余主动时长限制本次 Run，必要时取消包括重试等待在内的模型调用；Gateway 正常传播取消，不自行读取或处理 RunLimits。

每次 Run 的主动执行时间统一由 02 Runtime 统计并累加到逻辑任务的 RunUsage，覆盖模型、重试等待、工具和其他节点，队列/用户/澄清/审批等待及暂停时间不计入；Gateway 不累计主动时长，不接收工具次数或运行剩余额度。03 ToolExecutor 在执行工具前检查并增加同一任务累计工具次数，副作用前还须遵守 Runtime 按任务剩余主动时间确定的有效执行期限。01 只定义 RunLimits/RunUsage，不测试或宣称 120 秒任务累计主动时间限制已经生效。

V1 同一 Run 的模型与工具调用均串行，前一次调用返回并收集不可变快照后才开始下一次；不同逻辑任务的快照独立，同一逻辑任务的多个 Run 继承同一累计快照。无需额外并发预算锁或预留系统。任务在暂停、澄清、人工审批与恢复期间保持 task_id 稳定，按 3.5 交给 02/04 接续用量，不因新 run_id 清零。

用量为已知/估算/未知报告：本阶段不实现 tokenizer 估算；provider 未给出的字段为 null。全部存在时为 known，部分/全部缺失则 unknown，仍保留提供的数值。跨多次尝试只对已知项汇总，任一相关项未知则合计项保持未知，不将失败尝试默认记零。结构化解析失败有 raw 时也提取其 usage。

#### 4. 执行步骤

1. 实现 model_resources，创建共享模型及需要的异步 HTTP 客户端，显式设置 timeout 和 `max_retries=0`；仅释放自己创建的资源，不关闭注入测试对象的外部资源。
2. 实现 3.5 的 ModelCallLimits/ModelCallUsage、模型上下文/结果/错误；在 agent_runtime.py 仅定义 RunLimits/RunUsage 契约，不实现 Runtime 预算。分别从 Settings 映射，不在 AgentConfig 或单例网关保存可变计数。
3. 实现普通 invoke 与可选 tools 绑定，使用派生 runnable，保留工具名、原生 args 和 call_id；不调用工具、不改写用户权限。
4. 实现 invoke_structured，绑定指定 Pydantic schema，提取 raw/parsed/usage；解析失败以安全 code 结束，不自由文本兜底。
5. 在共同的底层调用路径统一应用任务累计模型尝试计数、单次尝试超时和单次 Gateway 调用的有限重试；成功与可预期失败均返回最新 ModelCallUsage。任务累计主动时间与工具计数留给 Runtime/Executor，不向 Gateway 增加运行预算参数。
6. 将模型资源接入 lifespan，旧 builder 暂使用共享 raw model；网关同时就绪但没有正式接管 Supervisor。列明 02 的实际迁移点，不额外建立“新/旧网关模式”配置。
7. 提供显式 check_model 脚本，仅使用固定无隐私文本和 RouteDecision 验证连通/结构化能力；真实业务 tools 的完整绑定在 03 联调。
8. 未来先运行可控模型场景，再在已配置环境显式真实联调；记录实际 model/method 和能力差异，不进入默认付费测试。

#### 5. 接口与数据结构

严格采用 3.5 的 ModelGateway/ModelCallResult/ModelCallError；只保留普通与结构化两个执行接口，工具绑定作为 invoke 参数，不再公开可能绕过限制的“返回裸 runnable 后自行 ainvoke”接口。

`ModelCallError.code` 最少区分 `model_limit_exceeded`、`model_timeout`、`model_unavailable`、`model_output_invalid`，均不携带 provider 响应原文。模型配置错误在生命周期或显式检查时安全报告；不把编程错误归入网络失败。`UsageReport.estimation_method` 在 01 恒为 None，estimated 枚举只定义数据口径，尚无估算实现。

ModelCallContext 不含 mutable usage，ModelCallUsage 以 model_usage 参数传入并通过结果/错误同名字段返回；usage 字段只表示 Token 报告。task_id 由未来图任务上下文提供，并在暂停、澄清、审批与恢复期间稳定；run_id 标识一次具体执行，恢复可以生成新值，但两类用量仍归原 task_id。RunUsage 不进入网关接口。数据结构中零值默认只用于创建全新逻辑任务，恢复不能重新调用默认构造来代替加载原用量。01网关独立验证使用受控调用契约，正式业务调用必须等待02 Runtime提供Task及Run关联，01不生成临时Task或workflow。

#### 6. 文件规划

新增 `app/infrastructure/model.py`、`app/runtime/model_gateway.py`、`scripts/check_model.py`；修改 `app/main.py` 的模型资源装配，在 `app/runtime/agent_runtime.py` 仅定义 RunLimits/RunUsage；新增少量 `tests/test_model_gateway.py`。沿用 1.1.2 设置，不引入 provider SDK、新 Agent、预算管理包或 execution 包，不修改 Supervisor 路由/澄清/State。

#### 7. 前置依赖

依赖 1.1.1/1.1.2 的工程和设置，不依赖数据库或 session。真实联调需要明确的供应商/模型/API key，秘密只在本地环境配置；缺失时先完成已授权可控部分，但本 Task 真实模型门禁仍未通过。

#### 8. 交付物与验收标准

交付网关、分离的模型调用与运行预算契约、客户端资源管理和显式检查入口。未来受控验证覆盖：工具调用信息保留、结构化解析、单次模型超时、失败尝试和一次额外重试共用模型尝试上限、额度耗尽不再发请求、缺 usage 不计零、不同调用工具绑定不互相污染。网关不测试工具次数或 Run 总期限；串行快照传递由 02 接线验证。真实模型文本和结构化能力分别有记录，关闭资源得到验证。

明确遗留：旧 Supervisor 直到 02 仍直接调用共享模型；01 不宣称全图预算、工具执行限制、resume 计数持久化已生效。03/04 需把 task 计数放入快照并验证跨恢复；不存在进程崩溃时用量与 Checkpoint 全局原子保证。

### Task 1.3.2 演示身份与管理边界

#### 1. 设计目标

解决请求任意 user_id 缺少受控边界、线程绑定未持久使用、普通聊天可能与未来管理审批混淆的问题。01 仅完成 development/test 普通演示身份与用户隔离接线；Task 名称中的管理边界只表示普通聊天无审批权，04仅负责本地审批Actor接入，真实管理员认证V1延期，不提前预留无调用方的模块。

#### 2. 职责划分

| 模块 | 职责 |
| --- | --- |
| Route / API 辅助函数 | Route 唯一解析 ChatRequest；普通辅助函数检查环境/名单并创建 DemoIdentity，无请求体依赖重复声明 |
| Service | 资源检查、await仓储、准备DemoContext和SubmitOptions；02再接Runtime提交与事件适配 |
| SessionRepository | 只负责 user/conversation→thread 持久绑定 |
| Runtime | 02实施正式Task创建/续接和Run关联，使用可信thread；不解析HTTP body |
| Graph | 02在Runtime绑定正式Task后映射ExecutionContext，不选择身份/scope或获得审批权 |

#### 3. 技术方案

固定两名受控用户，初始名单含现有 README 的 dev-user，均由服务端映射普通 scope。仅 app_env 为 development/test 时可创建 DemoIdentity；production 在检查名单前直接拒绝，即使 user_id 在名单内也不能启用。无需新增“生产可强行开启演示模式”的配置。HTTP 存活可保留，production 的 agent_ready=false。

白名单只是受控本地模拟，不是真实身份认证：知道另一个允许 user_id 的客户端仍可模拟该用户，用户隔离是数据按所选模拟身份分区，不证明请求者拥有该真实身份。不得直接作为公网部署的身份验证方案，也不在 01 加入 JWT、OAuth 或完整 RBAC。

普通身份与未来审批管理身份必须独立。01 不接受聊天内容、body 候选权限或任意管理 header 作为审批授权，不创建管理上下文、审批 scope、管理配置、认证函数或相关测试；04提供本地审批入口及审计Actor，未来认证沿Provider扩展。

01定义唯一DemoContext及SubmitOptions准备接口。SessionBinding.thread_id在Service转为字符串一次。01不创建正式Task，不生成workflow_id，不为维持旧Graph调用新增临时标识。02替换旧AgentContext的执行侧消费，在Runtime创建或加载Task后，将task_id及其同值workflow_id映射到ExecutionContext，再调用旧Graph。run_id候选值仅在受理新执行后有效，不授予权限。

#### 4. 执行步骤

1. 在context.py定义DemoIdentity、DemoContext与SubmitOptions，准备层使用新契约；02统一迁移旧AgentContext的Graph消费方，不在01双轨执行或新增管理上下文。
2. Route 唯一声明 body: ChatRequest，由框架一次解析校验，再调用普通 resolve_demo_identity(user_id=body.user_id, settings=...)；函数先拒绝 production，再检查名单。Service 注入依赖不声明 ChatRequest，不另读 JSON，不新增身份 Header/Query。普通 scope 固定来自服务端，不接受 body/model/Store 候选值。
3. 在Service增加async prepare_chat，检查基础资源，按identity.user_id/conversation取得绑定，准备候选run_id和DemoContext，并按已校验input_mode/request_id构造SubmitOptions，返回二元组。
4. 定义Route单次解析和准备接口，执行提交及SSE接线交02；不让01准备层直接调用旧Graph。02由submit_chat显式传递context/options/owner，受理后stream_chat(handle)。
5. 将context.thread_id及Task绑定映射作为02交接，02 Runtime移除自身thread重算，在正式Task创建或续接后填入ExecutionContext。01不创建Task或workflow关联。
6. 保持普通上下文无审批权限，将本地审批Actor及入口责任交给04，真实认证留未来，不为其提前编写无使用场景的实现。
7. main注入基础资源与Service准备接口，README注明production禁用、DB故障拒绝及02正式执行接线边界。01资源就绪不代表完整chat已验收，正式agent_ready及开流要求在02包括Runtime/Graph受理能力。
8. 未来验证单一请求解析、环境/名单、prepare_chat二元组及真实PG绑定；完整HTTP执行、正式Task生成、线程互斥、Run预算与SSE验收交02，不增加管理认证测试。

#### 5. 接口与数据结构

采用 3.5 的 DemoIdentity/DemoContext、resolve_demo_identity 与 prepare_chat/stream_chat。普通scope固定为`orders:read`、`refunds:request`、`knowledge:read`、`memory:read`、`memory:write`，没有审批管理 scope。本阶段仅定义普通受控 scope，不宣称 Registry/Executor 已执行权限过滤；03 按这组语义细化 Metadata 并复检。

身份辅助函数只接收 Route 已校验的 user_id 与 Settings，不声明 ChatRequest/Request，也不注册为请求体 Dependency；Settings 从应用状态取。请求体采用已对齐的三必填/两可选字段，不新增 user_id Header/Query。用户查不到其他用户 session 时不提供可枚举的差异响应；不新增 session 管理接口或任意 thread 状态查询。

所有HTTP状态/code按3.6，prepare_chat数据库故障在开流前抛SessionUnavailableError。绑定成功后准备候选run_id，02受理新执行后才生效；request_id命中复用原Run。01不实现resume或Task生命周期，不签发审批权限。

#### 6. 文件规划

新增app/runtime/context.py，保存DemoIdentity、DemoContext和SubmitOptions；修改身份辅助函数、Service准备接口、Route请求Schema及准备接线和main资源注入。02负责Runtime.submit、执行侧旧上下文迁移及SSE正式接线。未来同步README与受影响用例，不新增管理认证、审批路由、用户表或workflow repository。

#### 7. 前置依赖

依赖 1.1.2 的环境/普通身份设置与错误、1.2.2 的真实仓储/池、已有 Service/Runtime。最终接线安排在 1.3.1 后，使同一 lifespan 的模型资源与数据库资源一次组合交付；身份校验自身不依赖模型决策，不调用 Gateway，也不依赖04的本地审批Actor或未来认证。

#### 8. 交付物与验收标准

交付环境受限的普通演示上下文、SubmitOptions准备接口、持久thread绑定和说明。未来验证development/test名单、production禁用、额外权限拒绝、Route唯一解析三必填/两可选字段、无身份Header/Query、同会话保存thread、跨用户隔离、DB故障开流前拒绝。验证prepare_chat完整返回context/options且不创建Task、不调用Graph。完整HTTP调用及新Run/去重/旧Graph关联归02验收，Task唯一由Runtime创建，workflow_id为同值别名。01不验收管理认证、独立执行或正式任务生命周期。

HTTP 替身只用于传输与上下文观察，正式装配不含测试替身；真实 session 使用独立 PG 验证。尚无 thread 互斥、独立运行任务或审批接口，不能把身份测试通过写成 HITL 已完成。

## 7. 依赖关系与推荐开发顺序

```text
1.1.1 工程复用
  → 1.1.2 配置/入口
      ├→ 1.2.1 建库/迁移 → 1.2.2 池/session ─┐
      └→ 1.3.1 模型网关/限制 ────────────────┴→ 1.3.2 身份/请求接线
                                                    → 01 集成验收
                                                    → 02 实施（仍需明确授权）
```

| Task | 必要前置 | 交给谁 | 推荐序号 |
| --- | --- | --- | --- |
| 1.1.1 | 项目定位/路线图、已有骨架 | 1.1.2 的事实基线 | 1 |
| 1.1.2 | 1.1.1 | 1.2/1.3 的配置/错误/health 契约 | 2 |
| 1.2.1 | 1.1.2 | 1.2.2 的实际库与 schema | 3 |
| 1.2.2 | 1.2.1 | 1.3.2 和 02 的稳定 session | 4 |
| 1.3.1 | 1.1.2 | 1.3.2 的模型资源装配、02 的统一调用入口 | 5 |
| 1.3.2 | 1.2.2、最终组合装配依赖 1.3.1 | 阶段集成与 02 | 6 |

推荐按表串行推进，减少 main/config 的交叉修改。若数据库环境受阻，可单独授权 1.3.1，但不绕过真实 PG 门禁；这不授权自动并行开发或新增 Task。

上图及序号只描述未来实施依赖。六阶段详细设计已完成，当前整改与最终收敛，四项决策已确认或延期，待最终冻结后再由用户确认开发次序及Task授权。

未来实施时各 Task 可以有必要中间状态：1.1 只定义状态；1.2 实现池/仓储但未接 chat；1.3.1 提供网关与 Run 预算数据契约但旧 Supervisor 未切换；1.3.2 完成环境受限的普通身份/thread 接线。每次交付说明当前有效范围，不能提前填 future ready；本轮不执行任一 Task，也不启动 04 管理认证开发。

## 8. 阶段整体交付物与验收标准（未来执行）

### 8.1 交付物清单

1. 沿用现有分层的 FastAPI 工程与唯一 Settings、安全错误/health/启动说明。
2. 单 PostgreSQL 容器、独立开发/测试库、显式 bootstrap/编号迁移与 sessions。
3. 生命周期管理的异步池和模型 HTTP 资源，失败/退出均释放。
4. SessionRepository 和稳定用户/会话/thread 绑定、限 development/test 的 DemoIdentity/DemoContext；不含管理认证。
5. ModelGateway 的 ModelCallLimits/ModelCallUsage、模型单次超时/有限重试/Token 报告、RunLimits/RunUsage 数据契约及显式模型检查入口；整体 Run 管理在 02 接线。
6. 受影响测试、真实环境验证记录、README 和 02 交接清单；不把所有后续模块一次建齐。

### 8.2 验收矩阵

| 门禁 | 必须观察到的未来行为 | 证据与边界 |
| --- | --- | --- |
| 工程/配置 | 无外部依赖 HTTP 存活；配置非法安全失败；未就绪 chat 503 | 复用应用测试和实际启动；不以健康接口宣称业务就绪 |
| PG 环境 | 实际连接双库、固定版本、重跑不重复、失败回滚 | 真实 PG 与版本表；不是驱动安装或容器配置截图 |
| 生命周期 | 正常退出和部分初始化失败释放自有池/客户端 | 受控资源验证与真实启动关闭，不增加通用监控系统 |
| Session | 并发同键唯一、跨用户隔离、重启绑定可读 | 真 PG 记录与 thread 对应；不等于持久快照 |
| 请求准备边界 | Route唯一解析最终ChatRequest，Service返回DemoContext/SubmitOptions，普通身份/session已校验 | 不创建Task或调用Graph，正式提交及SSE归02，无身份Header/Query |
| 模型网关 | 原生 ToolCall 保留、解析错误安全、模型尝试次数/单次超时/重试受控 | 可控替身；Gateway 不包含工具次数/Run 期限；串行快照接线交给 02 |
| 真实模型 | 固定无隐私文本与结构化输出分别通过 | 独立显式联调；记录 provider/model/method，不自动收费测试 |
| 演示身份/隔离 | development/test 受控用户可用，production 禁用；非名单拒绝，普通聊天无审批权 | 普通身份辅助函数/HTTP 验证；不是公网认证，04仅提供本地审批Actor，真实认证延期 |
| 文档 | 按说明能初始化/迁移/启动，事实和限制清楚 | README 与实际结果一致；设计不是实现证据 |

### 8.3 未来验证组织

只在授权开发时执行，默认测试不访问付费模型。复用已有 HTTP/协议测试；新增少量 PG、Gateway、身份风险场景，不为枚举/getter/字段组合机械加测。PG 场景显式提供测试库 URL，缺环境允许标记未验证，但阶段验收不能因此通过。仅依赖发生变更时同步清单并执行 pip check，不因本设计新列文件而引入新依赖。

Task 内运行受影响验证；阶段整合涉及公共入口时运行一次完整回归与必要代码检查，检查通过后不无故扩大或重复。真实模型、PG、Windows 异步运行兼容性分别报告，不把可控模型通过等同 provider 已支持所有能力。本轮未运行以上任何验证或检查。

以上均为未来开发验收：01 实施完成要求六项授权实现、相关验证、真实 PG/模型门禁与用户阶段验收均完成；环境/凭据缺失时保持门禁未通过。六阶段设计已获最终确认，四项决策已确认或延期，实施仍由用户另行授权，不因本设计或基础资源方案确认而开始实施。

## 9. 与 02 AgentRuntime 阶段的衔接

| 01 提供 | 02 使用/补齐 | 后续边界 |
| --- | --- | --- |
| session 持久绑定、DemoContext.thread_id | 同 thread 输入互斥、稳定 config、普通聊天冲突处理 | 04 才接 PG Saver/恢复；thread 存在不能证明快照存在 |
| prepare_chat返回DemoContext/SubmitOptions二元组及候选run_id | submit_chat显式传context/options/owner到Runtime.submit，唯一创建正式Task后才映射旧Graph | 01不创建Task或直接执行Graph，02负责完整HTTP/SSE及去重验收 |
| ModelGateway、ModelCallLimits/ModelCallUsage | Supervisor 正式接网关；按 task_id 加载并串行更新累计模型快照，成功/失败均写回任务 State | max_attempts 按逻辑任务累计含重试；max_retries 只限单次 Gateway 调用；新 run_id 不清零 |
| RunLimits/RunUsage 数据契约 | Runtime 接收 RunLimits，在本次 Run 落实任务累计主动时间/工具次数余额；同 Run 模型与工具调用串行 | 03 Executor 统计同一任务累计工具次数，Runtime 汇总；02/04 保持 task_id 稳定并继承两类用量；暂停/用户/审批等待不计时，仅全新任务初始化为零；01 无持久 Run 管理 |
| 共享模型/池的 lifespan | builder 注入模型预测入口、保持启动编译一次 | 04/05 单独初始化库管理的 Saver/Store 资源 |
| 限 development/test 的 DemoIdentity 与普通 scope | 保持环境检查、可信执行上下文映射和专业输入隔离 | production 禁用演示模式；03 权限/Schema 绑定与执行复检；04通过服务端ActorProvider提供本地审计Actor，不继承普通聊天权限 |
| workflow_id/run_id 的兼容关联语义 | 明确公共输入迁移和单次执行关联，不静默忽略旧字段 | 无权威 Workflow 表或持久 Run 管理；task/run/workflow/thread 各自职责保持清晰 |
| 既有主图与映射 | 修澄清、AfterSales→Refund、三专业入口和未实现错误 | 业务工具/订单/退款/RAG/Store 按 03–05 推进 |

重点是复用而非复制：02 不再建第二个模型适配层、第二个 user/conversation→thread 算法或第二套身份上下文；只在其业务边界扩展必要数据。现有 AgentConfig 继续表达 Agent 静态配置，不保存请求用量。ModelCallLimits 唯一归 Gateway，RunLimits 唯一归 Runtime、工具次数由 Executor 统计，均沿用不可变快照；同 Run 串行即可，无需并发预算管理系统。04接本地审批Actor，未来身份认证沿Provider扩展，不以提前预留为由添加 01/02 无调用方的认证模块。

01交付准备层。02负责正式Task创建、旧Graph执行侧迁移、网关接入、独立任务、互斥及SSE完整链路。未完成02前不以旧Graph绕过Runtime创建任务，不用测试替身作为正式业务路径。

## 10. 技术决策分类与确认状态

### 已确定或已采用

以下记录既有审核和本轮明确的接口选择，不再作为用户待决策事项。采用设计不代表已经实施或验证。

| 决策 | 已采用方案 | 影响与确认时点 |
| --- | --- | --- |
| PG本地主版本与环境 | PostgreSQL17、单容器开发/测试双库 | 已采用主版本，1.2.1锁镜像，05验证pgvector |
| 迁移与账号 | 显式编号SQL、两库非超级owner，无ORM/Alembic | 已采用，bootstrap高权限凭据仅显式脚本使用 |
| 会话首次thread | uuid5候选首次持久化，之后数据库值权威 | 已采用，无第二套算法或独立workflow线程 |
| 健康与退化 | HTTP可存活，缺DB则chat 503，health不探测模型网络 | 01验收基础准备，完整chat执行归02 |
| 限制口径 | 保留原默认数值与职责；模型尝试、主动执行时间、工具次数均按逻辑任务累计，max_retries 仅限单次 Gateway 调用；同 Run 串行 | 两类不可变用量均归稳定 task_id；恢复可换 run_id 但不清零，非主动等待不计时，仅新逻辑任务从零开始；02–04 接线 |
| 演示用户与 scope | dev-user / demo-user-b 的普通 scope；仅 development/test 允许，production 禁用 | 本轮补环境约束；不是真实认证，不直接用于公网，不新增 JWT/OAuth/RBAC |
| 管理认证与审批责任 | 真实管理员认证V1延期，04只提供本地ActorProvider/审批入口，01不新增管理密钥或审批scope | 演示Actor仅审计，普通chat不审批，production禁用演示入口 |
| 请求解析与标识 | Route 唯一解析 ChatRequest，普通函数接已校验 user_id；workflow_id为task_id同值内部别名，run_id为单次执行关联 | 本轮消除重复声明；无新增身份 Header/Query、权威 Workflow 记录或持久 Run 管理 |
| 01/02迁移边界 | 01准备身份/session/context/options，不创建Task或调用旧Graph；02 Runtime唯一生成task_id并完成执行接线 | 旧Graph在正式Task关联后取同值workflow_id，无临时工作流 |

### 最终决策状态

全项目四项决策已确认或明确延期，见06第13.2A。正式采用OpenAI text-embedding-3-small/1536、candidate5/top3与2400tokens/24KiB/阈值null、审批创建起30分钟；管理员认证V1延期，仅保留04本地审批ActorProvider审计。此前已采用架构不重开，无该四项待确认参数。实际服务及框架行为仍按下节实施验证。

### 实施阶段验证

1.2.1实施时锁定PG17镜像tag/digest并验证双库、权限和迁移；1.3.1验证实际model/base_url/结构化method及Windows异步行为。使用ChatOpenAI兼容适配的设计已采用，实际供应商/API可用性留实施，不自动回退provider/method。

### V1范围外

生产级身份认证、分布式执行/预算、持久事件重放及通用恢复平台延期，不阻塞当前设计收敛。Memory自动崩溃恢复、复杂工具披露及ANN优化保持既有范围边界。

## 11. 设计状态与未来执行记录

| Task | 设计 | 实现 | 自动验证 | 真实联调 |
| --- | --- | --- | --- | --- |
| 1.1.1 | 已最终确认 | 未开始 | 未执行 | 不适用 |
| 1.1.2 | 已最终确认 | 未开始 | 未执行 | 未执行 |
| 1.2.1 | 已最终确认 | 未开始 | 未执行 | 未执行 |
| 1.2.2 | 已最终确认 | 未开始 | 未执行 | 未执行 |
| 1.3.1 | 已最终确认 | 未开始 | 未执行 | 未执行 |
| 1.3.2 | 已最终确认 | 未开始 | 未执行 | 未执行 |

每个授权 Task 完成后在本节记录新增/复用/修改内容、文件、实际验证结果、真实环境结论、遗留与后继责任，并同步路线图进度和 README 的实际行为。重要 Graph 契约真正变更时再更新 graph-protocol，不提前把规划写成现有能力。

以下为历史修订记录，待确认参数及旧管理密钥方案仅反映当时决策，已由末尾最新正式确认记录替代。

历史修订记录（仅追溯当轮范围，不作为当前待办）。本轮只修改本文件：拆分 ModelCallLimits/RunLimits 和不可变快照职责，将管理认证全部延期至 04，补齐 development/test 演示身份边界，统一 Route 单次请求体解析及 workflow_id/run_id 关联语义；同步本文件相关 Task、接口、文件规划、验收与 02 交接。其余已确认架构、3 个二级环节/6 个 Task、PostgreSQL 方案、分层和无关执行步骤均保留。未更新其他导航文档，未开始开发，未执行任何测试、代码检查、迁移、容器或模型操作；等待修订结果确认，之后继续全项目逻辑设计。

预算生命周期最终修订：仅明确 task_id 稳定、run_id 可随恢复变化、ModelCallUsage/RunUsage 按任务累计，区分任务累计模型尝试上限与单次 Gateway 额外重试上限，排除非主动等待时间，并同步配置解释、结构注释、预算职责、1.3.1 与 02 交接。其余设计和技术选型不变；本次只修改本文件，未检查开发进度、修改代码或执行测试/开发操作，整个项目继续处于纯逻辑设计阶段。

## 跨阶段最终接口收敛记录（2026-11-09）

普通身份固定获得orders:read/refunds:request/knowledge:read/memory:read/memory:write，由服务端DemoIdentity提供，经Service/Runtime传递，同ToolPolicy复检。演示用户仅访问自身偏好，Memory写入还须KNOWLEDGE/MEMORY_MANAGE、node路径及当前Task明确指令。管理权限由独立管理认证提供。

最终ChatRequest为user_id/conversation_id/message及可选input_mode/request_id。01的DemoContext不含task_id/workflow_id，02 Runtime创建或加载正式Task后在执行上下文中填入task_id及同值workflow_id。01定义准备层，02正式控制受理、Task和续接；旧workflow_id body字段422。此前记录中四字段兼容协议属于修订前历史，当前接口以本轮定义为准。仅修订设计接口，未开发。

## 2026-11-09 全项目审查第一轮整改记录

修复P1-02/P1-03。DemoContext和SubmitOptions分离，prepare_chat返回二元组，Service显式提交签名交02。01不创建正式Task或临时workflow，不直接调用旧Graph，Runtime绑定后才执行。同步1.3.2步骤、文件、验收及02交接，决策按四类整理。

六阶段、18环节、36Task保持不变。本轮仅修改Markdown设计、规范及导航，未检查实际开发进度，未修改业务代码、配置、依赖、数据库或迁移，未运行测试、代码检查、服务、容器、模型或Apifox联调。四项决策仍推荐待用户确认，设计尚未冻结。第一轮修订完成后停止，最终只读复核由用户另行授权。

## 2026-11-09 第二轮定向文档收敛记录

修改阶段边界及Task 1.1.2配置步骤。01只负责普通DemoIdentity、演示用户和会话准备，管理员单admin_api_key配置、SecretStr及compare_digest统一由04负责。01模型/数据库秘密管理保留。

第二轮修订完成，六阶段、18环节、36Task及既有八项结构不变。四项推荐决策仍待用户确认，未宣布冻结或授权实施。本轮仅修改Markdown，未检查实际开发进度，未开发、安装、测试、检查代码、操作数据库或启动/联调。最终只读复核由用户另行授权。

## 2026-11-09 最终技术决策确认与冻结准备记录

同步确认状态及04只接本地审批Actor/未来认证边界，01只准备普通身份/Schema/上下文，不新增管理认证。

用户正式确认前三项技术参数并明确延期管理员认证，已无这四项待确认决策。历史记录中的待确认或管理密钥方案仅供追溯，当前以本文规范及本记录为准。LocalDemoApprovalActor固定审计值采用local-demo-approval，沿用approver_id存储字段，不构成真实身份认证或授权。

六阶段、18环节、36Task和既有八项设计结构不变。仍为纯逻辑设计，只修改Markdown，未检查实际开发进度，未修改代码、SQL、实际配置或依赖，未安装、测试、检查代码、启动、数据库操作或联调。实施验证尚待授权，当前等待用户最终设计冻结确认，设计确认不授予任何Task开发权限。本轮完成即停止。
