# Agent Engine Demo：六阶段开发路线图与执行任务

六阶段、18环节、36Task及D01～D06已获最终设计确认，实施待独立授权。最终确认依据为README和AGENTS的正式收尾记录，历史待冻结文字保留追溯。

项目定位、架构及V1范围的权威依据是 [Agent Engine Demo定位文档](agent-engine-demo-plan.md)，其中保留实际评估与复用清单。旧九阶段全文见 [历史路线图](history/development-roadmap-commerce-history.md)，旧阶段设计只供历史参考，不得自动成为新V1要求。

历史资料保留于docs/history/。六阶段详细设计已完成，不再重复开展Task设计。后续仅在用户明确授权后执行指定Task，按需参考Graph旧协议，历史文档不构成当前V1新需求。

## 一、规划原则与核心接口

V1展示ToolRegistry、HITL、持久Checkpoint、RAG和Store五项真实能力。Supervisor→OrderAgent/RefundAgent/KnowledgeAgent，串行选择一个专业目标，父子State显式映射，工具消息保持私有。技术栈不变，不建设完整电商/真实支付/企业认证/分布式运行平台。

本稿包含6个一级阶段、18个二级环节、36个三级任务；数量来自职责划分，不继承旧9/34/26指标。按一级阶段设计审核；当前先完成全项目各阶段详细设计，全部审核后再按用户确认的二级环节/具体 Task 顺序授权实施。详细内容直接写MD，聊天提供链接和状态。需要未来细化时只补当前环节实际接口，不重建旧复杂度。

核心契约如下，实施等待用户授权。

- DemoContext保存演示身份、会话/thread、服务端scope和候选run关联，SubmitOptions独立保存input_mode及可选request_id。Service显式传二者到Runtime.submit，审批仅在本地控制面使用服务端审计Actor，演示身份不代表真实请求者认证。
- AgentState及专业结果复用既有结构，AFTER_SALES迁移REFUND。01只准备上下文，02 AgentRuntime唯一生成正式task_id，续接加载原值，workflow_id仅同值内部别名。旧Graph在正式Task关联后调用，公共请求不接收workflow_id。
- ToolDefinition：对象/handler、name/description、args Schema、allowed_agents、scope/风险/审批/副作用/安全重试/超时。注册冻结后按Agent和用户过滤，一次绑定完整允许Schema；list/get提供基础发现。
- Executor.execute(call,context)统一Schema/Policy、超时、预算、handler和安全执行记录。原生LLM ToolCall保留模型原始call_id并以对应ToolMessage闭合，节点构造调用使用node_call_id，经State/call_records返回，不伪造ToolMessage。两类共用Policy、Executor、预算和记录。
- Runtime.submit/execute/resume/get_state管理独立执行、thread门禁和有界订阅。管理resume核对可信引用后按04四类处理，真实interrupt才Command(resume)，Gate后核对安全续跑，正常END只返回持久结果，未知拒绝自动恢复。
- Checkpoint存图执行；Store按用户跨会话记忆；pgvector存知识片段；订单/退款/审批表存模拟事实。单个Postgres实例不意味着这些状态共享事务。

所有下列测试/命令均为未来执行，当前只写设计。

## 01 基础工程与运行环境

目标：复用工程，建立能运行真实模型和数据库的轻量基础。

详细方案见[01阶段完整详细设计](01-foundation-detailed-design.md)，三个二级环节、六Task设计已获最终确认，未实施。01负责模型/执行预算契约、development/test普通DemoIdentity、会话准备和唯一请求解析。管理员认证V1延期，04仅提供ApprovalActorProvider/本地审计Actor及审批入口，01不增加管理密钥。Task划分不变，开发须另行授权。

| 二级环节 | 目标/主要工作 | 前置 | 交付 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1.1 复用工程与配置收敛 | 保留FastAPI、分层、日志/密钥保护；更新Demo定位与最小设置 | 新方向审核 | 可运行工程配置 | 无凭据/数据库也可检查HTTP存活，未就绪明确 |
| 1.2 PostgreSQL资源与最小迁移 | Compose、池、显式编号SQL和测试库；不建所有未来业务表 | 1.1 | 可重复数据环境 | 真实连接/迁移/关闭通过，测试与开发隔离 |
| 1.3 模型入口与演示身份 | 单一模型适配、次数/期限/用量报告、固定演示用户及会话绑定 | 1.1/1.2 | ModelGateway、DemoContext、sessions | 真实模型可调用，用户/会话映射稳定，不冒充企业认证 |

