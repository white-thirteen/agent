# V2 02 Task 2.1.1 首轮 QA 修复记录

关联任务：[修复提示](../v2-02-task211-fix01.md)；问题：V202-211-QA-001、V202-211-QA-002。修复已提交独立复测，问题状态由主 Agent / QA 裁决。

- **QA-001**：`app/context/compaction.py` 从完整热列表剔除已摘要前缀，使用实际新增消息计算阈值和输入预算；仅增量列表和完整列表均覆盖新消息，全部已处理的重放直接返回原摘要，不调用模型。已摘要消息出现在新消息之后时拒绝，避免重排虚构覆盖。
- **QA-002**：摘要前拒绝非公开 Human/AI 消息；模型调用后覆盖检查或其他同步异常，通过 `CompactionError` 保留已消耗 `model_usage`、各次 `reports` 和汇总 `usage`，并保留原始异常链。Gateway 自身错误继续携带其预算和用量；若存在先前成功调用，也合并该失败快照。用量未知保持未知。
- `tests/test_context_contracts.py` 添加完整/增量/重放、SystemMessage 调用前拒绝以及模型调用后 known/unknown 失败快照的行为验证。纯零计数新增范围在调用前拒绝，避免 LangMem 以零阈值错误宣称完整覆盖。

实际验证（项目 `.venv`，无数据库访问、无新增依赖）：

- `.\.venv\Scripts\python.exe -m pytest tests/test_context_contracts.py tests/test_model_gateway.py tests/test_memory_manage.py tests/test_memory_reader.py tests/test_config.py -q`：42 passed，1 条现有 trustcall 上游弃用警告。
- `.\.venv\Scripts\python.exe -m ruff check app/context/compaction.py tests/test_context_contracts.py`：通过；相同路径 `ruff format --check`：2 files already formatted。
- 设置 `PYTHONPATH=.` 后运行独立 QA 原 `probe.py`：full 和 new 均覆盖 `[1, 2]`，各调用一次；replay 覆盖 `[1]` 且零调用；SystemMessage 在调用前拒绝且零调用。原失败证据未覆盖。

本轮无真实模型或数据库调用；受控测试不能替代独立 QA。未改变冻结设计、持久预算实现或后续 Task。
