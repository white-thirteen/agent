# V2 02 Task 2.1.2 独立 QA

结论：**PASS**。当前范围无发现需修复的编号问题；本结论不代表 V2 02 阶段验收。

审查了冻结设计、实现报告、验证矩阵、归档组件、迁移、配置、版本门禁及原测试。实现按可信输入选择已结束任务的连续公开历史；近期、活动或不完整任务受保护，身份以用户和会话双列限定，读取校验路径、状态、消息范围及哈希；失败不操作 Checkpoint 或裁剪热消息。摘要可信解析、Revision 和 Graph 接线属于后续 Task，未据此判定缺陷。

实际验证（项目 `.venv`；独立测试库预检 host、port、数据库、角色、PG 版本与共享 comment；未连接正式库）：

- 同进程以 `psycopg.conninfo.make_conninfo` 构造测试 DSN、Windows Selector 事件循环，执行 `pytest tests/test_context_archive.py tests/test_context_archive_postgres.py tests/test_context_contracts.py tests/test_config.py -q`：**21 passed，1 上游弃用警告**。真实 PG 用例包括迁移、文件发布后注入 READY 失败及重试、身份过滤和原文恢复。
- 独立真实 PG 探针：两线程、各自事件循环和连接池，以屏障使两个首次发布者进入文件发布竞争；结果均返回相同 READY 记录，数据库仅一条记录。采用唯一 `ctx212_` schema，finally 删除并核验不存在，临时文件目录自动清理。
- 独立真实 PG 探针：同一 Task 跨两个 Segment 时两个相关结果排序优先；消息 ID 精确锚点命中；同用户另一会话不能取到记录。唯一 schema 在 finally 删除并核验不存在。
- `python -m ruff check app/context tests/test_context_archive.py tests/test_context_archive_postgres.py app/core/config.py app/infrastructure/postgres.py`：通过。

遗留边界：READY 故障为受控注入，未模拟真实断电或 OS 崩溃，文件、PG 与 Checkpoint 之间不承诺原子性。可信历史来源、真实 Checkpoint 与 Graph 采纳尚待后续 Task 验证。当前代码版本门禁为 schema 8，正式库未迁移，部署前需专项授权；本次未以新代码启动正式环境或操作正式库。

独立探针证据：首次并发发布 [源码](../evidence/v2-02-task212-qa/first-publication.py)、[原始输出](../evidence/v2-02-task212-qa/first-publication.out)；跨 Segment 锚点 [源码](../evidence/v2-02-task212-qa/anchor-recovery.py)、[原始输出](../evidence/v2-02-task212-qa/anchor-recovery.out)。探针源码和输出依据已执行工具调用及其返回内容归档，本次证据补充未重新运行测试。
