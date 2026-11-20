# FORMAL-QA-001 / 002 修复本地证据

脚本SHA256：`27959a572af32bbfefa3a707ddbdcbe4ff4151ba8e5ff78d57f2d58f2f8900ba`。

使用项目 `.venv`，通过 `@'…'@ | .\.venv\Scripts\python.exe -` 运行三段内联受控自检：

1. **001**：替身模拟目标容器Running、目标SQL不可用，禁止调用维护态SQL；实际记录按目标ID stop、
   保留目标、恢复源及连接，状态为`ROLLBACK_ORIGINAL_RESTORED`。写入标记存在时无Docker命令且拒绝回滚。
2. **002**：替身模拟维护HBA加载后拒绝新连接；存在旧client时，确认旧client未被终止、没有断网、
   HBA恢复；client为零时，确认先拒绝新连接、后断网、再恢复原HBA。两种情况均核对inode与元数据。
3. **002恢复**：分别模拟源仍连接及已断开，原HBA的同inode恢复和reload均先于必要的reconnect；
   未知HBA字节触发拒绝且不被覆盖。

以上连接、SQL、Docker与网络为受控替身，不代表真实VM证据。
实际命令：`.\.venv\Scripts\python.exe -m ruff format scripts/upgrade_v2_01_pg1712.py`、
`.\.venv\Scripts\python.exe -m ruff check scripts/upgrade_v2_01_pg1712.py`、
`.\.venv\Scripts\python.exe -m ruff format --check scripts/upgrade_v2_01_pg1712.py`，均通过；
`.\.venv\Scripts\python.exe -c "import ast,pathlib; ast.parse(pathlib.Path('scripts/upgrade_v2_01_pg1712.py').read_text(encoding='utf-8')); print('AST OK')"`通过。
未连接VM、PostgreSQL或Docker，未运行真实业务/模型测试；独立QA未复测。
