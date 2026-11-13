# 04 HITL、Checkpoint与模拟退款整阶段执行任务

日期：2026-11-12。用户已明确授权开始04。本文仅汇总冻结[D04](04-hitl-checkpoint-refund-detailed-design.md)和[唯一路线图](development-roadmap.md)的既定任务、依赖与门禁，不新增规划或改设计。以D04完整正文及最新冻结确认记录为准，历史管理key/未冻结文字不构成当前要求。

## 1. 起点、协作与保护

01～03均ACCEPTED；03交付62b5eb2及回执50e4c55已推送并核验real-model-chat，完整真实库137项及27个不同外部场景验证，03-QA-001/002关闭。当前HEAD为50e4c55476e714ed1e6d692511d8d878108c399b，schema3，生产装配仍用InMemorySaver，Refund/Knowledge为不可用骨架，不能据已有依赖宣称持久恢复已实现。

复用Task/Run/RunScope/Gateway/身份与Session、同一Registry/Policy/Executor、Order与数据异常边界、父子白名单、图内run_finish及独立SSE生命周期。主Agent串行组织执行→独立QA→必要修复→复测；规划待命，Bridge维护独立。执行会话不调用其他会话或Bridge，不Commit/Push。04完成统一交付，正式验收、归档及05切换须用户决定。

工作区原六项差异按归属保留：general.py、旧01/02/architecture文档删除、D01历史注释差异和独立Bridge文档。不要覆盖主Agent拥有的04协调记录。AGENTS第10节工程纪律适用；保持既有RISK-02-CRED/P3-01决定，暂缓换密，后续输出继续脱敏。

## 2. 原六Task与固定实施依赖

| Task | 冻结目标 | 主要交付 |
| --- | --- | --- |
| 4.1.1 PG Saver装配 | 独立小池、显式setup、sync落盘、真实嵌套快照与恢复语义核实 | checkpoint资源/脚本、lifespan、实际框架验证 |
| 4.1.2 安全Resume入口 | 同Runtime门禁，四类受理、当前上下文、repair-binding及状态查询 | 原Runtime/Service/API扩展，不建第二恢复器 |
| 4.2.1 模拟退款事实 | 两表/约束、稳定operation/调用、准备与真实模拟退款事务、结果核对 | 最小Refund领域/数据服务及迁移 |
| 4.2.2 审批存取与身份 | 本地审计Actor、只读八字段视图、30分钟、原子决定/绑定 | ApprovalService/Repository/Router，认证延期 |
| 4.3.1 RefundAgent中断链 | 分节点、原call/Gate、同Executor、固定事实回复 | 实际Refund子图和主图接线 |
| 4.3.2 重启及重放验收 | 真PG与完整进程重启、响应/快照失败、原operation安全核对 | 可复核故障、并发及重启证据 |

实施顺序严格为 `4.1.1 → 4.2.1 → 4.2.2 → 4.1.2 → 4.3.1 → 4.3.2`。一个一级阶段连续完成全部依赖满足的Task，不逐Task请求用户确认。普通实现问题自行解决；冻结契约冲突、无法验证的框架假设或必须扩大范围交主Agent说明，不擅自改方案。

## 3. 必须落实的设计边界

