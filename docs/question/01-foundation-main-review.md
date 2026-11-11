# 01 主 Agent QA 复核与协调记录

复核日期为 2026-11-10。当前阶段状态为 **ACCEPTED**，用户已正式批准01验收及进入02，Baseline/Delivery两提交已推送并核实远端。P2-01 已关闭，P3-02 已关闭，P3-01 保留为非阻塞遗留。02当前为NOT_STARTED（已许可、待人工启动）。以下各节保留历次复核记录，最新处理见第 8 节。

## 1. 依据与本轮证据

已读取 AGENTS.md、README、项目定位、唯一路线图、D01 全文及末尾开发交付报告、[独立 QA 报告](01-foundation-acceptance.md)，并检查对应请求、配置、仓储、生命周期、迁移及测试代码。

- 显式启用 agent_demo_test 运行完整 pytest，结果为 **78 passed in 5.68s**。使用项目 `.venv`，测试临时迁移失败回滚及 Session 数据清理由已有测试负责。
- 直接构造 ChatRequest 及 Settings，二者均接受含 NUL 的标识。真实测试库参数 `SELECT %s::text` 抛出 DataError，信息为 PostgreSQL text fields cannot contain NUL (0x00) bytes。
- TestClient 使用真实 lifespan、模型客户端初始化及测试库，SelectorEventLoop 下 preparation_ready=True。提交 QA 原始 NUL 请求得到 **500、text/plain**，与独立 QA 结论一致。本探针未调用模型网络，非法标识未成功写入。
- 第一次 HTTP 探针使用 TestClient 默认 Windows loop，数据库初始化退化、返回 503，该次不作为缺陷复现证据。改用 README 已要求的 Selector loop 后得到上述有效复现。
- `pip check` 通过。全仓 Ruff lint 仍为 supervisor prompt 第 8 行 E501。format 仍有 8 个文件，已格式化数量为 91，较 QA 的 89 增加两个报告文件，不代表新增格式缺陷。

真实模型、空库首次初始化、bootstrap 幂等重跑及容器 Volume 重启在本轮未重验。真实模型采用开发报告及独立 QA 各自成功的证据。初始化/Volume 采用 D01 开发报告的既有证据，并明确独立 QA 未重复该操作。D01 第 8 节要求的双库、重跑、回滚和 Session 持久性已有真实验证，无需仅为重复证据重建现有环境。

## 2. 问题裁决与负责人

| 编号 | 独立判断 | 处理决定 | 负责人及关闭条件 |
| --- | --- | --- | --- |
| P2-01 | 真实 Bug，稳定复现，属于 01 外部输入边界遗漏，将影响 02 复用入口 | 阻塞阶段验收，保持 P2，修复输入校验并补回归，无需修改冻结设计 | 修复会话实施，独立测试会话验证 422、未进入准备层、正常请求仍为预期 JSON 503 |
| P3-01 | 真实工程遗留，与交付前已有文件一致，未发现运行影响 | 本阶段接受为非阻塞遗留，不安排全仓格式化 | 主 Agent 追踪。02 修改旧 Runtime/Response/Prompt 时处理相应代码，06 最终交付核对剩余文档示例及全仓检查。后续负责人需随任务人工传递，本记录不代表已通知 |
| P3-02 | 真实文档状态冲突 | 主 Agent 本轮修正定位页首、第 2 节历史基线标签、第 8 节旧状态及路线图当前状态，同步 README/QA 导航 | 已完成文档修正，历史审查报告与轮次记录保留 |

P2-01 根因是 Identifier 只有长度限制，名单校验也没有排除 NUL。数据库层按既有契约传播编程/参数错误，修复应集中在外部输入及配置边界。当前证据支持服务端错误，不上调为数据泄露或数据损坏问题。

## 3. D01 第 8 节验收矩阵（首次复核）

| 门禁 | 主 Agent 判断 | 证据及待办 |
| --- | --- | --- |
| 工程/配置 | 通过，保留 P3-01 | HTTP/配置测试和 pip check 通过，格式遗留明确登记 |
| PG 环境 | 通过，保留证据边界 | 真实双库、固定版本、迁移校验、重跑/回滚由开发和 QA 报告支持，本轮真实库测试再次通过 |
| 生命周期 | 通过 | 开发及 QA 正常/失败释放证据，本轮 Selector lifespan 实测成功 |
| Session | 通过 | 真 PG 五组各 12 路并发、隔离、碰撞回滚、重开再次通过，跨进程采用 QA 证据 |
| 请求准备边界 | 待修复 | context/options、单次解析及 Task 边界成立，NUL 输入返回 500 |
| 模型网关 | 通过 | Gateway 受控测试通过，正式节点/Run 接线归 02 |
| 真实模型 | 通过 | 开发与 QA 均分别验证文本及结构化，当前轮次未付费重跑 |
| 演示身份/隔离 | 主要行为通过，名单校验随 P2 修正 | 名单、production 和 scope 测试通过，名单 NUL 边界待处理 |
| 文档 | 当前状态已修正 | 当前入口明确 NEEDS_FIX，原始报告保留，独立环境重建边界明确 |

六个 Task 的实现状态均为 IMPLEMENTED。1.3.2 的输入边界存在 P2，1.1.2 配置名单应同步修正，相关 Task 修复前不能声明验证闭环。阶段整体保持 NEEDS_FIX。

## 4. 后续闭环

