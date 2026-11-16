# PG17.6 / pgvector0.8.7 复现边界

当前业务资源是原Ubuntu VM上的PG17.6，容器内Debian12，vector0.8.7。原[资源安装记录](05-pgvector-resource-report.md)与[持久重启证据](05-pgvector-restart-evidence.json)证明现有实例；它们不证明从空资源重建。`compose.yaml`固定官方PG17.6 digest，**不含vector**。原VM扩展在容器可写层，重启保留，重建丢失，禁止以原vanilla镜像直接替换现有容器。

## 独立资源配方

[Dockerfile](../deploy/postgres-vector.Dockerfile)在原PG17.6镜像上安装PGDG签名包，固定：

- `postgresql-17-pgvector=0.8.7-1.pgdg12+1`
- `postgresql-17=17.6-2.pgdg12+1`
- `postgresql-client-17=17.6-2.pgdg12+1`

后来的vector `+2`依赖较新PG，不能替换。构建断言实际PG及包版本，缺历史版本应失败并记录BLOCKED，不能改成latest或升级原库。旧包长期可获取性不是本项目承诺；离线复现应由操作者保留来自签名仓库且校验过的原包/镜像。

以下是**新隔离资源**命令，需有Docker的主机；Windows本轮无docker命令。不要在原VM目录直接执行`compose up --build`，不要复用原容器名/卷名/端口：

```powershell
docker build -f deploy/postgres-vector.Dockerfile -t agent-pg17-vector:17.6-0.8.7 .
```

在新部署目录复制原Compose配方，把image改为上述独立镜像，并用新的Compose project名、新卷及空闲回环端口，例如`docker compose -p agent-reproduce up -d --wait`；仅新目标配置`POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_PORT`，不在命令行、文档或Git写真实密码。复制文件仍需保留原健康检查、回环绑定和PG17数据目录。验收结束只停止/删除本轮新资源，不使用面向原项目的down -v。

## 新空双库初始化

在Windows设置本地`.env`中的新目标URL：管理连接到`postgres`，普通连接分别到`agent_demo/agent_app`和`agent_demo_test/agent_test`，host须为localhost/127.0.0.1及同一端口。VM远端bootstrap须通过经授权的本地转发或管理员本地入口；脚本不放宽远程管理边界。

1. 用项目解释器执行`python -m scripts.init_databases`，只创建固定双库及各自owner，验证既有口令，不重置已有角色。
2. 以管理员连接**各目标库**执行`CREATE EXTENSION IF NOT EXISTS vector`。普通应用owner无superuser；006自身也含IF NOT EXISTS，因此管理员预建不会改动冻结迁移。原VM采用管理员事务执行006及明确授权知识表CRUD，见原资源记录；不要修改006/checksum绕过权限。
3. 分别执行`python -m scripts.migrate --target development`、`--target test`，确认001～006全部checksum匹配，vector扩展0.8.7，embedding列vector(1024)。两库隔离连接权限继续核验。
4. 分别执行`python -m scripts.setup_checkpoint --target <target>`，再`python -m scripts.setup_store --target <target>`。Saver/Store框架表独立于001～006，应用启动不代为setup。
5. **仅首次新环境**执行`python -m scripts.seed_orders --target <target>`初始化五个模拟订单；已有库/新演示场景不seed、不重置固定订单。
6. 准备相同revision的本地Qwen及tokenizer缓存，以`python -m scripts.ingest_knowledge --target <target> --root data/knowledge --manifest data/knowledge/manifest.json`导入固定语料，导入/查询保持相同profile。不要并行启动另一个Qwen服务。
7. 显式启用Embedding，以README命令启动单worker，核health各资源状态，再按演示执行真实五能力；health本身不探测Chat网络。

上述顺序是新资源操作配方。Task6.3.2已实际完成[隔离镜像构建](06-database-reproduction-evidence-20261115-r2.json)、[新空双库迁移/Saver/Store初始化及幂等](06-delivery-fresh-database-evidence-20261115.json)，并由主Agent[独立核对和精确清理](06-database-reproduction-cleanup-evidence-20261115.json)通过；原两库、原volume和原运行版本保持，原容器未重启。新空库未seed或重演业务，实际范围与前序证据复用见[本轮交付报告](06-delivery-report.md)，未执行步骤不能由此文推导已通过。
