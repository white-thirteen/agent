# 当前交接状态

## 全项目联调及合并授权（2026-11-20）

当前V2基线完整回归322 passed/0 failed/0 skipped，真实TCP订单/隔离/知识/跨进程退款恢复、偏好控制、Context维护及SSE断流场景完成。两项发现保留：IT-001能力介绍输入曾路由失败、根因未确定；IT-002订单确定性中文展示限制。用户明确“记录即可，无需现在修复”，并授权V2分支合入main；见[联调报告](integration/2026-11-20/report.md)和[处理决定](integration/2026-11-20/issue-disposition.md)。本次不修复业务代码，不将两项发现标为已解决，合并与远端状态以实际Git回执为准。

## V2 03 = VERIFIED（2026-11-20，已归档推送）

用户随后明确授权“提交并push git”，V2 03已以a6ba906交付到origin/v2并核验远端，另补文档回执；见[Git归档回执](v2/v2-03/v2-03-git-archive-receipt.md)。4项无关遗留文件保留本地，阶段仍VERIFIED；下文等待Git/未提交为技术交付时状态，不推导合并main或后续开发授权。

Gemini六Task初步交付经两轮定向修复、原生独立QA与主Agent复核，六Task均VERIFIED，V203-QA-001～008关闭。完整真实隔离回归322 passed/0 failed/0 skipped，固定订单及受保护数据前后比较通过；真实Qwen和服务启停通过。独立真实模型13次/6710 known tokens，固定五题5/5，两条多候选完整PG链路及单工具成本对照通过，未声称收益。见[交付报告](v2/v2-03/v2-03-stage-delivery-report.md)、[最终独立QA](v2/v2-03/qa/v2-03-final-qa-report.md)及[接管记录](v2/v2-03/v2-03-takeover-ledger.md)。原FAIL、中断、编码和环境失败保留；全范围Ruff三项基线E501及旧审批跨进程等未覆盖边界如实留档。实际Subagent均Terra/high，源码已停止修改，尚无Git或正式数据库授权；HEAD仍1f3d736，未暂存/提交/推送。等待人工正式验收与Git归档授权，不进入后续开发。V2 02及更早记录保持，下文旧状态仅保留历史语境。

## V2 02 = VERIFIED（2026-11-20，等待人工验收）

用户随后明确授权“提交git并push到远程”。V2 02已以9821ab7交付到origin/v2并核验，必要文档前置为790fa08，另补记归档回执；见[Git回执](v2/v2-02/v2-02-git-archive-receipt.md)。不推导合入main、正式迁移、V2 03或额外人工验收状态变更。

六Task实施、自测、独立QA和主复核完成。最终完整真实隔离回归290 passed/0 failed/0 skipped，正式独立QA定向38 passed/0 failed/0 skipped；数据保护及真实Qwen/PG/Saver/Store启停通过。当前v5固定八例语义独立PASS，资源消费input6958→225，摘要成本单列；真实输出参数/截断、来源边界及缺失信息推断问题均已修复复测，所有编号问题关闭，原失败保留。

本轮按冻结依赖逐项Implementer→独立QA→主复核，12个原生子会话实际Terra/high元数据已核对。正式库、原.env和接管已有内容保持；开发已停止，Git归档按上述新授权执行，不进入V2 03。实际边界及未覆盖范围见[阶段交付报告](v2/v2-02/v2-02-stage-delivery-report.md)、[2.3.2主复核](v2/v2-02/v2-02-task232-main-review.md)及[建议归档范围](v2/v2-02/v2-02-git-archive-proposal.md)；[执行协调记录](v2/v2-02/v2-02-execution-ledger.md)保留接管与所有修复历史。以下“V2 02维持设计状态”为历史语境。

## V2 01 = ACCEPTED（2026-11-19）

