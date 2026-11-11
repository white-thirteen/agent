# 02 QA-EXEC-01 第二轮输出边界修复

关联[首轮任务](02-qa-credential-output-fix-task.md)及[首轮开发修复报告](record/02-qa-credential-output-fix-report.md)。用户决定保留既有凭据暴露和密码复用为Demo已知遗留，仍须保护后续测试输出。原业务设计和密码现值保持。

主Agent审核首轮后，用完全虚构的AGENT_TEST_DATABASE_URL在仓库外临时测试文件稳定复现两处剩余回显。

```python
def test_probe():
    value = os.environ["AGENT_TEST_DATABASE_URL"]
    warnings.warn(value)
    logging.warning(value)
    raise RuntimeError("controlled probe")
```

从项目根目录运行python -m pytest -c pyproject.toml -q <临时文件>，退出1，捕获日志中已有脱敏占位，但默认warnings汇总仍包含虚构密码。增加--log-file <临时文件>后，仍退出1且文件含虚构密码。主控检查只输出布尔结果，未使用或展示真实凭据。

请在首轮基础上最小修复。

1. pytest标准warnings汇总中的已配置凭据也须脱敏，保留warning类别、来源和正常失败状态。补充一项有实际意义的子进程回归。
2. pytest自带文件日志为独立输出边界。Demo可直接像现有JUnit/实时日志一样明确拒绝不支持的--log-file及对应ini配置，而非静默允许原文写盘；验证在测试执行前拒绝，或实现同等简单有效的脱敏。避免扩展第三方输出插件框架。
3. 保留首轮URL/kwargs/标准输出/标准错误/收集失败保护与支持边界。未知临时凭据、插件启用前输出及任意代码自行写文件仍按文档限制，不追求全能秘密扫描。
4. 项目.venv，定向合成回归、必要完整回归及Ruff，真实PG只用专用测试库并核对前后数据/schema；报告和工具输出均脱敏。不得修改数据库密码、认证文件、部署或主Agent协调记录，不调用其他会话、不Git归档。

独立保留本轮修复记录，保存到docs/resume/record/02-qa-credential-output-round2-report.md，关联阶段02、Task2.3验证/QA-EXEC-01及本提示词，说明修改文件、两个复现关闭证据、实际测试命令结果及边界。不要覆盖首轮报告。完成后返回报告路径，等待主Agent审核与独立测试会话回归。
