# V2 02 Context Engineering：完整逻辑设计

状态：**DESIGN APPROVED**。

设计验收日期：2026-11-17。用户已验收整体设计及五项定向整改，批准保留三个二级环节、六个 Task 和依赖关系。本文归档已审核方案，包含文末六项强制约束。

**本状态仅代表逻辑设计验收，不代表开发授权、实现完成或真实运行验收。02 当前不得标记 VERIFIED。** 所有真实 LangMem、PostgreSQL、Checkpoint、文件发布及模型调用兼容性验证均未在本轮执行，属于未来开发验收。本轮仅新增本文，不修改业务代码、数据库、运行配置或依赖，不执行测试、联调、部署、Git 提交或推送。

归档后停止。未经用户明确授权，不进入 03 逻辑规划或任何正式开发。

## 1. 依据、V1 现状与改造边界

依据：[项目定位](../../v1/agent-engine-demo-plan.md)、[V1 路线图](../../v1/development-roadmap.md)、[V1 D05](../../v1/v1-05/05-rag-memory-detailed-design.md)、[当前状态](../../STATE.md)、[V2 01 已批准设计](../v2-01/v2-01-knowledge-rag-enhancement-detailed-design.md)，以及设计阶段只读核实的源码。本文不变更 V1 阶段验收及 Git 归档状态，不把历史设计参数当作现行实现。

### 1.1 当前实际实现

| 模块 | 当前行为 |
| --- | --- |
| `app/graph/specialists/knowledge/memory.py` | 显式偏好管理子图，处理读取、修改、删除语言与风格偏好；不是历史压缩 Graph |
| `app/memory/manager.py` | 用户 Namespace、revision、operation 幂等、冲突与未知结果的统一管理 |
| `app/memory/reader.py` | 委托 Manager 读取两项偏好 |
| `app/graph/specialists/preferences.py` | 三个专业 Agent 经现有策略/执行器读取偏好 |
| `app/graph/state.py` | messages 使用 add_messages，保存当前 Task 消息 ID |
| `app/graph/transfers.py` | public_task_messages 仅提取当前 Task 公开消息，最多返回最近12条 |
| `app/infrastructure/sessions.py` | 按 user_id＋conversation_id 持久绑定 thread_id |
| `app/infrastructure/checkpoint.py` | PostgreSQL Saver 保存执行快照，支持原审批暂停和恢复 |
| `app/runtime/model_gateway.py` | 模型调用、尝试次数、超时及用量报告的统一入口 |

当前没有 Markdown Segment、Archive Repository、会话摘要或 LangMem 依赖。V1 偏好写入绑定 MEMORY_MANAGE 节点，依赖写前 Checkpoint；不能删掉 Graph 后裸调 Manager 冒充等价替代。

### 1.2 四类数据与权威位置

| 数据 | 权威位置 | 本阶段处理 |
| --- | --- | --- |
| 执行状态、审批中断、工具与副作用关联 | Checkpointer及业务数据库 | 保留原恢复职责 |
| 显式用户偏好 | 原 PostgreSQL Store／MemoryManager | 保留结构化持久化能力，替换业务入口 |
| 本会话公开历史原文 | 热消息及已发布 Markdown Segment | 增加归档与有界恢复 |
| 摘要与上下文版本 | Context Repository | 新增派生数据及其来源关联 |

不把摘要当作当前业务事实，不把 Archive 替代 Checkpoint，不从历史自动提取并写入长期偏好。保持 Supervisor、Service、Runtime、Policy、Executor、Checkpointer 核心边界；不增加 Supervisor Loop、Graph节点或多 Agent 并行，不改变退款审批、资格、幂等和未知结果核对协议，不设计03工具渐进式披露或独立Evaluation/Trace平台。

## 2. 定向修订结论

