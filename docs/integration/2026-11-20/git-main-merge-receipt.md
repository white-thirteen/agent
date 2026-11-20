# V2合入main回执

2026-11-20，用户明确“记录即可，无需现在修复，将V2 branch合并到main上”。两项联调发现按[处理决定](issue-disposition.md)保留，不修复、不标记关闭，不放宽原验收指标。

## 实际Git结果

- 原main及origin/main：`232469acf7e576883e84d58c5a140fd598d9b00e`。
- 已测试V2代码基线：`1c9a4b9ad071ffdef9317f7efbd912b05032f786`。
- V2联调/暂缓记录提交：`371f3d102b5ba5e95b3771ae7bc4a160c0e18c84`，108文件，仅记录、探针、原始证据、导航及字节保留规则，无生产代码改动。
- main合并提交：`3c344af46e29c9152dabe1e58eac54a537fd508b`，使用`--no-ff`，父提交分别为原main和上述V2记录提交，无冲突。
- 合并后、回执提交前，`git diff --exit-code v2 main`为空，整个合并树与V2一致。
- `git push --atomic origin main:refs/heads/main v2:refs/heads/v2`成功；随后`git ls-remote --heads origin main v2`分别返回`3c344af...`及`371f3d1...`完整SHA，两个远端分支已核验。
- 本回执及导航以main上的文档提交补记；其自身SHA及最后远端位置以Git日志和最终回复为准。

## 验证及边界

沿用本次[联调](report.md)与[独立QA](independent-qa-report.md)：完整回归322 passed/0 failed/0 skipped、真实多候选专项2 passed，以及真实TCP/PG/模型、跨进程审批、Context和SSE断流证据。合并树未改变已测代码，补记仅文档，本轮不重复付费或业务测试。

IT-001真实路由异常保持待归因；IT-002固定中文订单摘要限制保留。没有把用户的暂缓决定写成已修复或额外阶段ACCEPTED。

原4项无关untracked文件继续保留在原V2工作区，未提交、移动或删除；main在既有干净worktree中合并。真实.env、.git私有凭据/helper和完整原始行集基线未归档；106项联调记录逐文件确认Git blob与本地字节一致，已知凭据值扫描0命中。没有修改正式数据库、执行新迁移、部署应用或进入后续开发。
