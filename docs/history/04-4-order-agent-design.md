# 4.4 OrderAgent 查询子图与首业务联调——详细设计及三级执行任务（待审核）

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**设计待审核，未开发执行、未测试或真实联调**。编制日期：2026-11-08。

依据：[04 统一计划及一致性审核](04-stage-execution-plan.md)、[4.1](04-1-order-service-design.md)、[4.2](04-2-tool-registry-design.md)、[4.3](04-3-tool-execution-design.md)、[03 架构](03-stage-detailed-design.md)、[01 协议](01-stage-detailed-design.md)。本环节只查询，不实现取消/退款/支付/RAG。

## 1. 目标、范围及依赖

建立首个以真实 PostgreSQL 本地模拟业务为依据的专业 Agent。主图由 Supervisor 派 ORDER_QUERY，OrderAgent 发现并调用允许工具，生成有业务事实支持的 SpecialistResult，经主图唯一 Response 和 Runtime/SSE 输出。

实际依赖01契约/公共协议、02身份/池/仓储、03 Gateway/任务/快照/预算/Broker及4.1～4.3验收。仅有这些设计文档不能完成集成。OrderAgent 不持有连接/Repo，不直接调用 OrderService、不自行认证/调度/审批、不创建替代 Budget 或 SSE。

ORDER_CANCEL 虽归 ORDER，但在05前必须明确 unavailable，不因注入查询子图就宣称该任务可执行。wrapper/子图入口都按任务白名单，不把取消请求偷偷转换成查询成功。

## 2. 组件、目录及调用图

```text
app/graph/specialists/order/
  state.py          # 扩展现有 SpecialistState
  builder.py        # 启动编译，依赖注入
  nodes.py          # 初始化、模型、执行、澄清/收敛
  router.py         # 有限边
  tool_messages.py  # Outcome -> 私有 ToolMessage
  result_builder.py # 依据观察事实生成 SpecialistResult
app/agents/prompts/order.py
app/tools/implementations/orders.py  # 4.3拥有，仅复用
tests/test_order_agent.py
tests/integration/test_order_agent_engine.py
```

拓扑：START→prepare→model→校验回合；有 tool_calls→execute_batch→model；有合法完成意图→finalize；缺字段→clarify；业务拒绝→reject；不可恢复错误→fail；各正常出口写 result→END。专业子图不写父图 messages 或公共 done。

builder 接受 Gateway、Registry/Discovery、Executor、可信调用上下文提供入口；资源在应用启动编译注入，节点不创建新模型/池/线程。Gateway 接受完整工具定义且返回原生 ToolCall，不把工具调用执行委托给绕过 Executor 的框架 Agent。具体 LangChain 绑定接口未来按本地安装版本验证。

可信运行 context 通过03的Runtime调用配置提供，验证与 request.context/task_id 一致，不放进模型可填字段。节点只使用其引用，不在State持久化凭据或可调用对象。

## 3. 专业私有 State

复用 SpecialistState 的 request/messages/selected_tools/result，不另复制身份和workflow字段。

| 字段 | 类型/写入方/规则 |
| --- | --- |
| request | SpecialistInput，只读，wrapper创建，关联以当前run为准 |
| messages | 私有消息Reducer；prepare放必要公开上下文，model放AI工具消息，execute放配对ToolMessage；不回灌父历史 |
| selected_tools | 工具名列表；初始discover_tools，只有可信DisclosureDelta可扩展；当前任务重新创建 |
| registry_revision/schema_hashes | 记录披露快照/摘要；Schema按注册快照重建，不重复持久化全定义 |
| pending_calls | 当前模型回合的有序调用列表；由模型适配后验证；批次结束清空 |
| tool_observations | 按call_id记录规范结果、工具版本、关联和数据；Executor输出写入，不由模型生成 |
| finish_intent | 可空的模型完成/澄清建议；每回合覆盖，程序校验，不直接成为回复 |
| local_turn_count/format_retry_count | 本次子图硬保护，不能替代03持久workflow预算 |
| result | SpecialistResult或空，只由确定性result_builder写入 |

