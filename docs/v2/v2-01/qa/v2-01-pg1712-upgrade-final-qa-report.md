# PG17.12 原库升级最终独立 QA

结论：**PASS（本次授权范围）**；未发现需编号的问题。原 QA 已就正式脚本修复给出本地通过，本次独立核对正式执行结果及真实数据库只读状态，不代表 V2 后续开发获授权。

- 通过 `default_transaction_read_only=on` 的真实 PostgreSQL 连接，先以管理角色连接 postgres：服务版本 `170012`，`pg_control_system().system_identifier` 与 post-Docker 回执一致，规范化角色、成员、设置、参数 ACL 和表空间语义与最终备份相等。三个角色实际连接的服务端地址、端口和版本一致。
- 原 HBA 拒绝管理角色直连业务库；这是原有身份限制。本 QA 使用 `agent_app`、`agent_test` 各自连接所属库，以 repeatable-read、只读事务和已批准 helper 的完整 inventory 比较最终备份：两库各 13 张 public 表完整行数与 SHA、列定义、约束、索引、所有者/ACL、库及 schema ACL、序列和扩展均相等。各库均为订单 5 行，迁移分别 6/10/4 行；审批、退款、会话、checkpoint、store、知识数据均为空，不能外推非空历史恢复。
- 两普通身份实际连接所属库成功、跨库连接遭 HBA 拒绝，跨库 CONNECT 权限亦为否；两库仅有 `plpgsql` 和 `vector 0.8.7`。两库以纯 SELECT 验证合成向量维数 1024、自相似余弦距离 0、正交距离 1，无插入。
- 本地重新计算最终备份 manifest SHA 为 `40db2eaf611ca4369676ab922f7b8a7fc18c55ae223f987d0853a72de23029e4`，141 文件合计 405240 字节，逐文件大小和 SHA 与 manifest 一致；Windows 回执记录校验、fsync 与限制 ACL 均通过，ACL 和 fsync 本 QA 未重新实测。
- 本地核对 validation gate 对 full regression、Qwen 和 validation 回执的 SHA 绑定：既有真实门禁 229 passed、0 failed、0 skipped、退出码 0，保护数据未变，连接池和任务已关闭；Qwen 回执为 PASS。这些是既有执行证据，本次未重跑。正式各阶段回执依次记录 fenced、final backup、final restore、compose staged、maintenance verified 和 writes-open/reload；post-Docker 回执记录新目标 healthy、旧容器停止，未由本 QA 重新执行 Docker 命令。
- 主 Agent 的升级后应用健康回执记录数据库、checkpoint、store 和 agent ready，连接池关闭、无剩余异步任务，系统标识与 post-Docker 回执一致。该次应用健康检查明确禁用了 embedding，knowledge 不可用；不作为升级后 embedding/RAG 测试通过。
- 正式脚本实际 SHA 为 `a0124fd3c480eb538fc2e597abe1f3e9834343a7573be840c3d80f4d5efb57f7`；将开关及其说明注释按原文本还原后，内存计算 SHA 与已 QA 的 `70363c4b806ee410ab3466c76396eef8fa0f28ae4b50a25ac0cc053612708c25` 一致。

本次仅作只读 SQL 和本地文件核验，未写数据库、未调用 Store SDK、未运行 pytest/seed/setup、未重启服务或 Docker。没有独立重验 Docker/Compose 的当前实际状态、真实硬件断电恢复、非空业务历史恢复或升级后的真实 Qwen/RAG 业务调用；回执和此前验证的适用范围如上。执行权限继承父会话，不宣称独立沙盒隔离。

[独立脱敏证据](v2-01-pg1712-upgrade-final-qa-evidence.json)。