# 前序 Baseline 与 01 Delivery 独立归档提案

日期为 2026-11-10。**本文件为待用户确认的归档方案**。用户已批准 01 正式验收及进入 02，随后明确要求先确认独立归档方案。Commit/Push 现等待本方案批准。本文不启动 02。

## 1. 已核查事实

当前分支为 real-model-chat，HEAD 为 `2dcf65293683e63faf99b75b8ea2630dba42db76`。本轮读取本地引用，main、real-model-chat 和 origin/main 均指向该提交，本轮未访问远程。暂存区为空，工作区共 85 个变更路径，为原 84 个路径加本提案。下表及第 9 节逐文件三方比较覆盖全部 85 个路径。

Git HEAD 仍为最初脚手架。D01 明确记录开发开始时已有 Graph/协议/Runtime 逻辑、55项初始测试及冻结设计。当前完整82项真实库回归已通过。这些事实能识别前序来源与当前依赖，但不能证明任意拆出的历史快照已经通过同一套测试。

已核实可读树对象 `cdbe5272159936163414f64335f864ce2b49aa86`，下文记为 C。来源为本地引用 `refs/codex/turn-diffs/checkpoints/c2b208c229a008bb9930cbf1cf8e2f0b/a3c1e437b46c393fd877c133fc08ed13/1794231962474/14b9cd48-e3a4-40aa-b48b-b1bf85b68616`。`git cat-file -t` 返回 tree，`git for-each-ref` 显示该引用直接指向 C。它不是已完成的正式 Baseline Commit，没有提交消息、父提交或可据以认定阶段状态的提交时间。

原提案“无法取得历史原件”“没有完整旧 main 快照”的判断有误，现修正。C 中 main 已包含 ChatOpenAI 创建、Supervisor Graph 编译、Runtime(graph) 及 Service 注入。C 的 Runtime 与当前工作树 W 仅相差 RunLimits、RunUsage 两个数据类。HEAD 到 C 的 config.py 只有一行模型配置注释变化，属于前序模型装配说明。以上可按树对象与文件路径直接读取原件，详见第 5、9 节。

Baseline 改为以 C 保存的前序代码和设计原件为主要来源，再做本提案列明的归档指引和状态说明整理。D01 开工记录及 C 中 README/AGENTS 的最终确认记录支持其前序归属；C 本身只能证明文件内容存在。拟归档树对 C 的偏离必须逐项留痕，不称为 C 的原样恢复。82 项通过属于当前完整工作树，两个拆分快照的独立验证仍待方案批准后执行。

## 2. 完整归属清单

B 表示 Baseline Commit，D 表示 01 Delivery Commit，分片B+D 表示两个提交分别保存该文件的不同增量，暂缓表示本次两提交均不纳入。表中的“必需”区分当前运行依赖、测试验收和设计追溯。

Graph/类型/映射在当前已通过的协议、State、编译图测试及应用编译路径中有证据，但不能把每个Prompt/节点都标成真实模型专项通过。Prompt E501、Response旧格式问题继续追踪。文档“已确认”仅指设计审阅，不代表02～06实现通过。配置、模型、PG的细分覆盖以首次QA和独立回归矩阵为准。

