# 04 工具治理与订单查询闭环——完整开发执行计划与一致性审核（待审核）

> **历史设计方案，不再作为 V1 开发依据。** 自2026-11-08起，当前规划见[Agent Engine Demo定位与评估](../agent-engine-demo-plan.md)及[六阶段路线图](../development-roadmap.md)。下文原审核状态只适用于旧电商目标；可复用片段及新适用范围见评估清单，不能按旧任务直接开发。本轮保留原文，不删除代码或旧设计。

状态：**全阶段逻辑设计已编制，待审核；未开发、未测试、未验收**。编制日期：2026-11-08。审核通过后分别标记“设计已确认，待开发执行”，不能因保存文件直接变更状态。

## 1. 文档入口、范围和实际前提

- [4.1 订单领域服务与模拟数据](04-1-order-service-design.md)：复用原稿，补工具接口和后继任务；6项三级任务。
- [4.2 Registry与发现](04-2-tool-registry-design.md)：6项三级任务。
- [4.3 Policy与Executor](04-3-tool-execution-design.md)：7项三级任务。
- [4.4 OrderAgent查询](04-4-order-agent-design.md)：7项三级任务。

共26项三级任务，不改变九阶段/34二级环节。本轮不重新扫描仓库、不重复审核历史架构；按需引用 [01](01-stage-detailed-design.md)、[02](02-stage-detailed-design.md)、[03架构](03-stage-detailed-design.md)和[03执行计划](03-stage-execution-plan.md)。既有设计通过不是代码存在，当前所有下述步骤均为未来计划。

禁止本轮执行：Python业务文件创建/修改、SQL迁移、样本写入、pytest、Ruff/其他代码检查、模型和Apifox联调、业务验收。只编写Markdown并人工核对文档。本文“测试”一律指未来执行要求。

## 2. 阶段目标及冻结接口

链路：可信请求→03 Runtime/Supervisor→OrderAgent→Registry发现→Gateway完整工具绑定→Policy/Executor→OrderTool→OrderService→Repo/PG→规范观察→SpecialistResult→主图Response→03公共事件/状态查询。

职责唯一归属：4.1拥有领域事实，4.2拥有工具定义/目录/Schema，4.3拥有统一执行，4.4拥有私有工具消息/模型循环/结果构造。03仍拥有预算、任务、Checkpoint、订阅和唯一公共终态，不在04复制。Supervisor不加载订单全量工具。

| 接口 | 统一约定 |
| --- | --- |
| 三订单工具 | orders_get_detail/list/get_logistics逐一映射4.1三Service方法，Principal由可信context注入 |
| Schema | args_model为唯一参数来源；完整Schema与current_execution_set同源构造 |
| 披露 | Registry revision+名字+Schema摘要，可信Delta进入下一模型轮；同批不得追认 |
| Policy | ALLOW/DENY/REQUIRE_APPROVAL，不执行/不创建批准 |
| Executor | execute(call,context)→ToolExecutionOutcome；返回普通契约，不依赖LangGraph |
| 私有消息 | ToolMessage.tool_call_id=原call_id，每批全部配对再调模型 |
| 模型入口 | 03 ModelCallGateway增加bound_tool_definitions/原生ToolCall结果，不暴露裸模型给节点 |
| 预算 | 03 reserve_tool_call/settle_tool_call，每次实际尝试预留/结算；无新计数库 |
| 最终事实 | typed观察与确定性summary，模型完成建议不能创造facts |
| 公共输出 | 01信封、03投影/Broker；工具原结果和私有消息不得透传 |

## 3. 开发前门禁

1. 四设计和本计划审核，确认RLS/币种/分页/工具风险及限额。
2. 领域纯模型、Registry、Policy等可先用明确测试依赖独立开发；真正身份/数据库集成等待02.1/02.2验收。
3. Executor的持久预算、执行权与模型绑定集成等待03实际验收；不能用Mock接口宣布完成。
4. 公开端到端等待01公共协议、02受理/查询、03完整任务/订阅和既有新建workflow协议门禁关闭。
5. 不以缺少前置为由在04另建池、身份、预算、Runtime或审批设施。阻断只影响依赖该项的任务，记录明确，其他独立设计/开发可按授权推进。

## 4. 所有三级任务的推荐实施顺序

每项完整目标、接口、文件、前置/后继、未来测试和交付见各设计同编号。下表给出实际操作，不只罗列编号。推荐顺序允许在标明的前置满足后并行，不改变各文档契约。

