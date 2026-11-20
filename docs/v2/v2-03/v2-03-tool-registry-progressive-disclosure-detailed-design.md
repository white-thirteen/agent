# V2 03 ToolRegistry 渐进式披露：完整逻辑设计

状态：**DESIGN APPROVED**。

设计验收日期：2026-11-17。用户已原则通过整体架构及三个二级环节、六个 Task，本次按最终指令补充受控多候选真实集成验收和 Selector 调用前的模型预算预检查，归档为设计批准。

**本状态仅代表逻辑设计验收，不代表开发授权、实现完成或真实运行验收；03 当前不得标记开发 VERIFIED。** 以下模型调用、集成、数据库验证和测试均为未来计划，本轮未执行。本轮仅新增本文，不修改业务代码、配置、依赖或数据库，不执行测试、联调、Git 提交或推送。归档后停止，不自行进入正式开发。

## 1. 依据、实际现状与边界

依据：[项目定位](../../v1/agent-engine-demo-plan.md)、[V1 工具治理设计](../../v1/v1-03/03-tool-governance-detailed-design.md)、[当前状态](../../STATE.md)、[V2 01 批准设计](../v2-01/v2-01-knowledge-rag-enhancement-detailed-design.md)、[V2 02 批准设计](../v2-02/v2-02-context-engineering-detailed-design.md)，以及设计期间只读核实的源码。01、02 的设计批准不能当作已实现；本文不改变 V1 各阶段验收及归档状态。

### 1.1 当前实现

| 模块 | 实际行为 |
| --- | --- |
| `app/tools/registry.py` | 注册后冻结；按 AgentType、enabled、permission scopes 过滤；list直接构造完整Schema |
| `app/tools/models.py` | Metadata已有名称、版本、说明、Agent范围、权限、风险、审批、幂等、超时和标签 |
| `app/runtime/model_gateway.py` | invoke把传入工具绑定到实际ChatModel；统一尝试、超时、重试和用量 |
| `app/tools/policy.py` | ToolPolicy检查工具、Agent/Task、来源、允许集合、参数、权限、预算与审批 |
| `app/tools/executor.py` | 唯一实际执行入口，执行前策略复核、超时、有限重试及结果处理 |
| OrderAgent | 按query_spec确定get_order/list_orders，循环内复用单工具 |
| KnowledgeAgent | 模型只绑定search_knowledge；来源验证由确定性节点执行 |
| RefundAgent | 规划只绑定refund_order，审批后恢复原调用 |
| Supervisor | 结构化路由，不持有全量专业工具 |

当前V1通常已经只绑定一个业务工具，不能为展示Selector扩大范围或取消确定性选择。ToolPolicy是项目实际执行策略名称，不因设计另起ToolExecutePolicy实现。

### 1.2 本阶段边界

在原Registry上增加简要目录、受控Selector、选择记录和版本校验，保留完整Schema绑定和Policy/Executor。不得重新设计Supervisor、增加Loop/Graph节点/多Agent并行；不得改变订单、退款审批、操作幂等或未知结果核对；不建设工具向量库、动态插件、常驻工具服务或独立Evaluation/Trace阶段。

发现不授予执行权限。02规划的偏好控制入口不重新进入模型业务路由，01知识图八节点及Query来源约束保持。

## 2. 目标架构与完整调用链

```text
当前专业Agent的既有选择节点/调用位置
→ Registry按AgentType初筛
→ 权限 + 业务用途 + 调用来源过滤
→ 短路/有效选择记录复用
  ├─ 原位置无需工具：原有允许的结束路径
  ├─ 无候选：明确拒绝/不可用
  ├─ 确定目标/单候选：直接选择
  ├─ 有效选择：复用
  └─ 真正多候选：
       预检查并保留后续必要业务模型预算
       → ToolSelector（名称+简短说明）
       → 结构化工具名称
→ Registry核对选择/范围/版本
→ 解析所选完整Schema
→ ContextBuilder计入实际输入预算
→ ModelGateway绑定实际执行ChatModel
→ 原生AIMessage.tool_calls
→ ToolPolicy → ToolExecutor → 原业务服务/数据库
```

