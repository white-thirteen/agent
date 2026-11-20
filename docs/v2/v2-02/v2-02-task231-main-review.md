# V2 02 Task 2.3.1 主复核

2026-11-20：**VERIFIED**，非人工 ACCEPTED。主 Agent 对照[实现报告](v2-02-task231-implementation-report.md)、[首轮独立 QA](qa/v2-02-task231-qa-report.md)、[fix01](fixes/records/v2-02-task231-fix01-report.md)、[独立复测](qa/v2-02-task231-retest-report.md)与维护恢复源码，关闭 `V202-231-QA-001 / P2`，允许按冻结依赖进入2.3.2。

- Builder 计算完整必需输入与输出预留，历史作为独立低信任背景；当前 Task、可信身份、业务事实及当前 Evidence 保持既有来源。三个专业 Agent 显式接收背景，退款目标仍须由当前 Task Human 确认。
- 运行内压缩消耗当前 Run 预算，完成后维护使用独立持久预算及会话互斥。旧绑定恢复固定来源，实际模型输入视图在退款中断前保存。
- 结构化偏好入口通过原 Policy、Executor、Manager 和 Store，使用独立 command_id 与持久回执；UNKNOWN 阻止同用户不确定写入。新请求旧 Memory Graph 退役，严格旧命令返回迁移提示，旧活动或未知任务阻止切换。
- 已发布而缺少维护关联回执的版本，先核对固定来源、归档完整性、摘要及覆盖再幂等补记。会话已采纳、尚未采纳和过期预算均不重做摘要、不改变 Graph 或 Revision 状态、不新增额度；不把补记等同 APPLIED。

首轮独立受控119 passed；真实组件组合14 passed/1 failed，该失败来自并发QA探针干扰全库快照，清理后原文件独立3 passed。修复后独立真实PG/Saver/文件探针2 passed，运行与关闭4 passed，均串行执行；原FAIL及原始结果保留。采纳使用真实新请求，回执丢失以持久状态模拟，尚非实际进程终止。第三方LangGraph弃用警告保留。

当前无未关闭本Task问题。真实进程重启、渐进迁移、真实模型固定语义质量、资源观测及完整V1/V2 01回归留给2.3.2；客户端仅静态验证。011仅应用本轮隔离双库，正式库和.env未改，Git未提交或推送。
