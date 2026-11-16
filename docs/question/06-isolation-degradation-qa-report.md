# Task6.2.2 独立 QA 报告

2026-11-14；结论：**PASS，仅限 Task6.2.2**。无新增产品缺陷或验收阻塞问题，无新增 06-QA-001。完成后停止，交主 Agent 复核；本结论不代替阶段正式验收或 Git 授权。

依据 AGENTS/STATE、[QA任务](06-isolation-degradation-qa-task.md)、[执行任务](../06-isolation-degradation-execution-task.md)、D06 Task6.2.2/第10节、[交付报告](../06-isolation-degradation-delivery-report.md)及实际源码。只新增本报告、独立审计探针与新 JSON，未修改产品、既有测试、配置、旧证据或冻结设计；只读为行为约束，不声称有独立沙盒。

## 独立实际执行

全部使用项目 `.venv/Scripts/python.exe`，DSN 从 Settings 读取且不输出。在线目标 agent_demo_test / agent_test、PG17.6 / pgvector0.8.7。

| 命令或检查 | 实际结果 |
| --- | --- |
| `-m scripts.verify_06_isolation_degradation --output docs/question/06-isolation-degradation-qa-real-evidence-20261114.json` | 退出0，probe_result=PASS；正式 create_app、真实 TCP/PG/Saver/Store/Qwen CPU1024，Chat受控，无付费调用。 |
| `-c "import runpy; runpy.run_path('docs/question/06-isolation-degradation-qa-audit.py', run_name='__main__')"` | 退出0，QA622_AUDIT_PASS；独立核公共事件、四类退化、退款事实组合、记录PID退出、在线完整public指纹和迁移checksum。 |
| `-m ruff check scripts/verify_06_isolation_degradation.py` | All checks passed，退出0。 |
| `-m ruff format --check scripts/verify_06_isolation_degradation.py` | 1 file already formatted，退出0。 |

证据：[独立真实组合](06-isolation-degradation-qa-real-evidence-20261114.json)、[独立审计探针](06-isolation-degradation-qa-audit.py)、[最终在线审计](06-isolation-degradation-qa-final-audit-20261114.json)。复跑实现方驱动之外，独立审计固定核对empty说明原文，检查公共事件没有内部planner/结构化消息、raw_args、scope、namespace、完整偏好或故障注入原文；不是仅采信probe_result字段。

## 实际行为与源码核对

- A/B 均经过正式 HTTP 和服务端 DemoIdentity 解析。B查询A自有UUID订单被拒绝；A通过显式命令保存英语偏好，真实Manager读回en、B为空；B查询A退款申请404。`app/api/dependencies.py:21` 固定服务端scope且无审批scope；`app/domain/orders.py:51`/`:59` 的get/list SQL都约束owner，`app/domain/refunds.py:131` 按用户及会话限制状态查询，`app/memory/manager.py:20`/`:43` 以可信用户构造namespace。list边界本轮结合既有治理证据复用，没有新增独立HTTP list场景。
- 待审批普通chat返回409，伪造permission_scopes和reviewer_id字段各422；独立本地控制面提交后，数据库审计Actor为local-demo-approval。`app/api/schemas/chat.py:13`、`app/api/routes/approvals.py:34` 拒绝额外字段；`app/workflows/approvals.py:23` 提供固定Actor。回环控制面没有真实管理员认证，body选择允许名单中的A即按A演示身份执行；本PASS不宣称抵抗身份冒用。production禁用与非回环404沿前序装配/路由证据复用。
- 真实TCP在模型被阻塞时关闭，订阅释放时后台task仍未结束；释放模型后同run完成，再订阅无旧token且有done。Owner首次迭代前/构造/响应头失败和慢订阅沿实施方本轮99项及前序独立20项证据复用；没有将ASGI调用冒称本次真实TCP。
- 本地批准及恢复后，真实SQL退款成功；随后独立新会话显式Memory Task在Store aget边界注入OperationalError，任务failed。再次SQL核对订单is_refunded=true、申请SUCCEEDED。没有添加或验证自动MemoryWriter路径，也没有把记忆失败称为退款失败。
- Embedding故障、PG连接故障、model故障均failed、无最终正文及来源；empty为rejected，仅公开固定证据不足summary，无approved_answer或引用。`app/graph/specialists/knowledge/builder.py:330`/`:458`与`app/graph/nodes/result_aggregator.py:15`支持该区别。R2误要求empty所有final_answer为空，是探针契约错误；旧失败保留，本次独立固定原文断言通过，未改产品或放宽来源检查。
- PG故障仅替换KnowledgeRepository.pool连接边界，不是实际停PG；真实Repository负责转换安全错误。empty仅控制search空候选。PG及empty实际经过原Qwen query向量生成；Embedding失败在推理前注入，其余业务只装配Qwen。Chat输出与模型失败受控，不作为真实Chat语义证明。

## 复用、未重验及门禁

独立检查[本轮99项原始逐例结果](../06-isolation-degradation-targeted-evidence-20261114.json)：exit_code=0，99项全部passed、无skip；未机械重复99项。对照既有测试中的关键正确断言：知识失败不公开draft/来源、错call零handler、Memory真实sync失败零write handler、prepare不计尝试、最终Policy拒绝零尝试、原op重入只核对及unknown保留。细分scope/schema/Agent/节点/allowed_tools、Reader分类、版本幂等、入handler读取失败仍计次、跨Thread/进程、预算累计与到限停止，由该99项实际证据及前序独立报告支持；不称为本轮独立注入全部故障。

产品未变，完整门禁复用[6.1.2最终225 passed / 0 failed / 0 skipped](../06-state-events-full-regression-evidence-20261114-r2.json)及[独立QA](06-state-events-qa-report.md)。原seed幂等窄例外原样通过且无deselect；本轮没有新seed。退款unknown/安全快照与完整进程重启沿[6.2.1独立QA](06-persistence-fault-qa-report.md)及其真实进程证据复用，没有重复31进程矩阵。真实Chat来源/语义与英语偏好沿[6.1.1 R5](../06-assembly-real-evidence-20261114-r5.json)及[独立QA](06-assembly-qa-report.md)复用，本轮不重复付费。全app/scripts/tests Ruff通过采用实施方记录，本轮独立检查新增实现脚本。

## 清理与遗留风险

本次驱动开始/结束核专用身份及001～006全部本地/登记checksum，比较全部13张public表完整行集和列定义；UUID订单、申请/审批、session、Saver原thread及A profile按归属/FK精确删除。独立在线最终快照同时等于QA开始/结束及6.1.2完整门禁最终值；固定五订单未写、无残留行。`.env`、006与原角色文件SHA256前后一致，旧证据及六项暂缓差异保留。

本机服务是本次Python进程内的uvicorn任务，finally结束且记录PID已不存在。没有按唯一application_name额外统计关闭后PG连接数，不宣称完成此项计数；前序Store关闭即时视图历史波动仍未定因，本次无持续残留的新证据，不将其描述为已修复。保留unknown须核原operation/revision/last_mutation并暂停profile新写的操作限制、单worker互斥范围及SSE无持久重放边界。

未执行Git写操作、Bridge、SSH、PG重启、杀用户进程、另派Agent或下一Task。无FAIL项，完成停止。
