# PG17.6备份与独立PG17.12恢复演练

2026-11-17。当前仅授权原PG17.6的一致性逻辑备份及独立PG17.12恢复演练。
禁止升级、重启、替换或修改原实例数据；不修改业务代码、已有配置、迁移、冻结设计或Git。
本轮备份、恢复卷和已有持久资源全部保留，不自动进入1.1.2或原库升级。

**主Agent复核通过；独立QA PASS，仅限本轮一致性备份、可靠副本与独立恢复演练。**
原实例未升级、未重启、数据未改；本交付不代表阶段验收或原库升级授权。

首轮真实backup运行54秒、退出1，目录`pg176-20261117T051416Z-7290f4a7d2f6`及材料保留。
失败原因是将Docker `.Mounts`无序数组作为原始字符串比较；实际仅挂载排列顺序改变，
容器ID、启动时间和包版本一致。修复后仍比较每个挂载的完整结构与全部字段，
只规范化列表排序，不删除检查项；在全新子目录/输出路径重跑，不覆盖首轮失败。

首轮快照已观察到：两个业务库各13张表、各5个订单，其余业务事实、Checkpoint、Store与知识表为空；
schema/checkpoint/store迁移行数分别为6/10/4。
这不构成非空Checkpoint/Store/原知识向量的恢复证据；后续候选夹具仍是必要独立能力检查。

## 已完成的真实备份与可靠副本

二轮使用源码SHA256=`72e82a48d034d75f659ddb729fea9cde8b7e404a4aa4f1d43264d62a2d7ecd1c`，
主Agent实际观测退出0，UTC05:19:50.874503～05:20:52.966440，耗时62.091937秒。
[成功JSON](evidence/v2-01-pg1712-backup-restore-evidence-20261117/backup-success.json)
状态为BACKUP_COMPLETED_RESTORE_PENDING；
[首轮失败JSON](evidence/v2-01-pg1712-backup-restore-evidence-20261117/backup-failure-mount-order.json)独立保留。
两个库各自快照内的基线/dump前后相同，后续新快照也确认所有表、schema及序列未改变；
源容器、启动时间、完整挂载结构、精确包与配置/规范化全局权限前后一致。

成功VM目录：
`/home/white7/agent-db-backups/20261117-rehearsal-7c93e5/pg176-20261117T051950Z-6ddfec59da38`。
Windows同名目录位于上述仓库外可靠副本根。
[Windows复制回执](evidence/v2-01-pg1712-backup-restore-evidence-20261117/windows-copy-receipt.json)
记录141个私有文件、406,442字节全部通过大小/SHA核验，manifest SHA256为
`5ad6710a00f03f805f1479c2ac00a884e92548087249199da1d541a4cc12c46d`。

| 转储 | 大小 | SHA256 |
| --- | ---: | --- |
| agent_demo.dump | 29,847字节 | a9e848a1beb984c1f0878dc5a29ec9e982cc989267efe5159a4f6094276a2213 |
| agent_demo_test.dump | 29,938字节 | fd239f9495b073945a9305a216f98e3a9425e2ab8cc44e66d7407045feb44f96 |

主传输阶段最初用rb句柄fsync触发BadFD，改用r+b（未更改数据字节）后完成flush/fsync与SHA重验；
此为持久化操作修正，不是备份内容失败。Windows ACL仅当前用户和SYSTEM。
仓库只复制了脱敏backup JSON和回执；private-manifest、globals、配置、原始转储及私密日志没有进入仓库。

恢复token为`228a7f5b8d92`，对应独立容器/卷/网络分别为
`codex-pg1712restore-228a7f5b8d92`、`codex-pg1712restore-data-228a7f5b8d92`、
`codex-pg1712restore-net-228a7f5b8d92`，全部保留。

## 已完成的独立恢复与连接修正

[真实恢复JSON](evidence/v2-01-pg1712-backup-restore-evidence-20261117/restore-success.json)
记录UTC05:23:17.917916～05:36:17.131396，主Agent实际观测退出0，
状态RESTORE_MATCHED_SDK_PENDING。
两个库各13个源表的完整行count/SHA、schema/列/约束/索引、owner/ACL、数据库/schema ACL、
序列与扩展owner/版本全部一致；规范化全局角色属性、密码hash、成员关系、设置、parameter ACL及tablespace比对通过。
原管理角色CREATE只跳过精确1行，原globals SHA为
`6151f990dd4a5765e82d079b0439389ce1fc1d6c64cad0b4f7af540ee6081388`，
派生恢复SQL SHA为`9c7435a2234108dab963e89611c9be574b357e88667fd72a59051d446ba55e5f`。
实际SQL与私有角色内容未进入仓库。