| 文件路径 | Git状态 | 所属模块 | 01是否必需 | 已有验证情况 | 与01无关或混合的修改 | 拟归档 |
| --- | --- | --- | --- | --- | --- | --- |
| `.env.example` | M | 01配置/依赖声明 | 运行/重建需要 | 配置回归及已有pip check，无依赖版本变更 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `AGENTS.md` | M | 开发规范 | 协作必需 | 人工核对，非运行测试 | 冻结规范与01/QA/协调状态混合 | 分片B+D |
| `README.md` | M | 导航与运行说明 | 交付必需 | 当前说明经QA核对，拆分导航待验 | 前序导航/历史记录与01操作及QA入口混合 | 分片B+D |
| `app/agents/prompts/__init__.py` | M | Prompt包说明 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/agents/types.py` | M | Agent/Task类型 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/api/dependencies.py` | M | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/api/routes/agent.py` | M | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/api/schemas/chat.py` | M | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/core/config.py` | M | 前序模型说明及01配置 | 是 | C原件可读，当前配置回归通过 | HEAD→C注释归B，C→W配置/校验归D | 分片B+D |
| `app/core/errors.py` | M | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/core/logging.py` | M | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/graph/builder.py` | M | 主图编译 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/nodes/__init__.py` | M | Graph节点包说明 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/router.py` | M | Graph路由 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/state.py` | M | Graph State | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/infrastructure/postgres.py` | M | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/main.py` | M | 前序装配及01资源生命周期 | 是 | C原件含模型/Graph装配，当前集成已验 | HEAD→C模型装配归B，C→W资源/准备层归D | 分片B+D |
| `app/runtime/agent_runtime.py` | M | Runtime | 是 | 当前工作树集成通过，拆分快照待验 | 前序执行逻辑与01 RunLimits/RunUsage 混合 | 分片B+D |
| `app/services/agent_service.py` | M | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/01-environment-and-scaffold.md` | D | 历史归档入口 | 链接完整性必需 | C/W均删除，拟指引尚待验证 | B改为保留简短指引，避免保留HEAD旧架构文档后断链 | B |
| `docs/02-real-model-chat.md` | D | 旧模型接线文档删除 | 否 | 未发现逐字节相同归档，未证明已完整迁移 | 既有删除归属待确认，建议保留工作区状态且暂不提交 | 暂缓 |
| `docs/architecture.md` | D | 旧架构文档删除 | 否 | 未发现逐字节相同归档，未证明已完整迁移 | 既有删除归属待确认，建议保留工作区状态且暂不提交 | 暂缓 |
| `requirements.in` | M | 01配置/依赖声明 | 运行/重建需要 | 配置回归及已有pip check，无依赖版本变更 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `tests/test_application.py` | M | 01测试 | 验收需要 | 82项真实库回归包含 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/agents/prompts/general.py` | ?? | 旧通用Prompt | 否 | 无引用，无专属验证证据 | 与01无关的遗留候选，建议暂不归档 | 暂缓 |
| `app/agents/prompts/supervisor.py` | ?? | Supervisor Prompt | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/contracts.py` | ?? | Graph协议 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/nodes/clarification.py` | ?? | 澄清节点 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/nodes/response.py` | ?? | 公共回复节点 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/nodes/result_aggregator.py` | ?? | 结果汇总 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/nodes/specialist.py` | ?? | 专业图wrapper | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/nodes/supervisor.py` | ?? | Supervisor节点 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/graph/transfers.py` | ?? | 父子图映射 | 是（编译/import链；包说明仅随模块） | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `app/infrastructure/model.py` | ?? | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/infrastructure/sessions.py` | ?? | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/runtime/context.py` | ?? | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `app/runtime/model_gateway.py` | ?? | 01资源/API/准备层 | 是 | 82项真实库回归及QA集成证据 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `compose.yaml` | ?? | 01环境/迁移/显式验证 | 配置场景需要 | 实际环境证据见D01/QA，bootstrap及Volume本轮未重验 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/01-foundation-detailed-design.md` | ?? | D01设计及交付 | 验收必需 | 冻结设计已确认，交付记录经QA审查 | 前序设计正文与01实施记录/Task状态/交付报告混合 | 分片B+D |
| `docs/02-agent-runtime-detailed-design.md` | ?? | 冻结设计/协议参考 | 设计交接需要，非运行依赖 | 设计已确认，后续阶段实现未验收 | 是，前序设计成果 | B |
| `docs/03-tool-governance-detailed-design.md` | ?? | 冻结设计/协议参考 | 设计交接需要，非运行依赖 | 设计已确认，后续阶段实现未验收 | 是，前序设计成果 | B |
| `docs/04-hitl-checkpoint-refund-detailed-design.md` | ?? | 冻结设计/协议参考 | 设计交接需要，非运行依赖 | 设计已确认，后续阶段实现未验收 | 是，前序设计成果 | B |
| `docs/05-rag-memory-detailed-design.md` | ?? | 冻结设计/协议参考 | 设计交接需要，非运行依赖 | 设计已确认，后续阶段实现未验收 | 是，前序设计成果 | B |
| `docs/06-integration-and-final-delivery-detailed-design.md` | ?? | 冻结设计/协议参考 | 设计交接需要，非运行依赖 | 设计已确认，后续阶段实现未验收 | 是，前序设计成果 | B |
| `docs/agent-engine-demo-plan.md` | ?? | 权威定位设计 | 设计必需 | 已确认设计，当前状态经QA核对 | 前序冻结设计与当前阶段状态修正混合 | 分片B+D |
| `docs/development-roadmap.md` | ?? | 权威路线图 | 设计必需 | 已确认设计，当前状态经QA核对 | 前序冻结路线图与01实施/QA进度混合 | 分片B+D |
| `docs/graph-protocol.md` | ?? | 冻结设计/协议参考 | 设计交接需要，非运行依赖 | 设计已确认，后续阶段实现未验收 | 是，前序设计成果 | B |
| `docs/history/01-1-engineering-and-architecture-baseline-plan.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/01-environment-and-scaffold.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/01-stage-detailed-design.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/02-stage-detailed-design.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/03-stage-detailed-design.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/03-stage-execution-plan.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/04-1-order-service-design.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/04-2-tool-registry-design.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/04-3-tool-execution-design.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/04-4-order-agent-design.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/04-stage-execution-plan.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/README.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/history/development-roadmap-commerce-history.md` | ?? | 历史设计归档 | 否（追溯用途） | 历史/归档审阅，不是功能QA | 是，前序资料与归档 | B |
| `docs/question/01-foundation-acceptance.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/question/01-foundation-main-review.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/question/01-foundation-regression-report.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/question/01-foundation-regression-task.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/question/01-foundation-stage-acceptance.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/question/01-git-archive-proposal.md` | ?? | 归档协调提案 | 审计需要 | 本轮三方核查，待用户批准 | 本提案本身归D | D |
| `docs/question/README.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/resume/01-foundation-fix-task.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/resume/README.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/resume/record/01-foundation-fix-report.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `docs/resume/record/README.md` | ?? | 01 QA/修复/协调记录 | 交付追溯需要 | 报告已复核/文档链接检查，非新增运行功能 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `migrations/001_sessions.sql` | ?? | 01环境/迁移/显式验证 | 配置场景需要 | 实际环境证据见D01/QA，bootstrap及Volume本轮未重验 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `migrations/002_deferred_thread_uniqueness.sql` | ?? | 01环境/迁移/显式验证 | 配置场景需要 | 实际环境证据见D01/QA，bootstrap及Volume本轮未重验 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `scripts/__init__.py` | ?? | 01环境/迁移/显式验证 | 配置场景需要 | 实际环境证据见D01/QA，bootstrap及Volume本轮未重验 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `scripts/check_model.py` | ?? | 01环境/迁移/显式验证 | 配置场景需要 | 实际环境证据见D01/QA，bootstrap及Volume本轮未重验 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `scripts/init_databases.py` | ?? | 01环境/迁移/显式验证 | 配置场景需要 | 实际环境证据见D01/QA，bootstrap及Volume本轮未重验 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `scripts/migrate.py` | ?? | 01环境/迁移/显式验证 | 配置场景需要 | 实际环境证据见D01/QA，bootstrap及Volume本轮未重验 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `tests/test_agent_types.py` | ?? | 类型测试 | 测试验收需要 | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `tests/test_config.py` | ?? | 01测试 | 验收需要 | 82项真实库回归包含 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `tests/test_demo_identity.py` | ?? | 01测试 | 验收需要 | 82项真实库回归包含 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `tests/test_graph_protocol.py` | ?? | 协议及编译图测试 | 测试验收需要 | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `tests/test_graph_state.py` | ?? | State测试 | 测试验收需要 | 当前82项回归包含；覆盖强度见正文 | 是，前序工程成果 | B |
| `tests/test_model_gateway.py` | ?? | 01测试 | 验收需要 | 82项真实库回归包含 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `tests/test_postgres.py` | ?? | 01测试 | 验收需要 | 82项真实库回归包含 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |
| `tests/test_resources.py` | ?? | 01测试 | 验收需要 | 82项真实库回归包含 | 未发现额外前序业务变更，当前diff归01或协调记录 | D |

## 3. Baseline Commit 完整文件清单

建议提交说明为 `Establish Baseline - Supervisor Graph and Frozen Design`。共 45 个变更路径，含 8 个共享路径。代码取 C 原件，文档按第 5 节逐处处理，旧 01 路径采用第 6 节指引内容。文档设计确认与实现验证分别记录。

- `AGENTS.md`，仅前序片段
- `README.md`，仅前序片段
- `app/agents/prompts/__init__.py`
- `app/agents/types.py`
- `app/core/config.py`，C原件，前序模型配置注释
- `app/graph/builder.py`
- `app/graph/nodes/__init__.py`
- `app/graph/router.py`
- `app/graph/state.py`
- `app/main.py`，C原件，前序模型/Graph装配
- `app/runtime/agent_runtime.py`，仅前序片段
- `docs/01-environment-and-scaffold.md`，保留路径并替换为历史归档指引
- `app/agents/prompts/supervisor.py`
- `app/graph/contracts.py`
- `app/graph/nodes/clarification.py`
- `app/graph/nodes/response.py`
- `app/graph/nodes/result_aggregator.py`
- `app/graph/nodes/specialist.py`
- `app/graph/nodes/supervisor.py`
- `app/graph/transfers.py`
- `docs/01-foundation-detailed-design.md`，仅前序片段
- `docs/02-agent-runtime-detailed-design.md`
- `docs/03-tool-governance-detailed-design.md`
- `docs/04-hitl-checkpoint-refund-detailed-design.md`
- `docs/05-rag-memory-detailed-design.md`
- `docs/06-integration-and-final-delivery-detailed-design.md`
- `docs/agent-engine-demo-plan.md`，仅前序片段
- `docs/development-roadmap.md`，仅前序片段
- `docs/graph-protocol.md`
- `docs/history/01-1-engineering-and-architecture-baseline-plan.md`
- `docs/history/01-environment-and-scaffold.md`
- `docs/history/01-stage-detailed-design.md`
- `docs/history/02-stage-detailed-design.md`
- `docs/history/03-stage-detailed-design.md`
- `docs/history/03-stage-execution-plan.md`
- `docs/history/04-1-order-service-design.md`
- `docs/history/04-2-tool-registry-design.md`
- `docs/history/04-3-tool-execution-design.md`
- `docs/history/04-4-order-agent-design.md`
- `docs/history/04-stage-execution-plan.md`
- `docs/history/README.md`
- `docs/history/development-roadmap-commerce-history.md`
- `tests/test_agent_types.py`
- `tests/test_graph_protocol.py`
- `tests/test_graph_state.py`

## 4. 01 Delivery Commit 完整文件清单

建议提交说明为 `Complete Phase 01 - Foundation and Environment`。共 45 个变更路径，以 Baseline 为直接父提交，以下 8 个共享文件保存01增量，其余保存当前01交付内容。

- `.env.example`
- `AGENTS.md`，仅01/验收/协调增量
- `README.md`，仅01/验收/协调增量
- `app/api/dependencies.py`
- `app/api/routes/agent.py`
- `app/api/schemas/chat.py`
- `app/core/config.py`，C→W的01配置/校验增量
- `app/core/errors.py`
- `app/core/logging.py`
- `app/infrastructure/postgres.py`
- `app/main.py`，C→W的01生命周期/准备层增量
- `app/runtime/agent_runtime.py`，仅01/验收/协调增量
- `app/services/agent_service.py`
- `requirements.in`
- `tests/test_application.py`
- `app/infrastructure/model.py`
- `app/infrastructure/sessions.py`
- `app/runtime/context.py`
- `app/runtime/model_gateway.py`
- `compose.yaml`
- `docs/01-foundation-detailed-design.md`，仅01/验收/协调增量
- `docs/agent-engine-demo-plan.md`，仅01/验收/协调增量
- `docs/development-roadmap.md`，仅01/验收/协调增量
- `docs/question/01-foundation-acceptance.md`
- `docs/question/01-foundation-main-review.md`
- `docs/question/01-foundation-regression-report.md`
- `docs/question/01-foundation-regression-task.md`
- `docs/question/01-foundation-stage-acceptance.md`
- `docs/question/README.md`
- `docs/resume/01-foundation-fix-task.md`
- `docs/resume/README.md`
- `docs/resume/record/01-foundation-fix-report.md`
- `docs/resume/record/README.md`
- `migrations/001_sessions.sql`
- `migrations/002_deferred_thread_uniqueness.sql`
- `scripts/__init__.py`
- `scripts/check_model.py`
- `scripts/init_databases.py`
- `scripts/migrate.py`
- `tests/test_config.py`
- `tests/test_demo_identity.py`
- `tests/test_model_gateway.py`
- `tests/test_postgres.py`
- `tests/test_resources.py`
- `docs/question/01-git-archive-proposal.md`，本方案及批准后的归档记录，本轮仅修订此文件。

## 5. 八个共享路径与准确版本边界

H 为 HEAD，C 为第 1 节检查点，W 为本轮核查开始时的工作树。代码文件按完整 blob 取版本，避免手工拼接已保存的旧实现。对文本比较先统一 CRLF/LF，第 9 节同时列出原始 blob 标识及 W 的 SHA-256 前缀。

### 5.1 三个代码文件

- `app/main.py` 的 B 版本直接取 `C:app/main.py`。保留 lifespan 中 `if settings.model_name and settings.model_api_key`、局部 ChatOpenAI import/构造、`build_supervisor_graph(model)`、`AgentRuntime(graph)`、`AgentService(runtime)`，以及旧 AgentNotReadyError handler 和 health。D 版本以 W 为准。C→W 的 AsyncExitStack、open_pool/schema 检查、SessionRepository、model_resources/Gateway、服务准备层和资源状态、PublicError handler/production 门禁整体归 D。
- `app/runtime/agent_runtime.py` 的 B 版本直接取 C 原件。C→W 只有 logger 定义之后、AgentContext 之前插入的两个 `@dataclass(frozen=True, slots=True)` 类。`RunLimits(active_timeout_seconds, max_tool_calls)` 和 `RunUsage(tool_calls=0, active_elapsed_ms=0)` 连同其说明归 D，其余旧执行代码没有变化。D 版本取 W。
- `app/core/config.py` 的 B 版本直接取 C 原件。H→C 仅把 `# Reserved for model and persistence implementation; not used at startup yet.` 换为 `# Model settings enable the Supervisor graph; database settings remain reserved.`，该变化与 C 的模型装配对应，归 B。C→W 的注释移除、新增 import、app_name 默认值、hide_input_in_errors、测试库/连接池/次数/期限/名单配置、URL/名单/NUL/池边界验证、model_configured 属性均归 D。D 版本取 W。