六个 Task 均为 **ACCEPTED**。本轮正式接受 1.1.2、1.2.1、1.2.2、1.3.1 并归档专项实现记录、独立 QA 和原始证据。1.1.1 与 1.3.2 沿用既有正式验收及交付提交。当前基线无未关闭的 P0/P1 或阶段技术阻塞，指标、V1 回归及风险见[阶段正式验收](v2/v2-01/v2-01-stage-acceptance.md)。V2 02/03 维持设计状态。以下记录保留原轮次语境。

## V2 01 Task 1.3.2 = ACCEPTED（2026-11-19）

用户正式批准采用 RRF Top3 局部 BGE 重排并授权归档，独立 QA PASS，`V201-132-QA-001` 已关闭。冻结集真实五轮，纯 RRF→局部 BGE 的 Recall@3 为 1.0000→1.0000、MRR@3 为 0.9667→1.0000、nDCG@3 为 0.9606→0.9779。实际检索排序 24/24 一致，业务 6/6，隔离 PostgreSQL 定向回归 38 passed。独立新题泛化、前三之外证据无法由局部策略补回、并发排序稳定性继续留档。见[正式验收与证据索引](v2/v2-01/v2-01-task132-acceptance.md)。直接依赖随代码归档，前置 Task 的正式验收状态保持原记录。以下旧失败、待裁决和未推送描述保留各自历史语境。

## V2 01 续执行（2026-11-18）

用户已授权继续 V2 01 开发。Task 1.2.1 = VERIFIED，真实隔离库独立复测 PASS，V201-121-QA-001 已关闭，V1 知识/Graph 定向回归 23 passed。见[主复核](v2/v2-01/v2-01-task121-main-review.md)。1.1.2 技术交付与 QA 证据保持，Git 归档尚未授权。

Task 1.2.2 = VERIFIED，真实 BGE 与正常语料、共享容量的独立复测已通过，见[主复核](v2/v2-01/v2-01-task122-main-review.md)。Task 1.3.1 = VERIFIED，真实应用烟测及受治理 Graph 独立 QA 已通过，见[主复核](v2/v2-01/v2-01-task131-main-review.md)。Task 1.3.2 功能与 V1 兼容性验证通过，检索质量收益 FAIL。独立 QA 关闭 QA-002，V201-132-QA-001 继续 OPEN：C→D nDCG@3 0.9606→0.9233。V1 完整真实回归 238 passed/0 failed/0 skipped；固定业务复测 6/6。见[主复核与决策边界](v2/v2-01/v2-01-task132-main-review.md)。等待用户裁决重排方案，正式数据库与 Git 提交均未更改。

## 当前交付（2026-11-18，Task 1.1.2 = VERIFIED）

Task 1.1.1 保持 ACCEPTED。Task 1.1.2 已完成开发、真实隔离验证、独立 QA PASS 和主复核，等待人工验收及 Git 归档授权。见[实施报告](v2/v2-01/v2-01-task112-implementation-report.md)、[独立 QA](v2/v2-01/qa/v2-01-task112-qa-report.md)和[主复核](v2/v2-01/v2-01-task112-main-review.md)。

迁移 007 可在仅安装 pgvector 的 V1 环境使用。隔离环境验证历史回填、事务发布、版本替换、删除同步、失败回滚与重试、受控索引激活。V1 真实定向回归 12 passed，应用健康检查通过。正式库未执行迁移或写入。未提交或推送，本轮不启动 1.2.1。

## 当前交付（2026-11-18，Task 1.1.1 = ACCEPTED）

Codex 独立复验通过，用户正式接受并授权本 Task 的 Git 归档。固定基线为 PostgreSQL 17.12、pgvector 0.8.7（包 +2）、pg_textsearch 1.5.1、zhparser 2.4 和 SCWS 1.2.3。见[验收和证据索引](v2/v2-01/v2-01-task111-acceptance.md)。

BM25 并发分数/排序稳定性、应用级 Dense-only 回退、RRF/BGE 和完整质量评测留待后续 Task。V2 01 阶段仍在进行，1.1.2 等待另行启动。以下待复验与旧候选阻塞记录为历史。