| 项目 | 修订前 | 已批准方案 |
| --- | --- | --- |
| 维护时机 | 主要放在 Supervisor 准备阶段 | 区分受理前读取、节点前构建、运行内必要压缩、任务后维护 |
| Graph更新 | 归档、摘要、裁剪衔接不够明确 | 维护发布候选版本，Graph在指定边界采纳 |
| 一致性 | pending/ready为主 | 增加ContextRevision发布、采纳和完成回执 |
| Memory Graph | 保留原业务子图 | 新请求退役该路由和子图，改用显式偏好控制入口 |
| 历史恢复 | 引用优先、候选规则概括 | 精确关联优先，有界候选及一次邻接扩展 |
| LangMem预算 | 全计入当前Task | 运行内使用当前预算，任务后使用独立持久预算 |
| 旧Checkpoint | 兼容读取 | 按其绑定版本恢复，禁止自动套用最新上下文 |
| 失败处理 | 保留原文 | 明确部分成功、重复范围、重放、重启和过期版本处理 |

## 3. 架构与组件职责

```text
可信身份 + SessionBinding
          │
          ▼
原 Service / Runtime ───────── 原 Checkpointer
          │                         │
          ▼                         └─ 执行/审批恢复权威
原 Graph 现有节点
          │
          ▼
ContextManager
  ├─ ArchiveRepository ─ PostgreSQL元数据/版本/回执
  ├─ ArchiveStore ────── 本地Markdown
  ├─ LangMem Adapter ─── 原ModelGateway
  └─ ContextBuilder ──── 按调用目的组织模型输入

偏好控制入口 → PreferenceService → Policy/Executor
                                  → 原MemoryManager/Store
```

### 3.1 Runtime

负责会话执行互斥、受理时序、正式Task/Run、预算、恢复门禁和安全边界。受理前只读上下文；向Graph提供核验后的引用；正常完成后登记维护；核对Graph实际采纳的Checkpoint并补回执。不生成摘要内容，不直接写Saver底表。

### 3.2 ContextManager

选择允许维护的已完成历史范围，协调Archive/Summary/ContextRevision发布，核验候选与Checkpoint是否匹配，协调有界恢复，生成Graph采纳计划。不自行执行Graph，不决定审批、订单归属或退款结果。

### 3.3 ContextBuilder

输入当前任务、已允许的历史视图、工具Schema及必要事实，计算预算并组织完整模型输入，或返回明确预算不足。**不写文件、不提交数据库、不调用摘要模型。** 需要压缩时由调用节点请求ContextManager，完成后重新构建。

### 3.4 ArchiveStore与ArchiveRepository

ArchiveStore负责Markdown编码、临时写入、原子发布、读取和哈希检查；它不是原PostgreSQL Store。ArchiveRepository负责会话范围过滤、Segment/Summary/Revision及维护记录，不接受模型提供的任意路径。

### 3.5 Graph节点与LangMem适配器

现有Model Node在调用前使用Builder，必要时请求运行内压缩，并保存视图和用量。仅指定入口可采纳会话版本并裁剪父图历史。LangMem适配器通过现有ModelGateway逐次调用模型，不建设新摘要Agent或Summarization Graph。

## 4. Isolation与历史信任等级

所有上下文、摘要和Archive查询以服务端SessionBinding的 `user_id + conversation_id` 为隔离键。不能从模型、摘要正文、Markdown或archive_ref前缀取得可信身份。

- 同用户不同会话不自动共享历史与摘要；不同用户相同conversation_id完全隔离。
- 三个专业Agent可使用同一可信会话内按目的筛选的历史。
- 显式偏好继续按原user_id Namespace跨会话共享，这是明确例外。
- 不扩展企业租户ACL或跨会话聊天搜索。

历史摘要和恢复原文都是低信任背景，不能授予审批/工具权限，不能覆盖Task、Run、身份、调用绑定或当前事实。历史订单号只可帮助理解，歧义时澄清；不能仅因摘要提及某订单就确定并执行退款。KnowledgeAgent仍只引用本次有效Evidence，历史正文不能伪装知识来源。

## 5. 四种触发时机与完整调用链

### 5.1 请求进入、正式受理前：只读

```text
Route → Service核验身份/SessionBinding
→ Runtime取得会话执行权
→ 读取Graph Checkpoint
→ 检查暂停、活动任务与不确定状态
→ ContextManager读取Checkpoint绑定的上下文版本
→ 核对可采纳的已发布候选
→ 正式建立Task/Run及其预算
```

此阶段没有正式Run模型预算，不调用LLM，不归档、不压缩、不裁剪、不隐式启动维护。Repository最新发布版本只是候选，不能自动覆盖Checkpoint引用。

