# Task 5.2.1 知识工具与子图

2026-11-14，用户明确要求继续05，授权依原冻结D05顺序完成剩余Task。此前仅Embedding工作单元的“不改Specialist/Memory”限本地化范围，现由最新继续05指令覆盖，仍不得扩大到06或无关订单/退款业务。5.1本地Qwen/PG真实检索已独立QA PASS、主复核VERIFIED，证据不重写，不重新实现模型/向量库。当前只派5.2.1，完成后停止交主Agent独立QA，不自行做5.2.2或5.3，不Git。

## 必读与复用

根AGENTS、docs/STATE.md、D05（docs/05-rag-memory-detailed-design.md）第5～8节/Task5.2.1及必要跨阶段契约、docs/05-local-embedding-delivery-report.md和独立QA结论。必要源码完整阅读，尤其现有Knowledge骨架、Order子图、ToolExecutor/Policy/RunScope/Gateway、transfers/aggregator/Response、公共Runtime结果/SSE白名单。其他历史按需不通读。沿安装版本签名/源码，不盲升级依赖。

## 实现与验收

1. 复用现有Qwen/1024维/本地CPU/Profile与VectorRetriever，不更改006已应用迁移字节，不重启/SSH/改DB结构或.env，不加载多个模型。必要的DTO/来源接口增量沿既有SearchQuery/EvidenceReference，不重复抽象。公共知识按knowledge:read，domain不是租户ACL。
2. D05六节真实search_knowledge与validate_knowledge_sources注册，只资源就绪启用。全部运行时检索/来源复核经同一Policy/Executor；可信Agent/task/origin/node allowlist/参数约束/版本/scope每次执行复核，不直调handler/库绕过。按现有调用记录/稳定node_call_id/execution_id/累计预算契约；model调用原AIMessage/ToolMessage精确配对，node调用不造ToolMessage。
3. 保留D05八节点及条件边：check_request、prepare_query、select_retrieval_tool、retrieve_knowledge、assess_evidence、generate_answer、validate_sources、map_result。检索选择通过Gateway原生工具调用，最多一条、只暴露完整检索Schema，错/多/混合调用按既有03可靠ID闭合规则拒绝。prepare仅当前问题/可信白名单上下文；Reader暂未就绪明确unavailable/denied，不实现Memory写入。
4. 非空证据一次结构化评估sufficient/insufficient/conflicting（真缺参needs_input），空/弱/冲突拒答；故障failed不能假empty。AnswerDraft非空<=2000字符及真实1..5唯一引用，只有assess采用ID可用；引用关联校验+同Executor当前doc/version/chunk/hash复核后才approved_answer/服务器生成PublicCitation。更新删除失效不公开旧草稿。来源存在不是语义正确证明，禁止正文连续原文匹配替代生成式回答。文档视低信任数据，不授权读写订单或Memory。
5. 必要扩展既有contracts/transfers/聚合/Response/Runtime结果/SSE sources白名单，主Response原样输出approved_answer及真实sources，不另模型改写、不泄露私有证据/工具历史/向量/Profile。保留父子身份及Task/run关联、预算累计、Saver恢复边界。不重构Supervisor/其他业务，只做当前契约直接必要接点。
6. 按风险少量有意义测试：成功/无弱冲突证据/伪引用或过期/权限origin错参数/预算/消息配对及唯一公开出口。单元可受控模型/Embedding；必要PG集成用专用agent_demo_test/agent_test，在线核身份及完整迁移checksum，前后原业务/Saver/他人知识完整行集保护；唯一ID、精确清理，不seed/删除他人数据。不得将受控测试宣称5.2.2真Chat/Qwen联调。
7. 常规受影响测试；涉及公共契约完成最终完整真实PG回归和Ruff/改动格式，依赖不变无需反复pipcheck。不得削弱原断言/跳过失败。无业务测试改动前核实是否旧断言确不兼容；旧SourceReference契约如迁移保留正确安全边界。

## 交付与纪律

只写代码/必要测试与独立交付docs/05-knowledge-tools-delivery-report.md，README必要导航可增。主Agent负责STATE/AGENTS/主协调记录/独立QA派发，Implementer不修改它们或旧证据。交付列修改位置、实现链路、真实命令结果/失败与未验、未闭环。原六项暂缓差异（docs旧删除/01设计改动/general.py/Bridge设计）及既有未提交配置保留，不覆盖、不暂存/Commit/Push/reset。

若QA FAIL，主Agent将问题交回同Implementer；修复记录必须写docs/resume/record/并关联Task/问题编号/提示词。当前不得派其他子Agent/Bridge；完成即停止。
