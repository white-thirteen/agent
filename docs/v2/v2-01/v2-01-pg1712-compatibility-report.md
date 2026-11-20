# PG17.12 / pg_search0.26.6 隔离兼容排查

2026-11-17。用户本轮仅授权兼容排查：原PG17.6不得升级、重启、替换或修改，
不进入V2 01 Task1.1.2，不修改业务代码、配置、迁移或冻结设计。
上一轮[PG17.6加载失败证据](evidence/v2-01-01-compatibility-evidence-20261117.json)保持原样。

**结论：精确隔离组合的加载与最小功能实测通过，独立QA PASS（仅本次有限排查）。**
PG17.12 / pgvector0.8.7 `+2` / pg_search0.26.6真实预加载、建扩展、中文BM25、
事务更新/回滚/提交和重启恢复通过；原PG17.6保护检查通过。
这不关闭原PG17.6兼容阻塞，不批准原库升级，不进入1.1.2，也不代表V2 01阶段验收。

主Agent在授权VM只读检查：原4容器healthy，根盘可用2.9GB，RAM3350MB、available1918MB，
宿主机readelf已存在。首次manifest读取遇DockerHub子manifest EOF、Windows auth端点TLS超时；
这两项仅是网络失败，未解释为版本不兼容。
随后一次有300秒上限、限定linux/amd64的精确17.12-bookworm拉取成功，实际inspect结果：

- 基础镜像：`postgres:17.12-bookworm@sha256:40865bc877a289da75963d97d72b59633f639fc5af7a4e856bfa3714cae5b536`。
- 平台：linux/amd64；本轮新增基础镜像，由主Agent最终按精确身份清理。
- 实际服务器/客户端包：`17.12-1.pgdg12+1`。
- pgvector隔离apt-cache预检exit0，精确包：`0.8.7-1.pgdg12+2`。
  相对原`+1`包有二进制变更，SQL扩展版本仍为0.8.7，不声称二进制保持不变。

主Agent补充原库只读升级库存：两库均仅plpgsql1.0、vector0.8.7；public各30个索引，
access method均为btree；shared_preload_libraries均为空，原库没有pg_search。
该库存不排除所有REINDEX要求，仍需结合opclass、数据类型、TOAST及累积发行说明逐项判断。
未来给原库加入pg_search预加载并重启属于另行授权动作，本轮没有更改。

本地首次重新下载官方pg_search包返回11,911,168字节，少于已知资产54,276,840字节；
SHA256为`d12fa166cad9f864f32b81c5a9f210815f4d2401ee20c51330e33f598dc4cfbb`，
校验拒绝，未上传或安装，失败文件已精确删除。
[下载失败证据](evidence/v2-01-pg1712-download-evidence-20261117.json)独立保留；这不是版本兼容结论，
未以不完整包继续探针。
随后主Agent在VM对同一官方URL执行有时限、有限重试的网络恢复下载，
实际一次成功取得54,276,840字节，SHA256与官方16a14d...摘要一致，才开始隔离探针。
本轮不更换包来源/版本；先前Windows截断失败记录保留。

本轮实际ELF证据：

- 原PG17.6实际运行exe的只读复制哈希与`/proc/<postmaster>/exe`一致：
  `5a7c97038091358d2e41449f136a4d06f06be14a8ed403562ee0a0ee6d5e9786`；
  动态符号表没有`pg_mblen_cstr`导出。
- 固定包内pg_search.so SHA256：
  `e3b19a5d350efc27d3c9b23587f68004eee5d2468b96dc88422b73ad4432a598`；
  readelf明确记录`GLOBAL DEFAULT UND pg_mblen_cstr`。
- PG17.12实际运行exe与从候选镜像复制的exe哈希一致：
  `5a497342435d67f84119f5de3ea7d5efe97a07ebca766505abebe6caa008be36`；
  动态符号表将pg_mblen_cstr记录为已定义的`GLOBAL FUNC`。

上述证据与上一轮PG17.6真实预加载缺符号失败吻合，也直接核对了候选实际运行二进制。

## 真实运行与可追溯证据

主Agent通过已授权SSH执行，探针UTC起止为2026-11-17 04:18:45～04:29:05。
实际观测为最终JSON状态ISOLATED_COMBINATION_PASSED、保护/清理检查均true及run.log正常完成。
源码成功分支返回0，但父Launcher通过Popen后台启动，未单独采集进程最终退出码；
不把源码返回值推断作为实测退出码，也不为补退出码重新执行。
实际命令的非秘密参数见[launch.json](evidence/v2-01-pg1712-evidence-20261117/launch.json)：

```bash
python3 /tmp/agent-pg1712-compat-aYhgTD/verify_v2_01_pg1712_compatibility.py \
  --base-image postgres:17.12-bookworm@sha256:40865bc877a289da75963d97d72b59633f639fc5af7a4e856bfa3714cae5b536 \
  --pg-package 17.12-1.pgdg12+1 --vector-package 0.8.7-1.pgdg12+2 \
  --package /tmp/agent-pg1712-compat-aYhgTD/pg_search.deb \
  --output /tmp/agent-pg1712-compat-aYhgTD/compatibility-evidence.json
```

