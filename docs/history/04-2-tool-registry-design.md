# 4.2 Tool Registry 与渐进式发现——详细设计及三级执行任务（待审核）

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**设计待审核，未开发执行、未测试验收**。编制日期：2026-11-08。保存文档不等于审核通过；审核通过后才改为“设计已确认，待开发执行”。

依据：[04 统一执行计划与一致性审核](04-stage-execution-plan.md)、[4.1](04-1-order-service-design.md)、[4.3](04-3-tool-execution-design.md)、[4.4](04-4-order-agent-design.md)、[03 架构](03-stage-detailed-design.md)。本轮只编写 Markdown；不扫描仓库或运行任何开发验证。

## 1. 目标、范围和架构

建立应用启动时注册、运行时只读的工具目录，按可信 Agent/Task/用户权限过滤，再渐进披露完整 Schema。目录不是权限凭证，发现不是执行，模型拿到 Schema 后调用仍经过 Policy。

Registry 不访问订单库、不管理审批、预算或用户任务状态。V1 不新增工具数据库、远程工具市场、动态上传代码、热更新管理 API、向量化工具搜索。工具管理是启动装配中的 register/get/list/freeze，后续版本由部署更新。

链路：启动 ToolDefinition→Registry.freeze→基于可信上下文产生简化目录→模型调用 discover_tools→Executor/Policy→DiscoveryService→可信 DisclosureDelta→下一模型轮绑定完整 Schema＋同步 selected_tools→业务 ToolCall 再经 Executor。

业务模型和函数已经规划但未实现，本文依赖的是设计接口，不假装现有工具包占位文件可用。

## 2. 数据契约

### 2.1 ToolMetadata

| 字段 | 类型/约束与作用 |
| --- | --- |
| name/version | 唯一稳定工具名（小写字母、数字和下划线，1～64字符）、显式契约版本；客户端不能选择历史版本 |
| description/catalog_description | 完整功能描述和简化目录描述，有长度上限；不含用户数据、密钥或系统指令 |
| allowed_agents/allowed_tasks | 非空固定 AgentType/TaskType 集合，任务须属于对应 Agent；只作允许范围 |
| required_scopes | 全部必须具备的有限 scope 集合，不是任一满足 |
| risk | LOW/MEDIUM/HIGH/CRITICAL；risk 与是否需要审批分别判断 |
| approval_required | bool；不能由模型设置或覆盖 |
| side_effect | bool；04 活跃业务工具均 false |
| idempotent/retry_safe | 幂等声明和是否允许安全重试；声明不是业务去重实现 |
| timeout_seconds/max_attempts | 正数调用上限和次数上限，最终还受 03 剩余预算限制 |
| tags/enabled | 服务端维护的领域/能力标签和启用状态 |
| schema_version/schema_hash | 参数/结果契约版本和确定性摘要，绑定本次注册定义 |

ToolDefinition 组合 metadata、args_model、result_model、handler。参数 Schema 来自同一 args_model 的 JSON Schema，不手写第二套规则；结果模型约束标准化业务数据。handler 不进入模型定义或 Checkpoint。

RegistrySnapshot：不可变 revision、definitions 索引。revision 随部署/定义摘要变化，可在私有执行记录保存，但不公开全部注册信息。禁止同名覆盖、别名悄悄指向新实现或共享可变 metadata。

ToolCatalogEntry：name、catalog_description、tags、风险/只读标识。ToolModelDefinition：name、description、完整 parameters JSON Schema；不含 handler、凭据、Principal、连接。权限元数据不由模型参数传入。

### 2.2 本阶段活跃定义

| 名称 | 参数模型 | 结果 | Agent/Task/scope |
| --- | --- | --- | --- |
| orders_get_detail | order_id | OrderDetail 的 JSON 投影 | ORDER/ORDER_QUERY/orders:read |
| orders_list | status、created_from/to、page_size、cursor | OrderPage | 同上 |
| orders_get_logistics | order_id | LogisticsView | 同上 |
| discover_tools | mode、names 或目录游标 | 允许目录/完整 Schema | 各已装配专业 Agent/任务；按可信候选过滤 |

订单读取含用户业务信息，建议 risk=MEDIUM、approval_required=false、side_effect=false、idempotent/retry_safe=true。发现工具 risk=LOW、只读、不需要业务查询权限，但其返回目录必须按用户全部 scope 过滤；无 orders:read 不返回订单工具。

V1 不注册可执行取消/退款/支付工具。可以在未来部署新增定义，但 enabled=false 的工具没有目录、Schema 和执行权限；Registry 不能用空成功 handler 代替未实现能力。

## 3. 类、接口及文件规划

