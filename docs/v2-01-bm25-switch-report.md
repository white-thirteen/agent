# V2 01 BM25 技术切换报告

**日期**：2026-11-18
**状态**：BM25 技术切换 `ACCEPTED`。见[独立复验和归档](v2-01-task111-acceptance.md)。
**范围**：仅 BM25 引擎由 ParadeDB `pg_search` 切换为 Tiger Data `pg_textsearch`，不执行 V2 01 1.1.2 及后续 Task。

机器可读证据见 [`v2-01-bm25-switch-evidence.json`](v2-01-bm25-switch-evidence.json)。

## 1. 切换内容

| 项 | 切换前 | 切换后 |
| --- | --- | --- |
| BM25 扩展 | ParadeDB `pg_search 0.26.6` | `pg_textsearch 1.5.1` |
| 中文分词 | ParadeDB 内置 Jieba | `zhparser 2.4` + `SCWS 1.2.3` |
| 索引语法 | `USING paradedb` / `pdb.jieba` | `USING bm25` / `to_bm25query` |
| 预加载 | `pg_search` | `pg_textsearch` |
| Dense | pgvector 0.8.7 | 不变 |
| RRF/BGE | 既有设计 | 不变，本轮不实现/不评测 |

`app/knowledge/models.py` 的 `SparseIndexProfile` 已改为：

```text
extension=pg_textsearch
extension_version=1.5.1
text_config=public.chinese
tokenizer=zhparser / tokenizer_version=2.4
dictionary_version=scws-1.2.3
result_identity_field=chunk_id（仅结果身份，不是 BM25 索引字段）
text_field=search_text / indexed_fields=(search_text,)
score_order=ascending_negative
```

Profile 的 `key` 会随版本、词典和分数方向变化，避免旧缓存/旧索引身份冒充新 Profile；声明 Profile 仍不等于激活索引。

## 2. 版本、来源与构建

| 组件 | 固定版本/来源 | SHA256 |
| --- | --- | --- |
| PostgreSQL 基础镜像 | `postgres:17.12-bookworm@sha256:40865bc877a289da75963d97d72b59633f639fc5af7a4e856bfa3714cae5b536` | 见 `base-image.txt` |
| 头文件包 | `postgresql-server-dev-17 17.12-1.pgdg12+1` | 见 `build-env.txt` |
| pgvector 包 | `postgresql-17-pgvector 0.8.7-1.pgdg12+2` | 见 `candidate-vector2-package.txt`、`formal-vector-package.txt` |
| pg_textsearch | v1.5.1 源码 tarball | `2E7FB76ED96176AFC6D16CC5D095CED2CB233FF27FBEAA8C7BFFFC82E02F7498` |
| zhparser | commit `21ee29212e9f3b3c34bafb096e184f26c84111b5` | `F54018BE7509E9E68FAE95A078BCD0A3699BB20B04E5059CC4C7352C1C2FED67` |
| SCWS | 1.2.3 | `60D50AC3DC42CFF3C0B16CB1CFEE47D8CB8C8BAA142A58BC62854477B81F1AF5` |
| pg_textsearch.so | 17.12 头文件构建产物 | `6d2906e39c2e60acf03437359f5b3c3cf23d183445c6a8cc6a8eb782a40cbd88` |
| zhparser.so | 同上 | `30bb78ec7b788360c00eabf374f9d804373e5a2ea7dba132acbba65133ca8fb9` |
| libscws.so.1.1.0 | 同上 | `7795483ed9f7b7924fe406b319344711fc984ab9cd074b8a73ac6b5bd837e8a8` |
| `dict.utf8.xdb` | zhparser commit 内置词典 | `FD76A689F996C4E68CE53325A6A24DC652A678B1E7F676E4C5CA76265609A3E2` |
| `rules.utf8.ini` | 同上 | `45395F794226581FB1CC02B44AE1481804152511FC59FA677E2F7B755440479C` |
| 候选运行镜像 | `v201pt-candidate:1.5.1-vector2` | Id/RepoDigest `sha256:748b51b8d45a51bc517424a9cd78aab4c8d268fe2155cca018b66f84c361ce85` |