| 顺序/任务 | 开发前置 | 实际操作步骤与主要文件 | 局部验证/完成门禁 |
| --- | --- | --- | --- |
| 1 / 4.1.1 | 01、领域选择审核 | models/errors/repository端口；固定Decimal/UTC/查询/游标/DTO | 纯参数边界；领域无框架/SQL依赖 |
| 2 / 4.2.1 | 01/02身份契约 | tools/models定义Metadata/Definition/Catalog/Delta和schema/hash | 权限/任务/Schema组合无歧义 |
| 3 / 4.1.2 | 2.1实际验收、4.1.1 | 新编号迁移三表/复合FK/索引/RLS/只读角色 | 真实PG约束及非owner隔离通过 |
| 4 / 4.2.2 | 4.2.1 | Registry注册/查询/快照/revision/freeze | 同名和冻结写拒绝，无热替换 |
| 5 / 4.2.3 | 4.2.2、Principal | 过滤enabled/Agent/Task/ALL scopes，目录分页 | 无隐藏工具或跨用户泄漏 |
| 6 / 4.1.3 | 4.1.2、2.1池 | read_scope局部身份/只读事务→四Repo查询→seek映射 | PG结果/连接复用/超时无伪空结果 |
| 7 / 4.1.5 | 4.1.2 | 固定样本→环境/目标校验→事务互斥→插缺失/冲突拒绝 | PG重复/并发初始化不覆盖，隔离通过 |
| 8 / 4.1.4 | 4.1.3、2.2 | 三Service方法、orders:read、归属和DTO装配 | 本人、不可见、金额/物流一致 |
| 9 / 4.2.4 | 4.2.3、Gateway契约 | discover参数/Delta→完整工具Schema适配→下一轮集合构造 | Schema与执行集合一致；不追认同批 |
| 10 / 4.2.5 | 4.1.1、4.2.4 | 声明工厂与handler注入契约，确定三查询和发现定义 | 参数/result模型与4.1一致；真实handler不在本任务重复实现 |
| 11 / 4.3.1 | 4.2.1、03契约 | 调用/context/Decision/Envelope/Outcome及安全码 | JSON/身份/结果关联边界明确 |
| 12 / 4.3.2 | 4.2.2～4、4.3.1 | Policy粗检/最终判断/具体审批证据要求 | 三态、禁用/越权和副作用门禁正确 |
| 13 / 4.3.3 | 4.3.2、4.2.4、03预算 | Executor查定义→校验→Policy→预留→执行→结果校验/结算；发现handler接线 | 所有调用统一入口，失败不提升权限 |
| 14 / 4.3.4 | 4.1.4、4.2.5、4.3.3 | 订单薄handler调用Service，Decimal/时间投影、安全错误映射 | 无SQL/Repo/裸user_id输入，真实PG一致 |
| 15 / 4.3.5 | 4.3.3、03预算 | 有效期限→每attempt预留→瞬态一次重试→取消回滚/失权处理 | 计量正确，无未知副作用重试 |
| 16 / 4.3.6 | 4.3.1/4.3.3 | 定义消息/调用配对、数据投影和可信工具事件边界 | 重复/坏ID拒绝，不透传参数 |
| 17 / 4.1.6 | 4.1前五项、02验收 | 专用PG与真实运行角色覆盖领域矩阵 | 不靠Mock验收，4.1独立交付 |
| 18 / 4.2.6 | 4.2前五项、4.3.3 | 目录→Executor发现→下一模型完整Schema/集合 | 发现闭环，不只register/get测试 |
| 19 / 4.3.7 | 4.3前六项、4.1.6 | Registry→Policy/Executor→Service→PG，拒绝/异常/预算验证 | 统一入口闭环、审批仍未实现 |
| 20 / 4.4.1 | 01/03、共享契约 | 专业State/OrderModelTurn/FinishIntent、builder与任务白名单 | ORDER_CANCEL明确不可用，context不被模型改 |
| 21 / 4.4.2 | 4.4.1、4.2.4/5、4.3.3 | 初始discover→可信Delta→下一Gateway完整Schema/集合 | 真正动态绑定，无裸模型 |
| 22 / 4.4.3 | 4.4.2、4.3.5/6 | 解析唯一calls→有界串行执行→观察/ToolMessage→全批配对再循环 | 多调用和失败配对，预算退出 |
| 23 / 4.4.4 | 4.4.3、4.1 DTO | FinishIntent/观察关联校验→澄清模板/事实模板→SpecialistResult | 模型不能编金额、空页不假全空 |
| 24 / 4.4.5 | 4.4.4、03实际验收、4.3.7 | 实际子图注入主图，映射/Response/Projector/查询衔接 | 无私有历史回灌，终态一次 |
| 25 / 4.4.6 | 4.1～4.3验收、4.4.5 | PG真实业务+可控模型覆盖权限/分页/故障/断开 | 数据库关键场景实际通过 |
| 26 / 4.4.7 | 上项及真实配置/公开门禁 | 真实Supervisor/OrderAgent模型、Apifox、Gateway/Executor/PG/SSE查询 | 实际工具Schema调用与源行一致，联调单独记录 |

