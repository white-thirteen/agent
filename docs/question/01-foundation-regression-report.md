# 01 阶段 P2-01 独立 QA 回归报告

回归日期为 2026-11-10。关联阶段为 01「基础工程与运行环境」，关联 Task 为 1.1.2、1.3.2，原问题编号为 P2-01。

**独立回归通过，建议关闭 P2-01。完整真实测试库回归已独立核验为 82 passed、0 failed、0 skipped。主 Agent 复核及用户正式阶段验收待完成。**

## 1. 任务、依据与范围

本轮按 [独立回归任务](01-foundation-regression-task.md) 执行，核对 [原始验收报告](01-foundation-acceptance.md)、[主 Agent 复核及第 6 节修复复核](01-foundation-main-review.md)、[修复授权提示词](../resume/01-foundation-fix-task.md)、[开发修复报告](../resume/record/01-foundation-fix-report.md)。同时阅读 AGENTS.md、README、有效定位及路线图、D01 第 8 节及正式开发交付报告。

本轮独立执行代码审查、受影响测试、一次完整真实库回归、真实 PG 与 ASGI/lifespan 探针及 Ruff 检查。仅新增本 QA 报告，保留原始问题与修复记录。被测业务代码、配置、依赖和正式迁移文件保持本轮开始时内容。未调用付费模型、重建数据库、重启容器或执行 Git 归档。

开始时 Git 工作区已有大量未提交、删除和未跟踪文件，涉及历史 Graph、设计、01 实现与协调文档。对 HEAD 的完整差异不能全部归属于 P2-01 修复。本轮依据实际修复位置、授权任务和既有审查证据核对范围。

## 2. 实际审查文件与修复判断

| 文件 | 审查内容 | 判断 |
| --- | --- | --- |
| [app/api/schemas/chat.py](../../app/api/schemas/chat.py) | Identifier 第 9 行新增排除 NUL 的 pattern，保留 1～128 长度与全局 str_strip_whitespace | 校验发生在请求解析边界，两个标识共用规则 |
| [app/core/config.py](../../app/core/config.py) | normalize_users 在原去空、去重、长度校验后拒绝 NUL | 错误文本固定，继续隐藏配置输入 |
| [tests/test_demo_identity.py](../../tests/test_demo_identity.py) | 新增两个标识 NUL 场景及 Unicode/空白场景 | 断言 422、错误字段、prepare_chat 零调用及合法规范化 |
| [tests/test_config.py](../../tests/test_config.py) | Unicode 名单规范化及 NUL 错误输入隐藏 | 覆盖修复配置边界 |
| [app/api/routes/agent.py](../../app/api/routes/agent.py)、[dependencies.py](../../app/api/dependencies.py) | 唯一解析、环境/名单及 scope | 原身份和权限边界保留 |
| [app/services/agent_service.py](../../app/services/agent_service.py) | prepare_chat、context/options 和候选 run_id | 仍只准备数据，正常路径访问真实仓储 |
| [app/infrastructure/sessions.py](../../app/infrastructure/sessions.py)、[postgres.py](../../app/infrastructure/postgres.py) | SQL、异常、绑定和测试库保护 | 未新增宽泛 DataError 捕获，原持久绑定契约保留 |
| [app/main.py](../../app/main.py)、[tests/test_postgres.py](../../tests/test_postgres.py) | 实际资源生命周期、真实库测试和清理 | 本轮真实验证使用原正式装配 |

pattern 仅排除已确认的 NUL 字符，正常 Unicode 仍可用。长度、空白规范化、名单去重继续成立。未发现修复扩大到 Session 算法、迁移、正式 Task、Graph 执行或后续工具/审批/持久 Checkpoint/RAG/Store。

## 3. 命令与独立执行结果

