# Task6.1.2 会话/状态/事件统一交付

2026-11-14；实施及自测交付，待独立 QA。仅执行[当前 Task](06-state-events-execution-task.md)，依据 D06 第5/6/9节及6.1.2、6.1.1已通过的装配与 QA；未宣告 Task/阶段验收，未进入6.2.1。

## 修改与审计结论

实际接线已具备，沿 Route→Service→唯一 Runtime→Graph/run_finish→RunView/SSE 保留原实现。本轮唯一产品修复在 `app/runtime/agent_runtime.py:1159`：存在已受理活动 Run 时，current_task 全部使用该 Run 的可信 Task/workflow/run 关联并返回 running；避免同一 thread 的旧 Task 已完成、新 Task 尚未写首个快照时，将旧快照 Task ID 与新 Run ID/状态混合返回。持久查询、审批等待及业务状态投影继续沿既有实现。

- `tests/test_runtime.py:40`：新回归阻塞首个 Graph 调用，保留上一 Task 快照，断言公共当前任务的 task_id/workflow_id/run_id 归属一致；不改旧测试断言。
- `scripts/verify_06_state_events.py:136`：显式真实库组合探针。仅替换 Chat 输出以确定协议，正式 create_app 仍装配真实 PG 业务池/Saver/Store、Qwen CPU1024、Retriever、Registry/Policy/Executor及原专业/Memory图；没有固定成功业务替身。脚本不由默认 pytest 自动运行，不产生付费 Chat 请求。
- README 新增本交付入口。STATE、AGENTS、冻结设计、主协调与旧证据均未修改；前序工作区改动保留。

审计实际源码：Route 一次解析 `ChatRequest`，Service 返回并显式传递 context/options/owner；Runtime 在 thread 门禁内唯一生成 Task ID，workflow 为同值别名；新 Task 清空专业结果、sources及memory_read_record，澄清保留原 Task/目标/预算。父子图白名单映射而不回传私有工具历史。普通结果只有图内 run_finish 完成同步持久结算、Graph 返回并核对用量后才由 Runtime 发布 token/sources和唯一 done。KNOWLEDGE_QA 原样输出 approved_answer/PublicCitation；Memory 真实结果、unknown安全说明及 sources=[] 保留。

审批恢复继续使用04原四类分类与入口：真实 interrupt用原Command恢复；Gate后按原绑定及安全位置核对；正常END只读返回持久结果；未知拒绝盲目重放。管理受理发布 workflow_resumed，真实中断持久绑定后发布 workflow_paused。订阅只接当前快照和未来事件，无事件重放承诺。

## 中断后核查

前一轮受到 usage limit 中断，旧 exec 会话句柄不可恢复，没有6.1.2探针JSON，未把该运行计作成功。[中断核查证据](06-state-events-interruption-audit-20261114.json)在线核验专用 `agent_demo_test/agent_test`、001～006完整checksum、13张public表完整行集及列定义；无protocol612残留行、无其他活动测试连接。随后重新执行探针与完整门禁。

OS另有项目解释器的stdin进程PID45980/12488，命令行仅 `python -`，无法证明归属；父协调确认未启动shell/Python。本轮未终止所有权不明进程。自身模块探针和最终门禁均已退出。最后[清理证据](06-state-events-final-cleanup-evidence-20261114.json)核对全部public行集/列定义与中断核查时完全相同，protocol612命名连接为0。该证据不声称已解释或关闭上述不明确进程。

## 实际验证

运行解释器均为项目 `.venv/Scripts/python.exe`，测试DSN从 Settings安全读取，仅在当前验证进程设置 `AGENT_TEST_DATABASE_URL`，无凭据输出。应用仅使用获准的test/UUID用户/EmbeddingTrue临时Settings，原Qwen路径、CPU1024、模型配置与预算保持。

| 实际命令/入口 | 结果与证据 |
| --- | --- |
| `-m pytest tests/test_runtime.py tests/test_runtime_http.py -q` | 20 passed，7.51秒。覆盖新Task查询窗口、context/options、澄清用量、8活动Run门禁、请求去重冲突、TTL/容量淘汰、Owner首次迭代前/响应头/构造失败、中途断开、慢订阅、无旧token重放、run_finish失败不发布最终token、唯一done。该命令在中断前已打印完成结果，旧exec句柄现已失效；最终完整门禁重新执行了全部这些测试。 |
| `-m scripts.verify_06_state_events --output docs/06-state-events-real-evidence-20261114.json` | 首轮退出1，探针自身未给显式Memory命令选择Memory路由、搜索query未遵守实际问题收窄约束；保留[失败证据](06-state-events-real-evidence-20261114.json)，数据库前后完全相同。修正受控模型，未改产品策略/正确断言。 |
| `-m scripts.verify_06_state_events --output docs/06-state-events-real-evidence-20261114-r2.json` | 退出0/PASS；[真实持久化、受控Chat证据](06-state-events-real-evidence-20261114-r2.json)。 |
| 同一解释器stdin内 `pytest.main(['-q'], plugins=[Results])`，DSN进程内注入 | 首次完整门禁224 passed/1 failed/0 skipped，68.15秒；[原始数据保护证据](06-state-events-full-regression-evidence-20261114.json)。唯一失败为既有Store关闭后立即读pg_stat_activity断言，见下文。 |
| 同一解释器stdin内 `pytest.main(['-q','--tb=short'], plugins=[Results])`，无行为patch | 最终完整真实PG **225 passed/0 failed/0 skipped/0 deselected，59.50秒**；[最终门禁与保护证据](06-state-events-full-regression-evidence-20261114-r2.json)。插件仅统计结果和原seed用例执行结果，未改变行为。 |
| `-m ruff check app scripts tests` | 通过。 |
| `-m ruff format --check app/runtime/agent_runtime.py tests/test_runtime.py scripts/verify_06_state_events.py` | 3文件通过。 |

