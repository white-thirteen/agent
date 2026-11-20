# V2 01 / Task 1.1.1 适配与契约记录

2026-11-17。当前仅执行1.1.1；本记录不批准1.1.2，也不代表阶段验收。

**结论：BLOCKED。** 官方0.26.6预编译包在固定PG17.6上预加载失败：
`FATAL: could not load library "/usr/lib/postgresql/17/lib/pg_search.so": undefined symbol: pg_mblen_cstr`。
未升级PG、替换原vector或改用SQL BM25；未进入1.1.2。此结论针对本次固定官方二进制组合，
不泛化为其他版本/重新编译产物也已验证。

## 固定候选与证据边界

官方候选为 `pg_search 0.26.6`，Bookworm/amd64 包
`postgresql-17-pg-search_0.26.6-1PARADEDB-bookworm_amd64.deb`。
本地从官方发布下载54,276,840字节，实际SHA256与发布资产摘要均为
`16a14d382f088bc23e7c8624e4860fd8bf01a939c67c7695348de0615e323ddb`。
真实包control：Version=`0.26.6`，Architecture=`amd64`，Depends=`postgresql-17, libopenblas0`。
这只能证明包声明允许PG17，不能证明PG17.6的二进制兼容。

来源：[固定发布](https://github.com/paradedb/paradedb/releases/tag/v0.26.6)、
[资产摘要](https://github.com/paradedb/paradedb/releases/expanded_assets/v0.26.6)、
[固定版本control](https://github.com/paradedb/paradedb/blob/v0.26.6/pg_search/pg_search.control)、
[固定版本Jieba测试](https://github.com/paradedb/paradedb/blob/v0.26.6/tests/tests/jieba.rs)。
control声明requires=`vector`；[官方安装说明](https://www.paradedb.com/docs/operate/deploy/self-hosted/extension)
要求预加载`pg_search`并重启。部署命令不照抄会自动升级依赖的无版本apt示例。

运行门禁脚本：[verify_v2_01_compatibility.py](../../../scripts/verify_v2_01_compatibility.py)。
固定原PG17.6镜像digest、PG服务器/客户端包和vector0.8.7 `+1`包；
候选容器无网络、无主机端口、独立卷；仅对原容器执行只读版本/行摘要/列定义查询。
原始数据不写证据，原.env、原PG实例、原vector、迁移001～006均不修改。

真实远端运行由主Agent在授权SSH会话代执行。首轮运行的脚本SHA256为
`8d9b8205cf52dd858b4712368f49f2bcccdffebf7a8b68c8f2a967609d749a8c`。
[实际执行源](evidence/v2-01-01-compatibility-executed-20261117.py)已取回，字节SHA核对一致。
该版本只运行构建/加载门禁，完整语义检查尚未执行；工作区最新脚本在运行期间补强了首LABEL中间资源清理、源摘要、时间戳及后续语义探针，**不把最新源码冒充本轮执行源**。

实际远端命令（退出1）：

```bash
sudo -n python3 /tmp/agent-v201-compat-Fc9igj/verify_v2_01_compatibility.py \
  --package /tmp/agent-v201-compat-Fc9igj/v201111-pg-search.deb \
  --output /tmp/agent-v201-compat-Fc9igj/load-evidence.json
```

构建实际保持PG17.6、`postgresql-17-pgvector=0.8.7-1.pgdg12+1`，安装pg_search0.26.6成功。
这一步与Debian包依赖检查通过，不能掩盖随后的真实二进制加载失败。
启动使用`shared_preload_libraries=pg_search`，隔离服务器因缺符号退出；
所以`CREATE EXTENSION`、Jieba中文、英文标识符、text Chunk ID、过滤先Top K、参数化、
更新/删除/回滚、Dense/Sparse同快照、最终来源及重启持久化均**未执行/未验证**。
本次不运行Qwen/BGE，未重算原向量。

机器证据：[加载门禁JSON](evidence/v2-01-01-compatibility-evidence-20261117.json)。
原两库全部public行摘要与列定义、原容器ID/启动时间/卷和精确PG/vector包前后一致
（`protected_unchanged=true`）。本token候选容器、卷、镜像清理完成
（`cleanup_complete=true`），脚本自有构建目录已删除。
外层传输目录`/tmp/agent-v201-compat-Fc9igj`当前为独立QA保留，只含上传包/执行源/JSON等本轮材料；
它不在`cleanup_complete`所指的候选容器/卷/镜像范围内，待QA后由主Agent精确清理。

## 本Task增量契约（未激活）

[models.py](../../../app/knowledge/models.py)新增未装配契约，V1 SearchResult、工具版本、Graph解析器与运行路径保持。
由于兼容门禁BLOCKED，这些类型与下述回填/回滚规则只冻结候选接口，不代表可部署或已批准下一Task。

- `SparseIndexProfile`：固定扩展版本、text Chunk ID键、search_text字段、Jieba/search_mode=true、扩展默认BM25参数语义和输入格式。字段集为chunk_id/search_text；domain、当前文档版本约束在SQL JOIN/WHERE中先于LIMIT执行。BM25统计采用整个扩展索引语义，不声称按过滤集合重新计算。
- `RetrievalProfile`：原Embedding Profile字符串、Sparse Profile字符串，两路Top10/融合Top10、等权RRF/k=60、完整输入格式、BGE原始logit、512 Token及完整Chunk上下文预算。BGE权重/Tokenizer revision为必填，当前没有实例化或虚构已下载revision。
- `RetrievalCandidate`复用来源四元组。Dense为余弦相似度，Sparse为原生BM25，各自保存1起排名；RRF、reranker分数独立，不相加、不解释为概率。
- Hybrid模式下最终EvidenceChunk.retrieval_score固定为reranker原始logit，候选诊断保留两路原分数；V1该字段仍为余弦相似度，必须依mode/结果版本解释。
- `HybridSearchResult`继承原结果字段，强制contract_version=2、mode=hybrid、Profile、正整数发布水位及候选诊断。不能把缺失新字段的V1缓存解析成V2；旧解析器也拒绝V2增量字段。工具版本与Graph解析器的正式切换留在1.3.1。

Sparse输入格式`title-section-content-v1`固定为：标题 +（section非空时` / `+section）+换行+完整content，等同当前Chunk.embedding_text的文字布局。不得截正文，不能把Sparse或BGE配置加入现有document_version计算。改变Profile不改来源四元组、不重算原向量。

BGE输入格式`query-title-section-content-v1`为完整Query与上述完整Passage组成的输入对；特殊Token计入512上限，评分激活函数必须显式Identity以取得raw_logit。该契约不证明BGE已下载或其正常语料超限门禁通过，后者属于1.2.2。

## 后续迁移与回滚约束（未实施）

1. 新迁移追加search_text与单行knowledge_index_state；不改旧迁移。状态记录Profile、稳定索引身份、正整数发布水位与就绪状态，不保存历史正文。
2. 固定锁顺序：先同一全局knowledge索引/发布事务锁，再原document_id事务锁；所有发布、删除、回填和激活入口遵守。Embedding在事务外完成，不持锁运行模型。
3. 受控维护窗口内，只回填标题/章节/正文派生输入并建立固定索引，不重新调用Qwen。先核所有当前Chunk覆盖、派生输入一致、向量/来源身份不变及索引有效，再在同一发布事务激活；部分回填保持不可用。
4. 发布/删除/激活各自事务内递增同一水位。Dense/Sparse在一个只读REPEATABLE READ事务内读取当前版本约束与水位，事务结束后再BGE；发布前仍做现有来源复核。水位不能恢复历史全文。
5. 回滚先停止受理新Hybrid知识Task，等待活动知识Task结束，显式恢复原Dense装配/旧工具契约，再移除未启用的派生索引/字段/状态（需要时在维护窗口执行）。保留所有权威文档、原向量、来源身份和旧迁移；不无条件DROP EXTENSION CASCADE，不触及退款/Store。

## 已执行本地检查

项目`.venv`执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py -q
# 7 passed in 12.45s
# 补充indexed_fields后，单独复核新增契约用例：1 passed in 0.59s
.\.venv\Scripts\python.exe -m ruff check app/knowledge/models.py scripts/verify_v2_01_compatibility.py tests/test_knowledge.py
# All checks passed!
.\.venv\Scripts\python.exe -m ruff format --check app/knowledge/models.py scripts/verify_v2_01_compatibility.py tests/test_knowledge.py
# 3 files already formatted
```

控制测试只验证版本结果拒绝旧缓存、来源身份及原知识行为；不代替真实数据库兼容测试。未运行真实Qwen/BGE、Hybrid检索质量或V1完整回归。

## 未闭环与停止点

1. 原固定环境与官方pg_search0.26.6二进制不兼容，必须由主Agent/用户裁决后续方案；不自行升级PG或选择SQL BM25备选。
2. 真实加载后的全部语义/事务/重启门禁仍未验证；增强探针源码存在不等于执行证据。
3. 本Task交付为兼容阻塞发现及未激活契约，等待独立QA和主Agent复核，不宣告Task或阶段验收通过。
