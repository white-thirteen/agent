# 修复会话提示词

本目录统一保存主 Agent 交给独立修复会话的提示词；当前经用户授权由Bridge串行派发，历史人工转交记录保留。

每份提示词必须要求修复会话将修复记录整理到 `docs/resume/record/`，关联阶段、Task、问题编号及提示词。各轮任务和报告独立保留，避免覆盖历史证据。

| 阶段与问题 | 提示词 | 修复记录 |
| --- | --- | --- |
| 01 / P2-01 | [标识 NUL 校验修复任务](01-foundation-fix-task.md) | [修复与开发自测报告](record/01-foundation-fix-report.md)，修复及独立回归经主 Agent 复核通过，P2-01 已关闭 |
| 02 / QA-EXEC-01 | [测试异常输出脱敏修复任务](02-qa-credential-output-fix-task.md) | [修复与开发自测报告](record/02-qa-credential-output-fix-report.md)，两轮修复和独立回归已闭环，标准路径问题关闭 |
| 02 / QA-EXEC-01 第二轮 | [warnings 与文件日志修复任务](02-qa-credential-output-round2-task.md) | [第二轮修复报告](record/02-qa-credential-output-round2-report.md)，独立119项和外部3项通过，用户已验收02 |
| 03 / 03-QA-001、002 | [分层与调用关联修复任务](03-tool-governance-fix-task.md) | [修复与开发自测报告](record/03-tool-governance-fix-report.md)，主Agent复核及独立回归通过，03-QA-001/002均关闭 |
| 04 / 04-QA-001～006 | [首轮问题修复任务](04-hitl-checkpoint-refund-fix-01.md) | [首轮修复与开发自测报告](record/04-hitl-checkpoint-refund-fix-01-report.md)，待主 Agent 复核及独立回归 |
| 04 / 04-QA-007 | [绑定修复与补验任务](04-hitl-checkpoint-refund-fix-02.md) | [第二轮修复与开发自测报告](record/04-hitl-checkpoint-refund-fix-02-report.md)，待独立复测及主Agent裁决 |

修复记录规范见 [record 目录说明](record/README.md)。阶段验收及问题裁决见 [独立 QA 与主 Agent 复核](../question/README.md)。
