# 04 Task 4.3.2及阶段剩余门禁独立QA

日期：2026-11-13；HEAD：`50e4c55476e714ed1e6d692511d8d878108c399b`，包含工作区既有未提交实现。依据[任务](../04-hitl-checkpoint-refund-restart-task.md)、[Implementer交付](../04-hitl-checkpoint-refund-restart-report.md)及冻结D04第9/13/15节，复用[六问题独立复测](04-hitl-checkpoint-refund-fix-01-regression-report.md)，未重做该轮。

**结论：NEEDS_FIX。** 真实PG正式拓扑的完整TCP重启、SQL提交后Checkpoint故障、compose安全后段、确认未执行的新标记及sync屏障独立复测通过；新增 **04-QA-007 / P2：repair-binding异常状态及审计关联再检缺失**，三个子项均实际复现。第15节第10项失败，当前不能给04阶段技术通过结论。技术验收由主Agent，用户验收/归档/阶段转换未授权。

## 1. 独立性、环境与证据边界

执行前保护app/tests/scripts/migrations非缓存文件、全部既有docs文件、AGENTS和README，共204文件SHA256。清单及结束核对保存在独立目录R：

`C:/Users/15294/AppData/Local/Temp/agent04-restart-qa-20261113-131121`

未改生产代码、现有测试/脚本、冻结设计或原始JSON。仓库只新增本报告；临时复现仅写R。未提交/推送、调用Bridge/其他会话、派生Agent、运行05、换密、改基础设施、seed或迁移。未重复付费模型或完整回归；复用主Agent认可的Implementer **164 passed/0 skipped**、Ruff及显式`deepseek-flash`真实模型记录，不能称这些是本轮重新执行。

结束比对204个原文件，203个相同；唯一变化为`docs/question/04-hitl-checkpoint-refund-main-review.md`。主Agent已明确确认由其在本轮更新4.3.2交付与007裁决/修复任务，非本QA写入。实现、tests、scripts、迁移、10份既有JSON及Implementer交付报告均未改变；报告链接检查无断链。新建协调任务不属于原文件摘要集合，不冒称仓库所有文件均零变化。

先审查脚本的相对输出与子进程启动：Settings的PROJECT_ROOT和MIGRATIONS_DIR仍指仓库，子进程均以`-m scripts...`继承PYTHONPATH。实际运行时cwd=R、PYTHONPATH=`D:/py/agent-project/agent`，R/docs保存独立新JSON；原docs下10份JSON未覆盖。脚本用正式`create_app`生命周期、SessionRepository、ApprovalService、MockRefundService、Registry/Policy/Executor、根/Refund图和严格AsyncPostgresSaver。受控分支只替换模型与指定测试故障边界，不注入批准State或使用Command(goto)。

## 2. 实际命令与结果

P=`D:/py/agent-project/agent/.venv/Scripts/python.exe`。以下均在R中执行，使用上面的PYTHONPATH。PG用项目Windows selector runner；没有并行数据库测试。

| 实际命令 | 结果及本轮独立事实 |
| --- | --- |
| `P -m scripts.verify_04_tcp_restart` | **PASS，exit0**；uvicorn PID2560完全退出后PID43168启动，真实本机TCP按原审批恢复，同task/thread/call/raw与canonical args/digest/operation/namespace，PENDING/未退款→SUCCEEDED/已退款 |
| `P -m scripts.verify_04_restart --mode checkpoint` | **PASS，exit0**；wait21036→fault30460→resume26104，handler次数0/1/0；真实SQL提交后Saver的aput_writes/aput结果持久化均故障，真实next=execute_refund；新进程原节点成功事实复用 |
| `P -m scripts.verify_04_restart --mode unexecuted` | **PASS，exit0**；40384→31812→16128，handler 0/0/1；旧marker已sync，原execute边界前故障，恢复再检后新attempt/current run且sync后执行 |
| `P -m scripts.verify_04_restart --mode reply` | **PASS，exit0**；26176→19736→27476，handler 0/1/0；next=compose_refund_reply，恢复仅闭合原成功事实，保留累计用量和当前context |
| `P -m scripts.verify_04_restart --mode barrier` | **PASS，exit0**；3060→28196→41704，handler 0/0/0；prepared marker的Saver写入失败，next=prepare_refund_attempt；无可信窗口时显式resume409、零Run/Graph/handler |
| `P R/repair_negative.py` | **预期安全断言FAIL，exit1**；已决定空绑定、无效原审计Checkpoint两个子项均实际HTTP200；两个场景finally精确清理通过 |
| `P R/repair_negative.py --cas-only` | **预期安全断言FAIL，exit1**；Runtime检查后、真实绑定事务前主体摘要变化，仍实际HTTP200；finally精确清理通过 |

