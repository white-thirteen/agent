# 04-QA-007独立复测及矩阵缺口闭环

日期：2026-11-13；HEAD：`50e4c55476e714ed1e6d692511d8d878108c399b`，包括工作区既有未提交实现。依据[修复任务](../resume/04-hitl-checkpoint-refund-fix-02.md)、[开发修复报告](../resume/record/04-hitl-checkpoint-refund-fix-02-report.md)及冻结D04第9.6节，对[阶段QA](04-hitl-checkpoint-refund-restart-qa-report.md)中的007和矩阵#3/#4/#10/#14独立复测。

**本工作单元PASS。** 原007的A/B/C均按原外部脚本及正确409断言通过；四项矩阵缺口获得本轮独立真实PG证据，正常repair跨进程原调用恢复通过。未发现新增阻塞，建议主Agent复核关闭007，并结合既有阶段证据作技术验收。本报告不代替主Agent技术裁决、用户正式验收、Git归档或阶段转换。

## 1. 独立性与实际范围

执行前保存app/tests/scripts/migrations非缓存文件、全部既有docs、AGENTS/README、原`repair_negative.py`及原外部`test_review04.py`的SHA256，共213文件。结束核对**213个均相同，0变化**。仓库只新增本报告；未改业务/现有测试、原正确断言、已有证据或冻结设计，没有Commit/Push、Bridge/其他会话/子Agent、基础设施、迁移、seed、换密或05操作。

独立目录R：`C:/Users/15294/AppData/Local/Temp/agent04-fix02-qa-20261113-133504`。所有新输出位于R，原阶段JSON及上轮失败证据保留。清单为R/protected-before.json及protected-after.json。

本轮不重做001～006，也不重跑无新影响的完整TCP重启/故障全排列或付费模型。开发方最终165 passed/0 skipped、Ruff及此前真实模型证据按其来源复用，**不算本轮独立执行**。本轮实际新增实测如下。

## 2. 实际命令及结果

P=`D:/py/agent-project/agent/.venv/Scripts/python.exe`，Q=`C:/Users/15294/AppData/Local/Temp/agent04-restart-qa-20261113-131121`。cwd=R，PYTHONPATH=`D:/py/agent-project/agent`，项目Windows selector runner处理PG；串行执行，没有数据库并发测试单元互相干扰。

| 实际入口 | 结果 |
| --- | --- |
| `P Q/repair_negative.py` | **exit0**。原A/B均HTTP409、`approval_binding_conflict`、new_runs=0、业务全行集不变；两场精确清理通过 |
| `P Q/repair_negative.py --cas-only` | **exit0**。原C为HTTP409、相同安全错误、new_runs=0；精确清理通过。原`business_rowsets_unchanged=false`保留，原因是测试边界主动修改摘要，不能将它写成true |
| `P R/run_targeted.py` | **2 passed，0 failed，0 skipped，10.21s，exit0**。内层实际为`pytest.main(['-c', ROOT/pyproject.toml, '-q', '-rs', '--tb=short', ROOT/tests/test_refund_repair_postgres.py, ROOT/tests/test_refund_checkpoint.py+'::test_repair_binding_is_idempotent_and_never_starts_graph_execution'])`。两条已导入anyio/langsmith的assert-rewrite提示，无功能失败 |
| `P -m scripts.verify_04_restart --mode repair` | **PASS，exit0**。正式拓扑/真实PG，wait PID35892退出后resume PID41076；handler次数0/1，真实首次补绑/重复幂等后原task/call/args/operation/namespace恢复，原ToolMessage恰一，精确清理通过 |

R/run_targeted.py在进程内从Settings显式设置现有`AGENT_TEST_DATABASE_URL`，没有把URL写入命令或输出；保留pytest默认fd捕获及脱敏插件。外层另存真实DB前后完整快照并比较，不仅依赖测试自己的finally。新增PG测试中包含多个必要场景，2 passed表示两个pytest测试，不把其中场景机械换算为新增测试数量。

R中保留`repair-negative-evidence.json`、`repair-cas-negative-evidence.json`、`targeted-evidence.json`、`pg-before.json`、`pg-after.json`和`docs/04-restart-evidence-repair.json`。原Q脚本按其原绝对路径直接运行，没有复制修改断言；相对manifest/JSON写入R。没有出现本轮产品断言失败或skip。

## 3. 007逐子项与修复复核

| 子项 | 结论与证据 |
| --- | --- |
| A 已决定且三绑定全空 | **PASS**：原真实PG异常行复现现在409，原审批不被补绑，零新Run/Graph；源码明确空绑定仅PENDING。异常状态来自测试注入，不声称正常decision能创建此状态 |
| B 原审计Checkpoint不存在 | **PASS**：原脚本先确认该thread下引用不存在，repair现在409且原行不变。新增PG测试还取同namespace真实存在的历史非Gate审计，替换仅本轮引用后409、全行集不变 |
| C Runtime后、CAS前主体摘要变化 | **PASS**：原外部摘要变更探针现在409且零新Run/Graph；审批锁内`_check_subject`及期望摘要比较位于UPDATE之前。新增真实PG测试进一步将CAS前决定改为APPROVED，409并实际查询三绑定仍为NULL，Run集合不增 |
| 正常首次/重复repair | **PASS**：丢响应后重试幂等、TCP并发单次补绑、正常跨进程原调用通过。latest Gate ID与原audit ID不同仍幂等的既有定向用例独立通过；该ID差异用例为受控StateSnapshot，未冒称另在真实库构造新快照 |

源码审查结果：

