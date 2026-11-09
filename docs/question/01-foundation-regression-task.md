# 01 P2-01 独立 QA 回归任务提示词

你是 Agent Engine Demo 的独立测试 Agent。本轮对 P2-01 修复进行独立回归，输出是否可关闭原问题及阶段验证结论。仅执行审查及必要验证，保持被测业务代码、配置、依赖和正式迁移文件的独立性。新增或更新 QA 报告即可。

## 项目与依据

工作区为 `D:\py\agent-project\agent`。先检查 Git 现状及 AGENTS.md，阅读 README、有效定位/路线图、D01 第 8 节与开发交付报告，以及以下文件。

- `docs/question/01-foundation-acceptance.md`，原始 QA 问题和验收矩阵。
- `docs/question/01-foundation-main-review.md`，首次裁决及第 6 节修复复核。
- `docs/resume/01-foundation-fix-task.md`，修复授权范围。
- `docs/resume/record/01-foundation-fix-report.md`，开发自测证据。

六个 Task 和 P2 修复已交付，阶段当前为 IMPLEMENTED、独立回归待启动，02 未开始。主 Agent 已复核代码并复跑受影响测试 22 passed、四文件 Ruff 通过。修复会话报告完整真实库回归 82 passed。以上属于已有证据，本轮请独立核验。

## 核心审查与复现

1. 核对实际改动。请求 Identifier 增加排除 NUL 的 pattern，Settings 名单验证新增 NUL 拒绝。确认原有长度、Unicode、首尾空白规范化、去重及权限边界继续成立，校验集中在外部边界，无宽泛数据库异常吞掉问题。
2. 原始请求为 user_id=dev-user、conversation_id="qa\u0000probe"、message=hello，其中 JSON 转义表示实际 NUL。独立检查 user_id/conversation_id 含 NUL 时均为 JSON 422，错误定位正确，prepare_chat 未调用，Session 无新增。
3. 使用真实测试库及实际 lifespan 验证，先确认 database_status=ready、agent_ready=true。正常请求执行真实 Service/SessionRepository，仍返回 JSON 503 agent_not_ready，确认实际持久绑定及规范化。两种输入的边界证据分别记录。
4. 验证含 NUL 的演示用户名单配置失败，错误字符串隐藏探针输入，合法 Unicode 名单及去重正常。
5. 复核修复没有扩大到业务执行或更改 Session/迁移/Task 契约。原工具、审批、持久 Checkpoint、RAG 和 Store 的阶段边界继续按 D01 判断。

## 验证方式

使用 `.\.venv\Scripts\python.exe`。先审查现有新增回归，再运行受影响测试及一次完整现有测试，显式启用 agent_demo_test。连接前使用现有 validate_test_target，核验 current_database()。沿用 README 的安全配置方式，凭据不写入报告。

Windows psycopg 使用 Selector loop，TestClient 可用 `backend_options={"loop_factory": asyncio.SelectorEventLoop}`。可用 wraps 观察真实 prepare_chat 调用，以明确异常输入零调用和正常请求实际走仓储。只清理本轮随机标识的数据，使用 finally 精确清理，记录前后状态及资源关闭。ASGI 验证和独立 Uvicorn socket 验证分别标明，按需要选择，若复现失败先区分资源未就绪和修复行为。

检查四个修复文件的 Ruff lint/format，并核对全仓 Ruff 遗留仍为原 P3-01。无付费模型重跑或重建现有容器的必要。真实模型及 bootstrap/Volume 既有证据的接受范围见主 Agent 记录。本轮缺资源或有验证失败时明确列出边界，避免将 skip 算作真实库验证通过。

## 报告要求

保存到 `docs/question/01-foundation-regression-report.md`。关联阶段 01、Task 1.1.2/1.3.2、P2-01、修复提示词及修复报告。包含实际审查文件、命令及结果、真实 HTTP/数据库证据和清理、原问题关闭建议、回归问题、D01 第 8 节矩阵更新建议、P3 遗留及未验证项。

新问题使用独立编号，按原 QA 规范写严重度、设计要求、位置、复现、预期/实际、影响及证据，保持原 P2-01 编号。测试结论与正式验收决定分别记录，主 Agent 后续复核，用户批准后执行阶段切换及 Git 归档。完成后回复报告路径，由用户人工带回。
