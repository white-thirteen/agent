# V2 01 KnowledgeAgent RAG 增强：完整逻辑设计

状态：**DESIGN APPROVED**。BM25 引擎已按 2026-11-18 定向切换为 pg_textsearch，验证边界见 `docs/v2-01-bm25-switch-report.md`。

交付状态：**V2 01 = ACCEPTED**（2026-11-19）。六个 Task 的正式验收、证据与剩余风险见[阶段正式验收](v2-01-stage-acceptance.md)。

设计验收日期：2026-11-16。用户已原则验收本阶段设计，并要求在最终稿中补充正常语料的 BGE 超限门禁，以及功能正确性与检索质量收益分开验收的约束；本文已纳入。

**本状态仅代表逻辑设计通过，不代表开发授权、代码实现完成、真实运行验证通过或阶段交付验收通过。** 本轮仅保存设计文档，不修改业务代码、配置、依赖、数据库，不下载模型，不执行测试、部署或联调，不执行 Git 提交或推送。以下实施步骤、迁移、模型调用和验收均为未来计划，须另获开发授权。

保留三个二级环节、六个 Task 及 V1 KnowledgeAgent 八节点。不展开 V2 02 Context Engineering、03 ToolRegistry 渐进式披露，不设置独立系统集成阶段或 Evaluation/Trace 平台。归档后停止，等待用户下达 02 逻辑规划指令。

## 1. 依据、V1 现状与改造边界

依据：[项目定位](agent-engine-demo-plan.md)、[V1 路线图](development-roadmap.md)、[V1 D05](05-rag-memory-detailed-design.md)、[当前状态](STATE.md)、[V1 RAG 实测记录](rag-validation.md)，以及本轮已只读核实的源码。V1 文档中的历史 OpenAI/1536 参数不作为本阶段基线，现有实现为本地 Qwen CPU/1024 维。

V1 交付状态仍以 STATE 与各阶段验收记录为准。本文不将 V1 06 的技术 VERIFIED 改为用户 ACCEPTED，也不推导其 Git 归档授权。

### 1.1 实际实现

| 位置 | 当前职责与行为 |
| --- | --- |
| `app/graph/specialists/knowledge/builder.py` | 八节点知识子图；可信当前 Task 问题准备、工具选择、检索、证据评估、答案生成、来源验证和结果映射 |
| `app/knowledge/embedding.py` | LangChain Embeddings 兼容的 Qwen 本地 CPU Provider；单实例、有界推理、超时后的资源占用与关闭治理 |
| `app/knowledge/retriever.py` | Query Embedding、pgvector 候选检索、完整 Evidence 上下文组织和来源验证委托 |
| `app/knowledge/repository.py` | 当前文档及 Chunk 权威存储；事务替换/删除；精确余弦检索；当前版本、Chunk、哈希校验 |
| `app/knowledge/chunking.py` | 受控 md/txt 解析、清洗、标题/章节/行号、切分和确定性版本/Chunk ID |
| `app/knowledge/ingest.py` | manifest 导入、完整性检查、事务外 Embedding 与事务内发布 |
| `app/knowledge/models.py` | Document、Chunk、EmbeddingProfile、SearchQuery、SearchResult 和 Evidence 契约 |
| `app/tools/implementations/knowledge.py` | `search_knowledge`、`validate_knowledge_sources`，沿用 Policy/Executor |
| `app/main.py` | 模型、连接池、Repository、Retriever 和 Graph 的生命周期与依赖装配 |
| `migrations/006_knowledge_vectors.sql` | 当前文档与 Chunk 表、`vector(1024)`；没有本阶段 Sparse 索引 |

当前检索使用精确余弦排序，没有 ANN/HNSW。原 Retriever 数据库候选数为 5，对外 `top_k` 为 1～5、默认 3；上下文预算为 2400 cl100k Token 和 24 KiB。V1 Chunk 正文最多 500 cl100k Token，Embedding 文本最多 700 cl100k Token。这些长度不能直接证明满足 BGE Tokenizer 的长度限制。

原数据模型只保存当前文档版本，不提供历史全文保留。来源校验通过仅证明引用身份及当前版本有效，不能代替答案语义正确性验收。

### 1.2 本阶段边界

- 增强原 `search_knowledge` 底层，不增加 Graph 节点。
- 保留 Supervisor、Service、Runtime、Policy、Executor、Checkpointer 的核心职责。
- 不改退款审批、订单规则、幂等和故障恢复协议。
- 保留原 Qwen Provider、1024 维向量及 PG 权威数据，不为 Sparse/BGE 重算已有向量。
- 原知识为受控共享知识，执行现有身份、`knowledge:read` 和 domain 约束；不宣称已具备 V1 不存在的企业租户 ACL。
- 不恢复旧 Session Bridge，不增加多 Agent 并行调度。

