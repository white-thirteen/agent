# 02 QA-EXEC-01 第二轮输出边界修复报告

本记录关联阶段 02、Task 2.3 验证、QA-EXEC-01 及 [第二轮修复任务](../02-qa-credential-output-round2-task.md)。首轮记录保留于 [首轮修复报告](02-qa-credential-output-fix-report.md)。本轮为开发自测，待主 Agent 复核及独立 QA 回归。

## 复现与修复

首轮插件处理 pytest 测试及收集报告的异常和捕获内容。pytest warnings 汇总通过独立的 `pytest_warning_recorded` 钩子收集，文件日志通过独立的日志处理器写入，因此均绕过首轮报告脱敏。

修复前，以完全虚构的 `AGENT_TEST_DATABASE_URL` 和仓库外临时测试文件执行真实 pytest。临时测试分别发出 warning、记录日志并抛出 RuntimeError。默认运行和添加 `--log-file` 的运行均退出 1，主进程只输出布尔检查结果，确认虚构密码分别出现在 warnings 汇总和日志文件。未使用真实凭据进行失败注入，也未输出原始敏感回溯。

本轮在 `scripts/pytest_redaction.py` 增加 warnings 钩子，复用既有配置凭据替换逻辑，处理 warning 消息和显示源码行。pytest 的 warning 类别、文件和行号由原记录保留。pytest 内置文件日志按首轮输出边界策略拒绝，插件在日志插件初始化前检查 `--log-file` 和 `log_file` ini 设置，发现任一非空设置即以 pytest 使用错误退出。

## 本轮修改文件

| 文件 | 修改 |
| --- | --- |
| `scripts/pytest_redaction.py` | 脱敏 warnings 汇总，启动前拒绝 pytest 文件日志 |
| `tests/test_pytest_redaction.py` | 增加 warnings 失败场景及 CLI、ini 文件日志拒绝场景 |
| `README.md` | 更新支持的 warnings 输出和文件日志限制 |
| `docs/resume/README.md` | 增加第二轮任务与报告导航 |
| 本报告 | 保存本轮独立记录 |

现有首轮报告和主 Agent 协调记录保留。工作区中其他修改由原会话产生，本轮保留其内容。未修改密码、认证文件、业务设计、数据库角色或部署，未执行 Git Commit/Push。

## 验证与结果

使用项目解释器执行。

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_pytest_redaction.py
.\.venv\Scripts\python.exe -m ruff check scripts/pytest_redaction.py tests/test_pytest_redaction.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/pytest_redaction.py tests/test_pytest_redaction.py
```

定向回归为 10 passed。虚构凭据场景通过真实 pytest 子进程和仓库外临时探针检查，warnings 汇总包含 `UserWarning: [REDACTED]` 和测试文件行号，虚构密码及完整 URL 不可见，原 RuntimeError 与失败退出码 1 保留。日志文件的 CLI 和 ini 两种配置均返回退出码 4，测试执行标记和日志文件均未创建。首轮 URL、kwargs、标准输出、标准错误及其他拒绝模式回归继续通过。

两个修改的 Python 文件通过 Ruff lint，format 检查结果为 2 files already formatted。完整回归后加强了定向测试，要求类别和来源确实位于 warnings 汇总中，并重新运行定向回归。

## 完整回归和测试库核对

使用项目解释器通过 PowerShell here-string 管道执行 Python harness。先对 `Settings().test_database_url` 和开发库配置调用 `validate_test_target`，然后仅连接专用测试库，在只读事务中断言数据库及角色为 `agent_demo_test` / `agent_test`，并核对 schema 版本和 checksum 与仓库迁移文件一致。预检成功后向当前进程设置测试 URL，调用 `pytest.main(['-q'])`。测试完成后再次只读查询 schema 与全部 Session，断言前后快照一致。异常只报告类别，连接信息和原始异常不输出。

完整回归结果为 **119 passed、0 failed、0 skipped**，退出 0。测试前后 schema 和 Session 快照一致，Session 均为 0 行。既有真实 PG 用例沿用事务回滚及随机用户精确清理，未写入应用库或升级迁移。

## 边界与交接

标准 warnings 汇总及 pytest 内置文件日志已纳入本轮保护。仓库外 QA 文件从项目根目录使用 `.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q C:/path/to/test_probe.py` 加载项目插件。插件要求默认 fd 捕获，拒绝实时输出、JUnit XML 和文件日志。

保护仍限已配置数据库凭据及已验证的 pytest 标准输出路径。插件启用前输出、未知临时凭据、其他插件或报告后端、进程外输出及测试自行写文件仍在边界之外。warnings 消息被替换时保留原 warning 类别和来源，原消息对象替换为承载脱敏文本的 Warning。

用户决定暂缓更换密码，既有凭据暴露和密码复用仍是已知遗留。本报告不声明独立 QA 或阶段验收完成。