| 三级任务 | 目标与具体步骤 | 文件/接口规划 | 前置/后继 | 未来测试及完成交付 |
| --- | --- | --- | --- | --- |
| 1.1.1 工程复用与事实基线 | 核对本评估后变化→保留工作区→最小修正配置/格式→区分设计与实现 | main.py、config/logging、README | 新方向确认→1.1.2/1.2 | 原HTTP/参数测试不退化；交付实际基线，不重做全仓审计 |
| 1.1.2 Demo设置与运行入口 | 整理数据库/模型及普通演示身份设置→模型/数据库SecretStr→安全错误→无依赖启动说明，V1无管理认证，04仅接本地审批Actor | config、.env.example、错误边界 | 1.1.1→1.2/1.3 | 无秘密回显、缺配置不假就绪，无管理员密钥配置或认证实现；交配置示例 |
| 1.2.1 数据库与迁移入口 | 固定PG版本→独立库→最小编号迁移/版本表→显式初始化 | infrastructure/postgres.py、Compose、SQL目录 | 1.1→1.2.2 | 真实PG重跑/失败回滚；交环境与迁移，不执行旧RLS设计 |
| 1.2.2 连接与会话绑定 | 生命周期开关池→sessions用户/会话唯一、thread服务端保存→只读状态访问 | postgres、session小仓储、lifespan | 1.2.1→1.3.2/02 | 并发绑定唯一、池释放、用户隔离；交持久绑定 |
| 1.3.1 统一模型调用 | 注入现有LangChain适配→invoke/工具绑定接口→单次/总期限和次数→usage已知/估算/未知 | 轻量model_gateway、config | 1.1→02/03/05 | 可控模型验证超时/限制；显式真实模型连通；交网关，不建Token预留账本 |
| 1.3.2 演示身份与管理边界 | 受控演示用户→普通API上下文→会话绑定验证→与04审批管理身份隔离 | api/dependencies、DemoContext、sessions | 1.2.2→02/04 | 普通聊天无审批权，映射不串用户；V1管理认证延期，04接本地审计Actor，交普通身份说明 |

阶段门禁：本地PG/模型实际连接分别记录；不能把驱动安装或配置存在当服务验收。

## 02 AgentRuntime 与 Supervisor

目标：复用主图，形成可路由、可澄清、可接专业图的运行骨架。

详细方案：[02 阶段完整详细设计](02-agent-runtime-detailed-design.md)（设计已批准，未实施，包含三个专业 Subgraph 的目标 State/Node/Edge 与最小骨架）。下述 3 个二级环节与 6 个三级 Task 均采用统一八项结构，覆盖 Task/Run 生命周期、State 映射、任务累计预算、thread 互斥、独立执行与 SSE/查询/重订阅，以及 03–06 接口边界；普通预算在图内 run_finish 结算，SSE 请求级所有者覆盖首次迭代前断开。02 仅使用显式注入的内存快照进行未来骨架验证；持久化中断与恢复、可信管理审批仍属于 04。

| 二级环节 | 目标/主要工作 | 前置 | 交付 | 完成标准 |
| --- | --- | --- | --- | --- |
| 2.1 State与Supervisor收敛 | 修通用澄清；有限公共上下文；轻量角色/任务迁移 | 01、现有State | 正确路由/续接 | 未知意图不执行业务，同目标保task新run |
| 2.2 三专业骨架与主图装配 | 查询/退款/知识固定子图入口，显式映射；未实现明确不可用 | 2.1 | 可注入主图/子图 | 无私有历史泄漏，不用Stub冒充生产业务 |
| 2.3 轻量Runtime和SSE | 进程内task、每thread锁、简单有界队列、结果状态查询 | 2.2、01 | 可运行核心链 | 断开不取消执行，等待审批时聊天冲突，不承诺重放/持久队列 |

