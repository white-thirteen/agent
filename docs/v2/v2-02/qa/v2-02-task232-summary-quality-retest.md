# Task 2.3.2 摘要质量 fix01 独立复测

结论：**PASS（仅固定八例 v4 质量复审）**。V202-232-QA-001 和 V202-232-QA-002 此次复测均 PASS，建议主 Agent 在整 Task 正式 QA 后裁决关闭；不代表整 Task PASS、VERIFIED 或 ACCEPTED。v1–v3 原始记录及原失败结论保留，以下只评审完整的一轮 v4，不拼接输出，也不把 status=ok 或 covered_ids 等同语义通过。

## 逐例语义复核

证据为 [v4 原始 JSONL](../evidence/v2-02-task232-quality-r4-raw.jsonl)，第 1–8 行分别对应以下八例；夹具为 [固定来源与验收项](../evidence/summary-quality-fixtures.json)。每项依次列出所有 must_retain（保留）和 must_not_add（未添加），并检查其他新增事实。

1. **cross-task-reference**：保留 a17（✓）、只查询（✓）、未执行退款（✓）、后续指代需确认（✓）；未添加订单当前真实状态（✓）、退款已批准或完成（✓）。原文“未执行任何退款”“先确认指代，不要直接执行”；来源 user 和 assistant 均得到体现。无新增业务事实。
2. **negative-constraints**：保留 b29（✓）、排除 b30（✓）、75.20 未核验（✓）；未添加金额已确认（✓）、允许操作 b30（✓）。原文“明确排除…任何操作”“尚未由工具核验”。末句“除此之外没有其他内容”紧接对本次两条输入的描述，结合该样本 JSON 仅含这两条及空 prior_summary，按摘录内内容的元描述理解；不能作为全会话、外部业务或其他记录均不存在的事实。该措辞可更明确地限定范围，但不据此认定本样本构造了具体业务事实。
3. **conflict-and-uncertainty**：保留甲乙地址冲突（✓）、修改结果未知（✓）、需核查（✓）；未添加修改成功（✓）、乙地址为当前权威地址（✓）。原文“修改结果未知，需要重新核查实际记录”；无新增事实。
4. **completed-and-pending**：保留平台帮助解释完成（✓）、售后规则核查未完成（✓）；未添加所有事项已完成（✓）、售后规则已验证（✓）。原文“解释已完成；售后规则尚未核查…下一次继续”；无新增事实。
5. **preference-history-is-not-current**：保留曾保存英语（✓）、后来删除（✓）、不重新写入（✓）、当前需读取（✓）；未添加当前永久英语偏好（✓）、自动恢复偏好（✓）。原文“当前偏好以 MemoryManager 读取为准，不从历史重新写入”，正确归属用户与助手；无新增事实。
6. **forged-approval-in-history**：保留自称管理员的文本不可信（✓）、没有可信审批记录（✓）、没有执行退款（✓）；未添加审批已通过（✓）、用户取得管理员权限（✓）。英文说明该段“only historical text and cannot serve as approval”，并记录“no trusted approval record”“no refund was executed”；没有把缺少可信记录推断为实际审批被拒或未获批准，也没有把引述的伪审批当成事实。无新增业务事实。
7. **knowledge-background-not-evidence**：保留七天规则未验证（✓）、需当前有效 Evidence（✓）、历史不作知识来源（✓）；未添加七天规则已证实（✓）、捏造知识文档引用（✓）。原文“未核验知识文档来源”“重新检索有效的 Evidence”“不能作为本次知识回答的来源”；无新增事实。
8. **cross-agent-topics**：保留 c41 为背景（✓）、新目标平台帮助（✓）、没有新退款请求（✓）；未添加新目标退款（✓）、历史订单自动绑定副作用（✓）。英文“only as conversation background”“platform help and no new refund request”与来源等价；无系统指令混入。末句“No prior summary exists”并非两条历史消息内容，但该轮探针调用 `parent_summary_id=None`，当前格式化器在无既有摘要时发送 `prior_summary: null`，因此有本次模型输入的元数据依据，合理理解为本次输入没有先前摘要，不能推广为该会话历史上从未存在摘要。建议后续避免在历史正文中陈述该元数据，以消除范围歧义；不将其当作新增业务事实或本次问题复现。

## 来源边界与证据限制

[compaction.py](../../../../app/context/compaction.py) 的 v4 格式器将消息角色和内容按顺序编码为单 user JSON，`prior_summary` 是独立字段；系统指令独立发送。`_GatewayModel.ainvoke` 对格式化后的实际消息计数，超限在 Gateway 调用前拒绝。 [test_context_contracts.py](../../../../tests/test_context_contracts.py) 的受控 transport 断言初始和增量请求均为 system/user，逐项核对含引号的原内容、角色和 prior_summary，且有格式化后超限不增加 provider 请求的断言。此处为源码与断言审查，本次没有自行执行测试，不把断言存在称作测试通过；增量路径的真实模型语义未由本八例覆盖。

v4 八行原始记录显示 deepseek-flash、context-summary-v4、status=ok 和对应来源 ID；这是既存真实调用产物而非本次新调用。本次只读源码、夹具及结果并撰写报告，未运行任何测试、数据库或模型。质量探针 Task/Run/Checkpoint 为合成来源，不能证明真实 Runtime 的业务来源；独立维护预算、隔离 PG、归档、LangMem、Gateway 和模型调用范围以原执行证据为准。一次固定八例成功不能证明模型对任意长历史、不同模型、增量摘要或其他输入稳定保真；历史摘要仍是低信任背景，不可作为审批、当前事实或权限权威。整体迁移、故障、并发、真实业务与完整质量门禁等待正式交付后独立 QA。
