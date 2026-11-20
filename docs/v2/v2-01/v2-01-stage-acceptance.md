# V2 01 KnowledgeAgent RAG 增强阶段验收

**V2 01 = ACCEPTED（2026-11-19）。** 用户授权对四个技术验收已通过的前置 Task 完成正式验收及 Git 归档。复核确认六个 Task 的交付与独立 QA 均通过，当前基线没有未关闭的 P0/P1 或阶段技术阻塞。本轮依据已有验证结果收尾。

| Task | 最终状态 | Git 交付 |
| --- | --- | --- |
| [1.1.1 BM25 兼容性](v2-01-task111-acceptance.md) | ACCEPTED | `d60e5ab`、`2f5d5a2` |
| [1.1.2 Sparse 准备、事务发布与回填](#task-112-sparse-准备事务发布与回填) | ACCEPTED | 实现 `73e4a07`，专项证据随本次收尾归档 |
| [1.2.1 Dense/BM25 与 RRF](#task-121-densebm25-与-rrf) | ACCEPTED | 实现 `73e4a07`，专项证据随本次收尾归档 |
| [1.2.2 BGE 与推理资源](#task-122-bge-与推理资源) | ACCEPTED | 实现 `73e4a07`，专项证据随本次收尾归档 |
| [1.3.1 知识工具与八节点接线](#task-131-知识工具与八节点接线) | ACCEPTED | 实现及初次独立 QA `73e4a07`，真实烟测随本次收尾归档 |
| [1.3.2 质量、业务与 V1 回归](v2-01-task132-acceptance.md) | ACCEPTED | `73e4a07`、`d365fca` |

## Task 1.1.2 Sparse 准备、事务发布与回填

**Task 1.1.2 = ACCEPTED。** 独立 QA 在隔离 PostgreSQL 17.12 上验证旧数据迁移、原向量及来源保留、未完成回填拒绝激活、重复回填和激活、事务发布与更新/删除可见性。独立异常探针验证回填中断整事务回滚及恢复重试。仅启用 pgvector 的 V1 定向回归 12 项通过，维护 CLI 五步退出码均为 0，重复激活保留水位 2。

复核核对测试源、回执与探针摘要。1.1.2 回执是当时的实现快照，Repository 文件随后新增 Hybrid 召回和就绪检查，历史文件摘要保留，最终组合另有真实回归记录。[实现](v2-01-task112-implementation-report.md) · [独立 QA](qa/v2-01-task112-qa-report.md) · [主复核](v2-01-task112-main-review.md) · [原始回执](evidence/v2-01-task112-evidence/main-validation.json) · [回填失败探针](evidence/v2-01-task112-evidence/qa-backfill-failure-probe.py.txt) · [维护 CLI 探针](evidence/v2-01-task112-evidence/maintenance-cli-probe.py.txt)

## Task 1.2.1 Dense/BM25 与 RRF

**Task 1.2.1 = ACCEPTED。** 独立 QA 在隔离真实库检查同快照、权限和领域过滤、版本、候选身份去重、索引不可用及 RRF 排名。初次发现 `V201-121-QA-001`，修复后独立复测 2 项通过，覆盖两条受控 2.7 秒 SQL 触发累计 5 秒限制、连接池等待、错误映射与恢复。主复核已关闭该问题，另有 V1 定向回归 23 项通过。

归档保留首次独立复现探针、复测报告和已提交的真实数据库断言。初次探针针对修复前行为。复测的留存凭据为独立 QA 记录与对应测试源码。[实现](v2-01-task121-implementation-report.md) · [初次 QA](qa/v2-01-task121-qa-report.md) · [独立复测](qa/v2-01-task121-retest-report.md) · [主复核](v2-01-task121-main-review.md) · [原始复现探针](evidence/v2-01-task121-evidence/qa-timeout-repro.py.txt) · [数据库测试](../../../tests/test_hybrid_task121_postgres.py)

## Task 1.2.2 BGE 与推理资源

**Task 1.2.2 = ACCEPTED。** 首次的真实模型证据缺口已补齐，独立复测通过。固定 CPU BGE 的中英文真实评分、输入超限拒绝、强制超时、在途忙碌和关闭后容量释放均有回执。216 个正常语料配对最长 95 Token，零超限。真实 Qwen/BGE 同时争用容量仍以受控线程证据为限。

[实现](v2-01-task122-implementation-report.md) · [首次 QA](qa/v2-01-task122-qa-report.md) · [独立复测](qa/v2-01-task122-retest-report.md) · [主复核](v2-01-task122-main-review.md) · [真实 BGE 回执](evidence/v2-01-task122-evidence/real-bge-receipt.json) · [配对明细](evidence/v2-01-task122-evidence/normal-corpus-pairs.json)

## Task 1.3.1 知识工具与八节点接线

**Task 1.3.1 = ACCEPTED。** 既有八节点及 Policy/Executor 边界保持，默认 Dense v1，显式 Hybrid v2。独立隔离 PostgreSQL 定向 23 项通过，验证版本、回放、来源和生命周期。主 Agent 的真实 Qwen、BGE、PostgreSQL 应用烟测记录两次真实检索、来源复核、健康就绪和资源关闭。完整真实对话业务由 1.3.2 回执覆盖。

[实现](v2-01-task131-implementation-report.md) · [独立 QA](qa/v2-01-task131-qa-report.md) · [主复核](v2-01-task131-main-review.md) · [真实应用回执](evidence/v2-01-task131-evidence/real-app-receipt.json) · [原始探针](evidence/v2-01-task131-evidence/real-app-probe.py.txt)

## 阶段门禁与剩余风险

- 固定基线为 PostgreSQL 17.12、pgvector 0.8.7、pg_textsearch 1.5.1、zhparser 2.4 和 SCWS 1.2.3。Dense 与 BM25 同快照召回，经 RRF 和 BGE 接入 KnowledgeAgent。正式采用 `rrf-top3-bge-local-v1`，完整候选照常预检和评分，仅前三内部换位，第四名起保留 RRF 顺序。显式 Dense-only 回退、检索预算、超时和来源校验均保留。[设计](v2-01-knowledge-rag-enhancement-detailed-design.md)
- 冻结集 24 题各五轮，Dense 和 RRF 的 Recall@10 均为 1.0000，局部 BGE 相对 RRF 的 MRR@3 为 0.9667→1.0000，nDCG@3 为 0.9606→0.9779。业务 6/6，包含拒答和来源校验。此前完整 V1 真实回归 238 项通过，局部策略完成后隔离库定向回归 38 项通过。[最终质量与业务复验](v2-01-task132-top3-review.md)
- 当前基线编号问题均有闭环。历史 P1 对应已退出当前基线的 ParadeDB 组合，保留既有失败及安全证据缺口。[兼容性验收](v2-01-task111-acceptance.md) · [V1 回归复核](v2-01-task132-main-review.md)
- 新问题及新语料泛化、RRF 前三之外的证据无法补入、并发 BM25 分数及排序稳定性和跨索引重建漂移仍待验证。独立题上局部策略的 Recall@3、nDCG@3 低于全量 BGE。当前性能证据覆盖隔离环境和已测规模。正式 Hybrid 部署和生产规模验证留待单独安排。

四个专项证据目录均附 SHA256 清单。[1.1.2](evidence/v2-01-task112-evidence/sha256-manifest.json) · [1.2.1](evidence/v2-01-task121-evidence/sha256-manifest.json) · [1.2.2](evidence/v2-01-task122-evidence/sha256-manifest.json) · [1.3.1](evidence/v2-01-task131-evidence/sha256-manifest.json)

本轮新增正式验收、证据、版本校验和导航记录。历史失败报告、冻结语料和质量门槛保留原样。本轮无业务实现、运行配置、数据库或部署改动，未重跑真实环境测试，V2 02/03 维持设计状态。