构建证据路径：`docs/v2-01-bm25-switch-evidence-20261118/build.log`、`build-env.txt`、`build-commands.txt`、`artifacts.sha256`、`candidate2-image.txt`、`candidate2-hashcheck-clean.out`。构建在独立容器内重新执行，未用旧日志补写历史。可追溯链为：源码 SHA256 → `build-env.txt` 头文件/编译器版本 → `artifacts.sha256` 扩展产物 → 候选镜像 ID/Digest → `candidate2-hashcheck-clean.out` 实际加载产物逐项 `OK`。

构建要求：

- 必须安装与 17.12 匹配的 `postgresql-server-dev-17`，使用 `PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config`。
- 构建显式传 `with_llvm=no`；本次 `postgresql-server-dev-17` 仍带入 clang/llvm，PGXS 同时安装了 bitcode 文件，但运行时只加载 `.so`，构建未因 clang 失败。
- SCWS 安装到 `/usr/local`，`ldconfig` 后构建 zhparser；zhparser 的 `dict.utf8.xdb`、`rules.utf8.ini` 必须复制到 PostgreSQL `$SHAREDIR/tsearch_data/`。
- `shared_preload_libraries='pg_textsearch'`；需要重启实例生效。
- 不得使用早于 17.12 的预编译 pg_textsearch 包作为安全证明；不得使用 `latest` 镜像。

现有 `deploy/postgres-vector.Dockerfile` 与 `compose.yaml` 是 V1 的 PG17.6 基线，本轮不改动，避免破坏 V1；V2 按上述配方另行构建候选镜像，正式部署前仍需独立验证镜像摘要与恢复步骤。

## 3. 验证结果

### 3.1 加载、中文、事务、持久化

隔离环境仅 Unix socket、无宿主端口，原 PG17.6 容器/原卷及当前 PG17.12 正式库均未重启或修改。

| 检查 | 结果 |
| --- | --- |
| 扩展加载 | `pg_textsearch 1.5.1`、`zhparser 2.4`、`vector 0.8.7`、`plpgsql 1.0` 正常 |
| 中文索引 | 39 Chunk 建索引成功；中文查询返回非零负分 |
| 事务回滚 | 事务内 INSERT/UPDATE/DELETE 后 ROLLBACK，行数和正文不变 |
| 增量更新 | 插入、更新、删除后索引立即反映；删除后行数恢复 |
| 重启恢复 | 重启后索引和查询结果保留；`memory_limit=128MB` 生效 |
| 源验证 | 返回 Chunk ID 与源文档身份一致；零分文档不作为有效命中 |

固定 SQL 与原始输出：`docs/v2-01-bm25-switch-evidence-20261118/runtime/`。其中 `v201pt-evidence-setup.sql` 建 7 篇固定数据；`checks.out` 保存中文 `EXPLAIN (ANALYZE)`、事务回滚和增量更新输出；重启见 `restart-*.out`；过滤 TopK、DELETE 与并发分别见 §3.2～§3.4。中文查询使用 `evidence_bm25` Index Scan，返回 `doc-refund` 等 4 个非零负分结果；事务回滚前后均为 7 行，正文未变；增量插入/更新后可立即检索，删除后恢复 7 行。

### 3.2 过滤后 TopK

固定数据为 7 篇（`runtime/v201pt-evidence-setup.sql`），同一过滤条件 `domain='after_sales_help' AND doc_version=1`，同一非零条件 `content <@> to_bm25query('退款','evidence_bm25') < 0`，确定性排序 `score ASC, id ASC`，K=5：

| 路径 | 计划 | 实际返回 |
| --- | --- | --- |
| 顺序扫描 | `Seq Scan` + Sort + WindowAgg | 2 行：`doc-refund`、`doc-safety` |
| BM25 索引扫描 | `Index Scan using evidence_bm25` + Incremental Sort + WindowAgg | 2 行：`doc-refund`、`doc-safety` |

两条路径的 `(rank,id,score)` 完全一致（`filter-compare-clean.out` 为空 diff）；有效候选只有 2 条，查询返回 2 条，没有用零分文档补足 K=5。原始 SQL/计划/结果：`runtime/v201pt-filter-seq.sql`、`v201pt-filter-idx.sql`、`filter-seq.out`、`filter-idx.out`。这证明固定夹具下两种访问路径的过滤 TopK 一致；不承诺真实大语料上 planner 一定选择同一路径。

