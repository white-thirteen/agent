# 04 当前实现独立审查及可执行验证报告

日期：2026-11-13。本轮跨日完成，外部证据目录沿用20261112名称。依据：[QA任务](04-hitl-checkpoint-refund-qa-task.md)全文、[冻结D04](../04-hitl-checkpoint-refund-detailed-design.md)第15节24项及关联契约、[执行任务](../04-hitl-checkpoint-refund-execution-task.md)、[交付记录最新第八轮](../04-hitl-checkpoint-refund-delivery-report.md)。03已ACCEPTED；本报告是环境受阻期间的独立问题发现，不是04完整验收通过报告。

## 1. 总体结论

**当前04不通过阶段验收，不能标VERIFIED或进入05。**正式Refund图及装配确已存在，受控批准/拒绝/修复绑定/恢复链可以执行，但发现四项P1和两项P2问题/接口缺口；真实PG及退款完全重启、真实SQL/Checkpoint故障、真实模型门禁仍未完成。

- 专用测试库仅执行一次连接探针，结果为 **ConnectionTimeout**。连接前的配置目标保护通过，但没有取得连接，**current_database/current_user、schema1–5/checksum及Saver版本均未能在本轮在线核实**。未继续重连、使用应用库、改基础设施/密码或调用付费模型。
- 默认完整可控回归独立结果：**156 passed、6 skipped，44.62s，exit0**，包含第八轮最后的恢复断言。六项真实库测试的skip不能计为通过。
- 仓库外独立补测分批执行，最终共 **11个不同场景：4通过、7失败**。失败对应真实行为/报告格式偏差，没有删除失败或修改正确预期。另有一个只输出脱敏事实的诊断进程，进一步证实PENDING矛盾后被标completed。
- Ruff：`check app tests scripts`通过；`format --check app tests scripts`通过，**118 files already formatted**。未自动修复或格式化。
- 本轮独立保护清单127个文件摘要前后相等；只新增本报告。主Agent的126路径集合仍由主Agent用其原清单复核，本报告不把不同口径的数字直接说成相同集合。

已确认问题：03路径基础回归未失败；退款安全后段的业务核对、预算和消息闭合存在具体缺陷，冻结的两项查询API缺失。同一Executor的跨节点Prepared接口仍只具签名而未完整实现。pytest的skip汇总问题是既存插件中新发现的缺陷，不能归因于本次退款修改引入。

## 2. 资源与审查范围

已读取适用AGENTS、冻结D04核心接口/节点/恢复/预算/24项矩阵、执行任务、交付记录及主Agent最新协调记录。审查正式main、实际Refund builder、父wrapper、AgentRuntime、refund_checkpoint分类器、Policy/Executor/PreparedToolAttempt、Refund领域事务、ApprovalService/Actor/Router、业务迁移004/005、Saver独立池/Serializer、普通03路径及相关测试。

本地确认安装版本：LangGraph **1.2.20**、langgraph-checkpoint-postgres **3.2.0**。使用本地已安装源码核对根/子调用、sync和快照接口，不升级依赖。正式main使用AsyncPostgresSaver和明确Serializer，业务池与Saver池分开；没有发现应用自动setup或降级InMemorySaver。无资源时明确未就绪属允许行为，不作为Bug。

测试可信度：`test_refund_full_controlled.py`实际编译主/退款图，使用真实LangGraph interrupt，但模型、订单/退款/审批及Session/Saver是测试替身，ASGITransport未运行正式lifespan。它可以证明编排行为，不能证明真实SQL、PG持久化或新Python进程恢复。旧02/03测试中的Refund已显式改用tests/refund_skeleton.py；正式main注入真实Refund builder。未用旧骨架通过来判定退款成功。

独立补测保留真实Graph、Runtime、Registry/Policy/Executor、公开Router和Service协调，不mock这些核心行为。正向另使用正式checkpoint_serializer配置的InMemorySaver验证实际类型往返/原节点重进及sync故障屏障。业务效果以受控领域服务的effect_count和operation事实分别观测，明确不是实际退款SQL提交次数。

## 3. 六个Task结论

