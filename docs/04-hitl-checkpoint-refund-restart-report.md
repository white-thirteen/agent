# 04 Task 4.3.2 重启及重放验收：Implementer交付

日期：2026-11-13。基线HEAD `50e4c55476e714ed1e6d692511d8d878108c399b`，验证对象包括工作区既有未提交实现。范围按[本工作单元](04-hitl-checkpoint-refund-restart-task.md)及冻结D04执行，未改冻结设计、历史证据、协调记录或生产代码，未调用Bridge/其他会话/子Agent，未提交或推送，未进入05。

**本Task开发自测通过，交主Agent安排独立QA；不标记04为VERIFIED或ACCEPTED。** 已完成正式应用拓扑、真实PG、独立Python及真实uvicorn/TCP重启、提交后持久化故障、可信原调用恢复和少量真实模型联调。未知快照形态仍安全拒绝，详见限制。

## 1. 文件与证据层次

- [verify_04_restart.py](../scripts/verify_04_restart.py)：显式验收入口。生产`create_app`生命周期创建真实SessionRepository、ApprovalService、MockRefundService、Registry/Policy/Executor、Supervisor/Refund Graph及严格AsyncPostgresSaver；受控分支仅替换模型和明确故障边界。每个wait/fault/resume阶段由独立Python子进程执行HTTP入口，父进程等待该进程退出后才启动下一阶段。
- [verify_04_tcp_restart.py](../scripts/verify_04_tcp_restart.py)：真实uvicorn factory和本机HTTP；父进程仅编排及只读核对，不持有应用Runtime/Graph。收到真实waiting后停止旧uvicorn PID并wait确认退出，再启动新PID，仅提交原审批decision/resume。
- 本报告、下列10份安全JSON证据及README必要导航。JSON仅包含本次专用身份/ID、原工具参数/摘要、节点/调用形式、用量、PID和状态，不包含凭据、连接地址或模型内部原文。

| 证据 | 实际验证 |
| --- | --- |
| [normal](04-restart-evidence-normal.json) | 正式拓扑/真实PG，wait PID23600退出后PID18780恢复；原调用完成 |
| [checkpoint](04-restart-evidence-checkpoint.json) | wait42800→故障8016→恢复29968；SQL成功而执行结果Saver持久化不可用，`next=execute_refund` |
| [reply](04-restart-evidence-reply.json) | wait25452→故障30736→恢复34140；SQL成功、`next=compose_refund_reply`安全后段 |
| [barrier](04-restart-evidence-barrier.json) | 准备标记sync失败，零退款handler；无可证明执行窗口，后续显式resume409且零新Run/Graph/handler |
| [unexecuted](04-restart-evidence-unexecuted.json) | 已sync标记、handler前故障；确认未执行，当前审批/Policy/资格/预算再检，新attempt在新Run sync后执行 |
| [pending](04-restart-evidence-pending.json) | 仅aput失败但pending writes已保存的真实框架未知形态；业务SUCCEEDED，重启后409、零新Run/Graph/handler |
| [repair](04-restart-evidence-repair.json) | 真实PG Gate已持久但首次绑定写失败；决定409，repair读取原真实interrupt补绑，重复repair幂等、零新Run，随后跨进程恢复 |
| [tcp](04-restart-evidence-tcp.json) | 真实uvicorn本机TCP完整业务重启；记录old/new PID、旧进程退出及真实源表前后事实 |
| [real](04-restart-evidence-real.json) | 现有配置`deepseek-flash`，真实模型/真实PG/正式拓扑，wait3376退出→resume26080；原生ToolCall、handler一次、真实源表成功 |
| [regression](04-restart-evidence-regression.json) | 完整真实库回归及业务全行集/五订单/迁移/Saver线程保护核对 |

受控模型/故障用例使用ASGITransport调用正式HTTP Router，不能单独证明TCP或uvicorn；TCP证据单独列出。真实模型只有显式`--real`调用，不进入默认pytest或默认受控脚本。