## 2. 定向修订结论

| 项目 | 修订前 | 最终设计 |
| --- | --- | --- |
| BM25 主方案 | PG 倒排表与 SQL BM25 | 首选 pg_textsearch `1.5.1`，保留精确部署兼容门禁 |
| 自研 Sparse 基础设施 | 自建词项、词频、长度和统计维护 | 主方案取消；SQL BM25 仅保留备选，不同时开发 |
| 分词 | 应用侧独立 Jieba | 使用 zhparser 2.4 + SCWS 1.2.3，固定词典摘要 |
| BGE 输入 | 首尾双视图及多分数合并 | 完整 Query＋Chunk，一个候选一个分数 |
| 超长输入 | 视图截取 | BGE Tokenizer 预检，明确失败，不自动截断或跳过候选 |
| 超限门禁 | 输入边界验证 | 1.2.2 必须检查现有正常语料；频繁影响正常请求必须重新提交方案 |
| 质量验收 | 业务场景为主 | 固定语料/问题/标注，四组对照，Recall/MRR/nDCG 和 P50/P95 |
| 验收判定 | 容易混同功能与收益 | 功能正确性、质量收益分项判定；代码正确不能替代质量验收 |

## 3. BM25 技术选型与部署约束

### 3.1 已核实条件与版本锁定

BM25 主方案采用 **PostgreSQL 17.12 + pgvector 0.8.7 + pg_textsearch 1.5.1 + zhparser 2.4 + SCWS 1.2.3**。pg_textsearch 使用 PostgreSQL PGXS/C 扩展，不使用 pgrx；构建必须针对 17.12 headers，产物以 SHA256 固定。中文索引使用 `zhparser` 解析器与 SCWS 词典，`dict.utf8.xdb`、`rules.utf8.ini` 必须安装到 PostgreSQL `tsearch_data`，缺失时查询会静默无命中。

| 条件 | 已知事实 | 判定 |
| --- | --- | --- |
| PostgreSQL | 17.12（Debian 17.12-1.pgdg12+1） | 与 pg_textsearch 1.5.1 兼容 |
| pgvector | 0.8.7 | Dense 路径不变，同库共存已验证 |
| BM25 扩展 | pg_textsearch 1.5.1，PGXS，`shared_preload_libraries` | 已从源码针对 17.12 构建并加载 |
| 中文分词 | zhparser 2.4 + SCWS 1.2.3 | 固定 commit/版本及词典摘要 |
| 部署影响 | 预加载与实例重启 | 维护窗口内执行，需重启恢复验证 |
| 安全构建 | 不依赖未修复的 pgrx/pg_search 包 | 以 17.12 headers 重建并记录 SHA256 |
| 未验证项 | 大语料质量、BGE 重排、并发发布流程 | 属后续 Task/门禁，不在本轮冒充通过 |

