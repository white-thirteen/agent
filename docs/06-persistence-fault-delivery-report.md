# Task6.2.1 核心持久化故障实施交付

2026-11-14；仅执行[当前Task](06-persistence-fault-execution-task.md)，依据冻结D06第6节及Task6.2.1，交主Agent审查与独立QA。本文不代表阶段验收，不进入6.2.2。

## 修改范围

新增 `scripts/verify_06_persistence_faults.py`，显式运行的真实TCP/进程验证驱动；生产源码、数据库迁移和依赖没有修改。正式 `create_app` 生命周期装配真实业务PG、AsyncPostgresSaver、AsyncPostgresStore、原Qwen CPU/1024、Registry/Policy/Executor及三专业/Memory/根图，只有Chat输出和指定故障边界由测试侧控制。没有增加产品故障开关、恢复API或仓储。

故障注入沿用04的Saver.aput/aput_writes、退款handler前边界和绑定失败；原退款Domain、事务、审批Gate与Runtime恢复分类均真实执行。脚本工厂的只读诊断路由仅绑定本机随机端口，用于观察本轮自有应用的原调用、快照分类、节点、调用形式和handler尝试，不进入正式应用入口。

Windows项目 `.venv` 启动器PID与实际服务Python PID不同，证据分别记录Popen PID、server PID、命令、启动时间、就绪耗时和退出。驱动只通过taskkill终止自身Popen树，等待退出后才启动下一进程；此处是完整进程强制退出，非同进程Runtime重建，也非PG重启。所有场景串行，仅一个Qwen服务实例。

## 实际验证及边界

解释器均为项目 `.venv/Scripts/python.exe`。Settings只选择专用test库/UUID演示用户及EmbeddingTrue，保留原模型/provider配置、Qwen CPU线程/1024和预算。受控Chat没有付费请求；这里的结果不用于证明真实模型语义。

- [R1](06-persistence-fault-evidence-20261114-r1.json)、[R2](06-persistence-fault-evidence-20261114-r2.json)：退出1。真实中断及重启后决定已完成，探针对并发第二响应直接读取accepted字段触发KeyError。第二请求可在受理门禁返回409/thread_busy；修改探针解析后保留精确错误类别及唯一受理要求。R2是本地编辑命令编码失败后旧脚本再次执行，不能算修复后验证。两轮finally均确认全部public行集及列定义相同，未将探针失败称为产品故障或通过。
- [R3正常场景](06-persistence-fault-evidence-20261114-r3.json)：`-m scripts.verify_06_persistence_faults --output docs/06-persistence-fault-evidence-20261114-r3.json --modes normal`，退出0/PASS。真实中断后全进程退出，新进程按原interrupt恢复；两个TCP客户端并发resume恰一个202受理，另一个409且实际code=thread_busy。原Task/call/args/application/operation/approval/namespace保持，原订单一次模拟退款、唯一成功申请。再次全进程退出/启动后，END的resume返回200/accepted=false/run_id=null，零新Run、Graph调用和退款handler。全部public数据恢复。

- [R4故障组合](06-persistence-fault-evidence-20261114-r4.json)：`-m scripts.verify_06_persistence_faults --output docs/06-persistence-fault-evidence-20261114-r4.json --modes reject repair checkpoint unexecuted pending barrier expired_pending expired_approved success_expired business_unknown`，退出0，十个场景均PASS。
- [R5缺失快照](06-persistence-fault-evidence-20261114-r5.json)：`-m scripts.verify_06_persistence_faults --output docs/06-persistence-fault-evidence-20261114-r5.json --modes missing`，退出0/PASS。仅删除自有UUID Session的Saver线程，保留原申请/审批后全进程退出；新进程返回409/execution_uncertain，零Run/Graph/handler，原审批不变、业务PENDING、订单未退款。

R3～R5共12个独立UUID场景、31个记录launcher/server PID的服务进程，旧树退出后才加载下一个Qwen；实测启动至ready为19.528～25.898秒。正常END的额外跨进程验证只在normal执行，其余分支在各自最终进程核对END只读，不为相同分类机械重载模型。

| 本轮实际场景 | SQL/Checkpoint及恢复结果 | 退款handler尝试（等待/故障或首次恢复/再次恢复） |
| --- | --- | --- |
| normal | 原Gate、Command恢复；第二客户端409/thread_busy；再次完整进程重启后END只读 | 0/1/0 |
| reject | 原决定REJECTED、Task rejected、申请REJECTED、订单未退款 | 0/0 |
| repair | 已存interrupt但自动绑定失败；未绑定不能决定；新进程repair原绑定，重复repair幂等无Run；批准后原调用成功 | 0/1 |
| checkpoint | SQL先SUCCEEDED，结果aput/aput_writes失败，原next=execute_refund；新进程根/子None重入，可信succeeded context复用 | 0/1/0 |
| unexecuted | 原尝试已同步，但execute handler前故障；新进程核对原operation未开始，重新检查并保存新Run的新attempt后执行 | 0/0/1 |
| pending | 结果pending writes残留、原业务SUCCEEDED，框架快照分类unknown；新进程409，零Run/Graph | 0/1/0 |
| barrier | prepared_attempt同步失败，无可信准备窗口；新进程409，零Run/Graph | 0/0/0 |
| expired_pending | GET不改PENDING；POST resume按DB时间惰性转EXPIRED，原Gate使Task及申请rejected | 0/0 |
| expired_approved | APPROVED过期后Graph拒绝新写，保留人工决定/审核信息，申请REJECTED、订单未退款 | 0/0 |
| success_expired | 业务成功/结果快照失败后，只将本轮审批按原30分钟关系置过期；新进程仍复用原成功，不执行退款写 | 0/1/0 |
| business_unknown | execute前故障的可信窗口仍在；新进程原operation核对读取受控失败，409，零Run/Graph，业务仍PENDING | 0/0/0 |
| missing | 自有原线程Saver已缺失，新进程拒绝自动恢复，保留申请/审批与未退款订单 | 0/0 |

