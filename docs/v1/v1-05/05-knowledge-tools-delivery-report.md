# Task5.2.1 知识工具与八节点子图交付

2026-11-14。仅本 Task 的实现与开发自测交付，等待主 Agent 复核及独立 QA；不代表05阶段验收。依据[执行任务](05-knowledge-tools-execution-task.md)、冻结[D05第5～8节及Task5.2.1](05-rag-memory-detailed-design.md)。前置本地 Qwen CPU/1024维、PG17.6/pgvector及5.1证据原样保留。

## 修改位置及行为

| 文件 | 变化 |
| --- | --- |
| `app/graph/specialists/knowledge/builder.py` | 替换能力骨架为八节点；KnowledgeState私有证据/草稿/调用记录；EvidenceAssessment、AnswerDraft；条件分支、来源复核及结果映射 |
| `app/tools/implementations/knowledge.py` | SearchKnowledgeArgs、来源复核DTO及两项真实Retriever工具；资源缺失注册为disabled |
| `app/tools/policy.py` | 强制KNOWLEDGE/KNOWLEDGE_QA、knowledge:read、模型仅搜索、节点仅validate_sources及完整精确参数约束；沿原工具版本/预算复核 |
| `app/tools/models.py`、`app/tools/executor.py` | ToolUnavailableError携带安全错误码，保留订单默认码；知识故障不再错误标成订单查询不可用 |
| `app/knowledge/models.py` | 既有SearchQuery的top_k允许1..5严格整数，当前图固定3；复用原DTO/Profile/检索实现 |
| `app/graph/contracts.py`、`app/graph/state.py` | SourceReference迁为PublicCitation，使用服务器来源标题/安全逻辑source_key/真实版本与checked_at；拒绝任意URI及额外字段 |
| `app/infrastructure/checkpoint.py` | 显式允许PublicCitation序列化；知识私有State保存JSON原语，不扩大未知类型反序列化权限 |
| `app/main.py` | 在既有生命周期内注册知识工具、注入同Gateway/Registry/Executor/Profile后编译知识图；复用唯一Retriever/模型 |
| `app/runtime/agent_runtime.py`、`app/streaming/events.py` | 最终token事件增加sources白名单；RunView已有来源槽继续使用 |
| `tests/test_knowledge_graph.py` | 受控Chat/检索下的真实图、Policy、消息配对、预算及唯一公开出口验证 |
| `tests/test_knowledge_postgres.py` | 增加真实pgvector/Saver治理链、来源持久化及检索后删除文档拒发草稿；保护完整行集并精确清理 |
| `tests/test_graph_protocol.py` | 用新PublicCitation更新原完成QA/Memory来源边界测试，并保留非法URI/逻辑key拒绝验证 |
| `README.md` | 增加本报告导航 |

## 实现链路及必要限制

严格保留 `check_request → prepare_query → select_retrieval_tool → retrieve_knowledge → assess_evidence → generate_answer → validate_sources → map_result` 八节点。每个节点返回增量；失败/拒答/待补充直接进入map_result。当前Task的Human消息组成规范查询，模型候选entities不替换问题；默认搜索所有公共分类、top_k=3。没有另建查询重写模型或检索循环。Reader尚未实现，memory:read缺失为denied，有scope但资源未就绪为unavailable，memory_context为空；不访问或写入Store。

搜索计划只向Gateway暴露完整search_knowledge Schema。一条原生调用经同Policy/Executor执行，原AIMessage/ParsedToolCall/raw_args及同call_id的ToolMessage保存于专业私有State。可可靠关联的错工具、错参数和多/混合调用全部拒绝并闭合原ID，不选择其中一个执行；原03解析器判为不可可靠关联的批次直接失败，不伪造ID。检索技术故障保留安全码并failed，不变成empty。只将当前Profile/查询指纹及当前来源标记有效的标准SearchResult交证据评估。

空证据直接rejected；非空证据仅一次结构化评估，弱证据/冲突rejected，真正缺问题参数needs_input；充分证据才能生成自然语言AnswerDraft。正文非空且≤2000字符、引用1..5个唯一ID；引用必须同时属于本次真实证据和评估采用集合。文档作为低信任数据进入Human数据区，提示词禁止将其当订单、退款或Memory授权；不以正文连续原文匹配替代生成式回答。

来源复核采用由task/node/tool/version/固定槽/逻辑轮次派生的UUID5 node_call_id，无run_id成分，经同Executor核对当前doc/version/chunk/hash，返回真实checked_at。节点调用不产生ToolMessage。call_records含原call、参数摘要、版本、origin/node、Task/run、execution_id、attempts、安全结果及用量；重进已知记录须通过当前Policy和调用身份检查才复用，同ID内容冲突直接报协议错误。所有实际handler尝试计原RunScope累计工具预算，模型尝试计原Gateway累计模型预算；节点仅采纳当前快照。

