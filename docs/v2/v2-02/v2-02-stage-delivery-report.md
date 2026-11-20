# V2 02 技术交付报告

当前 **VERIFIED，已按后续授权归档推送，等待人工验收**。六Task开发、自测、独立QA及主复核均完成，全部编号问题已关闭。Git交付9821ab7及远端校验见[归档回执](v2-02-git-archive-receipt.md)；本报告不代表人工ACCEPTED，不进入V2 03。

## 1. 六Task实现与技术验收

| Task | 当前结论 | 实现及独立QA证据 |
| --- | --- | --- |
| 2.1.1 身份、契约与适配器 | VERIFIED | 两项P2修复后42 passed；[主复核](v2-02-task211-main-review.md) |
| 2.1.2 Segment归档与发布 | VERIFIED | 独立真实组件21 passed及并发/跨Segment探针；[主复核](v2-02-task212-main-review.md) |
| 2.2.1 LangMem摘要 | VERIFIED | 独立真实组件28 passed及持久claim探针；[主复核](v2-02-task221-main-review.md) |
| 2.2.2 Graph安全裁剪与Checkpoint | VERIFIED | 两项P2修复及重放/完整覆盖复测；[主复核](v2-02-task222-main-review.md) |
| 2.3.1 跨Agent上下文与偏好迁移 | VERIFIED | 一项P2修复后独立真实探针2 passed、运行与关闭4 passed；[主复核](v2-02-task231-main-review.md) |
| 2.3.2 迁移及真实业务验收 | VERIFIED | [实施交接](v2-02-task232-implementation-report.md)、[正式独立QA PASS](qa/v2-02-task232-qa-report.md)、[主复核](v2-02-task232-main-review.md) |

各组存在交集，不累计为阶段总数。最终代码完整门禁 **290 passed / 0 failed / 0 skipped**，正式独立QA另定向 **38 passed / 0 failed / 0 skipped**；此前失败、修复与复测分别保留。

## 2. Subagent实际分工与配置来源

每个Task均采用项目原生implementer与独立qa，共12个原生会话；主Agent负责依赖、范围、接口、问题关闭和最终集成。全部显式使用 `gpt-6.1-terra / high`、`fork_turns=none`，没有换模型、降低推理或调用Bridge。

配置来源为用户级 `C:/Users/15294/.codex/config.toml`、项目 `.codex/config.toml` 和 `.codex/agents/implementer.toml`、`qa.toml`。实际执行依据原生 `session_meta.agent_role` 与每次 `turn_context.model/effort`，不是子Agent自述；会话ID、观察到的运行参数和配置hash见[实际运行证据](evidence/subagent-runtime-evidence.json)及[协调表](v2-02-execution-ledger.md)。QA只读是角色行为约束，权限继承父会话，未声称独立只读环境。原生额度曾短暂中断，原配置重试后恢复。

## 3. 关键变更与冻结契约

| 代码范围 | 当前实现及边界 |
| --- | --- |
| app/context/models、archive_store、repository、manager；008～010 | 原始身份列隔离，固定Archive引用、不可变发布、哈希核验、有界精确历史引用；Summary/Revision及持久维护预算。归档不替代Checkpoint，摘要不是业务事实 |
| Runtime、原Supervisor及State/Transfers | 发布与实际Checkpoint采纳分离，原Supervisor同次提交ContextRef与RemoveMessage；实际采纳读取Saver完整Checkpoint，旧绑定不自动引用最新版本；resume/审批/未知恢复不升级 |
| ContextBuilder、Gateway、三个专业Agent | 完整必需输入含实际工具/结构化Schema与输出预留；历史单独作为低信任背景，实际输入view/hash在中断前保存；运行内使用当前Run预算，维护预算独立持久化 |
| 偏好Route/Service、原Policy/Executor/Manager/Store；011 | 独立command_id及持久PREPARED/EXECUTING/APPLIED/CONFLICT/UNKNOWN回执；旧聊天返回迁移提示，新Memory路由退役，旧活动或未知Memory任务切换门禁保留 |
| context/migration、Runtime安全入口 | 新任务安全边界逐会话只读恢复可证明消息关联；未知Run不猜、未知消息保留原文并标不完整，不批量改写旧Checkpoint |
| compaction、Gateway、模型资源 | 当前v5把角色/原文/已有摘要编码为独立JSON来源，只保留直接陈述；仅摘要请求固定temperature=0，不保证确定性。DeepSeek正确发送max_tokens；length摘要记录用量后失败，不发布Summary/Revision |

没有新增Supervisor循环、图节点、MemoryWriter、Evaluation平台或V2 03能力。订单/退款事实、审批、当前目标及知识Query/Evidence沿原权威来源。迁移008～011仅应用本轮隔离双库，正式库与原.env未改。

## 4. 独立QA、真实业务及V1/V2 01回归

