# Task5.2.2 RAG真实联调

2026-11-14用户授权继续05；仅5.2.1独立QA通过并经主Agent复核后派发本Task，当前文件是后继任务准备，不代表已开始。依据根AGENTS、STATE、D05第6～8/11节和Task5.2.2，以及5.1与5.2.1最终交付/QA记录。固定Qwen3-Embedding-0.6B/CPU/1024，Windows指定缓存，PG17.6/vector0.8.7/schema6，不改006、.env或既有资源。

目标是在已实现八节点/同Executor链上完成真实Qwen+真实Chat+真实PG的RAG联调，禁止用Mock结果替代真实模型。复用现有受控单元，不重新开发检索或重设计Graph。当前Chat供应商/模型/凭据从Settings读取，先确认可用，不输出密钥/DSN。用户已授权实际模型验收，使用少量必要请求不反复付费回归；遇真实模型/资源不可用如实BLOCKED，不静态冒充通过。

1. 固定8～12样本JSON，字段sample_id/question/可选domain/expected_doc或chunk/expected_outcome/semantic_checks，覆盖正常、无答案、弱相关、冲突、伪引用、合法引用但错误正文、恶意文档、更新/删除、缺scope；明确哪些受控精确输出、哪些真实Chat端到端。默认自有Demo语料不混入恶意fixture，不运行生产固定答案查表。
2. 受控模型+真PG验证引用/故障/预算/注入边界；真实Qwen+真Chat+PG至少正常、无答案、冲突完整主图/Runtime或HTTP/SSE真实请求，核ToolCall/ToolMessage、Executor计数、Task/run、唯一公开正文及公共sources。正常正文允许概括，不以连续原文匹配判定；逐样人工检查事实、概括、冲突和无依据陈述，合法ID错误正文必须展示来源校验可能通过但语义验收失败的边界。
3. 真检索相关性/向量维度/Profile、candidate5/top3、上下文2400tokens/24KiB、阈值null、实际供应商模型/固定语料版本分别记录。来源以服务器当前doc/version/chunk/hash校验，来源存在率不等于正文准确率。插入检索后更新/删除使原草稿不公开；Embedding/PG超时明确技术失败，不变空结果。
4. 只对发现的真实缺陷最小修正，必要回归，保持5.2.1治理/父子隔离/不泄露文档全文/不扩Memory或订单退款。若实质代码修复应完整门禁适配，不弱化断言、skip/deselect掩盖失败。
5. 真数据库仅agent_demo_test/agent_test，连接前核目标、在线身份/全部迁移checksum，原业务/Saver/他人知识完整行集前后保护。UUID来源/知识记录/会话/thread唯一且精确清理，不seed/删固定订单/影响开发库，不SSH/重启原数据库。调用Qwen进程串行正常排空，记录实际资源/耗时和未执行项目；不重复5.1已通过DB重启无收益动作。

交付tests/fixtures/knowledge_cases.json、必要集成测试/显式真实验证脚本、docs/rag-validation.md及脱敏机器证据；README必要导航。记录真实命令/通过失败/阻塞未验/语义人工判定与供应商/Profile/语料。不要修改STATE/AGENTS/主协调/旧证据，主Agent负责状态和独立QA。无Git/Bridge/额外Agent，完成后停止不做5.3；QA问题由主Agent交回原Implementer，并按docs/resume/record记录关联任务问题和提示词。
