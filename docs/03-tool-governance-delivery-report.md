# 03 工具治理与模拟订单查询：开发交付报告

日期：2026-11-11。状态：开发与自测完成，等待主 Agent 审核及独立 QA；本报告不是用户阶段验收。基线 `94cf205a734c305a6919a34cfeacc3e717d4856f`。开发按执行任务、冻结 D03 及本轮授权执行；未开始 04。

## 六个 Task

| Task | 结果 | 实现与证据 |
| --- | --- | --- |
| 3.1.1 Metadata/Registry | 完成 | 唯一 ToolDefinition、注册校验、重名/冻结防护和启动冻结；`tests/test_tool_governance.py`。 |
| 3.1.2 过滤与模型绑定 | 完成 | Agent/scope 与 query_spec 单工具交集、完整 Pydantic JSON Schema、曝光和执行集合一致；工具和订单图测试。 |
| 3.2.1 Policy/Executor | 完成 | ALLOW/DENY/REQUIRE_APPROVAL、唯一 Executor、参数一次验证与尝试前复检、最小业务上下文、只读有限重试、超时及累计预算。03 不放行审批。 |
| 3.2.2 工具消息与治理 | 完成 | 原生批次结构校验、顺序预检/执行、失败截断、逐 call 配对 ToolMessage、私有调用记录及观察重进；工具和订单图测试。 |
| 3.3.1 最小模拟订单事实 | 完成 | 003 DDL、owner SQL、领域归属复核、Decimal 投影、固定双用户五订单和幂等种子；`tests/test_order_postgres.py` 及实际迁移/种子。 |
| 3.3.2 OrderAgent 查询 | 完成 | 七节点、单工具精确约束、事实摘要、主图接线、同 Task 澄清续接和真实模型+PG 验证。 |

## 实际文件和接口

- 新增 `app/tools/models.py`、`app/tools/messages.py`、`app/tools/implementations/orders.py`；修改 `app/tools/registry.py`、`app/tools/policy.py`、`app/tools/executor.py`。核心接口为 `ToolRegistry.register/freeze/list/get`、`ToolPolicy.evaluate`、`ToolExecutor.execute/execute_batch`、`parse_tool_calls/to_tool_message`。内部 `ToolExecutionResult.normalized_args` 附加保存一次验证后的规范参数，供私有调用记录使用；ToolMessage 及公共事件不输出该字段。
- 新增 `app/domain/orders.py`、`migrations/003_demo_orders.sql`、`scripts/seed_orders.py`、`scripts/verify_03_real.py`。OrderRepository 对 get/list 固定使用可信 owner 的参数化 SQL；MockOrderService 复核 owner 并输出两位小数字符串与模拟标识。种子和真实联调均需显式执行。
- 修改 `app/graph/specialists/order/builder.py`、`app/graph/transfers.py`、`app/agents/prompts/supervisor.py`、`app/main.py`、`app/core/config.py`、`app/infrastructure/postgres.py`、`app/runtime/run_scope.py`、`.env.example`、`README.md`。新增三项工具配置，期望 schema 为 3；Supervisor 提供 get/list 候选，专业节点确定目标，Registry/Policy 仍以可信上下文约束。
- 新增 `tests/test_tool_governance.py`、`tests/test_order_graph.py`、`tests/test_order_postgres.py`、`tests/order_skeleton.py`；修改 `tests/runtime_support.py`、`tests/test_graph_protocol.py`。02 Runtime 隔离回归所需的原 Order 不可用骨架移到明确的测试专用替身；旧“实际专业骨架”参数集删除已正式实现的 Order，新增真实 Order 图和主图接线测试覆盖其新行为。
- 同步 `docs/graph-protocol.md` 当前协议说明并在 D03 末尾追加实施索引；报告文件为 `docs/03-tool-governance-delivery-report.md`。既有 `general.py`、三个旧文档删除、D01 历史差异和独立 Bridge 文档保持原状；主 Agent 协调文件未修改。未更改依赖、提交或推送。

应用按原生命周期管理连接池、模型及 Runtime；模型配置就绪时固定构造并冻结目录，Handler 闭包持有领域服务，专业图只调用 Executor。退出仍先收敛 Runtime 再释放模型及数据库资源。03 不建立新的 Task、Store、审批或 Checkpoint 平台。

## D03 13.2 矩阵与证据

