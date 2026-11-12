# 03 工具治理与模拟订单查询整阶段执行任务

2026-11-11用户已批准02正式验收及归档，并授权归档后实施03。02交付为 `94cf205a734c305a6919a34cfeacc3e717d4856f`，已推送且核验origin/real-model-chat。实施依据为冻结的 [D03完整设计](03-tool-governance-detailed-design.md)及第13.2节验收矩阵，6阶段/18环节/36Task保持。本文为现有任务的执行交接，规划会话待命。

## 1. 工作起点

目录为 `D:\py\agent-project\agent`，使用项目.venv Python 3.13.7、既有安装版本及配置。先读AGENTS、README、有效定位/路线图、D01/D02交付与验收记录，再读D03全文、D02 Order目标图及后续04/05必要接口。已确认设计中的旧“待冻结/未授权”是历史轮次说明，以本次用户授权及当前协调状态为准。

02为ACCEPTED，独立119项真实库和外部3项通过。Runtime独立执行、同thread门禁、RunScope累计快照、图内run_finish、请求级SubscriptionOwner和SSE/query均已完成。P3-01剩余6份设计示例格式按既有遗留管理。RISK-02-CRED的历史凭据暴露和三角色配置密码复用为用户接受的Demo遗留，暂缓换密；保留当前pytest输出保护及其支持范围，异常、日志及交付只输出脱敏摘要。

归档后六项工作区差异有明确归属，general.py未跟踪，旧01/旧02/architecture三个工作区删除，独立Bridge设计文档未跟踪，D01缺少前次快照状态注释。它们均保留，实际Git旧01归档指引及两份旧文档仍存在。主Agent新建的03任务和协调记录属于本阶段交接。不要覆盖这些已有用户成果，不改Bridge或用户级配置、不Commit/Push。主Agent独占维护 `docs/question/03-tool-governance-main-review.md`。

## 2. 六Task顺序及职责

| 二级环节 | Task | 交付 |
| --- | --- | --- |
| 3.1 工具定义与注册过滤 | 3.1.1 Metadata/Registry | 唯一ToolDefinition/Schema/handler、注册校验、重名拒绝及启动冻结 |
| 3.1 工具定义与注册过滤 | 3.1.2 过滤与模型绑定 | 按Agent/scope及query_spec过滤的单工具完整Schema绑定，与执行集合一致 |
| 3.2 Policy与Executor | 3.2.1 Policy/Executor | 三态纯策略、完整可信执行上下文、唯一实际尝试入口及最小handler业务上下文 |
| 3.2 Policy与Executor | 3.2.2 工具消息与治理 | 批次预检/串行、原生调用保留、逐call配对ToolMessage、失败闭合和观察重进 |
| 3.3 模拟订单与OrderAgent | 3.3.1 最小模拟订单事实 | demo_orders单表、精确金额、owner SQL、小服务和幂等种子 |
| 3.3 模拟订单与OrderAgent | 3.3.2 OrderAgent查询 | 七节点真实查询闭环、确定性事实摘要、真实PG和模型联调 |

依赖按 `3.1.1 → 3.1.2 → 3.2.1 → 3.2.2 → 3.3.1 → 3.3.2` 连续实施。普通实现问题自行解决，真实冻结需求/设计冲突或必须扩大范围才交主Agent及用户决定。阶段完成后统一交付，由主Agent组织独立QA、必要修复与复测，03正式验收及04切换由用户确认。

## 3. 必须落实的既定契约

### 3.1 注册与范围

固定目录只注册真实get_order/list_orders，元数据、工具对象、args/result Schema和async handler一份权威，注册后冻结。list按Agent/服务端scope过滤并稳定排序，不返回handler；get只负责内部查找，执行仍复检。Supervisor没有业务工具。

按query_spec精确收窄曝光和执行。get仅get_order并约束确定order_id，list仅list_orders并约束确定limit/offset。禁止模型换工具、其他订单或扩分页，即使通常拥有scope。Gateway只绑定完整Schema，保留原生AIMessage/call_id/name/raw_args，不绑定可旁路执行的handler。

### 3.2 Policy与Executor

复用现有RunScope/Limits/Usage与可信ExecutionContext。ToolExecutionContext完整保留执行范围、origin/node、允许名称/版本、参数约束、权限和预算；handler只接typed args与BusinessExecutionContext的user_id/task_id/run_id，不含预算或策略对象。

Policy按D03第4节校验存在/启用/任务集合、Agent/scope、一次Schema验证及参数精确匹配、预算和风险。Executor单call/批次共用内部执行入口，每次handler前复核最新允许范围/权限/风险/预算并先递增计数。成功、失败及安全只读重试均累计，拒绝/审批阻断/未执行零计数。

