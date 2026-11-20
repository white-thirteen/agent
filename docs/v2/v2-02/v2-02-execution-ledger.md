# V2 02 执行与协调记录

2026-11-19，用户明确授权本阶段六个 Task 开发、自测、串行独立 QA 及主复核。阶段正式 ACCEPTED、Git 提交和推送仍待另行授权；不进入 V2 03，不修改正式数据库。

## 接管事实

- 分支 `v2`，起始 HEAD `1ff92e082c5a348b715b221fbc0b687d8acf02e8`。V2 01 依现有阶段验收记录为 ACCEPTED，本轮未重跑其历史验收。
- 用户指定的设计已迁移至 [冻结设计](v2-02-context-engineering-detailed-design.md)。保持原冻结正文。
- 仓库仅发现根 AGENTS.md。已读取用户级 `C:/Users/15294/.codex/config.toml`、项目 `.codex/config.toml`、implementer/qa 角色 TOML 及已有角色验证记录。用户级主模型默认不用于推断当前主会话或子会话模型。
- 项目默认及两角色均为 `gpt-6.1-terra / high`，本聊天原生角色注册表同样固定该设置。每次新派发显式指定角色、模型、high、`fork_turns="none"`，并核对原生运行日志的 session_meta / turn_context。
- Implementer负责单Task编码、自测及定向修复；QA独立审查及复验，默认不修改实现或原测试。两者继承当前 `danger-full-access / never` 权限；QA只读为行为约束，没有额外只读沙盒。
- 工作区已有文档迁移、配置及脚本等未提交变更。[接管摘要](evidence/takeover-workspace-baseline.json)记录已有文件及哈希；不重置、不清理、不将其视为本轮开发。

## 顺序与门禁

| Task | 实现 | 独立 QA | 主复核 |
| --- | --- | --- | --- |
| 2.1.1 身份、契约与适配器 | 完成 | 修复独立复测 PASS | VERIFIED |
| 2.1.2 Segment 归档与发布 | 完成 | PASS | VERIFIED |
| 2.2.1 LangMem 摘要 | 完成 | PASS | VERIFIED |
| 2.2.2 Graph 安全裁剪与 Checkpoint | 完成 | 两项P2修复复测PASS | VERIFIED |
| 2.3.1 跨 Agent 上下文与偏好迁移 | 完成 | P2修复复测PASS | VERIFIED |
| 2.3.2 迁移及真实业务验收 | 完成 | 三项P2修复，正式独立QA PASS | VERIFIED |

每个 Task 在实现、自测、独立 QA 和主复核技术通过后推进下一项。失败由原 Implementer 定向修复，再由独立 QA 复验。真实 P0/P1 或冻结设计要求人工裁决时停止相关工作。测试证据区分受控、真实和未执行；不得借修改冻结指标制造通过。

## 原生派发

| 工作单元 | 角色与原生路径 | 模型 / 推理 | 核对依据 |
| --- | --- | --- | --- |
| 2.1.1 开发 | implementer `/root/v202_task211_impl` | gpt-6.1-terra / high | 显式原生 spawn；会话 `01a1f257-127c-7a63-8976-62483426c360` 的 session_meta.agent_role 与 turn_context.model/effort 已核对 |
| 2.1.1 独立 QA | qa `/root/v202_task211_qa` | gpt-6.1-terra / high | 显式原生 spawn；会话 `01a1f25e-1e1f-7da2-a382-445bec4a0d58` 的 session_meta.agent_role 与 turn_context.model/effort 已核对 |
| 2.1.2 开发 / QA | implementer / qa，task212_impl / task212_qa | gpt-6.1-terra / high | 原生会话元数据 |
| 2.2.1 开发 / QA | implementer / qa，task221_impl / task221_qa | gpt-6.1-terra / high | 原生会话元数据 |
| 2.2.2 开发 / QA | implementer / qa，task222_impl / task222_qa | gpt-6.1-terra / high | 原生会话元数据，含修复续执行 |
| 2.3.1 开发 / QA | implementer / qa，task231_impl / task231_qa | gpt-6.1-terra / high | 原生会话元数据，含修复复测续执行 |
| 2.3.2 开发 | implementer `/root/v202_task232_impl` | gpt-6.1-terra / high | 显式原生spawn，会话01a1f4bd-7538-7271-b3d8-eb1968cb4bc9元数据已核对 |
| 2.3.2 独立 QA | qa `/root/v202_task232_qa` | gpt-6.1-terra / high | 显式原生spawn，会话01a1f4ce-1d77-7702-9eb0-990bb962457b元数据已核对；先只读质量预审，整Task交付后正式QA |