| 矩阵项 | 结果和证据 |
| --- | --- |
| Registry 与 Schema | 自动测试验证冻结、重名、过滤和完整 schema；订单图测试确认实际绑定 get 或 list 的完整单工具 schema。 |
| 曝光/执行分离 | 错订单、身份注入、未登记工具、缺 scope、审批要求在 Handler 前拒绝；相应测试断言零 Handler/零工具尝试。 |
| Order 任务范围 | get/list 仅绑定目标工具，参数精确约束，错误订单拒绝；受控图测试及 Policy 测试。 |
| Handler 边界 | 测试断言 typed args 与仅 user/task/run 的业务上下文。 |
| 身份与 owner | 参数禁止身份；实际测试库对本人、另一用户和不存在订单验证统一不可访问；SQL 和领域再次复核归属。 |
| Policy 三态 | 低风险成功、DENY 和 REQUIRE_APPROVAL 验证；审批仍为不可用，不建立等待状态。 |
| 计数/限制 | 受控测试验证重试每次计数、拒绝零计数、预算耗尽不再重试；主图测试验证澄清跨 Run 的模型与工具累计。 |
| 批次/消息 | 测试验证串行、失败后 not_executed、重复 ID 拒绝、每结果配对原 ID 的 ToolMessage；真实模型也经过原生 call/message 往返。 |
| 超时/取消/观察重进 | 工具超时及取消测试通过；对保存结果直接两次调用实际 observe_order 节点，消息 ID/内容与事实一致、工具计数不增加。尚未模拟 LangGraph 持久中断后的跨进程恢复，该能力属于 04。 |
| 表与种子 | 真实 PG 验证 numeric(12,2)、非法金额 check、双用户种子、重复执行、已有退款状态保留；测试时短暂变更的字段已恢复。 |
| 订单结果 | 真实 PG 验证本人/跨用户/不存在/分页/空页；受控模型验证拒绝无事实回复、固定摘要；真实模型 get/list 的 facts 与源行比较一致。DB 故障分类由 Executor 边界实现，超时有自动测试；真实网络故障未人为制造。 |
| 专业主图 | 受控主图验证缺参同 Task、新 Run、累计额度、最终摘要和工具 ID 不进入公共事件；沿用 02 的 Response、run_finish 及独立订阅/断开回归。 |
| 真实联调 | DeepSeek `deepseek-flash`，使用真实模型和真实专用 PG：get `demo-order-a-001` 与 list 当前页各实际发出原生 ToolCall、收到 ToolMessage，facts 与源数据对比一致；每条链路 2 次模型、1 次工具尝试。最后一轮验证在本次实现收敛后执行。 |
| 后继未实现 | Refund/Knowledge 继续 capability_unavailable；没有审批、真实退款、RAG/Store 或持久恢复的假完成。 |

## 数据库操作与隔离

迁移前只读确认两库分别为 `agent_demo`/`agent_app`、`agent_demo_test`/`agent_test`，原版本均为 1、2；按授权分别应用下一空闲编号 003，001/002 原样保留，现为 1、2、3。只建 `demo_orders` 和 owner/时间索引；未重建容器、删除数据库/Volume、改角色或密码。两库各明确执行种子两次，首次各插入 5、第二次各插入 0。两库的五个固定种子作为显式初始化数据保留；测试专用的非法记录事务回滚、会话测试精确删除自身键，临时退款状态恢复原值；没有清理其他用户数据。测试和真实模型验收均连接测试库，未用应用库运行测试。历史凭据暴露和角色密码复用按既有接受决定保留。

## 命令与结果

- `python -m pytest -q`：默认不调用付费模型，初次全量 125 passed、2 skipped（未显式提供测试库环境）。
- 在进程内部从本地 Settings 获取 `AGENT_TEST_DATABASE_URL`、先调用 `validate_test_target` 后执行 `pytest -q`：**129 passed**；pytest 始终使用仓库默认 fd 捕获和脱敏插件，不打印连接设置或凭据。
- 完整回归后补充观察节点重入测试，`python -m pytest tests/test_order_graph.py -q`：6 passed；其余业务代码未改变。
- 显式测试库运行 `tests/test_postgres.py`：3 passed；`tests/test_order_postgres.py`：1 passed。前者包含真实迁移重入/回滚及 Session 并发隔离，后者包含种子状态保持、金额约束和 owner。
- `python -m scripts.verify_03_real`：`PG_IDENTITY_SCHEMA_OWNER_EMPTY_PAGE_OK`、`REAL_MODEL_PG_GET_OK model_attempts=2 tool_attempts=1`、`REAL_MODEL_PG_LIST_OK model_attempts=2 tool_attempts=1`；探针只输出安全固定类别，不输出 URL、密钥、连接异常全文或模型原文。真实模型验证执行两轮，每轮 get/list 各两次模型调用；第二轮复核收敛实现。
- `python -m ruff check .`：通过；`python -m ruff format --check app tests scripts`：101 个文件通过。全仓 `ruff format --check .` 因已有历史 Markdown 代码块格式不一致未通过，未格式化或修改冻结/历史设计文档。

## 偏差、限制与 04 交接

D03 设计中迁移编号采用“下一空闲编号”，实际按授权为 003。规范参数作为私有结果扩展字段传给 call_records；不改变公共协议或将原始参数发到 SSE。02 测试替身调整不代表生产 Order 退回骨架。

待独立 QA 重点复核观察节点重入不重做 Handler、真实 DB 技术故障分类、各矩阵边界及正式 HTTP 集成。真实模型验收是订单专业图 + 真实 Gateway + 测试库的链路；Supervisor 到订单图和公共事件由受控模型主图测试覆盖，未声称已进行真实模型全 HTTP 端到端验收。

04 应在同一 Policy/Executor 之上实现经可信记录核验的审批、持久中断恢复和业务幂等；03 的 approval_required 从不当成批准，私有 call_records 不是审批凭据或副作用幂等表。退款写操作、Checkpointer 持久化及断点恢复仍未实施。是否满足阶段正式验收须由主 Agent 和独立 QA 根据上述证据及未验证项判断。