五个正向场景全部打印`CLEANUP_FULL_ROWSETS_MIGRATIONS_THREADS_UNCHANGED`；三个异常场景也分别打印同一清理成功摘要。没有将负向探针的exit1写成产品通过。该探针保留正确409期望，没有为通过改断言。

新证据为R/docs中的`04-restart-evidence-{tcp,checkpoint,unexecuted,reply,barrier}.json`，以及R中的`repair-negative-evidence.json`、`repair-cas-negative-evidence.json`。这些文件与命令输出属于本轮独立证据。Implementer原normal/pending/repair/real/regression JSON本轮只审阅复用。

## 3. 04-QA-007：repair-binding异常状态及审计关联再检缺失

**P2，FAIL，需修复。** 冻结[D04 9.6](../04-hitl-checkpoint-refund-detailed-design.md:630)明确要求：空绑定审批仍未作决定；已有绑定检查原审计Checkpoint关联；事务内再比对主体/状态；不同关联拒绝，不能补造授权。三个子项来自同一修复控制面校验缺口，可合并处理。

| 子项及最小复现 | 期望 | 实测 |
| --- | --- | --- |
| A：通过正式图生成真实等待/审批；仅将本轮唯一审批行置APPROVED（含审计人/时间）且三绑定全NULL；新应用调用原repair-binding | 409，不补绑定，不发起Run/图/退款 | **200，repaired=true**，审批被补绑；new_runs=0 |
| B：正式等待的原审批仍PENDING且已绑定；仅把其checkpoint_id换为随机UUID，并先查询确认该thread下此Checkpoint不存在；调用repair-binding | 409审计关联冲突，不把不存在的原审计定位当成功绑定 | **200，repaired=false**；new_runs=0，异常行保持原状 |
| C：正式等待后只清空本轮三绑定，保持PENDING。Runtime检查真实快照后、调用真实bind_interrupt事务前，测试边界仅把本轮subject_digest改为另一值；不修改Runtime检查或事务代码 | 真实绑定事务内重新检查主体并409，三绑定保持空 | **200，repaired=true**；new_runs=0，变化后的主体仍被补绑 |

复现文件：`R/repair_negative.py`；A/B由默认入口执行，C由`--cas-only`执行。初始化/等待/清理复用原脚本`--worker setup/wait/cleanup`，三轮均使用独立唯一`qa04-repair-negative-*`数据。脚本第36～49行构造A/B异常，第61～67行在真实CAS前构造C。Graph.ainvoke替换为失败探针、Run集合实测为空，三轮均没有恢复/退款动作。

源码证据：

- [Runtime repair](../../app/runtime/agent_runtime.py:145)仅要求分类pending；[bound分支](../../app/runtime/agent_runtime.py:195)直接返回repaired=false；空绑定路径没有要求decision=PENDING。
- [分类器绑定检查](../../app/runtime/refund_checkpoint.py:151)核对非空、namespace和interrupt.id，未验证原checkpoint_id所指审计快照存在/关联。
- [ApprovalService.bind_interrupt](../../app/workflows/approvals.py:141)锁原审批行后只比较绑定元组；[空绑定UPDATE](../../app/workflows/approvals.py:156)缺少主体摘要/申请/session及当前决定状态再检。C正是在外层核验与该短事务之间改变主体，不能靠先前读校验覆盖。