## 5. 串行、并行与阶段性交接

必须串行：身份/Schema→真实DB读取；Registry契约→发现定义→Executor；Policy/预留→handler调用；披露→下一模型绑定→业务调用；批次全部ToolMessage→下一模型；规范观察→专业结果→公共终态。

允许并行：4.1.1与4.2.1；4.1.3/4.1.5与Registry目录；共享契约确定后Policy纯逻辑与结果模板；4.3.4/5/6按接口分工准备；专业State与测试fixture可提前准备。相同文件/SQL迁移统一合并顺序，不要求创建子Agent。

4.2.5是定义工厂，不等待真实handler编码才能设计/单测；4.3.4注入真实handler后才完整生产冻结，4.2.6再验发现闭环，因此没有“Registry先验收必须等Executor、Executor又要求Registry全部验收”的循环。

| 交接点 | 必交付物 | 不可冒充 |
| --- | --- | --- |
| 4.1→4.2/3 | 三Service签名、Query/DTO/错误、真实PG隔离结果 | Agent已实现 |
| 4.2→4.3/4 | 不可变定义、参数Schema、revision、Catalog/Delta | 披露等于授权 |
| 4.3→4.4 | execute/outcome、配对协议、预算/超时和错误 | 审批已可用或框架自动保证策略 |
| 4.4→主图/03 | 关联正确的SpecialistResult、私有消息隔离 | 完整子图State或直接SSE |

各环节记录设计/实现/自动验证/联调分别状态，未跑DB或真实模型不能把对应门禁勾选完成。

## 6. 跨环节接口与架构一致性审核结果

本节为设计审阅结论，不是代码检查或已通过测试。

| 检查 | 原潜在矛盾/遗漏 | 本轮统一方案 |
| --- | --- | --- |
| Service↔Tool | 可能引入user_id参数或重写领域规则 | 三个薄handler只从context注入Principal，参数/DTO沿4.1 |
| Metadata↔Registry | 独立手写Schema与校验规则漂移 | args_model单一来源、版本/hash、启动冻结 |
| Registry↔Policy | 目录可见被误作权限 | 完整披露绑定与执行集合同源，每次Policy重检 |
| 同批发现 | 先发现再执行可能追认权限 | 执行集合在当前模型调用前冻结，下一轮才新增 |
| Policy↔Executor | 策略执行或Executor替用户批准 | 三态分责；04无审批时明确不可用，无假等待 |
| Budget↔工具 | 另建计数、重试不收费 | reserve/settle复用03；每attempt计量；模型调用走Gateway |
| Executor↔ToolMessage | 结果无调用ID或直接透传SSE | Executor普通envelope，4.4专门消息层配对，全部完成才循环 |
| OrderAgent↔主图 | 重复身份/消息/工具历史回灌 | 复用SpecialistState，request只读，显式result映射 |
| 最终订单回复 | 直接展示模型自由文本可能编事实 | 观察验证＋确定性facts/summary；模型只提出完成/澄清建议 |
| State/Checkpointer | 存全目录、重复Schema和callable | 只保留名字/摘要/有界观察；定义从冻结Registry重建 |
| SSE/状态 | ToolMessage或审批建议成为公共成功 | 01/03白名单投影，一次done；无真实审批不发approval_required |
| 05/06扩展 | 只读重试用于退款，call_id当业务幂等 | 新增定义前必须落实Domain规则/稳定操作键/审批恢复；04不启用写工具 |
| Registry任务顺序 | 声明/handler/发现集成循环 | 定义工厂→Executor/handler→冻结装配→发现集成，见第5节 |
| 数值/时间/状态 | Decimal转float、时区猜测、嵌套status混淆 | 固定字符串金额/UTC；工具status与data.status分别校验 |

以上冲突均在文档层给出单一方案，不把互相矛盾的实现选项留给开发者。仅有业务范围/限额等审核决策，见第8节。

## 7. 04 最终集成验收设计（未来执行）

### 7.1 分层

1. 纯组件：查询边界、Schema、Registry过滤、Policy三态、FinishIntent/结果模板。
2. 真实PG：4.1三表/复合FK/RLS/一致读/种子/连接池隔离，4.3真实订单handler；不使用SQLite/Mock Repo替代关键验收。
3. 实际编译父子图+可控模型：工具发现/动态绑定/ToolMessage、多个调用、needs_input/rejected/failed、预算/超时/注入隔离。
4. 真实03执行器/订阅/元数据：可信身份、任务、快照、跨run、SSE/断开/重复/查询。
5. 显式真实模型+Apifox：真实Supervisor与OrderAgent工具调用，记录供应商、模型、用量质量/估算/未知和未完成项；不放入默认付费测试。

