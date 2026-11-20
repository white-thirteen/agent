# PG17.12 正式升级脚本 P1 修复独立复测

结论：**FAIL**。脚本 SHA256 为 `27959a572af32bbfefa3a707ddbdcbe4ff4151ba8e5ff78d57f2d58f2f8900ba`，正式开关仍为 False。发现新的 P1 恢复阻塞，须退回原 Implementer 修复并复测。

## FORMAL-QA-003 / P1：源 HBA 原位写入中断后无法按日志恢复

位置：`scripts/upgrade_v2_01_pg1712.py:711`、`:714`、`:769`、`:877`、`:965`。

源 HBA 同 inode 改写由 `write`、`truncate`、`fsync` 多步完成；进程中断、部分写入或 I/O 故障可使文件内容既非原始字节也非完整维护 HBA。即使原文件备份和写前 journal 均已保存，异常恢复及 `rollback-freeze` 最终都调用 `inplace_source_hba`，其对这种中间内容直接拒绝覆盖，无法恢复原 HBA。进程在源仍联网时中断会留下损坏或不完整的磁盘配置，实际生效规则与恢复情况需人工核查；不能声称已安全回退。

独立本地受控复现：使用临时文件保存原 HBA 及对应 inode/元数据，模拟维护 HBA 部分写入，调用真实 `inplace_source_hba` 恢复；函数返回 `Source HBA changed unexpectedly; refusing to overwrite`，部分内容仍保留、原内容未恢复。Windows 本地为进入该函数将缺失的 `O_NOFOLLOW` 常量临时设为 0；未在 Linux 模拟实际崩溃。修复须兼顾可识别的受控写入中间状态恢复与真正未知内容不覆盖。

## 原问题定向复测

- **FORMAL-QA-001：定向复测通过。** 代码不再依赖目标 SQL 判断停止条件，检查容器镜像、标签、卷和只读 HBA 目录等元数据后按目标 ID 停止。独立替身将目标 SQL 检查设为不可调用，确认首条 Docker 命令为 `stop target-id`；写入标记存在时拒绝回滚且未发 Docker 命令。本次替身在 stop 处故意中止，完整恢复流程依赖交付方替身证据，未作真实 Docker 验证。
- **FORMAL-QA-002：常规路径修复已检查，异常恢复未通过。** 源 HBA 先进入拒绝新 host 连接的维护态并 reload，检查现存 client 后才断网；存在 client 时走原 HBA 恢复而不主动断网。断网后再恢复原 HBA；connected/disconnected 两种回退均先恢复 HBA，未知内容拒绝覆盖。上述为静态检查；FORMAL-QA-003 表明受控原位写入中断时恢复边界不完整，因此本轮不能关闭该修复单元。未做真实连接竞态或 PG reload 验证。

实际执行：项目 `.venv` 本地受控替身与临时文件检查、脚本 SHA256 核对；未连接 VM、PostgreSQL 或 Docker，未执行真实升级、业务或模型测试。交付方的本地自检结果见 `docs/v2/v2-01/evidence/v2-01-pg1712-upgrade-evidence-20261117/formal-qa-001-002-fix-local.md`，不等同真实环境验证。源 Compose、PG 连接排空和故障恢复仍须主 Agent 在受控 VM 逐阶段核验。