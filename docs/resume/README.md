# 修复会话提示词

本目录统一保存主 Agent 交给独立修复会话的提示词，由用户人工转交。

每份提示词必须要求修复会话将修复记录整理到 `docs/resume/record/`，关联阶段、Task、问题编号及提示词。各轮任务和报告独立保留，避免覆盖历史证据。

| 阶段与问题 | 提示词 | 修复记录 |
| --- | --- | --- |
| 01 / P2-01 | [标识 NUL 校验修复任务](01-foundation-fix-task.md) | [修复与开发自测报告](record/01-foundation-fix-report.md)，修复及独立回归经主 Agent 复核通过，P2-01 已关闭 |

修复记录规范见 [record 目录说明](record/README.md)。阶段验收及问题裁决见 [独立 QA 与主 Agent 复核](../question/README.md)。