工具默认超时5秒、只读最多额外重试1次、每消息最多4 calls，设置集中化。仅明确安全瞬时异常可只读重试，超时不默认重试。取消传播并停止后续handler，意外编程错误按现有Runtime收敛。结果Schema投影、安全错误、effect_status按D03实现，不能假订单不存在或空列表。03的REQUIRE_APPROVAL返回approval_not_available且零尝试，不建立审批、等待或approved/skip_policy通道。04两步写前准备及VerifiedApproval仍为后继契约。

### 3.3 批次与消息

每条AIMessage执行前验证完整call结构、invalid_tool_calls、ID非空/历史唯一、最多4 calls。结构错误整批零handler，不能随机补ID。可关联批次先经同一Executor逐call Policy预检，再按原顺序串行尝试。任一拒绝/失败/额度耗尽停止后续handler，剩余call返回not_executed零尝试并闭合消息。

每有效call正常路径恰一条稳定ToolMessage，保留原tool_call_id/name，安全内容不含原始args、owner、scope或预算内部对象。call_records保存原调用/规范参数/安全结果，observe重进只映射已存结果，不重复执行或计数。半配对历史不再发送模型；不宣称Exactly Once。

### 3.4 数据、种子及OrderAgent

复用PG17、现有池与显式迁移。当前001/002均已应用，新订单迁移使用下一个空闲编号003，这是D03明确允许的实际编号选择。保留已应用SQL。demo_orders字段/Decimal、正金额/CNY、付款及退款标记约束、owner列表索引、五条固定双用户样本、固定时区时间按D03第7节。

Repository始终参数化owner限定SQL，Service结果边界再核验归属；不可见和不存在统一order_not_accessible。返回OrderView不带owner，金额固定两位字符串，合法空页成功、数据库故障明确失败。种子显式目标、事务插入及静态事实核对，保留已有付款/退款状态，启动不自动迁移或插入。

七节点为check_request、prepare_query、select_tools、plan_query、execute_query、observe_order、map_result。get缺ID澄清、list不要求ID、歧义先澄清。领域最终摘要从本次验证facts确定性渲染，模型候选只作私有结束建议。无事实不完成，工具成功后模型预算耗尽仍按预算规则失败。主图唯一Response、run_finish及订阅生命周期继续复用02。

## 4. 实际资源与验证授权

本阶段按D03实施所需的编号DDL及固定模拟种子，可在既有已授权VM的开发/专用测试库显式执行，先核对配置目标和当前版本，保持其他库、容器及卷。既有VM为01已批准的开发环境，冻结设计中的“本地开发库”沿该已有授权环境落实，不开放任意远程目标。测试只用agent_demo_test并精确清理本用例数据。应用库仅执行本阶段显式迁移/模拟种子及必要实际演示，禁止测试以开发库为目标或重置既有模拟业务状态。

使用项目.venv，先受控模型+真实PG验证，再按D03第13.2节显式完成必要的真实模型+真实PG原生工具调用验收。真实模型不进入默认测试，控制为验证get/list及源事实所需的少量调用，记录provider/model/method、调用和源事实摘要，凭据不进入输出。供应商不兼容或环境失败时定位事实，不伪造通过。

保持pytest默认配置、fd捕获及scripts.pytest_redaction。配置/连接探针在插件外执行时也须安全捕获并只输出固定类别/布尔值/脱敏结果。历史暴露和密码复用的接受不替代未来输出保护。不打印dotenv、完整URL/密码或原始连接异常回溯。

冻结验收矩阵逐项需要Registry/Schema、曝光/执行分离、单工具/参数目标、handler最小上下文、真实owner隔离、Policy三态、尝试计数/限制、批次配对、超时/取消/观察重进、真实表/种子、订单事实一致、专业主图/预算/私有消息，以及真实模型原生工具链路证据。必要完整回归覆盖02公共行为，默认119项为起点，不以数量维持代替正确性。

## 5. 范围、记录与交付

Refund/Knowledge保持capability_unavailable。04审批/退款/持久Checkpoint/resume、05RAG/Store/MemoryWriter、订单取消/真实支付/完整物流/企业认证/分布式平台不在03实现范围。已接受遗留按既有记录管理。

维护实际README/OpenAPI/Graph协议、D03实施记录及配置示例，保留冻结正文和历史语境。交付报告保存 `docs/03-tool-governance-delivery-report.md`，逐Task说明代码文件/接口、测试命令结果、迁移及种子状态、真实模型/PG证据、差异/遗留/未验事项与04交接。完成后向主Agent回复报告路径及摘要，进入独立QA，禁止自行Commit/Push或开始04。
