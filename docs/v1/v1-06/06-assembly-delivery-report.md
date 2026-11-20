# Task6.1.1 装配实施交付

本Task继续修复了首轮两项缺口；原R1～R4失败证据及partial gate保留，最新结果见末尾“补充修复与最终验证”。本文是实施交付，仍等待主Agent审查与独立QA。

2026-11-14；基线只读核实为 `f860bb5`。本报告是 Implementer 交付及实测记录，交主Agent审查与独立QA；未宣布Task/阶段验收。范围限[执行任务](06-assembly-execution-task.md)，01～05既有能力与原六项暂缓差异保留。

## 修改及实际接线

- `app/main.py`：沿用唯一lifespan/AsyncExitStack，将创建顺序调整为业务池/服务→Saver池→共享ChatGateway→Qwen/索引检查→Store自有池/Manager/Reader→统一Registry/Policy/Executor/专业图/Memory图/根图/Runtime。退出先Runtime沿原5秒窗口收敛及取消，再Store批处理任务及池、Embedding排空、Chat客户端、Saver池、业务池；初始化中途失败按已创建资源反序退出。停止日志移至资源栈完成之后。
- `app/knowledge/repository.py::check_ready`：只读核验向量操作符/列类型 `vector(1024)` 与当前知识文档profile。缺表/连接故障/profile不兼容不再仅凭Retriever实例报告ready；固定安全状态投影为 `knowledge_status=unavailable`，工具注册为禁用，其他专业及Memory仍独立装配。空但兼容的语料库仍是可检索资源，检索时真实返回empty。沿已有5秒SQL边界，无DDL/迁移/导入。
- `/health` 增加 `checkpoint_status`、`knowledge_status`，其余准备层语义保持。`model_status=initialized`表示客户端初始化，不探测供应商网络；就绪状态为启动核验结果，运行中故障仍经原Session/Saver/工具handler安全失败。
- `tests/test_resources.py`：扩展原关闭用例，验证Runtime调用已退出才关Store/模型；六个受控场景验证业务池、Saver、Embedding、KB/profile、Store失效与Graph中途初始化异常、冻结工具启用集合、503、安全health和反序清理；实际builder与模型构造各一次。
- `tests/test_knowledge_postgres.py`：在原真实PG用例中补兼容profile正常及不匹配拒绝的只读检查。
- `scripts/verify_06_assembly.py`：显式真实Chat+Qwen+PG公共HTTP应用探针；默认pytest不执行。UUID用户/订单/文档/会话，完整public行集及列定义前后保护，原线程精确删除；以application_name核连接归零并核Qwen线程归零。
- `README.md`：新增本Task报告导航。未修改用户.env、冻结设计/006、角色配置、业务规则、Graph协议、审批Router或前序QA。

核对既有装配：三专业及Memory均使用同Gateway/Registry/Policy/Executor，只有根图compile持PG Saver，子图默认compile继承per-invocation，wrapper显式白名单映射。既有approvals Router只注册一次，production不注册，服务端Actor为审计值；不把演示user_id或Actor描述为认证。演示入口没有替身，受控替身只用于测试。依赖未变。

## 已执行验证

解释器均为项目 `.\.venv\Scripts\python.exe`。

1. `-m pytest tests/test_resources.py tests/test_application.py -q`：最终 **18 passed**；受控模型/资源，不据此宣称真实外部依赖通过。
2. 进程内读取 `Settings().test_database_url` 写入当前进程 `AGENT_TEST_DATABASE_URL`，再调用 `pytest.main(['tests/test_knowledge_postgres.py','-q'])`：真实PG **2 passed**。凭据没有输出或写入证据。
3. `-m ruff check app scripts tests`：通过；`-m ruff format --check app/main.py app/knowledge/repository.py tests/test_resources.py tests/test_knowledge_postgres.py scripts/verify_06_assembly.py`：5文件通过。
4. 最终授权范围回归：结果见下节。没有执行固定订单seed例外。

### 真实HTTP应用探针

实际命令为 `-m scripts.verify_06_assembly --output docs/06-assembly-real-evidence-20261114[-r2|-r3|-r4].json`，四次独立UUID场景，证据均保留：

| 轮次 | 实际结果 | 清理及说明 |
| --- | --- | --- |
| [R1](evidence/06-assembly-real-evidence-20261114.json) | Memory及来源RAG完成；英语输出断言失败；退出1 | 新探针清理SQL错误引用approvals.user_id。随后独立修复清理，原UUID关联精确删除，完整public行集/列定义与原baseline相同，补记于原证据 |
| [R2](evidence/06-assembly-real-evidence-20261114-r2.json) | 英语RAG、订单完成；退款真实waiting_approval；退出1 | 探针错误断言父Checkpoint在中断时必须waiting_approval。原协议父快照仍running，公共done/Runtime为waiting_approval；修正观测位置，保留snapshot_task_status，未改业务。finally核全部public保持 |
| [R3](evidence/06-assembly-real-evidence-20261114-r3.json) | Memory及来源RAG完成；英语输出断言失败；退出1 | finally精确清理与public保护通过 |
| [R4](evidence/06-assembly-real-evidence-20261114-r4.json) | 同一app四路径全部执行；最终英语偏好断言仍失败，退出1 | 拒绝原退款operation收敛；全部public行集/列定义保持；命名PG连接0、Qwen工作线程0 |

