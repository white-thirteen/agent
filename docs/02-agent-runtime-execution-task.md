# 02 AgentRuntime 与 Supervisor 整阶段执行任务

本文件供用户人工转交独立执行会话。用户已批准01正式验收、归档及进入02。当前02尚未由专业执行会话启动，本任务被人工转交后按整阶段实施，六个Task按依赖连续推进，阶段交付后进入独立QA。本文不创建或调用其他会话。

## 1. 起点与验收事实

工作区为 `D:\py\agent-project\agent`，分支为 `real-model-chat`，跟踪 `origin/real-model-chat`。

| 归档 | Commit | 说明 |
| --- | --- | --- |
| 前序Baseline | `f89db15efc9b38e88bfed6a725abde76575c6bae` | Establish Baseline - Supervisor Graph and Frozen Design |
| 01交付 | `cf3e763e96f290dad4bb011e778bbcdf7c6c81d6` | Complete Phase 01 - Foundation and Environment |

两个提交各45个变更路径，已推送且核实远端分支指向01交付提交。01为ACCEPTED。Baseline独立快照55项通过，Delivery完整真实测试库82项通过、无失败或跳过；应用入口、实际socket启停、资源释放、链接和锚点检查通过。P2-01标识NUL缺陷已修复并独立回归关闭，P3-02状态冲突已闭环。真实模型沿用01开发及首次独立QA成功证据，快照验证使用受控模型。

01当前HTTP只完成身份/session准备，随后返回JSON503 agent_not_ready。正式Task受理、Graph执行、SSE和状态查询由本阶段接通。持久Session已实现，Graph仍为内存Saver。

## 2. 必读与工作区保护

先读根AGENTS.md及适用子目录规范，再依次读取README、项目定位、唯一development-roadmap、D01及末尾交付、D02完整详细设计。Graph旧协议仅作当前代码参考。按接口依赖参考D03～D06，历史九阶段不构成当前任务。

尤其核对以下记录。

- [01主Agent复核](question/01-foundation-main-review.md)、[正式验收建议](question/01-foundation-stage-acceptance.md)。
- [独立回归](question/01-foundation-regression-report.md)、[修复报告](resume/record/01-foundation-fix-report.md)。
- [归档提案第10～11节](question/01-git-archive-proposal.md)，以及本机 `D:\py\agent-project\archive-validation-20261110-01\git-archive-receipt.json`。

已确认的冻结状态以AGENTS/README最终收尾记录及本次授权为准。D02页首和历史表的“待冻结/未授权”保留旧轮次语境，不再等待设计确认，不重新设计36个Task。

开始时检查Git，不以工作区必须干净作为启动条件。归档采用暂存快照以保留原工作区，现有5个状态文档与提交树有已批准整理差异，旧01指引在Git中存在但工作区仍删除，另外两份旧文档删除及general.py未跟踪继续暂缓。具体为AGENTS、README、D01、定位、路线图的文档差异，以及三个旧文档路径的删除和general.py。用户在当前主会话的新协调记录也可能产生文档增量。

核对这些已知差异的来源后继续开发。可逆地同步本阶段需维护的状态/导航，同时保留历史记录。暂缓文件的恢复、删除和用途处置不自动纳入02。禁止批量checkout、reset、clean、覆盖其他会话修改或自行Commit/Push。其他worktree须先明确同步基线和授权文件，不能仅拿空脚手架开始。

## 3. 本阶段范围和依赖

以 [D02完整设计](02-agent-runtime-detailed-design.md) 为接口、行为及验收依据，按以下顺序完成整阶段。

| 二级环节 | Task | 本轮交付 |
| --- | --- | --- |
| 2.1 State与Supervisor收敛 | 2.1.1 类型/State适配Demo | 角色/任务迁移、可信Task关联、消息范围、任务累计预算及new/continue输入 |
| 2.1 State与Supervisor收敛 | 2.1.2 Supervisor与澄清 | Gateway路由、两类澄清、能力拒绝、有限上下文与结构纠正 |
| 2.2 三专业骨架与主图装配 | 2.2.1 主图与专业接入 | 三专业最小子图、外部注入Saver/Gateway、白名单映射、run_finish |
| 2.2 三专业骨架与主图装配 | 2.2.2 公共结果与骨架验证 | 澄清/结果/错误映射、唯一Response、图内普通结算及编译路径验证 |
| 2.3 轻量Runtime和SSE | 2.3.1 独立执行与互斥 | Runtime受理/Task/Run/Scope、thread门禁、去重/预算/退出及结果保留 |
| 2.3 轻量Runtime和SSE | 2.3.2 SSE和状态语义 | 单订阅所有权、请求级清理、安全事件、状态查询与无重放重订阅 |

