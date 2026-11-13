# 04-QA-001～006 首轮修复独立复测报告

日期：2026-11-13。基线 HEAD：`50e4c55476e714ed1e6d692511d8d878108c399b`，测试对象包括工作区既有未提交实现。本单元仅复测[首轮修复任务](../resume/04-hitl-checkpoint-refund-fix-01.md)及[开发修复报告](../resume/record/04-hitl-checkpoint-refund-fix-01-report.md)，关联[原独立 QA](04-hitl-checkpoint-refund-qa-report.md)，不是04阶段验收。

结论：**04-QA-001～006在本单元范围均PASS**，未发现需追加修复的产品问题。主Agent仍需复核问题关闭及后续阶段门禁；本报告不将04标为VERIFIED或ACCEPTED。

## 1. 独立性与执行边界

本角色通过原生子Agent工具派发，未声称加载项目自定义implementer/qa配置。先读根AGENTS、修复任务/报告及原QA，按需定向核对D03第5.1、D04第5.2/6.4/9.4及D05固定节点/业务上下文契约，没有通读历史或重新设计。

执行前保存app、tests、scripts、migrations全部非缓存文件及原外部`test_review04.py`的SHA256清单，共124文件；执行后全部一致。清单在`C:/Users/15294/AppData/Local/Temp/agent04-regression-20261113/protected-before.json`和`protected-after.json`。没有修改业务代码、既有测试、原外部QA断言或历史证据；仓库只新增本报告。没有Git提交、Bridge/其他会话调用、基础设施变更、依赖变更或05开发。

本单元无需再连接真实PG：六项修复风险用实际编译图、当前Runtime/Policy/Executor及受控模型、领域服务、Session、InMemorySaver验证，SQL只读路径另作源码核对。**本轮未再测真实PG**，不将开发方真实库3项证据算作本轮独立实测；无SQL写入、真实Saver数据或待清理数据库行，未执行seed/迁移/应用库访问或付费模型。

## 2. 实际命令与结果

解释器均为工作区`.venv/Scripts/python.exe`；pytest使用默认fd捕获及既有脱敏插件。R=`C:/Users/15294/AppData/Local/Temp/agent04-regression-20261113`，Q=`C:/Users/15294/AppData/Local/Temp/agent04-qa-20261112`，下表路径缩写仅用于阅读。

