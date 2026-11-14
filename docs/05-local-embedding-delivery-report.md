# 05 本地 Embedding 与真实检索交付报告

本报告覆盖 docs/05-local-embedding-execution-task.md 单元。实现与本轮自测已完成：最终完整真实测试库 **172 passed / 0 failed / 0 skipped**，真实Qwen CPU、1024维pgvector、FastAPI完整进程重启及PG重启后检索通过，验收数据精确清理。交主Agent复核与独立QA；不代表05六Task完成或阶段验收。

## 实现与调用链

- `app/knowledge/embedding.py`：直接实现现有 LangChain `Embeddings`，本地 SentenceTransformer CPU、一实例/单工作线程，batch1、CPU2线程、BF16。Query使用官方任务提示，Document无查询提示，L2归一化，完整1024维有限非零校验；Tokenizer预检查拒绝超长输入。异步初始化/推理/释放均离开事件循环。超时或取消后底层线程保持唯一容量，后续调用返回busy；关闭排空后释放权重。
- `models.py/chunking.py`：固定来源契约、受控md/txt、manifest路径与256KiB/50文件边界、cl100k_base计数、500 token正文/700 token嵌入输入、1000 Chunk/100000输入token上限；段落优先、Unicode安全分片，本实现重叠0（不超过冻结80上限）。保存真实章节、行号和内容hash，page始终null。
- `ingest.py/repository.py`：版本含规范化正文、manifest、parser-v1/chunker-v1和完整Embedding Profile；完整同版本跳过推理/写入。推理在事务外；每文档事务/锁内完整替换，两表复合FK；写失败旧版本不变。显式remove只删指定document_id。
- `retriever.py`：可信DemoIdentity的knowledge:read边界，domain仅公共分类；SQL绑定参数、当前版本/Profile、`<=>`精确余弦、候选5/最多3，含来源元数据≤2400 tokens和24KiB。返回真实Chunk、可供后续RAG使用的JSON上下文、query指纹与观测；来源复核依赖当前PG事实。
- `scripts/verify_04_restart.py:34/101`：经执行任务末尾主Agent裁决，仅新增集中EXPECTED_SCHEMA_VERSION导入并替换旧的schema数量5断言；完整checksum、行集和业务断言保持。该直接集成修正未修改退款实现。
- `app/main.py`：只增加资源装配和health的embedding_status/knowledge_ready，默认关闭Embedding；未改变Supervisor、专业图或订单/退款/审批/Workflow。`app.state.knowledge_retriever`供后续受治理接线使用。当前没有把检索接入KnowledgeAgent生成式回答或Store，也没有新增生产检索HTTP/工具入口。
- `scripts/ingest_knowledge.py`为显式target导入/remove；`scripts/verify_05_embedding.py`只在验证工厂增加本地probe/stop路由，真实加载正式应用lifespan及Qwen/PG，通过独立uvicorn进程保存并复核证据。

## 模型、依赖与Schema

固定目录 `D:/AI/models/qwen3-embedding-0.6b`，模型 `Qwen/Qwen3-Embedding-0.6B`。下载固定HF revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，权重1191586416字节，SHA256 `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`；官方Qwen ModelScope镜像下载后与HF固定revision的LFS hash核验一致。Tokenizer JSON SHA256 `def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a`。小配置文件来自同HF revision。上述缓存实际由临时requests流式命令下载、hashlib.file_digest核验；仓库下载脚本提供同样的显式流程，本轮未重复下载已完成的1.2GB权重。`REVISION`记录权重版本，后续加载强制local_files_only、不信任远程代码，验证子进程同时设HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE。固定cl100k_base的BPE缓存也先核对本地文件及官方SHA256，缺少时明确knowledge_tokenizer_unavailable，不隐式联网；显式下载脚本会预热该小缓存。Embedding关闭时不加载这些资产，初始化线程会提前加载上下文tokenizer。

模型官方说明：[Qwen模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)。Profile包含provider/model/dimensions、Tokenizer JSON内容指纹、权重revision、profile_revision、dtype、L2及完整Query提示。Profile变化需要显式重嵌，查询拒绝不一致。

