# 02 AgentRuntime 与 Supervisor 独立 QA 报告

审查日期为 2026-11-10。测试对象为当前共享工作区，01 Delivery 基线为 cf3e763e96f290dad4bb011e778bbcdf7c6c81d6。

**独立 QA 总体结论为 PASS。完整现有回归为 109 passed、0 failed、0 skipped，补充独立用例最终为 3 passed。未发现新增的已确认产品缺陷，P3-01 的六份设计示例格式遗留继续保留。正式阶段验收由主 Agent 复核后处理。**

## 1. 依据、范围和测试独立性

依据为适用 AGENTS.md、[本轮 QA 任务](02-agent-runtime-qa-task.md)、[D02 完整设计及第 11.2 节](../02-agent-runtime-detailed-design.md)、[02 整阶段执行任务](../02-agent-runtime-execution-task.md)、[当前 README](../../README.md) 和 [Graph 协议](../graph-protocol.md)。已读取 [开发交付报告](../02-agent-runtime-delivery-report.md) 和 [主 Agent 协调记录](02-agent-runtime-main-review.md)，将其中结论作为待核验信息。

本轮检查六个 Task 的实际实现、正常入口和测试覆盖，独立执行一次完整现有回归，并在临时目录增加三项验证。测试使用项目 .venv、受控模型和已核实的 agent_demo_test。只向本轮测试进程传入测试连接配置。

本轮新增项目文件仅为本报告。临时复现文件位于 C:/Users/15294/AppData/Local/Temp/agent-phase02-qa-7bda02066de345b6b1414d1352322536/test_phase02_independent.py。业务代码、仓库测试、配置、依赖、正式 SQL 和冻结设计保持本轮起点内容。主协调文档由主 Agent 维护。

开始时工作区存在 02 实现、已有文档增量、三个旧文档删除及未跟踪文件。Git 差异包含此前成果，未将全部差异归为 02。本轮未调用其他会话、操作基础设施、连接应用库、执行迁移升级、付费模型请求或 Git Commit/Push。

## 2. 六个 Task 审查结果

| Task | 实际实现与职责符合性 | 独立判断 |
| --- | --- | --- |
| 2.1.1 类型/State 适配 Demo | agents/types、graph/contracts/state/transfers/router 迁移 REFUND/REFUND_APPLY、MEMORY_MANAGE；Runtime 提供正式 Task，workflow 同值；轮次输入显式 new/continue，预算覆盖快照 | 通过。旧取消/售后执行值拒绝，关联、Reducer、续接继承和临时结果清理有断言 |
| 2.1.2 Supervisor 与澄清 | supervisor 节点调用唯一 Gateway，最多一次结构纠正；通用目标可细化，具体 PendingTask 保目标；本任务最近 12 条公开消息 | 通过。澄清、隐式换目标、unsupported、实体过滤、限额和新任务隔离均验证 |
| 2.2.1 主图与专业接入 | builder 显式注入 Gateway、三个真实编译骨架、Saver；wrapper 经当前 context 调用专业图并核验 request/result | 通过。四种专业 Task 实际进入三骨架，统一 failed/capability_unavailable，父子关联错误被拒绝 |
| 2.2.2 公共结果与骨架验证 | 唯一 Response，主 run_finish 图内冻结和结算，Runtime 等 sync durability 返回后发布最终事件 | 通过。普通 END 后额外 aupdate_state 被禁止，快照和已冻结用量一致；实际最终 Saver 故障补测通过 |
| 2.3.1 独立执行与互斥 | Runtime 管 thread/容量 claim、request_id、独立 task 强引用、RunScope、TTL、uncertain 和 shutdown | 通过。并发、去重、预算、故障及清理得到验证 |
| 2.3.2 SSE 和状态语义 | 三 POST 正式 Route、请求级 owner/guard、单订阅队列、白名单 DTO、安全查询与无重放附流 | 通过。ASGI 失败注入及真实 TCP 断开均验证，补测使用真实 PG 和正式 lifespan |

主要审查文件包括 app/runtime/agent_runtime.py、models.py、run_scope.py、context.py、model_gateway.py，app/graph 的 contracts/state/transfers/router/builder、supervisor/specialist/response/result_aggregator/run_finish 节点及三个专业 builder，以及 app/streaming 的 events/formatter/subscription/response、API Route/Schema、Service、main/config/errors 和对应测试。

