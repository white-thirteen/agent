# Task5.3.2 独立QA

仅主Agent在Implementer完成后派发才开始。必读根AGENTS/STATE、docs/05-memory-manage-execution-task.md、冻结D05第6/9/10节及5.3.2、实际交付。业务/既有测试/配置/旧证据只读，仅独立报告/临时复现；不代修/Git/Bridge/另派Agent/SSH/PG重启，不自行进06。

按真实风险独立审测：可信原Task Human一次确定解析（文档/模型实体/AI/旧Task不授权），所有固定规范和删除同义语法、混合/敏感拒绝、原Task澄清关联；wrapper每次只选QA或命令图，不重构Supervisor/扩MemoryWriter。

重点写前边界必须实际PG Saver验证：prepare_attempt真准备context+目标context+最小业务关联；准备零handler/零预扣，真实sync成功后execute_prepared最终当前身份/task/run/node/allowlist/参数/scope/版本/预算复核；sync失败零write handler/Put，旧Run marker不能执行，不用布尔或END后快照假sync。Policy错origin/节点/参数/allowlist拒绝零handler，无直接handler/Store旁路。

Manager.apply仅applied/reused/conflict/unknown，领域/Executor/effect_status分别核，不将unknown擦成failed技术不可用或not_started。同用户锁覆盖实际abatch GetOp/PutOp，revision和last_mutation同Item：同op复用、digest冲突/旧revision/旧op不覆盖、并发单winner；delete/clear去值留版本不复活。Put前明确失败与Put已开始未知分开；超时/取消不证明未提交、未知不自动重试，已知故障重进replay_check_only只核对无Put，材料丢失或后来写覆盖继续unknown。Policy或预算阻核对保留原unknown；特别复测“原unknown的核对在最终Policy被拒绝后再次重进”，不能复用该policy_denied/not_started缓存而清空原业务unknown。Runtime取消传播，人工提示正确，无自动跨会话恢复/全局阻断/新HTTP修复平台。

真实PG/Store用唯一测试身份/会话/Task/op，验证CRUD/查看、A跨会话/thread持久B不可见、新进程读取、正确来源无sources的SpecialistResult/公开回复；三个专业Reader回归不改订单退款事实。在线身份+全部迁移checksum，原业务/Saver/知识/他人Store全行集保护、精确清理。不seed/覆盖Demo用户，不用Mock持久化验收。故障注入可受控但标清层次，不skip。另核验最终实现的少量真实Chat记忆命令路由及偏好后真实Qwen/RAG链证据，读预算增加/来源和呈现约束不得用旧5.2.2计数或受控输出冒充；无需自己重复全部付费固定集。主Agent最终需要完整质量门禁，QA可复用最终未变Implementer全量并自己定向复测实际高风险，不无收益反复付费模型。

输出docs/question/05-memory-manage-qa-report.md：PASS/FAIL仅本Task、沿当前05-QA最大编号续号及严重度/位置复现、实际验证命令/通过失败跳过/未验、清理和资源/取消/unknown边界及门禁来源。失败停止交原Implementer修复，QA不代修；阶段ACCEPTED与06/Git均用户决定。
