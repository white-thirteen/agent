# 05 本地 Qwen / pgvector 独立 QA 报告

2026-11-13。结论：**PASS，仅限当前本地 Embedding 与真实检索工作单元**。无已确认的 05-QA 阻塞问题，不代表 05 全阶段完成或用户验收。

依据为根 AGENTS、[QA Task](05-local-embedding-qa-task.md)、[执行任务](../05-local-embedding-execution-task.md)、D05 第4～5节、实际源码、[交付报告](../05-local-embedding-delivery-report.md)及资源证据。QA 没有修改业务代码、既有测试、配置、迁移或协调文档，没有 Git、Bridge、SSH、数据库重启及子 Agent 操作。

## 独立源码检查

- `app/knowledge/embedding.py:52/87/104/123/161`：复用 LangChain Embeddings，纯本地 CPU SentenceTransformer，Query 有任务提示而 Document 无提示；实际 tokenizer 连同提示及特殊 token 预检，超限拒绝而非截断。输出校验完整1024维、有限、非零；encode 开启 L2 归一化。Profile包含固定权重 revision、tokenizer 内容摘要、dtype、归一化及完整提示。没有随机或 Mock 向量回退。
- 单实例/单工作线程与 `_busy` 锁限制推理并发；异步调用以 shield 等待工作 future，超时及取消不会取消底层内核或释放槽位。future 真正完成才清除 busy；关闭先标记 closed，将模型释放排在内核后，再在线程外等待 executor 关闭。初始化、推理及释放均在工作线程，生命周期失败对外标为 unavailable。默认关闭时无需大模型或 tokenizer 资产即可启动。
- `chunking.py:70`、`ingest.py`、`repository.py:32`：受控本地 md/txt、路径及数量/大小/输入预算，稳定版本与真实行号，Unicode完整分片；完整同版本跳过推理/写入。每文档事务加 advisory lock，删旧 Chunk、改文档、写新 Chunk 同事务完成；Embedding 在事务外。remove 精确指定 document_id。
- `retriever.py:17/52`、`models.py:69`、`repository.py:109/140`：scope先于Embedding检查，身份为可信 keyword 参数，搜索DTO禁止额外身份字段。公共Demo知识按domain分类共享，无私有域ACL；SQL参数绑定、当前版本/Profile、精确余弦candidate5/top3、来源复核，序列化上下文同时限制2400 tokens/24KiB。Profile不一致明确报错。
- `main.py:62`只增加资源与就绪装配；当前未接入KnowledgeAgent生成式回答/知识工具或Memory。语料为六份自编Demo，无订单行、审批事实或会话内容导入。006保持不可变，两表及必要B-tree，无ANN。

## QA 实际执行

所有命令使用项目 `.venv/Scripts/python.exe`。测试URL仅在当前Python进程从Settings读取并设置到 `AGENT_TEST_DATABASE_URL`，未打印凭据。

| 层次 | 命令/操作 | 实际结果 |
| --- | --- | --- |
| 受控+真实PG | `pytest.main(['tests/test_knowledge.py','tests/test_knowledge_postgres.py','-q'])` | **7 passed / 0 failed / 0 skipped，6.43秒** |
| 真Qwen+真PG | `-m scripts.verify_05_embedding --action prepare --state docs/question/05-local-embedding-qa-evidence-20261113-a.json` | 成功；实际uvicorn PID43840，正常关闭exit0 |
| 完整新进程 | 同唯一state，`--action check` | 成功；实际uvicorn PID42292，与首次不同，正常关闭exit0；未重新导入 |
| 精确清理 | 同唯一state，`--action cleanup` | 成功；实际PID5464，Embedding关闭，正常关闭exit0 |
| 独立只读边界探针 | 本地权重/REVISION/006摘要；SearchQuery额外身份字段；未知Provider；同步psycopg在线版本/索引查询 | 全部断言通过；agent_demo_test/agent_test、server170006、vector0.8.7，6项索引均B-tree |
| 依赖 | `-m pip check` | No broken requirements found |
| 静态检查 | `-m ruff check .` | All checks passed |
| 格式 | `-m ruff format --check`，知识包及本单元直接涉及的main/config/postgres/脚本/测试 | 16 files already formatted |

