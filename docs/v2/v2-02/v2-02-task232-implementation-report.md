# V2 02 Task 2.3.2 实施交接

当前实现、真实组件和回归证据已整理，交主 Agent 审查及整 Task 独立 QA；不代表阶段 VERIFIED 或用户 ACCEPTED。固定语义夹具、冻结设计及验收标准未改，正式库、`.env` 和 Git 未操作。旧版本引用仍保留，正式部署需另行授权数据库迁移及上下文限额配置；默认未配置 V2 上下文窗口和输出限额时沿既有 V1 行为。

## 实现与边界

- `app/context/migration.py` 和 `app/runtime/agent_runtime.py`：在正常新 Task 且当前旧 Task 安全结束时，只读同会话 Saver 历史；按最新 Task 快照和完整消息 ID/正文、所有者、Task/workflow 与终态证明补充公开热消息元数据。不能证明的消息保留原文，状态标记 `incomplete`；未知 Run 不猜测。补充信息随正常新 Task 写入，不改写旧 Checkpoint，不从历史猜测审批、偏好或当前业务事实，也不在活动、澄清、审批或未知恢复时升级。
- `app/main.py`：旧 Memory 切换门禁保留；Saver 初始 `input / step=-1` 且只有 messages 的快照，仅当已有后续已识别 Task 时可跳过。孤立未识别输入、未安全结束的旧 Memory Task 仍阻止切换。此修复解决真实退款恢复测试中应用重启被误拒的问题。
- `app/context/compaction.py`、`app/runtime/model_gateway.py`：摘要来源以独立 JSON 数据传递，保留 user/assistant 角色、原文、顺序及可选已有摘要；系统指令独立。v5 仅保留直接陈述的状态、不从未提及推断事实，并仅对摘要请求绑定 `temperature=0`。实际格式化后输入受预算检查；`finish_reason=length` 记录已耗尝试和用量后拒绝发布摘要。旧摘要引用和回执按原版本核验，v5 新生成不复用旧提示缓存。
- `app/infrastructure/model.py`：仅 `api.deepseek.com` 使用专用 SDK 适配，将最终请求的 `max_completion_tokens` 映射成该服务 Chat Completions 使用的 `max_tokens`；其他 endpoint 保持原 SDK 行为。摘要模型的温度设置是发送策略，不保证确定性或所有历史的语义正确。

## 功能与回归证据

- 最终代码的 [完整隔离库门禁](evidence/v2-02-task232-full-regression-r3.json) **290 passed / 0 failed / 0 skipped**，342.56 秒；[pytest 原始日志](evidence/v2-02-task232-full-regression-r3.log)。包含真实本地 Qwen、PG/Saver/Store、V1/V2 01 测试及原固定订单 seed 幂等窄例外，未 deselect。实际 Qwen/PG 应用启动、健康检查和关闭通过，未遗留 Qwen 线程或后台任务。保护快照通过，水位 36→47 与事前审计的 +11 一致。
- 真 Saver 旧快照和真实新 Runtime Task 接线验证了可证明消息补足、未知消息保留并标记 incomplete、原 Checkpoint 不变；受控和隔离库定向见 [首次组合](evidence/v2-02-task232-targeted-first.txt)与 [fix03 组合](evidence/v2-02-task232-fix03-controlled.txt)。退款、切换门禁及资源关闭的真实 PG/受控模型定向 **19 passed**，见 [输出](evidence/v2-02-task232-regression-fixes-r2.txt)。结构化偏好 HTTP、Store、幂等和 UNKNOWN 路径由完整回归及前序 Task 的真实组件测试覆盖；客户端仅静态/程序化检查，Postman 脚本和 UI 未实测。
- 实际独立进程在受控模型调用内被终止，另一新进程读取真实隔离 PG 持久预算并恢复，已预留次数未退回、未知用量未记零，余下预算及耗尽约束保持；[定向测试](evidence/v2-02-task232-kill-restart.txt) **1 passed**。这是受控模型在途进程终止，不是外部模型在途终止或机器断电。其余归档、部分提交、并发、采纳、回执及关闭故障证据沿用前序 Task 原始记录及本轮回归，不把持久状态模拟描述为实际断电。
- [真实 V2 Runtime 探针](evidence/v2-02-task232-runtime-probe.json)启用窗口16384、输出512、摘要输出256：真实外部模型、OrderAgent 和工具查询本轮唯一隔离订单，结果 paid、12.34 CNY、未退款，与当前 PG 一致；下一个 Task 实际注入该 Task 两条公开消息。应用关闭重启后同一 thread 绑定和原待澄清 Task 恢复；唯一数据已清理且保护快照通过。另一个无历史会话由于知识功能关闭返回 capability_unavailable，不能作为相同节点的资源对比。
- [真实 Qwen/BGE/Hybrid 组件探针](evidence/v2-02-task232-real-hybrid-r2.json)在隔离库导入事前确认不存在的六篇原样本，对两个原 query 直接检索均 found 且当前 Evidence 校验 valid；精确删除后保护快照通过，水位24→36对应六次导入和六次删除。该项为直接检索组件，不声称本轮真实外部模型 Knowledge Graph 回答；当前 Query/Evidence 的 Graph 接线另由受控模型的真实 PG 回归验证。
- fix02 的 [真实低限额 wire 回执](evidence/v2-02-task232-fix02-limit.json)仅含脱敏参数和 usage：真实 DeepSeek 请求 `max_tokens=8`、响应 output=8 且 `finish_reason=length`；维护预算真实持久预留1。受控 HTTP 覆盖普通、结构化、运行内摘要和独立维护请求字段，真实本机 PG/文件验证截断后 Archive 保持 READY、维护 FAILED、无 Summary。修复前真实输出异常和其不可追溯的请求明细按 [fix02](fixes/records/v2-02-task232-fix02-report.md) 原样保留。
- 项目 `.venv` 的本轮相关文件 Ruff check 和 format 检查通过；主 Agent 在依赖未变化时执行 `pip check`，无依赖冲突。修复后仅对 `app/context/manager.py` 做了空行格式调整，未改变行为。