### 3.1 受影响测试和代码检查

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_config.py tests/test_demo_identity.py tests/test_application.py
.\.venv\Scripts\python.exe -m ruff check app/api/schemas/chat.py app/core/config.py tests/test_config.py tests/test_demo_identity.py
.\.venv\Scripts\python.exe -m ruff format --check app/api/schemas/chat.py app/core/config.py tests/test_config.py tests/test_demo_identity.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check . --output-format concise
```

| 检查 | 本轮实际结果 |
| --- | --- |
| 受影响测试 | 22 passed in 2.80s，退出 0 |
| 四个修复文件 lint | All checks passed，退出 0 |
| 四个修复文件 format | 4 files already formatted，退出 0 |
| 全仓 lint | 原有 1 项 E501，退出 1 |
| 全仓 format | 原有 8 files would be reformatted、97 files already formatted，退出 1 |

### 3.2 完整真实测试库回归

实际通过以下内联入口先校验测试目标，再启用完整测试。连接信息由本地 Settings 读取，输出仅包含实际库名、账号和行数。

```powershell
@'
import os, pytest, psycopg
from app.core.config import Settings
from app.infrastructure.postgres import validate_test_target,connection_kwargs
from scripts import run_async
s=Settings();validate_test_target(s.test_database_url,s.database_url)
async def preflight():
 async with await psycopg.AsyncConnection.connect(**connection_kwargs(s.test_database_url)) as c:
  await c.execute('SET TRANSACTION READ ONLY')
  cur=await c.execute('SELECT current_database(), current_user, count(*) FROM sessions');row=await cur.fetchone()
  assert row[0]=='agent_demo_test';print('preflight',row)
