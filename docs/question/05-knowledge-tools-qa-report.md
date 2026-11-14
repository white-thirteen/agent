# Task5.2.1 独立 QA 报告

2026-11-14。结论：**PASS，仅 Task5.2.1**。没有发现需登记为 05-QA-001 的问题；无本 Task 未关闭阻塞。不代表5.2.2真实模型语义验收、05阶段 ACCEPTED 或 Git 归档许可。

依据：根 AGENTS.md、[当前状态](../STATE.md)、[执行任务](../05-knowledge-tools-execution-task.md)、[独立QA任务](05-knowledge-tools-qa-task.md)、冻结D05第5～8节及5.2.1、[Implementer交付报告](../05-knowledge-tools-delivery-report.md)。执行者为原生任务 `/root/qa521`，当前收到QA角色指令；本会话工具没有直接暴露自身运行时UUID，故不填造UUID。角色配置文件内容不能替代运行时角色元数据，后者由主Agent核验。

## 检查结论与源码位置

| 检查项 | 位置与独立证据 | 结果 |
| --- | --- | --- |
| 八节点、身份与任务关联、字段重置 | `app/graph/specialists/knowledge/builder.py:184`及末尾拓扑；`transfers.py`与`nodes/specialist.py`显式输入输出映射。当前Task Human形成查询，模型entities不替代问题；子图私有证据不并入父State | PASS |
| 原生调用、参数与权限边界 | builder第242/279行，`app/tools/policy.py:9`、`implementations/knowledge.py:41`。模型只获search完整Schema；search当前query/domain/top_k须精确匹配，来源工具仅固定node-origin、KNOWLEDGE_QA、scope和版本允许；错误及多/混合调用零handler并按可靠原ID闭合 | PASS |
| 调用记录与预算 | builder第114/378行。固定槽UUID5不含run_id，保留原call/result/execution_id/版本/摘要与Task/run。既有用例验证同调用复用不重复计数；独立追加撤销权限与摘要冲突检查均在handler前拒绝 | PASS |
| 空弱冲突、故障、草稿隔离 | builder第318/355/438行。真实空证据拒答、评估一次；弱/冲突拒答，缺参needs_input；技术故障与预算failed。伪造、重复、空白草稿或失效引用无公开答案/来源 | PASS |
| 当前来源复核与唯一公开出口 | builder第378行、`knowledge/repository.py`、`contracts.py:102`、result_aggregator/response、Runtime及streaming白名单。来源经同Executor查当前version/chunk/hash，服务器生成PublicCitation及checked_at；主图原样输出approved_answer，公共数据无证据全文/Profile/调用记录 | PASS |
| 真PG、事务、Saver兼容 | 独立执行两项PG测试：真实精确余弦、发布回滚/更新/删除、完整RAG链及检索后删除拒发草稿。另用新连接池和新Saver读取真实父/子Checkpoint，类型与公开出口均正确 | PASS |
| Reader未就绪与资源缺失 | Reader明确denied/unavailable，memory_context为空；独立验证缺失资源failed/capability_unavailable、空白问题needs_input且零模型/工具次数 | PASS |

没有将文档注入提示当作权限来源。源码和受控恶意文档测试共同确认：评估/生成不绑定业务工具，模型不能将来源复核、订单写或Store写加入当前允许集合。未实现通用语义安全证明。

## 本轮实际执行

均使用项目 `.venv/Scripts/python.exe`，没有改业务代码、既有测试、配置、依赖或旧证据。

1. **独立定向回归：78 passed / 0 failed / 0 skipped，18.38秒。** 当前Python进程从Settings读取test URL，先调用`validate_test_target(test_url, development_url)`，仅在该进程向既有测试提供`AGENT_TEST_DATABASE_URL`，执行：

   ```python
   pytest.main([
       'tests/test_knowledge_graph.py', 'tests/test_knowledge_postgres.py',
       'tests/test_graph_protocol.py', 'tests/test_tool_governance.py',
       'tests/test_resources.py', '-q',
   ])
   ```

   外层通过项目`scripts.run_async`与真实连接在pytest前后各取一次`protected_snapshot`，逐表比较完整排序行集，结果`QA_PROTECTED_TABLES_UNCHANGED True`。测试包括真实SQL/pgvector/Saver；Chat与Embedding为受控替身，没有把替身称为真实模型验收。