### 3.3 DELETE 后索引一致性

`runtime/v201pt-delete.sql` 与 `delete.out`：

| 阶段 | 结果 |
| --- | --- |
| 插入 `del-1` 后 | `before_delete=1`，`qzdelete_hits=1` |
| 事务内 DELETE | `inside_tx=0` |
| ROLLBACK 后 | `after_rollback=1`，`qzdelete_hits=1` |
| 提交 DELETE 后 | `after_delete=0`，`qzdelete_hits=0` |
| 全表旧关键词 | `all_qzdelete_hits=0` |

已删除文档及其旧关键词在提交后不再命中；回滚保留原文档和命中。

### 3.4 并发可见性

本轮只就固定夹具作结论：**未提交变更不可见，提交后可见**。原始输出 `runtime/candidate2-conc-*.out`（UTC）：

| 时刻 | 事件 | 结果 |
| --- | --- | --- |
| `2026-11-18 11:24:11.655272+00` | 更新前读取 `QZCONCURRENT` | 0 |
| `2026-11-18 11:24:11.933757+00` | 写事务开始，`txid=1064` | 未提交 |
| `2026-11-18 11:24:12.91385+00` | 事务内并发读 | 0 |
| `2026-11-18 11:24:15.2333+00` | 提交后读取 | 1 |

不对此前“并发更新后返回 0”的历史现象作根因结论：该轮会话原始证据不足，无法证明是分词、旧词还是其他原因；本轮只保留上述可复现的可见性事实。

### 3.5 5000 Chunk 压力

| 指标 | 结果 |
| --- | --- |
| 文档数 | 5000 |
| BM25 索引 | 408 KB |
| 表总大小 | 1088 KB |
| 过滤查询 | 2.365 ms（Top10，`domain='a'`） |
| 未过滤查询 | 0.527 ms（Top10） |
| 容器内存 | 空闲约 22.1 MiB（重启后 5000 Chunk 数据仍保留；活动峰值未单独采样） |

该数据仅验证基础规模和过滤 TopK/延迟，不参与真实召回质量结论。

## 4. 中文质量对照（临时评测集，非 V2 冻结语料）

- 语料：16 篇/39 Chunk；6 篇正式文档，10 篇明确标注的合成文档（中文、英文、中英混合、干扰）。
- 问题：24 道，其中 20 道有答案、4 道无答案。
- 指标：文档级 Recall@10 / MRR@10；未把零分文档计为命中。
- nDCG 未纳入：当前只有文档级期望集合，同一文档多 Chunk 会重复计数，算出的 nDCG@10 大于 1，指标实现未通过自检；需 Chunk 级 0–3 标注后重算。

| 引擎 | 可回答问题 | Recall@10 | MRR@10 |
| --- | ---: | ---: | ---: |
| ParadeDB Jieba 0.26.6（隔离质量对照） | 20 | 0.8792 | 0.9167 |
| pg_textsearch zhparser 2.4 | 20 | 0.8625 | 0.9167 |

结论：在该临时语料上两者接近，zhparser 的 Recall 低约 1.7 个百分点，MRR 相同；不能据此宣称全面优于 Jieba，也不能替代 V2 固定语料的质量门禁。ParadeDB 仅用于隔离对照，不作为正式部署候选。

## 5. 正式镜像、扩展安装与启用状态

必须区分三个不同状态，不能合并成“未进入正式镜像”：

| 状态 | 事实 | 证据 |
| --- | --- | --- |
| 正式镜像包含 `pg_search` 文件 | 是。镜像内存在 `/usr/lib/postgresql/17/lib/pg_search.so`（282,135,408 bytes）和 `pg_search.control` | `docs/v2-01-bm25-switch-evidence-20261118/formal-facts.txt` |
| 正式数据库安装扩展 | 否。`pg_available_extensions` 显示 `pg_search 0.26.6` 的 `installed_version` 为空；已安装扩展只有 `plpgsql`、`vector 0.8.7` | 同上（只读查询） |
| 正式数据库启用扩展 | 否。`shared_preload_libraries` 为空，`pg_search` 未预加载、未参与查询 | 同上 |

