# Task 5.3.1 Store 资源与共享 Reader 独立 QA 报告

2026-11-14。结论：**FAIL，仅 Task 5.3.1**。发现 1 项阻塞问题 **05-QA-001 / P2**，须退回原 Implementer 修复并独立复测。本报告不表示阶段验收，不进入 5.3.2。

依据：根 AGENTS.md、STATE、当前执行/QA任务、实际交付报告、冻结 D05 第6节、第9节、Task5.3.1。业务代码、配置与既有测试保持只读；仅新增本报告及两个独立复现脚本。未执行 Git、SSH、Bridge、PG重启、开发库写入或外部模型请求。

## 05-QA-001 / P2：真实非 object profile 在 Store 解码时逃逸，打断可选业务

位置：`app/infrastructure/store.py:24`、`app/memory/manager.py:45`；实际触发于已安装 `langgraph/store/postgres/base.py:1347`，调用进入 `orjson.loads`。

Manager 在取得 Item 后才执行 `not isinstance(value, dict)`。真实 psycopg JSONB 已将 `[]` 解为 list；Store3.2.0 `_row_to_item` 对非 dict 再调用默认 JSON loader，抛出 `orjson.JSONDecodeError`。异常不属于 Manager 当前捕获的 psycopg.Error/PoolClosed/PoolTimeout，也不属于 Executor 处理的 ToolUnavailableError，故没有形成明确的 `failed/memory_profile_invalid` 结果。

独立真实复现：使用唯一 `qa531-corrupt-<uuid>` 白名单用户，经公开 PutOp 建立自己的 profile，仅将该精确 namespace/profile 的 value 更新为 `'[]'::jsonb`；运行真实编译 `build_order_graph` 的准备路径。实际直接抛：

```text
JSONDecodeError: Input must be bytes, bytearray, memoryview, or str: line 1 column 1 (char 0)
```

预期：损坏 profile 安全分类为 `failed/memory_profile_invalid`；可选读取记 unavailable，保持默认呈现并继续订单业务。实际普通核心业务没有取得 needs_input 结果，图执行被异常打断。此项违反 QA任务对非 object 损坏 JSON 的明确验收要求。须在 Store/Manager 的实际解码边界准确处理该已证实场景，不建议泛化吞掉所有编程错误。未代修。

复现文件：`docs/question/05-store-reader-qa-probe.py`、`docs/question/05-store-reader-qa-corruption-probe.py`。第一脚本在安全分类断言处 exit 1；第二脚本对当前缺陷作观察并记录，exit 0 **仅表示缺陷成功复现和清理完成，不是功能通过**。

## 自己实际执行的验证

所有 Python 均使用 `.venv/Scripts/python.exe`，库仅 `agent_demo_test / agent_test`。每轮独立探针通过在线身份核对及完整001～006文件checksum一致性检查；使用唯一 A/B 用户或唯一 corruption 用户，不覆盖 Demo用户。前后快照比较全部 public 表完整行集及列定义，覆盖业务、Saver、KB和他人 Store。清理仅本轮 namespace/profile，以及既有真实回归自身精确 thread。两轮独立探针 finally 均确认全部行集/列定义恢复。

1. `python docs/question/05-store-reader-qa-probe.py`：实际约8.09秒，exit 1。已通过：三个实际编译专业准备节点均经真实 Store/Reader 读到相同 A profile，不同 conversation/thread/Task，每次1工具预算、1尝试，无工具消息；B真实 empty；缺 memory:read 返回 denied/attempts=0 且计数适配确认零 Store访问；实际 PG 单字段非法返回 partial 且不含非法原值；完整新 `.venv` Python进程新 Store池读取同一持久profile。随后非object损坏安全分类断言失败。finally 全表保护通过。
2. `python docs/question/05-store-reader-qa-corruption-probe.py`：约4.11秒，exit 0。真实未知schema经同编译订单图得到 failed/memory_profile_invalid，记忆 unavailable，核心 needs_input；真实数组profile则直接 JSONDecodeError，确认业务影响。finally 全表保护通过。
3. 独立执行以下定向回归，环境仅当前进程注入 `AGENT_TEST_DATABASE_URL=Settings().test_database_url.get_secret_value()`，不打印凭据：

   ```text
   python -m pytest tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py tests/test_order_graph.py tests/test_refund_preparation.py tests/test_tool_governance.py -q --tb=short
   54 passed in 8.13s / 0 failed / 0 skipped
   ```

   真实 `test_memory_postgres` 实际执行：Store/Saver跨会话持久记录、同Task澄清不重复预算、B隔离、新进程、正常/异常退出与拥有资源任务取消后 pg_stat_activity连接归零、调用取消传播及随后读取、精确清理/全表保护均通过。受控资源测试验证停止并await后台任务后Store退出/池关闭、部分初始化反序释放；受控技术故障可选继续、预算停止与取消传播通过。这些通过不覆盖缺失的真实损坏数据解码路径。
4. 独立执行以下检查：

   ```text
   python -m ruff check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py
   All checks passed!
   python -m ruff format --check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py
   95 files already formatted
   ```

## 源码与回归审查

已实际核对安装版3.2.0公开构造签名、Item和Store退出实现：外部自有独立池、index=None/ttl=None、不自动setup；私有 `_task` 生产访问仅Infrastructure适配。main的 AsyncExitStack 以 Runtime先收敛，再释放模型/Store/Saver/业务池。Reader只委托Manager；Manager只精确 namespace/profile读取并在访问前查固定名单，无全局搜索。模型仅接合法两枚举，内部metadata/非法值不进入偏好提示；合法组合提示固定且远低于128token，完整profile 2KiB上限存在。

Policy 对 model-origin、错误节点/Agent/Task、工具集、空参数与scope复核。节点调用有稳定task相关UUID、摘要及私有record，无孤立ToolMessage；当前scope重新核验，不直接访问Store降级。同Task澄清保存读取record，新Task初始化清空；退款恢复通过None继续原子图，不重跑准备读取。读取不会改变原金额/归属/审批参数，Order/Refund仍使用原事实模板。Memory.apply/用户显式CRUD/V2Writer未提前实现。

当前 `tests/test_knowledge_graph.py` 对未注册Memory工具的预期为 denied，符合 Executor真实 policy_denied，而非技术unavailable。检查可见原业务结果、无公开草稿/来源、检索/模型预算、调用配对与工具schema断言仍在；新增 policy_denied/attempts=0加强拒绝边界。未见通过削弱正确业务断言消除原11项失败的情形。

完整真实库门禁引用未变 Implementer最终交付：**208 passed / 0 failed / 0 skipped，90.04秒**。此前 **197 passed / 11 failed** 及 unavailable→denied 原因已在交付报告保留。QA未无收益重跑全量；自己的54项定向回归如上。主Agent开发库显式setup证据见 `docs/05-store-resource-main-evidence.json`，QA仅阅读，不在开发库运行测试。

## 遗留与裁决

阻塞仅05-QA-001，尚未修复/复测；现有208项及54项通过不能覆盖此失败。真实模型语言表达质量未重测，本Task不作其验收承诺。取消验证不证明已派发SQL撤销或未提交；没有CAS/全局Exactly Once承诺。fixture PutOp不是用户已具备显式保存能力。请主Agent退回原Implementer定向修复，复测前本Task保持FAIL。
