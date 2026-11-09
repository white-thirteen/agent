# 01 基础工程与运行环境独立验收报告

审查日期为 2026-11-10。审查角色为独立 QA / Senior Backend Engineer。

**独立 QA 结论为有条件通过。主 Agent 复核状态为待复核，用户正式阶段验收待确认。**

本文件根据本次对话中已执行的独立审查及验证整理。报告落盘期间仅新增验收文档和 README 导航，未重新运行测试。下文测试结果均属于同一轮审查。

## 1. 总体结论

| 判断项 | 独立审查结论 |
| --- | --- |
| 是否符合 D01 | 六个 Task 的主要职责、接口及阶段边界符合设计，存在一项请求校验遗漏 |
| 是否达到无条件验收条件 | 尚未达到，存在已复现的 P2 问题，空环境重建另有验证边界 |
| 是否建议进入 02 | 建议先处理 P2-01 并定向回归，再由主 Agent 复核和用户确认 |
| 既有 78 passed 是否可信 | 已独立复现，仍有未覆盖的输入边界 |
| 问题数量 | 已确认 P0 为 0、P1 为 0、P2 为 1、P3 为 2 |

审查依据包括完整阅读的 [AGENTS.md](../../AGENTS.md)、[README](../../README.md)、[项目定位](../agent-engine-demo-plan.md)、[唯一开发路线图](../development-roadmap.md)、[D01](../01-foundation-detailed-design.md)，并对照 [D02](../02-agent-runtime-detailed-design.md) 检查交接契约。

本轮审查未修改业务代码、配置、依赖或正式迁移文件，未安装依赖、重置工作区、重建数据库或重启容器。真实测试在独立测试库执行，Session 探针只清理本轮随机测试数据。失败迁移使用临时 SQL，实际 DDL 在事务失败后回滚。审查前后双库 Session 行数均为 0。

## 2. 六个 Task 审查结果

### 2.1 Task 1.1.1 工程复用与事实基线

- 设计符合性。保留 factory、lifespan、Route → Service → Runtime → Graph 分层，复用已有主图及 SSE formatter。
- 实际实现。主要见 [README](../../README.md)、[main.py](../../app/main.py) 及既有 Service/Runtime/Graph。
- 测试覆盖。无资源 HTTP、OpenAPI、503、参数校验和 formatter 回归通过。项目解释器为 Python 3.13.7，已安装版本与 requirements.txt 核对无偏差。
- 遗留问题。全仓 Ruff 检查仍有遗留，权威定位文档存在过期状态描述。
- 验收结论。主要要求通过，保留 P3-01、P3-02。

### 2.2 Task 1.1.2 Demo 设置与运行入口

- 设计符合性。唯一 Settings 集中管理配置，秘密使用 SecretStr。池大小、次数、超时、URL 及名单有校验。缺资源时 HTTP 可存活，production 演示入口禁用。
- 实际实现。见 [config.py](../../app/core/config.py)、[errors.py](../../app/core/errors.py)、[logging.py](../../app/core/logging.py)、[main.py](../../app/main.py)、[.env.example](../../.env.example)。
- 测试覆盖。配置和应用测试通过。独立进程注入非法名单 JSON、池大小、URL 时非零退出，探针秘密未出现在输出中。不可达数据库场景 health 为 200、chat 为 503，database_status 为 unavailable。
- 遗留问题。未确认本 Task 的阻断缺陷。
- 验收结论。通过。

### 2.3 Task 1.2.1 数据库与迁移入口

- 设计符合性。固定 PG 镜像、显式 bootstrap、编号 SQL、SHA-256、事务级锁、逐迁移事务和版本检查已实现。Web 启动路径只读检查版本。
- 实际实现。见 [compose.yaml](../../compose.yaml)、[init_databases.py](../../scripts/init_databases.py)、[migrate.py](../../scripts/migrate.py)、[001](../../migrations/001_sessions.sql)、[002](../../migrations/002_deferred_thread_uniqueness.sql)。
- 测试覆盖。真实测试库验证迁移重跑、checksum 拒绝、未知版本拒绝、失败 DDL 回滚和版本登记回滚。只读核对双库实际版本、角色、表和约束。
- 遗留问题。本轮未重新创建空库、执行 bootstrap 或重启容器，交付报告中的首次初始化和 Volume 重启证据未在本轮独立复现。
- 验收结论。既有环境通过，空环境复现保留未验证项。

