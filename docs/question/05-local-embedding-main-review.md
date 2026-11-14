# 05 本地Embedding主Agent协调记录

2026-11-13：用户授权05，随后明确本轮仅Embedding本地化与真实检索，Qwen3-Embedding-0.6B/Windows CPU/1024维，模型目录D:\AI\models\qwen3-embedding-0.6b；Ubuntu VM继续原PG17.6并安装pgvector。不依赖OpenAI Embedding、不索取API Key、不改Supervisor或其他业务，完整KnowledgeAgent/Store不从本单元推导实现完成。

主Agent已查实际实现/依赖和两库，只读确认没有Embedding实现、knowledge表、旧向量或可用vector扩展，schema1～5；因此不需清空或破坏旧向量。用户已授权SSH密码认证连接原VM及系统包/扩展安装，认证资料不记入项目。先检查系统/容器来源/权限，保留PG17.6、卷和所有业务数据，软件包安装先模拟检查；无sudo权限则报告，禁止绕过。

工作单元见[执行任务](../05-local-embedding-execution-task.md)。主Agent负责资源安装/重启，Implementer负责本地代码/依赖/模型与自测，完成后独立QA。当前IN_PROGRESS，05未验收，不Git提交/推送。原角色配置未提交及六项暂缓差异保留。

## pgvector安装与006冻结

实际VM为Ubuntu26.04，原项目容器基于Debian12官方postgres:17.6-bookworm镜像，原卷/私网5432映射和其他容器保留。已验证sudo权限。PGDG签名仓库当前0.8.7-1.pgdg12+2依赖新PG17.12，模拟发现升级后未执行；改选同仓库0.8.7-1.pgdg12+1，并显式固定服务器/客户端17.6-2.pgdg12+1，模拟与实际安装均0升级/1新增。安装后版本仍PG17.6，pgvector包0.8.7-1.pgdg12+1。

两库原9表完整行集已保存本机临时目录用于前后核对，无凭据入文档。006当前已审查、准备由主Agent显式应用，SHA256为`5427fa3648c5bd0e15d46b8961314351055aae849582e55825a2ea093ffc4ea3`。**从本轮应用起006原字节不可修改**，必要修正追加007；Implementer不并行执行迁移。用户已释放内存并明确继续真实验证，仍须按实际内存/CPU/推理结果验收。

006现已通过容器内本地agent_bootstrap管理入口，在同一事务中核对001～005登记摘要/连续性、取得原迁移锁、新增扩展/两表/索引及登记006，两库均COMMIT。Windows远程管理账号按原pg_hba仅可连接postgres库，最初直接管理连接被拒绝且未写数据库；未放宽pg_hba，而沿授权SSH本地管理方式执行。新知识表仅向本库原运行角色授SELECT/INSERT/UPDATE/DELETE，未扩其他表权限。Windows实际验证两库PG17.6、pgvector0.8.7、schema1～6、vector(1024)；1024维临时向量自相似距离0/正交距离1，事务回滚；原9表旧行集一致（迁移表仅新增006）。这是资源检查，不是Qwen模型验收。

原生Implementer父会话`01a1d41a-a960-7c90-a0e1-6c78994aa07a`及原子角色`01a1d41a-f474-70d3-849e-1789a8346464`已产生部分代码，随后运行时明确usage limit，回合failed，不能当完成。未重复派发。额度提示时间过后将用官方native exec resume续接原父会话，并由其followup原Implementer；不使用Bridge、不换账号/模型绕过限制。006和PG资源现已就绪，模型依赖/缓存及自测仍待继续。

额度提示时间后已通过官方native exec resume续接同一父会话、followup原Implementer，实际重新产生定向验证进展；没有新建替代实现角色。已确认两库新知识表CRUD权限，资源证据见[pgvector报告](../05-pgvector-resource-report.md)。受控/真实PG定向已有通过证据，真实Qwen尚待CPU轮子/固定权重下载，不能把构造向量的PG测试当模型通过。下载曾低速断流，实现方采用官方CPU直链与Qwen官方ModelScope来源并校验固定权重SHA256；该实际网络问题处理不引入模型服务或新Provider。主Agent等待完整交付后再派独立QA。

## 真实模型后的PG重启交接