- [Runtime精确审计读取](../../app/runtime/agent_runtime.py:137)显式传原thread/namespace/checkpoint_id，核对返回ID；在已校验当前root下重新分类原审计child。缺失、历史非Gate或不匹配不会用latest替代。
- [repair受理](../../app/runtime/agent_runtime.py:215)先验证latest唯一pending；已绑定再核对audit，空绑定要求PENDING。保留原audit ID，避免错误要求latest ID必须与其相同。
- [事务内再检](../../app/workflows/approvals.py:149)先锁审批，调用[主体/session/参数摘要检查](../../app/workflows/approvals.py:309)，再比对期望digest/decision；只有通过后才处理空绑定PENDING写入或同绑定复用。状态/主体变化在UPDATE之前拒绝。
- [InterruptBindingRequest](../../app/workflows/approvals.py:35)只承载本次CAS期望。两个生产bind调用方——[显式repair](../../app/runtime/agent_runtime.py:224)和[自动暂停绑定](../../app/runtime/agent_runtime.py:902)——均完整传递已核验主体/决定。全仓调用点检索没有遗漏生产调用方。
- 退款Gate仍构造[三字段InterruptBinding](../../app/graph/specialists/refund/builder.py:321)，Executor的binding_snapshot比较契约未扩成Request；本轮正常repair后的真实原调用执行进一步验证接口兼容。未增加Serializer类型或其他授权标记。

## 4. 原24矩阵明确缺口闭环

其他20项复用[上一轮阶段QA](04-hitl-checkpoint-refund-restart-qa-report.md)及[001～006复测](04-hitl-checkpoint-refund-fix-01-regression-report.md)，本报告只更新以下四项的新增证据。

| 原矩阵项 | 本轮结论及真实证据 |
| --- | --- |
| #3 过期APPROVED的GET完整视图/零写 | **PASS**。新增PG测试在真实批准后仅将自身审批按30分钟关系置过期。列表/详情完整八字段相同；decision仍APPROVED、validity=expired、bound、can_decide=false、can_resume=true。真实AsyncCursor.execute只允许SELECT，同时禁止Graph.ainvoke及Saver.aput，GET均成功；前后完整业务/迁移/Saver线程相同。原来仅源码/部分路由证据的缺口已补 |
| #4 过期审批经完整Graph拒绝闭合 | **PASS**。上述真实审批由正式HTTP resume、真实Gate及原完整Graph推进；Task=rejected、申请REJECTED、订单未退款，原call恰一个error ToolMessage。真实退款execute_original为失败探针且未触发；APPROVED审核人/时间/期限整行不变，没有改写人工决定或续期 |
| #10 repair异常、响应丢失、并发与幂等 | **PASS**。原007 A/B/C皆409。真实绑定事务完成后测试transport丢弃响应、抛ReadError，重试200 repaired=false且原行/Run集合不变。两个真实loopback TCP HTTP客户端并发repair，恰一repaired=true，另一个幂等200或thread忙409；随后重试false，零新Run/Graph/退款。已过期PENDING可补原绑定但不决定/续期；历史非Gate审计、错摘要、CAS前决定变化均409，错误路径不新增绑定 |
| #14 两个真实HTTP客户端同决定竞争 | **PASS**。两个独立loopback TCP客户端向正式应用并发提交同一决定，均200且完整响应相同，复用原审核人/时间/期限；Run集合不变，没有自动执行退款。其他不同operation/相反决定竞争继续复用可信真实事务回归 |

上述证据实际执行的是仓库新增[test_refund_repair_postgres.py](../../tests/test_refund_repair_postgres.py:31)，已独立审查其核心边界：丢响应在真实handler完成之后；历史审计来自真实Saver历史；TCP客户端各自建立HTTP连接；GET探针没有Mock数据库读或can_resume；过期恢复使用正式Graph与真实仓储，只有模型和必须零调用的退款handler采用受控替代。

## 5. 数据保护及限制

所有真实入口均先validate_test_target，在线确认`agent_demo_test/agent_test`，核对001～005本地迁移SHA256与数据库登记checksum；保存sessions/demo_orders/refund_requests/approvals/schema_migrations全行集和既有Saver线程集合。本轮全部使用唯一用户/订单/会话/操作，不seed、不修改固定五订单或应用库。

原A/B/C和正常repair每场cleanup均通过；新增PG测试finally按自有用户精确删除审批→申请→Session/订单，从自有Session补发现线程，对每个自有thread调用Saver.adelete_thread，逐表断言checkpoints/checkpoint_writes/checkpoint_blobs该thread零行。所有子进程、TCP server/client/socket均退出关闭。R/run_targeted.py外层再次确认完整业务/迁移/Saver线程前后相同，`targeted-evidence.json`保存exit0与保护结果；没有清理他人数据或输出原始连接异常。

真实层区分：数据库、事务、Graph、仓储、Saver与指定TCP并发为真实；模型是受控替身。响应丢失由ASGITransport在提交后抛错，不声称真实网络断电；TCP并发复用已正式初始化的同一应用生命周期，不声称额外完整进程重启。正常repair另有本轮不同Python进程证据；其他真实重启/Checkpoint故障及真实模型沿已有可信记录，不重复付费。

未发现本轮实质遗留或需新增修复的问题。未知Saver快照/无可信同步窗口继续安全409，多实例互斥、任意Python崩溃恢复及全局Exactly Once仍不在04保证内；历史凭据/密码复用和六份Markdown格式遗留按既有决定保留。本工作单元完成并停止，交主Agent复核。