```text
app/tools/models.py             # Metadata/Definition/Catalog/Disclosure 契约
app/tools/registry.py           # ToolRegistry 与不可变快照
app/tools/discovery.py          # 过滤、简化目录与 Schema 披露
app/tools/model_definitions.py  # 从注册 Schema 产生模型工具定义
app/tools/implementations/orders.py  # 三个薄适配器，4.3 实现
```

概念接口：

```text
ToolRegistry.register(definition) -> None
ToolRegistry.freeze() -> RegistrySnapshot
ToolRegistry.get(name) -> ToolDefinition
DiscoveryService.catalog(context, cursor=None) -> CatalogPage
DiscoveryService.disclose(context, names) -> DisclosureDelta
ModelToolDefinitions.build(snapshot, selected_names) -> 完整模型定义列表
```

context 是执行器提供的 Principal、Agent、Task、workflow/run/task、revision 和当前执行权，不从模型文本构造。Registry 对未知名字返回内部可分类错误；公开不区分“他人可用但你无权限”和“不存在”。

Definition 参数规范：extra=forbid、有限 JSON、无任意对象/SQL/身份字段。日期用带时区 ISO 字符串；枚举和分页遵循 4.1。JSON Schema 的非标准字段或 provider 不支持部分由定义适配器显式拒绝/兼容转换，并保持服务端原模型校验；不能为了绑定成功删除权限约束或放开参数。

## 4. 渐进式发现流程

1. 专业子图初始只绑定 discover_tools；提供简化且已经过滤的目录，不把全部业务 Schema 放入系统 Prompt。Supervisor 没有业务工具。
2. catalog 按 Agent、Task、enabled、全部 scope 过滤，再按任务标签和固定名字排序；不引入额外 LLM 或向量服务。目录每页最多20项，游标绑定 revision/上下文过滤，提示还有后续页。
3. 模型通过 discover_tools(mode=schemas,names=[...]) 选择最多4个可见名字；mode=catalog 可以请求后续目录。两种模式参数组合校验，不允许任意“描述匹配函数执行”。
4. discover_tools 自身也经过 Executor/Policy，计一次工具尝试，受超时/次数预算。不得直接在模型循环里绕过入口调用 DiscoveryService。
5. 服务端重新过滤选中名字，返回完整 Schema 和可信 DisclosureDelta(revision, selected_names, schema_hashes)。只返回安全不可见错误，不泄漏隐藏 Schema。
6. 子图从 Executor 的可信 side-channel 应用 Delta，不能解析模型声称的“已发现”。每个任务最多累计8个披露工具；04 只有三业务工具，限额可以配置。
7. 下一模型调用通过 Gateway 绑定 discover_tools＋披露集合的完整 Schema；同一集合进入 Policy 的 current_execution_set。两者必须由同一构造结果生成，避免“能执行却没绑定”或“Schema 已展示但执行器无集合”的断链。
8. 每次实际执行仍重新检查身份/任务/scope/当前执行权；披露不能延长过期权限。revision 不匹配时停止并报定义不一致，不静默换版继续。

并行返回多个 discovery 调用时串行执行、合并已验证 Delta；失败项不提升集合。业务调用如果与首次 discovery 出现在同一模型消息，但此前没有披露，该业务调用必须拒绝，要求下一轮再调用，不能通过同批后到的披露追认授权。

目录过大时分页而非静默丢弃工具；模型/Schema 上下文超限时明确失败或要求收窄选择，不伪装成没有能力。checkpoint 只保存已披露名字/摘要，不保存 callable、全目录或重复 Schema；运行时用固定 Registry 重建。

## 5. 扩展与前后边界

05 增加取消定义时须提供 Domain 操作、幂等记录和统一执行入口，不因 risk/side_effect 字段存在就能启用。06 增加审批/退款时由 ApprovalManager 提供特定操作证据；04 不创建审批库。07 检索工具保留同一注册/发现契约，不能从文档内容获得权限。

03 ModelCallGateway 需要接收 bound_tool_definitions 并保留原生 ToolCall 结构；这是现有统一模型入口的参数扩展，不新增裸模型旁路。供应商绑定 API 在实际开发时按安装版本验证，发现功能不能只有字符串目录而无后续真正工具绑定。

## 6. 三级任务与开发步骤

### 4.2.1 元数据与定义契约

- 目标/功能：唯一参数来源、权限/风险语义及不可变定义。
- 步骤：定义有限枚举和 Metadata→组合 Definition→校验 Agent/Task、名字、超时/重试组合→生成参数 Schema/hash→定义 Catalog/Disclosure 模型。
- 文件/接口：tools/models.py；ToolMetadata/ToolDefinition/DisclosureDelta。
- 前置：01 Agent/Task、02 Principal 契约；后继：4.2.2～4.2.5、4.3.1。
- 未来测试：重复名字、非法任务、额外身份字段、可变 Schema 污染；不机械逐字段穷举。
- 完成/交付：契约、Schema 示例、必要测试；参数模型是唯一校验来源，无代码执行或身份字段外泄。

