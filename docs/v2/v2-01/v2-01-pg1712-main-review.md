# PG17.12隔离兼容排查：主Agent复核

2026-11-17。主Agent接受[独立QA PASS](qa/v2-01-pg1712-compatibility-qa-report.md)，**仅限本次固定组合的符号根因及最小功能排查**。原PG17.6未升级/重启/替换，V201-111-QA-001/P1保持OPEN，不进入1.1.2，不将V2 01标VERIFIED或正式验收。

## 根因与真实结果

[原始机器证据](evidence/v2-01-pg1712-compatibility-evidence-20261117.json)直接核对原实际postmaster exe及复制哈希：PG17.6不导出pg_mblen_cstr，固定官方pg_search.so含该UND依赖；PG17.12实际运行exe有已定义导出。结合上一轮同包预加载FATAL，确认该二进制组合的缺符号根因，而非仅按包名猜测。

官方[2026-02-09修复邮件](https://www.postgresql.org/message-id/E1vpEoc-001x3U-14@gemulon.postgresql.org)介绍CVE-2026-2006的多字节边界检查；邮件为REL_16_STABLE背景，不冒充17分支commit。[17.8发行说明](https://www.postgresql.org/docs/release/17.8/)包含此修复；固定[REL_17_6源码](https://github.com/postgres/postgres/blob/REL_17_6/src/backend/utils/mb/mbutils.c)无该函数，[REL_17_8](https://github.com/postgres/postgres/blob/REL_17_8/src/backend/utils/mb/mbutils.c)和[REL_17_12](https://github.com/postgres/postgres/blob/REL_17_12/src/backend/utils/mb/mbutils.c)有，和实际ELF一致。

实测组合为PG17.12 Bookworm/amd64、server/client17.12-1.pgdg12+1、vector0.8.7-1.pgdg12+2、pg_search0.26.6及已固定镜像digest/官方包摘要。真实预加载、CREATE EXTENSION、ParadeDB Base Scan、中文text ID、事务更新/回滚/提交后可见性和容器重启后检索通过。仅有极小自编语料，未测试真实Qwen/BGE、完整Hybrid/同快照/质量或应用回归，不外推为完整升级验收。

## 证据与保护

实际执行源SHA为2b6b10e0fdb813e2a170e5bfad2faa9e427d5000be2a97cb698c6fd14dc4345a，构建日志SHA为557345d4c6aa1c53e35de9f6e3b2ddc614eb694ae0b271a19f7be804ed6c6500，与原始JSON相符。Launcher未直接wait采集退出码，以最终JSON和逐命令/日志为实测依据，不把源码成功分支返回0写成观测退出码。

原两库各13张public表全行/列摘要、版本及原容器/挂载/启动时间/实际exe/包版本前后完全一致。候选采用独立卷、无网络/主机端口、768MiB/1CPU；没有复用原数据目录。Windows截断下载被校验拒绝并保留失败记录；仅同一官方包有限重试后校验成功，没有尝试其他版本或编译。

原始机器JSON和QA报告未覆盖。仓库全局忽略*.log，主Agent将本轮日志字节不变归档为.txt，逐一核对哈希，[archive-map](evidence/v2-01-pg1712-evidence-20261117/archive-map.json)记录远端名到本地名；原JSON中的远端.log路径保持原样。当前完整[实现报告](v2-01-pg1712-compatibility-report.md)链接已指向可归档副本。

## 精确清理

探针最终本token容器/卷/镜像层均为空；级联删除后重复删除父image的NoSuchImage原错误保留，QA已核其具体前因，不能普遍忽略清理失败。

主Agent额外按实际tag/id删除本轮新增PG17.12基础镜像：[main-cleanup](evidence/v2-01-pg1712-evidence-20261117/main-cleanup.json)显示删除退出0/base_absent，原容器id/start/running保持，剩原五镜像。QA结束后核对外层/tmp/agent-pg1712-compat-aYhgTD绝对路径、无符号链接、唯一14文件集合和探针PID已不存在，逐文件删除再rmdir；[transfer-cleanup](evidence/v2-01-pg1712-evidence-20261117/transfer-cleanup.json)记录removed=true。外置临时回执取回后亦已精确删除。无prune或原资源清理。

## 推荐路线及停止条件

建议将PG17.12列为后续迁移候选，而非转SQL BM25。本次未批准部署，推荐先由用户单独授权升级准备/恢复演练，再评估维护切换：

1. 固定镜像与适配扩展包，核验17.12的C扩展重编译要求，不能因旧预编译包能加载就声称安全修复全部覆盖。
2. 在停写边界取得双库/角色权限/配置清单的一致备份，存Windows或独立介质；另新卷恢复演练，保留原镜像/容器/未被新版本写入的恢复副本，不覆盖唯一卷。
3. 核对迁移001～006/checksum、原向量/来源、Checkpoint ID/namespace/pending审批、operation与Store revision；保留锁定Saver/Store库版本，验证真实恢复和业务行为，不擅自setup/升级依赖。
4. 按[17.12发行说明](https://www.postgresql.org/docs/release/17.12/)和累计小版本说明评估受影响索引/完整备份要求；现有public均btree不代表所有索引都豁免。新环境启用写入前保留可回切边界，启用后需先停写核对期间增量，不能直接回切丢弃退款/记忆或重用新版本写过的唯一目录。

备份恢复、原库升级、完整应用回归及全部扩展安全重编译均未执行。本轮不修改业务代码、已有配置或迁移，不Git提交；已完成有限排查，等待用户明确授权，不自动继续开发。