| Task | 当前实现核查 | 独立结论 |
| --- | --- | --- |
| 4.1.1 PG Saver装配 | 独立autocommit池、版本检查、显式setup脚本、严格类型白名单、main真实Saver已接入；失败不降级，退出资源栈先Runtime后依赖 | 源码及受控资源/Serializer检查成立；本轮真实PG/Saver版本、嵌套持久化和真实同步边界未验证，不能验收通过 |
| 4.1.2 安全Resume | 原Runtime有真实Gate/post_gate/ended/unknown分类、repair及resume路由，当前上下文经wrapper到child；受控repair/正常END及execute重进可执行 | 部分通过，04-QA-001/002/003影响查询及安全恢复；真实四类恢复与完整重启仍阻塞 |
| 4.2.1 模拟退款事实 | 源码有owner限定、订单→申请→审批锁序、Session/调用/金额再检、同事务订单标志+SUCCEEDED、同op结果复用及唯一成功索引 | 不能以源码代替SQL事务/竞争验证；六项真实库测试中相关项未运行 |
| 4.2.2 审批存取/Actor | 本地development/test Router、固定服务端Actor、production不注册、八字段视图、严格body、决定与resume分离；DB锁后时间判断及惰性过期有实现 | 可控HTTP/production/schema边界通过；只读查询接口缺失04-QA-001，真实期限/并发/约束/零写未验证 |
| 4.3.1 Refund中断链 | 正式18个节点确实装配，单原生退款call、准备/登记/等待/Gate/尝试/执行/核对/结果路径存在；等待冻结scope且不走普通结算 | 受控主流程成立；04-QA-002/003/004及Prepared交接缺口尚存，不能称完整验收 |
| 4.3.2 重启/重放 | 有受控图跨进程探针脚本，交付方也明确不是退款业务验收 | **未完成**：无本轮真实PG退款完全停止旧Python再恢复证据，无真实SQL提交与Checkpoint故障窗口门禁，无真实模型退款门禁 |

## 4. 实际命令与结果

解释器均为项目`.venv\Scripts\python.exe`。外部目录R：

`C:\Users\15294\AppData\Local\Temp\agent04-qa-20261112`

| 命令/入口 | 实际结果与边界 |
| --- | --- |
| `.\.venv\Scripts\python.exe R/audit04.py`（R替换为上方实际绝对路径） | exit0；保存127项摘要；仅一次psycopg专用库连接，`PG_PROBE_UNAVAILABLE_CATEGORY ConnectionTimeout`。未建立Session/订单/审批或Saver测试数据 |
| `.\.venv\Scripts\python.exe R/run_tests04.py` | 内层`python -m pytest -q --tb=short -rs`，所有测试执行到100%，但skip汇总时pytest AssertionError，**exit1**；不能当作一次正常成功回归，见04-QA-005 |
| `.\.venv\Scripts\python.exe R/run_default04.py` | 为核实默认支持路径，内层去掉-rs，`python -m pytest -q --tb=short`：**156 passed、6 skipped in 44.62s，exit0**。因上一条发生真实报告失败才复跑；未改测试/插件 |
| `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q R/test_review04.py --tb=short`（当时4项） | **3 failed、1 passed in 10.59s，exit1**：权限撤销配对、PENDING矛盾、预算恢复失败；repair/正常END通过 |
| 同上加`-k 'same_limits or execute_refund_reentry'`（当时6项） | **1 failed、1 passed、4 deselected in 9.53s，exit1**：同配置保守预算再次失败；严格Serializer原execute节点成功事实复用通过 |
| 同上加`-k 'frozen_readonly or skipped_report'`（当时9项） | **3 failed、6 deselected in 10.61s，exit1**：两项冻结查询API404、skip longrepr形态被破坏 |
| 同上加`-k sync_marker`（当时10项） | **1 passed、9 deselected in 10.38s，exit0**：尝试标记同步保存失败，退款handler零次 |
| 同上加`-k refund_resume_tcp`（最终11项） | **1 passed、10 deselected in 7.59s，exit0**：真实本机TCP订阅断开，恢复Run继续完成，订阅释放，effect_count=1 |
| `.\.venv\Scripts\python.exe R/diagnose_pending.py` | exit0；保存pending-evidence.json：真实编译图child.next=compose_refund_reply且保存成功fact；核对服务改报PENDING后，resume HTTP202、Task completed、模型额外1次，effect_count仍1 |
| `.\.venv\Scripts\python.exe -m ruff check app tests scripts` | exit0，All checks passed |
| `.\.venv\Scripts\python.exe -m ruff format --check app tests scripts` | exit0，118 files already formatted；没有format写回 |