这是**受控异常数据库状态/并发变化测试**；本轮未证明普通decision API能自然创建APPROVED且空绑定，也未观察到重复退款或普通聊天获得审批权。风险是异常审批被控制面报告为修复成功，原审计关联无法验证，外层已检查主体在事务前变化仍落绑定，不满足冻结安全失败契约。修复应使用现有Runtime/ApprovalService的最小校验，保持真实等待、原审计关联、同绑定幂等、过期不续期与零新Run，不新增授权平台。修复由主Agent交Implementer，本角色不改业务。

## 4. 实际恢复语义与数据保护

源码及本轮JSON共同证实：正常初次根/子`ainvoke(dict)`；Gate恢复根`Command(resume=真实interrupt引用)`、原wrapper子`None`；post-gate根/子`None`且execution_mode=reconcile。checkpoint恢复实际先进入原execute_refund，收到当前run的succeeded recovery后进入record_tool_outcome/compose/map_result，退款handler=0；没有把“None会跳过写节点”当保护。

原Task、thread、call、raw/canonical args、digest、operation、approval/subject及namespace逐阶段不变，新run/current context传播至各观测节点；原namespace最终ToolMessage恰一条，ID为`tool:{task_id}:{call_id}`。累计模型/工具/主动时长至少继承waiting快照，旧marker的可能消耗按现有保守上界记入。unexecuted原execute重入走现有再检/准备分支，attempt_id区别于旧标记且run_id为当前run。源码写入屏障和实际barrier失败共同证明未sync不会进退款handler。

每场setup先validate_test_target，再在线核对`agent_demo_test/agent_test`、001～005全checksum及完整schema_migrations行。保存sessions/demo_orders/refund_requests/approvals/schema_migrations全行集及既有Saver线程集合。所有订单、用户、会话、operation/thread均为唯一测试记录，固定五订单及他人数据未修改。

cleanup按本轮唯一用户精确删除审批→申请→Session/订单，并对本轮原Session线程调用Saver.adelete_thread，逐表核对checkpoints/checkpoint_writes/checkpoint_blobs该thread均零行；结束业务全行集、迁移及既有线程集合等于各场前值。负向探针在异常审批上产生的测试改动与失败后补绑定也全部随本轮记录删除，未批量清理或使用seed恢复。没有应用库、迁移、Saver setup、SSH或服务操作；没有秘密/URL/原始连接异常输出。

## 5. D04第15节24项评估

I=本轮独立真实PG/进程证据；Q=已完成六问题独立复测及原外部QA；R=可信Implementer完整164项回归，已按需审查对应测试源码；M=Implementer显式真实模型JSON。PASS表示所列分层证据支持核心行为，不表示每个组合都在本轮重新实测。