- 先核对本地已安装API/源码并做真实PG小探针：AsyncPostgresSaver独立autocommit池，显式setup，专业图继承父Saver，durability=sync，真实namespace/Interrupt.id，根Command到原child、wrapper重入及当前context传播，Gate后原图续跑实际形式。库版本适配保持最小，不整体升级/复制引擎；不能未经验证假定ainvoke(None)会跳过写节点。
- 业务迁移用下一空闲004，保留001～003。仅refund_requests/approvals及所需订单复合约束/索引，按D04字段、同值task/workflow、主体、绑定空值组、状态/结果CHECK和唯一成功operation规则。Saver表及setup独立，不复制其DDL，不在普通启动/恢复中自动setup，不降级内存。
- 本人paid且未退才可准备全额模拟退款；金额/币种取锁内事实。申请/审批登记不退款。固定锁序订单→申请→审批，执行事务再次核验全部主体/决定/有效期，订单标记与SUCCEEDED结果同事务。原operation成功优先复用，不因已退款或后续审批过期误拒；不同operation不能再退。
- 六种工具按D04第5.1节装配同Registry/Policy/Executor：模型仅refund_order，读取/资格/准备/审批登记/关闭为固定node来源并限Task/节点/参数。退款原call保持origin=model，原name/version/id/raw/canonical不变，禁止用node来源绕过审批。数据层不反向依赖工具/Graph。
- assess/prepare_attempt/execute_prepared复用同一执行路径，准备拒绝零尝试；VerifiedApproval由可信存储核验，不是客户端Schema或通用放行票据。每次执行重检Policy，事务再检业务，不改approval_required，不设approved/skip_policy。handler仅接按D04投影的可信最小业务关联。
- 按D04第7.2节拆分实际节点与sync边界；plan只产单个合法refund_order调用，坏/多/混合调用整批零准备。原AIMessage/调用先落盘，申请/审批/等待/准备尝试/实际执行分节点。Gate固定位置无条件interrupt，不吞中断，不发假终结ToolMessage。
- 等待前冻结主动时间并持久累计用量，真实等待不走普通Response/run_finish。Runtime从有效child及真实中断解释状态，绑定真实interrupt/ns/checkpoint后才公开可恢复等待；绑定失败用原门禁repair-binding，不新Run/图执行/申请，不让客户端指定绑定。
- Resume区分真实pending interrupt、Gate后安全next、正常END和未知。Command只用于真实等待；安全后段通过当前refund_recovery和原图节点守卫先核对operation，成功只复用结果、退款写副作用尝试为零；确认未执行才经再检及本Run新标记sync后尝试；unknown停止，不用goto/update_state/新Task绕过。
- task/workflow/thread/user/原call/application/operation稳定，resume新run有效上下文必须传播到原child及结果。用量继承有效child，未知尝试/时长按D04保守记账并标不完整，不重置额度；正常结算仍图内一次。
- 审批仅development/test本地演示Router与服务端LocalDemoApprovalActor（local-demo-approval），production不注册且不创建Actor。不恢复旧admin key/Header/RBAC，不宣称本地Actor是真认证。普通聊天/模型/请求reviewer不授予审批或恢复。
- D04第8.2节全部API、八字段只读视图、幂等决定/30分钟DB时间、显式decision后resume、repair-binding、本人current task/退款status均落实。PENDING惰性过期只在POST事务，GET零写；APPROVED过期保留原决定且零新效果；相同决定先幂等识别，保留原人/时间/期限。
- 新paused/resumed及状态、安全SSE沿既有所有权；受理后独立执行，HTTP断开不取消。公开摘要只由可信事实固定模板生成，区分业务SUCCEEDED与技术失败，不输出私有工具历史/凭据，不误导重新申请。

## 4. 环境操作与验证授权

本阶段授权按冻结任务在已配置、此前授权的私网VM开发库及专用测试库执行必要的显式004业务迁移和checkpoint setup。先核对目标/current_database/current_user及现有版本/checksum，记录实际执行；无重建容器/数据库/Volume、清空全表或改密码授权。不要混用业务事务池与Saver池，不改既有迁移内容。

自动测试、故障注入、完整进程重启与真实模型验收只使用专用agent_demo_test及本轮唯一标识的数据/thread。保持原五订单及已有用户数据，不用重跑种子恢复退款。为测试创建独立订单/会话，按FK与checkpoint线程精确清理自己的记录；前后核对完整行集/迁移记录及必要Saver范围，框架setup新增结构如实记录。不要为测试接触应用库事实。

