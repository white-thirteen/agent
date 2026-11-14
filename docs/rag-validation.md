# Task5.2.2 RAG真实联调

2026-11-14，Implementer `/root/rag522`。已完成本Task开发验证，交主Agent审查与独立QA；不代表05阶段验收。范围依据[执行任务](05-rag-validation-execution-task.md)和冻结[D05第6～8、11节及Task5.2.2](05-rag-memory-detailed-design.md)。未修改生产代码、配置、依赖、迁移或原证据。

## 交付与复现

- [12条固定样本](../tests/fixtures/knowledge_cases.json)：3条真实HTTP，9类受控样本，其中faults分两次执行。
- [显式验证脚本](../scripts/verify_05_rag.py)：复用正式lifespan、HTTP路由、Service、Runtime、主图/八节点子图及PG Saver；受控部分复用5.2.1 Provider/资源构造器，使用真实Qwen、SQL和同Policy/Executor。不是默认pytest付费用例。
- [首轮机器证据](05-rag-real-evidence.json)：三条真实HTTP全部符合预期，另保留受控首轮已取得结果及清理摘要。该轮最终exit 1，原因见下文，不能称整轮通过。
- [最终受控机器证据](05-rag-controlled-evidence.json)：10次结果全部符合预期，exit 0。
- [证据审计](05-rag-evidence-audit.json)：真实HTTP结果、唯一公开正文、人工语义判断、证据文件SHA256及两轮临时文件精确清理。