## 2. 实际命令与结果

均使用项目`.venv/Scripts/python.exe`，PG异步操作使用项目Windows selector runner。秘密仅从现有Settings在进程内读取。

| 命令/入口 | 结果 |
| --- | --- |
| `python -m scripts.verify_04_restart` | 7个场景全部PASS，无skip；每场独立setup/wait/fault或resume/cleanup，全部退出0 |
| `python -m scripts.verify_04_tcp_restart` | PASS；真实uvicorn/TCP重启，精确清理通过 |
| `python -m scripts.verify_04_restart --real` | PASS；少量显式真实模型调用，累计模型尝试3、工具尝试6；精确清理通过 |
| 保护harness内`pytest.main(['-q','-rs','--tb=short'])`，进程内显式设置现有`AGENT_TEST_DATABASE_URL` | **164 passed，0 failed，0 skipped，53.36s**；两条已导入anyio/langsmith的assert-rewrite警告，无功能失败；未调用真实模型 |
| `python -m ruff check . --output-format concise` | All checks passed |
| `python -m ruff format --check app tests scripts` | 120 files already formatted |
| `python -m ruff format --check .` | 182 files already formatted、6份既有Markdown需格式化；沿既有P3-01保留，不修改冻结/历史文档 |

调试阶段实际出现过验收脚本误用`RunUsage.active_seconds`、单个Saver写入边界留下不同快照形态、错误预期未sync标记能够自动恢复等失败，均当轮精确清理后纠正脚本；未修改产品或正确业务断言。最终结果是上表实际完整运行。单个aput失败产生的unknown没有被隐藏或改造为可恢复形态，另立pending证据。首次Ruff发现新脚本格式问题后已修正；上述为最终代码检查结果。

## 3. 实际恢复调用、重入与原关联

本机实际版本：LangGraph 1.2.20、langgraph-checkpoint 4.3.1、langgraph-checkpoint-postgres 3.2.0、langchain-core 1.7.6、psycopg 3.3.8、uvicorn 0.54.0。未变更依赖。

实际记录到：首次根`ainvoke(dict)`→wrapper子`ainvoke(dict)`；真实Gate恢复根`ainvoke(Command(resume={真实interrupt.id:原审批引用}))`→原wrapper子`ainvoke(None)`；Gate后受控核对为根`ainvoke(None)`→原wrapper子`ainvoke(None)`，两层context均为新run及`execution_mode=reconcile`。未使用Command(goto)、图外批准/结果注入或重新提交退款文本。

每阶段核对相同thread/task/call/raw_args/canonical_args/args_digest/operation/subject_digest/approval及child namespace。普通恢复和真实模型恢复仍为原task，新run；Graph正常END重复resume200、accepted=false、无新Run。最终读取原namespace child，原call对应稳定`tool:{task_id}:{call_id}`的ToolMessage恰好一条。源表订单is_refunded=true与原申请SUCCEEDED吻合。

checkpoint场景的真实SQL事务先提交；随后测试边界使包含执行结果的`Saver.aput_writes`和`Saver.aput`均失败，避免把已保存pending write当丢失结果。实际最新child.next为execute_refund。新进程只读核对原operation成功后，以当前可信refund_recovery进入该原节点，再经record_tool_outcome/compose/map_result，**退款handler尝试0**，原operation和消息闭合无重复。不是只依赖Domain幂等返回证明零写。

reply场景在实际成功后compose节点抛测试异常，next为compose_refund_reply；新进程以相同成功事实恢复且退款handler尝试0。该窗口没有可信的全部模型主动时间上界，按既有恢复限制仅事实收敛，累计模型次数保持2，没有免费新模型请求。业务成功不被技术失败覆盖。

