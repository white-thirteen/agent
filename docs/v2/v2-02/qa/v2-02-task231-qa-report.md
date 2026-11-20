# V2 02 Task 2.3.1 独立 QA 首轮

结论：**FAIL**。V202-231-QA-001 / P2 未关闭，交原 Implementer 修复后独立复测；不代表阶段验收。

## V202-231-QA-001 / P2：已发布 Revision 的维护回执在采纳后无法恢复

`app/context/maintenance.py:284`–`292` 先要求最新 Checkpoint 的 context_ref 等于工作来源，`:359`–`:366` 才发布 Revision 并登记回执。发布成功至回执写入之间中断后，若会话已采纳该 Revision，恢复 worker 因来源视图变化提前返回，不能补写 revision。`resume_pending` 在 `:207`–`:218` 持续选择该 SUCCEEDED、revision NULL 记录；有界扫描可能占据后续维护的恢复名额。

独立探针 `docs/v2/v2-02/evidence/test_qa231_receipt.py` 使用隔离真实 PG、真实 Saver、真实文件和受控模型，生成真实已发布 Revision；将该工作回执改为 NULL 模拟发布后回执前中断，通过真实 Saver 的 aupdate_state 设置已采纳 ref 并移除被采纳消息（模拟采纳后的状态），再调用 worker 和两次恢复扫描。此处没有运行真正的进程重启或新请求采纳，故证据限于等价持久状态和恢复路径。观察 `('SUCCEEDED', None)`，相同工作连续两次被扫描选中；期待回执为 1 的断言失败。探针自身 guard 和 finally 精确清理用户数据、文件及 Saver thread。

命令：`.\.venv\Scripts\python.exe docs/v2/v2-02/evidence/linux-pg-launcher.py pytest docs/v2/v2-02/evidence/test_qa231_receipt.py -q -k False --tb=short`；实际 1 failed、1 deselected、1 第三方弃用警告，输出 `QA_INTERLEAVING ('SUCCEEDED', None) QUEUE_OCCURRENCES 2`。失败即缺陷证据，不能计为通过。

## 实际验证

- 交付记录所列 11 个受控测试文件独立重跑：119 passed，8.91s。
- 六个隔离 PG 组件文件组合：14 passed、1 failed。失败为 `test_real_memory_commands_cross_threads_process_crud_and_exact_cleanup` 的全库快照检查；它与本 QA 探针同时运行，探针临时 Saver 行进入其快照。探针结束并清理后单独重跑 `tests/test_memory_manage_postgres.py`：3 passed，15.59s。该并发造成的测试干扰如实保留，不将首次结果报为通过。其他 14 项在组合运行中通过；受控模型及退款业务替身不称为全业务真实。
- 客户端静态检查脚本通过 JSON、OpenAPI 引用、端点、环境键及旧命令提示；未操作客户端 UI。
- 检查 Builder、Gateway、模型节点、恢复维护与偏好服务。普通 Gateway 显式 `max_output_tokens` 参数可覆盖实际调用上限，而 Builder 使用配置 reserve；当前业务节点没有传该参数，故未以不可达假想场景另立问题，建议修复时确认接口契约。前四 Task 主复核及 222 修复记录已查阅。

## 遗留

未重跑真实模型质量、付费调用或阶段完整门禁，按授权留给 2.3.2；客户端 UI 未实测。上述源码检查不替代尚待的缺陷修复及复测。
