# PG17.12 原库升级执行与验收报告

## 当前结论（2026-11-17）

**原服务已升级至 PostgreSQL 17.12，独立最终 QA PASS，主 Agent 复核通过。**
服务继续使用 `192.168.150.101:5432`，项目与 VM 原 `.env` 未改。
本轮不代表 V2 01 阶段完成，不进入后续开发，不执行 Git 提交或推送。

| 项目 | 实际结果 |
| --- | --- |
| 服务端及客户端包 | `17.12-1.pgdg12+1`，实际服务版本 `170012` |
| 活跃扩展 | `plpgsql 1.0`、`vector 0.8.7`；vector 包 `0.8.7-1.pgdg12+2` |
| 新正式卷 | `pg1712-final-data-6595e98667c4`，由停写后的最终备份全新恢复 |
| 正式容器 | 原名称 `agent-engine-demo-db-postgres-1`，状态 healthy；新项目 `agent-engine-demo-db-v2` |
| 原容器 | `agent-engine-demo-db-postgres-1-pg176-6595e98667c4`，已停止保留，仍使用原卷 |
| 原卷与其他卷 | 原 `agent-engine-demo-db_agent_pg17`、其余原卷、演练和验证卷均保留，共 6 卷 |
| 数据及权限 | 最终 QA 真实只读比较两库各 13 张 public 表、全部行摘要、结构/索引/约束/ACL/序列/扩展与最终备份完全一致；globals 语义一致 |
| 完整回归 | 独立验证库 229 passed / 0 failed / 0 skipped，实际退出 0，含真实 Qwen，前后数据保护一致 |
| 切换后应用 | 使用原配置在 loopback 临时端口完成健康检查，数据库/Checkpoint/Store ready、agent ready；连接池关闭且无剩余异步任务 |

当前应用的 Embedding 开关沿用原配置为禁用，knowledge 不可用；上述切换后健康检查不冒称生产 RAG 通过。
真实 Qwen/PG 完整回归在独立验证库完成，耗时 356.68 秒；验证库应用启动 21.747 秒。
切换后原配置应用启动 4.783 秒。所有数值来自实际回执。

[最终独立 QA](qa/v2-01-pg1712-upgrade-final-qa-report.md)及
[独立证据](qa/v2-01-pg1712-upgrade-final-qa-evidence.json)记录了真实只读验证与未执行范围。
原业务状态中，每库 5 个订单，审批/退款/会话/Checkpoint/Store/知识表为空；
不能将空表恢复解释为已恢复非空历史审批或知识向量。

## 最终备份、执行与恢复边界

停写后的最终备份为 `/home/white7/agent-db-backups/pg176-20261117T144522Z-b66a2d363666`。
Windows 可靠副本为
`D:/AI/backups/agent-project/pg17-upgrade/20261117-pg1712-4f58c2/pg176-20261117T144522Z-b66a2d363666`。
141 个私有文件共 405,240 字节，逐文件大小/SHA、落盘和受限 ACL 检查通过；manifest SHA256：
`40db2eaf611ca4369676ab922f7b8a7fc18c55ae223f987d0853a72de23029e4`。
私有转储、globals、配置、`.env` 与原始日志未复制到仓库。
新正式配置另以受限 `production-config.private.tar.gz` 留存 VM/Windows 双份并校验，
SHA256 `92e587917ae8575d7f9e98adc4afc9023648b382159b1ffaf7d2812a64be2075`。

源维护 HBA 先拒绝新连接、确认所有数据库客户端排空，再断网；随后原 HBA 在原 inode 上恢复，
最终备份捕获原配置。三个正式脚本 QA 问题已定向修复、独立复测并主复核关闭；
本地通过范围见[第二轮复测](qa/v2-01-pg1712-formal-upgrade-script-fix2-qa-report.md)，
真实硬件断电/持续 I/O 故障没有实测，不作保证。