### 7.2 必要场景

| 场景 | 必须检查的可观察证据 |
| --- | --- |
| 本人详情/列表/物流 | PG原始行、Service、tool data、专业facts、公开summary一致；data_origin始终模拟 |
| 多轮发现 | 首轮只discover；后续完整Schema/集合一致，隐藏工具不可见不可执行 |
| 多ToolCall | 串行、每ID一结果、全批配对；发现不追认同批业务调用 |
| 归属/权限 | 用户A访问B与未知订单语义一致；缺scope不调业务；RLS独立阻止漏WHERE |
| 筛选/分页/金额 | 状态/时间半开区间、同时间seek、末页/空页、Decimal/UTC、未发货正确 |
| 澄清/续接 | 缺订单ID/时区保原目标，公共pending续接新run，同workflow预算不重置 |
| 模型异常/注入 | 非法JSON/calls/重复ID/无观察声称成功被拒，商品文本不能授权工具或创造事实 |
| 执行治理 | 瞬态一次重试/超时取消释放、预算耗尽、失权、数据库错误不假空结果 |
| 消息/公开输出 | 父图无私有ToolMessage，工具参数/凭据不出SSE，正常一次done |
| 连接与状态 | 断开仍执行、慢订阅不拖业务、重连只后续事件，幂等重复JSON不重做查询任务 |
| 边界能力 | ORDER_CANCEL/退款/RAG无假成功；ApprovalManager未接入不发假等待 |
| 数据初始化 | 固定样本、重复不改状态、冲突回滚、开发/测试隔离 |

验收不只断言模型说“查到了”，必须保存安全的PG/Service对照证据。数据库/模型未配置可在默认测试中跳过，但阶段记录明确未验收，不能“全部通过”。只运行有实际价值的用例，不靠数量/覆盖率宣称完成。

### 7.3 总体完成标准

- 四环节实际交付且01～03依赖验收通过；生产无Stub订单服务。
- 服务不依赖LLM/Graph，Agent不直接读库，所有调用统一策略/预算/执行入口。
- 目录、Schema、执行集合和身份权限无断链，工具私有消息正确配对。
- 真实PG数据支持首业务，真实模型确实选择/调用工具，公开事实与数据库一致。
- 安全、失败、预算、断开、隔离及查询结果验证通过；未实现业务明确不可用。
- 设计、开发、自动验证、真实联调状态分别记录，实际变更文档化。

## 8. 待用户确认的关键决策

| 决策 | 本稿建议 |
| --- | --- |
| 4.1既有选择 | CNY/单票/Decimal、三表RLS、keyset、种子不覆盖；沿用待审核稿，不擅自称已批准 |
| 工具注册 | 启动注册冻结、无热更新/工具DB，定义工厂注入handler |
| 发现方式 | 初始仅discover＋已过滤简化目录；完整披露后下一轮绑定，与执行集合同源 |
| 风险/审批 | 查询MEDIUM且无审批；任何缺审批能力的受限调用明确失败，不造等待 |
| 默认限额 | 目录20、单次披露4/累计8、每批4调用、本地8模型轮；单结果128KiB，模型商品投影前10条；仍受03总预算更严格限制 |
| 重试 | 只读且已知瞬态最多一次，超时不默认重试；每attempt计量 |
| 模型完成 | 严格FinishIntent，事实和公开summary确定性构造，避免自由文本编订单事实 |
| 04范围 | ORDER_CANCEL等仍不可用，05/06补真实规则/幂等/审批后启用 |

默认限额在审核和真实模型接入时验证；部署配置显式记录，不能悄悄取SDK默认值。若供应商不能返回原生工具调用，4.4不能假装完成；需单独记录兼容问题并讨论，不用字符串解析执行任意函数。

## 9. 文档同步、输出和后续动作

本轮新增4.2/4.3/4.4及本计划，4.1只补跨环节接口/后继，README加导航，路线图仅同步04设计状态；没有无关历史文档重写。03接口扩展（bound tools/原生ToolCall）、02订单权限/RLS角色以及01金额/时间投影在本阶段审核后按责任文档同步，不自动改写已批准的代码规范。

本轮没有创建Python文件、执行迁移/种子、pytest/Ruff/代码检查、模型/Apifox或业务验收。文档存在和一致性审阅不等于测试通过。等待四环节及本计划审核，再按用户授权的二级环节进入正式开发；不自动启动05～08。
