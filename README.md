# Agent Engine Demo

> 当前状态为01 已获用户正式验收，归档快照验证中，02 尚未启动。以下开发、QA及历次处理记录保留原有日期和语境；历史待批准文字不覆盖本条当前状态。

轻量多 Agent Demo，采用 Supervisor 与 Order / Refund / Knowledge 专业 Agent。V1 围绕工具治理、HITL、持久恢复、真实向量 RAG 和用户隔离 Store 展开，订单/退款采用本地模拟业务。

## 当前状态

2026-11-09 已实施一级阶段 01 的六个 Task，验收证据和遗留见 [01 阶段交付报告](docs/01-foundation-detailed-design.md#01-正式开发交付报告2026-11-09)。2026-11-10 独立 QA 结束，P2-01 修复及独立回归经主 Agent 复核通过并关闭，阶段状态为 VERIFIED，正式验收待用户批准，详见 [复核决定与阶段状态](docs/question/01-foundation-main-review.md)。02 尚未开始。

当前提供配置、安全错误、HTTP 存活/准备层状态、PostgreSQL 双库与显式迁移、连接池、持久 Session、ModelGateway、普通演示身份和请求准备层。已有主图/映射和 SSE formatter 复用，内存 Saver 保留。专业业务、正式 Task、独立执行与订阅、持久 Checkpoint、审批、RAG 和 Store 按后续阶段实施。

`POST /agent/chat` 在 01 完成身份与 session 准备后返回 JSON 503 `agent_not_ready`。正式受理/Graph/SSE 接线交给 02。HTTP 会校验最终请求格式，旧 workflow_id 字段返回 422。

## 本地运行（PowerShell）

在项目根目录使用 `.venv` Python 3.13.7，单 worker 启动。保留已有 `.env`。

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --loop app.infrastructure.postgres:selector_event_loop
```

Windows 的 psycopg 异步连接需要 Selector loop，已按当前安装源码和实际启动验证。开发可添加 `--reload`，进程重启验收使用上面的无 reload 命令。

- [接口文档](http://127.0.0.1:8000/docs)
- [存活与准备层状态](http://127.0.0.1:8000/health)

无模型或数据库配置也能检查 HTTP 存活。`database_status` 为 not_configured / unavailable / ready，ready 要求实际连接和 schema 版本检查成功。`model_status` 为 not_configured / initialized，初始化不探测模型网络。`agent_ready` 表示 development/test 下图与持久 session 资源已初始化，只反映准备层资源状态。生产环境恒为 false。运行中 DB 故障在开流前返回 `session_unavailable`。

请求示例仅会执行准备层。

```json
{
  "user_id": "dev-user",
  "conversation_id": "conversation-1",
  "message": "你好",
  "input_mode": "auto"
}
```

三个必填字段为 user_id / conversation_id / message，可选 input_mode 为 auto 或 new_task，可选 request_id 为 UUID。thread、scope、task、workflow 由服务端负责，额外请求字段拒绝。用户限 development/test 的受控名单，普通 scope 不含审批权限。此演示身份适用于受控本地环境。

## 数据库环境与显式迁移

本次实际使用 Ubuntu 私网虚拟机 `192.168.150.101:5432`。PG17.6 镜像固定到 digest，部署位于 `/home/white7/agent-engine-demo-db`，独立 Volume 为 `agent-engine-demo-db_agent_pg17`。HBA 只允许 Windows `192.168.150.1`，应用库 agent_demo / owner agent_app，测试库 agent_demo_test / owner agent_test。已验证容器重启持久化、双库连接与交叉连接拒绝。

本地 `.env` 已保存三个数据库连接项并被 Git 忽略，密码不进入文档。Web 只读取普通连接设置，管理 URL 仅由显式 bootstrap 读取。已有 `.env` 的应用名覆盖值保留，本次真实 health 的 service 因此仍为 Agent Backend，新配置默认值为 Agent Engine Demo。

仓库 `compose.yaml` 提供本机 localhost PG 环境，端口、bootstrap 用户和密码从本地环境注入。

```powershell
docker compose up -d --wait
.\.venv\Scripts\python.exe -m scripts.init_databases
.\.venv\Scripts\python.exe -m scripts.migrate --target development
.\.venv\Scripts\python.exe -m scripts.migrate --target test
```

init_databases 仅接受同一配置端口上的本地固定双库和 owner。虚拟机已通过 SSH 初始化，日常 Windows 连接虚拟机时直接执行两个迁移命令。经用户授权的临时 localhost 转发已用于 bootstrap 两次幂等重跑验证，验证后已关闭。该脚本不接受现有私网 URL 直接初始化远端。

应用启动只读检查版本，迁移由开发者显式执行。当前版本为 2，001 创建 sessions，002 按用户确认将 thread_id 唯一约束延迟到事务提交，修复相同 uuid5 候选的并发冲突。已应用 SQL 保留原样，后续修正新增编号。每个迁移事务与登记绑定，重跑检查 SHA-256，未知版本/已修改文件拒绝继续。

停止本地容器可使用 `docker compose stop`，具名卷保存数据。Session 仅持久绑定 thread，图快照在后续 04 接入。

## 模型验证与调用边界

ModelGateway 提供普通/工具绑定及结构化调用。SDK 重试关闭，网关统计包含失败和重试的任务累计模型尝试次数，单次调用按配置限制超时和额外重试。Token 缺失保持 unknown/null，成功和可预期错误都返回新用量快照，取消及编程错误继续传播。

当前真实联调使用本地已配置的 DeepSeek deepseek-flash，通过 ChatOpenAI 适配，结构化方法固定为 function_calling，reasoning_effort 固定为 none。该供应商在 thinking 模式拒绝强制工具选择，模式选择和首次失败已记录于交付报告。更换供应商/模型后重新显式验证其兼容性。

```powershell
.\.venv\Scripts\python.exe -m scripts.check_model
```

此命令显式调用真实模型，使用固定无隐私文本和 RouteDecision，可能产生费用。默认测试使用受控模型。启动和 health 不调用模型网络。Supervisor 在 02 切换到 Gateway，RunLimits/RunUsage 在 01 只定义数据契约，Runtime 的任务累计主动时长、工具预算与恢复继承按 02–04 接线。

## 环境重建与验证

`requirements.in` 维护直接依赖，`requirements.txt` 保留已验证版本。本阶段未安装或升级依赖；requirements.in 显式声明已安装并锁定的 openai，用于 Gateway 捕获供应商错误，requirements.txt 保留原验证版本。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

真实 PostgreSQL 测试要求显式测试 URL，默认不会仅因 `.env` 存在就访问数据库。可使用已配置设置显式启用，进程退出后环境随之释放。

```powershell
.\.venv\Scripts\python.exe -c "import os, pytest; from app.core.config import Settings; os.environ['AGENT_TEST_DATABASE_URL'] = Settings().test_database_url.get_secret_value(); raise SystemExit(pytest.main(['-q']))"
```

全仓检查保留此前用户文件中的 lint/格式问题，具体文件及本阶段定向检查结果见交付报告。SSE formatter 的传输回归在独立测试应用中保留，正式 /agent/chat 按 01 准备层边界验证。

## 开发文档

旧入口 [环境搭建归档指引](docs/01-environment-and-scaffold.md) 保留历史链接。[最初架构说明](docs/architecture.md) 与 [旧第二步模型计划](docs/02-real-model-chat.md) 仅供历史追溯，其未实现及待开发描述不代表本快照当前能力，当前启动、请求和实现边界以本README为准。

- [分阶段独立验收、主 Agent 复核及修复任务](docs/question/README.md)
- [修复会话提示词与修复记录](docs/resume/README.md)
- [01 / P2-01 修复与开发自测报告](docs/resume/record/01-foundation-fix-report.md)
- [项目定位、架构与V1范围（权威文档）](docs/agent-engine-demo-plan.md)
- [唯一有效的V1路线图：六阶段、18个二级环节、36项三级任务](docs/development-roadmap.md)
- [01 正式设计基线——工程、PostgreSQL、模型与普通演示身份](docs/01-foundation-detailed-design.md)
- [02 正式设计基线——Supervisor、三专业Subgraph、Runtime与SSE](docs/02-agent-runtime-detailed-design.md)
- [03 正式设计基线——ToolRegistry、Policy、Executor与模拟订单](docs/03-tool-governance-detailed-design.md)
- [04 正式设计基线——HITL、PG Checkpoint、原调用恢复与退款幂等](docs/04-hitl-checkpoint-refund-detailed-design.md)
- [05 正式设计基线——生成式RAG、来源校验、Store与Memory V1](docs/05-rag-memory-detailed-design.md)
- [06 正式设计基线——完整演示装配、故障验收与最终交付](docs/06-integration-and-final-delivery-detailed-design.md)
- [当前代码的 Graph 协议参考](docs/graph-protocol.md)
- [历史资料索引：旧九阶段路线图与阶段设计（不再作为V1依据）](docs/history/README.md)
- [Agent Engine Demo 开发规范](AGENTS.md)

新会话先读AGENTS.md，再读项目定位、六阶段路线图及D01，按当前授权Task需要查阅后续设计和Graph既有协议。获得正式开发授权后，从路线图第一个满足依赖条件的Task开始，初始起点为1.1.1「工程复用与事实基线」。后续按依赖和授权顺序推进，每项交付记录实现、验证及遗留。

旧九阶段路线图及旧阶段设计已统一归档至 `docs/history/`，只供历史参考，不自动带入新V1要求；graph-protocol.md继续保留在docs根目录，仅描述当前代码，不能当作目标架构已实现。历史技术方案需经当前阶段评估采纳后复用。各阶段设计现已获最终确认，具体开发顺序与范围由用户在新会话授权，设计基线不代表实现、测试或联调完成。

以下为历史修订记录，待确认参数及旧管理密钥方案仅反映当时决策，已由末尾最新正式确认记录替代。

## 2026-11-09 全项目审查第一轮整改记录

同步当前设计整改状态与01～06导航，补06入口。运行及旧请求示例保留此前实现记录，后续真实协议迁移归02及06交付。

六阶段、18环节、36Task保持不变。本轮仅修改Markdown设计、规范及导航，未检查实际开发进度，未修改业务代码、配置、依赖、数据库或迁移，未运行测试、代码检查、服务、容器、模型或Apifox联调。四项决策仍推荐待用户确认，设计尚未冻结。第一轮修订完成后停止，最终只读复核由用户另行授权。

## 2026-11-09 第二轮定向文档收敛记录

仅在旧Apifox ChatRequest示例附近补充协议说明，原JSON不变。旧workflow_id字段属于此前实现，V1目标接口移除，正式协议在02实施时迁移，task_id仅Runtime创建。

第二轮修订完成，六阶段、18环节、36Task及既有八项结构不变。四项推荐决策仍待用户确认，未宣布冻结或授权实施。本轮仅修改Markdown，未检查实际开发进度，未开发、安装、测试、检查代码、操作数据库或启动/联调。最终只读复核由用户另行授权。

## 2026-11-09 最终技术决策确认与冻结准备记录

旧ChatRequest JSON保留，说明01负责最终Schema与Route唯一解析，02负责正式Task受理及Runtime/Graph接线。同步确认状态及V1本地审批Actor、延期认证边界。

用户正式确认前三项技术参数并明确延期管理员认证，已无这四项待确认决策。历史记录中的待确认或管理密钥方案仅供追溯，当前以本文规范及本记录为准。LocalDemoApprovalActor固定审计值采用local-demo-approval，沿用approver_id存储字段，不构成真实身份认证或授权。

六阶段、18环节、36Task和既有八项设计结构不变。仍为纯逻辑设计，只修改Markdown，未检查实际开发进度，未修改代码、SQL、实际配置或依赖，未安装、测试、检查代码、启动、数据库操作或联调。实施验证尚待授权，当前等待用户最终设计冻结确认，设计确认不授予任何Task开发权限。本轮完成即停止。

## 2026-11-09 Memory V1与V2职责收敛记录

增加Memory V1/V2范围说明及D05导航描述，避免把未来MemoryWriter当作V1运行或显式写入的必要组件。

V1保留AsyncPostgresStore、两偏好字段、用户Namespace、跨会话/跨Thread、revision、operation_id/digest/expected_revision/last_mutation、per-user锁及conflict/unknown和原Checkpoint写前边界。显式解析独立于V2，旧记录中的Writer为当时V1写路径称谓，现已统一为MemoryManager及显式命令流程，不代表V2已实现。

六阶段、18环节、36Task和八项设计结构保持，5.3.2仅授权更名，无新增Agent、Graph或Task。此前四项最终技术决策不变。本轮仅改Markdown，未检查开发进度，未修改Python/SQL/依赖/配置，未测试、迁移或联调；实现及冻结不在本轮授权内，完成后停止并提交用户审核。

## 逻辑设计阶段正式收尾记录

用户已最终确认六阶段、18环节、36Task、D01～D06及跨阶段契约。逻辑设计阶段正式结束，开发待新会话接手；初始开发起点为1.1.1，实施须另行授权。本次仅更新状态、阅读指引及必要导航，详细设计、路线图及历史资料保留，未执行开发、测试、迁移、启动或联调。
