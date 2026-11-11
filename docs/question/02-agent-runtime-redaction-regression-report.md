# 02 QA-EXEC-01 输出脱敏独立回归报告

日期为 2026-11-11。关联阶段 02、Task 2.3 验证工作及 QA-EXEC-01。

**独立回归结论为 PASS，建议关闭本轮已验证标准输出路径的未来凭据回显实现问题。定向 10 项、完整真实库 119 项及原 QA 三项补测均独立通过。历史凭据暴露和密码复用继续作为用户接受的 Demo 遗留。**

## 1. 依据与审查范围

本轮依据 [独立回归任务](02-agent-runtime-redaction-regression-task.md)，对照 [首轮修复报告](../resume/record/02-qa-credential-output-fix-report.md)、[第二轮修复报告](../resume/record/02-qa-credential-output-round2-report.md)、两份对应修复提示词、[原独立 QA 报告](02-agent-runtime-qa-report.md) 和 [主 Agent 协调记录第 10 节](02-agent-runtime-main-review.md)。读取适用 AGENTS.md 和 README 的安全 pytest 调用说明。

实际审查 scripts/pytest_redaction.py、tests/test_pytest_redaction.py、pyproject.toml 及相关 README 说明。保护通过默认 addopts 加载，测试报告、收集报告和 warnings 分别使用 pytest 钩子处理。凭据集合同时包含本地 dotenv 和进程环境中两项数据库配置，提取完整连接值、明文密码、quote/quote_plus 编码及 Python 字符串表示。拒绝模式在 pytest_configure 的 tryfirst 钩子执行，早于内置文件日志初始化和测试收集。

本轮仅新增本独立报告。临时合成脚本保存在 C:/Users/15294/AppData/Local/Temp/qa02-redaction-y9ina865/check_output.py，失败注入只使用完全虚构的密码和连接串。子进程输出保存在父进程内存中，只打印检查布尔值和退出码。原历史敏感回溯未重读或复制。

用户已决定暂缓换密，RISK-02-CRED 的历史暴露及角色配置密码复用按主 Agent 记录保留。本轮没有更改密码、认证文件、部署、业务、测试保护实现或冻结设计，也没有调用其他会话或执行 Git 归档。

## 2. 实际命令与结果

