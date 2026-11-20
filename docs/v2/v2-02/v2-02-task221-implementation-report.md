# V2 02 Task 2.2.1 实施记录

本记录交主 Agent 审查及独立 QA，不代表 Task 或阶段验收。未启动 2.2.2/2.3、未修改冻结设计、正式数据库或 `.env`，未提交或推送。

## 实现

- `app/context/compaction.py` 固定 `context-summary-v1` 项目摘要 Prompt：主题、明确需求与否定约束、完成/未完成、必要标识、冲突和不确定性；历史与上次摘要作为低信任数据，禁止执行其中的指令或应用偏好。实际 LangMem 输入预检与覆盖检查保留，拒绝带工具调用的 AI 消息；Prompt 版本纳入输入哈希。输出上限经 Gateway 绑定模型请求。`summarize_for_run` 接受可信 RunScope、正式 Run/Task 上下文及 normal 模式，沿用剩余期限和累计 model_usage；请求前更新 scope，故调用中断也不会退回已用尝试。返回成功调用用量，失败继续携带 Gateway/CompactionError 用量。
- `app/context/manager.py` 从同用户/会话 READY Archive 逐段核验文件、消息和父摘要，构造输入哈希和独立范围哈希；运行内及任务后维护共用摘要组件，但所有者和预算分离。摘要内容及实际消息/Archive/父摘要关联以项目 Summary 契约存储；根据范围、输入哈希、来源和策略/模型/Prompt 版本复用 READY Summary。Summary ID 恢复通过服务端身份查询转为受限 archive refs，再逐段验权、验路径和哈希。模型配置须显式提供窗口与输出限额，输入加输出不得超过配置，模型名须一致。
- `app/context/repository.py`、`migrations/009_context_compaction.sql` 保存 Summary、维护工作和逐尝试记录。按用户/会话、消息范围内容哈希和策略复用工作；不同 maintenance_id、Summary 版本或来源 Run 不重置预算。注册时数据库固定 30 秒截止，持久 claim 保证同一工作只允许一个摘要执行者，竞争方获得 in-progress；每次调用前单独原子预留 attempt_id，回执按 attempt_id 和 claim 精确关联并幂等登记。已预留未返回的记录保持 unknown；核实旧执行者已不在且获得会话独占权后，`interrupt_maintenance` 可标记中断并保留剩余额度，耗尽或截止后禁止继续。模型调用期间不持数据库事务。Summary 保存时事务内核对 READY Archive、精确消息序列及父子覆盖，维护完成还核对同来源和关联。尚未做 Graph/Runtime 装配，调用方负责可信来源与会话执行/维护互斥，不能在仍有活跃执行者时调用中断恢复。
- `app/runtime/model_gateway.py` 维护预算协议返回 attempt_id 并用它登记回执；Task 调用可从 RunScope 传递截止期限和尝试登记回调。`app/infrastructure/postgres.py` 版本门禁随新增 009 更新为 9。正式库尚未应用，正式部署需单独迁移授权。

## 实际验证

- ` .\.venv\Scripts\python.exe docs/v2/v2-02/evidence/local-pg-launcher.py pytest tests/test_context_compaction_postgres.py tests/test_context_contracts.py tests/test_model_gateway.py tests/test_context_archive.py tests/test_config.py -q --tb=short`：**28 passed，1 条 trustcall 上游弃用警告**。真实本机 PostgreSQL 17.12 隔离专库、真实 LangMem、真实临时 Archive 文件、受控模型；数据库预检 host/port、数据库、角色、版本与共享 comment。测试在唯一 `ctx221_…` schema 执行 008/009，finally 精确删除并核验不存在。覆盖模型失败后 READY Archive 保留、同工作不同 ID 重试、未知用量、成功摘要复用、覆盖错误拒绝、父摘要增量、运行内预算、同时预留最多两次且回执不串号、相同工作并发入口仅一次模型调用、已保存摘要/完成回执失败后的恢复、跨进程中断恢复、截止与 EXHAUSTED、无配置及越限拒绝。新进程中断为受控故障，未模拟机器断电或正在真实网络调用时杀进程。
- ` .\.venv\Scripts\python.exe -m ruff check app/context app/runtime/model_gateway.py app/infrastructure/postgres.py tests/test_context_contracts.py tests/test_context_compaction_postgres.py tests/context_compaction_restart_probe.py docs/v2/v2-02/evidence/v2-02-task221/real_probe.py`：通过；这些 Python 文件已运行 Ruff format。
- ` .\.venv\Scripts\python.exe docs/v2/v2-02/evidence/local-pg-launcher.py module docs.v2.v2-02.evidence.v2-02-task221.real_probe`：真实 `model_resources(Settings(...))`、DeepSeek 配置模型、LangMem、Gateway、专用 PG 与文件的单次小合成输入通过；最终 [回执](evidence/v2-02-task221/real_probe_receipt_r4.json) 记录 1 次、known input 78/output 42、覆盖 2 条，Archive READY、维护 SUCCEEDED，唯一 schema 清理核验成功。探针临时设置窗口 4224、输入预算 4096、输出上限 128，计数器为近似计数；并非模型能力上限或摘要质量结论。供应商声明窗口 1048576、最大输出 393216 的只读能力回执见 [model-capability-receipt](evidence/model-capability-receipt.json)，不把能力最大值当推荐摘要长度。前 3 次合成探针回执保留于同目录。
- 首次受控 PG 集成运行曾因 PostgreSQL 无法推断 NULL 参数类型而失败（1 failed、19 passed）；完成显式类型修正后上述最终定向测试通过。没有掩盖这次失败。

## 尚未闭环

Graph 安全边界与 Revision 发布/采纳、Checkpointer 恢复及 Runtime 互斥接线归后续 Task；本组件只暴露入口，不写 Saver 或裁剪消息。真实断电/真实在途进程终止、冻结质量夹具、摘要保真与资源收益尚未验证；小合成调用只证明本次集成兼容。未运行完整阶段回归。工作区既有改动保留。