### 5.2 正常Graph入口：采纳已发布版本

在原Supervisor准备边界、尚未执行工具时核对候选的base_revision和消息范围，确认Archive/Summary就绪，生成采纳计划。现有节点在同一次状态更新中返回ContextRef及明确的旧消息移除，由Checkpointer同步提交。

不能先删消息再写摘要引用。已有工具或副作用执行后，不再切换整个会话的上下文版本；不增加Graph节点。

### 5.3 Model Node调用前：构建与必要压缩

```text
现有Model Node → ContextBuilder检查完整输入
  ├─ 能放入 → ModelGateway
  └─ 放不入 → ContextManager检查可安全压缩历史
             → 使用当前Run预算必要压缩
             → 重新构建
             → 仍放不入则明确失败或澄清
```

优先压缩已完成历史，不卸载当前活动Task。当前任务必需消息、待处理调用或必要事实本身超预算时，不以截断掩盖问题。在专业节点内部生成的本次调用压缩视图保存来源、摘要引用和输入哈希，但不裁剪父图消息、不推进会话版本。

### 5.4 已完成Task后：独立维护

```text
Graph同步完成
→ Runtime确认最终状态及无未决执行
→ 结算Run、发布业务结果
→ 登记可重入维护工作
→ 释放执行权
→ 有限维护执行器尝试取得同一会话维护权
→ 重新核对最新Checkpoint
→ 发布Archive
→ 独立预算下生成Summary
→ 发布ContextRevision
→ 等待下次正常Graph执行采纳
```

不改已结算Run，不延迟或撤回业务成功，不在维护中直接裁剪Graph消息。首版单进程、有限维护能力，不引入新服务或通用调度平台。同会话维护与执行互斥；维护未取得权利时新请求可先行，维护随后重新校验或延期。模型调用期间不持有长数据库事务。

### 5.5 状态许可表

下表归档/压缩对象均为已完成历史，不含当前活动Task。

| 状态/边界 | 读取/构建 | 归档/压缩 | Graph裁剪 |
| --- | --- | --- | --- |
| 请求未受理 | 只读元数据与已有内容 | 不允许 | 不允许 |
| 正常运行入口、尚未执行工具 | 允许 | 必要时允许，计入当前Run | 入口采纳合法版本时允许 |
| RUNNING中普通Model Node | 允许 | 仅必要压缩，计入当前Run | 不推进会话版本，不裁剪父图 |
| NEEDS_INPUT/WAITING_INPUT | 保留原Task上下文 | 首版暂停该会话维护 | 不允许 |
| COMPLETED/REJECTED且Checkpoint已确认 | 允许 | 允许独立维护 | 维护不裁剪，下次正常执行采纳 |
| FAILED但经核实无未决执行 | 允许 | 仅维护先前安全完成历史 | 等待显式新任务入口 |
| FAILED且执行结果不确定 | 仅原恢复所需读取 | 不允许 | 不允许 |
| WAITING_APPROVAL/PAUSED | 原绑定视图 | 暂停该会话维护 | 不允许 |
| resume/reconcile | 原恢复上下文 | 不新压缩、不切换版本 | 不允许 |
| 进程关闭中 | 有限结算与记录 | 不启动新模型调用 | 不允许 |

Run结束不等于Task完成，也不等于执行已确定安全。现有Runtime的_uncertain门禁必须保留，不能仅凭FAILED启动维护。

## 6. Offloading与Archive数据契约

### 6.1 范围与Segment边界

仅归档父图公开用户消息和经过Response边界批准的公开回复。不归档为通用上下文：内部推理、专业私有工具历史、待执行调用、审批凭据、恢复标记、未验证草稿及敏感原始工具数据。这些执行资料仍由现有存储负责。

Segment为同会话连续公开消息范围，只选已结束Task的历史前缀，保留近期公开交互，不拆开正常问答，不卸载当前Task、澄清中或审批中的消息。超长单消息不能截断后冒充完整归档。Segment大小、近期保留量和模型预算集中配置，区分精确与估算Token。

### 6.2 身份与Markdown

逻辑标识为 `user_id:conversation_id:segment_id`，使用archive_ref，不增加独立archive_id。身份字段允许冒号，组成部分必须无歧义转义；数据库同时保存独立原始身份列，权限不靠字符串前缀判断。

