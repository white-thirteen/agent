# Agent Engine Demo：项目定位、架构收缩与成果评估

2026-11-13最新状态：01～04均ACCEPTED；04已获用户正式验收，并获本轮Git提交/推送授权，归档进行中；05等待用户设置角色配置，05～06未开始。详情见[04验收记录](question/04-hitl-checkpoint-refund-stage-acceptance.md)及[当前交接STATE](STATE.md)。下文2026-11-12及更早状态保留历史语境。

六阶段、18环节、36Task及D01～D06冻结设计保持。2026-11-12阶段01/02/03为ACCEPTED，02已以94cf205归档推送并核验；03六Task、独立QA及两项修复回归完成，最新完整真实库137项通过，27个不同外部场景取得通过证据，主Agent技术验收通过，用户已正式验收03，状态ACCEPTED，03已以62b5eb2归档推送并核验；04已获用户开发授权，当前IN_PROGRESS；05～06未开始，既有凭据/密码复用及P3-01格式遗留按原决定管理。详见 [03技术验收报告](question/03-tool-governance-stage-acceptance.md)。以下旧轮次状态保留历史语境。

唯一有效的V1开发路线图：[六阶段路线图与执行任务](development-roadmap.md)。此前九阶段路线图另存[历史副本](history/development-roadmap-commerce-history.md)，旧详细设计只供历史参考，不得自动带入旧生产级要求或扩大V1。阶段实现细节在逐阶段设计时确认。

## 1. 项目定位与V1范围

暂名 Agent Engine Demo。目标是展示真实的多Agent工程能力，而非建设生产级电商后端。核心五项均为V1必需：ToolRegistry/统一执行、HITL、持久Checkpoint/Interrupt/Resume/完全重启恢复、真实向量RAG、用户隔离的跨会话Store。

栈保留Python、FastAPI、LangChain、LangGraph、PostgreSQL、pgvector、LangGraph Checkpointer和Store。一个FastAPI应用、一个worker，HTTP/执行任务/简单事件队列同进程；同一PostgreSQL实例逻辑区分业务表、Checkpoint、Store、向量索引。不拆微服务。

演示业务限本人订单查询、模拟退款、知识问答。订单/退款是真实本地数据库状态，不是模型编造或内存假成功；无真实资金。Store是三个专业Agent共用基础设施，不新增MemoryAgent。

V1不做完整电商/物流/支付、独立Java后端、企业多租户认证平台、分布式调度、复杂渐进披露、生产预算核算、支付核对补偿。Apifox仅模拟后端调用。

## 2. 有针对性的现状评估（设计时历史基线）

本轮读了当前目录、Runtime/Supervisor/builder/types/State/contracts/transfers/wrapper、工具/持久化/记忆占位、配置/API以及现有设计相关章节。未运行pytest/Ruff、连接数据库、初始化数据或调用模型。现有工作区修改不覆盖、不删除。

