# 05 本地Qwen Embedding与真实检索工作单元

2026-11-13，用户已授权进入05，并明确将本轮范围收敛为Embedding本地化及真实检索闭环。最新部署指令覆盖D05中OpenAI/1536维/API凭据要求；D05其余当前文档/Chunk、版本、发布事务、权限、精确余弦和来源约束继续适用。不将本单元完成等同05全部六Task完成。

## 当前事实与最小方案

04已ACCEPTED，交付ab30f12、回执6c72169，现有变更和六项暂缓差异保留。尚无app/knowledge、Embedding Provider、知识表或旧向量数据；OpenAI只存在冻结设计，没有待替换的运行调用。两库PG17.6/schema1～5可达，pg_available_extensions无vector，无knowledge表。Windows为16GB、Ryzen 7 8845H/8核16线程，当前物理内存紧张；不终止用户进程。Qwen、torch、sentence-transformers尚未安装。

复用已安装LangChain `Embeddings`兼容接口，不再另造Provider协议。业务只依赖该接口及显式Embedding Profile；工厂按配置选择本轮唯一实际Provider `qwen_local`，未知Provider明确拒绝，不实现无需求的OpenAI适配/插件框架。

## Implementer范围与验收

1. Windows固定模型目录 `D:\AI\models\qwen3-embedding-0.6b`，模型 `Qwen/Qwen3-Embedding-0.6B`，CPU、1024维；sentence-transformers直接加载，单生命周期一实例复用，首次显式下载可联网，以后支持纯本地加载。按官方模型卡使用Query任务提示、Document不加查询提示，明确归一化/Tokenizer/版本/Profile。不得默默截断超长输入或截维/补零。
2. CPU-only PyTorch轮子，禁止CUDA/GPU/分布式依赖或额外模型服务。仅在项目.venv安装并同步直接/锁定依赖、pip check；先查看实际SDK签名。配置模型路径、batch size、最大输入、并发/CPU资源和超时。优先batch1/并发1，选取并记录适合16GB的dtype/线程设置及实际测量；不假报内存或延迟。
3. 初始化/推理/释放不阻塞FastAPI事件循环；异步适配在受控线程执行。超时/取消不能谎称已终止CPU内核，底层未结束时不得释放执行容量导致并行暴涨；关闭应排空并释放实例。初始化失败明确unavailable，不回退随机向量/Mock，不扩大到推理调度平台。可显式关闭Embedding以保留原非知识能力启动，示例清楚标出开启方式。
4. 新增必要 `app/knowledge/{embedding,models,chunking,ingest,repository,retriever}.py`及最小资源/Service适配，配置集中app/core/config.py、示例.env.example、生命周期只改main资源装配/就绪，不改Supervisor、Specialist、订单/退款/审批/Workflow。禁止覆盖用户.env及现有配置；真实脚本可在自身进程显式覆盖非秘密本地Embedding参数。
5. 沿D05第4～5节实现受控md/txt→清洗/切分→稳定文档版本/Chunk/Profile→事务完整替换；相同完整版本跳过推理/写入，更新重新嵌入，失败旧版本不变，显式remove仅指定文档。6～10份自有Demo语料和manifest，不含真实隐私。新迁移使用实际下一编号006，只有knowledge_documents/knowledge_chunks及必要vector扩展，字段vector(1024)，精确余弦/分类B-tree，无ANN/ES/BM25/RRF/Reranker；001～005不可修改。
6. 检索保持candidate5/top3、2400tokens/24KiB、阈值null、有效版本/Profile/来源追踪；输出真实Chunk和可供后续RAG使用的上下文，不假称已完成KnowledgeAgent生成式回答或Store。权限复用可信DemoIdentity/knowledge:read，V1知识库公共、domain仅分类，不发明租户或私有域ACL；无scope拒绝，普通用户不能通过模型参数自授权。用户/会话身份不得被检索参数改写。
7. 独立测试层：单元可替身；PG集成必须真pgvector；模型验收必须真QwenCPU、Query+Documents的1024维有限非零有效向量、真实写入/语义召回/更新与Profile一致性/隔离拒绝。模型/DB异常、超时与并发、FastAPI完整进程重启后复用本地模型和持久向量、DB重启后查询恢复，记录PID/原文档版本和真实资源/耗时。默认pytest不加载大模型，真实验收显式运行；缺环境标BLOCKED，不以skip当通过。

## 协作与数据边界

主Agent负责Ubuntu SSH/pgvector安装及数据库重启，Implementer不得自行SSH或改VM。主Agent确认扩展可用后，再通过既有迁移入口显式把原两库推进006；安全核对、迁移记录与数据保留必需，首次不存在知识表不涉及有损维度转换。有损变更必须报告方案，不自行清库/改旧向量。若未取得环境，不耽误实现、依赖/缓存准备和可执行测试。

真实测试只用agent_demo_test/agent_test；主Agent控制显式开发库迁移，不把开发库当测试库。在线身份/迁移checksum，保存sessions/demo_orders/refund_requests/approvals及已有知识行集/迁移摘要、自身Saver线程，唯一文档/用户/会话/操作，按外键精确清理本轮数据，不seed或覆盖固定五订单/他人数据。继承既有全回归seed幂等窄例外只用于该已批准用例的原样门禁，不能用于新增场景恢复数据。

根AGENTS、当前任务及D05相关小节是必读，其他完整源码按需要读，不通读历史。主Agent/Implementer/独立QA职责串行，Implementer不自行进下一Task/Stage、不调用Bridge或派生Agent，不Commit/Push/reset，不修改主AgentSTATE/协调记录、原04证据或冻结正文。SSH认证资料仅主Agent处理，不得索取/记录秘密。

交付 `docs/05-local-embedding-delivery-report.md`：实际文件/接口/调用链、模型缓存/配置、安装版本、1024维Schema/索引及旧数据兼容、命令/通过失败阻塞未执行、真实模型/PG/重启/隔离证据、实际内存和耗时、精确清理、风险及人工步骤。必要README导航。完成实现和自测后停止，交主Agent派原生qa独立验收；不自行标05整阶段完成或ACCEPTED。

## 实施期旧验证辅助脚本裁决

006应用后，全量真实库首次170 passed/1 failed，唯一失败是旧`scripts/verify_04_restart.py`把schema_migrations数量写死5，发生在退款业务场景写入前。主Agent复核该辅助函数的完整checksum核对和集中EXPECTED_SCHEMA_VERSION，批准仅将计数断言改为复用当前集中版本，并必要新增import；保持原checksum/行集保护、业务断言和退款实现不变。这是本轮schema增量的直接必要集成，不扩04业务或削弱门禁。修正后最终完整回归必须真实全过，不用deselect/skip掩盖。
