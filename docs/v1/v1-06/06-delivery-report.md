# Task6.3.2 最终交付与干净环境复现

2026-11-15。范围仅最终交付材料、必要固定数据库配方与显式验证入口；不修改业务实现、冻结设计、迁移、角色或原.env。前五Task已独立QA PASS/主复核VERIFIED；本Task完成后交独立QA和主复核，**不代表06 ACCEPTED或Git归档授权**。

## 交付文件

| 文件 | 职责 |
| --- | --- |
| [README](../../../README.md) | 当前状态入口、架构、独立Python安装、初始化顺序、启动/关闭/重启、HTTP/SSE及恢复边界；旧轮次记录保留 |
| [.env.example](../../../.env.example) | 本地Embedding与Chat SDK边界、显式初始化、单实例CPU、V1审批无管理Key |
| [数据库复现](database-reproduction.md) / [Dockerfile](../../../deploy/postgres-vector.Dockerfile) | 原vanilla Compose无vector的事实、PGDG三包固定版本、新隔离资源及初始化配方，不改原卷 |
| [演示操作](demo-walkthrough.md) | 用户已确认导入；客户端脚本/回填/SSE未实测准确保留 |
| [最终验收入口](final-acceptance.md) / [Handoff](06-integration-handoff.md) | 按能力/责任Task/实现/自动/真实/环境/遗留分列；G5用户验收单独待填 |
| [显式交付门禁](../../../scripts/verify_06_delivery.py) | 新解释器全pytest、真实Qwen开关、新JSON、Settings安全注入测试URL、全public前后保护及真实Uvicorn启动/优雅关闭 |

requirements.in/txt沿已验证固定清单，无升级、删除或改解析版本。openai/langchain-openai保留为Chat兼容SDK。本轮新增的是交付验证脚本，不新增业务抽象或框架。

## 环境与证据归因

Windows Python3.13.7，独立`.venv-delivery632-20261115`，不启用system-site-packages、不覆盖原.venv、不复制site-packages。锁定CPU torch2.9.1+cpu / sentence-transformers5.1.2 / transformers4.57.6。原模型目录`D:/AI/models/qwen3-embedding-0.6b`，revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，CPU/bfloat16/2线程/单worker、输入上限1024/输出1024维、batch=1。未另启并行Qwen。

数据库原Ubuntu VM、PG17.6/vector0.8.7，test仅agent_demo_test/agent_test。编号schema001～006及在线checksum、Saver/Store框架表沿原版本；Web启动无DDL/seed。原.env默认Embedding关闭，验证只在进程配置中启用。真实Chat沿前序DeepSeek deepseek-flash，网关function_calling/reasoning_effort=none；本轮不重复付费Chat，不报告新增费用/Token测量。

真实五能力复用未变实现的[631三段与清理](06-demo-delivery-report.md)、[611真实英语偏好知识问答](evidence/06-assembly-real-evidence-20261114-r5.json)及对应前序独立QA。631初始FAIL与06-QA-001修复/独立复测证据原样留存，已由主Agent关闭；本轮完整门禁包含该新真实回归。Node受控执行、真实HTTP、用户导入截图三个证据层分别记录，不相互替代。

## 实际验证

全部命令从仓库根目录执行。首次独立环境创建与安装：

```powershell
.\.venv\Scripts\python.exe -m venv .venv-delivery632-20261115
.\.venv-delivery632-20261115\Scripts\python.exe -m pip install -r requirements.txt --disable-pip-version-check
.\.venv-delivery632-20261115\Scripts\python.exe -m pip check
.\.venv-delivery632-20261115\Scripts\python.exe -m ruff check app scripts tests
.\.venv-delivery632-20261115\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv-delivery632-20261115\Scripts\python.exe -m scripts.verify_06_delivery --output docs/v1/v1-06/evidence/06-delivery-clean-gate-evidence-20261115.json --qwen-evidence docs/v1/v1-06/evidence/06-delivery-qwen-regression-evidence-20261115.json
```

- 安装成功，90个锁定分发版本全部逐一匹配，`include-system-site-packages=false`、Python3.13.7。实际安装日志区间966.304秒；CPU torch官方wheel下载曾timeout/TLS EOF，pip断点恢复后成功，未改源/版本或绕过TLS。pip check：No broken requirements found。见[安装证据](evidence/06-delivery-install-evidence-20261115.json)，原始日志留本机Temp，仓库保留其SHA256和脱敏结果。
- 新解释器Ruff app/scripts/tests通过，155文件格式通过。
- 全套pytest `-q`：**228 passed / 0 failed / 0 skipped**，终端221.98秒，wrapper包括pytest初始化为223.135秒。真实Qwen开关、新JSON和测试URL由验证器在进程内设置；不传skip/deselect。仅两条anyio/langsmith已预导入导致的PytestAssertRewriteWarning，不影响测试结果。见[完整门禁及资源证据](evidence/06-delivery-clean-gate-evidence-20261115.json)。
- 新增真实测试实际执行原CLI首次prepare、重复目录拒绝和真实Qwen/PG提交后受控异常，完整数据/文件字节保持及精确清理通过，非付费Chat。[本轮新真实回归](evidence/06-delivery-qwen-regression-evidence-20261115.json)与原Implementer/QA JSON路径独立。
- 同一新解释器随后用正式`create_app`和真实Uvicorn在127.0.0.1:8632启动单worker，原test库、进程内启用Qwen；实际HTTP `/health`全部资源就绪（25.111秒）。model=initialized仍只表示SDK初始化，本步未调用Chat。服务按`should_exit`优雅关闭，两个池closed、async tasks=[]、Qwen线程=[]。本轮验证PID22288已退出、8632无监听，不停止其他进程。
- 完整门禁与启动前后原13张public表**完整行集和列定义相等**，001～006在线checksum每次快照核对成功；固定五订单和原Saver/Store保持。全套中的原seed幂等唯一窄例外原样执行并finally恢复实际原值，无新增场景seed。

