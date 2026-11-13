# 04 首轮独立 QA 问题修复报告

本记录关联阶段 04、[首轮修复任务](../04-hitl-checkpoint-refund-fix-01.md)、[独立 QA 报告](../../question/04-hitl-checkpoint-refund-qa-report.md)，涉及 Task 4.1.1、4.1.2、4.2.1、4.2.2、4.3.1、4.3.2 的接口与验证边界，问题编号为 04-QA-001～006。实施时 HEAD 为 `50e4c55476e714ed1e6d692511d8d878108c399b`。本报告是修复会话的开发自测，问题状态和阶段验收由主 Agent 与独立 QA 处理。

## 六项修复

| 问题 | 根因及本轮修复 |
| --- | --- |
| 04-QA-001 | 原公共路由缺少任务与退款查询。新增 `POST /agent/tasks/current` 和 `POST /agent/refunds/{application_id}/status`，沿 Route → Service → Runtime/领域服务只读检查已绑定 Session 和主体。当前 Task 读取有效父快照及可核验子中断，空任务返回 null，旧 Run 无活动协程时不显示活动 run_id。退款查询按用户、会话和已绑定 thread 读取申请、审批与模拟结果；其他人或不存在统一返回 404。查询不创建 Session/Task/Run，也不推进 Graph 或审批。 |
| 04-QA-002 | 原恢复将锁后读取的 PENDING 直接视作可继续，忽略快照中已有成功事实。恢复和 `can_resume` 现检查 execution_result、成功工具结果/ToolMessage、outcome 与安全节点位置，矛盾返回 `execution_uncertain`。先核对业务事实与快照，再调用可能处理审批过期的 prepare_resume。PENDING 仅在存在尝试标记且停在其 execute_refund 边界时具备可计量的在途 handler 窗口，其他后段位置保守拒绝继续；确认未执行后仍按预算及原流程重新校验并生成新标记。 |
| 04-QA-003 | 保守累计时长耗尽后 Runtime 原先进入无期限图执行，回复节点仍可调用模型。普通 Run 的主动时长耗尽直接停止，恢复路径使用既有配置的有界收敛期限，Scope 本身不增加预算。回复节点在主动时长耗尽或已成功恢复但无可信尝试窗口时不调用模型，允许确认事实的固定结果映射。无标记的成功恢复将用量标为不完整。 |
| 04-QA-004 | 关闭申请工具被撤权/策略阻止时，原生退款调用未配对便进入 compose。关闭动作仍经 Policy，失败时保留该失败并生成原 call_id 的稳定私有 ToolMessage；结果映射及恢复 compose 也会闭合尚未配对的原调用。已确认成功事实生成成功闭合，未完成使用失败闭合，私有消息不加入公共 SSE。 |
| 04-QA-005 | pytest skip 的 longrepr 原为 tuple，首轮脱敏将其整体转字符串，导致 `-rs` 汇总异常。测试及收集报告对 tuple 内字符串逐项脱敏并保留 tuple 和行号类型，原有异常、捕获及 warnings 处理继续使用。 |
| 04-QA-006 | 同 Executor 的可选准备/执行 context 原来总被拒绝。新增固定 `prepare_memory_write → execute_memory_write` 准备配对及执行节点同节点只核对配对。仅允许 KNOWLEDGE/MEMORY_MANAGE 的 node-origin `write_preferences`，目标 Policy 再检 scope、工具版本、规范参数及预算。准备标记绑定线程、RunScope、限制、scope 摘要、原调用摘要和最小业务快照；真正执行再核对当前关联并经同一 Policy/Executor，直接 execute 与 batch 不能绕过准备。`ToolExecutionContext.thread_id` 为节点调用的可信线程关联，调用方需显式提供。未注册或实现 MemoryManager、Store、RAG。 |

## 修改文件

| 文件 | 职责 |
| --- | --- |
| `app/api/routes/agent.py`、`app/services/agent_service.py`、`app/runtime/agent_runtime.py`、`app/domain/refunds.py` | 两个只读查询、持久主体与恢复受理核对 |
| `app/graph/specialists/refund/builder.py`、`app/runtime/context.py`、`app/runtime/run_scope.py` | 原调用闭合、保守预算/结果复用和本 Run Scope 关联 |
| `app/tools/models.py`、`app/tools/policy.py`、`app/tools/executor.py` | 同 Executor 固定节点准备/执行契约和必要可信上下文 |
| `scripts/pytest_redaction.py` | 保留 skip tuple 并脱敏 |
| `tests/test_refund_executor.py`、`tests/test_refund_preparation.py`、`tests/test_refund_full_controlled.py`、`tests/test_pytest_redaction.py` | 定向行为回归及受控服务的只读查询接口 |
| `docs/resume/README.md`、`README.md`、本报告 | 修复任务及报告导航和交接 |

