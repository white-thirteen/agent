# V2 03 接管首轮独立 QA

日期：2026-11-20。结论：**FAIL / REQUIRES_FIX**。这是首轮技术检查，不是阶段验收。审查基线 HEAD `1f3d73643af84fdc55f7f314d6c0db6f0c34560a`，工作区为 Gemini 接管改动，冻结设计及 `evidence/v2-03-takeover-baseline.json` 位于本目录。根规范及 `.codex/config.toml`、`.codex/agents/qa.toml` 已读；配置均为 Terra/high，实际运行元数据由主 Agent 核验。未修改业务代码或原测试，未运行 PostgreSQL 或真实模型。EOF 的根因本轮未确定，不能归因于代码或环境。

## 六 Task 初步状态

| Task | 结论 | 证据和缺口 |
| --- | --- | --- |
| 3.1.1 | BLOCKED | brief 从元数据读取，冻结时缓存 schema 与目录摘要；已有受控测试通过。未完成冻结版本变化及完整回归，不作为 VERIFIED。 |
| 3.1.2 | BLOCKED | PurposeSpec 与 discoverable/scopes/agent/task 三层过滤，生产四用途各一个工具；受控测试覆盖内部工具。真实业务与权限变更回归未完成。 |
| 3.2.1 | REQUIRES_FIX | 模型目录仅 name/description，重试有调用级上限；但压缩侵占业务预留、失败记录和恢复有缺口，见 001、003、004。时间余量和 B>1 实测仍缺。 |
| 3.2.2 | BLOCKED | Registry 解所选 Schema，Order/Knowledge/Refund 绑定及 Policy 路径存在；受控离线单订单通过。真实绑定、对抗 ToolCall、权限及审批回归未运行；Order 重新发现结果未写回见 005。 |
| 3.3.1 | REQUIRES_FIX | 待调用无记录时可重选，失败重发现不留计数；见 002、003、005。真实 Saver、旧 Checkpoint、暂停/unknown 与异常中断未验。 |
| 3.3.2 | REQUIRES_FIX | 真实链路缺安全 opt-in、唯一数据和充分事实证据，见 006；真实质量、成本、PG、V1 及完整门禁均未运行。 |

## 问题

### V203-QA-001 / P1：必要压缩可以消耗保留的最后业务尝试

`app/graph/specialists/order/builder.py:216` 等业务调用构造的 `ModelCallContext` 使用 `reserved_attempts=0`；`app/runtime/model_gateway.py:197` 在业务调用前执行 on_compact；`app/runtime/agent_runtime.py:1125` 将该 context 传到压缩，`app/context/compaction.py:77`、`:108` 以同一业务用量调用摘要。业务预留未传播给压缩。用真实 ContextBuilder 和 Gateway、受控摘要回调模拟 B=1 且仅余一次，实际输出：

```text
business: model_limit_exceeded summary_calls: 1 attempts: 2 reserved_attempts: 0
```

先付出一次摘要调用才发现业务无额度。最小修复：选择后到业务调用之间维护可信预留，压缩前检查并保留业务尝试及期限；不足时零额外模型调用明确失败。测试包括 B=1、B>1、超时与压缩成功后业务可调用，并核对实际运行期压缩路径。

### V203-QA-002 / P1：待调用或审批/unknown 缺记录时仍选择

`app/tools/selector.py:124` 的 pending/approval 检查仅在 `existing_record` 非空分支。独立受控实际调用 `has_pending_calls=True, existing_record=None` 输出：

```text
pending_without_record: selected selector_called: True selected: [('get_order', '1')]
```

旧 Checkpoint 无记录时此 API 不阻止产生新选择；同样的控制流适用于 `waiting_approval_or_unknown=True`。需在任何新选或重发现前固定恢复边界；旧退款恢复继续使用原调用及 Policy，不能伪造新选择。覆盖有/无记录两类 pending、审批、unknown，真实旧 Checkpoint/重启验证零 Selector 和原调用不变。

### V203-QA-003 / P1：失败的重新发现未持久化计数

`app/tools/selector.py:228` 仅在局部增加计数，`:361-398` 等失败返回不包含新记录。用旧记录重复两次非法选择，实际输出：

```text
first_count: 0 failure_1: failed selector_output_invalid record: None failure_2: failed selector_output_invalid selector_calls: 3 attempts: 3
```

