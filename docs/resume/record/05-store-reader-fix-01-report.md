# 05 / Task 5.3.1 / 05-QA-001 定向修复记录

2026-11-14。原 Implementer 按[本轮修复提示词](../05-store-reader-fix-01-task.md)处理阶段 05、Task 5.3.1、问题 **05-QA-001 / P2**。原[独立 QA FAIL 报告](../../question/05-store-reader-qa-report.md)及两份 QA 探针保持不变。本记录仅交付实现与自测，问题是否关闭由主 Agent 与原独立 QA 复测裁决。

## 根因与修复边界

已实际读取安装版 Store 3.2.0 的 `_row_to_item`：psycopg 将 JSONB `[]` 返回为 list，框架对非 dict 值再次调用默认 orjson loader；`orjson.JSONDecodeError` 在 Item 返回前抛出，Manager 原先取得 Item 后的 object guard 来不及执行。实际 MRO 确认该异常继承标准库 `json.JSONDecodeError`。

唯一生产修改位于 `app/memory/manager.py:47`：仅包围原 `resource.aget(namespace, 'profile')` 的读取捕获 `json.JSONDecodeError`，转换为无原始值/异常文本的 `ToolUnavailableError(code='memory_profile_invalid')`。不捕获所有 ValueError，不改变其他编程异常或取消传播；保留原 Store、Manager、Reader、Policy/Executor 调用链。Executor 仍形成真实 `failed/memory_profile_invalid` 工具结果，可选读取采用 `memory_read_status='unavailable'` 后继续核心业务。

没有修改第三方、依赖、Store 解码器、模型配置或业务节点。原 unknown-schema、partial、scope、预算及资源释放语义保持。

## 修改与验证位置

- `app/memory/manager.py:47`：上述精确异常分类与原因注释。
- `tests/test_memory_postgres.py:292`：新增真实非 object profile 回归。公开 PutOp 创建唯一 profile，仅按精确 prefix/key 将自己的值改为 JSONB `[]`；真实编译 Order 图经原准备节点读取。断言核心 needs_input、Memory unavailable、工具 failed/memory_profile_invalid、attempts=1、空偏好/无孤立消息、零模型调用、安全错误文本且日志不泄露 JSONDecodeError/原始驱动异常。
- `tests/test_memory_reader.py:329`：验证普通 ValueError 原实例继续抛出，防止扩大捕获。
- 本记录及[原开发交付报告](../../05-store-reader-delivery-report.md)追加修复入口；原 QA、旧失败与旧证据均保留。

真实回归只使用 agent_demo_test / agent_test。复用 `database_snapshot` 验证在线身份、001～006 全部版本与文件 checksum，以及全部 public 表完整行集/列定义。finally 只删除本轮随机 namespace/profile，并断言全库恢复；不创建持久 Saver 线程。全量门禁包含原真实 Saver/KB/业务隔离、跨进程 Store、三个专业 Reader、关闭/取消测试，各用原专属 fixture 精确清理。

## 实际命令与结果

全部使用项目 `.venv`。真实库环境仅按以下方式注入当前进程，不打印凭据，不改 `.env`：

```powershell
@'
import os, pytest
from app.core.config import Settings
os.environ['AGENT_TEST_DATABASE_URL']=Settings().test_database_url.get_secret_value()
raise SystemExit(pytest.main(['-q','--tb=short']))
'@ | .\.venv\Scripts\python.exe -
```

1. 修改生产代码前，以同一包装器的 pytest 参数 `['tests/test_memory_postgres.py::test_real_nonobject_profile_is_safe_optional_order_failure','-q','--tb=short']` 运行新增真实回归：**1 failed，4.34 秒**，准确复现 orjson.JSONDecodeError 从 Store `_row_to_item` 逃逸并打断 Order.prepare_query。finally 全 public 数据/列定义保护断言通过。
2. 修复后，以同一包装器运行 `tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py tests/test_order_graph.py tests/test_refund_preparation.py tests/test_tool_governance.py -q --tb=short`：**56 passed / 0 failed / 0 skipped，8.93 秒**。真实非 object 回归和其他受影响边界均通过。
3. 最终完整真实 PG 门禁使用上面的全量命令；结果见文末最终记录。
4. 实际执行 `.\.venv\Scripts\python.exe -m ruff check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py`：最终 **All checks passed**。首轮只发现新增测试函数内 import 排序，已由 Ruff 整理；未改测试行为。
5. 实际执行 `.\.venv\Scripts\python.exe -m ruff format --check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py`：**95 files already formatted**。

依赖清单未变，无安装/升级，无需本轮 pip check。

## 未闭环与限制

等待原独立 QA 复测及主 Agent 裁决，不自行标记 05-QA-001 已关闭。测试没有请求外部 Chat/Embedding；本修复验证真实 PG/Store 与实际编译图的安全分类及继续执行，不扩大语言表达质量验收。取消不承诺已派发 SQL 撤销，保留原限制。

未执行开发库写入/测试、SSH、PG 重启、Git、Bridge、其他 Agent、006 或 Task 5.3.2；没有修改 STATE、AGENTS、真实 `.env` 或原 QA 文件。

最终记录：本修复最终完整真实 PG 门禁 **210 passed / 0 failed / 0 skipped，96.88 秒**。原真实 Store/Saver/业务/KB 与 Reader、资源生命周期回归均通过；新增损坏 profile 在精确清理后全部 public 行集/列定义恢复。最终 Ruff All checks passed、95 files already formatted。实现会话停止，等待原独立 QA 复测与主 Agent 审查，不宣告问题关闭。
