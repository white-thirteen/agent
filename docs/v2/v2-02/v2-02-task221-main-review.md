# V2 02 Task 2.2.1 主复核

2026-11-19：**VERIFIED**，非人工 ACCEPTED。独立 QA PASS，无编号问题，允许进入2.2.2。

主 Agent 对照冻结设计审查当前 Manager、Repository、Compaction、Gateway 及009迁移，并核对[实施报告](v2-02-task221-implementation-report.md)、原始真实小合成回执及[独立 QA](qa/v2-02-task221-qa-report.md)：

- 运行内压缩使用正式RunScope的剩余期限和累计尝试，请求前登记尝试，维护所有者独立，不假造业务Task或Agent。
- 维护预留与逐尝试回执通过attempt_id关联，数据库截止与额度不因更换maintenance_id、来源Run或摘要版本清零；claim与摘要复用避免同工作并发重复调用。模型调用期间无长数据库事务。
- Summary关联实际READY Archive、消息序列、父摘要、输入哈希及策略/模型/Prompt版本；归档成功而摘要失败保留原文，已保存摘要可在完成回执失败后复用。精确summary_id恢复经会话身份核验。
- 项目摘要Prompt明确否定约束、未完成事项、矛盾与未知，历史不授予权限或重新应用偏好。当前小合成调用仅证明兼容，未代替阶段保真验收。

独立真实PG定向回归28 passed/0 skipped，另有claim/旧回执探针；唯一schema清理已核验。主复核采用已有独立原始结果，不重复相同测试。初次SQL类型错误和真实探针历史失败保留。

后续强制边界：`interrupt_maintenance` 是可信内部恢复操作，Runtime必须先取得会话独占权并证明旧执行者已消失；不能挤掉仍在运行的claim。该真实接线及在途终止须在后续Task验证。当前组件未裁剪Graph、未装配维护调度，旧Checkpoint和审批升级门禁仍待2.2.2。

代码schema门禁为9，正式库未迁移，新代码正式部署仍需专项迁移授权。未提交或推送Git。
