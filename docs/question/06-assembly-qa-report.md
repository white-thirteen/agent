# Task6.1.1 独立 QA 报告

2026-11-14；结论：**PASS，仅限 Task6.1.1**。无新增产品问题，无待关闭的 06-QA-001 等问题。未作阶段正式验收，未进入 6.1.2。

依据根 AGENTS、[执行任务](../06-assembly-execution-task.md)、[QA任务](06-assembly-qa-task.md)、D06 第2～4/6节与6.1.1及[交付最终补充](../06-assembly-delivery-report.md)。独立检查当前源码、实际测试与原始 JSON；没有以实施者自评替代检查。仅新增本报告、[QA探针](06-assembly-qa-probe.py)与[QA证据](06-assembly-qa-evidence.json)，未修改业务代码、既有测试、配置或旧证据。

## 亲自执行

项目 `.venv` 解释器执行 `docs/question/06-assembly-qa-probe.py`。进程内读取 Settings 测试 DSN，严格限定 agent_demo_test/agent_test，不输出凭据。以下七文件独立定向回归：

- tests/test_resources.py、tests/test_application.py：18项，正常/缺模型与业务池/Saver、Embedding/KB/profile/Store失败、Graph中途初始化异常、安全health、503、资源反序关闭、执行取消后再释放依赖。
- tests/test_knowledge_graph.py、tests/test_memory_reader.py：37项，来源/权限/预算/私有消息、三专业共享Reader、显式语言与风格优先级、Store任务关闭。
- tests/test_knowledge_postgres.py：真实PG 2项，真实向量列/余弦SQL、兼容与错误profile、来源版本变化拒绝、Saver持久数据。
- tests/test_memory_postgres.py、tests/test_memory_manage_postgres.py：真实PG 5项，跨thread/进程Store、非object损坏profile、revision/幂等/unknown、写前sync失败、重入只核对原操作、精确清理。

实际结果：**62 passed、0 failed、0 skipped、0 deselected，29.49秒**。两条 anyio/langsmith AssertRewriteWarning 来自快照依赖先于 pytest 初始化导入。独立 collect-only 核对为62项；没有重复执行全量门禁。

回归前后调用 database_snapshot：在线身份正确、001～006完整checksum一致，全部public表完整行集/列定义相同；各既有用例的UUID fixtures自行finally清理。QA没有调用固定订单seed例外，也未增加固定订单写场景。

随后在同一正式 create_app 实际生命周期内启用原Qwen CPU/1024，使用UUID测试用户及命名PG连接，未替换Model、Saver、Store或Retriever。真实业务池/Saver/Store、实际Chat客户端与Qwen初始化；HTTP /health 返回agent_ready/knowledge_ready=true和全部资源ready。冻结Registry的订单、退款、知识、偏好读写工具均启用，实际repository.check_ready通过。生命周期前中后public数据保持一致，普通startup未导入知识或seed。退出后业务池/Saver池关闭、模型两HTTP传输关闭，命名PG连接 **0**、Qwen线程 **0**、额外async Task **0**。本探针无付费模型请求，不宣称独立复测Chat网络可达性。

QA探针首轮在真实startup后误读 ModelGateway.model（实际字段为_model）而退出1；AsyncExitStack完成清理。修正QA脚本后仅以 `--factory-only` 重跑真实生命周期，退出0/PASS，未重跑62项测试。另一个只读Router检查最初误读新版FastAPI的_IncludedRouter.path，改用实际OpenAPI核对：test含5条管理路径，production为0；源码仅注册approvals Router一次。这两项为QA探针错误，无对应产品缺陷。

独立实测当前en+detailed偏好提示 **89 cl100k_base tokens ≤128**，含English枚举映射、explicit > stored > question/default层级；受控图实测明示中文/简短请求仍保留在实际生成上下文。未把受控输出视为真实模型override验证。

## 源码核查