**短路Selector不等于跳过原业务模型调用。** 退款仍通过原规划生成ToolCall并进入审批；选择模型的原始输出不作为业务ToolCall执行。

### 2.1 组件职责

| 组件 | 本阶段职责 |
| --- | --- |
| ToolRegistry | 简要候选目录、选择校验、按名称/版本解析完整Schema |
| ToolSelector | 短路、记录复用、模型选择前预算门禁、多候选调用与结果校验 |
| 原专业节点 | 可信用途/范围、必要后续模型调用需求、选择记录和原规划模型调用 |
| ContextBuilder | 选择后计入完整Schema，不自行选工具 |
| ModelGateway | Selector与业务模型统一治理、按调用额度/期限限制重试、绑定实际集合 |
| ToolPolicy/Executor | 每次调用前重新治理，不因选择或缓存跳过 |

不另建通用编排服务。Selector是轻量组件，不是新增AgentType或业务Agent。

## 3. 简要目录与三层筛选

### 3.1 Agent、权限及业务范围

1. AgentType：沿用allowed_agents。
2. 权限/可用性：enabled、required_scopes、当前可用能力、合法Agent/Task组合。
3. 用途/来源：由可信节点给定order.get、order.list、knowledge.search、refund.plan等固定业务用途。

模型和用户不能提供可信用途、权限或候选白名单。运行中核对当前可信scope，不顺带建设动态ACL体系。

### 3.2 模型发现与确定性调用分离

Metadata增加model_discoverable标记，结合用途规则筛选；不能只按AgentType和权限把所有可执行工具暴露给模型。

| 工具 | 模型发现范围 |
| --- | --- |
| get_order、list_orders | 对应订单用途 |
| search_knowledge | 知识检索用途 |
| refund_order | 仅退款规划，不代表已批准 |
| validate_knowledge_sources | 不发现，原节点调用 |
| 审批登记/申请持久化/退款关闭等 | 不发现，原节点调用 |
| 偏好读写/02控制入口 | 不发现，沿受控路径执行 |

get_order允许RefundAgent确定性读订单，不等于其规划模型可发现get_order。确定性节点不走Selector，但继续经过同Policy/Executor。

### 3.3 元数据级目录

新增简要查询能力直接读取元数据，不能先list全部Schema再删字段。对Selector只提供候选name与人工维护的简短description，不提供参数/结果Schema、handler或完整权限目录。首版复用现有简短description，不新增描述生成模型。

Registry冻结时可预计算目录/Schema摘要，内部不等于向Selector披露。完整Schema只能在选择校验后交给实际业务模型。

## 4. Selector契约与调用治理

### 4.1 输入与输出

输入为当前任务的最小需求、可信用途、已过滤名称/简短说明；不提供全历史、审批凭据、敏感工具原文或任意路径。需求文本低信任，不能改变候选集合。

输出二选一：

```json
{"action":"use_tools","tool_names":["get_order"]}
```

```json
{"action":"no_tool","tool_names":[]}
```

结构化输出Schema仅描述选择结果，不包含业务工具参数。Selector不生成参数、不执行工具、不生成业务答案，也不公开推理过程。

校验要求：名称精确在候选中、无重复、数量不超过可信调用位置上限、no_tool只配空集合、拒绝额外字段/参数/执行指令。未知、重复、超限或格式错误拒绝整个结果，不静默过滤或截取。

no_tool只是建议：原节点已有验证事实且允许结束时才结束；业务必须工具时不得虚构答案。缺信息沿原澄清路径，不能以Selector建议改变原业务完成标准。

### 4.2 模型接入

首版复用现有ChatModel接入，独立Prompt、简短输入和受限输出；可显式配置兼容的较轻量模型，不假定已有新模型或新增常驻服务。轻量指调用负载，不宣称复用模型改变参数规模。

通过ModelGateway计入当前Task/Run尝试、期限与用量；失败也计数；不增加免费额度，不使用02维护预算，不自动提高原模型上限。Selector原始结构化调用消息不加入业务工具历史，避免形成业务ToolMessage配对错误。

候选目录放不进输入预算时明确失败，不截断目录。实际实现需验证模型结构化输出及工具绑定兼容性，当前没有运行通过结论。

