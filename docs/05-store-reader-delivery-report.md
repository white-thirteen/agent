# Task 5.3.1 Store 资源与共享 Reader 交付报告

2026-11-14。范围依据 [执行任务](05-store-reader-execution-task.md)、冻结 D05 第 6/9 节及 Task 5.3.1。本报告是 Implementer 实现与自测证据，等待主 Agent 审查及独立 QA；不代表阶段验收。

## 实现及关键位置

| 文件 | 职责 |
| --- | --- |
| `app/infrastructure/store.py:18,36` | StoreResource 公开操作适配；独立 min1/max3 池，autocommit/dict_row/prepare_threshold=0；只读就绪检查；停止并 await 3.2.0 `_task`、退出 Store、关闭自有池 |
| `scripts/setup_store.py:21` | 显式 test/development 目标、批准 host、在线库/角色、完整 001～006 版本与 checksum 核验后调用公开 setup |
| `app/memory/manager.py:25,33`、`app/memory/reader.py:6` | 固定用户名单、可信 namespace/profile 精确读取；schema/revision/完整 profile 大小校验；只采用两项枚举，安全 partial 投影；Reader 仅委托 Manager |
| `app/tools/implementations/memory.py:14`、`app/tools/policy.py` | 空参数 read_preferences，固定超时 3 秒/最多一次只读重试；同 Policy/Executor；缺 scope 返回 memory_scope_denied，零 handler/Store 调用；禁止模型来源及未列节点 |
| `app/graph/specialists/preferences.py:11,94` | 三专业共享的节点调用、稳定 UUID5、参数摘要、call_records、Task 读取记录复用与累计预算；安全偏好提示 |
| `app/graph/specialists/order/builder.py:139`、`refund/builder.py:188`、`knowledge/builder.py:243` | 原准备节点可选读取；无新增 Graph 节点；退款恢复沿原 Checkpoint，不重跑准备 |
| `app/graph/state.py:38,45,100`、`app/graph/nodes/specialist.py:39,53` | 只映射读取记录，不复制全部子图历史；同 Task 澄清续接保留记录，新 Task 清空；普通字典通过真实 Saver 持久化 |
| `app/main.py:100,251` | lifespan 装配共享 Manager/Reader、工具和 Store 状态；Runtime 先收敛，再释放模型、Store、Saver/业务资源 |
| `tests/test_memory_reader.py`、`tests/test_memory_postgres.py` | 受控边界、三编译准备节点、真实 Store/Saver/新进程/隔离/关闭验证 |
| `.env.example`、`README.md` | 说明既有数据库配置、固定 Store 池和显式 setup，增加本报告导航；真实 `.env` 未改 |

安装版 `langgraph-checkpoint-postgres==3.2.0` 的实际签名/源码已读取：`AsyncPostgresStore(conn=pool,index=None,ttl=None)`；`aget` 使用后台队列，`abatch(GetOp/PutOp)` 在当前协程执行；`setup()` 是公开初始化入口；`__aexit__` 不收敛基类 batching task，也不关闭外部池。对 `_task` 的生产私有访问仅位于 Store infrastructure 适配。

普通 startup 不 setup、不写 profile、不创建内存替代品。工具只在 Store 就绪时 enabled；所有 Policy 拒绝均保留 `denied`，失败结果不伪装 successful empty。handler 技术失败可默认呈现，坏 schema/revision 明确 failed；预算耗尽和 CancelledError 不作为技术降级继续执行。

模型偏好仅两项合法枚举，不带 last_mutation、非法值、非法原始字段名或工具消息。包含完整优先级说明的最大枚举组合提示，经已安装 `tiktoken` / `cl100k_base` 实测 40 tokens，低于 128。当前用户明确语言/风格指令高于存储偏好。Knowledge 在生成答案时采用安全偏好提示；Order/Refund 保留事实确定性模板，不用模型改写金额、归属、审批参数或业务结果。

## 实际验证

所有命令均使用项目 `.venv`，未安装/升级依赖。

1. 首轮受影响回归：

   `.\.venv\Scripts\python.exe -m pytest tests/test_order_graph.py tests/test_knowledge_graph.py tests/test_refund_preparation.py tests/test_graph_protocol.py tests/test_tool_governance.py -q`

   **77 passed / 1 skipped**。此轮未注入真实测试库环境；原真实库测试条件跳过，不作为真实验收证据。

2. 新增受控用例：

   `.\.venv\Scripts\python.exe -m pytest tests/test_memory_reader.py -q --tb=short`

   **15 passed**。覆盖安全投影/非法单字段 partial、未知 schema/坏 revision/过大 profile、非法用户零访问、Policy 来源/节点/工具集合/参数拒绝、缺 scope 零访问、技术不可用降级、预算停止、取消传播、已知读取复用、正常/异常/部分初始化反序释放、三个实际编译准备节点及订单事实/工具 Schema/消息约束。