| 实际入口（展开R/Q后为绝对路径） | 结果 |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q Q/test_review04.py --tb=short -rs` | **11 passed in 15.42s**，exit0；原外部文件及断言保持不变 |
| `.\.venv\Scripts\python.exe -m pytest -q -rs tests/test_refund_executor.py tests/test_pytest_redaction.py -k 'fixed_node or skip_summary'` | **3 passed, 11 deselected in 5.06s**，exit0；含既有退款node范围、固定Memory接口准备/执行及真实pytest子进程skip/collect脱敏汇总 |
| `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q -rs R/test_regression04.py --tb=short` | **4 passed, 1 failed in 12.20s**，exit1；失败为本轮新增测试误用顶层`code`读取公共错误响应，已实际获得409后发生KeyError；见下行纠正 |
| 同上加`-k pending_contradiction` | 按现有`error.code`响应契约修正新增临时测试后，**1 passed, 4 deselected in 8.91s**，exit0；其余4项未变，不重复运行 |

共有19个不同场景取得通过证据（原11、仓库定向3、新增外部5），不声称最后将全部用例一次重跑。新增外部文件只在R中，未覆盖Q。测试用例数量不是阶段验收依据。没有重复开发方完整回归，也未为纯报告运行业务全量、lint或依赖检查。

## 3. 逐问题结论

| 问题 | 结论与独立证据 | 当前源码证据 |
| --- | --- | --- |
| 04-QA-001 | **PASS**。原查询两项200。新增current/refund参数化用例验证同owner查询、其他允许演示用户/不存在会话404、不存在申请404、旧Run无活动run_id；查询前后Session绑定/新建计数、Run集合、模型次数、审批/申请/业务事实及Saver存储相同；将get_or_create、Saver.aput及审批/关闭写方法替换为失败探针后仍通过。 | [路由](../../app/api/routes/agent.py:57)、[只读Session查找](../../app/services/agent_service.py:64)、[父快照身份核对](../../app/runtime/agent_runtime.py:1086)、[current](../../app/runtime/agent_runtime.py:1108)、[refund](../../app/runtime/agent_runtime.py:1212)、[领域仅SELECT且限制user/conversation](../../app/domain/refunds.py:131) |
| 04-QA-002 | **PASS**。原成功快照/PENDING矛盾用例409且零新模型。新增用例进一步确认`error.code=execution_uncertain`、Run集合不增、Saver及审批/业务状态完全相同，审批prepare_resume/退款执行/关闭/Saver.aput失败探针均未触发。正常repair/END及严格Serializer原execute节点成功复用仍通过。 | [矛盾识别](../../app/runtime/agent_runtime.py:51)、[PENDING节点/标记及预算检查](../../app/runtime/agent_runtime.py:394)、[审批准备在核对之后](../../app/runtime/agent_runtime.py:434)、[新Run生成更晚](../../app/runtime/agent_runtime.py:454) |
| 04-QA-003 | **PASS**。原降低限额与同一0.5秒限额的保守耗尽用例均阻止新模型且effect_count仍1。新增compose失败后按同30秒配置恢复场景，仍有正剩余时间但窗口无法可靠界定，usage_complete=false、零新模型/退款/关闭，Task完成且本人查询保留SUCCEEDED事实。事实闭合没有创造新预算。 | [恢复窗口约束](../../app/runtime/agent_runtime.py:420)、[普通耗尽停止及有界收敛](../../app/runtime/agent_runtime.py:773)、[compose预算/allow_model门禁](../../app/graph/specialists/refund/builder.py:522)、[固定事实结果与调用闭合](../../app/graph/specialists/refund/builder.py:582)、[工具执行预算](../../app/tools/policy.py:87) |
| 04-QA-004 | **PASS**。原撤权用例发往compose的消息已含原call_id ToolMessage。新增撤权探针确认退款handler及关闭申请handler均未进入，effect_count=0；发往模型的原call闭合恰好一个且status=error。权限失败与消息闭合分离，未绕过Policy关闭业务申请。 | [关闭仍经invoke_node且独立闭合](../../app/graph/specialists/refund/builder.py:492)、[compose缺失闭合补齐](../../app/graph/specialists/refund/builder.py:531)、[map_result安全闭合](../../app/graph/specialists/refund/builder.py:640) |
| 04-QA-005 | **PASS**。原synthetic tuple断言通过；既有定向用例启动实际pytest子进程，含测试阶段skip及模块收集skip，`-rs`正常exit0并保留1 passed/2 skipped汇总，虚构密码/URL均被隐藏。未使用真实凭据探测。 | [tuple按元素脱敏](../../scripts/pytest_redaction.py:46)、[测试报告](../../scripts/pytest_redaction.py:70)、[收集报告](../../scripts/pytest_redaction.py:77) |
| 04-QA-006 | **PASS**。既有定向固定节点测试覆盖错误线程/Run/scope/参数/业务user拒绝，准备零handler/零工具次数，直接execute/batch拒绝，执行前错线程/scope/node拒绝；正确准备执行一次、已消费标记拒绝，执行节点同节点replay_check_only核对路径成立。源码进一步核对同ExecutionContext/RunScope/limits、scope摘要、call摘要、业务快照、版本与当前Policy复核。未实现或调用真实Memory。 | [固定准备及context绑定](../../app/tools/executor.py:185)、[标记业务/绑定快照](../../app/tools/executor.py:254)、[最终再检及同Policy执行](../../app/tools/executor.py:368)、[固定执行白名单](../../app/tools/policy.py:67)、[普通入口禁止绕过准备](../../app/tools/executor.py:536) |

## 4. 证据限制与未验证门禁

本轮领域effect_count是受控handler次数，不是SQL提交次数；查询零写证据为受控写入口失败探针、内存状态比较和生产SELECT源码检查，不声称实测真实PG零写。原外部11项包含真实本机TCP断订阅继续运行、严格序列化与同步标记保存失败，但Saver仍是内存，实现了针对缺陷的行为复测，不能替代数据库持久性门禁。

新增测试初次错误仅为临时用例错误响应层级，按`app/main.py:177`现有公共封装纠正；没有改变产品预期或原QA断言。原非严格内存Saver部分场景产生框架未登记类型警告；严格Serializer场景通过，本轮未更改序列化配置，未据此扩展新问题。

**4.3.2完整重启/故障/真实模型仍未验证**：真实PG身份/001～005在线checksum与数据保护应在后续真实库单元重新核对；退款完整Python进程退出后恢复、真实SQL/Checkpoint故障安全后段、真实模型原调用协议及D04全部24项综合门禁不在本报告完成范围。开发方报告的PG通过证据只作为其记录保留。历史凭据/密码复用及P3-01按用户既有决定保留，本轮无新增凭据输出或换密。

本单元完成后交主Agent复核并停止，不自行进入4.3.2或05。