segment_id按来源消息ID范围确定性生成并核对内容哈希；同范围重试复用，相同ID不同内容报告冲突。Markdown包含格式版本、archive_ref、所有者、消息范围/数量、可确认的Task/Run、来源Checkpoint、消息ID/角色/顺序及完整正文。正文中的标题或伪造指令不能升级为可信元数据；编码恢复须往返一致。

数据库保存相对路径和文件哈希。系统生成路径并限制在归档根目录，模型不获得本机绝对路径或任意文件读取权限。文件写入采用同目录临时文件、刷新与原子发布，文件系统/PG/Checkpointer之间不宣称跨资源原子事务。

## 7. ContextRevision、Summary与Graph提交协议

### 7.1 四类身份

| 对象 | 身份/用途 |
| --- | --- |
| Archive | archive_ref，标识原文Segment |
| Summary | summary_id，关联实际覆盖的archive_refs |
| ContextRevision | 会话内不可变发布版本，绑定原文、摘要及拟卸载范围 |
| Graph ContextRef | Checkpoint实际采纳的版本引用 |

ContextRevision包含user_id/conversation_id、revision/base_revision、来源Checkpoint、消息ID范围与内容摘要、archive_refs、summary_ref、策略/模型/Prompt版本、发布状态及采纳回执。版本号不授予覆盖权，较大版本不能强行替换旧Checkpoint绑定。

Summary保存身份、会话、版本、文本、archive_refs、实际消息覆盖范围、父摘要关联和输入哈希。只将真正成功处理的范围加入引用；“已归档”不等于“已总结”。LangMem内部对象转换为项目序列化契约，不直接作为长期Checkpoint协议。

### 7.2 状态迁移表

| 对象 | 准备中 | 已发布 | 已完成/其他 |
| --- | --- | --- | --- |
| Archive | PREPARING | READY：文件存在、哈希核对、元数据提交 | 失败可核对恢复；完整性错误不可使用 |
| Summary | BUILDING | READY：文本、覆盖范围及输入哈希提交 | 调用失败/预算耗尽另记 |
| ContextRevision | PREPARING | PUBLISHED：所有依赖ready，关联校验通过 | APPLIED：确认Graph采纳；STALE：基线不再适配 |
| 维护尝试 | PENDING→RUNNING | 不适用 | SUCCEEDED/FAILED/EXHAUSTED/INTERRUPTED |

**PUBLISHED严格不同于APPLIED。** 前者可申请采纳，不能证明Graph已裁剪。后者必须有实际Checkpoint采纳依据；即使APPLIED也不代表允许删除原文、旧摘要或历史Checkpoint。

### 7.3 完整提交顺序

1. 取得会话执行/维护权，读取可信Checkpoint。
2. 记录base_revision、来源范围和内容哈希。
3. 确定性登记Archive，发布并核验Markdown，提交READY。
4. 通过LangMem生成摘要，记录真实覆盖范围，提交Summary READY。
5. Repository事务核验全部关联，发布ContextRevision。
6. 后续Graph正常入口重新核验基线与范围。
7. 同一Graph状态更新提交ContextRef及消息裁剪。
8. Runtime读取已提交Checkpoint，记录APPLIED回执。

任务后维护只到第5步，不调用Graph更新来提前裁剪。热消息移除使用现有Reducer支持的方式，不直接更新Saver底表。旧Checkpoint仍可能保留全文；本阶段不实现历史快照清理或隐私擦除。

### 7.4 可验证不变量

1. 每个被裁剪消息都有已发布、可核验Archive。
2. Graph引用Summary只能关联同用户/会话的ready Archive。
3. 摘要覆盖范围不超过实际成功处理范围。
4. ContextRef与对应裁剪共同提交。
5. Repository发布本身不能改变Graph当前版本。
6. 审批/未知结果恢复版本不被最新版本替换。
7. 重复范围不重复归档，不无条件重复模型调用。
8. 回执丢失不等于Graph提交失败，必须读取核对。
9. 旧Checkpoint可引用其原版本，不因版本旧自动删除依赖。

### 7.5 部分成功、重放与重启