### 5.2 AGENTS 与 README

- `AGENTS.md` 的 B 版本取 C 全文，其第 2 节和末尾“逻辑设计阶段正式收尾记录”已记载最终设计确认。C→W 只在标题后加入“最新实施状态”块，包含01交付、QA/人工会话协作及resume目录规则，此整块归 D。历史规范正文保留。
- `README.md` 的 B 版本以 C 全文为原件。完整保留“本地运行（PowerShell）”的 uvicorn 无PG loop命令、“重建环境”“验证”、含 `workflow_id` 的旧 ChatRequest JSON、模型齐全时 Supervisor/SSE 与未配置503说明，以及全部有效设计/history导航。不能将 W 的准备层请求或 Selector loop 命令提前放入 B。
- B README 第 5 行最终设计确认段后拟补一段明确的归档说明，声明其他设计文档中的“待冻结/纯设计”状态是原件保留的设计轮次文字，以本文及 AGENTS 的最终收尾记录为准。B 的“开发文档”导航补入旧01归档入口说明，以及两个暂缓删除的旧文档的历史适用范围。这些是依据既有记录新增的归档注释，不称为 C 原文。
- D README 以 W 全文为基准，保留01真实PG/模型/配置/Schema/准备层运行说明、QA/修复导航及历史记录。新增同样的旧文档历史说明，并将页首当前状态更新为“01已获用户正式验收，Git归档待完成，02待用户启动”。其余更改均为 C→W 已验收的01增量。B 的旧请求示例在 D 由现有最终Schema示例替换，这是阶段行为变化。

### 5.3 定位、路线图与 D01 的分散状态

以下 C/W 行号仅用于本轮定位，形成快照时使用章节和整段文本匹配，防止行偏移。正文业务契约以 C 原件和已确认记录为准。

