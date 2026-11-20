# Task6.1.2 会话/状态/事件统一

6.1.1独立QA PASS与主Agent复核已通过，现正式单独派发6.1.2，IN_PROGRESS。用户已授权06阶段，依据根AGENTS/STATE、D06第5/6/9节及Task6.1.2、6.1.1最终交付/QA和必要前序协议。旧“待冻结/未授权”保留设计历史，不重设计Task。

沿实际已实现代码核对并补最小接点，完成正常Route→Service(context/options/owner)→唯一Runtime.submit→Graph/finish→RunView/SSE。Route只解析一次，request_id可省略不承诺去重，input_mode原样显式转交，task_id仅Runtime创建、workflow同值别名。顺序Task同thread、澄清保留原Task/预算、同thread互斥、审批等待普通输入409；跨Task专业槽/来源/偏好读取记录清理，不能携带另一Task私有历史。

现有四类退款Resume/repair-binding按04实现：原thread/call/op、新实际推进Run、普通END只读返回持久结果无新Run/Graph/副作用、未知快照不盲重放。不要再实现第二Workflow/Repository或另建恢复API；真正故障矩阵交6.2.1，本Task只验证公共关联/状态投影和既有恢复接线。

已证实的观测区别：子图真实interrupt期间，父图最后已完成Checkpoint可仍是running；以实际interrupt/公共Runtime状态及原调用记录核验等待和预算，不能为断言一致而修改框架快照或把旧父计数当完整用量。

事件/公开结果遵循D06权威：run/task/business状态分别来自自身，done只表本次run结束；run_finish真实持久收敛后才发最终token/source和终态，唯一done/稳定sequence。KNQA正文原样approved_answer及服务器PublicCitation；Memory显式结果/unknown安全说明按原契约，无伪造知识来源。状态、内部工具/推理/凭据/全量证据不可透传。当前Task持久查询与可丢失Run缓存查询边界要真实，缓存30分钟100终态/8活动规则不改，HTTP去重不替代业务op幂等。

Owner资源覆盖首次迭代前/中途断开/慢订阅，订阅清理而执行继续，重订阅不重放旧token；复用已有02测试与必要组合，真实TCP断开/大故障留6.2.2按需，不无收益重复所有旧矩阵。多专业顺序/澄清/公开来源与Memory状态使用真实PG/Saver/Store，模型可受控以验证确定事件；真实Chat/Qwen证据复用未变6.1.1，不把受控输出冒充付费调用。

数据仅test库agent_demo_test/agent_test，身份/全部迁移checksum、完整public行集/列定义保护，UUID订单/KB/profile/session/thread，按FK精确清理。原固定五订单禁止新场景改动；完整回归原seed幂等单例外按AGENTS保留不deselect。不覆盖.env/006/旧证据/角色配置/六项暂缓差异。验收进程允许Settings.test目标/UUID/EmbeddingTrue(原QwenCPU路径/预算)，不改Codex模型provider账户。无SSH/PG重启/原容器重建/有损迁移、无Git/Bridge/另派Agent/下一Task。

不为制造改动重写已有接线。按风险定向测试，公共行为实质改动需最终完整真实PG门禁/Ruff/改动格式；纯验证增量可复用未变全量门禁并明确来源。交docs/v1/v1-06/06-state-events-delivery-report.md及必要脱敏证据/README导航，不改STATE/AGENTS/主协调。完成停止交独立QA；FAIL回原Implementer并按docs/v1/v1-06/fixes与record保留关联Task/问题/提示词。
