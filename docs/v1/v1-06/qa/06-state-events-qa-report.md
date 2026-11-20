# Task6.1.2 独立 QA 报告

2026-11-14；结论：**PASS，仅限 Task6.1.2**。未发现需退回 Implementer 的明确产品缺陷；无新增 06-QA-001。阶段正式验收、Git 归档与后继 Task 不在本结论内。

依据根 AGENTS、STATE、[QA 任务](06-state-events-qa-task.md)、[执行任务](../06-state-events-execution-task.md)、[交付报告](../06-state-events-delivery-report.md)、D06 第5/6/9节及6.1.2。独立检查实际源码、既有断言和交付原始成功/失败证据；未修改产品、既有测试、配置或旧证据。

## 实际执行与复用

所有命令使用项目 `.venv/Scripts/python.exe`。真实库 DSN 从 Settings 安全读取，仅在测试进程注入；不输出凭据。在线确认 agent_demo_test / agent_test、001～006全部迁移 checksum、13张 public 表完整行集及列定义。

| 独立执行 | 实际结果 |
| --- | --- |
| `-m pytest tests/test_runtime.py tests/test_runtime_http.py -q` | **20 passed，4.25秒**；无失败/跳过。新Task首快照窗口、澄清/预算、去重冲突、缓存、Owner各出口、断开继续、无token重放及run_finish失败路径通过。 |
| `docs/v1/v1-06/qa/06-state-events-qa-probe.py` | 退出0；独立12次Store关闭观察通过；内部原样运行 `tests/test_memory_postgres.py::test_real_store_cross_threads_process_persistence_and_exact_cleanup`，**1 passed，4.88秒**。两个既有 AssertRewriteWarning 来自先导入快照工具，不影响断言。 |
| `-m scripts.verify_06_state_events --output docs/v1/v1-06/qa/06-state-events-qa-real-evidence-20261114.json` | 退出0；正式 create_app + 真实 PG/Saver/Store/Qwen CPU1024，Chat受控，组合协议通过；public全行列相等、UUID精确清理。 |
| `-m ruff check app scripts tests` | 退出0，All checks passed。 |
| 独立最终只读核对 | public全行列同时等于独立开始快照和 Implementer 最终完整门禁结束快照；本轮命名Store/协议连接0。 |

详细证据：[独立Store观测](06-state-events-qa-evidence-20261114.json)、[真实组合](06-state-events-qa-real-evidence-20261114.json)、[最终保护核对](06-state-events-qa-final-check-20261114.json)。独立探针仅记录关闭对象状态并调用原始 `AsyncConnectionPool.close`，不改变产品关闭逻辑，不修改原用例断言；原用例执行时没有该观测 patch。

本轮未重复完整回归，复用当前最终实现的 [225 passed / 0 failed / 0 skipped 完整真实PG门禁](../evidence/06-state-events-full-regression-evidence-20261114-r2.json)。原seed幂等窄例外明确执行并通过，无deselect，前后public全部相等；首轮224 passed/1 failed和定向失败证据仍保留。该JSON elapsed_seconds=60.41，交付正文所写59.50秒与JSON存在小幅计时差，本报告以原始JSON为准，不影响数量和结果。

未改变模型/偏好Prompt/知识工具/资源装配，真实Chat语义和双题英语偏好归因复用 [6.1.1 R5](../evidence/06-assembly-real-evidence-20261114-r5.json)及[前序独立QA](06-assembly-qa-report.md)。本轮确实重验本地Qwen向量/检索，但受控Chat输出不作为真实模型语义或英语遵循证据。

## 源码与实际行为核对