[机器JSON](evidence/v2-01-pg1712-compatibility-evidence-20261117.json)记录
`status=ISOLATED_COMBINATION_PASSED`，运行版本170012 / pg_search0.26.6 / vector0.8.7。
实际候选镜像ID为`sha256:b413cd38dd061c627d042910904ee835e30d87ed676749d050b7e7589c763f07`，linux/amd64。
Jieba中文“退款”命中Unicode文本Chunk ID；EXPLAIN JSON记录`ParadeDB Base Scan`与`compat_bm25`索引。
事务内更新可见、回滚后原词恢复且新词消失、提交后新词可见且原词消失，全部核对通过。
同一独立卷重启后“物流”仍命中同一Chunk ID；postmaster启动时间
从04:27:42.985833+00变为04:28:16.542359+00，确认实际重启。

[实际执行源](evidence/v2-01-pg1712-evidence-20261117/verify_v2_01_pg1712_compatibility.py)
SHA256=`2b6b10e0fdb813e2a170e5bfad2faa9e427d5000be2a97cb698c6fd14dc4345a`，
与机器JSON及工作区探针一致。
[构建日志](evidence/v2-01-pg1712-evidence-20261117/build-6e6bcd7a4608.txt)
SHA256=`557345d4c6aa1c53e35de9f6e3b2ddc614eb694ae0b271a19f7be804ed6c6500`，已复核。
平台/包/网络失败与恢复/原库升级库存分别保存在同目录的
[base-preflight](evidence/v2-01-pg1712-evidence-20261117/base-preflight.json)、
[pull日志](evidence/v2-01-pg1712-evidence-20261117/base-pull.txt)、
[apt预检](evidence/v2-01-pg1712-evidence-20261117/apt-preflight.txt)、
[下载校验](evidence/v2-01-pg1712-evidence-20261117/download-evidence.json)、
[原库升级库存](evidence/v2-01-pg1712-evidence-20261117/upgrade-inventory.json)。
最初失败的base-manifest.json为空文件，保留失败痕迹，不用它证明摘要。

原实例两库全部public行摘要、列定义、精确包、实际exe、启动时间及容器/卷信息前后一致
（protected_unchanged=true）。本token `6e6bcd7a4608`的候选容器、工具容器、卷和镜像层清理后查询为空，
cleanup_complete=true，脚本自有构建目录已删除。
cleanup_errors有一次删除旧中间image ID返回“No such image”，因前一个image删除已级联删除其无标签父层；
最终三类标签查询均为空，未执行prune或删除原资源。

主Agent已按准确tag/sha删除本轮新增PG17.12基础镜像，
[补充清理回执](evidence/v2-01-pg1712-evidence-20261117/main-cleanup.json)记录remove_exit=0、base_absent=true，
原容器ID/启动时间/running状态保持，剩原5个镜像。
该动作不包含在probe的cleanup_complete范围，回执独立保留，不覆盖机器JSON。
外层传输目录初次交付时为QA保留；QA后主Agent核对绝对目标及唯一14文件集合后精确删除，见[传输清理回执](evidence/v2-01-pg1712-evidence-20261117/transfer-cleanup.json)。本地日志以字节不变的.txt保存，映射和哈希见[archive-map](evidence/v2-01-pg1712-evidence-20261117/archive-map.json)，原机器JSON保持不变。

## 探针与隔离边界

[独立探针](../../../scripts/verify_v2_01_pg1712_compatibility.py)只验证一个精确版本组合：
PG17.12 Bookworm/amd64 digest、对应服务器/客户端精确包、pgvector0.8.7精确包、
官方pg_search0.26.6预编译包。所有固定参数与探针源摘要写入机器证据。
pg_search包SHA256固定为
`16a14d382f088bc23e7c8624e4860fd8bf01a939c67c7695348de0615e323ddb`。

原实例仅执行只读版本、实际postmaster executable路径/版本/哈希，以及两库全部public行摘要和列定义查询。
只读复制实际exe并核对哈希，再用VM上的readelf检查动态符号；不在原容器安装工具。
pg_search包在自有目录解包检查UND符号，解包内容在构建前精确删除以控制磁盘占用。

候选使用独立标签/容器/卷、无网络、无主机端口；构建和运行限制为768MiB/1CPU。
构建采用首LABEL与legacy builder，日志实时写入证据目录。
命令90秒、构建1200秒、启动60秒期限可显式调整，失败保存阶段和日志，不无限重试。
finally精确清理本token容器、卷和镜像层；不执行prune，不删除原资源或其他镜像。
固定基础镜像及传输证据目录若本轮新增，由主Agent核对身份后另行精确清理，并单独记账。