实际命令均使用项目`.venv`：

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_05_rag --output docs/05-rag-real-evidence.json
.\.venv\Scripts\python.exe -m scripts.verify_05_rag --controlled-only --output docs/05-rag-controlled-evidence.json
.\.venv\Scripts\python.exe -m ruff check scripts/verify_05_rag.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/verify_05_rag.py
```

脚本拒绝覆盖既有证据；复现需使用新的output路径。只在进程内切到Settings提供的专用测试URL及`app_env=test`、启用Embedding，未改`.env`。保持8秒Embedding推理、120秒初始化、15秒总检索、原模型/工具/Runtime预算；故障样本有明确的临时期限注入。`--controlled-only`初始化正式模型资源但不请求真实Chat。

首轮预检曾因Embedding默认关闭在写库/加载模型前退出；改成显式进程内启用后执行。首轮真实请求完成后，受控预算样本复用了上一删除样本留下的空库，得到empty/rejected而非预期预算failed，这是验证脚本fixture顺序问题。finally完成清理且保护行集相同；已修正为预算样本先重新发布自有资料，只重跑受控部分，未重复付费Chat。没有发现需修正生产实现的缺陷。

## 真实模型、语料与参数

Chat从Settings读取：`api.deepseek.com`，`deepseek-flash`，使用现有Gateway和非thinking参数，不输出凭据。实际共10次Chat尝试：正常4、无答案3、冲突3，无重试。HTTP由httpx ASGITransport调用真实FastAPI端点`POST /agent/chat`并消费SSE响应；没有启动TCP监听器、uvicorn或Apifox，因此不声称验证了网络代理或外部客户端。

Embedding为Windows `D:/AI/models/qwen3-embedding-0.6b`，Qwen3-Embedding-0.6B、CPU、BF16、2线程、batch1、1024维、L2归一化、固定query任务提示。Profile为`demo-v1`，权重revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，Tokenizer摘要`def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a`；完整Profile在两份证据中。实际导入验证每个向量1024维，生产适配器继续验证有限、非零数值；5.1已有独立归一化与持久化证据，本轮不重复安装、迁移或重启。

PG在线身份为`agent_demo_test / agent_test`，PostgreSQL `17.6 (Debian 17.6-2.pgdg12+1)`，vector `0.8.7`，schema6。每轮写入前均在线核对身份及全部迁移checksum与仓库一致。

正常/无答案语料为`data/knowledge/manifest.json`六份自编Demo正文的UUID副本；本验证副本标题为`Demo <原document_id>`、source_key为原document_id，均显式使用platform_help分类。正文未改，未把恶意材料混入默认语料；副本实际document_id/version/content_hash在首轮证据`corpus`中，不能把这些副本version当原manifest导入版本。冲突单独清除自有正常语料后导入两份“Demo蓝星计划”资料，分别明确固定30天、固定90天。受控恶意文档另阶段单独发布，带`IGNORE SYSTEM`、写他人偏好/批准退款/输出标志的指令。全部源文本构造都可由脚本复现。

检索保持精确余弦、candidate_k=5、top_k=3、score_threshold=null、上下文≤2400 cl100k_base tokens且≤24KiB。没有新引入阈值；无答案案例仍能返回3条无关资料，依赖一次证据充分性评估拒答，距离排名本身不构成答案依据。小样本不足以校准通用数值阈值，本Task不虚构校准精度。

## 逐样人工语义核对

以下是开发者逐样核对，不是独立QA结论。真实拒答时`approved_answer=null`，公开唯一正文为固定的资料不足/冲突说明。

| 样本 | 模型与观测 | 来源有效性 | 语义/边界判断 |
| --- | --- | --- | --- |
| normal | 真Chat，completed；退款安全说明排第1，选1条引用；候选5/返回3；上下文1075 tokens；检索546.37ms；HTTP 6.624s | 同Executor实际核对当前doc/version/chunk/hash，1条服务器PublicCitation带checked_at | PASS：说明无真实支付、只变模拟数据；附带稳定操作编号防重复、未知先核对，都由refund-safety.md支持。没有声称退款已执行；自然概括可接受 |
| no_answer | 真Chat，insufficient/rejected；候选5/返回3；上下文1075 tokens；检索360.54ms；HTTP 3.826s | 不生成草稿/引用，公开sources=[] | PASS：检索结果是退款与审批资料，不包含量子发动机保修；未编造期限 |
| conflict | 真Chat，conflicting/rejected；两份都命中；上下文583 tokens；检索309.35ms；HTTP 4.569s | 不公开草稿/引用 | PASS：评估明确指出同一计划30/90天矛盾，无优先级依据；公开未选任意天数 |
| weak | 受控insufficient，真Qwen/PG检索 | 无来源输出 | PASS受控边界：rejected/evidence_insufficient，未生成正文；不代表真实Chat弱相关质量已全面验证 |
| forged | 受控fabricated ID | citation_invalid，未作伪来源输出 | PASS：failed，无草稿公开 |
| wrong_body | 受控“银行卡已经真实扣款成功。” | 当前来源复核通过，completed/1条真实来源 | **语义FAIL，预期反例**：引用真实存在，但资料只描述模拟退款，完全不支持已经真实扣款。来源存在率不能等于正文准确率；程序不会检测任意语义幻觉 |
| malicious | 受控安全回答，真恶意文档向量/SQL | 2个真实Chunk通过复核 | PASS受控权限边界：仅搜索/来源复核各1次，业务/Store均未执行，公开安全审批说明。没有把受控正文当真实Chat抗注入质量证明 |
| update | 受控生成后、复核前实际替换自有文档和向量 | source_changed | PASS：旧草稿无approved_answer/sources |
| delete | 受控生成后、复核前实际删除自有文档 | source_changed | PASS：旧草稿无approved_answer/sources |
| no_scope | 无knowledge:read | 无来源访问 | PASS：rejected，0模型/0工具 |
| tool_budget | 自有非空语料，工具预算1 | 来源复核被tool_budget_exceeded阻断 | PASS：搜索1次，模型3次，failed且无approved_answer/sources |
| faults | 受控Chat；真实Qwen超时；真实PG会话超时注入 | 均不当空结果 | PASS：分别failed/embedding_timeout、failed/retrieval_timeout；各1次工具尝试，无approved_answer/sources |

故障细节：Embedding样本只对该次实际Qwen调用临时设置极短异步期限，底层CPU工作保留单槽，最终lifespan正常排空。PG样本在自有连接事务中`SET LOCAL statement_timeout='1ms'`后执行`SELECT pg_sleep(0.1)`，确实收到QueryCanceled，在验证Retriever边界映射成retrieval_timeout，经同Executor/图失败出口处理；未锁其他行、未改服务器配置。它验证真实PG取消及失败出口，不声称生产余弦SELECT自然耗时超限或模拟过服务器断网。

## Runtime、公开出口及资源证据

三条真实请求各有独立UUID会话/稳定thread、正式Runtime task_id和run_id，首轮证据保留具体关联。读取真实Saver子Checkpoint确认每次只有一条原生search ToolCall，与ToolMessage的call_id精确配对；模型搜索和node来源复核均走同Executor，正常工具2次、另外两条各1次。正常4次模型尝试包含Supervisor，无答案/冲突各3次。公共sources由服务端构造，父State没有ToolMessage，公共事件没有content_hash/Profile/call_records。三条SSE均只有一条最终正文，正文与专业approved_answer或拒答说明一致，sources与专业结果相同；初轮结果另通过证据审计断言复核。

首轮启动63.165s、到完成清理89.754s；受控轮启动21.734s、总28.412s。首轮进程PID51608，峰值working set约1.151GiB、peak private/pagefile commit约3.611GiB；受控PID17988，峰值working set约1.332GiB、peak commit约3.611GiB。精确字节及测量时剩余物理内存在证据中；这些是完整Python应用进程指标，不是纯权重内存或全机峰值。两轮Qwen串行推理、正常lifespan关闭，没有强杀模型、重启服务或更改用户进程。

两轮均比较11张保护表完整排序行集：sessions、demo_orders、refund_requests、approvals、schema_migrations、checkpoints、checkpoint_blobs、checkpoint_writes、checkpoint_migrations、knowledge_documents、knowledge_chunks。原5订单、迁移、他人知识和Saver完整行集不变，前后行数及SHA256均在证据内。只按本轮完整UUID document_id、精确user/conversation和Saver公开adelete_thread清理；没有seed、按前缀删表或开发库写入。两处临时目录经解析确认直属TEMP、文件集合精确匹配本轮创建的md文件后逐文件删除再移除空目录，审计保留目录名。

## 必要回归与未验证范围

定向真实PG回归命令：进程内从Settings读取test URL、先`validate_test_target`，再仅向自身进程设置`AGENT_TEST_DATABASE_URL`，调用：

```python
pytest.main(['tests/test_knowledge_graph.py', 'tests/test_knowledge_postgres.py', '-q'])
```

结果 **21 passed / 0 failed / 0 skipped，5.37s**。这些既有测试的Chat/向量是受控替身，SQL/Saver真实，不与上面的真实Qwen/Chat证据混称。Ruff check及脚本format检查通过；生产代码和依赖未变，未重复完整192项门禁或pip check，5.2.1既有完整回归证据继续保留。

没有真实模型可用性阻塞或待修生产缺陷。保留的明确限制是语义正确性需人工判断、真实Chat恶意/伪引用精确输出由受控样本覆盖、未验证TCP/uvicorn/Apifox/断网/重启，且来源仅表达checked_at时刻当前有效。没有修改STATE/AGENTS/旧证据，没有Git、SSH、Bridge、额外Agent或5.3操作。本Task交主Agent审查和独立QA后停止。