### 2.4 Task 1.2.2 连接与会话绑定

- 设计符合性。异步池有界初始化，失败和退出均关闭。仓储使用参数化 SQL、用户条件及两语句事务，数据库已存绑定优先。获批 002 的延迟 thread 唯一约束已生效。
- 实际实现。见 [postgres.py](../../app/infrastructure/postgres.py)、[sessions.py](../../app/infrastructure/sessions.py) 及 main 的 lifespan。
- 测试覆盖。真实 PG 完成五组新键、每组 12 路并发。跨用户同名会话隔离、异键 thread 碰撞回滚、池关闭重开均通过。额外两个独立 Python 进程取得同一持久 thread。
- 遗留问题。请求输入遗漏会影响仓储参数提交，见 P2-01。
- 验收结论。正常、并发及持久绑定要求通过。

### 2.5 Task 1.3.1 统一模型调用

- 设计符合性。Gateway 保留原生 AIMessage/ToolCall，普通和结构化调用共用次数、超时、重试及用量路径。SDK 重试关闭，未知 Token 保留 null，预期失败携带最新次数快照，取消和编程错误传播。RunLimits/RunUsage 仅定义契约。
- 实际实现。见 [model_gateway.py](../../app/runtime/model_gateway.py)、[model.py](../../app/infrastructure/model.py)、[check_model.py](../../scripts/check_model.py)、[agent_runtime.py](../../app/runtime/agent_runtime.py)。
- 测试覆盖。受控场景验证超时、重试、限额、认证失败、解析失败、未知用量及取消传播。真实 ChatOpenAI 加 MockTransport 验证工具绑定隔离。真实 DeepSeek 文本和结构化调用分别通过。
- 遗留问题。任意真实业务工具调用由 03 验收，正式节点迁移由 02 实施。
- 验收结论。通过。

### 2.6 Task 1.3.2 演示身份与管理边界

- 设计符合性。Route 唯一声明 ChatRequest，身份辅助函数接收已校验 user_id。production 优先拒绝，普通 scope 无审批权限。Service 返回 DemoContext/SubmitOptions 二元组，准备层未创建正式 Task 或调用 Graph。
- 实际实现。见 [chat.py](../../app/api/schemas/chat.py)、[dependencies.py](../../app/api/dependencies.py)、[agent.py](../../app/api/routes/agent.py)、[context.py](../../app/runtime/context.py)、[agent_service.py](../../app/services/agent_service.py)。
- 测试覆盖。身份、权限字段注入拒绝、production 禁用、Schema 和准备接口测试通过。真实 HTTP 能创建测试库 Session，再返回预期 JSON 503。
- 遗留问题。含 NUL 的 conversation_id 校验通过后触发 HTTP 500，现有测试未覆盖。
- 验收结论。有条件通过，需处理 P2-01。

## 3. 测试执行结果与可信度

### 3.1 实际执行命令

以下命令均使用项目解释器。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -c "import os, pytest; from app.core.config import Settings; os.environ['AGENT_TEST_DATABASE_URL'] = Settings().test_database_url.get_secret_value(); raise SystemExit(pytest.main(['-q']))"
.\.venv\Scripts\python.exe -m scripts.check_model
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

另使用临时内联 Python 探针执行双库只读查询、独立进程绑定、真实 Uvicorn socket 请求、资源关闭、不可达数据库退化、非法环境变量及 NUL 输入检查。探针没有保存为仓库测试文件，复现要点见第 4 节。

| 检查 | 结果 |
| --- | --- |
| 默认 pytest | 76 passed、0 failed、2 skipped |
| 显式真实测试库 pytest | 78 passed、0 failed、0 skipped |
| 真实模型脚本 | text 和 structured 分别通过，退出 0 |
| pip check | No broken requirements found |
| 已安装版本与锁定清单核对 | 无偏差 |
| Ruff lint | 退出非零，1 项 E501 |
| Ruff format | 退出非零，8 files would be reformatted、89 files already formatted |

