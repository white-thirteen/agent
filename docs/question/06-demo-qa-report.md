# Task6.3.1 独立 QA 报告

2026-11-15；结论：**FAIL，仅限 Task6.3.1**。发现 **06-QA-001 / P2**，已真实 PostgreSQL 复现。退回原 Implementer 修复后由原 QA 独立复测；本结论不替代主 Agent 裁决或用户阶段验收。

依据 AGENTS/STATE、[当前执行任务](../06-demo-execution-task.md)、[最新 QA 分工](06-demo-qa-task.md)、D06 Task6.3.1/第8～9节、[交付报告](../06-demo-delivery-report.md)、演示说明、接口说明及实际 API/脚本。默认只读产品、既有测试、配置和旧证据；仅新增本报告、独立探针及证据，未代修。

## 06-QA-001 / P2：重复 prepare 误清理既有演示数据

位置：`scripts/demo_session.py:54` 的 `folder.mkdir(..., exist_ok=False)` 与 `scripts/demo_session.py:200` 的异常清理判断。

首次 `prepare --folder <本轮新目录>` 成功后，再对**同一个目录**执行相同命令，目录创建按预期抛出 FileExistsError；但 `main` 捕获后仅检查该目录是否有 `protected.pickle`，便调用 `inspect(folder, cleanup=True)`。该文件属于上一次成功准备，第二次调用没有创建目录或写入 fixture，却删除上一次的订单和语料。若其后已开展演示，清理代码还覆盖 manifest 用户的 Store、session/Saver 线程、审批及申请；这一扩大影响为源码确认，本轮未创建这些对象，不冒称全部实际复现。

独立实际复现使用唯一 UUID 自有数据，目标在线核验为 agent_demo_test / agent_test；原 `.env`、模型/provider/预算、006 和固定五订单保持。命令均用项目 `.venv`：

1. 执行 [独立探针](06-demo-qa-probe.py)：`-c "import runpy; runpy.run_path('docs/question/06-demo-qa-probe.py', run_name='__main__')"`。
2. 探针以新临时目录调用正式 `-m scripts.demo_session prepare --folder <本轮目录>`，退出0。实际读库确认两条自有订单和本轮真实 Qwen CPU/1024 维向量存在。
3. 同目录再次调用正式 prepare，退出1，捕获 FileExistsError；再次实际查询，两条订单和知识 chunks 均变为0，同时新增 `prepare-failure-cleanup.json`。
4. finally 显式执行 cleanup，退出0，`protected_unchanged=true`。本轮全13张 public 原行集/列定义和001～006 checksum保持；最终指纹还与前序631最终审计完全相同。

[真实复现证据](06-demo-qa-reprepare-evidence.json) 保存两次退出码、实际前后行数/向量维度、全表指纹及清理结果。探针外层退出0表示**缺陷成功复现及清理成功**，不表示产品行为通过。

影响：操作者误重复准备、恢复终端命令或复用已存在目录时，会意外销毁正在演示或留待原审批恢复的本轮事实；违背已有目录应拒绝覆盖、异常只清理本次部分写入的边界。无需触及固定五订单即会发生。

修复验收：已存在目录在拒绝 prepare 后，原订单、向量、manifest、保护基线及其他关联/目录文件/既有数据库行集完全不变；同时保留当前调用真正创建的新目录中本次 prepare 部分失败的精确清理能力。应退回原 Implementer，不以说明“不要重复命令”代替修复。

## 本轮通过的独立检查