| 路径及定位 | C→W 实际变化 | B 版本处置 | D 版本处置 |
| --- | --- | --- | --- |
| 定位文档第3行 | 待冻结改为实施/QA/VERIFIED状态 | 依据 C README 第5行、AGENTS第2节及最终收尾，整理为设计已确认、Task尚待实施授权的状态段 | 使用W实施/QA事实，页首补充本会话用户正式批准及Git待归档状态 |
| 定位文档第2节标题，第17行 | 添加“设计时历史基线” | 采用该标签，仅说明原评估所属历史语境，记录为整理文字 | 保留标签 |
| 定位文档第8节末段，第166行 | 待冻结改为当前状态引用 | 替换为“六阶段详细设计已获最终确认，实施另行授权，历史轮次待冻结文字仅追溯”，引用README/AGENTS现有收尾记录 | 使用W文字，实施状态指向D协调记录 |
| 定位文档第9节及后续修订 | C/W相同，仍有当轮“等待设计/冻结”描述 | 历史记录保留，当前状态由页首与最终确认说明覆盖 | 同样保留历史语境，避免据历史段落倒退当前进度 |
| 路线图第3行 | 待冻结改01实施及002说明 | 整理为设计已确认、实施待授权 | W事实加正式验收/归档待完成说明 |
| 路线图第24行 | 全部未来改01已有实测 | 保留C“所有下列测试/命令均为未来执行” | 保留W已实施与未来阶段的区分 |
| 路线图01摘要，第30行 | 六Task未实施改已实施及78项结果 | 仅将设计状态改为已确认，保留未实施及授权边界 | 保留78项为首次交付历史证据，在摘要标明后续独立回归82项及正式验收结果 |
| 路线图第4节标题及第189行 | 当前设计整改改01 VERIFIED | B保留章节结构，当前段明确设计已确认、无实施结果 | D以W记录为基准，补用户已批准01、Git归档待完成、02尚未启动 |
| 路线图各阶段表、统一标准、第3节及设计修订记录 | C/W其余内容无变化 | 按C保留冻结Task/依赖及历史记录 | 同样保留，不把后续设计表写成已实现 |
| D01第3行→W第3～11行 | 旧状态替换为正式开发记录/初始55项/环境事实 | B使用C，不含开发记录，当前状态段依确认记录整理为设计已确认、实施待授权 | W顶部开发记录整体归D，另标明其为2026-11-09开发过程历史记录，新增当前正式验收状态 |
| D01第1节第15行、8.3末段C第819行 | C/W主体仍沿用纯设计/待冻结语境 | 按设计最终确认记录修正当前冻结口径，保留未来实施/资源门禁要求，标注依据来源 | D保留设计规范，明确该段为设计时实施边界，当前实施以交付及QA记录为准 |
| D01第11节表，C第872～877行/W第880～885行 | 六Task设计待冻结/未开始改已实施/验证及002批准 | B设计列整理为“已最终确认”，实现为未开始、验证为未执行，真实联调按C；无002修正 | W实施/验证表整体归D，002另获批准按实施记录关联，不回填为原设计决策 |
| D01 C末尾之后→W第920行起 | Settings进度、PG进度、正式交付报告新增 | B不包含这些新增段 | 全部归D，包括001/002、并发故障、获批修正、真实模型/PG验证、遗留及02交接 |
| D01第2节历史实现评估、其余设计Task与历史修订 | 原件主体保留 | 作为设计时事实/规范保留，冻结待定旧记录由当前状态说明覆盖 | 不把历史评估当当前实现，当前结论指向正式交付及QA闭环 |

D01 的 Baseline 不含002 SQL、schema=2、DEFERRABLE修正或其验证。全部属于01实施时另获批准的变更，只进 Delivery。D01原设计里的唯一性、迁移和未来验收约束仍按原件保留。

### 5.4 D02～D06 与确认依据

C 中 D01～D06页首仍有“等待最终冻结”，定位页首和路线图第4节也有旧状态。C 中 `README.md` 第5行及“逻辑设计阶段正式收尾记录”（第119～121行），`AGENTS.md` 第2节（第34行）及末尾正式收尾（第192～194行）明确记载六阶段、18环节、36Task、D01～D06和跨阶段契约已获最终确认，并说明覆盖旧待冻结状态。当前用户提供的规范也保留该确认。以这些记录认定设计冻结，不能用检查点引用名或时间戳认定授权。

D02～D06 的 B 内容取 C 原件，与 W 内容在统一换行后相同。本方案保留其历史正文与旧状态原文，在 B README 的归档说明中逐个列明 D01～D06均适用最终确认覆盖规则。它们在两个提交中相同，不计入共享路径。此方式保留历史原件，同时有明确生效记录。不将这些设计状态整理成后续阶段已开发或已授权。

## 6. 文档链接与三项暂缓处置

### 6.1 旧01路径改为保留历史指引

原提案删除旧01路径将使保留的 `H:docs/architecture.md` 第4行断链，问题属实。修订方案在 B 中保留该路径，内容拟为下列历史指引，D继承同一版本。

```markdown
# 历史环境搭建记录入口

本页保留旧文档链接。历史搭建记录见 [归档正文](history/01-environment-and-scaffold.md)。
旧记录仅供追溯，当前设计依据见 [有效路线图](development-roadmap.md)。
```

这是一份批准后拟新增的指引，C和W该路径均不存在，不能标为检查点原件。H版本将被指引替换，属于B中的修改而非删除。`docs/history/01-environment-and-scaffold.md` 在C已保存历史提示和相对链接修订，并与W一致。当前工作区旧01路径仍保持删除，本轮未创建实际指引。

### 6.2 暂缓三项的来源与影响

| 路径 | 来源/引用 | 内容迁移及验证证据 | 暂缓方案及影响 |
| --- | --- | --- | --- |
| app/agents/prompts/general.py | H无此文件，C已存在，与W一致；app/tests未发现引用 | 旧通用Prompt，仅凭文件存在不能证明有可用GeneralAgent；类型测试拒绝general，没有专项运行验证 | 两提交均不收录，保留工作区未跟踪文件，前序Supervisor运行不依赖它 |
| docs/02-real-model-chat.md 的删除 | H有原件，C和W均缺失；H architecture第5行引用 | H内容是旧第二步待开发计划，通用ModelNode架构；新D01/D02覆盖相关领域但不构成原文完整迁移证据，docs中未找到逐字节副本 | 两提交保留H文件原件，暂缓提交其删除。B/D README明确其仅为旧计划追溯，不作为当前路线或能力事实 |
| docs/architecture.md 的删除 | H有原件，C和W均缺失；其自身链接AGENTS、旧01及旧02 | H记载Graph待实现、agent_ready恒false，已不代表C/W；定位/Graph协议承担新职责，但未找到原文完整迁移证据 | 两提交保留H原件，暂缓删除。通过旧01指引修复出链，B/D README明确它是最初脚手架说明，当前行为以相应快照README为准 |

“逐字节副本未找到”只证明没有完全相同文件，不据此断言所有内容未迁移。无更多来源证据时继续暂缓。拟归档后工作区预计保留4项差异，`?? app/agents/prompts/general.py`、`D docs/02-real-model-chat.md`、`D docs/architecture.md`，以及未在工作区恢复指引时的 `D docs/01-environment-and-scaffold.md`。最后一项是提交树新指引与被保护的当前删除状态之差，区别于3个暂缓处置项。

如批准后仅在暂存快照中整理README/定位/路线图/D01的说明而不回写工作区，还将留下这些路径的文本差异。执行时逐项报告实际状态，不能承诺只有上述4项，也不能用批量覆盖工作区来消除差异。默认通过明确的最小文档编辑同步获批状态说明，保留所有既有用户内容；本轮尚未授权实施该步骤。

### 6.3 按拟提交集合检查链接

文件集合必须从H完整树起算。B覆盖第3节路径，删除候选按第6.2节仍继承H，旧01覆盖成指引。D继承整个B再覆盖第4节路径，不能只检查当前W中存在的文档。