观察保存权威规范数据；ToolMessage仅有界模型投影（如前10条商品+总条数+projection_truncated），两者不能颠倒。每任务最多保留本次实际调用预算允许数量，绝不把全库/全部历史塞入Checkpoint。04无新增Agent数据库表，快照和公开结果沿用03的保护和保留策略。

## 4. 模型回合与完成意图

Gateway.invoke(call_context,model_request) 的 model_request 增加 bound_tool_definitions/工具调用选项；Gateway仍唯一计量入口，支持原生ToolCall结果。初始只绑定discover_tools，工具描述/Schema来自Registry，不在Prompt硬编码参数副本。

模型回合规范化为 OrderModelTurn：

- tool_calls：原生调用列表，content中的自由文字不作为公开答案。
- 或 finish_intent：严格JSON的 action=complete|needs_input|reject、query_kind=detail|list|logistics|combined、observation_refs、允许的missing_fields。

两者不能同时作为执行决定；native调用存在时按调用分支处理，不解析隐藏自由文本指令。无调用时严格校验完成意图，格式失败最多一次纠正，仍失败则退出；纠正走Gateway计量。此方案不假定供应商能同时支持工具绑定和另一套强制结构化输出API，provider适配在联调时验证。

finish_intent只是建议，不携带可信facts/金额/summary。complete要求引用当前run/task内成功观察，query_kind与工具/目标一致；明确订单ID不能被其他订单结果替代。模型没有调用工具便声称查到订单必须拒绝。reject须有实际Policy/Domain拒绝证据，不能让模型臆造资格。

needs_input只允许业务缺字段order_id、time_range、time_zone等已定义槽位；问题由安全模板根据缺失项生成，不让模型索取user_id、凭据或审批。列表本来不要求order_id，不能机械要求补订单号。相对时间无可信用户时区时先澄清，不能用服务器/聊天环境时区猜测。多个候选订单只使用已查到的本人候选。

## 5. 完整执行流程

1. wrapper校验ORDER_QUERY后构造独立私有State，prepare核对可信context/任务、清空旧观察/工具集合；不能从上次workflow继承披露。
2. 根据用户权限和任务取得简化目录，初始绑定discover_tools；模型经Gateway作决定。
3. 验证每批最多4个唯一ToolCall ID；固定本回合绑定集合，不按同批新披露追认。
4. execute_batch串行调用Executor。每个可识别调用形成一个ToolMessage，失败/拒绝也配对。可信Delta更新下一轮selected_tools和Schema摘要；业务结果保存观察。
5. 全批配对完成后才能再次调用模型；最新selected集合完整Schema与执行集合同时重建。重复call_id同参复用观察，不再调Service；不同参冲突则协议失败。
6. 在03剩余预算内继续；本地模型回合建议最多8轮（不含Gateway内部重试计次差别），非法参数/格式可纠正次数明确有界，不能用工具拒绝免费无限循环。
7. 完成意图通过程序校验后，result_builder从观察组织facts和安全summary；缺输入保留entities进展，拒绝/失败安全结束。
8. wrapper只把SpecialistResult增量映射到父图。主图Aggregator/Clarification→Response，Runtime持久终态→SSE/查询。

订单商品名、物流说明等查询数据是资料，不是系统规则或授权；Prompt明确不能执行数据内指令。真正的调用权由Policy及绑定集合决定，数据库文本不能让模型增加新工具。

## 6. 结果组织、查询规则及异常

完成summary使用确定性模板，**不直接采用模型自由生成的订单业务结论**。模型负责理解/工具选择/完成建议，事实取自tool_observations；金额/状态/物流不重算。回复标明本地模拟数据。

facts建议形态：query_kind、data_origin=local_simulation、observations=[{call_id,tool_name,data}]。仅合并当前查询相关、已成功且授权的观察，拒绝/未知结果不能混为成功。详情按订单ID，列表展示前若干行并明确“本页/还有更多”，不把空页当全用户没有订单；游标只在有真实next_cursor时保留。