| 检查 | 实际结果与边界 |
| --- | --- |
| 三份 JSON 与实际应用契约 | [独立材料探针](06-demo-qa-contract.py) 退出0；[证据](06-demo-qa-contract-evidence.json)。OpenAPI 覆盖实际11路径，当前应用生成的全部 Schema 与导出同名 Schema 一致。导出额外补充了未注解返回值的响应模型，不误判为契约差异。 |
| 集合请求 | 六组1/6/2/6/2/9，共26请求；每个 method/path 命中当前 API；替换变量后实际 Pydantic 请求校验通过。普通请求、原审批决定、resume及repair空对象一致；全部 noauth，无管理 Header 或客户端 Actor。 |
| 模板 | 12变量，仅回环 URL、示例会话和空值；没有模型/DB/管理秘密，历史 task/run/approval/application/digest 均未硬编码。 |
| 动态提取代码 | Node `vm` 实际执行全部3脚本、共15受控分支；当前Task提取申请/审批、详情digest、新resume Run、null Run及null当前Task通过。null不会擦除原 Run。此为受控脚本行为，未称为 Apifox 脚本运行。 |
| Memory示例 | 保存/查看/修改/删除/清除文案与当前确定性解析语法一致；同一chat入口，保留 revision/last_mutation 的说明准确。 |
| UUID准备与回收 | 正式 prepare 真实加载本地 Qwen、落库1024维语料与两个独立订单；失败路径真实复现如上，最终按自身manifest清理通过。没有替身、seed、固定订单写入或付费Chat。 |

材料探针第一次因过严要求“导出components必须完全等于未增强的app OpenAPI”失败；查明只有导出额外响应模型后，改为逐个核全部实际同名Schema，并通过。此为 QA 探针修正，未修改产品/材料或正确业务预期。

## 实际导入、复用与未验

用户已手动导入 Postman 集合并确认完成；主 Agent 派发记录明确用户截图可见项目 Agent Engine Demo Task631、六组26请求及12模块变量。本轮依最新分工采用**用户回执及截图**作为实际导入证据，没有再次控制GUI，也不冒称 QA 亲自执行了客户端导入。交付报告/说明中的“尚未导入”反映其交付时点，后续状态材料应补充最新用户回执，保留旧证据。

明确复用实施方631 [首段](../06-demo-before-restart-evidence-20261115-r1.json)、[完整重启恢复/RAG](../06-demo-after-restart-evidence-20261115-r1.json)、[第二次重启Memory](../06-demo-memory-restart-evidence-20261115-r1.json)、[进程与最终审计](../06-demo-final-audit-20261115.json)，**本轮未再跑三段TCP/付费Chat**。独立读原始事件/事实并执行断言：三段result均PASS，原task/thread/call/raw/canonical/operation/application/approval/digest/namespace/interrupt保持，SUCCEEDED与REJECTED两个订单标记对应，Actor均local-demo-approval，正常END重复恢复复用结果；RAG正文明确普通聊天不能审批、独立本地入口及固定审计Actor，sources指向实际本轮文档/version/chunk；Memory最终preferences={}、revision=5且last_mutation存在，B为空。该复用只覆盖原成功路径，不抵消本轮发现的脚本缺陷。

前序 [6.2.1独立QA](06-persistence-fault-qa-report.md) 已实际验证完整自有进程重启、并发resume唯一受理、原operation复用及Checkpoint结果保存故障后零退款handler再调用；[6.2.2独立QA](06-isolation-degradation-qa-report.md) 覆盖隔离/降级与来源边界。本轮不机械重跑31故障服务或完整225项；完整PG门禁来源仍为前序 [225 passed / 0 failed / 0 skipped](../06-state-events-full-regression-evidence-20261114-r2.json)，包括原seed窄例外，无deselect。

**未验证项**：Apifox导入后的后置脚本真实执行、变量实际回填及SSE客户端界面效果未实测；截图只能证明导入及变量可见。材料已有人工复制原关联的操作路径，当前未发现该部分明确产品缺陷，不能记GUI全场景PASS。可由主 Agent 在后续632材料中跟踪，最终用户验收仍需真实反馈。当前FAIL来自06-QA-001，不由这些未验项推定失败或成功。

## 数据和进程保护

独立准备子进程顺序运行且已全部退出，本轮没有启动FastAPI服务，不存在自有服务监听或待停止PID；只用单Qwen实例，没有杀用户进程。没有Git写操作、SSH、PG/容器重启、Bridge、另派Agent、业务代码/既有测试/配置改动或进入下一Task。完整本地保护快照留本机临时目录供追溯，未导出库原始行集或凭据；证据仅含自有UUID和指纹。只读为行为约束，不声称另有隔离沙盒。

完成停止，交主 Agent 退回原 Implementer处理06-QA-001；修复后需独立复测再裁决。