本轮已在内存中按上述集合检查Markdown本地文件链接，包含暂缓删除的H两份文档。B含92个文件、D含119个文件。以C/当前W正文和拟旧01指引检查时，B为205处本地链接（其中10处为同页标题锚点），D为286处（其中10处为同页标题锚点），文件目标及按GitHub标题规则解析的锚点均未发现缺失。旧架构文档到旧01指引、旧02到保留H文件、指引到history正文均有目标。

该检查不创建落盘快照，不等于两个提交已验证。链接核查使用原件及拟指引，尚未套用第5节将来整理的全部状态文字与导航。后续仍须对最终整理的正文、所有本地链接及标题锚点重新检查，包括本文、README新增指引和状态引用。只使用快照内文件解析目标，不借用工作区未归档文件使检查虚假通过。

## 7. 数量、依赖与批准后验证门禁

原84路径加提案为85个唯一变更路径。B为45条，D为45条，共享8条，暂缓3条。核算为 `45 + 45 - 8 + 3 = 85`。共享新增 `app/main.py` 和 `app/core/config.py`，D条目数保持45，B由43增为45。旧01指引修改仍算B的同一路径，不新增计数。H中其余继承文件不计入提交变更条目，故完整快照文件总数与条目数不同。

提交链拟为 `2dcf652 → Baseline Commit → 01 Delivery Commit`。Delivery依赖B的模型/Graph装配、Runtime旧实现、类型/协议/映射及冻结设计。引用C作为读取来源，不将内部checkpoint tree当成正式发布提交，也不改动检查点引用。

1. 用户确认两份45条清单、8条共享边界、旧01指引、3项暂缓和状态文字整理规则后，才授权进入归档执行。
2. 批准后先形成两份可审阅快照及逐文件来源清单，分别标记H/C原件、W交付、依据记录整理的文字、拟指引。核对全部导入依赖、应用入口、模型/Graph构建、Runtime/Service和请求契约，避免读取当前工作区模块掩盖Baseline缺文件。
3. Baseline使用其自己的测试和本地配置隔离，在项目解释器下执行前序完整测试及可控应用启动/编译验证，确认README旧请求/启动说明与代码一致。原55项是开发报告历史证据，实际结果独立记录。默认不读取真实.env，不触发付费模型或数据库操作。
4. Delivery使用其快照执行完整回归及必要真实库验证，真实库验证仅在后续明确授权执行范围内进行。现有82项无失败/跳过属于W，不能提前当作拆分快照结果。分别记录两快照命令、cwd、解释器、通过/失败/skip和资源证据。测试时确认实际import路径来自对应快照。
5. 两份快照分别检查文档文件目标与标题锚点、权限/密钥/缓存等排除项。全仓Ruff既有P3-01按原裁决保留，新增问题需报告。D对已验收W逐文件比对，运行代码和测试应一致，允许差异仅为旧01指引、暂缓文件保留及明确获批的状态/历史说明和本提案。任何额外差异先解决归属。
6. 以上验证通过后再进行实际暂存，逐项审查B与D各自差异，分别创建两条提交，暂存范围限批准清单，保留用户工作区修改。归档执行及push以用户批准为前提，发现文件并发变化或验证失败时记录原因并暂停相关提交。
7. 成功后记录两个hash、分支和远程核验结果，再准备02执行任务由用户人工启动。

## 8. 本轮修订结果与未决项

本轮仅修订本提案，未暂存、Commit、Push、创建提交对象或修改Git引用，未执行数据库操作、付费模型调用或业务测试。H仍为第1节完整标识，暂存区为空，85个变更路径的集合保持不变。逐文件保护检查以本轮开始时原始字节SHA-256为准，除本提案外各路径的内容/缺失状态均须保持一致。

尚待批准后的验证包括两个独立快照的导入/应用入口/测试、最终正文和标题锚点、D与已验收W的差异核对。C作为树对象没有提交历史，无法仅据它确认每次文档编辑的时间或作者。旧general用途和两份删除文档的完整迁移证据仍不充分，维持暂缓。状态说明采用C中已存在的最终确认记录，属于有依据的归档整理，不声称找到了一个已经逐页清理全部旧状态的历史原件。

本提案已具备提交用户审核批准的条件，实际Git归档仍以批准和验证门禁通过为前提。用户此前批准01正式验收有效，归档授权现按最新指令等待本提案确认。当前其他文档仍写VERIFIED/待批准属于尚未同步的状态，本轮按单文件授权保留现状，D的状态整理按第5节处理。

## 9. 逐文件 H/C/W 比较证据

下表覆盖原84路径和提案，共85条。H/C列为各自文件blob的12位前缀，可用完整树标识加路径获取完整blob及内容。W列为原始字节SHA-256的12位前缀，文件缺失记为“缺失”。比较结论按统一换行后的完整内容，H/C同时无文件时标为“均无”，不视为已有历史内容。W的提案摘要取本轮修订前，其他路径摘要适用于修订后保护核对。

可复核命令如下，均为只读。

```powershell
git cat-file -t cdbe5272159936163414f64335f864ce2b49aa86
git for-each-ref --format='%(refname) %(objectname) %(objecttype)' refs/codex/turn-diffs/checkpoints/
git show cdbe5272159936163414f64335f864ce2b49aa86:app/main.py
git diff HEAD cdbe5272159936163414f64335f864ce2b49aa86 -- app/core/config.py
git diff cdbe5272159936163414f64335f864ce2b49aa86 -- app/runtime/agent_runtime.py
```

