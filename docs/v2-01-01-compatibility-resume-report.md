# V2 01 / Task 1.1.1 续作记录

2026-11-17。任务仍为 **BLOCKED**：固定 pg_search 二进制的 PostgreSQL 17.12
安全构建门禁未闭环。正式数据库已升级至 PG17.12 / vector 0.8.7（包 +2）；
本记录不改变此前 PG17.6 二进制不兼容的历史证据，也不授权 1.1.2。

## 扩展构建来源及安全门禁

- [固定官方发布资产](https://github.com/paradedb/paradedb/releases/expanded_assets/v0.26.6)
  中 Bookworm/amd64 PG17 包的 SHA256 为 `16a14d382f088bc23e7c8624e4860fd8bf01a939c67c7695348de0615e323ddb`，
  资产时间 2026-11-08 22:43:20 UTC；原始包实际摘要与其一致，见
  [此前证据](v2-01-01-compatibility-evidence-20261117.json)。
  17.12 正式发布日期为 11 月 12 日；日期本身不能排除预发布修复头文件。
  本轮未找到该包可核验的编译 headers/buildinfo，不能据日期推定具体 headers。
- [PG17.12 发行说明](https://www.postgresql.org/docs/release/17.12/)
  指出 composite datum 安全修复的完整保护要求重建 C 扩展，某些扩展还需源码修改。
  PostgreSQL [CVE-2026-6460 修复提交说明](https://www.postgresql.org/message-id/E1xQQFr-000000003OT-3txh%40gemulon.postgresql.org)
  特别指出 pgrx 复制部分 PostgreSQL 代码，单纯重编译不足；这是 master 提交，说明标注回补至 14。
- [pg_search v0.26.6 固定源码](https://github.com/paradedb/paradedb/blob/v0.26.6/pg_search/Cargo.toml)
  使用 workspace 的 pgrx；[根 Cargo.toml](https://github.com/paradedb/paradedb/blob/v0.26.6/Cargo.toml)
  将其固定为 `=0.19.3`。pgrx [0.19.4 安全发布说明](https://github.com/pgcentralfoundation/pgrx/releases/tag/v0.19.4)
  说明需要使用 0.19.4 和含修复的 PostgreSQL headers 重建，检查只在相关头文件下编入，
  此产物不能加载更早的小版本。

因此固定源码按原依赖原样重编译不能作为上述完整保护的证明；需要受信构建来源、
pgrx 修复依赖与 headers 的可追溯证据，以及固定 pg_search 的构建和兼容验证。
这不是已证明当前业务调用可利用该漏洞，也不是所有其他保护均失效的结论。
本轮未发现固定包对应的厂商安全重构建证明，未修改依赖、未编译或启用正式扩展。
不将旧包在隔离环境可加载或业务语义通过解释为安全构建通过。

## 契约及本地验证

复核现有 `SparseIndexProfile`、`RetrievalProfile`、候选来源及 V1/V2 结果契约，
保留此前未激活实现和[契约及回填/回滚记录](v2-01-01-compatibility-report.md)，本轮未修改模型。
使用项目 `.venv` 执行 `python -m pytest tests/test_knowledge.py -q`，退出 0，
7 passed；这是受控契约/原知识行为测试，不是数据库或真实模型测试。

新增 [隔离续测入口](../scripts/verify_v2_01_pg1712_semantics_resume.py)，复用
[现有语义探针](../scripts/verify_v2_01_compatibility.py)；入口不构建或拉取镜像，
以固定镜像 ID 新建无网络隔离容器及专用卷，检查版本和此前旧包二进制 SHA，
限制资源并用独立标签精确清理；输出文件独占创建。其功能结果与构建安全门禁分开。
本地 `.venv` Ruff check、format check 通过；对已存在输出路径的拒绝测试通过，
这些检查不构成真实隔离数据库测试。

## 真实隔离语义

主 Agent 在授权 VM 执行下列命令，实际观察退出码 0：

```sh
sudo -n python3 /home/white7/v201-111-resume-20261117-815c/verify_v2_01_pg1712_semantics_resume.py \
  --image sha256:bfe9a33d715a56d441d60a34e48c68b93fb49ea83d0992fbc2c2819e26846af4 \
  --minimum-free-bytes 805306368 \
  --output /home/white7/v201-111-resume-20261117-815c/semantic-evidence.json
```

[机器回执](v2-01-01-resume-evidence-20261117/semantic-evidence.json) SHA256 为
`125f95f5d350bbd17471ea8817b6a865992283018a12caab384b3e87119777bc`，
本地取回与远端一致。执行时[续测入口](v2-01-01-resume-evidence-20261117/verify_v2_01_pg1712_semantics_resume.py)
SHA256 `7a4f7ede10b433879479a9c4e502139a36e666a52513b99cb899c2d88099b750`，
[复用语义源码](v2-01-01-resume-evidence-20261117/verify_v2_01_compatibility.py)
SHA256 `bc9fbc05b2b15ac1aff00da41c29f44dbf4e24e3c7825cc5e799f3bc9d9b96d1`。
镜像已存在，不构建或下载；Docker 所在文件系统启动前可用 1,150,488,576 字节，
检查门槛 805,306,368 字节。使用独立卷、无网络和端口、768 MiB / 1 CPU 限制。

回执记录 `FUNCTIONAL_PASSED_SAFETY_UNVERIFIED`：PG运行版本 170012、vector 0.8.7、
pg_search 0.26.6 及旧包 `.so` 摘要核验；Jieba 中文、英文标识、text Chunk ID、
domain 与当前版本过滤先于 Top 1、查询参数化、更新/删除回滚、提交删除和替换、
REPEATABLE READ 中 Dense/Sparse 同一来源快照与最终来源失效均通过。未过滤 Top 1
为 `deny-1`，证明夹具中存在过滤前更高结果。隔离容器重启前后时间分别为
15:33:28.057595 和 15:34:38.630849 UTC，Dense/Sparse 均保留 `restart-text-id`。
首次启动就绪检查有 6 次 exit 2，随后就绪；不将其记作命令失败后的隐瞒。
本 token 的容器及卷清理核验通过。功能测试是合成小型语料，不是 Qwen/BGE、质量或应用回归。

主 Agent 后验只读观察正式容器 ID `b7f36e1b86498f9c56299e127c5a8e9b840e285802ea4ec7ab21e4e87bbacc66`，
运行且 healthy，StartedAt 为 `2026-11-17T14:59:05.899044319Z`；本探针未连接正式数据库，
该后验观察不等于本轮对业务表进行前后完整行集比对。

## 未闭环

安全门禁仍未通过；现有官方二进制的构建头文件无法证明、pgrx 安全依赖修复尚未完成，
不在正式库启用扩展，不启动大规模源码编译，不进入下一 Task。独立 QA 和主复核待执行。