不调用 Session Bridge，不重建或改写已有角色配置。

实际角色、全部观察到的turn_context和配置hash见[原生运行证据](evidence/subagent-runtime-evidence.json)，可由[只导出元数据的脚本](evidence/refresh-native-agent-evidence.py)更新；不以子Agent自述或仅TOML值替代实际运行核验。QA只读为角色行为约束，继承当前权限，未声称独立只读隔离环境。

## 2.1.1 开发与首轮 QA 进展

[实现报告](v2-02-task211-implementation-report.md)记录开发定向38 passed、pip check、Ruff和一次真实合成摘要调用，数据库未访问。独立 QA 已复现 `V202-211-QA-001 / P2`：RunningSummary 与含旧消息的完整输入共同使用时，新增消息未被处理。等待完整独立 QA 后交原 Implementer 定向修复，当前未 VERIFIED。

主 Agent 另通过只读供应商 `/models` 核验实际配置 `deepseek-flash` 的能力声明，窗口1048576、最大输出393216，见[能力回执](evidence/model-capability-receipt.json)及[官方元数据说明](https://api-docs.deepseek.com/api/list-models/)。这不是满窗口实测，应用可配置更低限额，原 `.env` 保持。

## 2.1.1 技术关闭与2.1.2启动

[主复核](v2-02-task211-main-review.md)对照[独立复测](qa/v2-02-task211-retest-report.md)关闭两项P2。修复后42 passed，原首轮失败证据留存。2.1.1 VERIFIED，2.1.2按冻结依赖启动。2.1.2原生角色仍显式Terra/high，另核对本次运行元数据。

旧隔离库凭据文件已不存在；本机SSH密钥对VM的root及历史用户white7登录被拒。已向用户询问可用隔离连接/SSH配置位置，正式数据库未访问。该环境缺口不停止文件及代码实现，但真实PG结果不得用受控替身代替。

2.1.2 开发实际会话 `01a1f264-b10a-7f81-a8a5-3d6f8e39c03a`，原生 `session_meta.agent_role=implementer`、`turn_context.model=gpt-6.1-terra / effort=high` 已核对。主Agent准备官方EDB Windows portable PG17.12作为本机回环隔离验证环境；不注册服务、不接触正式库，不将无Linux扩展的本机结果声称V2 01完整回归。

## 2.1.2 技术关闭与2.2.1启动

[2.1.2主复核](v2-02-task212-main-review.md)VERIFIED。独立QA21 passed及首次并发/跨Segment锚点真实探针通过，无编号问题。QA会话01a1f26c-eeb3-7153-9386-11d0f72467e2的qa/Terra/high运行元数据已核对。

本机独立PG17.12已就绪；主Agent从pgvector v0.8.7源码通过现有MSVC构建，另建全新本机agent_demo/agent_demo_test双库、安装vector0.8.7，001~008/Saver/Store初始化通过，各导入五条**新库夹具**（不涉及原正式五订单）。凭据仅.git私有文件，临时环境变量启动器留存于[evidence/local-pg-launcher.py](evidence/local-pg-launcher.py)。LinuxBM25/zhparser未具备，不能声称Hybrid回归已通过。

## Linux隔离环境恢复

用户随后提供既有VM连接授权，主Agent完成只读预检，复用原候选镜像新建容器codex-v202-af45a90441及独立卷codex-v202-data-af45a90441。通过双端loopback SSH tunnel连接；真实vector0.8.7/pg_textsearch1.5.1/zhparser2.4已加载。正式库、原卷/备份/HBA不改。见[环境回执](evidence/linux-pg-environment.json)与[安全启动器](evidence/linux-pg-launcher.py)。本轮仅在.git私有文件保存连接参数，公开记录不含凭据。根分区空间有限，复用已有镜像不构建/拉取。后续真实Linux回归环境缺口已解除。

2.2.1开发会话01a1f270-3102-71a3-a3b0-803f35156954的implementer/Terra/high运行元数据已核对；曾局部交付但无真实阻塞，主Agent已要求继续至当前Task完整，不将局部结果视为QA或VERIFIED。

## 2.2.1 技术关闭与2.2.2启动

[2.2.1主复核](v2-02-task221-main-review.md)VERIFIED，无编号问题。独立QA会话01a1f282-bfe8-7c80-bfdc-b6e7f5c49e19的qa/Terra/high运行元数据已核对，独立真实PG28 passed/0 skipped及claim/旧回执探针PASS。Runtime必须核实旧执行者消失后才调用interrupt_maintenance，后续保留真实接线验收。2.2.2按依赖已启动。

## 2.2.2 开发与独立QA

开发已交付，见[实施报告](v2-02-task222-implementation-report.md)。真实Saver最终采纳/门禁8 passed、退款组合24 passed；开发发现并修正Graph.aget_state可能叠加pending writes的观察边界，APPLIED改以正式Saver实际Checkpoint为依据。受理前零写，STALE/APPLIED写入移至受理后安全边界。2.2.2开发实际会话01a1f285-ae43-7882-a5bc-d870bc971e43的implementer/Terra/high元数据已核对，用户续执行后亦再次核对最新turn_context。独立QA已启动，未提前标记VERIFIED。

本机临时PG在续执行时已停止，主Agent以独立隐藏进程恢复同一临时实例并重新核验guard；没有推断停止原因或将该偶发恢复算作受控业务验收。Windows Proactor连接失败在连接前发生，真实PG回归以Selector重试通过；两份阶段启动器已集中设置Selector策略。原失败记录保留。

## 2.2.2 技术关闭与2.3.1启动

[2.2.2主复核](v2-02-task222-main-review.md)关闭QA-001/002两项P2。独立QA首轮82 passed/0 skipped，发现基线历史覆盖遗漏与重放证据缺口；修复后独立8 passed/0 skipped，合法无父全量摘要独立1 passed，原缺历史探针按旧错误预期运行而出现预期失败，原始断言未改。QA实际会话01a1f38f-dfac-73e0-9b2e-66a91724dde9的qa/Terra/high运行元数据已核对。2.3.1已按[执行边界](v2-02-task231-execution-task.md)派发，不进入2.3.2前置验收。

## 2.3.1 进行中

开发原生会话01a1f399-e717-7ac1-bd58-f9c1f37ba357的implementer/Terra/high已核对，中断续执行后重新确认。011仅由主Agent应用到本轮Linux隔离双库，当前schema11。已完成偏好控制真实Store/HTTP初测与运行内压缩、维护互斥/失败预算复用等定向验证，尚待完整交付和独立QA，不标记VERIFIED。原.env无新limits时保留V1当前Task调用，V2背景/维护须显式配置，不以缺配置停掉原普通能力。

主Agent预先固定八个摘要语义场景和一个长历史资源观测场景，均在真实质量生成前保存hash；语义/资源实际结果在2.3.2另报，不能以当前组件测试代替。阶段最终执行要求见[2.3.2执行边界](v2-02-task232-execution-task.md)。

## 2026-11-20续执行

用户再次明确继续。2.3.1开发曾遇原生额度错误，工具提示00:11恢复；主Agent在00:30后按原角色续派成功，未换模型或降推理强度。最新原生turn_context仍Terra/high。两个隔离数据库已重新在线核验身份/版本/marker通过。历史四Task技术结论保持，231继续收尾，尚不具备阶段VERIFIED。

2.3.1首轮独立QA见[报告](qa/v2-02-task231-qa-report.md)，发现`V202-231-QA-001 / P2`：Revision发布后关联回执丢失，若会话已采纳，恢复worker不能补记而反复占用扫描名额。已交原Implementer按[fix01](fixes/v2-02-task231-fix01.md)修复。原FAIL保留；QA探针与全库快照并发导致的独立测试干扰也保留，清理后原文件3 passed，后续写入探针与快照严格串行。

2.3.1修复后独立真实PG/Saver/文件探针2 passed、受控运行与关闭4 passed，见[独立复测](qa/v2-02-task231-retest-report.md)。[主复核](v2-02-task231-main-review.md)关闭QA-001，Task VERIFIED；2.3.2依既有授权启动，按预先固定的语义/资源夹具和最终门禁执行。

2.3.2开发会话01a1f4bd-7538-7271-b3d8-eb1968cb4bc9的implementer/Terra/high已核对。真实摘要语义首轮v1及完整复测v2均保留原始输出，初审存在从缺少可信记录推断实际状态、从未提及推断待办或已执行情况的质量FAIL。主Agent要求一次通用摘录式Prompt根因修复，保留来源归属及原文否定/未知，不改固定夹具或阈值；最多再执行一次完整八例，不无限抽样。该质量缺口不以组件测试或Token下降掩盖，继续独立评审。

v3完整八例仍有遗漏与控制指令污染，已停止无变化抽样。[独立质量预审](qa/v2-02-task232-summary-quality-review.md)确认`V202-232-QA-001/002 / P2`，原Implementer按[fix01来源边界修复](fixes/v2-02-task232-fix01.md)处理，受控验证实际输入后仅一次完整真实复测，保留全部原始FAIL。首轮完整真实回归280 passed/6 failed/0 skipped，保护结论false；进一步只读审计确认仅知识发布水位+9，其余行集/列定义一致。Hybrid在未激活索引门禁提前失败，少走两次发布/清理；不把+9设成新验收阈值，待环境及兼容失败修复后复验。

fix01后v4八例获独立语义复测PASS；完整真实回归第二轮287 passed/0 failed/0 skipped，保护通过，水位13→24吻合预审计11次路径。真实订单模型/工具/DB及跨Task背景、应用重启绑定、真实Qwen/BGE/Hybrid组件均取得证据，首次失败保留。

实际资源实验在正式Runtime Task/Run中比较同节点输入6958→436，但摘要配置输出256、供应商known输出333。已定位SDK将当前DeepSeek要求的max_tokens改写为max_completion_tokens，并发现摘要桥未拒绝length；按[fix02](fixes/v2-02-task232-fix02.md)修复，旧287 passed不替代修复后门禁。Implementer原生调用曾返回usage-limit，工具提示5:29 AM（未推断其时区）；按同一原生会话/模型重试已恢复，最新turn_context仍Terra/high。参数适配及摘要截断拒绝已落地，受控组合29 passed，真实限额及最终门禁待完成。

fix02后受控30 passed、真实本机PG截断1 passed，真实DeepSeek wire max_tokens=8/无max_completion_tokens、actual output8/finish_reason length，持久维护尝试保留。资源r2摘要上限明确调整512，实际input6091/output367、4.30秒；同节点输入6958→502，真实活动Run尝试3、清理保护通过，摘要成本单列。r5完整八例在独立[质量预审](qa/v2-02-task232-summary-quality-fix02-review.md)新增QA-003/P2：未提及的查询/检索状态被写成实际未发生。按[fix03](fixes/v2-02-task232-fix03.md)修复直接陈述边界并固定仅摘要temperature=0、生成版本v5；不把该参数当确定性或质量正确的证据。

本轮隔离SSH通道断开后仅重启已核实的专用helper，四库只读身份guard重新通过，未重启任何容器。[正式容器只读复核](evidence/formal-container-readonly-audit.json)确认原容器ID及2026-11-17启动时间保持；不冒充正式库行级核对。

## 最终技术交付

当前v5固定八例r6独立逐项语义PASS；最终完整真实回归r3为290 passed/0 failed/0 skipped、保护通过、水位36→47与预审计11次一致。当前v5资源r3同节点消费input6958→225，摘要另6121/136、1.70秒，真实Run三次尝试和清理通过。

[正式独立QA](qa/v2-02-task232-qa-report.md)另串行38 passed/0 failed/0 skipped，无新编号问题。[主复核](v2-02-task232-main-review.md)关闭232-QA-001/002/003，六Task均VERIFIED，当前无未关闭编号问题。[阶段报告](v2-02-stage-delivery-report.md)及[建议归档范围](v2-02-git-archive-proposal.md)已整理。停止开发，不进入V2 03，等待人工ACCEPTED与Git归档授权；未提交推送，正式库/.env保持。

用户随后明确授权Git提交与push。必要文档/模型配置前置790fa08及V2 02交付9821ab7已推送origin/v2并核验，另以文档提交补记[归档回执](v2-02-git-archive-receipt.md)。四个无关原文件继续保留，未合入main、不更改正式数据库或开发V2 03；正式人工验收状态不因本次Git授权自动变更。