| 三级任务 | 目标与具体步骤 | 文件/接口规划 | 前置/后继 | 未来测试及完成交付 |
| --- | --- | --- | --- | --- |
| 2.1.1 类型/State适配Demo | AFTER_SALES→REFUND迁移→取消任务不可用→复用契约→轮次清临时结果 | agents/types、graph/state/contracts/transfers | 01→2.1.2/2.2 | JSON/关联/消息增量不退化；不同时保两套角色 |
| 2.1.2 Supervisor与澄清 | 保留结构化路由→修通用pending→业务缺字段→有限纠正→统一模型入口 | supervisor/Prompt/router | 2.1.1→2.2 | 两类多轮澄清、非法输出不执行；交实际节点路径测试 |
| 2.2.1 主图与专业接入 | builder注入模型/Saver→wrapper映射→order/refund/knowledge固定入口 | builder、specialist wrapper、各专业builder | 2.1→2.2.2/03 | 缺能力失败、错结果拒绝；源码专业骨架不假成功 |
| 2.2.2 公共结果与骨架验证 | 澄清/汇总→唯一Response→受控专业图测试→生产无Stub | nodes、契约测试 | 2.2.1→2.3 | 实际编译图验证路由/隔离，交接未实现列表 |
| 2.3.1 独立执行与互斥 | Service提交→Runtime创建task持有→thread锁→有界队列→状态/错误收敛 | service/runtime、轻量streaming模块 | 2.2→2.3.2/03 | 真实连接断开仍执行、同thread互斥；无claim/epoch持久调度 |
| 2.3.2 SSE和状态语义 | 安全token/status/error/done→run关联→终态查询→超时/关闭清理 | agent路由、events/formatter | 2.3.1→03/04/06 | 一次done、敏感过滤、慢队列不拖任务；重启普通内存run不承诺恢复 |

开发期本阶段可注入InMemorySaver验证骨架；这是临时开发手段，不是新04持久化验收。新04完成前不得宣称重启/审批恢复可用。

## 03 ToolRegistry 与工具执行治理

目标：真实注册、过滤、完整Schema绑定、统一执行与本人订单查询。复杂渐进披露移出V1。

详细方案：[03 阶段完整详细设计](03-tool-governance-detailed-design.md)（设计已批准，未实施）。严格沿用下述 Task 名称、数量与顺序，细化 ToolMetadata/Registry、完整 Schema 绑定、Policy 三态、Executor 唯一执行入口、原生 ToolCall/ToolMessage、任务累计工具尝试、最小订单表/种子和 OrderAgent 七节点真实闭环。已确认 Order get/list 各限单一工具、Handler 仅接最小可信业务上下文、04 持久审批核验后由同 Policy 再检 ALLOW。03 不实现审批、退款、持久中断恢复、RAG 或 Store；04/05 复用治理接口完成专业业务。

| 二级环节 | 目标/主要工作 | 前置 | 交付 | 完成标准 |
| --- | --- | --- | --- | --- |
| 3.1 工具定义与注册过滤 | 轻量Metadata/工具对象、注册冻结、list/get、Agent/用户过滤、完整Schema绑定 | 01/02 | ToolRegistry | 模型拿到当前允许完整Schema，执行仍复检 |
| 3.2 Policy与Executor | ALLOW/DENY/REQUIRE_APPROVAL、Schema/超时/次数/安全重试、ToolMessage | 3.1、统一限制 | 统一执行入口 | 各Agent不直接调业务，未接审批不伪造等待 |
| 3.3 模拟订单与OrderAgent | 单表本人查询/小样本、模型工具循环、事实结果 | 3.2、PG | 首个专业路径 | 真实模型/PG结果一致，跨用户不可见 |

| 三级任务 | 目标与具体步骤 | 文件/接口规划 | 前置/后继 | 未来测试及完成交付 |
| --- | --- | --- | --- | --- |
| 3.1.1 Metadata/Registry | 定义name/Schema/Agent/scope/风险/审批/副作用/超时→注册/拒绝重名→冻结 | tools/models、registry | 01/02→3.1.2/3.2 | 注册对象真实可调用，未知/越权过滤；交目录和Schema |
| 3.1.2 过滤与模型绑定 | 按Agent/用户过滤→直接绑定少量完整Schema→Gateway保留native calls→无目录权限提升 | tools适配、model_gateway | 3.1.1→3.2/3.3 | 下一模型实际有Schema；不做disclosure receipts/分页协议 |
| 3.2.1 Policy/Executor | 参数校验→权限/审批三态→次数/超时→handler→安全结果；原call_id关联 | tools/policy、executor、models | 3.1→3.2.2/04 | 拒绝不执行；副作用不默认重试；审批未就绪明确失败 |
| 3.2.2 工具消息与治理 | 每call恰一ToolMessage→多call串行→有界模型循环→安全错误/事件→预留HITL gate接口 | specialist工具适配、executor | 3.2.1→3.3/04 | 配对、重复ID、超时、缺Schema/越权不旁路；交只读集成测试 |
| 3.3.1 最小模拟订单事实 | 新单表owner/amount/currency/status/refunded标识→幂等小种子→get/list服务→用户限定SQL | 小domain服务、SQL、seed | 1.2、3.2→3.3.2/04 | 真PG归属/金额/重复种子；无商品物流/RLS系统，真实状态不在内存字典 |
| 3.3.2 OrderAgent查询 | 注入Registry/Gateway/Executor→Model/ToolCall/ToolMessage循环→依据事实返回主图 | specialists/order、order工具薄封装 | 3.3.1/02→04/06 | 真实模型调用与源行一致；无订单/越权/缺信息有边界；取消明确不可用 |

