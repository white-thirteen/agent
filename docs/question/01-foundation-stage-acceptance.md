# 01 基础工程与运行环境正式验收建议

日期为 2026-11-10。主 Agent 结论为 **VERIFIED，建议批准阶段正式验收并进入 02**。用户正式批准待确认，02 为 NOT_STARTED，Git 阶段归档待授权。

## 1. Task 完成情况

| Task | 实际交付 | 验证结论 |
| --- | --- | --- |
| 1.1.1 工程复用与事实基线 | 保留应用、分层、Graph/协议与 SSE formatter，区分当前和后续行为 | 通过，既有 Ruff 遗留单独追踪 |
| 1.1.2 Demo 设置与运行入口 | 集中配置、秘密隐藏、安全失败、无资源 HTTP、启动说明及名单校验 | 通过，名单 NUL 修复已独立回归 |
| 1.2.1 数据库与迁移入口 | 固定 PG17.6、双库、显式 bootstrap、事务迁移/checksum，获批 002 | 通过，现有真实库回归及既有环境证据齐备 |
| 1.2.2 连接与会话绑定 | 有界池、稳定 thread、用户归属与并发绑定、资源释放 | 通过，真实并发/隔离/重开及首次 QA 跨进程证据 |
| 1.3.1 统一模型调用 | Gateway、模型限制和 Usage、原生 ToolCall、结构化调用、显式真实模型脚本 | 通过，受控回归及既有真实文本/结构化证据 |
| 1.3.2 演示身份与管理边界 | 普通 scope、production 禁用、单次解析、context/options、真实 Session 准备 | 通过，P2-01 修复及独立回归完成 |

六个 Task 均完成实现及相应验证。具体文件及真实环境见 [D01 交付报告](../01-foundation-detailed-design.md#01-正式开发交付报告2026-11-09)。

## 2. 独立 QA 与修复闭环

证据链为 [首次独立 QA](01-foundation-acceptance.md) → [主 Agent 裁决](01-foundation-main-review.md) → [修复任务](../resume/01-foundation-fix-task.md) → [修复报告](../resume/record/01-foundation-fix-report.md) → [独立回归](01-foundation-regression-report.md)。

- P2-01 已关闭。原 NUL 输入导致 500，修复后两个请求标识均为 JSON 422、零准备调用、真实库零新增，正常准备仍为 JSON 503 并保存真实绑定。配置、Unicode、规范化及长度行为经独立核验。
- P3-02 已关闭。当前状态入口同步及历史基线标注经独立 QA 核对。
- P3-01 为接受的非阻塞遗留。全仓 lint 仍有 supervisor prompt E501，format 仍有 8 个失败文件。02 修改相关代码时处理对应项，06 最终交付核对剩余项，由主 Agent 持续追踪。

独立回归受影响测试 22 passed，完整真实库 82 passed、0 failed、0 skipped。四个修复文件 Ruff lint/format 通过，真实 PG/ASGI、精确清理、池及同步/异步 HTTP 客户端关闭验证通过。主 Agent 已复核报告与关闭条件，本轮未重复运行已通过验证。

## 3. D01 第 8 节正式验收矩阵

| 门禁 | 结论 | 主要依据 |
| --- | --- | --- |
| 工程/配置 | 通过，保留 P3-01 | HTTP/配置回归、非法配置安全失败，原 pip check 通过 |
| PG 环境 | 通过 | 真实双库及版本、迁移重跑/checksum/未知版本拒绝/失败回滚 |
| 生命周期 | 通过 | 正常及部分初始化失败清理，独立回归真实资源退出 |
| Session | 通过 | 真 PG 并发/归属/碰撞回滚/重开、首次 QA 跨进程读取 |
| 请求准备边界 | 通过 | NUL 422、正常 JSON 503 和实际绑定，单次解析及 context/options 契约 |
| 模型网关 | 通过 | 原生调用、解析、超时/次数/重试、未知用量受控回归 |
| 真实模型 | 通过，沿用已接受证据 | D01 及首次独立 QA 的 DeepSeek 文本与 function_calling 分项实测 |
| 演示身份/隔离 | 通过 | 受控名单、production 禁用、普通 scope、Unicode/配置 NUL 回归 |
| 文档 | 通过 | 当前入口、问题闭环、运行说明及限制明确，历史记录保留 |

## 4. 验证边界与遗留影响

本轮独立回归的 HTTP 使用真实应用 lifespan 加进程内 ASGI。独立 Uvicorn socket 与真实模型采用此前 QA 和开发交付证据，bootstrap/Volume 重启采用此前开发报告证据。这些操作在本轮未重验，空环境重建未获得本轮独立验证。

P3-01 使全仓 Ruff 仍非零退出，当前无运行缺陷证据，保留处理责任。此前获批 VM 部署和 002 约束修正有记录，无待批准设计变更。

01 当前 chat 准备成功返回 503 符合设计。02 需复用 DemoContext/SubmitOptions、持久 thread、Gateway 与 Limits/Usage 契约，落实正式 Task、Supervisor/专业骨架及独立执行/SSE。持久 Checkpoint、工具治理、退款审批、RAG 和 Store 按其后续阶段依赖推进。当前没有阻塞 02 开发的技术问题。

## 5. 人工决定与版本归档

请求用户明确批准 01 阶段正式验收并进入 02 AgentRuntime 开发。获批后记录 ACCEPTED，执行当前阶段安全 Git 归档，再准备下一阶段执行任务，交用户人工启动。

当前分支 real-model-chat，HEAD 为 2dcf652，origin 为 https://github.com/white-thirteen/agent.git。工作区混有既有 Graph/设计及 01 交付，获批后逐文件、逐差异核对归属并仅暂存适当内容。凭据继续按 Git 忽略规则保护。当前没有当前阶段归档成功的记录。
