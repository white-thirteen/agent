# 03 工具治理与模拟订单查询独立 QA 报告

日期：2026-11-12。性质：本轮重新派发后的独立审查与实测，不沿用此前 failed 轮次的结论。02 基线为 `94cf205a734c305a6919a34cfeacc3e717d4856f`；本报告不代表用户正式验收、Git 归档或 04 开始授权。

## 1. 总体结论

**建议有条件通过，交主 Agent 逐项裁决两处设计偏差后决定阶段验收。**

- 一次最新完整真实测试库回归：**130 passed，0 failed，0 skipped**。开发报告的 129 项之后新增的 observe 重入用例已包含在本次 130 项中。
- 仓库外独立补测：先运行 15 项，再补充真实 TCP / 正式应用查询场景 1 项，合计 **16 passed，0 failed，0 skipped**。
- 独立显式真实模型专项：DeepSeek / `deepseek-flash`，get/list 各完成 2 次模型尝试、1 次真实 PostgreSQL 工具查询；原生调用、配对 ToolMessage、facts 与源行核对通过。该专项与默认 pytest 分离。
- D03 第 13.2 节 **14 项核心行为门禁均取得通过证据**。这不等于完全无设计偏差：确认新增 **P2 一项、P3 一项**，分别涉及数据层依赖方向和调用记录的显式关联信息；未发现 P0/P1 或实际功能测试失败。
- Ruff lint 通过；执行代码 101 文件 format 通过。全仓 format 仍因既有六份 Markdown 示例不通过，属于已知 P3-01，未新增为本轮问题。

当前实现具备真实本人订单查询、工具统一治理和 02 Runtime 衔接基础。03-QA-001 应在进入 04 前整改或由主 Agent 明确作偏差接受决定；03-QA-002 建议一并收敛。QA 不自行修改或将阶段改为 ACCEPTED。

## 2. 审查基准、范围与独立性

已阅读适用 AGENTS、当前 README、有效项目定位/路线图、冻结 D03 全文及 13.2 矩阵、03 执行任务/交付报告、Graph 协议和 01/02 关联接口。历史“未实施”段落结合末尾实施索引理解，不将历史语境当作当前阻塞。

主要审查实现：`app/tools/{models,registry,policy,executor,messages}.py`、`app/tools/implementations/orders.py`、`app/domain/orders.py`、订单 builder、父子 transfers/wrapper、主图 builder/Response/run_finish、Runtime/RunScope/Gateway、正式 main/Route/Service/订阅所有者、PG/Session 生命周期、003 SQL、seed/real 验证脚本、集中配置和受影响测试。审查包括源码调用方向和实际运行路径，未仅凭文件存在判定完成。

测试可信度核查：

1. `test_order_postgres.py` 的数据库操作确实通过 psycopg/实际池访问专用库；真实迁移/Session 测试亦连接该库。并非用 Mock 替代 PG 门禁。
2. 常规模型测试使用受控输出，默认 pytest 不付费；真实模型专项另外显式运行。MockOrderService 名称表示模拟业务，但正式事实来自实际订单表。
3. `runtime_support.http_application` 替换 lifespan 和 Session，原 Order 骨架已迁到 tests/order_skeleton。因此普通 HTTP/部分 02 测试不能证明 03 正式装配；本轮另补正式 create_app/lifespan/真实 Session/PG 路径，保留全部这些被测业务逻辑，只替换模型输出来源。
4. 最新 observe 仓库测试确实调用实际 observe 节点，但其执行依赖是空目录。独立补测增加“任何 Executor 属性访问均失败”的守卫，并实际用 add_messages 两次合并结果，验证无 Handler 入口、无计数增长且最终只有一条对应 ToolMessage。
5. 未修改业务、仓库测试、配置、依赖、SQL或冻结文档。外部摘要检查覆盖 **108** 个源码/测试/脚本/SQL/依赖/配置示例等文件，测试前后相同。主 Agent 仍可用其独立摘要再次核对。