## 最新补证（2026-11-18，Task 1.1.1 PENDING_CODEX_REVIEW）

已在隔离候选镜像 `v201pt-candidate:1.5.1-vector2` 完成三项补证：参数化/中英混合 BM25 逐例断言 PASS；`REPEATABLE READ` 下 Dense/Sparse 同快照，版本替换后旧 `v1-refund` 的 `is_current=false`；REINDEX 超时失败后索引仍有效、5000 行校验和不变，重试成功，BM25 索引禁用时 Dense-only Top5 可执行。详见[Task 1.1.1 补证报告](v2/v2-01/v2-01-task111-report.md)及[证据目录](v2/v2-01/evidence/v2-01-task111-evidence-20261118/)。

未执行 1.1.2 及后续 Task；未修改/重启正式数据库、业务代码、设计、迁移或 V1 配置；未提交 Git。状态待 Codex 独立复验，不自行宣布 Task 1.1.1 ACCEPTED。

## 最新变更（2026-11-18，V2 01 BM25 切换 REQUIRES_FIX）

BM25 主方案已由 ParadeDB pg_search 切换为 Tiger Data pg_textsearch 1.5.1，中文采用 zhparser 2.4 + SCWS 1.2.3；PostgreSQL 17.12/vector 0.8.7 及既有 Dense 路径不变。隔离环境完成 PG17.12 headers 安全构建、扩展加载、中文索引、事务回滚、增量更新、重启、过滤后 TopK、5000 Chunk 压力及并发可见性复测，详见[切换报告](v2/v2-01/v2-01-bm25-switch-report.md)。

本轮完成与正式基线一致的 pgvector `0.8.7-1.pgdg12+2` 候选镜像重建；候选容器内 7 项实际加载产物 SHA256 全部 `OK`，过滤 TopK 顺序扫描与 BM25 索引扫描逐行一致，DELETE 提交后旧关键词不再命中。并发只证明固定夹具下未提交变更不可见、提交后可见，不对历史“返回 0”作根因结论。临时语料上 Jieba 与 zhparser 的 BM25 质量接近（Jieba Recall@10 0.8792 / MRR 0.9167；zhparser 0.8625 / 0.9167），未冒充 V2 冻结语料或完整 RAG 质量通过。

本轮仅改 `app/knowledge/models.py` 的 SparseIndexProfile 及设计/状态/报告文档；未改业务数据、迁移、`.env`、V1 代码或正式数据库，未启用 pg_search，未提交 Git，未进入 1.1.2。Codex 独立验收为 `REQUIRES_FIX`；第二轮修复映射见[QA 修复报告](v2/v2-01/qa/v2-01-bm25-switch-qa-fix-report.md)，构建/运行原始证据见[证据目录](v2/v2-01/evidence/v2-01-bm25-switch-evidence-20261118/)。正式镜像含 `pg_search.so`，但数据库未安装、未启用；三态事实见[正式事实](v2/v2-01/evidence/v2-01-bm25-switch-evidence-20261118/formal-facts.txt)。

## 最新门禁结果（2026-11-17，1.1.1续作 BLOCKED）

PG17.12隔离环境完整功能探针退出0：中文/英文标识、过滤后Top K、参数化、事务更新/删除回滚、Dense/Sparse同快照及重启持久化通过，专用容器/卷已精确清理。本地契约7 passed。
但固定pg_search0.26.6源码依赖pgrx0.19.3，上游要求修复版pgrx和修复后的PG headers重建，现缺安全构建证明。独立QA确认V201-111-QA-002/P1 OPEN；Task1.1.1仍BLOCKED，不进入1.1.2。
[续作实现](v2/v2-01/v2-01-01-compatibility-resume-report.md)、[独立QA](v2/v2-01/qa/v2-01-01-compatibility-resume-qa-report.md)、[主复核及路线](v2/v2-01/v2-01-01-resume-main-review.md)。原001在17.12基线的加载阻塞解除，17.6历史失败仍保留，不冒称已修复旧组合。
正式容器保持healthy且未重启，pg_search未启用，业务/迁移/.env/冻结设计未改；无Git提交推送。下一步需确定可追溯安全构建路线，当前VM约1.15GB空闲，不盲目启动大型源码编译、不删除备份/卷。