上表R为避免重复长路径而使用的文字缩写；实际执行均为R目录下对应绝对路径。没有宣称最终11项文件曾一次整套执行；各新增用例只在对应批次运行。第二个预算场景使用**相同0.5秒任务预算**，成功尝试中10ms受控延迟使保守追加后的主动时长耗尽，排除首个场景恢复前降低配置限额的影响。

六项skip为：真实迁移/checksum/回滚、真实Session并发重开、真实订单约束/隔离/种子、真实approval主体约束、真实退款准备、真实审批/退款事务并发。默认子进程撤去显式AGENT_TEST_DATABASE_URL，按既有fixture跳过；未伪造真实库通过。源码核查后确认订单真实库用例会调用种子并临时更新固定订单，本轮未启用该用例或任何种子脚本。

## 5. 问题清单

### 04-QA-001 / P1 / 缺实现：冻结的current-task及退款事实查询API未注册

- 设计：[D04第8.2节](../04-hitl-checkpoint-refund-detailed-design.md:466)规定POST `/agent/tasks/current`及`/agent/refunds/{application_id}/status`；第11/12节及矩阵第24项要求技术失败时仍可查询真实退款事实，重启后不把旧Run当active。
- 代码：[agent Route:48](../../app/api/routes/agent.py:48)只有run状态查询，其他为chat/events；[workflows.py:5](../../app/api/routes/workflows.py:5)仍是空Router；main未注册两项相应接口。
- 稳定复现：外部`test_frozen_readonly_status_endpoints_are_present[current/refund]`，先通过实际编译图创建有效退款等待/绑定，使用同一dev-user和conversation，分别POST上述冻结路径；均404，预期200当前Task或本人申请/审批/结果视图。
- 影响：普通用户不能按设计读取真实等待/安全后段或退款结果；RunRecord只在内存，重启后旧run查询也不能替代持久业务查询。现有八字段审批视图不包含完整退款事实，不能替代这两项接口。此项不只是缺测试。
- 建议：按既定Route→Service→原Runtime/领域只读路径补齐，验证会话/owner、有效父子状态、无Session新建/写入，其他人/不存在统一404；不创建新生命周期平台。

### 04-QA-002 / P1 / 恢复缺陷：PENDING与已保存成功结果矛盾仍自动续跑并完成

- 设计：D04 9.4.1明确PENDING/超时/读不到本身不足以证明未执行；9.4.2(4)要求未执行结论与已持久成功结果节点矛盾时拒绝；unknown不能自动推进模型或副作用。
- 代码：[Runtime:380](../../app/runtime/agent_runtime.py:380)将所有PENDING直接映射not_executed，只对`next=execute_refund且无marker`特别拒绝；[Refund guard:133](../../app/graph/specialists/refund/builder.py:133)只处理succeeded/unknown，not_executed不检查State已有成功fact；compose/map继续使用旧成功数据。
- 稳定复现：`test_postgate_pending_contradiction_must_not_complete`。正常批准，受控领域产生成功fact后，compose故意抛ValueError；**真实编译图**保存child.next=compose_refund_reply和execution_result。随后只将受控operation核对结果设为PENDING，调用原HTTP resume。
- 预期：409 execution_uncertain，无新Run/模型/写入，保存矛盾现场。实际：HTTP202，原Task继续后completed，模型额外1次。`pending-evidence.json`保存了这些固定字段；effect_count仍1，**未观察到第二次退款，问题是矛盾事实被自动接受并报告完成**。
- 证据边界：PENDING由受控领域查询模拟，是针对冻结要求的矛盾快照/业务结果测试；不是声称真实原子事务通常会自然产生此状态。真实get_operation源码确实等待订单/申请锁，但这不免除Runtime对当前快照矛盾的拒绝。
- 建议：分清可证未执行与仍未知；结合当前安全节点、已有结果/消息和标记校验一致性，矛盾拒绝。不要仅按status字符串赋予not_executed许可；后续新尝试仍须当前资格/批准/Policy/预算及sync新标记。

### 04-QA-003 / P1 / 预算缺陷：保守时长已耗尽仍调用摘要模型

