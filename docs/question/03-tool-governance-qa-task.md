# 03 工具治理与模拟订单查询独立QA任务

本任务在执行会话完成03交付并由主Agent核对后派发。独立测试角色仅审查和验证，输出问题报告，业务实现和修复保持独立。依据为 [D03冻结设计](../03-tool-governance-detailed-design.md)第13.2节、[03执行任务](../03-tool-governance-execution-task.md)及届时 [开发交付报告](../03-tool-governance-delivery-report.md)。02正式归档为 `94cf205a734c305a6919a34cfeacc3e717d4856f`。

## 1. 审查范围与保护

读取AGENTS、有效定位/路线图、D03全文和01/02接口必要章节，核对交付报告与实际代码。保持被测业务代码、仓库测试、依赖、迁移、配置内容，独立临时补测放仓库外并记录路径。只新增本轮QA报告。主Agent在派发前记录实现摘要，并在QA后核对独立性。

工作区含已记录的旧文档删除、general.py、D01历史注释差异、独立Bridge文档及03协调文件，按原归属保留。不调用Bridge/其他会话，不Commit/Push，不自行修复实现。规划不新增任务，真实冻结设计冲突交主Agent。03尚未获得正式验收或04切换许可。

## 2. 按冻结矩阵验证

| 门禁 | 独立证据要求 |
| --- | --- |
| Registry及绑定 | 重名和冻结拒绝，元数据约束，Agent/scope过滤；检查真实Gateway绑定载荷中的完整Schema及共享绑定隔离 |
| 曝光与执行 | 已曝光工具仍受参数/权限/风险/预算复检；unknown/disabled/未允许工具的handler零调用，不披露隐藏目录 |
| 查询任务范围 | get仅get_order且order_id精确匹配，list仅list_orders且limit/offset精确匹配；模型换合法工具或扩大参数也拒绝 |
| handler边界 | typed args一次验证；handler仅收到可信user_id/task_id/run_id业务关联，不能取得RunScope/Limits/Policy或模型身份候选 |
| 身份与SQL | args身份/owner注入拒绝，真实PG SQL含owner且Service结果再核验归属；A查B与不存在统一拒绝 |
| Policy三态 | ALLOW才执行，DENY/REQUIRE_APPROVAL零尝试；03审批未接入返回approval_not_available，不创建等待或聊天放行 |
| 尝试与预算 | 成功/失败/安全只读重试每次handler启动前计数，拒绝/剩余not_executed为零；跨Run继承且耗尽不再调用 |
| 批次与配对 | 最多4calls，重复/缺ID及invalid_tool_calls整批零执行；可关联call都经Policy，顺序执行、失败后停止后续；每call恰一ToolMessage，原id/name/raw_args保留 |
| 超时取消/观察重进 | 默认不重试工具超时，明确安全瞬时错误才只读额外重试；取消传播并停止后续；observe重进不重调handler或重计数 |
| PG与种子 | 当前编号迁移/版本/checksum/表约束、Decimal和固定时间；五条双用户样本；重跑不增加/重置付款或退款状态；测试目标及精确恢复 |
| 订单结果 | 真实本人get/list、不可见/不存在、空页、DB故障可区分；源行→ToolMessage→facts→公开摘要一致，金额精确，模型伪造物流/金额不公开 |
| 专业主图 | 七节点实际编译与正式Runtime路径；缺参同Task新Run及预算继承；唯一Response及run_finish，私有工具历史不进SSE |
| 真实模型联调 | 核对开发方实际provider/model/完整工具Schema、原生ToolCall/配对ToolMessage及真实源行记录；按需要独立显式少量真实模型+PG复现，默认回归不付费 |
| 后继边界 | Refund/Knowledge仍capability_unavailable，无审批/退款/持久恢复/RAG/Store假完成；02互斥/查询/订阅公共契约回归 |

D03描述的04/05扩展保持后继契约，不要求03实现PreparedToolAttempt、VerifiedApproval或Memory副作用。新迁移编号已占002，D03明确按下一个未占编号实施，003是常规实施选择。

## 3. 执行要求

使用项目 `.venv\Scripts\python.exe`。先审查已有测试可信度与必要边界，再进行受影响验证和一次完整既有回归，记录实际passed/failed/skipped，依赖变更才核对依赖清单/pip check。运行Ruff lint及执行代码format，六份设计示例原遗留单列。真实服务调用以实际安装API与配置为准，不升级依赖或切换provider掩盖问题。

真实数据库只用已配置agent_demo_test，连接前验证目标/current_database/current_user及迁移版本/checksum。测试前后核对schema、完整Session及订单行集和必要状态，保留已有种子/用户数据，不使用全表删除或测试数据重置。可在事务回滚或自身唯一数据范围验证约束/状态，记录精确清理。应用库只读现有交付事实时需说明，测试写入仍限专用库。不升级迁移、重建环境或改密码。

保持pytest默认插件和fd捕获。连接或配置探针在插件外时同样安全捕获，输出仅固定类别/布尔值及脱敏摘要，禁止真实凭据/URL或异常全文。用户接受的历史凭据暴露/密码复用为RISK-02-CRED遗留且暂缓换密，本轮后续输出仍应脱敏。额外模型调用只为冻结真实联调门禁，单独显式记录必要少量，不进入默认测试。

## 4. 交付

报告保存 `docs/question/03-tool-governance-qa-report.md`。包括六Task及矩阵逐项结论、审查文件、实际命令/结果、真实PG/模型证据边界、独立补测及数据清理、实现/设计偏差、遗留和是否支持阶段验证通过。

问题按03-QA-001递增编号，每项提供等级、事实、对应设计要求、准确代码位置、稳定复现步骤、预期/实际、影响及证据与修复建议，区分真实Bug、环境/配置、设计允许限制和04/05后继工作。严重度使用P0～P3，主Agent逐项裁决后交修复及独立复测，不由QA改被测代码或降低测试标准。

结束向主Agent回复报告路径、验收结论及问题摘要。阶段正式验收及Git归档、04切换等待用户确认。