run_async(preflight())
os.environ['AGENT_TEST_DATABASE_URL']=s.test_database_url.get_secret_value()
raise SystemExit(pytest.main(['-q']))
'@ | .\.venv\Scripts\python.exe -
```

预检输出为 `('agent_demo_test', 'agent_test', 0)`。完整结果为 **82 passed in 6.65s，退出 0，无失败或跳过**。该结果独立核实了开发报告中的 82 项结论。

真实库用例直接访问 agent_demo_test，覆盖迁移重跑/checksum/未知版本/失败回滚，以及五组各 12 路并发、跨用户隔离、thread 碰撞回滚和池重开。测试只清理随机测试用户数据，失败迁移的临时 DDL 在事务中回滚。受影响测试与完整测试有重复覆盖，数量分别记录。

## 4. 真实 HTTP、数据库与配置证据

### 4.1 环境及观测方式

另执行临时内联 Python 探针，使用实际 create_app、Service、SessionRepository、数据库池和模型客户端初始化。连接前调用 validate_test_target，查询 current_database() 并断言为 agent_demo_test。

HTTP 使用 TestClient 的进程内 ASGI 传输，真实 lifespan 启停，Windows 显式设置 SelectorEventLoop。通过 patch.object(service, 'prepare_chat', wraps=service.prepare_chat) 观察原方法，正常请求仍执行原 Service 和仓储。未使用替身返回绑定或业务结果。

开始请求前实际 health 为 database_status=ready、model_status=initialized、agent_ready=true，启动日志为 preparation_ready=True。避免资源未就绪的 503 掩盖修复行为。

### 4.2 原始错误路径

原始请求的 conversation_id 由 qa、一个实际 NUL、probe 组成，JSON 表示如下。

```json
{"user_id":"dev-user","conversation_id":"qa\u0000probe","message":"hello"}
```

另验证 user_id 含实际 NUL、conversation_id 为本轮随机标识。

| 场景 | HTTP | 错误定位 | prepare_chat 累计调用 | Session 行数变化 |
| --- | --- | --- | --- | --- |
| 原始 conversation_id NUL | JSON 422 | body / conversation_id | 0 | 0 |
| user_id NUL | JSON 422 | body / user_id | 0 | 0 |

两个响应均为 application/json。每次非法请求后直接查询真实库，均与请求前状态一致。原先的 DataError/HTTP 500 已在请求解析边界消除。

### 4.3 正常准备路径与规范化

继续使用同一就绪应用和 wraps 观测，发送两次合法请求。

- 默认用户 dev-user，conversation_id 为本轮随机 qa-regression 标识。
- 本轮应用配置允许的 Unicode 用户“演示用户”，conversation_id 为同一随机前缀加中文后缀。

两次请求均给 user_id/conversation_id/message 添加首尾空格。实际 prepare_chat 参数均已去除首尾空格，Unicode 原值保留。两次均返回 application/json、503、error.code=agent_not_ready，prepare_chat 累计调用为 2。

随后真实 SQL 查询得到两个 user/conversation 持久绑定，两个 thread 不同，Session 总行数由 0 增至 2。该证据确认合法请求实际执行准备层和持久仓储。

### 4.4 配置与长度补充检查

- 含 NUL 的 demo_user_ids 构造 Settings 时抛 ValidationError，定位 demo_user_ids。
- str(error) 不包含本轮 qa-private-probe 探针输入。
- Unicode 名单的去空、首尾空白去除和去重正常，得到“演示用户”和 dev-user。
- 对 user_id、conversation_id 分别直接构造 ChatRequest，1 和 128 个 Unicode 字符通过，0 和 129 个字符拒绝。

### 4.5 精确清理与释放

本轮探针使用 finally 按两个确切 user_id/conversation_id 删除自身绑定。清理后自身剩余为 0，Session 总行数恢复为 0，与完整回归预检及 HTTP 探针前一致。

真实 lifespan 退出后，pool.closed、同步 HTTP 客户端 is_closed、异步 HTTP 客户端 is_closed 均为 true。上述断言全部通过，探针退出 0。

## 5. 问题关闭建议与遗留

### P2-01

独立回归通过，建议主 Agent 关闭。证据覆盖两个请求标识的 422、正确字段定位、prepare_chat 零调用、数据库零新增、正常持久准备、Unicode/空白/长度保留及配置拒绝和输入隐藏。

### P3-01

继续按主 Agent 既定决定作为非阻塞遗留追踪。全仓 lint 仍仅为 app/agents/prompts/supervisor.py 第 8 行 E501。format 仍为以下 8 个文件。

- app/graph/nodes/response.py
- app/runtime/agent_runtime.py
- docs/01-foundation-detailed-design.md
- docs/02-agent-runtime-detailed-design.md
- docs/03-tool-governance-detailed-design.md
- docs/04-hitl-checkpoint-refund-detailed-design.md
- docs/05-rag-memory-detailed-design.md
- docs/history/04-1-order-service-design.md

本轮检查时已格式化数量为 97，新增 Markdown 文件影响扫描数量，未观察到新增格式失败文件。

### P3-02 与新问题

已核对定位页首及历史基线标签、README 和主 Agent 最新协调记录，原状态冲突已由主 Agent 修正，原始 QA 文档继续保留当时结论。本轮未发现新的需要编号的回归问题。

## 6. D01 第 8 节矩阵更新建议

| 门禁 | 独立 QA 更新建议 | 本轮或采用证据 |
| --- | --- | --- |
| 工程/配置 | 通过，保留 P3-01 | 受影响及完整回归通过，NUL 配置拒绝，四文件检查通过 |
| PG 环境 | 维持通过，保留证据边界 | agent_demo_test 实际目标已核验，真实迁移和 Session 测试通过；bootstrap/Volume 沿主 Agent 已接受证据 |
| 生命周期 | 通过 | 本轮真实 lifespan，池及两种 HTTP 客户端关闭断言通过 |
| Session | 通过 | 真 PG 既有集成回归及两个正常 HTTP 绑定、精确清理通过 |
| 请求准备边界 | 从待修复更新为通过 | 两类 NUL 请求 JSON 422、零准备调用、零新增；正常 JSON 503 和实际绑定成立 |
| 模型网关 | 维持通过 | 完整回归覆盖既有可控用例，修复未改变 Gateway |
| 真实模型 | 沿用既有通过证据 | 本轮仅初始化客户端，采用主 Agent 已接受的开发及首次独立 QA 证据 |
| 演示身份/隔离 | 通过 | 名单 NUL 修正、合法 Unicode、production/scope 回归及不同用户 thread 通过 |
| 文档 | 当前入口已同步 | P3-02 修正核对通过，历史报告保留 |

## 7. 验证边界与最终交接

本轮 HTTP 为真实应用生命周期加进程内 ASGI，未重复独立 Uvicorn socket 验证。真实 PG 已使用，模型网络、bootstrap、容器重启和 Volume 验证采用主 Agent 第 1 节明确接受的既有证据。Graph 持久恢复和正式 Task/独立 SSE 执行仍按后续阶段实施。

技术结论为 P2-01 独立回归通过，82 项完整真实库测试已核验，未发现新增阻塞问题。建议主 Agent 复核本报告后记录问题关闭及 VERIFIED 建议。正式阶段验收、进入 02 和 Git 归档继续等待用户批准，当前协调文档和原始 QA 报告未在本轮改写。