## 最新续执行授权（2026-11-17，V2 01）

用户在原库升级完成后明确要求继续01开发。本轮恢复Task 1.1.1：以已批准的新运行基线PG17.12/vector0.8.7核查pg_search安全构建来源，补齐独立环境的完整兼容门禁及契约，原始17.6失败证据保留。
Implementer与QA采用新建gpt-6.1-terra/high、干净上下文，按Task串行；1.1.1经独立QA及主复核通过后才推进1.1.2及后续依赖Task。安全构建或部署门禁未满足时不得假通过，不擅自重启正式库或改用SQL BM25。
本轮不进入V2 02/03，不从开发授权推导阶段ACCEPTED或Git提交/推送授权；已有工作区改动、正式HBA绑定、原卷及备份继续保护。下文升级轮次的停止条款由此次明确续执行授权覆盖。

## 当前运行基线（2026-11-17，PG17.12 升级完成）

用户已明确批准原库升级。原端点192.168.150.101:5432现为PG17.12/vector0.8.7（包+2，17.12 headers来源已核），
采用最终停写备份恢复的新卷；原17.6容器/原卷及全部备份保留。独立最终QA PASS、主复核通过，
两库各13表完整数据/结构/权限与最终备份一致；验证库完整真实Qwen/PG门禁229 passed/0 failed/0 skipped，
切换后原配置应用健康通过，Embedding原开关仍禁用，不冒称生产RAG通过。
见[升级报告及配置依赖/回退边界](v2/v2-01/v2-01-pg1712-upgrade-report.md)、[最终QA](v2/v2-01/qa/v2-01-pg1712-upgrade-final-qa-report.md)。
已开放正常写入，禁止未经增量核对直接切回旧库；当前升级根目录包含正式HBA绑定，不能清理。
原.env、业务代码及迁移未改，Git仍为v2/232469a且未提交本轮改动。

V2 01仍IN_PROGRESS，pg_search尚未在正式库启用，启用/安全重构建及完整兼容门禁未完成；
本轮不进入1.1.2或02/03开发，不把原PG17.6兼容失败历史改写为已通过。
用户另要求全部原生子Agent使用gpt-6.1-terra/high，项目默认及Implementer/QA配置已生效并实测调用；旧子会话已停止，后续只用经核对的新模型。
下文PG17.6未升级等描述为此前轮次记录，以本段及最新用户指令为准。

## 当前开发（2026-11-17，V2 01 IN_PROGRESS）

06交付98af9d8、归档回执232469a已推送real-model-chat/main，v2从main创建并推送同基线，远端SHA已核验。六项旧遗留与三份批准设计未混入06；保护摘要核对无变化。当前仅V2 01获开发授权，从[Task1.1.1](v2/v2-01/v2-01-01-compatibility-execution-task.md)开始串行实施/独立QA；其余Task等待该门禁，02/03不开发。V2 01当前IN_PROGRESS，设计批准不等于技术/正式验收。

1.1.1真实兼容门禁现为BLOCKED，独立QA及[主复核](v2/v2-01/v2-01-01-main-review.md)确认V201-111-QA-001/P1 OPEN：[原始证据](v2/v2-01/evidence/v2-01-01-compatibility-evidence-20261117.json)、[实现报告](v2/v2-01/v2-01-01-compatibility-report.md)。官方pg_search0.26.6包在固定PG17.6/vector0.8.7隔离镜像构建成功，但预加载失败，缺少`pg_mblen_cstr`符号；不能据此泛称所有ParadeDB版本均不支持PG17.6。两库全public行/列摘要、原容器/包版本前后不变，候选容器/卷/镜像及外层传输目录已精确清理。中文/过滤/事务/快照/重启语义未执行，不进入1.1.2、不启用新契约、不擅自升级PG或切SQL。用户技术路线裁决已请求；V2代码/设计尚未Git归档。