## 3. 实际命令与结果

### 3.1 完整现有回归及真实库保护

实际通过 PowerShell here-string 管道到项目解释器执行测试 harness。连接前调用 validate_test_target(test_url, development_url)，在只读事务中核对实际目标，并核对已应用版本/checksum 完全等于仓库 001/002。只有预检成功才执行 pytest。

```powershell
@'
import hashlib,json,os,sys,pytest,psycopg
from pathlib import Path
from app.core.config import Settings
from app.infrastructure.postgres import validate_test_target,connection_kwargs
from scripts import run_async
s=Settings();validate_test_target(s.test_database_url,s.database_url)
async def snapshot():
 async with await psycopg.AsyncConnection.connect(**connection_kwargs(s.test_database_url)) as c:
  await c.execute('SET TRANSACTION READ ONLY')
  cur=await c.execute('SELECT current_database(),current_user');ident=await cur.fetchone();assert ident==('agent_demo_test','agent_test')
  cur=await c.execute('SELECT version,checksum FROM schema_migrations ORDER BY version');versions=await cur.fetchall()
  expected=[(int(p.name.split('_')[0]),hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(Path('migrations').glob('*.sql'))];assert versions==expected
  cur=await c.execute('SELECT user_id,conversation_id,thread_id::text,created_at::text FROM sessions ORDER BY user_id,conversation_id');rows=await cur.fetchall()
  return {'identity':ident,'versions':versions,'sessions':rows}
before=run_async(snapshot());print('BEFORE',json.dumps(before));os.environ['AGENT_TEST_DATABASE_URL']=s.test_database_url.get_secret_value()
result=pytest.main(['-q']);after=run_async(snapshot());print('AFTER_IDENTICAL',before==after,'SESSION_COUNT',len(after['sessions']));assert before==after
raise SystemExit(result)
'@ | .\.venv\Scripts\python.exe -
```

实际结果为 **109 passed in 14.70s，退出 0**。测试前后快照完全一致，Session 均为 0 行，版本和 checksum 保持一致。开发报告中的 109 项结论已独立复现。

### 3.2 补充独立用例

```powershell
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q -s --tb=short C:/Users/15294/AppData/Local/Temp/agent-phase02-qa-7bda02066de345b6b1414d1352322536/test_phase02_independent.py
```

最终结果为 **3 passed、3 warnings in 15.15s，退出 0**。三项分别验证真实 PG 加正式 lifespan/TCP、实际最终 Checkpoint 提交失败、普通结算和用户等待排除。warning 来自临时 QA 文件用于选择 Windows Selector 的 event_loop_policy fixture 弃用提示，仓库测试未作此改动。

首轮运行该临时文件时，真实 PG 用例在连接前因 QA 未指定 Selector loop 而抛 InterfaceError，另两项通过，结果为 1 failed、2 passed。修正临时 QA fixture 后运行全部三项，得到上述最终结果。初次失败归为 QA 执行配置偏差，详见第 8 节。

