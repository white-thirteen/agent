# V2 02 Task 2.2.2 实施记录

本记录交主 Agent 审查及独立 QA，不代表 Task 或阶段验收。

- `migrations/010_context_revision.sql`、`app/context/repository.py`、`app/context/manager.py`：保存 Revision 及回执，发布事务核对 Summary 版本、来源、策略及 READY Archive 的身份、范围和内容哈希；管理器读取并核验文件和范围哈希。摘要可覆盖已采纳的历史及新增范围；Revision 仅裁剪新增后缀。发布候选不改 Saver。
- `app/graph/state.py`、`app/graph/nodes/response.py`、`app/graph/nodes/run_finish.py`：为新公开热消息记录可信 Task/Run 关联，结束时更新对应 Task 状态；旧消息缺少关联时保留原文，不猜测。
- `app/runtime/agent_runtime.py`、`app/runtime/context.py`、`app/main.py`：取得原会话执行 claim 后读取实际来源和当前 Checkpoint，只在正常新 Task 且原 Task 安全结束时检查候选。来源和当前消息必须有可证明前缀关系、同一基线及同会话有效归档；不匹配候选在 Run 受理后记 STALE。受理前只读；Run 结束或异常后通过 Saver 的实际 checkpoint channel_values 核对引用和已删除消息后记 APPLIED。独占会话的可信 `reconcile_context_receipt` 可补回执，但不恢复执行或解除 `_uncertain`。不调用 `interrupt_maintenance`。
- `app/graph/nodes/supervisor.py`：原 Supervisor 节点在执行工具前核对候选，同一次更新返回 ContextRef、RemoveMessage 及删减后的公开消息元数据；无新增节点。历史摘要未用于业务事实。`app/infrastructure/postgres.py` 版本门禁为10；正式数据库未迁移，隔离 Linux 双库已由主 Agent 应用 010。

## 实测

- [真实隔离 PG/Saver 与定向回归输出](evidence/v2-02-task222/targeted-final.txt)：项目 `.venv` 经 `linux-pg-launcher.py` 执行 `pytest tests/test_context_revision_postgres.py tests/test_context_revision_runtime.py tests/test_refund_checkpoint.py tests/test_refund_full_controlled.py tests/test_refund_executor.py -q --tb=short`，24 passed。新测试在连接写入前自身核验地址/端口、库、用户、PG 版本及共享 marker；唯一用户、会话、thread 与临时文件，finally 精确删除自己的 Revision/Summary/Archive 和 Saver thread 并核验。摘要及模型为受控替身，PG、Saver 和文件真实。覆盖发布/采纳分离、引用与移除、提交前/提交后故障、回执失败补记、当前基线变更 STALE、范围外追加、旧无引用 Checkpoint、旧版本引用及第二次增量采纳、用户隔离。中间 Checkpoint 结果不解除原 Runtime uncertain 门禁。
- 受理前只读与 NEEDS_INPUT、显式 new_task、审批/暂停、uncertain、停止状态门禁见新增定向测试；收紧输入等待时回执边界后，真实 Saver 与这些门禁[最终定向重测](evidence/v2-02-task222/final-adoption-gates.txt) 8 passed。resume/reconcile 原有保护由所列退款受控回归覆盖，未模拟真实断电。
- 既有 `tests/test_runtime.py tests/test_graph_state.py tests/test_graph_protocol.py` 与真实 Saver 测试组合此前 61 passed；上下文契约、Archive、Gateway 19 passed。检查与首次失败、pending writes 观察及修复过程见[控制台摘录](evidence/v2-02-task222/earlier-runs.txt)。Graph `aget_state` 可叠加持久 pending writes，故 APPLIED 以对应 `aget_tuple` 返回的实际完整 Checkpoint 为依据，不把叠加视图当成提交证明。
- Ruff 检查通过；format --check 对相关 16 个文件通过。首次 SQL 列缺失以及 pending writes 错误断言均已修复、重测；不是宣称首次全部通过。
- 旧 221/212 本机隔离 PostgreSQL 定向回归首次在只读守卫阶段连接超时，[原始输出](evidence/v2-02-task222/context-regression.txt)；主 Agent 恢复独立测试实例后[重试](evidence/v2-02-task222/context-regression-retry.txt)，221 压缩测试通过，212 Archive 测试在连接前因 Windows Proactor 不兼容失败。对后者设置 Windows SelectorEventLoopPolicy 后[重试](evidence/v2-02-task222/archive-selector-retry.txt) 1 passed。未访问正式库。

## 未闭环

未做真实断电或真实在途进程杀停；`interrupt_maintenance` 仍要求未来 Runtime 在会话独占且证明旧执行者已消失后调用。任务后维护调度、各模型节点 Builder、完整迁移及摘要质量验收属于后续 Task。完整阶段回归和独立 QA 未运行；工作区既有变更保留，未提交或推送。