阶段门禁：不能只实现工具名列表而无真实handler/Schema，也不能让Agent跳过Executor直接读库。

## 04 HITL人工审批与Checkpoint恢复

目标：项目最重要技术闭环，必须原执行interrupt/resume和真实进程重启恢复，不通过新发业务请求冒充。

详细方案：[04 HITL、Checkpoint 与 RefundAgent 完整详细设计](04-hitl-checkpoint-refund-detailed-design.md)（设计已批准，未实施）。覆盖原子图及安全节点拆分、PG Saver/sync/嵌套 namespace、本地审批ActorProvider及审计、决定持久化后显式恢复、原 ToolCall/规范参数/operation 校验、同 Executor 执行、事务幂等及故障核对，并明确可信补绑定和已提交结果的原节点重入守卫。保留下述 Task 划分与既有推荐实施依赖，不代表已运行任何中断/数据库/测试。

| 二级环节 | 目标/主要工作 | 前置 | 交付 | 完成标准 |
| --- | --- | --- | --- | --- |
| 4.1 持久Checkpoint与恢复入口 | PG Saver、稳定thread、状态读取、受控Command(resume)、嵌套子图传播 | 02/03 | 持久图和恢复接口 | 完全重启可找到原中断，不新建thread或普通用户消息 |
| 4.2 模拟退款和可信审批记录 | 本人资格/服务算金额、申请/operation幂等、审批快照与独立管理验证 | 3.3、PG | 模拟业务和可信决定 | 无真实支付，重复决定一致，错参/错人拒绝 |
| 4.3 RefundAgent与原调用恢复 | 原ToolCall→Policy→interrupt→批准/拒绝→原调用/ToolMessage→模型 | 4.1/4.2、3.2 | 完整HITL路径 | 已完成工具不重复、拒绝不退款、重启后批准执行一次 |

| 三级任务 | 目标与具体步骤 | 文件/接口规划 | 前置/后继 | 未来测试及完成交付 |
| --- | --- | --- | --- | --- |
| 4.1.1 PG Saver装配 | 验本地签名→独立初始化→应用注入→稳定thread→普通新轮次/澄清→实际子图中断保存 | checkpoint、lifespan、builder | 01/02→4.1.2 | 真PG快照、进程重启读取、子图namespace；交资源说明 |
| 4.1.2 安全Resume入口 | 管理引用→原session/thread门禁→核对绑定及最新快照→四类处理：真实pending interrupt才Command(resume)；Gate后按安全位置/原operation核对续跑；正常END返回持久Task结果且无新Run；未知拒绝自动恢复并核对/人工处理 | 原Runtime/API、当前执行上下文及持久结果映射，无新恢复组件 | 4.1.1、4.2.2→4.3 | 普通chat不可resume，原Task/operation稳定；Gate后不强求当前interrupt，已成功零重复写，END无Graph执行，未知不盲重发 |
| 4.2.1 模拟退款事实 | 本人资格→服务定金额→幂等创建待审批申请；实现原operation结果查询及退款执行接口，但只有可信审批后可调用执行接口改变退款结果/订单标记 | domain/refund小服务、refund_requests、orders | 3.3.1/PG→4.2.2/4.3 | 申请不等于退款；operation_id唯一约束和本地事务保证业务幂等；无支付账本 |
| 4.2.2 审批存取与身份 | 保存call_id/tool/规范args/hash/operation/用户/thread→服务端审计Actor/本地环境检查→创建起30分钟及DB时间校验→原子决定→重复一致/相反拒绝 | workflows/approvals、approvals表、审批路由 | 4.2.1、1.3→4.1.2/4.3 | 普通用户/错快照/错中断拒绝；审批先落库，早到可重试resume |
| 4.3.1 RefundAgent中断链 | 模型/申请节点与gate/执行节点分开→保存原call→幂等审批登记→interrupt→可信决定→Executor原调用→稳定ToolMessage→模型 | specialists/refund、退款工具、policy gate | 4.1/4.2/3.2→4.3.2 | 不重新模型生成退款call；批准重检、拒绝不执行；call与message配对 |
| 4.3.2 重启及重放验收 | 完全停进程→同thread恢复→重复/拒绝/冲突决定→工具成功后快照前故障→按operation_id核对既有结果 | PG集成/独立进程验收说明 | 4.3.1→05/06 | 原call/args保持；重放不重复改变业务结果，节点/工具允许重新进入幂等核验；无全局原子保证 |