| 路径 | H blob | C blob | W SHA-256 | H→C | C→W |
| --- | --- | --- | --- | --- | --- |
| `.env.example` | 01e8f93c1cb2 | 01e8f93c1cb2 | 1a60199d1133 | 相同 | 改变 |
| `AGENTS.md` | b31803f9bfde | f4c947e320f6 | 2240e7fe7224 | 改变 | 改变 |
| `README.md` | db35fd4ba42d | 32ff0d6f7f9f | 82d45533f10d | 改变 | 改变 |
| `app/agents/prompts/__init__.py` | d68f88605700 | 46e6cb378216 | 35c0cdb3617b | 改变 | 相同 |
| `app/agents/types.py` | 5622edec0d60 | 90e16d866aa2 | d0e39aeffbd3 | 改变 | 相同 |
| `app/api/dependencies.py` | 936a67c85c0d | 936a67c85c0d | a63a67338ab2 | 相同 | 改变 |
| `app/api/routes/agent.py` | 9baef6195697 | 9baef6195697 | 35a09b6df8af | 相同 | 改变 |
| `app/api/schemas/chat.py` | e0dd62db8fc0 | e0dd62db8fc0 | bf3e1fe05d97 | 相同 | 改变 |
| `app/core/config.py` | 33582bc3cd94 | 9cf3d5a713b7 | f3017441cc79 | 改变 | 改变 |
| `app/core/errors.py` | d4d19aa856c1 | d4d19aa856c1 | 05bf807525f9 | 相同 | 改变 |
| `app/core/logging.py` | b17aae003fd2 | b17aae003fd2 | 2d4cff606663 | 相同 | 改变 |
| `app/graph/builder.py` | fc376b1392ec | df4008053809 | d3e631c57232 | 改变 | 相同 |
| `app/graph/nodes/__init__.py` | cc990cf1bb94 | 47de113fcda2 | f0fcfb22441b | 改变 | 相同 |
| `app/graph/router.py` | 68adf87c7958 | 893999afeb4f | a5a77f79c514 | 改变 | 相同 |
| `app/graph/state.py` | 33ab75f44605 | e5f6eb1db9e5 | 96b284e2dc7f | 改变 | 相同 |
| `app/infrastructure/postgres.py` | 8a61147422ef | 8a61147422ef | 2e4574c48826 | 相同 | 改变 |
| `app/main.py` | 5a5ba238dd48 | c3d0335be413 | a49ad0399670 | 改变 | 改变 |
| `app/runtime/agent_runtime.py` | 6338a3ad077e | af63d4249b7e | 29a1d48c8a3e | 改变 | 改变 |
| `app/services/agent_service.py` | a7fab33a9b4b | a7fab33a9b4b | ff8767a43506 | 相同 | 改变 |
| `docs/01-environment-and-scaffold.md` | f5bc020ac976 | 缺失 | 缺失 | 删除 | 均无 |
| `docs/02-real-model-chat.md` | e95455a12cf4 | 缺失 | 缺失 | 删除 | 均无 |
| `docs/architecture.md` | 1c520dfc63b9 | 缺失 | 缺失 | 删除 | 均无 |
| `requirements.in` | 92a07525d643 | 92a07525d643 | d16c7db6d5ff | 相同 | 改变 |
| `tests/test_application.py` | 84810e59732a | 84810e59732a | 7195f04dfad8 | 相同 | 改变 |
| `app/agents/prompts/general.py` | 缺失 | 273b6b2f94c7 | 4a14ee4e1c5b | 新增 | 相同 |
| `app/agents/prompts/supervisor.py` | 缺失 | da5d727349df | 56776dd26d1f | 新增 | 相同 |
| `app/graph/contracts.py` | 缺失 | cfa517dedac4 | 6553f4f4c216 | 新增 | 相同 |
| `app/graph/nodes/clarification.py` | 缺失 | aeb88a061871 | 2b96767ec426 | 新增 | 相同 |
| `app/graph/nodes/response.py` | 缺失 | cc3816f98eac | 5d235e5be7b6 | 新增 | 相同 |
| `app/graph/nodes/result_aggregator.py` | 缺失 | 851c13f9c52e | 50d46d917bae | 新增 | 相同 |
| `app/graph/nodes/specialist.py` | 缺失 | 0e0039f37927 | 83271a9e175a | 新增 | 相同 |
| `app/graph/nodes/supervisor.py` | 缺失 | e6732837c3d2 | 0b6886e10c3c | 新增 | 相同 |
| `app/graph/transfers.py` | 缺失 | 6face028589e | 29c064210191 | 新增 | 相同 |
| `app/infrastructure/model.py` | 缺失 | 缺失 | dad64d2d871d | 均无 | 新增 |
| `app/infrastructure/sessions.py` | 缺失 | 缺失 | c3410a13d876 | 均无 | 新增 |
| `app/runtime/context.py` | 缺失 | 缺失 | 698b123c1dee | 均无 | 新增 |
| `app/runtime/model_gateway.py` | 缺失 | 缺失 | 14b9cdbf3f12 | 均无 | 新增 |
| `compose.yaml` | 缺失 | 缺失 | 0eb7ac02631d | 均无 | 新增 |
| `docs/01-foundation-detailed-design.md` | 缺失 | 87be1deeb27d | e3b4e8bc4210 | 新增 | 改变 |
| `docs/02-agent-runtime-detailed-design.md` | 缺失 | 63d057a3e4a8 | f1fd1b509d75 | 新增 | 相同 |
| `docs/03-tool-governance-detailed-design.md` | 缺失 | d4a76e369769 | f9ca59db75a6 | 新增 | 相同 |
| `docs/04-hitl-checkpoint-refund-detailed-design.md` | 缺失 | 9d1bfcbd7d77 | 01d19d015306 | 新增 | 相同 |
| `docs/05-rag-memory-detailed-design.md` | 缺失 | 6d0126bab382 | 413ea837b64e | 新增 | 相同 |
| `docs/06-integration-and-final-delivery-detailed-design.md` | 缺失 | b6fc634d3db0 | c8e60642bd44 | 新增 | 相同 |
| `docs/agent-engine-demo-plan.md` | 缺失 | 41e6622b2d5f | d462e40ae05f | 新增 | 改变 |
| `docs/development-roadmap.md` | 缺失 | 2bc7a0175b19 | 8ef365cc6e01 | 新增 | 改变 |
| `docs/graph-protocol.md` | 缺失 | c7693bd9b265 | 832270fa8181 | 新增 | 相同 |
| `docs/history/01-1-engineering-and-architecture-baseline-plan.md` | 缺失 | 47b55bd157de | 186cbcc2bd4b | 新增 | 相同 |
| `docs/history/01-environment-and-scaffold.md` | 缺失 | 28e1d8f03c83 | f9ab0303ada3 | 新增 | 相同 |
| `docs/history/01-stage-detailed-design.md` | 缺失 | caeb4133ef8b | 92ebd2da9c19 | 新增 | 相同 |
| `docs/history/02-stage-detailed-design.md` | 缺失 | c364e634475f | b472e4e1a8e5 | 新增 | 相同 |
| `docs/history/03-stage-detailed-design.md` | 缺失 | eb6b0588accd | 64ed7da1b027 | 新增 | 相同 |
| `docs/history/03-stage-execution-plan.md` | 缺失 | 191980e341cb | a90a42abff5e | 新增 | 相同 |
| `docs/history/04-1-order-service-design.md` | 缺失 | f2bbd882202a | 4b19e3bff3f7 | 新增 | 相同 |
| `docs/history/04-2-tool-registry-design.md` | 缺失 | 6af35ee9999c | e2baada5222e | 新增 | 相同 |
| `docs/history/04-3-tool-execution-design.md` | 缺失 | 80c0afa86423 | 02b9993f0b81 | 新增 | 相同 |
| `docs/history/04-4-order-agent-design.md` | 缺失 | 51c0a5838485 | b0e2148ab8b3 | 新增 | 相同 |
| `docs/history/04-stage-execution-plan.md` | 缺失 | 7c11280f24b6 | 4f4dedb4cee5 | 新增 | 相同 |
| `docs/history/README.md` | 缺失 | 84083cac40b0 | 167ff17092a0 | 新增 | 相同 |
| `docs/history/development-roadmap-commerce-history.md` | 缺失 | 6379e8f725b5 | f7788f807a86 | 新增 | 相同 |
| `docs/question/01-foundation-acceptance.md` | 缺失 | 缺失 | dbff21998be8 | 均无 | 新增 |
| `docs/question/01-foundation-main-review.md` | 缺失 | 缺失 | 0b58ed6e59b4 | 均无 | 新增 |
| `docs/question/01-foundation-regression-report.md` | 缺失 | 缺失 | 8f759a58b143 | 均无 | 新增 |
| `docs/question/01-foundation-regression-task.md` | 缺失 | 缺失 | 177a25adb8d5 | 均无 | 新增 |
| `docs/question/01-foundation-stage-acceptance.md` | 缺失 | 缺失 | a134189a35e2 | 均无 | 新增 |
| `docs/question/01-git-archive-proposal.md` | 缺失 | 缺失 | 9b2902ea24df | 均无 | 新增 |
| `docs/question/README.md` | 缺失 | 缺失 | d69b246dd95a | 均无 | 新增 |
| `docs/resume/01-foundation-fix-task.md` | 缺失 | 缺失 | bebbfcb1e8bb | 均无 | 新增 |
| `docs/resume/README.md` | 缺失 | 缺失 | dae6a9893ee6 | 均无 | 新增 |
| `docs/resume/record/01-foundation-fix-report.md` | 缺失 | 缺失 | a2ca645825e6 | 均无 | 新增 |
| `docs/resume/record/README.md` | 缺失 | 缺失 | 8de250995dc9 | 均无 | 新增 |
| `migrations/001_sessions.sql` | 缺失 | 缺失 | a631f16694b5 | 均无 | 新增 |
| `migrations/002_deferred_thread_uniqueness.sql` | 缺失 | 缺失 | 33b0c240ac8e | 均无 | 新增 |
| `scripts/__init__.py` | 缺失 | 缺失 | 8bb9c73899b5 | 均无 | 新增 |
| `scripts/check_model.py` | 缺失 | 缺失 | d031813df9f6 | 均无 | 新增 |
| `scripts/init_databases.py` | 缺失 | 缺失 | 5ccdb2c10037 | 均无 | 新增 |
| `scripts/migrate.py` | 缺失 | 缺失 | f849839da1cf | 均无 | 新增 |
| `tests/test_agent_types.py` | 缺失 | abeae57b3ef5 | a4e37f19c035 | 新增 | 相同 |
| `tests/test_config.py` | 缺失 | 缺失 | 9dfa316b8482 | 均无 | 新增 |
| `tests/test_demo_identity.py` | 缺失 | 缺失 | 608567bc1b90 | 均无 | 新增 |
| `tests/test_graph_protocol.py` | 缺失 | 1b77fdeb5cd3 | 636bb40a0b07 | 新增 | 相同 |
| `tests/test_graph_state.py` | 缺失 | cebf02f9fcf5 | 83a776640200 | 新增 | 相同 |
| `tests/test_model_gateway.py` | 缺失 | 缺失 | 9e063743a38e | 均无 | 新增 |
| `tests/test_postgres.py` | 缺失 | 缺失 | 4a0f41ee756a | 均无 | 新增 |
| `tests/test_resources.py` | 缺失 | 缺失 | 5a74644f4924 | 均无 | 新增 |

