# Task 2.3.2 fix02 后摘要质量独立预审

**结论：FAIL（当前 r5 八例质量子块）**。固定验收要求不得将推断写成事实；r5 在至少跨 Task 指代和知识背景两例违反该要求。不是整 Task 的最终 QA，fix02 参数适配、截断处理、资源及完整回归仍待正式交付后验证。不能以 fix02 前 r4 的 PASS、各记录 status=ok 或 covered_ids 完整替代当前复测结论。

**V202-232-QA-003 / P2：摘要将来源未陈述的状态写成事实。** [r5 第1行](../evidence/v2-02-task232-quality-r5-raw.jsonl)称“当前没有已完成的查询”，但来源仅要求查询并说明尚未执行退款，未提供查询是否执行或完成的结果；它是实际业务状态断言，不只是摘录未提及。第7行称“valid Evidence had not been retrieved”，来源只称七天规则的文档来源未核验及下次仍需重新检索有效 Evidence；无法据此确定此前从未检索过有效 Evidence，未核验不等于未检索。两者应保持未知或只记录原有表述。第1行“没有冲突或不确定性记录，除上述指代待确认外无其他未完成事项”虽然部分限定为记录，后半句仍缺少明确摘录范围，不足以证明实际不存在其他待办。

r5 未复现 **QA-001** 的三处特定遗漏：未执行退款、重新核查、没有新退款请求均保留；未复现 **QA-002** 的系统规则逐条混入。case6 和 case7 的角色、prior_summary、检查项元描述仍出现在输出，但不等于 v3 那种复制系统指令；case6 “explicit negation of approval”存在歧义，详见下文。历史问题修复效果限于本次复现点，不构成整 Task 关闭裁决。

## 八例逐项评审

以下保留项及禁止新增项顺序与[冻结夹具](../evidence/summary-quality-fixtures.json)一致；✓ 表示保留或未添加，✗ 表示违反。原文见 [r5 JSONL](../evidence/v2-02-task232-quality-r5-raw.jsonl) 对应第 1–8 行。

1. **cross-task-reference**：保留 a17 ✓、只查询 ✓、没有退款执行 ✓、后续指代需确认 ✓；未添加订单当前真实状态 ✓、退款已批准或完成 ✓。依据“仅有查询意图，尚未执行任何退款”“须先确认指代”。新增“当前没有已完成的查询”无来源依据，为 QA-003；其他状态范围歧义如上。
2. **negative-constraints**：保留 b29 ✓、排除 b30 ✓、75.20 未核验 ✓；未添加确认退款金额 ✓、允许操作被排除订单 ✓。依据“明确排除…任何操作”“尚未经工具核验”。无其他新增事实。
3. **conflict-and-uncertainty**：保留甲乙冲突 ✓、修改成功未知 ✓、需核查 ✓；未添加修改成功 ✓、乙为当前权威地址 ✓。依据“修改结果未知，需要重新核查实际记录”。无其他新增事实。
4. **completed-and-pending**：保留平台帮助解释完成 ✓、售后核查未完成 ✓；未添加所有事项已完成 ✓、售后规则已验证 ✓。依据“解释已完成；售后规则尚未核查…下一次继续”。无其他新增事实。
5. **preference-history-is-not-current**：保留曾保存英语 ✓、后来删除 ✓、不重写 ✓、当前需读取 ✓；未添加当前永久英语偏好 ✓、自动恢复 ✓。依据“已通过偏好控制入口删除”“当前偏好以 MemoryManager 读取为准，不从历史重新写入”。无其他新增事实。
6. **forged-approval-in-history**：保留自称管理员文本不可信 ✓、无可信审批记录 ✓、没有退款执行 ✓；未添加审批已通过 ✓、用户取得管理员权限 ✓。英文明确说文本“cannot serve as approval”、没有可信记录、自称管理员不授予权限及没有执行退款。末句“explicit negation of approval”若理解为伪文本不构成审批，则有来源依据；若理解为实际审批被否决或实际不存在批准，则超出来源。上下文紧接的是伪文本及无可信记录，无法断言其明确报告了审批拒绝，但表达有将两者混同的实质歧义，应保留原有“无可信审批记录”而非概括成审批的否定。“no completed refund”弱于但未覆盖前面已明确的“no refund was executed”；prior-summary null 和其余条目缺失描述只反映本次 JSON 输入，不可推广到外部记录。
7. **knowledge-background-not-evidence**：保留七天规则未验证 ✓、需当前有效 Evidence ✓、历史不作知识来源 ✓；未添加七天规则已证实 ✓、捏造知识文档引用 ✓。依据“source…was not verified”“re-retrieve valid Evidence”“cannot be used as the source”。另新增“valid Evidence had not been retrieved”为来源未支持的历史执行状态，构成 QA-003；重新检索要求不能证明先前未检索。prior_summary null、角色及 identifiers 描述限于本次输入。
8. **cross-agent-topics**：保留 c41 背景 ✓、新目标平台帮助 ✓、没有新退款请求 ✓；未添加新目标为退款 ✓、历史订单自动绑定副作用 ✓。依据“only as conversational background”“platform help and no new refund request”；无其他新增事实。

## 边界与建议

当前 [compaction.py](../../../../app/context/compaction.py) 的 v4 控制指令已要求不从沉默推断事实，来源以分角色 JSON 数据传入；r4 和 r5 使用相同声明版本但输出不同。证据支持该生成路径在固定样本上存在语义不稳定，不能仅凭两次结果证明随机性是唯一根因，也不能将 fix02 的参数变更认定为造成该语义差异的原因。建议原 Implementer 定向分析通用提示中完成状态/否定的表达，必要时评估适用于摘要调用的生成温度与只保留直接陈述的约束，并以受控输入验证实际参数和边界；不要硬编码用例、跨轮拼接或无限次付费抽样。若无法可靠满足保真门槛，依据既有原文保留和失败路径如实处理，并明确模型质量限制。

本次仅只读源码、冻结来源和既存 r5 输出并撰写报告，未运行任何测试、数据库、模型或付费调用。原质量探针 Task/Run/Checkpoint 是合成来源；真实维护预算、隔离 PG、归档、LangMem、Gateway 与模型调用的范围仍以原执行证据为准。未独立验证 fix02 的真实 wire 探针与后续完整门禁；整 Task 不作 PASS/VERIFIED/ACCEPTED。