主 Agent 仅在该复核后启用正式入口，实际执行源码 SHA256：
`a0124fd3c480eb538fc2e597abe1f3e9834343a7573be840c3d80f4d5efb57f7`。
各正式阶段实际退出 0：SOURCE_FENCED → FINAL_BACKUP_REQUIRES_OFFSITE_VERIFICATION →
FINAL_RESTORE_VERIFIED → COMPOSE_STAGED_FOR_REVIEW → CUTOVER_MAINTENANCE_VERIFIED → WRITES_OPEN_HBA_RELOADED。
回执、精确执行源及完整回归证据见[执行证据目录](evidence/v2-01-pg1712-upgrade-evidence-20261117/)。
首轮验证库 TypeError、各轮 QA FAIL/修复记录继续保留，不覆盖历史失败。

正式 Compose 已持久更新为新项目、固定本地镜像、external 新卷/原网络；
原容器、原卷和原 Compose 备份均保留。**现已跨过开放写入边界，禁止直接切回旧库丢弃增量**；
故障时先停止新写入并保留新卷，核对增量后选择正向修复或受控反向逻辑恢复。

正式访问配置是
`/home/white7/agent-db-upgrades/20261117-pg1712-4f58c2/stage-compose-fb60e1523087/hba/pg_hba.conf`，
其父目录绑定到容器 `/etc/postgresql`，支持原子替换后 reload。
**该升级目录包含正式服务的持久配置依赖，不能当作临时目录清理。**
原部署目录的旧 `pg_hba.conf` 留给旧容器回退使用；日常维护须以当前 Compose 的实际绑定路径为准。
根盘最后实测剩余约 1.15GB，后续新索引或镜像前仍需检查峰值容量，不删除现有备份/卷腾空间。

pg_search 未在正式库启用；其 0.26.6 安全重构建/启用与 V2 完整兼容门禁留待后续裁决。
Codex 两种子角色及默认子模型已改为 Terra/high，新派发与实际 QA 均使用新角色；
见[模型配置证据](../../../.codex/terra-high-validation-evidence.json)和根 AGENTS.md。
本轮结束后停止，等待用户审核及下一项明确指令。

## 前序准备与修复记录（以下保留原交付时态，当前状态以上文为准）

用户已明确“OK，升级原库”。preflight及首次validation restore已远端执行；恢复在重命名新bootstrap容器后失败，原服务未停止或切换。
本次仅修复脚本并提供针对保留资源的resume-validation，未执行恢复或正式切换。

## 版本与范围

正式目标仅PG17.12、现有vector0.8.7（包`0.8.7-1.pgdg12+2`）。
复用已验证镜像，不联网build/apt，原shared_preload_libraries为空并保持，
不CREATE pg_search、不做BM25生产初始化。镜像中存在扩展文件不代表已启用。
pg_search0.26.6重编译/启用门禁留在后续独立裁决，不混入本次数据库升级。

[官方PGDG buildinfo](evidence/v2-01-pg1712-upgrade-evidence-20261117/pgvector.buildinfo)
记录2026-11-10构建及`postgresql-server-dev-17 (=17.12-1.pgdg12+1)`。
buildinfo SHA=`957dbce865e18973330d152f87aa59af00ee0126b985e557e44e7cc915208ffe`；
官方deb SHA=`c512035ba6fd02357092ef3204d85abe486c9aaff21686660de8645812b6d2fb`、273,432字节。
候选vector.so与官方deb同路径字节相同：
`586f3fbd75fdf71d93a6a56ac51365b48aaf015fafb19079b402deae75c01e62`。
这闭合本轮现有vector的17.12 header来源，不外推为pg_search安全构建已通过。

## 已提供的可审阶段

[upgrade_v2_01_pg1712.py](../../../scripts/upgrade_v2_01_pg1712.py)提供显式`preflight`、`restore`与针对本次中断的`resume-validation`，
复用已PASS backup helper的Snapshot/inventory/normalized_globals等只读能力，强制helper源码SHA
`72e82a48d034d75f659ddb729fea9cde8b7e404a4aa4f1d43264d62a2d7ecd1c`。
不调用演练restore，故不会添加SDK/vector/BM25夹具或开启pg_search。

- preflight：原container/挂载/网络与5432绑定、0client/prepared/slot、当前每库5订单及其他状态空，
  已核验备份141文件、现有镜像ID/平台、操作峰值容量。只观察空闲，**不将0client当作持久停写**。