- 设计：D04 6.4及9.4.2(5)：未知窗口保守追加，usage_complete=false；额度/时长不确定时只报告确认事实和待核对执行状态，不再发模型或副作用。
- 代码：[Runtime:387](../../app/runtime/agent_runtime.py:387)仅在not_executed分支拒绝预算耗尽；[Runtime:742](../../app/runtime/agent_runtime.py:742)scope已耗尽时没有设置外层deadline；[compose_refund_reply:523](../../app/graph/specialists/refund/builder.py:523)没有检查剩余主动时间/预算就调用Gateway。Gateway自身模型次数限制不能代替任务主动时间。
- 稳定复现：`test_same_limits_conservative_success_budget_is_enforced`使用正式Serializer及实际编译图，首次与恢复始终同一RunLimits(0.5,12)。成功尝试中10ms受控延迟，compose失败留原快照。下一Run按旧marker保守追加单次上限后，remaining_active_seconds<=0、usage_complete=false。
- 预期：只复用已确认退款事实，不发新模型。实际：模型记录从2增至3，退款effect_count仍1。首个降低限额场景亦失败，但结论以前述**未改预算配置**的用例为主要证据。
- 建议：在安全后段区分纯事实/消息映射与模型执行；耗尽或无法可信界定时阻止模型及写入，保留确认业务事实。不要给新Run新额度或用无deadline执行替代预算核对。

### 04-QA-004 / P1 / 消息契约缺陷：权限撤销后未闭合原ToolCall即调用compose

- 设计：D04 7.2、矩阵第13项及D03原生消息契约：非等待结果须以原call_id稳定闭合；失败/权限拒绝不能向模型传半配对历史，不能为关闭申请绕过Policy。
- 代码：[record_rejection:503](../../app/graph/specialists/refund/builder.py:503)关闭工具非success时直接返回error，未创建原call的ToolMessage；其条件边仅failed转map_result，rejected仍进入[compose:523](../../app/graph/specialists/refund/builder.py:523)。
- 稳定复现：`test_revoked_scope_closes_native_message_before_model`。批准后从当前scope resolver撤销refunds:request，显式resume。recheck及关闭工具均被Policy拒绝；真实退款尝试0，但RecordingProvider实际收到下一次模型请求，包含原AIMessage退款call、**没有**其ToolMessage。
- 预期：安全拒绝/失败并闭合原调用，或停止模型；不绕过权限执行关闭。实际：半配对消息被送入compose。受控Provider允许该输入；真实供应商可能拒绝协议，这一供应商错误推论本轮未付费实测，不能写成已测到HTTP400。
- 建议：统一非等待终结消息映射，关闭业务失败与原call安全闭合分别处理；即使无权限/预算执行关闭，也不得调用模型消费未闭合历史，私有调用仍不入公共SSE。

### 04-QA-005 / P2 / 既存测试设施新发现：-rs跳过汇总被脱敏插件破坏

- 代码：[scripts/pytest_redaction.py:66](../../scripts/pytest_redaction.py:66)将所有longrepr转换为str；skip的原生tuple因此丢失。collectreport:73也有相同无条件转换形态。本轮没有修改该插件，属于既存行为，不称为退款代码新引入。
- 稳定复现：本轮`pytest -q --tb=short -rs`在六项skip汇总阶段退出1；安装pytest的`_folded_skips`要求tuple，触发AssertionError。独立`test_skipped_report_keeps_pytest_native_shape`用无秘密的synthetic.py tuple直接调用实际插件，确认被转成字符串，断言失败。
- 预期：保留pytest原生报告形态，只脱敏其中敏感文本；-rs是正常pytest汇总选项，不在当前插件声明禁止的输出配置中。实际：测试已到100%后无正常总结果/skip原因汇总。
- 影响：环境受阻时无法可靠使用详细skip报告，exit1易与产品失败混淆；默认不带-rs的156/6路径仍正常。未观察到本轮凭据泄露。
- 建议：针对tuple保留结构并逐文本脱敏，维持普通异常/捕获/告警保护，补无真实凭据的skip汇总回归；不得禁用脱敏或仅隐藏summary来“修复”。

### 04-QA-006 / P2 / 冻结交接接口缺实现：Prepared入口仍硬编码只允许退款model来源

- 设计：D03第5.1及D04第5.2/6.4已汇总同一Executor的execution_context/business_context可选参数、node准备/目标配对与业务关联标记，明确是本期两步入口的接口补齐；Memory四态、Manager/Store及实际调用仍归05。
- 代码：[Executor:117](../../app/tools/executor.py:117)对任意非空execution_context/business_context直接拒绝，又要求call.name=refund_order、origin=model；execute_prepared:195也同样只收退款/model。元数据字段/函数签名存在不代表该分支已实现。第四轮交付记录曾明确承认此缺口，最新源码仍如此。
- 复核方式：直接检查上述不可达条件及Policy固定node集合，任何提供跨节点上下文的调用都在执行前返回tool_not_allowed，无法得到设计要求的node标记/执行路径。**本项为源码确认的接口缺实现，未运行Memory/Store或虚构其业务成功测试。**
- 预期/实际影响：退款默认参数路径可用，但冻结交给05的通用两步准备机制未具备；05不能按已交付接口直接接入。当前拒绝是安全的，不是放行漏洞，不把未实现RAG/Store本身列为04缺陷。
- 建议：由主Agent按冻结本期/后继边界裁决并补齐同一Executor必要扩展及固定准备/执行关联，或明确记录未交付，不能以签名存在宣称完整契约完成。无需提前开发或注册Memory业务、RAG/Store。

