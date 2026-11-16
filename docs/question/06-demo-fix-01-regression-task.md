# 06 / Task6.3.1 / 06-QA-001 独立复测

仅原Implementer修复停止、主Agent明确派发后由原QA执行。读原FAIL报告/复现、docs/resume/06-demo-fix-01-task.md及docs/resume/record/06-demo-fix-01-report.md，保留旧报告/脚本/JSON，不代修。

独立验证调用级资源所有权：首次prepare在UUID新目录生成真实订单/Qwen1024知识数据后，记录全部public行集列定义、manifest及保护基线文件SHA；同folder再次prepare应非零拒绝，但前一轮全部数据/文件原样，不能调用旧manifest清理。当前调用真正新建目录后，在已写自有数据处注入失败，仍需按本调用原manifest/baseline精确清理，不能因早拒绝修复放弃失败保障。最后按明确自有目录cleanup，全部public恢复首次prepare前状态。

按实际修改运行定向回归/Ruff及必要真实PG/Qwen，test身份/全迁移checksum/固定五订单保护，禁新seed、.env/006/角色/旧证据/六项暂缓保持。无GUI/ComputerUse：用户已确认手动导入并授权继续，截图只证实际导入与变量存在，客户端脚本/SSE显示仍按未验事实单列。不重复付费Chat/完整故障或全量门禁，无Git/SSH/另派Agent/下一Task。

写docs/question/06-demo-fix-01-regression-report.md及新独立证据，明确06-QA-001 PASS/FAIL与Task6.3.1整体裁决；客户端剩余项与产品缺陷分开，不虚构GUI通过。FAIL退原Implementer，PASS仍由主Agent复核关闭。完成停止。