- restore：使用旧已核验备份先做回归副本；新独立卷、网络、容器，包与vector.so精确核验，
  globals只跳过唯一精确bootstrap CREATE，双库restore/ANALYZE并完整比对基线与权限。
  恢复原postgresql.conf/auto.conf/ident及原启动参数，HBA原字节副本，不加host-all或额外白名单。
  只在原HBA加载后发布受控私网测试端口`192.168.150.101:56322`；原5432保持。
  输出postgres数据库comment=`pg1712-upgrade-validation:<token>`。
- 主Agent后续受控Windows launcher使用原app/test/admin凭据只在进程内替换三URL host/port，
  先验170012与唯一comment，再执行原`verify_06_delivery`真实Qwen/PG完整门禁，不改.env或原测试源码。
  当前没有执行该门禁，结果待实际回填。

私有根为`/home/white7/agent-db-upgrades/20261117-pg1712-4f58c2`，0700。
Windows副本位于`D:/AI/backups/agent-project/pg17-upgrade/20261117-pg1712-4f58c2`，仅用户/SYSTEM ACL。
日志、配置与globals SQL外置保密；失败保留新容器/卷/网络和全部备份，不prune。
原容器、原卷、演练卷`228a7f5b8d92`及镜像不改不删除，演练卷绝不作为上线卷。

## 后续显式阶段（尚未实现/执行，不得自动连续）

1. validation完整回归先在维护窗口外完成。当前可用内存2.43GiB；源0client/Task/审批/refund/Checkpoint/Store。
   根盘free约1.308GB，源卷76.8MB、演练卷83.2MB；复用image时两新卷约166.4MB，
   另计WAL/测试512MiB与操作余量256MiB，建议主审明确1GiB峰值预算，不删除原资源腾空间。
2. 主审后建立持久停写：先私密保存原inspect/network endpoint，再精确disconnect原唯一bridge，
   保留docker exec本地socket能力；核外部PG协议不可达及源无现存client，再在本地做最终一致备份。
   保存原network=`agent-engine-demo-db_default`、IP172.19.0.2与aliases postgres/原container名；
   失败按已保存endpoint精确reconnect，不能以“暂时无人请求”代替停写边界。
3. 从停写最终备份恢复**另一个全新final卷**，不使用回归卷或演练卷。ANALYZE后，
   仅在未对外发布网络中核原数据/权限/迁移checksum/原HBA和配置，严禁夹具残留。
4. 发布原5432且恢复原HBA即是写入边界，不能随后才声称“尚未开写”。
   可先用新目标私有maintenance HBA reject普通角色，仅本地管理，验证完再原子替换为原HBA并reload；
   maintenance文件不能改原HBA源文件。切换后的失败必须核实期间真实写入，不能无条件fast rollback。
5. 旧container只stop/改名保留，不rm；旧17.6绝不打开17.12写过的卷。
   无新写入且目标已断开端口/network时才可精确恢复旧容器原名、IP/alias和端口；
   已写入则先停写保留增量，按正向修复或受控反向逻辑恢复裁决。
6. VM现有compose已私密备份。持久配方应最小patch固定image、新external finalvolume，
   使用**新顶层project name**、显式原container_name、external原network与原alias/HBA/restart策略。
   不能沿用旧project去管理两个带旧Compose labels的容器，避免future compose up删除归档容器或回旧数据。
   原.env保持不变，不compose down，不删除任何卷。新阶段供主审后才写VM生产compose。

## 本地检查与停止点

只执行新脚本Ruff/format/AST检查，通过；未远端执行、未跑业务或模型测试。
首次执行的旧脚本SHA=`66e2488c4f5cf1d7e163acc6c21a2090aca09a51ac876a9a53668f7012cb448d`；
修复脚本SHA=`6306184aa8c389ba2428b607f940c64fd3ffdf64f6b8c8d116a6dc3861e29857`。
preflight/restore交主审，后续stage按真实验证结果定向补齐，不能用本文计划冒充实际切换。

## 首次恢复中断与续跑交接（2026-11-17）

首次恢复已完成双库恢复、ANALYZE和inventory/globals比对，复制源配置，停止并重命名新bootstrap后，
因源`docker inspect`私有文件是数组、代码直接按对象取`Config`而触发TypeError。旧回执
VM 原件 `validation.json`（Windows 副本名 `validation-first.json`）保持原样，SHA256为`01fee08ea6f0dc93460c76fedd2cb6be8ba78851da1382a4ed8144a09b97ce90`；
原PG容器及业务未切换。该中断过程依据主Agent交接，并非本次远端复测。

