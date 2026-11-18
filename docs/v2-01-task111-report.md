# Task 1.1.1 剩余验收补证报告

**状态**：Task 1.1.1 = `ACCEPTED`。见[独立复验和归档](v2-01-task111-acceptance.md)。
**日期**：2026-11-18
**范围**：参数化/混合文本、同快照与版本一致性、维护失败与 Dense-only 最小回退契约。未执行 1.1.2 及后续 Task。

## 1. 隔离环境

- 候选镜像：`v201pt-candidate:1.5.1-vector2`，`sha256:748b51b8d45a51bc517424a9cd78aab4c8d268fe2155cca018b66f84c361ce85`。
- PostgreSQL 17.12，pg_textsearch 1.5.1、zhparser 2.4、SCWS 1.2.3、pgvector 0.8.7（包 `0.8.7-1.pgdg12+2`）。
- 独立容器、Unix socket `/tmp`、端口 55440、`pg_textsearch.memory_limit=128MB`；未连接正式库。
- 固定 SQL 与原始输出：[v2-01-task111-evidence-20261118](v2-01-task111-evidence-20261118/)。

## 2. 参数化与混合文本

SQL：[v201pt-task111-param.sql](v2-01-task111-evidence-20261118/v201pt-task111-param.sql)、[v201pt-task111-assert.sql](v2-01-task111-evidence-20261118/v201pt-task111-assert.sql)。原始输出：[task111-param.out](v2-01-task111-evidence-20261118/task111-param.out)、[task111-assert.out](v2-01-task111-evidence-20261118/task111-assert.out)。

- 使用 `PREPARE bm25_case(text,text)`，查询文本与索引名均为绑定参数；`EXPLAIN EXECUTE` 使用 `Index Scan using probe111_docs_bm25` + Incremental Sort。
- 逐例断言：

| 用例 | 查询 | 期望首条 | 结果 |
| --- | --- | --- | --- |
| 中文 | `退款 银行卡` | `zh-refund` | PASS，score `-1.6270842552185059` |
| 英文标识符 | `stream disconnects accepted task` | `en-stream` | PASS，score `-4.021807610988617` |
| 中英混合 | `退款 approval endpoint` | `mixed-approval` | PASS，score `-2.9887390732765198` |

- 可信索引标识符：合法 `to_regclass('probe111.probe111_docs_bm25')` 返回 `probe111_docs_bm25`；注入字符串 `probe111_docs_bm25; DROP TABLE probe111.docs` 返回 NULL，`to_bm25query` 报 `invalid name syntax`，执行后 `probe111.docs` 仍为 3 行。索引名不作为自由拼接 SQL，非法标识符被拒绝。
- 原始结果中的断言函数返回 `chinese|PASS`、`english|PASS`、`mixed|PASS`。

## 3. 同快照与版本一致性

SQL：[snapshot-a.sql](v2-01-task111-evidence-20261118/v201pt-task111-snapshot-a.sql)、[snapshot-b.sql](v2-01-task111-evidence-20261118/v201pt-task111-snapshot-b.sql)、[snapshot-c.sql](v2-01-task111-evidence-20261118/v201pt-task111-snapshot-c.sql)。原始输出：[snapshot-a.out](v2-01-task111-evidence-20261118/snapshot-a.out)、[snapshot-b.out](v2-01-task111-evidence-20261118/snapshot-b.out)、[snapshot-c.out](v2-01-task111-evidence-20261118/snapshot-c.out)。

会话 A 使用 `BEGIN ISOLATION LEVEL REPEATABLE READ`；B 在 A 读取后提交版本 2。时序（UTC）：

| 时刻 | 会话/事件 | 结果 |
| --- | --- | --- |
| `11:40:54.188498` | A 首次快照 | current=2，v1-refund current=1 |
| `11:40:54.210892` | A Dense | `v1-refund`，distance 0 |
| `11:40:54.224795` | A Sparse | `v1-refund`，score `-0.668293...` |
| `11:40:55.345512` | B 提交 | `v1-refund` is_current=f，`v2-refund` is_current=t |
| `11:40:57.258819` | A 第二次快照查询 | 仍 current=2，v1-refund current=1 |
| `11:40:57.262128` | A 二次 Dense | 仍 `v1-refund` |
| `11:40:57.268974` | A 二次 Sparse | 仍 `v1-refund` |
| `11:40:57.57166` | C 新快照 | `v2-refund` current=t，`v1-refund` is_current=f |
| `11:40:57.577886` | C Dense | `v2-refund`，distance 0 |
| `11:40:57.587017` | C Sparse | `v2-refund`，score `-0.395165...` |

结论：在 A 的 `REPEATABLE READ` 快照内，Dense 与 Sparse 同时看到 v1；B 提交后 A 仍看到 v1，新会话 C 才看到 v2。`v1-refund` 在替换后 `is_current=false`，旧来源不再作为当前来源返回。`v1_current=1` 来自另一文档 `v1-stream`，不是 `v1-refund`。

## 4. 维护失败与回退

SQL/原始输出：[v201pt-task111-maint.sql](v2-01-task111-evidence-20261118/v201pt-task111-maint.sql)、[task111-maint.out](v2-01-task111-evidence-20261118/task111-maint.out)。固定 5000 行，baseline 行数 5000，校验和 `a168afc9315af6158916c054a432d6cd`。

| 阶段 | 行为 | 结果 |
| --- | --- | --- |
| 基线 | BM25 查询 / `EXPLAIN` | `Index Scan using probe111_maint_bm25`；行数/校验和不变 |
| 维护失败 | `statement_timeout=1ms; REINDEX INDEX ...` | 报 `canceling statement due to statement timeout` |
| 失败后 | 检查索引与数据 | `indisvalid=t`；5000 行、校验和不变；BM25 查询仍返回结果 |
| 重试 | 无超时 `REINDEX` | 成功，`indisvalid=t`；校验和不变 |
| Dense-only 回退 | 将 BM25 索引改名（禁用）后执行 Dense Top5 | 成功返回 5 行，校验和不变；未调用 BM25 |
| 恢复 | 索引改回原名 | BM25 查询恢复，行数/校验和不变 |

该探针只验证当前层级的最小回退契约：BM25 不可用时 Dense 查询可执行；未实现应用级开关、RRF 或正式 Dense 流程（属后续 Task）。

## 5. 未覆盖与边界

- 未执行 1.1.2、正式 Dense/RRF/BGE 流程或 KnowledgeAgent 集成。
- 未对正式数据库做任何修改/重启；正式容器保持原状态。
- 未做生产规模性能/长期 compaction；5000 行仅用于维护/回退探针。
- 未修改业务代码、设计、迁移或 V1 配置；未提交 Git。
- Codex 已完成独立复验，用户已确认验收。

## 6. 证据索引

`docs/v2-01-task111-evidence-20261118/`：

- `v201pt-task111-setup.sql`：固定 docs/hybrid/maint 数据与索引。
- `v201pt-task111-param.sql`、`task111-param.out`：参数化查询、计划、混合文本。
- `v201pt-task111-assert.sql`、`task111-assert.out`：逐例断言与非法索引标识符。
- `v201pt-task111-snapshot-*.sql`、`snapshot-*.out`：同快照/版本替换。
- `v201pt-task111-maint.sql`、`task111-maint.out`：REINDEX 失败恢复与 Dense-only 回退。
- `task111-environment.out`：版本、预加载与资源设置。