两次 pytest 有重复覆盖，不累计为 154 个独立测试。默认跳过的两个用例均为显式启用的真实 PG 用例，本轮已单独启用并通过。

### 3.2 真实资源观察

| 项目 | 本轮实际观察 |
| --- | --- |
| Python | 项目 .venv，3.13.7 |
| PostgreSQL | 双库均为 17.6 (Debian 17.6-2.pgdg12+1) |
| 数据库与账号 | agent_demo / agent_app，agent_demo_test / agent_test |
| 角色权限 | 均非超级用户，无 CREATEDB/CREATEROLE |
| 跨库 CONNECT | 权限查询显示双方对另一数据库均无 CONNECT 权限 |
| 应用表 | 双库 public 均仅有 schema_migrations、sessions |
| 迁移 | 双库均有版本 1、2，checksum 与仓库文件一致 |
| 唯一约束 | sessions_thread_id_key 为 DEFERRABLE INITIALLY DEFERRED |
| 独立进程 | 两个新 Python 进程获得同一 user/conversation 的同一 thread |
| 真实 socket HTTP | health/docs 200，正常准备后 JSON 503 agent_not_ready，测试绑定实际存在 |
| 正常关闭 | pool.closed、同步及异步 HTTP 客户端 is_closed 均为 true |
| 数据库不可达 | 有界失败，health 200，database_status=unavailable，chat 503 |
| DeepSeek 文本 | deepseek-flash，chat，reasoning_effort=none，usage=known，累计尝试 1 |
| DeepSeek 结构化 | function_calling，reasoning_effort=none，usage=known，累计尝试 2 |
| 数据清理 | 审查前后双库 Session 行数均为 0 |

### 3.3 测试覆盖矩阵

| 设计要求 | 测试用例或检查 | 测试类型 | 是否真实资源 | 测试结果 | 覆盖评价 |
| --- | --- | --- | --- | --- | --- |
| 默认设置及名单规范化 | test_settings_defaults_and_normalization | 单元 | 否 | 通过 | 覆盖主要行为 |
| 配置秘密隐藏 | test_settings_errors_hide_inputs、环境变量探针 | 单元/独立进程 | 实际 Settings | 通过 | 包含解析失败 |
| 无资源 HTTP/503 | test_application | HTTP | 无外部资源 | 通过 | 符合退化设计 |
| DB 不可达 | 不可达端口探针 | 集成 | 实际连接失败 | 通过 | 有界、安全退化 |
| 迁移重跑/checksum/未知版本/回滚 | test_real_migrations_reentry_checksum_and_rollback | 集成 | PG | 通过 | 检查实际表及版本记录 |
| 测试库保护 | test_wrong_test_target_is_rejected_before_connecting、实际库核对 | 单元/集成 | 部分 | 通过 | 显式独立测试库成立 |
| 并发绑定及跨用户隔离 | test_real_session_concurrency_isolation_and_reopen | 集成 | PG | 通过 | 五组各 12 路，含碰撞回滚 |
| 跨进程持久绑定 | 双 Python 进程探针 | 集成 | PG | 通过 | 补足默认测试覆盖 |
| 初始化失败释放 | test_resources | 单元 | 替身 | 通过 | 包含后续初始化失败和编程错误 |
| 正常释放 | test_resources、真实 HTTP 生命周期 | 集成 | PG/实际 HTTP 客户端 | 通过 | 池和两种客户端均检查 |
| 原生 ToolCall/结构化结果 | test_native_calls_and_structured_raw_usage_are_preserved | 单元 | 模型替身 | 通过 | 保留 call_id、args、raw |
| 超时/重试/次数上限 | test_model_gateway 相关用例 | 单元 | 模型替身 | 通过 | 失败及重试共用累计次数 |
| Token 未知值 | test_partial_usage_and_retry_ceiling_do_not_manufacture_known_totals 等 | 单元 | 模型替身 | 通过 | 未知值未记零 |
| 工具绑定隔离 | test_real_langchain_tool_bindings_do_not_mutate_shared_model | 适配集成 | ChatOpenAI + MockTransport | 通过 | 检查实际请求载荷，无外部调用 |
| 真实文本及 Function Calling | scripts.check_model | 外部集成 | DeepSeek | 通过 | 分能力记录 |
| 身份/production/权限注入 | test_demo_identity | 单元/HTTP | 部分替身 | 通过 | 受控身份边界成立 |
| prepare_chat 契约及真实绑定 | 准备接口测试、socket 探针 | 单元/集成 | 部分使用 PG | 通过 | 无正式 Task 创建 |
| PG text 不支持的标识字符 | NUL 探针 | HTTP/集成 | PG | 失败 | 已确认 P2-01 |
| 空环境 bootstrap | 静态审查 | 静态 | 未重建 | 未重验 | 待主 Agent 核对采用证据 |
| 容器重启及 Volume | 既有交付记录 | 历史证据 | 本轮未重启 | 未重验 | 不计入本轮独立通过项 |