修复入口只接受该回执摘要及原preflight，核验源身份、镜像ID、带token的网络/卷/停止的bootstrap
及其卷挂载，核验保留HBA权限与源备份摘要；使用原启动参数和原HBA启动已有卷后重新核验
17.12、空preload、包/vector.so、双库完整inventory与globals及唯一数据库comment。
不重建卷、不重复导入、不删除资源；失败时保留新资源，使用新输出文件。

主Agent在VM核对脚本与回执SHA后，按实际部署路径运行（`<script>`和`<helper>`是VM上文件路径）：

```sh
python3 <script> resume-validation --helper <helper> \
  --workspace /home/white7/agent-db-upgrades/20261117-pg1712-4f58c2 \
  --backup-dir /home/white7/agent-db-backups/20261117-rehearsal-7c93e5/pg176-20261117T051950Z-6ddfec59da38 \
  --preflight /home/white7/agent-db-upgrades/20261117-pg1712-4f58c2/preflight.json \
  --receipt /home/white7/agent-db-upgrades/20261117-pg1712-4f58c2/validation.json \
  --output /home/white7/agent-db-upgrades/20261117-pg1712-4f58c2/validation-resume.json \
  --validation-port 56322
```

上述文件路径及摘要须在VM确认；本单元未连接VM、访问数据库或运行真实回归。
[本地检查证据](evidence/v2-01-pg1712-upgrade-evidence-20261117/resume-validation-local-check.md)。

## 正式阶段本地原型状态（历史，已由下节取代）

主Agent通报validation续跑真实exit 0，状态`VALIDATION_READY_NO_CUTOVER`，token `6b522e463c2b`；
完整真实回归及受信门禁以主Agent后续回执为准。本单元未连接VM核验该结果。

当前本地脚本含freeze、final-backup、final-restore和freeze回连原型，尝试关联验证门禁、
双库最终备份和Windows核验回执，并在断网前持久化恢复日志；**这些入口均已显式禁用，不得执行或上传替换已审脚本**。
正式compose准备及cutover、open-writes、开放写入前后的rollback尚未实现；HBA目录绑定、
写入边界日志、源卷保护和故障恢复需要完整实现及独立QA后才可执行。正式操作命令因此尚不可交付。
本次本地脚本SHA256 `9bd496b9080aafb37a5bb6922b449cfbd2315776a8a5005e7c4b1ac0a79a308a`；
该SHA仅标识未完成的本地原型，不取代已上传`630618...`版本。

本地项目`.venv`的Ruff check、format --check与AST parse通过；受控自检覆盖有效验证门禁及跳过项拒绝。
未执行Docker、数据库、VM、业务或模型测试。

## 正式阶段代码交接（本地待独立QA）

主Agent已报告完整真实门禁229 passed、0 failed、0 skipped，真实Qwen及保护快照通过；
`validation-gate.json`与对应validation回执已备妥。以上为主Agent回传事实，本单元没有自行连接VM重验。
原独立QA脚本SHA256 `ec595736199cc8b2341d4c542b2eed3e7a0edc61e12636c474686b4dbf7e4b1c`；
`FORMAL_EXECUTION_ENABLED=False`使所有正式操作入口在独立QA和主复核之前明确拒绝。
不要将该源码上传执行；独立QA通过后由主决定如何启用并核对最终源码摘要。

- freeze：绑定受信validation gate及回执摘要，确认源容器/网络/IP/alias/端口和身份，检查全部数据库
  的client backend、prepared transaction、slot及业务状态；持久记录后断开唯一网络，
  用PG协议探测及再次检查全部client确认围栏。不会终止未知连接。
- final-backup：调用指定SHA的原helper，围栏前后复核。Windows逐文件校验回执由主另行提供。
  final-restore核对冻结回执、helper备份回执、Windows回执及每个文件，检查当前剩余磁盘预算，
  使用新卷和internal网络恢复，保留原配置/HBA、权限和完整inventory/globals。