原仓库外 QA 文件及其断言未修改。工作区原有修改、冻结设计、历史报告、主 Agent 协调文档及指定暂缓文件保留。未改依赖、用户密码、认证配置、已应用迁移、基础设施或应用库，未调用其他会话或 Commit/Push。

## 实际开发自测

均使用项目 `.venv`，pytest 保留默认 fd 捕获和脱敏插件。

| 入口 | 结果 |
| --- | --- |
| `python -m pytest -q tests/test_refund_executor.py tests/test_refund_checkpoint.py tests/test_refund_full_controlled.py tests/test_approval_routes.py tests/test_runtime.py tests/test_runtime_http.py` | 最终 **37 passed**，0 failed，0 skipped。包括固定节点同 Executor 准备/执行、错误线程/Run/scope/参数/业务主体拒绝、直接执行及 batch 拒绝、已消费标记拒绝和同节点只核对模式。 |
| 上述相关测试加工具治理及 pytest 脱敏，使用 `-q -rs` | 收敛期间 **60 passed**，0 failed，0 skipped；之后收紧了恢复节点/查询状态校验，并执行表中最终 37 项及外部 11 项回归。skip 独立子进程合成测试覆盖测试阶段和收集阶段，保留正常汇总并隐藏虚构数据库凭据。 |
| `python -m pytest -c pyproject.toml -q C:/Users/15294/AppData/Local/Temp/agent04-qa-20261112/test_review04.py --tb=short` | 最终 **11 passed**，0 failed，0 skipped。执行对象是原仓库外 QA 文件，原断言保留。此为修复会话重跑，不等同后续独立 QA。 |
| 真实专用测试库 harness 内运行 `pytest.main(['-q', '-rs', 'tests/test_refund_preparation.py', 'tests/test_refund_transactions.py', 'tests/test_approval_constraints.py'])` | **3 passed**，0 failed，0 skipped；使用真实 PG 和唯一测试数据。 |
| 定向 `ruff check` 和 `ruff format --check` | 修改涉及的 15 个 Python 文件 lint 通过，format 检查 15 files already formatted。 |

实施中曾先运行原始 11 场景，当时查询接口尚未接入，结果为 9 passed、2 failed，两个失败对应查询路径缺失。补齐接口及后续安全收敛后，最终重跑为上表 11 passed。受控退款图使用真实编译 Graph、Runtime、Policy 和 Executor，业务数据库和模型以测试服务替代，其 effect_count 不作为真实 SQL 提交次数。

## 真实数据库和清理

真实库测试通过 PowerShell here-string 管道执行项目解释器内的安全 harness。连接前从 `Settings` 取得测试配置，调用 `validate_test_target` 与应用配置进行目标隔离检查。只读预检断言 `current_database/current_user` 为 `agent_demo_test/agent_test`，schema 版本为 1～5，登记 checksum 与仓库文件一致，并保存 `demo_orders`、`sessions`、`refund_requests`、`approvals` 全行集及 Saver 三张表的行数。

测试使用各用例唯一用户、订单、会话和操作。准备及事务用例按外键顺序精确清理自己的数据，约束用例事务回滚。测试前后四个业务表全行集及迁移摘要一致，固定订单共 5 条。Saver 的 checkpoints、checkpoint_writes、checkpoint_blobs 行数前后一致，本轮真实库用例未创建 Saver 线程，故无本轮线程需删除。未调用 seed、迁移、应用库或基础设施操作。配置和异常只输出固定摘要或错误类别，没有输出 URL、密码或原始连接异常。

## 交接与剩余门禁

PENDING 且未停在带标记 execute_refund 边界的恢复采用保守拒绝。已成功但无法以该标记可靠界定窗口的恢复只允许事实复用与安全闭合，不发新模型或写操作，其中包括已进入 compose 的未知模型调用窗口。固定节点接口提供业务上下文数据契约，后续 Memory 实现仍须按冻结 D05 构造可信 context、设置线程、实现同步边界及只核对语义。

本轮未执行完整真实库回归、付费真实模型、退款业务全进程重启、真实 SQL 与 Checkpoint 故障窗口的完整 4.3.2 门禁。原独立 QA 的受控 Graph 证据不等于这些真实资源验收。用户决定保留的凭据暴露/复用及 P3-01 文档格式遗留沿原记录追踪。完成本轮后等待主 Agent 审核及独立复测，不自行关闭问题或宣告阶段验收。