默认模型测试采用可控替身，真实 PG 测试直接连接 agent_demo_test。真实迁移用例的临时失败 SQL 验证实际回滚，Session 用例只删除随机测试用户的数据。真实模型调用由显式脚本执行。审查未发现测试以模型回复代替数据库事实断言，也未观察到遗留 Session 数据污染。

## 4. 问题清单

### P2-01 请求标识允许 NUL，触发未处理的数据库异常

状态为已确认、待主 Agent 复核、待授权整改。

代码位置为 [chat.py 第 8 行的 Identifier](../../app/api/schemas/chat.py)，以及 [sessions.py 第 46 行的参数提交](../../app/infrastructure/sessions.py)。前者只限制长度，后者向 PostgreSQL text 提交会话标识。

资源已初始化后，向 POST /agent/chat 发送以下 JSON 即可复现。验证时使用独立测试库。

```json
{
  "user_id": "dev-user",
  "conversation_id": "qa\u0000probe",
  "message": "hello"
}
```

实际观察为 ChatRequest 校验通过，prepare_chat 调用仓储后 psycopg 抛出 DataError，HTTP 返回 500、text/plain。该请求没有创建 Session 数据。

影响是外部输入能够穿过准备层校验并触发服务端错误，02 复用入口后仍会受到影响。现有 78 个测试没有覆盖此路径。

建议在外部标识校验处拒绝 PostgreSQL text 无法保存的 NUL，返回 422，并增加一个 HTTP 回归用例。演示用户配置应保持相同的标识约束。修复应集中在输入边界，避免用宽泛数据库异常捕获掩盖问题。

### P3-01 全仓 Ruff 检查仍未通过

状态为已确认、既有交付报告已披露、待主 Agent 决定处理归属。

执行第 3.1 节 Ruff 命令可复现。

- lint 位于 [supervisor.py 第 8 行](../../app/agents/prompts/supervisor.py)，E501。
- format 涉及 app/graph/nodes/response.py、app/runtime/agent_runtime.py、docs/01-foundation-detailed-design.md、docs/02-agent-runtime-detailed-design.md、docs/03-tool-governance-detailed-design.md、docs/04-hitl-checkpoint-refund-detailed-design.md、docs/05-rag-memory-detailed-design.md、docs/history/04-1-order-service-design.md，共 8 个文件。

目前没有证据表明这些格式问题影响运行，但全仓检查会非零退出。建议在后续授权范围内定向处理或明确保留状态，本轮未自动格式化。

### P3-02 权威定位文档保留过期当前状态

状态为已确认、待主 Agent 复核和同步。

[项目定位文档第 3 行](../agent-engine-demo-plan.md)仍称“尚未正式开发”“所有 Task 未获开发授权”，与 README、路线图页首和 D01 正式开发记录冲突。路线图历史状态段也保留类似描述。

复现方式为交叉阅读这些当前状态入口。影响是后续接手者容易误判实施进度。建议统一当前状态，并清楚标明历史状态段。

### P0/P1 与验证边界

本轮未发现已确认的 P0/P1。空环境 bootstrap 和容器重启属于本轮未重新验证的证据边界，未归类为代码缺陷。主 Agent 需明确采用既有证据或另行安排受授权验证。

## 5. 设计与实现偏差

