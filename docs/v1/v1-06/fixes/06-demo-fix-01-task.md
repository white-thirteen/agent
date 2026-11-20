# 06 / Task6.3.1 / 06-QA-001 定向修复

仅主Agent派发、原QA停止后由原Implementer执行。依据docs/v1/v1-06/qa/06-demo-qa-report.md及06-demo-qa-reprepare-evidence.json。06-QA-001/P2：同folder第一次prepare成功后，再prepare因mkdir FileExistsError失败，但main异常分支只看旧protected.pickle存在而清理上一轮订单/向量及可能的会话/审批/Memory。真实PG已复现且最终精确清理。

修复scripts/demo_session.py的调用级资源所有权：既有目录拒绝时不能清理或改动上一轮任何文件/数据库事实；只有当前调用确实新建目录并写入的准备数据，才允许在该调用失败后按其manifest/baseline清理。选最简单明确的所有权边界，不靠目录里存在旧文件猜测本调用取得所有权，不引入通用恢复平台。保留新建准备中途失败的精确清理，不因早拒绝修复削弱该保障。

增补有意义的定向回归，至少证明重复同folder保持已有订单/向量/manifest/原基线原样，以及本调用实际准备失败仍精确清理。单元可受控，真实集成用test库UUID自有数据与真实Qwen/PG，不改固定五订单。按现有契约核身份、001～006checksum、完整public行集和列定义；结束精确清理/自建进程关闭。默认不重新付费Chat，不机械重跑前序故障/全量门禁。

可同步演示说明中重复准备的行为及本次结果，不覆盖旧FAIL/复现证据。保护.env/006/冻结设计/角色/六项暂缓差异，不Git/Bridge/SSH/PG重启/GUI操作/另派Agent/进入632。你不是唯一工作者，不回退已有改动，主Agent拥有STATE/AGENTS/主协调。

必须交修复记录docs/v1/v1-06/fixes/records/06-demo-fix-01-report.md，关联阶段06、Task6.3.1、06-QA-001及本提示词，列修改位置、实际命令/通过失败与数据保护、未闭环项。完成停止，交回原QA独立复测；不能自行关闭问题或宣布阶段通过。
