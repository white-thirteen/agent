# V2 03 fix01 独立复测（第一阶段）

日期：2026-11-20。**首轮 FAIL 保持；fix01 尚未通过。** 本阶段只读检查交付、冻结设计和实际源码，执行纯内存受控测试；真实 PostgreSQL、真实模型、进程中断及完整门禁由主 Agent 后续安排，本报告不替代最终结论。

## 第一阶段发现

### V203-QA-007 / P1：持久预留耗时侵占业务时间

`app/tools/selector.py` 计算剩余 Run 时间和 `available_seconds` 后，先 `await scope.begin_selection(...)`，随后才以旧的 `available_seconds` 构造 Selector deadline。`app/runtime/model_gateway.py` 每次模型调用又先等待 `before_attempt` 持久写入，但没有在写入后重新从 RunScope 验证业务时间预留。慢 Saver 或重试可使首次或后续实际 Selector 调用侵占 B 次业务所需时间。

无数据库/无真实模型受控探针：Run 余 20 秒、业务配置时间 10 秒，模拟首次 `begin_selection` 消耗 15 秒后，实际输出：

```text
status: selected selector_calls: 1 remaining_seconds: 5.0 business_timeout: 10
```

应在每次实际 provider 调用（含每次重试）前，扣除所有持久化等已发生时间并重新核对可信 B 和截止时间；不足时不调用 provider。验证慢首次写、慢逐次预留写、B>1、重试和未放宽 Run 截止时间。

### V203-QA-008 / P2：业务上下文构造覆盖 Selector 用量回执

`app/runtime/run_scope.py` 的 `record_selector_usage` 把回执写在 `_context_view.selector_usage`，但业务 Gateway 触发 `record_context_view` 时整体替换该字典。纯受控实际 Selector→业务 Gateway 调用，关键输出：

```text
after_selector: {'selector_usage': {'input_tokens': 5, 'output_tokens': 3, 'total_tokens': 8, 'status': 'known', 'estimation_method': None}}
after_business: {'input_hash': '7281240cd8f9005786b9d3ca0ffbb6b15f662096cc555924f99a1ef36b8a66bf', 'history_ids': [], 'input_tokens': 89, 'count_status': 'estimated', 'count_method': 'langchain_approximate', 'provider_usage': {'input_tokens': 5, 'output_tokens': 3, 'total_tokens': 8, 'status': 'known', 'estimation_method': None}}
```

成功 Selector 用量丢失；多次 Selector 的回执也被覆盖，不能可靠分开报告选择成本。需要保存内部每次或明确汇总的 Selector 已知/unknown 用量，与业务回执区分，不向公开事实/SSE泄露；验证成功后业务调用、多次调用、失败与恢复。

## 已核对事项与实际执行

