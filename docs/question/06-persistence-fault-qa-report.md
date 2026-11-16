# Task6.2.1 独立 QA 报告

2026-11-14；结论：**PASS，仅限 Task6.2.1**。未发现需退回 Implementer 的产品或验收阻塞问题，无新增 06-QA-001。阶段验收和 Git 归档由主 Agent 与用户决定。

依据 AGENTS/STATE、[冻结执行任务](../06-persistence-fault-execution-task.md)、[QA任务](06-persistence-fault-qa-task.md)、D06第6节/Task6.2.1及故障矩阵、[交付报告](../06-persistence-fault-delivery-report.md)。独立阅读实际代码和原始成功/失败证据，未修改业务、既有测试、配置或旧证据。

## 独立实际执行

使用项目 `.venv/Scripts/python.exe`，真实 agent_demo_test / agent_test、PG17.6 / pgvector0.8.7。没有付费 Chat；受控 Provider 只给出路由及原始退款 ToolCall。正式 create_app 装配真实 Saver/Store、本地 Qwen CPU/1024、Registry/Policy/Executor、根图和专业子图。Qwen 本轮验证资源装配与就绪，不把退款场景称为新增向量检索或真实 Chat 语义验证。

| 命令/检查 | 实际结果 |
| --- | --- |
| `-m scripts.verify_06_persistence_faults --output docs/question/06-persistence-fault-qa-real-evidence-20261114.json --modes normal checkpoint` | 退出0，2场 PASS，6个独立服务进程，真实 HTTP/TCP。逐个停止旧进程树后再启动新进程，单 Qwen 实例。 |
| `-c "import runpy; runpy.run_path('docs/question/06-persistence-fault-qa-audit.py', run_name='__main__')"` | 退出0，QA621_AUDIT_PASS；独立语义断言、在线身份/全迁移 checksum、public 全行列及记录 PID 最终审计通过。 |
| `-m ruff check scripts/verify_06_persistence_faults.py` | 退出0，All checks passed。 |
| `-m ruff format --check scripts/verify_06_persistence_faults.py` | 退出0，1 file already formatted。 |

[独立进程证据](06-persistence-fault-qa-real-evidence-20261114.json)、[独立审计探针](06-persistence-fault-qa-audit.py)、[独立最终审计](06-persistence-fault-qa-final-audit-20261114.json)。独立审计读取事实及调用既有只读快照工具，没有替换产品行为。

normal：实际服务 PID 17624→52436→22380，旧 launcher/server 与命令、时间、退出记录齐备。初始真实 interrupt 已保存；新进程空 Runtime 读回原 Gate，根 Command/子 None 恢复。两个客户端并发 resume 返回202和409/thread_busy，恰一个受理。成功后再完整退出并启动第三进程，END resume 返回200/accepted=false/run_id=null，Run、Graph、退款 handler 均为零。原订单已退款且成功申请恰一条。

checkpoint：实际服务 PID 44300→21760→47444。第二进程真实事务已 SUCCEEDED，随后结果 aput/aput_writes 受控失败，原子图 next=execute_refund；不是回滚后假成功。第三进程按原 operation 核对成功，根/子 None 重入，原 execute_refund 节点收到 succeeded context；**退款 handler 为零次**，成功申请仍一条，未发生第二次订单变更。其后 END 查询无新增 Run/Graph/handler。

两场都保持原 user/session/thread/task/workflow/call/name/raw/canonical args/digest/application/operation/approval/child namespace，task=workflow；审核人为 local-demo-approval，同决定重提不改审核事实，相反决定409。原 ToolMessage ID 恰为 `tool:{task_id}:{call_id}`，仅一条配对。normal 的模型次数2→3、工具5→7、主动时间309→1050ms；checkpoint 的模型2→3、工具5→7、主动时间471→5794ms，恢复没有重置用量，原Task对应新Run。

## 源码与复用证据

