# Task6.2.1 核心持久化故障

6.1.2独立QA PASS、主Agent复核VERIFIED，现明确单独派发6.2.1，IN_PROGRESS。用户已授权06，沿冻结D06第6节、Task6.2.1和故障矩阵；读AGENTS/STATE、6.1.1/6.1.2最终交付及必要04恢复实现/验收，已有能力不重做。

范围是当前完整装配下的持久化故障组合：复用04现有管理API、Runtime恢复分类、RefundRecoveryContext和原operation查询，不创建新WorkflowRepository/恢复API/自动扫描重放平台。允许必要的最小业务修复，故障注入仅测试侧。默认受控Chat，真实PG/Saver/Store及完整独立FastAPI进程停止/新进程恢复，不能将同进程重建Runtime或ASGI请求称为进程/TCP验收。

验证独立UUID用户/订单/会话上真实退款调用与审批已持久化，记录原thread/task/workflow/call/name/规范args/application/operation/approval、child namespace和累计用量。完整停止自行创建的FastAPI进程，再以相同版本/拓扑启动，核原interrupt可恢复、新Run而原Task不变。父最后已完成checkpoint可仍running，使用实际interrupt/子调用和公开状态判断，不强改框架快照。

覆盖既有四分类：真实interrupt、Gate后未结束可核验推进；正常END只读返回原持久结果，不建新Run/Graph/副作用；缺失/未知快照或业务unknown拒绝盲重放。审批拒绝零退款、重复/相反决定、并发resume、PENDING惰性EXPIRED、APPROVED过期保留决定但禁写、成功op过期仅复用；重复resume不续期。注入已interrupt但绑定失败，原repair-binding幂等且未绑定不可决定。

按04已有可信窗口验证业务事务提交后快照失败：已成功原operation仅查证复用，退款写工具尝试及第二次业务变更均零；确认未执行则在原批准/期限/预算/Domain复核及可信准备快照下受控执行；unknown保留并停止。检查原ToolCall/ToolMessage配对和唯一成功申请/订单标记。优先复用前序未变化证据，明确哪些实际重跑、哪些来源复用，必要当前组合不能只静态推断。

仅test库agent_demo_test/agent_test，项目.venv及Windows异步PG既有Selector入口。运行前身份、001～006全迁移checksum、全部public完整行集及列定义保护；UUID自有数据按FK和明确ID精确清理。不得seed或改固定五订单；最终完整回归原seed幂等用例窄例外按AGENTS原样执行/finally恢复，不deselect。保护.env、006、已存证据、角色配置及六项暂缓差异。测试进程Settings选择test/UUID/EmbeddingTrue允许，不改用户真实配置或Codex模型/provider/账号。

不得SSH/重启PG或原容器/重建卷/有损迁移/杀用户进程，不Git/Bridge/另派Agent/进入6.2.2。只控制自行创建、已记录PID/启动时间/命令的验证进程，确保关闭及精确清理。定向测试优先，公共行为变更后最终完整真实PG门禁和Ruff/改动格式，未变则可有出处复用完整门禁。交付docs/v1/v1-06/06-persistence-fault-delivery-report.md和脱敏证据/必要README导航，注明实测命令/状态/关联/清理/失败与未验，完成停止交独立QA；不修改STATE/AGENTS/主协调。