正式运行事实（只读核验，未重启、未改卷）：

- 容器 `agent-engine-demo-db-postgres-1`，状态 `running`，启动时间 `2026-11-17T14:59:05.899044319Z`。
- 镜像 ID/RepoDigest `sha256:bfe9a33d715a56d441d60a34e48c68b93fb49ea83d0992fbc2c2819e26846af4`；标签 `pg1712-upgrade:final-6595e98667c4`。
- 数据卷 `pg1712-final-data-6595e98667c4` → `/var/lib/postgresql/data`；HBA bind 为只读挂载。
- 当前可证明“镜像含库、数据库未安装/未启用”；无法从现有材料证明该 `.so` 是何时、由哪次构建加入的，不能补写历史。正式库未因本轮证据采集重启或修改。

ParadeDB 处理结论：正式运行路径未使用 `pg_search`；历史 `scripts/verify_v2_01_*`、旧 QA/兼容报告保留为审计证据，不删除、不改写；本机旧 `pg_search` deb/隔离对照容器仅用于质量比较，不作为正式部署依赖。此前报告“不进入正式镜像”的表述已纠正为上面的三态事实。

## 6. 文件变更

| 文件 | 变更 |
| --- | --- |
| `app/knowledge/models.py` | `SparseIndexProfile`：`result_identity_field=chunk_id`、`indexed_fields=(search_text,)`、扩展/版本/分词/词典/分数方向；移除 `search_mode` |
| `docs/v2-01-knowledge-rag-enhancement-detailed-design.md` | §3 选型与门禁、§4 调用链、§6 索引 Profile/查询契约、§7 PG17.12 验收、§8/§10/§11 引擎引用 |
| `docs/STATE.md` | 记录本轮 BM25 切换修复状态与边界 |
| `docs/v2-01-bm25-switch-report.md` | 本报告 |
| `docs/v2-01-bm25-switch-evidence-20261118/` | 重建构建日志、环境、产物 SHA256、候选镜像、固定 SQL 与原始输出 |
| `docs/question/v2-01-bm25-switch-qa-fix-report.md` | Codex QA 问题逐项修复映射 |

未修改业务数据、迁移、`.env`、V1 代码或正式数据库；未提交 Git；未进入 1.1.2。

## 7. 风险与后续注意事项

1. `dict.utf8.xdb`/`rules.utf8.ini` 未安装时 zhparser 可能只发 NOTICE 并产生空查询；部署检查必须包含词典存在性和摘要。
2. `<@>` 分数为负且升序，上层只能使用排名做 RRF；若需要展示分数，必须显式取负并标注语义。
3. 过滤查询可能使用 B-tree 预过滤+独立评分，规模化延迟和内存需在真实语料继续观测；不能以 5000 Chunk 结果代替生产容量结论。
4. 中文质量对照是临时语料；V2 固定语料、Chunk 级标注、Dense/RRF/BGE 及完整 RAG 质量门禁仍属后续 Task。
5. 需要独立 QA 的正式阶段门禁未被本轮替代；本轮 QA 为隔离环境复测。

## 8. QA 结论

**QA 状态**：`ACCEPTED`（BM25 技术切换范围）。

- 功能：加载、中文索引、事务回滚、增量、重启、过滤 TopK、并发可见性通过。
- 安全构建：17.12 headers 重建，无 pgrx/pg_search 未修复依赖，来源与产物 SHA256 已记录。
- 检索质量：仅完成 BM25 两引擎临时对照，未冒充 V2 完整 RAG 质量通过。
- 性能：5000 Chunk 基础压力通过；生产规模仍需后续门禁。
- 程序性限制：本轮 QA 由主 Agent 在隔离环境执行，未冒充外部独立 QA；Codex 首轮判定 `REQUIRES_FIX`，第二轮修复后独立复验通过。修复映射见[修复报告](question/v2-01-bm25-switch-qa-fix-report.md)。

**建议**：正式将 V2 BM25 主方案切换为 pg_textsearch 1.5.1 + zhparser 2.4 + SCWS 1.2.3；保留 ParadeDB Jieba 仅作质量对照，不静默回退。用户已接受技术切换。1.1.2 等待另行启动。