| # | 结论及证据边界 |
| --- | --- |
| 1 正常申请/批准/模拟执行 | **PASS**：I-TCP真实PG源表与完全重启；M原生call/真实模型补充 |
| 2 管理拒绝 | **PASS（复用）**：R:test_refund_full_controlled原call拒绝/零handler；真实PG事务拒绝及订单状态见test_refund_transactions；本轮不另重启拒绝分支 |
| 3 GET审批视图 | **部分已验**：R路由八字段、I多场真实详情读取、源码get/list及can_resume为只读；**APPROVED过期视图的八字段完整派生组合及真实GET零SQL写探针未单独实测**，不能把Q的普通用户查询零写等同该管理视图全部通过 |
| 4 过期Resume | **部分已验**：R真实事务锁后DB时钟、PENDING过期提交EXPIRED/未到期拒绝、APPROVED过期阻止新效果；源码Gate派生expired保留APPROVED。**真实过期审批经完整Graph只拒绝闭合的组合未单独实测** |
| 5 Task兼容别名 | **PASS**：R真实004/005约束与准备关联、I跨进程原task/workflow保持；不把DDL字面存在当约束通过 |
| 6 重复决定 | **PASS（复用）**：R真实同决定复用原审核人/时间/期限，过期不续期，相反决定冲突；I完成后的重复resume另证无新执行 |
| 7 未付/已退/他人订单 | **PASS（复用）**：R真实准备/事务资格与订单隔离；Q身份查询；金额来自Domain锁内源表 |
| 8 chat/伪Actor/错主体 | **PASS（既有入口范围）**：R额外Actor字段/环境/回环、Policy/主体及Q撤权；repair异常主体另列007，第10项FAIL |
| 9 真实waiting | **PASS**：I真实Saver approval_gate、唯一interrupt/ns；R/Q普通chat/new_task冲突；中断没有普通结果或结算 |
| 10 中断持久但绑定失败/repair | **FAIL：04-QA-007**。Implementer repair及Q正向幂等可复用，但本轮三异常状态实际200。真实并发repair/响应丢失/历史中断等组合没有完整独立证据，不据正向勾选通过 |
| 11 完全重启 | **PASS**：I-TCP旧PID2560确认退出、新PID43168，仅决定/原引用resume；其余I故障阶段也为不同完整Python进程 |
| 12 审批后再检 | **PASS**：I-unexecuted真实再检/新标记；R真实权限/期限/资格变更及Executor复核；Q撤权；未另做每种变更的全进程排列 |
| 13 原ToolMessage | **PASS**：I成功场原namespace读取同call且稳定消息ID恰一；Q撤权error配对和公共历史隔离；M真实供应商闭环 |
| 14 重复/并发 | **PASS（分层）**：R真实不同operation同订单竞争、同operation重放、相反决定竞争；同决定原记录复用及Runtime单Run由既有测试支持。**两个真实管理HTTP客户端同决定竞争未单独实测** |
| 15 过期/失效 | **PASS（业务许可层）**：R新效果过期拒绝、成功后到期原事实复用，Q安全事实闭合；完整过期Gate组合限制见第4项 |
| 16 SQL成功回应/快照失败 | **PASS**：I-checkpoint next=execute_refund、I-reply next=compose，当前context核对成功，恢复退款handler=0；单aput残留pending writes的未知形态复用Implementer pending，不能强行恢复 |
| 17 未执行/未知核对 | **PASS**：I-unexecuted新attempt/current run/sync后一次实际handler；I-barrier未知409零Run/Graph/handler；Q矛盾及核对失败；未声明PENDING本身足以证明未执行 |
| 18 实际调用/重入守卫 | **PASS**：I invocations/nodes/namespace记录根Command或None、子None与当前recovery；真实原execute节点确实重入 |
| 19 四种Resume | **PASS（分层）**：I真实Gate、post_gate、END200 accepted=false；I-barrier及Implementer pending真实未知拒绝；未知不作为可自动完成保证 |
| 20 执行前/后崩溃 | **PASS（安全点范围）**：I-barrier/未执行/提交后故障及独立进程退出恢复；故障是测试边界异常、TCP是进程终止，不声称真实支付断电或任意Python指令恢复 |
| 21 任务预算 | **PASS**：I累计计数/保守时间与Q耗尽/未知模型窗口；R受控时钟等待不计时及预算继承；没有把崩溃用量称精确观测 |
| 22 中断/结算隔离 | **PASS**：I真实等待/当前context与正常END；R图内run_finish/最终Checkpoint延迟，Q已确认中断不走正常结算 |
| 23 SSE/HTTP断开 | **PASS（复用）**：Q原外部真实TCP恢复Run断开后继续且释放订阅；R初次迭代前解绑/重订阅及初始Run断开；本轮I-TCP证明重启，不另冒称重测断流 |
| 24 业务/技术状态分离 | **PASS**：I-checkpoint/reply读取真实SUCCEEDED且零再次handler，Q普通用户持久事实查询；Implementer pending原业务成功仍可核对，执行不明安全拒绝 |

未将矩阵里的部分组合/源码支持写成新增实测。修复007后，应由主Agent决定补齐上表明确未单独验证的必要组合再作阶段技术裁决；不能用164项数量、一次正常重启或本轮多数PASS覆盖第10项FAIL。

## 6. 交回

本轮只发现合并问题007；原001～006修复结论保留。所有本轮PG数据和子进程均已清理退出，原始实现证据保留。未知框架快照和未sync marker继续409是安全边界，不要求自动恢复。历史凭据/密码复用及六份Markdown格式遗留沿用户决定保留。

报告交主Agent，由原Implementer按确认范围修复后另做独立复测。本QA工作单元完成并停止，不自行修改业务或宣布04通过。
