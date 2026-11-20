# PG17.12 正式升级脚本独立 QA

结论：**FAIL**。当前脚本 SHA256 `ec595736199cc8b2341d4c542b2eed3e7a0edc61e12636c474686b4dbf7e4b1c`；不能只将 `FORMAL_EXECUTION_ENABLED` 改为 True 后执行。以下问题须退回原 Implementer 修复，再独立复测。

## FORMAL-QA-001 / P1：目标数据库启动失败时，写前自动回滚可能无法恢复原服务

位置：`scripts/upgrade_v2_01_pg1712.py:1276`、`:1438`、`:1139`。

复现条件：cutover 已归档原容器并启动目标容器；目标容器保持 Running，但 PostgreSQL 未就绪、启动失败或本地 SQL 不可用。`wait_sql` 超时后 cutover 留存目标。运行 `rollback-cutover` 时，代码在停止该目标前先调用 `verify_maintenance`，该函数依赖目标 PostgreSQL 的本地 SQL 与 TCP 响应；数据库不可用导致异常，停止目标、恢复原 Compose 和重启原容器均无法执行，旧服务继续不可用。没有跨越写入标记也不能避开此依赖。

本地受控自检以替身构造原容器已归档、目标仍 Running 且维护检查因 PostgreSQL 不可用失败的状态，实际返回 `ROLLBACK_CUTOVER_STARTED`、`failure: PostgreSQL startup unavailable`，记录的 Docker 命令列表为空；未执行真实 Docker 或数据库操作。需保证写入边界未越过时，针对启动失败安全确认目标身份并完成恢复，同时保留已开放写入时禁止自动切回的约束。

## FORMAL-QA-002 / P1：断网前检查与断网之间存在新连接竞态

位置：`scripts/upgrade_v2_01_pg1712.py:706`、`:720`、`:723`。

复现条件：第一次 `source_quiescence` 返回零 client 后，外部客户端在 `docker network disconnect` 前连接并开始事务。断网会中断该连接，断网后的 client 检查无法识别已经被中断的任务，违背不终止未知任务的要求。两次观察之间没有持久阻止新连接的措施。此结论基于命令顺序与网络断连行为，未在 VM 做真实并发复现。需要在不终止既有连接的前提下建立阻止新连接的边界，再安全核验或等待现有任务。
## 已检查的边界与证据

- 源围栏检查固定容器身份、网络、地址和全部数据库 client，断网前持久记录，断网后检查网络、PG 协议及 client；没有终止连接操作。最终备份使用固定 SHA helper，前后核验围栏，并要求 Windows 逐文件回执；最终恢复使用独立新卷及 internal 网络。
- 写入前通过目录挂载维护 HBA；持久写入边界标记先于原 HBA 原子替换，标记存在时拒绝自动回滚，写后停止目标保留数据。上述是源码检查，不等同实际故障恢复验证。
- 私有原 Compose 中七处预期替换片段实际均唯一；原 `command` 为 `postgres -c hba_file=/etc/postgresql/pg_hba.conf -c password_encryption=scram-sha-256`。代码对 Compose 解析后的 command 与 VM 原 inspect `Config.Cmd` 做精确比较；该 inspect 私有文件未在本地，不能独立确认二者实际相等。需要主 Agent 在 VM 受控确认，且本次没有运行真实 Compose。
- 已核对项目 `.venv` 本地脚本 SHA 和上述替身复现，读取正式交接及本地证据。主 Agent 提供的验证副本 229 passed、0 failed、0 skipped 与 Qwen 证据未在本次重复运行；不将替身和静态阅读当作 VM、Docker、PostgreSQL 或真实回滚通过。

遗留：本次未访问 VM/数据库，未对原容器、卷、源码、业务、迁移或 `.env` 写入。修复后仍须针对真实 Compose、源命令和受控故障恢复完成主复核及实际验证。