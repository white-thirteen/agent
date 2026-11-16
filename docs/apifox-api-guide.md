# Apifox 接口文档与导入说明

更新：2026-11-15。基于当前 FastAPI 路由和请求 Schema 导出，共 **11 个 HTTP 接口**。订单、支付及退款均为本地模拟；RAG 使用本地 Qwen CPU/1024 与 PostgreSQL/pgvector，Memory 使用同一 PostgreSQL Store。

用户负责手动导入。当前文件已完成代码契约核对；Apifox 的实际导入、变量脚本及 SSE 显示效果仍待用户验证，不将此前 HTTP 功能测试记为 GUI 验证。

## 选择导入文件

| 文件 | 用途 |
| --- | --- |
| [OpenAPI 3.1 JSON](../apifox/agent-engine-demo.openapi.json) | 接口文档：11 个实际接口、请求参数、字段约束、请求示例、SSE 类型与主要响应说明。 |
| [Postman Collection v2.1](../apifox/agent-engine-demo.postman_collection.json) | 推荐用于顺序演示：同一接口按订单、退款、RAG、Memory 等场景保留多个请求。 |
| [无秘密环境模板](../apifox/local.postman_environment.json) | 配合 Postman 集合使用，包含本地 URL、用户/订单及动态关联变量。 |

在 Apifox 新建独立项目，从导入入口选择相应格式和本地 JSON 文件。OpenAPI 和 Postman 二选一即可，避免在同一项目中重复导入相同接口。若环境模板或后置脚本未被当前版本保留，按模板手工建立变量、复制响应字段即可。

导入只创建接口材料，不会启动后端。完整的独立测试数据准备、服务启动、重启、核对和清理见 [演示操作说明](demo-walkthrough.md)。此前 Agent 的测试服务已关闭，临时数据已清理；不能直接复用历史证据中的 UUID。

## 地址与身份

- 独立演示默认前置 URL：`http://127.0.0.1:8631`。如果后端启动在其他端口，修改前置 URL 或环境 `base_url`。
- `user_id` 必须在后端允许名单内；它是 development/test 演示身份选择，不是登录令牌。独立演示使用准备脚本生成的 `user_a/user_b`；OpenAPI 中的 `dev-user` 只是默认配置示例，需替换为当前实际用户。
- `conversation_id` 由客户端选定，同一用户/会话绑定稳定线程。跨会话读取相同用户偏好时，应更换会话而保留用户。
- 本地审批只在 development/test 注册，并限制回环访问。没有管理员 Key/Header；审计 Actor 由服务端固定，不接受客户端 `reviewer_id` 或权限字段。
- API Key、数据库连接串和 `.env` 不应导入 Apifox。

## 接口清单

| 方法 | 路径 | 用途 / 请求 |
| --- | --- | --- |
| GET | `/health` | 安全资源就绪状态；无 body。 |
| POST | `/agent/chat` | 普通输入、订单、退款申请、RAG、显式记忆命令；返回 SSE。 |
| POST | `/agent/runs/{run_id}/status` | 查询 Run；body 为用户及原会话。 |
| POST | `/agent/runs/{run_id}/events` | 当前快照及未来 SSE；body 为用户及原会话。 |
| POST | `/agent/tasks/current` | 查询会话持久当前 Task；body 为用户及原会话。 |
| POST | `/agent/refunds/{application_id}/status` | 查询原模拟退款事实；body 为用户及原会话。 |
| GET | `/admin/approvals` | 审批列表；可选 query `decision`。 |
| GET | `/admin/approvals/{approval_id}` | 读取原审批和 `subject_digest`。 |
| POST | `/admin/approvals/{approval_id}/decision` | 提交 `APPROVED` 或 `REJECTED`，必须带原摘要。 |
| POST | `/admin/approvals/{approval_id}/resume` | 独立恢复原审批关联任务；body 为 `{}` 或省略。 |
| POST | `/admin/approvals/{approval_id}/repair-binding` | 仅原中断绑定缺失时修复；body 为 `{}`。 |

RAG 和 Memory 共用 `/agent/chat`，没有单独的 `/rag`、`/memory` HTTP 接口。`workflow_id` 是 `task_id` 的同值兼容别名，不是另一套工作流标识。

## 普通请求

`POST /agent/chat`，`Content-Type: application/json`：

```json
{
  "user_id": "{{user_a}}",
  "conversation_id": "{{conversation}}",
  "message": "请查询我的订单",
  "input_mode": "new_task"
}
```