迁移006由主Agent应用，Implementer没有重跑或修改已应用006；本地SHA256 `5427fa3648c5bd0e15d46b8961314351055aae849582e55825a2ea093ffc4ea3`保持。仅knowledge_documents/knowledge_chunks、vector(1024)、分类及FK B-tree，无ANN。首次无旧知识数据，不需要维度转换。应用schema期望更新为6。真实PG17.6/pgvector0.8.7部署与原数据保留见[主Agent资源证据](05-pgvector-resource-evidence.json)。

实际安装命令先尝试CPU官方index，遇到TLS断流/低吞吐后中止；官方直链分块续传得到CPU轮子110859971字节，SHA256 `404a7ab2fffaf2ca069e662f331eb46313692b2f1630df2720094284f390ccef`与PyTorch官方index一致。最终串行执行：

```powershell
.\.venv\Scripts\python.exe -m pip install 'D:/AI/wheels/torch-2.9.1+cpu-cp313-cp313-win_amd64.whl' -c requirements.txt
.\.venv\Scripts\python.exe -m pip install sentence-transformers==5.1.2 transformers==4.57.6 -c requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

安装成功且pip check为`No broken requirements found`。torch `2.9.1+cpu`，sentence-transformers `5.1.2`，transformers `4.57.6`，huggingface-hub `0.36.2`，tokenizers `0.22.2`，safetensors `0.8.0`，numpy `2.5.4`；其他新增解析版本同步requirements.txt，原有包版本由安装constraint保留。直接依赖同步requirements.in，并以CPU index和`+cpu`固定torch。实际检查torch.version.cuda=None、torch.cuda.is_available=False，锁定清单无nvidia/cuda/triton包。已用inspect.signature核对实际SentenceTransformer构造、encode、LangChain Embeddings.aembed_documents和HfApi.model_info签名。

## 已执行验证

1. `.venv/Scripts/python.exe -m pytest tests/test_knowledge.py tests/test_resources.py tests/test_application.py tests/test_config.py -q`：修正上下文预算测试输入后24 passed；之后新增初始化不可用测试及释放逻辑定向测试5 passed。
2. 在自身Python进程从本地Settings读取test URL并仅设置`AGENT_TEST_DATABASE_URL`，执行`pytest.main(['tests/test_knowledge.py','tests/test_knowledge_postgres.py','-q'])`：当时5 passed、0 skipped。真实PG覆盖在线agent_demo_test/agent_test、所有迁移checksum、精确余弦、相同版本重入、故意重复Chunk主键导致事务中途失败且旧版本完整、更新后旧来源失效、Profile拒绝及显式删除。前后业务/迁移/知识完整行集相同，精确清理仅自身唯一document_id。
3. 全量真实库命令同上述安全设置test URL后执行`pytest.main(['-q'])`：**170 passed、1 failed、0 skipped，57.97秒**。唯一失败为既有`test_refund_repair_postgres`复用`scripts/verify_04_restart.py:101`硬编码schema迁移数量5；006已应用后该旧断言不成立，失败发生在该业务场景写入前。该历史轮次已保留，之后主Agent授权最小辅助脚本兼容修正；最终全过记录见下方，不把历史失败改写为通过。
4. `.venv/Scripts/python.exe -m ruff check .`：通过。改动Python文件的`ruff format --check`：最终16 files already formatted（包含获准修改的04辅助脚本）。另补本地上下文tokenizer缺失/禁联网启动回归后，`pytest tests/test_knowledge.py -q`为6 passed（8.37秒）；其中新增子进程用空tokenizer缓存且拒绝requests联网，正式FastAPI关闭Embedding仍能健康启动，缺缓存知识调用明确失败。
5. `.venv/Scripts/python.exe -m scripts.verify_05_embedding --action prepare`：**真实模型+真实PG通过**。独立uvicorn实际PID36264（Windows launcher17188），离线本地模型，正常关闭exit0。完整证据[真实验收JSON](05-local-embedding-real-evidence.json)，过程日志[进程日志](05-local-embedding-process-evidence.txt)。

首轮真实验收：6份唯一Demo文档/6批推理，导入5.699秒；完整同版本再次导入0批。Document/Query均1024维有限非零，L2 norm分别1.000782/1.000544（BF16数值近似）。订单信息、聊天能否批准退款、真实银行卡扣款三个中文问题的预期文档均排第1，检索耗时289.55/324.21/298.94ms；上下文1013/1071/1071 cl100k_base tokens。真实更新订单说明重新推理2批，旧version `735c2821b1a40930fbfa65c4e2a5843f561ef8acb2f8e2037a12f282127bfed9`变为`e97eadc816f7ed9e35312654f6d702f835cc17f12026c7c32088bbbeb4f0d150`，旧来源失效。缺scope拒绝，业务/迁移/全部Checkpoint及他人知识行集指纹保持。

实测FastAPI工厂创建后至probe 18.391秒（涵盖资源lifespan初始化）；推理后working set1191641088字节、峰值working set1297006592字节（约1.208GiB）、private commit2758000640字节、peak commit3871641600字节（约3.606GiB）；当时系统剩余物理内存541241344字节。这里working set为该完整进程实际驻留内存，commit包含已提交私有页，不冒充纯权重大小或全机峰值。使用BF16、单推理槽、batch1、CPU2线程，没有终止用户进程或启动额外模型服务。

## 重启、最终门禁和清理闭环

主Agent已在2026-11-13T13:47:42Z执行唯一一次本轮PG重启，PostgreSQL startup由2026-11-12T16:11:02.919855Z变为2026-11-13T13:47:52.823667Z，仍为17.6/pgvector0.8.7；两库全部public行、测试库6文档/7 Chunk、版本/Profile/向量hash保持一致，见[PG重启证据](05-pgvector-restart-evidence.json)。该资源文件中的query_pending是生成当时状态；其后真实Qwen查询闭环记录在本报告和真实验收JSON。

实际命令`.\.venv\Scripts\python.exe -m scripts.verify_05_embedding --action check`通过：独立Windows/uvicorn实际PID42552（launcher23376），与首轮PID36264不同，HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE同时开启、local_files_only=True，仅复用本地模型和PG持久向量，没有重新导入。实际模型为Qwen3Model、595776512参数、device=cpu、dtype=torch.bfloat16；仍为1024维Profile、batch1、CPU2线程。六文档的document_version与完整Profile一致，三问预期文档均第1，旧订单说明拆成两个不同Chunk后均有真实来源。缺scope仍拒绝，原保护行集一致。该进程也覆盖最终dtype关键字与上下文tokenizer惰性/纯本地加载修正，正常排空关闭exit0。

| 实测 | 首轮prepare | 重启后check |
| --- | ---: | ---: |
| FastAPI工厂创建后至probe，秒 | 18.391 | 16.120 |
| 三次语义检索，毫秒（含Embedding和SQL） | 289.55 / 324.21 / 298.94 | 2650.16 / 189.90 / 195.24 |
| 推理后working set，字节 | 1191641088 | 1370902528 |
| 峰值working set，字节 | 1297006592 | 1370902528 |
| 推理后private commit，字节 | 2758000640 | 2716246016 |
| peak commit，字节 | 3871641600 | 3875680256 |

`.\.venv\Scripts\python.exe -m scripts.verify_05_embedding --action cleanup`通过，实际PID28712（launcher17548），正常关闭exit0。cleanup不加载Qwen，启动1.394秒、working set约119.5MB。仅删除6个完整唯一document_id及其7 Chunk；没有按前缀批量删表或修改开发库。原sessions/demo_orders/refund_requests/approvals/schema_migrations、全部4张Checkpoint表、他人知识行集指纹与prepare前相同。随后验证临时目录确实位于当前Windows TEMP、名称为本轮生成前缀，且文件集合恰好为6份源文件+manifest，才逐文件删除并移除空目录；未递归清理其他目录。证据JSON保留版本、资源和清理结果。

最终完整真实库命令为在自身Python进程读取Settings的test URL，仅设置`AGENT_TEST_DATABASE_URL`，测试fixture及真库入口在连接前核验test target，调用`pytest.main(['-q','--showlocals'])`：**172 passed、0 failed、0 skipped、65.01秒，无deselect**。凭据由既有pytest_redaction保护，没有回显。原04 schema失败已由授权的两行辅助兼容修正关闭，退款真实场景通过。最终全量前另有一次171 passed/1 failed（60.11秒），失败是旧脱敏测试的嵌套pytest临时collection错误；同一生成目录/同一子命令立即独立重跑exit0，之后最终完整172项通过，未修改该测试或脱敏实现，未削弱断言。其内部故意构造的`1 passed, 2 skipped`是脱敏测试的测试材料，不是主门禁skip。

完整门禁结束后再次只读核验在线agent_demo_test/agent_test、迁移checksum、所有保护行集及自身文档剩余0，结果与原基线一致，写入真实验收JSON的final_full_regression。最终`.venv/Scripts/python.exe -m pip check`为No broken requirements found，全仓Ruff通过，16个改动Python文件format检查通过，006 SHA256仍为`5427fa3648c5bd0e15d46b8961314351055aae849582e55825a2ea093ffc4ea3`。

受控单元覆盖超时/取消后仍占用容量、busy拒绝、关闭排空、资源不可用、默认禁用且缺本地tokenizer不联网、Unicode分片、版本稳定、重复导入和上下文预算。PG测试使用真实扩展/事务和受控向量，真实SQL主键错误验证中途写失败回滚；不把这组受控向量当Qwen语义证据。真实模型层使用未Mock的QwenCPU、Query/Document和真实持久向量，真实PG重启由主Agent执行；没有用付费Chat模型替代Embedding。没有强制终止真实CPU内核的实验，超时/取消行为由可阻塞线程替身验证。

## 使用方式

保持已有`.env`。示例`.env.example`新增的Embedding默认关闭；需要时显式设置`AGENT_EMBEDDING_ENABLED=true`，固定CPU/batch1/线程2/BF16，最大输入1024实际Qwen tokenizer tokens；默认推理超时8秒、初始化120秒，超时不代表CPU内核被终止。内存紧张时应释放用户自行决定的资源；实现不停止用户进程，不自动切换dtype或降维。

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.9.1+cpu --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.download_embedding --download
# HF大文件链路不稳定时，可显式选官方Qwen镜像，仍核验HF权重SHA256
.\.venv\Scripts\python.exe -m scripts.download_embedding --download --modelscope-mirror
.\.venv\Scripts\python.exe -m scripts.ingest_knowledge --target development --manifest data/knowledge/manifest.json
.\.venv\Scripts\python.exe -m scripts.ingest_knowledge --target development --remove demo-account-help
```

