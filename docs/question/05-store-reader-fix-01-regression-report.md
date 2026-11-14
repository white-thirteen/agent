# 05 / Task 5.3.1 / 05-QA-001 独立复测报告

2026-11-14。**05-QA-001：PASS；Task 5.3.1：独立 QA PASS。** 原 P2 问题修复有效，未发现本 Task 其他未关闭阻塞。交主 Agent 关闭问题并作技术裁决；本结论不代表05阶段ACCEPTED，不授权下一Task或Git归档。

依据：根AGENTS.md、STATE、原独立FAIL报告、本轮修复任务及独立复测任务、实际修复报告和必要源码/测试。原FAIL报告和两份旧探针均保持原样。本轮仅新增本报告及 `docs/question/05-store-reader-fix-01-qa-probe.py`，未修改业务、配置、既有测试或历史证据。

## 修复审查

`app/memory/manager.py:47` 在原 `resource.aget` 读取边界仅捕获标准库 `json.JSONDecodeError`，将安装版Store3.2.0的orjson解码异常转换为安全的 `ToolUnavailableError(code='memory_profile_invalid')`。真实库执行证实该类型分类有效。没有新增宽泛 ValueError/BaseException 捕获，没有修改第三方或绕过Store/Manager/Reader/Policy/Executor。后续原schema/revision/2KiB/partial投影保持。

新真实回归对唯一profile的JSONB数组执行实际编译Order图，包含核心继续、failed/code/attempts、空偏好、安全文本、无原始异常日志及全表保护断言；普通ValueError原实例传播回归亦保留。没有通过改变原正确断言隐藏问题。

## QA自己实际验证

全部使用项目 `.venv/Scripts/python.exe`，未调用外部模型。所有PG操作仅专用 `agent_demo_test / agent_test`，在线身份和001～006完整迁移checksum核对；UUID自有白名单用户、精确namespace/profile清理。保护快照逐表比较全部public行集及列定义，包括原业务、Saver、KB及他人Store。未seed、未开发库写/测试、未改.env、未Git/SSH/Bridge/重启PG/另派Agent。

1. 原样运行：

   ```text
   python docs/question/05-store-reader-qa-probe.py
   exit 0
   ```

   自己实际真实Store验证：Order/Refund/Knowledge三个编译准备路径通过；A不同conversation/thread读取同profile，B真实empty；缺scope denied、attempts=0且零Store访问；partial仅保留合法值；完整新Python进程新池仍读取同profile。此前失败的非object数组如今抛安全ToolUnavailableError/memory_profile_invalid，原安全断言通过。finally 全public行集/列定义恢复通过。

2. 新增独立断言探针：

   ```text
   python docs/question/05-store-reader-fix-01-qa-probe.py
   exit 0
   ```

   此探针保留旧观察脚本不动，独立断言真实编译Order路径：未知schema及真实JSONB `[]` 均产生 `failed/memory_profile_invalid`，Memory unavailable，核心业务返回needs_input；数组结果attempts=1、tool_calls=1、空memory_context、无孤立工具消息、data=None、安全固定message。finally 全public行集/列定义恢复通过。

   旧 `05-store-reader-qa-corruption-probe.py` 未重跑或改写；其历史exit0是“缺陷已复现”，不作为修复通过证据。

3. 独立定向真实库回归：在当前进程设置 `AGENT_TEST_DATABASE_URL=Settings().test_database_url.get_secret_value()` 后运行pytest，不打印凭据：

   ```text
   python -m pytest tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py tests/test_order_graph.py tests/test_refund_preparation.py tests/test_tool_governance.py -q --tb=short
   56 passed in 7.69s / 0 failed / 0 skipped
   ```

   包含新真实损坏profile回归、partial/schema/权限、预算耗尽停止、取消传播、三专业准备、正常/异常/取消资源退出、真实Store/Saver/新进程与精确清理。原未变资源/审批恢复源码及前轮QA结论继续适用。

4. 额外独立受控传播探针：通过实际 `read_optional_preferences` → 同Executor → Reader/Manager链分别令resource抛普通ValueError和CancelledError，断言抛出对象仍为原实例且访问仅一次；两项均PASS。确认修复没有将编程错误或Runtime取消伪装成可降级读失败。此项是受控异常边界验证，真实PG分类验证见前两项。

5. 独立执行：

   ```text
   python -m ruff check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py
   All checks passed!
   python -m ruff format --check app scripts/setup_store.py tests/test_memory_reader.py tests/test_memory_postgres.py tests/test_knowledge_graph.py
   95 files already formatted
   ```

## 完整门禁与限制

修复后完整真实PG门禁引用原Implementer的 `docs/resume/record/05-store-reader-fix-01-report.md`：**210 passed / 0 failed / 0 skipped，96.88秒**。本QA自己执行的是上述56项定向回归及独立真实/受控探针，未无收益重跑全量。原208项证据仍保留历史，不替代修复后210项。

本轮未重做真实模型语言表达质量验收，未验证未授权的Manager.apply/显式CRUD；fixture写入不代表用户已可保存。取消不保证已派发SQL撤销/未提交，没有新增CAS或Exactly Once承诺。无范围内未关闭问题，完成后停止。
