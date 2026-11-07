# Agent Backend 开发规范

## 1. 适用范围与协作方式

本文件适用于本仓库全部代码、测试与文档。用户在当前对话中的明确要求优先；
如子目录出现更具体的 `AGENTS.md`，在该目录内结合其规则执行。

- 修改前先查看现有实现、依赖和相关文档，不假定仓库为空，不覆盖用户正在进行的修改。
- 用户提供的架构总结是目标与讨论基础，不代表已经实现，也不自动授权执行其中所有任务。
- 围绕当前明确的任务推进，常规实现、可逆修复和必要验证无需反复确认。
- 大规模重构、破坏性操作或扩大业务范围前，说明影响并与用户对齐；已经明确授权的范围不重复确认。
- 遇到问题先结合实际代码定位原因，说明修改及其影响；不要只提供建议而留下已授权的修复。
- 先完成最小可运行闭环，再扩展架构；不为目录完整而增加无用抽象或复杂基础设施。

## 2. 项目目标与当前边界

目标是独立的 Python Agent Backend，后续由 Java 后端通过 HTTP/SSE 调用。
Java 负责用户身份、权限和传统业务，Python 负责 Agent 执行、工具、工作流和记忆。

当前已有 FastAPI 骨架、配置、日志、请求校验、Service/Runtime 边界与 SSE 适配。
模型、Graph、工具、持久化、审批和长期记忆尚未实现；对应文件中的职责说明不是功能实现。
当前事实以代码及 `docs/architecture.md` 为准，阶段文档保留该阶段的完成记录。

## 3. 环境与依赖

- 使用项目 `.venv`，当前基线为 Python 3.13.7；不要直接使用系统的裸 `pip` 安装项目依赖。
- 安装命令使用 `.\.venv\Scripts\python.exe -m pip ...`，运行和测试使用同一解释器。
- `requirements.in` 维护直接依赖；`requirements.txt` 记录已验证的解析版本，包含开发工具。
- 变更依赖时同步清单并验证兼容性；删除依赖时在干净环境确认，不能只依赖 `pip freeze`。
- LangChain、LangGraph 及相关库的 API 以实际安装版本为准，先检查本地签名、源码或官方文档。
- 不凭印象拼接 API，不为消除单个问题盲目升级全部依赖或切换 Python 版本。
- 配置集中在 `app/core/config.py`；示例更新到 `.env.example`，真实密钥不写入仓库、日志或文档。

## 4. 分层与依赖方向

主调用方向：`Route → Service → Runtime → Graph`。

| 模块 | 职责与边界 |
| --- | --- |
| `app/api` | HTTP 参数校验、依赖注入和响应，不实现 Agent 决策或数据库操作 |
| `app/services` | 创建请求上下文和 run_id，协调 Runtime、工作流及记忆 |
| `app/runtime` | 执行与恢复 Graph，将内部执行结果适配为公共事件，不依赖 HTTP Schema |
| `app/graph` | State、Reducer、节点、条件边与编译 |
| `app/agents` | Agent 类型、Prompt 与配置，按业务需要增加 |
| `app/tools` | 工具元数据、注册、发现、策略与实际执行 |
| `app/workflows` | 工作流业务状态、元数据与审批 |
| `app/memory` | 跨会话长期记忆读取、提取、去重和更新 |
| `app/infrastructure` | 数据库、Checkpointer 与 Store 的初始化和资源管理 |
| `app/streaming` | 对外 SSE 协议和序列化，不直接泄露 LangGraph 内部事件 |

应用级模型、连接池和 Graph 由生命周期管理；Graph 在启动时编译，不在每次请求中重编译。
单例 Service、Runtime、节点对象不保存用户的可变执行状态，请求状态经显式上下文或 State 传递。

## 5. State、ID 与持久化

- `user_id` 标识用户，`conversation_id` 标识逻辑会话，`workflow_id` 标识可管理工作流，
  `run_id` 标识一次执行，`thread_id` 标识 Checkpoint 线程；不得混用。
- 每次执行创建独立 run_id；恢复执行与业务 workflow 的关联在生命周期模块中明确处理。
- State 先定义每个字段的写入方和合并方式。消息使用消息专用 Reducer，其他字段按需覆盖或合并。
- 同一会话单活动 workflow、workflow 与 thread 的一对一映射是第一版目标，当前骨架没有实现该约束。
- Checkpointer 保存执行快照，Store 保存跨会话记忆，Workflow Repository 保存业务元数据。
- 不把全部聊天记录直接保存为长期记忆；记忆读写需要按用户隔离。
- interrupt 只在明确的安全中断点使用，不声称能够冻结任意运行中的 Python 代码。
- 恢复会重放部分节点时，应检查外部副作用与工具幂等性，不允许重复执行已审批的副作用。

## 6. 工具、身份与流式输出

- 工具先按 Agent 权限过滤，再进行渐进式披露；执行时仍需重新校验权限、参数和策略。
- 有副作用的工具明确超时、幂等及审批要求；审批绑定具体调用与参数，不能作为通用放行标记。
- 开发期可使用 Apifox 模拟身份；生产身份来自可信后端，并验证调用方和数据归属。
- 当前预留事件为 `token`、`status`、`tool_start`、`tool_end`、`approval_required`、`done`、`error`。
- 事件数据统一序列化；先于 SSE 响应头发生的问题使用合适的 HTTP 错误，开流后的问题使用事件协议。
- 处理流式异常、客户端断开、取消和资源释放；不要吞掉取消异常或在日志中输出密钥及完整敏感消息。
- 未实现能力明确返回不可用，不能用模拟成功结果替代；测试替身仅用于测试。

## 7. 验证与交付

涉及业务行为变更时，运行与改动有关的测试，重点覆盖请求隔离、错误路径和资源清理。
阶段完成时执行以下检查；没有新增问题时，不无意义地重复扩大测试范围。

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

纯文档修改检查事实、链接和示例一致性即可，不要求增加或重跑业务测试。
新增模型集成先使用可控替身验证，再在已配置的环境验证真实调用，不把付费外部请求放入默认测试。

交付时说明做了什么、验证结果、尚未实现或尚未验证的部分。
重要设计和阶段记录写入 `docs`，更新 README 导航；文档清楚区分“当前行为”和“计划行为”。