使用项目.venv，默认pytest保留脱敏插件和fd捕获，不默认付费。先运行有意义的受影响用例，阶段整合一次完整真实库回归、lint/执行代码format，依赖变更才同步锁及pip check。04验收必须有真实PG Saver和完全退出/重启Python进程证据，Mock或内存interrupt不替代；D04第15节24项矩阵逐项提供证据，含拒绝、过期、并发、repair-binding、四类resume、next=execute_refund故障窗口和预算保守核对。

冻结标准中的真实模型联调另做必要少量显式验证，使用现有provider/model及测试订单，实际源表/审批/原调用对照，不能只凭模型说成功。默认回归无付费请求，报告准确区分Mock、真实模型、真实PG及真实进程。所有探针安全捕获，禁止凭据、连接URL、原始敏感异常输出。

## 5. 交付与停止

报告保存 `docs/04-hitl-checkpoint-refund-delivery-report.md`：逐Task实际文件/接口、框架恢复调用与namespace证据、迁移/setup、命令/通过失败跳过、完整重启及故障矩阵、数据清理、真实模型证据、设计偏差/未验项和05接口交接。维护README/协议/配置示例及D04实施索引，保留冻结正文/历史证据，主Agent协调记录由主会话维护。

完成后回复交付报告路径及摘要并停止，交独立QA。05 RAG/Store、管理员真实认证、真实支付、通用生命周期/分布式调度均不在本阶段；不能因部分实现或自测通过自行正式验收或提交Git。

## 6. 实施期迁移修正裁决（2026-11-12）

执行初轮发现自编004的审批主体CHECK允许JSON null，已应用测试库，开发库尚未应用。主Agent复核确认是本阶段实现缺陷，按用户已授权的阶段内普通问题自处理执行，不改变冻结设计、不新增Task，不再向用户重复请求实施许可。

保留001～004原字节及已登记校验和，追加005定向约束修正，严格拒绝缺键、JSON null、非字符串、空字符串及task/workflow不一致的主体，允许有效非空同值字符串。先做受控真实PG约束验证/回滚，再核对两库身份与既有行；无不合格已有记录时，显式将开发库推进004/005、测试库推进005，数据保留，最终期望版本随实际迁移同步。发现他人不合格记录不得擅自清理，应报告。不得改004历史、篡改校验和或手工DROP重建表。

完成修正后继续本任务剩余六Task，报告保留实施问题及修正证据，阶段仍IN_PROGRESS。此裁决仅在既有04数据库/业务范围内，不是05 RAG阶段启动或扩大环境操作授权。

## 7. 第三轮数据/审批模块后的续接范围（2026-11-12）

当前开发报告已记录退款领域事务、ApprovalService/Actor、list/detail/decision Router和未注册的退款工具定义。can_resume临时false，正式退款工具未注册，尚不满足4.2.1/4.2.2接线及整体门禁；不得据这次部分交付启动阶段独立QA。

下一轮沿原Task连续补齐：先实现同一ToolPolicy/Executor的VerifiedApproval读取、固定node来源与Task/参数白名单、最小RefundBusinessContext投影、assess/prepare_attempt/execute_prepared及可持久尝试标记；保留03普通工具路径并验证拒绝零handler、当前批准/预算再检和写零重试。然后按D04第9节落实原Runtime四类resume、repair-binding、动态can_resume、当前effective run/context及保守用量，复用原thread/容量/RunRecord/独立执行，不建第二Runtime。随后接第7.2节Refund完整中断/安全重入图及SSE，再做4.3.2完全进程重启/SQL成功后checkpoint失败/真实模型+PG验收。每一项仍属原六Task，不新增规划或用户批准点。

执行会话容量不足时可如实交接当前模块，主Agent继续串行安排，直到整阶段实现及验证齐备；部分自测不能标阶段完成。数据保护、冻结设计、原迁移不可变、主Agent协调文件保护及禁止05/Commit/Push等约束保持。