## 10. 获批快照构造与独立验证记录

2026-11-10 用户批准按本提案构造两份仓库外快照，并授权使用已配置的专用测试库运行既有测试。当前状态为 **01 已获用户正式验收，归档快照验证中，02 尚未启动**。本节只记录快照准备与验证，实际暂存、提交和push等待用户审阅结果后另行授权。此前第1～9节的“待方案批准/未构造”文字保留为提案形成时记录，本节为本轮最新结果。

### 10.1 保护基线及快照产物

开始前记录HEAD、分支、原始暂存区摘要、85个变更路径、全部已跟踪/变更文件及真实.env的原始字节摘要，仅保存摘要、未输出凭据。记录位于 `D:/py/agent-project/archive-validation-20261110-01/workspace-before.json`。核对现有路径集合和第9节摘要，无新增变更或内容冲突。

| 快照 | 绝对路径 | 文件数 | 相对父版本变更数 | 内容摘要SHA-256 |
| --- | --- | --- | --- | --- |
| Baseline | `D:/py/agent-project/archive-validation-20261110-01/baseline` | 92 | 45 | `97670415bf857646f89e167fca2b57f15b8658ea8dabe01a3c88f1a8bbe06d10` |
| 01 Delivery | `D:/py/agent-project/archive-validation-20261110-01/delivery` | 119 | 45 | `67ff7f68951f900d581f73540345633d985149a81111a0772ab3d35bbfca9dfe` |

内容摘要为按路径排序的 `path<TAB>文件原始字节SHA-256<LF>` 清单的SHA-256，不是Git树对象。快照目录只包含拟交付文件，测试脚本、日志、来源清单及验证产物保存在其外层目录。后续检查确认快照文件没有被测试或检查工具改写。

外层目录中的 `baseline-manifest.json` 与 `delivery-manifest.json` 覆盖完整逐文件来源、原始字节摘要及整理原因；`baseline-changes.json`、`delivery-changes.json` 分别列出完整45项变更，`baseline-changes.diff`、`delivery-changes.diff` 给出可审阅正文差异。`validation-report.md` 汇总完整清单、逐命令记录及结果。构造脚本为 `build_snapshots.py`，其状态整理采用断言匹配和明确段落替换。

### 10.2 八个共享路径的实际拆分

| 路径 | Baseline实际来源与整理 | Delivery实际来源与整理 |
| --- | --- | --- |
| app/main.py | C完整原件，ChatOpenAI/Graph/Runtime/Service旧装配 | W原始字节，01池/Session/model_resources/准备层状态等增量 |
| app/core/config.py | C完整原件，包含前序模型配置注释 | W原始字节，01配置/限制/安全验证及NUL修正 |
| app/runtime/agent_runtime.py | C完整原件，旧执行逻辑 | W原始字节，只增加RunLimits/RunUsage |
| AGENTS.md | C完整原件，最终确认及历史规范 | W全文加获批当前状态说明，旧阶段记录保留 |
| README.md | C旧启动、workflow请求和导航，补最终确认覆盖及历史入口说明 | W当前运行/准备层说明，补当前状态和历史入口说明 |
| docs/agent-engine-demo-plan.md | C正文，按最终确认记录整理页首、第2节历史标签及第8节状态 | W正文加当前状态，原QA及历史记录保持语境 |
| docs/development-roadmap.md | C任务/依赖及未来验收，整理页首、01设计摘要、第4节冻结状态 | W正文加当前状态，将78项明确为首次交付历史证据并标注82项后续回归 |
| docs/01-foundation-detailed-design.md | C设计正文，整理页首、第1节、8.3及第11节设计列，未实施/未验证，无002实施记录 | W开发/PG/002及交付记录，补当前状态和开发过程历史说明 |

三项暂缓处置按提案执行。general.py不在任一快照，两份旧文档在两快照均保留HEAD原件，旧01路径在两快照均使用获批指引。当前工作区的未跟踪/删除状态保留。

### 10.3 命令、执行目录与导入隔离

所有验证使用 `D:/py/agent-project/agent/.venv/Scripts/python.exe`。子进程清除原AGENT_/OPENAI_/LANGCHAIN_/LANGSMITH_及PYTHONPATH/PYTHONHOME，禁用bytecode、pytest缓存和Ruff缓存。快照没有真实.env。测试库URL从原.env只读取得，仅经子进程环境传递，没有写入快照、脚本、命令参数或日志。

`validate_runtime.py` 在执行前把当前快照目录置于sys.path首位，并断言app.main、config、Runtime、builder、Service、ChatRequest的实际模块路径均在该快照下。pytest使用快照自己的tests和pyproject。运行日志记录完整cwd及解释器。源码的全部Python文件经AST解析通过。

以下命令路径均位于同一外层验证目录，完整可复现命令保存在 `test-results.json`、`socket-results.json` 及 `validation-report.md`。

