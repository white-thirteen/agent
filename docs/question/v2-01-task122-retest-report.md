# V2 01 Task 1.2.2 独立 QA 复测

结论：**PASS**，交主 Agent 复核。首次 QA 因真实模型回执缺失判 FAIL，该历史结论和证据保留在 [初次 QA 报告](v2-01-task122-qa-report.md)。本结论限 Task 1.2.2，不代表整个 V2 01 阶段或检索质量收益通过。

## 实际复核

- 核对主 Agent 执行的 `.git/task122-real-bge.py` 和 `.git/task122-real-bge-receipt.json`：固定 revision 的真实 CPU BGE 加载及中、英文各六 Chunk 评分；真实超长输入报 `rerank_input_too_long`；强制 0.001 秒超时后返回 `rerank_timeout`，再次调用返回 `rerank_busy`，关闭等待完成后共享容量锁可重新取得。退出 0 为主 Agent 报告；本 QA 审查探针、回执及断言，没有为此重复加载模型。
- 独立 `Get-FileHash`：`model.safetensors` SHA256 `ced967c45fd1902eb92716c9ceeca7c95a936770ea9db611f5a841b926e33fbd`，与探针、回执及下载记录一致；`tokenizer.json` 为 `9eb652ac4e40cc093272bbbe0f55d521cf67570060227109b5cdc20945a4489e`，`sentencepiece.bpe.model` 为 `cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865`，均与既有固定下载记录一致。
- 主 Agent 实测载入 18.020 秒；中/英文六候选计时分别 4.309/1.190 秒（探针计时还包含评分后的 Tokenizer 长度检查）。进程峰值工作集 1,020,796,928 字节，峰值页面文件使用量 3,648,540,672 字节；这是进程指标及单次样本，不是服务容量或延迟保证。关闭后工作集仍约 1.02 GB，容量锁已释放不等于内存全部归还操作系统。
- 本 QA 先前实际运行受控及 V1 知识测试 **9 passed / 0 skipped**，覆盖 512/513 边界、完整输入、原始 logit、取消及超时期间 Qwen/BGE 共用容量；独立使用真实 Tokenizer 重算设计 24 问题与 V1 12 问题、六来源全部 Chunk 的 216 对，逐对与回执一致，最大 95 Token、超限 0。

## 限制

真实模型回执覆盖一个受控超时后的忙碌和关闭，Qwen/BGE 跨模型争用及取消由受控线程验证；不能将其称为真实双模型并发测量。正常语料预检只覆盖现有六来源及已列问题，不证明所有合法长输入不会超限。Graph/工具接线、四组质量对照和阶段完整门禁尚属后续授权范围。本 QA 未连接数据库、未修改业务代码或既有测试、未重复运行资源密集模型。
