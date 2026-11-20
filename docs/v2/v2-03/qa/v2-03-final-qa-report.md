# V2 03 最终独立 QA 技术报告

2026-11-20。结论：**PASS；六 Task 均建议 VERIFIED，QA-001～008 建议关闭，交主 Agent 最终技术裁决。** 本结论不是用户正式 ACCEPTED 或 Git 授权。首轮 [FAIL](v2-03-initial-qa-report.md)、[fix01 FAIL 与 fix02 逐项复测](v2-03-fix01-retest-report.md)及所有原始失败保留。主 Agent 核对本 QA 与 Implementer 实际运行元数据均为 Terra/high；根规则和角色 TOML 未变。

## 六 Task 技术建议

| Task | 建议 | 主要证据 |
| --- | --- | --- |
| 3.1.1 目录视图与版本 | VERIFIED | 元数据目录、冻结及版本/schema 摘要的受控测试，完整 r2；模型候选仅名称与说明。 |
| 3.1.2 Agent/权限/用途 | VERIFIED | 三层过滤及内部/偏好工具不可发现，生产 Order 保持单工具；非法范围在 Policy/Executor 复核。 |
| 3.2.1 Selector 与预算 | VERIFIED | R/B、重试、慢持久化、剩余期限、B>1 压缩和用量回执定向检查；固定五题真实模型。 |
| 3.2.2 Schema/绑定/执行 | VERIFIED | 真实两候选 Node 的单订单与分页，经 Selector、Registry、真实模型 Gateway、Policy、Executor 和隔离 PG，实际 ToolCall 与 ToolMessage 配对及 SQL 核对。 |
| 3.3.1 复用/重发现/恢复 | VERIFIED | 受控范围和失败计数、真实隔离 Saver 完整提交/节点异常/独立进程退出、新 Run 与重发现下限、旧审批样本原调用恢复。 |
| 3.3.2 真实选择与兼容验收 | VERIFIED | 五题与两链路、实际单工具 HEAD 对照、真实 Qwen、完整 r2 322项和受保护数据库比较；实际限制见下。 |

## 问题闭环

- **V203-QA-001 / P1，建议关闭**：真实 Runtime compactor 的 B=1/B>1、期限与受控业务模型检查及隔离 PG compaction 回归通过；不声称摘要替身是真实模型。
- **002 / P1，建议关闭**：pending 缺记录拒绝；HEAD Refund builder 产生的真实 Saver 旧审批样本以当前 Runtime 恢复，Selector 0，原 call_id、operation_id、版本、参数、审批主体未变，Policy 重查，重复恢复后受控副作用 1。该样本是同进程 Runtime 重建、受控业务服务，并非生产旧快照或跨进程审批实证。
- **003 / P1，建议关闭**：失败重发现计数随记录保留、重复拒绝；真实 Saver 强退复跑获得 rediscovery floor 1、attempt floor 2、root 1，并清理 thread。
- **004 / P1，建议关闭**：独立真实 Saver 探针的节点异常与子进程 `os._exit(71)` 后，root 仍为0而持久 floor 1 且未决，未知结果不被确认为完成；真实完整主节点提交后可确认，新 Run 保留下限。另复跑受控业务新 Run 强退探针；适用范围为已验证故障与恢复路径，不声称全局 Exactly Once。
- **005 / P2，建议关闭**：Order 图将重发现记录与投影写回，可信目标变化与历史变化区分；真实链路绑定、调用、执行集合一致。
- **006 / P1，建议关闭**：付费真实测试移出默认发现且显式 opt-in；唯一数据、在线隔离身份、SQL 核对及精确清理经独立真实组验证。
- **007 / P1，建议关闭**：首次、重发现、逐次预留写和重试后的期限重核及 B>1 受控测试通过，避免侵占业务时间。
- **008 / P2，建议关闭**：Selector 内部回执与业务 context view 分离，成功、失败、unknown、重试、父子映射、新 Run 去重受控检查通过；真实 Saver 探针保存回执。

上述复测命令、实际输出及限制详见 [独立复测](v2-03-fix01-retest-report.md)。42 项受控测试、独立 Saver 和 fixture 核验的本会话工具输出为[文本摘录](../evidence/v2-03-independent-session-output-transcript.md)，不冒充原始进程字节。

## 完整门禁 r2 的独立只读审核

[原始日志](../evidence/v2-03-full-regression-r2.log)最终 `322 passed, 3 warnings in 400.08s`；[汇总](../evidence/v2-03-full-regression-r2.json)记录 pytest exit 0、322 passed/0 failed/0 skipped、pytest 401.005 秒。主 Agent 外层记录进程退出0、总435.796秒。独立计数日志中 **322 个不同 test node**，其中 progressive disclosure 32 个；固定五订单旧 seed 幂等窄例外 `tests/test_order_postgres.py::test_real_order_constraints_isolation_and_seed_idempotence` 在运行列表中。3条 warning 为2条 pytest assert rewrite 和1条 LangGraph 弃用，不是失败。