| 检查 | 工作目录 | 实际命令形式 | 结果 |
| --- | --- | --- | --- |
| Baseline完整前序测试 | `.../baseline` | 项目Python `-B -X utf8 ../validate_runtime.py pytest`，内部执行pytest `-q -p no:cacheprovider` | 55 passed，0 failed，0 skipped |
| Baseline受控应用/模型/Graph/旧请求 | `.../baseline` | 项目Python `-B -X utf8 ../validate_runtime.py baseline` | 退出0，无资源503、workflow必填422、受控主图澄清和SSE token/done通过 |
| Delivery真实库预检 | `.../delivery` | 项目Python `-B -X utf8 ../validate_runtime.py state` | 退出0，核实agent_demo_test/agent_test、schema及checksum |
| Delivery完整现有测试 | `.../delivery` | 项目Python `-B -X utf8 ../validate_runtime.py pytest`，仅子进程传专用测试URL | 82 passed，0 failed，0 skipped，与已验收记录一致 |
| Delivery真实PG/受控模型应用探针 | `.../delivery` | 项目Python `-B -X utf8 ../validate_runtime.py delivery` | 退出0，NUL422/零准备调用、正常JSON503及实际绑定、精确清理与资源关闭通过 |
| Delivery真实库后检 | `.../delivery` | 项目Python `-B -X utf8 ../validate_runtime.py state` | 退出0，与预检一致 |
| 两快照实际Uvicorn socket启停 | 各自快照目录 | 项目Python `-B -X utf8 ../socket_smoke.py baseline` 或 `delivery` | 各退出0，health/docs200、chat JSON503、正常退出 |
| 两快照Ruff lint | 各自快照目录 | 项目Python `-B -X utf8 -m ruff check --no-cache .` | 各退出1，仅既有supervisor.py第8行E501 |
| 两快照Ruff format | 各自快照目录 | 项目Python `-B -X utf8 -m ruff format --check --no-cache --output-format concise .` | 各退出1，原8个失败文件，无新增 |

Baseline pytest为55 passed，Delivery为82 passed in 6.63s。各有两条PytestAssertRewriteWarning，因验证入口在pytest.main前导入应用，anyio/langsmith已加载，断言及用例正常执行。没有付费模型调用。Baseline模型/路由使用ControlledModel，Delivery使用受控模型配合真实HTTP资源和测试库；Uvicorn无资源探针分别使用Baseline默认loop和Delivery文档中的Selector入口。

### 10.4 数据库与生命周期证据

预检以只读事务确认专用测试库，版本1/2及checksum与快照迁移一致，避免测试入口升级schema。既有真实库测试执行重跑/checksum/未知版本/临时失败DDL回滚，并按随机测试用户精确清理。额外HTTP探针使用唯一conversation_id，最后按该user/conversation精确删除。

前后Session均为0行，完整Session结果摘要均为 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`。版本/checksum和public表集合相同，仍为schema_migrations与sessions。证据见 `database-cleanup.json`。未访问应用库、重建基础设施或升级迁移。

Delivery真实lifespan退出后pool.closed、同步/异步HTTP客户端is_closed均为true。受控失败释放由完整测试覆盖。Baseline使用前序装配，没有新PG资源；无外部配置及受控模型路径正常启动退出，实际socket进程内server线程亦已收敛。

### 10.5 链接、排除项与Delivery一致性

- Baseline为208处本地链接/标题锚点，Delivery为289处，缺失文件和锚点均为0。两份暂缓删除的HEAD旧文档已纳入检查，旧架构到旧01指引及旧02均可解析。检查在真实落盘快照文件集合内进行，忽略代码示例中的伪链接。
- 两快照无真实.env、.git、虚拟环境、缓存、pyc或测试/验证日志。验证脚本与清单均在快照外。针对4项本地实际配置的密钥/数据库密码字符串扫描无命中，敏感值未进入报告。
- Delivery的app、tests、scripts、migrations运行代码和测试与已验收W逐字节一致。5个获批状态/历史说明文档及3个历史保留入口的语义差异已列入 `delivery-vs-worktree.diff`。
- D02～D06及requirements.txt共6项仅有原件LF与工作区CRLF的字节表示差异，`core.autocrlf=true`，归一化内容完全相同，未变更依赖版本。两侧原始摘要均在 `static-results.json`，不将其隐瞒为字节相同。首次一致性检查器将这些差异误判为越界，定位后改为分别报告换行差异与语义差异，保留源快照原件字节。
- 快照内提案保留构造时的获批输入版本。本轮工作区提案追加本节作为验证记录，该差异属于已批准例外，两个快照内容摘要保持固定。未来实际归档若同步最终验证记录，应重新核对文档差异及链接，运行代码无须因此重构。

静态验证产物为 `static-results.json`，快照文件摘要复核通过。两快照format遗留文件集合与P3-01相同，Baseline为78 files already formatted、Delivery为102，扫描数量差异来自快照内容差异。运行代码未作修复或扩展。

### 10.6 保护复核与归档判断

HEAD保持 `2dcf65293683e63faf99b75b8ea2630dba42db76`，分支保持real-model-chat，暂存区原始摘要仍为 `6fc1ba1e1afd8baa140a99e2920b201ddcb09743aaa1d9661fedee2f51a1e556`，cached diff为空，85个变更路径集合未变。保护核查覆盖全部已跟踪/变更文件及真实.env，除本提案追加本节外，原文件字节及缺失状态均保持不变。最终核查记录在 `workspace-after.json`。

两份快照的独立运行、测试、文档与来源门禁已满足，既有P3-01继续按原裁决保留。没有新增业务缺陷或待修复的快照拼装问题。前序检查点没有作者/阶段提交历史、三项暂缓的用途/迁移证据边界继续保留，未据此扩大归档范围。

结论为已具备提交用户审阅并申请实际Git归档授权的条件。实际暂存、Commit和push尚未授权，本轮完成后停止。02 尚未启动。



## 11. Git归档执行记录

2026-11-10 用户审核独立快照验证结果后明确授权提交Git并进入下一开发环节。01状态为 ACCEPTED，02执行任务在归档成功后交用户人工转交，专业开发会话尚待启动。第10节的快照验证及历史待授权表述保留当轮语境。

Baseline已按验证快照提交，提交标识为 `f89db15efc9b38e88bfed6a725abde76575c6bae`，提交说明为 `Establish Baseline - Supervisor Graph and Frozen Design`。45项范围及暂存完整树已核对，diff检查通过。01 Delivery按已验证快照及本提案最新验证/授权记录归档，提交说明为 `Complete Phase 01 - Foundation and Environment`。

分支沿用real-model-chat，远程为origin。实际Delivery提交标识、推送及远端核验结果另记于仓库外 `D:/py/agent-project/archive-validation-20261110-01/git-archive-receipt.json`，并在02人工交接任务中引用。实际Git对象按仓库core.autocrlf规则规范化换行，运行代码与已验证快照内容一致。

本轮采用暂存快照方式保护原工作区，五份文档的已批准状态整理保存在提交树内，原工作区文本保持原样。旧01归档指引同样保存在提交树内，原工作区的删除状态保留。general.py及两份旧文档删除继续按原决定暂缓。后继执行会话须先核对这些归属已明的工作区差异，再按授权修改，避免将其视为新的未审业务修改。