### 4.3 模型预算预检查（用户最终补充）

**必须在实际调用ToolSelector前，证明剩余预算足以覆盖允许的Selector调用，以及至少一次后续必要业务模型调用。预算不足则明确失败，Selector不得消耗最后一次业务所需额度。** 短路/复用不消耗Selector额度，但后续业务模型仍按Gateway检查。

可信Agent节点声明后续已知必要业务模型尝试预留数B，B至少为1；若该阶段明确还需要更多，则按实际已知最低需求预留，不能只为通过门禁固定填1。该值不来自模型输出，不保证整个未知长度Loop一定完成。

设当前剩余尝试为R，Selector原允许的总尝试（含重试）为S_config，则：

```text
S_granted = min(S_config, R - B)
仅当S_granted >= 1时允许调用Selector
```

例：R=1/B=1时直接返回明确的选择前预算不足；R=2/B=1最多给Selector一次尝试，禁止网络重试吃掉业务额度；R=3/B=1时Selector最多使用两次，且仍受原重试配置限制。不能只做R>=2检查后任由Gateway内部重试超支。

Gateway对本次Selector使用受信任、调用级尝试上限，每次重试重新核对Scope；不修改共享Gateway全局上限。业务预留不是新增额度，也不提前算成已消费。

剩余Run时间也需保留后续必要业务模型调用的配置时间额度及已知必需处理余量；Selector总deadline不得侵占该保留部分。没有有效Selector时间额度即失败，不临时放宽Run期限。每次模型输入/输出继续满足配置上限；V1没有现成Task级绝对Token总账，不能在此虚构精确剩余Token或把unknown计零。

预留期间，额外Selector调用、重发现及02必要压缩不能抢占已保留的业务额度。必要上下文准备尽量在选择前完成；选择后若仍需模型压缩，必须同时具备压缩预算和业务预留，否则在业务调用前明确失败。紧邻业务模型调用时再次核对预算；取消、外部故障或其他已知必需步骤失败不能伪称“已经保证业务成功”。

若Selector失败，它最多消耗已授予的额度；不得绑定全部工具兜底。若Selector成功，后续必要业务模型至少仍有已保留的一次尝试；其实际调用、重试和失败正常结算。

门禁对首次选择与受控重新发现同样生效。预留和调用用量不得因新Run、澄清或Checkpoint重放清零；执行仍沿现有Task预算与恢复规则，异常中断不能自动重开免费Selector执行。

## 5. 短路与原业务接线

### 5.1 短路顺序

原位置无需工具→可信范围已指定工具→无候选→单候选→有效选择记录复用→真正多候选。所有分支仍核验权限和用途，不因短路免检。

### 5.2 三个专业Agent

| 位置 | 本阶段行为 |
| --- | --- |
| OrderAgent select_tools | 保留query_spec确定get/list，确定性短路 |
| OrderAgent plan_query循环 | 复用有效记录，绑定当前合法Schema |
| KnowledgeAgent select_retrieval_tool | 保留八节点、单检索工具短路 |
| RefundAgent plan_refund_call | 保留原单退款工具和ToolCall规划 |
| 来源验证/审批/偏好控制 | 不进入Selector |
| Supervisor | 不绑定专业全目录 |

当前真实业务的Selector调用次数可能为零，这是正确短路。不能为展示多候选扩展生产工具权限。多候选能力由隔离的真实集成场景验收，见第10节。

## 6. 完整Schema、绑定与执行一致性

Registry在选择校验后核对范围/版本并解析完整Schema，生成绑定记录；业务层不能选择一个名字却绑定另一工具。ModelGateway.invoke(tools=...)将本次集合绑定到实际执行业务ChatModel，不修改共享基础模型，不残留其他用户/Agent/上次绑定。无工具位置使用无业务工具绑定的模型。

ContextBuilder此时计入完整Schema开销；绑定后解析原生ToolCall，对照本次有效选择构造精确allowed_tools和argument_constraints，再进入Policy/Executor。执行集合不能大于绑定集合。

绑定退款不等于审批；版本一致不等于权限仍有效；Schema合法不等于归属/资格通过。未绑定ToolCall拒绝，不自动重发现来迁就模型。原批次预检、串行执行、超时/幂等、原调用恢复和配对ToolMessage保持。