## 摘要质量与资源

修复后 v5 以真实 DeepSeek、LangMem、Gateway、独立持久维护所有者、隔离 PG 和文件完整执行固定八例一次，所有生成文本、来源、覆盖和 known 用量见 [r6 原始结果](evidence/v2-02-task232-quality-r6-raw.jsonl)。来源 Task/Run/Checkpoint 是合成夹具。原 QA 对八例的逐项事实、否定、冲突、未知及新增事实给出 [独立复测 PASS](qa/v2-02-task232-summary-quality-fix03-retest.md)；该结论仅覆盖这八例，不代替整 Task 正式 QA，不代表模型对其他历史必然保真。

[当前 v5 资源实验](evidence/v2-02-task232-resource-runtime-r3.json)在真实 Runtime 创建的同一正式 Task/Run 中执行三次真实模型调用。固定长历史、同一实验节点和当前问题、模型、Schema/工具及512输出预留不变，注入24条原文与1条摘要时，供应商 reported input **6958→225**，本地估算 **3394→154**。摘要本身另花 input 6121、output 136、耗时1.70秒，输出上限512、未触发 length；三次调用计入同一 Run 的三次尝试。归档首轮实测文件大小 30,510 字节；该归档数字来自早期 v1 实验，不能称作 v5 重新测量。该单场景测量不是整体成本收益承诺，也不能替代语义质量。

## 历史失败及仍需独立复核

原始证据全部保留：首次完整门禁 [280 passed / 6 failed](evidence/v2-02-task232-full-regression.log)，保护标志 false。只读[补充审计](evidence/v2-02-task232-snapshot-audit.txt)在内存副本把水位归一后核对所有行列和 hash 一致，实际数据库水位没有回退；当时 +9 是 Hybrid 稀疏索引未就绪导致其预期两次发布/清理未发生。隔离库补齐稀疏准备、退款实际门禁缺陷和旧测试替身适配后获得修复前 [287 passed](evidence/v2-02-task232-full-regression-r2.json)。实际进程探针最初两次 Windows 子进程启动失败，以及真实 Hybrid 首次属性访问失败也分别保留，成功的清理不代替当次未执行查询。

摘要 r1～r5 的失败及每轮原文保留于 [fix01](fixes/records/v2-02-task232-fix01-report.md)、[fix02](fixes/records/v2-02-task232-fix02-report.md)和[fix03](fixes/records/v2-02-task232-fix03-report.md)；最新 r6 独立质量复测不覆盖这些历史。`V202-232-QA-001/002/003` 的正式关闭与整 Task 结果交主 Agent 和独立 QA。模型生成仍可能遗漏或误述，历史摘要始终为低信任背景；真实外部模型 Knowledge Graph、机器断电与客户端界面未在本轮实测，不能由受控或组件证据替代。