- stage-compose：以源Compose原始私有备份SHA为前提，生成独立新项目、固定镜像标签（复核不可变ID）、
  external最终卷与原网络/IP的私有Compose，保留原命令、重启、健康检查及初始化脚本挂载；
  原配置文件不在此阶段替换。维护HBA目录绑定到`/etc/postgresql`，只允许local trust，拒绝外部。
- cutover：在持久日志记录各步，停止final隔离容器、停原源并改名保留，校验原Compose摘要后替换，
  以新project启动原5432。核验目标身份、版本、包、vector、配置、双库inventory和globals，
  以PG启动包确认维护HBA拒绝外部连接。不得删除旧容器/卷。
- open-writes：再次核验维护状态，先在绑定目录持久创建`writes-opened.journal`，然后在该目录
  原子替换HBA、核容器内摘要并reload，检查载入时间及配置解析。标记一旦存在，即使后续失败，
  rollback-cutover也会拒绝自动切回；stop-open-target只停止目标并保留增量供人工核对。
- rollback-freeze用于仅断网阶段；rollback-cutover用于维护态或中断后的写入边界之前，
  先停/改名保留目标，再恢复旧容器名、原Compose、IP和alias，检查PG17.6。
  所有阶段持锁串行，各自使用新回执；失败不清除资源。

正式入口启用并通过复核后，主Agent可据实际部署路径逐条执行以下命令；每条先检查上一回执，
不得作为无条件连续脚本。`<...>`须由主替换，备份传输及验证为独立人工门禁：

```sh
upgrade_script=<VM已审脚本绝对路径>
backup_helper=<VM已批准helper绝对路径>
upgrade_root=/home/white7/agent-db-upgrades/20261117-pg1712-4f58c2
source_backup=/home/white7/agent-db-backups/20261117-rehearsal-7c93e5/pg176-20261117T051950Z-6ddfec59da38
# freeze：validation-gate.json 必须先由主完成真实回归后生成并核验
sudo python3 "$upgrade_script" freeze --helper "$backup_helper" --workspace "$upgrade_root" --backup-dir "$source_backup" --preflight "$upgrade_root/preflight.json" --validation-gate "$upgrade_root/validation-gate.json" --validation-receipt "$upgrade_root/validation-resume.json" --output "$upgrade_root/freeze.json"
sudo python3 "$upgrade_script" final-backup --helper "$backup_helper" --workspace "$upgrade_root" --backup-dir /home/white7/agent-db-backups --preflight "$upgrade_root/preflight.json" --receipt "$upgrade_root/freeze.json" --output "$upgrade_root/final-backup.json"
# 主将新备份逐文件传至Windows并核验，生成并上传 final-backup-windows-receipt.json
final_backup=<final-backup.json中的backup_directory>
sudo python3 "$upgrade_script" final-restore --helper "$backup_helper" --workspace "$upgrade_root" --backup-dir "$final_backup" --preflight "$upgrade_root/preflight.json" --receipt "$upgrade_root/freeze.json" --backup-receipt "$upgrade_root/final-backup.json" --windows-receipt "$upgrade_root/final-backup-windows-receipt.json" --minimum-free-bytes <当前最终卷和WAL的剩余峰值预算字节数> --output "$upgrade_root/final-restore.json"
sudo python3 "$upgrade_script" stage-compose --helper "$backup_helper" --workspace "$upgrade_root" --backup-dir "$final_backup" --preflight "$upgrade_root/preflight.json" --final-receipt "$upgrade_root/final-restore.json" --compose-backup "$upgrade_root/compose.original.private.yaml" --output "$upgrade_root/stage-compose.json"
# 主审私有 staged compose、资源和回执后才进入下一步
sudo python3 "$upgrade_script" cutover --helper "$backup_helper" --workspace "$upgrade_root" --backup-dir "$final_backup" --preflight "$upgrade_root/preflight.json" --final-receipt "$upgrade_root/final-restore.json" --stage-receipt "$upgrade_root/stage-compose.json" --output "$upgrade_root/cutover.json"
sudo python3 "$upgrade_script" open-writes --helper "$backup_helper" --workspace "$upgrade_root" --backup-dir "$final_backup" --preflight "$upgrade_root/preflight.json" --final-receipt "$upgrade_root/final-restore.json" --stage-receipt "$upgrade_root/stage-compose.json" --cutover-receipt "$upgrade_root/cutover.json" --output "$upgrade_root/open-writes.json"
```