命令均从项目根目录使用项目解释器执行。

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_pytest_redaction.py
.\.venv\Scripts\python.exe C:/Users/15294/AppData/Local/Temp/qa02-redaction-y9ina865/check_output.py
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml -q --tb=short C:/Users/15294/AppData/Local/Temp/agent-phase02-qa-7bda02066de345b6b1414d1352322536/test_phase02_independent.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check app tests scripts
```

另以临时内联 Python 执行专用测试库预检、完整 pytest 及后检，以及两项实际 ini 文件配置拒绝验证。完整回归入口为预检成功后显式设置本进程 AGENT_TEST_DATABASE_URL，再调用 pytest.main(['-q'])，采用默认项目配置和 fd 捕获。

| 检查 | 独立执行结果 |
| --- | --- |
| 修复方定向测试 | 10 passed in 18.59s，退出 0 |
| 独立合成脚本 | 2 类合成失败报告及 10 种拒绝配置全部断言通过，脚本退出 0 |
| 实际 ini 文件补充 | log_file、log_cli 两种均在收集前退出 4，断言通过 |
| 完整现有测试，显式真实测试库 | 119 passed in 35.51s，0 failed、0 skipped，退出 0 |
| 原独立 QA 三项外部补测 | 3 passed、3 warnings in 14.53s，退出 0 |
| 全仓 lint | All checks passed，退出 0 |
| app/tests/scripts format | 90 files already formatted，退出 0 |

定向测试包含在完整 119 项中，数量分别记录。三条 warning 为原临时补测中 event_loop_policy fixture 的弃用提示，类别与定位正常保留。本轮补测使用默认 fd 捕获，未使用旧 -s 调用。

## 3. 合成失败、收集及 warnings 独立证据

独立脚本生成仓库外文件，以 -c pyproject.toml -q --showlocals 加载项目插件。环境变量中应用/测试连接均被完全虚构的值覆盖。密码含需要 URL 编码的字符，检查明文、quote、quote_plus 编码及完整测试 URL 是否出现在输出中。

| 场景 | 输入行为 | 实际退出码 | 脱敏及诊断证据 |
| --- | --- | --- | --- |
| 外部测试失败 | 从虚构 URL 解析 kwargs，print stdout/stderr、logging.warning、warnings.warn，随后 RuntimeError | 1 | 明文/两种编码/完整 URL 均不可见；RuntimeError、文件名和行号保留；Captured stdout/stderr/log 章节保留；warnings summary 中 UserWarning: [REDACTED] 存在 |
| 外部收集失败 | 模块收集阶段发 UserWarning，再抛含虚构 URL 的 LookupError | 2 | 同组敏感字符串均不可见；LookupError、收集文件名和行号保留；warning 类别及脱敏文本保留 |

父进程实际输出的两项 redacted/location/category/warnings/capture/pass 布尔值全部为 true。未将失败改成通过或 skip。合成测试失败退出 1、收集失败退出 2 得到保留。

修复方 10 项测试同时验证了外部探针、包含仓库测试的运行、两组不同虚构连接值、明文及编码密码、kwargs、--showlocals、stdout/stderr/log、warnings 汇总和拒绝模式。本轮对照测试实现，确认其断言实际子进程输出及退出码，未弱化失败标准。

默认项目入口的保护由本轮 10 项及 119 项运行核验。指定 -c pyproject.toml 的外部入口则由独立合成失败及原 QA 三项补测实际核验。

## 4. 不支持的输出配置

拒绝探针在临时模块的顶层创建执行标记，检查标记、日志及 XML 文件是否产生，因而验证拒绝发生在测试收集之前。每项均捕获子进程输出，只打印安全摘要。

| 配置 | 实际结果 |
| --- | --- |
| -s | 退出 4，标记与输出文件均未创建 |
| --capture=no | 同上 |
| --capture=sys | 同上 |
| --capture=tee-sys | 同上 |
| --log-cli-level=INFO | 同上 |
| -o log_cli=true | 同上 |
| --log-file 指向临时文件 | 同上，日志文件未创建 |
| -o log_file=临时路径 | 同上，日志文件未创建 |
| --junitxml 指向临时文件 | 同上，XML 文件未创建 |
| -o addopts 启用插件并指定 --capture=sys | 同上 |
| 实际临时 ini 文件设置 log_file | 退出 4，收集标记与日志均未创建 |
| 实际临时 ini 文件设置 log_cli=true | 退出 4，收集标记未创建 |

实际 ini 文件显式沿用项目插件和 pythonpath，确认有效 ini 路径也受到拒绝保护。--log-file 和 log_file 是本轮主 Agent 指出的独立文件输出边界，两种均已验证关闭。默认 warnings 汇总使用实际 warning 记录验证，消息脱敏后类别与文件行号仍保留。

## 5. 真实测试库保护及原 QA 联合场景

### 5.1 完整回归前后核对

连接前调用 validate_test_target(test_url, development_url)。开发配置只用于目标隔离校验，实际仅连接专用测试库。

在只读事务中确认 current_database/current_user 为 agent_demo_test/agent_test，schema_migrations 的版本和 checksum 与仓库 001/002 完全一致。预检成功后才启用真实库测试，输出仅为预检布尔值和 Session 行数。外围 harness 如发生异常仅输出异常类别，禁止原样输出连接异常。

实际预检 Session 为 0 行。119 项通过后再次读取版本/checksum 和完整 Session 行集，前后快照相等，Session 仍为 0。原 PG 用例继续采用临时失败 DDL 事务回滚和随机测试用户清理。本轮未执行迁移升级。

### 5.2 三项外部补测

确认外部合成探针保护加载有效后，使用第 2 节默认捕获命令运行原临时三项测试。三个原场景均通过。

- 真实 PG 加正式 create_app/lifespan、Service、SessionRepository、Runtime、编译主图及 Uvicorn TCP。模型仅替换为受控 Gateway。断开后订阅解绑、任务继续、状态可查询；去重不重执、续接保 Task、production 三入口拒绝和查询不建 Session 的断言保留。
- 实际最终 Saver aput 故障保留已知模型次数、usage_complete=false、无最终 token，并在 Run TTL 后继续阻塞 uncertain。
- 普通结算禁止 END 后额外 aupdate_state，验证同 Task 用量继承、用户等待排除和最终 Checkpoint 对齐。

联合场景的 finally 仍按确切 dev-user 和随机 conversation 删除自身 Session，随后断言完整行集恢复为 before。本轮该断言及池/HTTP 客户端关闭断言全部通过。原三项文件及被测代码未修改。

## 6. 结论、回归问题和支持边界

本轮未发现新增的已确认产品回归或需退回修复的问题。QA-EXEC-01 中标准测试异常、收集异常、kwargs/--showlocals、捕获 stdout/stderr/log、标准 warnings 汇总均通过虚构凭据失败验证。不支持的捕获、实时日志、JUnit 及 pytest 文件日志在收集前明确拒绝，失败类型、位置和退出状态保持。

建议主 Agent 关闭上述已验证入口的未来回显实现问题，结合原 D02 矩阵及本轮 119+3 有效结果完成阶段验收复核。

保护针对项目插件加载后的已配置数据库值和已验证表示，支持 pytest 标准报告边界。主动禁用插件、绕过项目配置、插件加载前输出、未知临时秘密、未验证的额外编码、第三方输出/报告插件、进程外输出及测试自行写文件仍需按各自路径另行验证。本轮拒绝检查覆盖 pytest 内置的已声明不支持后端。

P3-01 六份设计示例 format 仍按原独立 QA 和主 Agent 决定追踪。本轮执行 Python 的 lint/format 已通过，未为文档遗留扩大修改范围。

用户暂缓更换密码的决定继续有效。历史工具输出中的凭据暴露及密码复用保留为 RISK-02-CRED，本轮脱敏验证通过不改变这一遗留裁决。原始审计与先前 QA 报告保留。阶段正式状态和验收由主 Agent 维护。