unexecuted场景在写前标记sync后、execute节点调用handler前抛异常，原申请仍PENDING；原next=execute_refund。新进程原execute重入发现旧run标记，进入recheck/prepare，创建不同attempt_id且run_id为当前run的新标记并sync；handler仅在新标记后调用一次。累计工具次数5→9，模型2→3、主动时间333→5642ms，未清零旧Run消耗。

checkpoint场景累计工具6→6、模型2→3、主动时间553→5651ms；已落盘标记的可能执行窗口保守补计，不能称精确观测。每次恢复验证用量至少继承waiting快照。等待时间不计主动时间的时钟细节复用本次全回归既有预算测试与独立QA，未把进程关闭/崩溃时间称为可精确持久。

## 4. 数据保护与清理

每个新场景先`validate_test_target`，在线核对`agent_demo_test/agent_test`，确认001～005及本地迁移文件SHA256与数据库登记checksum逐项匹配，再保存sessions/demo_orders/refund_requests/approvals/schema_migrations**全行集**和Saver线程集合。每次仅插入唯一`restart04-*`用户/订单/会话及Runtime稳定thread/operation，未在应用库运行、未创建环境、未setup Saver或迁移、未换密。

独立cleanup进程先按专用用户/订单和外键删除本单元审批、申请、Session与订单，再调用Saver.adelete_thread删除本次真实thread，核对checkpoints/checkpoint_writes/checkpoint_blobs该thread均零行。前后业务全行集、全部迁移行及Saver线程集合完全一致。调试失败轮同样完成精确清理，未批量删除他人数据。

完整真实库回归的保护harness另保存完整前后快照，逐一核对5个固定订单的owner/amount/currency/created_at与既有SAMPLES一致，并在结束比较完整行集。主Agent只读审查既有test_order_postgres/seed_orders后明确批准**一次窄例外**：该既有门禁执行ON CONFLICT DO NOTHING的seed幂等检查并临时修改a-001的is_refunded，finally恢复原值。该例外保留原测试/断言，不Mock核心、不deselect；没有用seed恢复数据或覆盖状态。其余新增场景严格不seed、不改固定订单。完整回归后所有业务行/迁移/线程及5订单原值一致。

## 5. D04第15节24项证据索引

R表示本次164项完整回归；Q表示[已关闭六问题独立复测](question/04-hitl-checkpoint-refund-fix-01-regression-report.md)，复用该可信证据，不声称本次重新执行外部QA。下表明确真实PG、受控及历史独立证据的边界。