源两个库的5订单完整行摘要均为
`6d27a87145405ba594577363f0d702fa749e7fd03f4f394d8b56e509d9d6d40c`，恢复后匹配。
原退款、审批、会话、Checkpoint、Store及知识表均为空，恢复后的空表摘要相同，
不能将此解释成非空状态恢复能力已通过。

之后仅在候选`rehearsal_228a7f5b8d92`唯一schema添加synthetic1024 basis向量，
核自距离0与正交距离1，并安装pg_search0.26.6、建Jieba中文BM25夹具查询通过。
恢复完成后源容器/配置/全局权限/全部源表和序列仍保持；新增夹具不在源库。

SDK首轮退出1/OperationalError，尚未进入fixture写入：
Docker internal network没有实际发布请求的`-p 127.0.0.1:56321:5432`，
`docker port`为空，VM56321 connect_ex=111；Windows15632转发因此connection refused。
原restore JSON的host_port=56321是请求参数，不是实际发布成功证据。
保留internal network、原恢复卷和失败，不重建、不删除、不重跑备份；
主Agent实际核定候选内部IP为172.20.0.2，所属network的internal=true，
VM到172.20.0.2:5432 socket成功（connect_ex=0），
已启动Windows127.0.0.1:15633→SSH→172.20.0.2:5432新隧道。
旧15632失败隧道暂留到主Agent精确清理；实际路由由最终保护回执记录。

## 真实SDK写读（重启前）

主Agent实际以项目`.venv`执行下列入口（敏感连接凭据不作为命令参数），观测退出0：

```powershell
.\.venv\Scripts\python.exe -m scripts.rehearse_v2_01_pg1712_restore sdk-write --port 15633 --restore-evidence <仓库外restore-phase.json> --output <仓库外sdk-write-v2.json>
```

[SDK成功JSON](evidence/v2-01-pg1712-backup-restore-evidence-20261117/sdk-write-success.json)
状态SDK_FIXTURE_ROUNDTRIP_PASSED，两库真实角色分别agent_app/agent_test，
登录身份、普通权限、交叉库CONNECT拒绝和本地迁移checksum均核验通过。
锁定实际版本为langgraph-checkpoint-postgres3.2.0、langgraph-checkpoint4.3.1、psycopg3.3.8。
原serializer的HumanMessage与嵌套AgentType、Checkpoint ID/namespace和pending_writes，以及Store独占namespace/operation/revision，
均完成真实SDK写入和当场读取；无setup/迁移/seed。
[首轮失败JSON](evidence/v2-01-pg1712-backup-restore-evidence-20261117/sdk-write-failure-port.json)
保留SDK_FAILED/OperationalError，未在失败连接中写入fixture，不追溯覆盖。
候选重启后实际以新Python进程执行sdk-read（显式--port15633、--write-evidence对应sdk-write-v2.json），
主Agent观测退出0，[重启后SDK JSON](evidence/v2-01-pg1712-backup-restore-evidence-20261117/sdk-read-after-restart.json)
为SDK_FIXTURE_ROUNDTRIP_PASSED，UTC10:01:19.113264～10:01:22.356322。
两库Checkpoint ID与重启前写入证据逐一相同，pending writes、原serializer对象和Store值完整读取通过。

## 最终源保护、保留资源与执行回执

[最终补充JSON](evidence/v2-01-pg1712-backup-restore-evidence-20261117/final-proof-v2.json)
记录RESTART_AND_SOURCE_PROTECTION_PASSED：源身份、配置/全局权限、全部表与序列、规范化globals均保持；
主Agent另核456条既有保护路径SHA全部不变。
原3个持久卷仍在，加本轮新恢复卷，未删除备份/卷；剩余根盘空间1,308,536,832字节。
候选internal=true，实际172.20.0.2及15633 SSH路由明确记录。
重启后两库各2个1024维synthetic向量和BM25命中restore-chunk仍在，扩展版本仍为pg_search0.26.6/vector0.8.7。