| 情形 | 恢复规则 |
| --- | --- |
| Archive成功，Summary失败 | 保留ready原文，不发布完整Revision、不裁剪；重试复用原文并使用原工作剩余预算 |
| Summary成功，Revision发布失败 | 核对输入哈希、策略和覆盖后复用Summary，不重新调用模型 |
| Revision发布，Graph未采纳 | 保留PUBLISHED；原消息完整，后续重新校验 |
| Summary成功，Graph裁剪提交失败 | 先读Checkpoint；未提交则原消息仍在，已提交则补回执，不能盲目再移除 |
| Graph采纳，APPLIED回执失败 | Graph引用为事实依据，补回执，不重跑摘要 |
| 节点重放 | 同版本已采纳则不重复移除；否则核对当前消息和来源范围 |
| 重启时维护中断 | 恢复记录/预算并核对文件、摘要、Checkpoint，不能获得免费新预算 |
| 基线变化 | 仅增加范围外消息且可证明兼容时重新核验；冲突则STALE，禁止强制裁剪 |
| 文件缺失/哈希错误 | 完整性失败，禁止继续据此裁剪或恢复 |
| 同范围重复提交 | 按会话、消息范围、内容哈希和策略去重；ID对应不同内容为冲突 |

### 7.6 旧Checkpoint、审批及未知结果

有ContextRef则读取该不可变版本；没有则按V1处理，**不得自动注入Repository最新摘要**。审批恢复与副作用未知结果核对不执行上下文升级，不重写原调用、参数、计数或绑定。

恢复到新的安全边界后才允许重新规划维护。本阶段不提供任意旧Checkpoint覆盖当前会话的时间旅行接口；受控历史恢复也不能据此倒退Repository发布头。归档失败不能把已提交退款成功反向改成失败，更不能触发重发。

## 8. Compaction与ModelGateway预算

### 8.1 LangMem接入与质量