1. 用户人工转交 [01 修复会话完整任务](../resume/01-foundation-fix-task.md)，实际启动修复后再记录 FIXING。修复会话将修复记录整理到 `docs/resume/record/01-foundation-fix-report.md`。
2. 修复报告返回后，主 Agent 核对差异、原始问题及开发自测证据。
3. 再生成独立 QA 回归任务，人工转交后记录 TESTING。至少核对原 NUL 真实 HTTP 路径、配置拒绝、正常准备路径与完整现有回归。
4. 独立回归无阻塞问题后记录 VERIFIED，主 Agent 提交正式阶段验收报告及切换申请。用户批准前保持切换待定，Git 阶段归档在批准后执行。

首次复核时没有修复交付或独立回归通过证据。后续交付见第 6 节。

## 5. Git 与范围说明

当前分支为 `real-model-chat`，HEAD 为 `2dcf652`，origin 为 `https://github.com/white-thirteen/agent.git`。工作区混有先前 Graph/设计修改、01 交付及 QA 文档，Git 差异不能全部归为 01。未来归档须按 D01 文件清单及具体差异核对归属，归属不清时需进一步说明。.env 被忽略且未被跟踪。本轮只修改协调和状态 Markdown，Git HEAD 未改变。

用户本轮背景文字包含订单取消，Git 示例的 03～06 描述也与有效路线图名称不同。这些属于待对齐口径。本轮修复范围以明确要求遵循的冻结 V1/D01 为准，订单取消在有效定位文档中已移出 V1。若用户意图扩展范围，须单独确认；实际阶段名称和未来提交描述应对应有效路线图。

多 Agent 使用用户手动创建的独立会话，通过文件和人工传递协作。阶段内部 Task 按依赖连续实施，阶段切换须明确批准。本次用户指令优先于历史逐 Task 授权文字。

## 6. P2-01 修复交付复核

2026-11-10 用户带回 [修复报告](../resume/record/01-foundation-fix-report.md)。已核对实际 chat.py、config.py 及两个测试文件，修复集中于外部标识 NUL pattern 和名单 NUL 校验，无需调整冻结设计。新增回归覆盖两个请求标识的 422/prepare_chat 零调用、Unicode/空白规范化，以及名单拒绝及错误输入隐藏。与原始问题和修复任务对应，未发现需要退回修复的事项。

主 Agent 本轮实际运行受影响测试，结果为 **22 passed in 2.66s**，四个改动文件的 Ruff lint 通过、format 为 4 files already formatted。修复会话报告完整真实库回归为 82 passed，并记录真实 PG/ASGI 的 422、零准备调用、正常 JSON 503、实际 Session 及精确清理。本轮主 Agent 未重复完整真实库或 HTTP 探针，这些证据目前归属修复会话开发自测。

P2-01 状态为修复已交付、待独立回归，原问题保持待关闭。阶段从 NEEDS_FIX 更新为 IMPLEMENTED，独立回归实际启动后转 TESTING，通过并复核后才能转 VERIFIED。P3-01 继续按既定非阻塞遗留追踪，P3-02 当前文档已同步。下一步由用户人工转交 [独立 QA 回归任务](01-foundation-regression-task.md)。

## 7. 独立回归复核与问题关闭

2026-11-10 用户带回 [独立回归报告](01-foundation-regression-report.md)。主 Agent 已逐项核对原 P2-01、修复授权及开发报告。独立 QA 验证两个标识 NUL 请求 JSON 422、正确错误定位、prepare_chat 零调用、真实库零新增，同时合法请求实际持久绑定、Unicode/空白/长度及配置输入隐藏成立，证据满足原关闭条件。P2-01 正式关闭。P3-02 状态修正已由独立 QA 核对，正式关闭。未发现新增阻塞问题。

独立结果为受影响 22 passed、完整真实库 82 passed/0 failed/0 skipped、四文件 Ruff 通过。真实 PG/ASGI、精确清理和池及两种客户端释放通过。主 Agent 本轮审阅报告和当前 Git 状态，采用独立回归证据，未重复测试或外部资源操作。

阶段更新为 VERIFIED，正式验收建议见独立文件。P3-01 继续按第 2 节归属追踪。模型付费调用、独立 socket、bootstrap/Volume 本轮未重验，采用首次 QA 及 D01 已接受证据，保留原边界。用户正式批准前，ACCEPTED 和阶段切换保持待确认，02 为 NOT_STARTED。Git HEAD 仍为 2dcf652，当前工作区交付归属须在获批归档时逐项核对。

## 8. 用户验收、独立归档与02交接

用户已批准01验收，随后审核前序归档方案及两份独立快照验证，最终明确授权提交Git及进入下一环节。Baseline为 `f89db15efc9b38e88bfed6a725abde76575c6bae`，Delivery为 `cf3e763e96f290dad4bb011e778bbcdf7c6c81d6`，各45个变更路径。已正常推送到origin/real-model-chat并以ls-remote核实远端指向Delivery，提交父子关系通过核对。

快照验证Baseline55项、Delivery真实库82项通过，运行代码及测试与验收工作树一致。归档提交采用已验证快照，仅提案补入验证与授权记录，实际暂存完整树及289处链接/标题锚点检查通过。暂存区在提交后为空。

根AGENTS/README及本记录的最新协调说明和 [02执行任务](../02-agent-runtime-execution-task.md) 为归档后的交接增量，留待02阶段管理。先前5个状态文档的快照整理差异及3个旧文档路径删除、general.py暂缓状态均有记录，原业务代码与删除状态保留。归档回执位于 `D:/py/agent-project/archive-validation-20261110-01/git-archive-receipt.json`。

01标记ACCEPTED，02进入已许可、待人工启动状态。下一步由用户将整阶段任务文件交给独立执行会话，完成六Task后主Agent审核交付并安排独立QA。
