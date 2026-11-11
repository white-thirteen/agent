# 02 AgentRuntime 与 Supervisor 执行会话交付报告

日期为 2026-11-10。状态为六个 Task 已完成代码实施和开发自测，待主 Agent 审核与独立 QA。执行依据为 [整阶段执行任务](02-agent-runtime-execution-task.md)、[D02 完整设计及 11.2 矩阵](02-agent-runtime-detailed-design.md#112-验收矩阵) 和 [实施计划](02-agent-runtime-implementation-plan.md)。本报告属于执行会话，阶段验收状态由主会话及用户决定。

## 1. 基线、工作区归属和授权边界

实施起点为 real-model-chat 的 01 Delivery `cf3e763e96f290dad4bb011e778bbcdf7c6c81d6`，前序 Baseline 为 `f89db15efc9b38e88bfed6a725abde76575c6bae`。开始时默认回归为 80 passed、2 skipped，专用 PG 未经默认测试隐式启用。01 已验收的含真实测试库基线为 82 passed。

开始时已有 AGENTS、README、D01、项目定位、路线图及 01 主复核文档等差异，三个旧文档工作区删除、general.py 未跟踪，02 执行任务/实施计划、Bridge 设计和主协调记录等未跟踪文件均保留。实施期间主会话新增了 02 QA 任务，属于其协调产出。没有处理这些暂缓文件，也没有改动 Bridge 工程或派发其他会话。主协调文档 `docs/question/02-agent-runtime-main-review.md` 继续由主 Agent 维护。

本轮只实现 02。默认使用受控模型，真实数据库访问限 agent_demo_test。未调用额外付费模型、写入应用库、重建容器/数据库、增加业务表或升级 schema。现有 PG 测试在版本/checksum 预检之后运行，只重读已应用版本及验证临时失败事务回滚。依赖清单、正式 SQL 迁移、真实 .env 保持本轮起点内容。没有 Commit/Push。

## 2. 六个 Task 完成情况

| Task | 核心实现 | 主要验证 |
| --- | --- | --- |
| 2.1.1 类型/State 适配 Demo | REFUND/REFUND_APPLY、MEMORY_MANAGE 迁移，ExecutionContext 加 task_id 并校验 workflow 同值，create_turn_state 显式 new/continue，任务消息 ID 与预算覆盖快照 | 枚举拒绝旧执行值，消息 Reducer、跨用户图状态、显式续接、任务字段/预算不由工厂生成或归零 |
| 2.1.2 Supervisor 与澄清 | ModelGateway.invoke_structured + SupervisorOutput，两类澄清、具体目标补参、unsupported 边界、一次结构纠正、当前任务最多 12 条公开文本 | 通用→具体保持 Task，具体补参保目标/过滤身份候选，隐式换目标不结束原任务，new_task 新预算，非法结构两次失败后收敛 |
| 2.2.1 主图与专业接入 | 显式注入 Gateway、三专业编译骨架、InMemorySaver、RunExecutionContext；wrapper 白名单及当前关联检查 | 四种专业 Task 进入实际三节点骨架，统一 capability_unavailable，父子 context 传递与 foreign request 拒绝 |
| 2.2.2 公共结果与骨架验证 | 唯一 Response、approved_answer/来源约束、普通 run_finish 返回完整结算更新、sync durability 后才发布最终事件 | 私有工具消息隔离、较小子图计数不覆盖 scope、普通 END 后零 aupdate_state、慢 Saver 排除于主动期限、结算/提交失败无最终 token |
| 2.3.1 独立执行与互斥 | Runtime.submit 创建强引用执行任务，thread 同步门禁/容量占位、request_id 去重、RunScope、结果 TTL/数量限制、uncertain、shutdown | 同 thread 409、8 个并发/第 9 个拒绝、预受理取消释放、已受理独立执行、预算继承、缓存/故障/关闭顺序 |
| 2.3.2 SSE 和状态语义 | chat/status/events 三 POST、SubscriptionOwner/ASGI guard、64 帧单订阅、白名单事件、快照附流及无重放 | 首次迭代前/构造/响应头失败清理、实际 TCP 中途断开、慢队列、旧 owner 晚清理、查询隔离、终态快照+done |

六个 Task 内部按既定顺序实施，引用后继契约的纯结构先定义，实际 Runtime/HTTP 在 2.3 接通。本轮不替代独立 QA。

## 3. 实际文件变更及接口

新增实现文件如下。

- `app/runtime/models.py`，RunLimits/RunUsage、TaskStatus/RunStatus、RunHandle/RunRecord/RunView/TaskView。
- `app/runtime/run_scope.py`，本 Run 的可信累计快照、主动计时、普通冻结与失败现场停止。
- `app/graph/nodes/run_finish.py`，普通图内最终 Task/预算更新。
- `app/graph/specialists/__init__.py` 及 order/refund/knowledge 各目录的 `__init__.py`、`builder.py`，分别实际编译三节点专业骨架。
- `app/streaming/subscription.py`，EventSubscription/SubscriptionOwner。
- `app/streaming/response.py`，仅 SSE 路由的 SubscriptionRoute 请求级 guard。
- `tests/runtime_support.py`、`tests/test_runtime.py`、`tests/test_runtime_http.py`，共享受控模型及针对 Runtime/HTTP 风险的自测。
- 本交付报告。

修改实现文件如下。

- `app/agents/types.py`、`app/agents/prompts/supervisor.py`。
- `app/graph/contracts.py`、`state.py`、`transfers.py`、`router.py`、`builder.py`。
- `app/graph/nodes/supervisor.py`、`specialist.py`、`result_aggregator.py`、`response.py`。
- `app/runtime/context.py`、`agent_runtime.py`。01 RunLimits/RunUsage 的唯一定义按依赖迁入 models，旧 Runtime 模块继续导入并提供原入口。
- `app/services/agent_service.py`、`app/api/schemas/chat.py`、`app/api/routes/agent.py`。
- `app/streaming/events.py`、`formatter.py`、`app/core/errors.py`、`config.py`、`app/main.py`、`.env.example`。
- `tests/test_agent_types.py`、`test_graph_state.py`、`test_graph_protocol.py`、`test_application.py`、`test_demo_identity.py`、`test_resources.py`。
- README、Graph 协议及 D02 追加实施记录。既定设计需求正文保留。

公开接口如下。

| 接口 | JSON body | 当前结果 |
| --- | --- | --- |
| POST /agent/chat | user_id/conversation_id/message，input_mode/request_id 可选 | 受理后 SSE；配置/身份/状态冲突在开流前 JSON 错误 |
| POST /agent/runs/{run_id}/status | user_id/conversation_id | 安全 RunView，不创建 Task/Run/Session |
| POST /agent/runs/{run_id}/events | user_id/conversation_id | 当前安全快照与未来事件；终态只快照和该订阅 done |

01 的 DemoIdentity、DemoContext、SubmitOptions、prepare_chat 二元组、稳定 SessionRepository 绑定与 ModelGateway 全部复用。Service 只准备候选 run_id 并显式转交 context/options/owner。正式 task_id 仅由 Runtime 受理门禁内生成，workflow_id 同值。旧 AgentContext、生成器拥有 Graph 执行和 Runtime 自行算 thread 的正式路径已移除。

RunView 只包含 run/task/workflow、状态、最终文本/来源、安全错误、两组累计用量、usage_complete 和起止时间。来源 URI 限制为无凭据的 HTTP(S)，阻止本机路径公开。sources/私有 State 的投影由契约和 Runtime 边界控制。旧 RunView 保留结束时快照，不被后续新任务改写。

## 4. 主图、预算与资源生命周期

应用 lifespan 复用 01 池和自有 HTTP 模型资源，显式编译三个骨架及主图一次，再创建 Runtime/Service。health 保留原字段并增加 checkpoint_backend=memory。缺资源 HTTP 可存活，production 演示身份禁用。

普通路径为 Supervisor → 澄清/专业骨架/拒绝或受控错误 → 唯一 Response 或错误出口 → run_finish → END。Response 只追加批准文本，稳定消息 ID 为 assistant:{run_id}。run_finish 校验可信关联、Task 状态及错误关系，冻结主动时钟，返回 model_call_usage/run_usage 覆盖快照。Runtime 等 Graph 的 sync durability 返回后才 finalize 和发布最终事件，不执行 END 后第二次普通写回。

RunScope 在实际独立执行开始时计时，受理等待和两个 Run 之间的用户等待排除。模型重试与结构纠正期间计时并累计原 Task 尝试。finish 冻结后解除外层主动期限，Saver 最终提交和流/资源收尾不追加主动时间。失败取消采用 abort_active_period 保存本地可确认用量，usage_complete=false；异常路径不重试普通图结算。

Runtime 先同步 claim thread/容量，再 await 快照读取。快照缺失与读取失败区分，未完成 next/不可信现场拒绝普通输入。登记 Run、索引、初始订阅、owner.adopt、create_task 和返回之间无 await。受理前错误回滚自身占位，受理后由执行任务 finally 释放门禁。独立任务取消于首次执行前的情况由 done callback 收敛。

shutdown 先停止受理，默认等现有任务最多 5 秒，随后取消并 await 收敛，再关闭订阅、自有模型客户端和 PG 池。测试使用较短 grace 验证该顺序。生产依赖对象与 scope/queue/task 均不写入 Checkpoint。

## 5. D02 第 11.2 节逐项证据

| D02 场景 | 观察结果 | 自测证据 |
| --- | --- | --- |
| 通用澄清→具体业务 | 两次 submit 同 task/workflow、新 run，model_attempts 1→2，进入 Order 骨架返回 unavailable | test_runtime.py 的 generic_clarification_continues_task_budget_and_new_task_resets_scope |
| 具体缺参/显式换目标 | 具体补参保原 task_goal、合并白名单 order_id；unsupported/隐式换目标保 needs_input；new_task 建新目标并初始化预算 | test_runtime.py 的 specific_clarification_fills_entities、specific_pending_preserved |
| 不支持取消/非法模型输出 | unsupported 不进入专业且安全 rejected；非法结构最多纠正一次，两次尝试记入快照；预算不足不再启动模型 | test_runtime.py 的 unsupported_and_structure_correction、continued_model_budget_exhaustion；test_agent_types.py 拒绝旧取消/旧售后枚举 |
| 目标图与三专业骨架 | D02 4.6–4.8 目标图保留；实际四种专业任务分别通过真实编译骨架失败，无订单/退款/知识伪事实 | test_graph_protocol.py 的 actual_compiled_skeletons 参数场景，生产 main 显式装配三个 builder |
| 父子图隔离 | user/session/task/run/目标检查；foreign request 拒绝；私有 ToolMessage 不进入父历史；子图零计数不覆盖已确认模型次数；QA/Memory 结果约束 | test_graph_protocol.py 的 nested_success、child_input_filters、foreign_result、completed_qa；task_message_window |
| 预算 | 相同 Task 的模型次数与工具种子继承，达到 max_attempts 或工具限额后零新模型尝试；主动超时标 incomplete/uncertain | test_runtime.py 的 continued_model_budget_exhaustion、seeded_tool_budget、timeout_uncertain；test_model_gateway.py 的重试/超时/unknown 既有验证 |
| 普通结算与中断边界 | Saver 最终快照等于冻结 scope；普通路径不调用 aupdate_state；最终 Saver 额外延迟 0.3 秒超过 0.2 秒主动限额仍成功；故障不发最终 token | test_graph_protocol.py 的 real_topology_scope_settlement；test_runtime.py 的 frozen_clock、run_finish_failure、commit_failure |
| 同 thread/不同会话 | 第二执行立即 thread_busy；8 个不同 thread 占位并执行，第 9 个 runtime_busy；预受理取消/停止时释放占位 | test_runtime.py 的 gate_capacity_dedup、pre_admission_cancel |
| 重复请求 | 同 request_id/指纹复用原 Run，单订阅冲突，换内容拒绝；保留条数/TTL 清索引后新提交不宣称持久幂等 | test_runtime.py 的 gate_capacity_dedup、state_read_failures_unfinished_snapshot_and_retention；HTTP status/events 不重执 |
| 断开/慢队列 | 构造/首次迭代前退出/响应头发送失败清 owner，原任务继续并可立即附流；小队列溢出唤醒并解绑；旧 owner 不关闭新流 | test_runtime_http.py 的 request_guard_cleans_before_first_iteration 三场景；test_runtime.py 的 slow_subscription、gate_capacity_dedup |
| 重订阅/结束 | 首帧快照、只未来事件；终态只有 status+done，没有旧 token；正常流 done 一次；Last-Event-ID 开流前 409 | test_runtime_http.py 的 three_http_interfaces、real_tcp_disconnect；test_runtime.py 的 slow_subscription |
| 异常/预算结算失败 | state 读取失败为 state_unavailable，未完成 next 为 execution_uncertain；模型结构失败可普通结算，意外/timeout/finish/commit 故障保 incomplete；Run 过期不清 uncertain | test_runtime.py 的 state_read_failures、timeout_uncertain、run_finish_failure、commit_failure |
| 关闭/隔离 | 主动 shutdown 后拒绝新受理；挂起执行取消并 await；门禁/订阅收敛先于 HTTP 模型/池关闭；跨用户/会话统一 404；production/NUL 保留 | test_resources.py 的 shutdown_settles_execution_before_model_and_pool_close；test_runtime_http.py；test_demo_identity.py 原有 P2-01 回归 |

具体成功子图只用于协议验证，应用装配始终是 capability_unavailable 骨架。02 的工具次数验证采用可信测试快照，不声称已有 ToolExecutor。真实 interrupt/namespace/审批/副作用恢复的实测留 04，本轮没有将这些控制流伪装为普通 needs_input 或 failed 业务结果。

## 6. 实际 HTTP 断开和请求级清理

`test_real_tcp_disconnect_releases_subscription_and_run_finishes` 使用真实 Uvicorn、127.0.0.1 临时监听 socket、httpx.AsyncClient 和正式三个 Route。HTTP session 仓储为测试内 MemorySessions，执行是实际编译主/子图、ModelGateway 和 AgentRuntime。该测试与 PG 测试分别验证，未对应用库发请求。

客户端 POST /agent/chat，收到首个 status/run_id 后关闭实际 TCP 响应。受控模型仍处于阻塞点。断开后观察 RunRecord.subscription=None 且执行 task 尚未完成，status 接口仍返回 running。释放模型后查询得到 needs_input，events 返回终态快照+done，无旧 token，模型总调用仍为 1。测试最后停止 Uvicorn、关闭监听 socket 并 shutdown Runtime。

另有三个独立 ASGI 场景。响应构造抛错、返回的响应在首次迭代前取消，以及发送 response.start 抛错，都由请求最外层 guard finally 清理 owner。前两项显式断言 SSE 迭代器未进入。随后立即重新订阅原 Run，任务继续并正常结束。未用 generator.close 代替实际连接验证，也未增加竞争读取 receive 的监听器。

## 7. 实际测试命令和结果

全部命令使用项目 `.venv` 的 Python 3.13.7。主要开发自测如下。

| 检查 | 结果 |
| --- | --- |
| 开始时默认基线 pytest -q | 80 passed、2 skipped；与 01 的 82 项含库基线对应 |
| 类型/State/协议首批受影响验证 | 49 passed |
| Runtime/HTTP/身份/资源受影响验证 | 26 passed，发现的局部适配问题修复后通过 |
| 实际 HTTP/ASGI guard 场景 | 5 passed |
| 最终完整回归，显式启用专用测试库 | **109 passed in 14.29s，0 failed，0 skipped** |
| Ruff lint 全仓 | All checks passed |
| Ruff format app/tests/scripts | 88 files already formatted |
| git diff --check | 通过，Git 仅提示已有 autocrlf 换行转换 |
| 全仓 Ruff format | 6 个既有 Markdown 代码示例文件未通过；执行 Python 文件全部通过 |

可复现的常规入口如下。

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_types.py tests/test_graph_state.py tests/test_graph_protocol.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_runtime.py tests/test_runtime_http.py tests/test_resources.py
.\.venv\Scripts\python.exe -c "import os, pytest; from app.core.config import Settings; os.environ['AGENT_TEST_DATABASE_URL'] = Settings().test_database_url.get_secret_value(); raise SystemExit(pytest.main(['-q']))"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check app tests scripts
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

真实库完整回归的实际执行 harness 在 pytest 前用只读事务确认 current_database=agent_demo_test、current_user=agent_test、schema_migrations 的版本/checksum 完全等于仓库 001/002，并确认 Session 为 0 行。只向本次 Python 进程环境传递测试 URL，未打印 URL 或密码。既有 PG 回滚/并发测试清理随机生成的精确 user/conversation 数据。

结束后只读复核仍为 0 行，Session 摘要为 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`，版本/checksum 不变，public 表仍仅 schema_migrations 和 sessions。未运行迁移升级或基础设施命令，测试的临时失败 DDL 已回滚。

基线变化来自既定 02 协议迁移及风险覆盖。旧 order_cancel/refund_request/AfterSales 可执行枚举改为拒绝测试，补充 MEMORY_MANAGE；State 工厂测试改为显式 Task/new/continue；旧生成器 Runtime/SSE 测试改为 RuntimeEvent 和正式独立执行；01 prepare 固定 503 的观察替身改为断言显式 submit 转交。NUL/Unicode/身份/配置/模型/资源和 PG 核心断言保留。增加的 Runtime、订阅和实际 socket 用例覆盖 D02 新行为，没有以保持测试数量替代验收。

P3-01 中本轮实际修改的 Supervisor Prompt E501、Response 和旧 Runtime 格式已收敛。全仓 format 剩余文件为 D01、D02、D03、D04、D05 和 docs/history/04-1-order-service-design.md 的既有设计示例。本轮保留冻结文本和历史证据，未做全仓格式化。无依赖变化，未重复安装或升级依赖。

## 8. 实施适配、开发中修复与遗留

未发现需要重开冻结设计的实质冲突，未增加业务范围或改变三 POST/Task/预算接口。以下局部实现适配和开发中发现均已验证关闭。

- 已安装 FastAPI 的 included-router effective context 会绕过单独替换 APIRoute.app 的包装。请求 guard 放到 SubscriptionRoute.handle，覆盖完整响应生命周期，实际 ASGI 和 TCP 测试通过。
- shutdown 取消后的异常收敛不能再次 reschedule 已退出的 asyncio.Timeout。普通冻结仅在 run_finish 活动期解除期限，异常通过 abort_active_period 冻结可确认本地用量，避免重试图内结算。
- 普通图响应采用 sync durability；最终 Saver 提交延迟与故障分别验证。任何结算/提交不确定都只收敛内存记录并阻止盲重放。
- RunLimits/RunUsage 移至 runtime/models 唯一定义并保留旧导入入口，这是依赖组织调整，字段与语义延续 01。

遗留为上述 6 份设计示例 format 检查及后继阶段能力。当前没有未关闭的本轮自测失败。额外真实模型请求未授权且未执行，02 provider/SupervisorOutput 的真实网络联调未作为本轮证据；已有 01 模型基础连通证据保留归属。

## 9. 后继交接和停止点

主 Agent 可据本报告复核六 Task 和矩阵后安排独立 QA。当前开发自测完成，阶段 ACCEPTED 仍需其既定流程与用户批准。代码未 Commit/Push，主协调文档、Bridge 文件及他人工作区差异保持原归属。

03 接 Registry/Policy/Executor 与模拟订单事实及真实工具预算递增；04 接 PG Saver、本地可信 Actor、interrupt/resume/原调用幂等及等待主动时间暂停，替换内存不确定判断为持久事实核对；05 接真实知识证据、approved_answer 和 Memory 管理结果。RunExecutionContext、RunScope 和显式父子映射保留扩展边界。

本阶段已接通 Runtime/HTTP，但三专业仍返回 capability_unavailable；内存 Saver、Run 缓存/TTL、request_id 索引和 uncertain 标记不提供跨进程恢复或持久幂等。未知现场没有普通 HTTP 解除入口。正式专业业务、审批、RAG/Store、跨重启恢复依后续授权实施。