Checkpoint/审批/模拟操作不是一个原子事务。V1用幂等登记、唯一operation和重复恢复核对处理窗口，不建设分布式补偿。审批决定已保存但resume失败时保留原记录，可信接口可重试，不重新创建无关任务。图恢复会重跑节点，gate前逻辑必须幂等。

审批前创建申请只登记请求、候选金额和待审批状态，不写订单已退款或退款执行成功；可信批准、Policy与Domain复检通过后，才经Executor执行原ToolCall的实际模拟退款变更。拒绝不发生退款副作用。

业务幂等以稳定operation_id、数据库唯一约束和本地事务约束退款结果及订单标记；同operation返回已有结果，不再改变业务状态。这不代表Graph节点、ToolCall、Checkpoint和数据库全局Exactly Once或同一原子事务，恢复可能重进节点/执行器。申请幂等和退款执行幂等是两个边界，都应验证。

该阶段实际推荐顺序：4.1.1→4.2.1→4.2.2→4.1.2→4.3.1→4.3.2。4.1.2的恢复入口可先以受控引用开发，但可信审批接线等待4.2.2；4.2不依赖4.1全部验收，避免按二级编号机械执行形成循环。完整04最后统一验收。

## 05 RAG与Store长期记忆

目标：真实向量检索和独立跨会话记忆，PG/pgvector为V1唯一检索后端及知识权威，ES/BM25/Hybrid仅领域接口未来扩展，V1不实现或部署。

详细方案见[05 RAG与长期记忆Store](05-rag-memory-detailed-design.md)，三个二级环节及六Task已完成设计，当前进行最终收敛。保留md/txt导入、真实Embedding/pgvector、八节点KnowledgeAgent及原生工具治理。回答链为文档检索→证据组织→充分性评估→AnswerDraft→来源验证→approved_answer→Response。共享Store提供显式偏好读写及跨会话隔离。正式采用OpenAI text-embedding-3-small/1536及embedding_profile/profile_revision，candidate=5/topK=3、2400tokens/24KiB、固定阈值null，评估sufficient/insufficient/conflicting，ES仅未来扩展，未实施或验证。

| 二级环节 | 目标/主要工作 | 前置 | 交付 | 完成标准 |
| --- | --- | --- | --- | --- |
| 5.1 文档/Embedding/pgvector | txt/md导入、切分、文档版本/片段、真实Embedding和索引 | PG/模型 | 可更新知识索引 | 固定模型/维度、重复导入不重复、真实向量查询 |
| 5.2 KnowledgeAgent证据问答 | 注册检索、证据组织、充分性评估、AnswerDraft生成及来源验证 | 5.1、03 | approved_answer及真实来源 | Response原样输出批准正文，无证据拒答，引用有效性与语义质量分别验收 |
| 5.3 持久Store与共享Memory | V1 PG Store、用户namespace、共享Reader、Manager统一读写、显式命令校验/更新 | PG/02/03 | 跨会话长期记忆 | 用户隔离、重启保留、不是Checkpoint/聊天全文 |

| 三级任务 | 目标与具体步骤 | 文件/接口规划 | 前置/后继 | 未来测试及完成交付 |
| --- | --- | --- | --- | --- |
| 5.1.1 导入与向量资源 | 已确认OpenAI text-embedding-3-small/1536及显式Profile→pgvector环境/新增依赖审核→txt/md切分/版本元数据→幂等索引更新 | knowledge/ingest、embedding、索引适配/SQL | 01/PG→5.1.2 | 真Embedding写入PG，重复导入与更新有效；交样本文档和配置 |
| 5.1.2 Retriever证据契约 | candidate5/top3精确余弦检索→2400tokens/24KiB、阈值null→三态证据充分性→doc/version/chunk/hash/source→无结果/过期片段处理 | knowledge/retriever、证据DTO | 5.1.1→5.2 | 真向量排序/来源对应，空证据明确；不是关键词假检索 |
| 5.2.1 知识工具与子图 | 同Registry/Executor检索→证据组织与充分性评估→AnswerDraft→来源验证→approved_answer→Response，保留八节点 | specialists/knowledge、知识工具/Prompt | 5.1.2、03→5.2.2/06 | 不直连向量库，不伪造来源，未验证正文不公开 |
| 5.2.2 RAG真实联调 | 固定样本→真实模型检索和生成→来源核对及语义评价→不足/冲突/失效/文档注入 | 知识集成测试/演示说明 | 5.2.1→06 | 引用有效与正文质量分别核验，无证据拒答，记录供应商/维度/profile |
| 5.3.1 Store资源与Reader | 按安装版本接PG Store→用户namespace→MemoryManager.snapshot→三个Agent共享MemoryReader，跨会话/跨Thread读取 | infrastructure/store、memory/reader/manager | PG/02→5.3.2/06 | 用户A会话2读到会话1记忆，B不可见，重启仍有；不用Checkpoint冒充 |
| 5.3.2 显式记忆管理与幂等更新 | 原Human确定性解析→准备op/digest/expected_revision→同prepare_attempt绑定准备/执行节点→原State及标记sync→execute_memory_write经同Policy/execute_prepared→handler→MemoryManager.apply | memory/models、manager、既有命令图及统一Executor，无writer.py或第二执行器 | 5.3.1、03及04持久写前边界→06 | 固定节点白名单，模型候选不授权；sync失败无write handler，准备零计数，Manager四态/Executor状态及effect_status分层，unknown保留并人工核对，不盲写/重试 |

