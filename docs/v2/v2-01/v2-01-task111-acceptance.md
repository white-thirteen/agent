# V2 01 · Task 1.1.1 技术适配与契约冻结验收

**Task 1.1.1 = ACCEPTED**。2026-11-18，Codex 完成独立复验，用户正式接受并授权 Git 归档。V2 01 阶段仍在进行，1.1.2 等待另行启动。

固定基线为 **PostgreSQL 17.12 + pgvector 0.8.7 + pg_textsearch 1.5.1 + zhparser 2.4 + SCWS 1.2.3**。Debian PostgreSQL 服务及头文件包均为 `17.12-1.pgdg12+1`，pgvector 包为 `0.8.7-1.pgdg12+2`。候选镜像 ID 为 `sha256:748b51b8d45a51bc517424a9cd78aab4c8d268fe2155cca018b66f84c361ce85`。索引固定使用 `public.chinese` 和 `search_text`，`chunk_id` 是结果身份。正式镜像中仍有旧 `pg_search` 文件，已核查的正式数据库基线未启用该扩展。

| 独立复验项目 | 结论与依据 |
| --- | --- |
| 构建与技术切换 | PASS。比对构建、清单与运行输出，7 项产物 SHA256 全部一致，候选与正式基线的 pgvector 包一致。镜像 ID 与运行哈希分别留存，本次复验依据留存输出。见[切换报告](v2-01-bm25-switch-report.md)、[两轮 QA 整改](qa/v2-01-bm25-switch-qa-fix-report.md)及[容器哈希记录](evidence/v2-01-bm25-switch-evidence-20261118/candidate2-hashcheck.out)。 |
| BM25 行为 | PASS。两种扫描对相同非零条件返回相同排名、ID、分数。删除回滚恢复命中，提交后旧词不再命中。并发复测为 0 → 0 → 1，结论限于该夹具。见[顺序扫描](evidence/v2-01-bm25-switch-evidence-20261118/runtime/filter-seq.out)、[索引扫描](evidence/v2-01-bm25-switch-evidence-20261118/runtime/filter-idx.out)及[删除回执](evidence/v2-01-bm25-switch-evidence-20261118/runtime/delete.out)。 |
| 参数化与混合文本 | PASS。双参数 PREPARE/EXECUTE、中文、英文及混合查询逐例通过。非法索引名称触发错误，测试表仍有 3 行。见[参数化输出](evidence/v2-01-task111-evidence-20261118/task111-param.out)及[断言](evidence/v2-01-task111-evidence-20261118/task111-assert.out)。 |
| 同快照及来源版本 | PASS。B 提交版本替换后，A 的 REPEATABLE READ 事务两路仍返回 v1，新会话两路返回 v2，旧来源已标记为非当前。见[会话 A](evidence/v2-01-task111-evidence-20261118/snapshot-a.out)、[会话 B](evidence/v2-01-task111-evidence-20261118/snapshot-b.out)及[会话 C](evidence/v2-01-task111-evidence-20261118/snapshot-c.out)。 |
| 维护及数据库层回退 | PASS。REINDEX 超时后索引仍有效，重试成功。独立重算 5000 行 ID 和正文的 MD5，与五个阶段一致。变更索引名期间，独立 Dense 查询仍返回 5 行，恢复索引名后 BM25 查询恢复。见[维护回执](evidence/v2-01-task111-evidence-20261118/task111-maint.out)。 |

[模型契约](../../../app/knowledge/models.py)、[定向测试](../../../tests/test_knowledge.py)和[批准设计](v2-01-knowledge-rag-enhancement-detailed-design.md)随交付归档。定向测试此前执行为 7 passed。本轮归档复核证据字节和提交范围，无新增数据库、应用或模型测试。原始 SQL 和输出分别存于[技术切换证据目录](evidence/v2-01-bm25-switch-evidence-20261118/)和[补证目录](evidence/v2-01-task111-evidence-20261118/)，各目录附 SHA256 清单。

[原候选 QA](qa/v2-01-01-compatibility-qa-report.md)及[旧路线续作 QA](qa/v2-01-01-compatibility-resume-qa-report.md)按历史保留。V201-111-QA-001 和 V201-111-QA-002 对应的 ParadeDB 方案已退出当前基线，既有失败及安全证据缺口依然适用于旧组合。

**验收边界**：同一快照中的 BM25 分数实测发生变化，并发分数及排序稳定性仍未验证。应用级 Dense-only 回退、RRF、BGE 和完整质量评测仍待后续 Task。当前迁移与回退契约沿用[实施约束](v2-01-01-compatibility-report.md#后续迁移与回滚约束未实施)：追加 Sparse 派生字段及状态，保持权威文档、原向量和来源身份，完整性检查通过后才可激活。回退先恢复原 Dense 装配，再按维护计划处理 Sparse 派生资源。归档只记录数据库层探针与契约。
