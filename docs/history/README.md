# 历史设计资料索引

归档日期：2026-11-08。此目录保存原电商智能客服项目的九阶段路线图、阶段详细设计及搭建记录，供技术追溯和按需参考，**不作为 Agent Engine Demo V1 的开发依据**。

历史文档内“审核通过”“待开发执行”等状态仅适用于旧项目目标，不表示新 V1 已确认相同需求、已完成实现或通过验收。保留历史正文与原编号，仅修正归档后的相对链接；不得直接按旧任务启动开发。复用技术片段须在当前阶段设计中明确适用范围。

## 当前有效入口

- [项目定位、架构与V1范围（权威文档）](../agent-engine-demo-plan.md)
- [唯一有效的V1路线图：六阶段](../development-roadmap.md)
- [当前代码Graph协议参考](../graph-protocol.md)：保留在docs根目录，不属于历史设计，也不表示目标架构已实现。
- [项目开发规范](../../AGENTS.md)

新会话依次阅读定位文档、六阶段路线图，按需参考当前Graph协议即可开展Task设计，无需先阅读本目录。

## 历史文件

| 文件 | 历史范围 |
| --- | --- |
| [development-roadmap-commerce-history.md](development-roadmap-commerce-history.md) | 原九阶段、34个二级环节路线图 |
| [01-environment-and-scaffold.md](01-environment-and-scaffold.md) | 原环境与工程搭建记录 |
| [01-1-engineering-and-architecture-baseline-plan.md](01-1-engineering-and-architecture-baseline-plan.md) | 原1.1工程与架构基线设计 |
| [01-stage-detailed-design.md](01-stage-detailed-design.md) | 原01工程基线与核心协议设计 |
| [02-stage-detailed-design.md](02-stage-detailed-design.md) | 原02数据、身份与会话生命周期设计 |
| [03-stage-detailed-design.md](03-stage-detailed-design.md) | 原03 Supervisor与执行治理架构 |
| [03-stage-execution-plan.md](03-stage-execution-plan.md) | 原03开发执行计划 |
| [04-1-order-service-design.md](04-1-order-service-design.md) | 原订单查询领域服务与模拟数据设计 |
| [04-2-tool-registry-design.md](04-2-tool-registry-design.md) | 原工具注册与渐进式发现设计 |
| [04-3-tool-execution-design.md](04-3-tool-execution-design.md) | 原工具策略与执行设计 |
| [04-4-order-agent-design.md](04-4-order-agent-design.md) | 原OrderAgent查询子图设计 |
| [04-stage-execution-plan.md](04-stage-execution-plan.md) | 原04开发执行计划 |

本次仅归档Markdown与维护链接，未删除历史资料、修改业务代码或数据库，未运行测试、迁移或模型联调。当前状态：**项目定位与整体路线图已确认，等待逐阶段详细设计。**
