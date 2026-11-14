# 05 pgvector资源安装与迁移记录

2026-11-13。用户授权Windows本地Qwen/Ubuntu原PG17.6方案、SSH系统包安装及必要数据库配置。此报告只覆盖已实际执行的数据库资源工作，不替代Qwen真实模型、端到端及独立QA验收。

- VM：Ubuntu26.04；原项目容器内部Debian12，基于原官方postgres:17.6-bookworm固定镜像。保留原容器、agent-engine-demo-db_agent_pg17卷、私网5432绑定、pg_hba及其他三个容器，未重建数据库或升级PG。
- 使用PGDG签名仓库。模拟0.8.7-1.pgdg12+2时发现依赖PG17.12，未安装。改为`postgresql-17-pgvector=0.8.7-1.pgdg12+1`并显式固定服务器/客户端`17.6-2.pgdg12+1`；实际0升级、1新增，扩展包273kB。安装后dpkg和pg_config确认仍PG17.6。
- 安装命令：在原容器内执行`apt-get update`后，`apt-get -y --no-remove --no-install-recommends install postgresql-17-pgvector=0.8.7-1.pgdg12+1 postgresql-17=17.6-2.pgdg12+1 postgresql-client-17=17.6-2.pgdg12+1`。不使用会连带升级PG的默认最新包。
- 两库安装前均无vector可用扩展、knowledge表或旧向量，仅schema1～5；没有有损维度迁移、旧向量清空或索引重建。
- 006迁移SHA256：`5427fa3648c5bd0e15d46b8961314351055aae849582e55825a2ea093ffc4ea3`，已应用后不可修改。原Windows管理连接只允许postgres库，改连业务库被pg_hba拒绝且未写入；保留该访问控制，通过授权SSH在容器本地agent_bootstrap管理入口执行006。事务内核对001～005版本/原checksum，取得原迁移锁1701001，再建扩展、两知识表/必要索引、登记006并COMMIT。
- `agent_demo_test/agent_test`、`agent_demo/agent_app`均已在线核对schema1～6及全部本地SHA256，vector扩展0.8.7，knowledge_chunks.embedding为vector(1024)。仅给各自原运行角色新增两知识表CRUD权限，未扩旧表权限或开放远程管理连接。
- Windows实际执行1024维临时向量运算：自相似余弦距离0、正交距离1，排序正确；事务回滚，未留下探针表/行。此为数据库运算检查，向量为构造值，不冒称Qwen真实模型结果。
- 安装前保存两库全部原9表完整行集；迁移后原行集一致，schema_migrations仅新增006。原固定订单、Session、退款/审批及Saver数据保留。脱敏机器证据见[资源证据](05-pgvector-resource-evidence.json)，完整本机前后快照不写入仓库。

当前扩展包在原容器可写层中，普通容器/VM重启会保留；将来重建容器时必须在同一PG17.6基础镜像重新执行上述固定包安装，不能误换至原不含vector的镜像或默认升级PG。此处不擅自重建或切换现有容器。数据库重启后真实持久向量验收仍待模型/文档实际入库，再由主Agent执行原容器重启和查询核对。

后续实际执行：真实Qwen先在test库写入六文档/七Chunk并退出uvicorn，主Agent确认无活动项目DB客户端后重启原容器；PID11393→590087、healthy，两库PG启动时间改变。Windows核对全部公共表行集及逐向量摘要/版本/Profile重启前后相同，PG17.6/vector0.8.7保持，见[重启证据](05-pgvector-restart-evidence.json)。新Windows进程的离线Qwen语义复核由原Implementer继续执行，不能把只读SQL摘要核对写成该模型复核已完成。

SSH身份认证资料只在交互认证中使用，不保存在项目、脚本或本文。原生Implementer因使用额度限制曾中断，已保留其部分实现；本资源通过不代表本工作单元或05阶段通过。

最终闭环：原Implementer新Windows进程PID42552离线check已通过，随后独立QA两个模型进程再次验证真实持久检索和精确清理；详见[交付报告](05-local-embedding-delivery-report.md)和[独立QA](question/05-local-embedding-qa-report.md)。上文各待办仅为对应记录生成时状态，现无此项阻塞。