导入示例会显式写目标知识表，不在应用启动时自动导入。语料为data/knowledge内6份自编Demo，无真实客户数据。离开manifest不自动删除数据库文档。

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_05_embedding --action prepare
# 主Agent执行数据库重启；Implementer不做SSH/VM操作
.\.venv\Scripts\python.exe -m scripts.verify_05_embedding --action check
.\.venv\Scripts\python.exe -m scripts.verify_05_embedding --action cleanup
```

真实验证使用agent_demo_test/agent_test，唯一6文档，状态和测量写入docs/05-local-embedding-real-evidence.json；prepare不会覆盖已有证据；复跑应使用新的`--state`文件路径，避免覆盖本轮审计。验收脚本显式把初始化/CPU调用时限设为300/120秒，以测量紧张内存下冷启动；检索整体仍受15秒限制。普通pytest不加载大模型；仅知识切分/预算测试需要固定cl100k_base小型BPE缓存，可单独显式准备：`.\.venv\Scripts\python.exe -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"`，不必下载Qwen来跑单元测试。真实验收缺依赖/模型/DB时应报告失败/阻塞，不以skip宣称通过。cleanup只启动正式应用/测试库资源，不再次加载大模型。

## 未闭环

本单元实现与开发自测无剩余阻塞，等待主Agent复核和独立QA；没有执行Git提交/推送、SSH/VM操作，也未修改用户.env、其他Agent或业务实现。05其他Task、KnowledgeAgent生成式回答、运行时知识工具接线与Memory未在本单元实施，不从本次结果推导阶段ACCEPTED。