原Implementer已报告真实QwenCPU/pgvector初步通过，并正常退出验收uvicorn，保留test库前缀`qwen05-45b26e2deb0243bebdd1a5a63cbc67d0-`六文档七Chunk供持久化验证。主Agent确认两库无其他活动业务客户端后，**已于2026-11-13T13:47:42Z实际重启原项目容器，PG已重启**。旧容器PID11393→590087，healthy；原PG17.6镜像/卷保持，其他容器不动。Windows在线核对两库pg_postmaster_start_time改变、server170006/vector0.8.7、全部公共表行集相同；六文档/七Chunk的版本/Profile/逐向量摘要相同，证据见[PG重启](../05-pgvector-restart-evidence.json)。Implementer现在可运行新进程离线Qwen复核，不需等待主Agent再次重启或清理这六文档；完成后精确清理自身验收数据。

官方native queue已排队资源通知，但--resume返回当前非交互CLI无daemon无法主动唤醒；没有自研Bridge或改服务配置。CLI协调进程随后自行结束，保护性进程检查未执行任何终止动作。主Agent以同一父会话exec resume及原子角色followup续接，不并行启动两个协调器。

原Implementer首次完整真实库170 passed/1 failed，唯一失败定位旧04验证辅助函数硬编码schema=5。主Agent已批准只复用集中EXPECTED_SCHEMA_VERSION替换该旧计数，保留完整checksum及所有业务断言；任务末尾已记裁决。不改退款业务，不将失败写成通过，最终须完整回归。

## 实现交付与独立QA交接

原Implementer已完成并停止。最终完整真实库172 passed/0 failed/0 skipped，pip check、全仓Ruff及16个改动Python格式通过；原04辅助脚本只增加集中schema版本引用，业务/完整checksum断言不变。历史170/1及随后脱敏嵌套测试的短暂失败保留在交付报告，未弱化测试。

真实Qwen prepare、PG原容器重启、新Windows uvicorn离线check及精确cleanup均完成，详见交付报告与原始JSON。两次Windows实际进程PID36264和42552，重启后未重新导入便可召回原六文档，三问预期来源均Top1；cleanup只删除本轮六文档七Chunk，原业务/迁移/Saver行集保持。BF16/CPU2线程/batch1，峰值working set约1.21～1.28GiB，peak private commit约3.61GiB；不把驻留内存当全部需求。

主Agent已通过同一官方native父会话派发唯一配置qa角色，干净上下文、依任务独立验收。当前仅开发自测完成，独立QA与主Agent最终裁决待回报；不宣布05整阶段完成，不执行Git。

## 最终复核：本工作单元 VERIFIED

独立原生qa角色01a1d542-4626-7d03-b951-d3947563cec6已完成并停止，角色由本机运行时元数据核验为qa；父协调器exit0。[独立QA报告](05-local-embedding-qa-report.md)结论PASS，无05-QA阻塞项。QA自行运行7项受控/真PG测试全部通过、无skip，另以唯一state完整执行真实Qwen prepare/check/cleanup，独立两个Windows模型进程三问Top1、更新失效及精确清理通过；pip/Ruff/16文件格式通过。完整172项门禁与主Agent唯一一次真实DB重启明确标记为复用可信来源，没有重复全量或重启。

主Agent复核代码和两层真实证据，接受当前本地Embedding与真实检索工作单元技术交付，状态VERIFIED；不是05整阶段ACCEPTED。QA期间业务/脚本/测试/配置/006/.env及原模型验收JSON摘要均未变化；QA日志仅按原字节额外保留.txt副本以便将来归档（原.log受忽略规则影响），报告链接只作此文件名调整。

最后只读核对两库，仍server17.6、vector0.8.7，原9表含006迁移记录的完整行集相对重启前均无变化，开发/测试知识表均0行；验收数据全部精确清理。见[主Agent最终证据](../05-local-embedding-main-final-evidence.json)。原六项暂缓差异保留，无Git提交或推送，HEAD仍6c72169da306b5bfd604d043675d51a317d03de9。

限制：当前仅提供文档导入、向量持久化、检索及RAG Context，不含KnowledgeAgent生成式回答/工具接线/Store。Embedding默认关闭，使用时显式开启；真实验收显式放宽初始化/推理测量时限，默认应用仍120/8秒，检索整体15秒。CPU内核强制中断未做，超时/取消占槽和排空以受控线程验证。16GB环境可用内存与分页会影响延迟，峰值resident和private commit已分别记录。pgvector包在原容器可写层，重建容器须重新按固定兼容包安装，普通重启已验证。停止本单元，等待用户审核及后续Task，不推导新授权。
