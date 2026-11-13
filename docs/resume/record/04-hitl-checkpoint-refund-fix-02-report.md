# 04-QA-007 第二轮修复与开发自测报告

日期：2026-11-13。阶段04，关联Task4.1.2/4.2.2/4.3.2、问题**04-QA-007**、[本轮修复提示词](../04-hitl-checkpoint-refund-fix-02.md)及[独立QA发现](../../question/04-hitl-checkpoint-refund-restart-qa-report.md)。基线HEAD仍为`50e4c55476e714ed1e6d692511d8d878108c399b`，包含工作区原未提交实现。

**三项007原失败已修复，开发自测及新增必要矩阵场景通过；待独立QA复测和主Agent裁决，不自行关闭问题或标记阶段验收。** 最终完整真实库回归165 passed、0 failed、0 skipped，未重复付费模型。原001～006关闭结论及历史证据保留。

## 1. 根因、最小修改与职责

| 位置 | 根因与最终行为 |
| --- | --- |
| [Runtime](../../../app/runtime/agent_runtime.py) | 原repair只要求当前真实pending，已绑定即提前返回；现在空绑定仅允许PENDING。已绑定必须读取**精确原checkpoint_id**，将该真实历史child与同一可信root/主体/原call/namespace/interrupt重新分类核对。缺失或非原Gate审计返回409；不要求latest ID等于原审计ID。只有核验后才进入原短事务，保持原thread门禁，不执行Graph或创建Run。 |
| [ApprovalService](../../../app/workflows/approvals.py) | 原锁后只比较三绑定值，没有本次可信期望主体/决定。新增只用于CAS请求的typed `InterruptBindingRequest`，携带Runtime已检查的subject_digest/decision；锁原审批后，重新检查申请/session、完整主体与digest自洽，再与调用方期望digest/decision比较。空绑定仍须PENDING；任一变化409且不UPDATE绑定。已有相同绑定仅在这些检查全部通过后幂等返回。 |
| [退款Checkpoint测试](../../../tests/test_refund_checkpoint.py) | 既有repair测试适配事务再检调用，并验证latest为后续Gate快照时，原审计checkpoint仍可合法幂等复用，不因ID不同被误拒绝。 |
| [真实事务测试](../../../tests/test_refund_transactions.py) | 直接绑定调用方完整传递本次登记返回的期望主体/决定，保留全部原正确断言；工具执行使用原三字段InterruptBinding。 |
| [新增正式PG补验](../../../tests/test_refund_repair_postgres.py) | 一个小型正式lifespan夹具复用受控模型及真实所有仓储/工具/Graph/Saver，覆盖本轮明确缺口，详见第3节。 |

自动暂停绑定与显式repair两个生产调用方均完整接线。`InterruptBindingRequest`是既有三字段binding的仅请求子类型，**不改变工具尝试标记里已持久化的binding_snapshot形状**，不携带权限或通用批准标记，不新增审批表、接口、策略平台、依赖或Serializer白名单。

事务只在原审批锁内增加期望主体/状态检查，沿用已有锁序及申请/session校验；已过期但仍PENDING可以补原中断事实，修复不决定、不改变expires_at，不让已决定空绑定变成可审批/恢复。数据库不可用沿既有安全错误映射；没有放宽Checkpoint分类器或在图外注入批准/结果。

## 2. 原007复现的最终结果

原外部文件保持不变：

`C:/Users/15294/AppData/Local/Temp/agent04-restart-qa-20261113-131121/repair_negative.py`

最终版本在新的独立目录F执行，未覆盖原QA或先前10份JSON：

`C:/Users/15294/AppData/Local/Temp/agent04-fix02-final-7eafee94afde4880935c01d87f2c6281`

| 原正确断言 | 实际结果 |
| --- | --- |
| 默认入口A：已决定且三绑定为空 | HTTP409、new_runs=0，业务全行集不变，精确清理通过 |
| 默认入口B：审计checkpoint_id确认不存在 | HTTP409、new_runs=0，业务全行集不变，精确清理通过 |
| `--cas-only` C：Runtime后、真实CAS前subject_digest变化 | HTTP409、new_runs=0，不补绑定，精确清理通过 |

原复现将Graph.ainvoke设为失败探针，三项均未推进Graph/退款。C的原输出`business_rowsets_unchanged=false`来自**测试边界自己改变subject_digest**，没有把它隐去或改写为true；服务拒绝新增绑定。另在新增真实PG测试中实测CAS前decision从PENDING改为APPROVED，结果409且三绑定仍全NULL、无新Run/Graph/退款。

[本轮007及正常repair安全JSON](04-fix02-007-evidence.json)保留最终A/B/C响应与正常repair新轮次证据。原正确409断言、原QA文件及历史JSON均未修改。

## 3. 补齐原24项明确缺口

新增测试通过正式create_app生命周期创建真实业务池/Saver池、SessionRepository、ApprovalService、MockRefundService、Registry/Policy/Executor、Supervisor/Refund图及严格Serializer；只替换模型和显式失败探针，不Mock核心审批/事务/恢复。所有新增数据唯一，无seed或固定订单写入。

