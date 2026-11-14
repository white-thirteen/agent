# Task 5.3.2 显式记忆管理实现与自测交付

2026-11-14。依据[当前执行任务](05-memory-manage-execution-task.md)、冻结 D05 第 6/9/10 节及 Task 5.3.2。本文记录 Implementer 实现与实际验证，交主 Agent 审查及独立 QA；不表示 Task/阶段验收。此前 VERIFIED 证据及 05-QA-001 关闭记录保持。

## 实现与关键位置

| 文件 / 入口 | 实现职责 |
| --- | --- |
| `app/memory/models.py:10,29` | strict/extra-forbid 的有限 MemoryCommand、字段/值组合及四态 MemoryMutationResult |
| `app/memory/manager.py:63,97` | 复用安全 snapshot 校验；apply 在固定用户的短锁内公开单 GetOp→比较→单 PutOp；同 Item 保存 revision/preferences/last_mutation |
| `app/graph/specialists/knowledge/memory.py:35,65` | 冻结语法全字符串解析，以及 prepare_memory_command/read_preferences/prepare_memory_write/execute_memory_write/map_memory_result 五节点命令图 |
| `app/graph/nodes/specialist.py:20`、`app/graph/builder.py:19` | 仅 MEMORY_MANAGE 分支从 task_message_ids 定位当前真实 Human，在 wrapper 一次解析并校验模型候选；每次仅调用命令图或原八节点 QA 图 |
| `app/tools/implementations/memory.py:47,56`、`app/tools/policy.py:103` | write_preferences 注册、Schema/固定节点/单工具集合与精确参数复核；handler 只接 typed args 和最小可信业务关联 |
| `app/tools/models.py:56,190`、`app/tools/executor.py:187,627` | 复用原 prepare_attempt/execute_prepared；补明确未开始异常、带领域载荷的 conflict/unknown 适配及源目标工具集合绑定 |
| `app/runtime/run_scope.py:58` | 既有 Scope 内继承故障前可能已消耗的尝试时间，避免新 Scope 丢失原累计工具用量/时间 |
| `app/main.py:115,160,178`、`app/agents/prompts/supervisor.py` | 同一 Manager/Reader 装配、显式工具和命令图接线；Store 命令与 Embedding 就绪独立；Supervisor 仅提出候选 |
| `tests/test_memory_manage.py`、`tests/test_memory_manage_postgres.py` | 有限授权/来源、真实 Store/Saver、故障/重进/预算及精确清理验证 |
| `scripts/verify_05_memory_manage.py`、`README.md` | 显式有限真实 Chat 探针与使用/证据导航；默认 pytest 不调用付费模型 |

写前链路为：原 Task Human→规范命令与 source_message_id→经同 Reader 工具读取真实 revision→稳定 operation/call/digest→同 Executor prepare_attempt（准备零新增 handler）→命令图真实 `durability="sync"` 边界→当前 execute_memory_write context 的 execute_prepared→Manager.apply。wrapper 只对命令图显式要求 sync；原 QA 八节点不变。准备节点同时检查当前框架注入的 Saver/durability 配置，缺失时拒绝写；没有 State 布尔假 sync 或 END 后补快照。固定安装版 LangGraph 的相关配置键已按本地源码核对，未修改框架。

Manager 保留单进程/单 worker 的原前提：锁覆盖真实 Store 调用，不持锁等待模型；没有 Store CAS、跨进程锁或全局事务承诺。相同 op/digest/结果 revision 精确匹配复用；并发旧 revision 和同 op 不同 digest 冲突。delete/clear 去掉偏好值，保留最小版本/幂等元数据，旧写不能复活。仅两项枚举进入安全呈现，sources 始终为空。

进入 Put 后无法确认提交返回领域 unknown；写工具不重试。已知故障重进保留原 call/op/digest/revision，仅用当前 Run 重新准备 `replay_check_only=True`，即使 Store revision 未变也不 Put。核对失败或材料被后来操作覆盖继续 unknown；Policy/预算拒绝核对保留原领域 unknown，同时保存本次零尝试拒绝记录。已保存确定结果复用零 handler；实际进入核对 handler 仍计一次。未知结果公开文案为“本次偏好写入结果未知，请先核对，再提交新的记忆修改。”