多查询组合中，用户明确要求的目标必须均有对应可用观察；不能挑选成功的一项而忽略尚未解决的查询失败并宣称全部完成。参数纠正后已有覆盖同一目标的成功结果可以替代早期无效尝试；仍有目标失败则按failed/rejected的真实原因结束，可保存已确认的局部facts但不输出整体成功。当前首版不增加部分成功状态，后续若需要独立部分交付应另行设计公共语义。

summary受现有4000字符限制；长结果用有限摘要和真实数量，facts保留有界规范数据；公开结果数据裁剪不得悄悄改变总额/has_more。来源为空，订单事实不是RAG文档，不能虚构SourceReference。

| 情况 | 专业结果 | 主图/Runtime结果 |
| --- | --- | --- |
| 查询成功含空列表/未发货 | completed，真实facts | completed/answered，不假称已发货 |
| 缺业务信息 | needs_input，缺字段/问题/候选进展 | 澄清token+done(completed,needs_input) |
| 订单不存在或他人 | rejected，统一不可见说明 | 安全拒绝token+done(completed,rejected) |
| scope/Policy拒绝 | rejected；无额外查询泄漏 | 同上 |
| 连接/查询超时、数据不一致 | failed，安全error | error+done(failed) |
| 非法参数可纠正 | 配对错误后最多限定纠正；缺槽则needs_input | 不把错误当查询成功 |
| 预算耗尽/失权/协议错误 | failed或交Runtime安全退出 | 按03收敛；未知状态不假失败 |
| 04没有审批基础的请求 | failed/approval_unavailable | 不发假approval_required |
| 取消/退款进入查询子图 | unavailable失败 | 不执行、不返回模拟成功 |

本环节不生成公共tool事件或done，Executor发可信内部进度，03 Projector/Broker统一输出。正常一次done、断开不影响执行、重连先注册后查和重复受理JSON均复用03，不另建HTTP路径。

## 7. 核心方法

```text
build_order_query_graph(gateway,registry,executor,context_provider) -> compiled_subgraph
prepare_order_state(request,context) -> private delta
invoke_order_model(state,context) -> private delta
execute_tool_batch(state,context) -> outcomes/messages/disclosure delta
validate_finish_intent(state,intent) -> validated action
build_specialist_result(request,observations,action) -> SpecialistResult
```

所有工厂/节点不保存用户可变成员。业务调用只能经Executor；结果构造器是纯函数，不读库、不调用模型。

## 8. 三级任务及具体开发计划

### 4.4.1 专业State、入口及依赖
- 目标/功能：固定ORDER_QUERY专用接入，不扩展写业务。
- 步骤：扩展SpecialistState→定义OrderModelTurn/FinishIntent→校验可信运行context→注入Gateway/Registry/Executor→builder任务白名单。
- 文件/接口：order/state.py、builder.py、contracts相关专用模型；build_order_query_graph。
- 前置：01契约、03wrapper/Gateway接口、4.2/4.3共享契约；后继：4.4.2～4.4.5。
- 未来测试：错Agent/Task/run、ORDER_CANCEL、跨任务工具残留、全局单例污染。
- 完成/交付：可编译专业骨架，生产未就绪依赖失败而非用Stub成功。

### 4.4.2 目录、披露及动态绑定
- 目标/功能：将4.2发现真正接入每轮模型定义。
- 步骤：初始简化目录/发现Schema→经Executor发现→应用可信Delta→重建完整bound definitions/current set→检查revision/限额。
- 文件/接口：order/nodes.py、Prompt、4.2 model definitions、Gateway的工具参数扩展。
- 前置：4.4.1、4.2.4/4.2.5、4.3.3；后继：4.4.3。
- 未来测试：下一轮模型确有Schema、隐藏工具不绑定、同批追认拒绝、过期权限复检。
- 完成/交付：目录到执行集合闭环，无裸模型旁路。

