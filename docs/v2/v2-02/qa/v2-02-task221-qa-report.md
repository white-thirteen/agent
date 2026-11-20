# V2 02 Task 2.2.1 独立 QA

结论：**PASS**，无编号问题；仅针对本 Task 组件，不代表阶段验收。

- 复核了两种所有者、RunScope 尝试及期限、维护预算数据库原子预留及回执、摘要输入与覆盖、来源及身份限定、LangMem 预检、输出绑定、009 与版本门禁。模型调用不持数据库事务；异常和未知用量不退回预留。摘要发布与维护完成回执分离，并可恢复复用。
- 独立使用项目 `.venv` 和带守卫的本机隔离 PG17.12 专库运行 `local-pg-launcher.py pytest tests/test_context_compaction_postgres.py tests/test_context_contracts.py tests/test_model_gateway.py tests/test_context_archive.py tests/test_config.py -q --tb=short`：**28 passed，0 failed，0 skipped，1 上游弃用警告**。包含真实 PG、唯一 schema、真实文件及 LangMem、受控模型；测试 finally 精确清理 schema。
- 独立 [claim_probe.py](../evidence/v2-02-task221-qa/claim_probe.py) 在同一专库另建唯一 schema 检验活跃 claim 的竞争领取被拒、确认旧执行者消失后的中断恢复、旧预留回执拒绝、新 claim 的回执及两个预留保留；[实际输出](../evidence/v2-02-task221-qa/claim_probe.out) 全部 PASS，schema 删除并核验。该探针并未声称检查正在运行的模型调用被强行中断。
- 检查交付的四份真实小合成调用原始回执；r4 为 1 次、known input 78/output 42、覆盖 2 条、Archive READY、维护 SUCCEEDED、schema 清理。此次未重复真实付费模型调用，也不将小样本当作摘要质量验收。

遗留边界：`interrupt_maintenance` 依赖未来 Runtime 在确认旧执行者已消失并持有会话独占权之后调用；该方法自身不能识别活跃进程，后续接线和真实在途进程终止必须验证，不能把组件 claim 的竞争保护当作该前置条件已完成。Graph/Runtime 调度互斥、Revision 采纳与 Checkpoint、真实断电、冻结质量夹具及资源收益归后续 Task；本次未测完整阶段门禁。正式数据库未操作。
