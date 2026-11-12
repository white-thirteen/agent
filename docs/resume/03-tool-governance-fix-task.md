# 03 工具治理独立QA问题修复任务

日期：2026-11-12。主Agent已逐项复核并确认03-QA-001（P2）及03-QA-002（P3），本轮合并为最小修复任务。用户已授权03阶段内必要修复及复测；不得变更冻结设计、开始04或进行Git归档。

## 依据与范围

先读AGENTS、冻结D03、[03执行任务](../03-tool-governance-execution-task.md)、[开发交付](../03-tool-governance-delivery-report.md)、[独立QA报告](../question/03-tool-governance-qa-report.md)第7节及[主Agent裁决](../question/03-tool-governance-main-review.md)。02基线94cf205，03已完成六Task实现；独立完整真实库130项、仓库外16项及真实模型/PG通过，但设计符合性问题尚未闭环。

只处理下列两项及必要的少量回归测试，不以测试全绿接受明确分层偏差，不新建通用异常/审计平台。旧报告原文保留，修复新增独立报告。既有general.py、三个旧文档删除、D01历史差异、独立Bridge文件及主Agent协调文档按原归属保留。不得调用Bridge/其他会话，不Commit/Push，不改依赖、Schema/SQL/种子或用户凭据。

## 03-QA-001 / P2 / Task 3.3.1及3.2.1

根因：app/domain/orders.py直接导入并抛出app.tools.models中的ToolTransientError/ToolUnavailableError，后者引入Graph/Runtime。违反D03 Task3.3.1和第11节“数据层本身不反向依赖工具或图”。当前查询能运行不代表分层契约成立。

最小修复：数据/领域层使用自己定义的明确访问故障类型，订单工具适配负责转换到现有工具治理异常。不得把RunScope、工具执行上下文或Graph引入数据层；不改变owner SQL、领域归属复核、金额/模拟标识、业务拒绝和安全公开code。

验收：实际导入订单数据模块不加载工具/Graph/Runtime；可重试数据故障仍按只读安全白名单有限重试并每次计数；不可重试故障一次失败，不伪装not_found或空列表；取消、超时和非预期编程错误传播保持原契约。覆盖get/list适配，不用宽泛catch吞掉所有异常。

## 03-QA-002 / P3 / Task 3.2.2及3.3.2

根因：订单execute_query的call_records只保存call/normalized_args/result，缺少D03跨阶段收敛记录要求的显式origin和当前run关联，外围request可推断不等同于记录自身具备关联。

最小修复：在现有私有记录构造处保存可信执行入口origin和当前run_id，从服务端ToolExecutionContext/ExecutionContext取得，不能从模型raw_args取值。保留原始id/name/raw_args、规范参数、结果及execution_id/attempts/usage，不能因此新增公共SSE字段或数据库。

验收：实际成功工具链的记录具备准确origin/run_id；两次不同Run可正确区分，观察重进仍复用记录及稳定ToolMessage、零额外handler/计数；父图及公共SSE不泄漏私有记录。

## 自测与资源约束

使用项目.venv解释器。先定位再作最小修复，复用既有测试，必要时添加少量有意义的行为回归；执行受影响治理/订单/主图测试及真实订单库验证、对应Ruff。主Agent随后交独立测试会话进行完整回归，不必为相同证据反复全量测试或重跑付费模型。

真实写入仅已配置agent_demo_test，先核对目标/身份/schema3/checksum，按既有回滚及精确清理规则保留原五订单和Session行集；不得迁移、重建、写应用库、改密码。默认pytest脱敏插件/fd捕获保持，禁止输出凭据、URL或异常全文。RISK-02-CRED与P3-01继续按已接受遗留管理。

## 交付

**必须将修复记录整理到 `docs/resume/record/03-tool-governance-fix-report.md`**，关联阶段03、上述Task、03-QA-001/002及本提示词。写明根因、实际修改路径和接口、修复边界、命令/结果、数据前后核对与清理、设计偏差和遗留。结论仅为开发自测，不自行关闭QA问题或把03改为VERIFIED/ACCEPTED。

完成后向主Agent回复报告路径、实际测试结果及未完成项，等待独立回归。