依赖为01 → 2.1.1 → 2.1.2 → 2.2.1 → 2.2.2 → 2.3.1 → 2.3.2。2.2可使用受控上下文验证，随后在2.3接实际Runtime。阶段内部正常实施和必要修复无需逐Task请求确认。冻结设计的实质冲突或范围扩展交主Agent裁决。

## 4. 必须复用的01接口

- `app/runtime/context.py` 的DemoIdentity、DemoContext、SubmitOptions保持唯一。Route单次解析，Service.prepare_chat返回(context, options)，submit_chat显式转交Runtime和订阅owner。
- SessionRepository的稳定thread绑定为权威，同会话顺序任务复用该thread，停止旧Runtime自行重算线程的正式调用路径。沿用PG17/既有迁移和连接资源管理。
- ModelGateway及ModelCallLimits/ModelCallUsage保持任务累计尝试次数、单次超时/额外重试、失败快照和unknown/null用量语义。新节点调用经Gateway，成功和ModelCallError均adopt最新快照。
- RunLimits/RunUsage沿用01定义。Runtime落实主动时间及任务累计预算，工具次数由03接入，不建设第二套预算规则。旧Run不会使同Task额度归零。
- 继续现有消息Reducer、contracts/transfers/router与formatter，按D02迁移，保留关联、结果事实及来源边界。

## 5. 核心实施契约

### 5.1 角色、State与Supervisor

迁移AgentType为SUPERVISOR/ORDER/REFUND/KNOWLEDGE，TaskType按D02第4.4节为CLARIFICATION/ORDER_QUERY/REFUND_APPLY/KNOWLEDGE_QA/MEMORY_MANAGE，同步旧AfterSales、REFUND_REQUEST和取消执行入口，不保留重复角色或旧执行别名。

仅Runtime在受理门禁内新建正式task_id，workflow_id直接等于task_id。澄清续接加载原Task，新Run继承全部预算。create_turn_state不隐式生成Task，新任务清任务槽/用量，continue保留PendingTask、task_message_ids及累计快照，每轮清临时结果。预算为覆盖快照，消息用add_messages。

CLARIFICATION未知目标可在后续识别为具体任务，保持Task。已知业务补参保留原目标。unsupported按D02区分通用任务拒绝和具体PendingTask下的边界回复，不暗中终结原目标。上下文仅本任务最近12条允许公开Human/最终AI及PendingTask，过滤工具、推理、带tool_calls的AI及敏感元数据。结构纠正最多一次并消耗原任务模型额度。

### 5.2 三专业骨架及普通结算

三个真实骨架各为 `START → check_contract → capability_unavailable → map_result → END`。合法输入统一SpecialistResult.failed及capability_unavailable，错关联拒绝。目标领域图的完整业务节点留03～05，不建立空handler、Gate或Retriever以凑拓扑。

builder在启动时编译，显式注入Gateway、三个专业图及InMemorySaver，health/README明确checkpoint_backend=memory。wrapper只映射白名单，核验user/conversation/task/workflow/当前run/目标，私有历史不复制到公共State，可信用量不归零或重复相加。

唯一Response追加批准公开AI，专业map_result不发布公共终态。普通路径由主run_finish冻结时钟、返回最终Task/预算State更新后进入END。Runtime图后只收敛记录/事件/释放，禁止第二次常规update_state。终结或快照提交失败保留execution_uncertain。未来真实interrupt独立控制流，02不实现审批恢复。

### 5.3 Runtime受理、预算与退出

Service只准备候选run_id和上下文。Runtime在同thread门禁中判定新建/续接、去重、容量及状态迁移，再登记RunRecord/初始订阅/owner并创建强引用asyncio.Task。无await登记区按D02保证受理及所有权完整，取消发生在未受理await时清理记录并释放门禁，受理后执行由Runtime持有。

同thread第二执行立即409，跨thread最多8活动Run，满载503。request_id键包含user/conversation/id，指纹message/input_mode，命中复用原Run，异指纹409，缺省不按文本去重。等待审批/暂停普通输入拒绝，failed自动重试拒绝，不可信快照或未完成节点不能当空会话或盲重放。

RunScope只持本次可信不可变快照，任务主动时间跨Run累计，人工等待不计入。模型失败/重试/纠正均累计，超时或意外异常保留能确认的用量并标incomplete/uncertain。终态保留1800秒/最多100条，活动Run不按TTL清理，uncertain阻塞不随Run过期清除。shutdown先停受理、最多等5秒、再取消并await收敛，随后关闭模型/PG资源。

### 5.4 SSE、状态与请求生命周期

采用D02第7节三个接口，chat为提交，status/events仅查询或附流。

- `POST /agent/chat`。
- `POST /agent/runs/{run_id}/status`，body为user_id/conversation_id。
- `POST /agent/runs/{run_id}/events`，body同上。

沿用普通身份辅助函数和body唯一解析，不引入身份Header/Query。公共事件只投影status/token/error/done及run_id/task_id/workflow_id/sequence，屏蔽内部thread/scope、原始状态/消息/工具参数。token只来自批准最终回复，允许整段文本。done表示本Run结束，needs_input仍保留Task。