Memory V1仅answer_language/answer_style及显式管理，原Task可信Human在既有MemoryManage入口调用命令节点模块的确定性解析函数形成MemoryCommand，Manager负责版本/operation幂等/per-user锁及conflict/unknown，模型候选不授权。MemoryWriter正式归V2，只保留候选提取/筛选/归一化/冲突建议，经未来独立授权策略及统一治理后仍交Manager；V1不实现或依赖它，不新增Agent、Graph或Task。5.3.2仅按职责更名，编号及前置依赖不变。

RAG导入在01/03接口稳定后可与04部分工作并行，但最终HITL/Store仍须各自真实验收。Store读写不跨退款数据库事务，不拥有审批权。

## 06 三个专业流程集成与最终交付

目标：统一装配和交付五能力演示，验证组件组合而非重复堆叠基础测试。

| 二级环节 | 目标/主要工作 | 前置 | 交付 | 完成标准 |
| --- | --- | --- | --- | --- |
| 6.1 三Agent和共享能力整合 | Supervisor真实分派、统一Registry/模型入口/Store、有限会话控制 | 03/04/05 | 完整应用装配 | 无测试替身冒充专业业务 |
| 6.2 核心风险及跨会话验收 | 重启/重复审批/工具幂等、用户隔离、断开/错误及记忆失败 | 6.1 | 必要自动与故障记录 | 五核心均有真实证据，边界不假报 |
| 6.3 演示与交付 | Apifox、README、启动/重启演示、已知限制 | 6.2 | 可重复Demo | 按说明跑通，模拟/未实现/未验证清楚 |

| 三级任务 | 目标与具体步骤 | 文件/接口规划 | 前置/后继 | 未来测试及完成交付 |
| --- | --- | --- | --- | --- |
| 6.1.1 完整演示环境装配 | 三子图注入→Registry统一→共享Store/网关→移除验收Stub配置 | main、builders、依赖装配 | 03/04/05→6.1.2 | 真实请求三专业链路完整，保留模拟数据标志 |
| 6.1.2 会话/状态/事件统一 | 顺序任务→等待审批冲突→新run恢复原thread→公开来源/结果/状态 | Runtime、SSE/查询、会话契约说明 | 6.1.1→6.2 | done≠workflow完成，工具私有消息不外泄，跨会话记忆一致 |
| 6.2.1 核心持久化故障 | 重复/冲突审批、拒绝、重启、工具成功快照失败窗口→按operation_id核对DB | PG/独立进程测试 | 6.1/04→6.2.2 | 退款副作用幂等、原ToolCall恢复；不保证函数只调用一次，非等待运行崩溃不盲重放 |
| 6.2.2 隔离和退化路径 | 多用户订单/Store/审批→SSE断开→模型/检索/记忆故障→预算退出 | 集成/HTTP测试 | 6.2.1→6.3 | 无跨用户数据，断开不取消，记忆失败不撤销业务 |
| 6.3.1 Apifox与演示脚本 | 查询→退款等待→完整重启→批准/拒绝→RAG→跨会话Store→源数据核对 | Apifox集合、docs演示说明 | 6.2→6.3.2 | 非原文重新发退款冒充resume，证据/数据一致 |
| 6.3.2 交付记录和最小回归 | 固定依赖/启动/资源释放→必要回归→真实模型单独报告→限制/安全说明 | README、配置、验收记录 | 6.3.1 | 干净环境可复现，密钥不入库；V1完成需用户按证据验收 |