- [最终完整门禁](evidence/v2-02-task232-full-regression-r3.json)及[原始日志](evidence/v2-02-task232-full-regression-r3.log)：290/0/0，真实Qwen、PostgreSQL、Saver和Store启动/关闭通过，无遗留Qwen线程或后台任务。数据保护通过，知识发布水位36→47符合事前审计11次路径；原固定五订单seed唯一窄例外原样执行并finally恢复，未deselect。
- [真实模型业务探针](evidence/v2-02-task232-runtime-probe.json)：显式启用V2限额，外部模型经OrderAgent/工具查询唯一隔离模拟订单，状态paid、12.34 CNY、未退款，与数据库一致；下一Task实际注入前Task两条公开消息，应用关闭重启后线程与待澄清Task保持，精确清理通过。
- [Qwen/BGE/Hybrid组件实测](evidence/v2-02-task232-real-hybrid-r2.json)：两个原query直接检索found、当前Evidence有效，六篇临时样本精确清理，保护快照通过。没有将其称为本轮真实外部模型Knowledge Graph回答；Graph当前Query/Evidence接线由真实PG及受控模型回归检查。V2 01冻结排名收益沿用原验收，不声称本轮重跑全部质量指标。
- 实际受控模型调用中终止独立进程，再由新进程读PG恢复，预留次数和unknown保留、预算不重置；其余发布/采纳/回执故障结合前序原始证据及本轮回归。持久状态模拟不冒充机器断电或真实外部模型在途终止。
- [真实低限额回执](evidence/v2-02-task232-fix02-limit.json)：请求max_tokens=8，实际output8、finish_reason=length，维护尝试持久预留。真实PG截断检查保留READY归档、FAILED维护、无Summary及已耗用量。
- 当前固定八例v5真实输出见[r6](evidence/v2-02-task232-quality-r6-raw.jsonl)，独立逐项语义复测PASS，来源Task/Run/Checkpoint为合成夹具；不等同实际Runtime来源。正式独立QA通过后，主复核已关闭QA-001/002/003。
- [正式独立QA](qa/v2-02-task232-qa-report.md)另串行复验38/0/0，覆盖真实PG/Saver/Store/文件、受控transport、实际终止/新进程恢复、迁移、Revision和偏好，唯一数据精确清理断言通过。未独立重复全库快照、290全套或付费调用；完整门禁及保护由QA核对原始文件和源码。主Agent从原生QA工具输出留存[原始结果](evidence/v2-02-task232-independent-qa-raw.txt)及[来源回执](evidence/v2-02-task232-independent-qa-raw-receipt.json)。

历史失败完整保留：首轮完整回归280 passed/6 failed、保护false；只读内存归一审计确认仅发布水位差异，其他行列一致。另有首轮QA探针并发干扰快照、子进程探针启动失败、Hybrid空case失败、输出256/实报333异常及摘要r1～r3、r5质量失败；r4曾获固定八例PASS，但未用来覆盖r5失败。旧结果不计为最终通过，也未删除或用新断言覆盖。定位、修复及独立复测见[协调记录](v2-02-execution-ledger.md)和fixes/qa目录。

## 5. 当前资源观测

[当前v5资源实验](evidence/v2-02-task232-resource-runtime-r3.json)使用真实Runtime正式Task/Run及固定长历史：同一节点、模型、当前问题、Schema/工具及输出预留512，仅历史原文/摘要不同，消费请求的供应商input为 **6958→225 tokens**。摘要另消耗 **6121 input / 136 output tokens，1.70秒**，三次调用全部计入同一Run三次尝试，清理保护通过。

实验图和历史来源是合成夹具；Runtime所有权、Run预算、Gateway调用和供应商用量真实，不冒充实际业务Graph同一路由的流量收益。

本地估算3394→154与供应商实际用量分开，不能混减。归档30510字节来自早期同固定源实验，不称v5重测值。这是单场景消费输入变化，不是整体成本或任意输入的收益保证，不替代质量结论。无效的不同路由对照、旧版本及超限资源实验均保留。

## 6. 风险、阻塞与未覆盖

当前无未关闭编号问题或技术阻塞，阶段VERIFIED。已完成的固定八例不能保证不同模型、任意长历史或增量摘要的泛化保真，温度0也不能保证确定性；历史始终低信任，不能作为审批或业务事实。输入计数仍为明确标记的估算，供应商能力声明没有满窗口实测。

本轮未测真实外部模型Knowledge Graph回答、机器断电、真实外部模型在途终止及Postman脚本/变量回填/SSE界面。直接检索、受控Graph、真实PG故障各有证据但不互相替代。LangMem间接依赖的上游LangGraph弃用警告保留。

正式环境未应用008～011，原.env无新限额时保留V1当前任务行为；正式部署须另授权迁移和配置。旧活动或未知Memory任务须先完成安全处理，不能删除记录绕过切换门禁。历史检索为精确关联和有界候选，不承诺任意语义搜索。

## 7. Git工作区与建议归档

技术交付时分支v2、HEAD为`1ff92e082c5a348b715b221fbc0b687d8acf02e8`，当时尚未Git归档。[接管基线](evidence/takeover-workspace-baseline.json)和[保护复核](evidence/workspace-safety-audit.json)区分原有与本轮改动，492个受保护既有文件及冻结设计hash保持；正式容器ID和原启动时间只读复核一致，不冒充正式库行级审计。用户后续授权归档，必要文档/角色配置前置790fa08与V2 02交付9821ab7已推送核验，另补记回执；无关四文件继续保留未提交。

归档前快照有65个修改、385个原路径删除及676个未跟踪文件，包含接管前文档重排，不能全部视为本阶段新增；这些数字不是归档后状态。技术交付时51份Markdown链接通过；归档时另对52份交付Markdown的暂存树目标、固定夹具和127份关键文件字节核验通过。[公开凭据扫描](evidence/public-artifact-secret-scan.json)检查180份本阶段文档/代码，暂存内容也另核对，未命中已知实际凭据，未导出其值。

[建议归档范围](v2-02-git-archive-proposal.md)单列本阶段代码、迁移、依赖、客户端和证据；既有文档重排须先核实前置归档安排，不自动打包全部dirty工作区。.git私有连接资料、.env、临时数据库、运行归档和模型权重不归档。

本轮专用Linux容器/卷、本机临时PG和回环SSH通道保留用于人工复验；测试身份、线程、样本和临时schema按各自证据精确清理。这些验证环境不属于Git归档，保留不代表正式部署或后续开发授权。

技术开发、独立QA及主复核已完成，Git已按用户后续授权归档推送，当前停止，等待用户人工验收，不进入V2 03。
