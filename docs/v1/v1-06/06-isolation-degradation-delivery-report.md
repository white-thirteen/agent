# Task6.2.2 隔离和退化路径交付

2026-11-14；仅执行[当前Task](06-isolation-degradation-execution-task.md)，依据冻结D06 Task6.2.2与第10节。交主Agent审查与独立QA，不代表阶段验收。

## 修改与实际验证

新增 `scripts/verify_06_isolation_degradation.py`，使用正式create_app装配、真实PG/Saver/Store/Qwen CPU1024及本机随机端口uvicorn。Chat输出和指定故障由脚本注入，不改产品源码、依赖、迁移、预算或真实配置。仅脚本本进程启动并关闭服务任务，没有启动其他服务进程或杀进程。

项目解释器执行：

` .\.venv\Scripts\python.exe -m scripts.verify_06_isolation_degradation --output docs/v1/v1-06/evidence/06-isolation-degradation-real-evidence-20261114-r3.json `

实际场景及证据：

- [R1](evidence/06-isolation-degradation-real-evidence-20261114-r1.json)：退出0，基础组合通过。真实TCP在模型阻塞时断开，订阅已释放但后台Task仍运行；放行后订单查询完成；再次订阅只有当前快照/结束，没有旧token重放。
- [R2](evidence/06-isolation-degradation-real-evidence-20261114-r2.json)：退出1，探针对empty错误要求final_answer为空。既有契约允许安全的证据不足说明；Embedding与PG故障已通过无正文/无来源断言，empty实际rejected。保留失败证据，finally全部public行集/列定义、保护文件一致。修正探针核对empty的安全summary及approved_answer为空，没有改产品或削弱来源/私有输出检查。
- [R3](evidence/06-isolation-degradation-real-evidence-20261114-r3.json)：退出0，probe_result=PASS、protected_unchanged=true；四个退化场景均通过，protected_files_unchanged=true。最终[在线审计](evidence/06-isolation-degradation-final-audit-20261114.json)再次核PG17.6/pgvector0.8.7、专用身份、完整public指纹与R3最初baseline一致；Win32_Process只读检查本脚本Python进程剩余0。R1/R2/R3均正常退出，服务任务已停止，项目进程的连接随生命周期和进程退出释放；本轮未以application_name单独统计连接数，不冒称做过该项计数。

A/B通过正式HTTP解析DemoIdentity，B查询A订单被拒绝，A真实偏好en而B为空。B查询A退款申请404；普通chat在等待审批时409且不作决定；伪造permission_scopes或reviewer_id字段422。批准来自独立本地控制面，审计Actor始终local-demo-approval。该控制面V1无真实管理员认证，选择允许名单中的A代表A演示身份，不声称抵抗身份冒用。

真实批准/恢复完成模拟退款后，独立新会话显式Memory Task在真实Manager的Store aget边界注入OperationalError，任务failed；随后直接SQL核订单is_refunded=true、申请SUCCEEDED。未添加自动MemoryWriter或退款后的自动写路径。

完整装配的Embedding失败、PG连接失败、empty和模型失败均从正式chat入口运行。Embedding失败在aembed_query边界注入KnowledgeError；PG失败仅替换KnowledgeRepository.pool连接边界抛OperationalError，真实Repository转换安全错误；不是实际停止PG。empty仅控制repository.search返回空候选，真实检索服务/Graph完成rejected；模型失败在Chat调用边界注入。模型/Embedding/PG失败无最终正文或来源，empty只允许安全summary，无生成正文或引用。PG与empty场景实际调用原Qwen生成query向量；Embedding失败不调用Qwen推理；其余业务仅装配Qwen。没有付费Chat请求，没有本轮真实Chat语义证明。

## 风险定向回归与复用

项目解释器stdin安全读取Settings.test_database_url，仅设置当前进程AGENT_TEST_DATABASE_URL，调用pytest.main；实际args与逐例结果见[定向证据](evidence/06-isolation-degradation-targeted-evidence-20261114.json)。执行以下文件加 `-q --tb=short`：

