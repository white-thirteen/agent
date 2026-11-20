# V2 01 · Task 1.3.1 主复核

**Task 1.3.1 = ACCEPTED（2026-11-19）。** 用户授权正式验收及归档，详见[阶段验收](v2-01-stage-acceptance.md#task-131-知识工具与八节点接线)。以下为当时的技术验收记录。

**VERIFIED。** [独立 QA](qa/v2-01-task131-qa-report.md)判定 PASS，无编号问题。[实现报告](v2-01-task131-implementation-report.md)记录默认 V1 Dense v1、显式 Hybrid v2、原八节点、期限约束与来源重验。

专用测试库真实 PostgreSQL 通过受治理 Graph，独立 QA 合计 23 passed / 0 skipped，Embedding、BGE 和对话模型受控。另以确切隔离数据库和真实 Qwen 导入六个文档，运行同一应用的真实 Qwen+BGE+PostgreSQL 烟测。Hybrid v2 已注册，数据库、知识、Checkpoint 与 Store 健康就绪。启动 25.218 秒，中英文检索分别 8.015 / 1.858 秒，预期来源出现且当前来源复核通过。应用正常退出且池已关闭。未调用外部对话接口，此回执只证明真实检索组装及来源复核。见[原始回执](evidence/v2-01-task131-evidence/real-app-receipt.json)。

初始真实库测试使用项目 Windows Selector 事件循环后通过；受控故障验证确认 BGE 初始化错误仅使知识能力不可用，退出资源关闭。知识回放证据限于节点级，最终业务/质量及 V1 回归归入 1.3.2。正式数据库仍未通过 SQL 访问，无 Git 提交或推送。