### 4.2.2 注册与冻结

- 目标/功能：可查询、可追溯的进程内只读 Registry。
- 步骤：实现 register/get/list→启动完整校验→拒绝覆盖→固定 revision→freeze 后禁止变更→应用启动注入。
- 文件/接口：tools/registry.py；ToolRegistry/RegistrySnapshot。
- 前置：4.2.1；后继：4.2.3/4.2.4、4.3.3。
- 未来测试：重名、缺 handler 的启用项、冻结写入、不可变快照、未知版本。
- 完成/交付：Registry 与装配约定，所有运行调用来自启动快照，无热更新隐式行为。

### 4.2.3 候选过滤与目录

- 目标/功能：只显示当前任务允许的工具。
- 步骤：可信 context→四类过滤→稳定排序/分页→安全不可见错误→有界目录投影。
- 文件/接口：tools/discovery.py；catalog(context,cursor)。
- 前置：4.2.1/4.2.2、02 真实权限接入；后继：4.2.4、4.4.2。
- 未来测试：跨 Agent/Task/用户、缺任一 scope、禁用工具、目录翻页/revision 改变。
- 完成/交付：CatalogPage 和过滤测试，不向模型透露隐藏工具。

### 4.2.4 完整披露与模型定义适配

- 目标/功能：发现后真正可绑定，且与执行集合一致。
- 步骤：定义 discover_tools 参数→重新过滤 names→产生可信 Delta→从同快照重建完整 Schema→适配 Gateway 模型定义→处理大小/provider 兼容边界。
- 文件/接口：discovery.py、model_definitions.py；disclose/build。
- 前置：4.2.2/4.2.3、03 Gateway 契约；后继：4.3.3、4.4.2/4.4.3。
- 未来测试：多名字、隐藏名、同批追认拒绝、Schema 进入下一调用、集合/摘要一致。
- 完成/交付：Schema/Delta/模型定义适配，无“发现只是字符串”的断链。

### 4.2.5 启动装配与工具声明

- 目标/功能：声明三查询工具和发现工具，不提前调用业务。
- 步骤：从 4.1 查询参数/DTO 适配声明工厂→配置 scope/风险/超时→固定 handler 注入接口→用测试依赖验证工厂；实际 handler 由 4.3.4 实现后在应用装配冻结生产定义，4.2 不重做 handler。
- 文件/接口：tools/implementations/orders.py 的定义部分、registry 装配；handler 实现在 4.3.4，避免重复所有权。
- 前置：4.1 契约、4.2.4；后继：4.3.4、4.4.1。
- 未来测试：定义与参数/结果模型一致，生产无取消/退款假实现。
- 完成/交付：声明工厂和示例满足契约；实际冻结属于后续完整装配，不以尚缺的4.3 handler阻塞声明工厂本身，也不把未接handler假启用。4.2.6完成跨环节集成后才宣称发现闭环验收。

### 4.2.6 注册发现集成验收

- 目标/功能：验证目录→执行发现→下一轮 Schema/集合闭环。
- 步骤：搭建受控 Gateway/Executor依赖→测试多上下文→匹配 Schema 与 current set→核验冻结/revision/日志边界→更新说明。
- 文件/接口：tests/test_tool_registry.py、test_tool_discovery.py、实际 Gateway 适配集成用例。
- 前置：前五项；Executor 实际联接等 4.3；后继：4.4 集成。
- 未来测试：目录过滤、真实模型绑定最小兼容性在 4.4 联调，默认可控依赖。
- 完成/交付：受控完整发现验收记录及待外部联调项；只测 register/get 不算完成。

## 7. 顺序、验收和待决项

推荐 4.2.1→4.2.2→4.2.3→4.2.4→4.2.5→4.2.6；Schema 适配和目录纯测试可并行准备，启动装配与 Handler 集成串行。数据库无新增表；选中集合属于专业私有 State，不能进入全局 Registry。

验收：目录权限正确、完整 Schema 可绑定、披露/执行集合相同、执行仍重检、无跨任务残留、无 Schema/callable 进入公共 SSE。01～03 未验收的接口不得假装可用；Registry/ToolExecutor/Domain 的职责不混用。

待确认：本稿的 MEDIUM 只读风险、目录20/单次4/累计8的默认值、版本不匹配停止策略、启动只读注册与无热更新范围。审核前保持待审核，不执行任何测试。