本轮P0=0，P1=4，P2=2；新增P3=0。04-QA-001/006为缺实现，002/003/004为受控实测缺陷，005为既存测试设施问题。专用库超时单列为环境阻塞，既有凭据/格式遗留不重新编号。

## 6. D04第15节24项矩阵

结论中的“受控通过”仅指本轮或完整默认回归的可控证据；除特别说明外不含真实PG，不能折算成阶段门禁通过。F=已有缺陷，B=缺真实资源或未执行，P=受控部分成立。

| # / 必验场景 | 独立证据与当前结论 |
| --- | --- |
| 1 正常申请/批准/模拟执行 | **P+B**：仓库真实编译图HTTP正常批准和本轮repair/END场景通过，原operation受控effect=1；真实PENDING→interrupt→PG事务SUCCEEDED未验证 |
| 2 管理拒绝 | **P+B**：完整回归中REJECTED原handler零次；DB订单不变/原审批事务仍缺真实库证据 |
| 3 GET审批视图 | **P+B**：八字段/本地Actor/生产禁用测试通过，源码get/list无UPDATE；GET零SQL写及APPROVED到期真实时间未验证；相关用户只读API另有001 |
| 4 过期Resume | **B**：源码锁后clock_timestamp、PENDING惰性EXPIRED及Gate失效拒绝有实现；真实锁等待/过期综合测试skip，不能判通过 |
| 5 Task兼容别名 | **P+B**：004/005 SQL及Repository/subject再检源码核对；真实缺键/null/类型/空值/同值约束测试skip，本轮部署/checksum未在线核实 |
| 6 重复决定 | **B**：源码同决定先复用、相反冲突且不续期；真正数据库幂等/并发测试skip |
| 7 未付/已退/异主 | **P+B**：源SQL/Domain资格及owner检查存在；当前全量相关受控边界通过，退款真实订单资格/金额仍未验证 |
| 8 chat/伪Actor/错主体 | **P+B**：body额外字段、production/回环边界及Policy拒绝测试通过；真实申请/批准参数、金额/version篡改的SQL综合门禁缺证 |
| 9 真实waiting | **P+B+F**：实际InMemory interrupt与唯一child分类、等待状态成立；PG有效快照未测，current-task API缺失001 |
| 10 中断持久但绑定失败 | **P+B**：本轮真实编译图故意使bind失败，HTTP repair两次分别repaired=true/false，Run/模型/效果不增加，随后批准恢复成功；真实PG CAS、历史中断及故障窗口未完成 |
| 11 完全重启 | **B**：没有本轮真实PG退款旧Python完全退出再新进程续原Task/call/op证据；旧受控图探针不能替代退款门禁 |
| 12 审批后再检 | **P+B+F**：当前scope/Policy/审批再读有实现与测试；本轮撤权退款零次，但拒绝后消息协议失败004；真实状态竞争未测 |
| 13 原ToolMessage | **F**：正常受控批准/拒绝配对成立；撤权路径半配对输入compose，004未通过；真实模型协议未验 |
| 14 重复/并发 | **P+B**：Runtime门禁与重复受理测试通过；真实同op/不同op、两个决定事务竞争全部依赖skip项 |
| 15 过期/失效 | **P+B**：代码区分已成功复用与新执行授权；真实到期/资格变化/成功后过期复用未独立验证，不以交付方历史结果替代 |
| 16 SQL回应丢失/快照失败 | **P+B+F**：本轮严格Serializer+实际图在受控“效果后返回异常”留下next=execute_refund，恢复零新effect通过；真实SQL/PG快照故障和其他全部安全节点未验；PENDING矛盾002失败 |
| 17 未执行/未知核对 | **F+B**：已有unknown→reconcile停留及之后确认成功的回归；当前PENDING直接not_executed且成功快照矛盾继续完成，002失败；真实未执行证明/新标记SQL门禁未验 |
| 18 实际调用/重入守卫 | **P+B**：本轮实际已安装框架+严格Serializer的根None、wrapper→原execute节点及当前recovery传播通过，不是伪造StateSnapshot；真实PG版本/退款多进程语义仍未验 |
| 19 四种Resume受理 | **P+B+F**：本轮pending、repair后推进、正常END200且无新Run/Graph通过；仓库纯分类器覆盖未知形态；post_gate矛盾仍受理002，真实环境四类未完成 |
| 20 执行前/后崩溃 | **P+B**：严格Serializer内存Saver对marker快照注入失败，effect=0；受控效果后异常可复用；真实事务与PG Saver故障、完全进程退出未验证 |
| 21 任务预算 | **F**：基线继承/标记可能消耗及usage_complete=false有实现；本轮同预算下保守时长耗尽仍模型调用，003未通过 |
| 22 中断/结算隔离 | **P+B**：scope等待前冻结、实际pause没有专业结果，正常图内run_finish及旧02回归成立；真实PG等待/sync/最终结算故障未验 |
| 23 SSE/HTTP断开 | **P+B**：本轮恢复Run实际本机TCP事件流断开，订阅释放后独立完成，effect=1；lifespan关闭/Saver及全量初次迭代规则有受控回归，真实PG下初始/恢复综合门禁仍缺证 |
| 24 业务/技术状态分离 | **F+B**：正常ModelCallError分支源码保留成功fact；异常/重启需要的持久用户查询接口缺失001，矛盾可误报completed002；真实PG效果后Checkpoint/compose失败查询未验 |