| 原矩阵项 | 本轮实际证据 |
| --- | --- |
| #3 APPROVED过期GET | 在真实PG批准后将**本轮唯一**审批的created_at/expires_at按固定30分钟关系置为已到期；管理列表/详情均逐项断言完整八字段及相同派生值：APPROVED保留、validity=expired、bound、can_decide=false、can_resume=true。对真实AsyncCursor.execute设置只允许SELECT探针，另禁止Saver.aput和Graph.ainvoke；GET均成功，业务全行集/迁移/Saver线程前后相同。 |
| #4 过期审批完整Graph | 上述过期APPROVED经正式HTTP resume、原真实Gate/完整Graph拒绝收敛；task=rejected、申请REJECTED、订单未退款。原call的error ToolMessage恰好一条；真实退款handler为失败探针、零进入。原APPROVED审计及expires_at整行保持，不改为另一人工决定或续期。 |
| #10 repair响应丢失/幂等/并发 | 真实HTTP handler完成绑定事务后，测试transport抛ReadError模拟客户端丢失响应；再次repair200 repaired=false，原行及Run集合不变。两个**真实loopback TCP HTTP客户端**并发repair，只一项repaired=true，其他返回线程忙409或幂等200；随后重试false。该场景为已过期但仍PENDING，决定/审核人/时间/期限保持，不创建Run/Graph/退款。 |
| #10 错主体/历史中断/状态CAS | 实际读取同namespace中存在的历史非Gate checkpoint，替换仅本轮审计引用后repair409且全行集不变；错误subject_digest同样409零写。状态在Runtime后、CAS前变化409、三绑定全空。缺失审计、已决定空绑定及摘要CAS变化另由原A/B/C验证。 |
| #14 双HTTP同决定竞争 | 两个独立**真实loopback TCP HTTP客户端**向同一正式应用并发提交相同决定，两者200且完整响应一致，复用原审核人/时间/期限；Run集合不变，未自动执行退款。 |

TCP并发使用测试中临时绑定的本机socket，暴露已由正式lifespan初始化的同一应用；结束关闭server task/socket/client，不声称另做完整进程重启。响应丢失与GET故障探针使用ASGITransport，边界明确为HTTP handler提交之后客户端未收到响应，不冒称真实网络断电。

正常首次repair、重复repair及原退款批准恢复另运行现有显式`--mode repair`：真实PG、跨进程原关联、handler一次、原ToolMessage恰一，精确清理通过；新证据在F/docs，不覆盖历史文件。其余已过真实重启/故障/预算/断开证据沿[原4.3.2报告](../../04-hitl-checkpoint-refund-restart-report.md)及独立QA分层复用，没有再做全排列或重复付费模型。

## 4. 实际命令与最终门禁

解释器P为`D:/py/agent-project/agent/.venv/Scripts/python.exe`，PG操作沿项目Windows selector runner。外部原复现运行时cwd=F、PYTHONPATH=仓库绝对目录；秘密只从现有Settings在进程内读取。

| 实际命令/入口 | 结果 |
| --- | --- |
| `P 原repair_negative.py` | 最终A/B均409，exit0；各场完整精确清理通过 |
| `P 原repair_negative.py --cas-only` | 最终C为409，exit0；精确清理通过 |
| `P -m scripts.verify_04_restart --mode repair`（cwd=F） | PASS、exit0，原审批/调用跨进程恢复，精确清理通过 |
| 定向`pytest tests/test_refund_checkpoint.py tests/test_refund_full_controlled.py -q --tb=short` | 初步接口修复后14 passed |
| 进程内显式测试库，定向真实PG repair/transactions | 初步新增场景2 passed；随后相关4文件16 passed、0 skipped。最终TCP及后续Gate审计组合由下行最终全回归验证 |
| 保护harness内`pytest.main(['-q','-rs','--tb=short'])`，显式设置现有测试库环境变量 | **165 passed、0 failed、0 skipped，61.78s**，exit0；两条已导入anyio/langsmith的assert-rewrite提示，无功能失败 |
| `P -m ruff check . --output-format concise` | All checks passed |
| `P -m ruff format --check app tests scripts` | 121 files already formatted |

本轮测试未出现业务断言失败或skip；初次Ruff指出新代码格式/长行，已修正后最终检查通过。未削弱原断言、改正确预期、修改QA文件或用Mock替代本次核心行为。全仓六份Markdown格式遗留沿既有P3-01保留，本轮未重复检查或格式化冻结正文。

## 5. 数据保护、限制与交回

每个真实场景先validate_test_target及在线agent_demo_test/agent_test核对，读取001～005及本地迁移SHA256/登记checksum逐项匹配，保存sessions/demo_orders/refund_requests/approvals/schema_migrations全行集与Saver线程集合。新增测试所有订单/Session/操作均唯一。清理按本轮用户与外键顺序删除业务行，按本轮自有thread调用Saver.adelete_thread，逐表核对checkpoints/checkpoint_writes/checkpoint_blobs该thread零行；失败路径同样从自有Session发现线程再清理。

原A/B/C及正常repair每场均打印完整行集/迁移/线程未变化摘要。新增真实PG测试finally核对完整前后快照一致。最终全回归保护harness保存并比较相同完整快照及五固定订单原值，结果一致，见[新轮次回归JSON](04-fix02-regression-evidence.json)。既有seed幂等测试仅按当前任务窄例外原样运行：先核五固定订单事实，原测试临时改is_refunded后finally恢复，不以seed恢复或覆盖状态。其余新增测试没有seed。未访问应用库、修改迁移/依赖/环境/密码。

本轮新文件为本报告、两个新轮次安全JSON及新增PG测试；另仅修改上列四个既有Python文件和README必要导航。主Agent协调记录/STATE/AGENTS、冻结设计、原QA/开发报告、原10份JSON保留。没有Commit/Push、Bridge/其他会话/Agent调用、05开发或新增模型付费。

未知Saver快照形态与未sync无可信窗口仍沿既有安全409，不承诺任意崩溃自动恢复、多实例互斥或全局原子执行。本轮修复不影响模型Prompt/工具schema/模型调用协议，沿用原deepseek-flash真实模型证据。后续由独立QA复原007及必要新增边界，再由主Agent裁决；本单元完成后停止。