## 7. 选择记录、Loop复用与受控重新发现

### 7.1 内部记录

保存record_version、user/conversation/task、Agent/TaskType/purpose、可信需求/业务范围摘要、权限摘要、候选摘要、目录/规则版本、所选名称/版本/Schema摘要、方式（deterministic/singleton/model）、generation和rediscovery_count。selected_tools作为派生投影，不维持两个独立可变权威。

记录不是授权令牌。只在同Task、Agent、用途内复用；核对当次身份、目标、权限、候选、版本和未完成调用。不做跨用户/会话/Task语义缓存；不可变Schema按版本复用与用户选择缓存分开。

### 7.2 重新发现条件

仅在既有决策入口且无待处理ToolCall、审批或未知副作用时，因可信用途/范围实质变化、候选/权限失效或工具版本变化而重新核验。不是每轮重选，也不接受模型扩权要求。

首版每Task最多一次重新发现，计数随Task持久化，不因新Run、澄清或重启清零；它不增加模型额度，仍执行第4.3节预算门禁。无合法候选直接拒绝，不用Selector寻找绕过方式。

已有待执行调用、等待审批、resume/reconcile、未知结果/原操作核对、上限耗尽时禁止重发现。不换工具、call_id或退款操作处理未知结果。

### 7.3 状态迁移

| 状态 | 事件 | 行为 |
| --- | --- | --- |
| 未选择 | 确定目标/单候选 | 核验并记录 |
| 未选择 | 多候选且预算足够 | Selector→校验→记录 |
| 未选择 | 选择及后续业务预算不足 | 明确失败，零Selector调用 |
| 有效记录 | 范围/权限/版本不变 | 复用 |
| 有效记录 | 安全边界失配 | 失效，受控重新发现及预算门禁 |
| 有效记录 | 已有待处理调用 | 固定原关联，禁止替换 |
| 审批/未知结果 | 请求重新发现 | 拒绝，原恢复/核对 |
| 已失效 | 无候选/预算耗尽 | 明确结束，不扩大范围 |

## 8. State、Checkpoint与前序设计兼容

记录和计数属于内部Task状态，不进入公开facts/SSE。新Task初始化，同Task澄清继承；专业图输入/输出显式白名单映射，不合并全部子图历史。

旧Checkpoint无新记录时不能伪造Selector验证。正常新执行可在安全位置建记录；退款恢复使用原调用/版本/Policy，不重新Selector。工具失配不能通过改选修复已批准调用。

Registry仍启动冻结，不热加载；目录升级不得自动升级暂停任务。02 ContextRevision和工具版本分别管理，摘要改变本身不使工具选择失效；可信目标/用途实质变化才失效。02偏好控制与维护不进入本阶段业务Selector，不能借维护预算执行选择。

## 9. 异常边界

| 情形 | 处理 |
| --- | --- |
| 无权限/候选 | 拒绝或不可用 |
| Selector前预算不足 | 明确失败，保留业务额度，不调用Selector |
| Selector超时/不可用 | 失败，不绑定全目录兜底 |
| 未知/重复/过多工具或多余字段 | 拒绝整个结果，不静默修正 |
| 目录输入超预算 | 明确失败，不任意删候选 |
| Schema/版本失配 | 停止绑定，只在安全边界允许重发现 |
| 执行前权限改变 | Policy拒绝，缓存不放行 |
| 历史/文档诱导内部工具 | 过滤与程序校验阻止越界 |
| 未绑定ToolCall | 拒绝，不自动扩集合 |
| 退款审批/未知结果 | 原调用核对，不重新选择 |
| 跨身份/Task缓存 | 关联失败，不复用 |

合法集合内仍可能选错适合工具，这属于选择质量，不能用权限校验通过替代质量验收。

## 10. 真实集成与质量验收

### 10.1 功能门禁

简要目录不含参数/结果Schema；三层过滤正确；零/单/确定目标/缓存短路；结构化选择严格校验；实际ChatModel绑定正确；未绑定调用不可执行；Policy/Executor、参数、审批不绕过；会话/Task隔离；Loop复用与计数持久；审批/未知路径零Selector。

