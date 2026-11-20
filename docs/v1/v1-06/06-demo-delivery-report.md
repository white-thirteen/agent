# Task6.3.1 文件与真实功能演示交付记录

日期：2026-11-15。范围仅Apifox导入材料、演示脚本/说明及本Task验证。用户最新明确“接口文档做好，我来导入”，因此停止Agent桌面操作，GUI导入、变量运行和Apifox中的SSE显示交用户验证。当前记录不代表Task独立QA或06阶段验收。

## 修改位置

| 文件 | 内容 |
| --- | --- |
| `apifox/agent-engine-demo.postman_collection.json` | Postman v2.1，六组26请求，实际健康/chat/Run/Task/退款/本地审批/RAG/Memory；独立成功和拒绝订单；三处动态提取脚本 |
| `apifox/local.postman_environment.json` | 仅127.0.0.1地址和空白身份/关联变量，无模型/DB/管理密钥 |
| `docs/v1/v1-06/demo-walkthrough.md` | test目标准备、手工导入、动态原关联、两次完整服务重启、业务核对、隔离/CRUD和精确清理 |
| `scripts/demo_session.py` | UUID自有订单/真实Qwen语料准备，正式应用工厂、只读事实核对和按FK精确清理；准备部分失败也清理 |
| `scripts/verify_06_demo.py` | 显式分段真实TCP演示驱动，不进入默认pytest，不替代GUI导入 |
| `README.md` | 本Task说明/证据导航 |

OpenAPI规范及 `docs/v1/v1-06/apifox-api-guide.md` 由主Agent独立负责，本报告不代其生成或裁决。

## 实际执行与证据

全部Python命令使用 `.\.venv\Scripts\python.exe`。本轮仅专用 `agent_demo_test/agent_test`，真实Chat沿原DeepSeek配置，无受控模型替身；Qwen单实例CPU/1024，沿原预算/超时。未修改用户.env、006迁移、固定五订单，不执行seed、Git、SSH、Bridge、PG重启或容器重建。

1. `-m scripts.demo_session prepare --folder C:/Users/15294/AppData/Local/Temp/demo631-20261115-r1`：首次因fixture INSERT遗漏created_at而失败。PostgreSQL NOT NULL拒绝，没有伪成功；自动精确清理且全public原行列保持。已修为now()，原失败保留于 [准备失败证据](evidence/06-demo-prepare-failure-evidence-20261115-r1.json)。
2. 同命令以 `demo631-20261115-r2` 新目录重跑：真实Qwen准备成功，两个UUID订单各12.34 CNY及自有文档/1024维向量已落库。在线身份和001～006 checksum由既有全public snapshot门禁核验。
3. 以 `-m uvicorn scripts.demo_session:server_app --factory --host 127.0.0.1 --port 8631 --loop app.infrastructure.postgres:selector_event_loop --log-level critical` 启动，AGENT_DEMO_MANIFEST指本轮manifest。只停止命令已核对的自有PID：33488→43788→52760，两次完整进程退出后新建Runtime；PG全程保留。三进程现均已退出，8631无监听。
4. `-m scripts.verify_06_demo before-restart --folder <r2目录> --output docs/v1/v1-06/evidence/06-demo-before-restart-evidence-20261115-r1.json`：PASS，本人订单、偏好保存、真实waiting_approval/workflow_paused/done及普通chat批准409。[首段证据](evidence/06-demo-before-restart-evidence-20261115-r1.json)。
5. 完整重启后执行同驱动 `after-restart`，输出 `docs/v1/v1-06/evidence/06-demo-after-restart-evidence-20261115-r1.json`：PASS。原task/thread/call/raw及canonical args/operation/application/approval/digest/namespace/interrupt保持；原批准成功，另一独立订单拒绝；同决定和正常END重复resume复用原结果。实际Actor为local-demo-approval，SUCCEEDED订单is_refunded=true，REJECTED订单false。[恢复及真实RAG证据](evidence/06-demo-after-restart-evidence-20261115-r1.json)。
6. 上一步真实RAG正文明确普通聊天不能审批、应使用独立本地入口及固定审计操作者；人工语义复核与来源检查均通过，sources指向本轮真实document/version/chunk。库外温度问题rejected资料不足；没有为本Task重复注入技术故障，failed与不足的既有风险门禁复用6.2.2。
7. 再次完整重启后执行同驱动 `memory-after-restart`，输出 `docs/v1/v1-06/evidence/06-demo-memory-restart-evidence-20261115-r1.json`：PASS。A新会话和重启后SSE正文明确answer_style=concise，B为空；B查A订单rejected。A修改为detailed、删除指定字段、保存语言后清除，最终preferences={}，保留revision/last_mutation。[Memory证据](evidence/06-demo-memory-restart-evidence-20261115-r1.json)。
8. 最后停止52760并确认退出，再执行 `-m scripts.demo_session cleanup --folder <r2目录> --output docs/v1/v1-06/evidence/06-demo-cleanup-evidence-20261115-r1.json`：PASS，精确清理本轮profile/session/Saver线程/审批申请/两订单/语料，`protected_unchanged=true`。[清理证据](evidence/06-demo-cleanup-evidence-20261115-r1.json)、[原行集/列定义前后指纹及PID/GUI审计](evidence/06-demo-final-audit-20261115.json)。本机manifest和保护基线保留用于追溯，未导出完整原库快照。
9. 集合JSON逐请求核对正式 `create_app(...).openapi()` 路由、Pydantic请求模型、全部变量及无认证Header；Node对三段动态提取代码作受控响应执行：26请求/3脚本通过。[文件验证证据](evidence/06-demo-file-validation-evidence-20261115.json)。首次受控测试代码因局部变量重名失败，修正验证脚手架后通过，集合脚本未因该错误修改。
10. `-m ruff check scripts/demo_session.py scripts/verify_06_demo.py` 和 `-m ruff format --check scripts/demo_session.py scripts/verify_06_demo.py` 均通过。未变更业务代码/依赖，未无收益重复全套PG回归或此前故障矩阵。
11. 对本Task十三份脚本/说明/集合/证据作JSON解析、相对链接及已配置模型/DB凭据精确扫描，通过；仅输出检查结果，不输出凭据。

## GUI事实与未闭环项

Agent已实际启动Apifox，创建独立项目“Agent Engine Demo Task631 20261115”（9047819），进入Postman导入文件选择界面。此前发生物理Escape中断、最小化/用户输入恢复阻塞及文件模态目标不匹配；未成功选择或上传文件，**未完成集合导入**。收到用户由本人导入的新指令后，已完全停止GUI操作。

待用户手动验证集合实际导入、环境变量/后置脚本在该Apifox版本中的行为及SSE显示。多份chat样例使用同一接口路径，导入器如何保留样例需用户确认；说明给出人工提取原关联方式。当前文件/真实HTTP结果不能替代这些GUI结果，也不能替代后续独立QA。所有本轮自有后台服务已停止、测试数据已清理；无本轮数据库遗留。
