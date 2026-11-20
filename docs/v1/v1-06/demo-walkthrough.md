# 本地演示操作说明（Task6.3.1）

当前接口以 `app/api/routes/agent.py`、`approvals.py` 和 `schemas/chat.py` 为准。
本演示使用真实 DeepSeek Chat、Windows 本地 Qwen3-Embedding-0.6B CPU/1024 和原 Ubuntu PostgreSQL17.6/pgvector0.8.7。订单、支付和退款全部是模拟数据及数据库状态变更。

2026-11-15用户已手动导入Postman并提供截图确认六组26请求/12变量。Agent已执行真实TCP功能演示；**客户端后置脚本实际执行、变量回填和SSE界面仍未实测**。不再操作GUI；人工提取关联的步骤继续可用。API规范与字段说明另见 [Apifox接口文档](apifox-api-guide.md)，首次环境初始化另见[README](../../../README.md)与[数据库复现](database-reproduction.md)。

## 准备独立演示数据

使用项目 `.venv`，保持当前 `.env`、模型/provider、预算和迁移不变。此脚本只连接已配置的 `agent_demo_test`，在线要求 `agent_test`、迁移001～006及当前checksum一致。先确认没有其他测试正在改库，保持单个 Qwen 实例。

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_session prepare
```

命令输出一个本机临时目录中的 `manifest.json` 路径。记录为下文 `<folder>`，勿将尖括号占位符原样执行。manifest只包含本轮 UUID 用户A/B、独立成功/拒绝订单及知识文档标识；`protected.pickle` 为本地生成的全public行集/列定义基线，留本机供清理验证，禁止导入他人pickle。准备失败自动按manifest精确清理已写数据，失败记录留在该目录；未完成准备不能继续演示。

指定 `--folder` 时必须使用新目录。重复指定已有目录会在取得本次目录所有权之前报FileExistsError，不启动模型、不改文件，也不清理上一轮数据；只有本次实际新建目录中的准备中途失败才进入其清理分支。留存旧轮次时改用另一新目录，不复用或覆盖原manifest/基线。

原环境初始化脚本为 `scripts.migrate`、`scripts.setup_checkpoint`、`scripts.setup_store`、`scripts.ingest_knowledge`。仅首次初始化一个新的目标环境时才按各自 `--help` 使用；`scripts.seed_orders` 同样只用于首次目标初始化。本次在原库上演示不得执行seed或修改固定五订单。`demo_session prepare` 已完成自有订单及自有语料的真实Embedding，不需要重复初始化。

在项目根目录启动一个单worker服务，另一个终端保留用于操作/核对：

```powershell
$env:AGENT_DEMO_MANIFEST='<folder>/manifest.json'
.\.venv\Scripts\python.exe -m uvicorn scripts.demo_session:server_app --factory --host 127.0.0.1 --port 8631 --loop app.infrastructure.postgres:selector_event_loop --log-level critical
```

该工厂使用正式 `create_app` 和原配置，仅覆盖专用test库、UUID允许名单、Embedding启用及日志级别；不使用测试模型替身。记录实际PID及启动命令，停止时只停止自己的该服务。`GET /health` 应显示agent、knowledge就绪及PG/Saver/Store/Embedding ready。不要把真实密钥、DSN或 `.env` 导入Apifox。

## 导入集合与变量

在 Apifox 新建本轮独立通用项目（不要导入到已有用户项目），进入“项目设置→数据管理→导入数据”，选择Postman格式，导入 [集合](../../../apifox/agent-engine-demo.postman_collection.json)。集合采用Postman Collection v2.1，有六组26个请求；[无秘密环境模板](../../../apifox/local.postman_environment.json) 采用Postman environment格式。按桌面实际导入界面导入环境；如版本不能直接导入环境，在新建本地环境中逐项按模板建立变量。同一chat接口有多个演示请求，导入器可能将其归为同一接口的用例，请保留各请求名称/Body；实际导入行为待用户验证。

| 变量 | 填写规则 |
| --- | --- |
| base_url | `http://127.0.0.1:8631` |
| user_a/user_b、order_ok/order_no | 从本轮manifest取得，不用历史证据中的值 |
| conversation | 先取本轮唯一c1，例如manifest.prefix加`-gui-c1` |
| conversation_new | 另一个本轮唯一c2，例如manifest.prefix加`-gui-c2` |
| run_id/task_id/application_id/approval_id/subject_digest | 初始留空，按本轮返回动态取得 |

普通请求JSON的user_id只是development/test允许名单中的演示选择，可选择名单内A或B。它不构成真实登录认证；领域层按选定身份校验订单和Store归属。本地审批组无管理key/Header/认证变量，Actor由服务端固定为 `local-demo-approval`，仅作审计；仅回环development/test开放，production不注册管理Router。

不要通过集合运行器盲跑所有请求。成功/拒绝、修复绑定、重启和未知结果需要操作者按事实选择。

## 顺序演示

