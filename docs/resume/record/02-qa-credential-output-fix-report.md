# 02 QA-EXEC-01 测试异常输出脱敏修复报告

本记录关联阶段 02、Task 2.3 的验证工作、QA-EXEC-01、[本轮修复任务](../02-qa-credential-output-fix-task.md)及 01 Delivery 基线 `cf3e763`。本轮结果为开发自测，交由主 Agent 复核及独立回归。

## 问题与修复

独立 QA 临时探针在 Windows 默认 Proactor 事件循环下连接 psycopg，异常回溯展开连接 kwargs，导致真实测试凭据进入 pytest 失败输出。Settings 的 SecretStr 和生产连接池日志过滤没有覆盖 pytest 展开的驱动参数。此前输出已发生，当前接口不能定点撤回。

修复前使用临时外部测试文件和完全虚构的环境变量 URL，模拟异常、日志及标准输出。子进程的 pytest 退出码为 1，父进程在内存中确认虚构密码出现在失败输出且 RuntimeError 保留，只打印布尔结论，未打印原始回溯。

本轮新增 `scripts/pytest_redaction.py`，由 `pyproject.toml` 的 pytest addopts 在项目测试配置中加载。插件读取本地 `.env` 和进程环境变量中 `AGENT_DATABASE_URL`、`AGENT_TEST_DATABASE_URL` 的值，提取 PostgreSQL 密码及常见 URL 编码和 Python 字符串表示。环境覆盖 `.env` 时，两组配置均纳入替换。pytest 测试及收集报告的异常内容和捕获输出在报告分发前替换已知敏感值。失败状态、异常类型、文件及行号继续保留。

插件要求 `--capture=fd`，拒绝无捕获、`sys` 或 `tee-sys` 捕获、实时日志和 JUnit XML，避免这些已知输出路径绕过该报告边界。pytest 显式返回使用错误，失败不会变成成功或跳过。

## 本轮文件

| 文件 | 职责 |
| --- | --- |
| `scripts/pytest_redaction.py` | 配置凭据提取、pytest 报告脱敏及输出模式限制 |
| `pyproject.toml` | 默认加载项目 pytest 插件 |
| `tests/test_pytest_redaction.py` | 以真实 pytest 子进程及虚构连接配置验证输出与退出状态 |
| `README.md` | 常规与仓库外探针调用方式及边界 |
| `docs/resume/README.md` | 本轮提示词及修复报告导航 |
| 本报告 | 修复、证据与交接 |

工作区原有 02 实现和文档变更保留，主 Agent 协调文件未由本轮修改。密码、认证配置、数据库角色及部署未修改。未执行 Git Commit/Push。

## 受控验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_pytest_redaction.py
.\.venv\Scripts\python.exe -m ruff check scripts/pytest_redaction.py tests/test_pytest_redaction.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/pytest_redaction.py tests/test_pytest_redaction.py
```

定向测试为 7 passed。测试分别从项目配置执行外部临时失败用例和包含仓库测试的运行，虚构应用库与测试库 URL、URL 编码密码、连接 kwargs、`--showlocals`、捕获日志、标准输出及标准错误均经过真实 pytest 报告。断言两个明文密码、编码密码及完整连接串不可见，报告保留 `[REDACTED]`、RuntimeError、测试文件和行号、日志与标准输出及标准错误章节，子进程失败退出码为 1。五个不支持的输出模式各自以退出码 4 拒绝。两个 Python 修改文件 Ruff lint 通过，format 检查为 2 files already formatted。完整回归后仅补充了标准错误和行号断言，并重新运行本定向测试。

独立回归可从项目根目录执行以下命令，使用临时文件中的虚构凭据构造失败场景。执行时保留默认 fd 捕获。

```powershell
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q C:/path/to/test_probe.py
```

默认项目入口为 `.\.venv\Scripts\python.exe -m pytest -q`。从项目根目录并显式 `-c pyproject.toml` 运行仓库外 QA 文件也会加载同一插件。开发自测中实际使用绝对路径指向项目配置及仓库外临时测试文件。

## 真实测试库保护

使用项目解释器执行内联 Python harness。连接前调用 `validate_test_target`，只连接 `Settings().test_database_url`，在只读事务中断言数据库及角色为 `agent_demo_test` / `agent_test`，并核对 schema 版本及 checksum 等于仓库迁移文件。预检成功后以进程内环境变量显式启用既有完整 pytest。运行后再次只读检查 schema 与完整 Session 行集，要求与运行前相等。连接异常处理仅输出异常类别，未输出 URL、密码或异常原文。

首次完整回归为 115 passed。随后将输出模式从允许 `sys` 收紧为仅允许 `fd`，并新增对应拒绝测试。最终完整回归为 116 passed、0 failed、0 skipped，退出 0，前后 schema 和 Session 快照一致，Session 均为 0 行。既有 PG 测试的事务回滚和随机用户精确清理逻辑沿用，未连接应用库或升级迁移。

## 已知边界与交接

脱敏范围是项目插件加载后 pytest 标准测试和收集报告中的已配置数据库连接值及其密码。插件不会发现任意临时凭据，也不涵盖 pytest 启动前输出、进程外日志、测试自行写入的文件、第三方输出插件、独立子进程输出或主动覆盖配置/禁用插件的调用。测试如以其他凭据或输出后端运行，需针对该路径另行验证。插件替换完整 URL 时可能隐藏该 URL 中的非敏感连接信息，失败类型与定位仍保留。

用户决定暂缓换密，既有凭据暴露及密码复用仍为已知遗留，不能因本次修复视为消除。原 QA 事件循环偏差及历史报告保留原轮次语境。阶段状态与正式验收由主 Agent 维护，本报告不声明独立回归或阶段验收完成。