已读原 fix01 交付、主裁决及 Saver 复现证据，检查 SelectionReservation、Runtime 完整 checkpoint 和审批 child 读取、Selector/Scope/Gateway、三个业务图接线、受控工厂及真实测试入口。源码显示已增加 pending 缺记录拒绝、重新发现失败携带计数、业务压缩预留、Order 返回更新后的记录和受控范围摘要；这些是实现观察，尚不能关闭原问题。独立运行：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_tool_progressive_disclosure.py -q
....................                                                     [100%]
20 passed, 1 warning in 3.45s
```

警告为 LangGraph 对 `langgraph.constants.Send` 的依赖弃用警告。该模块当前不包含默认收集的真实模型用例；另有上述两个内存探针，使用项目 `.venv`，无数据库和真实模型。审查见手动真实入口已从默认测试发现移出，要求显式 opt-in、隔离库在线身份、唯一订单与 finally 精确清理，尚未独立运行。已交付的 HEAD 对照为受控模型且仅一个订单场景，不能称真实生产 token/延迟或收益对照。

原 QA-001～006 未因本轮受控通过而关闭。仍需在主 Agent 完整门禁完成后，按授权串行独立验证真实隔离 Saver/PG、审批原调用、崩溃/完整提交和同 Task 新 Run；对 ASCII 安全证据执行一次新增价值的真实模型组并核对 SQL 与清理。最后复测新问题并保留所有原始失败证据；阶段结论由主 Agent 决定。

## fix02 独立复测（2026-11-20）

**当前结论：定向修复证据通过，完整阶段门禁待主 Agent 运行并交独立只读审核；首轮 FAIL 原文保留，不宣布阶段 PASS 或用户 ACCEPTED。** 独立 QA 本轮结束后释放 PG/模型窗口，后续不并发运行测试。主 Agent 确认运行元数据 QA 与 Implementer 均 Terra/high。

### 六 Task 建议

| Task | 建议 | 边界 |
| --- | --- | --- |
| 3.1.1 目录与版本 | VERIFIED（定向） | 元数据 brief、冻结与绑定版本/摘要受控测试；完整默认门禁待审核。 |
| 3.1.2 筛选 | VERIFIED（定向） | Agent、scope、用途及内部工具受控检查，生产订单真实对照单工具。 |
| 3.2.1 Selector 与预算 | VERIFIED（定向） | R/B、重试、慢持久写、压缩预留、用量回执受控测试；真实 Selector 固定五题。 |
| 3.2.2 绑定执行一致 | VERIFIED（定向） | 两个受控多候选真实 Node 经正式绑定、Policy/Executor 及真实 PG，和 SQL 比对；其余边界由受控测试覆盖。 |
| 3.3.1 复用恢复 | VERIFIED（定向） | 真实隔离 Saver 的异常/强退/完整提交，旧审批样本及新 Run/重发现下限；旧审批使用受控业务服务，同进程重建 Runtime，非真实旧生产快照或跨进程审批验证。 |
| 3.3.2 阶段验收 | BLOCKED | 真实质量/两链路/成本定向证据完成，完整默认门禁 r2 和保护证据仍待主 Agent 提供及本 QA 只读审核。 |

### 原问题 001～008 复测建议

- **001 建议关闭（定向）**：真实 Runtime compactor 的 B=1、B=2、期限与业务调用受控检查在 `tests/test_tool_progressive_disclosure.py` 通过；隔离 PG 的运行内 compaction 测试 1 项通过。摘要模型为替身，不冒称真实模型压缩验证。
- **002 建议关闭（定向）**：pending 无记录受控拒绝；基于 HEAD Refund builder 生成的真实隔离 Saver 旧审批样本，当前 Runtime 同进程重建后 Selector 0，call_id、operation_id、工具版本、参数和审批主体均不变，Policy 重查、重复 resume 后受控副作用总数 1。复跑原探针证据 [legacy-refund](../evidence/v2-03-independent-legacy-refund.log)；未称实际旧生产快照或跨进程审批恢复。
- **003 建议关闭（定向）**：失败重新发现记录计数、二次拒绝和 unknown 用量受控测试通过；真实 Saver 强退探针重放检查显示 rediscovery floor=1、attempt floor=2、root attempts=1，唯一 thread 清理。此探针为复跑已审查的原实施脚本，见 [selector-kill](../evidence/v2-03-independent-selector-kill.log)。
- **004 建议关闭（定向）**：独立编写 [Saver 探针](../evidence/v2-03-independent-saver-probe.py)，真实隔离 Saver 上节点异常 root attempts=0、持久 floor=1/inflight，恢复拒绝未知；完整节点提交 root=1 后可确认，重建 reservation 开始同 Task 新 Run 保留 floor=1；独立子进程 `os._exit(71)` 后 root=0、floor=1/inflight。三个唯一 thread 及专属 namespace 均 `cleaned=true`。另外复跑原实施 [reuse-kill](../evidence/v2-03-independent-reuse-kill.log)：新 Run 业务调用强退 floor=2、root=1、thread 清理。受控 Selector 为替身；不能泛化到所有恢复组合。
- **005 建议关闭（定向）**：Order 按可信 query 形成范围摘要，重发现后输出记录、投影与绑定一致；相同目标历史变化复用、目标变化一次重选的受控 Graph 检查通过。真实 get/list 链路所选、绑定、执行和业务事实一致。
- **006 建议关闭（定向）**：默认测试不收集显式 opt-in 的手动真实入口；指定隔离库在线身份验证和唯一订单数据已在独立真实组实测，查询及分页同 SQL 对照，finally 清理剩余0。原有乱码日志保留，新增无损日志见下。
- **007 建议关闭（定向）**：慢首次/重发现/逐次持久写、重试、B>1 和绝对截止时间受控用例通过，额外零 provider 调用边界包含在本轮 42 项中；未通过付费调用模拟故障。
- **008 建议关闭（定向）**：成功/失败、重试 unknown、业务 context 覆盖、新 Run/父子白名单和去重受控用例通过；独立真实 Saver 探针看到完整 Selector 回执在 namespace 持久保存。真实模型用量另在手动日志中逐调用记载；不把未知推成零。

### 本轮实测与原始证据

- `.venv` 执行 `python -m pytest tests/test_tool_progressive_disclosure.py tests/test_refund_checkpoint.py -q --tb=short`：**42 passed，1 warning，4.15s**。警告为 LangGraph 依赖弃用。另通过经隔离 guard 的 `tests/test_context_run_compaction_postgres.py tests/test_refund_context_checkpoint_postgres.py`：**2 passed，1 warning**，见 [PG 定向](../evidence/v2-03-independent-pg-regression.log)。旧审批探针真实 Saver、业务服务替身；全部使用唯一 thread 和精确清理。
- [无损真实手动组原始字节](../evidence/v2-03-independent-real-manual.log)：显式 opt-in、隔离端点及在线数据库身份，`model_max_retries=0`，**2 passed**。固定质量五题均合法且语义符合预期；5 次 Selector 总 **2466 known tokens**。单订单与分页两个真实多候选 Node，候选各2、各1次 Selector和1次业务模型，共4次 **1879 known tokens**；Policy/Executor 的原生 ToolCall 与 ToolMessage 对应，SQL 单订单1行、分页2行、他用户排除；`cleanup_remaining=0`。全部 **9次调用、4345 known tokens、0 unknown**。fixture SHA-256 `1a3e596e1b7d684a64a25f08b26203c95a8d6209d07093875e967e12b6430725` 与原回执一致；原始字节为有效 UTF-8，无 U+FFFD，ASCII JSON 解码后的五题需求与 fixture 原文逐字一致。原乱码证据未改写。
- [真实单工具成本对照](../evidence/v2-03-independent-real-cost.log)：从 `1f3d73643af84fdc55f7f314d6c0db6f0c34560a` 提取 HEAD Order builder 源码（SHA-256 `787dfc90f2f9c4c3203ba0f9d8d6b2dd29a37d67b7da83bd3af78c606386b0a5`），共享当前其他依赖，使用同配置真实 deepseek-flash、同隔离 PG 唯一订单、正式 Policy/Executor，禁用自动模型重试。HEAD/current 各 **2次业务模型、Selector 0、1次业务工具**，分别 **1173/1192 known tokens**；每次实际绑定均单个 `get_order`，Schema 同 SHA，分别约 **83/83 tokens**（LangChain 估算）。两侧 SQL 事实比较通过、各完成，清理剩余0；单次耗时 **2.509/2.349 秒**仅为观测，不能归因于优化，不宣称延迟或成本收益。该对照不是完整旧版环境复现；optional preference 工具在此最小 Registry 不可用，Policy 明确拒绝后原路径继续。成本探针报告 SQL 事实匹配布尔值，未把单行原值写入日志，实际查询和比较逻辑见 [探针](../evidence/v2-03-independent-cost-probe.py)。
- 全范围 `ruff check app tests` 由主 Agent 发现 HEAD 已有3个 E501（`app/core/errors.py:56-57`、`tests/test_context_maintenance_shutdown.py:11`），两文件无本轮 diff，非本轮新增问题；不得称全范围 Ruff PASS。实施者报告受影响15文件 Ruff/format 通过，本 QA 未重跑该检查。

本轮真实模型共 **13次调用、6710 known tokens、0 unknown**（手动4345 + HEAD1173 + 当前1192），未额外重跑。此次 SQL 清理为唯一数据的精确清理；主 Agent 此前中断的完整回归是 **INTERRUPTED_NOT_PASS**，其 after-only 快照不是前后相同证明。最终完整默认回归、全库保护与审计仍开放；任何 skip、环境失败或中断均不算通过。

受控42项与独立Saver运行输出、子进程退出以及 fixture/编码检查的会话工具输出，另留 [逐字摘录](../evidence/v2-03-independent-session-output-transcript.md)；这是人工整理的会话文本，不冒称进程原始字节捕获。真实手动组原日志仍为原始字节。
