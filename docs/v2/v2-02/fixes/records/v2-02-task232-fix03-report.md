# Task 2.3.2 fix03：摘要直接陈述边界

关联 [fix03 任务](../v2-02-task232-fix03.md)和 `V202-232-QA-003 / P2`；本记录提交原独立 QA，问题关闭及摘要质量结论由 QA 和主 Agent 判定。

`app/context/compaction.py` 将摘要提示和策略版本更新为 `context-summary-v5`：完成/未完成状态仅保留来源直接陈述，未提及类别不补不存在或待办；无可信审批记录不推断审批决定。原 JSON 来源与说话方边界保留。`app/runtime/model_gateway.py` 仅对独立维护和经过摘要桥预检的运行内摘要绑定 `temperature=0`；普通模型及结构化业务路径不设置这一覆盖。摘要桥仍对实际格式化后输入检查预算，且保留截断失败和实际耗用。旧版本引用及回执继续按其原版本核验，不复用为 v5 摘要。

实际验证：

- `linux-pg-launcher.py pytest tests/test_deepseek_output_limits.py tests/test_context_contracts.py tests/test_model_gateway.py tests/test_context_compaction_postgres.py tests/test_context_maintenance_runtime_postgres.py tests/test_context_run_compaction_postgres.py -q --tb=short`：**23 passed**，1 条上游弃用警告，[原始输出](../../evidence/v2-02-task232-fix03-controlled.txt)。真实 LangMem、隔离 PostgreSQL/文件，受控 HTTP transport 核对初始/增量 JSON 来源、输出上限、摘要运行/维护请求的 temperature=0、普通及结构化请求未增加该覆盖、编码后预算和截断/usage。
- `linux-pg-launcher.py module docs.v2.v2-02.evidence.v2-02-task232-quality-probe --quality-r6`：固定八例完整真实生成一次，八次均返回；供应商 `deepseek-flash`、v5、实际输出39～72 tokens，覆盖 ID、原始摘要和用量见 [r6](../../evidence/v2-02-task232-quality-r6-raw.jsonl)。独立 QA 须按事实、否定、冲突、未知和新增事实逐项审核，不能以成功调用、覆盖 ID 或温度参数替代语义结论。r1～r5 原始结果和失败保留。
- temperature=0 是实际发送策略，不证明服务端输出确定或语义必然正确。[DeepSeek Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)说明 thinking 模式下该参数无效；本次配置 `reasoning_effort=none`。其 [Ignored Parameters](https://api-docs.deepseek.com/guides/build_a_chatbot/#ignored-parameters) 条款限定 web search/read、safety_check=high 或 title 等条件，本摘要未启用这些条件，不将该条款误写成全部非思考调用均忽略温度。
- [资源实验 r3](../../evidence/v2-02-task232-resource-runtime-r3.json)采用当前 v5 和真实 Runtime 创建的单个 Task/Run：在同一实验节点对相同当前问题、模型、Schema/工具及512输出预留，分别注入完整24条历史及生成摘要。供应商实际 input **6958→225**；摘要生成额外 input 6121、output 136、耗时1.70秒，使用独立的一次真实调用，三次调用共消耗该 Run 三次尝试。摘要上限512，未触发 length。资源观察不替代摘要质量，也不能把消费输入变化直接称为总成本收益。隔离PG/Saver清理和保护快照通过。此前[r2](../../evidence/v2-02-task232-resource-runtime-r2.json)使用 v4，原样保留。

模型和提示修复后完整门禁 **290 passed / 0 failed / 0 skipped**，真实 Qwen 与隔离 PostgreSQL/Saver/Store；受保护快照通过，水位 36→47 与预审计 +11 一致。原 seed 窄例外未跳过。见[原始回执](../../evidence/v2-02-task232-full-regression-r3.json)。此前287项完整结果是修复前证据。