没有增加 MemoryWriter、新 Agent、恢复 API/扫描平台、幂等表、迁移或依赖；序列化继续使用现有白名单类型和普通字典，无需放宽 Serializer。未改 `.env`、006、STATE、AGENTS、主协调文档、旧证据及原模型/provider/端点/预算配置；未执行 Git、SSH、重启、Bridge、其他 Agent 或 06。

## 实际验证

全部使用项目 `.venv`，真实 SQL 仅专用 `agent_demo_test / agent_test`。测试开始核验在线身份及 001～006 完整迁移 checksum。UUID 独立用户、conversation/thread、profile 和 operation；finally 精确清理自身行/线程。保护比较覆盖**所有 public 表完整行集和列定义**，包括业务、Saver、知识及他人 profile；没有修改/覆盖 Demo 用户 profile 或订单，没有重新 setup/seed。

1. 首轮受影响回归：

   ```text
   .\.venv\Scripts\python.exe -m pytest tests/test_refund_executor.py tests/test_memory_reader.py tests/test_knowledge_graph.py -q --tb=short
   38 passed in 3.15s
   ```

2. 最终定向真实库验证，通过当前进程注入下述同样的 `AGENT_TEST_DATABASE_URL`，实际执行：

   ```text
   pytest.main(['tests/test_memory_manage.py','tests/test_memory_manage_postgres.py','tests/test_refund_executor.py','-q','--tb=short'])
   9 passed in 8.28s / 0 failed / 0 skipped
   ```

   - 冻结保存/修改/删除/清空/查看及两种删除同义格式；不明确、混合、敏感自由文本、模型候选不符、旧 Human/AI 不授予写权限，零 Store 调用。澄清沿原 Task/预算。
   - 真实命令父/子图使用 AsyncPostgresSaver；A 新 conversation/thread 共享偏好，B 实际 empty；完整新 Python 进程新 Store/池仍能读到相同 revision/偏好。
   - 真实 Saver 的准备快照 `aput` 注入故障：只发生 revision read（tool_calls=1），零 write handler/Put；成功 sync 后 Saver 重载 marker，baseline=1/attempted=2，准备仍为1次。无 Saver 的命令图也拒绝写。
   - 同 Executor 拒绝 model 来源、错节点、缺 scope、缺 allowlist、错参数，零 handler。正常进入 handler 后 Get 故障计一次，failed/not_started/data=None，零 Put。
   - 实际 Manager 并发同 revision 一次 applied、一次 conflict；同 op 精确复用无 Put/更新时间，旧 op 遇后续 clear 冲突、不复活；同 op 不同 digest 冲突。
   - 受控 Put 故障但 revision 未变仍 unknown；原操作 check-only 无 Put。真实 Put 提交后受控丢失回应→unknown→原 op 精确核对 reused，无额外 Put；被后续版本覆盖及核对读取故障仍 unknown。取消原样传播，未伪造持久结果。
   - 新 Run/Scope 继承可能已消耗的原尝试及已保存的累计核对次数；本次核对计一次。Policy 或预算阻断保留原 unknown、零新增 handler，拒绝记录仍可关联；已保存 reused 结果再进入零 handler。
   - **受控 Chat/Retriever + 真实 Store**：真实保存 en 后，正常编译 QA 的 Reader 读取 en，生成提示同时保留当前明确中文要求优先说明；受控中文输出完成来源复核。QA 工具数为3（读偏好、检索、来源复核），模型只绑定 search_knowledge。此项证明接线/预算/提示约束，不冒充真实模型语言质量或真实 Qwen 检索验收。

   首轮测试曾把八条写命令误数为九次，已按实际命令清单修正期望；来源测试初始未完成状态 fixture 被 Runtime 正常拒绝，已补完整终态 fixture。失败轮均执行精确清理与全表保护断言；未改变正确业务预期来绕过失败。