### 10.2 独立真实Selector

使用现有工具说明构成独立只读多候选目录，固定单订单、列表、无关需求、越权诱导及含糊需求。真实调用配置模型，不用Mock冒充。独立Selector通过不能代替下节完整链路。

### 10.3 受控多候选真实完整链路（用户最终补充）

**必须增加受控多候选Agent Node集成场景，真实覆盖 `Agent Node → ToolSelector → Registry → ModelGateway → ToolPolicy → ToolExecutor`，并连接真实业务服务/PostgreSQL验证结果。** 不只测试独立选择器或直接调用handler。

在隔离验收环境的测试Graph/Agent Node中，复用正式选择、绑定和执行组件；提供测试专用受信任用途配置，使只读get_order/list_orders构成真正多候选，AgentType及orders:read权限仍合法。该配置仅由测试工厂构造，不注册进生产用途白名单，不增加运行配置中的测试绕过开关，不修改生产query_spec单工具约束、工具权限、业务Graph节点或审批规则。

测试Node可通过依赖注入提供受控用途，但不能复制一套简化Selector/绑定/执行逻辑冒充集成。实际业务模型生成原生ToolCall，执行上下文仍按所选集合及受控参数约束构造。选择器与业务规划均使用真实模型；Registry、Policy、Executor、handler和PG核心行为不被Mock。

验收链路：

1. 可信身份与合法Task进入受控Agent Node，形成至少两个合法候选；记录生产范围未变化。
2. 执行预算预检查，真实调用Selector，输出名称通过Registry校验。
3. Registry只解析被选完整Schema。
4. 通过ModelGateway绑定实际业务ChatModel，产生可关联ToolCall。
5. 通过正式Policy与Executor执行，只读访问真实PG。
6. 返回配对ToolMessage和可验证结果，对照实际订单/列表归属、分页及内容。

至少覆盖单订单与列表两种需求，另以受控异常/对抗输入验证：未绑定调用被拒绝、内部工具不可发现、预算不足零Selector、Selector重试不能吃掉业务预留。越界或故障可用定向注入验证拒绝路径，但不能替代上述真实成功链路。

证据包括实际候选数、选择方式为model、所选名称/版本、绑定集合摘要、真实模型调用及用量、ToolCall关联、Policy决策、Executor结果和PG事实核对。只保存必要脱敏证据，不输出凭据和不必要用户原文，不建设Trace平台。

生产单工具短路回归、独立Selector测试、受控多候选完整链路分开报告。受控目录成功不宣称生产天然存在多候选，也不为测试扩张生产权限。

### 10.4 预算边界验收

- R=1/B=1：预检查失败，Selector调用为0。
- R=2/B=1：Selector最多1次；模拟其可重试错误也不得尝试第2次。
- Selector成功后，至少保留所声明必要业务尝试；真实完整链路验证后续业务模型可调用。
- 后续明确需多次调用时按B>1核验，不能固定只保留1。
- 剩余期限不足、重发现额度不足、上下文压缩欲侵占预留时，均明确失败。
- 同Task澄清/重启/重放不能恢复已消费额度；失败及unknown用量照实记录。

R和B数值是测试边界，不是调整当前配置。本轮没有执行上述任何用例。

### 10.5 V1与前序兼容

真实订单归属/PG事实，Knowledge八节点及来源复核，退款原调用/审批/幂等/未知核对，02偏好控制不被发现，模型/工具预算、消息配对、SSE公开边界保持。遵守固定订单数据保护和既有完整门禁，不为新验收擅自修改/seed固定订单。

### 10.6 选择质量及成本

分别报告选择合法性、需求所需工具命中/遗漏、Selector新增调用/Token/延迟、业务Schema Token变化、Loop复用与重发现。以实际V1单工具绑定为基线，不用虚构全目录绑定制造收益。

当前业务Selector可能为零，不能预先承诺Token/延迟下降。合法不等于适合，代码正确不等于收益；效果退化、误选、失败、阻塞及未执行如实记录，不删除难例。

## 11. 三个二级环节与六个Task

以下全为未来实施计划，不构成本轮执行授权。

