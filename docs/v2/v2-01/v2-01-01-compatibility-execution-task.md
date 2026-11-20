# V2 01 / Task 1.1.1：技术适配与契约冻结

2026-11-17。用户已授权V2 01开发，当前分支v2，基线232469a（06交付98af9d8已合入并推送main）。仅执行本Task，交付后独立QA，未通过不得进入1.1.2。02/03不开发。

必读根AGENTS.md、[批准设计](v2-01-knowledge-rag-enhancement-detailed-design.md)第1/3/6/7节及实际knowledge模型、Repository、Retriever、ingest、固定PG镜像/数据库复现说明。按需读必要完整源码，不通读历史。

## 范围

1. 核对本地/VM及容器真实环境、固定PG17.6/pgvector0.8.7及既有数据边界；不得输出.env或凭据。
2. 核对官方pg_search候选固定版本、Bookworm/amd64包依赖/摘要/预加载与加载条件；不能只作静态主版本判断。
3. 在全新隔离镜像/容器/专用空库执行真实加载、Jieba中文/英文标识符、text Chunk ID、过滤先于Top K、更新/删除/回滚、同快照Dense/Sparse及重启持久化验证；保护原容器/卷/数据库，禁止升级PG、替换受保护vector或清空旧数据。无损的隔离验证及精确清理已在用户开发授权范围内。
4. 冻结SparseIndexProfile/RetrievalProfile及候选结果、版本/回填/回滚契约，优先复用现有模型，只做本Task必要契约修改，不实现1.1.2发布/索引接入或后续Hybrid/BGE。
5. 记录可核验命令/真实结果、包/镜像版本、保护检查、清理和兼容结论。未执行不算通过；必须升级固定基线或关键不兼容则报告BLOCKED，提交具体证据，不自行切换SQL BM25、冻结设计或数据库版本。

VM沿用既有Ubuntu目标192.168.150.101、SSH用户white7和原用户授权的认证方式；凭据不写入任务/代码/证据。必要认证由主Agent协助，不自行遍历用户秘密或请求重发聊天密码。

## 所有权

Implementer负责本Task必要knowledge契约、小型可复现兼容探针及专属报告/JSON；可用scripts/verify_v2_01_compatibility.py、docs/v2/v2-01/v2-01-01-compatibility-report.md等独立命名。主Agent负责STATE/README/AGENTS及Git。不得修改批准设计、原.env、旧证据、迁移001～006、既有六项遗留或02/03文档。共享代码库存在其他既有改动，保留它们，不回滚他人修改。

## 验收

精确PG/vector不变；真实扩展和两路语义/事务/重启证据；当前数据保护；版本契约明确；不重算原向量；必要定向测试；无假通过、凭据泄露、临时资源遗留或范围扩张。结束后交修改文件/关键位置、实现摘要、实际命令结果及遗留。Implementer不提交/推送、不另派Agent，等待独立QA。