- `app/api/routes/agent.py:35`、`app/services/agent_service.py:29`：Route一次解析body，Service返回context/options并显式传owner；可信session归属和input_mode/request_id完整转交。`app/runtime/agent_runtime.py:716`仅Runtime在thread门禁内创建正式Task，workflow同值；去重仅当前进程窗口，冲突409、缓存清理不冒充业务幂等。
- `app/runtime/agent_runtime.py:1159`：本轮修复在有活动Run时全用其可信Task/workflow/run，拒绝混合上一Task快照。独立单测与真实HTTP阻塞窗口均确认current_task返回新Task/新Run、普通第二输入409；校验旧快照及活动Run身份的边界保留。
- `app/graph/state.py:65`、`app/graph/transfers.py:107`：新Task清理sources/专业结果/偏好读取记录；续接保留原PendingTask/目标/消息范围及累计预算。父子传递采用白名单并校验上下文，没有整份私有历史回传。
- `app/graph/nodes/run_finish.py:13`、`app/runtime/agent_runtime.py:797`：普通Graph以sync持久化返回，Runtime确认scope.finished、身份和累计用量一致后再收敛及公开。run_finish异常没有token，仅安全error/唯一done。公开token可承载完整正文；SSE sequence唯一递增，没有私有planner/结构化消息、权限、raw_args、namespace/Profile/凭据透传。
- 真实同session/thread按 Memory保存→知识问答→订单澄清→补参→新订单Task→退款等待/拒绝恢复串行通过。知识正文逐字等于approved_answer，SSE/RunView来源对应本轮UUID文档及实际有效PublicCitation；Memory sources为空。澄清补参维持原Task，用量累计1→4模型、0→2工具，跨Task来源/专业槽清理成立。
- 真实Gate等待公开为waiting_approval，绑定原call/operation/approval/child namespace，子图与RunView用量相符；父已完成快照可仍running，此为正确观察差异。普通auto/new_task均409。本地拒绝后新Run沿原Task/operation推进，模型/工具累计不重置；run_status=completed、task_status=rejected、订单仍未退款。正常END再次resume返回accepted=false/run_id=null，未增加Run/Chat调用。清空可丢失缓存后Run404，持久当前Task及业务REJECTED仍可查询。
- Owner首次迭代前、响应头/构造失败、中途真实TCP断开、慢订阅、重新订阅不重放旧token沿独立执行的既有20项验证；Runtime强引用执行与订阅资源分离。未知快照拒绝盲恢复，四类恢复继续沿04分类，没有新生命周期或绕过治理。
- Memory unknown字段与核对边界沿未变05代码/既有用例及最终225门禁；本轮没有新增真实unknown注入场景，不将源码阅读称为该故障重新实测。

## Store关闭波动裁决

既有 `tests/test_memory_postgres.py:263/:277` 在实施首轮完整及定向复查曾失败，不能因最终225通过删除或解释为已修复。独立阅读 `app/infrastructure/store.py:36`：资源拥有Store批处理任务和池，finally取消并await批处理，退出Store后await pool.close；安装版本 `psycopg_pool/pool_async.py:497` 等待池worker并关闭归还的客户端；`psycopg/connection_async.py:210`设置closed并调用libpq finish，代码没有等待另一个PG观察会话确认后端退出的屏障。

独立探针对唯一application_name，在关闭前确认后端存在，分别覆盖normal/exception/cancel各4次。12次退出均pool.closed=true、捕获的客户端closed=true，另一条autocommit观察连接在首次关闭后查询即返回空；最终无命名后端。本次未触发后续有界采样分支，因为首次查询已经为0。原既有用例无patch独立1 passed。

**没有观察到持续连接泄漏，也没有证据支持将该现象定为本Task资源残留缺陷。** 客户端关闭与独立服务端观察之间缺少确认屏障，解释了“本地closed”本身不足以证明即时服务端视图必为0；这只是源码支持的时序可能性，未证明历史两次失败确由该原因造成。本轮据真实关闭状态、后端归零、原断言独立通过及最终完整门禁，判断不阻塞6.1.2；保留历史即时断言波动风险，不宣称根因已定位/修复，不新增等待或放宽断言，不要求无限重跑。

## 数据保护、问题与遗留

无新增编号产品问题、无FAIL项。Store即时观测历史波动作为上述非阻塞未定因风险保留；若后续出现关闭完成后后端持续存在或连接数累积，应凭新证据重开问题，不以本PASS覆盖。

独立探针全程保护app/tests/migrations/scripts/.codex及.env/AGENTS摘要，既有文件不变。新增业务数据均UUID自有订单/文档/profile/session/thread，按原FK精确清理；没有新增seed或触碰固定五订单。最终public全部行集/列定义等于开始及完整门禁结束值。保留前序六项暂缓差异和全部旧失败证据，不处理所有权不明的Python进程；本报告不声称已解释那些进程。

未执行付费Chat、SSH、PG重启、杀用户进程、Git写操作、Bridge或另派Agent。完整进程重启、Gate后故障矩阵及后继隔离退化/演示不在本次重验内，不能从缓存清空场景推导完整重启通过。本轮仅写本独立报告、探针及新JSON，完成后停止，交主Agent复核。