主首轮证据采集helper确已重启候选并通过vector/BM25检查，随后取错roles_sha256字段发生KeyError、退出1；
此为证据采集字段错误，不是PG或SDK失败。
后续helper只读采集，不再重启，通过该候选同一container ID的stop/die/start/restart事件确认前次真实重启。
因此最终helper的candidate_before/after启动时间相同，不能把它说成第二次重启。
[首轮helper源码](evidence/v2-01-pg1712-backup-restore-evidence-20261117/pg1712-final-proof.py)及
[补充helper源码](evidence/v2-01-pg1712-backup-restore-evidence-20261117/pg1712-final-proof-v2.py)
按实际执行字节保留，仅作审计，不是业务开发。

实际wrapper退出码回执独立保存：
[备份首轮1](evidence/v2-01-pg1712-backup-restore-evidence-20261117/backup-exit.json)、
[备份成功0](evidence/v2-01-pg1712-backup-restore-evidence-20261117/backup-exit-v2.json)、
[恢复0](evidence/v2-01-pg1712-backup-restore-evidence-20261117/restore-exit.json)、
[采集helper首轮1](evidence/v2-01-pg1712-backup-restore-evidence-20261117/final-proof-exit.json)、
[补充采集0](evidence/v2-01-pg1712-backup-restore-evidence-20261117/final-proof-exit-v2.json)。
这些是实际观测，不以源码成功分支推断退出码。

## 所有权与真实预检

Implementer仅新增[演练脚本](../../../scripts/rehearse_v2_01_pg1712_restore.py)、本报告及脱敏证据。
主Agent负责SSH、备份传输与Windows权限、最终源保护、独立QA和升级审批方案复核。

主Agent只读预检：原4容器healthy，原5镜像及3个已有卷保留；根盘可用约2.9GB，
/tmp为1.7GB tmpfs，RAM3350MB/available2072MB。
源agent_demo为8,563,859字节、agent_demo_test为11,209,875字节；postgres为7,654,547字节且无用户表、视图、序列。
源parameter ACL为0，tablespace只有pg_default/pg_global。备份覆盖双业务库与全局对象/恢复配置，
不冒称备份了postgres数据库内未在本轮转储范围中的内容。

VM专用根目录：`/home/white7/agent-db-backups/20261117-rehearsal-7c93e5`，0700、uid1000。
Windows可靠副本目标：`D:/AI/backups/agent-project/pg17-preupgrade/20261117-rehearsal-7c93e5`，
仅当前用户与SYSTEM ACL，盘空闲约178GB。脚本只对本次新子树设置0700/0600和该备份根所有者，
不改变原配置文件权限，不扩大读取权限，不删除已有备份。

源实际配置路径为`/var/lib/postgresql/data/postgresql.conf`、
`/etc/postgresql/pg_hba.conf`及`/var/lib/postgresql/data/pg_ident.conf`。
配置原样备份，不盲目施加候选环境；原容器的两个bind文件、私密Docker inspect（可能含Env秘密）、
auto.conf、include文件、全包清单，以及原vector.so/control/SQL均备份到受限私有目录。
不docker commit/export原运行容器，不暂停原服务，不把秘密文件或备份转储写入Git。

## 分阶段方法

1. **backup（VM标准库）**：每库独立持有exported REPEATABLE READ READ ONLY事务，
   基线与pg_dump custom `--create --snapshot`共用该库快照，直到dump完成才释放。
   不宣称两个库拥有集群同一瞬间快照。快照会话统一UTC/ISO/extra_float_digits=3/hex。
   pg_dump使用标准ACCESS SHARE，不持业务DML写锁，但不能声称完全无锁或不影响并发DDL。
2. 全局使用`pg_dumpall --globals-only`，保留角色密码/属性/成员关系、parameter ACL与tablespace定义；
   配置和全局元数据前后digest复核。序列不是MVCC对象，dump前后单独核对；变动时保留失败材料交复核，
   不修改源序列。后续源数据差异单列，可能是合法并发业务，不能自动重置原数据。
3. **可靠副本门禁**：主Agent传输仓库外备份并核SHA，确认容量/权限与恢复材料齐全后，才另行执行restore。
4. **restore（VM标准库）**：固定PG17.12 Bookworm/amd64 digest
   `40865bc877a289da75963d97d72b59633f639fc5af7a4e856bfa3714cae5b536`，
   PG server/client=`17.12-1.pgdg12+1`，vector=`0.8.7-1.pgdg12+2`，
   官方pg_search0.26.6包SHA=`16a14d382f088bc23e7c8624e4860fd8bf01a939c67c7695348de0615e323ddb`。
   vector相对原`+1`包存在二进制变化，不能称二进制不变。
