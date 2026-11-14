# Task5.2.1 独立QA工作单元

只在Implementer完成停止后派发。按根AGENTS、docs/05-knowledge-tools-execution-task.md、冻结D05第5～8节/5.2.1、实际交付报告验收本Task。前置Qwen/PG单元原真实证据可复用，不重复下载/重新实现或宣称本Task已等于5.2.2真Chat集成。默认不改代码/既有测试/配置/原证据，仅写独立报告和必要临时复现。无Commit/Push/Bridge/另派Agent/SSH/DB重启。

重点：
- 八节点拓扑/State写入权及Task/run/父子白名单。模型原生单检索调用参数受当前规范query/domain/top_k约束；错误或多条调用可靠ID按03闭合；真实search和sourcevalidate均经原Policy/Executor，固定origin/task/node allowlist和scope；模型不获得sourcevalidation/Store/订单写工具。
- 原AIMessage/ToolMessage一一对应、原call_id及稳定node_call_id、call_records含安全结果；node-origin不造ToolMessage；重复/重进复用仍核权限、预算累计无重复叠加/重置。仅本轮证据进入私有State，公共SSE/Run/结果不泄露查询历史、低信任文档全文、模型推理、Profile/向量。
- 空/弱/冲突拒答、真实缺参needs_input、资源/Embedding/PG/预算等故障failed，不能故障假empty或无限重试。充分性一次Gateway，生成AnswerDraft只私有候选，引用来自assess选中且当轮真实Evidence；伪造/重复/空/过期引用不能删错后继续发。
- validate_sources经统一工具当前版本/hash核验，服务器构造白名单PublicCitation及checked_at；主Response原样approved_answer，不改写政策或来源。合法ID并非逐句语义证明，受控合法引用错误正文要作为5.2.2风险保留，不发明原文匹配/固定回答替代生成。文档注入不提升权限。
- 资源未就绪不假成功；Reader未实现阶段明确unavailable/denied不伪造偏好。其他订单/退款/审批/Workflow保持现有行为，必要共用契约兼容和Serializer允许类型必须经实际持久Saver恢复验证，不只InMemory。

执行必要独立定向受控模型+真实PG/pgvector集成，真实测试仅agent_demo_test/agent_test，先核在线身份/完整迁移checksum、原业务/Saver/已有知识前后完整行集，唯一ID/精确清理不seed他人/固定五订单。006已应用原SHA不可改。未变完整门禁可清楚引用最终Implementer报告，不无收益重复全量；测试缺环境标BLOCKED不以skip通过。

输出docs/question/05-knowledge-tools-qa-report.md：PASS/FAIL仅Task5.2.1、05-QA问题编号/严重度/位置/复现、真实测试命令通过失败跳过/未验、门禁来源、隔离和清理、实质风险。新问题编号延续05局部首个001，旧Embedding无阻塞问题；如FAIL停止交主Agent退回原Implementer，不代修。完成即停止不进下一Task。