| 字段 | 约束 |
| --- | --- |
| user_id | 必填，1～128 字符，不含 NUL；受后端演示名单限制。 |
| conversation_id | 必填，1～128 字符，不含 NUL。 |
| message | 必填，1～32000 字符，不能只有空白。 |
| input_mode | 可省略，默认 `auto`；另支持 `new_task`。审批等待或运行中不能用 new_task 绕过门禁。 |
| request_id | 可省略或 null；传入时必须为 UUID，仅提供当前进程窗口内的 HTTP 去重。 |

订单示例：`请查询我的订单 {{order_ok}}`。退款示例：`请为我的订单 {{order_ok}} 申请模拟退款`。RAG 示例：`银帆演示中普通聊天可以批准模拟退款吗？`，需事先启用 Embedding 并导入对应知识。

Memory 使用以下明确语法，分别作为 message；不要将多个写命令合并为一句：

| 操作 | message |
| --- | --- |
| 保存语言 | `请记住：回答语言=英语` |
| 保存风格 | `请记住：回答风格=简洁` |
| 查看 | `请查看偏好记忆` |
| 修改风格 | `请修改记忆：回答风格=详细` |
| 删除单字段 | `请删除记忆：回答风格` |
| 清除偏好 | `请删除全部偏好记忆` |

清除偏好仍保留 revision 和最小幂等元数据，不会抹除历史 Checkpoint。

Run/Task/退款状态及 Run 事件订阅的 body 相同：

```json
{"user_id":"{{user_a}}","conversation_id":"{{conversation}}"}
```

其中 `run_id` 是某一次执行，`application_id` 是本轮真实申请 UUID，不能混用 task_id。`current_task` 可为 null；没有原会话可能返回 404。重启后旧 Run 缓存可能不存在，应查询持久当前 Task、原申请或原审批。

## SSE 响应

`/agent/chat` 和 `/agent/runs/{run_id}/events` 返回 `text/event-stream`，不能按一个完整 JSON 解析。示意帧如下，实际关联以本轮返回值为准：

```text
event: token
data: {"content":"最终回复正文","sources":[],"run_id":"本次Run","task_id":"原Task","workflow_id":"原Task","sequence":4}

event: done
data: {"run_status":"completed","task_status":"completed","run_id":"本次Run","task_id":"原Task","workflow_id":"原Task","sequence":5}

```

观察 `status`、`token`、`workflow_paused`、`workflow_resumed`、`error`、`done`。`done` 只表示本次 Run 流结束；等待审批时 Task 仍为 `waiting_approval`，不是退款成功。订阅断开不会取消已受理执行；重新订阅不重放历史 token，禁止携带 `Last-Event-ID`。

## 审批与恢复

1. 退款流暂停后，查询 `/agent/tasks/current`，取得 `current_task.refund.application_id/approval_id`。不要从列表猜选别人的审批。
2. GET 原审批详情，从返回值复制 `subject_digest`。详情包含 decision、expires_at、binding_status、approval_validity、can_decide、can_resume。
3. POST 原审批 `/decision`：

```json
{"decision":"APPROVED","subject_digest":"{{subject_digest}}"}
```

拒绝则用 `REJECTED`。返回 `resume_required=true` 后，独立 POST 原审批 `/resume`，body 为 `{}`。首次实际受理为 202；返回新 run_id，但沿用原 task_id/调用/operation。正常 END 再次恢复为 200、`accepted=false`、`run_id=null`，不会重新退款。

审批有效期从原创建时间起 30 分钟，重复决定或恢复不续期。完整重启后通过原审批恢复，不能重发自然语言退款请求代替 resume。结果未知时先核对原 operation，不改 ID 盲试。`repair-binding` 不是正常审批的必经步骤。

## 常见结果

| 结果 | 含义 |
| --- | --- |
| 200 | JSON 查询/决定结果，或 SSE 已建立；需继续看业务状态。 |
| 202 | 恢复已受理，后续查询新 Run。 |
| 403 | 演示用户不允许。 |
| 404 | 身份/会话/Run/申请不匹配，或本地管理入口不适用。 |
| 409 | thread_busy、等待审批、摘要/决定/绑定冲突、未知恢复位置等；按具体 code 处理。 |
| 422 | 参数、UUID 或额外字段不符合 Schema。 |
| 503 | 模型、数据库、Saver、Store 等资源不可用，或运行容量不足。 |

Runtime 公共错误通常为 `{"error":{"code":"...","message":"..."}}`；本地管理 HTTP 错误可能为 `{"detail":{"code":"..."}}`；422 为 FastAPI 校验错误。SSE 开流后的错误通过 error/done 事件报告。RAG 资料不足为 rejected 安全说明，技术故障为 failed；Memory unknown 需要先核对，不应报告成功或换 operation 重试。
