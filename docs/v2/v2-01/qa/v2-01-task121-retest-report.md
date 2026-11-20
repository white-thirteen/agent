# V2 01 Task 1.2.1 · V201-121-QA-001 独立复测

结论：**PASS**。V201-121-QA-001 / P2 的修复通过本次独立复测，交主 Agent 复核关闭。首次 FAIL 及原始证据继续保留在 [初次 QA 报告](v2-01-task121-qa-report.md)。本结论仅针对该问题，不能代替阶段验收。

修复后 `hybrid_candidates` 的 `asyncio.timeout(5)` 覆盖连接池获取、只读事务、准备检查和两路查询；数据库单语句期限使用同一常量。超时、连接池等待超时及 SQL 取消映射为 `retrieval_timeout`，其他数据库故障保留独立错误映射。

使用项目 `.venv` 独立执行 `python -B .git/task121-local-validation.py hybrid -q tests/test_hybrid_task121_postgres.py tests/test_hybrid_task121.py`：数据库标记守卫通过，**2 passed in 17.53s，0 skipped**。真实隔离 PostgreSQL 测试在实际事务中注入两次各 2.7 秒的 `pg_sleep`，断言累计期限触发 `retrieval_timeout` 且耗时在 4.5 至 7 秒；随后借出全部三个连接，断言事务空闲及查询可用，并再次成功检索。另占满连接池，断言等待也受累计期限约束，释放后检索成功。测试按唯一隔离库标记和空表检查执行，精确清理本次创建的表。

受控延迟用于验证期限及恢复，不是性能测量。Embedding 为测试替身；本次未连接正式库、未验证 BGE 或完整质量门禁。BM25 并发统计漂移等既有阶段风险不在本问题复测范围。
