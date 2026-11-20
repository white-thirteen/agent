# V2 01 · Task 1.1.2 主复核

**Task 1.1.2 = ACCEPTED（2026-11-19）。** 用户授权正式验收及归档，详见[阶段验收](v2-01-stage-acceptance.md#task-112-sparse-准备事务发布与回填)。以下为当时的技术验收记录。

**VERIFIED，等待人工验收及归档批准。** 独立 QA 为 **PASS**，无待修复编号。本轮完成 Sparse 索引准备与回填，1.2.1 尚未启动。

[实现报告](v2-01-task112-implementation-report.md)记录扩展无关的迁移 007、历史派生回填、事务发布、索引激活及 Profile/水位、维护命令和回退说明。[独立 QA](qa/v2-01-task112-qa-report.md)在真实库复测 006 到 007、旧向量与来源保持、中文查询、版本替换及删除、并发锁、索引异常和重试；独立故障注入验证回填中途失败时整事务回滚。故障探针原文见[留存源](evidence/v2-01-task112-evidence/qa-backfill-failure-probe.py.txt)。

- 独立实例采用 1.1.1 锁定镜像，实际 PostgreSQL 17.12、pgvector 包 +2；从运行容器观察到的 7 个产物 SHA256 与 1.1.1 清单一致。容器持独立卷且仅向 VM 回环地址发布端口，Windows 经 SSH 转发访问。每个验证库均带本轮专属标记。
- 另在只安装 pgvector 的两个 V1 隔离库应用 001–007，初始化 Checkpoint 和 Store。真实定向回归 12 passed、0 failed、0 skipped；覆盖迁移、Dense/来源、Checkpoint、Store、订单和退款恢复。实际应用生命周期的健康请求确认数据库、Checkpoint 和 Store 就绪，退出后两个连接池关闭。Embedding 在此健康检查中禁用。
- 在单独 Sparse 隔离库运行真实维护入口 backfill → activate → check → activate → check。退出码均为 0，重复激活保留水位 2。空库 CLI 探针验证入口与状态；存量数据行为由真实库专项及独立 QA 覆盖。
- Ruff 检查与格式检查通过；本 Task 采用定向验证。真实 Qwen、正式 Hybrid 和完整阶段质量验收留待各自后续任务。

[主验证回执](evidence/v2-01-task112-evidence/main-validation.json)记录测试文件、结果、源文件 SHA256 与资源身份。正式库 SQL 未访问，容器 ID、启动时间及健康状态前后相同。仅清理本轮自建容器及卷，标签复查为空。原 .env、V1 部署和 001–006 的八项哈希均持平。Git HEAD 仍为 2f5d5a2，暂无本 Task 的 Git 提交或推送。