`tests/test_runtime_http.py tests/test_runtime.py tests/test_tool_governance.py tests/test_memory_reader.py tests/test_memory_manage.py tests/test_memory_manage_postgres.py tests/test_memory_postgres.py tests/test_knowledge.py tests/test_knowledge_graph.py tests/test_knowledge_postgres.py tests/test_approval_routes.py tests/test_demo_identity.py tests/test_model_gateway.py`

**99 passed，0 failed，0 skipped，28.96秒**（外层记录30.45秒）。这些是本轮实际重跑，按其真实/受控边界归因：

| 风险 | 本轮实际证据 |
| --- | --- |
| 首迭代前/构造/发头异常与Owner释放 | runtime_http三个参数化出口；后台执行继续 |
| 实际TCP中断、重订无旧token、慢消费者 | runtime_http真实socket及runtime慢订阅用例；新增完整装配TCP证据 |
| 累计模型/工具/主动期限预算 | runtime预算跨Run与model_gateway有界调用测试；不重置、不继续新尝试 |
| scope/args/Agent白名单、零handler | tool_governance与memory_manage_postgres最终Policy；模型origin/错node/空allowed_tools/伪造参数全部零尝试 |
| 原生/节点来源与call配对 | knowledge_graph生成答案/重入与wrong multi mixed calls，工具记录/ID配对；Memory原marker的call/attempt/revision |
| empty/弱证据/错ID/来源版本/语义区别 | knowledge_graph参数化失败分支与合法引用错误语义用例；无私有draft公开 |
| Reader empty/unavailable/denied/partial | memory_reader投影与治理测试；denied零Store访问，partial剔除未知值 |
| Memory写前sync、最终Policy、unknown/not_started | 真实PG memory_manage_postgres：sync失败零写handler/prepare不计尝试；最终拒绝零尝试；Get失败已入handler计一次但零Put；提交丢确认unknown后原op核对，无再Put；unknown原领域载荷保留 |
| revision/operation与跨进程隔离 | 真实PG memory_manage_postgres与memory_postgres：原op复用/冲突、A跨Thread/新解释器持久保留/B隔离 |

上述真实PG用例每个使用UUID自有namespace/thread并核全public完整行集/列定义/迁移checksum。其他单元用例中的内存Saver/受控资源不冒称真实PG组合。

产品行为未修改，复用6.1.2[最终完整真实PG225门禁](evidence/06-state-events-full-regression-evidence-20261114-r2.json)及[独立QA](qa/06-state-events-qa-report.md)，其中原seed幂等窄例外原样执行，无deselect。本轮未新增seed或触碰固定五订单。真实Chat、来源与英语偏好语义复用6.1.1[最终R5](evidence/06-assembly-real-evidence-20261114-r5.json)及[交付报告](06-assembly-delivery-report.md)的两条预先固定问题；未变语义不重复付费。原审批恢复/unknown快照矩阵沿6.2.1[交付](06-persistence-fault-delivery-report.md)复用，不机械重跑所有进程排列。

` .\.venv\Scripts\python.exe -m ruff check app scripts tests ` 通过；` .\.venv\Scripts\python.exe -m ruff format --check scripts/verify_06_isolation_degradation.py ` 通过。首次Ruff发现新增脚本import排序/长行，已定向修正；无生产改动，无依赖检查需求。

## 数据保护与边界

每轮正式入口前验证专用agent_demo_test/agent_test及001～006全部checksum，记录全部public表完整行集和列定义指纹。finally停本轮uvicorn任务、shutdown Runtime，按UUID的A/B Session找到原thread并adelete_thread，按FK删除自有审批/退款申请/Session/订单及A profile，完整对比前后数据。R2起同时核.env、006与角色文件字节SHA256一致；不输出配置内容或凭据。

本轮无产品缺陷修复，不改冻结设计、STATE/AGENTS/主协调或六项暂缓差异。Store关闭即时视图波动的历史严格根因仍未证明；前序独立QA12次关闭和原用例通过，本轮未新增持续残留证据，不据此重构Store。unknown后应先人工核对原operation/revision/last_mutation并暂停相关profile新写，V1不提供自动恢复平台。V1无认证/多进程互斥/持久SSE重放等保证，保持原边界。完成本Task后停止，待独立QA。