### 3.3 检查命令

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check app tests scripts
.\.venv\Scripts\python.exe -m ruff format --check . --output-format concise
git diff --check
git diff cf3e763 -- tests/test_postgres.py tests/test_config.py tests/test_model_gateway.py
git diff --numstat cf3e763 -- tests
```

| 检查 | 独立结果 |
| --- | --- |
| 全仓 lint | All checks passed，退出 0 |
| app/tests/scripts format | 88 files already formatted，退出 0 |
| 全仓 format | 6 files would be reformatted、123 files already formatted，退出 1 |
| git diff --check | 退出 0，仅 autocrlf 换行转换提示 |
| PG、配置、Gateway 测试与 01 Delivery 对比 | 三个测试文件无差异 |

完整现有回归与三项补测分别记数。补测使用临时目录，未纳入仓库默认测试数量。

## 4. 正常入口、真实连接和数据保护证据

### 4.1 真实 PG 加正式 lifespan/TCP

临时独立用例只替换模型资源出口的 Gateway，使其使用受控模型。原 model_resources 仍实际创建及关闭自有 HTTP 客户端。create_app、lifespan、PG 池、SessionRepository、Service、三个正式 Route、主图及专业 builder、ModelGateway 和 AgentRuntime 均执行实际实现。未使用 MemorySessions，也未替换应用 lifespan。

测试库预检确认 current_database=agent_demo_test、current_user=agent_test。启动真实 Uvicorn，监听 127.0.0.1 的操作系统分配端口。health 实际为 agent_ready=true、database_status=ready、checkpoint_backend=memory。

| 顺序 | 输入/可控点 | 实际观察 |
| --- | --- | --- |
| 1 | 正式 POST /agent/chat，模型在 Event.wait 阻塞 | HTTP 200，首个 SSE status 取得 run/task 关联 |
| 2 | 客户端退出实际 socket stream | 原订阅最终为 None，执行 task 仍未完成 |
| 3 | 正式 status 查询 | Run 为 running |
| 4 | 错用户、错 conversation 查询 status/events | 全部统一 404 run_not_found |
| 5 | 查询阶段 wraps 真实 get_or_create | 零调用，前后 Session 查询结果完全一致 |
| 6 | 非空 Last-Event-ID 附流 | 开流前 409 |
| 7 | 释放模型阻塞点 | Task 为 needs_input，累计模型尝试 1 |
| 8 | 同 request_id、同指纹再次 chat | 复用原 run，仅终态快照/done，模型调用仍为 1 |
| 9 | 新输入识别 ORDER_QUERY | 同 task/workflow、新 run，实际 Order 骨架返回 capability_unavailable，模型调用为 2 |
| 10 | 对首个 Run 再附流 | 只有 status+done，旧 Run 结果保留 |
| 11 | 检查公开内容 | 无 thread_id、permission_scopes、Trusted pending task 等内部内容 |

随后建立 production 应用，使用同一测试库和正式 lifespan。health.agent_ready=false，chat/status/events 三个入口均为 503 demo_identity_disabled，Session 创建零调用，模型调用总数维持 2。

测试 finally 释放模型、停止 Uvicorn、关闭 socket，仅按本轮随机 conversation 和确切 dev-user 删除自己的 Session。清理后数据库行集等于测试前行集。两个应用的池与自有同步/异步 HTTP 客户端均关闭。

### 4.2 实际最终 Saver 写入失败

现有 test_commit_failure 在真实图正常返回后人为抛 OSError，覆盖 Runtime 对调用失败的收敛。独立补测进一步使用 InMemorySaver 子类，在包含 run_finish 的最终 aput 中直接抛 OSError，实际打断 sync durability 的提交。

断言最终 aput 仅失败一次、usage_complete=false、模型已确认尝试保留为 1、无最终 token、门禁释放。Run TTL 设为 0.01 秒，等待 0.03 秒后 get_run 为 run_not_found，随后 new_task 仍返回 execution_uncertain。该证据覆盖真实终结提交失败和 TTL 后阻塞保持。

### 4.3 普通结算及累计主动时间

独立补测将实际编译图类型的 aupdate_state 设为禁止调用，连续推进两次普通澄清。同 Task 的模型次数为 1→2，两次 Run 间等待 150ms。第二次累计主动时长增量小于 100ms，用户等待未计入主动预算。最终 snapshot.next 为空，Checkpoint 两类用量与 RunView 完全一致。

现有 SlowFinalSaver 用例另外验证最终提交增加 300ms 延迟、主动限额为 200ms 时仍正常完成，已冻结时钟排除最终提交等待。

## 5. D02 第 11.2 节逐项验收矩阵

以下现有用例均在本轮 109 项实际执行中通过。临时独立补测见第 4 节。

| D02 场景 | 可观察证据及用例 | 类型/真实资源 | 结论 |
| --- | --- | --- | --- |
| 通用澄清→具体业务 | test_generic_clarification_continues_task_budget_and_new_task_resets_scope；补测 TCP 续接同 task/workflow、新 run、模型 1→2 | 实际编译图/Runtime，补测使用 PG+TCP | PASS |
| 具体缺参/显式换目标 | test_specific_clarification_fills_entities_without_changing_task_goal 保 task_goal、过滤 user_id；test_specific_pending_preserved_on_unsupported_and_switch_requires_new_task 保目标；显式 new_task 新 ID/零基线 | 实际编译图/受控模型 | PASS |
| 不支持取消/非法模型输出 | 类型拒绝旧值；test_unsupported_and_structure_correction_have_bounded_attempts 固定拒绝、最多两次模型尝试；额度不足时零新请求 | 契约及实际主图 | PASS |
| 目标图与三专业骨架 | D02 4.6～4.8 分别有 State/Node/Edge 和交接；test_actual_compiled_skeletons_fail_safely_for_all_professional_tasks 的四种 Task 均 failed/capability_unavailable、无 token | 三个实际编译骨架 | PASS |
| 父子图隔离 | nested_success/foreign_result/child_input_filters/task_message_window；当前上下文相等检查、私有 ToolMessage 不入父历史、子计数 0 不覆盖已知尝试；QA 来源及批准正文约束保留 | 契约+受控成功专业图+实际 wrapper | PASS |
| 预算 | continued_model_budget_exhaustion、seeded_tool_budget、Gateway 重试/unknown 用例；补测模型 1→2、150ms 用户等待排除、快照对齐 | 受控模型/实际 Scope/图 | PASS |
| 普通结算与中断边界 | real_topology_scope_settlement_and_no_post_end_update、frozen_clock、run_finish_failure；补测实际最终 aput 失败及禁止 aupdate_state | 实际 run_finish/内存 Saver | PASS，真实 interrupt 恢复留 04 |
| 同 thread/不同会话 | gate_capacity_dedup 中同 thread 立即 thread_busy，8 个不同 thread claim，第 9 个 runtime_busy；pre_admission_cancel 清理未受理占位 | 实际 Runtime+受控阻塞模型 | PASS |
| 重复请求 | gate_capacity_dedup 同指纹复用、不重复模型、已有订阅冲突、异指纹 request_id_conflict；retention 清除索引；补测正式 HTTP 重交复用原 Run | Runtime/HTTP，补测 PG | PASS |
| 断开/慢队列 | request_guard 的 construct/preiterate/headers 三场景、real_tcp_disconnect、slow_subscription 和旧 owner 晚清理；补测真实 PG+TCP 断开执行继续 | ASGI 失败注入+实际 TCP | PASS |
| 重订阅/结束 | 首快照、只未来事件、终态 status+done；done 一次；非空 Last-Event-ID 409；补测原 Run 附流无旧 token | 正式 Route/Runtime/formatter | PASS |
| 异常/预算结算失败 | state_read_failures、timeout_uncertain、run_finish_failure、commit_failure；补测实际 aput 失败、已知用量保留、TTL 后 uncertain | 受控存储故障/实际执行 | PASS |
| 关闭/隔离 | timeout_uncertain 的 shutdown 1 秒外层限时断言，资源顺序 runtime_settled→model_closed→pool_closed；错身份/会话 404；production 三入口补测 | 实际 Runtime/lifespan，资源测试含替身，补测实际 PG/客户端 | PASS |

工具次数累计由可信测试快照置为限额，验证 Runtime 继承和停止行为。02 阶段的 ToolExecutor 递增与真实业务副作用尚属后继验收范围，报告未将种子计数解释为工具执行能力。

## 6. 测试可信度与入口覆盖审查

与 cf3e763 比较，test_postgres.py、test_config.py、test_model_gateway.py 无差异，原迁移重跑、回滚、checksum、未知版本、测试目标保护和 Session 竞争风险断言保留。

Graph 和类型测试随冻结协议迁移更新。旧取消/AfterSales 可执行值转为拒绝，Task 工厂显式提供 task/new/continue，消息及预算断言迁移到新契约。旧生成器 Runtime 的传输测试改为 formatter 独立验证，正式 Runtime/HTTP 风险另由新增测试覆盖。未观察到以删除或放宽失败断言掩盖本轮失败的证据。

现有 runtime_support.compiled 使用真实主图、三个真实骨架、ModelGateway 和 InMemorySaver，ControlledModel 只替代供应商输出。http_application 使用 MemorySessions 且替换 lifespan，因此该组测试独立证明 Route/Service/Runtime/图的行为。本轮第 4.1 节补足真实 SessionRepository 和正式 main/lifespan/TCP 的联合入口证据。

构造、首次迭代前及响应头失败测试分别向真实 ASGI app 注入响应构造错误、响应调用取消和 send(response.start) 错误，断言请求 owner 关闭、Run.subscription=None、执行 task 未完成、立即再订阅可完成。测试没有自行调用 owner.close 代替被测 guard，construct/preiterate 明确断言迭代器从未开始。消费中断开由实际 socket 测试及独立 PG+TCP 补测验证。

普通结算用例禁止 aupdate_state 并比较实际 Checkpoint，覆盖正常入口。现有 post-return commit_failure 的注入位置已明确，其证据由真实最终 aput 故障补测补齐。

## 7. 问题清单、遗留与设计判断

### 已确认产品问题

本轮新增已确认 P0、P1、P2、P3 均为 0。未记录无法稳定复现的推测性缺陷，也未发现需要主 Agent 重开冻结设计的确定冲突。

### 既有 P3-01

严重度继续为 P3，非阻塞归属沿用主 Agent 决定。D02 第 11.1 节交付检查与项目工程规范要求代码检查可追踪。本轮实际执行 Python 文件全部格式通过，全仓仍有六份设计示例 format 遗留。

| 位置 | 复现及实际 | 预期、影响及建议 |
| --- | --- | --- |
| docs/01-foundation-detailed-design.md:177 | 全仓 ruff format --check 报 would be reformatted | 全仓 format 退出 1；按原遗留归属在后续文档维护中处理 |
| docs/02-agent-runtime-detailed-design.md:71 | 同上 | 同上 |
| docs/03-tool-governance-detailed-design.md:69 | 同上 | 同上 |
| docs/04-hitl-checkpoint-refund-detailed-design.md:192 | 同上 | 同上 |
| docs/05-rag-memory-detailed-design.md:200 | 同上 | 同上 |
| docs/history/04-1-order-service-design.md:213 | 同上 | 同上 |

原 Supervisor E501、Response 和 Runtime 的代码格式遗留已在本阶段触及文件中收敛。本轮没有对冻结示例或业务代码自动格式化。

### 设计允许的限制与后继工作

三个专业骨架返回 capability_unavailable、内存 Saver、Run TTL 与 request_id 的进程内窗口、uncertain 的进程内保留、暂缺真实 HITL/PG Checkpointer 恢复、工具治理、RAG/Store 均符合 02 边界。02 的公开事件仍为 status/token/error/done。03～05 的业务及持久恢复验证继续按各阶段设计开展。

## 8. QA 执行偏差与验证边界

QA-EXEC-01 已纠正。首轮补充 pytest 文件未选择 Windows Selector，实际 psycopg 在连接前拒绝 Proactor，造成一个临时用例失败。其异常回溯包含连接关键字参数，工具输出曾回显连接参数。本报告省略其中秘密值。修正仅发生于临时 QA fixture，随后以短回溯模式运行，三项全部通过。该次失败没有执行数据库写入。

临时 fixture 的弃用 warning 保留在结果中，归属本次 QA 探针。现有仓库 109 项结果没有该 warning。本轮未为临时探针升级依赖或修改仓库事件循环配置。

本轮独立连接仅限 agent_demo_test，应用库未连接。PG 全套前后版本/checksum/Session 一致，补测创建的单个随机 Session 也已精确清理。真实模型供应商网络、bootstrap/Volume 重启、PG Checkpointer 及审批恢复没有在本轮执行。真实模型使用受控替身符合本轮授权。

## 9. 交接结论

六个 Task 的主要实现和 D02 第 11.2 节可观察门禁通过独立 QA，开发报告的 109 项完整真实库结果已核实，补充三项验证通过。当前没有需交修复会话处理的新增已确认产品问题。

建议主 Agent 复核本报告、确认既有 P3-01 及 QA 执行偏差记录后，处理阶段技术验收结论。阶段正式状态、用户批准及后续阶段切换由主 Agent 按既定流程维护。

## 10. 独立收尾核对（2026-11-11）

本节由原测试会话按主 Agent 单独派发的收尾任务追加。原报告九节正文保持其审查时事实。

### 10.1 报告来源、完整性与 Turn 状态

确认本报告由本测试会话依据上轮实际工具调用和测试结果生成。当前文件原正文共 200 行，包含总体结论、六 Task、实际命令、真实入口证据、D02 矩阵、测试可信度、遗留、QA 执行偏差和交接结论。UTF-8 可读，结尾完整，全部本地 Markdown 链接目标存在。报告中的 109 passed in 14.70s 与补测最终 3 passed、3 warnings in 15.15s，分别对应上轮已返回的实际命令结果。

主 Agent 通知上轮原生 Turn 为 failed。本测试会话可确认的最后业务动作是完整报告写入，apply_patch 返回成功。上轮未向主 Agent 正常返回最终交接回复。当前可见记录没有原生 Turn 的失败原因或调度错误详情，因此只能将已知边界定位为报告落盘后至正常最终回复完成之前，无法进一步断言具体系统故障原因。

原生 Turn 的 failed 属于会话完成状态。产品测试结果由已返回的进程退出码、断言及落盘报告支持。上轮完整现有回归退出 0、109 项通过，补充用例修正 QA 事件循环配置后退出 0、3 项通过，产品 QA 的 PASS 结论保留。正式阶段验收继续由主 Agent 复核决定。

### 10.2 临时补测及数据清理可核查性

已只读确认以下文件仍存在，包含原报告中的三项 async 测试及 Windows Selector fixture。

```text
C:/Users/15294/AppData/Local/Temp/agent-phase02-qa-7bda02066de345b6b1414d1352322536/test_phase02_independent.py
```

复核命令沿用第 3.2 节。三项名称为 test_real_pg_formal_lifespan_tcp_disconnect_query_and_production、test_actual_sync_final_checkpoint_failure_retains_uncertain_after_ttl、test_graph_no_post_end_write_and_budget_wait_exclusion。当前文件保留最后一次通过时的 Selector fixture，三条弃用 warning 归属于该临时 fixture。首轮 1 failed、2 passed 与修正后 3 passed 的结果均已在本会话工具记录中出现。

原完整回归的前后只读数据库快照相等断言通过，Session 行数为 0，版本/checksum 一致。真实 PG 加 TCP 补测的 finally 按确切 user_id 和本轮随机 conversation 删除自身 Session，随后断言完整行集恢复为 before，该断言亦通过。临时文件保留该清理及校验逻辑，可供主 Agent 复核。

本轮收尾只核对报告、临时文件与已有执行记录，未重新连接数据库，因此对当前数据库残留的判断以原轮次已通过的清理断言为证据。本轮未重新读取连接秘密，也未重复 109 项回归。主 Agent 已另行确认 88 个 Python 文件与 QA 前摘要一致。

### 10.3 QA-EXEC-01 敏感输出事实与最低后续处理

根据上轮已可见的失败工具输出，确认异常回溯包含真实测试库密码和分项连接参数。该处展示的是连接关键字参数，未展示完整 DSN 字符串。所涉连接为 agent_demo_test / agent_test，与当时临时用例只使用测试连接的代码路径一致，可确认本次回显涉及测试库凭据。

已知输出范围为本测试会话的一次 pytest 失败工具返回及其会话审计记录。本轮未重读或复制敏感回溯，未核查会话记录之外是否存在其他副本，因此不对其余留存范围作保证。当前报告只保留事实描述，静态核对未发现连接 URL 字面量、密码赋值字面量或原始 traceback。

当前会话没有可用的定点撤回既有工具输出能力。可采取的限制是后续仅交接本脱敏报告，限制原始失败回溯的复制和传播，并由具备管理权限的一方按既定访问控制管理审计记录。

最低后续处理建议为由主 Agent 将该测试角色凭据按已暴露处理，在单独授权的维护步骤中更换测试库密码并同步必要的本地测试配置，随后验证测试连接。保留本问题及回归证据。当前证据支持处理该测试角色凭据，应用库凭据不在此次回显证据范围内。本轮未执行密码或认证文件变更，也未删除会话审计。

### 10.4 收尾交接

报告完整性核对通过，原产品独立 QA 结论维持 PASS，新增已确认产品缺陷为 0，既有 P3-01 保留。待处理事项为主 Agent 复核三项临时补测、裁决 QA-EXEC-01 的测试凭据后续维护及阶段验收。会话 failed 的底层原因仍缺少原生错误详情，原轮次测试通过证据与本次正常最终回复分别交接。