5. 新internal network、新容器、新卷；原请求发布VM回环56321未生效，
   实际SDK连接改用SSH直达内部IP，详见连接修正记录。构建和运行768MiB/1CPU预算。
   候选使用agent_bootstrap初始化，随机PASSWORD_FILE仅用于初始化；原globals.sql永远保留，
   另生成私有globals.restore.sql，只跳过恰好一条精确`CREATE ROLE agent_bootstrap;`，
   其他字节原样，记录原始/派生SHA。不执行REASSIGN OWNED。
   原ALTER ROLE恢复后，初始化随机密码不能再代表当前admin密码；管理走容器本地socket。
6. 在加演练数据前，逐库比对全部非系统表的完整行count/SHA、列/约束/索引、owner/ACL、
   schema/database ACL、序列及扩展版本/owner。角色属性、密码hash、成员关系、设置与全局ACL按名称规范化比较，
   不跨集群比较catalog OID。完整规范化内容只留私有备份，公开仅bool/SHA。
7. **源为空的覆盖限制**：如源Checkpoint、Store或知识向量为空，明确报告空表恢复不能证明其非空数据已恢复。
   只在候选唯一schema建立synthetic1024向量与最小中文BM25夹具；这不是Qwen真实向量或检索质量验收。
8. **sdk-write / sdk-read（Windows项目.venv）**：主AgentSSH转发独立端口15633，保留失败的15632记录；
   只在内存中替换现有凭据的host/port，不修改.env。先验证170012和候选postgres数据库唯一token标记，
   再核普通角色登录、跨业务库拒绝、迁移001～006/checksum、现有Saver/Store迁移版本。
   原serializer与锁定AsyncPostgresSaver写读HumanMessage、嵌套AgentType、Checkpoint ID/namespace及pending_writes；
   Store保存独占namespace/operation/revision。无setup、无seed、无业务副作用。
   主Agent仅重启候选后，新Windows进程sdk-read必须读取同一Checkpoint ID与Store值；夹具保留供QA。

SDK夹具只证明恢复环境的序列化/持久读写能力，不冒充待审批Run的真实恢复。
当前源审批/Checkpoint/Store为空；若实际切换前出现活动Task、审批暂停或unknown，须另安排对应隔离演练。

所有命令有期限、逐阶段JSON与私密流式日志。失败保留备份和新卷，不执行prune或旧探针的删除finally。
源配置/inspect/globals SQL/restore日志可能含秘密，全部留受限仓库外备份；仓库只收允许元数据、状态和文件SHA。

## 本地检查与当前证据边界

仅对新脚本运行项目`.venv` Ruff、格式、AST语法检查，通过；
离线核对已安装SDK签名/源码与原checkpoint_serializer的嵌套AgentType序列化还原，通过。
没有运行会写源库的原项目测试、setup、seed、迁移或模型调用。

```powershell
.\.venv\Scripts\python.exe -m ruff check scripts/rehearse_v2_01_pg1712_restore.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/rehearse_v2_01_pg1712_restore.py
.\.venv\Scripts\python.exe -c "import ast,pathlib;ast.parse(pathlib.Path('scripts/rehearse_v2_01_pg1712_restore.py').read_text(encoding='utf-8'))"
```

真实备份、转储SHA、可靠副本、恢复一致性、SDK双进程和重启后持久读写均已在上述机器JSON补录。
不把实现源码或离线序列化检查当作真实SDK通过。

## 升级与回滚建议（尚未执行、须另行批准）

优先使用**全新卷的最终逻辑恢复后切换**，保留原17.6卷、镜像、配置和已核验备份。
本轮含演练夹具的恢复卷仅供验证，不能直接上线。

窗口开始前先离线准备并核验镜像、扩展包、磁盘、备份/恢复脚本与回退入口，
不要把联网拉取或安装计入实际维护窗口。可建议预留30分钟操作预算，
但这不是实测时长或完成保证；本轮62.09秒备份只供当前微型数据量参考，
实际窗口应以另行批准的完整离线演练结果确认。
当前VM根盘仅余约1.3GB；正式操作前必须核定新卷、最终备份与恢复临时峰值容量，
作为明确门禁。容量不足时先扩容或安排独立存储，不删除原卷或已有备份腾空间。