| 项目 | 分类 | 判断 |
| --- | --- | --- |
| 存储不支持的标识穿过校验并返回 500 | 未批准遗漏 | 偏离外部输入校验和安全错误目标，见 P2-01 |
| PG 使用 Ubuntu 私网 VM | 已批准调整 | D01 localhost 方案已有用户授权变更 |
| 002 延迟 thread 唯一约束 | 已批准调整 | 实际约束与记录一致，并发回归通过 |
| 固定 reasoning_effort=none 和 function_calling | 已记录实现选择 | 当前 DeepSeek 组合已独立验证 |
| 旧 Supervisor 调用 raw model | 设计允许过渡 | 02 接 Gateway |
| 旧 Runtime 重算 thread、保留旧上下文 | 设计允许过渡 | 公共 HTTP 未调用该执行路径，02 迁移 |
| chat 准备成功仍返回 503 | 设计规定 | 符合 01 交付边界 |

本轮未确认其他未经批准的核心设计偏差。文档状态冲突和格式遗留单列为工程问题。

## 6. D01 第 8 节阶段验收矩阵

| 门禁 | 本轮判断 | 依据及边界 |
| --- | --- | --- |
| 工程/配置 | 通过 | 无资源 HTTP、非法配置安全失败、未就绪 503 |
| PG 环境 | 既有环境通过，重建验证保留 | 双库、PG17.6、版本表、重跑和回滚实际通过，bootstrap/容器重启未重验 |
| 生命周期 | 通过 | 正常关闭、部分初始化失败清理、真实 socket 启停 |
| Session | 通过 | 同键并发、跨用户隔离、重开及独立进程读取 |
| 请求准备边界 | 有条件通过 | 唯一解析、context/options 和 Task 边界成立，NUL 输入失败 |
| 模型网关 | 通过 | 原生 ToolCall、解析错误、次数、超时、重试、未知用量 |
| 真实模型 | 通过 | DeepSeek 文本及结构化分别成功 |
| 演示身份/隔离 | 通过 | 名单、production 禁用、普通 scope 无审批权 |
| 文档 | 部分通过 | 主要运行说明符合事实，存在 P3 状态冲突 |

## 7. 阶段边界与进入 02 的风险

01 提供的 DemoContext/SubmitOptions、SessionRepository、ModelGateway 及两类 Limits/Usage 能与 D02 预期衔接。Gateway 成功和预期失败均返回模型次数快照，thread 有持久来源，资源具有明确生命周期。

本轮检查未发现新增正式 Task 生命周期、工具治理、独立 SSE 执行、退款审批、持久 Saver、Store 或 RAG 的提前实施。旧 Supervisor 和内存 Saver 保留，公共 HTTP 停在准备层。Session 跨进程证据仅证明绑定持久化，Graph 重启恢复需 04 单独验收。

02 需按既定设计完成 Runtime 唯一创建 Task、使用持久 thread、节点接 Gateway、任务累计预算、thread 互斥及独立执行。旧 Runtime 异常全文日志也按原责任在 02 迁移时处理。

已确认会直接带入 02 的风险为 P2-01。全仓检查遗留和文档状态冲突也应保持可追踪。

## 8. 最终建议与主 Agent 待处理项

独立 QA 建议为有条件通过。进入 02 前先处理 P2-01 并定向回归，由主 Agent 复核技术结果，再由用户确认阶段及后续授权。

| 编号 | 待处理内容 | 当前状态 | 完成证据 |
| --- | --- | --- | --- |
| A01 | 复核 P2-01，确认整改方案与归属 | 待主 Agent 复核 | 复现结论及处理决定 |
| A02 | 获授权后修复标识边界并定向回归 | 待授权 | NUL 返回 422，正常准备保持预期 JSON 503 |
| A03 | 明确 bootstrap/容器重启采用的证据范围 | 待主 Agent 复核 | 接受既有证据或安排独立验证的记录 |
| A04 | 决定 P3-01、P3-02 的处理归属 | 待主 Agent 复核 | 修复记录或明确保留理由 |
| A05 | 提交阶段验收及进入 02 的建议 | 待前项处理及用户确认 | 主 Agent 结论、用户阶段确认和后续授权 |

### 主 Agent 复核记录

待填写复核日期、复核范围、问题认定、整改授权、复测证据及阶段结论。当前问题均未在本轮修复，02 尚未启动。
