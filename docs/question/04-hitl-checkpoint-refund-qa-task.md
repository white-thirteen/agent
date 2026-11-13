# 04 HITL、Checkpoint与模拟退款独立QA任务

仅在执行交付完成并由主Agent核对后派发。依据AGENTS、冻结[D04](../04-hitl-checkpoint-refund-detailed-design.md)第15节全部24项门禁、[既定执行任务](../04-hitl-checkpoint-refund-execution-task.md)及届时[开发报告](../04-hitl-checkpoint-refund-delivery-report.md)。03已ACCEPTED，交付62b5eb2/回执50e4c55；04未正式验收，05未授权。

## 1. 独立性与工程边界

读取实际实现、相关01～03契约和实际安装LangGraph接口。核对执行报告的命令/覆盖可信度，不凭文件存在、Mock中断、依赖安装、测试数量或模型成功文字判定完成。保持业务/仓库测试/配置/依赖/迁移/冻结设计，独立补测放仓库外，只新增本轮QA报告。主Agent派发前后核对受控文件摘要。不要调用Bridge/其他会话、修复被测代码、Commit/Push或启动05。

原六项暂缓内容/删除状态和Bridge独立文档保留，RISK-02-CRED历史暴露/密码复用、P3-01既有示例format按原决定管理；后续输出仍须脱敏。本地审批Actor不是认证，V1不提供真实管理员认证本身不列Bug；production不注册、本地受控入口/可信主体/执行再检等冻结要求必须验证。

## 2. 六Task与完整矩阵

六Task逐项核对：4.1.1 PG Saver装配、4.1.2安全Resume、4.2.1模拟退款事实、4.2.2审批存取/审计Actor、4.3.1 Refund中断链、4.3.2重启/重放。依D04实际依赖理解，不以编号机械先后制造循环。

按D04第15节24行逐项列证据、真实资源与结论，不遗漏异常门禁。特别要求：

- 真PG Saver独立池、显式setup及启动版本检查，sync边界、嵌套namespace/Interrupt.id、wrapper恢复形式与当前context实际验证；无InMemory降级、自动setup、客户端namespace或图外update/goto捷径。
- 完整停止旧Python进程再新进程加载原PG快照：原session/thread/task/workflow/call/name/version/raw/canonical/application/operation保持，新run有效上下文/用量传播，不是重发退款文本；真实中断和历史interrupt区分。
- 正常批准/拒绝/过期，未付/已退/异主、参数/主体/版本/金额篡改；读取/资格/准备/登记/关闭均同Executor，模型仅refund_order，原call始终model来源，节点调用有固定白名单。单个合法原生call要求与原ToolMessage闭合，私有历史不进SSE。
- prepare_attempt只在ALLOW时生成可持久恢复原调用的标记，成功准备sync后才执行；执行时再检批准/Policy/预算，事务再次核对，handler不持RunScope/权限/Policy或客户端approved。
- 004已在测试库应用后发现JSON null的CHECK缺陷，必须保留原迁移/校验和并以005修复；独立真实PG验证缺键/null/非字符串/空字符串/不同值拒绝、非空同值接受，最终业务版本及两库部署记录准确。
- 固定订单→申请→审批锁序与事务、operation/成功唯一约束，同操作结果优先复用、不同操作同订单只有一成功。实际写副作用次数与handler/只读核对/ToolCall重进分别观测，不能用函数调用次数代替业务效果。
- 审批八字段视图、GET零写，30分钟期限从创建起按锁后DB clock_timestamp核实；PENDING只POST惰性转EXPIRED，APPROVED过期保留决定，重复同决定保留人/时间/期限，相反决定409。decision不自动调度，显式resume再检查。
- 真实中断已保存但绑定失败：repair-binding在原Runtime门禁读最新唯一父子中断/主体、CAS补空绑定；相同幂等、冲突拒绝、忙碌409、不可用503，无新Run/图调用/审批/改期限。未绑定decision始终409。
- 四类resume：唯一真实Gate才Command；Gate后安全next无interrupt仍按原绑定/operation续跑；正常END200 accepted=false/run_id=null且无Graph/新Run；unknown拒绝可能写入的恢复。同thread并发与普通chat/new_task互斥，restart后旧run不是active。
- 重点故障：原SQL commit成功但响应/结果checkpoint失败，分别令next=execute_refund及其他安全后段；当前refund_recovery经原wrapper到child，节点在任何副作用之前消费，原成功事实只复用、零新退款写尝试；再次落盘失败仍可重核。不假定ainvoke(None)自动跳过节点。
- 确认未执行必须在当前批准/资格/Policy/预算仍有效时用本Run新attempt标记并sync，不能复用旧标记；读不到/超时/PENDING不直接证明未执行。未知预算/时长按保存基线及有限上界保守核算，usage_complete正确，不清零/补新额度；无法确认时只查事实，不继续模型/副作用。
- 等待冻结主动时间且不走普通Response/run_finish；正常图内结算一次。初始/恢复Run HTTP/SSE断开后仍独立，paused/resumed/done语义与订阅资源释放正确，业务SUCCEEDED与compose/技术失败分开且不可误导重新申请。

05 Prepared节点/Memory接口补齐按冻结D03/D04真实本期契约审查，不要求提前实现RAG/Store或管理员认证。实现布局可按需归并，不能因此忽略明确依赖方向/审批/恢复契约。

## 3. 实测及资源保护

使用项目.venv。先审查已有验证并运行有意义的受影响补测、一次完整真实库回归及对应lint/执行代码format。依赖有变才核对清单/锁/pip check。保持pytest默认脱敏插件/fd捕获；所有外部探针/子进程日志同样安全捕获，禁止凭据、URL或敏感异常全文。默认回归不调用付费模型。

真实测试仅已配置agent_demo_test，预检current_database/current_user、业务版本及checksum、Saver版本。执行方已获准显式004业务迁移、实施期005定向约束修正与Saver setup，QA核对实际结果，不自行升级/重建环境或写应用库。不更改全局时间/密码，不停真实数据库制造故障。

前后比对完整sessions/demo_orders/refund_requests/approvals及迁移记录，另按本轮thread精确记录/清理checkpoint、blob、writes或用框架安全线程删除接口。使用自身唯一订单/会话/操作/thread注入故障，按FK清理自己的记录；固定五订单和既有用户/线程状态必须保留，不能靠重跑种子重置退款。结构setup新增与测试数据清理分开记录，不把count相同当行集不变。

完全重启/同步屏障/故障窗口必须有真实PG与独立新进程证据；必要少量显式真实模型+PG联调与默认pytest分离，可核查开发方证据并按实际疑点独立复现。报告区分受控故障与真实服务、专业图与正式HTTP、进程内重建对象与真停进程，不扩大为全局Exactly Once或任意协程恢复声明。

## 4. 报告与停止

保存 `docs/question/04-hitl-checkpoint-refund-qa-report.md`。提供六Task及24行矩阵、源码契约检查、实际命令/通过失败跳过、真实进程/PG/模型及故障注入证据、独立性/数据清理/遗留。缺环境或未执行不能算通过。

问题从04-QA-001递增，按P0～P3提供设计/代码位置、稳定复现、预期/实际、影响、证据及最小修复建议，区分真实Bug、环境/配置、设计允许限制与05工作。主Agent逐项裁决再交修复，QA不自行修复或变更验收标准。完成回复报告路径、验收判断、实际测试与问题摘要，停止等待主Agent。
