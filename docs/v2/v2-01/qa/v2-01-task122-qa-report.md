# V2 01 Task 1.2.2 独立 QA

结论：**FAIL（验收证据未齐）**。受控功能及现有正常语料 Tokenizer 预检通过；冻结设计 §7.2 要求真实模型重排、加载/耗时/内存及超时/关闭证据。报告时固定权重尚未完成准备，真实模型回执未就绪，不能将受控替身作为真实模型验收。此结论是证据门禁未完成，并非已证实实现缺陷。首次 QA 不进入后续 Task。

## 已执行检查

- `.venv` 执行 `python -B -m pytest -q tests/test_reranker_task122.py tests/test_knowledge.py`：**9 passed，0 skipped**。受控模型验证含特殊 Token 的 512/513 边界、所有候选先检查、完整输入和原始负 logit；受控工作线程验证 BGE 超时/取消后 Qwen 容量仍忙、关闭等待和线程完成后释放，以及 V1 知识行为。
- 使用本地固定 revision 的真实 Tokenizer，独立从设计 Q01–Q24、`tests/fixtures/knowledge_cases.json` 的全部 12 条问题和 `data/knowledge/manifest.json` 的全部来源重新切分并配对，逐项比对 `.git/task122-bge-tokenizer-preflight.json`：**36 问题 × 6 Chunk = 216 对全部一致，最大 95 Token，超过 512 为 0**。独立探针 `.git/task122-qa-preflight.py`；未下载或载入真实模型权重。本范围是现有六文档样本，不证明更长合法输入均不会超限。
- 源码核对：Query 与标题/章节/完整正文成对编码，禁用截断并对所有候选预检，再直接填充所验编码送模型取原始 logits；调用超时与取消使用 shield，worker 完成回调释放与 Qwen 共用的进程内锁，关闭将释放排在线程之后。当前未发现 Graph/工具新接线；V1 专用路径保留。

## 待补证

真实固定模型尚需核对来源和权重完整性，实测正常重排、启动/推理耗时与内存、超时/关闭及共享容量行为，并按设计审核正常请求影响。真实模型证据取得后须复核再判定；本报告不替代质量收益或阶段完整门禁。未连接数据库、未修改业务代码或测试。
