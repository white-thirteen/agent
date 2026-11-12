# 03 工具治理修复后独立回归报告

日期：2026-11-12。关联：03-QA-001 / P2、03-QA-002 / P3。依据：[回归任务](03-tool-governance-regression-task.md)、[原独立QA报告](03-tool-governance-qa-report.md)、[修复报告](../resume/record/03-tool-governance-fix-report.md)、[主Agent记录第5/6节](03-tool-governance-main-review.md)、冻结D03。原QA报告保持原文。

## 1. 结论

**独立回归支持关闭03-QA-001和03-QA-002，未发现需编号为03-QA-003的新增产品问题。**两处明确设计偏差已落实到正确边界，未观察到查询、错误分类、预算、消息或公开接口退化。建议主Agent复核后关闭问题并进行03技术验收；用户正式验收、归档及04切换仍待决定，QA不修改阶段状态。

- 一次最新完整专用真实库回归：**137 passed，0 failed，0 skipped，36.52s**。
- 原16项独立补测本轮全部通过，包含实际SDK Schema绑定、正式HTTP/lifespan/真实PG/Session及真实TCP断开后查询继续、资源释放。
- 新增11个独立场景：最终均取得通过证据。第一次合并执行为 **25 passed、2 failed**；两项失败来自外部夹具主动抛取消与LangGraph异常类型的预期不符。保留原夹具后，改用真实task.cancel()场景，仅复跑两项，结果 **2 passed、9 deselected**。因此本轮共有**27个不同外部场景通过**，并非宣称最终文件一次运行27 passed；初始失败未删除或隐去。
- 五个修复文件Ruff lint通过；执行代码101文件format通过。全仓format仍有原六份Markdown代码示例遗留。
- 测试前后专用库身份/schema/checksum、完整Session/订单行集相同：0条Session、5条订单。108个受保护文件在QA期间摘要未变。
- 本次修复未改变健康查询Schema、路由、SQL目标或事实投影，原独立真实DeepSeek+PG证据仍适用，**本轮付费模型调用0次**。

## 2. 实际修复范围及测试可信度

重新读取适用AGENTS、回归任务、原问题和主Agent裁决；复核D03关于数据层不反向依赖工具/图及私有记录origin/current run的冻结要求（D03:777、856、956）。未据修复方58项自测报告直接判定关闭。

用原QA留存的108文件摘要与本轮当前文件逐项对比，独立得到恰五项变化：

1. `app/domain/orders.py`
2. `app/tools/implementations/orders.py`
3. `app/graph/specialists/order/builder.py`
4. `tests/test_tool_governance.py`
5. `tests/test_order_graph.py`

其余103项与原QA摘要相等。本轮开始另保存修复后108文件摘要，结束复核全部相等。文档导航和协调文件不属于该108项实现摘要；本轮没有编辑它们，只新增本报告。

修复新增测试的实际覆盖：干净子进程导入；get/list两工具连接获取失败的OperationalError两次尝试和ProgrammingError一次尝试；get适配器的ValueError/CancelledError传播；实际Order链的可信记录、不同Run、观察重入、父图与事件隔离。新增测试没有替换或弱化被测治理实现。但其取消/编程错误只测试get，因此独立补测扩展为两工具、在Repository真实SQL执行调用位置注入故障，并经过完整专业图，而不是只调用异常转换函数。

旧独立16项文件逐字复制到本轮外部目录后执行，仍使用当前仓库业务及测试辅助构造，未修改旧证据文件。正式HTTP/TCP场景只替换模型响应源，保留正式create_app/lifespan、Registry、Policy、Executor、Order图、Runtime、SessionRepository及真实池；未将普通替换lifespan的02测试当作正式03装配证据。

## 3. 逐问题闭环

### 03-QA-001 / P2：建议关闭

原问题：数据模块直接导入工具层异常，工具契约又加载Graph/Runtime，违反D03的数据层依赖方向。

实际修复：