首次选择后每次都以 count=0 重新请求，超出每 Task 一次重新发现。需要在发起重新发现时可靠持久化消耗，失败、超时、异常、重启、新 Run 均不可清零；同时保留已发生的模型尝试与 unknown 用量。覆盖失败后重试、checkpoint 重放及成功之后第二次拒绝，防止只在成功路径记数。

### V203-QA-004 / P1：选择与调用用量在节点成功返回前缺持久屏障

`app/tools/selector.py:350` 仅将尝试写入进程内 RunScope；Knowledge `app/graph/specialists/knowledge/builder.py:290-340` 和 Refund `app/graph/specialists/refund/builder.py:222-302` 都在选择后同节点调用业务模型，成功后才返回选择记录；异常中断在节点写入 checkpoint 前可能重放并再次执行选择。当前生产用途单候选短路，但受控多候选同一节点同样如此。现有测试只在内存传递记录，不能证明异常恢复不免费重选。需以实际 Saver/进程中断验证；实现须确保已消费尝试及重发现计数在恢复后不清零，未知结果不能盲目重复。此项为可达恢复风险的源码分析，具体恢复表现待实测，不声称已实测通过。

### V203-QA-005 / P2：Order 循环重新发现结果未写回

`app/graph/specialists/order/builder.py:178-203` 的 plan_query 可接收选择器新 outcome 并绑定其 Schema，但 `:254-274` 返回没有新 record 或 selected_tools；`execute_query` 在 `:281` 仍检查旧投影。发生合法失效重发现时，计数/版本无法持久，执行集合可能与实际绑定不一致并抛 GraphProtocolError。应以记录为权威同步节点输出并保证绑定与执行一致，在权限/版本或可信目的变化、循环、恢复场景实测；待处理调用不得借此替换。

### V203-QA-006 / P1：真实验收入口可能意外调用付费模型，且证据不足

`tests/test_tool_progressive_disclosure.py:867-876` 的真实 PG 测试仅要求原始 `AGENT_TEST_DATABASE_URL` 与 model_configured，不检查 `AGENT_RUN_REAL_MODEL_TESTS=1`，普通全量若配置测试库便可能执行真实调用。`:912-966` 固定使用原五订单中的 `demo-order-a-001`，没有唯一隔离数据建立/清理及独立 SQL 核对列表的归属、分页、完整内容；缺完整选择与业务用量、绑定摘要、ToolCall 与 ToolMessage 配对、Policy 和 PG 对照等证据。测试工厂 `:701` 参数约束为空，需按受控业务输入构造并检验。当前只是只读固定订单，不声称发生写入。最小修复：真实模型显式 opt-in，使用经主 Agent 核验的专用隔离库、唯一数据及精确 finally 清理，补单订单和列表真实完整链路与对抗场景；不得扩张生产用途。独立 Selector 缺设计要求的无关与含糊需求固定题，需补报告质量及实际调用/Token/延迟，未知用量如实记录。

## 实际执行与原始输出

本轮使用项目 `.venv`，执行明确排除两个 `opt_in` 的纯受控测试：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_tool_progressive_disclosure.py -k 'not opt_in' -q
.........                                                                [100%]
9 passed, 2 deselected in 4.22s
```

另外运行三个无网络、无数据库的内存 Python 受控探针，完整关键 stdout 分别见 001～003；其模型为替身，不能代替真实模型或持久恢复验证。未执行全套、真实模型、PG、真实 Checkpoint、pip check 或 Ruff；不把排除视为 skip 通过。模型目录、短路和单次重试边界的受控断言仅证明所测输入；此前 Gemini 的 EOF 不在此轮复现。

## 修复后验收

退回 Implementer 修复上述问题，原 QA 重新独立验证。必须覆盖真实隔离 PG + 真实模型受控两种需求完整链路与 SQL 对照、数据精确清理；独立真实 Selector 的全部固定题；R/B、deadline、重试、压缩、失败/新 Run、真实 Saver 中断重放及旧 Checkpoint/审批/unknown；生产单工具、Knowledge 八节点来源、退款审批幂等、Policy 与未绑定调用、跨身份、02 偏好/上下文、V1 定向和阶段完整门禁。由主 Agent 准备和核验隔离环境，明确 opt-in，避免未经授权的正式库写入。所有未实测项保持开放；最终技术结论和用户 ACCEPTED 不由本首轮报告推导。
