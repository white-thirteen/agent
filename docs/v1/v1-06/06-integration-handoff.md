# 06 简洁 Handoff

## 最新验收（2026-11-17）

用户已授权06提交/推送及合入main，06正式ACCEPTED，以下技术证据和披露限制保持。随后仅V2 01获开发授权，按批准设计串行实施与独立QA；02/03不开发。Git结果见归档回执，下文等待批准属于历史语境。

2026-11-15。先读[STATE](../../STATE.md)、[最终交付报告](06-delivery-report.md)、[最终验收入口](final-acceptance.md)。01～05 ACCEPTED已归档；06六Task独立QA PASS/主复核完成，阶段VERIFIED，06-QA-001已关闭；最终新环境完整门禁228/0/0，632独立QA见[报告](qa/06-delivery-qa-report.md)。06正式ACCEPTED与Git归档仍须用户明确批准。

- 运行：Windows Python3.13.7、单worker；Qwen原本地目录/CPU/1024维，PG17.6/vector0.8.7、schema001～006/Saver/Store。原.env保持Embedding关闭；演示进程显式启用，单个Qwen实例。干净Python安装和本轮门禁的命令/结果见632报告。
- 首次环境：按[README](../../../README.md)和[数据库配方](database-reproduction.md)区分新目标初始化与原库保护；原Compose无vector，原VM容器可写层包不等于镜像已有扩展。不得擅自重建原容器/卷或升级PG。
- 演示：用户已手动导入Postman；[操作步骤](demo-walkthrough.md)含原关联提取、两次完整服务重启及精确清理。客户端脚本实际执行/变量回填/SSE界面未实测，保留人工路径；不再桌面操作。
- 数据：只用agent_demo_test/agent_test UUID自有场景，原五订单不改；唯一旧seed全门禁测试按批准窄例外原样执行并finally恢复实际原值。前后全public行集/列定义及全部迁移checksum保持，凭据和完整保护快照不入仓库。
- 隔离复现已完成[新镜像/空双库独立核对及清理](evidence/06-database-reproduction-cleanup-evidence-20261115.json)，临时容器/卷/镜像/凭据均已删除，原容器和卷保持。新Python环境与本机验证源留存供QA，未覆盖原.venv。
- 边界：unknown人工核对、可信安全窗口恢复、Store历史即时关闭观测波动、六项暂缓差异及既有凭据/格式决定保留；详见验收入口。不承诺全局Exactly Once或生产认证。

技术验收完成后停止等待用户正式验收，未提交/推送、使用Bridge或进入后续阶段。