### 4.4.3 多轮调用与消息配对
- 目标/功能：有界循环与私有工具历史正确。
- 步骤：解析native calls→唯一ID/每批上限→串行Executor→观察入State→安全投影为ToolMessage→全批配对再循环→重复ID处理。
- 文件/接口：nodes.py、router.py、tool_messages.py；execute_tool_batch。
- 前置：4.4.2、4.3.5/4.3.6；后继：4.4.4/4.4.5。
- 未来测试：成功/拒绝/参数错误均配对，多调用序列、重复ID、缺ID和工具内容注入、循环预算退出。
- 完成/交付：无孤立ToolMessage，无绕Policy直接调Service，无无限回合。

### 4.4.4 澄清与权威结果构造
- 目标/功能：LLM建议不能伪造订单结果。
- 步骤：校验FinishIntent/观察引用→限定缺槽问题→按模板render真实观察→控制summary/JSON尺寸→构造四类SpecialistResult。
- 文件/接口：result_builder.py、nodes.py；validate_finish_intent/build_specialist_result。
- 前置：4.4.1/4.4.3、4.1 DTO；后继：4.4.5/4.4.6。
- 未来测试：无工具却声称成功、错订单/陈旧观察、模型编造金额、空页、未发货、needs_input实体续接。
- 完成/交付：facts/summary来自查询，ID关联正确，无假RAG来源。

### 4.4.5 主图、Runtime与公共事件接线
- 目标/功能：专业输出进入既有真实Engine生命周期。
- 步骤：启动注入实际子图→父子映射→唯一Response→工具安全进度→终态/查询投影→保持生产无Stub。
- 文件/接口：主builder、main装配、order builder；复用03 Projector/Broker，不新建协议。
- 前置：03实际验收、4.4.4、4.3.7；后继：4.4.6/4.4.7。
- 未来测试：父图无私有工具历史，普通续接新run，公开无敏感参数，done一次，ORDER_CANCEL仍不可用。
- 完成/交付：实际图/Runtime接线，状态查询与结果一致。

### 4.4.6 真实数据库与故障集成
- 目标/功能：证明首业务不是Stub/Mock数据。
- 步骤：独立PG迁移/种子→运行角色→真实Service/Executor/子图→受控模型覆盖路径→预算/权限/连接/断开/迟到故障→核对数据库事实。
- 文件/接口：integration/test_order_agent_engine.py，复用4.1 fixtures和03生命周期测试。
- 前置：4.1～4.3验收、4.4.5；后继：4.4.7。
- 未来测试：A查B拒绝、状态/时间/分页/物流、缺信息/重试/unknown usage、慢消费者、状态查询。
- 完成/交付：真实PG关键场景实际通过；默认测试无付费请求；无业务状态写入。

### 4.4.7 真实模型与首业务联调
- 目标/功能：实际模型调用链与消费接口形成首个专业业务闭环。
- 步骤：显式配置模型→确认native工具绑定/结构化路由能力→Apifox受控身份→真实Supervisor/OrderAgent/Gateway/Executor/PG→多轮发现/查询→SSE/重复JSON/结果查询→记录供应商/用量质量/限制。
- 文件/接口：联调说明、消费示例及真实调用报告，不把付费联调加入默认pytest。
- 前置：4.4.6、模型配置、01/02/03实际验收和公开接线门禁关闭。
- 未来测试：详情/列表/物流、两轮缺字段续接、跨用户/无结果、实际Schema绑定、公开回复与源行一致。
- 完成/交付：真实模型和PG联调证据齐全；未配置或未调用明确未验收；05取消/06退款/07知识不标完成。

## 9. 顺序与验收

4.4.1→4.4.2→4.4.3→4.4.4→4.4.5→4.4.6→4.4.7。模板/纯结果测试可与循环准备并行，共享State/Gateway接口冻结后串行接线。最终验收见统一计划，不重复为等价边界增加测试。

需确认：严格FinishIntent且确定性事实回复、初始仅发现工具、每批4调用/本地8轮、结果投影前10商品和128KiB上限、ORDER_CANCEL保持不可用。以上为本阶段建议，审核前不启动开发或联调。
