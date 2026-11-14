# 项目级原生子 Agent

2026-11-13配置并验证；仅角色配置与最小只读验证，未启动05，未提交或推送Git。04实际已ACCEPTED且归档，交付ab30f12、回执6c72169，原任务开头的VERIFIED/未归档描述已过时。

## 实际配置

[config.toml](config.toml)仅设置 `agents.enabled=true`、`agents.max_concurrent_threads_per_session=2`，上限不包含主Agent。角色从`agents/*.toml`自动发现，未增加旧式`agents.<name>.config_file`注册或额外角色，未覆盖模型、供应商、权限或个人设置。

| 文件 | name及职责 |
| --- | --- |
| [implementer.toml](agents/implementer.toml) | `implementer`：指定Task实现、自测、QA清单定向修复；交付修改位置、实现摘要、实测命令/结果、未闭环问题。 |
| [qa.toml](agents/qa.toml) | `qa`：独立查业务边界、幂等、并发、恢复和必要回归；交付PASS/FAIL、问题严重程度、位置/复现、实测及风险，默认不改业务。 |

两个文件只包含`name`、`description`和`developer_instructions`；完整实际内容以文件为准，不复制AGENTS。主Agent负责拆分/派发、审查与QA裁决、Git集成；阶段转换须用户批准。默认Implementer→QA串行，FAIL交回原Implementer再复测。支持时用`fork_turns="none"`，提供当前Task、必读文件、修改范围和验收标准；不继承无关历史，不连续查询运行状态，简单任务无需委派。

## 加载及运行验证

Desktop包26.1106.6628.0内置运行时为 **codex-cli 0.167.0-alpha.4.1**，位于该包的`app/resources/codex.exe`。本轮使用此可执行文件从项目根启动全新原生`exec --strict-config --json --sandbox read-only`会话；没有开发Bridge或编排框架。实际`debug prompt-input`工具schema已列出implementer/qa，描述与TOML精确匹配，spawn参数含agent_type/fork_turns。

| 显式原生调用 | 子会话UUID与实际agent_role | 真实只读命令结果 |
| --- | --- | --- |
| `agent_type="implementer", fork_turns="none"` | `01a1d3e6-d212-7391-9bdf-c98e3be738e8`，`implementer` | `git rev-parse --short HEAD` → `6c72169`，exit0 |
| `agent_type="qa", fork_turns="none"` | `01a1d3e7-1fe5-7381-959c-a60af6f87bd0`，`qa` | `git branch --show-current` → `real-model-chat`，exit0 |

父会话`01a1d3e6-9f19-7412-8946-6fb20db9dfbb`按顺序派发。已交叉核对原生spawn实参、会话元数据agent_role、实际exec工具输入/exit0输出及角色特定交付栏目，未以默认Agent或模型自述替代。[精简原生证据](validation-evidence.json)保留角色/调用/命令/权限和配置摘要，不包含凭据或完整上下文。原始本轮日志在本机临时目录`C:/Users/15294/AppData/Local/Temp/codex-project-agents-0vzhvol8`；仅查询本轮原生会话元数据，没有调用旧Session Bridge。

先做过一次ephemeral最小验证，结果成功但未保存可审计的角色元数据，因此另做上述有原生日志的最小验证。最终会话exit0，两种角色均真实加载并调用。运行时出现模型目录/插件目录刷新、遥测、PowerShell快照及一次流重试等非致命诊断，未阻断验证；未为这些诊断升级、改个人配置或更换模型。

## 兼容性与权限边界

- PATH中的npm CLI仍为 **0.144.4**，实际报错`invalid type: boolean true, expected struct AgentRoleToml`，不支持本项目当前的agents.enabled结构。本轮未升级或改PATH；使用上述Desktop内置runtime或另行升级后再用CLI，不能将旧CLI视为验证通过。
- 本聊天启动时的工具schema不含agent_type，创建文件不会改写已经暴露的工具参数。**新Desktop原生会话已验证可用；正式使用前新开项目聊天加载配置**，核对工具确实提供implementer/qa；不伪装当前旧schema已热加载。
- QA只读提示属于行为约束。角色继承父会话权限，不能自行配置独立只读沙盒；本次验证的父、子turn_context均为read-only，只证明本轮继承了只读权限。正式父会话若允许写入，QA也有该底层能力，须遵守只读职责。
- 没有运行项目测试、访问项目PostgreSQL、修改业务/迁移/冻结设计或执行Git暂存/提交/推送/重置；原六项暂缓差异保留。配置已具备在上述Desktop新会话启用的条件，05仍等用户审核及后续指令。

配置结构和权限边界参考[官方Subagents说明](https://learn.chatgpt.com/docs/agent-configuration/subagents)，实际兼容性以本轮安装版本解析和原生运行结果为准。