每Run最多一个当前订阅，容量64，非阻塞发布，满队列释放订阅并唤醒消费者，执行继续。SubscriptionOwner及请求级ASGI guard覆盖handler、响应构造和完整response调用。submit前建立owner，Runtime无await登记subscription_id，清理幂等且只匹配自己的旧ID。必须覆盖生成器首次迭代前断开、响应头异常和旧owner晚清理，不另建receive竞争监听器。

重订阅先当前安全快照再未来事件，已终态仅快照及该订阅done，不重新执行、不补发旧token。非空Last-Event-ID返回409 event_replay_not_supported。错误用户、过期及未知Run统一404。按D02保留单订阅冲突、busy/stopping、uncertain/state_unavailable及开流前后错误边界。

## 6. 模块与文件职责

Route → Service → Runtime → Graph的依赖方向保持。runtime/models、run_scope承载执行元数据及本Run协调，State中不保存task/queue/客户端等活资源。specialists下仅添加order/refund/knowledge最小builder。streaming/subscription及必要response guard处理订阅生命周期，避免通用Broker/middleware平台。main统一装配、先关Runtime再关外部资源。config/.env.example仅增加本阶段有实际调用者的设置。

01的schema和NUL修复、配置输入隐藏、普通scope及production禁用均保留。真实.env/凭据不入代码、日志、文档或Git。P3-01对应本阶段修改的Supervisor Prompt E501、Response及旧Runtime格式可定向处理，剩余设计示例格式保留归属，避免全仓格式化。

## 7. 后续边界

03才实现Registry/Policy/Executor和模拟订单事实查询，04才实现PG Checkpointer/可信本地Actor审批/原ToolCall恢复/退款幂等，05才实现真实Embedding/pgvector/RAG/Store及MemoryManager，06做完整演示。02不创建业务表、持久Task/Run平台、退款或记忆副作用，不公开pause/resume审批端点，不以InMemorySaver声称重启恢复。

保持单worker、单专业串行分派。订单取消、真实支付、企业认证、分布式调度、事件重放、复杂工具披露和V2 MemoryWriter均不在02执行范围。内存Run/query存在保留窗口，状态未知不能表示业务从未执行。

## 8. 验证及阶段交付门禁

使用项目`.venv`解释器及实际安装版本签名，默认测试用受控模型。先运行受影响用例，公共入口集成完成后运行必要完整回归及Ruff，依赖变化才执行相应依赖一致性检查。真实库只使用专用测试库、核实目标/精确清理，沿用01环境而不重建。付费模型调用单独显式组织并记录，不加入默认回归。

按D02第11.2节验证下列可观察行为，重点风险使用少量有意义测试。

| 门禁 | 必须有的证据 |
| --- | --- |
| 两类澄清 | 通用到具体保持Task/换Run/预算延续；具体目标补参及合法new_task |
| 路由与骨架 | 取消明确不可用、非法输出有限纠正、三骨架真实编译并返回失败、无假业务事实 |
| 隔离及普通结算 | 父子关联校验、私有消息不外泄、临时结果清理、run_finish一次普通结算、END后无第二次常规写回 |
| 执行与去重 | 同thread冲突、不同thread并发、容量满、request_id命中不重执/异指纹拒绝、预算跨Run继承 |
| 订阅生命周期 | 迭代前断开、构造/响应头失败、消费中断开、慢队列及旧owner晚清理，执行继续/新订阅可建立 |
| 真实HTTP断开 | 至少一次实际连接取消验证，不只关闭生成器；核对任务仍执行及最终结果可查 |
| 查询与事件 | user隔离、快照加未来事件、每有效订阅最多一次done、非空Last-Event-ID拒绝、TTL及终态数量限制 |
| 失败与释放 | 模型/预算/快照失败安全收敛及uncertain，production禁用，shutdown有界且自有资源关闭 |

已有82项是01基线，02改变公共契约时按设计更新测试，说明变化原因，不以维持数量代替验收。不删除测试或弱化断言掩盖真实失败。专业业务、真实HITL重启及RAG/Store验收由后续阶段独立执行。

## 9. 交付报告与停止点

持续更新D02实施记录和实际README/OpenAPI/Graph协议，历史设计不整体覆盖。完整交付报告保存到 `docs/02-agent-runtime-delivery-report.md`，包含每Task实现、实际文件/接口、测试命令/结果和真实资源边界、设计偏差、未完成及问题编号、后续交接、工作区变更归属。注明基线Commit及新增协调文档的来源。

完成全部六Task及开发自测后，将报告路径交用户带回主Agent。主Agent随后审核并安排独立QA；执行会话不宣称阶段ACCEPTED，不启动03或自行Git归档。修复会话如后续需要，其提示词仍放docs/resume，修复记录放docs/resume/record。