## 二、统一安全/测试/验收标准

- 所有阶段的模型与工具都有轮次/次数/期限/有界重试；Token未知不能计零，但V1不承诺生产成本硬上限。
- 多Agent单任务、同thread互斥，普通chat不能批准或resume；模型不能选择可信用户、审批人或退款金额。
- 所有工具经Registry过滤/完整Schema/Gateway/Executor，参数和结果校验，ToolCall/ToolMessage匹配。
- 高风险原调用真正interrupt并持久化；审批前只创建申请，拒绝不退款，批准恢复原参数后执行；以operation_id/唯一约束验证副作用幂等，不宣称全局Exactly Once。
- RAG使用真实Embedding/pgvector并有来源；Store独立持久、按用户跨会话，不是完整历史。
- 使用真实PG验证隔离/唯一约束/退款状态/重启，不只Mock；真实模型显式联调，不进入默认付费测试。
- 单进程任务/队列不承诺持久运行调度或事件重放；进程崩溃无法送达done时据持久中断和业务记录查询，不宣称未执行。
- 每步记录实现、自动验证、真实联调分别状态；设计文档或安装依赖不能勾选功能完成。

## 三、旧方案映射与最终决策

旧01/02环境、身份、State、主图基础→新01/02（收缩）；旧03工具/运行及旧04→新03；旧05订单取消移出V1；旧06复杂审批退款→新04最小真实HITL；旧07知识/旧08记忆→新05；旧09交付→新06。旧九阶段的编号仅供追溯，以历史文件为准，不机械复用其三级任务。

定位、范围和六阶段详细设计已形成。Embedding模型/1536维、RAG参数/充分性、审批30分钟已正式采用，管理员认证V1延期，仅保留本地ActorProvider审计，见06第13.2A。实际版本、服务API及环境行为留实施验证，已采用文档格式、资格和Schema不重新开放。历史映射不改变阶段和Task数量。

以下为历史修订记录，待确认参数及旧管理密钥方案仅反映当时决策，已由末尾最新正式确认记录替代。

## 四、本轮状态

[01](01-foundation-detailed-design.md)、[02](02-agent-runtime-detailed-design.md)、[03](03-tool-governance-detailed-design.md)、[04](04-hitl-checkpoint-refund-detailed-design.md)、[05](05-rag-memory-detailed-design.md)、[06](06-integration-and-final-delivery-detailed-design.md)均已最终确认详细设计，共6阶段/18环节/36Task。实施待独立授权，设计确认不等于实现或验收。以下轮次说明保留历史语境。

以下为历史轮次记录，其中等待设计/审核等表述仅代表当时状态，当前以本节首段及最新修订为准。

2026-11-08：上一轮基于当前工程、依赖源码和权威文档形成 01 草案；本轮仅定向阅读设计与导航文档，将整个 01 的职责、步骤、接口/数据结构/文件、依赖、验收与 02 交接一次性展开。未修改业务代码、依赖、配置或数据库，未执行测试、代码检查、迁移、容器操作、真实模型或 Apifox 联调。此前文档体系收敛记录仍是历史文档工作，不代表开发执行成果。

2026-11-08 02 设计轮：依据项目定位、路线图、已批准的 01 预算/身份/环境契约及现有 Graph 协议，新增 02 整阶段设计并更新本路线图与 README 导航。未检查 Git 或开发完成情况，未修改业务代码、依赖、配置或数据库，未执行测试、代码检查、迁移、容器操作或模型联调。全项目各阶段设计完成并审核后才统一开发。

2026-11-08 03 设计轮：依据已批准的 01/02，新增 03 工具治理整阶段设计，补齐 Registry/Policy/Executor、ToolCall/ToolMessage、OrderAgent 七节点/真实订单单表与种子、后继审批/检索边界，同步设计状态及 README 导航。只修改 Markdown，未检查 Git 或开发进度，未编写业务代码/配置/迁移 SQL，未运行测试、代码检查、数据库/容器或模型操作；等待 03 整体审核。

2026-11-08 04 设计轮：依据已批准的 01–03，新增 04 全阶段方案及 API/State/Node/事务/恢复/预算/异常验收设计，同步本路线图与 README 状态/导航。定向查阅官方 LangGraph 说明和已安装包接口源码，不检查 Git 或开发进度；未修改业务代码、配置、依赖、迁移 SQL 或数据库，未运行测试、迁移、容器或模型联调。全部阶段设计审核后再统一开发。

