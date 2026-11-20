# Task 1.3.2 正式验收

**Task 1.3.2 = ACCEPTED（2026-11-19）。** 用户批准采用 RRF Top3 局部 BGE 重排并授权 Git 归档。独立 QA 为 PASS，`V201-132-QA-001` 已关闭。此前全量 BGE 的质量失败与修订后的验收各有独立记录。

## 实现契约

沿用当前 RRF 候选池、BGE 模型及对所有候选的预检和评分。只允许 RRF 前三按原始 logit 局部换位，同分按完整来源身份排序。第四名起保留 RRF 顺序。原输入超限失败、资源预算、检索超时、完整 Chunk 打包、来源复核、显式 Dense-only 回退均保留。策略身份为 `rrf-top3-bge-local-v1`，供既有回放校验使用。

| 归档内容 | 入口 |
| --- | --- |
| 代码、策略身份及定向测试 | [实现说明](v2-01-task132-top3-implementation.md)、[Retriever](../../../app/knowledge/retriever.py)、[Profile](../../../app/knowledge/models.py)、[定向测试](../../../tests/test_task132_local_rerank.py) |
| 最终验收与独立 QA | [主复核及独立 QA](v2-01-task132-top3-review.md)、[复验脚本](../../../scripts/compare_v2_01_local_rerank.py) |
| 冻结集五轮和逐题结果 | [冻结夹具](evidence/v2-01-task132-top3-evidence/fixture.json)、[逐轮排名与逐题指标](evidence/v2-01-task132-top3-evidence/fresh-metrics.json)、[真实检索结果](evidence/v2-01-task132-top3-evidence/qwen.json)、[真实 BGE 分数](evidence/v2-01-task132-top3-evidence/bge.json) |
| 独立问题与真实应用 | [问题及标注](evidence/v2-01-task132-top3-evidence/novel-questions.json)、[独立题结果](evidence/v2-01-task132-top3-evidence/novel.json)、[业务回执](evidence/v2-01-task132-top3-evidence/business.json)、[38 项定向回归](evidence/v2-01-task132-top3-evidence/regression.log) |
| 历史全量对照、回放和 V1 回归 | [首次实施](v2-01-task132-implementation-report.md)、[诊断](v2-01-task132-bge-ranking-diagnosis.md)、[旧证据回放](evidence/v2-01-task132-top3-evidence/offline-metrics.json)、[238 项完整 V1 回归回执](evidence/v2-01-task132-regression-evidence/task132-full-regression-retest.json) |

冻结集 24 题各五轮。纯 RRF、全量 BGE、局部 BGE 的 Recall@3 为 1.0000、0.9750、1.0000，MRR@3 为 0.9667、0.9750、1.0000，nDCG@3 为 0.9606、0.9233、0.9779。24 次实际 Hybrid Retriever 排序与第一轮局部结果一致。业务 6/6，含四题无答案拒答、冲突拒答和有效来源。

归档按 SHA256 核对[局部复验证据](evidence/v2-01-task132-top3-evidence/sha256-manifest.json)、[完整回归证据](evidence/v2-01-task132-regression-evidence/sha256-manifest.json)及新旧评分链。仓库按路径保留这些文件的原始换行和语料的冻结字节。

## 风险与交付范围

- 独立题仅四道有答案，且使用相同语料。局部策略的 MRR@3 与全量 BGE 持平，Recall@3 和 nDCG@3 低于全量 BGE。新问题和新语料的泛化继续待验证。
- RRF 前三之外的相关候选无法由局部策略补入前三。冻结集仍有五道题的 nDCG@3 低于纯 RRF。
- 并发 BM25 分数与排序稳定性、跨索引重建漂移仍待验证。顺序五轮和并发提交可见性证据的范围有限。

用户另行授权随交付纳入可运行所需的 Sparse 迁移与构建、Dense/Sparse 同快照召回、RRF、BGE、Graph 与工具接线。Task 1.1.1 保持 ACCEPTED，Task 1.1.2、1.2.1、1.2.2、1.3.1 保持原技术验收状态。本次正式验收范围为 Task 1.3.2。Hybrid 仍显式启用，部署需要相应数据库迁移、Sparse 激活及本地模型。归档本身未部署或操作数据库。
