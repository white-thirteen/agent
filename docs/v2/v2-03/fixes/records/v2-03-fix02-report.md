# V2 03 fix02 定向修复记录

2026-11-20。关联 [fix02任务](../v2-03-fix02.md)与[首轮复测](../../qa/v2-03-fix01-retest-report.md)。本记录是实施自测，原 QA-001～008 均由独立 QA 后续裁决，不声明 VERIFIED 或 ACCEPTED。

## 实现

- QA-007：`app/tools/selector.py` 在任何首次/重新发现持久写之前固定 Selector 配置总期限，并按当前 Run 时间扣除可信的后续业务模型和处理余量；`app/runtime/model_gateway.py` 在每次实际 provider 调用及重试前、持久预留之后重新核对绝对期限与 Scope 余量。已持久但未调用 provider 的尝试保留次数，`selector_called` 和回执不误称已发起。受控多候选 Node 从候选工具的既有 timeout 和 max_retries 推导一个工具的处理余量；没有新增任意秒数或配置。
- QA-008：`app/runtime/run_scope.py` 将 Selector 逻辑调用回执与业务 `context_view` 分开，保存 Task/Run、UUID、实际 provider 次数、已预留次数、状态及 known/unknown 用量，不保存原始需求或模型消息。`selection_reservation.py` 在现有 Task Saver namespace 中先保存 pending_unknown，成功或失败后更新；主/子图字段和 Runtime 在完成、澄清、新 Run 与审批恢复间显式传递，并按已提交 ID 去重。调用中断而尚未完成回执时，provider次数和用量为未知，不由预留推断。旧 Checkpoint 缺字段按空值读取。内部字段不进入公开 facts 或 SSE。
- 默认回归发现的退款测试问题：`tests/test_refund_checkpoint.py` 的三个固定快照 Graph 替身原先没有 Saver 读取契约，导致 Runtime 在进入 Graph 前失败；为其提供对应已提交快照的受控 Saver 替身，不修改生产 fail-closed 或原断言。duplicate-resume 测试的事件等待现有2秒上界，并在任务提前结束时显示错误，避免无限挂起。

## 实际验证

均使用项目 `.venv`，本单元未写 PostgreSQL、未调用真实模型。

- `python -m pytest tests/test_tool_progressive_disclosure.py tests/test_runtime.py tests/test_order_graph.py tests/test_refund_full_controlled.py tests/test_refund_checkpoint.py tests/test_graph_protocol.py tests/test_context_contracts.py tests/test_context_builder.py -q --tb=short`：**121 passed**，原始 `evidence/v2-03-fix02-final-controlled.txt`。包含首次/重发现慢写、逐次写、重试、B>1、配置总期限、处理余量、业务可调用、成功/失败与重试 unknown 回执、父子映射、新 Run 去重、旧记录、公开事件过滤、退款恢复。LangGraph依赖一条弃用警告。
- Ruff 首次发现 duplicate-resume 失败分支漏导入 pytest（仅失败诊断分支；原始 `v2-03-fix02-ruff.txt` 保留）；补导入后 `python -m pytest tests/test_refund_checkpoint.py -q --tb=short`：**10 passed**，`v2-03-fix02-refund-final.txt`；受影响15个代码和测试文件 `python -m ruff check ...` **All checks passed**，`v2-03-fix02-ruff-retry.txt`；format检查15文件通过，`v2-03-fix02-format.txt`。
- 更早两项退款失败的原始复现 `v2-03-fix02-refund-before.txt`、三项修复后 `v2-03-fix02-refund-retest.txt` 保留。期限定向的初次测试缺导入失败及复测分别保存在 `v2-03-fix02-deadline.txt`、`v2-03-fix02-deadline-retry.txt`；最新慢重新发现期限证据 `v2-03-fix02-rediscovery-deadline.txt`。回执定向见 `v2-03-fix02-receipts-final.txt`、`v2-03-fix02-new-run.txt`；中断时 pending_unknown 由 InMemorySaver 受控用例验证。

## 尚待独立验证

上述 Saver/进程中断用例仅是本单元内存受控证据，不能替代真实隔离PG或进程级复测；未重新运行付费模型。新版本的真实 Saver/PG、退款恢复、固定五题与两条无损模型链路、完整默认门禁及数据库前后保护由主 Agent 安排原独立 QA/后续门禁。既有真实模型中文捕获转码缺口继续保留，不用本轮构造数据回填。未修改冻结设计、.env、正式库或角色配置，未提交或推送 Git。