本轮Windows验证器PID22288在14:48:53采样WorkingSet531132416字节、OS当时报告PeakWorkingSet616673280字节；只是该采样时点/该进程的观察，不代表全部子进程总内存或最终完整峰值。Qwen真实回归子进程未采集完整内存峰值，不编造数值。原始采样及最终文件审计见[脱敏审计](evidence/06-delivery-final-audit-20261115.json)：86份原.env/SQL/角色/冻结设计/旧JSON/依赖文件摘要未变，新文件相对链接和真实原/临时凭据精确扫描通过。

隔离数据库资源由主Agent执行授权SSH操作，Implementer未SSH或操作原容器：[首轮资源探针失败](evidence/06-database-reproduction-evidence-20261115-r1.json)发生于build前（可选Mount.Name字段假设），修正探针后[真实构建证据](evidence/06-database-reproduction-evidence-20261115-r2.json)通过。相同Dockerfile在原固定PG17.6镜像实际构建144.412秒，三包固定版本/PG17.6/vector0.8.7及1024维余弦运算成功；新container/image/volume独立，原container ID/状态/镜像/全部Mounts保持，原库未重启。

新资源交接后，实际命令为`.venv-delivery632-20261115/Scripts/python.exe .venv-delivery632-20261115/verify_fresh.py <本机临时凭据JSON> docs/v1/v1-06/evidence/06-delivery-fresh-database-evidence-20261115.json`。路径中的尖括号是脱敏占位；真实URL只进程读取后封装SecretStr，不输出。临时验证源留本机独立venv，SHA256记录在最终审计，实际调用均复用现有`apply_migrations/setup_checkpoint/setup_store/create_app`入口。

[新空双库应用初始化证据](evidence/06-delivery-fresh-database-evidence-20261115.json)：11.613秒，development/agent_app与test/agent_test均从public空表开始，001～006实际首次应用，重跑返回[]；Saver与Store分别连续两次setup成功，正式应用lifespan资源agent/database/checkpoint/store就绪，Embedding disabled、订单0、两个池closed。未seed/导入固定语料/调用Chat/加载第二个Qwen，也未对新空库运行旧全套订单用例；这些新资源上的五能力业务演示没有重复执行。实际完整门禁和Qwen启动在原隔离test库完成，五能力真实调用按上文前序出处复用。

本轮新库探针PID36164正常退出、全部连接关闭后，主Agent已[独立SQL核对并精确清理](evidence/06-database-reproduction-cleanup-evidence-20261115.json)，结果PASS：两库13表、001～006 checksum、控制表6/10/4行、业务0行、vector1024及其他连接0确认；新container/volume/image、VM临时env与本机秘密JSON全部删除，原容器/镜像/挂载结构保持，StartedAt早于本轮验证（未重启）。[清理首轮回执](evidence/06-database-reproduction-cleanup-evidence-20261115-r1.json)保留：实际删除已完成，末尾原Mounts列表返回顺序改变导致字符串断言失败；最终按规范化结构比较相同，未据此重做删除或改变原资源。Implementer未自行操作VM。新Python环境与本机脱敏验证日志留存供独立QA，不影响原.venv。

## 保留项和停止边界

用户已确认手动导入Postman六组26请求/12变量；客户端后置脚本真实执行、变量实际回填及SSE界面未实测，人工复制原关联步骤可用；本轮无GUI操作。完整新数据库重建与Python新环境分别记录，静态配方不替代实际构建和初始化。

Store历史即时关闭观测波动原因未定，后续完整行集核对通过不等于已定因；unknown原操作/可信Checkpoint核对及拒绝自动重放的边界保留。V1无生产认证、真实支付、分布式执行、持久事件重放、ES/Hybrid或Memory V2。

原五订单及其他用户数据保护；完整回归只保留已批准的旧seed幂等测试窄例外，原样执行并finally恢复实际原值，无skip/deselect、无扩大例外。所有新场景UUID精确清理，完整原行集快照留本机，仓库只放脱敏指纹。六项暂缓差异/凭据与格式遗留保持，无Git/Bridge/SSH/容器重启/用户进程操作或下一阶段行为。VM独立资源工作由主Agent执行并单独归因。