## 最新授权（2026-11-17，06 ACCEPTED与V2 01）

用户已正式授权06提交/推送、合入main，再创建v2分支开发V2 01。06采用已有六Task独立QA及主复核证据，状态ACCEPTED；228 passed/0 failed/0 skipped为既有真实门禁，并非本轮重跑。客户端脚本/回填/SSE未实测、Store旧时序观察及六项暂缓差异保留。06交付98af9d8已推送real-model-chat和main并核验，V2设计和旧遗留未混入；见[06归档回执](v1/v1-06/06-git-archive-receipt.md)。

V2 01～03设计已DESIGN APPROVED，设计文档将在v2分支独立归档，不混入06交付。当前仅V2 01获开发授权，从1.1.1兼容验证与契约开始，Implementer→独立QA串行。ParadeDB精确适配未实测，不得升级原PG或以发布包存在冒充通过；V2 02/03不得开发。该段覆盖下文旧轮次等待状态。

## 当前阶段（2026-11-15，06已授权）

06六Task已完成实现、串行独立QA及主Agent技术复核，阶段VERIFIED，等待用户正式验收（未ACCEPTED、无06 Git归档/推送授权）。06-QA-001/P2已修复、原QA真实复测并主关闭，无未关闭编号问题。最终独立新Python3.13.7环境完整真实PG门禁228 passed/0failed/0skipped，含真实Qwen及原seed幂等窄例外；pip check/Ruff/155文件格式通过。固定PG17.6/vector镜像实际构建、新空双库应用/Saver/Store初始化和幂等、独立SQL审计与临时资源精确清理通过，原数据库未重启/重建。用户已确认Postman导入；客户端后置脚本/变量回填/SSE界面仍未实测，Store旧即时观察风险保留。入口[最终验收](v1/v1-06/final-acceptance.md)、[简洁Handoff](v1/v1-06/06-integration-handoff.md)、[06主协调](v1/v1-06/qa/06-integration-main-review.md)、[632独立QA](v1/v1-06/qa/06-delivery-qa-report.md)。01～05 ACCEPTED已归档，05交付79d576b/回执HEADf860bb59cd566743dc32912836cecff39f5df74b；六项暂缓变更保持。当前停止，等待用户正式验收及后续明确指令。

## 当前阶段（2026-11-14，05正式验收与Git归档）

**05六Task已实现、独立QA PASS并经主Agent复核，用户已正式验收，阶段ACCEPTED。** 05-QA-001/P2已修复、原QA独立复测并关闭，无未关闭05阻塞。最新完整真实PG216 passed/0 failed/0 skipped；主Agent最终Ruff(app/scripts/tests)通过、147文件格式通过。真实本地Qwen/PG检索、来源问答、显式偏好CRUD/跨会话隔离，以及英语偏好后真实新会话RAG均取得证据。

入口：[05技术验收](v1/v1-05/qa/05-rag-memory-stage-acceptance.md)、[简洁Handoff](v1/v1-05/05-rag-memory-handoff.md)、[最新协调](v1/v1-05/qa/05-remaining-main-review.md)。两库原业务/Saver保持、验收临时数据清理，schema6/Store迁移0～3，用户.env及006原字节保持；演示需显式启用Embedding并导入样本。05交付提交79d576bb47a45ffffe006a2a7182dd23bb825349已推送并核验origin/real-model-chat，含本轮使用的原生项目角色配置；原六项暂缓差异保留。归档回执另作文档提交，不替代交付标识，当前HEAD以git rev-parse为准。见[Git回执](v1/v1-05/05-git-archive-receipt.md)。**已停止，不进入06。** 下文各IN_PROGRESS/等待状态保留对应历史轮次，以本段为准。

## 当前工作单元（2026-11-13，05已授权）