2. **独立追加五组行为探针：全部通过，脚本exit 0。** 在独立Python进程直接调用实际图/节点/Runtime及Saver，复用测试资源构造器，但断言由QA另行编写：
   - 已成功的validate_sources节点再次调用，移除knowledge:read，返回failed/tool_not_allowed；验证handler仍仅执行一次，tool_calls不增加。
   - 将已保存调用的args_digest改为不同值，同一node_call_id重进抛GraphProtocolError，未执行handler。
   - 当前可信Human仅空白：needs_input，零模型尝试/工具次数。
   - 未注入资源的知识图：failed/capability_unavailable，无伪成功。
   - 独立唯一`qa521-<uuid>`线程运行真实父子图并写入PG Saver；关闭原Checkpoint连接池，重新打开池并新建AsyncPostgresSaver（均使用正式checkpoint_serializer）。`aget_tuple`恢复的来源是PublicCitation，JSON与RunView一致，SpecialistResult保留原approved_answer，父State无call_records/evidence/draft；`alist`实际读到两个namespace及包含SpecialistInput/调用JSON记录的子Checkpoint。通过公开`adelete_thread`精确清理自身线程，前后11张完整行集相同，输出`QA_EXTRA_PROTECTED_TABLES_UNCHANGED True`。本探针的检索替身用于隔离序列化风险，真实SQL检索由第1项单独验证；没有把它算作真实RAG质量证据。
3. **独立Ruff：** `python -m ruff check .`，exit 0，All checks passed。
4. **完整门禁来源：** Implementer最终交付报告记录192 passed / 0 failed / 0 skipped（82.99秒，无deselect）、15个改动Python文件format检查通过、全库Ruff通过。QA引用该完整门禁，未无收益重跑完整套件；QA自身执行结果以本节78项及追加探针为准。依赖未变，未重复pip check。

首个QA外层包装脚本误用了Windows默认`asyncio.run`，在取前置快照时连接初始化失败，pytest未开始。查阅项目`scripts.run_async`后改用其SelectorEventLoop再执行，连接与上述验证均正常。该次为QA脚本运行方式错误，不计业务失败或通过，未写数据库。

## 环境、隔离与清理

两轮真实库操作均先验证在线身份为`agent_demo_test / agent_test`，PG `17.6 (Debian 17.6-2.pgdg12+1)`，vector `0.8.7`；完整迁移版本/checksum字典与仓库migration_files相同。006文件独立SHA256为`5427fa3648c5bd0e15d46b8961314351055aae849582e55825a2ea093ffc4ea3`，未改字节。

保护表为sessions、demo_orders、refund_requests、approvals、schema_migrations、checkpoints、checkpoint_blobs、checkpoint_writes、checkpoint_migrations、knowledge_documents、knowledge_chunks。独立前后完整行集相同；原5订单及他人业务/知识/Saver数据均保持。初始及清理后：demo_orders=5，schema_migrations=6，checkpoint_migrations=10，其余8表各0行。

| 非空保护表 | 前后相同的排序行集SHA256 |
| --- | --- |
| demo_orders | `6e6a1011e1e60ce46ae1cc056e17ff51206c7bfbab1122d03d47b7945ba6e974` |
| schema_migrations | `649ac91aa2fd0dc3a6d52ca0da3520c3019e45a04d859329651717a4388e3260` |
| checkpoint_migrations | `828aec8ae7e34ba34051d970e5adeaa4e8ad8d13f28ab90dc546664cc2afb09b` |

空表各为`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`。不输出行内容、连接串或凭据。知识PG用例仅使用唯一document/thread及精确清理；未运行seed、修改结构、SSH、重启、Git、Bridge或另派Agent。只读为行为约束，并非额外沙盒隔离。

## 实质风险与未验证范围

- 合法且当前的来源不能证明正文逐句语义正确。独立执行的受控反例仍可让“银行卡已经真实扣款成功。”附合法来源通过程序来源验证，但人工语义验收失败；这是冻结设计明确要求保留的5.2.2验证风险，本Task不擅增原文匹配或固定答案替代生成。
- 本轮没有调用真实Chat/Qwen组合、启动HTTP服务或进行跨进程/数据库重启。新连接池/Saver验证证明真实持久化解码，不能等同进程重启恢复或5.2.2真实语义验收；原5.1真实Qwen证据可按任务复用。
- 来源只表达checked_at时刻的可用性；其后仍可能更新。Knowledge恢复入口继续沿既有仅退款可信恢复边界，不宣称任意知识故障可自动续跑。
- 5.3 Reader/Store/Memory尚未进入本Task。本报告不推进下一Task；交主Agent复核与裁决。