成功复核后才创建approved_answer及服务器PublicCitation；伪引用、来源更新/删除或复核故障均不公开草稿。父子transfers、聚合与Response已有显式映射及approved_answer原样输出能力，直接复用，没有重写Supervisor或增加主图自由总结模型。Runtime/SSE只公开最终正文和PublicCitation，不公开证据正文、Profile、向量或工具历史。知识QA不新增恢复协议，继续保持原Runtime仅退款可信恢复边界。

来源有效性不证明正文每句话语义正确。受控反例故意让模型输出“银行卡已经真实扣款成功。”并附合法引用：来源验证可以通过，该正文在人工语义验收中明确失败。该测试用于如实表达能力边界，没有把它作为正确政策答案；真实模型语义质量属于后续5.2.2。

## 实际验证

均使用项目 `.venv/Scripts/python.exe`。没有改.env、Chat/Embedding供应商或配置，没有加载真实大模型。本轮Chat及Embedding受控，SQL、事务、PG向量检索、Saver和来源存在性为真实；不宣称已经完成5.2.2真实Chat/Qwen联调。

1. `-m pytest tests/test_knowledge_graph.py tests/test_graph_protocol.py tests/test_knowledge.py -q`：**65 passed / 0 failed，20.68秒**。
2. 当前Python进程从Settings读取专用test URL，先`validate_test_target(test_url, development_url)`，只在当前进程设置`AGENT_TEST_DATABASE_URL`，随后`pytest.main(['tests/test_knowledge_graph.py','tests/test_knowledge_postgres.py','tests/test_graph_protocol.py','tests/test_tool_governance.py','tests/test_resources.py','-q'])`：**78 passed / 0 failed / 0 skipped，19.15秒**。在线身份核验`agent_demo_test/agent_test`，所有迁移checksum与仓库文件一致。新增真实PG用例创建唯一document_id/thread，成功查询及来源持久化后，第二次调用在草稿生成与复核之间实际删除自身文档，结果为source_changed、无token及sources。最终通过Saver公开adelete_thread精确清理自身thread、remove精确清理自身文档，原业务/迁移/全部Saver/他人知识完整行集一致。
3. 最终完整真实库回归：同上在当前Python进程读取并校验专用test URL、设置`AGENT_TEST_DATABASE_URL`，执行`pytest.main(['-q','--showlocals'])`：**192 passed / 0 failed / 0 skipped，82.99秒，无deselect**。前后通过`protected_snapshot`独立连接核验在线身份、迁移checksum及完整行集，输出`PROTECTED_TABLES_UNCHANGED True CHANGED_TABLE_NAMES []`。在线PG为`17.6 (Debian 17.6-2.pgdg12+1)`、vector`0.8.7`。没有失败业务断言、未削弱原断言或跳过测试。
4. `-m ruff check .`：**All checks passed**。`-m ruff format --check`对15个改动Python文件：**15 files already formatted**。初次检查发现新写文件字符串长度和导入排序问题，已修正后通过；没有修改Ruff规则。

完整门禁在执行前后独立核验在线test身份、迁移checksum及上述11张保护表的完整排序行集；只输出行数/摘要，不输出记录或凭据。保留的原始保护摘要如下，前后相同：

| 表 | 行数 | SHA256（排序行集JSON） |
| --- | ---: | --- |
| demo_orders | 5 | `6e6a1011e1e60ce46ae1cc056e17ff51206c7bfbab1122d03d47b7945ba6e974` |
| schema_migrations | 6 | `649ac91aa2fd0dc3a6d52ca0da3520c3019e45a04d859329651717a4388e3260` |
| checkpoint_migrations | 10 | `828aec8ae7e34ba34051d970e5adeaa4e8ad8d13f28ab90dc546664cc2afb09b` |
| sessions、refund_requests、approvals、checkpoints、checkpoint_blobs、checkpoint_writes、knowledge_documents、knowledge_chunks | 各0 | 各`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |

006原字节SHA256仍为`5427fa3648c5bd0e15d46b8961314351055aae849582e55825a2ea093ffc4ea3`。依赖未变，未重复pip check。未新增seed或清理他人数据；全回归既有seed幂等测试沿任务明确窄例外执行。

## 未闭环与交接

本Task实现与开发自测无剩余阻塞；独立QA尚未执行，交主Agent派发。5.2.2真实RAG语义及模型组合验证、5.3共享Reader/Store/Memory未进入本Task。没有Git、SSH、数据库结构变更/重启、其他Agent派发或Session Bridge操作；原有工作区变更及旧证据保留。
