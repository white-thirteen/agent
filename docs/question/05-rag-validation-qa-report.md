# Task5.2.2 独立 QA 报告

2026-11-14。结论：**PASS，仅 Task5.2.2**。未发现需新增编号的产品缺陷，无本 Task 未关闭阻塞。交主 Agent 裁决，不代表05阶段 ACCEPTED、Git授权或进入5.3。

依据：根 AGENTS.md、STATE、[执行任务](../05-rag-validation-execution-task.md)、[QA任务](05-rag-validation-qa-task.md)、D05第6～8/11节及5.2.2、[开发报告](../rag-validation.md)。执行者为原生 `/root/qa522`；独立读取实际源码、固定样本及原始JSON，未修改业务、既有测试、配置、迁移或旧证据。

## 实际独立验证

使用项目 `.venv` 执行：

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_05_rag --output docs/05-rag-qa-independent-evidence.json
.\.venv\Scripts\python.exe -m ruff check scripts/verify_05_rag.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/verify_05_rag.py
```

全部 exit 0；新[独立证据](../05-rag-qa-independent-evidence.json)中 `selected_cases_completed/protected_unchanged/temporary_sources_removed` 均为 true。SHA256：`5136e3446f583c9557986f18c2d6d5045e4457ff7b2bb73b972f671c0741d6e7`。本轮启动26.896秒、完成清理56.281秒，Qwen正常排空关闭，无强杀或重启。

实际组合为Windows本地 Qwen3-Embedding-0.6B、CPU、BF16、1024维、L2、demo-v1；权重revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，Tokenizer摘要及完整Profile见JSON。Chat为配置的 `api.deepseek.com / deepseek-flash`。PG在线身份为 `agent_demo_test / agent_test`，PG17.6、vector0.8.7、schema6；写测试数据前在线核对全部迁移checksum与仓库一致。

本次独立执行3条真实Qwen+Chat+PG的正式FastAPI路由、Service、Runtime、主图、八节点子图、Saver与SSE请求，共10次真实Chat尝试；HTTP由ASGITransport调用，没有TCP监听或uvicorn。另10次受控结果保留真实Qwen/PG，Chat使用明确受控Provider；故障样本使用命名注入，不冒充真实Chat质量。

| 样本 | 实际结果及人工语义判断 |
| --- | --- |
| normal | completed，6.394秒，模型4次/工具2次。实际命中首位 `demo-refund-safety`，公开1条当前来源。逐句对照 `data/knowledge/refund-safety.md`：无真实支付、只改变模拟数据、稳定操作编号防重复、未知先核对，均有正文支持；没有声称已执行退款。自然概括语义 PASS |
| no_answer | insufficient/rejected，4.854秒，模型3次/工具1次。检索片段是退款/审批资料，无法支持火星量子发动机保修年限；公开固定拒答、sources为空，没有编造期限。语义 PASS |
| conflict | conflicting/rejected，4.953秒，模型3次/工具1次。两份自有资料分别固定30/90天，评估识别矛盾及缺乏优先依据，公开拒答且没有选择任一天数。语义 PASS |
| weak / forged | 分别 rejected/evidence_insufficient、failed/citation_invalid，无正文及来源。受控边界 PASS |
| wrong_body | completed、1条合法当前来源，但“银行卡已经真实扣款成功。”完全无来源支持，**人工语义 FAIL（冻结要求的故意反例）**。程序来源通过不等于正文正确；没有将该条算作语义通过 |
| malicious | 受控安全回答，2次只读工具，不出现注入标志；完整业务行集未变。结合实际allowlist确认不能执行退款/Store。受控权限边界 PASS，不宣称真实Chat普适抗注入 |
| update / delete | 实际改写/删除自有文档后均 failed/source_changed；草稿及来源均未公开。PASS |
| no_scope / tool_budget | 分别 rejected/tool_not_allowed（0模型/0工具）、failed/tool_budget_exceeded（模型3次/工具1次），均无正文/来源。PASS |
| faults 两次 | failed/embedding_timeout及failed/retrieval_timeout，各1次工具尝试，无正文/来源。真实Qwen极短期限、真实PG独立事务语句取消后边界映射，均未伪装empty。PASS |

在上述脚本断言之外，QA另以项目Python读取新JSON，独立断言13个结果完整、保护行集摘要一致、正常首位文档/来源key正确、公开Task/workflow/run关联、每例唯一公开正文、原生call ID数量、Executor记录Task/run/attempts和工具计数一致、拒答状态及受控精确失败码，全部通过。检查原审计中两份开发证据SHA256仍匹配，未覆盖旧证据。原首轮受控预算fixture顺序失败继续保留，后续受控重跑与真实成功证据没有混为整轮成功。

## 源码与门禁

检查 `scripts/verify_05_rag.py`、`tests/fixtures/knowledge_cases.json`、`app/graph/specialists/knowledge/builder.py`、`app/tools/implementations/knowledge.py`、`app/knowledge/retriever.py`及`repository.py`：固定12样本覆盖范围与模式标注符合要求。真实请求从当前Human构造检索问题；搜索原生ToolCall与ToolMessage配对、来源复核经同Executor计数；父图没有私有ToolMessage，SSE仅输出最终正文及服务器PublicCitation。检索精确余弦、candidate5/top3、阈值null、2400tokens/24KiB保持，低信任证据以数据角色进入模型，不授予工具权限。失效来源、技术错误及预算失败均走失败出口。

本 Task未改生产实现或依赖。完整门禁明确复用[5.2.1交付](../05-knowledge-tools-delivery-report.md)的192 passed / 0 failed / 0 skipped、全仓Ruff与15文件格式检查，以及[5.2.1独立QA](05-knowledge-tools-qa-report.md)的78 passed及追加行为探针；本Task开发另有21项真实PG定向通过，见开发报告。本QA没有重跑上述pytest，不把引用结果称为自己执行；自己新增执行结果为本报告3条真实请求、10次受控结果、JSON独立断言及脚本Ruff/格式通过。没有skip或deselect替代通过，依赖未变未重复pip check。

## 隔离、清理与遗留边界

本轮自有UUID前缀 `rag522-3a7ef2e2658349d98849613c561f38d2`，会话/文档及正式Task/run/thread均独立；HTTP身份沿项目允许的 `dev-user`，没有新增或声称创建唯一用户。受控子图使用既有内存fixture的task/run标识，不将其算作正式Runtime身份验证。清理精确限定自有文档ID、该用户与完整会话ID列表，以及Saver公开 `adelete_thread` 的自有线程；临时源文件逐个删除，空目录移除，没有seed、前缀批删或开发库写入。

清理前后11张保护表完整排序行集相同：sessions、demo_orders、refund_requests、approvals、schema_migrations、checkpoints、checkpoint_blobs、checkpoint_writes、checkpoint_migrations、knowledge_documents、knowledge_chunks。原5订单保持；迁移6行、Checkpoint迁移10行，其余8表均恢复0行。实际排序行集SHA256与清理对象列表完整保留于独立证据，不输出业务行正文或凭据。未修改.env/006、安装、SSH、DB重启、Git、Bridge或另派Agent。

来源仅证明checked_at时刻当前有效。真实Chat恶意资料、精确伪引用、故障及弱相关泛化能力未全面实测；本轮不证明TCP/uvicorn/Apifox、断网或进程重启行为。PG故障使用真实独立会话 `statement_timeout=1ms` 与 `pg_sleep` 后映射，不声称生产余弦SQL自然超时。模型正文语义仍需人工核对，小固定集不提供通用准确率或阈值校准统计。以上为明确证据边界，无本Task待修产品问题。完成后停止。
