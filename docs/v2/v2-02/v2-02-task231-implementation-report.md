# V2 02 Task 2.3.1 实施记录

本记录交主 Agent 复核及独立 QA；不代表阶段验收。冻结设计、正式数据库、原 `.env` 和 Git 均未改动。迁移 `011_preference_control.sql` 已由主 Agent 应用于 Linux 隔离双库；本执行未自行初始化或重启数据库。

## 实现

- `app/context/builder.py`、`app/runtime/model_gateway.py`：纯构建完整输入，计入可信指令、实际工具或结构化 Schema、当前输入和输出预留；历史按完整交互作为单独低信任背景，必需输入超限明确失败。模型输入计数标记估算，供应商使用量单独记录；真实模型能力未在本任务重测。结构化输出上限通过受控 HTTP transport 检查实际请求。
- `app/graph/contracts.py`、`state.py`、`transfers.py` 和 Supervisor、Order、Refund、Knowledge 模型节点：移除当前 Task 消息 12 条截断，通过独立 history 字段传递会话背景，保存实际 view、输入哈希和来源。退款目标需出现在当前 Task 可信 Human 中，否则澄清；Knowledge 检索 Query 仍来自当前 Task Human，Evidence 仍由本次检索和来源验证产生。
- `app/runtime/agent_runtime.py`、`context/manager.py`、`context/maintenance.py`：固定读取 Checkpoint 引用并校验原 Summary/Archive；运行内必要压缩使用当前 Run 预算，不裁剪父消息、不推进会话版本。普通完成后确认最终 Checkpoint、结算发布结果，再在释放执行权前持久登记维护；有限执行器获取会话权及该接线的 PostgreSQL advisory lock 后重核并发布候选 Revision。失败不撤销已发布业务结果；恢复原 claim 以前必须取得其 advisory lock，预算持久复用。过期无摘要工作不占用恢复扫描，已有同源 Summary 仍可恢复发布。
- `app/api/routes/preferences.py`、`api/schemas/preferences.py`、`services/preference_service.py`、`tools/{models,policy,executor}.py`、`memory/manager.py` 和迁移 `011`：提供读、变更、原 operation 状态三个结构化端点。可信控制上下文使用真实 command_id，经同一 Policy/Executor 和原 Manager/Store；PREPARED、EXECUTING、APPLIED、CONFLICT、UNKNOWN 由 PG 持久记录。证明尚未启动的失败可回到 PREPARED；已有未知结果的核对失败不回退、不重发。新来源和旧 Task 来源均可读取。
- `app/main.py`、Supervisor 公开路由 Schema/Prompt 和客户端文件：新请求不装配 Memory Graph，严格旧命令在 LLM 前提示迁移；切换前检查旧会话历史中的未完成或不确定 Memory Task。偏好控制不依赖模型就绪。当前 Postman collection、OpenAPI、环境模板和 [迁移说明](v2-02-preferences-api-migration.md) 已更新；旧 V1 归档未重写。
- `app/core/config.py`、`.env.example`、`.gitignore`：增加独立摘要输出预算配置，运行归档目录不进入 Git。窗口和输出限额默认仍未配置：普通聊天保持 V1 当前 Task 输入，V2 背景注入、上下文采纳及模型维护不启用；若已有绑定版本或活动 V2 背景而配置缺失，恢复受门禁保护。启用摘要还须显式配置摘要输出预算，未以供应商最大输出能力充当建议值。

## 实际验证

所有测试使用项目 `.venv`；以下模型均为受控替身，除明确标注的 Saver、Store、PG 和文件外不声称真实外部服务调用。

- `.\.venv\Scripts\python.exe -m pytest tests/test_context_builder.py tests/test_preference_cutover.py tests/test_context_revision_runtime.py tests/test_graph_protocol.py tests/test_order_graph.py tests/test_knowledge_graph.py tests/test_refund_full_controlled.py tests/test_refund_checkpoint.py tests/test_memory_manage.py tests/test_memory_reader.py tests/test_model_gateway.py -q --tb=short`：119 passed；[原始输出](evidence/v2-02-task231-controlled-pytest.txt)。其后针对恢复时无 ContextManager 的门禁补充定向用例：`tests/test_refund_full_controlled.py tests/test_refund_checkpoint.py tests/test_context_revision_runtime.py` 17 passed；新增门禁及关闭执行器用例 2 passed。
- `.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/linux-pg-launcher.py pytest tests/test_preference_control_postgres.py tests/test_context_maintenance_runtime_postgres.py tests/test_context_run_compaction_postgres.py tests/test_refund_context_checkpoint_postgres.py tests/test_context_revision_postgres.py tests/test_memory_manage_postgres.py -q --tb=short`：15 passed、1 个第三方弃用警告；[原始输出](evidence/v2-02-task231-isolated-pg-pytest.txt)。后续恢复门禁小幅调整后，对 `tests/test_refund_context_checkpoint_postgres.py` 真实隔离库定向复测 1 passed。
- 隔离组合覆盖真实 PG/Saver/Store/本地文件：旧 Task 来源读取及新 command 来源；跨用户、CRUD、revision、幂等、已写回执丢失核对、值未变化仍 UNKNOWN；维护先登记、会话互斥、超时后预算复用、旧锁持有时不抢占、恢复扫描不饥饿；运行内摘要计入当前 Run 且父消息未裁剪；真实 Saver 退款中断保存 view/hash、原 Archive 篡改时拒绝恢复且副作用为零、修复后原调用只执行一次。退款业务服务和模型为受控替身。
- 新增真实测试预检 `127.0.0.1:56431`、`agent_demo_test/agent_test`、PG 170012 和专用数据库 comment，使用唯一用户、会话和线程；finally 按各自标识删除临时 Store、回执、维护记录、Archive/Summary/Revision 和 Saver thread，并核对记录或 thread 已清理。旧 Memory 真实门禁继续执行原前后全 public 行集/列定义与 checksum 核对。未扩展固定订单 seed 例外。
- `.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/v2-02-task231-apifox-check.py`：JSON、OpenAPI 内部引用、三端点、环境变量与旧聊天迁移示例静态检查通过；[脚本](evidence/v2-02-task231-apifox-check.py)、[输出](evidence/v2-02-task231-apifox-check.txt)。未操作桌面客户端，未验证脚本或变量回填 UI。
- 对本任务涉及的 `app/context`、Runtime、Graph、Memory、Tools、API、Service、配置及相关测试执行 `.\.venv\Scripts\python.exe -m ruff check`，通过。完整路径与命令由本记录和对应原始输出定位。

## 留待独立 QA 和 2.3.2

本任务未运行真实模型摘要语义质量、固定质量夹具指标、资源收益或完整阶段回归；第三方 LangMem 依赖出现一次弃用警告。上述受控和隔离库结果不替代独立 QA、真实模型质量判定或用户验收。旧 Memory 切换门禁保守拒绝无法确认已安全结束的历史，相关任务须先由旧版本完成或明确处理。客户端仅静态检查。

待独立核查：Revision 已发布但维护记录的 `revision` 回执未写入时若发生进程中断，重启后新请求先采纳该 Revision，维护 worker 可能因当前 `context_ref` 已变化而延期旧工作，留下 `SUCCEEDED` 且 `revision` 为空的记录。该交错未实测，不能把维护回执恢复宣称为完整闭环。