审核 [.git/v203-full-gate-r2.py](/D:/py/agent-project/agent/.git/v203-full-gate-r2.py)、[.git/v203-run-gate-r2.py](/D:/py/agent-project/agent/.git/v203-run-gate-r2.py)及 `scripts/verify_06_delivery.py`：原完整 verifier 执行 `pytest.main`，包装器只追加 `--tb=short` 和逐项进度插件，没有 deselect、skip 或修改断言；[实际调用记录](../evidence/v2-03-full-regression-r2-invocation.json)为 `-q --tb=short`，汇总原 verifier 的 `pytest_args` 仅记 `-q`，后者未记录格式参数，不影响测试范围。显式付费模型 opt-in 为 null；汇总的 `paid_chat_calls=0` 是 verifier 内固定报告值，并非独立网络计数，本结论依据 opt-in 和测试入口审查，不将其称为独立流量统计。

[r2 前后即时指纹](../evidence/v2-03-full-regression-r2-protection-snapshots.json)与汇总的 `protected_before/after` 两对象逐项一致；20张 public 表中仅 knowledge_index_state 摘要变化。固定五订单前后均5行、7列及相同 SHA-256 `c7b06b737552bb76c2e107b9dac84bdb9ec8c5d5877a43388c5e833e8d909fb8`。保护比较代码对所有其他表完整行集及列定义严格比较，并对索引状态非 watermark 字段逐值比较；watermark **58→69，精确 +11**。非 watermark 值相等是执行期间比较断言的结果，不能仅由摘要重建。先前[独立水位审计](../../v2-01/qa/v2-01-task132-v1-fix-retest-report.md)解释共享库原9次加 task131 与共享库同库的2次；r2 launcher 保持对应库映射，并明确在运行前配置精确 +11。

[真实 Qwen 回执](../evidence/v2-03-qwen-evidence-r2.json)记录真实 Qwen 1024 维、准备与重复拒绝/故障清理 PASS、内部水位58→62；完整 r2 使用真实 Qwen 开关而非跳过。启动验证通过真实 Uvicorn 健康请求：Agent/数据库/模型/Embedding/知识/Checkpoint/Store ready；business 与 checkpoint 连接池关闭，剩余 asyncio task 与 Qwen embedding 线程均为空。Python 3.13.7 使用项目 `.venv`，相关 torch、transformers、LangGraph 和 psycopg 实际版本见 r2 汇总。

## 独立真实模型与成本

[无损手动组](../evidence/v2-03-independent-real-manual.log)为真实配置模型、隔离 PG、显式 opt-in，2 passed；固定五题与原 fixture SHA 一致，ASCII JSON 解码后中文逐字相同且无 U+FFFD。5次 Selector **2466 known tokens**；单订单和分页两条完整链路4次模型调用 **1879 known tokens**，SQL 归属/分页对照、ToolMessage 配对和清理0。合计 **9次、4345 known、0 unknown**；关闭模型重试，不重跑旧乱码记录。

[单工具真实成本对照](../evidence/v2-03-independent-real-cost.log)比较 `1f3d736` 的 HEAD Order builder 与当前 builder，其他依赖共享当前版本；同真实模型、隔离 PG 和唯一订单，各2次业务调用、Selector 0、`get_order` Schema 一致且约83 tokens，SQL 事实匹配、清理0。HEAD/current 分别1173/1192 known tokens，单次延迟2.509/2.349秒，不能推导生产成本或延迟收益；最小 Registry 中可选偏好工具被 Policy 拒绝。SQL结果在该对照日志中保存的是事实一致布尔值而非原值，具体比较逻辑见探针。两组累计 **13次、6710 known tokens，0 unknown**。

## 遗留与保护边界

首轮完整运行是 [INTERRUPTED_NOT_PASS](../evidence/v2-03-full-regression-interruption.json)，其 after-only 快照不证明该次前后相等；r2 是独立完成的后续门禁。全范围 `ruff check app tests` 的3个 E501 为接管 HEAD 已有遗留，见 [Ruff 范围记录](../evidence/v2-03-main-ruff-scope.md)，不能称全范围 Ruff PASS；受影响文件检查另有实施者证据。既有批准的暂缓差异不在本单元关闭。

本次最终 r2 审核只读检查证据与脚本，未重跑测试、数据库或模型；之前独立定向运行和付费调用单独如实记载。正式库数据不在 r2 隔离测试库的前后比较范围；旧审批跨进程和任意时间旅行、模型选择对开放场景的泛化、一次成本与延迟观测的统计意义均不作额外承诺。最终 ACCEPTED 与后续阶段由用户决定。