实际维护窗口先停止应用写入、暂停新Task受理并排空活动Run；
pending审批、退款unknown及operation状态先核对，不自动重发副作用。
在双库停写期重新生成最终一致备份，再在另一个全新卷恢复；本轮每库在线快照不冒充该停写期全局一致备份。
逻辑恢复不保留优化器统计，正式新卷恢复后应先ANALYZE，再进行业务查询与性能验收；本轮没有对原库ANALYZE。
保留原锁定Python/SDK版本、迁移001～006/checksum、Checkpoint ID/namespace/pending、Store operation/revision与原知识向量，
不运行setup或修改迁移来冒充升级兼容。

升级开放写入前门禁至少包括原5订单完整行hash、退款/审批/operation幂等与unknown核对，
真实Checkpoint/Store SDK、知识向量是否存在的如实记录、受控新Qwen RAG与原完整回归；
这些业务回归先在隔离副本执行，本轮没有运行源库写测试或调用模型。
原五订单保护继续保持；新场景不得seed，若未来另行授权正式完整门禁，
既有唯一旧测试窄例外仍须原样执行并finally恢复实际原值，不能扩成新用例写源库的通行许可。
源两个库每库5订单的现状汇总为paid未退款2、paid已退款1、unpaid未退款2；
此汇总不替代完整行hash验证。

逻辑恢复会重新创建索引；仍须逐项审查[17.12发行说明](https://www.postgresql.org/docs/release/17.12/)
及[17.11累积项](https://www.postgresql.org/docs/release/17.11/)，包括bpchar、GIN、gist_trgm与TOAST等影响条件。
本轮主Agent已只读核实两个业务库各30个public索引均为btree，agent_demo没有不限长bpchar列，
并检查无replication slots/subscriptions；未在原库执行REINDEX。
不能仅凭原索引都是btree便排除所有升级影响。
pg_search0.26.6官方资产早于17.12发布，其C扩展安全构建来源尚未确认；
本轮不编译，不能宣称CVE-2026-6460等扩展安全重编译要求已全部满足。

开放业务写入前，失败可停止候选并切回保留的原实例/原卷。
新环境已接收写入后，禁止直接切回丢弃期间变化；应先停写、保留差异，评估正向修复或受控反向逻辑恢复，
重点核对退款、审批、记忆和Checkpoint增量。禁止让17.6打开已被17.12写入的数据目录。
备份可靠副本保存在Windows或独立介质，不在VM空间不足时覆盖唯一副本或删除原持久卷。

## 当前停止点

本轮实现与指定实测交付完成，源码冻结SHA
`72e82a48d034d75f659ddb729fea9cde8b7e404a4aa4f1d43264d62a2d7ecd1c`。
未执行原完整回归、Qwen语义RAG、待审批真实Task恢复、原库升级/切换或C扩展安全重编译。
本轮夹具不关闭既有Store时序观察或其他V1遗留；没有下一Task、Git或升级授权。

## 独立QA与主Agent收尾

[独立QA报告](qa/v2-01-pg1712-backup-restore-qa-report.md)结论PASS，
[独立实际证据](qa/v2-01-pg1712-backup-restore-qa-evidence.json)记录141文件重新校验、
456原路径保护、真实向量/BM25、SDK读取与全部public行摘要前后不变。
QA没有再次执行备份/恢复或重启，相关结论复核留存真实证据；实际SDK与SQL读取另行执行。

QA发现锁定Store SDK的aget内含TTL刷新UPDATE CTE，强制SQL只读时会失败，
即使ttl_minutes全部NULL。失败证据保留；主Agent仅授权候选库受控执行该零匹配更新，
QA确认全部public行摘要及Store时间字段前后不变。它不是严格SQL只读API，
QA只读职责也不代表独立只读沙盒；原库没有因此放开写入。

QA完成后，主Agent只停止本轮候选容器释放内存（退出0），原容器继续运行，
ID和2026-11-13启动时间均不变；原3卷及新恢复卷全部保留。
[收尾回执](evidence/v2-01-pg1712-backup-restore-evidence-20261117/closing-receipt.json)记录该边界。
备份、镜像、容器、网络和卷未删除；本轮SSH隧道随会话关闭。
报告及计划交用户审核，停止等待原库升级的明确批准。
