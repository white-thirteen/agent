# 项目真实 HTTP 联调：独立 QA

结论：**FAIL / 不作整体 PASS**。真实业务主路径及补充验证取得以下证据；IT-001 为待归因的真实模型路由失败，IT-002 为本轮确认的现有限制。此报告只覆盖本次 HTTP 联调，不替代主 Agent 的完整门禁和 V2 03 独立多候选测试。

## 发现

- **IT-001 / P2 / 待归因**：真实请求“请简要说明你能处理什么问题。”的 SSE 返回 `model_output_invalid`、`Model routing failed.`，Task 为 `failed`；本轮原探针对该非业务闲聊假定 `completed` 的断言不适当，但实际失败不能当成正常 `needs_input` 或忽略。[原始 SSE](project-http-run-01/http-45-preference-new-session.bin)及[本轮报告](project-http-run-01/report.json)保留。原轮没有保存结构化模型原始响应，不能确定是外部模型输出、解析还是其他契约原因。另一次仅含原 Supervisor prompt 和该句的单次 Gateway 诊断成功解析为 `NewSupervisorOutput`，1 次 attempt、863 输入 / 185 输出 / 1048 总 tokens，`finish_reason=tool_calls`，无 parsing error；其上下文与原 HTTP 执行不同，不是原请求的复现，不足以关闭问题。[脱敏诊断](project-http-it001-diagnostic.json)。
- **IT-002 / 既有能力限制，适用范围待裁决**：结构化控制写入 `answer_language=en` 后，新会话真实订单查询成功，但最终 SSE 答案为中文。当前 [Order 结果映射](../../../app/graph/specialists/order/builder.py)按确定性事实构造中文摘要。本轮证明控制端写入、重读、幂等、用户隔离以及新会话订单可用；未取得该次子图实际偏好注入的完整观测证据，不能声称英文最终展示生效，也不据此要求重设计业务格式。[原始 SSE](project-http-run-02/http-04-preference-cross-session.bin)。

## 已执行证据

- 项目 `.venv`、真实 DeepSeek、独立 PostgreSQL、真实 Qwen 1024 和 BGE；测试仅覆盖带专用标记的隔离测试库，使用唯一用户、订单和文档。测试配置显式启用 Hybrid，Context 窗口 16384、输出 512、摘要 256、独立 archive 根目录、模型自动重试 0；这些为本轮配置，不代表原 `.env` 默认值。测试专用唯一文档的直接检索返回 hybrid 和实际 reranker 分数，但只有一个候选，不能据此宣称排序质量收益或把组件检索称为 HTTP Graph 重排观测。
- [第一轮](project-http-run-01/report.json)经真实 Uvicorn TCP 验证本人订单、跨用户拒绝、等待审批时普通聊天 409、SSE `done` / `workflow_paused`、Knowledge 来源版本与 chunk、批准和拒绝、重复决定及重复恢复。旧进程完全退出后不同 PID 恢复原审批，原 Task、call、operation、参数及审批绑定保持；SQL 显示批准订单 `SUCCEEDED` 且已模拟退款，拒绝订单 `REJECTED` 且未退款，操作者为 `local-demo-approval`。后续非业务请求发生 IT-001，本轮进程 exit 1，不将整轮记为通过。
- [第二轮](project-http-run-02/report.json)只补充缺口：偏好结构化创建、相同 operation 重试、另一用户隔离、新会话合法订单、更新和删除；同会话四次真实订单请求自然触发维护，后续第五次订单请求采纳 revision 1。真实数据库记录 Archive、Summary 和 `APPLIED` Revision 关联，维护 `SUCCEEDED`，其一次摘要调用记录 known tokens 221 / 66 / 287。采纳前 Checkpoint 按相同 ID 重新读取并比较完整反序列化结构，保持相等。真实 SSE 客户端收到首个事件后提前断开，原受理订单 Run 随后通过状态接口达到 `completed`；不声称事件重放。第二轮 exit 0，但业务语义和以上发现仍需结合本报告审阅。
- 两轮前后均比较全部 public 行集与列定义；唯一文档发布及删除对应 watermark 分别 **80→82** 和 **82→84**，`protected_unchanged=true`。两轮按唯一身份清理业务记录、偏好回执与 Store、Context 记录、Saver 线程和 archive 文件，自有服务进程关闭。未 seed 固定五订单。原始字节输出分别为 [第一轮日志](project-http-stdout-01.log)和[第二轮日志](project-http-stdout-02.log)，各轮目录保存 HTTP 字节流与 JSON。

每个有状态 Run 的模型 attempt 见各轮 JSON；审批恢复属于原 Task，累计次数不能与原 Task 重复相加。维护和单次诊断的已知 token 如上，其余未完整观测的 provider token 标记 unknown，不用估算补零。无 Postman/Apifox UI 或变量回填实测；未把真实组件探针、测试专用节点或诊断当成端到端替代证据。