3. **有限真实模型 / 正式 HTTP lifespan / PG Store / PG Saver**：

   ```text
   .\.venv\Scripts\python.exe -m scripts.verify_05_memory_manage --output docs/05-memory-manage-real-chat-evidence.json
   exit 0
   save-en completed
   read-en completed
   delete-en completed
   read-empty completed
   Exact cleanup and complete public rows/columns protection passed
   ```

   [独立 JSON 证据](05-memory-manage-real-chat-evidence.json)记录实际 `deepseek-flash / api.deepseek.com`、安全公共事件、Task/Run/thread、结果与用量。实际4次 Supervisor 模型尝试：保存 en（revision1）→新会话查看确认→删除语言偏好→新会话为空（revision2）；工具累计分别2/1/2/1。当前真实配置 `embedding_enabled=False`，正式 lifespan 的 Store ready、Embedding disabled、knowledge_ready=false，命令全部正常完成，证明资源就绪独立。仅替换测试库及 UUID 演示身份以隔离数据；未覆盖模型/provider/Embedding 开关或预算。

4. **最终完整真实库门禁**，实际命令如下：

   ```powershell
   @'
   import os, pytest
   from app.core.config import Settings
   os.environ['AGENT_TEST_DATABASE_URL']=Settings().test_database_url.get_secret_value()
   raise SystemExit(pytest.main(['-q','--tb=short']))
   '@ | .\.venv\Scripts\python.exe -
   ```

   **216 passed / 0 failed / 0 skipped，100.74秒**。默认 pytest 无付费外部模型请求。依赖未变，未无收益重复 pip check。

5. 最终代码和改动格式检查：

   ```text
   .\.venv\Scripts\python.exe -m ruff check app scripts/verify_05_memory_manage.py tests/test_memory_manage.py tests/test_memory_manage_postgres.py
   All checks passed!
   .\.venv\Scripts\python.exe -m ruff format --check app scripts/verify_05_memory_manage.py tests/test_memory_manage.py tests/test_memory_manage_postgres.py
   96 files already formatted
   ```

## 未闭环与操作边界

**英语偏好保存后，新会话真实 Qwen + Chat + PG 的普通中文知识问题仍未验证。** 现有 `.env` 的 Embedding 开关关闭；主 Agent 转达的明确指令禁止 model/provider/config override，因而没有在测试 Settings 中启用开关、绕过就绪检查或换配置重试。JSON 明确记录 `not_verified_configuration_blocked`。此前 5.2 的 VERIFIED RAG 证据保持，但不能替代本次新增英语呈现组合验收；该缺口交主 Agent 处理。

未知写仍需操作者暂停该 profile 新写，从原 Task 已有 Checkpoint/调用记录定位 op/digest/revision，并确认原调用已结束后只读核对；材料丢失或被后来写覆盖继续 unknown。没有自动崩溃恢复、全局新写阻断或全量历史擦除承诺。真实持久测试使用真实 Store/Saver，故障网络/模型边界使用明确受控注入；未重启 PG/服务，未重跑旧付费场景。

实现会话至此停止，交主 Agent 审查和独立 QA；不自行宣告 Task 或05阶段验收。

## 2026-11-14 续执行：英语偏好与真实 RAG 缺口补验

主 Agent 随后派发同一 Task 的唯一 followup，并澄清[执行任务](05-memory-manage-execution-task.md)的配置边界：禁止覆盖指用户 `.env` 和 Codex 模型/provider/账户配置；验证进程可且必须用自身 `Settings.model_copy(embedding_enabled=True)` 启用原固定 Qwen CPU 与专用测试库。这一澄清撤销了前文对本次验证配置限制的理解；前文“未验证/配置阻塞”和原[命令 JSON](05-memory-manage-real-chat-evidence.json)保持原样，作为当时实施记录。**本节是当前最终补验结论：英语偏好后的真实 Qwen + Chat + PG RAG 样本已通过，原缺口已补齐。**

