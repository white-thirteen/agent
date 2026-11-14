# 05 本地Qwen/pgvector独立QA工作单元

仅在Implementer完成并停止后执行。依据最新用户授权、[执行任务](../05-local-embedding-execution-task.md)、实际交付报告及[资源报告](../05-pgvector-resource-report.md)，核验本轮Embedding与真实检索，不宣布05全部Task完成。D05旧OpenAI/1536由用户明确改为Qwen3-Embedding-0.6B/CPU/1024，其余数据版本、事务、来源、公共知识权限及预算边界适用。

先读根AGENTS/当前Task/交付与资源证据，按需读D05相关小节及完整必要源码；不通读历史。保护业务代码、既有测试/配置、迁移、模型文件/原证据摘要，默认不修改业务或代修。仅写独立报告和必要临时复现，不能改正确断言、降低门禁、不付费、不另派Agent/Bridge/Commit/Push。

## 重点与实际验证

- 复用LangChain Embeddings接口，业务不依赖Qwen加载细节；仅CPU轮子，无CUDA/新服务。检查Query提示与Document策略、1024维有限非零向量、Tokenizer边界/不静默截断、归一化及Profile含固定模型权重版本和预处理约定。未知Provider/错Profile明确拒绝，不回退Mock向量。
- 模型在Windows D:\AI\models\qwen3-embedding-0.6b，本地缓存可离线加载，来源及固定权重摘要真实；单实例、batch和并发有界，阻塞工作在事件循环外。超时/取消后CPU内核未结束不得释放容量或谎称停止；关闭排空、释放。检查初始化/运行失败就绪和错误语义，不重构其他Agent/Workflow。
- 实际运行足够证明Query和Document真Qwen的最小测试及真实test PG持久化/语义召回/更新/来源失效/事务回滚。测试层区分受控、真实PG、真实模型；复用已有可信重启/模型证据时标明来源，不把生成向量的SQL探针当Qwen。缺模型/依赖/下载时明确BLOCKED，不用skip宣称通过。
- public Demo知识库按D05不是私有租户库，验证无knowledge:read拒绝、参数不能篡改可信身份，合法用户共享公共知识符合设计；不发明域ACL。确认不把私有订单/审批/用户会话内容写入知识库或模型缓存。
- 006已在两库应用，原字节SHA256不可更改；schema1～6、PG17.6、vector0.8.7、vector(1024)、精确余弦及必要B-tree，无ANN。仅测试库agent_demo_test/agent_test，在线身份/全部checksum、业务/已有知识前后全行集/迁移摘要/自身Saver线程核对，唯一记录、精确清理；不seed或访问开发库跑测试，不改环境/密码。全回归如确有需要，既有seed幂等窄例外只适用原用例并恢复固定事实。
- Windows FastAPI完整进程重启和DB重启后持久向量仍可查询，不能以同进程换对象替代。数据库重启由主Agent协调，QA不得在其他测试执行时擅自重启。检查实际PID/原版本/Profile、模型复用/内存和耗时测量方法，不能编造性能值或承诺16GB所有配置都可用。

按风险做必要独立复测，不重复无新影响的全量或大模型全排列。QA模型运行与其他模型进程串行，避免资源竞争。完整门禁证据应来自最终实现，明确未重复执行的可信来源。

交付 `docs/question/05-local-embedding-qa-report.md`：PASS/FAIL（仅本工作单元），问题05-QA-xxx与严重度/位置/最小复现、实际命令/通过失败跳过/未验、真实资源分层、清理/权限与实质风险。发现FAIL交回主Agent，原Implementer定向修复后独立复测；报告完成即停止，不自动进05其他Task或06。