来源：[pg_textsearch v1.5.1](https://github.com/timescale/pg_textsearch/releases/tag/v1.5.1)、[zhparser](https://github.com/amutu/zhparser/tree/21ee29212e9f3b3c34bafb096e184f26c84111b5)、[SCWS 1.2.3](http://www.xunsearch.com/scws/download.php)。本轮只读查阅不等于安装验证；实际构建/运行证据见 `docs/v2-01-bm25-switch-report.md`。

### 3.2 工程成本比较

| 方面 | PG 倒排表＋SQL BM25 | pg_textsearch |
| --- | --- | --- |
| 部署 | 无新扩展 | 增加 C 扩展、预加载配置及镜像构建步骤 |
| 实现 | 自行维护倒排、tf、长度、统计与评分 | 索引定义、查询适配、配置和版本管理 |
| 一致性 | 应用维护多个派生表 | 扩展索引随表事务更新 |
| 优化 | 项目自行承担检索访问路径与性能优化 | 复用 Block-Max WAND TopK、LSM/compaction |
| 中文 | 自建分词与词典维护 | zhparser + SCWS 固定词典 |
| 维护风险 | 自研检索基础设施膨胀 | 扩展兼容、版本及部署回归 |

pg_textsearch 将索引更新纳入当前事务，减少应用侧独立 Sparse 双写职责。首版仍保留现有 pgvector Dense 精确检索，不顺带切换到扩展提供的向量检索。ParadeDB `pg_search` 仅保留为隔离环境的 Jieba 质量对照，不作为正式部署候选。

### 3.3 选择及兼容门禁

**采用 pg_textsearch 为 BM25 主方案，SQL BM25 为备选设计，不预先实现两套。** 正式启用前必须满足：

1. 在隔离环境用 PostgreSQL 17.12 headers 构建并记录 pg_textsearch、zhparser、SCWS 的来源、版本、SHA256 和构建参数；不得使用早于 17.12 的预编译包冒充安全构建。
2. 验证中文/英文/中英混合索引、查询参数化、固定 `text_config='public.chinese'`、词典安装和零分文档排除。
3. 验证 Chunk ID 的索引身份、`domain`/`document_version` 过滤、Top K、更新/删除/回滚可见性、重启恢复和并发读一致性。
4. 验证 Dense/Sparse 同一快照读取、RRF 输入排序和最终来源一致性；RRF 使用排名，不直接混用负 BM25 分数与余弦分数。
5. 检查固定环境的资源、延迟、索引维护和失败恢复；大语料性能与 BGE 质量另属后续门禁。

不能直接使用 `pg_textsearch` 预编译包或 `latest` 镜像；必须基于固定 PostgreSQL 17.12 镜像构建候选扩展镜像，保护原容器和卷。若构建、加载、过滤 TopK、并发或持久化不通过，停止切换并提交证据，不以 ParadeDB 静默回退。SQL 备选保留固定分词、倒排和 BM25 评分思路，但不在本阶段提前建设，也不作为运行时静默回退。

## 4. 目标架构与调用链

```text
KnowledgeAgent 原八节点
        │
        ▼
search_knowledge → HybridRetriever
  ① 身份/权限与 Query 约束
  ② 原 Qwen Query Embedding
  ③ 同一数据库只读快照内顺序执行：
       pgvector Dense Top10
       pg_textsearch BM25 Top10
  ④ RRF 融合与来源身份去重，取 Top10
  ⑤ BGE Tokenizer 完整输入预检
  ⑥ BGE 重排
  ⑦ 完整 Evidence 预算组织
        │
        ▼
assess_evidence → generate_answer → validate_sources → map_result
```

### 4.1 Graph、Service 与接口

原八节点顺序保留：

`check_request → prepare_query → select_retrieval_tool → retrieve_knowledge → assess_evidence → generate_answer → validate_sources → map_result`。

- `prepare_query` 继续取当前 Task 的可信用户问题，不接受模型改写身份、路径、Profile 或权限。
- 工具仍经同一 Policy/Executor，公开工具参数不提供模型可选的检索引擎或本地文件路径。
- 检索器继续提供 search 与 validate_evidence 能力；Graph 不依赖 pg_textsearch/BGE 的加载细节。
- Repository 提供同一连接/事务内的 Dense 与 Sparse 查询；不为两路召回增加 Agent 并行或 Graph 节点。
- `assess_evidence` 继续判断 sufficient/insufficient/conflicting/needs_clarification。
- `generate_answer` 只使用选中的证据；`validate_sources` 发布前校验当前版本和引用身份，不公开失效草稿。

### 4.2 召回和融合

两路在各自 Top10 截取前执行相同的现有领域、身份及当前版本约束。先生成 Query Embedding，再进入只读 REPEATABLE READ 事务执行两路查询与元数据读取；事务结束后进行 BGE，模型推理不占用数据库事务。

等权 RRF：`RRF(d) = Σ 1 / (60 + rank_r(d))`，排名从1开始，未召回路贡献为0。去重使用文档版本与 Chunk 身份，不合并不同来源的相同正文；并列采用固定来源身份排序。原始余弦、BM25 与 BGE 分数不直接相加，不统一解释成概率。参考 [RRF 原论文](https://cormack.uwaterloo.ca/cormack/cormacksigir09-rrf.pdf)。

### 4.3 上下文及预算

对外 `top_k` 仍为1～5、默认3。保留原2400 cl100k Token 与24 KiB上下文上限，预算包含证据正文及必要元数据。完整 Chunk 放不下时继续检查后续候选并记录预算筛选，不能截断正文却保留原全文哈希；全部无法组织时返回明确预算失败。

检索30秒总预算为设计配置提案：Embedding8秒、双路数据库阶段合计5秒、BGE15秒及剩余处理余量。它不是实测性能承诺。实施时集中配置并对齐工具/检索器期限，不留多个冲突的硬编码；Runtime既有总期限继续生效，分阶段上限不保证每次可用完整额度。

## 5. BGE 输入及资源设计

### 5.1 单视图重排

候选模型为 `BAAI/bge-reranker-base`，固定权重/Tokenizer revision，复用 sentence-transformers CrossEncoder，CPU单实例、小批量。它提供中英文 Query/Passage 成对评分，参考[官方模型卡](https://huggingface.co/BAAI/bge-reranker-base)。

每个候选输入为：完整 Query＋固定格式的标题、章节和完整 Chunk 正文。一个候选一个分数，取消首尾双视图与分数合并。不自动替换更大模型，不引入外部推理服务。评分类型固定并写入 Profile，不把默认激活函数产生的数值称为校准概率。

2026-11-19 实现契约：对完整 RRF 候选池执行既有 BGE 预检并评分，仅在 RRF 前三内部按原始 logit 降序、完整来源身份升序排序。第四名起保留 RRF 顺序，尾部高分不能进入前三。评分用时计入原有检索预算和超时，继续使用完整 Chunk 预算及权威来源校验。排序策略写入 `RetrievalProfile`，标识为 `rrf-top3-bge-local-v1`，旧策略的缓存观察无法通过 Profile 校验。

### 5.2 Tokenizer 预检和超限策略

- 使用对应 BGE Tokenizer 检查实际输入对，包含特殊 Token，检查时关闭截断。
- 首版按模型使用约定采用512 Token上限，不使用 Qwen/cl100k 数量替代。
- 推理沿用完全相同的输入格式，不允许库的默认截断悄悄改变已检查输入。
- 任一待重排候选超限，返回 `rerank_input_too_long` 技术失败。
- 不截断 Query/Chunk，不跳过超长候选，不把故障转换为知识不足，不自动回退 RRF-only，不公开回答草稿。

这一策略可能拒绝部分 V1 合法长输入；原 Dense 模式保留为显式运维回退，不能称 Hybrid 已覆盖所有 V1 输入。

### 5.3 正常语料超限门禁（用户补充约束）

**Task 1.2.2 必须检查现有正常语料的超限情况，而不只验证人工构造的边界输入。** 使用现有正常文档、原正常问题以及固定质量问题集，记录实际 Query/Chunk 配对长度、超限数量、比例、涉及问题和来源；区分问题过长与正常 Chunk 导致的超限。

不得只检查 Chunk 本身长度，不得通过删掉超长候选或测试样本降低超限率。正常请求是否受影响是独立验收项，实际数据和业务影响必须提交审核。

**若超限频繁影响正常请求，1.2.2 不得直接判定通过；必须重新提交输入预算或切分方案，说明版本、引用、旧向量兼容及资源影响，等待用户审核。** 不在本次设计中虚构一个已获批准的频率阈值，也不以单个演示成功掩盖普遍失败。必要调整须明确获批后实施，不能自动改切分、升级长上下文模型或启用隐式截断。

### 5.4 生命周期和容量

Qwen 与 BGE 复用单进程受控 CPU 推理容量；模型在生命周期中初始化和释放，不按请求反复加载，不在单例中存请求可变状态。推理离开事件循环；底层计算真实结束前，即使调用方超时或取消也不释放容量。默认小批量，不增加无界等待队列。

初始化失败明确标记 Knowledge 能力不可用，保持其他能力原有就绪边界。离线导入不能与在线推理各自额外加载一份 Qwen 而绕过资源限制。内存与加载/推理耗时仅在后续实测后填写。

## 6. 数据、State 与索引版本

### 6.1 保留的权威契约

- Document、Chunk 和现有 EmbeddingProfile继续使用。
- EvidenceReference仍为 `document_id/document_version/chunk_id/content_hash` 四元组。
- 保留 PublicCitation、行号、来源标题和公开来源键，路径不外泄。
- Sparse/BGE配置变化不修改 document_version，不重算 Qwen 向量；修改原文或切分规则仍按原版本机制生成新版本。

### 6.2 主方案增量

| 对象 | 内容与职责 |
| --- | --- |
| `knowledge_chunks.search_text` | 由标题、章节、完整正文确定性生成，供 Sparse 索引；不改变正文和来源哈希的含义 |
| pg_textsearch 索引 | 扩展管理词项、词频与 BM25；Chunk ID 作为稳定来源身份，索引字段/语法按固定版本验证 |
| `knowledge_index_state` | 激活的 Sparse Profile、索引身份与发布水位；不保存历史全文 |
| SparseIndexProfile | 扩展版本、索引字段、zhparser/SCWS 版本、BM25 参数和输入格式 |
| RetrievalProfile | 两路候选数、RRF、BGE版本/Tokenizer/输入/评分方式、局部排序策略、上下文策略 |
| 内部候选 | 来源身份、两路排名/分数、RRF与重排分数，禁止混淆分数含义 |
| SearchResult | 保留原结果信息，增加显式模式、Profile与索引水位等诊断字段；Graph按明确版本解析 |

主方案不新增自研 sparse_terms/tf/长度维护表。BM25 统计采用固定扩展的索引语义，不再承诺按每次 domain 过滤集合重新计算统计。首版建议索引与查询使用同一 `text_config='public.chinese'`；不删除否定词，不开放用户检索表达式或任意数据库字段。

### 6.2.1 BM25 索引与查询契约

- 索引 Profile：`extension=pg_textsearch 1.5.1`、`text_config=public.chinese`、`tokenizer=zhparser 2.4`、`dictionary=scws-1.2.3`，索引字段固定为 `search_text`；`chunk_id` 仅作为稳定结果身份返回，不参与 BM25 文本索引。
- DDL 约定：`CREATE INDEX ... ON knowledge_chunks USING bm25 (search_text) WITH (text_config='public.chinese');`，索引名和 Profile 进入 `knowledge_index_state`，不按 domain 建独立统计索引。
- 查询约定：`ORDER BY search_text <@> to_bm25query(%(query)s, %(index)s) ASC LIMIT %(top_k)s`；`<@>` 返回负 BM25 分数，越相关越负，禁止把原始分数直接与余弦相似度相加。
- TopK：`sparse_candidates=10`，先按上述顺序取 Top10，再由 RRF 使用排名融合；零分/无词项文档不是 BM25 候选，不能填充为有效命中。
- 过滤：`domain`、`document_version` 作为同一 SQL 的 `WHERE` 条件，与排序同语句、同只读快照执行；允许 planner 选择 B-tree 预过滤后独立评分，或 BM25 索引扫描后过滤，但结果必须与完整候选排序一致。V2 不承诺过滤集合内重算 BM25 统计。
- 返回：只向上层提供来源身份、排名和明确标记的 BM25 分数；排序方向、Profile 和索引水位写入结果诊断字段，保持 Retriever/RRF/KnowledgeAgent 接口契约不变。

### 6.3 更新、回填与一致性

新文档在事务外生成向量；原Repository发布事务中写文档、Chunk、search_text与向量，扩展维护其索引，不增加应用层异步双写。更新/删除必须同时改变两路可见数据，回滚不留下可检索的半成品。

旧文档只回填Sparse输入并建立索引，不重算向量。导入完整性检查区分Dense已完整与Sparse已准备，不能因旧的skip逻辑漏建索引。首版采用受控维护窗口，不建设双索引热切换平台。激活前检查覆盖、输入一致性与索引就绪；部分回填不能标记为可用。

文档更新/删除及索引激活更新发布水位；具体事务锁顺序固定，避免版本发布与索引激活竞争。检索快照中的证据在发布答案前仍经过现有来源验证，已经被更新/删除的引用不能公开。版本水位不等于可恢复历史正文。

### 6.4 State 和重放

不新增Graph节点，不整份复制父子图State。原检索结果字段承载明确版本的SearchResult，证据评估仍选择受检索约束的Evidence ID。模型不能覆盖可信身份、Task或Profile。

检索工具采用明确的新版本；原调用记录重放继续检查工具、参数、来源节点及结果契约。旧缓存不能冒充新Profile结果。不在活动知识Task中热切换实现；退款工具版本、审批关联和Checkpoint命名空间保持原有语义，并在应用集成验收中回归。

## 7. 三个二级环节与六个 Task

### 7.1 环节 1.1 检索契约与持久索引

**1.1.1 技术适配与契约冻结**

- 步骤：核对固定环境→独立候选镜像/数据库验证 pg_textsearch→验证中文、过滤与事务→固定版本、Profile、结果契约和回退步骤。
- 交付：兼容性证据、配置/数据契约、迁移与回滚说明；不兼容则提交备选裁决。
- 验收：PostgreSQL 17.12/vector 0.8.7 基线保持，关键查询与恢复通过；不能以存在 PG17 安装包代替实际兼容验证。

**1.1.2 Sparse准备、事务发布与回填**

- 步骤：增加Sparse输入和状态→接入发布事务→旧文档回填与覆盖检查→受控激活。
- 交付：迁移、索引、导入/回填能力与一致性证据。
- 验收：旧向量不重算；重复执行可核对；更新、删除、事务失败不产生两路版本混杂；未完整不能激活。

### 7.2 环节 1.2 混合召回与本地重排

**1.2.1 BM25、Dense与RRF**

- 步骤：同快照两路查询→过滤后Top K→RRF→去重、稳定排序及错误映射。
- 交付：Hybrid召回、候选契约及定向验证。
- 验收：两路遵守相同权限/domain/当前版本；空结果与技术故障分开；排名和去重可复核；不持事务执行模型推理。

**1.2.2 BGE与推理资源管理**

- 步骤：本地固定模型→完整输入预检→单视图评分→共享CPU容量与生命周期→现有正常语料配对长度/超限检查→真实资源及异常验证。
- 交付：真实重排、输入长度与正常请求影响报告、加载/耗时/内存及超时/关闭证据。
- 验收：无隐式截断、跳过或降级；真实模型而非Mock验收；超时后容量正确。**正常语料频繁超限必须重新提交输入预算或切分方案，不得直接通过。**

### 7.3 环节 1.3 Graph接线与阶段验收

**1.3.1 知识工具与八节点接线**

- 步骤：装配Hybrid→更新工具版本和结果解析→检查重放→验证证据评估/答案/来源链。
- 交付：原图接线及可信边界、版本和重放证据。
- 验收：八节点保持；不绕过Policy/Executor；旧结果不能伪装新结果；来源失效不公开草稿。

**1.3.2 真实业务验收与V1兼容**

- 步骤：冻结语料/问题/标注→执行四组对照→计算排名和最终上下文指标→实际延迟/资源→业务及V1回归→功能与质量分项结论。
- 交付：可复算的检索结果、指标报告、实际运行环境与命令、异常和未执行记录、独立QA及主Agent复核证据。
- 验收：真实Qwen/BGE/PG，质量收益单独判定；指标退化如实分析，不以代码正确替代质量验收，不修改样本掩盖退化。
- 实现记录：**Task 1.3.2 = ACCEPTED**（2026-11-19）。用户正式批准采用 RRF Top3 局部 BGE 重排。冻结集五轮、独立题、真实业务和独立 QA 见[验收归档](v2-01-task132-acceptance.md)。

依赖顺序保持：`1.1.1 → 1.1.2 → 1.2.1 → 1.2.2 → 1.3.1 → 1.3.2`。未来获开发授权后按Implementer→独立QA串行实施，设计通过不启动该流程。

## 8. 检索质量验收

### 8.1 固定数据

建立阶段夹具，不建设评估平台。保留现有六篇知识文档，增加固定的相近主题干扰文档，使候选竞争超过Top10。干扰资料不能随意与正式规则矛盾；冲突检测使用独立明确标注的功能场景。

验收采用隔离环境和独立文档ID，不写入原业务知识库。冻结manifest、原文哈希、切分版本、Chunk映射、问题、domain/权限范围及相关性标注。现有六篇微型语料单独通过不能证明混合检索有质量收益。

固定首版问题集为20个有答案问题和4个无答案问题：

| ID | 问题 | 预期证据文件（正式标注须绑定完整来源身份） |
| --- | --- | --- |
| Q01 | 当前提供哪些演示用户？ | account-help |
| Q02 | 选择 dev-user 是否等于真实生产登录？ | account-help |
| Q03 | 如何发起模拟退款申请？ | refund-entry |
| Q04 | 申请模拟退款需要提供什么信息？ | refund-entry |
| Q05 | 知识说明可以改变退款资格和金额吗？ | refund-entry |
| Q06 | 等待审批时，在聊天中说“同意”可以批准吗？ | approval-wait |
| Q07 | 审批通过后恢复原任务还是另建任务？ | approval-wait |
| Q08 | 一次审批能放行其他任意调用吗？ | approval-wait |
| Q09 | 模拟退款会扣真实银行卡的钱吗？ | refund-safety |
| Q10 | 退款结果未知时可以直接再退一次吗？ | refund-safety |
| Q11 | 相同退款操作如何避免重复副作用？ | refund-safety |
| Q12 | 查询订单需要提供什么？ | order-query |
| Q13 | 能查看其他演示用户的订单吗？ | order-query |
| Q14 | 关闭聊天页面后，已受理任务会停止吗？ | stream-help |
| Q15 | 断开连接后应如何核对任务结果？ | stream-help |
| Q16 | If the stream disconnects, does the accepted task continue? | stream-help |
| Q17 | Does this demo connect to a real payment provider? | refund-safety |
| Q18 | Who handles a pending refund approval? | approval-wait |
| Q19 | dev-user 和 demo-user-b 是生产认证账号吗？ | account-help |
| Q20 | 申请退款后，谁审批，审批后如何继续？ | refund-entry、approval-wait |
| Q21 | 火星基地量子发动机的保修期是多少年？ | 无答案 |
| Q22 | 真实银行卡退款需要几天到账？ | 无答案 |
| Q23 | 生产账号忘记密码怎样重置？ | 无答案 |
| Q24 | 国际物流费用如何计算？ | 无答案 |

原有冲突、注入、来源更新/删除及故障场景继续做功能验收，不混成普通排名得分。本问题集代表项目级验收，不外推为通用检索基准。

### 8.2 证据标注

先标注原文证据范围，再映射到固定Chunk，保存document_id/version/chunk_id/hash。0=无关，1=有背景关联但不能直接回答，2=直接支持部分关键答案，3=直接支持完整关键答案。

Recall/MRR以等级≥2为相关；nDCG使用分级增益。覆盖整个固定小语料中的有效证据，不能只标一个预期文档而漏掉其他有效来源。合并四组候选检查漏标；若确需纠正标注，保留原记录、说明原因并统一重新计算四组，不能只修对某组有利的标签。

### 8.3 四组方案

| 组别 | 方案 | 比较排名 |
| --- | --- | --- |
| A | Qwen＋pgvector Dense | Dense Top10 |
| B | pg_textsearch BM25 | BM25 Top10 |
| C | Dense Top10＋BM25 Top10＋RRF | 融合Top10 |
| D | 对C的同一批Top10执行BGE | 重排Top10 |

四组固定相同语料版本、Query与权限/domain。C/D使用同一候选池；记录各组真实计算成本，不宣称四组计算量相等。D只是重排C的10个候选，所以二者Recall@10应相同，不能据此声称BGE提高了该指标。

正式复验增加 E 组，仅对 C 的前三局部排序。D 与 E 共用同一候选池及各候选的真实 BGE 分数。正式采用的 E 按 8.6 中 D 对 C 的原排序目标验收，保留 D 作为全量重排对照，冻结语料、标注及门槛保持原基线。独立题单列，局部策略无法把 RRF 前三以外的证据补进前三，泛化与并发排序稳定性仍待覆盖。

排名指标在上下文组织前计算；最终完整Evidence的覆盖另列，防止预算筛选掩盖关键证据丢失。公开工具top_k仍最多5，验收读取内部排名不等于修改公开工具契约。

### 8.4 指标

对有答案问题，K取3、5、10，按问题宏平均：

- Recall@K：Top K相关Chunk数量/该问题全部相关Chunk数量。
- MRR@K：第一个相关结果排名的倒数；前K无相关结果为0。
- nDCG@K：DCG使用`(2^relevance-1)/log2(rank+1)`，除以该问题理想排序的IDCG。

无答案问题不混入这些指标分母，另报证据不足判断、错误回答与虚构来源。Dense返回候选并不意味着应该回答。

### 8.5 延迟与失败

计时从权限检查通过后的检索入口开始，到完整Evidence组织结束，包括Query处理/Embedding、数据库、融合、BGE和上下文组织，不包含答案生成。

固定顺序种子和重复次数，预热后建议有答案问题每组5轮；使用统一的最近秩百分位方法，排序后取`ceil(p*N)`对应样本。报告总检索P50/P95、Embedding/数据库/BGE阶段耗时，模型冷加载单列。记录机器、可用内存、模型版本、配置、实际内存及受控并发结果，不清理原生产/演示数据库缓存来制造条件。

成功请求延迟、全部尝试结果和失败耗时分开报告，同时报告成功率、超时率、输入超限及其他错误。排名得分不能通过丢弃失败问题提高；应报告全部固定问题的运行完成情况，并将有答案请求失败在整体收益统计中按未取得证据计入，同时给出成功子集诊断。质量计算不需要把同一重复请求当成多个独立问题。

### 8.6 功能正确性与质量收益分开验收（用户补充约束）

**功能正确性**检查过滤、事务、排名实现、输入边界、资源、来源、重放和V1兼容。**质量收益**检查固定数据上的召回与排序表现，独立给出通过、未通过或阻塞结论。

下列为冻结后的对比目标，不是算法必然保证：

1. C的Recall@10不低于A。
2. D的MRR@3、nDCG@3不低于C，并同时列出相对A的变化。
3. 逐题报告改善与退化，固定关键问题检查必要证据。
4. 无答案、冲突和过期来源不能产生伪成功。

**若Recall、MRR或nDCG退化，必须如实记录并分析候选截取、词项匹配、融合、重排或上下文预算等原因。功能测试通过或代码实现正确，不能替代质量收益验收，也不能自动使该项通过。** 不虚构提升幅度，不把更复杂等同于更优。

**不得通过删除/替换困难问题、改标签迎合结果、漏报失败或选择性报告掩盖退化。** 合理的数据纠错或方案调整须保留版本与原始结果，说明影响并重新评审；统一重跑比较，不追溯覆盖历史失败。未达目标时提交分析和调整建议，由用户裁决，不擅自降低门槛或直接宣称阶段完成。

## 9. 异常、回滚与V1兼容

| 场景 | 行为 |
| --- | --- |
| 一路合法无命中 | 另一有效路可继续融合 |
| 任一路技术失败 | Hybrid明确失败，不冒充知识不足 |
| BGE超限/超时/异常 | 明确失败，不截断、不隐藏降级 |
| 索引未完整回填 | 不激活Hybrid |
| 查询后文档更新/删除 | 来源复核拒绝失效引用及草稿 |
| Profile变化 | 显式版本校验，旧缓存不能冒充新结果 |
| 扩展不适配 | 停止部署，提交备选裁决 |
| 回滚 | 显式恢复原Dense模式，保留文档与向量，不删除业务数据 |
| 进程/数据库重启 | 验证索引持久化、模型生命周期和检索恢复 |

V1回归涵盖知识权限/domain、冲突/不足、文档注入、更新删除/伪造来源、工具预算、重放与真实持久化。应用生命周期变化还须覆盖退款审批暂停/恢复及Store原有行为；保留既有阶段门禁和数据保护约束，不能用新知识验收扩大订单seed或修改业务数据授权。

## 10. 拟修改文件与职责

以下全部为未来实施规划，本轮仅新增本文。

| 文件/范围 | 规划职责 |
| --- | --- |
| `app/knowledge/models.py` | Profile、候选排名、版本化SearchResult |
| `app/knowledge/repository.py` | 同快照Dense/Sparse查询、索引状态、发布事务 |
| `app/knowledge/retriever.py` | Hybrid编排、预算和错误映射 |
| 新增 `app/knowledge/lexical.py` | 固定版本 pg_textsearch 查询适配 |
| 新增 `app/knowledge/fusion.py` | RRF与稳定去重排序 |
| 新增 `app/knowledge/reranker.py` | BGE加载、完整输入检查和评分 |
| `app/knowledge/embedding.py`及必要共享资源模块 | 复用现有有界CPU推理机制，不重复设计Provider |
| `app/knowledge/ingest.py` | Sparse完整性、回填与发布 |
| `app/tools/implementations/knowledge.py` | 工具版本、期限与结果契约 |
| `app/graph/specialists/knowledge/builder.py` | 结果解析和重放约束，保留八节点 |
| `app/main.py`、`app/core/config.py`、`.env.example` | 生命周期、模式和集中资源配置 |
| 新增知识索引迁移 | search_text、索引状态与扩展索引；不改旧迁移 |
| `deploy/` | 固定基线的扩展候选镜像与恢复说明 |
| 测试夹具、阶段验证脚本和文档 | 四组排名/标注、真实模型/PG、质量及资源报告 |

具体新增迁移编号和共享资源文件名在开发前依当时仓库状态确定，不覆盖其他阶段已有文件。不创建通用插件框架、自研检索编排系统或独立评估服务。

## 11. 设计验收与停止记录

2026-11-18：Task 1.1.1 = **ACCEPTED**。交付范围、固定基线和后续验证边界见[Task 验收归档](v2-01-task111-acceptance.md)。以下内容保留原设计轮次记录。

用户已批准本阶段逻辑设计，并补充两项强制约束：正常语料BGE超限影响必须在1.2.2审核；检索质量退化必须与功能正确性分开判定并如实保留。本文状态为 **DESIGN APPROVED**；BM25 引擎切换见独立报告，不改变阶段设计批准状态。

pg_textsearch 的 BM25 切换基础兼容验证已完成（构建、加载、中文、事务、重启、过滤 TopK、5000 Chunk 压力及并发可见性），见 `docs/v2-01-bm25-switch-report.md`。**完整质量与规模门禁仍未完成**：V2 固定语料/Chunk 级标注、Dense/RRF/BGE、真实 BGE 长度/资源检查、生产规模延迟与索引维护仍属于后续开发/验收工作，不是本轮已通过的运行证据。BGE 本地路径、具体模型 revision 及扩展包摘要在实施时核对并固定，不伪造当前不存在的测量值。

本轮仅归档设计，不更新V1验收状态，不执行Git提交/推送，不进入01开发，不展开02/03。完成后停止，等待用户另行授权02逻辑规划。
