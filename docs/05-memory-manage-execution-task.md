# Task5.3.2 显式记忆管理与幂等更新

5.3.1独立QA及主Agent复核已完成，05-QA-001已关闭；本Task由主Agent于2026-11-14正式单独派发，当前IN_PROGRESS。用户2026-11-14已授权继续05，冻结D05第2.1/6/9/10节及Task5.3.2是完整验收依据，不重设计Memory。根AGENTS/STATE、5.3.1最终实现/证据及现有D03 prepare_attempt/execute_prepared、D04 sync契约必读；必要源码完整读，历史按需。

范围：同一MemoryManager增apply、既有Knowledge wrapper的MEMORY_MANAGE分支/命令小图和少量Supervisor提示/契约接点。仅answer_language=zh-CN/en、answer_style=concise/detailed。不得MemoryWriter/新增Agent/额外Graph平台/自动扫描恢复/HTTP修复/全局阻断/独立幂等表/分布式锁。其他订单退款审批逻辑不改，06不启动。MEMORY_MANAGE资源就绪与QA检索就绪分开：Store及命令能力不能因Embedding关闭/不可用被错误禁用；QA缺向量资源仍按原不可用语义。

- 当前Task可信原始Human通过task_message_ids定位，wrapper入口仅一次确定语法解析，放既有命令节点模块，产规范MemoryCommand和source_message_id；模型实体只是候选。D05固定保存/修改/删除/清空/查看及两种“请删除我的回答…偏好”等义格式全部适用；敏感/自由文本/文档指令/模型自发/混合任务不得授权写。澄清继承原Task/预算与可信来源，旧任务/AI回复不能当同意。
- command read进入同Reader工具；写命令准备与执行分开Graph节点。prepare_memory_write经同治理读取真实revision，生成稳定op/digest/expected_revision和目标write call，调用原executor.prepare_attempt（真实准备context、编译目标execute_memory_write context及最小MemoryBusinessContext），不预扣handler/tool计数；原命令/关联/call/marker/预算基线完成真实durability=sync才能execute_prepared。失败无write handler/Put，不能State布尔或END后快照假sync。
- execute_memory_write每次按当前Task/run/节点/scope/参数/工具版本/预算/marker复核，由同Executor投影最小可信业务context到handler，再交Manager.apply。Policy固定node-origin/KNOWLEDGE/MEMORY_MANAGE/execute_memory_write；model来源、错节点、allowlist缺失/错参数拒绝零handler。准备节点不能直接execute写。禁止把客户端身份/revision/op/批准字段传入权限判断。
- apply单进程per-user短锁，在同一profileItem保存revision/preferences/last_mutation。公开abatch单GetOp/PutOp顺序读取/写入，锁覆盖实际调用；不声称Store原生CAS或跨进程保护。同op/digest精确匹配复用，不同digest冲突，旧expected_revision不覆盖后续新值。delete/clear真去偏好值但保留最小版本/幂等元数据，旧写不复活；不冒充聊天/Checkpoint合规全擦除。
- 写/网络/取消边界按D05 10.3～10.5：Put前明确失败技术not_started，进入Put后无法确认提交为领域unknown，不自动重试。已知原操作故障重进先核对、replay_check_only=True绝不Put，即使revision未变也不能判未提交；材料丢失/已被后续操作覆盖继续unknown，未知不回退普通写。Policy/预算阻断核对时保留原unknown关联。Runtime取消传播，不能伪造已持久结果。
- Manager只返回applied/reused/conflict/unknown，不定义failed。handler/Executor分别success/completed、business_rejected/not_started、failed/memory_result_unknown/unknown并保留领域载荷；实际进入handler核对计一次、已记录结果复用零新增handler。unknown正文明确“本次偏好写入结果未知，请先核对，再提交新的记忆修改”，不新op绕过、不自动恢复、不清空领域结果。
- 复用既有Result/父子白名单/Run和Task累计预算，写后真实结果才公开，无知识sources。QA图保持八节点，wrapper每次仅选QA或命令图；原Task语义不随Store内容或新Run改变，退款审批等待仍409。资源Serializer仅必要白名单增量。

配置边界明确：不覆盖配置指不改用户.env及Codex模型/provider/账户配置；真实验证脚本可且必须在自身Settings/model_copy或子进程非秘密环境中设置embedding_enabled=True、固定原Qwen CPU模型目录及专用test目标，沿已批准限额。此前5.1/5.2也是如此，不得因.env默认embedding_enabled=False就宣称真实RAG因配置BLOCKED；实际依赖/内存/网络失败才如实报告。

模型路由/组合增量验证：Supervisor提示与共享Reader已变化，除受控风险用例外，以现有真实Chat对独立测试用户最少运行规范记忆保存/查看/删除链；至少实际保存answer_language=en并查看确认；另在同用户新会话用真实Qwen+Chat+PG正常中文知识问题验证英语偏好实际用于呈现（普通中文问题不等于明示中文回复），本轮明确语言要求优先可受控验证，且偏好只影响呈现、来源校验与新增读取预算正确。该有限联调属于05自身新增接线验收，不扩06退款/最终部署。不要重复全套真实RAG固定集或全部付费旧场景；真实输出/模型及清理写入独立证据，默认pytest仍不付费。已有验证脚本需更新受影响计数时保留所有业务/来源断言及旧JSON，不能把必需新read计数藏掉。不得为此创建诊断/恢复平台，按现有显式验收方式即可。

真实验收：专用testPG/Store，原业务/Saver/知识/他人profile完整行集保护、在线身份和全部迁移checksum；独立UUID测试身份和原op，精确清理，不seed/覆盖Demoprofile或订单。覆盖显式CRUD/查看/两种删除同义格式、A跨会话/thread共享B不可见、完整新进程持久读，权限/节点/参数拒绝、sync失败零handler/准备零计数、handler进但无Put计一次、并发revision冲突、同op幂等/旧op不覆盖、unknown与故障重进只核对/无Put。受控故障可替身但持久化不能Mock；测试层和未验清楚，不skip伪通过。最终完整真实库回归、Ruff/改动格式；依赖变动才pipcheck，不复跑无收益的付费模型或PG重启。

交付docs/05-memory-manage-delivery-report.md及必要脱敏证据/测试、README导航，列文件/链路/命令结果/unknown人工边界。不得覆盖.env/旧证据/006/STATE/AGENTS/主协调；主Agent负责独立QA/状态/技术验收。无Commit/Push/SSH/Bridge/另派Agent，完成停止。QA定向修复必须在docs/resume/record关联Task/编号/提示词。
