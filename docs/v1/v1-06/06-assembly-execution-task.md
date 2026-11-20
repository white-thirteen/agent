# Task6.1.1 完整演示环境装配

2026-11-14用户明确授权开始06。本Task正式派发，完成后停止交独立QA，不自动做6.1.2～6.3.2；主Agent按依赖逐项串行派发。01～05均ACCEPTED，05交付79d576b/归档回执HEADf860bb59cd566743dc32912836cecff39f5df74b。既有实现和真实证据不是空白，不重新设计或重复实现前序能力。D06页首旧“未授权/待冻结”是历史轮次，用户冻结确认和最新阶段授权优先。

## 必读与实际基础

根AGENTS、docs/STATE.md、docs/v1/v1-05/05-rag-memory-handoff.md、D06第2～4/6节及Task6.1.1；D01～D05仅查直接相关契约/接口及交付/QA结论，不通读历史。阅读必要完整源码，尤其main、资源适配/脚本、builders/wrapper、Runtime和三专业工具，不机械限行。D06旧OpenAI/1536已被用户明确改为Qwen3-Embedding-0.6B/WindowsCPU/1024；目录D:/AI/models/qwen3-embedding-0.6b，原PG17.6/vector0.8.7，应用schema6、Saver10项迁移、Store0～3，两库均已setup。006已应用字节不可改。

## 范围及验收

- 核前序能力实际装配，main为唯一资源所有者，一次共享ChatGateway/Embedding/Registry/Policy/Executor/Runtime/主图，三个专业和Memory命令图真实实现。只根compile持Saver，子图默认per-invocation继承；不重构Supervisor、Task生命周期、审批退款规则、不加基类/容器平台/第二Executor或第二管理Router。必要接点最小修改，无实际缺口不为制造变更重写。
- D06资源顺序：业务池/服务→Saver池→模型/Embedding与Retriever、Store自有池及Manager/Reader→统一工具/图/Runtime；停止先Runtime5秒收敛/取消，随后Store批处理任务await/Store池、模型/Embedding排空、Saver池、业务池，部分初始化反序清理。具体接口沿实际版本和已交付适配，必要私有适配仍限Infrastructure一处。普通startup不setup/迁移/seed/导入知识。
- 安全health就绪语义应与实际受理能力一致，隐藏DSN/凭据/原始异常。模型/session/Saver故障正确阻止受理；KB/Embedding/Profile不兼容不假ready或假empty，不影响独立Order/Refund/Memory；Store故障可选读取按既有规则降级/denied，显式操作安全失败/unknown，Memory独立于Embedding。注册冻结与当前模型可见Schema/允许执行集合一致，运行中错误经真实handler返回。
- 真实组合若复现Reader已读en而普通中文问题仍中文回答，须作为本Task前置接线行为缺项最小修复，不仅列遗留后交付。以最终实际源码为准（05已移除旧Use the question's language规则），核en枚举在生成指令中是否明确映射为英语，以及无条件concise是否冲突详细偏好；按冻结规则明确“本轮明示语言/风格 > 已验证存储偏好 > 无偏好时问题语言/默认风格”，只改直接必要提示/接点，不额外模型改写或校验后翻译，不换模型/预算、不放宽英语/语义断言。保留原失败证据，在一次真实应用生命周期内预先安排2个普通中文知识问题，均应依已保存en用英语且事实/来源正确；保留全部结果，不循环直到PASS。有限真实重测明确语言来源，事实/来源校验仍必须通过。
- 只注册前序已有approvals Router一次、服务端Actor仅审计、dev/test本地演示、production禁用；不能把客户端user_id选择当真实认证。运行入口无验收Stub/固定成功替身；受控测试保留构造注入，真实演示使用实际Domain/PG/模型。
- 必要定向用例验证正常、缺/错资源、部分初始化失败、模型/Graph只初始化一次、关闭顺序/连接任务无泄漏和取消不谎称未提交。真实PG实际应用集成，至少同一正式HTTP应用资源中三个专业任务及显式偏好命令可运行；真实Chat/Qwen少量必要请求，订单与退款始终标模拟，退款本Task可到真实Gate等待后拒绝清理，完整重启和故障组合留6.2，不重复04全矩阵。真实向量/来源/工具记录与budget据DB/Saver核实，不只LLM说成功。
- 真实测试只agent_demo_test/agent_test，先核在线身份/001～006完整checksum与库自管迁移；原业务/Saver/知识/他人Store所有public行集/列定义保护，UUID独立订单/用户/profile/会话/Task/文档，精确清理。不seed/修改固定五订单，不碰开发库业务数据；不能用Demo固定订单做会改变状态的退款演示。runtime模拟退款可以写独立fixture订单/申请，并核原operation，最后按FK精确清理。
- 不覆盖真实.env/冻结正文/006/原05证据/角色配置/六项暂缓差异；不SSH/重启数据库/升级PG/有损迁移或重建原容器。本Task先代码/应用装配，若发现可复现部署依赖缺口记录给6.3，不擅改原卷。
- 完整门禁继承已批准窄例外：允许原样执行tests/test_order_postgres.py::test_real_order_constraints_isolation_and_seed_idempotence（原05完整门禁已多次执行）。它仅在专用test库验证seed幂等并finally恢复原is_refunded值，须前后全部public行集/列定义一致；不能扩为新增测试seed/修改固定订单的授权。禁止deselect/skip该项来声称完整门禁；不修改其正确断言或调用实现。该特例覆盖前述一般“不seed/不改固定订单”对这一个既有用例的冲突。
- 受影响测试为主，公共装配实质改动完成最终完整真实PG门禁、Ruff/改动格式；依赖只在必要时改并同步requirements/pipcheck，勿盲升级。测试层区分受控/真PG/真Chat+Qwen，未执行/资源阻塞如实报告，不用skip冒充通过或削弱旧业务断言。

## 配置与交付纪律

禁止覆盖配置指用户.env和Codex账户/model/provider/角色配置；**允许验收进程Settings.model_copy/子进程非秘密环境选择test目标、UUID名单、embedding_enabled=True和原CPU模型路径**，预算沿冻结值。默认Embedding关闭不是缺失环境阻塞，按05真实脚本同样做进程内显式启用。真实凭据只Settings读取，不输出或复制。

只交本Task代码/必要测试/显式验证/README必要导航与docs/v1/v1-06/06-assembly-delivery-report.md及脱敏证据。不得修改STATE/AGENTS/主协调记录或历史QA证据。报告列修改位置/实际接线与资源顺序、实测命令/结果、未闭环及模拟标记。无Git提交/推送/reset、Bridge/另派Agent或下一Task。完成停止交主Agent独立QA；QA FAIL交回同Implementer定向修复并在docs/v1/v1-06/fixes/records关联Task/问题/提示词，原记录不覆盖。