- `scripts/verify_06_persistence_faults.py:62` 的验证工厂仅控制 Chat、显式 Saver/handler前/绑定故障及观测。被包装的原 AsyncPostgresSaver、MockRefundService.execute_original、ApprovalService 和 CompiledStateGraph 方法仍被调用；没有替换退款事务、审批 Gate、Policy 或执行结果。观测节点 await 原节点，未跳过原图流程。
- `app/main.py:137` 的实际装配使用持久 Saver 和共享 Store、原注册表及三个专业图；测试调用同一 create_app 生命周期。Windows launcher/server 双PID与完整进程退出证据成立，不是同进程 Runtime 重建。驱动只 taskkill 自有 Popen 树；独立最终查询12个记录 PID 均不存在，没有终止其他进程。
- `app/runtime/refund_checkpoint.py:58` 核可信身份、原call和规范参数、原namespace、interrupt和安全位置，END须已有匹配持久结果。`app/runtime/agent_runtime.py:314` 先分类，END直接返回，unknown拒绝；Gate后核原operation及准备标记，并保守继承预算。`app/graph/specialists/refund/builder.py:134` 的 succeeded guard 校验关联和成功事实后返回，execute_refund在调用 Executor 前执行 guard，因此独立观测到的零Domain入口与零退款写工具尝试相符。
- `app/domain/refunds.py:311` 的真实事务再次锁定订单、申请和审批，核身份/金额/原call/批准期限；`app/workflows/approvals.py:274` 在POST resume行锁后用DB时间惰性转换PENDING过期，APPROVED决定保留。没有把Prompt或受控Chat当成授权依据。

独立检查实施方 [R3](../06-persistence-fault-evidence-20261114-r3.json)、[R4](../06-persistence-fault-evidence-20261114-r4.json)、[R5](../06-persistence-fault-evidence-20261114-r5.json) 的12场/31服务进程及[最终审计](../06-persistence-fault-final-audit-20261114.json)。其余拒绝、repair、确认未执行、pending writes未知、准备屏障失败、三种过期、业务读取unknown及missing本轮**复用实施方实际证据，没有冒称独立重跑**。这些证据记录拒绝零写、repair原绑定/幂等/未绑定禁止决定、新attempt受控执行、unknown/missing 409且零Run/Graph、APPROVED过期保留决定禁写、成功op过期只复用，结果与源码一致。审批期限未因resume续期。R1/R2的KeyError失败保留，未算通过；其后修正的是并发响应探针解析，未改产品或弱化唯一受理要求。

未变04细分边界沿[04最终独立复测](04-hitl-checkpoint-refund-fix-02-regression-report.md)；本Task仅新增验证驱动，无新增生产/迁移/依赖修改。复用[6.1.2完整真实PG门禁](../06-state-events-full-regression-evidence-20261114-r2.json)：225 passed / 0 failed / 0 skipped，原seed窄例外实际通过，无deselect。另复用[本Task实施方21项定向回归](../06-persistence-fault-targeted-evidence-20261114.json)：退出0、无失败跳过；原JSON计时16.572秒，交付正文15.48秒有小幅计时出入，结果以JSON为准。本轮没有机械重跑完整门禁及相同定向组合。

## 数据保护及遗留风险

每场开始和结束实际在线核 test身份及001～006全部本地/登记checksum，比较所有13张public表完整行集与列定义。UUID订单、会话、审批/申请及Saver自有线程按明确归属精确清理。独立最终快照同时等于两场QA开始/结束及6.1.2最终完整门禁结束值；固定五订单未修改、未seed、无残留业务行或Saver数据。`.env`、006、原seed测试及两角色文件前后SHA256一致；旧证据、六项暂缓差异和用户改动保留。只读为行为约束，不声称另有权限隔离。

没有新增编号问题。保留前序Store关闭后即时视图历史波动的未定因风险；本轮跨进程验收不将其称为已修复。未知快照、无可信准备窗口和业务核对读取失败仍拒绝盲恢复；此为冻结边界。没有重启PG/容器、SSH、杀用户进程、Git写操作、Bridge、另派Agent、付费模型或进入下一Task。全局Exactly Once、多worker互斥、任意Python位置冻结及SSE持久重放未验证，也不由本PASS承诺。

完成停止，交主Agent复核；本结论不代替06阶段正式验收。
