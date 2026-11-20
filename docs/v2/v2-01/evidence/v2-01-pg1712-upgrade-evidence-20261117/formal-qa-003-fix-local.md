# FORMAL-QA-003 修复本地证据

脚本SHA256 `70363c4b806ee410ab3466c76396eef8fa0f28ae4b50a25ac0cc053612708c25`；
`FORMAL_EXECUTION_ENABLED=False`。

使用项目`.venv`通过`@'…'@ | .\.venv\Scripts\python.exe -`运行临时文件及替身检查：

- 模拟维护HBA部分写入、恢复再次部分写入，再按第二次intent恢复原字节与原inode，**通过**。
- 模拟每次写入最多3字节：循环完成后才截断；零字节写入会失败且不截断，**通过**。
- 模拟truncate完成后fsync失败：pending intent允许再次恢复，**通过**。
- 穷举短目标的前缀+旧后缀、长目标逐步扩展以及最终截断状态；未知字节和更换inode均拒绝且不覆盖，**通过**。
- 模拟`rollback-freeze`源仍连接并有部分HBA时，实际调用恢复路径并reload，不重新连接网络，**通过**。

首次Windows短写自检暴露原生文本模式换行转换；为源文件描述符加`O_BINARY`后以上检查重跑通过。
这些用例中快照和journal持久化函数以替身代替，未模拟进程崩溃后的真实Linux文件系统持久性；
未调用Docker、PostgreSQL或VM。持续I/O失败仅保留证据并等待人工处理。

实际静态检查命令：`.\.venv\Scripts\python.exe -m ruff check scripts/upgrade_v2_01_pg1712.py`、
`.\.venv\Scripts\python.exe -m ruff format --check scripts/upgrade_v2_01_pg1712.py`、
`.\.venv\Scripts\python.exe -c "import ast,pathlib; ast.parse(pathlib.Path('scripts/upgrade_v2_01_pg1712.py').read_text(encoding='utf-8')); print('AST OK')"`；均通过。