两个完整门禁均原样包含 `tests/test_order_postgres.py::test_real_order_constraints_isolation_and_seed_idempotence`，passed；没有deselect，没有修改其断言。该旧测试finally恢复实际读取的原is_refunded值；前后所有public行集/列定义完全相同。两轮门禁还核对 `.env`、006迁移、原seed测试、implementer/qa角色文件SHA256保持。两条anyio/langsmith AssertRewriteWarning来自验前快照导入早于pytest初始化，与前序相同。

## 真实组合探针的可观察结果

同一个正式应用和同一持久session/thread顺序执行 Memory保存→知识问答→订单澄清→订单补参续接→新订单Task→退款等待/拒绝恢复。前四次请求对应3个Task，澄清/续接原Task保持。Memory写入走原同步写前协议及Executor；知识正文与approved_answer逐字相等，SSE token与RunView都携带服务器校验后的当前PublicCitation，本轮UUID文档经真实Qwen向量和PG检索/来源校验。

澄清用量1模型/0工具，续接后累计4模型/2工具；跨Task不带旧sources、专业结果或偏好读取记录。首快照前受控阻塞时，HTTP current_task返回新Task/新Run，第二普通执行409。

退款真实Gate中断时公共状态waiting_approval，父图最后快照仍可为running；本轮以Runtime/实际interrupt分类及子图用量为据，没有强制父快照等于公共等待状态。已绑定原application/approval/call/operation，子图及RunView累计2模型/5工具。普通auto和new_task均409。本地REJECTED后恢复创建新Run，原Task/operation保持；结束时run_status=completed而task_status=rejected，累计3模型/6工具、活动时间240→414ms，订单is_refunded=false。正常END再次resume返回200/accepted=false/run_id=null，模型调用数和Run数不变。删除可丢失Run缓存后Run查询404，持久current_task和退款业务REJECTED仍可查。此项为受控缓存丢失，不声称完整进程重启证据。

每条SSE链校验递增唯一sequence、同值Task别名和唯一done，禁止私有planner/结构化消息、call_records、权限、raw_args、namespace及Embedding profile透传。Owner与缓存保留规则未改，沿02既有测试及本次最终全量结果验证。

## Store关闭断言波动与证据边界

首次完整门禁在旧 `tests/test_memory_postgres.py:277` 失败；原用例定向无patch复核又在同类普通关闭断言 `:263` 失败（[复核证据](06-state-events-store-recheck-evidence-20261114.json)），各轮完整public数据保护通过。没有放宽旧断言或修改Store产品代码。

读取实际安装源码确认 pool.close关闭本地客户端，PG服务端连接视图的即时收敛仍须区分。[三轮只读关闭诊断](06-state-events-store-close-diagnostic-20261114.json)中pool.closed及客户端closed均true，随后连续服务端查询均0。在原用例上只观察pool.close和原计数、保持原断言的[第二轮观测](06-state-events-store-close-observed-test-20261114-r2.json)为1 passed：普通/异常/取消三个出口客户端均closed、PG计数0。首轮观测脚本误读池字段 `_kwargs` 而失败，修正为实际kwargs后才得到这些结果；[首轮工具错误](06-state-events-store-close-observed-test-20261114.json)保留，没有算为产品故障或通过证据。

最终无patch完整门禁225项通过，后续不再重复检查。上述即时连接视图断言波动的严格根因仍未证明；本轮证据支持客户端关闭与最终服务端归零，不能以此断言所有时序均稳定。该观察项交独立QA判断，未新建任意等待/轮询、修改前序Store或承诺已根治波动。

本轮Chat为受控协议输出，不作为模型语义或偏好语言效果证明。未变的真实Chat双题英语偏好/业务路径沿[6.1.1 R5](06-assembly-real-evidence-20261114-r5.json)及[独立QA](question/06-assembly-qa-report.md)归因复用。这里的受控中文ANSWER不用于验证en偏好遵循。完整进程重启、Gate后故障与未知窗口矩阵、跨场景隔离退化、Apifox及演示属于后续Task，本轮未执行。

全部新增业务数据使用UUID隔离订单/文档/profile/session/thread，按原FK精确清理；无新seed/固定五订单写场景。未Git操作、Bridge、SSH、PG重启、容器重建、另派Agent或修改Codex账户/模型provider。交付后停止，等待主Agent安排独立QA。