- [领域模块:39](../../app/domain/orders.py:39)及:43定义OrderReadTransientError/OrderReadUnavailableError；[Repository:80](../../app/domain/orders.py:80)及:82按原白名单转换数据访问故障，不再引用工具/Graph/Runtime。
- [get适配器:57](../../app/tools/implementations/orders.py:57)和[list适配器:68](../../app/tools/implementations/orders.py:68)将领域故障转换为原治理异常。Executor、重试策略、错误code、Schema、owner SQL及正常返回结构未变。
- 没有增加宽泛Exception捕获。业务不可见仍为order_not_accessible；领域技术故障继续为order_query_unavailable；取消和非预期编程错误没有被适配器改成空页或订单不存在。

独立证据：

| 验证 | 可观察结果 | 判断 |
| --- | --- | --- |
| `python -I`干净子进程导入app.domain.orders | 进程中app.tools、app.graph、app.runtime及各自子模块数量均为0；子进程退出0 | 原反向依赖已消除；不是在预先导入上层模块的pytest进程中检查 |
| get/list完整专业图：SQL execute第一次OperationalError，第二次返回固定Decimal行 | 各2次SQL尝试/工具用量/record attempts，completed，ToolMessage安全data与19.95事实摘要；无模型伪造999金额/物流 | 安全瞬时重试后成功、逐尝试计数保持 |
| get/list完整专业图：SQL execute ProgrammingError | 各只1次SQL/工具尝试，failed/order_query_unavailable，ToolMessage.data=None，无facts，不再调用模型 | 不可重试技术失败没有伪装空页/不存在 |
| get/list完整专业图：SQL execute ValueError | ValueError向外传播，各1次工具尝试、模型仅首轮，未被转换成业务拒绝 | 编程错误边界保持 |
| get/list完整专业图：SQL处理中对运行任务task.cancel() | CancelledError向外传播，各1次工具尝试，后续模型未启动 | 实际Run取消链路保持 |
| 旧独立关闭真实池场景、治理超时/批次取消、最新全量 | 关闭实际PG池为技术失败且有限重试；超时不重试；取消不启动后续handler；相关测试通过 | 异常转换未破坏原治理 |
| 真实PG正常get/list、归属隔离、金额、种子、正式HTTP/TCP | 本轮全量与旧独立16项通过 | 健康路径与资源生命周期保持 |

补测的SQL故障是**受控连接/游标替身**，调用真实Repository/Service/工具适配/Executor/专业图；没有对真实库注入SQL错误、使用真实连接凭据构造失败，或声称进行真实网络停机。另有本轮实际PG健康链和关闭实际池的故障证据。

### 03-QA-002 / P3：建议关闭

原问题：call_records只有call、normalized_args和result，origin及当前run关联只能从外围推断。

实际修复：[execute_query:249](../../app/graph/specialists/order/builder.py:249)及:250分别保存`tool_context.origin`、`tool_context.execution.run_id`，保留原调用和结果，不将记录输出到公共事件。来源为程序构造的ToolExecutionContext，未读取raw_args中的候选值。

独立证据（get/list各一组）：

- 相同call_id=`shared-call`在trusted-one/trusted-two两个Run分别执行，记录origin均为model，run_id分别对应可信Run；原call_id/name/raw_args、normalized_args、execution_id、attempts保留。
- 请求候选entities携带伪造origin/run_id不影响可信关联；ToolCall.raw_args进一步携带伪造origin/run_id时Schema拒绝，attempts=0，记录仍保存真实origin/run_id和原始调用。安全ToolMessage不回显伪造值。
- 对已保存结果连续两次调用实际observe，并经add_messages合并；原call_records完全相等，计数仍为1，最终对应ToolMessage恰1条；观察依赖采用任何Executor属性访问即失败的守卫。
- 当前仓库主图测试检查父快照无call_records/ToolMessage，公开事件无私有记录字段或调用ID；独立正式HTTP补测再次检查公共流没有私有调用ID、call_records、工具消息或伪造模型候选。

该修复满足03的显式关联要求。不同Run仍是03普通调用验证，不声称已经实现04持久快照恢复或副作用幂等。

## 4. 命令与实际结果

解释器均为项目`.venv\Scripts\python.exe`，默认pyproject及脱敏插件、fd捕获保持，未使用-s。外部目录记为R：

`C:\Users\15294\AppData\Local\Temp\agent03-regression-20261112`

