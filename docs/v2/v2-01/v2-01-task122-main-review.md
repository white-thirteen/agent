# V2 01 · Task 1.2.2 主复核

**Task 1.2.2 = ACCEPTED（2026-11-19）。** 用户授权正式验收及归档，详见[阶段验收](v2-01-stage-acceptance.md#task-122-bge-与推理资源)。以下为当时的技术验收记录。

**VERIFIED。** 正常语料预检、受控异常验证和固定真实 BGE CPU 验收均已完成。独立 QA [复测 PASS](qa/v2-01-task122-retest-report.md)，[首轮缺证记录](qa/v2-01-task122-qa-report.md)保留。

- 固定 BAAI/bge-reranker-base revision `2cfc18c9415c912f9d8155881c133215df768a70`。离线实测启动 18.02 秒，六候选中文与英文重排分别为 4.309 秒和 1.190 秒。输出是有限 raw logits，且有落在 [0,1] 以外的分数。
- 真实超限输入拒绝。强制 1 ms 推理期限后返回 rerank_timeout，随后调用收到 rerank_busy；关闭等候 1.272 秒后容量可重新获取。进程峰值工作集 1,020,796,928 字节，峰值页面文件计数 3,648,540,672 字节；关闭时工作集仍约 1.02 GB，因此只证明模型关闭及容量释放。
- 正常语料为设计 Q01–Q24、V1 知识 fixture 12 题和现有 manifest 六个 Chunk。真实 tokenizer 在完整输入加特殊 Token、禁用截断的条件下检查全部 216 对，最长 95，超过 512 为 0。独立 QA 用同一固定 tokenizer 逐对复算。全配对覆盖比该夹具的实际召回集合更广；未以此判定冻结语料的质量收益。
- 两模型共享 CPU 容量的争用由受控线程测试验证，未在本实测同时载入真实 Qwen。独立 9 项受控和 V1 测试通过，具体见[实现报告](v2-01-task122-implementation-report.md)。

[真实运行回执](evidence/v2-01-task122-evidence/real-bge-receipt.json) · [全部输入对长度](evidence/v2-01-task122-evidence/normal-corpus-pairs.json) · [证据摘要](evidence/v2-01-task122-evidence/sha256-manifest.json)。