若freeze后、cutover前需恢复源网络，使用同样helper/workspace/backup-dir/preflight参数，
执行`rollback-freeze --receipt "$upgrade_root/freeze.json" --output "$upgrade_root/rollback-freeze.json"`。
若cutover期间或维护态需回滚，使用final backup目录、preflight、final-receipt、stage-receipt和
cutover-receipt，执行`rollback-cutover --output "$upgrade_root/rollback-cutover.json"`。
开放写入标记已存在时，使用final backup目录、preflight、final-receipt及stage-receipt，
执行`stop-open-target --output "$upgrade_root/stop-open-target.json"`并人工核对增量；不能自动切回旧库。
实际命令、资源与失败恢复路径仍须独立QA及主复核，以上不是已执行证据。

本地项目`.venv` Ruff check/format --check、AST parse通过；受控替身检查了全部client阻断、
Compose转换与解析契约、HBA写入标记先于替换及标记存在时禁止回滚。未访问Docker/VM/数据库，
未在本单元运行真实业务或模型测试。

[PostgreSQL 17 官方文档](https://www.postgresql.org/docs/17/view-pg-hba-file-rules.html)确认`rule_number`列及该视图检查当前磁盘文件；脚本另外检查reload时间，并不将视图本身当作已生效证明。

## FORMAL-QA-001 / 002 定向修复（待原QA复测）

修复脚本SHA256 `27959a572af32bbfefa3a707ddbdcbe4ff4151ba8e5ff78d57f2d58f2f8900ba`，
`FORMAL_EXECUTION_ENABLED`继续为`False`。原QA报告及旧脚本证据保持。

- FORMAL-QA-001：写入边界journal为false、目标维护HBA文件为预期内容且无写入标记时，
  根据真实inspect的目标ID、镜像、标签、最终卷和只读HBA目录绑定核验目标，
  停止并保留目标后恢复源；不以目标PostgreSQL SQL就绪作为停止目标的条件。
  持久写入标记存在时仍拒绝自动回滚，写后只能停目标并人工核对。
- FORMAL-QA-002：源原HBA绑定文件先保存原始字节、摘要、inode、设备、权限及属主并持久写journal；
  在同一inode原位写入仅本地连接、拒绝所有host的维护HBA，fsync、reload并核验PG规则及host连接拒绝。
  再检查全部数据库client及业务状态；有存量client或状态不明则恢复HBA并中止，不断网或终止连接。
  排空后才断开原网络，在仍断网时原位恢复原HBA并reload，然后复核源配置、角色和数据；
  最终备份后复核源完整inventory与备份一致。rollback-freeze支持已连接及已断网两种状态，
  均先恢复原HBA；文件内容既非原字节也非维护HBA时拒绝覆盖。

[本地受控复现证据](evidence/v2-01-pg1712-upgrade-evidence-20261117/formal-qa-001-002-fix-local.md)。
这些结果尚需原独立QA复测；未执行VM、Docker、PostgreSQL或业务测试。

## FORMAL-QA-003 定向修复（待原QA复测）

修复脚本SHA256 `70363c4b806ee410ab3466c76396eef8fa0f28ae4b50a25ac0cc053612708c25`；
正式执行开关继续为`False`。本条仅覆盖源HBA同inode部分写入的恢复，
原QA报告和前次证据保持不变。

每次原位写入前，脚本将当前字节和目标字节分别保存为私有快照并fsync，
随后持久发布含设备、inode、快照路径、SHA及pending阶段的write-intent。
写入采用短写循环，全部目标字节写完后才truncate并fsync，再记录completed。
恢复时仅在设备/inode与意图匹配，且当前内容可由该意图的顺序覆盖前缀、原后缀
或完成截断产生时接受；恢复写入本身也先保存新快照和意图，故再次中断可按新意图恢复。
记录之外的字节或不同inode仍拒绝覆盖；持续硬件I/O故障需人工处理。
合法中间态的字节与外部恰好写成相同字节的情况无法仅靠文件内容区分。

[本地受控证据](evidence/v2-01-pg1712-upgrade-evidence-20261117/formal-qa-003-fix-local.md)。
原QA尚未复测；未连接VM、Docker、PostgreSQL或运行业务/模型测试。
