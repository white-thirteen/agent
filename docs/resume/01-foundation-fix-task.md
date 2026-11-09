# 01 修复会话任务提示词

以下内容供用户人工复制到独立修复会话。当前仅完成任务编制，修复会话尚未启动。

---

你是 Agent Engine Demo 的修复 Agent。本轮仅处理主 Agent 确认的 **P2-01**，完成必要编码及开发自测，交付后由独立测试会话回归。

## 当前状态与必读依据

工作区为 `D:\py\agent-project\agent`。01 的六个 Task 已实现，独立 QA 已结束，主 Agent 判定 NEEDS_FIX。02 尚未开始。先读 AGENTS.md、README、项目定位、development-roadmap.md、D01 第 8 节及末尾正式开发报告，再读以下文件。

- `docs/question/01-foundation-acceptance.md`，原始 QA 报告。
- `docs/question/01-foundation-main-review.md`，主 Agent 裁决及证据边界。
- `app/api/schemas/chat.py`、`app/core/config.py`、`app/api/dependencies.py`。
- `app/api/routes/agent.py`、`app/services/agent_service.py`、`app/infrastructure/sessions.py`。
- `tests/test_demo_identity.py`、`tests/test_config.py`、`tests/test_application.py`。

先检查 Git 工作区及子目录 AGENTS.md。现有未提交改动包含先前用户成果，不得覆盖。

## 已确认的问题

请求体如下，JSON 中的转义表示一个实际 NUL 字符。

```json
{"user_id":"dev-user","conversation_id":"qa\u0000probe","message":"hello"}
```

当前 ChatRequest 校验通过。真实资源就绪时 SessionRepository 将参数提交 PostgreSQL，psycopg 抛 DataError，HTTP 为 500、text/plain。主 Agent 已在测试库和真实 lifespan 下再次复现，现有完整 78 项测试通过但未覆盖该边界。Settings.demo_user_ids 同样允许 NUL。

## 授权修复范围与约束

1. 在外部 user_id/conversation_id 标识边界拒绝 NUL，HTTP 返回 422，且请求未进入 prepare_chat/仓储。同步拒绝演示用户名单中包含 NUL 的配置项，保留秘密输入隐藏行为。
2. 保持现有长度、空白规范化、正常 Unicode 标识、名单去重和请求字段契约。新增规则只解决已确认的存储字符问题，不擅自扩展成 ASCII 白名单或全面禁止控制字符。
3. 使用最小清晰实现，适当复用现有验证逻辑，避免新基础设施、重复逐层校验或宽泛捕获 DataError。无需改迁移、Session 算法或冻结架构。
4. 增加少量有意义的 HTTP/配置回归。验证非法标识返回 422 且未进入准备层，合法请求仍按 01 边界返回 JSON 503 agent_not_ready。保留普通 Unicode/空白规范化行为的验证。
5. 仅处理 P2-01。P3-02 已由主 Agent 修正文档，P3-01 已登记为非阻塞遗留。

## 验证要求

使用 `.\.venv\Scripts\python.exe`。先运行受影响的配置、身份、HTTP 测试，再运行一次完整 pytest。显式使用 agent_demo_test 验证原复现请求得到 422、正常准备请求仍为 JSON 503，并核对自身测试数据清理。真实 PG 测试入口和安全配置方式见 README，不输出 URL/密码。

Windows psycopg 必须使用 Selector loop。TestClient 的真实库探针可用 `backend_options={"loop_factory": asyncio.SelectorEventLoop}`，并先断言 preparation_ready=True，避免资源未就绪的 503 掩盖校验问题。模型客户端可初始化，验证不需要调用付费模型。

检查修改文件的 Ruff lint/format，报告全仓既有遗留。依赖无需变更，不执行 Git Commit/Push。未具备真实测试资源时明确标记未验证，不能用替身通过代替真实回归结果。

## 交付要求

提交 P2-01 修复报告，包含根因、改动文件与职责、行为变化、命令和结果、真实 HTTP 状态及数据核对、设计偏差、未验证事项及对 02 的影响。必须将修复记录整理到 `docs/resume/record/01-foundation-fix-report.md`，关联本提示词、阶段 01 和问题 P2-01，并在回复提供路径。后续修复轮次使用独立文件保留历史记录。由主 Agent 后续复核和更新阶段状态，修复报告不宣称独立 QA 或正式阶段验收通过。

保持本轮业务代码修改集中于标识/配置边界及必要测试，不提前开发 02、订单取消、工具、审批、Checkpoint、RAG 或 Store。