- app/main.py:53/138：唯一资源所有者与Runtime，共享Gateway、Registry、Policy、Executor；真实专业/Memory图接线，root持PG Saver。app/graph/builder.py:44及三个专业/Memory图compile核实：仅根传Saver，子图默认继承；无运行入口Stub。
- app/main.py:256与app/knowledge/repository.py:15：启动只读ready检查、vector(1024)/当前profile一致性；失败禁用知识工具而独立保留其他能力。运行中知识池/查询错误经现有handler安全返回，Store读取降级/显式unknown沿既有治理。health是启动资源视图，model initialized不声称网络调用成功。
- app/runtime/agent_runtime.py:1284、app/infrastructure/store.py:36：先Runtime沿既有5秒窗口收敛/取消并await，再Store批处理await/池、Embedding排空、Chat传输、Saver池、业务池；部分初始化反序释放。取消不被解释为业务未提交，原unknown/operation核对保持。
- app/graph/transfers.py：可信身份/Task显式输入及结果关联核验，不合并子图私有历史。app/api/dependencies.py与approvals.py：普通scope无审批权，Actor为服务端固定审计，development/test本地入口，production不装配。
- app/graph/specialists/preferences.py:94与knowledge/builder.py:372：en明确映射English，明示要求优先；知识生成默认concise允许detailed覆盖。未增加rewriter、翻译、模型轮次或预算，未见旧“Use the question's language”冲突规则。

## 归因复用并独立核验的证据

[实施者R5](../06-assembly-real-evidence-20261114-r5.json)为一次预定双题、同app Memory→两个独立知识会话→Order→Refund真实Gate→本地REJECTED→原Task收敛。未再次付费重跑该流程。

亲自解析两个知识case：正文均为英语，无中文混入；分别明确普通聊天/聊天同意不能批准模拟退款、须独立本地入口、决定由服务端固定演示操作者记录，与corpus中文事实一致。两题均读取revision1的answer_language=en，无明示英语请求；每题4次模型/3次工具，read_preferences/search_knowledge/validate_knowledge_sources各一次success。独立比对result.sources与search证据的evidence_id/document/version/chunk，均对应自有当前文档，validate.valid=true、invalid列表空且checked_at对应；不是仅凭“有引用”判断语义正确。

R5订单事实12.34 CNY、模拟标记，退款原operation与审批绑定、REJECTED审计Actor/local-demo-approval、订单未退款及Task rejected一致；public前后摘要完全相同，PG17.6/vector0.8.7、Saver0～9、Store0～3、关闭连接/线程0。此处业务行为与当时SQL/Saver验证归因于实施探针，QA没有把已精确删除的fixtures描述为本轮重新在线验证。

[最终完整PG门禁](../06-assembly-full-regression-evidence-20261114-r2.json)及交付补充：**224 passed/0 failed/0 skipped/0 deselected，75.53秒**，原样包含唯一获批seed幂等测试；前后全public行集/列定义一致。核对原tests/test_order_postgres.py无diff，未改正确断言；本轮复用该最终门禁及Ruff/8文件格式通过证据，不重复无新变化的全量执行。首轮221 passed/1 deselected、首次完整223 passed/1 failed和R1/R3/R4语言失败均保留，未算入最终通过证据。

R5后仅恢复既有“explicit language/style instructions take precedence”同义优先级句；当前89 tokens与源代码核查及62项独立回归通过。该措辞不增加新语言行为，R5按任务授权归因复用。

## 遗留风险与范围

语言遵循结论限预定两题真实证明；真实模型明示中文override/详细风格未另付费验证，只有实际Prompt契约与受控图验证。引用校验不自动证明任意回答语义。health不持续探测供应商网络；运行中故障仍由既有handler处理。Store/退款unknown不承诺全局Exactly Once，单进程锁和本地演示身份边界保持。

完整重启/故障组合、跨场景隔离退化、Apifox及部署验收属于后续Task，本轮未进入。未Git写操作、Bridge、SSH、重启PG/服务或重建容器，未使用子Agent。完成后停止，交主Agent复核。
