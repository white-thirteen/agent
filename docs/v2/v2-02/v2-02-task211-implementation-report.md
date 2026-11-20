# V2 02 Task 2.1.1 实施记录

本次仅提供契约与适配基础，待独立 QA；没有启动后续 Task。未修改冻结设计、正式数据库或 Checkpoint。测试未连接数据库、未建立测试数据，无数据库清理需求。

## 实现与约束

- `app/context/models.py` 固定服务端用户＋会话身份、无歧义引用编码、Archive/Summary/Revision/Checkpoint ContextRef、维护工作及偏好控制命令契约。引用是标识，不是授权；仓储必须以独立身份列过滤并核对关联。旧偏好记录 `last_mutation.task_id` 可按旧来源解释，新记录采用 `source.kind=preference_control` 和 `source.command_id`；本 Task 未重写旧记录或改变现有 MemoryManager 行为。
- `ModelGateway` 扩展独立维护所有者：每次调用前通过持久预算接口预留，随后记录已知/未知用量；最多两次、截止时间最多 30 秒、请求强制输出上限。业务 Task 原签名及计数保持。后续实现必须保证接口在同一逻辑工作上原子预留、持久截止时间和消耗，异常中断保留未知，不能用新 ID 重置；当前仅为接口，未实现数据库仓储、互斥或重启恢复。调用者应从持久截止时间计算本次剩余单调期限。
- `app/context/compaction.py` 调用真实 LangMem `asummarize_messages`，模型调用经 Gateway；检查范围及完整摘要 Prompt 输入、输出限额和实际覆盖 ID。调用方须将完整模型窗口减去输出预留和所有其他输入开销得到输入上限，并传入适用计数器。输入计数如果是近似值只能称估算，不能声称硬限制或精确计数。模型窗口和输出参数集中配置但默认未设置，不能启用维护；没有可核验的当前模型窗口，因此未填虚构参数。
- 配置使用 `context_model_window_tokens` 和 `context_model_output_tokens` 成对提供且后者小于前者；实际调用层通过 `max_tokens` 绑定，受控 ChatOpenAI 请求验证发出 `max_completion_tokens`。窗口配置仍须由部署方依据实际模型配置核验，未声称模型真实上限已确定。
- LangMem 0.0.30 的安装源码显示其 `max_summary_tokens` 只用于估算，内部会调整/裁剪输入；适配器独立预检，调用后核对范围。依赖使用 `requirements.txt` 为约束解析，保留原有包版本，新增 LangMem 和其五项传递依赖。上游 trustcall 当前有 LangGraph 弃用警告。

## 后续实现必须履行的持久契约

仓储按用户和会话双列关联并验证 Archive、Summary、Revision 和 ContextRef；保存消息范围/哈希、来源 Checkpoint、相对路径/文件哈希、摘要父子与实际覆盖、策略/模型/Prompt 版本及发布/采纳回执。事务发布检查关联和 READY，PUBLISHED 不代表 APPLIED；Graph 实际 Checkpoint 是采纳依据。维护工作以身份、来源范围/内容哈希和策略唯一约束复用，保存来源 Task/Run、预算版本、绝对截止时间、已预留/实际尝试和已知/估算/未知用量、产物关联和状态，预留在发出请求前持久提交。偏好命令回执按用户及 operation_id 绑定 command_id、参数摘要和预期 revision，按 PREPARED→EXECUTING→APPLIED/CONFLICT/UNKNOWN 核对；控制入口仍须通过 Policy/Executor，禁止伪造 Task/Agent，旧 Task 操作回放保持原协议。以上是后续实现义务，非本次声称已落库或已完成执行链。

## 验证

- `.\.venv\Scripts\python.exe -m pytest tests/test_context_contracts.py tests/test_model_gateway.py tests/test_memory_manage.py tests/test_memory_reader.py tests/test_config.py -q`：38 passed，1 条上游弃用警告。受控 ChatOpenAI HTTP 响应走实际 LangMem 和 Gateway；覆盖输入拒绝、输出上限、维护独立预留及失败重试计数、旧来源解析、现有 Memory/ Gateway 回归。
- `.\.venv\Scripts\python.exe -m pip check`：No broken requirements found。
- `.\.venv\Scripts\python.exe -m ruff check app/context app/runtime/model_gateway.py app/core/config.py tests/test_context_contracts.py docs/v2/v2-02/evidence/v2-02-task211/real-probe.py` 和相同路径 `ruff format --check`：通过（最终测试追加后需以交付前结果为准）。
- `$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe docs/v2/v2-02/evidence/v2-02-task211/real-probe.py`：实际配置模型、单条合成输入、一次摘要，覆盖 `probe-1`，已知 input 19/output 37 tokens。探针采用临时 4096/128 参数和近似计数，仅验证这次调用兼容；它们不证明窗口能力。最初探针导入位置错误未调用模型，修正后成功。过程未输出凭据或摘要正文。

证据见 [results.json](evidence/v2-02-task211/results.json) 与 [real-probe.py](evidence/v2-02-task211/real-probe.py)。未验证维护持久化、文件/PG、重启、摘要质量、真实模型窗口及后续 Graph/偏好控制接线；这些不得以本次测试代替。

物理表规划供后续迁移实现：`context_archive`（会话双身份＋segment 唯一，保存路径及哈希）、`context_summary`（会话双身份＋summary_id 唯一，关联实际 archive 和消息覆盖）、`context_revision`（会话双身份＋revision 唯一，分别保存发布状态和采纳 Checkpoint）、`context_maintenance`（同会话范围/内容哈希/策略唯一，保存工作与预算）、`preference_command_receipt`（user_id＋operation_id 唯一，绑定命令及状态）。关联和发布在事务内核验；表名及物理列落实仍需后续 Task 的迁移与独立验证，本 Task 不创建表。
