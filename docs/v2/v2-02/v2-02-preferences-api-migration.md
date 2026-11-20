# 偏好控制接口迁移

偏好使用当前演示用户的结构化接口，不再由聊天分派 Memory Task。严格旧聊天命令会返回接口迁移提示。客户端先请求 `POST /agent/preferences/read`，以返回的 `revision` 作为下一次写入的 `expected_revision`；空档案的 revision 为 null，首次写入使用 0。

`POST /agent/preferences/mutations` 请求示例：

```json
{
  "user_id": "dev-user",
  "operation_id": "replace-with-a-unique-operation-id",
  "expected_revision": 0,
  "command": {"operation": "upsert", "field": "answer_style", "value": "concise"}
}
```

字段支持 `answer_language`（`zh-CN`、`en`）和 `answer_style`（`concise`、`detailed`）；`delete` 指定字段，`clear` 不指定字段和值。每次新操作使用新的 operation_id；重试相同操作必须保持用户、操作 ID、参数和 expected_revision 一致。请求的 user_id 经服务端演示身份和 scope 核验，不代表生产认证。

写入响应丢失或返回 `unknown` 后，使用原 operation_id 请求 `POST /agent/preferences/operations/{operation_id}/status`。结果仍为 unknown 时，系统阻止该用户后续写入；当前值未变化不能证明原写未执行。`prepared` 表示该命令已记录且写入明确未开始，可用相同参数重试；它不代表 unknown 已解决。Revision 冲突时先读取当前档案，再以新的 operation_id 和预期版本提交明确的新操作。

当前客户端集合中的偏好示例使用 `preference_revision` 与 `preference_operation_id` 环境变量，需手动按响应更新；新操作不得沿用旧 ID。集合和 OpenAPI 仅经过静态检查，未在桌面 Postman/Apifox 中验证脚本或变量回填。

数据库、Store 和 Saver 必须就绪，旧 Memory Task 的切换门禁必须通过。结构化偏好控制不依赖模型就绪；未配置模型上下文窗口/输出限额时，普通聊天仍按 V1 当前 Task 输入执行，V2 背景注入与维护不启用。显式配置限额后才启用完整输入预算；摘要另需配置 `AGENT_CONTEXT_SUMMARY_OUTPUT_TOKENS`，不要将供应商最大输出能力直接当摘要预算。
