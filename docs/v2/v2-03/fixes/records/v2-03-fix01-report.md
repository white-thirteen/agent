# V2 03 首轮 QA 定向修复记录

日期：2026-11-20。关联 [fix01任务](../v2-03-fix01.md)、[首轮FAIL](../../qa/v2-03-initial-qa-report.md) 和 [004主裁决](../../v2-03-main-decision-001.md)。本记录是实现自测交付，不是独立QA或阶段验收。首轮FAIL和本轮失败原始输出均保留。

## 修改及边界

- QA-001：`app/runtime/agent_runtime.py`、`app/context/compaction.py` 在运行内压缩前为当前业务调用及该调用之外的保留次数留出尝试和配置期限；摘要截止时间不随归档工作延后。零额外调用的不足检查覆盖 B=1、B=2 与期限不足；真实 Runtime compactor / Gateway、受控摘要模型验证摘要之后两次业务调用可用。实际生产节点当前声明B=1，B=2为受控已知需求验证。
- QA-002：`app/tools/selector.py` 无记录且pending/审批或unknown时不选择；有记录的锁定路径继续原关联。HEAD旧Refund builder生成的隔离Saver审批样本、关闭旧Runtime并重建当前Runtime后，选择记录缺失、Selector零调用，原call_id/operation_id/工具版本/参数/审批主体不变，正式Policy重新检查、重复resume后受控副作用1次。此为同进程Runtime重建、真实Saver和受控业务服务，不是旧生产Checkpoint，也不冒充跨进程旧审批恢复。
- QA-003：Selector在重新发现发起时递增计数，失败结果携带记录；Order、Knowledge、Refund失败分支返回记录及已用量。Selector失败的已知或unknown用量回执写入内部context_view；timeout用例验证unknown/null、失败次数和重发现计数保留、再试拒绝。异常进程持久下限见004。
- QA-004：`app/runtime/selection_reservation.py` 使用现有Saver公共接口和同thread的Task专属namespace，调用前预留已消费尝试及重发现，持有未决标记和结果摘要；`run_scope.py`、`model_gateway.py`、Runtime及现有节点负责接线。Runtime确认读取Saver实际完整channel_values，不把pending writes当作节点完成；正常结果需匹配Task、Run、摘要和用量，审批暂停基于原审批分类的真实child checkpoint确认；原退款reconcile只允许已验证原选择关联并保持单调下限。已有会话互斥保留。真实隔离Saver测试覆盖节点异常、结果已提交后的新读取确认、ToolSelector重发现后子进程强退和同Task新Run复用后业务调用强退；均使用唯一thread及公共API清理。该机制尚待独立QA复核，不能宣称覆盖所有故障与并发。
- QA-005：`app/graph/specialists/order/builder.py` 将新record和派生selected_tools与实际binding一并写回，包括业务模型失败路径；Order和Refund需求摘要包含已验证目标范围，仍由原参数约束和Policy校验。受控Order图验证同文本/相同范围仅改变上下文历史复用，同文本变更已验证order_id触发一次重新发现。单候选且允许no_tool也走单候选短路。
- QA-006：`tests/manual_v203_real_model.py` 是非默认收集、显式付费opt-in入口，隔离端点和在线数据库身份双重核验；唯一用户三订单和另一用户订单、真实Policy/Executor、参数约束、单单与分页SQL对照、配对ToolMessage、finally精确删除。显式窗口/输出为16384/512，不改.env；测试观察器仅记录实际调用，不替换核心。默认测试不启用付费。冻结五题读取独立fixture；实际候选、绑定、决策、调用、用量和清理保存在原始输出。

## 实际验证

- 项目 `.venv`：`python -m pytest tests/test_tool_progressive_disclosure.py tests/test_runtime.py tests/test_order_graph.py tests/test_refund_full_controlled.py tests/test_context_contracts.py tests/test_context_builder.py -q`，58 passed，见 `evidence/v2-03-fix01-final-regression.txt`。其后仅新增存储故障定向测试，单模块20 passed，见 `v2-03-fix01-storage-guard.txt`。Ruff受影响文件通过，见 `v2-03-fix01-ruff.txt`。LangGraph依赖产生一条弃用警告。
- 专用Linux隔离PG：`python docs/v2/v2-02/evidence/linux-pg-launcher.py pytest tests/test_context_run_compaction_postgres.py tests/test_refund_context_checkpoint_postgres.py -q`，2 passed，`v2-03-fix01-pg-final.txt`；运行内压缩模型及退款业务均为受控替身。guard核验PG17.12、数据库/角色/comment。Saver独立探针见 `v2-03-fix01-{confirm-probe-retry,selector-kill-probe,reuse-kill-probe,legacy-refund-probe-repeat}.txt`。
- 一次实际付费手动组：`AGENT_RUN_REAL_MODEL_TESTS=1`，launcher `pytest tests/manual_v203_real_model.py --capture=fd -rP -q`，2 passed，`v2-03-fix01-manual-real-guarded.txt`。五题各一次，合法及语义各5/5，provider已知2466 tokens；单单/列表各一Selector和一业务调用，真实SQL对照1行/分页2行、外用户排除，清理剩余0，已知1874 tokens。合计9次、4340已知tokens、无EOF。本次 captured stdout 经PowerShell转码中文出现U+FFFD：fixture本身UTF-8及hash未变，源码直接读取该fixture并传入Selector，但损坏输出不能单独证明该次线路中文原文字节；不以fixture文字补写冒充捕获。ASCII名称、计数、用量及SQL结果可核对。此后手动入口改用ASCII转义，无新增真实调用。
- 成本对照：受控模型执行HEAD旧Order图和当前正式Order图，均两次业务调用、两次绑定均各一个get_order、Selector零调用；未观察到此固定生产场景收益。见 `v2-03-fix01-cost-baseline-retry.txt`。真实多候选增加的Selector各一次，与业务调用分开报告，不虚构全目录收益。

## 未闭环与失败保留

首个手动 `-s` 命令被项目凭据保护在收集前拒绝，零模型调用，原始 `v2-03-fix01-manual-real.txt` 保留。隔离通道曾在写入前只读guard阶段断开，`v2-03-fix01-confirm-probe.txt` 保留，恢复后复测结果另存。实施中受控退款出现3项失败、一次仍有1项失败，分别见 `v2-03-fix01-controlled-reuse.txt`、`v2-03-fix01-refund-retest2.txt`；按原调用恢复修复后四项通过见 `v2-03-fix01-refund-retest3.txt`。B=2测试替身缺bind的首次失败和修复输出独立保存。另一次组合测试手工中断，不计通过。

本单元未执行完整阶段回归、独立QA或主Agent最终复核；未做跨进程旧审批Runtime恢复。真实模型捕获的中文转码缺口由主Agent裁决是否需要新增有验证价值的复验。运行内选择成功后其他异常时的所有恢复组合、数据隔离水位/全库快照和最终门禁仍须独立复测，以上结果不构成VERIFIED/ACCEPTED。未改正式数据库、.env、冻结设计、角色配置，未提交或推送Git。