| 成果 | 实现事实/证据 | 分类 | 新方向处理 |
| --- | --- | --- | --- |
| FastAPI/config/lifespan | app/main.py、core/config.py已有 | KEEP | 保留无外部配置可启动、SecretStr、资源生命周期 |
| Route→Service→Runtime | api/routes/agent.py、services/agent_service.py已有 | KEEP | 沿用分层，简化执行器方案 |
| Supervisor主图及公共节点 | graph/builder.py、nodes已有 | KEEP | 保留调度与唯一回复出口，不重写成单聊天Agent |
| Agent/Task枚举 | agents/types.py已有四Agent、五Task | MODIFY | 未来AfterSales改Refund角色；ORDER_CANCEL退出V1执行，保持明确不可用 |
| Supervisor决策 | nodes/supervisor.py已有 | MODIFY | 修通用澄清被锁定TaskType、补必要公开AI上下文，维持串行单任务 |
| 主/专业State、父子映射 | graph/state/contracts/transfers、wrapper已有 | KEEP | 输入/结果关联、消息Reducer和工具历史隔离保留 |
| 契约中必填workflow/复杂结果字段 | 有代码，但不等于业务能力 | SIMPLIFY | 会话/thread与task/run优先；workflow退为内部逻辑关联，不建设通用生命周期平台 |
| Runtime执行和历史 | 当前aget_state+ainvoke，uuid5线程，内存Saver | MODIFY | 保留入口，注入持久绑定/Saver；独立task避免断开取消，明确不自动恢复任意运行代码 |
| SSE编码 | streaming/events/formatter已有event/data | KEEP | 中文JSON/安全输出；补少量关联与终态，不建重放服务 |
| 工具Registry/Policy/Executor | tools/*.py仅docstring | KEEP | 保留职责和目录，需真正实现，不能声称已有工具中心 |
| 工具渐进披露设计 | 旧04.2详细方案，未实现 | DEFER | V1直接过滤后绑定少量完整Schema，基础list/get足够 |
| 独立任务、持久调度/fencing | 旧03设计，代码不存在 | SIMPLIFY | 单进程task+会话锁；重启恢复只保证持久中断，不建claim/epoch调度体系 |
| 完整WorkflowRepository状态系统 | workflows模块占位 | DEFER | 只保存session绑定、审批和退款必要事实；不用多状态平台阻挡HITL |
| PostgreSQL连接/迁移 | infrastructure/postgres.py占位，驱动已列依赖 | KEEP | 实现最小池、编号迁移、独立测试库；安装驱动不等于服务就绪 |
| Checkpointer | 只有builder内InMemorySaver，postgres模块占位 | MODIFY | 将Saver注入，04必须Postgres并验完全重启resume |
| 审批能力 | workflows/approvals.py占位 | KEEP | 新04核心，可信决定、绑定原调用、重复审批一致 |
| Store/Memory | infrastructure/store.py和memory/*.py占位 | KEEP | 新05必须真实持久化与跨会话隔离，不以Checkpoint替代 |
| RAG/pgvector | 无knowledge实现，只有旧计划 | KEEP | 新05真实导入、Embedding、检索与来源，不以模型常识代替 |
| 订单三表/物流/RLS | 旧04.1设计未实现 | SIMPLIFY | 订单单表、小样本、owner限定SQL；无完整物流/复杂RLS |
| 用户/审批身份 | 当前仅请求user_id、无认证 | MODIFY | 受控模拟用户＋本地审批入口/服务端审计Actor；普通聊天不能批准 |
| 企业认证/多角色数据库体系 | 旧02/04设计未实现 | DEFER | 保留凭据保护/参数SQL/归属，不建设企业权限平台 |
| 生产预算/Token预留核算 | 旧03/04设计未实现 | SIMPLIFY | 模型轮次/工具次数/单次和总期限/有界重试；usage未知明确记录，不做成本账本 |
| 多订阅Broker/重放协议 | 旧03设计未实现 | SIMPLIFY | 每run简单有界队列，断开不取消；不承诺事件重放/多实例 |
| 模拟退款幂等 | 旧设计未实现 | KEEP | 数据库稳定operation_id与唯一约束，恢复不能重复变更 |
| 支付账本、支付核对/补偿 | 旧方案规划 | REMOVE FROM V1 | 无真实支付，只原子更新模拟退款记录/订单标记 |
| 订单取消业务 | 枚举存在、无业务实现 | REMOVE FROM V1 | 非五项技术核心；明确不支持，不删现有代码 |
| 跨用户隔离/参数校验 | 内部关联已有，业务隔离尚未实现 | KEEP | 订单SQL/审批查询/Store命名空间真实验证 |
| 默认测试骨架 | 现有HTTP/契约/类型/State测试 | KEEP | 后续按变更更新，不为满足旧方案机械补大量测试 |

分类含义：KEEP保留能力或实现；SIMPLIFY降低复杂度；MODIFY调整命名/接口/执行方式；DEFER后置；REMOVE FROM V1只移出开发要求，不删除代码/文件。表中标KEEP的占位模块仍是待开发。

## 3. 新架构及最小模块职责

```text
FastAPI → AgentService → AgentRuntime → Supervisor
                                       ├─ OrderAgent
                                       ├─ RefundAgent
                                       └─ KnowledgeAgent
                                              ↓
                        ToolRegistry → ToolPolicy → ToolExecutor
                                              ↓
                       模拟订单/退款服务、Retriever

共享：Postgres Checkpointer / Postgres Store / pgvector / 用户上下文
```

- Supervisor只路由/澄清/汇总，不持有全量业务工具。
- Specialist采用有界Model→ToolCall→Executor→ToolMessage循环；工具Schema按Agent/用户范围一次过滤动态绑定；所有模型调用经统一入口。
- RefundAgent是当前AfterSales职责的轻量替换，未来明确迁移types/route/prompt/tests；本轮不改枚举，不同时保留两套售后Agent。现有退款结果关联约束可沿用。
- Domain只保留MockOrderService/MockRefundService两个小服务，独立于Graph；普通字段规则、金额/归属和事务保留，不建完整交易模型。
- app/tools复用既有目录真实实现；app/memory、infrastructure复用，knowledge仅在新05需要时创建。
- Runtime持有进程内任务和每thread锁，HTTP只消费简单有界事件队列；正常终态恰好一次done，done不表示workflow永久结束。断开后查询状态/结果，不承诺断点重放。
- 使用LangGraph提供的StateGraph、interrupt、Command、Checkpointer、Store，不再复制一个通用可恢复工作流引擎。

## 4. 最小数据与执行契约（建议）

### 4.1 标识、用户与存储权威

user_id是固定演示用户标识，只适用于受控模拟；不宣称真实登录认证。V1审批入口只用于development/test本地回环演示，服务端Actor仅审计，真实认证延期，production不注册该Router；user_id或聊天同意不能批准。

conversation_id按演示用户绑定稳定thread_id并持久保存。01准备身份/session/context/options，02 AgentRuntime唯一创建正式task_id，续接、审批和恢复沿用原值。workflow_id仅为同值内部兼容别名，无独立生成、存储或生命周期。每次实际执行有独立run_id，request_id命中复用原Run；operation_id持久保护业务副作用。旧Graph只在Runtime正式Task绑定后执行，公共workflow_id字段移除并明确422。

最小业务表：sessions（用户/会话/thread唯一绑定）；demo_orders（owner、amount Decimal、currency、paid/refund状态等少量字段）；refund_requests（owner/order/稳定operation、模拟金额、执行状态/结果）；approvals（原调用快照、可信决定、审批关联）。RAG文档/片段索引与库管理的Checkpoint/Store表各负其责。无库存、商品/物流三表、支付账本。

精确金额和owner查询仍必要；SQL显式owner条件，退款关联FK/唯一键保证归属与幂等。V1不加RLS/复杂数据库角色，迁移/运行权限和测试库隔离保留。上述是建议的最小模型，审核后再细化DDL，不在本轮建表。

### 4.2 简化运行与安全限制

只允许单实例/单worker；同thread输入和resume互斥，待审批时普通聊天409。Runtime不因SSE断开取消已受理task；慢队列可以结束订阅，状态/结果查询兜底。进程中正在运行的非中断代码崩溃不自动重放，启动依据Checkpoint/审批/退款事实显示可恢复等待或需要核对，不能承诺协程恢复。

不建设持久queued调度或全局原子执行平台。Checkpoint保存可恢复图状态；模拟退款以operation_id、数据库唯一约束和本地事务实现业务副作用幂等。Graph节点/ToolCall可能重放，Checkpoint、审批记录与业务库不共享全局事务，不承诺全局Exactly Once。运行期限与模型/工具次数随逻辑任务保存，resume不重置；Token usage只作已知/估算/未知报告，不假报硬上限。

### 4.3 必须实现的HITL闭环

RefundAgent模型产生原生退款ToolCall，先由服务计算/校验可退款金额并幂等创建申请，固定待执行调用的call_id、tool/version、规范参数、参数摘要、operation_id。模型不得裁定金额或批准。

申请创建是审批前的准备记录，只能登记请求/候选金额/待审批状态，不能设置订单已退款、增加已退款金额或写入模拟退款执行成功。只有可信批准并通过执行前复检后，Executor调用原退款工具，才在业务事务中改变退款执行结果和订单退款标记。拒绝只更新审批/申请拒绝，不发生退款副作用。

图节点分开：模型生成/保存调用 → 幂等审批登记 → approval_gate内interrupt → Executor执行已批准的原调用 → 添加对应ToolMessage → 模型完成回复。模型调用与实际退款不能置于同一个会因interrupt恢复重跑的节点里。

本地审批接口从ActorProvider取得审计来源并核验归属/原调用快照，持久保存决定。Command(resume)携带审批引用，gate重新读可信记录，不直接信任客户端resume内容为授权。批准后重新检查Policy/参数及业务状态，执行原call_id/原参数/原operation；拒绝添加拒绝ToolMessage且不退款。若想改金额/目标，须建立新调用和审批，不能复用批准。

interrupt所在节点会重跑，登记必须幂等且interrupt前无实际退款副作用。可信审批后，模拟执行在一个本地事务中复检订单/申请，以operation_id唯一约束和已有结果检查更新退款执行结果/订单标记；成功后下一快照前崩溃，resume按原operation_id返回既有结果，不能再产生业务变更。ToolMessage稳定ID匹配原tool_call_id；恢复时可能再次进入节点/执行器，但通过幂等核验复用结果，不声称Graph或工具函数全局只调用一次。

当前wrapper在恢复时可能重新从父节点进入，request里仍是旧run；未来在Runtime调用配置注入当前run，结果关联以可信当前上下文为准，保留workflow/task/operation。不得用普通新消息重建State，也不得向中断线程ainvoke普通输入。嵌套子图配置传播必须真实测试。

### 4.4 RAG与Store边界

KnowledgeAgent调用注册检索工具：文件→切分→真实Embedding→pgvector→候选5/选3→2400tokens且24KiB证据→三态充分性评估→生成及来源校验→approved_answer；不足则明确无证据。正式采用OpenAI text-embedding-3-small/1536及一致Profile，阈值null，PG/pgvector为唯一后端和知识权威，ES/Hybrid仅未来扩展。来源保留doc/version/chunk/title，不暴露本机凭据/绝对路径；文档指令不能授予工具权限。

Memory V1使用PostgreSQL/AsyncPostgresStore，只保存answer_language、answer_style。用户namespace不含conversation/thread，三个专业Agent共享MemoryReader，统一委托MemoryManager.snapshot读取；显式原Human命令由既有MemoryManage工作流确定性解析和字段校验，形成MemoryCommand，经同Policy/Executor到MemoryManager.apply。Manager负责revision、operation幂等、per-user锁及conflict/unknown。MemoryWriter归V2候选提取/维护，不持Store写权限，需未来独立授权后仍交Manager，V1不实现或依赖。记忆不替代Checkpoint或业务事实，不回滚退款，不新增MemoryAgent或自动持久化。

## 5. 旧设计处理清单

旧九阶段路线图及旧阶段文档统一归档在 `history/`，完整目录见[历史资料索引](history/README.md)。保留历史正文与审核记录，仅修正移动后的相对链接；历史状态中的审核通过只指旧目标，不能自动套用新V1。下表除 `graph-protocol.md` 外，文件名均相对于 `docs/history/`；`graph-protocol.md`继续留在 `docs/`，作为当前实现参考。

| 文档 | 处理及可复用片段 |
| --- | --- |
| development-roadmap.md原九阶段版 | 原文存 history/development-roadmap-commerce-history.md，当前docs根目录路线图为六阶段 |
| 01-1-engineering-and-architecture-baseline-plan.md | 历史参考；可复用环境/工作区保护规则，不再要求全套台账 |
| 01-environment-and-scaffold.md | 历史搭建记录；保留有效启动方法，不作为阶段任务 |
| 01-stage-detailed-design.md | 历史；State映射/安全事件/终态语义可复用，公共API按Demo迁移 |
| 02-stage-detailed-design.md | 历史；池/迁移/归属可复用，完整workflow/权限平台延期 |
| 03-stage-detailed-design.md、03-stage-execution-plan.md | 历史；主图/统一模型/断开语义可复用，guard/claim/epoch/复杂预算移出V1 |
| 04-1-order-service-design.md | 历史；Decimal、owner SQL/幂等种子可复用，完整订单/物流/RLS收缩 |
| 04-2-tool-registry-design.md | 历史；Metadata/注册冻结/Schema可复用，渐进披露延期 |
| 04-3-tool-execution-design.md | 历史；Policy/Executor/ToolMessage关联可复用，审批在新04真正接通 |
| 04-4-order-agent-design.md、04-stage-execution-plan.md | 历史；有界循环和PG联调可复用，原26任务不再为新V1强制要求 |
| graph-protocol.md | 保留为当前代码协议参考，加适用范围说明；不把尚未迁移的角色/字段称为新Demo实现 |

README仅同步定位、当前事实和权威入口，运行命令保留。AGENTS.md已在本轮收敛为Agent Engine Demo指令，保留通用编码/安全要求，明确本文件与六阶段路线图的权威关系；旧生产级范围不得自动成为V1要求。

## 6. 新旧差异及依赖主线

旧设计围绕订单/取消/审批/支付加长治理；新设计以工具、暂停恢复、检索和记忆为验收主线。取消和真实支付移出V1，RefundAgent不退化为“再次发送退款请求”。

开发顺序：运行环境→Runtime/路由→工具/查询→HITL持久恢复→RAG/Store→最终演示。RAG导入在PG/模型和工具接口稳定后可独立准备；审批与Store集成分别在其前置完成后推进。不能用多线开发隐藏未完成的持久恢复。

## 7. 最终演示与验收

1. 用户A询问本人订单：真实Supervisor路由、过滤工具、完整Schema绑定、Executor查询PG，用户B的订单不可见。
2. 用户申请模拟退款：产生原ToolCall，Policy要求审批，真实interrupt保存Postgres Checkpoint，当前流waiting_approval结束；普通聊天不可批准。
3. 完全关闭服务进程、重新启动；管理员批准原申请；Command(resume)恢复同thread/原调用，ToolMessage匹配；按相同operation_id和数据库唯一约束验证退款副作用幂等，重复恢复不会再次改变业务结果。验证重复/相反审批和拒绝不退款，不将此验收解释为Graph、ToolCall和数据库全局原子执行。
4. KnowledgeAgent真实Embedding/pgvector检索，回答带来源；无证据不编造；文档注入不提升权限。
5. 用户A在会话1保存偏好、在会话2被读取；用户B不可见；重启后Store仍存在。三个专业Agent通过同一记忆入口获取，不复制成三套存储。
6. 全链路真实模型+本地模拟业务；默认测试可控替身，真实模型单独记录。SSE断开不取消退款，done只表示本run结束，未实现业务明确不可用。

以上均为未来验收，当前未执行。关键PG/向量/Store/重启用例不能只用Mock证明。

## 8. 已采用范围与决策分类

- 项目定位和六阶段收缩路线已确认，详见路线图；原编号不再机械映射，不因确认规划启动开发。
- AfterSales未来改Refund；订单取消退出V1，不删现有枚举/文件。
- 只做订单少量字段和模拟退款申请/操作记录，无复杂RLS/物流/支付账本。
- 受控模拟用户＋本地审批入口/服务端审计Actor，V1不对公网生产提供真实身份保证。
- 单进程task/会话锁/简单SSE队列，不做持久任务调度或事件重放；仅持久中断支持重启resume。
- 新04接PG Checkpointer，之前内存模式只开发验证；最终不允许以内存验收替代。
- 工具直接按Agent/权限过滤绑定，复杂发现延后；保留统一模型入口和轻量限制。
- 已采用接口见01～06详细设计，UTF-8 md/txt、两字段演示偏好、本人已付未退款的模拟资格及现有API/Schema不再列为待重新选择。
- Embedding模型/1536维、RAG初始参数与充分性、审批30分钟已正式采用，管理员认证V1延期，见06第13.2A，已无这四项待决参数。
- 实施验证包括实际服务商/API、镜像扩展、LangGraph父子恢复、Store资源关闭及Apifox导出，责任按06第13.2B及前序Task。
- V1范围外继续包括生产认证、分布式治理、通用恢复平台和复杂工具披露，不阻塞当前逻辑设计收敛。

上述决策分类保留设计轮次语境。设计已获最终确认，当前实施及验收状态以页首和主 Agent 复核记录为准。

以下为历史修订记录，待确认参数及旧管理密钥方案仅反映当时决策，已由末尾最新正式确认记录替代。

## 9. 本轮变更记录

以下记录描述历史轮次，等待设计等表述不代表当前待办。当前状态以页首、第8节及末尾最新记录为准。

上一轮：新增本定位/评估文档、保留九阶段历史、改六阶段路线图并加历史标记。本文档体系收敛轮：更新AGENTS项目指令、权威关系和有效约束；统一README/路线图确认状态；补申请与执行分界及业务幂等语义；历史文件保持原路径和内容。没有删除旧代码/文档，没有修改Python、依赖、数据库或测试；未运行测试、迁移、种子、真实模型或Apifox。本轮仅文档整理，开发未启动。

2026-11-08 文档归档轮：将12份旧路线图、阶段设计及搭建记录移入 `docs/history/`，保留历史正文并修正相对链接；新增历史索引，更新README、AGENTS及当前定位/路线图的入口。上段“保持原路径”仅记录归档前一轮状态，本轮以新归档路径为准。三份核心文档继续保留在docs根目录，不改变架构与六阶段路线图，不修改业务代码、不执行测试、迁移或模型联调。当前状态仍为：**项目定位与整体路线图已确认，等待逐阶段详细设计。**

## 2026-11-09 全项目审查第一轮整改记录

同步当前状态、第4.1节ID权威和第8节决策分类，保留六阶段定位和历史归档边界。

六阶段、18环节、36Task保持不变。本轮仅修改Markdown设计、规范及导航，未检查实际开发进度，未修改业务代码、配置、依赖、数据库或迁移，未运行测试、代码检查、服务、容器、模型或Apifox联调。四项决策仍推荐待用户确认，设计尚未冻结。第一轮修订完成后停止，最终只读复核由用户另行授权。

## 2026-11-09 最终技术决策确认与冻结准备记录

同步身份/审批边界、已确认检索及期限参数、认证延期和等待最终冻结状态，保留范围与历史记录。

用户正式确认前三项技术参数并明确延期管理员认证，已无这四项待确认决策。历史记录中的待确认或管理密钥方案仅供追溯，当前以本文规范及本记录为准。LocalDemoApprovalActor固定审计值采用local-demo-approval，沿用approver_id存储字段，不构成真实身份认证或授权。

六阶段、18环节、36Task和既有八项设计结构不变。仍为纯逻辑设计，只修改Markdown，未检查实际开发进度，未修改代码、SQL、实际配置或依赖，未安装、测试、检查代码、启动、数据库操作或联调。实施验证尚待授权，当前等待用户最终设计冻结确认，设计确认不授予任何Task开发权限。本轮完成即停止。

## 2026-11-09 Memory V1与V2职责收敛记录

第4.4节明确Memory V1仅两个偏好字段、Reader共享和Manager统一持久化/版本/幂等，显式命令完整保留，MemoryWriter只作V2候选维护及未来独立授权边界。

V1保留AsyncPostgresStore、两偏好字段、用户Namespace、跨会话/跨Thread、revision、operation_id/digest/expected_revision/last_mutation、per-user锁及conflict/unknown和原Checkpoint写前边界。显式解析独立于V2，旧记录中的Writer为当时V1写路径称谓，现已统一为MemoryManager及显式命令流程，不代表V2已实现。

六阶段、18环节、36Task和八项设计结构保持，5.3.2仅授权更名，无新增Agent、Graph或Task。此前四项最终技术决策不变。本轮仅改Markdown，未检查开发进度，未修改Python/SQL/依赖/配置，未测试、迁移或联调；实现及冻结不在本轮授权内，完成后停止并提交用户审核。