检查范围为实际ELF符号、真实预加载/CREATE EXTENSION、text Chunk ID的中文BM25、
事务内更新与回滚、提交后可见性、独立容器重启后的持久检索。
不运行Qwen/BGE或业务回归，不称这些少量检查已完成V2 01完整语义/质量门禁。

## 本地验证

只使用项目`.venv`运行探针Ruff、格式及AST语法检查，通过；未运行原项目回归。
AST首条临时检查命令因Windows默认GBK读取UTF-8源码失败，改为显式`encoding='utf-8'`后通过；
未修改探针逻辑以绕过检查。

```powershell
.\.venv\Scripts\python.exe -m ruff check scripts/verify_v2_01_pg1712_compatibility.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/verify_v2_01_pg1712_compatibility.py
.\.venv\Scripts\python.exe -c "import ast,pathlib;ast.parse(pathlib.Path('scripts/verify_v2_01_pg1712_compatibility.py').read_text(encoding='utf-8'));print('syntax OK')"
```

## 升级影响与回滚建议（只提交建议，未执行）

若隔离组合通过，仍须独立QA复核，再由用户另行批准原库维护与升级；
不能据此关闭原PG17.6门禁或继续1.1.2。

实施前应核对全部服务器扩展、应用普通角色、pg_hba、Saver/Store、迁移checksum及原向量/来源身份，
冻结维护窗口并停止写入，保留原容器、原固定镜像与原卷，不能原地覆盖唯一副本。
Saver/Store保留原锁定库版本及原表数据，逐项核对Checkpoint ID、namespace、pending审批、
operation与revision，不运行setup、不改迁移来冒充升级兼容；迁移001～006及checksum保持。
先完成双库逻辑备份、角色/权限备份、配置和包清单，以及经一致性停库或数据库备份协议取得的物理副本；
普通运行中的数据目录文件复制不能充当一致备份。备份需有恢复演练及完整性证据。
建议将备份保存到Windows或独立介质，再使用另一个新卷做恢复演练；本轮未执行这些动作。
VM仅2.9GB可用，不能在原卷上覆盖唯一副本或把空间不足转化为删除原资源的理由。

PG17.6→17.12属于同主版本更新，但会包含17.7～17.12全部行为/安全修正，不能把修复单个符号当作完整升级评估。
主Agent官方资料核对定位到2026-02-09多字节边界检查补丁与CVE-2026-2006，
[17.8发行说明](https://www.postgresql.org/docs/release/17.8/)包含该修复；
固定标签REL_17_6的mbutils.c没有pg_mblen_cstr，REL_17_8与REL_17_12存在。
[补丁邮件](https://www.postgresql.org/message-id/E1vpEoc-001x3U-14@gemulon.postgresql.org)
属于REL_16_STABLE，只作为同一修复背景，不冒充17分支精确commit。

依[17.12官方发行说明](https://www.postgresql.org/docs/release/17.12/)，同17.X更新通常不需dump/restore，
但仍需检查受影响索引的REINDEX要求、已有增量备份的可信性限制并取得新的完整备份；
还须逐项核对[17.11说明](https://www.postgresql.org/docs/release/17.11/)及其余累积变更。
CVE-2026-6460的完整保护要求重编译C扩展，部分扩展可能需要源码适配。
本轮候选pg_search0.26.6官方资产发布时间为11月8日，早于17.12的11月12日发布，
因此即使本轮加载和最小检索成功，也不能宣称该预编译包满足全部17.12扩展安全重编译要求。
本轮不编译扩展；此项须作为真实升级前的独立阻塞/决策风险保留。

pgvector若从原0.8.7 `+1`改为适配17.12的`+2`，扩展版本号不变仍存在包二进制变化，需单列哈希与真实检索验证。
pg_search需要预加载和重启；这些都须作为原库另行授权的配置/维护动作。

回滚应优先保留原PG17.6容器/镜像和未被新版本写入的备份卷。
切换前用隔离恢复副本核对两库全部权威数据、知识向量/Profile、来源身份、Checkpoint和Store；
允许业务写入前，可停止候选后切回保留原实例；
若新库已接收写入，必须先停止受理并核对期间退款、记忆及Checkpoint等增量，
评估写入恢复后再裁决回滚，不可静默切回丢弃已受理业务。
不建议直接把被新扩展或新包写过的唯一卷交给旧服务器并声称可安全降级。

## 未验证与当前停止点

本轮没有验证Qwen真实向量检索、两路过滤/Top K/同快照、Hybrid/BGE、真实知识质量、
原项目完整回归、真实备份恢复、原实例升级或CVE-2026-6460全部安全保护。
仅证明上述精确组合的真实加载与最小BM25行为，不把其余范围推导为通过。
本次有限排查已独立QA PASS并经[主复核](v2-01-pg1712-main-review.md)；完成后停止。原库升级、配置变更与后续开发仍须另行授权，不关闭原PG17.6阻塞。