本轮只新增本报告。既有 general.py、三份旧文档删除、D01 差异、独立 Bridge 文件和协调文件保持原归属；未调用 Bridge/其他会话，未 Commit/Push，未开始 04。

## 3. 六个 Task 结果

| Task | 实际实现与设计符合性 | 测试及覆盖评价 | 遗留与验收判断 |
| --- | --- | --- | --- |
| 3.1.1 Metadata/Registry | models.py 唯一 Metadata/Definition/View，registry.py 注册检查、重名拒绝、启动 freeze；发现视图无 handler，稳定按名称排序，Agent/scope/enabled 同时过滤 | 仓库治理测试及独立 disabled/unknown/disallowed 零执行补测；注册校验源码核查，未机械穷举所有元数据组合 | 核心要求通过，无独立新增功能缺陷 |
| 3.1.2 过滤与模型绑定 | Order select_tools 按 query_spec 取单工具交集；Gateway 绑定完整参数 Schema；execute_query 用同一名称/version和精确参数限制 | 独立用真实 ChatOpenAI + MockTransport 并发捕获实际请求 JSON，逐份对比正式 get/list 完整 parameters；共享模型无原地 tools 污染。真实专项另证原生调用 | 通过；HTTP SDK 替身只承担传输载荷验证，未冒充真实供应商 |
| 3.2.1 Policy/Executor | Policy 三态，单call/批次共享执行函数；真实尝试前复检并先计数，handler 只收 typed args及 user/task/run；只读白名单有限重试，超时不重试，取消传播 | 治理测试及独立一次验证计数、全批 Policy 预检、最小上下文、批次取消/超时、精确目标补测通过；累计预算继承由 Runtime 和真实 Order 主图测试覆盖 | 行为通过；03-QA-001 为数据层反向依赖治理契约的问题，不是策略绕过 |
| 3.2.2 工具消息与治理 | 原生批次完整校验、最多4calls、串行失败截断、每call稳定 ToolMessage；execute 保存结果，observe 只映射 | 独立重复/缺ID/超限/invalid_tool_calls整批零执行；取消停止后项；原args和规范参数分离；observe两次合并不增消息/计数 | 行为通过；03-QA-002：记录未显式保存 origin/current run |
| 3.3.1 最小模拟订单事实 | 003 表/索引、Decimal、参数化 owner SQL、Service 归属复核、双用户五条固定时间种子、幂等且保留状态；真实库版本/checksum一致 | 真实库约束、本人/异主/不存在/分页/空页、重复种子和退款标记恢复；独立关闭真实池→完整工具/专业图技术失败通过 | 功能通过；03-QA-001 违反明确的数据层依赖方向 |
| 3.3.2 OrderAgent 查询 | 实际七节点编译、受限原生工具循环、facts固定摘要、主图唯一公开出口；退款/知识仍不可用 | 受控主图缺参同Task新Run及累计预算；正式HTTP/lifespan/真实Session/PG；真实TCP断开仍完成；真实DeepSeek+PG get/list通过 | 功能通过；不将内存记录认定为持久恢复或副作用幂等 |

## 4. 实际命令及结果

所有 Python 均为项目 `.venv\Scripts\python.exe`。以下 `QA_TMP` 仅是文字缩写，实际目录为：

`C:\Users\15294\AppData\Local\Temp\agent03-independent-20261112`