| 实际命令 | 结果 |
| --- | --- |
| `.\.venv\Scripts\python.exe C:/Users/15294/AppData/Local/Temp/agent03-regression-20261112/run_audit.py` | exit0；预检后内层`python -m pytest -q`：**137 passed in 36.52s**；完整行集/schema及108文件相等 |
| `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q C:/Users/15294/AppData/Local/Temp/agent03-regression-20261112/test_independent_03.py C:/Users/15294/AppData/Local/Temp/agent03-regression-20261112/test_fix_regression.py` | exit1；**25 passed, 2 failed in 13.48s**；原16项全通过，另9项新场景通过；失败原因见下文 |
| `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q C:/Users/15294/AppData/Local/Temp/agent03-regression-20261112/test_fix_regression.py -k 'complete_graph_fault_chain and cancel' --tb=short` | exit0；**2 passed, 9 deselected in 3.21s**；仅复跑修改后的两项真实任务取消场景，未重复其余已有效用例 |
| `.\.venv\Scripts\python.exe -m ruff check app/domain/orders.py app/tools/implementations/orders.py app/graph/specialists/order/builder.py tests/test_tool_governance.py tests/test_order_graph.py` | exit0；All checks passed |
| `.\.venv\Scripts\python.exe -m ruff format --check app tests scripts` | exit0；101 files already formatted |
| `.\.venv\Scripts\python.exe C:/Users/15294/AppData/Local/Temp/agent03-regression-20261112/check_after.py` | exit0；独立确认相对原QA仅五文件变化、本轮108文件相等、完整数据库行集/schema相等、领域AST上层导入数0；内部全仓format退出1，原六份Markdown遗留 |

137相对原130增加7项，来自修复加入的导入用例1、两工具×两种技术故障4、get编程错误/主动取消2；原订单图用例增加断言，没有以删旧用例维持数量。

**初始两项失败的归因与处理：**新外部夹具在SQL execute中直接`raise asyncio.CancelledError()`，并预期穿过整个LangGraph后仍是同类异常。安装版本的`.venv/Lib/site-packages/langgraph/pregel/_retry.py:790`明确区分：节点主动抛取消且Task.cancelling()==0时，转换成NodeCancelledError，防止被误报成功；真实Task取消保持传播。原失败输出正是execute_query的NodeCancelledError，不是吞掉取消继续成功。

保留初版`initial_synthetic_cancel_probe.py`，未改仓库测试或产品。只将两项独立取消刺激改为阻塞SQL后对运行任务调用task.cancel()，继续严格要求CancelledError传播、只尝试1次、后续模型0次；两项通过。结合修复新增的适配器直接取消用例通过和本地框架源码，判定为外部补测对框架行为预期不准确，不新增产品问题。原失败次数和退出码如上保留，不将其改写成首次全绿。

## 5. 原14项门禁的受影响复核

| D03 13.2门禁 | 本轮证据与结论 |
| --- | --- |
| Registry/Schema | 原独立SDK实际请求完整Schema及并发绑定隔离通过；Registry/Metadata未变，保持通过 |
| 曝光/执行分离 | 原独立未知/禁用/未允许工具零尝试通过；新增身份候选字段拒绝通过 |
| 查询任务范围 | 原get/list换工具、改订单/扩大limit/offset拒绝补测通过 |
| Handler边界 | 原typed一次验证、最小上下文通过；本轮领域无上层导入，03-QA-001闭环 |
| 身份与owner | 真实PG跨用户/不存在统一拒绝，参数化SQL及Service归属投影未变；受控完整故障链也检查owner参数 |
| Policy三态 | 全量审批不可用、DENY零执行等通过；Policy/Executor未变 |
| 尝试/预算 | 全量跨Run累计与独立重试/拒绝/取消计数通过；两工具完整新链验证1/2次符合预期 |
| 批次/消息 | 原批次结构错误零执行、逐call闭合与raw/规范参数分离通过；新记录没有改原call/result |
| 超时/取消/观察 | 原超时、批次取消、观察Reducer重进通过；新增真实任务取消及跨Run记录不变通过 |
| PG/种子 | 全量真实专用库身份/schema/checksum/约束/种子/Session并发通过，完整行集恢复 |
| 订单结果/DB故障 | 本轮真实PG健康路径、关闭真实池、新两工具瞬时后成功/不可重试/编程错误/取消通过 |
| 专业主图/公共出口 | 全量主图/预算/run_finish/订阅回归和原正式HTTP/TCP补测通过，无新增私有输出 |
| 真实模型+PG | 原独立DeepSeek专项证据继续有效，依据见下一节；本轮没有默认或额外付费请求 |
| 后继未实现 | 全量Refund/Knowledge不可用、Runtime公共契约通过；未实现或宣称04/05能力 |