R4真实环境：agent_demo_test/agent_test，PG17.6、pgvector0.8.7；在线001～006全checksum及列定义通过，Saver迁移0～9、Store迁移0～3。Settings仅选择test库/UUID名单、开启原CPU Qwen/1024，最后一轮额外连接application_name用于关闭核验；模型/provider及原预算未改。

R4独立Task：显式保存英语偏好1次模型/2次工具；知识4次模型/3次工具，真实Qwen检索、来源当前版本/hash与Saver记录一致；订单3次模型/2次工具，SQL事实金额12.34 CNY、simulated=true。退款原申请进入真实Gate，服务端本地入口提交REJECTED并resume，原Task收敛rejected，原operation业务状态REJECTED，审计Actor=local-demo-approval，SQL订单is_refunded=false。中断时根快照用量尚未回映，退款预算以保存的子图tool_records为据；未把根快照旧计数当完整Task用量。

R4知识子图确实读到 `answer_language=en`，但真实Chat生成中文。已核该回答语义与证据一致：普通聊天不能批准模拟退款，必须独立本地审批入口；语言遵循不稳定，不能据来源正确推导英语呈现通过。脚本最后保留正确英语断言，没有绕过、改写业务Prompt或无限重试获取PASS。R4后脚本仅补子图用量字段与失败结果标识保存位置，未再次调用付费模型，R4原证据不补造这些字段。

## 最终回归范围与结果

实际调用 `pytest.main(['-q', '--deselect=tests/test_order_postgres.py::test_real_order_constraints_isolation_and_seed_idempotence'])`，在同一解释器内由Settings安全读取测试DSN注入当前进程环境；运行前后分别打开专用测试池，调用既有database_snapshot核对在线身份、001～006 checksum、所有public表完整行集与列定义。

结果：**221 passed、1 deselected、0 failed、0 skipped，98.86秒**。两条PytestAssertRewriteWarning来自验前快照导入依赖早于pytest初始化（anyio/langsmith），无业务失败。回归前后所有public行集与列定义相同，见[回归保护证据](evidence/06-assembly-regression-evidence-20261114.json)。

唯一排除项 `tests/test_order_postgres.py::test_real_order_constraints_isolation_and_seed_idempotence` 会调用seed_orders并临时改固定demo-order-a-001的is_refunded，当前Task明确禁止且主Agent确认无本轮例外。没有修改该测试或降低其断言，也没有将排除当作完整门禁通过。

## 首轮未闭环与交接（历史，后续补充覆盖）

1. **真实英语偏好呈现不稳定**：四轮中R1/R3/R4输出中文，R2输出英语；偏好已正确持久化、跨会话读取并进入生成Prompt。真实探针最终退出1，不能称其整体PASS。保留前序Prompt与本Task边界，交主Agent和独立QA判断影响及后续定向修复。
2. **完整门禁未全执行**：当前授权禁止固定订单seed/临时状态修改，唯一涉及该行为的既有用例被明确排除；结果不得表述为完整门禁通过。
3. 本Task未重复完整进程重启/故障组合或Apifox/部署工作，属于后续Task。未SSH、重启PG、容器重建、Git写操作或派发Agent。完成当前实施与证据整理后停止，等待独立QA。


## 补充修复与最终验证（2026-11-14，同一Implementer）

主Agent明确要求关闭英语偏好呈现及完整门禁两项缺口，且重新明确原05 seed幂等窄例外适用于本轮唯一既有测试。依据为[当前Task补充](06-assembly-execution-task.md)及[05原窄例外](../v1-05/05-local-embedding-execution-task.md)的协作与数据边界；没有将此授权扩展到新固定订单场景。

### 偏好呈现的最小修复

实际检查确认05已经移除旧“Use the question's language”规则。本次修复没有基于该过期假设：

- `app/graph/specialists/preferences.py::preference_instructions`：将Reader已验证的 `en` / `zh-CN` 明确映射为 English / Simplified Chinese，风格枚举表达为可读指令；清楚声明当前用户明示语言/风格要求 > 存储偏好 > 问题语言/默认风格，中文问题本身不视为明示中文回答要求。只采用原Reader白名单投影，不纳入原始Store任意文本；en+detailed提示最终实测89个cl100k_base token，仍在既有128边界内。
- `app/graph/specialists/knowledge/builder.py::generate_answer`：将无条件“Write a concise answer”改为默认concise，允许显式用户风格或detailed偏好按冻结优先级生效。
- `tests/test_knowledge_graph.py`：增加两种受控图行为回归：普通中文问题保留en/detailed提示，用户明确“请用中文简短回答”也原样进入生成上下文并由优先级说明允许覆盖。真实Reader/Executor/八节点知识图及来源校验仍运行；受控模型用于核生成提示契约，不能替代真实语义证据。