| 实际命令/入口 | 本轮结果 | 说明 |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe C:/Users/15294/AppData/Local/Temp/agent03-independent-20261112/run_audit.py` | exit 0；内层 `python -m pytest -q`：**130 passed in 46.29s** | harness先核实专用库及迁移checksum，进程内从Settings给子进程传递测试库环境；无凭据出现在命令参数或输出。保存 full-pytest.txt |
| `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q C:/Users/15294/AppData/Local/Temp/agent03-independent-20261112/test_independent_03.py` | exit 0；**15 passed in 10.96s** | 当时文件包含15项；默认 fd 捕获及仓库脱敏插件均保留 |
| `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q C:/Users/15294/AppData/Local/Temp/agent03-independent-20261112/test_independent_03.py::test_formal_real_tcp_disconnect_keeps_order_query_alive` | exit 0；**1 passed in 7.96s** | 随后新增真实TCP场景，只执行新项；现在外部文件包含16项，未谎称运行过最终文件的一次16项整套命令 |
| `.\.venv\Scripts\python.exe -m scripts.verify_03_real` | exit 0；PG身份/schema/owner/空页及 REAL_MODEL_PG_GET_OK、REAL_MODEL_PG_LIST_OK | 每种查询model_attempts=2/tool_attempts=1；本轮合计4次真实模型尝试、2次真实只读工具尝试 |
| `.\.venv\Scripts\python.exe -m ruff check .` | exit 0；All checks passed | 未使用 --fix |
| `.\.venv\Scripts\python.exe -m ruff format --check app tests scripts` | exit 0；101 files already formatted | 未执行format写回 |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | exit 1；6 files would be reformatted, 148 files already formatted | 既有Markdown代码示例格式遗留，见下文 |
| `.\.venv\Scripts\python.exe C:/Users/15294/AppData/Local/Temp/agent03-independent-20261112/final_checks.py` | 最终exit 0；行集/schema/108文件相等，PG17确认；两处设计偏差探针 | 此脚本捕获全仓format输出并只显示文件定位，验证依赖及私有记录字段 |

**执行工具本身的失败与产品结果分开：**首次 final_checks.py 捕获 Ruff 的中文输出时，Windows 默认 GBK 解码导致子进程读取线程 UnicodeDecodeError，外层安全边界给出 TypeError 类别并退出1。该轮已先输出行集/文件相等，未修改被测工程；随后仅修正仓库外脚本为显式 UTF-8 解码，最终命令退出0。该失败不是 pytest 或产品失败。本轮不存在“failed 会话却沿用其通过结论”的情况。

完整 pytest 的真实资源项无跳过；未安装/升级依赖，依赖清单未变，未额外运行 pip check。未开展供应商网络中断、数据库服务停机、应用库演示、跨进程持久恢复或 04/05 能力测试；这些均不作为已验证事实。

## 5. D03 13.2 验收与覆盖矩阵

表中 T 为仓库 `tests/test_tool_governance.py`，O 为 `tests/test_order_graph.py`，P 为 `tests/test_order_postgres.py`，Q 为外部 `test_independent_03.py`。测试名中的参数化场景计入实测数字。

| # / 设计要求 | 用例/独立可观察证据 | 类型 | 真实资源 | 结果与覆盖评价 |
| --- | --- | --- | --- | --- |
| 1 Registry/完整Schema | T registry_filters…；Q actual_sdk_schema_binding_isolation；源码register/freeze/list；实际请求JSON完整parameters相等、各请求只有各自一个工具 | 单元/SDK传输集成/审查 | 真ChatOpenAI，HTTP受控；专项真模型 | 通过；过滤和实际绑定均验证，非仅名称列表 |
| 2 曝光≠执行 | T enforces_scope…；Q disabled_unknown_and_disallowed_zero；拒绝次数及handler记录均0，安全code不披露隐藏目录 | 治理边界 | 受控handler | 通过；包含未知、禁用、不在允许集合和缺scope |
| 3 精确目标 | O cannot_broaden…；Q precise_target四场景：get→list、list→get、limit5→20、offset0→1；均rejected/工具0/不再模型调用 | 实际专业图 | 受控模型/仓储 | 通过；原get改订单ID亦由仓库用例覆盖 |
| 4 handler最小边界 | T enforces_scope…；Q typed_once_preflight_all_and_minimal_context；三个call各验证一次，重试复用typed，handler字段集合恰user/task/run | 执行集成 | 受控handler | 通过；独立模型validator计数，非只读类型注解 |
| 5 身份/owner | T身份注入；P真实A查B和不存在均OrderNotAccessible；Repository静态owner参数化SQL，Service再次核对owner且View无owner | 真实DB/审查 | PG17测试库 | 通过；真实owner隔离及安全结果；未声称生产认证 |
| 6 Policy三态 | T高风险approval_required/approval_not_available/attempts0；正常ALLOW、scope/args DENY；observe映射审批为failed源码 | 治理/审查 | 受控handler | 通过；没有等待或聊天批准接口 |
| 7 尝试/累计预算 | T重试2次/限额1时不再重试；Q typed_once…；O clarification…累计model4/tool1；Runtime seeded_tool_budget…累计12时新Run模型不再启动 | 图/Runtime/治理 | 受控模型 | 通过；拒绝/后续not_executed为0，成功/失败/重试先计数 |
| 8 批次/配对 | T preflight_then_serial…；Q whole_bad_batch_zero_execution四场景；Q typed_once…初始Policy检查包含a/b/c且handler启动前完成；原args保留、规范args分存；配对原id/name | 实际图/执行集成 | 受控模型 | 通过；结构错误整批0，可关联策略错误逐call闭合后终止 |
| 9 超时/取消/重进 | T timeout…；Q batch_cancel_and_timeout_stop_next；Q observe_reentry_reducer_is_idempotent；取消只启动首handler，超时只1次，observe不访问Executor且Reducer后ToolMessage恰1条 | 异步执行/实际节点 | 受控阻塞handler | 通过；不以直接重复格式化冒充恢复执行，跨进程resume留04 |
| 10 表/种子 | P；test_postgres真实重入/checksum/失败回滚；前后完整行集摘要相等，schema1/2/3 checksum相符，PG17确认；numeric(12,2)、负金额约束、固定样本和时区源码 | DB集成/审查 | PG17测试库 | 通过；种子重跑0、退款标记保持并恢复，非重建库 |
| 11 订单事实/DB故障 | P本人get/list/空页/异主/缺失；Q real_closed_pool_is_technical_not_empty：关闭实际池后完整Repository→Service→Executor→图failed/order_query_unavailable、attempts2、无facts/旧data；O候选伪造不公开；专项facts对源行 | DB/实际专业图 | 真PG/真实关闭的池；模型受控及真实专项 | 通过；技术失败不是“订单不存在”或空列表；未通过破坏数据库服务制造故障 |
| 12 专业主图/公开出口 | O clarification…；test_graph_protocol real_topology_scope_settlement_and_no_post_end_update；Q formal_http_real_lifespan_pg_resources；Q formal_real_tcp_disconnect_keeps_order_query_alive；Response唯一、done一次、父消息无工具、断开后查询继续且订阅释放 | 主图/正式HTTP/TCP | 真PG/Session/正式lifespan/真实本地TCP，模型受控 | 通过；没有替换Runtime/Session/订单图/lifespan；SDK客户端与池均关闭 |
| 13 真实模型+PG | 本轮显式verify_03_real，get a-001/list5；绑定Schema由Q真SDK请求验证；专项实际工具消息存在、get/list facts逐项与Service真实源行一致 | 外部集成 | 真DeepSeek deepseek-flash + 真PG测试库 | 通过；每种2模型/1工具；这是专业图专项，非真实模型全HTTP端到端声明 |
| 14 后继未实现 | test_graph_protocol actual_compiled_skeletons…仍测Refund/Knowledge；正式main仅注册两个读取工具；02 Runtime/http全量回归含真实TCP、首次迭代/响应失败清理、容量/去重/互斥/uncertain/关闭 | 回归/源码审查 | 受控模型；TCP真实 | 通过；无审批/退款/RAG/Store/持久恢复假完成 |

该矩阵判定的是核心可观察行为。03-QA-001/002 是另列的设计符合性问题，不能用全绿矩阵或 130 passed 隐去。

## 6. 真实库保护、快照及清理

连接前：Settings 的专用测试目标经 validate_test_target 校验，连接后核对 current_database/current_user 为 **agent_demo_test / agent_test**；迁移版本恰 `[1,2,3]`，checksum逐项等于本地SQL SHA-256。后续只用此专用库；没有连接应用库进行测试或演示。最终另确认 server_version_num 主版本为17。

外部 run_audit.py 对 `sessions`、`demo_orders` 各执行完整 `SELECT * ORDER BY 1,2`，对 Python返回的完整行集序列计算SHA-256；迁移表包含 version/checksum/applied_at 的完整序列另取摘要。没有只比较 count。

| 检查点 | sessions | demo_orders | 完整行集/迁移摘要 |
| --- | --- | --- | --- |
| 回归前 before.json | 0 | 5 | 基准 |
| 全量回归后 after-full.json | 0 | 5 | 全部相等 |
| 补测、TCP和真实模型后 after-final.json | 0 | 5 | 与基准全部相等 |

既有真实 Session 测试创建UUID随机用户/会话，并在finally精确删除自己两名随机用户的行；订单测试临时改a-001的退款标记，在finally按原值恢复，非法金额插入回滚。独立HTTP和TCP使用 `qa03-` / `qa03-tcp-` 加UUID的新conversation，只按 **user_id+该唯一conversation_id** 删除自身Session。固定五条订单及其所有字段前后相等，没有删除或重写样本订单。

完整既有迁移测试调用幂等 apply_migrations 入口：当前001–003已存在且checksum一致，故无新版本应用；其临时下一编号建表/错误SQL在失败事务中全部回滚，并检查无探针表、无新增迁移记录。**本轮没有执行成功的新版本迁移或结构升级**。这一区分如实记录，未把运行迁移测试描述为完全没有触达迁移入口。

外部可核查文件：run_audit.py、test_independent_03.py、final_checks.py、before.json、after-full.json、after-final.json、protected.json、full-pytest.txt、full-format.txt，均在上述 QA_TMP。快照只保存摘要及行数，不存数据库行原文或秘密。外部临时证据保留供复核，没有删除会话审计。仓库内的持久交付为本报告。

## 7. 问题清单

### 03-QA-001 · P2 · 数据层反向依赖工具/Graph/Runtime 契约

**已确认，新增设计偏差；不是数据库查询功能失败。**

- 设计依据：[D03 Task 3.3.1 前置/后继](../03-tool-governance-detailed-design.md:777)明确“数据层本身不反向依赖工具或图”；[第11节](../03-tool-governance-detailed-design.md:856)再次要求“数据服务不引用工具/图”。
- 代码位置：[app/domain/orders.py:12](../../app/domain/orders.py:12)直接导入工具层 ToolTransientError/ToolUnavailableError；在 :74/:76 把psycopg异常转换成工具层异常。[app/tools/models.py:11](../../app/tools/models.py:11)又导入 Graph ExecutionContext、Runtime RunLimits/RunUsage/RunScope。
- 稳定复现：执行外部 final_checks.py；AST检查输出 `DOMAIN_IMPORTS_TOOL_MODELS True`。直接导入订单数据模块的依赖链实际加载 Graph contracts 与 RunScope。源码导入本身已足以证明反向依赖，不以当前是否产生循环为判断前提。
- 预期：Domain/Repository用自己的领域/数据访问异常表达可重试或不可用；工具薄适配负责转换到治理层异常。实际：数据模块直接依赖上层工具契约，并传递引入Graph/Runtime。
- 影响：当前130+16测试及真实查询均通过，没有观察到循环导入、数据泄漏或错误分类失败；但后续04在订单事务/退款域复用数据层时，会继续携带工具执行层依赖，违反冻结的分层边界。
- 建议：将数据访问故障类别放在数据/领域边界，在订单工具适配内转换为现有治理异常，保持Executor安全重试和错误code行为；不需要建设新通用异常平台。修复后复核关闭池/不可重试技术失败及真实查询。由主Agent裁决并组织实现，QA本轮未修改。

### 03-QA-002 · P3 · 私有调用记录缺少显式 origin 和当前 run 关联

**已确认，新增设计偏差；不影响本轮普通查询和观察重进结果。**

- 设计依据：[D03跨阶段最终接口收敛记录:956](../03-tool-governance-detailed-design.md:956)要求call_records记录 origin、安全摘要、状态/code/effect_status、当前run、execution_id、attempts及累计用量。
- 代码位置：[订单builder:245](../../app/graph/specialists/order/builder.py:245)只写入call、normalized_args、result；[ToolExecutionResult:119](../../app/tools/models.py:119)内也无origin/run关联字段。
- 稳定复现：外部final_checks.py调用实际execute_order产生一次成功原生工具链，再检查call_records。输出顶层键恰 `call/normalized_args/result`；结果字段包括状态、execution_id、attempts和run_usage，但 `RECORD_ORIGIN_PRESENT False`、`RECORD_CURRENT_RUN_PRESENT False`。后者递归比较记录的标量值，不把名为run_usage的键误认为当前run值。
- 预期：保存记录时明确保留可信origin及当前run关联；实际：只能回到外围request上下文推断本轮run，origin由现有03固定模型入口隐含。
- 影响：03每次普通专业调用重建私有历史，因此当前可从周边状态推断，observe也不依赖这两个字段。后续04引入node/model混合入口和跨Run快照时，独立检查记录的来源及尝试归属不够直接；不能拿当前记录当完整的后继审计关联。
- 建议：在现有记录构造处保存可信origin/run_id，不从raw_args取值，不把这些私有记录新增到公共SSE；用保存结果重进用例检查关联保持即可。无需增加数据库或新审计系统。

本轮P0：0；P1：0；P2：1；P3新增：1。上述两项均为源码/探针确认问题，不是“待验证猜测”。

## 8. 其他设计差异、限制与风险

- Repository与Service合并在domain/orders.py，七节点/Prompt集中在订单builder，而设计文件规划曾列独立repository/state/nodes/prompt文件。职责仍能辨识，未发现第二执行入口；这些文件布局选择本身不另列Bug。数据层反向依赖则是明确契约，已单列03-QA-001。
- 实际迁移003符合“下一未占编号”，不是偏差；normalized_args作为私有结果扩展保留规范参数，原生raw_args未被改写，亦不属于错误。
- 既有P3-01六份format文件为D01、D02、D03、D04、D05和history/04-1-order-service-design；本轮未修正文档示例。全仓format退出1不应描述成所有检查通过。
- RISK-02-CRED历史暴露和配置密码复用按用户已接受遗留保留；未打印实际凭据/连接串/headers/原始敏感异常，未换密，也不以该既知风险重新阻塞03。
- 未配置资源时的明确不可用、内存Checkpointer、单进程Run/订阅/去重、无事件重放均为既有允许限制；Session持久绑定和call_records不是Checkpoint持久恢复。
- 04 PreparedToolAttempt/VerifiedApproval/审批记录/退款事务及幂等、05 RAG/Store/记忆均未实现且不要求本轮完成。没有因这些后继能力缺失判03失败。
- 独立TCP补测证实正式Order查询不依赖SSE订阅存活；没有将“TestClient正常读完流”代替网络断开证据。真实供应商专项只覆盖专业图，受控模型正式HTTP/TCP补测覆盖应用装配，两类证据界限明确。

## 9. 交回建议

03核心功能和14项行为门禁已独立核实，测试与真实资源证据足以支持进入主Agent验收复核。**当前结论为有条件通过，不作完全符合D03的无保留声明。**请主Agent对03-QA-001/002逐项作整改或明确接受决定，必要修复后按受影响范围独立复测，再由用户决定正式验收、归档及是否切换04。

本轮审查到此结束；不自行修复，不变更主Agent协调文件或阶段状态。