| # | 冻结场景 | 证据与层次 |
| --- | --- | --- |
| 1 | 正常申请/批准/模拟执行 | normal、tcp、real：真实PG/正式拓扑/独立进程；源表同事务成功 |
| 2 | 管理拒绝 | R:test_refund_full_controlled拒绝原call、零handler；test_refund_transactions真实PG拒绝/订单未变化 |
| 3 | GET审批视图 | R:test_approval_routes与Q；真实PG视图在各新场景实际读取，完整派生字段组合用受控路由证据 |
| 4 | 过期Resume | R:test_refund_transactions：真实PG锁后DB时间、PENDING到期转EXPIRED、未到期拒绝；受控Gate过期收敛复用Q |
| 5 | Task兼容别名 | R:test_approval_constraints真实PG约束、test_refund_preparation及checkpoint分类；所有新场景task关联保持 |
| 6 | 重复决定 | R:test_refund_transactions真实PG相同决定原审计时间/到期不续期、相反决定冲突 |
| 7 | 未付/已退/他人订单 | R:真实PG退款资格/事务；订单跨用户查询和固定样例门禁通过 |
| 8 | 普通chat/伪Actor/错主体 | R:路由extra forbid、身份/Policy/Executor错误主体；Q撤权与闭合；新流程审批只走本地管理入口 |
| 9 | 真实waiting | normal/repair/real：真实Saver Gate、namespace、interrupt；普通输入409复用R/Q |
| 10 | 中断持久但绑定失败 | repair真实PG/实际Gate/真实CAS及重复repair、未绑定决定409；异常位置/环境/忙碌组合R:test_refund_checkpoint与Q |
| 11 | 完全重启 | tcp真实uvicorn旧PID退出、新PID；normal/real及各故障阶段不同Python PID，原关联保持 |
| 12 | 审批后再检 | unexecuted完整PG恢复再检/新标记；R:test_refund_transactions当前权限/期限/资格与Executor复核；Q撤权 |
| 13 | 原ToolMessage | 所有完成新场景读取原child消息，原call恰一稳定ID；R/Q私有历史不入SSE |
| 14 | 重复/并发 | R:test_refund_transactions真实PG同订单不同operation竞争/同operation重放/相反决定竞争；test_refund_checkpoint重复resume单Run为受控证据 |
| 15 | 过期/失效 | R真实PG批准到期拒绝新效果、成功后到期原事实仍可复用；受控Gate收敛R/Q |
| 16 | SQL成功回复/快照丢失 | checkpoint next=execute、reply next=compose，当前context成功复用，零退款handler；pending写残留未知形态单独拒绝 |
| 17 | 未执行/未知核对 | unexecuted真实PG新attempt及sync；barrier/pending409零Run/Graph/handler；Q核对异常和矛盾形态 |
| 18 | 实际调用/重入守卫 | normal/checkpoint/unexecuted JSON invocations与nodes；根Command或None、子None、原namespace、当前run/refund_recovery均实测 |
| 19 | 四种Resume | normal真实Gate、checkpoint/reply真实后段、全部完成场景END200零新Run、pending真实未知形态409 |
| 20 | 执行前/后崩溃 | barrier sync失败零handler、unexecuted执行前、checkpoint/reply提交后；独立进程退出后恢复；未声称任意Python指令可恢复 |
| 21 | 任务预算 | 新场景累计计数/保守时长；R:test_runtime/test_refund_checkpoint和Q-003耗尽/未知窗口无新额度，等待不计时为受控时钟证据 |
| 22 | 中断/结算隔离 | 正式PG真实中断无正常专业结果，resume使用当前context；R:test_runtime run_finish一次/最终Checkpoint延迟及Q |
| 23 | SSE/HTTP断开 | 复用Q所述真实本机TCP断开后继续执行证据；本次R:test_runtime_http既有订阅生命周期。新tcp证明重启，不声称另测恢复Run TCP断流 |
| 24 | 业务/技术状态分离 | checkpoint/reply/pending的真实申请SUCCEEDED保留；状态查询来自源表；Q-003完成事实收敛无再次申请/执行 |

## 6. 限制与交接

没有发现需要本Task修改的产品缺陷。实际发现的框架形态说明必须保留：单独aput失败时，pending writes可能已保存，根仍等待wrapper而child.next为空/任务已完成；当前分类unknown，重启后显式resume409。此时业务表SUCCEEDED可查询，**不能自动恢复该未知形态**，需要操作者核对；没有放宽分类、篡改快照或补写批准/结果来强迫完成。

准备标记尚未sync的barrier同样缺少可信主动窗口边界，当前拒绝自动推进；只在已sync、可核对且预算足够的unexecuted路径验证新尝试。测试覆盖明确安全点，不承诺任意进程崩溃、全局Exactly Once、多实例互斥、模型Token/崩溃时钟精确核算或持久SSE重放。

除TCP主路径外，故障用例通过ASGITransport在完整独立Python进程内运行；故障由测试边界抛异常后正式生命周期退出，不声称在真实支付系统断电。模拟数据与模拟退款均落真实测试数据库，不涉及真实支付。真实模型只验证本次原生调用闭环，不替代受控故障/安全回归。

本次只完成Implementer验收与证据交付，独立QA和主Agent复核尚未执行，04阶段用户验收未完成。既有凭据/密码复用与6份Markdown格式遗留按既定决定保留。