05 设计轮：依据用户确认的01～04设计批准状态，新增05全阶段方案并同步本路线图/README导航。只定向阅读权威设计、依赖清单/必要静态接口及官方技术资料；未检查Git/实际开发进度，未修改代码/配置/依赖/实际迁移或数据库，未执行测试、检查、容器、导入或模型联调。05待整体审核，06待设计；全项目仍未授权开发。

## 2026-11-09 全项目审查第一轮整改记录

修复统一context/options、Runtime正式Task、四类Resume及原生/节点消息规则，05摘要及5.2 Task对齐生成式RAG，更新状态导航和决策分类，保留所有Task编号/名称。

六阶段、18环节、36Task保持不变。本轮仅修改Markdown设计、规范及导航，未检查实际开发进度，未修改业务代码、配置、依赖、数据库或迁移，未运行测试、代码检查、服务、容器、模型或Apifox联调。四项决策仍推荐待用户确认，设计尚未冻结。第一轮修订完成后停止，最终只读复核由用户另行授权。

## 2026-11-09 第二轮定向文档收敛记录

修订01摘要、1.1.2与1.3.2管理边界，4.1.2四类恢复摘要及5.3.2显式Human语法授权/字段校验/幂等更新。模型候选不能单独授权写Memory，unknown不盲写或重试。

第二轮修订完成，六阶段、18环节、36Task及既有八项结构不变。四项推荐决策仍待用户确认，未宣布冻结或授权实施。本轮仅修改Markdown，未检查实际开发进度，未开发、安装、测试、检查代码、操作数据库或启动/联调。最终只读复核由用户另行授权。

## 2026-11-09 最终技术决策确认与冻结准备记录

移除第7行过期重复Task设计指引，仅按明确授权实施。同步四项最终决策、Actor与30分钟审批摘要、PG唯一权威及RAG固定参数/未来ES边界，Task编号名称不变。

用户正式确认前三项技术参数并明确延期管理员认证，已无这四项待确认决策。历史记录中的待确认或管理密钥方案仅供追溯，当前以本文规范及本记录为准。LocalDemoApprovalActor固定审计值采用local-demo-approval，沿用approver_id存储字段，不构成真实身份认证或授权。

六阶段、18环节、36Task和既有八项设计结构不变。仍为纯逻辑设计，只修改Markdown，未检查实际开发进度，未修改代码、SQL、实际配置或依赖，未安装、测试、检查代码、启动、数据库操作或联调。实施验证尚待授权，当前等待用户最终设计冻结确认，设计确认不授予任何Task开发权限。本轮完成即停止。

## 2026-11-09 Memory V1与V2职责收敛记录

5.3.2按用户决定更名为显式记忆管理与幂等更新，更新文件/调用链及V1/V2说明；5.3.1明确Reader经Manager.snapshot跨会话/跨Thread读取。Task编号、数量及既有依赖不变。

V1保留AsyncPostgresStore、两偏好字段、用户Namespace、跨会话/跨Thread、revision、operation_id/digest/expected_revision/last_mutation、per-user锁及conflict/unknown和原Checkpoint写前边界。显式解析独立于V2，旧记录中的Writer为当时V1写路径称谓，现已统一为MemoryManager及显式命令流程，不代表V2已实现。

六阶段、18环节、36Task和八项设计结构保持，5.3.2仅授权更名，无新增Agent、Graph或Task。此前四项最终技术决策不变。本轮仅改Markdown，未检查开发进度，未修改Python/SQL/依赖/配置，未测试、迁移或联调；实现及冻结不在本轮授权内，完成后停止并提交用户审核。

## 2026-11-09 Memory V1最终执行接口收敛记录

仅同步5.3.2的准备/sync/execute_prepared链路、节点白名单及两层失败验收摘要，编号、依赖、既有V1显式管理交付不变。

本轮补齐的是同一Executor的跨阶段接口细节，无第二执行器或新治理平台。MemoryManager仍只返回applied/reused/conflict/unknown，明确未开始的技术故障沿Executor异常契约；unknown不得伪装普通技术失败或未写。V1显式管理、共享Reader/Manager、两字段、单进程锁及人工核对边界保留，MemoryWriter仍仅V2且未来需独立授权。

六阶段、18环节、36Task保持，不新增Agent、Graph、Task、表或独立服务。仅修改Markdown，未修改代码/SQL/配置/依赖，未检查开发进度、运行测试/代码检查、安装、启动、数据库操作或联调。文档完成提交用户审核，未授权任何实施。