因此24项没有获得一套完整真实资源验收；不能用其中受控通过项或156 passed推导04通过。真实模型+真实PG退款门禁也未运行，默认测试不付费，符合本轮环境分支要求。

## 7. 数据与工程保护、证据边界

探针通过validate_test_target限制配置dbname为agent_demo_test并与开发目标区分，失败只输出ConnectionTimeout类别，未输出凭据、URL、headers或连接异常全文。连接未建立，没有执行身份SQL或写入；**没有可提供的真实库前后行集快照，也不声称既有五订单已由查询证明保持不变**。本轮不启用真实库测试、不执行seed/reset/迁移/Saver setup、不清理应用库或已有数据。受控业务/审批/Session/Saver均在进程内，无真实thread/SQL数据需删除。

127项独立摘要含app、tests、scripts、SQL、pyproject、requirements及.env.example，也包含既有general.py；保存于R/protected-before.json，最终相等。主Agent原126路径清单由其单独复核；本轮未访问其用户级会话日志、Bridge或其他会话。既有三个旧文档删除、D01差异、general.py及Bridge独立文件保持。

R目录保留：audit04.py、probe.json、protected-before.json、run_tests04.py、full-controlled.txt（含-rs报告失败）、run_default04.py、full-default.txt（默认完整结果）、test_review04.py（最终11场景）、diagnose_pending.py、pending-evidence.json。分批外部pytest结果如第4节和本会话执行记录；未谎称所有分批stdout均另存文件。源码、实际命令和固定事实足以由主Agent/后续修复角色复现。没有将受控效果计数称作真实数据库写计数。

依赖清单未变化，未安装/升级或重复执行pip check。P3-01六份Markdown示例格式为既有遗留，本轮只检查执行代码format，未重新运行或自动修正文档示例。RISK-02-CRED历史凭据暴露/密码复用继续按用户接受决定处理，不作为新增阻塞；本轮后续输出保护仍保留。production无本地审批认证能力属于设计允许，真实管理员认证、RAG/Store、任意协程恢复、多实例/Exactly Once均未扩为04要求。

## 8. 交回与后续门禁

建议主Agent逐项裁决04-QA-001～006，在现有冻结设计范围组织必要修复。尤其先修恢复矛盾、预算及原调用闭合，再验证缺失查询接口与跨节点Prepared交接。真实环境恢复后仍须完成：身份/schema5/checksum/Saver版本、全部业务表和本轮Saver线程的前后保护、真实005约束/锁后时间/并发与幂等、退款完整新Python进程恢复、真实SQL成功/Checkpoint失败的execute_refund及其他安全后段零新写、当前查询和真实模型原调用门禁，然后重新独立复核24项。

本轮不修改实现、不改验收标准、不将skip视作通过、不把阶段标VERIFIED、不进入05。报告完成后停止，等待主Agent裁决。
