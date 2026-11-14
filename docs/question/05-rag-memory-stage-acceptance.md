# 05 RAG / Store 阶段技术验收

2026-11-14。主Agent结论：**ACCEPTED，用户已正式验收并授权Git提交/推送**。01～04保持ACCEPTED/已归档，05六Task实现与独立QA均已闭环，无未关闭05阻塞；未进入06，本轮执行已授权Git归档。

## Task与可追溯证据

| Task | 技术状态 | 交付/独立验收 |
| --- | --- | --- |
| 5.1.1 导入与向量资源 | VERIFIED | [本地Qwen交付](../05-local-embedding-delivery-report.md)、[独立QA](05-local-embedding-qa-report.md)、[资源安装](../05-pgvector-resource-report.md) |
| 5.1.2 Retriever证据契约 | VERIFIED | 同上真实向量/当前来源/更新回滚；三态充分性在[5.2.1交付](../05-knowledge-tools-delivery-report.md)及其[独立QA](05-knowledge-tools-qa-report.md)实际接线 |
| 5.2.1 知识工具与八节点子图 | VERIFIED | [交付](../05-knowledge-tools-delivery-report.md)、[独立QA PASS](05-knowledge-tools-qa-report.md) |
| 5.2.2 RAG真实联调 | VERIFIED | [逐样验证](../rag-validation.md)、[独立QA PASS](05-rag-validation-qa-report.md) |
| 5.3.1 Store资源与共享Reader | VERIFIED | [交付](../05-store-reader-delivery-report.md)、[原FAIL](05-store-reader-qa-report.md)、[05-QA-001修复](../resume/record/05-store-reader-fix-01-report.md)、[原QA复测PASS](05-store-reader-fix-01-regression-report.md) |
| 5.3.2 显式记忆管理与幂等更新 | VERIFIED | [最终交付及英语补验](../05-memory-manage-delivery-report.md)、[独立QA PASS](05-memory-manage-qa-report.md) |

冻结D05的业务/身份/版本/预算/来源/写前边界保留；用户明确将原OpenAI Embedding/1536/API Key替换为Windows本地Qwen3-Embedding-0.6B CPU/1024维。没有改冻设计正文或扩BM25/RRF/Reranker/MemoryWriter/生产租户认证。

## 最终行为与主Agent裁决

- 文档受控md/txt清洗/切分→单例sentence-transformers本地CPU Qwen→PG vector(1024)持久化；完整同版本跳过，更新事务替换，异常保留旧版本；明确Profile阻止混用。检索candidate5/top3、精确余弦、2400tokens/24KiB、阈值null。
- Knowledge八节点经同Registry/Policy/Executor执行真实检索与当前来源复核，原Call/ToolMessage匹配、node不造ToolMessage，来源校验通过才公开approved_answer；服务器PublicCitation，主Response不再模型改写。空弱冲突拒答，技术故障不假空；公共Demo知识按scope共享，domain不是私有域ACL。
- Store3.2.0独立小池、index=None/ttl=None，显式setup，启动只检查；三个专业共享Reader→Manager.snapshot。可信用户namespace/profile跨会话/thread，scope拒绝零访问、partial白名单投影、技术故障可选默认呈现，预算/取消不降级绕过。
- 当前Task原始Human一次确定语法解析才授权Memory命令；同prepare_attempt→真实Saver durability=sync→execute_prepared，固定节点/参数/scope/预算最终复核。Manager单用户锁/单Item revision与last_mutation处理applied/reused/conflict/unknown；unknown只核对不盲写，模型/文档/旧AI消息不授权。Memory命令独立于Embedding就绪。

主Agent已检查实现接点、真实证据与独立QA；原生Implementer→QA串行，干净上下文，失败交原Implementer并由原QA复测。运行时role/父子标识与各轮裁决见[主协调记录](05-remaining-main-review.md)，未用Bridge/新编排框架。QA期间受保护业务/测试/配置/.env/006/旧证据摘要无变化；QA只读是行为约束，不是独立沙盒。

## 验证与问题闭环