受控测试实际覆盖超时/取消保持容量、busy拒绝、关闭排空、初始化不可用、缺tokenizer不隐式联网、版本/分片及上下文预算。真实PG用例以受控向量验证精确余弦、同版本重入、更新来源失效、错Profile拒绝及故意重复Chunk主键触发的真实事务回滚；失败后旧文档完整，清理后所有保护表完整行集与原始一致。该层不冒充Qwen语义验证。

独立权重SHA256为 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`，本地REVISION为 `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`；006原字节SHA256仍为 `5427fa3648c5bd0e15d46b8961314351055aae849582e55825a2ea093ffc4ea3`。

QA临时探针第一次命令因PowerShell转义产生SyntaxError；随后一次异步只读探针直接使用Windows默认Proactor loop，连接池初始化失败。核对既有 `scripts.run_async` 的Selector约定后，独立同步psycopg探针通过。两次均未产生业务写入，不记为产品缺陷或通过证据。

## 真实模型、持久化与资源

完整机器证据为[QA独立JSON](05-local-embedding-qa-evidence-20261113-a.json)与[进程日志](05-local-embedding-qa-evidence-20261113-a.process.txt)，未覆盖原Implementer证据。实际模型Qwen3Model、595776512参数、cpu、torch.bfloat16、batch1/CPU2线程，离线环境加载同一Profile。

- 首轮唯一6文档6批导入5.420秒，再导入0批。真实Document/Query均1024维有限非零，norm分别1.000782/1.000544；BF16数值近似符合归一化结果。
- 订单信息、聊天批准退款、真实银行卡扣款三问均预期来源Top1；首轮耗时398.33/341.11/293.98ms，上下文1021/1064/1064 tokens。实际更新重新推理2批、版本改变、旧引用失效；无scope拒绝。
- 全新FastAPI进程只加载本地模型并查询持久向量，原版本/Profile一致，三问仍Top1；耗时3063.22/305.33/319.72ms，上下文946/1064/1064 tokens。两个订单Chunk有不同真实来源位置，不是重复Chunk。
- 两次工厂创建至probe为19.984/20.142秒；峰值working set为1275789312/1418338304字节，peak commit为3874013184/3873423360字节。这是完整进程的Win32实际测量，不是权重大小或全机峰值。第二次推理后全机剩余物理内存仅94302208字节，冷启动与分页敏感，不能据此保证16GB任意其他负载配置都可用。

在线身份与全部迁移checksum、sessions/demo_orders/refund_requests/approvals、全部4张Saver表及既有知识行集均纳入保护指纹。精确删除本轮6个完整UUID文档ID及其7个Chunk，确认剩余0且保护指纹一致。临时源目录在核对其为当前TEMP直属目录、生成前缀及精确6源文件+manifest集合后逐文件清理并删除空目录；证据文件保留。

## 复用门禁与限制

完整回归复用最终实现的[原交付记录](../05-local-embedding-delivery-report.md)和[原始JSON的final_full_regression](../05-local-embedding-real-evidence.json)：`pytest -q --showlocals` **172 passed / 0 failed / 0 skipped，65.01秒，无deselect**；其后保护基线相同且自身文档剩余0。QA没有无收益重跑全量，也没有将原历史失败或嵌套脱敏测试材料中的skip改记为通过。

数据库真实重启复用主Agent的[重启JSON](../05-pgvector-restart-evidence.json)：PG启动时间从2026-11-12T16:11:02.919855Z变为2026-11-13T13:47:52.823667Z，两库全部公共行和测试库持久向量摘要保持，仍PG17.6/vector0.8.7。该文件生成时query_pending=true；之后原Implementer真实新进程PID42552的check及本次QA新进程验证提供查询闭环，不能单凭SQL摘要推导模型通过。QA未自行重启数据库。

没有强制终止真实CPU内核；超时/取消语义以可阻塞工作线程受控验证和源码为依据，真实模型层验证正常执行/排空。默认8秒推理超时仍保留；真实验收工厂显式使用120秒推理/300秒初始化以测量冷启动，检索整体仍受15秒约束。容器重建需重新安装原固定PG17.6兼容pgvector包，这是既有资源报告的部署限制。

无新增05-QA问题编号。完成本工作单元独立验收并停止，交主Agent复核；其他05 Task、阶段转换和Git不在本报告授权内。