1. “环境与健康→健康”确认全部资源；“普通chat与Run→本人订单”返回本轮order_ok真实金额12.34 CNY、paid、is_refunded=false。
2. 同conversation执行“申请模拟退款”。观察 `workflow_paused`、`waiting_approval` 及本Run的 `done`。done只表示此次流结束。普通“聊天不能审批”应409，不能改变审批。
3. 执行“Task与退款事实→当前Task 提取关联”。响应 `current_task.refund.application_id/approval_id` 对应原申请；后置脚本将关联写入当前环境。执行“独立本地管理→原审批 提取digest”取得原 `subject_digest`。可人工复制相同字段作对照，不从列表猜选他人的审批。
4. SSE首帧顶层data含 `run_id/task_id`；手工填run_id，或从当前活动Task填入。旧Run结束后 `current_task.run_id` 可为null，因此集合不会用null覆盖已有run_id。查看Run状态/Run事件请求前确认是本轮原run。流订阅只给当前快照与后续事件，无历史重放；禁止传Last-Event-ID。订阅断开不取消执行。
5. 将原审批/申请/task等关联记录下来，**完整停止自己的FastAPI进程并确认PID退出，保持PG运行**。以同manifest、版本及命令启动新进程，确认新PID与健康就绪。旧进程Run缓存丢失，可通过持久“当前Task”和“原审批”查询；不要重发退款chat来代替恢复。
6. 查询原approval仍PENDING、bound，核对digest。执行“批准原审批”，返回 `resume_required=true`；随后**独立**执行“resume原审批”，202并产生新run_id，task_id保持原值。用新run_id与原conversation查状态，直至completed。申请状态SUCCEEDED、模拟订单is_refunded=true，原operation只成功一次。
7. 再提交相同决定、resume：正常END返回200、accepted=false、run_id=null、原持久结果。相反决定409。审批有效期30分钟，过期不能新增退款写；unknown时先核原operation，禁止改ID盲试。
8. 换新conversation，执行“独立订单退款 用于拒绝分支”（使用本轮order_no）；等待原审批后重新取得该分支的申请/审批/digest，提交REJECTED，再独立resume。最终Task rejected、申请REJECTED，order_no的is_refunded仍false。
9. 换新conversation执行RAG“真实知识问答”。正文应明确普通聊天不能批准，审批经独立本地入口；RunView的sources需指向本轮manifest.document_id、相同version及真实chunk。正文语义与合法引用分别核对。执行“资料不足”应rejected，并明确不足；技术Embedding/PG错误是failed，不能称为无资料。
10. Memory“保存偏好”→A“新会话读取”，预期answer_style=concise。完整停止该自有服务，再按同manifest启动新进程；新conversation读取仍concise。A/B新会话各用其自身user_id：B读取为空，B查询A订单被拒绝；选择A作为对照可读取A订单。这只证明选定身份后的数据隔离。
11. A“修改偏好”后为detailed；“删除指定偏好”后该字段消失；“保存语言”后清除全部，再“最终读取”为空。每次写观察实际revision递增；清除仍保留revision和最小last_mutation元数据，不等于抹除历史Checkpoint。

## 事实核对、关闭与清理

在后台无活动执行时运行只读核对，输出到本轮新证据路径：

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_session audit --folder '<folder>' --output '<new-evidence.json>'
```

输出本轮session/thread、原申请/task/call/operation/approval/namespace/interrupt及Store profile。成功前后应保持原关联、原规范参数，只有业务/审批状态变化；一张SUCCEEDED/is_refunded=true，一张REJECTED/is_refunded=false。实际Actor固定，B profile为空。引用再对照manifest的文档version/chunks。

停止本轮全部自有服务并确认PID退出后，精确清理：

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_session cleanup --folder '<folder>' --output '<new-cleanup-evidence.json>'
```

清理仅本轮用户的profile/session、Saver自有线程、申请/审批、两订单及自有知识文档，按FK顺序处理。必须看到 `protected_unchanged=true`，表示全部public原行集/列定义、迁移checksum一致；失败时保留临时manifest和基线定位，不扩大删除范围。本机临时目录可在证据落盘后由操作者按精确目录删除；不要导出其完整数据库基线。

可选HTTP功能复跑驱动 `scripts.verify_06_demo` 分三个stage：before-restart、after-restart、memory-after-restart，两个stage之间完整重启上述服务。每次 `--folder` 指向同一轮，`--output` 必须是新文件。这些证据仅证明真实HTTP功能，**不替代Apifox GUI导入、变量和SSE验收**；不要把手工流程和驱动混在同一组订单重复执行。

| 现象 | 定位 |
| --- | --- |
| health未ready/503 | 先查相应资源就绪，勿继续发退款；本地模型内存不足要记录失败 |
| 普通chat 409 | 原会话仍等待/执行，使用原Task/审批，不新建operation绕过 |
| resume 409 | 核digest、绑定、安全位置、有效期和当前活动Run；未知结果先核原业务 |
| 重启后旧run 404 | Run缓存属进程内；查持久Task、原申请/审批 |
| RAG rejected | 查看资料是否支持问题；与技术failed分开 |
| Memory unknown | 暂停该profile新写，核原operation/revision/last_mutation；不重建operation盲试 |
| Apifox用户输入/最小化阻塞 | 保留GUI失败，重新观察可用窗口后操作，不用静态JSON或HTTP冒充已导入 |
