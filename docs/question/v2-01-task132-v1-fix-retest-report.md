# V2 01 Task 1.3.2 V1 修复独立复测

结论：**PASS（两项修复的受控复测）**。V201-132-V1-QA-001、002 的关闭建议交主 Agent；完整真实回归尚未执行，本结论不等同完整门禁通过。

- 001：保护快照默认期望水位增量为 0；完整门禁的 `--expected-publication-delta` 明确传入固定值并写入报告。其他所有表行及列、索引状态非水位字段仍严格比较。受控用例验证 5→999 被拒绝、指定的精确 5→7 通过，非预期增量和其他字段改变被拒绝。
- 002：删除前以原子替换写入绑定文档 ID 的本地意图标记；首次存在文档及随后不存在文档的重试均要求初始水位精确增加 2，不匹配 ID 拒绝。受控用例覆盖标记与重试分支；未实测真实数据库上的中断恢复或系统掉电。
- 定向命令：`.\.venv\Scripts\python.exe -B -m pytest -q tests/test_demo_session.py::test_snapshot_comparison_only_accepts_expected_watermark_advance tests/test_demo_session.py::test_cleanup_intent_survives_delete_and_report_failures tests/test_demo_session.py::test_existing_prepare_directory_never_enters_cleanup tests/test_demo_session.py::test_new_directory_partial_failure_keeps_owned_cleanup`，**4 passed**。未访问数据库、未加载真实模型。

共享 `agent_demo_test` 完整成功路径的预期水位增量由源码独立计算为 **9**：

1. `tests/test_knowledge_postgres.py::test_real_publication_rollback_current_sources_and_exact_cosine`：新建、更新、删除各 +1，共 **3**。相同版本重放、唯一约束异常事务回滚和 finally 再删除均不增加。
2. `tests/test_knowledge_postgres.py::test_governed_rag_pg_sources_checkpoint_and_deleted_draft`：新建和答案前删除各 +1，共 **2**；finally 再删除不增加。
3. `tests/test_demo_session.py::test_real_prepare_ownership_and_partial_publication_cleanup`：正常 prepare/cleanup 与注入失败后的 prepare/cleanup 各发布、删除一次，共 **4**。

假设以上真实用例全部完整运行，测试库无其他并发发布，task112/121/131 专用隔离库不指向共享库。该数值不是从实际运行后的水位反推；若测试环境、执行路径或并发条件改变必须重新核对。完整真实回归及其中实际数据保护核验仍待主 Agent 执行。

## 完整回归回执补充核对

主 Agent 后续执行完整真实回归；独立只读核对 [完整回执](../v2-01-task132-regression-evidence/task132-full-regression-retest.json) 和 [Qwen 清理回执](../v2-01-task132-regression-evidence/task132-full-qwen-retest.json) 与 `.git` 原始文件逐字节一致。完整回执记录 **238 passed / 0 failed / 0 skipped**、退出 0，应用健康就绪，连接池关闭且无遗留 Qwen 线程；14 项保护对象中除 `knowledge_index_state` 外前后行数、列数和摘要均相同，索引状态行列数相同，水位 16→27、精确 +11，回执的保护比较通过。JSON 仅保存摘要和比较结果，非水位列逐值一致由运行时比较断言记录，不能从摘要单独重建。

先前独立源码推导 +9 的假设不适用于此次 launcher：核对 `.git/task131-local-validation.py`，它把 `AGENT_HYBRID_TASK131_DATABASE_URL` 和共享 `AGENT_TEST_DATABASE_URL` 均指向同一隔离测试库；`test_hybrid_task131_postgres` 新建和删除各 +1，故总预期为 **+11**。这是对先前假设的更正。

Qwen 回执记录正常及注入失败清理 PASS，水位 16→20、精确 +4；14 项中仅索引状态摘要变化，其他对象摘要、行列数一致。以上为回执核验，未另行运行模型或连接数据库；不涉及 Task 1.3.2 检索质量结论。
