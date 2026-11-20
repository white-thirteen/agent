# V2 01 Task 1.3.2 V1 回归修复独立 QA

结论：**FAIL**，交原 Implementer 修复后独立复测。范围仅为保护快照及演示清理修复，质量评测不在本报告范围。

- **V201-132-V1-QA-001 / P2** — `scripts/verify_06_delivery.py:142` 未传 `expected_delta`，`scripts/verify_05_memory_manage.py:63` 因此接受任意非负水位增长。纯内存以相同受保护状态构造 watermark 5→999，实际返回 `protected_unchanged=True`；传入期望值 4 时返回 False。完整回归原有严格保护在此被放宽，无法辨认非预期水位写入，不能作为完整质量门禁保护通过证据。
- **V201-132-V1-QA-002 / P2** — `scripts/demo_session.py:175`、`:185` 以本次清理前文档是否存在判断相对初始快照的总增量。正常发布、移除使水位 5→7；首次清理有文档、期望 2 比较通过，重试时文档不存在、期望 0，比对同一实际状态失败。纯内存调用比较函数已复现；同样影响移除完成后快照或报告失败的重试恢复。需要在不放宽意外写入检查的前提下保留可恢复的可信操作证据。

实际定向命令：`.\.venv\Scripts\python.exe -B -m pytest -q tests/test_demo_session.py::test_snapshot_comparison_only_accepts_expected_watermark_advance tests/test_demo_session.py::test_existing_prepare_directory_never_enters_cleanup tests/test_demo_session.py::test_new_directory_partial_failure_keeps_owned_cleanup`，**3 passed**。首次命令误写第三个测试名，pytest 未运行任何测试；修正后结果如上。两项问题均为纯内存验证，未执行数据库写入或真实模型。

已检查 Repository 发布与存在文档的移除各增加一次水位，不存在文档移除不增加；`database_snapshot` 继续校验库名、用户、迁移 checksum、表全集、列及行。真实全量回归尚待修复后重跑；原始回执为 235 passed / 1 failed，不能视作本轮通过。
