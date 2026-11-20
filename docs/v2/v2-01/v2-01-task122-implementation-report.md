# V2 01 · Task 1.2.2 实现报告

`app/knowledge/reranker.py` 提供固定 `BAAI/bge-reranker-base` revision `2cfc18c9415c912f9d8155881c133215df768a70` 的本地 CPU CrossEncoder 生命周期；使用本地 safetensors、禁止远程代码，默认每批 2 条，异步调用默认 15 秒。每个 Query 与 `search_text(title, section, content)` 完整配对，使用 BGE Tokenizer 含特殊 token 且不截断；所有候选通过 512 token 检查后，直接将已检查的编码送入模型，返回原始 logits。超长、忙碌、超时、不可用和无效分数分别报技术错误，不降级。

`app/knowledge/cpu_capacity.py` 及 `embedding.py` 为 Qwen 和 BGE 共用进程内非排队 CPU 容量；工作线程真实结束才释放容量，调用超时、取消及关闭均不提前释放。各模型关闭时在后台等待自己的工作完成，再释放模型。配置位于 `app/core/config.py`。本 Task 未接 Graph 或工具；应用生命周期装配和集中检索整体预算仍由后续接线完成。

## 实施者验证

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_reranker_task122.py tests/test_knowledge.py`：9 passed。受控替身覆盖 512/513 token、全候选先检查、完整输入、原始负 logit，BGE 超时及取消后 Qwen 无法抢占、关闭等待，以及既有 Qwen 行为。并非真实模型性能证据。
- `.\.venv\Scripts\python.exe -m ruff check app/knowledge/reranker.py app/knowledge/cpu_capacity.py app/knowledge/embedding.py app/core/config.py` 和对新测试文件的 Ruff 检查通过；格式化已执行。

主 Agent 独立准备的本地 Tokenizer 预检临时结果为 36 问题 × 6 Chunk 共 216 对，最大 95 token、超 512 为 0；来源范围、可追溯结果文件和真实模型加载/资源/异常证据由主 Agent 核实并补充。仅凭上述受控测试不能声明真实模型验收或阶段验收；正常语料门禁及真实环境仍待复核。
