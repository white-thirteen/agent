# Agent Engine Demo

项目方向调整为轻量多 Agent Demo，以 ToolRegistry、HITL、持久化 Checkpoint/Interrupt/Resume、RAG、Store 五项工程能力为核心。Supervisor 分派给 OrderAgent、RefundAgent、KnowledgeAgent；订单和退款使用有真实本地状态的模拟服务，不涉及真实资金。

**当前状态为逻辑设计阶段已完成，正式开发阶段待新会话接手。** 六阶段、18个二级环节、36个Task及D01～D06已获用户最终确认，作为正式开发设计基线。development-roadmap.md是唯一有效开发路线图，已确认技术决策不再待议，V1范围外能力按规划延期。本次最终确认覆盖此前文档的待审核、待整改及待冻结状态，历史记录保留。设计确认不代表Task实现或验收，开发由用户在新会话正式授权。

以下运行方法和请求示例保留此前实现记录，本轮未重新检查开发进度。此前已有HTTP分层骨架、State/类型、Supervisor及专业wrapper，使用进程内InMemorySaver，真实模型及专业业务尚无本轮验收结论。01～06设计不代表已实施，持久恢复、真实向量RAG和跨会话Store须按未来实际证据验收。本轮仅整改Markdown契约、状态及导航，未执行开发或测试。

Memory设计范围已区分V1与V2。V1仅两项长期偏好，由共享MemoryReader及MemoryManager提供跨会话/跨Thread持久读写，显式用户命令通过既有MemoryManage与统一工具治理；版本、幂等和unknown处理保留。MemoryWriter仅V2智能候选维护预留，V1不实现或自动写记忆，详见D05第2.2节。

归档说明依据本页“逻辑设计阶段正式收尾记录”及AGENTS.md同名记录。D01、D02、D03、D04、D05、D06及跨阶段契约均已最终确认，设计正文保留的“等待最终冻结”“纯逻辑设计”等轮次文字仅作历史追溯，实施仍需独立授权。

## 本地运行（PowerShell）

在项目根目录执行：

```powershell
# 首次配置，保留已有 .env。
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}

# 当前 .venv 已使用 Python 3.13.7 安装依赖。
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/health>
- `POST /agent/chat`：模型配置完整时可执行 Supervisor 路由和澄清并通过 SSE 返回；
  未配置模型时开流前返回 HTTP 503，错误码 `agent_not_ready`。
- 工作流接口尚未注册，预留模块不会返回模拟业务结果。

`/health` 表示 HTTP 服务存活；`agent_ready` 表示模型配置并构建了 Supervisor 图，
不代表专业 Agent 已实现。未配置模型时 HTTP 服务仍可启动。数据库设置仍为预留项。

开发期请求示例（可粘贴至 Apifox）：

> 以下为当前已有代码的旧协议示例，仅用于说明此前实现行为，不代表V1目标接口。01负责最终ChatRequest Schema和Route唯一请求解析，02负责正式Task受理、Runtime提交及Graph执行接线，目标公共请求不接收workflow_id。task_id仅由AgentRuntime创建，workflow_id仅为内部同值兼容别名。

```json
{
  "user_id": "dev-user",
  "conversation_id": "conversation-1",
  "workflow_id": "workflow-1",
  "message": "你好"
}
```

目前身份字段仅用于受控本地模拟，不构成生产认证；Apifox只模拟后端调用，独立Java业务系统不在V1范围。V1审批通过development/test本地入口由服务端Actor审计，普通聊天不能批准；真实管理员认证延期，production禁用演示入口。

## 重建环境

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.in` 记录直接依赖，`requirements.txt` 记录当前 Windows / Python 3.13
环境解析出的全部固定版本，包含测试工具。变更依赖时修改直接依赖清单、重新安装并验证，
然后更新固定版本清单；`pip freeze` 本身不会移除不再需要的包。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

测试中的 Runtime 替身只用于验证 SSE 传输与请求隔离，应用不会返回替身响应。

## 开发文档

旧入口 [环境搭建归档指引](docs/01-environment-and-scaffold.md) 保留历史链接。[最初架构说明](docs/architecture.md) 与 [旧第二步模型计划](docs/02-real-model-chat.md) 仅供历史追溯，其未实现及待开发描述不代表本快照当前能力，当前启动、请求和实现边界以本README为准。

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