## 6. 原真实模型证据适用性

本轮摘要证实Gateway、模型资源/配置、Supervisor Prompt/路由、主图/Runtime、SQL迁移、种子、真实专项脚本均与原QA相同。审查五文件实际变化：领域层只替换故障异常定义和抛出位置；工具层只增加对应异常适配；Order builder只增加两项私有记录；两测试文件加强断言。GetOrderArgs/ListOrdersArgs、工具元数据、完整模型参数Schema、健康SQL/返回行、金额/时间投影、facts固定摘要及ToolMessage/公共事件生成逻辑没有改变。

原独立专项已实际验证DeepSeek/deepseek-flash的get/list原生ToolCall、配对ToolMessage及真实源行facts，各2次模型/1次工具。修复后的真实PG正常路径、完整专业图和正式HTTP/TCP又在本轮通过。因此本次没有需要重新付费验证的Schema/供应商兼容性变化，延用原证据合理。未将“本轮未调用”写成“本轮真实模型重新通过”。

## 7. 数据保护与独立性

连接前验证Settings配置目标，连接后current_database/current_user核对为agent_demo_test/agent_test；版本恰1、2、3，每个checksum等于本地SQL SHA-256。只使用该专用库，没有连接应用库测试、改密码、重建、迁移升级或安装依赖。

run_audit.py先对Session和订单完整`SELECT * ORDER BY 1,2`结果计算摘要，对完整迁移记录含applied_at另取摘要，随后运行全量；check_after.py及最终只读探针再次比较。不是只检查行数。

| 时点 | Session | 订单 | 完整行集/迁移记录摘要 |
| --- | --- | --- | --- |
| before.json | 0 | 5 | 基准 |
| after-full.json | 0 | 5 | 全部相等 |
| after-final.json（外部补测及取消复测后） | 0 | 5 | 全部与基准相等 |

既有真实订单约束插入事务回滚，退款标记恢复原值；原Session测试精确清理自身随机用户。独立HTTP/TCP只删除各自唯一UUID conversation与dev-user匹配的Session，未删除固定订单或用户已有数据。

完整回归包含既有迁移测试：幂等入口检查已应用001–003，无新版本应用；受控下一编号故障DDL事务回滚，并断言无探针表/新增版本。本轮没有成功迁移或结构升级，未隐去测试对幂等入口及回滚的调用。

本轮外部证据为R目录下run_audit.py、test_independent_03.py（原16项）、test_fix_regression.py（最终11项）、initial_synthetic_cancel_probe.py（初版失败夹具）、check_after.py、before.json、after-full.json、after-final.json、protected.json、full-pytest.txt、full-format.txt。两轮外部pytest数字及失败类别另在本报告如实记录；没有声称外部stdout全文均已单独落盘。快照只保存摘要/行数，不保存凭据、连接串或数据库行原文。

本轮未修改业务/仓库测试/配置/依赖/冻结设计、原QA报告、修复报告或主Agent记录；未调用Bridge或其他会话，未Commit/Push，未做04。

## 8. 遗留与交回

03-QA-001/002均建议关闭，无新增03-QA-003。既有P3-01六份Markdown示例格式、RISK-02-CRED历史暴露/密码复用按既定接受决定保留，不重复阻塞；本轮仍保持输出脱敏。内存快照/单进程执行/无事件重放及04审批恢复、05 RAG/Store均是已声明边界。

独立回归完成，交主Agent作问题关闭与技术验收。03用户正式验收、Git归档、04切换授权不在本报告权限内。