3. 真实 Store/Saver 用例：通过下述同样的显式环境注入，调用 `pytest.main(['tests/test_memory_postgres.py','-q','--tb=short'])`，最终增强版本 **1 passed（5.88 秒）**。

   - 仅 `agent_demo_test / agent_test`，在线身份及所有迁移版本/checksum 核验通过。
   - 通过脚本公开 API 完成测试库 Store setup；setup 前存在的全部 public 表完整行集、列定义均保持。保留库自管 store/store_migrations 表，不修改编号迁移、业务或知识表。
   - 随机唯一 A/B 用户和唯一 profile。A 在两个不同 conversation/thread 读到相同 revision/偏好；B 为真实 empty。三个主图运行使用真实 AsyncPostgresSaver，受控 Supervisor；Store 读取未 mock。
   - 原 Task 澄清续接后，真实 Saver 重载的读取记录保持相同，累计 tool_calls 仍为 1。
   - 完整新 `.venv` Python 进程创建新 Store 池，读取到相同安全 snapshot。
   - 实际读取调用取消传播，后续精确读取正常；取消不能证明已派发 SQL 被撤销，未作这种保证。
   - 用唯一 application_name 查询真实 pg_stat_activity：正常退出、主动异常退出、拥有 Store 上下文的任务被取消后，连接数均归零。受控资源测试另确认先 await batching task，再 Store exit/池关闭。
   - finally 仅按本轮 A namespace/profile 和三个精确 thread_id 清理，完整 public 行集及列定义恢复到 setup 后基线；包括原业务、Saver、知识和其他 Store profile。
   - 调试中测试接线曾漏传 RunLimits，随后遇 Windows Selector loop 不支持异步 subprocess；均修正测试调用。各失败轮 finally 精确清理和保护快照断言通过；未更改核心实现来绕过断言。新进程使用 `asyncio.to_thread(subprocess.run)`，psycopg 仍在 Selector loop 下真实执行。

4. 完整真实库门禁使用以下实际方式（不输出凭据，环境仅当前进程及其探针继承）：

   ```powershell
   @'
   import os, pytest
   from app.core.config import Settings
   os.environ['AGENT_TEST_DATABASE_URL']=Settings().test_database_url.get_secret_value()
   raise SystemExit(pytest.main(['-q','--tb=short']))
   '@ | .\.venv\Scripts\python.exe -
   ```

   首轮 **208 passed / 0 failed / 0 skipped（95.48 秒）**。交付复核将 disabled 工具的 Policy denied 状态统一保持 denied 后，最终版本再次执行；结果见本报告末尾最终记录。

5. 最终代码检查实际命令：

   `.\.venv\Scripts\python.exe -m ruff check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py`

   `.\.venv\Scripts\python.exe -m ruff format --check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py`

   **All checks passed；95 files already formatted**。限定本任务 Python 变更及现有 app，未修改历史 Markdown 格式遗留。

## 边界及待闭环

- development Store setup 本 Implementer 未执行，交主 Agent 按既定授权显式执行及前后保护验证；普通启动在未 setup 的开发库只报告 Store unavailable，保留核心业务。
- 默认 pytest 不请求真实 Chat/Embedding；本任务实际验证采用真实 PG Store/Saver、受控 Chat。未重跑已 VERIFIED 的 Qwen/RAG 实验，也未声称偏好语言表达完成真实模型质量验收。
- Manager.apply、显式查看/保存/删除命令、MemoryWriter 均未实现/装配；留 Task 5.3.2。fixture PutOp 仅用于隔离测试，不代表用户已可保存偏好。
- 未改 `.env`、STATE、AGENTS、旧证据、既有模型/provider；未执行 development 写、SSH、PG 重启、Git、Bridge、其他 Agent 或下一 Task。
- 无已知范围内实现阻塞；独立 QA 与主 Agent 裁决待进行。

补充回归记录：统一保留 Policy denied 后，第二轮完整门禁为 197 passed / 11 failed（99.60 秒）。11 项均是原 `tests/test_knowledge_graph.py` 中将未注册 Memory 工具的读取视为占位 unavailable 的旧状态断言，实际 Executor 结果是 policy_denied；按本 Task 契约更新为 denied，并增加 policy_denied/attempts=0 断言。原业务、来源、草稿和预算断言全部保留。该测试文件属于本 Task 受影响调用方，已列入最终 Ruff/格式检查。

最终记录：完成上述旧状态断言迁移后的最终版本，完整真实 PG 门禁 **208 passed / 0 failed / 0 skipped，90.04 秒**。最终 Ruff **All checks passed**，格式检查 **95 files already formatted**；报告相对链接及新增文件存在性核对通过。测试库本轮 profile/线程已精确清理，原 public 数据保护断言通过。实现会话至此停止，提交主 Agent 审查和独立 QA。

05-QA-001 定向修复实现及测试见[修复记录](resume/record/05-store-reader-fix-01-report.md)，依据[修复提示词](resume/05-store-reader-fix-01-task.md)。保留原[QA FAIL 报告](question/05-store-reader-qa-report.md)，等待原独立 QA 复测及主 Agent 裁决，不以实现自测代替问题关闭。
