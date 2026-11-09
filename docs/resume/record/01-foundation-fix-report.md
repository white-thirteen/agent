# 01 基础阶段 P2-01 修复报告

## 关联与交付状态

- 日期为 2026-11-10。
- 对应任务为 [01 修复会话任务](../01-foundation-fix-task.md)，问题编号为 P2-01。
- 关联阶段 01 的 Task 1.3.2「演示身份与管理边界」及 Task 1.1.2「Demo 设置与运行入口」。
- 裁决依据为 [主 Agent 复核](../../question/01-foundation-main-review.md)，原始证据见 [独立 QA 报告](../../question/01-foundation-acceptance.md)。
- 本轮完成修复及开发自测，交由主 Agent 复核，再安排独立 QA 回归。阶段正式验收与进入 02 的决定由主 Agent 和用户按既定流程处理。

## 根因与修复行为

原 ChatRequest 的 Identifier 仅限制长度，允许实际 NUL 字符进入 conversation_id。资源就绪时，prepare_chat 将该标识交给 SessionRepository，psycopg 向 PostgreSQL text 提交参数时抛出 DataError，最终 HTTP 返回 500。Settings.demo_user_ids 同样遗漏 NUL 限制。

本轮在共用 Identifier 的 Field 增加仅排除 NUL 的 pattern，user_id 和 conversation_id 在请求解析时返回 JSON 422。配置名单在既有规范化与去重后检查 NUL，抛出固定文本的 ValueError，沿用 hide_input_in_errors。其余长度限制、正常 Unicode、首尾空白去除、空名单项过滤、名单去重及请求字段契约继续由原逻辑处理。

## 本轮修改文件与职责

| 文件 | 本轮具体修改 |
| --- | --- |
| app/api/schemas/chat.py | Identifier 增加 NUL 排除正则及 PostgreSQL text 约束注释 |
| app/core/config.py | normalize_users 增加名单 NUL 校验 |
| tests/test_demo_identity.py | 两个参数化 HTTP 场景验证 NUL 返回 422、字段定位及 prepare_chat 零调用；一个 Unicode/空白场景验证规范化及 JSON 503 |
| tests/test_config.py | 复用既有正常与错误场景，增加 Unicode 名单规范化、NUL 配置拒绝及错误输入隐藏断言 |
| docs/resume/record/01-foundation-fix-report.md | 本轮修复与验证证据 |
| docs/resume/README.md、README.md | 增加报告导航 |

开始时工作区已有大量已修改、删除及未跟踪文件。本轮在其基础上定向增量修改，Git 对 HEAD 的完整差异包含此前成果，不能全部归属于本修复。

本轮未执行 Git Commit/Push，阶段状态由主 Agent 后续复核维护。

## 验证命令与结果

所有 Python 命令使用项目 `.venv`。受影响测试先执行，随后仅执行一次完整 pytest，并显式启用真实测试库。

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_config.py tests/test_demo_identity.py tests/test_application.py
.\.venv\Scripts\python.exe -c "import os, pytest; from app.core.config import Settings; os.environ['AGENT_TEST_DATABASE_URL'] = Settings().test_database_url.get_secret_value(); raise SystemExit(pytest.main(['-q']))"
.\.venv\Scripts\python.exe -m ruff check app/api/schemas/chat.py app/core/config.py tests/test_config.py tests/test_demo_identity.py
.\.venv\Scripts\python.exe -m ruff format --check app/api/schemas/chat.py app/core/config.py tests/test_config.py tests/test_demo_identity.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

| 检查 | 实际结果 |
| --- | --- |
| 受影响配置、身份及 HTTP 测试 | 22 passed，退出 0 |
| 完整 pytest，含显式真实 PG 测试 | 82 passed，0 failed，0 skipped，退出 0 |
| 四个修改文件的 Ruff lint | All checks passed，退出 0 |
| 四个修改文件的 Ruff format | 4 files already formatted，退出 0 |
| 全仓 Ruff lint | 1 项既有 E501，退出 1 |
| 全仓 Ruff format | 8 files would be reformatted、95 files already formatted，退出 1 |

全仓检查的遗留与已登记 P3-01 一致。lint 位于 app/agents/prompts/supervisor.py 第 8 行。format 涉及 app/graph/nodes/response.py、app/runtime/agent_runtime.py、D01～D05 及 docs/history/04-1-order-service-design.md。

## 真实 HTTP 与数据核对

另外通过 PowerShell here-string 管道至 `.\.venv\Scripts\python.exe -` 执行临时内联探针。连接来自 Settings().test_database_url，在连接前调用 validate_test_target，并查询 current_database() 断言为 agent_demo_test。探针创建 Settings(database_url=base.test_database_url, app_env="test")，使用实际 create_app、真实连接池、仓储及模型客户端初始化。

HTTP 使用 TestClient 与真实应用 lifespan，设置 `backend_options={"loop_factory": asyncio.SelectorEventLoop}`。进入后先断言 health 的 database_status 为 ready、model_status 为 initialized、agent_ready 为 true，同时服务启动日志显示 preparation_ready=True。使用 `patch.object(service, "prepare_chat", wraps=service.prepare_chat)` 观察调用，正常请求执行原方法。

| 探针步骤 | 真实观察与断言 |
| --- | --- |
| 原始请求，user_id=dev-user、conversation_id 为 qa 后接 NUL 再接 probe、message=hello | HTTP 422，application/json，prepare_chat 未调用，Session 总行数增量为 0 |
| user_id 含 NUL，conversation_id 使用本轮随机名称 | HTTP 422，prepare_chat 仍未调用 |
| 正常请求，conversation_id 为首尾带空格的 p2-01-fix- 加随机 UUID | HTTP 503，application/json，error.code=agent_not_ready，prepare_chat 累计调用 1 次 |
| 正常请求的持久数据 | 测试库实际存在 dev-user 与去除首尾空格后 conversation_id 的 Session 绑定 |
| 清理 | finally 中仅按本轮 user_id/conversation_id 精确删除自身 Session；自身剩余 0 行，总 Session 行数由 0 恢复到 0 |
| 资源退出 | 实际 pool.closed 为 true |

以上 HTTP 探针使用进程内 ASGI 传输。真实 PG 与应用生命周期已验证，独立 Uvicorn socket 未在本轮重验。临时探针随命令执行，核心校验与 Unicode/配置回归已落入测试文件。完整真实库 pytest 同时覆盖原迁移与 Session 用例，其清理逻辑沿用现有测试。连接 URL、密码及模型密钥均未输出。

## 设计偏差、验证边界与交接

本轮采用共用 Identifier 的声明式正则和既有配置验证器，修复范围符合提示词授权，无新增设计偏差。校验仅增加 NUL 存储限制。业务代码改动集中于两个外部边界。

本轮验证覆盖原始错误路径、准备层零调用、正常准备的持久事实、配置输入隐藏及完整现有回归。依赖清单沿用原版本，模型客户端仅初始化，付费模型调用、环境重建、容器重启与 Graph 持久恢复属于本轮验证范围之外。

开发自测支持 P2-01 进入主 Agent 复核与独立 QA 回归。02 可复用修复后的请求和配置边界，正式 Task/Graph/SSE 接线仍按 D02 授权推进。P3-01 的既有检查遗留继续按主 Agent 决定追踪。本报告提交后，独立回归和正式阶段验收仍待安排。
