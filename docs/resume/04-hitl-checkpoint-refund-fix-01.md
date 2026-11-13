# 04 首轮独立QA确认问题修复任务

日期：2026-11-13。用户已授权04阶段内普通问题自行协调修复。依据AGENTS、冻结D03/D04、`docs/question/04-hitl-checkpoint-refund-qa-report.md`和开发报告第八轮，不改变冻结规划或进入05。主Agent已审查源码/设计，重跑独立11场景为7 failed、4 passed；六问题均确认。修复只针对以下问题及直接必要集成。

## 确认问题与修复边界

| 问题 | 主Agent裁决 | 要求 |
| --- | --- | --- |
| 04-QA-001 P1 | D04第8.2节两项查询真实缺实现，属于04 | 补POST /agent/tasks/current和/agent/refunds/{application_id}/status。严格沿Route→Service→原Runtime/领域，只读解析已有本人session/快照/退款事实；查询不新建session/Task/Run，不写Graph/审批；不存在或他人统一404，current无任务正确空值，重启旧Run不伪装active。 |
| 04-QA-002 P1 | 受控矛盾场景真实可复现，非声称真实事务自然产生PENDING反转 | PENDING/读不到/超时不能单独证明未执行；结合锁后核对、原快照成功结果/消息/节点/标记检查一致性，矛盾409 execution_uncertain、零新Run/模型/写。确认未执行才经当前权限/审批/资格/预算及本Run新标记sync；成功复用原operation。 |
| 04-QA-003 P1 | 同一预算配置下保守时长耗尽仍发模型，确认 | 阻止主动时间/未知窗口不能可信界定时的新模型及写入，允许只读核对、原call安全闭合及确认事实固定模板映射；不重置额度，不以无deadline运行绕过预算。 |
| 04-QA-004 P1 | 撤权后关闭被Policy拒绝，仍带半配对消息进compose，确认 | 所有非等待终结原call稳定闭合，关闭业务动作失败与消息闭合分离；不能绕过Policy关闭申请，不能将半配对历史送模型；原call_id稳定、内部历史不入SSE。 |
| 04-QA-005 P2 | 既存插件问题，本次新发现，影响验证可信度 | 保持skip longrepr原生tuple结构，逐敏感文本脱敏；同样核对collectreport。保留异常/警告/捕获保护，禁止禁用脱敏、隐藏失败或禁用-rs。用合成无真实凭据输入验证。 |
| 04-QA-006 P2 | D03第5.1/D04第5.2明确本期同Executor交接，不是提前实现Memory | 补齐可选execution_context/business_context的固定准备/执行节点配对、同user/thread/task/run/scope/RunScope/limits、原工具/参数及最小业务快照标记；最终真实节点同Policy重新校验。默认退款保持原model来源/审批。按D05冻结白名单补接口，禁止提前实现/注册MemoryManager/Store/RAG或新增权限框架。 |

复现及证据位于独立报告第5节；仓库外用例 `C:/Users/15294/AppData/Local/Temp/agent04-qa-20261112/test_review04.py`、diagnose_pending.py及pending-evidence.json。先核实这些用例/实际代码，不能通过更改正确预期或删除用例消除失败。原11场景包括两预算场景、两查询参数场景，不能把7失败等同7不同问题。

## 环境与工程保护

2026-11-13用户解释VM关机后已重启并明确授权SSH恢复原服务。主Agent已登录并启动既有agent-engine-demo-db-postgres-1，接回原agent-engine-demo-db_default网络；容器running/healthy，端口仅192.168.150.101:5432，原agent-engine-demo-db_agent_pg17卷保留。无重建/迁移/密码更改。专用测试库agent_demo_test/agent_test在线身份与001～005全部checksum已核对通过，数据库环境阻塞已解除；密码不存项目，修复角色不需要SSH或基础设施权限。

测试只用专用测试库，沿原授权隔离规则创建唯一订单/用户/session/operation/thread，保留固定五订单与他人数据；前后全行集/迁移摘要和自身Saver线程核对，精确按FK及框架线程接口清理。不得使用重跑seed重置固定订单。001～005原字节及登记checksum不可改。应用库事实/其他容器/网络配置不动，不付费默认测试、不泄露URL/凭据。

使用项目.venv；先受影响及独立回归，必要时完整真实库回归。实际PG检查和源码修复证据区分，不将受控图当退款完全重启验收。原04剩余4.3.2全进程/真实SQL与checkpoint故障/真实模型24项门禁仍须后续完成，本轮优先修确认问题，不以修复通过声称阶段完成。库接口先看实际安装版本，不盲目升级。

主Agent协调文档、冻结设计、历史QA/开发记录及六项原暂缓差异保护，不改其他会话文件。必要代码、针对性仓库回归及说明可修改；测试角色外部原始证据保留。不得调用Bridge/其他会话、不Commit/Push、不进入05。

## 交付

必须将修复记录整理到 `docs/resume/record/04-hitl-checkpoint-refund-fix-01-report.md`，关联本提示词、阶段04、涉及六Task、04-QA-001～006、当前HEAD。逐项记录根因、最小修改、文件/接口、实际命令及通过失败跳过、真实/替身边界、数据清理及未完成门禁。普通实现问题自行解决；冻结设计冲突/扩大范围才交主Agent。完成回复报告及摘要，等待主Agent组织独立复测，不自行验收。