没有新增模型/rewriter/生成后翻译、模型轮次、预算、供应商或配置；英语及事实/来源断言未放宽。运行 `-m pytest tests/test_knowledge_graph.py tests/test_memory_reader.py -q`：**37 passed**。

### 预先固定两题的一次真实验证

实际命令：`.\.venv\Scripts\python.exe -m scripts.verify_06_assembly --output docs/v1/v1-06/evidence/06-assembly-real-evidence-20261114-r5.json`，**退出0，probe_result=PASS**。本次修复后只运行这一次，问题清单在真实请求前写入证据；各题一次，没有循环直到PASS。

同一个create_app生命周期：先保存英语偏好，再用两个新会话问普通中文知识问题，均无明示英语指令；最后继续订单与退款路径。

| 固定问题 | 实际英文正文与人工语义核对 |
| --- | --- |
| 根据银帆演示指南，普通聊天能批准模拟退款吗？审批应该通过什么入口提交？ | “No. Per the Yinfan demo guide, ordinary chat cannot approve simulated refunds, and agreement expressed in chat does not count as approval. Approval must be submitted through the separate local approval entry, where the decision is recorded by a server-fixed demo operator.” |
| 根据银帆演示指南，聊天中的同意能代替批准吗？模拟退款审批从哪里提交，由谁记录？ | “No. Per the Yinfan demo guide, agreement expressed in ordinary chat does not constitute approval of a simulated refund. Simulated refund approvals must be submitted through a separate local approval entry point, and the approval decision is recorded by the server's fixed demo operator.” |

两题均完整英语；语义分别与本轮中文自有文档中的聊天不能批准、独立本地入口、固定服务端演示操作者一致。每题来源1项，当前document_version/chunk及来源复核均通过，Saver读取偏好均en，工具记录read_preferences/search_knowledge/validate_knowledge_sources均success/1次；每题模型4次、工具3次。证据记明language_source来自存储偏好，无用户显式覆盖。人工核语义与服务端来源校验分别成立，没有把引用存在当成语义证明。

随后同一Gateway/根图/Runtime完成模拟订单SQL事实查询、模拟退款真实Gate等待、本地REJECTED决定及原Task收敛；原operation REJECTED、订单金额12.34 CNY/is_refunded=false、服务端审计Actor正确。真实模型/provider保持原DeepSeek，Qwen CPU/1024、PG17.6/vector0.8.7及原预算保持。数据库身份/checksum与Saver0～9/Store0～3核验通过；所有public既有行集和列定义完全一致；命名应用PG连接0、Qwen工作线程0。完整证据见[R5](evidence/06-assembly-real-evidence-20261114-r5.json)。

### 最终完整真实PG门禁

第一次完整门禁命令为相同解释器内 `pytest.main(['-q'])`，已包含原样seed幂等窄例外：223 passed、1 failed、0 skipped、0 deselected，71.39秒。失败是 `tests/test_memory_manage_postgres.py::test_real_memory_commands_cross_threads_process_crud_and_exact_cleanup` 对既有提示子串“explicit language/style instructions take precedence”的原断言；新提示已明确同义层级，但移除了旧措辞。保留该原优先级句并保留新层级及英文映射，未改测试及正确断言。此次public行集/列定义完全保持，见[首次完整回归证据](evidence/06-assembly-full-regression-evidence-20261114.json)。R5双题及来源/四路径证据仍适用；追加句只恢复相同优先级措辞，没有新增语言行为，不重复付费调用。

修正措辞后的最终完整门禁仍调用 `pytest.main(['-q'])`（pytest按项目addopts将实际参数扩为 `-p scripts.pytest_redaction -q`），**224 passed、0 failed、0 skipped、0 deselected，75.53秒**；包含原样seed幂等用例。前后所有public既有行集/列定义完全一致，见[最终完整回归与数据保护证据](evidence/06-assembly-full-regression-evidence-20261114-r2.json)。anyio/langsmith两条导入顺序AssertRewriteWarning与上次相同，不影响执行结果。

最终 `-m ruff check app scripts tests`通过；`-m ruff format --check app/main.py app/knowledge/repository.py app/graph/specialists/preferences.py app/graph/specialists/knowledge/builder.py tests/test_resources.py tests/test_knowledge_postgres.py tests/test_knowledge_graph.py scripts/verify_06_assembly.py`：8文件通过。依赖未变，未额外安装或运行无关检查。

### 当前交接

本补充覆盖首轮未闭环项的当时结论：两条预定真实中文知识问题按英语偏好输出并通过事实/当前来源核验，最终完整真实PG门禁已无排除项通过。当前没有已知未闭环的本Task实施问题；语言结论限本次两题真实证据，明示中文override为受控提示契约证据。原R1～R4失败及partial gate、首次完整门禁失败均保持追溯。

已完成实施范围和必要验证并停止，交主Agent复核与独立QA；未自行进行QA、宣告Task/阶段正式验收或开始下一Task。保留工作区已有变更，未执行Git写操作、Bridge、SSH、PG重启、容器重建，用户.env及角色配置保持。