| 环节/Task | 实施交付 | 验收标准 |
| --- | --- | --- |
| **3.1 简要目录与受控筛选** | | |
| **3.1.1 目录视图与版本契约** | 分离简要/完整Schema；固定发现标记、目录摘要和选择记录 | 简要目录不生成/披露业务Schema；冻结/旧接口/版本明确 |
| **3.1.2 Agent/权限/用途筛选** | 三层过滤，区分模型/节点/控制工具 | 内部工具不泄露；生产范围不扩大；零/单候选短路 |
| **3.2 ToolSelector与完整绑定** | | |
| **3.2.1 结构化选择与预算** | Prompt/校验/Gateway；预检查及业务额度保留；失败处理 | 只看名称说明；R不足零调用；重试不侵占业务预留；实际调用/期限受治理 |
| **3.2.2 Schema解析与执行一致性** | 选择后解析、实际模型绑定、ToolCall与执行集合关联 | 所选/绑定/执行一致；策略/参数/审批保留；集成组件供受控真实Node复用 |
| **3.3 Loop复用与阶段验收** | | |
| **3.3.1 复用、重新发现与恢复** | Task记录/计数/父子映射、失效和旧Checkpoint兼容 | Loop不重复选；重发现有界且预算预检；暂停/未知不替换；计数不清零 |
| **3.3.2 真实选择与V1兼容验收** | 独立Selector、受控多候选完整链路、真实业务、质量/资源对照 | 真实Node→Selector→Registry→Gateway→Policy→Executor→PG证据；不扩大生产权限；预算边界及V1回归；不虚构收益 |

依赖保持：`3.1.1 → 3.1.2 → 3.2.1 → 3.2.2 → 3.3.1 → 3.3.2`。未来授权开发后Implementer→独立QA串行、主Agent复核。每阶段自行验收，不新增04系统集成阶段。

## 12. 文件与数据规划

| 拟修改/新增位置 | 职责 |
| --- | --- |
| `app/tools/models.py` | 简要视图、发现标记、选择结果/记录 |
| `app/tools/registry.py` | 元数据过滤、选择校验、所选Schema解析 |
| 新增 `app/tools/selector.py` | 短路/复用、预算门禁、受控选择 |
| `app/runtime/model_gateway.py`及必要Scope契约 | 调用级上限、业务预算保留、目的/输出限制，不提高全局预算 |
| 现有专业Graph builder | 原位置接线、绑定记录与状态映射 |
| `app/graph/state.py`、`contracts.py`、`transfers.py` | Task内部记录及显式映射 |
| `app/tools/policy.py`及必要Executor调用位置 | 本次实际允许集合，保留执行治理 |
| 生命周期/配置示例 | Selector接入和集中限制，不提供生产测试绕过配置 |
| 现有测试、必要夹具/测试Graph、验证脚本 | 独立真实Selector、完整真实链路、预算/复用/恢复 |

首版不新增业务数据库表，记录随现有Checkpoint保存；序列化优先简单版本化数据，必要时才更新允许类型。新文件及迁移冲突在开发前按仓库真实状态核对，不改01/02批准设计，不重做其功能。

## 13. 设计验收记录与停止条件

03状态为 **DESIGN APPROVED**，不是开发VERIFIED。保留现有架构、三个环节、六个Task和依赖。最终补充约束：

1. **独立ToolSelector测试不足以完成验收，必须有受控多候选Agent Node→ToolSelector→Registry→ModelGateway→ToolPolicy→ToolExecutor完整真实链路，核对真实PG业务事实，且不扩大生产工具权限。**
2. **调用Selector前预检查并保留选择与至少一次后续必要业务模型调用的预算；计入重试、期限和必要后续调用数，预算不足明确失败，禁止消耗最后业务额度。**

其他已批准原则保持：确定性/单候选短路；内部节点/控制工具不披露；选择后取完整Schema；实际模型绑定与执行集合一致；Policy/Executor每次复核；同Task复用、最多一次受控重发现；审批/未知恢复不重选；真实V1成本对照。

所有真实模型兼容、预算、PG、Checkpoint、生产回归及集成结果仍待未来开发验收，不写成功数据或VERIFIED。本次仅保存设计文档，不执行测试/联调或Git写操作；归档后停止，等待用户明确授权。
