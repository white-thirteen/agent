# V2 02 Task2.3.2 主复核

2026-11-20：**VERIFIED，非人工ACCEPTED**。主Agent对照冻结设计、[实施交接](v2-02-task232-implementation-report.md)、fix01～03、逐轮原始质量结果与[正式独立QA](qa/v2-02-task232-qa-report.md)，关闭`V202-232-QA-001/002/003 / P2`。本阶段六Task技术实现和独立QA完成，不进入V2 03，不提交推送，等待人工验收。

## 关闭依据

- QA-001关键约束遗漏：当前v5完整八例保留原标识、未执行退款、核查要求、新目标与没有新退款请求，独立逐项复测通过；未以覆盖ID代替语义。
- QA-002控制指令污染：历史角色/原文与prior_summary独立JSON来源，system控制指令分离，实际初始和增量transport检查及r6语义复测通过，旧版本引用仍按原来源核验。
- QA-003未提及推断执行状态：v5只保留直接陈述、未提及类别省略，r6未再把查询或Evidence缺失写成实际未执行；温度0只是摘要请求策略，不声称确定性或泛化保真。
- fix02参数/截断边界：DeepSeek官方host实际发送max_tokens；真实低限8返回output8/length。摘要截断先记录用量后失败，真实PG检查READY原文保留、FAILED维护、无Summary；不将原输出256/实报333异常视为PASS。
- 渐进迁移仅在新Task安全边界恢复可证明的公开消息关联，未知保留/incomplete、Run不猜测、旧Checkpoint不改。初始Saver输入快照的有限跳过有后续可信Task证明；孤立输入和不安全旧Memory仍被门禁拒绝。

## 验证与实际边界

最终代码[完整门禁](evidence/v2-02-task232-full-regression-r3.json)290 passed/0 failed/0 skipped，真实Qwen/PG/Saver/Store启动和关闭通过，数据保护通过，水位36→47符合预审计11次发布/清理，原seed窄例外未改写或deselect。该完整组由开发执行，独立QA检查日志、回执、源码及保护规则，不冒称独立重跑290项。

正式独立QA另串行复验38 passed/0 failed/0 skipped，覆盖真实隔离PG/Saver/Store/文件、迁移、Revision、偏好、实际子进程终止与新进程预算恢复及受控HTTP参数；精确清理断言通过，未独立做全库快照。主Agent从原生QA会话实际工具输出保存[38项原始结果](evidence/v2-02-task232-independent-qa-raw.txt)及[来源/hash回执](evidence/v2-02-task232-independent-qa-raw-receipt.json)，不是从QA自述重建，也未重复测试。

真实模型查询隔离模拟订单、跨Task背景与应用重启，真实Qwen/BGE/Hybrid直接检索、当前Evidence，以及v5同节点资源6958→225消费者input（摘要另6121/136、1.70秒、三次预算）均有原始证据，并由QA核对范围。资源实验图/历史为合成夹具，Runtime所有权与调用真实；不冒充业务流量净收益。

无未关闭本Task编号问题。保留所有历史失败，不把受控模型或持久状态模拟称机器断电/真实外部模型在途终止；真实外部模型Knowledge Graph回答、客户端UI及任意/增量历史的语义泛化仍未实测。正式库及.env未改，新迁移只用于隔离库，部署仍需专项授权。