本次仅新增 `scripts/verify_05_memory_rag.py`、[全新唯一 JSON 证据](05-memory-manage-real-rag-evidence-20261114.json)，追加本报告并修正 README 当前导航；没有修改生产代码、Prompt、用户 `.env`、006、STATE、AGENTS、旧 JSON 或旧已 VERIFIED 证据。

实际命令与结果：

```text
.\.venv\Scripts\python.exe -m scripts.verify_05_memory_rag --output docs/05-memory-manage-real-rag-evidence-20261114.json
exit 0
Unique corpus embedded and committed
save-en completed
knowledge completed
English answer and server-verified sources; three governed tool attempts
Qwen drained; exact cleanup and all public rows/columns preserved

.\.venv\Scripts\python.exe -m ruff check scripts/verify_05_memory_rag.py
All checks passed!
.\.venv\Scripts\python.exe -m ruff format --check scripts/verify_05_memory_rag.py
1 file already formatted
```

验证使用原 `deepseek-flash / api.deepseek.com`、`D:\AI\models\qwen3-embedding-0.6b` CPU / bfloat16 / 2线程 / 1024维，以及 `agent_demo_test / agent_test`、PostgreSQL17.6 / pgvector0.8.7。原 Embedding profile、模型权重 revision、超时和预算均保留，run120秒 / 工具12次 / 单 Embedding8秒；仅验证 Settings 对象启用 Embedding、选择专用测试库及全新 UUID 演示身份。没有更改 Codex 模型/provider/账户或用户配置。

仅两次实际 HTTP：

1. 新 UUID 用户发送“请记住：回答语言=英语”，实际 Store applied/revision1，工具2次、Supervisor模型1次。随后真实 Reader snapshot 确认偏好为 en。
2. 同用户**新 conversation/thread**发送普通中文知识问题：“根据银帆演示指南，普通聊天能批准模拟退款吗？审批应该通过什么入口提交？”问题没有要求中文回复。真实 Qwen 对自有唯一中文指南生成1024维向量并实际提交 PG；检索实际调用1次 Embedding、候选1个。模型产出英语答案，开头为 `No. According to the Yinfan demo guide, ordinary chat cannot approve simulated refunds.`，继而说明须独立本地审批入口、服务端固定演示操作者记录、聊天同意不构成批准。Implementer 将三项陈述逐一对照 JSON 中保存的自有原文，均有依据，没有编造订单/退款执行结果；此为单样本语义核对，不声称通用质量保证。

第二次请求实际完成 `read_preferences / search_knowledge / validate_knowledge_sources` 各1次，总工具数**3**，模型数**4**（Supervisor加专业图3次）。从真实 Saver 的最终子图快照核验 memory_context=en/revision1、三个调用记录均 success/attempts1、来源复核 valid=true；公共来源 document/version/chunk 与本次唯一文档完全一致，`validated_sources` 与公共 sources 相等。答案直接采用经服务器来源验证的 approved_answer，偏好只影响呈现。

测试开始仍核验在线身份、001～006完整 migration checksum，比较所有 public 表**完整行集和列定义**。本次唯一 profile/namespace、知识文档及 chunks、两条 session、两个精确 Saver thread 和临时源文件均在 finally 清理。关停先收敛 Runtime，Qwen 正常排空后释放资源；前后保护快照完全相同。未 seed/setup、未触及原订单/他人 profile、未重启服务或 PG。

此次没有生产变更，按派发要求复用前文最终**216 passed / 0 failed / 0 skipped**完整真实库门禁，不重复全回归或旧付费场景；本次仅增加脚本检查和上述真实组合证据。原 unknown 人工核对、单进程锁、删除保留最小元数据等边界保持。当前无此 Task 已知未闭环实现/补验项；独立 QA 和主 Agent 审查仍待进行，不自行宣布验收或进入下一 Task。实现会话再次停止。
