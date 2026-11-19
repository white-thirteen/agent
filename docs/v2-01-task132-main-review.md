# V2 01 · Task 1.3.2 主复核

下文为首次全量 BGE 验收记录。用户已正式接受经后续复验通过的局部策略，见[Task 1.3.2 正式验收](v2-01-task132-acceptance.md)。

**功能与 V1 兼容性通过；检索质量收益 FAIL。** V201-132-QA-001 保持 OPEN，Task 1.3.2 和 V2 01 阶段均未取得验收通过。按冻结设计 §8.6，等待用户裁决重排方案，保留原语料、标注、排名与失败记录。

- [评测报告](v2-01-task132-implementation-report.md)记录 18 个冻结 Chunk 和 24 个问题，真实 Qwen/PG 与 BGE 各五轮 120/120 成功。独立复算 A/C Recall@10 均为 1.0000，C→D MRR@3 为 0.9667→0.9750，nDCG@3 为 0.9606→0.9233。Q01 的账户证据 1→2，Q20 的退款申请证据 2→4，Q20 的 Recall@3 由 1.000 降至 0.500。见[首次独立质量 QA](question/v2-01-task132-quality-qa-report.md)。
- [QA-002 独立复测](question/v2-01-task132-quality-retest-report.md)通过，主复核关闭。A/B/C 分别五轮各 120 次端到端请求，20 个有答案问题各 100 个样本，实测 P50/P95 分别 428.6/520.5、341.6/511.7、652.2/788.5 ms；D 实测一轮，20 个有答案样本为 2253/2456 ms，采样轮数不同。B/C 分别有 40/30 次跨重建排名变化，包含 C 的 Q10 相关证据 1→2。该复测只报告漂移和延迟，原冻结质量统计未被覆盖，漂移原因未验证。
- [固定语料业务回执](v2-01-task132-regression-evidence/business-frozen.json)：真实应用、配置的对话服务、Qwen、BGE 与隔离 PostgreSQL，18 个 Chunk 起始，六项通过。正常问答引用退款安全来源，Q21–Q24 均为 evidence_insufficient，冲突场景临时另加两篇冲突资料并因 evidence_conflicting 拒答；拒答案例无答案及引用。首次六 Chunk [业务回执](v2-01-task132-regression-evidence/business-first.json)单独保留，冲突场景为 failed，未发布答案或引用。来源过期及回放见 [1.3.1 QA](question/v2-01-task131-qa-report.md)。
- [V1 完整门禁首次记录](v2-01-task132-regression-evidence/v1-full-first-run.json)：235 passed、1 failed。复核确认差异对象仅是 Sparse 发布水位；修复 Demo 清理精确记录己方发布与删除、可重试意图及严格快照比较。经[独立 QA 和复测](question/v2-01-task132-v1-fix-retest-report.md)，关闭 V201-132-V1-QA-001/002。[完整真实复测](v2-01-task132-regression-evidence/task132-full-regression-retest.json) 238 passed、0 failed、0 skipped，启动通过，14 个保护对象仅知识索引状态摘要变化，按源码事先核算 +11，实际水位 16→27，比较器逐值校验其余字段、结构及业务行。此次 V1 完整门禁含真实 Qwen。
- 固定业务夹具删除后，隔离环境保留的原六个 Chunk 内容与身份核对一致，见[最终清理回执](v2-01-task132-regression-evidence/final-fixture-cleanup.json)。精确清理本轮专属容器及数据卷，标签复查为空；正式容器 ID、启动时间及健康状态前后相同，无正式数据库 SQL 连接。没有 Git 提交或推送，也未启动 V2 02 或 03。

[回归与业务证据 SHA256](v2-01-task132-regression-evidence/sha256-manifest.json)。
