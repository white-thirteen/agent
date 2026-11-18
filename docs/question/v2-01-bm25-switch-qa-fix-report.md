# V2 01 BM25 切换第二轮 QA 定向修复报告

**状态**：`REQUIRES_FIX`（第二轮修复完成，待 Codex 独立复验；不自行宣布 ACCEPTED）  
**日期**：2026-11-18  
**范围**：仅修复 Codex 第二轮指出的构建证据链、过滤 TopK、DELETE 一致性、并发结论及证据关联；已通过的契约、ParadeDB 三态事实、V1 边界不重复修改。

## 1. 第二轮修复映射

| Codex 问题 | 修复 | 原始证据 |
| --- | --- | --- |
| 候选镜像使用 pgvector `+1`，与正式 `+2` 不一致 | 用 `postgresql-17-pgvector 0.8.7-1.pgdg12+2` 重建候选镜像 | `candidate-vector2-package.txt`、`candidate2-image.txt` |
| 未在候选运行容器内核对实际加载产物 | 在候选容器内对 7 个实际文件执行 `sha256sum -c`，全部 `OK` | `candidate2-hashcheck-clean.out` |
| 过滤 TopK 未用同一数据/条件/非零分数/确定性排序对比 | 固定 7 篇数据，同一过滤条件、`score < 0`、`ORDER BY score,id`、K=5；顺序扫描与 BM25 索引扫描逐行一致 | `runtime/filter-seq.out`、`filter-idx.out`、`filter-compare-clean.out` |
| 未验证 DELETE 后旧关键词不再命中 | 增加事务回滚、提交删除、全表旧关键词断言 | `runtime/v201pt-delete.sql`、`delete.out` |
| 并发结论过度归因历史异常 | 收窄为“固定夹具下未提交不可见、提交后可见”，不再声称历史根因 | `runtime/candidate2-conc-*.out` |
| 报告与证据未逐项关联 | 本报告按问题列原始文件；报告 §2～§3 同步 | 本文件及 `docs/v2-01-bm25-switch-evidence-20261118/` |

## 2. 构建证据链（第二轮）

- 正式基线包：`postgresql-17-pgvector 0.8.7-1.pgdg12+2`（与正式库一致）。
- 候选镜像：`v201pt-candidate:1.5.1-vector2`，`Id/RepoDigest=sha256:748b51b8d45a51bc517424a9cd78aab4c8d268fe2155cca018b66f84c361ce85`。
- 候选容器内实际检查：

```text
PostgreSQL 17.12 (Debian 17.12-1.pgdg12+1)
postgresql-17-pgvector 0.8.7-1.pgdg12+2
pg_textsearch|1.5.1
zhparser|2.4
vector|0.8.7
shared_preload_libraries=pg_textsearch
```

`sha256sum -c` 的 7 项全部 `OK`：`pg_textsearch.so`、`zhparser.so`、`libscws.so.1.1.0`、`dict.utf8.xdb`、`rules.utf8.ini`、`pg_textsearch.control`、`zhparser.control`。原始输出见 `candidate2-hashcheck-clean.out`；构建环境/源码/产物见 `build-env.txt`、`build.log`、`artifacts.sha256`。未出现哈希不一致。

## 3. 过滤 TopK（第二轮）

固定数据 7 篇（`runtime/v201pt-evidence-setup.sql`）；同一过滤 `domain='after_sales_help' AND doc_version=1`；同一非零条件 `content <@> to_bm25query('退款','evidence_bm25') < 0`；确定性排序 `score ASC, id ASC`；K=5。

| 路径 | 计划 | 结果 |
| --- | --- | --- |
| 顺序扫描 | `Seq Scan` + Sort + WindowAgg | 2 行：`doc-refund`、`doc-safety` |
| BM25 索引扫描 | `Index Scan using evidence_bm25` + Incremental Sort + WindowAgg | 2 行：`doc-refund`、`doc-safety` |

两侧 `(rank,id,score)` 完全一致；`filter-compare-clean.out` 为空 diff。有效候选只有 2 条，返回 2 条而非用零分文档补足 K=5。原始 SQL 与输出：`runtime/v201pt-filter-seq.sql`、`v201pt-filter-idx.sql`、`filter-seq.out`、`filter-idx.out`。

## 4. DELETE 后索引一致性

`runtime/v201pt-delete.sql` / `delete.out`：

| 阶段 | 结果 |
| --- | --- |
| 插入 `del-1` 后 | `before_delete=1`，`qzdelete_hits=1` |
| 事务内 DELETE | `inside_tx=0` |
| ROLLBACK 后 | `after_rollback=1`，`qzdelete_hits=1` |
| 提交 DELETE 后 | `after_delete=0`，`qzdelete_hits=0` |
| 全表旧关键词 | `all_qzdelete_hits=0` |

删除提交后旧关键词不再命中；回滚保留原文档与命中。

## 5. 并发结论（收窄）

固定夹具、固定词 `QZCONCURRENT`、同一 `evidence.docs`；原始输出 `runtime/candidate2-conc-*.out`（UTC）：

| 时刻 | 事件 | 结果 |
| --- | --- | --- |
| `2026-11-18 11:24:11.655272+00` | 更新前读取 | 0 |
| `2026-11-18 11:24:11.933757+00` | 写事务开始，`txid=1064` | 未提交 |
| `2026-11-18 11:24:12.91385+00` | 事务内并发读 | 0 |
| `2026-11-18 11:24:15.2333+00` | 提交后读取 | 1 |

本轮只证明：**固定夹具下，未提交变更不可见，提交后可见**。不对此前“并发更新后返回 0”的历史现象作分词、旧词或其他根因结论；该轮缺少可复核的原始会话证据。

## 6. 已保留的通过项与未覆盖范围

已保留并通过、本轮未重复修改：

- `SparseIndexProfile` 的 `result_identity_field=chunk_id`、`indexed_fields=(search_text,)` 及设计 §6.2.1/§7 PG17.12 契约。
- 正式镜像三态事实：含 `pg_search.so`、未安装扩展、未预加载/启用。
- 中文索引、事务回滚、增量更新、重启恢复、5000 Chunk 基础压力。

未覆盖：

- Dense/RRF/BGE 与 V2 冻结语料质量。
- 生产规模延迟、compaction 长期开销。
- 正式库重启/配置变更（本轮只读核验）。
- 外部独立结论；等待 Codex 复验。

## 7. 证据路径

`docs/v2-01-bm25-switch-evidence-20261118/`

- `build.log`、`build-env.txt`、`build-commands.txt`、`artifacts.sha256`
- `candidate2-image.txt`、`candidate-vector2-package.txt`、`candidate2-hashcheck-clean.out`
- `runtime/v201pt-filter-seq.sql`、`runtime/v201pt-filter-idx.sql`、`runtime/filter-*.out`
- `runtime/v201pt-delete.sql`、`runtime/delete.out`
- `runtime/candidate2-conc-*.out`
- `formal-facts.txt`、`base-image.txt`

**结论**：第二轮问题已按证据修复；状态仍为 `REQUIRES_FIX`，等待 Codex 独立复验，不自行宣布 `ACCEPTED`。
