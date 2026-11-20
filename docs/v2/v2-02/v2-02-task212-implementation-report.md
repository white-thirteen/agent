# V2 02 Task 2.1.2 实施记录

当前为实现与自测交付，待独立 QA；不代表阶段验收。未连接或修改正式数据库，也未修改 Checkpoint、Graph 或热消息。

- `app/context/models.py` 定义受信调用方提供的公开消息及完整交互；`manager.py` 从已完成/拒绝的可信 Task 选择连续前缀，保护近期和不完整 Task，并按交互与消息数限制；当前无 Graph 接线，调用方必须从可信 Checkpoint/Task 元数据构建输入，缺乏可靠关联时不得构造或猜测。
- `archive_store.py` 以消息 ID 序列生成确定性 Segment；Markdown JSON 单行转义正文，保留 Unicode、控制字符和原文，伪造标题无法成为元数据。身份与路径均由服务端生成，读取核验身份、路径、格式、消息范围和哈希。临时文件同目录刷新后硬链接原子发布，已存在时比对，禁止覆盖；每次 READY 前读回核验。
- `repository.py` 和新增 `008_context_archive.sql` 保存独立用户/会话、消息和 Task 关联、来源、哈希、文件与发布状态。先登记 PREPARING，再发布文件和提交 READY；文件已发布但数据库失败时重试复用，已 READY 文件缺失或损坏时拒绝使用。无跨文件/数据库/Checkpoint 原子性宣称。
- 恢复支持可信方提供已验证 Summary 的 archive_refs、Task/消息锚点及近期候选，候选、总字节及计数器提供的 Token 值有界，最多扩展一次前邻；按 Segment 整体返回和消息 ID 去重，不截断交互。Summary 持久化及 Summary ID 的可信解析属于 2.2.1；本 Task 不虚构该关系。Token 精度取决于调用方计数器。
- 根目录、消息数、近期保留量及读取上限集中配置于 `app/core/config.py` 和 `.env.example`；目前仅提供组件，尚未装配后台维护、调用模型或 Graph 采纳。

## 实际验证

- `.\.venv\Scripts\python.exe -m pytest tests/test_context_archive.py tests/test_context_contracts.py tests/test_config.py -q`：19 passed，1 条上游弃用警告。受控 Repository、真实临时文件，覆盖写文件后数据库提交失败重试、幂等与内容冲突、跨身份拒绝、路径逃逸、哈希损坏、完整原文和字节/Token 上限。
- 随后调整 Markdown 编码后，`.\.venv\Scripts\python.exe -m pytest tests/test_context_archive.py -q`：3 passed（追加候选数、单次邻接扩展与整段 Token 限额用例）。
- `.\.venv\Scripts\python.exe -m ruff check app/context tests/test_context_archive.py app/core/config.py`：通过。
- 新增 `tests/test_context_archive_postgres.py` 作为专用隔离库探针，仅允许 `agent_context_test`，在随机 `ctx212_...` schema 内运行 008 并精确清理。本机隔离 PostgreSQL 17.12（数据库/用户/版本/共享 comment 标记和 loopback 均预检）运行该探针：1 passed。实际执行 008、PREPARING 后文件发布及模拟 READY 提交失败恢复、重复并发读取发布、身份过滤、候选锚点与文件恢复；finally 精确删除自有 schema 并核验不存在。原预检误用 obj_description 导致断言中止、未写库，改用共享对象 shobj_description 后通过。真实 PG 故障为受控注入，并非真实断电或进程崩溃。

未验证同时首次发布冲突或实际进程崩溃/机器断电；不宣称文件系统与数据库跨资源原子。真实 Checkpoint/Graph、安全状态来源及后续 Summary/Revision 接线仍属后续任务。

根据主 Agent 裁决，`app/infrastructure/postgres.py` 的版本门禁更新为 8，与新迁移一致。正式数据库尚未迁移，禁止以新代码在正式环境启动；部署前须获得正式迁移专项授权。