用户已授权05，并以最新增量指令确定本轮仅本地Qwen Embedding及真实pgvector检索闭环。本工作单元已完成实现、自测、独立QA PASS与主Agent复核，状态VERIFIED，待用户审核；05整阶段仍IN_PROGRESS。任务见[05本地Embedding](v1/v1-05/05-local-embedding-execution-task.md)，协调见[05记录](v1/v1-05/qa/05-local-embedding-main-review.md)。模型在Windows D:\AI\models\qwen3-embedding-0.6b，CPU/1024维；原Ubuntu PG17.6安装pgvector。最终完整真实库172 passed/0 failed/0 skipped；QA另独立7项及真实Qwen/新进程持久检索通过。验收数据已清理，两库原业务和Checkpoint保持；见[独立QA](v1/v1-05/qa/05-local-embedding-qa-report.md)。不改其他Agent/业务，不将本单元完成等同05全部完成，不提交Git。下文“05等待/不启动”为此前交接轮次语境，已被本次明确授权覆盖。


更新：2026-11-13。以本页、当前工作单元和最新QA/协调记录为接手入口，历史记录按需查阅。

- 分支 `real-model-chat`，04交付提交 `ab30f12f8ca4cc9db767f9389d1120ec01c19ea0` 已推送并核验远端；01～04均ACCEPTED且已归档。当前HEAD以git rev-parse为准，后续回执提交不替代交付标识。原六项暂缓差异保留；05等待用户设置角色配置及后续指令，不启动。
- 原生Multi-Agent已接管，Implementer→独立QA串行；不使用Session Bridge。`.codex/agents/implementer.toml`与`qa.toml`已配置，Desktop内置0.167.0-alpha.4.1已实际显式选择两角色，使用fork_turns="none"。验证及兼容性见[配置记录](../.codex/README.md)；PATH旧CLI0.144.4不兼容，已启动的旧聊天需新开项目聊天加载。该配置轮未提交/推送，05仍等用户审核与后续指令。
- 04-QA-001～006独立复测通过并经主Agent关闭，见[首轮独立复测](v1/v1-04/qa/04-hitl-checkpoint-refund-fix-01-regression-report.md)。
- 4.3.2正式真实PG/进程/uvicorn/故障/DeepSeek证据见[开发报告](v1/v1-04/04-hitl-checkpoint-refund-restart-report.md)。最终修复版本完整真实库 **165 passed/0 failed/0 skipped**、Ruff代码通过；旧164项为修复前证据，不替代最终门禁。
- **04-QA-007已独立复测并经主Agent关闭，用户已正式验收04，阶段ACCEPTED，Git归档已完成并核验远端。** [修复记录](v1/v1-04/fixes/records/04-hitl-checkpoint-refund-fix-02-report.md)、[最终独立复测](v1/v1-04/qa/04-hitl-checkpoint-refund-fix-02-regression-report.md)及[技术验收](v1/v1-04/qa/04-hitl-checkpoint-refund-stage-acceptance.md)齐备。原三项失败均409，正常repair跨进程恢复通过，24矩阵必要缺口闭环；没有运行中的实施或QA单元。04归档后停止，不进入05。
- 数据库仅用专用agent_demo_test/agent_test，在线身份/迁移checksum、唯一数据及业务全行集/Saver自身线程精确清理继续要求。原五订单/他人数据保护；仅既有全回归seed幂等测试有明确窄例外，见当前任务。
- 凭据暴露/密码复用及P3-01六份Markdown格式遗留沿用户既有决定保留，不自行换密或扩整改范围。未知框架快照与未sync无可信窗口拒绝自动恢复，限制保留。

主Agent最新裁决见[协调记录](v1/v1-04/qa/04-hitl-checkpoint-refund-main-review.md)，冻结依据为[D04](v1/v1-04/04-hitl-checkpoint-refund-detailed-design.md)和[唯一路线图](v1/development-roadmap.md)。05首个Task为5.1.1，但本轮不得启动。