最终未变应用的完整真实PG门禁 **216 passed / 0 failed / 0 skipped，100.74秒，无deselect**，来自5.3.2交付。最后补验仅新增脚本/证据，不修改应用，未无收益重跑全量。主Agent最终运行 `ruff check app scripts tests`通过、`ruff format --check app scripts tests`为**147 files already formatted**；依赖自本地Embedding单元后未变，原pip check通过证据保持。

独立QA包括5.2.1的78项及真实新Saver解码补充，5.2.2自己执行真实Qwen/Chat/PG三例+10个受控结果，5.3.1修复后56项及真实跨进程/资源/损坏profile探针，5.3.2的25项及独立真实PG补充：sync失败零Put、最终Policy拒绝后同/新Run重复核对保留unknown无Put、真实Put提交后取消/超时不公开成功。QA复用完整门禁/付费证据的来源在各报告明确，不将引用当自己执行。

真实模型层：Qwen/PG生成、写入、中文语义召回与文档更新/来源失效；真实PG容器重启及新Windows uvicorn离线查询已在5.1验证。真实Chat为配置的DeepSeek deepseek-flash：正常回答、无答案拒答、30/90天冲突拒答；来源存在性和正文人工语义分开。最终真实命令save/read/delete/read-empty通过，Embedding关闭仍工作；最后保存英语偏好后，同用户新会话普通中文问题得到有中文原文支持的英语答案，真实Qwen1024/PG来源复核，工具3（read/search/validate）、模型4。[最终组合JSON](../05-memory-manage-real-rag-evidence-20261114.json)。

唯一阻塞缺陷**05-QA-001/P2已关闭**：非object JSON profile在Store3.2.0解码阶段抛JSONDecodeError，原Manager事后类型校验来不及。精确转换该已证实解码错误，真实编译订单路径安全失败并继续；普通ValueError/取消仍传播。原FAIL/修复提示/记录/原QA复测均独立留存。历史测试/夹具失败及配置解释造成的暂时未验也保留，均有后续闭环，不改写为当时成功。

## 数据、资源及使用边界

主Agent最终仅只读核两库，见[最终机器证据](../05-stage-main-final-evidence.json)：PG17.6、pgvector0.8.7、应用schema1～6全部checksum匹配，006原字节不变；Store库自管迁移0～3。原业务/Saver行集与重启前基线相同，原五订单保持。开发/测试的knowledge_documents/chunks/store均0行，验收UUID临时数据精确清理；并非用户偏好delete会物理删除版本元数据。

开发/测试Store已显式setup，原表行集/列定义不变。[资源setup证据](../05-store-resource-main-evidence.json)。模型位于 `D:\AI\models\qwen3-embedding-0.6b`，CPU/BF16/batch1/2线程，单推理槽、超时/取消保留槽直到真实工作完成、退出排空。已测峰值驻留约1.21～1.33GiB、peak private commit约3.61GiB；加载/延迟随可用内存和分页变化，具体真实字节与耗时在原报告，不承诺16GB任意其他负载均可用。

真实 `.env` 未变，Embedding默认关闭；演示RAG需显式启用 `AGENT_EMBEDDING_ENABLED=true`，并用已有 `scripts.ingest_knowledge --target development --manifest data/knowledge/manifest.json`显式导入随附Demo语料。启动不自动导入。Store显式命令无需Qwen就绪。测试库不得作为生产/开发数据导入目标混用。

保留限制：单进程/单worker内存锁，无跨进程CAS或Graph/Store/Checkpoint全局原子承诺；unknown需操作者先暂停相关profile新写并按已知原op人工核对，无自动扫描恢复/全局写阻断。删除偏好不擦除历史聊天/Checkpoint。来源仅证明checked_at时刻存在，合法引用不保证任意正文语义正确；故意错误正文反例仍人工语义FAIL，小样本不是通用准确率。当前pgvector包在原容器可写层，重建容器需按固定PG17.6兼容包重新安装；普通重启已验证。

Git仍 `real-model-chat` / HEAD `6c72169da306b5bfd604d043675d51a317d03de9`，05及本轮使用的角色配置按用户最新授权归档；原六项暂缓差异保留。**用户已正式验收05并授权提交/推送；归档后停止，进入06仍待用户另行授权。**