使用LangMem异步短期消息压缩，适配器通过现有Gateway调用，不增加Graph节点。可复用asummarize_messages/RunningSummary机制，但依赖、API及当前模型兼容性仍需未来验证，不能因官方范围看似匹配就宣称通过。参考[官方API](https://langchain-ai.github.io/langmem/reference/short_term/)及[依赖声明](https://github.com/langchain-ai/langmem/blob/main/pyproject.toml)。

摘要保留讨论主题、明确需求/约束、完成与未完成事项、必要标识及来源、冲突与不确定性；不把推断写成事实。旧偏好操作可完整归档，但摘要/恢复不能把它当作当前偏好命令，当前偏好来自Manager。

预检摘要输入，不能依赖内部裁剪隐藏遗漏；单个完整交互超过摘要输入能力则原文可归档，但不能冒充完整压缩。摘要失败且完整原文仍可放入预算时可继续原文；否则明确上下文准备失败，不静默丢弃历史。

### 8.2 运行内必要压缩预算

预算所有者是当前正式Task/Run。使用原尝试次数、剩余期限和累计用量，包含LangMem附加调用与重试；失败也记录已消耗尝试及known/estimated/unknown用量。不能借维护预算继续当前业务，不因压缩重置Task预算。审批恢复和未知结果核对不启动新摘要调用。

### 8.3 Task后维护预算

所有者是独立maintenance_id，关联来源Task/Run，但不新建业务Task。持久记录工作/来源范围、预算配置版本、允许尝试与期限/输出限制、已预留/实际尝试、真实用量和状态，关联Archive/Summary/Revision。

已审核方案的维护初始上限为**最多2次模型尝试、总期限30秒**，包含重试及LangMem附加调用。单调用期限不超过维护剩余期限或Gateway限制。输入/输出Token上限依据实际模型能力集中固定；没有有效上限不启用模型维护。这些是未来配置要求，不是当前运行配置或已测性能。

### 8.4 统一治理与重启

Gateway支持task_run或context_maintenance执行所有者，不新增AgentType，不伪造Task。维护模型请求发出前持久预留尝试，返回后记录结果；输出限制在实际调用层明确设置，不能把LangMem摘要预算当作输出硬限。

- 中断后已预留尝试不退回，未知Token不记零。
- 同一来源/策略的逻辑工作复用原记录，重启或更换maintenance_id不能重置额度。
- 预算耗尽标记EXHAUSTED，不自动创建新工作无限重试。
- 运行与维护不共享可互相借用的额度；所有调用均通过Gateway。

持久维护记录是必要预算/恢复证据，不建设独立Trace或成本账本平台。

## 9. Archive定位、恢复与注入

### 9.1 精确关联

优先顺序：summary_id→archive_refs→Segment；同会话task_id→公开消息范围→archive_refs；消息ID/范围→Segment记录。一个Task跨多个Segment时返回相关引用。V1关联不可靠时标记未知，不猜测。

### 9.2 有界候选恢复

1. 先查当前摘要范围和最近完成Task。
2. 根据明确Task、消息锚点或时间顺序筛选。
3. 只在该会话选有限Segment元数据，按锚点优先、近期次之稳定排序。
4. 必要时只扩展一次相邻Segment。
5. 达候选数、读取字节或Token上限即停止。

上限集中配置，不能不断扩大重试直到全部历史。歧义或证据不足则询问Task/话题。**不承诺任意历史语义搜索，不建设聊天历史向量库，不复用01知识库索引存私聊。**

模型提供的archive_ref只是建议，服务端重新核验所有者、ready、根目录和哈希；模型不能决定文件路径。恢复按消息ID去重，优先完整相关交互。

### 9.3 注入与预算

Builder组织可信系统指令、当前Task/Pending、经验证业务事实/Evidence、独立低信任历史区域及当前Task必需消息/私有历史。历史不能伪装当前HumanMessage或进入task_message_ids。

可用历史预算=模型窗口－输出预留－可信Prompt－完整工具Schema－当前任务必需消息－必要事实/Evidence。优先保证当前任务；按完整交互加入历史，不任意截断。必需恢复放不下则明确失败或澄清，记录实际注入范围。具体预算在适配Task依实际ChatModel能力固定，不虚构已验证数值。

Supervisor可用背景理解指代；OrderAgent重查当前订单事实；RefundAgent不以历史改变审批/目标绑定；KnowledgeAgent历史不作Evidence，也不放宽01冻结Query来源，指代不清先澄清。本阶段不设计工具动态筛选。

## 10. V1 Memory Graph退役与偏好替代

### 10.1 方案比较与结论

| 方案 | 优点 | 代价/结论 |
| --- | --- | --- |
| 保留Memory Graph | 原聊天入口和恢复改动少 | 仍把偏好当独立Agent业务，不采用 |
| 显式偏好入口 | 职责清楚、无LLM路由成本 | 必须替代写前记录、策略与未知结果核对；采用 |
| 自由文本自动提取偏好 | 交互灵活 | 增加误写/授权，本阶段不采用 |

**新请求撤销MEMORY_MANAGE路由和Memory Graph装配，保留answer_language、answer_style与原MemoryManager持久化能力。** 不只是改名为另一个业务Graph。

### 10.2 结构化入口与控制链

拟用接口：

| 入口 | 功能 |
| --- | --- |
| POST /agent/preferences/read | 当前用户偏好与revision |
| POST /agent/preferences/mutations | 明确修改、删除单项、清空 |
| POST /agent/preferences/operations/{operation_id}/status | 核对原操作 |

写请求含操作、字段/值、operation_id、expected_revision。可信身份和memory:read/write仍由服务端核验，不允许指定其他用户。

调用链为可信身份/权限→PreferenceService→持久命令回执→同Policy/Executor受控控制入口→原Manager/Store。新增可信控制上下文，只允许偏好工具，不能伪造KnowledgeAgent/Task/Run以绕过旧约束。保留用户Namespace、revision、预期版本、operation幂等、互斥和unknown语义。

last_mutation区分旧Task操作与新控制命令来源，旧记录可读，新记录保存真实命令身份，不把命令ID塞入task_id。兼容契约在2.1.1固定，不批量覆盖现有偏好。

### 10.3 替代写前Checkpoint

命令回执状态为PREPARED→EXECUTING→APPLIED/CONFLICT/UNKNOWN，写Store前持久绑定用户、操作ID、参数摘要及预期revision。Store与回执之间不宣称全局原子。

响应丢失使用原operation_id核对；Store成功而回执失败依据原操作关联恢复；无法证明结果则UNKNOWN，不重新执行。未知操作未解决时阻止会破坏核对依据的后续同用户写入。“当前值暂未变化”不能证明写入未发生。

### 10.4 入口兼容变化与切换

从Prompt、公开路由Schema、Agent/Task映射及装配移除新MEMORY_MANAGE请求。原严格聊天偏好命令在LLM前识别并返回明确接口迁移提示，不静默忽略、不执行旧Memory Task。Apifox说明迁移到新入口。**能力保留但旧聊天写入口不再原样执行，这是已审阅的显式兼容差异。**

切换前不能有活动、待补充或结果未知的旧Memory Task；需由旧版本完成或经用户处理，不能删掉恢复路径强行上线。旧枚举仅作历史反序列化兼容，不再对新业务路由开放，不长期装配两套Graph。

### 10.5 旧会话与偏好迁移

逐会话、可重入迁移，不批量重写Checkpoint。活动/澄清/审批任务保持原样；到安全边界后读取可确认公开历史，利用Checkpoint关联恢复Task/类型，按固定消息身份归档；原文和摘要就绪才裁剪。

V1消息元数据不足时不凭文本猜测。可可靠关联者正常迁移，无法可靠关联者保留原文并标记不完整，不自动当可信指令或偏好；历史快照不足则说明覆盖范围。

同会话不同已完成Task可读取历史背景，是相对V1的明确变化。new_task切换目标但不自动清空会话历史，不继承旧Pending/entities/Task身份；完全隔离使用新conversation_id。测试应检查旧目标不能成为当前权威指令，不能以“模型绝不看见任何旧文字”代替V2契约。

## 11. State与数据设计

Graph建议增加context_schema_version、context_revision、context_summary_ref、context_view、public_message_metadata、context_status，按明确版本覆盖或按消息ID更新，不无界累积。元数据只保留热消息关联。SpecialistInput.messages仍为当前Task，历史独立字段显式传递，不合并全部子图State。

Repository存储会话上下文状态、Archive、Summary、ContextRevision及必要维护预算/采纳回执；偏好入口增加命令回执。具体物理表组织在契约适配中确定，不预建通用调度/审计平台。所有对象显式关联用户/会话，来源内容和版本可核验。

## 12. 三个二级环节、六个Task与依赖

以下为未来开发计划，不构成当前执行授权。

| 环节/Task | 交付与步骤 | 更新后的验收标准 |
| --- | --- | --- |
| **2.1 Isolation与Archive基础** | | |
| **2.1.1 身份、契约与依赖适配** | 固定隔离、Revision/Summary/Archive、维护所有者、偏好控制契约，适配LangMem与Gateway | 不伪造Task/Agent；依赖不盲目升级；旧记录可读；运行/维护预算分离 |
| **2.1.2 Segment归档与发布恢复** | Markdown、定位元数据、确定性范围、文件/DB发布、有界恢复 | 原文往返一致；重复范围复用；故障不丢消息；候选严格有界；拒绝跨身份和任意路径 |
| **2.2 Compaction与Checkpoint安全** | | |
| **2.2.1 LangMem压缩与摘要关联** | 两类压缩入口、Gateway适配、覆盖关系和持久维护用量 | 每次调用计数；重启不清预算；Archive成功/Summary失败可恢复；无虚构覆盖、隐式截断、无限重试 |
| **2.2.2 热历史裁剪与恢复兼容** | Revision采纳、Graph同步状态更新、APPLIED回执、状态门禁 | 发布不等于采纳；提交失败读回核对；重放幂等；旧Checkpoint不套最新摘要；审批/未知恢复零维护 |
| **2.3 Retrieval/Injection与迁移验收** | | |
| **2.3.1 跨Agent上下文构建** | 读取/构建/维护接线、预算不足、偏好新入口及Memory路由退役 | Builder无写副作用；历史不冒充当前消息；偏好CRUD/幂等保留；无新Memory Task；旧活动任务未处理不切换 |
| **2.3.2 迁移与真实阶段验收** | 渐进迁移、完整故障矩阵、真实模型/PG/文件、必要V1回归 | 功能/摘要质量/资源分别结论；新旧入口差异明确；重复范围/重启/部分提交证据完整；代码正确不代替保真 |

依赖保持：`2.1.1 → 2.1.2 → 2.2.1 → 2.2.2 → 2.3.1 → 2.3.2`。未来获开发授权后Implementer→独立QA串行，主Agent复核，不能以设计批准启动开发。

## 13. 阶段验收设计

### 13.1 固定场景与层次

单元可控替身、真实PG/文件集成、真实LangMem/模型和必要完整回归分开。固定夹具包括跨Task指代、跨Agent主题、订单号/否定约束、矛盾与未解决事项、偏好修改后删除、伪造审批/注入、超长输入与预算不足。

隔离检查同用户跨会话、跨用户同名会话、伪造引用、含冒号/中文/路径字符身份与路径逃逸。文件/数据库/Checkpoint各提交边界故障覆盖第7节矩阵，验证原文、版本及回执不变量。维护验证重启不清预算、耗尽不无限重试、失败尝试及未知用量照实记录。

### 13.2 分项结论

- 功能正确性：隔离、覆盖、引用、预算、发布/采纳和恢复协议。
- 摘要质量：关键事实/约束保留、不增加事实、冲突与不确定性正确表达。
- 使用收益：真实输入Token变化、压缩耗时、恢复效果及资源。

摘要更短不等于正确；引用有效不等于语义保真。保留失败/未执行记录，不删除难例掩盖遗漏，不用代码正确替代质量验收。

### 13.3 V1兼容门禁

保留偏好CRUD、跨会话共享、revision/幂等/unknown；订单归属与当前事实；退款审批、重复恢复、未知结果核对；普通消息不能批准；KnowledgeAgent八节点与来源验证；SSE断开不取消执行；预算/互斥；旧Checkpoint及持久化读取。偏好聊天入口变化按第10节明确验收，不伪称原入口完全兼容。遵守原数据保护及完整质量门禁，不扩大seed授权。

## 14. 文件规划

| 拟修改/新增范围 | 职责 |
| --- | --- |
| `app/context/manager.py`、`builder.py`、`models.py` | 生命周期、视图与版本契约 |
| `app/context/archive_store.py`、`repository.py` | Markdown及会话范围数据/发布回执 |
| `app/context/compaction.py` | LangMem与Gateway桥接 |
| `app/graph/state.py`、`contracts.py`、`transfers.py` | 历史独立字段、消息元数据、父子映射 |
| 原Supervisor/专业Model Node | Builder与运行内必要压缩接线，不增节点 |
| `app/runtime/model_gateway.py`、`context.py`、`agent_runtime.py` | 所有者、只读准备、互斥、有限维护及Checkpoint核对 |
| 偏好Route/Service及命令回执 | 结构化读取/写入/删除/状态入口 |
| `app/tools`必要契约/策略/执行适配 | 偏好控制上下文，保留同一治理入口 |
| Supervisor路由/Prompt、类型与Graph装配 | 新请求Memory路由/子图退役及历史读取兼容 |
| 原MemoryManager/Reader | 保留持久能力及真实命令来源兼容，不新增自动MemoryWriter |
| 生命周期、配置示例、新迁移 | 归档资源、集中预算、版本/维护/命令元数据 |
| 固定夹具、验证脚本、说明及报告 | 隔离、故障、保真、真实资源与偏好入口迁移 |

上述均待开发授权，不修改旧迁移或Saver底表，不引入常驻服务。本轮只新增本文。

## 15. 设计验收记录与强制停止条件

用户于2026-11-17验收02，状态为 **DESIGN APPROVED**。五项整改通过，三个二级环节、六个Task及依赖保持。以下六项为最终约束：

1. **ContextRevision的PUBLISHED与APPLIED严格区分，Graph实际Checkpoint是采纳依据。**
2. **旧Checkpoint不得自动注入Repository最新摘要；审批和未知结果恢复不得升级上下文。**
3. **Context Maintenance预算必须持久化，同一逻辑工作重启后不得重置。**
4. **V1 Memory Graph从新请求路由退役，保留结构化偏好；旧聊天提示迁移与新偏好接口的兼容变化必须明确。**
5. **恢复使用精确关联与有界候选，不承诺任意历史语义搜索。**
6. **真实LangMem、PG、Checkpoint、文件发布和模型兼容验证均属未来开发验收；当前不得标记VERIFIED。**

本次为设计文档归档，不是Git归档或实施。完成后停止，等待用户明确指令；不自行进入03或开发。