handler计数观察真实 `MockRefundService.execute_original` 入口；正式refund_order handler在可信context核验后直接调用此入口，未替换实际事务。成功恢复均核原Task/workflow/thread、call/name/raw/canonical args/digest、application/operation/approval、子namespace不变；新Run继承原模型/工具/主动时间。确认未执行的恢复使用不同于旧标记的attempt_id及当前run_id；已成功恢复沿原节点执行且退款handler为零，没有用“跳过节点”的假设代替检查。

正常结束/拒绝路径均在原namespace读取恰一条同call ToolMessage，ID为 `tool:{task_id}:{call_id}`；SQL订单标记及成功申请计数相符。重复同决定保留原审核人/时间/期限，相反决定409；重复END resume不新增Run/图/handler。最终审计逐场复核created_at/expires_at无续期，APPROVED过期不改人工决定、成功op过期保留原成功；unknown与缺失快照未被写成执行成功。

### 定向检查与最终审计

在项目解释器stdin内从Settings安全读取test DSN，仅注入本进程 `AGENT_TEST_DATABASE_URL`，执行 `pytest.main(args, plugins=[Results])`。args为 `tests/test_refund_checkpoint.py tests/test_refund_transactions.py tests/test_refund_repair_postgres.py tests/test_approval_routes.py tests/test_approval_constraints.py tests/test_refund_full_controlled.py tests/test_refund_executor.py -q --tb=short`：**21 passed、0 failed、0 skipped，15.48秒**，见[定向证据](06-persistence-fault-targeted-evidence-20261114.json)。Results只记录用例结果，未改测试行为。anyio/langsmith的两条AssertRewriteWarning来自验前快照导入顺序，与前序相同。

`-m ruff check app scripts tests`通过；`-m ruff format --check scripts/verify_06_persistence_faults.py`通过。依赖未变，无需安装或升级。

[最终审计](06-persistence-fault-final-audit-20261114.json)实际在线确认PG17.6/pgvector0.8.7和专用身份、001～006全部checksum；最终全部public行集/列定义与R3最初baseline、定向回归后完全相同。R4/R5前后 `.env`、006、原seed幂等测试及两角色文件SHA256一致，结束时再核一次保持。Win32_Process只读查询没有本脚本遗留Python验证进程；没有终止任何其他进程。原失败R1/R2与所有后续证据均保留。

## 复用证据

生产恢复路径未修改。04的完整矩阵与修复后独立复测继续作为未变化分支证据：[04最终复测](question/04-hitl-checkpoint-refund-fix-02-regression-report.md)、[04实施](04-hitl-checkpoint-refund-restart-report.md)。其中repair错误审计Checkpoint/已决定空绑定/CAS主体变化拒绝、响应丢失重试、并发repair、审批GET八字段只读、撤权/预算/资格复检等不冒称本轮重新做了全部进程排列。

6.1.2最终完整真实PG门禁225 passed/0 failed/0 skipped/0 deselected，见[原始证据](06-state-events-full-regression-evidence-20261114-r2.json)及[独立QA](question/06-state-events-qa-report.md)。本Task无生产行为变更，复用该完整门禁；原seed幂等测试已在该门禁原样执行，不新增排除或扩大固定订单例外。Store关闭后即时视图波动的严格根因仍未证明，沿前轮与独立QA证据保留观察边界，没有顺带重构Store。

## 数据与操作保护

每场景运行前在线验证 `agent_demo_test/agent_test`、001～006全部本地/登记checksum，保存全部public表完整行集与列定义。新数据仅本轮UUID订单/用户/会话；finally按自有用户精确删除审批→申请→Session/订单，对原Session发现的自有线程调用Saver.adelete_thread，然后完整比较前后public数据。没有seed或修改固定五订单。

没有改用户.env、006、冻结设计、角色配置、前序证据、STATE/AGENTS/主协调或六项暂缓差异。没有Git写操作、Bridge、SSH、PG/容器重启、另派Agent或后继Task。

## 交回与未验边界

本Task实施及必要验证已完成，未发现需要修改生产代码的问题；交主Agent审查及独立QA，随后停止。真实Chat语义沿6.1.1既有真实证据；本轮不新增付费调用。强制进程退出验证持久恢复，不据此声称任意Python指令冻结、全局Exactly Once、多进程互斥或持久SSE事件重放。未知快照/无可信准备窗口/业务核对读取失败继续拒绝盲重放，是保留边界。没有本Task尚未完成的实施项；阶段正式验收仍须用户批准。
